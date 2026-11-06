"""タスクの絞り込み条件と判定。NiceGUI には依存しない。"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from projectapp.models import Project, Section, Task, TaskKind


@dataclass(frozen=True)
class TaskFilter:
    query: str = ""  # タスク名への部分一致(大文字小文字を区別しない)
    assignee: str | None = None  # None なら全員
    exclude: frozenset[str] = (
        frozenset()
    )  # 描かないタスクの id(画像の書き出しで、チェックを外したものを除く)
    team: str | None = None  # 絞り込み中のチーム名。assignee とは同時に使わない
    team_members: frozenset[str] = (
        frozenset()
    )  # そのチームのメンバー名(名簿が変わったら gantt が更新する)

    @property
    def active(self) -> bool:
        return (
            bool(self.query.strip())
            or self.assignee is not None
            or self.team is not None
            or bool(self.exclude)
        )


def _own_match(task: Task, task_filter: TaskFilter) -> bool:
    """タスク自身が、担当者・チーム・検索語のすべてに合うか(絞り込み用の除外は見ない)。"""
    return (
        (task_filter.assignee is None or task_filter.assignee in task.assignee_names)
        and (
            task_filter.team is None
            or not task_filter.team_members.isdisjoint(task.assignee_names)
        )
        and (task_filter.query.strip().casefold() in task.name.casefold())
    )


def _under_matched_summary(
    task: Task, task_filter: TaskFilter, by_id: Mapping[str, Task]
) -> bool:
    """親のまとめが、検索に自分で合うか(合うまとめは、子をすべて出す。まとめは入れ子にならない)。"""
    return any(
        parent.kind is TaskKind.SUMMARY
        and task.id in parent.children
        and parent.id not in task_filter.exclude
        and _own_match(parent, task_filter)
        for parent in by_id.values()
    )


def matches(
    task: Task, task_filter: TaskFilter, by_id: Mapping[str, Task] | None = None
) -> bool:
    """検索と担当者の両方に合うとき True。条件が空なら常に True。
    `by_id`(id → タスク)を渡すと、まとめの扱いが加わる。
    - 子のどれかが合えば、まとめも合う。
    - 検索語がまとめの名前に合えば、その子もすべて合う(まとめ名で探すと、まとめの中身が見える)。"""
    if task.id in task_filter.exclude:
        return False
    own = _own_match(task, task_filter)
    if (
        own
        and task_filter.exclude
        and by_id is not None
        and task.kind is TaskKind.SUMMARY
        and task.children
    ):
        own = any(
            cid not in task_filter.exclude for cid in task.children if cid in by_id
        )
    if own:
        return True
    if by_id is None:
        return False
    if task.kind is TaskKind.SUMMARY and any(
        matches(by_id[cid], task_filter) for cid in task.children if cid in by_id
    ):
        return True
    return bool(task_filter.query.strip()) and _under_matched_summary(
        task, task_filter, by_id
    )


def visible_task_indexes(
    section: Section,
    task_filter: TaskFilter,
    collapsed: bool,
    by_id: Mapping[str, Task] | None = None,
) -> list[int]:
    """セクションで描くタスクの添字。絞り込み中は折りたたみを無視し、一致したものだけを返す。"""
    if task_filter.active:
        return [
            i
            for i, task in enumerate(section.tasks)
            if matches(task, task_filter, by_id)
        ]
    return [] if collapsed else list(range(len(section.tasks)))


def section_has_match(
    section: Section, task_filter: TaskFilter, by_id: Mapping[str, Task] | None = None
) -> bool:
    """セクション自身か、子孫のどれかのタスクが条件に合うか。条件が空なら常に True。"""
    if not task_filter.active:
        return True
    return any(matches(task, task_filter, by_id) for task in section.tasks) or any(
        section_has_match(child, task_filter, by_id) for child in section.sections
    )


def hidden_by_summary(
    project: Project, collapsed_summaries: Collection[str]
) -> set[str]:
    """折りたたんだまとめの子の id。"""
    by_id = project.task_map()
    return {
        cid
        for sid in collapsed_summaries
        if (task := by_id.get(sid)) is not None and task.kind is TaskKind.SUMMARY
        for cid in task.children
    }
