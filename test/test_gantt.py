import asyncio
from datetime import date, datetime

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import DayKind
from projectapp.filtering import TaskFilter
from projectapp.gantt_drag import CHART_DRAG_CSS
from projectapp.gantt import (
    COLUMN_WIDTH_PX,
    ViewOptions,
    PRIORITY_BACKGROUND_VAR,
    PRIORITY_BACKGROUNDS,
    PRIORITY_CLASSES,
    PRIORITY_CSS,
    PRIORITY_DARK_BACKGROUNDS,
    CHART_MAX_HEIGHT,
    CHART_TOP_OFFSET_PX,
    REFRESH_SCROLLBARS_JS,
    FAB_ZONE_PX,
    SCROLL_RESET_JS,
    SCROLL_TO_LEFT_JS,
    SCROLL_TO_TOP_JS,
    STICKY_CSS,
    STICKY_Z_HEADER,
    STICKY_Z_NAME,
    STICKY_Z_SPACER,
    ACTUAL_HEIGHT_PX,
    ACTUAL_TOP_PX,
    PLANNED_OPACITY,
    planned_background,
    fill_percent,
    PROGRESS_STATE_COLORS,
    PROGRESS_STATE_MARKS,
    STATUS_CLASSES,
    STATUS_COLOR_VAR,
    STATUS_COLORS,
    STATUS_CSS,
    STATUS_DARK_COLORS,
    PROGRESS_CSS,
    PROGRESS_STATE_CLASSES,
    PROGRESS_STATE_DARK_COLORS,
    DEADLINE_MARKER_HALF_PX,
    GRID_BORDER,
    NAME_WIDTH_PX,
    KIND_COLORS,
    MIN_BAR_PX,
    SCROLLBAR_ROOM_PX,
    SEARCH_ENTER_JS,
    OVERDUE_COLOR,
    GanttActions,
    GanttChart,
)
from projectapp.timeline import build_columns
from projectapp.models import DEFAULT_COLOR, Actual, Member, Priority, Project, Section, Status, Task
from projectapp.timeline import ProgressState, Scale

BASE = date(2026, 10, 5)  # 月曜


