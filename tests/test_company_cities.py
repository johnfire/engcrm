"""City resolution for LinkedIn-created organizations: the pure decision rule,
the Places request, and the resolver's caching and failure handling. DB and
network are mocked — runs without Postgres or a Google key."""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.tools import company_places, db_linkedin
from gcrm.tools.company_places import PlacesError, decide_city, lookup_places


def place(name, city="Augsburg", country="DE", pid="p1"):
    components = [{"types": ["country"], "longText": "Germany", "shortText": country}]
    if city:
        components.append({"types": ["locality"], "longText": city, "shortText": city})
    return {"id": pid, "displayName": {"text": name}, "formattedAddress": "x",
            "addressComponents": components}


class TestDecideCity:
    def test_one_place_with_the_companys_name_resolves(self):
        decision = decide_city("fintiba", [place("Fintiba GmbH", "Frankfurt", pid="f1")])
        assert (decision.outcome, decision.city, decision.country, decision.place_id) == (
            "resolved", "Frankfurt", "DE", "f1")

    def test_same_name_in_two_cities_is_ambiguous_not_guessed(self):
        decision = decide_city("helios", [place("Helios", "Berlin"), place("Helios", "Augsburg")])
        assert decision.outcome == "ambiguous" and decision.city == ""
        assert {c["city"] for c in decision.candidates} == {"Berlin", "Augsburg"}

    def test_several_places_in_one_city_still_resolve(self):
        decision = decide_city("acme", [place("Acme", "Ulm", pid="a"), place("Acme GmbH", "Ulm", pid="b")])
        assert (decision.outcome, decision.city) == ("resolved", "Ulm")

    def test_places_with_other_names_are_ignored(self):
        decision = decide_city("acme", [place("Acme", "Ulm"), place("Acme Bakery Supplies", "Rome", "IT")])
        assert (decision.outcome, decision.city) == ("resolved", "Ulm")

    def test_no_place_carries_the_name(self):
        decision = decide_city("acme", [place("Totally Different", "Bonn")])
        assert decision.outcome == "not_found"
        assert decision.candidates[0]["city"] == "Bonn"  # kept for the review queue

    def test_nothing_found(self):
        assert decide_city("acme", []).outcome == "not_found"

    def test_a_named_place_without_a_city_is_not_guessed(self):
        assert decide_city("acme", [place("Acme", city="")]).outcome == "not_found"

    def test_small_spelling_differences_still_count_as_the_name(self):
        assert decide_city("hofmann consulting", [place("Hoffmann Consulting", "Ulm")]).outcome == "resolved"

    def test_international_country_comes_from_the_result(self):
        decision = decide_city("globex", [place("Globex Corp", "Austin", "US")])
        assert (decision.city, decision.country) == ("Austin", "US")

    def test_falls_back_to_postal_town_for_places_without_locality(self):
        raw = {"id": "x", "displayName": {"text": "Acme"}, "addressComponents": [
            {"types": ["postal_town"], "longText": "Reading"},
            {"types": ["country"], "shortText": "gb"}]}
        decision = decide_city("acme", [raw])
        assert (decision.city, decision.country) == ("Reading", "GB")


class TestLookupPlaces:
    def respond(self, status=200, body=None):
        request = httpx.Request("POST", "https://places.googleapis.com/v1/places:searchText")
        return httpx.Response(status, json=body or {}, request=request)

    def test_asks_only_for_address_fields_and_sends_only_the_name(self):
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", "key"), \
                patch.object(company_places.httpx, "post",
                             return_value=self.respond(body={"places": [{"id": "1"}]})) as post:
            assert lookup_places("Acme GmbH") == [{"id": "1"}]
        kwargs = post.call_args.kwargs
        assert kwargs["json"]["textQuery"] == "Acme GmbH"
        assert set(kwargs["json"]) == {"textQuery", "languageCode", "maxResultCount"}
        mask = kwargs["headers"]["X-Goog-FieldMask"]
        assert "websiteUri" not in mask and "Phone" not in mask and "rating" not in mask

    def test_no_key_is_a_fatal_error(self):
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", ""):
            with pytest.raises(PlacesError) as caught:
                lookup_places("Acme")
        assert caught.value.fatal

    @pytest.mark.parametrize("status,fatal", [(403, True), (429, True), (500, False)])
    def test_http_failures(self, status, fatal):
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", "key"), \
                patch.object(company_places.httpx, "post", return_value=self.respond(status)):
            with pytest.raises(PlacesError) as caught:
                lookup_places("Acme")
        assert caught.value.fatal is fatal

    def test_network_error_is_retryable_and_never_leaks_details(self):
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", "secret-key"), \
                patch.object(company_places.httpx, "post", side_effect=httpx.ConnectError("secret-key")):
            with pytest.raises(PlacesError) as caught:
                lookup_places("Acme")
        assert not caught.value.fatal and "secret-key" not in str(caught.value)


