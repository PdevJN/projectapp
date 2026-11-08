"""完了見込み(要望 133): 進捗(残りの工数)を見た、今日からの完了日。NiceGUI に依存しない純粋関数。

当初の完了予定(`effective_end`)は変えない。見込みは保存せず、表示のたびに算出する。
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite

from projectapp.daily_crew import rows_of, with_added_from
from projectapp.models import (
    Project,
    Status,
    Task,
    TaskKind,
)
from projectapp.pace import warning_pace
from projectapp.remaining import remaining_hours
from projectapp.timeline import (
    Schedule,
    calc_end,
    crew_of,
    crew_track,
    effective_end,
    effective_start,
)


@dataclass(frozen=True)
class Forecast:
    end: datetime  # 完了見込み
    planned_end: datetime | None  # 当初の完了予定(effective_end)

    @property
    def days_later(self) -> int | None:
        """見込み − 当初の予定の日数(早ければ負)。当初の予定がなければ None。"""
        if self.planned_end is None:
            return None
        return (self.end.date() - self.planned_end.date()).days


def _has_progress(task: Task) -> bool:
    return bool(task.progress) or bool(task.actuals)


def forecast_end(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule,
    extra_crew: tuple[tuple[str, ...], date] | None = None,
) -> Forecast | None:
    """今日(または実効の開始)から、残りの工数を今の担当で消化して終わる日時。出さないときは None。

    通常タスクで、終了しておらず、残りの工数があり、実効の開始が今日以前のものが対象。
    進捗度も実績もないタスクは、予定超過か警告のときだけ出す(経過日数ぶん常に遅く出るのを避ける)。
    extra_crew = (増員の名前の列, 増員日)は要望 132 の試算用。増員日は丸めずそのまま使う(週頭ならその週以降、週の途中ならその週だけ日ごと)。
    """
    if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None or start > now:
        return None
    planned = effective_end(task, project, holidays, schedule)
    rest = remaining_hours(task, project, holidays, now)
    if not (isfinite(rest) and rest > 0):
        return None
    if not _has_progress(task):
        overdue = planned is not None and planned <= now
        if not overdue and warning_pace(task, project, holidays, now, schedule) is None:
            return None
    origin = max(now, start)
    anchor = start.date()  # 週の区切りは常に実効の開始から数える(確定後の担当と同じ)
    weekly, daily = rows_of(task)
    if extra_crew is not None:
        names, day = extra_crew
        added = with_added_from(weekly, daily, (day - anchor).days, names)
        if added is None:
            return None
        weekly, daily = added
    track = crew_track(
        weekly,
        daily,
        lambda crew: crew_of(
            crew,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        ),
    )
    end = calc_end(
        origin,
        rest,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=track,
        weeks_start=anchor,
    )
    return None if end is None else Forecast(end, planned)
