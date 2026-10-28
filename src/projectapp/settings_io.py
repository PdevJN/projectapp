"""プロジェクトの設定値・メンバーの設定値の書き出しと取り込み。NiceGUI には依存しない。"""

import json
from collections.abc import Collection
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from projectapp.handoff import write_json
from projectapp.models import (
    FORMAT_VERSION,
    ActualMode,
    Category,
    Event,
    Member,
    Parameter,
    Project,
    ReferenceMode,
    UrlTemplate,
    new_id,
)
from projectapp.storage import dumps_project, parse_project

SETTINGS_KIND = "projectapp-settings"
SETTINGS_VERSION = 1
SETTINGS_FILE_TYPES = ("JSON ファイル (*.json)",)
DEFAULT_FILENAME = "settings.json"
IMPORT_NAME = "設定"  # 読み込みに使う仮のプロジェクト名
PROJECT_KEYS = (
    "base_date",
    "daily_hours",
    "work_start",
    "actual_mode",
    "reference_mode",
    "plantuml_overload_notice",
    "ratio_limit_upper",
    "ratio_limit_lower",
)
COLLECTION_KEYS = ("members", "parameters", "categories", "url_templates", "events")
SECTION_LABELS = {
    "project": "プロジェクト設定",
    "members": "メンバー",
    "parameters": "パラメータ",
    "categories": "カテゴリ",
    "url_templates": "URL テンプレート",
    "events": "イベント",
}


@dataclass
class ImportFile:
    project: Project  # 設定ファイルの中身を載せた、タスクのないプロジェクト
    has_project_settings: bool  # プロジェクト設定のキーが 1 つでもあったか


def build_settings(project: Project) -> dict[str, Any]:
    """設定ファイルの辞書。各要素の形は、プロジェクトファイルの保存と同じ。タスクとセクションは含めない。"""
    raw = json.loads(dumps_project(replace(project, tasks=[], sections=[])))
    data: dict[str, Any] = {"kind": SETTINGS_KIND, "version": SETTINGS_VERSION, "project_version": raw["version"]}
    data.update({key: raw[key] for key in (*PROJECT_KEYS, *COLLECTION_KEYS)})
    return data


def write_settings(path: Path, data: dict[str, Any]) -> Path:
    """設定ファイルを書く。拡張子がなければ .json を付ける。一時ファイル経由。"""
    return write_json(path, data)


def _version(value: Any, label: str, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
        raise ValueError(f"{label} が正しくありません: {value!r}")
    return value


def parse_settings(text: str) -> ImportFile:
    """設定ファイルを読んで検証する。正しくなければ ValueError(何も変えない)。"""
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"JSON として読めません: {exc}") from None
    if not isinstance(raw, dict) or raw.get("kind") != SETTINGS_KIND:
        raise ValueError("プロジェクトの設定ファイルではありません")
    version = raw.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version > SETTINGS_VERSION:
        raise ValueError(f"このアプリより新しい形式です(version {version})。アプリを更新してください")
    _version(version, "version", SETTINGS_VERSION)
    project_version = _version(raw.get("project_version", FORMAT_VERSION), "project_version", FORMAT_VERSION)
    for key in COLLECTION_KEYS:
        if key in raw and not isinstance(raw[key], list):
            raise ValueError(f"{key} がリストではありません")
    body = json.loads(dumps_project(Project(IMPORT_NAME)))  # キーのない区分は、空の既定で読む
    body["version"] = project_version
    body.update({key: raw[key] for key in (*PROJECT_KEYS, *COLLECTION_KEYS) if key in raw})
    try:
        project = parse_project(json.dumps(body), IMPORT_NAME)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("設定ファイルの形式が正しくありません") from exc
    return ImportFile(project, any(key in raw for key in PROJECT_KEYS))


Item = Member | Parameter | Category | UrlTemplate | Event


