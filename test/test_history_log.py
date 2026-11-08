"""変更履歴(要望 128)。NiceGUI に依存しない部分。"""

import json
from copy import deepcopy
from datetime import datetime

import pytest

from projectapp.history_log import (
    TaskState,
    diff_events,
    dirty_key,
    earliest,
    effective_progress,
    effort_weight,
    events_by_task,
    is_known,
    merge_logs,
    reconcile,
    record_edit,
    state_at,
    stamp_creation,
    states_at,
)
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


def test_turning_a_normal_task_into_a_summary_records_a_retirement() -> None:
    before = project_of(
        Task("a", id="a", effort_hours=8, progress=50, status=Status.RUNNING)
    )
    after = deepcopy(before)
    after.tasks[0].kind = TaskKind.SUMMARY
    events = diff_events(before, after, NOW)
    assert events == [
        ev(
            "a",
            NOW,
            status=("実行中", None),
            progress=(50, None),
            effort=(8.0, None),
        )
    ]
    assert state_at(after.tasks[0], events, datetime(2026, 11, 10)) is None


def test_a_task_that_is_deleted_records_no_retirement() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    assert diff_events(before, project_of(), NOW) == []


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


SINCE = datetime(2026, 11, 1, 0, 0)


def running_then_done() -> tuple[Project, Task]:
    task = Task("a", id="a", effort_hours=10, status=Status.DONE, progress=100)
    project = Project(
        "p",
        tasks=[task],
        history_since=SINCE,
        history=[
            ev(
                "a",
                datetime(2026, 11, 3, 10),
                status=("未着手", "実行中"),
                progress=(None, 50),
            ),
            ev(
                "a",
                datetime(2026, 11, 5, 10),
                status=("実行中", "終了"),
                progress=(50, 100),
            ),
        ],
    )
    return project, task


def test_state_before_the_first_event_uses_that_events_before_values() -> None:
    project, task = running_then_done()
    events = events_by_task(project)["a"]
    assert state_at(task, events, datetime(2026, 11, 2)) == TaskState(
        Status.NOT_STARTED, None, 10.0
    )


def test_state_between_events_uses_the_latest_after_values() -> None:
    project, task = running_then_done()
    events = events_by_task(project)["a"]
    assert state_at(task, events, datetime(2026, 11, 4)) == TaskState(
        Status.RUNNING, 50, 10.0
    )
    assert state_at(task, events, datetime(2026, 11, 6)) == TaskState(
        Status.DONE, 100, 10.0
    )


def test_state_without_any_event_is_the_current_value() -> None:
    task = Task("b", id="b", effort_hours=4, progress=20, status=Status.RUNNING)
    assert state_at(task, [], datetime(2026, 11, 4)) == TaskState(
        Status.RUNNING, 20, 4.0
    )


def test_a_task_created_after_the_moment_did_not_exist() -> None:
    task = Task("c", id="c", effort_hours=4)
    created = [
        ev(
            "c",
            datetime(2026, 11, 4),
            status=(None, "未着手"),
            progress=(None, None),
            effort=(None, 4.0),
        )
    ]
    assert state_at(task, created, datetime(2026, 11, 3)) is None
    assert state_at(task, created, datetime(2026, 11, 5)) == TaskState(
        Status.NOT_STARTED, None, 4.0
    )


def test_a_moment_exactly_at_an_event_does_not_include_it() -> None:
    project, task = running_then_done()
    events = events_by_task(project)["a"]
    state = state_at(task, events, datetime(2026, 11, 3, 10))
    assert state is not None and state.status is Status.NOT_STARTED


def test_history_is_unknown_before_it_started_or_when_never_recorded() -> None:
    project = Project("p", history_since=SINCE)
    assert not is_known(project, datetime(2026, 10, 31, 23, 59))
    assert is_known(project, SINCE)
    assert not is_known(Project("p"), datetime(2026, 11, 8))


def test_merge_logs_unions_dedupes_and_sorts() -> None:
    first = ev("a", datetime(2026, 11, 3), progress=(None, 10))
    second = ev("a", datetime(2026, 11, 4), progress=(10, 20))
    assert merge_logs([second, first], [first]) == [first, second]


def test_earliest_ignores_missing_moments() -> None:
    assert earliest(None, NOV8, SINCE) == SINCE
    assert earliest(None, None) is None


