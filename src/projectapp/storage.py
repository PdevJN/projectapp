"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import hashlib
import json
import os
import re
import secrets
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any, NamedTuple

from projectapp.categories import COLORS, migrate_legacy, parse_expiry, validate_categories
from projectapp.events import normalize_color, validate_events
from projectapp.icons import is_valid_icon
from projectapp.linkgraph import validate_links
from projectapp.models import (
    OverloadSpan,
    ReferenceMode,
    ReferenceValue,
    FORMAT_VERSION,
    MAX_WARNING_LIMIT,
    MIN_WARNING_LIMIT,
    MAX_WEEKS,
    union_assignees,
    CHECKPOINT_STATUSES,
    ID_KEY,
    URL_KEY,
    ActualMode,
    MAX_ALLOCATION,
    DEFAULT_RATIO_MAX,
    DEFAULT_RATIO_MIN,
    MAX_LEVEL_VALUE,
    MAX_PROJECT_CODE_LENGTH,
    MAX_PROGRESS,
    MAX_RATIO,
    MAX_SECTION_DEPTH,
    MAX_YEAR,
    MIN_ALLOCATION,
    MIN_LEVEL_VALUE,
    MIN_PROGRESS,
    MIN_RATIO,
    RatioLimits,
    MIN_YEAR,
    Actual,
    Assignee,
    Category,
    Event,
    Level,
    Member,
    Membership,
    Parameter,
    Priority,
    Project,
    Team,
    Section,
    Status,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
    WorkDay,
    new_id,
    tidy_task_name,
    walk_sections,
)
from projectapp.teams import membership_error, team_name_error
from projectapp.workdays import sort_work_days, validate_work_days
from projectapp.urls import validate_templates, validate_urls

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


