"""LinkedIn connections: Connections.csv parsing, company matching, the import and
match-review database functions, the web routes, and the who-do-I-know-here
notice. DB is mocked — runs without Postgres."""
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.linkedin import (
    OrgIndex,
    decode_export,
    linkedin_url_hash,
    normalize_company,
    normalize_linkedin_url,
    parse_connected_on,
    parse_connections_csv,
)
from gcrm.tools import db_linkedin, db_people

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}

EXPORT = '''Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing. You will only see email addresses for connections who have chosen to allow their contacts to download or export their email addresses."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Anna,Roth,https://www.linkedin.com/in/anna-roth-123/,Anna@Acme.de,Acme GmbH,CTO,05 Mar 2024
Bernd,,https://de.linkedin.com/in/BERND/?trk=abc,,Müller & Söhne e.K.,Inhaber,5 Mär 2023
,,,,,,
Cara,Lee,,not-an-email,Self-employed,"Designer, Illustrator",garbage
'''


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


class TestParseConnectionsCsv:
    def test_skips_the_notes_preamble_and_reads_every_connection(self):
        parsed = parse_connections_csv(EXPORT)
        assert parsed.header_found
        assert [row["name"] for row in parsed.rows] == ["Anna Roth", "Bernd", "Cara Lee"]
        assert parsed.skipped == 0  # the blank line is not a skipped connection

    def test_maps_fields_and_canonicalises_url_email_and_date(self):
        anna = parse_connections_csv(EXPORT).rows[0]
        assert anna == {
            "name": "Anna Roth",
            "linkedin_url": "https://www.linkedin.com/in/anna-roth-123",
            "email": "anna@acme.de",
            "company": "Acme GmbH",
            "title": "CTO",
            "connected_on": date(2024, 3, 5),
        }

    def test_a_quoted_comma_stays_inside_its_field(self):
        assert parse_connections_csv(EXPORT).rows[2]["title"] == "Designer, Illustrator"

    def test_bad_date_and_bad_email_degrade_to_empty_not_dropped(self):
        cara = parse_connections_csv(EXPORT).rows[2]
        assert cara["connected_on"] is None
        assert cara["email"] == ""

    def test_reads_german_headers_and_semicolons(self):
        text = (
            "Vorname;Nachname;URL;E-Mail-Adresse;Unternehmen;Position;Verbunden am\n"
            "Jörg;Bauer;linkedin.com/in/jbauer;;Bauer AG;Leiter;12.01.2022\n"
        )
        parsed = parse_connections_csv(text)
        assert parsed.header_found
        assert parsed.rows[0]["name"] == "Jörg Bauer"
        assert parsed.rows[0]["company"] == "Bauer AG"
        assert parsed.rows[0]["connected_on"] == date(2022, 1, 12)

    def test_a_row_without_a_name_is_skipped_and_counted(self):
        text = "First Name,Last Name,URL\n,,https://www.linkedin.com/in/x\nAnna,Roth,\n"
        parsed = parse_connections_csv(text)
        assert parsed.skipped == 1
        assert [row["name"] for row in parsed.rows] == ["Anna Roth"]

    def test_a_short_row_does_not_break_the_rest(self):
        text = "First Name,Last Name,URL,Email Address,Company\nAnna,Roth\nBob,Ng,,,Acme\n"
        parsed = parse_connections_csv(text)
        assert [row["name"] for row in parsed.rows] == ["Anna Roth", "Bob Ng"]
        assert parsed.rows[1]["company"] == "Acme"

    def test_a_file_that_is_not_a_connections_export_is_reported(self):
        parsed = parse_connections_csv("Date,Amount\n2024-01-01,5\n")
        assert parsed.header_found is False
        assert parsed.rows == []

    def test_empty_text(self):
        assert parse_connections_csv("").header_found is False


class TestDecodeExport:
    def test_strips_a_utf8_bom(self):
        assert decode_export("﻿First Name".encode("utf-8")).startswith("First Name")

    def test_falls_back_to_windows_1252(self):
        assert decode_export("Müller".encode("cp1252")) == "Müller"


class TestParseConnectedOn:
    @pytest.mark.parametrize("text,expected", [
        ("05 Mar 2024", date(2024, 3, 5)),
        ("5 Mär. 2023", date(2023, 3, 5)),
        ("2024-03-05", date(2024, 3, 5)),
        ("05.03.2024", date(2024, 3, 5)),
        ("31 Dez 2020", date(2020, 12, 31)),
    ])
    def test_formats(self, text, expected):
        assert parse_connected_on(text) == expected

    @pytest.mark.parametrize("text", ["", None, "garbage", "31.02.2024", "5 Xyz 2024"])
    def test_unreadable_is_none(self, text):
        assert parse_connected_on(text) is None


class TestNormalizeLinkedinUrl:
    @pytest.mark.parametrize("raw", [
        "https://www.linkedin.com/in/Anna-Roth/",
        "http://de.linkedin.com/in/anna-roth?trk=x#top",
        "linkedin.com/in/anna-roth",
    ])
    def test_one_canonical_form(self, raw):
        assert normalize_linkedin_url(raw) == "https://www.linkedin.com/in/anna-roth"

    @pytest.mark.parametrize("raw", [
        "", None, "javascript:alert(1)", "https://evil.test/in/anna",
        "https://linkedin.com.evil.test/in/anna", "https://www.linkedin.com/",
    ])
    def test_anything_else_is_rejected(self, raw):
        assert normalize_linkedin_url(raw) is None


