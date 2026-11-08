"""The three contract-flow charts, drawn from a get_contract_flow() result: new business per period,
the running total, and money in against the target. In the outlook the first two stop at today and
the third runs twelve months on, with a projection line. Text comes from the translation catalogs;
the tooltips carry the number of deals and the split by status."""
from gcrm.charts import bar_chart, line_chart
from gcrm.i18n import translate

LABEL_FORMAT = {"week": "%d.%m.", "month": "%m.%Y", "year": "%Y"}
SPLIT_ORDER = ("expected", "booked", "contracted", "collected")
OUTLOOK_WIDTH, OUTLOOK_HEIGHT = 900, 320     # the outlook chart spans the page and has up to 37 months to show


def _undated_item(item: dict, t, money) -> dict:
    """One sale with no due day, as a line with a link to where its due day can be set: an
    organization's Sales card, or the person's deal card."""
    if item["organization_id"] is not None:
        name, href = item["organization_name"], f"/organizations/{item['organization_id']}#sales"
    else:
        name, href = item["person_name"], f"/people/{item['person_id']}#deal-{item['deal_id']}"
    return {"name": name, "href": href, "amount": money(item["amount_eur"]),
            "status": t(f"sale.status.{item['status']}"), "description": item["description"] or ""}


def _outlook_chart(flow: dict, t, label, money) -> dict:
    """Money in so far (solid), the projection from today on (a smooth dotted line) and the target
    (dashed), by month, up to twelve months ahead."""
    has_target = flow["has_target"]
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
        if has_target:
            parts.append(t("flow.part.target", amount=money(b["cum_target"])))
        if future or current:
            parts.append(t("flow.part.thisMonth", sales=money(b["proj_sales"]), other=money(b["proj_other"])))
        values = [None if future else float(b["cum_money_in"]),
                  None if b["projection"] is None else float(b["projection"])]
        cells = ["—" if future else money(b["cum_money_in"]), "—" if b["projection"] is None else money(b["projection"])]
        if has_target:
            values.append(float(b["cum_target"]))
            cells.append(money(b["cum_target"]))
        points.append({"label": label(b), "values": values, "tip": f"{label(b)}: " + " · ".join(parts)})
        rows.append([label(b)] + cells)
    title = t("flow.chart.outlook" if has_target else "flow.chart.outlookOnly")
    series = ["chart-line", "chart-line chart-line--projection chart-line--smooth"]
    if has_target:
        series.append("chart-line chart-line--ref")
    undated = flow.get("undated")
    extra = t("flow.undated", count=undated["count"], amount=money(undated["total"])) if undated and undated["count"] else ""
    items = [_undated_item(item, t, money) for item in (undated or {}).get("items", [])]
    return {"key": "cash", "title": title, "note": t("flow.note.outlook" if has_target else "flow.note.outlookOnly"),
            "rows": rows, "extra": extra, "undated_items": items, "wide": True,
            "svg": line_chart(points, series, title, height=OUTLOOK_HEIGHT, tick_label=money,
                                width=OUTLOOK_WIDTH)}


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

    new_points, new_rows = [], []
    for b in buckets:
        split = ", ".join(f"{t('sale.status.' + status)} {money(b['entered'][status])}"
                          for status in SPLIT_ORDER if b["entered"][status])
        parts = [f"{label(b)}: {money(b['entered_total'])}", t("flow.deals", count=b["deals"])]
        tip = " · ".join(parts + ([split] if split else []))
        new_points.append({"label": label(b), "value": float(b["entered_total"]), "tip": tip})
        new_rows.append([label(b), money(b["entered_total"]), str(b["deals"])])

    running_points = [{"label": label(b), "values": [float(b["cumulative"])],
                       "tip": t("flow.tip.running", label=label(b), total=money(b["cumulative"]),
                                added=money(b["entered_total"]))} for b in buckets]
    running_rows = [[label(b), money(b["cumulative"]), money(b["entered_total"])] for b in buckets]

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
    return [
        {"key": "new", "title": new_title, "note": t("flow.note.new"), "rows": new_rows, "extra": "", "undated_items": [], "wide": False,
         "svg": bar_chart(new_points, new_title, tick_label=money)},
        {"key": "running", "title": running_title, "note": t("flow.note.running"), "rows": running_rows, "extra": "", "undated_items": [], "wide": False,
         "svg": line_chart(running_points, ["chart-line"], running_title, tick_label=money)},
        cash,
    ]
