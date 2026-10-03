import os
import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from projectapp.config import load_theme, save_theme
from projectapp.models import Member, Priority, Project, Section, Status, Task
from projectapp.timeline import Scale, build_columns
from projectapp.storage import list_project_files, load_project, save_project, validate_name


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", sections=[Section("s1", [Task("t1")])])
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.name == "demo"
    assert loaded.sections[0].tasks[0].name == "t1"


def test_list_excludes_config(tmp_path: Path) -> None:
    save_theme("dark", tmp_path)
    save_project(Project("demo"), tmp_path)
    assert [p.stem for p in list_project_files(tmp_path)] == ["demo"]


def test_theme_default(tmp_path: Path) -> None:
    assert load_theme(tmp_path) == "auto"
    save_theme("dark", tmp_path)
    assert load_theme(tmp_path) == "dark"


def test_roundtrip_restores_dates_enums_and_base_date(tmp_path: Path) -> None:
    task = Task(
        "t1",
        planned_start=datetime(2026, 10, 5, 9, 30),
        planned_end=datetime(2026, 10, 7, 18),
        effort_hours=8.0,
        priority=Priority.HIGH,
        status=Status.RUNNING,
        color="#112233",
        assignee="佐藤",
        predecessors=["a"],
    )
    project = Project(
        "demo",
        base_date=date(2020, 1, 1),
        daily_hours=7.0,
        members=[Member("佐藤", 0.5)],
        sections=[Section("s1", [task])],
        tasks=[Task("top", planned_start=datetime(2026, 10, 6), planned_end=datetime(2026, 10, 8))],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded == project
    assert len(build_columns(loaded, Scale.DAY)) > 0


def test_file_without_top_level_tasks_loads_as_empty(tmp_path: Path) -> None:
    path = save_project(Project("old"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["tasks"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks == []


def test_work_start_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", work_start=time(8, 30))
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.work_start == time(8, 30)


def test_file_without_work_start_loads_with_the_default(tmp_path: Path) -> None:
    path = save_project(Project("old"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["work_start"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).work_start == time(9, 0)


@pytest.mark.parametrize(
    "name",
    ["", "   ", "\u3000", "a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b",
     "a\tb", ".hidden", "config", "holidays"],
)
def test_validate_name_rejects_unusable_names(name: str, tmp_path: Path) -> None:
    assert validate_name(name, tmp_path, new=True) is not None


def test_validate_name_accepts_japanese_and_strips_whitespace(tmp_path: Path) -> None:
    assert validate_name("デモ", tmp_path, new=True) is None
    assert validate_name("  デモ\u3000", tmp_path, new=True) is None


def test_validate_name_detects_an_existing_file_only_for_new(tmp_path: Path) -> None:
    save_project(Project("demo"), tmp_path)
    assert validate_name("demo", tmp_path, new=True) is not None
    assert validate_name(" demo ", tmp_path, new=True) is not None
    assert validate_name("demo", tmp_path, new=False) is None


def test_validate_name_with_a_missing_base_dir(tmp_path: Path) -> None:
    assert validate_name("demo", tmp_path / "none", new=True) is None


@pytest.mark.parametrize("name", ["", "a/b", "config", ".x"])
def test_save_project_rejects_an_invalid_name(name: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_project(Project(name), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_save_project_strips_the_name_for_the_file(tmp_path: Path) -> None:
    assert save_project(Project(" demo "), tmp_path).name == "demo.json"


def test_save_project_creates_a_missing_base_dir(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path / ".projectapp")
    assert path.is_file()


def test_save_project_leaves_the_original_when_writing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = save_project(Project("demo", sections=[Section("元")]), tmp_path)
    before = path.read_text(encoding="utf-8")

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.storage.os.replace", boom)
    with pytest.raises(OSError):
        save_project(Project("demo", sections=[Section("新")]), tmp_path)
    assert path.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.json"]


def test_save_project_without_overwrite_creates_a_new_file(tmp_path: Path) -> None:
    path = save_project(Project("new"), tmp_path, overwrite=False)
    assert path.name == "new.json"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["new.json"]


def test_save_project_without_overwrite_refuses_an_existing_file(tmp_path: Path) -> None:
    path = save_project(Project("demo", sections=[Section("元")]), tmp_path)
    with pytest.raises(FileExistsError):
        save_project(Project("demo"), tmp_path, overwrite=False)
    assert load_project(path).sections[0].name == "元"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.json"]


def test_load_project_uses_the_file_name_as_the_name(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path)
    renamed = path.rename(tmp_path / "other.json")
    assert load_project(renamed).name == "other"


def test_list_excludes_files_that_cannot_be_saved_back(tmp_path: Path) -> None:
    save_project(Project("ok"), tmp_path)
    for name in [" a.json", "a .json", "　b.json", ".foo.json"]:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [p.stem for p in list_project_files(tmp_path)] == ["ok"]


def _rewrite(path: Path, edit) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("value", ["6.5", None, True, [], 0, -1, 24.5, float("nan"), float("inf")])
def test_load_rejects_an_invalid_daily_hours(value: object, tmp_path: Path) -> None:
    path = save_project(Project("bad"), tmp_path)
    _rewrite(path, lambda d: d.update(daily_hours=value))
    with pytest.raises(ValueError, match="稼働可能時間"):
        load_project(path)


@pytest.mark.parametrize("value", [0.5, 6.5, 8, 24])
def test_load_accepts_daily_hours_the_calculation_accepts(value: float, tmp_path: Path) -> None:
    path = save_project(Project("ok"), tmp_path)
    _rewrite(path, lambda d: d.update(daily_hours=value))
    assert load_project(path).daily_hours == value


@pytest.mark.parametrize("value", ["9", "25:00", "abc", 9, None, ""])
def test_load_rejects_an_invalid_work_start(value: object, tmp_path: Path) -> None:
    path = save_project(Project("bad"), tmp_path)
    _rewrite(path, lambda d: d.update(work_start=value))
    with pytest.raises(ValueError, match="始業時刻"):
        load_project(path)


@pytest.mark.parametrize("name", ["abc.", "abc. ", "a b."])
def test_validate_name_rejects_a_trailing_dot(name: str, tmp_path: Path) -> None:
    assert validate_name(name, tmp_path, new=True) == "名前は「.」で終われません"


def test_save_project_honors_the_umask(tmp_path: Path) -> None:
    old = os.umask(0o077)
    try:
        path = save_project(Project("private"), tmp_path)
    finally:
        os.umask(old)
    assert path.stat().st_mode & 0o777 == 0o600


def test_save_project_default_mode_follows_the_umask(tmp_path: Path) -> None:
    old = os.umask(0o022)
    try:
        path = save_project(Project("shared"), tmp_path)
    finally:
        os.umask(old)
    assert path.stat().st_mode & 0o777 == 0o644


def _no_hard_links(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(src: object, dst: object) -> None:
        raise OSError(1, "Operation not permitted")  # FAT/exFAT などの挙動

    monkeypatch.setattr("projectapp.storage.os.link", refuse)


def test_new_save_works_where_hard_links_are_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hard_links(monkeypatch)
    path = save_project(Project("new"), tmp_path, overwrite=False)
    assert load_project(path).name == "new"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["new.json"]


def test_new_save_fallback_still_refuses_an_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = save_project(Project("demo", sections=[Section("元")]), tmp_path)
    _no_hard_links(monkeypatch)
    with pytest.raises(FileExistsError):
        save_project(Project("demo"), tmp_path, overwrite=False)
    assert load_project(path).sections[0].name == "元"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.json"]


def test_save_project_syncs_the_data_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[int] = []
    real = os.fsync
    monkeypatch.setattr("projectapp.storage.os.fsync", lambda fd: (synced.append(fd), real(fd)))
    save_project(Project("demo"), tmp_path)
    assert synced


def test_failed_write_leaves_no_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.storage.os.fsync", boom)
    with pytest.raises(OSError):
        save_project(Project("demo"), tmp_path, overwrite=False)
    assert list(tmp_path.iterdir()) == []


def test_planned_start_is_saved_and_the_legacy_start_key_is_still_read(tmp_path: Path) -> None:
    project = Project("p", tasks=[Task("a", planned_start=datetime(2026, 10, 5, 9))])
    path = save_project(project, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tasks"][0]["planned_start"] == "2026-10-05T09:00:00"
    assert "start" not in data["tasks"][0]

    legacy = {
        k: v
        for k, v in data["tasks"][0].items()
        if k not in ("planned_end", "planned_end_manual", "deadline")
    }
    legacy["start"] = legacy.pop("planned_start")
    data["tasks"][0] = legacy
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path).tasks[0].planned_start == datetime(2026, 10, 5, 9)


def test_deadline_roundtrip(tmp_path: Path) -> None:
    project = Project(
        "d",
        sections=[Section("s", [Task("a", deadline=datetime(2026, 10, 9, 18, 0)), Task("b")])],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [t.deadline for t in loaded.sections[0].tasks] == [datetime(2026, 10, 9, 18, 0), None]


def _legacy_file(tmp_path: Path, raw_task: dict[str, object]) -> Path:
    """新形式で保存したファイルの最初のタスクを、旧形式の項目で置き換える。"""
    path = save_project(Project("old", tasks=[Task("a")]), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = {
        k: v
        for k, v in data["tasks"][0].items()
        if k not in ("planned_start", "planned_end", "planned_end_manual", "deadline")
    }
    data["tasks"][0] = {**kept, **raw_task}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_legacy_manual_end_becomes_the_deadline(tmp_path: Path) -> None:
    path = _legacy_file(
        tmp_path,
        {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00", "end_auto": False},
    )
    task = load_project(path).tasks[0]
    assert task.planned_start == datetime(2026, 10, 5, 9)
    assert task.deadline == datetime(2026, 10, 7, 18)
    assert (task.planned_end, task.planned_end_manual) == (None, False)


def test_legacy_end_without_end_auto_is_treated_as_manual(tmp_path: Path) -> None:
    path = _legacy_file(tmp_path, {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00"})
    assert load_project(path).tasks[0].deadline == datetime(2026, 10, 7, 18)


def test_legacy_auto_end_is_dropped(tmp_path: Path) -> None:
    path = _legacy_file(
        tmp_path,
        {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00", "end_auto": True},
    )
    assert load_project(path).tasks[0].deadline is None


def test_legacy_end_without_a_start_still_becomes_the_deadline(tmp_path: Path) -> None:
    path = _legacy_file(tmp_path, {"end": "2026-10-07T18:00:00", "end_auto": False})
    task = load_project(path).tasks[0]
    assert (task.planned_start, task.deadline) == (None, datetime(2026, 10, 7, 18))


def test_new_format_roundtrip_keeps_the_planned_fields(tmp_path: Path) -> None:
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 18),
        planned_end_manual=True,
        deadline=datetime(2026, 10, 12, 18),
        effort_hours=8.0,
    )
    loaded = load_project(save_project(Project("n", tasks=[task]), tmp_path)).tasks[0]
    assert loaded == task


def test_new_format_has_no_end_or_end_auto(tmp_path: Path) -> None:
    path = save_project(Project("n", tasks=[Task("a")]), tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))["tasks"][0]
    assert "end" not in saved and "end_auto" not in saved and "start" not in saved


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, []])
def test_planned_end_manual_that_is_not_a_bool_reads_as_false(
    value: object, tmp_path: Path
) -> None:
    path = save_project(Project("n", tasks=[Task("a", planned_end_manual=True)]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(planned_end_manual=value))
    assert load_project(path).tasks[0].planned_end_manual is False
