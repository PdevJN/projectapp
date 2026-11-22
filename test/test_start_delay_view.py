"""着工遅れ・停止の描画(要望 161): ガントチャートの帯と名前の欄のチップ。"""

from datetime import date, datetime

import pytest
from nicegui import ui
from nicegui.testing import User

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
    StartDelayStyle,
    Task,
)
from test_gantt import Recorder

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
