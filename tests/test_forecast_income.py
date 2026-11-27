"""Which Forecast money the calculator counts, and as what."""
from decimal import Decimal

from gcrm.tools.forecast_income import summarise

D = Decimal


def row(contract_id, kind, eur, status="booked", undated=False, title="Contract", customer="Customer", n=1):
    return {"contract_id": contract_id, "title": title, "customer": customer, "kind": kind,
            "status": status, "undated": undated, "eur": D(eur), "n": n}


def test_teaching_courses_are_teaching_and_consulting_and_workshops_are_taxable():
    income = summarise([row(1, "teaching_course", "1000"), row(2, "consulting", "200"),
                        row(3, "workshop", "30")], possible=D(0), possible_as="consulting")
    assert income.teaching == D("1000")
    assert income.consulting == D("230")


def test_contracts_marked_other_are_listed_but_not_counted():
    income = summarise([row(1, "other", "500", title="Mystery"), row(2, "teaching_course", "10")],
                       possible=D(0), possible_as="consulting")
    assert (income.teaching, income.consulting) == (D("10"), D("0"))
    assert [(line.title, line.eur) for line in income.unclassified] == [("Mystery", D("500"))]
    assert [line.contract_id for line in income.lines] == [2]


def test_money_without_a_due_day_cannot_be_put_in_a_year():
    income = summarise([row(1, "teaching_course", "700", undated=True, n=2),
                        row(1, "teaching_course", "100")], possible=D(0), possible_as="consulting")
    assert income.teaching == D("100")
    assert (income.undated_total, income.undated_count) == (D("700"), 2)


def test_one_line_per_contract_adds_up_its_statuses():
    income = summarise([row(1, "teaching_course", "100", status="collected"),
                        row(1, "teaching_course", "300", status="booked", n=3)],
                       possible=D(0), possible_as="consulting")
    assert [(line.contract_id, line.eur, line.count) for line in income.lines] == [(1, D("400"), 4)]


def test_possible_new_sales_count_as_the_chosen_kind():
    taxable = summarise([], possible=D("900"), possible_as="consulting")
    teaching = summarise([], possible=D("900"), possible_as="teaching")
    assert (taxable.consulting, taxable.teaching, taxable.possible) == (D("900"), D("0"), D("900"))
    assert (teaching.consulting, teaching.teaching) == (D("0"), D("900"))
