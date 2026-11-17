"""負荷の調整ダイアログ(要望 145)。選んだ人のタスクごとに、率の変更・移す・追加を選び、変えるたびに結果を見せる。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from nicegui import ui

from projectapp.dashboard import Period, PeriodKind, summarize_backlog, summarize_loads
from projectapp.forms import disposable
from projectapp.models import Project, Task
from projectapp.rebalance import (
    ADD_DEFAULT_RATE,
    Edit,
    edit_from_inputs,
    has_varying_rate,
    load_text,
    preview,
    rate_of,
    rate_text,
    stats_text,
    target_options,
    task_text,
    tasks_of,
)
from projectapp.remaining import remaining_hours

Mode = Literal["none", "rate", "move", "add"]
MODES = {"none": "そのまま", "rate": "率を変える", "move": "移す", "add": "追加"}


@dataclass
class _Row:
    mode: Mode = "none"
    name: str | None = None
    percent: float | None = None


def open_rebalance_dialog(
    owner: str,
    project: Project,
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
    on_apply: Callable[[list[Edit]], object],
) -> None:
    """`適用`を押すと、選んだ調整の一覧を`on_apply`に渡して閉じる。"""
    tasks = tasks_of(project, owner)
    options = target_options(
        project,
        owner,
        summarize_backlog(project, period, kind, now, holidays).candidates,
    )
    state = {task.id: _Row() for task in tasks}

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[44rem] max-w-full"):
        ui.label(f"負荷の調整: {owner}").classes("text-h6").mark("rebalance-title")
        if not tasks:
            ui.label("調整できるタスクがありません").classes("text-grey").mark(
                "rebalance-empty"
            )
        rows_box = ui.column().classes("w-full gap-2")
        loads_box = ui.column().classes("w-full gap-0")
        tasks_box = ui.column().classes("w-full gap-0")
        error = ui.label("").classes("text-negative").mark("rebalance-error")
        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark(
                "rebalance-cancel"
            )
            apply_button = ui.button("適用").mark("rebalance-apply")
            apply_button.set_enabled(False)

        def edits_now() -> list[Edit]:
            found: list[Edit] = []
            for task in tasks:
                row = state[task.id]
                edit = edit_from_inputs(
                    task.id, row.mode, row.name, row.percent, rate_of(task, owner)
                )
                if edit is not None:
                    found.append(edit)
            return found

        def update() -> None:
            edits = edits_now()
            loads_box.clear()
            tasks_box.clear()
            error.set_text("")
            apply_button.set_enabled(False)
            if not edits:
                current = summarize_loads(project, period, holidays).get(owner)
                if current is not None:
                    with loads_box:
                        ui.label(stats_text(owner, current)).mark(
                            f"rebalance-load-{owner}"
                        )
                return
            try:
                result = preview(project, owner, edits, period, kind, now, holidays)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            with loads_box:
                for change in result.loads:
                    better = change.after.overload_days < change.before.overload_days
                    worse = change.after.overload_days > change.before.overload_days
                    ui.label(load_text(change)).classes(
                        "text-positive" if better else "text-negative" if worse else ""
                    ).mark(f"rebalance-load-{change.name}")
            with tasks_box:
                for change in result.tasks:
                    ui.label(task_text(change)).classes("text-caption").mark(
                        f"rebalance-task-{change.task_id}"
                    )
                if result.review_count:
                    ui.label(
                        f"完了予定を見直したタスク {result.review_count} 件"
                        "(手で指定の完了予定になります)"
                    ).classes("text-caption text-grey").mark("rebalance-review")
            apply_button.set_enabled(True)

        def build_row(task: Task) -> None:
            row = state[task.id]
            current = rate_of(task, owner)
            varying = has_varying_rate(task, owner)
            with rows_box:
                with (
                    ui.column().classes("w-full gap-1").mark(f"rebalance-row-{task.id}")
                ):
                    ui.label(
                        f"{task.name}(残り {remaining_hours(task, project, holidays, now):.1f}h"
                        f" / 率 {rate_text(task, owner)})"
                    ).classes("ellipsis")
                    if task.weekly_crew:
                        note = "全週に適用"
                        if varying:
                            note += f"(今の率は{rate_text(task, owner)}。率を変えると全週が同じ率に上書きされます)"
                        ui.label(note).classes("text-caption text-grey").mark(
                            f"rebalance-note-{task.id}"
                        )
                    with ui.row().classes("items-center gap-2"):
                        mode = ui.toggle(MODES, value="none").mark(
                            f"rebalance-mode-{task.id}"
                        )
                        percent = (
                            ui.number("率(%)", min=1, max=100, precision=0)
                            .classes("w-24")
                            .mark(f"rebalance-rate-{task.id}")
                        )
                        target = (
                            ui.select(options, label="相手", value=None)
                            .classes("w-56")
                            .mark(f"rebalance-target-{task.id}")
                        )
                        reset = (
                            ui.button("戻す", on_click=lambda: mode.set_value("none"))
                            .props("flat dense")
                            .mark(f"rebalance-reset-{task.id}")
                        )
                    percent.set_visibility(False)
                    target.set_visibility(False)
                    reset.set_visibility(False)

            def on_mode(event: object) -> None:
                chosen: Mode = getattr(event, "value", "none")
                row.mode = chosen
                row.name = None if chosen in ("none", "rate") else row.name
                shown = chosen != "none"
                percent.set_visibility(shown)
                target.set_visibility(chosen in ("move", "add"))
                reset.set_visibility(shown)
                if chosen in ("none", "rate"):
                    target.set_value(None)  # 表示の相手も外す(内部の状態とそろえる)
                if chosen == "none":
                    percent.set_value(None)
                    row.percent = None
                elif chosen == "add":
                    percent.set_value(ADD_DEFAULT_RATE * 100)
                else:
                    percent.set_value(None if current is None else current * 100)
                update()

            def on_percent(event: object) -> None:
                value = getattr(event, "value", None)
                row.percent = None if value is None else float(value)
                update()

            def on_target(event: object) -> None:
                row.name = getattr(event, "value", None)
                update()

            mode.on_value_change(on_mode)
            percent.on_value_change(on_percent)
            target.on_value_change(on_target)

        for task in tasks:
            build_row(task)
        update()

        def apply() -> None:
            edits = edits_now()
            dialog.close()
            on_apply(edits)

        apply_button.on_click(apply)
    dialog.open()
