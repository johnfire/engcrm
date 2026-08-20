"""Recon proximity endpoint — auth + passthrough. DB mocked."""
from unittest.mock import patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


def test_requires_auth():
    assert client.get("/api/recon?lat=48&lng=11").status_code in (401, 403)


def test_returns_nearby():
    with patch("gcrm.api.routers.api_recon.get_organizations_near",
               return_value=[{"id": 1, "name": "X", "distance_m": 120.0}]) as near:
        resp = client.get("/api/recon?lat=48.05&lng=10.88&not_contacted=true", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()[0]["distance_m"] == 120.0
    assert near.call_args.kwargs["not_contacted"] is True
