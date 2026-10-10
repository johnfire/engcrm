"""Every GET page and API endpoint answers without a server error, on the real
schema, with a few organizations and people in it.

Mocked unit tests pass even when a query names a column that is not there; this
is the net under all of them. Written for migration 064, which moved the stage
from contacts/people onto deals: a query the move missed is a 500 here."""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.people_next_step import set_person_next_step

pytestmark = pytest.mark.e2e

API = {"Authorization": f"Bearer {create_token('admin')}"}
# Endpoints that stream files or talk to the outside world rather than the database.
SKIPPED = {"/api/health", "/health"}


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    acme = save_organization("Acme", "Augsburg", email="info@acme.test", pipeline_stage="suspect",
                             status="ready", source="test_fixture")
    school = save_organization("Simmons Language School", "Hannover", source="test_fixture")
    with db() as connection:
        set_organization_deal(connection.cursor(), school, stage="prospect", offer="learnwohl")
    ann = save_person("Ann", contact_id=acme, pipeline_stage="prospect", source="test_fixture")
    save_person("Bob", pipeline_stage="candidate", allow_duplicate=True, source="test_fixture")
    set_person_next_step(ann, "Call on Friday", None)
    return {"contact_id": acme, "person_id": ann}


def _get_routes(routes, prefix=""):
    """Every GET APIRoute's full path, walking included routers (FastAPI wraps them)."""
    for route in routes:
        if isinstance(route, APIRoute):
            if "GET" in route.methods:
                yield prefix + route.path
        elif hasattr(route, "original_router"):
            yield from _get_routes(route.original_router.routes, prefix + route.include_context.prefix)


def _get_paths(ids: dict) -> list[str]:
    paths = []
    for path in _get_routes(main.app.routes):
        params = re.findall(r"{(\w+)(?::\w+)?}", path)
        if path in SKIPPED or any(name not in ids for name in params):
            continue
        paths.append(re.sub(r"{(\w+)(?::\w+)?}", lambda m: str(ids[m.group(1)]), path))
    return sorted(set(paths))


def test_no_page_or_endpoint_fails(world):
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    client = TestClient(main.app, raise_server_exceptions=False)
    failures = []
    try:
        paths = _get_paths(world)
        for path in paths:
            response = client.get(path, headers=API if path.startswith("/api/") else {}, follow_redirects=False)
            if response.status_code >= 500:
                failures.append((path, response.status_code))
    finally:
        main.app.dependency_overrides.pop(require_login, None)
        main.app.dependency_overrides.pop(require_admin, None)
    assert len(paths) > 40  # the crawl reached the app, not an empty route table
    assert failures == []
