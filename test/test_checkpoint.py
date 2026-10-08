from datetime import datetime
from pathlib import Path

import pytest

from projectapp import arrange
from projectapp.dashboard import Period, summarize_due, summarize_progress, summarize_workload
from projectapp.forms import build_task
from projectapp.models import Priority, Project, Section, Status, Task, TaskKind, TaskUrl
from projectapp.storage import load_project, save_project
from projectapp.timeline import Schedule, effective_end, effective_start, is_overdue
from test_storage import write_raw

DEADLINE = datetime(2026, 10, 12, 17, 0)


def checkpoint(name: str, deadline: datetime | None = DEADLINE, *predecessors: str, **fields: object) -> Task:
    return Task(
        name,
        id=name,
        kind=TaskKind.CHECKPOINT,
        deadline=deadline,
        predecessors=list(predecessors),
        **fields,  # type: ignore[arg-type]
    )


def test_kind_roundtrip(tmp_path: Path) -> None:
    project = Project("cp", sections=[Section("s", [checkpoint("レビュー")])])
    loaded = load_project(save_project(project, tmp_path)).sections[0].tasks[0]
    assert (loaded.kind, loaded.deadline, loaded.planned_start) == (
        TaskKind.CHECKPOINT,
        DEADLINE,
        None,
    )


def test_a_file_without_kind_loads_as_normal(tmp_path: Path) -> None:
    path = write_raw(tmp_path, [{"name": "a"}])
    assert load_project(path).sections[0].tasks[0].kind is TaskKind.NORMAL


