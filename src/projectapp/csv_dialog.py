"""CSV・TSV の取り込みと書き出しのダイアログ(列の対応・プロファイルの保存)。"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, replace

from nicegui import background_tasks, ui

from projectapp.csv_import import CsvImportError, cell_ok, sniff_table
from projectapp.csv_profile import (
    EXPORT_FIELDS,
    MAX_HEADER,
    IMPORT_FIELDS,
    header_key,
    SMARTSHEET,
    CsvColumn,
    CsvField,
    CsvProfile,
    best_profile,
    FIELD_LABELS,
    guess_columns,
    resolve_columns,
    split_template,
    template_fields,
    template_problem,
    validate_profile,
)
from projectapp.csv_import_chips import ImportChips
from projectapp.forms import disposable
from projectapp.template_builder_view import ColumnBuilder, TemplateBuilder

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
KEEP_OPTIONS = {False: "区切りも消す", True: "区切りは残す"}
SUMMARY_OPTIONS = {False: "書かない", True: "行として書く"}
SECTION_OPTIONS = {
    "row": "行として書く",
    "none": "書かない",
    "breadcrumb": "タイトルの手前に階層を付ける",
}
PERCENT_OPTIONS = {True: "% あり(50%)", False: "% なし(50)"}
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
    templates: dict[CsvField, str] = {}  # 書式の最初の項目 → 書式
    state = {"name": GUESS_NAME, "date": "ymd-dash", "breadcrumb": False}

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
    templates.update({c.field: c.template for c in first.columns if c.template})
    state["date"] = first.date_format
    state["breadcrumb"] = first.title_breadcrumb

    with (
        disposable(ui.dialog()) as dialog,
        ui.card().classes("w-[46rem] max-w-full") as card,
    ):
        dialog.mark("csv-import-dialog")
        ui.label("CSV・TSV の取り込み").classes("text-h6")
        with ui.row().classes("items-end w-full"):
            profile_select = (
                ui.select(names(), label="プロファイル", value=state["name"])
                .classes("min-w-[12rem]")
                .mark("csv-profile")
            )
            delimiter_select = (
                ui.select(DELIMITER_OPTIONS, label="区切り", value=sniff.delimiter)
                .classes("min-w-[12rem]")
                .mark("csv-delimiter")
            )
            encoding_select = (
                ui.select(ENCODING_OPTIONS, label="文字コード", value=sniff.encoding)
                .classes("min-w-[12rem]")
                .mark("csv-encoding")
            )
            header_input = ui.number(
                "見出しの行", value=sniff.header_row + 1, min=1, precision=0
            ).mark("csv-header-row")
            owner_sep = (
                ui.select(
                    OWNER_SEPARATOR_OPTIONS,
                    label="担当の区切り",
                    value=first.owner_separator,
                )
                .classes("min-w-[12rem]")
                .mark("csv-owner-sep")
            )

        def header_of_column(index: int) -> str:
            return sniff.header[index] if index < len(sniff.header) else ""

        chips = ImportChips(
            IMPORT_FIELDS,
            mapping,
            templates,
            header_of_column,
            lambda: bool(state["breadcrumb"]),
            on_pick=lambda f: pick_column(f),
            on_remove=lambda f: choose(f, UNASSIGNED),
            on_format=lambda f: open_format(f),
            on_clear_format=lambda f: clear_format(f),
        )

        def column_options() -> dict[int, str]:
            seen: set[str] = set()
            options: dict[int, str] = {}
            for i, cell in enumerate(sniff.header):
                key = header_key(cell)
                if key and key in seen:
                    continue  # 同じ見出しの 2 列目は、取り込みが 1 列目を読むので選ばせない
                seen.add(key)
                options[i] = f"{i + 1}: {cell}"
            return options

        def pick_column(field: CsvField) -> None:
            """項目に割り当てる列を選ぶ小さなダイアログ。"""
            with card, disposable(ui.dialog()) as sub, ui.card():
                ui.label(f"「{FIELD_LABELS[field]}」の列を選ぶ").classes("text-h6")
                column = (
                    ui.select(column_options(), label="列", value=mapping.get(field))
                    .classes("min-w-[14rem]")
                    .mark("csv-pick-select")
                )

                def accept() -> None:
                    if isinstance(column.value, int):
                        choose(field, column.value)
                    sub.close()

                with ui.row().classes("justify-end w-full"):
                    ui.button("キャンセル", on_click=sub.close).props("flat").mark(
                        "csv-pick-cancel"
                    )
                    ui.button("決定", on_click=accept).mark("csv-pick-ok")
            sub.open()

        def open_format(anchor: CsvField | None) -> None:
            """書式の列(複数の項目を 1 列にまとめる)と、タイトルの階層の読み方を決める。"""
            current = templates.get(anchor, "") if anchor else ""
            with (
                card,
                disposable(ui.dialog()) as sub,
                ui.card().classes("min-w-[32rem]").mark("csv-fmt-dialog"),
            ):
                ui.label("書式の列").classes("text-h6")
                column = (
                    ui.select(
                        column_options(),
                        label="読み込む列(書式を使うとき)",
                        value=mapping.get(anchor) if anchor else None,
                    )
                    .classes("min-w-[14rem]")
                    .mark("csv-fmt-column")
                )
                made = {"text": current}
                TemplateBuilder(
                    current,
                    IMPORT_FIELDS,
                    lambda text: made.update(text=text),
                    mark="csv-tb",
                ).build()
                crumb = ui.checkbox(
                    "タイトルの「 > 」をセクションとして読む",
                    value=bool(state["breadcrumb"]),
                ).mark("csv-fmt-breadcrumb")
                note = ui.label("").classes("text-negative").mark("csv-fmt-note")

                def accept() -> None:
                    text = made["text"].strip()
                    if text:
                        problem = template_problem(text)
                        if problem is None and not isinstance(column.value, int):
                            problem = "読み込む列を選んでください"
                        if problem:
                            note.set_text(problem)
                            return
                        apply_format(anchor, int(column.value), text)
                    elif anchor is not None:
                        clear_format(anchor, refresh=False)
                    state["breadcrumb"] = bool(crumb.value)
                    refresh_state()
                    sub.close()

                with ui.row().classes("justify-end w-full"):
                    ui.button("キャンセル", on_click=sub.close).props("flat").mark(
                        "csv-fmt-cancel"
                    )
                    ui.button("決定", on_click=accept).mark("csv-fmt-ok")
            sub.open()

        def template_part(field: CsvField, text: str) -> str:
            """書式にまとめた列は、その項目の部分だけを返す。"""
            for anchor, template in templates.items():
                if field in template_fields(template):
                    split = (
                        split_template(template, text.strip()) if text.strip() else {}
                    )
                    return (split or {}).get(field, "")
            return text

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
                            text = template_part(f, text)
                            ui.label(text).classes(
                                "w-32 truncate"
                                + ("" if cell_ok(f, text) else " text-negative")
                            )

        chips.build()
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
        chips.refresh()
        preview.refresh()

    def drop_templates_with(field: CsvField) -> None:
        for anchor in [a for a, t in templates.items() if field in template_fields(t)]:
            for other in template_fields(templates.pop(anchor)):
                if other != field and other != anchor:
                    mapping.pop(other, None)

    def clear_format(field: CsvField, refresh: bool = True) -> None:
        """書式を外す(書式で足した割り当ても外れ、先頭の項目の列だけ残る)。"""
        drop_templates_with(field)
        if refresh:
            refresh_state()

    def apply_format(anchor: CsvField | None, index: int, text: str) -> None:
        """書式の列を、書式の項目すべてに割り当てる。前の書式があれば置き換える。"""
        had_template = anchor is not None and anchor in templates
        if anchor is not None:
            drop_templates_with(anchor)
        fields = template_fields(text)
        if anchor is not None and had_template and anchor not in fields:
            mapping.pop(anchor, None)
        for other in fields:
            drop_templates_with(other)
        for other in [f for f, i in mapping.items() if i == index and f not in fields]:
            drop_templates_with(other)
            mapping.pop(other, None)
        for other in fields:
            mapping[other] = index
        templates[fields[0]] = text

    def choose(field: CsvField, value: int) -> None:
        drop_templates_with(field)
        if value == UNASSIGNED:
            mapping.pop(field, None)
        else:
            for other in [f for f, i in mapping.items() if i == value and f != field]:
                drop_templates_with(other)
                mapping.pop(other, None)
            mapping[field] = value
        refresh_state()

    def load_profile(profile: CsvProfile) -> None:
        mapping.clear()
        templates.clear()
        mapping.update(resolve_columns(profile, sniff.header))
        templates.update({c.field: c.template for c in profile.columns if c.template})
        state["date"] = profile.date_format
        owner_sep.set_value(profile.owner_separator)
        state["breadcrumb"] = profile.title_breadcrumb
        refresh_state()

    def current_profile(name: str | None = None) -> CsvProfile:
        absorbed = {
            other
            for anchor, t in templates.items()
            for other in template_fields(t)
            if other != anchor
        }
        columns = tuple(
            CsvColumn(
                f,
                sniff.header[mapping[f]].strip() or FIELD_LABELS[f],
                templates.get(f, ""),
            )
            for f in IMPORT_FIELDS
            if f in mapping and f not in absorbed
        )
        return CsvProfile(
            name or str(profile_select.value or GUESS_NAME),
            columns,
            str(delimiter_select.value),
            str(encoding_select.value),
            state["date"] if isinstance(state["date"], str) else "ymd-dash",
            str(owner_sep.value or ""),
            title_breadcrumb=bool(state["breadcrumb"]),
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
        templates.clear()
        mapping.clear()
        for f, text in texts.items():
            if text in sniff.header:
                mapping[f] = sniff.header.index(text)
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


def open_csv_export_dialog(
    profiles: list[CsvProfile],
    last: str | None,
    on_export: Callable[[CsvProfile], object],
    on_save: Callable[[CsvProfile], str | None],
) -> None:
    """書き出しの列・区切り・文字コード・日付の書式・担当の区切りを決めるダイアログ。`書き出す`で`on_export(プロファイル)`を呼んで閉じる。"""
    saved = list(profiles)

    def known() -> list[CsvProfile]:
        return [SMARTSHEET, *saved]

    def names() -> list[str]:
        return [p.name for p in known()]

    def profile_named(name: str) -> CsvProfile:
        return next((p for p in known() if p.name == name), SMARTSHEET)

    def rows_of(profile: CsvProfile) -> list[dict]:
        used = [
            {"field": c.field, "use": True, "header": c.header}
            for c in profile.columns
            if not c.template
        ]
        rest = [
            {"field": f, "use": False, "header": FIELD_LABELS[f]}
            for f in EXPORT_FIELDS
            if f not in {c.field for c in profile.columns if not c.template}
        ]
        return used + rest

    start = profile_named(last) if last in names() else SMARTSHEET
    rows = rows_of(start)

    def quick_of(profile: CsvProfile) -> dict:
        """保存済みの書式つきの列(最初の 1 つ)を、上部の書式の入力に出す。"""
        column = next((c for c in profile.columns if c.template), None)
        return {
            "on": column is not None,
            "template": column.template if column else "",
            "header": column.header if column else "まとめ",
        }

    quick = quick_of(start)

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[48rem] max-w-full"):
        dialog.mark("csv-export-dialog")
        ui.label("CSV・TSV の書き出し").classes("text-h6")
        with ui.row().classes("items-end w-full"):
            profile_select = (
                ui.select(names(), label="プロファイル", value=start.name)
                .classes("min-w-[12rem]")
                .mark("csv-ex-profile")
            )
            delimiter_select = (
                ui.select(DELIMITER_OPTIONS, label="区切り", value=start.delimiter)
                .classes("min-w-[12rem]")
                .mark("csv-ex-delimiter")
            )
            encoding_select = (
                ui.select(ENCODING_OPTIONS, label="文字コード", value=start.encoding)
                .classes("min-w-[12rem]")
                .mark("csv-ex-encoding")
            )
            date_select = (
                ui.select(DATE_OPTIONS, label="日付の書式", value=start.date_format)
                .classes("min-w-[12rem]")
                .mark("csv-ex-date")
            )
            owner_select = (
                ui.select(
                    OWNER_SEPARATOR_OPTIONS,
                    label="担当の区切り",
                    value=start.owner_separator,
                )
                .classes("min-w-[12rem]")
                .mark("csv-ex-owner-sep")
            )
            percent_select = (
                ui.select(
                    PERCENT_OPTIONS,
                    label="進捗率の書式",
                    value=start.progress_percent,
                )
                .classes("min-w-[12rem]")
                .mark("csv-ex-percent")
            )
            keep_select = (
                ui.select(
                    KEEP_OPTIONS,
                    label="書式で空の項目の区切り",
                    value=start.keep_separators,
                )
                .classes("min-w-[12rem]")
                .mark("csv-ex-keep-sep")
            )
            summary_select = (
                ui.select(
                    SUMMARY_OPTIONS,
                    label="まとめの行",
                    value=start.summary_rows,
                )
                .classes("min-w-[12rem]")
                .mark("csv-ex-summary")
            )
            section_select = (
                ui.select(
                    SECTION_OPTIONS,
                    label="セクション",
                    value=start.section_mode,
                )
                .classes("min-w-[12rem]")
                .mark("csv-ex-section")
            )
        note = ui.label("").classes("text-negative")

        with ui.row().classes("items-end w-full no-wrap"):
            quick_check = ui.checkbox(
                "書式を使う",
                value=quick["on"],
                on_change=lambda e: edit_quick("on", e.value),
            ).mark("csv-ex-quick-on")
            quick_input = (
                ui.input(
                    label="書式(複数の項目を 1 列にまとめる)",
                    value=quick["template"],
                    placeholder="例 {開始日}/{期限}: {タスク名}",
                    on_change=lambda e: edit_quick("template", e.value),
                )
                .classes("grow")
                .mark("csv-ex-quick")
            )

        columns = ColumnBuilder(
            rows, EXPORT_FIELDS, lambda: refresh_state(), mark="csv-ex-cb"
        )

        def set_quick_text(text: str) -> None:
            quick_input.set_value(text)

        builder = TemplateBuilder(
            quick["template"],
            EXPORT_FIELDS,
            set_quick_text,
            header=quick["header"],
            on_header=lambda text: edit_quick("header", text),
            mark="csv-ex-tb",
        )
        builder.build()
        builder.set_enabled(quick["on"])
        quick_input.set_enabled(quick["on"])
        with (
            ui.expansion("列の詳細設定(使う・見出し・並び)", value=False)
            .classes("w-full")
            .mark("csv-ex-details")
        ):
            columns.build()
            columns.set_enabled(not quick["on"])  # 自由書式のあいだは使えない
        with ui.row().classes("justify-end w-full"):
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark(
                "csv-ex-cancel"
            )
            ui.button("プロファイルとして保存…", on_click=lambda: ask_save()).props(
                "flat"
            ).mark("csv-ex-save")
            confirm = ui.button("書き出す", on_click=lambda: do_export()).mark(
                "csv-export-confirm"
            )

    def problem() -> str | None:
        chosen = [r for r in rows if r["use"]]
        if quick["on"]:  # 自由書式は、通常の項目の列に代わる(列の一覧は使わない)
            text = quick["template"].strip()
            if not text:
                return "書式を入力してください"
            found = template_problem(text)
            if found:
                return found
            if len(quick["header"].strip()) > MAX_HEADER:
                return f"見出しは {MAX_HEADER} 文字までです"
            if CsvField.TITLE not in template_fields(text):
                return "書式に{タスク名}を入れてください"
            return None
        fields = [f for c in current_columns() for f in c.fields]
        if CsvField.TITLE not in fields:
            return "タスク名の列を含めてください"
        if len(fields) != len(set(fields)):
            return "同じ項目が二つの列に入っています(書式の項目と、ほかの列を確かめてください)"
        if any(not 1 <= len(str(r["header"]).strip()) <= MAX_HEADER for r in chosen):
            return f"見出しは 1〜{MAX_HEADER} 文字にしてください"
        return None

    def current_columns() -> tuple[CsvColumn, ...]:
        columns = []
        if quick["on"]:
            template = quick_template()
            if not template:
                return ()
            return (
                CsvColumn(
                    template_fields(template)[0], quick["header"].strip(), template
                ),
            )
        for r in rows:
            if not r["use"]:
                continue
            columns.append(CsvColumn(r["field"], str(r["header"]).strip()))
        return tuple(columns)

    def refresh_state() -> None:
        message = problem()
        note.set_text(message or "")
        confirm.set_enabled(message is None)

    def quick_template() -> str:
        text = quick["template"].strip()
        if quick["on"] and text and template_problem(text) is None:
            return text
        return ""

    def edit_quick(key: str, value: str) -> None:
        quick[key] = value if key == "on" else (value or "")
        if key == "template":
            builder.set_template(quick["template"])
        if key == "on":
            columns.set_enabled(not value)
            quick_input.set_enabled(bool(value))
            builder.set_enabled(bool(value))
        refresh_state()

    def current_profile(name: str | None = None) -> CsvProfile:
        columns = current_columns()
        profile = CsvProfile(
            name or str(profile_select.value),
            columns,
            str(delimiter_select.value),
            str(encoding_select.value),
            str(date_select.value),
            str(owner_select.value or ""),
            progress_percent=bool(percent_select.value),
            keep_separators=bool(keep_select.value),
            summary_rows=bool(summary_select.value),
            section_mode=str(section_select.value),
        )
        same = (
            columns == SMARTSHEET.columns
            and profile.delimiter == SMARTSHEET.delimiter
            and profile.encoding == SMARTSHEET.encoding
            and profile.date_format == SMARTSHEET.date_format
            and profile.owner_separator == SMARTSHEET.owner_separator
            and profile.progress_percent == SMARTSHEET.progress_percent
            and profile.keep_separators == SMARTSHEET.keep_separators
            and profile.summary_rows == SMARTSHEET.summary_rows
            and profile.section_mode == SMARTSHEET.section_mode
        )
        return replace(profile, blank_rows=SMARTSHEET.blank_rows if same else 0)

    def on_profile(name: str) -> None:
        profile = profile_named(name)
        rows[:] = rows_of(profile)
        delimiter_select.set_value(profile.delimiter)
        encoding_select.set_value(profile.encoding)
        date_select.set_value(profile.date_format)
        owner_select.set_value(profile.owner_separator)
        percent_select.set_value(profile.progress_percent)
        keep_select.set_value(profile.keep_separators)
        summary_select.set_value(profile.summary_rows)
        section_select.set_value(profile.section_mode)
        quick.update(quick_of(profile))
        quick_check.set_value(quick["on"])
        quick_input.set_value(quick["template"])
        builder.set_template(quick["template"])
        builder.set_header(quick["header"])
        columns.refresh()
        refresh_state()

    def ask_save() -> None:
        def save(name: str) -> None:
            profile = current_profile(name.strip())
            message = validate_profile(profile) or on_save(profile)
            if message:
                ui.notify(message, type="negative")
                return
            saved[:] = [p for p in saved if p.name != profile.name] + [profile]
            profile_select.set_options(names(), value=profile.name)

        current = str(profile_select.value)
        ask_profile_name("" if current == SMARTSHEET.name else current, save, "csv-ex")

    def do_export() -> None:
        if problem() is not None:
            return
        profile = current_profile()
        dialog.close()
        result = on_export(profile)
        if inspect.isawaitable(result):
            background_tasks.create(result)

    profile_select.on_value_change(lambda e: on_profile(e.value))
    refresh_state()
    dialog.open()
