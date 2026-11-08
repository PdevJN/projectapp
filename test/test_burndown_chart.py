"""残りの工数の推移の SVG(要望 128 段階 2)。"""

import re
from dataclasses import replace
from datetime import date

from projectapp.burndown import Burndown, Mark
from projectapp.burndown_chart import chart_svg, y_scale


def sample(**changes: object) -> Burndown:
    base = Burndown(
        first=date(2026, 11, 2),
        last=date(2026, 11, 8),
        known=True,
        since=date(2026, 10, 26),
        count=3,
        initial=14.0,
        actual=(14.0, 15.0, 10.0),
        planned=(10.0, 6.0, 2.0, 0.0, 0.0, 0.0, 0.0),
        future=(10.0, 6.0, 3.0, 0.0, 0.0),
        workdays=(True, True, True, True, True, False, False),
        today_index=2,
        now_fraction=0.5,
        marks=(Mark(date(2026, 11, 3), ("A",)),),
    )
    return replace(base, **changes)


def lines(svg: str) -> list[str]:
    return re.findall(r"<polyline[^>]*>", svg)


def test_y_scale_picks_a_round_ceiling_and_step() -> None:
    assert y_scale(14.0) == (15.0, 5.0)
    assert y_scale(100.0) == (100.0, 50.0)
    assert y_scale(0.0) == (1.0, 0.5)


def test_three_lines_are_told_apart_by_shape_as_well_as_color() -> None:
    drawn = lines(chart_svg(sample()))
    assert len(drawn) == 3
    assert sum('stroke-dasharray="2 4"' in line for line in drawn) == 1  # 当初の予定
    assert sum('stroke-dasharray="6 4"' in line for line in drawn) == 1  # 今後の予定
    assert sum("stroke-dasharray" not in line for line in drawn) == 1  # 実際


def test_the_today_line_is_drawn_only_when_today_is_in_the_period() -> None:
    assert 'class="today"' in chart_svg(sample())
    svg = chart_svg(sample(today_index=None, future=(), actual=(14.0,) * 7))
    assert 'class="today"' not in svg
    assert len(lines(svg)) == 2  # 当初の予定と実際だけ


def test_before_the_period_only_the_first_plan_is_drawn() -> None:
    svg = chart_svg(sample(today_index=None, future=(), actual=()))
    assert len(lines(svg)) == 1


def test_days_off_get_a_band() -> None:
    assert chart_svg(sample()).count('class="band"') == 2


def test_each_mark_is_a_triangle_with_the_task_names() -> None:
    svg = chart_svg(sample(marks=(Mark(date(2026, 11, 3), ("A", "B")),)))
    assert svg.count('class="mark"') == 1
    assert "進捗度を入力(A、B)" in svg


def test_task_names_are_escaped() -> None:
    svg = chart_svg(sample(marks=(Mark(date(2026, 11, 3), ("<b>x</b>",)),)))
    assert "<b>x</b>" not in svg and "&lt;b&gt;x&lt;/b&gt;" in svg


def test_the_actual_points_say_their_day_and_value() -> None:
    svg = chart_svg(sample())
    assert "11/02 残り 14.0h" in svg and "11/04 残り 10.0h" in svg


def test_a_flat_zero_chart_does_not_divide_by_zero() -> None:
    svg = chart_svg(sample(initial=0.0, actual=(0.0, 0.0, 0.0), planned=(0.0,) * 7, future=(0.0,) * 5, marks=()))
    assert svg.startswith("<svg") and "nan" not in svg.lower()
