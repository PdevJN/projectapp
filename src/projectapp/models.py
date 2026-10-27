"""プロジェクトのデータモデル。"""

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
import re
import secrets
import unicodedata
from enum import StrEnum

FORMAT_VERSION = 13  # プロジェクトファイルの形式のバージョン。キーのない古いファイルは 1 として読む(2: メンバーとセクションの id、担当者はメンバー id で指す。3: カテゴリ、タスクは category_id で指す。4: イベント。5: タスクの進捗度。6: まとめ〔種別と子の id〕。7: メンバーのアイコン。8: 稼働日の上書き。9: タスクのパラメータ。10: タスクの週ごとの担当〔weekly_crew〕。11: プロジェクト参照〔reference_mode・ref_project・ref_snapshot〕。12: PlantUML の通知の設定〔plantuml_overload_notice〕。13: 相対比率の加算分の上限・下限〔ratio_limit_upper・ratio_limit_lower〕)
DEFAULT_DAILY_HOURS = 6.5
DEFAULT_WORK_START = time(9, 0)
DEFAULT_COLOR = "#4c8bf5"
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ
MIN_RATIO, MAX_RATIO = 0.1, 3.0  # 相対比率(10%〜300%)
MAX_SECTION_DEPTH = 3  # セクションの入れ子の上限(root 直下が 1 階層目。root は数えない)
SectionPath = tuple[int, ...]  # セクションの位置。root は ()、1 番目のセクションは (0,)、その 2 番目のサブセクションは (0, 1)
MIN_LEVEL_VALUE, MAX_LEVEL_VALUE = -0.9, 2.9  # パラメータの段階の判定値(-90%〜+290%)
MIN_ALLOCATION, MAX_ALLOCATION = 0.01, 1.0  # 割り当て率(1%〜100%)
MAX_WEEKS = 52  # 週ごとの担当の週数の上限。誤入力で配列が際限なく伸びるのを防ぐ
MIN_PROGRESS, MAX_PROGRESS = 0, 100  # 進捗度(%)
MAX_PROJECT_CODE_LENGTH = 20  # PRJコードの最大文字数
MAX_TASK_NAME_LENGTH = 50  # タスク名の最大文字数
MAX_CATEGORY_NAME_LENGTH = 30  # カテゴリの名前の最大文字数
MAX_CATEGORY_KIND_LENGTH = 20  # カテゴリの種別の最大文字数
MAX_EVENT_TEXT_LENGTH = 30  # イベントの文字列の最大文字数
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


FORBIDDEN_CATEGORIES = ("Cc", "Cf", "Zl", "Zp")  # todoapp の `has_control_chars` と同じ。受け取る側が拒否する文字を、こちらから渡さない


def has_control_char(text: str) -> bool:
    """名前に使えない文字を含むか。制御文字(Cc: 改行・タブなど)・書式制御文字(Cf: ゼロ幅文字・BOM など)・行/段落区切り(Zl・Zp)。"""
    return any(unicodedata.category(ch) in FORBIDDEN_CATEGORIES for ch in text)


def tidy_task_name(name: str) -> str:
    """読込で使う、タスク名の整形。制御文字は空白に替え、前後の空白を除き、上限を超える分は切り詰める(古いファイルを開けなくしない)。"""
    text = "".join(" " if has_control_char(ch) else ch for ch in name).strip()
    return text[:MAX_TASK_NAME_LENGTH].rstrip()


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
    REFERENCE = "プロジェクト参照"  # 他のプロジェクトを参照する行。日程・進捗・遅延・負荷は参照先から出す(自分の工数・担当・実績は持たない)
    SUMMARY = "まとめ"  # 分解した子のタスクをまとめる親。日程・工数・進捗・状態は子から算出し、保存しない


CHECKPOINT_STATUSES = (Status.NOT_STARTED, Status.DONE)  # チェックポイントが取れる状態


class ActualMode(StrEnum):
    SIMPLE = "simple"  # 簡易: 実績は 1 区間
    INTERVALS = "intervals"  # 区間: 実績を複数の区間で入力する


@dataclass
class WorkDay:
    """日付ごとの稼働の上書き(プロジェクト共通)。start・end がともに None なら休み。"""

    day: date
    start: time | None = None
    end: time | None = None  # 同じ日の 23:59 まで。start より後


@dataclass
class Member:
    name: str
    ratio: float = 1.0  # 基本比率(1.0 = 100%)。相対比率 = 基本比率 + 選んだ段階の判定値の合計
    levels: dict[str, str] = field(default_factory=dict)  # パラメータ名 → 選んだ段階名
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する(担当者はこの id で指す)
    icon: str = ""  # アイコン(128×128 の PNG の data URI)。空はアイコンなし
    work_days: list[WorkDay] = field(default_factory=list)  # 稼働日の上書き(日付の昇順。このメンバーだけに効く)


@dataclass
class Category:
    """プロジェクト共通のカテゴリ。todoapp のカテゴリと同じ項目を持つ。「未定」は持たない(`Task.category_id` が None)。"""

    name: str
    kind: str = ""  # 種別(自由入力)
    expiry_date: date | None = None  # 有効期限日。None は期限なし
    color: str = "blue"  # categories.COLORS のどれか
    prj_code: str = ""  # PRJコード。前後の空白は除く
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する


@dataclass
class Level:
    name: str
    value: float  # 判定値。割合(+0.2 = +20%)


@dataclass
class Parameter:
    name: str
    levels: list[Level] = field(default_factory=list)


