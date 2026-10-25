"""期間の欄(`2026-10-01 〜 2026-10-31`)の読み書きと、範囲カレンダー。プレビュー・メイン・ダッシュボードが共用する。"""

import re
from datetime import date, datetime

from nicegui import ui

from projectapp.dateinput import parse_date_input
from projectapp.models import MAX_YEAR, MIN_YEAR
from projectapp.timeline import Scale

PERIOD_SEPARATOR = " 〜 "
PERIOD_SEPARATOR_PATTERN = re.compile(r"\s*[〜~～]\s*")  # 日付の区切りの `-` と混ざらないよう、波ダッシュだけ
PERIOD_ORDER_MESSAGE = "期間は、開始日が終了日以前になるように入れてください"
# 列が多すぎると、描き直しでブラウザとサーバが固まる。日次は約2年まで(1年強は問題なく出せる)
MAX_COLUMNS = {Scale.DAY: 800, Scale.WEEK: 400, Scale.MONTH: 240}
COLUMN_UNITS = {Scale.DAY: "日", Scale.WEEK: "週", Scale.MONTH: "か月"}


def validate_period(start_text: str, end_text: str) -> tuple[date, date]:
    """期間の入力(YYYY-MM-DD)を検証する。開始日は終了日以前。"""
    try:
        start = datetime.strptime((start_text or "").strip(), "%Y-%m-%d").date()
        end = datetime.strptime((end_text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("日付の形式が正しくありません(YYYY-MM-DD)") from None
    if not (MIN_YEAR <= start.year <= MAX_YEAR and MIN_YEAR <= end.year <= MAX_YEAR):
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if start > end:
        raise ValueError(PERIOD_ORDER_MESSAGE)
    return start, end


def format_period(start: date, end: date) -> str:
    """期間の欄の文字列(`2026-10-01 〜 2026-10-31`)。"""
    return f"{start.isoformat()}{PERIOD_SEPARATOR}{end.isoformat()}"


def split_period(text: str) -> tuple[str, str]:
    """期間の欄の文字列を (開始, 終了) の文字列に分ける。区切りが 1 つでないときは (全体, "") で、検証でエラーになる。"""
    parts = PERIOD_SEPARATOR_PATTERN.split((text or "").strip())
    return (parts[0], parts[1]) if len(parts) == 2 else ((text or "").strip(), "")


def normalize_period(text: str, today: date) -> str | None:
    """両端の省略形(`10/15`・`1015`・`20261015`)を `YYYY-MM-DD` にした期間の文字列。読めないときは None。過ぎた日でも翌年にしない。"""
    start, end = split_period(text)
    fixed_start, fixed_end = parse_date_input(start, today, False), parse_date_input(end, today, False)
    if fixed_start is None or fixed_end is None:
        return None
    return f"{fixed_start}{PERIOD_SEPARATOR}{fixed_end}"


def parse_range_value(value: object) -> tuple[str, str] | None:
    """範囲カレンダーの値を (開始, 終了) にする。同じ日を 2 回押すと日付の文字列で届くので、1 日の範囲とする。未選択・片側だけは None。"""
    if isinstance(value, str):
        return (value, value) if value else None
    if not isinstance(value, dict):
        return None
    first, last = value.get("from"), value.get("to")
    if isinstance(first, str) and isinstance(last, str) and first and last:
        return first, last
    return None


def check_column_count(scale: Scale, count: int) -> str | None:
    """列の数がスケールごとの上限を超えるときの、エラー文。収まるなら None。"""
    limit = MAX_COLUMNS[scale]
    if count <= limit:
        return None
    return f"期間が長すぎます({scale.value}は最大{limit}{COLUMN_UNITS[scale]}。期間かスケールを変えてください)"


def add_range_picker(field: ui.input, key: str) -> None:
    """期間の欄の右に、範囲カレンダーを開くアイコンを足す。OK で欄に反映する。選んでいる途中は OK を押せない。マーカーは `{key}-range-picker` など。"""
    with ui.dialog() as dialog, ui.card():
        picker = ui.date().props("range").mark(f"{key}-range-picker")
        ok = ui.button("OK").mark(f"{key}-range-picker-ok")

    def on_pick(_event: object = None) -> None:
        ok.set_enabled(parse_range_value(picker.value) is not None)

    def open_picker() -> None:
        try:
            current = validate_period(*split_period(field.value or ""))
        except ValueError:
            picker.set_value(None)  # 空・不正・開始が終了より後のときは、選択なしで開く
        else:
            picker.set_value({"from": current[0].isoformat(), "to": current[1].isoformat()})
        on_pick()
        dialog.open()

    def apply() -> None:
        chosen = parse_range_value(picker.value)
        if chosen is None:
            return
        field.set_value(f"{chosen[0]}{PERIOD_SEPARATOR}{chosen[1]}")
        dialog.close()

    picker.on_value_change(on_pick)
    # Quasar は 1 回目のクリックでは値を送らない。選んでいる途中は前の範囲を適用させず、2 回目(rangeEnd)で値から判定し直す
    picker.on("rangeStart", lambda _e: ok.disable())
    picker.on("rangeEnd", on_pick)
    ok.on_click(apply)
    with field.add_slot("append"):
        ui.icon("date_range").classes("cursor-pointer").on("click", open_picker).mark(f"open-{key}-range-picker")
