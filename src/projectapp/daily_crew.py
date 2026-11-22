"""日ごとの担当(要望 135)。NiceGUI に依存しない純粋関数。

週ごとの担当(`Task.weekly_crew`。実効の開始の日から 7 日ごと)のうち、選んだ週だけを日ごとにできる
(`Task.daily_crew`)。日の位置は、起点との暦日の差だけで数える(月・年・閏年で場合分けしない)。
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta

from projectapp.models import (
    MAX_ALLOCATION,
    MAX_WEEKS,
    MIN_ALLOCATION,
    Assignee,
    Task,
    TaskKind,
    union_assignees,
)

WEEK_DAYS = 7
DailyCrew = dict[int, list[list[Assignee]]]
Cell = tuple[int, int | None]  # (週, 日)。日は日ごとの週のセルだけ


def copy_crew(crew: list[Assignee]) -> list[Assignee]:
    return [replace(a) for a in crew]


def copy_weekly(weekly: list[list[Assignee]]) -> list[list[Assignee]]:
    return [copy_crew(week) for week in weekly]


def copy_daily(daily: DailyCrew) -> DailyCrew:
    return {week: [copy_crew(day) for day in days] for week, days in daily.items()}


def rows_of(task: Task) -> tuple[list[list[Assignee]], DailyCrew]:
    """タスクの週ごとの担当と日ごとの担当の複製。週ごとでないタスクは、担当 1 週ぶん(日ごとなし)。"""
    if not task.weekly_crew:
        return [copy_crew(task.assignees)], {}
    return copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)


def _is_daily(daily: DailyCrew, week: int) -> bool:
    days = daily.get(week)
    return days is not None and len(days) == WEEK_DAYS


def crew_spans(
    weekly: list[list[Assignee]], daily: DailyCrew
) -> list[tuple[int, list[Assignee]]]:
    """(日数, 担当) の並び。週は (7, 担当)、日ごとの週は (1, 担当) × 7。最後の要素は以降も続く。
    週の数を超える添字・7 日でない日ごとの担当は無視する。"""
    spans: list[tuple[int, list[Assignee]]] = []
    for number, week in enumerate(weekly):
        if _is_daily(daily, number):
            spans.extend((1, day) for day in daily[number])
        else:
            spans.append((WEEK_DAYS, week))
    return spans


def _tail(weekly: list[list[Assignee]], daily: DailyCrew) -> list[Assignee]:
    """最後の週の、以降も続く担当(最後の週が日ごとなら、その 7 日目)。"""
    last = len(weekly) - 1
    return daily[last][-1] if _is_daily(daily, last) else weekly[last]


def _plus(crew: list[Assignee], names: tuple[str, ...]) -> list[Assignee]:
    present = {a.name for a in crew}
    return copy_crew(crew) + [Assignee(n) for n in names if n not in present]


def with_added_from(
    weekly: list[list[Assignee]],
    daily: DailyCrew,
    offset: int,
    names: tuple[str, ...],
) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週の起点から offset 日目(負は 0)以降に names を足した、週ごとの担当と日ごとの担当。
    offset が週頭(7 の倍数)なら日ごとにせず、その週以降の担当に足す。週の途中なら、その週だけを日ごとにする。
    定義済みの最後の週より先は、直前の担当のコピーで間を埋める。52 週以上になるなら None。入力は変えない。"""
    offset = max(offset, 0)
    week, day = divmod(offset, WEEK_DAYS)
    if week >= MAX_WEEKS:
        return None
    rows = copy_weekly(weekly)
    days_by_week = copy_daily(daily)
    while len(rows) <= week:
        rows.append(copy_crew(_tail(rows, days_by_week)))
    for number in range(week, len(rows)):
        first = day if number == week else 0
        if first == 0 and not _is_daily(days_by_week, number):
            rows[number] = _plus(rows[number], names)
            continue
        days = (
            days_by_week[number]
            if _is_daily(days_by_week, number)
            else [copy_crew(rows[number]) for _ in range(WEEK_DAYS)]
        )
        days = [d if i < first else _plus(d, names) for i, d in enumerate(days)]
        days_by_week[number] = days
        rows[number] = union_assignees(days)
    return rows, days_by_week


