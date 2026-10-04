"""ガントチャートの描画(NiceGUI要素とCSS)。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime

from nicegui import Client, context, ui

from projectapp.calendar import DayKind, day_kind
from projectapp.filtering import TaskFilter, matches
from projectapp.models import DEFAULT_COLOR, Project, Section, Task, is_hex_color
from projectapp.timeline import (
    Band,
    Column,
    Overload,
    Scale,
    bar_span,
    build_columns,
    clip_overloads,
    deadline_position,
    effective_end,
    interval_span,
    is_overdue,
    month_bands,
    overallocations,
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
DEADLINE_MARKER_HALF_PX = 6  # 「◆」の幅の半分。締切の位置が目印の中心に来るようにずらす
DEADLINE_COLOR = "#f57c00"  # 赤は予定超過の背景と競合するので使わない
OVERLOAD_STRIPES = (  # 割り当て合計が100%を超える期間の縞。タスクの色に依存しないよう白と黒の半透明を重ねる
    "repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 4px, rgba(0,0,0,0.35) 4px 8px)"
)
MIN_BAR_PX = 4  # 幅0や終了が開始より前のタスクも、見える細い棒で出す
OVERDUE_COLOR = "rgba(239, 83, 80, 0.18)"  # 予定超過のタスク行の背景
GRID_BORDER = "1px solid rgba(128, 128, 128, 0.3)"  # 格子線。両テーマで見える半透明の灰色
ADD_ROW_HEIGHT_PX = 24  # 追加行は通常の行より細くする
ROW_STYLE = f"height: {ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
ADD_ROW_STYLE = f"height: {ADD_ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
ALL_ASSIGNEES = ""  # 担当者の選択で「すべて」を表す値。メンバー名は空にできない


@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[int], object]
    add_top_task: Callable[[], object]
    edit_task: Callable[[int | None, int], object]  # セクション番号(Noneはセクションなし), タスク番号


class GanttChart:
    def __init__(
        self,
        project: Project,
        holidays: dict[date, str],
        actions: GanttActions,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.actions = actions
        self.now = now
        self.overloads: list[Overload] = []
        self.scale = Scale.DAY
        self.task_filter = TaskFilter()
        self.search_input: ui.input | None = None
        self.assignee_select: ui.select | None = None
        self.client: Client | None = None

    def set_project(self, project: Project) -> None:
        """条件は保つ。担当者がメンバーからいなくなったときだけ、担当者の指定を外す。"""
        self.project = project
        names = {member.name for member in project.members}
        if self.task_filter.assignee not in (None, *names):
            self.task_filter = replace(self.task_filter, assignee=None)
        self.sync_assignee_select()
        self.render.refresh()

    def set_filter(self, task_filter: TaskFilter) -> None:
        if task_filter == self.task_filter:
            return
        self.task_filter = task_filter
        self.render.refresh()
        self.scroll_to_top()

    def reset_filter(self) -> None:
        """条件を空に戻し、入力欄と選択にも反映する。別のプロジェクトを開いたときに使う。"""
        self.task_filter = TaskFilter()
        if self.search_input is not None:
            self.search_input.set_value("")
        if self.assignee_select is not None:
            self.assignee_select.set_value(ALL_ASSIGNEES)
        self.render.refresh()
        self.scroll_to_top()

    def assignee_options(self) -> dict[str, str]:
        options = {ALL_ASSIGNEES: "すべての担当者"}
        options.update({member.name: member.name for member in self.project.members})
        return options

    def sync_assignee_select(self) -> None:
        if self.assignee_select is not None:
            value = self.task_filter.assignee or ALL_ASSIGNEES
            self.assignee_select.set_options(self.assignee_options(), value=value)

    def scroll_to_top(self) -> None:
        if self.client is not None:
            self.client.run_javascript("window.scrollTo({top: 0})")

    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.holidays = holidays
        self.render.refresh()

    def set_scale(self, scale: Scale) -> None:
        self.scale = scale
        self.render.refresh()

    def build(self) -> None:
        self.client = context.client
        with ui.row().classes("w-full items-center gap-4"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).mark("scale-toggle")
            ui.button("セクション追加", icon="add", on_click=self.actions.add_section).props(
                "flat"
            ).mark("add-section")
            self.search_input = (
                ui.input(
                    placeholder="タスク名で検索",
                    value=self.task_filter.query,
                    on_change=lambda e: self.set_filter(
                        replace(self.task_filter, query=e.value or "")
                    ),
                )
                .props("clearable dense outlined debounce=300")
                .classes("w-64")
                .mark("search-input")
            )
            self.assignee_select = (
                ui.select(
                    self.assignee_options(),
                    value=self.task_filter.assignee or ALL_ASSIGNEES,
                    on_change=lambda e: self.set_filter(
                        replace(
                            self.task_filter,
                            assignee=None if e.value == ALL_ASSIGNEES else e.value,
                        )
                    ),
                )
                .props("dense outlined")
                .classes("w-48")
                .mark("assignee-filter")
            )
        self.render()

    @ui.refreshable_method
    def render(self) -> None:
        columns = build_columns(self.project, self.scale, self.holidays)
        self.overloads = overallocations(self.project, self.holidays)
        width = COLUMN_WIDTH_PX[self.scale]
        total = NAME_WIDTH_PX + width * len(columns)
        with ui.element("div").classes("w-full").style("overflow-x: auto"):
            with ui.element("div").style(f"position: relative; width: {total}px"):
                top = BAND_HEIGHT_PX * (1 if self.scale is Scale.MONTH else 2)
                self.gridlines(columns, width, top)
                if self.scale is Scale.DAY:
                    self.stripes(columns, width, top)
                self.header(columns, width)
                self.no_match_message()
                for ti, task in enumerate(self.project.tasks):
                    if matches(task, self.task_filter):
                        self.task_row(None, ti, task, columns, width)
                self.top_add_row()
                for si, section in enumerate(self.project.sections):
                    self.section_rows(si, section, columns, width)

    def no_match_message(self) -> None:
        """絞り込み中に1件も一致しないとき(タスクが1つもないときは出さない)。"""
        tasks = self.project.all_tasks()
        if not (self.task_filter.active and tasks):
            return
        if any(matches(task, self.task_filter) for task in tasks):
            return
        ui.label("条件に一致するタスクがありません").classes("text-caption").style(
            "position: relative; padding: 8px 16px"
        ).mark("no-match")

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
        if self.task_filter.active and not any(
            matches(task, self.task_filter) for task in section.tasks
        ):
            return
        with ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE):
            ui.label(section.name).classes("text-subtitle2")
            ui.button(
                icon="add", on_click=lambda si=si: self.actions.add_task(si)
            ).props("flat dense round size=sm").tooltip("タスク追加").mark(f"add-task-{si}")
        for ti, task in enumerate(section.tasks):
            if matches(task, self.task_filter):
                self.task_row(si, ti, task, columns, width)

    def task_row(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        key = "top" if si is None else si
        style = ROW_STYLE
        if is_overdue(task, self.project, self.holidays, self.now()):
            style += f"; background: {OVERDUE_COLOR}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            ui.label(task.name).classes("ellipsis cursor-pointer").style(
                f"width: {NAME_WIDTH_PX}px; padding-left: 16px"
            ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                f"task-{key}-{ti}"
            )
            end = effective_end(task, self.project, self.holidays)
            span = bar_span(task.planned_start, end, columns)
            if span is not None:
                left, length = span
                bar_width = max(length * width, MIN_BAR_PX)
                with ui.element("div").style(
                    f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                    f" width: {bar_width:.1f}px; top: 6px;"
                    f" height: {ROW_HEIGHT_PX - 12}px;"
                    f" background: {task.color if is_hex_color(task.color) else DEFAULT_COLOR};"
                    " border-radius: 4px; cursor: pointer; overflow: hidden"
                ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                    f"bar-{key}-{ti}"
                ):
                    self.overload_stripes(key, ti, task, left, bar_width, columns, width)
            self.deadline_marker(si, ti, task, columns, width)

    def overload_stripes(
        self,
        key: int | str,
        ti: int,
        task: Task,
        bar_left: float,
        bar_width: float,
        columns: list[Column],
        width: int,
    ) -> None:
        """棒の内側に、割り当て合計が100%を超える期間の縞を重ねる。棒の外にははみ出さない。"""
        clipped = clip_overloads(task, self.project, self.holidays, self.overloads)
        for n, overload in enumerate(clipped):
            start, length = interval_span(overload.start, overload.end, columns)
            left_px = max((start - bar_left) * width, 0.0)
            width_px = min(length * width, bar_width - left_px)
            if width_px <= 0:
                continue
            ui.element("div").style(
                f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px;"
                f" top: 0; bottom: 0; background: {OVERLOAD_STRIPES}; pointer-events: none"
            ).mark(f"overload-{key}-{ti}-{n}")
        if clipped:
            peak = round(max(o.total for o in clipped) * 100)
            first, last = clipped[0], clipped[-1]
            ui.tooltip(
                f"{first.member} の割り当てが最大{peak}%"
                f"({first.start:%Y-%m-%d}〜{last.end:%Y-%m-%d})"
            )

    def deadline_marker(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """締切がある行に、締切の位置へ「◆」を出す。表示範囲の外なら出さない。"""
        if task.deadline is None:
            return
        position = deadline_position(task.deadline, columns)
        if position is None:
            return
        key = "top" if si is None else si
        left = NAME_WIDTH_PX + position * width - DEADLINE_MARKER_HALF_PX
        ui.label("◆").style(
            f"position: absolute; left: {left:.1f}px; top: 4px; line-height: 1;"
            f" color: {DEADLINE_COLOR}; cursor: pointer"
        ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).tooltip(
            f"締切 {task.deadline:%Y-%m-%d %H:%M}"
        ).mark(f"deadline-{key}-{ti}")
