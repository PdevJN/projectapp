"""ダッシュボードの集計。NiceGUI に依存しない純粋関数。"""

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from math import isfinite
from typing import NamedTuple

from projectapp.events import effective_holidays
from projectapp.models import Assignee, Member, Project, Status, Task, TaskKind, WorkDay
from projectapp.ratios import effective_ratio
from projectapp.remaining import overlap_hours, remaining_hours, total_effort
from projectapp.timeline import (
    OVERLOAD_EPSILON,
    Schedule,
    actual_end,
    assignees_rate,
    counted_pieces,
    crew_on,
    crew_pieces,
    current_progress,
    day_hours,
    is_overdue,
    is_workday,
)
from projectapp.teams import team_scope, team_weights, teams_with_members
from projectapp.workdays import work_day_map


class PeriodKind(StrEnum):
    WEEK = "今週"
    MONTH = "今月"
    ALL = "全期間"
    CUSTOM = "指定"  # 日付で指定した期間(MainView.dashboard_custom)


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # 両端を含む

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    def bounds(self) -> tuple[datetime, datetime]:
        """[開始日の 0 時, 終了日の翌日の 0 時)。"""
        return datetime.combine(self.start, time.min), datetime.combine(self.end + timedelta(days=1), time.min)


MAX_CUSTOM_DAYS = 400  # 指定できる期間の長さ(日数)。日ごとの推移の表が重くならないように


def custom_period_error(period: Period) -> str | None:
    """指定した期間が長すぎるときの、エラー文。"""
    if len(period.days()) > MAX_CUSTOM_DAYS:
        return f"期間が長すぎます(最大{MAX_CUSTOM_DAYS}日)"
    return None


def period_for(
    kind: PeriodKind,
    today: date,
    project: Project,
    holidays: dict[date, str],
    custom: Period | None = None,
) -> Period:
    if kind is PeriodKind.CUSTOM and custom is not None:
        return custom
    if kind is PeriodKind.CUSTOM:  # 指定がまだないときは、今週
        kind = PeriodKind.WEEK
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
    by_team: list[MemberProgress] = field(default_factory=list)  # チームごと(メンバーのいるチームだけ)。絞り込み中は空


Scope = str | frozenset[str] | Mapping[str, float] | None  # 絞り込み。文字列は 1 人、集合はそのうちの誰か(チーム)、辞書は名前 → 重み(チームの所属の割合)。None は全員


def _names(scope: Scope) -> frozenset[str] | None:
    """絞り込みを、メンバー名の集合にする。全員は None。"""
    if scope is None:
        return None
    if isinstance(scope, str):
        return frozenset({scope})
    return frozenset(scope)  # 集合はそのまま、辞書はキー


def _factor(scope: Scope, name: str) -> float:
    """メンバーの値に掛ける重み。チーム(辞書)なら所属の割合、それ以外は 1.0。"""
    return scope.get(name, 1.0) if isinstance(scope, Mapping) else 1.0


def _tasks(project: Project, member: Scope = None) -> list[Task]:
    """集計の対象のタスク。まとめは、子の工数・進捗・期限を二重に数えないよう外す。`member`があれば、その人(チームなら誰か)が担当のものだけ。"""
    scoped = _names(member)
    return [
        task
        for task in project.all_tasks()
        if task.kind not in (TaskKind.SUMMARY, TaskKind.REFERENCE)
        and (scoped is None or not scoped.isdisjoint(task.assignee_names))
    ]


@dataclass(frozen=True)
class ChildProject:
    """参照先のプロジェクトと、その休み(参照先自身のイベントを反映したもの)。"""

    project: Project
    holidays: dict[date, str]


class Entry(NamedTuple):
    """集計の 1 件。タスクと、それが属するプロジェクトの日程(参照先のタスクは参照先自身の日程)。"""

    task: Task
    project: Project
    schedule: Schedule
    origin: str  # 参照先のタスクなら参照先の名前。開いているプロジェクトのタスクは空

    @property
    def label(self) -> str:
        return f"{self.task.name}({self.origin})" if self.origin else self.task.name


