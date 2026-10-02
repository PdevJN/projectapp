"""プロジェクトのデータモデル。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

DEFAULT_DAILY_HOURS = 6.5


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
    start: datetime | None = None
    end: datetime | None = None
    effort_hours: float = 0.0
    priority: Priority = Priority.MEDIUM
    status: Status = Status.STARTED
    color: str = "#4c8bf5"
    assignee: str | None = None
    predecessors: list[str] = field(default_factory=list)


@dataclass
class Section:
    name: str
    tasks: list[Task] = field(default_factory=list)


@dataclass
class Project:
    name: str
    base_date: date = field(default_factory=date.today)
    daily_hours: float = DEFAULT_DAILY_HOURS
    members: list[Member] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
