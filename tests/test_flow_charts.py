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
