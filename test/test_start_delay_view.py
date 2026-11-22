"""着工遅れ・停止の描画(要望 161): ガントチャートの帯と名前の欄のチップ。"""

from datetime import date, datetime, time
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp import arrange
from projectapp.forms import build_start_delay, open_settings_dialog
from projectapp.gantt import (
    ACTUAL_HEIGHT_PX,
    ACTUAL_TOP_PX,
    BAR_HEIGHT_PX,
    BAR_TOP_PX,
    GanttChart,
    ViewOptions,
    from_name,
)
from projectapp.models import (
    Actual,
    Project,
    Section,
    StartDelaySettings,
    StartDelayStyle,
    Task,
)
from projectapp.views import MainView
from test_gantt import Recorder
from test_views import mount_capturing, open_members_view
from projectapp.calendar import save_cache

BASE = date(2026, 10, 5)  # 月曜


def mount(
    project: Project,
    now: datetime = datetime(2026, 10, 9, 10),
    options: ViewOptions | None = None,
) -> None:
    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, Recorder().actions, now=lambda: now)
        if options is not None:
            chart.options = options
        chart.build()


def late_start_project(**settings: object) -> Project:
    """予定の開始 10/5 12:00、実績の開始 10/7 9:00(月・火の 2 稼働日の遅れ)。"""
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 9, 12),
        actuals=[Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12))],
    )
    return Project(
        "demo", base_date=BASE, sections=[Section("開発", [task])], **settings
    )


def stopped_project(**settings: object) -> Project:
    """実績が 10/5 9〜12 と 10/7 9〜12。火曜が抜けている(停止 1 日)。"""
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 12),
        actuals=[
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
        ],
    )
    return Project(
        "demo", base_date=BASE, sections=[Section("開発", [task])], **settings
    )


async def test_a_start_delay_band_is_drawn_left_of_the_bar(user: User) -> None:
    mount(late_start_project())
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert band._style["left"] == from_name(20.0)  # 10/5 12:00 = 0.5 日
    assert band._style["width"] == "75.0px"  # 10/7 9:00 = 2.375 日。(2.375 - 0.5) * 40
    assert band._style["top"] == f"{BAR_TOP_PX}px"
    assert band._style["height"] == f"{BAR_HEIGHT_PX}px"
    assert "dashed" in band._style["border"]
    assert "#7e57c2" in band._style["border"]
    assert "repeating-linear-gradient" not in band._style["background"]


async def test_the_chip_names_the_delay(user: User) -> None:
    mount(late_start_project())
    await user.open("/")
    await user.should_see("着工 +2日")
    await user.should_see(marker="task-start-delay-0-0-0")


async def test_a_stop_band_sits_in_the_actual_lane(user: User) -> None:
    mount(stopped_project())
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert band._style["top"] == f"{ACTUAL_TOP_PX}px"
    assert band._style["height"] == f"{ACTUAL_HEIGHT_PX}px"
    await user.should_see("停止 +1日")
    await user.should_not_see("着工")


async def test_an_unstarted_task_gets_a_band_up_to_now(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 9, 12),
    )
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see("未着手 +4日")  # 10/5〜10/8 の 4 稼働日(今は 10/9)
    await user.should_see(marker="start-delay-0-0-0")


@pytest.mark.parametrize(
    ("style", "band", "chip"),
    [
        (StartDelayStyle.BOTH, True, True),
        (StartDelayStyle.BAND, True, False),
        (StartDelayStyle.CHIP, False, True),
    ],
)
async def test_the_style_chooses_the_band_and_the_chip(
    user: User, style: StartDelayStyle, band: bool, chip: bool
) -> None:
    mount(late_start_project(start_delay_style=style))
    await user.open("/")
    for marker, shown in (
        ("start-delay-0-0-0", band),
        ("task-start-delay-0-0-0", chip),
    ):
        if shown:
            await user.should_see(marker=marker)
        else:
            await user.should_not_see(marker=marker)


async def test_nothing_is_drawn_when_it_is_off(user: User) -> None:
    mount(late_start_project(start_delay_enabled=False))
    await user.open("/")
    await user.should_not_see(marker="start-delay-0-0-0")
    await user.should_not_see(marker="task-start-delay-0-0-0")


async def test_the_color_is_used(user: User) -> None:
    mount(late_start_project(start_delay_color="#112233"))
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert "#112233" in band._style["border"]


