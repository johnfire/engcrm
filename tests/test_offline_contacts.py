"""Manual monthly statistics are separate, bounded, and require administrator access."""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gcrm.api.auth import require_admin
from gcrm.api.main import app
from gcrm.api.routers.contact_feed import safe_offline_totals
from gcrm.audit_context import current_audit_context
from gcrm.tools.db_offline_contacts import parse_offline_total


@pytest.mark.parametrize("month,total,expected", [
    ("2026-10-01", "35", (date(2026, 10, 1), 35)),
    ("2026-11-01", "0", (date(2026, 11, 1), 0)),
    ("2026-11-01", "1000000", (date(2026, 11, 1), 1000000)),
])
def test_parse_monthly_total(month, total, expected):
    assert parse_offline_total(month, total, on=date(2026, 11, 6)) == expected


@pytest.mark.parametrize("month,total", [
    ("2026-11-02", "35"), ("2026-10-02", "35"), ("2026-12-01", "35"), ("2026-09-01", "35"),
    ("2026-02-30", "35"), ("oops", "35"), ("2026-11-01", "-1"),
    ("2026-11-01", "3.5"), ("2026-11-01", "1000001"), ("2026-11-01", ""),
    ("2026-11-01", "٣٥"),
])
def test_invalid_month_or_count_is_rejected(month, total):
    with pytest.raises(HTTPException) as failure:
        parse_offline_total(month, total, on=date(2026, 11, 6))
    assert failure.value.status_code == 400


def test_signed_out_cannot_change_offline_totals():
    with patch("gcrm.api.routers.contact_feed.save_offline_total") as save:
        response = TestClient(app).post("/contact-feed/offline", data={"month": "2026-11-01", "total": "35"},
                                        follow_redirects=False)
    assert response.status_code in (303, 307, 403)
    save.assert_not_called()


def test_unavailable_offline_storage_does_not_break_the_contact_page():
    with patch("gcrm.api.routers.contact_feed.get_offline_totals", side_effect=RuntimeError("unavailable")):
        assert safe_offline_totals() is None
    with patch("gcrm.api.routers.contact_feed.get_offline_totals", return_value={"2026-11-01": 35}):
        assert safe_offline_totals() == {"2026-11-01": 35}


def test_save_route_keeps_month_and_total_separate_and_records_actor():
    observed = []

    def save(month, total):
        observed.append((month, total, current_audit_context()))

    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.save_offline_total", side_effect=save):
            response = TestClient(app).post("/contact-feed/offline", data={"month": "2026-10-01", "total": "35"},
                                            follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/contact-feed/?offline_saved=1"
        assert observed[0][:2] == (date(2026, 10, 1), 35)
        assert observed[0][2].actor == "shared-admin" and observed[0][2].correlation_id
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_save_failure_is_visible_and_does_not_claim_success():
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.save_offline_total", side_effect=RuntimeError("unavailable")):
            response = TestClient(app).post("/contact-feed/offline", data={"month": "2026-10-01", "total": "35"})
        assert response.status_code == 503 and "could not be saved" in response.text
    finally:
        app.dependency_overrides.pop(require_admin, None)
