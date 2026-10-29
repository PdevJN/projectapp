"""複数タスクの一括編集のダイアログ。節ごとに「変更する」をオンにした項目だけを適用する。"""

from collections.abc import Callable
from datetime import date
from math import isfinite

from nicegui import ui

from projectapp.bulk_edit import (
    BulkChanges,
    CategoryChange,
    CrewChange,
    CrewMode,
    EffortChange,
    EffortMode,
    EndChange,
    EndMode,
    apply_bulk,
    forecast_text,
)
from projectapp.dateinput import parse_date_input
from projectapp.effortunits import EffortUnit, to_hours
from projectapp.forms import _build_assignees, disposable
from projectapp.models import MAX_ALLOCATION, MIN_ALLOCATION, Assignee, Project
from projectapp.task_dialog import AssigneeFields

UNDECIDED = "__undecided__"  # カテゴリの選択肢で「未定」を表す値
SHIFT_FORWARD, SHIFT_BACK = "後ろへ", "前へ"
EFFORT_UP, EFFORT_DOWN = "増やす", "減らす"
MAX_SHIFT_DAYS = 365
EFFORT_ERROR = "工数は 0 以上の数で入力してください"
RATE_ERROR = f"割り当て率は {MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}% で入力してください"


CREW_HELP = {
    CrewMode.ADD: "選んだメンバーを担当に加えます。すでにいる人は、割り当て率だけ更新します。",
    CrewMode.REMOVE: "選んだメンバーを担当から外します。担当がいなくなったタスクは担当なしになります。",
    CrewMode.REPLACE: "担当を、下の一覧に置き換えます。週ごとの担当は解除されます。",
}


def _whole(value: object, low: int, high: int) -> int | None:
    """low〜high の整数なら整数にする(小数・範囲外・空は None)。"""
    if not isinstance(value, (int, float)) or not isfinite(value) or value != int(value):
        return None
    return int(value) if low <= value <= high else None


