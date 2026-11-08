"""The three contract-flow charts, drawn from a get_contract_flow() result: new business per period,
the running total, and money in against the target. In the outlook the first two stop at today and
the third runs twelve months on, with a projection line. Text comes from the translation catalogs;
the tooltips carry the number of deals and the split by status."""
from gcrm.charts import bar_chart, line_chart
from gcrm.forecast_math import month_index
from gcrm.i18n import translate
from gcrm.sale_series import shift_months

LABEL_FORMAT = {"week": "%d.%m.", "month": "%m.%Y", "year": "%Y"}
SPLIT_ORDER = ("expected", "booked", "contracted", "collected")
OUTLOOK_WIDTH, OUTLOOK_HEIGHT, OUTLOOK_LABELS = 1400, 340, 14     # drawn wide so its type stays small; up to 37 months to show
NEW_BUSINESS_MONTHS_AHEAD = 6                # with new sales expected, the bars run this far past this month
TICK_STEPS = {"new": 10_000, "running": 20_000, "cash": 20_000}     # outlook: a mark every so many euros
TALL = 260                                   # room for the extra marks


def _undated_item(item: dict, t, money) -> dict:
    """One sale with no due day, as a line with a link to where its due day can be set: an
    organization's Sales card, or the person's deal card."""
    if item["organization_id"] is not None:
        name, href = item["organization_name"], f"/organizations/{item['organization_id']}#sales"
    else:
        name, href = item["person_name"], f"/people/{item['person_id']}#deal-{item['deal_id']}"
    return {"name": name, "href": href, "amount": money(item["amount_eur"]),
            "status": t(f"sale.status.{item['status']}"), "description": item["description"] or ""}


def _year_view(flow: dict, label, t, money) -> tuple[list[dict], list[list]]:
    """Points and table rows for the "total won" chart when new sales are expected: the black running total
    up to today and, from this month on, the blue line of where the calendar year of each month is heading
    (what is known for that year plus the cash the expected new bookings started by then bring that year)."""
    points, rows = [], []
    for b in flow["buckets"]:
        year_total = b["year_total"]
        parts = []
        if not b["future"]:
            parts.append(t("flow.tip.running", label=label(b), total=money(b["cumulative"]), added=money(b["entered_total"])))
        if year_total is not None:
            parts.append(t("flow.part.yearHeading", label=label(b), year=b["start"].year, total=money(year_total),
                           known=money(b["year_known"]), new=money(b["year_new"])))
        tip = " · ".join(parts)
        points.append({"label": label(b), "tip": tip or label(b),
                       "values": [None if b["future"] else float(b["cumulative"]),
                                  None if year_total is None else float(year_total)]})
        rows.append([label(b), "—" if b["future"] else money(b["cumulative"]),
                     "—" if year_total is None else money(year_total)])
    return points, rows


def _outlook_chart(flow: dict, t, label, money) -> dict:
    """Money in so far (solid), the projection from today on (a smooth dotted line), the same plus the
    new sales the owner expects each month (a smooth blue line, only when entered) and the target
    (dashed), by month, up to twelve months ahead."""
    has_target = flow["has_target"]
    expected_new = flow.get("expected_new")
    today = flow["today"]
    points, rows = [], []
    for b in flow["buckets"]:
        future = b["future"]
        current = not future and b["start"] <= today <= b["end"]
        parts = []
        if not future:
            parts.append(t("flow.part.inSoFar", amount=money(b["cum_money_in"])))
        if future or current:
            parts.append(t("flow.part.projected", amount=money(b["projection"])))
            if b["with_new"] is not None:
                parts.append(t("flow.part.withNew", amount=money(b["with_new"])))
        if has_target:
            parts.append(t("flow.part.target", amount=money(b["cum_target"])))
        if future or current:
            parts.append(t("flow.part.thisMonth", sales=money(b["proj_sales"]), other=money(b["proj_other"])))
        values = [None if future else float(b["cum_money_in"]),
                  None if b["projection"] is None else float(b["projection"])]
        cells = ["—" if future else money(b["cum_money_in"]), "—" if b["projection"] is None else money(b["projection"])]
        if expected_new:
            values.append(None if b["with_new"] is None else float(b["with_new"]))
            cells.append("—" if b["with_new"] is None else money(b["with_new"]))
        if has_target:
            values.append(float(b["cum_target"]))
            cells.append(money(b["cum_target"]))
        points.append({"label": label(b), "values": values, "tip": f"{label(b)}: " + " · ".join(parts)})
        rows.append([label(b)] + cells)
    title = t("flow.chart.outlook" if has_target else "flow.chart.outlookOnly")
    series = ["chart-line", "chart-line chart-line--projection chart-line--smooth"]
    if expected_new:
        series.append("chart-line chart-line--assumed chart-line--smooth")
    if has_target:
        series.append("chart-line chart-line--ref")
    note = t("flow.note.outlook" if has_target else "flow.note.outlookOnly")
    if expected_new:
        months = flow.get("expected_new_months", 1)
        key = "flow.note.assumedForever" if months is None else "flow.note.assumedMonths" if months > 1 else "flow.note.assumed"
        delay = flow.get("expected_new_delay", 1)
        when = t("flow.when.same" if delay == 0 else "flow.when.next" if delay == 1 else "flow.when.later", delay=delay)
        note += " " + t(key, amount=money(expected_new), months=months, when=when)
        if flow.get("expected_new_campaign"):
            note += " " + t("flow.note.campaignStops", months=flow["expected_new_campaign"])
    undated = flow.get("undated")
    extra = t("flow.undated", count=undated["count"], amount=money(undated["total"])) if undated and undated["count"] else ""
    items = [_undated_item(item, t, money) for item in (undated or {}).get("items", [])]
    return {"key": "cash", "title": title, "note": note,
            "rows": rows, "extra": extra, "undated_items": items, "wide": True,
            "svg": line_chart(points, series, title, height=OUTLOOK_HEIGHT, tick_label=money,
                                width=OUTLOOK_WIDTH, tick_step=TICK_STEPS["cash"], max_labels=OUTLOOK_LABELS)}