class Recorder:
    """操作のコールバックを記録する。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[object, ...]]] = []
        self.actions = GanttActions(
            add_section=lambda: self.events.append(("add_section", ())),
            add_task=lambda si: self.events.append(("add_task", (si,))),
            add_top_task=lambda: self.events.append(("add_top_task", ())),
            edit_task=lambda si, ti: self.events.append(("edit_task", (si, ti))),
            move_task=lambda src, dst, copy: self.events.append(("move_task", (src, dst, copy))),
            shift_task=lambda si, ti, days: self.events.append(("shift_task", (si, ti, days))),
        )


def sample_project() -> Project:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        color="#ff0000",
    )
    return Project("demo", base_date=BASE, sections=[Section("開発", [task, Task("未設定")])])


def mount(
    project: Project,
    holidays: dict[date, str] | None = None,
    now: datetime = datetime(2026, 10, 1),
) -> Recorder:
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        GanttChart(project, holidays or {}, recorder.actions, now=lambda: now).build()

    return recorder


async def test_renders_sections_tasks_and_bars(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    await user.should_see("開発")
    await user.should_see("設計")
    await user.should_see("未設定")
    await user.should_see(marker="bar-0-0")
    await user.should_not_see(marker="bar-0-1")


async def test_bar_geometry_and_color(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["left"] == "220.0px"  # 200 + 0.5 * 40
    assert bar._style["width"] == "80.0px"  # 2.0 * 40
    assert bar._style["background"] == planned_background(STATUS_COLOR_VAR)


async def test_day_scale_colors_weekends_and_holidays(user: User) -> None:
    mount(sample_project(), {date(2026, 10, 7): "テスト祝日"})
    await user.open("/")
    html = user.find(marker="stripes").elements.pop().content
    assert html.count(KIND_COLORS[DayKind.HOLIDAY]) == 1
    assert html.count(KIND_COLORS[DayKind.SATURDAY]) == 6
    assert html.count(KIND_COLORS[DayKind.SUNDAY]) == 6


async def test_holiday_wins_over_sunday(user: User) -> None:
    mount(sample_project(), {date(2026, 10, 11): "日曜の祝日"})
    await user.open("/")
    html = user.find(marker="stripes").elements.pop().content
    assert html.count(KIND_COLORS[DayKind.HOLIDAY]) == 1
    assert html.count(KIND_COLORS[DayKind.SUNDAY]) == 5


async def test_week_scale_has_no_stripes_and_scales_bars(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.WEEK)
    await user.should_not_see(marker="stripes")
    await user.should_see("5~")
    assert user.find(marker="col-2026-10-05").elements.pop().text == "5~"
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["left"] == "204.0px"  # 200 + 0.5 / 7 * 56
    assert bar._style["width"] == "16.0px"  # 2 / 7 * 56


async def test_month_scale_labels(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.MONTH)
    await user.should_see(marker="col-2026-10-01")
    assert user.find(marker="col-2026-10-01").elements.pop().text == "10月"


async def test_clicks_call_the_actions(user: User) -> None:
    recorder = mount(sample_project())
    await user.open("/")
    user.find(marker="bar-0-0").click()
    user.find(marker="task-0-1").click()
    user.find(marker="add-task-0").click()
    user.find(marker="add-section").click()
    assert recorder.events == [
        ("edit_task", (0, 0)),
        ("edit_task", (0, 1)),
        ("add_task", (0,)),
        ("add_section", ()),
    ]


async def test_empty_section_and_html_like_names_are_shown_literally(user: User) -> None:
    project = Project("p", base_date=BASE, sections=[Section("<b>空</b>")])
    mount(project)
    await user.open("/")
    await user.should_see("<b>空</b>")
    await user.should_see(marker="add-task-0")


async def test_day_header_shows_weekday_in_parentheses_under_the_date(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert user.find(marker="col-2026-10-05").elements.pop().text == "5"
    for day, weekday in (("2026-10-05", "（月）"), ("2026-10-10", "（土）"), ("2026-10-11", "（日）")):
        assert user.find(marker=f"weekday-{day}").elements.pop().text == weekday


async def test_week_and_month_headers_have_no_weekday(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    toggle = user.find(kind=ui.toggle).elements.pop()
    toggle.set_value(Scale.WEEK)
    await user.should_not_see(marker="weekday-2026-10-05")
    toggle.set_value(Scale.MONTH)
    await user.should_not_see(marker="weekday-2026-10-05")
    await user.should_see(marker="col-2026-10-01")
    assert user.find(marker="col-2026-10-01").elements.pop().text == "10月"



def top_project() -> Project:
    task = Task(
        "単独",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        color="#00ff00",
    )
    return Project("demo", base_date=BASE, tasks=[task, Task("未設定の単独")])


async def test_top_level_tasks_render_without_any_section(user: User) -> None:
    mount(top_project())
    await user.open("/")
    await user.should_see("単独")
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="bar-top-1")
    await user.should_not_see(marker="add-task-0")
    bar = user.find(marker="bar-top-0").elements.pop()
    assert bar._style["left"] == "220.0px"
    assert bar._style["background"] == planned_background(STATUS_COLOR_VAR)


async def test_top_level_task_clicks_call_edit_with_no_section(user: User) -> None:
    recorder = mount(top_project())
    await user.open("/")
    user.find(marker="bar-top-0").click()
    user.find(marker="task-top-1").click()
    assert recorder.events == [("edit_task", (None, 0)), ("edit_task", (None, 1))]


async def test_top_level_tasks_come_before_sections(user: User) -> None:
    project = top_project()
    project.sections.append(Section("開発"))
    mount(project)
    await user.open("/")
    labels = sorted(user.find(kind=ui.label).elements, key=lambda e: e.id)  # 作成順
    order = [e.text for e in labels if e.text in ("単独", "開発")]
    assert order == ["単独", "開発"]


async def test_vertical_grid_lines_in_every_scale(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    toggle = user.find(kind=ui.toggle).elements.pop()
    for scale, columns in ((Scale.DAY, 42), (Scale.WEEK, 26), (Scale.MONTH, 12)):
        toggle.set_value(scale)
        for _ in range(60):  # 再描画を待つ
            counts = [e.content.count("border-left") for e in user.find(marker="gridlines").elements]
            if counts == [columns]:
                break
            await asyncio.sleep(0.05)
        assert counts == [columns]


async def test_horizontal_grid_lines_under_every_row(user: User) -> None:
    mount(sample_project())
    await user.open("/")

    def row_of(marker: str | None = None, content: str | None = None):  # noqa: ANN202
        label = user.find(marker=marker, content=content).elements.pop()
        return label.parent_slot.parent

    assert row_of(marker="task-0-0")._style["border-bottom"] == GRID_BORDER
    assert user.find(marker="section-0").elements.pop()._style["border-bottom"] == GRID_BORDER
    header = row_of(marker="col-2026-10-05").parent_slot.parent
    assert header._style["border-bottom"] == GRID_BORDER


def band_widths(user: User, marker: str) -> dict[str, str]:
    return {
        label.text: band._style["width"]
        for band in user.find(marker=marker).elements
        for label in user.find(marker=f"{marker}-label").elements
        if label.parent_slot.parent is band
    }


async def test_band_labels_stay_visible_when_scrolled_horizontally(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    for marker in ("year-band-label", "month-band-label"):
        labels = user.find(marker=marker).elements
        assert labels, marker
        for label in labels:
            assert label._style["position"] == "sticky", marker
            assert label._style["left"] == f"{NAME_WIDTH_PX}px", marker


async def test_day_scale_has_year_and_month_bands_merging_cells(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert band_widths(user, "year-band") == {"2026年": "1680px"}  # 42列 * 40px
    assert band_widths(user, "month-band") == {"10月": "1080px", "11月": "600px"}


async def test_week_scale_has_month_band_and_month_scale_does_not(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    toggle = user.find(kind=ui.toggle).elements.pop()
    toggle.set_value(Scale.WEEK)
    await user.should_see("5~")
    assert user.find(marker="month-band").elements
    toggle.set_value(Scale.MONTH)
    await user.should_see(marker="col-2026-10-01")
    await user.should_not_see(marker="month-band")
    assert user.find(marker="year-band").elements


async def test_grid_layers_start_below_the_bands(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert user.find(marker="gridlines").elements.pop()._style["top"] == "44px"
    assert user.find(marker="stripes").elements.pop()._style["top"] == "44px"
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.MONTH)
    await user.should_see(marker="col-2026-10-01")
    assert user.find(marker="gridlines").elements.pop()._style["top"] == "22px"


async def test_no_toolbar_add_task_button(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    await user.should_see(marker="add-section")
    await user.should_not_see(marker="add-top-task")  # ツールバーにはない
    await user.should_not_see(marker="refresh-holidays")  # 祝日更新はヘッダー側


async def test_add_row_is_right_aligned_in_the_name_column(user: User) -> None:
    recorder = mount(Project("p", base_date=BASE))
    await user.open("/")
    await user.should_see(marker="add-task-top")
    cell = user.find(marker="add-task-top").elements.pop().parent_slot.parent
    assert "justify-end" in cell.classes
    assert cell._style["width"] == "200px"
    user.find(marker="add-task-top").click()
    assert recorder.events == [("add_top_task", ())]


async def test_add_row_is_shown_with_only_empty_sections(user: User) -> None:
    mount(Project("p", base_date=BASE, sections=[Section("空")]))
    await user.open("/")
    await user.should_see(marker="add-task-top")
    await user.should_see(marker="add-task-0")


async def test_add_row_stays_when_tasks_exist(user: User) -> None:
    recorder = mount(sample_project())
    await user.open("/")
    await user.should_see(marker="task-0-0")
    user.find(marker="add-task-top").click()
    assert recorder.events == [("add_top_task", ())]


async def test_add_row_comes_after_top_level_tasks_and_before_sections(user: User) -> None:
    project = top_project()
    project.sections.append(Section("開発"))
    mount(project)
    await user.open("/")

    def element_id(marker: str) -> int:
        return user.find(marker=marker).elements.pop().id

    assert element_id("task-top-1") < element_id("add-task-top") < element_id("add-task-0")


def row_background(user: User, marker: str) -> str | None:
    row = user.find(marker=marker).elements.pop().parent_slot.parent
    return row._style.get("background")


async def test_overdue_task_row_is_red_and_others_are_not(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-0-0") == OVERDUE_COLOR  # 終了10/7 12:00を過ぎた
    assert row_background(user, "task-0-1") is None  # 終了なし


async def test_task_not_yet_overdue_is_not_red(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 6))
    await user.open("/")
    assert row_background(user, "task-0-0") is None


async def test_done_task_is_not_red(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].status = Status.DONE
    mount(project, now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-0-0") is None


async def test_overdue_keeps_the_bar_color(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert user.find(marker="bar-0-0").elements.pop()._style["background"] == planned_background(STATUS_COLOR_VAR)


async def test_overdue_applies_to_top_level_tasks(user: User) -> None:
    mount(top_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-top-0") == OVERDUE_COLOR



async def test_a_task_that_ends_before_it_starts_still_shows_a_thin_bar(user: User) -> None:
    project = sample_project()
    task = project.sections[0].tasks[0]
    task.planned_start, task.planned_end = task.planned_end, task.planned_start
    mount(project)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["width"] == f"{MIN_BAR_PX:.1f}px"


async def test_a_zero_length_task_still_shows_a_thin_bar(user: User) -> None:
    project = sample_project()
    task = project.sections[0].tasks[0]
    task.planned_end = task.planned_start
    mount(project)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["width"] == f"{MIN_BAR_PX:.1f}px"


async def test_the_deadline_marker_is_placed_at_the_deadline(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].deadline = datetime(2026, 10, 8, 12)  # BASE は 10/5
    mount(project)
    await user.open("/")
    marker = user.find(marker="deadline-0-0").elements.pop()
    assert marker._style["left"] == f"{200 + 3.5 * 40 - DEADLINE_MARKER_HALF_PX:.1f}px"


async def test_a_task_without_a_start_still_shows_its_deadline_marker(user: User) -> None:
    project = Project(
        "demo", base_date=BASE, tasks=[Task("締切のみ", deadline=datetime(2026, 10, 8, 12))]
    )
    mount(project)
    await user.open("/")
    await user.should_see(marker="deadline-top-0")
    await user.should_not_see(marker="bar-top-0")


async def test_a_deadline_outside_the_range_has_no_marker(user: User) -> None:
    project = Project("demo", base_date=BASE, tasks=[Task("遠い", deadline=datetime(2030, 1, 1))])
    mount(project)
    await user.open("/")
    await user.should_see("遠い")
    await user.should_not_see(marker="deadline-top-0")


async def test_clicking_the_deadline_marker_edits_the_task(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].deadline = datetime(2026, 10, 8, 12)
    recorder = mount(project)
    await user.open("/")
    user.find(marker="deadline-0-0").click()
    assert recorder.events == [("edit_task", (0, 0))]


async def test_a_task_with_a_start_and_a_deadline_draws_the_bar_up_to_the_deadline(
    user: User,
) -> None:
    project = Project(
        "demo",
        base_date=BASE,
        tasks=[
            Task(
                "締切まで",
                planned_start=datetime(2026, 10, 5, 12),
                deadline=datetime(2026, 10, 7, 12),
            )
        ],
    )
    mount(project)
    await user.open("/")
    bar = user.find(marker="bar-top-0").elements.pop()
    assert bar._style["width"] == "80.0px"  # 完了予定は空なので、締切(2日後)まで


def overloaded_project() -> Project:
    a = Task(
        "A",
        planned_start=datetime(2026, 10, 5),
        planned_end=datetime(2026, 10, 9),
        assignee="田中",
        allocation=0.6,
    )
    b = Task(
        "B",
        planned_start=datetime(2026, 10, 7),
        planned_end=datetime(2026, 10, 12),
        assignee="田中",
        allocation=0.6,
    )
    return Project("demo", base_date=BASE, members=[Member("田中")], tasks=[a, b])


async def test_stripes_cover_only_the_overloaded_part_of_each_bar(user: User) -> None:
    mount(overloaded_project())
    await user.open("/")
    a = user.find(marker="overload-top-0-0").elements.pop()
    b = user.find(marker="overload-top-1-0").elements.pop()
    # 超過は 10/7〜10/9。Aの棒は 10/5 から、Bの棒は 10/7 から始まる
    assert (a._style["left"], a._style["width"]) == ("80.0px", "80.0px")
    assert (b._style["left"], b._style["width"]) == ("0.0px", "80.0px")


async def test_stripes_do_not_block_clicks_on_the_bar(user: User) -> None:
    recorder = mount(overloaded_project())
    await user.open("/")
    assert user.find(marker="overload-top-0-0").elements.pop()._style["pointer-events"] == "none"
    user.find(marker="bar-top-0").click()
    assert recorder.events == [("edit_task", (None, 0))]


async def test_the_bar_tooltip_names_the_member_and_the_peak(user: User) -> None:
    mount(overloaded_project())
    await user.open("/")
    bar = user.find(marker="bar-top-0").elements.pop()
    tooltips = [c for c in bar.default_slot.children if isinstance(c, ui.tooltip)]
    assert len(tooltips) == 1
    assert "田中 の割り当てが最大120%" in tooltips[0].text
    assert "2026-10-07" in tooltips[0].text


async def test_no_stripes_without_an_overload(user: User) -> None:
    project = overloaded_project()
    project.tasks[1].allocation = 0.4  # 合計ちょうど100%
    mount(project)
    await user.open("/")
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="overload-top-0-0")
    await user.should_not_see(marker="overload-top-1-0")


async def test_tasks_that_are_done_get_no_stripes(user: User) -> None:
    project = overloaded_project()
    project.tasks[1].status = Status.DONE
    mount(project)
    await user.open("/")
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="overload-top-0-0")
    await user.should_not_see(marker="overload-top-1-0")


async def test_stripes_stay_inside_a_thin_bar(user: User) -> None:
    def thin(name: str) -> Task:
        return Task(
            name,
            planned_start=datetime(2026, 10, 5),
            planned_end=datetime(2026, 10, 5, 0, 1),
            assignee="田中",
            allocation=0.6,
        )

    mount(Project("demo", base_date=BASE, members=[Member("田中")], tasks=[thin("A"), thin("B")]))
    await user.open("/")
    stripe = user.find(marker="overload-top-0-0").elements.pop()
    bar = user.find(marker="bar-top-0").elements.pop()
    bar_width = float(bar._style["width"].removesuffix("px"))
    left = float(stripe._style["left"].removesuffix("px"))
    width = float(stripe._style["width"].removesuffix("px"))
    assert 0.0 <= left and left + width <= bar_width + 1e-6


def mount_chart(
    project: Project, holidays: dict[date, str] | None = None
) -> tuple[list[GanttChart], Recorder]:
    charts: list[GanttChart] = []
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(
            project, holidays or {}, recorder.actions, now=lambda: datetime(2026, 10, 1)
        )
        charts.append(chart)
        chart.build()

    return charts, recorder


def filter_project() -> Project:
    def task(name: str, assignee: str) -> Task:
        return Task(
            name,
            planned_start=datetime(2026, 10, 5, 12),
            planned_end=datetime(2026, 10, 7, 12),
            assignee=assignee,
        )

    return Project(
        "demo",
        base_date=BASE,
        members=[Member("田中"), Member("鈴木")],
        tasks=[task("調査", "田中")],
        sections=[
            Section("開発", [task("設計", "田中"), task("実装", "鈴木")]),
            Section("試験", [task("結合試験", "鈴木")]),
        ],
    )


async def test_a_query_hides_rows_that_do_not_match(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="実"))
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")
    await user.should_not_see(marker="task-0-0")
    await user.should_not_see(marker="task-1-0")


async def test_an_empty_filter_shows_every_row(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="実"))
    charts[0].set_filter(TaskFilter())
    for marker in ("task-top-0", "task-0-0", "task-0-1", "task-1-0"):
        await user.should_see(marker=marker)


async def test_original_indexes_are_kept_for_clicks_and_markers(user: User) -> None:
    charts, recorder = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(assignee="鈴木"))
    await user.should_see(marker="bar-0-1")
    await user.should_see(marker="bar-1-0")
    await user.should_not_see(marker="bar-0-0")
    user.find(marker="task-0-1").click()
    user.find(marker="bar-1-0").click()
    assert recorder.events == [("edit_task", (0, 1)), ("edit_task", (1, 0))]


async def test_query_and_assignee_are_combined(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="計", assignee="田中"))
    await user.should_see(marker="task-0-0")
    await user.should_not_see(marker="task-top-0")
    await user.should_not_see(marker="task-0-1")
    await user.should_not_see(marker="task-1-0")


async def test_a_section_without_a_match_is_hidden_with_its_add_button(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_see(marker="add-task-0")
    await user.should_not_see(marker="add-task-1")


async def test_an_empty_section_is_hidden_only_while_filtering(user: User) -> None:
    project = filter_project()
    project.sections.append(Section("空", []))
    charts, _ = mount_chart(project)
    await user.open("/")
    await user.should_see(marker="add-task-2")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="add-task-2")


async def test_the_top_add_row_stays_while_filtering(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="zzz"))
    await user.should_see(marker="add-task-top")


async def test_no_match_message_appears_only_when_nothing_matches(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    await user.should_not_see(marker="no-match")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="no-match")
    charts[0].set_filter(TaskFilter(query="zzz"))
    await user.should_see(marker="no-match")
    await user.should_see("条件に一致するタスクがありません")


async def test_no_match_message_is_not_shown_for_a_project_without_tasks(user: User) -> None:
    charts, _ = mount_chart(Project("空", base_date=BASE))
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="何か"))
    await user.should_not_see(marker="no-match")


async def test_stripes_do_not_change_while_filtering(user: User) -> None:
    charts, _ = mount_chart(overloaded_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="A"))
    a = user.find(marker="overload-top-0-0").elements.pop()
    assert (a._style["left"], a._style["width"]) == ("80.0px", "80.0px")
    await user.should_not_see(marker="bar-top-1")


async def test_the_filter_survives_a_scale_change(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="実"))
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.WEEK)
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-0-0")


async def test_set_project_keeps_the_filter_but_drops_a_vanished_assignee(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    chart = charts[0]
    chart.set_filter(TaskFilter(query="設", assignee="田中"))
    chart.set_project(filter_project())
    assert chart.task_filter == TaskFilter(query="設", assignee="田中")
    other = filter_project()
    other.members = [Member("鈴木")]
    chart.set_project(other)
    assert chart.task_filter == TaskFilter(query="設", assignee=None)


async def test_typing_in_the_search_input_does_not_filter_until_enter(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    await user.should_see(marker="search-input")
    user.find(marker="search-input").type("実")
    assert charts[0].task_filter == TaskFilter()
    await user.should_see(marker="task-top-0")


async def test_enter_in_the_search_input_filters_the_rows(user: User) -> None:
    mount_chart(filter_project())
    await user.open("/")
    user.find(marker="search-input").type("実").trigger("keydown.enter", args="実")
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")


async def test_enter_with_blank_text_means_no_condition(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="search-input").trigger("keydown.enter", args="\u3000 ")
    assert charts[0].task_filter == TaskFilter()
    await user.should_see(marker="task-top-0")


def test_the_enter_script_ignores_ime_composition() -> None:
    assert "isComposing" in SEARCH_ENTER_JS
    assert "229" in SEARCH_ENTER_JS
    assert "emit(e.target.value)" in SEARCH_ENTER_JS


async def test_clearing_the_search_input_shows_every_row_again(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="search-input").trigger("keydown.enter", args="実")
    await user.should_not_see(marker="task-top-0")
    box = user.find(marker="search-input").elements.pop()
    box.set_value(None)
    assert charts[0].task_filter == TaskFilter()
    await user.should_see(marker="task-top-0")


async def test_the_assignee_select_lists_the_members_and_filters(user: User) -> None:
    mount_chart(filter_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    assert select.options == {"": "すべての担当者", "田中": "田中", "鈴木": "鈴木"}
    assert select.value == ""
    select.set_value("鈴木")
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")
    select.set_value("")
    await user.should_see(marker="task-top-0")


async def test_set_project_updates_the_assignee_options_and_resets_a_vanished_choice(
    user: User,
) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value("田中")
    other = filter_project()
    other.members = [Member("鈴木"), Member("佐藤")]
    charts[0].set_project(other)
    assert select.options == {"": "すべての担当者", "鈴木": "鈴木", "佐藤": "佐藤"}
    assert select.value == ""
    assert charts[0].task_filter.assignee is None


async def test_set_project_keeps_a_chosen_assignee_that_still_exists(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value("鈴木")
    charts[0].set_project(filter_project())
    assert select.value == "鈴木"
    assert charts[0].task_filter.assignee == "鈴木"


async def test_reset_filter_clears_the_inputs_and_shows_every_row(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="search-input").elements.pop().set_value("実")
    charts[0].set_filter(TaskFilter(query="実"))
    user.find(marker="assignee-filter").elements.pop().set_value("鈴木")
    charts[0].reset_filter()
    assert charts[0].task_filter == TaskFilter()
    assert user.find(marker="search-input").elements.pop().value == ""
    assert user.find(marker="assignee-filter").elements.pop().value == ""
    await user.should_see(marker="task-top-0")
    await user.should_see(marker="task-1-0")


async def test_changing_the_filter_scrolls_to_the_top_but_set_project_does_not(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    calls: list[str] = []
    monkeypatch.setattr(charts[0], "scroll_to_top", lambda: calls.append("scroll"))
    charts[0].set_filter(TaskFilter(query="実"))
    charts[0].set_filter(TaskFilter(query="実"))  # 同じ条件では動かない
    assert calls == ["scroll"]
    charts[0].set_project(filter_project())
    assert calls == ["scroll"]
    charts[0].reset_filter()
    assert calls == ["scroll", "scroll"]


async def test_the_toolbar_never_wraps_and_the_filters_shrink(user: User) -> None:
    mount_chart(filter_project())
    await user.open("/")
    toolbar = user.find(marker="chart-toolbar").elements.pop()
    assert "no-wrap" in toolbar.classes
    for marker in ("search-input", "assignee-filter"):
        style = user.find(marker=marker).elements.pop()._style
        assert style["flex"].startswith("1 1")
        assert style["min-width"]


async def test_the_chart_scroll_box_has_room_for_the_horizontal_scrollbar(user: User) -> None:
    mount_chart(filter_project())
    await user.open("/")
    style = user.find(marker="chart-scroll").elements.pop()._style
    assert style["overflow"] == "auto"  # 縦横とも枠の中でスクロールする(見出しの固定の基準になる)
    assert style["max-height"] == CHART_MAX_HEIGHT
    assert style["padding-bottom"] == f"{SCROLLBAR_ROOM_PX}px"  # 横のスクロールバーが最下行に重ならない


def actual_project(*actuals: Actual) -> Project:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        color="#ff0000",
        actuals=list(actuals),
    )
    return Project("demo", base_date=BASE, sections=[Section("開発", [task])])


async def test_planned_bar_is_semi_transparent_without_fading_its_children(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    # 棒全体の opacity は使わない(中の割り当て超過の縞まで薄くなるため)。背景の色だけを半透明にする
    assert "opacity" not in bar._style
    assert bar._style["background"] == planned_background(STATUS_COLOR_VAR)
    assert bar._style["background"].startswith("color-mix(")
    assert f"{PLANNED_OPACITY * 100:g}%" in bar._style["background"]


async def test_actual_bar_is_drawn_in_the_lower_half_with_the_task_color(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 8, 12))))
    await user.open("/")
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["left"] == "260.0px"  # 200 + 1.5 * 40
    assert bar._style["width"] == "80.0px"  # 2.0 * 40
    assert bar._style["background"] == STATUS_COLOR_VAR
    assert bar._style["top"] == f"{ACTUAL_TOP_PX}px"
    assert bar._style["height"] == f"{ACTUAL_HEIGHT_PX}px"
    assert "opacity" not in bar._style


async def test_no_actual_bar_without_actuals(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    await user.should_not_see(marker="actual-0-0-0")


async def test_in_progress_actual_bar_extends_to_now(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 6, 12), None)), now=datetime(2026, 10, 8, 12))
    await user.open("/")
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["width"] == "80.0px"


async def test_in_progress_actual_starting_in_the_future_is_a_minimum_width_bar(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 9, 12), None)), now=datetime(2026, 10, 6))
    await user.open("/")
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["width"] == f"{MIN_BAR_PX:.1f}px"


async def test_actual_bar_is_drawn_without_a_planned_bar(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 7, 12))])
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see(marker="actual-0-0-0")
    await user.should_not_see(marker="bar-0-0")


async def test_actual_bar_shows_the_progress(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 8, 12), 40)))
    await user.open("/")
    label = user.find(marker="actual-progress-0-0-0").elements.pop()
    assert label.text == "40%"
    assert label._style["pointer-events"] == "none"


async def test_actual_bar_shows_zero_percent(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 8, 12), 0)))
    await user.open("/")
    assert user.find(marker="actual-progress-0-0-0").elements.pop().text == "0%"


async def test_actual_bar_without_progress_shows_no_text(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 8, 12))))
    await user.open("/")
    await user.should_see(marker="actual-0-0-0")
    await user.should_not_see(marker="actual-progress-0-0-0")


async def test_each_actual_shows_its_own_progress(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 7, 12), 30),
            Actual(datetime(2026, 10, 8, 12), None, 60),
        )
    )
    await user.open("/")
    assert user.find(marker="actual-progress-0-0-0").elements.pop().text == "30%"
    assert user.find(marker="actual-progress-0-0-1").elements.pop().text == "60%"


async def test_actual_bar_clips_its_progress_text(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 6, 13), 40)))
    await user.open("/")
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["overflow"] == "hidden"


def progress_project(progress: int | None, **overrides: object) -> Project:
    actuals = [Actual(datetime(2026, 10, 5, 12), None, progress)] if progress is not None else []
    values: dict[str, object] = {
        "planned_start": datetime(2026, 10, 5, 12),
        "planned_end": datetime(2026, 10, 7, 12),
        "color": "#ff0000",
        "status": Status.RUNNING,
        "actuals": actuals,
    }
    values.update(overrides)
    task = Task("設計", **values)  # type: ignore[arg-type]
    return Project("demo", base_date=BASE, sections=[Section("開発", [task])])


def test_fill_percent() -> None:
    assert fill_percent(Task("t", actuals=[Actual(datetime(2026, 10, 5, 9), None, 40)])) == 40
    assert fill_percent(Task("t", actuals=[Actual(datetime(2026, 10, 5, 9), None, 0)])) == 0
    assert fill_percent(Task("t")) is None
    assert fill_percent(Task("t", status=Status.DONE)) == 100
    done = Task("t", status=Status.DONE, actuals=[Actual(datetime(2026, 10, 5, 9), None, 80)])
    assert fill_percent(done) == 80


async def test_planned_bar_is_filled_by_the_progress(user: User) -> None:
    mount(progress_project(40))
    await user.open("/")
    fill = user.find(marker="progress-fill-0-0").elements.pop()
    assert fill._style["width"] == "40%"
    assert fill._style["left"] == "0"
    assert fill._style["background"] == STATUS_COLOR_VAR
    assert fill._style["pointer-events"] == "none"


async def test_progress_zero_makes_a_zero_width_fill(user: User) -> None:
    mount(progress_project(0))
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "0%"


async def test_no_fill_without_progress(user: User) -> None:
    mount(progress_project(None))
    await user.open("/")
    await user.should_see(marker="bar-0-0")
    await user.should_not_see(marker="progress-fill-0-0")


async def test_done_without_progress_is_filled_completely(user: User) -> None:
    mount(progress_project(None, status=Status.DONE))
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "100%"


async def test_no_fill_without_a_planned_bar(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 6, 12), None, 40)])
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see(marker="actual-0-0-0")
    await user.should_not_see(marker="progress-fill-0-0")


async def test_fill_is_inside_the_bar_and_below_the_overload_stripes(user: User) -> None:
    mount(progress_project(40))
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    markers = [m for child in bar.default_slot.children for m in child._markers]
    assert markers[0].startswith("progress-fill-")  # 縞(overload-)より先に置く = 縞が手前


MID = datetime(2026, 10, 6, 12)  # 予定の中間(進んでいるはずの割合は50%)


def test_state_colors_and_marks_cover_the_visible_states() -> None:
    assert PROGRESS_STATE_COLORS == {
        ProgressState.DELAYED: "#b26a00",
        ProgressState.AHEAD: "#00897b",
        ProgressState.DONE: "#757575",
        ProgressState.LATE_DONE: "#8e24aa",
    }
    assert PROGRESS_STATE_MARKS == {
        ProgressState.DELAYED: "▼",
        ProgressState.AHEAD: "▲",
        ProgressState.DONE: "✓",
        ProgressState.LATE_DONE: "✓!",
    }


@pytest.mark.parametrize(
    ("progress", "state"),
    [(10, ProgressState.DELAYED), (90, ProgressState.AHEAD)],
)
async def test_bar_outline_and_mark_follow_the_state(
    user: User, progress: int, state: ProgressState
) -> None:
    mount(progress_project(progress), now=MID)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["outline"] == "2px solid var(--pstate)"
    assert bar._style["outline-offset"] == "-2px"
    assert PROGRESS_STATE_CLASSES[state] in bar.classes
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert mark.text == PROGRESS_STATE_MARKS[state]
    assert mark._style["color"] == "var(--pstate)"
    assert PROGRESS_STATE_CLASSES[state] in mark.classes
    assert mark._style["left"] == "304.0px"  # 200 + 0.5 * 40 + 2.0 * 40 + 4


async def test_normal_state_has_no_outline_and_no_mark(user: User) -> None:
    mount(progress_project(50), now=MID)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert "outline" not in bar._style
    await user.should_not_see(marker="progress-state-0-0")


async def test_no_state_without_progress_has_no_outline_and_no_mark(user: User) -> None:
    mount(progress_project(None), now=MID)
    await user.open("/")
    assert "outline" not in user.find(marker="bar-0-0").elements.pop()._style
    await user.should_not_see(marker="progress-state-0-0")


async def test_done_state_is_marked(user: User) -> None:
    in_time = Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 7, 10), 100)
    mount(progress_project(100, status=Status.DONE, actuals=[in_time]), now=datetime(2026, 10, 20))
    await user.open("/")
    assert user.find(marker="progress-state-0-0").elements.pop().text == "✓"


async def test_late_done_state_is_marked(user: User) -> None:
    late = Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 8, 12), 100)
    mount(progress_project(100, status=Status.DONE, actuals=[late]), now=datetime(2026, 10, 20))
    await user.open("/")
    assert user.find(marker="progress-state-0-0").elements.pop().text == "✓!"
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["outline"] == "2px solid var(--pstate)"
    assert PROGRESS_STATE_CLASSES[ProgressState.LATE_DONE] in bar.classes
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert PROGRESS_STATE_CLASSES[ProgressState.LATE_DONE] in mark.classes


def tooltip_texts(user: User, target: ui.element) -> list[str]:
    """要素に付いたツールチップの文字。tooltip() は作成時の親の子として作り、target で対象を指す。"""
    return [
        t.text
        for t in user.find(kind=ui.tooltip).elements
        if t.props.get("target") == f"#{target.html_id}"
    ]


async def test_state_mark_tooltips(user: User) -> None:
    mount(progress_project(10), now=MID)
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert tooltip_texts(user, mark) == ["遅延(進捗 10% / 予定 50%)"]


async def test_done_mark_tooltip_has_no_progress_part(user: User) -> None:
    mount(progress_project(None, status=Status.DONE), now=datetime(2026, 10, 20))
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert tooltip_texts(user, mark) == ["完了"]


async def test_no_outline_or_mark_without_a_planned_bar(user: User) -> None:
    task = Task("設計", status=Status.DONE, actuals=[Actual(datetime(2026, 10, 6, 12), None, 40)])
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see(marker="actual-0-0-0")
    await user.should_not_see(marker="progress-state-0-0")


async def test_overdue_background_and_state_outline_coexist(user: User) -> None:
    late = Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 8, 12), 100)
    mount(progress_project(100, status=Status.DONE, actuals=[late]), now=datetime(2026, 10, 20))
    await user.open("/")
    row = user.find(marker="row-0-0").elements.pop()
    assert OVERDUE_COLOR in row._style["background"]


def finished_project(end: datetime) -> Project:
    return progress_project(
        100, status=Status.DONE, actuals=[Actual(datetime(2026, 10, 5, 12), end, 100)]
    )


@pytest.mark.parametrize(
    "end", [datetime(2026, 10, 7, 10), datetime(2026, 10, 8, 12)], ids=["done", "late-done"]
)
async def test_finished_task_has_a_gray_actual_bar_and_a_struck_through_name(
    user: User, end: datetime
) -> None:
    mount(finished_project(end), now=datetime(2026, 10, 20))
    await user.open("/")
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["background"] == STATUS_COLOR_VAR
    assert "status-done" in bar.classes
    name = user.find(marker="task-name-0-0").elements.pop()
    assert name._style["text-decoration"] == "line-through"


async def test_running_task_keeps_its_color_and_name(user: User) -> None:
    mount(progress_project(50), now=MID)
    await user.open("/")
    assert user.find(marker="actual-0-0-0").elements.pop()._style["background"] == STATUS_COLOR_VAR
    assert "text-decoration" not in user.find(marker="task-name-0-0").elements.pop()._style


async def test_finished_task_without_a_planned_bar_is_also_grayed(user: User) -> None:
    task = Task(
        "設計",
        status=Status.DONE,
        color="#ff0000",
        actuals=[Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 7, 12), 100)],
    )
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["background"] == STATUS_COLOR_VAR
    assert "status-done" in bar.classes
    assert user.find(marker="task-name-0-0").elements.pop()._style["text-decoration"] == "line-through"


async def test_finished_task_keeps_the_planned_fill_and_the_overdue_background(user: User) -> None:
    mount(finished_project(datetime(2026, 10, 8, 12)), now=datetime(2026, 10, 20))
    await user.open("/")
    fill = user.find(marker="progress-fill-0-0").elements.pop()
    assert fill._style["background"] == STATUS_COLOR_VAR  # 予定の棒の塗りも状態の色
    assert OVERDUE_COLOR in user.find(marker="row-0-0").elements.pop()._style["background"]


async def test_late_done_mark_does_not_overlap_the_longer_actual_bar(user: User) -> None:
    mount(finished_project(datetime(2026, 10, 8, 12)), now=datetime(2026, 10, 20))
    await user.open("/")
    actual = user.find(marker="actual-0-0-0").elements.pop()
    actual_right = float(actual._style["left"][:-2]) + float(actual._style["width"][:-2])
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert actual_right == 340.0  # 200 + 3.5 * 40
    assert mark._style["left"] == "344.0px"  # 実績の棒の右端 + 4


async def test_mark_stays_next_to_the_planned_bar_when_the_actual_is_shorter(user: User) -> None:
    mount(finished_project(datetime(2026, 10, 7, 10)), now=datetime(2026, 10, 20))
    await user.open("/")
    assert user.find(marker="progress-state-0-0").elements.pop()._style["left"] == "304.0px"


async def test_delayed_mark_clears_an_in_progress_actual_bar_that_runs_past_the_plan(
    user: User,
) -> None:
    mount(progress_project(10), now=datetime(2026, 10, 9, 12))  # 進行中の実績が、予定の終了より先まで伸びる
    await user.open("/")
    actual = user.find(marker="actual-0-0-0").elements.pop()
    actual_right = float(actual._style["left"][:-2]) + float(actual._style["width"][:-2])
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert float(mark._style["left"][:-2]) >= actual_right + 4


async def test_mark_does_not_overlap_the_deadline_diamond(user: User) -> None:
    deadline = datetime(2026, 10, 7, 12)  # 完了予定と同じ。◆は x=300 を中心に 294〜306
    mount(progress_project(10, deadline=deadline), now=MID)
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert mark._style["left"] == "310.0px"  # ◆の右端 306 + 4
    assert user.find(marker="deadline-0-0").elements.pop()  # ◆は今のまま出る


async def test_mark_ignores_a_far_away_deadline(user: User) -> None:
    mount(progress_project(10, deadline=datetime(2026, 10, 20, 12)), now=MID)
    await user.open("/")
    assert user.find(marker="progress-state-0-0").elements.pop()._style["left"] == "304.0px"


def luminance(color: str) -> float:
    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(foreground: str, background: str) -> float:
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def over(overlay: tuple[int, int, int, float], base: str) -> str:
    """半透明の色を、不透明な背景に重ねた色(#rrggbb)。"""
    red, green, blue, alpha = overlay
    mixed = [
        round(alpha * c + (1 - alpha) * int(base[i : i + 2], 16))
        for c, i in zip((red, green, blue), (1, 3, 5))
    ]
    return "#" + "".join(f"{c:02x}" for c in mixed)


DARK_PAGE = "#121212"  # ダークテーマのページの背景(gantt.py の --q-dark-page の既定値)
OVERDUE_ON_DARK = over((239, 83, 80, 0.18), DARK_PAGE)  # 予定超過の行の背景(赤みが乗る)


@pytest.mark.parametrize("state", list(PROGRESS_STATE_COLORS))
def test_dark_state_colors_are_readable_on_the_dark_page(state: ProgressState) -> None:
    color = PROGRESS_STATE_DARK_COLORS[state]
    assert contrast(color, DARK_PAGE) >= 4.5
    assert contrast(color, OVERDUE_ON_DARK) >= 4.5  # 遅延完了の行は赤みの背景になる


@pytest.mark.parametrize("state", list(PROGRESS_STATE_COLORS))
def test_light_state_colors_are_readable_on_white(state: ProgressState) -> None:
    assert contrast(PROGRESS_STATE_COLORS[state], "#ffffff") >= 4.0


def test_dark_state_colors_cover_the_same_states_and_differ_from_light() -> None:
    assert PROGRESS_STATE_DARK_COLORS.keys() == PROGRESS_STATE_COLORS.keys()
    assert all(PROGRESS_STATE_DARK_COLORS[s] != PROGRESS_STATE_COLORS[s] for s in PROGRESS_STATE_COLORS)


@pytest.mark.parametrize("state", list(PROGRESS_STATE_COLORS))
def test_progress_css_defines_the_variable_for_both_themes(state: ProgressState) -> None:
    cls = PROGRESS_STATE_CLASSES[state]
    assert f".{cls} {{ --pstate: {PROGRESS_STATE_COLORS[state]}; }}" in PROGRESS_CSS
    dark = f"body.body--dark .{cls} {{ --pstate: {PROGRESS_STATE_DARK_COLORS[state]}; }}"
    assert dark in PROGRESS_CSS


async def test_progress_css_is_added_to_the_page(user: User) -> None:
    mount(progress_project(10), now=MID)
    response = await user.http_client.get("/")
    rules = PROGRESS_CSS.splitlines()
    assert len(rules) == 2 * len(PROGRESS_STATE_CLASSES)
    for rule in rules:  # ページでは add_css が改行を \\n に変えて埋め込むので、ルールごとに確かめる
        assert rule in response.text


async def test_clicking_an_actual_bar_edits_the_task(user: User) -> None:
    recorder = mount(actual_project(Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 8, 12))))
    await user.open("/")
    user.find(marker="actual-0-0-0").click()
    assert recorder.events == [("edit_task", (0, 0))]


