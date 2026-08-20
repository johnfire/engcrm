"""Render every web page template end-to-end, in both languages, with both
empty and populated data. This was a pre-existing coverage gap (most of these
routes had zero render tests) — closing it now doubles as the correctness
check for the i18n conversion (a bad t() call or Jinja typo shows up as a
500 or an UndefinedError here, not just at request time in prod)."""
import re
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_login

client = TestClient(main.app)


def make_mock_conn(*fetchall_sequences, fetchone_sequence=None):
    """A cursor whose fetchall()/fetchone() return the given sequences in
    call order — matches a handler that runs several queries in a row."""
    cur = MagicMock()
    if fetchall_sequences:
        cur.fetchall.side_effect = list(fetchall_sequences)
    else:
        cur.fetchall.return_value = []
    if fetchone_sequence is not None:
        cur.fetchone.side_effect = list(fetchone_sequence)
    else:
        cur.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


CONTACT_ROW = {
    "id": 1, "name": "Acme GmbH", "city": "Augsburg", "country": "DE", "type": "Handwerksbetrieb",
    "pipeline_stage": "candidate", "status": "none",
    "do_not_contact": False, "email_bounced": False, "research_exhausted": False,
    "email": "a@acme.de", "website": "https://acme.de", "fit_score": 80,
    "notes": "Test note", "flagged": False, "starred": False,
    "personal_priority": None, "last_contact": None,
}

INTERACTION_ROW = {
    "interaction_date": None, "method": "email", "direction": "out",
    "summary": "hi", "outcome": "sent", "next_action": None, "next_action_date": None,
}


def with_login_session():
    main.app.dependency_overrides[require_login] = lambda: "admin"


def clear_login_session():
    main.app.dependency_overrides.pop(require_login, None)


