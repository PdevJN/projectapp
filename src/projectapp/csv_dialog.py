"""CSV・TSV の取り込みと書き出しのダイアログ(列の対応・プロファイルの保存)。"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, replace

from nicegui import background_tasks, ui
from nicegui.events import ValueChangeEventArguments

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
    selects: dict[CsvField, ui.select] = {}
    templates: dict[CsvField, str] = {}  # 書式の最初の項目 → 書式
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
    templates.update({c.field: c.template for c in first.columns if c.template})
    state["date"] = first.date_format

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[46rem] max-w-full"):
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
            breadcrumb_check = ui.checkbox(
                "タイトルの「 > 」をセクションとして読む",
                value=first.title_breadcrumb,
            ).mark("csv-title-breadcrumb")

        @ui.refreshable
        def mapping_panel() -> None:
            selects.clear()
            seen: set[str] = set()
            options = {UNASSIGNED: "割り当てなし"}
            for i, cell in enumerate(sniff.header):
                key = header_key(cell)
                if key and key in seen:
                    continue  # 同じ見出しの 2 列目は、取り込みが 1 列目を読むので選ばせない
                seen.add(key)
                options[i] = f"{i + 1}: {cell}"
            with ui.grid(columns=2).classes("w-full"):
                for field in IMPORT_FIELDS:
                    label = FIELD_LABELS[field] + (
                        "(必須)" if field is CsvField.TITLE else ""
                    )
                    with ui.row().classes("items-end no-wrap"):
                        selects[field] = (
                            ui.select(
                                options,
                                label=label,
                                value=mapping.get(field, UNASSIGNED),
                                on_change=lambda e, f=field: choose(f, e.value),
                            )
                            .classes("min-w-[10rem]")
                            .mark(f"csv-map-{field.value}")
                        )
                        template_input = (
                            ui.input(
                                label="書式(任意)",
                                value=templates.get(field, ""),
                                placeholder="{開始日}〜{期限}",
                                on_change=lambda e, f=field: set_template(f, e),
                            )
                            .props("dense")
                            .classes("w-40")
                            .mark(f"csv-template-{field.value}")
                        )
                        ui.button(
                            "組み立て…",
                            on_click=lambda _, box=template_input: open_builder(box),
                        ).props("flat dense").mark(f"csv-build-{field.value}")

        def open_builder(box: ui.input) -> None:
            """書式の欄の中身を、項目と区切りのチップで組み立て直す小さなダイアログ。"""
            with (
                ui.dialog() as sub,
                ui.card().classes("min-w-[32rem]").mark("csv-tb-dialog"),
            ):
                ui.label("書式を組み立てる").classes("text-h6")
                made = {"text": str(box.value or "")}
                tb = TemplateBuilder(
                    made["text"],
                    IMPORT_FIELDS,
                    lambda text: made.update(text=text),
                    mark="csv-tb",
                )
                tb.build()

                def accept() -> None:
                    box.set_value(made["text"])
                    sub.close()

                with ui.row().classes("justify-end w-full"):
                    ui.button("キャンセル", on_click=sub.close).props("flat").mark(
                        "csv-tb-cancel"
                    )
                    ui.button("決定", on_click=accept).mark("csv-tb-ok")
            sub.on("hide", lambda _: sub.delete())
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

    def drop_templates_with(field: CsvField) -> None:
        for anchor in [a for a, t in templates.items() if field in template_fields(t)]:
            for other in template_fields(templates.pop(anchor)):
                if other != field and other != anchor:
                    mapping.pop(other, None)
                    if other in selects:
                        state["updating"] = True
                        selects[other].set_value(UNASSIGNED)
                        state["updating"] = False

    def set_template(field: CsvField, event: ValueChangeEventArguments) -> None:
        """書式を入れると、その列を書式の項目すべてに割り当てる。空にすると、書式で足した割り当てを外す。"""
        sender = event.sender
        text = str(event.value or "").strip()
        for anchor in [a for a, t in templates.items() if a == field]:
            drop_templates_with(anchor)
        if not text:
            sender.props(remove="error")
            refresh_state()
            return
        problem = template_problem(text)
        if problem is None and field not in mapping:
            problem = "先に列を選んでください"
        if problem:
            sender.props(f'error error-message="{problem}"')
            return
        sender.props(remove="error")
        index = mapping[field]
        for other in template_fields(text):
            drop_templates_with(other)
            mapping[other] = index
            if other in selects and other != field:
                state["updating"] = True
                selects[other].set_value(index)
                state["updating"] = False
        templates[template_fields(text)[0]] = text
        refresh_state()

    def choose(field: CsvField, value: int) -> None:
        if state["updating"]:
            return
        drop_templates_with(field)
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
        templates.clear()
        mapping.update(resolve_columns(profile, sniff.header))
        templates.update({c.field: c.template for c in profile.columns if c.template})
        state["date"] = profile.date_format
        owner_sep.set_value(profile.owner_separator)
        breadcrumb_check.set_value(profile.title_breadcrumb)
        mapping_panel.refresh()
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
            title_breadcrumb=bool(breadcrumb_check.value),
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
