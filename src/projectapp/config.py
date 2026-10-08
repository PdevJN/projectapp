"""アプリ設定(~/.projectapp/config.json)。"""

import json
import os
import secrets
from math import isfinite
from pathlib import Path

from projectapp.storage import BASE_DIR

THEMES = ("auto", "light", "dark")
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