class CityCursor:
    def __init__(self, todo, fail_insert_for=None):
        self.todo = todo
        self.fail_insert_for = fail_insert_for
        self.executed = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.executed.append((sql, params))
        self.rowcount = 0
        if sql.startswith("INSERT INTO company_city_lookups") and params[0] == self.fail_insert_for:
            raise RuntimeError("boom")

    def fetchall(self):
        return list(self.todo)

    def statements(self, prefix):
        return [(s, p) for s, p in self.executed if s.startswith(prefix)]


def resolve(cursor, lookup, **kwargs):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    with patch("gcrm.tools.db_linkedin.db") as mock_db, \
            patch("gcrm.tools.db_linkedin.log_audit"):
        mock_db.return_value.__enter__.return_value = conn
        return db_linkedin.resolve_company_cities(lookup=lookup, **kwargs)


def todo(*names, people=1):
    return [{"company_key": n.lower(), "name": n, "people": people} for n in names]


class TestResolveCompanyCities:
    def test_resolved_city_is_cached_and_applied_unresolved_is_cached_only(self):
        cursor = CityCursor(todo("Acme", "Globex"))
        answers = {"Acme": [place("Acme", "Ulm")], "Globex": []}
        counts = resolve(cursor, lambda name: answers[name])
        assert (counts["looked_up"], counts["resolved"], counts["not_found"]) == (2, 1, 1)
        assert len(cursor.statements("INSERT INTO company_city_lookups")) == 2  # both cached
        [(update, params)] = [
            (s, p) for s, p in cursor.statements("UPDATE contacts c SET city") if p is not None
        ]
        assert params == ("Ulm", "DE", "acme")
        # never overwrites a city that is already set
        assert "COALESCE(c.city, '') = ''" in update

    def test_most_connections_first_and_the_limit_caps_billed_lookups(self):
        rows = [{"company_key": "small", "name": "Small", "people": 1},
                {"company_key": "big", "name": "Big", "people": 9},
                {"company_key": "mid", "name": "Mid", "people": 4}]
        asked = []
        counts = resolve(CityCursor(rows), lambda name: asked.append(name) or [], limit=2)
        assert asked == ["Big", "Mid"] and counts["looked_up"] == 2

    def test_one_failed_lookup_is_skipped_and_the_rest_continue(self):
        def lookup(name):
            if name == "Bad":
                raise PlacesError("HTTP 500")
            return [place(name, "Ulm")]
        counts = resolve(CityCursor(todo("Bad", "Good")), lookup)
        assert (counts["errors"], counts["resolved"], counts["stopped"]) == (1, 1, "")

    def test_a_fatal_error_stops_the_run_immediately(self):
        calls = []

        def lookup(name):
            calls.append(name)
            raise PlacesError("Places API returned HTTP 403", fatal=True)
        counts = resolve(CityCursor(todo("A", "B", "C")), lookup)
        assert calls == ["A"] and "403" in counts["stopped"]

    def test_five_failures_in_a_row_stop_the_run(self):
        def lookup(name):
            raise PlacesError("HTTP 500")
        counts = resolve(CityCursor(todo(*"ABCDEFGH")), lookup)
        assert counts["errors"] == 5 and counts["stopped"]

    def test_a_success_resets_the_failure_streak(self):
        sequence = iter([PlacesError("x")] * 4 + [None] + [PlacesError("x")] * 4)

        def lookup(name):
            outcome = next(sequence)
            if outcome:
                raise outcome
            return []
        counts = resolve(CityCursor(todo(*"ABCDEFGHI")), lookup)
        assert counts["stopped"] == "" and counts["errors"] == 8

    def test_a_result_that_cannot_be_saved_is_counted_and_skipped(self):
        cursor = CityCursor(todo("Acme", "Globex"), fail_insert_for="acme")
        counts = resolve(cursor, lambda name: [place(name, "Ulm")])
        assert counts["errors"] == 1 and counts["resolved"] == 1

    def test_nothing_to_do_makes_no_lookups(self):
        lookup = MagicMock()
        counts = resolve(CityCursor([]), lookup)
        lookup.assert_not_called()
        assert counts["looked_up"] == 0


