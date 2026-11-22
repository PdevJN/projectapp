"""アサイン専用の全画面ダイアログ(要望 168 段階 1)。

対象タスク 1 件の試算のコピーを持ち、`GanttChart`の埋め込みモードで読み取り専用に描く。確定で
`on_confirm(trial)`を呼び、キャンセルでは何も反映しない。変更があるとき(`is_dirty`)だけ、捨てる確認を出す。
段階 2 以降で、左にメンバーのアイコン列、下に負荷のヒストグラムを足す。
"""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import date, datetime

from nicegui import ui

from projectapp import clock
from projectapp.assign_trial import (
    AssignTrial,
    hidden_ids,
    is_dirty,
    start_trial,
    trial_project,
)
from projectapp.config import DEFAULT_NAME_WIDTH_PX
from projectapp.forms import disposable
from projectapp.gantt import GanttActions, GanttChart, ViewOptions
from projectapp.models import Project, Task
from projectapp.timeline import DEFAULT_FISCAL_START_MONTH, Scale

ASSIGN_SCALES = (Scale.DAY, Scale.WEEK, Scale.MONTH)


def read_only_actions() -> GanttActions:
    """読み取り専用の画面なので、チャートからの操作は何もしない(必須のコールバックだけ空で渡す)。"""
    return GanttActions(
        add_section=lambda: None,
        add_task=lambda path: None,
        add_top_task=lambda: None,
        edit_task=lambda path, ti: None,
        move_task=lambda src, dst, copy: None,
        shift_task=lambda path, ti, days: None,
        set_name_width=lambda width: None,
    )


class AssignScreen:
    def __init__(
        self,
        project: Project,
        task: Task,
        holidays: dict[date, str],
        on_confirm: Callable[[AssignTrial], object],
        *,
        now: Callable[[], datetime] = clock.now,
        name_width: int = DEFAULT_NAME_WIDTH_PX,
        fiscal_start_month: int = DEFAULT_FISCAL_START_MONTH,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.on_confirm = on_confirm
        self.now = now
        self.name_width = name_width
        self.fiscal_start_month = fiscal_start_month
        self.trial = start_trial(task)
        self.chart: GanttChart | None = None
        self.dialog: ui.dialog | None = None

    def open(self, parent: ui.element | None = None) -> None:
        """`parent`は、更新(refreshable)で消されない外側の要素。なければ呼び出しの文脈の下に作る。"""
        with parent if parent is not None else nullcontext():
            self.build()

    def build(self) -> None:
        with (
            disposable(ui.dialog()).props("persistent maximized") as dialog,
            ui.card().classes("w-full h-full no-wrap").mark("assign-screen"),
        ):
            self.dialog = dialog
            dialog.on("escape-key", lambda _e: self.cancel())
            with ui.row().classes("w-full items-center no-wrap gap-4"):
                ui.label(self.trial.task.name).classes("text-h6 col ellipsis").mark(
                    "assign-task-title"
                )
                ui.toggle(
                    {scale: scale.value for scale in ASSIGN_SCALES},
                    value=Scale.DAY,
                    on_change=lambda e: self.set_scale(Scale(e.value)),
                ).mark("assign-scale")
                ui.button("キャンセル", on_click=self.cancel).props("flat").mark(
                    "assign-cancel"
                )
                ui.button("確定", on_click=self.confirm).props("color=primary").mark(
                    "assign-confirm"
                )
            with (
                ui.element("div").classes("w-full").style("flex: 1 1 0; min-height: 0")
            ):
                self.chart = GanttChart(
                    trial_project(self.project, self.trial),
                    self.holidays,
                    read_only_actions(),
                    now=self.now,
                    name_width=self.name_width,
                    fiscal_start_month=self.fiscal_start_month,
                )
                self.chart.build_embedded(
                    ViewOptions(
                        read_only=True,
                        excluded=hidden_ids(self.project, self.trial),
                        hide_excluded=True,
                    )
                )
        dialog.open()

    def set_scale(self, scale: Scale) -> None:
        if self.chart is not None:
            self.chart.set_scale(scale)

    def confirm(self) -> None:
        self.close()
        self.on_confirm(self.trial)

    def cancel(self) -> None:
        if not is_dirty(self.trial):
            self.close()
            return
        with disposable(ui.dialog()) as ask, ui.card().mark("assign-discard"):
            ui.label("変更を捨てますか?")
            with ui.row():
                ui.button("戻る", on_click=ask.close).props("flat").mark(
                    "assign-discard-no"
                )
                ui.button("捨てる", on_click=lambda: (ask.close(), self.close())).props(
                    "color=negative"
                ).mark("assign-discard-yes")
        ask.open()

    def close(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