def _task_dicts(tasks: list[dict[str, Any]], sections: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    yield from tasks
    for section in sections:
        yield from _task_dicts(section["tasks"], section["sections"])


def _check_unique_ids(project: Project) -> None:
    """タスク同士・メンバー同士・セクション同士などの id の重複と、読めないチームの所属があれば ValueError(読めないファイルを書かない)。"""
    groups = {
        "タスク": [t.id for t in project.all_tasks()],
        "メンバー": [m.id for m in project.members],
        "セクション": [s.id for _, s in walk_sections(project.sections)],
        "カテゴリ": [c.id for c in project.categories],
        "イベント": [e.id for e in project.events],
        "チーム": [t.id for t in project.teams],
    }
    for label, ids in groups.items():
        if len(set(ids)) != len(ids):
            raise ValueError(f"{label}の id が重複しています")
    team_ids = {t.id for t in project.teams}
    for member in project.members:
        error = membership_error(member.teams, team_ids)
        if error is not None:
            raise ValueError(f"{member.name}: {error}")


def _dump(project: Project) -> dict[str, Any]:
    """ファイルに書く辞書。担当者は名前ではなくメンバー id で指す。メンバーにいない名前は、メンバーを補う(実行時のプロジェクトは変えない)。"""
    data: dict[str, Any] = {"version": FORMAT_VERSION, **asdict(project)}
    for saved, member in zip(data["members"], project.members):
        saved["work_days"] = [asdict(row) for row in sort_work_days(member.work_days)]
    ids: dict[str, str] = {}
    for member in data["members"]:
        ids.setdefault(member["name"], member["id"])  # 同名は最初の 1 件を指す(読込が残すのも最初の 1 件)
    taken = project.used_ids()

    def refs_of(assignees: list[dict[str, Any]]) -> list[dict[str, Any]]:
        refs = []
        for assignee in assignees:
            name = assignee["name"]
            if name not in ids:
                ids[name] = new_id(taken)
                taken.add(ids[name])
                data["members"].append({"name": name, "ratio": 1.0, "levels": {}, "id": ids[name], "icon": "", "work_days": [], "teams": []})
            refs.append({"member": ids[name], "allocation": assignee["allocation"]})
        return refs

    for task in _task_dicts(data["tasks"], data["sections"]):
        task["assignees"] = refs_of(task["assignees"])
        task["weekly_crew"] = [refs_of(week) for week in task["weekly_crew"]]
    return data


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


class ExternalChange(Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"


def file_digest(path: Path) -> str | None:
    """ファイルの内容の SHA-256(16 進)。なければ None。更新時刻は使わない(git や同期は内容が同じでも変える)。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def check_external_change(path: Path, digest: str | None) -> ExternalChange:
    """読み込んだときのハッシュ `digest` と、いまのファイルを比べる。覚えていなければ判定できないので UNCHANGED。"""
    current = file_digest(path)
    if current is None:
        return ExternalChange.MISSING
    if digest is None or current == digest:
        return ExternalChange.UNCHANGED
    return ExternalChange.CHANGED


def backup_file(path: Path) -> Path:
    """同じ場所の `<名前>.json.bak` に退避する(1 世代。既存は置き換える)。失敗は OSError のまま通す。"""
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    return backup


def dumps_project(project: Project) -> str:
    """ファイルに書く JSON 文字列。id が重複していれば`ValueError`(読めないファイルを作らない)。"""
    _check_unique_ids(project)
    return json.dumps(_dump(project), ensure_ascii=False, indent=2, default=_encode)


def save_project(
    project: Project, base_dir: Path = BASE_DIR, *, overwrite: bool = True
) -> Path:
    """一時ファイルへ書いてから置き換える。overwrite=Falseは既存ファイルを壊さない。"""
    name = project.name.strip()
    if error := validate_name(name, base_dir, new=False):
        raise ValueError(error)
    data = dumps_project(project)
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


def _task(raw: dict[str, Any], ctx: "_Context") -> Task:
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
    kind = _kind(raw.get("kind"))
    actuals, legacy_progress = _actuals(raw.get("actuals"))
    weekly = _weekly_crew(raw.get("weekly_crew"), ctx) if ctx.version >= 10 else []
    assignees = union_assignees(weekly) if weekly else _assignees(raw, ctx)  # 週ごとのタスクの担当は週の表が正
    task = Task(
        name=_task_name(raw.get("name")),
        id=_task_id(raw.get("id")),
        planned_start=planned_start,
        planned_end=planned_end,
        planned_end_manual=manual,
        deadline=deadline,
        effort_hours=raw["effort_hours"],
        priority=Priority(raw["priority"]),
        status=_status(raw["status"]),
        color=raw["color"],
        assignees=assignees,
        weekly_crew=weekly,
        predecessors=_predecessors(raw.get("predecessors")),
        actuals=actuals,
        kind=kind,
        urls=_task_urls(raw.get("urls")),
        progress=_task_progress(raw, ctx.version, legacy_progress),
        category_id=_category_id(raw.get("category_id")) if ctx.version >= 3 else None,
        children=_children(raw.get("children")) if ctx.version >= 6 else [],
        parameters=_parameter_names(raw.get("parameters")),
        ref_project=_ref_project(raw.get("ref_project")) if kind is TaskKind.REFERENCE else "",
        ref_snapshot=_reference_value(raw.get("ref_snapshot")) if ctx.version >= 11 else None,
    )
    if kind is TaskKind.CHECKPOINT:
        result = _checkpoint(task)
    elif kind is TaskKind.SUMMARY:
        result = _summary(task)
    elif kind is TaskKind.REFERENCE:
        result = _reference(task)
    else:
        result = task
    if ctx.version < 3:
        ctx.legacy_codes[id(result)] = _project_code(raw.get("project_code"))  # 読込の最後に、カテゴリへ移す
    if raw.get("id") is None:
        ctx.pending.append(result)  # 読込の最後に、ファイルの他の id と重ならない id を振る
    return result


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


def _progress(value: Any, label: str = "実績の進捗度") -> int | None:
    """進捗度を読む。null・キーなしは未入力。整数(boolは不可)で0〜100。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label}が整数ではありません")
    if not MIN_PROGRESS <= value <= MAX_PROGRESS:
        raise ValueError(f"{label}は{MIN_PROGRESS}〜{MAX_PROGRESS}で指定してください")
    return value


def _task_progress(raw: dict[str, Any], version: int, legacy: int | None) -> int | None:
    """タスクの進捗度。古いファイルの実績の区間に進捗度があれば、入っている最後の値を使う(従来の優先順位のまま)。"""
    own = _progress(raw.get("progress"), "進捗度") if version >= 5 else None
    return legacy if legacy is not None else own


def _actuals(value: Any) -> tuple[list[Actual], int | None]:
    """実績を読む。キーがない・nullは実績なし。不正はValueError(開けませんでした)。
    区間の進捗度は廃止したので、Actual には入れず、入っている最後の値を別に返す。"""
    if value is None:
        return [], None
    if not isinstance(value, list):
        raise ValueError("実績がリストではありません")
    actuals: list[Actual] = []
    last_progress: int | None = None
    for raw in value:
        if not isinstance(raw, dict) or "start" not in raw:
            raise ValueError("実績に開始がありません")
        start = _actual_moment(raw["start"], "開始")
        end = None if raw.get("end") is None else _actual_moment(raw["end"], "終了")
        if end is not None and end < start:
            raise ValueError("実績の終了が開始より前です")
        progress = _progress(raw.get("progress"))
        if progress is not None:
            last_progress = progress
        actuals.append(Actual(start, end))
    return actuals, last_progress


def _project_code(value: Any) -> str:
    """ProjectCode。キーがない・nullは空。文字列以外と長すぎるものはValueError(開けませんでした)。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"ProjectCodeが文字列ではありません: {value!r}")
    code = value.strip()
    if len(code) > MAX_PROJECT_CODE_LENGTH:
        raise ValueError(f"ProjectCodeが{MAX_PROJECT_CODE_LENGTH}文字を超えています")
    return code


def _category_id(value: Any) -> str | None:
    """タスクのカテゴリ id。キーがない・null は未定。空・文字列以外は ValueError(存在の検証は読込の後で行う)。"""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"タスクのカテゴリの id が正しくありません: {value!r}")
    return value


def _optional_text(value: Any, label: str) -> str:
    """カテゴリの文字列の項目。キーがない・null は空。文字列以外は ValueError。前後の空白を除く。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label}が文字列ではありません: {value!r}")
    return value.strip()


