"""スケールごとの列生成と、日時から位置・幅への変換(純粋関数)。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from itertools import groupby
from math import ceil, isfinite
from typing import NamedTuple

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


def visible_range(project: Project) -> tuple[date, date]:
    """基準日とバーを持つタスクから、表示範囲[開始日, 終了日)を返す。"""
    start = end = project.base_date
    tasks = [*project.tasks, *(t for section in project.sections for t in section.tasks)]
    for task in tasks:
        if task.start is None or task.end is None:
            continue
        first, last = sorted((task.start.date(), task.end.date()))
        start = min(start, first)
        end = max(end, last + timedelta(days=1))
    return start, end


def build_columns(project: Project, scale: Scale) -> list[Column]:
    start, end = visible_range(project)
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


def bar_span(task: Task, columns: list[Column]) -> tuple[float, float] | None:
    """バーの(左端, 幅)を列の単位で返す。開始・終了が未設定ならNone。"""
    if task.start is None or task.end is None:
        return None
    left = _position(task.start, columns)
    right = _position(task.end, columns)
    return left, max(right - left, 0.0)


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


def fill_end(task: Task, project: Project, holidays: dict[date, str]) -> Task:
    """開始あり・終了なし・工数ありのタスクに、算出した終了を入れて返す。"""
    if task.start is None or task.end is not None:
        return task
    end = calc_end(
        task.start, task.effort_hours, project.daily_hours, project.work_start, holidays
    )
    return task if end is None else replace(task, end=end, end_auto=True)


class Recalc(NamedTuple):
    changed: int  # 終了が変わった件数
    failed: int  # 自動算出の終了だが、算出できず古い終了のまま残った件数


def recalc_ends(project: Project, holidays: dict[date, str]) -> Recalc:
    """自動算出された終了(end_auto)だけを、現在の稼働設定で再計算する。"""
    changed = failed = 0

    def renew(task: Task) -> Task:
        nonlocal changed, failed
        if not task.end_auto or task.start is None:
            return task
        end = calc_end(
            task.start, task.effort_hours, project.daily_hours, project.work_start, holidays
        )
        if end is None:
            failed += 1
            return task
        if end == task.end:
            return task
        changed += 1
        return replace(task, end=end)

    project.tasks[:] = [renew(t) for t in project.tasks]
    for section in project.sections:
        section.tasks[:] = [renew(t) for t in section.tasks]
    return Recalc(changed, failed)


def is_overdue(task: Task, now: datetime) -> bool:
    """終了予定を過ぎていて、状態が「終了」でない。"""
    return task.end is not None and task.status is not Status.DONE and now > task.end
