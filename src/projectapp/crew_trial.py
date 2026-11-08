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
from projectapp.pace import warning_pace
from projectapp.remaining import remaining_hours
from projectapp.timeline import (
    Schedule,
    Worker,
    calc_end,
    crew_of,
    crew_on,
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
    from_now: bool = False  # 完了予定を過ぎたタスク: 今日からの残り工数で出した見込み
    baseline_end: datetime | None = None  # from_now のとき、増員しない場合の見込み

    @property
    def days_earlier(self) -> int | None:
        """増員で早まる日数。遅れたタスクは、増員しない場合の見込みとの差。"""
        base = self.baseline_end if self.from_now else self.original_end
        if base is None or self.trial_end is None:
            return None
        return (base.date() - self.trial_end.date()).days


def snap_week(anchor: date, day: date) -> int:
    """増員日を、実効の開始から 7 日ごとの週の境目に、遅い側へ丸めた週の添字(0 始まり)。開始より前は第 1 週。"""
    days = (day - anchor).days
    return 0 if days <= 0 else -(-days // 7)


def trial_weeks(
    task: Task, trial: TrialCrew, anchor: date
) -> list[list[Assignee]] | None:
    """今の担当に増員分を足した週ごとの担当。週数が上限を超えるなら None。"""
    return _with_added(
        [list(w) for w in task.weekly_crew] or [list(task.assignees)],
        snap_week(anchor, trial.start),
        trial.names,
    )


def _with_added(
    base: list[list[Assignee]], first: int, names: tuple[str, ...]
) -> list[list[Assignee]] | None:
    """base の週ごとの担当の、first 週以降に names を足す(重複なし)。上限を超えるなら None。"""
    if first >= MAX_WEEKS:
        return None
    while len(base) <= first:
        base.append([replace(a) for a in base[-1]])
    weeks: list[list[Assignee]] = []
    for number, week in enumerate(base):
        crew = [replace(a) for a in week]
        if number >= first:
            present = {a.name for a in crew}
            crew += [Assignee(n) for n in names if n not in present]
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
    now: datetime,
) -> TrialResult | None:
    """増員後の完了見込み。対象外(担当なし・通常でない・開始なし・上限超え)は None。
    完了予定を過ぎたタスクと警告のタスクは、今日からの残りの工数を、増員後の担当で消化する見込みにする。"""
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

    def crews_of(rows: list[list[Assignee]]) -> list[list[Worker]]:
        return [
            crew_of(
                week,
                project.members,
                project.parameters,
                task.parameters,
                project.ratio_limits,
            )
            for week in rows
        ]

    overdue = original is not None and original <= now and start <= now
    if overdue or warning_pace(task, project, holidays, now, schedule) is not None:
        # 遅れたタスクと警告のタスク: 今日を起点に、残りの工数を消化する。今日の担当に、増員分を足す
        origin = max(now, start)
        remaining = remaining_hours(task, project, holidays, now)
        today_crew = [replace(a) for a in crew_on(task, start.date(), origin.date())]
        added = _with_added(
            [list(today_crew)], snap_week(origin.date(), trial.start), trial.names
        )
        if added is None:
            return None

        def finish(rows: list[list[Assignee]]) -> datetime | None:
            return calc_end(
                origin,
                remaining,
                project.daily_hours,
                project.work_start,
                holidays,
                weeks=crews_of(rows),
            )

        return TrialResult(
            task.id,
            trial.names,
            first,
            original,
            finish(added),
            False,
            from_now=True,
            baseline_end=finish([today_crew]),
        )
    end = calc_end(
        start,
        task.total_effort,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=crews_of(weeks),
    )
    return TrialResult(task.id, trial.names, first, original, end, False)


def confirmed(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    trial: TrialCrew,
) -> Task | None:
    """試算を確定したタスク(weekly_crew に乗せ、assignees は和集合)。対象外は None。
    増員は次の週の境目から載せる(過去の週の担当を変えないので、過去の棒は縮まない)。"""
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
