"""タスクの追加・編集ダイアログ。入力の検証は forms.py の build_task に任せる。"""

from collections.abc import Callable
from datetime import date, datetime, time

from nicegui import ui

from projectapp.forms import (
    bind_picker,
    build_task,
    compose_datetime,
    default_times,
    disposable,
    parse_datetime,
    needs_end_time,
    needs_start_time,
)
from projectapp.models import (
    DEFAULT_DAILY_HOURS,
    DEFAULT_WORK_START,
    MAX_ALLOCATION,
    MIN_ALLOCATION,
    Member,
    Priority,
    Status,
    Task,
)
from projectapp.timeline import combine_rate, computed_end, effort_days

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
    field: ui.input, picker_factory: Callable[[], ui.date | ui.time], icon: str, key: str, fmt: str
) -> None:
    """入力欄の右端のアイコンで、選択部品のダイアログを開く。小さな画面でも切れない。"""
    with ui.dialog() as picker, ui.card():
        bind_picker(picker_factory().mark(f"{key}-picker"), field, fmt)
        ui.button("OK", on_click=picker.close).mark(f"{key}-picker-ok")
    with field.add_slot("append"):
        ui.icon(icon).classes("cursor-pointer").on("click", picker.open).mark(
            f"open-{key}-picker"
        )


