"""Statistics end to end on the real schema: log activities and a sale through the
web forms, then read them back on the Statistics page."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.statistics import get_statistics

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
            "INSERT INTO contacts (name, city, workspace_id) "
            "VALUES ('Acme GmbH', 'Augsburg', "
            "(SELECT id FROM workspaces WHERE slug = 'default')) RETURNING id"
        )
        contact_id = cursor.fetchone()["id"]
        set_organization_deal(cursor, contact_id, stage="suspect", status="ready")
        return contact_id


def _deal(contact_id: int) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM deals WHERE contact_id = %s AND deleted_at IS NULL", (contact_id,))
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
    # moved on from the Organizations list, as you would by hand
    assert post(f"/deals/{_deal(acme)}", {"stage": "customer", "next": "/organizations/"}).status_code == 303

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


def test_training_and_post_mail_can_be_logged_and_read_back(web):
    acme = _organization()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, workspace_id FROM offers WHERE slug='training' AND workspace_id="
                       "(SELECT id FROM workspaces WHERE slug='default')")
        training = cursor.fetchone()
        training_id, workspace_id = training['id'], training['workspace_id']
        cursor.execute("INSERT INTO people (name,workspace_id) SELECT 'Postal Person', id FROM workspaces "
                       "WHERE slug='default' RETURNING id")
        person_id = cursor.fetchone()['id']
    for path in [f'/organizations/{acme}?lang=en', f'/people/{person_id}?lang=en']:
        page = web.get(path)
        assert page.status_code == 200
        assert 'value="letter">Post mail</option>' in page.text
        assert f'value="{training_id}"' in page.text and '>Training</option>' in page.text
    organization = web.post(f'/organizations/{acme}/activity', data={
        'method': 'letter', 'note': 'Posted training brochure', 'offer': str(training_id),
        'duration_minutes': '12',
    }, follow_redirects=False)
    assert organization.status_code == 303
    person = web.post(f'/people/{person_id}/notes', data={
        'method': 'letter', 'note': 'Posted training invitation', 'offer': str(training_id),
        'duration_minutes': '8',
    }, follow_redirects=False)
    assert person.status_code == 303
    assert 'Post mail' in web.get(f'/organizations/{acme}?lang=en').text
    assert 'Post mail' in web.get(f'/people/{person_id}?lang=en').text
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT method,offer_id FROM interactions WHERE contact_id=%s", (acme,))
        assert dict(cursor.fetchone()) == {'method': 'letter', 'offer_id': training_id}
        cursor.execute("SELECT method,offer_id FROM people_interactions WHERE person_id=%s", (person_id,))
        assert dict(cursor.fetchone()) == {'method': 'letter', 'offer_id': training_id}
    statistics = web.get('/statistics?period=month&lang=en')
    assert statistics.status_code == 200 and 'Post mail' in statistics.text
    summary = get_statistics(workspace_id, date.today(), date.today())
    assert summary['current']['effort']['post_mail']['count'] == 2
    assert summary['current']['effort']['post_mail']['minutes'] == 20


def test_training_seed_is_idempotent_and_keeps_existing_settings(web):
    from pathlib import Path

    migration = Path('gcrm/db/migrations/068_training_offer.sql').read_text()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE offers SET name='Training courses' WHERE slug='training' "
                       "AND workspace_id=(SELECT id FROM workspaces WHERE slug='default')")
        cursor.execute(migration)
        cursor.execute(migration)
        cursor.execute("SELECT name FROM offers WHERE slug='training' "
                       "AND workspace_id=(SELECT id FROM workspaces WHERE slug='default')")
        assert [row['name'] for row in cursor.fetchall()] == ['Training courses']
        cursor.execute("UPDATE offers SET name='Training' WHERE slug='training' "
                       "AND workspace_id=(SELECT id FROM workspaces WHERE slug='default')")


@pytest.mark.e2e
def test_customer_status_saves_and_remains_selected_after_reloading(web):
    acme = _organization()
    deal_id = _deal(acme)
    response = web.post(f'/deals/{deal_id}', data={'status': 'customer'}, follow_redirects=False)
    assert response.status_code == 303
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT pipeline_stage,status FROM deals WHERE id=%s', (deal_id,))
        assert dict(cursor.fetchone()) == {'pipeline_stage': 'suspect', 'status': 'customer'}
    for language, label in [('en', 'Customer'), ('de', 'Kunde')]:
        detail = web.get(f'/organizations/{acme}?lang={language}')
        assert detail.status_code == 200
        assert 'value="customer" selected' in detail.text
        assert label in detail.text
    listing = web.get('/organizations/?status=customer&lang=en')
    assert listing.status_code == 200
    assert 'Acme GmbH' in listing.text
