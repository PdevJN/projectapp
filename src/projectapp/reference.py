"""プロジェクト参照: 参照先のプロジェクト全体の値の算出と、参照先の読み込み。NiceGUI に依存しない。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from projectapp.dashboard import ChildProject, _progress_weight
from projectapp.events import effective_holidays
from projectapp.models import OverloadSpan, Project, ReferenceMode, ReferenceValue, Status, Task, TaskKind
from projectapp.storage import file_digest, load_project
from projectapp.timeline import Schedule, is_overdue, overallocations

COUNTED_KINDS = (TaskKind.NORMAL, TaskKind.CHECKPOINT)  # 数えるのは通常タスクと節目だけ(まとめは二重になり、参照行は循環のもと)


def _counted(project: Project) -> list[Task]:
    return [task for task in project.all_tasks() if task.kind in COUNTED_KINDS]


def compute_reference(project: Project, holidays: dict[date, str], now: datetime) -> ReferenceValue:
    """参照先のプロジェクト全体の予定・実績・進捗・遅延・負荷。数えるタスクがなければ、日程なしの値。"""
    tasks = _counted(project)
    schedule = Schedule(project, holidays)
    starts = [moment for task in tasks if (moment := schedule.start(task)) is not None]
    ends = [moment for task in tasks if (moment := schedule.end(task)) is not None]
    intervals = [a for task in tasks for a in task.actuals]
    finished_ends = [a.end for a in intervals if a.end is not None]
    running = any(a.end is None for a in intervals)
    weights = [w for task in tasks if (w := _progress_weight(task)) is not None]
    total = sum(weight for weight, _ in weights)
    progress = round(sum(weight * percent for weight, percent in weights) / total) if total > 0 else None
    delayed = sum(1 for task in tasks if task.status is not Status.DONE and is_overdue(task, project, holidays, now, schedule))
    overloads = tuple(
        OverloadSpan(o.member, o.start, o.end, o.total) for o in overallocations(project, holidays, tasks)
    )
    peak = max(overloads, key=lambda o: o.total, default=None)
    return ReferenceValue(
        planned_start=min(starts, default=None),
        planned_end=max(ends, default=None),
        actual_start=min((a.start for a in intervals), default=None),
        actual_end=None if running or not finished_ends else max(finished_ends),
        progress=progress,
        finished=bool(tasks) and all(task.status is Status.DONE for task in tasks),
        delayed=delayed,
        peak_load=peak.total if peak else 0.0,
        peak_member=peak.member if peak else "",
        overloads=overloads,
    )


@dataclass(frozen=True)
class Reference:
    """参照行 1 つぶんの、表示に使う参照。value が None なら、帯・チップ・縞は出さない。"""

    value: ReferenceValue | None
    problem: str = ""  # 見つからない・読めない理由(正常は空)
    source: ReferenceMode = ReferenceMode.LIVE
    stale: bool = False  # スナップショットが、今の参照先の値と違う


class ReferenceResolver:
    """参照先のファイルを読んで、参照値にする。内容のハッシュと日付が同じ間は、同じ値を返す。"""

    def __init__(self, project_dir: Callable[[], Path], holidays: Callable[[], dict[date, str]]) -> None:
        self.project_dir = project_dir
        self.holidays = holidays
        self._cache: dict[str, tuple[tuple[str, date], ReferenceValue | None, str]] = {}
        self._projects: dict[str, tuple[str, Project]] = {}

    def live(self, name: str, now: datetime) -> tuple[ReferenceValue | None, str]:
        path = self.project_dir() / f"{name}.json"
        digest = file_digest(path)
        if digest is None:
            return None, f"「{name}.json」が格納先にありません"
        key = (digest, now.date())  # 超過の判定が日付で変わるので、日付も鍵にする
        cached = self._cache.get(name)
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        try:
            project = load_project(path)
            value, problem = compute_reference(project, effective_holidays(project, self.holidays()), now), ""
        except Exception as exc:  # noqa: BLE001 他人のファイルの形の崩れで、画面を止めない
            value, problem = None, f"「{name}.json」を読めません({exc or type(exc).__name__})"
        self._cache[name] = (key, value, problem)
        return value, problem

    def project(self, name: str) -> tuple[Project | None, str]:
        """参照先のプロジェクトそのもの(ダッシュボードの展開用)。内容のハッシュが同じ間は同じ物を返す。"""
        path = self.project_dir() / f"{name}.json"
        digest = file_digest(path)
        if digest is None:
            return None, f"「{name}.json」が格納先にありません"
        cached = self._projects.get(name)
        if cached is not None and cached[0] == digest:
            return cached[1], ""
        try:
            loaded = load_project(path)
        except Exception as exc:  # noqa: BLE001 他人のファイルの形の崩れで、画面を止めない
            return None, f"「{name}.json」を読めません({exc or type(exc).__name__})"
        self._projects[name] = (digest, loaded)
        return loaded, ""


def build_references(project: Project, resolver: ReferenceResolver, now: datetime) -> dict[str, Reference]:
    """参照行(タスクの id)ごとの参照。常に最新は参照先を読み、スナップショットは保存した値で出す(古さも調べる)。"""
    result: dict[str, Reference] = {}
    for task in project.all_tasks():
        if task.kind is not TaskKind.REFERENCE:
            continue
        live, problem = resolver.live(task.ref_project, now)
        if project.reference_mode is ReferenceMode.SNAPSHOT:
            saved = task.ref_snapshot
            stale = live is not None and (saved is None or not saved.same_as(live))
            result[task.id] = Reference(saved, problem, ReferenceMode.SNAPSHOT, stale)
        else:
            result[task.id] = Reference(live, problem, ReferenceMode.LIVE)
    return result


def take_snapshot(resolver: ReferenceResolver, name: str, now: datetime) -> ReferenceValue | None:
    """今の参照先の値に取得日時を付けたスナップショット。取れなければ None。"""
    value, _ = resolver.live(name, now)
    return replace(value, taken_at=now) if value is not None else None


def missing_references(project: Project, resolver: ReferenceResolver, now: datetime) -> list[str]:
    """見つからない・読めない参照先のファイル名(重複なし・初出の順)。"""
    names = dict.fromkeys(t.ref_project for t in project.all_tasks() if t.kind is TaskKind.REFERENCE)
    return [name for name in names if resolver.live(name, now)[0] is None]


def load_children(
    project: Project, resolver: ReferenceResolver, base_holidays: dict[date, str]
) -> dict[str, ChildProject]:
    """参照行が指す参照先を、ダッシュボードに数える形で読む(重複は 1 回、自分自身と読めないものは外す)。"""
    names = dict.fromkeys(t.ref_project for t in project.all_tasks() if t.kind is TaskKind.REFERENCE)
    children: dict[str, ChildProject] = {}
    for name in names:
        if name == project.name:
            continue
        child, _ = resolver.project(name)
        if child is not None:
            children[name] = ChildProject(child, effective_holidays(child, base_holidays))
    return children
