import asyncio
import re
from datetime import date, datetime, timedelta

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import (
    Backlog,
    CrossLoad,
    CrossSummary,
    DayLoad,
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
    TeamProgress,
    WorkloadRow,
)
from projectapp.dashboard_views import DEFAULT_ORDER, CardId, ViewState
from projectapp.dashboard_view import HEATMAP_CSS, ViewActions, HEATMAP_HINT_DAYS, MAX_TIP_CHIPS, DashboardView, heatmap_html, percent_width
from projectapp.models import Status


def sample() -> Dashboard:
    return Dashboard(
        Period(date(2026, 10, 5), date(2026, 10, 11)),
        Progress(
            42.4,
            {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 3},
            [OverdueRow("遅れた作業", "田中", datetime(2026, 10, 6, 17), ("田中",))],
            [
                MemberProgress("田中", 40.0, {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 0}),
                MemberProgress("佐藤", None, {status: 0 for status in Status}),
            ],
        ),
        {"田中": LoadStats(0.5, 1.2, 2), "佐藤": LoadStats(0.0, 0.0, 0)},
        [WorkloadRow("田中", 9.5, 3.0), WorkloadRow("佐藤", 0.0, 0.0), WorkloadRow(UNASSIGNED, 6.5, 0.0)],
        [
            DueRow(datetime(2026, 10, 8, 17), "締切", "設計", "田中", False, False, ("田中",)),
            DueRow(datetime(2026, 10, 9, 12), "完了予定", "遅れ", None, True),
        ],
        TeamProgress(
            42.4,
            {Status.NOT_STARTED: 0.0, Status.RUNNING: 3.0, Status.PAUSED: 0.0, Status.DONE: 1.0},
            counts={Status.NOT_STARTED: 0, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 1},
            tasks={Status.NOT_STARTED: [], Status.RUNNING: ["設計", "実装"], Status.PAUSED: [], Status.DONE: ["調査"]},
        ),
        None,
        ["田中", "佐藤"],
    )


def empty() -> Dashboard:
    day = Period(date(2026, 10, 7), date(2026, 10, 7))
    return Dashboard(day, Progress(None, {status: 0 for status in Status}, []), {}, [], [])


def mount(
    member_changes: list[str | None] | None = None,
    actions: ViewActions | None = None,
    late_basis_changes: list[LateBasis] | None = None,
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
            on_late_basis_change=late_basis_changes.append if late_basis_changes is not None else None,
        )
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
    assert label.text == "平均 50% / 最大 120% / 割り当て超過 2 日"
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
    assert user.find(marker="dashboard-load-icon-佐藤").elements.pop().text == "佐"  # アイコンのない人は頭文字の丸


async def test_the_load_card_shows_the_initial_when_no_icon_is_given(user: User) -> None:
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
    assert user.find(marker="dashboard-backlog-member-icon-田中").elements.pop().text == "田"
    await user.should_not_see(marker="dashboard-backlog-member-icon-未割り当て")  # メンバーでない行には出さない
    await user.should_see(marker="dashboard-overdue-assignee-0")
    row = user.find(marker="dashboard-overdue-assignee-0").elements.pop()
    assert [c.text for c in row.descendants() if getattr(c, "text", None)] == ["田", "田中"]  # 頭文字の丸と名前
    await user.should_see(marker="dashboard-hours-icon-田中")
    await user.should_see(marker="dashboard-due-assignee-0")


def test_the_heatmap_names_have_an_icon_or_initial(icon: str) -> None:
    cross = long_heat_summary(2)
    assert ">田</span>田中" in heatmap_html(cross)
    with_icon = heatmap_html(cross, {"田中": icon})
    assert "<img" in with_icon and ">田</span>" not in with_icon


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


async def test_the_member_select_lists_everyone_and_the_members_and_reports_changes(user: User) -> None:
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
    counts = {Status.NOT_STARTED: 0, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 0}
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