def _categories(value: Any) -> list[Category]:
    """カテゴリ(version 3)。キーがない・null は空。名前の空・重複・予約名、色・日付・長さの不正は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("カテゴリがリストではありません")
    categories: list[Category] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("カテゴリの形式が正しくありません")
        name = raw.get("name")
        if not isinstance(name, str):
            raise ValueError("カテゴリの名前が文字列ではありません")
        expiry = raw.get("expiry_date")
        if expiry is not None and not isinstance(expiry, str):
            raise ValueError(f"カテゴリの有効期限が文字列ではありません: {expiry!r}")
        color = raw.get("color", "blue")
        if color not in COLORS:  # 文字列以外も、ここで落ちる
            raise ValueError(f"カテゴリの色が正しくありません: {color!r}")
        categories.append(
            Category(
                name.strip(),
                _optional_text(raw.get("kind"), "カテゴリの種別"),
                parse_expiry(expiry or ""),
                color,
                _optional_text(raw.get("prj_code"), "PRJコード"),
                _entity_id(raw.get("id"), "カテゴリ"),
            )
        )
    validate_categories(categories)
    return categories


_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _iso_date(text: Any, label: str) -> date:
    if not isinstance(text, str) or _ISO_DATE.fullmatch(text) is None:
        raise ValueError(f"イベントの{label}が YYYY-MM-DD ではありません: {text!r}")
    return date.fromisoformat(text)


def _teams(value: Any) -> list[Team]:
    """チーム(version 17)。キーがない・null は空。名前の空・重複・長さ・制御文字、id の不正・重複は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("チームがリストではありません")
    teams: list[Team] = []
    names: set[str] = set()
    ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("チームの形式が正しくありません")
        name = raw.get("name")
        if not isinstance(name, str):
            raise ValueError("チームの名前が文字列ではありません")
        error = team_name_error(name, names)
        if error is not None:
            raise ValueError(error)
        team_id = _entity_id(raw.get("id"), "チーム")
        if team_id in ids:
            raise ValueError(f"チームの id が重複しています: {team_id}")
        names.add(name.strip())
        ids.add(team_id)
        teams.append(Team(name.strip(), team_id))
    return teams


def _memberships(value: Any, team_ids: set[str]) -> list[Membership]:
    """メンバーの所属(version 17)。キーがない・null は空。存在しないチーム・重複・割合の不正・合計が 100 でないものは ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("メンバーの所属がリストではありません")
    rows: list[Membership] = []
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("team_id"), str):
            raise ValueError("メンバーの所属の形式が正しくありません")
        rows.append(Membership(raw["team_id"], raw.get("percent")))  # type: ignore[arg-type]  # 割合の型は membership_error が見る
    error = membership_error(rows, team_ids)
    if error is not None:
        raise ValueError(error)
    return rows


def _events(value: Any, version: int = FORMAT_VERSION) -> list[Event]:
    """イベント(version 4)。キーがない・null は空。日付・文字列・色・id の不正は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("イベントがリストではありません")
    events: list[Event] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("イベントの形式が正しくありません")
        dates = [_iso_date(raw.get("start"), "開始日"), _iso_date(raw.get("end"), "終了日")]
        text = raw.get("text")
        if not isinstance(text, str):
            raise ValueError(f"イベントの文字列が文字列ではありません: {text!r}")
        color = raw.get("color", "gray")
        normalized = normalize_color(color) if isinstance(color, str) else None
        if normalized is None:
            raise ValueError(f"イベントの色が正しくありません: {color!r}(#RRGGBB か、red・orange・gray などの色名)")
        closed = raw.get("closed", False) if version >= 15 else False
        if not isinstance(closed, bool):
            raise ValueError(f"イベントの休みが真偽値ではありません: {closed!r}")
        events.append(
            Event(dates[0], dates[1], text.strip(), normalized, _entity_id(raw.get("id"), "イベント"), closed=closed)
        )
    validate_events(events)
    return events


