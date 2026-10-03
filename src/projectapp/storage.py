"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import json
import os
import secrets
from dataclasses import asdict
from datetime import date, datetime, time
from math import isfinite
from pathlib import Path
from typing import Any, NamedTuple

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
    if name.endswith("."):
        return "名前は「.」で終われません"  # Windowsは末尾の . を落とす
    if name in RESERVED:
        return "この名前は使えません"
    if new and (base_dir / f"{name}.json").exists():
        return "同じ名前のプロジェクトがすでにあります"
    return None


class _Temp(NamedTuple):
    fd: int
    path: Path


def _create_temp(base_dir: Path) -> _Temp:
    """一時ファイルを作る。権限はumaskに従う(mkstempは所有者のみ)。"""
    while True:
        path = base_dir / f".save-{secrets.token_hex(8)}.tmp"
        try:
            return _Temp(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666), path)
        except FileExistsError:
            continue


def _publish_new(tmp: Path, path: Path) -> None:
    """既存のファイルを上書きせずに、一時ファイルを本来の名前にする。"""
    try:
        os.link(tmp, path)  # 既存ならFileExistsError。書き込み済みの内容が一度に現れる
    except FileExistsError:
        raise
    except OSError:
        # ハードリンクに対応しない場所(FAT/exFATなど)。同名の有無を確かめて置き換える。
        # 確認と置き換えの間の競合は防げないが、壊れたファイルは残らない。
        if path.exists():
            raise FileExistsError(path) from None
        os.replace(tmp, path)


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
    tmp = _create_temp(base_dir)
    try:
        with open(tmp.fd, "w", encoding="utf-8") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())  # 電源断で空ファイルが残るのを防ぐ
        if overwrite:
            os.replace(tmp.path, path)
        else:
            _publish_new(tmp.path, path)
    finally:
        tmp.path.unlink(missing_ok=True)
    return path


def _datetime(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _task(raw: dict[str, Any]) -> Task:
    return Task(
        name=raw["name"],
        planned_start=_datetime(raw.get("planned_start", raw.get("start"))),  # 旧形式は start
        end=_datetime(raw.get("end")),
        effort_hours=raw["effort_hours"],
        priority=Priority(raw["priority"]),
        status=Status(raw["status"]),
        color=raw["color"],
        assignee=raw.get("assignee"),
        predecessors=list(raw["predecessors"]),
        end_auto=raw.get("end_auto") is True,  # bool以外(手編集の誤り)は手入力扱い
        deadline=_datetime(raw.get("deadline")),
    )


def _daily_hours(value: Any) -> float:
    """算出側(calc_end)が受け付ける範囲: 有限の数値で、0より大きく24以下。"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("稼働可能時間が数値ではありません")
    if not isfinite(value) or not 0 < value <= 24:
        raise ValueError("稼働可能時間が範囲外です(0より大きく24以下)")
    return value


def _work_start(value: Any) -> time:
    if not isinstance(value, str):
        raise ValueError("始業時刻が文字列ではありません")
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ValueError(f"始業時刻の形式が正しくありません: {value!r}") from None


def load_project(path: Path) -> Project:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sections = [Section(s["name"], [_task(t) for t in s["tasks"]]) for s in raw["sections"]]
    members = [Member(**m) for m in raw["members"]]
    return Project(
        name=path.stem,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=_daily_hours(raw["daily_hours"]),
        work_start=_work_start(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t) for t in raw.get("tasks", [])],
    )
