"""タスクの絞り込み条件と判定。NiceGUI には依存しない。"""

from dataclasses import dataclass

from projectapp.models import Section, Task


@dataclass(frozen=True)
class TaskFilter:
    query: str = ""  # タスク名への部分一致(大文字小文字を区別しない)
    assignee: str | None = None  # None なら全員

    @property
    def active(self) -> bool:
        return bool(self.query.strip()) or self.assignee is not None


def matches(task: Task, task_filter: TaskFilter) -> bool:
    """検索と担当者の両方に合うとき True。条件が空なら常に True。"""
    if task_filter.assignee is not None and task_filter.assignee not in task.assignee_names:
        return False
    return task_filter.query.strip().casefold() in task.name.casefold()


def visible_task_indexes(section: Section, task_filter: TaskFilter, collapsed: bool) -> list[int]:
    """セクションで描くタスクの添字。絞り込み中は折りたたみを無視し、一致したものだけを返す。"""
    if task_filter.active:
        return [i for i, task in enumerate(section.tasks) if matches(task, task_filter)]
    return [] if collapsed else list(range(len(section.tasks)))


def section_has_match(section: Section, task_filter: TaskFilter) -> bool:
    """セクション自身か、子孫のどれかのタスクが条件に合うか。条件が空なら常に True。"""
    if not task_filter.active:
        return True
    return any(matches(task, task_filter) for task in section.tasks) or any(
        section_has_match(child, task_filter) for child in section.sections
    )
