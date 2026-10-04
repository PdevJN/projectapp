import asyncio
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import DayKind
from projectapp.filtering import TaskFilter
from projectapp.gantt import (
    DEADLINE_MARKER_HALF_PX,
    GRID_BORDER,
    KIND_COLORS,
    MIN_BAR_PX,
    OVERDUE_COLOR,
    GanttActions,
    GanttChart,
)
from projectapp.models import DEFAULT_COLOR, Member, Project, Section, Status, Task
from projectapp.timeline import Scale

BASE = date(2026, 10, 5)  # 月曜


class Recorder:
    """操作のコールバックを記録する。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[int | None, ...]]] = []
        self.actions = GanttActions(
            add_section=lambda: self.events.append(("add_section", ())),
            add_task=lambda si: self.events.append(("add_task", (si,))),
            add_top_task=lambda: self.events.append(("add_top_task", ())),
            edit_task=lambda si, ti: self.events.append(("edit_task", (si, ti))),
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
    assert bar._style["background"] == "#ff0000"


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
    assert bar._style["background"] == "#00ff00"


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
    assert row_of(content="開発")._style["border-bottom"] == GRID_BORDER
    header = row_of(marker="col-2026-10-05").parent_slot.parent
    assert header._style["border-bottom"] == GRID_BORDER


def band_widths(user: User, marker: str) -> dict[str, str]:
    return {e.text: e._style["width"] for e in user.find(marker=marker).elements}


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
    assert user.find(marker="bar-0-0").elements.pop()._style["background"] == "#ff0000"


async def test_overdue_applies_to_top_level_tasks(user: User) -> None:
    mount(top_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-top-0") == OVERDUE_COLOR


async def test_a_bad_color_in_a_hand_edited_file_falls_back_to_the_default(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].color = "red; background: url(x)"
    mount(project)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["background"] == DEFAULT_COLOR


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
