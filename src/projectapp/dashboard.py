"""ダッシュボードの集計。NiceGUI に依存しない純粋関数。"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from math import isfinite

from projectapp.models import Project, Status
from projectapp.timeline import (
    OVERLOAD_EPSILON,
    actual_end,
    counted_span,
    current_progress,
    effective_end,
    is_overdue,
    is_workday,
)


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
            else:
                moments.append(datetime.combine(today, time.min))  # 実行中の区間は、今日まで数える
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


UNASSIGNED = "未割り当て"
DEADLINE = "締切"
PLANNED_END = "完了予定"


@dataclass(frozen=True)
class LoadStats:
    average: float  # 稼働日ごとの、同時刻の割り当て率の合計の最大(その日の負荷)の平均(1.0 = 100%)
    peak: float
    overload_days: int  # 100% を超えた稼働日の数


@dataclass(frozen=True)
class WorkloadRow:
    name: str
    planned_hours: float
    actual_hours: float


@dataclass(frozen=True)
class DueRow:
    moment: datetime
    kind: str
    name: str
    assignee: str | None
    overdue: bool


def _workdays(period: Period, holidays: dict[date, str]) -> list[date]:
    return [day for day in period.days() if is_workday(day, holidays)]


def _covers(start: datetime, end: datetime, day: date) -> bool:
    """[start, end) が、その日(0 時から翌 0 時)と重なる。"""
    return start < datetime.combine(day + timedelta(days=1), time.min) and end > datetime.combine(day, time.min)


def _day_peak(items: list[tuple[datetime, datetime, float]], day: date) -> float:
    """その日の、同じ時刻に重なる割り当て率の合計の最大。割り当て超過の縞(同時刻の重なり)と同じ基準。"""
    low = datetime.combine(day, time.min)
    high = low + timedelta(days=1)
    clipped = [(max(start, low), min(end, high), a) for start, end, a in items if start < high and end > low]
    points = sorted({p for start, end, _ in clipped for p in (start, end)})
    return max(
        (sum(a for start, end, a in clipped if start <= left and right <= end) for left, right in zip(points, points[1:])),
        default=0.0,
    )


def summarize_loads(project: Project, period: Period, holidays: dict[date, str]) -> dict[str, LoadStats]:
    days = _workdays(period, holidays)
    spans: dict[str, list[tuple[datetime, datetime, float]]] = {}
    for task in project.all_tasks():
        counted = counted_span(task, project, holidays)
        if counted is not None and task.assignee is not None:
            spans.setdefault(task.assignee, []).append((*counted, task.allocation))
    loads: dict[str, LoadStats] = {}
    for member in project.members:
        items = spans.get(member.name, [])
        totals = [_day_peak(items, day) for day in days]
        loads[member.name] = LoadStats(
            sum(totals) / len(totals) if totals else 0.0,
            max(totals, default=0.0),
            sum(1 for total in totals if total > 1.0 + OVERLOAD_EPSILON),
        )
    return loads


def summarize_workload(
    project: Project, period: Period, now: datetime, holidays: dict[date, str]
) -> list[WorkloadRow]:
    names = [member.name for member in project.members]
    planned = {name: 0.0 for name in (*names, UNASSIGNED)}
    actual = {name: 0.0 for name in (*names, UNASSIGNED)}
    days = _workdays(period, holidays)
    low, high = period.bounds()
    for task in project.all_tasks():
        key = task.assignee if task.assignee in names else UNASSIGNED
        start, end = task.planned_start, effective_end(task, project, holidays)
        if start is not None and end is not None and end > start and isfinite(task.allocation):
            count = sum(1 for day in days if _covers(start, end, day))
            planned[key] += task.allocation * project.daily_hours * count
        for interval in task.actuals:
            seconds = (min(interval.end or now, high) - max(interval.start, low)).total_seconds()
            if seconds > 0:
                actual[key] += seconds / 3600
    rows = [WorkloadRow(name, planned[name], actual[name]) for name in names]
    if planned[UNASSIGNED] or actual[UNASSIGNED]:
        rows.append(WorkloadRow(UNASSIGNED, planned[UNASSIGNED], actual[UNASSIGNED]))
    return rows


def summarize_due(
    project: Project, period: Period, now: datetime, holidays: dict[date, str]
) -> list[DueRow]:
    low, high = period.bounds()
    rows: list[DueRow] = []
    for task in project.all_tasks():
        if task.status is Status.DONE:
            continue
        late = is_overdue(task, project, holidays, now)
        for kind, moment in ((DEADLINE, task.deadline), (PLANNED_END, effective_end(task, project, holidays))):
            if kind == PLANNED_END and moment == task.deadline:
                continue  # 締切だけのタスクは、完了予定が締切と同じになる。同じ日時の 2 行にしない
            if moment is not None and low <= moment < high:
                rows.append(DueRow(moment, kind, task.name, task.assignee, late))
    rows.sort(key=lambda row: (row.moment, row.kind))
    return rows


@dataclass
class Dashboard:
    period: Period
    progress: Progress
    loads: dict[str, LoadStats]
    workload: list[WorkloadRow]
    due: list[DueRow]

    @property
    def planned_total(self) -> float:
        return sum(row.planned_hours for row in self.workload)

    @property
    def actual_total(self) -> float:
        return sum(row.actual_hours for row in self.workload)


def summarize(project: Project, period: Period, now: datetime, holidays: dict[date, str]) -> Dashboard:
    return Dashboard(
        period,
        summarize_progress(project, holidays, now),
        summarize_loads(project, period, holidays),
        summarize_workload(project, period, now, holidays),
        summarize_due(project, period, now, holidays),
    )
