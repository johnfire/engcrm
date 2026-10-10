"""Mobile endpoints that change where an organization or a person stands in the
pipeline: PATCH /api/contacts/{id}/state and PATCH /api/people/{id}/stage. DB is
mocked — runs without Postgres."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
VIEWER = {"Authorization": f"Bearer {create_token('viewer')}"}


def current_row(stage="candidate", status="none"):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"pipeline_stage": stage, "status": status} if stage else None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def patch_state(row_stage="candidate", row_status="none"):
    conn, cursor = current_row(row_stage, row_status)
    db_patch = patch("gcrm.api.routers.api_organizations.db")
    set_patch = patch("gcrm.api.routers.api_organizations.set_organization_state")
    audit_patch = patch("gcrm.api.routers.api_organizations.log_audit")
    return conn, cursor, db_patch, set_patch, audit_patch


class TestOrganizationState:
    def move(self, body, headers=ADMIN, stage="candidate", status="none", contact_id=7):
        conn, cursor, db_p, set_p, audit_p = patch_state(stage, status)
        with db_p as mock_db, set_p as set_state, audit_p as audit:
            mock_db.return_value.__enter__.return_value = conn
            response = client.patch(f"/api/contacts/{contact_id}/state", json=body, headers=headers)
        return response, set_state, audit, cursor

    def test_a_stage_change_keeps_the_current_status(self):
        response, set_state, audit, _ = self.move({"pipeline_stage": "suspect"}, status="ready")
        assert response.status_code == 200
        assert response.json() == {"pipeline_stage": "suspect", "status": "ready", "typical": True}
        set_state.assert_called_once_with(7, pipeline_stage="suspect", status="ready")
        assert audit.call_args.args[2:] == ("contact.state_changed", "contact:7",
                                            "candidate/ready->suspect/ready")

    def test_a_status_change_keeps_the_current_stage(self):
        response, set_state, _, _ = self.move({"status": "meeting"}, stage="prospect", status="contacted")
        assert response.status_code == 200
        set_state.assert_called_once_with(7, pipeline_stage="prospect", status="meeting")

    def test_both_can_change_at_once(self):
        response, set_state, _, _ = self.move({"pipeline_stage": "opportunity", "status": "proposal"})
        assert response.json() == {"pipeline_stage": "opportunity", "status": "proposal", "typical": True}

    def test_an_unusual_pair_is_allowed_but_reported(self):
        response, set_state, _, _ = self.move({"pipeline_stage": "customer", "status": "proposal"})
        assert response.status_code == 200
        assert response.json()["typical"] is False  # the phone may warn; the server never blocks
        set_state.assert_called_once()

    @pytest.mark.parametrize("body", [{"pipeline_stage": "bogus"}, {"status": "cold"}, {"pipeline_stage": ""},
                                      {"status": ""}, {}, {"pipeline_stage": None, "status": None}])
    def test_unknown_or_empty_values_are_refused_not_replaced(self, body):
        response, set_state, _, _ = self.move(body)
        assert response.status_code == 400
        set_state.assert_not_called()

    def test_a_missing_or_deleted_organization_is_a_404(self):
        response, set_state, _, _ = self.move({"pipeline_stage": "suspect"}, stage=None)
        assert response.status_code == 404
        set_state.assert_not_called()

    def test_only_the_admin_may_change_state(self):
        response, set_state, _, _ = self.move({"pipeline_stage": "suspect"}, headers=VIEWER)
        assert response.status_code == 403
        set_state.assert_not_called()

    def test_a_login_is_required(self):
        response = client.patch("/api/contacts/7/state", json={"pipeline_stage": "suspect"})
        assert response.status_code in (401, 403)

    def test_deleted_organizations_are_not_changed(self):
        _, _, _, cursor = self.move({"pipeline_stage": "suspect"})
        assert "deleted_at IS NULL" in cursor.execute.call_args.args[0]


class TestPersonStage:
    def set_stage(self, body, headers=ADMIN, updated=True, person_id=5):
        stored = body.get("stage") if updated else None
        with patch("gcrm.api.routers.api_people.set_person_pipeline_stage",
                   return_value=(updated, stored)) as update, \
             patch("gcrm.api.routers.api_people.log_audit") as audit:
            response = client.patch(f"/api/people/{person_id}/stage", json=body, headers=headers)
        return response, update, audit

    def test_sets_the_stage(self):
        response, update, audit = self.set_stage({"stage": "prospect"})
        assert response.status_code == 200 and response.json() == {"pipeline_stage": "prospect"}
        update.assert_called_once_with(5, "prospect")
        assert audit.call_args.args[2:] == ("person.stage_changed", "person:5", "prospect")

    def test_null_clears_the_stage(self):
        response, update, audit = self.set_stage({"stage": None})
        assert response.status_code == 200 and response.json() == {"pipeline_stage": None}
        update.assert_called_once_with(5, None)
        assert audit.call_args.args[4] == "cleared"

    def test_an_unknown_stage_is_refused(self):
        response, update, _ = self.set_stage({"stage": "bogus"})
        assert response.status_code == 400
        update.assert_not_called()

    def test_a_missing_person_is_a_404(self):
        assert self.set_stage({"stage": "suspect"}, updated=False)[0].status_code == 404

    def test_the_stage_actually_stored_comes_back(self):
        """Clearing the stage of someone with an open next step leaves them a
        candidate (the next step needs a deal to live on) — the phone shows that."""
        with patch("gcrm.api.routers.api_people.set_person_pipeline_stage", return_value=(True, "candidate")), \
             patch("gcrm.api.routers.api_people.log_audit"):
            response = client.patch("/api/people/5/stage", json={"stage": None}, headers=ADMIN)
        assert response.json() == {"pipeline_stage": "candidate"}

    def test_only_the_admin_may_set_it(self):
        response, update, _ = self.set_stage({"stage": "suspect"}, headers=VIEWER)
        assert response.status_code == 403
        update.assert_not_called()

    def test_a_login_is_required(self):
        assert client.patch("/api/people/5/stage", json={"stage": "suspect"}).status_code in (401, 403)

    def test_the_persons_stage_comes_back_with_the_person(self):
        """The phone reads it from the normal detail response — nothing new to fetch."""
        row = {"id": 5, "name": "Ann", "pipeline_stage": "candidate"}
        with patch("gcrm.api.routers.api_people.get_person", return_value=row):
            assert client.get("/api/people/5", headers=ADMIN).json()["pipeline_stage"] == "candidate"