def _work_days(value: Any, version: int = FORMAT_VERSION) -> list[WorkDay]:
    """稼働日の上書き(version 8)。キーがない・null は空。形・時刻・重複の不正は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("稼働日の上書きがリストではありません")
    rows: list[WorkDay] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("稼働日の上書きの形式が正しくありません")
        try:
            day = _iso_date(raw.get("day"), "日付")
        except ValueError as exc:
            raise ValueError(str(exc).replace("イベントの", "稼働日の")) from None
        times: list[time | None] = []
        for key in ("start", "end"):
            text = raw.get(key)
            if text is None:
                times.append(None)
            elif isinstance(text, str):
                try:
                    if not _CLOCK.fullmatch(text):
                        raise ValueError(text)
                    times.append(time.fromisoformat(text))
                except ValueError:
                    raise ValueError(f"稼働日の{key}の形式が正しくありません: {text!r}") from None
            else:
                raise ValueError(f"稼働日の{key}が文字列ではありません: {text!r}")
        note = raw.get("note") if version >= 14 else None
        if note is None:
            note = ""
        elif not isinstance(note, str):
            raise ValueError(f"稼働日のメモが文字列ではありません: {note!r}")
        rows.append(WorkDay(day, times[0], times[1], note.strip()))
    validate_work_days(rows)
    return sort_work_days(rows)


_CLOCK = re.compile(r"\d{2}:\d{2}(:00)?")  # 時刻は HH:MM か HH:MM:00(秒未満・タイムゾーンは不可)


def _kind(value: Any) -> TaskKind:
    """タスクの種別。キーがない・null は通常。不正は ValueError(開けませんでした)。"""
    if value is None:
        return TaskKind.NORMAL
    try:
        return TaskKind(value)
    except ValueError:
        raise ValueError(f"タスクの種別が正しくありません: {value!r}") from None


def _children(value: Any) -> list[str]:
    """まとめの子の id のリスト。キーがない・null は空。リストでない・文字列以外は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(cid, str) for cid in value):
        raise ValueError("まとめの子が文字列のリストではありません")
    return list(value)


def _summary(task: Task) -> Task:
    """まとめの使わない項目(日程・工数・担当・実績・進捗度・先行・締切)を空にし、状態を未着手にして返す。"""
    return replace(
        task,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=None,
        effort_hours=0.0,
        assignees=[],
        actuals=[],
        progress=None,
        predecessors=[],
        status=Status.NOT_STARTED,
        parameters=[],
        weekly_crew=[],
    )


def _checkpoint(task: Task) -> Task:
    """チェックポイントを検証し、使わない項目(開始予定・工数・担当・実績・進捗度など)を空にして返す。"""
    if task.deadline is None:
        raise ValueError(f"チェックポイントに締切がありません: {task.name}")
    if task.status not in CHECKPOINT_STATUSES:
        raise ValueError(f"チェックポイントの状態は未着手か終了です: {task.name}")
    return replace(
        task,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        effort_hours=0.0,
        assignees=[],
        actuals=[],
        progress=None,
        parameters=[],
        weekly_crew=[],
    )


def _reference_mode(value: Any) -> ReferenceMode:
    if value is None:
        return ReferenceMode.LIVE
    try:
        return ReferenceMode(value)
    except ValueError:
        raise ValueError(f"参照の方式が正しくありません: {value!r}") from None


def _plantuml_overload_notice(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"PlantUML の通知の設定が正しくありません: {value!r}")
    return value


def _ratio_limit(value: Any, name: str) -> float | None:
    """相対比率の上限・下限。null は設定なし(既定の 50〜150%)。数値以外・非有限・範囲外は ValueError。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise ValueError(f"{name}が正しくありません: {value!r}")
    if not DEFAULT_RATIO_MIN - 1e-9 <= value <= DEFAULT_RATIO_MAX + 1e-9:
        raise ValueError(f"{name}は{DEFAULT_RATIO_MIN * 100:g}〜{DEFAULT_RATIO_MAX * 100:g}%で指定してください: {value!r}")
    return round(float(value), 4)


def _ratio_limits(raw: dict[str, Any], version: int) -> RatioLimits:
    """version 13 以上の、相対比率の上限・下限。下限が上限を上回るのは拒否する。"""
    if version < 13:
        return RatioLimits()
    limits = RatioLimits(
        upper=_ratio_limit(raw.get("ratio_limit_upper"), "相対比率の上限"),
        lower=_ratio_limit(raw.get("ratio_limit_lower"), "相対比率の下限"),
    )
    if limits.upper is not None and limits.lower is not None and limits.lower > limits.upper:
        raise ValueError(f"相対比率の下限が上限を上回っています: {limits.lower!r} > {limits.upper!r}")
    return limits


def _ref_project(value: Any) -> str:
    """参照先のファイル名。空・文字列以外・使えない文字は ValueError。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("参照先のプロジェクトが正しくありません")
    if any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("参照先のプロジェクトに使えない文字が含まれています")
    return value


