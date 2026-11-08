"""ダッシュボードの表示。集計(dashboard.py)の結果を、カードと横棒で描く。"""

import html
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import NamedTuple

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp import clock
from projectapp.avatar import avatar, avatar_html
from projectapp.burndown_chart import chart_svg
from projectapp.dashboard import (
    UNASSIGNED,
    Backlog,
    Burndown,
    CrossSummary,
    Dashboard,
    DayLoad,
    Investment,
    CatchUp,
    CatchUpMode,
    LateBasis,
    LoadStats,
    MemberProgress,
    Period,
    PeriodKind,
    Recovery,
    Progress,
    ProgressDelta,
    TeamProgress,
)
from projectapp.dashboard_drag import DASHBOARD_DRAG_CSS, DASHBOARD_DRAG_JS
from projectapp.dashboard_views import (
    DEFAULT_ORDER,
    STANDARD_NAME,
    CardId,
    ViewState,
    late_counts,
    load_order,
    parse_card_move,
)
from projectapp.gantt import (
    STATUS_COLORS,
    STATUS_DARK_COLORS,
    WARNING_BACKGROUND,
    WEEKDAYS,
)
from projectapp.models import Status
from projectapp.periodfield import add_range_picker, normalize_period
from projectapp.scope import read_scope, scope_options, scope_value
from projectapp.timeline import OVERLOAD_EPSILON
from projectapp.tipchips import name_chips_tooltip

TRACK_STYLE = (
    "height: 10px; width: 100%; border-radius: 5px; overflow: hidden;"
    " background: rgba(128, 128, 128, 0.25); position: relative"
)
TICK_STYLE = (
    "position: absolute; top: 0; bottom: 0; width: 2px; background: currentColor"
)
LOAD_SCALE = 2.0  # `人ごとの負荷`の棒の範囲(0〜200%で固定。1 人の飛び抜けた値で全員の棒が縮まないように)
OVER_FULL = 3.0  # 日ごとの推移の赤が最も濃くなる負荷(300%)
REFERENCE_STYLE = "position: absolute; top: 0; bottom: 0; width: 0; border-left: 2px dotted rgba(128, 128, 128, 0.9)"
GRID_STYLE = "display: grid; grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr)); gap: 16px; width: 100%"
LOAD_COLOR = "#1e88e5"  # 負荷・進捗
OVER_COLOR = "#ef5350"  # 100% を超える日がある負荷(予定超過の赤と同じ系統)
PLANNED_COLOR = "#1e88e5"  # 予定の時間。dataviz の検証で、灰青は「灰色に見える」ため不合格。青と緑の組は全項目 PASS
ACTUAL_COLOR = "#43a047"  # 実績の時間
NEED_COLOR = "#6250d6"  # 残りの工数と必要人数: これから要る量(必要人数・担当別・チーム別の残りの工数)。予定の青と混ざらないすみれ
WARNING_FILL = "var(--warning)"  # 必要人数のうち警告の分。警告の色の設定に従う
WARNING_OUTLINE = "box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.35)"  # 黄は明るい背景で薄いので、輪郭で補う(凡例とホバーの値も出す)
HAVE_COLOR = "#1baf7a"  # 残りの工数と必要人数: 稼働できる人員。実績の緑と混ざらない青緑(ライトでは背景との比が 3:1 未満なので、値は文字でも出す)
LATE_COLOR = "#e0562f"  # 残りの工数と必要人数: 必要人数のうち遅れの分(必要のすみれの隣で、青緑とも区別できる赤橙。凡例と文字の数値で補う)
EMPTY = "データがありません"
CARD_TITLES = {
    CardId.TEAM: "チーム全体の進捗",
    CardId.PROGRESS: "進捗と遅れ",
    CardId.LOAD: "人ごとの負荷",
    CardId.HEATMAP: "負荷の日ごとの推移",
    CardId.HOURS: "工数の予定と実績",
    CardId.BACKLOG: "残りの工数と必要人数",
    CardId.BURNDOWN: "残りの工数の推移",
    CardId.DUE: "期限とマイルストーン",
}
REFRESH_SECONDS = 300  # 表示中に集計し直す間隔(今日の残り時間が変わるため)
ALL_MEMBERS = ""  # プルダウンの`全員`の値
PIE_VARS = {
    status: f"--pie-{status.name.lower().replace('_', '-')}" for status in Status
}
# 状態色はガントチャートの棒と同じ。ダークテーマでは明るい色に替える
PIE_CSS = (
    ":root { "
    + " ".join(f"{PIE_VARS[status]}: {STATUS_COLORS[status]};" for status in Status)
    + " }\nbody.body--dark { "
    + " ".join(
        f"{PIE_VARS[status]}: {STATUS_DARK_COLORS[status]};" for status in Status
    )
    + " }"
)


CELL_PX = 22  # 見出しの日の数字が収まる幅
HEATMAP_HINT_DAYS = 20  # これより列が多いとき、横にスクロールできることを案内する
HEATMAP_CSS = (
    ".heatmap-name { position: sticky; left: 0; z-index: 2; background: #fff; padding-right: 8px; white-space: nowrap }\n"
    ".heat-cell { width: 22px; height: 22px; border: 1px solid rgba(128, 128, 128, 0.25) }\n"
    ".heat-over { outline: 2px solid #b71c1c; outline-offset: -2px }\n"
    ".heat-person { cursor: pointer }\n"
    ".heat-person:hover { text-decoration: underline }\n"
    ".heat-badges { margin-left: 6px; font-size: 10px; font-weight: normal }\n"
    ".heat-late { color: #b71c1c; margin-right: 4px }\n"
    ".heat-warn { color: #e65100 }\n"
    "body.body--dark .heat-late { color: #ff8a80 }\n"
    "body.body--dark .heat-warn { color: #ffb74d }\n"
    ".heat-month { border-left: 2px solid rgba(128, 128, 128, 0.85) !important }\n"
    ".heat-week { border-left: 1px solid rgba(128, 128, 128, 0.55) !important }\n"
    ".heat-today { box-shadow: -2px 0 0 #1976d2, 2px 0 0 #1976d2 }\n"
    ".heat-head { position: sticky; z-index: 3; background: #fff; font-weight: normal; font-size: 10px; text-align: center; box-sizing: border-box }\n"
    ".heat-head.heat-today-head { background: #1976d2; color: #fff }\n"
    ".heat-r1 { top: 0; height: 18px; text-align: left; white-space: nowrap; overflow: hidden }\n"
    ".heat-r2 { top: 18px; height: 30px }\n"
    ".heat-r3 { top: 48px; height: 20px; color: #b71c1c; font-weight: bold }\n"
    ".heatmap-scroll { overflow: auto; max-width: 100%; max-height: calc(var(--app-vh, 100vh) * 0.7) }\n"
    ".dash-maximized > * { flex-shrink: 0 }\n"
    ".dash-maximized .heatmap-scroll { max-height: calc(var(--app-vh, 100vh) - 16rem) }\n"
    ".heatmap-scroll::-webkit-scrollbar { height: 12px; width: 12px }\n"
    ".heatmap-scroll::-webkit-scrollbar-track { background: rgba(128, 128, 128, 0.15) }\n"
    ".heatmap-scroll::-webkit-scrollbar-thumb { background: rgba(128, 128, 128, 0.55); border-radius: 6px }\n"
    "body.body--dark .heatmap-name, body.body--dark .heat-head { background: #1d1d1d }\n"
    "body.body--dark .heat-head.heat-today-head { background: #1976d2 }\n"
    "body.body--dark .heat-r3 { color: #ff8a80 }\n"
    "body.body--dark .heat-over { outline-color: #ff8a80 }"
)


def rgba(color: str, alpha: float) -> str:
    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha:.2f})"


def cell_style(total: float) -> str:
    """セルの塗り。0% は塗りなし、100% 以下は青、100% 超は赤(濃さは値に比例)。枠線は heat-over で足す。"""
    if total <= 0:
        return "background: transparent"
    if total <= 1.0 + OVERLOAD_EPSILON:
        return f"background: {rgba(LOAD_COLOR, 0.15 + 0.65 * min(total, 1.0))}"
    return f"background: {rgba(OVER_COLOR, 0.45 + 0.55 * min((total - 1.0) / (OVER_FULL - 1.0), 1.0))}"


def cell_class(total: float) -> str:
    return "heat-cell heat-over" if total > 1.0 + OVERLOAD_EPSILON else "heat-cell"


def cell_title(name: str, load: DayLoad) -> str:
    head = f"{name} {load.day:%m/%d}({WEEKDAYS[load.day.weekday()]}) {load.total * 100:.0f}%"
    lines = [html.escape(head)]
    if load.by_project:
        lines.append(
            html.escape(
                " / ".join(f"{p.project} {p.peak * 100:.0f}%" for p in load.by_project)
            )
        )
    return "&#10;".join(lines)


def scroll_to_today_js(element_id: int) -> str:
    """今日の列が見えるように、表を横にスクロールする(今日がなければ何もしない)。"""
    return (
        f"const box = getElementById({element_id}); "
        "const scroller = box && box.querySelector('.heatmap-scroll'); "
        "const mark = scroller && scroller.querySelector('.heat-today'); "
        "if (mark) scroller.scrollLeft = Math.max(0, mark.offsetLeft - 200);"
    )


def late_badges(counts: tuple[int, int] | None) -> str:
    """名前の横に添える`遅れ n 件`・`警告 n 件`。0 件は出さない。"""
    if counts is None:
        return ""
    late, warned = counts
    parts = []
    if late:
        parts.append(f'<span class="heat-late">遅れ {late}</span>')
    if warned:
        parts.append(f'<span class="heat-warn">警告 {warned}</span>')
    return f'<span class="heat-badges">{"".join(parts)}</span>' if parts else ""


