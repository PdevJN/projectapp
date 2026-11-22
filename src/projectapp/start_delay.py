"""着工遅れ・停止の判定(要望 161)。NiceGUI に依存しない。

日付で比べ、時刻は見ない。日数はプロジェクト全体の稼働日(土日・祝日・休みのイベント)で数える。
個人の休み・稼働日の上書きは見ない(要望 162)。結果は保存せず、表示のたびに算出する。
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.timeline import Schedule, effective_start, is_workday


class DelayKind(StrEnum):
    START = "start"  # 着手済みで、開始が予定より遅れた
    UNSTARTED = "unstarted"  # 開始予定を過ぎても着手していない
    STOP = "stop"  # 実績の区間の間に、作業のなかった稼働日がある・一時停止のまま


@dataclass(frozen=True)
class StartDelay:
    kind: DelayKind
    since: datetime  # 帯の始まり
    until: datetime  # 帯の終わり
    days: int  # 稼働日数
    ongoing: bool = False  # until が今(まだ続いている)か


def missed_workdays(
    first: date,
    last: date,
    holidays: dict[date, str],
    *,
    include_first: bool,
    include_last: bool,
) -> int:
    """first から last までの稼働日の数。端の日を数えるかは引数で決める。last が first より前なら 0。"""
    if last < first:
        return 0
    total = 0
    current = first
    while current <= last:
        edge = (current == first and not include_first) or (
            current == last and not include_last
        )
        if not edge and is_workday(current, holidays):
            total += 1
        current += timedelta(days=1)
    return total


def start_delays(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    now: datetime,
) -> list[StartDelay]:
    """タスクの着工遅れ・停止。猶予日数(`project.start_delay_grace`)を超えたものだけ。
    先頭は着工か未着手(あれば 1 つ)、続けて停止(実績の区間の順)。対象外(通常タスク以外・開始が決まらない)は空。"""
    if task.kind is not TaskKind.NORMAL:
        return []
    planned = effective_start(task, project, holidays, schedule)
    if planned is None:
        return []
    grace = project.start_delay_grace
    found: list[StartDelay] = []
    actuals = task.actuals
    if actuals:
        began = actuals[0].start
        days = missed_workdays(
            planned.date(),
            began.date(),
            holidays,
            include_first=True,
            include_last=False,
        )
        if days > grace:
            found.append(StartDelay(DelayKind.START, planned, began, days))
    elif task.status is Status.NOT_STARTED:
        days = missed_workdays(
            planned.date(),
            now.date(),
            holidays,
            include_first=True,
            include_last=False,
        )
        if days > grace:
            found.append(StartDelay(DelayKind.UNSTARTED, planned, now, days, True))
    for before, after in zip(actuals, actuals[1:]):
        if before.end is None or after.start <= before.end:
            continue  # 進行中の区間の後ろ・重なり・逆順(手で編集したファイル)は、停止にしない
        days = missed_workdays(
            before.end.date(),
            after.start.date(),
            holidays,
            include_first=False,
            include_last=False,
        )
        if days > grace:
            found.append(StartDelay(DelayKind.STOP, before.end, after.start, days))
    if actuals and task.status is Status.PAUSED and actuals[-1].end is not None:
        ended = actuals[-1].end
        if now > ended:
            days = missed_workdays(
                ended.date(),
                now.date(),
                holidays,
                include_first=False,
                include_last=False,
            )
            if days > grace:
                found.append(StartDelay(DelayKind.STOP, ended, now, days, True))
    return found


def _moment(value: datetime) -> str:
    return value.strftime("%m/%d %H:%M")


def chip_texts(delays: list[StartDelay]) -> list[tuple[DelayKind, str, str]]:
    """名前の欄のチップ(種類・文言・ホバー)。停止は複数あっても 1 つにまとめ、日数は合計、ホバーは区間ごとに 1 行。"""
    chips: list[tuple[DelayKind, str, str]] = []
    stops = [d for d in delays if d.kind is DelayKind.STOP]
    for delay in delays:
        if delay.kind is DelayKind.START:
            chips.append(
                (
                    delay.kind,
                    f"着工 +{delay.days}日",
                    f"予定の開始 {delay.since.strftime('%m/%d')} → 着工 {_moment(delay.until)}",
                )
            )
        elif delay.kind is DelayKind.UNSTARTED:
            chips.append(
                (
                    delay.kind,
                    f"未着手 +{delay.days}日",
                    f"予定の開始 {delay.since.strftime('%m/%d')} を過ぎても着手していません",
                )
            )
    if stops:
        lines = [
            f"{_moment(s.since)} 〜 {'(今)' if s.ongoing else _moment(s.until)}({s.days}日)"
            for s in stops
        ]
        chips.append(
            (DelayKind.STOP, f"停止 +{sum(s.days for s in stops)}日", "\n".join(lines))
        )
    return chips
