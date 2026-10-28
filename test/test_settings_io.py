import json
from datetime import date, time
from pathlib import Path

import pytest

from projectapp.models import (
    ActualMode,
    Category,
    Event,
    Level,
    Member,
    Parameter,
    Project,
    ReferenceMode,
    Section,
    Task,
    UrlTemplate,
    WorkDay,
)
from projectapp.settings_io import (
    DEFAULT_FILENAME,
    SETTINGS_FILE_TYPES,
    build_settings,
    parse_settings,
    write_settings,
)


def full_project() -> Project:
    return Project(
        "元",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        work_start=time(10, 0),
        actual_mode=ActualMode.INTERVALS,
        reference_mode=ReferenceMode.SNAPSHOT,
        plantuml_overload_notice=False,
        ratio_limit_upper=1.2,
        ratio_limit_lower=0.8,
        parameters=[Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])],
        members=[Member("田中", 1.2, {"経験": "上級"}, work_days=[WorkDay(date(2026, 10, 12), None, None, "休暇")])],
        categories=[Category("開発", kind="業務", color="red", prj_code="PRJ-1")],
        url_templates=[UrlTemplate("チケット", "https://example.com/{ID}")],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "orange", closed=True)],
        sections=[Section("開発", [Task("実装")])],
        tasks=[Task("雑務")],
    )


def test_the_file_names_its_kind_and_leaves_out_the_tasks() -> None:
    data = build_settings(full_project())
    assert data["kind"] == "projectapp-settings" and data["version"] == 1
    assert "tasks" not in data and "sections" not in data
    assert DEFAULT_FILENAME == "settings.json" and SETTINGS_FILE_TYPES == ("JSON ファイル (*.json)",)


def test_the_settings_round_trip_into_a_project_without_tasks() -> None:
    project = full_project()
    loaded = parse_settings(json.dumps(build_settings(project)))
    got = loaded.project
    assert loaded.has_project_settings
    assert (got.base_date, got.daily_hours, got.work_start) == (project.base_date, 7.0, time(10, 0))
    assert (got.actual_mode, got.reference_mode, got.plantuml_overload_notice) == (
        ActualMode.INTERVALS,
        ReferenceMode.SNAPSHOT,
        False,
    )
    assert (got.ratio_limit_upper, got.ratio_limit_lower) == (1.2, 0.8)
    assert got.members == project.members and got.parameters == project.parameters
    assert got.categories == project.categories and got.url_templates == project.url_templates
    assert got.events == project.events
    assert got.members[0].id == project.members[0].id  # 取り込み側で振り直すので、ここでは保つ
    assert got.tasks == [] and got.sections == []


def test_missing_sections_read_as_empty() -> None:
    loaded = parse_settings(json.dumps({"kind": "projectapp-settings", "version": 1, "members": []}))
    assert not loaded.has_project_settings
    assert loaded.project.members == [] and loaded.project.events == []


def test_the_file_is_written_as_json(tmp_path: Path) -> None:
    path = write_settings(tmp_path / "out", build_settings(full_project()))
    assert path.name == "out.json"  # 拡張子がなければ付ける
    assert json.loads(path.read_text(encoding="utf-8"))["kind"] == "projectapp-settings"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]  # 一時ファイルを残さない


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "JSON"),
        ("{", "JSON"),
        ("[]", "設定ファイルではありません"),
        (json.dumps({"kind": "other", "version": 1}), "設定ファイルではありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 2}), "新しい形式"),
        (json.dumps({"kind": "projectapp-settings", "version": 0}), "version"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "project_version": 999}), "project_version"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "members": "abc"}), "リストではありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "members": [1]}), "形式が正しくありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "daily_hours": 0}), "稼働可能時間"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "base_date": "x"}), "Invalid isoformat"),
    ],
)
def test_a_broken_file_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_settings(text)
