"""ダッシュボードの表示。集計(dashboard.py)の結果を、カードと横棒で描く。"""

from collections.abc import Callable
from datetime import datetime

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.avatar import avatar
from projectapp.dashboard import CrossSummary, Dashboard, LoadStats, MemberProgress, PeriodKind, TeamProgress
from projectapp.gantt import STATUS_COLORS, STATUS_DARK_COLORS
from projectapp.models import Status

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
    ) -> None:
        self.on_back, self.on_change, self.on_member_change = on_back, on_change, on_member_change
        self.on_cross_change, self.on_project_change = on_cross_change, on_project_change
        self.cross_switch: ui.switch | None = None
        self.box: ui.column | None = None
        self.toggle: ui.toggle | None = None
        self.member_select: ui.select | None = None
        self.data: Dashboard | None = None
        self.icons: dict[str, str] = {}  # メンバー名 → アイコン(ある人だけ)
        self.syncing = False  # 開き直しでトグルの値を書き換えるあいだは、変更を通知しない

    def build(self) -> None:
        ui.add_css(PIE_CSS)
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

    def on_member(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and self.on_member_change is not None:
            self.on_member_change(event.value or None)

    def on_cross(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and self.on_cross_change is not None:
            self.on_cross_change(bool(event.value))

    def on_project(self, name: str, included: bool) -> None:
        if not self.syncing and self.on_project_change is not None:
            self.on_project_change(name, included)

    def show(self, data: Dashboard, kind: PeriodKind, icons: dict[str, str] | None = None) -> None:
        self.icons = icons or {}
        self.data = data
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
        with ui.element("div").style(GRID_STYLE):
            self.team_card(data)
            self.progress_card(data)
            self.load_card(data)
            self.hours_card(data)
            self.due_card(data)

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
