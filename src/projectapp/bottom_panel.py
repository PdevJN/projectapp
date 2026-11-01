"""ガントチャートの下部パネルの描画(要望 95)。内容は`PanelContent`で受け取り、計算はしない。"""

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from projectapp.avatar import avatar
from projectapp.bottom_info import (
    DASH,
    LEGEND,
    STATUS_CLASS,
    STATUS_ICON,
    AssignmentCell,
    AssignmentLayout,
    AssignmentTable,
    PeriodSummary,
    TaskDetail,
    TodayRow,
)
from projectapp.models import Status

TABS = {"today": "今日の予定", "legend": "凡例"}
CELL_STYLE = "text-align: center; padding: 1px 2px; font-size: 12px; overflow: hidden"
DEFAULT_LAYOUT = AssignmentLayout(160, 40)

# ガントチャートと割り当て表の横スクロールを連動させる(ページに一度だけ仕掛ける)。scroll は親に伝わらないので、キャプチャで拾う。
# 相手の位置が(ほぼ)同じなら合わせ直さない。これで、合わせた側の scroll イベントが、こちらをもう一度動かすことがない
ASSIGNMENT_SYNC_JS = """
(() => {
  if (window.__assignmentSync) return;
  window.__assignmentSync = true;
  document.addEventListener('scroll', (e) => {
    const t = e.target;
    if (!t || !t.matches) return;
    // こちらが合わされた結果の scroll イベントは 1 回だけ無視する(慣性スクロール中に、古い値で相手を引き戻さない)
    if (t.__syncTo !== undefined && Math.abs(t.scrollLeft - t.__syncTo) <= 0.5) { t.__syncTo = undefined; return; }
    t.__syncTo = undefined;
    let other = null;
    if (t.matches('[data-chart-scroll]')) other = document.querySelector('[data-assignment-scroll]');
    else if (t.matches('[data-assignment-scroll]')) other = document.querySelector('[data-chart-scroll]');
    if (other && Math.abs(other.scrollLeft - t.scrollLeft) > 0.5) {
      const before = other.scrollLeft;
      other.scrollLeft = t.scrollLeft;
      if (other.scrollLeft !== before) other.__syncTo = other.scrollLeft;  // 動いたときだけ、そのイベントを待つ
    }
  }, true);
})();
"""
# 表を描き直したあと、チャートの横位置へ合わせる(描き直しで先頭に戻らないように)
ASSIGNMENT_ALIGN_JS = (
    "requestAnimationFrame(() => {"
    " const chart = document.querySelector('[data-chart-scroll]');"
    " const table = document.querySelector('[data-assignment-scroll]');"
    " if (chart && table) table.scrollLeft = chart.scrollLeft; })"
)
LOAD_COLOR = "rgba(76, 139, 245, {alpha:.2f})"
OVER_STRIPE = "repeating-linear-gradient(45deg, rgba(220, 53, 69, 0.6) 0 4px, transparent 4px 8px)"


@dataclass
class PanelContent:
    detail: TaskDetail | None
    summary: PeriodSummary
    today: list[TodayRow]
    assignment: AssignmentTable | None = None  # `割り当て`ビューのときだけ作る
    layout: AssignmentLayout | None = None  # 同上。ガントチャートに合わせた列幅


