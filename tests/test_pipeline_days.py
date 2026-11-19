from datetime import date, datetime

from gcrm.pipeline_days import days_to_customer

TODAY = date(2026, 11, 19)


def _deals(*stages):
    return [{"stage": s} for s in stages]


def test_candidates_and_suspects_have_no_figure():
    for stage in ("candidate", "suspect", "not_in_pipeline"):
        assert days_to_customer(_deals(stage), date(2026, 11, 1), None, TODAY) is None


def test_open_relationship_counts_until_today():
    for stage in ("nibble", "prospect", "opportunity"):
        assert days_to_customer(_deals(stage), date(2026, 11, 9), None, TODAY) == 10


def test_customer_stops_the_clock_on_the_day_they_signed():
    since = datetime(2026, 11, 15, 14, 30)
    assert days_to_customer(_deals("customer"), date(2026, 11, 1), since, TODAY) == 14


def test_customer_without_recorded_date_is_blank_not_guessed():
    assert days_to_customer(_deals("customer"), date(2026, 11, 1), None, TODAY) is None


def test_no_contact_yet_is_blank():
    assert days_to_customer(_deals("prospect"), None, None, TODAY) is None


def test_no_deals_is_blank():
    assert days_to_customer([], date(2026, 11, 1), None, TODAY) is None


def test_accepts_the_iso_strings_feed_rows_carry():
    assert days_to_customer(_deals("prospect"), "2026-11-09", None, TODAY) == 10
    assert days_to_customer(_deals("customer"), "2026-11-01", "2026-11-15T14:30:00+00:00", TODAY) == 14
