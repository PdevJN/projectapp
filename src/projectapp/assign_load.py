"""アサイン専用画面(要望 168 段階 5)の負荷のヒストグラムの SVG と要約。文字列だけで、NiceGUI に依存しない。

棒は稼働日ごとの負荷(1.0 = 100%)。0〜200% で固定し(`LOAD_SCALE`)、100% に点線を引く。100% 超の棒は超過の色にする。
"""

from datetime import date

from projectapp.dashboard_view import LOAD_COLOR, LOAD_SCALE, OVER_COLOR
from projectapp.timeline import OVERLOAD_EPSILON

BAR_PX = 4
BAR_GAP_PX = 1
CHART_HEIGHT_PX = 48


def load_svg(days: list[tuple[date, float]]) -> str:
    """稼働日ごとの負荷の棒。負荷が 0 の日は棒を出さない。棒にマウスを重ねると`m/d 120%`。"""
    step = BAR_PX + BAR_GAP_PX
    width = max(len(days) * step, 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{CHART_HEIGHT_PX}"'
        f' viewBox="0 0 {width} {CHART_HEIGHT_PX}" role="img" style="display: block">'
    ]
    for index, (day, total) in enumerate(days):
        if total <= 0:
            continue
        height = CHART_HEIGHT_PX * min(total, LOAD_SCALE) / LOAD_SCALE
        color = OVER_COLOR if total > 1.0 + OVERLOAD_EPSILON else LOAD_COLOR
        parts.append(
            f'<rect x="{index * step}" y="{CHART_HEIGHT_PX - height:.1f}" width="{BAR_PX}"'
            f' height="{height:.1f}" fill="{color}">'
            f"<title>{day.month}/{day.day} {total * 100:.0f}%</title></rect>"
        )
    reference = CHART_HEIGHT_PX / LOAD_SCALE
    parts.append(
        f'<line x1="0" x2="{width}" y1="{reference:.1f}" y2="{reference:.1f}"'
        ' stroke="currentColor" stroke-opacity="0.6" stroke-width="1" stroke-dasharray="3 3"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


def load_summary(days: list[tuple[date, float]]) -> str:
    """`最大 130%・100% 超 3 日`。稼働日がなければ`稼働日がありません`。"""
    if not days:
        return "稼働日がありません"
    peak = max(total for _, total in days)
    over = sum(1 for _, total in days if total > 1.0 + OVERLOAD_EPSILON)
    return f"最大 {peak * 100:.0f}%・100% 超 {over} 日"
