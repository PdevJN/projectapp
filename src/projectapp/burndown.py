"""残りの工数の推移(要望 128 段階 2)。NiceGUI にも`dashboard`にも依存しない。

`dashboard.summarize_burndown`が、対象のタスクを`BurnTask`にして渡す(循環 import を避けるため)。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from projectapp.history_log import (
    TaskState,
    effective_progress,
    effort_weight,
    states_at,
)
from projectapp.models import HistoryEvent, Status, Task, TaskKind
from projectapp.timeline import is_workday

WINDOW_DAYS = 10  # 直近のペースの窓(稼働日)
MIN_WINDOW_DAYS = 3  # これより短い窓ではペースを出さない
BEHIND_RATIO = 1.2  # 必要なペースが直近のペースのこの倍率を超えたら「追いついていない」


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


@dataclass(frozen=True)
class Mark:
    """進捗度が未入力から入った日と、そのタスク名(実際の線の段差の理由)。"""

    day: date
    names: tuple[str, ...]


@dataclass(frozen=True)
class Burndown:
    first: date
    last: date
    known: bool  # 期間の始めまで履歴がある
    since: date | None  # 履歴を記録し始めた日
    count: int = 0  # 対象のタスクの件数
    initial: float = 0.0  # 期間の始めの残り[h]
    actual: tuple[float, ...] = ()  # 日ごとの実際の残り(日の終わり。今日の分は「今」)
    planned: tuple[float, ...] = ()  # 当初の予定の残り(期間の全日。日の終わり)
    future: tuple[
        float, ...
    ] = ()  # 今後の予定の残り(今日から期間の終わり。先頭は今日の実際)
    workdays: tuple[bool, ...] = ()  # 期間の各日が稼働日か
    today_index: int | None = None  # 今日が期間の何日目か(期間の外は None)
    now_fraction: float = 0.0  # 今日の経過した割合(0〜1)
    marks: tuple[Mark, ...] = ()
    unset: tuple[str, ...] = ()  # 進捗度なしの実行中・一時停止のタスク名
    rest: float | None = None  # 今日の実際 − 期間の終わりの予定の残り(今後の予定の終端)
    required: float | None = None  # 必要なペース[h/稼働日]
    recent: float | None = None  # 直近のペース[h/稼働日]
    recent_days: int = 0  # 直近のペースの窓の稼働日数
    behind: bool = False  # 必要なペースが直近のペースの 1.2 倍を超える
    ahead: bool = False  # 今日の実際が、当初の予定の今日の終わり以下
    whole: bool = False  # `全期間`のため、履歴のある期間で描いている


def _remaining(state: TaskState | None) -> float:
    """タスクの残り。まだ作られていない(None)なら 0。"""
    if state is None:
        return 0.0
    return effort_weight(state.effort) * (1 - effective_progress(state) / 100)


def _by_task(
    tasks: Sequence[BurnTask], moments: Sequence[datetime]
) -> tuple[list[list[float]], list[float]]:
    """タスクごと・時刻ごとの残りと、時刻ごとの合計。"""
    per_task = [
        [_remaining(s) for s in states_at(item.task, item.events, moments)]
        for item in tasks
    ]
    totals = [sum(row[i] for row in per_task) for i in range(len(moments))]
    return per_task, totals


def _recent_pace(
    tasks: Sequence[BurnTask],
    today: date,
    now: datetime,
    since: datetime,
    holidays: dict[date, str],
) -> tuple[float | None, int]:
    """直近 10 稼働日の正味のペース[h/稼働日]。窓の始めは記録開始以降に縮める。3 稼働日に満たなければ出さない。"""
    day, found, window_start = today - timedelta(1), 0, None
    for _ in range(366):
        if found >= WINDOW_DAYS or datetime.combine(day, time.min) < since:
            break
        window_start = day
        found += is_workday(day, holidays)
        day -= timedelta(1)
    if window_start is None:
        return None, 0
    days = count_workdays(window_start, today - timedelta(1), holidays)
    if days < MIN_WINDOW_DAYS:
        return None, 0
    _, totals = _by_task(tasks, [datetime.combine(window_start, time.min), now])
    return max(0.0, (totals[0] - totals[1]) / days), days


def _marks(
    tasks: Sequence[BurnTask], low: datetime, now: datetime, last: date
) -> tuple[Mark, ...]:
    """進捗度が未入力から入ったイベント(作成と退場は除く)の日ごとのタスク名。"""
    days: dict[date, list[str]] = {}
    for item in tasks:
        for event in item.events:
            changes = {c.field: c for c in event.changes}
            progress, status = changes.get("progress"), changes.get("status")
            if (
                progress is None
                or progress.before is not None
                or progress.after is None
            ):
                continue
            if status is not None and status.before is None:  # 作成
                continue
            if low <= event.at <= now and event.at.date() <= last:
                days.setdefault(event.at.date(), []).append(item.task.name)
    return tuple(Mark(day, tuple(names)) for day, names in sorted(days.items()))


def compute_burndown(
    tasks: Sequence[BurnTask],
    first: date,
    last: date,
    now: datetime,
    since: datetime | None,
    holidays: dict[date, str],
) -> Burndown:
    """期間(`first`〜`last`)の残りの工数の推移。期間の始めが記録開始より前なら不明。"""
    low = datetime.combine(first, time.min)
    if since is None or low < since:
        return Burndown(first, last, False, since.date() if since else None)
    days = (last - first).days + 1
    today = now.date()
    moments = [low]
    for index in range(days):
        end = datetime.combine(first + timedelta(index + 1), time.min)
        if end <= now:
            moments.append(end)
        else:
            if (
                first + timedelta(index) <= today
            ):  # 今日が期間の中: 日の終わりでなく「今」
                moments.append(now)
            break
    per_task, totals = _by_task(tasks, moments)
    initial, actual = totals[0], tuple(totals[1:])
    planned = planned_curve(
        tasks, [row[0] for row in per_task], first - timedelta(1), last, holidays
    )
    offset = (today - first).days
    today_index = offset if 0 <= offset < days else None
    future: tuple[float, ...] = ()
    fraction = 0.0
    rest = required = None
    recent, recent_days = None, 0
    if today_index is not None:
        fraction = (now - datetime.combine(today, time.min)).total_seconds() / 86400
        tail = planned_curve(
            tasks, [row[-1] for row in per_task], today, last, holidays
        )
        future = (actual[-1], *tail)
        rest = actual[-1] - future[-1]
        days_left = count_workdays(today + timedelta(1), last, holidays)
        required = rest / days_left if days_left else None
        recent, recent_days = _recent_pace(tasks, today, now, since, holidays)
    behind = (
        required is not None
        and required > 0
        and recent is not None
        and required > BEHIND_RATIO * recent
    )
    ahead = (
        today_index is not None
        and len(planned) > today_index
        and actual[-1] <= planned[today_index] + 1e-6
    )
    unset = tuple(
        item.task.name
        for item in tasks
        if item.task.kind is TaskKind.NORMAL
        and item.task.status in (Status.RUNNING, Status.PAUSED)
        and item.task.progress is None
    )
    return Burndown(
        first,
        last,
        True,
        since.date(),
        len(tasks),
        initial,
        actual,
        planned,
        future,
        tuple(is_workday(first + timedelta(i), holidays) for i in range(days)),
        today_index,
        fraction,
        _marks(tasks, low, now, last),
        unset,
        rest,
        required,
        recent,
        recent_days,
        behind,
        ahead,
    )
