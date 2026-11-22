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


OVERLAY_BAR_PX = 20  # 日付を毎日書けるだけの幅
AXIS_HEIGHT_PX = 14
OVERLAY_HEIGHT_PX = 96
OVERLAY_OPACITY = 0.45

Overlay = list[tuple[str, str, list[tuple[date, float]]]]


def _overlay_days(members: Overlay) -> list[date]:
    """重ねる日付。人ごとの日リストの長さが違う(負荷のない人は空)ので、いちばん長いものを使う。"""
    return [d for d, _ in max((days for _, _, days in members), key=len, default=[])]


def _value(days: list[tuple[date, float]], index: int) -> float:
    return days[index][1] if index < len(days) else 0.0


def overlay_svg(
    members: Overlay,
    bar_px: int = BAR_PX,
    height_px: int = CHART_HEIGHT_PX,
    labels: bool = False,
) -> str:
    """表示中のメンバー(名前・色・稼働日ごとの負荷)の棒を、同じ位置に半透明で重ねる。

    縦は個人ごとの行と同じ 0〜200%(100% に点線)。負荷の大きい棒を奥に描き、小さい棒が隠れないようにする。
    100% を超えた分は超過の色。ホバーには、その日の全員の値を出す。
    `labels`なら、棒の下に毎日の日付(`16`。最初の日と月が変わる日は`11/16`)を書く。"""
    dates = _overlay_days(members)
    step = bar_px + BAR_GAP_PX
    width = max(len(dates) * step, 1)
    total_height = height_px + (AXIS_HEIGHT_PX if labels else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}"'
        f' viewBox="0 0 {width} {total_height}" role="img" style="display: block">'
    ]
    for index, day in enumerate(dates):
        today = [
            (name, color, _value(days, index))
            for name, color, days in members
            if _value(days, index) > 0
        ]
        title = (
            f"<title>{day.month}/{day.day} "
            + "・".join(f"{name} {value * 100:.0f}%" for name, _, value in today)
            + "</title>"
        )
        for _, color, value in sorted(today, key=lambda row: -row[2]):
            over = value > 1.0 + OVERLOAD_EPSILON
            segments = [
                (0.0, min(value, 1.0) if over else min(value, LOAD_SCALE), color)
            ]
            if over:
                segments.append((1.0, min(value, LOAD_SCALE), OVER_COLOR))
            for low, high, fill in segments:
                top = height_px * high / LOAD_SCALE
                height = height_px * (high - low) / LOAD_SCALE
                parts.append(
                    f'<rect x="{index * step}" y="{height_px - top:.1f}" width="{bar_px}"'
                    f' height="{height:.1f}" fill="{fill}" fill-opacity="{OVERLAY_OPACITY}"'
                    f' stroke="{fill}" stroke-width="1">{title}</rect>'
                )
    reference = height_px / LOAD_SCALE
    parts.append(
        f'<line x1="0" x2="{width}" y1="{reference:.1f}" y2="{reference:.1f}"'
        ' stroke="currentColor" stroke-opacity="0.6" stroke-width="1" stroke-dasharray="3 3"/>'
    )
    if labels:
        for index, day in enumerate(dates):
            new_month = index == 0 or day.month != dates[index - 1].month
            text = f"{day.month}/{day.day}" if new_month else str(day.day)
            parts.append(
                f'<text x="{index * step + bar_px / 2:.1f}" y="{height_px + 11}"'
                ' text-anchor="middle" font-size="10" fill="currentColor"'
                f' fill-opacity="0.75">{text}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def overlay_summary(members: Overlay) -> str:
    """`最大 130%・100% 超 3 人日`(個人の最大と、100% を超えた人×日の数)。稼働日がなければ`稼働日がありません`。"""
    if not _overlay_days(members):
        return "稼働日がありません"
    values = [value for _, _, days in members for _, value in days]
    peak = max(values, default=0.0)
    over = sum(1 for value in values if value > 1.0 + OVERLOAD_EPSILON)
    return f"最大 {peak * 100:.0f}%・100% 超 {over} 人日"
