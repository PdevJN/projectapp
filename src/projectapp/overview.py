"""系統図の、階層の変換と座標の計算。NiceGUI には依存しない純粋関数。"""

import unicodedata
from dataclasses import dataclass, field, replace
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


NODE_WIDTH = 200
GAP_X = 48
GAP_Y = 12
LINE_HEIGHT = 18
PADDING = 8


NAME_WIDTH = 15  # 名前の 1 行の幅。全角を 1、半角を 0.5 として数える
NAME_MAX_LINES = 3


def _char_width(char: str) -> float:
    return 1.0 if unicodedata.east_asian_width(char) in ("W", "F") else 0.5


def wrap_name(name: str) -> list[str]:
    """名前を、幅(全角 15 文字分)で折り返す。3 行を超える分は、3 行目の末尾を…で切る。"""
    lines: list[str] = []
    current, used = "", 0.0
    for char in name:
        width = _char_width(char)
        if used + width > NAME_WIDTH:
            lines.append(current)
            current, used = "", 0.0
        current += char
        used += width
    lines.append(current)
    if len(lines) <= NAME_MAX_LINES:
        return lines
    last = lines[NAME_MAX_LINES - 1]
    while last and sum(_char_width(c) for c in last) + 1 > NAME_WIDTH:
        last = last[:-1]
    return [*lines[: NAME_MAX_LINES - 1], last + "…"]


def node_lines(node: OverviewNode, show_progress: bool, show_effort: bool) -> list[str]:
    """ノードに出す文字(画面と PDF で共通)。先頭は、折り返した名前(`Placed.name_lines` 行)。"""
    lines = wrap_name(node.name)
    if show_progress and node.progress is not None:
        lines.append(f"進捗 {node.progress}%")
    if show_effort:
        parts = []
        if node.effort_hours:
            parts.append(f"工数 {node.effort_hours:g}h")
        if node.due is not None:
            parts.append(f"完了 {node.due.month}/{node.due.day}")
        if parts:
            lines.append("・".join(parts))
    return lines


@dataclass
class Placed:
    node: OverviewNode
    lines: list[str]
    x: int
    y: int
    width: int
    height: int
    depth: int
    name_lines: int = 1  # lines のうち、先頭の何行が名前か


@dataclass
class Edge:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class Layout:
    placed: list[Placed]
    edges: list[Edge]
    width: int
    height: int


_STRUCTURE = (NodeKind.SECTION, NodeKind.SUMMARY)


def _without_tasks(node: OverviewNode) -> OverviewNode:
    """セクションとまとめだけを残した写し(集計の値は、元のまま)。"""
    return replace(
        node,
        children=[
            _without_tasks(child) for child in node.children if child.kind in _STRUCTURE
        ],
    )


def layout_overview(
    root: OverviewNode,
    show_progress: bool,
    show_effort: bool,
    show_tasks: bool = True,
) -> Layout:
    """左から右へ、深さが列、兄弟が縦に並ぶ座標。親は、子の範囲の中央に置く(同じ列の上と重ならない範囲で)。
    `show_tasks`が偽のときは、セクションとまとめだけにする。"""
    if not show_tasks:
        root = _without_tasks(root)
    placed: list[Placed] = []
    edges: list[Edge] = []
    next_leaf = [0]  # 次の葉を置く y
    column_floor: dict[int, int] = {}  # 列ごとの、次に置ける最小の y

    def place(node: OverviewNode, depth: int) -> Placed:
        lines = node_lines(node, show_progress, show_effort)
        names = len(wrap_name(node.name))
        height = PADDING * 2 + LINE_HEIGHT * len(lines)
        kids = [place(child, depth + 1) for child in node.children]
        if kids:
            top = kids[0].y
            bottom = kids[-1].y + kids[-1].height
            y = round((top + bottom - height) / 2)
        else:
            y = next_leaf[0]
        y = max(y, column_floor.get(depth, 0))
        column_floor[depth] = y + height + GAP_Y
        next_leaf[0] = max(next_leaf[0], y + height + GAP_Y)
        me = Placed(
            node,
            lines,
            depth * (NODE_WIDTH + GAP_X),
            y,
            NODE_WIDTH,
            height,
            depth,
            names,
        )
        placed.append(me)
        for kid in kids:
            edges.append(
                Edge(
                    me.x + NODE_WIDTH,
                    y + height // 2,
                    kid.x,
                    kid.y + kid.height // 2,
                )
            )
        return me

    place(root, 0)
    placed.sort(key=lambda p: (p.depth, p.y))
    width = max(p.x + p.width for p in placed)
    height = max(p.y + p.height for p in placed)
    return Layout(placed, edges, width, height)
