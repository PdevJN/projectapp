"""アプリ設定(~/.projectapp/config.json)。"""

import json
from pathlib import Path

from projectapp.storage import BASE_DIR

THEMES = ("auto", "light", "dark")


def load_theme(base_dir: Path = BASE_DIR) -> str:
    path = base_dir / "config.json"
    if not path.is_file():
        return "auto"
    theme = json.loads(path.read_text(encoding="utf-8")).get("theme", "auto")
    return theme if theme in THEMES else "auto"


def save_theme(theme: str, base_dir: Path = BASE_DIR) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / "config.json"
    path.write_text(json.dumps({"theme": theme}), encoding="utf-8")
