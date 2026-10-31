"""ガントチャートの描画(NiceGUI要素とCSS)。"""

import html
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta

from nicegui import Client, context, ui
from nicegui.events import ValueChangeEventArguments

from projectapp import arrange
from projectapp.avatar import avatar
from projectapp.browser import open_url as default_open_url
from projectapp.bulk_select import BulkSelection
from projectapp.arrange import Position, section_key
from projectapp.calendar import DayKind, day_kind, member_notes
from projectapp.forms import section_name_error, task_name_error
from projectapp.events import EffectiveHolidays, assign_lanes, cell_colors, color_hex, column_span
from projectapp.categories import by_id, chip_text
from projectapp.config import (
    DEFAULT_NAME_WIDTH_PX,
    MAX_NAME_WIDTH_PX,
    MIN_NAME_WIDTH_PX,
    parse_name_width,
)
from projectapp.decompose import decompose_block_reason
from projectapp.filtering import TaskFilter, hidden_by_summary, matches, section_has_match, visible_task_indexes
from projectapp.gantt_drag import CHART_DRAG_CSS, CHART_DRAG_JS, NAME_RESIZE_CSS, RESIZE_EDGE_PX
from projectapp.links import Bar, RowSlot, link_points, path_data, row_centers, row_slots, total_height
from projectapp.periodfield import (
    PERIOD_SEPARATOR,
    add_range_picker,
    check_column_count,
    format_period,
    normalize_period,
    split_period,
    validate_period,
)
from projectapp.pace import warning_pace
from projectapp.models import ID_KEY, MAX_SECTION_DEPTH, URL_KEY, Assignee, Category, Event, Priority, Project, ReferenceMode, ReferenceValue, Section, SectionPath, Status, Task, TaskKind, TaskUrl
from projectapp.reference import Reference
from projectapp.scope import read_scope, scope_options, scope_value
from projectapp.teams import team_scope, teams_with_members
from projectapp.selection import CheckState, check_state, task_ids_of, toggled
from projectapp.urls import resolve
from projectapp.summary import children_of, parent_map, summary_progress, summary_status
from projectapp.timeline import (
    in_range,
    Band,
    Column,
    Overload,
    ProgressState,
    Scale,
    Schedule,
    bar_span,
    build_columns,
    clip_overloads,
    current_progress,
    deadline_position,
    effective_start,
    expected_progress,
    interval_span,
    is_overdue,
    month_bands,
    overallocations,
    progress_state,
    today_position,
    year_bands,
)

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
CHECKPOINT_MARKER_PX = 20  # チェックポイントの ◆ の大きさ(締切の小さな ◆ より大きい)
WORKMARK_HEIGHT_PX = 4  # 担当者の稼働日の上書きの印の高さ
DEADLINE_COLOR = "#f57c00"  # 赤は予定超過の背景と競合するので使わない
TODAY_COLOR = "#e53935"  # 今日の線。ダークでは明るい赤に替える
TODAY_DARK_COLOR = "#ff5252"
TODAY_COLOR_VAR = "var(--today)"
TODAY_LINE_WIDTH_PX = 2
TODAY_CSS = f":root {{ --today: {TODAY_COLOR}; }}\nbody.body--dark {{ --today: {TODAY_DARK_COLOR}; }}"
WARNING_COLOR = "#fdd835"  # 警告のタスクの行・名前の欄の背景(薄く重ねる)。設定で変えられる(--warning)
WARNING_BACKGROUND = "color-mix(in srgb, var(--warning) 22%, transparent)"
WARNING_CSS = f":root {{ --warning: {WARNING_COLOR}; }}"
OVERLOAD_STRIPES = (  # 割り当て合計が100%を超える期間の縞。タスクの色に依存しないよう白と黒の半透明を重ねる
    "repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 4px, rgba(0,0,0,0.35) 4px 8px)"
)
MIN_BAR_PX = 4  # 幅0や終了が開始より前のタスクも、見える細い棒で出す
PLANNED_OPACITY = 0.4  # 実績を重ねるため、予定の棒は半透明にする(背景の色だけ。縞は薄くしない)
BAR_TOP_PX = 6
BAR_HEIGHT_PX = ROW_HEIGHT_PX - 12
ACTUAL_HEIGHT_PX = BAR_HEIGHT_PX // 2  # 実績の棒は、予定の棒の下半分
ACTUAL_TOP_PX = BAR_TOP_PX + BAR_HEIGHT_PX - ACTUAL_HEIGHT_PX
SUMMARY_BAND_HEIGHT_PX = 9  # まとめの細い帯(通常の棒は BAR_HEIGHT_PX)
SUMMARY_BAND_TOP_PX = (ROW_HEIGHT_PX - SUMMARY_BAND_HEIGHT_PX) // 2 - 1
SUMMARY_TIP_PX = 6  # 帯の両端の三角の半幅
SUMMARY_INDENT_PX = 12  # まとめの子の名前の欄の字下げ
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
EVENT_ROW_HEIGHT_PX = 16
EVENT_CSS = (
    ".event-fill { position: absolute; inset: 0; background: var(--ev); opacity: 0.45 }\n"
    ".event-tint { background: var(--ev); opacity: 0.18 }\n"
    "body.body--dark .event-fill { opacity: 0.35 }\n"
    "body.body--dark .event-tint { opacity: 0.14 }"
)


@dataclass(frozen=True)
class ViewOptions:
    """ガントチャートの表示の設定。既定値が、通常の画面と同じ描画になる。"""

    period: tuple[date, date] | None = None  # 表示する期間 [開始日, 終了日]。None は、基準日とバーから決める
    scale: Scale | None = None  # None は、ツールバーのスケール
    show_chips: bool = True  # 名前欄のチップと進捗
    show_alerts: bool = True  # 予定超過の赤みと、割り当て超過の縞
    show_events: bool = True  # イベントの帯とセルの色
    show_today: bool = True  # 今日の赤い縦線
    read_only: bool = False  # 編集の部品・クリック・ドラッグをなくす
    selectable: bool = False  # 行と見出しの先頭に、出力のチェックボックスを出す(読み取り専用のときだけ)
    excluded: frozenset[str] = frozenset()  # チェックを外したタスクの id。薄く描く
    hide_excluded: bool = False  # 外したタスクを描かない(画像の書き出し用。チェックボックスも出さない)
    on_select: Callable[[list[str], bool], object] | None = None  # チェックの変更(対象のタスク id, 出力するか)


# 名前の右のチップ。名前だけが縮み、チップは縮めない
CODE_CHIP_STYLE = (
    "flex: none; max-width: 56px; padding: 0 6px; font-size: 10px; line-height: 16px;"
    " border: 1px solid rgba(128, 128, 128, 0.6); border-radius: 8px"
)
# 割り当て超過の縞の上でも頭文字が読めるように、チップの文字に黒い縁を付け、チップを縞より前に出す
WEEK_CHIP_TEXT_SHADOW = "0 0 2px #000, 0 0 2px #000, 0 0 3px #000"
HOVER_NAMES_PER_LINE = 3  # 週ごとの担当のマウスオーバーで、1 行に並べる人数
MAX_ASSIGNEE_CHIPS = 3  # これを超える担当者は、「+n」のチップ 1 つにまとめる
WEEK_CHIP_HEIGHT_PX = 12  # 棒の上の週ごとのチップの高さ
WEEK_CHIP_ICON_PX = 10  # 週ごとのチップの中の、アイコン画像の大きさ
MIN_WEEK_CHIP_TEXT_PX = 24  # 週ごとのチップに頭文字を出す最小の幅(これより狭いときは区切りだけ)
ASSIGNEE_CHIP_STYLE = (
    "flex: none; width: 16px; height: 16px; line-height: 16px; text-align: center;"
    " font-size: 10px; border-radius: 50%; background: rgba(128, 128, 128, 0.3)"
)
PROGRESS_TEXT_STYLE = "flex: none; font-size: 10px"
REFERENCE_CHIP_STYLE = (  # 文字入りのチップ(担当者の丸いチップは文字が収まらない)。折り返さず、名前のほうを縮める
    "flex: none; padding: 0 6px; font-size: 10px; line-height: 16px; white-space: nowrap;"
    " border-radius: 8px; background: rgba(128, 128, 128, 0.3)"
)
REFERENCE_MARK = "📅 "  # 参照行の名前の頭に付ける目印(表示だけ。名前には含めない)
REFERENCE_CSS = ".ref-link { cursor: pointer; } .ref-link:hover { text-decoration: underline; }"
OVERDUE_COLOR_SOLID = "rgba(239, 83, 80, 0.45)"  # 遅延のチップの背景(行の赤みより濃く)
RED_BAR_COLOR = "#ef5350"  # 遅延のある参照先の帯の色
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
LINK_CSS = """
.gantt-links { --link-color: #757575; }
body.body--dark .gantt-links { --link-color: #bdbdbd; }
"""
CONTEXT_MENU_CSS = """
.app-context-menu .q-item { min-height: 26px; padding: 2px 12px; font-size: 12px; }
.app-context-menu .q-separator { margin: 2px 0; }
"""
LINK_STYLE = "stroke: var(--link-color); stroke-width: 1.5; fill: none"
LINK_HEAD = (
    '<defs><marker id="link-head" markerWidth="6" markerHeight="6" refX="6" refY="3"'
    ' orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L6,3 L0,6 z"'
    ' style="fill: var(--link-color)"/></marker></defs>'
)
GRID_BORDER = "1px solid rgba(128, 128, 128, 0.3)"  # 格子線。両テーマで見える半透明の灰色
ADD_ROW_HEIGHT_PX = 24  # 追加行は通常の行より細くする
ARROW_EXPANDED = "expand_more"
ARROW_COLLAPSED = "chevron_right"
ROW_STYLE = f"height: {ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
ADD_ROW_STYLE = f"height: {ADD_ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
# IME の変換確定の Enter は無視する。Safari 系は確定時に isComposing が偽でも keyCode が 229 になる
SEARCH_ENTER_JS = "(e) => { if (!e.isComposing && e.keyCode !== 229) emit(e.target.value); }"
# ダブルクリックで入力行を出す(Shift ならセクション用、Ctrl/Cmd ならまとめ用。押したかを渡す)。
# ボタン・リンク・入力欄と、印の付いた要素(まとめの名前)の上では出さない
QUICK_ADD_JS = (
    "(e) => { if (!e.target.closest('button, a, input, [data-no-quick-add]'))"
    " emit({shift: e.shiftKey, ctrl: e.ctrlKey || e.metaKey}); }"
)
# Cmd/Ctrl クリックと Shift クリックだけを選択として送る。ボタン・リンク・入力欄と、印の付いた要素の上は除く
SELECT_CLICK_JS = (
    "(e) => { if (!(e.shiftKey || e.ctrlKey || e.metaKey)) return;"
    " if (e.target.closest('button, a, input, [data-no-select]')) return;"
    " e.preventDefault(); emit({shift: e.shiftKey, ctrl: e.ctrlKey || e.metaKey}); }"
)
# 修飾キーつきのクリックは、まとめ・参照行の名前のクリック(開閉・参照先を開く)で横取りせず、選択へ回す
PLAIN_CLICK_JS = "(e) => { if (e.shiftKey || e.ctrlKey || e.metaKey) return; e.stopPropagation(); emit(); }"
BULK_CSS = """
.task-selected { outline: 2px solid var(--q-primary); outline-offset: -2px; }
.task-selected > .gantt-sticky {
  box-shadow: inset 4px 0 0 var(--q-primary), inset 0 0 0 999px color-mix(in srgb, var(--q-primary) 18%, transparent);
}
"""
SCROLLBAR_ROOM_PX = 16  # 横スクロールバーの分の余白。WebKit は高さ auto にバーの厚みを含めない
# チャートの枠は縦横ともここでスクロールする。高さの上限は、画面の高さから、上のヘッダー
# (1 行のメニュー・ツールバー・ページの余白)の分を引いた値(固定の見積もり。実機で合わせる)
CHART_TOP_OFFSET_PX = 170
CHART_MAX_HEIGHT = f"calc(100vh - {CHART_TOP_OFFSET_PX}px)"
# 固定する要素の重なり。見出し > タスク名の列 > 棒・縞・格子線。見出しの中では左端の空白が帯より手前
STICKY_Z_SPACER, STICKY_Z_NAME, STICKY_Z_HEADER = 1, 2, 3
# 固定した要素の下を棒や縞が通るので、不透明な背景が要る(ページの背景色に合わせる)
STICKY_CSS = """
.gantt-sticky { background-color: var(--app-bg, #fff); }
body.body--dark .gantt-sticky { background-color: var(--app-bg, var(--q-dark-page, #121212)); }
body.body--dark [data-chart-scroll] { color-scheme: dark; background-color: var(--app-bg, var(--q-dark-page, #121212)); }
body.body--dark [data-chart-scroll]::-webkit-scrollbar { width: 12px; height: 12px; }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-track { background: var(--app-bg, var(--q-dark-page, #121212)); }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-thumb { background: #555; border-radius: 6px; }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-corner { background: var(--app-bg, var(--q-dark-page, #121212)); }
"""
# 絞り込みの変更時に、チャートの枠とページの両方を先頭へ戻す
SCROLL_TO_LEFT_JS = "document.querySelector('[data-chart-scroll]')?.scrollTo({left: 0})"
SCROLL_RESET_JS = (
    "document.querySelector('[data-chart-scroll]')?.scrollTo({top: 0, left: 0});"
    " window.scrollTo({top: 0})"
)


