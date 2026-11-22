"""アサイン専用の全画面ダイアログ(要望 168 段階 1・2)。

対象タスク 1 件の試算のコピーを持ち、`GanttChart`の埋め込みモードで読み取り専用に描く。左にチームごとの
メンバー一覧、チャートのタスク行の直下に割り当ての行(週・日のセル)を置き、メンバーをドラッグアンドドロップ
で週(日)に割り当てる。確定で`on_confirm(trial)`を呼び、キャンセルでは何も反映しない。変更があるとき
(`is_dirty`)だけ、捨てる確認を出す。
"""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import date, datetime, time, timedelta
from math import isfinite

from nicegui import context, ui

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
    Segment,
    add_member,
    current_allocation,
    merge_week,
    remove_member,
    segments,
    set_allocation,
    set_allocation_all,
    split_week,
    to_weekly,
)
from projectapp.forms import disposable
from projectapp.gantt import GanttActions, GanttChart, ViewOptions, from_name
from projectapp.models import MAX_ALLOCATION, MIN_ALLOCATION, Assignee, Project, Task
from projectapp.task_dialog import RangeSlider
from projectapp.timeline import (
    DEFAULT_FISCAL_START_MONTH,
    Column,
    Scale,
    interval_span,
)

ASSIGN_SCALES = (Scale.DAY, Scale.WEEK, Scale.MONTH)
ROW_HEIGHT_PX = 40
CHIP_STEP_PX = 20  # アイコン 18px + すき間 2px
LINE_STEP_PX = 22  # セルの 1 段の高さ
ACTIVE: dict[
    str, "AssignScreen"
] = {}  # クライアント id → 今開いている画面(ドロップを受ける)
REGISTERED: set[str] = set()  # ドロップのイベントを登録済みのクライアント id


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
        self.client_id = ""
        self.members_box: ui.element | None = None
        self.rate_target: tuple[str, int, int | None] | None = None
        self.rate_dialog: ui.dialog | None = None
        self.rate_slider: RangeSlider | None = None
        self.rate_number: ui.number | None = None
        self.rate_title: ui.label | None = None

    def open(self, parent: ui.element | None = None) -> None:
        """`parent`は、更新(refreshable)で消されない外側の要素。なければ呼び出しの文脈の下に作る。"""
        with parent if parent is not None else nullcontext():
            ui.add_css(ASSIGN_DRAG_CSS)
            # 画面を開いたあとの`add_head_html`は、`<script>`が実行されない。直接実行する(重複は JS が防ぐ)
            ui.run_javascript(ASSIGN_DRAG_JS)
            self.client_id = context.client.id
            ACTIVE[self.client_id] = self
            if (
                self.client_id not in REGISTERED
            ):  # クライアントごとに 1 回だけ。受けるのは今の画面
                REGISTERED.add(self.client_id)
                client_id = self.client_id
                ui.on(ASSIGN_DROP_EVENT, lambda e: drop_on_active(client_id, e.args))
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
            self.build_rate_popup()
        dialog.open()

    # --- 左のメンバー一覧 ---

    def members_panel(self, groups: list[TeamGroup]) -> None:
        self.members_box = (
            ui.column()
            .classes("gap-2")
            .style("width: 14rem; flex: none; overflow: auto")
            .mark("assign-members")
        )
        with self.members_box:
            self.members_content(groups)

    def members_content(self, groups: list[TeamGroup]) -> None:
        assigned = {a.name for a in self.trial.task.assignees}
        if True:
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
                            .props("draggable=true")
                            .style(
                                "border: 1px solid rgba(128,128,128,0.5);"
                                " border-radius: 12px"
                            )
                            .mark(f"assign-member-{member.name}")
                        )
                        chip._props["data-assign-member"] = (
                            member.name
                        )  # 名前に引用符があっても壊れない
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
        if self.plan is None:
            self.no_start_row()
            return
        weeks = max(self.plan.weeks, len(task.weekly_crew))
        last_day = self.plan.origin + timedelta(days=WEEK_DAYS * weeks - 1)
        crews: list[list[Assignee]] = task.weekly_crew or [
            list(task.assignees) for _ in range(weeks)
        ]
        segs = segments(crews, task.daily_crew, self.plan.origin, last_day)
        # 狭いセル(日ごとの週)は、アイコンを折り返す。行の高さは、いちばん段の多いセルに合わせる
        lines = max((self.lines_needed(seg, columns, width) for seg in segs), default=1)
        row = (
            ui.element("div")
            .style(f"height: {row_height(lines)}px; position: relative; width: 100%")
            .mark("assign-row")
        )
        with row:
            for seg in segs:
                self.cell(
                    seg.week,
                    seg.day,
                    seg.first,
                    seg.last,
                    seg.crew,
                    columns,
                    width,
                    lines,
                )
            if task.weekly_crew or task.assignees:  # 担当者がいなければ日ごとにできない
                for week in range(weeks):
                    self.daily_toggle(week, columns, width)

    def no_start_row(self) -> None:
        with (
            ui.element("div")
            .style(f"height: {ROW_HEIGHT_PX}px; position: relative; width: 100%")
            .mark("assign-row")
        ):
            ui.label("開始日がないため週に分けられません").classes(
                "text-caption text-grey"
            ).style(f"position: absolute; left: {from_name(8)}; top: 10px").mark(
                "assign-no-start"
            )

    def lines_needed(self, seg: Segment, columns: list[Column], width: int) -> int:
        _, span = self.edges(seg.first, seg.last, columns, width)
        return lines_for(len(seg.crew), span)

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
        lines: int = 1,
    ) -> None:
        left, span = self.edges(first, last, columns, width)
        marker = f"assign-cell-{week}" if day is None else f"assign-cell-{week}-{day}"
        props = f'data-assign-cell data-week="{week}"'
        if day is not None:
            props += f' data-day="{day}"'
        with (
            ui.row()
            .classes("items-start")
            .props(props)
            .style(
                f"position: absolute; left: {from_name(left)};"
                f" width: {max(span - 2, 0):.0f}px; top: 14px;"
                f" height: {lines * LINE_STEP_PX}px; display: flex; flex-wrap: wrap;"
                " align-content: flex-start; gap: 2px;"
                " border: 1px dashed rgba(128,128,128,0.6); border-radius: 4px;"
                " padding: 3px 2px"
            )
            .mark(marker)
        ):
            for assignee in crew:
                self.chip(assignee, week, day)

    # --- 割り当て率のポップアップ(要望 168 段階 3a) ---

    def build_rate_popup(self) -> None:
        """率のポップアップを 1 つだけ作る。チャートの再描画で消えない場所(`refreshable`の外)に置く。"""
        with (
            ui.dialog() as popup,
            ui.card()
            .classes("gap-2")
            .style("min-width: 18rem")
            .mark("assign-rate-popup"),
        ):
            self.rate_title = (
                ui.label("").classes("text-subtitle2").mark("assign-rate-title")
            )
            # 画面の倍率(CSS zoom)の中でも、つまみがずれない標準の入力(要望 144 の学び)
            self.rate_slider = (
                RangeSlider(
                    round(MIN_ALLOCATION * 100), round(MAX_ALLOCATION * 100), 100
                )
                .classes("w-full")
                .mark("assign-rate-slider")
            )
            # min・max は付けない(付けると blur で範囲に丸めてから受け取り、範囲外を通知できない)。整数に整える
            self.rate_number = ui.number(
                "割り当て率(%)", value=100, step=1, precision=0
            ).mark("assign-rate-number")
            with ui.row().classes("w-full justify-between"):
                ui.button(
                    "このメンバーの全週に適用", on_click=self.apply_rate_all
                ).props("flat").mark("assign-rate-all")
                ui.button("閉じる", on_click=popup.close).props("flat").mark(
                    "assign-rate-close"
                )
        self.rate_dialog = popup
        slider, number = self.rate_slider, self.rate_number
        # ドラッグ中は数値欄の表示だけ合わせ、離したときに試算へ反映する
        slider.on_value_change(lambda e: number.set_value(e.value))
        slider.on_release(lambda: self.apply_rate(slider.value))
        number.on("blur", lambda _e: self.apply_rate(number.value))
        number.on("keydown.enter", lambda _e: self.apply_rate(number.value))

    def open_rate(self, name: str, week: int, day: int | None) -> None:
        self.rate_target = (name, week, day)
        self.show_rate()
        if self.rate_dialog is not None and self.rate_target is not None:
            self.rate_dialog.open()

    def show_rate(self) -> None:
        """試算の今の率を、ポップアップの見出し・スライダー・数値欄に出す。そのセルにいなければ閉じる。"""
        if self.rate_target is None:
            return
        name, week, day = self.rate_target
        current = current_allocation(self.trial.task, name, week, day)
        if (
            current is None
            or self.rate_slider is None
            or self.rate_number is None
            or self.rate_title is None
        ):
            self.rate_target = None
            if self.rate_dialog is not None:
                self.rate_dialog.close()
            return
        percent = round(current * 100, 2)
        title = f"{name} 第 {week + 1} 週"
        self.rate_title.set_text(title if day is None else f"{title} {day + 1} 日目")
        self.rate_slider.set_value(round(percent))
        self.rate_number.set_value(percent)

    def apply_rate(self, percent: object) -> None:
        if self.rate_target is None or self.plan is None:
            return
        whole = whole_percent(percent)
        if whole is None:
            ui.notify("割り当て率は 1〜100% で入れてください", type="warning")
            self.show_rate()  # 表示は直前の値に戻す
            return
        name, week, day = self.rate_target
        result = set_allocation(
            self.trial.task, name, whole / 100, week, day, weeks=self.plan.weeks
        )
        if result is None:  # 今と同じ値・そのセルにいない
            self.show_rate()
            return
        self.trial.task = result
        self.refresh()
        self.show_rate()

    def apply_rate_all(self) -> None:
        if self.rate_target is None or self.rate_number is None:
            return
        whole = whole_percent(self.rate_number.value)
        if whole is None:
            ui.notify("割り当て率は 1〜100% で入れてください", type="warning")
            self.show_rate()
            return
        result = set_allocation_all(self.trial.task, self.rate_target[0], whole / 100)
        if result is None:
            ui.notify("変わる週がありません", type="info")
            return
        self.trial.task = result
        self.refresh()
        self.show_rate()

    def chip(self, assignee: Assignee, week: int, day: int | None) -> None:
        """アイコンだけのチップ(名前と率はツールチップ)。アイコンのクリックで率のポップアップ。
        `×`は、マウスを乗せたときにアイコンの角に出す。率が 100% でなければ、角に数字を重ねる。"""
        name = assignee.name
        icon = next((m.icon for m in self.project.members if m.name == name), "")
        suffix = f"{week}-{name}" if day is None else f"{week}-{day}-{name}"
        percent = round(assignee.allocation * 100)
        with ui.element("div").classes("assign-chip").mark(f"assign-chip-{suffix}"):
            avatar(name, icon, 18).tooltip(
                name if percent == 100 else f"{name} {percent}%"
            ).style("cursor: pointer").on(
                "click", lambda n=name, w=week, d=day: self.open_rate(n, w, d)
            ).mark(f"assign-open-rate-{suffix}")
            if percent != 100:
                ui.label(str(percent)).classes("assign-rate-badge").mark(
                    f"assign-rate-badge-{suffix}"
                )
            ui.button(
                icon="close",
                on_click=lambda n=name, w=week, d=day: self.remove_member_at(n, w, d),
            ).props("flat dense round size=6px").classes("assign-remove").mark(
                f"assign-remove-{suffix}"
            )

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
        # 率を下げると完了予定が後ろへ伸びるので、セルの週の数は試算の終了に合わせて取り直す(開始日がなければそのまま)
        self.plan = cell_plan(self.project, self.trial.task, self.holidays) or self.plan
        if self.chart is not None:
            self.chart.set_project(trial_project(self.project, self.trial))
        if self.members_box is not None:
            self.members_box.clear()
            with self.members_box:
                self.members_content(team_groups(self.project))

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
        weeks = self.plan.weeks if self.plan is not None else 1
        result = remove_member(self.trial.task, name, week, day, weeks=weeks)
        if result is None:
            ui.notify("最後の 1 人は外せません", type="warning")
            return
        self.trial.task = result
        self.refresh()

    def toggle_daily(self, week: int) -> None:
        task = self.trial.task
        if not task.weekly_crew:  # 週ごとでなければ、先に週ごとにする
            weekly = to_weekly(task, self.plan.weeks if self.plan is not None else 1)
            if weekly is None:
                ui.notify("担当者がいないため、日ごとにできません", type="warning")
                return
            task = weekly
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
        if ACTIVE.get(self.client_id) is self:
            del ACTIVE[self.client_id]
        if self.rate_dialog is not None:
            self.rate_dialog.close()
        if self.dialog is not None:
            self.dialog.close()


def whole_percent(value: object) -> int | None:
    """入力された割り当て率(%)を整数に丸める。数でない・`nan`・丸めて 1〜100 の外なら None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isfinite(value):
        return None
    whole = round(value)
    if not round(MIN_ALLOCATION * 100) <= whole <= round(MAX_ALLOCATION * 100):
        return None
    return whole


def lines_for(count: int, span_px: float) -> int:
    """幅`span_px`のセルに、アイコン`count`個を並べるときの段の数(1 段に最低 1 個は入れる)。"""
    per_line = max(int((span_px - 6) // CHIP_STEP_PX), 1)
    return max(-(-count // per_line), 1)


def row_height(lines: int) -> int:
    """割り当ての行の高さ。段の数に合わせて広げる(ヘッダーのボタンの分を含む)。"""
    return max(ROW_HEIGHT_PX, 18 + lines * LINE_STEP_PX)


def drop_on_active(client_id: str, args: dict) -> None:
    """ドロップのイベントを、そのクライアントで今開いている画面に渡す。"""
    screen = ACTIVE.get(client_id)
    if screen is not None:
        day = args["day"]
        screen.drop_member(
            str(args["name"]), int(args["week"]), None if day is None else int(day)
        )