def open_bulk_dialog(
    project: Project, ids: list[str], holidays: dict[date, str], on_apply: Callable[[BulkChanges], object]
) -> None:
    members = [m.name for m in project.members]
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[36rem] p-0 gap-0 no-wrap").style(
        "max-height: 88vh; max-width: 96vw; overflow: hidden"
    ).mark("bulk-dialog"):
        with ui.row().classes("w-full items-start no-wrap px-5 pt-4 pb-3"):
            with ui.column().classes("gap-0 flex-1"):
                ui.label(f"{len(ids)} 件を一括編集").classes("text-h6")
                ui.label("変更する項目をオンにすると、選んだタスクにまとめて適用します").classes("text-caption text-grey")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").mark("bulk-close")
        ui.separator()
        body = ui.column().classes("w-full gap-3 px-5 py-4").style("overflow-y: auto; flex: 1 1 auto; min-height: 0")

        def section(icon: str, title: str, marker: str) -> tuple[ui.switch, ui.column]:
            """項目 1 つぶんの枠。見出し(アイコン・名前・右端のスイッチ)と、オンのときだけ出す中身。"""
            with body, ui.card().props("flat bordered").classes("w-full gap-0 px-4 py-3"):
                with ui.row().classes("w-full items-center no-wrap gap-3"):
                    ui.icon(icon).classes("text-primary text-xl")
                    ui.label(title).classes("text-subtitle2 flex-1")
                    switch = ui.switch(value=False, on_change=lambda _e: refresh()).props("dense").mark(marker)
                content = ui.column().classes("w-full gap-2 pt-3")
            return switch, content

        def modes(options: list[str], value: str) -> ui.toggle:
            return ui.toggle(options, value=value, on_change=lambda _e: refresh()).props(
                "no-caps unelevated dense toggle-color=primary"
            )

        # 担当
        crew_on, crew_box = section("group", "担当", "bulk-crew-on")
        with crew_box:
            crew_mode = modes([m.value for m in CrewMode], CrewMode.ADD.value).mark("bulk-crew-mode")
            crew_help = ui.label("").classes("text-caption text-grey").mark("bulk-crew-help")  # モードごとの説明
            with ui.row().classes("w-full items-center no-wrap gap-4") as one_box:  # 追加・削除は 1 人
                crew_member = ui.select(members, label="メンバー", on_change=lambda _e: refresh()).classes("flex-1")
                crew_member.mark("bulk-crew-member")
                crew_rate = ui.number("割り当て率(%)", value=100, step=5, on_change=lambda _e: refresh()).classes("flex-1")
                crew_rate.mark("bulk-crew-rate")
            crew_list = AssigneeFields(
                [], project.members, lambda: refresh(), marker="bulk-crew-list", title="新しい担当者(メンバーと割り当て率)"
            )  # 置き換え

        def crew_change() -> CrewChange | str:
            mode = CrewMode(crew_mode.value)
            if mode in (CrewMode.ADD, CrewMode.REMOVE):
                if not crew_member.value:
                    return "担当のメンバーを選んでください"
                if mode is CrewMode.REMOVE:
                    return CrewChange(mode, (Assignee(crew_member.value),))
                rate = _whole(crew_rate.value, round(MIN_ALLOCATION * 100), round(MAX_ALLOCATION * 100))
                if rate is None:
                    return RATE_ERROR
                return CrewChange(mode, (Assignee(crew_member.value, rate / 100),))
            names = [name for name, _ in crew_list.rows() if name]
            if len(names) != len(set(names)):
                return "同じメンバーは 1 回までです"
            if not names:
                return "担当のメンバーを選んでください"
            try:
                chosen = _build_assignees(crew_list.rows())
            except ValueError:
                return RATE_ERROR
            return CrewChange(mode, tuple(chosen))

        # カテゴリ
        category_on, category_box = section("label", "カテゴリ", "bulk-category-on")
        with category_box:
            category = ui.select(
                {UNDECIDED: "未定", **{c.id: c.name for c in project.categories}},
                value=UNDECIDED,
                label="カテゴリ",
                on_change=lambda _e: refresh(),
            ).props("dense outlined").classes("w-full")
            category.mark("bulk-category")

        # 完了予定
        end_on, end_box = section("event", "完了予定", "bulk-end-on")
        with end_box:
            end_mode = modes([m.value for m in EndMode], EndMode.DATE.value).mark("bulk-end-mode")
            end_date = ui.input("日付(YYYY-MM-DD)", on_change=lambda _e: refresh()).props("dense outlined")
            end_date.mark("bulk-end-date")
            with ui.row().classes("items-center no-wrap gap-4") as shift_box:
                end_sign = modes([SHIFT_FORWARD, SHIFT_BACK], SHIFT_FORWARD)
                end_days = ui.number("日数(暦日)", value=1, min=1, max=MAX_SHIFT_DAYS, step=1, on_change=lambda _e: refresh())
                end_days.props("dense outlined").mark("bulk-end-days")
        end_date.on("blur", lambda _e: _normalize_date())

        def _normalize_date() -> None:
            found = parse_date_input(end_date.value or "", date.today(), True)
            if found is not None and found != end_date.value:
                end_date.set_value(found)

        def end_change() -> EndChange | str:
            if EndMode(end_mode.value) is EndMode.DATE:
                found = parse_date_input(end_date.value or "", date.today(), True)
                if found is None:
                    return "日付を YYYY-MM-DD で入力してください"
                return EndChange(EndMode.DATE, day=date.fromisoformat(found))
            days = _whole(end_days.value, 1, MAX_SHIFT_DAYS)
            if days is None:
                return f"ずらす日数は 1〜{MAX_SHIFT_DAYS} で入力してください"
            return EndChange(EndMode.SHIFT, days=days if end_sign.value == SHIFT_FORWARD else -days)

        # 工数
        effort_on, effort_box = section("schedule", "工数", "bulk-effort-on")
        with effort_box:
            effort_mode = modes([m.value for m in EffortMode], EffortMode.SET.value).mark("bulk-effort-mode")
            with ui.row().classes("w-full items-center no-wrap gap-3"):
                effort_sign = modes([EFFORT_UP, EFFORT_DOWN], EFFORT_UP)  # 増減のときだけ
                effort_value = ui.input("値", on_change=lambda _e: refresh()).props("dense outlined").classes("flex-1")
                effort_value.mark("bulk-effort-value")
                effort_unit = ui.select(
                    [u.value for u in EffortUnit], value=EffortUnit.HOURS.value, on_change=lambda _e: refresh()
                ).props("dense outlined").classes("w-24")
                effort_unit.mark("bulk-effort-unit")

        def effort_change() -> EffortChange | str:
            try:
                value = float(effort_value.value)
            except (TypeError, ValueError):
                return EFFORT_ERROR
            if not value >= 0 or not isfinite(value):  # NaN・無限大も弾く
                return EFFORT_ERROR
            hours = to_hours(value, EffortUnit(effort_unit.value), project.daily_hours)
            if effort_mode.value == EffortMode.ADJUST.value:
                return EffortChange(EffortMode.ADJUST, hours if effort_sign.value == EFFORT_UP else -hours)
            return EffortChange(EffortMode.SET, hours)

        ui.separator()
        with ui.row().classes("w-full items-center no-wrap gap-3 px-5 py-3"):
            with ui.column().classes("gap-0 flex-1"):
                forecast = ui.label("").classes("text-caption text-grey").mark("bulk-forecast")
                error = ui.label("").classes("text-caption text-negative").mark("bulk-error")
            ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark("bulk-cancel")
            apply_button = ui.button("適用", on_click=lambda: apply()).props("unelevated no-caps color=primary").mark(
                "bulk-apply"
            )

        def build_changes() -> BulkChanges | str:
            """オンの節だけを BulkChanges にする。入力が不正なら、エラーの文言を返す。"""
            crew = category_change = end = effort = None
            if crew_on.value:
                crew = crew_change()
                if isinstance(crew, str):
                    return crew
            if end_on.value:
                end = end_change()
                if isinstance(end, str):
                    return end
            if effort_on.value:
                effort = effort_change()
                if isinstance(effort, str):
                    return effort
            if category_on.value:
                category_change = CategoryChange(None if category.value == UNDECIDED else category.value)
            return BulkChanges(crew=crew, category=category_change, end=end, effort=effort)

        def show_parts() -> None:
            crew_box.set_visibility(bool(crew_on.value))
            crew_mode_value = CrewMode(crew_mode.value)
            one_box.set_visibility(crew_mode_value in (CrewMode.ADD, CrewMode.REMOVE))
            crew_rate.set_visibility(crew_mode_value is CrewMode.ADD)
            crew_list.container.set_visibility(crew_mode_value is CrewMode.REPLACE)
            crew_help.set_text(CREW_HELP[crew_mode_value])
            category_box.set_visibility(bool(category_on.value))
            end_box.set_visibility(bool(end_on.value))
            date_mode = EndMode(end_mode.value) is EndMode.DATE
            end_date.set_visibility(date_mode)
            shift_box.set_visibility(not date_mode)
            effort_box.set_visibility(bool(effort_on.value))
            effort_sign.set_visibility(effort_mode.value == EffortMode.ADJUST.value)

        def refresh() -> None:
            show_parts()
            built = build_changes()
            if isinstance(built, str):
                error.set_text(built)
                forecast.set_text("")
                apply_button.disable()
                return
            error.set_text("")
            result = apply_bulk(project, ids, built, holidays)
            forecast.set_text(forecast_text(result, len(ids)))
            apply_button.set_enabled(built.any_change)

        def apply() -> None:
            built = build_changes()
            if isinstance(built, BulkChanges) and built.any_change:
                dialog.close()
                on_apply(built)

        refresh()
    dialog.open()
