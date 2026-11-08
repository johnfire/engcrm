"""The three contract-flow charts, drawn from a flow result: titles, tooltips (with the number of
deals), the reference line, and German."""
from datetime import date
from decimal import Decimal

from gcrm.flow_charts import build_flow_charts

D = Decimal


def money(value) -> str:
    return f"€{Decimal(value):,.0f}"


def _bucket(start, entered, deals, cumulative, sales_in, other_in, target, cum_in, cum_target):
    zero = {"expected": D(0), "booked": D(0), "contracted": D(0), "collected": D(0)}
    total = sum(entered.values(), D(0))
    return {"start": start, "end": start, "entered": {**zero, **entered}, "entered_total": total, "deals": deals,
            "cumulative": D(cumulative), "sales_in": D(sales_in), "other_in": D(other_in), "money_in": D(sales_in) + D(other_in),
            "target": D(target), "cum_money_in": D(cum_in), "cum_target": D(cum_target)}


def _flow(has_target=True, granularity="month"):
    return {"granularity": granularity, "has_target": has_target, "buckets": [
        _bucket(date(2026, 10, 1), {"collected": D(600)}, 1, 700, 600, 1500, 5000, 2100, 5000),
        _bucket(date(2026, 11, 1), {"booked": D(2400), "expected": D(1000), "contracted": D(300)}, 3, 4400, 0, 900, 3000, 3000, 8000),
    ]}


def test_there_are_three_charts_in_order_each_with_a_title_a_note_and_a_table():
    charts = build_flow_charts(_flow(), "en", money)
    assert [c["key"] for c in charts] == ["new", "running", "cash"]
    assert [c["title"] for c in charts] == ["New business per month", "Total won so far (running total)",
                                            "Money in vs target (running total)"]
    for chart in charts:
        assert "<svg" in str(chart["svg"]) and chart["note"] and chart["rows"]


def test_the_titles_follow_the_bucket_size():
    assert build_flow_charts(_flow(granularity="week"), "en", money)[0]["title"] == "New business per week"
    assert build_flow_charts(_flow(granularity="year"), "en", money)[0]["title"] == "New business per year"


def test_the_new_business_bars_carry_the_number_of_deals_and_the_split_by_status_in_the_tooltip():
    svg = str(build_flow_charts(_flow(), "en", money)[0]["svg"])
    assert "10.2026: €600 · 1 deal · Collected €600" in svg
    assert "11.2026: €3,700 · 3 deals · Expected €1,000, Booked €2,400, Contracted €300" in svg
    assert svg.count('class="chart-bar"') == 2


def test_the_running_total_line_shows_the_total_so_far_and_what_was_added():
    chart = build_flow_charts(_flow(), "en", money)[1]
    svg = str(chart["svg"])
    assert svg.count("<polyline") == 1
    assert "11.2026: €4,400 in total · +€3,700 new" in svg
    assert chart["rows"][-1] == ["11.2026", "€4,400", "€3,700"]


def test_the_cash_chart_draws_money_in_against_a_dashed_target_with_the_split_in_the_tooltip():
    chart = build_flow_charts(_flow(), "en", money)[2]
    svg = str(chart["svg"])
    assert svg.count("<polyline") == 2 and "chart-line--ref" in svg
    assert "10.2026: €2,100 in of €5,000 target so far (this period: sales €600 + other income €1,500)" in svg
    assert chart["rows"][0] == ["10.2026", "€2,100", "€5,000"]


def test_without_a_plan_the_cash_chart_is_just_the_money_in_line():
    chart = build_flow_charts(_flow(has_target=False), "en", money)[2]
    svg = str(chart["svg"])
    assert svg.count("<polyline") == 1 and "chart-line--ref" not in svg and "target" not in svg
    assert chart["rows"][0] == ["10.2026", "€2,100"]


def test_labels_follow_the_bucket_size():
    week = str(build_flow_charts(_flow(granularity="week"), "en", money)[0]["svg"])
    assert "01.10.:" in week or "01.10." in week
    year = str(build_flow_charts(_flow(granularity="year"), "en", money)[0]["svg"])
    assert "2026: €600" in year or "2026:" in year


def test_german():
    charts = build_flow_charts(_flow(), "de", money)
    assert charts[0]["title"] == "Neues Geschäft pro Monat"
    assert "3 Abschlüsse" in str(charts[0]["svg"]) and "Gebucht €2,400" in str(charts[0]["svg"])


def test_a_flow_with_nothing_in_it_draws_nothing_to_hover():
    empty = {"granularity": "month", "has_target": False, "buckets": []}
    assert all(str(c["svg"]) == "" for c in build_flow_charts(empty, "en", money))


TODAY = date(2026, 11, 18)


