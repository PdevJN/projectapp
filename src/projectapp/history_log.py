"""変更履歴(要望 128)。タスクの状態・進捗度・工数の変化を、プロジェクト全体のログ(`Project.history`)に追記する。

NiceGUI に依存しない。データの持ち方を変えるときは、この境界の内側で変える(集計と画面はここの関数だけを通す)。
"""

from datetime import datetime

from projectapp.models import (
    HISTORY_FIELDS,
    Change,
    HistoryEvent,
    Project,
    Task,
    TaskKind,
    Value,
)


def _recordable(task: Task) -> bool:
    """記録の対象は通常タスクだけ。まとめは子から算出し、節目は進捗度を持たず、参照は参照先の値。"""
    return task.kind is TaskKind.NORMAL


def _values(task: Task) -> dict[str, Value]:
    return {
        "status": task.status.value,
        "progress": task.progress,
        "effort": task.total_effort,
    }


def creation_events(project: Project, now: datetime) -> list[HistoryEvent]:
    """いまある通常タスクすべての作成イベント(各項目の before は None)。"""
    events = []
    for task in project.all_tasks():
        if not _recordable(task):
            continue
        values = _values(task)
        events.append(
            HistoryEvent(
                task.id,
                now,
                tuple(Change(name, None, values[name]) for name in HISTORY_FIELDS),
            )
        )
    return events


def diff_events(before: Project, after: Project, now: datetime) -> list[HistoryEvent]:
    """編集の前後の差から、タスクごとに 1 件のイベントを作る。新しい通常タスクは作成イベント、消えたタスクは記録しない。"""
    old = {t.id: t for t in before.all_tasks() if _recordable(t)}
    events = []
    for task in after.all_tasks():
        if not _recordable(task):
            continue
        new = _values(task)
        if task.id not in old:
            changes = tuple(Change(name, None, new[name]) for name in HISTORY_FIELDS)
        else:
            was = _values(old[task.id])
            changes = tuple(
                Change(name, was[name], new[name])
                for name in HISTORY_FIELDS
                if was[name] != new[name]
            )
        if changes:
            events.append(HistoryEvent(task.id, now, changes))
    return events


def record_edit(before: Project, after: Project, now: datetime) -> None:
    """編集の前後の差を`after.history`に足す。記録を始めた日時は、最初の編集の時刻にする。"""
    after.history.extend(diff_events(before, after, now))
    if after.history_since is None:
        after.history_since = now


def stamp_creation(project: Project, now: datetime) -> None:
    """取り込んだ(保存前の新規の)プロジェクトに、作成イベントと記録の開始を入れる。"""
    project.history.extend(creation_events(project, now))
    project.history_since = now
