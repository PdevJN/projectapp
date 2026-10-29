"""タスク・セクションの追加・編集の入力検証と、ファイル・名前・設定のダイアログ。"""

from collections.abc import Awaitable, Callable, Collection, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from decimal import Decimal
from math import isfinite
from typing import Any

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.dateinput import parse_date_input, parse_time_input
from projectapp.avatar import avatar
from projectapp.events import color_hex, normalize_color, sort_events, validate_events
from projectapp.icons import is_valid_icon
from projectapp.categories import (
    COLOR_HEX,
    COLOR_LABELS,
    COLORS,
    UNDECIDED,
    CategoryEdit,
    next_color,
    parse_expiry,
    validate_categories,
)
from projectapp.gitops import FileChange
from projectapp.merge import DELETED, OURS, THEIRS, Choices, Conflict, format_value
from projectapp.models import (
    CHECKPOINT_STATUSES,
    ID_KEY,
    MAX_ALLOCATION,
    MAX_CATEGORY_KIND_LENGTH,
    MAX_CATEGORY_NAME_LENGTH,
    MAX_EVENT_TEXT_LENGTH,
    Event,
    DEFAULT_RATIO_MAX,
    DEFAULT_RATIO_MIN,
    MAX_LEVEL_VALUE,
    MAX_PROGRESS,
    MAX_PROJECT_CODE_LENGTH,
    MAX_RATIO,
    MAX_TASK_NAME_LENGTH,
    MAX_YEAR,
    MIN_ALLOCATION,
    MIN_LEVEL_VALUE,
    MIN_PROGRESS,
    MIN_RATIO,
    MIN_YEAR,
    URL_KEY,
    Actual,
    Assignee,
    ActualMode,
    Category,
    Level,
    Member,
    Membership,
    Parameter,
    Team,
    ReferenceMode,
    Priority,
    RatioLimits,
    Status,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
    WorkDay,
    has_control_char,
    is_hex_color,
    new_id,
    union_assignees,
)
from projectapp.periodfield import add_range_picker, normalize_period, split_period, validate_period
from projectapp.workdays import MAX_NOTE, expand_range, sort_work_days, validate_work_days
from projectapp.teams import membership_error, membership_summary, normalize
from projectapp.teams_dialog import open_member_teams_dialog, teams_panel
from projectapp.ratios import ParameterEdit, limit_note, ratio_detail, remap_levels, validate_parameters
from projectapp.urls import TemplateEdit, resolve, validate_templates

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"
STANDARD_WORK_HOURS = 8  # 時刻を指定しないときに補う終了の、標準稼働時間(固定)
LUNCH_HOURS = 1  # 同じく、昼休憩(固定。稼働設定の対象外)
MIN_DAILY_HOURS, MAX_DAILY_HOURS = 1.0, 8.0  # 稼働可能時間の範囲
HOURS_RANGE_MESSAGE = f"稼働可能時間は{MIN_DAILY_HOURS:g}以上{MAX_DAILY_HOURS:g}以下で入力してください"
HOURS_DECIMALS = 2  # 稼働時間の小数点以下の桁数(0.25=15分刻みを含む)


def disposable(dialog: ui.dialog) -> ui.dialog:
    """閉じたら要素ごと取り除く。開くたびに新しく作るダイアログが、閉じても溜まらないようにする。"""
    dialog.on("hide", dialog.delete)
    return dialog


def bind_picker(picker: ui.date | ui.time, field: ui.input, fmt: str) -> None:
    """入力欄と選択部品の値をそろえる。入力途中の(形式に合わない)文字列は部品に渡さない。"""

    def valid_or_none(text: str | None) -> str | None:
        try:
            datetime.strptime(text or "", fmt)
        except ValueError:
            return None
        return text

    picker.bind_value_from(field, backward=valid_or_none)
    picker.bind_value_to(field, forward=lambda value: value if value else field.value)


def parse_datetime(text: str) -> datetime | None:
    """datetime-local形式を解析する。空はNone、不正・タイムゾーン付きはValueError。"""
    text = text.strip()
    if not text:
        return None
    value = datetime.fromisoformat(text)
    if value.tzinfo is not None:
        raise ValueError("タイムゾーン付きの日時は扱えません")
    return value


def end_gap_hint(manual: datetime | None, computed: datetime | None) -> str:
    """手で指定した完了予定が、工数からの算出値と何日ずれているかの 1 行のヒント(暦日の差。どちらかがなければ空)。"""
    if manual is None or computed is None:
        return ""
    days = (manual.date() - computed.date()).days
    if days > 0:
        return f"算出値より {days} 日遅い"
    if days < 0:
        return f"算出値より {-days} 日前倒し"
    return "算出値と同じ日"


def _parse_planned_end(text: str, *, strict: bool, fallback: datetime | None) -> datetime | None:
    """完了予定の入力を解析する。使われない値(工数ありで手指定なし)は、不正でも保存を妨げず、
    形式や年が不正なら前の値を保つ。"""
    try:
        value = parse_datetime(text)
    except ValueError:
        if strict:
            raise
        return fallback
    if not strict and value and not MIN_YEAR <= value.year <= MAX_YEAR:
        return fallback
    return value


def push_hint(start: datetime | None, finishes: list[datetime]) -> str:
    """先行の完了が開始より後のときの、1 行のヒント。押し出されていなければ空。"""
    if not finishes:
        return ""
    latest = max(finishes)
    if start is not None and latest <= start:
        return ""
    return f"先行の完了により、実際の開始は {latest:%m/%d %H:%M} です"


def _links(
    base: Task, predecessors: list[str] | None, linkable_ids: frozenset[str] | None
) -> list[str]:
    """先行タスクの入力を検証する。None は既存のまま。重複は除く(順序は保つ)。"""
    links = list(base.predecessors) if predecessors is None else list(dict.fromkeys(predecessors))
    if predecessors is not None and (
        base.id in links or (linkable_ids is not None and not set(links) <= linkable_ids)
    ):
        raise ValueError("先行タスクが正しくありません")
    return links


def _build_reference(
    base: Task,
    name: str,
    ref_project: str,
    deadline: str,
    color: str,
    predecessors: list[str] | None,
    linkable_ids: frozenset[str] | None,
) -> Task:
    """プロジェクト参照。参照先・締切(任意)・色・先行だけを検証し、使わない項目は空にする(隠した欄の入力は見ない)。
    参照先を変えたときは、保存したスナップショットを捨てる。"""
    if not ref_project.strip():
        raise ValueError("参照先のプロジェクトを選んでください")
    try:
        deadline_at = parse_datetime(deadline)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    if deadline_at is not None and not MIN_YEAR <= deadline_at.year <= MAX_YEAR:
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    return replace(
        base,
        kind=TaskKind.REFERENCE,
        name=name,
        ref_project=ref_project,
        ref_snapshot=base.ref_snapshot if base.ref_project == ref_project else None,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=deadline_at,
        effort_hours=0.0,
        priority=Priority.MEDIUM,
        status=Status.NOT_STARTED,
        color=color,
        assignees=[],
        weekly_crew=[],
        actuals=[],
        progress=None,
        parameters=[],
        category_id=None,
        urls=[],
        predecessors=_links(base, predecessors, linkable_ids),
    )


def _build_checkpoint(
    base: Task,
    name: str,
    category_id: str | None,
    deadline: str,
    priority: Priority,
    status: Status,
    color: str,
    predecessors: list[str] | None,
    linkable_ids: frozenset[str] | None,
    urls: list[TaskUrl] | None,
) -> Task:
    """チェックポイント。締切だけを検証し、開始予定・工数・担当・実績・進捗度は空にする(隠した欄の入力は見ない)。"""
    try:
        deadline_at = parse_datetime(deadline)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    if deadline_at is None:
        raise ValueError("チェックポイントには締切を入れてください")
    if not MIN_YEAR <= deadline_at.year <= MAX_YEAR:
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if status not in CHECKPOINT_STATUSES:
        raise ValueError("チェックポイントの状態は、未着手か終了にしてください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    return replace(
        base,
        kind=TaskKind.CHECKPOINT,
        name=name,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=deadline_at,
        effort_hours=0.0,
        priority=priority,
        status=status,
        color=color,
        assignees=[],
        weekly_crew=[],
        actuals=[],
        progress=None,
        parameters=[],
        category_id=category_id,
        predecessors=_links(base, predecessors, linkable_ids),
        urls=base.urls if urls is None else urls,
    )


UrlRow = tuple[str, str | None, str]  # リンク 1 行の入力: 表示名、テンプレート名(None はなし)、値(URL か ID)


def build_urls(rows: list[UrlRow], templates: list[UrlTemplate]) -> list[TaskUrl]:
    """リンクの入力を検証して TaskUrl にする。完全に空の行は無視し、不完全な行は行番号つきの ValueError。"""
    urls: list[TaskUrl] = []
    for number, (title, template, value) in enumerate(rows, start=1):
        title, value = title.strip(), value.strip()
        if not title and not value and template is None:
            continue
        link = TaskUrl(title, template, {URL_KEY if template is None else ID_KEY: value})
        try:
            resolve(link, templates)
        except ValueError as exc:
            raise ValueError(f"リンク{number}行目: {exc}") from None
        urls.append(link)
    return urls


ActualRow = tuple[str, str]  # 区間の1行の入力(開始・終了の文字列)


def _build_assignees(rows: list[tuple[str, float | None]]) -> list[Assignee]:
    """担当者の行を検証して Assignee にする。メンバーを選んでいない行は捨てる。"""
    result: list[Assignee] = []
    seen: set[str] = set()
    for raw_name, percent in rows:
        name = raw_name.strip()
        if not name:
            continue
        if name in seen:
            raise ValueError(f"担当者が重複しています: {name}")
        seen.add(name)
        if (
            percent is None
            or not isfinite(percent)
            or not MIN_ALLOCATION * 100 <= percent <= MAX_ALLOCATION * 100
        ):
            raise ValueError(
                f"割り当て率は{MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}%で入力してください"
            )
        result.append(Assignee(name, round(percent / 100, 4)))
    return result


def task_name_error(clean: str) -> str | None:
    """タスク名(前後の空白を除いたもの)の不正な理由。問題なければ None。"""
    if not clean:
        return "名前を入力してください"
    if len(clean) > MAX_TASK_NAME_LENGTH:
        return f"名前は{MAX_TASK_NAME_LENGTH}文字以内で入力してください"
    if has_control_char(clean):
        return "名前に改行・制御文字は使えません"
    return None


