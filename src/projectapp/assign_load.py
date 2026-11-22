"""アサイン専用画面(要望 168 段階 5)の負荷のヒストグラムの SVG と要約。文字列だけで、NiceGUI に依存しない。

棒は稼働日ごとの負荷(1.0 = 100%)。0〜200% で固定し(`LOAD_SCALE`)、100% に点線を引く。
棒はメンバーの色。100% を超えた分だけを超過の色にする。
"""

from datetime import date

from projectapp.dashboard_view import LOAD_COLOR, LOAD_SCALE, OVER_COLOR
from projectapp.timeline import OVERLOAD_EPSILON

# メンバーの色(dataviz の検証済みの並びの 1〜7。8 番目の赤は超過の色なので使わない)。明るい・暗いテーマで値が変わる
MEMBER_COLORS = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
)
MEMBER_COLORS_DARK = (
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#0ca30c",
    "#9085e9",
)
MEMBER_CSS = (
    "body { "
    + " ".join(f"--assign-member-{i}: {c};" for i, c in enumerate(MEMBER_COLORS))
    + " }\nbody.body--dark { "
    + " ".join(f"--assign-member-{i}: {c};" for i, c in enumerate(MEMBER_COLORS_DARK))
    + " }"
)

BAR_PX = 4
BAR_GAP_PX = 1
CHART_HEIGHT_PX = 48


def member_color(index: int) -> str:
    """メンバー一覧の何番目かで決まる色(CSS 変数。明るい・暗いテーマで切り替わる)。7 人を超えたら繰り返す。"""
    return f"var(--assign-member-{index % len(MEMBER_COLORS)})"


def load_svg(days: list[tuple[date, float]], color: str = LOAD_COLOR) -> str:
    """稼働日ごとの負荷の棒。負荷が 0 の日は棒を出さない。棒にマウスを重ねると`m/d 120%`。

    100% までは`color`、超えた分は超過の色で、同じ棒に重ねる。"""
    step = BAR_PX + BAR_GAP_PX
    width = max(len(days) * step, 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{CHART_HEIGHT_PX}"'
        f' viewBox="0 0 {width} {CHART_HEIGHT_PX}" role="img" style="display: block">'
    ]
    for index, (day, total) in enumerate(days):
        if total <= 0:
            continue
        title = f"<title>{day.month}/{day.day} {total * 100:.0f}%</title>"
        shown = min(total, LOAD_SCALE)
        base = min(shown, 1.0) if total > 1.0 + OVERLOAD_EPSILON else shown
        segments = [(0.0, base, color)]
        if total > 1.0 + OVERLOAD_EPSILON:
            segments.append((1.0, shown, OVER_COLOR))
        for low, high, fill in segments:
            top = CHART_HEIGHT_PX * high / LOAD_SCALE
            height = CHART_HEIGHT_PX * (high - low) / LOAD_SCALE
            parts.append(
                f'<rect x="{index * step}" y="{CHART_HEIGHT_PX - top:.1f}" width="{BAR_PX}"'
                f' height="{height:.1f}" fill="{fill}">{title}</rect>'
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