class TestNormalizeCompany:
    def test_folds_case_umlauts_punctuation_and_legal_forms(self):
        assert normalize_company("Müller & Söhne e.K.") == normalize_company("MUELLER und SOEHNE")
        assert normalize_company("Acme GmbH") == "acme"
        assert normalize_company("Acme Ltd.") == "acme"

    def test_a_name_that_is_only_a_legal_form_keeps_its_words(self):
        assert normalize_company("GmbH") == "gmbh"

    @pytest.mark.parametrize("placeholder", ["Self-employed", "Selbstständig", "Freelance", "-", ""])
    def test_placeholders_never_match(self, placeholder):
        assert normalize_company(placeholder) == ""


ORGS = [
    {"id": 1, "name": "Acme GmbH", "city": "Augsburg"},
    {"id": 2, "name": "Siemens Healthineers", "city": "Erlangen"},
    {"id": 3, "name": "Café Central", "city": "München"},
    {"id": 4, "name": "Cafe Central", "city": "Zürich"},
    {"id": 5, "name": "Hoffmann Kunst", "city": "Berlin"},
    {"id": 6, "name": "Hotel Adler", "city": "Lindau"},
]


class TestOrgIndex:
    index = OrgIndex(ORGS)

    def test_exact_unique_match(self):
        [match] = self.index.match("ACME Ltd.")
        assert (match.contact_id, match.confidence) == (1, "exact")

    def test_two_organizations_with_one_name_are_ambiguous(self):
        matches = self.index.match("Cafe Central")
        assert {m.contact_id for m in matches} == {3, 4}
        assert {m.confidence for m in matches} == {"ambiguous"}

    def test_a_shorter_name_inside_a_longer_one_is_partial(self):
        [match] = self.index.match("Siemens AG")
        assert (match.contact_id, match.confidence) == (2, "partial")

    def test_a_typo_is_fuzzy(self):
        [match] = self.index.match("Hofmann Kunst GmbH")
        assert (match.contact_id, match.confidence) == (5, "fuzzy")

    def test_a_generic_word_alone_does_not_match(self):
        assert self.index.match("Hotel") == []
        assert self.index.match("Hotel Schwan") == []  # shares only 'hotel' with Hotel Adler

    def test_unrelated_and_empty_companies_match_nothing(self):
        assert self.index.match("Nothing Like It") == []
        assert self.index.match("Self-employed") == []
        assert self.index.match(None) == []


class TestCommonWords:
    """A word found in a great many organizations identifies none of them."""

    index = OrgIndex(
        [{"id": i, "name": f"Müller Filiale{i}", "city": "x"} for i in range(150)]
        + [{"id": 1000, "name": "Siemens Healthineers", "city": "Erlangen"}]
    )

    def test_a_very_common_word_alone_suggests_nothing(self):
        assert self.index.match("Müller") == []

    def test_a_rare_word_still_matches(self):
        [match] = self.index.match("Siemens")
        assert (match.contact_id, match.confidence) == (1000, "partial")

    def test_the_exact_name_still_wins_regardless(self):
        [match] = self.index.match("Müller Filiale7")
        assert (match.contact_id, match.confidence) == (7, "exact")


class FakeCursor:
    """Answers the importer's lookups from a dict and can fail one insert."""

    def __init__(self, known_urls=None, fail_on_name=None, suppressed_hashes=()):
        self.suppressed_hashes = set(suppressed_hashes)
        self.executed = []
        self.known_urls = known_urls or {}
        self.fail_on_name = fail_on_name
        self.rowcount = 1
        self._rows = []

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self._rows = []
        if sql.strip().startswith("SELECT id FROM people WHERE lower(linkedin_url)"):
            person_id = self.known_urls.get(params[0])
            self._rows = [{"id": person_id}] if person_id else []
        elif sql.strip().startswith("SELECT 1 FROM person_import_suppressions"):
            self._rows = [{"?column?": 1}] if params[0] in self.suppressed_hashes else []
        elif sql.strip().startswith("INSERT INTO people") and params[0] == self.fail_on_name:
            raise RuntimeError("boom")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def statements(self, prefix):
        return [sql for sql, _ in self.executed if sql.startswith(prefix)]


