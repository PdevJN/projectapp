"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import json
from dataclasses import asdict
from pathlib import Path

from projectapp.models import Member, Project, Section, Task

BASE_DIR = Path.home() / ".projectapp"
RESERVED = {"config", "holidays"}


def list_project_files(base_dir: Path = BASE_DIR) -> list[Path]:
    """基準ディレクトリを走査し、プロジェクトファイルを返す。"""
    if not base_dir.is_dir():
        return []
    return sorted(p for p in base_dir.glob("*.json") if p.stem not in RESERVED)


def save_project(project: Project, base_dir: Path = BASE_DIR) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{project.name}.json"
    data = json.dumps(asdict(project), ensure_ascii=False, indent=2, default=str)
    path.write_text(data, encoding="utf-8")
    return path


def load_project(path: Path) -> Project:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sections = [
        Section(s["name"], [Task(**t) for t in s["tasks"]]) for s in raw["sections"]
    ]
    members = [Member(**m) for m in raw["members"]]
    return Project(
        name=raw["name"],
        daily_hours=raw["daily_hours"],
        members=members,
        sections=sections,
    )