def build_flow_charts(flow: dict, lang: str, money) -> list[dict]:
    """[{key, title, note, extra, svg, rows}] for the page. `money` formats an amount in euros."""
    fmt = LABEL_FORMAT[flow["granularity"]]
    outlook = flow.get("range") == "outlook"
    buckets = [b for b in flow["buckets"] if not b.get("future")]              # the first two charts stop at today
    has_target = flow["has_target"]

    def t(key: str, **params) -> str:
        return translate(key, lang, **params)

    def label(bucket: dict) -> str:
        return bucket["start"].strftime(fmt)

    expected_new = flow.get("expected_new") if outlook else None
    new_points, new_rows = [], []
    reach = shift_months(flow["today"].replace(day=1), NEW_BUSINESS_MONTHS_AHEAD) if expected_new else None
    for b in ([b for b in flow["buckets"] if b["start"] <= reach] if expected_new else buckets):
        split = ", ".join(f"{t('sale.status.' + status)} {money(b['entered'][status])}"
                          for status in SPLIT_ORDER if b["entered"][status])
        parts = [f"{label(b)}: {money(b['entered_total'])}", t("flow.deals", count=b["deals"])]
        point = {"label": label(b), "value": float(b["entered_total"])}
        row = [label(b), money(b["entered_total"]), str(b["deals"])]
        if expected_new:
            campaign = flow.get("expected_new_campaign")
            this_month = flow["today"].replace(day=1)
            has_blue = b["end"] >= flow["today"] and (campaign is None or month_index(this_month, b["start"]) < campaign)
            if has_blue:
                parts.append(t("flow.part.newExpected", amount=money(expected_new)))
                point["assumed"] = float(expected_new)
            row.insert(2, money(expected_new) if has_blue else "—")
        point["tip"] = " · ".join(parts + ([split] if split else []))
        new_points.append(point)
        new_rows.append(row)

    running_points = [{"label": label(b), "values": [float(b["cumulative"])],
                       "tip": t("flow.tip.running", label=label(b), total=money(b["cumulative"]),
                                added=money(b["entered_total"]))} for b in buckets]
    running_rows = [[label(b), money(b["cumulative"]), money(b["entered_total"])] for b in buckets]
    running_series, running_note = ["chart-line"], t("flow.note.running")
    if outlook and flow.get("expected_new"):
        running_points, running_rows = _year_view(flow, label, t, money)
        running_series.append("chart-line chart-line--assumed chart-line--smooth")
        running_note += " " + t("flow.note.runningYear")

    cash_points, cash_rows = [], []
    for b in buckets:
        split = {"label": label(b), "money_in": money(b["cum_money_in"]), "target": money(b["cum_target"]),
                 "sales": money(b["sales_in"]), "other": money(b["other_in"])}
        key = "flow.tip.cash" if has_target else "flow.tip.cashNoTarget"
        values = [float(b["cum_money_in"])] + ([float(b["cum_target"])] if has_target else [])
        cash_points.append({"label": label(b), "values": values, "tip": t(key, **split)})
        cash_rows.append([label(b), money(b["cum_money_in"])] + ([money(b["cum_target"])] if has_target else []))

    new_title = t("flow.chart.new", period=t(f"flow.period.{flow['granularity']}"))
    running_title = t("flow.chart.running")
    cash_title = t("flow.chart.cash" if has_target else "flow.chart.cashOnly")
    series = ["chart-line", "chart-line chart-line--ref"] if has_target else ["chart-line"]
    cash = (_outlook_chart(flow, t, label, money) if outlook else
            {"key": "cash", "title": cash_title, "note": t("flow.note.cash" if has_target else "flow.note.cashOnly"),
             "rows": cash_rows, "extra": "", "undated_items": [], "wide": False, "svg": line_chart(cash_points, series, cash_title, tick_label=money)})
    new_note = t("flow.note.new")
    if expected_new:
        campaign = flow.get("expected_new_campaign")
        new_note += " " + (t("flow.note.newExpectedFor", amount=money(expected_new), months=campaign) if campaign
                           else t("flow.note.newExpected", amount=money(expected_new)))
    steps = TICK_STEPS if outlook else {}
    tall = {"height": TALL} if outlook else {}
    return [
        {"key": "new", "title": new_title, "note": new_note, "rows": new_rows, "extra": "", "undated_items": [], "wide": False,
         "svg": bar_chart(new_points, new_title, tick_label=money, tick_step=steps.get("new"), **tall)},
        {"key": "running", "title": running_title, "note": running_note, "rows": running_rows, "extra": "", "undated_items": [], "wide": False,
         "svg": line_chart(running_points, running_series, running_title, tick_label=money,
                           tick_step=steps.get("running"), **tall)},
        cash,
    ]
