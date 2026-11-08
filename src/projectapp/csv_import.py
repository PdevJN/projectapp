"""CSV・TSV(Smartsheet のガントチャートのテンプレートの形)から、新規プロジェクトを作る。NiceGUI には依存しない。"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from projectapp import clock
from projectapp.history_log import stamp_creation
from projectapp.csv_profile import (
    ALIASES,
    SMARTSHEET,
    CsvField,
    CsvProfile,
    header_key,
    resolve_columns,
    split_template,
)
from projectapp.models import (
    MAX_CATEGORY_NAME_LENGTH,
    MAX_SECTION_DEPTH,
    MAX_YEAR,
    MIN_YEAR,
    Actual,
    Assignee,
    Category,
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
WBS_SEPARATOR = (
    "#"  # WBS 番号とタイトルをつなぐ文字(書き出しでは、この最初の 1 文字で分ける)
)
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
    unresolved: (
        int  # 日付が読めない・期限が開始日より前で、日程を入れなかったタスクの数
    )
    invalid_progress: int  # 読めず、入れなかった進捗率の数
    dropped_values: (
        int  # セクションにした行で、日付・オーナー・進捗率を取り込まなかった行の数
    )
    invalid_values: int = 0  # 読めない工数・状態・実績と、入れなかった実績の数


def _plain(text: str) -> str:
    """全角を半角にして、前後の空白を除く(日付・進捗率・WBS 番号の判定用)。"""
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


MAX_EFFORT_HOURS = 10000
_EFFORT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h|時間)?", re.IGNORECASE)
_DATETIME = re.compile(r"(.+?)(?:[T\s]+(\d{1,2}):(\d{2}))?")
STATUS_WORDS = {
    "未着手": Status.NOT_STARTED,
    "notstarted": Status.NOT_STARTED,
    "todo": Status.NOT_STARTED,
    "実行中": Status.RUNNING,
    "inprogress": Status.RUNNING,
    "running": Status.RUNNING,
    "一時停止": Status.PAUSED,
    "onhold": Status.PAUSED,
    "paused": Status.PAUSED,
    "終了": Status.DONE,
    "完了": Status.DONE,
    "done": Status.DONE,
    "complete": Status.DONE,
    "completed": Status.DONE,
}


def parse_effort(text: str) -> float | None:
    """`8`・`8.5`・`8h`・`8.5時間` を時間で読む。0 以下・1 万時間超・読めない値は None。"""
    found = _EFFORT.fullmatch(_plain(text))
    if found is None:
        return None
    value = float(found.group(1))
    return value if 0 < value <= MAX_EFFORT_HOURS else None


def parse_ratio(text: str) -> float | None:
    """担当の割合 `50`・`50%` を 0.01〜1.0 で読む。0・100 超・読めない値は None。"""
    value = parse_percent(text)
    return value / 100 if value else None


def parse_status(text: str) -> Status | None:
    return STATUS_WORDS.get(header_key(text))


def date_only(text: str) -> bool:
    return not re.search(r"\d{1,2}:\d{2}", _plain(text))


def parse_datetime(text: str) -> datetime | None:
    """`2026-10-05`・`2026-10-05 09:30`・`2026/10/5T9:05` を読む。日付だけは 0 時。読めなければ None。"""
    found = _DATETIME.fullmatch(_plain(text))
    if found is None:
        return None
    day = parse_date(found.group(1))
    if day is None:
        return None
    if found.group(2) is None:
        return datetime.combine(day, time(0))
    hour, minute = int(found.group(2)), int(found.group(3))
    if hour >= 24 or minute >= 60:
        return None
    return datetime.combine(day, time(hour, minute))


def cell_ok(field_: CsvField, text: str) -> bool:
    """プレビューで読めない値を示すための検査。空は読める。"""
    if not text.strip():
        return True
    if field_ in (CsvField.START, CsvField.END, CsvField.DEADLINE):
        return parse_date(text) is not None
    if field_ is CsvField.RATIO:
        return all(parse_ratio(part) is not None for part in text.split(";"))
    if field_ is CsvField.PROGRESS:
        return parse_percent(text) is not None
    if field_ is CsvField.EFFORT:
        return parse_effort(text) is not None
    if field_ is CsvField.STATUS:
        return parse_status(text) is not None
    if field_ in (CsvField.ACTUAL_START, CsvField.ACTUAL_END):
        return parse_datetime(text) is not None
    return True


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
    effort: str = ""
    status: str = ""
    actual_start: str = ""
    actual_end: str = ""
    category: str = ""
    ratio: str = ""
    deadline: str = ""

    @property
    def blank_fields(self) -> bool:
        return not (
            self.owner
            or self.start
            or self.end
            or self.progress
            or self.effort
            or self.status
            or self.actual_start
            or self.actual_end
            or self.category
            or self.ratio
            or self.deadline
        )

    @property
    def section_depth(self) -> int | None:
        """WBS 番号の階層(`1` が 1、`1.1` が 2)。番号でなければ None。"""
        return self.wbs.count(".") + 1 if WBS_NUMBER.fullmatch(self.wbs) else None

    @property
    def name(self) -> str:
        return tidy_task_name(
            f"{self.wbs}{WBS_SEPARATOR}{self.title}" if self.wbs else self.title
        )


def detect_delimiter(line: str) -> str:
    """ヘッダー行で最も多い区切り(タブ・カンマ・セミコロン)。同数ならタブ、次にカンマ。"""
    counts = {d: line.count(d) for d in ("\t", ",", ";")}
    return max(counts, key=lambda d: (counts[d], d == "\t", d == ","))


def _find_header(lines: list[str], profile: CsvProfile) -> int | None:
    """プロファイルのタスク名の見出しを含む最初の行(従来どおり、行全体の部分一致)。"""
    wanted = header_key(profile.header_of(CsvField.TITLE))
    if not wanted:
        return None
    return next((i for i, line in enumerate(lines) if wanted in header_key(line)), None)


def _rows(
    text: str,
    profile: CsvProfile,
    delimiter: str | None,
    header_row: int | None,
) -> list[_Row | None]:
    """ヘッダー行を探し、そのあとの行を読む。空行は読み飛ばし、タイトルのない行は None で返す。"""
    lines = text.splitlines()
    header_at = header_row if header_row is not None else _find_header(lines, profile)
    title_header = profile.header_of(CsvField.TITLE) or "タスク名"
    if header_at is None or not 0 <= header_at < len(lines):
        raise CsvImportError(f"「{title_header}」の列が見つかりません")
    sep = delimiter or detect_delimiter(lines[header_at])
    table = csv.reader(io.StringIO("\n".join(lines[header_at:])), delimiter=sep)
    header = next(table)
    columns = resolve_columns(profile, header)
    if CsvField.TITLE not in columns:
        raise CsvImportError(f"「{title_header}」の列が見つかりません")
    rows: list[_Row | None] = []
    for cells in table:
        if not any(cell.strip() for cell in cells):
            continue

        parts: dict[CsvField, str] = {}
        for column in profile.columns:
            if not column.template or column.field not in columns:
                continue
            index = columns[column.field]
            text = cells[index].strip() if index < len(cells) else ""
            split = (split_template(column.template, text) if text else None) or {}
            parts.update({f: split.get(f, "") for f in column.fields})

        def cell(field_: CsvField) -> str:
            if field_ in parts:
                return parts[field_]
            index = columns.get(field_)
            return (
                cells[index].strip() if index is not None and index < len(cells) else ""
            )

        row = _Row(
            _plain(cell(CsvField.WBS)),
            cell(CsvField.TITLE),
            cell(CsvField.OWNER),
            cell(CsvField.START),
            cell(CsvField.END),
            cell(CsvField.PROGRESS),
            cell(CsvField.EFFORT),
            cell(CsvField.STATUS),
            cell(CsvField.ACTUAL_START),
            cell(CsvField.ACTUAL_END),
            cell(CsvField.CATEGORY),
            cell(CsvField.RATIO),
            cell(CsvField.DEADLINE),
        )
        rows.append(row if tidy_task_name(row.title) else None)
    return rows


class _Builder:
    def __init__(
        self,
        name: str,
        holidays: dict[date, str],
        today: date,
        profile: CsvProfile = SMARTSHEET,
    ) -> None:
        self.profile = profile
        self.categories: dict[str, Category] = {}
        self.invalid_values = 0
        self.project = Project(name)
        self.holidays = holidays
        self.today = today
        self.taken: set[str] = set()
        self.stack: list[Section] = []  # 開いているセクション(先頭が 1 階層目)
        self.members: dict[str, Member] = {}
        self.starts: list[date] = []
        self.ends: list[date] = []
        self.sections = self.created_members = self.unresolved = (
            self.invalid_progress
        ) = self.dropped = 0

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
        depth = min(
            row.section_depth or 1, MAX_SECTION_DEPTH, len(self.stack) + 1
        )  # 階層を飛ばした分は詰める
        del self.stack[depth - 1 :]
        section = Section(row.name, id=self.fresh())
        (self.stack[-1].sections if self.stack else self.project.sections).append(
            section
        )
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
        ratios = self.ratios(row.ratio)
        for owner, index in self.owners(row.owner):
            task.assignees.append(Assignee(owner, ratios.get(index, 1.0)))
            self.member(owner)
        self.apply_deadline(task, row)
        self.schedule(task, row)
        self.apply_effort(task, row)
        self.apply_status(task, row)
        self.apply_actuals(task, row)
        self.apply_category(task, row)
        (self.stack[-1].tasks if self.stack else self.project.tasks).append(task)

    def owners(self, text: str) -> list[tuple[str, int]]:
        """(名前, 元の並びの位置)。割合は位置で対応づける。"""
        sep = self.profile.owner_separator
        found: list[tuple[str, int]] = []
        for index, raw in enumerate(text.split(sep) if sep else [text]):
            name = tidy_task_name(raw)
            if name and all(name != n for n, _ in found):
                found.append((name, index))
        return found

    def ratios(self, text: str) -> dict[int, float]:
        """位置ごとの割合。読めない値は数えて、100% のままにする。"""
        sep = self.profile.owner_separator
        found: dict[int, float] = {}
        for index, raw in enumerate(text.split(sep) if sep else [text]):
            if not raw.strip():
                continue
            value = parse_ratio(raw)
            if value is None:
                self.invalid_values += 1
            else:
                found[index] = value
        return found

    def apply_deadline(self, task: Task, row: _Row) -> None:
        if not row.deadline:
            return
        day = parse_date(row.deadline)
        if day is None:
            self.invalid_values += 1
            return
        project = self.project
        task.deadline = datetime.combine(day, project.work_start) + timedelta(
            hours=project.daily_hours
        )

    def apply_effort(self, task: Task, row: _Row) -> None:
        if not row.effort:
            return
        hours = parse_effort(row.effort)
        if hours is None:
            self.invalid_values += 1
            return
        task.effort_hours = hours
        end = parse_date(row.end) if row.end else None
        if end is not None:  # 期限は守る: 完了予定を手で指定する
            task.planned_end_manual = True
            task.planned_end = datetime.combine(
                end, self.project.work_start
            ) + timedelta(hours=self.project.daily_hours)

    def apply_status(self, task: Task, row: _Row) -> None:
        if not row.status:
            return
        status = parse_status(row.status)
        if status is None:
            self.invalid_values += 1
            return
        task.status = status
        if status is Status.DONE:
            task.progress = 100
        elif status is Status.NOT_STARTED:
            task.progress = None

    def apply_actuals(self, task: Task, row: _Row) -> None:
        if not (row.actual_start or row.actual_end):
            return
        start = parse_datetime(row.actual_start) if row.actual_start else None
        end = parse_datetime(row.actual_end) if row.actual_end else None
        bad = (
            bool(row.actual_start and start is None)
            or bool(row.actual_end and end is None)
            or (end is not None and start is None)
            or (start is not None and end is not None and end < start)
        )
        if bad or start is None:
            self.invalid_values += 1
            return
        project = self.project
        if date_only(row.actual_start):
            start = datetime.combine(start.date(), project.work_start)
        if end is not None and date_only(row.actual_end):
            end = datetime.combine(end.date(), project.work_start) + timedelta(
                hours=project.daily_hours
            )
            end = max(end, start)
        if end is not None and end < start:  # 補った時刻で前後が逆になる
            self.invalid_values += 1
            return
        task.actuals = [Actual(start, end)]
        if end is None and task.status in (Status.NOT_STARTED, Status.DONE):
            task.status = Status.RUNNING  # 進行中の区間があるのに未着手・終了は食い違う

    def apply_category(self, task: Task, row: _Row) -> None:
        name = tidy_task_name(row.category)[:MAX_CATEGORY_NAME_LENGTH]
        if not name:
            return
        if name not in self.categories:
            category = Category(name, id=self.fresh())
            self.categories[name] = category
            self.project.categories.append(category)
        task.category_id = self.categories[name].id

    def member(self, name: str) -> None:
        if name not in self.members:
            self.members[name] = Member(name, id=self.fresh())
            self.project.members.append(self.members[name])
            self.created_members += 1

    def schedule(self, task: Task, row: _Row) -> None:
        """開始日・期限から日程を入れる。両方あれば、稼働日数 × 稼働可能時間を工数にして、完了予定は算出に任せる。"""
        start = parse_date(row.start) if row.start else None
        end = parse_date(row.end) if row.end else None
        if (
            (row.start and start is None)
            or (row.end and end is None)
            or (start and end and end < start)
        ):
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
            days = sum(
                is_workday(start + timedelta(days=n), self.holidays)
                for n in range((end - start).days + 1)
            )
            if 0 < days <= MAX_WORKDAYS:
                task.effort_hours = days * project.daily_hours
                if is_workday(end, self.holidays):
                    return  # 完了予定は算出で期限の日の終業時刻になる
                task.planned_end_manual = True  # 期限が休みの日: 算出だと直前の稼働日に縮むので、期限を手で指定する
        task.planned_end = datetime.combine(end, project.work_start) + timedelta(
            hours=project.daily_hours
        )

    def build(self) -> Project:
        dates = self.starts or self.ends
        self.project.base_date = min(dates) if dates else self.today
        return self.project


def parse_csv(
    text: str,
    name: str,
    holidays: dict[date, str],
    today: date | None = None,
    profile: CsvProfile = SMARTSHEET,
    delimiter: str | None = None,
    header_row: int | None = None,
) -> CsvImport:
    """CSV・TSV のテキストから、新規プロジェクトを作る。取り込めなければ `CsvImportError`。
    `holidays` は稼働日数の数え方に使う。`today` は、日付がまったくないときの基準日(省略は今日)。"""
    builder = _Builder(name, holidays, today or clock.today(), profile)
    skipped = 0
    for row in _rows(text, profile, delimiter, header_row):
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
    stamp_creation(project, clock.now())  # 取り込んだタスクの作成を、履歴の最初にする
    return CsvImport(
        project,
        len(project.all_tasks()),
        builder.sections,
        builder.created_members,
        skipped,
        builder.unresolved,
        builder.invalid_progress,
        builder.dropped,
        builder.invalid_values,
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
        f"読めない進捗率 {result.invalid_progress} 件"
        if result.invalid_progress
        else "",
        f"セクションの行の値を取り込まなかった行 {result.dropped_values} 行"
        if result.dropped_values
        else "",
        f"読めない値 {result.invalid_values} 件" if result.invalid_values else "",
    ]
    detail = "、".join(note for note in notes if note)
    return f"取り込みました({head})" + (f"。{detail}" if detail else "")


def decode_table(data: bytes, encoding: str | None = None) -> tuple[str, str]:
    """(テキスト, 文字コード)。`encoding`が None なら UTF-8(BOM 可)を先に試し、読めなければ Shift_JIS。"""
    for name in (encoding,) if encoding else ("utf-8-sig", "cp932"):
        try:
            return data.decode(name), name
        except UnicodeDecodeError:
            continue
    raise CsvImportError(
        "文字コードを判定できません(UTF-8 か Shift_JIS にしてください)"
    )


def read_table(path: Path) -> str:
    """テキストを読む。UTF-8(BOM は除く)を先に試し、読めなければ Shift_JIS。読めなければ `CsvImportError`。"""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CsvImportError(f"ファイルを読めません: {exc}") from exc
    return decode_table(data)[0]


PREVIEW_ROWS = 5


@dataclass(frozen=True)
class TableSniff:
    text: str
    encoding: str
    delimiter: str
    header_row: int
    header: list[str]
    rows: list[list[str]]  # ヘッダーの次からの、空でない先頭 5 行


def sniff_table(
    data: bytes,
    encoding: str | None = None,
    delimiter: str | None = None,
    header_row: int | None = None,
) -> TableSniff:
    """文字コード・区切り・ヘッダー行を判定し、見出しと先頭の数行を返す(取り込みのダイアログ用)。"""
    text, used = decode_table(data, encoding)
    lines = text.splitlines()
    if header_row is None:
        titles = ALIASES[CsvField.TITLE]
        header_row = next(
            (
                i
                for i, line in enumerate(lines)
                if any(header_key(c) in titles for c in re.split(r"[\t,;]", line))
            ),
            next((i for i, line in enumerate(lines) if line.strip()), 0),
        )
    if not lines or not 0 <= header_row < len(lines):
        raise CsvImportError("取り込める行がありません")
    sep = delimiter or detect_delimiter(lines[header_row])
    table = csv.reader(io.StringIO("\n".join(lines[header_row:])), delimiter=sep)
    header = [c.strip() for c in next(table, [])]
    rows = [r for r in table if any(c.strip() for c in r)][:PREVIEW_ROWS]
    return TableSniff(text, used, sep, header_row, header, rows)
