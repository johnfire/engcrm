"""The Deals panel's forms, the Offers page and the mobile deal endpoints: what
they send to gcrm/tools/deal_records.py and db_offers.py, and what they refuse.
The deal logic itself runs against Postgres in tests/integration/test_deal_records_db.py."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.tools.deal_offer_changes import DealOfferConflict
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


def test_switching_an_existing_offer_preserves_the_deal_and_returns_to_its_page(admin_web):
    with patch('gcrm.api.routers.deals.change_deal_offer', return_value=DEAL) as change:
        response = post('/deals/9/offer', {'offer_id': '5', 'next': '/organizations/4'})
    change.assert_called_once_with(9, 5, None)
    assert response.status_code == 303 and response.headers['location'] == '/organizations/4'


@pytest.mark.parametrize('failure,status', [(DealNotFound(), 404), (DealOfferConflict('Already pitched'), 409)])
def test_offer_switch_errors_leave_the_existing_deal_alone(admin_web, failure, status):
    with patch('gcrm.api.routers.deals.change_deal_offer', side_effect=failure):
        assert post('/deals/9/offer', {'offer_id': '5'}).status_code == status


def test_offer_switch_requires_an_admin_on_the_api():
    with patch('gcrm.api.routers.api_deals.change_deal_offer') as change:
        response = client.patch('/api/deals/9/offer', headers=VIEWER, json={'offer_id': 5})
    assert response.status_code == 403
    change.assert_not_called()


def test_offer_switch_rejects_invalid_ids_before_writing(admin_web):
    with patch('gcrm.api.routers.deals.change_deal_offer') as change:
        assert post('/deals/9/offer', {'offer_id': '0'}).status_code == 422
    change.assert_not_called()


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
        add_form = add_form[:add_form.index("</form>")]
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


class TestSubscriptionRoutes:
    def test_the_card_starts_and_ends_a_subscription(self, admin_web):
        with patch("gcrm.api.routers.deals.start_subscription") as start:
            response = post("/deals/9/subscription", {"amount_eur_month": "49,50", "started_on": "2026-10-01",
                                                      "next": "/organizations/4"})
        assert response.headers["location"] == "/organizations/4"
        assert start.call_args.args[:3] == (9, Decimal("49.50"), date(2026, 10, 1))
        with patch("gcrm.api.routers.deals.end_subscription", return_value=False):
            assert post("/deals/9/subscription/end", {"ended_on": "2026-12-31"}).status_code == 404

    def test_bad_amounts_and_overlaps_are_refused(self, admin_web):
        assert post("/deals/9/subscription", {"amount_eur_month": "lots", "started_on": "2026-10-01"}).status_code == 400
        with patch("gcrm.api.routers.deals.start_subscription", side_effect=ValueError("overlap")):
            assert post("/deals/9/subscription", {"amount_eur_month": "49", "started_on": "2026-10-01"}).status_code == 400

    def test_the_phone_records_sales_and_subscriptions(self):
        with patch("gcrm.api.routers.api_deals.start_subscription", return_value=3) as start:
            response = client.post("/api/deals/9/subscription", headers=ADMIN,
                                   json={"amount_eur_month": "19", "started_on": "2026-10-01"})
        assert response.status_code == 201 and start.call_args.args[:3] == (9, Decimal("19"), date(2026, 10, 1))
        with patch("gcrm.api.routers.api_deals.add_deal_sale", side_effect=ValueError("a person's deal")):
            assert client.post("/api/deals/9/sales", headers=ADMIN,
                               json={"amount_eur": "100", "won_on": "2026-10-05"}).status_code == 400
        assert client.post("/api/deals/9/subscription", headers=VIEWER,
                           json={"amount_eur_month": "19", "started_on": "2026-10-01"}).status_code == 403


class TestSaleStatus:
    """A sale is booked, contracted, collected or cancelled; the web forms and the phone say which."""

    def test_the_deal_card_records_a_sale_with_its_status_and_expected_day(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            response = post("/deals/9/sales", {"amount_eur": "2400,50", "won_on": "2026-11-03",
                                                "description": "AI course", "status": "booked",
                                                "expected_on": "20.01.2027", "next": "/people/4"})
        assert response.headers["location"] == "/people/4"
        args, kwargs = add.call_args
        assert args[:4] == (9, Decimal("2400.50"), date(2026, 11, 3), "AI course")
        assert kwargs["status"] == "booked" and kwargs["expected_on"] == date(2027, 1, 20)

    def test_a_blank_expected_day_is_none_and_nonsense_is_refused(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            post("/deals/9/sales", {"amount_eur": "100", "won_on": "2026-11-03", "status": "booked",
                                    "expected_on": ""})
        assert add.call_args.kwargs["expected_on"] is None
        assert post("/deals/9/sales", {"amount_eur": "lots", "won_on": "2026-11-03"}).status_code == 400
        with patch("gcrm.api.routers.deals.add_deal_sale", side_effect=ValueError("unknown sale status")):
            assert post("/deals/9/sales", {"amount_eur": "1", "won_on": "2026-11-03",
                                            "status": "paid"}).status_code == 400

    def test_moving_a_sale_along_passes_the_day_the_money_came_in(self, admin_web):
        with patch("gcrm.api.routers.deals.set_sale_status", return_value=True) as move:
            response = post("/deals/9/sales/5/status", {"status": "collected", "collected_on": "12.11.2026",
                                                         "next": "/organizations/4"})
        assert response.headers["location"] == "/organizations/4"
        assert move.call_args.args[:3] == (9, 5, "collected")
        assert move.call_args.kwargs["collected_on"] == date(2026, 11, 12)
        with patch("gcrm.api.routers.deals.set_sale_status", return_value=False):
            assert post("/deals/9/sales/5/status", {"status": "cancelled"}).status_code == 404
        with patch("gcrm.api.routers.deals.set_sale_status", side_effect=ValueError("bad")):
            assert post("/deals/9/sales/5/status", {"status": "paid"}).status_code == 400

    def test_a_sale_can_be_deleted_from_the_deal_card(self, admin_web):
        with patch("gcrm.api.routers.deals.delete_deal_sale", return_value=True):
            assert post("/deals/9/sales/5/delete", {"next": "/people/4"}).headers["location"] == "/people/4"
        with patch("gcrm.api.routers.deals.delete_deal_sale", return_value=False):
            assert post("/deals/9/sales/5/delete", {}).status_code == 404

    def test_the_phone_sends_a_status_and_moves_sales_along(self):
        with patch("gcrm.api.routers.api_deals.add_deal_sale", return_value=3) as add:
            response = client.post("/api/deals/9/sales", headers=ADMIN, json={
                "amount_eur": "100", "won_on": "2026-11-05", "status": "booked", "expected_on": "2027-01-20"})
        assert response.status_code == 201
        assert add.call_args.kwargs["status"] == "booked" and add.call_args.kwargs["expected_on"] == date(2027, 1, 20)
        with patch("gcrm.api.routers.api_deals.set_sale_status", return_value=True) as move:
            moved = client.patch("/api/deals/9/sales/3", headers=ADMIN,
                                 json={"status": "collected", "collected_on": "2026-11-12"})
        assert moved.status_code == 200 and move.call_args.args[:3] == (9, 3, "collected")
        assert move.call_args.kwargs["collected_on"] == date(2026, 11, 12)
        assert client.patch("/api/deals/9/sales/3", headers=VIEWER, json={"status": "collected"}).status_code == 403
        with patch("gcrm.api.routers.api_deals.set_sale_status", return_value=False):
            assert client.patch("/api/deals/9/sales/3", headers=ADMIN, json={"status": "booked"}).status_code == 404
        with patch("gcrm.api.routers.api_deals.set_sale_status", side_effect=ValueError("unknown")):
            assert client.patch("/api/deals/9/sales/3", headers=ADMIN, json={"status": "x"}).status_code == 400


class TestPaymentSchedules:
    """A contract paid over months: the forms send how many, and move the whole contract."""

    def test_the_deal_form_sends_the_number_of_monthly_payments(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            post("/deals/9/sales", {"amount_eur": "2400", "won_on": "2026-11-08", "status": "booked",
                                    "expected_on": "01.02.2027", "months": "4"})
        assert add.call_args.kwargs["months"] == 4 and add.call_args.kwargs["expected_on"] == date(2027, 2, 1)

    def test_one_payment_is_the_default(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            post("/deals/9/sales", {"amount_eur": "100", "won_on": "2026-11-08"})
        assert add.call_args.kwargs["months"] == 1

    def test_a_schedule_the_server_refuses_is_a_400(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", side_effect=ValueError("needs the first due day")):
            assert post("/deals/9/sales", {"amount_eur": "100", "won_on": "2026-11-08", "months": "3"}).status_code == 400

    def test_the_whole_contract_moves_together(self, admin_web):
        with patch("gcrm.api.routers.deals.set_series_status", return_value=3) as move:
            response = post("/deals/9/series/6f1c2f1e-0a5b-4b7e-9a39-0c1f2d3e4a5b/status",
                            {"status": "contracted", "next": "/organizations/4"})
        assert response.headers["location"] == "/organizations/4"
        assert move.call_args.args[:3] == (9, "6f1c2f1e-0a5b-4b7e-9a39-0c1f2d3e4a5b", "contracted")
        with patch("gcrm.api.routers.deals.set_series_status", return_value=0):
            assert post("/deals/9/series/6f1c2f1e-0a5b-4b7e-9a39-0c1f2d3e4a5b/status", {"status": "booked"}).status_code == 404
        with patch("gcrm.api.routers.deals.set_series_status", side_effect=ValueError("collected")):
            assert post("/deals/9/series/6f1c2f1e-0a5b-4b7e-9a39-0c1f2d3e4a5b/status", {"status": "collected"}).status_code == 400

    def test_a_malformed_contract_id_is_a_404_before_touching_anything(self, admin_web):
        with patch("gcrm.api.routers.deals.set_series_status") as move:
            assert post("/deals/9/series/not-a-uuid/status", {"status": "booked"}).status_code == 404
        move.assert_not_called()

    def test_the_phone_api_takes_months_and_moves_a_contract(self):
        with patch("gcrm.api.routers.api_deals.add_deal_sale", return_value=3) as add:
            response = client.post("/api/deals/9/sales", headers=ADMIN, json={
                "amount_eur": "2400", "won_on": "2026-11-08", "status": "booked", "expected_on": "2027-02-01", "months": 4})
        assert response.status_code == 201 and add.call_args.kwargs["months"] == 4
        with patch("gcrm.api.routers.api_deals.set_series_status", return_value=3) as move:
            moved = client.patch("/api/deals/9/series/6f1c2f1e-0a5b-4b7e-9a39-0c1f2d3e4a5b", headers=ADMIN,
                                 json={"status": "cancelled"})
        assert moved.status_code == 200 and moved.json()["changed"] == 3 and move.call_args.args[2] == "cancelled"
        assert client.patch("/api/deals/9/series/6f1c2f1e-0a5b-4b7e-9a39-0c1f2d3e4a5b", headers=VIEWER,
                            json={"status": "cancelled"}).status_code == 403


class TestOneTimeOrMonthly:
    """The Sales form asks "one-time or monthly"; for monthly the amount typed is per month."""

    def test_monthly_means_the_amount_is_per_month_and_the_contract_is_amount_times_months(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            post("/deals/9/sales", {"amount_eur": "500", "won_on": "2026-11-08", "status": "booked",
                                    "expected_on": "01.02.2027", "schedule": "monthly", "months": "6"})
        assert add.call_args.args[1] == Decimal("3000") and add.call_args.kwargs["months"] == 6

    def test_one_time_ignores_the_months_box(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            post("/deals/9/sales", {"amount_eur": "500", "won_on": "2026-11-08", "schedule": "one", "months": "6"})
        assert add.call_args.args[1] == Decimal("500") and add.call_args.kwargs["months"] == 1

    def test_an_older_form_without_the_choice_still_means_the_total_split_over_months(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale", return_value=3) as add:
            post("/deals/9/sales", {"amount_eur": "2400", "won_on": "2026-11-08", "expected_on": "01.02.2027", "months": "4"})
        assert add.call_args.args[1] == Decimal("2400") and add.call_args.kwargs["months"] == 4

    @pytest.mark.parametrize("months", ["1", "0", "61", "-2"])
    def test_monthly_needs_two_to_sixty_months(self, admin_web, months):
        with patch("gcrm.api.routers.deals.add_deal_sale") as add:
            response = post("/deals/9/sales", {"amount_eur": "500", "won_on": "2026-11-08", "schedule": "monthly",
                                               "expected_on": "01.02.2027", "months": months})
        assert response.status_code == 400
        add.assert_not_called()

    def test_an_unknown_choice_is_refused(self, admin_web):
        with patch("gcrm.api.routers.deals.add_deal_sale") as add:
            assert post("/deals/9/sales", {"amount_eur": "5", "won_on": "2026-11-08", "schedule": "weekly"}).status_code == 400
        add.assert_not_called()


class TestDueDay:
    """Setting or changing a sale's due day from the sale row."""

    def test_the_form_sends_the_day_and_returns_to_the_page(self, admin_web):
        with patch("gcrm.api.routers.deals.set_sale_due_day", return_value=1) as setter:
            response = post("/deals/9/sales/5/due-day", {"due_on": "15.02.2027", "next": "/organizations/4"})
        assert response.headers["location"] == "/organizations/4"
        assert setter.call_args.args[:3] == (9, 5, date(2027, 2, 15))

    def test_a_day_that_cannot_be_read_or_is_missing_is_a_400_and_changes_nothing(self, admin_web):
        with patch("gcrm.api.routers.deals.set_sale_due_day") as setter:
            assert post("/deals/9/sales/5/due-day", {"due_on": "someday"}).status_code == 400
            assert post("/deals/9/sales/5/due-day", {"due_on": ""}).status_code == 400
        setter.assert_not_called()

    def test_a_sale_that_cannot_be_changed_is_a_404(self, admin_web):
        with patch("gcrm.api.routers.deals.set_sale_due_day", return_value=0):
            assert post("/deals/9/sales/5/due-day", {"due_on": "15.02.2027"}).status_code == 404
        with patch("gcrm.api.routers.deals.set_sale_due_day", side_effect=DealNotFound()):
            assert post("/deals/9/sales/5/due-day", {"due_on": "15.02.2027"}).status_code == 404
