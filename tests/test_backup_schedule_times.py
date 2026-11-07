"""When the next backup is due: a pure calculation in the workspace's own time zone."""
from datetime import datetime, time, timezone

import pytest

from gcrm.tools.backup_schedule import compute_next_run

UTC = timezone.utc


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_off_has_no_next_run():
    assert compute_next_run("off", 0, time(3, 0), "Europe/Berlin", at("2026-11-07T10:00")) is None


def test_daily_is_the_next_time_of_day_in_the_workspaces_zone():
    # 03:00 Berlin in November is 02:00 UTC
    assert compute_next_run("daily", 0, time(3, 0), "Europe/Berlin", at("2026-11-07T10:00")) == at("2026-11-08T02:00")
    assert compute_next_run("daily", 0, time(3, 0), "Europe/Berlin", at("2026-11-07T01:00")) == at("2026-11-07T02:00")


def test_a_run_exactly_now_is_not_due_again_until_the_next_day():
    assert compute_next_run("daily", 0, time(3, 0), "Europe/Berlin", at("2026-11-07T02:00")) == at("2026-11-08T02:00")


def test_weekly_is_the_chosen_weekday():
    # 2026-11-07 is a Saturday; Monday (0) is the 9th, Saturday (5) is a week later
    assert compute_next_run("weekly", 0, time(8, 30), "Europe/Berlin", at("2026-11-07T10:00")) == at("2026-11-09T07:30")
    assert compute_next_run("weekly", 5, time(8, 30), "Europe/Berlin", at("2026-11-07T10:00")) == at("2026-11-14T07:30")
    assert compute_next_run("weekly", 5, time(8, 30), "Europe/Berlin", at("2026-11-07T05:00")) == at("2026-11-07T07:30")


def test_summer_time_moves_the_utc_hour_but_not_the_local_one():
    assert compute_next_run("daily", 0, time(3, 0), "Europe/Berlin", at("2026-07-01T10:00")) == at("2026-07-02T01:00")


def test_other_zones_work():
    assert compute_next_run("daily", 0, time(9, 0), "America/New_York", at("2026-11-07T10:00")) == at("2026-11-07T14:00")


@pytest.mark.parametrize("args", [("hourly", 0, time(3, 0), "Europe/Berlin"), ("daily", 7, time(3, 0), "Europe/Berlin"),
                                  ("daily", 0, time(3, 0), "Mars/Olympus")])
def test_nonsense_is_refused(args):
    with pytest.raises(ValueError):
        compute_next_run(*args, at("2026-11-07T10:00"))
