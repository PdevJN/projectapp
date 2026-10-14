"""プレビューのガントチャートを、PlantUML のガント(`@startgantt`)のテキストにする。NiceGUI には依存しない。"""

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from projectapp.events import color_hex
from projectapp.filtering import TaskFilter, matches, section_has_match
from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.timeline import Scale, Schedule, current_progress, effective_end, effective_start, is_overdue

PLANTUML_FILE_TYPES = ("PlantUML ファイル (*.puml)",)
UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
SCALE_NAMES = {Scale.DAY: "daily", Scale.WEEK: "weekly", Scale.MONTH: "monthly"}
STATUS_COLORS = {  # gantt.STATUS_COLORS と同じ(あちらは NiceGUI に依存するので、写して持つ。テストで一致を確かめる)
    Status.NOT_STARTED: "#78909c",
    Status.RUNNING: "#1e88e5",
    Status.PAUSED: "#fb8c00",
    Status.DONE: "#9e9e9e",
}
OVERDUE_COLOR = "#e53935"
MAX_ASSIGNEE_NAMES = 3  # これを超える担当者は「ほか n 名」にまとめる
EVENT_SECTION = "イベント"


@dataclass(frozen=True)
class PlantUml:
    text: str
    task_count: int  # 出したタスク(チェックポイントを含む)の数
    skipped: int  # 期間の外・日程なしで出さなかったタスクの数(絞り込みで除いたものは数えない)


def default_filename(project_name: str, today: date) -> str:
    """既定のファイル名 `<名前>_<YYYYMMDD>.puml`。ファイル名に使えない文字は `_` にする。"""
    name = UNSAFE_NAME_CHARS.sub("_", project_name.strip()).lstrip(".")
    return f"{name or 'gantt'}_{today:%Y%m%d}.puml"


def write_text(path: Path, text: str) -> Path:
    """テキストを書く。拡張子がなければ .puml を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    if not path.suffix:
        path = path.with_name(path.name + ".puml")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".plantuml-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def _safe(text: str) -> str:
    """PlantUML の `[ ]` の中に置けるよう、角括弧を丸括弧に替える。"""
    return text.replace("[", "(").replace("]", ")")


def _days(start: datetime, end: datetime | None) -> tuple[date, date]:
    """開始日と、終了日(含む)。終了が 0 時ちょうどなら前日。終了が開始日より前なら開始日。"""
    first = start.date()
    if end is None:
        return first, first
    last = (end - timedelta(seconds=1) if end.time() == time(0, 0) else end).date()
    return first, max(first, last)


def _assignees(task: Task) -> str:
    names = task.assignee_names
    if not names:
        return ""
    shown = "・".join(names[:MAX_ASSIGNEE_NAMES])
    more = len(names) - MAX_ASSIGNEE_NAMES
    return f" ({shown}ほか{more}名)" if more > 0 else f" ({shown})"


def build_plantuml(
    project: Project,
    holidays: dict[date, str],
    period: tuple[date, date],
    scale: Scale,
    task_filter: TaskFilter,
    now: datetime,
    *,
    show_chips: bool = True,
    show_alerts: bool = True,
    show_events: bool = True,
) -> PlantUml:
    """プレビューの設定で見えるガントチャートを、PlantUML のテキストにする。プロジェクトは変えない。"""
    p_start, p_end = period
    schedule = Schedule(project, holidays)
    used: set[str] = set()
    aliases: dict[str, str] = {}  # タスクの id → 別名(T1, T2, ...)。出したものだけ
    order: list[Task] = []
    skipped = 0

    def unique(label: str) -> str:
        candidate, n = label, 1
        while candidate in used:
            n += 1
            candidate = f"{label}#{n}"
        used.add(candidate)
        return candidate

    head = [
        "@startgantt",
        f"title {project.name}",
        f"printscale {SCALE_NAMES[scale]}",
        f"Project starts {p_start.isoformat()}",
        "saturday are closed",
        "sunday are closed",
    ]
    head += [
        f"{day.isoformat()} is closed"
        for day in sorted(holidays)
        if p_start <= day <= p_end and day.weekday() < 5
    ]

    event_lines: list[str] = []
    if show_events:
        shown = [e for e in project.events if e.start <= p_end and e.end >= p_start]
        for e in shown:
            head.append(
                f"{max(e.start, p_start).isoformat()} to {min(e.end, p_end).isoformat()}"
                f" are colored in {color_hex(e.color)}"
            )
        for n, e in enumerate(shown, 1):
            label = unique(_safe(e.text))
            event_lines.append(
                f"[{label}] as [E{n}] starts {max(e.start, p_start).isoformat()}"
                f" and ends {min(e.end, p_end).isoformat()}"
            )
            event_lines.append(f"[E{n}] is colored in {color_hex(e.color)}")

    def emit(task: Task, target: list[str]) -> None:
        nonlocal skipped
        start = effective_start(task, project, holidays, schedule)
        if start is None:
            skipped += 1
            return
        first, last = _days(start, effective_end(task, project, holidays, schedule))
        if last < p_start or first > p_end:
            skipped += 1
            return
        first, last = max(first, p_start), min(last, p_end)
        alias = f"T{len(aliases) + 1}"
        label = unique(_safe(task.name) + (_assignees(task) if show_chips else ""))
        aliases[task.id] = alias
        order.append(task)
        if task.kind is TaskKind.CHECKPOINT:
            target.append(f"[{label}] as [{alias}] happens on {first.isoformat()}")
        else:
            target.append(f"[{label}] as [{alias}] starts {first.isoformat()} and ends {last.isoformat()}")
            progress = current_progress(task)
            if show_chips and progress is not None:
                target.append(f"[{alias}] is {progress}% completed")
        overdue = show_alerts and is_overdue(task, project, holidays, now, schedule)
        target.append(f"[{alias}] is colored in {OVERDUE_COLOR if overdue else STATUS_COLORS[task.status]}")

    root_body: list[str] = []  # セクションに属さないタスク(区切りなし)。イベントの区切りより前に置く
    for task in project.tasks:
        if matches(task, task_filter):
            emit(task, root_body)
    section_body: list[str] = []

    def visit(section: Section, names: list[str]) -> None:
        if task_filter.active and not section_has_match(section, task_filter):
            return
        path = [*names, section.name]
        block: list[str] = []
        for task in section.tasks:
            if matches(task, task_filter):
                emit(task, block)
        if block:
            section_body.append(f"-- {' / '.join(path)} --")
            section_body.extend(block)
        for child in section.sections:
            visit(child, path)

    for section in project.sections:
        visit(section, [])

    arrows = [
        f"[{aliases[pid]}] -> [{aliases[task.id]}]"
        for task in order
        for pid in task.predecessors
        if pid in aliases and pid != task.id
    ]
    lines = [*head, *root_body]
    if event_lines:
        lines += [f"-- {EVENT_SECTION} --", *event_lines]
    lines += [*section_body, *arrows, "@endgantt"]
    return PlantUml("\n".join(lines) + "\n", len(aliases), skipped)
