"""メイン画面。"""

import asyncio
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any
from pathlib import Path

import httpx
from nicegui import run, ui
from nicegui.events import KeyEventArguments

from projectapp.calendar import load_cache
from projectapp.events import EffectiveHolidays, effective_holidays
from projectapp.extract import check as check_extraction, extract, name_error as extract_name_error, selection_error
from projectapp.categories import CategoryEdit
from projectapp.icons import ICON_FILE_TYPES, IconError, load_icon
from projectapp.categories import apply_edit as apply_category_edit
from projectapp.categories import count_usage as count_category_usage
from projectapp.linkgraph import drop_task_links, link_options
from projectapp.calendar import refresh_holidays as download_holidays
from projectapp.config import (
    DEFAULT_ZOOM_PERCENT,
    THEMES,
    check_project_dir,
    load_custom_theme,
    load_today_color,
    load_dashboard_view_last,
    load_dashboard_views,
    load_project_dir,
    load_name_width,
    load_task_sections,
    load_theme,
    load_zoom,
    resolve_project_dir,
    save_custom_theme,
    save_today_color,
    save_dashboard_view_last,
    save_dashboard_views,
    save_name_width,
    save_project_dir,
    save_task_sections,
    save_theme,
    save_zoom,
    step_zoom,
)
from projectapp.bulk_dialog import open_bulk_dialog
from projectapp.bulk_edit import BulkChanges, BulkResult, delete_summary, delete_tasks, store
from projectapp.bulk_edit import apply_bulk as apply_bulk_changes  # MainView.apply_bulk と紛れないように
from projectapp.forms import (
    MEMBER_TABLE_CSS,
    open_commit_dialog,
    open_conflict_dialog,
    open_merge_conflict_dialog,
    open_file_dialog,
    open_handoff_dialog,
    open_members_parameters_dialog,
    open_confirm_dialog,
    open_name_dialog,
    section_name_error,
    task_name_error,
    open_section_dialog,
    open_settings_dialog,
    open_stale_reference_dialog,
    open_stale_snapshot_dialog,
    open_unsaved_dialog,
)
from projectapp import arrange
from projectapp.reference import (
    ReferenceResolver,
    build_references,
    compute_reference,
    load_children,
    missing_references,
    take_snapshot,
)
from projectapp.shortcuts import Screen, defers_to_inputs, help_entries, key_guard_js, label_for, resolve
from projectapp.dashboard import MAX_CUSTOM_DAYS, CrossSummary, Period, PeriodKind, custom_period_error, period_for, summarize, summarize_cross_loads
from projectapp.dashboard_view import DashboardView, ViewActions
from projectapp.dashboard_views import (
    DEFAULT_ORDER,
    MAX_VIEWS,
    STANDARD_NAME,
    CardId,
    ViewSpec,
    ViewState,
    hidden_cards,
    hide_card,
    move_card,
    resolve_member,
    resolve_team,
    show_card,
    standard_view,
)
from projectapp.dashboard_views import validate_name as validate_view_name
from projectapp.portfolio import load_others
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
from projectapp.plantuml import PLANTUML_FILE_TYPES, build_plantuml, day_overload_notice, weekly_crew_notice, write_text
from projectapp.plantuml import default_filename as plantuml_filename
from projectapp.csv_export import DEFAULT_FILENAME as TSV_DEFAULT_FILENAME
from projectapp.csv_export import TSV_FILE_TYPES, build_tsv, write_tsv
from projectapp.csv_import import CSV_OPEN_FILE_TYPES, CsvImportError, parse_csv, read_table
from projectapp.csv_import import summary as csv_import_summary
from projectapp.settings_io import DEFAULT_FILENAME as SETTINGS_DEFAULT_FILENAME
from projectapp.settings_dialog import open_import_dialog
from projectapp.settings_io import SETTINGS_FILE_TYPES, ImportFile, ImportResult, apply_import, build_settings
from projectapp.settings_io import copy_into, parse_settings, plan_import, write_settings
from projectapp.settings_io import summary as settings_import_summary
from projectapp.puml_import import (
    PLANTUML_OPEN_FILE_TYPES,
    PlantUmlImportError,
    parse_plantuml,
    read_plantuml,
)
from projectapp.puml_import import summary as import_summary
from projectapp.filemanager import open_folder
from projectapp.gitops import FileChange, GitResult, PullKind, PullOps, default_message, list_changes
from projectapp.gitops import commit as commit_files_in_git
from projectapp.gitops import push as push_to_remote
from projectapp.gitstate import GitKind, GitState, describe, read_git_state, tooltip
from projectapp.decompose import ParamMode, Part, can_make_section, decompose, settle
from projectapp.decompose_dialog import open_decompose_dialog
from projectapp.history import History
from projectapp.merge import merge_files
from projectapp.gantt import GanttActions, GanttChart, ViewOptions, short_date
from projectapp.models import MAX_SECTION_DEPTH, MAX_WEEKS, ActualMode, Assignee, Event, Member, Project, RatioLimits, ReferenceMode, ReferenceValue, Section, SectionPath, Task, TaskKind, Team, WorkDay, new_id, union_assignees
from projectapp.workdays import work_day_map
from projectapp.selection import set_checked
from projectapp.preview import (
    LARGE_IMAGE_MESSAGE,
    NOT_NATIVE_MESSAGE,
    PreviewBar,
    PreviewSettings,
    check_column_count,
    coarser_notice,
    fit_scale,
    format_period,
    split_period,
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
from projectapp.summary import parent_map
from projectapp.task_dialog import open_task_dialog, open_week_crew_dialog
from projectapp.teams import removal_impacts, replace_teams, team_scope, teams_with_members
from projectapp.theme import BODY_CSS, CustomTheme, theme_js, today_color_js
from projectapp.theme_dialog import open_theme_dialog as show_theme_dialog
from projectapp.theme_dialog import open_today_color_dialog as show_today_color_dialog
from projectapp.urls import TemplateEdit, apply_template_edit, count_usage
from projectapp.ratios import ParameterEdit, apply_parameter_edit, impact_lines
from projectapp.reassign import limit_reviews
from projectapp.timeline import (
    Schedule,
    build_columns,
    clip_overloads,
    effective_end,
    effective_start,
    overallocations,
    visible_range,
    week_count,
)

THEME_LABELS = {"auto": "自動", "light": "ライト", "dark": "ダーク", "custom": "カスタム"}
CUSTOM_COLORS_LABEL = "カスタムの色…"
TODAY_COLOR_LABEL = "今日の線の色…"
THEME_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode", "custom": "palette"}


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
.app-header { background: var(--app-header, var(--q-primary)); color: var(--app-header-fg, #fff); font-size: 12px; padding: 4px 12px; flex-wrap: nowrap !important; overflow: hidden; }
body.body--dark .app-header { background: var(--app-header, color-mix(in srgb, var(--q-primary) 55%, #000)); }
.app-header .q-btn, .app-header .q-field { font-size: 12px; }
.app-header .q-btn { white-space: nowrap; flex: none; }
.app-header .q-btn__content { white-space: nowrap; flex-wrap: nowrap; }
.app-header .app-project-select { flex: 0 1 16rem; min-width: 8rem; color: var(--app-header-fg, #fff); }
.app-header .app-project-select .q-field__native, .app-header .app-project-select .q-field__input { font-size: 10px; color: var(--app-header-fg, #fff); }
.app-header .app-project-select.q-field--outlined .q-field__control:before { border-color: var(--app-header-border, hsla(0, 0%, 100%, 0.24)); }
.app-header .app-project-select .q-field__label, .app-header .app-project-select .q-field__append { color: var(--app-header-label, rgba(255, 255, 255, 0.7)); }
.app-select-popup .q-item { font-size: 10px; min-height: 28px; }
.app-title { font-size: 12px; font-weight: 700; white-space: nowrap; }
.app-header .app-menu-btn { background: var(--app-header-chip, rgba(255, 255, 255, 0.18)); padding: 0 14px; }
.app-header .app-menu-btn:hover { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }
.app-menu .q-item { font-size: 12px; min-height: 32px; }
.app-git-chip { flex: none; font-size: 10px; line-height: 1; padding: 4px 8px; border-radius: 9999px; background: var(--app-header-chip, rgba(255, 255, 255, 0.18)); white-space: nowrap; cursor: pointer; }
.app-git-chip:hover { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }
.app-git-chip.app-git-dirty { background: #ffd54f; color: #3e2723; }
.app-git-chip.app-git-behind { background: #ffb74d; color: #3e2723; }
.app-git-chip.app-git-error { background: #ef9a9a; color: #3e2723; }
.q-tooltip { white-space: pre-line; }
"""
HANDOFF_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、書き出せます"
CHANGE_DIR_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、格納先を変更できます"
IMPORT_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、取り込めます"
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
        self.dashboard_custom: Period | None = None  # `指定` の期間。保存しない
        self.dashboard_custom_error = ""  # `指定` の欄の入力が不正なときの、エラー文
        self.dashboard_member: str | None = None  # ダッシュボードで絞り込み中のメンバー。保存しない
        self.dashboard_team: str | None = None  # 絞り込み中のチーム名。メンバーとは同時に使わない。保存しない
        self.dashboard_cross = False  # 全プロジェクトを重ねるか。保存しない
        self.dashboard_excluded: set[str] = set()  # 重ねるのから外したプロジェクトの名前。保存しない
        self.dashboard_views = load_dashboard_views(base_dir)  # 保存したビュー(`標準` を含まない)。全プロジェクト共通
        self.dashboard_view_name = load_dashboard_view_last(base_dir) or STANDARD_NAME  # 最後に使ったビュー
        self.dashboard_cards: tuple[CardId, ...] = DEFAULT_ORDER  # 表示するカードの並び。保存するのはビューにしたときだけ
        self.dashboard_names: list[str] = []  # 今の名簿(refresh のたびに更新)。保存したメンバーが残っているかの判定に使う
        self.open_folder: Callable[[Path], object] = open_folder  # テストで差し替える(実際にはファイラを開かない)
        self.saving = False
        self.zoom = load_zoom(base_dir)  # 画面全体の倍率(%)。全プロジェクト共通
        self.task_sections = load_task_sections(base_dir)  # タスクのダイアログで開いている節。全プロジェクト共通
        self.run_js: Callable[..., Any] = ui.run_javascript  # テストで差し替える
        self.project = Project(NEW_PROJECT_NAME)
        self.files: dict[str, Path] = {p.stem: p for p in list_project_files(self.project_dir)}
        self.origin: str | None = None  # 参照行のクリックで開いたときの、元のプロジェクト名(戻るリンク用。保存しない)
        self.pending_origin: tuple[str, str] | None = None  # (元, 開く先)。開くのが確認で取りやめになったら、次の切り替えでは使わない
        self.path: Path | None = None
        self.digest: str | None = None  # 読み込み(保存)時のファイルの内容のハッシュ。外部変更の検知用
        self.read_git: Callable[[Path], GitState] = read_git_state  # テストで差し替える(本物の git を呼ばない)
        self.git_state: GitState = GitState(GitKind.NOT_REPO)  # 最後に読んだ結果。読むまでは出さない
        self.git_generation = 0  # 読み込みのたびに進める。古い結果を捨てる印
        self.read_changes: Callable[[Path], list[FileChange] | GitResult] = list_changes  # テストで差し替える
        self.commit_files: Callable[[Path, list[str], str], GitResult] = commit_files_in_git
        self.push_remote: Callable[[Path], GitResult] = push_to_remote
        self.git_busy = False  # コミット・プッシュの実行中。二重に始めない
        self.pull_ops = PullOps()  # プルの各段階。テストで差し替える
        self.menu_entries: dict[str, ui.menu_item] = {}  # メニューの項目(マーカー → 項目)
        self.git_menu_tips: dict[str, ui.tooltip] = {}  # 押せない理由を出すツールチップ
        self.mark_clean()
        self.history = History()  # 元に戻す・やり直しの履歴。保存しても残し、別のプロジェクトに切り替えると捨てる
        self.committed = deepcopy(self.project)  # 最後に確定した状態。これと違えば、編集があったとみなして履歴に積む
        self.theme = load_theme(base_dir)
        self.custom_theme = load_custom_theme(base_dir)  # 保存済みのカスタムの色
        self.today_color = load_today_color(base_dir)  # 今日の線の色。None は既定(テーマに従う)
        self.dark = ui.dark_mode()
        self.dark.value = self.dark_value(self.theme, self.custom_theme)
        cached = load_cache(base_dir)
        self.base_holidays: dict[date, str] = cached or {}  # 祝日だけ。計算には、休みのイベントを足した holidays を使う
        self._effective_holidays = EffectiveHolidays()
        self.needs_first_fetch = cached is None
        self.reference_resolver = ReferenceResolver(lambda: self.project_dir, lambda: self.base_holidays)
        self.gantt = GanttChart(
            self.project,
            self.base_holidays,
            GanttActions(
                add_section=self.add_section,
                add_task=self.add_task,
                add_top_task=self.add_top_task,
                edit_task=self.edit_task,
                move_task=self.move_task,
                shift_task=self.shift_task,
                set_name_width=self.set_name_width,
                add_subsection=self.add_subsection,
                decompose_task=self.decompose_task,
                bulk_edit=self.bulk_edit,
                bulk_delete=self.confirm_bulk_delete,
                extract_tasks=self.extract_tasks,
                copy_task=self.copy_task_below,
                rename_task=self.rename_task,
                delete_task=self.confirm_delete_task,
                copy_section=self.copy_section,
                rename_section=self.rename_section,
                delete_section=self.confirm_delete_section,
                move_section=self.move_section,
                add_named_task=self.add_named_task,
                add_named_child=self.add_named_child,
                add_named_summary=self.add_named_summary,
                add_named_section=self.add_named_section,
                toggle_weeks=self.toggle_weeks,
                edit_week_crew=self.edit_week_crew,
                open_reference=self.open_reference,
                refresh_reference=self.refresh_reference,
            ),
            name_width=load_name_width(base_dir),
            references=lambda: build_references(self.project, self.reference_resolver, datetime.now()),
        )
        self.preview_bar = PreviewBar(
            self.on_preview_change, self.exit_preview, self.save_image, self.save_plantuml, self.on_select_all
        )
        self.dashboard_view = DashboardView(
            self.close_dashboard,
            self.change_dashboard_period,
            self.change_dashboard_member,
            self.change_dashboard_cross,
            self.change_dashboard_project,
            self.change_dashboard_custom,
            on_team_change=self.change_dashboard_team,
            actions=ViewActions(
                select=self.select_dashboard_view,
                save=self.save_dashboard_view,
                save_as=self.save_dashboard_view_as,
                revert=self.revert_dashboard_view,
                rename=self.rename_dashboard_view,
                delete=self.delete_dashboard_view,
                move_card=self.move_dashboard_card,
                hide_card=self.hide_dashboard_card,
                show_card=self.show_dashboard_card,
            ),
        )

    @staticmethod
    def dark_value(theme: str, colors: CustomTheme) -> bool | None:
        """`ui.dark_mode`の値。自動は None、カスタムは基調に従う。"""
        if theme == "custom":
            return colors.base == "dark"
        return None if theme == "auto" else theme == "dark"

    def apply_theme(self, theme: str, custom: CustomTheme | None = None) -> None:
        """テーマを画面に反映する(保存はしない)。`custom`を渡すと、保存済みでなくその色で見せる(プレビュー)。"""
        was_custom = self.theme == "custom"
        self.theme = theme
        colors = custom or self.custom_theme
        self.dark.value = self.dark_value(theme, colors)
        if theme == "custom":
            self.run_js(theme_js(colors))
        elif was_custom:
            self.run_js(theme_js(None))  # カスタムの変数が付いているときだけ外す

    def set_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        self.gantt.refresh_scrollbars()  # 標準のスクロールバーは、切り替えだけでは配色が変わらない
        save_theme(theme, self.base_dir)
        self.theme_menu.refresh()

    def open_theme_dialog(self) -> None:
        """カスタムの色のダイアログ。色を変えると画面に反映し(プレビュー)、キャンセルで開く前に戻す。"""
        previous = self.theme
        show_theme_dialog(self.custom_theme, self.preview_custom, self.apply_custom, lambda: self.restore_theme(previous))

    def preview_custom(self, theme: CustomTheme) -> None:
        self.apply_theme("custom", theme)
        self.gantt.refresh_scrollbars()

    def restore_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        self.gantt.refresh_scrollbars()

    def apply_custom(self, theme: CustomTheme) -> bool:
        """色と`theme: custom`を 1 回の書き込みで保存する。失敗したら通知して False(保存済みの色は変えない)。"""
        try:
            save_custom_theme(theme, self.base_dir, select=True)
        except OSError:
            ui.notify("テーマを保存できませんでした", type="warning")
            return False
        self.custom_theme = theme
        self.apply_theme("custom")
        self.theme_menu.refresh()
        return True

    def open_today_color_dialog(self) -> None:
        """今日の線の色のダイアログ。色を変えると画面に反映し(プレビュー)、キャンセルで保存済みの色に戻す。"""
        show_today_color_dialog(
            self.today_color,
            lambda color: self.run_js(today_color_js(color)),
            self.apply_today_color,
            lambda: self.run_js(today_color_js(self.today_color)),
        )

    def apply_today_color(self, color: str | None) -> bool:
        """今日の線の色を保存する。失敗したら通知して False(保存済みの色は変えない)。"""
        try:
            save_today_color(color, self.base_dir)
        except OSError:
            ui.notify("今日の線の色を保存できませんでした", type="warning")
            return False
        self.today_color = color
        self.run_js(today_color_js(color))
        return True

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

    def after_edit(self) -> None:
        """編集のあとの共通の処理。直前の確定した状態と違えば履歴に積み、画面を描き直す(Undo の入口はここだけ)。"""
        if self.project != self.committed:
            self.history.record(self.committed)
            self.committed = deepcopy(self.project)
        self.gantt.set_project(self.project)

    def reset_history(self) -> None:
        """履歴を捨て、いまの内容を確定した状態にする(別のプロジェクトに切り替えたとき・名前をつけて保存したとき)。"""
        self.history.clear()
        self.committed = deepcopy(self.project)
        self.gantt.clear_selection()  # 履歴を捨てる場面(開く・新規・取り込み・名前をつけて保存)では、一括操作の選択も解除する

    def restore(self, project: Project) -> None:
        """Undo・Redo で取り出した状態に差し替えて描き直す。折りたたみはセクションの id で引き継ぎ、絞り込み・スクロールは変えない。"""
        folded = arrange.collapsed_ids(self.project, self.gantt.collapsed)
        self.project = project
        self.gantt.collapsed = arrange.collapsed_paths(project, folded)
        self.committed = deepcopy(project)
        self.gantt.set_project(self.project)

    def undo(self) -> None:
        restored = self.history.undo(self.project)
        if restored is None:
            ui.notify("これ以上戻せません")
            return
        self.restore(restored)
        ui.notify("元に戻しました")

    def redo(self) -> None:
        restored = self.history.redo(self.project)
        if restored is None:
            ui.notify("やり直す操作がありません")
            return
        self.restore(restored)
        ui.notify("やり直しました")

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
            with self.client:  # 確認ダイアログの中で作ると、確認が閉じて削除されるときに一緒に消える
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
        pending, self.pending_origin = self.pending_origin, None
        self.origin = pending[0] if pending is not None and path is not None and path.stem == pending[1] else None
        self.path, self.project, self.digest = path, project, digest
        self.mark_clean()
        self.file_select.set_value(path.stem if path else None)
        self.title.refresh()
        self.gantt.reset_collapsed()  # 折りたたみは保存しない。別のプロジェクトは全展開から始める
        self.gantt.set_period(None)  # 表示期間も、別のプロジェクトでは古い期間が何も映さないことがあるので自動に戻す
        self.reset_history()
        self.gantt.set_project(self.project)
        self.gantt.reset_filter()
        self.gantt.scroll_on_open()  # 別のプロジェクトは、先頭に戻してから今日の位置へ(編集後の再描画では動かさない)
        for name in missing_references(project, self.reference_resolver, datetime.now()):
            ui.notify(f"参照先のプロジェクトが見つかりません: {name}", type="warning")
        if stale := self.stale_references():
            open_stale_snapshot_dialog(stale, "続ける", self.refresh_stale_snapshots, lambda: None)

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

    def request_import_plantuml(self) -> None:
        """PlantUML の取り込みを始める(ネイティブのみ)。編集中は、確認してからファイルを選ばせる。"""
        self.request_import(self.pick_plantuml)

    def request_import_csv(self) -> None:
        """CSV・TSV の取り込みを始める(ネイティブのみ)。編集中は、確認してからファイルを選ばせる。"""
        self.request_import(self.pick_csv)

    def request_import(self, pick: Callable[[], None]) -> None:
        if not self.exporter.available:
            ui.notify(IMPORT_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not self.is_dirty():
            pick()
            return
        open_unsaved_dialog(
            on_save=lambda: self.save_then(pick),
            on_discard=pick,
            purpose="取り込み",
        )

    def pick_csv(self) -> None:
        """ファイル選択を始める(`pick_plantuml` と同じ理由で、タイマーは画面の直下に置く)。"""
        with self.client:
            ui.timer(0, self.import_csv, once=True)

    async def import_csv(self) -> None:
        """選んだ CSV・TSV から、保存前の新規プロジェクトを作る。失敗したら、通知だけして何も変えない。"""
        path = await self.exporter.ask_open_path(CSV_OPEN_FILE_TYPES)
        if path is None:
            return
        try:
            result = parse_csv(read_table(path), path.stem, self.holidays)
        except CsvImportError as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        self.show_project(result.project, None)
        self.snapshot = asdict(Project(NEW_PROJECT_NAME))  # 空の新規とは別物なので、未保存の扱いにする
        ui.notify(csv_import_summary(result))

    def request_import_settings(self) -> None:
        """設定の取り込みを始める(ネイティブのみ)。プロジェクトは置き換えず、今のプロジェクトへ足すので、編集中でも確認しない。"""
        if not self.exporter.available:
            ui.notify(IMPORT_NOT_NATIVE_MESSAGE, type="warning")
            return
        with self.client:  # `pick_csv` と同じ理由で、タイマーは画面の直下に置く
            ui.timer(0, self.import_settings, once=True)

    async def import_settings(self) -> None:
        """選んだ設定ファイルを読み、取り込みのダイアログを開く。失敗したら、通知だけして何も変えない。"""
        path = await self.exporter.ask_open_path(SETTINGS_FILE_TYPES)
        if path is None:
            return
        try:
            incoming = parse_settings(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # UnicodeDecodeError は ValueError
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        plan = plan_import(self.project, incoming)
        if not plan.sections and not plan.project_changes:
            ui.notify("取り込める項目がありません")
            return
        with self.client:
            open_import_dialog(plan, lambda sections, overwrite: self.apply_settings_import(incoming, sections, overwrite))

    def apply_settings_import(self, incoming: ImportFile, sections: set[str], overwrite: set[tuple[str, str]]) -> None:
        """選んだ内容を取り込む。相対比率の上限・下限が変わり、見直しが要るタスクがあるときは、先に選ばせる。"""
        try:
            result = apply_import(self.project, incoming, sections, overwrite)
        except ValueError as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        old, new = self.project.ratio_limits, result.project.ratio_limits
        reviews: list[tuple[Task, datetime]] = []
        if new != old:
            before = replace(result.project, ratio_limit_upper=old.upper, ratio_limit_lower=old.lower)
            reviews = limit_reviews(before, new, self.holidays, datetime.now())
        if not reviews:
            self.commit_settings_import(result)
            return
        ends = {task.id: end for task, end in reviews}

        def choose(review: bool | None) -> None:
            if review is None:  # キャンセルは、プロジェクト設定の反映だけを取り消す
                self.apply_settings_import(incoming, sections - {"project"}, overwrite)
            else:
                self.commit_settings_import(result, ends if review else None)

        self.ask_limit_review(len(reviews), choose, "プロジェクト設定は取り込みませんでした")

    def commit_settings_import(self, result: ImportResult, ends: dict[str, datetime] | None = None) -> None:
        """取り込み後のプロジェクトを今のプロジェクトへ移し、1 回の編集として確定する。"""
        for task in result.project.all_tasks():
            if ends and task.id in ends:
                task.planned_end, task.planned_end_manual = ends[task.id], True
        mode_changed = result.project.reference_mode is not self.project.reference_mode
        copy_into(self.project, result.project)
        if mode_changed:
            self.refresh_all_snapshots()
        self.after_edit()
        ui.notify(settings_import_summary(result))

    async def export_settings(self) -> None:
        """設定値(プロジェクト設定・メンバー・パラメータなど)を書き出す。プロジェクトは変えない(保存も、変更扱いもしない)。"""
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        path = await self.exporter.ask_path(SETTINGS_DEFAULT_FILENAME, SETTINGS_FILE_TYPES)
        if path is None:
            return
        try:
            written = write_settings(path, build_settings(self.project))
        except (OSError, ValueError) as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        ui.notify(f"書き出しました({written.name})")

    async def export_tsv(self) -> None:
        """通常タスクとセクションを TSV に書き出す。プロジェクトは変えない(保存も、変更扱いもしない)。"""
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        now = datetime.now()
        values = {
            tid: ref.value
            for tid, ref in build_references(self.project, self.reference_resolver, now).items()
            if ref.value is not None
        }
        result = build_tsv(self.project, self.holidays, values)
        if result.task_count == 0 and result.section_count == 0 and result.references == 0:
            ui.notify("書き出せるタスクがありません", type="warning")
            return
        path = await self.exporter.ask_path(TSV_DEFAULT_FILENAME, TSV_FILE_TYPES)
        if path is None:
            return
        try:
            write_tsv(path, result.text)
        except OSError as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        notes = [
            f"{result.skipped} 件(まとめ・節目)は書き出していません" if result.skipped else "",
            f"担当者が複数の {result.multiple_owners} 件は筆頭だけを書きました" if result.multiple_owners else "",
            f"参照先が読めない {result.unresolved} 件は、日付と完了率を空にしました" if result.unresolved else "",
        ]
        detail = "、".join(note for note in notes if note)
        head = f"書き出しました(タスク {result.task_count} 件、参照 {result.references} 件、セクション {result.section_count} 件)"
        ui.notify(head + (f"。{detail}" if detail else ""))

    def pick_plantuml(self) -> None:
        """ファイル選択を始める。確認ダイアログは閉じると消えるので、タイマーは画面の直下に置く。"""
        with self.client:
            ui.timer(0, self.import_plantuml, once=True)

    async def import_plantuml(self) -> None:
        """選んだ PlantUML から、保存前の新規プロジェクトを作る。失敗したら、通知だけして何も変えない。"""
        path = await self.exporter.ask_open_path(PLANTUML_OPEN_FILE_TYPES)
        if path is None:
            return
        try:
            result = parse_plantuml(read_plantuml(path), path.stem)
        except PlantUmlImportError as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        self.show_project(result.project, None)
        self.snapshot = asdict(Project(NEW_PROJECT_NAME))  # 空の新規とは別物なので、未保存の扱いにする
        ui.notify(import_summary(result))

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
        with self.client:  # 確認ダイアログの中で作ると、確認が閉じて削除されるときに一緒に消える
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
            events=self.project.events,
            on_events=self.apply_events,
            used_ids=self.project.used_ids(),
            base_date=self.project.base_date,
            on_base_date=self.apply_base_date,
            reference_mode=self.project.reference_mode,
            on_reference_mode=self.apply_reference_mode,
            plantuml_notice=self.project.plantuml_overload_notice,
            on_plantuml_notice=self.apply_plantuml_notice,
            ratio_limits=self.project.ratio_limits,
            on_ratio_limits=self.apply_ratio_limits,
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
        self.apply_select_popup()
        try:
            save_zoom(zoom, self.base_dir)
        except OSError:
            ui.notify("倍率を保存できませんでした", type="warning")

    def apply_select_popup(self) -> None:
        """倍率が 100% でないあいだ、プルダウンの候補を専用のダイアログで出す。

        Quasar のメニューは、位置を `window.innerHeight` で決める。CSS の `zoom` をかけた画面では、見える範囲が
        その倍率ぶん狭いので、メニューが画面の下にはみ出し、下の候補が見えなくなる(拡大のときだけ)。
        ダイアログ形式なら位置の計算を使わない。これから作るプルダウンは `default_props` で、いま画面にあるものは
        個別に切り替える(`default_props` はクラスに付くので、100% に戻すときは外す)。"""
        zoomed = self.zoom != DEFAULT_ZOOM_PERCENT
        if zoomed:
            ui.select.default_props("behavior=dialog")
        else:
            ui.select.default_props(remove="behavior")
        for element in list(self.client.elements.values()):
            if isinstance(element, ui.select):
                if zoomed:
                    element.props("behavior=dialog")
                else:
                    element.props(remove="behavior")

    def set_task_sections(self, keys: list[str]) -> None:
        """タスクのダイアログの節の開閉を覚える。保存できなくても、画面には反映する(通知だけ出す)。"""
        self.task_sections = keys
        try:
            save_task_sections(keys, self.base_dir)
        except OSError:
            ui.notify("節の開閉を保存できませんでした", type="warning")

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
        "git_pull": "start_git_pull",
        "undo": "undo",
        "redo": "redo",
        "bulk_delete": "delete_selected",
    }

    def on_plain_key(self, event: KeyEventArguments) -> None:
        if not (event.modifiers.ctrl or event.modifiers.meta):
            self.on_key(event)

    def on_modified_key(self, event: KeyEventArguments) -> None:
        """Ctrl/Cmd 付きは入力欄でも受ける側。ただし、入力欄に任せるキー(Ctrl/Cmd+Z)は、`on_undo_key` が受ける。"""
        ctrl = event.modifiers.ctrl or event.modifiers.meta
        if ctrl and not defers_to_inputs(event.key.name, ctrl):
            self.on_key(event)

    def on_undo_key(self, event: KeyEventArguments) -> None:
        """入力欄に任せるキー(Ctrl/Cmd+Z)を受ける側。入力欄では NiceGUI が送らない。ボタンにフォーカスがあるときは受ける
        (文字キー用は button を無視するので、ダイアログを閉じてフォーカスがボタンに戻ったあとも、Undo が届くように)。"""
        ctrl = event.modifiers.ctrl or event.modifiers.meta
        if ctrl and defers_to_inputs(event.key.name, ctrl):
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
            self.escape_pressed()
        elif action == "search":
            self.gantt.focus_search()
        elif action == "help":
            self.help_dialog.open()
        elif action in ZOOM_DIRECTIONS:
            self.change_zoom(ZOOM_DIRECTIONS[action])
        elif action is not None:
            getattr(self, self.SHORTCUT_METHODS[action])()

    def delete_selected(self) -> None:
        """Delete キー。選択中のタスクの一括削除を、確認つきで呼ぶ(選択がなければ何もしない)。"""
        ids = self.gantt.selected_ids()
        if ids:
            self.confirm_bulk_delete(ids)

    def escape_pressed(self) -> None:
        """ESC。プレビュー・ダッシュボードから戻る。何もなければ(ダイアログが開いていないとき)一括操作の選択を解除する。"""
        if self.preview is not None:
            self.exit_preview()
        elif self.dashboard_kind is not None:
            self.close_dashboard()
        elif not self.dialog_open() and self.gantt.has_selection():
            self.gantt.clear_selection()

    def set_header_visible(self, visible: bool) -> None:
        """ヘッダーと、メイン側のタイトルを、一緒に出す・隠す(プレビューとダッシュボードの出入り)。"""
        self.header_box.set_visibility(visible)
        self.title_box.set_visibility(visible)

    def open_dashboard(self) -> None:
        """メイン画面を、ダッシュボードに切り替える(期間の初期値は今週)。プレビュー中は開かない。"""
        if self.preview is not None or self.dashboard_kind is not None:
            return
        self.dashboard_kind = PeriodKind.WEEK
        self.dashboard_custom = None
        self.dashboard_custom_error = ""
        self.set_header_visible(False)
        self.gantt.set_visible(False)
        self.apply_dashboard_view(self.saved_dashboard_view(self.dashboard_view_name))
        self.refresh_dashboard()

    def refresh_dashboard(self, sync_field: bool = True) -> None:
        """集計して描き直す。sync_field が偽のときは、`指定` の欄の文字を書き換えない(欄で入力している最中)。"""
        if self.dashboard_kind is None:
            return
        now = self.now()
        period = period_for(self.dashboard_kind, now.date(), self.project, self.holidays, self.dashboard_custom)
        projects = [self.project]
        failures = []
        if self.dashboard_cross:
            others, failures = load_others(self.project_dir, self.path)
            if self.project.name in {p.name for p in others}:  # 保存前の新規などが、ファイルと同名のとき
                projects = [replace(self.project, name=f"{self.project.name}(開いている)")]
            projects += others
        names = list(dict.fromkeys(m.name for p in projects for m in p.members))
        self.dashboard_names = names
        if self.dashboard_member not in names:
            self.dashboard_member = None  # 削除・改名・横断オフで見えなくなったメンバーは、全員に戻す
        if self.dashboard_member is not None or self.dashboard_team not in (None, *teams_with_members(self.project)):
            self.dashboard_team = None  # 消えたチームは全員に戻す。メンバーを選んでいるときはチームを使わない
        data = summarize(
            self.project,
            period,
            now,
            self.holidays,
            self.dashboard_kind,
            self.dashboard_member,
            self.dashboard_team,
            load_children(self.project, self.reference_resolver, self.base_holidays),
        )
        if self.dashboard_cross:
            chosen = [p for p in projects if p.name not in self.dashboard_excluded]
            scope = self.dashboard_member if self.dashboard_member is not None else team_scope(self.project, self.dashboard_team)
            loads = summarize_cross_loads(chosen, period, self.base_holidays, scope)
            titles = [p.name for p in projects]
            data.cross = CrossSummary(loads, titles, self.dashboard_excluded & set(titles), failures)
            data.members = names
        icons = {m.name: m.icon for p in reversed(projects) for m in p.members if m.icon}
        # 入力が不正なあいだは、欄の文字を書き換えない(入力中の値を残す)
        custom_text = format_period(period.start, period.end) if sync_field and not self.dashboard_custom_error else None
        self.dashboard_view.show(
            data, self.dashboard_kind, icons, custom_text, self.dashboard_custom_error, self.dashboard_view_state()
        )

    def change_dashboard_cross(self, on: bool) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cross = on
        self.refresh_dashboard()

    def change_dashboard_project(self, name: str, included: bool) -> None:
        if self.dashboard_kind is None:
            return
        (self.dashboard_excluded.discard if included else self.dashboard_excluded.add)(name)
        self.refresh_dashboard()

    def starting_custom_period(self) -> Period:
        """`指定` を始めるときの期間 = 直前に見ていた期間。全期間が長いときは、終わりの側の上限の長さに切る。"""
        previous = period_for(
            self.dashboard_kind or PeriodKind.WEEK, self.now().date(), self.project, self.holidays, self.dashboard_custom
        )
        if custom_period_error(previous):
            previous = Period(previous.end - timedelta(days=MAX_CUSTOM_DAYS - 1), previous.end)
        return previous

    def change_dashboard_period(self, kind: PeriodKind) -> None:
        if self.dashboard_kind is None:
            return
        if kind is PeriodKind.CUSTOM:
            self.dashboard_custom = self.starting_custom_period()
        self.dashboard_custom_error = ""
        self.dashboard_kind = kind
        self.refresh_dashboard()

    def change_dashboard_custom(self, text: str) -> None:
        """`指定` の期間の欄が変わった。不正・長すぎる値はエラーを出して、前の期間のままにする。"""
        if self.dashboard_kind is not PeriodKind.CUSTOM:
            return
        try:
            start, end = validate_period(*split_period(text))
        except ValueError as exc:
            error, period = str(exc), None
        else:
            period = Period(start, end)
            error = custom_period_error(period) or ""
            period = None if error else period
        self.dashboard_custom_error = error
        if period is not None and period != self.dashboard_custom:
            self.dashboard_custom = period
            self.refresh_dashboard(sync_field=False)  # 期間が変わったときだけ、集計し直す
        else:
            self.dashboard_view.set_custom_error(error)  # 入力の途中(不正・同じ期間)では、エラー表示だけを更新する

    def change_dashboard_member(self, name: str | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_member = name
        self.dashboard_team = None  # メンバーとチームは、どちらか一方
        self.refresh_dashboard()

    def change_dashboard_team(self, name: str | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_team = name
        self.dashboard_member = None
        self.refresh_dashboard()

    def saved_dashboard_view(self, name: str) -> ViewSpec:
        """保存済みのビュー。名前がなければ `標準`。"""
        return next((v for v in self.dashboard_views if v.name == name), standard_view())

    def working_spec(self, name: str) -> ViewSpec:
        """今の画面の条件とカードの並びを、ビューの形にしたもの。"""
        custom = None
        if self.dashboard_kind is PeriodKind.CUSTOM and self.dashboard_custom is not None and not self.dashboard_custom_error:
            custom = (self.dashboard_custom.start, self.dashboard_custom.end)
        return ViewSpec(
            name,
            self.dashboard_kind or PeriodKind.WEEK,
            self.dashboard_member,
            self.dashboard_cross,
            self.dashboard_cards,
            custom,
            self.dashboard_team,
        )

    def dashboard_dirty(self) -> bool:
        """保存したビューと違うか。保存したメンバーがいないときは、全員に戻した状態を同じとみなす。"""
        saved = self.saved_dashboard_view(self.dashboard_view_name)
        saved = replace(
            saved,
            member=resolve_member(saved.member, self.dashboard_names),
            team=resolve_team(saved.team, teams_with_members(self.project)),
        )
        if saved.member is not None:
            saved = replace(saved, team=None)  # 両方あればメンバー優先
        return self.working_spec(saved.name) != saved

    def custom_save_block(self) -> str | None:
        if self.dashboard_kind is PeriodKind.CUSTOM and (self.dashboard_custom_error or self.dashboard_custom is None):
            return "期間の欄を直してください"
        return None

    def dashboard_save_block(self) -> str | None:
        """`保存` できない理由。`標準` は上書きできない。"""
        if self.dashboard_view_name == STANDARD_NAME:
            return "「標準」は上書きできません。名前をつけて保存してください"
        return self.custom_save_block()

    def dashboard_view_state(self) -> ViewState:
        return ViewState(
            (STANDARD_NAME, *(v.name for v in self.dashboard_views)),
            self.dashboard_view_name,
            self.dashboard_dirty(),
            self.dashboard_save_block(),
            self.dashboard_cards,
            hidden_cards(self.dashboard_cards, self.dashboard_cross),
        )

    def apply_dashboard_view(self, spec: ViewSpec) -> None:
        """ビューの条件とカードの並びを、画面の状態に取り込む(集計し直さない)。除外したプロジェクトは空に戻る。"""
        self.dashboard_view_name = spec.name
        self.dashboard_kind = spec.period
        if spec.period is PeriodKind.CUSTOM:
            self.dashboard_custom = Period(*spec.custom) if spec.custom is not None else self.starting_custom_period()
        self.dashboard_custom_error = ""
        self.dashboard_member = spec.member
        self.dashboard_team = None if spec.member is not None else spec.team
        self.dashboard_cross = spec.cross
        self.dashboard_excluded = set()
        self.dashboard_cards = spec.cards

    def persist_dashboard(self, *, views: bool = False, last: bool = False) -> None:
        """設定に書く。書けなくても、画面上のビューは使い続ける(通知だけ出す)。"""
        try:
            if views:
                save_dashboard_views(self.dashboard_views, self.base_dir)
            if last:
                save_dashboard_view_last(self.dashboard_view_name, self.base_dir)
        except (OSError, ValueError):  # ValueError = 壊れた config.json(読めないファイルは上書きしない)
            ui.notify("ダッシュボードのビューを保存できませんでした(この画面では使い続けられます)")

    def select_dashboard_view(self, name: str) -> None:
        if self.dashboard_kind is None or (name != STANDARD_NAME and all(v.name != name for v in self.dashboard_views)):
            return
        self.apply_dashboard_view(self.saved_dashboard_view(name))
        self.persist_dashboard(last=True)
        self.refresh_dashboard()

    def save_dashboard_view(self) -> None:
        if self.dashboard_kind is None:
            return
        if reason := self.dashboard_save_block():
            ui.notify(reason)
            return
        name = self.dashboard_view_name
        self.dashboard_views = [self.working_spec(name) if v.name == name else v for v in self.dashboard_views]
        self.persist_dashboard(views=True)
        self.refresh_dashboard()
        ui.notify(f"ビュー「{name}」を保存しました")

    def save_dashboard_view_as(self) -> None:
        if self.dashboard_kind is None:
            return
        if reason := self.custom_save_block():
            ui.notify(reason)
            return

        def validate(clean: str) -> str | None:
            if len(self.dashboard_views) >= MAX_VIEWS:
                return f"ビューは{MAX_VIEWS}件までです"
            return validate_view_name(clean, (v.name for v in self.dashboard_views))

        def apply(name: str) -> None:
            self.dashboard_views = [*self.dashboard_views, self.working_spec(name)]
            self.dashboard_view_name = name
            self.persist_dashboard(views=True, last=True)
            self.refresh_dashboard()

        open_name_dialog(apply, validate, title="ビューの保存", label="ビュー名")

    def revert_dashboard_view(self) -> None:
        if self.dashboard_kind is None:
            return
        self.apply_dashboard_view(self.saved_dashboard_view(self.dashboard_view_name))
        self.refresh_dashboard()

    def rename_dashboard_view(self) -> None:
        old = self.dashboard_view_name
        if self.dashboard_kind is None or old == STANDARD_NAME:
            return

        def apply(name: str) -> None:
            self.dashboard_views = [replace(v, name=name) if v.name == old else v for v in self.dashboard_views]
            self.dashboard_view_name = name
            self.persist_dashboard(views=True, last=True)
            self.refresh_dashboard()

        others = [v.name for v in self.dashboard_views if v.name != old]
        open_name_dialog(
            apply, lambda clean: validate_view_name(clean, others), title="ビュー名の変更", initial=old, label="ビュー名"
        )

    def delete_dashboard_view(self) -> None:
        name = self.dashboard_view_name
        if self.dashboard_kind is None or name == STANDARD_NAME:
            return

        def apply() -> None:
            self.dashboard_views = [v for v in self.dashboard_views if v.name != name]
            self.apply_dashboard_view(standard_view())
            self.persist_dashboard(views=True, last=True)
            self.refresh_dashboard()

        open_confirm_dialog(f"ビュー「{name}」を削除しますか?", apply)

    def move_dashboard_card(self, card_id: CardId, before_id: CardId | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cards = move_card(self.dashboard_cards, card_id, before_id)
        self.refresh_dashboard()

    def hide_dashboard_card(self, card_id: CardId) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cards = hide_card(self.dashboard_cards, card_id)
        self.refresh_dashboard()

    def show_dashboard_card(self, card_id: CardId) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cards = show_card(self.dashboard_cards, card_id)
        self.refresh_dashboard()

    def close_dashboard(self) -> None:
        """ダッシュボードから戻る。ガントチャートは作り直さない(絞り込み・スケール・位置はそのまま)。"""
        if self.dashboard_kind is None:
            return
        self.dashboard_kind = None
        self.dashboard_view.hide()
        self.set_header_visible(True)
        self.gantt.set_visible(True)

    def reference_values(self) -> dict[str, ReferenceValue]:
        """参照行(タスクの id)ごとの参照値。読めない参照先は含めない。"""
        refs = build_references(self.project, self.reference_resolver, datetime.now())
        return {tid: ref.value for tid, ref in refs.items() if ref.value is not None}

    def enter_preview(self) -> None:
        """メイン画面を、プレビューモードに切り替える。初期値は、メインの期間(指定があれば)か今の表示範囲と、今のスケール。"""
        if self.preview is not None or self.dashboard_kind is not None:
            return
        if self.gantt.period is not None:
            period = self.gantt.period  # メインで期間を指定しているときは、それから始める
            start = period[0]
        else:
            start, end = visible_range(self.project, self.holidays, self.reference_values())
            period = (start, max(end - timedelta(days=1), start))  # タスクがないと、範囲が空になる。基準日の 1 日にする
        scale = fit_scale(
            self.project, self.holidays, period, self.gantt.scale, self.gantt.name_width, self.reference_values()
        )
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
        start_text, end_text, scale, chips, alerts, events, today = self.preview_bar.read()
        try:
            start, end = validate_period(start_text, end_text)
        except ValueError as exc:
            self.preview_bar.set_error(str(exc))
            self.preview_bar.set_warning(None)
            self.preview_bar.set_save_enabled(False)
            return
        too_long = check_column_count(scale, len(build_columns(self.project, scale, self.holidays, (start, end), self.reference_values())))
        if too_long is not None:
            self.preview_bar.set_error(too_long)
            self.preview_bar.set_warning(None)
            self.preview_bar.set_save_enabled(False)
            return
        self.preview = PreviewSettings(start, end, scale, chips, alerts, events, self.preview.excluded, show_today=today)
        self.apply_preview(self.preview)

    def selectable_ids(self) -> list[str]:
        """出力の選択の対象になる全タスクの id(まとめ自身は除く)。"""
        return [t.id for t in self.project.all_tasks() if t.kind is not TaskKind.SUMMARY]

    def select_in_preview(self, ids: list[str], checked: bool) -> None:
        """プレビューで、ids を出力する・しないにする。保存中は撮っている画面を変えない。"""
        if self.preview is None or self.saving:
            return
        excluded = set_checked(self.preview.excluded, ids, checked)
        self.preview = replace(self.preview, excluded=excluded)
        self.apply_preview(self.preview)

    def on_select_all(self, checked: bool) -> None:
        self.select_in_preview(self.selectable_ids(), checked)

    def apply_preview(self, settings: PreviewSettings) -> None:
        self.gantt.set_options(settings.to_options(self.select_in_preview))
        ids = self.selectable_ids()
        self.preview_bar.set_selection(sum(1 for i in ids if i not in settings.excluded), len(ids))
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
        if self.preview.excluded and len(self.preview.excluded) >= len(self.selectable_ids()):
            ui.notify("出力するタスクがありません", type="warning")
            return
        self.saving = True
        self.preview_bar.set_save_enabled(False)
        if self.zoom != 100:
            self.run_js(zoom_js(100))  # 倍率をかけたままだと、画像の大きさがずれる
        try:
            ratio = export_pixel_ratio(self.gantt.content_width())
            # チェックを外した行とチェックボックスは、撮る間だけ描かない(全部チェックのままでも、チェックボックスは出さない)
            self.gantt.set_options(replace(self.preview.to_options(), selectable=False, hide_excluded=True))
            await asyncio.sleep(0)  # 描き直し(バックグラウンドで走る)を先に進めてから撮る
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
                self.gantt.set_options(self.preview.to_options(self.select_in_preview))
                self.preview_bar.set_save_enabled(self.exporter.available)

    async def save_plantuml(self) -> None:
        """プレビューの設定で、ガントチャートを PlantUML のテキストにして、選んだ場所へ保存する。失敗しても、プレビューに留まる。"""
        if self.preview is None or self.saving or not self.exporter.available:
            return
        settings = self.preview
        result = build_plantuml(
            self.project,
            self.holidays,
            (settings.start, settings.end),
            settings.scale,
            self.gantt.task_filter,
            datetime.now(),
            show_chips=settings.show_chips,
            show_alerts=settings.show_alerts,
            show_events=settings.show_events,
            show_today=settings.show_today,
            today_color=self.today_color,
            excluded=settings.excluded,
            references=self.reference_values(),
        )
        if result.task_count == 0:
            ui.notify("出力できるタスクがありません", type="warning")
            return
        self.saving = True
        self.preview_bar.set_save_enabled(False)
        try:
            path = await self.exporter.ask_path(plantuml_filename(self.project.name, date.today()), PLANTUML_FILE_TYPES)
            if path is None:
                return
            try:
                write_text(path, result.text)
            except OSError as exc:
                ui.notify(f"保存できませんでした: {exc}", type="negative")
                return
            note = f"(期間の外などで {result.skipped} 件を省きました)" if result.skipped else ""
            ui.notify(f"保存しました{note}")
            if self.project.plantuml_overload_notice and (warning := day_overload_notice(result.day_overloads)) is not None:
                ui.notify(warning, type="warning", timeout=10000)
            if (approx := weekly_crew_notice(result.weekly_tasks)) is not None:
                ui.notify(approx, type="warning", timeout=10000)
        finally:
            self.saving = False
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
        opened = deepcopy(self.project)  # 開いた時点。`キャンセル`の「すべて取り消す」で戻る
        saved_history = self.history.snapshot()

        def rollback() -> None:
            self.restore(deepcopy(opened))
            self.history.rollback(saved_history)

        open_members_parameters_dialog(
            get_members=lambda: self.project.members,
            assigned=self.assigned_count,
            on_apply_members=self.apply_members,
            get_parameters=lambda: self.project.parameters,
            impacts=lambda edit: impact_lines(self.project, edit),
            on_apply_parameters=self.apply_parameters,
            get_taken=self.project.used_ids,
            pick_icon=self.pick_member_icon if self.exporter.available else None,
            applied=lambda: self.project != opened,
            rollback=rollback,
            get_limits=lambda: self.project.ratio_limits,
            get_holidays=lambda: self.holidays,
            get_teams=lambda: self.project.teams,
            team_impacts=lambda teams: removal_impacts(self.project, teams),
            on_apply_teams=self.apply_teams,
        )

    async def pick_member_icon(self) -> str | None:
        """メンバーのアイコンにする画像を選ばせる。キャンセルと、画像にできないとき(理由を通知)は None。"""
        path = await self.exporter.ask_open_path(ICON_FILE_TYPES)
        if path is None:
            return None
        try:
            return load_icon(path)
        except (IconError, OSError) as exc:
            ui.notify(f"アイコンにできませんでした: {exc}", type="negative")
            return None

    def assigned_count(self, name: str) -> int:
        return sum(1 for task in self.project.all_tasks() if name in task.assignee_names)

    def apply_members(self, members: list[Member], renames: dict[str, str]) -> None:
        """メンバーを更新し、改名をタスクの担当者に伝える。保存はしない(編集中の判定に入る)。"""
        if members == self.project.members and not renames:
            return
        self.project.members = members
        if renames:
            for task in self.project.all_tasks():
                for assignee in [*task.assignees, *(a for week in task.weekly_crew for a in week)]:
                    if assignee.name in renames:
                        assignee.name = renames[assignee.name]
        self.after_edit()

    def apply_teams(self, teams: list[Team]) -> None:
        """チームを更新し、消えたチームへの所属をメンバーから外す。保存はしない(編集中の判定に入る)。"""
        if [(t.id, t.name) for t in teams] == [(t.id, t.name) for t in self.project.teams]:
            return
        replace_teams(self.project, teams)
        self.after_edit()

    def apply_parameters(self, edit: ParameterEdit) -> None:
        """パラメータの定義を更新し、メンバーの選択に改名・削除を伝える。保存はしない(編集中の判定に入る)。"""
        if not edit.changes(self.project.parameters):
            return
        apply_parameter_edit(self.project, edit)
        self.after_edit()

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
        self.after_edit()

    def apply_base_date(self, day: date) -> None:
        """基準日(プロジェクト開始日)を更新して再描画する。同じ日なら何もしない。保存はしない。"""
        if day == self.project.base_date:
            return
        self.project.base_date = day
        self.after_edit()

    def apply_plantuml_notice(self, enabled: bool) -> None:
        """PlantUML の保存後の「100% 超に見える」通知の、出す・出さないを変える。保存はしない。"""
        if enabled is self.project.plantuml_overload_notice:
            return
        self.project.plantuml_overload_notice = enabled
        self.after_edit()

    def apply_ratio_limits(self, limits: RatioLimits) -> None:
        """相対比率の下限・上限を変える。実績か進捗のあるタスクの完了予定が変わるときは、見直しを選ばせる。"""
        if limits == self.project.ratio_limits:
            return
        reviews = limit_reviews(self.project, limits, self.holidays, datetime.now())

        def commit(review: bool) -> None:
            if review:
                for task, end in reviews:
                    task.planned_end, task.planned_end_manual = end, True
            self.project.ratio_limit_upper, self.project.ratio_limit_lower = limits.upper, limits.lower
            self.after_edit()

        if not reviews:
            commit(False)
            return
        self.ask_limit_review(
            len(reviews), lambda review: commit(review) if review is not None else None, "上限・下限は変更しませんでした"
        )

    def ask_limit_review(self, count: int, on_choice: Callable[[bool | None], None], cancel_message: str) -> None:
        """相対比率の上限・下限の変更で完了予定を見直すかを選ばせる。見直す=True・見直さない=False・キャンセル=None で on_choice を 1 回呼ぶ。"""
        with self.client, ui.dialog() as dialog, ui.card():  # 設定ダイアログの中で作ると、それが閉じるときに一緒に消える
            ui.label(
                f"上限・下限の変更で、実績か進捗のある {count} 件のタスクの換算率が変わります。\n"
                "残りの作業を新しい条件で見直して、完了予定を手で指定の値にしますか。"
            ).classes("whitespace-pre-line")

            decided = [False]

            def choose(review: bool) -> None:
                decided[0] = True
                dialog.close()
                on_choice(review)

            def cancel() -> None:
                """ほかの設定は適用済みなので、制限だけが未適用と知らせる(外側クリックと ESC も同じ)。"""
                if not decided[0]:
                    decided[0] = True
                    ui.notify(cancel_message)
                    on_choice(None)
                dialog.close()

            dialog.on("hide", cancel)

            with ui.row():
                ui.button("見直して適用", on_click=lambda: choose(True)).mark("limit-review-apply")
                ui.button("見直さずに適用", on_click=lambda: choose(False)).props("flat").mark("limit-review-skip")
                ui.button("キャンセル", on_click=cancel).props("flat").mark("limit-review-cancel")
        dialog.open()

    def apply_reference_mode(self, mode: ReferenceMode) -> None:
        """参照の方式を変える。スナップショットへは全参照行のスナップショットをそのとき取り、常に最新へは捨てる。保存はしない。"""
        if mode is self.project.reference_mode:
            return
        self.project.reference_mode = mode
        self.refresh_all_snapshots()
        self.after_edit()

    def refresh_all_snapshots(self) -> None:
        """全参照行のスナップショットを方式に合わせて取り直す(スナップショットは取得、常に最新は捨てる)。"""
        now = datetime.now()
        snapshot = self.project.reference_mode is ReferenceMode.SNAPSHOT
        for task in self.project.all_tasks():
            if task.kind is TaskKind.REFERENCE:
                task.ref_snapshot = take_snapshot(self.reference_resolver, task.ref_project, now) if snapshot else None

    def refresh_reference(self, path: SectionPath, index: int) -> None:
        """参照行のスナップショットを、今の参照先の値に取り直す(スナップショットの方式のときだけ)。"""
        self.refresh_snapshot(self.tasks_in(path)[index])

    def refresh_snapshot(self, task: Task) -> bool:
        if task.kind is not TaskKind.REFERENCE or self.project.reference_mode is not ReferenceMode.SNAPSHOT:
            return False
        taken = take_snapshot(self.reference_resolver, task.ref_project, datetime.now())
        if taken is None:
            ui.notify(f"「{task.ref_project}」を読めないため、更新できません", type="warning")
            return False
        task.ref_snapshot = taken
        self.after_edit()
        ui.notify(f"「{task.name}」のスナップショットを更新しました")
        return True

    def open_reference(self, task_id: str) -> None:
        """参照先のプロジェクトへ切り替える。スナップショットが古ければ先に更新の確認を出す(更新すると未保存になるので、続けて保存の確認が出る)。"""
        task = self.project.task_map().get(task_id)
        if task is None or task.kind is not TaskKind.REFERENCE:
            return
        self.files = {p.stem: p for p in list_project_files(self.project_dir)}
        name = task.ref_project
        if name not in self.files:
            ui.notify(f"参照先のプロジェクトが見つかりません: {name}", type="warning")
            return
        ref = build_references(self.project, self.reference_resolver, datetime.now()).get(task_id)
        if ref is not None and ref.stale:

            def update_then_open() -> None:
                self.refresh_snapshot(task)
                self.go_to_reference(name)

            open_stale_reference_dialog(name, update_then_open, lambda: self.go_to_reference(name))
            return
        self.go_to_reference(name)

    def go_to_reference(self, name: str) -> None:
        """参照先を開く。開けたら、元のプロジェクトへ戻るリンクを出す。"""
        current = self.current_name()
        self.pending_origin = (current, name) if current else None
        self.request_open(name)

    def return_to_origin(self) -> None:
        """参照行から開いたプロジェクトから、元のプロジェクトへ戻る(未保存の編集があれば確認する)。"""
        if self.origin is not None:
            self.request_open(self.origin)

    def apply_templates(self, edit: TemplateEdit) -> None:
        """URL テンプレートの編集を反映する(削除分のリンクは URL に展開される)。保存はしない。"""
        apply_template_edit(self.project, edit)
        self.after_edit()

    def apply_categories(self, edit: CategoryEdit) -> None:
        """カテゴリの編集を反映する(削除したカテゴリのタスクは未定に戻る)。保存はしない。"""
        apply_category_edit(self.project, edit)
        self.after_edit()

    def apply_events(self, events: list[Event]) -> None:
        """イベントの編集を反映する。保存はしない(編集中の判定に入る)。"""
        self.project.events = events
        self.after_edit()

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
            self.reset_history()  # 別のファイルになる。名前の変更を、次の編集の 1 ステップにしない
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
        self.after_edit()

    def add_subsection(self, path: SectionPath) -> None:
        open_section_dialog(lambda name: self.save_subsection(path, name), title="サブセクションの追加")

    def save_subsection(self, path: SectionPath, name: str) -> None:
        """セクションの末尾にサブセクションを足す。親がない・root・3 階層目の親は何もしない。"""
        parent = arrange.section_at(self.project, path)
        if parent is None or len(path) >= MAX_SECTION_DEPTH:
            return
        parent.sections.append(Section(name, id=new_id(self.project.used_ids())))
        self.gantt.expand_section(path)
        self.after_edit()

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
            "ratio_limits": self.project.ratio_limits,
            "categories": self.project.categories,
            "sections": self.task_sections,
            "on_sections_change": self.set_task_sections,
            "reference_choices": sorted(
                p.stem for p in list_project_files(self.project_dir) if p.stem != self.current_name()
            ),  # プロジェクト参照の参照先(自分を除く)
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
            teams=self.project.teams,
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
            teams=self.project.teams,
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
            teams=self.project.teams,
            on_delete=lambda: self.delete_task(path, task_index),
            on_decompose=None  # まとめの子は、入れ子になるので分解できない
            if task.id in parent_map(self.project)
            else lambda close_edit: self.decompose_task(path, task_index, close_edit),
            **self.link_args(task),
        )

    def decompose_task(
        self, path: SectionPath, index: int, on_done: Callable[[], object] | None = None
    ) -> None:
        """分解ダイアログを開く。実行は `apply_decompose`。`on_done` は、分解に成功したあとに呼ぶ(開いたままの編集ダイアログを閉じる)。"""

        def apply(parts: list[Part], chain: bool, new_section: bool, params: ParamMode) -> None:
            self.apply_decompose(path, index, parts, chain, new_section, params)
            if on_done is not None:
                on_done()

        task = self.tasks_in(path)[index]
        settled = settle(self.project, task, self.holidays, datetime.now())
        open_decompose_dialog(task, can_make_section(path), apply, settled)

    def copy_task_below(self, path: SectionPath, index: int) -> None:
        """タスクを複製して、直後(まとめは子の後ろ)に置く。"""
        src = (path, index)
        self.move_task(src, arrange.after_task(self.project, src), True)

    def rename_task(self, path: SectionPath, index: int) -> None:
        """タスク名だけを変える(名前の入力ダイアログ)。"""
        task = self.tasks_in(path)[index]

        def apply(name: str) -> None:
            self.tasks_in(path)[index] = replace(task, name=name)
            self.after_edit()

        open_name_dialog(apply, task_name_error, title="タスク名の変更", initial=task.name, label="タスク名")

    def toggle_weeks(self, path: SectionPath, index: int) -> None:
        """担当を週ごとに分ける(今の担当を、開始から完了までの全部の週に入れる)/ 週ごとをやめる(第1週の担当に戻す)。"""
        task = self.tasks_in(path)[index]
        if task.weekly_crew:
            saved = replace(task, weekly_crew=[], assignees=list(task.weekly_crew[0]))
        elif task.kind is TaskKind.NORMAL and task.assignees:
            schedule = Schedule(self.project, self.holidays)
            start = effective_start(task, self.project, self.holidays, schedule)
            end = effective_end(task, self.project, self.holidays, schedule)
            weeks = week_count(start, end) if start is not None and end is not None and end > start else 1
            saved = replace(task, weekly_crew=[list(task.assignees) for _ in range(weeks)])
        else:
            ui.notify("担当者のいないタスクは、週ごとに分けられません")
            return
        self.tasks_in(path)[index] = saved
        self.after_edit()

    def edit_week_crew(self, path: SectionPath, index: int, week: int) -> None:
        """週ごとのタスクの、1 週ぶんの担当だけを直す(ガントチャートのチップのクリック)。"""
        task = self.tasks_in(path)[index]
        if not task.weekly_crew or week >= MAX_WEEKS:
            return
        shown = task.weekly_crew[min(week, len(task.weekly_crew) - 1)]  # 定義した週より後は、最後の週の担当が続いている

        def apply(crew: list[Assignee]) -> None:
            weeks = [list(w) for w in task.weekly_crew]
            while len(weeks) <= week:
                weeks.append(list(weeks[-1]))  # 間の週は、直前の週のコピーで足す
            weeks[week] = crew
            saved = replace(task, weekly_crew=weeks, assignees=union_assignees(weeks))
            self.tasks_in(path)[index] = saved
            self.after_edit()
            self.warn_overallocation(saved)

        period = ""
        schedule = Schedule(self.project, self.holidays)
        if (start := effective_start(task, self.project, self.holidays, schedule)) is not None:
            first = start.date() + timedelta(days=7 * week)
            period = f"{short_date(first)}〜{short_date(first + timedelta(days=6))}"
        open_week_crew_dialog(week + 1, shown, self.project.members, apply, period)

    def add_named_task(self, path: SectionPath, index: int, name: str) -> None:
        """名前だけの通常タスクを、セクション(root は ())の index 番目に作る(名前の入力行の確定)。"""
        arrange.insert_named_task(self.project, (path, index), name)
        self.after_edit()

    def add_named_child(self, path: SectionPath, index: int, name: str, parent_id: str) -> None:
        """名前だけの通常タスクを、まとめ(parent_id)の子として、index 番目に作る(名前の入力行の確定)。"""
        arrange.insert_named_child(self.project, (path, index), name, parent_id)
        self.after_edit()

    def add_named_summary(self, path: SectionPath, index: int, name: str) -> None:
        """まとめを、最初の子と一緒に、セクション(root は ())の index 番目に作る(名前の入力行の確定)。"""
        arrange.insert_named_summary(self.project, (path, index), name)
        self.after_edit()

    def add_named_section(self, parent: SectionPath, name: str) -> None:
        """名前だけのセクションを、親(最上位は ())の子の末尾に作る(名前の入力行の確定)。"""
        if parent:
            self.save_subsection(parent, name)
        else:
            self.save_section(name)

    def confirm_delete_task(self, path: SectionPath, index: int) -> None:
        """確認してから、タスクを削除する。"""
        task = self.tasks_in(path)[index]
        detail = f"子のタスク {len(task.children)} 件は、通常のタスクとして残ります" if task.kind is TaskKind.SUMMARY else None
        open_confirm_dialog(f"「{task.name}」を削除しますか?", lambda: self.delete_task(path, index), detail=detail)

    def copy_section(self, path: SectionPath) -> None:
        """セクションを、中のタスク・サブセクションごと複製して、直後に置く。"""
        section = arrange.section_at(self.project, path)
        assert section is not None
        name = section.name
        arrange.copy_section(self.project, path)
        self.gantt.remap_collapsed(path[:-1], path[-1] + 1, 1)  # 後ろの兄弟の番号が 1 つずれる
        self.after_edit()
        ui.notify(f"セクション「{name}」をコピーしました")

    def rename_section(self, path: SectionPath) -> None:
        """セクション名だけを変える(名前の入力ダイアログ)。"""
        section = arrange.section_at(self.project, path)
        assert section is not None

        def apply(name: str) -> None:
            section.name = name
            self.after_edit()

        open_name_dialog(apply, section_name_error, title="セクション名の変更", initial=section.name, label="セクション名")

    def confirm_delete_section(self, path: SectionPath) -> None:
        """確認してから、セクションを削除する。中のタスクは、セクションなしへ移す。"""
        section = arrange.section_at(self.project, path)
        assert section is not None
        count = len(section.all_tasks())
        detail = f"中のタスク {count} 件(サブセクションのも含む)は、セクションなしへ移します" if count else None
        open_confirm_dialog(f"セクション「{section.name}」を削除しますか?", lambda: self.delete_section(path), detail=detail)

    def delete_section(self, path: SectionPath) -> None:
        section = arrange.section_at(self.project, path)
        assert section is not None
        name = section.name
        moved = arrange.delete_section(self.project, path)
        self.gantt.remap_collapsed(path[:-1], path[-1], -1)
        self.after_edit()
        tail = f"(タスク {len(moved)} 件は、セクションなしへ移しました)" if moved else ""
        ui.notify(f"セクション「{name}」を削除しました{tail}")

    def move_section(self, src: SectionPath, dst: SectionPath) -> None:
        """セクションを、同じ親の dst の位置へ動かす。親が違う・変化なしなら何もしない(履歴も積まない)。"""
        if not src or not dst or src[:-1] != dst[:-1]:
            return
        if arrange.move_section(self.project, src, dst[-1]):
            self.gantt.reorder_collapsed(src[:-1], src[-1], dst[-1])
            self.after_edit()

    def apply_decompose(
        self,
        path: SectionPath,
        index: int,
        parts: list[Part],
        chain: bool,
        new_section: bool,
        params: ParamMode = ParamMode.INHERIT,
    ) -> None:
        """分解して再描画する(元に戻すの 1 ステップ)。不正なときは ValueError で、何も変えない。"""
        name = self.tasks_in(path)[index].name
        children = decompose(
            self.project,
            path,
            index,
            parts,
            chain=chain,
            new_section=new_section,
            holidays=self.holidays,
            params=params,
        )
        if path:
            self.gantt.expand_section(path)
        self.after_edit()
        ui.notify(f"「{name}」を {len(parts)} 件に分解しました")
        self.warn_overallocation(*children)  # 連結しない分解は、同じ担当の子が重なる

    def delete_task(self, path: SectionPath, task_index: int) -> None:
        """タスクを取り除いて再描画する。保存は自動では行わない(編集中の判定に入る)。"""
        removed = self.tasks_in(path).pop(task_index)
        drop_task_links(self.project, removed.id)
        self.after_edit()

    def bulk_edit(self, ids: list[str]) -> None:
        """選択中のタスクの一括編集ダイアログを開く。"""
        if ids:
            open_bulk_dialog(self.project, ids, self.holidays, lambda changes: self.apply_bulk(ids, changes))

    def apply_bulk(self, ids: list[str], changes: BulkChanges) -> None:
        """一括編集を適用する。置き換えで週ごとが解除されるときだけ、先に件数を出して確認する。"""
        result = apply_bulk_changes(self.project, ids, changes, self.holidays)
        if result.weeks_dropped:
            open_confirm_dialog(
                f"週ごとの担当が {result.weeks_dropped} 件のタスクで解除されます",
                lambda: self.commit_bulk(result),
                detail="置き換えると、週ごとの担当は 1 つの担当に戻ります",
                confirm_label="適用",
            )
            return
        self.commit_bulk(result)

    def commit_bulk(self, result: BulkResult) -> None:
        store(self.project, result)
        self.after_edit()  # 適用 1 回 = 元に戻す 1 ステップ
        ui.notify(f"{result.changed} 件を一括編集しました")
        if result.skipped:
            reasons = "・".join(f"{reason} {count}" for reason, count in result.skips.items())
            ui.notify(f"スキップ {result.skipped} 項目: {reasons}", type="warning")
        if result.review_needed:
            ui.notify(f"完了予定の見直しが要るタスクが {result.review_needed} 件あります", type="warning")
        if result.manual_switched:
            ui.notify(f"自動算出から手で指定に変わったタスク {result.manual_switched} 件(設定を変えても追従しません)", type="warning")
        if result.emptied:
            ui.notify(f"担当がいなくなったタスクが {result.emptied} 件あります", type="warning")
        if result.filled_weeks:
            ui.notify(f"担当のいなくなった週 {result.filled_weeks} 週を、隣の週の担当にしました", type="warning")
        self.warn_overallocation(*result.tasks.values(), limit=3)

    def extract_tasks(self, ids: list[str]) -> None:
        """選択中のタスクを子プロジェクトに切り出す(名前の入力ダイアログを開く)。"""
        if self.preview is not None or not ids:
            return
        if (reason := selection_error(self.project, ids)) is not None:
            ui.notify(reason, type="warning")
            return

        def validate(name: str) -> str | None:
            existing = {p.stem for p in self.project_dir.glob("*.json")}
            return extract_name_error(self.project, name, existing) or validate_name(name, self.project_dir, new=True)

        open_name_dialog(
            lambda name: self.apply_extract(ids, name),
            validate,
            title="子プロジェクトに切り出し",
            label="子プロジェクト名",
            submit="切り出す",
        )

    def apply_extract(self, ids: list[str], name: str) -> bool:
        """子を新規保存し、親を参照行に置き換える(元に戻す 1 ステップ)。失敗は False(親は変えない)。"""
        try:
            result = extract(self.project, ids, name)
            now = self.now()
            if self.project.reference_mode is ReferenceMode.SNAPSHOT:
                value = compute_reference(result.child, effective_holidays(result.child, self.base_holidays), now)
                reference = next(t for t in result.parent.all_tasks() if t.id == result.reference_id)
                reference.ref_snapshot = replace(value, taken_at=now)
            check_extraction(result)
            saved = save_project(result.child, self.project_dir, overwrite=False)  # 子を先に保存する。失敗したら親は変えない
        except (OSError, ValueError) as exc:
            ui.notify(f"切り出せませんでした: {exc}", type="negative")
            return False
        self.files[saved.stem] = saved
        self.file_select.set_options(sorted(self.files), value=self.current_name())  # 開いているプロジェクトの選択は変えない
        self.request_git_refresh()
        self.project = result.parent
        self.gantt.clear_selection()
        self.after_edit()
        notes = [
            f"先行 {result.dropped} 件を外しました" if result.dropped else "",
            "親を保存してください",
            "元に戻しても子のファイルは残ります",
        ]
        ui.notify(f"「{name.strip()}」に {result.moved} 件を切り出しました。" + "。".join(n for n in notes if n))
        return True

    def confirm_bulk_delete(self, ids: list[str]) -> None:
        if not ids:
            return
        info = delete_summary(self.project, ids)
        message = f"{info.total} 件のタスクを削除します(うちまとめ {info.summaries} 件・子 {info.children} 件)"
        detail = f"実行中の記録があるタスクが {info.running} 件あります" if info.running else None
        open_confirm_dialog(message, lambda: self.bulk_delete(ids), detail=detail)

    def bulk_delete(self, ids: list[str]) -> None:
        delete_tasks(self.project, ids)
        self.gantt.clear_selection()
        self.after_edit()

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
        self.after_edit()

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
        self.after_edit()
        self.warn_overallocation(task)

    def tasks_in(self, path: SectionPath) -> list[Task]:
        """セクション(パス)のタスク一覧。root は (): セクションに属さないタスク。"""
        return arrange.tasks_at(self.project, path)

    def stale_references(self) -> list[str]:
        """スナップショットが今の参照先と違う参照行の、参照先の名前(重複なし)。常に最新のときは空。"""
        refs = build_references(self.project, self.reference_resolver, datetime.now())
        tasks = self.project.task_map()
        return list(dict.fromkeys(tasks[tid].ref_project for tid, ref in refs.items() if ref.stale))

    def refresh_stale_snapshots(self, then: Callable[[], object] | None = None) -> None:
        """古いスナップショットをすべて今の参照先の値に取り直す。`then` があれば、その中で再描画する(なければ描き直す)。"""
        now = datetime.now()
        refs = build_references(self.project, self.reference_resolver, now)
        for task in self.project.all_tasks():
            if task.kind is TaskKind.REFERENCE and refs.get(task.id) is not None and refs[task.id].stale:
                taken = take_snapshot(self.reference_resolver, task.ref_project, now)
                if taken is not None:
                    task.ref_snapshot = taken
        if then is None:
            self.after_edit()
        else:
            then()

    def save_task(
        self, path: SectionPath, task_index: int | None, task: Task
    ) -> None:
        """タスクを保存する。スナップショットが古い参照先があるときは、先に確認する(キャンセルなら保存しない)。"""
        if stale := self.stale_references():
            open_stale_snapshot_dialog(
                stale,
                "保存",
                lambda: self.refresh_stale_snapshots(lambda: self.apply_task(path, task_index, task)),
                lambda: self.apply_task(path, task_index, task),
            )
            return
        self.apply_task(path, task_index, task)

    def apply_task(self, path: SectionPath, task_index: int | None, task: Task) -> None:
        tasks = self.tasks_in(path)
        if task_index is None:
            if task.id in self.project.used_ids():
                task.id = new_id(self.project.used_ids())  # 他のタスク・メンバー・セクションと同じ id にならないように
            tasks.append(task)
        else:
            tasks[task_index] = task
        if task_index is None and path:
            self.gantt.expand_section(path)  # 追加したタスクが、親も含めて見えるように
        self.after_edit()
        self.warn_overallocation(task)

    def warn_overallocation(self, *tasks: Task, limit: int | None = None) -> None:
        """保存したタスクが担当者の割り当て合計の超過に関わるなら、担当者ごとに通知する(保存は妨げない)。
        複数のタスクを渡したときは、担当者ごとに 1 回だけ出す。limit があれば、その人数だけ通知し、残りは件数にまとめる。"""
        if not any(task.assignees for task in tasks):
            return
        overloads = overallocations(self.project, self.holidays)
        mine = [o for task in tasks for o in clip_overloads(task, self.project, self.holidays, overloads)]
        names = dict.fromkeys(name for task in tasks for name in task.assignee_names)
        notified = 0
        for name in names:
            peaks = [o.total for o in mine if o.member == name]
            if not peaks:
                continue
            if limit is not None and notified >= limit:
                notified += 1
                continue
            notified += 1
            ui.notify(
                f"{name} 最大{round(max(peaks) * 100)}%になる期間があります",
                type="warning",
            )
        if limit is not None and notified > limit:
            ui.notify(f"ほか {notified - limit} 人も割り当てが 100% を超える期間があります", type="warning")

    @property
    def holidays(self) -> dict[date, str]:
        """祝日に、休みにしたイベントの期間を足した辞書。日程の計算・集計はこれを使う。"""
        return self._effective_holidays.get(self.project, self.base_holidays)

    @holidays.setter
    def holidays(self, value: dict[date, str]) -> None:
        self.base_holidays = value

    async def refresh_holidays(self, quiet: bool = False) -> None:
        """祝日を取得してチャートに反映する。失敗しても画面は変えず通知だけ出す。"""
        try:
            self.base_holidays = await download_holidays(self.base_dir, self.transport)
        except (httpx.HTTPError, ValueError, OSError):  # OSErrorはキャッシュの書き込み失敗
            ui.notify("祝日データを取得できませんでした", type="warning")
            return
        self.gantt.set_holidays(self.base_holidays)
        if not quiet:
            ui.notify("祝日データを更新しました")

    async def first_fetch(self) -> None:
        await self.refresh_holidays(quiet=True)

    def build(self) -> None:
        ui.add_head_html(f'<script src="{HTML_TO_IMAGE_URL}"></script>')
        ui.add_css(HEADER_CSS)
        ui.add_css(BODY_CSS)
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
        self.apply_select_popup()
        if self.theme == "custom":
            self.run_js(theme_js(self.custom_theme))
        if self.today_color is not None:
            self.run_js(today_color_js(self.today_color))
        ui.keyboard(on_key=self.on_plain_key)  # 入力欄・ボタンにフォーカスがあるときは、受けない
        ui.keyboard(on_key=self.on_modified_key, ignore=[])  # Ctrl/Cmd 付きだけは、入力欄でも受ける(Ctrl/Cmd+Z を除く)
        ui.keyboard(on_key=self.on_undo_key, ignore=["input", "select", "textarea"])  # Ctrl/Cmd+Z: 入力欄では文字の取り消し
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
                    MenuItem("PlantUML を取り込む", "upload_file", self.request_import_plantuml, "file-import-plantuml"),
                    *(  # ファイル選択はネイティブのみなので、Web では項目を出さない
                        [MenuItem("CSV を取り込む", "table_view", self.request_import_csv, "file-import-csv")]
                        if self.exporter.available
                        else []
                    ),
                    *(
                        [MenuItem("設定を取り込む", "settings_backup_restore", self.request_import_settings, "file-import-settings")]
                        if self.exporter.available
                        else []
                    ),
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
                    MenuItem("TSV として書き出す", "download", self.export_tsv, "export-tsv"),
                    *(
                        [MenuItem("設定を書き出す", "save_alt", self.export_settings, "export-settings")]
                        if self.exporter.available
                        else []
                    ),
                ],
            )
            self.header_menu(
                "Git",
                "menu-git",
                [
                    MenuItem("コミット…", "commit", self.open_git_commit, "git-commit", label_for("git_commit")),
                    MenuItem("プッシュ", "cloud_upload", self.start_git_push, "git-push", label_for("git_push")),
                    MenuItem("プル", "cloud_download", self.start_git_pull, "git-pull", label_for("git_pull")),
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
    GIT_MENU = (("commit", "git-commit"), ("push", "git-push"), ("pull", "git-pull"), ("refresh", "git-refresh"))

    def git_reason(self, action: str) -> str | None:
        """Git メニューの操作が、今できない理由(できるときは None)。`action`は commit・push・pull・push_after_commit・refresh。
        `push_after_commit`は、コミットのあとにプッシュするとき(今は未プッシュが 0 でもよい)。"""
        state = self.git_state
        if action == "refresh":
            return None  # 作業ツリーでなくても読み直せる(外で git init したあとの手段)
        if state.kind is not GitKind.OK:
            return self.NOT_WORK_TREE
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
        if action == "pull":
            if state.error is not None:
                return "git の状態を読めていません"
            if state.upstream is None:
                return "上流がありません"
            if state.ahead is None:
                return "上流が見つかりません"
            if state.dirty:
                return "未コミットの変更があります。先にコミットしてください"
            if self.is_dirty():
                return "保存されていない編集があります。先に保存・コミットしてください"
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

    def start_git_pull(self) -> None:
        """プルを始める(メニューとショートカットの入口)。できないときは、理由を通知する。"""
        reason = self.git_reason("pull")
        if reason is not None:
            ui.notify(reason, type="warning")
            return
        self.later(self.run_pull)

    async def run_pull(self) -> None:
        """fetch して、最新・早送り・マージのどれかを行う。終わったら、開いているプロジェクトを読み直す。"""
        if self.git_busy:
            return
        self.set_git_busy(True)
        reload_needed = False
        try:
            ops = self.pull_ops
            plan = await run.io_bound(ops.prepare, self.project_dir)
            if plan is None:  # アプリの終了中
                return
            if isinstance(plan, GitResult):
                ui.notify(plan.message, type="negative")
                return
            if plan.kind is PullKind.UP_TO_DATE:
                ui.notify("最新です")
                return
            if self.is_dirty():  # 取得している間に編集された。読み直しで捨てないよう、始めない
                ui.notify("保存されていない編集があるため、取り込みを中止しました。先に保存・コミットしてください", type="warning")
                return
            if plan.kind is PullKind.FAST_FORWARD:
                done = await run.io_bound(ops.fast_forward, self.project_dir)
                if done is None:
                    return
                ui.notify(done.message, type="positive" if done.ok else "negative")
                reload_needed = done.ok
                return
            reload_needed = await self.pull_merge(plan.upstream)
        finally:
            self.set_git_busy(False)
            if reload_needed:
                self.reload_after_pull()
            self.request_git_refresh()

    async def pull_merge(self, upstream: str) -> bool:
        """マージを始め、ファイルごとに統合する(衝突は選ばせる)。取り込めたら True。失敗・中止は元に戻す。"""
        ops = self.pull_ops
        session = await run.io_bound(ops.start_merge, self.project_dir, upstream)
        if session is None:
            return False
        if isinstance(session, GitResult):
            ui.notify(session.message, type="negative")
            return False
        merged: dict[str, str] = {}
        notes: list[str] = []
        picked = 0
        try:
            for file in session.files:
                outcome = merge_files(file.name, file.base, file.ours, file.theirs)
                if outcome.conflicts:
                    choices = await self.ask_conflicts(file.name, outcome.conflicts)
                    if choices is None:
                        await self.abort_pull()
                        return False
                    picked += len(outcome.conflicts)
                    outcome = merge_files(file.name, file.base, file.ours, file.theirs, choices)
                merged[file.name] = outcome.text
                notes += outcome.notes
        except Exception as exc:  # ValueError(読めない・検証を通らない)以外でも、マージを途中のまま残さない
            await self.abort_pull(f"統合できませんでした: {exc}")
            return False
        done = await run.io_bound(ops.finish_merge, self.project_dir, session, merged)
        if done is None:
            return False
        if not done.ok:
            ui.notify(f"取り込めませんでした: {done.message}", type="negative")
            return False
        message = "取り込みました" + (f"(衝突 {picked} 件を選択)" if picked else "")
        ui.notify(message, type="positive")
        for note in notes:
            ui.notify(note, type="warning")
        return True

    async def abort_pull(self, reason: str | None = None) -> None:
        """マージを中止して元に戻す。戻せなかったときは、そう通知する(`reason`があれば、中止の理由として出す)。"""
        done = await run.io_bound(self.pull_ops.abort, self.project_dir)
        if done is None:  # アプリの終了中
            return
        if not done.ok:
            ui.notify(f"取り込みを中止できませんでした: {done.message}", type="negative")
        elif reason is None:
            ui.notify("取り込みを中止しました")
        else:
            ui.notify(reason, type="negative")

    async def ask_conflicts(self, name: str, conflicts):
        """衝突ダイアログを開き、選択(中止なら None)を待つ。"""
        future = asyncio.get_running_loop().create_future()
        open_merge_conflict_dialog(
            name,
            conflicts,
            lambda choices: future.done() or future.set_result(choices),
            lambda: future.done() or future.set_result(None),
        )
        return await future

    def reload_after_pull(self) -> None:
        """プルで書き換わったかもしれないので、開いているプロジェクトを読み直す(未保存の編集はなかった)。"""
        self.files = {p.stem: p for p in list_project_files(self.project_dir)}
        self.file_select.set_options(sorted(self.files), value=self.current_name())
        name = self.current_name()
        if self.is_dirty():  # 取り込み中に編集された。読み直すと捨ててしまう
            ui.notify("取り込み中に編集があったため、画面は読み直していません。保存すると取り込んだ内容を上書きします", type="warning")
        elif name is not None and name in self.files:
            self.open_project(name)

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
        if self.origin is not None and self.origin in self.files:  # 参照行から開いたときだけ
            ui.button(f"{self.origin}に戻る", icon="arrow_back", on_click=self.return_to_origin).props(
                "flat dense no-caps size=sm"
            ).tooltip("参照した元のプロジェクトに戻る").mark("back-to-origin")

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
                ui.separator().mark("theme-separator")
                self.menu_entry(CUSTOM_COLORS_LABEL, "tune", self.open_theme_dialog, "theme-custom-settings")
                self.menu_entry(TODAY_COLOR_LABEL, "event", self.open_today_color_dialog, "theme-today-color")

    def build_help_dialog(self) -> ui.dialog:
        """ショートカットヘルプのダイアログ(ヘルプメニューから開く)。"""
        with ui.dialog() as dialog, ui.card():
            ui.label("キー操作").classes("text-h6")
            for key, desc in help_entries():
                ui.label(f"{key}: {desc}")
            ui.label("Ctrl/Cmd+クリック: タスクを選択に加える・外す(名前の欄。まとめは子も)").mark("help-bulk-click")
            ui.label("Shift+クリック: 最後に選んだ行との間を選ぶ。ESC か選択バーの解除で解除").mark("help-bulk-range")
            ui.button("閉じる", on_click=dialog.close)
        return dialog
