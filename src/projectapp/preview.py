"""プレビューモードの設定と、上部のバー。切り替えと保存の流れは MainView が持つ。"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from nicegui import ui

from projectapp.config import DEFAULT_NAME_WIDTH_PX
from projectapp.gantt import COLUMN_WIDTH_PX, ViewOptions
from projectapp.models import MAX_YEAR, MIN_YEAR, Project, ReferenceValue
from projectapp.selection import CheckState, toggled
from projectapp.task_dialog import add_picker
from projectapp.timeline import Scale, build_columns

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


def parse_range_value(value: object) -> tuple[str, str] | None:
    """範囲カレンダーの値を (開始, 終了) にする。1 日だけ選んだとき・未選択のときは None(確定できない)。"""
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


class PreviewBar:
    """プレビューの上部のバー。期間・スケール・表示項目と、戻る・保存のボタン。"""

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
                self.start = ui.input("開始日").classes("w-40").mark("preview-start")
                add_picker(self.start, ui.date, "event", "preview-start", "%Y-%m-%d")
                self.end = ui.input("終了日").classes("w-40").mark("preview-end")
                add_picker(self.end, ui.date, "event", "preview-end", "%Y-%m-%d")
                self.scale = ui.toggle({s.value: s.value for s in Scale}).mark("preview-scale")
                self.chips = ui.checkbox("チップと進捗", value=True).mark("preview-chips")
                self.alerts = ui.checkbox("予定超過の赤みと割り当て超過の縞", value=True).mark(
                    "preview-alerts"
                )
                self.events = ui.checkbox("イベント", value=True).mark("preview-events")
                self.select_all = ui.checkbox("すべて選択", value=True).mark("preview-select-all")
                self.select_count = ui.label("").classes("text-caption").mark("preview-select-count")
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
        for widget in (self.start, self.end, self.scale, self.chips, self.alerts, self.events):
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
            self.start.set_value(settings.start.isoformat())
            self.end.set_value(settings.end.isoformat())
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
        return (
            self.start.value or "",
            self.end.value or "",
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
