"""プロジェクトファイル(~/.projectapp/<名前>.json)の読み書き。"""

import json
import os
import secrets
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time
from math import isfinite
from pathlib import Path
from typing import Any, NamedTuple

from projectapp.linkgraph import validate_links
from projectapp.models import (
    FORMAT_VERSION,
    CHECKPOINT_STATUSES,
    ID_KEY,
    URL_KEY,
    ActualMode,
    MAX_ALLOCATION,
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
    MIN_YEAR,
    Actual,
    Assignee,
    Level,
    Member,
    Parameter,
    Priority,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
    new_id,
    walk_sections,
)
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
    """タスク同士・メンバー同士・セクション同士の id の重複があれば ValueError(読めないファイルを書かない)。"""
    groups = {
        "タスク": [t.id for t in project.all_tasks()],
        "メンバー": [m.id for m in project.members],
        "セクション": [s.id for _, s in walk_sections(project.sections)],
    }
    for label, ids in groups.items():
        if len(set(ids)) != len(ids):
            raise ValueError(f"{label}の id が重複しています")


def _dump(project: Project) -> dict[str, Any]:
    """ファイルに書く辞書。担当者は名前ではなくメンバー id で指す。メンバーにいない名前は、メンバーを補う(実行時のプロジェクトは変えない)。"""
    data: dict[str, Any] = {"version": FORMAT_VERSION, **asdict(project)}
    ids: dict[str, str] = {}
    for member in data["members"]:
        ids.setdefault(member["name"], member["id"])  # 同名は最初の 1 件を指す(読込が残すのも最初の 1 件)
    taken = project.used_ids()
    for task in _task_dicts(data["tasks"], data["sections"]):
        refs = []
        for assignee in task["assignees"]:
            name = assignee["name"]
            if name not in ids:
                ids[name] = new_id(taken)
                taken.add(ids[name])
                data["members"].append({"name": name, "ratio": 1.0, "levels": {}, "id": ids[name]})
            refs.append({"member": ids[name], "allocation": assignee["allocation"]})
        task["assignees"] = refs
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


def save_project(
    project: Project, base_dir: Path = BASE_DIR, *, overwrite: bool = True
) -> Path:
    """一時ファイルへ書いてから置き換える。overwrite=Falseは既存ファイルを壊さない。"""
    name = project.name.strip()
    if error := validate_name(name, base_dir, new=False):
        raise ValueError(error)
    _check_unique_ids(project)
    data = json.dumps(_dump(project), ensure_ascii=False, indent=2, default=_encode)
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
    task = Task(
        name=raw["name"],
        id=_task_id(raw.get("id")),
        planned_start=planned_start,
        planned_end=planned_end,
        planned_end_manual=manual,
        deadline=deadline,
        effort_hours=raw["effort_hours"],
        priority=Priority(raw["priority"]),
        status=_status(raw["status"]),
        color=raw["color"],
        assignees=_assignees(raw, ctx),
        predecessors=_predecessors(raw.get("predecessors")),
        actuals=_actuals(raw.get("actuals")),
        project_code=_project_code(raw.get("project_code")),
        kind=kind,
        urls=_task_urls(raw.get("urls")),
    )
    result = _checkpoint(task) if kind is TaskKind.CHECKPOINT else task
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


def _kind(value: Any) -> TaskKind:
    """タスクの種別。キーがない・null は通常。不正は ValueError(開けませんでした)。"""
    if value is None:
        return TaskKind.NORMAL
    try:
        return TaskKind(value)
    except ValueError:
        raise ValueError(f"タスクの種別が正しくありません: {value!r}") from None


def _checkpoint(task: Task) -> Task:
    """チェックポイントを検証し、使わない項目(開始予定・工数・担当・実績など)を空にして返す。"""
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
    )


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


def _members(raw_members: list[dict[str, Any]], ctx: "_Context") -> list[Member]:
    """メンバーを読む。相対比率は検証し、空の名前と重複は(最初の1件を残して)捨てる。"""
    members: list[Member] = []
    seen: set[str] = set()
    ids: set[str] = set()
    for raw in raw_members:
        name = str(raw["name"]).strip()
        ratio = _number_in_range(raw.get("ratio", 1.0), MIN_RATIO, MAX_RATIO, "相対比率")
        levels = _member_levels(raw.get("levels"))
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
        member = Member(name, ratio, levels)
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


def load_project(path: Path) -> Project:
    raw = json.loads(path.read_text(encoding="utf-8"))
    ctx = _Context(_check_version(raw))
    members = _members(raw["members"], ctx)  # version 2 の担当者の解決に要るので、タスクより先に読む
    sections = [_section(s, 1, ctx) for s in raw["sections"]]
    project = Project(
        name=path.stem,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=_daily_hours(raw["daily_hours"]),
        work_start=_work_start(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t, ctx) for t in raw.get("tasks", [])],
        actual_mode=_actual_mode(raw.get("actual_mode", "simple")),
        url_templates=_url_templates(raw.get("url_templates")),
        parameters=_parameters(raw.get("parameters")),
    )
    known = {m.name for m in project.members}
    for task in project.all_tasks():  # 古いファイルの自由入力の担当者を、メンバーとして補う
        for assignee in task.assignees:
            if assignee.name not in known:
                known.add(assignee.name)
                project.members.append(Member(assignee.name, 1.0))
    _assign_ids(project, ctx)
    validate_links(project.all_tasks())
    for task in project.all_tasks():
        validate_urls(task.urls, project.url_templates)
    return project