def _optional_moment(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"スナップショットの{label}が文字列ではありません")
    return _datetime(value)


def _reference_value(raw: Any) -> ReferenceValue | None:
    """保存したスナップショットを読む。null・キーなしは None。形が崩れていれば ValueError。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("スナップショットが正しくありません")
    try:
        progress = raw.get("progress")
        if progress is not None:
            progress = _progress(progress, "スナップショットの進捗率")
        delayed = raw.get("delayed", 0)
        if isinstance(delayed, bool) or not isinstance(delayed, int) or delayed < 0:
            raise ValueError("スナップショットの遅延の件数が正しくありません")
        peak = raw.get("peak_load", 0.0)
        if isinstance(peak, bool) or not isinstance(peak, int | float) or not isfinite(peak) or peak < 0:
            raise ValueError("スナップショットの負荷が正しくありません")
        spans = raw.get("overloads") or []
        if not isinstance(spans, list):
            raise ValueError("スナップショットの負荷の期間が正しくありません")
        overloads = tuple(
            OverloadSpan(
                str(span["member"]),
                _actual_moment(span["start"], "負荷の開始"),
                _actual_moment(span["end"], "負荷の終了"),
                float(span["total"]),
            )
            for span in spans
        )
        return ReferenceValue(
            planned_start=_optional_moment(raw.get("planned_start"), "開始予定"),
            planned_end=_optional_moment(raw.get("planned_end"), "完了予定"),
            actual_start=_optional_moment(raw.get("actual_start"), "実績の開始"),
            actual_end=_optional_moment(raw.get("actual_end"), "実績の終了"),
            progress=progress,
            finished=raw.get("finished") is True,
            delayed=delayed,
            peak_load=float(peak),
            peak_member=str(raw.get("peak_member") or ""),
            overloads=overloads,
            taken_at=_optional_moment(raw.get("taken_at"), "取得日時"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"スナップショットが正しくありません: {exc}") from None


def _reference(task: Task) -> Task:
    """プロジェクト参照の使わない項目(日程・工数・担当・実績・進捗度・状態・カテゴリ・リンクなど)を空にして返す。"""
    return replace(
        task,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        effort_hours=0.0,
        assignees=[],
        weekly_crew=[],
        actuals=[],
        progress=None,
        parameters=[],
        status=Status.NOT_STARTED,
        priority=Priority.MEDIUM,
        category_id=None,
        urls=[],
    )


def _parameter_names(value: Any) -> list[str]:
    """タスクに付けたパラメータの名前。キーがない・null は空。配列でない・文字列以外は ValueError。重複は最初の 1 件を残す。
    登録されていない名前も残す(計算で数えないだけ)。"""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        raise ValueError("パラメータが文字列のリストではありません")
    return list(dict.fromkeys(value))


def _task_name(value: Any) -> str:
    """タスク名。文字列以外は ValueError。制御文字・長すぎる名前は、開けるように整える(`tidy_task_name`)。"""
    if not isinstance(value, str):
        raise ValueError(f"タスクの名前が文字列ではありません: {value!r}")
    return tidy_task_name(value)


def _task_id(value: Any) -> str:
    """タスクの id。キーがない・null は新しく振る(古いファイル)。空・文字列以外は ValueError。"""
    if value is None:
        return new_id()
    if not isinstance(value, str) or not value:
        raise ValueError(f"タスクの id が正しくありません: {value!r}")
    return value


def _predecessors(value: Any) -> list[str]:
    """先行タスクの id のリスト。キーがない・null は空。リストでない・文字列以外は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(pid, str) for pid in value):
        raise ValueError("先行タスクが文字列のリストではありません")
    return list(value)


