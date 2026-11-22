from datetime import date

from projectapp.assign_load import (
    BAR_GAP_PX,
    BAR_PX,
    CHART_HEIGHT_PX,
    MEMBER_COLORS,
    MEMBER_CSS,
    load_summary,
    load_svg,
    member_color,
)
from projectapp.dashboard_view import LOAD_COLOR, OVER_COLOR


def days(*totals: float) -> list[tuple[date, float]]:
    return [(date(2026, 11, 16 + i), total) for i, total in enumerate(totals)]


def test_each_day_with_a_load_is_a_bar_with_a_tooltip() -> None:
    svg = load_svg(days(0.5, 1.0))
    assert svg.count("<rect") == 2
    assert "<title>11/16 50%</title>" in svg and "<title>11/17 100%</title>" in svg
    assert f'width="{2 * (BAR_PX + BAR_GAP_PX)}"' in svg


def test_a_day_without_a_load_has_no_bar() -> None:
    assert load_svg(days(0.0, 0.0)).count("<rect") == 0


def test_bars_over_100_percent_show_only_the_excess_in_the_overload_color() -> None:
    svg = load_svg(days(1.0, 1.2))
    assert svg.count("<rect") == 3  # 100% の棒、120% の棒の下の 100% と上の 20%
    assert svg.count(f'fill="{OVER_COLOR}"') == 1
    assert svg.count(f'fill="{LOAD_COLOR}"') == 2


def test_the_bar_color_can_be_given_per_member() -> None:
    svg = load_svg(days(0.5, 1.2), color="red")
    assert svg.count('fill="red"') == 2 and LOAD_COLOR not in svg
    assert svg.count(f'fill="{OVER_COLOR}"') == 1


def test_member_colors_follow_the_member_order_and_wrap() -> None:
    assert member_color(0) == "var(--assign-member-0)"
    assert member_color(len(MEMBER_COLORS)) == member_color(0)
    assert len(set(MEMBER_COLORS)) == len(MEMBER_COLORS) == 7
    assert OVER_COLOR not in MEMBER_COLORS
    assert "--assign-member-6" in MEMBER_CSS and "body--dark" in MEMBER_CSS


def test_the_bar_height_is_clamped_at_200_percent() -> None:
    svg = load_svg(days(1.0, 2.5))
    half = CHART_HEIGHT_PX / 2
    assert f'y="{half:.1f}" width="{BAR_PX}" height="{half:.1f}"' in svg  # 100%
    # 250% は端で止まる(100% の下の半分は 2 本とも、上の半分は超過の色)
    assert svg.count(f'y="0.0" width="{BAR_PX}" height="{half:.1f}"') == 1


def test_the_100_percent_reference_line_is_dotted() -> None:
    svg = load_svg(days(0.5))
    half = CHART_HEIGHT_PX / 2
    assert f'y1="{half:.1f}" y2="{half:.1f}"' in svg and "stroke-dasharray" in svg


def test_an_empty_list_still_draws_a_valid_svg() -> None:
    svg = load_svg([])
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "<rect" not in svg


def test_the_summary_names_the_peak_and_the_overloaded_days() -> None:
    assert load_summary(days(0.5, 1.3, 1.1, 1.0)) == "最大 130%・100% 超 2 日"
    assert load_summary(days(0.5, 1.0)) == "最大 100%・100% 超 0 日"
    assert load_summary([]) == "稼働日がありません"
