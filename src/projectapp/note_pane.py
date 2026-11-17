"""タスクのメモの右ペイン(要望 150)。`right_drawer`に`ui.editor`を入れ、入力が止まって約 1 秒後に自動で保存する。"""

from collections.abc import Callable

from nicegui import ui

WIDTH_PX = 360
SAVE_SECONDS = 1.0


class NotePane:
    def __init__(
        self,
        save: Callable[[str, str, str], object],
        load: Callable[[str, str], str | None],
    ) -> None:
        self._save = save
        self._load = load
        self.name: str | None = None
        self.task_id: str | None = None
        self.dirty = False
        self._loading = False
        self.drawer = (
            ui.right_drawer(value=False, fixed=True, bordered=True)
            .props(f"width={WIDTH_PX} behavior=desktop")
            .mark("note-pane")
        )
        with self.drawer:
            with ui.row().classes("w-full items-center no-wrap"):
                self.title = (
                    ui.label("")
                    .classes("text-subtitle1 ellipsis flex-1")
                    .mark("note-title")
                )
                ui.button(icon="close", on_click=lambda: self.close()).props(
                    "flat dense round"
                ).mark("note-close")
            self.editor = (
                ui.editor(placeholder="メモ").classes("w-full").mark("note-editor")
            )
        self.editor.on_value_change(self._edited)
        self.drawer.on("keydown.esc", lambda: self.close())
        ui.timer(SAVE_SECONDS, self.flush)

    def open(self, name: str, task_id: str, title: str) -> None:
        """メモを開く。開いていたメモの入力は、先に保存する。"""
        self.flush()
        self.name, self.task_id = name, task_id
        self.title.set_text(title)
        self._loading = True
        try:
            self.editor.set_value(self._load(name, task_id) or "")
        finally:
            self._loading = False
        self.dirty = False
        self.drawer.show()

    def _edited(self, _event: object = None) -> None:
        if not self._loading:
            self.dirty = True

    def flush(self) -> None:
        if self.dirty and self.name is not None and self.task_id is not None:
            self.dirty = False
            self._save(self.name, self.task_id, self.editor.value or "")

    def close(self, save: bool = True) -> None:
        """閉じる。save が偽なら、入力を捨てる(開いていたタスクが消えたとき)。"""
        if save:
            self.flush()
        self.dirty = False
        self.name = self.task_id = None
        self.drawer.hide()
