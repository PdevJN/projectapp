"""タスクの追加・編集ダイアログ。入力の検証は forms.py の build_task に任せる。"""

import html
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.browser import open_url as default_open_url
from projectapp.categories import UNDECIDED, category_full_label, category_label
from projectapp.dateinput import (
    DATE_FORMAT,
    SHORTCUT_LABELS,
    parse_date_input,
    parse_time_input,
    shortcut_dates,
)
from projectapp.effortunits import PRESET_HOURS, EffortUnit, from_hours, reference_text, to_hours
from projectapp.forms import (
    _build_assignees,
    STANDARD_WORK_HOURS,
    ActualRow,
    UrlRow,
    bind_picker,
    build_task,
    build_urls,
    compose_actual,
    compose_datetime,
    default_times,
    disposable,
    parse_datetime,
    needs_end_time,
    needs_start_time,
    end_gap_hint,
    push_hint,
    suggest_status,
)
from projectapp.models import (
    CHECKPOINT_STATUSES,
    DEFAULT_DAILY_HOURS,
    DEFAULT_WORK_START,
    ID_KEY,
    MAX_ALLOCATION,
    MAX_PROGRESS,
    MAX_TASK_NAME_LENGTH,
    MAX_WEEKS,
    MIN_ALLOCATION,
    MIN_PROGRESS,
    URL_KEY,
    Actual,
    ActualMode,
    Assignee,
    Category,
    Member,
    Parameter,
    Priority,
    Status,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
    has_control_char,
)
from projectapp.ratios import effective_ratio
from projectapp.reassign import needs_review, reviewed_end
from projectapp.timeline import Worker, assignees_rate, combine_rate, computed_end, crew_of, effort_days
from projectapp.workdays import work_day_map
from projectapp.urls import resolve

# 赤は「予定超過」の背景色と意味が競合するため、優先度には使わない
PRIORITY_COLORS = {Priority.HIGH: "orange", Priority.MEDIUM: "amber", Priority.LOW: "blue"}


class EffortField:
    """工数の入力。数値・単位・プリセットのチップ・換算の参考。値(`value`)は、常に時間。
    数値を編集すると時間を持ち直し、単位だけを切り替えたときは、時間を変えずに表示だけを直す。"""

    def __init__(self, hours: float | None, daily_hours: float, standard_hours: float) -> None:
        self._hours = hours
        self._unit = EffortUnit.HOURS
        self._daily = daily_hours
        self._standard = standard_hours
        self._syncing = False
        self._callbacks: list[Callable[[float | None], object]] = []
        with ui.column().classes("flex-1 gap-0 min-w-0") as self.container:
            with ui.row().classes("w-full items-start no-wrap gap-2"):
                self.number = ui.number("工数", value=hours, min=0).classes("flex-1 min-w-0").mark("task-effort")
                self.unit = (
                    ui.select({u: u.value for u in EffortUnit}, value=EffortUnit.HOURS)
                    .classes("w-24")
                    .mark("task-effort-unit")
                )
            with ui.row().classes("w-full items-center no-wrap gap-1"):
                for preset in PRESET_HOURS:
                    ui.chip(f"{preset:g}h", on_click=lambda _e, p=preset: self._set_hours(float(p))).props(
                        "dense clickable outline size=sm"
                    ).mark(f"task-effort-preset-{preset:g}")
            self.reference = ui.label("").classes("text-caption text-grey").mark("task-effort-reference")
        self.number.on_value_change(self._number_changed)
        self.unit.on_value_change(self._unit_changed)

    @property
    def value(self) -> float | None:
        return self._hours

    def on_value_change(self, callback: Callable[[float | None], object]) -> None:
        self._callbacks.append(callback)

    def set_visibility(self, visible: bool) -> None:
        self.container.set_visibility(visible)

    def _notify(self) -> None:
        for callback in self._callbacks:
            callback(self._hours)

    def _number_changed(self, event: ValueChangeEventArguments) -> None:
        if self._syncing:
            return
        self._hours = None if event.value is None else to_hours(event.value, self._unit, self._daily)
        self._update_reference()
        self._notify()

    def _unit_changed(self, event: ValueChangeEventArguments) -> None:
        self._unit = event.value
        self._show_number()
        self._update_reference()

    def _set_hours(self, hours: float) -> None:
        self._hours = hours
        self._show_number()
        self._update_reference()
        self._notify()

    def _show_number(self) -> None:
        self._syncing = True
        try:
            self.number.set_value(None if self._hours is None else from_hours(self._hours, self._unit, self._daily))
        finally:
            self._syncing = False

    def _update_reference(self) -> None:
        self.reference.set_text(reference_text(self._unit, self._daily, self._standard))


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


LAYOUT_LABELS = {"schedule": "予定・実績", "all": "すべて"}

# ESC だけをサーバーへ送る。日本語の変換中の ESC は、変換の取り消しなので送らない。
# 伝播を止めて、Quasar に ESC の印を付けさせない(付くと、同じ ESC の keyup で、開いたばかりの確認ダイアログが閉じる)
ESCAPE_KEYDOWN_JS = "(e) => { if (e.code === 'Escape' && !e.isComposing) { e.stopPropagation(); emit(); } }"


