"""プロジェクトを、プロファイルで決めた列・区切り・文字コードの CSV・TSV に書き出す(組み込みの Smartsheet はテンプレートの形)。NiceGUI には依存しない。"""

import csv
import io
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from projectapp.csv_import import WBS_NUMBER, WBS_SEPARATOR
from projectapp.models import Project, ReferenceValue, Section, Status, Task, TaskKind
from projectapp.csv_profile import SMARTSHEET, CsvField, CsvProfile
from projectapp.plantuml import write_text
from projectapp.timeline import Schedule, effective_end, effective_start

TSV_FILE_TYPES = ("TSV ファイル (*.tsv)",)
CSV_SAVE_FILE_TYPES = ("CSV TSV ファイル (*.csv;*.tsv)",)
HEADER = tuple(c.header for c in SMARTSHEET.columns)
EXTENSION = ".tsv"
DEFAULT_FILENAME = "out.tsv"  # 保存ダイアログの既定のファイル名
BLANK_ROWS = (
    SMARTSHEET.blank_rows
)  # 見出しの次の空行(テンプレートのサンプルと同じ。タブだけの行)
REFERENCE_PREFIX = "(参照) "  # 参照行のタイトルの頭。取り込みは通常タスクとして読む(往復で参照行には戻らない)


@dataclass(frozen=True)
class TableExport:
    text: str
    task_count: int
    section_count: int
    skipped: int  # 書き出さなかったタスク(まとめ・チェックポイント)の数
    multiple_owners: int  # 担当者が複数で、筆頭だけを書いたタスクの数
    references: int = 0  # 書いたプロジェクト参照の行の数
    unresolved: int = 0  # うち、参照先の値がなく、日付と進捗率を空にした行の数


TsvExport = TableExport  # 従来の名前


def format_date(day: date, style: str = "ja") -> str:
    """`ja`は`26年 10月 5日`(2 桁にできない年〔2100 年〕は 4 桁)、`ymd-dash`は`2026-10-05`、`ymd-slash`は`2026/10/05`。"""
    if style == "ymd-dash":
        return f"{day.year:04d}-{day.month:02d}-{day.day:02d}"
    if style == "ymd-slash":
        return f"{day.year:04d}/{day.month:02d}/{day.day:02d}"
    year = f"{day.year % 100:02d}" if day.year < 2100 else str(day.year)
    return f"{year}年 {day.month}月 {day.day}日"


def format_datetime(moment: datetime, style: str = "ymd-dash") -> str:
    """日付の書式のあとに` HH:MM`を付ける。"""
    return f"{format_date(moment.date(), style)} {moment:%H:%M}"


def split_name(name: str) -> tuple[str, str]:
    """名前を最初の `#` で WBS 番号とタイトルに分ける。前が番号(数字と `.`)でなければ、分けずに全体をタイトルにする。"""
    front, separator, back = name.partition(WBS_SEPARATOR)
    if separator and WBS_NUMBER.fullmatch(front):
        return front, back
    return "", name


def _last_day(end: datetime) -> date:
    return (
        end.date() - timedelta(days=1) if end.time() == time(0) else end.date()
    )  # 0 時ちょうどは前日の終わり


