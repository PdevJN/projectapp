"""PlantUML のガント(`@startgantt`)のテキストから、新規プロジェクトを作る。NiceGUI には依存しない。"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from projectapp.models import (
    MAX_SECTION_DEPTH,
    MAX_YEAR,
    MIN_YEAR,
    Assignee,
    Member,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
    new_id,
    tidy_task_name,
)
from projectapp.storage import dumps_project, parse_project

PLANTUML_OPEN_FILE_TYPES = ("PlantUML ファイル (*.puml;*.plantuml;*.txt)",)
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
MAX_LASTS_DAYS = 3660  # 期間の上限(稼働日)。これを超える指定は読み飛ばす
MAX_SEARCH_DAYS = 3660  # 稼働日を探す日数の上限(全日が休みでも止まる)
WORKDAYS_PER_WEEK = 5
UNNAMED = "名称なし"

_D = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"
_START = re.compile(r"@startgantt\b", re.I)
_END = re.compile(r"@endgantt\b", re.I)
_TITLE = re.compile(r"title\s+(.+)$", re.I)
_PROJECT_STARTS = re.compile(rf"project\s+starts?\s+(?:on\s+)?{_D}$", re.I)
_WEEKDAY_RULE = re.compile(rf"({'|'.join(WEEKDAYS)})s?\s+(?:is|are)\s+(closed|open)$", re.I)
_RANGE_RULE = re.compile(rf"{_D}\s+to\s+{_D}\s+(?:is|are)\s+(closed|open)$", re.I)
_DAY_RULE = re.compile(rf"{_D}\s+(?:is|are)\s+(closed|open)$", re.I)
_SECTION = re.compile(r"--\s*(.+?)\s*--$")
_TASK = re.compile(r"\[([^\]]+)\](?:\s+as\s+\[([^\]]+)\])?(?:\s+(.*))?$", re.I)
_IGNORED = re.compile(r"(?:printscale|scale|hide|header|footer|caption|skinparam|language)\b|.*\bcolored\s+in\b", re.I)
_COLORED = re.compile(r"(?:\band\s+)?\b(?:is|are)\s+colored\s+in\s+\S+", re.I)
_HAPPENS_ON = re.compile(rf"\bhappens\s+on\s+{_D}", re.I)
_STARTS_DATE = re.compile(rf"\bstarts?\s+(?:on\s+)?{_D}", re.I)
_ENDS_DATE = re.compile(rf"\bends?\s+(?:on\s+)?{_D}", re.I)
_LASTS = re.compile(r"\blasts?\s+(\d+)\s+(day|week)s?\b", re.I)
_ON = re.compile(r"\bon\s+((?:\{[^}]*\}\s*)+)", re.I)
_RESOURCE = re.compile(r"\{\s*([^}:]*?)\s*(?::\s*(\d+(?:\.\d+)?)\s*%)?\s*\}")
_PROGRESS = re.compile(r"\bis\s+(\d{1,3})%\s+completed\b", re.I)
_REF = r"\[([^\]]+)\]'s\s+(end|start)"
_DEPENDENCY = re.compile(r"\[([^\]]+)\]\s*->\s*\[([^\]]+)\]$")
_HAPPENS_AT = re.compile(rf"\bhappens\s+at\s+{_REF}", re.I)
_STARTS_AT = re.compile(rf"\bstarts?\s+at\s+{_REF}", re.I)
_STARTS_AFTER = re.compile(r"\bstarts?\s+(\d+)\s+days?\s+after\s+\[([^\]]+)\]'s\s+end", re.I)


class PlantUmlImportError(ValueError):
    """取り込めないテキスト(囲みがない・タスクがない・結果が不正)。"""


@dataclass(frozen=True)
class PlantUmlImport:
    project: Project
    task_count: int
    created_members: int  # 自動で作ったメンバーの数
    skipped_lines: int  # 解釈できず読み飛ばした行の数
    unresolved: int  # 日程が求まらなかったタスクの数
    clamped_allocations: int  # 範囲外で 100% にした割り当て率の数


def _parse_date(text: str) -> date | None:
    try:
        year, month, day = (int(part) for part in re.split(r"[-/]", text))
        value = date(year, month, day)
    except ValueError:
        return None
    return value if MIN_YEAR <= year <= MAX_YEAR else None


def _section_path(text: str) -> tuple[str, ...]:
    """`親 / 子` を名前の並びにする。3 階層を超える分は、3 階層目の名前につなぐ。"""
    parts = [part for part in (tidy_task_name(p) for p in text.split("/")) if part]
    if len(parts) > MAX_SECTION_DEPTH:
        merged = tidy_task_name(" / ".join(parts[MAX_SECTION_DEPTH - 1 :]))
        parts = [*parts[: MAX_SECTION_DEPTH - 1], merged]
    return tuple(parts)


@dataclass
class _Raw:
    """読み取ったタスク 1 件(日付の解決の前)。"""

    name: str
    section: tuple[str, ...]
    milestone: bool = False
    day: date | None = None  # starts / happens on
    end_day: date | None = None
    lasts: int | None = None  # 稼働日数
    after: tuple[str, str, int] | None = None  # (参照するタスク, "end" か "start", 日数)
    preds: list[str] = field(default_factory=list)  # `->` の先行(名前または別名)
    assignees: list[tuple[str, float | None]] = field(default_factory=list)  # (名前, `:N%` の N。省略は None)
    progress: int | None = None
    bad_date: bool = False  # 日付の書式はあるが、日付として読めなかった(PlantUML ではエラー。日程なしにする)


class _Scanner:
    """行ごとに読む。解釈できない行は数える。"""

    def __init__(self) -> None:
        self.title = ""
        self.project_start: date | None = None
        self.first_date: date | None = None  # タスクの行で最初に現れた日付
        self.closed_weekdays = {5, 6}
        self.day_rules: dict[date, bool] = {}  # 日付 → 休みか
        self.tasks: list[_Raw] = []
        self.sections: list[tuple[str, ...]] = []
        self.skipped = 0
        self.complete = False
        self._started = False
        self._section: tuple[str, ...] = ()
        self._alias: dict[str, int] = {}
        self._names: dict[str, int] = {}

    def lookup(self, key: str) -> int | None:
        key = key.strip()
        return self._alias.get(key, self._names.get(key))

    def scan(self, text: str) -> None:
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("﻿")
            if not self._started:
                self._started = _START.match(line) is not None
                continue
            if _END.match(line):
                self.complete = True
                return
            if line and not line.startswith("'") and not self._line(line):
                self.skipped += 1

    def _line(self, line: str) -> bool:
        """行を解釈できたか。"""
        if m := _TITLE.match(line):
            self.title = m.group(1).strip()
            return True
        if m := _PROJECT_STARTS.match(line):
            day = _parse_date(m.group(1))
            if day is not None:
                self.project_start = day
            return day is not None
        if m := _WEEKDAY_RULE.match(line):
            index = WEEKDAYS[m.group(1).lower()]
            if m.group(2).lower() == "closed":
                self.closed_weekdays.add(index)
            else:
                self.closed_weekdays.discard(index)
            return True
        if m := _RANGE_RULE.match(line):
            return self._range(m.group(1), m.group(2), m.group(3).lower() == "closed")
        if m := _DAY_RULE.match(line):
            day = _parse_date(m.group(1))
            if day is not None:
                self.day_rules[day] = m.group(2).lower() == "closed"
            return day is not None
        if m := _SECTION.match(line):
            self._enter_section(_section_path(m.group(1)))
            return True
        if m := _DEPENDENCY.match(line):
            self._declare(m.group(1), None)
            self.tasks[self._declare(m.group(2), None)].preds.append(m.group(1).strip())
            return True
        if line.startswith("["):
            return self._task_line(line)
        return _IGNORED.match(line) is not None

    def _range(self, first: str, last: str, closed: bool) -> bool:
        start, end = _parse_date(first), _parse_date(last)
        if start is None or end is None or end < start or (end - start).days > MAX_SEARCH_DAYS:
            return False
        for offset in range((end - start).days + 1):
            self.day_rules[start + timedelta(days=offset)] = closed
        return True

    def _enter_section(self, path: tuple[str, ...]) -> None:
        self._section = path
        for depth in range(1, len(path) + 1):
            if path[:depth] not in self.sections:
                self.sections.append(path[:depth])

    def _declare(self, key: str, alias: str | None) -> int:
        """名前(または別名)のタスクの番号。なければ作る。`as` の別名は覚える。"""
        key = key.strip()
        index = self.lookup(key)
        if index is None:
            index = len(self.tasks)
            self.tasks.append(_Raw(key, self._section))
            self._names[key] = index
        if alias and alias.strip():
            self._alias[alias.strip()] = index
        return index

    def _task_line(self, line: str) -> bool:
        m = _TASK.match(line)
        if m is None or not m.group(1).strip():
            return False
        raw = self.tasks[self._declare(m.group(1), m.group(2))]
        rest = (m.group(3) or "").strip()
        return not rest or self._clauses(raw, rest)

    def _clauses(self, raw: _Raw, rest: str) -> bool:
        """タスクの行の続き。ひとつでも解釈できれば True。"""
        rest, colored = _COLORED.subn(" ", rest)
        matched = colored > 0
        if m := _ON.search(rest):
            raw.assignees += [(n, float(p) if p else None) for n, p in _RESOURCE.findall(m.group(1))]
            rest = f"{rest[: m.start()]} {rest[m.end() :]}"
            matched = True
        if (m := _PROGRESS.search(rest)) and int(m.group(1)) <= 100:
            raw.progress, matched = int(m.group(1)), True
        return self._when(raw, rest) or matched

    def _note(self, text: str) -> date | None:
        day = _parse_date(text)
        if day is not None and self.first_date is None:
            self.first_date = day
        return day

    def _when(self, raw: _Raw, rest: str) -> bool:
        matched = False
        if m := _HAPPENS_ON.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.milestone, raw.day, matched = True, day, True
            else:
                raw.bad_date = True
        elif m := _HAPPENS_AT.search(rest):
            raw.milestone, raw.after, matched = True, (m.group(1).strip(), m.group(2).lower(), 0), True
        elif m := _STARTS_AT.search(rest):
            raw.after, matched = (m.group(1).strip(), m.group(2).lower(), 0), True
        elif m := _STARTS_AFTER.search(rest):
            raw.after, matched = (m.group(2).strip(), "end", int(m.group(1))), True
        elif m := _STARTS_DATE.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.day, matched = day, True
            else:
                raw.bad_date = True
        if m := _ENDS_DATE.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.end_day, matched = day, True
            else:
                raw.bad_date = True
        if m := _LASTS.search(rest):
            count = int(m.group(1)) * (WORKDAYS_PER_WEEK if m.group(2).lower() == "week" else 1)
            if 1 <= count <= MAX_LASTS_DAYS:
                raw.lasts, matched = count, True
        return matched


@dataclass(frozen=True)
class _Calendar:
    closed_weekdays: frozenset[int]
    day_rules: dict[date, bool]

    def is_open(self, day: date) -> bool:
        closed = self.day_rules.get(day)
        return day.weekday() not in self.closed_weekdays if closed is None else not closed

    def next_open(self, day: date) -> date | None:
        """その日以降で最初の稼働日。見つからなければ None。"""
        for offset in range(MAX_SEARCH_DAYS):
            candidate = day + timedelta(days=offset)
            if self.is_open(candidate):
                return candidate
        return None


Span = tuple[date | None, date | None]


def _in_range(span: Span) -> bool:
    return all(day is not None and MIN_YEAR <= day.year <= MAX_YEAR for day in span)


class _Resolver:
    """PlantUML のルールで、タスクの開始日・終了日(含む)を求める。"""

    def __init__(self, scanner: _Scanner, today: date) -> None:
        self.scanner = scanner
        self.today = today
        self.calendar = _Calendar(frozenset(scanner.closed_weekdays), dict(scanner.day_rules))
        self._memo: dict[int, Span] = {}
        self._active: set[int] = set()

    def span(self, index: int) -> Span:
        if index in self._memo:
            return self._memo[index]
        if index in self._active:  # 循環
            return None, None
        self._active.add(index)
        try:
            result = self._compute(self.scanner.tasks[index])
        finally:
            self._active.discard(index)
        self._memo[index] = result
        return result

    def _compute(self, raw: _Raw) -> Span:
        if raw.milestone:
            day = raw.day if raw.day is not None else self._anchor(raw.after)
            result: Span = (day, day)
        else:
            start = self._start(raw)
            result = (None, None) if start is None else (start, self._end(raw, start))
        return result if _in_range(result) else (None, None)

    def _anchor(self, after: tuple[str, str, int] | None) -> date | None:
        """参照するタスクの終了日(`end`)か開始日(`start`)。求まらなければ None。"""
        if after is None:
            return None
        index = self.scanner.lookup(after[0])
        if index is None:
            return None
        start, end = self.span(index)
        return start if after[1] == "start" else end

    def _start(self, raw: _Raw) -> date | None:
        if raw.day is not None:
            return raw.day
        if raw.after is not None:
            base = self._anchor(raw.after)
            if base is None:
                return None
            if raw.after[1] == "start":
                return base
            return self.calendar.next_open(base + timedelta(days=1 + raw.after[2]))
        if raw.preds:
            ends = [self._anchor((key, "end", 0)) for key in raw.preds]
            known = [end for end in ends if end is not None]
            if len(known) != len(ends):
                return None
            return self.calendar.next_open(max(known) + timedelta(days=1))
        if raw.bad_date:
            return None
        # 日付がまったくないガントは、PlantUML では相対の日数(1 日目から)で描かれる。取り込み日を 1 日目とみなす
        return self.scanner.project_start or self.scanner.first_date or self.today

    def _end(self, raw: _Raw, start: date) -> date:
        if raw.end_day is not None:
            return max(raw.end_day, start)
        day = self.calendar.next_open(start)  # 開始日が休みなら、次の稼働日から数える
        if day is None:
            return start
        for _ in range((raw.lasts or 1) - 1):
            following = self.calendar.next_open(day + timedelta(days=1))
            if following is None:
                break
            day = following
        return day


@dataclass
class _Counts:
    unresolved: int = 0
    clamped: int = 0
    created_members: int = 0


class _Builder:
    """読み取った結果と解決した日付から、`Project` を組み立てる。"""

    def __init__(self, scanner: _Scanner, name: str, today: date) -> None:
        self.scanner = scanner
        self.resolver = _Resolver(scanner, today)
        self.project = Project(tidy_task_name(scanner.title) or name, base_date=scanner.project_start or today)
        self.counts = _Counts()
        self._taken: set[str] = set()
        self._sections: dict[tuple[str, ...], Section] = {}
        self._members: dict[str, Member] = {}

    def build(self) -> Project:
        for path in self.scanner.sections:
            self._section(path)
        tasks = [self._task(index, raw) for index, raw in enumerate(self.scanner.tasks)]
        for raw, task in zip(self.scanner.tasks, tasks):
            (self._section(raw.section).tasks if raw.section else self.project.tasks).append(task)
        self._link(tasks)
        return self.project

    def _link(self, tasks: list[Task]) -> None:
        """`->` と、終わりからの指定(`'s end`)の参照先を、先行タスクにする(`'s start` は入れない)。"""
        for index, (raw, task) in enumerate(zip(self.scanner.tasks, tasks)):
            keys = list(raw.preds)
            if raw.after is not None and raw.after[1] == "end":
                keys.append(raw.after[0])
            for key in keys:
                found = self.scanner.lookup(key)
                if found is None or found == index or tasks[found].id in task.predecessors:
                    continue
                if not self._reaches(tasks, tasks[found], task.id):  # 循環になる連結は入れない
                    task.predecessors.append(tasks[found].id)

    @staticmethod
    def _reaches(tasks: list[Task], start: Task, target: str) -> bool:
        """`start` から先行をたどって、`target` の id に着くか。"""
        by_id = {task.id: task for task in tasks}
        seen: set[str] = set()
        stack = [start.id]
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current not in seen:
                seen.add(current)
                stack.extend(by_id[current].predecessors)
        return False

    def _fresh(self) -> str:
        value = new_id(self._taken)
        self._taken.add(value)
        return value

    def _end_of_day(self, day: date) -> datetime:
        return datetime.combine(day, self.project.work_start) + timedelta(hours=self.project.daily_hours)

    def _section(self, path: tuple[str, ...]) -> Section:
        if path not in self._sections:
            section = Section(path[-1], id=self._fresh())
            siblings = self.project.sections if len(path) == 1 else self._section(path[:-1]).sections
            siblings.append(section)
            self._sections[path] = section
        return self._sections[path]

    def _task(self, index: int, raw: _Raw) -> Task:
        start, end = self.resolver.span(index)
        task = Task(tidy_task_name(raw.name) or UNNAMED, id=self._fresh())
        task.status = _status(raw.progress)
        task.progress = raw.progress or None  # 0 は入れない(未着手と区別しない)
        if start is None or end is None:
            self.counts.unresolved += 1
        elif raw.milestone:
            task.kind = TaskKind.CHECKPOINT
            task.deadline = self._end_of_day(start)
            task.status = Status.DONE if task.status is Status.DONE else Status.NOT_STARTED
            task.progress = None  # チェックポイントは進捗度を持たない
            return task
        else:
            task.planned_start = datetime.combine(start, self.project.work_start)
            task.planned_end = self._end_of_day(end)
        task.assignees = self._assignees(raw)
        return task

    def _assignees(self, raw: _Raw) -> list[Assignee]:
        found: list[Assignee] = []
        for raw_name, percent in raw.assignees:
            name = tidy_task_name(raw_name)
            if not name or any(a.name == name for a in found):
                continue
            if name not in self._members:
                member = Member(name, id=self._fresh())
                self._members[name] = member
                self.project.members.append(member)
                self.counts.created_members += 1
            allocation = 1.0 if percent is None else percent / 100
            if percent is not None and not 1 <= percent <= 100:
                allocation = 1.0
                self.counts.clamped += 1
            found.append(Assignee(name, allocation))
        return found


def _status(progress: int | None) -> Status:
    if not progress:
        return Status.NOT_STARTED
    return Status.DONE if progress == 100 else Status.RUNNING


def parse_plantuml(text: str, name: str, today: date | None = None) -> PlantUmlImport:
    """PlantUML のガントのテキストから、新規プロジェクトを作る。取り込めなければ `PlantUmlImportError`。
    `today` は、日付がまったくないガントの 1 日目(省略は今日)。"""
    scanner = _Scanner()
    scanner.scan(text)
    if not scanner.complete:
        raise PlantUmlImportError("@startgantt から @endgantt までが見つかりません")
    if not scanner.tasks:
        raise PlantUmlImportError("取り込めるタスクがありません")
    builder = _Builder(scanner, name, today or date.today())
    project = builder.build()
    try:  # 保存・読込と同じ検証を通す
        project = parse_project(dumps_project(project), project.name)
    except (ValueError, KeyError, TypeError) as exc:
        raise PlantUmlImportError(f"取り込んだ結果が正しくありません: {exc}") from exc
    counts = builder.counts
    return PlantUmlImport(
        project,
        len(project.all_tasks()),
        counts.created_members,
        scanner.skipped,
        counts.unresolved,
        counts.clamped,
    )


def summary(result: PlantUmlImport) -> str:
    """取り込み後の通知。件数と、取り込めなかったものの内訳。"""
    head = f"タスク {result.task_count} 件"
    if result.created_members:
        head += f"、メンバー {result.created_members} 人を作成"
    notes = [
        f"読み飛ばした行 {result.skipped_lines} 行" if result.skipped_lines else "",
        f"日程が求まらないタスク {result.unresolved} 件" if result.unresolved else "",
        f"割り当て率を 100% にした担当 {result.clamped_allocations} 件" if result.clamped_allocations else "",
    ]
    detail = "、".join(note for note in notes if note)
    return f"取り込みました({head})" + (f"。{detail}" if detail else "")


def read_plantuml(path: Path) -> str:
    """UTF-8 のテキストを読む(BOM は除く)。読めなければ `PlantUmlImportError`。"""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise PlantUmlImportError(f"ファイルを読めません: {exc}") from exc
