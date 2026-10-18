from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import (
    UNASSIGNED,
    Dashboard,
    DueRow,
    LoadStats,
    OverdueRow,
    Period,
    PeriodKind,
    Progress,
    TeamProgress,
    WorkloadRow,
)
from projectapp.dashboard_view import MAX_TIP_CHIPS, DashboardView, percent_width
from projectapp.models import Status


def sample() -> Dashboard:
    return Dashboard(
        Period(date(2026, 10, 5), date(2026, 10, 11)),
        Progress(
            42.4,
            {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 3},
            [OverdueRow("遅れた作業", "田中", datetime(2026, 10, 6, 17))],
        ),
        {"田中": LoadStats(0.5, 1.2, 2), "佐藤": LoadStats(0.0, 0.0, 0)},
        [WorkloadRow("田中", 9.5, 3.0), WorkloadRow("佐藤", 0.0, 0.0), WorkloadRow(UNASSIGNED, 6.5, 0.0)],
        [
            DueRow(datetime(2026, 10, 8, 17), "締切", "設計", "田中", False),
            DueRow(datetime(2026, 10, 9, 12), "完了予定", "遅れ", None, True),
        ],
        TeamProgress(
            42.4,
            {Status.NOT_STARTED: 0.0, Status.RUNNING: 3.0, Status.PAUSED: 0.0, Status.DONE: 1.0},
            counts={Status.NOT_STARTED: 0, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 1},
            tasks={Status.NOT_STARTED: [], Status.RUNNING: ["設計", "実装"], Status.PAUSED: [], Status.DONE: ["調査"]},
        ),
    )


def empty() -> Dashboard:
    day = Period(date(2026, 10, 7), date(2026, 10, 7))
    return Dashboard(day, Progress(None, {status: 0 for status in Status}, []), {}, [], [])


def mount() -> tuple[list[DashboardView], list[int], list[PeriodKind]]:
    views: list[DashboardView] = []
    backs: list[int] = []
    changes: list[PeriodKind] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(lambda: backs.append(1), changes.append)
        views.append(view)
        view.build()

    return views, backs, changes