class DateTimeFields:
    """開始予定・完了予定・締切を、日付の入力と、側ごとのチェックで出す時刻の入力で受け取る。

    完了予定は、工数があって「手で指定」がオフのときは、算出値を読み取り専用で出す
    (入力欄は隠すだけで、入力済みの値は保つ)。
    """

    def __init__(
        self,
        task: Task,
        work_start: time,
        daily_hours: float,
        holidays: dict[date, str],
        rate: float = 1.0,
    ) -> None:
        default_start, default_end = default_times(work_start)
        self._defaults = {"start": default_start, "end": default_end, "deadline": default_end}
        self._work_start, self._daily_hours, self._holidays = work_start, daily_hours, holidays
        self.effort = task.effort_hours
        self._rate = rate
        with ui.row().classes("w-full no-wrap gap-4"):
            self.start_day, self.start_time, self.use_start_time, _ = self._column(
                "開始予定",
                "start",
                task.planned_start,
                needs_start_time(task.planned_start, work_start),
            )
            self.end_day, self.end_time, self.use_end_time, self.end_editable = self._column(
                "完了予定",
                "end",
                task.planned_end,
                needs_end_time(task.planned_end, work_start),
                header=lambda: self._end_header(task.planned_end_manual),
            )
        self.second_row = ui.row().classes("w-full no-wrap gap-4")
        with self.second_row:
            self.deadline_day, self.deadline_time, self.use_deadline_time, _ = self._column(
                "締切",
                "deadline",
                task.deadline,
                needs_end_time(task.deadline, work_start),
            )
        for key in ("start", "end", "deadline"):
            self._show_time(key, self._use(key).value)
        for widget in (self.start_day, self.start_time, self.deadline_day, self.deadline_time):
            widget.on_value_change(self._refresh_end)
        self.use_start_time.on_value_change(self._refresh_end)
        self.use_deadline_time.on_value_change(self._refresh_end)
        self._refresh_end()

    def _end_header(self, manual: bool) -> None:
        self.manual = ui.checkbox("手で指定", value=manual, on_change=self._refresh_end).mark(
            "task-end-manual"
        )
        self.computed = (
            ui.input("算出値", value="").props("readonly").classes("w-full").mark("task-end-computed")
        )

    def _column(
        self,
        label: str,
        key: str,
        moment: datetime | None,
        use_time: bool,
        header: Callable[[], None] | None = None,
    ) -> tuple[ui.input, ui.input, ui.checkbox, ui.column]:
        default = self._defaults[key]
        with ui.column().classes("flex-1 gap-0"):
            ui.label(label).classes("text-caption text-grey")
            if header is not None:
                header()
            with ui.column().classes("w-full gap-0") as editable:
                day = ui.input("日付", value=moment.strftime("%Y-%m-%d") if moment else "")
                day.classes("w-full").mark(f"task-{key}-date")
                add_picker(day, ui.date, "event", f"{key}-date", "%Y-%m-%d")
                checkbox = ui.checkbox(
                    "時刻を指定",
                    value=use_time,
                    on_change=lambda e, k=key: self._show_time(k, e.value),
                ).mark(f"task-{key}-use-time")
                clock = ui.input(
                    "時刻", value=(moment.time() if moment else default).strftime("%H:%M")
                )
                clock.classes("w-full").mark(f"task-{key}-time")
                add_picker(clock, ui.time, "access_time", f"{key}-time", "%H:%M")
        return day, clock, checkbox, editable

    def _use(self, key: str) -> ui.checkbox:
        return getattr(self, f"use_{key}_time")

    def _time(self, key: str) -> ui.input:
        return getattr(self, f"{key}_time")

    def _show_time(self, key: str, show: bool) -> None:
        """側ごとに時刻入力を出し入れする。隠しても入力の値は保ち、入れ直すと元の値が出る。"""
        self._time(key).set_visibility(show)

    def _clock(self, key: str) -> str:
        """保存と変更判定に使う時刻。チェックのない側は、入力の値ではなく補う時刻を使う。"""
        if self._use(key).value:
            return self._time(key).value or ""
        return self._defaults[key].strftime("%H:%M")

    def set_rate(self, rate: float) -> None:
        self._rate = rate
        self._refresh_end()

    def set_effort(self, value: float | None) -> None:
        self.effort = value or 0.0
        self._refresh_end()

    def _refresh_end(self, _event: object = None) -> None:
        """完了予定の欄を、工数と「手で指定」に合わせて切り替え、算出値を更新する。"""
        has_effort = (self.effort or 0.0) > 0
        computed_mode = has_effort and not self.manual.value
        self.manual.set_visibility(has_effort)
        self.computed.set_visibility(computed_mode)
        self.end_editable.set_visibility(not computed_mode)
        hint = (
            "空なら工数から算出します"
            if has_effort
            else "空なら締切(なければ開始予定の翌日)になります"
        )
        self.end_day.props(f'hint="{hint}"')
        self.computed.set_value(self._computed_text())

    def _computed_text(self) -> str:
        try:
            start = parse_datetime(self.start_text())
            deadline = parse_datetime(self.deadline_text())
        except ValueError:
            return ""
        end = computed_end(
            start,
            self.effort or 0.0,
            self._daily_hours,
            self._work_start,
            self._holidays,
            deadline,
            self._rate,
        )
        return end.strftime("%Y-%m-%d %H:%M") if end else ""

    def start_text(self) -> str:
        return compose_datetime(self.start_day.value or "", self._clock("start"))

    def end_text(self) -> str:
        return compose_datetime(self.end_day.value or "", self._clock("end"))

    def deadline_text(self) -> str:
        return compose_datetime(self.deadline_day.value or "", self._clock("deadline"))

    def state(self) -> tuple[object, ...]:
        """入力の生の値。開いた時点との比較(変更の判定)に使う。隠れた時刻は含めない。"""
        return (
            self.start_day.value or "",
            self._clock("start"),
            self.end_day.value or "",
            self._clock("end"),
            bool(self.manual.value),
            self.deadline_day.value or "",
            self._clock("deadline"),
        )


