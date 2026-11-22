"""ダッシュボードの`進捗と遅れ`の着工遅れ(要望 161 段階 2)。今は 2026-10-07(水)12:00。"""

from datetime import date, datetime

from projectapp.dashboard import ChildProject, StartDelayRow, summarize_progress
from projectapp.models import (
    Actual,
    Assignee,
    Member,
    Project,
    Status,
    Task,
    TaskKind,
)
from projectapp.start_delay import DelayKind

NOW = datetime(2026, 10, 7, 12)
MON = datetime(2026, 10, 5, 9)  # 月曜


def project_of(*tasks: Task, **settings: object) -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=list(tasks),
        **settings,
    )


def task(
    name: str,
    *actuals: Actual,
    status: Status = Status.NOT_STARTED,
    who: str = "田中",
    start: datetime = MON,
) -> Task:
    return Task(
        name,
        planned_start=start,
        planned_end=datetime(2026, 10, 9, 17),
        effort_hours=16,
        status=status,
        actuals=list(actuals),
        assignees=[Assignee(who)],
    )


def rows(project: Project, member: str | None = None) -> list[StartDelayRow]:
    return summarize_progress(project, {}, NOW, member).start_delays


def test_an_unstarted_task_past_its_start_is_counted() -> None:
    assert rows(project_of(task("a"))) == [
        StartDelayRow("a", DelayKind.UNSTARTED, 2, ("田中",))
    ]


def test_a_task_left_paused_is_counted_as_a_stop() -> None:
    paused = task(
        "p",
        Actual(MON, datetime(2026, 10, 5, 12)),
        status=Status.PAUSED,
    )
    assert rows(project_of(paused)) == [
        StartDelayRow("p", DelayKind.STOP, 1, ("田中",))
    ]


def test_past_delays_are_not_counted() -> None:
    late_start = task(
        "late",
        Actual(datetime(2026, 10, 6, 9), None),  # 火曜に着手(予定は月曜)。今は進行中
        status=Status.RUNNING,
    )
    resumed = task(
        "resumed",
        Actual(MON, datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 7, 9), None),  # 火曜が抜けたが、再開している
        status=Status.RUNNING,
    )
    assert rows(project_of(late_start, resumed)) == []


def test_the_grace_days_apply() -> None:
    assert rows(project_of(task("a"), start_delay_grace=2)) == []
    assert len(rows(project_of(task("a"), start_delay_grace=1))) == 1


def test_nothing_is_counted_when_the_setting_is_off() -> None:
    project = project_of(task("a"), start_delay_enabled=False)
    progress = summarize_progress(project, {}, NOW)
    assert progress.start_delays == []
    assert progress.start_delay_enabled is False


def test_the_setting_is_reported_when_on() -> None:
    assert (
        summarize_progress(project_of(task("a")), {}, NOW).start_delay_enabled is True
    )


def test_the_member_filter_applies() -> None:
    project = project_of(task("a", who="田中"), task("b", who="鈴木"))
    assert [r.name for r in rows(project, "鈴木")] == ["b"]


def test_rows_are_sorted_by_days_descending() -> None:
    old = task("old", start=datetime(2026, 10, 1, 9))  # 木曜から。木・金・月・火 = 4 日
    new = task("new")  # 月曜から 2 日
    assert [(r.name, r.days) for r in rows(project_of(new, old))] == [
        ("old", 4),
        ("new", 2),
    ]


def test_a_done_task_is_not_counted() -> None:
    done = task("d", Actual(MON, datetime(2026, 10, 5, 12)), status=Status.DONE)
    assert rows(project_of(done)) == []


# --- 参照先・絞り込み・対象外(要望 161 段階 2 の最終レビュー) ---


def parent_of(*tasks: Task, **settings: object) -> Project:
    ref = Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤")
    return project_of(*tasks, ref, **settings)


def child_of(*tasks: Task, **settings: object) -> Project:
    return Project(
        "基盤",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=list(tasks),
        **settings,
    )


def with_child(
    parent: Project, child: Project, holidays: dict[date, str] | None = None
) -> list[StartDelayRow]:
    children = {child.name: ChildProject(child, holidays or {})}
    return summarize_progress(parent, {}, NOW, None, children).start_delays


def test_a_referenced_projects_task_is_counted_with_its_origin_in_the_name() -> None:
    result = with_child(parent_of(), child_of(task("子タスク")))
    assert result == [
        StartDelayRow("子タスク(基盤)", DelayKind.UNSTARTED, 2, ("田中",))
    ]


def test_a_referenced_project_uses_its_own_setting_and_grace() -> None:
    assert with_child(parent_of(), child_of(task("c"), start_delay_enabled=False)) == []
    assert with_child(parent_of(), child_of(task("c"), start_delay_grace=5)) == []
    own = task("own")
    result = with_child(parent_of(own, start_delay_grace=5), child_of(task("c")))
    assert [r.name for r in result] == [
        "c(基盤)"
    ]  # 開いている側の猶予 5 は参照先に及ばない


def test_a_referenced_project_uses_its_own_workdays() -> None:
    off = {date(2026, 10, 5): "休", date(2026, 10, 6): "休"}  # 月・火が休み
    assert with_child(parent_of(), child_of(task("c")), off) == []


def test_a_closed_open_project_hides_referenced_delays_in_the_data_too() -> None:
    """開いているプロジェクトが表示オフなら、参照先がオンでも、データ上も空にする。"""
    parent = parent_of(start_delay_enabled=False)
    children = {"基盤": ChildProject(child_of(task("c")), {})}
    progress = summarize_progress(parent, {}, NOW, None, children)
    assert progress.start_delays == []
    assert progress.start_delay_enabled is False


def test_the_team_scope_filters_by_assignee() -> None:
    project = project_of(task("a", who="田中"), task("b", who="鈴木"))
    for scope in ({"田中": 1.0}, frozenset({"田中"}), "田中"):
        result = summarize_progress(project, {}, NOW, scope).start_delays
        assert [r.name for r in result] == ["a"]


def test_a_shared_task_is_one_row() -> None:
    shared = task("s")
    shared.assignees = [Assignee("田中"), Assignee("鈴木")]
    result = rows(project_of(shared))
    assert [(r.name, r.assignee_names) for r in result] == [("s", ("田中", "鈴木"))]


def test_a_paused_task_with_an_open_or_no_actual_is_not_counted() -> None:
    running_interval = task("open", Actual(MON, None), status=Status.PAUSED)
    no_actual = task("none", status=Status.PAUSED)
    assert rows(project_of(running_interval, no_actual)) == []


def test_only_normal_tasks_are_counted() -> None:
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=MON)
    kid = task("子")
    summary = Task(
        "まとめ", kind=TaskKind.SUMMARY, children=[kid.id], planned_start=MON
    )
    result = rows(project_of(checkpoint, summary, kid))
    assert [r.name for r in result] == ["子"]  # 子だけ(まとめ・節目は数えない)


def test_start_delay_rows_carry_the_task_id_only_for_the_open_project() -> None:
    own = task("own")
    own.id = "own-id"
    [row] = rows(project_of(own))
    assert row.task_id == "own-id"
    child_task = task("c")
    child_task.id = "child-id"
    [referenced] = with_child(parent_of(), child_of(child_task))
    assert referenced.task_id == ""  # 参照先のタスクはアサイン画面の対象外(要望 168)
