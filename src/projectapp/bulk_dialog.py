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
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[36rem]").style("max-height: 85vh; overflow: auto").mark(
        "bulk-dialog"
    ):
        ui.label(f"{len(ids)} 件を一括編集").classes("text-h6")

        # 担当
        crew_on = ui.switch("担当を変更する", on_change=lambda _e: refresh()).mark("bulk-crew-on")
        with ui.column().classes("w-full gap-1") as crew_box:
            crew_mode = ui.toggle(
                [m.value for m in CrewMode], value=CrewMode.ADD.value, on_change=lambda _e: refresh()
            ).mark("bulk-crew-mode")
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
        category_on = ui.switch("カテゴリを変更する", on_change=lambda _e: refresh()).mark("bulk-category-on")
        category = ui.select(
            {UNDECIDED: "未定", **{c.id: c.name for c in project.categories}},
            value=UNDECIDED,
            label="カテゴリ",
            on_change=lambda _e: refresh(),
        ).classes("w-full")
        category.mark("bulk-category")

        # 完了予定
        end_on = ui.switch("完了予定を変更する", on_change=lambda _e: refresh()).mark("bulk-end-on")
        with ui.column().classes("w-full gap-1") as end_box:
            end_mode = ui.toggle(
                [m.value for m in EndMode], value=EndMode.DATE.value, on_change=lambda _e: refresh()
            ).mark("bulk-end-mode")
            end_date = ui.input("日付(YYYY-MM-DD)", on_change=lambda _e: refresh()).props("dense outlined")
            end_date.mark("bulk-end-date")
            with ui.row().classes("items-center no-wrap gap-4") as shift_box:
                end_sign = ui.toggle([SHIFT_FORWARD, SHIFT_BACK], value=SHIFT_FORWARD, on_change=lambda _e: refresh())
                end_days = ui.number("日数(暦日)", value=1, min=1, max=MAX_SHIFT_DAYS, step=1, on_change=lambda _e: refresh())
                end_days.mark("bulk-end-days")
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
        effort_on = ui.switch("工数を変更する", on_change=lambda _e: refresh()).mark("bulk-effort-on")
        with ui.row().classes("items-center no-wrap gap-4") as effort_box:
            effort_mode = ui.toggle(
                [m.value for m in EffortMode], value=EffortMode.SET.value, on_change=lambda _e: refresh()
            ).mark("bulk-effort-mode")
            effort_sign = ui.toggle([EFFORT_UP, EFFORT_DOWN], value=EFFORT_UP, on_change=lambda _e: refresh())  # 増減のときだけ
            effort_value = ui.input("値", on_change=lambda _e: refresh()).props("dense outlined").mark("bulk-effort-value")
            effort_unit = ui.select(
                [u.value for u in EffortUnit], value=EffortUnit.HOURS.value, on_change=lambda _e: refresh()
            ).mark("bulk-effort-unit")

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

        forecast = ui.label("").classes("text-caption").mark("bulk-forecast")
        error = ui.label("").classes("text-negative").mark("bulk-error")

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
            category.set_visibility(bool(category_on.value))
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

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("bulk-cancel")
            apply_button = ui.button("適用", on_click=apply).mark("bulk-apply")
        refresh()
    dialog.open()
