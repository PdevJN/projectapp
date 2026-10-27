import re
from datetime import date, datetime, timedelta

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import (
    CrossLoad,
    CrossSummary,
    DayLoad,
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
            [OverdueRow("遅れた作業", "田中", datetime(2026, 10, 6, 17))],
            [
                MemberProgress("田中", 40.0, {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 0}),
                MemberProgress("佐藤", None, {status: 0 for status in Status}),
            ],
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
        None,
        ["田中", "佐藤"],
    )


def empty() -> Dashboard:
    day = Period(date(2026, 10, 7), date(2026, 10, 7))
    return Dashboard(day, Progress(None, {status: 0 for status in Status}, []), {}, [], [])


def mount(
    member_changes: list[str | None] | None = None, actions: ViewActions | None = None
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
    assert text(user, "dashboard-load-田中") == "平均 70% / 最大 120% / 超過 1 日"
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
    assert text(user, "dashboard-load-田中") == "平均 50% / 最大 120% / 超過 2 日"
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
    await user.should_see(marker="dashboard-view-save-as")  # 名前をつけて保存は常に出す
    await user.should_not_see(marker="dashboard-view-dirty")
    await user.should_not_see(marker="dashboard-view-save")
    await user.should_not_see(marker="dashboard-view-revert")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True))
    await user.should_see(marker="dashboard-view-dirty")
    await user.should_see(marker="dashboard-view-save")
    await user.should_see(marker="dashboard-view-revert")


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