def today() -> date:
    """今日。テストで差し替える。"""
    return date.today()


def date_normalizer(roll_forward: bool) -> Callable[[str], str | None]:
    return lambda text: parse_date_input(text, today(), roll_forward)


def normalize_field(field: ui.input, normalize: Callable[[str], str | None]) -> None:
    """入力欄を離れたとき、省略形を正式な形へ直す。読めない値(入力の途中を含む)は、そのまま残す。"""
    text = field.value or ""
    fixed = normalize(text) if text.strip() else None
    if fixed is not None and fixed != text:
        field.set_value(fixed)


def add_picker(
    field: ui.input,
    picker_factory: Callable[[], ui.date | ui.time],
    icon: str,
    key: str,
    fmt: str,
    normalize: Callable[[str], str | None] | None = None,
) -> None:
    """入力欄の右端のアイコンで、選択部品のダイアログを開く。小さな画面でも切れない。
    normalize があれば、欄を離れたときに省略形を直す。入力欄が無効のあいだは開かない。"""
    if normalize is not None:
        field.on("blur", lambda _e: normalize_field(field, normalize))
    with ui.dialog() as picker, ui.card():
        bind_picker(picker_factory().mark(f"{key}-picker"), field, fmt)
        ui.button("OK", on_click=picker.close).mark(f"{key}-picker-ok")
    with field.add_slot("append"):
        ui.icon(icon).classes("cursor-pointer").on("click", lambda: picker.open() if field.enabled else None).mark(
            f"open-{key}-picker"
        )


def moment_column(
    label: str, mark: str, picker: str, moment: datetime | None
) -> tuple[ui.input, ui.input]:
    """実績の日付と時刻の入力の組。マーカーは `{mark}-date` と `{mark}-time`。"""
    with ui.column().classes("flex-1 gap-0"):
        day = ui.input(f"{label}の日付", value=moment.strftime("%Y-%m-%d") if moment else "")
        day.classes("w-full").mark(f"{mark}-date")
        add_picker(day, ui.date, "event", f"{picker}-date", "%Y-%m-%d", date_normalizer(False))
        clock = ui.input(f"{label}の時刻", value=moment.strftime("%H:%M") if moment else "")
        clock.classes("w-full").mark(f"{mark}-time")
        add_picker(clock, ui.time, "access_time", f"{picker}-time", "%H:%M", parse_time_input)
    return day, clock


class DateTimeFields:
    """開始予定・完了予定・締切を、日付の入力と、側ごとのチェックで出す時刻の入力で受け取る。

    完了予定は、工数があって「手で指定」がオフのときは、算出値を読み取り専用で出す
    (入力欄は隠すだけで、入力済みの値は保つ)。手で指定のときは、入力欄の上に算出値を参考値として出し、
    ヒントに算出値との日数差を出す。
    """

    def __init__(
        self,
        task: Task,
        work_start: time,
        daily_hours: float,
        holidays: dict[date, str],
        crew: Sequence[Worker] = (),
        weeks: Sequence[Sequence[Worker]] = (),
    ) -> None:
        default_start, default_end = default_times(work_start)
        self._defaults = {"start": default_start, "end": default_end, "deadline": default_end}
        self._work_start, self._daily_hours, self._holidays = work_start, daily_hours, holidays
        self.effort = task.effort_hours
        self._crew = list(crew)
        self._weeks = [list(week) for week in weeks]
        self.first_row = ui.row().classes("w-full no-wrap gap-4")
        with self.first_row:
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
        for widget in (self.start_day, self.start_time, self.deadline_day, self.deadline_time, self.end_day):
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
        with ui.column().classes("flex-1 gap-0 min-w-0"):
            ui.label(label).classes("text-caption text-grey")
            if header is not None:
                header()
            with ui.column().classes("w-full gap-0") as editable:
                with ui.row().classes("w-full items-start no-wrap gap-2"):
                    day = ui.input("日付", value=moment.strftime(DATE_FORMAT) if moment else "")
                    day.classes("flex-1 min-w-0").mark(f"task-{key}-date")
                    add_picker(day, ui.date, "event", f"{key}-date", "%Y-%m-%d", date_normalizer(True))
                    clock = ui.input("時刻", value=(moment.time() if moment else default).strftime("%H:%M"))
                    clock.classes("w-28").mark(f"task-{key}-time")
                    add_picker(clock, ui.time, "access_time", f"{key}-time", "%H:%M", parse_time_input)
                if key == "end":  # 入力欄の hint は固定の高さで、欄が狭いと 2 行に折り返して下のチップに重なる。通常の流れのラベルにする
                    self.end_hint = ui.label("").classes("text-caption text-grey").mark("task-end-hint")
                with ui.row().classes("w-full items-center no-wrap gap-1"):
                    for name, text in SHORTCUT_LABELS.items():
                        ui.chip(
                            text,
                            on_click=lambda _e, n=name, d=day: d.set_value(
                                shortcut_dates(today())[n].strftime(DATE_FORMAT)
                            ),
                        ).props("dense clickable outline size=sm").mark(f"task-{key}-shortcut-{name}")
                    ui.space()
                    checkbox = (
                        ui.checkbox("時刻を指定", value=use_time, on_change=lambda e, k=key: self._show_time(k, e.value))
                        .props("dense")
                        .mark(f"task-{key}-use-time")
                    )
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

    def set_crew(self, crew: Sequence[Worker], weeks: Sequence[Sequence[Worker]] = ()) -> None:
        self._crew = list(crew)
        self._weeks = [list(week) for week in weeks]
        self._refresh_end()

    def set_effort(self, value: float | None) -> None:
        self.effort = value or 0.0
        self._refresh_end()

    def _refresh_end(self, _event: object = None) -> None:
        """完了予定の欄を、工数と「手で指定」に合わせて切り替え、算出値を更新する。"""
        has_effort = (self.effort or 0.0) > 0
        computed_mode = has_effort and not self.manual.value
        self.manual.set_visibility(has_effort)
        self.computed.set_visibility(has_effort)
        self.computed.set_label("算出値" if computed_mode else "算出値(参考)")
        self.end_editable.set_visibility(not computed_mode)
        computed = self._computed_end()
        hint = (
            "空なら工数から算出します"
            if has_effort
            else "空なら締切(なければ開始予定の翌日)になります"
        )
        if has_effort and not computed_mode:
            try:
                hint = end_gap_hint(parse_datetime(self.end_text()), computed) or hint
            except ValueError:
                pass
        self.end_hint.set_text(hint)
        self.computed.set_value(computed.strftime("%Y-%m-%d %H:%M") if computed else "")

    def _computed_end(self) -> datetime | None:
        try:
            start = parse_datetime(self.start_text())
            deadline = parse_datetime(self.deadline_text())
        except ValueError:
            return None
        return computed_end(
            start,
            self.effort or 0.0,
            self._daily_hours,
            self._work_start,
            self._holidays,
            deadline,
            crew=self._crew,
            weeks=self._weeks or None,
        )

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

    def _column(self, label: str, key: str, moment: datetime | None) -> tuple[ui.input, ui.input]:
        return moment_column(label, f"task-actual-{key}", f"actual-{key}", moment)

    def bind(self, callback: Callable[[object], None]) -> None:
        """入力が変わったときに呼ぶ関数を、すべての入力に付ける。"""
        for widget in self.inputs():
            widget.on_value_change(callback)

    def inputs(self) -> list[ui.input | ui.number]:
        if self.read_only:
            return []
        return [self.start_day, self.start_time, self.end_day, self.end_time]

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
        """変更の判定に使う入力値。"""
        return tuple(widget.value or "" for widget in self.inputs())


