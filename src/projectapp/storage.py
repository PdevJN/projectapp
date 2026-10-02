"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import json
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from projectapp.models import Member, Priority, Project, Section, Status, Task

BASE_DIR = Path.home() / ".projectapp"
RESERVED = {"config", "holidays"}


def list_project_files(base_dir: Path = BASE_DIR) -> list[Path]:
    """基準ディレクトリを走査し、プロジェクトファイルを返す。"""
    if not base_dir.is_dir():
        return []
    return sorted(p for p in base_dir.glob("*.json") if p.stem not in RESERVED)


def _encode(value: object) -> str:
    """JSONにない日付・時刻型をISO形式の文字列にする。"""
    if isinstance(value, (date, time)):  # datetimeもdateのサブクラス
        return value.isoformat()
    raise TypeError(f"{type(value).__name__}はJSONに保存できません")


def save_project(project: Project, base_dir: Path = BASE_DIR) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{project.name}.json"
    data = json.dumps(asdict(project), ensure_ascii=False, indent=2, default=_encode)
    path.write_text(data, encoding="utf-8")
    return path


def _datetime(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _task(raw: dict[str, Any]) -> Task:
    return Task(
        name=raw["name"],
        start=_datetime(raw.get("start")),
        end=_datetime(raw.get("end")),
        effort_hours=raw["effort_hours"],
        priority=Priority(raw["priority"]),
        status=Status(raw["status"]),
        color=raw["color"],
        assignee=raw.get("assignee"),
        predecessors=list(raw["predecessors"]),
    )


def load_project(path: Path) -> Project:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sections = [Section(s["name"], [_task(t) for t in s["tasks"]]) for s in raw["sections"]]
    members = [Member(**m) for m in raw["members"]]
    return Project(
        name=raw["name"],
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=raw["daily_hours"],
        work_start=time.fromisoformat(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t) for t in raw.get("tasks", [])],
    )