@dataclass
class Event:
    """ガントチャートに出すイベント(プロジェクト共通)。日付の下の帯と、期間のセルの色になる。"""

    start: date
    end: date  # 終了日(含む)。start 以降
    text: str
    color: str = "gray"  # events.CSS_COLORS のどれか(小文字)
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する


@dataclass
class Actual:
    """実績の1区間。endがNoneのときは進行中。"""

    start: datetime
    end: datetime | None = None
    progress: int | None = None  # 廃止(常に None)。古いファイルの値は、読込でタスクの進捗度へ寄せる


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


def union_assignees(weeks: Sequence[Sequence[Assignee]]) -> list[Assignee]:
    """全週の担当者の和集合(初出の順)。割り当て率は各人の最大値。元の週は書き換えない。"""
    merged: dict[str, Assignee] = {}
    for week in weeks:
        for assignee in week:
            seen = merged.get(assignee.name)
            if seen is None:
                merged[assignee.name] = Assignee(assignee.name, assignee.allocation)
            elif assignee.allocation > seen.allocation:
                seen.allocation = assignee.allocation
    return list(merged.values())


class ReferenceMode(StrEnum):
    LIVE = "live"  # 表示のたびに参照先を読む(保存しない)
    SNAPSHOT = "snapshot"  # 参照行ごとに、参照値を保存して表示する


@dataclass(frozen=True)
class OverloadSpan:
    """参照先の、担当者の割り当て合計が 100% を超える期間。total は期間内の合計の最大(1.0 = 100%)。"""

    member: str
    start: datetime
    end: datetime
    total: float


@dataclass(frozen=True)
class ReferenceValue:
    """参照先のプロジェクト全体の値(細かなタスクは持たない)。スナップショットは、これと取得日時を保存する。"""

    planned_start: datetime | None = None  # 全タスクの実効の開始の最小
    planned_end: datetime | None = None  # 全タスクの完了予定の最大
    actual_start: datetime | None = None  # 実績の区間の開始の最小
    actual_end: datetime | None = None  # 実績の終了の最大。進行中の区間があれば None
    progress: int | None = None  # 工数で重みづけした進捗率(0〜100)。数えるタスクがなければ None
    finished: bool = False  # 数えるタスクがすべて終了
    delayed: int = 0  # 予定超過(終了していない)のタスク数
    peak_load: float = 0.0  # 割り当て合計のピーク(1.0 = 100%)。超過がなければ 0
    peak_member: str = ""
    overloads: tuple[OverloadSpan, ...] = ()
    taken_at: datetime | None = None  # スナップショットを取った日時(保存した値だけ)

    def same_as(self, other: "ReferenceValue") -> bool:
        """取得日時を除いて同じ値か(スナップショットが古いかの判定)。"""
        return replace(self, taken_at=None) == replace(other, taken_at=None)


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
    category_id: str | None = None  # カテゴリの id。None は「未定」
    kind: TaskKind = TaskKind.NORMAL  # チェックポイントは、締切だけを持つ(他の日時・工数・担当・実績は持たない)
    urls: list[TaskUrl] = field(default_factory=list)  # 関連する URL(チケット・資料など)
    progress: int | None = None  # タスクの進捗度(0〜100%)。進捗度の入力はこの 1 つだけ
    children: list[str] = field(default_factory=list)  # まとめの子のタスクの id(まとめだけが持つ)
    parameters: list[str] = field(default_factory=list)  # 付けたパラメータの名前。空は付けない(相対比率は全パラメータの合計)
    ref_project: str = ""  # 参照先のプロジェクトのファイル名(拡張子なし)。プロジェクト参照だけが持つ
    ref_snapshot: ReferenceValue | None = None  # 参照の方式がスナップショットのときの、保存した参照値
    weekly_crew: list[list[Assignee]] = field(default_factory=list)  # 週ごとの担当(添字が週。開始の日から 7 日ごと)。空は週ごとに分けない。分けるときの assignees は全週の和集合

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


@dataclass(frozen=True)
class RatioLimits:
    """相対比率の加算分(判定値の合計)の上限・下限。None の側は制限しない。"""

    upper: float | None = None
    lower: float | None = None


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
    categories: list[Category] = field(default_factory=list)  # カテゴリ(プロジェクト共通。「未定」は含まない)
    events: list[Event] = field(default_factory=list)  # イベント(プロジェクト共通。並びが色の優先順で、後ろが勝つ)
    reference_mode: ReferenceMode = ReferenceMode.LIVE  # プロジェクト参照の方式
    plantuml_overload_notice: bool = True  # PlantUML の保存後に、100% 超に見える担当者を通知するか
    ratio_limit_upper: float | None = None  # 相対比率の加算分の上限(+50% は 0.5)。None は制限なし
    ratio_limit_lower: float | None = None  # 同じく下限(-50% は -0.5)

    @property
    def ratio_limits(self) -> RatioLimits:
        return RatioLimits(self.ratio_limit_upper, self.ratio_limit_lower)

    def all_tasks(self) -> list[Task]:
        """セクションなしのタスク、続いて各セクションを深さ優先で(そのタスク → そのサブセクション)。"""
        tasks = list(self.tasks)
        for section in self.sections:
            tasks += section.all_tasks()
        return tasks

    def task_map(self) -> dict[str, Task]:
        """id → タスク。"""
        return {task.id: task for task in self.all_tasks()}

    def used_ids(self) -> set[str]:
        """タスク・メンバー・セクション・カテゴリ・イベントの id。新しい id が既存と重ならないように、振る側が渡す。"""
        return (
            {t.id for t in self.all_tasks()}
            | {m.id for m in self.members}
            | {s.id for _, s in walk_sections(self.sections)}
            | {c.id for c in self.categories}
            | {e.id for e in self.events}
        )
