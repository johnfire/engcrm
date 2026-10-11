"""Where an organization or a person stands in the pipeline, on the phone: since
phase 5 every change goes to a deal (PATCH /api/deals/{id}); the old
PATCH /api/contacts/{id}/state and PATCH /api/people/{id}/stage are gone. DB is
mocked — runs without Postgres. The deal logic itself runs against Postgres in
tests/integration/test_deal_records_db.py."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.tools.deal_records import DealNotFound

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
VIEWER = {"Authorization": f"Bearer {create_token('viewer')}"}

STORED = {"id": 9, "offer_slug": "consulting", "pipeline_stage": "suspect", "status": "ready"}


def test_the_old_stage_endpoints_are_gone():
    """The app before phase 4 used them. They must not quietly come back and
    write around the deals."""
    assert client.patch("/api/contacts/7/state", json={"pipeline_stage": "suspect"},
                        headers=ADMIN).status_code in (404, 405)
    assert client.patch("/api/people/5/stage", json={"stage": "suspect"}, headers=ADMIN).status_code in (404, 405)


class TestDealStage:
    def change(self, body, headers=ADMIN, stored=STORED, error=None):
        with patch("gcrm.api.routers.api_deals.update_deal", return_value=stored, side_effect=error) as update:
            response = client.patch("/api/deals/9", json=body, headers=headers)
        return response, update

    def test_a_stage_change_leaves_the_status_and_the_stored_deal_comes_back(self):
        response, update = self.change({"stage": "suspect"})
        assert response.status_code == 200 and response.json() == STORED
        assert update.call_args.kwargs == {"stage": "suspect", "status": None}  # None keeps the status

    def test_a_status_change_leaves_the_stage(self):
        _, update = self.change({"status": "meeting"})
        assert update.call_args.kwargs == {"stage": None, "status": "meeting"}

    def test_an_unusual_pair_is_allowed(self):
        """The phone marks it (isTypicalPair); the server never blocks it."""
        response, update = self.change({"stage": "customer", "status": "proposal"})
        assert response.status_code == 200
        assert update.call_args.kwargs == {"stage": "customer", "status": "proposal"}

    @pytest.mark.parametrize("body", [{"stage": "bogus"}, {"status": "cold"}, {"stage": ""}, {"status": ""}])
    def test_unknown_or_empty_values_are_refused_not_replaced(self, body):
        response, update = self.change(body)
        assert response.status_code == 400
        update.assert_not_called()

    def test_a_missing_deal_or_one_of_a_deleted_organization_is_a_404(self):
        assert self.change({"stage": "suspect"}, error=DealNotFound())[0].status_code == 404

    def test_only_the_admin_may_change_it(self):
        response, update = self.change({"stage": "suspect"}, headers=VIEWER)
        assert response.status_code == 403
        update.assert_not_called()

    def test_a_login_is_required(self):
        response, update = self.change({"stage": "suspect"}, headers={})
        assert response.status_code in (401, 403)
        update.assert_not_called()


class TestPersonDetail:
    def test_the_persons_stage_comes_back_with_the_person(self):
        """The phone reads it from the normal detail response — nothing new to fetch."""
        row = {"id": 5, "name": "Ann", "pipeline_stage": "candidate"}
        with patch("gcrm.api.routers.api_people.get_person", return_value=row):
            assert client.get("/api/people/5", headers=ADMIN).json()["pipeline_stage"] == "candidate"
