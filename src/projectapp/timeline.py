"""スケールごとの列生成と、日時から位置・幅への変換(純粋関数)。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from itertools import groupby
from math import ceil, isfinite

from projectapp.models import Project, Status, Task


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
    tasks = [*project.tasks, *(t for section in project.sections for t in section.tasks)]
    for task in tasks:
        task_end = effective_end(task, project, holidays)
        if task.planned_start is None or task_end is None:
            continue
        first, last = sorted((task.planned_start.date(), task_end.date()))
        try:
            task_last = last + timedelta(days=1)
        except OverflowError:  # 日付の上限(手編集のファイル)。範囲に入れない
            continue
        start = min(start, first)
        end = max(end, task_last)
    return start, end


def build_columns(
    project: Project, scale: Scale, holidays: dict[date, str] | None = None
) -> list[Column]:
    start, end = visible_range(project, holidays)
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


def _counted_span(
    task: Task, project: Project, holidays: dict[date, str]
) -> tuple[datetime, datetime] | None:
    """割り当ての合計に数えるタスクの期間。数えない(担当者なし・終了・開始予定なしなど)ときはNone。"""
    if not task.assignee or task.status is Status.DONE or task.planned_start is None:
        return None
    if all(m.name != task.assignee for m in project.members):
        return None
    end = effective_end(task, project, holidays)
    if end is None or end <= task.planned_start:
        return None
    return task.planned_start, end


def overallocations(project: Project, holidays: dict[date, str]) -> list[Overload]:
    """同じ担当者の、期間が重なるタスクの割り当て率の合計が100%を超える期間。"""
    spans: dict[str, list[tuple[datetime, datetime, float]]] = {}
    for task in project.all_tasks():
        counted = _counted_span(task, project, holidays)
        if counted is not None and task.assignee is not None:
            spans.setdefault(task.assignee, []).append((*counted, task.allocation))
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
    task: Task, project: Project, holidays: dict[date, str], overloads: list[Overload]
) -> list[Overload]:
    """そのタスクの期間に重なる超過区間を、タスクの期間に切り詰めて返す。"""
    counted = _counted_span(task, project, holidays)
    if counted is None:
        return []
    start, end = counted
    clipped: list[Overload] = []
    for overload in overloads:
        if overload.member != task.assignee:
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


def conversion_rate(task: Task, project: Project) -> float:
    member = next((m for m in project.members if m.name == task.assignee), None)
    if member is None:
        return 1.0
    return combine_rate(member.ratio, task.allocation)


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


def effective_end(task: Task, project: Project, holidays: dict[date, str]) -> datetime | None:
    """完了予定。工数が無い、または手で指定のときは planned_end、それ以外は算出する。"""
    if task.planned_end is not None and (task.effort_hours <= 0 or task.planned_end_manual):
        return task.planned_end
    return computed_end(
        task.planned_start,
        task.effort_hours,
        project.daily_hours,
        project.work_start,
        holidays,
        task.deadline,
        conversion_rate(task, project),
    )


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
    task: Task, project: Project, holidays: dict[date, str], now: datetime
) -> bool:
    """締切か完了予定を過ぎている。実績の終了があれば、その時刻で判定する(遅れて終わったものも超過)。
    実績の終了がなければ、状態が「終了」でない間だけ、現在時刻と比べる。"""
    moment = actual_end(task)
    if moment is None:
        if task.status is Status.DONE:
            return False
        moment = now
    if task.deadline is not None and moment > task.deadline:
        return True
    end = effective_end(task, project, holidays)
    return end is not None and moment > end
