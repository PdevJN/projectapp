"""プレビューモードの設定と、上部のバー。切り替えと保存の流れは MainView が持つ。"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

from nicegui import ui

from projectapp.config import DEFAULT_NAME_WIDTH_PX
from projectapp.gantt import COLUMN_WIDTH_PX, ViewOptions
from projectapp.models import Project, ReferenceValue
from projectapp.selection import CheckState, toggled
from projectapp import task_dialog
from projectapp.periodfield import (  # noqa: F401  (他の画面とテストが、ここから読む)
    COLUMN_UNITS,
    MAX_COLUMNS,
    PERIOD_ORDER_MESSAGE,
    PERIOD_SEPARATOR,
    add_range_picker,
    check_column_count,
    format_period,
    normalize_period,
    parse_range_value,
    split_period,
    validate_period,
)
from projectapp.task_dialog import normalize_field
from projectapp.timeline import Scale, build_columns

LARGE_IMAGE_MESSAGE = "画像が大きいため、縮小して保存されます(期間かスケールを変えると小さくできます)"
NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、画像として保存できます"
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
    show_today: bool = True

    def to_options(self, on_select: Callable[[list[str], bool], object] | None = None) -> ViewOptions:
        return ViewOptions(
            period=(self.start, self.end),
            scale=self.scale,
            show_chips=self.show_chips,
            show_alerts=self.show_alerts,
            show_events=self.show_events,
            show_today=self.show_today,
            read_only=True,
            selectable=True,
            excluded=self.excluded,
            on_select=on_select,
        )


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
            with ui.row().classes("w-full items-center gap-4").mark("preview-bar"):  # 1 段目: 出力の条件と戻る
                self.period = ui.input("期間", placeholder="2026-10-01 〜 2026-10-31").classes("w-72").mark(
                    "preview-period"
                )
                add_range_picker(self.period, "preview")
                # 両端の 10/15・1015・20261015 を YYYY-MM-DD に整える
                self.period.on(
                    "blur", lambda _e: normalize_field(self.period, lambda t: normalize_period(t, task_dialog.today()))
                )
                self.scale = ui.toggle({s.value: s.value for s in Scale}).mark("preview-scale")
                with ui.button("表示項目", icon="tune").props("flat dense").mark("preview-display-menu"):
                    with ui.menu():  # チェックを押してもメニューは閉じない(Quasar の既定。auto-close は付けない)
                        with ui.column().classes("gap-0 q-pa-sm"):
                            self.chips = ui.checkbox("チップと進捗", value=True).mark("preview-chips")
                            self.alerts = ui.checkbox("遅れの赤みと割り当て超過の縞", value=True).mark(
                                "preview-alerts"
                            )
                            self.events = ui.checkbox("イベント", value=True).mark("preview-events")
                            self.today = ui.checkbox("今日", value=True).mark("preview-today")
                ui.space()
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props("flat").mark(
                    "preview-back"
                )
            with ui.row().classes("w-full items-center gap-4").mark("preview-output"):  # 2 段目: 出力の選択と保存
                self.select_all = ui.checkbox("すべて選択", value=True).mark("preview-select-all")
                self.select_count = ui.label("").classes("text-caption").mark("preview-select-count")
                ui.space()
                with ui.button("保存", icon="save").mark("preview-save-menu") as self.save_menu_button:
                    with ui.menu():
                        self.save_button = ui.menu_item(
                            "画像として保存", on_click=lambda: self.on_save()
                        ).mark("preview-save")
                        self.plantuml_button = ui.menu_item(
                            "PlantUML として保存", on_click=lambda: self.on_save_plantuml()
                        ).mark("preview-plantuml")
            self.error = ui.label("").classes("text-negative text-caption").mark("preview-error")
            self.warning = ui.label("").classes("text-caption text-grey").mark("preview-warning")
        box.set_visibility(False)
        self.box = box
        for widget in (self.period, self.scale, self.chips, self.alerts, self.events, self.today):
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
            self.today.set_value(settings.show_today)
        finally:
            self.on_change = callback
        self.set_error(None)
        self.set_warning(None)
        if self.box is not None:
            self.box.set_visibility(True)

    def hide(self) -> None:
        if self.box is not None:
            self.box.set_visibility(False)

    def read(self) -> tuple[str, str, Scale, bool, bool, bool, bool]:
        start, end = split_period(self.period.value or "")
        return (
            start,
            end,
            Scale(self.scale.value),
            bool(self.chips.value),
            bool(self.alerts.value),
            bool(self.events.value),
            bool(self.today.value),
        )

    def set_error(self, text: str | None) -> None:
        self.error.set_text(text or "")

    def set_warning(self, text: str | None) -> None:
        self.warning.set_text(text or "")

    def set_save_enabled(self, enabled: bool) -> None:
        self.save_menu_button.set_enabled(enabled)
        self.save_button.set_enabled(enabled)
        self.plantuml_button.set_enabled(enabled)
