import os
import json
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path

import pytest

from projectapp.config import load_theme, save_theme
from projectapp.models import (
    FORMAT_VERSION,
    Assignee,
    Actual,
    ActualMode,
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
    walk_sections,
)
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
        assignees=[Assignee("佐藤")],
        predecessors=["a"],
    )
    project = Project(
        "demo",
        base_date=date(2020, 1, 1),
        daily_hours=7.0,
        members=[Member("佐藤", 0.5)],
        sections=[Section("s1", [task])],
        tasks=[
            Task("top", id="a", planned_start=datetime(2026, 10, 6), planned_end=datetime(2026, 10, 8))
        ],
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


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("planned_start", "1999-12-31T23:59:00"),
        ("planned_end", "9999-12-31T00:00:00"),
        ("deadline", "2101-01-01T00:00:00"),
    ],
)
def test_load_rejects_a_year_outside_the_supported_range(
    key: str, value: str, tmp_path: Path
) -> None:
    path = save_project(Project("n", tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update({key: value}))
    with pytest.raises(ValueError, match="年"):
        load_project(path)


def test_load_rejects_a_legacy_end_outside_the_supported_range(tmp_path: Path) -> None:
    path = _legacy_file(tmp_path, {"start": "2026-10-05T09:00:00", "end": "9999-12-31T00:00:00"})
    with pytest.raises(ValueError, match="年"):
        load_project(path)


def test_an_explicit_deadline_wins_over_a_legacy_end(tmp_path: Path) -> None:
    path = _legacy_file(
        tmp_path,
        {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00", "deadline": "2026-10-20T18:00:00"},
    )
    assert load_project(path).tasks[0].deadline == datetime(2026, 10, 20, 18)


def test_allocation_roundtrip_and_default(tmp_path: Path) -> None:
    project = Project(
        "r",
        members=[Member("田中", 1.2)],
        tasks=[Task("a", assignees=[Assignee("田中", 0.6)]), Task("b")],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [[a.allocation for a in t.assignees] for t in loaded.tasks] == [[0.6], []]
    assert loaded.members == [Member("田中", 1.2)]


@pytest.mark.parametrize("value", [0, 0.09, 3.01, -1, float("nan"), float("inf"), True, "1", None])
def test_load_rejects_an_invalid_member_ratio(value: object, tmp_path: Path) -> None:
    path = save_project(Project("r", members=[Member("田中")]), tmp_path)
    _rewrite(path, lambda d: d["members"][0].update(ratio=value))
    with pytest.raises(ValueError, match="相対比率"):
        load_project(path)


def test_load_accepts_the_ratio_and_allocation_boundaries(tmp_path: Path) -> None:
    project = Project(
        "r",
        members=[Member("低", 0.1), Member("高", 3.0)],
        tasks=[Task("a", assignees=[Assignee("低", 0.01)]), Task("b", assignees=[Assignee("高", 1.0)])],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [m.ratio for m in loaded.members] == [0.1, 3.0]
    assert [[a.allocation for a in t.assignees] for t in loaded.tasks] == [[0.01], [1.0]]


def test_an_assignee_missing_from_the_members_is_added_as_a_member(tmp_path: Path) -> None:
    project = Project("old", members=[Member("田中", 1.2)], tasks=[Task("a", assignees=[Assignee("佐藤")])])
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.members == [Member("田中", 1.2), Member("佐藤", 1.0)]
    assert loaded.tasks[0].assignee_names == ["佐藤"]


def test_added_members_are_not_duplicated_and_keep_the_task_order(tmp_path: Path) -> None:
    project = Project(
        "old",
        tasks=[Task("a", assignees=[Assignee("佐藤")]), Task("b", assignees=[Assignee("鈴木")]), Task("c", assignees=[Assignee("佐藤")])],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [m.name for m in loaded.members] == ["佐藤", "鈴木"]


def test_assignee_whitespace_is_trimmed_and_blank_becomes_none(tmp_path: Path) -> None:
    path = save_project(Project("old", tasks=[Task("a"), Task("b"), Task("c")]), tmp_path)

    def legacy(data: dict) -> None:
        data.pop("version")  # version 1 のファイル(担当者は名前で書く)
        for task, name in zip(data["tasks"], [" 佐藤 ", "  ", ""]):
            task.pop("assignees")
            task["assignee"] = name

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert [t.assignee_names for t in loaded.tasks] == [["佐藤"], [], []]
    assert [m.name for m in loaded.members] == ["佐藤"]


def test_duplicate_member_names_keep_the_first(tmp_path: Path) -> None:
    project = Project("r", members=[Member("田中", 1.2), Member("田中", 0.5)])
    assert load_project(save_project(project, tmp_path)).members == [Member("田中", 1.2)]


def test_a_blank_member_name_is_dropped(tmp_path: Path) -> None:
    project = Project("r", members=[Member("  ", 1.0), Member("田中", 1.0)])
    assert [m.name for m in load_project(save_project(project, tmp_path)).members] == ["田中"]


def test_project_all_tasks_lists_top_level_then_sections() -> None:
    top, inner = Task("top"), Task("in")
    project = Project("p", tasks=[top], sections=[Section("s", [inner])])
    assert project.all_tasks() == [top, inner]


def _project_with_actuals(*actuals: Actual) -> Project:
    return Project("demo", tasks=[Task("t", actuals=list(actuals))])


def test_actuals_roundtrip(tmp_path: Path) -> None:
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 17, 30)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.tasks[0].actuals == project.tasks[0].actuals


def test_file_without_actuals_loads_as_empty(tmp_path: Path) -> None:
    path = save_project(_project_with_actuals(), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["tasks"][0]["actuals"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].actuals == []


def test_file_with_null_actuals_loads_as_empty(tmp_path: Path) -> None:
    path = save_project(_project_with_actuals(), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["actuals"] = None
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].actuals == []


@pytest.mark.parametrize(
    "bad",
    [
        "x",
        {"start": "2026-10-05T09:00:00"},
        [{"end": "2026-10-05T09:00:00"}],
        [{"start": None}],
        [{"start": 5}],
        [{"start": "2026-10-05T09:00:00", "end": 5}],
        [{"start": "2026-10-05T09:00:00", "end": "2026-10-05T08:00:00"}],
        [{"start": "2026-10-05T09:00:00+09:00"}],
        [{"start": "1999-10-05T09:00:00"}],
        ["2026-10-05T09:00:00"],
    ],
)
def test_invalid_actuals_are_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(_project_with_actuals(), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["actuals"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_project(path)


def test_actual_progress_roundtrip(tmp_path: Path) -> None:
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 0),
        Actual(datetime(2026, 10, 6, 9, 0), None, 40),
        Actual(datetime(2026, 10, 7, 9, 0), None, None),
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [a.progress for a in loaded.tasks[0].actuals] == [0, 40, None]


def test_file_without_progress_loads_as_none(tmp_path: Path) -> None:
    path = save_project(_project_with_actuals(Actual(datetime(2026, 10, 5, 9, 0))), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["tasks"][0]["actuals"][0]["progress"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].actuals[0].progress is None


@pytest.mark.parametrize("bad", [True, False, 40.5, 40.0, "40", -1, 101, [40]])
def test_invalid_progress_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(_project_with_actuals(Actual(datetime(2026, 10, 5, 9, 0))), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["actuals"][0]["progress"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_project(path)


@pytest.mark.parametrize("value", [0, 100])
def test_progress_boundaries_are_accepted(tmp_path: Path, value: int) -> None:
    project = _project_with_actuals(Actual(datetime(2026, 10, 5, 9, 0), None, value))
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.tasks[0].actuals[0].progress == value


def test_progress_that_decreases_across_actuals_is_rejected(tmp_path: Path) -> None:
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 60),
        Actual(datetime(2026, 10, 6, 9, 0), None, 40),
    )
    path = save_project(project, tmp_path)
    with pytest.raises(ValueError):
        load_project(path)


def test_unset_progress_between_actuals_is_skipped_when_checking_order(tmp_path: Path) -> None:
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 40),
        Actual(datetime(2026, 10, 6, 9, 0), datetime(2026, 10, 6, 12, 0), None),
        Actual(datetime(2026, 10, 7, 9, 0), None, 40),
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [a.progress for a in loaded.tasks[0].actuals] == [40, None, 40]


def test_not_started_status_is_saved_as_the_new_name(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["tasks"][0]["status"] == "未着手"
    assert load_project(path).tasks[0].status is Status.NOT_STARTED


def test_legacy_status_started_loads_as_not_started(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["status"] = "開始"  # 旧名
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].status is Status.NOT_STARTED


@pytest.mark.parametrize("status", [Status.RUNNING, Status.PAUSED, Status.DONE])
def test_other_statuses_are_unchanged(tmp_path: Path, status: Status) -> None:
    path = save_project(Project("demo", tasks=[Task("t", status=status)]), tmp_path)
    assert load_project(path).tasks[0].status is status


def test_unknown_status_is_still_rejected(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["status"] = "不明"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_project(path)


def test_actual_mode_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", actual_mode=ActualMode.INTERVALS)
    assert load_project(save_project(project, tmp_path)).actual_mode is ActualMode.INTERVALS


def test_file_without_actual_mode_loads_as_simple(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["actual_mode"] == "simple"
    del raw["actual_mode"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).actual_mode is ActualMode.SIMPLE


@pytest.mark.parametrize("bad", ["weekly", None, 1, []])
def test_invalid_actual_mode_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("demo"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["actual_mode"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="記録方式"):
        load_project(path)


def test_simple_file_with_two_actuals_still_loads(tmp_path: Path) -> None:
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.actual_mode is ActualMode.SIMPLE
    assert len(loaded.tasks[0].actuals) == 2


def _project_with_code(code: str) -> Project:
    return Project("demo", tasks=[Task("t", project_code=code)])


def test_project_code_roundtrip(tmp_path: Path) -> None:
    loaded = load_project(save_project(_project_with_code("PRJ-001"), tmp_path))
    assert loaded.tasks[0].project_code == "PRJ-001"


def test_empty_project_code_is_saved_as_an_empty_string(tmp_path: Path) -> None:
    path = save_project(_project_with_code(""), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["project_code"] == ""


@pytest.mark.parametrize("missing", ["delete", "null"])
def test_file_without_project_code_loads_as_empty(tmp_path: Path, missing: str) -> None:
    path = save_project(_project_with_code("X"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if missing == "delete":
        del raw["tasks"][0]["project_code"]
    else:
        raw["tasks"][0]["project_code"] = None
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].project_code == ""


def test_project_code_is_trimmed_on_load(tmp_path: Path) -> None:
    path = save_project(_project_with_code("X"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["project_code"] = "  " + "A" * 20 + "  "
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].project_code == "A" * 20


@pytest.mark.parametrize("bad", ["A" * 21, 1, ["x"], True])
def test_invalid_project_code_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(_project_with_code("X"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["project_code"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="ProjectCode"):
        load_project(path)


def write_raw(tmp_path: Path, tasks: list[dict[str, object]]) -> Path:
    base = {
        "name": "t",
        "effort_hours": 0.0,
        "priority": "中",
        "status": "未着手",
        "color": "#4c8bf5",
        "predecessors": [],
    }
    data = {
        "base_date": "2026-10-05",
        "daily_hours": 6.5,
        "members": [],
        "sections": [{"name": "s", "tasks": [{**base, **raw} for raw in tasks]}],
    }
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_ids_and_predecessors_roundtrip(tmp_path: Path) -> None:
    a = Task("a", id="aaaaaaaa")
    b = Task("b", id="bbbbbbbb", predecessors=["aaaaaaaa"])
    path = save_project(Project("links", sections=[Section("s", [a, b])]), tmp_path)
    loaded = load_project(path).sections[0].tasks
    assert [(t.id, t.predecessors) for t in loaded] == [
        ("aaaaaaaa", []),
        ("bbbbbbbb", ["aaaaaaaa"]),
    ]


def test_a_file_without_ids_gets_unique_ids_and_empty_predecessors(tmp_path: Path) -> None:
    path = write_raw(tmp_path, [{"name": "a"}, {"name": "b"}])
    for raw in json.loads(path.read_text(encoding="utf-8"))["sections"][0]["tasks"]:
        assert "id" not in raw
    tasks = load_project(path).sections[0].tasks
    assert len({t.id for t in tasks}) == 2
    assert all(len(t.id) == 8 for t in tasks)
    path_no_key = write_raw(tmp_path, [{"name": "a"}])
    data = json.loads(path_no_key.read_text(encoding="utf-8"))
    del data["sections"][0]["tasks"][0]["predecessors"]
    path_no_key.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path_no_key).sections[0].tasks[0].predecessors == []


@pytest.mark.parametrize(
    "tasks",
    [
        [{"name": "a", "id": ""}],
        [{"name": "a", "id": 5}],
        [{"name": "a", "id": "x"}, {"name": "b", "id": "x"}],
        [{"name": "a", "id": "x", "predecessors": "x"}],
        [{"name": "a", "id": "x", "predecessors": [1]}],
        [{"name": "a", "id": "x", "predecessors": ["zz"]}],
        [{"name": "a", "id": "x", "predecessors": ["x"]}],
        [
            {"name": "a", "id": "x", "predecessors": ["y"]},
            {"name": "b", "id": "y", "predecessors": ["x"]},
        ],
    ],
)
def test_bad_ids_and_predecessors_are_rejected(
    tmp_path: Path, tasks: list[dict[str, object]]
) -> None:
    with pytest.raises(ValueError):
        load_project(write_raw(tmp_path, tasks))


def saved_project(tmp_path: Path) -> Path:
    project = Project(
        "links",
        tasks=[
            Task(
                "t",
                urls=[
                    TaskUrl("メモ", "チケット", {"ID": "231"}),
                    TaskUrl("", None, {"URL": "https://example.com/a"}),
                ],
            )
        ],
        url_templates=[UrlTemplate("チケット", "https://example.com/{ID}")],
    )
    return save_project(project, tmp_path)


def rewrite(path: Path, edit: Callable[[dict], None]) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    edit(raw)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_links_and_templates_roundtrip(tmp_path: Path) -> None:
    loaded = load_project(saved_project(tmp_path))
    assert loaded.url_templates == [UrlTemplate("チケット", "https://example.com/{ID}")]
    assert loaded.tasks[0].urls == [
        TaskUrl("メモ", "チケット", {"ID": "231"}),
        TaskUrl("", None, {"URL": "https://example.com/a"}),
    ]


def test_an_old_file_without_the_keys_loads_with_no_links(tmp_path: Path) -> None:
    path = saved_project(tmp_path)

    def drop(raw: dict) -> None:
        del raw["url_templates"]
        del raw["tasks"][0]["urls"]

    rewrite(path, drop)
    loaded = load_project(path)
    assert loaded.url_templates == [] and loaded.tasks[0].urls == []


def test_null_keys_load_as_empty(tmp_path: Path) -> None:
    path = saved_project(tmp_path)

    def nulls(raw: dict) -> None:
        raw["url_templates"] = None
        raw["tasks"][0]["urls"] = None

    rewrite(path, nulls)
    loaded = load_project(path)
    assert loaded.url_templates == [] and loaded.tasks[0].urls == []


GOOD = {"name": "チケット", "pattern": "https://example.com/{ID}"}


@pytest.mark.parametrize(
    ("templates", "urls"),
    [
        ("x", []),
        ([1], []),
        ([{"pattern": "https://x.test/{ID}"}], []),
        ([{"name": 1, "pattern": "https://x.test"}], []),
        ([GOOD, GOOD], []),
        ([{"name": " ", "pattern": "https://x.test"}], []),
        ([{"name": "a", "pattern": "javascript:{ID}"}], []),
        ([GOOD], "x"),
        ([GOOD], [1]),
        ([GOOD], [{"title": 1, "template": None, "values": {"URL": "https://x.test"}}]),
        ([GOOD], [{"title": "", "template": "なし", "values": {"ID": "1"}}]),
        ([GOOD], [{"title": "", "template": "チケット", "values": {"ID": ""}}]),
        ([GOOD], [{"title": "", "template": "チケット", "values": {"URL": "https://x.test"}}]),
        ([GOOD], [{"title": "", "template": None, "values": {"ID": "1"}}]),
        ([GOOD], [{"title": "", "template": "チケット", "values": {"ID": 1}}]),
        ([GOOD], [{"title": "", "template": "チケット", "values": {"ID": "1", "X": "2"}}]),
        ([GOOD], [{"title": "", "template": None, "values": {"URL": "javascript:alert(1)"}}]),
        ([GOOD], [{"title": "", "template": None}]),
    ],
)
def test_invalid_links_and_templates_are_rejected(
    tmp_path: Path, templates: object, urls: object
) -> None:
    path = saved_project(tmp_path)

    def bad(raw: dict) -> None:
        raw["url_templates"] = templates
        raw["tasks"][0]["urls"] = urls

    rewrite(path, bad)
    with pytest.raises(ValueError):
        load_project(path)


def test_a_checkpoint_keeps_its_links(tmp_path: Path) -> None:
    project = Project(
        "cp",
        tasks=[
            Task(
                "節目",
                kind=TaskKind.CHECKPOINT,
                deadline=datetime(2026, 10, 20, 17),
                urls=[TaskUrl("", None, {"URL": "https://example.com/doc"})],
            )
        ],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.tasks[0].urls == [TaskUrl("", None, {"URL": "https://example.com/doc"})]


def test_assignees_roundtrip(tmp_path: Path) -> None:
    project = Project(
        "p",
        members=[Member("田中"), Member("鈴木")],
        tasks=[Task("a", assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.5)]), Task("b")],
    )
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.tasks[0].assignees == [Assignee("田中", 0.6), Assignee("鈴木", 0.5)]
    assert loaded.tasks[1].assignees == []
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["tasks"][0]["assignees"] == [
        {"member": project.members[0].id, "allocation": 0.6},
        {"member": project.members[1].id, "allocation": 0.5},
    ]
    assert "assignee" not in raw["tasks"][0] and "allocation" not in raw["tasks"][0]


def test_old_keys_load_as_one_assignee(tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")], tasks=[Task("a"), Task("b")]), tmp_path)

    def legacy(data: dict) -> None:
        data.pop("version")
        for task in data["tasks"]:
            task.pop("assignees")
        data["tasks"][0].update(assignee=" 田中 ", allocation=0.4)
        data["tasks"][1].update(assignee="", allocation=1.0)

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert loaded.tasks[0].assignees == [Assignee("田中", 0.4)]
    assert loaded.tasks[1].assignees == []


@pytest.mark.parametrize("value", [0.0, 1.5, "x", True, float("nan")])
def test_old_keys_with_a_bad_allocation_are_rejected_even_without_an_assignee(value: object, tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("a")]), tmp_path)

    def legacy(data: dict) -> None:
        data.pop("version")
        data["tasks"][0].pop("assignees")
        data["tasks"][0].update(assignee=None, allocation=value)

    _rewrite(path, legacy)
    with pytest.raises(ValueError):
        load_project(path)


def test_assignees_win_over_the_old_keys(tmp_path: Path) -> None:
    path = save_project(
        Project("p", members=[Member("田中"), Member("鈴木")], tasks=[Task("a", assignees=[Assignee("鈴木")])]), tmp_path
    )
    _rewrite(path, lambda d: d["tasks"][0].update(assignee="田中", allocation=0.2))
    assert load_project(path).tasks[0].assignees == [Assignee("鈴木", 1.0)]


@pytest.mark.parametrize(
    "bad",
    [
        "田中",  # リストでない
        ["田中"],  # 辞書でない
        [{"name": "", "allocation": 1.0}],
        [{"name": 3, "allocation": 1.0}],
        [{"name": "田中", "allocation": 0.0}],
        [{"name": "田中", "allocation": 1.01}],
        [{"name": "田中", "allocation": "x"}],
        [{"name": "田中", "allocation": 1.0}, {"name": " 田中 ", "allocation": 0.5}],  # 重複
    ],
)
def test_bad_assignees_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")], tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignees=bad))
    with pytest.raises(ValueError):
        load_project(path)


def test_missing_allocation_in_an_assignee_means_one(tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")], tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: (d.pop("version"), d["tasks"][0].update(assignees=[{"name": "田中"}])))
    assert load_project(path).tasks[0].assignees == [Assignee("田中", 1.0)]


def test_every_assignee_missing_from_the_members_is_added_as_a_member(tmp_path: Path) -> None:
    project = Project(
        "p",
        members=[Member("田中", 1.2)],
        tasks=[Task("a", assignees=[Assignee("佐藤"), Assignee("鈴木")]), Task("b", assignees=[Assignee("佐藤")])],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [(m.name, m.ratio) for m in loaded.members] == [("田中", 1.2), ("佐藤", 1.0), ("鈴木", 1.0)]


def test_a_checkpoint_has_no_assignees(tmp_path: Path) -> None:
    checkpoint = Task("c", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), assignees=[Assignee("田中")])
    path = save_project(Project("p", members=[Member("田中")], tasks=[checkpoint]), tmp_path)
    assert load_project(path).tasks[0].assignees == []


def test_parameters_and_levels_roundtrip(tmp_path: Path) -> None:
    project = Project(
        "p",
        members=[Member("田中", 1.0, {"経験": "上級", "専門": "高"}), Member("鈴木")],
        parameters=[
            Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)]),
            Parameter("専門", [Level("高", 0.1)]),
            Parameter("空", []),
        ],
    )
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.parameters == project.parameters
    assert loaded.members[0].levels == {"経験": "上級", "専門": "高"}
    assert loaded.members[1].levels == {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["parameters"][0] == {"name": "経験", "levels": [{"name": "初級", "value": -0.2}, {"name": "上級", "value": 0.2}]}
    assert raw["members"][0]["levels"] == {"経験": "上級", "専門": "高"}


def test_a_file_without_parameters_or_levels_loads_as_empty(tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中", 1.2)]), tmp_path)

    def legacy(data: dict) -> None:
        data.pop("parameters")
        data["members"][0].pop("levels")

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert loaded.parameters == []
    assert loaded.members == [Member("田中", 1.2)]
    _rewrite(path, lambda d: d.update(parameters=None))
    assert load_project(path).parameters == []


@pytest.mark.parametrize(
    "bad",
    [
        "経験",  # リストでない
        ["経験"],  # 辞書でない
        [{"name": "", "levels": []}],
        [{"name": "  ", "levels": []}],
        [{"name": 3, "levels": []}],
        [{"name": "経験", "levels": []}, {"name": " 経験 ", "levels": []}],  # 重複
        [{"name": "経験", "levels": "上級"}],  # levels がリストでない
        [{"name": "経験", "levels": ["上級"]}],  # 段階が辞書でない
        [{"name": "経験", "levels": [{"name": "", "value": 0.1}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": 0.1}, {"name": "上級", "value": 0.2}]}],  # 段階名の重複
        [{"name": "経験", "levels": [{"name": "上級"}]}],  # 値がない
        [{"name": "経験", "levels": [{"name": "上級", "value": "x"}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": True}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": -0.91}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": 2.91}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": float("nan")}]}],
    ],
)
def test_bad_parameters_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")]), tmp_path)
    _rewrite(path, lambda d: d.update(parameters=bad))
    with pytest.raises(ValueError):
        load_project(path)


@pytest.mark.parametrize("value", [-0.9, 2.9, 0.0])
def test_the_level_value_boundaries_are_accepted(value: float, tmp_path: Path) -> None:
    project = Project("p", parameters=[Parameter("経験", [Level("a", value)])])
    assert load_project(save_project(project, tmp_path)).parameters[0].levels[0].value == pytest.approx(value)


@pytest.mark.parametrize("bad", ["上級", ["経験"], {"経験": 3}, {"3": 3}])
def test_bad_member_levels_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")]), tmp_path)
    _rewrite(path, lambda d: d["members"][0].update(levels=bad))
    with pytest.raises(ValueError):
        load_project(path)


def test_a_member_selection_that_points_nowhere_is_kept(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中", 1.0, {"消えた": "上級"})], parameters=[Parameter("経験", [Level("初級", -0.2)])])
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.members[0].levels == {"消えた": "上級"}  # 読込は拒否しない。計算では 0% として扱う


def nested_sections() -> list[Section]:
    deep = Section("孫", [Task("孫タスク")])
    child = Section("子", [Task("子タスク")], [deep])
    return [Section("親", [Task("親タスク")], [child, Section("子2", [Task("子2タスク")])]), Section("別", [Task("別タスク")])]


def test_nested_sections_roundtrip(tmp_path: Path) -> None:
    project = Project("p", tasks=[Task("root")], sections=nested_sections())
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.sections == project.sections
    assert [t.name for t in loaded.all_tasks()] == ["root", "親タスク", "子タスク", "孫タスク", "子2タスク", "別タスク"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["sections"][0]["sections"][0]["sections"][0]["name"] == "孫"


def test_a_file_without_nested_sections_loads_as_flat(tmp_path: Path) -> None:
    path = save_project(Project("p", sections=[Section("A", [Task("a")])]), tmp_path)

    def legacy(data: dict) -> None:
        data["sections"][0].pop("sections")

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert loaded.sections == [Section("A", [Task("a")])]
    _rewrite(path, lambda d: d["sections"][0].update(sections=None))
    assert load_project(path).sections[0].sections == []


def test_four_levels_of_sections_are_rejected(tmp_path: Path) -> None:
    four = Section("1", sections=[Section("2", sections=[Section("3", sections=[Section("4")])])])
    path = save_project(Project("p", sections=[four]), tmp_path)
    with pytest.raises(ValueError, match="3階層"):
        load_project(path)


def test_three_levels_of_sections_are_accepted(tmp_path: Path) -> None:
    three = Section("1", sections=[Section("2", sections=[Section("3")])])
    loaded = load_project(save_project(Project("p", sections=[three]), tmp_path))
    assert loaded.sections[0].sections[0].sections[0].name == "3"


@pytest.mark.parametrize("bad", ["子", ["子"], [3], [None]])
def test_bad_nested_sections_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", sections=[Section("A")]), tmp_path)
    _rewrite(path, lambda d: d["sections"][0].update(sections=bad))
    with pytest.raises(ValueError):
        load_project(path)


def _rewrite_version(path: Path, version: object, *, remove: bool = False) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del raw["version"]
    else:
        raw["version"] = version
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_saved_file_starts_with_the_format_version(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert list(raw)[0] == "version"
    assert raw["version"] == FORMAT_VERSION == 2


def test_file_without_version_loads_as_version_1(tmp_path: Path) -> None:
    path = save_project(Project("old", sections=[Section("s1", [Task("t1")])]), tmp_path)
    _rewrite_version(path, None, remove=True)
    assert load_project(path).sections[0].tasks[0].name == "t1"


def test_file_with_a_newer_version_is_rejected_with_a_clear_message(tmp_path: Path) -> None:
    path = save_project(Project("future"), tmp_path)
    _rewrite_version(path, FORMAT_VERSION + 1)
    with pytest.raises(ValueError, match="より新しい形式.*アプリを更新"):
        load_project(path)


@pytest.mark.parametrize("version", [0, -1, True, False, 1.5, "1", None, [1]])
def test_file_with_an_invalid_version_is_rejected(version: object, tmp_path: Path) -> None:
    path = save_project(Project("bad"), tmp_path)
    _rewrite_version(path, version)
    with pytest.raises(ValueError, match="version"):
        load_project(path)


def test_resave_keeps_the_version(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path)
    loaded = load_project(path)
    raw = json.loads(save_project(loaded, tmp_path).read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION


def _task_dicts(tasks: list[dict], sections: list[dict]):
    yield from tasks
    for section in sections:
        yield from _task_dicts(section["tasks"], section["sections"])


def _to_v1(data: dict) -> None:
    """version 2 のファイルの辞書を、version 1 の形(id なし・担当者は名前)にする。"""
    names = {m["id"]: m["name"] for m in data["members"]}
    del data["version"]
    for member in data["members"]:
        del member["id"]

    def strip(sections: list[dict]) -> None:
        for section in sections:
            del section["id"]
            strip(section["sections"])

    strip(data["sections"])
    for task in _task_dicts(data["tasks"], data["sections"]):
        task["assignees"] = [{"name": names[a["member"]], "allocation": a["allocation"]} for a in task["assignees"]]


def ids_project() -> Project:
    return Project(
        "p",
        members=[Member("田中"), Member("鈴木")],
        tasks=[Task("r", assignees=[Assignee("鈴木", 0.5)])],
        sections=[
            Section("s", [Task("a", assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.4)])], [Section("sub", [Task("b")])])
        ],
    )


def test_saved_file_is_version_2_and_refers_to_members_by_id(tmp_path: Path) -> None:
    project = ids_project()
    raw = json.loads(save_project(project, tmp_path).read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION == 2
    tanaka, suzuki = project.members
    assert [m["id"] for m in raw["members"]] == [tanaka.id, suzuki.id]
    assert raw["sections"][0]["id"] == project.sections[0].id
    assert raw["sections"][0]["sections"][0]["id"] == project.sections[0].sections[0].id
    assert raw["sections"][0]["tasks"][0]["assignees"] == [
        {"member": tanaka.id, "allocation": 0.6},
        {"member": suzuki.id, "allocation": 0.4},
    ]
    assert raw["tasks"][0]["assignees"] == [{"member": suzuki.id, "allocation": 0.5}]


def test_ids_survive_save_load_save(tmp_path: Path) -> None:
    project = ids_project()
    loaded = load_project(save_project(project, tmp_path))
    assert [m.id for m in loaded.members] == [m.id for m in project.members]
    assert [s.id for _, s in walk_sections(loaded.sections)] == [s.id for _, s in walk_sections(project.sections)]
    assert loaded.sections[0].tasks[0].assignees == [Assignee("田中", 0.6), Assignee("鈴木", 0.4)]
    again = load_project(save_project(loaded, tmp_path))
    assert again.used_ids() == project.used_ids()


def test_a_renamed_member_keeps_the_id_and_the_assignment(tmp_path: Path) -> None:
    project = ids_project()
    path = save_project(project, tmp_path)
    _rewrite(path, lambda d: d["members"][0].update(name="田中二郎"))
    loaded = load_project(path)
    assert loaded.members[0].id == project.members[0].id
    assert loaded.sections[0].tasks[0].assignee_names == ["田中二郎", "鈴木"]


def test_a_version_1_file_gets_unique_ids(tmp_path: Path) -> None:
    path = save_project(ids_project(), tmp_path)
    _rewrite(path, lambda d: (_to_v1(d), [t.pop("id") for t in _task_dicts(d["tasks"], d["sections"]) if t["name"] == "b"]))
    loaded = load_project(path)
    ids = [t.id for t in loaded.all_tasks()] + [m.id for m in loaded.members] + [s.id for _, s in walk_sections(loaded.sections)]
    assert len(ids) == 3 + 2 + 2 and len(set(ids)) == len(ids)
    assert all(len(i) == 8 for i in ids)
    assert loaded.sections[0].tasks[0].assignees == [Assignee("田中", 0.6), Assignee("鈴木", 0.4)]
    raw = json.loads(save_project(loaded, tmp_path, overwrite=True).read_text(encoding="utf-8"))
    assert raw["version"] == 2


def test_version_1_ids_avoid_the_ids_in_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project("p", members=[Member("田中")], sections=[Section("s", [Task("a", id="aaaaaaaa")])])
    path = save_project(project, tmp_path)
    _rewrite(path, _to_v1)
    # 先頭の 2 つは、読込が作る Member と Section の既定の id(default_factory)で使われる
    values = iter(["11111111", "22222222", "aaaaaaaa", "bbbbbbbb", "cccccccc"])
    monkeypatch.setattr("projectapp.models.secrets.token_hex", lambda nbytes: next(values))
    loaded = load_project(path)
    assert loaded.sections[0].tasks[0].id == "aaaaaaaa"
    assert {loaded.members[0].id, loaded.sections[0].id} == {"bbbbbbbb", "cccccccc"}


def test_save_adds_a_member_for_an_unknown_assignee(tmp_path: Path) -> None:
    project = Project("p", tasks=[Task("a", assignees=[Assignee("佐藤", 0.5)])])
    path = save_project(project, tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert [m["name"] for m in raw["members"]] == ["佐藤"]
    assert raw["tasks"][0]["assignees"] == [{"member": raw["members"][0]["id"], "allocation": 0.5}]
    assert project.members == []  # 保存は実行時のプロジェクトを変えない
    loaded = load_project(path)
    assert loaded.tasks[0].assignees == [Assignee("佐藤", 0.5)]
    assert [m.name for m in loaded.members] == ["佐藤"]


def test_save_points_a_duplicate_named_member_at_the_first(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中", 1.2), Member("田中", 0.5)], tasks=[Task("a", assignees=[Assignee("田中")])])
    path = save_project(project, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["assignees"][0]["member"] == project.members[0].id
    loaded = load_project(path)
    assert loaded.members == [Member("田中", 1.2)]
    assert loaded.tasks[0].assignee_names == ["田中"]


def test_an_assignee_pointing_at_a_dropped_duplicate_reads_as_the_kept_member(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中", 1.2), Member("田中", 0.5)], tasks=[Task("a", assignees=[Assignee("田中")])])
    path = save_project(project, tmp_path)
    second = project.members[1].id
    _rewrite(path, lambda d: d["tasks"][0]["assignees"][0].update(member=second))
    assert load_project(path).tasks[0].assignee_names == ["田中"]


def test_an_assignee_pointing_at_a_blank_named_member_is_rejected(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中"), Member("鈴木")], tasks=[Task("a", assignees=[Assignee("鈴木")])])
    path = save_project(project, tmp_path)
    _rewrite(path, lambda d: d["members"][1].update(name="  "))
    with pytest.raises(ValueError, match="メンバーが見つかりません"):
        load_project(path)


def _bad_id_cases() -> list[tuple[str, Callable[[dict], None]]]:
    return [
        ("メンバー id なし", lambda d: d["members"][0].pop("id")),
        ("メンバー id 空", lambda d: d["members"][0].update(id="")),
        ("メンバー id null", lambda d: d["members"][0].update(id=None)),
        ("メンバー id 数値", lambda d: d["members"][0].update(id=5)),
        ("メンバー id 重複", lambda d: d["members"][1].update(id=d["members"][0]["id"])),
        ("セクション id なし", lambda d: d["sections"][0].pop("id")),
        ("セクション id 空", lambda d: d["sections"][0].update(id="")),
        ("セクション id 数値", lambda d: d["sections"][0].update(id=5)),
        ("入れ子のセクション id 重複", lambda d: d["sections"][0]["sections"][0].update(id=d["sections"][0]["id"])),
        ("担当者の member が存在しない", lambda d: d["tasks"][0]["assignees"][0].update(member="zzzzzzzz")),
        ("担当者の member が文字列でない", lambda d: d["tasks"][0]["assignees"][0].update(member=5)),
        ("担当者の member がない", lambda d: d["tasks"][0]["assignees"][0].pop("member")),
        ("担当者に旧キー name", lambda d: d["tasks"][0]["assignees"][0].update(name="鈴木")),
    ]


@pytest.mark.parametrize(("label", "edit"), _bad_id_cases(), ids=[c[0] for c in _bad_id_cases()])
def test_version_2_rejects_bad_ids_and_references(label: str, edit: Callable[[dict], None], tmp_path: Path) -> None:
    path = save_project(ids_project(), tmp_path)
    _rewrite(path, edit)
    with pytest.raises(ValueError):
        load_project(path)


def test_version_2_ignores_the_old_assignee_keys(tmp_path: Path) -> None:
    path = save_project(ids_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignee="田中", allocation=0.2))
    assert load_project(path).tasks[0].assignees == [Assignee("鈴木", 0.5)]


@pytest.mark.parametrize("kind", ["task", "member", "section"])
def test_save_rejects_duplicate_ids_and_leaves_the_file(kind: str, tmp_path: Path) -> None:
    good = save_project(Project("p"), tmp_path)
    before = good.read_text(encoding="utf-8")
    project = Project("p")
    if kind == "task":
        project.tasks = [Task("a", id="same"), Task("b", id="same")]
    elif kind == "member":
        project.members = [Member("田中", id="same"), Member("鈴木", id="same")]
    else:
        project.sections = [Section("a", id="same"), Section("b", sections=[Section("c", id="same")], id="other")]
    with pytest.raises(ValueError, match="重複"):
        save_project(project, tmp_path)
    assert good.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["p.json"]  # 一時ファイルも残さない
