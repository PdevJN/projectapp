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
        start=datetime(2026, 10, 5, 9, 30),
        end=datetime(2026, 10, 7, 18),
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
        tasks=[Task("top", start=datetime(2026, 10, 6), end=datetime(2026, 10, 8))],
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


def test_end_auto_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", sections=[Section("s", [Task("a", end_auto=True), Task("b")])])
    loaded = load_project(save_project(project, tmp_path))
    assert [t.end_auto for t in loaded.sections[0].tasks] == [True, False]


def test_old_file_without_end_auto_reads_as_manual(tmp_path: Path) -> None:
    path = save_project(Project("old", sections=[Section("s", [Task("a", end_auto=True)])]), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["sections"][0]["tasks"][0]["end_auto"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path).sections[0].tasks[0].end_auto is False
