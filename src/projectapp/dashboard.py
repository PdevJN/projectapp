"""ダッシュボードの集計。NiceGUI に依存しない純粋関数。"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from math import isfinite

from projectapp.models import Project, Status
from projectapp.timeline import actual_end, current_progress, effective_end, is_overdue


class PeriodKind(StrEnum):
    WEEK = "今週"
    MONTH = "今月"
    ALL = "全期間"


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # 両端を含む

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    def bounds(self) -> tuple[datetime, datetime]:
        """[開始日の 0 時, 終了日の翌日の 0 時)。"""
        return datetime.combine(self.start, time.min), datetime.combine(self.end + timedelta(days=1), time.min)


def period_for(kind: PeriodKind, today: date, project: Project, holidays: dict[date, str]) -> Period:
    if kind is PeriodKind.WEEK:
        start = today - timedelta(days=today.weekday())
        return Period(start, start + timedelta(days=6))
    if kind is PeriodKind.MONTH:
        return Period(today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1]))
    moments: list[datetime] = []
    for task in project.all_tasks():
        for moment in (task.planned_start, task.deadline, effective_end(task, project, holidays)):
            if moment is not None:
                moments.append(moment)
        for actual in task.actuals:
            moments.append(actual.start)
            if actual.end is not None:
                moments.append(actual.end)
    if not moments:
        return Period(today, today)
    return Period(min(moments).date(), max(moments).date())


@dataclass(frozen=True)
class OverdueRow:
    name: str
    assignee: str | None
    limit: datetime  # 過ぎている基準(締切と完了予定のうち、早いほう)


@dataclass
class Progress:
    percent: float | None  # 工数で重みづけした進捗率(0〜100)。タスクがなければ None
    counts: dict[Status, int]
    overdue: list[OverdueRow]


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def summarize_progress(project: Project, holidays: dict[date, str], now: datetime) -> Progress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    overdue: list[OverdueRow] = []
    for task in project.all_tasks():
        counts[task.status] += 1
        weight = _weight(task.effort_hours)
        percent = 100 if task.status is Status.DONE else (current_progress(task) or 0)
        weighted += weight * percent
        total += weight
        if task.status is not Status.DONE and is_overdue(task, project, holidays, now):
            moment = actual_end(task) or now
            limits = [
                limit
                for limit in (task.deadline, effective_end(task, project, holidays))
                if limit is not None and moment > limit
            ]
            overdue.append(OverdueRow(task.name, task.assignee, min(limits)))
    overdue.sort(key=lambda row: row.limit)
    return Progress(weighted / total if total else None, counts, overdue)
