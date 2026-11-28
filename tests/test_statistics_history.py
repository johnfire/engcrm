"""Buckets for the over-time charts."""
from datetime import date

from gcrm.tools.statistics_history import bucket_start, bucket_starts


def test_weekly_buckets_are_the_last_twelve_mondays():
    starts = bucket_starts("week", date(2026, 10, 15))
    assert len(starts) == 12 and starts[-1] == date(2026, 10, 12) and starts[0] == date(2026, 7, 27)


def test_monthly_buckets_cross_the_year():
    starts = bucket_starts("month", date(2026, 2, 10))
    assert starts[0] == date(2025, 3, 1) and starts[-1] == date(2026, 2, 1) and len(starts) == 12


def test_yearly_buckets_are_five_years():
    assert bucket_starts("year", date(2026, 6, 1)) == [date(y, 1, 1) for y in range(2022, 2027)]


def test_bucket_start():
    assert bucket_start("week", date(2026, 10, 18)) == date(2026, 10, 12)
    assert bucket_start("month", date(2026, 10, 18)) == date(2026, 10, 1)
    assert bucket_start("year", date(2026, 10, 18)) == date(2026, 1, 1)


from gcrm.tools.statistics_history import side_stage_moves, stage_counts  # noqa: E402

WEEKS = [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16)]


def _series(pipeline):
    return {"periods": [{"start": start} for start in WEEKS], "pipeline": pipeline}


def test_stage_counts_add_organization_and_person_deals_and_fill_a_missing_bucket_with_zero():
    series = _series({
        "organization": {"prospect": {WEEKS[0]: 2, WEEKS[2]: 1}},
        "person": {"prospect": {WEEKS[0]: 1}, "nibble": {WEEKS[1]: 4}},
    })
    counts = stage_counts(series, ("suspect", "nibble", "prospect"))
    assert counts == {"suspect": [0, 0, 0], "nibble": [0, 4, 0], "prospect": [3, 0, 1]}


def test_side_stage_moves_compare_the_latest_bucket_with_the_first_bucket_that_has_a_log():
    series = _series({"organization": {"candidate": {WEEKS[1]: 10, WEEKS[2]: 12}, "not_now": {WEEKS[1]: 3}}})
    moves = side_stage_moves(series, ("candidate", "not_now", "not_in_pipeline"))
    assert moves["candidate"] == {"latest": 12, "change": 2}
    assert moves["not_now"] == {"latest": 0, "change": -3}      # the stage emptied: latest 0 vs 3 at the start
    assert moves["not_in_pipeline"] == {"latest": 0, "change": 0}


def test_side_stage_moves_are_zero_while_nothing_is_logged():
    assert side_stage_moves(_series({}), ("candidate",)) == {"candidate": {"latest": 0, "change": 0}}