class BottomPanel:
    def __init__(
        self,
        on_select: Callable[[list[str]], None] | None = None,
        on_toggle_view: Callable[[], None] | None = None,
    ) -> None:
        self.on_toggle_view = on_toggle_view  # 割り当てビューの切り替え(開く処理も含む)
        self.view = "info"  # "info" | "assignment"。保存しない
        self.on_select = on_select  # 工数未設定のタスクを選ぶ(Cmd/Ctrl クリックと同じ)
        self.content: PanelContent | None = None
        self.tab = "today"  # 保存しない。開くたびに今日の予定

    def build(self) -> None:
        with (
            ui.element("div")
            .classes("w-full h-full")
            .style("position: relative; overflow: hidden")
        ):
            ui.button(icon="calendar_view_week", on_click=self.press_toggle).props(
                "flat dense round size=sm"
            ).classes("text-grey-8").style(
                "position: absolute; top: 2px; right: 8px; z-index: 5"
            ).mark("bottom-view-toggle").tooltip(
                "割り当て表示の切り替え(Ctrl/Cmd+Alt/Option)"
            )
            with (
                ui.column()
                .classes("w-full h-full gap-1 p-2")
                .style("overflow: auto")
                .mark("bottom-panel")
            ):
                self.body()

    def press_toggle(self) -> None:
        if self.on_toggle_view is not None:
            self.on_toggle_view()
        else:
            self.toggle_view()

    def toggle_view(self) -> None:
        self.view = "info" if self.view == "assignment" else "assignment"
        self.body.refresh()

    def update(self, content: PanelContent) -> None:
        self.content = content
        self.body.refresh()

    @ui.refreshable_method
    def body(self) -> None:
        if self.content is None:
            return
        if self.view == "assignment":
            self.show_assignment(self.content.assignment)
            return
        if self.content.detail is not None:
            self.show_detail(self.content.detail)
            return
        with ui.row().classes("w-full items-start gap-6 no-wrap"):
            self.show_summary(self.content.summary)
            with ui.column().classes("grow gap-1"):
                self.show_tabs()

    def show_detail(self, detail: TaskDetail) -> None:
        with ui.column().classes("w-full gap-1").mark("bottom-detail"):
            ui.label(f"{detail.title}({detail.kind})").classes(
                "text-subtitle2 text-bold"
            )
            if detail.others:
                ui.label(f"ほか {detail.others} 件を選択中").classes(
                    "text-caption text-grey"
                ).mark("bottom-others")
            with ui.grid(columns="auto 1fr").classes("gap-x-4 gap-y-0"):
                for label, value in detail.lines:
                    ui.label(label).classes("text-caption text-grey")
                    ui.label(value)
            for note in detail.notes:
                ui.label(note).classes("text-caption text-negative")

    def show_summary(self, s: PeriodSummary) -> None:
        with ui.column().classes("gap-0 shrink-0").mark("bottom-summary"):
            ui.label("表示中のタスクの集計").classes("text-subtitle2 text-bold")
            percent = DASH if s.percent is None else f"{s.percent:.0f}%"
            ui.label(f"{s.total} 件 / 進捗 {percent}")
            with ui.row().classes("items-center gap-0"):
                ui.label("工数 " + (f"{s.hours:.1f}h" if s.hours > 0 else DASH))
                if s.no_effort:
                    self.show_no_effort(s)
            with ui.row().classes("items-center gap-2"):
                for status in Status:
                    ui.label(f"{status.value} {s.counts[status]}").classes(
                        STATUS_CLASS[status]
                    ).style("color: var(--scolor); font-weight: 500").mark(
                        "bottom-status-count"
                    )
            with ui.row().classes("items-center gap-2"):
                ui.label(f"遅れ {s.overdue} 件").classes(
                    "text-negative" if s.overdue else ""
                )
                ui.label(f"警告 {s.warned} 件").classes(
                    "text-warning" if s.warned else ""
                )

    def show_no_effort(self, s: PeriodSummary) -> None:
        """`(工数未設定 n 件)`。重ねると該当タスクをチップで並べ、押すと全部を選ぶ。"""
        label = (
            ui.label(f"(工数未設定 {s.no_effort} 件)")
            .classes("cursor-pointer text-primary")
            .mark("bottom-no-effort")
            .on("click", self.select_no_effort)
        )
        with label:
            with ui.tooltip().classes("bg-white text-dark shadow-4"):
                with ui.row().classes("gap-1 max-w-md"):
                    for _, name in s.no_effort_tasks:
                        ui.chip(name).props("dense outline").mark(
                            "bottom-no-effort-chip"
                        )

    def select_no_effort(self) -> None:
        if self.on_select is None or self.content is None:
            return
        ids = [task_id for task_id, _ in self.content.summary.no_effort_tasks]
        if ids:
            self.on_select(ids)

    def show_tabs(self) -> None:
        tabs = ui.tabs(on_change=self.set_tab).props("dense align=left")
        tabs.mark("bottom-tabs")
        with tabs:
            for key, label in TABS.items():
                ui.tab(key, label=label).mark(f"bottom-tab-{key}")
        tabs.value = self.tab  # 名前(文字列)で選ぶ
        if self.tab == "today":
            self.show_today()
        else:
            self.show_legend()

    def set_tab(self, event) -> None:
        if event.value != self.tab:
            self.tab = event.value
            self.body.refresh()

    def show_today(self) -> None:
        rows = self.content.today if self.content else []
        with ui.column().classes("w-full gap-0").mark("bottom-today"):
            if not rows:
                ui.label(DASH).classes("text-grey")
            for row in rows:
                progress = "" if row.progress is None else f" {row.progress}%"
                end = "" if row.end is None else f" 〜{row.end:%m/%d %H:%M}"
                with (
                    ui.row()
                    .classes(f"items-center gap-1 no-wrap {STATUS_CLASS[row.status]}")
                    .style("color: var(--scolor)")
                    .mark("bottom-today-row")
                ):
                    ui.icon(STATUS_ICON[row.status], size="1.2em").classes(
                        STATUS_CLASS[row.status]
                    ).mark("bottom-today-icon")
                    ui.label(f"{row.name}({row.assignees}){progress}{end}")

    def show_legend(self) -> None:
        """凡例。グループごとに 1 行で、横に並べる(表)。"""
        groups: dict[str, list] = {}
        for entry in LEGEND:
            groups.setdefault(entry.group, []).append(entry)
        with ui.column().classes("w-full gap-1").mark("bottom-legend"):
            for group, entries in groups.items():
                with (
                    ui.row()
                    .classes("w-full items-center gap-x-4 gap-y-1")
                    .mark("bottom-legend-group")
                ):
                    ui.label(group).classes("text-caption text-grey").style(
                        "min-width: 3.5em"
                    )
                    for entry in entries:
                        with ui.row().classes("items-center gap-1 no-wrap"):
                            chip = ui.label(entry.label).classes("px-2")
                            if entry.css_class:
                                chip.classes(entry.css_class).style(
                                    "background: var(--pbg, var(--scolor)); color: #fff"
                                    if entry.group == "状態"
                                    else "background: var(--pbg)"
                                )
                            ui.label(entry.note).classes("text-caption text-grey")

    def show_assignment(self, table: AssignmentTable | None) -> None:
        """担当者×列の割り当て率。列の幅はガントチャートと同じ px。担当者の列は左に固定する。"""
        layout = (self.content.layout if self.content else None) or DEFAULT_LAYOUT
        ui.run_javascript(
            ASSIGNMENT_ALIGN_JS
        )  # 描き直しで先頭に戻らないよう、チャートの位置へ合わせる
        with (
            ui.element("div")
            .classes("w-full")
            .props("data-assignment-scroll")
            .style(  # パネルの左右の余白(p-2)を打ち消し、表の左端をチャートと同じ位置にする
                "overflow-x: auto; margin: 0 -0.5rem; width: calc(100% + 1rem)"
            )
            .mark("bottom-assignment")
        ):
            if table is None or not table.rows:
                ui.label("割り当てのある担当者はいません").classes(
                    "text-grey q-px-sm"
                ).mark("bottom-assignment-empty")
                return
            count = len(table.labels)
            with (
                ui.element("div")
                .style(
                    f"display: grid; width: {layout.total_width(count)}px;"
                    f" grid-template-columns: {layout.grid_columns(count)}"
                )
                .mark("bottom-assignment-grid")
            ):
                ui.element("div").classes("gantt-sticky").style(
                    "position: sticky; left: 0px; z-index: 2"
                )  # 左上の空き
                for label in table.labels:
                    ui.label(label).classes("text-caption text-grey").style(CELL_STYLE)
                for row in table.rows:
                    name_cell = (
                        ui.row()
                        .classes("items-center gap-1 no-wrap gantt-sticky")
                        .style(
                            "position: sticky; left: 0px; z-index: 2; overflow: hidden;"
                            f" width: {layout.name_px}px; padding: 1px 4px"
                        )
                        .mark("bottom-assignment-name")
                    )
                    name_cell._props["title"] = (
                        row.name
                    )  # 属性値としてそのまま渡る(エスケープ不要)
                    with name_cell:
                        avatar(row.name, row.icon, 18).mark("bottom-assignment-avatar")
                        ui.label(row.name).classes("text-bold ellipsis").style(
                            "min-width: 0"
                        )
                    for cell in row.cells:
                        self.show_assignment_cell(cell)

    def show_assignment_cell(self, cell: AssignmentCell) -> None:
        markers = "bottom-assignment-cell"
        if cell.closed:
            background = "rgba(128, 128, 128, 0.18)"
            markers += " bottom-assignment-closed"
        else:
            background = LOAD_COLOR.format(alpha=min(cell.load, 1.0) * 0.7)
            if cell.over:
                background = f"{OVER_STRIPE}, {background}"
                markers += " bottom-assignment-over"
        text = "" if cell.closed or cell.load <= 0 else f"{cell.load * 100:.0f}"
        ui.label(text).style(f"{CELL_STYLE}; background: {background}").mark(markers)
