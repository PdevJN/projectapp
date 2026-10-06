"""ガントチャートの描画(NiceGUI要素とCSS)。"""

import html
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time

from nicegui import Client, context, ui
from nicegui.events import ValueChangeEventArguments

from projectapp import arrange
from projectapp.arrange import Position
from projectapp.calendar import DayKind, day_kind
from projectapp.config import (
    DEFAULT_NAME_WIDTH_PX,
    MAX_NAME_WIDTH_PX,
    MIN_NAME_WIDTH_PX,
    parse_name_width,
)
from projectapp.filtering import TaskFilter, matches, visible_task_indexes
from projectapp.gantt_drag import CHART_DRAG_CSS, CHART_DRAG_JS
from projectapp.models import Priority, Project, Section, Status, Task
from projectapp.timeline import (
    in_range,
    Band,
    Column,
    Overload,
    ProgressState,
    Scale,
    bar_span,
    build_columns,
    clip_overloads,
    current_progress,
    deadline_position,
    effective_end,
    expected_progress,
    interval_span,
    is_overdue,
    month_bands,
    overallocations,
    progress_state,
    year_bands,
)

RESIZE_EDGE_PX = 6  # 名前の欄の右端の、幅の調整の掴み場所の幅(Task 4 で gantt_drag へ移す)
NAME_WIDTH_PROPS = (  # JS が範囲と掴み場所の幅を読む。定義元は Python の定数
    f"data-chart-content data-name-min={MIN_NAME_WIDTH_PX} data-name-max={MAX_NAME_WIDTH_PX}"
    f" data-name-default={DEFAULT_NAME_WIDTH_PX} data-name-edge={RESIZE_EDGE_PX}"
)
ROW_HEIGHT_PX = 32
COLUMN_WIDTH_PX = {Scale.DAY: 40, Scale.WEEK: 56, Scale.MONTH: 80}
KIND_COLORS = {
    DayKind.SATURDAY: "rgba(66, 165, 245, 0.18)",
    DayKind.SUNDAY: "rgba(244, 143, 177, 0.22)",
    DayKind.HOLIDAY: "rgba(129, 199, 132, 0.28)",
}
BAND_HEIGHT_PX = 22  # 年・月の帯の高さ
HEADER_HEIGHT_PX = 44  # 日次の日付と(曜日)の2段
WEEKDAYS = "月火水木金土日"
DEADLINE_MARKER_HALF_PX = 6  # 「◆」の幅の半分。締切の位置が目印の中心に来るようにずらす
DEADLINE_COLOR = "#f57c00"  # 赤は予定超過の背景と競合するので使わない
OVERLOAD_STRIPES = (  # 割り当て合計が100%を超える期間の縞。タスクの色に依存しないよう白と黒の半透明を重ねる
    "repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 4px, rgba(0,0,0,0.35) 4px 8px)"
)
MIN_BAR_PX = 4  # 幅0や終了が開始より前のタスクも、見える細い棒で出す
PLANNED_OPACITY = 0.4  # 実績を重ねるため、予定の棒は半透明にする(背景の色だけ。縞は薄くしない)
BAR_TOP_PX = 6
BAR_HEIGHT_PX = ROW_HEIGHT_PX - 12
ACTUAL_HEIGHT_PX = BAR_HEIGHT_PX // 2  # 実績の棒は、予定の棒の下半分
ACTUAL_TOP_PX = BAR_TOP_PX + BAR_HEIGHT_PX - ACTUAL_HEIGHT_PX
OVERDUE_COLOR = "rgba(239, 83, 80, 0.18)"  # 予定超過のタスク行の背景
# 進捗の状態を示す枠線の色と印。赤は予定超過の背景、橙は◆(締切)と競合するので使わない。通常は何も出さない
PROGRESS_STATE_COLORS = {
    ProgressState.DELAYED: "#b26a00",
    ProgressState.AHEAD: "#00897b",
    ProgressState.DONE: "#757575",
    ProgressState.LATE_DONE: "#8e24aa",
}
MARK_WIDTH_PX = 18  # 印(✓! が最も広い)が占める幅の見積もり。◆との重なりの判定に使う
MARK_GAP_PX = 4  # 印と、棒・◆との間の余白
# タスクの状態別の、棒(予定・進捗の塗り・実績)の色。タスクごとの色(task.color)は棒には使わない。CSS 変数 --scolor 経由
STATUS_COLORS = {
    Status.NOT_STARTED: "#78909c",
    Status.RUNNING: "#1e88e5",
    Status.PAUSED: "#fb8c00",
    Status.DONE: "#9e9e9e",
}
STATUS_DARK_COLORS = {  # ダークテーマでは、暗い背景に沈まないよう明るい色に替える
    Status.NOT_STARTED: "#b0bec5",
    Status.RUNNING: "#64b5f6",
    Status.PAUSED: "#ffb74d",
    Status.DONE: "#bdbdbd",
}
STATUS_CLASSES = {
    Status.NOT_STARTED: "status-not-started",
    Status.RUNNING: "status-running",
    Status.PAUSED: "status-paused",
    Status.DONE: "status-done",
}
STATUS_COLOR_VAR = "var(--scolor)"
# 優先度ごとの、名前の欄の背景色。赤は予定超過の背景と競合するので使わない。CSS 変数 --pbg 経由
PRIORITY_BACKGROUNDS = {
    Priority.HIGH: "#ffe0b2",
    Priority.MEDIUM: "#fff9c4",
    Priority.LOW: "#bbdefb",
}
PRIORITY_DARK_BACKGROUNDS = {  # ダークテーマでは、暗い背景に合う濃さに替える
    Priority.HIGH: "#6b4a1f",
    Priority.MEDIUM: "#5f5a1c",
    Priority.LOW: "#1f3f5f",
}
PRIORITY_CLASSES = {
    Priority.HIGH: "prio-high",
    Priority.MEDIUM: "prio-medium",
    Priority.LOW: "prio-low",
}
PRIORITY_BACKGROUND_VAR = "var(--pbg)"
PRIORITY_CSS = "\n".join(
    f".{cls} {{ --pbg: {PRIORITY_BACKGROUNDS[priority]}; }}\n"
    f"body.body--dark .{cls} {{ --pbg: {PRIORITY_DARK_BACKGROUNDS[priority]}; }}"
    for priority, cls in PRIORITY_CLASSES.items()
)
@dataclass(frozen=True)
class ViewOptions:
    """ガントチャートの表示の設定。既定値が、通常の画面と同じ描画になる。"""

    period: tuple[date, date] | None = None  # 表示する期間 [開始日, 終了日]。None は、基準日とバーから決める
    scale: Scale | None = None  # None は、ツールバーのスケール
    show_chips: bool = True  # 名前欄のチップと進捗
    show_alerts: bool = True  # 予定超過の赤みと、割り当て超過の縞
    read_only: bool = False  # 編集の部品・クリック・ドラッグをなくす