async def test_actual_bar_follows_the_week_scale(user: User) -> None:
    mount(actual_project(Actual(datetime(2026, 10, 5, 0), datetime(2026, 10, 12, 0))))
    await user.open("/")
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.WEEK)
    await user.should_not_see(marker="stripes")  # 週次に切り替わった(再描画の完了を待つ)
    bar = user.find(marker="actual-0-0-0").elements.pop()
    assert bar._style["width"] == "56.0px"  # 1週 = 1列


def pinned(user: User, marker: str) -> object:
    return user.find(marker=marker).elements.pop()


async def test_task_name_is_pinned_to_the_left(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    label = pinned(user, "task-0-0")
    assert label._style["position"] == "sticky"
    assert label._style["left"] == "0px"
    assert label._style["z-index"] == str(STICKY_Z_NAME)
    assert label._style["align-self"] == "stretch"  # 行の高さいっぱいを不透明な背景で覆う
    assert "gantt-sticky" in label.classes


async def test_pinned_name_keeps_the_overdue_tint(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert OVERDUE_COLOR in pinned(user, "task-0-0")._style["background-image"]
    assert "background-image" not in pinned(user, "task-0-1")._style


async def test_header_is_pinned_to_the_top(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    header = pinned(user, "chart-header")
    assert header._style["position"] == "sticky"
    assert header._style["top"] == "0px"
    assert header._style["z-index"] == str(STICKY_Z_HEADER)
    assert "gantt-sticky" in header.classes
    assert STICKY_Z_HEADER > STICKY_Z_NAME  # 見出しは、スクロールしてくるタスク名の列より手前


async def test_header_left_spacers_are_pinned_to_the_left(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    for marker in ("year-band-spacer", "month-band-spacer", "label-row-spacer"):
        spacer = pinned(user, marker)
        assert spacer._style["position"] == "sticky", marker
        assert spacer._style["left"] == "0px", marker
        assert spacer._style["z-index"] == str(STICKY_Z_SPACER), marker
        assert "gantt-sticky" in spacer.classes, marker


async def test_section_name_is_pinned_to_the_left(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    name = pinned(user, "section-name-0")
    assert name._style["position"] == "sticky"
    assert name._style["left"] == "0px"
    assert name._style["z-index"] == str(STICKY_Z_NAME)
    assert "gantt-sticky" in name.classes
    # 名前の列(200px)の全体を覆い、それを越えない。狭いと縞や格子線が見え、広いと棒を隠す
    assert name._style["width"] == f"{NAME_WIDTH_PX}px"
    assert name._style["overflow"] == "hidden"
    assert pinned(user, "add-task-0").parent_slot.parent is name  # 追加ボタンも一緒に固定される


async def test_add_row_cell_is_pinned_to_the_left(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    cell = pinned(user, "add-task-top").parent_slot.parent
    assert cell._style["position"] == "sticky"
    assert cell._style["left"] == "0px"
    assert cell._style["z-index"] == str(STICKY_Z_NAME)
    assert "gantt-sticky" in cell.classes


async def test_chart_scroll_box_is_marked_for_scrolling_to_the_top(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert pinned(user, "chart-scroll").props.get("data-chart-scroll") is True


def test_scroll_to_top_resets_the_chart_box_and_the_page() -> None:
    assert "[data-chart-scroll]" in SCROLL_TO_TOP_JS
    assert "window.scrollTo" in SCROLL_TO_TOP_JS


def test_pinned_cells_have_an_opaque_background_for_both_themes() -> None:
    assert ".gantt-sticky" in STICKY_CSS
    assert "background-color: #fff" in STICKY_CSS
    assert "body.body--dark .gantt-sticky" in STICKY_CSS
    assert "--q-dark-page" in STICKY_CSS


def test_the_chart_scrollbars_follow_the_dark_theme() -> None:
    # 標準のスクロールバーがライト用の白いまま残らないように
    assert "body.body--dark [data-chart-scroll]" in STICKY_CSS
    assert "color-scheme: dark" in STICKY_CSS
    # 枠の余白(横スクロールバーの下)やトラックが、白いまま残らないように、暗い色を明示する
    assert "body.body--dark [data-chart-scroll] { color-scheme: dark; background-color:" in STICKY_CSS
    for part in ("::-webkit-scrollbar {", "::-webkit-scrollbar-track", "::-webkit-scrollbar-thumb", "::-webkit-scrollbar-corner"):
        assert f"body.body--dark [data-chart-scroll]{part}" in STICKY_CSS, part


def test_drop_marks_are_repeated_on_pinned_cells() -> None:
    # 不透明な背景が、行の「ここに入る」の線を左の列で隠さないように
    assert ".drop-before > .gantt-sticky" in CHART_DRAG_CSS
    assert ".drop-after > .gantt-sticky" in CHART_DRAG_CSS
    assert ".drop-into > .gantt-sticky" in CHART_DRAG_CSS


async def test_a_long_section_name_is_shortened_inside_the_name_column(user: User) -> None:
    project = sample_project()
    project.sections[0].name = "とても長いセクション名" * 10
    mount(project)
    await user.open("/")
    label = pinned(user, "section-label-0")
    assert "ellipsis" in label.classes
    assert label._style["min-width"] == "0"  # 縮められる(縮まないと追加ボタンが列の外へ出る)
    assert "shrink-0" in pinned(user, "add-task-0").classes  # 追加ボタンは常に見える
    assert pinned(user, "section-name-0")._style["width"] == f"{NAME_WIDTH_PX}px"


def test_the_chart_box_stops_above_the_help_button() -> None:
    # 右下のヘルプのボタン(下から18px + 高さ56px)に、枠の右下が重ならない
    assert FAB_ZONE_PX >= 18 + 56
    assert CHART_MAX_HEIGHT == f"calc(100vh - {CHART_TOP_OFFSET_PX + FAB_ZONE_PX}px)"


def test_refreshing_the_scrollbars_keeps_the_scroll_position() -> None:
    # WebKit は、親のクラス(body--dark)が実行中に変わっても、標準のスクロールバーを描き直さない。
    # overflow を一度切り替えて描き直させ、スクロール位置は戻す
    assert "[data-chart-scroll]" in REFRESH_SCROLLBARS_JS
    assert "style.overflow" in REFRESH_SCROLLBARS_JS
    assert "scrollTop" in REFRESH_SCROLLBARS_JS and "scrollLeft" in REFRESH_SCROLLBARS_JS
    assert "scrollTo" in REFRESH_SCROLLBARS_JS


def record_javascript(chart: GanttChart) -> list[str]:
    """チャートが画面へ送る JavaScript を記録する(実際には送らない)。"""
    sent: list[str] = []
    assert chart.client is not None
    chart.client.run_javascript = lambda code, **_: sent.append(code)  # type: ignore[method-assign]
    return sent


async def test_the_scroll_box_survives_a_redraw_so_the_scroll_position_is_kept(user: User) -> None:
    # 行の移動などで描き直しても、スクロールする枠は作り直さない(作り直すと位置が先頭に戻る)
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    before = user.find(marker="chart-scroll").elements.pop()
    charts[0].render.refresh()
    after = user.find(marker="chart-scroll").elements.pop()
    assert after is before
    assert not before.is_deleted
    await user.should_see(marker="bar-top-0")  # 中身は描き直されている


async def test_changing_the_scale_resets_only_the_horizontal_scroll(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].set_scale(Scale.WEEK)
    assert sent == [SCROLL_TO_LEFT_JS]


async def test_set_project_does_not_touch_the_scroll_position(user: User) -> None:
    # 行の移動・タスクの編集・削除など、すべての編集のあとの再描画に使われる
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].set_project(filter_project())
    assert sent == []


async def test_a_plain_redraw_does_not_touch_the_scroll_position(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].set_holidays({})
    assert sent == []


def test_scroll_scripts_target_the_chart_box() -> None:
    for code in (SCROLL_TO_LEFT_JS, SCROLL_RESET_JS):
        assert "[data-chart-scroll]" in code
    assert "left: 0" in SCROLL_TO_LEFT_JS and "top" not in SCROLL_TO_LEFT_JS
    assert "left: 0" in SCROLL_RESET_JS and "top: 0" in SCROLL_RESET_JS


def test_status_colors_cover_every_status_in_both_themes() -> None:
    assert set(STATUS_COLORS) == set(Status) == set(STATUS_DARK_COLORS) == set(STATUS_CLASSES)
    assert len(set(STATUS_COLORS.values())) == len(Status)
    for status, cls in STATUS_CLASSES.items():
        assert f".{cls} {{ --scolor: {STATUS_COLORS[status]}; }}" in STATUS_CSS
        assert f"body.body--dark .{cls} {{ --scolor: {STATUS_DARK_COLORS[status]}; }}" in STATUS_CSS


@pytest.mark.parametrize("status", list(Status))
async def test_bars_use_the_status_color_instead_of_the_task_color(
    user: User, status: Status
) -> None:
    task = Task(
        "設計",
        status=status,
        color="red; background: url(x)",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        actuals=[Actual(datetime(2026, 10, 6, 12), datetime(2026, 10, 7, 12), 50)],
    )
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    for marker in ("bar-0-0", "actual-0-0-0"):
        assert STATUS_CLASSES[status] in user.find(marker=marker).elements.pop().classes
    assert user.find(marker="actual-0-0-0").elements.pop()._style["background"] == STATUS_COLOR_VAR
    assert "url(x)" not in user.find(marker="bar-0-0").elements.pop()._style["background"]


async def test_a_dashed_line_joins_two_intervals(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
        )
    )
    await user.open("/")
    gap = user.find(marker="actual-gap-0-0-0").elements.pop()
    assert gap._style["left"] == "220.0px"  # 前の区間の終了 10/5 12:00 = 0.5日
    assert gap._style["width"] == "75.0px"  # 次の開始 10/7 9:00 = 2.375日。(2.375 - 0.5) * 40
    assert gap._style["top"] == f"{ACTUAL_TOP_PX}px"
    assert gap._style["height"] == f"{ACTUAL_HEIGHT_PX}px"
    assert "repeating-linear-gradient" in gap._style["background"]
    assert "var(--scolor)" in gap._style["background"]
    assert STATUS_CLASSES[Status.NOT_STARTED] in gap.classes


async def test_there_is_one_line_per_gap(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
            Actual(datetime(2026, 10, 7, 9), None),
        ),
        now=datetime(2026, 10, 7, 12),
    )
    await user.open("/")
    await user.should_see(marker="actual-gap-0-0-0")
    await user.should_see(marker="actual-gap-0-0-1")
    await user.should_not_see(marker="actual-gap-0-0-2")


async def test_no_line_without_a_gap(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 5, 15)),  # 隙間なし
        )
    )
    await user.open("/")
    await user.should_not_see(marker="actual-gap-0-0-0")


async def test_no_line_and_no_crash_for_a_hand_edited_overlap_or_open_interval(
    user: User,
) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 15)),
            Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 5, 18)),  # 重なり
            Actual(datetime(2026, 10, 4, 9), None),  # 逆順で進行中
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),  # 進行中の後ろ
        ),
        now=datetime(2026, 10, 6, 15),
    )
    await user.open("/")
    await user.should_see(marker="actual-0-0-3")
    await user.should_not_see(marker="actual-gap-0-0-0")
    await user.should_not_see(marker="actual-gap-0-0-1")
    await user.should_not_see(marker="actual-gap-0-0-2")


