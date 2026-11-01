import asyncio
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

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
