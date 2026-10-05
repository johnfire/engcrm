"""Statistics end to end on the real schema: log activities and a sale through the
web forms, then read them back on the Statistics page."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.db.connection import db

pytestmark = pytest.mark.integration


@pytest.fixture
def web(clean_database):
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def _organization() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, city, pipeline_stage, status, workspace_id) "
            "VALUES ('Acme GmbH', 'Augsburg', 'suspect', 'ready', "
            "(SELECT id FROM workspaces WHERE slug = 'default')) RETURNING id"
        )
        return cursor.fetchone()["id"]


def test_logged_work_and_a_sale_show_up_in_the_statistics(web):
    acme = _organization()
    post = lambda url, data: web.post(url, data=data, follow_redirects=False)  # noqa: E731
    assert post(f"/organizations/{acme}/activity", {"method": "in_person", "note": "Dropped by"}).status_code == 303
    assert post(f"/organizations/{acme}/activity",
                {"method": "meeting", "duration_minutes": "90", "note": "Sat down with the owner"}).status_code == 303
    assert post(f"/organizations/{acme}/sales",
                {"amount_eur": "2.400,00".replace(".", ""), "won_on": date.today().isoformat(),
                 "description": "Painting"}).status_code == 303
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET pipeline_stage = 'customer' WHERE id = %s", (acme,))

    page = web.get("/statistics?period=month&lang=en")

    assert page.status_code == 200, page.text[:500]
    text = page.text
    assert "2.400 €" in text                       # won
    assert "<strong class=\"stat-tile__value\">2</strong>" in text  # 2 activities
    assert "<strong class=\"stat-tile__value\">1.8</strong>" in text  # 15 + 90 min = 1.75 h
    assert "1.371,43 €" in text                   # € per hour: 2400 / 105 min * 60
    assert "Suspect → Customer" in text           # the trigger caught the stage change
    assert f'href="/organizations/{acme}">Acme GmbH</a>' in text

    detail = web.get(f"/organizations/{acme}?lang=en").text
    assert "2.400 €" in detail and "Painting" in detail
    assert "Sit-down meeting · 90 min" in detail


def test_bad_input_is_refused_and_nothing_is_written(web):
    acme = _organization()
    assert web.post(f"/organizations/{acme}/sales", data={"amount_eur": "0", "won_on": "2026-10-05"}).status_code == 400
    assert web.post(f"/organizations/{acme}/sales", data={"amount_eur": "abc", "won_on": "2026-10-05"}).status_code == 400
    assert web.post(f"/organizations/{acme}/activity", data={"method": "bogus", "note": "x"}).status_code == 400
    assert web.post(f"/organizations/{acme}/activity", data={"method": "phone", "duration_minutes": "-5",
                                                            "note": "x"}).status_code == 400
    assert web.post("/organizations/999999/sales", data={"amount_eur": "5", "won_on": "2026-10-05"}).status_code == 404
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT (SELECT COUNT(*) FROM sales) + (SELECT COUNT(*) FROM interactions) AS n")
        assert cursor.fetchone()["n"] == 0


def test_default_minutes_can_be_changed_and_a_custom_period_is_shown(web):
    assert web.post("/statistics/minutes", data={"minutes_drop_in": "20", "minutes_meeting": "60"},
                    follow_redirects=False).status_code == 303
    page = web.get("/statistics?period=custom&start=2026-01-01&end=2026-03-31&lang=de")
    assert page.status_code == 200
    assert 'Vorbeischauen <span class="muted small">(20 Min.)</span>' in page.text  # the effort table's default
    assert "2026-01-01 – 2026-03-31" in page.text and "Statistik" in page.text
    assert web.get("/statistics?period=custom&start=2026-03-31&end=2026-01-01").status_code == 400
