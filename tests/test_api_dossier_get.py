"""GET /api/research/dossier/{id} only reads; generating one is an admin POST."""
from unittest.mock import patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
SPECTATOR = {"Authorization": f"Bearer {create_token('spectator')}"}
STORED = {"contact_id": 7, "official_domain": "example.test", "company_summary": "Makes gears.",
          "research_status": "complete"}


def test_get_without_a_stored_dossier_is_404_and_never_generates():
    with patch("gcrm.research.dossier._get_active_dossier", return_value=None), \
         patch("gcrm.research.dossier._get_contact", return_value={"id": 7, "website": "https://example.test"}), \
         patch("gcrm.research.dossier._generate_dossier", return_value=dict(STORED)) as generate:
        response = client.get("/api/research/dossier/7", headers=SPECTATOR)
    assert response.status_code == 404
    generate.assert_not_called()


def test_get_returns_a_stored_dossier():
    with patch("gcrm.research.dossier._get_active_dossier", return_value=dict(STORED)), \
         patch("gcrm.research.dossier._generate_dossier") as generate:
        response = client.get("/api/research/dossier/7", headers=SPECTATOR)
    assert response.status_code == 200
    assert response.json()["dossier"]["company_summary"] == "Makes gears."
    generate.assert_not_called()


def test_a_spectator_cannot_generate_a_dossier():
    with patch("gcrm.research.dossier._generate_dossier") as generate:
        response = client.post("/api/research/dossier/7", headers=SPECTATOR)
    assert response.status_code == 403
    generate.assert_not_called()
