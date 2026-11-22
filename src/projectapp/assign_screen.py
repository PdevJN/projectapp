"""アサイン専用の全画面ダイアログ(要望 168 段階 1・2)。

対象タスク 1 件の試算のコピーを持ち、`GanttChart`の埋め込みモードで読み取り専用に描く。左にチームごとの
メンバー一覧、チャートのタスク行の直下に割り当ての行(週・日のセル)を置き、メンバーをドラッグアンドドロップ
で週(日)に割り当てる。確定で`on_confirm(trial)`を呼び、キャンセルでは何も反映しない。変更があるとき
(`is_dirty`)だけ、捨てる確認を出す。
"""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import date, datetime, time, timedelta

from nicegui import ui

from projectapp import clock
from projectapp.assign_drag import (
    ASSIGN_DRAG_CSS,
    ASSIGN_DRAG_JS,
    ASSIGN_DROP_EVENT,
)
from projectapp.assign_trial import (
    AssignTrial,
    CellPlan,
    TeamGroup,
    cell_plan,
    hidden_ids,
    is_dirty,
    start_trial,
    team_groups,
    trial_project,
)
from projectapp.avatar import avatar
from projectapp.config import DEFAULT_NAME_WIDTH_PX
from projectapp.daily_crew import (
    WEEK_DAYS,
    add_member,
    merge_week,
    remove_member,
    segments,
    split_week,
)
from projectapp.forms import disposable
from projectapp.gantt import GanttActions, GanttChart, ViewOptions, from_name
from projectapp.models import Assignee, Project, Task
from projectapp.timeline import (
    DEFAULT_FISCAL_START_MONTH,
    Column,
    Scale,
    interval_span,
)

ASSIGN_SCALES = (Scale.DAY, Scale.WEEK, Scale.MONTH)
ROW_HEIGHT_PX = 40


def read_only_actions() -> GanttActions:
    """読み取り専用の画面なので、チャートからの操作は何もしない(必須のコールバックだけ空で渡す)。"""
    return GanttActions(
        add_section=lambda: None,
        add_task=lambda path: None,
        add_top_task=lambda: None,
        edit_task=lambda path, ti: None,
        move_task=lambda src, dst, copy: None,
        shift_task=lambda path, ti, days: None,
        set_name_width=lambda width: None,
    )