def _entries(
    project: Project,
    holidays: dict[date, str],
    member: Scope = None,
    children: Mapping[str, ChildProject] | None = None,
) -> list[Entry]:
    """進捗の集計の対象。開いているプロジェクトのタスクに、参照先のタスクが続く(参照先の順)。"""
    own = Schedule(project, holidays)
    entries = [Entry(task, project, own, "") for task in _tasks(project, member)]
    for name, child in (children or {}).items():
        schedule = Schedule(child.project, child.holidays)
        entries += [Entry(task, child.project, schedule, name) for task in _tasks(child.project, member)]
    return entries


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
    member: Scope = None,
    children: Mapping[str, ChildProject] | None = None,
) -> TeamProgress:
    """チーム全体の進捗。担当者に関わらず、1 タスクを 1 回だけ数える。`period` があれば、期間にかかるタスクだけ。参照先のタスクも同列に数える。"""
    hours = {status: 0.0 for status in Status}
    counts = {status: 0 for status in Status}
    names: dict[Status, list[str]] = {status: [] for status in Status}
    weighted = total = 0.0
    moment = now or datetime.now()
    for entry in _entries(project, holidays or {}, member, children):
        task = entry.task
        weight_and_percent = _progress_weight(task)
        if weight_and_percent is None or (period is not None and not _touches(task, entry.schedule, period, moment)):
            continue
        weight, percent = weight_and_percent
        hours[task.status] += weight
        counts[task.status] += 1
        names[task.status].append(entry.label)
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


def summarize_member_progress(project: Project, children: Mapping[str, ChildProject] | None = None) -> list[MemberProgress]:
    """メンバーごとの進捗。共同タスクは担当の全員の行に数える。メンバーが担当にいないタスクは`未割り当て`。参照先のタスクは名前で当てる。"""
    if not project.members:
        return []
    tasks = [entry.task for entry in _entries(project, {}, None, children)]
    names = {member.name for member in project.members}
    rows = [_member_row(m.name, [t for t in tasks if m.name in t.assignee_names]) for m in project.members]
    # 節目は担当を持てず、進捗の重みもないので、割り当て漏れには数えない
    nobody = [t for t in tasks if t.kind not in (TaskKind.CHECKPOINT, TaskKind.REFERENCE) and not names.intersection(t.assignee_names)]
    if nobody:
        rows.append(_member_row(UNASSIGNED, nobody))
    return rows


def summarize_team_rows(project: Project, children: Mapping[str, ChildProject] | None = None) -> list[MemberProgress]:
    """チームごとの進捗(メンバーのいるチームだけ)。共同タスクは、担当が所属する全チームの行に数える。"""
    tasks = [entry.task for entry in _entries(project, {}, None, children)]
    rows = []
    for name in teams_with_members(project):
        scoped = team_scope(project, name)
        assert scoped is not None
        rows.append(_member_row(name, [t for t in tasks if not scoped.isdisjoint(t.assignee_names)]))
    return rows


def summarize_progress(
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    member: Scope = None,
    children: Mapping[str, ChildProject] | None = None,
) -> Progress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    overdue: list[OverdueRow] = []
    for entry in _entries(project, holidays, member, children):
        task = entry.task
        counts[task.status] += 1
        if (weight_and_percent := _progress_weight(task)) is not None:  # 節目は進捗率の重みに入れない
            weight, percent = weight_and_percent
            weighted += weight * percent
            total += weight
        if task.status is not Status.DONE and is_overdue(task, entry.project, entry.schedule.holidays, now, entry.schedule):
            moment = actual_end(task) or now
            limits = [
                limit
                for limit in (task.deadline, entry.schedule.end(task))
                if limit is not None and moment > limit
            ]
            limit = min(limits, default=task.deadline or now)  # 見込みの超過は、締切を基準にする
            overdue.append(OverdueRow(entry.label, assignee_label(task), limit))
    overdue.sort(key=lambda row: row.limit)
    by_member = summarize_member_progress(project, children) if member is None else []
    by_team = summarize_team_rows(project, children) if member is None else []
    return Progress(weighted / total if total else None, counts, overdue, by_member, by_team)


UNASSIGNED = "未割り当て"
NO_TEAM = "チームなし"
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