def patched_db(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    patcher = patch("gcrm.tools.db_linkedin.db")
    mock_db = patcher.start()
    mock_db.return_value.__enter__.return_value = conn
    return patcher


def row(name, url=None, company="Acme", email=""):
    return {"name": name, "linkedin_url": url, "email": email, "company": company,
            "title": "CTO", "connected_on": date(2024, 3, 5)}


class TestImportConnections:
    def test_creates_new_and_marks_existing_people(self):
        cursor = FakeCursor(known_urls={"https://www.linkedin.com/in/anna": 7})
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([
                row("Anna Roth", "https://www.linkedin.com/in/anna"),
                row("Bob Ng", "https://www.linkedin.com/in/bob"),
            ])
        finally:
            patcher.stop()
        assert counts == {"created": 1, "updated": 1, "failed": 0, "suppressed": 0}
        [update] = cursor.statements("UPDATE people SET")
        assert "is_linkedin_contact = TRUE" in update
        # Existing values are only filled in when blank, never overwritten.
        assert "COALESCE(NULLIF(title, ''), %s)" in update
        [insert] = cursor.statements("INSERT INTO people")
        assert "'default'" in insert  # workspace falls back to the default one

    def test_one_failing_row_is_rolled_back_and_the_rest_still_import(self):
        cursor = FakeCursor(fail_on_name="Bad Row")
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([
                row("Anna Roth", "https://www.linkedin.com/in/anna"),
                row("Bad Row", "https://www.linkedin.com/in/bad"),
                row("Cy Diaz", "https://www.linkedin.com/in/cy"),
            ])
        finally:
            patcher.stop()
        assert counts == {"created": 2, "updated": 0, "failed": 1, "suppressed": 0}
        assert cursor.statements("ROLLBACK TO SAVEPOINT") == ["ROLLBACK TO SAVEPOINT linkedin_row"]
        assert len(cursor.statements("RELEASE SAVEPOINT")) == 2

    def test_a_row_without_a_url_is_matched_by_name_and_company_not_name_alone(self):
        cursor = FakeCursor()
        cursor.fetchall = lambda: [
            {"id": 1, "company_raw": "Other Corp", "company": None, "connected_on": None},
            {"id": 2, "company_raw": None, "company": "Acme GmbH", "connected_on": None},
        ]
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([row("Anna Roth", None, company="Acme")])
        finally:
            patcher.stop()
        assert counts["updated"] == 1
        [update] = [(s, p) for s, p in cursor.executed if s.startswith("UPDATE people SET")]
        assert update[1][-1] == 2  # the Acme one, not the Other Corp one

    def test_a_namesake_at_another_company_and_date_is_a_new_person(self):
        cursor = FakeCursor()
        cursor.fetchall = lambda: [
            {"id": 1, "company_raw": "Other Corp", "company": None, "connected_on": date(2020, 1, 1)},
        ]
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([row("Anna Roth", None, company="Acme")])
        finally:
            patcher.stop()
        assert counts == {"created": 1, "updated": 0, "failed": 0, "suppressed": 0}

    def test_reimporting_a_connection_with_no_url_email_or_real_company_does_not_duplicate(self):
        """Regression, found against real Postgres: "Self-employed" normalises to
        no company, so such a row used to be created again on every import."""
        cursor = FakeCursor()
        cursor.fetchall = lambda: [
            {"id": 4, "company_raw": "Self-employed", "company": None, "connected_on": None},
        ]
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([
                {**row("Cara Lee", None, company="Self-employed"), "connected_on": None},
            ])
        finally:
            patcher.stop()
        assert counts == {"created": 0, "updated": 1, "failed": 0, "suppressed": 0}

    def test_the_connected_on_date_alone_corroborates_a_name(self):
        cursor = FakeCursor()
        cursor.fetchall = lambda: [
            {"id": 4, "company_raw": None, "company": None, "connected_on": date(2024, 3, 5)},
        ]
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([row("Cara Lee", None, company="")])
        finally:
            patcher.stop()
        assert counts["updated"] == 1

    def test_a_person_deleted_earlier_is_not_brought_back(self):
        url = "https://www.linkedin.com/in/anna"
        cursor = FakeCursor(suppressed_hashes={linkedin_url_hash(url)})
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.import_connections([
                row("Anna Roth", url),
                row("Bob Ng", "https://www.linkedin.com/in/bob"),
            ])
        finally:
            patcher.stop()
        assert counts == {"created": 1, "updated": 0, "failed": 0, "suppressed": 1}
        [insert] = [(s, p) for s, p in cursor.executed if s.startswith("INSERT INTO people")]
        assert insert[1][0] == "Bob Ng"

    def test_empty_import(self):
        cursor = FakeCursor()
        patcher = patched_db(cursor)
        try:
            assert db_linkedin.import_connections([]) == {"created": 0, "updated": 0, "failed": 0, "suppressed": 0}
        finally:
            patcher.stop()


def cursor_answering(*fetchall_results, fetchone_results=()):
    cursor = MagicMock()
    cursor.fetchall.side_effect = list(fetchall_results)
    cursor.fetchone.side_effect = list(fetchone_results)
    cursor.rowcount = 1
    return cursor


class TestMatchSuggestions:
    def test_suggests_organizations_best_match_first_and_honours_rejections(self):
        people = [
            {"id": 2, "name": "Bob", "title": None, "company_raw": "Siemens AG", "linkedin_url": None},
            {"id": 1, "name": "Anna", "title": "CTO", "company_raw": "Acme GmbH", "linkedin_url": None},
            {"id": 3, "name": "Cy", "title": None, "company_raw": "Acme", "linkedin_url": None},
        ]
        orgs = [
            {"id": 10, "name": "Acme", "city": "Augsburg", "status": "cold"},
            {"id": 11, "name": "Siemens Healthineers", "city": "Erlangen", "status": "candidate"},
        ]
        rejections = [{"person_id": 3, "contact_id": 10}]
        cursor = cursor_answering(people, orgs, rejections)
        patcher = patched_db(cursor)
        try:
            suggestions = db_linkedin.get_match_suggestions()
        finally:
            patcher.stop()
        assert [s["name"] for s in suggestions] == ["Anna", "Bob"]  # exact before partial; Cy rejected
        assert suggestions[0]["matches"][0] == {
            "contact_id": 10, "name": "Acme", "city": "Augsburg",
            "confidence": "exact", "status": "cold",
        }
        assert suggestions[1]["matches"][0]["confidence"] == "partial"

    def test_no_unlinked_people_means_no_further_queries(self):
        cursor = cursor_answering([])
        patcher = patched_db(cursor)
        try:
            assert db_linkedin.get_match_suggestions() == []
        finally:
            patcher.stop()
        assert cursor.execute.call_count == 1


class TestSoftDeletedPeople:
    def test_deleted_people_never_reach_suggestions_or_the_walk_in_notice(self):
        cursor = cursor_answering([], [], [], fetchone_results=[{"id": 10, "name": "Acme", "city": "A"}])
        patcher = patched_db(cursor)
        try:
            db_linkedin.get_match_suggestions()
            db_linkedin.get_linkedin_connections_for_org(10)
        finally:
            patcher.stop()
        people_queries = [
            " ".join(call.args[0].split()) for call in cursor.execute.call_args_list
            if "FROM people" in call.args[0]
        ]
        assert len(people_queries) == 3
        assert all("deleted_at IS NULL" in sql for sql in people_queries)


class TestApplyMatchDecisions:
    def test_links_and_remembers_rejections(self):
        cursor = MagicMock()
        cursor.rowcount = 1
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.apply_match_decisions([
                {"person_id": 1, "contact_id": 10, "rejected": []},
                {"person_id": 2, "contact_id": None, "rejected": [11, 12]},
            ])
        finally:
            patcher.stop()
        assert counts == {"linked": 1, "rejected": 2, "failed": 0}
        sql = [" ".join(call.args[0].split()) for call in cursor.execute.call_args_list]
        assert any(s.startswith("UPDATE people SET contact_id") and "is_linkedin_contact" in s for s in sql)
        assert sum(s.startswith("INSERT INTO person_match_rejections") for s in sql) == 2

    def test_a_failing_decision_does_not_stop_the_next(self):
        cursor = MagicMock()
        cursor.rowcount = 1

        def execute(sql, params=None):
            if sql.strip().startswith("UPDATE people SET contact_id") and params[1] == 1:
                raise RuntimeError("boom")

        cursor.execute.side_effect = execute
        patcher = patched_db(cursor)
        try:
            counts = db_linkedin.apply_match_decisions([
                {"person_id": 1, "contact_id": 10, "rejected": []},
                {"person_id": 2, "contact_id": 11, "rejected": []},
            ])
        finally:
            patcher.stop()
        assert counts == {"linked": 1, "rejected": 0, "failed": 1}


class TestConnectionsForOrg:
    def test_returns_confirmed_and_possible_and_skips_unrelated_companies(self):
        linked = [{"id": 1, "name": "Anna", "title": "CTO", "linkedin_url": "u", "connected_on": date(2024, 3, 5)}]
        unlinked = [
            {"id": 2, "name": "Bob", "title": None, "linkedin_url": None, "connected_on": None,
             "company_raw": "Acme Ltd"},
            {"id": 3, "name": "Cy", "title": None, "linkedin_url": None, "connected_on": None,
             "company_raw": "Elsewhere AG"},
        ]
        cursor = cursor_answering(linked, unlinked, fetchone_results=[{"id": 10, "name": "Acme GmbH", "city": "A"}])
        patcher = patched_db(cursor)
        try:
            result = db_linkedin.get_linkedin_connections_for_org(10)
        finally:
            patcher.stop()
        assert [p["name"] for p in result["linked"]] == ["Anna"]
        assert result["linked"][0]["connected_on"] == "2024-03-05"  # JSON-safe
        assert [p["name"] for p in result["possible"]] == ["Bob"]

    def test_a_missing_organization_has_no_possible_connections(self):
        cursor = cursor_answering([], fetchone_results=[None])
        patcher = patched_db(cursor)
        try:
            assert db_linkedin.get_linkedin_connections_for_org(99) == {"linked": [], "possible": []}
        finally:
            patcher.stop()


def people_conn(rows=None):
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


class TestDbPeopleLinkedin:
    def test_filter_all_connections(self):
        conn, cur = people_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7, linkedin="1")
        sql, params = cur.execute.call_args.args
        assert sql.split("WHERE", 2)[-1].lstrip().startswith("person.is_linkedin_contact")
        assert params == [7, 7]

    def test_filter_unlinked_connections(self):
        conn, cur = people_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7, linkedin="unlinked")
        sql, _ = cur.execute.call_args.args
        assert "person.is_linkedin_contact AND person.contact_id IS NULL" in sql

    def test_unknown_filter_value_is_ignored(self):
        conn, cur = people_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7, linkedin="'; DROP TABLE people;--")
        sql, _ = cur.execute.call_args.args
        assert "is_linkedin_contact" not in sql and "DROP" not in sql

    def test_sort_by_connected_on(self):
        conn, cur = people_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(sort="connected_on", dir="desc")
        assert "ORDER BY person.connected_on DESC NULLS LAST" in cur.execute.call_args.args[0]

    def test_update_writes_the_flag_as_a_boolean_and_canonicalises_the_url(self):
        conn, cur = people_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            ok = db_people.update_person(3, {
                "name": "Anna", "linkedin_url": "linkedin.com/in/Anna/", "is_linkedin_contact": "1",
            })
        assert ok
        sql, params = cur.execute.call_args.args
        assert "is_linkedin_contact = %s" in sql and "linkedin_url = %s" in sql
        assert True in params and "https://www.linkedin.com/in/anna" in params

    def test_update_can_clear_the_flag_and_the_url(self):
        conn, cur = people_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.update_person(3, {"name": "Anna", "linkedin_url": "  ", "is_linkedin_contact": False})
        params = cur.execute.call_args.args[1]
        assert False in params and None in params

    def test_update_rejects_a_url_that_is_not_linkedin_before_touching_the_db(self):
        with patch("gcrm.tools.db_people.db") as mock_db:
            with pytest.raises(ValueError):
                db_people.update_person(3, {"linkedin_url": "https://evil.test/in/anna"})
        mock_db.assert_not_called()


