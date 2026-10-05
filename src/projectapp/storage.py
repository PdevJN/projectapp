"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import json
import os
import secrets
from dataclasses import asdict
from datetime import date, datetime, time
from math import isfinite
from pathlib import Path
from typing import Any, NamedTuple

from projectapp.models import (
    ActualMode,
    MAX_ALLOCATION,
    MAX_PROGRESS,
    MAX_RATIO,
    MAX_YEAR,
    MIN_ALLOCATION,
    MIN_PROGRESS,
    MIN_RATIO,
    MIN_YEAR,
    Actual,
    Member,
    Priority,
    Project,
    Section,
    Status,
    Task,
)

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
    """日時を読む。年が範囲外(手編集の誤り)なら、描画が止まるのを防ぐためにValueError。"""
    if not text:
        return None
    moment = datetime.fromisoformat(text)
    if not MIN_YEAR <= moment.year <= MAX_YEAR:
        raise ValueError(f"日時の年は{MIN_YEAR}〜{MAX_YEAR}の範囲で指定してください: {text}")
    return moment


def _task(raw: dict[str, Any]) -> Task:
    if "planned_end_manual" in raw:  # 新形式
        planned_start = _datetime(raw.get("planned_start"))
        planned_end = _datetime(raw.get("planned_end"))
        manual = raw["planned_end_manual"] is True  # bool以外(手編集の誤り)は偽
        deadline = _datetime(raw.get("deadline"))
    else:  # 旧形式: start は開始予定、手入力の end は締切、自動算出の end は捨てる
        planned_start = _datetime(raw.get("planned_start", raw.get("start")))
        planned_end, manual = None, False
        legacy_end = None if raw.get("end_auto") is True else _datetime(raw.get("end"))
        deadline = _datetime(raw.get("deadline")) or legacy_end  # 明示された締切を優先
    return Task(
        name=raw["name"],
        planned_start=planned_start,
        planned_end=planned_end,
        planned_end_manual=manual,
        deadline=deadline,
        effort_hours=raw["effort_hours"],
        priority=Priority(raw["priority"]),
        status=_status(raw["status"]),
        color=raw["color"],
        assignee=_assignee(raw.get("assignee")),
        predecessors=list(raw["predecessors"]),
        allocation=_allocation(raw.get("allocation", 1.0)),
        actuals=_actuals(raw.get("actuals")),
    )


def _number_in_range(value: Any, low: float, high: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label}が数値ではありません")
    if not isfinite(value) or not low - 1e-9 <= value <= high + 1e-9:
        raise ValueError(f"{label}が範囲外です({low:g}以上{high:g}以下)")
    return float(value)


def _allocation(value: Any) -> float:
    return _number_in_range(value, MIN_ALLOCATION, MAX_ALLOCATION, "割り当て率")


def _actual_moment(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"実績の{label}が文字列ではありません")
    moment = _datetime(value)
    if moment is None or moment.tzinfo is not None:
        raise ValueError(f"実績の{label}の形式が正しくありません: {value!r}")
    return moment


LEGACY_STATUSES = {"開始": Status.NOT_STARTED}  # 旧名。「開始」は「未着手」に改名した


def _status(value: Any) -> Status:
    """状態を読む。旧名は新名として読む(移行は要らない)。不正はValueError。"""
    if isinstance(value, str) and value in LEGACY_STATUSES:
        return LEGACY_STATUSES[value]
    return Status(value)


def _progress(value: Any) -> int | None:
    """実績の進捗度を読む。null・キーなしは未入力。整数(boolは不可)で0〜100。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("実績の進捗度が整数ではありません")
    if not MIN_PROGRESS <= value <= MAX_PROGRESS:
        raise ValueError(f"実績の進捗度は{MIN_PROGRESS}〜{MAX_PROGRESS}で指定してください")
    return value


def _actuals(value: Any) -> list[Actual]:
    """実績を読む。キーがない・nullは実績なし。不正はValueError(開けませんでした)。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("実績がリストではありません")
    actuals: list[Actual] = []
    previous: int | None = None  # 直前に入力のあった区間の進捗度(累積なので減らない)
    for raw in value:
        if not isinstance(raw, dict) or "start" not in raw:
            raise ValueError("実績に開始がありません")
        start = _actual_moment(raw["start"], "開始")
        end = None if raw.get("end") is None else _actual_moment(raw["end"], "終了")
        if end is not None and end < start:
            raise ValueError("実績の終了が開始より前です")
        progress = _progress(raw.get("progress"))
        if progress is not None:
            if previous is not None and progress < previous:
                raise ValueError("実績の進捗度が前の区間より小さくなっています")
            previous = progress
        actuals.append(Actual(start, end, progress))
    return actuals


def _assignee(value: Any) -> str | None:
    """担当者名。前後の空白を取り除き、空はNone。"""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _members(raw_members: list[dict[str, Any]]) -> list[Member]:
    """メンバーを読む。相対比率は検証し、空の名前と重複は(最初の1件を残して)捨てる。"""
    members: list[Member] = []
    seen: set[str] = set()
    for raw in raw_members:
        name = str(raw["name"]).strip()
        ratio = _number_in_range(raw.get("ratio", 1.0), MIN_RATIO, MAX_RATIO, "相対比率")
        if not name or name in seen:
            continue
        seen.add(name)
        members.append(Member(name, ratio))
    return members


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


def _actual_mode(value: Any) -> ActualMode:
    """実績の記録方式。不正はValueError(開けませんでした)。"""
    try:
        return ActualMode(value)
    except ValueError:
        raise ValueError(f"実績の記録方式が正しくありません: {value!r}") from None


def load_project(path: Path) -> Project:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sections = [Section(s["name"], [_task(t) for t in s["tasks"]]) for s in raw["sections"]]
    members = _members(raw["members"])
    project = Project(
        name=path.stem,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=_daily_hours(raw["daily_hours"]),
        work_start=_work_start(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t) for t in raw.get("tasks", [])],
        actual_mode=_actual_mode(raw.get("actual_mode", "simple")),
    )
    known = {m.name for m in project.members}
    for task in project.all_tasks():  # 古いファイルの自由入力の担当者を、メンバーとして補う
        if task.assignee and task.assignee not in known:
            known.add(task.assignee)
            project.members.append(Member(task.assignee, 1.0))
    return project