async def test_the_line_is_in_the_status_color(user: User) -> None:
    project = actual_project(
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
    )
    project.sections[0].tasks[0].status = Status.PAUSED
    mount(project)
    await user.open("/")
    gap = user.find(marker="actual-gap-0-0-0").elements.pop()
    assert STATUS_CLASSES[Status.PAUSED] in gap.classes


def test_priority_backgrounds_cover_every_priority_in_both_themes() -> None:
    assert set(PRIORITY_BACKGROUNDS) == set(Priority) == set(PRIORITY_DARK_BACKGROUNDS) == set(PRIORITY_CLASSES)
    assert len(set(PRIORITY_BACKGROUNDS.values())) == len(Priority)
    for priority, cls in PRIORITY_CLASSES.items():
        assert f".{cls} {{ --pbg: {PRIORITY_BACKGROUNDS[priority]}; }}" in PRIORITY_CSS
        assert f"body.body--dark .{cls} {{ --pbg: {PRIORITY_DARK_BACKGROUNDS[priority]}; }}" in PRIORITY_CSS


@pytest.mark.parametrize("priority", list(Priority))
async def test_the_name_cell_has_the_priority_background(user: User, priority: Priority) -> None:
    project = sample_project()
    project.sections[0].tasks[0].priority = priority
    mount(project)
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    assert PRIORITY_CLASSES[priority] in cell.classes
    assert cell._style["background-color"] == PRIORITY_BACKGROUND_VAR
    assert "background-color" not in user.find(marker="row-0-0").elements.pop()._style  # 行は変えない
    assert "background-color" not in user.find(marker="bar-0-0").elements.pop()._style  # 棒は変えない


