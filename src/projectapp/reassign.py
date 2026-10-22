"""担当の付け替えで換算率が変わったときの、完了予定の見直し(純粋関数。NiceGUI に依存しない)。"""

from collections.abc import Mapping
from datetime import date, datetime, time

from projectapp.models import Status, Task, TaskKind, WorkDay
from projectapp.timeline import calc_end, combine_rate

RATE_TOLERANCE = 1e-9  # 換算率が変わったとみなす差


def consumed_hours(task: Task, old_rate: float) -> float:
    """消化分(基準の人の時間)。進捗度があれば 工数 × 進捗度、なければ 実績の区間の合計時間 × 旧換算率。"""
    if task.effort_hours <= 0:
        return 0.0
    if task.progress:  # None と 0 は、進捗度なし
        done = task.effort_hours * task.progress / 100
    else:
        worked = sum(  # 進行中の区間(終了なし)は数えない
            (a.end - a.start).total_seconds() / 3600 for a in task.actuals if a.end is not None and a.end > a.start
        )
        done = worked * combine_rate(old_rate, 1.0)
    return min(max(done, 0.0), task.effort_hours)


def needs_review(task: Task, old_rate: float, new_rate: float) -> bool:
    """付け替えの保存で、完了予定の見直しを選ばせるか。task は編集後のタスク。"""
    return (
        task.kind is TaskKind.NORMAL
        and task.effort_hours > 0
        and task.status is not Status.DONE
        and bool(task.actuals or (task.progress or 0) >= 1)
        and abs(old_rate - new_rate) > RATE_TOLERANCE
    )


def reviewed_end(
    task: Task,
    old_rate: float,
    new_rate: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    now: datetime,
    work_days: Mapping[date, WorkDay] | None = None,
) -> datetime | None:
    """残りの工数(工数 − 消化分)を新換算率で割り当てた完了予定。残りがない・算出できないときは None。"""
    remaining = task.effort_hours - consumed_hours(task, old_rate)
    if remaining <= 0:
        return None
    start = max(now, task.planned_start) if task.planned_start else now
    return calc_end(start, remaining / combine_rate(new_rate, 1.0), daily_hours, work_start, holidays, work_days)
