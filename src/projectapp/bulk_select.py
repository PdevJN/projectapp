"""複数タスクの一括操作の選択。NiceGUI に依存しない。タスクの id で持つ(行の位置は編集で変わるため)。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from projectapp.models import Task, TaskKind


def with_children(task_id: str, by_id: Mapping[str, Task]) -> list[str]:
    """task_id と、まとめなら子(by_id にあるもの)。task_id が by_id になければ空。"""
    task = by_id.get(task_id)
    if task is None:
        return []
    if task.kind is TaskKind.SUMMARY:
        return [task_id, *(cid for cid in task.children if cid in by_id)]
    return [task_id]


@dataclass
class BulkSelection:
    ids: set[str] = field(default_factory=set)
    anchor: str | None = None  # Shift クリックの基点(最後に Cmd/Ctrl クリックした行)

    def toggle(self, task_id: str, by_id: Mapping[str, Task]) -> None:
        """Cmd/Ctrl クリック。まとめなら子もまとめて入れる・外す。基点を動かす。"""
        group = with_children(task_id, by_id)
        if not group:
            return
        if task_id in self.ids:
            self.ids.difference_update(group)
        else:
            self.ids.update(group)
        self.anchor = task_id

    def extend(
        self, visible_ids: Sequence[str], task_id: str, by_id: Mapping[str, Task]
    ) -> None:
        """Shift クリック。見えている行の中で、基点と task_id の間を加える。基点が使えなければ toggle と同じ。"""
        if self.anchor not in visible_ids or task_id not in visible_ids:
            self.toggle(task_id, by_id)
            return
        first, last = sorted(
            (visible_ids.index(self.anchor), visible_ids.index(task_id))
        )
        for tid in visible_ids[first : last + 1]:
            self.ids.update(with_children(tid, by_id))

    def effective(self, visible_ids: Sequence[str]) -> list[str]:
        """適用の対象。見えている行だけを、描画順で返す(絞り込みで隠れた行は含めない)。"""
        return [tid for tid in visible_ids if tid in self.ids]

    def prune(self, by_id: Mapping[str, Task]) -> None:
        """削除や Undo でなくなった id を落とす。"""
        self.ids.intersection_update(by_id.keys())
        if self.anchor not in by_id:
            self.anchor = None

    def clear(self) -> None:
        self.ids.clear()
        self.anchor = None
