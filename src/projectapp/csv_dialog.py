"""CSV・TSV の取り込みと書き出しのダイアログ(列の対応・プロファイルの保存)。"""

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from projectapp.csv_import import CsvImportError, cell_ok, sniff_table
from projectapp.csv_profile import (
    IMPORT_FIELDS,
    SMARTSHEET,
    CsvColumn,
    CsvField,
    CsvProfile,
    best_profile,
    FIELD_LABELS,
    guess_columns,
    resolve_columns,
    validate_profile,
)
from projectapp.forms import disposable

GUESS_NAME = "推測"  # その場限りの対応(見出しから推測したもの)
UNASSIGNED = -1  # 列のコンボで「割り当てなし」を表す値
DELIMITER_OPTIONS = {",": "カンマ", "\t": "タブ", ";": "セミコロン"}
ENCODING_OPTIONS = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8(BOM 付き)",
    "cp932": "Shift_JIS",
}
DATE_OPTIONS = {
    "ja": "26年 10月 5日",
    "ymd-dash": "2026-10-05",
    "ymd-slash": "2026/10/05",
}
OWNER_SEPARATOR_OPTIONS = {
    ";": ";",
    ",": ",",
    "/": "/",
    "、": "、",
    "": "なし(筆頭のみ)",
}


@dataclass(frozen=True)
class ImportChoice:
    profile: CsvProfile
    delimiter: str
    header_row: int
    encoding: str


def ask_profile_name(
    initial: str, on_name: Callable[[str], object], prefix: str
) -> None:
    """プロファイルの名前を聞く小さなダイアログ。`保存`で`on_name`を呼ぶ(閉じるのは呼び出し側が決める)。"""
    with disposable(ui.dialog()) as dialog, ui.card():
        field = ui.input("プロファイルの名前", value=initial).props("autofocus")
        field.mark(f"{prefix}-save-name")
        with ui.row().classes("justify-end w-full"):
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button(
                "保存", on_click=lambda: (on_name(field.value or ""), dialog.close())
            ).mark(f"{prefix}-save-ok")
    dialog.open()


