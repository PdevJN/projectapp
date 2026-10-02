"""メイン画面。"""

from datetime import date
from pathlib import Path

import httpx
from nicegui import ui

from projectapp.calendar import load_cache
from projectapp.calendar import refresh_holidays as download_holidays
from projectapp.config import THEMES, load_theme, save_theme
from projectapp.forms import open_section_dialog, open_task_dialog
from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import Project, Section, Task
from projectapp.storage import BASE_DIR, list_project_files, load_project

THEME_LABELS = {"auto": "自動", "light": "ライト", "dark": "ダーク"}
THEME_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode"}
NEW_PROJECT_NAME = "新規プロジェクト"
HELP_KEYS: list[tuple[str, str]] = []  # (キー, 機能) 機能追加時に登録する


class MainView:
    """メインパネル。現在のプロジェクトと画面部品を保持する。"""

    def __init__(
        self,
        base_dir: Path = BASE_DIR,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.transport = transport
        self.project = Project(NEW_PROJECT_NAME)
        self.files: dict[str, Path] = {p.stem: p for p in list_project_files(base_dir)}
        self.selected: str | None = None
        self.theme = load_theme(base_dir)
        self.dark = ui.dark_mode()
        self.apply_theme(self.theme)
        cached = load_cache(base_dir)
        self.holidays: dict[date, str] = cached or {}
        self.needs_first_fetch = cached is None
        self.gantt = GanttChart(
            self.project,
            self.holidays,
            GanttActions(
                add_section=self.add_section,
                add_task=self.add_task,
                add_top_task=self.add_top_task,
                edit_task=self.edit_task,
            ),
        )

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.dark.value = None if theme == "auto" else theme == "dark"

    def set_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        save_theme(theme, self.base_dir)
        self.theme_buttons.refresh()

    def open_selected(self) -> None:
        if self.selected is None:
            return
        self.project = load_project(self.files[self.selected])
        self.title.refresh()
        self.gantt.set_project(self.project)

    def add_section(self) -> None:
        open_section_dialog(self.save_section)

    def save_section(self, name: str) -> None:
        self.project.sections.append(Section(name))
        self.gantt.set_project(self.project)

    def add_task(self, section_index: int) -> None:
        open_task_dialog(None, lambda task: self.save_task(section_index, None, task))

    def add_top_task(self) -> None:
        open_task_dialog(None, lambda task: self.save_task(None, None, task))

    def edit_task(self, section_index: int | None, task_index: int) -> None:
        task = self.tasks_in(section_index)[task_index]
        open_task_dialog(task, lambda t: self.save_task(section_index, task_index, t))

    def tasks_in(self, section_index: int | None) -> list[Task]:
        """セクション番号のタスク一覧。Noneはセクションに属さないタスク。"""
        if section_index is None:
            return self.project.tasks
        return self.project.sections[section_index].tasks

    def save_task(
        self, section_index: int | None, task_index: int | None, task: Task
    ) -> None:
        tasks = self.tasks_in(section_index)
        if task_index is None:
            tasks.append(task)
        else:
            tasks[task_index] = task
        self.gantt.set_project(self.project)

    async def refresh_holidays(self, quiet: bool = False) -> None:
        """祝日を取得してチャートに反映する。失敗しても画面は変えず通知だけ出す。"""
        try:
            self.holidays = await download_holidays(self.base_dir, self.transport)
        except (httpx.HTTPError, ValueError):
            ui.notify("祝日データを取得できませんでした", type="warning")
            return
        self.gantt.set_holidays(self.holidays)
        if not quiet:
            ui.notify("祝日データを更新しました")

    async def first_fetch(self) -> None:
        await self.refresh_holidays(quiet=True)

    def build(self) -> None:
        self.header()
        self.gantt.build()
        self.theme_fab()
        self.help_button()
        if self.needs_first_fetch:
            ui.timer(0.1, self.first_fetch, once=True)

    def header(self) -> None:
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("items-center gap-4"):
                self.title()
                ui.button("祝日を更新", icon="refresh", on_click=self.refresh_holidays).props(
                    "flat"
                ).mark("refresh-holidays")
            with ui.row().classes("w-full items-center justify-start gap-4"):
                ui.select(
                    list(self.files),
                    label="プロジェクトファイル",
                    on_change=lambda e: setattr(self, "selected", e.value),
                ).classes("w-64")
                ui.button("開く", icon="folder_open", on_click=self.open_selected)

    @ui.refreshable_method
    def title(self) -> None:
        ui.label(self.project.name).classes("text-h5")

    def theme_fab(self) -> None:
        with ui.page_sticky(position="top-right", x_offset=18, y_offset=18):
            with ui.fab("palette", direction="left"):
                self.theme_buttons()

    @ui.refreshable_method
    def theme_buttons(self) -> None:
        for theme in THEMES:
            color = "primary" if theme == self.theme else "grey"
            ui.fab_action(
                THEME_ICONS[theme],
                label=THEME_LABELS[theme],
                color=color,
                on_click=lambda t=theme: self.set_theme(t),
            )

    def help_button(self) -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("キー操作").classes("text-h6")
            if not HELP_KEYS:
                ui.label("登録されたキー操作はありません")
            for key, desc in HELP_KEYS:
                ui.label(f"{key}: {desc}")
            ui.button("閉じる", on_click=dialog.close)
        with ui.page_sticky(position="bottom-right", x_offset=18, y_offset=18):
            ui.button(icon="help_outline", on_click=dialog.open).props("fab")
