"""残りの工数の推移の SVG(要望 128 段階 2)。NiceGUI に依存しない。

横軸は期間の日(位置 i は i 日目の始め = i-1 日目の終わり)、縦軸は残りの工数[h]。
"""

import html
from datetime import timedelta
from math import ceil, floor, log10

from projectapp.burndown import Burndown

WIDTH, HEIGHT = 640, 250
LEFT, RIGHT, TOP, BOTTOM = 46, 14, 30, 36
PLANNED_COLOR = "#8a8f98"
ACTUAL_COLOR = "var(--q-primary, #1976d2)"
FUTURE_COLOR = "var(--q-secondary, #26a69a)"
TODAY_COLOR = "var(--today, #e53935)"


def y_scale(value: float) -> tuple[float, float]:
    """縦軸の上端と目盛りの間隔(1・2・5 × 10^k)。目盛りはおよそ 4 本。"""
    top = max(value, 1.0)
    raw = top / 4
    unit = 10 ** floor(log10(raw))
    step = next(m * unit for m in (1, 2, 5, 10) if m * unit >= raw)
    return float(step * ceil(top / step - 1e-9)), float(step)


def _line(
    points: list[tuple[float, float]], color: str, width: float, dash: str | None
) -> str:
    if len(points) < 2:
        return ""
    coords = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline fill="none" stroke="{color}" stroke-width="{width}"'
        f'{dash_attr} points="{coords}"/>'
    )


def chart_svg(b: Burndown) -> str:
    days = (b.last - b.first).days + 1
    plot_w, plot_h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    ceiling, step = y_scale(max([b.initial, *b.actual, *b.planned, *b.future]))

    def x(position: float) -> float:
        return LEFT + plot_w * position / days

    def y(value: float) -> float:
        return TOP + plot_h * (1 - value / ceiling)

    parts: list[str] = []
    for index, open_ in enumerate(b.workdays):  # 休みの日の帯
        if not open_:
            parts.append(
                f'<rect class="band" x="{x(index):.1f}" y="{TOP}" width="{plot_w / days:.1f}" '
                f'height="{plot_h}" fill="currentColor" opacity="0.06"/>'
            )
    for tick in range(round(ceiling / step) + 1):  # 横線と目盛り
        value = tick * step
        parts.append(
            f'<line x1="{LEFT}" y1="{y(value):.1f}" x2="{WIDTH - RIGHT}" y2="{y(value):.1f}" '
            f'stroke="currentColor" opacity="0.15"/>'
        )
        parts.append(
            f'<text x="{LEFT - 6}" y="{y(value) + 3:.1f}" text-anchor="end" font-size="10" '
            f'fill="currentColor" opacity="0.7">{value:g}</text>'
        )
    label_every = max(1, ceil(days / 10))
    for index in range(0, days, label_every):  # 日付
        day = b.first + timedelta(index)
        parts.append(
            f'<text x="{x(index + 0.5):.1f}" y="{HEIGHT - BOTTOM + 14}" text-anchor="middle" '
            f'font-size="10" fill="currentColor" opacity="0.7">{day:%m/%d}</text>'
        )
    planned = [(0.0, b.initial)] + [(i + 1.0, v) for i, v in enumerate(b.planned)]
    parts.append(_line([(x(p), y(v)) for p, v in planned], PLANNED_COLOR, 2, "2 4"))
    actual = [(0.0, b.initial)]
    for index, value in enumerate(b.actual):
        today = b.today_index == index
        actual.append((index + (b.now_fraction if today else 1.0), value))
    parts.append(_line([(x(p), y(v)) for p, v in actual], ACTUAL_COLOR, 2.5, None))
    if b.today_index is not None and b.future:
        start = b.today_index + b.now_fraction
        future = [(start, b.future[0])] + [
            (b.today_index + 2.0 + j, v) for j, v in enumerate(b.future[1:])
        ]
        parts.append(_line([(x(p), y(v)) for p, v in future], FUTURE_COLOR, 2, "6 4"))
    for index, (position, value) in enumerate(actual[1:]):  # 日ごとの点
        day = b.first + timedelta(index)
        parts.append(
            f'<circle cx="{x(position):.1f}" cy="{y(value):.1f}" r="3" fill="{ACTUAL_COLOR}">'
            f"<title>{day:%m/%d} 残り {value:.1f}h</title></circle>"
        )
    if b.today_index is not None:
        px = x(b.today_index + b.now_fraction)
        parts.append(
            f'<line class="today" x1="{px:.1f}" y1="{TOP}" x2="{px:.1f}" y2="{TOP + plot_h}" '
            f'stroke="{TODAY_COLOR}" stroke-width="1.5"/>'
        )
    base = TOP + plot_h
    for mark in b.marks:  # 進捗度が未入力から入った日
        mx = x((mark.day - b.first).days + 0.5)
        names = html.escape("、".join(mark.names))
        parts.append(
            f'<polygon class="mark" points="{mx - 5:.1f},{base + 9} {mx + 5:.1f},{base + 9} '
            f'{mx:.1f},{base + 2}" fill="{ACTUAL_COLOR}"><title>進捗度を入力({names})</title></polygon>'
        )
    legend = [(PLANNED_COLOR, "2 4", "当初の予定"), (ACTUAL_COLOR, None, "実際")]
    if b.future:
        legend.append((FUTURE_COLOR, "6 4", "今後の予定"))
    for index, (color, dash, text) in enumerate(legend):
        lx = LEFT + index * 120
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{lx}" y1="14" x2="{lx + 24}" y2="14" stroke="{color}" '
            f'stroke-width="2"{dash_attr}/>'
            f'<text x="{lx + 30}" y="18" font-size="11" fill="currentColor">{text}</text>'
        )
    if b.marks:
        parts.append(
            f'<text x="{LEFT + len(legend) * 120}" y="18" font-size="11" fill="currentColor">'
            f"▲ 進捗度を入力</text>"
        )
    return (
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" role="img" '
        f'aria-label="残りの工数の推移" style="max-width: {WIDTH}px; height: auto">'
        + "".join(parts)
        + "</svg>"
    )
