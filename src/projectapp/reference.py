"""プロジェクト参照: 参照先のプロジェクト全体の値の算出と、参照先の読み込み。NiceGUI に依存しない。"""

from datetime import date, datetime

from projectapp.dashboard import _progress_weight
from projectapp.models import OverloadSpan, Project, ReferenceValue, Status, Task, TaskKind
from projectapp.timeline import Schedule, is_overdue, overallocations

COUNTED_KINDS = (TaskKind.NORMAL, TaskKind.CHECKPOINT)  # 数えるのは通常タスクと節目だけ(まとめは二重になり、参照行は循環のもと)


def _counted(project: Project) -> list[Task]:
    return [task for task in project.all_tasks() if task.kind in COUNTED_KINDS]


def compute_reference(project: Project, holidays: dict[date, str], now: datetime) -> ReferenceValue:
    """参照先のプロジェクト全体の予定・実績・進捗・遅延・負荷。数えるタスクがなければ、日程なしの値。"""
    tasks = _counted(project)
    schedule = Schedule(project, holidays)
    starts = [moment for task in tasks if (moment := schedule.start(task)) is not None]
    ends = [moment for task in tasks if (moment := schedule.end(task)) is not None]
    intervals = [a for task in tasks for a in task.actuals]
    finished_ends = [a.end for a in intervals if a.end is not None]
    running = any(a.end is None for a in intervals)
    weights = [w for task in tasks if (w := _progress_weight(task)) is not None]
    total = sum(weight for weight, _ in weights)
    progress = round(sum(weight * percent for weight, percent in weights) / total) if total > 0 else None
    delayed = sum(1 for task in tasks if task.status is not Status.DONE and is_overdue(task, project, holidays, now, schedule))
    overloads = tuple(
        OverloadSpan(o.member, o.start, o.end, o.total) for o in overallocations(project, holidays, tasks)
    )
    peak = max(overloads, key=lambda o: o.total, default=None)
    return ReferenceValue(
        planned_start=min(starts, default=None),
        planned_end=max(ends, default=None),
        actual_start=min((a.start for a in intervals), default=None),
        actual_end=None if running or not finished_ends else max(finished_ends),
        progress=progress,
        finished=bool(tasks) and all(task.status is Status.DONE for task in tasks),
        delayed=delayed,
        peak_load=peak.total if peak else 0.0,
        peak_member=peak.member if peak else "",
        overloads=overloads,
    )
