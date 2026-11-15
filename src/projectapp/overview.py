"""俯瞰図(系統図)の、階層の変換と座標の計算。NiceGUI には依存しない純粋関数。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from projectapp.dashboard import _progress_weight
from projectapp.models import (
    Project,
    Section,
    SectionPath,
    Status,
    Task,
    TaskKind,
)
from projectapp.summary import children_of, parent_map, summary_status
from projectapp.timeline import Schedule, effective_end, is_overdue


class NodeKind(StrEnum):
    SECTION = "セクション"
    SUMMARY = "まとめ"
    TASK = "タスク"
    CHECKPOINT = "チェックポイント"
    REFERENCE = "プロジェクト参照"


@dataclass
class OverviewNode:
    id: str
    name: str
    kind: NodeKind
    status: Status
    late: bool = False  # 予定超過・期限超過(赤)
    progress: int | None = None  # 0〜100。出せないときは None
    effort_hours: float | None = None
    due: datetime | None = None
    children: list["OverviewNode"] = field(default_factory=list)
    first_task_id: str | None = None  # クリックで移る先のタスク


_KINDS = {
    TaskKind.SUMMARY: NodeKind.SUMMARY,
    TaskKind.CHECKPOINT: NodeKind.CHECKPOINT,
    TaskKind.REFERENCE: NodeKind.REFERENCE,
}


def _percent(tasks: list[Task]) -> int | None:
    """配下の通常タスクの、工数で重みづけした進捗率。数えるものがなければ None。"""
    pairs = [
        pair
        for task in tasks
        if task.kind is TaskKind.NORMAL  # まとめ・参照・節目は、二重に数えない
        if (pair := _progress_weight(task)) is not None
    ]
    total = sum(weight for weight, _ in pairs)
    if not pairs or total <= 0:
        return None
    return round(sum(weight * percent for weight, percent in pairs) / total)


def _hours(tasks: list[Task]) -> float | None:
    values = [t.total_effort for t in tasks if t.kind is TaskKind.NORMAL]
    return sum(values) if values else None


class _Builder:
    def __init__(
        self, project: Project, holidays: dict[date, str], now: datetime
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.now = now
        self.by_id = project.task_map()
        self.in_summary = set(parent_map(project))
        self.schedule = Schedule(project, holidays)

    def task_node(self, task: Task) -> OverviewNode:
        kind = _KINDS.get(task.kind, NodeKind.TASK)
        late = is_overdue(task, self.project, self.holidays, self.now, self.schedule)
        due = effective_end(task, self.project, self.holidays, self.schedule)
        if task.kind is TaskKind.SUMMARY:
            kids = children_of(task, self.by_id)
            return OverviewNode(
                task.id,
                task.name,
                kind,
                summary_status(kids),
                late,
                _percent(kids),
                _hours(kids),
                due,
                [self.task_node(kid) for kid in kids],
                task.id,
            )
        percent = None
        if task.kind is TaskKind.NORMAL and (pair := _progress_weight(task)):
            percent = round(pair[1])
        return OverviewNode(
            task.id,
            task.name,
            kind,
            task.status,
            late,
            percent,
            task.total_effort if task.kind is TaskKind.NORMAL else None,
            due,
            [],
            task.id,
        )

    def section_node(self, section: Section) -> OverviewNode:
        tasks = section.all_tasks()
        # セクション直下のタスクのうち、まとめの子は、まとめの下だけに出す
        children = [
            self.task_node(task)
            for task in section.tasks
            if task.id not in self.in_summary
        ] + [self.section_node(child) for child in section.sections]
        leaves = [t for t in tasks if t.kind is TaskKind.NORMAL]
        return OverviewNode(
            section.id,
            section.name,
            NodeKind.SECTION,
            summary_status(leaves) if leaves else Status.NOT_STARTED,
            False,
            _percent(tasks),
            _hours(tasks),
            None,
            children,
            tasks[0].id if tasks else None,
        )


def build_overview(
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    *,
    section_path: SectionPath | None = None,
    summary_id: str | None = None,
) -> OverviewNode:
    """セクション(パスで指す)かまとめ(id で指す)の配下を、ツリーにする。どちらか一方だけを渡す。"""
    if (section_path is None) == (summary_id is None):
        raise ValueError(
            "section_path か summary_id のどちらか一方だけを渡してください"
        )
    builder = _Builder(project, holidays, now)
    if summary_id is not None:
        task = builder.by_id.get(summary_id)
        if task is None or task.kind is not TaskKind.SUMMARY:
            raise ValueError(f"まとめが見つかりません: {summary_id}")
        return builder.task_node(task)
    assert section_path is not None
    sections = project.sections
    node: Section | None = None
    for index in section_path:
        node = sections[index]
        sections = node.sections
    if node is None:
        raise ValueError("セクションのパスが空です")
    return builder.section_node(node)