# --- review queue ------------------------------------------------------------

class QueueCursor:
    def __init__(self, rows, total=None, fail_for=None):
        self.rows = rows
        self.total = len(rows) if total is None else total
        self.fail_for = fail_for
        self.executed = []
        self.rowcount = 1
        self._one = None

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.executed.append((sql, params))
        if sql.startswith("SELECT COUNT(*)"):
            self._one = {"n": self.total}
        elif sql.startswith("UPDATE contacts c SET") and params and self.fail_for in params:
            raise RuntimeError("boom")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return [dict(r) for r in self.rows]

    def updates(self):
        return [(s, p) for s, p in self.executed if s.startswith("UPDATE contacts c SET")]


def with_db(cursor, fn):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    with patch("gcrm.tools.db_linkedin.db") as mock_db:
        mock_db.return_value.__enter__.return_value = conn
        return fn()


class TestCityReviewQueue:
    def test_distinct_offered_cities_become_choices_and_candidates_are_dropped(self):
        rows = [{"id": 1, "name": "Helios", "lookup_outcome": "ambiguous", "people_count": 3,
                 "people": [{"id": 5, "name": "Ann", "title": "CTO"}],
                 "candidates": [{"name": "Helios", "city": "Berlin", "country": "DE"},
                                {"name": "Helios", "city": "Berlin", "country": "DE"},
                                {"name": "Helios", "city": "", "country": "DE"},
                                {"name": "Helios", "city": "Wien", "country": "AT"}]}]
        queue = with_db(QueueCursor(rows, total=7), db_linkedin.get_city_review_queue)
        assert queue["total"] == 7
        [row] = queue["rows"]
        assert row["choices"] == [{"city": "Berlin", "country": "DE"}, {"city": "Wien", "country": "AT"}]
        assert "candidates" not in row

    def test_never_looked_up_organizations_have_no_choices(self):
        rows = [{"id": 2, "name": "Acme", "lookup_outcome": None, "people_count": 1,
                 "people": [], "candidates": None}]
        [row] = with_db(QueueCursor(rows), db_linkedin.get_city_review_queue)["rows"]
        assert row["choices"] == [] and row["lookup_outcome"] is None

    def test_pages_by_offset(self):
        cursor = QueueCursor([])
        with_db(cursor, lambda: db_linkedin.get_city_review_queue(3))
        select = [(s, p) for s, p in cursor.executed if "LIMIT" in s][0]
        assert select[1] == (db_linkedin.CITY_QUEUE_PAGE_SIZE, 2 * db_linkedin.CITY_QUEUE_PAGE_SIZE)


class TestApplyCityDecisions:
    def apply(self, decisions, **kwargs):
        cursor = QueueCursor([], **kwargs)
        return with_db(cursor, lambda: db_linkedin.apply_city_decisions(decisions)), cursor

    def test_typed_city_is_saved_as_manual_and_only_while_still_waiting(self):
        counts, cursor = self.apply([{"contact_id": 4, "city": " Ulm ", "country": "de"}])
        assert counts == {"saved": 1, "dismissed": 0, "failed": 0}
        [(sql, params)] = cursor.updates()
        assert params == ("Ulm", "DE", 4)
        assert "city_status = 'manual'" in sql and "city_status = 'needs_review'" in sql

    def test_country_left_blank_keeps_the_existing_one(self):
        _, cursor = self.apply([{"contact_id": 4, "city": "Ulm", "country": ""}])
        [(sql, params)] = cursor.updates()
        assert params[1] is None and "COALESCE(%s, c.country)" in sql

    def test_dismiss_stops_asking_without_touching_the_city(self):
        counts, cursor = self.apply([{"contact_id": 4, "dismiss": True}])
        assert counts["dismissed"] == 1
        [(sql, _)] = cursor.updates()
        assert "city_status = 'dismissed'" in sql and "city = " not in sql.replace("city_status", "")

    def test_bad_country_code_fails_that_row_only(self):
        counts, cursor = self.apply([
            {"contact_id": 1, "city": "Ulm", "country": "Germany"},
            {"contact_id": 2, "city": "Bonn", "country": "DE"},
        ])
        assert counts == {"saved": 1, "dismissed": 0, "failed": 1}
        assert [p[2] for _, p in cursor.updates()] == [2]

    def test_a_database_error_on_one_row_is_rolled_back_and_the_rest_apply(self):
        counts, cursor = self.apply(
            [{"contact_id": 1, "city": "Ulm", "country": ""},
             {"contact_id": 2, "city": "Bonn", "country": ""}], fail_for=1)
        assert counts["saved"] == 1 and counts["failed"] == 1
        assert any("ROLLBACK TO SAVEPOINT" in s for s, _ in cursor.executed)

    def test_blank_city_without_dismiss_does_nothing(self):
        counts, cursor = self.apply([{"contact_id": 1, "city": "  ", "country": "DE"}])
        assert counts["saved"] == 0 and cursor.updates() == []