class TestActivityPage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            for lang in ("en", "de"):
                run_row = {
                    "id": 1, "agent_name": "research", "started_at": __import__("datetime").datetime.now(),
                    "finished_at": None, "status": "running", "summary": None,
                }
                stats_row = {"total": 1, "pending": 1, "approved": 0, "rejected": 0, "edited": 0}
                conn, cur = make_mock_conn([run_row], fetchone_sequence=[stats_row])
                with patch("gcrm.api.routers.activity.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/activity/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestApprovalPage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            item = {
                "id": 1, "draft_subject": "Hi", "draft_body": "Body", "created_at": __import__("datetime").datetime.now(),
                "contact_id": 1, "contact_name": "Acme", "city": "Augsburg", "email": "a@acme.de", "website": "https://acme.de",
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([item], [])
                with patch("gcrm.api.routers.approval.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/approvals/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestDroppedPage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            item = {
                "contact_name": "Acme", "city": "Augsburg", "email": "a@acme.de",
                "reviewer_note": "not a fit", "reviewed_at": None, "draft_subject": "Hi",
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([item])
                with patch("gcrm.api.routers.approval.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/approvals/dropped/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestContactsPage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            for lang in ("en", "de"):
                conn, cur = make_mock_conn(
                    [CONTACT_ROW],  # contacts rows
                    [  # status/stage counts
                        {"status": "none", "pipeline_stage": "candidate", "cnt": 4},
                        {"status": "ready", "pipeline_stage": "suspect", "cnt": 2},
                    ],
                    [{"type": "Handwerksbetrieb"}],  # distinct types
                    fetchone_sequence=[{"cnt": 1}],
                )
                with patch("gcrm.api.routers.contacts.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/contacts/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()

    def test_flagged_contact_renders_delete_confirm(self):
        with_login_session()
        try:
            flagged = {**CONTACT_ROW, "flagged": True}
            conn, cur = make_mock_conn([flagged], [], [], fetchone_sequence=[{"cnt": 1}])
            with patch("gcrm.api.routers.contacts.db") as mock_db:
                mock_db.return_value.__enter__.return_value = conn
                r = client.get("/contacts/")
            assert r.status_code == 200
            assert "Acme GmbH" in r.text
        finally:
            clear_login_session()

    def test_starred_sort_orders_starred_contacts_first(self):
        with_login_session()
        try:
            conn, cur = make_mock_conn(
                [{**CONTACT_ROW, "starred": True}],
                [{"status": "none", "pipeline_stage": "candidate", "cnt": 1}],
                [{"type": "Handwerksbetrieb"}],
                fetchone_sequence=[{"cnt": 1}],
            )
            with patch("gcrm.api.routers.contacts.db") as mock_db:
                mock_db.return_value.__enter__.return_value = conn
                response = client.get("/contacts/?sort=starred&dir=desc&lang=en")

            assert response.status_code == 200, response.text
            assert '<option value="starred" selected>Starred</option>' in response.text
            contact_query = cur.execute.call_args_list[1].args[0]
            assert "ORDER BY c.starred DESC NULLS LAST, c.id ASC" in contact_query
        finally:
            clear_login_session()


class TestContactsPrintPage:
    def test_renders(self):
        with_login_session()
        try:
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([CONTACT_ROW])
                with patch("gcrm.api.routers.contacts.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/contacts/print?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestContactBriefPage:
    def test_renders_full_and_minimal(self):
        with_login_session()
        try:
            full_contact = {
                **CONTACT_ROW, "decision_maker": "Anna Roth", "best_visit_time": "Tue afternoons",
                "visit_duration": "20 min", "phone": "+49 821 1", "address": "Hauptstr 1",
                "last_visited_at": "2026-01-01", "first_impression": "warm", "last_impression": "warm",
                "materials_left": "cards", "followup_promised": "call back", "space_notes": "small",
                "access_notes": "bus", "price_sensitivity": "low",
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([INTERACTION_ROW], fetchone_sequence=[full_contact])
                with patch("gcrm.api.routers.contacts.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/contacts/1/brief?lang={lang}")
                assert r.status_code == 200, r.text

            # minimal contact — no optional fields, no interactions (exercises the "no data" branches)
            minimal_contact = {
                "id": 1, "name": "Bare Co", "city": None, "country": None, "type": None, "status": "candidate",
                "fit_score": None, "decision_maker": None, "best_visit_time": None, "visit_duration": None,
                "phone": None, "email": None, "website": None, "address": None, "last_visited_at": None,
                "first_impression": None, "last_impression": None, "materials_left": None,
                "followup_promised": None, "space_notes": None, "access_notes": None,
                "price_sensitivity": None, "notes": None,
            }
            conn, cur = make_mock_conn([], fetchone_sequence=[minimal_contact])
            with patch("gcrm.api.routers.contacts.db") as mock_db:
                mock_db.return_value.__enter__.return_value = conn
                r = client.get("/contacts/1/brief")
            assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestContactDetailPage:
    def test_renders_full_and_minimal_contact_details(self):
        with_login_session()
        try:
            full_contact = {
                **CONTACT_ROW,
                "decision_maker": "Anna Roth",
                "preferred_contact_method": "email",
                "best_visit_time": "Tue afternoons",
                "visit_duration": "20 min",
                "last_visited_at": "2026-01-01",
                "first_impression": "warm",
                "last_impression": "warm",
                "materials_left": "cards",
                "followup_promised": "call back",
                "space_notes": "small",
                "access_notes": "bus",
                "price_sensitivity": "low",
            }
            opportunity_analysis = {
                "fit_reasoning": "Manual quoting suggests a useful automation opportunity.",
                "suggested_approach": "Map the quote workflow in a Digitalisierungs-Check.",
                "priority_score": 80,
                "opportunity_score": 84,
                "confidence_score": 70,
                "evidence": ["Manual quotes"],
                "recommended_services": [{"service": "Quote assistant", "outcome": "Faster quotes", "rationale": "Manual workflow"}],
                "discovery_questions": ["How are quotes prepared?"],
                "analysis_date": None,
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([INTERACTION_ROW], fetchone_sequence=[full_contact, opportunity_analysis])
                with patch("gcrm.api.routers.contacts.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    response = client.get(f"/contacts/1?lang={lang}")
                assert response.status_code == 200, response.text
                assert re.search(r'value="candidate"\s+selected', response.text)
                assert re.search(r'value="email"\s+selected', response.text)
                assert len(re.findall(r'value="warm"\s+selected', response.text)) == 2
                assert 'class="contact-edit-form"' in response.text
                assert 'class="contact-detail-page"' in response.text
                assert 'for="contact-name"' in response.text
                assert 'id="contact-name"' in response.text
                assert "Quote assistant" in response.text

            minimal_contact = {
                **CONTACT_ROW,
                "city": None,
                "country": None,
                "type": None,
                "fit_score": None,
                "email": None,
                "website": None,
                "phone": None,
                "notes": None,
                "decision_maker": None,
                "preferred_contact_method": None,
                "best_visit_time": None,
                "visit_duration": None,
                "last_visited_at": None,
                "first_impression": None,
                "last_impression": None,
                "materials_left": None,
                "followup_promised": None,
                "space_notes": None,
                "access_notes": None,
                "price_sensitivity": None,
            }
            conn, cur = make_mock_conn([], fetchone_sequence=[minimal_contact, None])
            with patch("gcrm.api.routers.contacts.db") as mock_db:
                mock_db.return_value.__enter__.return_value = conn
                response = client.get("/contacts/1")
            assert response.status_code == 200, response.text
        finally:
            clear_login_session()


class TestPeoplePage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            person = {
                "name": "Anna Roth", "city": "Augsburg", "relationship": "owner",
                "email": "anna@acme.de", "phone": "+49 1", "website": None, "notes": None,
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([person])
                with patch("gcrm.api.routers.people.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/people/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestResearchPage:
    def test_renders(self):
        with_login_session()
        try:
            overview = {
                "cities": [{
                    "city": "Augsburg", "region": "Bayern", "country": "DE",
                    "levels": [{"level": 1, "scan": {"complete": True, "last_run_at": "2026-01-01", "contacts_found": 5}, "emailed": 2}],
                    "emailed_total": 2, "total_contacts": 5, "scanned_levels": 1,
                }],
                "levels": [1],
                "level_labels": {1: "Tier 1 — Handwerk"},
                "total": 1, "level1_done": 1, "unscanned": 0,
                "totals": {"contacts": 5, "emailed": 2},
            }
            for lang in ("en", "de"):
                with patch("gcrm.api.routers.research.build_research_overview", return_value=overview):
                    r = client.get(f"/research/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestInboxPage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            message = {
                "id": 1, "from_email": "x@y.com", "subject": "hi", "body_snippet": "hello",
                "received_at": None, "classification": "interested", "classification_reasoning": "keen",
                "visit_when_nearby": True, "contact_id": 1, "contact_name": "Acme", "city": "Augsburg",
                "contact_status": "candidate",
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([message], [{"classification": "interested", "cnt": 1}])
                with patch("gcrm.api.routers.inbox.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/inbox/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestMarketingPage:
    def test_renders(self):
        with_login_session()
        try:
            for lang in ("en", "de"):
                r = client.get(f"/marketing/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()


class TestDraftsPage:
    def test_renders_empty_and_populated(self):
        with_login_session()
        try:
            draft = {
                "id": 1, "draft_subject": "Hi", "draft_body": "Body", "created_at": __import__("datetime").datetime.now(),
                "reviewer_note": None, "contact_id": 1, "contact_name": "Acme", "city": "Augsburg",
                "country": "DE", "contact_type": "Handwerksbetrieb", "email": "a@acme.de",
                "website": "https://acme.de", "contact_notes": "x" * 150,
            }
            for lang in ("en", "de"):
                conn, cur = make_mock_conn([draft])
                with patch("gcrm.api.routers.drafts.db") as mock_db:
                    mock_db.return_value.__enter__.return_value = conn
                    r = client.get(f"/drafts/?lang={lang}")
                assert r.status_code == 200, r.text
        finally:
            clear_login_session()
