"""タスクの分解(1 つのタスクを、複数のタスクに割る)。NiceGUI には依存しない純粋関数。"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from math import isfinite

from projectapp.arrange import section_at, tasks_at
from projectapp.models import (
    MAX_SECTION_DEPTH,
    MAX_TASK_NAME_LENGTH,
    Actual,
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
from projectapp.reassign import consumed_hours
from projectapp.summary import parent_map
from projectapp.timeline import Schedule, assignees_rate, combine_rate, crew_on, effective_start, week_index

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


@dataclass(frozen=True)
class Settled:
    """実績・進捗度のあるタスクの分解で、消し込む分(消化分)と、残りを受け持つ担当。"""

    consumed: float  # 消化分(基準の人の時間)。1 つ目の子の工数になる
    crew: list[Assignee]  # 残りの子の担当(週ごとのタスクは、今日の週の担当)


def _worked_rate(project: Project, task: Task, start: date, interval_start: datetime) -> float:
    """実績の区間を数えるときの換算率。週ごとのタスクは、区間の開始の日の週の担当で数える。"""
    crew = crew_on(task, start, interval_start.date())
    return assignees_rate(crew, project.members, project.parameters, task.parameters)


def settle(project: Project, task: Task, holidays: dict[date, str], today: datetime) -> Settled | None:
    """実績か進捗度(1% 以上)のあるタスクの、消化分と残りの担当。どちらもなければ None(未着手のままの分解)。"""
    if not (task.actuals or (task.progress or 0) >= 1):
        return None
    start = effective_start(task, project, holidays, Schedule(project, holidays))
    anchor = (start or task.planned_start or today).date()
    if task.progress:  # None と 0 は、進捗度なし
        consumed = consumed_hours(task, 1.0)
    elif task.weekly_crew:
        worked = sum(
            (a.end - a.start).total_seconds() / 3600 * combine_rate(_worked_rate(project, task, anchor, a.start), 1.0)
            for a in task.actuals
            if a.end is not None and a.end > a.start
        )
        consumed = min(worked, task.effort_hours)
    else:
        consumed = consumed_hours(task, assignees_rate(task.assignees, project.members, project.parameters, task.parameters))
    crew = task.weekly_crew[week_index(anchor, today.date(), len(task.weekly_crew))] if task.weekly_crew else task.assignees
    return Settled(round(consumed, EFFORT_DECIMALS), [Assignee(a.name, a.allocation) for a in crew])


def default_parts_settled(task: Task, settled: Settled, count: int) -> list[Part]:
    """実績ありの分解のダイアログの初期値。1 行目は消し込み(工数=消化分)、残りは「工数 − 消化分」の均等割り。"""
    width = len(str(count)) + 1
    base = task.name[: MAX_TASK_NAME_LENGTH - width]
    remaining = split_effort(max(task.effort_hours - settled.consumed, 0.0), count - 1)
    return [Part(f"{base} 1", settled.consumed)] + [Part(f"{base} {n}", e) for n, e in enumerate(remaining, start=2)]


def can_make_section(path: SectionPath) -> str | None:
    """新しいセクションを作れない理由。作れるなら None。"""
    if not path:
        return "セクションに属さないタスクは、セクションにまとめられません"
    if len(path) >= MAX_SECTION_DEPTH:
        return f"セクションは {MAX_SECTION_DEPTH} 階層までです"
    return None


def decompose_block_reason(
    project: Project,
    task: Task,
    holidays: dict[date, str] | None = None,
    today: datetime | None = None,
) -> str | None:
    """そのタスクを分解できない理由。分解できるなら None。"""
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクだけ分解できます"
    if task.id in parent_map(project):
        return "まとめの子は分解できません"
    if not (task.actuals or (task.progress or 0) >= 1):
        if task.status is not Status.NOT_STARTED or task.progress is not None:
            return "状態が未着手でない、または進捗度のあるタスクは分解できません(分解すると失われます)"
        return None
    # 実績・進捗度のあるタスク: 残りの見積もりを割り、実績は 1 つ目の子へ消し込む
    if task.status is Status.DONE:
        return "終了したタスクは分解できません"
    if task.effort_hours <= 0:
        return "実績のあるタスクは、工数を入れてから分解してください"
    if not task.assignees:
        return "実績のあるタスクは、担当者を入れてから分解してください"
    if any(a.end is None for a in task.actuals):
        return "実行中のタスクは、先に実行を終えてから分解してください"
    settled = settle(project, task, holidays or {}, today or datetime.now())
    assert settled is not None
    if task.effort_hours - settled.consumed < 10 ** -EFFORT_DECIMALS:
        return "残りの工数がないため分解できません"
    return None


def _validate(
    project: Project, task: Task, parts: Sequence[Part], holidays: dict[date, str], today: datetime
) -> None:
    if (reason := decompose_block_reason(project, task, holidays, today)) is not None:
        raise ValueError(reason)
    settled = task.actuals or (task.progress or 0) >= 1
    low = 3 if settled else 2  # 実績があるときは、消し込みの 1 つ + 残りを割った 2 つ以上
    if not low <= len(parts) <= MAX_PARTS:
        raise ValueError(f"分解は {low}〜{MAX_PARTS} 件で指定してください")
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
    holidays: dict[date, str] | None = None,
    today: datetime | None = None,
) -> list[Task]:
    """`path` のセクションの `index` 番目のタスクを、`parts` の分だけの子に分解する。元のタスクはまとめとして残る。

    子は元の担当・カテゴリ・優先度・色・リンク・開始予定を引き継ぐ(工数は各行の値)。元の先行は最初の子へ移す
    (`chain` がオフなら全員が引き継ぐ)。締切は最後の子に渡す。不正なときは ValueError で、何も変えない。

    実績か進捗度のあるタスクは、1 つ目の子を消し込み(実績を引き継いで終了。工数=消化分)にし、残りの子には残りの見積もりを
    割る。消し込みの子は元の担当(週ごとなら全週の和集合)、残りの子は今の担当(週ごとなら今日の週)。週ごとの担当は、
    どの子にも持たせない(未着手の分解では、全員が第 1 週の担当になる)。
    """
    tasks = tasks_at(project, path)
    task = tasks[index]
    now = today or datetime.now()
    _validate(project, task, parts, holidays or {}, now)
    settled = settle(project, task, holidays or {}, now)
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
        done = settled is not None and n == 0  # 消し込みの子
        if settled is None:
            crew = task.weekly_crew[0] if task.weekly_crew else task.assignees
        else:
            crew = task.assignees if done else settled.crew
        children.append(
            Task(
                part.name.strip(),
                id=child_id,
                planned_start=task.planned_start,
                effort_hours=settled.consumed if done and settled else part.effort_hours,
                priority=task.priority,
                status=Status.DONE if done else Status.NOT_STARTED,
                color=task.color,
                assignees=[Assignee(a.name, a.allocation) for a in crew],
                actuals=[Actual(a.start, a.end) for a in task.actuals] if done else [],
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
        weekly_crew=[],
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
