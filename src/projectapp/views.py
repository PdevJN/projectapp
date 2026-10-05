"""メイン画面。"""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date, time
from pathlib import Path

import httpx
from nicegui import ui

from projectapp.calendar import load_cache
from projectapp.calendar import refresh_holidays as download_holidays
from projectapp.config import THEMES, load_theme, save_theme
from projectapp.forms import (
    open_file_dialog,
    open_members_dialog,
    open_name_dialog,
    open_section_dialog,
    open_settings_dialog,
    open_unsaved_dialog,
)
from projectapp import arrange
from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import ActualMode, Member, Project, Section, Task
from projectapp.storage import (
    BASE_DIR,
    list_project_files,
    load_project,
    save_project,
    validate_name,
)
from projectapp.task_dialog import open_task_dialog
from projectapp.timeline import clip_overloads, overallocations

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
        self.path: Path | None = None
        self.mark_clean()
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
                move_task=self.move_task,
                shift_task=self.shift_task,
            ),
        )

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.dark.value = None if theme == "auto" else theme == "dark"

    def set_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        self.gantt.refresh_scrollbars()  # 標準のスクロールバーは、切り替えだけでは配色が変わらない
        save_theme(theme, self.base_dir)
        self.theme_buttons.refresh()

    def mark_clean(self) -> None:
        """いまの内容を、保存済み(または開いた直後)の状態として覚える。"""
        self.snapshot = asdict(self.project)

    def is_dirty(self) -> bool:
        return asdict(self.project) != self.snapshot

    def current_name(self) -> str | None:
        return self.path.stem if self.path else None

    def request_open(self, name: str | None) -> None:
        """編集中なら確認してから開く。コンボボックスと一覧ダイアログの共通の入口。"""
        if name is None or name == self.current_name():
            return
        if not self.is_dirty():
            self.open_project(name)
            return
        self.file_select.set_value(self.current_name())  # 確認中は表示を現状に戻す
        open_unsaved_dialog(
            on_save=lambda: self.save_then(lambda: self.open_project(name)),
            on_discard=lambda: self.open_project(name),
        )

    def save_then(self, after: Callable[[], object]) -> None:
        """保存に成功したときだけ、続きの処理を行う。"""
        if self.path is None:

            def submit(name: str) -> bool:
                saved = self.save_as_new(name)
                if saved:
                    after()
                return saved

            open_name_dialog(submit, lambda name: validate_name(name, self.base_dir, new=True))
        elif self.write(overwrite=True):
            after()

    def open_project(self, name: str) -> None:
        path = self.files[name]
        try:
            project = load_project(path)
        except (OSError, ValueError, KeyError) as exc:
            ui.notify(f"開けませんでした: {exc}", type="negative")
            self.file_select.set_value(self.current_name())
            return
        self.path, self.project = path, project
        self.mark_clean()
        self.file_select.set_value(name)
        self.title.refresh()
        self.gantt.set_project(self.project)
        self.gantt.reset_filter()
        self.gantt.reset_scroll()  # 別のプロジェクトは、先頭から見せる(編集後の再描画では動かさない)

    def show_file_list(self) -> None:
        """ファイルを走査し直して、一覧ダイアログを出す。"""
        self.files = {p.stem: p for p in list_project_files(self.base_dir)}
        names = sorted(self.files)
        self.file_select.set_options(names, value=self.current_name())
        open_file_dialog(names, self.request_open)

    def open_settings(self) -> None:
        open_settings_dialog(
            self.project.daily_hours,
            self.project.work_start,
            self.apply_settings,
            self.project.actual_mode,
            self.multi_interval_count(),
        )

    def multi_interval_count(self) -> int:
        """2区間以上の実績を持つタスクの数。簡易へ戻せるかの判定に使う。"""
        return sum(1 for task in self.project.all_tasks() if len(task.actuals) > 1)

    def open_members(self) -> None:
        open_members_dialog(self.project.members, self.assigned_count, self.apply_members)

    def assigned_count(self, name: str) -> int:
        return sum(1 for task in self.project.all_tasks() if task.assignee == name)

    def apply_members(self, members: list[Member], renames: dict[str, str]) -> None:
        """メンバーを更新し、改名をタスクの担当者に伝える。保存はしない(編集中の判定に入る)。"""
        if members == self.project.members and not renames:
            return
        self.project.members = members
        if renames:
            for task in self.project.all_tasks():
                if task.assignee in renames:
                    task.assignee = renames[task.assignee]
        self.gantt.set_project(self.project)

    def apply_settings(self, hours: float, start: time, mode: ActualMode) -> None:
        """稼働設定と記録方式を更新して再描画する。完了予定は表示のたびに計算されるので、再計算の処理は要らない。保存はしない。"""
        if (
            hours == self.project.daily_hours
            and start == self.project.work_start
            and mode is self.project.actual_mode
        ):
            return
        self.project.daily_hours, self.project.work_start = hours, start
        self.project.actual_mode = mode
        self.gantt.set_project(self.project)

    def save_project_clicked(self) -> None:
        if self.path is None:
            open_name_dialog(
                self.save_as_new,
                lambda name: validate_name(name, self.base_dir, new=True),
            )
            return
        self.write(overwrite=True)

    def save_as_new(self, name: str) -> bool:
        previous = self.project.name
        self.project.name = name
        if self.write(overwrite=False):
            return True
        self.project.name = previous
        return False

    def write(self, *, overwrite: bool) -> bool:
        """保存して画面を更新する。失敗したら通知だけ出し、状態は変えない。"""
        try:
            path = save_project(self.project, self.base_dir, overwrite=overwrite)
        except FileExistsError:
            ui.notify("同じ名前のファイルがすでにあります", type="negative")
            return False
        except (ValueError, OSError) as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return False
        self.path = path
        self.mark_clean()
        self.files[path.stem] = path
        self.file_select.set_options(sorted(self.files), value=path.stem)
        self.title.refresh()
        ui.notify("保存しました")
        return True

    def add_section(self) -> None:
        open_section_dialog(self.save_section)

    def save_section(self, name: str) -> None:
        self.project.sections.append(Section(name))
        self.gantt.set_project(self.project)

    def add_task(self, section_index: int) -> None:
        open_task_dialog(
            None,
            lambda task: self.save_task(section_index, None, task),
            work_start=self.project.work_start,
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
            members=self.project.members,
        )

    def add_top_task(self) -> None:
        open_task_dialog(
            None,
            lambda task: self.save_task(None, None, task),
            work_start=self.project.work_start,
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
            members=self.project.members,
        )

    def edit_task(self, section_index: int | None, task_index: int) -> None:
        task = self.tasks_in(section_index)[task_index]
        open_task_dialog(
            task,
            lambda t: self.save_task(section_index, task_index, t),
            work_start=self.project.work_start,
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
            members=self.project.members,
            on_delete=lambda: self.delete_task(section_index, task_index),
        )

    def delete_task(self, section_index: int | None, task_index: int) -> None:
        """タスクを取り除いて再描画する。保存は自動では行わない(編集中の判定に入る)。"""
        del self.tasks_in(section_index)[task_index]
        self.gantt.set_project(self.project)

    def move_task(self, src: arrange.Position, dst: arrange.Position, copy: bool) -> None:
        """行を動かす(copy が真なら複製を置く)。位置が不正・変化なしなら何もしない。"""
        if not arrange.has_task(self.project, src) or not arrange.has_list(self.project, dst):
            return
        name = arrange.tasks_at(self.project, src[0])[src[1]].name
        if copy:
            arrange.copy_task(self.project, src, dst)
            ui.notify(f"「{name}」をコピーしました")
        elif not arrange.move_task(self.project, src, dst):
            return
        self.gantt.set_project(self.project)

    def shift_task(self, section_index: int | None, task_index: int, days: int) -> None:
        """開始予定(と入っていれば完了予定)を days 日ずらす。締切は動かさず、基準日より前へは動かさない。"""
        if days == 0 or not arrange.has_task(self.project, (section_index, task_index)):
            return
        task = self.tasks_in(section_index)[task_index]
        days = max(days, arrange.min_shift_days(task, self.project.base_date))
        if days == 0:
            return
        if not arrange.shift_task(task, days):
            if task.planned_start is not None:
                ui.notify("日付の範囲を超えるため動かせません", type="warning")
            return
        self.gantt.set_project(self.project)
        self.warn_overallocation(task)

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
        self.warn_overallocation(task)

    def warn_overallocation(self, task: Task) -> None:
        """保存したタスクが担当者の割り当て合計の超過に関わるなら、通知する(保存は妨げない)。"""
        if not task.assignee:
            return
        overloads = overallocations(self.project, self.holidays)
        mine = clip_overloads(task, self.project, self.holidays, overloads)
        if mine:
            peak = max(o.total for o in mine)
            ui.notify(
                f"{task.assignee} の割り当てが最大{round(peak * 100)}%になる期間があります",
                type="warning",
            )

    async def refresh_holidays(self, quiet: bool = False) -> None:
        """祝日を取得してチャートに反映する。失敗しても画面は変えず通知だけ出す。"""
        try:
            self.holidays = await download_holidays(self.base_dir, self.transport)
        except (httpx.HTTPError, ValueError, OSError):  # OSErrorはキャッシュの書き込み失敗
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
                self.file_select = ui.select(
                    list(self.files),
                    label="プロジェクトファイル",
                    on_change=lambda e: self.request_open(e.value),
                ).classes("w-64").mark("project-select")
                ui.button("開く", icon="folder_open", on_click=self.show_file_list)
                ui.button("保存", icon="save", on_click=self.save_project_clicked).mark(
                    "save-project"
                )
                ui.button("設定", icon="settings", on_click=self.open_settings).mark(
                    "open-settings"
                )
                ui.button("メンバー", icon="group", on_click=self.open_members).mark(
                    "open-members"
                )

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
