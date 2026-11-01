import asyncio
from datetime import datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.bottom_info import (
    AssignmentCell,
    AssignmentRow,
    AssignmentTable,
    PeriodSummary,
    TaskDetail,
    TodayRow,
)
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


async def test_status_counts_and_today_rows_carry_the_status_color(user: User) -> None:
    from projectapp.bottom_info import TodayRow

    panels: list[BottomPanel] = []

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel()
        panel.build()
        today = [
            TodayRow("実装", "田中", 30, datetime(2026, 10, 8, 12), Status.RUNNING)
        ]
        panel.update(PanelContent(None, SUMMARY, today))
        panels.append(panel)

    await user.open("/")
    row = user.find(marker="bottom-today-row").elements.pop()
    assert "status-running" in row.classes
    counts = user.find(marker="bottom-status-count").elements
    assert len(counts) == len(Status)
    assert any("status-running" in e.classes for e in counts)


async def test_no_effort_count_lists_chips_and_a_click_selects_them(
    user: User,
) -> None:
    picked: list[list[str]] = []
    summary = PeriodSummary(
        3,
        {s: 0 for s in Status},
        26.0,
        2,
        40.0,
        0,
        0,
        (("a", "設計"), ("b", "調査")),
    )

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel(on_select=picked.append)
        panel.build()
        panel.update(PanelContent(None, summary, []))

    await user.open("/")
    chips = user.find(marker="bottom-no-effort-chip").elements
    assert sorted(c.text for c in chips) == ["設計", "調査"]  # 順序は保証されない
    user.find(marker="bottom-no-effort").click()
    await asyncio.sleep(0.2)  # クリックの処理は非同期に届く
    assert picked == [["a", "b"]]


async def test_the_legend_is_a_table_with_one_row_per_group(user: User) -> None:
    mount()
    await user.open("/")
    user.find(marker="bottom-tab-legend").click()
    await user.should_see(marker="bottom-legend")
    rows = user.find(marker="bottom-legend-group").elements
    assert len(rows) == 3  # 状態・優先度・印


async def test_each_today_row_has_a_status_icon_left_of_the_label(user: User) -> None:
    from projectapp.bottom_info import STATUS_ICON, TodayRow

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel()
        panel.build()
        today = [
            TodayRow("実装", "田中", 30, datetime(2026, 10, 8, 12), Status.RUNNING),
            TodayRow("調査", "鈴木", None, None, Status.PAUSED),
        ]
        panel.update(PanelContent(None, SUMMARY, today))

    await user.open("/")
    icons = user.find(marker="bottom-today-icon").elements
    assert sorted(i.props["name"] for i in icons) == sorted(
        [STATUS_ICON[Status.RUNNING], STATUS_ICON[Status.PAUSED]]
    )
    assert len(set(STATUS_ICON.values())) == len(Status)
    assert all("status-" in " ".join(i.classes) for i in icons)


TABLE = AssignmentTable(
    ["10/5", "10/6", "10/7"],
    [
        AssignmentRow(
            "田中",
            [
                AssignmentCell(1.0, False, False),
                AssignmentCell(2.0, True, False),
                AssignmentCell(0.0, False, True),
            ],
        )
    ],
)


def mount_assignment(content: PanelContent, toggled: list[int] | None = None):
    panels: list[BottomPanel] = []

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel(
            on_toggle_view=(lambda: toggled.append(1)) if toggled is not None else None
        )
        panel.build()
        panel.update(content)
        panels.append(panel)

    return panels


async def test_the_assignment_view_shows_a_row_per_member_and_cell_markers(
    user: User,
) -> None:
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, TABLE))
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment")
    await user.should_not_see(marker="bottom-summary")
    assert len(user.find(marker="bottom-assignment-cell").elements) == 3
    assert len(user.find(marker="bottom-assignment-over").elements) == 1
    assert len(user.find(marker="bottom-assignment-closed").elements) == 1


async def test_the_assignment_view_ignores_a_selection_until_it_is_toggled_back(
    user: User,
) -> None:
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, TABLE))
    await user.open("/")
    panels[0].toggle_view()
    panels[0].update(PanelContent(DETAIL, SUMMARY, TODAY, TABLE))  # 選択した
    await user.should_see(marker="bottom-assignment")
    await user.should_not_see(marker="bottom-detail")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-detail")


async def test_an_empty_table_says_so_instead_of_failing(user: User) -> None:
    panels = mount_assignment(
        PanelContent(None, SUMMARY, TODAY, AssignmentTable([], []))
    )
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment-empty")


async def test_the_toggle_button_calls_the_callback(user: User) -> None:
    toggled: list[int] = []
    mount_assignment(PanelContent(None, SUMMARY, TODAY), toggled)
    await user.open("/")
    user.find(marker="bottom-view-toggle").click()
    await asyncio.sleep(0.2)
    assert toggled == [1]
