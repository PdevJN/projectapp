"""タスクの分解ダイアログ。名前と工数の行を足し引きして、分解を指定する。"""

from collections.abc import Callable

from nicegui import ui

from projectapp.decompose import MAX_PARTS, Part, Settled, default_parts, default_parts_settled
from projectapp.models import MAX_TASK_NAME_LENGTH, Task

MIN_ROWS = 2


def total_text(rows: list[Part], original: float) -> str:
    total = round(sum(part.effort_hours for part in rows), 2)
    if round(original, 2) == total:
        return f"工数の合計 {total:g}h(元の工数と一致)"
    return f"工数の合計 {total:g}h(元の工数 {original:g}h と違います。このまま分解もできます)"


def open_decompose_dialog(
    task: Task,
    section_reason: str | None,
    on_apply: Callable[[list[Part], bool, bool], object],
    settled: Settled | None = None,
) -> ui.dialog:
    """`on_apply(行, 連結する, 新しいセクションにまとめる)`。ValueError なら、閉じずにエラー欄へ出す。
    `section_reason` は、新しいセクションにまとめられない理由(まとめられるなら None)。
    `settled` があれば(実績・進捗度のあるタスク)、1 行目は消し込み(工数=消化分で固定)、残りは「工数 − 消化分」を割る。"""
    min_rows = MIN_ROWS + 1 if settled else MIN_ROWS
    rows = default_parts_settled(task, settled, min_rows) if settled else default_parts(task, MIN_ROWS)
    with ui.dialog().props("persistent") as dialog, ui.card().classes("w-[36rem] max-w-full"):
        ui.label(f"「{task.name}」を分解").classes("text-h6")
        ui.label("元のタスクは「まとめ」として残ります。").classes("text-caption text-grey")
        if settled:
            ui.label(
                "1 行目は消し込みです(実績を引き継いで終了。工数は消化分で固定)。残りの工数を、2 行目以降に割ります。"
            ).classes("text-caption text-grey").mark("decompose-settled-note")
        if task.weekly_crew:
            note = (
                "週ごとの担当は引き継がれません。消し込みの行は全週の担当、残りの行は今日の週の担当になります。"
                if settled
                else "週ごとの担当は引き継がれません。全員が第1週の担当になります。"
            )
            ui.label(note).classes("text-caption text-warning").mark("decompose-weekly-note")
        box = ui.column().classes("w-full gap-1")
        total = ui.label("").classes("text-caption").mark("decompose-total")
        add = ui.button("行を足す", icon="add", on_click=lambda: add_row()).props("flat dense").mark("decompose-add")
        chain = ui.checkbox("順に連結する(前の行を先行にする)", value=True).mark("decompose-chain")
        section = ui.checkbox("新しいセクションにまとめる", value=False).mark("decompose-section")
        if section_reason is not None:
            section.set_enabled(False)
            ui.label(section_reason).classes("text-caption text-grey")
        error = ui.label("").classes("text-negative").mark("decompose-error")

        def set_name(n: int, value: str | None) -> None:
            rows[n] = Part(value or "", rows[n].effort_hours)

        def set_effort(n: int, value: float | None) -> None:
            rows[n] = Part(rows[n].name, value or 0.0)
            total.set_text(total_text(rows, task.effort_hours))

        def redraw() -> None:
            box.clear()
            with box:
                for n, part in enumerate(rows):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        name = ui.input(value=part.name).props(f"dense maxlength={MAX_TASK_NAME_LENGTH}")
                        name.classes("grow").mark(f"decompose-name-{n}")
                        name.on_value_change(lambda e, n=n: set_name(n, e.value))
                        effort = ui.number(value=part.effort_hours, min=0, step=0.5, suffix="h").props("dense")
                        effort.classes("w-28").mark(f"decompose-effort-{n}")
                        effort.on_value_change(lambda e, n=n: set_effort(n, e.value))
                        if settled and n == 0:
                            effort.set_enabled(False)
                            ui.label("消し込み").classes("text-caption text-grey").mark("decompose-settled-0")
                        elif len(rows) > min_rows:
                            ui.button(icon="close", on_click=lambda n=n: remove_row(n)).props(
                                "flat dense round size=sm"
                            ).mark(f"decompose-remove-{n}")
            add.set_enabled(len(rows) < MAX_PARTS)
            total.set_text(total_text(rows, task.effort_hours))

        def add_row() -> None:
            rows.append(Part(f"{task.name[: MAX_TASK_NAME_LENGTH - 3]} {len(rows) + 1}", 0.0))
            redraw()

        def remove_row(n: int) -> None:
            del rows[n]
            redraw()

        def apply() -> None:
            error.set_text("")
            try:
                on_apply(list(rows), bool(chain.value), bool(section.value) and section_reason is None)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            dialog.close()

        redraw()
        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("decompose-cancel")
            ui.button("分解", on_click=apply).mark("decompose-apply")
    dialog.open()
    return dialog
