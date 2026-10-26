"""CSV・TSV(Smartsheet のガントチャートのテンプレートの形)から、新規プロジェクトを作る。NiceGUI には依存しない。"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
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
    new_id,
    tidy_task_name,
)
from projectapp.storage import dumps_project, parse_project
from projectapp.timeline import MAX_WORKDAYS, is_workday

CSV_OPEN_FILE_TYPES = ("CSV TSV ファイル (*.csv;*.tsv)",)
WBS_SEPARATOR = "#"  # WBS 番号とタイトルをつなぐ文字(書き出しでは、この最初の 1 文字で分ける)
WBS_NUMBER = re.compile(r"\d+(?:\.\d+)*")
TITLE_COLUMN = "タスクのタイトル"
COLUMN_NAMES = {  # 空白を除いた列名 → 項目
    "WBS番号": "wbs",
    TITLE_COLUMN: "title",
    "タスクオーナー": "owner",
    "タスクのオーナー": "owner",
    "開始日": "start",
    "期限": "end",
    "タスク完了率": "progress",
}
_ISO_DATE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_JA_DATE = re.compile(r"(\d{2}|\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_PERCENT = re.compile(r"(\d{1,3})\s*%?")


class CsvImportError(ValueError):
    """取り込めないファイル(タイトルの列がない・タスクがない・読めない・結果が不正)。"""


@dataclass(frozen=True)
class CsvImport:
    project: Project
    task_count: int
    section_count: int
    created_members: int  # 自動で作ったメンバーの数
    skipped_rows: int  # タイトルがなく読み飛ばした行の数
    unresolved: int  # 日付が読めない・期限が開始日より前で、日程を入れなかったタスクの数
    invalid_progress: int  # 読めず、入れなかった完了率の数
    dropped_values: int  # セクションにした行で、日付・オーナー・完了率を取り込まなかった行の数


def _plain(text: str) -> str:
    """全角を半角にして、前後の空白を除く(日付・完了率・WBS 番号の判定用)。"""
    return unicodedata.normalize("NFKC", text).strip()


def _column_key(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def parse_date(text: str) -> date | None:
    """`2026-10-05`・`2026/10/5`・`26年 10月 5日`・`2026年10月5日`(全角も可)を読む。2 桁の年は 2000 年代。読めなければ None。"""
    plain = _plain(text)
    found = _ISO_DATE.fullmatch(plain) or _JA_DATE.fullmatch(plain)
    if found is None:
        return None
    year, month, day = (int(part) for part in found.groups())
    if year < 100:
        year += 2000
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_percent(text: str) -> int | None:
    """`50`・`50%` を 0〜100 の整数で読む。読めない・範囲外は None。"""
    found = _PERCENT.fullmatch(_plain(text))
    if found is None or int(found.group(1)) > 100:
        return None
    return int(found.group(1))


def _status(progress: int) -> Status:
    if progress == 0:
        return Status.NOT_STARTED
    return Status.DONE if progress == 100 else Status.RUNNING


@dataclass
class _Row:
    wbs: str
    title: str
    owner: str
    start: str
    end: str
    progress: str

    @property
    def blank_fields(self) -> bool:
        return not (self.owner or self.start or self.end or self.progress)

    @property
    def section_depth(self) -> int | None:
        """WBS 番号の階層(`1` が 1、`1.1` が 2)。番号でなければ None。"""
        return self.wbs.count(".") + 1 if WBS_NUMBER.fullmatch(self.wbs) else None

    @property
    def name(self) -> str:
        return tidy_task_name(f"{self.wbs}{WBS_SEPARATOR}{self.title}" if self.wbs else self.title)


def _rows(text: str) -> list[_Row | None]:
    """ヘッダー行を探し、そのあとの行を読む。空行は読み飛ばし、タイトルのない行は None で返す。"""
    lines = text.splitlines()
    header_at = next((i for i, line in enumerate(lines) if TITLE_COLUMN in _column_key(line)), None)
    if header_at is None:
        raise CsvImportError(f"「{TITLE_COLUMN}」の列が見つかりません")
    delimiter = "\t" if lines[header_at].count("\t") >= lines[header_at].count(",") else ","
    table = csv.reader(io.StringIO("\n".join(lines[header_at:])), delimiter=delimiter)
    header = next(table)
    columns = {COLUMN_NAMES[key]: index for index, cell in enumerate(header) if (key := _column_key(cell)) in COLUMN_NAMES}
    rows: list[_Row | None] = []
    for cells in table:
        if not any(cell.strip() for cell in cells):
            continue

        def cell(name: str) -> str:
            index = columns.get(name)
            return cells[index].strip() if index is not None and index < len(cells) else ""

        row = _Row(_plain(cell("wbs")), cell("title"), cell("owner"), cell("start"), cell("end"), cell("progress"))
        rows.append(row if tidy_task_name(row.title) else None)
    return rows


class _Builder:
    def __init__(self, name: str, holidays: dict[date, str], today: date) -> None:
        self.project = Project(name)
        self.holidays = holidays
        self.today = today
        self.taken: set[str] = set()
        self.stack: list[Section] = []  # 開いているセクション(先頭が 1 階層目)
        self.members: dict[str, Member] = {}
        self.starts: list[date] = []
        self.ends: list[date] = []
        self.sections = self.created_members = self.unresolved = self.invalid_progress = self.dropped = 0

    def fresh(self) -> str:
        value = new_id(self.taken)
        self.taken.add(value)
        return value

    def add(self, row: _Row) -> None:
        depth = row.section_depth
        if row.blank_fields or depth == 1:
            if not row.blank_fields:
                self.dropped += 1
            self.add_section(row)
        else:
            self.add_task(row)

    def add_section(self, row: _Row) -> None:
        depth = min(row.section_depth or 1, MAX_SECTION_DEPTH, len(self.stack) + 1)  # 階層を飛ばした分は詰める
        del self.stack[depth - 1 :]
        section = Section(row.name, id=self.fresh())
        (self.stack[-1].sections if self.stack else self.project.sections).append(section)
        self.stack.append(section)
        self.sections += 1

    def add_task(self, row: _Row) -> None:
        task = Task(row.name, id=self.fresh())
        if row.progress:
            value = parse_percent(row.progress)
            if value is None:
                self.invalid_progress += 1
            else:
                task.status, task.progress = _status(value), value or None
        owner = tidy_task_name(row.owner)
        if owner:
            task.assignees = [Assignee(owner, 1.0)]
            self.member(owner)
        self.schedule(task, row)
        (self.stack[-1].tasks if self.stack else self.project.tasks).append(task)

    def member(self, name: str) -> None:
        if name not in self.members:
            self.members[name] = Member(name, id=self.fresh())
            self.project.members.append(self.members[name])
            self.created_members += 1

    def schedule(self, task: Task, row: _Row) -> None:
        """開始日・期限から日程を入れる。両方あれば、稼働日数 × 稼働可能時間を工数にして、完了予定は算出に任せる。"""
        start = parse_date(row.start) if row.start else None
        end = parse_date(row.end) if row.end else None
        if (row.start and start is None) or (row.end and end is None) or (start and end and end < start):
            self.unresolved += 1
            return
        project = self.project
        if start is not None:
            task.planned_start = datetime.combine(start, project.work_start)
            self.starts.append(start)
        if end is None:
            return
        self.ends.append(end)
        if start is not None:
            days = sum(is_workday(start + timedelta(days=n), self.holidays) for n in range((end - start).days + 1))
            if 0 < days <= MAX_WORKDAYS:
                task.effort_hours = days * project.daily_hours
                if is_workday(end, self.holidays):
                    return  # 完了予定は算出で期限の日の終業時刻になる
                task.planned_end_manual = True  # 期限が休みの日: 算出だと直前の稼働日に縮むので、期限を手で指定する
        task.planned_end = datetime.combine(end, project.work_start) + timedelta(hours=project.daily_hours)

    def build(self) -> Project:
        dates = self.starts or self.ends
        self.project.base_date = min(dates) if dates else self.today
        return self.project


def parse_csv(text: str, name: str, holidays: dict[date, str], today: date | None = None) -> CsvImport:
    """CSV・TSV のテキストから、新規プロジェクトを作る。取り込めなければ `CsvImportError`。
    `holidays` は稼働日数の数え方に使う。`today` は、日付がまったくないときの基準日(省略は今日)。"""
    builder = _Builder(name, holidays, today or date.today())
    skipped = 0
    for row in _rows(text):
        if row is None:
            skipped += 1
        else:
            builder.add(row)
    project = builder.build()
    if not project.all_tasks() and not builder.sections:
        raise CsvImportError("取り込める行がありません")
    try:  # 保存・読込と同じ検証を通す
        project = parse_project(dumps_project(project), project.name)
    except (ValueError, KeyError, TypeError) as exc:
        raise CsvImportError(f"取り込んだ結果が正しくありません: {exc}") from exc
    return CsvImport(
        project,
        len(project.all_tasks()),
        builder.sections,
        builder.created_members,
        skipped,
        builder.unresolved,
        builder.invalid_progress,
        builder.dropped,
    )


def summary(result: CsvImport) -> str:
    """取り込み後の通知。件数と、取り込めなかったものの内訳。"""
    head = f"タスク {result.task_count} 件"
    if result.section_count:
        head += f"、セクション {result.section_count} 件"
    if result.created_members:
        head += f"、メンバー {result.created_members} 人を作成"
    notes = [
        f"読み飛ばした行 {result.skipped_rows} 行" if result.skipped_rows else "",
        f"日程が求まらないタスク {result.unresolved} 件" if result.unresolved else "",
        f"読めない完了率 {result.invalid_progress} 件" if result.invalid_progress else "",
        f"セクションの行の値を取り込まなかった行 {result.dropped_values} 行" if result.dropped_values else "",
    ]
    detail = "、".join(note for note in notes if note)
    return f"取り込みました({head})" + (f"。{detail}" if detail else "")


def read_table(path: Path) -> str:
    """テキストを読む。UTF-8(BOM は除く)を先に試し、読めなければ Shift_JIS。読めなければ `CsvImportError`。"""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CsvImportError(f"ファイルを読めません: {exc}") from exc
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvImportError("文字コードを判定できません(UTF-8 か Shift_JIS にしてください)")
