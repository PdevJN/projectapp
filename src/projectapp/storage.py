"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import json
import os
import tempfile
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from projectapp.models import Member, Priority, Project, Section, Status, Task

BASE_DIR = Path.home() / ".projectapp"
RESERVED = {"config", "holidays"}
INVALID_NAME_CHARS = set('/\\:*?"<>|')


def list_project_files(base_dir: Path = BASE_DIR) -> list[Path]:
    """基準ディレクトリを走査し、保存し直せる名前のプロジェクトファイルを返す。"""
    if not base_dir.is_dir():
        return []
    return sorted(
        p
        for p in base_dir.glob("*.json")
        if p.stem == p.stem.strip() and validate_name(p.stem, base_dir, new=False) is None
    )


def _encode(value: object) -> str:
    """JSONにない日付・時刻型をISO形式の文字列にする。"""
    if isinstance(value, (date, time)):  # datetimeもdateのサブクラス
        return value.isoformat()
    raise TypeError(f"{type(value).__name__}はJSONに保存できません")


def validate_name(name: str, base_dir: Path, *, new: bool) -> str | None:
    """プロジェクト名を検証する。問題があればエラー文、なければNone。"""
    name = name.strip()
    if not name:
        return "名前を入力してください"
    if any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in name):
        return "名前に使えない文字が含まれています"
    if name.startswith("."):
        return "名前は「.」で始められません"
    if name in RESERVED:
        return "この名前は使えません"
    if new and (base_dir / f"{name}.json").exists():
        return "同じ名前のプロジェクトがすでにあります"
    return None


def save_project(
    project: Project, base_dir: Path = BASE_DIR, *, overwrite: bool = True
) -> Path:
    """一時ファイルへ書いてから置き換える。overwrite=Falseは既存ファイルを壊さない。"""
    name = project.name.strip()
    if error := validate_name(name, base_dir, new=False):
        raise ValueError(error)
    data = json.dumps(asdict(project), ensure_ascii=False, indent=2, default=_encode)
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{name}.json"
    fd, tmp_name = tempfile.mkstemp(dir=base_dir, prefix=".save-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(data)
        tmp.chmod(0o644)  # mkstempは所有者のみの権限で作る
        if overwrite:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)  # 既存ならFileExistsError
    finally:
        tmp.unlink(missing_ok=True)
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
        name=path.stem,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=raw["daily_hours"],
        work_start=time.fromisoformat(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t) for t in raw.get("tasks", [])],
    )
