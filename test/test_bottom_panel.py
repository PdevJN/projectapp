from datetime import datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.bottom_info import PeriodSummary, TaskDetail, TodayRow
from projectapp.bottom_panel import BottomPanel, PanelContent
from projectapp.models import Status

SUMMARY = PeriodSummary(
    3, {s: (1 if s is Status.RUNNING else 0) for s in Status}, 26.0, 1, 40.0, 1, 0
)
DETAIL = TaskDetail(
    "設計",
    "通常",
    [("状態", "実行中"), ("担当", "田中 100%")],
    ["予定超過(完了予定 10/06 12:00 を過ぎています)"],
    2,
)
TODAY = [TodayRow("実装", "田中", 30, datetime(2026, 10, 8, 12))]


def mount() -> list[BottomPanel]:
    panels: list[BottomPanel] = []

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel()
        panel.build()
        panel.update(PanelContent(None, SUMMARY, TODAY))
        panels.append(panel)

    return panels


async def test_without_a_selection_it_shows_the_summary_and_the_today_tab(
    user: User,
) -> None:
    mount()
    await user.open("/")
    await user.should_see(marker="bottom-summary")
    await user.should_see(marker="bottom-today")
    await user.should_not_see(marker="bottom-detail")


async def test_the_legend_tab_replaces_the_today_tab(user: User) -> None:
    mount()
    await user.open("/")
    user.find(marker="bottom-tab-legend").click()
    await user.should_see(marker="bottom-legend")
    await user.should_not_see(marker="bottom-today")


async def test_a_selection_shows_only_the_detail_and_the_other_count(
    user: User,
) -> None:
    panels = mount()
    await user.open("/")
    panels[0].update(PanelContent(DETAIL, SUMMARY, TODAY))
    await user.should_see(marker="bottom-detail")
    await user.should_see(marker="bottom-others")
    await user.should_not_see(marker="bottom-summary")
    await user.should_see("予定超過")


async def test_clearing_the_selection_returns_to_the_summary_and_keeps_the_tab(
    user: User,
) -> None:
    panels = mount()
    await user.open("/")
    user.find(marker="bottom-tab-legend").click()
    panels[0].update(PanelContent(DETAIL, SUMMARY, TODAY))
    panels[0].update(PanelContent(None, SUMMARY, TODAY))
    await user.should_see(marker="bottom-summary")
    await user.should_see(marker="bottom-legend")


async def test_an_empty_summary_shows_dashes(user: User) -> None:
    panels = mount()
    await user.open("/")
    empty = PeriodSummary(0, {s: 0 for s in Status}, 0.0, 0, None, 0, 0)
    panels[0].update(PanelContent(None, empty, []))
    await user.should_see(marker="bottom-summary")
    await user.should_see("—")
