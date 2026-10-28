"""稼働日の上書きの規則(検証・並べ替え・辞書化)。NiceGUI に依存しない。"""

from collections.abc import Iterable
from datetime import date

from projectapp.models import MAX_YEAR, MIN_YEAR, WorkDay, has_control_char

MAX_NOTE = 30  # メモの最大文字数
MAX_RANGE_DAYS = 366  # 期間で一括追加できる日数


def validate_note(note: str) -> None:
    """メモは 30 文字以内で、改行・制御文字・ゼロ幅文字を含まない。不正は ValueError。"""
    if len(note) > MAX_NOTE:
        raise ValueError(f"稼働日のメモは{MAX_NOTE}文字以内で入力してください")
    if has_control_char(note):
        raise ValueError("稼働日のメモに改行・制御文字は使えません")


def validate_work_days(days: list[WorkDay]) -> None:
    """日付が重複しない・年が範囲内・休みか(開始 < 終了)のどちらか。不正は ValueError。"""
    seen: set[date] = set()
    for row in days:
        if not MIN_YEAR <= row.day.year <= MAX_YEAR:
            raise ValueError(f"稼働日の日付は {MIN_YEAR}〜{MAX_YEAR} 年にしてください: {row.day.isoformat()}")
        if row.day in seen:
            raise ValueError(f"稼働日の日付が重複しています: {row.day.isoformat()}")
        seen.add(row.day)
        validate_note(row.note)
        if (row.start is None) != (row.end is None):
            raise ValueError(f"稼働日の開始と終了は、両方入れるか休みにしてください: {row.day.isoformat()}")
        if row.start is not None and row.end is not None and row.start >= row.end:
            raise ValueError(f"稼働日の終了は開始より後にしてください: {row.day.isoformat()}")


def sort_work_days(days: list[WorkDay]) -> list[WorkDay]:
    return sorted(days, key=lambda row: row.day)


def work_day_map(days: Iterable[WorkDay]) -> dict[date, WorkDay]:
    """日付 → 上書き。"""
    return {row.day: row for row in days}
