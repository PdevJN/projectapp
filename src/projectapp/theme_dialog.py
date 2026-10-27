"""カスタムテーマの色のダイアログ(プレビュー・適用・キャンセル)。"""

from collections.abc import Callable
from dataclasses import replace

from nicegui import ui

from projectapp.forms import disposable
from projectapp.theme import DEFAULTS, CustomTheme, header_color, normalize_hex, warnings

INVALID_COLOR_MESSAGE = "#RRGGBB の形で入力してください"
COLOR_FIELDS = (
    ("primary", "primary", "theme-primary"),
    ("background", "画面の背景", "theme-background"),
    ("foreground", "文字の色", "theme-foreground"),
)


def color_field(
    label: str, value: str, on_change: Callable[[str | None], object], marker: str, allow_empty: bool = False
) -> ui.input:
    """`#RRGGBB`の入力欄。右の色見本のボタンから、色の選択もできる。`allow_empty`なら空欄も正しい(既定の色)。"""
    field = ui.input(
        label,
        value=value,
        on_change=lambda e: on_change(e.value),
        validation={
            INVALID_COLOR_MESSAGE: lambda v: (allow_empty and not v) or normalize_hex(v or "") is not None
        },
    ).classes("w-full").mark(marker)
    with field.add_slot("append"):
        with ui.button(icon="colorize").props("flat round dense") as swatch:
            ui.color_picker(on_pick=lambda e: field.set_value(e.color))

    def paint(text: str | None) -> None:
        color = normalize_hex(text or "")
        if color is not None:
            swatch.style(f"color: {color}")

    field.on_value_change(lambda e: paint(e.value))
    paint(value)
    return field


def open_theme_dialog(
    initial: CustomTheme,
    on_preview: Callable[[CustomTheme], object],
    on_apply: Callable[[CustomTheme], bool],
    on_cancel: Callable[[], object],
) -> None:
    """色を変えるたびに`on_preview`を呼ぶ。`適用`は`on_apply`が真のときだけ閉じる。適用せずに閉じたら`on_cancel`。"""
    current = initial
    applied = False
    invalid: set[str] = set()
    inputs: dict[str, ui.input] = {}

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[28rem] max-w-full"):
        ui.label("カスタムの色").classes("text-h6")
        base = ui.toggle({"light": "ライト", "dark": "ダーク"}, value=initial.base).mark("theme-base")

        def update(**fields: str | None) -> None:
            nonlocal current
            current = replace(current, **fields)
            show_warnings()
            on_preview(current)

        def edit(key: str, value: str | None) -> None:
            color = normalize_hex(value or "")
            if color is None:
                invalid.add(key)
            else:
                invalid.discard(key)
                update(**{key: color})
            apply_button.set_enabled(not invalid)

        for key, label, marker in COLOR_FIELDS:
            inputs[key] = color_field(label, getattr(initial, key), lambda v, k=key: edit(k, v), marker)

        follow = ui.checkbox("ヘッダーの背景を primary に追従", value=initial.header is None).mark("theme-header-follow")
        header_input = color_field(
            "ヘッダーの背景",
            initial.header or header_color(initial),
            lambda v: edit("header", v) if not follow.value else None,
            "theme-header",
        )
        header_input.set_visibility(initial.header is not None)

        def toggle_follow(event: object) -> None:
            if follow.value:
                invalid.discard("header")
                header_input.set_visibility(False)
                update(header=None)
            else:
                header_input.set_visibility(True)
                edit("header", header_input.value)
            apply_button.set_enabled(not invalid)

        follow.on_value_change(toggle_follow)

        warning_box = ui.column().classes("w-full gap-0").mark("theme-warnings")

        def show_warnings() -> None:
            warning_box.clear()
            with warning_box:
                for text in warnings(current):
                    ui.label(text).classes("text-caption text-orange").mark("theme-warning")

        def switch_base(new_base: str) -> None:
            """基調を替え、背景と文字を、その基調の既定値に入れ替える(primary とヘッダーは残す)。"""
            defaults = DEFAULTS[new_base]
            invalid.discard("background")
            invalid.discard("foreground")
            update(base=new_base, background=defaults.background, foreground=defaults.foreground)
            inputs["background"].set_value(defaults.background)
            inputs["foreground"].set_value(defaults.foreground)
            apply_button.set_enabled(not invalid)

        base.on_value_change(lambda e: switch_base(e.value))

        def reset() -> None:
            nonlocal current
            defaults = DEFAULTS[current.base]
            invalid.clear()
            current = defaults
            for key, _, _ in COLOR_FIELDS:
                inputs[key].set_value(getattr(defaults, key))
            follow.set_value(True)
            header_input.set_value(header_color(defaults))
            current = defaults
            show_warnings()
            on_preview(current)
            apply_button.set_enabled(True)

        def apply() -> None:
            nonlocal applied
            if on_apply(current):
                applied = True
                dialog.close()

        with ui.row().classes("w-full justify-between"):
            ui.button("既定に戻す", on_click=reset).props("flat no-caps").mark("theme-reset")
            with ui.row():
                ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark("theme-cancel")
                apply_button = ui.button("適用", on_click=apply).props("no-caps").mark("theme-apply")
        show_warnings()
        dialog.on_value_change(lambda e: None if e.value or applied else on_cancel())  # ESC・外側クリックも、値が偽になる
    dialog.open()


def open_today_color_dialog(
    initial: str | None,
    on_preview: Callable[[str | None], object],
    on_apply: Callable[[str | None], bool],
    on_cancel: Callable[[], object],
) -> None:
    """今日の線の色のダイアログ。空欄は既定の色(None)。色を変えるたびに`on_preview`を呼ぶ。
    `適用`は`on_apply`が真のときだけ閉じる。適用せずに閉じたら`on_cancel`。"""
    applied = False
    current = initial

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[24rem] max-w-full"):
        ui.label("今日の線の色").classes("text-h6")

        def edit(value: str | None) -> None:
            nonlocal current
            text = (value or "").strip()
            color = normalize_hex(text)
            valid = color is not None or not text
            apply_button.set_enabled(valid)
            if valid:
                current = color
                on_preview(color)

        field = color_field("色", initial or "", edit, "today-color", allow_empty=True)
        ui.label("空欄は既定の色(ライトは赤、ダークは明るい赤)です").classes("text-caption text-grey")

        def apply() -> None:
            nonlocal applied
            if on_apply(current):
                applied = True
                dialog.close()

        with ui.row().classes("w-full justify-between"):
            ui.button("既定に戻す", on_click=lambda: field.set_value("")).props("flat no-caps").mark("today-reset")
            with ui.row():
                ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark("today-cancel")
                apply_button = ui.button("適用", on_click=apply).props("no-caps").mark("today-apply")
        dialog.on_value_change(lambda e: None if e.value or applied else on_cancel())
    dialog.open()
