"""変更履歴(要望 128)。NiceGUI に依存しない部分。"""

import json
from copy import deepcopy
from datetime import datetime

import pytest

from projectapp.history_log import diff_events, record_edit, stamp_creation
from projectapp.models import (
    Change,
    HistoryEvent,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.storage import dumps_project, parse_project

pytestmark = pytest.mark.smoke


def ev(task: str, at: datetime, **fields: tuple) -> HistoryEvent:
    """`ev("a", at, status=("未着手", "実行中"), progress=(None, 30))`。項目は status, progress, effort の順で渡す。"""
    return HistoryEvent(
        task, at, tuple(Change(name, b, a) for name, (b, a) in fields.items())
    )


NOV8 = datetime(2026, 11, 8, 10, 0)


def test_history_round_trips_through_the_file() -> None:
    project = Project(
        "p",
        history=[ev("t1", NOV8, status=("未着手", "実行中"), progress=(None, 30))],
        history_since=datetime(2026, 11, 8, 9, 0),
    )
    loaded = parse_project(dumps_project(project), "p")
    assert loaded.history == project.history
    assert loaded.history_since == project.history_since


def test_a_version_20_file_is_read_without_history() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = 20
    del raw["history"], raw["history_since"]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.history == [] and loaded.history_since is None


@pytest.mark.parametrize(
    "bad",
    [
        {
            "task": "t",
            "at": "2026-11-08T10:00:00",
            "changes": {"status": ["未着手", "x"]},
        },
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"name": ["a", "b"]}},
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {}},
        {
            "task": "t",
            "at": "2026-11-08T10:00:00",
            "changes": {"progress": [None, 101]},
        },
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"effort": [None, -1]}},
        {"task": "", "at": "2026-11-08T10:00:00", "changes": {"progress": [0, 1]}},
        {"task": "t", "at": "not-a-date", "changes": {"progress": [0, 1]}},
        {"task": "t", "changes": {"progress": [0, 1]}},
    ],
)
def test_a_broken_history_entry_is_rejected(bad: dict) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["history"] = [bad]
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_copying_a_project_shares_the_events() -> None:
    event = ev("t1", NOV8, progress=(None, 30))
    assert deepcopy(event) is event


NOW = datetime(2026, 11, 9, 9, 0)


def project_of(*tasks: Task) -> Project:
    return Project("p", tasks=list(tasks))


def test_a_status_change_records_only_the_changed_fields() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    after = deepcopy(before)
    after.tasks[0].status = Status.RUNNING
    assert diff_events(before, after, NOW) == [
        ev("a", NOW, status=("未着手", "実行中"))
    ]


def test_status_and_progress_changed_together_make_one_event() -> None:
    before = project_of(
        Task("a", id="a", effort_hours=8, progress=50, status=Status.RUNNING)
    )
    after = deepcopy(before)
    after.tasks[0].status = Status.DONE
    after.tasks[0].progress = 100
    assert diff_events(before, after, NOW) == [
        ev("a", NOW, status=("実行中", "終了"), progress=(50, 100))
    ]


def test_an_effort_change_uses_the_total_with_extra_efforts() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    after = deepcopy(before)
    after.tasks[0].effort_hours = 12
    assert diff_events(before, after, NOW) == [ev("a", NOW, effort=(8.0, 12.0))]


def test_a_new_task_records_a_creation_event_with_every_field() -> None:
    before = project_of()
    after = project_of(Task("a", id="a", effort_hours=8))
    assert diff_events(before, after, NOW) == [
        ev("a", NOW, status=(None, "未着手"), progress=(None, None), effort=(None, 8.0))
    ]


def test_a_deleted_task_and_an_unchanged_one_record_nothing() -> None:
    before = project_of(Task("a", id="a"), Task("b", id="b"))
    after = project_of(Task("b", id="b"))
    assert diff_events(before, after, NOW) == []


def test_summaries_checkpoints_and_references_are_not_recorded() -> None:
    kinds = (TaskKind.SUMMARY, TaskKind.CHECKPOINT, TaskKind.REFERENCE)
    before = project_of()
    after = project_of(*[Task(k.name, id=k.name, kind=k) for k in kinds])
    assert diff_events(before, after, NOW) == []


def test_turning_a_normal_task_into_a_summary_records_nothing() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    after = deepcopy(before)
    after.tasks[0].kind = TaskKind.SUMMARY
    assert diff_events(before, after, NOW) == []


def test_tasks_inside_sections_are_recorded() -> None:
    before = Project("p", sections=[Section("s", [Task("a", id="a")])])
    after = deepcopy(before)
    after.sections[0].tasks[0].progress = 20
    assert diff_events(before, after, NOW) == [ev("a", NOW, progress=(None, 20))]


def test_record_edit_appends_and_sets_the_start_once() -> None:
    before = project_of(Task("a", id="a"))
    after = deepcopy(before)
    after.tasks[0].progress = 20
    record_edit(before, after, NOW)
    assert after.history_since == NOW and len(after.history) == 1
    later = datetime(2026, 11, 10, 9, 0)
    again = deepcopy(after)
    again.tasks[0].progress = 40
    record_edit(after, again, later)
    assert again.history_since == NOW and len(again.history) == 2


def test_stamp_creation_records_every_normal_task_and_the_start() -> None:
    project = project_of(
        Task("a", id="a", effort_hours=2, progress=30, status=Status.RUNNING),
        Task("c", id="c", kind=TaskKind.CHECKPOINT),
    )
    stamp_creation(project, NOW)
    assert project.history_since == NOW
    assert project.history == [
        ev("a", NOW, status=(None, "実行中"), progress=(None, 30), effort=(None, 2.0))
    ]
