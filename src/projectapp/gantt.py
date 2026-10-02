"""ガントチャートの描画(NiceGUI要素とCSS)。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from nicegui import ui

from projectapp.calendar import DayKind, day_kind
from projectapp.models import Project, Section, Task
from projectapp.timeline import (
    Band,
    Column,
    Scale,
    bar_span,
    build_columns,
    month_bands,
    year_bands,
)

NAME_WIDTH_PX = 200
ROW_HEIGHT_PX = 32
COLUMN_WIDTH_PX = {Scale.DAY: 40, Scale.WEEK: 56, Scale.MONTH: 80}
KIND_COLORS = {
    DayKind.SATURDAY: "rgba(66, 165, 245, 0.18)",
    DayKind.SUNDAY: "rgba(244, 143, 177, 0.22)",
    DayKind.HOLIDAY: "rgba(129, 199, 132, 0.28)",
}
BAND_HEIGHT_PX = 22  # 年・月の帯の高さ
HEADER_HEIGHT_PX = 44  # 日次の日付と(曜日)の2段
WEEKDAYS = "月火水木金土日"
GRID_BORDER = "1px solid rgba(128, 128, 128, 0.3)"  # 格子線。両テーマで見える半透明の灰色
ADD_ROW_HEIGHT_PX = 24  # 追加行は通常の行より細くする
ROW_STYLE = f"height: {ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
ADD_ROW_STYLE = f"height: {ADD_ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"


@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[int], object]
    add_top_task: Callable[[], object]
    edit_task: Callable[[int | None, int], object]  # セクション番号(Noneはセクションなし), タスク番号


class GanttChart:
    def __init__(
        self, project: Project, holidays: dict[date, str], actions: GanttActions
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.actions = actions
        self.scale = Scale.DAY

    def set_project(self, project: Project) -> None:
        self.project = project
        self.render.refresh()

    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.holidays = holidays
        self.render.refresh()

    def set_scale(self, scale: Scale) -> None:
        self.scale = scale
        self.render.refresh()

    def build(self) -> None:
        with ui.row().classes("w-full items-center gap-4"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).mark("scale-toggle")
            ui.button("セクション追加", icon="add", on_click=self.actions.add_section).props(
                "flat"
            ).mark("add-section")
        self.render()

    @ui.refreshable_method
    def render(self) -> None:
        columns = build_columns(self.project, self.scale)
        width = COLUMN_WIDTH_PX[self.scale]
        total = NAME_WIDTH_PX + width * len(columns)
        with ui.element("div").classes("w-full").style("overflow-x: auto"):
            with ui.element("div").style(f"position: relative; width: {total}px"):
                top = BAND_HEIGHT_PX * (1 if self.scale is Scale.MONTH else 2)
                self.gridlines(columns, width, top)
                if self.scale is Scale.DAY:
                    self.stripes(columns, width, top)
                self.header(columns, width)
                for ti, task in enumerate(self.project.tasks):
                    self.task_row(None, ti, task, columns, width)
                self.top_add_row()
                for si, section in enumerate(self.project.sections):
                    self.section_rows(si, section, columns, width)

    def top_add_row(self) -> None:
        """セクションなしのタスクの末尾に置く追加行。名前の列の右端にボタンを置く。"""
        with ui.row().classes("items-center no-wrap gap-0").style(ADD_ROW_STYLE):
            cell = ui.row().classes("items-center justify-end no-wrap")
            cell.style(f"width: {NAME_WIDTH_PX}px; padding-right: 8px")
            with cell:
                ui.button("タスク追加", icon="add", on_click=self.actions.add_top_task).props(
                    "flat dense size=sm"
                ).mark("add-task-top")

    def gridlines(self, columns: list[Column], width: int, top: int) -> None:
        """列の境界の縦線。全スケールで引く。年・月の帯の下から始める。"""
        cells = f'<div style="width:{width}px;border-left:{GRID_BORDER}"></div>' * len(columns)
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: {NAME_WIDTH_PX}px;"
            " pointer-events: none"
        ).mark("gridlines")

    def stripes(self, columns: list[Column], width: int, top: int) -> None:
        """日次スケールの土日祝の背景。内容は定数と日付のみで利用者の入力を含まない。"""
        cells = "".join(
            f'<div style="width:{width}px;background:'
            f'{KIND_COLORS.get(day_kind(column.start, self.holidays), "transparent")}">'
            "</div>"
            for column in columns
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: {NAME_WIDTH_PX}px;"
            " pointer-events: none"
        ).mark("stripes")

    def header(self, columns: list[Column], width: int) -> None:
        """年・月の帯(結合セル)と、日・曜日の見出し。月次スケールに月の帯はない。"""
        with ui.column().classes("gap-0"):
            self.band_row(year_bands(columns), width, "year-band")
            if self.scale is not Scale.MONTH:
                self.band_row(month_bands(columns), width, "month-band")
            self.label_row(columns, width)

    def band_row(self, bands: list[Band], width: int, marker: str) -> None:
        style = f"height: {BAND_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            ui.element("div").style(f"width: {NAME_WIDTH_PX}px")
            for band in bands:
                ui.label(band.label).classes("text-caption text-center").style(
                    f"width: {band.count * width}px; border-left: {GRID_BORDER};"
                    " overflow: hidden; white-space: nowrap"
                ).mark(marker)

    def label_row(self, columns: list[Column], width: int) -> None:
        height = HEADER_HEIGHT_PX if self.scale is Scale.DAY else ROW_HEIGHT_PX
        style = f"height: {height}px; position: relative; border-bottom: {GRID_BORDER}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            ui.element("div").style(f"width: {NAME_WIDTH_PX}px")
            for column in columns:
                with ui.column().classes("items-center gap-0").style(f"width: {width}px"):
                    ui.label(column.label).classes("text-caption").mark(
                        f"col-{column.start.isoformat()}"
                    )
                    if self.scale is Scale.DAY:
                        weekday = f"（{WEEKDAYS[column.start.weekday()]}）"
                        ui.label(weekday).classes("text-caption").mark(
                            f"weekday-{column.start.isoformat()}"
                        )

    def section_rows(
        self, si: int, section: Section, columns: list[Column], width: int
    ) -> None:
        with ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE):
            ui.label(section.name).classes("text-subtitle2")
            ui.button(
                icon="add", on_click=lambda si=si: self.actions.add_task(si)
            ).props("flat dense round size=sm").tooltip("タスク追加").mark(f"add-task-{si}")
        for ti, task in enumerate(section.tasks):
            self.task_row(si, ti, task, columns, width)

    def task_row(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        key = "top" if si is None else si
        with ui.row().classes("items-center no-wrap gap-0").style(ROW_STYLE):
            ui.label(task.name).classes("ellipsis cursor-pointer").style(
                f"width: {NAME_WIDTH_PX}px; padding-left: 16px"
            ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                f"task-{key}-{ti}"
            )
            span = bar_span(task, columns)
            if span is None:
                return
            left, length = span
            ui.element("div").style(
                f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                f" width: {length * width:.1f}px; top: 6px;"
                f" height: {ROW_HEIGHT_PX - 12}px; background: {task.color};"
                " border-radius: 4px; cursor: pointer"
            ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                f"bar-{key}-{ti}"
            )
