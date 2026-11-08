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


def test_a_year_of_weeks_is_drawn_wide_so_the_type_stays_small_with_a_label_every_few_weeks():
    import re
    from datetime import timedelta
    start = date(2026, 11, 9)
    weeks = [{"start": start + timedelta(weeks=i), "end": start + timedelta(weeks=i, days=6), "entered": D(i % 20), "expected": D(0),
              "total": D(i % 20)} for i in range(52)]
    chart = build_weekly_hours_chart({"weeks": weeks, "capacity": None, "has_expected": False}, "en", hours)
    svg = str(chart["svg"])
    assert 'viewBox="0 0 1400 ' in svg and len(chart["rows"]) == 52 and svg.count("<title>") == 52
    assert 10 <= len(re.findall(r'text-anchor="middle">\d\d\.\d\d\.<', svg)) <= 14
