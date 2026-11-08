"""The server-drawn charts: one hue, a hover tooltip per mark, escaped text."""
from gcrm.charts import _x_labels, bar_chart, spark, y_ticks


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


def test_the_y_scale_uses_round_steps_up_past_the_largest_value():
    assert y_ticks(5, whole=True) == [0, 2, 4, 6]
    assert y_ticks(662, whole=True) == [0, 200, 400, 600, 800]
    assert y_ticks(1.3, whole=False) == [0, 0.5, 1, 1.5]
    assert y_ticks(10, whole=True) == [0, 5, 10]


def test_counts_never_get_a_fractional_step_and_all_zero_still_has_a_scale():
    assert y_ticks(2, whole=True) == [0, 1, 2]
    assert y_ticks(0, whole=True) == [0, 1]


def test_bars_draw_a_labelled_scale_and_gridlines_and_scale_to_its_top():
    svg = str(bar_chart(_points([0, 3, 5]), "Activities", tick_label=lambda v: f"{v:g} h"))
    for label in ("0 h", "2 h", "4 h", "6 h"):
        assert f">{label}</text>" in svg
    assert svg.count('class="chart-grid"') == 3  # one per step above the baseline
    assert "max" not in svg


from gcrm.charts import line_chart  # noqa: E402


def _line_points(first, second=None):
    return [{"label": f"M{i}", "values": [v] if second is None else [v, second[i]], "tip": f"M{i}: {v}"}
            for i, v in enumerate(first)]


def test_a_line_chart_has_a_tooltip_per_slot_a_labelled_scale_and_one_line_per_series():
    svg = str(line_chart(_line_points([1000, 2500, 4000]), ["chart-line"], "Running total"))
    assert svg.count("<title>") == 3 and "<title>M2: 4000</title>" in svg
    assert svg.count("<polyline") == 1 and svg.count("<circle") == 3
    assert 'role="img" aria-label="Running total"' in svg and 'class="chart-grid"' in svg


def test_a_second_series_is_a_reference_line_on_the_same_scale():
    svg = str(line_chart(_line_points([100, 200, 300], [500, 500, 500]), ["chart-line", "chart-line chart-line--ref"],
                         "Money in vs target"))
    assert svg.count("<polyline") == 2 and 'class="chart-line chart-line--ref"' in svg
    assert svg.count("<title>") == 3                                       # still one tooltip per slot, not per line
    assert ">500<" in svg or ">600<" in svg or ">400<" in svg                # the scale reaches the larger series


def test_a_single_point_is_a_dot_and_nothing_draws_nothing():
    svg = str(line_chart(_line_points([5]), ["chart-line"], "x"))
    assert "<polyline" not in svg and svg.count("<circle") == 1
    assert str(line_chart([], ["chart-line"], "x")) == ""


def test_line_chart_text_is_escaped_and_money_ticks_use_the_formatter():
    svg = str(line_chart([{"label": "<b>", "values": [1000], "tip": "a & b"}], ["chart-line"], "x < y",
                         tick_label=lambda v: f"{v:g} €"))
    assert "<b>" not in svg and "&lt;b&gt;" in svg and "a &amp; b" in svg and 'aria-label="x &lt; y"' in svg
    assert "€" in svg


import re  # noqa: E402


def test_a_gap_breaks_a_line_and_a_lone_point_is_a_dot():
    gap = [{"label": f"M{i}", "values": [v], "tip": f"M{i}"} for i, v in enumerate([None, None, 100, 200, 300])]
    svg = str(line_chart(gap, ["chart-line"], "x"))
    assert svg.count("<polyline") == 1 and svg.count("<circle") == 3 and svg.count("<title>") == 5
    split = [{"label": f"M{i}", "values": [v], "tip": f"M{i}"} for i, v in enumerate([10, None, 30])]
    svg = str(line_chart(split, ["chart-line"], "x"))
    assert "<polyline" not in svg and svg.count("<circle") == 2


def test_a_series_that_ends_early_still_scales_to_the_largest_visible_value():
    points = [{"label": f"M{i}", "values": [a, b], "tip": f"M{i}"} for i, (a, b) in enumerate([(100, 300), (None, 900)])]
    svg = str(line_chart(points, ["chart-line", "chart-line chart-line--ref"], "x"))
    assert ">1000<" in svg or ">1200<" in svg                               # the scale reaches 900


def _smooth_segments(svg: str):
    path = re.search(r'<path class="chart-line chart-line--smooth" d="([^"]+)"', svg).group(1)
    start = re.match(r"M([\d.\-]+),([\d.\-]+)", path)
    y0 = float(start.group(2))
    segments = []
    for c in re.finditer(r"C([\d.\-]+),([\d.\-]+) ([\d.\-]+),([\d.\-]+) ([\d.\-]+),([\d.\-]+)", path):
        _, y1, _, y2, _, y = (float(g) for g in c.groups())
        segments.append((y0, y1, y2, y))
        y0 = y
    return segments