def _outlook_bucket(start, end, *, money_in, projection, target, future=False, sales=D(0), other=D(0), entered=None):
    zero = {"expected": D(0), "booked": D(0), "contracted": D(0), "collected": D(0)}
    total = sum((entered or {}).values(), D(0))
    return {"start": start, "end": end, "future": future, "entered": {**zero, **(entered or {})}, "entered_total": total,
            "deals": 1 if total else 0, "cumulative": D(700), "sales_in": None if future else D(600), "other_in": None if future else D(1500),
            "money_in": None if future else money_in, "target": D(5000), "cum_money_in": None if future else money_in,
            "cum_target": target, "projection": projection, "proj_sales": sales, "proj_other": other}


def _outlook(has_target=True, undated=None):
    return {"range": "outlook", "granularity": "month", "has_target": has_target, "today": TODAY, "undated": undated, "buckets": [
        _outlook_bucket(date(2026, 10, 1), date(2026, 10, 31), money_in=D(2100), projection=D(2100), target=D(5000), entered={"collected": D(600)}),
        _outlook_bucket(date(2026, 11, 1), date(2026, 11, 30), money_in=D(3000), projection=D(4300), target=D(10000), sales=D(700), other=D(1500)),
        _outlook_bucket(date(2026, 12, 1), date(2026, 12, 31), money_in=None, projection=D(5800), target=D(15000), future=True, sales=D(0), other=D(1500)),
    ]}


def _marks(svg) -> int:
    return str(svg).count('class="chart-mark"')


def test_the_outlook_keeps_the_first_two_charts_to_the_past_and_the_present():
    charts = build_flow_charts(_outlook(), "en", money)
    assert _marks(charts[0]["svg"]) == 2 and _marks(charts[1]["svg"]) == 2                  # no empty future months
    assert _marks(charts[2]["svg"]) == 3                                                    # the cash chart runs on


def test_the_outlook_cash_chart_has_money_in_a_smooth_projection_and_a_dashed_target():
    chart = build_flow_charts(_outlook(), "en", money)[2]
    svg = str(chart["svg"])
    assert chart["title"] == "Money in, projection and target (running total)"
    assert svg.count("<polyline") == 2 and svg.count("chart-line--smooth") == 1 and "chart-line--projection" in svg and "chart-line--ref" in svg


def test_the_outlook_tooltips_say_what_is_in_so_far_what_is_projected_and_what_is_scheduled():
    svg = str(build_flow_charts(_outlook(), "en", money)[2]["svg"])
    assert "10.2026: €2,100 in so far · target €5,000" in svg                               # a past month: what happened
    assert ("11.2026: €3,000 in so far · projected €4,300 by month end · target €10,000 · "
            "this month: scheduled sales €700 + other income €1,500") in svg                # this month: both
    assert ("12.2026: projected €5,800 by month end · target €15,000 · "
            "this month: scheduled sales €0 + other income €1,500") in svg                  # a future month: projection only


def test_the_outlook_table_shows_a_dash_where_there_is_no_money_in_yet():
    rows = build_flow_charts(_outlook(), "en", money)[2]["rows"]
    assert rows[0] == ["10.2026", "€2,100", "€2,100", "€5,000"] and rows[2] == ["12.2026", "—", "€5,800", "€15,000"]


def test_without_a_plan_the_outlook_draws_money_in_and_the_projection_only():
    chart = build_flow_charts(_outlook(has_target=False), "en", money)[2]
    svg = str(chart["svg"])
    assert chart["title"] == "Money in and projection (running total)" and "chart-line--ref" not in svg and "target" not in svg
    assert chart["rows"][2] == ["12.2026", "—", "€5,800"]


def test_money_with_no_due_day_is_mentioned_under_the_chart():
    chart = build_flow_charts(_outlook(undated={"count": 2, "total": D(900)}), "en", money)[2]
    assert "2 payments worth €900 have no due day yet" in chart["extra"]
    assert build_flow_charts(_outlook(undated={"count": 1, "total": D(500)}), "en", money)[2]["extra"].startswith("1 payment worth €500")
    assert build_flow_charts(_outlook(), "en", money)[2]["extra"] == ""


def test_the_outlook_in_german():
    chart = build_flow_charts(_outlook(), "de", money)[2]
    assert chart["title"] == "Eingang, Prognose und Ziel (Laufende Summe)"
    assert "voraussichtlich €4,300 bis Monatsende" in str(chart["svg"])


def test_the_outlook_chart_is_wide_and_tall_and_the_others_are_not():
    charts = build_flow_charts(_outlook(), "en", money)
    assert [c["wide"] for c in charts] == [False, False, True]
    assert 'viewBox="0 0 900 320"' in str(charts[2]["svg"]) and 'viewBox="0 0 600 150"' in str(charts[0]["svg"])
    assert [c["wide"] for c in build_flow_charts(_flow(), "en", money)] == [False, False, False]
