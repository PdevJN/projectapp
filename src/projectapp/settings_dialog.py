"""設定の取り込みのダイアログ。区分ごとのチェックと、重複の項目ごとの上書きを選ばせる。"""

from collections.abc import Callable

from nicegui import ui

from projectapp.forms import disposable
from projectapp.settings_io import SECTION_LABELS, ImportPlan


def open_import_dialog(
    plan: ImportPlan, on_apply: Callable[[set[str], set[tuple[str, str]]], object]
) -> None:
    sections: dict[str, ui.checkbox] = {}
    overwrites: dict[tuple[str, str], ui.checkbox] = {}
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[32rem]"):
        ui.label("設定を取り込む").classes("text-h6")
        with ui.column().classes("w-full gap-0"):
            if plan.project_changes:
                sections["project"] = ui.checkbox(
                    SECTION_LABELS["project"], value=True
                ).mark("import-section-project")
                for change in plan.project_changes:
                    ui.label(
                        f"{change.label}: {change.now} → {change.incoming}"
                    ).classes("text-caption q-ml-lg")
            for section in plan.sections:
                title = f"{SECTION_LABELS[section.key]}(追加 {len(section.new)} 件・重複 {len(section.duplicates)} 件)"
                sections[section.key] = ui.checkbox(title, value=True).mark(
                    f"import-section-{section.key}"
                )
                for name in section.new:
                    ui.label(f"追加: {name}").classes("text-caption q-ml-lg")
                for index, name in enumerate(section.duplicates):
                    if section.overwritable:
                        overwrites[(section.key, name)] = (
                            ui.checkbox(f"上書き: {name}")
                            .classes("q-ml-lg")
                            .mark(f"import-overwrite-{section.key}-{index}")
                        )
                    else:
                        ui.label(f"重複(取り込みません): {name}").classes(
                            "text-caption q-ml-lg"
                        )

        def apply() -> None:
            chosen = {key for key, box in sections.items() if box.value}
            picked = {pair for pair, box in overwrites.items() if box.value}
            dialog.close()
            on_apply(chosen, picked)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark(
                "import-cancel"
            )
            ui.button("取り込む", on_click=apply).mark("import-apply")
    dialog.open()
