"""変更履歴(要望 128)。タスクの状態・進捗度・工数の変化を、プロジェクト全体のログ(`Project.history`)に追記する。

NiceGUI に依存しない。データの持ち方を変えるときは、この境界の内側で変える(集計と画面はここの関数だけを通す)。
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime

from projectapp.models import (
    HISTORY_FIELDS,
    Change,
    HistoryEvent,
    Project,
    Status,
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
    """編集の前後の差から、タスクごとに 1 件のイベントを作る。新しい通常タスクは作成イベント、消えたタスクは記録しない。
    通常タスクがまとめなどに変わって残るときは、退場のイベント(各項目の後が None)を作る。"""
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
    # 通常タスクが、残ったまま通常でなくなった(分解でまとめになった)ときは、各項目の after を None にした退場の記録
    still_there = {t.id for t in after.all_tasks() if not _recordable(t)}
    for task_id, task in old.items():
        if task_id in still_there:
            was = _values(task)
            events.append(
                HistoryEvent(
                    task_id,
                    now,
                    tuple(Change(name, was[name], None) for name in HISTORY_FIELDS),
                )
            )
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


@dataclass(frozen=True)
class TaskState:
    """ある時点のタスクの、記録している 3 項目。"""

    status: Status
    progress: int | None
    effort: float


def events_by_task(project: Project) -> dict[str, list[HistoryEvent]]:
    """タスクの id ごとのイベント(日時順)。同じ日時は記録した順。"""
    index: dict[str, list[HistoryEvent]] = {}
    for event in sorted(project.history, key=lambda e: e.at):
        index.setdefault(event.task, []).append(event)
    return index


def is_known(project: Project, moment: datetime) -> bool:
    """`moment`の値を履歴から復元できるか。記録を始めた日時より前、または一度も記録していないときは不明。"""
    return project.history_since is not None and moment >= project.history_since


def state_at(
    task: Task, events: Sequence[HistoryEvent], moment: datetime
) -> TaskState | None:
    """`moment`(その時刻の直前まで)のタスクの値。`events`はこのタスクの分(日時順)。
    項目ごとに、直前のイベントの「後」。なければ、その後の最初のイベントの「前」。それもなければ現在の値。
    その時点で作られていなければ None。"""
    current = _values(task)
    found: dict[str, Value] = {}
    for name in HISTORY_FIELDS:
        touching = [(e.at, c) for e in events for c in e.changes if c.field == name]
        earlier = [c for at, c in touching if at < moment]
        later = [c for at, c in touching if at >= moment]
        if earlier:
            found[name] = earlier[-1].after
        elif later:
            found[name] = later[0].before
        else:
            found[name] = current[name]
    if found["status"] is None:
        return None
    progress, effort = found["progress"], found["effort"]
    return TaskState(
        Status(str(found["status"])),
        progress if isinstance(progress, int) else None,
        float(effort) if isinstance(effort, (int, float)) else 0.0,
    )


def merge_logs(*logs: Sequence[HistoryEvent]) -> list[HistoryEvent]:
    """複数のログの和集合。同じイベント(タスク・日時・変化が同じ)は 1 件にし、日時順に並べる。"""
    unique = dict.fromkeys(event for log in logs for event in log)
    return sorted(unique, key=lambda e: e.at)


def earliest(*moments: datetime | None) -> datetime | None:
    known = [m for m in moments if m is not None]
    return min(known) if known else None


def reconcile(project: Project, at: datetime) -> int:
    """ログの最後の「後」と現在の値が食い違うタスクに、`at`の補正イベントを足す(3 者マージの衝突の解決などで起きる)。
    ログのないタスクは対象外。足した件数を返す。"""
    index = events_by_task(project)
    added = 0
    for task in project.all_tasks():
        if not _recordable(task) or task.id not in index:
            continue
        last: dict[str, Value] = {}
        for event in index[task.id]:
            for change in event.changes:
                last[change.field] = change.after
        current = _values(task)
        changes = tuple(
            Change(name, last[name], current[name])
            for name in HISTORY_FIELDS
            if name in last and last[name] != current[name]
        )
        if changes:
            project.history.append(HistoryEvent(task.id, at, changes))
            added += 1
    return added


def without_history(project: Project) -> Project:
    """履歴を空にした浅い複製。`asdict`が履歴の全イベントを辞書にする手間を省くために使う(元は変えない)。"""
    return replace(project, history=[])


def dirty_key(project: Project) -> tuple:
    """保存済みかどうかの比較用の値。履歴を除いた全体の辞書に、履歴の件数と最後のイベントを添える。
    履歴は追記のみ(元に戻すで減る)なので、これで変化を見逃さない。履歴の長さに比例して重くならない。"""
    last = project.history[-1] if project.history else None
    return (asdict(without_history(project)), len(project.history), last)
