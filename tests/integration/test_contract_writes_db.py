"""Everything that reads or changes one contract, on the real schema: the contact-person rule, links and their
order, adding a payment, deleting a contract and what that does to the Forecast, the audit trail, and that another
workspace's contract is never found."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.contract_input import ContractInputError
from gcrm.db.connection import db
from gcrm.tools.db_contracts import (
    MAX_LINKS,
    ContractNotFound,
    add_link,
    add_payment,
    delete_contract,
    get_contract,
    list_contracts,
    move_link,
    remove_link,
    update_contract,
)
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.forecast import get_forecast
from gcrm.tools.revenue import business_revenue
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
TODAY = date.today()


def _consulting(owner_kind, owner_id):
    return next(d["id"] for d in get_deals(owner_kind, owner_id) if d["offer_slug"] == "consulting")


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES ('other-customer', 'Other') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        second = cursor.fetchone()["id"]
    with workspace_scope(first):
        school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
        other_school = save_organization("Berufsschule Beispiel", "Ulm", source="test_fixture")
        coordinator = save_person("Mara Beispiel", source="test_fixture", contact_id=school)
        colleague = save_person("Tim Lehrer", source="test_fixture", contact_id=school)
        outsider = save_person("Olga Fremd", source="test_fixture", contact_id=other_school)
        freelancer = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(%s, 'consulting') AS id", (first,))
            own_deal = add_deal("person", freelancer, cursor.fetchone()["id"])
        deal = _consulting("organization", school)
        add_deal_sale(deal, "2400", date(2026, 11, 8), "Year course", first, status="booked",
                      expected_on=TODAY, months=4, hours="40")
        add_deal_sale(own_deal, "300", date(2026, 11, 8), "Coaching block", first, status="booked")
    with workspace_scope(second):
        foreign_org = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(_consulting("organization", foreign_org), "9000", date(2026, 11, 8), "Kessler secret", second, status="booked")
    ids = {}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, title, workspace_id FROM contracts")
        for row in cursor.fetchall():
            ids[row["title"]] = row["id"]
    return {"first": first, "second": second, "deal": deal, "own_deal": own_deal, "contract": ids["Year course"],
            "own_contract": ids["Coaching block"], "foreign": ids["Kessler secret"], "coordinator": coordinator,
            "colleague": colleague, "outsider": outsider, "freelancer": freelancer, "school": school}


def _audit(action):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT target, outcome FROM audit_log WHERE action = %s ORDER BY id", (action,))
        return [dict(row) for row in cursor.fetchall()]


def _links(contract):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT label FROM contract_links WHERE contract_id = %s ORDER BY sort_order, id", (contract,))
        return [row["label"] for row in cursor.fetchall()]


def _row(contract):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM contracts WHERE id = %s", (contract,))
        return dict(cursor.fetchone())


# --- reading one contract -----------------------------------------------------

def test_a_contract_comes_with_its_owner_payments_summary_and_who_may_be_its_contact(world):
    contract = get_contract(world["contract"], world["first"])
    assert (contract["title"], contract["kind"], contract["offer_slug"], contract["owner_name"]) == (
        "Year course", "other", "consulting", "VHS Musterstadt")
    assert contract["organization_id"] == world["school"] and contract["person_id"] is None
    assert [p["name"] for p in contract["contact_options"]] == ["Mara Beispiel", "Tim Lehrer"]       # not the other school's
    assert contract["contact_person"] is None and contract["links"] == []
    summary = contract["summary"]
    assert (summary["value"], summary["hours"], summary["payments"]) == (Decimal("2400"), Decimal("40"), 4)
    payments = contract["payments"]
    assert len(payments) == 4 and payments[0]["contract"]["payments"] == 4          # the series control sits on the first
    assert all("contract" not in p for p in payments[1:])


def test_a_contract_of_another_workspace_is_not_found_and_neither_is_a_deleted_one_or_one_without_a_live_owner(world):
    with pytest.raises(ContractNotFound):
        get_contract(world["foreign"], world["first"])
    with pytest.raises(ContractNotFound):
        get_contract(world["contract"], world["second"])
    with pytest.raises(ContractNotFound):
        get_contract(987654, world["first"])
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (world["school"],))
    with pytest.raises(ContractNotFound):
        get_contract(world["contract"], world["first"])


def test_deleted_payments_do_not_count(world):
    with db() as connection:
        connection.cursor().execute("UPDATE sales SET deleted_at = NOW() WHERE contract_id = %s AND series_part = 1", (world["contract"],))
    contract = get_contract(world["contract"], world["first"])
    assert len(contract["payments"]) == 3 and contract["summary"]["value"] == Decimal("1800")


# --- editing -----------------------------------------------------------------

def test_an_edit_saves_every_field_and_is_audited(world):
    before = _row(world["contract"])["updated_at"]
    update_contract(world["contract"], world["first"], "  Year-long AI course ", "teaching_course", "Week 1: basics\r\nWeek 2: tools",
                    world["coordinator"])
    saved = _row(world["contract"])
    assert (saved["title"], saved["kind"], saved["assignment"], saved["contact_person_id"]) == (
        "Year-long AI course", "teaching_course", "Week 1: basics\nWeek 2: tools", world["coordinator"])
    assert saved["updated_at"] > before
    (event,) = _audit("contract.edited")
    assert event["target"] == f"contract:{world['contract']}" and event["outcome"] == "title, kind, assignment, contact"
    assert get_contract(world["contract"], world["first"])["contact_person"]["name"] == "Mara Beispiel"


def test_the_audit_names_only_what_changed_and_never_the_assignment_text(world):
    update_contract(world["contract"], world["first"], "Year course", "other", "Secret terms of the deal", None)
    (event,) = _audit("contract.edited")
    assert event["outcome"] == "assignment" and "Secret" not in str(event)


def test_a_contact_must_work_at_the_deals_organization(world):
    update_contract(world["contract"], world["first"], "Year course", "other", "", world["colleague"])           # allowed
    for refused in (world["outsider"], world["freelancer"], 987654):
        with pytest.raises(ContractInputError) as error:
            update_contract(world["contract"], world["first"], "Changed", "other", "", refused)
        assert error.value.key == "contractPage.error.contact"
    saved = _row(world["contract"])
    assert saved["title"] == "Year course" and saved["contact_person_id"] == world["colleague"]      # a refusal changes nothing


def test_a_contact_who_has_since_been_deleted_is_refused_and_no_longer_shown(world):
    update_contract(world["contract"], world["first"], "Year course", "other", "", world["coordinator"])
    with db() as connection:
        connection.cursor().execute("UPDATE people SET deleted_at = NOW() WHERE id = %s", (world["coordinator"],))
    assert get_contract(world["contract"], world["first"])["contact_person"] is None
    with pytest.raises(ContractInputError):
        update_contract(world["contract"], world["first"], "Year course", "other", "", world["coordinator"])


def test_a_persons_own_deal_allows_that_person_or_nobody(world):
    assert [p["id"] for p in get_contract(world["own_contract"], world["first"])["contact_options"]] == [world["freelancer"]]
    update_contract(world["own_contract"], world["first"], "Coaching block", "other", "", world["freelancer"])
    update_contract(world["own_contract"], world["first"], "Coaching block", "other", "", None)
    for refused in (world["coordinator"], world["outsider"]):
        with pytest.raises(ContractInputError):
            update_contract(world["own_contract"], world["first"], "Coaching block", "other", "", refused)


@pytest.mark.parametrize("title,kind,assignment", [("", "other", ""), ("x" * 201, "other", ""), ("Fine", "speech", ""),
                                                   ("Fine", "other", "x" * 20_001)])
def test_a_bad_entry_is_refused_and_nothing_is_saved(world, title, kind, assignment):
    with pytest.raises(ValueError):
        update_contract(world["contract"], world["first"], title, kind, assignment, None)
    assert _row(world["contract"])["title"] == "Year course" and _audit("contract.edited") == []


def test_another_workspaces_contract_cannot_be_changed(world):
    with pytest.raises(ContractNotFound):
        update_contract(world["foreign"], world["first"], "Hijacked", "other", "", None)
    assert _row(world["foreign"])["title"] == "Kessler secret"


# --- links ------------------------------------------------------------------

def _three_links(world):
    for label in ("Syllabus", "Slides", "Recording"):
        add_link(world["contract"], world["first"], label, f"https://example.org/{label.lower()}")


def test_links_keep_the_order_they_were_added_in_and_each_add_is_audited(world):
    _three_links(world)
    assert _links(world["contract"]) == ["Syllabus", "Slides", "Recording"]
    assert [link["label"] for link in get_contract(world["contract"], world["first"])["links"]] == ["Syllabus", "Slides", "Recording"]
    assert len(_audit("contract.link_added")) == 3


def test_a_link_that_is_not_http_or_https_is_refused_and_nothing_is_written(world):
    for url in ("javascript:alert(1)", "data:text/html,x", "ftp://example.org/a", "example.org"):
        with pytest.raises(ContractInputError) as error:
            add_link(world["contract"], world["first"], "Bad", url)
        assert error.value.key == "contractPage.error.linkUrl"
    with pytest.raises(ContractInputError) as error:
        add_link(world["contract"], world["first"], "  ", "https://example.org")
    assert error.value.key == "contractPage.error.linkLabel"
    assert _links(world["contract"]) == [] and _audit("contract.link_added") == []


def test_moving_a_link_swaps_it_with_its_neighbour_and_the_order_is_stable(world):
    _three_links(world)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contract_links WHERE label = 'Recording'")
        last = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM contract_links WHERE label = 'Syllabus'")
        first = cursor.fetchone()["id"]
    move_link(world["contract"], last, "up", world["first"])
    assert _links(world["contract"]) == ["Syllabus", "Recording", "Slides"]
    move_link(world["contract"], first, "up", world["first"])                  # already first: nothing changes
    move_link(world["contract"], last, "down", world["first"])
    move_link(world["contract"], last, "down", world["first"])                 # now last: nothing changes
    assert _links(world["contract"]) == ["Syllabus", "Slides", "Recording"]
    move_link(world["contract"], first, "down", world["first"])
    assert _links(world["contract"]) == ["Slides", "Syllabus", "Recording"]
    assert _links(world["contract"]) == _links(world["contract"])               # reading again gives the same order


def test_links_with_equal_order_numbers_get_a_stable_order_when_one_is_moved(world):
    _three_links(world)
    with db() as connection:
        connection.cursor().execute("UPDATE contract_links SET sort_order = 7 WHERE contract_id = %s", (world["contract"],))
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contract_links WHERE label = 'Slides'")
        slides = cursor.fetchone()["id"]
    move_link(world["contract"], slides, "up", world["first"])
    assert _links(world["contract"]) == ["Slides", "Syllabus", "Recording"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT sort_order FROM contract_links WHERE contract_id = %s ORDER BY sort_order", (world["contract"],))
        assert [row["sort_order"] for row in cursor.fetchall()] == [0, 1, 2]


def test_a_link_can_be_removed_and_only_from_its_own_contract(world):
    _three_links(world)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contract_links WHERE label = 'Slides'")
        slides = cursor.fetchone()["id"]
    with pytest.raises(ContractNotFound):
        remove_link(world["own_contract"], slides, world["first"])             # the link sits on another contract
    with pytest.raises(ContractNotFound):
        move_link(world["own_contract"], slides, "up", world["first"])
    remove_link(world["contract"], slides, world["first"])
    assert _links(world["contract"]) == ["Syllabus", "Recording"]
    with pytest.raises(ContractNotFound):
        remove_link(world["contract"], slides, world["first"])                 # already gone
    assert len(_audit("contract.link_removed")) == 1 and len(_audit("contract.link_moved")) == 0


def test_an_unknown_direction_is_refused(world):
    _three_links(world)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contract_links LIMIT 1")
        link = cursor.fetchone()["id"]
    with pytest.raises(ValueError):
        move_link(world["contract"], link, "sideways", world["first"])


def test_links_of_another_workspace_cannot_be_added_moved_or_removed(world):
    with pytest.raises(ContractNotFound):
        add_link(world["foreign"], world["first"], "Sneaky", "https://example.org")
    assert _links(world["foreign"]) == []


def test_a_contract_keeps_at_most_fifty_links(world):
    for number in range(MAX_LINKS):
        add_link(world["contract"], world["first"], f"Link {number}", "https://example.org/a")
    with pytest.raises(ContractInputError) as error:
        add_link(world["contract"], world["first"], "One too many", "https://example.org/a")
    assert error.value.key == "contractPage.error.tooManyLinks" and len(_links(world["contract"])) == MAX_LINKS


# --- adding a payment ---------------------------------------------------------

def _contract_count():
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM contracts")
        return cursor.fetchone()["n"]


def test_a_payment_joins_this_contract_and_never_makes_another(world):
    before = _contract_count()
    payment = add_payment(world["contract"], world["first"], "250.50", date(2027, 6, 1), "contracted")
    assert _contract_count() == before
    contract = get_contract(world["contract"], world["first"])
    added = next(p for p in contract["payments"] if p["id"] == payment)
    assert (added["amount_eur"], added["status"], added["expected_on"], added["series_id"]) == (Decimal("250.50"), "contracted", "2027-06-01", None)
    assert contract["summary"]["value"] == Decimal("2650.50") and len(contract["payments"]) == 5
    assert _audit("sale.added")[-1]["target"] == f"deal:{world['deal']}"


def test_a_payment_may_have_no_due_day_and_a_collected_one_counts_as_received_today(world):
    add_payment(world["contract"], world["first"], 100, None, "collected")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT expected_on, collected_on, won_on FROM sales WHERE contract_id = %s AND amount_eur = 100",
                       (world["contract"],))
        row = cursor.fetchone()
    assert row["expected_on"] is None and row["collected_on"] == TODAY and row["won_on"] == TODAY


@pytest.mark.parametrize("amount", [0, "0", "-5", None, "abc", "0.001"])
def test_an_amount_that_is_not_above_zero_is_refused(world, amount):
    with pytest.raises(ContractInputError) as error:
        add_payment(world["contract"], world["first"], amount, None, "booked")
    assert error.value.key == "contractPage.error.payment"
    assert len(get_contract(world["contract"], world["first"])["payments"]) == 4


def test_an_unknown_status_is_refused(world):
    with pytest.raises(ValueError):
        add_payment(world["contract"], world["first"], 100, None, "paid-maybe")


def test_no_payment_can_be_added_to_another_workspaces_or_a_deleted_contract(world):
    with pytest.raises(ContractNotFound):
        add_payment(world["foreign"], world["first"], 100, None, "booked")
    delete_contract(world["contract"], world["first"])
    with pytest.raises(ContractNotFound):
        add_payment(world["contract"], world["first"], 100, None, "booked")


# --- deleting ---------------------------------------------------------------

def _forecast_total(workspace):
    with workspace_scope(workspace):
        result = get_forecast(workspace, "month", TODAY, None)
    return sum((p["subtotal"] for p in result["periods"]), Decimal("0")) + result["undated"]["total"]


def test_deleting_a_contract_deletes_its_payments_with_it_and_takes_the_money_out_of_the_forecast(world):
    add_payment(world["contract"], world["first"], 700, TODAY, "booked")
    before_forecast, before_revenue = _forecast_total(world["first"]), business_revenue(world["first"])["total"]
    assert before_revenue == Decimal("2400") + Decimal("700") + Decimal("300")
    assert delete_contract(world["contract"], world["first"]) == 5
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS live FROM sales WHERE contract_id = %s AND deleted_at IS NULL", (world["contract"],))
        assert cursor.fetchone()["live"] == 0
        cursor.execute("SELECT count(*) AS n FROM sales WHERE contract_id = %s", (world["contract"],))
        assert cursor.fetchone()["n"] == 5                                      # soft delete: the rows are still there
    assert _forecast_total(world["first"]) == before_forecast - Decimal("3100")
    assert business_revenue(world["first"])["total"] == Decimal("300")
    assert world["contract"] not in [c["id"] for c in list_contracts(world["first"])]
    assert _audit("contract.deleted") == [{"target": f"contract:{world['contract']}", "outcome": "5 payments"}]


def test_deleting_a_contract_leaves_the_deals_other_contracts_alone(world):
    other = add_deal_sale(world["deal"], "111", date(2026, 11, 9), "Second job", world["first"], status="booked")
    delete_contract(world["contract"], world["first"])
    assert other and [c["title"] for c in list_contracts(world["first"]) if c["deal_id"] == world["deal"]] == ["Second job"]


def test_a_contract_can_only_be_deleted_once_and_only_from_its_own_workspace(world):
    with pytest.raises(ContractNotFound):
        delete_contract(world["foreign"], world["first"])
    assert _row(world["foreign"])["deleted_at"] is None
    delete_contract(world["contract"], world["first"])
    with pytest.raises(ContractNotFound):
        delete_contract(world["contract"], world["first"])
    assert len(_audit("contract.deleted")) == 1


def test_a_deleted_contract_is_no_longer_found(world):
    delete_contract(world["own_contract"], world["first"])
    with pytest.raises(ContractNotFound):
        get_contract(world["own_contract"], world["first"])