def build_table(
    project: Project,
    holidays: dict[date, str],
    profile: CsvProfile,
    references: Mapping[str, ReferenceValue] | None = None,
) -> TableExport:
    """通常タスクとプロジェクト参照とセクションを、`Project.all_tasks` と同じ順(セクションなしが先、続いてセクションを深さ優先)で書く。
    列・区切り・日付の書式・担当の区切りは`profile`が決める。references は参照行(タスクの id)ごとの参照先の値。なければ日付と進捗率を空にする。"""
    schedule = Schedule(project, holidays)
    style = profile.date_format
    category_names = {c.id: c.name for c in project.categories}
    out = io.StringIO()
    writer = csv.writer(out, delimiter=profile.delimiter, lineterminator="\n")
    columns = [c.field for c in profile.columns]
    writer.writerow([c.header for c in profile.columns])
    for _ in range(profile.blank_rows):
        writer.writerow([""] * len(columns))
    counts = {
        "tasks": 0,
        "sections": 0,
        "skipped": 0,
        "multiple": 0,
        "references": 0,
        "unresolved": 0,
    }

    def write(values: dict[CsvField, str]) -> None:
        writer.writerow([values.get(field, "") for field in columns])

    sign = "%" if profile.progress_percent else ""

    def reference_row(task: Task) -> None:
        value = (references or {}).get(task.id)
        counts["references"] += 1
        start = value.planned_start if value is not None else None
        end = value.planned_end if value is not None else None
        first, last = (
            (start.date() if start else None),
            (_last_day(end) if end else None),
        )
        if value is None:
            counts["unresolved"] += 1
            percent = ""
        else:
            percent = (
                f"{value.progress if value.progress is not None else (100 if value.finished else 0)}"
                + sign
            )
        write(
            {
                CsvField.TITLE: REFERENCE_PREFIX + task.name,
                CsvField.START: format_date(first, style) if first else "",
                CsvField.END: format_date(last, style) if last else "",
                CsvField.DURATION: str((last - first).days if first and last else 0),
                CsvField.PROGRESS: percent,
            }
        )

    def task_row(task: Task) -> None:
        if task.kind is TaskKind.REFERENCE:
            reference_row(task)
            return
        if task.kind is not TaskKind.NORMAL:
            counts["skipped"] += 1
            return
        wbs, title = split_name(task.name)
        start = effective_start(task, project, holidays, schedule)
        end = effective_end(task, project, holidays, schedule)
        first, last = (
            (start.date() if start else None),
            (_last_day(end) if end else None),
        )
        progress = (
            task.progress
            if task.progress is not None
            else (100 if task.status is Status.DONE else 0)
        )
        counts["tasks"] += 1
        names = task.assignee_names
        if profile.owner_separator:
            owner = profile.owner_separator.join(names)
        else:
            owner = names[0] if names else ""
            counts["multiple"] += len(names) > 1
        shares = [f"{max(1, round(a.allocation * 100))}%" for a in task.assignees]
        ratio = (
            profile.owner_separator.join(shares)
            if profile.owner_separator
            else (shares[0] if shares else "")
        )
        write(
            {
                CsvField.WBS: wbs,
                CsvField.TITLE: title,
                CsvField.OWNER: owner,
                CsvField.RATIO: ratio,
                CsvField.DEADLINE: format_date(task.deadline.date(), style)
                if task.deadline
                else "",
                CsvField.START: format_date(first, style) if first else "",
                CsvField.END: format_date(last, style) if last else "",
                # 日付がない行は 0(テンプレートと同じ)
                CsvField.DURATION: str((last - first).days if first and last else 0),
                CsvField.PROGRESS: f"{progress}{sign}",
                CsvField.EFFORT: f"{task.total_effort:g}" if task.total_effort else "",
                CsvField.STATUS: task.status.value,
                CsvField.ACTUAL_START: format_datetime(task.actuals[0].start, style)
                if task.actuals
                else "",
                CsvField.ACTUAL_END: format_datetime(task.actuals[-1].end, style)
                if task.actuals and task.actuals[-1].end is not None
                else "",
                CsvField.CATEGORY: category_names.get(task.category_id or "", ""),
            }
        )

    def section_rows(section: Section) -> None:
        counts["sections"] += 1
        wbs, title = split_name(section.name)
        write({CsvField.WBS: wbs, CsvField.TITLE: title})
        for task in section.tasks:
            task_row(task)
        for child in section.sections:
            section_rows(child)

    for task in project.tasks:
        task_row(task)
    for section in project.sections:
        section_rows(section)
    return TableExport(
        out.getvalue(),
        counts["tasks"],
        counts["sections"],
        counts["skipped"],
        counts["multiple"],
        counts["references"],
        counts["unresolved"],
    )


def build_tsv(
    project: Project,
    holidays: dict[date, str],
    references: Mapping[str, ReferenceValue] | None = None,
) -> TableExport:
    """Smartsheet のテンプレートの形(従来の TSV)。"""
    return build_table(project, holidays, SMARTSHEET, references)


def encode_table(text: str, encoding: str) -> bytes:
    """指定の文字コードにする。Shift_JIS にできない文字があれば、黙って置き換えず `ValueError`。"""
    if encoding == "utf-8":
        return text.encode("utf-8")
    if encoding == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    try:
        return text.encode("cp932")
    except UnicodeEncodeError:
        bad: list[str] = []
        for ch in text:
            try:
                ch.encode("cp932")
            except UnicodeEncodeError:
                if ch not in bad:
                    bad.append(ch)
        raise ValueError(
            f"Shift_JIS にできない文字があります: {''.join(bad[:5])}"
        ) from None


def default_filename(delimiter: str) -> str:
    return "out.tsv" if delimiter == "\t" else "out.csv"


def write_table(path: Path, data: bytes, delimiter: str) -> Path:
    """バイト列を書く。拡張子がなければ、タブは .tsv、それ以外は .csv を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    if not path.suffix:
        path = path.with_name(path.name + (".tsv" if delimiter == "\t" else ".csv"))
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".table-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def write_tsv(path: Path, text: str) -> Path:
    """UTF-8(BOM なし)で書く。拡張子がなければ .tsv を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    return write_text(
        path if path.suffix else path.with_name(path.name + EXTENSION), text
    )
