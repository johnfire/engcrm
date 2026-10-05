"""The server-drawn charts: one hue, a hover tooltip per mark, escaped text."""
from gcrm.charts import _x_labels, bar_chart, spark


def _points(values):
    return [{"label": f"W{i}", "value": v, "tip": f"W{i}: {v} h"} for i, v in enumerate(values)]


def test_bars_have_a_tooltip_each_and_scale_to_the_largest():
    svg = str(bar_chart(_points([0, 2, 4]), "Hours worked"))
    assert svg.count("<title>") == 3 and "<title>W2: 4 h</title>" in svg
    assert svg.count('class="chart-bar"') == 2  # a zero draws no bar, but keeps its tooltip
    assert 'role="img" aria-label="Hours worked"' in svg


def test_text_is_escaped():
    svg = str(bar_chart([{"label": "<b>", "value": 1, "tip": "a & b"}], "x < y"))
    assert "<b>" not in svg and "&lt;b&gt;" in svg and "a &amp; b" in svg and 'aria-label="x &lt; y"' in svg


def test_at_most_six_x_labels_and_always_the_last():
    shown = _x_labels(12)
    assert len(shown) <= 6 and 11 in shown
    assert _x_labels(3) == {0, 1, 2}


def test_a_single_point_line_is_a_dot():
    svg = str(spark(_points([5]), "Prospects"))
    assert "<polyline" not in svg and svg.count("<circle") == 1
    assert str(spark(_points([1, 3, 2]), "Prospects")).count("<circle") == 3


def test_no_points_draw_nothing():
    assert str(bar_chart([], "x")) == "" and str(spark([], "x")) == ""
