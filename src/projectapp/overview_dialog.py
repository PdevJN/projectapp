"""俯瞰図のダイアログ。座標は`overview.py`の純粋関数で作り、ここは描くだけ。"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from projectapp.forms import disposable
from projectapp.gantt import STATUS_COLORS
from projectapp.overview import Layout, OverviewNode, layout_overview

PAGE_MARGIN = 16
LATE_COLOR = "#ef5350"  # 予定超過・期限超過の枠
EDGE_STYLE = (
    "position: absolute; border-color: #90a4ae; border-style: solid; border-width: 0;"
)


def open_overview_dialog(
    root: OverviewNode,
    on_jump: Callable[[str], object],
    on_pdf: Callable[[Layout], Awaitable[None]],
) -> None:
    """俯瞰図を開く。チェックボックスの状態は、このダイアログの中だけで持つ(保存しない)。"""
    state = {"progress": True, "effort": True, "tasks": False}

    def current() -> Layout:
        return layout_overview(root, state["progress"], state["effort"], state["tasks"])

    with (
        disposable(ui.dialog()).props("maximized") as dialog,
        ui.card().classes("w-full h-full"),
    ):

        def jump(task_id: str | None) -> None:
            dialog.close()
            if task_id is not None:
                on_jump(task_id)

        @ui.refreshable
        def diagram() -> None:
            layout = current()
            if not state["tasks"] and root.children and len(layout.placed) == 1:
                ui.label(
                    "「タスクの詳細」をオンにすると、配下のタスクが出ます"
                ).classes("text-caption text-grey").mark("overview-hint")
            with ui.scroll_area().classes("w-full grow"):
                with ui.element("div").style(
                    f"position: relative; width: {layout.width + PAGE_MARGIN * 2}px;"
                    f" height: {layout.height + PAGE_MARGIN * 2}px"
                ):
                    for edge in layout.edges:
                        mid = (edge.x1 + edge.x2) // 2
                        top, bottom = sorted((edge.y1, edge.y2))
                        for style in (
                            f"left: {edge.x1 + PAGE_MARGIN}px; top: {edge.y1 + PAGE_MARGIN}px;"
                            f" width: {mid - edge.x1}px; border-top-width: 1px",
                            f"left: {mid + PAGE_MARGIN}px; top: {top + PAGE_MARGIN}px;"
                            f" height: {bottom - top}px; border-left-width: 1px",
                            f"left: {mid + PAGE_MARGIN}px; top: {edge.y2 + PAGE_MARGIN}px;"
                            f" width: {edge.x2 - mid}px; border-top-width: 1px",
                        ):
                            ui.element("div").style(EDGE_STYLE + style)
                    for item in layout.placed:
                        node = item.node
                        border = LATE_COLOR if node.late else "#b0bec5"
                        box = ui.element("div").style(
                            f"position: absolute; left: {item.x + PAGE_MARGIN}px;"
                            f" top: {item.y + PAGE_MARGIN}px; width: {item.width}px;"
                            f" height: {item.height}px; box-sizing: border-box;"
                            f" border: {2 if node.late else 1}px solid {border};"
                            f" border-left: 5px solid {STATUS_COLORS[node.status]};"
                            " border-radius: 4px; padding: 8px 8px 8px 10px;"
                            " overflow: hidden; cursor: pointer;"
                        )
                        box.mark(f"overview-node-{node.id}")
                        box.on("click", lambda _, n=node: jump(n.first_task_id))
                        with box:
                            for number, text in enumerate(item.lines):
                                ui.label(text).classes(
                                    "" if number < item.name_lines else "text-caption"
                                ).style(
                                    "line-height: 18px; height: 18px; white-space: nowrap"
                                )

        def change(key: str, value: bool) -> None:
            state[key] = bool(value)
            diagram.refresh()

        async def export() -> None:
            await on_pdf(current())

        with ui.row().classes("items-center w-full gap-4"):
            ui.label(f"俯瞰図: {root.name}").classes("text-h6")
            ui.space()
            ui.checkbox(
                "タスクの詳細",
                value=False,
                on_change=lambda e: change("tasks", e.value),
            ).mark("overview-tasks")
            ui.checkbox(
                "進捗", value=True, on_change=lambda e: change("progress", e.value)
            ).mark("overview-progress")
            ui.checkbox(
                "工数・完了予定",
                value=True,
                on_change=lambda e: change("effort", e.value),
            ).mark("overview-effort")
            ui.button("PDF に出力", icon="picture_as_pdf", on_click=export).props(
                "flat"
            ).mark("overview-pdf")
            ui.button(icon="close", on_click=dialog.close).props("flat round")
        diagram()
    dialog.open()
