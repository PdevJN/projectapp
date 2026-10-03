"""タスク・セクションの追加・編集の入力検証と、ファイル・名前・設定のダイアログ。"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, time
from decimal import Decimal
from math import isfinite

from nicegui import ui

from projectapp.models import Priority, Status, Task

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"
STANDARD_WORK_HOURS = 8  # 時刻を指定しないときに補う終了の、標準稼働時間(固定)
LUNCH_HOURS = 1  # 同じく、昼休憩(固定。稼働設定の対象外)
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ
MIN_DAILY_HOURS, MAX_DAILY_HOURS = 1.0, 8.0  # 稼働可能時間の範囲
HOURS_RANGE_MESSAGE = f"稼働可能時間は{MIN_DAILY_HOURS:g}以上{MAX_DAILY_HOURS:g}以下で入力してください"
HOURS_DECIMALS = 2  # 稼働時間の小数点以下の桁数(0.25=15分刻みを含む)


def parse_datetime(text: str) -> datetime | None:
    """datetime-local形式を解析する。空はNone、不正・タイムゾーン付きはValueError。"""
    text = text.strip()
    if not text:
        return None
    value = datetime.fromisoformat(text)
    if value.tzinfo is not None:
        raise ValueError("タイムゾーン付きの日時は扱えません")
    return value


def build_task(
    existing: Task | None,
    *,
    name: str,
    start: str,
    end: str,
    effort_hours: float | None,
    priority: Priority,
    status: Status,
    color: str,
    assignee: str,
) -> Task:
    """入力値からTaskを作る。編集時はフォームにない項目を引き継ぐ。"""
    clean = name.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    try:
        start_at, end_at = parse_datetime(start), parse_datetime(end)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    for moment in (start_at, end_at):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    hours = effort_hours or 0.0
    base = existing or Task(clean)
    # ダイアログは日時を分単位で表示するので、同じ分なら既存の終了(秒を含む)を残す
    end_unchanged = existing is not None and format_datetime(existing.end) == end.strip()
    inputs_changed = existing is not None and (
        format_datetime(existing.start) != start.strip() or hours != existing.effort_hours
    )
    # 自動算出の終了は、開始か工数を変えたら捨てて、保存時に算出し直す
    recompute = base.end_auto and end_unchanged and inputs_changed
    if start_at and end_at and end_at < start_at and not recompute:
        raise ValueError("終了は開始以降の日時にしてください")
    if hours < 0:
        raise ValueError("工数は0以上で入力してください")
    return replace(
        base,
        name=clean,
        start=start_at,
        end=None if recompute else (existing.end if existing and end_unchanged else end_at),
        end_auto=base.end_auto and end_unchanged and not inputs_changed,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignee=assignee.strip() or None,
    )


def in_hours_range(hours: float) -> bool:
    return MIN_DAILY_HOURS <= hours <= MAX_DAILY_HOURS


def exceeds_decimals(hours: float) -> bool:
    """小数点以下がHOURS_DECIMALS桁を超えるか。入力どおりの10進数で桁数を数える。"""
    exact = Decimal(repr(hours))
    return exact != exact.quantize(Decimal(1).scaleb(-HOURS_DECIMALS))


def build_work_settings(hours: float | None, start: str) -> tuple[float, time]:
    """稼働可能時間と始業時刻の入力を検証する。"""
    if hours is None:
        raise ValueError("稼働可能時間を入力してください")
    if not isfinite(hours) or not in_hours_range(hours):
        raise ValueError(HOURS_RANGE_MESSAGE)
    if exceeds_decimals(hours):
        raise ValueError(f"稼働可能時間は小数点以下{HOURS_DECIMALS}桁までで入力してください")
    try:
        work_start = datetime.strptime(start.strip(), "%H:%M").time()
    except ValueError:
        raise ValueError("始業時刻はHH:MMの形式で入力してください") from None
    minutes = work_start.hour * 60 + work_start.minute + hours * 60
    if minutes > 24 * 60 + 1e-9:  # 稼働枠が日をまたぐと算出が曖昧になる
        raise ValueError("始業時刻と稼働可能時間の合計が24時を超えています")
    return hours, work_start


def build_section_name(text: str) -> str:
    clean = text.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    return clean


def format_datetime(moment: datetime | None) -> str:
    return moment.strftime(DATETIME_FORMAT) if moment else ""


def default_times(work_start: time) -> tuple[time, time]:
    """時刻を指定しないときに補う開始・終了の時刻。終了は始業 + 標準稼働時間 + 昼休憩。"""
    start = work_start.replace(second=0, microsecond=0)
    minutes = start.hour * 60 + start.minute + (STANDARD_WORK_HOURS + LUNCH_HOURS) * 60
    minutes = min(minutes, 24 * 60 - 1)  # 暫定: 24時以降は表せないので23:59で頭打ち(保留事項)
    return start, time(minutes // 60, minutes % 60)


def compose_datetime(day: str, clock: str) -> str:
    """日付と時刻の入力から、build_taskに渡す文字列を作る。日付が空なら空(時刻は無視する)。"""
    day, clock = day.strip(), clock.strip()
    if not day:
        return ""
    try:
        datetime.strptime(clock, "%H:%M")
    except ValueError:
        raise ValueError("時刻の形式が正しくありません") from None
    return f"{day}T{clock}"


def needs_time(start: datetime | None, end: datetime | None, work_start: time) -> bool:
    """開始・終了が、補う時刻と違うか。違えば、ダイアログは時刻の入力を開いた状態で出す。"""
    default_start, default_end = default_times(work_start)

    def minute(moment: datetime) -> time:
        return moment.time().replace(second=0, microsecond=0)

    return (start is not None and minute(start) != default_start) or (
        end is not None and minute(end) != default_end
    )


def open_section_dialog(on_save: Callable[[str], object]) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("セクションの追加").classes("text-h6")
        name = ui.input("セクション名").mark("section-name")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_section_name(name.value or "")
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("section-save")
    dialog.open()


def open_name_dialog(
    on_submit: Callable[[str], object], validate: Callable[[str], str | None]
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("プロジェクトの保存").classes("text-h6")
        name = ui.input("プロジェクト名").mark("project-name")
        error = ui.label("").classes("text-negative").mark("name-error")

        def save() -> None:
            clean = (name.value or "").strip()
            if message := validate(clean):
                error.set_text(message)
                return
            on_submit(clean)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("name-save")
    dialog.open()


def open_file_dialog(names: list[str], on_select: Callable[[str], object]) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("プロジェクトを開く").classes("text-h6")
        if not names:
            ui.label("プロジェクトファイルがありません")

        def choose(name: str) -> None:
            dialog.close()
            on_select(name)

        with ui.column().classes("w-full gap-1"):
            for index, name in enumerate(names):
                ui.button(name, on_click=lambda n=name: choose(n)).props(
                    "flat align=left"
                ).classes("w-full").mark(f"file-{index}")
        ui.button("キャンセル", on_click=dialog.close).props("flat")
    dialog.open()


def open_unsaved_dialog(
    on_save: Callable[[], object], on_discard: Callable[[], object]
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("保存されていない変更があります").classes("text-h6")
        ui.label("開く前に、現在のプロジェクトを保存しますか。")

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("unsaved-cancel")
            ui.button("保存せず開く", on_click=lambda: run(on_discard)).props(
                "flat color=negative"
            ).mark("unsaved-discard")
            ui.button("保存して開く", on_click=lambda: run(on_save)).mark("unsaved-save")
    dialog.open()


def open_settings_dialog(
    daily_hours: float,
    work_start: time,
    on_apply: Callable[[float, time], object],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("稼働時間の設定").classes("text-h6")
        hours = ui.number(
            "1日の稼働可能時間(h)",
            value=daily_hours,
            min=MIN_DAILY_HOURS,
            max=MAX_DAILY_HOURS,
            step=0.5,
            validation={
                HOURS_RANGE_MESSAGE: lambda v: v is None or (isfinite(v) and in_hours_range(v)),
                f"小数点以下{HOURS_DECIMALS}桁までで入力してください": lambda v: (
                    v is None or not isfinite(v) or not exceeds_decimals(v)
                ),
            },
        ).classes("w-full").mark("settings-hours")
        start = ui.input("始業時刻", value=work_start.strftime("%H:%M")).classes(
            "w-full"
        ).mark("settings-start")
        with ui.dialog() as picker, ui.card():  # 小さな画面でも切れないよう、中央のダイアログにする
            ui.time().bind_value(start).mark("settings-time-picker")
            ui.button("OK", on_click=picker.close).mark("time-picker-ok")
        with start.add_slot("append"):
            ui.icon("access_time").classes("cursor-pointer").on("click", picker.open).mark(
                "open-time-picker"
            )
        error = ui.label("").classes("text-negative").mark("settings-error")

        def apply() -> None:
            try:
                result = build_work_settings(hours.value, start.value or "")
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_apply(*result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("settings-apply")
    dialog.open()
