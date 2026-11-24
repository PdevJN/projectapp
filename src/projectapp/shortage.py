"""アサイン専用画面の不足と余裕(要望 168 段階 4a。要望 158 の不足の定義)。NiceGUI に依存しない純粋関数。

基準日(締切、なければ手で決めた完了予定)までに、このタスクの担当で積める稼働量が、残りの工数に足りているかを見る。
算出された完了予定は基準にしない(割り当てから決まるので、常に足りてしまう)。稼働量の数え方は警告の判定(`pace.py`)と同じ。"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from math import ceil, isfinite

from projectapp.models import (
    MAX_ALLOCATION,
    Assignee,
    Project,
    Status,
    Task,
    TaskKind,
)
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import (
    Schedule,
    crew_of,
    effective_end,
    effective_start,
    weekly_crews,
    work_capacity,
)

GAP_EPSILON = 0.05  # 時間を小数 1 桁で表したとき 0.0 になる差(これ未満は`ちょうど`)


@dataclass(frozen=True)
class Shortage:
    remaining: float  # 残りの工数[h]
    capacity: float  # 今から基準日までに、このタスクの担当で積める稼働量[h](換算率つき)
    unit: float  # 同じ範囲に、100% の人 1 人が積める稼働量[h](人数への換算の分母)
    due: datetime  # 基準日
    basis: str  # `締切`か`完了予定`

    @property
    def gap(self) -> float:
        """残りの工数 − 稼働量。正なら不足、負なら余裕。"""
        return self.remaining - self.capacity

    @property
    def kind(self) -> str:
        if abs(self.gap) < GAP_EPSILON:
            return "ちょうど"
        return "不足" if self.gap > 0 else "余裕"

    @property
    def people(self) -> float | None:
        """不足(余裕)を、100% の人の数に換算した値(絶対値)。換算の分母がないときは None。"""
        return None if self.unit <= 0 else abs(self.gap) / self.unit


def _unfit(task: Task) -> str | None:
    """不足・消化の見通しを出せないタスクの理由。通常のタスクで、終了しておらず、工数があれば None。"""
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクではありません"
    if task.status is Status.DONE:
        return "終了したタスクです"
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return "工数がありません"
    return None


def due_of(task: Task) -> tuple[datetime, str] | None:
    """基準日と、その種類。締切があればそれ、なければ手で決めた完了予定。どちらもなければ None。"""
    if task.deadline is not None:
        return task.deadline, "締切"
    if task.planned_end_manual and task.planned_end is not None:
        return task.planned_end, "完了予定"
    return None


def _capacity_of(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    origin: datetime,
    due_at: datetime,
    start: datetime,
) -> float:
    """今から基準日までに、このタスクの担当で積める稼働量[h](換算率つき)。`task_shortage`と`required_rate`で共有する。"""
    return work_capacity(
        origin,
        due_at,
        project.daily_hours,
        project.work_start,
        holidays,
        crew=crew_of(
            task.assignees,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        ),
        weeks=weekly_crews(task, project) or None,
        weeks_start=start.date(),
    )


def task_shortage(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> Shortage | str:
    """不足と余裕。出せないときは、その理由の文字列を返す。"""
    reason = _unfit(task)
    if reason is not None:
        return reason
    due = due_of(task)
    if due is None:
        return "基準日(締切か、手で決めた完了予定)がありません"
    schedule = schedule or Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return "開始日がありません"
    rest = remaining_hours(task, project, holidays, now)
    if not rest > 0:
        return "残りの工数がありません"
    origin = max(now, start)
    due_at, basis = due
    if due_at <= now:
        return "基準日を過ぎています"
    if due_at <= start:
        return "基準日が開始より前です"
    capacity = _capacity_of(task, project, holidays, origin, due_at, start)
    unit = work_capacity(
        origin, due_at, project.daily_hours, project.work_start, holidays
    )
    return Shortage(rest, capacity, unit, due_at, basis)


@dataclass(frozen=True)
class WeekBurn:
    week: int  # 週の番号(0 始まり。`CellPlan`と同じ)
    first: datetime  # その週の数える範囲 [first, last)。過ぎた週・範囲が空の週は first == last
    last: datetime
    before: float  # 週の初めの残りの工数[h]
    burn: float  # その週に消化できる工数[h](換算率つき。残りを超えない)
    left: float  # 週の終わりの残りの工数[h](0 以上)

    @property
    def done(self) -> bool:
        """この週で残りが 0 になったか。"""
        return self.before > 0 and self.left <= 0


def weekly_burn(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    weeks: int,
    origin: date,
    schedule: Schedule | None = None,
) -> list[WeekBurn] | str:
    """週ごとの消化の見通し(要望 168 段階 4b)。週 w は [origin + 7w 日, origin + 7(w+1) 日)。
    出せないときは、その理由の文字列を返す。基準日は要らない。"""
    reason = _unfit(task)
    if reason is not None:
        return reason
    schedule = schedule or Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return "開始日がありません"
    rest = remaining_hours(task, project, holidays, now)
    if not rest > 0:
        return "残りの工数がありません"
    counted_from = max(now, start)
    crew = crew_of(
        task.assignees,
        project.members,
        project.parameters,
        task.parameters,
        project.ratio_limits,
    )
    track = weekly_crews(task, project) or None
    result: list[WeekBurn] = []
    left = rest
    for week in range(weeks):
        head = datetime.combine(origin + timedelta(days=7 * week), time.min)
        tail = head + timedelta(days=7)
        first = min(max(head, counted_from), tail)
        capacity = (
            work_capacity(
                first,
                tail,
                project.daily_hours,
                project.work_start,
                holidays,
                crew=crew,
                weeks=track,
                weeks_start=origin,
            )
            if first < tail
            else 0.0
        )
        before = left
        burn = min(capacity, before)
        left = before - burn
        result.append(WeekBurn(week, first, tail, before, burn, left))
    return result


def burn_text(value: WeekBurn, narrow: bool = False) -> str:
    """`消化 12.0h / 残り 28.0h`・`消化 6.0h / 完了`・`—`(完了したあとの週)。狭いときは`12.0h→28.0h`・`6.0h 完了`。"""
    if value.before <= 0:
        return "—"
    if value.done:
        return f"{value.burn:.1f}h 完了" if narrow else f"消化 {value.burn:.1f}h / 完了"
    if narrow:
        return f"{value.burn:.1f}h→{value.left:.1f}h"
    return f"消化 {value.burn:.1f}h / 残り {value.left:.1f}h"


def burn_hint(value: WeekBurn) -> str:
    """ホバーの文字。`10/05〜10/11 の稼働 32.5h。残り 40.0h → 7.5h`。期間は週の頭から末日まで。"""
    head = value.last - timedelta(days=7)
    last_day = value.last - timedelta(days=1)
    return (
        f"{head:%m/%d}〜{last_day:%m/%d} の稼働 {value.burn:.1f}h。"
        f"残り {value.before:.1f}h → {value.left:.1f}h"
    )


def shortage_text(value: Shortage) -> str:
    """`あと 12.0h 足りません(約 0.8 人)`・`余裕 6.0h(約 0.4 人)`・`ちょうど`。人数は 100% の人に換算した数。"""
    kind = value.kind
    if kind == "ちょうど":
        return "ちょうど"
    hours = abs(value.gap)
    people = value.people
    tail = "" if people is None or round(people, 1) == 0 else f"(約 {people:.1f} 人)"
    if kind == "不足":
        return f"あと {hours:.1f}h 足りません{tail}"
    return f"余裕 {hours:.1f}h{tail}"


def shortage_hint(value: Shortage) -> str:
    """ホバーの文字。`残り 40.0h / 稼働 28.0h(11/30 17:00 まで。締切)`。"""
    return (
        f"残り {value.remaining:.1f}h / 稼働 {value.capacity:.1f}h"
        f"({value.due:%m/%d %H:%M} まで。{value.basis})"
    )


@dataclass(frozen=True)
class RequiredRate:
    factor: float | None  # 倍率 k。全員 100% でも届かないときは None
    members: tuple[
        tuple[str, float, float], ...
    ]  # (名前, 今の率, 必要な率)。届かないときは空
    short_hours: float  # 届かないときの、足りない時間[h]
    short_people: float | None  # 同じく、100% の人に換算した人数
    shortage: Shortage  # 4a の不足(ヒントに使う)


BISECT_STEPS = 50  # 倍率の二分法の回数(k の上限は最大 100 なので、十分に細かい)


def _crews(task: Task) -> list[list[Assignee]]:
    """全体・週ごと・日ごとのすべての担当。"""
    return [
        task.assignees,
        *task.weekly_crew,
        *(crew for days in task.daily_crew.values() for crew in days),
    ]


def _scaled(task: Task, factor: float) -> Task:
    """担当の率を factor 倍(各人 100% で頭打ち)にした複製。元は変えない。"""

    def scale(crew: list[Assignee]) -> list[Assignee]:
        return [
            replace(a, allocation=min(MAX_ALLOCATION, a.allocation * factor))
            for a in crew
        ]

    return replace(
        task,
        assignees=scale(task.assignees),
        weekly_crew=[scale(crew) for crew in task.weekly_crew],
        daily_crew={
            week: [scale(crew) for crew in days]
            for week, days in task.daily_crew.items()
        },
    )


def required_rate(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> RequiredRate | str:
    """基準日に間に合う、担当の率の倍率(要望 168 段階 4c)。不足のときだけ出す。出せないときは理由の文字列。
    担当の全員の率(全体・週ごと・日ごと)を k 倍して各人 100% で頭打ちにし、稼働量が残りの工数に届く最小の k を求める。"""
    schedule = schedule or Schedule(project, holidays)
    value = task_shortage(task, project, holidays, now, schedule)
    if isinstance(value, str):
        return value
    if value.kind != "不足":
        return "不足していません"
    start = effective_start(task, project, holidays, schedule)
    if start is None:  # task_shortage が通っているので起きないが、型のために
        return "開始日がありません"
    origin = max(now, start)

    def capacity(factor: float) -> float:
        return _capacity_of(
            _scaled(task, factor), project, holidays, origin, value.due, start
        )

    known = {
        member.name for member in project.members
    }  # メンバー表にいない担当者は、稼働に寄与しない
    allocations = [
        a.allocation for crew in _crews(task) for a in crew if a.name in known
    ]
    upper = 1.0 / min(allocations) if allocations else 1.0  # これ以上は全員 100% で同じ
    best = capacity(upper)
    if best < value.remaining - 1e-9:
        short = value.remaining - best
        people = None if value.unit <= 0 else short / value.unit
        return RequiredRate(None, (), short, people, value)
    low, high = 1.0, upper
    for _ in range(BISECT_STEPS):
        mid = (low + high) / 2
        if capacity(mid) >= value.remaining:
            high = mid
        else:
            low = mid
    peaks: dict[str, float] = {}
    for crew in _crews(task):
        for a in crew:
            if a.name not in known:
                continue
            peaks[a.name] = max(peaks.get(a.name, 0.0), a.allocation)
    members = tuple(
        (name, peak, min(MAX_ALLOCATION, peak * high)) for name, peak in peaks.items()
    )
    return RequiredRate(high, members, 0.0, None, value)


def _up(value: float, digits: int = 0) -> float:
    """表示の桁で、足りない側にずれないよう切り上げる(浮動小数点の誤差は除く)。"""
    scale = 10**digits
    return ceil(value * scale - 1e-6) / scale


MEMBERS_SHOWN = 3  # 文言に出す人数(これを超える分は`ほか n 人`)


def required_rate_text(value: RequiredRate) -> str:
    """`必要な率: 今の ×1.7(田中 100%・鈴木 50→85%)`・`全員 100% でもあと 7.5h 足りません(約 0.2 人)`。"""
    if value.factor is None:
        people = value.short_people
        tail = (
            "" if people is None or round(people, 1) == 0 else f"(約 {people:.1f} 人)"
        )
        return f"全員 100% でもあと {value.short_hours:.1f}h 足りません{tail}"
    parts = []
    for name, now_rate, need in value.members[:MEMBERS_SHOWN]:
        before, after = round(now_rate * 100), int(_up(need * 100))
        parts.append(
            f"{name} {before}→{after}%" if after != before else f"{name} {before}%"
        )
    rest = len(value.members) - MEMBERS_SHOWN
    if rest > 0:
        parts.append(f"ほか {rest} 人")
    return f"必要な率: 今の ×{_up(value.factor, 1):.1f}({'・'.join(parts)})"


def required_rate_hint(value: RequiredRate) -> str:
    """ホバーの文字。4a の不足のヒントに、倍率の前提を足す。"""
    base = shortage_hint(value.shortage)
    if value.factor is None:
        return f"{base}。全員の率を 100% にしても、残りの工数に届きません"
    return f"{base}。全員の率を ×{value.factor:.2f}(上限 100%)にすると、稼働が残りの工数に届きます。人ごとの率は、週ごと・日ごとに違う人は最大の率から"


@dataclass(frozen=True)
class TrialCompare:
    before_end: datetime | None  # 前(画面を開いた時点)の完了予定
    after_end: datetime | None  # 後(今の試算)の完了予定
    before: Shortage | None  # 前の不足。基準日がないなど出せないときは None
    after: Shortage | None


def shortage_gap_text(value: Shortage) -> str:
    """比較用の短い形。`あと 7.5h 不足`・`余裕 25.0h`・`ちょうど`(人数は省く)。"""
    kind = value.kind
    if kind == "ちょうど":
        return "ちょうど"
    hours = abs(value.gap)
    return f"あと {hours:.1f}h 不足" if kind == "不足" else f"余裕 {hours:.1f}h"


def compare_trial(
    before_task: Task,
    before_project: Project,
    after_task: Task,
    after_project: Project,
    holidays: dict[date, str],
    now: datetime,
) -> TrialCompare:
    """試算の前後の、完了予定と不足(要望 168 段階 4d)。求まらない項目は None。元は変えない。"""

    def side(task: Task, project: Project) -> tuple[datetime | None, Shortage | None]:
        schedule = Schedule(project, holidays)
        end = effective_end(task, project, holidays, schedule)
        value = task_shortage(task, project, holidays, now, schedule)
        return end, None if isinstance(value, str) else value

    before_end, before = side(before_task, before_project)
    after_end, after = side(after_task, after_project)
    return TrialCompare(before_end, after_end, before, after)


def _compare_parts(value: TrialCompare) -> list[str]:
    parts: list[str] = []
    if value.before_end is not None and value.after_end is not None:
        days = (value.after_end.date() - value.before_end.date()).days
        if days != 0:
            word = "遅れる" if days > 0 else "早まる"
            parts.append(
                f"完了予定 {value.before_end:%m/%d} → {value.after_end:%m/%d}"
                f"({abs(days)} 日{word})"
            )
    if value.before is not None and value.after is not None:
        before, after = shortage_gap_text(value.before), shortage_gap_text(value.after)
        if before != after:
            parts.append(f"{before} → {after}")
    return parts


def compare_changed(value: TrialCompare) -> bool:
    """前後で、完了予定の日付か、不足の文言が変わったか。"""
    return bool(_compare_parts(value))


def compare_text(value: TrialCompare) -> str:
    """`前→後: 完了予定 10/13 → 10/08(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h`。変化がなければ空。"""
    parts = _compare_parts(value)
    return f"前→後: {'・'.join(parts)}" if parts else ""


def compare_hint(value: TrialCompare) -> str:
    """ホバーの文字。前後それぞれの`残り / 稼働(基準日)`。出せない側は書かない。"""
    parts = []
    if value.before is not None:
        parts.append(f"前: {shortage_hint(value.before)}")
    if value.after is not None:
        parts.append(f"後: {shortage_hint(value.after)}")
    return "。".join(parts)
