"""プロジェクトのデータモデル。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
import re
import secrets
from enum import StrEnum

DEFAULT_DAILY_HOURS = 6.5
DEFAULT_WORK_START = time(9, 0)
DEFAULT_COLOR = "#4c8bf5"
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ
MIN_RATIO, MAX_RATIO = 0.1, 3.0  # 相対比率(10%〜300%)
MIN_ALLOCATION, MAX_ALLOCATION = 0.01, 1.0  # 割り当て率(1%〜100%)
MIN_PROGRESS, MAX_PROGRESS = 0, 100  # 実績の進捗度(%)
MAX_PROJECT_CODE_LENGTH = 20  # ProjectCode の最大文字数
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")


def new_id() -> str:
    """タスクの id。8 桁の 16 進(プロジェクト内で重複しないことは、保存と読込が確かめる)。"""
    return secrets.token_hex(4)


def is_hex_color(value: str) -> bool:
    """#RGB / #RRGGBB / #RRGGBBAA。CSSにそのまま入れても安全な形式だけを通す。"""
    return HEX_COLOR.fullmatch(value) is not None


class Priority(StrEnum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class Status(StrEnum):
    NOT_STARTED = "未着手"
    RUNNING = "実行中"
    PAUSED = "一時停止"
    DONE = "終了"


class TaskKind(StrEnum):
    NORMAL = "通常"
    CHECKPOINT = "チェックポイント"  # 締切だけを持つ節目。バーを持たず、◆ だけを出す


CHECKPOINT_STATUSES = (Status.NOT_STARTED, Status.DONE)  # チェックポイントが取れる状態


class ActualMode(StrEnum):
    SIMPLE = "simple"  # 簡易: 実績は 1 区間
    INTERVALS = "intervals"  # 区間: 実績を複数の区間で入力する


@dataclass
class Member:
    name: str
    ratio: float = 1.0  # 基準倍率(1.0 = 100%)


@dataclass
class Actual:
    """実績の1区間。endがNoneのときは進行中。"""

    start: datetime
    end: datetime | None = None
    progress: int | None = None  # 区間の終わり時点の累積(0〜100%)。Noneは未入力


URL_KEY = "URL"  # テンプレートなしのリンクの値のキー
ID_KEY = "ID"  # テンプレートありのリンクの値のキー(型の `{ID}` を置き換える)


@dataclass
class UrlTemplate:
    name: str
    pattern: str  # URL の型。`{ID}` を、リンクの ID で置き換える


@dataclass
class TaskUrl:
    title: str = ""  # 表示名(任意)
    template: str | None = None  # テンプレート名。None はテンプレートなし
    values: dict[str, str] = field(default_factory=dict)  # {"ID": …} か {"URL": …}


@dataclass
class Task:
    name: str
    id: str = field(default_factory=new_id, compare=False)  # 連結の参照用。ファイルに保存する
    planned_start: datetime | None = None
    effort_hours: float = 0.0
    priority: Priority = Priority.MEDIUM
    status: Status = Status.NOT_STARTED
    color: str = DEFAULT_COLOR
    assignee: str | None = None
    predecessors: list[str] = field(default_factory=list)
    deadline: datetime | None = None  # 締切(納期)
    planned_end: datetime | None = None  # 完了予定の手入力値
    planned_end_manual: bool = False  # 工数があるときに、完了予定を手で指定するか
    allocation: float = 1.0  # 担当者の時間のうち、このタスクに使う割合(1.0 = 100%)
    actuals: list[Actual] = field(default_factory=list)  # 実績の区間(今回の画面は0〜1件)
    project_code: str = ""  # ProjectCode。前後の空白は除く。最大 MAX_PROJECT_CODE_LENGTH 文字
    kind: TaskKind = TaskKind.NORMAL  # チェックポイントは、締切だけを持つ(他の日時・工数・担当・実績は持たない)
    urls: list[TaskUrl] = field(default_factory=list)  # 関連する URL(チケット・資料など)


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
    actual_mode: ActualMode = ActualMode.SIMPLE  # 実績の記録方式
    url_templates: list[UrlTemplate] = field(default_factory=list)  # リンクの URL の型(プロジェクト共通)

    def all_tasks(self) -> list[Task]:
        """セクションなしのタスク、続いてセクションのタスク。"""
        return [*self.tasks, *(t for section in self.sections for t in section.tasks)]
