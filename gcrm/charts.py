"""Small server-drawn SVG charts for the Statistics page: no script, no outside
service. One series per chart in one hue (several measures get several charts,
never a second axis); every bar or point has a full-height hover target whose
<title> is its tooltip; text is drawn in text colours, not the series colour.
Colours come from the page's CSS (classes chart-*), so the theme applies."""
from html import escape

from markupsafe import Markup

WIDTH = 600
MAX_X_LABELS = 6


def _x_labels(count: int) -> set[int]:
    """Which positions get an x label: at most MAX_X_LABELS, always the last."""
    step = max(1, -(-count // MAX_X_LABELS))
    return {i for i in range(count) if (count - 1 - i) % step == 0}


def bar_chart(points: list[dict], title: str, height: int = 150) -> Markup:
    """Vertical bars over a baseline. Each point: label, value (number), tip (tooltip text)."""
    if not points:
        return Markup("")
    top, bottom = 18, 22
    plot = height - top - bottom
    most = max((p["value"] for p in points), default=0) or 1
    slot = WIDTH / len(points)
    bar = max(2.0, slot - 4)  # a 4px surface gap between bars
    shown = _x_labels(len(points))
    parts = [
        f'<svg class="chart" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{escape(title)}">',
        f'<line class="chart-axis" x1="0" x2="{WIDTH}" y1="{top + plot}" y2="{top + plot}"/>',
    ]
    for i, p in enumerate(points):
        x = i * slot + (slot - bar) / 2
        h = plot * p["value"] / most if p["value"] else 0
        y = top + plot - h
        parts.append(f'<g class="chart-mark"><title>{escape(p["tip"])}</title>'
                     f'<rect class="chart-hit" x="{i * slot:.1f}" y="0" width="{slot:.1f}" height="{height}"/>')
        if h:
            r = min(4.0, bar / 2, h)  # rounded data end, square on the baseline
            parts.append(
                f'<path class="chart-bar" d="M{x:.1f},{top + plot} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} '
                f'H{x + bar - r:.1f} Q{x + bar:.1f},{y:.1f} {x + bar:.1f},{y + r:.1f} V{top + plot} Z"/>')
        parts.append("</g>")
        if i in shown:
            parts.append(f'<text class="chart-label" x="{i * slot + slot / 2:.1f}" y="{height - 6}" '
                         f'text-anchor="middle">{escape(p["label"])}</text>')
    parts.append(f'<text class="chart-label" x="2" y="12">{escape(points[0].get("max_label", ""))}</text>')
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
