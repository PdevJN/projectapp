from datetime import datetime

import pytest

from projectapp.forms import build_task
from projectapp.models import DEFAULT_COLOR, Priority, ReferenceValue, Status, Task, TaskKind


def built(existing: Task | None = None, **kwargs: object) -> Task:
    values: dict[str, object] = dict(
        name="a", planned_start="", planned_end="", deadline="", effort_hours=None,
        priority=Priority.MEDIUM, status=Status.NOT_STARTED, color=DEFAULT_COLOR,
    )
    return build_task(existing, **{**values, **kwargs})  # type: ignore[arg-type]


def test_build_task_makes_a_reference_row_with_only_the_shared_fields() -> None:
    task = built(kind=TaskKind.REFERENCE, ref_project="基盤", deadline="2026-12-01 17:00", color="#112233", name="基盤開発")
    assert (task.kind, task.ref_project, task.deadline) == (TaskKind.REFERENCE, "基盤", datetime(2026, 12, 1, 17))
    assert (task.effort_hours, task.assignees, task.actuals, task.status) == (0.0, [], [], Status.NOT_STARTED)


def test_build_task_needs_a_reference_target() -> None:
    with pytest.raises(ValueError, match="参照先のプロジェクトを選んでください"):
        built(kind=TaskKind.REFERENCE, ref_project="")


def test_changing_the_reference_target_drops_the_snapshot() -> None:
    existing = Task("基盤開発", kind=TaskKind.REFERENCE, ref_project="基盤", ref_snapshot=ReferenceValue(progress=10))
    same = built(existing, kind=TaskKind.REFERENCE, ref_project="基盤", name="基盤開発")
    other = built(existing, kind=TaskKind.REFERENCE, ref_project="共通", name="基盤開発")
    assert same.ref_snapshot is not None and other.ref_snapshot is None