async def test_the_name_cell_is_one_row_with_the_name_inside(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    name = user.find(marker="task-name-0-0").elements.pop()
    assert isinstance(cell, ui.row)
    assert name.parent_slot.parent is cell
    assert name.text == "設計"
    assert cell.parent_slot.parent is user.find(marker="row-0-0").elements.pop()  # 行の直接の子
    assert cell._style["width"] == "200px"
    assert "padding-left" in cell._style
    assert "flex" in name._style and "min-width" in name._style  # チップの分だけ名前が縮む
    assert "ellipsis" in name.classes


async def test_the_overdue_tint_is_laid_over_the_priority_background(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    assert cell._style["background-color"] == PRIORITY_BACKGROUND_VAR
    assert OVERDUE_COLOR in cell._style["background-image"]


async def test_the_name_cell_is_a_drag_handle_without_a_filter(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert user.find(marker="task-0-0").elements.pop().props.get("draggable") == "true"


def project_with(task: Task) -> Project:
    return Project("demo", base_date=BASE, sections=[Section("開発", [task])])


def chip(user: User, marker: str):  # noqa: ANN202
    return user.find(marker=marker).elements.pop()


def tooltips_targeting(element: ui.element) -> list[str]:
    """element を対象にしたツールチップ。ツールチップは、対象の兄弟として作られ、target で対象を指す。"""
    return [
        c.text
        for c in element.parent_slot.children
        if isinstance(c, ui.tooltip) and c.props.get("target") == f"#{element.html_id}"
    ]


def click_listeners(element: ui.element) -> list[object]:
    return [listener for listener in element._event_listeners.values() if listener.type == "click"]


async def test_no_chips_for_a_plain_task(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    for marker in ("task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        await user.should_not_see(marker=marker)


async def test_project_code_chip(user: User) -> None:
    mount(project_with(Task("設計", project_code="PRJ-001")))
    await user.open("/")
    code = chip(user, "task-code-0-0")
    assert code.text == "PRJ-001"
    assert code._style["max-width"] == "56px"
    assert "ellipsis" in code.classes
    assert tooltips_targeting(code) == ["PRJ-001"]
    assert code.parent_slot.parent is chip(user, "task-0-0")  # 名前の欄の枠の中


async def test_assignee_chip_shows_the_first_character_and_the_name_on_hover(user: User) -> None:
    mount(project_with(Task("設計", assignee="山田太郎")))
    await user.open("/")
    who = chip(user, "task-assignee-0-0")
    assert who.text == "山"
    assert tooltips_targeting(who) == ["山田太郎"]
    assert who._style["width"] == who._style["height"] == "16px"
    assert who.parent_slot.parent is chip(user, "task-0-0")


async def test_an_assignee_who_is_not_a_member_and_an_emoji_name_do_not_break_the_chart(
    user: User,
) -> None:
    mount(project_with(Task("設計", assignee="👨‍👩‍👧 家族")))  # メンバーにいない・複数のコードポイント
    await user.open("/")
    assert chip(user, "task-assignee-0-0").text == "👨"


async def test_progress_text(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        actuals=[Actual(datetime(2026, 10, 5, 12), None, 40)],
    )
    mount(project_with(task), now=datetime(2026, 10, 6, 12))
    await user.open("/")
    assert chip(user, "task-progress-0-0").text == "40%"


async def test_no_progress_text_without_progress(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 5, 12), None)])  # 進捗度なし
    mount(project_with(task))
    await user.open("/")
    await user.should_not_see(marker="task-progress-0-0")


async def test_a_finished_task_without_progress_shows_100_percent(user: User) -> None:
    mount(project_with(Task("設計", status=Status.DONE)))
    await user.open("/")
    assert chip(user, "task-progress-0-0").text == "100%"


async def test_a_zero_progress_is_shown(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 5, 12), None, 0)])
    mount(project_with(task))
    await user.open("/")
    assert chip(user, "task-progress-0-0").text == "0%"


