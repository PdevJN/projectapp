"""プロジェクトのデータモデル。"""

from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time
import re
import secrets
from enum import StrEnum

FORMAT_VERSION = 2  # プロジェクトファイルの形式のバージョン。キーのない古いファイルは 1 として読む(2: メンバーとセクションの id、担当者はメンバー id で指す)
DEFAULT_DAILY_HOURS = 6.5
DEFAULT_WORK_START = time(9, 0)
DEFAULT_COLOR = "#4c8bf5"
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ
MIN_RATIO, MAX_RATIO = 0.1, 3.0  # 相対比率(10%〜300%)
MAX_SECTION_DEPTH = 3  # セクションの入れ子の上限(root 直下が 1 階層目。root は数えない)
SectionPath = tuple[int, ...]  # セクションの位置。root は ()、1 番目のセクションは (0,)、その 2 番目のサブセクションは (0, 1)
MIN_LEVEL_VALUE, MAX_LEVEL_VALUE = -0.9, 2.9  # パラメータの段階の判定値(-90%〜+290%)
MIN_ALLOCATION, MAX_ALLOCATION = 0.01, 1.0  # 割り当て率(1%〜100%)
MIN_PROGRESS, MAX_PROGRESS = 0, 100  # 実績の進捗度(%)
MAX_PROJECT_CODE_LENGTH = 20  # ProjectCode の最大文字数
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")


def new_id(taken: Collection[str] = ()) -> str:
    """id。8 桁の 16 進。`taken` にある id は返さない(プロジェクト内で重複しないように、振る側が既存の id を渡す)。"""
    while True:
        candidate = secrets.token_hex(4)
        if candidate not in taken:
            return candidate


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
    ratio: float = 1.0  # 基本比率(1.0 = 100%)。相対比率 = 基本比率 + 選んだ段階の判定値の合計
    levels: dict[str, str] = field(default_factory=dict)  # パラメータ名 → 選んだ段階名
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する(担当者はこの id で指す)


@dataclass
class Level:
    name: str
    value: float  # 判定値。割合(+0.2 = +20%)


@dataclass
class Parameter:
    name: str
    levels: list[Level] = field(default_factory=list)


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
class Assignee:
    name: str
    allocation: float = 1.0  # 担当者の時間のうち、このタスクに使う割合(1.0 = 100%)


@dataclass
class Task:
    name: str
    id: str = field(default_factory=new_id, compare=False)  # 連結の参照用。ファイルに保存する
    planned_start: datetime | None = None
    effort_hours: float = 0.0
    priority: Priority = Priority.MEDIUM
    status: Status = Status.NOT_STARTED
    color: str = DEFAULT_COLOR
    assignees: list[Assignee] = field(default_factory=list)  # 担当者(先頭が筆頭)。空は担当なし
    predecessors: list[str] = field(default_factory=list)
    deadline: datetime | None = None  # 締切(納期)
    planned_end: datetime | None = None  # 完了予定の手入力値
    planned_end_manual: bool = False  # 工数があるときに、完了予定を手で指定するか
    actuals: list[Actual] = field(default_factory=list)  # 実績の区間(今回の画面は0〜1件)
    project_code: str = ""  # ProjectCode。前後の空白は除く。最大 MAX_PROJECT_CODE_LENGTH 文字
    kind: TaskKind = TaskKind.NORMAL  # チェックポイントは、締切だけを持つ(他の日時・工数・担当・実績は持たない)
    urls: list[TaskUrl] = field(default_factory=list)  # 関連する URL(チケット・資料など)

    @property
    def assignee_names(self) -> list[str]:
        return [a.name for a in self.assignees]


@dataclass
class Section:
    name: str
    tasks: list[Task] = field(default_factory=list)
    sections: list["Section"] = field(default_factory=list)  # サブセクション(タスクの後ろに並ぶ)
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する

    def all_tasks(self) -> list[Task]:
        """このセクションのタスク、続いてサブセクションのタスク(深さ優先)。"""
        tasks = list(self.tasks)
        for child in self.sections:
            tasks += child.all_tasks()
        return tasks


def walk_sections(sections: list[Section], prefix: SectionPath = ()) -> Iterator[tuple[SectionPath, Section]]:
    """セクションを深さ優先でたどる(親 → その子孫 → 次の兄弟)。パスは root からの番号の並び。"""
    for index, section in enumerate(sections):
        path = (*prefix, index)
        yield path, section
        yield from walk_sections(section.sections, path)


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
    parameters: list[Parameter] = field(default_factory=list)  # 相対比率のパラメータ(プロジェクト共通)

    def all_tasks(self) -> list[Task]:
        """セクションなしのタスク、続いて各セクションを深さ優先で(そのタスク → そのサブセクション)。"""
        tasks = list(self.tasks)
        for section in self.sections:
            tasks += section.all_tasks()
        return tasks

    def used_ids(self) -> set[str]:
        """タスク・メンバー・セクションの id。新しい id が既存と重ならないように、振る側が渡す。"""
        return (
            {t.id for t in self.all_tasks()}
            | {m.id for m in self.members}
            | {s.id for _, s in walk_sections(self.sections)}
        )