@dataclass(frozen=True)
class Segment:
    """棒の上のチップ 1 つぶん。週(day が None)か、日ごとの週の 1 日。"""

    week: int  # 0 始まりの週
    day: int | None  # 日ごとの週の 0〜6。週のままは None
    first: date
    last: date  # この区間の最後の日(含む)
    crew: list[Assignee]
    carried: bool  # 定義済みの週より後(最後の担当が続く)


def segments(
    weekly: list[list[Assignee]], daily: DailyCrew, start: date, last_day: date
) -> list[Segment]:
    """start から last_day(含む)までの表示区間。週は 7 日ぶんで 1 つ、日ごとの週は 1 日ずつ。"""
    result: list[Segment] = []
    number = 0
    while (first := start + timedelta(days=WEEK_DAYS * number)) <= last_day:
        if number < len(weekly) and _is_daily(daily, number):
            for j, crew in enumerate(daily[number]):
                day = first + timedelta(days=j)
                if day > last_day:
                    break
                result.append(Segment(number, j, day, day, crew, False))
        else:
            defined = number < len(weekly)
            crew = weekly[number] if defined else _tail(weekly, daily)
            last = first + timedelta(days=WEEK_DAYS - 1)
            result.append(Segment(number, None, first, last, crew, not defined))
        number += 1
    return result


def split_week(task: Task, week: int) -> Task | None:
    """週を日ごとに分ける(その週の担当を 7 日すべてにコピー)。週ごとでない・上限超え・すでに日ごとは None。
    定義済みの最後の週より先なら、直前の担当のコピーで間を埋める。"""
    if not task.weekly_crew or not 0 <= week < MAX_WEEKS:
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    while len(weekly) <= week:
        weekly.append(copy_crew(_tail(weekly, daily)))
    if _is_daily(daily, week):
        return None
    daily[week] = [copy_crew(weekly[week]) for _ in range(WEEK_DAYS)]
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def merge_week(task: Task, week: int) -> Task | None:
    """日ごとの週を週に戻す(1 日目の担当を週の担当にする)。日ごとでなければ None。"""
    if not _is_daily(task.daily_crew, week) or week >= len(task.weekly_crew):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    weekly[week] = copy_crew(daily.pop(week)[0])
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def set_week_days(task: Task, week: int, days: list[list[Assignee]]) -> Task | None:
    """日ごとの週の 7 日ぶんの担当を差し替える。日ごとでない週・7 日でない・担当のいない日は None。"""
    if (
        not _is_daily(task.daily_crew, week)
        or week >= len(task.weekly_crew)
        or len(days) != WEEK_DAYS
        or not all(days)
    ):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    daily[week] = [copy_crew(day) for day in days]
    weekly[week] = union_assignees(daily[week])
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def _crews(task: Task, weeks: int) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週ごとの担当を返す。週ごとでないタスクは、現在の担当を`weeks`週ぶんに写す。担当者がなければ None。"""
    if task.weekly_crew:
        return copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    if not task.assignees:
        return None
    return [copy_crew(task.assignees) for _ in range(max(weeks, 1))], {}


def add_member(
    task: Task, name: str, week: int, day: int | None = None, *, weeks: int = 1
) -> Task | None:
    """アサイン専用画面(要望 168 段階 2): メンバーを週(日)のセルに、割り当て率 100% で足す。

    週ごとでないタスクは、現在の担当を`weeks`週ぶんに写して週ごとにし、落とした週だけに足す。担当者のいないタスクは
    週ごとにできない(担当のいない週を作らない)ので、全体の担当にする。定義済みの週より先は、直前の担当で間を埋める。
    重複・範囲外(`week`が 0 未満か`MAX_WEEKS`以上、`day`が日ごとの週の 0〜6 の外)は None(何も変えない)。
    """
    if not 0 <= week < MAX_WEEKS or task.kind is not TaskKind.NORMAL:
        return None
    if not task.weekly_crew and not task.assignees:
        return replace(task, assignees=[Assignee(name)])
    padded = _padded(task, week, weeks)
    assert padded is not None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None:
        return None
    missing = [crew for crew in crews if name not in {a.name for a in crew}]
    if not missing:
        return None
    for crew in missing:
        crew.append(Assignee(name))
    return _rebuilt(task, weekly, daily)


def to_weekly(task: Task, weeks: int) -> Task | None:
    """週ごとでないタスクを、現在の担当を`weeks`週ぶんに写して週ごとにする。すでに週ごと・担当者がなければ None。"""
    if task.weekly_crew or not task.assignees:
        return None
    weekly = [copy_crew(task.assignees) for _ in range(max(min(weeks, MAX_WEEKS), 1))]
    return replace(task, weekly_crew=weekly, daily_crew={})


def remove_member(
    task: Task, name: str, week: int, day: int | None = None, *, weeks: int = 1
) -> Task | None:
    """アサイン専用画面: メンバーを週(日)のセルから外す。そのセルの最後の 1 人・いない人は None。
    週ごとでないタスクは`weeks`週ぶんに写して週ごとにしてから、定義済みの週より先は直前の担当で埋めてから外す。
    日ごとの週で`day`がなければ 7 日すべてから外す(どれかの日で最後の 1 人なら None)。"""
    padded = _padded(task, week, weeks)
    if padded is None:
        return None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None:
        return None
    if any(name not in {a.name for a in crew} or len(crew) <= 1 for crew in crews):
        return None  # いない・最後の 1 人は外せない
    for crew in crews:
        crew[:] = [a for a in crew if a.name != name]
    return _rebuilt(task, weekly, daily)


def _padded(
    task: Task, week: int, weeks: int
) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週ごとの担当(複製)を、`week`の週まで直前の担当で埋めて返す。担当者のいない週ごとでないタスク・範囲外の週は None。"""
    if not 0 <= week < MAX_WEEKS:
        return None
    crews = _crews(task, min(weeks, MAX_WEEKS))
    if crews is None:
        return None
    weekly, daily = crews
    while len(weekly) <= week:
        weekly.append(copy_crew(_tail(weekly, daily)))
    return weekly, daily


