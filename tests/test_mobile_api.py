"""Mobile JSON API: JWT issuance/verification and the auth endpoint.
DB is patched out — these are unit-level."""
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token, decode_token

client = TestClient(main.app)


class TestJWT:
    def test_roundtrip(self):
        assert decode_token(create_token("admin")) == "admin"
        assert decode_token(create_token("spectator")) == "spectator"

    def test_invalid_token_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            decode_token("not-a-token")


class TestAuthTokenEndpoint:
    def test_valid_credentials_return_token(self):
        with patch("gcrm.api.routers.api_auth.get_user_by_email", return_value={"id": 1}), \
             patch("gcrm.api.routers.api_auth.authenticate",
                   return_value={"role": "admin", "user_id": 1, "email": "a@b.com"}):
            r = client.post("/api/auth/token", json={"email": "a@b.com", "password": "pw"})
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "admin"
        assert decode_token(body["token"]) == "admin"

    def test_invalid_credentials_401(self):
        with patch("gcrm.api.routers.api_auth.get_user_by_email", return_value=None), \
             patch("gcrm.api.routers.api_auth.authenticate", return_value=None):
            r = client.post("/api/auth/token", json={"email": "a@b.com", "password": "wrong"})
        assert r.status_code == 401


class TestAuthGuard:
    def test_protected_route_rejects_missing_token(self):
        # HTTPBearer with no Authorization header → 403 (Starlette default)
        assert client.get("/api/activity").status_code in (401, 403)

    def test_protected_route_rejects_bad_token(self):
        r = client.get("/api/activity", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401


class TestRoleEnforcement:
    """Mutating mobile endpoints require the admin role; a read-only spectator
    token is rejected with 403 at the auth dependency (before any DB access)."""
    SPECTATOR = {"Authorization": f"Bearer {create_token('spectator')}"}

    def test_spectator_cannot_discard_card(self):
        assert client.post("/api/cards/1/discard", headers=self.SPECTATOR).status_code == 403

    def test_spectator_cannot_confirm_card(self):
        r = client.post("/api/cards/1/confirm", headers=self.SPECTATOR, json={"fields": {}})
        assert r.status_code == 403

    def test_spectator_cannot_confirm_voice(self):
        r = client.post("/api/voice/confirm", headers=self.SPECTATOR, json={"summary": "x"})
        assert r.status_code == 403