class AssignScreen:
    def __init__(
        self,
        project: Project,
        task: Task,
        holidays: dict[date, str],
        on_confirm: Callable[[AssignTrial], object],
        *,
        now: Callable[[], datetime] = clock.now,
        name_width: int = DEFAULT_NAME_WIDTH_PX,
        fiscal_start_month: int = DEFAULT_FISCAL_START_MONTH,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.on_confirm = on_confirm
        self.now = now
        self.name_width = name_width
        self.fiscal_start_month = fiscal_start_month
        self.trial = start_trial(task)
        self.plan: CellPlan | None = cell_plan(project, self.trial.task, holidays)
        self.chart: GanttChart | None = None
        self.dialog: ui.dialog | None = None

    def open(self, parent: ui.element | None = None) -> None:
        """`parent`は、更新(refreshable)で消されない外側の要素。なければ呼び出しの文脈の下に作る。"""
        with parent if parent is not None else nullcontext():
            ui.add_css(ASSIGN_DRAG_CSS)
            ui.add_head_html(f"<script>{ASSIGN_DRAG_JS}</script>")
            ui.on(
                ASSIGN_DROP_EVENT,
                lambda e: self.drop_member(
                    str(e.args["name"]),
                    int(e.args["week"]),
                    None if e.args["day"] is None else int(e.args["day"]),
                ),
            )
            self.build()

    def build(self) -> None:
        with (
            disposable(ui.dialog()).props("persistent maximized") as dialog,
            ui.card().classes("w-full h-full no-wrap").mark("assign-screen"),
        ):
            self.dialog = dialog
            dialog.on("escape-key", lambda _e: self.cancel())
            with ui.row().classes("w-full items-center no-wrap gap-4"):
                ui.label(self.trial.task.name).classes("text-h6 col ellipsis").mark(
                    "assign-task-title"
                )
                ui.toggle(
                    {scale: scale.value for scale in ASSIGN_SCALES},
                    value=Scale.DAY,
                    on_change=lambda e: self.set_scale(Scale(e.value)),
                ).mark("assign-scale")
                ui.button("キャンセル", on_click=self.cancel).props("flat").mark(
                    "assign-cancel"
                )
                ui.button("確定", on_click=self.confirm).props("color=primary").mark(
                    "assign-confirm"
                )
            with (
                ui.row()
                .classes("w-full no-wrap gap-2")
                .style("flex: 1 1 0; min-height: 0")
            ):
                self.members_panel(team_groups(self.project))
                with (
                    ui.element("div").classes("col").style("min-width: 0; height: 100%")
                ):
                    self.chart = GanttChart(
                        trial_project(self.project, self.trial),
                        self.holidays,
                        read_only_actions(),
                        now=self.now,
                        name_width=self.name_width,
                        fiscal_start_month=self.fiscal_start_month,
                    )
                    self.chart.task_extra = self.assign_row
                    self.chart.build_embedded(
                        ViewOptions(
                            read_only=True,
                            excluded=hidden_ids(self.project, self.trial),
                            hide_excluded=True,
                        )
                    )
        dialog.open()

    # --- 左のメンバー一覧 ---

    def members_panel(self, groups: list[TeamGroup]) -> None:
        assigned = {a.name for a in self.trial.task.assignees}
        with (
            ui.column()
            .classes("gap-2")
            .style("width: 14rem; flex: none; overflow: auto")
            .mark("assign-members")
        ):
            ui.label("メンバー").classes("text-subtitle2")
            if not groups:
                ui.label("メンバーがいません").classes("text-grey").mark(
                    "assign-no-members"
                )
            for group in groups:
                ui.label(group.name).classes("text-caption text-grey").mark(
                    f"assign-team-{group.name}"
                )
                with ui.row().classes("gap-1"):
                    for member in group.members:
                        chip = (
                            ui.row()
                            .classes("items-center no-wrap gap-1 q-px-xs")
                            .props(f'draggable=true data-assign-member="{member.name}"')
                            .style(
                                "border: 1px solid rgba(128,128,128,0.5);"
                                " border-radius: 12px"
                            )
                            .mark(f"assign-member-{member.name}")
                        )
                        with chip:
                            avatar(member.name, member.icon, 24)
                            ui.label(member.name).classes("text-body2")
                        if member.name in assigned:
                            chip.style("border-color: #1976d2; border-width: 2px")
                            chip.mark(
                                f"assign-member-{member.name}",
                                f"assign-member-assigned-{member.name}",
                            )

    # --- チャートの中の割り当ての行(`GanttChart.task_extra`) ---

    def assign_row(self, task: Task, columns: list[Column], width: int) -> None:
        if task.id != self.trial.task.id:
            return
        row = (
            ui.element("div")
            .style(f"height: {ROW_HEIGHT_PX}px; position: relative; width: 100%")
            .mark("assign-row")
        )
        with row:
            if self.plan is None:
                ui.label("開始日がないため週に分けられません").classes(
                    "text-caption text-grey"
                ).style(f"position: absolute; left: {from_name(8)}; top: 10px").mark(
                    "assign-no-start"
                )
                return
            weeks = max(self.plan.weeks, len(task.weekly_crew))
            last_day = self.plan.origin + timedelta(days=WEEK_DAYS * weeks - 1)
            crews: list[list[Assignee]] = task.weekly_crew or [
                list(task.assignees) for _ in range(weeks)
            ]
            for seg in segments(crews, task.daily_crew, self.plan.origin, last_day):
                self.cell(
                    seg.week, seg.day, seg.first, seg.last, seg.crew, columns, width
                )
            for week in range(weeks):
                self.daily_toggle(week, columns, width)

    def edges(
        self, first: date, last: date, columns: list[Column], width: int
    ) -> tuple[float, float]:
        """区間(first から last を含む)の、チャート内の左端と幅(px)。"""
        left, span = interval_span(
            datetime.combine(first, time.min),
            datetime.combine(last + timedelta(days=1), time.min),
            columns,
        )
        return left * width, span * width

    def cell(
        self,
        week: int,
        day: int | None,
        first: date,
        last: date,
        crew: list[Assignee],
        columns: list[Column],
        width: int,
    ) -> None:
        left, span = self.edges(first, last, columns, width)
        marker = f"assign-cell-{week}" if day is None else f"assign-cell-{week}-{day}"
        props = f'data-assign-cell data-week="{week}"'
        if day is not None:
            props += f' data-day="{day}"'
        with (
            ui.row()
            .classes("items-center no-wrap gap-1")
            .props(props)
            .style(
                f"position: absolute; left: {from_name(left)};"
                f" width: {max(span - 2, 0):.0f}px; top: 14px; height: 24px;"
                " border: 1px dashed rgba(128,128,128,0.6); border-radius: 4px;"
                " overflow: hidden; padding: 0 2px"
            )
            .mark(marker)
        ):
            for assignee in crew:
                self.chip(assignee.name, week, day)

    def chip(self, name: str, week: int, day: int | None) -> None:
        icon = next((m.icon for m in self.project.members if m.name == name), "")
        suffix = f"{week}-{name}" if day is None else f"{week}-{day}-{name}"
        with (
            ui.row().classes("items-center no-wrap gap-0").mark(f"assign-chip-{suffix}")
        ):
            avatar(name, icon, 18).tooltip(name)
            ui.button(
                icon="close",
                on_click=lambda n=name, w=week, d=day: self.remove_member_at(n, w, d),
            ).props("flat dense round size=xs").mark(f"assign-remove-{suffix}")

    def daily_toggle(self, week: int, columns: list[Column], width: int) -> None:
        assert self.plan is not None
        first = self.plan.origin + timedelta(days=WEEK_DAYS * week)
        left, _ = self.edges(first, first, columns, width)
        daily = week in self.trial.task.daily_crew
        ui.button(
            "週に戻す" if daily else "日ごと",
            on_click=lambda w=week: self.toggle_daily(w),
        ).props("flat dense size=xs").style(
            f"position: absolute; left: {from_name(left)}; top: -2px; z-index: 2;"
            " min-height: 16px; padding: 0 4px"
        ).mark(f"assign-daily-{week}")

    # --- 操作 ---

    def refresh(self) -> None:
        """試算のタスクから複製を作り直し、チャート(棒・完了予定・警告)と割り当ての行を描き直す。"""
        if self.chart is not None:
            self.chart.set_project(trial_project(self.project, self.trial))

    def drop_member(self, name: str, week: int, day: int | None) -> None:
        if self.plan is None:
            ui.notify("開始日がないため週に分けられません", type="warning")
            return
        if name not in {m.name for m in self.project.members}:
            ui.notify("このメンバーは名簿にいません", type="warning")
            return
        result = add_member(self.trial.task, name, week, day, weeks=self.plan.weeks)
        if result is None:
            reason = (
                "すでに割り当てています"
                if self.already_in(name, week, day)
                else "この週には割り当てられません"
            )
            ui.notify(reason, type="warning")
            return
        self.trial.task = result
        self.refresh()

    def already_in(self, name: str, week: int, day: int | None) -> bool:
        task = self.trial.task
        if not task.weekly_crew:
            return name in {a.name for a in task.assignees}
        if week >= len(task.weekly_crew):
            return False
        if week in task.daily_crew:
            days = range(WEEK_DAYS) if day is None else [day]
            return all(
                name in {a.name for a in task.daily_crew[week][j]}
                for j in days
                if 0 <= j < WEEK_DAYS
            )
        return name in {a.name for a in task.weekly_crew[week]}

    def remove_member_at(self, name: str, week: int, day: int | None) -> None:
        result = remove_member(self.trial.task, name, week, day)
        if result is None:
            ui.notify("最後の 1 人は外せません", type="warning")
            return
        self.trial.task = result
        self.refresh()

    def toggle_daily(self, week: int) -> None:
        task = self.trial.task
        result = (
            merge_week(task, week)
            if week in task.daily_crew
            else split_week(task, week)
        )
        if result is None:
            ui.notify("この週は日ごとに変えられません", type="warning")
            return
        self.trial.task = result
        self.refresh()

    def set_scale(self, scale: Scale) -> None:
        if self.chart is not None:
            self.chart.set_scale(scale)

    def confirm(self) -> None:
        self.close()
        self.on_confirm(self.trial)

    def cancel(self) -> None:
        if not is_dirty(self.trial):
            self.close()
            return
        with disposable(ui.dialog()) as ask, ui.card().mark("assign-discard"):
            ui.label("変更を捨てますか?")
            with ui.row():
                ui.button("戻る", on_click=ask.close).props("flat").mark(
                    "assign-discard-no"
                )
                ui.button("捨てる", on_click=lambda: (ask.close(), self.close())).props(
                    "color=negative"
                ).mark("assign-discard-yes")
        ask.open()

    def close(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
