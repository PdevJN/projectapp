"""タスク・セクションの追加・編集ダイアログと入力検証。"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from nicegui import ui

from projectapp.models import Priority, Status, Task

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"
MIN_YEAR, MAX_YEAR = 2000, 2100  # 入力ミスで表示範囲が際限なく広がるのを防ぐ


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
    if start_at and end_at and end_at < start_at:
        raise ValueError("終了は開始以降の日時にしてください")
    hours = effort_hours or 0.0
    if hours < 0:
        raise ValueError("工数は0以上で入力してください")
    return replace(
        existing or Task(clean),
        name=clean,
        start=start_at,
        end=end_at,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignee=assignee.strip() or None,
    )


def build_section_name(text: str) -> str:
    clean = text.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    return clean


def _format(moment: datetime | None) -> str:
    return moment.strftime(DATETIME_FORMAT) if moment else ""


def open_task_dialog(task: Task | None, on_save: Callable[[Task], object]) -> None:
    initial = task or Task("")
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        name = ui.input("名前", value=initial.name).mark("task-name")
        start = ui.input("開始日時", value=_format(initial.start)).props(
            "type=datetime-local"
        ).mark("task-start")
        end = ui.input("終了日時", value=_format(initial.end)).props(
            "type=datetime-local"
        ).mark("task-end")
        effort = ui.number("工数(時間)", value=initial.effort_hours, min=0)
        priority = ui.select(
            {p: p.value for p in Priority}, label="優先度", value=initial.priority
        )
        status = ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
        color = ui.color_input("色", value=initial.color)
        assignee = ui.input("担当者", value=initial.assignee or "")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    start=start.value or "",
                    end=end.value or "",
                    effort_hours=effort.value,
                    priority=Priority(priority.value),
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("task-save")
    dialog.open()


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
