"""City resolution for LinkedIn-created organizations: the pure decision rule,
the Places request, and the resolver's caching and failure handling. DB and
network are mocked — runs without Postgres or a Google key."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

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
