from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import GanttChart, ViewOptions
from projectapp.models import Project, Task
from test_gantt import Recorder

BASE = date(2026, 10, 5)


def project() -> Project:
    return Project(
        "demo",
        base_date=BASE,
        tasks=[
            Task("a", id="a", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5),
            Task("b", id="b"),
        ],
    )


def mount(main_split: int = 100, open_ratio: int = 70):
    charts: list[GanttChart] = []
    recorder = Recorder()
    saved: list[int] = []
    actions = recorder.actions
    actions.set_main_split = saved.append

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(
            project(),
            {},
            actions,
            now=lambda: datetime(2026, 10, 7, 12),
            main_split=main_split,
            open_ratio=open_ratio,
        )
        charts.append(chart)
        chart.build()

    return charts, saved


async def test_the_first_start_folds_the_bottom_panel(user: User) -> None:
    charts, _ = mount()
    await user.open("/")
    assert charts[0].splitter.value == 100
    assert not charts[0].bottom_open


async def test_a_saved_split_is_restored(user: User) -> None:
    charts, _ = mount(main_split=60)
    await user.open("/")
    assert charts[0].splitter.value == 60 and charts[0].bottom_open
    await user.should_see(marker="bottom-summary")


async def test_selecting_a_task_opens_a_folded_panel_at_the_open_ratio(
    user: User,
) -> None:
    charts, _ = mount(open_ratio=75)
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    assert charts[0].splitter.value == 75
    await user.should_see(marker="bottom-detail")


async def test_selecting_does_not_move_an_open_panel(user: User) -> None:
    charts, _ = mount(main_split=55)
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    assert charts[0].splitter.value == 55


async def test_clearing_the_selection_keeps_the_panel_open_and_shows_the_summary(
    user: User,
) -> None:
    charts, _ = mount()
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    charts[0].clear_selection()
    assert charts[0].splitter.value == 70
    await user.should_see(marker="bottom-summary")


async def test_moving_the_splitter_reports_the_new_value(user: User) -> None:
    charts, saved = mount()
    await user.open("/")
    charts[0].splitter.set_value(65)
    assert saved[-1] == 65


async def test_a_selected_task_that_gets_filtered_out_falls_back_to_the_summary(
    user: User,
) -> None:
    from projectapp.filtering import TaskFilter

    charts, _ = mount()
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    charts[0].set_filter(TaskFilter(query="zzz"))
    await user.should_see(marker="bottom-summary")


async def test_the_preview_hides_the_panel_and_does_not_report_the_split(
    user: User,
) -> None:
    charts, saved = mount(main_split=60)
    await user.open("/")
    saved.clear()
    charts[0].set_options(ViewOptions(read_only=True))
    assert charts[0].splitter.value == 100 and saved == []
    charts[0].set_options(ViewOptions())
    assert charts[0].splitter.value == 60 and saved == []


async def test_an_almost_folded_split_counts_as_folded_and_a_selection_opens_it(
    user: User,
) -> None:
    charts, saved = mount()
    await user.open("/")
    charts[0].splitter.set_value(99.6)  # Quasar は小数を送る
    assert not charts[0].bottom_open
    charts[0].clicked_task("a", {"ctrl": True})
    assert charts[0].splitter.value == 70
    assert saved[0] == 100  # 99.6 は切り捨てず丸める
