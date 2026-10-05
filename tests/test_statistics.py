"""The rules behind the statistics: periods, activity types, stage directions."""
from datetime import date

import pytest

from gcrm.activity_types import activity_type, parse_minutes, type_case_sql
from gcrm.tools.statistics import period_bounds, previous_period, stage_direction


@pytest.mark.parametrize("period, expected", [
    ("week", (date(2026, 10, 12), date(2026, 10, 18))),
    ("month", (date(2026, 10, 1), date(2026, 10, 31))),
    ("quarter", (date(2026, 10, 1), date(2026, 12, 31))),
    ("year", (date(2026, 1, 1), date(2026, 12, 31))),
])
def test_period_bounds(period, expected):
    assert period_bounds(period, date(2026, 10, 15)) == expected


def test_month_and_quarter_ends_across_year_and_february():
    assert period_bounds("month", date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert period_bounds("quarter", date(2026, 2, 10)) == (date(2026, 1, 1), date(2026, 3, 31))


def test_previous_period_has_the_same_length():
    assert previous_period(date(2026, 10, 1), date(2026, 10, 31)) == (date(2026, 8, 31), date(2026, 9, 30))


@pytest.mark.parametrize("method, kind", [
    ("in_person", "drop_in"), ("visit", "drop_in"), ("meeting", "meeting"), ("phone", "phone"),
    ("call", "phone"), ("video", "video"), ("email", "email"), ("other", "note"), (None, "note"),
])
def test_both_vocabularies_map_to_one_set_of_types(method, kind):
    assert activity_type(method) == kind


def test_the_sql_mapping_is_built_from_constants_only():
    sql = type_case_sql("i.method")
    assert sql.startswith("(CASE i.method WHEN 'in_person' THEN 'drop_in'") and sql.endswith("ELSE 'note' END)")


@pytest.mark.parametrize("value, minutes", [(None, None), ("", None), ("  ", None), ("45", 45), (0, 0)])
def test_typed_minutes(value, minutes):
    assert parse_minutes(value) == minutes


@pytest.mark.parametrize("value", ["-5", "1441", "abc", "1.5"])
def test_bad_minutes_are_refused(value):
    with pytest.raises(ValueError):
        parse_minutes(value)


@pytest.mark.parametrize("before, after, direction", [
    ("candidate", "suspect", "forward"), ("prospect", "suspect", "back"),
    ("opportunity", "not_in_pipeline", "dropped"), ("not_in_pipeline", "prospect", "other"),
    (None, "candidate", "other"),
])
def test_stage_direction(before, after, direction):
    assert stage_direction(before, after) == direction
