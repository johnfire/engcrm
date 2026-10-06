"""Contact-day validation, request authorization and stale form handling."""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from gcrm.api.auth import require_admin
from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.audit_context import current_audit_context
from gcrm.tools.db_contact_dates import contact_tables, parse_contact_day

ROUTE = "gcrm.api.routers.contact_dates"
RECORD = {"id": 1, "kind": "person", "name": "Ann", "interaction_id": 9, "contact_date": "2026-10-04"}
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.mark.parametrize("invalid", ["", "yesterday", "2026-02-30", "20261003", "2026-W01-1", "2026-10-03T10:00:00", "9999-12-31"])
def test_invalid_or_future_contact_day_is_rejected(invalid):
    with pytest.raises(HTTPException) as failure:
        parse_contact_day(invalid)
    assert failure.value.status_code == 400


def test_valid_day_and_known_kinds():
    assert parse_contact_day("2026-10-03") == date(2026, 10, 3)
    assert contact_tables("person")[0] == "people"
    assert contact_tables("organization")[0] == "contacts"
    with pytest.raises(HTTPException):
        contact_tables("contacts; DROP TABLE people")


def test_mobile_read_and_write_scope_and_trace_the_contact():
    with patch(f"{ROUTE}._personal_identity", return_value=(None, 3)), \
         patch(f"{ROUTE}.get_contact_date", return_value=RECORD) as read:
        response = TestClient(app).get("/api/contact-feed/person/1/date", headers=ADMIN)
    assert response.json() == RECORD
    read.assert_called_once_with("person", 1, 3)
    def save(*arguments):
        assert arguments == ("person", 1, date(2026, 10, 3), 9, "2026-10-04", 3)
        assert current_audit_context().actor == "shared-admin"
        assert current_audit_context().correlation_id == "date-test"
        return {**RECORD, "contact_date": "2026-10-03"}
    with patch(f"{ROUTE}._personal_identity", return_value=(None, 3)), \
         patch(f"{ROUTE}.set_contact_date", side_effect=save):
        response = TestClient(app).patch("/api/contact-feed/person/1/date", headers={**ADMIN, "X-Request-ID": "date-test"},
                                        json={"contact_date": "2026-10-03", "interaction_id": 9, "previous_date": "2026-10-04"})
    assert response.status_code == 200 and response.json()["contact_date"] == "2026-10-03"


def test_mobile_invalid_day_and_spectator_never_write():
    with patch(f"{ROUTE}.set_contact_date") as save:
        response = TestClient(app).patch("/api/contact-feed/person/1/date", headers=ADMIN, json={"contact_date": "tomorrow"})
        assert response.status_code == 400
        spectator = {"Authorization": f"Bearer {create_token('spectator')}"}
        assert TestClient(app).get("/api/contact-feed/person/1/date", headers=spectator).status_code == 403
        assert TestClient(app).patch("/api/contact-feed/person/1/date", headers=spectator, json={"contact_date": "2026-10-03"}).status_code == 403
        save.assert_not_called()


@pytest.fixture
def admin_browser():
    def signed_in(request: Request):
        request.session.update(role="admin", email="owner@example.test")
        return "admin"
    app.dependency_overrides[require_admin] = signed_in
    yield TestClient(app)
    app.dependency_overrides.pop(require_admin, None)


def test_web_form_date_and_history_version(admin_browser):
    with patch(f"{ROUTE}.get_contact_date", return_value=RECORD):
        response = admin_browser.get("/contact-feed/person/1/date")
        assert response.status_code == 200
        assert 'type="date"' in response.text and 'value="2026-10-04"' in response.text
        assert 'name="interaction_id" value="9"' in response.text
        assert "Datum des letzten Kontakts" in admin_browser.get("/contact-feed/person/1/date?lang=de").text


@pytest.mark.parametrize("failure,status", [(HTTPException(409, "History changed"), 409), (RuntimeError("offline"), 503)])
def test_web_error_keeps_the_selected_date(admin_browser, failure, status):
    with patch(f"{ROUTE}.get_contact_date", return_value=RECORD), \
         patch(f"{ROUTE}.set_contact_date", side_effect=failure):
        response = admin_browser.post("/contact-feed/person/1/date", data={
            "contact_date": "2026-10-03", "interaction_id": "9", "previous_date": "2026-10-04",
        })
    assert response.status_code == status and 'value="2026-10-03"' in response.text


def test_web_first_contact_and_save_redirect(admin_browser):
    with patch(f"{ROUTE}.get_contact_date", return_value={**RECORD, "interaction_id": None, "contact_date": None}), \
         patch(f"{ROUTE}.set_contact_date", return_value=RECORD) as save:
        response = admin_browser.post("/contact-feed/person/1/date", data={"contact_date": "2026-10-03"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/contact-feed/"
    assert save.call_args.args[3:5] == (None, None)

def test_stale_web_form_keeps_the_reviewed_version_until_reopened(admin_browser):
    changed = {**RECORD, "interaction_id": 10, "contact_date": "2026-10-05"}
    with patch(f"{ROUTE}.get_contact_date", return_value=changed), \
         patch(f"{ROUTE}.set_contact_date", side_effect=HTTPException(409, "History changed")):
        response = admin_browser.post("/contact-feed/person/1/date", data={
            "contact_date": "2026-10-03", "interaction_id": "9", "previous_date": "2026-10-04",
        })
    assert response.status_code == 409
    assert 'name="interaction_id" value="9"' in response.text
    assert 'name="previous_date" value="2026-10-04"' in response.text
    assert 'name="interaction_id" value="10"' not in response.text
