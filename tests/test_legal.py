"""Public legal pages — no auth required."""
from fastapi.testclient import TestClient

import gcrm.api.main as main

client = TestClient(main.app)


class TestImpressum:
    def test_reachable_without_login(self):
        r = client.get("/impressum")
        assert r.status_code == 200

    def test_contains_required_ddg_5_fields(self):
        r = client.get("/impressum")
        assert "Christopher Rehm" in r.text
        assert "Alpenstr. 3" in r.text
        assert "86836 Klosterlechfeld" in r.text
        assert "car2187bus@pm.me" in r.text

    def test_linked_from_public_login_page(self):
        r = client.get("/login")
        assert '<a href="/impressum">Impressum</a>' in r.text
