"""祝日データの取得・キャッシュと日付種別の判定。"""

import csv
import io
import json
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from pathlib import Path

import httpx

from projectapp.models import Project, Task, WorkDay
from projectapp.storage import BASE_DIR

HOLIDAYS_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
CACHE_NAME = "holidays.json"
TIMEOUT_SECONDS = 10.0


class DayKind(StrEnum):
    WEEKDAY = "平日"
    SATURDAY = "土曜"
    SUNDAY = "日曜"
    HOLIDAY = "祝日"


def parse_holidays_csv(raw: bytes) -> dict[date, str]:
    """内閣府CSV(cp932)を解析する。読み取れた行がなければValueError。"""
    rows = csv.reader(io.StringIO(raw.decode("cp932")))
    next(rows, None)  # ヘッダー行
    holidays: dict[date, str] = {}
    for row in rows:
        try:
            year, month, day = (int(v) for v in row[0].split("/"))
            holidays[date(year, month, day)] = row[1].strip()
        except (ValueError, IndexError):
            continue
    if not holidays:
        raise ValueError("祝日データを解析できません")
    return holidays


def day_kind(day: date, holidays: dict[date, str]) -> DayKind:
    if day in holidays:
        return DayKind.HOLIDAY
    if day.weekday() == 5:
        return DayKind.SATURDAY
    if day.weekday() == 6:
        return DayKind.SUNDAY
    return DayKind.WEEKDAY


def work_day_note(
    day: date,
    holidays: dict[date, str],
    work_days: Mapping[date, WorkDay] | None = None,
) -> str | None:
    """日付ヘッダーのマウスオーバー。上書きがあるときだけ(`稼働 13:00〜16:00`・`休み`。メモと祝日の名前を添える)。"""
    if not work_days or day not in work_days:
        return None
    row = work_days[day]
    text = (
        "休み"
        if row.start is None or row.end is None
        else f"稼働 {row.start:%H:%M}〜{row.end:%H:%M}"
    )
    details = ([row.note] if row.note else []) + (
        [f"祝日: {holidays[day]}"] if day in holidays else []
    )
    return f"{text}({'。'.join(details)})" if details else text


def member_notes(
    task: Task, project: Project, holidays: dict[date, str]
) -> dict[date, str]:
    """担当者が上書きした日 → 説明(`田中: 稼働 13:00〜16:00`)。複数なら ` / ` で結ぶ。メンバーでない担当者は数えない。"""
    by_name = {m.name: m for m in project.members}
    notes: dict[date, list[str]] = {}
    for assignee in task.assignees:
        member = by_name.get(assignee.name)
        if member is None:
            continue
        days = {row.day: row for row in member.work_days}
        for day in days:
            text = work_day_note(day, holidays, days)
            if text:
                notes.setdefault(day, []).append(f"{member.name}: {text}")
    return {day: " / ".join(lines) for day, lines in notes.items()}


def load_cache(base_dir: Path = BASE_DIR) -> dict[date, str] | None:
    """キャッシュを読む。ファイルがない・壊れている場合はNone。"""
    try:
        raw = json.loads((base_dir / CACHE_NAME).read_text(encoding="utf-8"))
        return {date.fromisoformat(key): str(name) for key, name in raw.items()}
    except (OSError, ValueError, AttributeError):
        return None


def save_cache(holidays: dict[date, str], base_dir: Path = BASE_DIR) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    data = {day.isoformat(): name for day, name in holidays.items()}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    (base_dir / CACHE_NAME).write_text(text, encoding="utf-8")


async def refresh_holidays(
    base_dir: Path = BASE_DIR,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[date, str]:
    """祝日を取得してキャッシュに保存する。失敗時は何も保存せず例外を送出する。"""
    async with httpx.AsyncClient(
        transport=transport, timeout=TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        response = await client.get(HOLIDAYS_URL)
    response.raise_for_status()
    holidays = parse_holidays_csv(response.content)
    save_cache(holidays, base_dir)
    return holidays