def today_scroll_js(x: float, name_width: int) -> str:
    """今日の線が、名前の欄を除いたチャート領域の左から 1/4 の位置に来るよう、横にスクロールする。"""
    return (
        "requestAnimationFrame(() => { const el = document.querySelector('[data-chart-scroll]');"
        f" if (el) el.scrollTo({{left: Math.max(0, {x:.1f} - (el.clientWidth - {name_width}) / 4)}}) }})"
    )


# 非表示(display: none)にすると、枠のスクロール位置が失われる。要素の更新(隠す)は run_javascript より先にブラウザへ届き、
# 隠す直前には位置を読めないので、スクロールのたびに覚える(見えているときだけ。隠れて 0 を返すときは上書きしない)。
# 出したあとの次のフレームで戻す
TRACK_SCROLL_JS = (
    "(e) => { const el = e.target; if (el.offsetHeight > 0)"
    " { el.dataset.top = el.scrollTop; el.dataset.left = el.scrollLeft; } }"
)
SHOW_CHART_JS = (
    "requestAnimationFrame(() => { const el = document.querySelector('[data-chart-scroll]');"
    " if (el) el.scrollTo({top: Number(el.dataset.top || 0), left: Number(el.dataset.left || 0)}); })"
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


def held_keys(keys: object) -> tuple[bool, bool]:
    """ダブルクリックで渡された、押していたキー({shift, ctrl})。渡されなければ、どちらも押していない。"""
    held = keys if isinstance(keys, dict) else {}
    return bool(held.get("shift")), bool(held.get("ctrl"))


def reference_open_hint(task: Task) -> str:
    """参照行のマウスオーバーに添える、クリックで参照先のプロジェクトが表示される案内。"""
    return f"クリックすると「{task.ref_project}」プロジェクトを開く"


def planned_background(color: str) -> str:
    """予定の棒の背景。要素の opacity ではなく背景だけを半透明にし、中の縞は不透明のまま残す。"""
    return f"color-mix(in srgb, {color} {PLANNED_OPACITY * 100:g}%, transparent)"


def week_chip_text(names: list[str], width_px: float, scale: Scale) -> str:
    """棒の上の週ごとのチップの文字。日次・週次で幅が足りるときだけ頭文字を出す(4 人目以降は +n)。"""
    if scale is Scale.MONTH or width_px < MIN_WEEK_CHIP_TEXT_PX or not names:
        return ""
    rest = len(names) - MAX_ASSIGNEE_CHIPS
    return "".join(name[0] for name in names[:MAX_ASSIGNEE_CHIPS]) + (f"+{rest}" if rest > 0 else "")


def crew_text(crew: list[Assignee], per_line: int = HOVER_NAMES_PER_LINE) -> str:
    """担当者と割り当て率(マウスオーバー用)。per_line 人ごとに改行し、2 行目からは全角空白で字下げする。"""
    names = [f"{a.name} {round(a.allocation * 100)}%" for a in crew]
    return "\n　".join("、".join(names[i : i + per_line]) for i in range(0, len(names), per_line))


def short_date(day: date) -> str:
    """ヒント用の短い日付(9/21)。"""
    return f"{day.month}/{day.day}"


SHIFT_HINT = "Shift: 週ごとの担当"
SHIFT_TOOLTIP_CSS = """
.tip-plain, .tip-detail { white-space: pre-line; }
.tip-detail { display: none; }
body.shift-held .tip-plain { display: none; }
body.shift-held .tip-detail { display: block; }
"""
# Shift を押している間だけ body に shift-held を付ける(ウィンドウを離れたとき・マウスの動きでも合わせ直す)
SHIFT_TRACK_JS = """
(() => {
  const set = (on) => document.body && document.body.classList.toggle('shift-held', on);
  document.addEventListener('keydown', (e) => { if (e.key === 'Shift') set(true); });
  document.addEventListener('keyup', (e) => { if (e.key === 'Shift') set(false); });
  document.addEventListener('mousemove', (e) => set(e.shiftKey), { passive: true });
  window.addEventListener('blur', () => set(false));
})();
"""


def shift_tooltip(target: ui.element, plain: str, detail: str) -> None:
    """マウスオーバーのヒント。detail があれば、Shift を押している間だけ detail に切り替える(普通は plain と、操作の案内)。"""
    if not detail:
        target.tooltip(plain)
        return
    with ui.tooltip().props(f'target="#{target.html_id}"'):
        ui.label(f"{plain}\n{SHIFT_HINT}").classes("tip-plain")
        ui.label(detail).classes("tip-detail")


def week_summary(task: Task, start: date | None = None) -> str:
    """週ごとの担当の説明(マウスオーバー用)。週ごとに分けないタスクは空。start(実効の開始の日)を渡すと、週の期間を添える。"""
    lines = []
    for number, week in enumerate(task.weekly_crew, start=1):
        period = ""
        if start is not None:
            first = start + timedelta(days=7 * (number - 1))
            period = f" {short_date(first)}〜{short_date(first + timedelta(days=6))}"
        lines.append(f"第{number}週{period}: {crew_text(week)}")
    return "\n".join(lines)


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
    header: ui.element | None = None  # 見出しの行(親が折りたたまれると隠す)
    rows: list[ui.element] = field(default_factory=list)  # このセクション自身のタスクの行
    children: list[SectionPath] = field(default_factory=list)  # 描いたサブセクション


@dataclass
class SummaryView:
    """描画したまとめの、折りたたみで切り替える部品。描き直すたびに作り直す。"""

    arrow: ui.button | None = None  # 開閉の矢印(読み取り専用では出さない)
    count: ui.element | None = None  # 折りたたみ中に出す子の件数


@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[SectionPath], object]
    add_top_task: Callable[[], object]
    edit_task: Callable[[SectionPath, int], object]  # セクションのパス(root は ()), タスク番号
    move_task: Callable[[Position, Position, bool], object]  # 元, 挿入先, コピーか
    shift_task: Callable[[SectionPath, int, int], object]  # セクションのパス(root は ()), タスク番号, 日数
    set_name_width: Callable[[int], object]  # 名前の欄の幅(px)。範囲に収めた整数。保存は受け取り側
    add_subsection: Callable[[SectionPath], object] = lambda path: None  # サブセクションの追加(親のセクションのパス)
    # 右クリックのメニューの操作(セクションのパス, タスク番号)
    decompose_task: Callable[[SectionPath, int], object] = lambda path, ti: None
    # 選択中の一括操作(見えている選択済みのタスク id。描画順)
    bulk_edit: Callable[[list[str]], object] = lambda ids: None
    bulk_delete: Callable[[list[str]], object] = lambda ids: None
    extract_tasks: Callable[[list[str]], object] = lambda ids: None
    copy_task: Callable[[SectionPath, int], object] = lambda path, ti: None
    rename_task: Callable[[SectionPath, int], object] = lambda path, ti: None
    delete_task: Callable[[SectionPath, int], object] = lambda path, ti: None
    # セクションの見出しの右クリックのメニューの操作(セクションのパス)
    copy_section: Callable[[SectionPath], object] = lambda path: None
    rename_section: Callable[[SectionPath], object] = lambda path: None
    delete_section: Callable[[SectionPath], object] = lambda path: None
    move_section: Callable[[SectionPath, SectionPath], object] = lambda src, dst: None  # 元, 落とした先の見出し(同じ親)
    # 名前の入力行で確定した、名前だけのタスクの追加(セクションのパス, 挿入位置, 名前)
    add_named_task: Callable[[SectionPath, int, str], object] = lambda path, index, name: None
    # 同じく、まとめの子として作る追加(セクションのパス, 挿入位置, 名前, まとめのタスク id)
    add_named_child: Callable[[SectionPath, int, str, str], object] = lambda path, index, name, parent: None
    # 同じく、まとめの追加(セクションのパス, 挿入位置, 名前)。最初の子も一緒に作る
    add_named_summary: Callable[[SectionPath, int, str], object] = lambda path, index, name: None
    # 名前の入力行で確定した、名前だけのセクションの追加(親のセクションのパス。最上位は (), 名前)
    add_named_section: Callable[[SectionPath, str], object] = lambda parent, name: None
    toggle_weeks: Callable[[SectionPath, int], object] = lambda path, ti: None  # 週ごとに分ける / やめる
    edit_week_crew: Callable[[SectionPath, int, int], object] = lambda path, ti, week: None  # 週ごとの担当の編集(0 始まり)
    open_reference: Callable[[str], object] = lambda task_id: None  # プロジェクト参照の行のクリック(タスクの id)
    refresh_reference: Callable[[SectionPath, int], object] = lambda path, ti: None  # スナップショットの更新