@dataclass(frozen=True)
class SectionPlan:
    key: str
    new: tuple[str, ...]  # 開いているプロジェクトにない項目(追加する)
    duplicates: tuple[str, ...]  # すでにある項目(上書きかスキップ)
    overwritable: bool  # False(イベント)は、重複を上書きできず、取り込まない


@dataclass(frozen=True)
class ProjectChange:
    label: str
    now: str
    incoming: str


@dataclass(frozen=True)
class ImportPlan:
    sections: tuple[SectionPlan, ...]
    project_changes: tuple[ProjectChange, ...]


@dataclass
class ImportResult:
    project: Project  # 取り込み後の新しいプロジェクト(元は変えない)
    counts: dict[str, int]  # 区分 → 追加か上書きした件数(プロジェクト設定は 0 か 1)
    skipped: int  # 重複のため取り込まなかった件数
    dropped_levels: int  # 合わなくなって外した、メンバーの段階の選択
    notes: list[str]


def item_key(item: Item) -> str:
    """突き合わせの鍵。イベントは期間と文字列、それ以外は名前。"""
    if isinstance(item, Event):
        return f"{item.start.isoformat()}〜{item.end.isoformat()} {item.text}"
    return item.name.strip()


def _describe(project: Project) -> dict[str, str]:
    def ratio(value: float | None) -> str:
        return "設定なし" if value is None else f"{value:.0%}"

    modes = {ActualMode.SIMPLE: "簡易", ActualMode.INTERVALS: "区間"}
    refs = {ReferenceMode.LIVE: "常に最新", ReferenceMode.SNAPSHOT: "スナップショット"}
    return {
        "基準日": project.base_date.isoformat(),
        "稼働可能時間": f"{project.daily_hours:g}h",
        "始業時刻": project.work_start.strftime("%H:%M"),
        "実績の記録方式": modes[project.actual_mode],
        "プロジェクト参照の方式": refs[project.reference_mode],
        "PlantUML の通知": "出す" if project.plantuml_overload_notice else "出さない",
        "相対比率の上限": ratio(project.ratio_limit_upper),
        "相対比率の下限": ratio(project.ratio_limit_lower),
    }


def project_changes(current: Project, incoming: Project) -> tuple[ProjectChange, ...]:
    now, then = _describe(current), _describe(incoming)
    return tuple(ProjectChange(label, now[label], then[label]) for label in now if now[label] != then[label])


def plan_import(current: Project, incoming: ImportFile) -> ImportPlan:
    """取り込む内容を、区分ごとの追加・重複と、プロジェクト設定の違いにまとめる。何も変えない。"""
    sections: list[SectionPlan] = []
    for key in COLLECTION_KEYS:
        mine = {item_key(item) for item in getattr(current, key)}
        new: list[str] = []
        duplicates: list[str] = []
        seen: set[str] = set()
        for item in getattr(incoming.project, key):
            name = item_key(item)
            if name in seen:
                continue
            seen.add(name)
            (duplicates if name in mine else new).append(name)
        if new or duplicates:
            sections.append(SectionPlan(key, tuple(new), tuple(duplicates), key != "events"))
    changes = project_changes(current, incoming.project) if incoming.has_project_settings else ()
    return ImportPlan(tuple(sections), changes)


def _overwrite(target: Item, item: Item) -> None:
    """重複の項目を、取り込む値で置き換える。名前と id は保つ。"""
    if isinstance(target, Member) and isinstance(item, Member):
        target.ratio, target.levels, target.icon, target.work_days = item.ratio, item.levels, item.icon, item.work_days
        target.ratio_unclamped = item.ratio_unclamped
    elif isinstance(target, Parameter) and isinstance(item, Parameter):
        target.levels = item.levels
    elif isinstance(target, Category) and isinstance(item, Category):
        target.kind, target.expiry_date, target.color, target.prj_code = (
            item.kind,
            item.expiry_date,
            item.color,
            item.prj_code,
        )
    elif isinstance(target, UrlTemplate) and isinstance(item, UrlTemplate):
        target.pattern = item.pattern


