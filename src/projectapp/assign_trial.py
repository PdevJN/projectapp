"""アサイン専用画面(要望 168)の試算の状態。NiceGUI に依存しない純粋関数。

試算は保存しない(ファイル形式は変えない)。開いた時点のタスクのコピーを画面の中で持ち、確定したときだけ
`crew_trial.replace_task`で書き戻す。
"""

from copy import deepcopy
from dataclasses import dataclass, replace

from projectapp.crew_trial import replace_task
from projectapp.models import Project, Status, Task, TaskKind


@dataclass
class AssignTrial:
    original: Task  # 開いた時点のタスク(変更の有無を比べる基準)
    task: Task  # 画面の中で編集するコピー


def start_trial(task: Task) -> AssignTrial:
    return AssignTrial(deepcopy(task), deepcopy(task))


def is_dirty(trial: AssignTrial) -> bool:
    return trial.task != trial.original


def is_assignable(task: Task) -> bool:
    """アサインの対象になるタスク: 通常で、終了していないもの。"""
    return task.kind is TaskKind.NORMAL and task.status is not Status.DONE


def hidden_ids(project: Project, trial: AssignTrial) -> frozenset[str]:
    """日程の計算のために複製へ入れる先行タスクの id(たどれる限り)。描かない。"""
    tasks = project.task_map()
    found: set[str] = set()
    stack = list(trial.task.predecessors)
    while stack:
        pid = stack.pop()
        pred = tasks.get(pid)
        if pid in found or pid == trial.task.id or pred is None:
            continue
        found.add(pid)
        stack.extend(pred.predecessors)
    return frozenset(found)


def trial_project(project: Project, trial: AssignTrial) -> Project:
    """試算のタスクと、その日程を決める先行タスクだけを持つプロジェクトの複製(ガントチャートの描画用)。

    先行タスクがないと、後続の開始・完了が求まらず、メインと違う描画になる。先行は`hidden_ids`で描かない。
    元は変えない。"""
    copy = deepcopy(project)
    keep = hidden_ids(project, trial)
    others = [task for task in copy.all_tasks() if task.id in keep]
    return replace(copy, tasks=[deepcopy(trial.task), *others], sections=[])


def apply_trial(project: Project, trial: AssignTrial) -> bool:
    """試算のコピーを、同じ id のタスクへ書き戻す。タスクがなければ False。"""
    return replace_task(project, deepcopy(trial.task))
