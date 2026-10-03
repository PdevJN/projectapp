import asyncio
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import DayKind
from projectapp.gantt import (
    GRID_BORDER,
    KIND_COLORS,
    MIN_BAR_PX,
    OVERDUE_COLOR,
    GanttActions,
    GanttChart,
)
from projectapp.models import DEFAULT_COLOR, Project, Section, Status, Task
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