def _merge(work: Project, source: Project, key: str, overwrite: Collection[tuple[str, str]], result: ImportResult) -> None:
    mine = {item_key(item): item for item in getattr(work, key)}
    seen: set[str] = set()
    for item in getattr(source, key):
        name = item_key(item)
        if name in seen:
            continue
        seen.add(name)
        target = mine.get(name)
        if target is None:
            if isinstance(item, Member | Category | Event):
                item.id = new_id(work.used_ids())
            getattr(work, key).append(item)
            result.counts[key] += 1
        elif key != "events" and (key, name) in overwrite:
            _overwrite(target, item)
            result.counts[key] += 1
        else:
            result.skipped += 1


def _apply_project_settings(work: Project, source: Project, result: ImportResult) -> None:
    work.base_date, work.daily_hours, work.work_start = source.base_date, source.daily_hours, source.work_start
    work.reference_mode = source.reference_mode
    work.plantuml_overload_notice = source.plantuml_overload_notice
    work.ratio_limit_upper, work.ratio_limit_lower = source.ratio_limit_upper, source.ratio_limit_lower
    if source.actual_mode is ActualMode.SIMPLE and any(len(task.actuals) > 1 for task in work.all_tasks()):
        result.notes.append("記録方式は、2 区間以上のタスクがあるため変えませんでした")
    else:
        work.actual_mode = source.actual_mode
    if work.reference_mode is ReferenceMode.LIVE:  # 常に最新は、スナップショットを持たない
        for task in work.all_tasks():
            task.ref_snapshot = None


def _drop_stale_levels(work: Project) -> int:
    levels = {parameter.name: {level.name for level in parameter.levels} for parameter in work.parameters}
    dropped = 0
    for member in work.members:
        kept = {name: level for name, level in member.levels.items() if level in levels.get(name, set())}
        dropped += len(member.levels) - len(kept)
        member.levels = kept
    return dropped


def apply_import(
    current: Project,
    incoming: ImportFile,
    sections: Collection[str],
    overwrite: Collection[tuple[str, str]],
) -> ImportResult:
    """選んだ区分を取り込んだ、新しいプロジェクトを返す。current は変えない。結果が読み込みの検証を通らなければ ValueError。"""
    work, source = deepcopy(current), deepcopy(incoming.project)
    result = ImportResult(work, dict.fromkeys(SECTION_LABELS, 0), 0, 0, [])
    for key in COLLECTION_KEYS:
        if key in sections:
            _merge(work, source, key, overwrite, result)
    if "project" in sections and incoming.has_project_settings:
        _apply_project_settings(work, source, result)
        result.counts["project"] = 1 if project_changes(current, work) else 0
    result.dropped_levels = _drop_stale_levels(work)
    parse_project(dumps_project(work), work.name)  # 保存・読込と同じ検証。通らなければ ValueError
    return result


def summary(result: ImportResult) -> str:
    done = [
        SECTION_LABELS[key] if key == "project" else f"{SECTION_LABELS[key]} {count} 件"
        for key, count in result.counts.items()
        if count
    ]
    head = f"取り込みました({'、'.join(done)})" if done else "取り込む項目はありませんでした"
    extras = [
        *([f"重複 {result.skipped} 件は取り込んでいません"] if result.skipped else []),
        *([f"合わない段階の選択 {result.dropped_levels} 件を外しました"] if result.dropped_levels else []),
        *result.notes,
    ]
    return head + (f"。{'、'.join(extras)}" if extras else "")


def copy_into(target: Project, source: Project) -> None:
    """source の全フィールドを target へ移す(画面が持つ Project の参照を保つ)。"""
    for field in fields(Project):
        setattr(target, field.name, getattr(source, field.name))
