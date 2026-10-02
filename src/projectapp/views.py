"""メイン画面の骨組み。"""

from pathlib import Path

from nicegui import ui

from projectapp.config import THEMES, load_theme, save_theme
from projectapp.models import Project
from projectapp.storage import list_project_files, load_project

THEME_LABELS = {"auto": "自動", "light": "ライト", "dark": "ダーク"}
THEME_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode"}
NEW_PROJECT_NAME = "新規プロジェクト"
HELP_KEYS: list[tuple[str, str]] = []  # (キー, 機能) 機能追加時に登録する


class MainView:
    """メインパネル。現在のプロジェクトと画面部品を保持する。"""

    def __init__(self) -> None:
        self.project = Project(NEW_PROJECT_NAME)
        self.files: dict[str, Path] = {p.stem: p for p in list_project_files()}
        self.selected: str | None = None
        self.theme = load_theme()
        self.dark = ui.dark_mode()
        self.apply_theme(self.theme)

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.dark.value = None if theme == "auto" else theme == "dark"

    def set_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        save_theme(theme)
        self.theme_buttons.refresh()

    def open_selected(self) -> None:
        if self.selected is None:
            return
        self.project = load_project(self.files[self.selected])
        self.title.refresh()
        self.chart.refresh()

    def build(self) -> None:
        self.header()
        self.chart()
        self.theme_fab()
        self.help_button()

    def header(self) -> None:
        with ui.column().classes("w-full gap-2"):
            self.title()
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

    @ui.refreshable_method
    def chart(self) -> None:
        # ガントチャートの配置場所
        with ui.card().classes("w-full h-96 items-center justify-center"):
            ui.label(f"基準日: {self.project.base_date:%Y-%m-%d}")

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
