"""Typed open hours for one day."""
from datetime import time

import pytest

from gcrm.booking.hours_text import format_day_hours, parse_day_hours


def test_two_windows_in_any_order_and_style():
    assert parse_day_hours("13.30–16:30, 9:30-12:00") == [(time(9, 30), time(12)), (time(13, 30), time(16, 30))]


def test_empty_means_closed():
    assert parse_day_hours("  ") == []
    assert parse_day_hours(",") == []


@pytest.mark.parametrize("typed", ["9-12", "12:00-09:00", "09:30-12:00, 11:00-13:00", "25:00-26:00", "morning"])
def test_bad_windows_are_refused(typed):
    with pytest.raises(ValueError):
        parse_day_hours(typed)


def test_format_round_trips():
    windows = [(time(9, 30), time(12)), (time(13, 30), time(16, 30))]
    assert format_day_hours(windows) == "09:30-12:00, 13:30-16:30"
    assert parse_day_hours(format_day_hours(windows)) == windows