def _url_templates(value: Any) -> list[UrlTemplate]:
    """URL テンプレート。キーがない・null は空。名前の空・重複、http(s) でない型は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("URL テンプレートがリストではありません")
    templates: list[UrlTemplate] = []
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise ValueError("URL テンプレートの名前が文字列ではありません")
        if not isinstance(raw.get("pattern"), str):
            raise ValueError("URL テンプレートの型が文字列ではありません")
        templates.append(UrlTemplate(raw["name"], raw["pattern"]))
    validate_templates(templates)
    return templates


def _task_urls(value: Any) -> list[TaskUrl]:
    """タスクのリンク。キーがない・null は空。形が正しくなければ ValueError(テンプレートの存在は読込の後で検証する)。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("リンクがリストではありません")
    urls: list[TaskUrl] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("リンクがオブジェクトではありません")
        title, template, values = raw.get("title", ""), raw.get("template"), raw.get("values")
        if not isinstance(title, str) or not (template is None or isinstance(template, str)):
            raise ValueError("リンクの表示名かテンプレート名が文字列ではありません")
        key = URL_KEY if template is None else ID_KEY
        if not isinstance(values, dict) or set(values) != {key} or not isinstance(values[key], str):
            raise ValueError(f"リンクの値が正しくありません(キーは {key} だけです)")
        urls.append(TaskUrl(title, template, dict(values)))
    return urls


def _assignee(value: Any) -> str | None:
    """担当者名。前後の空白を取り除き、空はNone。"""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _member_assignees(value: Any, names: dict[str, str]) -> list[Assignee]:
    """version 2 の担当者。`member` はメンバーの id。名前の取り違えを避けるため、旧キー `name` は拒否する。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("担当者が配列ではありません")
    assignees: list[Assignee] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or "name" in item:
            raise ValueError("担当者の形式が正しくありません")
        member = item.get("member")
        if not isinstance(member, str) or member not in names:
            raise ValueError(f"担当者のメンバーが見つかりません: {member!r}")
        name = names[member]
        if name in seen:
            raise ValueError(f"担当者が重複しています: {name}")
        seen.add(name)
        assignees.append(Assignee(name, _allocation(item.get("allocation", 1.0))))
    return assignees


def _weekly_crew(value: Any, ctx: "_Context") -> list[list[Assignee]]:
    """version 10 の週ごとの担当。各週は担当者の配列(形式は assignees と同じ)。担当者のいない週・上限超えは拒否する。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("週ごとの担当が配列ではありません")
    if len(value) > MAX_WEEKS:
        raise ValueError(f"週ごとの担当は{MAX_WEEKS}週までです")
    weeks: list[list[Assignee]] = []
    for week in value:
        if not isinstance(week, list):
            raise ValueError("週の担当が配列ではありません")
        crew = _member_assignees(week, ctx.member_names)
        if not crew:
            raise ValueError("担当者のいない週があります")
        weeks.append(crew)
    return weeks


def _assignees(raw: dict[str, Any], ctx: "_Context") -> list[Assignee]:
    """担当者のリスト。version 2 は `member`(メンバー id)。version 1 は `assignees` を使い、なければ古いキー(assignee・allocation)を 1 人にする。"""
    if ctx.version >= 2:
        return _member_assignees(raw.get("assignees"), ctx.member_names)
    value = raw.get("assignees")
    if value is None:
        allocation = _allocation(raw.get("allocation", 1.0))  # 古いファイルも、不正な値は拒否する
        name = _assignee(raw.get("assignee"))
        return [Assignee(name, allocation)] if name else []
    if not isinstance(value, list):
        raise ValueError("担当者が配列ではありません")
    assignees: list[Assignee] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("担当者の形式が正しくありません")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("担当者の名前が正しくありません")
        name = name.strip()
        if name in seen:
            raise ValueError(f"担当者が重複しています: {name}")
        seen.add(name)
        assignees.append(Assignee(name, _allocation(item.get("allocation", 1.0))))
    return assignees


def _label_name(value: Any, label: str) -> str:
    """パラメータ・段階の名前。前後の空白を除く。空・文字列以外は ValueError。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}の名前が正しくありません")
    return value.strip()


def _parameters(value: Any) -> list[Parameter]:
    """パラメータの定義。キーがない・null は空。名前の空・重複、判定値の範囲外・非有限は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("パラメータがリストではありません")
    parameters: list[Parameter] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("パラメータの形式が正しくありません")
        name = _label_name(raw.get("name"), "パラメータ")
        if name in seen:
            raise ValueError(f"パラメータ名が重複しています: {name}")
        seen.add(name)
        raw_levels = raw.get("levels")
        if raw_levels is None:
            raw_levels = []
        if not isinstance(raw_levels, list):
            raise ValueError("段階がリストではありません")
        levels: list[Level] = []
        level_names: set[str] = set()
        for item in raw_levels:
            if not isinstance(item, dict):
                raise ValueError("段階の形式が正しくありません")
            level_name = _label_name(item.get("name"), "段階")
            if level_name in level_names:
                raise ValueError(f"段階名が重複しています: {name} の {level_name}")
            level_names.add(level_name)
            levels.append(
                Level(level_name, _number_in_range(item.get("value"), MIN_LEVEL_VALUE, MAX_LEVEL_VALUE, "判定値"))
            )
        parameters.append(Parameter(name, levels))
    return parameters


