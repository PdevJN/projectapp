"""アプリ設定(~/.projectapp/config.json)。"""

import json
import os
import secrets
from math import isfinite
from pathlib import Path

from projectapp.dashboard_views import ViewSpec, views_from_config, views_to_config
from projectapp.storage import BASE_DIR
from projectapp.theme import CustomTheme, custom_theme_to_dict, parse_custom_theme, parse_today_color

THEMES = ("auto", "light", "dark", "custom")
TASK_SECTION_KEYS = ("assignees", "actuals", "related")  # タスクのダイアログの、折りたためる節(基本は常に開く)
DEFAULT_NAME_WIDTH_PX = 200  # ガントチャートの名前の欄の幅
MIN_NAME_WIDTH_PX = 120
MAX_NAME_WIDTH_PX = 480
MIN_ZOOM_PERCENT = 70  # 画面全体の拡大・縮小(%)
DEFAULT_ZOOM_PERCENT = 100
MAX_ZOOM_PERCENT = 200
ZOOM_STEP_PERCENT = 10


def parse_name_width(value: object) -> int | None:
    """名前の欄の幅(px)の検証。有限の数(真偽値でない)を、丸めて、範囲に収める。それ以外は None。"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    return min(max(round(value), MIN_NAME_WIDTH_PX), MAX_NAME_WIDTH_PX)


def read_config(base_dir: Path) -> dict:
    """設定ファイルの中身。ファイルがないか、オブジェクトでなければ、空。"""
    path = base_dir / "config.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def update_config(updates: dict, base_dir: Path) -> None:
    """指定のキーだけを更新して書く(ほかのキーは残す)。一時ファイル経由で置き換え、失敗しても元のファイルを残す。"""
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / "config.json"
    data = json.dumps({**read_config(base_dir), **updates})
    tmp = path.with_name(f".config.json.{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_theme(base_dir: Path = BASE_DIR) -> str:
    theme = read_config(base_dir).get("theme", "auto")
    return theme if theme in THEMES else "auto"


def save_theme(theme: str, base_dir: Path = BASE_DIR) -> None:
    update_config({"theme": theme}, base_dir)


def load_custom_theme(base_dir: Path = BASE_DIR) -> CustomTheme:
    return parse_custom_theme(read_config(base_dir).get("custom_theme"))


def save_custom_theme(theme: CustomTheme, base_dir: Path = BASE_DIR, select: bool = False) -> None:
    """カスタムの色を保存する。`select`が真なら、テーマも`custom`にして、1 回の書き込みで保存する。"""
    updates: dict = {"custom_theme": custom_theme_to_dict(theme)}
    if select:
        updates["theme"] = "custom"
    update_config(updates, base_dir)


def load_today_color(base_dir: Path = BASE_DIR) -> str | None:
    """今日の線の色(`#rrggbb`)。未設定・不正は None(既定の色)。"""
    return parse_today_color(read_config(base_dir).get("today_color"))


def save_today_color(color: str | None, base_dir: Path = BASE_DIR) -> None:
    """None は既定に戻す(キーを消す代わりに null を書く)。"""
    update_config({"today_color": color}, base_dir)


def load_task_sections(base_dir: Path = BASE_DIR) -> list[str] | None:
    """開いている節のキー(節の順)。保存がない・不正(リストでない、未知のキーを含む)は None。"""
    value = read_config(base_dir).get("task_sections")
    if not isinstance(value, list) or any(key not in TASK_SECTION_KEYS for key in value):
        return None
    return [key for key in TASK_SECTION_KEYS if key in value]


def save_task_sections(keys: list[str], base_dir: Path = BASE_DIR) -> None:
    update_config({"task_sections": [key for key in TASK_SECTION_KEYS if key in keys]}, base_dir)


def load_dashboard_views(base_dir: Path = BASE_DIR) -> list[ViewSpec]:
    """保存したダッシュボードのビュー(`標準` を含まない)。読めないときは空。"""
    try:
        raw = read_config(base_dir).get("dashboard_views")
    except (OSError, ValueError):
        return []
    return views_from_config(raw)


def save_dashboard_views(views: list[ViewSpec], base_dir: Path = BASE_DIR) -> None:
    update_config({"dashboard_views": views_to_config(views)}, base_dir)


def load_dashboard_view_last(base_dir: Path = BASE_DIR) -> str | None:
    """最後に使ったダッシュボードのビューの名前。読めないときは None。"""
    try:
        name = read_config(base_dir).get("dashboard_view_last")
    except (OSError, ValueError):
        return None
    return name if isinstance(name, str) and name else None


def save_dashboard_view_last(name: str, base_dir: Path = BASE_DIR) -> None:
    update_config({"dashboard_view_last": name}, base_dir)


def load_name_width(base_dir: Path = BASE_DIR) -> int:
    width = parse_name_width(read_config(base_dir).get("name_width"))
    return DEFAULT_NAME_WIDTH_PX if width is None else width


def save_name_width(width: int, base_dir: Path = BASE_DIR) -> None:
    update_config({"name_width": width}, base_dir)


def parse_zoom(value: object) -> int | None:
    """画面の倍率(%)の検証。有限の数(真偽値でない)を、丸めて、範囲に収める。それ以外は None。"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    return min(max(round(value), MIN_ZOOM_PERCENT), MAX_ZOOM_PERCENT)


def step_zoom(current: int, direction: int) -> int:
    """倍率を 1 刻み動かす(+1 拡大・-1 縮小)。刻みからずれた値は、次の刻みへそろえる。0 は既定へ戻す。"""
    if direction == 0:
        return DEFAULT_ZOOM_PERCENT
    step = ZOOM_STEP_PERCENT
    if direction > 0:
        value = (current // step + 1) * step
    else:
        value = (-(-current // step) - 1) * step
    return min(max(value, MIN_ZOOM_PERCENT), MAX_ZOOM_PERCENT)


def load_zoom(base_dir: Path = BASE_DIR) -> int:
    zoom = parse_zoom(read_config(base_dir).get("zoom"))
    return DEFAULT_ZOOM_PERCENT if zoom is None else zoom


def save_zoom(zoom: int, base_dir: Path = BASE_DIR) -> None:
    update_config({"zoom": zoom}, base_dir)


PROJECT_DIR_MISSING_MESSAGE = "格納先が見つからないため、既定の場所を使っています"


def load_project_dir(base_dir: Path = BASE_DIR) -> Path | None:
    """プロジェクトの格納先。未設定・文字列でない・空・相対パスは None(`~` は展開する)。"""
    value = read_config(base_dir).get("project_dir")
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip()).expanduser()
    return path if path.is_absolute() else None


def save_project_dir(path: Path, base_dir: Path = BASE_DIR) -> None:
    update_config({"project_dir": str(path)}, base_dir)


def check_project_dir(path: Path) -> str | None:
    """格納先として使えるか。使えなければ理由を返す(ファイルは作らない。空のフォルダは使える)。"""
    if not path.exists():
        return "フォルダが見つかりません"
    if not path.is_dir():
        return "フォルダではありません"
    if not os.access(path, os.W_OK | os.X_OK):
        return "書き込めません"
    return None


def resolve_project_dir(base_dir: Path = BASE_DIR) -> tuple[Path, str | None]:
    """起動時に使う格納先と、通知する文言。保存した格納先が使えなければ、`base_dir` を使う(設定は書き換えない)。"""
    saved = load_project_dir(base_dir)
    if saved is None:
        return base_dir, None
    if check_project_dir(saved) is not None:
        return base_dir, PROJECT_DIR_MISSING_MESSAGE
    return saved, None