async def test_the_strike_through_covers_the_name_only(user: User) -> None:
    mount(project_with(Task("設計", status=Status.DONE, project_code="P", assignee="山")))
    await user.open("/")
    assert chip(user, "task-name-0-0")._style["text-decoration"] == "line-through"
    for marker in ("task-0-0", "task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        assert "text-decoration" not in chip(user, marker)._style


async def test_the_chips_do_not_shrink_and_the_name_does(user: User) -> None:
    mount(
        project_with(
            Task("とても長いタスクの名前" * 3, project_code="PRJ-LONG-CODE-0001", assignee="山")
        )
    )
    await user.open("/")
    for marker in ("task-code-0-0", "task-assignee-0-0"):
        assert chip(user, marker)._style["flex"] == "none"
    name = chip(user, "task-name-0-0")
    assert "flex" in name._style and name._style["min-width"] == "0"


async def test_the_click_is_handled_once_by_the_name_cell_so_the_chips_bubble_to_it(
    user: User,
) -> None:
    # User のシミュレーションのクリックは、親へ伝わらない(実ブラウザでは、DOM のクリックが枠へ伝わる)。
    # そのため、枠だけがクリックを処理し、名前とチップは自分では処理しないことを確かめる。
    recorder = mount(
        project_with(Task("設計", project_code="PRJ-1", assignee="山", status=Status.DONE))
    )
    await user.open("/")
    assert len(click_listeners(chip(user, "task-0-0"))) == 1
    for marker in ("task-name-0-0", "task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        assert click_listeners(chip(user, marker)) == []
    user.find(marker="task-0-0").click()
    assert recorder.events == [("edit_task", (0, 0))]


def mount_with(project: Project, options: ViewOptions, now: datetime = datetime(2026, 10, 1)) -> None:
    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, Recorder().actions, now=lambda: now)
        chart.options = options
        chart.build()


def test_view_options_defaults_mean_today_s_chart() -> None:
    options = ViewOptions()
    assert (options.period, options.scale, options.show_chips, options.show_alerts, options.read_only) == (
        None, None, True, True, False,
    )


async def test_period_sets_the_first_column_and_clips_bars_at_the_edge(user: User) -> None:
    mount_with(sample_project(), ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 8))))
    await user.open("/")
    await user.should_see(marker="col-2026-10-06")
    await user.should_not_see(marker="col-2026-10-05")
    bar = user.find(marker="bar-0-0").elements.pop()  # 10/5 12:00 → 10/7 12:00。左は端で切る
    assert bar._style["left"] == "200.0px"
    assert bar._style["width"] == "60.0px"  # 10/6 0:00 から 10/7 12:00 = 1.5 日 * 40


