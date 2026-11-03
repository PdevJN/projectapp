"""担当なしのタスクに、メンバーを 1 人割り当てる小さなダイアログ(要望 39)。"""

from collections.abc import Callable, Sequence

from nicegui import ui

from projectapp.avatar import avatar
from projectapp.forms import disposable
from projectapp.models import Member


def open_assign_dialog(
    task_name: str,
    members: Sequence[Member],
    on_pick: Callable[[str], object],
) -> None:
    """メンバーを押すと`on_pick(名前)`を呼んで閉じる。割り当て率は呼び出し側が既定(100%)で入れる。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label("担当を割り当てる").classes("text-h6")
        ui.label(task_name).classes("text-grey ellipsis").mark("assign-task-name")

        def pick(name: str) -> None:
            dialog.close()
            on_pick(name)

        with ui.column().classes("w-full gap-1"):
            for member in members:
                with (
                    ui.item(on_click=lambda n=member.name: pick(n))
                    .props("clickable dense")
                    .classes("w-full")
                    .mark(f"assign-member-{member.name}")
                ):
                    with ui.row().classes("items-center no-wrap gap-2"):
                        avatar(member.name, member.icon, 20)
                        ui.label(member.name)
        ui.button("キャンセル", on_click=dialog.close).props("flat")
    dialog.open()