def _cell_crews(
    weekly: list[list[Assignee]], daily: DailyCrew, week: int, day: int | None
) -> list[list[Assignee]] | None:
    """`week`(と`day`)のセルの担当の並び。日ごとの週で`day`がなければ 7 日ぶん。日の指定が合わなければ None。"""
    if _is_daily(daily, week):
        targets = range(WEEK_DAYS) if day is None else [day]
        if any(not 0 <= j < WEEK_DAYS for j in targets):
            return None
        return [daily[week][j] for j in targets]
    return None if day is not None else [weekly[week]]


def _in_range(value: float) -> bool:
    """割り当て率の範囲(`nan`・無限大は範囲外)。"""
    return MIN_ALLOCATION <= value <= MAX_ALLOCATION


def current_allocation(
    task: Task, name: str, week: int, day: int | None = None
) -> float | None:
    """アサイン専用画面(要望 168 段階 3a): セルにいるメンバーの割り当て率。いない・セルが合わないときは None。
    週ごとでないタスクは全体の担当の率、定義済みの週より先は直前の担当の率。"""
    padded = _padded(task, week, week + 1)
    if padded is None:
        return None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None or len(crews) != 1:
        return None
    return next((a.allocation for a in crews[0] if a.name == name), None)


def _rebuilt(task: Task, weekly: list[list[Assignee]], daily: DailyCrew) -> Task:
    """日ごとの週の担当から週の担当を作り直し、全体の担当(和集合)も合わせたタスク。"""
    for week, days in daily.items():
        if week < len(weekly) and len(days) == WEEK_DAYS:
            weekly[week] = union_assignees(days)
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def set_allocation(
    task: Task,
    name: str,
    value: float,
    week: int,
    day: int | None = None,
    *,
    weeks: int = 1,
) -> Task | None:
    """アサイン専用画面: 週(日)のセルのメンバーの割り当て率を`value`にする。そのセルだけが変わる。

    週ごとでないタスクは、`add_member`と同じく`weeks`週ぶんに写して週ごとにしてから変える(定義済みの週より先は直前の担当で埋める)。
    日ごとの週で`day`がなければ 7 日すべて。`None`(何も変えない): 範囲外の率・`nan`・通常でないタスク・範囲外の週・
    日の指定が合わない・そのセルにメンバーがいない・値が今と同じ・担当者のいない週ごとでないタスク。"""
    if task.kind is not TaskKind.NORMAL or not _in_range(value):
        return None
    padded = _padded(task, week, weeks)
    if padded is None:
        return None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None:
        return None
    found = [a for crew in crews for a in crew if a.name == name]
    if len(found) != len(crews) or all(a.allocation == value for a in found):
        return None
    for assignee in found:
        assignee.allocation = value
    return _rebuilt(task, weekly, daily)


