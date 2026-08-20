"""Area-scan endpoints (web session + mobile JWT): request validation, area
creation/reuse, and that a queued scan calls spawn_area_stage with the right
args. subprocess.Popen is mocked via spawn_area_stage — nothing actually spawns."""
from unittest.mock import patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


class TestMobileAreasEndpoint:
    def test_requires_auth(self):
        assert client.post("/api/areas/scan", json={"lat": 48.37, "lon": 10.9, "radius_m": 500, "levels": [1]}).status_code in (401, 403)

    def test_queues_area_scan(self):
        with patch("gcrm.api.routers.api_areas.reverse_geocode", return_value=None), \
             patch("gcrm.api.routers.api_areas.find_or_create_area", return_value=42) as find_area, \
             patch("gcrm.api.routers.api_areas.spawn_area_stage") as spawn:
            resp = client.post(
                "/api/areas/scan", headers=AUTH,
                json={"lat": 48.37, "lon": 10.9, "radius_m": 500, "levels": [1, 3], "label": "Test area"},
            )
        assert resp.status_code == 202
        assert resp.json() == {"status": "queued", "area_id": 42, "levels": [1, 3]}
        find_area.assert_called_once_with(48.37, 10.9, 500, label="Test area", city_id=None)
        spawn.assert_called_once_with("research", 42, [1, 3])

    def test_resolves_city_id_from_reverse_geocode(self):
        resolved = {"name": "Augsburg", "country": "DE", "state": "Bavaria"}
        with patch("gcrm.api.routers.api_areas.reverse_geocode", return_value=resolved), \
             patch("gcrm.api.routers.api_areas.add_city", return_value=9) as add_city, \
             patch("gcrm.api.routers.api_areas.find_or_create_area", return_value=42) as find_area, \
             patch("gcrm.api.routers.api_areas.spawn_area_stage"):
            resp = client.post(
                "/api/areas/scan", headers=AUTH,
                json={"lat": 48.37, "lon": 10.9, "radius_m": 500, "levels": [1]},
            )
        assert resp.status_code == 202
        add_city.assert_called_once_with("Augsburg", "DE", "Bavaria")
        find_area.assert_called_once_with(48.37, 10.9, 500, label="", city_id=9)

    def test_bad_request_is_422(self):
        # Real spawn_area_stage runs: unknown level -> ValueError -> 422
        with patch("gcrm.api.routers.api_areas.reverse_geocode", return_value=None), \
             patch("gcrm.api.routers.api_areas.find_or_create_area", return_value=42):
            resp = client.post(
                "/api/areas/scan", headers=AUTH,
                json={"lat": 48.37, "lon": 10.9, "radius_m": 500, "levels": [99]},
            )
        assert resp.status_code == 422

    def test_radius_out_of_bounds_is_422(self):
        resp = client.post(
            "/api/areas/scan", headers=AUTH,
            json={"lat": 48.37, "lon": 10.9, "radius_m": 5000, "levels": [1]},
        )
        assert resp.status_code == 422

    def test_list_requires_auth(self):
        assert client.get("/api/areas/").status_code in (401, 403)

    def test_list_returns_overview(self):
        overview = {"areas": [], "levels": [1], "level_labels": {1: "Tier 1"}, "total": 0}
        with patch("gcrm.api.routers.api_areas.build_area_overview", return_value=overview):
            resp = client.get("/api/areas/", headers=AUTH)
        assert resp.status_code == 200
        # JSON round-trip stringifies dict keys — level_labels' int keys become "1".
        assert resp.json() == {**overview, "level_labels": {"1": "Tier 1"}}

    def test_organizations_requires_auth(self):
        assert client.get("/api/areas/42/organizations").status_code in (401, 403)

    def test_organizations_returns_list(self):
        orgs = [{"id": 1, "name": "Test Org", "latitude": 48.37, "longitude": 10.9}]
        with patch("gcrm.api.routers.api_areas.get_area_organizations", return_value=orgs):
            resp = client.get("/api/areas/42/organizations", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"organizations": orgs}


class TestWebAreasEndpoint:
    def test_requires_login(self):
        resp = client.post(
            "/areas/scan", json={"lat": 48.37, "lon": 10.9, "radius_m": 500, "levels": [1]},
            follow_redirects=False,
        )
        assert resp.status_code in (303, 307)

    def test_admin_queues_area_scan(self):
        from gcrm.api.auth import require_admin, require_login
        main.app.dependency_overrides[require_login] = lambda: "admin"
        main.app.dependency_overrides[require_admin] = lambda: "admin"
        try:
            with patch("gcrm.api.routers.areas.reverse_geocode", return_value=None), \
                 patch("gcrm.api.routers.areas.find_or_create_area", return_value=42) as find_area, \
                 patch("gcrm.api.routers.areas.spawn_area_stage") as spawn:
                resp = client.post(
                    "/areas/scan",
                    json={"lat": 48.37, "lon": 10.9, "radius_m": 500, "levels": [1]},
                )
            assert resp.status_code == 202
            assert resp.json() == {"status": "queued", "area_id": 42, "levels": [1]}
            find_area.assert_called_once_with(48.37, 10.9, 500, label="", city_id=None)
            spawn.assert_called_once_with("research", 42, [1])
        finally:
            main.app.dependency_overrides.pop(require_login, None)
            main.app.dependency_overrides.pop(require_admin, None)

    def test_page_renders(self):
        from gcrm.api.auth import require_login
        main.app.dependency_overrides[require_login] = lambda: "admin"
        try:
            overview = {"areas": [], "levels": [1], "level_labels": {1: "Tier 1"}, "total": 0}
            with patch("gcrm.api.routers.areas.build_area_overview", return_value=overview):
                resp = client.get("/areas/")
            assert resp.status_code == 200
        finally:
            main.app.dependency_overrides.pop(require_login, None)