# --- routes ------------------------------------------------------------------

QUEUE_ROW = {"id": 8, "name": "Helios Kliniken GmbH", "lookup_outcome": "ambiguous", "people_count": 2,
             "people": [{"id": 5, "name": "Ann Roth", "title": "CTO"}],
             "choices": [{"city": "Berlin", "country": "DE"}]}


@pytest.fixture
def admin_session():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


class TestCityRoutes:
    def test_page_shows_who_you_know_and_what_the_lookup_offered(self, admin_session):
        with patch("gcrm.api.routers.people.get_city_review_queue",
                   return_value={"total": 1, "rows": [QUEUE_ROW]}):
            response = admin_session.get("/people/linkedin/cities")
        assert response.status_code == 200
        assert "Helios Kliniken GmbH" in response.text and "Ann Roth" in response.text
        assert 'name="city_8"' in response.text and 'name="pick_8"' in response.text
        assert 'value="Berlin|DE"' in response.text and "several cities" in response.text

    def test_page_survives_a_failing_queue(self, admin_session):
        with patch("gcrm.api.routers.people.get_city_review_queue", side_effect=RuntimeError("x")):
            response = admin_session.get("/people/linkedin/cities")
        assert response.status_code == 200 and "could not be loaded" in response.text

    def test_empty_state(self, admin_session):
        with patch("gcrm.api.routers.people.get_city_review_queue",
                   return_value={"total": 0, "rows": []}):
            assert "has a city" in admin_session.get("/people/linkedin/cities").text

    def test_apply_turns_the_form_into_decisions(self, admin_session):
        with patch("gcrm.api.routers.people.apply_city_decisions",
                   return_value={"saved": 2, "dismissed": 1, "failed": 0}) as apply, \
             patch("gcrm.api.routers.people.log_audit"):
            response = admin_session.post("/people/linkedin/cities", data={
                "city_1": "Ulm", "country_1": "de",                  # typed
                "pick_2": "Berlin|DE", "city_2": "", "country_2": "",  # picked: country rides along
                "pick_3": "Berlin|DE", "city_3": "Köln", "country_3": "",  # typed wins, pick's country ignored
                "dismiss_4": "1", "city_4": "",                      # dismissed
                "dismiss_5": "1", "city_5": "Bonn",                  # a city beats a dismiss
                "pick_6": "", "city_6": "", "country_6": "DE",       # nothing to save
                "city_x": "Nope",                                    # not an id
            }, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/people/linkedin/cities?saved=2&dismissed=1&failed=0"
        assert apply.call_args.args[0] == [
            {"contact_id": 1, "city": "Ulm", "country": "de", "dismiss": False},
            {"contact_id": 2, "city": "Berlin", "country": "DE", "dismiss": False},
            {"contact_id": 3, "city": "Köln", "country": "", "dismiss": False},
            {"contact_id": 4, "city": "", "country": "", "dismiss": True},
            {"contact_id": 5, "city": "Bonn", "country": "", "dismiss": False},
        ]

    def test_apply_with_nothing_chosen_writes_nothing(self, admin_session):
        with patch("gcrm.api.routers.people.apply_city_decisions") as apply, \
             patch("gcrm.api.routers.people.log_audit"):
            response = admin_session.post("/people/linkedin/cities", data={"city_1": ""},
                                          follow_redirects=False)
        assert response.status_code == 303
        apply.assert_not_called()

    def test_the_people_page_links_to_the_queue(self, admin_session):
        with patch("gcrm.api.routers.people.get_people", return_value=[]):
            assert "/people/linkedin/cities" in admin_session.get("/people/").text


# --- reachable fits ----------------------------------------------------------

class ReachableCursor(QueueCursor):
    def fetchone(self):
        return {"n": self.total}


class TestReachableFits:
    def fetch(self, rows, total=None, **kwargs):
        cursor = ReachableCursor(rows, total=total)
        result = with_db(cursor, lambda: db_linkedin.get_reachable_fits(**kwargs))
        return result, cursor

    def test_only_fitting_unsuppressed_organizations_with_a_confirmed_connection(self):
        _, cursor = self.fetch([])
        select = [s for s, _ in cursor.executed if "LIMIT" in s][0]
        assert "c.pipeline_stage = 'suspect'" in select and "c.status = 'ready'" in select
        assert "c.do_not_contact = FALSE" in select and "c.deleted_at IS NULL" in select
        assert "k.is_linkedin_contact AND k.deleted_at IS NULL" in select
        assert "ORDER BY c.fit_score DESC NULLS LAST" in select

    def test_workspace_scopes_the_list_and_the_count(self):
        _, cursor = self.fetch([], workspace_id=7)
        assert all("c.workspace_id = %s" in s for s, _ in cursor.executed)
        assert all(7 in p for _, p in cursor.executed)

    def test_pages_by_offset(self):
        _, cursor = self.fetch([], page=3)
        params = [p for s, p in cursor.executed if "LIMIT" in s][0]
        assert params == [db_linkedin.REACHABLE_PAGE_SIZE, 2 * db_linkedin.REACHABLE_PAGE_SIZE]

    def test_returns_total_and_rows(self):
        result, _ = self.fetch([{"id": 1, "name": "Acme", "people": []}], total=9)
        assert result["total"] == 9 and result["rows"][0]["name"] == "Acme"


REACHABLE_ROW = {"id": 8, "name": "Helios Kliniken", "city": "Augsburg", "country": "DE", "type": "clinic",
                 "fit_score": 82, "website": None,
                 "people": [{"id": 5, "name": "Ann Roth", "title": "CTO",
                             "linkedin_url": "https://www.linkedin.com/in/ann"},
                            {"id": 6, "name": "Bob Ng", "title": None,
                             "linkedin_url": "javascript:alert(1)"}]}


class TestReachableRoute:
    def test_lists_fits_with_the_people_you_know_and_their_linkedin_links(self, admin_session):
        with patch("gcrm.api.routers.organizations.get_reachable_fits",
                   return_value={"total": 1, "rows": [REACHABLE_ROW]}):
            response = admin_session.get("/organizations/reachable")
        assert response.status_code == 200
        assert "Helios Kliniken" in response.text and "Augsburg, DE" in response.text
        assert "Ann Roth" in response.text and "CTO" in response.text
        assert 'href="https://www.linkedin.com/in/ann"' in response.text
        assert 'rel="noopener noreferrer"' in response.text

    def test_only_linkedin_urls_become_links(self, admin_session):
        with patch("gcrm.api.routers.organizations.get_reachable_fits",
                   return_value={"total": 1, "rows": [REACHABLE_ROW]}):
            response = admin_session.get("/organizations/reachable")
        assert "javascript:" not in response.text

    def test_is_not_swallowed_by_the_organization_id_route(self, admin_session):
        with patch("gcrm.api.routers.organizations.get_reachable_fits",
                   return_value={"total": 0, "rows": []}):
            assert admin_session.get("/organizations/reachable").status_code == 200

    def test_empty_state_and_failure(self, admin_session):
        with patch("gcrm.api.routers.organizations.get_reachable_fits",
                   return_value={"total": 0, "rows": []}):
            assert "No fitting organization" in admin_session.get("/organizations/reachable").text
        with patch("gcrm.api.routers.organizations.get_reachable_fits", side_effect=RuntimeError("x")):
            response = admin_session.get("/organizations/reachable")
        assert response.status_code == 200 and "could not be loaded" in response.text

    def test_the_organization_list_links_to_it(self, admin_session):
        with patch("gcrm.api.routers.organizations._fetch_organizations_page",
                   return_value=([], {}, {}, [], 0)):
            assert "/organizations/reachable" in admin_session.get("/organizations/").text