def build_task(
    existing: Task | None,
    *,
    name: str,
    planned_start: str,
    planned_end: str,
    planned_end_manual: bool = False,
    deadline: str,
    effort_hours: float | None,
    priority: Priority,
    status: Status,
    color: str,
    actual_start: str = "",
    actual_end: str = "",
    actual_rows: list[ActualRow] | None = None,
    progress: float | None = None,
    category_id: str | None = None,
    predecessors: list[str] | None = None,
    linkable_ids: frozenset[str] | None = None,
    kind: TaskKind = TaskKind.NORMAL,
    urls: list[TaskUrl] | None = None,
    assignees: list[tuple[str, float | None]] | None = None,
    parameters: list[str] | None = None,
    ref_project: str = "",
) -> Task:
    """入力値からTaskを作る。編集時はフォームにない項目(週ごとの担当を含む)を引き継ぐ。`progress` はタスクの進捗度。"""
    clean = name.strip()
    if (message := task_name_error(clean)) is not None:
        raise ValueError(message)
    base = existing or Task(clean)
    if kind is TaskKind.SUMMARY:  # まとめは分解でだけ作る。編集では、共通の項目(名前・カテゴリ・優先度・リンク)だけを変える
        if existing is None or existing.kind is not TaskKind.SUMMARY:
            raise ValueError("まとめは分解でだけ作れます")
        return replace(
            existing,
            name=clean,
            category_id=category_id,
            priority=priority,
            urls=existing.urls if urls is None else urls,
        )
    if kind is TaskKind.CHECKPOINT:
        return _build_checkpoint(
            base, clean, category_id, deadline, priority, status, color, predecessors, linkable_ids, urls
        )
    if kind is TaskKind.REFERENCE:
        return _build_reference(base, clean, ref_project, deadline, color, predecessors, linkable_ids)
    hours = effort_hours or 0.0
    manual = planned_end_manual and hours > 0
    uses_planned_end = hours <= 0 or manual
    try:
        start_at, deadline_at = parse_datetime(planned_start), parse_datetime(deadline)
        end_at = _parse_planned_end(planned_end, strict=uses_planned_end, fallback=base.planned_end)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    for moment in (start_at, deadline_at, end_at if uses_planned_end else None):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if not isfinite(hours) or hours < 0:
        raise ValueError("工数は0以上の数値で入力してください")
    if exceeds_decimals(hours) and hours != base.effort_hours:  # 古いファイルの値は、触らなければ保存できる
        raise ValueError(f"工数は小数点以下{HOURS_DECIMALS}桁までで入力してください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    if uses_planned_end and start_at and end_at and end_at < start_at:
        raise ValueError("完了予定は開始予定以降の日時にしてください")
    assignee_list = _build_assignees(assignees or [])
    weeks = [list(week) for week in base.weekly_crew]  # 週ごとの担当はダイアログでは直さない(棒のチップで直す)
    if actual_rows is not None:
        actuals = build_actual_intervals(actual_rows)
    elif len(base.actuals) > 1:
        actuals = base.actuals
    else:
        actuals = build_actuals(actual_start, actual_end)
    links = _links(base, predecessors, linkable_ids)
    task_progress = _check_progress(progress)
    return replace(
        base,
        kind=TaskKind.NORMAL,
        name=clean,
        planned_start=start_at,
        planned_end=end_at,
        planned_end_manual=manual,
        deadline=deadline_at,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignees=union_assignees(weeks) if weeks else assignee_list,
        weekly_crew=weeks,
        actuals=actuals,
        progress=task_progress,
        category_id=category_id,
        predecessors=links,
        urls=base.urls if urls is None else urls,
        parameters=list(dict.fromkeys(base.parameters if parameters is None else parameters)),
    )


def build_actuals(start_text: str, end_text: str) -> list[Actual]:
    """実績の入力(compose_actual の結果)を検証して、0件か1件の区間にする。"""
    try:
        start_at, end_at = parse_datetime(start_text), parse_datetime(end_text)
    except ValueError:
        raise ValueError("実績の日時の形式が正しくありません") from None
    if start_at is None:
        if end_at is not None:
            raise ValueError("実績の開始を入れてください")
        return []
    for moment in (start_at, end_at):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if end_at is not None and end_at < start_at:
        raise ValueError("実績の終了は開始以降の日時にしてください")
    return [Actual(start_at, end_at)]


def build_actual_intervals(rows: list[ActualRow]) -> list[Actual]:
    """区間の行の入力を検証して、区間のリストにする。すべて空の行は無視する(行番号は数える)。
    開始の昇順、重ならない、終了のない区間は最後の1つだけ。"""
    kept: list[tuple[int, Actual]] = []
    for number, (start_text, end_text) in enumerate(rows, start=1):
        if not start_text and not end_text:
            continue
        try:
            built = build_actuals(start_text, end_text)
        except ValueError as exc:
            raise ValueError(f"区間 {number}: {exc}") from None
        kept.append((number, built[0]))
    previous: tuple[int, Actual] | None = None
    for number, actual in kept:
        if previous is not None:
            before_number, before = previous
            if before.end is None:
                raise ValueError(f"区間 {before_number}: 終了のない区間は最後の1つだけにしてください")
            if actual.start < before.start:
                raise ValueError("区間は開始の早い順に入れてください")
            if actual.start < before.end:
                raise ValueError(f"区間 {number}: 前の区間と重なっています")
        previous = (number, actual)
    return [actual for _, actual in kept]


def _check_progress(value: float | None) -> int | None:
    """進捗度の入力を検証する。空は None。0〜100の整数だけを通す。"""
    if value is None:
        return None
    if not isfinite(value) or value != int(value) or not MIN_PROGRESS <= value <= MAX_PROGRESS:
        raise ValueError(f"進捗度は{MIN_PROGRESS}〜{MAX_PROGRESS}の整数で入力してください")
    return int(value)


def in_hours_range(hours: float) -> bool:
    return MIN_DAILY_HOURS <= hours <= MAX_DAILY_HOURS


def exceeds_decimals(hours: float) -> bool:
    """小数点以下がHOURS_DECIMALS桁を超えるか。入力どおりの10進数で桁数を数える。"""
    exact = Decimal(repr(hours))
    return exact != exact.quantize(Decimal(1).scaleb(-HOURS_DECIMALS))


def build_work_settings(hours: float | None, start: str) -> tuple[float, time]:
    """稼働可能時間と始業時刻の入力を検証する。"""
    if hours is None:
        raise ValueError("稼働可能時間を入力してください")
    if not isfinite(hours) or not in_hours_range(hours):
        raise ValueError(HOURS_RANGE_MESSAGE)
    if exceeds_decimals(hours):
        raise ValueError(f"稼働可能時間は小数点以下{HOURS_DECIMALS}桁までで入力してください")
    try:
        work_start = datetime.strptime(start.strip(), "%H:%M").time()
    except ValueError:
        raise ValueError("始業時刻はHH:MMの形式で入力してください") from None
    minutes = work_start.hour * 60 + work_start.minute + hours * 60
    if minutes > 24 * 60 + 1e-9:  # 稼働枠が日をまたぐと算出が曖昧になる
        raise ValueError("始業時刻と稼働可能時間の合計が24時を超えています")
    return hours, work_start


def ratio_range_text(limits: RatioLimits | None) -> str:
    """相対比率を丸める範囲の表示(例: 50〜150%)。設定のない側は既定の 50〜150%。"""
    lower = DEFAULT_RATIO_MIN if limits is None or limits.lower is None else limits.lower
    upper = DEFAULT_RATIO_MAX if limits is None or limits.upper is None else limits.upper
    return f"{lower * 100:g}〜{upper * 100:g}%"


def build_ratio_limits(upper_text: str, lower_text: str) -> RatioLimits:
    """相対比率の上限・下限(%)の入力を検証する。空欄は設定なし(既定の 50〜150%)。下限は上限以下。"""

    def read(text: str, name: str) -> float | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = float(text) / 100
        except ValueError:
            raise ValueError(f"{name}は数値で入力してください") from None
        if not isfinite(value) or not DEFAULT_RATIO_MIN - 1e-9 <= value <= DEFAULT_RATIO_MAX + 1e-9:
            raise ValueError(f"{name}は{DEFAULT_RATIO_MIN * 100:g}〜{DEFAULT_RATIO_MAX * 100:g}%で入力してください")
        return round(value, 4)

    limits = RatioLimits(read(upper_text, "相対比率の上限"), read(lower_text, "相対比率の下限"))
    if limits.upper is not None and limits.lower is not None and limits.lower > limits.upper:
        raise ValueError("相対比率の下限は上限以下にしてください")
    return limits


def build_base_date(text: str, today: date) -> date:
    """基準日(プロジェクト開始日)の入力を検証する。過去の日も、タスクより後ろの日も許可する。"""
    parsed = parse_date_input(text, today, roll_forward=False)
    if parsed is None:
        raise ValueError("基準日を日付で入力してください(例: 2026-10-05、10/05)")
    day = date.fromisoformat(parsed)
    if not MIN_YEAR <= day.year <= MAX_YEAR:
        raise ValueError(f"基準日の年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    return day


@dataclass
class TemplateRow:
    """設定ダイアログの URL テンプレートの 1 行。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    pattern: str


@dataclass
class CategoryRow:
    """設定ダイアログのカテゴリの 1 行。originalは、開いた時点のカテゴリの id(新しい行はNone)。"""

    original: str | None
    name: str
    kind: str
    expiry: str  # YYYY-MM-DD か空
    color: str
    prj_code: str


@dataclass
class EventRow:
    """設定ダイアログのイベントの 1 行。originalは、開いた時点のイベントの id(新しい行はNone)。"""

    original: str | None
    start: str  # YYYY-MM-DD か、省略形(10/20・1020・20261020)
    end: str
    text: str
    color: str  # 色名
    closed: bool = False  # 期間の稼働日を全員の休みにする


def build_event_list(rows: list[EventRow], taken: Collection[str], today: date) -> list[Event]:
    """入力の行を検証して、並べ替えたイベントの一覧にする。完全に空の新しい行は無視する。新しい行には、既存の id と重ならない id を振る。"""
    used = set(taken)
    built: list[Event] = []
    for row in rows:
        if row.original is None and not any(t.strip() for t in (row.start, row.end, row.text)):
            continue
        days = []
        for text, label in ((row.start, "開始日"), (row.end, "終了日")):
            parsed = parse_date_input(text, today, roll_forward=False)
            if parsed is None:
                raise ValueError(f"イベントの{label}を日付で入力してください(例: 2026-10-20、10/20)")
            days.append(date.fromisoformat(parsed))
        color = normalize_color(row.color)
        if color is None:
            raise ValueError(f"イベントの色が正しくありません: {row.color.strip()!r}(red・orange・gray などの色名)")
        event_id = row.original or new_id(used)
        used.add(event_id)
        built.append(Event(days[0], days[1], row.text.strip(), color, event_id, closed=row.closed))
    validate_events(built)
    return sort_events(built)


def event_key(e: Event) -> tuple:
    return (e.id, e.start, e.end, e.text, e.color, e.closed)


@dataclass
class WorkDayRow:
    day: str
    start: str
    end: str
    rest: bool
    note: str = ""


def build_work_day_list(rows: list[WorkDayRow], today: date) -> list[WorkDay]:
    """入力の行を検証して、日付の昇順の一覧にする。完全に空の行は無視する(メモだけの行は日付のエラー)。休みの行は時刻を見ない。"""
    built: list[WorkDay] = []
    for row in rows:
        if not row.rest and not any(t.strip() for t in (row.day, row.start, row.end, row.note)):
            continue
        day = parse_date_input(row.day, today, roll_forward=False)
        if day is None:
            raise ValueError("稼働日の日付を入力してください(例: 2026-10-17、10/17)")
        note = row.note.strip()
        if row.rest:
            built.append(WorkDay(date.fromisoformat(day), note=note))
            continue
        start, end = parse_time_input(row.start), parse_time_input(row.end)
        if start is None or end is None:
            raise ValueError(
                f"稼働日 {day} の開始と終了を時刻で入力してください(例: 13:00、930)。休みなら「休み」にチェックしてください"
            )
        built.append(WorkDay(date.fromisoformat(day), time.fromisoformat(start), time.fromisoformat(end), note))
    validate_work_days(built)
    return sort_work_days(built)


@dataclass
class RangeAdd:
    rows: list[WorkDayRow]  # 足す行(日付の昇順)
    registered: int  # 登録済みで飛ばした日数
    off: int  # 土日祝で飛ばした日数


def plan_work_day_range(
    period_text: str,
    rest: bool,
    start_text: str,
    end_text: str,
    note: str,
    skip_off: bool,
    rows: list[WorkDayRow],
    holidays: Mapping[date, str],
    today: date,
) -> RangeAdd:
    """「期間で追加」の入力を解釈して、足す行を作る。不正は ValueError。"""
    fixed = normalize_period(period_text, today)
    if fixed is None:
        raise ValueError("期間を入れてください(例: 2026-10-26 〜 2026-10-30)")
    start, end = validate_period(*split_period(fixed))
    window: tuple[time, time] | None = None
    if not rest:
        opens, closes = parse_time_input(start_text), parse_time_input(end_text)
        if opens is None or closes is None:
            raise ValueError("開始と終了を時刻で入力してください(例: 13:00、930)。休みなら「休み」にしてください")
        window = (time.fromisoformat(opens), time.fromisoformat(closes))
    existing = {date.fromisoformat(d) for r in rows if (d := parse_date_input(r.day, today, roll_forward=False))}
    added, registered, off = expand_range(start, end, window, note, existing, holidays, skip_off)
    built = [
        WorkDayRow(
            w.day.isoformat(),
            w.start.strftime("%H:%M") if w.start else "",
            w.end.strftime("%H:%M") if w.end else "",
            window is None,
            w.note,
        )
        for w in added
    ]
    return RangeAdd(built, registered, off)


def work_day_range_summary(plan: RangeAdd) -> str:
    """追加のあとの通知(足した日数と、飛ばした日数)。足す日がないときは、その旨。"""
    head = f"{len(plan.rows)} 日を追加しました" if plan.rows else "追加する日がありません"
    skipped = []
    if plan.registered:
        skipped.append(f"{plan.registered} 日は登録済みのため飛ばしました")
    if plan.off:
        skipped.append(f"土日祝 {plan.off} 日を除きました")
    return head + (f"({'。'.join(skipped)})" if skipped else "")


def work_day_editor(
    rows: list[WorkDayRow], marker: str, get_holidays: Callable[[], Mapping[date, str]] = dict
) -> None:
    """稼働日の上書きの行(日付 / 開始 / 終了 / 休み / メモ / 削除)と、追加・期間で追加のボタン。rows をその場で書き換える。"""

    from projectapp.task_dialog import add_picker, date_normalizer  # task_dialog が forms を使うので、呼ぶときに読む

    @ui.refreshable
    def table() -> None:
        with ui.column().classes("w-full gap-1"):
            for n, wrow in enumerate(rows):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    day_input = ui.input(
                        "日付", value=wrow.day, on_change=lambda e, r=wrow: setattr(r, "day", e.value or "")
                    ).classes("w-40").mark(f"{marker}-{n}-day")
                    add_picker(day_input, ui.date, "event", f"{marker}-{n}-day", "%Y-%m-%d", date_normalizer(False))
                    for label, name in (("開始", "start"), ("終了", "end")):
                        field_input = ui.input(
                            label,
                            value=getattr(wrow, name),
                            on_change=lambda e, r=wrow, k=name: setattr(r, k, e.value or ""),
                        ).classes("w-28").mark(f"{marker}-{n}-{name}")
                        add_picker(field_input, ui.time, "access_time", f"{marker}-{n}-{name}", "%H:%M", parse_time_input)
                        field_input.set_enabled(not wrow.rest)
                    ui.checkbox("休み", value=wrow.rest, on_change=lambda e, r=wrow: toggle(r, bool(e.value))).mark(
                        f"{marker}-{n}-rest"
                    )
                    note_input = ui.input(
                        "メモ", value=wrow.note, on_change=lambda e, r=wrow: setattr(r, "note", e.value or "")
                    ).classes("w-44").mark(f"{marker}-{n}-note")
                    limit_length(note_input, MAX_NOTE)
                    ui.button(icon="delete", on_click=lambda _e, r=wrow: remove(r)).props(
                        "flat dense color=negative"
                    ).mark(f"{marker}-{n}-remove")

    def toggle(wrow: WorkDayRow, value: bool) -> None:
        wrow.rest = value
        table.refresh()

    def remove(wrow: WorkDayRow) -> None:
        rows.remove(wrow)
        table.refresh()

    def add() -> None:
        rows.append(WorkDayRow("", "", "", False))
        table.refresh()

    def open_range() -> None:
        with ui.dialog() as sub, ui.card().classes("w-[34rem] max-w-full"):
            ui.label("期間で稼働日を追加").classes("text-subtitle1")
            ui.label("期間の各日を、1 日ずつの行として足します。登録済みの日は飛ばします").classes("text-caption text-grey")
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                period = ui.input("期間", placeholder="2026-10-26 〜 2026-10-30").classes("col").mark(
                    f"{marker}-range-period"
                )
                add_range_picker(period, f"{marker}-range")
            kind = ui.toggle({"rest": "休み", "window": "稼働の時間帯"}, value="rest").mark(f"{marker}-range-kind")
            with ui.row().classes("items-center gap-2"):
                start = ui.input("開始").classes("w-28").mark(f"{marker}-range-start")
                end = ui.input("終了").classes("w-28").mark(f"{marker}-range-end")
                for field_input in (start, end):
                    field_input.bind_enabled_from(kind, "value", lambda value: value == "window")
            skip = ui.checkbox("土日祝を除く", value=True).mark(f"{marker}-range-skip")
            note = ui.input("メモ(任意)").classes("w-full").mark(f"{marker}-range-note")
            limit_length(note, MAX_NOTE)
            error = ui.label("").classes("text-negative").mark(f"{marker}-range-error")

            def add_rows() -> None:
                try:
                    plan = plan_work_day_range(
                        period.value or "",
                        kind.value == "rest",
                        start.value or "",
                        end.value or "",
                        note.value or "",
                        bool(skip.value),
                        rows,
                        get_holidays(),
                        date.today(),
                    )
                except ValueError as exc:
                    error.set_text(str(exc))
                    return
                if not plan.rows:
                    error.set_text(work_day_range_summary(plan))
                    return
                rows.extend(plan.rows)
                rows.sort(key=lambda r: parse_date_input(r.day, date.today(), roll_forward=False) or "9999")
                ui.notify(work_day_range_summary(plan))
                sub.close()
                table.refresh()

            with ui.row().classes("gap-2"):
                ui.button("追加", on_click=add_rows).mark(f"{marker}-range-add")
                ui.button("キャンセル", on_click=sub.close).props("flat").mark(f"{marker}-range-cancel")
        sub.open()

    table()
    with ui.row().classes("gap-2"):
        ui.button("稼働日を追加", icon="add", on_click=add).props("flat dense").mark(f"{marker}-add")
        ui.button("期間で追加", icon="date_range", on_click=open_range).props("flat dense").mark(f"{marker}-range-open")


# 色の名前(ラベル)→ 色コード(Vue の式)。NiceGUI の select は、選択肢の value に番号(0〜9)を渡すので、色名では引けない。名前は一意
_COLOR_MAP = "{" + ",".join(f"'{COLOR_LABELS[color]}':'{code}'" for color, code in COLOR_HEX.items()) + "}"
_COLOR_DOT = f'<q-icon name="circle" size="xs" :style="{{ color: ({_COLOR_MAP})[props.opt.label] }}" />'
COLOR_OPTION_TEMPLATE = (  # 選択肢: 色付きの丸 + 色の名前
    '<q-item v-bind="props.itemProps"><q-item-section avatar>'
    f"{_COLOR_DOT}</q-item-section><q-item-section>{{{{ props.opt.label }}}}</q-item-section></q-item>"
)
COLOR_SELECTED_TEMPLATE = (  # 選んだあとの表示: 色付きの丸 + 色の名前
    f'<span class="row items-center no-wrap">{_COLOR_DOT}<span class="q-ml-xs">{{{{ props.opt.label }}}}</span></span>'
)


def limit_length(field: ui.input, limit: int) -> ui.input:
    """入力が上限(文字数)を超えたら、超えた分を切り捨てる。ブラウザの maxlength は UTF-16 単位で、絵文字などが 1 文字に数えられず、早く止まる。"""

    def cut(event: ValueChangeEventArguments) -> None:
        text = event.value or ""
        if len(text) > limit:
            field.set_value(text[:limit])

    field.on_value_change(cut)
    return field


def build_category_edit(rows: list[CategoryRow], originals: list[Category], taken: Collection[str]) -> CategoryEdit:
    """入力の行を検証して CategoryEdit にする。完全に空の新しい行(色だけ入っている行も)は無視する。新しい行には、既存の id と重ならない id を振る。"""
    used = set(taken)
    built: list[Category] = []
    for row in rows:
        texts = (row.name, row.kind, row.expiry, row.prj_code)
        if row.original is None and not any(t.strip() for t in texts):
            continue
        category_id = row.original or new_id(used)
        used.add(category_id)
        built.append(
            Category(
                row.name.strip(),
                row.kind.strip(),
                parse_expiry(row.expiry),
                row.color,
                row.prj_code.strip(),
                category_id,
            )
        )
    validate_categories(built)
    kept = {c.id for c in built}
    return CategoryEdit(built, [c.id for c in originals if c.id not in kept])


@dataclass
class LevelRow:
    """パラメータのダイアログの段階の 1 行。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    value_percent: float | None


@dataclass
class ParameterRow:
    """パラメータのダイアログの 1 行(下に段階の行を持つ)。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    levels: list[LevelRow]


def build_parameter_edit(rows: list[ParameterRow], before: list[Parameter]) -> ParameterEdit:
    """ダイアログの行を検証して、新しい定義と、旧い名前からの対応を返す。不正なら ValueError。"""
    parameters: list[Parameter] = []
    for row in rows:
        levels: list[Level] = []
        for level_row in row.levels:
            value = level_row.value_percent
            if value is None or not isfinite(value):
                raise ValueError("判定値を入力してください")
            if exceeds_decimals(value):
                raise ValueError(f"判定値は小数点以下{HOURS_DECIMALS}桁までで入力してください")
            levels.append(Level(level_row.name.strip(), round(value / 100, 4)))
        parameters.append(Parameter(row.name.strip(), levels))
    validate_parameters(parameters)
    by_name = {p.name: p for p in before}
    parameter_map: dict[str, str | None] = {p.name: None for p in before}
    level_map: dict[str, dict[str, str | None]] = {}
    for row, built in zip(rows, parameters):
        if row.original is None or row.original not in by_name:
            continue
        parameter_map[row.original] = built.name
        mapping: dict[str, str | None] = {lv.name: None for lv in by_name[row.original].levels}
        for level_row, level in zip(row.levels, built.levels):
            if level_row.original is not None and level_row.original in mapping:
                mapping[level_row.original] = level.name
        level_map[row.original] = mapping
    return ParameterEdit(parameters, parameter_map, level_map)


@dataclass
class MemberRow:
    """メンバーのダイアログの1行。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    ratio_percent: float | None
    levels: dict[str, str] = field(default_factory=dict)  # パラメータ名 → 選んだ段階名
    id: str | None = None  # 開いた時点のメンバーの id。新しい行は None(適用で新しい id を振る)
    icon: str = ""  # アイコン(data URI)。空はアイコンなし
    work_days: list[WorkDayRow] = field(default_factory=list)  # 稼働日の上書きの入力行
    ratio_unclamped: bool = False  # 丸めない(相対比率を 50〜150% に丸めない)
    teams: list[Membership] = field(default_factory=list)  # 所属するチーム(割合の合計 100。空はチームなし)


def build_members(
    rows: list[MemberRow],
    originals: list[str],
    assigned: Callable[[str], int],
    parameters: list[Parameter] | None = None,
    taken: Collection[str] = (),
    today: date | None = None,
    team_ids: Collection[str] = (),
) -> tuple[list[Member], dict[str, str]]:
    """ダイアログの行を検証して、メンバー一覧と、改名の対応({旧: 新})を返す。`taken` は、プロジェクトにある id(新しい行の id がこれと重ならない)。
    `team_ids` は、所属を検証する、今あるチームの id。"""
    members: list[Member] = []
    renames: dict[str, str] = {}
    seen: set[str] = set()
    used = set(taken)
    low, high = MIN_RATIO * 100, MAX_RATIO * 100
    for row in rows:
        name = (row.name or "").strip()
        if not name:
            raise ValueError("名前を入力してください")
        if name in seen:
            raise ValueError(f"名前が重複しています: {name}")
        seen.add(name)
        ratio = row.ratio_percent
        if ratio is None or not isfinite(ratio) or not low - 1e-9 <= ratio <= high + 1e-9:
            raise ValueError(f"相対比率は{low:g}〜{high:g}%で入力してください")
        if exceeds_decimals(ratio):
            raise ValueError(f"相対比率は小数点以下{HOURS_DECIMALS}桁までで入力してください")
        existing = {p.name: {lv.name for lv in p.levels} for p in parameters or []}
        levels = {p: lv for p, lv in row.levels.items() if lv in existing.get(p, set())}
        if row.icon and not is_valid_icon(row.icon):
            raise ValueError(f"アイコンが正しくありません: {name}")
        try:
            work_days = build_work_day_list(row.work_days, today or date.today())
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from None
        team_error = membership_error(row.teams, team_ids)
        if team_error is not None:
            raise ValueError(f"{name}: {team_error}")
        member_id = row.id or new_id(used)
        used.add(member_id)
        teams = [Membership(s.team_id, s.percent) for s in row.teams]
        members.append(
            Member(name, round(ratio / 100, 4), levels, member_id, row.icon, work_days, row.ratio_unclamped, teams)
        )
        if row.original is not None and row.original != name:
            renames[row.original] = name
    kept = {row.original for row in rows if row.original is not None}
    for original in originals:
        if original not in kept and (count := assigned(original)):
            raise ValueError(f"{original} を担当するタスクが{count}件あります")
    return members, renames


def build_section_name(text: str) -> str:
    clean = text.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    return clean


def section_name_error(text: str) -> str | None:
    """セクション名の不正な理由。問題なければ None。"""
    try:
        build_section_name(text)
    except ValueError as exc:
        return str(exc)
    return None


def format_datetime(moment: datetime | None) -> str:
    return moment.strftime(DATETIME_FORMAT) if moment else ""


def default_times(work_start: time) -> tuple[time, time]:
    """時刻を指定しないときに補う開始・終了の時刻。終了は始業 + 標準稼働時間 + 昼休憩。"""
    start = work_start.replace(second=0, microsecond=0)
    minutes = start.hour * 60 + start.minute + (STANDARD_WORK_HOURS + LUNCH_HOURS) * 60
    minutes = min(minutes, 24 * 60 - 1)  # 暫定: 24時以降は表せないので23:59で頭打ち(保留事項)
    return start, time(minutes // 60, minutes % 60)


def compose_datetime(day: str, clock: str) -> str:
    """日付と時刻の入力から、build_taskに渡す文字列を作る。日付が空なら空(時刻は無視する)。"""
    day, clock = day.strip(), clock.strip()
    if not day:
        return ""
    try:
        day = datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d")  # 2026-10-5 を正規化する
    except ValueError:
        pass  # 形式の誤りは build_task が報告する
    try:
        datetime.strptime(clock, "%H:%M")
    except ValueError:
        raise ValueError("時刻の形式が正しくありません") from None
    return f"{day}T{clock}"


def compose_actual(day: str, clock: str) -> str:
    """実績の日付と時刻から文字列を作る。両方空は空、片方だけはエラー(実績は時刻を補わない)。"""
    if not day.strip() and not clock.strip():
        return ""
    if not day.strip() or not clock.strip():
        raise ValueError("日付と時刻を両方入れてください")
    return compose_datetime(day, clock)


def suggest_status(
    has_start: bool, has_end: bool, progress: float | None = None, intervals: bool = False
) -> Status | None:
    """実績の入力から、提案する状態。開始なし(終了だけを含む)は提案しない。
    終了が空で進捗度が100のときは、完了とはみなさず、状態を変えない。
    区間(intervals)のときは、最後の区間が終わっていて進捗度が100でなければ、一時停止を提案する。"""
    if not has_start:
        return None
    if has_end:
        if intervals and progress != MAX_PROGRESS:
            return Status.PAUSED
        return Status.DONE
    return None if progress == MAX_PROGRESS else Status.RUNNING


def _minute(moment: datetime) -> time:
    return moment.time().replace(second=0, microsecond=0)


def needs_start_time(start: datetime | None, work_start: time) -> bool:
    """開始が、補う時刻(始業時刻)と違うか。違えば、ダイアログは開始の時刻入力を開いた状態で出す。"""
    return start is not None and _minute(start) != default_times(work_start)[0]


def needs_end_time(end: datetime | None, work_start: time) -> bool:
    """終了が、補う時刻と違うか。自動算出の終了(例: 15:30)も、違えば開いた状態で出す。"""
    return end is not None and _minute(end) != default_times(work_start)[1]


def open_section_dialog(on_save: Callable[[str], object], title: str = "セクションの追加") -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label(title).classes("text-h6")
        name = ui.input("セクション名").mark("section-name")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_section_name(name.value or "")
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("section-save")
    dialog.open()


def open_name_dialog(
    on_submit: Callable[[str], object],
    validate: Callable[[str], str | None],
    *,
    title: str = "プロジェクトの保存",
    initial: str = "",
    label: str = "プロジェクト名",
) -> None:
    """名前を入力して保存する。on_submitがFalseを返したら(保存に失敗)、入力を残して開いたままにする。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label(title).classes("text-h6")
        name = ui.input(label, value=initial).mark("project-name")
        error = ui.label("").classes("text-negative").mark("name-error")

        def save() -> None:
            clean = (name.value or "").strip()
            if message := validate(clean):
                error.set_text(message)
                return
            if on_submit(clean) is False:
                return
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("name-save")
    dialog.open()


def open_confirm_dialog(
    message: str, on_confirm: Callable[[], object], *, detail: str | None = None, confirm_label: str = "削除"
) -> None:
    """確認のダイアログ。確認したときだけ on_confirm を呼ぶ。"""
    with disposable(ui.dialog()) as dialog, ui.card():
        ui.label(message)
        if detail:
            ui.label(detail).classes("text-caption")

        def confirm() -> None:
            dialog.close()
            on_confirm()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("confirm-cancel")
            ui.button(confirm_label, on_click=confirm).props("color=negative").mark("confirm-ok")
    dialog.open()


def open_file_dialog(names: list[str], on_select: Callable[[str], object]) -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label("プロジェクトを開く").classes("text-h6")
        if not names:
            ui.label("プロジェクトファイルがありません")

        def choose(name: str) -> None:
            dialog.close()
            on_select(name)

        with ui.column().classes("w-full gap-1"):
            for index, name in enumerate(names):
                ui.button(name, on_click=lambda n=name: choose(n)).props(
                    "flat align=left"
                ).classes("w-full").mark(f"file-{index}")
        ui.button("キャンセル", on_click=dialog.close).props("flat")
    dialog.open()


def open_unsaved_dialog(
    on_save: Callable[[], object], on_discard: Callable[[], object], *, purpose: str = "開く"
) -> None:
    """編集中の確認。`purpose` は、続けてやりたい操作(「開く」「作成」)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("保存されていない変更があります").classes("text-h6")
        ui.label(f"{purpose}前に、現在のプロジェクトを保存しますか。")

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("unsaved-cancel")
            ui.button(f"保存せず{purpose}", on_click=lambda: run(on_discard)).props(
                "flat color=negative"
            ).mark("unsaved-discard")
            ui.button(f"保存して{purpose}", on_click=lambda: run(on_save)).mark("unsaved-save")
    dialog.open()


def open_stale_reference_dialog(name: str, on_update: Callable[[], object], on_skip: Callable[[], object]) -> None:
    """スナップショットが古いときの、参照先を開く前の確認(更新して開く / 更新せず開く / キャンセル)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("スナップショットが古くなっています").classes("text-h6")
        ui.label(f"「{name}」の参照値は、保存したあとに変わっています。更新してから開きますか。")

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("stale-cancel")
            ui.button("更新せず開く", on_click=lambda: run(on_skip)).props("flat").mark("stale-skip")
            ui.button("更新して開く", on_click=lambda: run(on_update)).mark("stale-update")
    dialog.open()


def open_stale_snapshot_dialog(
    names: list[str], purpose: str, on_update: Callable[[], object], on_skip: Callable[[], object]
) -> None:
    """スナップショットが古い参照先があるときの確認(更新して続ける / 更新せず続ける / キャンセル)。`purpose` は続けたい操作(「保存」など)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("スナップショットが古くなっています").classes("text-h6")
        ui.label(
            f"{''.join(f'「{n}」' for n in names)}の参照値は、保存したあとに変わっています。更新しますか。"
        )

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("snapshot-cancel")
            ui.button(f"更新せず{purpose}", on_click=lambda: run(on_skip)).props("flat").mark("snapshot-skip")
            ui.button(f"更新して{purpose}", on_click=lambda: run(on_update)).mark("snapshot-update")
    dialog.open()


def open_conflict_dialog(
    on_overwrite: Callable[[], object], on_save_as: Callable[[], object]
) -> None:
    """保存の直前に、ファイルが外部で変わっていたときの 3 択の確認(キャンセルは何もしない)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("ファイルが外部で変更されています").classes("text-h6")
        ui.label(
            "読み込んだあとに、別のプロセスや git、同期などでファイルが変わりました。"
            "上書きすると、その変更は失われます。"
        )

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("conflict-cancel")
            ui.button("名前をつけて保存", on_click=lambda: run(on_save_as)).props("flat").mark(
                "conflict-save-as"
            )
            ui.button("上書き", on_click=lambda: run(on_overwrite)).props("color=negative").mark(
                "conflict-overwrite"
            )
    dialog.open()


def open_commit_dialog(
    changes: list[FileChange],
    make_message: Callable[[list[str]], str],
    push_blocked: str | None,
    unsaved: bool,
    on_commit: Callable[[list[str], str, bool], object],
) -> None:
    """コミットのダイアログ。変更のあるファイルを選び(既定はすべて)、メッセージ(自動の案つき)を確かめて確定する。

    `push_blocked`は、「コミットしてプッシュ」を押せない理由(押せるときは None)。`unsaved`は、
    開いているプロジェクトに未保存の編集があるとき(コミットされないことを知らせる)。
    """
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[32rem]"):
        ui.label("コミット").classes("text-h6")
        if unsaved:
            ui.label("保存されていない編集は、コミットされません").classes("text-warning").mark("commit-unsaved")
        boxes: dict[str, ui.checkbox] = {}
        for change in changes:
            with ui.row().classes("items-center no-wrap"):
                boxes[change.name] = ui.checkbox(change.name, value=True).mark(f"commit-file-{change.name}")
                ui.label(change.status.value).classes("text-caption text-grey")
        message = ui.input("メッセージ").props("outlined dense").classes("w-full").mark("commit-message")
        auto = {"text": ""}  # 最後に入れた自動の案。利用者が直していなければ、選択の変更に合わせて更新する

        def chosen() -> list[str]:
            return [name for name, box in boxes.items() if box.value]

        def sync() -> None:
            names = chosen()
            suggestion = make_message(names)
            if (message.value or "") == auto["text"]:  # 最初(空 = 空)と、案のままのとき
                message.value = suggestion
            auto["text"] = suggestion
            ready = bool(names) and bool((message.value or "").strip())
            submit.set_enabled(ready)
            submit_push.set_enabled(ready and push_blocked is None)

        def submit_with(push: bool) -> None:
            names, text = chosen(), (message.value or "").strip()
            dialog.close()
            on_commit(names, text, push)

        with ui.row().classes("justify-end w-full"):
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("commit-cancel")
            submit = ui.button("コミット", on_click=lambda: submit_with(False)).mark("commit-submit")
            submit_push = ui.button("コミットしてプッシュ", on_click=lambda: submit_with(True)).mark("commit-submit-push")
            if push_blocked is not None:
                submit_push.tooltip(push_blocked)
        for box in boxes.values():
            box.on_value_change(sync)
        message.on_value_change(sync)
        sync()
    dialog.open()


def open_merge_conflict_dialog(
    file_name: str,
    conflicts: list[Conflict],
    on_apply: Callable[[Choices], object],
    on_cancel: Callable[[], object],
) -> None:
    """両側が違う値に変えた項目を、1 つずつ「自分」か「相手」で選ぶ(既定は相手)。
    「取り込む」で`on_apply`、「中止」・ESC・閉じるで`on_cancel`を、どちらか一度だけ呼ぶ。"""
    decided = {"done": False}

    def finish(action: Callable[[], object]) -> None:
        if decided["done"]:
            return
        decided["done"] = True
        action()

    dialog = ui.dialog()
    dialog.on("hide", lambda: finish(on_cancel))  # ESC・外側のクリックも中止。`disposable`の削除より前に登録する(削除後のイベントは捨てられる)
    with disposable(dialog), ui.card().classes("w-[40rem] max-w-full"):
        ui.label(f"{file_name} の衝突").classes("text-h6")
        ui.label("自分と相手が、同じ項目を違う値に変えています。採る値を選んでください。").classes("text-caption text-grey")
        radios: list[ui.radio] = []
        shown_label = None
        with ui.scroll_area().classes("w-full max-h-[60vh]"):
            for index, conflict in enumerate(conflicts):
                if (conflict.kind, conflict.key) != shown_label:
                    shown_label = (conflict.kind, conflict.key)
                    ui.label(conflict.label).classes("text-subtitle2 q-mt-sm")
                ui.label(conflict.field).classes("text-caption text-grey")
                if conflict.field == DELETED:
                    options = {
                        OURS: "自分: " + ("削除する" if conflict.ours is None else "残す"),
                        THEIRS: "相手: " + ("削除する" if conflict.theirs is None else "残す"),
                    }
                else:
                    options = {
                        OURS: f"自分: {format_value(conflict.ours)}",
                        THEIRS: f"相手: {format_value(conflict.theirs)}",
                    }
                radios.append(ui.radio(options, value=THEIRS).props("dense").mark(f"conflict-choice-{index}"))

        def apply() -> None:
            choices = {conflict.id: str(radio.value) for conflict, radio in zip(conflicts, radios, strict=True)}
            finish(lambda: on_apply(choices))
            dialog.close()

        def cancel() -> None:
            finish(on_cancel)
            dialog.close()

        with ui.row().classes("justify-end w-full"):
            ui.button("中止", on_click=cancel).props("flat").mark("conflict-abort")
            ui.button("取り込む", on_click=apply).mark("conflict-apply")
    dialog.open()


def open_settings_dialog(
    daily_hours: float,
    work_start: time,
    on_apply: Callable[[float, time, ActualMode], object],
    actual_mode: ActualMode = ActualMode.SIMPLE,
    multi_interval_tasks: int = 0,
    templates: list[UrlTemplate] | None = None,
    template_usage: Callable[[str], int] | None = None,
    on_templates: Callable[[TemplateEdit], object] | None = None,
    categories: list[Category] | None = None,
    category_usage: Callable[[str], int] | None = None,
    on_categories: Callable[[CategoryEdit], object] | None = None,
    events: list[Event] | None = None,
    on_events: Callable[[list[Event]], object] | None = None,
    used_ids: Collection[str] = (),
    base_date: date | None = None,
    on_base_date: Callable[[date], object] | None = None,
    reference_mode: ReferenceMode = ReferenceMode.LIVE,
    on_reference_mode: Callable[[ReferenceMode], object] | None = None,
    plantuml_notice: bool = True,
    on_plantuml_notice: Callable[[bool], object] | None = None,
    ratio_limits: RatioLimits = RatioLimits(),
    on_ratio_limits: Callable[[RatioLimits], object] | None = None,
) -> None:
    card_width = "w-[30rem] max-w-full" if categories is None and events is None else "w-[46rem] max-w-full"
    with disposable(ui.dialog()) as dialog, ui.card().classes(card_width):
        ui.label("稼働時間の設定").classes("text-h6")
        hours = ui.number(
            "1日の稼働可能時間(h)",
            value=daily_hours,
            min=MIN_DAILY_HOURS,
            max=MAX_DAILY_HOURS,
            step=0.5,
            validation={
                HOURS_RANGE_MESSAGE: lambda v: v is None or (isfinite(v) and in_hours_range(v)),
                f"小数点以下{HOURS_DECIMALS}桁までで入力してください": lambda v: (
                    v is None or not isfinite(v) or not exceeds_decimals(v)
                ),
            },
        ).classes("w-full").mark("settings-hours")
        start = ui.input("始業時刻", value=work_start.strftime("%H:%M")).classes(
            "w-full"
        ).mark("settings-start")
        with ui.dialog() as picker, ui.card():  # 小さな画面でも切れないよう、中央のダイアログにする
            bind_picker(ui.time().mark("settings-time-picker"), start, "%H:%M")
            ui.button("OK", on_click=picker.close).mark("time-picker-ok")
        with start.add_slot("append"):
            ui.icon("access_time").classes("cursor-pointer").on("click", picker.open).mark(
                "open-time-picker"
            )
        base_input: ui.input | None = None
        if base_date is not None:
            base_input = ui.input("基準日(プロジェクト開始日)", value=base_date.isoformat()).classes(
                "w-full"
            ).mark("settings-base-date")
            with ui.dialog() as base_picker, ui.card():
                bind_picker(ui.date().mark("settings-base-date-picker"), base_input, "%Y-%m-%d")
                ui.button("OK", on_click=base_picker.close).mark("date-picker-ok")
            with base_input.add_slot("append"):
                ui.icon("event").classes("cursor-pointer").on("click", base_picker.open).mark(
                    "open-date-picker"
                )
        ui.label("実績の記録方式").classes("text-caption text-grey")
        mode = ui.toggle(
            {ActualMode.SIMPLE.value: "簡易", ActualMode.INTERVALS.value: "区間"},
            value=actual_mode.value,
        ).mark("settings-actual-mode")
        # 区間から簡易へは、2区間以上のタスクがあるあいだ戻せない(選んでも区間に戻す)
        if multi_interval_tasks > 0 and actual_mode is ActualMode.INTERVALS:
            ui.label(
                f"{multi_interval_tasks}件のタスクに複数の区間があるため、簡易には戻せません"
            ).classes("text-caption text-grey").mark("settings-mode-locked")

            def keep_intervals(event: object) -> None:
                if getattr(event, "value", None) == ActualMode.SIMPLE.value:
                    mode.set_value(ActualMode.INTERVALS.value)

            mode.on_value_change(keep_intervals)
        reference = None
        if on_reference_mode is not None:
            ui.label("プロジェクト参照の方式").classes("text-caption text-grey")
            reference = ui.toggle(
                {ReferenceMode.LIVE.value: "常に最新", ReferenceMode.SNAPSHOT.value: "スナップショット"},
                value=reference_mode.value,
            ).mark("settings-reference-mode")
            ui.label("スナップショットは、参照行の値を保存します(右クリックの「更新」で取り直す)").classes(
                "text-caption text-grey"
            )
        notice = None
        if on_plantuml_notice is not None:
            notice = ui.checkbox(
                "PlantUML の保存後に、割り当てが 100% 超に見える担当者を通知する", value=plantuml_notice
            ).mark("settings-plantuml-notice")
        limit_upper = limit_lower = None
        if on_ratio_limits is not None:
            ui.label("相対比率の下限・上限").classes("text-caption text-grey")
            ui.label(
                "基本比率を含めた相対比率そのものの範囲を、既定の 50〜150% の中で狭められます(空欄は 50〜150%)"
            ).classes("text-caption text-grey")
            with ui.row().classes("items-center"):
                limit_upper = (
                    ui.input("上限(%)", value="" if ratio_limits.upper is None else f"{ratio_limits.upper * 100:g}")
                    .props("dense")
                    .classes("w-28")
                    .mark("settings-limit-upper")
                )
                limit_lower = (
                    ui.input("下限(%)", value="" if ratio_limits.lower is None else f"{ratio_limits.lower * 100:g}")
                    .props("dense")
                    .classes("w-28")
                    .mark("settings-limit-lower")
                )

                def fill_preset() -> None:
                    limit_upper.set_value("150")
                    limit_lower.set_value("50")

                ui.button("50% 〜 150%", on_click=fill_preset).props("flat dense").mark("settings-limit-preset")
        rows = [TemplateRow(t.name, t.name, t.pattern) for t in templates or []]
        if templates is not None:
            ui.label("URL テンプレート").classes("text-caption text-grey")
            ui.label("URL の型に {ID} と書くと、リンクで入力した ID に置き換わります").classes(
                "text-caption text-grey"
            )

            @ui.refreshable
            def template_table() -> None:
                with ui.column().classes("w-full gap-1"):
                    for n, row in enumerate(rows):
                        with ui.row().classes("w-full items-center no-wrap gap-2"):
                            ui.input(
                                "名前",
                                value=row.name,
                                on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                            ).classes("w-32").mark(f"settings-template-{n}-name")
                            ui.input(
                                "URL の型",
                                value=row.pattern,
                                on_change=lambda e, r=row: setattr(r, "pattern", e.value or ""),
                            ).classes("grow").mark(f"settings-template-{n}-pattern")
                            ui.button(
                                icon="delete", on_click=lambda _e, r=row: remove_template(r)
                            ).props("flat dense color=negative").mark(
                                f"settings-template-{n}-remove"
                            )

            def add_template() -> None:
                rows.append(TemplateRow(None, "", ""))
                template_table.refresh()

            def remove_template(row: TemplateRow) -> None:
                rows.remove(row)
                template_table.refresh()

            template_table()
            ui.button("テンプレートを追加", icon="add", on_click=add_template).props(
                "flat dense"
            ).mark("settings-template-add")
        category_rows = [
            CategoryRow(c.id, c.name, c.kind, c.expiry_date.isoformat() if c.expiry_date else "", c.color, c.prj_code)
            for c in categories or []
        ]
        if categories is not None:
            ui.label("カテゴリ").classes("text-caption text-grey")
            ui.label("担当者へ書き出すとき、タスクのカテゴリとして渡します").classes("text-caption text-grey")

            @ui.refreshable
            def category_table() -> None:
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("w-full items-center no-wrap gap-2").mark("settings-category-undecided"):
                        ui.icon("circle").classes("text-grey")
                        ui.label(UNDECIDED).classes("text-grey")
                        ui.label("(名前・PRJコード・色などは設定できません)").classes("text-caption text-grey")
                    for n, crow in enumerate(category_rows):
                        # 1 つのカテゴリは 2 段のブロック。1 段目に名前(残りの幅いっぱい)・色・削除、2 段目に種別(残りの幅)・有効期限・PRJコード
                        with ui.column().classes("w-full gap-1").style(
                            "border: 1px solid rgba(128, 128, 128, 0.35); border-radius: 4px; padding: 6px 8px"
                        ):
                            with ui.row().classes("w-full items-center no-wrap gap-2"):
                                limit_length(
                                    ui.input(
                                        "名前",
                                        value=crow.name,
                                        on_change=lambda e, r=crow: setattr(r, "name", e.value or ""),
                                    )
                                    .classes("grow")
                                    .mark(f"settings-category-{n}-name"),
                                    MAX_CATEGORY_NAME_LENGTH,
                                )
                                color_select = ui.select(
                                    {color: COLOR_LABELS[color] for color in COLORS},
                                    label="色",
                                    value=crow.color,
                                    on_change=lambda e, r=crow: setattr(r, "color", e.value),
                                ).classes("w-32").mark(f"settings-category-{n}-color")
                                color_select.add_slot("option", COLOR_OPTION_TEMPLATE)
                                color_select.add_slot("selected-item", COLOR_SELECTED_TEMPLATE)
                                ui.button(icon="delete", on_click=lambda _e, r=crow: remove_category(r)).props(
                                    "flat dense color=negative"
                                ).mark(f"settings-category-{n}-remove")
                            with ui.row().classes("w-full items-center no-wrap gap-2"):
                                limit_length(
                                    ui.input(
                                        "種別",
                                        value=crow.kind,
                                        on_change=lambda e, r=crow: setattr(r, "kind", e.value or ""),
                                    )
                                    .classes("grow")
                                    .mark(f"settings-category-{n}-kind"),
                                    MAX_CATEGORY_KIND_LENGTH,
                                )
                                ui.input(
                                    "有効期限",
                                    value=crow.expiry,
                                    on_change=lambda e, r=crow: setattr(r, "expiry", e.value or ""),
                                ).props("type=date stack-label").classes("w-36").mark(f"settings-category-{n}-expiry")
                                limit_length(
                                    ui.input(
                                        "PRJコード",
                                        value=crow.prj_code,
                                        on_change=lambda e, r=crow: setattr(r, "prj_code", e.value or ""),
                                    )
                                    .classes("w-48")
                                    .mark(f"settings-category-{n}-prj"),
                                    MAX_PROJECT_CODE_LENGTH,
                                )

            def add_category() -> None:
                color = next_color(built_categories())
                category_rows.append(CategoryRow(None, "", "", "", color, ""))
                category_table.refresh()

            def remove_category(crow: CategoryRow) -> None:
                category_rows.remove(crow)
                category_table.refresh()

            def built_categories() -> list[Category]:
                """色の選び方のために、いまの行をカテゴリとして見る(検証はしない)。"""
                return [Category(r.name, color=r.color) for r in category_rows]

            category_table()
            ui.button("カテゴリを追加", icon="add", on_click=add_category).props("flat dense").mark(
                "settings-category-add"
            )
        event_rows = [EventRow(e.id, e.start.isoformat(), e.end.isoformat(), e.text, e.color, e.closed) for e in events or []]
        if events is not None:
            ui.label("イベント").classes("text-caption text-grey")
            ui.label("開始日〜終了日に、文字列をガントチャートの日付の下に出し、期間のセルを色で塗ります").classes(
                "text-caption text-grey"
            )
            ui.label(
                "「稼働日を休みにする」をチェックした期間は、全員の稼働日を休みとして扱います(メンバーが稼働日の上書きで稼働にした日を除く)"
            ).classes("text-caption text-grey")

            @ui.refreshable
            def event_table() -> None:
                with ui.column().classes("w-full gap-1"):
                    for n, erow in enumerate(event_rows):
                        with ui.column().classes("w-full gap-1").style(
                            "border: 1px solid rgba(128, 128, 128, 0.35); border-radius: 4px; padding: 6px 8px"
                        ):
                            with ui.row().classes("w-full items-center no-wrap gap-2"):
                                limit_length(
                                    ui.input(
                                        "文字列",
                                        value=erow.text,
                                        on_change=lambda e, r=erow: setattr(r, "text", e.value or ""),
                                    )
                                    .classes("grow")
                                    .mark(f"settings-event-{n}-text"),
                                    MAX_EVENT_TEXT_LENGTH,
                                )
                                ui.button(icon="delete", on_click=lambda _e, r=erow: remove_event(r)).props(
                                    "flat dense color=negative"
                                ).mark(f"settings-event-{n}-remove")
                            with ui.row().classes("w-full items-center no-wrap gap-2"):
                                ui.input(
                                    "開始日",
                                    value=erow.start,
                                    on_change=lambda e, r=erow: setattr(r, "start", e.value or ""),
                                ).classes("w-36").mark(f"settings-event-{n}-start")
                                ui.input(
                                    "終了日",
                                    value=erow.end,
                                    on_change=lambda e, r=erow: setattr(r, "end", e.value or ""),
                                ).classes("w-36").mark(f"settings-event-{n}-end")
                                swatch = ui.icon("circle").style(f"color: {swatch_color(erow.color)}")
                                swatch.mark(f"settings-event-{n}-swatch")
                                ui.input(
                                    "色(red, orange, gray…)",
                                    value=erow.color,
                                    on_change=lambda e, r=erow, s=swatch: change_event_color(r, s, e.value or ""),
                                ).classes("grow").mark(f"settings-event-{n}-color")
                                ui.checkbox(
                                    "稼働日を休みにする",
                                    value=erow.closed,
                                    on_change=lambda e, r=erow: setattr(r, "closed", bool(e.value)),
                                ).mark(f"settings-event-{n}-closed")

            def swatch_color(text: str) -> str:
                name = normalize_color(text)
                return color_hex(name) if name else "#bdbdbd"

            def change_event_color(erow: EventRow, swatch: ui.icon, text: str) -> None:
                erow.color = text
                swatch.style(f"color: {swatch_color(text)}")

            def add_event() -> None:
                event_rows.append(EventRow(None, "", "", "", "gray"))
                event_table.refresh()

            def remove_event(erow: EventRow) -> None:
                event_rows.remove(erow)
                event_table.refresh()

            event_table()
            ui.button("イベントを追加", icon="add", on_click=add_event).props("flat dense").mark("settings-event-add")
        error = ui.label("").classes("text-negative").mark("settings-error")
        pending: dict[str, Any] = {}
        with ui.dialog() as confirm, ui.card():
            confirm_text = ui.label("").classes("whitespace-pre-line")
            with ui.row():
                ui.button("キャンセル", on_click=confirm.close).props("flat").mark(
                    "settings-confirm-cancel"
                )
                ui.button("削除する", on_click=lambda: confirm_delete()).props(
                    "color=negative"
                ).mark("settings-confirm-delete")

        def build_edit() -> TemplateEdit | None:
            if templates is None:
                return None
            active = [r for r in rows if r.original is not None or r.name.strip() or r.pattern.strip()]
            built = [UrlTemplate(r.name.strip(), r.pattern.strip()) for r in active]
            validate_templates(built)
            renames = {
                r.original: r.name.strip()
                for r in active
                if r.original is not None and r.original != r.name.strip()
            }
            kept = {r.original for r in active if r.original is not None}
            removed = [t.name for t in templates if t.name not in kept]
            return TemplateEdit(built, renames, removed)

        def build_categories() -> CategoryEdit | None:
            if categories is None:
                return None
            return build_category_edit(category_rows, categories, used_ids)

        def build_events() -> list[Event] | None:
            if events is None:
                return None
            return build_event_list(event_rows, used_ids, date.today())

        def commit(
            result: tuple[float, time],
            edit: TemplateEdit | None,
            cedit: CategoryEdit | None,
            elist: list[Event] | None,
            base: date | None,
            limits: RatioLimits | None,
        ) -> None:
            on_apply(*result, ActualMode(mode.value))
            if base is not None and on_base_date is not None:
                on_base_date(base)
            if reference is not None and on_reference_mode is not None and ReferenceMode(reference.value) is not reference_mode:
                on_reference_mode(ReferenceMode(reference.value))
            if notice is not None and on_plantuml_notice is not None and bool(notice.value) is not plantuml_notice:
                on_plantuml_notice(bool(notice.value))
            if limits is not None and on_ratio_limits is not None and limits != ratio_limits:
                on_ratio_limits(limits)
            if edit is not None and on_templates is not None and edit.templates != templates:
                on_templates(edit)
            if cedit is not None and on_categories is not None and (cedit.categories != categories or cedit.removed_ids):  # Category の比較は id を見ないので、内容が同じ行の入れ直しも、削除として適用する
                on_categories(cedit)
            if elist is not None and on_events is not None and [event_key(e) for e in elist] != [event_key(e) for e in events or []]:
                on_events(elist)
            dialog.close()

        def confirm_delete() -> None:
            confirm.close()
            commit(pending["result"], pending["edit"], pending["cedit"], pending["elist"], pending["base"], pending["limits"])

        def apply() -> None:
            try:
                result = build_work_settings(hours.value, start.value or "")
                edit = build_edit()
                cedit = build_categories()
                elist = build_events()
                base = build_base_date(base_input.value or "", date.today()) if base_input else None
                limits = (
                    build_ratio_limits(limit_upper.value or "", limit_lower.value or "")
                    if limit_upper is not None and limit_lower is not None
                    else None
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            messages = []
            used = sum(template_usage(n) for n in edit.removed) if edit and template_usage else 0
            if used:
                messages.append(
                    f"削除するテンプレートを使っているリンクが{used}件あります。URL としてそのまま残ります。"
                )
            tasks = sum(category_usage(i) for i in cedit.removed_ids) if cedit and category_usage else 0
            if tasks:
                messages.append(f"削除するカテゴリを使っているタスクが{tasks}件あります。未定に戻ります。")
            if messages:
                pending.update(result=result, edit=edit, cedit=cedit, elist=elist, base=base, limits=limits)
                confirm_text.set_text("\n".join(messages))
                confirm.open()
                return
            commit(result, edit, cedit, elist, base, limits)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("settings-apply")
    dialog.open()


@dataclass
class ParametersPanel:
    """パラメータのタブの操作。dirty は、未適用の編集があるか、apply は適用(続きの処理は、適用できたときだけ呼ぶ)。"""

    dirty: Callable[[], bool]
    apply: Callable[[Callable[[], None] | None], None]


def parameters_panel(
    get_parameters: Callable[[], list[Parameter]],
    impacts: Callable[[ParameterEdit], list[str]],
    on_apply: Callable[[ParameterEdit], object],
    on_applied: Callable[[ParameterEdit], object],
    get_limits: Callable[[], RatioLimits] = RatioLimits,
) -> ParametersPanel:
    """パラメータの定義の編集(タブの中身)。削除でメンバーの選択が外れるときは、適用の前に確認する。
    適用してもダイアログは閉じず、プロジェクトの今の定義から行を作り直す。"""

    def to_rows() -> list[ParameterRow]:
        return [
            ParameterRow(p.name, p.name, [LevelRow(lv.name, lv.name, round(lv.value * 100, 2)) for lv in p.levels])
            for p in get_parameters()
        ]

    rows = to_rows()
    baseline = deepcopy(rows)
    ui.label(f"相対比率 = 基本比率 + 選んだ段階の判定値の合計({ratio_range_text(get_limits())} に丸めます。メンバーの「丸めない」を除く)").classes(
        "text-caption text-grey"
    )

    @ui.refreshable
    def table() -> None:
        with ui.column().classes("w-full gap-2"):
            if not rows:
                ui.label("パラメータがありません").classes("text-grey")
            for p, row in enumerate(rows):
                with ui.column().classes("w-full gap-1 q-pa-sm").style("border: 1px solid rgba(128,128,128,0.4)"):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.input(
                            "パラメータ名",
                            value=row.name,
                            on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                        ).classes("flex-1").mark(f"parameter-name-{p}")
                        ui.button(icon="delete", on_click=lambda _e, r=row: remove_parameter(r)).props(
                            "flat dense round color=negative"
                        ).mark(f"parameter-delete-{p}")
                    for n, level in enumerate(row.levels):
                        with ui.row().classes("w-full items-center no-wrap gap-2 q-pl-md"):
                            ui.input(
                                "段階",
                                value=level.name,
                                on_change=lambda e, lv=level: setattr(lv, "name", e.value or ""),
                            ).classes("flex-1").mark(f"level-name-{p}-{n}")
                            ui.number(
                                "判定値(%)",
                                value=level.value_percent,
                                min=MIN_LEVEL_VALUE * 100,
                                max=MAX_LEVEL_VALUE * 100,
                                step=5,
                                on_change=lambda e, lv=level: setattr(lv, "value_percent", e.value),
                            ).classes("w-32").mark(f"level-value-{p}-{n}")
                            ui.button(
                                icon="delete", on_click=lambda _e, r=row, lv=level: remove_level(r, lv)
                            ).props("flat dense round").mark(f"level-delete-{p}-{n}")
                    ui.button("段階を追加", icon="add", on_click=lambda _e, r=row: add_level(r)).props(
                        "flat dense"
                    ).classes("q-ml-md").mark(f"level-add-{p}")

    def add_parameter() -> None:
        rows.append(ParameterRow(None, "", []))
        table.refresh()

    def remove_parameter(row: ParameterRow) -> None:
        rows.remove(row)
        table.refresh()

    def add_level(row: ParameterRow) -> None:
        row.levels.append(LevelRow(None, "", 0.0))
        table.refresh()

    def remove_level(row: ParameterRow, level: LevelRow) -> None:
        row.levels.remove(level)
        table.refresh()

    table()
    ui.button("パラメータを追加", icon="add", on_click=add_parameter).props("flat").mark("parameter-add")
    error = ui.label("").classes("text-negative").mark("parameter-error")
    pending: dict[str, ParameterEdit] = {}
    after: dict[str, Callable[[], None] | None] = {"then": None}
    with ui.dialog() as confirm, ui.card():
        confirm_text = ui.label("").style("white-space: pre-line")
        with ui.row():
            ui.button("キャンセル", on_click=confirm.close).props("flat").mark("parameter-delete-cancel")
            ui.button("削除する", on_click=lambda: confirm_apply()).props("color=negative").mark(
                "parameter-delete-confirm"
            )

    def commit(edit: ParameterEdit, then: Callable[[], None] | None) -> None:
        on_apply(edit)
        on_applied(edit)
        rows[:] = to_rows()
        baseline[:] = deepcopy(rows)
        table.refresh()
        if then is not None:
            then()

    def confirm_apply() -> None:
        confirm.close()
        commit(pending["edit"], after["then"])

    def apply(then: Callable[[], None] | None = None) -> None:
        error.set_text("")
        try:
            edit = build_parameter_edit(rows, get_parameters())
        except ValueError as exc:
            error.set_text(str(exc))
            return
        affected = impacts(edit)
        if affected:
            pending["edit"] = edit
            after["then"] = then
            confirm_text.set_text(
                "\n".join(affected) + "\n削除すると、その選択は外れます(メンバーは判定値 0%、タスクはパラメータなしになります)"
            )
            confirm.open()
            return
        commit(edit, then)

    ui.button("適用", on_click=lambda: apply()).mark("parameter-apply")
    return ParametersPanel(dirty=lambda: rows != baseline, apply=apply)


def effective_ratio_text(row: MemberRow, parameters: list[Parameter], limits: RatioLimits | None = None) -> str:
    """メンバーの行の、実効比率の表示。基本比率が空・非有限のときは空。範囲に丸めた・設定の下限/上限で制限したときは、その旨を足す。"""
    percent = row.ratio_percent
    if percent is None or not isfinite(percent):
        return ""
    detail = ratio_detail(
        Member(row.name, percent / 100, row.levels, ratio_unclamped=row.ratio_unclamped), parameters, limits=limits
    )
    notes = ["丸め対象外"] if detail.unclamped else []
    if detail.clamped and not detail.limited:
        notes.append("範囲に丸めました")  # 制限したときは、その注記だけ
    if note := limit_note(detail, limits):
        notes.append(note)
    suffix = f"({'・'.join(notes)})" if notes else ""
    return f"相対比率 {detail.ratio * 100:g}%{suffix}"


def _signed_percent(value: float) -> str:
    return f"{value * 100:+g}%" if value else "0%"


MEMBER_ICON_COLUMN_REM = 6  # アイコンの列(画像 + 選ぶ・外すのボタン)
MEMBER_ICON_SIZE_PX = 28
MEMBER_NAME_COLUMN_REM = 7  # 名前の列(固定。列の数や画面の幅で変わらない)
MEMBER_RATIO_COLUMN_REM = 7
MEMBER_UNCLAMPED_COLUMN_REM = 5  # 丸めないのチェックの列
MEMBER_LEVEL_COLUMN_REM = 9
MEMBER_EFFECTIVE_COLUMN_REM = 11
MEMBER_WORK_DAYS_COLUMN_REM = 7
MEMBER_TEAMS_COLUMN_REM = 10  # チームの列(所属の要約のボタン)
MEMBER_DELETE_COLUMN_REM = 3
MEMBER_ROW_HEIGHT_PX = 36
MEMBER_ROW_GAP_PX = 4  # 行の間隔(gap-y-1)
MEMBER_HEADER_HEIGHT_PX = 20  # 見出しの行(12px の文字)
MEMBER_SCROLLBAR_ROOM_PX = 24  # 横スクロールバー(約 15px)の余裕
# メンバーの表の中のコントロールを 14px にそろえる(入力・選択の文字、プルダウンの項目、実効比率)。見出しは 12px のまま
MEMBER_TABLE_CSS = f"""
.member-table .q-field__native, .member-table .q-field__input, .member-table .q-field__label {{ font-size: 14px; line-height: 20px; }}
.member-table .q-field--dense .q-field__control, .member-table .q-field--dense .q-field__marginal {{ height: {MEMBER_ROW_HEIGHT_PX}px; min-height: {MEMBER_ROW_HEIGHT_PX}px; }}
.member-table .q-field--dense .q-field__native {{ min-height: {MEMBER_ROW_HEIGHT_PX}px; }}
.member-table .member-effective {{ font-size: 14px; }}
.member-popup .q-item {{ font-size: 14px; min-height: {MEMBER_ROW_HEIGHT_PX}px; }}
"""


def member_columns(level_count: int, with_effective: bool, with_teams: bool = False) -> list[str]:
    """メンバーの表の列の幅(アイコン・名前・基本比率・丸めない・パラメータごとの段階・実効比率・チーム・稼働日・削除)。"""
    columns = [
        f"{MEMBER_ICON_COLUMN_REM}rem",
        f"{MEMBER_NAME_COLUMN_REM}rem",
        f"{MEMBER_RATIO_COLUMN_REM}rem",
        f"{MEMBER_UNCLAMPED_COLUMN_REM}rem",
    ]
    columns += [f"{MEMBER_LEVEL_COLUMN_REM}rem"] * level_count
    if with_effective:
        columns.append(f"{MEMBER_EFFECTIVE_COLUMN_REM}rem")
    if with_teams:
        columns.append(f"{MEMBER_TEAMS_COLUMN_REM}rem")
    columns.append(f"{MEMBER_WORK_DAYS_COLUMN_REM}rem")
    columns.append(f"{MEMBER_DELETE_COLUMN_REM}rem")
    return columns


def member_scroll_min_height_px(row_count: int) -> int:
    """表を囲む枠の最小の高さ(px)。見出し 1 行 + 行数ぶん + 横スクロールバーの余裕。"""
    return MEMBER_HEADER_HEIGHT_PX + row_count * (MEMBER_ROW_HEIGHT_PX + MEMBER_ROW_GAP_PX) + MEMBER_SCROLLBAR_ROOM_PX


def member_table_min_rem(level_count: int, with_effective: bool, with_teams: bool = False) -> int:
    """表の最小の幅(rem)。これより狭い画面では、表を横にスクロールさせる。"""
    return (
        MEMBER_ICON_COLUMN_REM
        + MEMBER_NAME_COLUMN_REM
        + MEMBER_RATIO_COLUMN_REM
        + MEMBER_UNCLAMPED_COLUMN_REM
        + MEMBER_LEVEL_COLUMN_REM * level_count
        + (MEMBER_EFFECTIVE_COLUMN_REM if with_effective else 0)
        + (MEMBER_TEAMS_COLUMN_REM if with_teams else 0)
        + MEMBER_WORK_DAYS_COLUMN_REM
        + MEMBER_DELETE_COLUMN_REM
        + 2 * (6 + level_count + (1 if with_effective else 0) + (1 if with_teams else 0))  # 列の間隔(gap 0.5rem)の概算
    )


@dataclass
class MembersPanel:
    """メンバーのタブの操作。dirty は未適用の編集があるか、min_rem は今の表の幅(rem)、
    parameters_changed は、パラメータの適用を、teams_changed は、チームの削除を、未適用の行へ伝える。"""

    dirty: Callable[[], bool]
    min_rem: Callable[[], int]
    parameters_changed: Callable[[ParameterEdit], None]
    teams_changed: Callable[[set[str]], None]
    apply: Callable[[Callable[[], None] | None], None]


def members_panel(
    get_members: Callable[[], list[Member]],
    assigned: Callable[[str], int],
    on_apply: Callable[[list[Member], dict[str, str]], object],
    get_parameters: Callable[[], list[Parameter]],
    get_taken: Callable[[], Collection[str]],
    pick_icon: Callable[[], Awaitable[str | None]] | None = None,
    get_limits: Callable[[], RatioLimits] = RatioLimits,
    get_holidays: Callable[[], dict[date, str]] = dict,
    get_teams: Callable[[], list[Team]] = list,
) -> MembersPanel:
    """メンバーの編集(タブの中身)。1 行が 1 人の表(名前・基本比率・パラメータごとの段階・実効比率・削除)。
    適用してもダイアログは閉じず、プロジェクトの今のメンバーから行を作り直す。"""

    def work_day_rows(member: Member) -> list[WorkDayRow]:
        return [
            WorkDayRow(
                w.day.isoformat(),
                w.start.strftime("%H:%M") if w.start else "",
                w.end.strftime("%H:%M") if w.end else "",
                w.start is None,
                w.note,
            )
            for w in member.work_days
        ]

    def to_rows() -> list[MemberRow]:
        return [
            MemberRow(
                m.name,
                m.name,
                round(m.ratio * 100, 2),
                dict(m.levels),
                m.id,
                m.icon,
                work_day_rows(m),
                m.ratio_unclamped,
                [Membership(s.team_id, s.percent) for s in m.teams],
            )
            for m in get_members()
        ]

    rows = to_rows()
    baseline = deepcopy(rows)
    originals = [r.name for r in rows]
    current = {"parameters": list(get_parameters())}

    def layout() -> tuple[list[Parameter], bool, list[str], int, bool]:
        parameters = current["parameters"]
        with_effective = bool(parameters)
        with_teams = bool(get_teams())
        return (
            parameters,
            with_effective,
            member_columns(len(parameters), with_effective, with_teams),
            member_table_min_rem(len(parameters), with_effective, with_teams),
            with_teams,
        )

    @ui.refreshable
    def table() -> None:
        chosen_parameters, with_effective, columns, min_rem, with_teams = layout()
        if not rows:
            ui.label("メンバーがいません").classes("text-grey")
        # 横に伸びる(パラメータが多い)ときは、表だけを横にスクロールさせる。
        # タブの中身は flex の縦並びで、overflow を持つ枠は縮められる(1 行ぶんまで潰れる)ので、縮めない。
        # 行を足した直後に高さが追従しないことがあるため、行数から必要な高さを下限として与える
        with ui.element("div").classes("w-full").style(
            f"overflow-x: auto; flex-shrink: 0; min-height: {member_scroll_min_height_px(len(rows))}px"
        ).mark("member-scroll"):
            with ui.grid(columns=" ".join(columns)).classes("member-table items-center gap-x-2 gap-y-1").style(
                f"min-width: {min_rem}rem"
            ).mark("member-grid"):
                header = "text-caption text-grey"
                ui.label("アイコン").classes(header).mark("member-header-icon")
                ui.label("名前").classes(header).mark("member-header-name")
                ui.label("基本比率(%)" if with_effective else "相対比率(%)").classes(header).mark(
                    "member-header-ratio"
                )
                ui.label("丸めない").classes(header).mark("member-header-unclamped")
                for p, parameter in enumerate(chosen_parameters):
                    ui.label(parameter.name).classes(f"{header} ellipsis").mark(f"member-header-level-{p}")
                if with_effective:
                    ui.label("相対比率").classes(header).mark("member-header-effective")
                if with_teams:
                    ui.label("チーム").classes(header).mark("member-header-teams")
                ui.label("稼働日").classes(header).mark("member-header-workdays")
                ui.label("")
                for index, row in enumerate(rows):
                    effective: list[ui.label] = []  # 行の実効比率のラベル(各入力の変更で更新する)

                    def refresh_effective(r: MemberRow, holder: list[ui.label] = effective) -> None:
                        if holder:
                            holder[0].set_text(effective_ratio_text(r, chosen_parameters, get_limits()))

                    def on_ratio(e, r=row) -> None:  # noqa: ANN001
                        r.ratio_percent = e.value
                        refresh_effective(r)

                    with ui.row().classes("items-center no-wrap gap-1"):
                        avatar(row.name or "?", row.icon, MEMBER_ICON_SIZE_PX).mark(f"member-icon-{index}")
                        if pick_icon is not None:
                            ui.button(icon="image", on_click=lambda r=row: choose_icon(r)).props(
                                "flat dense round size=sm"
                            ).tooltip("アイコンを選ぶ").mark(f"member-icon-pick-{index}")
                        if row.icon:
                            ui.button(icon="close", on_click=lambda r=row: clear_icon(r)).props(
                                "flat dense round size=sm"
                            ).tooltip("アイコンを外す").mark(f"member-icon-clear-{index}")
                    ui.input(
                        value=row.name,
                        on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                    ).props("dense outlined aria-label=名前").classes("w-full").mark(f"member-name-{index}")
                    ui.number(
                        value=row.ratio_percent,
                        min=MIN_RATIO * 100,
                        max=MAX_RATIO * 100,
                        step=5,
                        on_change=on_ratio,
                    ).props("dense outlined aria-label=比率").classes("w-full").mark(f"member-ratio-{index}")

                    def on_unclamped(e, r=row) -> None:  # noqa: ANN001
                        r.ratio_unclamped = bool(e.value)
                        refresh_effective(r)

                    ui.checkbox(value=row.ratio_unclamped, on_change=on_unclamped).props(
                        "dense aria-label=丸めない"
                    ).tooltip(
                        "50〜150%(設定の上限・下限)に丸めず、基本比率 + 判定値をそのまま使います。10〜300% は常に守ります"
                    ).mark(f"member-unclamped-{index}")
                    for p, parameter in enumerate(chosen_parameters):

                        def on_level(e, r=row, name=parameter.name) -> None:  # noqa: ANN001
                            if e.value:
                                r.levels[name] = e.value
                            else:
                                r.levels.pop(name, None)
                            refresh_effective(r)

                        options = {
                            "": "(なし)",
                            **{lv.name: f"{lv.name} {_signed_percent(lv.value)}" for lv in parameter.levels},
                        }
                        current = row.levels.get(parameter.name, "")
                        ui.select(
                            options,
                            value=current if current in options else "",
                            on_change=on_level,
                        ).props(
                            f"dense outlined aria-label={parameter.name} popup-content-class=member-popup"
                        ).classes("w-full").mark(
                            f"member-level-{index}-{p}"
                        )
                    if with_effective:
                        effective.append(
                            ui.label(effective_ratio_text(row, chosen_parameters, get_limits()))
                            .classes("text-grey member-effective")
                            .mark(f"member-effective-{index}")
                        )
                    if with_teams:
                        ui.button(
                            membership_summary(row.teams, get_teams()),
                            on_click=lambda r=row: open_teams(r),
                        ).props("flat dense no-caps").classes("ellipsis").mark(f"member-teams-open-{index}")
                    ui.button(
                        f"稼働日({len(row.work_days)})" if row.work_days else "稼働日",
                        on_click=lambda r=row: open_work_days(r),
                    ).props("flat dense no-caps").mark(f"member-workday-open-{index}")
                    ui.button(icon="delete", on_click=lambda r=row: remove(r)).props(
                        "flat dense round"
                    ).mark(f"member-delete-{index}")

    def remove(row: MemberRow) -> None:
        rows.remove(row)
        table.refresh()

    def open_work_days(row: MemberRow) -> None:
        with ui.dialog() as sub, ui.card().classes("w-[58rem] max-w-full"):
            ui.label(f"{row.name or '(名前なし)'} の稼働日の上書き").classes("text-subtitle1")
            ui.label("日付ごとに、稼働の時間帯(開始〜終了)か休みを決めます。土日祝を稼働にしたり、平日を休みにできます").classes(
                "text-caption text-grey"
            )
            work_day_editor(row.work_days, "member-workday", get_holidays)
            ui.button("閉じる", on_click=sub.close).mark("member-workday-close")
        sub.on("hide", table.refresh)
        sub.open()

    def open_teams(row: MemberRow) -> None:
        def save(chosen: list[Membership]) -> None:
            row.teams = chosen
            table.refresh()

        open_member_teams_dialog(row.name, get_teams(), list(row.teams), save)

    async def choose_icon(row: MemberRow) -> None:
        assert pick_icon is not None
        chosen = await pick_icon()
        if chosen is not None:
            row.icon = chosen
            table.refresh()

    def clear_icon(row: MemberRow) -> None:
        row.icon = ""
        table.refresh()

    def add() -> None:
        rows.append(MemberRow(None, "", 100.0))
        table.refresh()
    table()
    ui.button("メンバーを追加", icon="add", on_click=add).props("flat").mark("member-add")
    error = ui.label("").classes("text-negative").mark("member-error")

    def apply(then: Callable[[], None] | None = None) -> None:
        try:
            result = build_members(
                rows, originals, assigned, current["parameters"], get_taken(), team_ids={t.id for t in get_teams()}
            )
        except ValueError as exc:
            error.set_text(str(exc))
            return
        error.set_text("")
        on_apply(*result)
        rows[:] = to_rows()
        baseline[:] = deepcopy(rows)
        originals[:] = [r.name for r in rows]
        table.refresh()
        if then is not None:
            then()

    def parameters_changed(edit: ParameterEdit) -> None:
        for row in (*rows, *baseline):  # 未適用の行も、適用済みの基準も、同じように写す(印が出ない)
            row.levels = remap_levels(row.levels, edit)
        current["parameters"] = list(get_parameters())
        table.refresh()

    def teams_changed(removed: set[str]) -> None:
        for row in (*rows, *baseline):  # 未適用の行も、適用済みの基準も、同じように写す(印が出ない)
            row.teams = normalize([s for s in row.teams if s.team_id not in removed])
        table.refresh()

    ui.button("適用", on_click=lambda: apply()).mark("member-apply")
    return MembersPanel(
        dirty=lambda: rows != baseline,
        min_rem=lambda: layout()[3],
        parameters_changed=parameters_changed,
        teams_changed=teams_changed,
        apply=apply,
    )


def open_members_parameters_dialog(
    *,
    get_members: Callable[[], list[Member]],
    assigned: Callable[[str], int],
    on_apply_members: Callable[[list[Member], dict[str, str]], object],
    get_parameters: Callable[[], list[Parameter]],
    impacts: Callable[[ParameterEdit], list[str]],
    on_apply_parameters: Callable[[ParameterEdit], object],
    get_taken: Callable[[], Collection[str]],
    pick_icon: Callable[[], Awaitable[str | None]] | None = None,
    applied: Callable[[], bool] = lambda: False,
    rollback: Callable[[], object] = lambda: None,
    get_limits: Callable[[], RatioLimits] = RatioLimits,
    get_holidays: Callable[[], dict[date, str]] = dict,
    get_teams: Callable[[], list[Team]] = list,
    team_impacts: Callable[[list[Team]], list[str]] = lambda teams: [],
    on_apply_teams: Callable[[list[Team]], object] = lambda teams: None,
) -> None:
    """メンバーとパラメータのダイアログ。`適用`はタブごとで閉じない。`閉じる`は変更のあるタブを確定して閉じ、
    `キャンセル`は未適用の編集を捨てて閉じる(開いてから適用した分〔applied〕があれば、残すか rollback で戻すかを確認する)。"""
    with disposable(ui.dialog()) as dialog, ui.card() as card:
        ui.label("メンバーとパラメータ").classes("text-h6")
        with ui.tabs().mark("members-parameters-tabs") as tabs:
            with ui.tab("members", label="").mark("tab-members"), ui.row().classes("items-center no-wrap gap-1"):
                ui.label("メンバー")
                members_mark = ui.label("").classes("text-orange").mark("members-dirty")
            with ui.tab("parameters", label="").mark("tab-parameters"), ui.row().classes("items-center no-wrap gap-1"):
                ui.label("パラメータ")
                parameters_mark = ui.label("").classes("text-orange").mark("parameters-dirty")
            with ui.tab("teams", label="").mark("tab-teams"), ui.row().classes("items-center no-wrap gap-1"):
                ui.label("チーム")
                teams_mark = ui.label("").classes("text-orange").mark("teams-dirty")
        with ui.tab_panels(tabs, value="members").props("keep-alive").classes("w-full").style(
            "flex-shrink: 0"  # 縮むと、はみ出た分が overflow: hidden で切れる。カードのスクロールに任せる
        ).mark("members-parameters-panels"):
            with ui.tab_panel("members"):
                members = members_panel(
                    get_members, assigned, on_apply_members, get_parameters, get_taken, pick_icon, get_limits, get_holidays, get_teams
                )
            with ui.tab_panel("parameters"):

                def parameters_applied(edit: ParameterEdit) -> None:
                    members.parameters_changed(edit)
                    fit_width()

                parameters = parameters_panel(
                    get_parameters, impacts, on_apply_parameters, parameters_applied, get_limits
                )
            with ui.tab_panel("teams"):
                teams = teams_panel(
                    get_teams, team_impacts, on_apply_teams, lambda removed: members.teams_changed(removed), get_taken
                )

        def fit_width() -> None:
            card.style(replace=f"width: {max(36, members.min_rem() + 3)}rem; max-width: 96vw")

        def update_marks() -> None:
            members_mark.set_text("●" if members.dirty() else "")
            parameters_mark.set_text("●" if parameters.dirty() else "")
            teams_mark.set_text("●" if teams.dirty() else "")

        fit_width()
        ui.timer(0.3, update_marks)

        def close_dialog() -> None:
            dialog.close()

        def close_after_apply() -> None:
            """変更のあるタブを、パラメータ → チーム → メンバーの順に確定して閉じる。エラーのタブは表示して閉じない。"""

            def apply_members() -> None:
                if members.dirty():
                    tabs.set_value("members")
                    members.apply(close_dialog)
                else:
                    close_dialog()

            def apply_teams() -> None:
                if teams.dirty():
                    tabs.set_value("teams")
                    teams.apply(apply_members)
                else:
                    apply_members()

            if parameters.dirty():
                tabs.set_value("parameters")
                parameters.apply(apply_teams)
            else:
                apply_teams()

        def rollback_and_close() -> None:
            confirm.close()
            rollback()
            dialog.close()

        def discard_unapplied_and_close() -> None:
            confirm.close()
            dialog.close()

        with ui.dialog() as confirm, ui.card():
            ui.label("このダイアログで適用した分があります。どこまで取り消しますか。")
            with ui.row():
                ui.button("戻る", on_click=confirm.close).props("flat").mark("members-parameters-cancel-back")
                ui.button("適用しなかった分だけ取り消す", on_click=discard_unapplied_and_close).props("flat").mark(
                    "members-parameters-cancel-unapplied"
                )
                ui.button("すべて取り消す", on_click=rollback_and_close).props("color=negative").mark(
                    "members-parameters-cancel-all"
                )

        def cancel() -> None:
            if applied():
                confirm.open()
            else:
                dialog.close()

        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=cancel).props("flat").mark("members-parameters-cancel")
            ui.button("閉じる", on_click=close_after_apply).mark("members-parameters-close")
    dialog.open()


def open_handoff_dialog(
    names: list[str],
    count_for: Callable[[str], int],
    on_export: Callable[[str], Awaitable[bool]],
) -> None:
    """担当者を選んで、その担当の書き出しを頼む。`on_export` が True を返したら閉じる(キャンセル・失敗は開いたまま)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[28rem] max-w-full"):
        ui.label("担当者へ書き出し").classes("text-h6")
        select = ui.select(
            names, value=names[0], label="担当者", on_change=lambda _: update()
        ).classes("w-full").mark("handoff-member")
        info = ui.label().mark("handoff-count")

        def update() -> None:
            count = count_for(select.value)
            info.set_text(f"終了以外のタスク: {count} 件" if count else "終了以外のタスクがありません")
            export.set_enabled(count > 0)

        async def run() -> None:
            export.disable()
            closing = False
            try:
                closing = await on_export(select.value)
            finally:
                if closing:
                    dialog.close()
                else:
                    update()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            export = ui.button("書き出す", on_click=run).mark("handoff-export")
        update()
    dialog.open()
