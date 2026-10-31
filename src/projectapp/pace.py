"""警告の判定(要望 103)。残りの工数が、完了予定までの稼働量に収まるかを見る。NiceGUI に依存しない純粋関数。

予定どおりに進んでいれば、残りの工数と稼働量は同じ(比 100%)になる。比が WARNING_RATIO を超えると、
このペースでは完了予定を超える見込みなので警告にする。予定超過(`is_overdue`)になったタスクは、赤い行に任せる。"""

from dataclasses import dataclass
from datetime import date, datetime
from math import inf, isfinite

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import (
    Schedule,
    crew_of,
    effective_end,
    effective_start,
    is_overdue,
    weekly_crews,
    work_capacity,
)

WARNING_RATIO = 1.10  # 残りの工数 ÷ 稼働量 がこれ以上で警告(固定)
_EPSILON = 1e-9  # 比の比較の許容差(浮動小数の丸め)


@dataclass(frozen=True)
class Pace:
    remaining: float  # 残りの工数[h]
    capacity: float  # 今から完了予定までに積める稼働量[h](換算率つき)

    @property
    def ratio(self) -> float:
        """残りの工数 ÷ 稼働量。稼働量がないときは inf。"""
        return inf if self.capacity <= 0 else self.remaining / self.capacity

    @property
    def warning(self) -> bool:
        return self.ratio >= WARNING_RATIO - _EPSILON

    def hint(self) -> str:
        """ホバーの文字。稼働量がないときは、割合を出さない。"""
        head = f"警告: 残り {self.remaining:.1f}h / 稼働 {self.capacity:.1f}h"
        return head if self.capacity <= 0 else f"{head}({self.ratio * 100:.0f}%)"


def pace(
    task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule | None = None
) -> Pace | None:
    """タスクの残りの工数と稼働量。判定できないとき(通常タスクでない・終了・工数なし・日程なし・
    完了予定を過ぎた・予定超過・残りなし)は None。"""
    if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
        return None
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return None
    schedule = schedule or Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    end = effective_end(task, project, holidays, schedule)
    if start is None or end is None or end <= now:
        return None
    if is_overdue(task, project, holidays, now, schedule):
        return None
    rest = remaining_hours(task, project, holidays, now)
    if not rest > 0:
        return None
    capacity = work_capacity(
        max(now, start),
        end,
        project.daily_hours,
        project.work_start,
        holidays,
        crew=crew_of(task.assignees, project.members, project.parameters, task.parameters, project.ratio_limits),
        weeks=weekly_crews(task, project) or None,
        weeks_start=start.date(),
    )
    return Pace(rest, capacity)


def warning_pace(
    task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule | None = None
) -> Pace | None:
    """警告のときだけ Pace を返す(行の背景とホバーに使う)。"""
    value = pace(task, project, holidays, now, schedule)
    return value if value is not None and value.warning else None
