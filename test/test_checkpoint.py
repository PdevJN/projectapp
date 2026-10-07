from datetime import datetime
from pathlib import Path

import pytest

from projectapp import arrange
from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.storage import load_project, save_project
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
    assert (task.effort_hours, task.assignee, task.allocation, task.actuals) == (0.0, None, 1.0, [])
    assert task.deadline == DEADLINE
    assert loaded.members == []  # 担当は使わないので、メンバーも補わない


def test_copy_keeps_the_kind() -> None:
    project = Project("p", sections=[Section("A", [checkpoint("c")])])
    copy = arrange.copy_task(project, (0, 0), (0, 1))
    assert copy.kind is TaskKind.CHECKPOINT and copy.deadline == DEADLINE
