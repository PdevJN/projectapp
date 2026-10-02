from pathlib import Path

from projectapp.config import load_theme, save_theme
from projectapp.models import Project, Section, Task
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