def month_label(day: date, first: bool) -> str:
    return f"{day.year}年{day.month}月" if first or day.month == 1 else f"{day.month}月"


def column_classes(days: list[date], today: date | None) -> list[str]:
    """列ごとの印。月の初め(heat-month)・週の初め(heat-week)・今日(heat-today)。"""
    marks = []
    for i, day in enumerate(days):
        names = []
        if i > 0:
            prev = days[i - 1]
            if (day.year, day.month) != (prev.year, prev.month):
                names.append("heat-month")
            elif day.weekday() < prev.weekday() or (day - prev).days >= 7:
                names.append("heat-week")
        if day == today:
            names.append("heat-today")
        marks.append(" ".join(names))
    return marks


def heatmap_html(
    cross: CrossSummary,
    icons: dict[str, str] | None = None,
    today: date | None = None,
    order: list[str] | None = None,
    counts: dict[str, tuple[int, int]] | None = None,
) -> str:
    """人×稼働日の表。名前・プロジェクト名はエスケープする。名前の前にアイコン(なければ頭文字の丸)を付ける。

    見出しは月の帯と日の数字の 2 段で、その下に`100% 超の人数`の行を置く(3 段とも縦に固定)。
    """
    first = next(iter(cross.loads.values()), None)
    days = first.days if first is not None else []
    dates = [d.day for d in days]
    marks = column_classes(dates, today)
    bands = []
    for i, day in enumerate(dates):
        if i == 0 or (day.year, day.month) != (dates[i - 1].year, dates[i - 1].month):
            bands.append([i, 0])
        bands[-1][1] += 1
    band = "".join(
        f'<th class="heat-head heat-r1 {marks[i]}" colspan="{n}">{month_label(dates[i], i == 0)}</th>'
        for i, n in bands
    )
    head = "".join(
        f'<th class="heat-head heat-r2 {mark}{" heat-today-head" if "heat-today" in mark else ""}">'
        f"<div>{day.day}</div><div>{WEEKDAYS[day.weekday()]}</div></th>"
        for day, mark in zip(dates, marks)
    )
    over = []
    for i in range(len(days)):
        count = sum(
            1
            for entry in cross.loads.values()
            if i < len(entry.days) and entry.days[i].total > 1.0 + OVERLOAD_EPSILON
        )
        over.append(
            f'<th class="heat-head heat-r3 {marks[i]}" title="{dates[i]:%m/%d} 100%超 {count}人">'
            f"{count or ''}</th>"
        )
    rows = []
    for name in order if order is not None else list(cross.loads):
        entry = cross.loads[name]
        cells = "".join(
            f'<td class="{cell_class(day.total)} {mark}" data-cell="{html.escape(name)}|{day.day.isoformat()}"'
            f' title="{cell_title(name, day)}" style="{cell_style(day.total)}"></td>'
            for day, mark in zip(entry.days, marks)
        )
        mark = avatar_html(name, (icons or {}).get(name, ""), 20)
        label = (
            '<th class="heatmap-name text-body2" style="text-align: left">'
            f'{mark}<span class="heat-person" data-name="{html.escape(name)}"'
            f" onclick=\"emitEvent('dashboard_member', this.dataset.name)\">{html.escape(name)}</span>"
            f"{late_badges((counts or {}).get(name))}</th>"
        )
        rows.append(f"<tr>{label}{cells}</tr>")
    corner = '<th class="heatmap-name heat-head heat-r{n}" style="z-index: 4{extra}">{text}</th>'
    return (
        '<div class="heatmap-scroll">'
        '<table style="border-collapse: separate; border-spacing: 0">'
        f"<thead><tr>{corner.format(n=1, extra='', text='')}{band}</tr>"
        f"<tr>{corner.format(n=2, extra='', text='')}{head}</tr>"
        f"<tr>{corner.format(n=3, extra='; text-align: left', text='100%超の人数')}{''.join(over)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def legend_html() -> str:
    swatches = [
        (0.0, "0%"),
        (0.5, "50%"),
        (1.0, "100%"),
        (1.2, "120%"),
        (2.0, "200%"),
        (3.0, "300%以上"),
    ]
    items = "".join(
        f'<span style="display: inline-flex; align-items: center; gap: 4px; margin-right: 12px">'
        f'<span class="{cell_class(value)}" style="display: inline-block; width: 14px; height: 14px;'
        f' {cell_style(value)}"></span>{label}</span>'
        for value, label in swatches
    )
    return f'<div class="text-caption">{items}</div>'


def percent_width(fraction: float) -> str:
    """割合(0〜1)を、棒の幅(%)にする。範囲外は端に丸める。"""
    return f"{min(max(fraction, 0.0), 1.0) * 100:.1f}%"


def bar(
    fraction: float,
    color: str,
    tick: float | None = None,
    marker: str | None = None,
    reference: float | None = None,
) -> None:
    """横棒。`tick` があれば、その位置に縦の印を出す(最大値など)。`reference` があれば、その位置に点線の目印(100% など)を出す。`marker` は塗りの部分に付ける。"""
    with ui.element("div").style(TRACK_STYLE):
        fill = ui.element("div").style(
            f"height: 100%; width: {percent_width(fraction)}; background: {color}"
        )
        if marker is not None:
            fill.mark(marker)
        if reference is not None:
            ui.element("div").style(
                f"{REFERENCE_STYLE}; left: {percent_width(reference)}"
            )
        if tick is not None:
            ui.element("div").style(f"{TICK_STYLE}; left: {percent_width(tick)}")


def stacked_bar(
    parts: list[
        tuple[float, str, str | None, str | None]
        | tuple[float, str, str | None, str | None, str]
    ],
) -> None:
    """積み上げの横棒。(割合, 色, マーク, ホバーの文字[, 追加の CSS])を左から並べ、区切りに 2px の隙間を空ける。割合の合計が 1 を超えないこと。"""
    with ui.element("div").style(TRACK_STYLE + "; display: flex; gap: 2px"):
        for fraction, color, marker, tip, *extra in parts:
            if fraction <= 0:
                continue
            fill = ui.element("div").style(
                f"height: 100%; width: {percent_width(fraction)}; background: {color}"
                + (f"; {extra[0]}" if extra else "")
            )
            if marker is not None:
                fill.mark(marker)
            if tip is not None:
                with fill:
                    ui.tooltip(tip)


def late_summary(backlog: Backlog) -> str:
    """残りの工数の見出しの括弧の中身。予定超過と警告(`警告を含む`のときだけ)の件数と工数。なければ`遅れなし`。"""
    parts = []
    if backlog.overdue_count:
        parts.append(f"遅れ {backlog.overdue_count} 件・{backlog.overdue_hours:.1f}h")
    if backlog.warning_count:
        parts.append(f"警告 {backlog.warning_count} 件・{backlog.warning_hours:.1f}h")
    return "うち" + "、".join(parts) if parts else "遅れなし"


def legend(prefix: str, entries: tuple[tuple[str, str, str], ...]) -> None:
    """2 系列以上の凡例。(ラベル, 色, キー)。ラベルは`{prefix}-legend-{キー}`、色の四角は`{prefix}-swatch-{キー}`。"""
    with ui.row().classes("items-center gap-4 text-caption"):
        for label, color, key in entries:
            with ui.row().classes("items-center no-wrap gap-1"):
                ui.element("div").style(
                    f"width: 10px; height: 10px; border-radius: 2px; background: {color}"
                ).mark(f"{prefix}-swatch-{key}")
                ui.label(label).mark(f"{prefix}-legend-{key}")


MAX_RECOVER_PEOPLE = 20.0  # 遅れを取り戻すために追加できる人数の上限


def toggled(names: tuple[str, ...], name: str, on: bool) -> tuple[str, ...]:
    """投入するメンバーの選択に、`name`を足す(on)か外す。選んだ順を保つ。"""
    rest = tuple(n for n in names if n != name)
    return (*rest, name) if on else rest


def investment_text(investment: Investment) -> str:
    """選んだメンバーを投入したときの文言(要望 131)。余力が届かないときは不足を、届くときは日付を出す。"""
    spare, hours = investment.spare_hours, investment.hours
    if spare < hours - 1e-9:
        return (
            f"選んだ人の余力 {spare:.1f}h では、遅れ {hours:.1f}h のうち {spare:.1f}h しか"
            f"取り戻せません(残り {hours - spare:.1f}h)"
        )
    if investment.date is None:
        return "稼働日が見つからず、取り戻せる日を出せません"
    text = (
        f"{'・'.join(investment.names)}を投入すると {investment.date:%m/%d} に取り戻せます"
        f"(余力の合計 {spare:.1f}h ≥ 遅れ {hours:.1f}h)"
    )
    if investment.due is not None:
        verdict = (
            "間に合います" if investment.date <= investment.due else "間に合いません"
        )
        text += f"。期間の終わり({investment.due:%m/%d})に{verdict}"
    return text


def recovery_text(recovery: Recovery) -> str:
    """追加した人だけで遅れを取り戻せる日の文言(要望 130)。期限があれば、間に合うかも添える。"""
    if recovery.date is None:
        return "稼働日が見つからず、取り戻せる日を出せません"
    text = (
        f"追加 {recovery.people:.1f} 人で {recovery.date:%m/%d} に取り戻せます"
        f"(遅れ {recovery.hours:.1f}h ÷ {recovery.people:.1f} 人"
        f" = 1 人あたり {recovery.hours / recovery.people:.1f}h・約 {recovery.days:.1f} 稼働日)"
    )
    if recovery.due is not None:
        verdict = "間に合います" if recovery.date <= recovery.due else "間に合いません"
        text += f"。期間の終わり({recovery.due:%m/%d})に{verdict}"
    return text


def warning_icon(marker: str) -> ui.icon:
    """警告の印。警告の色(`--warning`)のアイコン。文字そのものは色づけしない(白地で読めないため)。"""
    return (
        ui.icon("warning_amber", size="xs").style("color: var(--warning)").mark(marker)
    )


def card(title: str, marker: str, title_marker: str | None = None) -> ui.card:
    box = ui.card().classes("w-full gap-2").mark(marker)
    with box:
        label = ui.label(title).classes("text-subtitle1 text-weight-bold")
        if title_marker is not None:
            label.mark(title_marker)
    return box


def empty_message(marker: str) -> None:
    ui.label(EMPTY).classes("text-grey").mark(marker)


def scope_label(data: Dashboard, period: Period | None) -> str:
    """カードの見出しに添える対象。メンバー・チームを選んでいれば先頭に付く。"""
    scope = (
        "すべてのタスク"
        if period is None
        else f"{period.start:%m/%d}〜{period.end:%m/%d} にかかるタスク"
    )
    if data.member:
        return f"{data.member}・{scope}"
    if data.team_name:
        return f"チーム「{data.team_name}」・{scope}"
    return scope


class BurnLine(NamedTuple):
    key: str  # マークの末尾(unknown・end・pace・behind・ahead・unset)
    text: str


def burndown_lines(b: Burndown) -> list[BurnLine]:
    """`残りの工数の推移`のグラフの下の行(要望 128 段階 2)。"""
    if not b.known:
        if b.since is None:
            return [BurnLine("unknown", "履歴はまだありません")]
        return [BurnLine("unknown", f"履歴は {b.since:%m/%d} から(それ以前は不明)")]
    lines: list[BurnLine] = []
    if b.today_index is not None and b.future:
        lines.append(
            BurnLine(
                "end",
                f"期間の終わりの予定の残り {b.future[-1]:.1f}h(今日の実際 {b.actual[-1]:.1f}h)",
            )
        )
    elif b.actual:
        lines.append(
            BurnLine(
                "end",
                f"期間の終わりの実際の残り {b.actual[-1]:.1f}h(予定 {b.planned[-1]:.1f}h)",
            )
        )
    elif b.planned:
        lines.append(
            BurnLine(
                "end",
                f"期間の始めの残り {b.initial:.1f}h(予定どおりなら終わりに {b.planned[-1]:.1f}h)",
            )
        )
    if b.required is not None and b.rest is not None:
        recent = (
            f"直近 {b.recent_days} 稼働日のペース {b.recent:.1f}h/稼働日"
            if b.recent is not None
            else "直近のペースが出ていません"
        )
        lines.append(
            BurnLine(
                "pace",
                f"必要なペース {b.required:.1f}h/稼働日({b.last:%m/%d} までに {b.rest:.1f}h 減らす)・{recent}",
            )
        )
    if b.behind:
        lines.append(BurnLine("behind", "ペースを上げるか、予定を見直す必要があります"))
    if b.ahead:
        lines.append(BurnLine("ahead", "予定より進んでいます"))
    if b.unset:
        lines.append(
            BurnLine(
                "unset",
                f"進捗度なしの実行中・一時停止 {len(b.unset)} 件(終了まで減りません)",
            )
        )
    return lines


def references_note(data: Dashboard, key: str) -> None:
    """参照先のプロジェクトのタスクを数えているときの注記。`key`はカードごとのマークの末尾(team・progress)。"""
    if data.references:
        ui.label(f"参照先 {data.references} 件を含む").classes(
            "text-caption text-grey"
        ).mark(f"dashboard-{key}-references")


def weighted_note(data: Dashboard, key: str) -> None:
    """チームを選んでいるときの注記。`key`はカードごとのマークの末尾(load・hours・backlog)。"""
    if data.team_name:
        ui.label(f"チーム「{data.team_name}」の所属の割合で按分しています").classes(
            "text-caption text-grey"
        ).mark(f"dashboard-weighted-note-{key}")


def cross_note(data: Dashboard) -> None:
    """全プロジェクトを重ねているときの、残りの工数のカードの注記。"""
    if data.cross is not None:
        count = len(data.cross.projects) - len(data.cross.excluded)
        ui.label(
            f"全 {count} プロジェクトを重ねています。稼働時間と祝日は開いているプロジェクトの設定で数えます"
        ).classes("text-caption text-grey").mark("dashboard-backlog-cross-note")


def shortage_text(value: float) -> str:
    """不足する人数の表示。負は余裕。表示の桁で 0 になるときは「あと 0.0 人」と出さず「ちょうど」にする。"""
    short = round(value, 1)
    return (
        f"あと {short:.1f} 人"
        if short > 0
        else f"余裕 {-short:.1f} 人"
        if short < 0
        else "ちょうど"
    )


def days_text(days: float) -> str:
    """稼働日数の表示。小数 1 桁(整数なら小数点なし)。"""
    return f"{days:.1f}".removesuffix(".0")


def delta_line(delta: ProgressDelta, previous: ProgressDelta | None) -> str:
    """`チーム全体の進捗`の「進んだ分」の 1 行(要望 128)。履歴がない期間は、0 とせず不明と書く。"""
    if not delta.known:
        if delta.since is None:
            return "進んだ分: 履歴はまだありません"
        return f"進んだ分: 履歴は {delta.since:%m/%d} から(それ以前は不明)"
    if delta.percent is None:
        text = "進んだ分: 対象のタスクなし"
    else:
        text = f"進んだ分 {round(delta.percent):+d}%"
        if previous is not None and previous.percent is not None:
            text += f"(前の期間 {round(previous.percent):+d}%)"
    if abs(delta.scope_hours) >= 0.05:
        text += f"  範囲 {delta.scope_hours:+.1f}h"
    return text


def moment_text(moment: datetime) -> str:
    return f"{moment:%m/%d %H:%M}"


@dataclass
class ViewActions:
    """ビューの操作。MainView が渡す。"""

    select: Callable[[str], object]
    save: Callable[[], object]
    save_as: Callable[[], object]
    revert: Callable[[], object]
    rename: Callable[[], object]
    delete: Callable[[], object]
    move_card: Callable[[CardId, CardId | None], object]
    hide_card: Callable[[CardId], object]
    show_card: Callable[[CardId], object]


class DashboardView:
    """メイン画面の切り替え先。`show` で集計を受け取って描き、`hide` で隠す。"""

    def __init__(
        self,
        on_back: Callable[[], object],
        on_change: Callable[[PeriodKind], object],
        on_member_change: Callable[[str | None], object] | None = None,
        on_cross_change: Callable[[bool], object] | None = None,
        on_project_change: Callable[[str, bool], object] | None = None,
        on_custom_change: Callable[[str], object] | None = None,
        on_team_change: Callable[[str | None], object] | None = None,
        actions: ViewActions | None = None,
        on_tick: Callable[[], object] | None = None,
        on_late_basis_change: Callable[[LateBasis], object] | None = None,
        on_catch_up_change: Callable[[CatchUp], object] | None = None,
        on_assign: Callable[[str], object] | None = None,
        on_add_crew: Callable[[str], object] | None = None,
        on_try_on_gantt: Callable[[tuple[str, ...]], object] | None = None,
    ) -> None:
        self.on_try_on_gantt = on_try_on_gantt
        self.actions = actions
        self.on_assign = on_assign
        self.on_add_crew = on_add_crew
        self.assign_mode = (
            False  # 担当なしの割り当てを編集できるか(保存せず、閉じるとオフ)
        )
        self.on_late_basis_change = on_late_basis_change
        self.on_catch_up_change = on_catch_up_change
        self.on_tick = on_tick
        self.edit_mode = False
        self.maximized: CardId | None = (
            None  # 画面いっぱいに出しているカード(保存しない)
        )
        self.sort_by_load = False  # 並び替えと絞り込みは保存しない(閉じると既定に戻る)
        self.over_only = False
        self.edit_button: ui.button | None = None
        self.view_select: ui.select | None = None
        self.dirty_mark: ui.label | None = None
        self.save_button: ui.button | None = None
        self.save_as_item: ui.menu_item | None = None
        self.revert_item: ui.menu_item | None = None
        self.top_bar: ui.row | None = None
        self.view_bar: ui.row | None = None
        self.filter_bar: ui.row | None = None
        self.rename_item: ui.menu_item | None = None
        self.delete_item: ui.menu_item | None = None
        self.on_custom_change = on_custom_change
        self.on_team_change = on_team_change
        self.custom_field: ui.input | None = None
        self.custom_box: ui.column | None = None
        self.custom_error: ui.label | None = None
        self.on_back, self.on_change, self.on_member_change = (
            on_back,
            on_change,
            on_member_change,
        )
        self.on_cross_change, self.on_project_change = (
            on_cross_change,
            on_project_change,
        )
        self.cross_switch: ui.switch | None = None
        self.box: ui.column | None = None
        self.toggle: ui.toggle | None = None
        self.member_select: ui.select | None = None
        self.data: Dashboard | None = None
        self.icons: dict[str, str] = {}  # メンバー名 → アイコン(ある人だけ)
        self.syncing = (
            False  # 開き直しでトグルの値を書き換えるあいだは、変更を通知しない
        )
        self.state: ViewState | None = (
            None  # ビューの選択・カードの並び。None のあいだは既定の順で全部出す
        )
        self.card_order: tuple[CardId, ...] = DEFAULT_ORDER

    def build(self) -> None:
        ui.add_css(PIE_CSS)
        ui.add_css(HEATMAP_CSS)
        ui.add_css(DASHBOARD_DRAG_CSS)
        ui.add_head_html(f"<script>{DASHBOARD_DRAG_JS}</script>")
        ui.on("dashboard_move_card", lambda e: self.handle_move(e.args))
        ui.on("dashboard_member", lambda e: self.pick_member(e.args))
        ui.timer(REFRESH_SECONDS, self.tick)
        with ui.column().classes("w-full gap-4") as box:
            self.box = box
            box.mark("dashboard-box")
            with ui.row().classes(
                "w-full items-center gap-4 justify-between"
            ) as self.top_bar:  # 1 段目: 画面の操作(見出しと戻る)
                self.top_bar.mark("dashboard-bar-top")
                ui.label("ダッシュボード").classes("text-h5")
                ui.button(
                    "戻る", icon="arrow_back", on_click=lambda: self.on_back()
                ).props("flat").mark("dashboard-back")
            with (
                ui.column()
                .classes("w-full gap-2")
                .style(
                    "border: 1px solid rgba(128, 128, 128, 0.4); border-radius: 6px; padding: 8px 12px"
                )
                .mark("dashboard-view-group")
            ):  # 2 段目: ビューに保存されるもの(ビューの管理・カードの編集・表示条件)
                with ui.row().classes(
                    "w-full items-center gap-4 justify-between"
                ) as self.view_bar:
                    self.view_bar.mark("dashboard-bar-view")
                    with ui.row().classes("items-center gap-2"):
                        self.view_select = (
                            ui.select(
                                {STANDARD_NAME: STANDARD_NAME},
                                value=STANDARD_NAME,
                                on_change=self.on_view,
                            )
                            .props("dense outlined options-dense")
                            .style("min-width: 8rem")
                            .mark("dashboard-view")
                        )
                        self.dirty_mark = (
                            ui.label("●")
                            .classes("text-warning")
                            .tooltip("保存していない変更があります")
                            .mark("dashboard-view-dirty")
                        )
                        self.save_button = (
                            ui.button("保存", on_click=lambda: self.act("save"))
                            .props("flat dense")
                            .mark("dashboard-view-save")
                        )
                        with (
                            ui.button(icon="more_vert")
                            .props("flat dense round")
                            .mark("dashboard-view-menu")
                        ):
                            with ui.menu():
                                self.save_as_item = ui.menu_item(
                                    "名前をつけて保存",
                                    on_click=lambda: self.act("save_as"),
                                ).mark("dashboard-view-save-as")
                                self.revert_item = ui.menu_item(
                                    "元に戻す", on_click=lambda: self.act("revert")
                                ).mark("dashboard-view-revert")
                                ui.separator()
                                self.rename_item = ui.menu_item(
                                    "名前の変更", on_click=lambda: self.act("rename")
                                ).mark("dashboard-view-rename")
                                self.delete_item = ui.menu_item(
                                    "削除", on_click=lambda: self.act("delete")
                                ).mark("dashboard-view-delete")
                        for item in (self.dirty_mark, self.save_button):
                            item.set_visibility(False)
                    with ui.row().classes("items-center gap-2"):
                        self.edit_button = (
                            ui.button(
                                "カードを編集",
                                icon="edit",
                                on_click=lambda: self.set_edit_mode(not self.edit_mode),
                            )
                            .props("flat dense")
                            .mark("dashboard-edit-toggle")
                        )
                with ui.row().classes(
                    "w-full items-start gap-4"
                ) as self.filter_bar:  # 2 段目: 表示条件の絞り込み
                    self.filter_bar.mark("dashboard-bar-filters")
                    self.toggle = ui.toggle(
                        {kind.value: kind.value for kind in PeriodKind},
                        value=PeriodKind.WEEK.value,
                        on_change=self.on_toggle,
                    ).mark("dashboard-period")
                    with ui.column().classes(
                        "gap-0"
                    ) as custom_box:  # `指定` のときだけ出す期間欄
                        self.custom_field = (
                            ui.input(
                                placeholder="2026-10-01 〜 2026-10-31",
                                on_change=self.on_custom,
                            )
                            .props("dense outlined")
                            .style("width: 17rem")
                            .mark("dashboard-period-field")
                        )
                        add_range_picker(self.custom_field, "dashboard-period")
                        self.custom_field.on("blur", lambda _e: self.normalize_custom())
                        self.custom_error = (
                            ui.label("")
                            .classes("text-negative text-caption")
                            .mark("dashboard-period-error")
                        )
                    self.custom_box = custom_box
                    custom_box.set_visibility(False)
                    self.custom_field.set_visibility(False)
                    self.member_select = (
                        ui.select(
                            {ALL_MEMBERS: "全員"},
                            value=ALL_MEMBERS,
                            on_change=self.on_member,
                        )
                        .props("dense outlined options-dense")
                        .style("min-width: 8rem")
                        .mark("dashboard-member")
                    )
                    self.cross_switch = ui.switch(
                        "全プロジェクト", value=False, on_change=self.on_cross
                    ).mark("dashboard-cross")
            self.cards()
        box.set_visibility(False)

    def set_edit_mode(self, on: bool) -> None:
        self.edit_mode = on
        self.maximized = None  # 編集中は最大化しない(取っ手の操作と競合する)
        if self.edit_button is not None:
            self.edit_button.set_text("完了" if on else "カードを編集")
            self.edit_button.props(f"icon={'check' if on else 'edit'}")
        self.cards.refresh()

    def handle_move(self, args: object) -> None:
        """ブラウザからのカードの移動(取っ手を掴んで落とした)を受ける。不正な値は無視する。"""
        parsed = parse_card_move(args)
        if parsed is not None:
            self.act("move_card", *parsed)

    def decorate(self, element: ui.element, card_id: CardId) -> None:
        """編集モードのカードに、取っ手(掴む)と非表示ボタンの帯を、先頭に足す。"""
        element.props(f"data-dash-card={card_id.value}")
        with element:
            with ui.row().classes("w-full items-center justify-between no-wrap") as bar:
                ui.icon("drag_indicator").props(
                    f"data-dash-handle={card_id.value} draggable=true"
                ).classes("text-grey")
                ui.button(
                    icon="close", on_click=lambda c=card_id: self.act("hide_card", c)
                ).props("flat dense round size=sm").mark(
                    f"dashboard-hide-{card_id.value}"
                )
        bar.move(element, target_index=0)

    def add_maximize_button(
        self, element: ui.element, card_id: CardId, maximized: bool
    ) -> None:
        """カードの右上に、最大化(最大化中は戻す)ボタンを足す。最大化中のカードは画面の高さに合わせる。"""
        if maximized:
            element.classes("dash-maximized").style(
                "grid-column: 1 / -1; height: calc(var(--app-vh, 100vh) - 9rem); overflow-y: auto"
            )
        with element:
            ui.button(
                icon="fullscreen_exit" if maximized else "fullscreen",
                on_click=lambda: self.set_maximized(None if maximized else card_id),
            ).props(
                f"flat dense round size=sm aria-label={'戻る' if maximized else '最大化'}"
            ).style("position: absolute; top: 8px; right: 8px").mark(
                "dashboard-restore"
                if maximized
                else f"dashboard-maximize-{card_id.value}"
            )

    def set_maximized(self, card_id: CardId | None) -> None:
        self.maximized = card_id
        self.cards.refresh()

    def restore(self) -> bool:
        """最大化を解除する(ESC 用)。最大化していなければ何もせず偽を返す。"""
        if self.maximized is None:
            return False
        self.set_maximized(None)
        return True

    def rows_box(self) -> ui.element:
        """人の行を並べる箱。`人ごとの負荷`の最大化中は、広い幅に合わせて複数列に折り返す。"""
        if self.maximized is CardId.LOAD:
            return ui.element("div").style(
                "display: grid; grid-template-columns: repeat(auto-fill, minmax(22rem, 1fr)); gap: 12px; width: 100%"
            )
        return ui.column().classes("w-full gap-2")

    def act(self, name: str, *args: object) -> None:
        """MainView の操作を呼ぶ。actions がないとき(単体のテスト)は何もしない。"""
        if self.actions is not None:
            getattr(self.actions, name)(*args)

    def on_view(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and event.value:
            self.act("select", event.value)

    def sync_toolbar(self) -> None:
        """ビューの選択・`●`・ボタンの有効/無効を、状態に合わせる(通知は出さない)。"""
        state = self.state
        if state is None or self.view_select is None:
            return
        self.syncing = True
        try:
            self.view_select.set_options(
                {name: name for name in state.names}, value=state.current
            )
        finally:
            self.syncing = False
        if self.dirty_mark is not None:
            self.dirty_mark.set_visibility(state.dirty)
        if self.save_button is not None:
            self.save_button.set_visibility(state.dirty)
            self.save_button.set_enabled(state.save_block is None)
            if state.save_block is not None:
                self.save_button.props(
                    f'title="{state.save_block}"'
                )  # 押せない理由(ネイティブのヒント)
            else:
                self.save_button.props(remove="title")
        if self.revert_item is not None:
            self.revert_item.set_enabled(
                state.dirty
            )  # 元に戻すは、変更があるときだけ押せる(⋮ の中)
        standard = state.current == STANDARD_NAME
        for item in (self.rename_item, self.delete_item):
            if item is not None:
                item.set_enabled(not standard)

    def on_toggle(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing:
            self.on_change(PeriodKind(event.value))

    def on_custom(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and self.on_custom_change is not None:
            self.on_custom_change(event.value or "")

    def set_custom_error(self, text: str) -> None:
        """`指定` の欄のエラー表示だけを更新する(集計し直さない)。"""
        if self.custom_error is not None:
            self.custom_error.set_text(text)

    def normalize_custom(self) -> None:
        """欄を離れたとき、両端の省略形を `YYYY-MM-DD` に整える。読めない値はそのまま。"""
        if self.custom_field is None:
            return
        text = self.custom_field.value or ""
        fixed = normalize_period(text, clock.today()) if text.strip() else None
        if fixed is not None and fixed != text:
            self.custom_field.set_value(fixed)

    def on_member(self, event: ValueChangeEventArguments) -> None:
        if self.syncing:
            return
        member, team = read_scope(event.value)
        if team is not None:
            if self.on_team_change is not None:
                self.on_team_change(team)
        elif self.on_member_change is not None:
            self.on_member_change(member)

    def on_cross(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and self.on_cross_change is not None:
            self.on_cross_change(bool(event.value))

    def on_project(self, name: str, included: bool) -> None:
        if not self.syncing and self.on_project_change is not None:
            self.on_project_change(name, included)

    def show(
        self,
        data: Dashboard,
        kind: PeriodKind,
        icons: dict[str, str] | None = None,
        custom_text: str | None = None,
        custom_error: str = "",
        view_state: ViewState | None = None,
    ) -> None:
        """custom_text が None のときは、欄の文字(入力中の値)を書き換えない。"""
        self.icons = icons or {}
        self.data = data
        self.state = view_state
        self.card_order = view_state.cards if view_state is not None else DEFAULT_ORDER
        self.sync_toolbar()
        if (
            self.custom_box is not None
            and self.custom_field is not None
            and self.custom_error is not None
        ):
            self.custom_box.set_visibility(kind is PeriodKind.CUSTOM)
            self.custom_field.set_visibility(kind is PeriodKind.CUSTOM)
            if custom_text is not None and self.custom_field.value != custom_text:
                self.syncing = True
                try:
                    self.custom_field.set_value(custom_text)
                finally:
                    self.syncing = False
            self.custom_error.set_text(custom_error)
        if self.toggle is not None and self.toggle.value != kind.value:
            self.syncing = True
            try:
                self.toggle.value = kind.value
            finally:
                self.syncing = False
        if self.member_select is not None:
            options = scope_options("全員", data.members, data.teams)
            self.syncing = True
            try:
                self.member_select.set_options(
                    options, value=scope_value(data.member, data.team_name)
                )
            finally:
                self.syncing = False
        if self.cross_switch is not None and self.cross_switch.value != (
            data.cross is not None
        ):
            self.syncing = True
            try:
                self.cross_switch.value = data.cross is not None
            finally:
                self.syncing = False
        if self.box is not None:
            self.box.set_visibility(True)
        self.cards.refresh()

    def tick(self) -> None:
        """表示中だけ、集計し直す。カードの編集中は、並べ替えの途中で描き直さない。"""
        if (
            self.on_tick is not None
            and self.box is not None
            and self.box.visible
            and not self.edit_mode
        ):
            self.on_tick()

    def hide(self) -> None:
        self.edit_mode = False  # 編集モードは持ち越さない(次に開くときは、ふだんの表示)
        self.maximized = None
        self.sort_by_load = self.over_only = False
        self.assign_mode = False
        if self.edit_button is not None:
            self.edit_button.set_text("カードを編集")
            self.edit_button.props("icon=edit")
        if self.box is not None:
            self.box.set_visibility(False)

    @ui.refreshable_method
    def cards(self) -> None:
        data = self.data
        if data is None:
            return
        builders = {
            CardId.TEAM: self.team_card,
            CardId.PROGRESS: self.progress_card,
            CardId.LOAD: self.load_card,
            CardId.HEATMAP: self.heatmap_card,
            CardId.HOURS: self.hours_card,
            CardId.BACKLOG: self.backlog_card,
            CardId.BURNDOWN: self.burndown_card,
            CardId.DUE: self.due_card,
        }
        only = None if self.edit_mode else self.maximized
        with ui.element("div").style(GRID_STYLE) as grid:
            for card_id in self.card_order:
                if only is not None and card_id is not only:
                    continue
                before = len(grid.default_slot.children)
                builders[card_id](data)
                created = grid.default_slot.children[before:]
                if not created:  # 何も描かないカード(空の横断など)は、印を付けない
                    continue
                if self.edit_mode:
                    self.decorate(created[0], card_id)
                else:
                    self.add_maximize_button(created[0], card_id, only is not None)
            if only is not None and not grid.default_slot.children:
                self.maximized = (
                    None  # 最大化中のカードが消えた(データの変化)ときは、一覧に戻す
                )
                ui.timer(0.01, self.cards.refresh, once=True)
            if self.edit_mode:
                ui.element("div").props("data-dash-end=1").style(
                    "min-height: 3rem; border: 2px dashed rgba(128, 128, 128, 0.5)"
                ).mark("dashboard-drop-end")
        if self.edit_mode and self.state is not None and self.state.hidden:
            with ui.row().classes("w-full items-center gap-2"):
                ui.label("隠したカード").classes("text-caption text-grey")
                for card_id in self.state.hidden:
                    ui.button(
                        CARD_TITLES[card_id],
                        icon="add",
                        on_click=lambda c=card_id: self.act("show_card", c),
                    ).props("flat dense").mark(f"dashboard-hidden-{card_id.value}")

    def team_card(self, data: Dashboard) -> None:
        team = data.team
        period = team.period
        scope = scope_label(data, period)
        with card(
            f"チーム全体の進捗({scope})", "dashboard-team", "dashboard-team-scope"
        ):
            references_note(data, "team")
            if not any(team.counts.values()):
                empty_message("dashboard-empty-team")
                return
            slices = team.slices()
            if slices:
                done = team.hours[Status.DONE] / team.total
                ui.label(f"終了 {done * 100:.0f}%(工数ベース)").classes("text-h6").mark(
                    "dashboard-team-done"
                )
                stacked_bar(
                    [
                        (
                            fraction,
                            f"var({PIE_VARS[status]})",
                            f"dashboard-team-bar-{status.name}",
                            f"{status.value} {hours:.1f}h",
                        )
                        for status, hours, fraction in slices
                    ]
                )
            if data.delta is not None:
                ui.label(delta_line(data.delta, data.previous_delta)).classes(
                    "text-caption"
                ).mark("dashboard-team-delta")
            if team.unset:
                ui.label(f"工数なし {team.unset} 件は 1h として数えています").classes(
                    "text-caption text-grey"
                ).mark("dashboard-team-unset")
            with ui.column().classes("gap-1"):
                for status in Status:
                    if not team.counts[status]:
                        continue
                    hours = team.hours[status]
                    fraction = hours / team.total if team.total else 0.0
                    with ui.row().classes("items-center no-wrap gap-2"):
                        ui.element("span").style(
                            f"width: 10px; height: 10px; border-radius: 2px; background: var({PIE_VARS[status]})"
                        )
                        ui.label(
                            f"{status.value} {team.counts[status]}件 {hours:.1f}h ({fraction * 100:.0f}%)"
                        ).mark(f"dashboard-team-legend-{status.name}")
                        self.status_tip(team, status)

    def status_tip(self, team: TeamProgress, status: Status) -> None:
        """凡例の行のツールチップ。その状態のタスク名をチップで並べる。"""
        name_chips_tooltip(
            team.tasks[status],
            f"dashboard-team-chip-{status.name}",
            more_marker=f"dashboard-team-more-{status.name}",
            color=f"var({PIE_VARS[status]})",  # 枠と文字が凡例の色と揃う
        )

    def progress_card(self, data: Dashboard) -> None:
        progress = data.progress
        with card("進捗と遅れ", "dashboard-progress"):
            references_note(data, "progress")
            if progress.percent is None:
                empty_message("dashboard-empty-progress")
                return
            ui.label(f"{progress.percent:.0f}%").classes("text-h4").mark(
                "dashboard-progress-percent"
            )
            bar(progress.percent / 100, LOAD_COLOR)
            with ui.row().classes("gap-4"):
                for status in Status:
                    ui.label(f"{status.value} {progress.counts[status]}").mark(
                        f"dashboard-count-{status.name}"
                    )
                with ui.row().classes("items-center no-wrap gap-1"):
                    if progress.warnings:
                        warning_icon("dashboard-count-warning-icon")
                    ui.label(f"警告 {progress.warnings}").mark(
                        "dashboard-count-warning"
                    )
            self.unassigned_row(progress)
            if progress.by_member:
                ui.label("メンバー別").classes("text-subtitle2")
                for row in progress.by_member:
                    self.member_progress_row(row)
            if progress.by_team:
                ui.label("チーム別").classes("text-subtitle2")
                for row in progress.by_team:
                    self.member_progress_row(row, "dashboard-team-row")
            ui.label("遅れ").classes("text-subtitle2")
            if not progress.overdue:
                ui.label("なし").classes("text-grey").mark("dashboard-overdue-none")
            for index, row in enumerate(progress.overdue):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.label(moment_text(row.limit)).classes("text-negative")
                    ui.label(row.name).classes("col ellipsis").mark(
                        f"dashboard-overdue-name-{index}"
                    )
                    if row.forecast is not None:
                        ui.label(f"見込み {row.forecast:%m/%d}").classes(
                            "text-grey text-caption"
                        ).mark(f"dashboard-overdue-forecast-{index}")
                    self.assignee_chips(
                        row.assignee_names, f"dashboard-overdue-assignee-{index}"
                    )

    def edit_toggle(self) -> None:
        ui.checkbox(
            "割り当てを編集",
            value=self.assign_mode,
            on_change=lambda e: self.set_assign_mode(bool(e.value)),
        ).props("dense").mark("dashboard-unassigned-edit")

    def unassigned_row(self, progress: Progress) -> None:
        """`担当なし n 件`の行。ふだんはマウスオーバーでタスク名を見せるだけ。`割り当てを編集`をオンにすると、押して担当を選べる(要望 39)。
        警告のタスクがあるときは、同じ編集で、警告のタスクを押してメンバーを足せる(要望 134)。担当なしがなくても、警告があればチェックボックスを出す。"""
        if not progress.unassigned and not progress.warning_tasks:
            self.assign_mode = False  # 対象がなくなったら、次に増えたときはオフから
            return
        with ui.row().classes("w-full items-center gap-2"):
            if progress.unassigned:
                with ui.row().classes("items-center no-wrap gap-1"):
                    ui.icon("person_off", size="sm").classes("text-warning")
                    label = ui.label(f"担当なし {len(progress.unassigned)}件").mark(
                        "dashboard-unassigned-count"
                    )
                    if not self.assign_mode:
                        with label:
                            name_chips_tooltip(
                                [t.name for t in progress.unassigned],
                                "dashboard-unassigned-chip",
                                more_marker="dashboard-unassigned-more",
                            )
            self.edit_toggle()
        if self.assign_mode and progress.unassigned:
            with ui.row().classes("w-full gap-1"):
                for index, task in enumerate(progress.unassigned):
                    chip = ui.chip(
                        task.name,
                        color=None,
                        on_click=lambda t=task.id: self.assign(t),
                    ).props("dense square outline clickable")
                    chip.classes("ellipsis").mark(f"dashboard-unassigned-pick-{index}")
        if self.assign_mode and progress.warning_tasks:
            with ui.row().classes("w-full items-center gap-1"):
                warning_icon("dashboard-warning-pick-icon")
                ui.label("警告のタスクに足す").classes("text-caption")
                for index, warned in enumerate(progress.warning_tasks):
                    chip = ui.chip(
                        warned.name,
                        color=None,
                        on_click=lambda t=warned.id: self.add_crew(t),
                    ).props("dense square outline clickable")
                    chip.classes("ellipsis").mark(f"dashboard-warning-pick-{index}")

    def set_assign_mode(self, on: bool) -> None:
        if on != self.assign_mode:
            self.assign_mode = on
            self.cards.refresh()

    def add_crew(self, task_id: str) -> None:
        if self.assign_mode and self.on_add_crew is not None:
            self.on_add_crew(task_id)

    def assign(self, task_id: str) -> None:
        if self.assign_mode and self.on_assign is not None:
            self.on_assign(task_id)

    def member_icon(self, name: str, marker: str | None = None) -> None:
        """メンバーのアイコン(なければ頭文字の丸)。メンバーでない行(`未割り当て`)には出さない。"""
        if name == UNASSIGNED:
            return
        element = avatar(name, self.icons.get(name, ""), 20)
        if marker:
            element.mark(marker)

    def assignee_chips(self, names: tuple[str, ...], marker: str) -> None:
        """担当者を、アイコンと名前の組で人ごとに並べる。担当なしは何も出さない。"""
        with ui.row().classes("items-center no-wrap gap-2").mark(marker):
            for name in names:
                with ui.row().classes("items-center no-wrap gap-1"):
                    self.member_icon(name)
                    ui.label(name).classes("text-caption")

    def member_progress_row(
        self, row: MemberProgress, marker: str = "dashboard-member"
    ) -> None:
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("items-center no-wrap gap-2"):
                if marker == "dashboard-member":  # チーム別の行はメンバーではない
                    self.member_icon(row.name, f"{marker}-icon-{row.name}")
                ui.label(row.name)
                if row.over_limit:
                    warning_icon(f"{marker}-limit-{row.name}").tooltip(
                        f"警告が閾値({row.limit} 件)に達しています"
                    )
            if row.warnings:
                with (
                    ui.label(f"警告 {row.warnings} 件")
                    .classes(
                        "text-caption" + (" text-weight-bold" if row.over_limit else "")
                    )
                    .mark(f"{marker}-warning-{row.name}")
                ):
                    name_chips_tooltip(
                        row.warned_tasks,
                        f"{marker}-warning-chip-{row.name}",
                        more_marker=f"{marker}-warning-more-{row.name}",
                    )
            if row.percent is None:
                ui.label("タスクなし").classes("text-caption text-grey").mark(
                    f"{marker}-progress-{row.name}"
                )
                return
            ui.label(f"{row.percent:.0f}% / {sum(row.counts.values())}件").classes(
                "text-caption"
            ).mark(f"{marker}-progress-{row.name}")
            if row.delta is not None:
                ui.label(f"進んだ分 {round(row.delta):+d}%").classes(
                    "text-caption"
                ).mark(f"{marker}-delta-{row.name}")
            bar(row.percent / 100, LOAD_COLOR)

    def pick_member(self, name: object) -> None:
        """人の名前の押下。ダッシュボード全体をその人に絞る(同じ人をもう一度押すと全員に戻す)。"""
        data = self.data
        if (
            not isinstance(name, str)
            or data is None
            or self.on_member_change is None
            or name not in data.members
        ):
            return
        self.on_member_change(None if data.member == name else name)

    def order_controls(self, suffix: str) -> None:
        """並び替え(負荷の高い順)と絞り込み(割り当て超過の人だけ)。2 つのカードで同じ状態を共有する。"""
        with ui.row().classes("w-full items-center gap-4"):
            ui.checkbox(
                "負荷の高い順",
                value=self.sort_by_load,
                on_change=lambda e: self.set_order(sort_by_load=bool(e.value)),
            ).props("dense").mark(f"dashboard-sort-{suffix}")
            ui.checkbox(
                "割り当て超過の人だけ",
                value=self.over_only,
                on_change=lambda e: self.set_order(over_only=bool(e.value)),
            ).props("dense").mark(f"dashboard-over-only-{suffix}")

    def set_order(
        self, sort_by_load: bool | None = None, over_only: bool | None = None
    ) -> None:
        if sort_by_load is not None:
            self.sort_by_load = sort_by_load
        if over_only is not None:
            self.over_only = over_only
        self.cards.refresh()

    def load_row(
        self,
        name: str,
        stats: LoadStats,
        counts: tuple[int, int] | None = None,
    ) -> None:
        """1 人 1 行(名前・棒・数字を横に並べる)。棒は 0〜200% で固定し、100% に点線の目印、最大に縦の印を出す。"""
        over = stats.overload_days > 0
        with ui.row().classes("w-full items-center gap-x-3 gap-y-0"):
            with ui.column().classes("gap-0").style("width: 9rem; flex: none"):
                with ui.row().classes("items-center no-wrap gap-2"):
                    self.member_icon(name, f"dashboard-load-icon-{name}")
                    ui.label(name).classes("cursor-pointer ellipsis").on(
                        "click", lambda _=None, n=name: self.pick_member(n)
                    ).mark(f"dashboard-load-name-{name}")
                late, warned = counts or (0, 0)
                if late or warned:
                    with ui.row().classes("items-center no-wrap gap-2"):
                        if late:
                            ui.label(f"遅れ {late} 件").classes(
                                "text-caption text-negative"
                            ).mark(f"dashboard-load-late-{name}")
                        if warned:
                            ui.label(f"警告 {warned} 件").classes("text-caption").style(
                                "color: var(--warning)"
                            ).mark(f"dashboard-load-warning-{name}")
            with ui.element("div").style("flex: 1 1 8rem; min-width: 8rem"):
                bar(
                    stats.average / LOAD_SCALE,
                    OVER_COLOR if over else LOAD_COLOR,
                    tick=stats.peak / LOAD_SCALE,
                    reference=1.0 / LOAD_SCALE,
                )
            ui.label(
                f"平均 {stats.average * 100:.0f}% / 最大 {stats.peak * 100:.0f}% / 割り当て超過 {stats.overload_days} 日"
            ).classes("text-caption" + (" text-negative" if over else "")).style(
                "flex: none"
            ).mark(f"dashboard-load-{name}")

    def load_summary(self, loads: dict[str, LoadStats]) -> None:
        """カードの見出しの下の 1 行。割り当て超過の人数と、最大の人。"""
        if not loads:
            return
        over = sum(1 for stats in loads.values() if stats.overload_days > 0)
        top = max(loads, key=lambda n: loads[n].peak)
        text = f"割り当て超過 {over} 名 / {len(loads)} 名"
        if loads[top].peak > 1.0 + OVERLOAD_EPSILON:
            text += f"・最大 {loads[top].peak * 100:.0f}%({top})"
        ui.label(text).classes(
            "text-caption" + (" text-negative" if over else " text-grey")
        ).mark("dashboard-load-summary")

    def load_card(self, data: Dashboard) -> None:
        with card("人ごとの負荷", "dashboard-load"):
            if data.cross is None:  # 全プロジェクトを重ねる負荷は按分しない
                weighted_note(data, "load")
            if data.cross is not None:
                self.cross_load_card(data.cross, late_counts(data))
                return
            if not data.loads:
                empty_message("dashboard-empty-load")
                return
            self.load_summary(data.loads)
            self.order_controls("load")
            counts = late_counts(data)
            names = load_order(data.loads, self.sort_by_load, self.over_only)
            if not names:
                empty_message("dashboard-load-none")
            with self.rows_box():
                for name in names:
                    self.load_row(name, data.loads[name], counts.get(name))

    def heatmap_card(self, data: Dashboard) -> None:
        cross = data.heat_summary
        if cross is None or not cross.loads:
            return
        box = card("負荷の日ごとの推移", "dashboard-heatmap")
        box.style("grid-column: 1 / -1; min-width: 0")
        with box:
            if not any(entry.days for entry in cross.loads.values()):
                ui.label("稼働日がありません").classes("text-grey").mark(
                    "dashboard-heatmap-empty"
                )
                return
            columns = max(len(entry.days) for entry in cross.loads.values())
            if columns > HEATMAP_HINT_DAYS:
                ui.label("横にスクロールできます").classes(
                    "text-caption text-grey"
                ).mark("dashboard-heatmap-hint")
            self.order_controls("heatmap")
            ui.html(legend_html(), sanitize=False)
            totals = {name: entry.total for name, entry in cross.loads.items()}
            order = load_order(totals, self.sort_by_load, self.over_only)
            if not order:
                empty_message("dashboard-heatmap-none")
            table = (
                ui.html(
                    heatmap_html(
                        cross, self.icons, clock.today(), order, late_counts(data)
                    ),
                    sanitize=False,
                )
                .style("min-width: 0; max-width: 100%; overflow-x: auto")
                .mark("dashboard-heatmap-table")
            )
            ui.run_javascript(scroll_to_today_js(table.id))

    def cross_load_card(
        self, cross: CrossSummary, counts: dict[str, tuple[int, int]]
    ) -> None:
        ui.label(
            "同じ名前のメンバーを同一人物として、全プロジェクトを重ねています。開いているプロジェクト以外は保存済みの内容です。"
        ).classes("text-caption text-grey").mark("dashboard-cross-note")
        with ui.row().classes("w-full gap-2"):
            for name in cross.projects:
                ui.checkbox(
                    name,
                    value=name not in cross.excluded,
                    on_change=lambda event, name=name: self.on_project(
                        name, bool(event.value)
                    ),
                ).mark(f"dashboard-cross-project-{name}")
        for index, failure in enumerate(cross.failures):
            ui.label(
                f"読み込めなかったファイル: {failure.name}({failure.reason})"
            ).classes("text-caption text-negative").mark(
                f"dashboard-cross-failure-{index}"
            )
        if not cross.loads:
            empty_message("dashboard-empty-load")
            return
        totals = {name: entry.total for name, entry in cross.loads.items()}
        self.load_summary(totals)
        self.order_controls("load")
        names = load_order(totals, self.sort_by_load, self.over_only)
        if not names:
            empty_message("dashboard-load-none")
        with self.rows_box():
            for name in names:
                entry = cross.loads[name]
                with ui.column().classes("w-full gap-0"):
                    self.load_row(name, entry.total, counts.get(name))
                    with ui.expansion("プロジェクト別").classes("w-full text-caption"):
                        for index, row in enumerate(entry.by_project):
                            ui.label(
                                f"{row.project}: 平均 {row.average * 100:.0f}% / 最大 {row.peak * 100:.0f}%"
                            ).mark(f"dashboard-cross-detail-{name}-{index}")

    def hours_card(self, data: Dashboard) -> None:
        with card("工数の予定と実績", "dashboard-hours"):
            weighted_note(data, "hours")
            if not data.workload:
                empty_message("dashboard-empty-hours")
                return
            legend(
                "dashboard-hours",
                (("予定", PLANNED_COLOR, "planned"), ("実績", ACTUAL_COLOR, "actual")),
            )
            scale = (
                max(
                    (max(row.planned_hours, row.actual_hours) for row in data.workload),
                    default=0.0,
                )
                or 1.0
            )
            for row in data.workload:
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("items-center no-wrap gap-2"):
                        self.member_icon(row.name, f"dashboard-hours-icon-{row.name}")
                        ui.label(row.name)
                    ui.label(
                        f"予定 {row.planned_hours:.1f}h / 実績 {row.actual_hours:.1f}h"
                    ).classes("text-caption").mark(f"dashboard-hours-{row.name}")
                    bar(row.planned_hours / scale, PLANNED_COLOR)
                    bar(row.actual_hours / scale, ACTUAL_COLOR)
            ui.label(
                f"合計 予定 {data.planned_total:.1f}h / 実績 {data.actual_total:.1f}h"
            ).classes("text-subtitle2").mark("dashboard-hours-total")

    def burndown_card(self, data: Dashboard) -> None:
        b = data.burndown
        if b is None or b.whole:  # 全期間は、履歴のある期間を添える
            scope = scope_label(data, None)
            if b is not None:
                scope += f"・履歴のある期間 {b.first:%m/%d}〜{b.last:%m/%d}"
        else:
            scope = scope_label(data, Period(b.first, b.last))
        with card("残りの工数の推移", "dashboard-burndown"):
            ui.label(scope).classes("text-caption text-grey").mark(
                "dashboard-burndown-scope"
            )
            if b is None:
                empty_message("dashboard-empty-burndown")
                return
            if b.known and not b.count:
                empty_message("dashboard-empty-burndown")
                return
            if b.known:
                ui.html(chart_svg(b), sanitize=False).classes("w-full").mark(
                    "dashboard-burndown-chart"
                )
            for line in burndown_lines(b):
                with ui.row().classes("items-center no-wrap gap-1"):
                    if line.key == "behind":
                        warning_icon("dashboard-burndown-behind-icon")
                    with (
                        ui.label(line.text)
                        .classes("text-caption")
                        .mark(f"dashboard-burndown-{line.key}")
                    ):
                        if line.key == "unset":
                            name_chips_tooltip(
                                b.unset,
                                "dashboard-burndown-chip",
                                more_marker="dashboard-burndown-more",
                            )

    def backlog_card(self, data: Dashboard) -> None:
        backlog = data.backlog
        with card("残りの工数と必要人数", "dashboard-backlog"):
            weighted_note(data, "backlog")
            cross_note(data)
            if backlog.hours <= 0 and not backlog.unset_count:
                empty_message("dashboard-empty-backlog")
                return
            known = backlog.required is not None and backlog.shortfall is not None
            if backlog.shortfall is not None:  # 答え(あと何人)を先頭に出す
                ui.label(shortage_text(backlog.shortfall)).classes(
                    "text-h6"
                    + (" text-negative" if round(backlog.shortfall, 1) > 0 else "")
                ).mark("dashboard-backlog-gap")
            ui.label(
                f"残りの工数 {backlog.hours:.1f}h({late_summary(backlog)})"
            ).classes("text-subtitle2" if known else "text-h6").mark(
                "dashboard-backlog-hours"
            )
            self.hours_graph(backlog)
            self.late_line(backlog)
            if backlog.unset_count:
                ui.label(
                    f"工数未設定 {backlog.unset_count} 件(合計に入れていません)"
                ).classes("text-caption text-grey").mark("dashboard-backlog-unset")
            if (
                backlog.required is None
                or backlog.shortfall is None
                or backlog.days is None
            ):
                reason = (
                    "期間がすでに終わっている"
                    if backlog.days == 0
                    else "期間が決まらない"
                )
                ui.label(f"{reason}ため、必要な人数は出せません").classes(
                    "text-grey"
                ).mark("dashboard-backlog-nodays")
            else:
                ui.label(f"稼働 {days_text(backlog.days)} 日で終える場合").classes(
                    "text-caption"
                ).mark("dashboard-backlog-days")
                scale = max(backlog.required, backlog.supply) or 1.0
                overdue = min(backlog.overdue_required or 0.0, backlog.required)
                warned = min(
                    backlog.warning_required or 0.0, backlog.required - overdue
                )
                ui.label(f"必要 {backlog.required:.1f} 人").mark(
                    "dashboard-backlog-need"
                )
                stacked_bar(
                    [
                        (
                            (backlog.required - overdue - warned) / scale,
                            NEED_COLOR,
                            "dashboard-backlog-bar-need",
                            None,
                        ),
                        (
                            warned / scale,
                            WARNING_FILL,
                            "dashboard-backlog-bar-warning",
                            f"警告 {backlog.warning_hours:.1f}h({warned:.1f} 人)",
                            WARNING_OUTLINE,
                        ),
                        (
                            overdue / scale,
                            LATE_COLOR,
                            "dashboard-backlog-bar-late",
                            f"遅れ {backlog.overdue_hours:.1f}h({overdue:.1f} 人)",
                        ),
                    ]
                )
                entries = (
                    (("うち警告", WARNING_FILL, "warning"),)
                    if backlog.warning_count and warned > 0
                    else ()
                ) + (
                    (("うち遅れ", LATE_COLOR, "late"),)
                    if backlog.overdue_count and overdue > 0
                    else ()
                )
                if entries:  # 凡例は、積み上げの棒のすぐ下に置く
                    legend("dashboard-backlog", entries)
                ui.label(f"稼働できる人員 {backlog.supply:.1f} 人").mark(
                    "dashboard-backlog-have"
                )
                bar(
                    backlog.supply / scale,
                    HAVE_COLOR,
                    marker="dashboard-backlog-bar-have",
                )
                ui.label(
                    "人は、100% の人に換算した数です。今日は、今から稼働の枠の終わりまでの残り時間で数えます。"
                ).classes("text-caption text-grey").mark("dashboard-backlog-unit")
                if backlog.nominal_supply is not None:
                    ui.label(
                        f"相対比率の合計 {backlog.nominal_supply:.1f} 人 → 稼働を反映して {backlog.supply:.1f} 人"
                    ).classes("text-caption text-grey").mark(
                        "dashboard-backlog-supply-note"
                    )
            if backlog.by_member:
                ui.label("担当別").classes("text-subtitle2")
                top = max(hours for _, hours in backlog.by_member)
                for name, hours in backlog.by_member:
                    with ui.row().classes("items-center no-wrap gap-2"):
                        self.member_icon(name, f"dashboard-backlog-member-icon-{name}")
                        ui.label(f"{name} {hours:.1f}h").classes("text-caption").mark(
                            f"dashboard-backlog-member-{name}"
                        )
                    bar(
                        hours / top,
                        NEED_COLOR,
                        marker=f"dashboard-backlog-member-bar-{name}",
                    )
            if backlog.by_team:
                ui.label("チーム別").classes("text-subtitle2")
                top = max(hours for _, hours in backlog.by_team)
                for name, hours in backlog.by_team:
                    ui.label(f"{name} {hours:.1f}h").classes("text-caption").mark(
                        f"dashboard-backlog-team-{name}"
                    )
                    bar(hours / top, NEED_COLOR)

    def hours_graph(self, backlog: Backlog) -> None:
        """残りの工数の内訳(状態ごと)の積み上げ棒。値はホバーに出し、色は円グラフと同じ状態色。"""
        total = sum(backlog.by_status.values())
        if total <= 0:
            return
        stacked_bar(
            [
                (
                    hours / total,
                    f"var({PIE_VARS[status]})",
                    f"dashboard-backlog-hours-bar-{status.name.lower()}",
                    f"{status.value} {hours:.1f}h",
                )
                for status, hours in backlog.by_status.items()
            ]
        )
        legend(
            "dashboard-backlog-hours",
            tuple(
                (status.value, f"var({PIE_VARS[status]})", status.name.lower())
                for status in backlog.by_status
            ),
        )

    def late_line(self, backlog: Backlog) -> None:
        """遅れがなかった場合の不足(遅れがあり、期間が決まっているときだけ)。遅れの判定の選択も置く。
        選んでいる側は塗りつぶし、押すと on_late_basis_change で基準を切り替える(選択は保存しない)。"""
        required, without = backlog.late_required, backlog.shortfall_without_overdue
        if backlog.late_count and required is not None and without is not None:
            name = "遅れ・警告" if backlog.late_basis is LateBasis.WARNING else "遅れ"
            ui.label(f"{name}がなければ {shortage_text(without)}").classes(
                "text-caption"
            ).mark("dashboard-backlog-late")
        with ui.button_group().props("flat dense").mark("dashboard-backlog-late-basis"):
            for basis, marker in (
                (LateBasis.DELAY, "delay"),
                (LateBasis.WARNING, "warning"),
            ):
                props = "dense no-caps color=primary size=sm" + (
                    "" if backlog.late_basis is basis else " outline"
                )
                ui.button(
                    basis.value,
                    on_click=lambda b=basis, now=backlog.late_basis: (
                        self.pick_late_basis(b, now)
                    ),
                ).props(props).mark(f"dashboard-backlog-late-{marker}")
        self.catch_up_controls(backlog.catch_up)
        self.recovery_controls(backlog)
        self.invest_controls(backlog)

    def catch_up_controls(self, rule: CatchUp) -> None:
        """遅れを取り戻す期限の選択(`期間の終わり`・`タスクごと`)。`タスクごと`のときは、予定超過を取り戻す稼働日数の欄も出す(選択は保存しない)。"""
        with ui.row().classes("items-center gap-2").mark("dashboard-backlog-catch-up"):
            with ui.button_group().props("flat dense"):
                for mode, marker in (
                    (CatchUpMode.PERIOD, "period"),
                    (CatchUpMode.TASK, "task"),
                ):
                    props = "dense no-caps color=primary size=sm" + (
                        "" if rule.mode is mode else " outline"
                    )
                    ui.button(
                        mode.value,
                        on_click=lambda m=mode, now=rule: self.pick_catch_up(
                            replace(now, mode=m), now
                        ),
                    ).props(props).mark(f"dashboard-backlog-catch-up-{marker}")
            if rule.mode is CatchUpMode.TASK:
                ui.label("予定超過は").classes("text-caption")
                field = (
                    ui.number(value=rule.days, min=1, max=60, step=1, format="%d")
                    .props("dense outlined style=width:5rem")
                    .mark("dashboard-backlog-catch-up-days")
                )
                for event in ("blur", "keydown.enter"):
                    field.on(
                        event,
                        lambda _=None, f=field, now=rule: self.pick_catch_up(
                            replace(now, days=int(f.value or now.days)), now
                        ),
                    )
                ui.label("稼働日で取り戻す").classes("text-caption")

    def recovery_controls(self, backlog: Backlog) -> None:
        """遅れを取り戻すために追加する人数の欄と、追加した人だけで取り戻せる日の試算(要望 130)。保存しない。"""
        rule = backlog.catch_up
        with ui.row().classes("items-center gap-2").mark("dashboard-backlog-recover"):
            ui.label("遅れを取り戻す追加人数").classes("text-caption")
            people = (
                ui.number(
                    value=rule.people,
                    min=0,
                    max=MAX_RECOVER_PEOPLE,
                    step=0.5,
                    format="%.1f",
                )
                .props("dense outlined style=width:5rem")
                .mark("dashboard-backlog-recover-people")
            )
            for event in ("blur", "keydown.enter"):
                people.on(
                    event,
                    lambda _=None, f=people, now=rule: self.pick_catch_up(
                        replace(now, people=float(f.value or 0.0)), now
                    ),
                )
            ui.label("人(100% の人に換算)").classes("text-caption")
        if rule.people <= 0:
            return
        recovery = backlog.recovery
        if recovery is None:
            ui.label("遅れはありません").classes("text-caption").mark(
                "dashboard-backlog-recovery"
            )
            return
        with (
            ui.row()
            .classes("items-center gap-1")
            .mark("dashboard-backlog-recovery-row")
        ):
            if (
                recovery.date is not None
                and recovery.due is not None
                and (recovery.date > recovery.due)
            ):
                warning_icon("dashboard-backlog-recovery-icon")
            ui.label(recovery_text(recovery)).classes("text-caption").mark(
                "dashboard-backlog-recovery"
            )
        ui.label(
            "追加した人だけで遅れを取り戻す前提の、稼働時間の算術です(予測ではありません)。"
            "追加した人が並行して進められること、立ち上がりの遅れは見ていません。"
        ).classes("text-caption text-grey").mark("dashboard-backlog-recovery-note")

    def invest_controls(self, backlog: Backlog) -> None:
        """遅れを取り戻すために投入する人の候補(余力の多い順)と、選んだ人を投入したときに取り戻せる日の試算(要望 131)。
        選択は保存しない。遅れがないとき・候補がいないときは出さない。"""
        if backlog.late_hours <= 0 or not backlog.candidates:
            return
        rule = backlog.catch_up
        with ui.column().classes("gap-0").mark("dashboard-backlog-candidates"):
            ui.label("投入の候補(余力の多い順)").classes("text-caption")
            for candidate in backlog.candidates:
                has_spare = candidate.spare_hours > 0
                label = (
                    f"{candidate.name}  余力 {candidate.spare_hours:.1f}h"
                    if has_spare
                    else f"{candidate.name}  余力なし"
                )
                box = (
                    ui.checkbox(
                        label,
                        value=candidate.name in rule.invest,
                        on_change=lambda e, n=candidate.name, now=rule: (
                            self.pick_catch_up(
                                replace(now, invest=toggled(now.invest, n, e.value)),
                                now,
                            )
                        ),
                    )
                    .props("dense")
                    .mark(f"dashboard-backlog-candidate-{candidate.name}")
                )
                if not has_spare:
                    box.disable()
        if rule.invest and self.on_try_on_gantt is not None:
            handler = self.on_try_on_gantt
            ui.button(
                "ガントチャートで試す",
                on_click=lambda names=rule.invest: handler(names),
            ).props("dense flat").mark("dashboard-backlog-try-gantt")
        investment = backlog.investment
        if investment is None:
            return
        missed = investment.date is None or (
            investment.due is not None and investment.date > investment.due
        )
        with (
            ui.row().classes("items-center gap-1").mark("dashboard-backlog-invest-row")
        ):
            if missed:
                warning_icon("dashboard-backlog-invest-icon")
            ui.label(investment_text(investment)).classes("text-caption").mark(
                "dashboard-backlog-invest"
            )
        ui.label(
            "選んだ人が自分の余力の範囲で遅れを手伝う前提の、稼働時間の算術です(予測ではありません)。"
            "並行して進められること、立ち上がりの遅れは見ていません。"
        ).classes("text-caption text-grey").mark("dashboard-backlog-invest-note")

    def pick_catch_up(self, rule: CatchUp, current: CatchUp) -> None:
        """取り戻す期限と追加人数を選ぶ。今と同じなら何もしない。日数は 1〜60、追加人数は 0〜20(小数 1 桁)に収める。"""
        rule = replace(
            rule,
            days=min(60, max(1, rule.days)),
            people=round(min(MAX_RECOVER_PEOPLE, max(0.0, rule.people)), 1),
        )
        if rule != current and self.on_catch_up_change is not None:
            self.on_catch_up_change(rule)

    def pick_late_basis(self, basis: LateBasis, current: LateBasis) -> None:
        """遅れの判定の基準を選ぶ。今の基準と同じなら何もしない。"""
        if basis is not current and self.on_late_basis_change is not None:
            self.on_late_basis_change(basis)

    def due_card(self, data: Dashboard) -> None:
        with card("期限とマイルストーン", "dashboard-due"):
            if not data.due:
                empty_message("dashboard-empty-due")
                return
            for index, row in enumerate(data.due):
                color = " text-negative" if row.overdue else ""
                line = ui.row().classes("w-full items-center no-wrap gap-2")
                if row.warning:
                    line.style(f"background: {WARNING_BACKGROUND}")
                with line:
                    ui.label(moment_text(row.moment)).classes(color.strip())
                    ui.label(row.kind).classes("text-caption" + color).mark(
                        f"dashboard-due-kind-{index}"
                    )
                    ui.label(row.name).classes("col ellipsis" + color).mark(
                        f"dashboard-due-{index}"
                    )
                    if row.warning:
                        warning_icon(f"dashboard-due-warning-icon-{index}")
                        ui.label("警告").classes("text-caption").mark(
                            f"dashboard-due-warning-{index}"
                        )
                    self.assignee_chips(
                        row.assignee_names, f"dashboard-due-assignee-{index}"
                    )