@dataclass
class IntervalRow:
    card: ui.card
    start_day: ui.input
    start_time: ui.input
    end_day: ui.input
    end_time: ui.input


class IntervalFields:
    """実績の区間を、行を足していく形で入力する(記録方式が「区間」のとき)。
    ActualFields と同じ呼び出し口(bind / filled / state)にそろえる。
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
                ui.button(
                    "削除", icon="delete", on_click=lambda c=card: self._remove(c)
                ).props("flat dense color=negative").mark(f"task-interval-{n}-remove")
        row = IntervalRow(card, start_day, start_time, end_day, end_time)
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
        return [row.start_day, row.start_time, row.end_day, row.end_time]

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
            result.append((start, end))
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

    def state(self) -> tuple[object, ...]:
        """変更の判定に使う入力値。行の数と、各行の値。"""
        values: list[object] = [len(self._rows)]
        for row in self._rows:
            values += [
                row.start_day.value or "",
                row.start_time.value or "",
                row.end_day.value or "",
                row.end_time.value or "",
            ]
        return tuple(values)


class TaskProgressField:
    """タスクの進捗度の欄。進捗度の入力はこの 1 つだけ(実績には持たない)。"""

    def __init__(self, own: int | None) -> None:
        with ui.column().classes("w-full gap-0") as self.container:
            self.input = (
                ui.number("進捗度(%)", value=own, min=MIN_PROGRESS, max=MAX_PROGRESS, precision=0)
                .classes("w-full")
                .mark("task-progress")
            )

    @property
    def value(self) -> float | None:
        return self.input.value

    def state(self) -> tuple[object, ...]:
        """変更の判定に使う入力値(進捗度は 0 と空を区別する)。"""
        return (self.input.value,)


NO_TEMPLATE = ""  # 選択肢の「テンプレートなし」(select の値は空文字で表す)


@dataclass
class UrlItem:
    row: ui.row
    title: ui.input
    template: ui.select
    value: ui.input
    previous: str  # 直前のテンプレートの選択。なし/ありが変わったときに値を空にする


def _value_label(template: str) -> str:
    return "URL" if template == NO_TEMPLATE else "ID"


class UrlFields:
    """タスクのリンクの節。1 行が 表示名・テンプレート・値(URL か ID)・開く・削除。"""

    def __init__(
        self,
        urls: list[TaskUrl],
        templates: list[UrlTemplate],
        open_url: Callable[[str], object],
    ) -> None:
        self.templates = templates
        self.open_url = open_url
        self.items: list[UrlItem] = []
        self.counter = 0
        ui.label("リンク").classes("text-caption text-grey")
        self.box = ui.column().classes("w-full gap-1")
        for link in urls:
            self._add_row(link)
        ui.button("リンクを追加", icon="add", on_click=lambda: self._add_row(None)).props(
            "flat dense"
        ).mark("task-url-add")

    def _add_row(self, link: TaskUrl | None) -> None:
        self.counter += 1
        n = self.counter
        current = link.template if link is not None and link.template is not None else NO_TEMPLATE
        names = [t.name for t in self.templates]
        if current != NO_TEMPLATE and current not in names:
            names.append(current)  # 一覧にない参照も、保存で失わない
        options = {NO_TEMPLATE: "テンプレートなし", **{name: name for name in names}}
        text = "" if link is None else next(iter(link.values.values()), "")
        with self.box:
            with ui.row().classes("w-full items-center no-wrap gap-2") as row:
                title = ui.input("表示名", value="" if link is None else link.title)
                title.classes("w-32").mark(f"task-url-{n}-title")
                template = ui.select(options, value=current, label="テンプレート")
                template.classes("w-40").mark(f"task-url-{n}-template")
                value = ui.input(_value_label(current), value=text)
                value.classes("grow").mark(f"task-url-{n}-value")
                item = UrlItem(row, title, template, value, current)
                ui.button(icon="open_in_new", on_click=lambda: self._open(item)).props(
                    "flat dense"
                ).mark(f"task-url-{n}-open")
                ui.button(icon="delete", on_click=lambda: self._remove(item)).props(
                    "flat dense color=negative"
                ).mark(f"task-url-{n}-remove")
        template.on_value_change(lambda e: self._template_changed(item, e.value or NO_TEMPLATE))
        self.items.append(item)

    def _template_changed(self, item: UrlItem, new: str) -> None:
        if (item.previous == NO_TEMPLATE) != (new == NO_TEMPLATE):
            item.value.set_value("")  # URL と ID は別のものなので、持ち越さない
        item.value.props(f"label={_value_label(new)}")
        item.previous = new

    def _remove(self, item: UrlItem) -> None:
        self.items.remove(item)
        item.row.delete()

    def _open(self, item: UrlItem) -> None:
        title, template, value = self._row(item)
        key = URL_KEY if template is None else ID_KEY
        link = TaskUrl(title.strip(), template, {key: value.strip()})
        try:
            self.open_url(resolve(link, self.templates))
        except (ValueError, OSError) as exc:
            ui.notify(str(exc), type="negative")

    @staticmethod
    def _row(item: UrlItem) -> UrlRow:
        chosen = item.template.value or NO_TEMPLATE
        return (item.title.value or "", None if chosen == NO_TEMPLATE else chosen, item.value.value or "")

    def rows(self) -> list[UrlRow]:
        return [self._row(item) for item in self.items]

    def state(self) -> tuple[UrlRow, ...]:
        return tuple(self.rows())


NO_MEMBER = ""
AssigneeRow = tuple[str, float | None]  # (メンバー名, 割り当て率の%)


@dataclass
class AssigneeItem:
    row: ui.row
    member: ui.select
    allocation: ui.number


class AssigneeFields:
    """タスクの担当者の節。1 行が メンバー・割り当て率(%)・削除。メンバーは行をまたいで重ならない。"""

    def __init__(
        self,
        assignees: list[Assignee],
        members: list[Member],
        on_change: Callable[[], object],
        marker: str = "task",
        title: str = "担当者",
    ) -> None:
        self.members = members
        self.on_change = on_change
        self.marker = marker
        self.items: list[AssigneeItem] = []
        self.counter = 0
        self.container = ui.column().classes("w-full gap-1")
        with self.container:
            ui.label(title).classes("text-caption text-grey")
            self.box = ui.column().classes("w-full gap-1")
            for assignee in assignees or [None]:
                self._add_row(assignee)
            ui.button("担当者を追加", icon="add", on_click=self._add_blank).props("flat dense").mark(
                f"{self.marker}-assignee-add"
            )
        self._sync()

    def _add_blank(self) -> None:
        self._add_row(None)
        self._sync()
        self.on_change()

    def _add_row(self, assignee: Assignee | None) -> None:
        self.counter += 1
        suffix = "" if self.counter == 1 else f"-{self.counter}"
        name = NO_MEMBER if assignee is None else assignee.name
        fraction = 1.0 if assignee is None else assignee.allocation
        with self.box:
            with ui.row().classes("w-full items-center no-wrap gap-4") as row:
                member = ui.select(
                    {NO_MEMBER: "(なし)", **({name: name} if name else {})}, label="担当者", value=name
                )
                member.classes("flex-1").mark(f"{self.marker}-assignee{suffix}")
                allocation = ui.number(
                    "割り当て率(%)",
                    value=round(fraction * 100, 2),
                    min=MIN_ALLOCATION * 100,
                    max=MAX_ALLOCATION * 100,
                    step=5,
                )
                allocation.classes("flex-1").mark(f"{self.marker}-allocation{suffix}")
                item = AssigneeItem(row, member, allocation)
                ui.button(icon="delete", on_click=lambda: self._remove(item)).props(
                    "flat dense color=negative"
                ).mark(f"{self.marker}-assignee-remove{suffix}")
        member.on_value_change(lambda _e: self._changed())
        allocation.on_value_change(lambda _e: self.on_change())
        self.items.append(item)

    def _remove(self, item: AssigneeItem) -> None:
        self.items.remove(item)
        item.row.delete()
        self._sync()
        self.on_change()

    def _changed(self) -> None:
        self._sync()
        self.on_change()

    def _options(self, item: AssigneeItem) -> dict[str, str]:
        taken = {other.member.value for other in self.items if other is not item}
        own = item.member.value
        names = [m.name for m in self.members if m.name == own or m.name not in taken]
        return {NO_MEMBER: "(なし)", **{n: n for n in names}}

    def _sync(self) -> None:
        for item in self.items:
            item.member.set_options(self._options(item), value=item.member.value)
            item.allocation.set_visibility(bool(item.member.value))

    def assignee_list(self) -> list[Assignee]:
        """メンバーを選んだ行を Assignee にしたもの(割り当て率の空は 100%)。"""
        return [Assignee(name, (percent or 100) / 100) for name, percent in self.rows() if name]

    def set_assignees(self, assignees: list[Assignee]) -> None:
        """行を作り直す(オフにしたとき、第1週の担当を全期間の担当に戻す)。"""
        for item in self.items:
            item.row.delete()
        self.items.clear()
        self.counter = 0
        for assignee in assignees or [None]:
            self._add_row(assignee)
        self._sync()
        self.on_change()

    def rows(self) -> list[AssigneeRow]:
        return [(item.member.value or "", item.allocation.value) for item in self.items]

    def state(self) -> tuple[AssigneeRow, ...]:
        """変更の判定に使う値。メンバーのない行の割り当て率は、隠れているので数えない(値は消さない)。"""
        return tuple((name, percent if name else None) for name, percent in self.rows())

    def chosen(self) -> list[tuple[Member, float]]:
        """メンバーを選んだ行の、(メンバー, 割り当ての割合)。"""
        by_name = {m.name: m for m in self.members}
        return [(by_name[name], (percent or 100) / 100) for name, percent in self.rows() if name in by_name]


def open_week_crew_dialog(
    number: int,
    crew: list[Assignee],
    members: list[Member],
    on_save: Callable[[list[Assignee]], object],
    period: str = "",
) -> None:
    """週ごとのタスクの、1 週ぶんの担当だけを直す小さなダイアログ(ガントチャートのチップのクリックで開く)。
    タイトルは、チップのヒントの見出しと同じ「第N週 期間」。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label(f"第{number}週 {period}".rstrip()).classes("text-h6").mark("week-edit-title")
        fields = AssigneeFields(crew, members, lambda: None, marker="week-edit")
        error = ui.label("").classes("text-negative").mark("week-edit-error")

        def save() -> None:
            try:
                chosen = _build_assignees(fields.rows())
            except ValueError as exc:
                error.set_text(str(exc))
                return
            if not chosen:
                error.set_text("担当者を選んでください")
                return
            dialog.close()
            on_save(chosen)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("week-edit-save")
    dialog.open()


