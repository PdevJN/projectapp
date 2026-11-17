"""負荷の調整(要望 145)。NiceGUI に依存しない純粋関数。

選んだ人(owner)の担当を、率の変更・他の人への移し替え・別の人の追加で調整した複製を作る。
週ごと・日ごとの担当を持つタスクは、owner が出てくる全週・全日に同じ操作を一括で当てる(いない週・日は変えない)。
"""

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from projectapp.crew_trial import replace_task
from projectapp.daily_crew import WEEK_DAYS, rows_of
from projectapp.models import (
    MAX_ALLOCATION,
    MIN_ALLOCATION,
    Assignee,
    Project,
    Status,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.reassign import needs_review, reviewed_end
from projectapp.timeline import conversion_rate, crew_of

ADD_DEFAULT_RATE = 0.5  # 足す人の割り当て率の既定(元の人の率は変えない)
RATE_EPSILON = 1e-9
Kind = Literal["rate", "move", "add"]


@dataclass(frozen=True)
class Edit:
    """1 タスクへの調整。rate: 新しい率 / move: 移し先(name)と移し先の率(rate。省くと元の率)
    / add: 足す人(name)と率(rate。省くと 50%)。"""

    task_id: str
    kind: Kind
    name: str | None = None
    rate: float | None = None


def adjustable(task: Task, owner: str) -> bool:
    """owner の調整の対象になるか。通常タスクで、終了しておらず、owner が担当しているもの。"""
    return (
        task.kind is TaskKind.NORMAL
        and task.status is not Status.DONE
        and owner in task.assignee_names
    )


def tasks_of(project: Project, owner: str) -> list[Task]:
    """owner の調整できるタスク(プロジェクトの並び順)。"""
    return [task for task in project.all_tasks() if adjustable(task, owner)]


def _rates_of(task: Task, owner: str) -> list[float]:
    weekly, daily = rows_of(task)
    crews = list(weekly)
    for days in daily.values():
        crews.extend(days)
    return [a.allocation for crew in crews for a in crew if a.name == owner]


def rate_of(task: Task, owner: str) -> float | None:
    """owner の割り当て率。週・日によって違う、またはいないときは None。"""
    rates = _rates_of(task, owner)
    if not rates or max(rates) - min(rates) >= RATE_EPSILON:
        return None
    return rates[0]


def has_varying_rate(task: Task, owner: str) -> bool:
    rates = _rates_of(task, owner)
    return bool(rates) and max(rates) - min(rates) >= RATE_EPSILON


def rate_text(task: Task, owner: str) -> str:
    """owner の今の割り当て率の表示。週・日によって違うときは`50〜100%`の範囲。"""
    rates = _rates_of(task, owner)
    if not rates:
        return "-"
    low, high = min(rates), max(rates)
    if high - low < RATE_EPSILON:
        return f"{low * 100:.0f}%"
    return f"{low * 100:.0f}〜{high * 100:.0f}%"


def _check_rate(rate: float | None, required: bool) -> None:
    if rate is None:
        if required:
            raise ValueError("割り当て率を入れてください")
        return
    if not MIN_ALLOCATION <= rate <= MAX_ALLOCATION:
        raise ValueError(
            f"割り当て率は{MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}%で入力してください"
        )


def _check(project: Project, owner: str, edit: Edit) -> Task:
    task = project.task_map().get(edit.task_id)
    if task is None:
        raise ValueError("タスクが見つかりません")
    if not adjustable(task, owner):
        raise ValueError(f"{task.name}は調整できません")
    if edit.kind == "rate":
        _check_rate(edit.rate, True)
    elif edit.kind in ("move", "add"):
        if edit.name is None or edit.name not in {m.name for m in project.members}:
            raise ValueError("メンバーを選んでください")
        if edit.name == owner:
            raise ValueError("同じ人には移せません")
        _check_rate(edit.rate, False)
    else:
        raise ValueError("調整の種類が正しくありません")
    return task


def _crew_edit(crew: list[Assignee], owner: str, edit: Edit) -> list[Assignee]:
    """1 つの担当の並び(1 週・1 日・タスク全体)に調整を当てる。owner がいない並びは変えない。"""
    copy = [Assignee(a.name, a.allocation) for a in crew]
    names = {a.name for a in crew}
    if owner not in names:
        return copy
    if edit.kind == "rate":
        assert edit.rate is not None
        return [
            Assignee(a.name, edit.rate if a.name == owner else a.allocation)
            for a in copy
        ]
    assert edit.name is not None
    if edit.kind == "add":
        if edit.name in names:
            return copy
        rate = ADD_DEFAULT_RATE if edit.rate is None else edit.rate
        return [*copy, Assignee(edit.name, rate)]
    moved: list[Assignee] = []
    for a in copy:
        if a.name != owner:
            moved.append(a)
        elif edit.name not in names:  # 移し先がすでにいるときは、いる側の率を残す
            moved.append(
                Assignee(edit.name, a.allocation if edit.rate is None else edit.rate)
            )
    return moved


def _edited(task: Task, owner: str, edit: Edit) -> Task:
    if not task.weekly_crew:
        return replace(task, assignees=_crew_edit(task.assignees, owner, edit))
    weekly, daily = rows_of(task)
    weekly = [_crew_edit(week, owner, edit) for week in weekly]
    daily = {
        number: [_crew_edit(day, owner, edit) for day in days]
        for number, days in daily.items()
    }
    for number, days in daily.items():
        if number < len(weekly) and len(days) == WEEK_DAYS:
            weekly[number] = union_assignees(days)
    return replace(
        task,
        weekly_crew=weekly,
        daily_crew=daily,
        assignees=union_assignees(weekly),
    )


def _reviewed(
    old: Task, new: Task, project: Project, holidays: dict[date, str], now: datetime
) -> Task:
    """換算率が変わるタスクの完了予定を、担当の付け替えと同じ規則で見直す(手で指定の完了予定にする)。"""
    old_rate, new_rate = conversion_rate(old, project), conversion_rate(new, project)
    if not needs_review(new, old_rate, new_rate):
        return new
    end = reviewed_end(
        new,
        old_rate,
        new_rate,
        project.daily_hours,
        project.work_start,
        holidays,
        now,
        crew_of(new.assignees, project.members),
    )
    if end is None:
        return new
    return replace(new, planned_end=end, planned_end_manual=True)


def apply_edits(
    project: Project,
    owner: str,
    edits: Sequence[Edit],
    holidays: dict[date, str],
    now: datetime,
) -> Project:
    """調整を当てた複製を返す(project は変えない)。正しくないときは ValueError。"""
    result = deepcopy(project)
    seen: set[str] = set()
    for edit in edits:
        if edit.task_id in seen:
            raise ValueError("同じタスクを 2 回調整できません")
        seen.add(edit.task_id)
        old = _check(result, owner, edit)
        new = _reviewed(old, _edited(old, owner, edit), result, holidays, now)
        replace_task(result, new)
    return result
