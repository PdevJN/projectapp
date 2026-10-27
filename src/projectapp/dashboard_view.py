"""ダッシュボードの表示。集計(dashboard.py)の結果を、カードと横棒で描く。"""

import html
from collections.abc import Callable
from datetime import date, datetime

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.avatar import avatar
from projectapp.dashboard import (
    CrossSummary,
    Dashboard,
    DayLoad,
    LoadStats,
    MemberProgress,
    PeriodKind,
    TeamProgress,
)
from projectapp.dashboard_views import DEFAULT_ORDER, CardId, ViewState
from projectapp.gantt import STATUS_COLORS, STATUS_DARK_COLORS, WEEKDAYS
from projectapp.models import Status
from projectapp.periodfield import add_range_picker, normalize_period
from projectapp.timeline import OVERLOAD_EPSILON

TRACK_STYLE = (
    "height: 10px; width: 100%; border-radius: 5px; overflow: hidden;"
    " background: rgba(128, 128, 128, 0.25); position: relative"
)
TICK_STYLE = "position: absolute; top: 0; bottom: 0; width: 2px; background: currentColor"
GRID_STYLE = "display: grid; grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr)); gap: 16px; width: 100%"
LOAD_COLOR = "#1e88e5"  # 負荷・進捗
OVER_COLOR = "#ef5350"  # 100% を超える日がある負荷(予定超過の赤と同じ系統)
PLANNED_COLOR = "#1e88e5"  # 予定の時間。dataviz の検証で、灰青は「灰色に見える」ため不合格。青と緑の組は全項目 PASS
ACTUAL_COLOR = "#43a047"  # 実績の時間
EMPTY = "データがありません"
ALL_MEMBERS = ""  # プルダウンの`全員`の値
MAX_TIP_CHIPS = 10  # 凡例のツールチップに並べるチップの上限。超えた分は「+n件」にまとめる
PIE_DIAMETER = "9rem"
PIE_HOLE_PERCENT = 60  # 中央に進捗率を出すための穴(円の半径に対する割合)
PIE_VARS = {status: f"--pie-{status.name.lower().replace('_', '-')}" for status in Status}
# 状態色はガントチャートの棒と同じ。ダークテーマでは明るい色に替える
PIE_CSS = (
    ":root { "
    + " ".join(f"{PIE_VARS[status]}: {STATUS_COLORS[status]};" for status in Status)
    + " }\nbody.body--dark { "
    + " ".join(f"{PIE_VARS[status]}: {STATUS_DARK_COLORS[status]};" for status in Status)
    + " }"
)


