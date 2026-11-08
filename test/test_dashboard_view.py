import asyncio
import re
from dataclasses import replace
from datetime import date, datetime, timedelta

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import (
    Backlog,
    CrossLoad,
    CrossSummary,
    DayLoad,
    CatchUp,
    CatchUpMode,
    Candidate,
    Investment,
    LateBasis,
    LoadFailure,
    ProjectLoad,
    ProjectPeak,
    UNASSIGNED,
    Dashboard,
    DueRow,
    LoadStats,
    MemberProgress,
    OverdueRow,
    Period,
    PeriodKind,
    Progress,
    ProgressDelta,
    Recovery,
    TeamProgress,
    UnassignedTask,
    WorkloadRow,
)
from projectapp.burndown import Burndown, Mark
from projectapp.dashboard_views import DEFAULT_ORDER, CardId, ViewState, hidden_cards
from projectapp.tipchips import MAX_TIP_CHIPS
from projectapp.dashboard_view import (
    HEATMAP_CSS,
    ViewActions,
    burndown_lines,
    HEATMAP_HINT_DAYS,
    DashboardView,
    delta_line,
    heatmap_html,
    scroll_to_today_js,
    percent_width,
)
from projectapp.models import Status


def sample() -> Dashboard:
    return Dashboard(
        Period(date(2026, 10, 5), date(2026, 10, 11)),
        Progress(
            42.4,
            {
                Status.NOT_STARTED: 1,
                Status.RUNNING: 2,
                Status.PAUSED: 0,
                Status.DONE: 3,
            },
            [OverdueRow("遅れた作業", "田中", datetime(2026, 10, 6, 17), ("田中",))],
            [
                MemberProgress(
                    "田中",
                    40.0,
                    {
                        Status.NOT_STARTED: 1,
                        Status.RUNNING: 2,
                        Status.PAUSED: 0,
                        Status.DONE: 0,
                    },
                ),
                MemberProgress("佐藤", None, {status: 0 for status in Status}),
            ],
        ),
        {"田中": LoadStats(0.5, 1.2, 2), "佐藤": LoadStats(0.0, 0.0, 0)},
        [
            WorkloadRow("田中", 9.5, 3.0),
            WorkloadRow("佐藤", 0.0, 0.0),
            WorkloadRow(UNASSIGNED, 6.5, 0.0),
        ],
        [
            DueRow(
                datetime(2026, 10, 8, 17),
                "締切",
                "設計",
                "田中",
                False,
                False,
                ("田中",),
            ),
            DueRow(datetime(2026, 10, 9, 12), "完了予定", "遅れ", None, True),
        ],
        TeamProgress(
            42.4,
            {
                Status.NOT_STARTED: 0.0,
                Status.RUNNING: 3.0,
                Status.PAUSED: 0.0,
                Status.DONE: 1.0,
            },
            counts={
                Status.NOT_STARTED: 0,
                Status.RUNNING: 2,
                Status.PAUSED: 0,
                Status.DONE: 1,
            },
            tasks={
                Status.NOT_STARTED: [],
                Status.RUNNING: ["設計", "実装"],
                Status.PAUSED: [],
                Status.DONE: ["調査"],
            },
        ),
        None,
        ["田中", "佐藤"],
    )


def empty() -> Dashboard:
    day = Period(date(2026, 10, 7), date(2026, 10, 7))
    return Dashboard(
        day, Progress(None, {status: 0 for status in Status}, []), {}, [], []
    )


def mount(
    member_changes: list[str | None] | None = None,
    actions: ViewActions | None = None,
    late_basis_changes: list[LateBasis] | None = None,
    catch_up_changes: list[CatchUp] | None = None,
    try_changes: list[tuple[str, ...]] | None = None,
) -> tuple[list[DashboardView], list[int], list[PeriodKind]]:
    views: list[DashboardView] = []
    backs: list[int] = []
    changes: list[PeriodKind] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(
            lambda: backs.append(1),
            changes.append,
            member_changes.append if member_changes is not None else None,
            actions=actions,
            on_late_basis_change=late_basis_changes.append
            if late_basis_changes is not None
            else None,
            on_catch_up_change=catch_up_changes.append
            if catch_up_changes is not None
            else None,
            on_try_on_gantt=try_changes.append if try_changes is not None else None,
        )
        views.append(view)
        view.build()

    return views, backs, changes