def test_a_smooth_series_is_a_curve_that_never_overshoots_and_stays_flat_where_the_data_is_flat():
    values = [0, 0, 100, 400, 400, 900]
    points = [{"label": f"M{i}", "values": [v], "tip": f"M{i}"} for i, v in enumerate(values)]
    svg = str(line_chart(points, ["chart-line chart-line--smooth"], "x"))
    assert "<polyline" not in svg
    segments = _smooth_segments(svg)
    assert len(segments) == 5
    for (y0, c1, c2, y1), (a, b) in zip(segments, zip(values, values[1:])):
        low, high = min(y0, y1) - 0.06, max(y0, y1) + 0.06
        assert low <= c1 <= high and low <= c2 <= high                       # no wobble beyond its two neighbours
        if a == b:
            assert abs(c1 - y0) < 0.06 and abs(c2 - y0) < 0.06               # a flat stretch is drawn flat


def test_a_smooth_series_with_two_points_is_still_drawn():
    points = [{"label": "A", "values": [1], "tip": "A"}, {"label": "B", "values": [5], "tip": "B"}]
    assert 'class="chart-line chart-line--smooth"' in str(line_chart(points, ["chart-line chart-line--smooth"], "x"))


def test_projection_dots_are_hollow():
    points = [{"label": "A", "values": [1], "tip": "A"}, {"label": "B", "values": [5], "tip": "B"}]
    svg = str(line_chart(points, ["chart-line chart-line--projection chart-line--smooth"], "x"))
    assert 'class="chart-dot chart-dot--projection"' in svg


def test_a_line_chart_can_be_drawn_on_a_wider_canvas():
    svg = str(line_chart(_line_points([1, 2, 3]), ["chart-line"], "x", width=900))
    assert 'viewBox="0 0 900 170"' in svg and 'x2="900"' in svg
    assert 'viewBox="0 0 600 170"' in str(line_chart(_line_points([1, 2, 3]), ["chart-line"], "x"))


def test_the_assumed_new_sales_line_has_its_own_dot_style():
    points = [{"label": "A", "values": [1, 2], "tip": "A"}, {"label": "B", "values": [5, 7], "tip": "B"}]
    svg = str(line_chart(points, ["chart-line", "chart-line chart-line--assumed chart-line--smooth"], "x"))
    assert 'class="chart-dot chart-dot--assumed"' in svg and 'class="chart-line chart-line--assumed chart-line--smooth"' in svg


def test_a_wanted_tick_step_is_used_when_it_gives_a_readable_number_of_marks():
    from gcrm.charts import y_ticks
    assert y_ticks(88000, False, 10000) == [i * 10000 for i in range(10)]
    assert y_ticks(138000, False, 20000) == [i * 20000 for i in range(8)]
    assert y_ticks(15000, False, 10000) == y_ticks(15000, False)                   # only 2 marks: automatic instead
    assert y_ticks(900000, False, 10000) == y_ticks(900000, False)                 # 90 marks: automatic instead


def test_a_bar_can_carry_an_assumed_part_stacked_on_top():
    points = [{"label": "A", "value": 10, "tip": "A"}, {"label": "B", "value": 0, "assumed": 6, "tip": "B"},
              {"label": "C", "value": 4, "assumed": 6, "tip": "C"}]
    svg = str(bar_chart(points, "x"))
    assert svg.count('class="chart-bar chart-bar--assumed"') == 2 and svg.count('class="chart-bar"') == 2


def test_a_limit_is_a_dashed_line_that_the_scale_always_reaches():
    svg = str(bar_chart(_points([2, 4]), "x", limit=30))
    assert svg.count('class="chart-limit"') == 1
    assert 'class="chart-bar"' in svg
    top = [float(m) for m in __import__("re").findall(r'<line class="chart-limit" x1="[\d.]+" x2="[\d.]+" y1="([\d.]+)"', svg)]
    assert top and top[0] <= 20                                                  # near the top of the plot: the scale grew to the limit
    assert "chart-limit" not in str(bar_chart(_points([2, 4]), "x"))
    assert "chart-limit" not in str(bar_chart(_points([2, 4]), "x", limit=None))


def test_a_bar_chart_can_be_drawn_wider_with_more_labels_on_the_axis():
    import re
    points = _points(list(range(1, 53)))
    narrow = str(bar_chart(points, "x"))
    wide = str(bar_chart(points, "x", width=1400, max_labels=14))
    assert 'viewBox="0 0 600 150"' in narrow and 'viewBox="0 0 1400 150"' in wide
    count = lambda svg: len(re.findall(r'<text class="chart-label" x="[\d.]+" y="\d+" text-anchor="middle">', svg))   # noqa: E731
    assert count(narrow) <= 6 and 10 <= count(wide) <= 14
    assert wide.count("<title>") == 52 and 'x2="1400"' in wide


def test_a_line_chart_can_name_more_points_on_its_axis():
    import re

    from gcrm.charts import line_chart
    points = [{"label": f"{i:02d}.2027", "values": [float(i)], "tip": "t"} for i in range(1, 15)]
    count = lambda svg: len(re.findall(r'text-anchor="middle">\d\d\.2027<', svg))   # noqa: E731
    assert count(str(line_chart(points, ["chart-line"], "x"))) <= 6
    assert 10 <= count(str(line_chart(points, ["chart-line"], "x", width=1400, max_labels=14))) <= 14
