"""Profile discovery filters and authenticated scan lookup guards."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.routers.api_capture_linkedin import establish_capture_workspace
from gcrm.tools.capture_linkedin import (
    find_capture_profiles,
    normalize_profile_url,
    profile_candidates,
    search_text,
)
from gcrm.tools.db_capture_linkedin import save_capture_profile
from gcrm.tools.documents import normalize_document_contacts

PROFILE = "https://www.linkedin.com/in/anna-roth"
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.mark.parametrize("value", [
    "linkedin.com/in/Anna-Roth/?trk=scan", "https://de.linkedin.com/in/anna-roth#contact",
])
def test_person_profile_is_canonical(value):
    assert normalize_profile_url(value) == PROFILE


@pytest.mark.parametrize("value", [
    None, "", "https://linkedin.com/company/acme", "https://linkedin.com/search/results/people",
    "https://linkedin.com.evil.test/in/anna", "javascript:alert(1)",
    "https://user:password@linkedin.com/in/anna", "https://linkedin.com:bad/in/anna",
    "https://linkedin.com:123/in/anna", "https://linkedin.com/in/anna/details",
])
def test_non_person_or_hostile_urls_are_rejected(value):
    assert normalize_profile_url(value) is None


def test_query_terms_normalize_accents_and_search_operators():
    assert search_text('Jürgen Müller site:evil.test "') == 'jurgen muller site evil test'


def test_suggestions_require_name_evidence_dedup_and_person_urls():
    matches = [
        {"href": PROFILE, "title": "Anna Roth - ACME", "body": "Augsburg"},
        {"href": PROFILE + "?trk=other", "title": "Anna Roth", "body": "Another snippet"},
        {"href": "https://linkedin.com/in/bernd-roth", "title": "Bernd Roth", "body": "ACME"},
        {"href": "https://linkedin.com/company/anna-roth", "title": "Anna Roth"},
        {"href": "https://evil.test/in/anna-roth", "title": "Anna Roth"},
    ]
    assert profile_candidates(matches, "Anna Roth") == [
        {"url": PROFILE, "title": "Anna Roth - ACME", "snippet": "Augsburg"},
    ]


def test_search_uses_identity_context_and_does_not_choose_a_match():
    with patch("gcrm.tools.capture_linkedin.DDGS") as search:
        search.return_value.text.return_value = [{"href": PROFILE, "title": "Anna Roth", "body": "ACME"}]
        suggestions = find_capture_profiles("Anna Roth", "ACME", "Augsburg")
    assert suggestions["status"] == "found"
    assert "linkedin_url" not in suggestions
    search.assert_called_once_with(timeout=8)
    query = search.return_value.text.call_args.args[0]
    assert 'site:linkedin.com/in/ "anna roth" acme augsburg' == query


def test_missing_name_does_not_search_and_failures_are_nonblocking():
    with patch("gcrm.tools.capture_linkedin.DDGS", side_effect=RuntimeError("offline")) as search:
        assert find_capture_profiles("Bakery")["status"] == "needs_name"
        search.assert_not_called()
        assert find_capture_profiles("Anna Roth") == {"status": "unavailable", "candidates": []}


def test_empty_search_does_not_claim_a_profile_exists():
    with patch("gcrm.tools.capture_linkedin.DDGS") as search:
        search.return_value.text.return_value = []
        assert find_capture_profiles("Anna Roth") == {"status": "no_match", "candidates": []}


def test_document_keeps_printed_profile_for_review():
    contacts = normalize_document_contacts({"contacts": [{"name": "Anna Roth", "linkedin_url": PROFILE}]})
    assert contacts[0]["linkedin_url"] == PROFILE


@pytest.mark.parametrize("role, status", [(None, 401), ("viewer", 403)])
def test_profile_lookup_requires_admin(role, status):
    headers = {"Authorization": f"Bearer {create_token(role)}"} if role else {}
    with patch("gcrm.api.routers.api_capture_linkedin.find_capture_profiles") as search:
        response = TestClient(app).post("/api/cards/1/linkedin-search", headers=headers, json={"name": "Anna Roth"})
    assert response.status_code == status
    search.assert_not_called()


def test_lookup_only_searches_pending_capture_and_carries_trace_id():
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {"id": 1}
    with patch("gcrm.api.routers.api_capture_linkedin.db") as database, \
         patch("gcrm.api.routers.api_capture_linkedin.find_capture_profiles", return_value={"status": "no_match", "candidates": []}) as search, \
         patch("gcrm.api.routers.api_capture_linkedin.log_audit") as audit:
        database.return_value.__enter__.return_value = connection
        response = TestClient(app).post("/api/cards/1/linkedin-search", headers={**AUTH, "X-Request-ID": "lookup-test"},
                                        json={"name": "Anna Roth", "company": "ACME", "city": "Augsburg"})
    assert response.status_code == 200
    search.assert_called_once_with("Anna Roth", "ACME", "Augsburg")
    audit.assert_called_once_with(None, None, "capture.linkedin_searched", "card_capture:1", "no_match")


def test_missing_capture_never_performs_search():
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = None
    with patch("gcrm.api.routers.api_capture_linkedin.db") as database, \
         patch("gcrm.api.routers.api_capture_linkedin.find_capture_profiles") as search:
        database.return_value.__enter__.return_value = connection
        response = TestClient(app).post("/api/cards/1/linkedin-search", headers=AUTH, json={"name": "Anna Roth"})
    assert response.status_code == 404
    search.assert_not_called()


@pytest.mark.parametrize("fields", [
    {"name": "Anna Roth", "linkedin_url": "https://linkedin.com/company/acme"},
    {"company": "ACME", "linkedin_url": PROFILE},
    {"name": "Anna Roth", "linkedin_url": [PROFILE]},
])
def test_invalid_profile_does_not_create_records(fields):
    with patch("gcrm.api.routers.api_cards.db") as database:
        response = TestClient(app).post("/api/cards/1/confirm", headers=AUTH, json={"fields": fields})
    assert response.status_code == 422
    database.assert_not_called()


def test_workspace_is_derived_from_authenticated_user():
    with patch("gcrm.api.routers.api_capture_linkedin.get_user_by_id", return_value={"workspace_id": 7}) as user, \
         patch("gcrm.api.routers.api_capture_linkedin.set_workspace_id") as workspace:
        establish_capture_workspace({"uid": 42})
    user.assert_called_once_with(42)
    workspace.assert_called_once_with(7)


def test_missing_user_workspace_is_denied():
    from fastapi import HTTPException
    with patch("gcrm.api.routers.api_capture_linkedin.get_user_by_id", return_value=None):
        with pytest.raises(HTTPException) as denied:
            establish_capture_workspace({"uid": 42})
    assert denied.value.status_code == 403


def test_profile_persistence_validates_before_database_access():
    with patch("gcrm.tools.db_capture_linkedin.db") as database:
        with pytest.raises(ValueError):
            save_capture_profile(7, "https://linkedin.com/company/acme")
    database.assert_not_called()
