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


def _outlook_bucket(start, end, *, money_in, projection, target, future=False, sales=D(0), other=D(0), entered=None, with_new=None, year=None):
    zero = {"expected": D(0), "booked": D(0), "contracted": D(0), "collected": D(0)}
    total = sum((entered or {}).values(), D(0))
    return {"start": start, "end": end, "future": future, "entered": {**zero, **(entered or {})}, "entered_total": total,
            "deals": 1 if total else 0, "cumulative": D(700), "sales_in": None if future else D(600), "other_in": None if future else D(1500),
            "money_in": None if future else money_in, "target": D(5000), "cum_money_in": None if future else money_in,
            "cum_target": target, "projection": projection, "proj_sales": sales, "proj_other": other, "with_new": with_new,
            "year_known": None if year is None else year[0], "year_new": None if year is None else year[1],
            "year_total": None if year is None else year[0] + year[1]}


def _outlook(has_target=True, undated=None, new=None, months=1, delay=0, campaign=None):
    extra = (lambda connector, now, later: (connector, now, later)) if new else (lambda *_: (None, None, None))
    connector, now, later = extra(D(2100), D(4300) + new, D(5800) + 2 * new) if new else (None, None, None)
    return {"range": "outlook", "granularity": "month", "has_target": has_target, "today": TODAY, "undated": undated,
            "expected_new": new, "expected_new_months": months, "expected_new_delay": delay, "expected_new_campaign": campaign, "buckets": [
        _outlook_bucket(date(2026, 10, 1), date(2026, 10, 31), money_in=D(2100), projection=D(2100), target=D(5000), entered={"collected": D(600)}, with_new=connector),
        _outlook_bucket(date(2026, 11, 1), date(2026, 11, 30), money_in=D(3000), projection=D(4300), target=D(10000), sales=D(700), other=D(1500), with_new=now),
        _outlook_bucket(date(2026, 12, 1), date(2026, 12, 31), money_in=None, projection=D(5800), target=D(15000), future=True, sales=D(0), other=D(1500), with_new=later),
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
    assert 'viewBox="0 0 900 320"' in str(charts[2]["svg"]) and 'viewBox="0 0 600 260"' in str(charts[0]["svg"])   # taller: more marks
    ordinary = build_flow_charts(_flow(), "en", money)
    assert 'viewBox="0 0 600 150"' in str(ordinary[0]["svg"])                        # the other ranges are unchanged
    assert [c["wide"] for c in build_flow_charts(_flow(), "en", money)] == [False, False, False]


def test_the_undated_sales_become_a_list_of_links_to_where_they_can_be_fixed():
    items = [
        {"sale_id": 11, "deal_id": 3, "status": "expected", "amount_eur": D(800), "description": "Eckert", "organization_id": 7,
         "organization_name": "Eckert Schulen", "person_id": None, "person_name": None},
        {"sale_id": 12, "deal_id": 4, "status": "booked", "amount_eur": D(250), "description": "", "organization_id": None,
         "organization_name": None, "person_id": 9, "person_name": "Pat <Freelancer>"},
    ]
    chart = build_flow_charts(_outlook(undated={"count": 2, "total": D(1050), "items": items}), "en", money)[2]
    assert chart["undated_items"] == [
        {"name": "Eckert Schulen", "href": "/organizations/7#sales", "amount": "€800", "status": "Expected", "description": "Eckert"},
        {"name": "Pat <Freelancer>", "href": "/people/9#deal-4", "amount": "€250", "status": "Booked", "description": ""},
    ]
    assert build_flow_charts(_outlook(), "en", money)[2]["undated_items"] == []
    assert all(c["undated_items"] == [] for c in build_flow_charts(_flow(), "en", money))


def test_the_expected_new_sales_are_a_blue_smooth_line_between_the_projection_and_the_target():
    chart = build_flow_charts(_outlook(new=D(1000)), "en", money)[2]
    svg = str(chart["svg"])
    assert svg.count("chart-line--smooth") == 2 and "chart-line--assumed" in svg and "chart-line--ref" in svg
    assert svg.count("<polyline") == 2                                                   # money in and the target stay straight


def test_the_tooltips_name_the_total_with_the_new_sales_you_expect():
    svg = str(build_flow_charts(_outlook(new=D(1000)), "en", money)[2]["svg"])
    assert "10.2026: €2,100 in so far · target €5,000" in svg                           # a past month is unchanged
    assert ("11.2026: €3,000 in so far · projected €4,300 by month end · with expected new sales €5,300 · target €10,000 · "
            "this month: scheduled sales €700 + other income €1,500") in svg
    assert ("12.2026: projected €5,800 by month end · with expected new sales €7,800 · target €15,000 · "
            "this month: scheduled sales €0 + other income €1,500") in svg


def test_the_table_has_a_column_for_the_new_sales_line_only_when_there_is_one():
    rows = build_flow_charts(_outlook(new=D(1000)), "en", money)[2]["rows"]
    assert rows[0] == ["10.2026", "€2,100", "€2,100", "€2,100", "€5,000"] and rows[2] == ["12.2026", "—", "€5,800", "€7,800", "€15,000"]
    assert build_flow_charts(_outlook(), "en", money)[2]["rows"][2] == ["12.2026", "—", "€5,800", "€15,000"]


def test_the_note_says_what_the_blue_line_assumes_and_without_a_target_it_still_draws():
    chart = build_flow_charts(_outlook(new=D(1000)), "en", money)[2]
    assert "€1,000 a month" in chart["note"] and "paid in the month" in chart["note"]
    no_target = build_flow_charts(_outlook(has_target=False, new=D(1000)), "en", money)[2]
    assert "chart-line--assumed" in str(no_target["svg"]) and "chart-line--ref" not in str(no_target["svg"])
    assert "a month" not in build_flow_charts(_outlook(), "en", money)[2]["note"]


def test_the_new_sales_line_in_german():
    chart = build_flow_charts(_outlook(new=D(1000)), "de", money)[2]
    assert "mit erwarteten Neuverkäufen €5,300" in str(chart["svg"]) and "€1,000 pro Monat" in chart["note"]


def test_the_note_says_how_long_each_booking_keeps_paying():
    one = build_flow_charts(_outlook(new=D(1000)), "en", money)[2]["note"]
    six = build_flow_charts(_outlook(new=D(1000), months=6), "en", money)[2]["note"]
    forever = build_flow_charts(_outlook(new=D(1000), months=None), "en", money)[2]["note"]
    assert "paid in the month it is booked" in one and "6 months" not in one
    assert "every month for 6 months" in six and "€1,000 a month" in six
    assert "every month from then on" in forever and "paid in the month it is booked" not in forever
    german = build_flow_charts(_outlook(new=D(1000), months=None), "de", money)[2]["note"]
    assert "jeden Monat" in german and "danach" in german


def test_the_note_says_when_the_first_payment_comes():
    nxt = build_flow_charts(_outlook(new=D(1000), delay=1), "en", money)[2]["note"]
    later = build_flow_charts(_outlook(new=D(1000), months=6, delay=2), "en", money)[2]["note"]
    assert "paid in the month after it is booked" in nxt
    assert "starting 2 months after it is booked" in later and "every month for 6 months" in later
    german = build_flow_charts(_outlook(new=D(1000), months=None, delay=1), "de", money)[2]["note"]
    assert "im Monat nach dem Abschluss" in german


def _with_years():
    flow = _outlook(new=D(1000), months=None, delay=1)
    flow["buckets"][1]["year_known"], flow["buckets"][1]["year_new"], flow["buckets"][1]["year_total"] = D(36000), D(0), D(36000)
    flow["buckets"][2]["year_known"], flow["buckets"][2]["year_new"], flow["buckets"][2]["year_total"] = D(36000), D(24000), D(60000)
    return flow


def test_the_total_won_chart_gets_a_blue_year_line_from_this_month_on_even_in_the_future():
    chart = build_flow_charts(_with_years(), "en", money)[1]
    svg = str(chart["svg"])
    assert svg.count("<path") == 1 and "chart-line--assumed" in svg                       # one smooth blue path (two points); black is straight
    assert "12.2026: the 2026 total is heading for €60,000 (known €36,000 + expected new sales €24,000)" in svg
    assert chart["rows"][2] == ["12.2026", "—", "€60,000"] and chart["rows"][0][2] == "—"
    assert "calendar year of each month is heading" in chart["note"]


def test_without_expected_new_sales_the_total_won_chart_stays_as_it_was():
    chart = build_flow_charts(_outlook(), "en", money)[1]
    assert "chart-line--assumed" not in str(chart["svg"]) and "calendar year" not in chart["note"]
    german = build_flow_charts(_with_years(), "de", money)[1]
    assert "steuert auf" in str(german["svg"]) and "Kalenderjahr" in german["note"]


def _big_outlook():
    flow = _outlook(new=D(1000), months=None, delay=1)
    for bucket, total in zip(flow["buckets"], (30000, 90000, 140000)):
        bucket["cumulative"] = D(total)
        bucket["entered_total"] = D(total) if bucket["start"].month == 11 else bucket["entered_total"]
    flow["buckets"][2]["cum_target"], flow["buckets"][2]["projection"], flow["buckets"][2]["with_new"] = D(120000), D(70000), D(95000)
    flow["buckets"][1]["entered_total"] = D(85000)
    flow["buckets"][1]["entered"]["booked"] = D(85000)
    return flow


def test_the_outlook_axes_are_marked_every_ten_and_twenty_thousand():
    new, running, cash = build_flow_charts(_big_outlook(), "en", money)
    for marks in ("€10,000", "€50,000", "€90,000"):
        assert f">{marks}<" in str(new["svg"])
    marks = str(running["svg"])
    assert ">€20,000<" in marks and ">€40,000<" in marks and ">€100,000<" in marks          # every 20,000 ...
    assert ">€30,000<" not in marks and ">€50,000<" not in marks                              # ... not every 50,000
    assert ">€20,000<" in str(cash["svg"]) and ">€30,000<" not in str(cash["svg"])


def test_new_business_runs_six_months_ahead_with_the_expected_sales_stacked_in_blue():
    flow = _big_outlook()
    start = flow["buckets"][2]["start"]
    flow["buckets"] += [{**flow["buckets"][2], "start": date(2027, month, 1), "end": date(2027, month, 28), "future": True,
                         "entered_total": D(0), "deals": 0} for month in range(1, 9)]
    del start
    chart = build_flow_charts(flow, "en", money)[0]
    svg = str(chart["svg"])
    assert svg.count("chart-bar--assumed") >= 6 and 'class="chart-bar"' in svg
    labels = [row[0] for row in chart["rows"]]
    assert labels[-1] == "05.2027" and "06.2027" not in labels                      # this month (11.2026) + 6
    assert chart["rows"][0][2] == "—" and chart["rows"][1][2] == "€1,000"                    # past month: no blue; this month: blue
    assert "expected new sales €1,000" in svg and "Yellow: business you have entered" in chart["note"]


def test_without_expected_sales_new_business_stops_today_and_has_no_blue():
    chart = build_flow_charts(_outlook(), "en", money)[0]
    assert "chart-bar--assumed" not in str(chart["svg"]) and "Yellow" not in chart["note"]


def test_the_blue_bars_stop_when_the_campaign_ends_and_the_note_says_so():
    flow = _big_outlook()
    flow["expected_new_campaign"] = 2                                               # this month and the next only
    flow["buckets"] += [{**flow["buckets"][2], "start": date(2027, month, 1), "end": date(2027, month, 28), "future": True,
                         "entered_total": D(0), "deals": 0} for month in range(1, 9)]
    chart = build_flow_charts(flow, "en", money)[0]
    assert str(chart["svg"]).count("chart-bar--assumed") == 2
    assert [row[2] for row in chart["rows"][:5]] == ["—", "€1,000", "€1,000", "—", "—"]       # Oct (past), Nov, Dec, then none
    assert "for 2 months" in chart["note"]
    other = build_flow_charts(_outlook(new=D(1000)), "en", money)[1]["note"]
    assert "campaign" not in other


def test_the_money_notes_mention_the_campaign_length():
    note = build_flow_charts(_outlook(new=D(1000), months=None, delay=1, campaign=4), "en", money)[2]["note"]
    assert "campaign runs for 4 months" in note and "no new bookings are added" in note
    assert "campaign" not in build_flow_charts(_outlook(new=D(1000), months=None, delay=1), "en", money)[2]["note"]