CSV_BYTES = EXPORT.encode("utf-8")


class TestImportRoutes:
    def test_form_renders(self, admin_web):
        response = client.get("/people/import/linkedin")
        assert response.status_code == 200
        assert 'action="/people/import/linkedin"' in response.text
        assert 'enctype="multipart/form-data"' in response.text

    def test_import_requires_login(self):
        response = client.post(
            "/people/import/linkedin", files={"connections": ("c.csv", CSV_BYTES, "text/csv")},
            follow_redirects=False,
        )
        assert response.status_code == 307

    def test_import_parses_the_export_and_reports_counts(self, admin_web):
        with patch("gcrm.api.routers.people.import_connections",
                   return_value={"created": 2, "updated": 1, "failed": 0, "suppressed": 0}) as mimport, \
             patch("gcrm.api.routers.people.log_audit") as maudit:
            response = client.post(
                "/people/import/linkedin", files={"connections": ("c.csv", CSV_BYTES, "text/csv")},
            )
        assert response.status_code == 200
        assert "Import finished" in response.text
        assert "New people: 2" in response.text
        assert [r["name"] for r in mimport.call_args.args[0]] == ["Anna Roth", "Bernd", "Cara Lee"]
        assert "created:2 updated:1" in maudit.call_args.args[4]

    def test_a_file_that_is_not_an_export_is_rejected_without_importing(self, admin_web):
        with patch("gcrm.api.routers.people.import_connections") as mimport:
            response = client.post(
                "/people/import/linkedin", files={"connections": ("c.csv", b"Date,Amount\n1,2\n", "text/csv")},
            )
        assert response.status_code == 400
        assert "does not look like LinkedIn" in response.text
        mimport.assert_not_called()

    def test_an_empty_file_is_rejected(self, admin_web):
        with patch("gcrm.api.routers.people.import_connections") as mimport:
            response = client.post(
                "/people/import/linkedin", files={"connections": ("c.csv", b"", "text/csv")},
            )
        assert response.status_code == 400
        mimport.assert_not_called()

    def test_a_database_failure_is_shown_not_a_stack_trace(self, admin_web):
        with patch("gcrm.api.routers.people.import_connections", side_effect=RuntimeError("db down")):
            response = client.post(
                "/people/import/linkedin", files={"connections": ("c.csv", CSV_BYTES, "text/csv")},
            )
        assert response.status_code == 500
        assert "nothing was saved" in response.text
        assert "db down" not in response.text