def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
    on_delete: Callable[[], object] | None = None,
    daily_hours: float = DEFAULT_DAILY_HOURS,
    holidays: dict[date, str] | None = None,
    members: list[Member] | None = None,
) -> ui.dialog:
    initial = task or Task("")
    member_list = list(members or [])
    if initial.assignee and all(m.name != initial.assignee for m in member_list):
        member_list.append(Member(initial.assignee, 1.0))  # 一覧にいない担当者も、保存で失わない
    initial_member = next((m for m in member_list if m.name == initial.assignee), None)
    initial_rate = (
        combine_rate(initial_member.ratio, initial.allocation) if initial_member else 1.0
    )
    with disposable(ui.dialog().props("persistent")) as dialog, ui.card().classes("w-[36rem] max-w-full"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        name = ui.input("名前", value=initial.name).mark("task-name")
        fields = DateTimeFields(initial, work_start, daily_hours, holidays or {}, initial_rate)
        with fields.second_row:
            effort = (
                ui.number("工数(時間)", value=initial.effort_hours, min=0)
                .classes("flex-1")
                .mark("task-effort")
            )
        with ui.row().classes("w-full no-wrap gap-4"):
            assignee = (
                ui.select(
                    {"": "(なし)", **{m.name: m.name for m in member_list}},
                    label="担当者",
                    value=initial.assignee if initial_member else "",
                )
                .classes("flex-1")
                .mark("task-assignee")
            )
            allocation = (
                ui.number(
                    "割り当て率(%)",
                    value=round(initial.allocation * 100, 2),
                    min=MIN_ALLOCATION * 100,
                    max=MAX_ALLOCATION * 100,
                    step=5,
                )
                .classes("flex-1")
                .mark("task-allocation")
            )
        conversion = ui.label("").classes("text-caption text-grey").mark("task-conversion")

        def current_member() -> Member | None:
            return next((m for m in member_list if m.name == assignee.value), None)

        def refresh_conversion(_event: object = None) -> None:
            member = current_member()
            allocation.set_enabled(member is not None)
            fraction = (allocation.value or 100) / 100 if member else 1.0
            rate = combine_rate(member.ratio, fraction) if member else 1.0
            fields.set_rate(rate)
            days = effort_days(effort.value or 0.0, rate, daily_hours) if member else None
            if member is None or days is None:
                conversion.set_text("")
                return
            conversion.set_text(
                f"{effort.value:g}h → {days:.1f}日分"
                f"(相対比率 {member.ratio * 100:g}% × 割り当て {fraction * 100:g}%)"
            )

        def on_effort_change(e: object) -> None:
            fields.set_effort(getattr(e, "value", None))
            refresh_conversion()

        effort.on_value_change(on_effort_change)
        assignee.on_value_change(refresh_conversion)
        allocation.on_value_change(refresh_conversion)
        refresh_conversion()
        priority = PriorityChips(initial.priority)
        status = (
            ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
            .classes("w-full")
            .mark("task-status")
        )
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )
        error = ui.label("").classes("text-negative").mark("form-error")

        def current() -> tuple[object, ...]:
            """入力の現在値。開いた時点と比べて、変更があるかを判定する。"""
            return (
                name.value,
                *fields.state(),
                effort.value,
                priority.value,
                status.value,
                color.value,
                assignee.value,
                allocation.value,
            )

        opened = current()

        def save() -> None:
            error.set_text("")
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    planned_start=fields.start_text(),
                    planned_end=fields.end_text(),
                    planned_end_manual=bool(fields.manual.value),
                    deadline=fields.deadline_text(),
                    effort_hours=effort.value,
                    priority=priority.value,
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                    allocation_percent=allocation.value,
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.dialog() as confirm, ui.card():
            ui.label("編集内容を確定しますか?")

            def confirm_save() -> None:
                confirm.close()
                save()

            def discard() -> None:
                confirm.close()
                dialog.close()

            with ui.row():
                ui.button("保存", on_click=confirm_save).mark("close-save")
                ui.button("破棄して閉じる", on_click=discard).props("flat").mark("close-discard")
                ui.button("編集に戻る", on_click=confirm.close).props("flat").mark("close-back")

        delete_confirm: ui.dialog | None = None
        if task is not None and on_delete is not None:
            handler = on_delete
            with ui.dialog() as delete_confirm, ui.card():
                ui.label(f"「{task.name}」を削除しますか?")

                def delete() -> None:
                    delete_confirm.close()
                    dialog.close()
                    handler()

                with ui.row():
                    ui.button("キャンセル", on_click=delete_confirm.close).props("flat").mark(
                        "delete-cancel"
                    )
                    ui.button("削除", on_click=delete).props("color=negative").mark(
                        "delete-confirm"
                    )

        def request_close() -> None:
            if current() == opened:
                dialog.close()
            else:
                confirm.open()

        dialog.on("escape-key", request_close)  # persistent なので、ESCでは自動で閉じない
        with ui.row().classes("w-full items-center"):
            if delete_confirm is not None:
                ui.button("削除", on_click=delete_confirm.open).props(
                    "flat color=negative"
                ).mark("task-delete")
            ui.space()
            ui.button("キャンセル", on_click=request_close).props("flat").mark("task-cancel")
            ui.button("保存", on_click=save).mark("task-save")
    dialog.open()
    return dialog
