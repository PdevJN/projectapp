"""残りの工数の計算(要望 98・103)。ダッシュボードと警告の判定が共有する。NiceGUI に依存しない純粋関数。"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta

from projectapp.models import Project, Task, WorkDay
from projectapp.reassign import consumed_hours
from projectapp.timeline import combine_rate, conversion_rate, day_window


def total_effort(task: Task) -> float:
    """タスクの工数の合計[h]。残りの工数・警告の判定・ダッシュボードの按分は、工数をここから取る。
    後から追加工数を足せるようにする(要望 105)ときは、ここに追加分を足す。"""
    return task.effort_hours


def overlap_hours(
    project: Project,
    holidays: dict[date, str],
    day: date,
    start: datetime,
    end: datetime,
    work_days: Mapping[date, WorkDay] | None = None,
) -> float:
    """その日の稼働の枠のうち、[start, end) と重なる時間[h]。work_days があれば、その人の上書きを反映する。"""
    window = day_window(
        day, project.daily_hours, project.work_start, holidays, work_days
    )
    if window is None:
        return 0.0
    return max(
        0.0, (min(end, window[1]) - max(start, window[0])).total_seconds() / 3600
    )


def open_hours(
    task: Task, project: Project, holidays: dict[date, str], now: datetime, limit: float
) -> float:
    """終了のない実績の区間が、今までに稼働の枠の中で積んだ時間[h]。`limit` に達したら数えるのをやめる。"""
    total = 0.0
    for interval in task.actuals:
        if interval.end is not None or interval.start >= now:
            continue
        day = interval.start.date()
        while day <= now.date():
            total += overlap_hours(project, holidays, day, interval.start, now)
            if total >= limit:
                return total
            day += timedelta(days=1)
    return total


def remaining_hours(
    task: Task, project: Project, holidays: dict[date, str], now: datetime
) -> float:
    """残りの工数。工数から消化分を引く。消化分は、進捗度があれば工数 × 進捗度、
    なければ実績の区間 × 換算率(開いたままの区間は、今までに稼働の枠で積んだ時間)。
    状態は手入力なので、未着手でも進捗度か実績があれば引く(なければ全量)。"""
    effort = total_effort(task)
    rate = conversion_rate(task, project)
    done = consumed_hours(task, rate)
    if not task.progress:  # 進捗度があれば、そちらを優先する(None と 0 は進捗度なし)
        factor = combine_rate(rate, 1.0)
        done = min(
            done + open_hours(task, project, holidays, now, effort / factor) * factor,
            effort,
        )
    return effort - done