def _workdays(
    period: Period, holidays: dict[date, str], work_days: Mapping[date, WorkDay] | None = None
) -> list[date]:
    return [day for day in period.days() if is_workday(day, holidays, work_days)]


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


def _member_spans(project: Project, holidays: dict[date, str], member: Scope) -> dict[str, list[Span]]:
    """担当者名 → (開始, 終了, 割り当て率)。数えないタスクは入れない。"""
    spans: dict[str, list[Span]] = {}
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        for left, right, crew in counted_pieces(task, project, holidays, schedule):
            for assignee in crew:
                spans.setdefault(assignee.name, []).append((left, right, assignee.allocation))
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


def _scaled(stats: LoadStats, factor: float) -> LoadStats:
    """平均と最大に重みを掛ける。超過の日数は、掛ける前の値で判定したままにする。"""
    if factor == 1.0:
        return stats
    return LoadStats(stats.average * factor, stats.peak * factor, stats.overload_days)


def summarize_loads(
    project: Project, period: Period, holidays: dict[date, str], member: Scope = None
) -> dict[str, LoadStats]:
    spans = _member_spans(project, holidays, member)
    scoped = _names(member)
    return {
        entry.name: _scaled(
            _load_stats(spans.get(entry.name, []), _workdays(period, holidays, work_day_map(entry.work_days))),
            _factor(member, entry.name),
        )
        for entry in project.members
        if scoped is None or entry.name in scoped
    }


def summarize_cross_loads(
    projects: list[Project], period: Period, holidays: dict[date, str], member: Scope = None
) -> dict[str, CrossLoad]:
    """複数のプロジェクトを重ねた負荷。同じ名前のメンバーを同一人物とみなす。"""
    scoped = _names(member)
    closed_aware = {id(p): effective_holidays(p, holidays) for p in projects}  # 各プロジェクトの休みのイベントを足す
    open_days = {
        (id(p), m.name): set(_workdays(period, closed_aware[id(p)], work_day_map(m.work_days)))
        for p in projects
        for m in p.members
    }
    days = sorted(set().union(*open_days.values())) if open_days else []
    per_project = [(project, _member_spans(project, closed_aware[id(project)], member)) for project in projects]
    names = dict.fromkeys(m.name for p in projects for m in p.members if scoped is None or m.name in scoped)
    loads: dict[str, CrossLoad] = {}
    for name in names:
        rows: list[ProjectLoad] = []
        everything: list[tuple[Project, list[Span]]] = []
        per_day: list[tuple[str, list[float]]] = []
        # 平均は、その人がどこかのプロジェクトで稼働する日だけで数える(他のメンバーの稼働日で薄めない)
        mine = [open_days[(id(p), name)] for p in projects if (id(p), name) in open_days]
        own = [i for i, day in enumerate(days) if any(day in opened for opened in mine)]
        for project, spans in per_project:
            if name not in {m.name for m in project.members}:
                continue
            items = spans.get(name, [])
            everything.append((project, items))
            # 自分が稼働しない日は、タスクの期間が通っても数えない
            totals = [peak if day in open_days[(id(project), name)] else 0.0 for peak, day in zip(_day_totals(items, days), days)]
            stats = _stats_of([totals[i] for i in own])
            rows.append(ProjectLoad(project.name, stats.average, stats.peak))
            per_day.append((project.name, totals))
        overall = [
            _day_peak([span for p, items in everything if day in open_days[(id(p), name)] for span in items], day)
            for day in days
        ]

        day_rows = [
            DayLoad(day, overall[i], [ProjectPeak(title, totals[i]) for title, totals in per_day if totals[i] > 0])
            for i, day in enumerate(days)
        ]
        loads[name] = CrossLoad(_stats_of([overall[i] for i in own]), rows, day_rows)
    return loads


def _shares(assignees: list[Assignee], names: list[str]) -> list[tuple[str, float, float]]:
    """(集計先, 割り当て率, 実績の按分の比)。メンバーでない担当者と担当なしは「未割当」。"""
    if not assignees:
        return [(UNASSIGNED, 1.0, 1.0)]
    total = sum(a.allocation for a in assignees)
    usable = isfinite(total) and total > 0
    return [
        (
            a.name if a.name in names else UNASSIGNED,
            a.allocation,
            a.allocation / total if usable else 1 / len(assignees),
        )
        for a in assignees
    ]


