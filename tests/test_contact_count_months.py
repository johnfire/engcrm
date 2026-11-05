"""The two completed calendar months keep exact dates across year and leap-year boundaries."""
from datetime import date
from unittest.mock import patch

import pytest

from gcrm.tools.db_contact_counts import get_contact_counts


@pytest.mark.parametrize("day,expected", [
    (date(2026, 11, 5), [(date(2026, 10, 1), date(2026, 10, 31)),
                        (date(2026, 9, 1), date(2026, 9, 30))]),
    (date(2027, 1, 1), [(date(2026, 12, 1), date(2026, 12, 31)),
                       (date(2026, 11, 1), date(2026, 11, 30))]),
    (date(2028, 3, 31), [(date(2028, 2, 1), date(2028, 2, 29)),
                         (date(2028, 1, 1), date(2028, 1, 31))]),
    (date(2027, 3, 1), [(date(2027, 2, 1), date(2027, 2, 28)),
                       (date(2027, 1, 1), date(2027, 1, 31))]),
])
def test_previous_months_are_complete_calendar_months(day, expected):
    def count(first_day, last_day, workspace_id, offer):
        return {"people": first_day.month, "organizations": last_day.day}
    with patch("gcrm.tools.db_contact_counts.count_contacted", side_effect=count) as count_contacts:
        counts = get_contact_counts(7, on=day, offer="consulting")
    assert counts["previous_months"] == [
        {"month_start": first.isoformat(), "month_end": last.isoformat(),
         "people": first.month, "organizations": last.day}
        for first, last in expected
    ]
    for first, last in expected:
        count_contacts.assert_any_call(first, last, 7, "consulting")
    count_contacts.assert_any_call(day.replace(day=1), day, 7, "consulting")
    assert count_contacts.call_count == 4


def test_previous_months_use_the_same_local_today_as_the_current_month():
    with patch("gcrm.tools.db_contact_counts.today", return_value=date(2027, 1, 1)), \
         patch("gcrm.tools.db_contact_counts.count_contacted", return_value={"people": 0, "organizations": 0}):
        counts = get_contact_counts(1)
    assert counts["month_start"] == "2027-01-01"
    assert [period["month_start"] for period in counts["previous_months"]] == ["2026-12-01", "2026-11-01"]
