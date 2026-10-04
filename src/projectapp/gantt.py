"""ガントチャートの描画(NiceGUI要素とCSS)。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime

from nicegui import Client, context, ui
from nicegui.events import ValueChangeEventArguments

from projectapp import arrange
from projectapp.arrange import Position
from projectapp.calendar import DayKind, day_kind
from projectapp.filtering import TaskFilter, matches
from projectapp.gantt_drag import CHART_DRAG_CSS, CHART_DRAG_JS
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
PLANNED_OPACITY = 0.4  # 実績を重ねるため、予定の棒は半透明にする(背景の色だけ。縞は薄くしない)
BAR_TOP_PX = 6
BAR_HEIGHT_PX = ROW_HEIGHT_PX - 12
ACTUAL_HEIGHT_PX = BAR_HEIGHT_PX // 2  # 実績の棒は、予定の棒の下半分
ACTUAL_TOP_PX = BAR_TOP_PX + BAR_HEIGHT_PX - ACTUAL_HEIGHT_PX
OVERDUE_COLOR = "rgba(239, 83, 80, 0.18)"  # 予定超過のタスク行の背景
GRID_BORDER = "1px solid rgba(128, 128, 128, 0.3)"  # 格子線。両テーマで見える半透明の灰色
ADD_ROW_HEIGHT_PX = 24  # 追加行は通常の行より細くする
ROW_STYLE = f"height: {ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
ADD_ROW_STYLE = f"height: {ADD_ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
# IME の変換確定の Enter は無視する。Safari 系は確定時に isComposing が偽でも keyCode が 229 になる
SEARCH_ENTER_JS = "(e) => { if (!e.isComposing && e.keyCode !== 229) emit(e.target.value); }"
SCROLLBAR_ROOM_PX = 16  # 横スクロールバーの分の余白。WebKit は高さ auto にバーの厚みを含めない
# チャートの枠は縦横ともここでスクロールする。高さの上限は、画面の高さから、上のヘッダー
# (タイトル・ファイル選択・ボタン・ツールバー)と、右下のヘルプのボタンの分を引いた値
# (どちらも固定の見積もり。実機で合わせる)
CHART_TOP_OFFSET_PX = 190
FAB_ZONE_PX = 100  # ヘルプのボタン: 下から18px + 高さ56px + 余白
CHART_MAX_HEIGHT = f"calc(100vh - {CHART_TOP_OFFSET_PX + FAB_ZONE_PX}px)"
# 固定する要素の重なり。見出し > タスク名の列 > 棒・縞・格子線。見出しの中では左端の空白が帯より手前
STICKY_Z_SPACER, STICKY_Z_NAME, STICKY_Z_HEADER = 1, 2, 3
# 固定した要素の下を棒や縞が通るので、不透明な背景が要る(ページの背景色に合わせる)
STICKY_CSS = """
.gantt-sticky { background-color: #fff; }
body.body--dark .gantt-sticky { background-color: var(--q-dark-page, #121212); }
"""
# 絞り込みの変更時に、チャートの枠とページの両方を先頭へ戻す
SCROLL_TO_TOP_JS = (
    "document.querySelector('[data-chart-scroll]')?.scrollTo({top: 0});"
    " window.scrollTo({top: 0})"
)
ALL_ASSIGNEES = ""  # 担当者の選択で「すべて」を表す値。メンバー名は空にできない


def planned_background(color: str) -> str:
    """予定の棒の背景。要素の opacity ではなく背景だけを半透明にし、中の縞は不透明のまま残す。"""
    return f"color-mix(in srgb, {color} {PLANNED_OPACITY * 100:g}%, transparent)"


def sticky_left(z_index: int) -> str:
    """横スクロールで左に残す要素のスタイル。"""
    return f"position: sticky; left: 0px; z-index: {z_index}"


@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[int], object]
    add_top_task: Callable[[], object]
    edit_task: Callable[[int | None, int], object]  # セクション番号(Noneはセクションなし), タスク番号
    move_task: Callable[[Position, Position, bool], object]  # 元, 挿入先, コピーか
    shift_task: Callable[[int | None, int, int], object]  # セクション番号, タスク番号, 日数


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

    def commit_query(self, query: str | None) -> None:
        self.set_filter(replace(self.task_filter, query=(query or "").strip()))

    def on_search_changed(self, e: ValueChangeEventArguments) -> None:
        """入力中は反映しない(IME の変換中を避ける)。空になったときだけ、すぐ条件を外す。"""
        if not e.value:
            self.commit_query("")

    def handle_move(self, args: object) -> None:
        """行のドロップを受ける。絞り込み中と、不正な値は無視する。"""
        if self.task_filter.active:
            return
        parsed = arrange.parse_move(args)
        if parsed is not None:
            self.actions.move_task(*parsed)

    def handle_shift(self, args: object) -> None:
        """バーの横移動を受ける。日次スケール以外と、不正な値は無視する。"""
        if self.scale is not Scale.DAY:
            return
        parsed = arrange.parse_shift(args)
        if parsed is not None:
            (section, index), days = parsed
            self.actions.shift_task(section, index, days)

    def drag_props(self, kind: str, key: int | str, **extra: object) -> str:
        """ドロップ先の `data-*` 属性。絞り込み中は空(ドロップできない)。"""
        if self.task_filter.active:
            return ""
        parts = [f"data-drop={kind}", f"data-si={key}"]
        parts += [f"data-{name}={value}" for name, value in extra.items()]
        return " ".join(parts)

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
            self.client.run_javascript(SCROLL_TO_TOP_JS)

    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.holidays = holidays
        self.render.refresh()

    def set_scale(self, scale: Scale) -> None:
        self.scale = scale
        self.render.refresh()

    def build(self) -> None:
        self.client = context.client
        ui.add_css(CHART_DRAG_CSS)
        ui.add_css(STICKY_CSS)
        ui.add_head_html(f"<script>{CHART_DRAG_JS}</script>")
        ui.on("chart_move", lambda e: self.handle_move(e.args))
        ui.on("chart_shift", lambda e: self.handle_shift(e.args))
        with ui.row().classes("w-full items-center no-wrap gap-4").mark("chart-toolbar"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).classes("shrink-0").mark("scale-toggle")
            ui.button("セクション追加", icon="add", on_click=self.actions.add_section).props(
                "flat"
            ).classes("shrink-0").mark("add-section")
            self.search_input = (
                ui.input(
                    placeholder="タスク名で検索(Enterで確定)",
                    value=self.task_filter.query,
                    on_change=self.on_search_changed,
                )
                .props("clearable dense outlined")
                .style("flex: 1 1 8rem; min-width: 6rem; max-width: 16rem")
                .on(
                    "keydown.enter",
                    lambda e: self.commit_query(e.args),
                    js_handler=SEARCH_ENTER_JS,
                )
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
                .style("flex: 1 1 8rem; min-width: 7rem; max-width: 12rem")
                .mark("assignee-filter")
            )
        self.render()

    @ui.refreshable_method
    def render(self) -> None:
        columns = build_columns(self.project, self.scale, self.holidays)
        self.overloads = overallocations(self.project, self.holidays)
        width = COLUMN_WIDTH_PX[self.scale]
        total = NAME_WIDTH_PX + width * len(columns)
        scroll_style = (
            f"overflow: auto; max-height: {CHART_MAX_HEIGHT};"
            f" padding-bottom: {SCROLLBAR_ROOM_PX}px"
        )
        scroll = ui.element("div").classes("w-full").style(scroll_style)
        with scroll.props("data-chart-scroll").mark("chart-scroll"):
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
        row = ui.row().classes("items-center no-wrap gap-0").style(ADD_ROW_STYLE)
        row.props(self.drag_props("top-end", "top", count=len(self.project.tasks)))
        row.mark("top-end")
        with row:
            cell = ui.row().classes("items-center justify-end no-wrap gantt-sticky")
            cell.style(
                f"width: {NAME_WIDTH_PX}px; padding-right: 8px; align-self: stretch;"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
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
        header_style = f"position: sticky; top: 0px; z-index: {STICKY_Z_HEADER}"
        with ui.column().classes("gap-0 gantt-sticky").style(header_style).mark("chart-header"):
            self.band_row(year_bands(columns), width, "year-band")
            if self.scale is not Scale.MONTH:
                self.band_row(month_bands(columns), width, "month-band")
            self.label_row(columns, width)

    def header_spacer(self, marker: str) -> None:
        """見出しの左端の空白。縦にも横にも固定された見出しの中で、横スクロールでも左に残る。"""
        spacer = ui.element("div").classes("gantt-sticky")
        spacer.style(
            f"width: {NAME_WIDTH_PX}px; align-self: stretch; {sticky_left(STICKY_Z_SPACER)}"
        )
        spacer.mark(marker)

    def band_row(self, bands: list[Band], width: int, marker: str) -> None:
        style = f"height: {BAND_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            self.header_spacer(f"{marker}-spacer")
            for band in bands:
                ui.label(band.label).classes("text-caption text-center").style(
                    f"width: {band.count * width}px; border-left: {GRID_BORDER};"
                    " overflow: hidden; white-space: nowrap"
                ).mark(marker)

    def label_row(self, columns: list[Column], width: int) -> None:
        height = HEADER_HEIGHT_PX if self.scale is Scale.DAY else ROW_HEIGHT_PX
        style = f"height: {height}px; position: relative; border-bottom: {GRID_BORDER}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            self.header_spacer("label-row-spacer")
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
        header = ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE)
        header.props(self.drag_props("section", si, count=len(section.tasks)))
        header.mark(f"section-{si}")
        with header:
            name = ui.row().classes("items-center no-wrap gap-2 gantt-sticky")
            name.style(  # 名前の列にちょうど収める(狭いと縞や格子線が見え、広いと棒を隠す)
                f"width: {NAME_WIDTH_PX}px; overflow: hidden; align-self: stretch;"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
            with name.mark(f"section-name-{si}"):
                label = ui.label(section.name).classes("text-subtitle2 ellipsis")
                label.style("min-width: 0; padding-left: 4px")  # 長い名前は縮めて、ボタンを残す
                label.tooltip(section.name).mark(f"section-label-{si}")
                ui.button(
                    icon="add", on_click=lambda si=si: self.actions.add_task(si)
                ).props("flat dense round size=sm").classes("shrink-0").tooltip(
                    "タスク追加"
                ).mark(f"add-task-{si}")
        for ti, task in enumerate(section.tasks):
            if matches(task, self.task_filter):
                self.task_row(si, ti, task, columns, width)

    def task_row(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        key = "top" if si is None else si
        style = ROW_STYLE
        overdue = is_overdue(task, self.project, self.holidays, self.now())
        if overdue:
            style += f"; background: {OVERDUE_COLOR}"
        row = ui.row().classes("items-center no-wrap gap-0").style(style)
        row.props(self.drag_props("row", key, ti=ti)).mark(f"row-{key}-{ti}")
        with row:
            label = ui.label(task.name).classes("ellipsis cursor-pointer gantt-sticky")
            label_style = (
                f"width: {NAME_WIDTH_PX}px; padding-left: 16px; align-self: stretch;"
                f" line-height: {ROW_HEIGHT_PX - 1}px; {sticky_left(STICKY_Z_NAME)}"
            )
            if overdue:  # 不透明な背景の上に、行と同じ赤みを重ねる
                label_style += (
                    f"; background-image: linear-gradient({OVERDUE_COLOR}, {OVERDUE_COLOR})"
                )
            label.style(label_style)
            label.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
            label.mark(f"task-{key}-{ti}")
            if not self.task_filter.active:
                label.props(f"draggable=true data-drag-handle data-si={key} data-ti={ti}")
            end = effective_end(task, self.project, self.holidays)
            span = bar_span(task.planned_start, end, columns)
            if span is not None:
                left, length = span
                bar_width = max(length * width, MIN_BAR_PX)
                draggable = self.scale is Scale.DAY
                cursor = "grab" if draggable else "pointer"
                bar = ui.element("div").style(
                    f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                    f" width: {bar_width:.1f}px; top: {BAR_TOP_PX}px;"
                    f" height: {BAR_HEIGHT_PX}px;"
                    f" background: {planned_background(task.color if is_hex_color(task.color) else DEFAULT_COLOR)};"
                    f" border-radius: 4px; cursor: {cursor}; overflow: hidden;"
                    " user-select: none; touch-action: none"
                )
                bar.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
                bar.mark(f"bar-{key}-{ti}")
                if draggable:
                    least = arrange.min_shift_days(task, self.project.base_date)
                    bar.props(
                        f"data-bar data-si={key} data-ti={ti} data-day-width={width}"
                        f" data-min-days={least}"
                    )
                with bar:
                    self.overload_stripes(key, ti, task, left, bar_width, columns, width)
            self.actual_bars(si, ti, task, columns, width)
            self.deadline_marker(si, ti, task, columns, width)

    def actual_bars(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """実績の棒。予定の棒の下半分に、不透明で重ねる。進行中は現在時刻まで。ドラッグはできない。"""
        key = "top" if si is None else si
        color = task.color if is_hex_color(task.color) else DEFAULT_COLOR
        for n, actual in enumerate(task.actuals):
            finish = actual.end if actual.end is not None else self.now()
            left, length = interval_span(actual.start, finish, columns)
            bar = ui.element("div").style(
                f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                f" width: {max(length * width, MIN_BAR_PX):.1f}px;"
                f" top: {ACTUAL_TOP_PX}px; height: {ACTUAL_HEIGHT_PX}px;"
                f" background: {color}; border-radius: 3px; cursor: pointer;"
                " user-select: none"
            )
            bar.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
            bar.mark(f"actual-{key}-{ti}-{n}")

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
