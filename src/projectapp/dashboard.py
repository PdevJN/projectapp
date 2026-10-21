"""ダッシュボードの集計。NiceGUI に依存しない純粋関数。"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from math import isfinite
from typing import NamedTuple

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.timeline import (
    OVERLOAD_EPSILON,
    Schedule,
    actual_end,
    counted_assignees,
    counted_span,
    current_progress,
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
    schedule = Schedule(project, holidays)
    for task in _tasks(project):
        for moment in (schedule.start(task), task.deadline, schedule.end(task)):
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


def assignee_label(task: Task) -> str | None:
    """担当者の名前を「、」でつなぐ。担当なしは None。"""
    return "、".join(task.assignee_names) or None


@dataclass(frozen=True)
class OverdueRow:
    name: str
    assignee: str | None
    limit: datetime  # 過ぎている基準(締切と完了予定のうち、早いほう)


@dataclass(frozen=True)
class MemberProgress:
    name: str
    percent: float | None  # 工数で重みづけした進捗率(0〜100)。担当のタスクがなければ None
    counts: dict[Status, int]


@dataclass
class Progress:
    percent: float | None  # 工数で重みづけした進捗率(0〜100)。タスクがなければ None
    counts: dict[Status, int]
    overdue: list[OverdueRow]
    by_member: list[MemberProgress] = field(default_factory=list)  # メンバーごと。絞り込み中は空


def _tasks(project: Project, member: str | None = None) -> list[Task]:
    """集計の対象のタスク。まとめは、子の工数・進捗・期限を二重に数えないよう外す。`member`があれば、その人が担当のものだけ。"""
    return [
        task
        for task in project.all_tasks()
        if task.kind is not TaskKind.SUMMARY and (member is None or member in task.assignee_names)
    ]


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def _progress_weight(task: Task) -> tuple[float, float] | None:
    """進捗率の重みと、その進み具合(0〜100)。節目は工数がないので None。"""
    if task.kind is TaskKind.CHECKPOINT:
        return None
    return _weight(task.effort_hours), 100 if task.status is Status.DONE else (current_progress(task) or 0)


@dataclass
class TeamProgress:
    percent: float | None = None  # 工数で重みづけした進捗率(0〜100)。タスクがなければ None
    hours: dict[Status, float] = field(default_factory=lambda: {status: 0.0 for status in Status})
    period: Period | None = None  # 絞り込んだ期間。None は全期間(すべてのタスク)
    counts: dict[Status, int] = field(default_factory=lambda: {status: 0 for status in Status})  # 円に数えたタスクの件数
    tasks: dict[Status, list[str]] = field(default_factory=lambda: {status: [] for status in Status})  # その名前(並び順)

    @property
    def total(self) -> float:
        return sum(self.hours.values())

    def slices(self) -> list[tuple[Status, float, float]]:
        """円の切片(状態, 工数, 全体に対する割合)。工数のない状態は出さない。"""
        total = self.total
        return [(status, hours, hours / total) for status, hours in self.hours.items() if hours > 0]


def _touches(task: Task, schedule: Schedule, period: Period, now: datetime) -> bool:
    """予定の期間・締切・実績のどれかが、期間にかかる。"""
    low, high = period.bounds()
    start, end = schedule.start(task), schedule.end(task)
    if start is not None and end is not None and start < high and (end > low or start >= low):
        return True
    if task.deadline is not None and low <= task.deadline < high:
        return True
    return any(a.start < high and (a.end or now) > low for a in task.actuals)


def summarize_team_progress(
    project: Project,
    period: Period | None = None,
    now: datetime | None = None,
    holidays: dict[date, str] | None = None,
    member: str | None = None,
) -> TeamProgress:
    """チーム全体の進捗。担当者に関わらず、1 タスクを 1 回だけ数える。`period` があれば、期間にかかるタスクだけ。"""
    hours = {status: 0.0 for status in Status}
    counts = {status: 0 for status in Status}
    names: dict[Status, list[str]] = {status: [] for status in Status}
    weighted = total = 0.0
    schedule = Schedule(project, holidays or {})
    moment = now or datetime.now()
    for task in _tasks(project, member):
        weight_and_percent = _progress_weight(task)
        if weight_and_percent is None or (period is not None and not _touches(task, schedule, period, moment)):
            continue
        weight, percent = weight_and_percent
        hours[task.status] += weight
        counts[task.status] += 1
        names[task.status].append(task.name)
        weighted += weight * percent
        total += weight
    return TeamProgress(weighted / total if total else None, hours, period, counts, names)


def _member_row(name: str, tasks: list[Task]) -> MemberProgress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    for task in tasks:
        counts[task.status] += 1
        if (weight_and_percent := _progress_weight(task)) is not None:  # 節目は重みに入れない
            weight, percent = weight_and_percent
            weighted += weight * percent
            total += weight
    return MemberProgress(name, weighted / total if total else None, counts)


def summarize_member_progress(project: Project) -> list[MemberProgress]:
    """メンバーごとの進捗。共同タスクは担当の全員の行に数える。メンバーが担当にいないタスクは`未割り当て`。"""
    if not project.members:
        return []
    tasks = _tasks(project)
    names = {member.name for member in project.members}
    rows = [_member_row(m.name, [t for t in tasks if m.name in t.assignee_names]) for m in project.members]
    # 節目は担当を持てず、進捗の重みもないので、割り当て漏れには数えない
    nobody = [t for t in tasks if t.kind is not TaskKind.CHECKPOINT and not names.intersection(t.assignee_names)]
    if nobody:
        rows.append(_member_row(UNASSIGNED, nobody))
    return rows


def summarize_progress(
    project: Project, holidays: dict[date, str], now: datetime, member: str | None = None
) -> Progress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    overdue: list[OverdueRow] = []
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        counts[task.status] += 1
        if (weight_and_percent := _progress_weight(task)) is not None:  # 節目は進捗率の重みに入れない
            weight, percent = weight_and_percent
            weighted += weight * percent
            total += weight
        if task.status is not Status.DONE and is_overdue(task, project, holidays, now, schedule):
            moment = actual_end(task) or now
            limits = [
                limit
                for limit in (task.deadline, schedule.end(task))
                if limit is not None and moment > limit
            ]
            limit = min(limits, default=task.deadline or now)  # 見込みの超過は、締切を基準にする
            overdue.append(OverdueRow(task.name, assignee_label(task), limit))
    overdue.sort(key=lambda row: row.limit)
    by_member = summarize_member_progress(project) if member is None else []
    return Progress(weighted / total if total else None, counts, overdue, by_member)


UNASSIGNED = "未割り当て"
DEADLINE = "締切"
PLANNED_END = "完了予定"


class LoadFailure(NamedTuple):
    name: str
    reason: str


@dataclass(frozen=True)
class LoadStats:
    average: float  # 稼働日ごとの、同時刻の割り当て率の合計の最大(その日の負荷)の平均(1.0 = 100%)
    peak: float
    overload_days: int  # 100% を超えた稼働日の数


@dataclass(frozen=True)
class ProjectLoad:
    project: str
    average: float  # そのプロジェクトだけで見た、稼働日ごとの負荷の平均
    peak: float


@dataclass(frozen=True)
class ProjectPeak:
    project: str
    peak: float  # その日、そのプロジェクトだけで見た割り当て率の合計の最大


@dataclass(frozen=True)
class DayLoad:
    day: date
    total: float  # 全プロジェクトを重ねた、その日の負荷(1.0 = 100%)
    by_project: list[ProjectPeak]  # 0 より大きいプロジェクトだけ


@dataclass(frozen=True)
class CrossLoad:
    total: LoadStats  # 全プロジェクトを重ねた負荷
    by_project: list[ProjectLoad]  # その人がメンバーのプロジェクトごと
    days: list[DayLoad] = field(default_factory=list)  # 稼働日ごと


@dataclass
class CrossSummary:
    loads: dict[str, CrossLoad]
    projects: list[str]  # チェックの並び。開いているプロジェクトが先
    excluded: set[str]
    failures: list[LoadFailure]


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


Span = tuple[datetime, datetime, float]


def _member_spans(project: Project, holidays: dict[date, str], member: str | None) -> dict[str, list[Span]]:
    """担当者名 → (開始, 終了, 割り当て率)。数えないタスクは入れない。"""
    spans: dict[str, list[Span]] = {}
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        counted = counted_span(task, project, holidays, schedule)
        if counted is not None:
            for assignee in counted_assignees(task, project):
                spans.setdefault(assignee.name, []).append((*counted, assignee.allocation))
    return spans


def _day_totals(items: list[Span], days: list[date]) -> list[float]:
    return [_day_peak(items, day) for day in days]


def _stats_of(totals: list[float]) -> LoadStats:
    return LoadStats(
        sum(totals) / len(totals) if totals else 0.0,
        max(totals, default=0.0),
        sum(1 for total in totals if total > 1.0 + OVERLOAD_EPSILON),
    )


def _load_stats(items: list[Span], days: list[date]) -> LoadStats:
    return _stats_of(_day_totals(items, days))


def summarize_loads(
    project: Project, period: Period, holidays: dict[date, str], member: str | None = None
) -> dict[str, LoadStats]:
    days = _workdays(period, holidays)
    spans = _member_spans(project, holidays, member)
    return {
        entry.name: _load_stats(spans.get(entry.name, []), days)
        for entry in project.members
        if member is None or entry.name == member
    }


def summarize_cross_loads(
    projects: list[Project], period: Period, holidays: dict[date, str], member: str | None = None
) -> dict[str, CrossLoad]:
    """複数のプロジェクトを重ねた負荷。同じ名前のメンバーを同一人物とみなす。"""
    days = _workdays(period, holidays)
    per_project = [(project, _member_spans(project, holidays, member)) for project in projects]
    names = dict.fromkeys(m.name for p in projects for m in p.members if member is None or m.name == member)
    loads: dict[str, CrossLoad] = {}
    for name in names:
        rows: list[ProjectLoad] = []
        everything: list[Span] = []
        per_day: list[tuple[str, list[float]]] = []
        for project, spans in per_project:
            if name not in {m.name for m in project.members}:
                continue
            items = spans.get(name, [])
            everything += items
            totals = _day_totals(items, days)
            stats = _stats_of(totals)
            rows.append(ProjectLoad(project.name, stats.average, stats.peak))
            per_day.append((project.name, totals))
        overall = _day_totals(everything, days)
        day_rows = [
            DayLoad(day, overall[i], [ProjectPeak(title, totals[i]) for title, totals in per_day if totals[i] > 0])
            for i, day in enumerate(days)
        ]
        loads[name] = CrossLoad(_stats_of(overall), rows, day_rows)
    return loads


def _shares(task: Task, names: list[str]) -> list[tuple[str, float, float]]:
    """(集計先, 割り当て率, 実績の按分の比)。メンバーでない担当者と担当なしは「未割当」。"""
    if not task.assignees:
        return [(UNASSIGNED, 1.0, 1.0)]
    total = sum(a.allocation for a in task.assignees)
    usable = isfinite(total) and total > 0
    return [
        (
            a.name if a.name in names else UNASSIGNED,
            a.allocation,
            a.allocation / total if usable else 1 / len(task.assignees),
        )
        for a in task.assignees
    ]


def summarize_workload(
    project: Project, period: Period, now: datetime, holidays: dict[date, str], member: str | None = None
) -> list[WorkloadRow]:
    names = [member.name for member in project.members]
    planned = {name: 0.0 for name in (*names, UNASSIGNED)}
    actual = {name: 0.0 for name in (*names, UNASSIGNED)}
    days = _workdays(period, holidays)
    low, high = period.bounds()
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        start, end = schedule.start(task), schedule.end(task)
        count = (
            sum(1 for day in days if _covers(start, end, day))
            if start is not None and end is not None and end > start
            else 0
        )
        for key, allocation, share in _shares(task, names):
            if count and isfinite(allocation):
                planned[key] += allocation * project.daily_hours * count
            for interval in task.actuals:
                seconds = (min(interval.end or now, high) - max(interval.start, low)).total_seconds()
                if seconds > 0:
                    actual[key] += seconds / 3600 * share
    shown = [name for name in names if member is None or name == member]
    rows = [WorkloadRow(name, planned[name], actual[name]) for name in shown]
    if member is None and (planned[UNASSIGNED] or actual[UNASSIGNED]):
        rows.append(WorkloadRow(UNASSIGNED, planned[UNASSIGNED], actual[UNASSIGNED]))
    return rows


def summarize_due(
    project: Project, period: Period, now: datetime, holidays: dict[date, str], member: str | None = None
) -> list[DueRow]:
    low, high = period.bounds()
    rows: list[DueRow] = []
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        if task.status is Status.DONE:
            continue
        late = is_overdue(task, project, holidays, now, schedule)
        for kind, moment in ((DEADLINE, task.deadline), (PLANNED_END, schedule.end(task))):
            if kind == PLANNED_END and moment == task.deadline:
                continue  # 締切だけのタスクは、完了予定が締切と同じになる。同じ日時の 2 行にしない
            if moment is not None and low <= moment < high:
                rows.append(DueRow(moment, kind, task.name, assignee_label(task), late))
    rows.sort(key=lambda row: (row.moment, row.kind))
    return rows


@dataclass
class Dashboard:
    period: Period
    progress: Progress
    loads: dict[str, LoadStats]
    workload: list[WorkloadRow]
    due: list[DueRow]
    team: TeamProgress = field(default_factory=TeamProgress)
    member: str | None = None  # 絞り込み中のメンバー。None は全員
    members: list[str] = field(default_factory=list)  # プルダウンの選択肢(プロジェクトのメンバーの順)
    cross: CrossSummary | None = None  # 全プロジェクトを重ねるとき。None は開いているプロジェクトだけ

    @property
    def planned_total(self) -> float:
        return sum(row.planned_hours for row in self.workload)

    @property
    def actual_total(self) -> float:
        return sum(row.actual_hours for row in self.workload)


def summarize(
    project: Project,
    period: Period,
    now: datetime,
    holidays: dict[date, str],
    kind: PeriodKind = PeriodKind.ALL,
    member: str | None = None,
) -> Dashboard:
    return Dashboard(
        period,
        summarize_progress(project, holidays, now, member),
        summarize_loads(project, period, holidays, member),
        summarize_workload(project, period, now, holidays, member),
        summarize_due(project, period, now, holidays, member),
        summarize_team_progress(project, None if kind is PeriodKind.ALL else period, now, holidays, member),
        member,
        [m.name for m in project.members],
    )
