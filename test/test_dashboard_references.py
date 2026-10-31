from datetime import date, datetime

from projectapp.dashboard import (
    ChildProject,
    Period,
    PeriodKind,
    summarize,
    summarize_progress,
    summarize_team_progress,
)
from projectapp.extract import extract
from projectapp.events import effective_holidays
from projectapp.models import (
    Assignee,
    Event,
    Member,
    Membership,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
    Team,
)

NOW = datetime(2026, 10, 7, 12)


def parent() -> Project:
    return Project(
        "親",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        tasks=[
            Task(
                "p1",
                id="p1",
                effort_hours=8,
                status=Status.DONE,
                assignees=[Assignee("田中", 1.0)],
            ),
            Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤"),
        ],
    )


def child() -> Project:
    return Project(
        "基盤",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("外部", 1.0)],
        tasks=[
            Task(
                "c1",
                id="c1",
                effort_hours=4,
                status=Status.DONE,
                assignees=[Assignee("田中", 1.0)],
            ),
            Task(
                "c2",
                id="c2",
                effort_hours=4,
                status=Status.RUNNING,
                progress=50,
                assignees=[Assignee("外部", 1.0)],
            ),
        ],
    )


def children(
    project: Project | None = None, holidays: dict[date, str] | None = None
) -> dict[str, ChildProject]:
    chosen = project or child()
    return {chosen.name: ChildProject(chosen, holidays or {})}


def test_team_progress_counts_the_tasks_of_a_referenced_project_like_its_own() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, None, children())
    assert team.counts[Status.DONE] == 2  # 親の p1 と子の c1
    assert team.counts[Status.RUNNING] == 1
    assert team.hours[Status.DONE] == 12
    assert round(team.percent) == round((8 * 100 + 4 * 100 + 4 * 50) / 16)


def test_the_reference_row_itself_is_not_counted() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, None, None)
    assert (
        sum(team.counts.values()) == 1
    )  # 子を渡さなければ、今までどおり参照行は数えない


def test_a_referenced_task_is_named_with_its_project() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, None, children())
    assert team.tasks[Status.RUNNING] == ["c2(基盤)"]
    assert team.tasks[Status.DONE] == ["p1", "c1(基盤)"]


def test_summaries_and_references_inside_the_referenced_project_are_not_counted() -> (
    None
):
    inner = child()
    inner.tasks += [
        Task("S", id="S", kind=TaskKind.SUMMARY, children=["c1"]),
        Task("孫", id="g", kind=TaskKind.REFERENCE, ref_project="孫"),
    ]
    team = summarize_team_progress(parent(), None, NOW, {}, None, children(inner))
    assert sum(team.counts.values()) == 3  # p1・c1・c2 だけ


def test_the_member_filter_matches_referenced_tasks_by_name() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, "外部", children())
    assert sum(team.counts.values()) == 1 and team.tasks[Status.RUNNING] == [
        "c2(基盤)"
    ]  # 親の名簿にいなくても、名前で当たる


def test_the_period_uses_the_schedule_of_the_referenced_project() -> None:
    late = child()
    late.tasks[1].deadline = datetime(2026, 12, 1, 18)  # 期間の外
    late.tasks[0].deadline = datetime(2026, 10, 8, 18)  # 期間の中
    period = Period(date(2026, 10, 5), date(2026, 10, 11))
    team = summarize_team_progress(parent(), period, NOW, {}, None, children(late))
    assert [n for names in team.tasks.values() for n in names] == [
        "c1(基盤)"
    ]  # 親の p1 は日程も締切もなく期間にかからない