def text(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


def test_percent_width_is_clamped() -> None:
    assert [percent_width(f) for f in (-1.0, 0.0, 0.5, 2.0)] == [
        "0.0%",
        "0.0%",
        "50.0%",
        "100.0%",
    ]


async def test_the_view_is_hidden_until_shown_and_can_be_hidden_again(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    await user.should_not_see(marker="dashboard-back")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-back")
    views[0].hide()
    await user.should_not_see(marker="dashboard-back")


async def test_the_progress_card_shows_percent_counts_and_overdue_rows(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(
        marker="dashboard-progress-percent"
    )  # refresh は遅延実行なので、描かれるのを待つ
    assert text(user, "dashboard-progress-percent") == "42%"
    assert text(user, "dashboard-count-RUNNING") == "実行中 2"
    assert text(user, "dashboard-count-DONE") == "終了 3"
    assert text(user, "dashboard-overdue-name-0") == "遅れた作業"


async def test_the_load_card_shows_average_peak_and_overload_days(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(
        marker="dashboard-progress-percent"
    )  # refresh は遅延実行なので、描かれるのを待つ
    label = user.find(marker="dashboard-load-田中").elements.pop()
    assert label.text == "平均 50% / 最大 120% / 割り当て超過 2 日"
    assert "text-negative" in label.classes  # 100% を超える日があれば強調する
    assert (
        "text-negative"
        not in user.find(marker="dashboard-load-佐藤").elements.pop().classes
    )


async def test_the_hours_card_lists_members_unassigned_and_the_total(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(
        marker="dashboard-progress-percent"
    )  # refresh は遅延実行なので、描かれるのを待つ
    assert text(user, "dashboard-hours-田中") == "予定 9.5h / 実績 3.0h"
    assert text(user, f"dashboard-hours-{UNASSIGNED}") == "予定 6.5h / 実績 0.0h"
    assert text(user, "dashboard-hours-total") == "合計 予定 16.0h / 実績 3.0h"


async def test_the_due_card_lists_rows_in_order_and_marks_overdue(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(
        marker="dashboard-progress-percent"
    )  # refresh は遅延実行なので、描かれるのを待つ
    assert [text(user, "dashboard-due-0"), text(user, "dashboard-due-kind-0")] == [
        "設計",
        "締切",
    ]
    assert [text(user, "dashboard-due-1"), text(user, "dashboard-due-kind-1")] == [
        "遅れ",
        "完了予定",
    ]
    assert (
        "text-negative"
        not in user.find(marker="dashboard-due-0").elements.pop().classes
    )
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
    views[0].show(
        sample(), PeriodKind.ALL
    )  # 開き直しでトグルを書き換えても、通知しない
    assert changes == [PeriodKind.MONTH]
    assert user.find(marker="dashboard-period").elements.pop().value == "全期間"
    user.find(marker="dashboard-back").click()
    assert backs == [1]


async def test_the_hours_card_has_a_legend_for_its_two_series(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(
        marker="dashboard-progress-percent"
    )  # refresh は遅延実行なので、描かれるのを待つ
    assert text(user, "dashboard-hours-legend-planned") == "予定"
    assert text(user, "dashboard-hours-legend-actual") == "実績"


async def test_the_load_card_shows_the_icon_of_a_member_who_has_one(
    user: User, icon: str
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, {"田中": icon})
    await user.should_see(marker="dashboard-load-icon-田中")
    assert (
        user.find(marker="dashboard-load-icon-田中").elements.pop()._props["src"]
        == icon
    )
    assert (
        user.find(marker="dashboard-load-icon-佐藤").elements.pop().text == "佐"
    )  # アイコンのない人は頭文字の丸


async def test_the_load_card_shows_the_initial_when_no_icon_is_given(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert user.find(marker="dashboard-load-icon-田中").elements.pop().text == "田"


async def test_every_row_with_a_name_has_an_icon_or_initial(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, 2, 4.0, 3.0, [("田中", 12.0), ("未割り当て", 8.0)])
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-member-田中")
    assert (
        user.find(marker="dashboard-backlog-member-icon-田中").elements.pop().text
        == "田"
    )
    await user.should_not_see(
        marker="dashboard-backlog-member-icon-未割り当て"
    )  # メンバーでない行には出さない
    await user.should_see(marker="dashboard-overdue-assignee-0")
    row = user.find(marker="dashboard-overdue-assignee-0").elements.pop()
    assert [c.text for c in row.descendants() if getattr(c, "text", None)] == [
        "田",
        "田中",
    ]  # 頭文字の丸と名前
    await user.should_see(marker="dashboard-hours-icon-田中")
    await user.should_see(marker="dashboard-due-assignee-0")


def test_the_heatmap_names_have_an_icon_or_initial(icon: str) -> None:
    cross = long_heat_summary(2)
    assert '>田</span><span class="heat-person"' in heatmap_html(cross)
    with_icon = heatmap_html(cross, {"田中": icon})
    assert "<img" in with_icon and ">田</span>" not in with_icon


async def test_the_team_card_draws_the_bar_and_lists_status_hours(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-done")
    assert text(user, "dashboard-team-done") == "終了 25%(工数ベース)"
    assert text(user, "dashboard-team-legend-RUNNING") == "実行中 2件 3.0h (75%)"
    assert text(user, "dashboard-team-legend-DONE") == "終了 1件 1.0h (25%)"
    await user.should_not_see(
        marker="dashboard-team-legend-PAUSED"
    )  # 件数のない状態は出さない
    await user.should_see(marker="dashboard-team-bar-RUNNING")
    await user.should_not_see(marker="dashboard-team-percent")  # 円と中央の進捗率はない


async def test_the_team_card_notes_tasks_counted_as_one_hour(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    views[0].show(data, PeriodKind.WEEK)
    await user.should_not_see(marker="dashboard-team-unset")
    data.team.unset = 2
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see("工数なし 2 件は 1h として数えています")


async def test_the_team_card_is_empty_without_tasks(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(empty(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-empty-team")
    await user.should_not_see(marker="dashboard-team-bar-RUNNING")


async def test_the_team_card_says_which_tasks_it_counts(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    views[0].show(data, PeriodKind.ALL)
    await user.should_see(marker="dashboard-team-scope")
    assert text(user, "dashboard-team-scope") == "チーム全体の進捗(すべてのタスク)"
    data.team.period = data.period
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(
        "10/05〜10/11 にかかるタスク"
    )  # refresh は遅延実行なので、文言が変わるのを待つ
    assert (
        text(user, "dashboard-team-scope")
        == "チーム全体の進捗(10/05〜10/11 にかかるタスク)"
    )


async def test_the_team_legend_tooltip_lists_task_chips(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-done")
    assert {
        e.text for e in user.find(marker="dashboard-team-chip-RUNNING").elements
    } == {"設計", "実装"}  # elements は集合で順序を持たない
    assert {e.text for e in user.find(marker="dashboard-team-chip-DONE").elements} == {
        "調査"
    }
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
    assert (
        len(user.find(marker="dashboard-team-chip-RUNNING").elements) == MAX_TIP_CHIPS
    )


async def test_the_member_select_lists_everyone_and_the_members_and_reports_changes(
    user: User,
) -> None:
    picked: list[str | None] = []
    views, _, _ = mount(picked)
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member")
    select = user.find(marker="dashboard-member").elements.pop()
    assert select.options == {"": "全員", "田中": "田中", "佐藤": "佐藤"}
    assert select.value == ""
    assert picked == []  # 表示を合わせるだけでは通知しない
    select.set_value("田中")
    assert picked == ["田中"]
    select.set_value("")
    assert picked == ["田中", None]


async def test_the_member_select_follows_the_dashboard_data(user: User) -> None:
    views, _, _ = mount([])
    await user.open("/")
    data = sample()
    data.member = "佐藤"
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member")
    assert user.find(marker="dashboard-member").elements.pop().value == "佐藤"


async def test_the_progress_card_lists_progress_per_member(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-progress-田中")
    assert text(user, "dashboard-member-progress-田中") == "40% / 3件"
    assert text(user, "dashboard-member-progress-佐藤") == "タスクなし"


def warned_sample() -> Dashboard:
    counts = {
        Status.NOT_STARTED: 0,
        Status.RUNNING: 2,
        Status.PAUSED: 0,
        Status.DONE: 0,
    }
    data = sample()
    data.progress = Progress(
        40.0,
        counts,
        [],
        [
            MemberProgress("田中", 40.0, counts, warnings=3, limit=3),  # 閾値ちょうど
            MemberProgress("鈴木", 40.0, counts, warnings=2, limit=3),  # 閾値の手前
            MemberProgress("佐藤", 40.0, counts, warnings=4, limit=None),  # 閾値なし
            MemberProgress("高橋", 40.0, counts, warnings=0, limit=1),  # 0 件
        ],
        [MemberProgress("甲", 40.0, counts, warnings=5)],
        warnings=5,
    )
    data.due = [
        DueRow(datetime(2026, 10, 8, 17), "締切", "警告の作業", "田中", False, True),
        DueRow(datetime(2026, 10, 9, 12), "完了予定", "遅れ", None, True, False),
        DueRow(datetime(2026, 10, 9, 17), "締切", "ふつう", None, False, False),
    ]
    return data


async def test_the_progress_card_shows_the_warning_count(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-count-warning")
    assert text(user, "dashboard-count-warning") == "警告 5"


async def test_member_and_team_rows_show_the_warning_count_only_when_there_is_one(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-warning-田中")
    assert text(user, "dashboard-member-warning-田中") == "警告 3 件"
    assert text(user, "dashboard-team-row-warning-甲") == "警告 5 件"
    await user.should_not_see(marker="dashboard-member-warning-高橋")


async def test_a_member_at_the_limit_is_highlighted_and_others_are_not(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-limit-田中")
    await user.should_not_see(marker="dashboard-member-limit-鈴木")
    await user.should_not_see(marker="dashboard-member-limit-佐藤")
    await user.should_not_see(marker="dashboard-member-limit-高橋")
    assert (
        "text-weight-bold"
        in user.find(marker="dashboard-member-warning-田中").elements.pop().classes
    )
    assert (
        "text-weight-bold"
        not in user.find(marker="dashboard-member-warning-鈴木").elements.pop().classes
    )


async def test_the_team_row_is_never_highlighted(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-row-warning-甲")
    await user.should_not_see(marker="dashboard-team-row-limit-甲")


async def test_the_due_card_marks_the_warning_rows_only(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-due-warning-0")
    assert text(user, "dashboard-due-warning-0") == "警告"
    await user.should_not_see(marker="dashboard-due-warning-1")
    await user.should_not_see(marker="dashboard-due-warning-2")
    assert "text-negative" in user.find(marker="dashboard-due-1").elements.pop().classes


async def test_the_member_rows_are_not_shown_while_filtering(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.member = "田中"
    data.progress.by_member = []
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    await user.should_not_see(marker="dashboard-member-progress-田中")


async def test_the_team_card_scope_starts_with_the_member(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.member = "田中"
    views[0].show(data, PeriodKind.ALL)
    await user.should_see("田中・すべてのタスク")


async def test_without_members_the_select_has_only_everyone_and_no_member_section(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.members, data.progress.by_member = [], []
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    assert user.find(marker="dashboard-member").elements.pop().options == {"": "全員"}
    await user.should_not_see("メンバー別")


def cross_sample() -> Dashboard:
    data = sample()
    data.cross = CrossSummary(
        {
            "田中": CrossLoad(
                LoadStats(0.7, 1.2, 1),
                [ProjectLoad("A", 0.4, 0.6), ProjectLoad("B", 0.3, 0.6)],
            )
        },
        ["A", "B", "C"],
        {"C"},
        [LoadFailure("壊れた", "invalid")],
    )
    return data


def mount_cross() -> tuple[list[DashboardView], list[bool], list[tuple[str, bool]]]:
    views: list[DashboardView] = []
    crosses: list[bool] = []
    projects: list[tuple[str, bool]] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(
            lambda: None,
            lambda kind: None,
            None,
            crosses.append,
            lambda name, on: projects.append((name, on)),
        )
        views.append(view)
        view.build()

    return views, crosses, projects


async def test_the_cross_load_card_shows_the_total_and_the_project_breakdown(
    user: User,
) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert (
        text(user, "dashboard-load-田中") == "平均 70% / 最大 120% / 割り当て超過 1 日"
    )
    assert text(user, "dashboard-cross-detail-田中-0") == "A: 平均 40% / 最大 60%"
    assert text(user, "dashboard-cross-detail-田中-1") == "B: 平均 30% / 最大 60%"
    await user.should_see(marker="dashboard-cross-note")


async def test_the_cross_load_card_lists_failures_and_the_project_checks(
    user: User,
) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-cross-failure-0")
    assert (
        text(user, "dashboard-cross-failure-0")
        == "読み込めなかったファイル: 壊れた(invalid)"
    )
    assert user.find(marker="dashboard-cross-project-A").elements.pop().value is True
    assert user.find(marker="dashboard-cross-project-C").elements.pop().value is False


async def test_toggling_the_switch_and_a_project_check_calls_back(user: User) -> None:
    views, crosses, projects = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-cross-project-A")
    user.find(marker="dashboard-cross").elements.pop().set_value(False)
    user.find(marker="dashboard-cross-project-A").elements.pop().set_value(False)
    assert crosses == [False]
    assert projects == [("A", False)]


async def test_without_cross_the_load_card_is_unchanged_and_the_switch_is_off(
    user: User,
) -> None:
    views, crosses, _ = mount_cross()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert (
        text(user, "dashboard-load-田中") == "平均 50% / 最大 120% / 割り当て超過 2 日"
    )
    await user.should_not_see(marker="dashboard-cross-note")
    assert user.find(marker="dashboard-cross").elements.pop().value is False
    assert crosses == []  # 表示の同期では通知しない


def heat_summary(name: str = "田中", project: str = "A") -> CrossSummary:
    days = [
        DayLoad(date(2026, 10, 5), 0.0, []),
        DayLoad(date(2026, 10, 6), 0.6, [ProjectPeak(project, 0.6)]),
        DayLoad(
            date(2026, 10, 7), 1.2, [ProjectPeak(project, 0.6), ProjectPeak("B", 0.6)]
        ),
    ]
    loads = {name: CrossLoad(LoadStats(0.6, 1.2, 1), [], days)}
    return CrossSummary(loads, [project, "B"], set(), [])


def cell_of(markup: str, key: str) -> str:
    match = re.search(rf'<td[^>]*data-cell="{re.escape(key)}"[^>]*>', markup)
    assert match is not None, key
    return match.group(0)


def test_the_heatmap_has_a_cell_per_person_and_day_and_marks_overload() -> None:
    markup = heatmap_html(heat_summary())
    assert markup.count("data-cell=") == 3
    assert "heat-over" in cell_of(markup, "田中|2026-10-07")  # 120% は枠線つき
    assert "heat-over" not in cell_of(markup, "田中|2026-10-06")
    assert "transparent" in cell_of(markup, "田中|2026-10-05")  # 0% は塗りなし


def test_the_heatmap_cells_show_the_total_and_the_breakdown_on_hover() -> None:
    markup = heatmap_html(heat_summary())
    assert "田中 10/07(水) 120%&#10;A 60% / B 60%" in cell_of(markup, "田中|2026-10-07")
    assert "田中 10/05(月) 0%" in cell_of(markup, "田中|2026-10-05")


def test_the_heatmap_escapes_names() -> None:
    markup = heatmap_html(heat_summary(name='<b>"田&中', project="<i>"))
    assert "<b>" not in markup and "<i>" not in markup
    assert "&lt;b&gt;" in markup and "&lt;i&gt;" in markup


async def test_the_heatmap_card_is_shown_only_with_cross(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    await user.should_not_see(marker="dashboard-heatmap")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = heat_summary().loads["田中"]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-table")
    assert (
        "data-cell"
        in user.find(marker="dashboard-heatmap-table").elements.pop().content
    )


async def test_the_heatmap_card_says_so_when_there_are_no_workdays(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = CrossLoad(LoadStats(0.0, 0.0, 0), [], [])
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-empty")
    assert text(user, "dashboard-heatmap-empty") == "稼働日がありません"


def test_the_heatmap_cells_keep_the_fixed_styles_in_css_to_stay_small() -> None:
    cell = cell_of(heatmap_html(heat_summary()), "田中|2026-10-07")
    assert "width" not in cell and "outline" not in cell and "border" not in cell


def test_the_overload_outline_is_brighter_in_the_dark_theme() -> None:
    assert "body.body--dark .heat-over" in HEATMAP_CSS


async def test_the_heatmap_card_can_shrink_so_that_the_table_scrolls(
    user: User,
) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = heat_summary().loads["田中"]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap")
    assert (
        user.find(marker="dashboard-heatmap").elements.pop()._style.get("min-width")
        == "0"
    )


async def test_the_heatmap_table_wrapper_can_shrink_and_scrolls_by_itself(
    user: User,
) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = heat_summary().loads["田中"]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-table")
    style = user.find(marker="dashboard-heatmap-table").elements.pop()._style
    assert (
        style.get("min-width") == "0"
        and style.get("max-width") == "100%"
        and style.get("overflow-x") == "auto"
    )


def test_the_heatmap_scroller_has_an_always_visible_scrollbar_style() -> None:
    assert 'class="heatmap-scroll"' in heatmap_html(heat_summary())
    for rule in (
        "::-webkit-scrollbar {",
        "::-webkit-scrollbar-track",
        "::-webkit-scrollbar-thumb",
    ):
        assert f".heatmap-scroll{rule}" in HEATMAP_CSS


def long_heat_summary(count: int) -> CrossSummary:
    days = [
        DayLoad(date(2026, 10, 1) + timedelta(days=i), 0.5, []) for i in range(count)
    ]
    return CrossSummary(
        {"田中": CrossLoad(LoadStats(0.5, 0.5, 0), [], days)}, ["A"], set(), []
    )


async def test_the_heatmap_card_tells_that_a_wide_table_scrolls_sideways(
    user: User,
) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = sample()
    data.cross = long_heat_summary(HEATMAP_HINT_DAYS + 1)
    views[0].show(data, PeriodKind.ALL)
    await user.should_see(marker="dashboard-heatmap-hint")
    assert text(user, "dashboard-heatmap-hint") == "横にスクロールできます"


async def test_the_heatmap_card_has_no_scroll_hint_for_a_narrow_table(
    user: User,
) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = sample()
    data.cross = long_heat_summary(HEATMAP_HINT_DAYS)
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-table")
    await user.should_not_see(marker="dashboard-heatmap-hint")


def state(cards: tuple[CardId, ...]) -> ViewState:
    return ViewState(("標準",), "標準", False, None, cards, ())


async def test_cards_follow_the_view_order_and_skip_hidden_ones(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        sample(), PeriodKind.WEEK, view_state=state((CardId.DUE, CardId.HOURS))
    )
    await user.should_see(marker="dashboard-due-0")
    await user.should_see(marker="dashboard-hours-total")
    await user.should_not_see(marker="dashboard-progress-percent")
    await user.should_not_see(marker="dashboard-team")
    assert views[0].card_order == (
        CardId.DUE,
        CardId.HOURS,
    )  # 描く順は card_order のとおり


async def test_without_a_view_state_all_cards_show_in_the_default_order(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    assert views[0].card_order == DEFAULT_ORDER


def full_state(
    current: str = "標準",
    dirty: bool = False,
    save_block: str | None = None,
    names: tuple[str, ...] = ("標準", "月次"),
) -> ViewState:
    return ViewState(names, current, dirty, save_block, DEFAULT_ORDER, ())


def recording_actions(log: list) -> ViewActions:
    return ViewActions(
        select=lambda name: log.append(("select", name)),
        save=lambda: log.append("save"),
        save_as=lambda: log.append("save_as"),
        revert=lambda: log.append("revert"),
        rename=lambda: log.append("rename"),
        delete=lambda: log.append("delete"),
        move_card=lambda card_id, before: log.append(("move", card_id, before)),
        hide_card=lambda card_id: log.append(("hide", card_id)),
        show_card=lambda card_id: log.append(("show", card_id)),
    )


async def test_the_toolbar_shows_the_dirty_mark_and_save_buttons_only_when_dirty(
    user: User,
) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(dirty=False))
    await user.should_see(marker="dashboard-view")
    await user.should_see(
        marker="dashboard-view-save-as"
    )  # 名前をつけて保存は常に押せる(⋮ の中)
    await user.should_not_see(marker="dashboard-view-dirty")
    await user.should_not_see(marker="dashboard-view-save")
    assert views[0].save_as_item.enabled is True
    assert (
        views[0].revert_item.enabled is False
    )  # 元に戻すは、変更があるときだけ押せる(⋮ の中)
    views[0].show(
        sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True)
    )
    await user.should_see(marker="dashboard-view-dirty")
    await user.should_see(marker="dashboard-view-save")
    assert views[0].revert_item.enabled is True


async def test_the_toolbar_groups_the_view_controls_and_the_filters_in_one_box(
    user: User,
) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(
        sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True)
    )
    view = views[0]
    await user.should_see(marker="dashboard-view-group")
    group = set(user.find(marker="dashboard-view-group").elements.pop().descendants())
    top, bar, filters = (
        set(view.top_bar.descendants()),
        set(view.view_bar.descendants()),
        set(view.filter_bar.descendants()),
    )
    assert {
        view.view_select,
        view.dirty_mark,
        view.save_button,
        view.edit_button,
    } <= bar
    assert (
        view.save_as_item in bar and view.revert_item in bar
    )  # ⋮ の中のメニュー項目も
    assert {
        view.toggle,
        view.member_select,
        view.cross_switch,
        view.custom_field,
    } <= filters
    assert bar | filters <= group  # ビューの操作も条件も、同じ枠の中
    assert top.isdisjoint(group)  # 見出しと戻るは枠の外
    assert bar.isdisjoint(filters)
    back = user.find(marker="dashboard-back").elements.pop()
    assert back in top and back not in group


async def test_save_is_disabled_when_blocked(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(
        sample(),
        PeriodKind.WEEK,
        view_state=full_state(dirty=True, save_block="「標準」は上書きできません"),
    )
    await user.should_see(marker="dashboard-view-save")
    save = user.find(marker="dashboard-view-save").elements.pop()
    assert save.enabled is False


async def test_toolbar_buttons_call_the_actions(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(
        sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True)
    )
    await user.should_see(marker="dashboard-view-save")
    user.find(marker="dashboard-view-save").click()
    user.find(marker="dashboard-view-save-as").click()
    user.find(marker="dashboard-view-revert").click()
    assert log == ["save", "save_as", "revert"]


async def test_selecting_in_the_dropdown_calls_select_but_syncing_does_not(
    user: User,
) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state())
    await user.should_see(marker="dashboard-view")
    assert log == []  # show でプルダウンの値を合わせても、選択の通知は出ない
    views[0].view_select.set_value("月次")
    assert log == [("select", "月次")]


async def test_rename_and_delete_are_disabled_for_the_standard_view(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="標準"))
    assert (
        views[0].rename_item.enabled is False and views[0].delete_item.enabled is False
    )
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次"))
    assert views[0].rename_item.enabled is True and views[0].delete_item.enabled is True


async def test_edit_mode_shows_handles_and_hide_buttons_and_the_hidden_list(
    user: User,
) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    hidden_state = ViewState(
        ("標準",), "標準", False, None, (CardId.TEAM, CardId.DUE), (CardId.PROGRESS,)
    )
    views[0].show(sample(), PeriodKind.WEEK, view_state=hidden_state)
    await user.should_see(marker="dashboard-edit-toggle")
    await user.should_not_see(marker="dashboard-hide-team")  # ふだんは出さない
    user.find(marker="dashboard-edit-toggle").click()
    await user.should_see(marker="dashboard-hide-team")
    await user.should_see(marker="dashboard-hide-due")
    await user.should_see(marker="dashboard-hidden-progress")
    await user.should_see(marker="dashboard-drop-end")
    user.find(marker="dashboard-hide-due").click()
    user.find(marker="dashboard-hidden-progress").click()
    assert log == [("hide", CardId.DUE), ("show", CardId.PROGRESS)]
    user.find(marker="dashboard-edit-toggle").click()
    await user.should_not_see(marker="dashboard-hide-team")


async def test_a_move_event_calls_move_card_and_ignores_bad_arguments(
    user: User,
) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state())
    views[0].handle_move({"card": "due", "before": "team"})
    views[0].handle_move({"card": "due", "before": None})
    views[0].handle_move({"card": "nope", "before": None})
    views[0].handle_move("due")
    assert log == [("move", CardId.DUE, CardId.TEAM), ("move", CardId.DUE, None)]


def with_backlog(backlog: Backlog) -> Dashboard:
    data = sample()
    data.backlog = backlog
    return data


async def test_the_backlog_card_lists_the_team_rows(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        26.0,
        0,
        3,
        2.0,
        1.5,
        [("田中", 16.0)],
        by_team=[("開発", 16.0), ("チームなし", 10.0)],
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-team-開発")
    assert text(user, "dashboard-backlog-team-開発") == "開発 16.0h"
    assert text(user, "dashboard-backlog-team-チームなし") == "チームなし 10.0h"


async def test_the_backlog_card_hides_the_team_heading_without_team_rows(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-member-田中")
    await user.should_not_see("チーム別")


async def test_the_cards_note_the_weighting_only_when_a_team_is_selected(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)]))
    data.team_name = "開発"
    views[0].show(data, PeriodKind.WEEK)
    for key in ("load", "hours", "backlog"):
        await user.should_see(marker=f"dashboard-weighted-note-{key}")
    assert (
        text(user, "dashboard-weighted-note-backlog")
        == "チーム「開発」の所属の割合で按分しています"
    )


async def test_the_cards_do_not_note_the_weighting_without_a_team(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-hours")
    await user.should_not_see(marker="dashboard-weighted-note-backlog")


async def test_the_backlog_card_shows_hours_required_people_and_the_shortfall(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(19.5, 2, 3, 2.0, 1.5, [("田中", 13.0), (UNASSIGNED, 6.5)])
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-need")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 19.5h(遅れなし)"
    assert (
        text(user, "dashboard-backlog-unset") == "工数未設定 2 件(合計に入れていません)"
    )
    assert text(user, "dashboard-backlog-days") == "稼働 3 日で終える場合"
    assert text(user, "dashboard-backlog-need") == "必要 2.0 人"
    assert text(user, "dashboard-backlog-have") == "稼働できる人員 1.5 人"
    assert text(user, "dashboard-backlog-gap") == "あと 0.5 人"
    assert text(user, "dashboard-backlog-member-田中") == "田中 13.0h"
    assert text(user, f"dashboard-backlog-member-{UNASSIGNED}") == f"{UNASSIGNED} 6.5h"


async def test_the_backlog_card_shows_spare_people_when_supply_is_enough(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 0.5, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-gap")
    assert text(user, "dashboard-backlog-gap") == "余裕 1.0 人"
    await user.should_not_see(marker="dashboard-backlog-unset")


async def test_the_backlog_card_says_when_the_period_is_undecided(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(5.0, 0, None, None, 1.0, [])), PeriodKind.ALL)
    await user.should_see(marker="dashboard-backlog-nodays")
    assert (
        text(user, "dashboard-backlog-nodays")
        == "期間が決まらないため、必要な人数は出せません"
    )
    await user.should_not_see(marker="dashboard-backlog-need")


async def test_the_backlog_card_is_empty_without_effort(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(0.0, 0, 3, 0.0, 1.0, [])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-empty-backlog")


async def test_the_backlog_card_says_when_no_workday_is_left(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(5.0, 0, 0, None, 1.0, [])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-nodays")
    assert (
        text(user, "dashboard-backlog-nodays")
        == "期間がすでに終わっているため、必要な人数は出せません"
    )


async def test_the_backlog_card_says_just_right_instead_of_zero_point_zero(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(24.3, 0, 3, 1.0125, 1.0, [("田中", 24.3)])),
        PeriodKind.WEEK,
    )
    await user.should_see(marker="dashboard-backlog-gap")
    assert text(user, "dashboard-backlog-gap") == "ちょうど"
    assert (
        "text-negative"
        not in user.find(marker="dashboard-backlog-gap").elements.pop().classes
    )


async def test_the_backlog_card_explains_the_unit_of_people(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 0.5, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-unit")
    assert text(user, "dashboard-backlog-unit") == (
        "人は、100% の人に換算した数です。今日は、今から稼働の枠の終わりまでの残り時間で数えます。"
    )


async def test_the_rest_is_a_stacked_bar_by_status_without_the_text_row(
    user: User,
) -> None:
    from projectapp.dashboard_view import PIE_VARS

    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        20.0,
        0,
        3,
        20 / 19.5,
        1.5,
        [("田中", 20.0)],
        {Status.NOT_STARTED: 12.0, Status.RUNNING: 6.0, Status.PAUSED: 2.0},
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours-bar-not_started")
    await user.should_not_see(
        marker="dashboard-backlog-by-status"
    )  # 文字の内訳は出さない
    for status, width in (
        (Status.NOT_STARTED, "60.0%"),
        (Status.RUNNING, "30.0%"),
        (Status.PAUSED, "10.0%"),
    ):
        segment = (
            user.find(marker=f"dashboard-backlog-hours-bar-{status.name.lower()}")
            .elements.pop()
            ._style
        )
        assert segment["width"] == width
        assert (
            segment["background"] == f"var({PIE_VARS[status]})"
        )  # 円グラフと同じ状態色
    assert text(user, "dashboard-backlog-hours-legend-not_started") == "未着手"
    assert text(user, "dashboard-backlog-hours-legend-running") == "実行中"
    assert text(user, "dashboard-backlog-hours-legend-paused") == "一時停止"


async def test_the_status_bar_is_left_out_without_a_rest(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(0.0, 2, 3, 0.0, 1.5, [])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-unset")
    await user.should_not_see(marker="dashboard-backlog-hours-legend-not_started")


async def test_the_team_row_and_dropdown_show_for_everyone_and_report_team_changes(
    user: User,
) -> None:
    from projectapp.scope import team_key

    members: list[str | None] = []
    teams: list[str | None] = []
    views: list[DashboardView] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(
            lambda: None, lambda kind: None, members.append, on_team_change=teams.append
        )
        views.append(view)
        view.build()

    await user.open("/")
    data = sample()
    data.teams = ["開発"]
    data.progress.by_team = [
        MemberProgress(
            "開発",
            40.0,
            {
                Status.NOT_STARTED: 1,
                Status.RUNNING: 2,
                Status.PAUSED: 0,
                Status.DONE: 0,
            },
        )
    ]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-row-progress-開発")
    assert text(user, "dashboard-team-row-progress-開発") == "40% / 3件"
    select = user.find(marker="dashboard-member").elements.pop()
    assert select.options[team_key("開発")] == "チーム: 開発"
    select.set_value(team_key("開発"))
    assert teams == ["開発"] and members == []
    select.set_value("田中")
    assert members == ["田中"]


async def test_the_team_and_progress_cards_note_how_many_referenced_projects_are_counted(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.references = 2
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-references")
    assert text(user, "dashboard-team-references") == "参照先 2 件を含む"
    assert text(user, "dashboard-progress-references") == "参照先 2 件を含む"


async def test_the_cards_do_not_note_references_when_none_are_counted(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-done")
    await user.should_not_see(marker="dashboard-team-references")
    await user.should_not_see(marker="dashboard-progress-references")


async def test_the_backlog_card_shows_the_days_with_one_decimal(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(16.5, 0, 16.5 / 6.5, 1.0, 1.0, [("田中", 16.5)])),
        PeriodKind.WEEK,
    )
    await user.should_see(marker="dashboard-backlog-days")
    assert text(user, "dashboard-backlog-days") == "稼働 2.5 日で終える場合"


def mount_ticking() -> tuple[list[DashboardView], list[int]]:
    views: list[DashboardView] = []
    ticks: list[int] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(
            lambda: None, lambda kind: None, on_tick=lambda: ticks.append(1)
        )
        views.append(view)
        view.build()

    return views, ticks


async def test_the_tick_refreshes_only_while_shown_and_not_editing(user: User) -> None:
    views, ticks = mount_ticking()
    await user.open("/")
    view = views[0]
    view.tick()
    assert ticks == []  # まだ開いていない
    view.show(with_backlog(Backlog(6.5, 0, 1, 1.0, 1.0, [])), PeriodKind.WEEK)
    view.tick()
    assert ticks == [1]
    view.set_edit_mode(True)
    view.tick()
    assert ticks == [1]  # 編集モード中は更新しない
    view.set_edit_mode(False)
    view.hide()
    view.tick()
    assert ticks == [1]  # 隠したら止まる


async def test_the_backlog_card_notes_the_projects_it_overlays(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)]))
    data.cross = CrossSummary({}, ["A", "B", "C"], {"C"}, [])
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-cross-note")
    assert text(user, "dashboard-backlog-cross-note") == (
        "全 2 プロジェクトを重ねています。稼働時間と祝日は開いているプロジェクトの設定で数えます"
    )


async def test_the_backlog_card_has_no_overlay_note_for_one_project(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-hours")
    await user.should_not_see(marker="dashboard-backlog-cross-note")


async def test_the_backlog_card_shows_the_unadjusted_supply_only_when_it_changed(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    changed = Backlog(6.5, 0, 3, 0.5, 1.6, [("田中", 6.5)], nominal_supply=2.0)
    views[0].show(with_backlog(changed), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-supply-note")
    assert (
        text(user, "dashboard-backlog-supply-note")
        == "相対比率の合計 2.0 人 → 稼働を反映して 1.6 人"
    )
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 0.5, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-need")
    await user.should_not_see(marker="dashboard-backlog-supply-note")


def swatch_color(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop()._style["background"]


async def test_the_people_bars_carry_their_numbers_and_own_colors(user: User) -> None:
    from projectapp.dashboard_view import HAVE_COLOR, NEED_COLOR, PLANNED_COLOR

    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(19.5, 0, 3, 2.5, 2.0, [("田中", 13.0)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-need")
    assert (
        text(user, "dashboard-backlog-need") == "必要 2.5 人"
    )  # 数字は棒のすぐ上のラベルに出す
    assert text(user, "dashboard-backlog-have") == "稼働できる人員 2.0 人"
    assert (
        user.find(marker="dashboard-backlog-bar-need")
        .elements.pop()
        ._style["background"]
        == NEED_COLOR
    )
    assert (
        user.find(marker="dashboard-backlog-bar-have")
        .elements.pop()
        ._style["background"]
        == HAVE_COLOR
    )
    assert (
        len({NEED_COLOR, HAVE_COLOR, PLANNED_COLOR}) == 3
    )  # 予定の青・実績の緑と混ざらない
    await user.should_not_see(
        marker="dashboard-backlog-legend-late"
    )  # 遅れがなければ凡例は出さない


async def test_the_backlog_member_bars_use_the_need_color(user: User) -> None:
    from projectapp.dashboard_view import NEED_COLOR

    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(13, 0, 3, 2.0, 1.5, [("田中", 13.0)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-member-田中")
    bars = [e for e in user.find(marker="dashboard-backlog-member-bar-田中").elements]
    assert bars and bars[0]._style["background"] == NEED_COLOR


async def test_the_backlog_card_has_no_legend_when_no_people_are_shown(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, None, None, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-nodays")
    await user.should_not_see(marker="dashboard-backlog-bar-need")


async def test_the_headline_is_the_shortfall_and_the_late_row_shows_it_without_the_delay(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-gap")
    assert text(user, "dashboard-backlog-gap") == "あと 1.0 人"
    assert (
        text(user, "dashboard-backlog-hours")
        == "残りの工数 20.0h(うち遅れ 2 件・10.0h)"
    )
    assert text(user, "dashboard-backlog-late") == "遅れがなければ 余裕 1.0 人"
    assert "text-h6" in user.find(marker="dashboard-backlog-gap").elements.pop().classes


async def test_the_late_row_shows_how_much_room_the_delay_eats(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        20.0, 0, 2, 4.0, 5.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late")
    assert text(user, "dashboard-backlog-gap") == "余裕 1.0 人"
    assert text(user, "dashboard-backlog-late") == "遅れがなければ 余裕 3.0 人"


async def test_the_late_row_says_just_right_when_the_delay_was_the_only_load(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        20.0, 0, 2, 4.0, 2.0, [("田中", 20.0)], overdue_hours=20.0, overdue_count=1
    )  # 遅れがなければ必要 0
    assert backlog.shortfall_without_overdue == -2.0
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late")
    assert text(user, "dashboard-backlog-late").endswith("遅れがなければ 余裕 2.0 人")


async def test_the_late_part_has_no_people_without_a_period(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, None, None, 3.0, [], overdue_hours=10.0, overdue_count=2)
    views[0].show(with_backlog(backlog), PeriodKind.ALL)
    await user.should_see(marker="dashboard-backlog-hours")
    assert (
        text(user, "dashboard-backlog-hours")
        == "残りの工数 20.0h(うち遅れ 2 件・10.0h)"
    )
    await user.should_not_see(marker="dashboard-backlog-late")  # 人数は出せない
    assert (
        "text-h6" in user.find(marker="dashboard-backlog-hours").elements.pop().classes
    )  # 人数が出せないときは時間が見出し


async def test_the_need_bar_is_stacked_with_the_late_part_and_the_legend_names_it(
    user: User,
) -> None:
    from projectapp.dashboard_view import LATE_COLOR, NEED_COLOR

    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-bar-late")
    assert text(user, "dashboard-backlog-legend-late") == "うち遅れ"
    assert swatch_color(user, "dashboard-backlog-swatch-late") == LATE_COLOR
    need = user.find(marker="dashboard-backlog-bar-need").elements.pop()._style
    late = user.find(marker="dashboard-backlog-bar-late").elements.pop()._style
    assert need["background"] == NEED_COLOR and late["background"] == LATE_COLOR
    assert (
        need["width"] == "50.0%" and late["width"] == "50.0%"
    )  # 必要 4.0 人のうち遅れの分が 2.0 人


async def test_without_a_late_part_the_need_bar_is_a_single_segment(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(19.5, 0, 3, 2.0, 1.5, [("田中", 13.0)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-bar-need")
    await user.should_not_see(marker="dashboard-backlog-bar-late")
    await user.should_not_see(marker="dashboard-backlog-legend-late")


async def test_the_late_cover_says_when_nothing_is_late(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-hours")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 6.5h(遅れなし)"
    await user.should_not_see(marker="dashboard-backlog-late")


async def test_both_late_bases_are_selectable_and_the_current_one_is_filled(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-late-basis")
    delay = next(iter(user.find(marker="dashboard-backlog-late-delay").elements))
    warning = next(iter(user.find(marker="dashboard-backlog-late-warning").elements))
    assert delay.props.get("disable") is None and warning.props.get("disable") is None
    assert delay.text == "遅れのみ" and warning.text == "警告を含む"
    assert "outline" not in delay.props and "outline" in warning.props


async def test_the_warning_basis_button_is_filled_when_chosen(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], late_basis=LateBasis.WARNING
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    delay = next(iter(user.find(marker="dashboard-backlog-late-delay").elements))
    warning = next(iter(user.find(marker="dashboard-backlog-late-warning").elements))
    assert "outline" in delay.props and "outline" not in warning.props


async def test_pressing_the_other_basis_notifies_and_the_current_one_does_nothing(
    user: User,
) -> None:
    changes: list[LateBasis] = []
    views, _, _ = mount(late_basis_changes=changes)
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-late-basis")
    user.find(marker="dashboard-backlog-late-delay").click()
    assert changes == []
    user.find(marker="dashboard-backlog-late-warning").click()
    assert changes == [LateBasis.WARNING]


async def test_the_catch_up_choice_notifies_and_the_days_field_shows_only_for_task(
    user: User,
) -> None:
    changes: list[CatchUp] = []
    views, _, _ = mount(catch_up_changes=changes)
    await user.open("/")
    views[0].show(
        with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-catch-up")
    await user.should_not_see(marker="dashboard-backlog-catch-up-days")
    user.find(marker="dashboard-backlog-catch-up-period").click()
    assert changes == []
    user.find(marker="dashboard-backlog-catch-up-task").click()
    assert changes == [CatchUp(CatchUpMode.TASK, 5)]
    task = Backlog(
        6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], catch_up=CatchUp(CatchUpMode.TASK, 3)
    )
    views[0].show(with_backlog(task), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-catch-up-days")


def test_picking_a_catch_up_clamps_the_days_and_ignores_the_same_rule() -> None:
    seen: list[CatchUp] = []
    view = DashboardView(
        lambda: None, lambda kind: None, on_catch_up_change=seen.append
    )
    current = CatchUp(CatchUpMode.TASK, 5)
    view.pick_catch_up(CatchUp(CatchUpMode.TASK, 5), current)
    view.pick_catch_up(CatchUp(CatchUpMode.TASK, 999), current)
    view.pick_catch_up(CatchUp(CatchUpMode.TASK, 0), current)
    assert seen == [CatchUp(CatchUpMode.TASK, 60), CatchUp(CatchUpMode.TASK, 1)]


async def test_the_headline_lists_overdue_and_warning_separately(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    both = Backlog(
        20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=6.5, overdue_count=1,
        late_basis=LateBasis.WARNING, warning_hours=3.5, warning_count=2,
    )  # fmt: skip
    views[0].show(with_backlog(both), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    assert (
        text(user, "dashboard-backlog-hours")
        == "残りの工数 20.0h(うち遅れ 1 件・6.5h、警告 2 件・3.5h)"
    )
    only_warning = Backlog(
        20.0,
        0,
        2,
        4.0,
        3.0,
        [("田中", 20.0)],
        late_basis=LateBasis.WARNING,
        warning_hours=3.5,
        warning_count=2,
    )
    views[0].show(with_backlog(only_warning), PeriodKind.WEEK)
    await asyncio.sleep(0.3)  # 描き直しを待つ
    assert (
        text(user, "dashboard-backlog-hours") == "残りの工数 20.0h(うち警告 2 件・3.5h)"
    )
    clean = Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], late_basis=LateBasis.WARNING)
    views[0].show(with_backlog(clean), PeriodKind.WEEK)
    await asyncio.sleep(0.3)
    assert text(user, "dashboard-backlog-hours") == "残りの工数 6.5h(遅れなし)"


async def test_the_need_bar_has_a_warning_segment_and_legend_only_for_warnings(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    both = Backlog(
        20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=6.0, overdue_count=1,
        late_basis=LateBasis.WARNING, warning_hours=4.0, warning_count=1,
    )  # fmt: skip
    views[0].show(with_backlog(both), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-bar-warning")
    await user.should_see(marker="dashboard-backlog-bar-late")
    assert text(user, "dashboard-backlog-legend-warning") == "うち警告"
    assert text(user, "dashboard-backlog-legend-late") == "うち遅れ"
    assert text(user, "dashboard-backlog-late").startswith("遅れ・警告がなければ")
    delay = Backlog(
        20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=6.0, overdue_count=1
    )
    views[0].show(with_backlog(delay), PeriodKind.WEEK)
    await asyncio.sleep(0.3)
    await user.should_not_see(marker="dashboard-backlog-bar-warning")
    await user.should_not_see(marker="dashboard-backlog-legend-warning")
    assert text(user, "dashboard-backlog-late").startswith("遅れがなければ")


async def test_the_member_warning_count_has_a_tooltip_of_task_chips(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = warned_sample()
    data.progress.by_member[0] = MemberProgress(
        "田中",
        40.0,
        data.progress.by_member[0].counts,
        warnings=2,
        limit=3,
        warned_tasks=("設計", "実装"),
    )
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-warning-田中")
    chips = user.find(marker="dashboard-member-warning-chip-田中").elements
    assert sorted(c.text for c in chips) == ["実装", "設計"]


def unassigned_sample() -> Dashboard:
    data = sample()
    data.progress.unassigned = [
        UnassignedTask("a", "設計"),
        UnassignedTask("b", "試験"),
    ]
    return data


def mount_assign(picked: list[str]) -> list[DashboardView]:
    views: list[DashboardView] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(lambda: None, lambda kind: None, on_assign=picked.append)
        views.append(view)
        view.build()

    return views


async def test_unassigned_row_is_hidden_without_unassigned_tasks(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    await user.should_not_see(marker="dashboard-unassigned-count")


async def test_unassigned_chips_do_nothing_until_editing_is_enabled(
    user: User,
) -> None:
    picked: list[str] = []
    views = mount_assign(picked)
    await user.open("/")
    views[0].show(unassigned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-unassigned-count")
    assert text(user, "dashboard-unassigned-count") == "担当なし 2件"
    await user.should_not_see(marker="dashboard-unassigned-pick-0")
    views[0].assign("a")  # オフのときは通知しない
    assert picked == []


async def test_enabling_the_checkbox_makes_the_chips_pick_a_task(user: User) -> None:
    picked: list[str] = []
    views = mount_assign(picked)
    await user.open("/")
    views[0].show(unassigned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-unassigned-edit")
    user.find(marker="dashboard-unassigned-edit").click()
    await user.should_see(marker="dashboard-unassigned-pick-1")
    user.find(marker="dashboard-unassigned-pick-1").click()
    assert picked == ["b"]
    views[0].hide()
    assert views[0].assign_mode is False  # 閉じるとオフに戻る


def wide_heat_summary() -> CrossSummary:
    """10/30(金)・11/2(月)・11/3(火)・11/4(水)。11/3 は 2 人とも 100% 超、11/4 は 1 人だけ。"""
    days = [date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]

    def person(totals: list[float]) -> CrossLoad:
        return CrossLoad(
            LoadStats(0.5, 1.2, 1),
            [],
            [DayLoad(d, t, []) for d, t in zip(days, totals)],
        )

    loads = {"田中": person([0.5, 0.5, 1.2, 1.2]), "佐藤": person([0.0, 0.5, 1.5, 0.5])}
    return CrossSummary(loads, ["A"], set(), [])


def test_the_heatmap_head_has_a_month_band_and_day_numbers() -> None:
    markup = heatmap_html(wide_heat_summary())
    assert 'colspan="1">2026年10月</th>' in markup
    assert 'colspan="3">11月</th>' in markup
    assert "<div>30</div><div>金</div>" in markup


def test_the_heatmap_marks_the_start_of_a_month_and_of_a_week() -> None:
    markup = heatmap_html(wide_heat_summary())
    assert "heat-month" in cell_of(markup, "田中|2026-11-02")  # 月が替わる
    assert "heat-week" not in cell_of(markup, "田中|2026-11-02")
    assert "heat-month" not in cell_of(markup, "田中|2026-11-03")
    days = heat_summary()  # 10/5(月)〜10/7(水)。最初の列には印を付けない
    assert "heat-week" not in cell_of(heatmap_html(days), "田中|2026-10-05")
    week = heatmap_html(
        wide_heat_summary()
    )  # 金 → 月は週の替わりだが、月も替わるので月が優先
    assert "heat-week" not in cell_of(week, "田中|2026-11-02")


def test_the_heatmap_marks_a_week_start_inside_a_month() -> None:
    days = [date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12)]
    loads = {
        "田中": CrossLoad(LoadStats(0, 0, 0), [], [DayLoad(d, 0.0, []) for d in days])
    }
    markup = heatmap_html(CrossSummary(loads, ["A"], set(), []))
    assert "heat-week" in cell_of(markup, "田中|2026-10-12")
    assert "heat-week" not in cell_of(markup, "田中|2026-10-09")


def test_the_heatmap_marks_todays_column() -> None:
    markup = heatmap_html(wide_heat_summary(), today=date(2026, 11, 3))
    assert "heat-today" in cell_of(markup, "田中|2026-11-03")
    assert "heat-today" not in cell_of(markup, "田中|2026-11-04")
    assert "heat-today-head" in markup
    assert "heat-today" not in heatmap_html(wide_heat_summary())


def test_the_heatmap_counts_people_over_100_percent_per_day() -> None:
    markup = heatmap_html(wide_heat_summary())
    assert "100%超の人数" in markup
    assert 'title="11/03 100%超 2人">2</th>' in markup
    assert 'title="11/04 100%超 1人">1</th>' in markup
    assert 'title="11/02 100%超 0人"></th>' in markup  # 0 人は空欄


def test_the_heatmap_head_rows_stay_in_place_while_scrolling() -> None:
    for rule in (".heat-r1 { top: 0", ".heat-r2 { top: 18px", ".heat-r3 { top: 48px"):
        assert rule in HEATMAP_CSS
    assert "max-height" in HEATMAP_CSS


def test_scroll_to_today_js_looks_for_the_today_mark() -> None:
    script = scroll_to_today_js(7)
    assert "getElementById(7)" in script and ".heat-today" in script


async def test_each_card_has_a_maximize_button_and_it_shows_only_that_card(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-maximize-load")
    await user.should_see(marker="dashboard-progress")
    user.find(marker="dashboard-maximize-load").click()
    await user.should_not_see(marker="dashboard-progress")
    await user.should_see(marker="dashboard-load")
    await user.should_see(marker="dashboard-restore")
    assert views[0].maximized is CardId.LOAD


async def test_the_restore_button_and_restore_bring_back_all_cards(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-maximize-load")
    user.find(marker="dashboard-maximize-load").click()
    await user.should_see(marker="dashboard-restore")
    user.find(marker="dashboard-restore").click()
    await user.should_see(marker="dashboard-progress")
    assert views[0].maximized is None
    assert views[0].restore() is False  # 最大化していなければ何もしない
    views[0].set_maximized(CardId.LOAD)
    assert views[0].restore() is True and views[0].maximized is None


async def test_the_maximized_card_is_sized_to_the_screen_and_scrolls_by_itself(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    views[0].set_maximized(CardId.LOAD)
    await user.should_see(marker="dashboard-load")
    style = user.find(marker="dashboard-load").elements.pop()._style
    assert "--app-vh" in style["height"] and style["overflow-y"] == "auto"


async def test_editing_cards_clears_the_maximize_and_hides_the_buttons(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    views[0].set_maximized(CardId.LOAD)
    user.find(marker="dashboard-edit-toggle").click()
    await user.should_see(marker="dashboard-hide-team")
    assert views[0].maximized is None
    await user.should_not_see(marker="dashboard-maximize-load")


async def test_hiding_the_dashboard_clears_the_maximize(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    views[0].set_maximized(CardId.LOAD)
    views[0].hide()
    assert views[0].maximized is None


def test_the_maximized_card_keeps_its_children_from_shrinking_so_bars_stay_visible() -> (
    None
):
    assert ".dash-maximized > * { flex-shrink: 0 }" in HEATMAP_CSS


def test_the_heatmap_follows_the_given_order_and_marks_late_counts() -> None:
    cross = wide_heat_summary()
    markup = heatmap_html(
        cross, order=["佐藤"], counts={"佐藤": (2, 1), "田中": (5, 5)}
    )
    assert 'data-cell="佐藤|' in markup and 'data-cell="田中|' not in markup
    assert '<span class="heat-late">遅れ 2</span>' in markup
    assert '<span class="heat-warn">警告 1</span>' in markup
    names = heatmap_html(cross, order=["佐藤", "田中"])
    assert names.index("佐藤|") < names.index("田中|")
    assert "heat-badges" not in names  # 件数がなければ出さない


def test_the_heatmap_names_ask_to_filter_the_dashboard_when_clicked() -> None:
    markup = heatmap_html(wide_heat_summary())
    assert "emitEvent('dashboard_member', this.dataset.name)" in markup
    assert 'data-name="田中"' in markup
    escaped = heatmap_html(heat_summary(name='<b>"田'))
    assert "<b>" not in escaped


async def test_the_load_card_sorts_filters_and_shows_late_counts(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.loads["佐藤"] = LoadStats(0.9, 1.0, 0)
    data.loads["高橋"] = LoadStats(1.0, 2.0, 4)
    data.members.append("高橋")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-late-田中")
    assert text(user, "dashboard-load-late-田中") == "遅れ 1 件"
    await user.should_not_see(marker="dashboard-load-late-佐藤")

    def order() -> list[str]:
        """画面にある人の名前の行を、作られた順(= 並び順)で返す。"""
        found = {}
        for name in ("佐藤", "田中", "高橋"):
            try:
                found[name] = (
                    user.find(marker=f"dashboard-load-name-{name}").elements.pop().id
                )
            except AssertionError:  # 絞り込みで外れた人は画面にいない
                continue
        return sorted(found, key=found.__getitem__)

    assert sorted(order()) == ["佐藤", "田中", "高橋"]
    views[0].set_order(sort_by_load=True)
    await asyncio.sleep(0.2)
    assert order() == ["高橋", "田中", "佐藤"]
    views[0].set_order(over_only=True)
    await asyncio.sleep(0.2)
    assert order() == ["高橋", "田中"]


async def test_the_load_card_says_so_when_nobody_is_over(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.loads = {"佐藤": LoadStats(0.0, 0.0, 0)}
    views[0].show(data, PeriodKind.WEEK)
    views[0].set_order(over_only=True)
    await user.should_see(marker="dashboard-load-none")


async def test_clicking_a_name_filters_the_dashboard_to_that_person_and_back(
    user: User,
) -> None:
    changes: list[str | None] = []
    views, _, _ = mount(member_changes=changes)
    await user.open("/")
    data = sample()
    views[0].show(data, PeriodKind.WEEK)
    views[0].pick_member("田中")
    data.member = "田中"
    views[0].pick_member("田中")  # 同じ人をもう一度 → 全員
    views[0].pick_member("存在しない人")
    views[0].pick_member(123)
    assert changes == ["田中", None]


def test_sort_and_filter_are_not_kept_when_the_dashboard_is_hidden() -> None:
    view = DashboardView(lambda: None, lambda kind: None)
    view.sort_by_load = view.over_only = True
    view.hide()
    assert not view.sort_by_load and not view.over_only


def test_the_overload_red_gets_darker_as_the_load_grows() -> None:
    from projectapp.dashboard_view import cell_style

    def alpha(total: float) -> float:
        return float(cell_style(total).rsplit(",", 1)[1].strip(" )"))

    assert alpha(1.2) < alpha(1.5) < alpha(2.0) < alpha(3.0)
    assert alpha(3.0) == alpha(4.0) == 1.0  # 300% 以上は同じ濃さ


def test_the_heatmap_legend_shows_the_overload_steps() -> None:
    from projectapp.dashboard_view import legend_html

    legend = legend_html()
    for label in ("120%", "200%", "300%以上"):
        assert label in legend


async def test_the_load_summary_counts_the_people_over_100_percent(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)  # 田中 120%(2 日)、佐藤 0%
    await user.should_see(marker="dashboard-load-summary")
    assert (
        text(user, "dashboard-load-summary")
        == "割り当て超過 1 名 / 2 名・最大 120%(田中)"
    )


async def test_the_load_summary_leaves_out_the_max_when_nobody_is_over(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.loads = {"佐藤": LoadStats(0.5, 0.9, 0)}
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-summary")
    assert text(user, "dashboard-load-summary") == "割り当て超過 0 名 / 1 名"


async def test_the_load_bars_use_a_fixed_range_with_a_100_percent_line(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    from projectapp.dashboard_view import LOAD_SCALE

    assert LOAD_SCALE == 2.0
    styles = [
        e._style.get("left")
        for e in user.client.elements.values()
        if e._style.get("border-left", "").startswith("2px dotted")
    ]
    assert "50.0%" in styles  # 100% の線は、範囲の真ん中


DELTA_PERIOD = Period(date(2026, 10, 5), date(2026, 10, 11))


def delta(
    percent: float | None = 12.4,
    scope: float = 6.0,
    known: bool = True,
    since: date | None = date(2026, 10, 1),
) -> ProgressDelta:
    return ProgressDelta(DELTA_PERIOD, percent, scope, known, since, 2)


def test_delta_line_shows_the_gain_the_previous_period_and_the_scope() -> None:
    assert delta_line(delta(), delta(8.2)) == "進んだ分 +12%(前の期間 +8%)  範囲 +6.0h"


def test_delta_line_omits_what_is_missing() -> None:
    assert delta_line(delta(scope=0.0), None) == "進んだ分 +12%"
    assert delta_line(delta(), delta(None, known=False)) == "進んだ分 +12%  範囲 +6.0h"
    assert delta_line(delta(-3.2, scope=-2.0), None) == "進んだ分 -3%  範囲 -2.0h"
    assert delta_line(delta(0.2, scope=0.0), None) == "進んだ分 +0%"


def test_delta_line_says_unknown_instead_of_zero() -> None:
    assert (
        delta_line(delta(None, known=False), None)
        == "進んだ分: 履歴は 10/01 から(それ以前は不明)"
    )
    assert (
        delta_line(delta(None, known=False, since=None), None)
        == "進んだ分: 履歴はまだありません"
    )
    assert delta_line(delta(None), None) == "進んだ分: 対象のタスクなし  範囲 +6.0h"


async def test_the_team_card_shows_the_delta_line(user: User) -> None:
    views, _, _ = mount()
    data = sample()
    data.delta, data.previous_delta = delta(), delta(8.2)
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-delta")
    assert (
        text(user, "dashboard-team-delta") == "進んだ分 +12%(前の期間 +8%)  範囲 +6.0h"
    )


async def test_the_team_card_has_no_delta_line_for_the_whole_period(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.ALL)
    await user.should_not_see(marker="dashboard-team-delta")


def burndown_sample(**changes: object) -> Burndown:
    base = Burndown(
        first=date(2026, 10, 5),
        last=date(2026, 10, 11),
        known=True,
        since=date(2026, 9, 28),
        count=3,
        initial=14.0,
        actual=(14.0, 15.0, 10.0),
        planned=(10.0, 6.0, 2.0, 0.0, 0.0, 0.0, 0.0),
        future=(10.0, 6.0, 3.0, 0.0, 0.0),
        workdays=(True, True, True, True, True, False, False),
        today_index=2,
        now_fraction=0.5,
        marks=(Mark(date(2026, 10, 6), ("A",)),),
        unset=("走るタスク",),
        rest=10.0,
        required=5.0,
        recent=2.8,
        recent_days=10,
        behind=True,
    )
    return replace(base, **changes)


def line_texts(b: Burndown) -> dict[str, str]:
    return {line.key: line.text for line in burndown_lines(b)}


def test_burndown_lines_for_a_period_in_progress() -> None:
    texts = line_texts(burndown_sample())
    assert texts["end"] == "期間の終わりの予定の残り 0.0h(今日の実際 10.0h)"
    assert (
        texts["pace"]
        == "必要なペース 5.0h/稼働日(10/11 までに 10.0h 減らす)・直近 10 稼働日のペース 2.8h/稼働日"
    )
    assert texts["behind"] == "ペースを上げるか、予定を見直す必要があります"
    assert "ahead" not in texts
    assert texts["unset"] == "進捗度なしの実行中・一時停止 1 件(終了まで減りません)"


def test_burndown_lines_when_ahead_or_without_a_recent_pace() -> None:
    texts = line_texts(
        burndown_sample(behind=False, ahead=True, recent=None, recent_days=0, unset=())
    )
    assert texts["ahead"] == "予定より進んでいます"
    assert texts["pace"].endswith("・直近のペースが出ていません")
    assert "unset" not in texts and "behind" not in texts


def test_burndown_lines_without_a_required_pace_still_say_ahead() -> None:
    texts = line_texts(
        burndown_sample(required=None, rest=0.0, behind=False, ahead=True)
    )
    assert "pace" not in texts and texts["ahead"] == "予定より進んでいます"


def test_burndown_lines_before_and_after_the_period() -> None:
    before = line_texts(
        burndown_sample(
            today_index=None,
            future=(),
            actual=(),
            required=None,
            behind=False,
            unset=(),
        )
    )
    assert before["end"] == "期間の始めの残り 14.0h(予定どおりなら終わりに 0.0h)"
    after = line_texts(
        burndown_sample(
            today_index=None,
            future=(),
            actual=(14.0,) * 6 + (9.0,),
            required=None,
            behind=False,
            unset=(),
        )
    )
    assert after["end"] == "期間の終わりの実際の残り 9.0h(予定 0.0h)"


def test_burndown_lines_say_what_is_unknown() -> None:
    assert (
        line_texts(
            Burndown(date(2026, 10, 5), date(2026, 10, 11), False, date(2026, 10, 7))
        )["unknown"]
        == "履歴は 10/07 から(それ以前は不明)"
    )
    assert (
        line_texts(Burndown(date(2026, 10, 5), date(2026, 10, 11), False, None))[
            "unknown"
        ]
        == "履歴はまだありません"
    )


def test_the_new_card_follows_the_backlog_card_by_default() -> None:
    order = list(DEFAULT_ORDER)
    assert order.index(CardId.BURNDOWN) == order.index(CardId.BACKLOG) + 1


def test_a_saved_view_from_before_the_card_has_it_hidden() -> None:
    old = tuple(c for c in DEFAULT_ORDER if c is not CardId.BURNDOWN)
    assert CardId.BURNDOWN in hidden_cards(old)


async def test_the_burndown_card_draws_the_chart_and_the_lines(user: User) -> None:
    views, _, _ = mount()
    data = sample()
    data.burndown = burndown_sample()
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-burndown-chart")
    content = user.find(marker="dashboard-burndown-chart").elements.pop().content
    assert content.startswith("<svg") and content.count("<polyline") == 3
    assert (
        text(user, "dashboard-burndown-behind")
        == "ペースを上げるか、予定を見直す必要があります"
    )
    await user.should_see(marker="dashboard-burndown-behind-icon")


async def test_the_burndown_card_names_the_range_for_the_whole_period(
    user: User,
) -> None:
    views, _, _ = mount()
    data = sample()
    data.burndown = replace(burndown_sample(), whole=True)
    await user.open("/")
    views[0].show(data, PeriodKind.ALL)
    await user.should_see(marker="dashboard-burndown-chart")
    assert (
        text(user, "dashboard-burndown-scope")
        == "すべてのタスク・履歴のある期間 10/05〜10/11"
    )


async def test_the_burndown_card_is_empty_without_a_burndown(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.ALL)
    await user.should_see(marker="dashboard-empty-burndown")
    await user.should_not_see(marker="dashboard-burndown-chart")


async def test_the_burndown_card_says_unknown_instead_of_drawing(user: User) -> None:
    views, _, _ = mount()
    data = sample()
    data.burndown = Burndown(
        date(2026, 10, 5), date(2026, 10, 11), False, date(2026, 10, 7)
    )
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-burndown-unknown")
    assert (
        text(user, "dashboard-burndown-unknown") == "履歴は 10/07 から(それ以前は不明)"
    )
    await user.should_not_see(marker="dashboard-burndown-chart")


async def test_the_burndown_card_is_empty_without_tasks(user: User) -> None:
    views, _, _ = mount()
    data = sample()
    data.burndown = burndown_sample(count=0)
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-empty-burndown")
    await user.should_not_see(marker="dashboard-burndown-chart")


async def test_the_burndown_card_shows_the_period_apart_from_the_title(
    user: User,
) -> None:
    views, _, _ = mount()
    data = sample()
    data.member = "田中"
    data.burndown = burndown_sample()
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see("残りの工数の推移")
    await user.should_see(marker="dashboard-burndown-scope")
    assert text(user, "dashboard-burndown-scope") == "田中・10/05〜10/11 にかかるタスク"
    await user.should_not_see("残りの工数の推移(")


async def test_a_member_row_shows_the_progress_made(user: User) -> None:
    views, _, _ = mount()
    data = sample()
    data.progress.by_member[0] = replace(data.progress.by_member[0], delta=12.4)
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-delta-田中")
    assert text(user, "dashboard-member-delta-田中") == "進んだ分 +12%"


async def test_a_member_row_without_a_delta_shows_nothing(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_not_see(marker="dashboard-member-delta-田中")


# --- 要望 130: 追加人数と、取り戻せる日 ----------------------------------------


def recovery_backlog(
    people: float,
    recovery: Recovery | None,
    mode: CatchUpMode = CatchUpMode.PERIOD,
    overdue: float = 0.0,
) -> Backlog:
    return Backlog(
        6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], overdue_hours=overdue,
        overdue_count=1 if overdue else 0,
        catch_up=CatchUp(mode, 5, people), recovery=recovery,
    )  # fmt: skip


async def test_the_people_field_is_shown_even_with_zero_people(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(recovery_backlog(0, None)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-recover-people")
    field = user.find(marker="dashboard-backlog-recover-people").elements.pop()
    assert field.value == 0


async def test_the_people_field_shows_the_current_value(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(recovery_backlog(2.5, None)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-recover-people")
    field = user.find(marker="dashboard-backlog-recover-people").elements.pop()
    assert field.value == 2.5


async def test_switching_the_mode_keeps_the_added_people(user: User) -> None:
    changes: list[CatchUp] = []
    views, _, _ = mount(catch_up_changes=changes)
    await user.open("/")
    views[0].show(with_backlog(recovery_backlog(2.0, None)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-catch-up")
    user.find(marker="dashboard-backlog-catch-up-task").click()
    assert changes == [CatchUp(CatchUpMode.TASK, 5, 2.0)]


def test_picking_clamps_the_people_to_zero_to_twenty_in_tenths() -> None:
    seen: list[CatchUp] = []
    view = DashboardView(
        lambda: None, lambda kind: None, on_catch_up_change=seen.append
    )
    current = CatchUp()
    view.pick_catch_up(CatchUp(people=99), current)
    view.pick_catch_up(CatchUp(people=-3), CatchUp(people=1))
    view.pick_catch_up(CatchUp(people=1.26), current)
    assert [rule.people for rule in seen] == [20.0, 0.0, 1.3]


async def test_the_recovery_line_gives_the_date_and_the_working(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    recovery = Recovery(2.0, 26.0, 2.0, date(2026, 11, 20), date(2026, 11, 27))
    views[0].show(
        with_backlog(recovery_backlog(2.0, recovery, overdue=26.0)), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-recovery")
    line = text(user, "dashboard-backlog-recovery")
    assert "追加 2.0 人で 11/20 に取り戻せます" in line
    assert "遅れ 26.0h ÷ 2.0 人 = 1 人あたり 13.0h・約 2.0 稼働日" in line
    assert "期間の終わり(11/27)に間に合います" in line
    await user.should_see(marker="dashboard-backlog-recovery-note")


async def test_the_recovery_line_says_when_the_period_end_is_missed(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    recovery = Recovery(1.0, 26.0, 4.0, date(2026, 12, 3), date(2026, 11, 27))
    views[0].show(
        with_backlog(recovery_backlog(1.0, recovery, overdue=26.0)), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-recovery")
    assert "期間の終わり(11/27)に間に合いません" in text(
        user, "dashboard-backlog-recovery"
    )


async def test_the_per_task_mode_shows_the_date_without_comparing(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    recovery = Recovery(2.0, 26.0, 2.0, date(2026, 11, 20), None)
    views[0].show(
        with_backlog(recovery_backlog(2.0, recovery, CatchUpMode.TASK, overdue=26.0)),
        PeriodKind.WEEK,
    )
    await user.should_see(marker="dashboard-backlog-recovery")
    line = text(user, "dashboard-backlog-recovery")
    assert "11/20 に取り戻せます" in line and "間に合" not in line


async def test_no_late_work_is_explained(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(recovery_backlog(2.0, None)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-recovery")
    assert text(user, "dashboard-backlog-recovery") == "遅れはありません"


async def test_a_missing_date_is_explained(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    none_found = Recovery(2.0, 26.0, 2.0, None, None)
    views[0].show(
        with_backlog(recovery_backlog(2.0, none_found, overdue=26.0)), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-recovery")
    assert "取り戻せる日を出せません" in text(user, "dashboard-backlog-recovery")


async def test_nothing_is_shown_for_zero_people(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(recovery_backlog(0, None)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-catch-up")
    await user.should_not_see(marker="dashboard-backlog-recovery")
    await user.should_not_see(marker="dashboard-backlog-recovery-note")


# --- 要望 131: 投入の候補 --------------------------------------------------------

CANDIDATES = [
    Candidate("鈴木", 16.5, 1.0),
    Candidate("田中", 3.0, 1.0),
    Candidate("佐藤", -2.0, 1.0),
]


def invest_backlog(
    invest: tuple[str, ...] = (),
    investment: Investment | None = None,
    overdue: float = 26.0,
    candidates: list[Candidate] | None = None,
) -> Backlog:
    return Backlog(
        30.0, 0, 3, 1.0, 1.5, [("田中", 30.0)], overdue_hours=overdue,
        overdue_count=1 if overdue else 0,
        catch_up=CatchUp(CatchUpMode.PERIOD, 5, 1.5, invest),
        candidates=CANDIDATES if candidates is None else candidates,
        investment=investment,
    )  # fmt: skip


async def test_candidates_are_listed_with_their_spare_and_a_member_without_spare_is_disabled(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(invest_backlog()), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-candidate-鈴木")
    assert user.find(marker="dashboard-backlog-candidate-鈴木").elements.pop().text == (
        "鈴木  余力 16.5h"
    )
    assert user.find(marker="dashboard-backlog-candidate-田中").elements.pop().text == (
        "田中  余力 3.0h"
    )
    none = user.find(marker="dashboard-backlog-candidate-佐藤").elements.pop()
    assert none.text == "佐藤  余力なし" and not none.enabled


async def test_ticking_a_candidate_notifies_the_new_rule_keeping_the_rest(
    user: User,
) -> None:
    changes: list[CatchUp] = []
    views, _, _ = mount(catch_up_changes=changes)
    await user.open("/")
    views[0].show(with_backlog(invest_backlog(("鈴木",))), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-candidate-田中")
    user.find(marker="dashboard-backlog-candidate-田中").elements.pop().set_value(True)
    assert changes == [CatchUp(CatchUpMode.PERIOD, 5, 1.5, ("鈴木", "田中"))]


async def test_unticking_a_candidate_removes_only_that_member(user: User) -> None:
    changes: list[CatchUp] = []
    views, _, _ = mount(catch_up_changes=changes)
    await user.open("/")
    views[0].show(with_backlog(invest_backlog(("鈴木", "田中"))), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-candidate-鈴木")
    user.find(marker="dashboard-backlog-candidate-鈴木").elements.pop().set_value(False)
    assert changes == [CatchUp(CatchUpMode.PERIOD, 5, 1.5, ("田中",))]


async def test_the_investment_line_gives_the_date_and_whether_the_period_end_holds(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    investment = Investment(
        ("鈴木", "田中"), 19.5, 18.0, date(2026, 11, 13), date(2026, 11, 15)
    )
    views[0].show(
        with_backlog(invest_backlog(("鈴木", "田中"), investment)), PeriodKind.WEEK
    )
    await user.should_see(marker="dashboard-backlog-invest")
    line = text(user, "dashboard-backlog-invest")
    assert "鈴木・田中を投入すると 11/13 に取り戻せます" in line
    assert "余力の合計 19.5h ≥ 遅れ 18.0h" in line
    assert "期間の終わり(11/15)に間に合います" in line


async def test_the_investment_line_says_when_the_period_end_is_missed(
    user: User,
) -> None:
    views, _, _ = mount()
    await user.open("/")
    investment = Investment(
        ("鈴木",), 19.5, 18.0, date(2026, 11, 20), date(2026, 11, 15)
    )
    views[0].show(with_backlog(invest_backlog(("鈴木",), investment)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-invest")
    assert "期間の終わり(11/15)に間に合いません" in text(
        user, "dashboard-backlog-invest"
    )


async def test_the_investment_line_reports_a_spare_shortage(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    investment = Investment(("田中",), 3.0, 26.0, None, None)
    views[0].show(with_backlog(invest_backlog(("田中",), investment)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-invest")
    line = text(user, "dashboard-backlog-invest")
    assert "選んだ人の余力 3.0h では、遅れ 26.0h のうち 3.0h しか取り戻せません" in line
    assert "残り 23.0h" in line


async def test_a_missing_date_with_enough_spare_is_explained(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    investment = Investment(("鈴木",), 30.0, 26.0, None, None)
    views[0].show(with_backlog(invest_backlog(("鈴木",), investment)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-invest")
    assert "取り戻せる日を出せません" in text(user, "dashboard-backlog-invest")


async def test_candidates_are_hidden_when_nothing_is_late(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(invest_backlog(overdue=0.0)), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-catch-up")
    await user.should_not_see(marker="dashboard-backlog-candidate-鈴木")


async def test_candidates_are_hidden_without_any_candidate(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(invest_backlog(candidates=[])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-catch-up")
    await user.should_not_see(marker="dashboard-backlog-candidates")


async def test_the_try_on_gantt_button_needs_a_chosen_person(user: User) -> None:
    tried: list[tuple[str, ...]] = []
    views, _, _ = mount(try_changes=tried)
    await user.open("/")
    views[0].show(with_backlog(invest_backlog()), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-candidates")
    await user.should_not_see(marker="dashboard-backlog-try-gantt")  # 選んでいない
    views[0].show(with_backlog(invest_backlog(("鈴木",))), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-try-gantt")
    user.find(marker="dashboard-backlog-try-gantt").click()
    assert tried == [("鈴木",)]
