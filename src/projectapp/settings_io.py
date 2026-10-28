"""プロジェクトの設定値・メンバーの設定値の書き出しと取り込み。NiceGUI には依存しない。"""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from projectapp.handoff import write_json
from projectapp.models import FORMAT_VERSION, Project
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