SUGGESTION = {
    "id": 1, "name": "Anna Roth", "title": "CTO", "company_raw": "Acme GmbH", "linkedin_url": None,
    "matches": [
        {"contact_id": 10, "name": "Acme", "city": "Augsburg", "confidence": "exact", "status": "cold"},
        {"contact_id": 11, "name": "Acme Tools", "city": "Ulm", "confidence": "partial", "status": "cold"},
    ],
}


class TestMatchRoutes:
    def test_page_lists_suggestions_with_the_exact_match_preselected(self, admin_web):
        with patch("gcrm.api.routers.people.get_match_suggestions", return_value=[SUGGESTION]):
            response = client.get("/people/linkedin/matches")
        assert response.status_code == 200
        assert 'name="person_1"' in response.text
        assert 'name="cands_1" value="10,11"' in response.text
        assert "Acme (Augsburg)" in response.text
        assert 'value="10" selected' in response.text
        assert 'value="11" selected' not in response.text

    def test_page_survives_a_failing_lookup(self, admin_web):
        with patch("gcrm.api.routers.people.get_match_suggestions", side_effect=RuntimeError("boom")):
            response = client.get("/people/linkedin/matches")
        assert response.status_code == 200
        assert "Could not load the suggestions" in response.text

    def test_empty_state(self, admin_web):
        with patch("gcrm.api.routers.people.get_match_suggestions", return_value=[]):
            response = client.get("/people/linkedin/matches")
        assert "Nothing to match" in response.text

    def test_page_is_paginated(self, admin_web):
        many = [{**SUGGESTION, "id": i, "name": f"Person {i}"} for i in range(1, 251)]
        with patch("gcrm.api.routers.people.get_match_suggestions", return_value=many):
            first = client.get("/people/linkedin/matches")
            last = client.get("/people/linkedin/matches?page=3")
            beyond = client.get("/people/linkedin/matches?page=99")
        assert "250 to review" in first.text
        assert 'name="person_1"' in first.text and 'name="person_100"' in first.text
        assert 'name="person_101"' not in first.text
        assert 'href="?page=2"' in first.text and "Page 1 of 3" in first.text
        assert 'name="person_250"' in last.text and 'name="person_200"' not in last.text
        assert 'href="?page=2"' in last.text and 'href="?page=4"' not in last.text
        assert "Page 3 of 3" in beyond.text  # out-of-range clamps to the last page

    def test_apply_turns_form_choices_into_decisions(self, admin_web):
        with patch("gcrm.api.routers.people.apply_match_decisions",
                   return_value={"linked": 1, "rejected": 2, "failed": 0}) as mapply, \
             patch("gcrm.api.routers.people.log_audit"):
            response = client.post(
                "/people/linkedin/matches",
                data={
                    "person_1": "10", "cands_1": "10,11",      # link to an offered organization
                    "person_2": "none", "cands_2": "12,13",    # reject everything offered
                    "person_3": "99", "cands_3": "5",          # not offered: forged, ignored
                    "person_4": "", "cands_4": "7",            # decide later: no decision
                    "person_x": "10", "cands_x": "10",         # not a person id: ignored
                },
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/people/linkedin/matches?linked=1&rejected=2"
        assert mapply.call_args.args[0] == [
            {"person_id": 1, "contact_id": 10, "rejected": []},
            {"person_id": 2, "contact_id": None, "rejected": [12, 13]},
        ]

    def test_apply_with_nothing_chosen_writes_nothing(self, admin_web):
        with patch("gcrm.api.routers.people.apply_match_decisions") as mapply, \
             patch("gcrm.api.routers.people.log_audit"):
            response = client.post(
                "/people/linkedin/matches", data={"person_1": "", "cands_1": "10"}, follow_redirects=False,
            )
        assert response.status_code == 303
        mapply.assert_not_called()

    def test_apply_requires_login(self):
        response = client.post("/people/linkedin/matches", data={}, follow_redirects=False)
        assert response.status_code == 307


PERSON_ROW = {
    "id": 3, "name": "Anna Roth", "title": "CTO", "email": None, "phone": None, "website": None,
    "city": None, "country": None, "relationship": None, "notes": None, "met_at": None,
    "contact_id": None, "company": None, "source": "linkedin_import",
    "created_at": "2026-08-19T10:00:00+00:00", "distance_km": None,
    "is_linkedin_contact": True, "linkedin_url": "https://www.linkedin.com/in/anna-roth",
    "connected_on": "2024-03-05", "company_raw": "Acme GmbH",
}


class TestPersonPages:
    def test_detail_shows_the_linkedin_fields(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.get_person_interactions", return_value=[]):
            response = client.get("/people/3")
        assert response.status_code == 200
        assert 'name="linkedin_url" value="https://www.linkedin.com/in/anna-roth"' in response.text
        assert 'name="is_linkedin_contact" value="1"' in response.text
        assert "checked" in response.text.split('name="is_linkedin_contact"')[1].split(">")[0]
        assert 'href="https://www.linkedin.com/in/anna-roth" target="_blank" rel="noopener noreferrer"' in response.text
        assert "2024-03-05" in response.text
        assert "Acme GmbH" in response.text and "not linked to an organization" in response.text

    def test_detail_never_links_an_unsafe_stored_url(self, admin_web):
        person = {**PERSON_ROW, "linkedin_url": "javascript:alert(1)"}
        with patch("gcrm.api.routers.people.get_person", return_value=person), \
             patch("gcrm.api.routers.people.get_person_interactions", return_value=[]):
            response = client.get("/people/3")
        assert 'href="javascript:' not in response.text

    def test_detail_of_an_ordinary_person_has_no_linkedin_badge_or_meta(self, admin_web):
        person = {**PERSON_ROW, "is_linkedin_contact": False, "linkedin_url": None, "company_raw": None}
        with patch("gcrm.api.routers.people.get_person", return_value=person), \
             patch("gcrm.api.routers.people.get_person_interactions", return_value=[]):
            response = client.get("/people/3")
        assert "linkedin-badge" not in response.text
        assert "Company on LinkedIn" not in response.text

    def test_edit_passes_the_linkedin_fields_through(self, admin_web):
        with patch("gcrm.api.routers.people.update_person", return_value=True) as update, \
             patch("gcrm.api.routers.people.log_audit"):
            response = client.post(
                "/people/3/edit",
                data={"name": "Anna", "linkedin_url": "linkedin.com/in/anna", "is_linkedin_contact": "1"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        values = update.call_args.args[1]
        assert values["linkedin_url"] == "linkedin.com/in/anna"
        assert values["is_linkedin_contact"] is True

    def test_edit_without_the_checkbox_unmarks_the_person(self, admin_web):
        with patch("gcrm.api.routers.people.update_person", return_value=True) as update, \
             patch("gcrm.api.routers.people.log_audit"):
            client.post("/people/3/edit", data={"name": "Anna"}, follow_redirects=False)
        assert update.call_args.args[1]["is_linkedin_contact"] is False

    def test_edit_with_a_non_linkedin_url_is_a_400(self, admin_web):
        with patch("gcrm.api.routers.people.update_person", side_effect=ValueError("nope")):
            response = client.post(
                "/people/3/edit", data={"name": "Anna", "linkedin_url": "https://evil.test/x"},
                follow_redirects=False,
            )
        assert response.status_code == 400

    def test_list_passes_the_linkedin_filter(self, admin_web):
        with patch("gcrm.api.routers.people.get_people", return_value=[]) as mget:
            response = client.get("/people/?linkedin=unlinked")
        assert response.status_code == 200
        assert mget.call_args.args[6] == "unlinked"
        assert 'value="unlinked" selected' in response.text

    def test_list_marks_linkedin_people(self, admin_web):
        listed = {**PERSON_ROW, "company_pipeline_stage": None, "company_opportunity_score": None,
                  "company_personal_priority": None, "value_rating": None, "last_contact": None}
        with patch("gcrm.api.routers.people.get_people", return_value=[listed]):
            response = client.get("/people/")
        assert "linkedin-badge" in response.text


ORG_ROW = {
    "id": 1, "name": "Acme GmbH", "city": "Augsburg", "country": "DE", "type": "Handwerksbetrieb",
    "status": "candidate", "pipeline_stage": "candidate", "email": None, "website": None,
    "fit_score": None, "notes": None, "flagged": False, "starred": False, "personal_priority": None,
    "last_contact": None, "address": None, "phone": None, "source": None, "maps_uri": None,
    "distance_km": None, "created_at": "2026-08-19T10:00:00+00:00", "decision_maker": None,
    "preferred_contact_method": None, "best_visit_time": None, "visit_duration": None,
    "last_visited_at": None, "first_impression": None, "last_impression": None,
    "materials_left": None, "followup_promised": None, "space_notes": None,
    "access_notes": None, "price_sensitivity": None,
}


def organization_page(row):
    cur = MagicMock()
    cur.fetchone.side_effect = [row, None]
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def get_organization_page(connections=None, error=None):
    lookup = patch(
        "gcrm.api.routers.organizations.get_linkedin_connections_for_org",
        return_value=connections, side_effect=error,
    )
    with patch("gcrm.api.routers.organizations.db") as mock_db, lookup:
        mock_db.return_value.__enter__.return_value = organization_page(ORG_ROW)
        return client.get("/organizations/1")


class TestWalkInNotice:
    """The point of the whole feature: opening an organization tells you whether
    you already know someone there."""

    def test_names_the_confirmed_connections(self, admin_web):
        response = get_organization_page({
            "linked": [{"id": 3, "name": "Anna Roth", "title": "CTO",
                        "linkedin_url": "https://www.linkedin.com/in/anna-roth", "connected_on": None}],
            "possible": [],
        })
        assert response.status_code == 200
        assert "You know someone here on LinkedIn" in response.text
        assert 'href="/people/3">Anna Roth</a>' in response.text
        assert 'href="https://www.linkedin.com/in/anna-roth"' in response.text
        assert "Possible LinkedIn connections" not in response.text

    def test_unconfirmed_lookalikes_are_labelled_as_such(self, admin_web):
        response = get_organization_page({
            "linked": [],
            "possible": [{"id": 4, "name": "Bob Ng", "title": None, "linkedin_url": None,
                          "connected_on": None, "company_raw": "Acme Ltd"}],
        })
        assert "Possible LinkedIn connections" in response.text
        assert "unconfirmed" in response.text
        assert "Company on LinkedIn: Acme Ltd" in response.text
        assert "You know someone here on LinkedIn" not in response.text

    def test_no_connections_means_no_notice(self, admin_web):
        response = get_organization_page({"linked": [], "possible": []})
        assert response.status_code == 200
        assert 'class="linkedin-notice"' not in response.text

    def test_a_failing_lookup_does_not_break_the_page(self, admin_web):
        response = get_organization_page(error=RuntimeError("db down"))
        assert response.status_code == 200
        assert 'class="linkedin-notice"' not in response.text

    def test_german(self, admin_web):
        lookup = {"linked": [{"id": 3, "name": "Anna Roth", "title": None, "linkedin_url": None,
                              "connected_on": None}], "possible": []}
        with patch("gcrm.api.routers.organizations.db") as mock_db, \
             patch("gcrm.api.routers.organizations.get_linkedin_connections_for_org", return_value=lookup):
            mock_db.return_value.__enter__.return_value = organization_page(ORG_ROW)
            response = client.get("/organizations/1?lang=de")
        assert "Hier gibt es LinkedIn-Kontakte" in response.text
        client.get("/login?lang=en")  # leave the shared session in English


class TestMobileApi:
    def test_organization_detail_carries_the_connections(self):
        from gcrm.api.routers import api_organizations

        connections = {"linked": [{"id": 3, "name": "Anna Roth"}], "possible": []}
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchone.return_value = {**ORG_ROW, "created_at": datetime(2026, 8, 19, 10, 0)}
        cur.fetchall.return_value = []
        with patch.object(api_organizations, "db") as mock_db, \
             patch.object(api_organizations, "get_latest_opportunity_analysis", return_value=None), \
             patch.object(api_organizations, "get_linkedin_connections_for_org", return_value=connections):
            mock_db.return_value.__enter__.return_value = conn
            response = client.get("/api/contacts/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["linkedin_connections"] == connections

    def test_a_failing_lookup_degrades_to_no_connections(self):
        from gcrm.api.routers import api_organizations

        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchone.return_value = {**ORG_ROW, "created_at": datetime(2026, 8, 19, 10, 0)}
        cur.fetchall.return_value = []
        with patch.object(api_organizations, "db") as mock_db, \
             patch.object(api_organizations, "get_latest_opportunity_analysis", return_value=None), \
             patch.object(api_organizations, "get_linkedin_connections_for_org", side_effect=RuntimeError("x")):
            mock_db.return_value.__enter__.return_value = conn
            response = client.get("/api/contacts/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["linkedin_connections"] == {"linked": [], "possible": []}


class TestLinkedinUrlHash:
    def test_one_hash_for_every_spelling_of_a_profile(self):
        assert linkedin_url_hash("https://www.linkedin.com/in/Anna/") == linkedin_url_hash("linkedin.com/in/anna")

    def test_it_is_a_sha256_not_the_url(self):
        digest = linkedin_url_hash("https://www.linkedin.com/in/anna")
        assert len(digest) == 64 and "anna" not in digest

    def test_nothing_to_hash(self):
        assert linkedin_url_hash("") is None and linkedin_url_hash(None) is None


class TestOrganizationsListFilter:
    """Combined with the status filter this answers "which cold organizations can
    I reach through someone I know?"."""

    def test_filter_only_keeps_organizations_with_a_live_linkedin_connection(self):
        from gcrm.api.routers.organizations import _build_organization_filters

        where, params = _build_organization_filters("", "", "", "", linkedin="1")
        assert "EXISTS (SELECT 1 FROM people lp WHERE lp.contact_id = c.id" in where
        assert "lp.is_linkedin_contact AND lp.deleted_at IS NULL" in where
        assert params == []

    @pytest.mark.parametrize("value", ["", "0", "x", "1; DROP TABLE contacts"])
    def test_anything_else_adds_no_condition(self, value):
        from gcrm.api.routers.organizations import _build_organization_filters

        where, _ = _build_organization_filters("", "", "", "", linkedin=value)
        assert "people" not in where

    def test_it_combines_with_the_other_filters(self):
        from gcrm.api.routers.organizations import _build_organization_filters

        where, params = _build_organization_filters("ready", "", "", "", linkedin="1", stage="suspect")
        assert "c.status = %s" in where and "c.pipeline_stage = %s" in where and "EXISTS" in where
        assert params == ["ready", "suspect"]

    def _list(self, query=""):
        org = {**ORG_ROW, "linkedin_connection_count": 2, "do_not_contact": False, "email_bounced": False,
               "research_exhausted": False, "created_at": datetime(2026, 8, 19, 10, 0)}
        other = {**org, "id": 2, "name": "Nobody Known", "linkedin_connection_count": 0}
        with patch("gcrm.api.routers.organizations._fetch_organizations_page",
                   return_value=([org, other], {}, {}, [], 2)) as fetch:
            return client.get(f"/organizations/{query}"), fetch

    def test_list_marks_organizations_where_you_know_someone(self, admin_web):
        response, _ = self._list()
        assert response.status_code == 200
        assert response.text.count("linkedin-badge") == 1  # only the one with connections
        assert ">in 2<" in response.text

    def test_list_passes_the_filter_and_keeps_it_across_sorting_and_paging(self, admin_web):
        response, fetch = self._list("?linkedin=1&stage=suspect&status=ready")
        assert 'value="1" selected' in response.text
        assert "linkedin=1" in response.text.split("sort=")[1]  # header sort links carry it
        assert "EXISTS" in fetch.call_args.args[0]  # the WHERE clause built for the query


class TestMobileListCount:
    def test_the_count_ignores_deleted_people_like_the_web_list_and_the_notice(self):
        """Regression, found against real Postgres: the mobile count once included
        soft-deleted people, so it disagreed with the web list."""
        from gcrm.api.routers import api_organizations

        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchall.return_value = []
        with patch.object(api_organizations, "db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            response = client.get("/api/contacts", headers=AUTH)
        assert response.status_code == 200
        sql = " ".join(cur.execute.call_args.args[0].split())
        assert "linkedin_connection_count" in sql
        assert "lp.is_linkedin_contact AND lp.deleted_at IS NULL" in sql