# 名前の右のチップ。名前だけが縮み、チップは縮めない
CODE_CHIP_STYLE = (
    "flex: none; max-width: 56px; padding: 0 6px; font-size: 10px; line-height: 16px;"
    " border: 1px solid rgba(128, 128, 128, 0.6); border-radius: 8px"
)
ASSIGNEE_CHIP_STYLE = (
    "flex: none; width: 16px; height: 16px; line-height: 16px; text-align: center;"
    " font-size: 10px; border-radius: 50%; background: rgba(128, 128, 128, 0.3)"
)
PROGRESS_TEXT_STYLE = "flex: none; font-size: 10px"
# 実績の区間の間(休んでいた期間)の点線。実績の棒の中央の高さに、1px の破線を引く
ACTUAL_GAP_BACKGROUND = (
    f"repeating-linear-gradient(90deg, {STATUS_COLOR_VAR} 0 4px, transparent 4px 8px)"
    " center / 100% 1px no-repeat"
)
STATUS_CSS = "\n".join(
    f".{cls} {{ --scolor: {STATUS_COLORS[status]}; }}\n"
    f"body.body--dark .{cls} {{ --scolor: {STATUS_DARK_COLORS[status]}; }}"
    for status, cls in STATUS_CLASSES.items()
)
# ダークテーマでは、同じ色が暗い背景(とのせる赤み)に沈むので、明るい色に替える。どちらも CSS 変数 --pstate 経由
PROGRESS_STATE_DARK_COLORS = {
    ProgressState.DELAYED: "#ffb74d",
    ProgressState.AHEAD: "#4db6ac",
    ProgressState.DONE: "#bdbdbd",
    ProgressState.LATE_DONE: "#ce93d8",
}
PROGRESS_STATE_CLASSES = {
    ProgressState.DELAYED: "pstate-delayed",
    ProgressState.AHEAD: "pstate-ahead",
    ProgressState.DONE: "pstate-done",
    ProgressState.LATE_DONE: "pstate-late-done",
}
PROGRESS_CSS = "\n".join(
    f".{cls} {{ --pstate: {PROGRESS_STATE_COLORS[state]}; }}\n"
    f"body.body--dark .{cls} {{ --pstate: {PROGRESS_STATE_DARK_COLORS[state]}; }}"
    for state, cls in PROGRESS_STATE_CLASSES.items()
)
PROGRESS_STATE_MARKS = {
    ProgressState.DELAYED: "▼",
    ProgressState.AHEAD: "▲",
    ProgressState.DONE: "✓",
    ProgressState.LATE_DONE: "✓!",
}
GRID_BORDER = "1px solid rgba(128, 128, 128, 0.3)"  # 格子線。両テーマで見える半透明の灰色
ADD_ROW_HEIGHT_PX = 24  # 追加行は通常の行より細くする
ARROW_EXPANDED = "expand_more"
ARROW_COLLAPSED = "chevron_right"
ROW_STYLE = f"height: {ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
ADD_ROW_STYLE = f"height: {ADD_ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
# IME の変換確定の Enter は無視する。Safari 系は確定時に isComposing が偽でも keyCode が 229 になる
SEARCH_ENTER_JS = "(e) => { if (!e.isComposing && e.keyCode !== 229) emit(e.target.value); }"
SCROLLBAR_ROOM_PX = 16  # 横スクロールバーの分の余白。WebKit は高さ auto にバーの厚みを含めない
# チャートの枠は縦横ともここでスクロールする。高さの上限は、画面の高さから、上のヘッダー
# (タイトル・ファイル選択・ボタン・ツールバー)と、右下のヘルプのボタンの分を引いた値
# (どちらも固定の見積もり。実機で合わせる)
CHART_TOP_OFFSET_PX = 190
FAB_ZONE_PX = 100  # ヘルプのボタン: 下から18px + 高さ56px + 余白
CHART_MAX_HEIGHT = f"calc(100vh - {CHART_TOP_OFFSET_PX + FAB_ZONE_PX}px)"
# 固定する要素の重なり。見出し > タスク名の列 > 棒・縞・格子線。見出しの中では左端の空白が帯より手前
STICKY_Z_SPACER, STICKY_Z_NAME, STICKY_Z_HEADER = 1, 2, 3
# 固定した要素の下を棒や縞が通るので、不透明な背景が要る(ページの背景色に合わせる)
STICKY_CSS = """
.gantt-sticky { background-color: #fff; }
body.body--dark .gantt-sticky { background-color: var(--q-dark-page, #121212); }
body.body--dark [data-chart-scroll] { color-scheme: dark; background-color: var(--q-dark-page, #121212); }
body.body--dark [data-chart-scroll]::-webkit-scrollbar { width: 12px; height: 12px; }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-track { background: var(--q-dark-page, #121212); }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-thumb { background: #555; border-radius: 6px; }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-corner { background: var(--q-dark-page, #121212); }
"""
# 絞り込みの変更時に、チャートの枠とページの両方を先頭へ戻す
SCROLL_TO_LEFT_JS = "document.querySelector('[data-chart-scroll]')?.scrollTo({left: 0})"
SCROLL_RESET_JS = (
    "document.querySelector('[data-chart-scroll]')?.scrollTo({top: 0, left: 0});"
    " window.scrollTo({top: 0})"
)
SCROLL_TO_TOP_JS = (
    "document.querySelector('[data-chart-scroll]')?.scrollTo({top: 0});"
    " window.scrollTo({top: 0})"
)
# WebKit は、親のクラス(body--dark)が実行中に変わっても、標準のスクロールバーを描き直さない。
# overflow を一度切り替えて描き直させ、スクロール位置と元の overflow は戻す
REFRESH_SCROLLBARS_JS = """
setTimeout(() => {
  const el = document.querySelector('[data-chart-scroll]');
  if (!el) return;
  const top = el.scrollTop, left = el.scrollLeft, overflow = el.style.overflow;
  el.style.overflow = 'hidden';
  void el.offsetHeight;
  el.style.overflow = overflow;
  el.scrollTo(left, top);
}, 50);
"""
ALL_ASSIGNEES = ""  # 担当者の選択で「すべて」を表す値。メンバー名は空にできない