def _member_levels(value: Any) -> dict[str, str]:
    """メンバーが選んだ段階(パラメータ名 → 段階名)。キーがない・null は空。存在しない参照は拒否しない。"""
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError("メンバーの段階の選択が正しくありません")
    return dict(value)


def _section(raw: Any, depth: int, ctx: "_Context") -> Section:
    """セクションを読む(入れ子)。depth は 1 階層目が 1。上限を超えたら ValueError。"""
    if depth > MAX_SECTION_DEPTH:
        raise ValueError(f"セクションは{MAX_SECTION_DEPTH}階層までです")
    if not isinstance(raw, dict):
        raise ValueError("セクションの形式が正しくありません")
    children = raw.get("sections")
    if children is None:
        children = []
    if not isinstance(children, list):
        raise ValueError("サブセクションがリストではありません")
    section_id = None
    if ctx.version >= 2:
        section_id = _entity_id(raw.get("id"), "セクション")
        if section_id in ctx.section_ids:
            raise ValueError(f"セクションの id が重複しています: {section_id}")
        ctx.section_ids.add(section_id)
    section = Section(
        raw["name"], [_task(t, ctx) for t in raw["tasks"]], [_section(c, depth + 1, ctx) for c in children]
    )
    if section_id is not None:
        section.id = section_id
    return section


def _icon(value: Any) -> str:
    """メンバーのアイコン(version 7)。キーがない・null・空は、アイコンなし。形・大きさ・中身が不正なら ValueError。"""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not is_valid_icon(value):
        raise ValueError("メンバーのアイコンが正しくありません")
    return value


