"""取り込みダイアログの「項目 ← 列」のチップ表示(要望 139)。

割り当て済みの項目をチップで並べ、割り当てていない項目はパレットに並べる(クリックで足す)。
チップのダブルクリックで列を選び直し、×で外す。複数の項目を 1 列にまとめた書式の列と、
タイトルの階層(` > `)を読む設定のタスク名のチップにだけ、右クリックで書式変更を出す。
状態(`mapping`・`templates`)はダイアログが持ち、ここは見せて操作を知らせるだけ。
"""

from collections.abc import Callable, Mapping, Sequence

from nicegui import ui

from projectapp.csv_profile import FIELD_LABELS, CsvField, template_fields


def anchors_and_absorbed(
    templates: Mapping[CsvField, str],
) -> tuple[set[CsvField], set[CsvField]]:
    """書式の列の先頭の項目(チップになる)と、それにまとめられた残りの項目(チップにならない)。"""
    absorbed = {
        other
        for anchor, text in templates.items()
        for other in template_fields(text)
        if other != anchor
    }
    return set(templates), absorbed


def chip_label(
    field: CsvField,
    mapping: Mapping[CsvField, int],
    templates: Mapping[CsvField, str],
    header: Callable[[int], str],
    breadcrumb: bool,
) -> str:
    """`項目 ← 3: 見出し`。書式の列は`開始日+期限 ← 4: 期間`、階層を読むタスク名は末尾に`(階層)`。"""
    template = templates.get(field)
    names = [FIELD_LABELS[f] for f in template_fields(template)] if template else []
    text = "+".join(names) if names else FIELD_LABELS[field]
    index = mapping[field]
    label = f"{text} ← {index + 1}: {header(index)}"
    if breadcrumb and field is CsvField.TITLE:
        label += "(階層)"
    return label


class ImportChips:
    def __init__(
        self,
        fields: Sequence[CsvField],
        mapping: Mapping[CsvField, int],
        templates: Mapping[CsvField, str],
        header: Callable[[int], str],
        breadcrumb: Callable[[], bool],
        *,
        on_pick: Callable[[CsvField], object],
        on_remove: Callable[[CsvField], object],
        on_format: Callable[[CsvField | None], object],
        on_clear_format: Callable[[CsvField], object],
        mark: str = "csv-ic",
    ) -> None:
        self.fields = tuple(fields)
        self.mapping = mapping
        self.templates = templates
        self.header = header
        self.breadcrumb = breadcrumb
        self.on_pick = on_pick
        self.on_remove = on_remove
        self.on_format = on_format
        self.on_clear_format = on_clear_format
        self.mark = mark
        self.view = ui.refreshable(self._render)

    def build(self) -> None:
        self.view()

    def refresh(self) -> None:
        self.view.refresh()

    def _render(self) -> None:
        _, absorbed = anchors_and_absorbed(self.templates)
        shown = [f for f in self.fields if f in self.mapping and f not in absorbed]
        with ui.row().classes("items-center w-full gap-1").mark(f"{self.mark}-items"):
            for field in shown:
                self._chip(field)
            if not shown:
                ui.label("下の項目から足してください").classes("text-grey text-caption")
        with ui.row().classes("items-center gap-1"):
            ui.label("項目").classes("text-caption text-grey w-12")
            for field in self.fields:
                if field in self.mapping or field in absorbed:
                    continue
                chip = ui.chip(
                    FIELD_LABELS[field], color="grey-4", text_color="black"
                ).mark(f"{self.mark}-pal-{field.value}")
                chip.on("click", lambda _, f=field: self.on_pick(f))
            add = ui.chip("＋書式の列", color="grey-4", text_color="black").mark(
                f"{self.mark}-pal-format"
            )
            add.on("click", lambda _: self.on_format(None))

    def _chip(self, field: CsvField) -> None:
        has_template = field in self.templates
        special = has_template or (field is CsvField.TITLE and self.breadcrumb())
        chip = (
            ui.chip(
                chip_label(
                    field, self.mapping, self.templates, self.header, self.breadcrumb()
                ),
                removable=True,
                color="primary",
                text_color="white",
                on_value_change=lambda e, f=field: (
                    e.value is False and self.on_remove(f)
                ),
            )
            .mark(f"{self.mark}-item-{field.value}")
            .tooltip(
                "ダブルクリックで列を選び直す"
                + ("・右クリックで書式変更" if special else "")
            )
        )
        chip.on("dblclick", lambda _, f=field: self.on_pick(f))
        if special:
            with chip, ui.context_menu():
                ui.menu_item(
                    "書式変更…", on_click=lambda f=field: self.on_format(f)
                ).mark(f"{self.mark}-menu-edit-{field.value}")
                if has_template:
                    ui.menu_item(
                        "書式を解除", on_click=lambda f=field: self.on_clear_format(f)
                    ).mark(f"{self.mark}-menu-clear-{field.value}")