@pytest.mark.parametrize(
    "raw",
    [
        {"name": "a", "kind": "zz"},
        {"name": "a", "kind": 1},
        {"name": "a", "kind": "チェックポイント"},  # 締切なし
        {"name": "a", "kind": "チェックポイント", "deadline": "2026-10-12T17:00:00", "status": "実行中"},
        {"name": "a", "kind": "チェックポイント", "deadline": "2026-10-12T17:00:00", "status": "一時停止"},
    ],
)
def test_bad_kinds_are_rejected(tmp_path: Path, raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        load_project(write_raw(tmp_path, [raw]))


def test_a_checkpoint_with_stray_fields_is_loaded_without_them(tmp_path: Path) -> None:
    path = write_raw(
        tmp_path,
        [
            {
                "name": "a",
                "kind": "チェックポイント",
                "deadline": "2026-10-12T17:00:00",
                "planned_end_manual": True,
                "planned_start": "2026-10-05T09:00:00",
                "planned_end": "2026-10-07T18:00:00",
                "effort_hours": 5.0,
                "assignee": "佐藤",
                "allocation": 0.5,
                "actuals": [{"start": "2026-10-05T09:00:00"}],
            }
        ],
    )
    loaded = load_project(path)
    task = loaded.sections[0].tasks[0]
    assert (task.planned_start, task.planned_end, task.planned_end_manual) == (None, None, False)
    assert (task.effort_hours, task.assignees, task.actuals) == (0.0, [], [])
    assert task.deadline == DEADLINE
    assert loaded.members == []  # 担当は使わないので、メンバーも補わない


def test_copy_keeps_the_kind() -> None:
    project = Project("p", sections=[Section("A", [checkpoint("c")])])
    copy = arrange.copy_task(project, ((0,), 0), ((0,), 1))
    assert copy.kind is TaskKind.CHECKPOINT and copy.deadline == DEADLINE


MON = datetime(2026, 10, 5, 9, 0)
WED_NOON = datetime(2026, 10, 7, 12, 0)


def work(name: str, *predecessors: str, **fields: object) -> Task:
    return Task(name, id=name, predecessors=list(predecessors), **fields)  # type: ignore[arg-type]


def project(*tasks: Task) -> Project:
    return Project("p", tasks=list(tasks), daily_hours=6.5)


def test_a_checkpoints_start_and_end_are_its_deadline() -> None:
    cp = checkpoint("c", planned_start=MON, effort_hours=5.0)  # 使われない値が入っていても
    proj = project(cp)
    assert effective_start(cp, proj, {}) == DEADLINE
    assert effective_end(cp, proj, {}) == DEADLINE
    schedule = Schedule(proj, {})
    assert (schedule.start(cp), schedule.end(cp)) == (DEADLINE, DEADLINE)


def test_a_checkpoint_pushes_its_successor_to_the_deadline() -> None:
    friday = datetime(2026, 10, 9, 17, 0)
    c = checkpoint("c", friday)
    b = work("b", "c", planned_start=MON, effort_hours=1)
    proj = project(c, b)
    assert effective_start(b, proj, {}) == friday


def test_a_successor_already_later_is_not_pulled_back() -> None:
    c = checkpoint("c", datetime(2026, 10, 7, 12, 0))
    later = datetime(2026, 10, 9, 9, 0)
    b = work("b", "c", planned_start=later, effort_hours=1)
    assert effective_start(b, project(c, b), {}) == later


def test_a_checkpoint_is_not_pushed_by_its_predecessors() -> None:
    a = work("a", planned_start=MON, effort_hours=26)  # 木曜 15:30 まで
    c = checkpoint("c", WED_NOON, "a")
    assert effective_start(c, project(a, c), {}) == WED_NOON


def test_a_checkpoint_is_overdue_when_its_predecessors_will_finish_after_the_deadline() -> None:
    a = work("a", planned_start=MON, effort_hours=26)  # 木曜 15:30 まで
    c = checkpoint("c", WED_NOON, "a")
    proj = project(a, c)
    assert is_overdue(c, proj, {}, MON)  # まだ締切の前でも、間に合わない見込み


def test_a_checkpoint_is_not_overdue_when_the_predecessors_finish_in_time() -> None:
    a = work("a", planned_start=MON, effort_hours=1)
    c = checkpoint("c", WED_NOON, "a")
    assert not is_overdue(c, project(a, c), {}, MON)


def test_a_done_checkpoint_is_never_overdue() -> None:
    a = work("a", planned_start=MON, effort_hours=26)
    c = checkpoint("c", WED_NOON, "a", status=Status.DONE)
    assert not is_overdue(c, project(a, c), {}, datetime(2026, 10, 20))


def test_a_checkpoint_is_overdue_after_its_deadline() -> None:
    c = checkpoint("c", WED_NOON)
    assert is_overdue(c, project(c), {}, datetime(2026, 10, 8))
    assert not is_overdue(c, project(c), {}, MON)


def test_a_normal_task_is_not_overdue_just_because_it_will_miss_the_deadline() -> None:
    a = work("a", planned_start=MON, effort_hours=26)
    b = work("b", "a", planned_start=MON, effort_hours=1, deadline=WED_NOON)
    assert not is_overdue(b, project(a, b), {}, MON)  # 通常タスクは、現在時刻だけで判定する(従来どおり)


def make(existing: Task | None = None, **overrides: object) -> Task:
    values: dict[str, object] = {
        "name": "レビュー",
        "planned_start": "",
        "planned_end": "",
        "deadline": "2026-10-12T17:00",
        "effort_hours": None,
        "priority": Priority.HIGH,
        "status": Status.NOT_STARTED,
        "color": "#112233",
        "assignees": [],
        "kind": TaskKind.CHECKPOINT,
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]


def test_a_checkpoint_keeps_only_the_deadline() -> None:
    task = make(
        planned_start="日付ではない",  # 隠した欄の不正な入力は、保存を妨げない
        planned_end="2026-10-07T18:00",
        effort_hours=-3.0,
        assignees=[("佐藤", 500.0)],
        actual_start="2026-10-05T09:00",
    )
    assert task.kind is TaskKind.CHECKPOINT
    assert task.deadline == DEADLINE
    assert (task.planned_start, task.planned_end, task.planned_end_manual) == (None, None, False)
    assert (task.effort_hours, task.assignees, task.actuals) == (0.0, [], [])
    assert task.priority is Priority.HIGH and task.color == "#112233"


def test_a_checkpoint_needs_a_deadline() -> None:
    with pytest.raises(ValueError, match="締切"):
        make(deadline="")


@pytest.mark.parametrize("status", [Status.RUNNING, Status.PAUSED])
def test_a_checkpoint_rejects_the_other_statuses(status: Status) -> None:
    with pytest.raises(ValueError, match="状態"):
        make(status=status)


def test_a_checkpoint_can_become_normal_again() -> None:
    existing = checkpoint("x")
    task = make(
        existing,
        kind=TaskKind.NORMAL,
        planned_start="2026-10-05T09:00",
        planned_end="2026-10-07T18:00",
        effort_hours=8.0,
        status=Status.RUNNING,
    )
    assert task.kind is TaskKind.NORMAL and task.id == "x"
    assert task.planned_start == datetime(2026, 10, 5, 9, 0)


def test_a_normal_task_keeps_building_as_before() -> None:
    task = make(kind=TaskKind.NORMAL, planned_start="2026-10-05T09:00", effort_hours=8.0)
    assert task.kind is TaskKind.NORMAL and task.effort_hours == 8.0


def test_a_project_of_only_checkpoints_has_no_progress_percent() -> None:
    progress = summarize_progress(project(checkpoint("c")), {}, MON)
    assert progress.percent is None
    assert progress.counts[Status.NOT_STARTED] == 1  # 件数には含める


def test_checkpoints_do_not_weigh_the_progress_percent() -> None:
    done = work("a", effort_hours=10, status=Status.DONE)
    progress = summarize_progress(project(done, checkpoint("c")), {}, MON)
    assert progress.percent == 100.0


def test_a_missed_checkpoint_is_listed_as_overdue_with_its_deadline() -> None:
    a = work("a", planned_start=MON, effort_hours=26)  # 木曜 15:30 まで
    c = checkpoint("c", WED_NOON, "a")
    progress = summarize_progress(project(a, c), {}, MON)  # 現在時刻は締切の前でも、見込みで超過
    rows = [row for row in progress.overdue if row.name == "c"]
    assert len(rows) == 1 and rows[0].limit == WED_NOON


def test_a_checkpoint_appears_once_in_the_due_list() -> None:
    c = checkpoint("c", WED_NOON)
    period = Period(datetime(2026, 10, 5).date(), datetime(2026, 10, 9).date())
    rows = summarize_due(project(c), period, MON, {})
    assert [(row.kind, row.name) for row in rows] == [("締切", "c")]


def test_checkpoints_are_left_out_of_the_workload() -> None:
    period = Period(datetime(2026, 10, 5).date(), datetime(2026, 10, 9).date())
    assert summarize_workload(project(checkpoint("c", WED_NOON)), period, MON, {}) == []


def test_a_checkpoint_keeps_and_replaces_its_links() -> None:
    existing = Task(
        "レビュー",
        kind=TaskKind.CHECKPOINT,
        deadline=datetime(2026, 10, 12, 17),
        urls=[TaskUrl("", None, {"URL": "https://example.com/a"})],
    )
    assert make(existing).urls == existing.urls
    replaced = [TaskUrl("資料", None, {"URL": "https://example.com/b"})]
    assert make(existing, urls=replaced).urls == replaced
