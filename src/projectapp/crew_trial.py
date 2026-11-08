"""遅延対応(要望 132): 遅れた分の増員の試算。NiceGUI に依存しない純粋関数。

試算は保存しない。確定すると `Task.weekly_crew` に乗る(ファイル形式は変えない)。
"""

from dataclasses import dataclass, replace
from datetime import date, datetime

from projectapp.models import (
    MAX_WEEKS,
    Assignee,
    Project,
    Section,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.timeline import (
    Schedule,
    calc_end,
    crew_of,
    effective_end,
    effective_start,
)


@dataclass(frozen=True)
class TrialCrew:
    """だれを・どのタスクに・いつから増員するかの試算(画面の中だけ)。start は丸める前の指定日。"""

    task_id: str
    names: tuple[str, ...]
    start: date


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    names: tuple[str, ...]
    first_week: int  # 増員が始まる週(0 始まり)
    original_end: datetime | None
    trial_end: datetime | None  # 手動指定の完了予定のタスクは None
    manual: bool

    @property
    def days_earlier(self) -> int | None:
        if self.original_end is None or self.trial_end is None:
            return None
        return (self.original_end.date() - self.trial_end.date()).days


def snap_week(anchor: date, day: date) -> int:
    """増員日を、実効の開始から 7 日ごとの週の境目に、遅い側へ丸めた週の添字(0 始まり)。開始より前は第 1 週。"""
    days = (day - anchor).days
    return 0 if days <= 0 else -(-days // 7)


def trial_weeks(
    task: Task, trial: TrialCrew, anchor: date
) -> list[list[Assignee]] | None:
    """今の担当に増員分を足した週ごとの担当。週数が上限を超えるなら None。"""
    first = snap_week(anchor, trial.start)
    if first >= MAX_WEEKS:
        return None
    base = [list(w) for w in task.weekly_crew] or [list(task.assignees)]
    while len(base) <= first:
        base.append([replace(a) for a in base[-1]])
    weeks: list[list[Assignee]] = []
    for number, week in enumerate(base):
        crew = [replace(a) for a in week]
        if number >= first:
            present = {a.name for a in crew}
            crew += [Assignee(n) for n in trial.names if n not in present]
        weeks.append(crew)
    return weeks


def _target(task: Task) -> bool:
    return task.kind is TaskKind.NORMAL and bool(task.assignees or task.weekly_crew)


def _manual(task: Task) -> bool:
    return task.planned_end is not None and task.planned_end_manual


def evaluate(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    trial: TrialCrew,
) -> TrialResult | None:
    """増員後の完了見込み。対象外(担当なし・通常でない・開始なし・上限超え)は None。"""
    if not _target(task):
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    weeks = trial_weeks(task, trial, start.date())
    if weeks is None:
        return None
    original = effective_end(task, project, holidays, schedule)
    first = snap_week(start.date(), trial.start)
    if _manual(task):
        return TrialResult(task.id, trial.names, first, original, None, True)
    crews = [
        crew_of(
            week,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        )
        for week in weeks
    ]
    end = calc_end(
        start,
        task.total_effort,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=crews,
    )
    return TrialResult(task.id, trial.names, first, original, end, False)


def confirmed(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    trial: TrialCrew,
) -> Task | None:
    """試算を確定したタスク(weekly_crew に乗せ、assignees は和集合)。対象外は None。"""
    if not _target(task):
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    weeks = trial_weeks(task, trial, start.date())
    if weeks is None:
        return None
    return replace(task, weekly_crew=weeks, assignees=union_assignees(weeks))


def _replace_in(tasks: list[Task], task: Task) -> bool:
    for index, existing in enumerate(tasks):
        if existing.id == task.id:
            tasks[index] = task
            return True
    return False


def _replace_in_sections(sections: list[Section], task: Task) -> bool:
    for section in sections:
        if _replace_in(section.tasks, task) or _replace_in_sections(
            section.sections, task
        ):
            return True
    return False


def replace_task(project: Project, task: Task) -> bool:
    """同じ id のタスクを差し替える。なければ False。"""
    return _replace_in(project.tasks, task) or _replace_in_sections(
        project.sections, task
    )