class GanttChart:
    def __init__(
        self,
        project: Project,
        holidays: dict[date, str],
        actions: GanttActions,
        now: Callable[[], datetime] = datetime.now,
        name_width: int = DEFAULT_NAME_WIDTH_PX,
        open_url: Callable[[str], object] = default_open_url,
        references: Callable[[], dict[str, Reference]] = lambda: {},
    ) -> None:
        self.project = project
        self.references_of = references
        self.refs: dict[str, Reference] = {}  # 参照行の id → 参照。描画のたびに取り直す
        self.open_url = open_url
        self.base_holidays = holidays  # 祝日だけ。背景と稼働日のホバーは、これを使う
        self._effective = EffectiveHolidays()
        self.actions = actions
        self.now = now
        self.name_width = name_width  # 名前の欄の幅(px)。ドラッグで変わり、保存は呼び出し側
        self.overloads: list[Overload] = []
        self.category_lookup: dict[str, Category] = {}
        self.icon_lookup: dict[str, str] = {}
        self.schedule = Schedule(project, self.holidays)
        self.links_html: ui.html | None = None
        self.link_layout: tuple[list[Column], int] | None = None
        self.scale = Scale.DAY
        self.options = ViewOptions()
        self.period: tuple[date, date] | None = None  # メインの表示期間。None は自動(基準日とバーから決める)。保存しない
        self.period_input: ui.input | None = None
        self.period_error: ui.label | None = None
        self.syncing_period = False  # 欄を書き換えるあいだは、入力の変更として扱わない
        self.toolbar: ui.row | None = None
        self.scroll_box: ui.element | None = None
        self.today_button: ui.button | None = None
        self.today_tooltip: ui.tooltip | None = None
        self.task_filter = TaskFilter()
        self.quick_add: Position | None = None  # 名前の入力行を出している位置。保存しない
        self.quick_parent: str | None = None  # 入力行で作るタスクを、子にするまとめの id。なければ通常のタスク
        self.quick_summary = False  # 入力行で作るのが、まとめ(最初の子つき)か
        self.quick_section: SectionPath | None = None  # セクションの入力行を、子の末尾に出す親のパス(最上位は ())。保存しない
        self.quick_row: ui.element | None = None
        self.collapsed: set[SectionPath] = set()  # 折りたたんだセクションのパス。保存しない
        self.section_views: dict[SectionPath, SectionView] = {}  # 描画中のセクションの部品
        self.collapsed_summaries: set[str] = set()  # 折りたたんだまとめのタスク id。保存しない
        self.menu: ui.context_menu | None = None  # 右クリックの共有メニュー(1 つだけ。行ごとには作らない)
        self.menu_target: tuple[SectionPath, int] | None = None  # メニューを開いた行
        self.decompose_item: ui.menu_item | None = None
        self.bulk = BulkSelection()  # 一括操作の選択。保存しない・元に戻す対象にしない
        self.bulk_bar: ui.row | None = None
        self.bulk_count: ui.label | None = None
        self.bulk_edit_item: ui.menu_item | None = None
        self.bulk_delete_item: ui.menu_item | None = None
        self.bulk_separator: ui.separator | None = None
        self.bulk_edit_label: ui.label | None = None
        self.bulk_delete_label: ui.label | None = None
        self.extract_item: ui.menu_item | None = None
        self.extract_label: ui.label | None = None
        self.weeks_item: ui.menu_item | None = None
        self.refresh_item: ui.menu_item | None = None
        self.weeks_label: ui.label | None = None
        self.section_menu: ui.context_menu | None = None  # セクションの見出しの右クリックの共有メニュー
        self.section_menu_target: SectionPath | None = None
        self.summary_views: dict[str, SummaryView] = {}  # 描画中のまとめの部品
        self.task_rows: dict[str, ui.element] = {}  # 描画中のタスクの行(折りたたみで表示を切り替える)
        self.tasks_by_id: dict[str, Task] = {}
        self.parents: dict[str, str] = {}  # 子のタスク id → まとめの id
        self.search_input: ui.input | None = None
        self.assignee_select: ui.select | None = None
        self.client: Client | None = None

    def set_project(self, project: Project) -> None:
        """条件は保つ。担当者がメンバーからいなくなったときだけ、担当者の指定を外す。"""
        self.project = project
        self.quick_add = self.quick_section = self.quick_parent = None  # 番号がずれるので、開いている入力行は閉じる
        self.quick_summary = False
        names = {member.name for member in project.members}
        if self.task_filter.assignee not in (None, *names):
            self.task_filter = replace(self.task_filter, assignee=None)
        if self.task_filter.team is not None:  # チームの絞り込みは、名簿の変更に追従し、消えたら外す
            members = team_scope(project, self.task_filter.team)
            if members is None:
                self.task_filter = replace(self.task_filter, team=None, team_members=frozenset())
            elif members != self.task_filter.team_members:
                self.task_filter = replace(self.task_filter, team_members=members)
        self.sync_assignee_select()
        self.tasks_by_id = project.task_map()  # 選択の整理は、描き直しを待たずに行う
        self.sync_bulk(restyle=False)
        self.render.refresh()

    def set_filter(self, task_filter: TaskFilter) -> None:
        if task_filter == self.task_filter:
            return
        self.task_filter = task_filter
        self.sync_bulk(restyle=False)  # 隠れた行は対象から外れる(件数が変わる)。行は描き直しで付け直す
        self.render.refresh()
        self.scroll_to_top()

    def commit_query(self, query: str | None) -> None:
        self.set_filter(replace(self.task_filter, query=(query or "").strip()))

    def focus_search(self) -> None:
        """検索欄にカーソルを置く(ショートカット)。"""
        if self.search_input is not None:
            self.search_input.run_method("focus")

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
            src, dst, copy = parsed
            self.actions.move_task(src, self.after_folded_children(dst), copy)

    def handle_move_section(self, args: object) -> None:
        """セクションの見出しのドロップを受ける。絞り込み中・読み取り専用・同じ親でない・不正な値は無視する。"""
        if self.task_filter.active or self.options.read_only:
            return
        parsed = arrange.parse_section_move(args)
        if parsed is not None and all(arrange.valid_section(self.project, p) for p in parsed):
            self.actions.move_section(*parsed)

    def after_folded_children(self, dst: arrange.Position) -> arrange.Position:
        """折りたたんだまとめの隠れた子のあいだには置けないので、その後ろへ送る。"""
        if not self.collapsed_summaries or self.options.read_only or not arrange.has_list(self.project, dst):
            return dst
        path, index = dst
        tasks = arrange.tasks_at(self.project, path)
        folded = hidden_by_summary(self.project, self.collapsed_summaries)
        while 0 <= index < len(tasks) and tasks[index].id in folded:
            index += 1
        return path, index

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

    def drag_props(self, kind: str, key: str, **extra: object) -> str:
        """ドロップ先の `data-*` 属性。絞り込み中は空(ドロップできない)。"""
        if self.task_filter.active or self.options.read_only:
            return ""
        parts = [f"data-drop={kind}", f"data-si={key}"]
        parts += [f"data-{name}={value}" for name, value in extra.items()]
        return " ".join(parts)

    def hidden_by_ancestor(self, path: SectionPath) -> bool:
        """親のどれかが折りたたまれているか。"""
        return any(path[:n] in self.collapsed for n in range(1, len(path)))

    def remap_collapsed(self, parent: SectionPath, index: int, delta: int) -> None:
        """セクションの挿入・削除で番号がずれたぶん、折りたたみの状態を付け替える(再描画は呼び出し側)。"""
        self.collapsed = arrange.remap_collapsed(self.collapsed, parent, index, delta)

    def reorder_collapsed(self, parent: SectionPath, src: int, dst: int) -> None:
        """セクションの並べ替えで番号がずれたぶん、折りたたみの状態を付け替える(再描画は呼び出し側)。"""
        self.collapsed = arrange.reorder_collapsed(self.collapsed, parent, src, dst)

    def toggle_section(self, path: SectionPath) -> None:
        """セクションの折りたたみを切り替える。描き直さず、行の表示と矢印だけを変える。"""
        self.collapsed.symmetric_difference_update({path})
        view = self.section_views.get(path)
        if view is None or self.options.read_only:
            return
        self.update_links()
        if view.arrow is not None:
            view.arrow.props(f"icon={ARROW_COLLAPSED if path in self.collapsed else ARROW_EXPANDED}")
        if not self.task_filter.active:  # 絞り込み中は、折りたたみを無視する(表示は変えない)
            self.apply_visibility(path, self.hidden_by_ancestor(path))
            self.sync_task_rows()  # 折りたたんだまとめの子は、セクションを開いても隠したまま

    def apply_visibility(self, path: SectionPath, hidden: bool) -> None:
        """セクションの見出し・タスク・サブセクションの表示を、折りたたみの状態に合わせる。"""
        view = self.section_views.get(path)
        if view is None:
            return
        collapsed = path in self.collapsed
        if view.header is not None:
            view.header.set_visibility(not hidden)
        for row in view.rows:
            row.set_visibility(not hidden and not collapsed)
        for child in view.children:
            self.apply_visibility(child, hidden or collapsed)

    def folded_ids(self) -> set[str]:
        """折りたたみで隠すタスクの id(折りたたんだまとめの子)。絞り込み中と読み取り専用では、折りたたみを無視する。"""
        if self.task_filter.active or self.options.read_only:
            return set()
        return hidden_by_summary(self.project, self.collapsed_summaries)

    def toggle_summary(self, task_id: str) -> None:
        """まとめの折りたたみを切り替える。描き直さず、子の行の表示・矢印・件数だけを変える。"""
        self.collapsed_summaries.symmetric_difference_update({task_id})
        view = self.summary_views.get(task_id)
        if view is None or self.options.read_only:
            return
        folded = task_id in self.collapsed_summaries
        if view.arrow is not None:
            view.arrow.props(f"icon={ARROW_COLLAPSED if folded else ARROW_EXPANDED}")
        if view.count is not None:
            view.count.set_visibility(folded)
        self.sync_task_rows()
        self.update_links()

    @staticmethod
    def show_menu_part(part: ui.element | None, shown: bool) -> None:
        """右クリックメニューの一括の項目を出す・隠す。Quasar の項目は `hidden` クラスだけでは隠れないことがあるので、display も切り替える。"""
        if part is None:
            return
        part.set_visibility(shown)
        if shown:
            part.style(remove="display: none")
        else:
            part.style("display: none")

    def visible_task_ids(self) -> list[str]:
        """見えているタスク行の id(描画順)。折りたたみ・絞り込みで隠れた行は含めない。"""
        return [s.task_id for s in self.slots() if s.task_id is not None and s.shown]

    def clicked_task(self, task_id: str, keys: object) -> None:
        """名前の欄の Cmd/Ctrl クリック(個別に追加・解除)と Shift クリック(範囲)。修飾なしは何もしない。"""
        shift, ctrl = held_keys(keys)
        if self.options.read_only or not (shift or ctrl):
            return
        if shift:
            self.bulk.extend(self.visible_task_ids(), task_id, self.tasks_by_id)
        else:
            self.bulk.toggle(task_id, self.tasks_by_id)
        self.sync_bulk()

    def has_selection(self) -> bool:
        return bool(self.bulk.ids)

    def clear_selection(self) -> None:
        self.bulk.clear()
        self.sync_bulk()

    def selected_ids(self) -> list[str]:
        """適用の対象。選択のうち、見えている行だけ(描画順)。"""
        return self.bulk.effective(self.visible_task_ids())

    def sync_bulk(self, restyle: bool = True) -> None:
        """選択バーと、行の見た目(クラス)を合わせる。描き直さない。restyle=False は、描き直しの中(行が自分でクラスを付ける)。"""
        self.bulk.prune(self.tasks_by_id)
        if self.bulk_bar is not None:
            self.bulk_bar.set_visibility(bool(self.bulk.ids))
        for item in (self.bulk_edit_item, self.bulk_delete_item, self.extract_item, self.bulk_separator):
            if not self.bulk.ids:
                self.show_menu_part(item, False)  # 選択がなければ、右クリックのメニューに一括の項目を出さない
        if self.bulk_count is not None:
            chosen = len(self.selected_ids())
            # 1 件だけのときは、選択中であることと使い方を添える(最初の選択で気づけるように)
            hint = "  — Cmd/Ctrl+クリックで追加、Shift+クリックで範囲、Esc で解除" if chosen == 1 else ""
            self.bulk_count.set_text(f"{chosen} 件選択中{hint}")
        if restyle and self.client is not None:
            ids = json.dumps(sorted(self.bulk.ids))
            self.client.run_javascript(
                f"(() => {{ const ids = new Set({ids});"
                " document.querySelectorAll('[data-task-id]').forEach((el) =>"
                " el.classList.toggle('task-selected', ids.has(el.dataset.taskId))); })()"
            )

    def sync_task_rows(self) -> None:
        """行の表示を `slots()`(セクション・まとめの折りたたみ・絞り込みをすべて見たもの)に合わせる。"""
        for slot in self.slots():
            row = self.task_rows.get(slot.task_id) if slot.task_id is not None else None
            if row is not None:
                row.set_visibility(slot.shown)
        self.sync_bulk()

    def expand_section(self, path: SectionPath) -> None:
        """セクションと、その親をすべて展開する(描き直しは、呼び出し側のあとの処理に任せる)。"""
        for n in range(1, len(path) + 1):
            self.collapsed.discard(path[:n])

    def reset_collapsed(self) -> None:
        """すべて展開に戻す(描き直しは、呼び出し側のあとの処理に任せる)。"""
        self.collapsed.clear()
        self.collapsed_summaries.clear()

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
        return scope_options(
            "すべての担当者", [member.name for member in self.project.members], teams_with_members(self.project)
        )

    def on_assignee_filter(self, value: str | None) -> None:
        """担当者のプルダウンの選択。メンバーかチームのどちらか一方だけを絞り込みに入れる。"""
        member, team = read_scope(value)
        members = team_scope(self.project, team)
        if members is None:
            team = None  # 消えた・メンバーのいないチームは、絞り込まない
        self.set_filter(replace(self.task_filter, assignee=member, team=team, team_members=members or frozenset()))

    def sync_assignee_select(self) -> None:
        if self.assignee_select is not None:
            value = scope_value(self.task_filter.assignee, self.task_filter.team)
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

    def today_x(self, columns: list[Column] | None = None) -> float | None:
        """今日の線のチャート内の横位置(px)。表示範囲の外なら None。"""
        if columns is None:
            columns = build_columns(
                self.project, self.view_scale, self.holidays, self.view_period, self.reference_values()
            )
        position = today_position(self.now(), columns, self.view_scale)
        return None if position is None else position * COLUMN_WIDTH_PX[self.view_scale]

    def scroll_to_today(self) -> None:
        x = self.today_x()
        if self.client is not None and x is not None:
            self.client.run_javascript(today_scroll_js(x, self.name_width))

    def scroll_on_open(self) -> None:
        """別のプロジェクトを開いた直後だけ、先頭に戻してから今日の位置へ移る(範囲の外なら先頭のまま)。"""
        self.reset_scroll()
        self.scroll_to_today()

    def sync_today_button(self, x: float | None) -> None:
        """`当日`ボタンの押せる・押せないと、ホバーの文言を、今日が表示範囲の中かに合わせる。"""
        if self.today_button is None or self.today_tooltip is None:
            return
        self.today_button.set_enabled(x is not None)
        self.today_tooltip.set_text("今日の位置へ移ります" if x is not None else "今日は表示期間の外です")

    def scroll_to_top(self) -> None:
        if self.client is not None:
            self.client.run_javascript(SCROLL_TO_TOP_JS)

    @property
    def holidays(self) -> dict[date, str]:
        """祝日に、休みにしたイベントの期間を足した辞書。計算はこれを使う。"""
        return self._effective.get(self.project, self.base_holidays)

    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.base_holidays = holidays
        self.render.refresh()

    def set_scale(self, scale: Scale) -> None:
        self.scale = scale
        if self.period is not None and self.period_error_text(self.period, scale) is not None:
            ui.notify("期間が長すぎるため、期間を自動に戻しました", type="warning")
            self.period = None  # 描き直しで固まるので、自動に戻す
            self.sync_period_input()
        elif self.period_input is not None and self.period_error is not None and self.period_error.text:
            self.on_period_changed(self.period_input.value)  # 長すぎて退けた欄の期間を、新しいスケールで評価し直す
        self.render.refresh()
        self.scroll_to_left()  # 列の幅が変わるので、横の位置は意味を持たない(縦は保つ)

    @property
    def view_period(self) -> tuple[date, date] | None:
        """描画に使う期間。プレビューで指定されていればそれ、なければメインの期間(None は自動)。"""
        return self.options.period or self.period

    def period_error_text(self, period: tuple[date, date], scale: Scale) -> str | None:
        """期間が列の数の上限を超えるときの、エラー文。"""
        columns = build_columns(self.project, scale, self.holidays, period, self.reference_values())
        return check_column_count(scale, len(columns))

    def sync_period_input(self) -> None:
        """メインの期間を欄に映す(エラーも消す)。欄の変更としては扱わない。"""
        if self.period_input is None:
            return
        self.syncing_period = True
        try:
            self.period_input.set_value(format_period(*self.period) if self.period else "")
        finally:
            self.syncing_period = False
        if self.period_error is not None:
            self.period_error.set_text("")

    def set_period(self, period: tuple[date, date] | None) -> None:
        """メインの表示期間を変えて、描き直す(None は自動)。"""
        if period == self.period:
            return
        self.period = period
        self.sync_period_input()
        self.render.refresh()
        self.scroll_to_left()

    def normalize_period_input(self) -> None:
        """欄を離れたとき、両端の省略形(`10/15`・`1015`・`20261015`)を `YYYY-MM-DD` に整える。読めない値はそのまま。"""
        if self.period_input is None:
            return
        text = self.period_input.value or ""
        fixed = normalize_period(text, self.now().date()) if text.strip() else None
        if fixed is not None and fixed != text:
            self.period_input.set_value(fixed)

    def on_period_changed(self, text: str | None) -> None:
        """期間の欄が変わった。空は自動。不正・長すぎる値はエラーを出して、前の期間のままにする。"""
        if self.syncing_period or self.period_error is None:
            return
        if not (text or "").strip():
            self.period_error.set_text("")
            if self.period is not None:
                self.period = None
                self.render.refresh()
                self.scroll_to_left()
            return
        try:
            period = validate_period(*split_period(text or ""))
        except ValueError as exc:
            self.period_error.set_text(str(exc))
            return
        message = self.period_error_text(period, self.view_scale)
        self.period_error.set_text(message or "")
        if message is None and period != self.period:
            self.period = period
            self.render.refresh()
            self.scroll_to_left()

    @property
    def view_scale(self) -> Scale:
        """描画に使うスケール。プレビューで指定されていればそれ、なければツールバーのスケール。"""
        return self.options.scale or self.scale

    def set_visible(self, visible: bool) -> None:
        """ツールバーとチャートを、出す・隠す(描き直さない)。位置は、スクロールのたびに覚え、出したあとに戻す。"""
        if self.toolbar is None or self.scroll_box is None:
            return
        if visible:
            self.toolbar.set_visibility(not self.options.read_only)
            self.scroll_box.set_visibility(True)
            if self.client is not None:
                self.client.run_javascript(SHOW_CHART_JS)
        else:
            self.toolbar.set_visibility(False)
            self.scroll_box.set_visibility(False)

    def set_options(self, options: ViewOptions) -> None:
        """表示の設定を変えて、描き直す。描画のスケールが変わるときは、横のスクロールを先頭へ戻す。"""
        before = self.view_scale
        self.options = options
        self.task_filter = replace(self.task_filter, exclude=options.excluded if options.hide_excluded else frozenset())
        if self.toolbar is not None:
            self.toolbar.set_visibility(not options.read_only)
        self.render.refresh()
        if self.view_scale != before:
            self.scroll_to_left()  # 列の幅が変わるので、横の位置は意味を持たない(縦は保つ)

    def resize_classes(self) -> str:
        """名前の欄の右端を、幅の調整の掴み場所にするクラス(先頭に空白)。読み取り専用では付けない。"""
        return "" if self.options.read_only else " gantt-name-resizable"

    def reference_values(self) -> dict[str, ReferenceValue]:
        """参照行(タスクの id)ごとの、表示に使う参照値。参照先が読めない行は含めない。"""
        return {tid: ref.value for tid, ref in self.refs.items() if ref.value is not None}

    def content_width(self) -> int:
        """描画の全体の幅(px)。名前の列と、すべての列。画像の幅になる。"""
        columns = build_columns(
            self.project, self.view_scale, self.holidays, self.view_period, self.reference_values()
        )
        return self.name_width + COLUMN_WIDTH_PX[self.view_scale] * len(columns)

    def bar_visible(
        self, start: datetime | None, end: datetime | None, columns: list[Column]
    ) -> bool:
        """棒を描くか。期間を指定したときだけ、期間と重ならない棒を描かない(端に細い棒を出さない)。"""
        if self.view_period is None or start is None or end is None:
            return True
        return in_range(start, end, columns)

    def slots(self) -> list[RowSlot]:
        return row_slots(
            self.project,
            self.task_filter,
            self.collapsed,
            self.options.read_only,
            ROW_HEIGHT_PX,
            ADD_ROW_HEIGHT_PX,
            self.collapsed_summaries,
            self.quick_add,
            self.quick_section,
        )

    def link_bars(self, columns: list[Column], width: int) -> dict[str, Bar]:
        """矢印を出せる棒(表示範囲にあるもの)の、境界からの左端・右端。"""
        bars: dict[str, Bar] = {}
        for task in self.project.all_tasks():
            start, end = self.schedule.start(task), self.schedule.bar_end(task)
            span = bar_span(start, end, columns)
            if span is None or not self.bar_visible(start, end, columns):
                continue
            left = span[0] * width
            if task.kind is TaskKind.CHECKPOINT:  # ◆ の左右の端に、矢印をつなぐ
                half = CHECKPOINT_MARKER_PX / 2
                bars[task.id] = Bar(left - half, left + half)
            else:
                bars[task.id] = Bar(left, left + max(span[1] * width, MIN_BAR_PX))
        return bars

    def links_markup(self, columns: list[Column], width: int) -> str:
        """矢印の SVG。内容は数値と、保存時に検証した id だけで、念のためエスケープする。"""
        slots = self.slots()
        centers = row_centers(slots, 0)
        bars = self.link_bars(columns, width)
        paths: list[str] = []
        parents = parent_map(self.project) if self.collapsed_summaries else {}
        folding = not self.task_filter.active and not self.options.read_only

        def shown(task_id: str) -> str:
            """折りたたんだまとめに隠れた子は、そのまとめの帯から引く。"""
            parent = parents.get(task_id)
            if folding and task_id not in centers and parent in self.collapsed_summaries and parent in centers:
                return parent
            return task_id

        drawn: set[tuple[str, str]] = set()
        for task in self.project.all_tasks():
            for pred in task.predecessors:
                pid, tid = shown(pred), shown(task.id)
                if pid == tid or (pid, tid) in drawn:
                    continue
                if pid not in bars or tid not in bars:
                    continue
                if pid not in centers or tid not in centers:
                    continue
                drawn.add((pid, tid))
                points = link_points(bars[pid], centers[pid], bars[tid], centers[tid], ROW_HEIGHT_PX)
                paths.append(
                    f'<path data-link="{html.escape(pid)}-{html.escape(tid)}"'
                    f' d="{path_data(points)}" style="{LINK_STYLE}" marker-end="url(#link-head)"/>'
                )
        size = f'width="{width * len(columns):g}" height="{total_height(slots, 0):g}"'
        return f'<svg {size} style="overflow: visible">{LINK_HEAD}{"".join(paths)}</svg>'

    def links(self, columns: list[Column], width: int) -> None:
        """棒より下、格子線・縞より上に、矢印をまとめて 1 要素で置く。

        ヘッダーの高さは環境で変わる(実機では設計より高かった)ので、座標は行の上端から測り、
        最初の行の直前に置いた高さ 0 の要素を基準にする。
        """
        self.link_layout = (columns, width)
        anchor = ui.element("div").style("position: relative; height: 0")
        with anchor:
            self.links_html = ui.html(self.links_markup(columns, width), sanitize=False)
            self.links_html.classes("gantt-links").style(
                "position: absolute; top: 0; left: var(--name-w); pointer-events: none"
            ).mark("links")

    def update_links(self) -> None:
        """折りたたみの切り替えで、再描画せず、矢印だけ作り直す。"""
        if self.links_html is not None and self.link_layout is not None:
            self.links_html.content = self.links_markup(*self.link_layout)

    def build(self) -> None:
        self.client = context.client
        ui.add_css(CHART_DRAG_CSS)
        ui.add_css(NAME_RESIZE_CSS)
        ui.add_css(STICKY_CSS)
        ui.add_css(PROGRESS_CSS)
        ui.add_css(STATUS_CSS)
        ui.add_css(TODAY_CSS)
        ui.add_css(WARNING_CSS)
        ui.add_css(PRIORITY_CSS)
        ui.add_css(LINK_CSS)
        ui.add_css(CONTEXT_MENU_CSS)
        ui.add_css(EVENT_CSS)
        ui.add_css(REFERENCE_CSS)
        ui.add_css(BULK_CSS)
        ui.add_css(SHIFT_TOOLTIP_CSS)
        ui.add_head_html(f"<script>{CHART_DRAG_JS}</script>")
        ui.add_head_html(f"<script>{SHIFT_TRACK_JS}</script>")
        ui.on("chart_move", lambda e: self.handle_move(e.args))
        ui.on("chart_move_section", lambda e: self.handle_move_section(e.args))
        ui.on("chart_shift", lambda e: self.handle_shift(e.args))
        ui.on("chart_name_width", lambda e: self.handle_name_width(e.args))
        self.build_menu()
        self.toolbar = ui.row().classes("w-full items-center no-wrap gap-4")
        # 検索欄・担当の切り替えの右クリックで、WebView 標準のメニュー(サービス・自動入力など)を出さない
        self.toolbar.on("contextmenu", js_handler="(e) => e.preventDefault()")
        with self.toolbar.mark("chart-toolbar"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).classes("shrink-0").mark("scale-toggle")
            self.today_button = (
                ui.button("当日", icon="today", on_click=self.scroll_to_today)
                .props("flat dense")
                .classes("shrink-0")
                .mark("today-button")
            )
            with self.today_button:
                self.today_tooltip = ui.tooltip("今日の位置へ移ります")
            with ui.column().classes("gap-0 shrink-0"):  # 欄とエラーを縦に並べる(エラーが空のときは高さを取らない)
                self.period_input = (
                    ui.input(placeholder="表示期間(空は自動)", on_change=lambda e: self.on_period_changed(e.value))
                    .props("clearable dense outlined")
                    .style("width: 17rem")
                    .mark("chart-period")
                )
                add_range_picker(self.period_input, "chart")
                self.period_input.on("blur", lambda _e: self.normalize_period_input())
                self.period_error = ui.label("").classes("text-negative text-caption").mark("chart-period-error")
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
                    value=scope_value(self.task_filter.assignee, self.task_filter.team),
                    on_change=lambda e: self.on_assignee_filter(e.value),
                )
                .props("dense outlined")
                .style("flex: 1 1 8rem; min-width: 7rem; max-width: 12rem")
                .mark("assignee-filter")
            )
        # スクロールする枠は一度だけ作る。render は中身だけを作り直すので、描き直してもスクロール位置が保たれる
        if not self.options.read_only:
            with ui.row().classes("w-full items-center no-wrap gap-2") as self.bulk_bar:
                self.bulk_count = ui.label("").classes("text-body2").mark("bulk-count")
                ui.button("編集…", icon="edit", on_click=lambda: self.actions.bulk_edit(self.selected_ids())).props(
                    "flat dense size=sm"
                ).mark("bulk-edit")
                ui.button("削除", icon="delete", on_click=lambda: self.actions.bulk_delete(self.selected_ids())).props(
                    "flat dense size=sm color=negative"
                ).mark("bulk-delete")
                ui.button(
                    "子プロジェクトに切り出し…", icon="call_split", on_click=lambda: self.actions.extract_tasks(self.selected_ids())
                ).props("flat dense size=sm").mark("bulk-extract")
                ui.button("解除", icon="close", on_click=self.clear_selection).props("flat dense size=sm").mark("bulk-clear")
            self.bulk_bar.mark("bulk-bar").set_visibility(False)
        scroll_style = (
            f"overflow: auto; max-height: {CHART_MAX_HEIGHT};"
            f" padding-bottom: {SCROLLBAR_ROOM_PX}px"
        )
        scroll = ui.element("div").classes("w-full").style(scroll_style)
        self.scroll_box = scroll
        scroll.on("scroll", js_handler=TRACK_SCROLL_JS)
        with scroll.props("data-chart-scroll").mark("chart-scroll"):
            self.render()

    def build_menu(self) -> None:
        """タスクの行の右クリックで開く共有メニュー。開いた行は `menu_target` に持つ。"""

        def act(action: Callable[[SectionPath, int], object]) -> Callable[[], None]:
            def run() -> None:
                if self.menu_target is not None:
                    action(*self.menu_target)

            return run

        with ui.context_menu().props("no-parent-event").classes("app-context-menu") as self.menu:  # 親の右クリックでは開かない(行の右クリックだけ)
            with ui.menu_item(on_click=lambda: self.actions.bulk_edit(self.selected_ids())).mark("context-bulk-edit") as item:
                with ui.item_section():
                    self.bulk_edit_label = ui.label("選択中を編集…")  # 件数入りの文言に open_menu で差し替える
            self.bulk_edit_item = item
            with ui.menu_item(on_click=lambda: self.actions.bulk_delete(self.selected_ids())).props(
                "class=text-negative"
            ).mark("context-bulk-delete") as item:
                with ui.item_section():
                    self.bulk_delete_label = ui.label("選択中を削除")
            self.bulk_delete_item = item
            with ui.menu_item(on_click=lambda: self.actions.extract_tasks(self.selected_ids())).mark("context-extract") as item:
                with ui.item_section():
                    self.extract_label = ui.label("選択中を子プロジェクトに切り出し…")
            self.extract_item = item
            self.bulk_separator = ui.separator()
            for part in (self.bulk_edit_item, self.bulk_delete_item, self.extract_item, self.bulk_separator):
                self.show_menu_part(part, False)  # 選択した行の右クリックで、open_menu が出す
            ui.menu_item("編集", on_click=act(lambda p, t: self.actions.edit_task(p, t))).mark("context-edit")
            self.decompose_item = ui.menu_item(
                "分解…", on_click=act(lambda p, t: self.actions.decompose_task(p, t))
            ).mark("context-decompose")
            with ui.menu_item(on_click=act(lambda p, t: self.actions.toggle_weeks(p, t))).mark("context-weeks") as item:
                with ui.item_section():
                    self.weeks_label = ui.label("週ごとに分ける").mark("context-weeks-label")  # 状態で文言を替える
            self.weeks_item = item
            ui.menu_item("コピー", on_click=act(lambda p, t: self.actions.copy_task(p, t))).mark("context-copy")
            self.refresh_item = ui.menu_item(
                "更新", on_click=act(lambda p, t: self.actions.refresh_reference(p, t))
            ).mark("context-refresh")
            with self.refresh_item:
                ui.tooltip("参照の方式が「スナップショット」のときだけ更新できます")  # 押せないときの理由(押せるときも害はない)
            ui.menu_item("名前の変更", on_click=act(lambda p, t: self.actions.rename_task(p, t))).mark("context-rename")
            ui.separator()
            ui.menu_item("削除", on_click=act(lambda p, t: self.actions.delete_task(p, t))).props(
                "class=text-negative"
            ).mark("context-delete")
        with ui.context_menu().props("no-parent-event").classes("app-context-menu") as self.section_menu:
            for label, marker, action in (
                ("コピー", "section-context-copy", lambda p: self.actions.copy_section(p)),
                ("名前の変更", "section-context-rename", lambda p: self.actions.rename_section(p)),
            ):
                ui.menu_item(label, on_click=lambda action=action: self.act_on_section(action)).mark(marker)
            ui.separator()
            ui.menu_item("削除", on_click=lambda: self.act_on_section(lambda p: self.actions.delete_section(p))).props(
                "class=text-negative"
            ).mark("section-context-delete")
        ui.run_javascript(self.menu_close_js())

    def act_on_section(self, action: Callable[[SectionPath], object]) -> None:
        if self.section_menu_target is not None:
            action(self.section_menu_target)

    def open_section_menu(self, path: SectionPath) -> None:
        """右クリックした見出しのセクションを覚える(メニュー自体はブラウザ側で開く)。"""
        self.section_menu_target = path

    def section_menu_on_right_click(self, header: ui.element, path: SectionPath) -> None:
        """セクションの見出しの右クリックで、セクションのメニューを、クリックした位置に開く。"""
        if self.options.read_only or self.section_menu is None:
            return
        js = f"(e) => {{ e.preventDefault(); getElement({self.section_menu.id}).show(e); emit(); }}"
        header.on("contextmenu", lambda path=path: self.open_section_menu(path), js_handler=js)

    def menu_close_js(self) -> str:
        """メニューの外を押したら閉じる JS(タスクとセクションの両方)。Quasar の外側クリックだけに任せると、
        ドラッグできる行などで閉じないことがある。メニューの中の押下は除く(項目のクリックを妨げない)。"""
        assert self.menu is not None and self.section_menu is not None
        hide = "".join(
            f" if (getElement({menu.id})) getElement({menu.id}).hide();" for menu in (self.menu, self.section_menu)
        )
        return (
            "document.addEventListener('pointerdown', (e) => {"
            " if (e.target.closest && e.target.closest('.q-menu')) return;"
            f"{hide}"
            " }, true);"
        )

    def open_menu(self, path: SectionPath, ti: int) -> None:
        """右クリックした行を覚え、分解できるかをメニューに反映する(メニュー自体はブラウザ側で開く)。"""
        self.menu_target = (path, ti)
        if self.decompose_item is None:
            return
        tasks = arrange.tasks_at(self.project, path) if arrange.has_list(self.project, (path, 0)) else []
        chosen = self.selected_ids()
        clicked = tasks[ti] if ti < len(tasks) else None
        show = clicked is not None and clicked.id in chosen  # 選択に含まれる行の右クリックだけ、一括の項目を出す
        self.show_menu_part(self.bulk_separator, show)
        for item, label, text in (
            (self.bulk_edit_item, self.bulk_edit_label, "編集…"),
            (self.bulk_delete_item, self.bulk_delete_label, "削除"),
            (self.extract_item, self.extract_label, "子プロジェクトに切り出し…"),
        ):
            self.show_menu_part(item, show)
            if show and label is not None:
                label.set_text(f"選択中 {len(chosen)} 件を{text}")
        if self.weeks_item is not None and self.weeks_label is not None:
            task = tasks[ti] if ti < len(tasks) else None
            weekly = task is not None and bool(task.weekly_crew)
            can = task is not None and (weekly or (task.kind is TaskKind.NORMAL and bool(task.assignees)))
            self.weeks_label.set_text("週ごとをやめる" if weekly else "週ごとに分ける")
            self.weeks_item.props(add="" if can else "disable", remove="disable" if can else "")
        blocked = ti >= len(tasks) or decompose_block_reason(self.project, tasks[ti], self.holidays) is not None
        self.decompose_item.props(add="disable" if blocked else "", remove="" if blocked else "disable")
        if self.refresh_item is not None:
            task = tasks[ti] if ti < len(tasks) else None
            is_reference = task is not None and task.kind is TaskKind.REFERENCE
            can = is_reference and self.project.reference_mode is ReferenceMode.SNAPSHOT
            self.refresh_item.set_visibility(is_reference)
            self.refresh_item.props(add="" if can else "disable", remove="disable" if can else "")

    def menu_on_right_click(self, row: ui.element, path: SectionPath, ti: int) -> None:
        """行の右クリックで共有メニューを、クリックした位置に開く。ブラウザ標準のメニューは出さない。"""
        if self.options.read_only or self.menu is None:
            return
        js = f"(e) => {{ e.preventDefault(); getElement({self.menu.id}).show(e); emit(); }}"
        row.on("contextmenu", lambda path=path, ti=ti: self.open_menu(path, ti), js_handler=js)

    def open_quick_add(self, path: SectionPath, index: int, parent: str | None = None, summary: bool = False) -> None:
        """名前の入力行を、セクション(root は ())の index 番目に出す。折りたたんだセクションは開く。parent があれば、そのまとめの子として(折りたたんだまとめも開く)、summary ならまとめ(最初の子つき)として作る。"""
        if self.options.read_only:
            return
        if self.task_filter.active:
            ui.notify("絞り込みを解除してください")
            return
        self.collapsed.discard(path)
        if parent is not None:
            self.collapsed_summaries.discard(parent)
        self.quick_add, self.quick_section, self.quick_parent, self.quick_summary = (path, index), None, parent, summary
        self.render.refresh()

    def open_quick_section(self, parent: SectionPath) -> None:
        """セクションの名前の入力行を、親のセクション(最上位は ())の子の末尾に出す。折りたたんだ親は開く。"""
        if self.options.read_only:
            return
        if self.task_filter.active:
            ui.notify("絞り込みを解除してください")
            return
        if len(parent) >= MAX_SECTION_DEPTH:
            ui.notify(f"サブセクションは {MAX_SECTION_DEPTH} 階層までです")
            return
        self.collapsed.discard(parent)
        self.quick_add, self.quick_section, self.quick_parent, self.quick_summary = None, parent, None, False
        self.render.refresh()

    def double_clicked_task(self, path: SectionPath, ti: int, keys: object) -> None:
        """タスクの名前の欄のダブルクリック。Shift ならそのセクションの子の末尾にセクションを、Ctrl/Cmd なら直下(まとめのブロックの後ろ)にまとめを作る。
        押さなければ、直下にタスクを作る(子の行は同じまとめの子を、まとめの行は子の末尾に子を作る)。"""
        shift, ctrl = held_keys(keys)
        if shift:
            self.open_quick_section(path)
        else:
            self.open_quick_add_after(path, ti, ctrl)

    def double_clicked_section(self, path: SectionPath, keys: object) -> None:
        """セクションの見出し・末尾の追加行(root は ())のダブルクリック。Shift ならその子の末尾にセクションを、Ctrl/Cmd ならまとめを、なければタスクを作る。"""
        shift, ctrl = held_keys(keys)
        if shift:
            self.open_quick_section(path)
        else:
            self.open_quick_add_at_end(path, ctrl)

    def open_quick_add_after(self, path: SectionPath, ti: int, summary: bool = False) -> None:
        """タスクの直下(まとめは子の後ろ)に出す。summary なら、まとめを作る(子の行は、まとめのブロックの後ろ)。
        summary でなければ、子の行は同じまとめの子として、まとめの行は子の末尾に子として作る。"""
        if not arrange.has_task(self.project, (path, ti)):
            return
        tasks = arrange.tasks_at(self.project, path)
        task, owner = tasks[ti], arrange.parent_of(self.project, (path, ti))
        if summary:
            anchor = tasks.index(owner) if owner is not None else ti
            self.open_quick_add(*arrange.after_task(self.project, (path, anchor)), summary=True)
            return
        parent = owner if owner is not None else (task if task.kind is TaskKind.SUMMARY else None)
        self.open_quick_add(*arrange.after_task(self.project, (path, ti)), parent.id if parent is not None else None)

    def open_quick_add_at_end(self, path: SectionPath, summary: bool = False) -> None:
        """セクション(root は ())のタスクの末尾に出す。summary ならまとめを作る。"""
        self.open_quick_add(path, len(arrange.tasks_at(self.project, path)), summary=summary)

    def close_quick_add(self) -> None:
        """入力行を閉じる。描き直さず、行を消して矢印だけ作り直す。"""
        row, self.quick_row, self.quick_add, self.quick_section, self.quick_parent = self.quick_row, None, None, None, None
        self.quick_summary = False
        if row is not None and not row.is_deleted:
            row.delete()
        self.update_links()

    def submit_quick_add(self, text: object, error: ui.label) -> None:
        name = str(text or "").strip()
        if message := (section_name_error if self.quick_section is not None else task_name_error)(name):
            error.set_text(message)
            error.set_visibility(True)
            return
        if self.quick_section is not None:
            parent, _ = self.quick_section, self.close_quick_add()
            self.actions.add_named_section(parent, name)
            return
        if self.quick_add is None:
            return
        (path, index), parent, summary, _ = self.quick_add, self.quick_parent, self.quick_summary, self.close_quick_add()
        if summary:
            self.actions.add_named_summary(path, index, name)
        elif parent is not None:
            self.actions.add_named_child(path, index, name, parent)
        else:
            self.actions.add_named_task(path, index, name)

    def quick_add_row(self, path: SectionPath, hidden: bool = False, section: bool = False) -> None:
        """名前を入れる入力行(section ならセクションの名前。path はその親)。名前の欄の中に入力欄を置き、Enter で確定、Esc かフォーカスを外すと取り消す。"""
        row = ui.row().classes("items-center no-wrap gap-0").style(ROW_STYLE).mark("quick-add-row")
        row.set_visibility(not hidden)
        self.quick_row = row
        with row:
            cell = ui.row().classes("items-center no-wrap gap-1 gantt-sticky" + self.resize_classes())
            cell.style(
                f"width: var(--name-w); padding-left: {16 + 12 * max(len(path) - 1, 0) + (SUMMARY_INDENT_PX if self.quick_parent else 0)}px;"
                f" padding-right: 4px; align-self: stretch; {sticky_left(STICKY_Z_NAME)}"
            )
            with cell:
                label = "セクション名" if section else "まとめ名" if self.quick_summary else "タスク名"
                field = ui.input(placeholder=f"{label}(Enter で作成・Esc で取り消し)").classes("grow")
                field.props("dense outlined autofocus").mark("quick-add-input")
            error = ui.label("").classes("text-negative text-caption").style("padding-left: 8px")
            error.set_visibility(False)
            error.mark("quick-add-error")
        field.on("keydown.enter", lambda e: self.submit_quick_add(e.args, error), js_handler=SEARCH_ENTER_JS)
        field.on("keydown.escape", self.close_quick_add)
        field.on("blur", self.close_quick_add)

    def quick_add_here(self, path: SectionPath, index: int, hidden: bool = False) -> None:
        """入力行が、このセクションの index 番目に出ているなら描く。"""
        if self.quick_add == (path, index):
            self.quick_add_row(path, hidden)

    def quick_section_here(self, parent: SectionPath, hidden: bool = False) -> None:
        """セクションの入力行が、この親の子の末尾に出ているなら描く。"""
        if self.quick_section == parent:
            self.quick_add_row(parent, hidden, section=True)

    @property
    def selecting(self) -> bool:
        return self.options.selectable and self.options.read_only and not self.options.hide_excluded

    def selection_box(self, marker: str, ids: list[str]) -> None:
        """出力のチェックボックス。一部だけ出力のとき(中間)に押すと、全部を出力にする。"""
        state = check_state(ids, self.options.excluded)
        value = None if state is CheckState.MIXED else state is CheckState.ON  # 中間は None
        box = ui.checkbox(value=value)
        box.props("dense").classes("shrink-0").mark(marker)
        if state is None:
            box.props("disable")
            return

        def pick(_: object, ids: list[str] = ids, checked: bool = toggled(state)) -> None:
            if self.options.on_select is not None:
                self.options.on_select(ids, checked)

        box.on_value_change(pick)

    @ui.refreshable_method
    def render(self) -> None:
        self.section_views = {}
        self.summary_views = {}
        self.task_rows = {}
        self.tasks_by_id = self.project.task_map()
        self.parents = parent_map(self.project)
        self.refs = self.references_of()
        self.schedule = Schedule(self.project, self.holidays, self.reference_values())
        columns = build_columns(
            self.project, self.view_scale, self.holidays, self.view_period, self.reference_values()
        )
        self.sync_today_button(self.today_x(columns))
        self.overloads = overallocations(self.project, self.holidays)
        self.category_lookup = by_id(self.project.categories)
        self.icon_lookup = {m.name: m.icon for m in self.project.members if m.icon}
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
            self.event_tints(columns, width, top)
            self.today_line(columns, width, top)
            self.header(columns, width)
            self.no_match_message()
            self.links(columns, width)
            folded = self.folded_ids()
            self.quick_add_here((), 0)
            for ti, task in enumerate(self.project.tasks):
                if matches(task, self.task_filter, self.tasks_by_id):
                    self.task_row((), ti, task, columns, width).set_visibility(task.id not in folded)
                    self.quick_add_here((), ti + 1)
            self.top_add_row()
            for index, section in enumerate(self.project.sections):
                self.section_rows((index,), section, columns, width)
            self.quick_section_here(())
            self.bottom_add_row()
        self.sync_bulk(restyle=False)

    def no_match_message(self) -> None:
        """絞り込み中に1件も一致しないとき(タスクが1つもないときは出さない)。"""
        tasks = self.project.all_tasks()
        if not (self.task_filter.active and tasks):
            return
        if any(matches(task, self.task_filter, self.tasks_by_id) for task in tasks):
            return
        ui.label("条件に一致するタスクがありません").classes("text-caption").style(
            "position: relative; padding: 8px 16px"
        ).mark("no-match")

    def add_row(self, marker: str) -> tuple[ui.row, ui.row]:
        """追加行の枠(行と、名前の列の右寄せのセル)。名前の列の右端にボタンを置く。"""
        row = ui.row().classes("items-center no-wrap gap-0").style(ADD_ROW_STYLE)
        row.mark(marker)
        with row:
            cell = ui.row().classes("items-center justify-end no-wrap gantt-sticky" + self.resize_classes())
            cell.style(
                f"width: var(--name-w); padding-right: 8px; align-self: stretch;"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
        return row, cell

    def top_add_row(self) -> None:
        """セクションなしのタスクの末尾に置く追加行。"""
        if self.options.read_only:
            return
        row, cell = self.add_row("top-end")
        row.props(self.drag_props("top-end", "top", count=len(self.project.tasks)))
        row.on("dblclick", lambda e: self.double_clicked_section((), e.args), js_handler=QUICK_ADD_JS)
        with cell:
            ui.button("タスク追加", icon="add_task", on_click=self.actions.add_top_task).props(
                "flat dense size=sm"
            ).mark("add-task-top")

    def bottom_add_row(self) -> None:
        """チャートの末尾(最後のセクションの下)に置く、セクションの追加行。移動の落とし先にはしない。"""
        if self.options.read_only:
            return
        _, cell = self.add_row("bottom-end")
        with cell:
            ui.button("セクション追加", icon="create_new_folder", on_click=self.actions.add_section).props(
                "flat dense size=sm"
            ).mark("add-section")

    def gridlines(self, columns: list[Column], width: int, top: int) -> None:
        """列の境界の縦線。全スケールで引く。年・月の帯の下から始める。"""
        cells = f'<div style="width:{width}px;border-left:{GRID_BORDER}"></div>' * len(columns)
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: var(--name-w);"
            " pointer-events: none"
        ).mark("gridlines")

    def work_day_strip(
        self, key: int | str, ti: int, notes: dict[date, str], columns: list[Column], width: int
    ) -> None:
        """日次の行の下端に、担当者が稼働日を上書きした日の印(橙)を出す。内容は日付と、メンバー名・時刻(エスケープする)。"""
        cells = "".join(
            f'<div title="{html.escape(notes[c.start], quote=True)}" style="width:{width}px;height:100%;'
            f'background:{DEADLINE_COLOR};pointer-events:auto"></div>'
            if c.start in notes
            else f'<div style="width:{width}px"></div>'
            for c in columns
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; left: var(--name-w); bottom: 0; height: {WORKMARK_HEIGHT_PX}px;"
            " pointer-events: none"
        ).mark(f"workmark-{key}-{ti}")

    def stripes(self, columns: list[Column], width: int, top: int) -> None:
        """日次スケールの土日祝の背景。内容は定数と日付のみで利用者の入力を含まない。"""
        cells = "".join(
            f'<div style="width:{width}px;background:'
            f'{KIND_COLORS.get(day_kind(column.start, self.base_holidays), "transparent")}">'
            "</div>"
            for column in columns
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: var(--name-w);"
            " pointer-events: none"
        ).mark("stripes")

    def shown_events(self) -> list[Event]:
        return self.project.events if self.options.show_events else []

    def today_line(self, columns: list[Column], width: int, top: int) -> None:
        """今日の赤い縦線。年・月の帯の下から最下行まで。クリックは通す。内容は定数と数値だけ。"""
        position = today_position(self.now(), columns, self.view_scale)
        if not self.options.show_today or position is None:
            return
        left = from_name(position * width - TODAY_LINE_WIDTH_PX / 2)
        ui.element("div").style(
            f"position: absolute; top: {top}px; bottom: 0; left: {left};"
            f" width: {TODAY_LINE_WIDTH_PX}px; background: {TODAY_COLOR_VAR};"
            " pointer-events: none; z-index: 1"
        ).mark("today-line")

    def event_tints(self, columns: list[Column], width: int, top: int) -> None:
        """イベントの期間のセルの色。内容は定数と検証済みの色だけで、利用者の文字列を含まない。"""
        colors = cell_colors(self.shown_events(), columns)
        if not any(colors):
            return
        cells = "".join(
            f'<div class="event-tint" style="width:{width}px;--ev:{color_hex(color)}"></div>'
            if color
            else f'<div style="width:{width}px"></div>'
            for color in colors
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: {top}px; bottom: 0; left: var(--name-w); pointer-events: none"
        ).mark("event-tints")

    def event_rows(self, columns: list[Column], width: int) -> None:
        """日付の下の帯。重なるイベントは段を重ねる。見出しの中なので、縦にも横にも固定される。"""
        events = self.shown_events()
        lanes = assign_lanes(events, columns)
        drawn: list[tuple[int, int, int]] = []  # (イベントの添字, 先頭の列, 列数)
        for i, event in enumerate(events):
            span = column_span(event, columns)
            if span is not None:
                drawn.append((i, span[0], span[1]))
        used_lanes = sorted({lanes[i] for i, _, _ in drawn})  # 描くイベントだけで、段を詰める
        for n, lane in enumerate(used_lanes):
            style = f"height: {EVENT_ROW_HEIGHT_PX}px; position: relative; border-bottom: {GRID_BORDER}"
            with ui.row().classes("items-center no-wrap gap-0").style(style).mark(f"event-row-{n}"):
                self.header_spacer(f"event-row-{n}-spacer")
                track = ui.element("div").style(
                    f"position: relative; flex: none; height: 100%; width: {width * len(columns)}px"
                )
                with track:
                    for i, first, count in drawn:
                        if lanes[i] == lane:
                            self.event_bar(events[i], first * width, count * width)

    def event_bar(self, event: Event, left: int, bar_width: int) -> None:
        bar = ui.element("div").style(
            f"position: absolute; left: {left}px; width: {bar_width}px; top: 0;"
            f" height: {EVENT_ROW_HEIGHT_PX}px; overflow: clip; --ev: {color_hex(event.color)}"
        )
        # 属性の値として渡る(HTML にはならない)。全文はマウスオーバーで出す。休みのイベントは、その旨を添える
        bar._props["title"] = f"{event.text}(休み: 全員の稼働日)" if event.closed else event.text
        with bar.mark(f"event-bar-{event.id}"):
            ui.element("div").classes("event-fill")
            # 帯が画面より広くても、名前の列の右端に文字が残るよう、帯の中で固定する(年・月の帯と同じ)
            ui.label(f"休 {event.text}" if event.closed else event.text).style(
                "position: sticky; left: var(--name-w); display: inline-block; padding: 0 4px;"
                " font-size: 10px; line-height: 16px; white-space: nowrap"
            )

    def header(self, columns: list[Column], width: int) -> None:
        """年・月の帯(結合セル)と、日・曜日の見出し。月次スケールに月の帯はない。"""
        header_style = f"position: sticky; top: 0px; z-index: {STICKY_Z_HEADER}"
        with ui.column().classes("gap-0 gantt-sticky").style(header_style).mark("chart-header"):
            self.band_row(year_bands(columns), width, "year-band")
            if self.view_scale is not Scale.MONTH:
                self.band_row(month_bands(columns), width, "month-band")
            self.label_row(columns, width)
            self.event_rows(columns, width)

    def header_spacer(self, marker: str) -> None:
        """見出しの左端の空白。縦にも横にも固定された見出しの中で、横スクロールでも左に残る。"""
        spacer = ui.element("div").classes("gantt-sticky" + self.resize_classes())
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
            cells = "".join(
                header_cell_html(column, width, weekday=day)
                for column in columns
            )
            ui.html(f'<div style="display:flex">{cells}</div>', sanitize=False).style(
                "flex: none"
            ).mark("label-row-cells")

    def section_rows(
        self, path: SectionPath, section: Section, columns: list[Column], width: int, hidden: bool = False
    ) -> None:
        """セクションの見出し・タスク・サブセクション(再帰)を描く。hidden は、親のどれかが折りたたまれている。"""
        if self.task_filter.active and not section_has_match(section, self.task_filter, self.tasks_by_id):
            return
        key = section_key(path)
        collapsed = path in self.collapsed and not self.options.read_only
        effective = collapsed and not self.task_filter.active
        visible = visible_task_indexes(section, self.task_filter, collapsed, self.tasks_by_id)
        folded = self.folded_ids()
        view = self.section_views[path] = SectionView()
        indent = 12 * (len(path) - 1)
        header = ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE)
        parent_key = section_key(path[:-1])
        header.props(self.drag_props("section", key, count=len(section.tasks), parent=parent_key))
        header.mark(f"section-{key}")
        self.section_menu_on_right_click(header, path)
        header.set_visibility(not hidden)
        if not self.options.read_only:
            header.on("dblclick", lambda e, path=path: self.double_clicked_section(path, e.args), js_handler=QUICK_ADD_JS)
        view.header = header
        with header:
            name = ui.row().classes("items-center no-wrap gap-2 gantt-sticky" + self.resize_classes())
            name.style(  # 名前の列にちょうど収める(狭いと縞や格子線が見え、広いと棒を隠す)
                f"width: var(--name-w); overflow: hidden; align-self: stretch;"
                f" padding-left: {indent}px; {sticky_left(STICKY_Z_NAME)}"
            )
            if not self.options.read_only and not self.task_filter.active:  # つかんで動かせるのは、絞り込みなし・編集時だけ
                name.props(f"draggable=true data-section-handle data-si={key} data-parent={parent_key}")
            with name.mark(f"section-name-{key}"):
                if self.selecting:
                    self.selection_box(f"select-section-{key}", task_ids_of(section, self.tasks_by_id))
                if not self.options.read_only:
                    arrow = ARROW_COLLAPSED if collapsed else ARROW_EXPANDED
                    view.arrow = ui.button(
                        icon=arrow, on_click=lambda path=path: self.toggle_section(path)
                    ).props("flat dense round size=sm").classes("shrink-0").mark(f"section-toggle-{key}")
                label = ui.label(section.name).classes("text-subtitle2 ellipsis")
                label.style("min-width: 0; padding-left: 4px")  # 長い名前は縮めて、ボタンを残す
                label.tooltip(section.name).mark(f"section-label-{key}")
                if not self.options.read_only:
                    label.classes("cursor-pointer").on("click", lambda path=path: self.toggle_section(path))
                ui.label(f"({sum(1 for t in section.all_tasks() if t.kind is not TaskKind.SUMMARY)})").classes("text-caption shrink-0").mark(
                    f"section-count-{key}"
                )
                if not self.options.read_only and len(path) < MAX_SECTION_DEPTH:
                    ui.button(
                        icon="create_new_folder", on_click=lambda path=path: self.actions.add_subsection(path)
                    ).props("flat dense round size=sm").classes("shrink-0").tooltip("サブセクション追加").mark(
                        f"add-subsection-{key}"
                    )
                if not self.options.read_only:
                    ui.button(
                        icon="add_task", on_click=lambda path=path: self.actions.add_task(path)
                    ).props("flat dense round size=sm").classes("shrink-0").tooltip("タスク追加").mark(
                        f"add-task-{key}"
                    )
        shown = set(visible)
        self.quick_add_here(path, 0, hidden)
        for ti, task in enumerate(section.tasks):
            if self.task_filter.active and ti not in shown:
                continue  # 絞り込みで外れたタスクは、描かない
            row = self.task_row(path, ti, task, columns, width)
            row.set_visibility(not hidden and ti in shown and task.id not in folded)  # 折りたたみ中は、行を作って隠しておく(開くとき作り直さない)
            view.rows.append(row)
            self.quick_add_here(path, ti + 1, hidden)
        for index, child in enumerate(section.sections):
            child_path = (*path, index)
            self.section_rows(child_path, child, columns, width, hidden or effective)
            if child_path in self.section_views:
                view.children.append(child_path)
        self.quick_section_here(path, hidden)

    def task_row(
        self, path: SectionPath, ti: int, task: Task, columns: list[Column], width: int
    ) -> ui.element:
        key = section_key(path)
        style = ROW_STYLE
        now = self.now()
        overdue = is_overdue(task, self.project, self.holidays, now, self.schedule) and self.options.show_alerts
        state = progress_state(task, self.project, self.holidays, now, self.schedule)
        finished = state in (ProgressState.DONE, ProgressState.LATE_DONE)
        if task.kind is TaskKind.SUMMARY:  # 状態は子から算出する
            finished = summary_status(children_of(task, self.tasks_by_id), self.reference_values()) is Status.DONE
        warning = None
        if self.options.show_alerts and not overdue:  # 予定超過(赤)を優先する
            warning = warning_pace(task, self.project, self.holidays, now, self.schedule)
        if overdue:
            style += f"; background: {OVERDUE_COLOR}"
        elif warning is not None:
            style += f"; background: {WARNING_BACKGROUND}"
        ids = task_ids_of(task, self.tasks_by_id)
        if self.selecting and ids and all(i in self.options.excluded for i in ids):
            style += "; opacity: 0.4"  # 出力しない行は薄く描く
        row = ui.row().classes("items-center no-wrap gap-0").style(style)
        row.props(self.drag_props("row", key, ti=ti)).props(f"data-task-id={task.id}").mark(f"row-{key}-{ti}")
        if task.id in self.bulk.ids:
            row.classes("task-selected")
        self.menu_on_right_click(row, path, ti)
        self.task_rows[task.id] = row
        summary = task.kind is TaskKind.SUMMARY
        indent = SUMMARY_INDENT_PX if task.id in self.parents else 0  # まとめの子は、一段字下げする
        with row:
            cell = ui.row().classes(
                "items-center no-wrap gap-1 gantt-sticky"
                f" {PRIORITY_CLASSES[task.priority]}" + self.resize_classes()
            )
            cell_style = (
                f"width: var(--name-w); padding-left: {16 + 12 * max(len(path) - 1, 0) + indent}px; padding-right: 4px;"
                f" align-self: stretch; background-color: {PRIORITY_BACKGROUND_VAR};"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
            if overdue:  # 不透明な背景の上に、行と同じ赤みを重ねる
                cell_style += (
                    f"; background-image: linear-gradient({OVERDUE_COLOR}, {OVERDUE_COLOR})"
                )
            elif warning is not None:  # 警告の色も、同じ場所に重ねる
                cell_style += f"; background-image: linear-gradient({WARNING_BACKGROUND}, {WARNING_BACKGROUND})"
            cell.style(cell_style)
            cell.mark(f"task-{key}-{ti}")
            if not self.options.read_only:
                cell.on("dblclick", lambda e, path=path, ti=ti: self.double_clicked_task(path, ti, e.args), js_handler=QUICK_ADD_JS)
                cell.on("click", lambda e, tid=task.id: self.clicked_task(tid, e.args), js_handler=SELECT_CLICK_JS)
            if not self.task_filter.active and not self.options.read_only:
                cell.props(f"draggable=true data-drag-handle data-si={key} data-ti={ti}")
            with cell:
                if self.selecting:
                    self.selection_box(f"select-task-{key}-{ti}", ids)
                if summary and not self.options.read_only:
                    view = self.summary_views[task.id] = SummaryView()
                    folded = task.id in self.collapsed_summaries
                    view.arrow = (
                        ui.button(icon=ARROW_COLLAPSED if folded else ARROW_EXPANDED)
                        .on(
                            "click",
                            lambda tid=task.id: self.toggle_summary(tid),
                            js_handler="(e) => { e.stopPropagation(); emit(); }",
                        )
                        .props("flat dense round size=sm")
                        .classes("shrink-0")
                        .mark(f"summary-toggle-{key}-{ti}")
                    )
                name = ui.label(REFERENCE_MARK + task.name if task.kind is TaskKind.REFERENCE else task.name).classes("ellipsis").style(
                    f"flex: 1 1 0; min-width: 0; line-height: {ROW_HEIGHT_PX - 1}px"
                )
                if summary:
                    name.style("font-weight: 700")
                    if not self.options.read_only:  # 名前のクリックでも開閉する(行の編集は開かない)
                        name.style("flex: 0 1 auto").props("data-no-quick-add")  # 文字の右の余白を、ダブルクリックの対象にする
                        name.on(
                            "click",
                            lambda tid=task.id: self.toggle_summary(tid),
                            js_handler=PLAIN_CLICK_JS,
                        )
                if task.kind is TaskKind.REFERENCE and not self.options.read_only:
                    name.classes("ref-link").props("data-no-quick-add").tooltip(reference_open_hint(task))
                    name.on(
                        "click",
                        lambda tid=task.id: self.actions.open_reference(tid),
                        js_handler=PLAIN_CLICK_JS,
                    )
                if warning is not None:
                    name.tooltip(warning.hint())
                if finished:  # 終了したタスクは、名前に取り消し線を引く
                    name.style("text-decoration: line-through")
                name.mark(f"task-name-{key}-{ti}")
                if summary and not self.options.read_only:
                    self.summary_count(key, ti, task)
                    ui.element("div").style("flex: 1 1 0; align-self: stretch; min-width: 4px")  # チップを右に寄せる
                if self.options.show_chips:
                    self.task_chips(key, ti, task)
            if task.kind is TaskKind.CHECKPOINT:  # バーも実績もなく、◆ だけを出す
                self.checkpoint_marker(path, ti, task, columns, width)
                return row
            if summary:  # 棒の代わりに、子の期間を覆う細い帯を出す
                self.summary_band(path, key, ti, task, columns, width)
                return row
            if task.kind is TaskKind.REFERENCE:  # 参照先全体の帯だけ。自分の棒・実績は出さない(締切の目印だけ)
                self.reference_band(key, ti, task, columns, width)
                self.deadline_marker(path, ti, task, columns, width)
                return row
            if self.view_scale is Scale.DAY and (notes := member_notes(task, self.project, self.base_holidays)):
                self.work_day_strip(key, ti, notes, columns, width)
            start = self.schedule.start(task)
            end = self.schedule.bar_end(task)
            span = bar_span(start, end, columns)
            if span is not None and self.bar_visible(start, end, columns):
                left, length = span
                bar_width = max(length * width, MIN_BAR_PX)
                draggable = self.view_scale is Scale.DAY and not self.options.read_only
                cursor = "grab" if draggable else "default"
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
                bar.mark(f"bar-{key}-{ti}")
                if draggable:
                    least = arrange.min_shift_days(
                        task, self.project.base_date, start, self.schedule.latest_finish(task)
                    )
                    bar.props(
                        f"data-bar data-si={key} data-ti={ti} data-day-width={width}"
                        f" data-min-days={least}"
                    )
                with bar:
                    self.progress_fill(key, ti, task, columns, end)
                    if self.options.show_alerts:
                        self.overload_stripes(key, ti, task, left, bar_width, columns, width)
                    if self.options.show_chips and task.weekly_crew:
                        assert start is not None and end is not None
                        self.week_chips(key, path, ti, task, start, end, left, bar_width, columns, width)
                mark_left = self.marker_left(task, columns, width, left * width + bar_width)
                total = width * len(columns)
                if self.view_period is None or mark_left <= total - MARK_WIDTH_PX:
                    self.progress_marker(key, ti, task, state, mark_left, end)  # 期間の右端の外へは出さない
            self.actual_bars(path, ti, task, columns, width)
            self.deadline_marker(path, ti, task, columns, width)
        return row

    def task_chips(self, key: int | str, ti: int, task: Task) -> None:
        """名前の右の、カテゴリ(PRJコード、なければ名前)・担当・進捗。空のものは出さない。名前の欄の枠の中で呼ぶ。"""
        if task.kind is TaskKind.REFERENCE:
            self.reference_chips(key, ti, task)
            return
        category = self.category_lookup.get(task.category_id) if task.category_id else None
        if category is not None:
            ui.label(chip_text(category)).classes("ellipsis code-chip").style(CODE_CHIP_STYLE).tooltip(
                category.name
            ).mark(f"task-code-{key}-{ti}")
        begin = effective_start(task, self.project, self.holidays, self.schedule) if task.weekly_crew else None
        detail = week_summary(task, begin.date() if begin else None)  # Shift を押しながらのとき、週ごとの担当を出す
        for n, assignee in enumerate(task.assignees[:MAX_ASSIGNEE_CHIPS]):
            suffix = "" if n == 0 else f"-{n}"
            who = avatar(assignee.name, self.icon_lookup.get(assignee.name, ""), 16)
            shift_tooltip(who, f"{assignee.name} {round(assignee.allocation * 100)}%", detail)
            who.mark(f"task-assignee-{key}-{ti}{suffix}")
        rest = task.assignees[MAX_ASSIGNEE_CHIPS:]
        if rest:
            more = ui.label(f"+{len(rest)}").style(ASSIGNEE_CHIP_STYLE)
            shift_tooltip(more, "\n".join(f"{a.name} {round(a.allocation * 100)}%" for a in rest), detail)
            more.mark(f"task-assignee-more-{key}-{ti}")
        if task.kind is TaskKind.SUMMARY:
            percent = summary_progress(children_of(task, self.tasks_by_id), self.reference_values())
        else:
            percent = None if task.kind is TaskKind.CHECKPOINT else fill_percent(task)
        if percent is not None:
            ui.label(f"{percent}%").style(PROGRESS_TEXT_STYLE).mark(f"task-progress-{key}-{ti}")
        if task.urls and not self.options.read_only:
            self.link_icon(key, ti, task)

    def open_link(self, link: TaskUrl) -> None:
        try:
            self.open_url(resolve(link, self.project.url_templates))
        except (ValueError, OSError) as exc:
            ui.notify(str(exc), type="negative")

    def link_icon(self, key: int | str, ti: int, task: Task) -> None:
        """リンクのアイコン。1 件ならクリックで開き、複数ならメニューから選ぶ。名前の欄の枠の中で呼ぶ。"""

        def label(link: TaskUrl) -> str:
            if link.title:
                return link.title
            try:
                return resolve(link, self.project.url_templates)
            except ValueError:
                return link.values.get(URL_KEY) or link.values.get(ID_KEY) or ""

        icon = ui.icon("link", size="16px").classes("cursor-pointer").mark(f"task-link-{key}-{ti}")
        if len(task.urls) == 1:
            link = task.urls[0]
            icon.tooltip(label(link))
            icon.on("click", lambda _=None, link=link: self.open_link(link))
            return
        with icon, ui.menu().classes("app-context-menu"):
            for n, link in enumerate(task.urls):
                ui.menu_item(label(link), on_click=lambda link=link: self.open_link(link)).mark(
                    f"task-link-item-{key}-{ti}-{n}"
                )

    def summary_count(self, key: int | str, ti: int, task: Task) -> None:
        """折りたたみ中のまとめに添える、子の件数。開いているときは隠す。名前の欄の枠の中で呼ぶ。"""
        count = ui.label(f"{len(task.children)}件").classes("code-chip").style(CODE_CHIP_STYLE)
        count.mark(f"summary-count-{key}-{ti}")
        count.set_visibility(task.id in self.collapsed_summaries)
        self.summary_views[task.id].count = count

    def summary_band(
        self, path: SectionPath, key: str, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """まとめの細い帯。子の期間を覆い、状態の色で塗る。進捗は暗く塗り、両端に下向きの三角を付ける。"""
        start, end = self.schedule.start(task), self.schedule.end(task)
        span = bar_span(start, end, columns)
        if span is None or not self.bar_visible(start, end, columns):
            return
        left, length = span
        band_width = max(length * width, MIN_BAR_PX)
        kids = children_of(task, self.tasks_by_id)
        percent = summary_progress(kids, self.reference_values())
        band = ui.element("div").style(
            f"position: absolute; left: {from_name(left * width)}; width: {band_width:.1f}px;"
            f" top: {SUMMARY_BAND_TOP_PX}px; height: {SUMMARY_BAND_HEIGHT_PX}px;"
            f" background: {STATUS_COLOR_VAR}; border-radius: 1px"
        )
        band.classes(STATUS_CLASSES[summary_status(kids, self.reference_values())])
        band.mark(f"summary-band-{key}-{ti}")
        with band:
            if percent:
                ui.element("div").style(
                    f"position: absolute; left: 0; top: 0; bottom: 0; width: {percent}%;"
                    " background: rgba(0, 0, 0, 0.25); pointer-events: none"
                )
            for side in ("left", "right"):
                ui.element("div").style(
                    f"position: absolute; {side}: -{SUMMARY_TIP_PX}px; top: {SUMMARY_BAND_HEIGHT_PX}px;"
                    f" width: 0; height: 0; border-top: {SUMMARY_TIP_PX + 1}px solid {STATUS_COLOR_VAR};"
                    f" border-left: {SUMMARY_TIP_PX}px solid transparent;"
                    f" border-right: {SUMMARY_TIP_PX}px solid transparent; pointer-events: none"
                )

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
        start = self.schedule.start(task)
        if self.view_period is None or start is None or end is None or end <= start:
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
            start = self.schedule.start(task)
            if start is not None and end is not None:
                expected = expected_progress(start, end, self.now())
                tip = f"{state.value}(進捗 {percent}% / 予定 {expected:.0f}%)"
        ui.label(PROGRESS_STATE_MARKS[state]).style(
            f"position: absolute; left: {from_name(mark_left)}; top: {BAR_TOP_PX}px;"
            f" line-height: {BAR_HEIGHT_PX}px; font-size: 11px; color: var(--pstate)"
        ).classes(PROGRESS_STATE_CLASSES[state]).tooltip(tip).mark(f"progress-state-{key}-{ti}")

    def actual_bars(
        self,
        path: SectionPath,
        ti: int,
        task: Task,
        columns: list[Column],
        width: int,
    ) -> None:
        """実績の棒。予定の棒の下半分に、不透明で重ねる。進行中は現在時刻まで。ドラッグはできない。色は状態の色。"""
        key = section_key(path)
        for n, actual in enumerate(task.actuals):
            finish = actual.end if actual.end is not None else self.now()
            if not self.bar_visible(actual.start, finish, columns):
                continue
            left, length = interval_span(actual.start, finish, columns)
            bar = ui.element("div").style(
                f"position: absolute; left: {from_name(left * width)};"
                f" width: {max(length * width, MIN_BAR_PX):.1f}px;"
                f" top: {ACTUAL_TOP_PX}px; height: {ACTUAL_HEIGHT_PX}px;"
                f" background: {STATUS_COLOR_VAR}; border-radius: 3px;"
                " user-select: none; overflow: hidden"
            ).classes(STATUS_CLASSES[task.status])
            bar.mark(f"actual-{key}-{ti}-{n}")
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
                f" background: {ACTUAL_GAP_BACKGROUND}; user-select: none"
            ).classes(STATUS_CLASSES[task.status])
            gap.mark(f"actual-gap-{key}-{ti}-{n}")

    def week_chips(
        self,
        key: int | str,
        path: SectionPath,
        ti: int,
        task: Task,
        start: datetime,
        end: datetime,
        bar_left: float,
        bar_width: float,
        columns: list[Column],
        width: int,
    ) -> None:
        """棒の上に、週ごと(実効の開始の日から 7 日ごと)の担当のチップを重ねる。2 つ目からは左端に区切り線を付ける。"""
        defined = len(task.weekly_crew)
        n = 0
        while (left := start if n == 0 else datetime.combine(start.date() + timedelta(days=7 * n), time.min)) < end:
            # 定義した週より後も、7 日ごとに区切る(担当は最後の週のものが続く。タップすると、その週まで足して直せる)
            right = min(datetime.combine(start.date() + timedelta(days=7 * (n + 1)), time.min), end)
            crew = task.weekly_crew[min(n, defined - 1)]
            n += 1
            index = n - 1
            origin, length = interval_span(left, right, columns)
            left_px = max((origin - bar_left) * width, 0.0)
            width_px = min(length * width, bar_width - left_px)
            if width_px <= 0:
                continue
            divider = " border-left: 1px solid rgba(255,255,255,0.8);" if index else ""
            text = week_chip_text([a.name for a in crew], width_px, self.view_scale)
            shown = crew[:MAX_ASSIGNEE_CHIPS]
            with_icons = bool(text) and any(self.icon_lookup.get(a.name) for a in shown)
            chip = ui.label("" if with_icons else text).style(
                f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px; top: 0;"
                f" height: {WEEK_CHIP_HEIGHT_PX}px; font-size: 10px; line-height: {WEEK_CHIP_HEIGHT_PX}px;"
                f" color: #fff; background: rgba(0,0,0,0.3); padding-left: 3px; overflow: hidden;"
                f" white-space: nowrap; z-index: 1; text-shadow: {WEEK_CHIP_TEXT_SHADOW};{divider}"
            )
            # 見出し(第N週 と期間)を 1 行にまとめ、担当、負荷の順に並べる。期間は見出しにあるので、負荷には付けない
            last_day = (right - timedelta(microseconds=1)).date()
            if with_icons:
                # アイコンのある人は小さな丸い画像、ない人は頭文字(幅に合わせて、4 人目以降は +n)
                chip.style("display: flex; align-items: center; gap: 2px")
                with chip:
                    for a in shown:
                        if self.icon_lookup.get(a.name):
                            avatar(a.name, self.icon_lookup[a.name], WEEK_CHIP_ICON_PX)
                        else:
                            ui.label(a.name[:1])
                    if (rest := len(crew) - len(shown)) > 0:
                        ui.label(f"+{rest}")
            carried = f"(第{defined}週の担当が続く)" if index >= defined else ""
            title = f"第{index + 1}週 {short_date(left.date())}〜{short_date(last_day)}{carried}\n{crew_text(crew)}"
            if load := self.overload_text(task, (left, right)) if self.options.show_alerts else "":
                title += f"\n⚠ {load}"
            chip.tooltip(title).mark(f"week-chip-{key}-{ti}-{index}")
            if not self.options.read_only:
                chip.style("cursor: pointer").on("click", lambda _e, week=index: self.actions.edit_week_crew(path, ti, week))

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
        clipped = clip_overloads(task, self.project, self.holidays, self.overloads, self.schedule)
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
        if text := self.overload_text(task):
            if self.options.show_chips and task.weekly_crew:
                # 週のチップは棒の上端を覆う。棒そのものにマウスオーバーを付けると、チップの上で 2 つのヒントが重なるので、
                # チップの行より下の領域にだけ付ける(チップのヒントには負荷の説明を足す)
                with ui.element("div").style(
                    f"position: absolute; left: 0; right: 0; top: {WEEK_CHIP_HEIGHT_PX}px; bottom: 0"
                ).mark(f"overload-tip-{key}-{ti}"):
                    ui.tooltip(text)
            else:
                ui.tooltip(text)

    def overload_text(self, task: Task, within: tuple[datetime, datetime] | None = None) -> str:
        """割り当て超過の説明(担当者ごとに最大の率と期間)。3 人ごとに改行し、2 行目からは全角空白で字下げする。超過がなければ空。

        within(週のチップ用)を渡すと、その期間にかかる超過だけを数え、期間は見出しにあるので付けない。
        """
        clipped = clip_overloads(task, self.project, self.holidays, self.overloads, self.schedule)
        if within is not None:
            clipped = [o for o in clipped if o.start < within[1] and o.end > within[0]]
        lines: list[str] = []
        for member in dict.fromkeys(o.member for o in clipped):
            mine = [o for o in clipped if o.member == member]
            peak = round(max(o.total for o in mine) * 100)
            span = "" if within else f"({short_date(min(o.start for o in mine).date())}〜{short_date(max(o.end for o in mine).date())})"
            lines.append(f"{member} 最大{peak}%{span}")
        per_line = HOVER_NAMES_PER_LINE
        return "\n　".join(" / ".join(lines[i : i + per_line]) for i in range(0, len(lines), per_line))

    def reference_chips(self, key: int | str, ti: int, task: Task) -> None:
        """参照行の、名前の右のチップ: 遅延の件数・負荷のピーク・進捗・見つからない理由。名前の欄の枠の中で呼ぶ。"""
        ref = self.refs.get(task.id)
        if ref is None:
            return
        if ref.problem and ref.value is None:
            ui.label("(参照先が見つかりません)").classes("text-caption text-grey").tooltip(ref.problem).mark(
                f"ref-missing-{key}-{ti}"
            )
            return
        value = ref.value
        if value is None:
            return
        if self.options.show_alerts and value.delayed:
            ui.label(f"遅延 {value.delayed}件").style(REFERENCE_CHIP_STYLE + f" background: {OVERDUE_COLOR_SOLID};").mark(
                f"ref-delay-{key}-{ti}"
            )
        if self.options.show_alerts and value.warned:
            ui.label(f"警告 {value.warned}件").style(
                REFERENCE_CHIP_STYLE + " background: var(--warning); color: #212121;"
            ).mark(f"ref-warning-{key}-{ti}")
        if self.options.show_alerts and value.peak_load > 1.0:
            ui.label(f"負荷 {round(value.peak_load * 100)}%").style(REFERENCE_CHIP_STYLE).mark(f"ref-load-{key}-{ti}")
        if value.progress is not None:
            ui.label(f"{value.progress}%").style(PROGRESS_TEXT_STYLE).mark(f"task-progress-{key}-{ti}")

    def reference_text(self, task: Task, ref: Reference) -> str:
        """参照行の帯のマウスオーバー(細かなタスクは出さない)。"""
        value = ref.value
        assert value is not None
        lines = [task.name]
        if value.planned_start is not None and value.planned_end is not None:
            lines[0] += f" {short_date(value.planned_start.date())}〜{short_date(value.planned_end.date())}"
        if value.actual_start is not None:
            tail = short_date(value.actual_end.date()) if value.actual_end is not None else ""
            lines.append(f"実績 {short_date(value.actual_start.date())}〜{tail}")
        lines.append(f"遅延 {value.delayed} 件")
        lines.append(f"警告 {value.warned} 件")
        lines.append(
            f"ピーク負荷 {round(value.peak_load * 100)}%({value.peak_member})" if value.peak_load > 1.0 else "負荷の超過なし"
        )
        if ref.source is ReferenceMode.SNAPSHOT and value.taken_at is not None:
            lines.append(f"スナップショット {short_date(value.taken_at.date())}" + (" (古い)" if ref.stale else ""))
        if ref.problem:
            lines.append(ref.problem)
        if not self.options.read_only:
            lines.append(reference_open_hint(task))
        return "\n".join(lines)

    def reference_band(self, key: int | str, ti: int, task: Task, columns: list[Column], width: int) -> None:
        """参照先全体の予定の帯(進捗の塗りと、超過期間の縞)。参照値がなければ出さない。"""
        ref = self.refs.get(task.id)
        start, end = self.schedule.start(task), self.schedule.end(task)
        span = bar_span(start, end, columns)
        if ref is None or ref.value is None or span is None or not self.bar_visible(start, end, columns):
            return
        left, length = span
        bar_width = max(length * width, MIN_BAR_PX)
        late = self.options.show_alerts and ref.value.delayed > 0
        bar = ui.element("div").style(
            f"position: absolute; left: {from_name(left * width)}; width: {bar_width:.1f}px; top: {BAR_TOP_PX}px;"
            f" height: {BAR_HEIGHT_PX}px; background: {planned_background(task.color if not late else RED_BAR_COLOR)};"
            " border-radius: 4px; overflow: hidden; user-select: none"
        )
        bar.mark(f"bar-{key}-{ti}")
        if not self.options.read_only:
            bar.classes("ref-link").on(
                "click",
                lambda tid=task.id: self.actions.open_reference(tid),
                js_handler="(e) => { e.stopPropagation(); emit(); }",
            )
        bar.tooltip(self.reference_text(task, ref))
        with bar:
            if ref.value.progress:
                ui.element("div").style(
                    f"position: absolute; left: 0; top: 0; bottom: 0; width: {ref.value.progress}%;"
                    f" background: {task.color}; opacity: 0.6; pointer-events: none"
                )
            if self.options.show_alerts:
                for n, over in enumerate(ref.value.overloads):
                    origin, length_cols = interval_span(over.start, over.end, columns)
                    left_px = max((origin - left) * width, 0.0)
                    width_px = min(length_cols * width, bar_width - left_px)
                    if width_px > 0:
                        ui.element("div").style(
                            f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px; top: 0; bottom: 0;"
                            f" background: {OVERLOAD_STRIPES}; pointer-events: none"
                        ).mark(f"overload-{key}-{ti}-{n}")

    def checkpoint_marker(
        self, path: SectionPath, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """チェックポイントの ◆。締切の位置・行の中央。表示範囲の外なら出さない。"""
        if task.deadline is None:
            return
        position = deadline_position(task.deadline, columns)
        if position is None:
            return
        key = section_key(path)
        left = position * width - CHECKPOINT_MARKER_PX / 2
        marker = ui.label("◆").style(
            f"position: absolute; left: {from_name(left)}; top: 0; width: {CHECKPOINT_MARKER_PX}px;"
            f" height: {ROW_HEIGHT_PX}px; line-height: {ROW_HEIGHT_PX}px; text-align: center;"
            f" font-size: {CHECKPOINT_MARKER_PX}px; color: {STATUS_COLOR_VAR};"
            " user-select: none"
        ).classes(STATUS_CLASSES[task.status])
        marker.tooltip(f"チェックポイント {task.deadline:%Y-%m-%d %H:%M}").mark(
            f"checkpoint-{key}-{ti}"
        )

    def deadline_marker(
        self, path: SectionPath, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """締切がある行に、締切の位置へ「◆」を出す。表示範囲の外なら出さない。"""
        if task.deadline is None:
            return
        position = deadline_position(task.deadline, columns)
        if position is None:
            return
        key = section_key(path)
        left = position * width - DEADLINE_MARKER_HALF_PX
        marker = ui.label("◆").style(
            f"position: absolute; left: {from_name(left)}; top: 4px; line-height: 1;"
            f" color: {DEADLINE_COLOR}"
        )
        marker.tooltip(f"締切 {task.deadline:%Y-%m-%d %H:%M}").mark(f"deadline-{key}-{ti}")
