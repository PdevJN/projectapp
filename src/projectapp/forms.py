"""タスク・セクションの追加・編集の入力検証と、ファイル・名前・設定のダイアログ。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal
from math import isfinite

from nicegui import ui

from projectapp.models import (
    MAX_ALLOCATION,
    MAX_PROGRESS,
    MAX_PROJECT_CODE_LENGTH,
    MAX_RATIO,
    MAX_YEAR,
    MIN_ALLOCATION,
    MIN_PROGRESS,
    MIN_RATIO,
    MIN_YEAR,
    Actual,
    ActualMode,
    Member,
    Priority,
    Status,
    Task,
    is_hex_color,
)

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


ActualRow = tuple[str, str, float | None]  # 区間の1行の入力(開始・終了の文字列、進捗度)


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
    assignee: str,
    allocation_percent: float | None,
    actual_start: str = "",
    actual_end: str = "",
    actual_progress: float | None = None,
    actual_rows: list[ActualRow] | None = None,
    project_code: str = "",
) -> Task:
    """入力値からTaskを作る。編集時はフォームにない項目を引き継ぐ。"""
    clean = name.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    code = project_code.strip()
    if len(code) > MAX_PROJECT_CODE_LENGTH:
        raise ValueError(f"ProjectCode は{MAX_PROJECT_CODE_LENGTH}文字以内で入力してください")
    base = existing or Task(clean)
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
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    if uses_planned_end and start_at and end_at and end_at < start_at:
        raise ValueError("完了予定は開始予定以降の日時にしてください")
    assignee_name = assignee.strip()
    allocation = 1.0
    if assignee_name:
        if (
            allocation_percent is None
            or not isfinite(allocation_percent)
            or not MIN_ALLOCATION * 100 <= allocation_percent <= MAX_ALLOCATION * 100
        ):
            raise ValueError(
                f"割り当て率は{MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}%で入力してください"
            )
        allocation = round(allocation_percent / 100, 4)
    if actual_rows is not None:
        actuals = build_actual_intervals(actual_rows)
    elif len(base.actuals) > 1:
        actuals = base.actuals
    else:
        actuals = build_actuals(actual_start, actual_end, actual_progress)
    return replace(
        base,
        name=clean,
        planned_start=start_at,
        planned_end=end_at,
        planned_end_manual=manual,
        deadline=deadline_at,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignee=assignee_name or None,
        allocation=allocation,
        actuals=actuals,
        project_code=code,
    )


def build_actuals(
    start_text: str, end_text: str, progress: float | None = None
) -> list[Actual]:
    """実績の入力(compose_actual の結果と進捗度)を検証して、0件か1件の区間にする。"""
    try:
        start_at, end_at = parse_datetime(start_text), parse_datetime(end_text)
    except ValueError:
        raise ValueError("実績の日時の形式が正しくありません") from None
    percent = _check_progress(progress)
    if start_at is None:
        if end_at is not None or percent is not None:
            raise ValueError("実績の開始を入れてください")
        return []
    for moment in (start_at, end_at):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if end_at is not None and end_at < start_at:
        raise ValueError("実績の終了は開始以降の日時にしてください")
    return [Actual(start_at, end_at, percent)]


def build_actual_intervals(rows: list[ActualRow]) -> list[Actual]:
    """区間の行の入力を検証して、区間のリストにする。すべて空の行は無視する(行番号は数える)。
    開始の昇順、重ならない、終了のない区間は最後の1つだけ、進捗度は前の入力以上。"""
    kept: list[tuple[int, Actual]] = []
    for number, (start_text, end_text, progress) in enumerate(rows, start=1):
        if not start_text and not end_text and progress is None:
            continue
        try:
            built = build_actuals(start_text, end_text, progress)
        except ValueError as exc:
            raise ValueError(f"区間 {number}: {exc}") from None
        kept.append((number, built[0]))
    previous: tuple[int, Actual] | None = None
    last_progress: int | None = None
    for number, actual in kept:
        if previous is not None:
            before_number, before = previous
            if before.end is None:
                raise ValueError(f"区間 {before_number}: 終了のない区間は最後の1つだけにしてください")
            if actual.start < before.start:
                raise ValueError("区間は開始の早い順に入れてください")
            if actual.start < before.end:
                raise ValueError(f"区間 {number}: 前の区間と重なっています")
        if actual.progress is not None:
            if last_progress is not None and actual.progress < last_progress:
                raise ValueError(f"区間 {number}: 進捗度は前の区間以上にしてください")
            last_progress = actual.progress
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


@dataclass
class MemberRow:
    """メンバーのダイアログの1行。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    ratio_percent: float | None