async def test_bars_outside_the_period_are_not_drawn_but_the_rows_stay(user: User) -> None:
    outside = Task(
        "範囲外",
        planned_start=datetime(2026, 9, 20),
        planned_end=datetime(2026, 9, 22),
        deadline=datetime(2026, 9, 25),
        actuals=[
            Actual(datetime(2026, 9, 20, 9), datetime(2026, 9, 20, 12)),
            Actual(datetime(2026, 9, 21, 9), datetime(2026, 9, 21, 12)),
        ],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [outside])])
    mount_with(project, ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 8))))
    await user.open("/")
    await user.should_see(marker="task-0-0")  # 行は残る
    for marker in ("bar-0-0", "actual-0-0-0", "actual-0-0-1", "actual-gap-0-0-0", "deadline-0-0", "progress-state-0-0"):
        await user.should_not_see(marker=marker)


async def test_actual_bars_and_gap_lines_inside_the_period_are_kept(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 6),
        planned_end=datetime(2026, 10, 9),
        actuals=[
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
            Actual(datetime(2026, 10, 8, 9), datetime(2026, 10, 8, 12)),
        ],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [task])])
    mount_with(project, ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 10))))
    await user.open("/")
    for marker in ("bar-0-0", "actual-0-0-0", "actual-0-0-1", "actual-gap-0-0-0"):
        await user.should_see(marker=marker)


