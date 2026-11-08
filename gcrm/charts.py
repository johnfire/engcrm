"""Small server-drawn SVG charts for the Statistics and Forecast pages: no script, no outside
service. One series per chart in one hue (several measures get several charts,
never a second axis; the one exception is a dashed reference line in the same unit on the
same scale, such as a target); every bar or point has a full-height hover target whose
<title> is its tooltip; text is drawn in text colours, not the series colour.
Colours come from the page's CSS (classes chart-*), so the theme applies."""
import math
from html import escape

from markupsafe import Markup

WIDTH = 600
MAX_X_LABELS = 6
Y_INTERVALS = 4  # roughly how many steps the y scale is cut into
LABEL_CHAR_WIDTH = 11  # px per character of a 17px axis label (digits are widest), for the gutter


def _x_labels(count: int) -> set[int]:
    """Which positions get an x label: at most MAX_X_LABELS, always the last."""
    step = max(1, -(-count // MAX_X_LABELS))
    return {i for i in range(count) if (count - 1 - i) % step == 0}


def y_ticks(most: float, whole: bool) -> list[float]:
    """Round scale values from 0 up to at least `most`, in steps of 1, 2 or 5 times a
    power of ten. `whole` keeps the step at 1 or more, for counts."""
    raw = (most or 1) / Y_INTERVALS
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(f * magnitude for f in (1, 2, 5, 10) if f * magnitude >= raw)
    if whole:
        step = max(1, step)
    count = max(1, math.ceil(most / step - 1e-9))
    return [round(i * step, 10) for i in range(count + 1)]


def bar_chart(points: list[dict], title: str, height: int = 150, tick_label=str) -> Markup:
    """Vertical bars over a baseline, against a labelled y scale with gridlines.
    Each point: label, value (number), tip (tooltip text). `tick_label` formats a
    scale value (adds the unit)."""
    if not points:
        return Markup("")
    top, bottom = 18, 22
    plot = height - top - bottom
    values = [p["value"] for p in points]
    ticks = y_ticks(max(values, default=0), all(float(v).is_integer() for v in values))
    scale = ticks[-1]
    labels = [tick_label(t) for t in ticks]
    left = max(len(text) for text in labels) * LABEL_CHAR_WIDTH + 8  # gutter for the scale
    slot = (WIDTH - left) / len(points)
    bar = max(2.0, slot - 4)  # a 4px surface gap between bars
    shown = _x_labels(len(points))
    parts = [f'<svg class="chart" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{escape(title)}">']
    for tick, text in zip(ticks, labels):
        y = top + plot - plot * tick / scale
        if tick:
            parts.append(f'<line class="chart-grid" x1="{left}" x2="{WIDTH}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="chart-label" x="{left - 8}" y="{y:.1f}" text-anchor="end" '
                     f'dominant-baseline="middle">{escape(text)}</text>')
    parts.append(f'<line class="chart-axis" x1="{left}" x2="{WIDTH}" y1="{top + plot}" y2="{top + plot}"/>')
    for i, p in enumerate(points):
        x0 = left + i * slot
        x = x0 + (slot - bar) / 2
        h = plot * p["value"] / scale if p["value"] else 0
        y = top + plot - h
        parts.append(f'<g class="chart-mark"><title>{escape(p["tip"])}</title>'
                     f'<rect class="chart-hit" x="{x0:.1f}" y="0" width="{slot:.1f}" height="{height}"/>')
        if h:
            r = min(4.0, bar / 2, h)  # rounded data end, square on the baseline
            parts.append(
                f'<path class="chart-bar" d="M{x:.1f},{top + plot} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} '
                f'H{x + bar - r:.1f} Q{x + bar:.1f},{y:.1f} {x + bar:.1f},{y + r:.1f} V{top + plot} Z"/>')
        parts.append("</g>")
        if i in shown:
            parts.append(f'<text class="chart-label" x="{x0 + slot / 2:.1f}" y="{height - 6}" '
                         f'text-anchor="middle">{escape(p["label"])}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


def spark(points: list[dict], title: str, height: int = 60) -> Markup:
    """A small line for one series of a small multiple. Each point: label, value, tip.
    One point draws as a dot."""
    if not points:
        return Markup("")
    pad = 6
    most = max(p["value"] for p in points) or 1
    least = min(p["value"] for p in points)
    span = (most - least) or 1
    step = (WIDTH - 2 * pad) / max(1, len(points) - 1)

    def xy(i, v):
        x = pad if len(points) == 1 else pad + i * step
        y = pad + (height - 2 * pad) * (1 - (v - least) / span) if most != least else height / 2
        return x, y

    coords = [xy(i, p["value"]) for i, p in enumerate(points)]
    parts = [f'<svg class="chart chart--spark" viewBox="0 0 {WIDTH} {height}" role="img" '
             f'aria-label="{escape(title)}">']
    if len(coords) > 1:
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        parts.append(f'<polyline class="chart-line" points="{line}"/>')
    slot = WIDTH / len(points)
    for i, ((x, y), p) in enumerate(zip(coords, points)):
        parts.append(f'<g class="chart-mark"><title>{escape(p["tip"])}</title>'
                     f'<rect class="chart-hit" x="{max(0, x - slot / 2):.1f}" y="0" width="{slot:.1f}" height="{height}"/>'
                     f'<circle class="chart-dot" cx="{x:.1f}" cy="{y:.1f}" r="4"/></g>')
    parts.append("</svg>")
    return Markup("".join(parts))


def _smooth_path(coords: list[tuple[float, float]]) -> str:
    """An SVG path through the points as a smooth curve that never overshoots (monotone cubic
    interpolation): between two points it stays between their heights, and flat stretches stay flat.
    The curve passes through every point, so it is only the look that is smoothed, not the numbers."""
    n = len(coords)
    slopes = [(coords[i + 1][1] - coords[i][1]) / (coords[i + 1][0] - coords[i][0]) for i in range(n - 1)]
    tangents = [slopes[0]] + [0.0 if slopes[i - 1] * slopes[i] <= 0 else (slopes[i - 1] + slopes[i]) / 2
                              for i in range(1, n - 1)] + [slopes[-1]]
    for i, slope in enumerate(slopes):
        if slope == 0:
            tangents[i] = tangents[i + 1] = 0.0
            continue
        a, b = tangents[i] / slope, tangents[i + 1] / slope
        if a * a + b * b > 9:
            tau = 3 / math.sqrt(a * a + b * b)
            tangents[i], tangents[i + 1] = tau * a * slope, tau * b * slope
    d = [f"M{coords[0][0]:.1f},{coords[0][1]:.1f}"]
    for i in range(n - 1):
        (x0, y0), (x1, y1) = coords[i], coords[i + 1]
        h = x1 - x0
        d.append(f"C{x0 + h / 3:.1f},{y0 + tangents[i] * h / 3:.1f} {x1 - h / 3:.1f},{y1 - tangents[i + 1] * h / 3:.1f} "
                 f"{x1:.1f},{y1:.1f}")
    return " ".join(d)


def line_chart(points: list[dict], series_classes: list[str], title: str, height: int = 170,
               tick_label=str, width: int = WIDTH) -> Markup:
    """One to three lines over a labelled y scale with gridlines, for running totals. Each point: label,
    values (one number per series; None where a series has nothing, which breaks its line), tip (one
    tooltip for the whole slot). `series_classes` are the CSS classes of the lines: a dashed reference
    in the same unit has "chart-line--ref"; a projection "chart-line--projection" (hollow dots); and
    "chart-line--smooth" draws the line as a smooth curve through its points instead of straight
    segments. Dots are drawn while there are few enough points. A chart shown across the page can be
    drawn on a wider `width` so its text keeps its size."""
    if not points:
        return Markup("")
    top, bottom = 18, 22
    plot = height - top - bottom
    values = [v for p in points for v in p["values"] if v is not None]
    ticks = y_ticks(max(values, default=0), all(float(v).is_integer() for v in values))
    scale = ticks[-1]
    labels = [tick_label(t) for t in ticks]
    left = max(len(text) for text in labels) * LABEL_CHAR_WIDTH + 8
    slot = (width - left) / len(points)
    shown = _x_labels(len(points))
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for tick, text in zip(ticks, labels):
        y = top + plot - plot * tick / scale
        if tick:
            parts.append(f'<line class="chart-grid" x1="{left}" x2="{width}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="chart-label" x="{left - 8}" y="{y:.1f}" text-anchor="end" '
                     f'dominant-baseline="middle">{escape(text)}</text>')
    parts.append(f'<line class="chart-axis" x1="{left}" x2="{width}" y1="{top + plot}" y2="{top + plot}"/>')
    for index, css in enumerate(series_classes):
        runs, run = [], []
        for i, p in enumerate(points):
            value = p["values"][index]
            if value is None:
                if run:
                    runs.append(run)
                run = []
            else:
                run.append((left + (i + 0.5) * slot, top + plot - plot * float(value) / scale))
        if run:
            runs.append(run)
        for coords in runs:
            if len(coords) > 1 and "--smooth" in css:
                parts.append(f'<path class="{escape(css)}" d="{_smooth_path(coords)}"/>')
            elif len(coords) > 1:
                line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
                parts.append(f'<polyline class="{escape(css)}" points="{line}"/>')
        if len(points) <= 31:
            dot = ("chart-dot chart-dot--projection" if "--projection" in css
                   else "chart-dot chart-dot--ref" if "--ref" in css else "chart-dot")
            parts.extend(f'<circle class="{dot}" cx="{x:.1f}" cy="{y:.1f}" r="3.5"/>' for coords in runs for x, y in coords)
    for i, p in enumerate(points):
        x0 = left + i * slot
        parts.append(f'<g class="chart-mark"><title>{escape(p["tip"])}</title>'
                     f'<rect class="chart-hit" x="{x0:.1f}" y="0" width="{slot:.1f}" height="{height}"/></g>')
        if i in shown:
            parts.append(f'<text class="chart-label" x="{x0 + slot / 2:.1f}" y="{height - 6}" '
                         f'text-anchor="middle">{escape(p["label"])}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))
