"""The weekly-hours chart: yellow bars for entered hours, blue on top for expected new bookings, a dashed limit."""
from datetime import date
from decimal import Decimal

from gcrm.weekly_charts import build_weekly_hours_chart

D = Decimal


def hours(value):
    return f"{Decimal(value):,.1f} h"


def _weekly(capacity=None, with_expected=True):
    weeks = [{"start": date(2026, 11, 9), "end": date(2026, 11, 15), "entered": D("7.5"), "expected": D("0"), "total": D("7.5")},
             {"start": date(2026, 11, 16), "end": date(2026, 11, 22), "entered": D("10"), "expected": D("3") if with_expected else D("0"),
              "total": D("13") if with_expected else D("10")}]
    return {"weeks": weeks, "capacity": capacity, "has_expected": with_expected}


def test_the_chart_has_a_title_a_note_a_table_and_a_tooltip_per_week():
    chart = build_weekly_hours_chart(_weekly(D("30")), "en", hours)
    svg = str(chart["svg"])
    assert chart["title"] == "Hours booked per week" and svg.count("<title>") == 2
    assert "09.11.–15.11.: 7.5 h entered" in svg and "3.0 h expected from new sales" in svg and "13.0 h together" in svg
    assert "limit 30.0 h" in svg
    assert chart["rows"][0] == ["09.11.", "7.5 h", "0.0 h", "7.5 h"] and chart["rows"][1] == ["16.11.", "10.0 h", "3.0 h", "13.0 h"]
    assert "Yellow" in chart["note"] and "Blue" in chart["note"] and "30.0 h" in chart["note"]


def test_the_blue_part_and_the_limit_only_appear_when_there_is_something_to_show():
    chart = build_weekly_hours_chart(_weekly(None, with_expected=False), "en", hours)
    assert "chart-bar--assumed" not in str(chart["svg"]) and "chart-limit" not in str(chart["svg"])
    assert chart["rows"][0] == ["09.11.", "7.5 h", "7.5 h"] and "Blue" not in chart["note"] and "limit" not in chart["note"].lower()
    with_everything = str(build_weekly_hours_chart(_weekly(D("30")), "en", hours)["svg"])
    assert with_everything.count("chart-bar--assumed") == 1 and "chart-limit" in with_everything          # only the week with blue hours


def test_the_chart_follows_the_language():
    chart = build_weekly_hours_chart(_weekly(D("30")), "de", hours)
    assert chart["title"] == "Gebuchte Stunden pro Woche" and "erfasst" in str(chart["svg"]) and "Grenze" in str(chart["svg"])