def _warning_limit(value: Any) -> int | None:
    """メンバーの警告の件数の閾値。null・キーなしは閾値なし。整数(boolは不可)で 1〜999。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"メンバーの警告の件数が整数ではありません: {value!r}")
    if not MIN_WARNING_LIMIT <= value <= MAX_WARNING_LIMIT:
        raise ValueError(f"メンバーの警告の件数は{MIN_WARNING_LIMIT}〜{MAX_WARNING_LIMIT}で指定してください: {value}")
    return value


def _members(raw_members: list[dict[str, Any]], ctx: "_Context") -> list[Member]:
    """メンバーを読む。相対比率は検証し、空の名前と重複は(最初の1件を残して)捨てる。"""
    members: list[Member] = []
    seen: set[str] = set()
    ids: set[str] = set()
    for raw in raw_members:
        name = str(raw["name"]).strip()
        ratio = _number_in_range(raw.get("ratio", 1.0), MIN_RATIO, MAX_RATIO, "相対比率")
        levels = _member_levels(raw.get("levels"))
        icon = _icon(raw.get("icon")) if ctx.version >= 7 else ""
        work_days = _work_days(raw.get("work_days"), ctx.version) if ctx.version >= 8 else []
        unclamped = raw.get("ratio_unclamped", False) if ctx.version >= 16 else False
        if not isinstance(unclamped, bool):
            raise ValueError(f"メンバーの丸め対象外の設定が真偽値ではありません: {unclamped!r}")
        teams = _memberships(raw.get("teams"), ctx.team_ids) if ctx.version >= 17 else []
        warning_limit = _warning_limit(raw.get("warning_limit")) if ctx.version >= 19 else None
        member_id = None
        if ctx.version >= 2:
            member_id = _entity_id(raw.get("id"), "メンバー")
            if member_id in ids:
                raise ValueError(f"メンバーの id が重複しています: {member_id}")
            ids.add(member_id)
            if name:
                ctx.member_names[member_id] = name  # 捨てる同名のメンバーを指す担当者も、名前で残ったメンバーへ読める
        if not name or name in seen:
            continue
        seen.add(name)
        member = Member(name, ratio, levels, icon=icon, work_days=work_days, ratio_unclamped=unclamped, teams=teams, warning_limit=warning_limit)
        if member_id is not None:
            member.id = member_id
        members.append(member)
    return members


def _assign_ids(project: Project, ctx: "_Context") -> None:
    """古いファイルに id を振る。version 1 のメンバー・セクションと、id のないタスク。ファイルにある他の id と重ならないようにする。"""
    pending = {id(task) for task in ctx.pending}
    taken = {t.id for t in project.all_tasks() if id(t) not in pending}
    targets: list[Task | Member | Section] = list(ctx.pending)
    sections = [s for _, s in walk_sections(project.sections)]
    if ctx.version < 2:
        targets += [*project.members, *sections]
    else:
        taken |= {m.id for m in project.members} | {s.id for s in sections}
    for target in targets:
        target.id = new_id(taken)
        taken.add(target.id)


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


@dataclass
class _Context:
    """読込の途中で持ち回るもの。version 2 の担当者の解決と、id の重複・振り直しに使う。"""

    version: int
    member_names: dict[str, str] = field(default_factory=dict)  # version 2: メンバー id → 名前(名前が空のメンバーは入れない)
    section_ids: set[str] = field(default_factory=set)
    pending: list[Task] = field(default_factory=list)  # id のないタスク(古いファイル)。読込の最後に id を振る
    team_ids: set[str] = field(default_factory=set)  # version 17: 読んだチームの id(メンバーの所属の検証に使う)
    legacy_codes: dict[int, str] = field(default_factory=dict)  # version 2 以前: タスク(id())→ 旧 ProjectCode。読込の最後にカテゴリへ移す


def _entity_id(value: Any, label: str) -> str:
    """version 2 のメンバー・セクションの id。空・文字列以外は ValueError。"""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}の id が正しくありません: {value!r}")
    return value


def _check_version(raw: dict[str, Any]) -> int:
    """形式のバージョンを確かめて返す。キーがない古いファイルは 1。整数でない・1 未満・このアプリより新しいものは ValueError。"""
    if "version" not in raw:
        return 1
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError(f"version が正しくありません: {version!r}")
    if version > FORMAT_VERSION:
        raise ValueError(f"このアプリより新しい形式です(version {version})。アプリを更新してください")
    return version


def file_version(path: Path) -> int:
    """ファイルの形式のバージョンを返す(キーがなければ 1)。"""
    return _check_version(json.loads(path.read_text(encoding="utf-8")))


def load_project(path: Path) -> Project:
    return parse_project(path.read_text(encoding="utf-8"), path.stem)


def parse_project(text: str, name: str) -> Project:
    raw = json.loads(text)
    ctx = _Context(_check_version(raw))
    teams = _teams(raw.get("teams")) if ctx.version >= 17 else []
    ctx.team_ids = {t.id for t in teams}
    members = _members(raw["members"], ctx)  # version 2 の担当者の解決に要るので、タスクより先に読む
    sections = [_section(s, 1, ctx) for s in raw["sections"]]
    ratio_limits = _ratio_limits(raw, ctx.version)
    project = Project(
        name=name,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=_daily_hours(raw["daily_hours"]),
        work_start=_work_start(raw.get("work_start", "09:00:00")),
        members=members,
        teams=teams,
        sections=sections,
        tasks=[_task(t, ctx) for t in raw.get("tasks", [])],
        actual_mode=_actual_mode(raw.get("actual_mode", "simple")),
        url_templates=_url_templates(raw.get("url_templates")),
        parameters=_parameters(raw.get("parameters")),
        categories=_categories(raw.get("categories")) if ctx.version >= 3 else [],
        events=_events(raw.get("events"), ctx.version) if ctx.version >= 4 else [],
        reference_mode=_reference_mode(raw.get("reference_mode")) if ctx.version >= 11 else ReferenceMode.LIVE,
        plantuml_overload_notice=(
            _plantuml_overload_notice(raw.get("plantuml_overload_notice", True)) if ctx.version >= 12 else True
        ),
        ratio_limit_upper=ratio_limits.upper,
        ratio_limit_lower=ratio_limits.lower,
    )
    for task in project.all_tasks():
        if task.kind is TaskKind.REFERENCE:
            if task.ref_project == name:
                raise ValueError(f"参照先が自分自身です: {task.name}")
            if project.reference_mode is ReferenceMode.LIVE:
                task.ref_snapshot = None  # 常に最新のプロジェクトは、スナップショットを持たない
        else:
            task.ref_snapshot = None
    known = {m.name for m in project.members}
    for task in project.all_tasks():  # 古いファイルの自由入力の担当者を、メンバーとして補う
        for assignee in task.assignees:
            if assignee.name not in known:
                known.add(assignee.name)
                project.members.append(Member(assignee.name, 1.0))
    _assign_ids(project, ctx)
    if ctx.version < 3:  # 旧 ProjectCode をカテゴリへ移す(id は、振り終えた他の id と重ならないようにする)
        pairs = [(t, ctx.legacy_codes.get(id(t), "")) for t in project.all_tasks()]
        project.categories = migrate_legacy(pairs, project.used_ids())
    else:
        known = {c.id for c in project.categories}
        for task in project.all_tasks():
            if task.category_id is not None and task.category_id not in known:
                raise ValueError(f"タスクのカテゴリが見つかりません: {task.category_id!r}")
    validate_links(project.all_tasks())
    for task in project.all_tasks():
        validate_urls(task.urls, project.url_templates)
    return project
