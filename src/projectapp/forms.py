"""タスク・セクションの追加・編集の入力検証と、ファイル・名前・設定のダイアログ。"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, time
from decimal import Decimal
from math import isfinite

from nicegui import ui

from projectapp.models import Priority, Status, Task, is_hex_color

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"
STANDARD_WORK_HOURS = 8  # 時刻を指定しないときに補う終了の、標準稼働時間(固定)
LUNCH_HOURS = 1  # 同じく、昼休憩(固定。稼働設定の対象外)
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ
MIN_DAILY_HOURS, MAX_DAILY_HOURS = 1.0, 8.0  # 稼働可能時間の範囲
HOURS_RANGE_MESSAGE = f"稼働可能時間は{MIN_DAILY_HOURS:g}以上{MAX_DAILY_HOURS:g}以下で入力してください"
HOURS_DECIMALS = 2  # 稼働時間の小数点以下の桁数(0.25=15分刻みを含む)


def disposable(dialog: ui.dialog) -> ui.dialog:
    """閉じたら要素ごと取り除く。開くたびに新しく作るダイアログが、閉じても溜まらないようにする。"""
    dialog.on("hide", dialog.delete)
    return dialog


def bind_picker(picker: ui.date | ui.time, field: ui.input, fmt: str) -> None:
    """入力欄と選択部品の値をそろえる。入力途中の(形式に合わない)文字列は部品に渡さない。"""

    def valid_or_none(text: str | None) -> str | None:
        try:
            datetime.strptime(text or "", fmt)
        except ValueError:
            return None
        return text

    picker.bind_value_from(field, backward=valid_or_none)
    picker.bind_value_to(field, forward=lambda value: value if value else field.value)


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
    planned_start: str,
    planned_end: str,
    planned_end_manual: bool = False,
    deadline: str | None = None,
    effort_hours: float | None,
    priority: Priority,
    status: Status,
    color: str,
    assignee: str,
) -> Task:
    """入力値からTaskを作る。編集時はフォームにない項目を引き継ぐ。

    deadlineがNoneのときは既存の締切を保つ(空文字は締切なし)。
    """
    clean = name.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    try:
        start_at, end_at = parse_datetime(planned_start), parse_datetime(planned_end)
        deadline_at = parse_datetime(deadline) if deadline is not None else None
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    for moment in (start_at, end_at, deadline_at):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    hours = effort_hours or 0.0
    if not isfinite(hours) or hours < 0:
        raise ValueError("工数は0以上の数値で入力してください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    manual = planned_end_manual and hours > 0
    uses_planned_end = hours <= 0 or manual  # 工数ありで手指定なしの値は、使われないので検証しない
    if uses_planned_end and start_at and end_at and end_at < start_at:
        raise ValueError("完了予定は開始予定以降の日時にしてください")
    base = existing or Task(clean)
    return replace(
        base,
        name=clean,
        planned_start=start_at,
        planned_end=end_at,
        planned_end_manual=manual,
        deadline=base.deadline if deadline is None else deadline_at,
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
        day = datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d")  # 2026-10-5 を正規化する
    except ValueError:
        pass  # 形式の誤りは build_task が報告する
    try:
        datetime.strptime(clock, "%H:%M")
    except ValueError:
        raise ValueError("時刻の形式が正しくありません") from None
    return f"{day}T{clock}"


def _minute(moment: datetime) -> time:
    return moment.time().replace(second=0, microsecond=0)


def needs_start_time(start: datetime | None, work_start: time) -> bool:
    """開始が、補う時刻(始業時刻)と違うか。違えば、ダイアログは開始の時刻入力を開いた状態で出す。"""
    return start is not None and _minute(start) != default_times(work_start)[0]


def needs_end_time(end: datetime | None, work_start: time) -> bool:
    """終了が、補う時刻と違うか。自動算出の終了(例: 15:30)も、違えば開いた状態で出す。"""
    return end is not None and _minute(end) != default_times(work_start)[1]


def open_section_dialog(on_save: Callable[[str], object]) -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
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
    """名前を入力して保存する。on_submitがFalseを返したら(保存に失敗)、入力を残して開いたままにする。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label("プロジェクトの保存").classes("text-h6")
        name = ui.input("プロジェクト名").mark("project-name")
        error = ui.label("").classes("text-negative").mark("name-error")

        def save() -> None:
            clean = (name.value or "").strip()
            if message := validate(clean):
                error.set_text(message)
                return
            if on_submit(clean) is False:
                return
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("name-save")
    dialog.open()


def open_file_dialog(names: list[str], on_select: Callable[[str], object]) -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
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
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
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
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
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
            bind_picker(ui.time().mark("settings-time-picker"), start, "%H:%M")
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
