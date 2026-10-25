"""プレビューモードの設定と、上部のバー。切り替えと保存の流れは MainView が持つ。"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from nicegui import ui

from projectapp.config import DEFAULT_NAME_WIDTH_PX
from projectapp.gantt import COLUMN_WIDTH_PX, ViewOptions
from projectapp.models import MAX_YEAR, MIN_YEAR, Project, ReferenceValue
from projectapp.selection import CheckState, toggled
from projectapp import task_dialog
from projectapp.dateinput import parse_date_input
from projectapp.task_dialog import normalize_field
from projectapp.timeline import Scale, build_columns

PERIOD_SEPARATOR = " 〜 "
PERIOD_SEPARATOR_PATTERN = re.compile(r"\s*[〜~～]\s*")  # 日付の区切りの `-` と混ざらないよう、波ダッシュだけ
PERIOD_ORDER_MESSAGE = "期間は、開始日が終了日以前になるように入れてください"
LARGE_IMAGE_MESSAGE = "画像が大きいため、縮小して保存されます(期間かスケールを変えると小さくできます)"
NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、画像として保存できます"
# 列が多すぎると、描き直しでブラウザとサーバが固まる。日次は約2年まで(1年強は問題なく出せる)
MAX_COLUMNS = {Scale.DAY: 800, Scale.WEEK: 400, Scale.MONTH: 240}
COLUMN_UNITS = {Scale.DAY: "日", Scale.WEEK: "週", Scale.MONTH: "か月"}
# 資料に貼ると、画像の幅に合わせて縮む。これを超えると、文字が小さくなりすぎるので、粗いスケールで開く
PREVIEW_COMFORT_WIDTH_PX = 6000
COARSER = (Scale.DAY, Scale.WEEK, Scale.MONTH)  # 細かい順


@dataclass(frozen=True)
class PreviewSettings:
    start: date
    end: date
    scale: Scale
    show_chips: bool = True
    show_alerts: bool = True
    show_events: bool = True
    excluded: frozenset[str] = frozenset()  # PlantUML と画像に出さないタスクの id(チェックを外したもの)

    def to_options(self, on_select: Callable[[list[str], bool], object] | None = None) -> ViewOptions:
        return ViewOptions(
            period=(self.start, self.end),
            scale=self.scale,
            show_chips=self.show_chips,
            show_alerts=self.show_alerts,
            show_events=self.show_events,
            read_only=True,
            selectable=True,
            excluded=self.excluded,
            on_select=on_select,
        )


def validate_period(start_text: str, end_text: str) -> tuple[date, date]:
    """期間の入力(YYYY-MM-DD)を検証する。開始日は終了日以前。"""
    try:
        start = datetime.strptime((start_text or "").strip(), "%Y-%m-%d").date()
        end = datetime.strptime((end_text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("日付の形式が正しくありません(YYYY-MM-DD)") from None
    if not (MIN_YEAR <= start.year <= MAX_YEAR and MIN_YEAR <= end.year <= MAX_YEAR):
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if start > end:
        raise ValueError(PERIOD_ORDER_MESSAGE)
    return start, end


def format_period(start: date, end: date) -> str:
    """期間の欄の文字列(`2026-10-01 〜 2026-10-31`)。"""
    return f"{start.isoformat()}{PERIOD_SEPARATOR}{end.isoformat()}"


def split_period(text: str) -> tuple[str, str]:
    """期間の欄の文字列を (開始, 終了) の文字列に分ける。区切りが 1 つでないときは (全体, "") で、検証でエラーになる。"""
    parts = PERIOD_SEPARATOR_PATTERN.split((text or "").strip())
    return (parts[0], parts[1]) if len(parts) == 2 else ((text or "").strip(), "")


def normalize_period(text: str, today: date) -> str | None:
    """両端の省略形(`10/15`・`1015`・`20261015`)を `YYYY-MM-DD` にした期間の文字列。読めないときは None。過ぎた日でも翌年にしない。"""
    start, end = split_period(text)
    fixed_start, fixed_end = parse_date_input(start, today, False), parse_date_input(end, today, False)
    if fixed_start is None or fixed_end is None:
        return None
    return f"{fixed_start}{PERIOD_SEPARATOR}{fixed_end}"


def parse_range_value(value: object) -> tuple[str, str] | None:
    """範囲カレンダーの値を (開始, 終了) にする。同じ日を 2 回押すと日付の文字列で届くので、1 日の範囲とする。未選択・片側だけは None。"""
    if isinstance(value, str):
        return (value, value) if value else None
    if not isinstance(value, dict):
        return None
    first, last = value.get("from"), value.get("to")
    if isinstance(first, str) and isinstance(last, str) and first and last:
        return first, last
    return None


def fit_scale(
    project: Project,
    holidays: dict[date, str],
    period: tuple[date, date] | None,
    scale: Scale,
    name_width: int = DEFAULT_NAME_WIDTH_PX,
    references: Mapping[str, ReferenceValue] | None = None,
) -> Scale:
    """全期間の画像の幅が快適な幅に収まるまで、スケールを 1 段ずつ粗くする。細かくはしない。月次は、広くても月次。"""
    for candidate in COARSER[COARSER.index(scale) :]:
        columns = build_columns(project, candidate, holidays, period, references)
        if name_width + COLUMN_WIDTH_PX[candidate] * len(columns) <= PREVIEW_COMFORT_WIDTH_PX:
            return candidate
    return Scale.MONTH


def coarser_notice(chosen: Scale, original: Scale) -> str:
    return f"幅が大きいため、{chosen.value}で開きました({original.value}にするには、期間を狭めてください)"


def check_column_count(scale: Scale, count: int) -> str | None:
    """列の数がスケールごとの上限を超えるときの、エラー文。収まるなら None。"""
    limit = MAX_COLUMNS[scale]
    if count <= limit:
        return None
    return f"期間が長すぎます({scale.value}は最大{limit}{COLUMN_UNITS[scale]}。期間かスケールを変えてください)"


def add_range_picker(field: ui.input) -> None:
    """期間の欄の右に、範囲カレンダーを開くアイコンを足す。OK で欄に反映する。1 日だけ選んだ間は OK を押せない。"""
    with ui.dialog() as dialog, ui.card():
        picker = ui.date().props("range").mark("preview-range-picker")
        ok = ui.button("OK").mark("preview-range-picker-ok")

    def on_pick(_event: object = None) -> None:
        ok.set_enabled(parse_range_value(picker.value) is not None)

    def open_picker() -> None:
        try:
            current = validate_period(*split_period(field.value or ""))
        except ValueError:
            picker.set_value(None)  # 空・不正・開始が終了より後のときは、選択なしで開く
        else:
            picker.set_value({"from": current[0].isoformat(), "to": current[1].isoformat()})
        on_pick()
        dialog.open()

    def apply() -> None:
        chosen = parse_range_value(picker.value)
        if chosen is None:
            return
        field.set_value(f"{chosen[0]}{PERIOD_SEPARATOR}{chosen[1]}")
        dialog.close()

    picker.on_value_change(on_pick)
    # Quasar は 1 回目のクリックでは値を送らない。選んでいる途中は前の範囲を適用させず、2 回目(rangeEnd)で値から判定し直す
    picker.on("rangeStart", lambda _e: ok.disable())
    picker.on("rangeEnd", on_pick)
    ok.on_click(apply)
    with field.add_slot("append"):
        ui.icon("date_range").classes("cursor-pointer").on("click", open_picker).mark("open-preview-range-picker")


class PreviewBar:
    """プレビューの上部のバー。1 段目に期間・スケール・表示項目、2 段目に出力の選択と戻る・保存。"""

    def __init__(
        self,
        on_change: Callable[[], object],
        on_back: Callable[[], object],
        on_save: Callable[[], object],
        on_save_plantuml: Callable[[], object],
        on_select_all: Callable[[bool], object] = lambda checked: None,
    ) -> None:
        self.on_change, self.on_back, self.on_save = on_change, on_back, on_save
        self.on_save_plantuml = on_save_plantuml
        self.on_select_all = on_select_all
        self.select_state: CheckState | None = None
        self.syncing = False
        self.box: ui.column | None = None

    def build(self) -> None:
        with ui.column().classes("w-full gap-1") as box:
            with ui.row().classes("w-full items-center gap-4").mark("preview-bar"):
                self.period = ui.input("期間", placeholder="2026-10-01 〜 2026-10-31").classes("w-72").mark(
                    "preview-period"
                )
                add_range_picker(self.period)
                # 両端の 10/15・1015・20261015 を YYYY-MM-DD に整える
                self.period.on(
                    "blur", lambda _e: normalize_field(self.period, lambda t: normalize_period(t, task_dialog.today()))
                )
                self.scale = ui.toggle({s.value: s.value for s in Scale}).mark("preview-scale")
                self.chips = ui.checkbox("チップと進捗", value=True).mark("preview-chips")
                self.alerts = ui.checkbox("予定超過の赤みと割り当て超過の縞", value=True).mark(
                    "preview-alerts"
                )
                self.events = ui.checkbox("イベント", value=True).mark("preview-events")
            with ui.row().classes("w-full items-center gap-4").mark("preview-output"):
                self.select_all = ui.checkbox("すべて選択", value=True).mark("preview-select-all")
                self.select_count = ui.label("").classes("text-caption").mark("preview-select-count")
                ui.space()
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props(
                    "flat"
                ).mark("preview-back")
                self.save_button = ui.button(
                    "画像として保存", icon="image", on_click=lambda: self.on_save()
                ).mark("preview-save")
                self.plantuml_button = ui.button(
                    "PlantUML として保存", icon="code", on_click=lambda: self.on_save_plantuml()
                ).mark("preview-plantuml")
            self.error = ui.label("").classes("text-negative text-caption").mark("preview-error")
            self.warning = ui.label("").classes("text-caption text-grey").mark("preview-warning")
        box.set_visibility(False)
        self.box = box
        for widget in (self.period, self.scale, self.chips, self.alerts, self.events):
            widget.on_value_change(lambda _event: self.on_change())
        self.select_all.on_value_change(self.on_select_all_changed)

    def on_select_all_changed(self, _event: object) -> None:
        if not self.syncing and self.select_state is not None:
            self.on_select_all(toggled(self.select_state))

    def set_selection(self, selected: int, total: int) -> None:
        """出力するタスクの数を表す。「すべて選択」は、全部で ON・全部外れで OFF・混在で中間。"""
        state = CheckState.ON if selected == total else CheckState.OFF if selected == 0 else CheckState.MIXED
        self.select_state = state
        self.syncing = True  # 値を入れ直すときは、通知しない
        try:
            self.select_all.set_value(None if state is CheckState.MIXED else state is CheckState.ON)
        finally:
            self.syncing = False
        self.select_count.set_text(f"{selected} / {total} 件を出力")

    def show(self, settings: PreviewSettings) -> None:
        """初期値を入れて出す。値を入れる間は、変更の通知を出さない。"""
        callback, self.on_change = self.on_change, lambda: None
        try:
            self.period.set_value(format_period(settings.start, settings.end))
            self.scale.set_value(settings.scale.value)
            self.chips.set_value(settings.show_chips)
            self.alerts.set_value(settings.show_alerts)
            self.events.set_value(settings.show_events)
        finally:
            self.on_change = callback
        self.set_error(None)
        self.set_warning(None)
        if self.box is not None:
            self.box.set_visibility(True)

    def hide(self) -> None:
        if self.box is not None:
            self.box.set_visibility(False)

    def read(self) -> tuple[str, str, Scale, bool, bool, bool]:
        start, end = split_period(self.period.value or "")
        return (
            start,
            end,
            Scale(self.scale.value),
            bool(self.chips.value),
            bool(self.alerts.value),
            bool(self.events.value),
        )

    def set_error(self, text: str | None) -> None:
        self.error.set_text(text or "")

    def set_warning(self, text: str | None) -> None:
        self.warning.set_text(text or "")

    def set_save_enabled(self, enabled: bool) -> None:
        self.save_button.set_enabled(enabled)
        self.plantuml_button.set_enabled(enabled)