def summarize_workload(
    project: Project, period: Period, now: datetime, holidays: dict[date, str], member: Scope = None
) -> list[WorkloadRow]:
    names = [m.name for m in project.members]
    scoped = _names(member)
    planned = {name: 0.0 for name in (*names, UNASSIGNED)}
    actual = {name: 0.0 for name in (*names, UNASSIGNED)}
    calendars = {m.name: work_day_map(m.work_days) for m in project.members}
    tables: dict[str, list[tuple[date, float]]] = {}

    def table(key: str) -> list[tuple[date, float]]:
        """担当者(未割当は通常カレンダー)の、期間の稼働日と稼働時間。"""
        if key not in tables:
            cal = calendars.get(key)
            rows = ((day, day_hours(day, project.daily_hours, holidays, cal)) for day in period.days())
            tables[key] = [(day, hours) for day, hours in rows if hours > 0]
        return tables[key]

    low, high = period.bounds()
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        start, end = schedule.start(task), schedule.end(task)
        if start is not None and end is not None and end > start:
            for left, right, crew in crew_pieces(task, start, end):  # 週ごとのタスクは、週の区間ごとの担当者で数える
                for key, allocation, _ in _shares(crew, names):
                    if isfinite(allocation):
                        planned[key] += allocation * sum(h for day, h in table(key) if _covers(left, right, day))
        for interval in task.actuals:
            seconds = (min(interval.end or now, high) - max(interval.start, low)).total_seconds()
            if seconds <= 0:
                continue
            # 実績は、区間の開始の日の担当者で按分する(週ごとのタスクは、その週の担当者)
            crew = crew_on(task, start.date(), interval.start.date()) if start is not None else task.assignees
            for key, _, share in _shares(crew, names):
                actual[key] += seconds / 3600 * share
    shown = [name for name in names if scoped is None or name in scoped]
    rows = [
        WorkloadRow(name, planned[name] * _factor(member, name), actual[name] * _factor(member, name))
        for name in shown
    ]
    if member is None and (planned[UNASSIGNED] or actual[UNASSIGNED]):
        rows.append(WorkloadRow(UNASSIGNED, planned[UNASSIGNED], actual[UNASSIGNED]))
    return rows