def test_the_period_uses_the_holidays_of_the_referenced_project() -> None:
    inner = child()
    inner.tasks[1].planned_start = datetime(2026, 10, 6, 9)
    inner.tasks[1].effort_hours = 8
    inner.events = [
        Event(date(2026, 10, 6), date(2026, 10, 9), "休業", "gray", closed=True)
    ]
    holidays = effective_holidays(inner, {})
    period = Period(
        date(2026, 10, 12), date(2026, 10, 18)
    )  # 休業で完了予定が来週に押される
    team = summarize_team_progress(
        parent(), period, NOW, {}, None, children(inner, holidays)
    )
    assert team.counts[Status.RUNNING] == 1
    plain = summarize_team_progress(
        parent(), period, NOW, {}, None, children(inner, {})
    )  # 休みを渡さなければ今週で終わる
    assert plain.counts[Status.RUNNING] == 0


def test_progress_counts_the_referenced_tasks_and_names_overdue_rows_with_the_project() -> (
    None
):
    inner = child()
    inner.tasks[1].deadline = datetime(2026, 10, 6, 18)  # 実行中で締切を過ぎた
    progress = summarize_progress(parent(), {}, NOW, None, children(inner))
    assert progress.counts[Status.DONE] == 2 and progress.counts[Status.RUNNING] == 1
    assert [row.name for row in progress.overdue] == ["c2(基盤)"]
    assert progress.overdue[0].assignee == "外部"


def test_member_rows_match_referenced_tasks_by_name_and_the_rest_are_unassigned() -> (
    None
):
    rows = {
        row.name: row
        for row in summarize_progress(parent(), {}, NOW, None, children()).by_member
    }
    assert rows["田中"].counts[Status.DONE] == 2  # 親の p1 と、子の c1(同名の田中)
    assert rows["未割り当て"].counts[Status.RUNNING] == 1  # 外部は親の名簿にいない


def test_team_rows_count_referenced_tasks_of_the_team_members() -> None:
    project = parent()
    project.teams = [Team("開発", id="t1")]
    project.members[0].teams = [Membership("t1", 100)]
    rows = {
        row.name: row
        for row in summarize_progress(project, {}, NOW, None, children()).by_team
    }
    assert rows["開発"].counts[Status.DONE] == 2


def test_filtering_by_member_filters_the_referenced_tasks_too() -> None:
    progress = summarize_progress(parent(), {}, NOW, "田中", children())
    assert progress.counts[Status.DONE] == 2 and progress.counts[Status.RUNNING] == 0
    assert progress.by_member == []  # 絞り込み中は従来どおり空


def test_summarize_reports_how_many_referenced_projects_it_counted() -> None:
    period = Period(date(2026, 10, 5), date(2026, 10, 11))
    assert (
        summarize(
            parent(), period, NOW, {}, PeriodKind.ALL, None, None, children()
        ).references
        == 1
    )
    assert summarize(parent(), period, NOW, {}, PeriodKind.ALL).references == 0


def test_numbers_match_before_and_after_extracting_tasks_into_a_child() -> None:
    whole = Project(
        "親",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        sections=[
            Section(
                "開発",
                [
                    Task(
                        "a",
                        id="a",
                        effort_hours=8,
                        status=Status.DONE,
                        assignees=[Assignee("田中", 1.0)],
                    ),
                    Task(
                        "b",
                        id="b",
                        effort_hours=4,
                        status=Status.RUNNING,
                        progress=25,
                        assignees=[Assignee("田中", 1.0)],
                    ),
                    Task(
                        "c", id="c", effort_hours=6, assignees=[Assignee("田中", 1.0)]
                    ),
                ],
                id="s1",
            )
        ],
    )
    period = Period(date(2026, 10, 5), date(2026, 10, 11))
    before = summarize(whole, period, NOW, {}, PeriodKind.ALL)
    result = extract(whole, ["b", "c"], "子")
    after = summarize(
        result.parent,
        period,
        NOW,
        {},
        PeriodKind.ALL,
        None,
        None,
        {"子": ChildProject(result.child, {})},
    )
    assert after.progress.percent == before.progress.percent
    assert after.progress.counts == before.progress.counts
    assert after.team.percent == before.team.percent
    assert after.team.hours == before.team.hours
    assert after.team.counts == before.team.counts
    assert [row.counts for row in after.progress.by_member] == [
        row.counts for row in before.progress.by_member
    ]
