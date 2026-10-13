"""メイン画面。"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from pathlib import Path

import httpx
from nicegui import run, ui
from nicegui.events import KeyEventArguments

from projectapp.calendar import load_cache
from projectapp.categories import CategoryEdit
from projectapp.categories import apply_edit as apply_category_edit
from projectapp.categories import count_usage as count_category_usage
from projectapp.linkgraph import drop_task_links, link_options
from projectapp.calendar import refresh_holidays as download_holidays
from projectapp.config import (
    THEMES,
    check_project_dir,
    load_project_dir,
    load_name_width,
    load_task_layout,
    load_theme,
    load_zoom,
    resolve_project_dir,
    save_name_width,
    save_project_dir,
    save_task_layout,
    save_theme,
    save_zoom,
    step_zoom,
)
from projectapp.forms import (
    MEMBER_TABLE_CSS,
    open_commit_dialog,
    open_conflict_dialog,
    open_file_dialog,
    open_handoff_dialog,
    open_members_parameters_dialog,
    open_name_dialog,
    open_section_dialog,
    open_settings_dialog,
    open_unsaved_dialog,
)
from projectapp import arrange
from projectapp.shortcuts import Screen, help_entries, key_guard_js, label_for, resolve
from projectapp.dashboard import PeriodKind, period_for, summarize
from projectapp.dashboard_view import DashboardView
from projectapp.export import (
    HTML_TO_IMAGE_URL,
    PNG_FILE_TYPES,
    ExportError,
    ImageExporter,
    NativeImageExporter,
    default_filename,
    exceeds_canvas,
    export_pixel_ratio,
    write_png,
)
from projectapp.handoff import (
    JSON_FILE_TYPES,
    build_todos,
    summary,
    tasks_for,
    write_json,
)
from projectapp.handoff import default_filename as handoff_filename
from projectapp.filemanager import open_folder
from projectapp.gitops import FileChange, GitResult, default_message, list_changes
from projectapp.gitops import commit as commit_files_in_git
from projectapp.gitops import push as push_to_remote
from projectapp.gitstate import GitKind, GitState, describe, read_git_state, tooltip
from projectapp.gantt import GanttActions, GanttChart, ViewOptions
from projectapp.models import MAX_SECTION_DEPTH, ActualMode, Member, Project, Section, SectionPath, Task, new_id
from projectapp.preview import (
    LARGE_IMAGE_MESSAGE,
    NOT_NATIVE_MESSAGE,
    PreviewBar,
    PreviewSettings,
    check_column_count,
    coarser_notice,
    fit_scale,
    validate_period,
)
from projectapp.storage import (
    BASE_DIR,
    ExternalChange,
    backup_file,
    check_external_change,
    file_digest,
    list_project_files,
    load_project,
    save_project,
    validate_name,
)
from projectapp.task_dialog import open_task_dialog
from projectapp.urls import TemplateEdit, apply_template_edit, count_usage
from projectapp.ratios import ParameterEdit, apply_parameter_edit, deletion_impacts
from projectapp.timeline import Schedule, build_columns, clip_overloads, overallocations, visible_range

THEME_LABELS = {"auto": "自動", "light": "ライト", "dark": "ダーク"}
THEME_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode"}


@dataclass(frozen=True)
class MenuItem:
    """ヘッダーのメニューの 1 項目。keyは、割り当てたショートカットのキー(右端に薄く添える。なければ空)。"""

    text: str
    icon: str
    handler: Callable[[], object]
    marker: str
    key: str = ""
NEW_PROJECT_NAME = "新規プロジェクト"
# ヘッダーは、画面の上端・左右いっぱいの四角い帯(ui.header)。テーマカラーの背景 + 白文字(ダークは暗めのテーマカラー)。フォントは標準の 14px から -2 で 12px、
# メニューのボタンは折り返さない(縮むのはプロジェクト選択のコンボだけ。中のファイル名は 10px)。プロジェクト名は、ヘッダーの外(メイン側の左上)に、12px の太字(24px の text-h5 から。太さで区別する)。メニューのボタンは楕円型(半透明の白の背景)。開いたメニューは body 直下に出るので、`app-menu` で同じ大きさにする
HEADER_CSS = """
.app-header { background: var(--q-primary); color: #fff; font-size: 12px; padding: 4px 12px; flex-wrap: nowrap !important; overflow: hidden; }
body.body--dark .app-header { background: color-mix(in srgb, var(--q-primary) 55%, #000); }
.app-header .q-btn, .app-header .q-field { font-size: 12px; }
.app-header .q-btn { white-space: nowrap; flex: none; }
.app-header .q-btn__content { white-space: nowrap; flex-wrap: nowrap; }
.app-header .app-project-select { flex: 0 1 16rem; min-width: 8rem; }
.app-header .app-project-select .q-field__native, .app-header .app-project-select .q-field__input { font-size: 10px; }
.app-select-popup .q-item { font-size: 10px; min-height: 28px; }
.app-title { font-size: 12px; font-weight: 700; white-space: nowrap; }
.app-header .app-menu-btn { background: rgba(255, 255, 255, 0.18); padding: 0 14px; }
.app-header .app-menu-btn:hover { background: rgba(255, 255, 255, 0.3); }
.app-menu .q-item { font-size: 12px; min-height: 32px; }
.app-git-chip { flex: none; font-size: 10px; line-height: 1; padding: 4px 8px; border-radius: 9999px; background: rgba(255, 255, 255, 0.18); white-space: nowrap; cursor: pointer; }
.app-git-chip:hover { background: rgba(255, 255, 255, 0.3); }
.app-git-chip.app-git-dirty { background: #ffd54f; color: #3e2723; }
.app-git-chip.app-git-behind { background: #ffb74d; color: #3e2723; }
.app-git-chip.app-git-error { background: #ef9a9a; color: #3e2723; }
.q-tooltip { white-space: pre-line; }
"""
HANDOFF_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、書き出せます"
CHANGE_DIR_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、格納先を変更できます"
KEY_GUARD_JS = key_guard_js()


def zoom_js(percent: int) -> str:
    """画面全体の倍率をかける JS(CSS の zoom。行の高さ・バー・矢印・文字・ダイアログがそろって変わる)。"""
    return f"document.body.style.zoom = {round(percent / 100, 2)}"


ZOOM_DIRECTIONS = {"zoom_in": 1, "zoom_out": -1, "zoom_reset": 0}


class MainView:
    """メインパネル。現在のプロジェクトと画面部品を保持する。"""

    def __init__(
        self,
        base_dir: Path = BASE_DIR,
        transport: httpx.AsyncBaseTransport | None = None,
        exporter: ImageExporter | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self.base_dir = base_dir  # 設定(config.json)と祝日のキャッシュの置き場所。固定
        self.startup_notice: str | None = None
        if project_dir is None:
            project_dir, self.startup_notice = resolve_project_dir(base_dir)
        self.project_dir = project_dir  # プロジェクトファイルの格納先
        self.transport = transport
        self.exporter: ImageExporter = exporter or NativeImageExporter()
        self.preview: PreviewSettings | None = None
        self.preview_notice: str | None = None  # スケールを粗くして開いたときのお知らせ。設定を変えたら消す
        self.now: Callable[[], datetime] = datetime.now  # テストで差し替える
        self.dashboard_kind: PeriodKind | None = None  # 開いているときの期間。保存しない
        self.open_folder: Callable[[Path], object] = open_folder  # テストで差し替える(実際にはファイラを開かない)
        self.saving = False
        self.zoom = load_zoom(base_dir)  # 画面全体の倍率(%)。全プロジェクト共通
        self.task_layout = load_task_layout(base_dir)  # タスクのダイアログのレイアウト。全プロジェクト共通
        self.run_js: Callable[..., Any] = ui.run_javascript  # テストで差し替える
        self.project = Project(NEW_PROJECT_NAME)
        self.files: dict[str, Path] = {p.stem: p for p in list_project_files(self.project_dir)}
        self.path: Path | None = None
        self.digest: str | None = None  # 読み込み(保存)時のファイルの内容のハッシュ。外部変更の検知用
        self.read_git: Callable[[Path], GitState] = read_git_state  # テストで差し替える(本物の git を呼ばない)
        self.git_state: GitState = GitState(GitKind.NOT_REPO)  # 最後に読んだ結果。読むまでは出さない
        self.git_generation = 0  # 読み込みのたびに進める。古い結果を捨てる印
        self.read_changes: Callable[[Path], list[FileChange] | GitResult] = list_changes  # テストで差し替える
        self.commit_files: Callable[[Path, list[str], str], GitResult] = commit_files_in_git
        self.push_remote: Callable[[Path], GitResult] = push_to_remote
        self.git_busy = False  # コミット・プッシュの実行中。二重に始めない
        self.menu_entries: dict[str, ui.menu_item] = {}  # メニューの項目(マーカー → 項目)
        self.git_menu_tips: dict[str, ui.tooltip] = {}  # 押せない理由を出すツールチップ
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
                set_name_width=self.set_name_width,
                add_subsection=self.add_subsection,
            ),
            name_width=load_name_width(base_dir),
        )
        self.preview_bar = PreviewBar(self.on_preview_change, self.exit_preview, self.save_image)
        self.dashboard_view = DashboardView(self.close_dashboard, self.change_dashboard_period)

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.dark.value = None if theme == "auto" else theme == "dark"

    def set_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        self.gantt.refresh_scrollbars()  # 標準のスクロールバーは、切り替えだけでは配色が変わらない
        save_theme(theme, self.base_dir)
        self.theme_menu.refresh()

    def set_name_width(self, width: int) -> None:
        """名前の欄の幅を、アプリ全体の設定として保存する。プロジェクトのデータには入れない。
        保存できなくても、画面の幅はそのまま(通知だけ出す)。"""
        try:
            save_name_width(width, self.base_dir)
        except OSError:
            ui.notify("名前の欄の幅を保存できませんでした", type="warning")

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
        """保存に成功したときだけ、続きの処理を行う(外部変更の確認を挟んだときも、続きは引き継ぐ)。"""
        if self.path is None:
            open_name_dialog(
                lambda name: self.save_as_new(name, after),
                lambda name: validate_name(name, self.project_dir, new=True),
            )
        else:
            self.write(overwrite=True, after=after)

    def open_project(self, name: str) -> None:
        path = self.files[name]
        try:
            digest = file_digest(path)  # 読み込みの前に取る。間にファイルが変わっても、保存時に CHANGED になる側へ倒れる
            project = load_project(path)
        except (OSError, ValueError, KeyError) as exc:
            ui.notify(f"開けませんでした: {exc}", type="negative")
            self.file_select.set_value(self.current_name())
            return
        self.show_project(project, path, digest)
        self.request_git_refresh()

    def show_project(self, project: Project, path: Path | None, digest: str | None = None) -> None:
        """別のプロジェクトに切り替える(開いたとき・新規作成のとき)。保存済みの状態から始める。"""
        self.path, self.project, self.digest = path, project, digest
        self.mark_clean()
        self.file_select.set_value(path.stem if path else None)
        self.title.refresh()
        self.gantt.reset_collapsed()  # 折りたたみは保存しない。別のプロジェクトは全展開から始める
        self.gantt.set_project(self.project)
        self.gantt.reset_filter()
        self.gantt.reset_scroll()  # 別のプロジェクトは、先頭から見せる(編集後の再描画では動かさない)

    def open_project_folder(self) -> None:
        """プロジェクトの格納フォルダを、ファイラで開く。開けなければ通知する。"""
        try:
            self.open_folder(self.project_dir)
        except OSError as exc:
            ui.notify(f"フォルダを開けませんでした: {exc}", type="negative")

    def request_new(self) -> None:
        """新しいプロジェクトを作る。編集中なら、確認してから。"""
        if not self.is_dirty():
            self.new_project()
            return
        open_unsaved_dialog(
            on_save=lambda: self.save_then(self.new_project),
            on_discard=self.new_project,
            purpose="作成",
        )

    def request_change_project_dir(self) -> None:
        """格納先を変える(ネイティブのみ)。編集中は、確認してからフォルダを選ばせる。"""
        if not self.exporter.available:
            ui.notify(CHANGE_DIR_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not self.is_dirty():
            self.pick_project_dir()
            return
        open_unsaved_dialog(
            on_save=lambda: self.save_then(self.pick_project_dir),
            on_discard=self.pick_project_dir,
            purpose="変更",
        )

    def pick_project_dir(self) -> None:
        """フォルダ選択を始める。確認ダイアログは閉じると消えるので、タイマーは画面の直下に置く。"""
        with self.client:
            ui.timer(0, self.choose_project_dir, once=True)

    async def choose_project_dir(self) -> None:
        path = await self.exporter.ask_directory()
        if path is not None:
            self.change_project_dir(path)

    def change_project_dir(self, path: Path) -> None:
        """検査に通れば、格納先を保存して、ファイル一覧を読み直し、保存前の新規プロジェクトにする。"""
        if path.resolve() == self.project_dir.resolve():
            # 起動時に既定の場所へ戻っていた場合、保存してある(使えない)格納先を、今の場所で直す
            saved = load_project_dir(self.base_dir)
            if saved is not None and saved.resolve() != path.resolve():
                try:
                    save_project_dir(path, self.base_dir)
                except OSError as exc:
                    ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        if error := check_project_dir(path):
            ui.notify(f"このフォルダは使えません: {error}", type="negative")
            return
        try:
            save_project_dir(path, self.base_dir)
        except OSError as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        self.project_dir = path
        self.files = {p.stem: p for p in list_project_files(path)}
        self.file_select.set_options(sorted(self.files), value=None)
        self.new_project()
        self.request_git_refresh()

    def new_project(self) -> None:
        """起動時と同じ、保存前の新規プロジェクトにする(ファイルは、保存するまで作らない)。"""
        self.show_project(Project(NEW_PROJECT_NAME), None)

    def save_as(self) -> None:
        """名前をつけて保存する。成功したら、新しいファイルが現在のプロジェクトになる(元のファイルは残る)。"""
        self.save_as_then(None)

    def save_as_then(self, after: Callable[[], object] | None) -> None:
        open_name_dialog(
            lambda name: self.save_as_new(name, after),
            lambda name: validate_name(name, self.project_dir, new=True),
            title="名前をつけて保存",
            initial=self.project.name,
        )

    def show_file_list(self) -> None:
        """ファイルを走査し直して、一覧ダイアログを出す。"""
        self.files = {p.stem: p for p in list_project_files(self.project_dir)}
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
            templates=self.project.url_templates,
            template_usage=lambda name: count_usage(self.project, name),
            on_templates=self.apply_templates,
            categories=self.project.categories,
            category_usage=lambda category_id: count_category_usage(self.project, category_id),
            on_categories=self.apply_categories,
            used_ids=self.project.used_ids(),
        )

    def multi_interval_count(self) -> int:
        """2区間以上の実績を持つタスクの数。簡易へ戻せるかの判定に使う。"""
        return sum(1 for task in self.project.all_tasks() if len(task.actuals) > 1)

    def change_zoom(self, direction: int) -> None:
        """画面の倍率を 1 刻み変える(+1 拡大・-1 縮小・0 で 100%)。全体の設定として保存する。
        保存できなくても、画面には反映する(通知だけ出す)。画像の書き出し中は変えない。"""
        zoom = step_zoom(self.zoom, direction)
        if zoom == self.zoom or self.saving:
            return
        self.zoom = zoom
        self.run_js(zoom_js(zoom))
        try:
            save_zoom(zoom, self.base_dir)
        except OSError:
            ui.notify("倍率を保存できませんでした", type="warning")

    def set_task_layout(self, layout: str) -> None:
        """タスクのダイアログのレイアウトを覚える。保存できなくても、画面には反映する(通知だけ出す)。"""
        self.task_layout = layout
        try:
            save_task_layout(layout, self.base_dir)
        except OSError:
            ui.notify("レイアウトを保存できませんでした", type="warning")

    SHORTCUT_METHODS = {
        "save": "save_project_clicked",
        "save_as": "save_as",
        "open": "show_file_list",
        "new": "request_new",
        "settings": "open_settings",
        "members_parameters": "open_members_parameters",
        "handoff": "open_handoff",
        "preview": "enter_preview",
        "dashboard": "open_dashboard",
        "git_commit": "open_git_commit",
        "git_push": "start_git_push",
    }

    def on_plain_key(self, event: KeyEventArguments) -> None:
        if not (event.modifiers.ctrl or event.modifiers.meta):
            self.on_key(event)

    def on_modified_key(self, event: KeyEventArguments) -> None:
        if event.modifiers.ctrl or event.modifiers.meta:
            self.on_key(event)

    def screen(self) -> Screen:
        if self.preview is not None:
            return Screen.PREVIEW
        return Screen.DASHBOARD if self.dashboard_kind is not None else Screen.MAIN

    def dialog_open(self) -> bool:
        return any(isinstance(e, ui.dialog) and e.value for e in self.client.elements.values())

    def on_key(self, event: KeyEventArguments) -> None:
        """キー操作を、メニューと同じ操作へ振り分ける。ESC は、プレビューまたはダッシュボードから戻る
        (ダイアログの ESC は Quasar が閉じる。タスクの編集は、確認を挟む)。"""
        if not event.action.keydown:
            return
        action = resolve(
            event.key.name,
            ctrl=event.modifiers.ctrl or event.modifiers.meta,
            shift=event.modifiers.shift,
            modal=self.dialog_open(),
            screen=self.screen(),
        )
        if action == "escape":
            if self.preview is not None:
                self.exit_preview()
            elif self.dashboard_kind is not None:
                self.close_dashboard()
        elif action == "search":
            self.gantt.focus_search()
        elif action == "help":
            self.help_dialog.open()
        elif action in ZOOM_DIRECTIONS:
            self.change_zoom(ZOOM_DIRECTIONS[action])
        elif action is not None:
            getattr(self, self.SHORTCUT_METHODS[action])()

    def set_header_visible(self, visible: bool) -> None:
        """ヘッダーと、メイン側のタイトルを、一緒に出す・隠す(プレビューとダッシュボードの出入り)。"""
        self.header_box.set_visibility(visible)
        self.title_box.set_visibility(visible)

    def open_dashboard(self) -> None:
        """メイン画面を、ダッシュボードに切り替える(期間の初期値は今週)。プレビュー中は開かない。"""
        if self.preview is not None or self.dashboard_kind is not None:
            return
        self.dashboard_kind = PeriodKind.WEEK
        self.set_header_visible(False)
        self.gantt.set_visible(False)
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        if self.dashboard_kind is None:
            return
        now = self.now()
        period = period_for(self.dashboard_kind, now.date(), self.project, self.holidays)
        self.dashboard_view.show(summarize(self.project, period, now, self.holidays), self.dashboard_kind)

    def change_dashboard_period(self, kind: PeriodKind) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_kind = kind
        self.refresh_dashboard()

    def close_dashboard(self) -> None:
        """ダッシュボードから戻る。ガントチャートは作り直さない(絞り込み・スケール・位置はそのまま)。"""
        if self.dashboard_kind is None:
            return
        self.dashboard_kind = None
        self.dashboard_view.hide()
        self.set_header_visible(True)
        self.gantt.set_visible(True)

    def enter_preview(self) -> None:
        """メイン画面を、プレビューモードに切り替える。初期値は、今の表示範囲と、今のスケール。"""
        if self.preview is not None or self.dashboard_kind is not None:
            return
        start, end = visible_range(self.project, self.holidays)
        period = (start, max(end - timedelta(days=1), start))  # タスクがないと、範囲が空になる。基準日の 1 日にする
        scale = fit_scale(self.project, self.holidays, period, self.gantt.scale, self.gantt.name_width)
        self.preview_notice = coarser_notice(scale, self.gantt.scale) if scale is not self.gantt.scale else None
        self.preview = PreviewSettings(start, period[1], scale)
        self.set_header_visible(False)
        self.preview_bar.show(self.preview)
        self.apply_preview(self.preview)

    def exit_preview(self) -> None:
        """プレビューから戻る。通常のヘッダー・ツールバー・描画に戻す(絞り込みは変えない)。"""
        if self.preview is None or self.saving:
            return  # 保存中は、撮っている画面を変えない
        self.preview = None
        self.preview_notice = None
        self.preview_bar.hide()
        self.set_header_visible(True)
        self.gantt.set_options(ViewOptions())

    def on_preview_change(self) -> None:
        """バーの入力が変わったとき。期間が正しければ描き直し、誤りなら理由を出して保存を止める。"""
        if self.preview is None or self.saving:
            return  # 保存中は、撮っている画面を変えない
        self.preview_notice = None  # 利用者が設定を変えたので、お知らせは消す
        start_text, end_text, scale, chips, alerts = self.preview_bar.read()
        try:
            start, end = validate_period(start_text, end_text)
        except ValueError as exc:
            self.preview_bar.set_error(str(exc))
            self.preview_bar.set_warning(None)
            self.preview_bar.set_save_enabled(False)
            return
        too_long = check_column_count(scale, len(build_columns(self.project, scale, self.holidays, (start, end))))
        if too_long is not None:
            self.preview_bar.set_error(too_long)
            self.preview_bar.set_warning(None)
            self.preview_bar.set_save_enabled(False)
            return
        self.preview = PreviewSettings(start, end, scale, chips, alerts)
        self.apply_preview(self.preview)

    def apply_preview(self, settings: PreviewSettings) -> None:
        self.gantt.set_options(settings.to_options())
        self.preview_bar.set_error(None)
        available = self.exporter.available
        self.preview_bar.set_save_enabled(available and not self.saving)
        if not available:
            self.preview_bar.set_warning(NOT_NATIVE_MESSAGE)
        elif exceeds_canvas(self.gantt.content_width()):
            self.preview_bar.set_warning(LARGE_IMAGE_MESSAGE)
        else:
            self.preview_bar.set_warning(self.preview_notice)

    async def save_image(self) -> None:
        """プレビューを画像にして、選んだ場所へ保存する。失敗しても、プレビューに留まる。"""
        if self.preview is None or self.saving or not self.exporter.available:
            return
        self.saving = True
        self.preview_bar.set_save_enabled(False)
        if self.zoom != 100:
            self.run_js(zoom_js(100))  # 倍率をかけたままだと、画像の大きさがずれる
        try:
            ratio = export_pixel_ratio(self.gantt.content_width())
            try:
                data = await self.exporter.capture(ratio)
            except ExportError as exc:
                ui.notify(f"画像を作れませんでした: {exc}", type="negative")
                return
            path = await self.exporter.ask_path(default_filename(self.project.name, date.today()), PNG_FILE_TYPES)
            if path is None:
                return
            try:
                write_png(path, data)
            except OSError as exc:
                ui.notify(f"保存できませんでした: {exc}", type="negative")
                return
            ui.notify("保存しました")
        finally:
            self.saving = False
            if self.zoom != 100:
                self.run_js(zoom_js(self.zoom))
            if self.preview is not None:
                self.preview_bar.set_save_enabled(self.exporter.available)

    def open_handoff(self) -> None:
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not self.project.members:
            ui.notify("メンバーが登録されていません", type="warning")
            return
        open_handoff_dialog(
            [m.name for m in self.project.members],
            lambda name: len(tasks_for(self.project, name)),
            self.export_handoff,
        )

    async def export_handoff(self, member_name: str) -> bool:
        """選んだ担当の未終了タスクを、todoapp 形式で書き出す。閉じてよいとき(書き出せたとき)だけ True。プロジェクトは変えない。"""
        result = build_todos(self.project, member_name, self.holidays)
        if result.task_count == 0:
            return False
        path = await self.exporter.ask_path(handoff_filename(member_name), JSON_FILE_TYPES)
        if path is None:
            return False
        try:
            write_json(path, result.data)
        except OSError as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return False
        ui.notify(summary(result))
        return True

    def open_members_parameters(self) -> None:
        open_members_parameters_dialog(
            get_members=lambda: self.project.members,
            assigned=self.assigned_count,
            on_apply_members=self.apply_members,
            get_parameters=lambda: self.project.parameters,
            impacts=lambda edit: deletion_impacts(self.project, edit),
            on_apply_parameters=self.apply_parameters,
            get_taken=self.project.used_ids,
        )

    def assigned_count(self, name: str) -> int:
        return sum(1 for task in self.project.all_tasks() if name in task.assignee_names)

    def apply_members(self, members: list[Member], renames: dict[str, str]) -> None:
        """メンバーを更新し、改名をタスクの担当者に伝える。保存はしない(編集中の判定に入る)。"""
        if members == self.project.members and not renames:
            return
        self.project.members = members
        if renames:
            for task in self.project.all_tasks():
                for assignee in task.assignees:
                    if assignee.name in renames:
                        assignee.name = renames[assignee.name]
        self.gantt.set_project(self.project)

    def apply_parameters(self, edit: ParameterEdit) -> None:
        """パラメータの定義を更新し、メンバーの選択に改名・削除を伝える。保存はしない(編集中の判定に入る)。"""
        if not edit.changes(self.project.parameters):
            return
        apply_parameter_edit(self.project, edit)
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

    def apply_templates(self, edit: TemplateEdit) -> None:
        """URL テンプレートの編集を反映する(削除分のリンクは URL に展開される)。保存はしない。"""
        apply_template_edit(self.project, edit)
        self.gantt.set_project(self.project)

    def apply_categories(self, edit: CategoryEdit) -> None:
        """カテゴリの編集を反映する(削除したカテゴリのタスクは未定に戻る)。保存はしない。"""
        apply_category_edit(self.project, edit)
        self.gantt.set_project(self.project)

    def save_project_clicked(self) -> None:
        if self.path is None:
            open_name_dialog(
                self.save_as_new,
                lambda name: validate_name(name, self.project_dir, new=True),
            )
            return
        self.write(overwrite=True)

    def save_as_new(self, name: str, after: Callable[[], object] | None = None) -> bool:
        previous = self.project.name
        self.project.name = name
        if self.write(overwrite=False, after=after):
            return True
        self.project.name = previous
        return False

    def write(self, *, overwrite: bool, after: Callable[[], object] | None = None) -> bool:
        """保存して画面を更新する。成功したら `after` を呼ぶ。失敗したら通知だけ出し、状態は変えない。

        上書き保存の直前に、読み込んだあとの外部変更を調べる。変更があれば確認を出して False を返し、
        続きの `after` は、確認の結果の保存に引き継ぐ。
        """
        if overwrite and self.path is not None:
            try:
                change = check_external_change(self.path, self.digest)
            except OSError as exc:
                ui.notify(f"保存できませんでした: {exc}", type="negative")
                return False
            if change is ExternalChange.CHANGED:
                open_conflict_dialog(
                    on_overwrite=lambda: self.overwrite_external(after),
                    on_save_as=lambda: self.save_as_then(after),
                )
                return False
            if change is ExternalChange.MISSING:
                ui.notify("ファイルが見つかりませんでした。新しく作成します", type="warning")
        return self.commit(overwrite=overwrite, after=after)

    def overwrite_external(self, after: Callable[[], object] | None) -> None:
        """外部変更を承知で上書きする。相手の版は `.bak` に退避し、退避できなければ保存しない。"""
        if self.path is not None:
            try:
                backup_file(self.path)
            except FileNotFoundError:
                pass  # 確認の間に消えた。退避するものがない
            except OSError:
                ui.notify("バックアップを作れなかったため、保存しませんでした", type="negative")
                return
        self.commit(overwrite=True, after=after)

    def commit(self, *, overwrite: bool, after: Callable[[], object] | None) -> bool:
        """検査なしで保存する(`write` の本体)。"""
        try:
            path = save_project(self.project, self.project_dir, overwrite=overwrite)
        except FileExistsError:
            ui.notify("同じ名前のファイルがすでにあります", type="negative")
            return False
        except (ValueError, OSError) as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return False
        self.path = path
        try:
            self.digest = file_digest(path)  # 書いたファイルを読み直して覚える
        except OSError:
            self.digest = None  # 読めなくても保存は成功している。次の保存では判定しない
        self.mark_clean()
        self.files[path.stem] = path
        self.file_select.set_options(sorted(self.files), value=path.stem)
        self.title.refresh()
        ui.notify("保存しました")
        self.request_git_refresh()
        if after is not None:
            after()
        return True

    def add_section(self) -> None:
        open_section_dialog(self.save_section)

    def save_section(self, name: str) -> None:
        self.project.sections.append(Section(name, id=new_id(self.project.used_ids())))
        self.gantt.set_project(self.project)

    def add_subsection(self, path: SectionPath) -> None:
        open_section_dialog(lambda name: self.save_subsection(path, name), title="サブセクションの追加")

    def save_subsection(self, path: SectionPath, name: str) -> None:
        """セクションの末尾にサブセクションを足す。親がない・root・3 階層目の親は何もしない。"""
        parent = arrange.section_at(self.project, path)
        if parent is None or len(path) >= MAX_SECTION_DEPTH:
            return
        parent.sections.append(Section(name, id=new_id(self.project.used_ids())))
        self.gantt.expand_section(path)
        self.gantt.set_project(self.project)

    def link_args(self, task: Task | None) -> dict[str, Any]:
        """編集ダイアログに渡す、先行タスクとリンクの引数。"""
        schedule = Schedule(self.project, self.holidays)
        by_id = {t.id: t for t in self.project.all_tasks()}

        def finish_of(task_id: str) -> datetime | None:
            pred = by_id.get(task_id)
            return None if pred is None else schedule.finish(pred)

        return {
            "link_options": link_options(self.project, task),
            "finish_of": finish_of,
            "url_templates": self.project.url_templates,
            "parameters": self.project.parameters,
            "categories": self.project.categories,
            "layout": self.task_layout,
            "on_layout_change": self.set_task_layout,
        }

    def add_task(self, path: SectionPath) -> None:
        open_task_dialog(
            None,
            lambda task: self.save_task(path, None, task),
            work_start=self.project.work_start,
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
            members=self.project.members,
            actual_mode=self.project.actual_mode,
            **self.link_args(None),
        )

    def add_top_task(self) -> None:
        open_task_dialog(
            None,
            lambda task: self.save_task((), None, task),
            work_start=self.project.work_start,
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
            members=self.project.members,
            actual_mode=self.project.actual_mode,
            **self.link_args(None),
        )

    def edit_task(self, path: SectionPath, task_index: int) -> None:
        task = self.tasks_in(path)[task_index]
        open_task_dialog(
            task,
            lambda t: self.save_task(path, task_index, t),
            work_start=self.project.work_start,
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
            members=self.project.members,
            actual_mode=self.project.actual_mode,
            on_delete=lambda: self.delete_task(path, task_index),
            **self.link_args(task),
        )

    def delete_task(self, path: SectionPath, task_index: int) -> None:
        """タスクを取り除いて再描画する。保存は自動では行わない(編集中の判定に入る)。"""
        removed = self.tasks_in(path).pop(task_index)
        drop_task_links(self.project, removed.id)
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

    def shift_task(self, path: SectionPath, task_index: int, days: int) -> None:
        """開始予定(と入っていれば完了予定)を days 日ずらす。締切は動かさず、基準日より前へは動かさない。"""
        if days == 0 or not arrange.has_task(self.project, (path, task_index)):
            return
        task = self.tasks_in(path)[task_index]
        schedule = Schedule(self.project, self.holidays)
        shown = schedule.start(task)
        floor = schedule.latest_finish(task)
        days = max(days, arrange.min_shift_days(task, self.project.base_date, shown, floor))
        if days == 0:
            return
        if not arrange.shift_task(task, days, shown):
            if task.planned_start is not None:
                ui.notify("日付の範囲を超えるため動かせません", type="warning")
            return
        self.gantt.set_project(self.project)
        self.warn_overallocation(task)

    def tasks_in(self, path: SectionPath) -> list[Task]:
        """セクション(パス)のタスク一覧。root は (): セクションに属さないタスク。"""
        return arrange.tasks_at(self.project, path)

    def save_task(
        self, path: SectionPath, task_index: int | None, task: Task
    ) -> None:
        tasks = self.tasks_in(path)
        if task_index is None:
            if task.id in self.project.used_ids():
                task.id = new_id(self.project.used_ids())  # 他のタスク・メンバー・セクションと同じ id にならないように
            tasks.append(task)
        else:
            tasks[task_index] = task
        if task_index is None and path:
            self.gantt.expand_section(path)  # 追加したタスクが、親も含めて見えるように
        self.gantt.set_project(self.project)
        self.warn_overallocation(task)

    def warn_overallocation(self, task: Task) -> None:
        """保存したタスクが担当者の割り当て合計の超過に関わるなら、担当者ごとに通知する(保存は妨げない)。"""
        if not task.assignees:
            return
        overloads = overallocations(self.project, self.holidays)
        mine = clip_overloads(task, self.project, self.holidays, overloads)
        for name in task.assignee_names:
            peaks = [o.total for o in mine if o.member == name]
            if peaks:
                ui.notify(
                    f"{name} の割り当てが最大{round(max(peaks) * 100)}%になる期間があります",
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
        ui.add_head_html(f'<script src="{HTML_TO_IMAGE_URL}"></script>')
        ui.add_css(HEADER_CSS)
        ui.add_css(MEMBER_TABLE_CSS)
        self.help_dialog = self.build_help_dialog()
        self.header()
        with ui.row().classes("w-full items-center") as title_box:
            self.title_box = title_box
            title_box.mark("title-box")
            self.title()
        self.preview_bar.build()
        self.dashboard_view.build()
        self.gantt.build()
        self.client = ui.context.client
        self.request_git_refresh()
        self.run_js(KEY_GUARD_JS)
        self.run_js(zoom_js(self.zoom))
        ui.keyboard(on_key=self.on_plain_key)  # 入力欄・ボタンにフォーカスがあるときは、受けない
        ui.keyboard(on_key=self.on_modified_key, ignore=[])  # Ctrl/Cmd 付きだけは、入力欄でも受ける
        if self.startup_notice:
            ui.notify(self.startup_notice, type="warning")
        if self.needs_first_fetch:
            ui.timer(0.1, self.first_fetch, once=True)

    def header(self) -> None:
        """ヘッダー(画面の上端に固定する 1 行。左からメニュー 4 つ、右側にコンボ・ダッシュボード・テーマ。プロジェクト名は、ヘッダーの外): タイトル・メニュー 4 つ・(右側)プロジェクトの切り替え・ダッシュボード・テーマ。"""
        with ui.header(elevated=False, wrap=False).classes("row items-center no-wrap gap-1 app-header") as box:
            self.header_box = box
            box.mark("header-box")
            self.header_menu(
                "ファイル",
                "menu-file",
                [
                    MenuItem("開く", "folder_open", self.show_file_list, "file-open"),
                    MenuItem("新規プロジェクト作成", "note_add", self.request_new, "file-new"),
                    None,  # 水平線(開く・作る / 保存 / データの更新)
                    MenuItem("上書き保存", "save", self.save_project_clicked, "save-project"),
                    MenuItem("名前をつけて保存", "save_as", self.save_as, "file-save-as"),
                    None,
                    MenuItem("格納先を変更", "drive_file_move", self.request_change_project_dir, "file-change-dir"),
                    MenuItem("祝日を更新", "event_repeat", self.refresh_holidays, "refresh-holidays"),
                ],
            )
            self.header_menu(
                "プロジェクト",
                "menu-project",
                [
                    MenuItem("設定", "settings", self.open_settings, "open-settings"),
                    MenuItem("メンバーとパラメータ", "groups", self.open_members_parameters, "open-members-parameters"),
                    MenuItem("ダッシュボード", "dashboard", self.open_dashboard, "menu-open-dashboard", "D"),
                ],
            )
            self.header_menu(
                "エクスポート",
                "menu-export",
                [
                    MenuItem("チャートプレビュー", "visibility", self.enter_preview, "export-preview"),
                    MenuItem("担当者へ書き出し", "ios_share", self.open_handoff, "export-handoff"),
                ],
            )
            self.header_menu(
                "Git",
                "menu-git",
                [
                    MenuItem("コミット…", "commit", self.open_git_commit, "git-commit", label_for("git_commit")),
                    MenuItem("プッシュ", "cloud_upload", self.start_git_push, "git-push", label_for("git_push")),
                    MenuItem("状態を読み直す", "refresh", self.request_git_refresh, "git-refresh"),
                ],
            )
            self.header_menu(
                "ヘルプ", "menu-help", [MenuItem("ショートカットヘルプ", "keyboard", self.help_dialog.open, "help-shortcuts")]
            )
            ui.space()
            self.git_chip()
            self.file_select = ui.select(
                list(self.files),
                label="プロジェクトファイル",
                on_change=lambda e: self.request_open(e.value),
            ).props("dense outlined dark popup-content-class=app-select-popup").classes("app-project-select").mark("project-select")
            ui.button(icon="dashboard", color=None, on_click=self.open_dashboard).props("flat round dense").tooltip(
                "ダッシュボード"
            ).mark("open-dashboard")
            ui.button(icon="folder_special", color=None, on_click=self.open_project_folder).props(
                "flat round dense"
            ).tooltip("プロジェクトの格納フォルダを開く").mark("open-folder")
            self.theme_menu()
            self.update_git_menu()

    def header_menu(self, label: str, marker: str, items: list[MenuItem | None]) -> None:
        """ヘッダーのメニュー。項目のマーカーは、押す操作を指す(None は水平線)。"""
        with ui.button(label, color=None).props("unelevated rounded no-caps").classes("app-menu-btn").mark(marker):
            with ui.menu().props("content-class=app-menu").mark(f"{marker}-items"):
                for item in items:
                    if item is None:
                        ui.separator().mark(f"{marker}-separator")
                        continue
                    self.menu_entries[item.marker] = self.menu_entry(item.text, item.icon, item.handler, item.marker, item.key)

    @staticmethod
    def menu_entry(text: str, icon: str, handler: Callable[[], object], marker: str, key: str = "") -> ui.menu_item:
        """メニューの 1 項目(左にアイコン、右端にキー)。文言の ItemSection は、menu_item が作る。"""
        with ui.menu_item(text, on_click=handler).mark(marker) as entry:
            with ui.item_section().props("avatar") as avatar:
                ui.icon(icon)
            avatar.move(entry, target_index=0)
            if key:
                ui.item_section(key).props("side").classes("text-caption text-grey")
        return entry

    NOT_WORK_TREE = "git の作業ツリーではありません"
    GIT_MENU = (("commit", "git-commit"), ("push", "git-push"), ("refresh", "git-refresh"))

    def git_reason(self, action: str) -> str | None:
        """Git メニューの操作が、今できない理由(できるときは None)。`action`は commit・push・push_after_commit・refresh。
        `push_after_commit`は、コミットのあとにプッシュするとき(今は未プッシュが 0 でもよい)。"""
        state = self.git_state
        if state.kind is not GitKind.OK:
            return self.NOT_WORK_TREE
        if action == "refresh":
            return None
        if self.git_busy:
            return "実行中です"
        if action in ("push", "push_after_commit"):
            if state.error is not None:
                return "git の状態を読めていません"
            if state.upstream is None:
                return "上流がありません"
            if state.ahead is None:
                return "上流が見つかりません"
            if action == "push" and state.ahead == 0:
                return "未プッシュのコミットがありません"
        return None

    def update_git_menu(self) -> None:
        """Git メニューの項目を、押せるかどうかと、押せない理由のツールチップに合わせる。"""
        for action, marker in self.GIT_MENU:
            entry = self.menu_entries[marker]
            reason = self.git_reason(action)
            entry.set_enabled(reason is None)
            tip = self.git_menu_tips.get(marker)
            if tip is None:
                with entry:
                    tip = ui.tooltip("")
                self.git_menu_tips[marker] = tip
            tip.set_text(reason or "")
            tip.set_visibility(reason is not None)

    def set_git_busy(self, busy: bool) -> None:
        self.git_busy = busy
        self.update_git_menu()

    def later(self, handler: Callable[[], object]) -> None:
        """処理を画面の直下のタイマーで始める(ダイアログが閉じても残る。同期の入口から、非同期の処理を始める)。"""
        with self.client:
            ui.timer(0, handler, once=True)

    def open_git_commit(self) -> None:
        """コミットのダイアログを開く(メニューとショートカットの入口)。できないときは、理由を通知する。"""
        reason = self.git_reason("commit")
        if reason is not None:
            ui.notify(reason, type="warning")
            return
        self.later(self.show_commit_dialog)

    async def show_commit_dialog(self) -> None:
        changes = await run.io_bound(self.read_changes, self.project_dir)
        if changes is None:  # アプリの終了中
            return
        if isinstance(changes, GitResult):
            ui.notify(changes.message, type="negative")
            return
        if not changes:
            ui.notify("コミットする変更がありません")
            return
        open_commit_dialog(
            changes,
            default_message,
            self.git_reason("push_after_commit"),
            self.is_dirty(),
            lambda names, message, push: self.later(lambda: self.run_commit(names, message, push)),
        )

    async def run_commit(self, names: list[str], message: str, push: bool) -> None:
        """選んだファイルをコミットし、`push`ならプッシュする。終わったらチップを読み直す。"""
        if self.git_busy:
            return
        self.set_git_busy(True)
        try:
            result = await run.io_bound(self.commit_files, self.project_dir, names, message)
            if result is None:  # アプリの終了中
                return
            if not result.ok:
                ui.notify(result.message, type="negative")
                return
            ui.notify(f"コミットしました({result.detail})")
            if push:
                pushed = await run.io_bound(self.push_remote, self.project_dir)
                if pushed is None:
                    return
                if pushed.ok:
                    ui.notify(pushed.message)
                else:
                    ui.notify(f"コミットしました。プッシュに失敗しました: {pushed.message}", type="warning")
        finally:
            self.set_git_busy(False)
            self.request_git_refresh()

    def start_git_push(self) -> None:
        """プッシュを始める(メニューとショートカットの入口)。できないときは、理由を通知する。"""
        reason = self.git_reason("push")
        if reason is not None:
            ui.notify(reason, type="warning")
            return
        self.later(self.run_push)

    async def run_push(self) -> None:
        if self.git_busy:
            return
        self.set_git_busy(True)
        try:
            result = await run.io_bound(self.push_remote, self.project_dir)
            if result is None:
                return
            ui.notify(result.message, type="positive" if result.ok else "negative")
        finally:
            self.set_git_busy(False)
            self.request_git_refresh()

    def request_git_refresh(self) -> None:
        """git の状態の読み直しを予約する(ダイアログが閉じても残るよう、タイマーは画面の直下に置く)。"""
        with self.client:
            ui.timer(0, self.refresh_git, once=True)

    async def refresh_git(self) -> None:
        """git の状態を読んでチップを更新する。画面は止めない。あとから始めた読み込みがあれば、この結果は捨てる。"""
        self.git_generation += 1
        generation = self.git_generation
        state = await run.io_bound(self.read_git, self.project_dir)
        if state is None or generation != self.git_generation:  # None はアプリの終了中
            return
        self.git_state = state
        self.git_chip.refresh()
        self.update_git_menu()

    @ui.refreshable_method
    def git_chip(self) -> None:
        """ヘッダーの git の状態のチップ(読み取り専用。押すと読み直す)。作業ツリーでなければ出さない。"""
        text = describe(self.git_state)
        if not text:
            return
        chip = ui.label(text).classes("app-git-chip").tooltip(tooltip(self.git_state)).mark("git-state")
        chip.on("click", self.request_git_refresh)
        if self.git_state.error is not None:
            chip.classes("app-git-error")
        elif self.git_state.behind:
            chip.classes("app-git-behind")
        elif self.git_state.dirty:
            chip.classes("app-git-dirty")

    @ui.refreshable_method
    def title(self) -> None:
        ui.label(self.project.name).classes("app-title")

    @ui.refreshable_method
    def theme_menu(self) -> None:
        """ヘッダー右端のテーマのメニュー。ボタンの絵が今のテーマで、開いたメニューの選択中の項目が強調される。"""
        with ui.button(icon=THEME_ICONS[self.theme], color=None).props("flat round dense").tooltip("テーマ").mark(
            "menu-theme"
        ):
            with ui.menu().props("content-class=app-menu").mark("menu-theme-items"):
                for theme in THEMES:
                    item = self.menu_entry(
                        THEME_LABELS[theme], THEME_ICONS[theme], lambda t=theme: self.set_theme(t), f"theme-{theme}"
                    )
                    if theme == self.theme:
                        item.props("active")

    def build_help_dialog(self) -> ui.dialog:
        """ショートカットヘルプのダイアログ(ヘルプメニューから開く)。"""
        with ui.dialog() as dialog, ui.card():
            ui.label("キー操作").classes("text-h6")
            for key, desc in help_entries():
                ui.label(f"{key}: {desc}")
            ui.button("閉じる", on_click=dialog.close)
        return dialog
