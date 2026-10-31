from pathlib import Path

from projectapp.calendar import save_cache
from projectapp.models import Project
from projectapp.portfolio import load_others
from projectapp.storage import save_project


def test_load_others_skips_the_open_project_and_reads_the_rest(tmp_path: Path) -> None:
    current = save_project(Project("開いている"), tmp_path)
    save_project(Project("ほか"), tmp_path)
    projects, failures = load_others(tmp_path, current)
    assert [p.name for p in projects] == ["ほか"]
    assert failures == []


def test_load_others_reads_everything_when_the_open_project_is_unsaved(
    tmp_path: Path,
) -> None:
    save_project(Project("甲"), tmp_path)
    save_project(Project("乙"), tmp_path)
    projects, _ = load_others(tmp_path, None)
    assert sorted(p.name for p in projects) == ["乙", "甲"]


def test_load_others_collects_unreadable_files_and_keeps_going(tmp_path: Path) -> None:
    save_project(Project("良い"), tmp_path)
    (tmp_path / "壊れた.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "新しい.json").write_text('{"version": 999}', encoding="utf-8")
    projects, failures = load_others(tmp_path, None)
    assert [p.name for p in projects] == ["良い"]
    assert sorted(f.name for f in failures) == ["壊れた", "新しい"]
    assert all(f.reason for f in failures)


def test_load_others_does_not_read_config_or_holidays(tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert load_others(tmp_path, None) == ([], [])


def test_load_others_reports_a_missing_directory(tmp_path: Path) -> None:
    projects, failures = load_others(tmp_path / "ない", None)
    assert projects == []
    assert [f.reason for f in failures] == ["格納先を読めません"]


def test_load_others_treats_a_structurally_broken_file_as_a_failure(
    tmp_path: Path,
) -> None:
    save_project(Project("良い"), tmp_path)
    (tmp_path / "崩れた.json").write_text(
        '{"version": 7, "base_date": "2026-10-05", "daily_hours": 6.5, "members": [], "sections": [], "tasks": [[]]}',
        encoding="utf-8",
    )
    projects, failures = load_others(tmp_path, None)
    assert [p.name for p in projects] == ["良い"]
    assert [f.name for f in failures] == ["崩れた"]


def test_load_others_reports_an_unreadable_directory(
    tmp_path: Path, monkeypatch
) -> None:
    def deny(base_dir: Path) -> list[Path]:
        raise PermissionError("denied")

    monkeypatch.setattr("projectapp.portfolio.list_project_files", deny)
    projects, failures = load_others(tmp_path, None)
    assert projects == []
    assert [f.name for f in failures] == [str(tmp_path)]
