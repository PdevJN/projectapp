from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import Project, Task
from projectapp.timeline import Scale


def noop_actions() -> GanttActions:
    return GanttActions(
        add_section=lambda: None,
        add_task=lambda path: None,
        add_top_task=lambda: None,
        edit_task=lambda path, ti: None,
        move_task=lambda src, dst, copy: None,
        shift_task=lambda path, ti, days: None,
        set_name_width=lambda width: None,
    )


def one_task_project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        tasks=[
            Task(
                "設計",
                id="a",
                planned_start=datetime(2026, 10, 6, 9),
                planned_end=datetime(2026, 10, 9, 12),
            )
        ],
    )


async def test_embedded_chart_draws_the_bar_without_a_second_toolbar(
    user: User,
) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        embedded = GanttChart(one_task_project(), {}, noop_actions())
        embedded.build_embedded()
        charts.extend([main, embedded])

    await user.open("/")
    main, embedded = charts
    assert embedded.toolbar is None and embedded.splitter is None
    assert embedded.options.read_only is True
    assert len(embedded.task_rows) == 1
    embedded.set_scale(Scale.WEEK)  # ツールバーがなくても切り替えられる
    assert embedded.scale is Scale.WEEK
    assert main.scale is Scale.DAY  # メインには影響しない
