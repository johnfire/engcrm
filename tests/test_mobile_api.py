"""Mobile JSON API: JWT issuance/verification and the auth endpoint.
DB is patched out — these are unit-level."""
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token, decode_token
from gcrm.api.routers import api_organizations

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


class TestOpportunityAnalysis:
    """The mobile opportunity-analysis run mirrors the web action: admin-only,
    synchronous, returns the freshly stored assessment."""
    ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
    SPECTATOR = {"Authorization": f"Bearer {create_token('spectator')}"}

    STORED = {
        "opportunity_score": 80,
        "confidence_score": 60,
        "priority_score": 70,
        "fit_reasoning": "Strong fit.",
        "suggested_approach": "Email the owner.",
        "evidence": ["Old website"],
        "recommended_services": [{"service": "Booking bot", "outcome": "Fewer no-shows", "rationale": "Manual now"}],
        "discovery_questions": ["How do you book today?"],
        "analysis_date": None,
        "model_used": "cheap-llm",
    }

    def test_spectator_cannot_run_analysis(self):
        assert client.post("/api/contacts/42/opportunity-analysis", headers=self.SPECTATOR).status_code == 403

    def test_admin_runs_analysis_and_gets_result(self):
        with patch("gcrm.api.routers.api_organizations.analyse_organization_opportunity", return_value={"summary": "saved"}) as run, \
             patch("gcrm.api.routers.api_organizations.get_latest_opportunity_analysis", return_value=dict(self.STORED)):
            r = client.post("/api/contacts/42/opportunity-analysis", headers=self.ADMIN)
        run.assert_called_once_with(42)
        assert r.status_code == 200
        payload = r.json()["opportunity_analysis"]
        assert payload["opportunity_score"] == 80
        assert payload["recommended_services"][0]["service"] == "Booking bot"

    def test_missing_organization_returns_404(self):
        with patch("gcrm.api.routers.api_organizations.analyse_organization_opportunity", side_effect=LookupError):
            r = client.post("/api/contacts/999/opportunity-analysis", headers=self.ADMIN)
        assert r.status_code == 404

    def test_analysis_failure_returns_502(self):
        with patch("gcrm.api.routers.api_organizations.analyse_organization_opportunity", side_effect=RuntimeError("llm down")):
            r = client.post("/api/contacts/42/opportunity-analysis", headers=self.ADMIN)
        assert r.status_code == 502


class TestPersonalPriority:
    """Any real account may mutate only its own contact priority."""

    PAYLOAD = {"sub": "spectator", "uid": 7}
    USER = {
        "id": 7,
        "role": "spectator",
        "is_active": True,
        "workspace_id": 3,
    }

    def test_spectator_can_set_personal_priority(self):
        with patch(
            "gcrm.api.routers.api_organizations.get_user_by_id",
            return_value=self.USER,
        ), patch(
            "gcrm.api.routers.api_organizations.set_personal_priority",
            return_value=(True, 1),
        ) as save_priority, patch("gcrm.api.routers.api_organizations.log_audit"):
            response = api_organizations.update_personal_priority(
                42,
                api_organizations.PersonalPriorityBody(priority=1),
                self.PAYLOAD,
            )

        assert response == {"personal_priority": 1}
        save_priority.assert_called_once_with(7, 3, 42, 1)

    def test_spectator_can_clear_personal_priority(self):
        with patch(
            "gcrm.api.routers.api_organizations.get_user_by_id",
            return_value=self.USER,
        ), patch(
            "gcrm.api.routers.api_organizations.set_personal_priority",
            return_value=(True, None),
        ), patch("gcrm.api.routers.api_organizations.log_audit"):
            response = api_organizations.update_personal_priority(
                42,
                api_organizations.PersonalPriorityBody(priority=None),
                self.PAYLOAD,
            )

        assert response == {"personal_priority": None}

    def test_rejects_out_of_range_priority(self):
        with patch(
            "gcrm.api.routers.api_organizations.get_user_by_id",
            return_value=self.USER,
        ), pytest.raises(api_organizations.HTTPException) as error:
            api_organizations.update_personal_priority(
                42,
                api_organizations.PersonalPriorityBody(priority=6),
                self.PAYLOAD,
            )

        assert error.value.status_code == 400

    def test_shared_admin_cannot_own_personal_priority(self):
        with pytest.raises(api_organizations.HTTPException) as error:
            api_organizations.update_personal_priority(
                42,
                api_organizations.PersonalPriorityBody(priority=1),
                {"sub": "admin"},
            )
        assert error.value.status_code == 403

    def test_cross_workspace_organization_is_hidden(self):
        with patch(
            "gcrm.api.routers.api_organizations.get_user_by_id",
            return_value=self.USER,
        ), patch(
            "gcrm.api.routers.api_organizations.set_personal_priority",
            return_value=(False, None),
        ):
            with pytest.raises(api_organizations.HTTPException) as error:
                api_organizations.update_personal_priority(
                    42,
                    api_organizations.PersonalPriorityBody(priority=1),
                    self.PAYLOAD,
                )

        assert error.value.status_code == 404


class TestResearchOverview:
    """The read-only Research overview (mobile display parity with the web page)
    is viewable by any authenticated user, including a spectator."""
    SPECTATOR = {"Authorization": f"Bearer {create_token('spectator')}"}

    def test_requires_auth(self):
        assert client.get("/api/research/overview").status_code in (401, 403)

    def test_spectator_can_read_overview(self):
        fake = {
            "cities": [], "levels": [1, 2], "level_labels": {1: "A", 2: "B"},
            "total": 0, "level1_done": 0, "unscanned": 0,
            "totals": {"contacts": 0, "emailed": 0},
        }
        with patch("gcrm.api.routers.api_research.build_research_overview", return_value=fake):
            r = client.get("/api/research/overview", headers=self.SPECTATOR)
        assert r.status_code == 200
        assert r.json()["totals"] == {"contacts": 0, "emailed": 0}
