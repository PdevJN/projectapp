"""まとめタスクの規則(状態・進捗の算出、親子の対応、空のまとめの扱い)。NiceGUI には依存しない純粋関数。

日程(開始・完了)は `timeline.Schedule` が算出する。
"""

from collections.abc import Mapping, Sequence
from math import isfinite

from projectapp.models import Project, Status, Task, TaskKind


def parent_map(project: Project) -> dict[str, str]:
    """子のタスクの id → まとめの id。"""
    return {cid: task.id for task in project.all_tasks() if task.kind is TaskKind.SUMMARY for cid in task.children}


def children_of(task: Task, by_id: Mapping[str, Task]) -> list[Task]:
    """まとめの子。`children` の順で、`by_id` にないものは飛ばす。"""
    return [by_id[cid] for cid in task.children if cid in by_id]


def summary_status(children: Sequence[Task]) -> Status:
    """全員が終了なら終了、1 つでも着手済み(実行中・一時停止・終了)なら実行中、それ以外は未着手。"""
    if children and all(c.status is Status.DONE for c in children):
        return Status.DONE
    if any(c.status is not Status.NOT_STARTED for c in children):
        return Status.RUNNING
    return Status.NOT_STARTED


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def summary_progress(children: Sequence[Task]) -> int | None:
    """子の進捗度を、工数(なければ 1)で重みづけした平均(四捨五入)。終了は 100、進捗度がないものは 0。
    どの子にも進捗度がなく、終了もないときは None。"""
    if not any(c.status is Status.DONE or c.progress is not None for c in children):
        return None
    weighted = total = 0.0
    for c in children:
        weight = _weight(c.effort_hours)
        percent = 100 if c.status is Status.DONE else (c.progress or 0)
        weighted += weight * percent
        total += weight
    return int(weighted / total + 0.5)  # 四捨五入(round は銀行丸めで、62.5 が 62 になる)


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
