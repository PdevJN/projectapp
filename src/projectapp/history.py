"""元に戻す・やり直しの履歴(NiceGUI に依存しない)。プロジェクトの複製を積む。"""

from collections import deque
from copy import deepcopy

from projectapp.models import Project

HISTORY_LIMIT = 50


class History:
    """変更の直前の状態(Undo)と、戻した側の状態(Redo)を持つ。どちらも複製で持ち、上限を超えたら古い物から捨てる。"""

    def __init__(self, limit: int = HISTORY_LIMIT) -> None:
        self.undo_stack: deque[Project] = deque(maxlen=limit)
        self.redo_stack: deque[Project] = deque(maxlen=limit)

    def record(self, before: Project) -> None:
        """変更の直前の状態を積む。新しい編集なので、Redo は空にする。直前に積んだ物と等しければ積まない。"""
        self.redo_stack.clear()
        if self.undo_stack and self.undo_stack[-1] == before:
            return
        self.undo_stack.append(deepcopy(before))

    def undo(self, current: Project) -> Project | None:
        """いまの状態を Redo に積み、直前の状態を返す。戻せなければ None(何も変えない)。"""
        if not self.undo_stack:
            return None
        self.redo_stack.append(deepcopy(current))
        return self.undo_stack.pop()

    def redo(self, current: Project) -> Project | None:
        """いまの状態を Undo に積み、やり直す状態を返す。やり直せなければ None(何も変えない)。"""
        if not self.redo_stack:
            return None
        self.undo_stack.append(deepcopy(current))
        return self.redo_stack.pop()

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)
