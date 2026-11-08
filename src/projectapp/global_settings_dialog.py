"""全体の設定のダイアログ(全プロジェクト共通の値)。下部パネルを開くときの比率と、保存するときの履歴の残し方。"""

from collections.abc import Callable

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.config import MAX_OPEN_RATIO, MIN_OPEN_RATIO, OPEN_RATIO_STEP
from projectapp.forms import disposable
from projectapp.history_log import (
    MAX_DETAIL_DAYS,
    MAX_MAX_EVENTS,
    MIN_DETAIL_DAYS,
    MIN_MAX_EVENTS,
    HistoryKeep,
)


def open_global_settings_dialog(
    initial_ratio: int,
    initial_keep: HistoryKeep,
    on_preview: Callable[[int], object],
    on_apply: Callable[[int, HistoryKeep], bool],
    on_cancel: Callable[[], object],
) -> None:
    """動かすとすぐ反映し(プレビュー)、`適用`で保存。適用せずに閉じたら`on_cancel`で元に戻す。"""
    applied = False
    current = initial_ratio
    keep = initial_keep
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[26rem] max-w-full"):
        ui.label("全体の設定").classes("text-h6")
        ui.label("下部パネルを開くときの、ガントチャートの割合").classes("text-caption")

        def change(event: ValueChangeEventArguments) -> None:
            nonlocal current
            current = int(event.value)
            on_preview(current)

        ui.slider(
            min=MIN_OPEN_RATIO,
            max=MAX_OPEN_RATIO,
            step=OPEN_RATIO_STEP,
            value=initial_ratio,
            on_change=change,
        ).props("label-always").mark("global-settings-ratio")
        ui.label(
            "タスクを選んで下部パネルが畳まれているとき、この割合で開きます(下は残り)"
        ).classes("text-caption text-grey")
        ui.separator()
        ui.label("保存するときの履歴の残し方").classes("text-caption")

        def set_days(event: ValueChangeEventArguments) -> None:
            nonlocal keep
            if event.value is not None:
                keep = HistoryKeep(int(event.value), keep.max_events)

        def set_max(event: ValueChangeEventArguments) -> None:
            nonlocal keep
            if event.value is not None:
                keep = HistoryKeep(keep.days, int(event.value))

        ui.number(
            "細かい履歴を残す日数",
            value=initial_keep.days,
            format="%d",
            on_change=set_days,
        ).classes("w-full").mark("global-settings-history-days")
        ui.number(
            "履歴の件数の上限",
            value=initial_keep.max_events,
            format="%d",
            on_change=set_max,
        ).classes("w-full").mark("global-settings-history-max")
        ui.label(
            f"残す日数より古い履歴は、保存のときに日ごとにまとめます({MIN_DETAIL_DAYS}〜{MAX_DETAIL_DAYS} 日)。"
            f"件数が上限({MIN_MAX_EVENTS}〜{MAX_MAX_EVENTS})を超えたら、古い日から捨てます。"
        ).classes("text-caption text-grey")

        def apply() -> None:
            nonlocal applied
            if on_apply(current, keep):
                applied = True
                dialog.close()

        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark(
                "global-settings-cancel"
            )
            ui.button("適用", on_click=apply).props("no-caps").mark(
                "global-settings-apply"
            )
        dialog.on_value_change(lambda e: None if e.value or applied else on_cancel())
    dialog.open()
