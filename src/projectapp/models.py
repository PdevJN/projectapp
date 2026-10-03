"""プロジェクトのデータモデル。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
import re
from enum import StrEnum

DEFAULT_DAILY_HOURS = 6.5
DEFAULT_WORK_START = time(9, 0)
DEFAULT_COLOR = "#4c8bf5"
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")


def is_hex_color(value: str) -> bool:
    """#RGB / #RRGGBB / #RRGGBBAA。CSSにそのまま入れても安全な形式だけを通す。"""
    return HEX_COLOR.fullmatch(value) is not None


class Priority(StrEnum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class Status(StrEnum):
    STARTED = "開始"
    RUNNING = "実行中"
    PAUSED = "一時停止"
    DONE = "終了"


@dataclass
class Member:
    name: str
    ratio: float = 1.0  # 基準倍率(1.0 = 100%)


@dataclass
class Task:
    name: str
    planned_start: datetime | None = None
    end: datetime | None = None
    effort_hours: float = 0.0
    priority: Priority = Priority.MEDIUM
    status: Status = Status.STARTED
    color: str = DEFAULT_COLOR
    assignee: str | None = None
    predecessors: list[str] = field(default_factory=list)
    end_auto: bool = False  # 終了が自動算出で、利用者が書き換えていない
    deadline: datetime | None = None  # 締切(納期)


@dataclass
class Section:
    name: str
    tasks: list[Task] = field(default_factory=list)


@dataclass
class Project:
    name: str
    base_date: date = field(default_factory=date.today)
    daily_hours: float = DEFAULT_DAILY_HOURS
    work_start: time = DEFAULT_WORK_START  # 稼働日の始業時刻
    members: list[Member] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)  # セクションに属さないタスク