def set_allocation_all(task: Task, name: str, value: float) -> Task | None:
    """アサイン専用画面: そのメンバーがいるすべての週(日ごとの週はすべての日)の割り当て率を`value`にする。
    いない週には足さない。週ごとでないタスクは、全体の担当の率だけを変える(週ごとにしない)。
    1 つも変わらないとき・範囲外の率・通常でないタスクは None。"""
    if task.kind is not TaskKind.NORMAL or not _in_range(value):
        return None
    if not task.weekly_crew:
        found = [a for a in task.assignees if a.name == name]
        if not found or all(a.allocation == value for a in found):
            return None
        return replace(
            task,
            assignees=[
                replace(a, allocation=value) if a.name == name else replace(a)
                for a in task.assignees
            ],
        )
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    crews = [
        crew
        for number, week in enumerate(weekly)
        for crew in (daily[number] if _is_daily(daily, number) else [week])
    ]
    found = [a for crew in crews for a in crew if a.name == name]
    if not found or all(a.allocation == value for a in found):
        return None
    for assignee in found:
        assignee.allocation = value
    return _rebuilt(task, weekly, daily)


def ordered_cells(first: Cell, last: Cell) -> tuple[Cell, Cell]:
    """2 つのセルを日付の順(週、日。日がなければ 0)に並べる。"""

    def key(cell: Cell) -> tuple[int, int]:
        return cell[0], cell[1] or 0

    return (first, last) if key(first) <= key(last) else (last, first)


def cell_in_range(first: Cell, last: Cell, week: int, day: int | None) -> bool:
    """アサイン専用画面: `first`〜`last`(両端を含む。逆順でもよい)の範囲に、セル`(week, day)`が入るか。
    日ごとでない週(`day`が None)は、その週が範囲の週にかかれば入る。"""
    low, high = ordered_cells(first, last)
    if not low[0] <= week <= high[0]:
        return False
    if day is None:
        return True
    if week == low[0] and low[1] is not None and day < low[1]:
        return False
    return not (week == high[0] and high[1] is not None and day > high[1])


def range_cells(daily: DailyCrew, first: Cell, last: Cell) -> list[Cell]:
    """範囲のセルの並び。日ごとの週は日のセル(範囲の端の週は範囲の日だけ)、そうでない週は週のセル。"""
    low, high = ordered_cells(first, last)
    cells: list[Cell] = []
    for week in range(low[0], high[0] + 1):
        if not _is_daily(daily, week):
            cells.append((week, None))
            continue
        start = low[1] if week == low[0] and low[1] is not None else 0
        end = high[1] if week == high[0] and high[1] is not None else WEEK_DAYS - 1
        cells.extend((week, day) for day in range(start, end + 1))
    return cells


def add_member_range(
    task: Task, name: str, first: Cell, last: Cell, *, weeks: int = 1
) -> Task | None:
    """アサイン専用画面(要望 168 段階 3b): `first`〜`last`の範囲のすべてのセルに、メンバーを 100% で足す。
    すでにいるセルは飛ばす。週ごとでないタスク・担当者のいないタスク・定義済みの週より先は`add_member`と同じ。
    `None`(何も変えない): すべてのセルにすでにいる・範囲が 0 未満か`MAX_WEEKS`以上の週にかかる・通常でないタスク。"""
    low, high = ordered_cells(first, last)
    if low[0] < 0 or high[0] >= MAX_WEEKS or task.kind is not TaskKind.NORMAL:
        return None
    result = task
    changed = False
    for week, day in range_cells(task.daily_crew, low, high):
        step = add_member(result, name, week, day, weeks=weeks)
        if step is not None:
            result = step
            changed = True
    return result if changed else None