def planned_background(color: str) -> str:
    """予定の棒の背景。要素の opacity ではなく背景だけを半透明にし、中の縞は不透明のまま残す。"""
    return f"color-mix(in srgb, {color} {PLANNED_OPACITY * 100:g}%, transparent)"


def fill_percent(task: Task) -> int | None:
    """予定の棒を塗る進捗度の割合。進捗度がなくても、終了なら100。それ以外で進捗度がなければ None。"""
    percent = current_progress(task)
    if percent is None and task.status is Status.DONE:
        return 100
    return percent


def header_cell_html(column: Column, width: int, weekday: bool) -> str:
    """見出しの 1 列ぶん(日付、日次は曜日も)の HTML。内容は日付のみで、念のためエスケープする。"""
    lines = [column.label]
    if weekday:
        lines.append(f"（{WEEKDAYS[column.start.weekday()]}）")
    inner = "".join(f"<div>{html.escape(line)}</div>" for line in lines)
    return (
        f'<div class="text-caption" data-col="{column.start.isoformat()}"'
        f' style="width:{width}px;display:flex;flex-direction:column;align-items:center">'
        f"{inner}</div>"
    )


def from_name(px: float) -> str:
    """名前の欄の右端(境界)からの距離を、CSS 変数 --name-w に追従する位置の式にする。"""
    return f"calc(var(--name-w) + {px:.1f}px)"


def sticky_left(z_index: int) -> str:
    """横スクロールで左に残す要素のスタイル。"""
    return f"position: sticky; left: 0px; z-index: {z_index}"


@dataclass
class SectionView:
    """描画したセクションの、折りたたみで切り替える部品。描き直すたびに作り直す。"""

    arrow: ui.button | None = None  # 開閉の矢印(読み取り専用では出さない)
    rows: list[ui.element] = field(default_factory=list)  # このセクションのタスクの行


@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[int], object]
    add_top_task: Callable[[], object]
    edit_task: Callable[[int | None, int], object]  # セクション番号(Noneはセクションなし), タスク番号
    move_task: Callable[[Position, Position, bool], object]  # 元, 挿入先, コピーか
    shift_task: Callable[[int | None, int, int], object]  # セクション番号, タスク番号, 日数
    set_name_width: Callable[[int], object]  # 名前の欄の幅(px)。範囲に収めた整数。保存は受け取り側