async def test_preview_scale_is_separate_from_the_toolbar_scale(user: User) -> None:
    mount_with(sample_project(), ViewOptions(scale=Scale.WEEK))
    await user.open("/")
    assert user.find(kind=ui.toggle).elements.pop().value == Scale.DAY  # ツールバーは変わらない
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["width"] != "80.0px"  # 週次の幅で描かれる(日次なら 2.0 日 * 40 = 80px)
    await user.should_not_see(marker="stripes")  # 土日の背景は日次だけ


async def test_show_chips_false_hides_the_chips_and_progress(user: User) -> None:
    task = Task("設計", project_code="PRJ-1", assignee="山", status=Status.DONE)
    project = Project("demo", base_date=BASE, sections=[Section("開発", [task])])
    mount_with(project, ViewOptions(show_chips=False))
    await user.open("/")
    await user.should_see(marker="task-name-0-0")
    for marker in ("task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        await user.should_not_see(marker=marker)


async def test_show_alerts_false_hides_the_overdue_tint(user: User) -> None:
    mount_with(sample_project(), ViewOptions(show_alerts=False), now=datetime(2026, 10, 8))
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    assert "background-image" not in cell._style
    assert user.find(marker="row-0-0").elements.pop()._style.get("background") is None


async def test_show_alerts_false_hides_the_overload_stripes(user: User) -> None:
    mount_with(overloaded_project(), ViewOptions(show_alerts=False))
    await user.open("/")
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="overload-top-0-0")


async def test_alerts_are_shown_by_default(user: User) -> None:
    mount_with(overloaded_project(), ViewOptions())
    await user.open("/")
    await user.should_see(marker="overload-top-0-0")


async def test_set_options_rerenders_and_the_view_scale_follows(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    await user.open("/")
    chart = charts[0]
    chart.set_options(ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 8))))
    await user.should_not_see(marker="col-2026-10-05")
    assert chart.view_scale is Scale.DAY
    chart.set_options(ViewOptions(scale=Scale.MONTH))
    assert chart.view_scale is Scale.MONTH
    assert chart.scale is Scale.DAY
    chart.set_options(ViewOptions())
    await user.should_see(marker="col-2026-10-05")


async def test_read_only_removes_the_edit_parts(user: User) -> None:
    mount_with(sample_project(), ViewOptions(read_only=True))
    await user.open("/")
    for marker in ("add-task-top", "add-task-0", "top-end"):
        await user.should_not_see(marker=marker)
    await user.should_see(marker="section-name-0")  # セクションの見出しは残る
    await user.should_see(marker="task-0-0")


async def test_read_only_hides_the_toolbar_and_set_options_restores_it(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    await user.open("/")
    chart = charts[0]
    assert chart.toolbar is not None and chart.toolbar.visible
    chart.set_options(ViewOptions(read_only=True))
    assert not chart.toolbar.visible
    chart.set_options(ViewOptions())
    assert chart.toolbar.visible


async def test_read_only_has_no_click_handlers_and_no_drag_attributes(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        deadline=datetime(2026, 10, 9),
        actuals=[
            Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 6, 12)),
            Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
        ],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [task])])
    mount_with(project, ViewOptions(read_only=True))
    await user.open("/")
    for marker in ("task-0-0", "bar-0-0", "actual-0-0-0", "actual-gap-0-0-0", "deadline-0-0"):
        assert click_listeners(user.find(marker=marker).elements.pop()) == [], marker
    cell = user.find(marker="task-0-0").elements.pop()
    assert "draggable" not in cell.props and "data-drag-handle" not in cell.props
    bar = user.find(marker="bar-0-0").elements.pop()
    assert "data-bar" not in bar.props
    assert "data-drop" not in user.find(marker="row-0-0").elements.pop().props
    assert "data-drop" not in user.find(marker="section-0").elements.pop().props


async def test_the_edit_handlers_are_kept_when_not_read_only(user: User) -> None:
    recorder = mount(sample_project())
    await user.open("/")
    user.find(marker="bar-0-0").click()
    user.find(marker="task-0-1").click()
    assert recorder.events == [("edit_task", (0, 0)), ("edit_task", (0, 1))]


async def test_content_width_and_the_content_attribute(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    await user.open("/")
    chart = charts[0]
    columns = build_columns(chart.project, Scale.DAY, {})
    assert chart.content_width() == NAME_WIDTH_PX + COLUMN_WIDTH_PX[Scale.DAY] * len(columns)
    content = user.find(marker="chart-content").elements.pop()
    assert "data-chart-content" in content.props
    assert content._style["width"] == f"{chart.content_width()}px"
    chart.set_options(ViewOptions(scale=Scale.WEEK))
    weeks = build_columns(chart.project, Scale.WEEK, {})
    assert chart.content_width() == NAME_WIDTH_PX + COLUMN_WIDTH_PX[Scale.WEEK] * len(weeks)


def long_running_task(progress: int) -> Task:
    """10/5 から翌年 1/31 まで。期間を 10/1〜10/10 にすると、右端(11/11)で切られる。"""
    return Task(
        "長い",
        planned_start=datetime(2026, 10, 5),
        planned_end=datetime(2027, 1, 31),
        planned_end_manual=True,
        status=Status.RUNNING,
        actuals=[Actual(datetime(2026, 10, 5, 9), None, progress)],
    )


async def test_a_state_mark_beyond_the_right_edge_of_the_period_is_not_drawn(user: User) -> None:
    mount_with(
        project_with(long_running_task(0)),
        ViewOptions(period=(date(2026, 10, 1), date(2026, 10, 10))),
        now=datetime(2026, 10, 20),
    )
    await user.open("/")
    await user.should_see(marker="bar-0-0")
    await user.should_not_see(marker="progress-state-0-0")


async def test_the_state_mark_is_still_drawn_without_a_period(user: User) -> None:
    mount_with(project_with(long_running_task(0)), ViewOptions(), now=datetime(2026, 10, 20))
    await user.open("/")
    await user.should_see(marker="progress-state-0-0")


async def test_a_state_mark_does_not_follow_an_actual_bar_outside_the_period(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5),
        planned_end=datetime(2026, 10, 7),
        planned_end_manual=True,
        status=Status.RUNNING,
        actuals=[
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), 0),
            Actual(datetime(2027, 6, 1, 9), datetime(2027, 6, 1, 12), 0),  # 期間よりずっと後ろ
        ],
    )
    mount_with(project_with(task), ViewOptions(period=(date(2026, 10, 1), date(2026, 10, 20))), now=datetime(2026, 10, 12))
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert float(mark._style["left"][:-2]) < 200 + 42 * 40  # 描画の幅(名前の列 + 42 日)の内側


def clipped_task(progress: int, start: datetime, end: datetime) -> Task:
    return Task(
        "設計",
        planned_start=start,
        planned_end=end,
        planned_end_manual=True,
        status=Status.RUNNING,
        actuals=[Actual(start.replace(hour=9), None, progress)],
    )


async def test_the_progress_fill_of_a_bar_clipped_at_the_left_edge_reflects_the_hidden_part(user: User) -> None:
    # 10/1〜10/11 の 10 日で進捗 50% = 10/6 まで塗る。期間は 10/6 から = 見えている部分(5日)に、塗りはない
    mount_with(
        project_with(clipped_task(50, datetime(2026, 10, 1), datetime(2026, 10, 11))),
        ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 20))),
    )
    await user.open("/")
    fill = user.find(marker="progress-fill-0-0").elements.pop()
    assert fill._style["width"] == "0%"


async def test_the_progress_fill_of_a_bar_clipped_at_the_left_edge_covers_the_visible_part_proportionally(
    user: User,
) -> None:
    # 80% = 10/9 まで塗る。見えている 10/6〜10/11 の 5 日のうち、3 日 = 60%
    mount_with(
        project_with(clipped_task(80, datetime(2026, 10, 1), datetime(2026, 10, 11))),
        ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 20))),
    )
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "60%"


async def test_the_progress_fill_of_a_bar_clipped_at_the_right_edge_covers_all_when_the_fill_passes_the_edge(
    user: User,
) -> None:
    mount_with(
        project_with(long_running_task(50)),  # 10/5〜1/31 の 50% = 12/7 まで。右端は 11/11
        ViewOptions(period=(date(2026, 10, 1), date(2026, 10, 10))),
        now=datetime(2026, 10, 20),
    )
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "100%"


async def test_the_progress_fill_without_a_period_is_the_plain_percentage(user: User) -> None:
    mount_with(
        project_with(clipped_task(40, datetime(2026, 10, 5), datetime(2026, 10, 15))),
        ViewOptions(),
        now=datetime(2026, 10, 8),
    )
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "40%"


async def test_the_progress_fill_of_an_unclipped_bar_in_a_period_is_the_plain_percentage(user: User) -> None:
    mount_with(
        project_with(clipped_task(40, datetime(2026, 10, 5), datetime(2026, 10, 15))),
        ViewOptions(period=(date(2026, 10, 1), date(2026, 10, 31))),
        now=datetime(2026, 10, 8),
    )
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "40%"