def test_reconcile_adds_a_correction_where_the_log_and_the_value_disagree() -> None:
    task = Task("a", id="a", progress=70, status=Status.RUNNING)
    project = Project(
        "p",
        tasks=[task],
        history=[ev("a", NOV8, status=("未着手", "実行中"), progress=(None, 50))],
    )
    assert reconcile(project, NOW) == 1
    assert project.history[-1] == ev("a", NOW, progress=(50, 70))


def test_reconcile_leaves_consistent_and_unlogged_tasks_alone() -> None:
    project = Project(
        "p",
        tasks=[
            Task("a", id="a", progress=50, status=Status.RUNNING),
            Task("b", id="b", progress=10),
        ],
        history=[ev("a", NOV8, status=("未着手", "実行中"), progress=(None, 50))],
    )
    assert reconcile(project, NOW) == 0 and len(project.history) == 1


@pytest.mark.parametrize("moment", [5, "2026-01-01T00:00:00+09:00", "x"])
def test_a_non_text_or_timezone_aware_moment_is_rejected(moment) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["history"] = [{"task": "t", "at": moment, "changes": {"progress": [0, 1]}}]
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")
    raw["history"] = []
    raw["history_since"] = moment
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_dirty_key_changes_with_the_history_and_with_the_rest() -> None:
    base = project_of(Task("a", id="a"))
    same = deepcopy(base)
    assert dirty_key(base) == dirty_key(same)
    appended = deepcopy(base)
    appended.history.append(ev("a", NOW, progress=(None, 10)))
    assert dirty_key(appended) != dirty_key(base)
    swapped = deepcopy(appended)
    swapped.history[-1] = ev("a", NOW, progress=(None, 20))
    assert dirty_key(swapped) != dirty_key(appended)  # 件数が同じでも最後が違えば違う
    renamed = deepcopy(base)
    renamed.tasks[0].name = "b"
    assert dirty_key(renamed) != dirty_key(base)
    started = deepcopy(base)
    started.history_since = NOW
    assert dirty_key(started) != dirty_key(base)


def test_states_at_matches_state_at_for_every_moment() -> None:
    task = Task("a", id="a", effort_hours=10, status=Status.DONE, progress=80)
    events = [
        ev("a", datetime(2026, 11, 3, 10), status=("未着手", "実行中"), progress=(None, 40)),
        ev("a", datetime(2026, 11, 5, 9), progress=(40, 80), effort=(10, 12)),
        ev("a", datetime(2026, 11, 6, 9), status=("実行中", "終了")),
    ]
    moments = [datetime(2026, 11, d, h) for d in range(2, 8) for h in (0, 12)]
    assert states_at(task, events, moments) == [
        state_at(task, events, m) for m in moments
    ]


def test_states_at_is_none_before_the_task_was_created_and_after_it_left() -> None:
    task = Task("s", id="s", kind=TaskKind.SUMMARY)
    events = [
        ev("s", datetime(2026, 11, 3), status=(None, "実行中"), progress=(None, 50), effort=(None, 10)),
        ev("s", datetime(2026, 11, 5), status=("実行中", None), progress=(50, None), effort=(10, None)),
    ]
    moments = [datetime(2026, 11, 2), datetime(2026, 11, 4), datetime(2026, 11, 6)]
    assert states_at(task, events, moments) == [
        None,
        TaskState(Status.RUNNING, 50, 10.0),
        None,
    ]


def test_states_at_without_events_is_the_current_value() -> None:
    task = Task("a", id="a", effort_hours=4, status=Status.PAUSED, progress=20)
    moments = [datetime(2026, 11, 2), datetime(2026, 11, 9)]
    assert states_at(task, [], moments) == [TaskState(Status.PAUSED, 20, 4.0)] * 2


def test_effort_weight_counts_missing_or_broken_effort_as_one_hour() -> None:
    assert effort_weight(6.5) == 6.5
    assert effort_weight(0) == 1.0
    assert effort_weight(-3) == 1.0
    assert effort_weight(float("nan")) == 1.0
    assert effort_weight(float("inf")) == 1.0


def test_effective_progress_is_100_when_done_and_zero_without_progress() -> None:
    assert effective_progress(TaskState(Status.DONE, 30, 1.0)) == 100.0
    assert effective_progress(TaskState(Status.RUNNING, 30, 1.0)) == 30.0
    assert effective_progress(TaskState(Status.RUNNING, None, 1.0)) == 0.0
