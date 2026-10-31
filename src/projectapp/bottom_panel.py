"""ガントチャートの下部パネルの描画(要望 95)。内容は`PanelContent`で受け取り、計算はしない。"""

from dataclasses import dataclass

from nicegui import ui

from projectapp.bottom_info import DASH, LEGEND, PeriodSummary, TaskDetail, TodayRow
from projectapp.models import Status

TABS = {"today": "今日の予定", "legend": "凡例"}


@dataclass
class PanelContent:
    detail: TaskDetail | None
    summary: PeriodSummary
    today: list[TodayRow]


class BottomPanel:
    def __init__(self) -> None:
        self.content: PanelContent | None = None
        self.tab = "today"  # 保存しない。開くたびに今日の予定

    def build(self) -> None:
        with (
            ui.column()
            .classes("w-full h-full gap-1 p-2")
            .style("overflow: auto")
            .mark("bottom-panel")
        ):
            self.body()

    def update(self, content: PanelContent) -> None:
        self.content = content
        self.body.refresh()

    @ui.refreshable_method
    def body(self) -> None:
        if self.content is None:
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
            ui.label(
                "工数 "
                + (f"{s.hours:.1f}h" if s.hours > 0 else DASH)
                + (f"(工数未設定 {s.no_effort} 件)" if s.no_effort else "")
            )
            ui.label(
                "・".join(f"{status.value} {s.counts[status]}" for status in Status)
            )
            ui.label(f"遅れ {s.overdue} 件・警告 {s.warned} 件")

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
                ui.label(f"{row.name}({row.assignees}){progress}{end}")

    def show_legend(self) -> None:
        with ui.column().classes("w-full gap-0").mark("bottom-legend"):
            group = ""
            for entry in LEGEND:
                if entry.group != group:
                    group = entry.group
                    ui.label(group).classes("text-caption text-grey")
                with ui.row().classes("items-center gap-2"):
                    chip = ui.label(entry.label).classes("px-2")
                    if entry.css_class:
                        chip.classes(entry.css_class).style(
                            "background: var(--pbg, var(--scolor)); color: #fff"
                            if entry.group == "状態"
                            else "background: var(--pbg)"
                        )
                    ui.label(entry.note).classes("text-caption text-grey")
