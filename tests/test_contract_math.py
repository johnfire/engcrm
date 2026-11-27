"""What a contract is worth, when it runs, and which section of the list it belongs in.

Everything is worked out from the contract's payments (its sales), never stored, so the page and the
Forecast read the same rows. Pure functions: no database."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from gcrm.contract_math import (
    SORT_KEYS,
    contract_summary,
    group_by_timing,
    sort_contracts,
    timing,
    totals,
)

D = Decimal
TODAY = date(2026, 11, 27)


def pay(amount="100", status="booked", hours=None, won_on=date(2026, 5, 1), expected_on=None, collected_on=None,
        work_from=None, work_to=None):
    return {"amount_eur": D(amount), "status": status, "hours": None if hours is None else D(hours),
            "won_on": won_on, "expected_on": expected_on, "collected_on": collected_on,
            "work_from": work_from, "work_to": work_to}


def contract(*payments, title="A contract", customer="Customer", kind="other"):
    return {"id": 1, "title": title, "owner_name": customer, "kind": kind, "summary": contract_summary(list(payments))}


# --- the money ---------------------------------------------------------------

def test_value_is_the_sum_of_the_payments_and_collected_plus_open_is_the_value():
    summary = contract_summary([pay("600", "collected", collected_on=date(2026, 6, 1)), pay("600"), pay("300", "contracted")])
    assert summary["value"] == D("1500")
    assert summary["collected"] == D("600") and summary["open"] == D("900")
    assert summary["collected"] + summary["open"] == summary["value"]


def test_a_cancelled_payment_is_left_out_of_everything():
    summary = contract_summary([pay("600", "collected", collected_on=date(2026, 6, 1)), pay("900", "cancelled", hours="10")])
    assert (summary["value"], summary["collected"], summary["open"], summary["hours"]) == (D("600"), D("600"), D("0"), None)
    assert summary["cancelled"] is False


def test_hours_are_the_sum_of_the_hours_recorded_and_none_when_none_are():
    assert contract_summary([pay(hours="10"), pay(hours="2.5"), pay()])["hours"] == D("12.5")
    assert contract_summary([pay(), pay()])["hours"] is None


def test_the_rate_is_value_over_hours_and_only_when_there_are_hours():
    summary = contract_summary([pay("1000", hours="8"), pay("500")])
    assert summary["rate"] == D("187.50")          # 1500 over 8 hours: payments without hours still count in the value
    assert contract_summary([pay("1000")])["rate"] is None


def test_a_contract_with_no_payments_is_empty_not_a_crash():
    summary = contract_summary([])
    assert (summary["value"], summary["collected"], summary["open"]) == (D("0"), D("0"), D("0"))
    assert (summary["hours"], summary["rate"], summary["start"], summary["end"]) == (None, None, None, None)
    assert summary["cancelled"] is False and summary["payments"] == 0
    assert timing(summary, TODAY) == "finished"


def test_a_contract_whose_every_payment_is_cancelled_is_cancelled_and_worth_nothing():
    summary = contract_summary([pay("600", "cancelled"), pay("600", "cancelled")])
    assert summary["cancelled"] is True and summary["value"] == D("0") and summary["open"] == D("0")


# --- when it runs: the work window, else the due days, else the days it was won ----

def test_the_work_window_gives_the_start_and_the_end():
    summary = contract_summary([pay(work_from=date(2026, 9, 1), work_to=date(2026, 12, 18), expected_on=date(2027, 3, 1)),
                                pay(work_from=date(2026, 10, 1), work_to=date(2027, 1, 31))])
    assert (summary["start"], summary["end"]) == (date(2026, 9, 1), date(2027, 1, 31))      # due days are ignored


def test_without_a_work_window_the_due_days_give_the_dates():
    summary = contract_summary([pay(expected_on=date(2027, 2, 1), won_on=date(2026, 1, 1)),
                                pay(expected_on=date(2027, 5, 1), won_on=date(2026, 1, 2))])
    assert (summary["start"], summary["end"]) == (date(2027, 2, 1), date(2027, 5, 1))


def test_without_a_work_window_or_due_days_the_days_it_was_won_give_the_dates():
    summary = contract_summary([pay(won_on=date(2026, 3, 9)), pay(won_on=date(2026, 4, 2))])
    assert (summary["start"], summary["end"]) == (date(2026, 3, 9), date(2026, 4, 2))


def test_a_one_off_with_nothing_but_a_won_day_starts_and_ends_on_it():
    summary = contract_summary([pay(won_on=date(2026, 3, 9), status="collected", collected_on=date(2026, 3, 20))])
    assert (summary["start"], summary["end"]) == (date(2026, 3, 9), date(2026, 3, 9))


def test_payments_that_mix_dated_and_undated_ones_use_the_dated_ones_at_the_best_level():
    # no work window anywhere: two payments have a due day and one does not; the undated one is not a gap
    due_days = contract_summary([pay(expected_on=date(2027, 1, 1)), pay(), pay(expected_on=date(2027, 3, 1))])
    assert (due_days["start"], due_days["end"]) == (date(2027, 1, 1), date(2027, 3, 1))
    # a work window on only some payments: the window decides, the others' due days are not mixed in
    some_windows = contract_summary([pay(work_from=date(2026, 9, 1), work_to=date(2026, 9, 30)), pay(expected_on=date(2030, 1, 1)),
                                     pay(work_from=date(2026, 11, 1), work_to=date(2026, 12, 15))])
    assert (some_windows["start"], some_windows["end"]) == (date(2026, 9, 1), date(2026, 12, 15))


def test_cancelled_payments_do_not_stretch_the_dates():
    summary = contract_summary([pay(expected_on=date(2027, 1, 1)), pay(expected_on=date(2030, 1, 1), status="cancelled")])
    assert (summary["start"], summary["end"]) == (date(2027, 1, 1), date(2027, 1, 1))


def test_a_cancelled_contract_still_has_dates_to_sort_by():
    summary = contract_summary([pay(expected_on=date(2027, 1, 1), status="cancelled"), pay(expected_on=date(2027, 4, 1), status="cancelled")])
    assert (summary["start"], summary["end"]) == (date(2027, 1, 1), date(2027, 4, 1))


# --- which section ---------------------------------------------------------

def _running(start, end):
    return contract_summary([pay(work_from=start, work_to=end)])


def test_a_contract_that_ends_today_is_still_running():
    assert timing(_running(TODAY - timedelta(days=30), TODAY), TODAY) == "running"


def test_a_contract_that_starts_today_is_running():
    assert timing(_running(TODAY, TODAY + timedelta(days=30)), TODAY) == "running"


def test_a_contract_that_starts_tomorrow_is_upcoming():
    assert timing(_running(TODAY + timedelta(days=1), TODAY + timedelta(days=30)), TODAY) == "upcoming"


def test_a_contract_that_ended_yesterday_is_finished():
    assert timing(_running(TODAY - timedelta(days=30), TODAY - timedelta(days=1)), TODAY) == "finished"


def test_a_cancelled_contract_is_finished_whatever_its_dates():
    summary = contract_summary([pay(status="cancelled", work_from=TODAY - timedelta(days=5), work_to=TODAY + timedelta(days=5))])
    assert timing(summary, TODAY) == "finished"


def test_sections_are_sorted_running_by_soonest_end_upcoming_by_soonest_start_finished_by_latest_end():
    def at(title, start, end):
        return contract(pay(work_from=start, work_to=end), title=title)
    contracts = [
        at("run-late", date(2026, 1, 1), date(2027, 6, 1)), at("run-soon", date(2026, 1, 1), date(2026, 12, 1)),
        at("up-late", date(2027, 5, 1), date(2027, 6, 1)), at("up-soon", date(2027, 1, 1), date(2027, 6, 1)),
        at("done-old", date(2025, 1, 1), date(2025, 2, 1)), at("done-new", date(2026, 1, 1), date(2026, 3, 1)),
        contract(title="empty"),
        contract(pay(status="cancelled", work_from=date(2026, 1, 1), work_to=date(2026, 12, 31)), title="cancelled"),
    ]
    groups = group_by_timing(contracts, TODAY)
    assert [c["title"] for c in groups["running"]] == ["run-soon", "run-late"]
    assert [c["title"] for c in groups["upcoming"]] == ["up-soon", "up-late"]
    assert [c["title"] for c in groups["finished"]][:3] == ["cancelled", "done-new", "done-old"]
    assert [c["title"] for c in groups["finished"]][-1] == "empty"                # no dates: last
    assert sum(len(v) for v in groups.values()) == len(contracts)


def test_the_groups_always_exist_even_when_empty():
    assert group_by_timing([], TODAY) == {"running": [], "upcoming": [], "finished": []}


# --- sorting the list ------------------------------------------------------

def _titles(contracts):
    return [c["title"] for c in contracts]


def _finished(title, customer="Customer", kind="other", amount="100", start=None):
    start = start or date(2026, 1, 1)
    return contract(pay(amount, work_from=start, work_to=start + timedelta(days=1)), title=title, customer=customer, kind=kind)


def test_by_customer_sorts_on_the_customer_name_ignoring_case_then_on_the_title():
    contracts = [_finished("b", "zeta GmbH"), _finished("z", "Alpha AG"), _finished("a", "alpha ag"), _finished("m", "Mitte")]
    assert _titles(sort_contracts(contracts, "customer")) == ["a", "z", "m", "b"]
    assert _titles(sort_contracts(contracts, "customer", descending=True)) == ["b", "m", "a", "z"]   # ties stay by title


def test_by_kind_follows_the_kinds_in_their_fixed_order_with_an_unknown_kind_last():
    contracts = [_finished("o", kind="other"), _finished("c", kind="consulting"), _finished("x", kind="retired_kind"),
                 _finished("t", kind="teaching_course"), _finished("w", kind="workshop")]
    assert _titles(sort_contracts(contracts, "kind")) == ["t", "w", "c", "o", "x"]
    assert _titles(sort_contracts(contracts, "kind", descending=True)) == ["o", "c", "w", "t", "x"]


def test_by_dates_sorts_on_the_start_and_a_contract_without_dates_is_last_either_way():
    contracts = [_finished("mid", start=date(2026, 3, 1)), contract(title="no dates"), _finished("early", start=date(2026, 1, 1)),
                 _finished("late", start=date(2026, 9, 1))]
    assert _titles(sort_contracts(contracts, "dates")) == ["early", "mid", "late", "no dates"]
    assert _titles(sort_contracts(contracts, "dates", descending=True)) == ["late", "mid", "early", "no dates"]


def test_by_value_sorts_on_the_contract_value_and_equal_values_by_customer_then_title():
    contracts = [_finished("small", amount="200"), _finished("big", amount="9000"), _finished("b-equal", "Beta", amount="500"),
                 _finished("a-equal", "Alpha", amount="500")]
    assert _titles(sort_contracts(contracts, "value")) == ["small", "a-equal", "b-equal", "big"]
    assert _titles(sort_contracts(contracts, "value", descending=True)) == ["big", "a-equal", "b-equal", "small"]


def test_an_unknown_sort_is_refused_and_the_known_ones_are_listed():
    assert SORT_KEYS == ("customer", "kind", "dates", "value")
    with pytest.raises(ValueError):
        sort_contracts([], "price")


def test_a_chosen_sort_orders_each_section_and_keeps_every_contract_in_its_own_section():
    contracts = [
        contract(pay("100", work_from=date(2026, 1, 1), work_to=date(2027, 6, 1)), title="run-small"),
        contract(pay("900", work_from=date(2026, 1, 1), work_to=date(2026, 12, 1)), title="run-big"),
        contract(pay("50", work_from=date(2027, 1, 1), work_to=date(2027, 2, 1)), title="up-small"),
        contract(pay("700", work_from=date(2027, 3, 1), work_to=date(2027, 4, 1)), title="up-big"),
        contract(pay("300", work_from=date(2025, 1, 1), work_to=date(2025, 2, 1)), title="done-mid"),
        contract(pay("800", work_from=date(2026, 1, 1), work_to=date(2026, 2, 1)), title="done-big"),
    ]
    groups = group_by_timing(contracts, TODAY, sort="value", descending=True)
    assert _titles(groups["running"]) == ["run-big", "run-small"]
    assert _titles(groups["upcoming"]) == ["up-big", "up-small"]
    assert _titles(groups["finished"]) == ["done-big", "done-mid"]
    default = group_by_timing(contracts, TODAY)                     # no sort: the agreed timing order, unchanged
    assert _titles(default["running"]) == ["run-big", "run-small"] and _titles(default["upcoming"]) == ["up-small", "up-big"]


# --- the totals ------------------------------------------------------------

def test_totals_add_value_hours_and_collected_and_leave_out_cancelled_contracts():
    live = contract(pay("1000", "collected", hours="10", collected_on=date(2026, 6, 1)), pay("500", hours="5"))
    other = contract(pay("700"))
    gone = contract(pay("9999", "cancelled", hours="99"))
    result = totals([live, other, gone])
    assert result["count"] == 2 and result["cancelled"] == 1
    assert (result["value"], result["hours"], result["collected"]) == (D("2200"), D("15"), D("1000"))
    assert result["open"] == D("1200") and result["collected"] + result["open"] == result["value"]


def test_the_average_rate_only_counts_contracts_that_have_hours():
    hours = contract(pay("1500", hours="10"))
    no_hours = contract(pay("5000"))
    assert totals([hours, no_hours])["rate"] == D("150.00")       # 5000 with no hours recorded would flatter it
    assert totals([no_hours])["rate"] is None


def test_totals_of_nothing_are_zero_and_do_not_divide_by_zero():
    result = totals([])
    assert (result["count"], result["value"], result["collected"], result["open"]) == (0, D("0"), D("0"), D("0"))
    assert result["hours"] is None and result["rate"] is None
