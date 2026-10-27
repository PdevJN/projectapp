"""プレビューのガントチャートを、PlantUML のガント(`@startgantt`)のテキストにする。NiceGUI には依存しない。"""

import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
from pathlib import Path

from projectapp.events import color_hex
from projectapp.filtering import TaskFilter, matches, section_has_match
from projectapp.models import Assignee, Project, ReferenceValue, Section, Status, Task, TaskKind
from projectapp.timeline import (
    Scale,
    Schedule,
    current_progress,
    effective_end,
    effective_start,
    is_overdue,
    overallocations,
)

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
EVENT_SECTION = "イベント"


@dataclass(frozen=True)
class PlantUml:
    text: str
    task_count: int  # 出したタスク(チェックポイントを含む)の数
    skipped: int  # 期間の外・日程なしで出さなかったタスクの数(絞り込みで除いたものは数えない)
    # PlantUML は日単位で集計するので、100% 超の赤に見えるが、アプリの時刻での判定では超過でない(担当者, 日)
    day_overloads: tuple[tuple[str, date], ...] = ()
    # 週ごとの担当を持つ出力したタスクの数(担当者を出したときだけ)。PlantUML は週ごとを表せず、和集合・最大の割り当て率の近似で出す
    weekly_tasks: int = 0


def day_overload_notice(items: tuple[tuple[str, date], ...]) -> str | None:
    """日単位の集計で 100% 超に見える(担当者, 日)の通知。なければ None。先頭の 3 件を示し、残りは件数にする。"""
    if not items:
        return None
    shown = "、".join(f"{name} {day.month}/{day.day}" for name, day in items[:3])
    more = f" ほか {len(items) - 3} 件" if len(items) > 3 else ""
    return f"PlantUML は日単位で集計するため、100% 超に見える日があります(実際の予定では超過していません): {shown}{more}"


def weekly_crew_notice(count: int) -> str | None:
    """週ごとの担当を近似で出力したことの通知。なければ None。"""
    if count <= 0:
        return None
    return f"週ごとの担当は近似で出力しました({count} 件。和集合の担当者を、各人の最大の割り当て率で出しています)"


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


def _resource(name: str) -> str:
    """担当の構文 `{名前}` の中に置けるよう、波括弧を丸括弧に、コロンを全角にする。"""
    return name.replace("{", "(").replace("}", ")").replace(":", "：")


def _percent(a: Assignee) -> int:
    return max(1, min(100, round(a.allocation * 100))) if isfinite(a.allocation) else 100


def _assignees(task: Task) -> str:
    """` on {田中:60%} {鈴木}`。割り当て率が 100% なら省く。担当なしは空。"""
    parts = []
    for a in task.assignees:
        percent = _percent(a)
        parts.append(f"{{{_resource(a.name)}}}" if percent == 100 else f"{{{_resource(a.name)}:{percent}%}}")
    return f" on {' '.join(parts)}" if parts else ""


def _day_overloads(
    project: Project, holidays: dict[date, str], drawn: list[Task], days: dict[str, tuple[date, date]]
) -> tuple[tuple[str, date], ...]:
    """PlantUML が(日単位の合計で)100% 超に描くが、アプリの時刻での判定では超過でない(担当者, 日)。"""
    totals: dict[tuple[str, date], int] = {}
    for task in drawn:
        first, last = days[task.id]
        for offset in range((last - first).days + 1):
            day = first + timedelta(days=offset)
            if day.weekday() >= 5 or day in holidays:
                continue  # 休みの日は、PlantUML が枠を使わない
            for a in task.assignees:
                key = (a.name, day)
                totals[key] = totals.get(key, 0) + _percent(a)
    real: set[tuple[str, date]] = set()
    for over in overallocations(project, holidays, drawn):
        for offset in range((over.end - timedelta(microseconds=1)).date().toordinal() - over.start.date().toordinal() + 1):
            real.add((over.member, over.start.date() + timedelta(days=offset)))
    flagged = [key for key, total in totals.items() if total > 100 and key not in real]
    return tuple(sorted(flagged, key=lambda key: (key[1], key[0])))


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
    show_today: bool = True,
    today_color: str | None = None,
    excluded: frozenset[str] = frozenset(),
    references: Mapping[str, ReferenceValue] | None = None,
) -> PlantUml:
    """プレビューの設定で見えるガントチャートを、PlantUML のテキストにする。プロジェクトは変えない。"""
    p_start, p_end = period
    schedule = Schedule(project, holidays, references)
    used: set[str] = set()
    aliases: dict[str, str] = {}  # タスクの id → 別名(T1, T2, ...)。出したものだけ
    order: list[Task] = []
    drawn_days: dict[str, tuple[date, date]] = {}  # 出したタスクの id → PlantUML に渡した日付の範囲(含む)
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

    if show_today and p_start <= now.date() <= p_end:
        head.append(f"{now.date().isoformat()} is colored in {today_color or 'red'}")  # PlantUML は線を引けないので、列を塗る

    def emit(task: Task, target: list[str]) -> None:
        nonlocal skipped
        if task.kind is TaskKind.SUMMARY:
            return  # 親子の構文がなく、帯を出すと子と二重になる。親子は区切り(セクション)で表す
        if task.id in excluded:
            return  # 利用者がチェックを外した。省いた件数には数えない
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
        label = unique(_safe(f"{task.name}(参照)" if task.kind is TaskKind.REFERENCE else task.name))
        aliases[task.id] = alias
        order.append(task)
        drawn_days[task.id] = (first, last)
        if task.kind is TaskKind.CHECKPOINT:
            target.append(f"[{label}] as [{alias}] happens on {first.isoformat()}")
        elif task.kind is TaskKind.REFERENCE:  # 参照先全体の 1 本の帯。担当者・進捗は出さない
            target.append(f"[{label}] as [{alias}] starts {first.isoformat()} and ends {last.isoformat()}")
            value = (references or {}).get(task.id)
            late = show_alerts and value is not None and value.delayed > 0
            target.append(f"[{alias}] is colored in {OVERDUE_COLOR if late else STATUS_COLORS[Status.NOT_STARTED]}")
            return
        else:
            on = _assignees(task) if show_chips else ""
            target.append(f"[{label}] as [{alias}]{on} starts {first.isoformat()} and ends {last.isoformat()}")
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

    summaries = {t.id: t for t in project.all_tasks() if t.kind is TaskKind.SUMMARY}

    def source_alias(pid: str) -> str | None:
        """先行の別名。まとめは、出力した子のうち完了が最も遅いものから引く(出した子がなければ引かない)。"""
        if pid in aliases:
            return aliases[pid]
        owner = summaries.get(pid)
        drawn = [t for t in order if owner is not None and t.id in owner.children]
        if not drawn:
            return None
        latest = max(drawn, key=lambda t: schedule.end(t) or datetime.min)
        return aliases[latest.id]

    arrows = []
    for task in order:
        for pid in task.predecessors:
            alias = source_alias(pid)
            if alias is not None and pid != task.id:
                arrows.append(f"[{alias}] -> [{aliases[task.id]}]")
    day_overloads = _day_overloads(project, holidays, order, drawn_days) if show_chips else ()
    lines = [*head, *root_body]
    if event_lines:
        lines += [f"-- {EVENT_SECTION} --", *event_lines]
    lines += [*section_body, *arrows, "@endgantt"]
    weekly_tasks = sum(1 for t in order if t.weekly_crew) if show_chips else 0
    return PlantUml("\n".join(lines) + "\n", len(aliases), skipped, day_overloads, weekly_tasks)
