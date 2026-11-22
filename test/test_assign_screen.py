from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.assign_screen import AssignScreen
from projectapp.assign_trial import AssignTrial
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


def mount_screen(confirmed: list[AssignTrial], screens: list[AssignScreen]) -> None:
    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        project = one_task_project()
        screen = AssignScreen(
            project, project.tasks[0], {}, on_confirm=confirmed.append
        )
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")


async def test_open_shows_the_title_and_the_chart(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-screen")
    await user.should_see(marker="assign-task-title")
    assert screens[0].chart is not None and len(screens[0].chart.task_rows) == 1


async def test_scale_toggle_changes_only_the_embedded_chart(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-scale")
    screens[0].set_scale(Scale.MONTH)
    assert screens[0].chart is not None and screens[0].chart.scale is Scale.MONTH


async def test_confirm_calls_back_with_the_trial_and_closes(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-confirm")
    screens[0].trial.task.name = "詳細設計"
    user.find(marker="assign-confirm").click()
    assert [t.task.name for t in confirmed] == ["詳細設計"]
    assert screens[0].dialog is not None and screens[0].dialog.value is False


async def test_cancel_without_changes_closes_without_asking(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    user.find(marker="assign-cancel").click()
    assert screens[0].dialog is not None and screens[0].dialog.value is False
    assert confirmed == []


async def test_cancel_with_changes_asks_and_keeps_the_screen_on_no(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    screens[0].trial.task.name = "変更"
    user.find(marker="assign-cancel").click()
    await user.should_see(marker="assign-discard-no")
    user.find(marker="assign-discard-no").click()
    assert (
        screens[0].dialog is not None and screens[0].dialog.value is True
    )  # 画面に戻る
    user.find(marker="assign-discard-yes").click()
    assert screens[0].dialog.value is False
    assert confirmed == []


async def test_escape_key_cancels_like_the_cancel_button(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    dialog = screens[0].dialog
    assert dialog is not None
    [listener] = [ev for ev in dialog._event_listeners.values() if "escape" in ev.type]
    listener.handler(None)  # 変更がないので、確認なしで閉じる
    assert dialog.value is False
    assert confirmed == []


async def test_embedded_scroll_box_is_separate_from_the_main_chart(user: User) -> None:
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
    assert embedded.scroll_selector != main.scroll_selector
    assert embedded.scroll_box is not None
    assert "data-assign-scroll" in embedded.scroll_box.props
    sent: list[str] = []
    assert embedded.client is not None
    embedded.client.run_javascript = lambda js, **kw: sent.append(js)  # type: ignore[method-assign]
    embedded.scroll_to_left()
    assert sent and all("data-assign-scroll" in js for js in sent)
    assert not any("data-chart-scroll" in js for js in sent)
