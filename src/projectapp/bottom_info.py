"""ガントチャートの下部パネルの内容(要望 95)。NiceGUI に依存しない純粋関数。判定は既存の関数に任せる。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from projectapp.dashboard import _progress_weight
from projectapp.models import Project, Status, Task, TaskKind
from projectapp.pace import warning_pace
from projectapp.timeline import Schedule, overdue_reasons

DetailLine = tuple[str, str]
DASH = "—"
KIND_LABELS = {
    TaskKind.NORMAL: "通常",
    TaskKind.SUMMARY: "まとめ",
    TaskKind.CHECKPOINT: "チェックポイント",
    TaskKind.REFERENCE: "プロジェクト参照",
}


@dataclass(frozen=True)
class TaskDetail:
    title: str
    kind: str
    lines: list[DetailLine]
    notes: list[str] = field(default_factory=list)  # 遅れ・警告の理由
    others: int = 0  # ほかに選んでいる件数


@dataclass(frozen=True)
class PeriodSummary:
    total: int
    counts: dict[Status, int]
    hours: float
    no_effort: int
    percent: float | None  # 工数で重みづけした進捗率。数えるタスクがなければ None
    overdue: int
    warned: int


@dataclass(frozen=True)
class TodayRow:
    name: str
    assignees: str
    progress: int | None
    end: datetime | None


@dataclass(frozen=True)
class LegendEntry:
    group: str
    label: str
    css_class: str  # gantt.py の状態・優先度のクラス名。印は空
    note: str = ""


def _stamp(value: datetime | None) -> str:
    return DASH if value is None else f"{value:%m/%d %H:%M}"


def _crew(task: Task) -> str:
    if not task.assignees:
        return DASH
    return "・".join(f"{a.name} {round(a.allocation * 100)}%" for a in task.assignees)


def task_detail(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule,
    others: int = 0,
) -> TaskDetail:
    """選んだタスクの詳細。種別ごとに、持っている項目だけを出す。"""
    kind = KIND_LABELS[task.kind]
    lines: list[DetailLine] = [("状態", task.status.value)]
    if task.kind is TaskKind.CHECKPOINT:
        lines.append(("締切", _stamp(task.deadline)))
        return TaskDetail(
            task.name,
            kind,
            lines,
            _notes(task, project, holidays, now, schedule),
            others,
        )
    if task.kind is TaskKind.SUMMARY:
        lines.append(("子", f"{len(task.children)} 件"))
    lines += [
        ("担当", _crew(task)),
        ("開始予定", _stamp(schedule.start(task))),
        (
            "完了予定",
            _stamp(schedule.end(task))
            + ("(手指定)" if task.planned_end_manual else ""),
        ),
        ("締切", _stamp(task.deadline)),
        ("工数", f"{task.effort_hours:.1f}h" if task.effort_hours > 0 else DASH),
        ("進捗度", f"{task.progress}%" if task.progress is not None else DASH),
        ("実績", f"{len(task.actuals)} 区間" if task.actuals else DASH),
        ("リンク", f"{len(task.urls)} 件" if task.urls else DASH),
        ("先行", f"{len(task.predecessors)} 件" if task.predecessors else DASH),
    ]
    return TaskDetail(
        task.name, kind, lines, _notes(task, project, holidays, now, schedule), others
    )


def _notes(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule,
) -> list[str]:
    notes = overdue_reasons(task, project, holidays, now, schedule)
    pace = warning_pace(task, project, holidays, now, schedule)
    if pace is not None:
        notes.append(pace.hint())
    return notes


def _overlaps(task: Task, schedule: Schedule, period: tuple[date, date]) -> bool:
    start, end = schedule.start(task), schedule.end(task)
    if start is None and end is None:
        return False
    first = (start or end).date()
    last = (end or start).date()
    return first <= period[1] and last >= period[0]


def period_summary(
    tasks: list[Task],
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule,
    period: tuple[date, date] | None,
) -> PeriodSummary:
    """見えているタスクの集計。まとめ・チェックポイント・プロジェクト参照は数えない。period があれば、かかるタスクだけ。"""
    counts = {status: 0 for status in Status}
    weighted = hours = total_weight = 0.0
    no_effort = overdue = warned = total = 0
    for task in tasks:
        if task.kind is not TaskKind.NORMAL:
            continue
        if period is not None and not _overlaps(task, schedule, period):
            continue
        total += 1
        counts[task.status] += 1
        if task.effort_hours > 0:
            hours += task.effort_hours
        else:
            no_effort += 1
        weight_and_percent = _progress_weight(task)
        if weight_and_percent is not None:
            weight, percent = weight_and_percent
            weighted += weight * percent
            total_weight += weight
        if overdue_reasons(task, project, holidays, now, schedule):
            overdue += 1
        elif warning_pace(task, project, holidays, now, schedule) is not None:
            warned += 1
    percent = weighted / total_weight if total_weight > 0 else None
    return PeriodSummary(total, counts, hours, no_effort, percent, overdue, warned)


def today_plan(tasks: list[Task], schedule: Schedule, now: datetime) -> list[TodayRow]:
    """今日が日程にかかる、未終了の通常タスク。完了予定が 0 時ちょうどなら前日までとする。"""
    today = now.date()
    rows: list[TodayRow] = []
    for task in tasks:
        if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
            continue
        start, end = schedule.start(task), schedule.end(task)
        if start is None or end is None:
            continue
        last = (
            (end - timedelta(microseconds=1)).date()
            if end.time() == time(0)
            else end.date()
        )
        if start.date() <= today <= last:
            rows.append(
                TodayRow(
                    task.name,
                    "・".join(task.assignee_names) or DASH,
                    task.progress,
                    end,
                )
            )
    return rows


LEGEND = [
    LegendEntry("状態", "未着手", "status-not-started", "棒の色"),
    LegendEntry("状態", "実行中", "status-running", "棒の色"),
    LegendEntry("状態", "一時停止", "status-paused", "棒の色"),
    LegendEntry("状態", "終了", "status-done", "棒の色"),
    LegendEntry("優先度", "高", "prio-high", "名前欄の背景"),
    LegendEntry("優先度", "中", "prio-medium", "名前欄の背景"),
    LegendEntry("優先度", "低", "prio-low", "名前欄の背景"),
    LegendEntry("印", "赤い行", "", "遅れ(完了予定か締切を過ぎた)"),
    LegendEntry("印", "黄色い行", "", "警告(完了予定を過ぎそう)"),
    LegendEntry("印", "縞", "", "割り当て超過(同じ人の割り当てが 100% 超)"),
    LegendEntry("印", "◆", "", "締切(大きい◆はチェックポイント)"),
    LegendEntry("印", "赤い縦線", "", "今日"),
]