async def test_the_grace_hides_a_short_delay(user: User) -> None:
    mount(late_start_project(start_delay_grace=2))
    await user.open("/")
    await user.should_not_see(marker="start-delay-0-0-0")


async def test_the_read_only_chart_does_not_draw_it(user: User) -> None:
    mount(late_start_project(), options=ViewOptions(read_only=True))
    await user.open("/")
    await user.should_see("設計")
    await user.should_not_see(marker="start-delay-0-0-0")
    await user.should_not_see(marker="task-start-delay-0-0-0")


def test_build_start_delay_reads_the_inputs() -> None:
    assert build_start_delay(True, "band", 3, "#ABCDEF") == StartDelaySettings(
        True, StartDelayStyle.BAND, 3, "#abcdef"
    )


@pytest.mark.parametrize(
    ("grace", "color", "message"),
    [
        (-1, "#7e57c2", "猶予日数"),
        (31, "#7e57c2", "猶予日数"),
        (1.5, "#7e57c2", "猶予日数"),
        (None, "#7e57c2", "猶予日数"),
        (0, "purple", "色"),
        (0, "", "色"),
    ],
)
def test_build_start_delay_rejects_bad_inputs(
    grace: object, color: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_start_delay(True, "both", grace, color)


def open_dialog_page(start_delay: StartDelaySettings, applied: list) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda *a: None,
                start_delay=start_delay,
                on_start_delay=applied.append,
            ),
        )


async def test_the_settings_dialog_reports_a_changed_start_delay(user: User) -> None:
    applied: list[StartDelaySettings] = []
    open_dialog_page(StartDelaySettings(), applied)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-start-delay-style").elements.pop().set_value("chip")
    user.find(marker="settings-start-delay-grace").elements.pop().set_value(2)
    user.find(marker="settings-apply").click()
    assert applied == [StartDelaySettings(True, StartDelayStyle.CHIP, 2, "#7e57c2")]


async def test_an_unchanged_start_delay_is_not_reported(user: User) -> None:
    applied: list[StartDelaySettings] = []
    open_dialog_page(StartDelaySettings(grace=1), applied)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert applied == []


async def test_a_bad_grace_keeps_the_dialog_open_and_reports_nothing(
    user: User,
) -> None:
    applied: list[StartDelaySettings] = []
    open_dialog_page(StartDelaySettings(), applied)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-start-delay-grace").elements.pop().set_value(1.5)
    user.find(marker="settings-apply").click()
    assert applied == []
    await user.should_see("猶予日数は")


async def test_the_main_view_applies_the_start_delay(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    assert view.project.start_delay == StartDelaySettings()
    view.apply_start_delay(
        StartDelaySettings(False, StartDelayStyle.BAND, 2, "#010203")
    )
    assert view.project.start_delay == StartDelaySettings(
        False, StartDelayStyle.BAND, 2, "#010203"
    )
    assert view.is_dirty()


async def test_the_settings_dialog_in_the_app_changes_the_project(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    user.find(marker="open-settings").click()
    user.find(marker="settings-start-delay-enabled").elements.pop().set_value(False)
    user.find(marker="settings-apply").click()
    assert views[0].project.start_delay_enabled is False
    user.find(marker="open-settings").click()
    assert (
        user.find(marker="settings-start-delay-enabled").elements.pop().value is False
    )


async def test_moving_the_bar_updates_the_delay(user: User) -> None:
    """棒のドラッグ移動(arrange.shift_task + 描き直し)で、予定の開始が動くと、帯とチップも変わる。"""
    project = late_start_project()  # 予定 10/5、着手 10/7: 2 稼働日の遅れ
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(
            project, {}, Recorder().actions, now=lambda: datetime(2026, 10, 9, 10)
        )
        charts.append(chart)
        chart.build()

    await user.open("/")
    await user.should_see("着工 +2日")
    task = project.sections[0].tasks[0]
    assert arrange.shift_task(task, 1)  # 1 日後ろへ
    charts[0].set_project(project)
    await user.should_see("着工 +1日")
    assert arrange.shift_task(task, 1)  # 着手の日と同じになる
    charts[0].set_project(project)
    await user.should_not_see(marker="task-start-delay-0-0-0")
    await user.should_not_see(marker="start-delay-0-0-0")