def open_csv_import_dialog(
    data: bytes,
    profiles: list[CsvProfile],
    last: str | None,
    on_import: Callable[[ImportChoice, str], object],
    on_save: Callable[[CsvProfile], str | None],
) -> None:
    """列の対応を決めるダイアログ。`取り込む`で`on_import(選んだ内容, テキスト)`を呼んで閉じる。"""
    sniff = sniff_table(data)
    saved = list(profiles)
    mapping: dict[CsvField, int] = {}
    selects: dict[CsvField, ui.select] = {}
    state = {"name": GUESS_NAME, "date": "ymd-dash", "updating": False}

    def known() -> list[CsvProfile]:
        return [SMARTSHEET, *saved]

    def profile_named(name: str) -> CsvProfile:
        if name == GUESS_NAME:
            return CsvProfile(
                GUESS_NAME,
                guess_columns(sniff.header),
                sniff.delimiter,
                sniff.encoding,
                "ymd-dash",
                ";",
            )
        return next((p for p in known() if p.name == name), profile_named(GUESS_NAME))

    def names() -> list[str]:
        return [GUESS_NAME, *(p.name for p in known())]

    initial = best_profile(sniff.header, known())
    if initial is not None:
        state["name"] = initial.name
    elif last in names():
        state["name"] = str(last)

    first = profile_named(str(state["name"]))
    mapping.update(resolve_columns(first, sniff.header))
    state["date"] = first.date_format

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[46rem] max-w-full"):
        dialog.mark("csv-import-dialog")
        ui.label("CSV・TSV の取り込み").classes("text-h6")
        with ui.row().classes("items-end w-full"):
            profile_select = ui.select(
                names(), label="プロファイル", value=state["name"]
            ).mark("csv-profile")
            delimiter_select = ui.select(
                DELIMITER_OPTIONS, label="区切り", value=sniff.delimiter
            ).mark("csv-delimiter")
            encoding_select = ui.select(
                ENCODING_OPTIONS, label="文字コード", value=sniff.encoding
            ).mark("csv-encoding")
            header_input = ui.number(
                "見出しの行", value=sniff.header_row + 1, min=1, precision=0
            ).mark("csv-header-row")
            owner_sep = ui.select(
                OWNER_SEPARATOR_OPTIONS,
                label="担当の区切り",
                value=first.owner_separator,
            ).mark("csv-owner-sep")

        @ui.refreshable
        def mapping_panel() -> None:
            selects.clear()
            options = {UNASSIGNED: "割り当てなし"} | {
                i: f"{i + 1}: {cell}" for i, cell in enumerate(sniff.header)
            }
            with ui.grid(columns=2).classes("w-full"):
                for field in IMPORT_FIELDS:
                    label = FIELD_LABELS[field] + (
                        "(必須)" if field is CsvField.TITLE else ""
                    )
                    selects[field] = ui.select(
                        options,
                        label=label,
                        value=mapping.get(field, UNASSIGNED),
                        on_change=lambda e, f=field: choose(f, e.value),
                    ).mark(f"csv-map-{field.value}")

        @ui.refreshable
        def preview() -> None:
            fields = [f for f in IMPORT_FIELDS if f in mapping]
            if CsvField.TITLE not in mapping:
                ui.label("タスク名の列を割り当ててください").classes("text-negative")
                return
            with (
                ui.element("div").classes("w-full overflow-x-auto").mark("csv-preview")
            ):
                with ui.row().classes("no-wrap font-bold"):
                    for f in fields:
                        ui.label(FIELD_LABELS[f]).classes("w-32")
                for row in sniff.rows:
                    with ui.row().classes("no-wrap"):
                        for f in fields:
                            index = mapping[f]
                            text = row[index] if index < len(row) else ""
                            ui.label(text).classes(
                                "w-32 truncate"
                                + ("" if cell_ok(f, text) else " text-negative")
                            )

        mapping_panel()
        preview()
        with ui.row().classes("justify-end w-full"):
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark(
                "csv-cancel"
            )
            ui.button("プロファイルとして保存…", on_click=lambda: ask_save()).props(
                "flat"
            ).mark("csv-save-profile")
            confirm = ui.button("取り込む", on_click=lambda: do_import()).mark(
                "csv-import-confirm"
            )

    def refresh_state() -> None:
        confirm.set_enabled(CsvField.TITLE in mapping)
        preview.refresh()

    def choose(field: CsvField, value: int) -> None:
        if state["updating"]:
            return
        if value == UNASSIGNED:
            mapping.pop(field, None)
        else:
            state["updating"] = True
            try:
                for other in [
                    f for f, i in mapping.items() if i == value and f != field
                ]:
                    mapping.pop(other)
                    if other in selects:
                        selects[other].set_value(UNASSIGNED)
            finally:
                state["updating"] = False
            mapping[field] = value
        refresh_state()

    def load_profile(profile: CsvProfile) -> None:
        mapping.clear()
        mapping.update(resolve_columns(profile, sniff.header))
        state["date"] = profile.date_format
        owner_sep.set_value(profile.owner_separator)
        mapping_panel.refresh()
        refresh_state()

    def current_profile(name: str | None = None) -> CsvProfile:
        columns = tuple(
            CsvColumn(f, sniff.header[mapping[f]].strip() or FIELD_LABELS[f])
            for f in IMPORT_FIELDS
            if f in mapping
        )
        return CsvProfile(
            name or str(profile_select.value or GUESS_NAME),
            columns,
            str(delimiter_select.value),
            str(encoding_select.value),
            state["date"] if isinstance(state["date"], str) else "ymd-dash",
            str(owner_sep.value or ""),
        )

    def resniff() -> None:
        nonlocal sniff
        header_row = int(header_input.value or 1) - 1
        try:
            fresh = sniff_table(
                data,
                str(encoding_select.value),
                str(delimiter_select.value),
                header_row,
            )
        except CsvImportError as exc:
            ui.notify(str(exc), type="negative")
            return
        texts = {
            f: sniff.header[i] for f, i in mapping.items() if i < len(sniff.header)
        }
        sniff = fresh
        mapping.clear()
        for f, text in texts.items():
            if text in sniff.header:
                mapping[f] = sniff.header.index(text)
        mapping_panel.refresh()
        refresh_state()

    def on_profile(name: str) -> None:
        state["name"] = name
        load_profile(profile_named(name))

    def ask_save() -> None:
        def save(name: str) -> None:
            profile = current_profile(name.strip())
            problem = validate_profile(profile) or on_save(profile)
            if problem:
                ui.notify(problem, type="negative")
                return
            saved[:] = [p for p in saved if p.name != profile.name] + [profile]
            profile_select.set_options(names(), value=profile.name)

        ask_profile_name(
            ""
            if state["name"] in (GUESS_NAME, SMARTSHEET.name)
            else str(state["name"]),
            save,
            "csv",
        )

    def do_import() -> None:
        if CsvField.TITLE not in mapping:
            return
        profile = current_profile()
        on_import(
            ImportChoice(
                profile,
                profile.delimiter,
                int(header_input.value or 1) - 1,
                profile.encoding,
            ),
            sniff.text,
        )
        dialog.close()

    profile_select.on_value_change(lambda e: on_profile(e.value))
    for control in (delimiter_select, encoding_select, header_input):
        control.on_value_change(lambda _: resniff())
    refresh_state()
    dialog.open()
