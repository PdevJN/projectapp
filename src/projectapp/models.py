"""プロジェクトのデータモデル。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
import re
from enum import StrEnum

DEFAULT_DAILY_HOURS = 6.5
DEFAULT_WORK_START = time(9, 0)
DEFAULT_COLOR = "#4c8bf5"
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ
MIN_RATIO, MAX_RATIO = 0.1, 3.0  # 相対比率(10%〜300%)
MIN_ALLOCATION, MAX_ALLOCATION = 0.01, 1.0  # 割り当て率(1%〜100%)
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
class Actual:
    """実績の1区間。endがNoneのときは進行中。"""

    start: datetime
    end: datetime | None = None


@dataclass
class Task:
    name: str
    planned_start: datetime | None = None
    effort_hours: float = 0.0
    priority: Priority = Priority.MEDIUM
    status: Status = Status.STARTED
    color: str = DEFAULT_COLOR
    assignee: str | None = None
    predecessors: list[str] = field(default_factory=list)
    deadline: datetime | None = None  # 締切(納期)
    planned_end: datetime | None = None  # 完了予定の手入力値
    planned_end_manual: bool = False  # 工数があるときに、完了予定を手で指定するか
    allocation: float = 1.0  # 担当者の時間のうち、このタスクに使う割合(1.0 = 100%)
    actuals: list[Actual] = field(default_factory=list)  # 実績の区間(今回の画面は0〜1件)


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

    def all_tasks(self) -> list[Task]:
        """セクションなしのタスク、続いてセクションのタスク。"""
        return [*self.tasks, *(t for section in self.sections for t in section.tasks)]
