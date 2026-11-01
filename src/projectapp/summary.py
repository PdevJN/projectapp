"""まとめタスクの規則(状態・進捗の算出、親子の対応、空のまとめの扱い)。NiceGUI には依存しない純粋関数。

日程(開始・完了)は `timeline.Schedule` が算出する。
"""

from collections.abc import Mapping, Sequence
from math import isfinite

from projectapp.models import Project, ReferenceValue, Status, Task, TaskKind


def parent_map(project: Project) -> dict[str, str]:
    """子のタスクの id → まとめの id。"""
    return {
        cid: task.id
        for task in project.all_tasks()
        if task.kind is TaskKind.SUMMARY
        for cid in task.children
    }


def children_of(task: Task, by_id: Mapping[str, Task]) -> list[Task]:
    """まとめの子。`children` の順で、`by_id` にないものは飛ばす。"""
    return [by_id[cid] for cid in task.children if cid in by_id]


def _status_of(child: Task, references: Mapping[str, ReferenceValue] | None) -> Status:
    """子の状態。参照行は、状態を持たないので、参照先の値から出す(値がなければ未着手)。"""
    if child.kind is not TaskKind.REFERENCE:
        return child.status
    value = (references or {}).get(child.id)
    if value is None:
        return Status.NOT_STARTED
    if value.finished:
        return Status.DONE
    return Status.RUNNING if value.actual_start is not None else Status.NOT_STARTED


def summary_status(
    children: Sequence[Task], references: Mapping[str, ReferenceValue] | None = None
) -> Status:
    """全員が終了なら終了、1 つでも着手済み(実行中・一時停止・終了)なら実行中、それ以外は未着手。
    参照行は参照先の値(全部終了なら終了、実績があれば実行中)で数える。"""
    states = [_status_of(c, references) for c in children]
    if states and all(s is Status.DONE for s in states):
        return Status.DONE
    if any(s is not Status.NOT_STARTED for s in states):
        return Status.RUNNING
    return Status.NOT_STARTED


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def _percent_of(
    child: Task, references: Mapping[str, ReferenceValue] | None
) -> tuple[int | None, float]:
    """(進捗度, 重み)。参照行は参照先の進捗(全部終了なら 100)で、重みは 1。進捗度がないものは None。"""
    if child.kind is TaskKind.REFERENCE:
        value = (references or {}).get(child.id)
        if value is None:
            return None, 1.0
        return (100 if value.finished else value.progress), 1.0
    return (100 if child.status is Status.DONE else child.progress), _weight(
        child.total_effort
    )


def summary_progress(
    children: Sequence[Task], references: Mapping[str, ReferenceValue] | None = None
) -> int | None:
    """子の進捗度を、工数(なければ 1)で重みづけした平均(四捨五入)。終了は 100、進捗度がないものは 0。
    どの子にも進捗度がなく、終了もないときは None。参照行は参照先の進捗で、重みは 1。"""
    parts = [_percent_of(c, references) for c in children]
    if all(percent is None for percent, _ in parts):
        return None
    weighted = sum(weight * (percent or 0) for percent, weight in parts)
    total = sum(weight for _, weight in parts)
    return int(
        weighted / total + 0.5
    )  # 四捨五入(round は銀行丸めで、62.5 が 62 になる)


def revert_empty(project: Project) -> None:
    """子のいなくなったまとめを、通常タスクに戻す。"""
    for task in project.all_tasks():
        if task.kind is TaskKind.SUMMARY and not task.children:
            task.kind = TaskKind.NORMAL


def drop_child(project: Project, task_id: str) -> None:
    """全まとめの子から、その id を取り除く(タスクの削除のとき)。空になったまとめは通常タスクに戻す。"""
    for task in project.all_tasks():
        if task_id in task.children:
            task.children = [cid for cid in task.children if cid != task_id]
    revert_empty(project)
