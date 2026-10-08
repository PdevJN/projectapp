"""スケールごとの列生成と、日時から位置・幅への変換(純粋関数)。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from itertools import groupby
from math import ceil, isfinite

from projectapp.models import Assignee, Member, Parameter, Project, Status, Task, TaskKind
from projectapp.ratios import effective_ratio


class Scale(StrEnum):
    DAY = "日次"
    WEEK = "週次"
    MONTH = "月次"


MIN_COLUMNS = {Scale.DAY: 42, Scale.WEEK: 26, Scale.MONTH: 12}
MAX_WORKDAYS = 3650  # 約14年分。誤入力で計算が長引くのを防ぐ


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


def overallocations(project: Project, holidays: dict[date, str]) -> list[Overload]:
    """同じ担当者の、期間が重なるタスクの割り当て率の合計が100%を超える期間。"""
    spans: dict[str, list[tuple[datetime, datetime, float]]] = {}
    schedule = Schedule(project, holidays)
    for task in project.all_tasks():
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


def is_workday(day: date, holidays: dict[date, str]) -> bool:
    """月〜金で祝日でない日。"""
    return day.weekday() < 5 and day not in holidays


def _next_workday(day: date, holidays: dict[date, str]) -> date:
    day += timedelta(days=1)
    while not is_workday(day, holidays):
        day += timedelta(days=1)
    return day


def calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
) -> datetime | None:
    """稼働日の稼働枠(始業から連続daily_hours時間)に工数を割り当てた終了日時。

    工数が不正(NaN・inf・0以下・稼働日数の上限超え)、daily_hoursが0以下・24超、
    または日付が範囲を超えるときは、例外にせずNoneを返す。
    """
    if not isfinite(effort_hours) or effort_hours <= 0 or not 0 < daily_hours <= 24:
        return None
    if effort_hours > daily_hours * MAX_WORKDAYS:
        return None
    try:
        return _calc_end(start, effort_hours, daily_hours, work_start, holidays)
    except OverflowError:
        return None


def _calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
) -> datetime:
    slot = timedelta(hours=daily_hours)
    day = start.date()
    if is_workday(day, holidays) and start < datetime.combine(day, work_start) + slot:
        cursor = max(start, datetime.combine(day, work_start))
    else:
        cursor = datetime.combine(_next_workday(day, holidays), work_start)
    remaining = timedelta(hours=effort_hours)
    while True:
        available = datetime.combine(cursor.date(), work_start) + slot - cursor
        if remaining <= available:
            return cursor + remaining
        remaining -= available
        cursor = datetime.combine(_next_workday(cursor.date(), holidays), work_start)


def combine_rate(ratio: float, allocation: float) -> float:
    """換算率 = 相対比率 × 割り当て率。使えない値(0以下・NaN・inf)のときは換算しない(1.0)。"""
    rate = ratio * allocation
    return rate if isfinite(rate) and rate > 0 else 1.0


def assignees_rate(
    assignees: list[Assignee], members: list[Member], parameters: list[Parameter] | None = None
) -> float:
    """担当者全員の換算率(相対比率 × 割り当て率)の合計。相対比率は、パラメータを反映した実効比率。
    メンバーにいない担当者は数えない。誰も数えられなければ 1.0(換算しない)。"""
    by_name = {m.name: m for m in members}
    chosen = parameters or []
    rates = [
        combine_rate(effective_ratio(by_name[a.name], chosen), a.allocation)
        for a in assignees
        if a.name in by_name
    ]
    return sum(rates) if rates else 1.0


def conversion_rate(task: Task, project: Project) -> float:
    return assignees_rate(task.assignees, project.members, project.parameters)


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
) -> datetime | None:
    """手入力を使わない完了予定。工数を換算率で割って算出し、算出できなければ締切、締切もなければ開始予定の1日後。"""
    if start is not None and effort_hours > 0:
        end = calc_end(
            start, effort_hours / combine_rate(rate, 1.0), daily_hours, work_start, holidays
        )
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
        conversion_rate(task, project),
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

    def finish(self, pred: Task) -> datetime | None:
        """先行としての完了。終了済みで実績の終了があればその時刻、なければ実効の完了。"""
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
    if schedule is None and not task.predecessors:
        return _own_end(task, project, holidays, task.planned_start)
    return (schedule or Schedule(project, holidays)).end(task)


def current_progress(task: Task) -> int | None:
    """進捗度の入っている最後の区間の値(累積)。ひとつもなければ None。0 は入力ありとして返す。"""
    for actual in reversed(task.actuals):
        if actual.progress is not None:
            return actual.progress
    return None


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