CELL_PX = 26  # 見出しの `10/22` が収まる幅
HEATMAP_HINT_DAYS = 20  # これより列が多いとき、横にスクロールできることを案内する
HEATMAP_CSS = (
    ".heatmap-name { position: sticky; left: 0; background: #fff; padding-right: 8px; white-space: nowrap }\n"
    ".heat-cell { width: 26px; height: 26px; border: 1px solid rgba(128, 128, 128, 0.25) }\n"
    ".heat-over { outline: 2px solid #b71c1c; outline-offset: -2px }\n"
    ".heatmap-scroll { overflow-x: auto; max-width: 100% }\n"
    ".heatmap-scroll::-webkit-scrollbar { height: 12px }\n"
    ".heatmap-scroll::-webkit-scrollbar-track { background: rgba(128, 128, 128, 0.15) }\n"
    ".heatmap-scroll::-webkit-scrollbar-thumb { background: rgba(128, 128, 128, 0.55); border-radius: 6px }\n"
    "body.body--dark .heatmap-name { background: #1d1d1d }\n"
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
    return f"background: {rgba(OVER_COLOR, 0.55 + 0.45 * min(total - 1.0, 1.0))}"


def cell_class(total: float) -> str:
    return "heat-cell heat-over" if total > 1.0 + OVERLOAD_EPSILON else "heat-cell"


def cell_title(name: str, load: DayLoad) -> str:
    head = f"{name} {load.day:%m/%d}({WEEKDAYS[load.day.weekday()]}) {load.total * 100:.0f}%"
    lines = [html.escape(head)]
    if load.by_project:
        lines.append(html.escape(" / ".join(f"{p.project} {p.peak * 100:.0f}%" for p in load.by_project)))
    return "&#10;".join(lines)


def heatmap_html(cross: CrossSummary) -> str:
    """人×稼働日の表。名前・プロジェクト名はエスケープする。"""
    first = next(iter(cross.loads.values()), None)
    days = first.days if first is not None else []
    head = "".join(
        f'<th class="text-caption" style="font-weight: normal; font-size: 10px; min-width: {CELL_PX}px">'
        f"<div>{day.day:%m/%d}</div><div>{WEEKDAYS[day.day.weekday()]}</div></th>"
        for day in days
    )
    rows = []
    for name, entry in cross.loads.items():
        cells = "".join(
            f'<td class="{cell_class(day.total)}" data-cell="{html.escape(name)}|{day.day.isoformat()}"'
            f' title="{cell_title(name, day)}" style="{cell_style(day.total)}"></td>'
            for day in entry.days
        )
        label = f'<th class="heatmap-name text-body2" style="text-align: left">{html.escape(name)}</th>'
        rows.append(f"<tr>{label}{cells}</tr>")
    return (
        '<div class="heatmap-scroll">'
        '<table style="border-collapse: separate; border-spacing: 2px">'
        f'<tr><th class="heatmap-name"></th>{head}</tr>{"".join(rows)}</table></div>'
    )


def legend_html() -> str:
    swatches = [(0.0, "0%"), (0.5, "50%"), (1.0, "100%"), (1.5, "超過")]
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


def bar(fraction: float, color: str, tick: float | None = None) -> None:
    """横棒。`tick` があれば、その位置に縦の印を出す(最大値など)。"""
    with ui.element("div").style(TRACK_STYLE):
        ui.element("div").style(f"height: 100%; width: {percent_width(fraction)}; background: {color}")
        if tick is not None:
            ui.element("div").style(f"{TICK_STYLE}; left: {percent_width(tick)}")


def pie_background(team: TeamProgress) -> str:
    """切片を状態の順に並べた conic-gradient。"""
    stops: list[str] = []
    start = 0.0
    for status, _, fraction in team.slices():
        end = start + fraction * 100
        stops.append(f"var({PIE_VARS[status]}) {start:.1f}% {end:.1f}%")
        start = end
    return f"conic-gradient({', '.join(stops)})"


def card(title: str, marker: str) -> ui.card:
    box = ui.card().classes("w-full gap-2").mark(marker)
    with box:
        ui.label(title).classes("text-subtitle1 text-weight-bold")
    return box


def empty_message(marker: str) -> None:
    ui.label(EMPTY).classes("text-grey").mark(marker)


def moment_text(moment: datetime) -> str:
    return f"{moment:%m/%d %H:%M}"


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
    ) -> None:
        self.on_custom_change = on_custom_change
        self.custom_field: ui.input | None = None
        self.custom_box: ui.column | None = None
        self.custom_error: ui.label | None = None
        self.on_back, self.on_change, self.on_member_change = on_back, on_change, on_member_change
        self.on_cross_change, self.on_project_change = on_cross_change, on_project_change
        self.cross_switch: ui.switch | None = None
        self.box: ui.column | None = None
        self.toggle: ui.toggle | None = None
        self.member_select: ui.select | None = None
        self.data: Dashboard | None = None
        self.icons: dict[str, str] = {}  # メンバー名 → アイコン(ある人だけ)
        self.syncing = False  # 開き直しでトグルの値を書き換えるあいだは、変更を通知しない
        self.state: ViewState | None = None  # ビューの選択・カードの並び。None のあいだは既定の順で全部出す
        self.card_order: tuple[CardId, ...] = DEFAULT_ORDER

    def build(self) -> None:
        ui.add_css(PIE_CSS)
        ui.add_css(HEATMAP_CSS)
        with ui.column().classes("w-full gap-4") as box:
            self.box = box
            box.mark("dashboard-box")
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("ダッシュボード").classes("text-h5")
                self.toggle = ui.toggle(
                    {kind.value: kind.value for kind in PeriodKind},
                    value=PeriodKind.WEEK.value,
                    on_change=self.on_toggle,
                ).mark("dashboard-period")
                with ui.column().classes("gap-0") as custom_box:  # `指定` のときだけ出す期間欄
                    self.custom_field = (
                        ui.input(placeholder="2026-10-01 〜 2026-10-31", on_change=self.on_custom)
                        .props("dense outlined")
                        .style("width: 17rem")
                        .mark("dashboard-period-field")
                    )
                    add_range_picker(self.custom_field, "dashboard-period")
                    self.custom_field.on("blur", lambda _e: self.normalize_custom())
                    self.custom_error = ui.label("").classes("text-negative text-caption").mark("dashboard-period-error")
                self.custom_box = custom_box
                custom_box.set_visibility(False)
                self.custom_field.set_visibility(False)
                self.member_select = (
                    ui.select({ALL_MEMBERS: "全員"}, value=ALL_MEMBERS, on_change=self.on_member)
                    .props("dense outlined options-dense")
                    .style("min-width: 8rem")
                    .mark("dashboard-member")
                )
                self.cross_switch = ui.switch("全プロジェクト", value=False, on_change=self.on_cross).mark(
                    "dashboard-cross"
                )
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props("flat").mark(
                    "dashboard-back"
                )
            self.cards()
        box.set_visibility(False)

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
        fixed = normalize_period(text, date.today()) if text.strip() else None
        if fixed is not None and fixed != text:
            self.custom_field.set_value(fixed)

    def on_member(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and self.on_member_change is not None:
            self.on_member_change(event.value or None)

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
        if self.custom_box is not None and self.custom_field is not None and self.custom_error is not None:
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
            options = {ALL_MEMBERS: "全員", **{name: name for name in data.members}}
            self.syncing = True
            try:
                self.member_select.set_options(options, value=data.member or ALL_MEMBERS)
            finally:
                self.syncing = False
        if self.cross_switch is not None and self.cross_switch.value != (data.cross is not None):
            self.syncing = True
            try:
                self.cross_switch.value = data.cross is not None
            finally:
                self.syncing = False
        if self.box is not None:
            self.box.set_visibility(True)
        self.cards.refresh()

    def hide(self) -> None:
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
            CardId.DUE: self.due_card,
        }
        with ui.element("div").style(GRID_STYLE):
            for card_id in self.card_order:
                builders[card_id](data)

    def team_card(self, data: Dashboard) -> None:
        team = data.team
        with card("チーム全体の進捗", "dashboard-team"):
            period = team.period
            scope = "すべてのタスク" if period is None else f"{period.start:%m/%d}〜{period.end:%m/%d} にかかるタスク"
            if data.member:
                scope = f"{data.member}・{scope}"
            ui.label(scope).classes("text-caption text-grey").mark("dashboard-team-scope")
            if team.percent is None:
                empty_message("dashboard-empty-team")
                return
            with ui.row().classes("w-full items-center no-wrap gap-4"):
                with ui.element("div").style(
                    f"position: relative; flex: none; width: {PIE_DIAMETER}; height: {PIE_DIAMETER}"
                ):
                    hole = f"radial-gradient(circle, transparent {PIE_HOLE_PERCENT}%, #000 {PIE_HOLE_PERCENT + 1}%)"
                    ui.element("div").style(
                        f"width: 100%; height: 100%; border-radius: 50%; background: {pie_background(team)};"
                        f" -webkit-mask: {hole}; mask: {hole}"
                    ).mark("dashboard-team-pie")
                    ui.label(f"{team.percent:.0f}%").classes("text-h6 absolute-center").mark("dashboard-team-percent")
                with ui.column().classes("gap-1"):
                    for status, hours, fraction in team.slices():
                        with ui.row().classes("items-center no-wrap gap-2"):
                            ui.element("span").style(
                                f"width: 10px; height: 10px; border-radius: 2px; background: var({PIE_VARS[status]})"
                            )
                            ui.label(f"{status.value} {team.counts[status]}件 {hours:.1f}h ({fraction * 100:.0f}%)").mark(
                                f"dashboard-team-legend-{status.name}"
                            )
                            self.status_tip(team, status)

    def status_tip(self, team: TeamProgress, status: Status) -> None:
        """凡例の行のツールチップ。その状態のタスク名をチップで並べる。"""
        names = team.tasks[status]
        with ui.tooltip().classes("bg-grey-9 text-white").style("max-width: 28rem"):
            with ui.row().classes("gap-1"):
                for name in names[:MAX_TIP_CHIPS]:
                    ui.chip(name, color=None).props("dense square outline").classes("ellipsis").style(
                        f"color: var({PIE_VARS[status]})"  # 枠と文字が currentColor になり、凡例の色と揃う
                    ).mark(f"dashboard-team-chip-{status.name}")
                if len(names) > MAX_TIP_CHIPS:
                    ui.label(f"+{len(names) - MAX_TIP_CHIPS}件").mark(f"dashboard-team-more-{status.name}")

    def progress_card(self, data: Dashboard) -> None:
        progress = data.progress
        with card("進捗と遅れ", "dashboard-progress"):
            if progress.percent is None:
                empty_message("dashboard-empty-progress")
                return
            ui.label(f"{progress.percent:.0f}%").classes("text-h4").mark("dashboard-progress-percent")
            bar(progress.percent / 100, LOAD_COLOR)
            with ui.row().classes("gap-4"):
                for status in Status:
                    ui.label(f"{status.value} {progress.counts[status]}").mark(f"dashboard-count-{status.name}")
            if progress.by_member:
                ui.label("メンバー別").classes("text-subtitle2")
                for row in progress.by_member:
                    self.member_progress_row(row)
            ui.label("予定超過").classes("text-subtitle2")
            if not progress.overdue:
                ui.label("なし").classes("text-grey").mark("dashboard-overdue-none")
            for index, row in enumerate(progress.overdue):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.label(moment_text(row.limit)).classes("text-negative")
                    ui.label(row.name).classes("col ellipsis").mark(f"dashboard-overdue-name-{index}")
                    ui.label(row.assignee or "").classes("text-caption")

    def member_progress_row(self, row: MemberProgress) -> None:
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("items-center no-wrap gap-2"):
                if icon := self.icons.get(row.name):
                    avatar(row.name, icon, 20).mark(f"dashboard-member-icon-{row.name}")
                ui.label(row.name)
            if row.percent is None:
                ui.label("タスクなし").classes("text-caption text-grey").mark(f"dashboard-member-progress-{row.name}")
                return
            ui.label(f"{row.percent:.0f}% / {sum(row.counts.values())}件").classes("text-caption").mark(
                f"dashboard-member-progress-{row.name}"
            )
            bar(row.percent / 100, LOAD_COLOR)

    def load_row(self, name: str, stats: LoadStats, scale: float) -> None:
        over = stats.overload_days > 0
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("items-center no-wrap gap-2"):
                if icon := self.icons.get(name):
                    avatar(name, icon, 20).mark(f"dashboard-load-icon-{name}")
                ui.label(name)
            ui.label(
                f"平均 {stats.average * 100:.0f}% / 最大 {stats.peak * 100:.0f}% / 超過 {stats.overload_days} 日"
            ).classes("text-caption" + (" text-negative" if over else "")).mark(f"dashboard-load-{name}")
            bar(stats.average / scale, OVER_COLOR if over else LOAD_COLOR, tick=stats.peak / scale)

    def load_card(self, data: Dashboard) -> None:
        with card("人ごとの負荷", "dashboard-load"):
            if data.cross is not None:
                self.cross_load_card(data.cross)
                return
            if not data.loads:
                empty_message("dashboard-empty-load")
                return
            scale = max(1.0, *(stats.peak for stats in data.loads.values()))
            for name, stats in data.loads.items():
                self.load_row(name, stats, scale)

    def heatmap_card(self, data: Dashboard) -> None:
        cross = data.cross
        if cross is None or not cross.loads:
            return
        box = card("負荷の日ごとの推移", "dashboard-heatmap")
        box.style("grid-column: 1 / -1; min-width: 0")
        with box:
            if not any(entry.days for entry in cross.loads.values()):
                ui.label("稼働日がありません").classes("text-grey").mark("dashboard-heatmap-empty")
                return
            columns = max(len(entry.days) for entry in cross.loads.values())
            if columns > HEATMAP_HINT_DAYS:
                ui.label("横にスクロールできます").classes("text-caption text-grey").mark("dashboard-heatmap-hint")
            ui.html(legend_html(), sanitize=False)
            ui.html(heatmap_html(cross), sanitize=False).style(
                "min-width: 0; max-width: 100%; overflow-x: auto"
            ).mark("dashboard-heatmap-table")

    def cross_load_card(self, cross: CrossSummary) -> None:
        ui.label(
            "同じ名前のメンバーを同一人物として、全プロジェクトを重ねています。開いているプロジェクト以外は保存済みの内容です。"
        ).classes("text-caption text-grey").mark("dashboard-cross-note")
        with ui.row().classes("w-full gap-2"):
            for name in cross.projects:
                ui.checkbox(
                    name,
                    value=name not in cross.excluded,
                    on_change=lambda event, name=name: self.on_project(name, bool(event.value)),
                ).mark(f"dashboard-cross-project-{name}")
        for index, failure in enumerate(cross.failures):
            ui.label(f"読み込めなかったファイル: {failure.name}({failure.reason})").classes(
                "text-caption text-negative"
            ).mark(f"dashboard-cross-failure-{index}")
        if not cross.loads:
            empty_message("dashboard-empty-load")
            return
        scale = max(1.0, *(entry.total.peak for entry in cross.loads.values()))
        for name, entry in cross.loads.items():
            self.load_row(name, entry.total, scale)
            with ui.expansion("プロジェクト別").classes("w-full text-caption"):
                for index, row in enumerate(entry.by_project):
                    ui.label(f"{row.project}: 平均 {row.average * 100:.0f}% / 最大 {row.peak * 100:.0f}%").mark(
                        f"dashboard-cross-detail-{name}-{index}"
                    )

    def hours_card(self, data: Dashboard) -> None:
        with card("工数の予定と実績", "dashboard-hours"):
            if not data.workload:
                empty_message("dashboard-empty-hours")
                return
            with ui.row().classes("items-center gap-4 text-caption"):  # 2 系列なので、凡例を出す
                for label, color, key in (("予定", PLANNED_COLOR, "planned"), ("実績", ACTUAL_COLOR, "actual")):
                    with ui.row().classes("items-center no-wrap gap-1"):
                        ui.element("div").style(f"width: 10px; height: 10px; border-radius: 2px; background: {color}")
                        ui.label(label).mark(f"dashboard-hours-legend-{key}")
            scale = max((max(row.planned_hours, row.actual_hours) for row in data.workload), default=0.0) or 1.0
            for row in data.workload:
                with ui.column().classes("w-full gap-1"):
                    ui.label(row.name)
                    ui.label(f"予定 {row.planned_hours:.1f}h / 実績 {row.actual_hours:.1f}h").classes(
                        "text-caption"
                    ).mark(f"dashboard-hours-{row.name}")
                    bar(row.planned_hours / scale, PLANNED_COLOR)
                    bar(row.actual_hours / scale, ACTUAL_COLOR)
            ui.label(f"合計 予定 {data.planned_total:.1f}h / 実績 {data.actual_total:.1f}h").classes(
                "text-subtitle2"
            ).mark("dashboard-hours-total")

    def due_card(self, data: Dashboard) -> None:
        with card("期限とマイルストーン", "dashboard-due"):
            if not data.due:
                empty_message("dashboard-empty-due")
                return
            for index, row in enumerate(data.due):
                color = " text-negative" if row.overdue else ""
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.label(moment_text(row.moment)).classes(color.strip())
                    ui.label(row.kind).classes("text-caption" + color).mark(f"dashboard-due-kind-{index}")
                    ui.label(row.name).classes("col ellipsis" + color).mark(f"dashboard-due-{index}")
                    ui.label(row.assignee or "").classes("text-caption")