async def test_member_and_team_rows_show_the_warning_count_only_when_there_is_one(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-warning-田中")
    assert text(user, "dashboard-member-warning-田中") == "警告 3 件"
    assert text(user, "dashboard-team-row-warning-甲") == "警告 5 件"
    await user.should_not_see(marker="dashboard-member-warning-高橋")


async def test_a_member_at_the_limit_is_highlighted_and_others_are_not(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-limit-田中")
    await user.should_not_see(marker="dashboard-member-limit-鈴木")
    await user.should_not_see(marker="dashboard-member-limit-佐藤")
    await user.should_not_see(marker="dashboard-member-limit-高橋")
    assert "text-weight-bold" in user.find(marker="dashboard-member-warning-田中").elements.pop().classes
    assert "text-weight-bold" not in user.find(marker="dashboard-member-warning-鈴木").elements.pop().classes


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


async def test_without_members_the_select_has_only_everyone_and_no_member_section(user: User) -> None:
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
        {"田中": CrossLoad(LoadStats(0.7, 1.2, 1), [ProjectLoad("A", 0.4, 0.6), ProjectLoad("B", 0.3, 0.6)])},
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


async def test_the_cross_load_card_shows_the_total_and_the_project_breakdown(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert text(user, "dashboard-load-田中") == "平均 70% / 最大 120% / 割り当て超過 1 日"
    assert text(user, "dashboard-cross-detail-田中-0") == "A: 平均 40% / 最大 60%"
    assert text(user, "dashboard-cross-detail-田中-1") == "B: 平均 30% / 最大 60%"
    await user.should_see(marker="dashboard-cross-note")


async def test_the_cross_load_card_lists_failures_and_the_project_checks(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-cross-failure-0")
    assert text(user, "dashboard-cross-failure-0") == "読み込めなかったファイル: 壊れた(invalid)"
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


async def test_without_cross_the_load_card_is_unchanged_and_the_switch_is_off(user: User) -> None:
    views, crosses, _ = mount_cross()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert text(user, "dashboard-load-田中") == "平均 50% / 最大 120% / 割り当て超過 2 日"
    await user.should_not_see(marker="dashboard-cross-note")
    assert user.find(marker="dashboard-cross").elements.pop().value is False
    assert crosses == []  # 表示の同期では通知しない


def heat_summary(name: str = "田中", project: str = "A") -> CrossSummary:
    days = [
        DayLoad(date(2026, 10, 5), 0.0, []),
        DayLoad(date(2026, 10, 6), 0.6, [ProjectPeak(project, 0.6)]),
        DayLoad(date(2026, 10, 7), 1.2, [ProjectPeak(project, 0.6), ProjectPeak("B", 0.6)]),
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
    assert "data-cell" in user.find(marker="dashboard-heatmap-table").elements.pop().content


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


async def test_the_heatmap_card_can_shrink_so_that_the_table_scrolls(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = heat_summary().loads["田中"]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap")
    assert user.find(marker="dashboard-heatmap").elements.pop()._style.get("min-width") == "0"


async def test_the_heatmap_table_wrapper_can_shrink_and_scrolls_by_itself(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = heat_summary().loads["田中"]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-table")
    style = user.find(marker="dashboard-heatmap-table").elements.pop()._style
    assert style.get("min-width") == "0" and style.get("max-width") == "100%" and style.get("overflow-x") == "auto"


def test_the_heatmap_scroller_has_an_always_visible_scrollbar_style() -> None:
    assert 'class="heatmap-scroll"' in heatmap_html(heat_summary())
    for rule in ("::-webkit-scrollbar {", "::-webkit-scrollbar-track", "::-webkit-scrollbar-thumb"):
        assert f".heatmap-scroll{rule}" in HEATMAP_CSS


def long_heat_summary(count: int) -> CrossSummary:
    days = [DayLoad(date(2026, 10, 1) + timedelta(days=i), 0.5, []) for i in range(count)]
    return CrossSummary({"田中": CrossLoad(LoadStats(0.5, 0.5, 0), [], days)}, ["A"], set(), [])


async def test_the_heatmap_card_tells_that_a_wide_table_scrolls_sideways(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = sample()
    data.cross = long_heat_summary(HEATMAP_HINT_DAYS + 1)
    views[0].show(data, PeriodKind.ALL)
    await user.should_see(marker="dashboard-heatmap-hint")
    assert text(user, "dashboard-heatmap-hint") == "横にスクロールできます"


async def test_the_heatmap_card_has_no_scroll_hint_for_a_narrow_table(user: User) -> None:
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
    views[0].show(sample(), PeriodKind.WEEK, view_state=state((CardId.DUE, CardId.HOURS)))
    await user.should_see(marker="dashboard-due-0")
    await user.should_see(marker="dashboard-hours-total")
    await user.should_not_see(marker="dashboard-progress-percent")
    await user.should_not_see(marker="dashboard-team")
    assert views[0].card_order == (CardId.DUE, CardId.HOURS)  # 描く順は card_order のとおり


async def test_without_a_view_state_all_cards_show_in_the_default_order(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    assert views[0].card_order == DEFAULT_ORDER


def full_state(
    current: str = "標準", dirty: bool = False, save_block: str | None = None, names: tuple[str, ...] = ("標準", "月次")
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


async def test_the_toolbar_shows_the_dirty_mark_and_save_buttons_only_when_dirty(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(dirty=False))
    await user.should_see(marker="dashboard-view")
    await user.should_see(marker="dashboard-view-save-as")  # 名前をつけて保存は常に押せる(⋮ の中)
    await user.should_not_see(marker="dashboard-view-dirty")
    await user.should_not_see(marker="dashboard-view-save")
    assert views[0].save_as_item.enabled is True
    assert views[0].revert_item.enabled is False  # 元に戻すは、変更があるときだけ押せる(⋮ の中)
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True))
    await user.should_see(marker="dashboard-view-dirty")
    await user.should_see(marker="dashboard-view-save")
    assert views[0].revert_item.enabled is True


async def test_the_toolbar_has_two_rows_one_for_the_view_and_one_for_the_filters(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True))
    top = set(views[0].top_bar.descendants())
    filters = set(views[0].filter_bar.descendants())
    assert {views[0].view_select, views[0].dirty_mark, views[0].save_button, views[0].edit_button} <= top
    assert views[0].save_as_item in top and views[0].revert_item in top  # ⋮ の中のメニュー項目も 1 段目
    assert {views[0].toggle, views[0].member_select, views[0].cross_switch, views[0].custom_field} <= filters
    assert top.isdisjoint(filters)


async def test_save_is_disabled_when_blocked(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(dirty=True, save_block="「標準」は上書きできません"))
    await user.should_see(marker="dashboard-view-save")
    save = user.find(marker="dashboard-view-save").elements.pop()
    assert save.enabled is False


async def test_toolbar_buttons_call_the_actions(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True))
    await user.should_see(marker="dashboard-view-save")
    user.find(marker="dashboard-view-save").click()
    user.find(marker="dashboard-view-save-as").click()
    user.find(marker="dashboard-view-revert").click()
    assert log == ["save", "save_as", "revert"]


async def test_selecting_in_the_dropdown_calls_select_but_syncing_does_not(user: User) -> None:
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
    assert views[0].rename_item.enabled is False and views[0].delete_item.enabled is False
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次"))
    assert views[0].rename_item.enabled is True and views[0].delete_item.enabled is True


async def test_edit_mode_shows_handles_and_hide_buttons_and_the_hidden_list(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    hidden_state = ViewState(("標準",), "標準", False, None, (CardId.TEAM, CardId.DUE), (CardId.PROGRESS,))
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


async def test_a_move_event_calls_move_card_and_ignores_bad_arguments(user: User) -> None:
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
    backlog = Backlog(26.0, 0, 3, 2.0, 1.5, [("田中", 16.0)], by_team=[("開発", 16.0), ("チームなし", 10.0)])
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-team-開発")
    assert text(user, "dashboard-backlog-team-開発") == "開発 16.0h"
    assert text(user, "dashboard-backlog-team-チームなし") == "チームなし 10.0h"


async def test_the_backlog_card_hides_the_team_heading_without_team_rows(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-member-田中")
    await user.should_not_see("チーム別")


async def test_the_cards_note_the_weighting_only_when_a_team_is_selected(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)]))
    data.team_name = "開発"
    views[0].show(data, PeriodKind.WEEK)
    for key in ("load", "hours", "backlog"):
        await user.should_see(marker=f"dashboard-weighted-note-{key}")
    assert text(user, "dashboard-weighted-note-backlog") == "チーム「開発」の所属の割合で按分しています"


async def test_the_cards_do_not_note_the_weighting_without_a_team(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    await user.should_not_see(marker="dashboard-weighted-note-backlog")


async def test_the_backlog_card_shows_hours_required_people_and_the_shortfall(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(19.5, 2, 3, 2.0, 1.5, [("田中", 13.0), (UNASSIGNED, 6.5)])
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-need")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 19.5h(遅れなし)"
    assert text(user, "dashboard-backlog-unset") == "工数未設定 2 件(合計に入れていません)"
    assert text(user, "dashboard-backlog-days") == "稼働 3 日で終える場合"
    assert text(user, "dashboard-backlog-need") == "必要 2.0 人"
    assert text(user, "dashboard-backlog-have") == "稼働できる人員 1.5 人"
    assert text(user, "dashboard-backlog-gap") == "あと 0.5 人"
    assert text(user, "dashboard-backlog-member-田中") == "田中 13.0h"
    assert text(user, f"dashboard-backlog-member-{UNASSIGNED}") == f"{UNASSIGNED} 6.5h"


async def test_the_backlog_card_shows_spare_people_when_supply_is_enough(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 0.5, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-gap")
    assert text(user, "dashboard-backlog-gap") == "余裕 1.0 人"
    await user.should_not_see(marker="dashboard-backlog-unset")


async def test_the_backlog_card_says_when_the_period_is_undecided(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(5.0, 0, None, None, 1.0, [])), PeriodKind.ALL)
    await user.should_see(marker="dashboard-backlog-nodays")
    assert text(user, "dashboard-backlog-nodays") == "期間が決まらないため、必要な人数は出せません"
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
    assert text(user, "dashboard-backlog-nodays") == "期間がすでに終わっているため、必要な人数は出せません"


async def test_the_backlog_card_says_just_right_instead_of_zero_point_zero(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(24.3, 0, 3, 1.0125, 1.0, [("田中", 24.3)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-gap")
    assert text(user, "dashboard-backlog-gap") == "ちょうど"
    assert "text-negative" not in user.find(marker="dashboard-backlog-gap").elements.pop().classes


async def test_the_backlog_card_explains_the_unit_of_people(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 0.5, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-unit")
    assert text(user, "dashboard-backlog-unit") == (
        "人は、100% の人に換算した数です。今日は、今から稼働の枠の終わりまでの残り時間で数えます。"
    )


async def test_the_rest_is_a_stacked_bar_by_status_without_the_text_row(user: User) -> None:
    from projectapp.dashboard_view import PIE_VARS

    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(
        20.0, 0, 3, 20 / 19.5, 1.5, [("田中", 20.0)],
        {Status.NOT_STARTED: 12.0, Status.RUNNING: 6.0, Status.PAUSED: 2.0},
    )
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours-bar-not_started")
    await user.should_not_see(marker="dashboard-backlog-by-status")  # 文字の内訳は出さない
    for status, width in ((Status.NOT_STARTED, "60.0%"), (Status.RUNNING, "30.0%"), (Status.PAUSED, "10.0%")):
        segment = user.find(marker=f"dashboard-backlog-hours-bar-{status.name.lower()}").elements.pop()._style
        assert segment["width"] == width
        assert segment["background"] == f"var({PIE_VARS[status]})"  # 円グラフと同じ状態色
    assert text(user, "dashboard-backlog-hours-legend-not_started") == "未着手"
    assert text(user, "dashboard-backlog-hours-legend-running") == "実行中"
    assert text(user, "dashboard-backlog-hours-legend-paused") == "一時停止"


async def test_the_status_bar_is_left_out_without_a_rest(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(0.0, 2, 3, 0.0, 1.5, [])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-unset")
    await user.should_not_see(marker="dashboard-backlog-hours-legend-not_started")


async def test_the_team_row_and_dropdown_show_for_everyone_and_report_team_changes(user: User) -> None:
    from projectapp.scope import team_key

    members: list[str | None] = []
    teams: list[str | None] = []
    views: list[DashboardView] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(lambda: None, lambda kind: None, members.append, on_team_change=teams.append)
        views.append(view)
        view.build()

    await user.open("/")
    data = sample()
    data.teams = ["開発"]
    data.progress.by_team = [MemberProgress("開発", 40.0, {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 0})]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-row-progress-開発")
    assert text(user, "dashboard-team-row-progress-開発") == "40% / 3件"
    select = user.find(marker="dashboard-member").elements.pop()
    assert select.options[team_key("開発")] == "チーム: 開発"
    select.set_value(team_key("開発"))
    assert teams == ["開発"] and members == []
    select.set_value("田中")
    assert members == ["田中"]


async def test_the_team_and_progress_cards_note_how_many_referenced_projects_are_counted(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.references = 2
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-references")
    assert text(user, "dashboard-team-references") == "参照先 2 件を含む"
    assert text(user, "dashboard-progress-references") == "参照先 2 件を含む"


async def test_the_cards_do_not_note_references_when_none_are_counted(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-percent")
    await user.should_not_see(marker="dashboard-team-references")
    await user.should_not_see(marker="dashboard-progress-references")


async def test_the_backlog_card_shows_the_days_with_one_decimal(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(16.5, 0, 16.5 / 6.5, 1.0, 1.0, [("田中", 16.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-days")
    assert text(user, "dashboard-backlog-days") == "稼働 2.5 日で終える場合"


def mount_ticking() -> tuple[list[DashboardView], list[int]]:
    views: list[DashboardView] = []
    ticks: list[int] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(lambda: None, lambda kind: None, on_tick=lambda: ticks.append(1))
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
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    await user.should_not_see(marker="dashboard-backlog-cross-note")


async def test_the_backlog_card_shows_the_unadjusted_supply_only_when_it_changed(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    changed = Backlog(6.5, 0, 3, 0.5, 1.6, [("田中", 6.5)], nominal_supply=2.0)
    views[0].show(with_backlog(changed), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-supply-note")
    assert text(user, "dashboard-backlog-supply-note") == "相対比率の合計 2.0 人 → 稼働を反映して 1.6 人"
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 0.5, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-need")
    await user.should_not_see(marker="dashboard-backlog-supply-note")


def swatch_color(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop()._style["background"]


async def test_the_people_bars_carry_their_numbers_and_own_colors(user: User) -> None:
    from projectapp.dashboard_view import HAVE_COLOR, NEED_COLOR, PLANNED_COLOR

    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(19.5, 0, 3, 2.5, 2.0, [("田中", 13.0)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-need")
    assert text(user, "dashboard-backlog-need") == "必要 2.5 人"  # 数字は棒のすぐ上のラベルに出す
    assert text(user, "dashboard-backlog-have") == "稼働できる人員 2.0 人"
    assert user.find(marker="dashboard-backlog-bar-need").elements.pop()._style["background"] == NEED_COLOR
    assert user.find(marker="dashboard-backlog-bar-have").elements.pop()._style["background"] == HAVE_COLOR
    assert len({NEED_COLOR, HAVE_COLOR, PLANNED_COLOR}) == 3  # 予定の青・実績の緑と混ざらない
    await user.should_not_see(marker="dashboard-backlog-legend-late")  # 遅れがなければ凡例は出さない


async def test_the_backlog_member_bars_use_the_need_color(user: User) -> None:
    from projectapp.dashboard_view import NEED_COLOR

    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(13, 0, 3, 2.0, 1.5, [("田中", 13.0)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-member-田中")
    bars = [e for e in user.find(marker="dashboard-backlog-member-bar-田中").elements]
    assert bars and bars[0]._style["background"] == NEED_COLOR


async def test_the_backlog_card_has_no_legend_when_no_people_are_shown(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, None, None, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-nodays")
    await user.should_not_see(marker="dashboard-backlog-bar-need")


async def test_the_headline_is_the_shortfall_and_the_late_row_shows_it_without_the_delay(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2)
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-gap")
    assert text(user, "dashboard-backlog-gap") == "あと 1.0 人"
    assert text(user, "dashboard-backlog-hours") == "残りの工数 20.0h(うち遅れ 2 件・10.0h)"
    assert text(user, "dashboard-backlog-late") == "遅れがなければ 余裕 1.0 人"
    assert "text-h6" in user.find(marker="dashboard-backlog-gap").elements.pop().classes


async def test_the_late_row_shows_how_much_room_the_delay_eats(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, 2, 4.0, 5.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2)
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late")
    assert text(user, "dashboard-backlog-gap") == "余裕 1.0 人"
    assert text(user, "dashboard-backlog-late") == "遅れがなければ 余裕 3.0 人"


async def test_the_late_row_says_just_right_when_the_delay_was_the_only_load(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, 2, 4.0, 2.0, [("田中", 20.0)], overdue_hours=20.0, overdue_count=1)  # 遅れがなければ必要 0
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
    assert text(user, "dashboard-backlog-hours") == "残りの工数 20.0h(うち遅れ 2 件・10.0h)"
    await user.should_not_see(marker="dashboard-backlog-late")  # 人数は出せない
    assert "text-h6" in user.find(marker="dashboard-backlog-hours").elements.pop().classes  # 人数が出せないときは時間が見出し


async def test_the_need_bar_is_stacked_with_the_late_part_and_the_legend_names_it(user: User) -> None:
    from projectapp.dashboard_view import LATE_COLOR, NEED_COLOR

    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2)
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-bar-late")
    assert text(user, "dashboard-backlog-legend-late") == "うち遅れ"
    assert swatch_color(user, "dashboard-backlog-swatch-late") == LATE_COLOR
    need = user.find(marker="dashboard-backlog-bar-need").elements.pop()._style
    late = user.find(marker="dashboard-backlog-bar-late").elements.pop()._style
    assert need["background"] == NEED_COLOR and late["background"] == LATE_COLOR
    assert need["width"] == "50.0%" and late["width"] == "50.0%"  # 必要 4.0 人のうち遅れの分が 2.0 人


async def test_without_a_late_part_the_need_bar_is_a_single_segment(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(19.5, 0, 3, 2.0, 1.5, [("田中", 13.0)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-bar-need")
    await user.should_not_see(marker="dashboard-backlog-bar-late")
    await user.should_not_see(marker="dashboard-backlog-legend-late")


async def test_the_late_cover_says_when_nothing_is_late(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 6.5h(遅れなし)"
    await user.should_not_see(marker="dashboard-backlog-late")


async def test_both_late_bases_are_selectable_and_the_current_one_is_filled(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    delay = next(iter(user.find(marker="dashboard-backlog-late-delay").elements))
    warning = next(iter(user.find(marker="dashboard-backlog-late-warning").elements))
    assert delay.props.get("disable") is None and warning.props.get("disable") is None
    assert delay.text == "遅れのみ" and warning.text == "警告を含む"
    assert "outline" not in delay.props and "outline" in warning.props


async def test_the_warning_basis_button_is_filled_when_chosen(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], late_basis=LateBasis.WARNING)
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    delay = next(iter(user.find(marker="dashboard-backlog-late-delay").elements))
    warning = next(iter(user.find(marker="dashboard-backlog-late-warning").elements))
    assert "outline" in delay.props and "outline" not in warning.props


async def test_pressing_the_other_basis_notifies_and_the_current_one_does_nothing(user: User) -> None:
    changes: list[LateBasis] = []
    views, _, _ = mount(late_basis_changes=changes)
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    user.find(marker="dashboard-backlog-late-delay").click()
    assert changes == []
    user.find(marker="dashboard-backlog-late-warning").click()
    assert changes == [LateBasis.WARNING]


async def test_the_headline_lists_overdue_and_warning_separately(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    both = Backlog(
        20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=6.5, overdue_count=1,
        late_basis=LateBasis.WARNING, warning_hours=3.5, warning_count=2,
    )  # fmt: skip
    views[0].show(with_backlog(both), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 20.0h(うち遅れ 1 件・6.5h、警告 2 件・3.5h)"
    only_warning = Backlog(20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], late_basis=LateBasis.WARNING, warning_hours=3.5, warning_count=2)
    views[0].show(with_backlog(only_warning), PeriodKind.WEEK)
    await asyncio.sleep(0.3)  # 描き直しを待つ
    assert text(user, "dashboard-backlog-hours") == "残りの工数 20.0h(うち警告 2 件・3.5h)"
    clean = Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], late_basis=LateBasis.WARNING)
    views[0].show(with_backlog(clean), PeriodKind.WEEK)
    await asyncio.sleep(0.3)
    assert text(user, "dashboard-backlog-hours") == "残りの工数 6.5h(遅れなし)"


async def test_the_need_bar_has_a_warning_segment_and_legend_only_for_warnings(user: User) -> None:
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
    delay = Backlog(20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=6.0, overdue_count=1)
    views[0].show(with_backlog(delay), PeriodKind.WEEK)
    await asyncio.sleep(0.3)
    await user.should_not_see(marker="dashboard-backlog-bar-warning")
    await user.should_not_see(marker="dashboard-backlog-legend-warning")
    assert text(user, "dashboard-backlog-late").startswith("遅れがなければ")