def build_members(
    rows: list[MemberRow], originals: list[str], assigned: Callable[[str], int]
) -> tuple[list[Member], dict[str, str]]:
    """ダイアログの行を検証して、メンバー一覧と、改名の対応({旧: 新})を返す。"""
    members: list[Member] = []
    renames: dict[str, str] = {}
    seen: set[str] = set()
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
        members.append(Member(name, round(ratio / 100, 4)))
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


def open_section_dialog(on_save: Callable[[str], object]) -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label("セクションの追加").classes("text-h6")
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
    on_submit: Callable[[str], object], validate: Callable[[str], str | None]
) -> None:
    """名前を入力して保存する。on_submitがFalseを返したら(保存に失敗)、入力を残して開いたままにする。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label("プロジェクトの保存").classes("text-h6")
        name = ui.input("プロジェクト名").mark("project-name")
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
    on_save: Callable[[], object], on_discard: Callable[[], object]
) -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("保存されていない変更があります").classes("text-h6")
        ui.label("開く前に、現在のプロジェクトを保存しますか。")

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("unsaved-cancel")
            ui.button("保存せず開く", on_click=lambda: run(on_discard)).props(
                "flat color=negative"
            ).mark("unsaved-discard")
            ui.button("保存して開く", on_click=lambda: run(on_save)).mark("unsaved-save")
    dialog.open()


def open_settings_dialog(
    daily_hours: float,
    work_start: time,
    on_apply: Callable[[float, time, ActualMode], object],
    actual_mode: ActualMode = ActualMode.SIMPLE,
    multi_interval_tasks: int = 0,
) -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
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
        error = ui.label("").classes("text-negative").mark("settings-error")

        def apply() -> None:
            try:
                result = build_work_settings(hours.value, start.value or "")
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_apply(*result, ActualMode(mode.value))
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("settings-apply")
    dialog.open()


def open_members_dialog(
    members: list[Member],
    assigned: Callable[[str], int],
    on_apply: Callable[[list[Member], dict[str, str]], object],
) -> None:
    rows = [MemberRow(m.name, m.name, round(m.ratio * 100, 2)) for m in members]
    originals = [m.name for m in members]
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[28rem] max-w-full"):
        ui.label("メンバー").classes("text-h6")

        @ui.refreshable
        def table() -> None:
            with ui.column().classes("w-full gap-1"):
                if not rows:
                    ui.label("メンバーがいません").classes("text-grey")
                for index, row in enumerate(rows):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.input(
                            "名前",
                            value=row.name,
                            on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                        ).classes("flex-1").mark(f"member-name-{index}")
                        ui.number(
                            "相対比率(%)",
                            value=row.ratio_percent,
                            min=MIN_RATIO * 100,
                            max=MAX_RATIO * 100,
                            step=5,
                            on_change=lambda e, r=row: setattr(r, "ratio_percent", e.value),
                        ).classes("w-32").mark(f"member-ratio-{index}")
                        ui.button(icon="delete", on_click=lambda r=row: remove(r)).props(
                            "flat dense round"
                        ).mark(f"member-delete-{index}")

        def remove(row: MemberRow) -> None:
            rows.remove(row)
            table.refresh()

        def add() -> None:
            rows.append(MemberRow(None, "", 100.0))
            table.refresh()

        table()
        ui.button("メンバーを追加", icon="add", on_click=add).props("flat").mark("member-add")
        error = ui.label("").classes("text-negative").mark("member-error")

        def apply() -> None:
            try:
                result = build_members(rows, originals, assigned)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_apply(*result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("member-apply")
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
