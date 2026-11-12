import asyncio
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.bottom_info import AssignmentLayout
from projectapp.gantt import GanttChart, ViewOptions
from projectapp.models import Assignee, Member, Project, Task
from projectapp.timeline import Scale
from test_gantt import Recorder

BASE = date(2026, 10, 5)


def project() -> Project:
    return Project(
        "demo",
        base_date=BASE,
        members=[Member("田中", 1.0)],
        tasks=[
            Task(
                "a",
                id="a",
                planned_start=datetime(2026, 10, 5, 9),
                effort_hours=13,
                assignees=[Assignee("田中", 1.0)],
            ),
            Task("b", id="b"),
        ],
    )


def mount() -> list[GanttChart]:
    charts: list[GanttChart] = []
    recorder = Recorder()
    recorder.actions.set_main_split = lambda value: None
    recorder.actions.set_name_width = lambda value: None

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(
            project(), {}, recorder.actions, now=lambda: datetime(2026, 10, 7, 12)
        )
        charts.append(chart)
        chart.build()

    return charts


async def test_toggling_opens_a_folded_panel_on_the_assignment_view(
    user: User,
) -> None:
    charts = mount()
    await user.open("/")
    assert not charts[0].bottom_open
    charts[0].toggle_assignment()
    assert charts[0].bottom_open and charts[0].bottom.view == "assignment"
    await user.should_see(marker="bottom-assignment")
    assert [r.name for r in charts[0].bottom.content.assignment.rows] == ["田中"]


async def test_selecting_while_in_the_assignment_view_keeps_it_until_toggled_back(
    user: User,
) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    charts[0].clicked_task("a", {"ctrl": True})
    await user.should_see(marker="bottom-assignment")
    await user.should_not_see(marker="bottom-detail")
    charts[0].toggle_assignment()
    await user.should_see(marker="bottom-detail")


async def test_the_table_follows_the_scale(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    days = len(charts[0].bottom.content.assignment.labels)
    charts[0].set_scale(Scale.WEEK)
    await asyncio.sleep(0.2)
    weeks = len(charts[0].bottom.content.assignment.labels)
    assert 0 < weeks < days


async def test_the_info_view_does_not_compute_the_table(user: User) -> None:
    charts = mount()
    await user.open("/")
    assert charts[0].bottom.content.assignment is None


async def test_toggling_does_nothing_in_the_preview(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].set_options(ViewOptions(read_only=True))
    charts[0].toggle_assignment()
    assert charts[0].bottom.view == "info"


async def test_the_layout_follows_the_scale_and_the_name_width(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    assert charts[0].bottom.content.layout == AssignmentLayout(200, 40)
    charts[0].set_scale(Scale.WEEK)
    await asyncio.sleep(0.2)
    assert charts[0].bottom.content.layout == AssignmentLayout(200, 56)


async def test_dragging_the_name_width_updates_the_table(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    charts[0].handle_name_width({"width": 300})
    assert charts[0].bottom.content.layout.name_px == 300


async def test_the_name_width_change_is_harmless_in_the_info_view(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].handle_name_width({"width": 300})
    assert charts[0].bottom.content.layout is None


async def test_the_table_and_header_follow_the_quarter_scale(user: User) -> None:
    from projectapp.timeline import Scale

    charts = mount()
    await user.open("/")
    charts[0].fiscal_start_month = 4
    charts[0].toggle_assignment()
    charts[0].set_scale(Scale.QUARTER)
    await asyncio.sleep(0.2)
    labels = charts[0].bottom.content.assignment.labels
    assert 0 < len(labels) <= 12 and set(labels) <= {"Q1", "Q2", "Q3", "Q4"}
    await user.should_see(marker="year-band")
    await user.should_not_see(marker="month-band")
    band = user.find(marker="year-band-label").elements.pop()
    assert band.text.endswith("年度")


def test_the_quarter_column_limit_and_unit() -> None:
    from projectapp.periodfield import check_column_count

    assert check_column_count(Scale.QUARTER, 80) is None
    message = check_column_count(Scale.QUARTER, 81)
    assert message is not None and "四半期" in message