def text(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


def test_percent_width_is_clamped() -> None:
    assert [percent_width(f) for f in (-1.0, 0.0, 0.5, 2.0)] == ["0.0%", "0.0%", "50.0%", "100.0%"]


async def test_the_view_is_hidden_until_shown_and_can_be_hidden_again(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    await user.should_not_see(marker="dashboard-back")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-back")
    views[0].hide()
    await user.should_not_see(marker="dashboard-back")


async def test_the_progress_card_shows_percent_counts_and_overdue_rows(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")  # refresh は遅延実行なので、描かれるのを待つ
    assert text(user, "dashboard-progress-percent") == "42%"
    assert text(user, "dashboard-count-RUNNING") == "実行中 2"
    assert text(user, "dashboard-count-DONE") == "終了 3"
    assert text(user, "dashboard-overdue-name-0") == "遅れた作業"


async def test_the_load_card_shows_average_peak_and_overload_days(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")  # refresh は遅延実行なので、描かれるのを待つ
    label = user.find(marker="dashboard-load-田中").elements.pop()
    assert label.text == "平均 50% / 最大 120% / 超過 2 日"
    assert "text-negative" in label.classes  # 100% を超える日があれば強調する
    assert "text-negative" not in user.find(marker="dashboard-load-佐藤").elements.pop().classes


async def test_the_hours_card_lists_members_unassigned_and_the_total(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")  # refresh は遅延実行なので、描かれるのを待つ
    assert text(user, "dashboard-hours-田中") == "予定 9.5h / 実績 3.0h"
    assert text(user, f"dashboard-hours-{UNASSIGNED}") == "予定 6.5h / 実績 0.0h"
    assert text(user, "dashboard-hours-total") == "合計 予定 16.0h / 実績 3.0h"


async def test_the_due_card_lists_rows_in_order_and_marks_overdue(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")  # refresh は遅延実行なので、描かれるのを待つ
    assert [text(user, "dashboard-due-0"), text(user, "dashboard-due-kind-0")] == ["設計", "締切"]
    assert [text(user, "dashboard-due-1"), text(user, "dashboard-due-kind-1")] == ["遅れ", "完了予定"]
    assert "text-negative" not in user.find(marker="dashboard-due-0").elements.pop().classes
    assert "text-negative" in user.find(marker="dashboard-due-1").elements.pop().classes


async def test_every_card_shows_a_message_without_data(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(empty(), PeriodKind.WEEK)
    for card in ("progress", "load", "hours", "due"):
        await user.should_see(marker=f"dashboard-empty-{card}")


async def test_changing_the_period_notifies_but_showing_does_not(user: User) -> None:
    views, backs, changes = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    user.find(marker="dashboard-period").elements.pop().set_value("今月")
    assert changes == [PeriodKind.MONTH]
    views[0].show(sample(), PeriodKind.ALL)  # 開き直しでトグルを書き換えても、通知しない
    assert changes == [PeriodKind.MONTH]
    assert user.find(marker="dashboard-period").elements.pop().value == "全期間"
    user.find(marker="dashboard-back").click()
    assert backs == [1]


async def test_the_hours_card_has_a_legend_for_its_two_series(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")  # refresh は遅延実行なので、描かれるのを待つ
    assert text(user, "dashboard-hours-legend-planned") == "予定"
    assert text(user, "dashboard-hours-legend-actual") == "実績"


async def test_the_load_card_shows_the_icon_of_a_member_who_has_one(user: User, icon: str) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, {"田中": icon})
    await user.should_see(marker="dashboard-load-icon-田中")
    assert user.find(marker="dashboard-load-icon-田中").elements.pop()._props["src"] == icon
    await user.should_not_see(marker="dashboard-load-icon-佐藤")  # アイコンのない人には出さない


async def test_the_load_card_shows_no_icon_when_none_are_given(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    await user.should_not_see(marker="dashboard-load-icon-田中")


async def test_the_team_card_draws_the_pie_and_lists_status_hours(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-percent")
    assert text(user, "dashboard-team-percent") == "42%"
    assert text(user, "dashboard-team-legend-RUNNING") == "実行中 2件 3.0h (75%)"
    assert text(user, "dashboard-team-legend-DONE") == "終了 1件 1.0h (25%)"
    await user.should_not_see(marker="dashboard-team-legend-PAUSED")  # 工数のない状態は出さない
    style = user.find(marker="dashboard-team-pie").elements.pop()._style
    assert "conic-gradient" in style["background"]


async def test_the_team_card_is_empty_without_tasks(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(empty(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-empty-team")
    await user.should_not_see(marker="dashboard-team-pie")


def test_pie_background_covers_the_circle_in_status_order() -> None:
    from projectapp.dashboard_view import pie_background

    team = TeamProgress(0, {Status.NOT_STARTED: 1.0, Status.RUNNING: 3.0, Status.PAUSED: 0.0, Status.DONE: 0.0})
    background = pie_background(team)
    assert background.startswith("conic-gradient(")
    assert "var(--pie-not-started) 0.0% 25.0%" in background
    assert "var(--pie-running) 25.0% 100.0%" in background


async def test_the_team_card_says_which_tasks_it_counts(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    views[0].show(data, PeriodKind.ALL)
    await user.should_see(marker="dashboard-team-scope")
    assert text(user, "dashboard-team-scope") == "すべてのタスク"
    data.team.period = data.period
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see("10/05〜10/11 にかかるタスク")  # refresh は遅延実行なので、文言が変わるのを待つ
    assert text(user, "dashboard-team-scope") == "10/05〜10/11 にかかるタスク"


async def test_the_team_legend_tooltip_lists_task_chips(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-percent")
    assert {e.text for e in user.find(marker="dashboard-team-chip-RUNNING").elements} == {"設計", "実装"}  # elements は集合で順序を持たない
    assert {e.text for e in user.find(marker="dashboard-team-chip-DONE").elements} == {"調査"}
    await user.should_not_see(marker="dashboard-team-more-RUNNING")
    chip = user.find(marker="dashboard-team-chip-RUNNING").elements.pop()
    assert chip._style["color"] == "var(--pie-running)"  # 凡例の色。primary にはしない
    assert chip.props.get("color") is None


async def test_the_team_legend_tooltip_folds_the_overflow(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    names = [f"タスク{i}" for i in range(MAX_TIP_CHIPS + 3)]
    data.team.tasks[Status.RUNNING] = names
    data.team.counts[Status.RUNNING] = len(names)
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-more-RUNNING")
    assert text(user, "dashboard-team-more-RUNNING") == "+3件"
    assert len(user.find(marker="dashboard-team-chip-RUNNING").elements) == MAX_TIP_CHIPS
