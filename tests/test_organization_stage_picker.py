"""Changing a stage straight from the Organizations or People list: the row's
select posts to its deal (POST /deals/{id}) and comes back to the same filtered
list. The old POST /organizations/{id}/stage is gone (phase 5)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.tools.deal_records import DealNotFound

client = TestClient(main.app)


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def _post_stage(stage: str, next_url: str = "/organizations/?stage=suspect&page=2", error=None):
    deal = {"id": 41, "contact_id": 7, "person_id": None}
    with patch("gcrm.api.routers.deals.update_deal", return_value=deal, side_effect=error) as update:
        response = client.post("/deals/41", data={"stage": stage, "next": next_url}, follow_redirects=False)
    return response, update


def test_picking_a_stage_saves_only_the_stage_and_returns_to_the_same_list(admin_web):
    response, update = _post_stage("prospect")

    assert response.status_code == 303
    assert response.headers["location"] == "/organizations/?stage=suspect&page=2"
    update.assert_called_once_with(41, None, stage="prospect", status=None)  # None keeps the status


def test_an_unknown_stage_is_refused_and_nothing_is_written(admin_web):
    response, update = _post_stage("bogus")

    assert response.status_code == 400
    update.assert_not_called()


def test_a_missing_deal_is_a_404(admin_web):
    """Also a deal whose organization or person was deleted: get_deal hides it."""
    response, _ = _post_stage("customer", error=DealNotFound())

    assert response.status_code == 404


def test_an_offsite_next_url_does_not_redirect_away(admin_web):
    response, _ = _post_stage("customer", next_url="https://evil.example/")

    assert response.headers["location"] == "/organizations/"


def test_the_people_list_comes_back_to_itself(admin_web):
    response, _ = _post_stage("suspect", next_url="/people/?linkedin=1&stage=candidate")

    assert response.headers["location"] == "/people/?linkedin=1&stage=candidate"


def test_only_the_admin_may_change_a_stage():
    with patch("gcrm.api.routers.deals.update_deal") as update:
        response = client.post("/deals/41", data={"stage": "suspect"}, follow_redirects=False)
    assert response.status_code in (303, 307, 401, 403)
    update.assert_not_called()


def test_the_old_list_route_is_gone(admin_web):
    response = client.post("/organizations/7/stage", data={"stage": "prospect"}, follow_redirects=False)
    assert response.status_code in (404, 405)