def _title_table(hover: list[str]) -> str:
    """選択肢の番号 → マウスオーバーの全文(省略していないものは空)。NiceGUI の select は、選択肢の value に番号を渡す。
    属性の中に入れるので、JSON の引用符は &quot; にする(Vue が属性の値を戻す)。"""
    return html.escape(json.dumps(hover, ensure_ascii=False), quote=True)


def category_option_template(hover: list[str]) -> str:
    return (
        f'<q-item v-bind="props.itemProps" :title="{_title_table(hover)}[props.opt.value]">'
        "<q-item-section>{{ props.opt.label }}</q-item-section></q-item>"
    )


def category_selected_template(hover: list[str]) -> str:
    return f'<span :title="{_title_table(hover)}[props.opt.value]">{{{{ props.opt.label }}}}</span>'


def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
    on_delete: Callable[[], object] | None = None,
    daily_hours: float = DEFAULT_DAILY_HOURS,
    holidays: dict[date, str] | None = None,
    members: list[Member] | None = None,
    actual_mode: ActualMode = ActualMode.SIMPLE,
    link_options: dict[str, str] | None = None,
    finish_of: Callable[[str], datetime | None] | None = None,
    url_templates: list[UrlTemplate] | None = None,
    open_url: Callable[[str], object] = default_open_url,
    parameters: list[Parameter] | None = None,
    categories: list[Category] | None = None,
    layout: str = "all",
    on_layout_change: Callable[[str], object] | None = None,
    on_decompose: Callable[[Callable[[], object]], object] | None = None,
    now: Callable[[], datetime] = datetime.now,
) -> ui.dialog:
    initial = task or Task("")
    is_summary = initial.kind is TaskKind.SUMMARY  # まとめは、名前・カテゴリ・優先度・リンクだけを編集する
    raw_members = list(members or [])
    chosen_parameters = list(initial.parameters)  # 付けたパラメータ(選択欄の値。空は全パラメータの合計)
    # 換算には、付けたパラメータを反映した実効比率を使う(以降は、このコピーだけを見る)
    member_list = [
        Member(m.name, effective_ratio(m, parameters or [], chosen_parameters), work_days=list(m.work_days))
        for m in raw_members
    ]
    for assignee in initial.assignees:  # 一覧にいない担当者も、保存で失わない(相対比率は 100% とみなす)
        if all(m.name != assignee.name for m in member_list):
            member_list.append(Member(assignee.name, 1.0))
    initial_rate = assignees_rate(initial.assignees, member_list)

    def reapply_ratios() -> None:
        """付けたパラメータの選択が変わったとき、比率を作り直す(member_list は担当者の欄と共有なので、その場で書き換える)。"""
        by_name = {m.name: m for m in raw_members}
        for member in member_list:
            if member.name in by_name:
                member.ratio = effective_ratio(by_name[member.name], parameters or [], chosen_parameters)
    with disposable(ui.dialog().props("persistent")) as dialog, ui.card().classes("w-[44rem] max-w-full"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        layout_toggle = ui.toggle(LAYOUT_LABELS, value=layout if layout in LAYOUT_LABELS else "all").mark(
            "task-layout"
        )
        kind = ui.toggle(  # まとめは分解でだけ作る(選択肢に出さない)。まとめの編集では、トグル自体を隠す
            {k: k.value for k in TaskKind if k is not TaskKind.SUMMARY},
            value=TaskKind.NORMAL if is_summary else initial.kind,
        ).mark("task-kind")
        kind_hint = (
            ui.label("保存すると、開始予定・工数・担当・実績は消えます")
            .classes("text-caption text-grey")
            .mark("task-kind-hint")
        )
        # 長い名前は折り返す(textarea を 1 行から伸ばす)。名前に改行は使えないので、Enter は無効にし、貼り付けた改行は空白にする
        name = (
            ui.textarea("名前", value=initial.name)
            .props("autogrow rows=1")
            .classes("w-full")
            .on("keydown.enter.prevent", lambda: None)
            .mark("task-name")
        )

        def replace_control_chars(event: ValueChangeEventArguments) -> None:
            # 使えない文字は空白に替え、上限(文字数。ブラウザの maxlength は UTF-16 単位でずれる)で切る
            text = event.value or ""
            cleaned = "".join(" " if has_control_char(ch) else ch for ch in text)[:MAX_TASK_NAME_LENGTH]
            if cleaned != text:
                name.set_value(cleaned)

        name.on_value_change(replace_control_chars)
        # 先頭が未定(値は空文字。None は選択なしと区別できない)。名前が長いときだけ省略し、種別・PRJコードは残す。全文はマウスオーバーで出す
        category_options = {"": UNDECIDED, **{c.id: category_label(c) for c in categories or []}}
        category = (
            ui.select(
                category_options,
                label="カテゴリ",
                value=initial.category_id if initial.category_id in category_options else "",
            )
            .classes("w-full")
            .mark("task-category")
        )
        full_labels = [UNDECIDED] + [category_full_label(c) for c in categories or []]
        hover = [full if full != label else "" for full, label in zip(full_labels, category_options.values())]
        category.add_slot("option", category_option_template(hover))
        category.add_slot("selected-item", category_selected_template(hover))
        parameter_select: ui.select | None = None
        if parameters:
            parameter_select = (
                ui.select(
                    [p.name for p in parameters],
                    label="パラメータ(付けると、そのパラメータの判定値だけで相対比率を決める)",
                    value=[name for name in initial.parameters if any(p.name == name for p in parameters)],
                    multiple=True,
                )
                .props("use-chips")
                .classes("w-full")
                .mark("task-parameters")
            )
        fields = DateTimeFields(
            initial,
            work_start,
            daily_hours,
            holidays or {},
            crew_of(initial.assignees, member_list),
            weeks=[crew_of(week, member_list) for week in initial.weekly_crew],
        )
        with fields.second_row:
            effort = EffortField(initial.effort_hours, daily_hours, STANDARD_WORK_HOURS)
        weekly = bool(initial.weekly_crew)  # 週ごとのタスクの担当は、ガントチャートの棒のチップをタップして直す(ここでは直さない)
        assignee_fields = AssigneeFields(initial.assignees, member_list, lambda: refresh_conversion())
        weekly_note = ui.label(
            "担当は週ごとに分けています。棒の上のチップをタップして直します(担当者: "
            + "・".join(a.name for a in initial.assignees)
            + ")"
        ).classes("text-caption text-grey").mark("task-weekly-note")
        conversion = ui.label("").classes("text-caption text-grey").mark("task-conversion")

        def refresh_conversion(_event: object = None) -> None:
            tagged = f"・{'・'.join(chosen_parameters)}を反映" if chosen_parameters else ""
            if weekly:
                by_name = {m.name: m for m in member_list}
                weeks = [[(by_name[a.name], a.allocation) for a in week if a.name in by_name] for week in initial.weekly_crew]
                fields.set_crew(
                    [],
                    [[Worker(combine_rate(m.ratio, f), work_day_map(m.work_days)) for m, f in week] for week in weeks],
                )
                if not (effort.value or 0.0) > 0 or not any(weeks):
                    conversion.set_text("")
                    return
                parts = []
                for number, week in enumerate(weeks, start=1):
                    rate = sum(combine_rate(m.ratio, f) for m, f in week) if week else 1.0
                    detail = " + ".join(f"{m.name} {m.ratio * 100:g}%×{f * 100:g}%" for m, f in week) or "担当なし"
                    parts.append(f"第{number}週: {detail} = {rate * 100:g}%")
                conversion.set_text(f"換算率 {' / '.join(parts)}{tagged}")
                return
            chosen = assignee_fields.chosen()
            rate = sum(combine_rate(m.ratio, f) for m, f in chosen) if chosen else 1.0
            fields.set_crew([Worker(combine_rate(m.ratio, f), work_day_map(m.work_days)) for m, f in chosen])
            days = effort_days(effort.value or 0.0, rate, daily_hours) if chosen else None
            if not chosen or days is None:
                conversion.set_text("")
                return
            detail = " + ".join(f"{m.name} {m.ratio * 100:g}%×{f * 100:g}%" for m, f in chosen)
            conversion.set_text(f"換算率 {rate * 100:g}%({detail}{tagged})→ {effort.value:g}h は約 {days:.1f}日分")

        def on_effort_change(value: float | None) -> None:
            fields.set_effort(value)
            refresh_conversion()

        effort.on_value_change(on_effort_change)

        if parameter_select is not None:

            def on_parameters_change(event: ValueChangeEventArguments) -> None:
                chosen_parameters[:] = event.value or []
                reapply_ratios()
                refresh_conversion()

            parameter_select.on_value_change(on_parameters_change)
        refresh_conversion()
        options = dict(link_options or {})
        kept = [pid for pid in initial.predecessors if pid in options]  # 候補にない参照は、欄に出さない
        predecessors = (
            ui.select(options, label="先行タスク", value=kept, multiple=True)
            .props("use-chips")
            .classes("w-full")
            .mark("task-predecessors")
        )
        push = ui.label("").classes("text-caption text-grey").mark("task-predecessors-hint")

        def refresh_push(_event: object = None) -> None:
            finishes = [
                finish
                for pid in predecessors.value or []
                if finish_of is not None and (finish := finish_of(pid)) is not None
            ]
            try:
                start_at = parse_datetime(fields.start_text())
            except ValueError:
                start_at = None
            # チェックポイントは押し出されない(締切に固定)ので、ヒントを出さない
            text = "" if kind.value == TaskKind.CHECKPOINT else push_hint(start_at, finishes)
            push.set_text(text)
            push.set_visibility(bool(text) and layout_toggle.value == "all")

        predecessors.on_value_change(refresh_push)
        refresh_push()

        def merged_predecessors() -> list[str]:
            """欄の値。候補にない既存の参照(通常はない)は、そのまま残す。"""
            hidden = [pid for pid in initial.predecessors if pid not in options]
            return [*(predecessors.value or []), *hidden]

        with ui.column().classes("w-full gap-1") as priority_box:
            priority = PriorityChips(initial.priority)
        intervals = actual_mode is ActualMode.INTERVALS
        with ui.column().classes("w-full") as actual_box:
            actual_fields: ActualFields | IntervalFields = (
                IntervalFields(initial) if intervals else ActualFields(initial)
            )
        progress_field = TaskProgressField(initial.progress)
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
                *actual_fields.filled(), progress_field.value, intervals=intervals
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
        progress_field.input.on_value_change(on_actual_change)
        has_normal_data = bool(
            initial.planned_start
            or initial.planned_end
            or initial.effort_hours
            or initial.assignees
            or initial.actuals
            or initial.progress is not None
        )

        def apply_kind(_event: object = None) -> None:
            """チェックポイントでは、開始予定・完了予定・工数・担当・実績の欄を隠し、状態を 2 つにする。"""
            checkpoint = kind.value == TaskKind.CHECKPOINT
            allowed = CHECKPOINT_STATUSES if checkpoint else tuple(Status)
            suggest["setting"] = True
            try:
                status.set_options(
                    {s: s.value for s in allowed},
                    value=status.value if status.value in allowed else Status.NOT_STARTED,
                )
            finally:
                suggest["setting"] = False
            kind_hint.set_visibility(
                checkpoint and initial.kind is TaskKind.NORMAL and has_normal_data
            )
            refresh_push()

        kind.on_value_change(apply_kind)
        apply_kind()
        templates = list(url_templates or [])
        with ui.column().classes("w-full gap-1") as url_box:
            url_fields = UrlFields(initial.urls, templates, open_url)
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )

        def refresh_visibility(_event: object = None) -> None:
            """欄の出し入れを 1 か所で決める(値は消さない)。チェックポイントでは通常の欄を隠し、レイアウトは付加的な欄を隠す。
            換算の説明は、完了予定の算出値を動かすので、レイアウトに関わらず出す。"""
            if is_summary:
                for widget in (
                    fields.first_row, fields.second_row, conversion, actual_box, progress_field.container,
                    assignee_fields.container, weekly_note,
                    predecessors, push, status, hint, color, kind, kind_hint, layout_toggle,
                    *([parameter_select] if parameter_select is not None else []),
                ):
                    widget.set_visibility(False)
                for widget in (category, priority_box, url_box):
                    widget.set_visibility(True)
                return
            full = layout_toggle.value == "all"
            normal = kind.value != TaskKind.CHECKPOINT
            for widget in (fields.first_row, effort, conversion, actual_box, progress_field.container):
                widget.set_visibility(normal)
            assignee_fields.container.set_visibility(full and normal and not weekly)
            weekly_note.set_visibility(full and normal and weekly)
            if parameter_select is not None:
                parameter_select.set_visibility(full and normal)
            for widget in (category, predecessors, priority_box, url_box, color):
                widget.set_visibility(full)
            refresh_push()

        kind.on_value_change(refresh_visibility)
        layout_toggle.on_value_change(refresh_visibility)
        if on_layout_change is not None:
            layout_toggle.on_value_change(lambda e: on_layout_change(e.value))
        refresh_visibility()
        error = ui.label("").classes("text-negative").mark("form-error")

        def current() -> tuple[object, ...]:
            """入力の現在値。開いた時点と比べて、変更があるかを判定する。"""
            return (
                name.value,
                kind.value,
                category.value or "",
                *fields.state(),
                effort.value,
                priority.value,
                status.value,
                color.value,
                assignee_fields.state(),
                tuple(predecessors.value or []),
                *actual_fields.state(),
                *progress_field.state(),
                url_fields.state(),
            )

        opened = current()
        pending: dict[str, object] = {}  # 確認待ちの保存内容(task)と、見直した完了予定(end)

        def finish(apply: bool) -> None:
            review.close()
            result = pending["task"]
            assert isinstance(result, Task)
            if apply:
                end = pending["end"]
                assert isinstance(end, datetime)
                result.planned_end = end
                result.planned_end_manual = True
            on_save(result)
            dialog.close()

        with ui.dialog() as review, ui.card():
            review_text = ui.label("").classes("whitespace-pre-line").mark("reassign-text")
            with ui.row():
                ui.button("見直す", on_click=lambda: finish(True)).mark("reassign-apply")
                ui.button("見直さない", on_click=lambda: finish(False)).props("flat").mark("reassign-skip")
                ui.button("編集に戻る", on_click=lambda: review.close()).props("flat").mark("reassign-back")

        def save() -> None:
            error.set_text("")
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    category_id=category.value or None,
                    planned_start=fields.start_text(),
                    planned_end=fields.end_text(),
                    planned_end_manual=bool(fields.manual.value),
                    deadline=fields.deadline_text(),
                    effort_hours=effort.value,
                    priority=priority.value,
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignees=assignee_fields.rows(),
                    predecessors=merged_predecessors(),
                    kind=TaskKind.SUMMARY if is_summary else TaskKind(kind.value),
                    linkable_ids=frozenset(options) | frozenset(initial.predecessors),
                    actual_start=actual_fields.start_text(),
                    actual_end=actual_fields.end_text(),
                    actual_rows=actual_fields.rows() if isinstance(actual_fields, IntervalFields) else None,
                    progress=progress_field.value,
                    urls=build_urls(url_fields.rows(), templates),
                    parameters=chosen_parameters if parameter_select is not None else None,
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            new_rate = assignees_rate(result.assignees, member_list)
            new_end = (
                reviewed_end(result, initial_rate, new_rate, daily_hours, work_start, holidays or {}, now(), crew_of(result.assignees, member_list))
                if task is not None and not task.weekly_crew and needs_review(result, initial_rate, new_rate)
                else None
            )
            if new_end is None:
                on_save(result)
                dialog.close()
                return
            pending["task"], pending["end"] = result, new_end
            review_text.set_text(
                f"担当またはパラメータの変更で、換算率が {initial_rate:.2f} → {new_rate:.2f} に変わります。\n"
                f"残りの作業を新しい条件で見直すと、完了予定は {new_end:%Y-%m-%d %H:%M} です。"
            )
            review.open()

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
                if task.kind is TaskKind.SUMMARY:
                    ui.label(f"子のタスク {len(task.children)} 件は、通常のタスクとして残ります")

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

        # persistent の Quasar は、ESC で escapeKey を送らない(ゆらすだけ)ので、keydown で受ける
        dialog.on("keydown", request_close, js_handler=ESCAPE_KEYDOWN_JS)
        with ui.row().classes("w-full items-center"):
            if delete_confirm is not None:
                ui.button("削除", on_click=delete_confirm.open).props(
                    "flat color=negative"
                ).mark("task-delete")
            if (
                task is not None
                and on_decompose is not None
                and task.kind is TaskKind.NORMAL
                and not task.actuals
                and task.status is Status.NOT_STARTED
                and task.progress is None
                and not task.weekly_crew
            ):
                decompose_handler = on_decompose

                def decompose_now() -> None:
                    if current() != opened:
                        ui.notify("編集内容を保存してから分解してください", type="warning")
                        return
                    decompose_handler(dialog.close)  # 編集は開いたまま、上に分解を重ねる(閉じて開くと画面が一瞬消える)。成功したら閉じる

                ui.button("分解…", on_click=decompose_now).props("flat").mark("task-decompose")
            ui.space()
            ui.button("キャンセル", on_click=request_close).props("flat").mark("task-cancel")
            ui.button("保存", on_click=save).mark("task-save")
    dialog.open()
    return dialog
