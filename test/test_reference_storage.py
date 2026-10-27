import json
from datetime import datetime

import pytest

from projectapp.models import (
    FORMAT_VERSION,
    OverloadSpan,
    Project,
    ReferenceMode,
    ReferenceValue,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.storage import dumps_project, parse_project

VALUE = ReferenceValue(
    planned_start=datetime(2026, 9, 7, 9),
    planned_end=datetime(2026, 11, 20, 17),
    actual_start=datetime(2026, 9, 7, 10),
    actual_end=None,
    progress=45,
    finished=False,
    delayed=3,
    peak_load=1.3,
    peak_member="田中",
    overloads=(OverloadSpan("田中", datetime(2026, 10, 1, 9), datetime(2026, 10, 3, 9), 1.3),),
    taken_at=datetime(2026, 10, 25, 10),
)


def reference_task(**kwargs: object) -> Task:
    return Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤", **kwargs)  # type: ignore[arg-type]


def test_format_version_is_12() -> None:
    assert FORMAT_VERSION == 13


def test_a_reference_task_round_trips_with_its_snapshot() -> None:
    project = Project("p", reference_mode=ReferenceMode.SNAPSHOT, sections=[Section("s", [reference_task(ref_snapshot=VALUE)])])
    loaded = parse_project(dumps_project(project), "p")
    task = loaded.sections[0].tasks[0]
    assert loaded.reference_mode is ReferenceMode.SNAPSHOT
    assert (task.kind, task.ref_project, task.ref_snapshot) == (TaskKind.REFERENCE, "基盤", VALUE)


def test_a_live_project_drops_the_snapshots_on_load() -> None:
    project = Project("p", reference_mode=ReferenceMode.LIVE, tasks=[reference_task(ref_snapshot=VALUE)])
    assert parse_project(dumps_project(project), "p").tasks[0].ref_snapshot is None


def test_an_old_file_reads_with_the_defaults() -> None:
    raw = json.loads(dumps_project(Project("p", tasks=[Task("a")])))
    raw["version"] = 10
    del raw["reference_mode"]
    for task in raw["tasks"]:
        del task["ref_project"], task["ref_snapshot"]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.reference_mode is ReferenceMode.LIVE and loaded.tasks[0].ref_project == ""


def test_unused_fields_of_a_reference_task_are_emptied_on_load() -> None:
    task = reference_task(effort_hours=8.0, status=Status.RUNNING, progress=30, urls=[], category_id=None)
    loaded = parse_project(dumps_project(Project("p", tasks=[task])), "p").tasks[0]
    assert (loaded.effort_hours, loaded.status, loaded.progress, loaded.assignees, loaded.actuals) == (
        0.0, Status.NOT_STARTED, None, [], [],
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw["tasks"][0].update(ref_project=""), "参照先"),
        (lambda raw: raw["tasks"][0].update(ref_project=3), "参照先"),
        (lambda raw: raw["tasks"][0].update(ref_project="p"), "自分自身"),
        (lambda raw: raw.update(reference_mode="auto"), "参照の方式"),
        (lambda raw: raw["tasks"][0].update(ref_snapshot={"progress": "x"}), "スナップショット"),
    ],
)
def test_invalid_references_are_rejected(change, message: str) -> None:
    project = Project("p", reference_mode=ReferenceMode.SNAPSHOT, tasks=[reference_task(ref_snapshot=VALUE)])
    raw = json.loads(dumps_project(project))
    change(raw)
    with pytest.raises(ValueError, match=message):
        parse_project(json.dumps(raw), "p")
