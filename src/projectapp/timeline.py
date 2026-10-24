"""スケールごとの列生成と、日時から位置・幅への変換(純粋関数)。"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from itertools import groupby
from math import ceil, isfinite

from projectapp.models import Assignee, Member, Parameter, Project, Status, Task, TaskKind, WorkDay
from projectapp.ratios import effective_ratio
from projectapp.summary import children_of
from projectapp.workdays import work_day_map

class Scale(StrEnum):
    DAY = "日次"
    WEEK = "週次"
    MONTH = "月次"


MIN_COLUMNS = {Scale.DAY: 42, Scale.WEEK: 26, Scale.MONTH: 12}
MAX_WORKDAYS = 3650  # 約14年分。誤入力で計算が長引くのを防ぐ
CAPACITY_EPSILON = 1e-9  # 工数の消化の比較の許容差[h](約3.6µs)


@dataclass(frozen=True)
class Worker:
    """完了予定の算出に使う担当者 1 人。rate は換算率(相対比率 × 割り当て率)、days は日付 → 稼働日の上書き。
    name と allocation は、担当者向けの見積もりでの按分に使う(比較には使わない)。"""

    rate: float = 1.0
    days: Mapping[date, WorkDay] = field(default_factory=dict)
    name: str = field(default="", compare=False)
    allocation: float = field(default=1.0, compare=False)


@dataclass(frozen=True)
class Column:
    start: date
    end: date  # 終端を含まない
    label: str


@dataclass(frozen=True)
class Band:
    """見出しの帯。countは結合する列数。"""

    label: str
    count: int


def visible_range(
    project: Project, holidays: dict[date, str] | None = None
) -> tuple[date, date]:
    """基準日とバーを持つタスクから、表示範囲[開始日, 終了日)を返す。"""
    holidays = holidays or {}
    start = end = project.base_date
    tasks = project.all_tasks()
    schedule = Schedule(project, holidays)
    for task in tasks:
        task_start, task_end = schedule.start(task), schedule.end(task)
        if task_start is None or task_end is None:
            continue
        first, last = sorted((task_start.date(), task_end.date()))
        try:
            task_last = last + timedelta(days=1)
        except OverflowError:  # 日付の上限(手編集のファイル)。範囲に入れない
            continue
        start = min(start, first)
        end = max(end, task_last)
    return start, end


def build_columns(
    project: Project,
    scale: Scale,
    holidays: dict[date, str] | None = None,
    period: tuple[date, date] | None = None,
) -> list[Column]:
    """列を作る。period は [開始日, 終了日](終了日を含む)。None は、基準日とバーから決めた表示範囲。"""
    if period is None:
        start, end = visible_range(project, holidays)
    else:
        if period[0] > period[1]:
            raise ValueError("期間の開始日が終了日より後です")
        start, end = period[0], period[1] + timedelta(days=1)
    if scale is Scale.WEEK:
        return _week_columns(start, end)
    if scale is Scale.MONTH:
        return _month_columns(start, end)
    return _day_columns(start, end)


def _day_columns(start: date, end: date) -> list[Column]:
    count = max((end - start).days, MIN_COLUMNS[Scale.DAY])
    days = (start + timedelta(days=i) for i in range(count))
    return [Column(d, d + timedelta(days=1), f"{d.day}") for d in days]


def _week_columns(start: date, end: date) -> list[Column]:
    monday = start - timedelta(days=start.weekday())
    count = max(ceil((end - monday).days / 7), MIN_COLUMNS[Scale.WEEK])
    weeks = (monday + timedelta(weeks=i) for i in range(count))
    return [Column(d, d + timedelta(days=7), f"{d.day}~") for d in weeks]


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _month_columns(start: date, end: date) -> list[Column]:
    first = start.replace(day=1)
    last = max(end - timedelta(days=1), first)
    count = (last.year - first.year) * 12 + last.month - first.month + 1
    columns: list[Column] = []
    for i in range(max(count, MIN_COLUMNS[Scale.MONTH])):
        month = _add_months(first, i)
        columns.append(Column(month, _add_months(first, i + 1), f"{month.month}月"))
    return columns


def _position(moment: datetime, columns: list[Column]) -> float:
    """日時を、列の単位(0〜列数)の連続値に変換する。"""
    if moment <= datetime.combine(columns[0].start, time.min):
        return 0.0
    for index, column in enumerate(columns):
        begin = datetime.combine(column.start, time.min)
        finish = datetime.combine(column.end, time.min)
        if begin <= moment < finish:
            return index + (moment - begin) / (finish - begin)
    return float(len(columns))


def bar_span(
    start: datetime | None, end: datetime | None, columns: list[Column]
) -> tuple[float, float] | None:
    """バーの(左端, 幅)を列の単位で返す。開始・終了が無ければNone。"""
    if start is None or end is None:
        return None
    left = _position(start, columns)
    right = _position(end, columns)
    return left, max(right - left, 0.0)


def in_range(start: datetime, end: datetime, columns: list[Column]) -> bool:
    """棒が、列の範囲と重なるか。幅 0 の棒は、位置が範囲内のときだけ。逆順(手編集)でも落ちない。"""
    begin = datetime.combine(columns[0].start, time.min)
    finish = datetime.combine(columns[-1].end, time.min)
    first, last = sorted((start, end))
    if first == last:
        return begin <= first < finish
    return first < finish and last > begin


def deadline_position(deadline: datetime, columns: list[Column]) -> float | None:
    """締切の位置(列の単位)。表示範囲の外ならNone。"""
    begin = datetime.combine(columns[0].start, time.min)
    finish = datetime.combine(columns[-1].end, time.min)
    if not begin <= deadline < finish:
        return None
    return _position(deadline, columns)


def interval_span(start: datetime, end: datetime, columns: list[Column]) -> tuple[float, float]:
    """区間の(左端, 幅)を列の単位で返す。幅は0以上。"""
    left = _position(start, columns)
    right = _position(end, columns)
    return left, max(right - left, 0.0)


@dataclass(frozen=True)
class Overload:
    """担当者の割り当て合計が100%を超える期間。totalは期間内の合計の最大値(1.0 = 100%)。"""

    member: str
    start: datetime
    end: datetime
    total: float


OVERLOAD_EPSILON = 1e-9  # 浮動小数の誤差で、ちょうど100%を超過にしない


def counted_assignees(task: Task, project: Project) -> list[Assignee]:
    """換算率と割り当ての合計に数える担当者(メンバーにいる人だけ。タスクの並び順)。"""
    names = {m.name for m in project.members}
    return [a for a in task.assignees if a.name in names]


def counted_span(
    task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None
) -> tuple[datetime, datetime] | None:
    """割り当ての合計に数えるタスクの期間。数えない(担当者なし・終了・開始予定なしなど)ときはNone。"""
    if task.status is Status.DONE or not counted_assignees(task, project):
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    end = effective_end(task, project, holidays, schedule)
    if end is None or end <= start:
        return None
    return start, end


def overallocations(
    project: Project, holidays: dict[date, str], tasks: Iterable[Task] | None = None
) -> list[Overload]:
    """同じ担当者の、期間が重なるタスクの割り当て率の合計が100%を超える期間。tasks を渡すと、それだけを数える。"""
    spans: dict[str, list[tuple[datetime, datetime, float]]] = {}
    schedule = Schedule(project, holidays)
    for task in project.all_tasks() if tasks is None else tasks:
        counted = counted_span(task, project, holidays, schedule)
        if counted is not None:
            for assignee in counted_assignees(task, project):
                spans.setdefault(assignee.name, []).append((*counted, assignee.allocation))
    result: list[Overload] = []
    for name, items in spans.items():
        points = sorted({p for start, end, _ in items for p in (start, end)})
        current: Overload | None = None
        for left, right in zip(points, points[1:]):
            total = sum(a for start, end, a in items if start <= left and right <= end)
            if total > 1.0 + OVERLOAD_EPSILON:
                if current is not None and current.end == left:
                    current = replace(current, end=right, total=max(current.total, total))
                else:
                    if current is not None:
                        result.append(current)
                    current = Overload(name, left, right, total)
            elif current is not None:
                result.append(current)
                current = None
        if current is not None:
            result.append(current)
    return result


def clip_overloads(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    overloads: list[Overload],
    schedule: Schedule | None = None,
) -> list[Overload]:
    """そのタスクの期間に重なる超過区間を、タスクの期間に切り詰めて返す。"""
    counted = counted_span(task, project, holidays, schedule)
    if counted is None:
        return []
    start, end = counted
    clipped: list[Overload] = []
    for overload in overloads:
        if overload.member not in task.assignee_names:
            continue
        left, right = max(overload.start, start), min(overload.end, end)
        if left < right:
            clipped.append(replace(overload, start=left, end=right))
    return clipped


def _bands(
    columns: list[Column], key: Callable[[Column], object], label: Callable[[Column], str]
) -> list[Band]:
    """keyが同じ(同じ年や月)の連続する列を、1つの帯にまとめる。"""
    bands: list[Band] = []
    for _, group in groupby(columns, key=key):
        members = list(group)
        bands.append(Band(label(members[0]), len(members)))
    return bands


def year_bands(columns: list[Column]) -> list[Band]:
    return _bands(columns, lambda c: c.start.year, lambda c: f"{c.start.year}年")


def month_bands(columns: list[Column]) -> list[Band]:
    """月の帯。週は開始日が属する月に数える。"""
    return _bands(
        columns, lambda c: (c.start.year, c.start.month), lambda c: f"{c.start.month}月"
    )


def _default_open(day: date, holidays: dict[date, str]) -> bool:
    """上書きがないときの稼働日: 月〜金で祝日でない日。"""
    return day.weekday() < 5 and day not in holidays


def is_workday(day: date, holidays: dict[date, str], work_days: Mapping[date, WorkDay] | None = None) -> bool:
    """稼働日か。稼働日の上書きがあればそれ(休みは稼働日でない)、なければ月〜金で祝日でない日。"""
    if work_days and day in work_days:
        return work_days[day].start is not None
    return _default_open(day, holidays)


def day_window(
    day: date,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    work_days: Mapping[date, WorkDay] | None = None,
) -> tuple[datetime, datetime] | None:
    """その日の稼働の枠(開始, 終了)。枠がない日(休み・土日祝)は None。上書きがあれば、その日の枠を置き換える。"""
    if work_days and day in work_days:
        row = work_days[day]
        if row.start is None or row.end is None:
            return None
        return datetime.combine(day, row.start), datetime.combine(day, row.end)
    if not _default_open(day, holidays):
        return None
    opens = datetime.combine(day, work_start)
    return opens, opens + timedelta(hours=daily_hours)


def day_hours(
    day: date,
    daily_hours: float,
    holidays: dict[date, str],
    work_days: Mapping[date, WorkDay] | None = None,
) -> float:
    """その日の稼働時間[h]。枠がなければ 0。"""
    window = day_window(day, daily_hours, time.min, holidays, work_days)
    return (window[1] - window[0]).total_seconds() / 3600 if window else 0.0


def week_index(start: date, day: date, count: int) -> int:
    """開始の日から 7 日(暦日)ごとの週の添字(0 が第1週)。最後の週より後は最後の週。開始より前は第1週。"""
    return min(max((day - start).days, 0) // 7, count - 1)


def crew_on(task: Task, start: date, day: date) -> list[Assignee]:
    """その日の担当者。週ごとに分けないタスクは assignees。start は実効の開始の日。"""
    if not task.weekly_crew:
        return task.assignees
    return task.weekly_crew[week_index(start, day, len(task.weekly_crew))]


def _crews(
    effort_hours: float, daily_hours: float, crew: Sequence[Worker] | None, weeks: Sequence[Sequence[Worker]] | None
) -> list[list[Worker]] | None:
    """算出に使う週ごとの担当(週ごとに分けないときは 1 週ぶん)。算出できない入力は None。
    担当者のいない週は換算率 1 の 1 人。工数の上限の判定は、最も遅い週(換算率の合計が最小)で行う。"""
    crews = [list(week) or [Worker()] for week in weeks] if weeks else [list(crew) if crew else [Worker()]]
    total = min(sum(w.rate for w in c) for c in crews)
    if not isfinite(effort_hours) or effort_hours <= 0 or not 0 < daily_hours <= 24:
        return None
    if not isfinite(total) or total <= 0 or effort_hours / total > daily_hours * MAX_WORKDAYS:
        return None
    return crews


def calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
) -> datetime | None:
    """基準の人の工数を、担当者全員の稼働の枠(その人の上書き、なければ始業から稼働可能時間)に割り当てた終了日時。

    枠が重なる時刻は、稼働中の担当者の換算率の合計で工数を消化する。crew が空なら換算率1の1人。
    weeks があれば、start の日から 7 日ごとにその週の担当者で消化する(最後の週は以降も続く。crew は使わない)。
    工数が不正(NaN・inf・0以下・稼働日数の上限超え)、daily_hoursが0以下・24超、
    または日付が範囲を超えるときは、例外にせずNoneを返す。
    """
    crews = _crews(effort_hours, daily_hours, crew, weeks)
    if crews is None:
        return None
    try:
        return _calc_end(start, effort_hours, daily_hours, work_start, holidays, crews)
    except OverflowError:
        return None


def consumed_slices(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
) -> list[tuple[datetime, datetime, list[Worker]]]:
    """工数を消化する区間(左, 右, その区間で稼働している担当者)。算出できないときは空。"""
    crews = _crews(effort_hours, daily_hours, crew, weeks)
    if crews is None:
        return []
    try:
        return list(_consume(start, effort_hours, daily_hours, work_start, holidays, crews))
    except OverflowError:
        return []


def _consume(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crews: list[list[Worker]],
) -> Iterator[tuple[datetime, datetime, list[Worker]]]:
    remaining = effort_hours
    day, cursor = start.date(), start
    while True:
        workers = crews[week_index(start.date(), day, len(crews))]
        windows = [
            (w, window)
            for w in workers
            if (window := day_window(day, daily_hours, work_start, holidays, w.days)) is not None
        ]
        points = sorted({max(p, cursor) for _, window in windows for p in window})
        for left, right in zip(points, points[1:]):
            active = [w for w, (opens, closes) in windows if opens <= left and right <= closes]
            speed = sum(w.rate for w in active)
            if speed <= 0:
                continue
            capacity = speed * (right - left).total_seconds() / 3600
            if remaining <= capacity + CAPACITY_EPSILON:  # 浮動小数の丸めで、ちょうど枠の終わりで終わる工数が翌日に回らない
                yield left, min(left + timedelta(hours=remaining / speed), right), active
                return
            remaining -= capacity
            yield left, right, active
        day += timedelta(days=1)
        cursor = datetime.combine(day, time.min)


def _calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crews: list[list[Worker]],
) -> datetime:
    end = start
    for _, end, _ in _consume(start, effort_hours, daily_hours, work_start, holidays, crews):
        pass
    return end


def combine_rate(ratio: float, allocation: float) -> float:
    """換算率 = 相対比率 × 割り当て率。使えない値(0以下・NaN・inf)のときは換算しない(1.0)。"""
    rate = ratio * allocation
    return rate if isfinite(rate) and rate > 0 else 1.0


def crew_of(
    assignees: list[Assignee],
    members: list[Member],
    parameters: list[Parameter] | None = None,
    only: Collection[str] | None = None,
) -> list[Worker]:
    """担当者を算出用の Worker にする。相対比率は、パラメータを反映した実効比率(only はタスクに付けたパラメータ)。メンバーにいない担当者は入れない。"""
    by_name = {m.name: m for m in members}
    chosen = parameters or []
    return [
        Worker(
            combine_rate(effective_ratio(by_name[a.name], chosen, only), a.allocation),
            work_day_map(by_name[a.name].work_days),
            a.name,
            a.allocation,
        )
        for a in assignees
        if a.name in by_name
    ]


def assignees_rate(
    assignees: list[Assignee],
    members: list[Member],
    parameters: list[Parameter] | None = None,
    only: Collection[str] | None = None,
) -> float:
    """担当者全員の換算率(相対比率 × 割り当て率)の合計。誰も数えられなければ 1.0(換算しない)。"""
    rates = [w.rate for w in crew_of(assignees, members, parameters, only)]
    return sum(rates) if rates else 1.0


def conversion_rate(task: Task, project: Project) -> float:
    return assignees_rate(task.assignees, project.members, project.parameters, task.parameters)


def weekly_crews(task: Task, project: Project) -> list[list[Worker]]:
    """週ごとの担当を算出用の Worker にしたもの(パラメータを反映)。週ごとに分けないタスクは空。"""
    return [crew_of(week, project.members, project.parameters, task.parameters) for week in task.weekly_crew]


def effort_days(effort_hours: float, rate: float, daily_hours: float) -> float | None:
    """基準の人の工数(h)を、換算率と稼働可能時間で日数にする。使えない値はNone。"""
    if not isfinite(effort_hours) or effort_hours <= 0:
        return None
    if not isfinite(daily_hours) or daily_hours <= 0:
        return None
    return effort_hours / combine_rate(rate, 1.0) / daily_hours


def computed_end(
    start: datetime | None,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    deadline: datetime | None = None,
    rate: float = 1.0,
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
) -> datetime | None:
    """手入力を使わない完了予定。工数を換算率で割って算出し、算出できなければ締切、締切もなければ開始予定の1日後。"""
    if start is not None and effort_hours > 0:
        workers = list(crew) if crew else [Worker(combine_rate(rate, 1.0))]
        end = calc_end(start, effort_hours, daily_hours, work_start, holidays, workers, weeks)
        if end is not None:
            return end
    if deadline is not None:
        return deadline  # 開始予定より前でも、そのまま使う(遅れている状態が見える)
    if start is None:
        return None
    try:
        return start + timedelta(days=1)
    except OverflowError:
        return None


def _own_end(
    task: Task, project: Project, holidays: dict[date, str], start: datetime | None
) -> datetime | None:
    """開始を `start` としたときの完了予定。手指定・工数なしの planned_end は、押し出された分ずらす。"""
    if task.planned_end is not None and (task.effort_hours <= 0 or task.planned_end_manual):
        if task.planned_start is None or start is None or start <= task.planned_start:
            return task.planned_end
        try:
            return task.planned_end + (start - task.planned_start)
        except OverflowError:
            return task.planned_end
    return computed_end(
        start,
        task.effort_hours,
        project.daily_hours,
        project.work_start,
        holidays,
        task.deadline,
        crew=crew_of(task.assignees, project.members, project.parameters, task.parameters),
        weeks=weekly_crews(task, project) or None,
    )


class Schedule:
    """タスクの id から、実効の開始・完了への対応。必要なものだけ算出して使い回す(保存しない)。"""

    def __init__(self, project: Project, holidays: dict[date, str]) -> None:
        self.project = project
        self.holidays = holidays
        self._tasks = {task.id: task for task in project.all_tasks()}
        self._done: dict[str, tuple[datetime | None, datetime | None]] = {}
        self._active: set[str] = set()

    def start(self, task: Task) -> datetime | None:
        return self._resolve(task)[0]

    def end(self, task: Task) -> datetime | None:
        return self._resolve(task)[1]

    def bar_end(self, task: Task) -> datetime | None:
        """棒の右端。終了済みで実績の終了があればその時刻(担当を替えても伸び縮みしない)、なければ実効の完了。"""
        if task.kind is TaskKind.NORMAL and task.status is Status.DONE:
            actual = actual_end(task)
            if actual is not None:
                return actual
        return self.end(task)

    def finish(self, pred: Task) -> datetime | None:
        """先行としての完了。終了済みで実績の終了があればその時刻、なければ実効の完了。
        まとめは、子の完了の最大(終了済みの子は実績の終了)。"""
        if pred.kind is TaskKind.SUMMARY:
            if pred.id in self._active:  # 循環(手編集のファイルなど)
                return None
            self._active.add(pred.id)
            try:
                finishes = [self.finish(child) for child in children_of(pred, self._tasks)]
            finally:
                self._active.discard(pred.id)
            return max((f for f in finishes if f is not None), default=None)
        if pred.status is Status.DONE:
            actual = actual_end(pred)
            if actual is not None:
                return actual
        return self._resolve(pred)[1]

    def latest_finish(self, task: Task) -> datetime | None:
        """先行の完了の最大。先行がない、または完了が求まる先行がなければ None。"""
        finishes = [
            finish
            for pid in task.predecessors
            if pid != task.id and (pred := self._tasks.get(pid)) is not None
            if (finish := self.finish(pred)) is not None
        ]
        return max(finishes, default=None)

    def _resolve(self, task: Task) -> tuple[datetime | None, datetime | None]:
        if task.id in self._done:
            return self._done[task.id]
        if task.kind is TaskKind.CHECKPOINT:  # 締切に固定。先行で押し出さない
            result = (task.deadline, task.deadline)
            self._done[task.id] = result
            return result
        if task.kind is TaskKind.SUMMARY:  # 子の最小の開始と最大の完了。自分の先行は持たない
            if task.id in self._active:  # 循環(手編集のファイルなど)
                return None, None
            self._active.add(task.id)
            try:
                spans = [self._resolve(child) for child in children_of(task, self._tasks)]
            finally:
                self._active.discard(task.id)
            starts = [start for start, _ in spans if start is not None]
            ends = [end for _, end in spans if end is not None]
            result = (min(starts, default=None), max(ends, default=None))
            self._done[task.id] = result
            return result
        if task.id in self._active:  # 循環(手編集のファイルなど)。押し出しなしで扱う
            return task.planned_start, _own_end(task, self.project, self.holidays, task.planned_start)
        self._active.add(task.id)
        try:
            floor = self.latest_finish(task)
        finally:
            self._active.discard(task.id)
        start = task.planned_start
        if floor is not None and (start is None or floor > start):
            start = floor
        result = (start, _own_end(task, self.project, self.holidays, start))
        self._done[task.id] = result
        return result


def effective_start(
    task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None
) -> datetime | None:
    """実効の開始。先行がなければ開始予定。あれば、開始予定と先行の完了の遅いほう。チェックポイントは締切。"""
    if task.kind is TaskKind.CHECKPOINT:
        return task.deadline
    if task.kind is TaskKind.SUMMARY:
        return (schedule or Schedule(project, holidays)).start(task)
    if schedule is None and not task.predecessors:
        return task.planned_start
    return (schedule or Schedule(project, holidays)).start(task)


def effective_end(
    task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None
) -> datetime | None:
    """完了予定。工数が無い、または手で指定のときは planned_end、それ以外は算出する。先行の押し出しを含む。
    チェックポイントは締切。"""
    if task.kind is TaskKind.CHECKPOINT:
        return task.deadline
    if task.kind is TaskKind.SUMMARY:
        return (schedule or Schedule(project, holidays)).end(task)
    if schedule is None and not task.predecessors:
        return _own_end(task, project, holidays, task.planned_start)
    return (schedule or Schedule(project, holidays)).end(task)


def current_progress(task: Task) -> int | None:
    """タスクの進捗度。入っていなければ None。0 は入力ありとして返す。"""
    return task.progress


def actual_end(task: Task) -> datetime | None:
    """実績の終了。実績がない、または終了のない区間があれば None。複数あるときは最後の区間の終了。"""
    if not task.actuals or any(a.end is None for a in task.actuals):
        return None
    return task.actuals[-1].end


def is_overdue(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> bool:
    """締切か完了予定を過ぎている。実績の終了があれば、その時刻で判定する(遅れて終わったものも超過)。
    実績の終了がなければ、状態が「終了」でない間だけ、現在時刻と比べる。"""
    if task.kind is TaskKind.SUMMARY:
        return False  # 超過は子に出る
    moment = actual_end(task)
    if moment is None:
        if task.status is Status.DONE:
            return False
        moment = now
    if task.kind is TaskKind.CHECKPOINT and task.deadline is not None and task.predecessors:
        floor = (schedule or Schedule(project, holidays)).latest_finish(task)
        if floor is not None and floor > task.deadline:
            return True  # 先行の完了が締切を超える見込み
    if task.deadline is not None and moment > task.deadline:
        return True
    end = effective_end(task, project, holidays, schedule)
    return end is not None and moment > end


class ProgressState(StrEnum):
    NORMAL = "通常"
    DELAYED = "遅延"
    AHEAD = "前倒し"
    DONE = "完了"
    LATE_DONE = "遅延完了"


PROGRESS_TOLERANCE = 10  # 進んでいるはずの割合との差の許容幅(パーセントポイント)


def expected_progress(start: datetime, end: datetime, now: datetime) -> float:
    """現在時刻までに進んでいるはずの割合(0〜100)。暦の時間で、開始〜完了予定の経過割合。"""
    if end <= start:
        return 100.0 if now >= end else 0.0
    ratio = (now - start) / (end - start)
    return min(max(ratio, 0.0), 1.0) * 100


def progress_state(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> ProgressState | None:
    """進捗の状態。終了は完了か遅延完了(超過の判定は is_overdue)。それ以外は、進捗度を
    進んでいるはずの割合と比べる。進捗度か予定がなければ判定できず None。"""
    if task.status is Status.DONE:
        late = is_overdue(task, project, holidays, now, schedule)
        return ProgressState.LATE_DONE if late else ProgressState.DONE
    if task.kind is TaskKind.SUMMARY:
        return None
    percent = current_progress(task)
    start = effective_start(task, project, holidays, schedule)
    end = effective_end(task, project, holidays, schedule)
    if percent is None or start is None or end is None:
        return None
    expected = expected_progress(start, end, now)
    if percent < expected - PROGRESS_TOLERANCE:
        return ProgressState.DELAYED
    if percent > expected + PROGRESS_TOLERANCE:
        return ProgressState.AHEAD
    return ProgressState.NORMAL
