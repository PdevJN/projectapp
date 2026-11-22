"""アサイン専用画面の不足と余裕(要望 168 段階 4a。要望 158 の不足の定義)。NiceGUI に依存しない純粋関数。

基準日(締切、なければ手で決めた完了予定)までに、このタスクの担当で積める稼働量が、残りの工数に足りているかを見る。
算出された完了予定は基準にしない(割り当てから決まるので、常に足りてしまう)。稼働量の数え方は警告の判定(`pace.py`)と同じ。"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import (
    Schedule,
    crew_of,
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


def due_of(task: Task) -> tuple[datetime, str] | None:
    """基準日と、その種類。締切があればそれ、なければ手で決めた完了予定。どちらもなければ None。"""
    if task.deadline is not None:
        return task.deadline, "締切"
    if task.planned_end_manual and task.planned_end is not None:
        return task.planned_end, "完了予定"
    return None


def task_shortage(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> Shortage | str:
    """不足と余裕。出せないときは、その理由の文字列を返す。"""
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクではありません"
    if task.status is Status.DONE:
        return "終了したタスクです"
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return "工数がありません"
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
    if due_at <= origin:
        return "基準日を過ぎています"
    capacity = work_capacity(
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
    unit = work_capacity(
        origin, due_at, project.daily_hours, project.work_start, holidays
    )
    return Shortage(rest, capacity, unit, due_at, basis)


def shortage_text(value: Shortage) -> str:
    """`あと 12.0h 足りません(約 0.8 人)`・`余裕 6.0h(約 0.4 人)`・`ちょうど`。人数は 100% の人に換算した数。"""
    kind = value.kind
    if kind == "ちょうど":
        return "ちょうど"
    hours = abs(value.gap)
    people = value.people
    tail = "" if people is None else f"(約 {people:.1f} 人)"
    if kind == "不足":
        return f"あと {hours:.1f}h 足りません{tail}"
    return f"余裕 {hours:.1f}h{tail}"


def shortage_hint(value: Shortage) -> str:
    """ホバーの文字。`残り 40.0h / 稼働 28.0h(11/30 17:00 まで。締切)`。"""
    return (
        f"残り {value.remaining:.1f}h / 稼働 {value.capacity:.1f}h"
        f"({value.due:%m/%d %H:%M} まで。{value.basis})"
    )