def summarize_due(
    project: Project, period: Period, now: datetime, holidays: dict[date, str], member: Scope = None
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


@dataclass(frozen=True)
class Backlog:
    hours: float  # 残りの工数の合計(100% の人の時間)
    unset_count: int  # 工数のない未終了のタスク(合計に入れない)
    days: float | None  # 割る期間の稼働日数(今日は残りの時間を稼働可能時間で割った小数)。決まらないときは None
    required: float | None  # 必要な人数(100% の人に換算)。days が None か 0 のときは None
    supply: float  # 稼働できる人員(相対比率の合計)
    by_member: list[tuple[str, float]]  # (担当者, 残りの工数)。共同タスクは割り当て率の比で按分
    by_status: dict[Status, float] = field(default_factory=dict)  # 状態ごとの残りの工数(0 は除く)
    by_team: list[tuple[str, float]] = field(default_factory=list)  # (チーム, 残りの工数)。全員のときだけ。メンバーの分を所属の割合で配る
    nominal_supply: float | None = None  # 稼働日の上書きで調整する前の稼働できる人員。調整で値が変わるときだけ
    overdue_hours: float = 0.0  # hours のうち、遅れたタスクの残りの工数(要望 98)
    overdue_count: int = 0  # 遅れたタスクの件数

    @property
    def shortfall(self) -> float | None:
        """不足する人数。負なら余裕。"""
        return None if self.required is None else self.required - self.supply

    @property
    def overdue_required(self) -> float | None:
        """遅れの分だけで要る人数(必要人数と同じ期間で割る)。必要人数が出せないときは None。"""
        if self.required is None:
            return None
        return self.required * self.overdue_hours / self.hours if self.hours > 0 else 0.0

    @property
    def shortfall_without_overdue(self) -> float | None:
        """遅れがなかった場合の不足する人数(負なら余裕)。遅れの分の人数を、不足から引く。"""
        shortfall, overdue = self.shortfall, self.overdue_required
        if shortfall is None or overdue is None:
            return None
        return shortfall - overdue


def _next_workday(day: date, holidays: dict[date, str]) -> date:
    """その日以降で最初の稼働日(通常カレンダー)。2 週間見て無ければその日。"""
    return next((d for d in (day + timedelta(days=i) for i in range(14)) if is_workday(d, holidays)), day)


def _backlog_window(
    project: Project, period: Period, kind: PeriodKind, now: datetime, holidays: dict[date, str], ends: list[datetime]
) -> tuple[date, date] | None:
    """必要人数の分母にする日の範囲(今日より前は数えない)。決まらないとき(全期間で数えたタスクに終わりがない)は None。
    開始が終了より後なら、期間がすでに終わっている。"""
    today = now.date()
    if kind is PeriodKind.ALL:  # 全期間は、数えたタスクの最も遅い終わりまで
        if not ends:
            return None
        start = max(today, project.base_date)
        end = max(max(ends).date(), _next_workday(start, holidays))  # 全部が遅れていても、最初の稼働日で終える場合を示す
        return start, end
    return max(today, period.start), period.end


def _window_hours(
    project: Project,
    holidays: dict[date, str],
    window: tuple[date, date],
    now: datetime,
    work_days: Mapping[date, WorkDay] | None = None,
) -> float:
    """範囲の稼働時間。今日は、今から稼働の枠の終わりまでの残り(始業前は枠の全体、終業後は 0)。
    work_days があれば、その人の上書きを反映する。"""
    start, end = window
    if start > end:
        return 0.0
    today = now.date()
    rest_of_today = datetime.combine(today + timedelta(days=1), time.min)
    return sum(
        overlap_hours(project, holidays, day, now, rest_of_today, work_days)
        if day == today
        else day_hours(day, project.daily_hours, holidays, work_days)
        for day in Period(start, end).days()
    )


def _next_workday_after(window: tuple[date, date], holidays: dict[date, str]) -> bool:
    """範囲の稼働時間が 0 のとき、次の稼働日の 1 日で終える場合を示せるか。"""
    return is_workday(_next_workday(window[1] + timedelta(days=1), holidays), holidays)


class _WorkHours:
    """通常カレンダーの稼働時間の累積。タスクの期間を 1 日ずつ回さずに、日の範囲の合計を出す。"""

    def __init__(self, project: Project, holidays: dict[date, str], first: date, last: date) -> None:
        self.first = first
        self.cumulative = [0.0]
        for day in Period(first, last).days():
            self.cumulative.append(self.cumulative[-1] + day_hours(day, project.daily_hours, holidays))

    def between(self, low: date, high: date) -> float:
        """[low, high] の稼働時間。表の範囲に収まっていること。"""
        if low > high:
            return 0.0
        return self.cumulative[(high - self.first).days + 1] - self.cumulative[(low - self.first).days]


def _counted_fraction(
    task: Task,
    project: Project,
    schedule: Schedule,
    period: Period,
    now: datetime,
    holidays: dict[date, str],
    table: _WorkHours | None,
) -> float:
    """期間の分として数える、工数の割合(0〜1)。期間の終わりより後ろに予定した分と、まだ先の期間までの隙間は数えない。
    予定の終わりを過ぎた遅れと、日程のないタスクは、全量が残っているので数える(締切が期間より後なら除く)。"""
    start, end = schedule.start(task), schedule.end(task)
    if start is None or end is None:
        return 0.0 if task.deadline is not None and task.deadline.date() > period.end else 1.0
    if end <= now:
        return 1.0
    if end <= start:
        return float(start.date() <= period.end)
    first, last = start.date(), (end - timedelta(microseconds=1)).date()  # 終わりが 0 時ちょうどなら前日まで
    assert table is not None  # 日程のあるタスクがあれば、呼び出し側が作る

    def weight(low: date, high: date) -> float:
        """[low, high] のうち、タスクの期間と重なる日の稼働時間。初日と最終日は、重なる時間だけ。"""
        low, high = max(low, first), min(high, last)
        if low > high:
            return 0.0
        if first == last:
            return overlap_hours(project, holidays, first, start, end)
        total = table.between(low, high)
        if low == first:
            total += overlap_hours(project, holidays, first, start, end) - table.between(first, first)
        if high == last:
            total += overlap_hours(project, holidays, last, start, end) - table.between(last, last)
        return total

    def days(low: date, high: date) -> int:
        return max(0, (min(high, last) - max(low, first)).days + 1)

    cutoff, gap_end = period.end, period.start - timedelta(days=1)  # 隙間は [今日, 期間の始まりの前日]
    total = weight(first, last)
    if total > 0:
        counted = weight(first, cutoff) - weight(now.date(), min(gap_end, cutoff))
        return counted / total
    # 稼働日にかからない(土日だけ)ときは、日数で割る
    return (days(first, cutoff) - days(now.date(), min(gap_end, cutoff))) / days(first, last)


OPEN_STATUSES = (Status.NOT_STARTED, Status.RUNNING, Status.PAUSED)  # 残りの工数に数える状態


def _remaining_shares(
    task: Task, project: Project, schedule: Schedule, holidays: dict[date, str], rest: float, names: list[str]
) -> list[tuple[str, float, float]]:
    """残りの工数を担当者へ按分する比(`_shares`と同じ形)。週ごとのタスクは、消化分を先の週から差し引き、
    残った分を、その週の担当(割り当て率の比)で配る。週の重みは、週の稼働時間 × その週の換算率。"""
    start, end = schedule.start(task), schedule.end(task)
    if not task.weekly_crew or start is None or end is None or rest <= 0:
        return _shares(task.assignees, names)
    pieces = crew_pieces(task, start, end)
    capacity = [
        sum(overlap_hours(project, holidays, day, left, right) for day in Period(left.date(), right.date()).days())
        * assignees_rate(crew, project.members, project.parameters, task.parameters, project.ratio_limits)
        for left, right, crew in pieces
    ]
    total = sum(capacity)
    if not total > 0:
        return _shares(task.assignees, names)
    done = total_effort(task) - rest
    weights: dict[str, float] = {}
    for (_, _, crew), hours in zip(pieces, capacity):
        hours *= total_effort(task) / total  # 工数に合わせる(週の重みの比は変えない)
        left_over = max(0.0, hours - done)
        done = max(0.0, done - hours)
        for key, _, share in _shares(crew, names):
            weights[key] = weights.get(key, 0.0) + left_over * share
    whole = sum(weights.values())
    if not whole > 0:
        return _shares(task.assignees, names)
    return [(key, 0.0, value / whole) for key, value in weights.items()]


def _backlog_by_team(project: Project, split: dict[str, float]) -> list[tuple[str, float]]:
    """メンバーごとの残りの工数を、所属の割合で各チームに配る。チームに入っていない人は`チームなし`、担当なしは`未割り当て`。
    メンバーのいるチームがなければ空(チーム別を出さない)。"""
    names = {entry.id: entry.name for entry in project.teams}
    hours: dict[str, float] = {name: 0.0 for name in teams_with_members(project)}
    if not hours:
        return []
    hours[NO_TEAM] = 0.0
    for member in project.members:
        if not member.teams:
            hours[NO_TEAM] += split.get(member.name, 0.0)
        for membership in member.teams:
            hours[names[membership.team_id]] += split.get(member.name, 0.0) * membership.percent / 100
    hours[UNASSIGNED] = split.get(UNASSIGNED, 0.0)
    return [(name, value) for name, value in hours.items() if value > 0]


def _is_late(task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule) -> bool:
    """遅れたタスクか(要望 98)。今は予定超過(ガントチャートの赤みと同じ判定)。警告を含める選択は未実装(警告の状態を作るときに足す)。"""
    return is_overdue(task, project, holidays, now, schedule)


@dataclass
class _BacklogParts:
    """1 プロジェクトぶんの残りの工数の集計の途中経過(重ねるときは、これを足し合わせる)。"""

    split: dict[str, float]  # 担当者(メンバーでない人と担当なしは「未割当」)ごとの残りの工数
    by_status: dict[Status, float]
    unset: int  # 工数のない未終了のタスク
    ends: list[datetime]  # 数えたタスクの完了予定・締切(必要人数の期間を決める)
    overdue_split: dict[str, float] = field(default_factory=dict)  # split のうち、遅れたタスクの分
    overdue_count: int = 0  # 遅れたタスクの件数(絞り込みの範囲に担当がいるもの)


def _backlog_parts(
    project: Project,
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
    member: Scope,
) -> _BacklogParts:
    schedule = Schedule(project, holidays)
    names = [m.name for m in project.members]
    scoped = _names(member)
    unset = 0
    ends: list[datetime] = []
    split = {name: 0.0 for name in (*names, UNASSIGNED)}
    by_status = {status: 0.0 for status in OPEN_STATUSES}
    overdue_split = {name: 0.0 for name in (*names, UNASSIGNED)}
    overdue_count = 0
    targets = [
        task for task in _tasks(project, member) if task.status in OPEN_STATUSES and task.kind is TaskKind.NORMAL
    ]
    spans = [(schedule.start(task), schedule.end(task)) for task in targets]
    dates = [moment.date() for pair in spans if None not in pair for moment in pair if moment is not None]
    table = _WorkHours(project, holidays, min(dates), max(dates)) if dates and kind is not PeriodKind.ALL else None
    for task in targets:
        fraction = (
            1.0 if kind is PeriodKind.ALL else _counted_fraction(task, project, schedule, period, now, holidays, table)
        )
        if fraction <= 0:
            continue
        if not (isfinite(total_effort(task)) and total_effort(task) > 0):
            unset += 1
            continue
        ends.extend(moment for moment in (schedule.end(task), task.deadline) if moment is not None)
        rest = remaining_hours(task, project, holidays, now)
        due = max(0.0, rest - total_effort(task) * (1 - fraction))  # 期間の終わりまでに予定した工数 − 消化分
        late = _is_late(task, project, holidays, now, schedule)
        counted = False
        for key, _, share in _remaining_shares(task, project, schedule, holidays, rest, names):
            portion = due * share
            split[key] += portion
            if late:
                overdue_split[key] += portion
            if scoped is None or key in scoped:
                by_status[task.status] += portion * _factor(member, key)
                counted = counted or (late and portion > 0)
        overdue_count += counted
    return _BacklogParts(split, by_status, unset, ends, overdue_split, overdue_count)


def _assemble_backlog(
    base: Project,
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
    member: Scope,
    parts: list[_BacklogParts],
    supply_from: list[tuple[Member, Project]],
) -> Backlog:
    """部品を足し合わせて Backlog にする。割る側の稼働時間は base のカレンダー(holidays は base の休み)で数える。"""
    scoped = _names(member)
    split: dict[str, float] = {}
    for part in parts:
        for key, value in part.split.items():
            split[key] = split.get(key, 0.0) + value
    split.setdefault(UNASSIGNED, 0.0)
    shown = [name for name in (*(k for k in split if k != UNASSIGNED), UNASSIGNED) if scoped is None or name in scoped]
    by_status = {status: sum(part.by_status[status] for part in parts) for status in OPEN_STATUSES}
    hours = sum(split[name] * _factor(member, name) for name in shown)
    overdue_split: dict[str, float] = {}
    for part in parts:
        for key, value in part.overdue_split.items():
            overdue_split[key] = overdue_split.get(key, 0.0) + value
    overdue_hours = sum(overdue_split.get(name, 0.0) * _factor(member, name) for name in shown)
    ends = [moment for part in parts for moment in part.ends]
    window = _backlog_window(base, period, kind, now, holidays, ends)
    standard = 0.0 if window is None else _window_hours(base, holidays, window, now)
    fallback = window is not None and window[0] <= window[1] and standard <= 0 and _next_workday_after(window, holidays)
    capacity = None if window is None else base.daily_hours if fallback else standard
    days = None if capacity is None else capacity / base.daily_hours
    required = hours / capacity if capacity else None
    supply = nominal = 0.0
    for m, owner in supply_from:
        if scoped is not None and m.name not in scoped:
            continue
        weight = effective_ratio(m, owner.parameters, None, owner.ratio_limits) * _factor(member, m.name)
        nominal += weight
        # 上書きのあるメンバーは、標準の稼働時間に対するその人の稼働時間の比で数える(標準が 0 のときは数えない)
        scale = 1.0
        if m.work_days and window is not None and standard > 0:
            scale = _window_hours(base, holidays, window, now, work_day_map(m.work_days)) / standard
        supply += weight * scale
    rows = [(name, split[name] * _factor(member, name)) for name in shown if split[name] > 0]
    by_team = _backlog_by_team(base, split) if scoped is None else []
    return Backlog(
        hours,
        sum(part.unset for part in parts),
        days,
        required,
        supply,
        rows,
        {k: v for k, v in by_status.items() if v > 0},
        by_team,
        nominal if abs(nominal - supply) > 1e-9 else None,
        overdue_hours,
        sum(part.overdue_count for part in parts),
    )


def summarize_backlog(
    project: Project,
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
    member: Scope = None,
) -> Backlog:
    """残りの工数(未着手の全量と、実行中・一時停止の消化分を除いた分)の合計と、それを期間内に終えるのに要る人数。全期間以外は、期間の終わりまでに予定した分。
    メンバーで絞るときは、共同タスクのその人の分(割り当て率の比)だけを数える。"""
    parts = [_backlog_parts(project, period, kind, now, holidays, member)]
    return _assemble_backlog(project, period, kind, now, holidays, member, parts, [(m, project) for m in project.members])


def summarize_cross_backlog(
    projects: list[Project],
    base: Project,
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
    member: Scope = None,
) -> Backlog:
    """複数のプロジェクトを重ねた残りの工数と必要人数。同じ名前のメンバーを同一人物とみなす。
    工数は各プロジェクト自身の日程・休みで数え、割る側(稼働時間)は base(開いているプロジェクト)の稼働可能時間・休みで数える。
    稼働できる人員は、名前ごとに 1 回(projects の先頭に近いプロジェクトの相対比率)。"""
    parts = [_backlog_parts(p, period, kind, now, effective_holidays(p, holidays), member) for p in projects]
    owners = {m.name: (m, p) for p in reversed(projects) for m in p.members}  # 先頭のプロジェクトが勝つ
    names = list(dict.fromkeys(m.name for p in projects for m in p.members))
    return _assemble_backlog(
        base, period, kind, now, effective_holidays(base, holidays), member, parts, [owners[name] for name in names]
    )


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
    team_name: str | None = None  # 絞り込み中のチーム名。member とは同時に使わない
    teams: list[str] = field(default_factory=list)  # プルダウンの選択肢のチーム(メンバーのいるものだけ)
    cross: CrossSummary | None = None  # 全プロジェクトを重ねるとき。None は開いているプロジェクトだけ
    backlog: Backlog = field(default_factory=lambda: Backlog(0.0, 0, None, None, 0.0, []))
    references: int = 0  # 進捗に数えた参照先のプロジェクトの数

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
    team: str | None = None,
    children: Mapping[str, ChildProject] | None = None,
) -> Dashboard:
    """`member`があれば`team`は無視する。存在しない・メンバーのいないチームは絞り込まない。"""
    team_members = team_scope(project, team) if member is None else None
    scope: Scope = member if member is not None else team_weights(project, team)
    return Dashboard(
        period,
        summarize_progress(project, holidays, now, scope, children),
        summarize_loads(project, period, holidays, scope),
        summarize_workload(project, period, now, holidays, scope),
        summarize_due(project, period, now, holidays, scope),
        summarize_team_progress(project, None if kind is PeriodKind.ALL else period, now, holidays, scope, children),
        member,
        [m.name for m in project.members],
        backlog=summarize_backlog(project, period, kind, now, holidays, scope),
        team_name=team if team_members is not None else None,
        teams=teams_with_members(project),
        references=len(children or {}),
    )
