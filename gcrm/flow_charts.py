"""The three contract-flow charts, drawn from a get_contract_flow() result: new business per period,
the running total, and money in against the target. Text comes from the translation catalogs; the
tooltips carry the number of deals and the split by status."""
from gcrm.charts import bar_chart, line_chart
from gcrm.i18n import translate

LABEL_FORMAT = {"week": "%d.%m.", "month": "%m.%Y", "year": "%Y"}
SPLIT_ORDER = ("expected", "booked", "contracted", "collected")


def build_flow_charts(flow: dict, lang: str, money) -> list[dict]:
    """[{key, title, note, svg, rows}] for the page. `money` formats an amount in euros."""
    fmt = LABEL_FORMAT[flow["granularity"]]
    buckets = flow["buckets"]
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
    return [
        {"key": "new", "title": new_title, "note": t("flow.note.new"), "rows": new_rows,
         "svg": bar_chart(new_points, new_title, tick_label=money)},
        {"key": "running", "title": running_title, "note": t("flow.note.running"), "rows": running_rows,
         "svg": line_chart(running_points, ["chart-line"], running_title, tick_label=money)},
        {"key": "cash", "title": cash_title, "note": t("flow.note.cash" if has_target else "flow.note.cashOnly"),
         "rows": cash_rows, "svg": line_chart(cash_points, series, cash_title, tick_label=money)},
    ]
