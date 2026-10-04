"""タスクの絞り込み条件と判定。NiceGUI には依存しない。"""

from dataclasses import dataclass

from projectapp.models import Task


@dataclass(frozen=True)
class TaskFilter:
    query: str = ""  # タスク名への部分一致(大文字小文字を区別しない)
    assignee: str | None = None  # None なら全員

    @property
    def active(self) -> bool:
        return bool(self.query.strip()) or self.assignee is not None


def matches(task: Task, task_filter: TaskFilter) -> bool:
    """検索と担当者の両方に合うとき True。条件が空なら常に True。"""
    if task_filter.assignee is not None and task.assignee != task_filter.assignee:
        return False
    return task_filter.query.strip().casefold() in task.name.casefold()
