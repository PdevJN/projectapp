"""ダッシュボードの表示。集計(dashboard.py)の結果を、カードと横棒で描く。"""

from collections.abc import Callable
from datetime import datetime

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.dashboard import Dashboard, PeriodKind
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


def percent_width(fraction: float) -> str:
    """割合(0〜1)を、棒の幅(%)にする。範囲外は端に丸める。"""
    return f"{min(max(fraction, 0.0), 1.0) * 100:.1f}%"


def bar(fraction: float, color: str, tick: float | None = None) -> None:
    """横棒。`tick` があれば、その位置に縦の印を出す(最大値など)。"""
    with ui.element("div").style(TRACK_STYLE):
        ui.element("div").style(f"height: 100%; width: {percent_width(fraction)}; background: {color}")
        if tick is not None:
            ui.element("div").style(f"{TICK_STYLE}; left: {percent_width(tick)}")


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

    def __init__(self, on_back: Callable[[], object], on_change: Callable[[PeriodKind], object]) -> None:
        self.on_back, self.on_change = on_back, on_change
        self.box: ui.column | None = None
        self.toggle: ui.toggle | None = None
        self.data: Dashboard | None = None
        self.syncing = False  # 開き直しでトグルの値を書き換えるあいだは、変更を通知しない

    def build(self) -> None:
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
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props("flat").mark(
                    "dashboard-back"
                )
            self.cards()
        box.set_visibility(False)

    def on_toggle(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing:
            self.on_change(PeriodKind(event.value))

    def show(self, data: Dashboard, kind: PeriodKind) -> None:
        self.data = data
        if self.toggle is not None and self.toggle.value != kind.value:
            self.syncing = True
            try:
                self.toggle.value = kind.value
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
            self.progress_card(data)
            self.load_card(data)
            self.hours_card(data)
            self.due_card(data)

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
            ui.label("予定超過").classes("text-subtitle2")
            if not progress.overdue:
                ui.label("なし").classes("text-grey").mark("dashboard-overdue-none")
            for index, row in enumerate(progress.overdue):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.label(moment_text(row.limit)).classes("text-negative")
                    ui.label(row.name).classes("col ellipsis").mark(f"dashboard-overdue-name-{index}")
                    ui.label(row.assignee or "").classes("text-caption")

    def load_card(self, data: Dashboard) -> None:
        with card("人ごとの負荷", "dashboard-load"):
            if not data.loads:
                empty_message("dashboard-empty-load")
                return
            scale = max(1.0, *(stats.peak for stats in data.loads.values()))
            for name, stats in data.loads.items():
                over = stats.overload_days > 0
                with ui.column().classes("w-full gap-1"):
                    ui.label(name)
                    ui.label(
                        f"平均 {stats.average * 100:.0f}% / 最大 {stats.peak * 100:.0f}% / 超過 {stats.overload_days} 日"
                    ).classes("text-caption" + (" text-negative" if over else "")).mark(f"dashboard-load-{name}")
                    bar(stats.average / scale, OVER_COLOR if over else LOAD_COLOR, tick=stats.peak / scale)

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
