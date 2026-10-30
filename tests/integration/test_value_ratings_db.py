"""Short- and long-term value ratings on the real schema: they share the private
rating row with priority, clear independently, and show up on the lists."""
import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_login
from gcrm.api.routers.organizations import _build_organization_filters, _fetch_organizations_page
from gcrm.db.connection import db
from gcrm.tools.db_people import (
    get_people,
    get_person,
    save_person,
    set_person_rating,
    set_person_value_rating,
)
from gcrm.tools.db_personal_priorities import set_organization_rating, set_personal_priority

pytestmark = pytest.mark.integration


def _user_and_contact() -> tuple[int, int, int]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users (email, password_hash, role, workspace_id) "
                       "VALUES ('value@example.test', 'hash', 'admin', %s) RETURNING id", (workspace_id,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts (name, workspace_id) VALUES ('Value Venue', %s) RETURNING id",
                       (workspace_id,))
        return user_id, workspace_id, cursor.fetchone()["id"]


def _rating_rows(contact_id: int) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT priority, short_term_value, long_term_value FROM contact_user_priorities "
                       "WHERE contact_id = %s", (contact_id,))
        return [dict(row) for row in cursor.fetchall()]


def test_organization_ratings_share_one_row_and_clear_independently(clean_database):
    user_id, workspace_id, contact_id = _user_and_contact()

    assert set_organization_rating(user_id, workspace_id, contact_id, "short_term_value", 3) == (True, 3)
    assert set_organization_rating(user_id, workspace_id, contact_id, "long_term_value", 0) == (True, 0)
    assert set_personal_priority(user_id, workspace_id, contact_id, 2) == (True, 2)
    assert _rating_rows(contact_id) == [{"priority": 2, "short_term_value": 3, "long_term_value": 0}]

    # Clearing priority keeps the values; clearing the last rating removes the row.
    assert set_personal_priority(user_id, workspace_id, contact_id, None) == (True, None)
    assert _rating_rows(contact_id) == [{"priority": None, "short_term_value": 3, "long_term_value": 0}]
    set_organization_rating(user_id, workspace_id, contact_id, "short_term_value", None)
    set_organization_rating(user_id, workspace_id, contact_id, "long_term_value", None)
    assert _rating_rows(contact_id) == []


def test_database_rejects_values_outside_zero_to_three(clean_database):
    user_id, workspace_id, contact_id = _user_and_contact()
    import psycopg2

    with pytest.raises(psycopg2.errors.CheckViolation):
        with db() as connection:
            connection.cursor().execute(
                "INSERT INTO contact_user_priorities (workspace_id, user_id, contact_id, long_term_value) "
                "VALUES (%s, %s, %s, 4)", (workspace_id, user_id, contact_id))


def test_organization_list_and_detail_show_and_sort_by_value(clean_database):
    user_id, workspace_id, low_id = _user_and_contact()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts (name, workspace_id) VALUES ('High Venue', %s) RETURNING id",
                       (workspace_id,))
        high_id = cursor.fetchone()["id"]
    set_organization_rating(user_id, workspace_id, low_id, "short_term_value", 1)
    set_organization_rating(user_id, workspace_id, high_id, "short_term_value", 3)
    set_organization_rating(user_id, workspace_id, high_id, "long_term_value", 2)

    where, params = _build_organization_filters("", "", "", "", workspace_id=workspace_id)
    rows, *_ = _fetch_organizations_page(where, params, "cup.short_term_value", "DESC", 0, user_id, workspace_id)
    assert [(r["name"], r["short_term_value"], r["long_term_value"]) for r in rows] == [
        ("High Venue", 3, 2), ("Value Venue", 1, None)]

    main.app.dependency_overrides[require_login] = lambda: "admin"
    try:
        client = TestClient(main.app)
        with client:
            client.cookies.clear()
            # The detail page needs a session user to show the rating buttons; without
            # one it still renders and asks for a personal account.
            page = client.get(f"/organizations/{high_id}")
            listing = client.get("/organizations/?sort=long_term_value&dir=desc")
            printed = client.get("/organizations/print?sort=short_term_value&dir=desc")
    finally:
        main.app.dependency_overrides.pop(require_login, None)
    assert page.status_code == 200, page.text[:500]
    assert "Sign in with a personal account to rate this value." in page.text
    assert listing.status_code == 200, listing.text[:500]
    assert printed.status_code == 200, printed.text[:500]


def test_person_values_show_and_sort_on_the_people_list(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    user_id, workspace_id, _ = _user_and_contact()
    anna = save_person("Anna", allow_duplicate=True, source="test_fixture")
    ben = save_person("Ben", allow_duplicate=True, source="test_fixture")
    set_person_value_rating(user_id, workspace_id, anna, 2)
    assert set_person_rating(user_id, workspace_id, anna, "long_term_value", 1) == (True, 1)
    assert set_person_rating(user_id, workspace_id, ben, "long_term_value", 3) == (True, 3)

    found = get_people(user_id=user_id, sort="long_term_value", dir="desc")
    assert [(p["name"], p["long_term_value"], p["value_rating"]) for p in found] == [
        ("Ben", 3, None), ("Anna", 1, 2)]
    assert get_person(anna, user_id)["long_term_value"] == 1
    assert get_person(anna, None)["long_term_value"] is None


def test_forget_it_is_stored_for_organizations_only(clean_database):
    import psycopg2

    user_id, workspace_id, contact_id = _user_and_contact()
    assert set_personal_priority(user_id, workspace_id, contact_id, 6) == (True, 6)
    with pytest.raises(psycopg2.errors.CheckViolation):
        with db() as connection:
            connection.cursor().execute(
                "INSERT INTO contact_user_priorities (workspace_id, user_id, contact_id, priority) "
                "VALUES (%s, %s, %s, 7) ON CONFLICT (user_id, contact_id) DO UPDATE SET priority = 7",
                (workspace_id, user_id, contact_id))
    person = save_person("Pat", allow_duplicate=True, source="test_fixture")
    with pytest.raises(psycopg2.errors.CheckViolation):
        with db() as connection:
            connection.cursor().execute(
                "INSERT INTO person_user_priorities (workspace_id, user_id, person_id, priority) "
                "VALUES (%s, %s, %s, 6)", (workspace_id, user_id, person))
