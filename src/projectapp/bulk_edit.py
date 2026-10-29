"""複数タスクの一括編集。NiceGUI に依存しない。apply_bulk は project を変えず、変更後のタスクを返す。"""

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum

from projectapp.effortunits import DECIMALS
from projectapp.models import MAX_YEAR, MIN_YEAR, Assignee, Project, Task, TaskKind, walk_sections
from projectapp.timeline import Schedule, own_end

SKIP_KIND = "対象外の種別"
SKIP_NO_CREW = "担当なし"
SKIP_NO_START = "開始予定なし"
SKIP_BEFORE_START = "開始予定より前"
SKIP_NO_END = "完了予定が読めない"
SKIP_NO_EFFORT = "工数なし"
SKIP_NEGATIVE = "工数が 0 未満"
SKIP_RANGE = "日付が範囲外"

CATEGORY_KINDS = (TaskKind.NORMAL, TaskKind.SUMMARY, TaskKind.CHECKPOINT)


class CrewMode(Enum):
    ADD = "追加"
    REMOVE = "削除"
    REPLACE = "置き換え"
    FROM_WEEK = "第 N 週以降"


@dataclass(frozen=True)
class CrewChange:
    mode: CrewMode
    members: tuple[Assignee, ...] = ()  # ADD・REMOVE は 1 人(REMOVE は名前だけ使う)。REPLACE・FROM_WEEK は一覧
    from_week: int = 2  # FROM_WEEK だけ(1 始まり。2〜MAX_WEEKS)


@dataclass(frozen=True)
class CategoryChange:
    category_id: str | None  # None は「未定」


class EndMode(Enum):
    DATE = "日付を指定"
    SHIFT = "ずらす"


@dataclass(frozen=True)
class EndChange:
    mode: EndMode
    day: date | None = None  # DATE
    days: int = 0  # SHIFT(暦日。負は前へ)


class EffortMode(Enum):
    SET = "値にする"
    ADJUST = "増減"


@dataclass(frozen=True)
class EffortChange:
    mode: EffortMode
    hours: float  # 時間に換算済み(増減は負も可)


@dataclass(frozen=True)
class BulkChanges:
    crew: CrewChange | None = None
    category: CategoryChange | None = None
    end: EndChange | None = None
    effort: EffortChange | None = None

    @property
    def any_change(self) -> bool:
        return any(c is not None for c in (self.crew, self.category, self.end, self.effort))


@dataclass
class BulkResult:
    tasks: dict[str, Task] = field(default_factory=dict)  # 変わったタスクだけ(id → 変更後)。描画順
    skips: Counter[str] = field(default_factory=Counter)  # 理由 → 項目の数
    review_needed: int = 0  # 換算率が変わり、完了予定の見直しが要るタスク
    manual_switched: int = 0  # 自動算出から手で指定に変わったタスク(工数あり)
    weeks_dropped: int = 0  # 置き換えで週ごとが解除されたタスク
    emptied: int = 0  # 担当の削除で担当なしになったタスク
    filled_weeks: int = 0  # 担当の削除で空になり、隣の週と同じにした週

    @property
    def changed(self) -> int:
        return len(self.tasks)

    @property
    def skipped(self) -> int:
        return sum(self.skips.values())

    def skip(self, reason: str) -> None:
        self.skips[reason] += 1


def _category(task: Task, change: CategoryChange, result: BulkResult) -> Task:
    if task.kind not in CATEGORY_KINDS:
        result.skip(SKIP_KIND)
        return task
    return replace(task, category_id=change.category_id)


def _effort(task: Task, change: EffortChange, result: BulkResult) -> Task:
    if task.kind is not TaskKind.NORMAL:
        result.skip(SKIP_KIND)
        return task
    if change.mode is EffortMode.SET:
        hours = round(change.hours, DECIMALS)
    else:
        if task.effort_hours <= 0:
            result.skip(SKIP_NO_EFFORT)
            return task
        hours = round(task.effort_hours + change.hours, DECIMALS)
    if hours < 0:
        result.skip(SKIP_NEGATIVE)
        return task
    return replace(task, effort_hours=hours)


def _end(task: Task, original: Task, change: EndChange, project: Project, holidays: dict[date, str], result: BulkResult) -> Task:
    if task.kind is not TaskKind.NORMAL:
        result.skip(SKIP_KIND)
        return task
    if change.mode is EndMode.DATE:
        assert change.day is not None
        new_end = datetime.combine(change.day, project.work_start) + timedelta(hours=project.daily_hours)
    else:
        base = own_end(original, project, holidays)  # 押し出しを含めない(手指定にすると押し出しは二重に掛かるため)
        if base is None:
            result.skip(SKIP_NO_END)
            return task
        try:
            new_end = base + timedelta(days=change.days)
        except OverflowError:
            result.skip(SKIP_RANGE)
            return task
    if not MIN_YEAR <= new_end.year <= MAX_YEAR:
        result.skip(SKIP_RANGE)
        return task
    if task.planned_start is not None and new_end < task.planned_start:
        result.skip(SKIP_BEFORE_START)
        return task
    if task.effort_hours > 0 and not task.planned_end_manual:
        result.manual_switched += 1
    return replace(task, planned_end=new_end, planned_end_manual=True)


def apply_bulk(project: Project, ids: Sequence[str], changes: BulkChanges, holidays: dict[date, str]) -> BulkResult:
    """ids(描画順)のタスクに changes を当てた結果を返す。project は変えない(ダイアログの見込みにも使う)。
    項目の順は 担当 → カテゴリ → 工数 → 完了予定。ずらしの基準は、元のタスクの完了予定。"""
    by_id = project.task_map()
    schedule = Schedule(project, holidays)
    result = BulkResult()
    for task_id in ids:
        original = by_id.get(task_id)
        if original is None:
            continue
        task = original
        if changes.crew is not None:
            task = _crew(task, changes.crew, project, holidays, schedule, result)
        if changes.category is not None:
            task = _category(task, changes.category, result)
        if changes.effort is not None:
            task = _effort(task, changes.effort, result)
        if changes.end is not None:
            task = _end(task, original, changes.end, project, holidays, result)
        if task != original:
            result.tasks[task_id] = task
    return result


def _task_lists(project: Project) -> list[list[Task]]:
    return [project.tasks, *(section.tasks for _, section in walk_sections(project.sections))]


def store(project: Project, result: BulkResult) -> None:
    """結果のタスクを、同じ id のタスクの位置に差し込む(並びは変えない)。"""
    for tasks in _task_lists(project):
        for index, task in enumerate(tasks):
            if task.id in result.tasks:
                tasks[index] = result.tasks[task.id]


def forecast_text(result: BulkResult, total: int) -> str:
    """ダイアログの適用前の見込み。"""
    text = f"対象 {total} 件 / 変更 {result.changed} 件"
    if result.skips:
        reasons = "・".join(f"{reason} {count}" for reason, count in result.skips.items())
        text += f" / スキップ {result.skipped} 項目({reasons})"
    return text


def _crew(task: Task, change: CrewChange, project: Project, holidays: dict[date, str], schedule: Schedule, result: BulkResult) -> Task:
    raise NotImplementedError  # Task 3 で実装する
