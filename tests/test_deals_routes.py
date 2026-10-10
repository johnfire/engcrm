"""The Deals panel's forms, the Offers page and the mobile deal endpoints: what
they send to gcrm/tools/deal_records.py and db_offers.py, and what they refuse.
The deal logic itself runs against Postgres in tests/integration/test_deal_records_db.py."""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.tools.deal_records import DealNotFound

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
VIEWER = {"Authorization": f"Bearer {create_token('spectator')}"}

DEAL = {"id": 9, "offer_id": 2, "offer_slug": "learnwohl", "offer_name": "LearnWohl",
        "revenue_kind": "subscription", "offer_archived": False, "contact_id": 4, "person_id": None,
        "pipeline_stage": "prospect", "status": "contacted", "next_step": "Demo for Jamie",
        "next_step_date": "2020-01-31", "notes": None, "contact_person_id": 7, "contact_person_name": "Jamie"}


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def post(url, data):
    return client.post(url, data=data, follow_redirects=False)


class TestPanelForms:
    def test_adding_an_offer_returns_to_the_owners_page(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal", return_value=11) as add:
            response = post("/deals/new", {"owner": "organization", "owner_id": "4", "offer_id": "2"})
        assert response.status_code == 303 and response.headers["location"] == "/organizations/4"
        add.assert_called_once_with("organization", 4, 2, None)

    def test_an_unknown_owner_kind_or_offer_is_refused(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal") as add:
            assert post("/deals/new", {"owner": "workspace", "owner_id": "4", "offer_id": "2"}).status_code == 400
        add.assert_not_called()
        with patch("gcrm.api.routers.deals.add_deal", side_effect=DealNotFound()):
            assert post("/deals/new", {"owner": "person", "owner_id": "4", "offer_id": "99"}).status_code == 404

    def test_picking_a_stage_changes_only_the_stage(self, admin_web):
        with patch("gcrm.api.routers.deals.update_deal") as update:
            response = post("/deals/9", {"stage": "opportunity", "next": "/people/7"})
        assert response.headers["location"] == "/people/7"
        update.assert_called_once_with(9, None, stage="opportunity", status=None)

    def test_the_contact_person_is_set_and_cleared(self, admin_web):
        with patch("gcrm.api.routers.deals.update_deal") as update:
            post("/deals/9", {"stage": "prospect", "status": "contacted", "contact_person_id": "7"})
            post("/deals/9", {"stage": "prospect", "status": "contacted", "contact_person_id": "0"})
        assert update.call_args_list[0].kwargs["contact_person_id"] == 7
        assert update.call_args_list[1].kwargs["contact_person_id"] is None

    @pytest.mark.parametrize("data", [{"stage": "bogus"}, {"status": "bogus"}, {"contact_person_id": "x"}])
    def test_unknown_values_are_refused_before_anything_is_written(self, admin_web, data):
        with patch("gcrm.api.routers.deals.update_deal") as update:
            assert post("/deals/9", data).status_code == 400
        update.assert_not_called()

    def test_a_contact_person_from_elsewhere_is_refused(self, admin_web):
        with patch("gcrm.api.routers.deals.update_deal", side_effect=ValueError("must work there")):
            assert post("/deals/9", {"contact_person_id": "8"}).status_code == 400

    def test_next_step_set_and_done(self, admin_web):
        with patch("gcrm.api.routers.deals.set_deal_next_step") as setter:
            post("/deals/9/next-step", {"next_step": "Demo", "next_step_date": "2026-10-20"})
            post("/deals/9/next-step", {"next_step": "Demo", "next_step_date": "2026-10-20", "done": "1"})
        assert setter.call_args_list[0].args == (9, "Demo", date(2026, 10, 20), None)
        assert setter.call_args_list[1].args == (9, "", None, None)

    def test_removing_a_missing_deal_is_a_404(self, admin_web):
        with patch("gcrm.api.routers.deals.remove_deal", side_effect=DealNotFound()):
            assert post("/deals/9/remove", {}).status_code == 404

    def test_an_offsite_next_url_is_ignored(self, admin_web):
        with patch("gcrm.api.routers.deals.remove_deal"):
            response = post("/deals/9/remove", {"next": "https://evil.test/"})
        assert response.headers["location"] == "/organizations/"

    def test_a_form_without_the_contact_person_leaves_it_alone(self, admin_web):
        with patch("gcrm.api.routers.deals.update_deal") as update:
            post("/deals/9", {"stage": "prospect"})
        assert "contact_person_id" not in update.call_args.kwargs


class TestPanelOnThePage:
    def test_an_organization_shows_each_deal_and_offers_the_rest(self, admin_web):
        offers = [{"id": 1, "name": "Consulting"}, {"id": 2, "name": "LearnWohl"}, {"id": 3, "name": "LeGuild.art"}]
        organization = {"id": 4, "name": "Simmons Language School", "city": "Hannover", "country": "DE",
                        "source": "manual_web", "distance_km": None, "personal_priority": None}
        with patch("gcrm.api.routers.organizations.db") as mock_db, \
             patch("gcrm.api.routers.organizations.get_known_people_for_org",
                   return_value={"linked": [], "possible": []}), \
             patch("gcrm.api.routers.organizations.get_sales", return_value=[]), \
             patch("gcrm.api.routers.deals.get_deals", return_value=[DEAL]), \
             patch("gcrm.api.routers.deals.list_offers", return_value=offers), \
             patch("gcrm.api.routers.deals.contact_people", return_value=[{"id": 7, "name": "Jamie", "title": None}]):
            cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
            cursor.fetchone.side_effect = [organization, None]
            cursor.fetchall.return_value = []
            page = client.get("/organizations/4?lang=en").text
        assert "<h3>LearnWohl" in page and 'action="/deals/9"' in page
        assert '<option value="7" selected>Jamie</option>' in page
        assert "Demo for Jamie" in page and "next-step__due--overdue" in page
        # what is already pitched is not offered again
        add_form = page[page.index('action="/deals/new"'):]
        assert '<option value="1">Consulting</option>' in add_form and ">LearnWohl<" not in add_form


class TestOffersPage:
    def test_lists_offers_with_their_deal_counts(self, admin_web):
        offers = [{"id": 1, "slug": "consulting", "name": "Consulting", "website": None,
                   "revenue_kind": "one_off", "sort_order": 10, "archived": False, "deals": 312},
                  {"id": 5, "slug": "old", "name": "Old thing", "website": None,
                   "revenue_kind": "subscription", "sort_order": 50, "archived": True, "deals": 2}]
        with patch("gcrm.api.routers.offers.list_offers", return_value=offers):
            page = client.get("/offers/?lang=en").text
        assert 'value="Consulting"' in page and "312" in page
        assert "Restore" in page and 'action="/offers/5/archive"' in page

    def test_adding_and_a_bad_name(self, admin_web):
        with patch("gcrm.api.routers.offers.create_offer") as create:
            assert post("/offers/", {"name": "LearnWohl", "revenue_kind": "subscription"}).headers["location"] == "/offers/"
        create.assert_called_once_with(None, "LearnWohl", "", "subscription")
        with patch("gcrm.api.routers.offers.create_offer", side_effect=ValueError()):
            assert post("/offers/", {"name": ""}).headers["location"] == "/offers/?error=invalid"

    def test_move_needs_a_direction_and_an_offer(self, admin_web):
        with patch("gcrm.api.routers.offers.move_offer", side_effect=ValueError()):
            assert post("/offers/1/move", {"direction": "sideways"}).status_code == 400
        with patch("gcrm.api.routers.offers.move_offer", return_value=False):
            assert post("/offers/9/move", {"direction": "up"}).status_code == 404


class TestMobileEndpoints:
    def test_offers_for_the_phone(self):
        with patch("gcrm.api.routers.api_deals.list_offers",
                   return_value=[{"id": 1, "slug": "consulting", "name": "Consulting", "website": None,
                                  "revenue_kind": "one_off", "sort_order": 10, "archived": False, "deals": 3}]):
            assert client.get("/api/offers", headers=ADMIN).json() == [
                {"id": 1, "slug": "consulting", "name": "Consulting", "website": None, "revenue_kind": "one_off"}]

    def test_create_change_and_remove(self):
        with patch("gcrm.api.routers.api_deals.add_deal", return_value=11) as add:
            response = client.post("/api/deals", headers=ADMIN,
                                   json={"owner": "person", "owner_id": 7, "offer_id": 2, "stage": "prospect"})
        assert response.status_code == 201 and response.json() == {"id": 11}
        add.assert_called_once_with("person", 7, 2, None, "prospect", "none")
        with patch("gcrm.api.routers.api_deals.update_deal", return_value=DEAL) as update:
            client.patch("/api/deals/9", headers=ADMIN, json={"status": "not_interested"})
            client.patch("/api/deals/9", headers=ADMIN, json={"contact_person_id": None})
        assert update.call_args_list[0].kwargs == {"stage": None, "status": "not_interested"}
        assert update.call_args_list[1].kwargs == {"stage": None, "status": None, "contact_person_id": None}
        with patch("gcrm.api.routers.api_deals.remove_deal", side_effect=DealNotFound()):
            assert client.delete("/api/deals/9", headers=ADMIN).status_code == 404

    def test_bad_values_and_viewers_are_refused(self):
        assert client.post("/api/deals", headers=ADMIN,
                           json={"owner": "person", "owner_id": 7, "offer_id": 2, "stage": "bogus"}).status_code == 400
        assert client.patch("/api/deals/9", headers=ADMIN, json={"status": "bogus"}).status_code == 400
        assert client.patch("/api/deals/9", headers=VIEWER, json={"status": "none"}).status_code == 403

    def test_next_step(self):
        with patch("gcrm.api.routers.api_deals.set_deal_next_step",
                   return_value={"next_step": "Demo", "next_step_date": date(2026, 10, 20), "logged": True}) as setter:
            response = client.put("/api/deals/9/next-step", headers=ADMIN,
                                  json={"next_step": "Demo", "next_step_date": "2026-10-20"})
        assert response.json()["next_step_date"] == "2026-10-20"
        setter.assert_called_once_with(9, "Demo", date(2026, 10, 20), None)
