"""日付と時刻の入力の整形(省略形の読み取りと、ショートカットの日付)。NiceGUI に依存しない。"""

import re
from datetime import date, timedelta

DATE_FORMAT = "%Y-%m-%d"
SHORTCUT_LABELS = {"today": "今日", "tomorrow": "明日", "next-monday": "来週月"}


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_day(today: date, month: int, day: int, roll_forward: bool) -> date | None:
    """年を省いた日付。年は今年で、その日が過ぎていて roll_forward なら、翌年にする。"""
    found = _make(today.year, month, day)
    if found is not None and roll_forward and found < today:
        return _make(today.year + 1, month, day)
    return found


def parse_date_input(text: str, today: date, roll_forward: bool) -> str | None:
    """日付の省略形を `YYYY-MM-DD` にする。読めないとき、存在しない日付のときは None。"""
    value = text.strip()
    found: date | None
    if m := re.fullmatch(r"([0-9]{4})[-/]([0-9]{1,2})[-/]([0-9]{1,2})", value):
        found = _make(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.fullmatch(r"([0-9]{4})([0-9]{2})([0-9]{2})", value):
        found = _make(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})", value):
        found = _month_day(today, int(m[1]), int(m[2]), roll_forward)
    elif m := re.fullmatch(r"([0-9]{2})([0-9]{2})", value):
        found = _month_day(today, int(m[1]), int(m[2]), roll_forward)
    else:
        return None
    return found.strftime(DATE_FORMAT) if found else None


def shortcut_dates(today: date) -> dict[str, date]:
    """ショートカットの日付。来週月は、今日が属する週(月曜始まり)の次の週の月曜。"""
    return {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "next-monday": today + timedelta(days=7 - today.weekday()),
    }


def parse_time_input(text: str) -> str | None:
    """時刻の省略形(`9`・`930`・`0930`・`9:30`)を `HH:MM` にする。読めないとき、範囲外のときは None。"""
    value = text.strip()
    if m := re.fullmatch(r"([0-9]{1,2}):([0-9]{2})", value):
        hour, minute = int(m[1]), int(m[2])
    elif m := re.fullmatch(r"[0-9]{1,2}", value):
        hour, minute = int(value), 0
    elif m := re.fullmatch(r"([0-9]{1,2})([0-9]{2})", value):
        hour, minute = int(m[1]), int(m[2])
    else:
        return None
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"
