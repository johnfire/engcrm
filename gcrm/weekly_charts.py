"""The weekly-hours chart for the Forecast page, drawn from get_weekly_hours(): one bar a week, yellow for the
hours entered on sales, blue on top for the hours of the new bookings the plan expects, and a dashed line at the
hours that can be worked in a week. Text comes from the translation catalogs."""
from gcrm.charts import bar_chart
from gcrm.i18n import translate

CHART_WIDTH, CHART_HEIGHT, MAX_LABELS = 1400, 280, 14      # a year of weeks: drawn wide so the type stays small


def build_weekly_hours_chart(weekly: dict, lang: str, hours) -> dict:
    """{title, note, rows, svg} for the page. `hours` formats a number of hours (with its unit)."""
    def t(key: str, **params) -> str:
        return translate(key, lang, **params)

    capacity, has_expected = weekly["capacity"], weekly["has_expected"]
    points, rows = [], []
    for week in weekly["weeks"]:
        span = f"{week['start']:%d.%m.}–{week['end']:%d.%m.}"
        parts = [f"{span}: {t('hours.part.entered', hours=hours(week['entered']))}"]
        point = {"label": f"{week['start']:%d.%m.}", "value": float(week["entered"])}
        row = [point["label"], hours(week["entered"])]
        if has_expected:
            if week["expected"]:
                parts.append(t("hours.part.expected", hours=hours(week["expected"])))
                point["assumed"] = float(week["expected"])
            row.append(hours(week["expected"]))
        parts.append(t("hours.part.together", hours=hours(week["total"])))
        if capacity:
            parts.append(t("hours.part.limit", hours=hours(capacity)))
        point["tip"] = " · ".join(parts)
        row.append(hours(week["total"]))
        points.append(point)
        rows.append(row)
    note = t("hours.note")
    if has_expected:
        note += " " + t("hours.noteExpected")
    if capacity:
        note += " " + t("hours.noteLimit", hours=hours(capacity))
    title = t("hours.title")
    return {"title": title, "note": note, "rows": rows, "has_expected": has_expected,
            "svg": bar_chart(points, title, height=CHART_HEIGHT, tick_label=lambda tick: f"{tick:g}",
                             limit=float(capacity) if capacity else None, width=CHART_WIDTH, max_labels=MAX_LABELS)}
