"""ガントチャートの下部パネルの内容(要望 95)。NiceGUI に依存しない純粋関数。判定は既存の関数に任せる。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from projectapp.dashboard import Span, _day_peak, _progress_weight
from projectapp.models import Project, Status, Task, TaskKind
from projectapp.pace import warning_pace
from projectapp.timeline import (
    OVERLOAD_EPSILON,
    Column,
    Schedule,
    counted_pieces,
    is_workday,
    overdue_reasons,
)
from projectapp.workdays import work_day_map

# 状態ごとの色のクラス(gantt.py の棒の色と同じ。--scolor を定める)
STATUS_CLASS = {
    Status.NOT_STARTED: "status-not-started",
    Status.RUNNING: "status-running",
    Status.PAUSED: "status-paused",
    Status.DONE: "status-done",
}
# 状態ごとのアイコン(Material Icons の名前)。形でも見分けられる
STATUS_ICON = {
    Status.NOT_STARTED: "radio_button_unchecked",
    Status.RUNNING: "play_circle",
    Status.PAUSED: "pause_circle",
    Status.DONE: "check_circle",
}
DetailLine = tuple[str, str]
NAME_WIDTH_VAR = "--assign-name-w"  # gantt_drag.py の JS と同じ名前
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
    no_effort_tasks: tuple[tuple[str, str], ...] = ()  # 工数未設定の(id, 名前)
    status_tasks: dict[Status, tuple[str, ...]] = field(
        default_factory=dict
    )  # 状態ごとのタスク名(集計に数えたもの)


@dataclass(frozen=True)
class TodayRow:
    name: str
    assignees: str
    progress: int | None
    end: datetime | None
    status: Status = Status.NOT_STARTED  # 文字の色分け用


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
    first = start or end
    last = end or start
    if first is None or last is None:
        return False
    return first.date() <= period[1] and last.date() >= period[0]


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
    no_effort_tasks: list[tuple[str, str]] = []
    status_tasks: dict[Status, list[str]] = {status: [] for status in Status}
    for task in tasks:
        if task.kind is not TaskKind.NORMAL:
            continue
        if period is not None and not _overlaps(task, schedule, period):
            continue
        total += 1
        counts[task.status] += 1
        status_tasks[task.status].append(task.name)
        if task.effort_hours > 0:
            hours += task.effort_hours
        else:
            no_effort += 1
            no_effort_tasks.append((task.id, task.name))
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
    return PeriodSummary(
        total,
        counts,
        hours,
        no_effort,
        percent,
        overdue,
        warned,
        tuple(no_effort_tasks),
        {status: tuple(names) for status, names in status_tasks.items()},
    )


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
                    task.status,
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


@dataclass(frozen=True)
class AssignmentCell:
    load: float  # 日次はその日の負荷。週次・月次は、期間の稼働日の平均(1.0 = 100%)
    over: bool  # 期間のどこかに 100% 超の日がある
    closed: bool  # 期間に稼働日が 1 日もない
    tasks: tuple[str, ...] = ()  # 期間にかかる、その担当者のタスク名(重複なし)


@dataclass(frozen=True)
class AssignmentRow:
    name: str
    cells: list[AssignmentCell]
    icon: str = ""  # メンバーのアイコン(なければ空)


@dataclass(frozen=True)
class AssignmentTable:
    labels: list[str]
    rows: list[AssignmentRow]


@dataclass(frozen=True)
class AssignmentLayout:
    """割り当て表の列幅(px)。ガントチャートの名前欄と日付の列にそろえる。"""

    name_px: int  # 担当者の列(チャートの名前欄の幅)
    column_px: int  # 日付の列 1 つ(チャートの`COLUMN_WIDTH_PX`)

    @property
    def name_css(self) -> str:
        """担当者の列の幅。名前欄のドラッグ中は、JS が CSS 変数で動かす(なければ、いまの名前欄の幅)。"""
        return f"var({NAME_WIDTH_VAR}, {self.name_px}px)"

    def grid_columns(self, count: int) -> str:
        if count <= 0:  # 列がなくても不正な CSS にしない
            return self.name_css
        return f"{self.name_css} repeat({count}, {self.column_px}px)"

    def width_css(self, count: int) -> str:
        return f"calc({self.name_css} + {self.column_px * max(count, 0)}px)"


def assignment_table(
    tasks: list[Task],
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    columns: list[Column],
) -> AssignmentTable:
    """担当者×列の割り当て率。tasks(絞り込み後)で数える区間のある担当者だけを、メンバーの並びで行にする。"""
    spans: dict[str, list[Span]] = {}
    pieces: dict[str, list[tuple[datetime, datetime, str]]] = {}
    for task in tasks:
        for left, right, crew in counted_pieces(task, project, holidays, schedule):
            for assignee in crew:
                spans.setdefault(assignee.name, []).append(
                    (left, right, assignee.allocation)
                )
                pieces.setdefault(assignee.name, []).append((left, right, task.name))
    rows: list[AssignmentRow] = []
    for member in project.members:
        items = spans.get(member.name)
        if not items:
            continue
        overrides = work_day_map(member.work_days)
        cells: list[AssignmentCell] = []
        for column in columns:
            days = [
                column.start + timedelta(days=n)
                for n in range((column.end - column.start).days)
            ]
            open_days = [d for d in days if is_workday(d, holidays, overrides)]
            if not open_days:
                cells.append(AssignmentCell(0.0, False, True))
                continue
            peaks = [_day_peak(items, d) for d in open_days]
            begin = datetime.combine(column.start, time.min)
            finish = datetime.combine(column.end, time.min)
            names = dict.fromkeys(  # 並びは入力順のまま、同じ名前は 1 つにする
                name
                for left, right, name in pieces[member.name]
                if left < finish and right > begin
            )
            cells.append(
                AssignmentCell(
                    sum(peaks) / len(peaks),
                    any(p > 1.0 + OVERLOAD_EPSILON for p in peaks),
                    False,
                    tuple(names),
                )
            )
        rows.append(AssignmentRow(member.name, cells, member.icon))
    return AssignmentTable([c.label for c in columns], rows)
