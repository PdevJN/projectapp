"""カテゴリ(プロジェクト共通)の検証・移行・編集。NiceGUI から切り離した純粋関数。"""

import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from projectapp.models import (
    MAX_CATEGORY_KIND_LENGTH,
    MAX_CATEGORY_NAME_LENGTH,
    MAX_PROJECT_CODE_LENGTH,
    MAX_YEAR,
    MIN_YEAR,
    Category,
    Project,
    Task,
    has_control_char,
    new_id,
)

UNDECIDED = "未定"  # 保存しない擬似カテゴリ。タスクが選ぶと category_id が None になる
COLORS = ("blue", "indigo", "purple", "pink", "red", "orange", "amber", "green", "teal", "brown")  # todoapp の色
COLOR_LABELS = {
    "blue": "青",
    "indigo": "藍",
    "purple": "紫",
    "pink": "ピンク",
    "red": "赤",
    "orange": "オレンジ",
    "amber": "琥珀",
    "green": "緑",
    "teal": "青緑",
    "brown": "茶",
}
COLOR_HEX = {
    "blue": "#2196f3",
    "indigo": "#3f51b5",
    "purple": "#9c27b0",
    "pink": "#e91e63",
    "red": "#f44336",
    "orange": "#ff9800",
    "amber": "#ffc107",
    "green": "#4caf50",
    "teal": "#009688",
    "brown": "#795548",
}
EXPIRY_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")
PRJ_CODE_FORMAT = re.compile(r"[A-Za-z0-9._-]*")  # PRJコードに使える文字(半角英数字と - _ .)。空は可


def validate_categories(categories: list[Category]) -> None:
    """カテゴリの一覧を検証する。名前は前後の空白を除いて、空・長すぎ・「未定」・重複を拒否する。名前・種別は制御文字を含むものを、PRJコードは半角英数字と - _ . 以外を含むものを拒否する。"""
    ids: set[str] = set()
    names: set[str] = set()
    for category in categories:
        if not category.id or category.id in ids:
            raise ValueError(f"カテゴリの id が正しくありません: {category.id!r}")
        ids.add(category.id)
        name = category.name.strip()
        if not name:
            raise ValueError("カテゴリの名前を入力してください")
        if name == UNDECIDED:
            raise ValueError(f"「{UNDECIDED}」はカテゴリの名前に使えません")
        if len(name) > MAX_CATEGORY_NAME_LENGTH:
            raise ValueError(f"カテゴリの名前は{MAX_CATEGORY_NAME_LENGTH}文字以内で入力してください")
        if has_control_char(name):
            raise ValueError("カテゴリの名前に改行・制御文字は使えません")
        if name in names:
            raise ValueError(f"カテゴリの名前が重複しています: {name}")
        names.add(name)
        if category.color not in COLORS:
            raise ValueError(f"カテゴリの色が正しくありません: {category.color!r}")
        if len(category.kind) > MAX_CATEGORY_KIND_LENGTH:
            raise ValueError(f"カテゴリの種別は{MAX_CATEGORY_KIND_LENGTH}文字以内で入力してください")
        if has_control_char(category.kind):
            raise ValueError("カテゴリの種別に改行・制御文字は使えません")
        if len(category.prj_code) > MAX_PROJECT_CODE_LENGTH:
            raise ValueError(f"PRJコードは{MAX_PROJECT_CODE_LENGTH}文字以内で入力してください")
        if PRJ_CODE_FORMAT.fullmatch(category.prj_code) is None:
            raise ValueError("PRJコードは半角英数字と - _ . だけで入力してください")


def parse_expiry(text: str) -> date | None:
    """有効期限。空は None。YYYY-MM-DD 以外と、年が範囲外のものは ValueError。"""
    value = text.strip()
    if not value:
        return None
    try:
        if not EXPIRY_FORMAT.fullmatch(value):
            raise ValueError
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"有効期限の形式が正しくありません(YYYY-MM-DD): {value}") from None
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise ValueError(f"有効期限の形式が正しくありません(YYYY-MM-DD): {value}")
    return parsed


def migrate_legacy(pairs: list[tuple[Task, str]], taken: Collection[str] = ()) -> list[Category]:
    """旧 ProjectCode(version 2 以前)をカテゴリへ移す。同じコードごとに 1 つ、出現順に作り、タスクの category_id を書き換える。
    名前はコードそのまま(制御文字は空白に替える)。PRJコードは、使える文字だけでできているときだけ入れる(それ以外は空。チップは名前を出す)。
    空と「未定」(予約名)のコードは、カテゴリを作らず未定のままにする。色は 10 色を出現順に巡回する。"""
    used = set(taken)
    by_name: dict[str, Category] = {}
    for task, code in pairs:
        name = "".join(" " if has_control_char(ch) else ch for ch in code).strip()
        if not name or name == UNDECIDED:
            continue
        category = by_name.get(name)
        if category is None:
            prj_code = name if PRJ_CODE_FORMAT.fullmatch(name) else ""
            category = Category(name, "", None, COLORS[len(by_name) % len(COLORS)], prj_code, new_id(used))
            used.add(category.id)
            by_name[name] = category
        task.category_id = category.id
    return list(by_name.values())


def next_color(categories: list[Category]) -> str:
    """新しい行の色。使っていない色の先頭。すべて使っていれば、数に応じて巡回する。"""
    used = {c.color for c in categories}
    for color in COLORS:
        if color not in used:
            return color
    return COLORS[len(categories) % len(COLORS)]


def count_usage(project: Project, category_id: str) -> int:
    """そのカテゴリを選んでいるタスクの数。"""
    return sum(1 for task in project.all_tasks() if task.category_id == category_id)


@dataclass(frozen=True)
class CategoryEdit:
    """設定ダイアログでのカテゴリの編集結果。"""

    categories: list[Category]  # 編集後の一覧(順序どおり)
    removed_ids: list[str]  # 削除した元のカテゴリの id


def apply_edit(project: Project, edit: CategoryEdit) -> None:
    """削除したカテゴリを選んでいたタスクを未定に戻してから、一覧を置き換える。改名は id で引き継がれるので処理は要らない。"""
    removed = set(edit.removed_ids)
    for task in project.all_tasks():
        if task.category_id in removed:
            task.category_id = None
    project.categories = list(edit.categories)


def chip_text(category: Category) -> str:
    """名前の欄のチップの文字。PRJコード、空なら名前。"""
    return category.prj_code or category.name


def by_id(categories: list[Category]) -> dict[str, Category]:
    return {c.id: c for c in categories}
