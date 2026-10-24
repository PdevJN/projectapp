"""タスクの分解(1 つのタスクを、複数のタスクに割る)。NiceGUI には依存しない純粋関数。"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import isfinite

from projectapp.arrange import section_at, tasks_at
from projectapp.models import (
    MAX_SECTION_DEPTH,
    MAX_TASK_NAME_LENGTH,
    Assignee,
    Project,
    Section,
    SectionPath,
    Status,
    Task,
    TaskKind,
    has_control_char,
    new_id,
)
from projectapp.summary import parent_map

MAX_PARTS = 20  # 一度に分けられる数の上限
EFFORT_DECIMALS = 2  # 工数の小数点以下の桁数(forms.HOURS_DECIMALS と同じ。forms は NiceGUI に依存するのでここに持つ)


@dataclass(frozen=True)
class Part:
    name: str
    effort_hours: float


def split_effort(total: float, count: int) -> list[float]:
    """工数を count 等分する(小数点以下 2 桁)。端数は最後に寄せて、合計を保つ。"""
    each = round(total / count, EFFORT_DECIMALS)
    parts = [each] * (count - 1)
    return [*parts, round(total - each * (count - 1), EFFORT_DECIMALS)]


def default_parts(task: Task, count: int) -> list[Part]:
    """ダイアログの初期値。名前は`<元の名前> n`(上限に収める)、工数は均等割り。"""
    efforts = split_effort(task.effort_hours, count)
    width = len(str(count)) + 1
    base = task.name[: MAX_TASK_NAME_LENGTH - width]
    return [Part(f"{base} {n}", efforts[n - 1]) for n in range(1, count + 1)]


def can_make_section(path: SectionPath) -> str | None:
    """新しいセクションを作れない理由。作れるなら None。"""
    if not path:
        return "セクションに属さないタスクは、セクションにまとめられません"
    if len(path) >= MAX_SECTION_DEPTH:
        return f"セクションは {MAX_SECTION_DEPTH} 階層までです"
    return None


def decompose_block_reason(project: Project, task: Task) -> str | None:
    """そのタスクを分解できない理由。分解できるなら None。"""
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクだけ分解できます"
    if task.actuals:
        return "実績のあるタスクは分解できません"
    if task.status is not Status.NOT_STARTED or task.progress is not None:
        return "状態が未着手でない、または進捗度のあるタスクは分解できません(分解すると失われます)"
    if task.id in parent_map(project):
        return "まとめの子は分解できません"
    return None


def _validate(project: Project, task: Task, parts: Sequence[Part]) -> None:
    if (reason := decompose_block_reason(project, task)) is not None:
        raise ValueError(reason)
    if not 2 <= len(parts) <= MAX_PARTS:
        raise ValueError(f"分解は 2〜{MAX_PARTS} 件で指定してください")
    for part in parts:
        name = part.name.strip()
        if not name:
            raise ValueError("名前を入力してください")
        if len(name) > MAX_TASK_NAME_LENGTH:
            raise ValueError(f"名前は{MAX_TASK_NAME_LENGTH}文字以内で入力してください")
        if has_control_char(name):
            raise ValueError("名前に改行・制御文字は使えません")
        if not isfinite(part.effort_hours) or part.effort_hours < 0:
            raise ValueError("工数は 0 以上の数値で入力してください")
        if round(part.effort_hours, EFFORT_DECIMALS) != part.effort_hours:
            raise ValueError(f"工数は小数点以下{EFFORT_DECIMALS}桁までで入力してください")


def _unique_name(name: str, taken: Sequence[str]) -> str:
    if name not in taken:
        return name
    n = 2
    while f"{name}#{n}" in taken:
        n += 1
    return f"{name}#{n}"


def decompose(
    project: Project,
    path: SectionPath,
    index: int,
    parts: Sequence[Part],
    *,
    chain: bool = True,
    new_section: bool = False,
) -> list[Task]:
    """`path` のセクションの `index` 番目のタスクを、`parts` の分だけの子に分解する。元のタスクはまとめとして残る。

    子は元の担当・カテゴリ・優先度・色・リンク・開始予定を引き継ぐ(工数は各行の値)。元の先行は最初の子へ移す
    (`chain` がオフなら全員が引き継ぐ)。締切は最後の子に渡す。不正なときは ValueError で、何も変えない。
    """
    tasks = tasks_at(project, path)
    task = tasks[index]
    _validate(project, task, parts)
    parent_section: Section | None = None
    if new_section:
        reason = can_make_section(path)
        if reason is not None:
            raise ValueError(reason)
        parent_section = section_at(project, path)
        assert parent_section is not None
    taken = project.used_ids()
    children: list[Task] = []
    for n, part in enumerate(parts):
        child_id = new_id(taken)
        taken.add(child_id)
        if n == 0 or not chain:
            predecessors = list(task.predecessors)
        else:
            predecessors = [children[n - 1].id]
        children.append(
            Task(
                part.name.strip(),
                id=child_id,
                planned_start=task.planned_start,
                effort_hours=part.effort_hours,
                priority=task.priority,
                status=Status.NOT_STARTED,
                color=task.color,
                assignees=[Assignee(a.name, a.allocation) for a in task.assignees],
                predecessors=predecessors,
                deadline=task.deadline if n == len(parts) - 1 else None,
                category_id=task.category_id,
                urls=[replace(u, values=dict(u.values)) for u in task.urls],
                parameters=list(task.parameters),
            )
        )
    tasks[index] = replace(
        task,
        kind=TaskKind.SUMMARY,
        children=[c.id for c in children],
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=None,
        effort_hours=0.0,
        assignees=[],
        predecessors=[],
        actuals=[],
        progress=None,
        parameters=[],
        status=Status.NOT_STARTED,
    )
    if parent_section is not None:
        name = _unique_name(task.name, [s.name for s in parent_section.sections])
        parent_section.sections.append(Section(name, list(children), id=new_id(taken)))
    else:
        tasks[index + 1 : index + 1] = children
    return children