class GanttChart:
    def __init__(
        self,
        project: Project,
        holidays: dict[date, str],
        actions: GanttActions,
        now: Callable[[], datetime] = datetime.now,
        name_width: int = DEFAULT_NAME_WIDTH_PX,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.actions = actions
        self.now = now
        self.name_width = name_width  # 名前の欄の幅(px)。ドラッグで変わり、保存は呼び出し側
        self.overloads: list[Overload] = []
        self.scale = Scale.DAY
        self.options = ViewOptions()
        self.toolbar: ui.row | None = None
        self.task_filter = TaskFilter()
        self.collapsed: set[int] = set()  # 折りたたんだセクションの添字。保存しない
        self.section_views: dict[int, SectionView] = {}  # 描画中のセクションの部品
        self.search_input: ui.input | None = None
        self.assignee_select: ui.select | None = None
        self.client: Client | None = None

    def set_project(self, project: Project) -> None:
        """条件は保つ。担当者がメンバーからいなくなったときだけ、担当者の指定を外す。"""
        self.project = project
        names = {member.name for member in project.members}
        if self.task_filter.assignee not in (None, *names):
            self.task_filter = replace(self.task_filter, assignee=None)
        self.sync_assignee_select()
        self.render.refresh()

    def set_filter(self, task_filter: TaskFilter) -> None:
        if task_filter == self.task_filter:
            return
        self.task_filter = task_filter
        self.render.refresh()
        self.scroll_to_top()

    def commit_query(self, query: str | None) -> None:
        self.set_filter(replace(self.task_filter, query=(query or "").strip()))

    def on_search_changed(self, e: ValueChangeEventArguments) -> None:
        """入力中は反映しない(IME の変換中を避ける)。空になったときだけ、すぐ条件を外す。"""
        if not e.value:
            self.commit_query("")

    def handle_move(self, args: object) -> None:
        """行のドロップを受ける。絞り込み中と、不正な値は無視する。"""
        if self.task_filter.active:
            return
        parsed = arrange.parse_move(args)
        if parsed is not None:
            self.actions.move_task(*parsed)

    def handle_shift(self, args: object) -> None:
        """バーの横移動を受ける。日次スケール以外と、不正な値は無視する。"""
        if self.view_scale is not Scale.DAY:
            return
        parsed = arrange.parse_shift(args)
        if parsed is not None:
            (section, index), days = parsed
            self.actions.shift_task(section, index, days)

    def handle_name_width(self, args: object) -> None:
        """名前の欄の幅の変更を受ける。不正な値は無視し、範囲外は範囲に収める。
        描き直さない(ブラウザ側の --name-w が、すでに同じ値)。以降の描画は、この値を使う。"""
        width = parse_name_width(args.get("width") if isinstance(args, dict) else None)
        if width is None:
            return
        self.name_width = width
        self.actions.set_name_width(width)

    def drag_props(self, kind: str, key: int | str, **extra: object) -> str:
        """ドロップ先の `data-*` 属性。絞り込み中は空(ドロップできない)。"""
        if self.task_filter.active or self.options.read_only:
            return ""
        parts = [f"data-drop={kind}", f"data-si={key}"]
        parts += [f"data-{name}={value}" for name, value in extra.items()]
        return " ".join(parts)

    def toggle_section(self, si: int) -> None:
        """セクションの折りたたみを切り替える。描き直さず、行の表示と矢印だけを変える。"""
        self.collapsed.symmetric_difference_update({si})
        view = self.section_views.get(si)
        if view is None or self.options.read_only:
            return
        collapsed = si in self.collapsed
        if view.arrow is not None:
            view.arrow.props(f"icon={ARROW_COLLAPSED if collapsed else ARROW_EXPANDED}")
        if not self.task_filter.active:  # 絞り込み中は、折りたたみを無視する(表示は変えない)
            for row in view.rows:
                row.set_visibility(not collapsed)

    def expand_section(self, si: int) -> None:
        """セクションを展開する(描き直しは、呼び出し側のあとの処理に任せる)。"""
        self.collapsed.discard(si)

    def reset_collapsed(self) -> None:
        """すべて展開に戻す(描き直しは、呼び出し側のあとの処理に任せる)。"""
        self.collapsed.clear()

    def reset_filter(self) -> None:
        """条件を空に戻し、入力欄と選択にも反映する。別のプロジェクトを開いたときに使う。"""
        self.task_filter = TaskFilter()
        if self.search_input is not None:
            self.search_input.set_value("")
        if self.assignee_select is not None:
            self.assignee_select.set_value(ALL_ASSIGNEES)
        self.render.refresh()
        self.scroll_to_top()

    def assignee_options(self) -> dict[str, str]:
        options = {ALL_ASSIGNEES: "すべての担当者"}
        options.update({member.name: member.name for member in self.project.members})
        return options

    def sync_assignee_select(self) -> None:
        if self.assignee_select is not None:
            value = self.task_filter.assignee or ALL_ASSIGNEES
            self.assignee_select.set_options(self.assignee_options(), value=value)

    def refresh_scrollbars(self) -> None:
        """テーマの切り替え後に、枠のスクロールバーを新しい配色で描き直させる。"""
        if self.client is not None:
            self.client.run_javascript(REFRESH_SCROLLBARS_JS)

    def scroll_to_left(self) -> None:
        if self.client is not None:
            self.client.run_javascript(SCROLL_TO_LEFT_JS)

    def reset_scroll(self) -> None:
        if self.client is not None:
            self.client.run_javascript(SCROLL_RESET_JS)

    def scroll_to_top(self) -> None:
        if self.client is not None:
            self.client.run_javascript(SCROLL_TO_TOP_JS)

    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.holidays = holidays
        self.render.refresh()

    def set_scale(self, scale: Scale) -> None:
        self.scale = scale
        self.render.refresh()
        self.scroll_to_left()  # 列の幅が変わるので、横の位置は意味を持たない(縦は保つ)

    @property
    def view_scale(self) -> Scale:
        """描画に使うスケール。プレビューで指定されていればそれ、なければツールバーのスケール。"""
        return self.options.scale or self.scale

    def set_options(self, options: ViewOptions) -> None:
        """表示の設定を変えて、描き直す。描画のスケールが変わるときは、横のスクロールを先頭へ戻す。"""
        before = self.view_scale
        self.options = options
        if self.toolbar is not None:
            self.toolbar.set_visibility(not options.read_only)
        self.render.refresh()
        if self.view_scale != before:
            self.scroll_to_left()  # 列の幅が変わるので、横の位置は意味を持たない(縦は保つ)

    def edit_on_click(self, element: ui.element, si: int | None, ti: int) -> ui.element:
        """クリックでタスクの編集を開く。読み取り専用では何も付けない。"""
        if not self.options.read_only:
            element.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
        return element

    def content_width(self) -> int:
        """描画の全体の幅(px)。名前の列と、すべての列。画像の幅になる。"""
        columns = build_columns(self.project, self.view_scale, self.holidays, self.options.period)
        return self.name_width + COLUMN_WIDTH_PX[self.view_scale] * len(columns)

    def bar_visible(
        self, start: datetime | None, end: datetime | None, columns: list[Column]
    ) -> bool:
        """棒を描くか。期間を指定したときだけ、期間と重ならない棒を描かない(端に細い棒を出さない)。"""
        if self.options.period is None or start is None or end is None:
            return True
        return in_range(start, end, columns)

    def build(self) -> None:
        self.client = context.client
        ui.add_css(CHART_DRAG_CSS)
        ui.add_css(STICKY_CSS)
        ui.add_css(PROGRESS_CSS)
        ui.add_css(STATUS_CSS)
        ui.add_css(PRIORITY_CSS)
        ui.add_head_html(f"<script>{CHART_DRAG_JS}</script>")
        ui.on("chart_move", lambda e: self.handle_move(e.args))
        ui.on("chart_shift", lambda e: self.handle_shift(e.args))
        ui.on("chart_name_width", lambda e: self.handle_name_width(e.args))
        self.toolbar = ui.row().classes("w-full items-center no-wrap gap-4")
        with self.toolbar.mark("chart-toolbar"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).classes("shrink-0").mark("scale-toggle")
            ui.button("セクション追加", icon="add", on_click=self.actions.add_section).props(
                "flat"
            ).classes("shrink-0").mark("add-section")
            self.search_input = (
                ui.input(
                    placeholder="タスク名で検索(Enterで確定)",
                    value=self.task_filter.query,
                    on_change=self.on_search_changed,
                )
                .props("clearable dense outlined")
                .style("flex: 1 1 8rem; min-width: 6rem; max-width: 16rem")
                .on(
                    "keydown.enter",
                    lambda e: self.commit_query(e.args),
                    js_handler=SEARCH_ENTER_JS,
                )
                .mark("search-input")
            )
            self.assignee_select = (
                ui.select(
                    self.assignee_options(),
                    value=self.task_filter.assignee or ALL_ASSIGNEES,
                    on_change=lambda e: self.set_filter(
                        replace(
                            self.task_filter,
                            assignee=None if e.value == ALL_ASSIGNEES else e.value,
                        )
                    ),
                )
                .props("dense outlined")
                .style("flex: 1 1 8rem; min-width: 7rem; max-width: 12rem")
                .mark("assignee-filter")
            )
        # スクロールする枠は一度だけ作る。render は中身だけを作り直すので、描き直してもスクロール位置が保たれる
        scroll_style = (
            f"overflow: auto; max-height: {CHART_MAX_HEIGHT};"
            f" padding-bottom: {SCROLLBAR_ROOM_PX}px"
        )
        scroll = ui.element("div").classes("w-full").style(scroll_style)
        with scroll.props("data-chart-scroll").mark("chart-scroll"):
            self.render()

    @ui.refreshable_method
    def render(self) -> None:
        self.section_views = {}
        columns = build_columns(self.project, self.view_scale, self.holidays, self.options.period)
        self.overloads = overallocations(self.project, self.holidays)
        width = COLUMN_WIDTH_PX[self.view_scale]
        content = ui.element("div").style(
            f"position: relative; width: {from_name(width * len(columns))};"
            f" --name-w: {self.name_width}px"
        )
        with content.props(NAME_WIDTH_PROPS).mark("chart-content"):
            top = BAND_HEIGHT_PX * (1 if self.view_scale is Scale.MONTH else 2)
            self.gridlines(columns, width, top)
            if self.view_scale is Scale.DAY:
                self.stripes(columns, width, top)
            self.header(columns, width)
            self.no_match_message()
            for ti, task in enumerate(self.project.tasks):
                if matches(task, self.task_filter):
                    self.task_row(None, ti, task, columns, width)
            self.top_add_row()
            for si, section in enumerate(self.project.sections):
                self.section_rows(si, section, columns, width)

    def no_match_message(self) -> None:
        """絞り込み中に1件も一致しないとき(タスクが1つもないときは出さない)。"""
        tasks = self.project.all_tasks()
        if not (self.task_filter.active and tasks):
            return
        if any(matches(task, self.task_filter) for task in tasks):
            return
        ui.label("条件に一致するタスクがありません").classes("text-caption").style(
            "position: relative; padding: 8px 16px"
        ).mark("no-match")

    def top_add_row(self) -> None:
        """セクションなしのタスクの末尾に置く追加行。名前の列の右端にボタンを置く。"""
        if self.options.read_only:
            return
        row = ui.row().classes("items-center no-wrap gap-0").style(ADD_ROW_STYLE)
        row.props(self.drag_props("top-end", "top", count=len(self.project.tasks)))
        row.mark("top-end")
        with row:
            cell = ui.row().classes("items-center justify-end no-wrap gantt-sticky")
            cell.style(
                f"width: var(--name-w); padding-right: 8px; align-self: stretch;"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
            with cell:
                ui.button("タスク追加", icon="add", on_click=self.actions.add_top_task).props(
                    "flat dense size=sm"
                ).mark("add-task-top")

    def gridlines(self, columns: list[Column], width: int, top: int) -> None:
        """列の境界の縦線。全スケールで引く。年・月の帯の下から始める。"""
        cells = f'<div style="width:{width}px;border-left:{GRID_BORDER}"></div>' * len(columns)
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: var(--name-w);"
            " pointer-events: none"
        ).mark("gridlines")

    def stripes(self, columns: list[Column], width: int, top: int) -> None:
        """日次スケールの土日祝の背景。内容は定数と日付のみで利用者の入力を含まない。"""
        cells = "".join(
            f'<div style="width:{width}px;background:'
            f'{KIND_COLORS.get(day_kind(column.start, self.holidays), "transparent")}">'
            "</div>"
            for column in columns
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: var(--name-w);"
            " pointer-events: none"
        ).mark("stripes")

    def header(self, columns: list[Column], width: int) -> None:
        """年・月の帯(結合セル)と、日・曜日の見出し。月次スケールに月の帯はない。"""
        header_style = f"position: sticky; top: 0px; z-index: {STICKY_Z_HEADER}"
        with ui.column().classes("gap-0 gantt-sticky").style(header_style).mark("chart-header"):
            self.band_row(year_bands(columns), width, "year-band")
            if self.view_scale is not Scale.MONTH:
                self.band_row(month_bands(columns), width, "month-band")
            self.label_row(columns, width)

    def header_spacer(self, marker: str) -> None:
        """見出しの左端の空白。縦にも横にも固定された見出しの中で、横スクロールでも左に残る。"""
        spacer = ui.element("div").classes("gantt-sticky")
        spacer.style(
            f"width: var(--name-w); align-self: stretch; {sticky_left(STICKY_Z_SPACER)}"
        )
        spacer.mark(marker)

    def band_row(self, bands: list[Band], width: int, marker: str) -> None:
        style = f"height: {BAND_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            self.header_spacer(f"{marker}-spacer")
            for band in bands:
                cell = ui.element("div").style(
                    f"width: {band.count * width}px; border-left: {GRID_BORDER};"
                    " white-space: nowrap"
                )
                with cell.mark(marker):
                    # 帯が画面より広くても、名前の列の右端に文字が残るよう、帯の中で固定する
                    ui.label(band.label).classes("text-caption").style(
                        f"position: sticky; left: var(--name-w); display: inline-block;"
                        " padding-left: 8px"
                    ).mark(f"{marker}-label")

    def label_row(self, columns: list[Column], width: int) -> None:
        height = HEADER_HEIGHT_PX if self.view_scale is Scale.DAY else ROW_HEIGHT_PX
        style = f"height: {height}px; position: relative; border-bottom: {GRID_BORDER}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
            self.header_spacer("label-row-spacer")
            # 列ごとに要素を作ると、描画の大半を占めるので、日付と曜日は 1 つの HTML にまとめる(格子線・縞と同じ)
            day = self.view_scale is Scale.DAY
            cells = "".join(header_cell_html(column, width, weekday=day) for column in columns)
            ui.html(f'<div style="display:flex">{cells}</div>', sanitize=False).style(
                "flex: none"
            ).mark("label-row-cells")

    def section_rows(
        self, si: int, section: Section, columns: list[Column], width: int
    ) -> None:
        collapsed = si in self.collapsed and not self.options.read_only
        visible = visible_task_indexes(section, self.task_filter, collapsed)
        if self.task_filter.active and not visible:
            return
        view = self.section_views[si] = SectionView()
        header = ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE)
        header.props(self.drag_props("section", si, count=len(section.tasks)))
        header.mark(f"section-{si}")
        with header:
            name = ui.row().classes("items-center no-wrap gap-2 gantt-sticky")
            name.style(  # 名前の列にちょうど収める(狭いと縞や格子線が見え、広いと棒を隠す)
                f"width: var(--name-w); overflow: hidden; align-self: stretch;"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
            with name.mark(f"section-name-{si}"):
                if not self.options.read_only:
                    arrow = ARROW_COLLAPSED if collapsed else ARROW_EXPANDED
                    view.arrow = ui.button(
                        icon=arrow, on_click=lambda si=si: self.toggle_section(si)
                    ).props("flat dense round size=sm").classes("shrink-0").mark(
                        f"section-toggle-{si}"
                    )
                label = ui.label(section.name).classes("text-subtitle2 ellipsis")
                label.style("min-width: 0; padding-left: 4px")  # 長い名前は縮めて、ボタンを残す
                label.tooltip(section.name).mark(f"section-label-{si}")
                if not self.options.read_only:
                    label.classes("cursor-pointer").on("click", lambda si=si: self.toggle_section(si))
                ui.label(f"({len(section.tasks)})").classes("text-caption shrink-0").mark(
                    f"section-count-{si}"
                )
                if not self.options.read_only:
                    ui.button(
                        icon="add", on_click=lambda si=si: self.actions.add_task(si)
                    ).props("flat dense round size=sm").classes("shrink-0").tooltip(
                        "タスク追加"
                    ).mark(f"add-task-{si}")
        shown = set(visible)
        for ti, task in enumerate(section.tasks):
            if self.task_filter.active and ti not in shown:
                continue  # 絞り込みで外れたタスクは、描かない
            row = self.task_row(si, ti, task, columns, width)
            row.set_visibility(ti in shown)  # 折りたたみ中は、行を作って隠しておく(開くとき作り直さない)
            view.rows.append(row)

    def task_row(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> ui.element:
        key = "top" if si is None else si
        style = ROW_STYLE
        overdue = is_overdue(task, self.project, self.holidays, self.now()) and self.options.show_alerts
        state = progress_state(task, self.project, self.holidays, self.now())
        finished = state in (ProgressState.DONE, ProgressState.LATE_DONE)
        if overdue:
            style += f"; background: {OVERDUE_COLOR}"
        row = ui.row().classes("items-center no-wrap gap-0").style(style)
        row.props(self.drag_props("row", key, ti=ti)).mark(f"row-{key}-{ti}")
        with row:
            cell = ui.row().classes(
                "items-center no-wrap gap-1 cursor-pointer gantt-sticky"
                f" {PRIORITY_CLASSES[task.priority]}"
            )
            cell_style = (
                f"width: var(--name-w); padding-left: 16px; padding-right: 4px;"
                f" align-self: stretch; background-color: {PRIORITY_BACKGROUND_VAR};"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
            if overdue:  # 不透明な背景の上に、行と同じ赤みを重ねる
                cell_style += (
                    f"; background-image: linear-gradient({OVERDUE_COLOR}, {OVERDUE_COLOR})"
                )
            cell.style(cell_style)
            self.edit_on_click(cell, si, ti)
            cell.mark(f"task-{key}-{ti}")
            if not self.task_filter.active and not self.options.read_only:
                cell.props(f"draggable=true data-drag-handle data-si={key} data-ti={ti}")
            with cell:
                name = ui.label(task.name).classes("ellipsis").style(
                    f"flex: 1 1 0; min-width: 0; line-height: {ROW_HEIGHT_PX - 1}px"
                )
                if finished:  # 終了したタスクは、名前に取り消し線を引く
                    name.style("text-decoration: line-through")
                name.mark(f"task-name-{key}-{ti}")
                if self.options.show_chips:
                    self.task_chips(key, ti, task)
            end = effective_end(task, self.project, self.holidays)
            span = bar_span(task.planned_start, end, columns)
            if span is not None and self.bar_visible(task.planned_start, end, columns):
                left, length = span
                bar_width = max(length * width, MIN_BAR_PX)
                draggable = self.view_scale is Scale.DAY and not self.options.read_only
                cursor = "grab" if draggable else "pointer"
                outline = ""
                if state in PROGRESS_STATE_COLORS:
                    outline = " outline: 2px solid var(--pstate); outline-offset: -2px;"
                bar = ui.element("div").style(
                    f"position: absolute; left: {from_name(left * width)};"
                    f" width: {bar_width:.1f}px; top: {BAR_TOP_PX}px;"
                    f" height: {BAR_HEIGHT_PX}px;"
                    f" background: {planned_background(STATUS_COLOR_VAR)};"
                    f" border-radius: 4px; cursor: {cursor}; overflow: hidden;{outline}"
                    " user-select: none; touch-action: none"
                )
                bar.classes(STATUS_CLASSES[task.status])
                if state in PROGRESS_STATE_CLASSES:
                    bar.classes(PROGRESS_STATE_CLASSES[state])
                self.edit_on_click(bar, si, ti)
                bar.mark(f"bar-{key}-{ti}")
                if draggable:
                    least = arrange.min_shift_days(task, self.project.base_date)
                    bar.props(
                        f"data-bar data-si={key} data-ti={ti} data-day-width={width}"
                        f" data-min-days={least}"
                    )
                with bar:
                    self.progress_fill(key, ti, task, columns, end)
                    if self.options.show_alerts:
                        self.overload_stripes(key, ti, task, left, bar_width, columns, width)
                mark_left = self.marker_left(task, columns, width, left * width + bar_width)
                total = width * len(columns)
                if self.options.period is None or mark_left <= total - MARK_WIDTH_PX:
                    self.progress_marker(key, ti, task, state, mark_left, end)  # 期間の右端の外へは出さない
            self.actual_bars(si, ti, task, columns, width)
            self.deadline_marker(si, ti, task, columns, width)
        return row

    def task_chips(self, key: int | str, ti: int, task: Task) -> None:
        """名前の右の、ProjectCode・担当・進捗。空のものは出さない。名前の欄の枠の中で呼ぶ。"""
        if task.project_code:
            ui.label(task.project_code).classes("ellipsis").style(CODE_CHIP_STYLE).tooltip(
                task.project_code
            ).mark(f"task-code-{key}-{ti}")
        if task.assignee:
            ui.label(task.assignee[0]).style(ASSIGNEE_CHIP_STYLE).tooltip(task.assignee).mark(
                f"task-assignee-{key}-{ti}"
            )
        percent = fill_percent(task)
        if percent is not None:
            ui.label(f"{percent}%").style(PROGRESS_TEXT_STYLE).mark(f"task-progress-{key}-{ti}")

    def progress_fill(
        self, key: int | str, ti: int, task: Task, columns: list[Column], end: datetime | None
    ) -> None:
        """予定の棒の左端から、進捗度の割合の幅を、タスクの色で不透明に塗る。縞より先に置いて、縞を手前にする。
        期間の端で切られた棒は、切る前の棒の全体に対する進捗を、見えている部分に直して塗る。"""
        percent = fill_percent(task)
        if percent is None:
            return
        shown = self.clipped_fill_percent(task, columns, end, percent)
        ui.element("div").style(
            f"position: absolute; left: 0; top: 0; bottom: 0; width: {percent if shown is None else f'{shown:g}'}%;"
            f" background: {STATUS_COLOR_VAR}; pointer-events: none"
        ).mark(f"progress-fill-{key}-{ti}")

    def clipped_fill_percent(
        self, task: Task, columns: list[Column], end: datetime | None, percent: int
    ) -> float | None:
        """切られた棒の、見えている部分に対する塗りの割合(%)。切られていない(または期間なし)なら None。"""
        start = task.planned_start
        if self.options.period is None or start is None or end is None or end <= start:
            return None
        begin = datetime.combine(columns[0].start, time.min)
        finish = datetime.combine(columns[-1].end, time.min)
        if begin <= start and end <= finish:
            return None
        left, length = interval_span(start, end, columns)
        if length <= 0:
            return 0.0
        fill_left, fill_length = interval_span(start, start + (end - start) * percent / 100, columns)
        return max(0.0, min((fill_left + fill_length - left) / length * 100, 100.0))

    def marker_left(
        self, task: Task, columns: list[Column], width: int, bar_right: float
    ) -> float:
        """印の左端(境界からの距離)。予定の棒と、それより右へ伸びる実績の棒(完了の遅れや進行中)の右に置き、
        締切の◆と重なるときは◆の右へずらす。bar_right も、境界からの距離。"""
        right = bar_right
        for actual in task.actuals:
            finish = actual.end if actual.end is not None else self.now()
            if not self.bar_visible(actual.start, finish, columns):
                continue  # 期間の外の実績は、描かないので、印をずらさない
            start, length = interval_span(actual.start, finish, columns)
            right = max(right, start * width + max(length * width, MIN_BAR_PX))
        left = right + MARK_GAP_PX
        position = None if task.deadline is None else deadline_position(task.deadline, columns)
        if position is not None:
            center = position * width
            diamond_left, diamond_right = center - DEADLINE_MARKER_HALF_PX, center + DEADLINE_MARKER_HALF_PX
            if diamond_left < left + MARK_WIDTH_PX and left < diamond_right:
                left = diamond_right + MARK_GAP_PX
        return left

    def progress_marker(
        self,
        key: int | str,
        ti: int,
        task: Task,
        state: ProgressState | None,
        mark_left: float,
        end: datetime | None,
    ) -> None:
        """棒の右に、状態の印を小さく出す(位置は marker_left)。通常と判定できないときは出さない。"""
        if state not in PROGRESS_STATE_MARKS:
            return
        tip = state.value
        percent = current_progress(task)
        if state in (ProgressState.DELAYED, ProgressState.AHEAD) and percent is not None:
            if task.planned_start is not None and end is not None:
                expected = expected_progress(task.planned_start, end, self.now())
                tip = f"{state.value}(進捗 {percent}% / 予定 {expected:.0f}%)"
        ui.label(PROGRESS_STATE_MARKS[state]).style(
            f"position: absolute; left: {from_name(mark_left)}; top: {BAR_TOP_PX}px;"
            f" line-height: {BAR_HEIGHT_PX}px; font-size: 11px; color: var(--pstate)"
        ).classes(PROGRESS_STATE_CLASSES[state]).tooltip(tip).mark(f"progress-state-{key}-{ti}")

    def actual_bars(
        self,
        si: int | None,
        ti: int,
        task: Task,
        columns: list[Column],
        width: int,
    ) -> None:
        """実績の棒。予定の棒の下半分に、不透明で重ねる。進行中は現在時刻まで。ドラッグはできない。色は状態の色。"""
        key = "top" if si is None else si
        for n, actual in enumerate(task.actuals):
            finish = actual.end if actual.end is not None else self.now()
            if not self.bar_visible(actual.start, finish, columns):
                continue
            left, length = interval_span(actual.start, finish, columns)
            bar = ui.element("div").style(
                f"position: absolute; left: {from_name(left * width)};"
                f" width: {max(length * width, MIN_BAR_PX):.1f}px;"
                f" top: {ACTUAL_TOP_PX}px; height: {ACTUAL_HEIGHT_PX}px;"
                f" background: {STATUS_COLOR_VAR}; border-radius: 3px; cursor: pointer;"
                " user-select: none; overflow: hidden"
            ).classes(STATUS_CLASSES[task.status])
            self.edit_on_click(bar, si, ti)
            bar.mark(f"actual-{key}-{ti}-{n}")
            if actual.progress is not None:
                with bar:
                    ui.label(f"{actual.progress}%").style(
                        f"font-size: 10px; line-height: {ACTUAL_HEIGHT_PX}px; padding: 0 4px;"
                        " color: #fff; text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);"
                        " white-space: nowrap; pointer-events: none"
                    ).mark(f"actual-progress-{key}-{ti}-{n}")
        for n in range(len(task.actuals) - 1):
            before, after = task.actuals[n], task.actuals[n + 1]
            if before.end is None or after.start <= before.end:
                continue  # 進行中の区間の後ろ、隙間なし、重なり・逆順(手で編集したファイル)は引かない
            if not self.bar_visible(before.end, after.start, columns):
                continue
            left, length = interval_span(before.end, after.start, columns)
            gap = ui.element("div").style(
                f"position: absolute; left: {from_name(left * width)};"
                f" width: {length * width:.1f}px;"
                f" top: {ACTUAL_TOP_PX}px; height: {ACTUAL_HEIGHT_PX}px;"
                f" background: {ACTUAL_GAP_BACKGROUND}; cursor: pointer; user-select: none"
            ).classes(STATUS_CLASSES[task.status])
            self.edit_on_click(gap, si, ti)
            gap.mark(f"actual-gap-{key}-{ti}-{n}")

    def overload_stripes(
        self,
        key: int | str,
        ti: int,
        task: Task,
        bar_left: float,
        bar_width: float,
        columns: list[Column],
        width: int,
    ) -> None:
        """棒の内側に、割り当て合計が100%を超える期間の縞を重ねる。棒の外にははみ出さない。"""
        clipped = clip_overloads(task, self.project, self.holidays, self.overloads)
        for n, overload in enumerate(clipped):
            start, length = interval_span(overload.start, overload.end, columns)
            left_px = max((start - bar_left) * width, 0.0)
            width_px = min(length * width, bar_width - left_px)
            if width_px <= 0:
                continue
            ui.element("div").style(
                f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px;"
                f" top: 0; bottom: 0; background: {OVERLOAD_STRIPES}; pointer-events: none"
            ).mark(f"overload-{key}-{ti}-{n}")
        if clipped:
            peak = round(max(o.total for o in clipped) * 100)
            first, last = clipped[0], clipped[-1]
            ui.tooltip(
                f"{first.member} の割り当てが最大{peak}%"
                f"({first.start:%Y-%m-%d}〜{last.end:%Y-%m-%d})"
            )

    def deadline_marker(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """締切がある行に、締切の位置へ「◆」を出す。表示範囲の外なら出さない。"""
        if task.deadline is None:
            return
        position = deadline_position(task.deadline, columns)
        if position is None:
            return
        key = "top" if si is None else si
        left = position * width - DEADLINE_MARKER_HALF_PX
        marker = ui.label("◆").style(
            f"position: absolute; left: {from_name(left)}; top: 4px; line-height: 1;"
            f" color: {DEADLINE_COLOR}; cursor: pointer"
        )
        self.edit_on_click(marker, si, ti)
        marker.tooltip(f"締切 {task.deadline:%Y-%m-%d %H:%M}").mark(f"deadline-{key}-{ti}")
