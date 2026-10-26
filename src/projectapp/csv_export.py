"""プロジェクトを、Smartsheet のガントチャートのテンプレートの形の TSV(タブ区切り)に書き出す。NiceGUI には依存しない。"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from projectapp.csv_import import WBS_NUMBER, WBS_SEPARATOR
from projectapp.export import UNSAFE_NAME_CHARS
from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.plantuml import write_text
from projectapp.timeline import Schedule, effective_end, effective_start

TSV_FILE_TYPES = ("TSV ファイル (*.tsv)",)
HEADER = ("WBS 番号", "タスクのタイトル", "タスクオーナー", "開始日", "期限", "期間", "タスク完了率")
EXTENSION = ".tsv"


@dataclass(frozen=True)
class TsvExport:
    text: str
    task_count: int
    section_count: int
    skipped: int  # 書き出さなかったタスク(まとめ・チェックポイント・プロジェクト参照)の数
    multiple_owners: int  # 担当者が複数で、筆頭だけを書いたタスクの数


def format_date(day: date) -> str:
    """`26年 10月 5日` の形。2 桁にできない年(2100 年)は 4 桁。"""
    year = f"{day.year % 100:02d}" if day.year < 2100 else str(day.year)
    return f"{year}年 {day.month}月 {day.day}日"


def split_name(name: str) -> tuple[str, str]:
    """名前を最初の `#` で WBS 番号とタイトルに分ける。前が番号(数字と `.`)でなければ、分けずに全体をタイトルにする。"""
    front, separator, back = name.partition(WBS_SEPARATOR)
    if separator and WBS_NUMBER.fullmatch(front):
        return front, back
    return "", name


def _last_day(end: datetime) -> date:
    return end.date() - timedelta(days=1) if end.time() == time(0) else end.date()  # 0 時ちょうどは前日の終わり


def build_tsv(project: Project, holidays: dict[date, str]) -> TsvExport:
    """通常タスクとセクションを、`Project.all_tasks` と同じ順(セクションなしが先、続いてセクションを深さ優先)で書く。"""
    schedule = Schedule(project, holidays)
    out = io.StringIO()
    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
    writer.writerow(HEADER)
    counts = {"tasks": 0, "sections": 0, "skipped": 0, "multiple": 0}

    def task_row(task: Task) -> None:
        if task.kind is not TaskKind.NORMAL:
            counts["skipped"] += 1
            return
        wbs, title = split_name(task.name)
        start = effective_start(task, project, holidays, schedule)
        end = effective_end(task, project, holidays, schedule)
        first, last = (start.date() if start else None), (_last_day(end) if end else None)
        progress = task.progress if task.progress is not None else (100 if task.status is Status.DONE else 0)
        counts["tasks"] += 1
        counts["multiple"] += len(task.assignees) > 1
        writer.writerow(
            (
                wbs,
                title,
                task.assignees[0].name if task.assignees else "",
                format_date(first) if first else "",
                format_date(last) if last else "",
                (last - first).days if first and last else "",
                f"{progress}%",
            )
        )

    def section_rows(section: Section) -> None:
        counts["sections"] += 1
        wbs, title = split_name(section.name)
        writer.writerow((wbs, title, "", "", "", "", ""))
        for task in section.tasks:
            task_row(task)
        for child in section.sections:
            section_rows(child)

    for task in project.tasks:
        task_row(task)
    for section in project.sections:
        section_rows(section)
    return TsvExport(out.getvalue(), counts["tasks"], counts["sections"], counts["skipped"], counts["multiple"])


def default_filename(project_name: str) -> str:
    """既定のファイル名 `<名前>.tsv`。ファイル名に使えない文字は `_` にする。"""
    name = UNSAFE_NAME_CHARS.sub("_", project_name.strip()).lstrip(".")
    return f"{name or 'gantt'}{EXTENSION}"


def write_tsv(path: Path, text: str) -> Path:
    """UTF-8(BOM なし)で書く。拡張子がなければ .tsv を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    return write_text(path if path.suffix else path.with_name(path.name + EXTENSION), text)
