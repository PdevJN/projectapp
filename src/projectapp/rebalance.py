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
from projectapp.dashboard import (
    Candidate,
    LoadStats,
    Period,
    PeriodKind,
    summarize_backlog,
    summarize_loads,
)
from projectapp.forecast import forecast_end
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
from projectapp.timeline import Schedule, conversion_rate, crew_of, effective_end

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


@dataclass(frozen=True)
class LoadChange:
    name: str
    before: LoadStats
    after: LoadStats


@dataclass(frozen=True)
class TaskChange:
    task_id: str
    name: str
    end_before: datetime | None  # 完了予定
    end_after: datetime | None
    forecast_before: datetime | None  # 完了見込み
    forecast_after: datetime | None
    reviewed: bool  # 完了予定を見直した


@dataclass(frozen=True)
class Preview:
    edited: Project
    loads: list[LoadChange]
    tasks: list[TaskChange]
    candidates: list[Candidate]  # 調整後の余力(余力の多い順)

    @property
    def review_count(self) -> int:
        return sum(1 for change in self.tasks if change.reviewed)


def preview(
    project: Project,
    owner: str,
    edits: Sequence[Edit],
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
) -> Preview:
    """調整の前後の負荷(owner と、移し先・追加先)・完了予定・完了見込み・余力。何も変えない。"""
    edited = apply_edits(project, owner, edits, holidays, now)
    before = summarize_loads(project, period, holidays)
    after = summarize_loads(edited, period, holidays)
    involved = list(
        dict.fromkeys(
            [owner, *(e.name for e in edits if e.name is not None and e.kind != "rate")]
        )
    )
    loads = [LoadChange(n, before[n], after[n]) for n in involved if n in before]
    schedule_before = Schedule(project, holidays)
    schedule_after = Schedule(edited, holidays)
    changes: list[TaskChange] = []
    for edit in edits:
        old, new = project.task_map()[edit.task_id], edited.task_map()[edit.task_id]
        found_before = forecast_end(old, project, holidays, now, schedule_before)
        found_after = forecast_end(new, edited, holidays, now, schedule_after)
        changes.append(
            TaskChange(
                edit.task_id,
                new.name,
                effective_end(old, project, holidays, schedule_before),
                effective_end(new, edited, holidays, schedule_after),
                None if found_before is None else found_before.end,
                None if found_after is None else found_after.end,
                new.planned_end_manual and new.planned_end != old.planned_end,
            )
        )
    return Preview(
        edited,
        loads,
        changes,
        summarize_backlog(edited, period, kind, now, holidays).candidates,
    )


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def stats_text(name: str, stats: LoadStats) -> str:
    return (
        f"{name}: 平均 {_percent(stats.average)} / 最大 {_percent(stats.peak)}"
        f" / 割り当て超過 {stats.overload_days} 日"
    )


def load_text(change: LoadChange) -> str:
    before, after = change.before, change.after
    return (
        f"{change.name}: 平均 {_percent(before.average)} → {_percent(after.average)}"
        f" / 最大 {_percent(before.peak)} → {_percent(after.peak)}"
        f" / 割り当て超過 {before.overload_days} 日 → {after.overload_days} 日"
    )


def _moment(value: datetime | None) -> str:
    return "-" if value is None else f"{value:%m/%d %H:%M}"


def task_text(change: TaskChange) -> str:
    text = f"{change.name}: 完了予定 {_moment(change.end_before)} → {_moment(change.end_after)}"
    if change.forecast_before is not None or change.forecast_after is not None:
        text += (
            f" / 完了見込み {_moment(change.forecast_before)}"
            f" → {_moment(change.forecast_after)}"
        )
    if change.reviewed:
        text += "(完了予定を見直し)"
    return text


def edit_from_inputs(
    task_id: str,
    mode: Literal["none", "rate", "move", "add"],
    name: str | None,
    percent: float | None,
    current: float | None,
) -> Edit | None:
    """1 行の入力(モード・相手・率[%])から調整を作る。変更にならないとき(そのまま・相手がない・今と同じ率)は None。"""
    rate = None if percent is None else percent / 100
    if mode == "rate":
        if rate is None or (current is not None and abs(rate - current) < RATE_EPSILON):
            return None
        return Edit(task_id, "rate", rate=rate)
    if mode == "move" and name is not None:
        return Edit(task_id, "move", name, rate)
    if mode == "add" and name is not None:
        return Edit(task_id, "add", name, rate)
    return None


def target_options(
    project: Project, owner: str, candidates: Sequence[Candidate]
) -> dict[str, str]:
    """移し先・追加先の選択肢(名前 → 表示)。余力の多い順で余力(時間)を添え、候補にいない人は名前だけで後ろに並べる。owner は除く。"""
    spare = {c.name: c.spare_hours for c in candidates}
    names = [n for n in spare if n != owner]
    names += [
        m.name for m in project.members if m.name != owner and m.name not in spare
    ]
    return {n: (f"{n}(余力 {spare[n]:.1f}h)" if n in spare else n) for n in names}
