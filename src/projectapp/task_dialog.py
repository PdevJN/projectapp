"""タスクの追加・編集ダイアログ。入力の検証は forms.py の build_task に任せる。"""

from collections.abc import Callable
from datetime import datetime, time

from nicegui import ui

from projectapp.forms import build_task, compose_datetime, default_times, needs_time
from projectapp.models import DEFAULT_WORK_START, Priority, Status, Task

# 赤は「予定超過」の背景色と意味が競合するため、優先度には使わない
PRIORITY_COLORS = {Priority.HIGH: "orange", Priority.MEDIUM: "amber", Priority.LOW: "blue"}


class PriorityChips:
    """優先度を色付きチップで選ぶ。選択は常に1つで、選択中は塗りつぶし、未選択は枠線のみ。"""

    def __init__(self, value: Priority) -> None:
        self.value = value
        ui.label("優先度").classes("text-caption text-grey")
        self._chips: dict[Priority, ui.chip] = {}
        with ui.row().classes("gap-2"):
            for priority in Priority:
                self._chips[priority] = ui.chip(
                    priority.value,
                    color=PRIORITY_COLORS[priority],
                    on_click=lambda _, p=priority: self.select(p),
                ).mark(f"priority-{priority.name}")
        self._refresh()

    def select(self, priority: Priority) -> None:
        self.value = priority
        self._refresh()

    def _refresh(self) -> None:
        for priority, chip in self._chips.items():
            selected = priority == self.value
            chip.props(remove="outline" if selected else "", add="" if selected else "outline")
            filled_text = "black" if priority == Priority.MEDIUM else "white"  # 黄は白だと読みにくい
            chip.props["text-color"] = filled_text if selected else PRIORITY_COLORS[priority]
            chip.update()


def add_picker(
    field: ui.input, picker_factory: Callable[[], ui.date | ui.time], icon: str, key: str
) -> None:
    """入力欄の右端のアイコンで、選択部品のダイアログを開く。小さな画面でも切れない。"""
    with ui.dialog() as picker, ui.card():
        picker_factory().bind_value(field).mark(f"{key}-picker")
        ui.button("OK", on_click=picker.close).mark(f"{key}-picker-ok")
    with field.add_slot("append"):
        ui.icon(icon).classes("cursor-pointer").on("click", picker.open).mark(
            f"open-{key}-picker"
        )


class DateTimeFields:
    """開始・終了を、日付の入力(横並び)と、チェックで出す時刻の入力で受け取る。"""

    def __init__(self, start: datetime | None, end: datetime | None, work_start: time) -> None:
        default_start, default_end = default_times(work_start)
        self._defaults = {"start": default_start, "end": default_end}
        with ui.row().classes("w-full no-wrap gap-4"):
            self.start_day, self.start_time = self._column("開始", "start", start, default_start)
            self.end_day, self.end_time = self._column("終了", "end", end, default_end)
        self.use_time = ui.checkbox(
            "時刻も指定する",
            value=needs_time(start, end, work_start),
            on_change=lambda e: self._show_times(e.value),
        ).mark("task-use-time")
        self._show_times(self.use_time.value, reset=False)

    @staticmethod
    def _column(
        label: str, key: str, moment: datetime | None, default: time
    ) -> tuple[ui.input, ui.input]:
        with ui.column().classes("flex-1 gap-0"):
            ui.label(label).classes("text-caption text-grey")
            day = ui.input("日付", value=moment.strftime("%Y-%m-%d") if moment else "")
            day.classes("w-full").mark(f"task-{key}-date")
            add_picker(day, ui.date, "event", f"{key}-date")
            clock = ui.input("時刻", value=(moment.time() if moment else default).strftime("%H:%M"))
            clock.classes("w-full").mark(f"task-{key}-time")
            add_picker(clock, ui.time, "access_time", f"{key}-time")
        return day, clock

    def _show_times(self, show: bool, *, reset: bool = True) -> None:
        for key, clock in (("start", self.start_time), ("end", self.end_time)):
            clock.set_visibility(show)
            if not show and reset:
                clock.set_value(self._defaults[key].strftime("%H:%M"))

    def start_text(self) -> str:
        return compose_datetime(self.start_day.value or "", self.start_time.value or "")

    def end_text(self) -> str:
        return compose_datetime(self.end_day.value or "", self.end_time.value or "")

    def state(self) -> tuple[str, str, str, str]:
        """入力の生の値。開いた時点との比較(変更の判定)に使う。"""
        return (
            self.start_day.value or "",
            self.start_time.value or "",
            self.end_day.value or "",
            self.end_time.value or "",
        )


def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
) -> None:
    initial = task or Task("")
    with ui.dialog() as dialog, ui.card().classes("w-[36rem] max-w-full"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        name = ui.input("名前", value=initial.name).mark("task-name")
        fields = DateTimeFields(initial.start, initial.end, work_start)
        effort = ui.number("工数(時間)", value=initial.effort_hours, min=0)
        priority = PriorityChips(initial.priority)
        status = (
            ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
            .classes("w-full")
            .mark("task-status")
        )
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )
        assignee = ui.input("担当者", value=initial.assignee or "")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    start=fields.start_text(),
                    end=fields.end_text(),
                    effort_hours=effort.value,
                    priority=priority.value,
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
