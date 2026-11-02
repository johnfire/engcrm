"""Dates are shown and typed European style, 28.10.2026, in both languages;
stored and sent between machines as ISO."""
from datetime import date, datetime, timezone

import pytest

from gcrm.dates import format_day, format_day_time, parse_day

TODAY = date(2026, 11, 2)


@pytest.mark.parametrize("value,shown", [
    (date(2026, 10, 28), "28.10.2026"),
    (date(2026, 1, 5), "05.01.2026"),
    (datetime(2026, 10, 28, 14, 7), "28.10.2026"),
    ("2026-10-28", "28.10.2026"),
    ("2026-10-28T14:07:00+00:00", "28.10.2026"),
    (None, ""),
    ("", ""),
])
def test_a_day_is_shown_day_month_year_with_dots(value, shown):
    assert format_day(value) == shown


@pytest.mark.parametrize("value,shown", [
    (datetime(2026, 10, 28, 14, 7), "28.10.2026 14:07"),
    (datetime(2026, 10, 28, 14, 7, tzinfo=timezone.utc), "28.10.2026 14:07"),
    ("2026-10-28T14:07:59.123+00:00", "28.10.2026 14:07"),
    ("2026-10-28 09:05", "28.10.2026 09:05"),
    (date(2026, 10, 28), "28.10.2026"),  # no time to show
    (None, ""),
])
def test_a_moment_is_shown_with_its_time(value, shown):
    assert format_day_time(value) == shown


def test_text_that_is_not_a_date_is_shown_unchanged_rather_than_hidden():
    assert format_day("next spring") == "next spring"


@pytest.mark.parametrize("typed,day", [
    ("28.10.2026", date(2026, 10, 28)),
    (" 28.10.2026 ", date(2026, 10, 28)),
    ("5.1.2026", date(2026, 1, 5)),
    ("28/10/2026", date(2026, 10, 28)),
    ("28-10-2026", date(2026, 10, 28)),
    ("28.10.26", date(2026, 10, 28)),
    ("28.10.", date(2026, 10, 28)),   # this year
    ("28.10", date(2026, 10, 28)),
    ("2026-10-28", date(2026, 10, 28)),  # ISO, as the phone app and old forms send it
])
def test_typed_days_are_read_european_style_and_iso(typed, day):
    assert parse_day(typed, TODAY) == day


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_day_is_none(blank):
    assert parse_day(blank, TODAY) is None


@pytest.mark.parametrize("typed", ["10/28/2026", "31.02.2026", "28.13.2026", "yesterday", "2026-28-10", "28..2026",
                                   "1.2.3.4", "28.10.20266"])
def test_impossible_or_american_days_are_refused(typed):
    with pytest.raises(ValueError):
        parse_day(typed, TODAY)


def test_no_form_uses_the_browsers_own_date_input():
    """The browser's date input shows its own locale's order (10/28/2026 in a US
    browser), so every form uses partials/date_field.html instead."""
    from pathlib import Path

    templates = Path(__file__).parents[1] / "gcrm/ui/templates"
    offenders = [str(path.relative_to(templates)) for path in templates.rglob("*.html")
                 if "_layout_audit" not in str(path) and path.name != "date_field.html"
                 and 'type="date"' in path.read_text()]
    assert offenders == []


def test_log_activity_reads_european_days():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from gcrm.api.routers import statistics

    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {"?column?": 1}
    form = {"method": "phone", "duration_minutes": "", "note": "Call", "offer": None, "occurred_on": "28.10.2020",
            "attitude": [], "my_read": [], "materials_left": "", "followup_promised": "", "followup_date": "15.11.2026"}
    with patch.object(statistics, "db") as database, patch.object(statistics, "_workspace_id", return_value=1), \
         patch.object(statistics, "resolve_log_offer", return_value=None), \
         patch.object(statistics, "log_meeting_note") as log:
        database.return_value.__enter__.return_value = connection
        statistics.log_activity(SimpleNamespace(session={}), 7, _admin="admin", **form)
    assert log.call_args.kwargs["occurred_on"] == date(2020, 10, 28)
    assert log.call_args.kwargs["follow_up_date"] == date(2026, 11, 15)


def test_the_date_field_shows_its_value_european_style_and_names_only_the_text_box():
    from gcrm.api.templates import templates

    macro = templates.env.from_string(
        "{% from 'partials/date_field.html' import date_field with context %}{{ date_field('won_on', day, required=True) }}")
    html = macro.render(day=date(2026, 10, 28), t=lambda key: {"date.placeholder": "DD.MM.YYYY"}.get(key, key))
    assert 'name="won_on"' in html and 'value="28.10.2026"' in html and "required" in html
    assert html.count("name=") == 1  # the hidden calendar is never submitted
    assert 'placeholder="DD.MM.YYYY"' in html
