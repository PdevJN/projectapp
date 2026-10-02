import json
from datetime import date, datetime
from pathlib import Path

from projectapp.config import load_theme, save_theme
from projectapp.models import Member, Priority, Project, Section, Status, Task
from projectapp.timeline import Scale, build_columns
from projectapp.storage import list_project_files, load_project, save_project


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
