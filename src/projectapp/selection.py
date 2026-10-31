"""プレビューの出力選択。チェックを外したタスクの id の集合(excluded)を扱う。NiceGUI には依存しない。"""

from collections.abc import Collection, Mapping
from enum import Enum

from projectapp.models import Section, Task, TaskKind


class CheckState(Enum):
    ON = "on"
    OFF = "off"
    MIXED = "mixed"


def task_ids_of(item: Task | Section, by_id: Mapping[str, Task]) -> list[str]:
    """チェックの対象のタスク id。まとめは自身ではなく子、セクションは配下のタスク(サブセクション含む)。"""
    if isinstance(item, Section):
        return [
            i
            for t in item.all_tasks()
            if t.kind is not TaskKind.SUMMARY
            for i in task_ids_of(t, by_id)
        ]
    if item.kind is TaskKind.SUMMARY:
        return [cid for cid in item.children if cid in by_id]
    return [item.id]


def check_state(ids: Collection[str], excluded: Collection[str]) -> CheckState | None:
    """ids の全部が出力なら ON、全部外れなら OFF、混在なら MIXED。対象がなければ None。"""
    if not ids:
        return None
    off = sum(1 for i in ids if i in excluded)
    if off == 0:
        return CheckState.ON
    return CheckState.OFF if off == len(ids) else CheckState.MIXED


def set_checked(
    excluded: frozenset[str], ids: Collection[str], checked: bool
) -> frozenset[str]:
    """ids をまとめて出力する(checked)・しないにした excluded を返す。"""
    return excluded - set(ids) if checked else excluded | set(ids)


def toggled(state: CheckState) -> bool:
    """押したあとのチェック。混在は、全部出力にする。"""
    return state is not CheckState.ON
