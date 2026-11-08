"""残りの工数の推移(要望 128 段階 2)。NiceGUI にも`dashboard`にも依存しない。

`dashboard.summarize_burndown`が、対象のタスクを`BurnTask`にして渡す(循環 import を避けるため)。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from projectapp.models import HistoryEvent, Task
from projectapp.timeline import is_workday


@dataclass(frozen=True)
class BurnTask:
    """推移の対象のタスク 1 件。`start`・`end`は予定の開始・完了予定の日付(読めなければ None)。"""

    task: Task
    events: tuple[HistoryEvent, ...]  # このタスクの履歴(日時の昇順)
    start: date | None
    end: date | None


def count_workdays(first: date, last: date, holidays: dict[date, str]) -> int:
    """`first`〜`last`(両端を含む)の稼働日の数。月〜金で`holidays`の日を除く。"""
    if last < first:
        return 0
    weeks, rest = divmod((last - first).days + 1, 7)
    count = weeks * 5 + sum(
        1 for offset in range(rest) if (first + timedelta(offset)).weekday() < 5
    )
    return count - sum(
        1 for day in holidays if first <= day <= last and day.weekday() < 5
    )


def next_workday(day: date, holidays: dict[date, str]) -> date:
    """その日以降で最初の稼働日。14 日見て無ければその日。"""
    return next(
        (
            d
            for d in (day + timedelta(offset) for offset in range(14))
            if is_workday(d, holidays)
        ),
        day,
    )


def planned_curve(
    tasks: Sequence[BurnTask],
    remains: Sequence[float],
    anchor: date,
    last: date,
    holidays: dict[date, str],
) -> tuple[float, ...]:
    """`anchor`の翌日から`last`までの各日の終わりの、予定の残りの合計。

    タスクごとに、`anchor`時点の残り(`remains`)が、予定の開始(`anchor`の翌日より前なら翌日)から完了予定まで、
    稼働日で直線に下がるとする。完了予定が開始より前(予定超過など)なら開始の 1 日で終える。
    休みの日だけの予定は、次の稼働日に終える扱い。予定が読めないタスクは動かない。
    """
    days = (last - anchor).days
    if days <= 0:
        return ()
    cumulative = [0]  # cumulative[k]: anchor の翌日から k 日目までの稼働日数
    for k in range(1, days + 1):
        cumulative.append(cumulative[-1] + is_workday(anchor + timedelta(k), holidays))
    first_day = anchor + timedelta(1)
    totals = [0.0] * days
    for item, remain in zip(tasks, remains, strict=True):
        if remain <= 0:
            continue
        if item.start is None or item.end is None:
            for index in range(days):
                totals[index] += remain
            continue
        begin = max(item.start, first_day)
        finish = max(item.end, begin)
        if count_workdays(begin, finish, holidays) == 0:
            finish = next_workday(finish, holidays)
        width = max(1, count_workdays(begin, finish, holidays))
        begin_k, finish_k = (begin - anchor).days, (finish - anchor).days
        for k in range(1, days + 1):
            elapsed = (
                0
                if k < begin_k
                else cumulative[min(k, finish_k)] - cumulative[begin_k - 1]
            )
            totals[k - 1] += remain * (1 - min(1.0, elapsed / width))
    return tuple(totals)
