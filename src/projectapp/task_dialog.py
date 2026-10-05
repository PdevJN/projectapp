"""タスクの追加・編集ダイアログ。入力の検証は forms.py の build_task に任せる。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time

from nicegui import ui

from projectapp.forms import (
    ActualRow,
    bind_picker,
    build_task,
    compose_actual,
    compose_datetime,
    default_times,
    disposable,
    parse_datetime,
    needs_end_time,
    needs_start_time,
    suggest_status,
)
from projectapp.models import (
    DEFAULT_DAILY_HOURS,
    DEFAULT_WORK_START,
    MAX_ALLOCATION,
    MAX_PROGRESS,
    MIN_ALLOCATION,
    MIN_PROGRESS,
    Actual,
    ActualMode,
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


def moment_column(
    label: str, mark: str, picker: str, moment: datetime | None
) -> tuple[ui.input, ui.input]:
    """実績の日付と時刻の入力の組。マーカーは `{mark}-date` と `{mark}-time`。"""
    with ui.column().classes("flex-1 gap-0"):
        day = ui.input(f"{label}の日付", value=moment.strftime("%Y-%m-%d") if moment else "")
        day.classes("w-full").mark(f"{mark}-date")
        add_picker(day, ui.date, "event", f"{picker}-date", "%Y-%m-%d")
        clock = ui.input(f"{label}の時刻", value=moment.strftime("%H:%M") if moment else "")
        clock.classes("w-full").mark(f"{mark}-time")
        add_picker(clock, ui.time, "access_time", f"{picker}-time", "%H:%M")
    return day, clock


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


def _parses(day: str | None, clock: str | None) -> bool:
    """日付と時刻が、どちらも完成した形式か。入力の途中の値で状態を提案しないために使う。"""
    try:
        datetime.strptime((day or "").strip(), "%Y-%m-%d")
        datetime.strptime((clock or "").strip(), "%H:%M")
    except ValueError:
        return False
    return True


class ActualFields:
    """実績の開始・終了。日付と時刻を両方入れる(補う時刻はない)。2件以上の実績は編集できない。"""

    def __init__(self, task: Task) -> None:
        self.read_only = len(task.actuals) > 1
        ui.label("実績").classes("text-caption text-grey")
        if self.read_only:
            ui.label("複数の区間があるため、このバージョンでは編集できません").classes(
                "text-caption"
            ).mark("task-actuals-readonly")
            return
        actual = task.actuals[0] if task.actuals else None
        with ui.row().classes("w-full no-wrap gap-4"):
            self.start_day, self.start_time = self._column(
                "開始", "start", actual.start if actual else None
            )
            self.end_day, self.end_time = self._column(
                "終了", "end", actual.end if actual else None
            )
        self.progress = (
            ui.number(
                "進捗度(%)",
                value=actual.progress if actual else None,
                min=MIN_PROGRESS,
                max=MAX_PROGRESS,
                precision=0,
            )
            .classes("w-full")
            .mark("task-actual-progress")
        )

    def _column(self, label: str, key: str, moment: datetime | None) -> tuple[ui.input, ui.input]:
        return moment_column(label, f"task-actual-{key}", f"actual-{key}", moment)

    def bind(self, callback: Callable[[object], None]) -> None:
        """入力が変わったときに呼ぶ関数を、すべての入力に付ける。"""
        for widget in self.inputs():
            widget.on_value_change(callback)

    def inputs(self) -> list[ui.input | ui.number]:
        if self.read_only:
            return []
        return [self.start_day, self.start_time, self.end_day, self.end_time, self.progress]

    def progress_value(self) -> float | None:
        if self.read_only:
            return None
        return self.progress.value

    def start_text(self) -> str:
        if self.read_only:
            return ""
        return compose_actual(self.start_day.value or "", self.start_time.value or "")

    def end_text(self) -> str:
        if self.read_only:
            return ""
        return compose_actual(self.end_day.value or "", self.end_time.value or "")

    def filled(self) -> tuple[bool, bool]:
        """開始・終了の日付と時刻がそろっているか(状態の提案に使う)。"""
        if self.read_only:
            return False, False
        return (
            _parses(self.start_day.value, self.start_time.value),
            _parses(self.end_day.value, self.end_time.value),
        )

    def state(self) -> tuple[object, ...]:
        """変更の判定に使う入力値。進捗度は 0 と空を区別する。"""
        texts = tuple(widget.value or "" for widget in self.inputs()[:4])
        return (*texts, None if self.read_only else self.progress.value)


@dataclass
class IntervalRow:
    card: ui.card
    start_day: ui.input
    start_time: ui.input
    end_day: ui.input
    end_time: ui.input
    progress: ui.number


class IntervalFields:
    """実績の区間を、行を足していく形で入力する(記録方式が「区間」のとき)。
    ActualFields と同じ呼び出し口(bind / filled / progress_value / state)にそろえる。
    状態の提案は、最後の行で判定する。"""

    read_only = False

    def __init__(self, task: Task) -> None:
        self._rows: list[IntervalRow] = []
        self._counter = 0  # マーカーの番号。行を削除しても詰めない
        self._on_change: Callable[[object], None] | None = None
        ui.label("実績(区間)").classes("text-caption text-grey")
        self._container = ui.column().classes("w-full gap-2")
        for actual in task.actuals:
            self._add_row(actual)
        ui.button("区間を追加", icon="add", on_click=lambda: self._add_row(None)).props(
            "flat dense"
        ).mark("task-interval-add")

    def _add_row(self, actual: Actual | None) -> None:
        n = self._counter
        self._counter += 1
        with self._container:
            with ui.card().classes("w-full").props("flat bordered") as card:
                with ui.row().classes("w-full no-wrap gap-4"):
                    start_day, start_time = moment_column(
                        "開始",
                        f"task-interval-{n}-start",
                        f"interval-{n}-start",
                        actual.start if actual else None,
                    )
                    end_day, end_time = moment_column(
                        "終了",
                        f"task-interval-{n}-end",
                        f"interval-{n}-end",
                        actual.end if actual else None,
                    )
                progress = (
                    ui.number(
                        "進捗度(%)",
                        value=actual.progress if actual else None,
                        min=MIN_PROGRESS,
                        max=MAX_PROGRESS,
                        precision=0,
                    )
                    .classes("w-full")
                    .mark(f"task-interval-{n}-progress")
                )
                ui.button(
                    "削除", icon="delete", on_click=lambda c=card: self._remove(c)
                ).props("flat dense color=negative").mark(f"task-interval-{n}-remove")
        row = IntervalRow(card, start_day, start_time, end_day, end_time, progress)
        self._rows.append(row)
        if self._on_change is not None:
            for widget in self._widgets(row):
                widget.on_value_change(self._on_change)
            self._on_change(None)

    def _remove(self, card: ui.card) -> None:
        self._rows = [row for row in self._rows if row.card is not card]
        card.delete()
        if self._on_change is not None:
            self._on_change(None)

    @staticmethod
    def _widgets(row: IntervalRow) -> list[ui.input | ui.number]:
        return [row.start_day, row.start_time, row.end_day, row.end_time, row.progress]

    def bind(self, callback: Callable[[object], None]) -> None:
        self._on_change = callback
        for widget in self.inputs():
            widget.on_value_change(callback)

    def inputs(self) -> list[ui.input | ui.number]:
        return [widget for row in self._rows for widget in self._widgets(row)]

    def rows(self) -> list[ActualRow]:
        """保存用の入力。日付と時刻の片方だけの行は、「区間 N: …」のエラーにする(N は現在の位置)。"""
        result: list[ActualRow] = []
        for number, row in enumerate(self._rows, start=1):
            try:
                start = compose_actual(row.start_day.value or "", row.start_time.value or "")
                end = compose_actual(row.end_day.value or "", row.end_time.value or "")
            except ValueError as exc:
                raise ValueError(f"区間 {number}: {exc}") from None
            result.append((start, end, row.progress.value))
        return result

    def start_text(self) -> str:
        return ""  # 区間は rows() を使う

    def end_text(self) -> str:
        return ""  # 区間は rows() を使う

    def filled(self) -> tuple[bool, bool]:
        """最後の区間の、開始・終了の日付と時刻がそろっているか(状態の提案に使う)。"""
        if not self._rows:
            return False, False
        last = self._rows[-1]
        return (
            _parses(last.start_day.value, last.start_time.value),
            _parses(last.end_day.value, last.end_time.value),
        )

    def progress_value(self) -> float | None:
        return self._rows[-1].progress.value if self._rows else None

    def state(self) -> tuple[object, ...]:
        """変更の判定に使う入力値。行の数と、各行の値(進捗度は 0 と空を区別する)。"""
        values: list[object] = [len(self._rows)]
        for row in self._rows:
            values += [
                row.start_day.value or "",
                row.start_time.value or "",
                row.end_day.value or "",
                row.end_time.value or "",
                row.progress.value,
            ]
        return tuple(values)


def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
    on_delete: Callable[[], object] | None = None,
    daily_hours: float = DEFAULT_DAILY_HOURS,
    holidays: dict[date, str] | None = None,
    members: list[Member] | None = None,
    actual_mode: ActualMode = ActualMode.SIMPLE,
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
        project_code = (
            ui.input("ProjectCode", value=initial.project_code)
            .classes("w-full")
            .mark("task-project-code")
        )
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
        intervals = actual_mode is ActualMode.INTERVALS
        actual_fields: ActualFields | IntervalFields = (
            IntervalFields(initial) if intervals else ActualFields(initial)
        )
        status = (
            ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
            .classes("w-full")
            .mark("task-status")
        )
        hint = ui.label("").classes("text-caption text-grey").mark("task-status-hint")
        hint.set_visibility(False)
        suggest = {"manual": False, "setting": False}

        def on_status_change(_event: object) -> None:
            if not suggest["setting"]:
                suggest["manual"] = True  # 手で選んだら、以降は提案しない
                hint.set_visibility(False)

        status.on_value_change(on_status_change)

        def on_actual_change(_event: object = None) -> None:
            if suggest["manual"]:
                return
            suggested = suggest_status(
                *actual_fields.filled(), actual_fields.progress_value(), intervals=intervals
            )
            if suggested is None or suggested == status.value:
                return
            suggest["setting"] = True
            try:
                status.set_value(suggested)
            finally:
                suggest["setting"] = False
            hint.set_text("実績に合わせて状態を変えました")
            hint.set_visibility(True)

        actual_fields.bind(on_actual_change)
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )
        error = ui.label("").classes("text-negative").mark("form-error")

        def current() -> tuple[object, ...]:
            """入力の現在値。開いた時点と比べて、変更があるかを判定する。"""
            return (
                name.value,
                project_code.value or "",
                *fields.state(),
                effort.value,
                priority.value,
                status.value,
                color.value,
                assignee.value,
                allocation.value,
                *actual_fields.state(),
            )

        opened = current()

        def save() -> None:
            error.set_text("")
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    project_code=project_code.value or "",
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
                    actual_start=actual_fields.start_text(),
                    actual_end=actual_fields.end_text(),
                    actual_progress=actual_fields.progress_value(),
                    actual_rows=actual_fields.rows() if isinstance(actual_fields, IntervalFields) else None,
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
