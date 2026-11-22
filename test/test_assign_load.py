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
    overlay_summary,
    overlay_svg,
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


def members(*rows: tuple[str, str, list[float]]):
    return [(n, c, days(*t)) for n, c, t in rows]


def test_overlay_draws_every_member_from_the_baseline() -> None:
    svg = overlay_svg(members(("田中", "red", [0.8]), ("佐藤", "blue", [0.5])))
    assert svg.count("<rect") == 2
    half = CHART_HEIGHT_PX / 2
    # 100% の点線は個人の上限として 1 本(0〜200% 固定)
    assert f'y1="{half:.1f}" y2="{half:.1f}"' in svg
    assert 'fill="red" fill-opacity="0.45"' in svg and 'fill="blue"' in svg
    # どの棒も下端(y + height = 48)に届く
    assert 'y="28.8" width="4" height="19.2"' in svg  # 80%
    assert 'y="36.0" width="4" height="12.0"' in svg  # 50%


def test_overlay_draws_the_larger_bar_first_so_the_smaller_stays_visible() -> None:
    svg = overlay_svg(members(("小", "blue", [0.3]), ("大", "red", [0.9])))
    assert svg.index('fill="red"') < svg.index('fill="blue"')


def test_overlay_over_100_percent_shows_only_the_excess_in_the_overload_color() -> None:
    svg = overlay_svg(members(("田中", "red", [1.2])))
    assert svg.count("<rect") == 2
    assert svg.count(f'fill="{OVER_COLOR}"') == 1 and svg.count('fill="red"') == 1


def test_overlay_hover_lists_everyone_that_day() -> None:
    svg = overlay_svg(members(("田中", "red", [0.8]), ("佐藤", "blue", [0.5])))
    assert svg.count("<title>11/16 田中 80%・佐藤 50%</title>") == 2


def test_overlay_height_is_clamped_at_200_percent() -> None:
    svg = overlay_svg(members(("田中", "red", [2.5])))
    assert 'y="0.0" width="4" height="24.0"' in svg


def test_overlay_tolerates_members_with_no_or_short_load_lists() -> None:
    rows = [
        ("田中", "red", days(0.5, 1.2)),
        ("佐藤", "blue", []),
        ("鈴木", "g", days(0.3)),
    ]
    assert overlay_svg(rows).count("<rect") == 4  # 0.5, 1.2(2 本), 0.3
    assert overlay_summary(rows) == "最大 120%・100% 超 1 人日"
    assert "<rect" not in overlay_svg([("田中", "red", []), ("佐藤", "blue", [])])
    assert overlay_summary([]) == "稼働日がありません"
    assert "<rect" not in overlay_svg([])


def test_overlay_can_be_drawn_larger() -> None:
    small = overlay_svg(members(("田中", "red", [0.5, 0.5])))
    large = overlay_svg(members(("田中", "red", [0.5, 0.5])), 8, 96)
    assert 'width="10" height="48"' in small
    assert 'width="18" height="96"' in large
