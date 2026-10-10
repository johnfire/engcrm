"""The Organizations list names the people at each organization — real schema."""
import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.db.connection import db
from gcrm.tools.db_people import save_person

pytestmark = pytest.mark.integration


def test_the_list_query_returns_the_people_at_each_organization(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, city, workspace_id) "
            "VALUES ('Acme GmbH', 'Augsburg', (SELECT id FROM workspaces WHERE slug = 'default')) "
            "RETURNING id"
        )
        acme = cursor.fetchone()["id"]
    linkedin = save_person("Anna LinkedIn", contact_id=acme, source="linkedin_import", allow_duplicate=True)
    card = save_person("Zora Card", contact_id=acme, source="card_capture", allow_duplicate=True)

    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        response = TestClient(main.app).get("/organizations/?lang=en")
    finally:
        main.app.dependency_overrides.pop(require_login, None)
        main.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200, response.text[:500]
    zora, anna = response.text.index(f'href="/people/{card}"'), response.text.index(f'href="/people/{linkedin}"')
    assert zora < anna  # met in person first
