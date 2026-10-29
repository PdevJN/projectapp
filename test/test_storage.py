import os
import json
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path

import pytest

from projectapp.config import load_theme, save_theme
from projectapp.models import (
    FORMAT_VERSION,
    MAX_WEEKS,
    Assignee,
    Actual,
    ActualMode,
    Assignee,
    Category,
    Event,
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
    WorkDay,
    walk_sections,
)
from projectapp.timeline import Scale, build_columns
from projectapp.storage import (
    ExternalChange,
    backup_file,
    check_external_change,
    dumps_project,
    file_digest,
    list_project_files,
    load_project,
    parse_project,
    save_project,
    validate_name,
)


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


def test_legacy_actual_progress_moves_to_the_task_progress(tmp_path: Path) -> None:
    """実績の区間の進捗度は廃止した。古いファイルは、入っている最後の値をタスクの進捗度にして読む。"""
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 0),
        Actual(datetime(2026, 10, 6, 9, 0), None, 40),
        Actual(datetime(2026, 10, 7, 9, 0), None, None),
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.tasks[0].progress == 40
    assert [a.progress for a in loaded.tasks[0].actuals] == [None, None, None]


def test_legacy_actual_progress_wins_over_the_task_value(tmp_path: Path) -> None:
    """以前は区間の値を優先して表示していたので、その表示のまま移す。"""
    project = _project_with_actuals(Actual(datetime(2026, 10, 5, 9, 0), None, 60))
    project.tasks[0].progress = 10
    assert load_project(save_project(project, tmp_path)).tasks[0].progress == 60


def test_the_task_value_is_kept_without_actual_progress(tmp_path: Path) -> None:
    project = _project_with_actuals(Actual(datetime(2026, 10, 5, 9, 0)))
    project.tasks[0].progress = 10
    assert load_project(save_project(project, tmp_path)).tasks[0].progress == 10


def test_file_without_progress_loads_as_none(tmp_path: Path) -> None:
    path = save_project(_project_with_actuals(Actual(datetime(2026, 10, 5, 9, 0))), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["tasks"][0]["actuals"][0]["progress"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_project(path).tasks[0]
    assert loaded.actuals[0].progress is None and loaded.progress is None


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
    assert loaded.tasks[0].progress == value


def test_legacy_progress_that_decreases_across_actuals_is_no_longer_rejected(tmp_path: Path) -> None:
    """区間の進捗度は入力できなくなったので、順序の検査はしない。最後の値を使う。"""
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 60),
        Actual(datetime(2026, 10, 6, 9, 0), None, 40),
    )
    assert load_project(save_project(project, tmp_path)).tasks[0].progress == 40


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


def _edit_raw(path: Path, edit: Callable[[dict], None]) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    edit(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")


def _legacy_codes_file(tmp_path: Path, codes: list[object]) -> Path:
    """version 2 のファイル。タスクごとに project_code を持つ(カテゴリと category_id はない)。"""
    path = save_project(Project("demo", tasks=[Task(f"t{i}") for i in range(len(codes))]), tmp_path)

    def edit(raw: dict) -> None:
        raw["version"] = 2
        del raw["categories"]
        for task, code in zip(raw["tasks"], codes):
            del task["category_id"]
            task["project_code"] = code

    _edit_raw(path, edit)
    return path


def test_categories_roundtrip(tmp_path: Path) -> None:
    dev = Category("開発", "業務", date(2026, 12, 31), "indigo", "PRJ-1")
    ops = Category("保守", color="red")
    project = Project(
        "demo",
        tasks=[Task("a", category_id=dev.id), Task("b")],
        sections=[Section("s", [Task("c", category_id=ops.id)])],
        categories=[dev, ops],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.categories == [dev, ops]
    assert [c.id for c in loaded.categories] == [dev.id, ops.id]
    assert [t.category_id for t in loaded.all_tasks()] == [dev.id, None, ops.id]


def test_task_has_no_project_code_field() -> None:
    assert not hasattr(Task("t"), "project_code")


def test_saved_file_has_categories_and_no_project_code(tmp_path: Path) -> None:
    category = Category("開発", expiry_date=date(2026, 12, 31))
    path = save_project(Project("demo", tasks=[Task("a", category_id=category.id)], categories=[category]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["categories"] == [
        {"name": "開発", "kind": "", "expiry_date": "2026-12-31", "color": "blue", "prj_code": "", "id": category.id}
    ]
    assert raw["tasks"][0]["category_id"] == category.id
    assert "project_code" not in raw["tasks"][0]


def test_undecided_is_saved_as_null_and_is_not_a_category(tmp_path: Path) -> None:
    raw = json.loads(save_project(Project("demo", tasks=[Task("a")]), tmp_path).read_text(encoding="utf-8"))
    assert raw["categories"] == []
    assert raw["tasks"][0]["category_id"] is None


def test_checkpoint_keeps_its_category(tmp_path: Path) -> None:
    category = Category("開発")
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), category_id=category.id)
    loaded = load_project(save_project(Project("demo", tasks=[checkpoint], categories=[category]), tmp_path))
    assert loaded.tasks[0].category_id == category.id


@pytest.mark.parametrize("missing", ["categories", "category_id"])
def test_version_3_file_without_the_category_keys_loads_as_empty(tmp_path: Path, missing: str) -> None:
    path = save_project(Project("demo", tasks=[Task("a")]), tmp_path)

    def edit(raw: dict) -> None:
        if missing == "categories":
            del raw["categories"]
        else:
            del raw["tasks"][0]["category_id"]

    _edit_raw(path, edit)
    loaded = load_project(path)
    assert loaded.categories == [] and loaded.tasks[0].category_id is None


def test_version_3_ignores_a_stale_project_code_key(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("a")]), tmp_path)
    _edit_raw(path, lambda raw: raw["tasks"][0].update(project_code="OLD"))
    loaded = load_project(path)
    assert loaded.categories == [] and loaded.tasks[0].category_id is None


def test_legacy_project_codes_become_categories(tmp_path: Path) -> None:
    path = _legacy_codes_file(tmp_path, ["PRJ-A", "PRJ-B", "PRJ-A", ""])
    loaded = load_project(path)
    assert [(c.name, c.prj_code, c.color) for c in loaded.categories] == [
        ("PRJ-A", "PRJ-A", "blue"),
        ("PRJ-B", "PRJ-B", "indigo"),
    ]
    first, second = loaded.categories
    assert [t.category_id for t in loaded.tasks] == [first.id, second.id, first.id, None]
    raw = json.loads(save_project(loaded, tmp_path, overwrite=True).read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION and len(raw["categories"]) == 2


@pytest.mark.parametrize("missing", ["delete", "null"])
def test_legacy_codes_file_without_project_code_loads_as_undecided(tmp_path: Path, missing: str) -> None:
    path = _legacy_codes_file(tmp_path, ["X"])
    _edit_raw(path, lambda raw: raw["tasks"][0].pop("project_code") if missing == "delete" else raw["tasks"][0].update(project_code=None))
    loaded = load_project(path)
    assert loaded.categories == [] and loaded.tasks[0].category_id is None


def test_legacy_project_code_is_trimmed(tmp_path: Path) -> None:
    loaded = load_project(_legacy_codes_file(tmp_path, ["  " + "A" * 20 + "  "]))
    assert loaded.categories[0].prj_code == "A" * 20


def test_legacy_code_that_is_not_a_valid_prj_code_keeps_only_the_name(tmp_path: Path) -> None:
    loaded = load_project(_legacy_codes_file(tmp_path, ["設計 A", "A\nB"]))
    assert [(c.name, c.prj_code) for c in loaded.categories] == [("設計 A", ""), ("A B", "")]
    raw = json.loads(save_project(loaded, tmp_path, overwrite=True).read_text(encoding="utf-8"))
    assert load_project(tmp_path / "demo.json").categories == loaded.categories  # 書き戻したファイルを、そのまま読める
    assert raw["version"] == FORMAT_VERSION


def test_legacy_reserved_code_becomes_undecided(tmp_path: Path) -> None:
    loaded = load_project(_legacy_codes_file(tmp_path, ["未定"]))
    assert loaded.categories == [] and loaded.tasks[0].category_id is None


@pytest.mark.parametrize("bad", ["A" * 21, 1, ["x"], True])
def test_invalid_legacy_project_code_is_rejected(tmp_path: Path, bad: object) -> None:
    with pytest.raises(ValueError, match="ProjectCode"):
        load_project(_legacy_codes_file(tmp_path, [bad]))


def _categorized(tmp_path: Path) -> Path:
    category = Category("開発")
    return save_project(Project("demo", tasks=[Task("a", category_id=category.id)], categories=[category]), tmp_path)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda raw: raw.update(categories={}), "カテゴリ"),
        (lambda raw: raw["tasks"][0].update(category_id="zzzzzzzz"), "カテゴリ"),
        (lambda raw: raw["tasks"][0].update(category_id=""), "カテゴリ"),
        (lambda raw: raw["tasks"][0].update(category_id=1), "カテゴリ"),
        (lambda raw: raw["categories"][0].update(name="未定"), "未定"),
        (lambda raw: raw["categories"][0].update(name="  "), "名前"),
        (lambda raw: raw["categories"][0].update(name=1), "名前"),
        (lambda raw: raw["categories"][0].update(name="あ" * 31), "名前"),
        (lambda raw: raw["categories"][0].update(name="開\n発"), "名前"),
        (lambda raw: raw["categories"][0].update(name="開\u200b発"), "名前"),
        (lambda raw: raw["categories"][0].update(kind="業\u200b務"), "種別"),
        (lambda raw: raw["categories"][0].update(prj_code="P\nQ"), "PRJ"),
        (lambda raw: raw["categories"][0].update(prj_code="設計"), "PRJ"),
        (lambda raw: raw["categories"][0].update(prj_code="PRJ 1"), "PRJ"),
        (lambda raw: raw["categories"][0].update(color="gold"), "色"),
        (lambda raw: raw["categories"][0].update(color=1), "色"),
        (lambda raw: raw["categories"][0].update(kind="あ" * 21), "種別"),
        (lambda raw: raw["categories"][0].update(kind="業務\n開発"), "種別"),
        (lambda raw: raw["categories"][0].update(kind=1), "種別"),
        (lambda raw: raw["categories"][0].update(prj_code="A" * 21), "PRJ"),
        (lambda raw: raw["categories"][0].update(prj_code=1), "PRJ"),
        (lambda raw: raw["categories"][0].update(expiry_date="2026-13-01"), "有効期限"),
        (lambda raw: raw["categories"][0].update(expiry_date="20261231"), "有効期限"),
        (lambda raw: raw["categories"][0].update(expiry_date=5), "有効期限"),
        (lambda raw: raw["categories"][0].pop("id"), "id"),
        (lambda raw: raw["categories"][0].update(id=""), "id"),
        (lambda raw: raw["categories"].append(dict(raw["categories"][0], name="別")), "id"),
        (lambda raw: raw["categories"].append(dict(raw["categories"][0], id="bbbbbbbb")), "重複"),
    ],
)
def test_invalid_categories_are_rejected(tmp_path: Path, edit: Callable[[dict], None], message: str) -> None:
    path = _categorized(tmp_path)
    _edit_raw(path, edit)
    with pytest.raises(ValueError, match=message):
        load_project(path)


def test_missing_optional_category_fields_use_defaults(tmp_path: Path) -> None:
    path = _categorized(tmp_path)

    def edit(raw: dict) -> None:
        for key in ("kind", "expiry_date", "color", "prj_code"):
            del raw["categories"][0][key]

    _edit_raw(path, edit)
    loaded = load_project(path).categories[0]
    assert (loaded.kind, loaded.expiry_date, loaded.color, loaded.prj_code) == ("", None, "blue", "")


def test_category_text_is_trimmed_on_load(tmp_path: Path) -> None:
    path = _categorized(tmp_path)
    _edit_raw(path, lambda raw: raw["categories"][0].update(name="  開発  ", prj_code=" P "))
    loaded = load_project(path).categories[0]
    assert (loaded.name, loaded.prj_code) == ("開発", "P")


def test_saving_duplicate_category_ids_is_refused(tmp_path: Path) -> None:
    a, b = Category("a", id="aaaaaaaa"), Category("b", id="aaaaaaaa")
    with pytest.raises(ValueError, match="カテゴリ"):
        save_project(Project("demo", categories=[a, b]), tmp_path)


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
    assert raw["version"] == FORMAT_VERSION == 17


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


def test_saved_file_is_version_3_and_refers_to_members_by_id(tmp_path: Path) -> None:
    project = ids_project()
    raw = json.loads(save_project(project, tmp_path).read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION == 17
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
    assert raw["version"] == FORMAT_VERSION


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


def test_loading_tidies_a_long_task_name(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    _edit_raw(path, lambda raw: raw["tasks"][0].update(name="あ" * 60))
    assert load_project(path).tasks[0].name == "あ" * 50


def test_loading_replaces_control_characters_in_a_task_name(tmp_path: Path) -> None:
    path = save_project(Project("demo", sections=[Section("s", [Task("t")])]), tmp_path)
    _edit_raw(path, lambda raw: raw["sections"][0]["tasks"][0].update(name="設計\n開発\t"))
    assert load_project(path).sections[0].tasks[0].name == "設計 開発"


def test_a_task_name_of_only_control_characters_loads_as_empty(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    _edit_raw(path, lambda raw: raw["tasks"][0].update(name="\n"))
    assert load_project(path).tasks[0].name == ""


@pytest.mark.parametrize("bad", [1, None, ["x"], True])
def test_a_task_name_that_is_not_a_string_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    _edit_raw(path, lambda raw: raw["tasks"][0].update(name=bad))
    with pytest.raises(ValueError, match="タスクの名前"):
        load_project(path)


def test_a_tidied_task_name_can_be_saved_again(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    _edit_raw(path, lambda raw: raw["tasks"][0].update(name="あ" * 60))
    loaded = load_project(path)
    assert load_project(save_project(loaded, tmp_path, overwrite=True)).tasks[0].name == "あ" * 50


def test_loading_replaces_zero_width_characters_in_a_task_name(tmp_path: Path) -> None:
    path = save_project(Project("demo", tasks=[Task("t")]), tmp_path)
    _edit_raw(path, lambda raw: raw["tasks"][0].update(name="\u200b設計\u200b開発\u2028"))
    assert load_project(path).tasks[0].name == "設計 開発"



def test_file_digest_is_the_same_for_the_same_content_and_none_when_missing(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    a.write_text("同じ", encoding="utf-8")
    b.write_text("同じ", encoding="utf-8")
    c.write_text("違う", encoding="utf-8")
    assert file_digest(a) == file_digest(b)
    assert file_digest(a) != file_digest(c)
    assert file_digest(tmp_path / "ない.json") is None


def test_check_external_change_unchanged_changed_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("元", encoding="utf-8")
    digest = file_digest(path)
    assert check_external_change(path, digest) is ExternalChange.UNCHANGED
    path.write_text("変更", encoding="utf-8")
    assert check_external_change(path, digest) is ExternalChange.CHANGED
    path.unlink()
    assert check_external_change(path, digest) is ExternalChange.MISSING


def test_check_external_change_ignores_a_modification_time_change_alone(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("元", encoding="utf-8")
    digest = file_digest(path)
    os.utime(path, (1_000_000_000, 1_000_000_000))
    assert check_external_change(path, digest) is ExternalChange.UNCHANGED


def test_check_external_change_without_a_remembered_digest_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("元", encoding="utf-8")
    assert check_external_change(path, None) is ExternalChange.UNCHANGED


def test_backup_file_copies_next_to_the_file_and_replaces_the_old_backup(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("一つ目", encoding="utf-8")
    backup = backup_file(path)
    assert backup == tmp_path / "p.json.bak"
    assert backup.read_text(encoding="utf-8") == "一つ目"
    path.write_text("二つ目", encoding="utf-8")
    backup_file(path)
    assert backup.read_text(encoding="utf-8") == "二つ目"


def test_backup_file_is_not_listed_as_a_project(tmp_path: Path) -> None:
    save_project(Project("p"), tmp_path)
    backup_file(tmp_path / "p.json")
    assert [f.name for f in list_project_files(tmp_path)] == ["p.json"]


def test_backup_file_raises_oserror_when_the_file_is_missing(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        backup_file(tmp_path / "ない.json")


def test_dumps_and_parse_round_trip(tmp_path: Path) -> None:
    from projectapp.storage import dumps_project, parse_project

    alice = Member("甲", 1.0)
    task = Task("調査", assignees=[Assignee("甲", 0.5)])
    project = Project("文字列", date(2026, 10, 1), members=[alice], sections=[Section("A", tasks=[task])])
    text = dumps_project(project)
    loaded = parse_project(text, "文字列")
    assert loaded == project
    assert loaded.sections[0].tasks[0].id == task.id
    save_project(project, tmp_path)
    assert (tmp_path / "文字列.json").read_text(encoding="utf-8") == text


def test_dumps_rejects_duplicate_ids() -> None:
    from projectapp.storage import dumps_project

    one = Task("a", id="same")
    two = Task("b", id="same")
    with pytest.raises(ValueError):
        dumps_project(Project("p", date(2026, 10, 1), tasks=[one, two]))


def test_events_roundtrip_and_are_ordered_as_saved(tmp_path: Path) -> None:
    a = Event(date(2026, 10, 20), date(2026, 10, 24), "リリース", "red", id="e1")
    b = Event(date(2026, 10, 1), date(2026, 10, 1), "休み", "gray", id="e2")
    project = Project("p", events=[a, b])
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.events == [a, b]
    assert [e.id for e in loaded.events] == ["e1", "e2"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION
    assert raw["events"][0] == {
        "start": "2026-10-20", "end": "2026-10-24", "text": "リリース", "color": "red", "id": "e1", "closed": False
    }


def test_version_3_file_loads_without_events(tmp_path: Path) -> None:
    path = save_project(Project("p"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 3
    del raw["events"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).events == []


def test_version_3_file_ignores_an_events_key(tmp_path: Path) -> None:
    path = save_project(Project("p", events=[Event(date(2026, 10, 1), date(2026, 10, 1), "x", "red", id="e1")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 3
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).events == []


def test_version_4_file_without_events_key_is_empty(tmp_path: Path) -> None:
    path = save_project(Project("p"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["events"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).events == []


def test_event_color_is_lowercased_on_load(tmp_path: Path) -> None:
    path = save_project(Project("p", events=[Event(date(2026, 10, 1), date(2026, 10, 1), "x", "red", id="e1")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["events"][0]["color"] = " Red "
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).events[0].color == "red"


@pytest.mark.parametrize(
    "change",
    [
        {"start": "2026-10-02", "end": "2026-10-01"},
        {"start": "20261001"},
        {"start": 20261001},
        {"end": None},
        {"text": ""},
        {"text": "あ" * 31},
        {"text": 5},
        {"color": "#ff0000"},
        {"color": "transparent"},
        {"color": None},
        {"id": ""},
        {"id": 3},
    ],
)
def test_invalid_event_is_rejected(tmp_path: Path, change: dict) -> None:
    path = save_project(Project("p", events=[Event(date(2026, 10, 1), date(2026, 10, 1), "x", "red", id="e1")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["events"][0].update(change)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_project(path)


@pytest.mark.parametrize("value", ["x", 1, [1], [{"start": "2026-10-01"}]])
def test_malformed_events_are_rejected(tmp_path: Path, value: object) -> None:
    path = save_project(Project("p"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["events"] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_project(path)


def test_duplicate_event_ids_are_rejected_on_save_and_load(tmp_path: Path) -> None:
    from projectapp.storage import dumps_project

    same = [Event(date(2026, 10, 1), date(2026, 10, 1), "a", "red", id="e1"), Event(date(2026, 10, 2), date(2026, 10, 2), "b", "red", id="e1")]
    with pytest.raises(ValueError, match="イベント"):
        dumps_project(Project("p", events=same))


def test_new_ids_do_not_collide_with_event_ids() -> None:
    project = Project("p", events=[Event(date(2026, 10, 1), date(2026, 10, 1), "a", id="e1")])
    assert "e1" in project.used_ids()


@pytest.mark.parametrize("value", [None, 0, 40, 100])
def test_task_progress_roundtrip(tmp_path: Path, value: int | None) -> None:
    loaded = load_project(save_project(Project("p", tasks=[Task("t", progress=value)]), tmp_path))
    assert loaded.tasks[0].progress == value


def _rewrite_task(path: Path, **changes: object) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0].update(changes)
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_file_without_task_progress_loads_as_none(tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("t", progress=40)]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["tasks"][0]["progress"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].progress is None


@pytest.mark.parametrize("bad", [True, False, 40.5, 40.0, "40", -1, 101, [40]])
def test_invalid_task_progress_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("p", tasks=[Task("t")]), tmp_path)
    _rewrite_task(path, progress=bad)
    with pytest.raises(ValueError, match="進捗度"):
        load_project(path)


def test_progress_key_in_a_version_4_file_is_ignored(tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("t")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 4
    raw["tasks"][0]["progress"] = 40
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].progress is None


def test_a_checkpoint_loads_without_progress(tmp_path: Path) -> None:
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 20, 17, 0))
    path = save_project(Project("p", tasks=[checkpoint]), tmp_path)
    _rewrite_task(path, progress=50)
    assert load_project(path).tasks[0].progress is None


def write_member_icon(path: Path, value: object, version: int = 7) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = version
    raw["members"][0]["icon"] = value
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_member_icon_roundtrips(tmp_path: Path, icon: str) -> None:
    project = Project("demo", members=[Member("甲", 1.0, icon=icon), Member("乙", 1.0)])
    loaded = load_project(save_project(project, tmp_path))
    assert [m.icon for m in loaded.members] == [icon, ""]


def test_a_file_without_the_icon_key_loads_with_no_icon(tmp_path: Path) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 6
    del raw["members"][0]["icon"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).members[0].icon == ""


def test_a_version_6_file_ignores_an_icon_key(tmp_path: Path, icon: str) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, icon, version=6)
    assert load_project(path).members[0].icon == ""


@pytest.mark.parametrize("value", [None, ""])
def test_a_null_or_empty_icon_means_no_icon(tmp_path: Path, value: object) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, value)
    assert load_project(path).members[0].icon == ""


@pytest.mark.parametrize(
    "value",
    ["https://example.com/a.png", "data:image/png;base64,!!!", "data:image/png;base64,AAAA", 123, ["x"]],
)
def test_an_invalid_icon_is_rejected_on_load(tmp_path: Path, value: object) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, value)
    with pytest.raises(ValueError, match="アイコン"):
        load_project(path)


def test_a_member_added_for_an_unknown_assignee_is_saved_with_an_empty_icon(tmp_path: Path) -> None:
    project = Project("demo", sections=[Section("s", [Task("t", assignees=[Assignee("丙", 1.0)])])])
    raw = json.loads(save_project(project, tmp_path).read_text(encoding="utf-8"))
    assert raw["members"] == [{"name": "丙", "ratio": 1.0, "levels": {}, "id": raw["members"][0]["id"], "icon": "", "work_days": []}]


def test_an_icon_with_a_huge_declared_size_is_rejected_on_load_with_a_value_error(tmp_path: Path) -> None:
    import base64
    import struct
    import zlib

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress(b"\0" * 100)) + chunk(b"IEND", b"")
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, "data:image/png;base64," + base64.b64encode(raw).decode())
    with pytest.raises(ValueError, match="アイコン"):
        load_project(path)


def test_a_top_level_work_days_key_is_not_written_or_read() -> None:
    raw = json.loads(dumps_project(Project("p")))
    assert "work_days" not in raw
    raw["work_days"] = [{"day": "2026-10-17", "start": "13:00:00", "end": "16:00:00"}]
    assert not hasattr(parse_project(json.dumps(raw), "p"), "work_days")


@pytest.mark.parametrize(
    "rows",
    [
        "x",  # リストでない
        [1],  # 行が辞書でない
        [{"day": "10/17", "start": None, "end": None}],  # 日付の形式
        [{"day": "2026-10-17", "start": "13:00:00", "end": None}],  # 片方だけ
        [{"day": "2026-10-17", "start": "16:00:00", "end": "13:00:00"}],  # 開始 > 終了
        [{"day": "2026-10-17", "start": 9, "end": 10}],  # 時刻が文字列でない
        [{"day": "2026-10-17", "start": "13:00+09:00", "end": "16:00+09:00"}],  # タイムゾーン付き
        [{"day": "2026-10-17", "start": "13:00:00.5", "end": "16:00:00"}],  # 秒未満
        [{"day": "2026-10-17", "start": "1300", "end": "1600"}],  # 省略形
        [{"day": "2026-10-17", "start": None, "end": None}, {"day": "2026-10-17", "start": None, "end": None}],  # 重複
    ],
)
def test_bad_work_days_are_rejected(rows: object) -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", id="m1")])))
    raw["members"][0]["work_days"] = rows
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_member_work_days_round_trip_in_date_order() -> None:
    member = Member(
        "甲",
        id="m1",
        work_days=[WorkDay(date(2026, 10, 18)), WorkDay(date(2026, 10, 17), time(13), time(16))],
    )
    text = dumps_project(Project("p", members=[member]))
    saved = json.loads(text)["members"][0]["work_days"]
    assert saved == [
        {"day": "2026-10-17", "start": "13:00:00", "end": "16:00:00", "note": ""},
        {"day": "2026-10-18", "start": None, "end": None, "note": ""},
    ]
    loaded = parse_project(text, "p").members[0].work_days
    assert loaded == [WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 18))]


def test_members_without_work_days_load_as_empty() -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", id="m1")])))
    raw["version"] = 7
    del raw["members"][0]["work_days"]
    assert parse_project(json.dumps(raw), "p").members[0].work_days == []


def test_task_parameters_round_trip_and_the_version_is_10(tmp_path: Path) -> None:
    project = Project("p", parameters=[Parameter("Python", []), Parameter("Java", [])], tasks=[Task("a", parameters=["Python", "Java"])])
    path = save_project(project, tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION == 17
    assert raw["tasks"][0]["parameters"] == ["Python", "Java"]
    assert load_project(path).tasks[0].parameters == ["Python", "Java"]


def test_a_file_without_the_parameters_key_loads_as_none_attached(tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("a", parameters=["P"])]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].pop("parameters"))
    assert load_project(path).tasks[0].parameters == []


def test_unregistered_and_duplicate_parameter_names_are_kept_once(tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(parameters=["ない", "ない", "ある"]))
    assert load_project(path).tasks[0].parameters == ["ない", "ある"]


@pytest.mark.parametrize("bad", ["Python", [1], [None], {"a": 1}])
def test_a_malformed_parameters_value_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("p", tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(parameters=bad))
    with pytest.raises(ValueError):
        load_project(path)


def test_summaries_and_checkpoints_lose_their_parameters_on_load(tmp_path: Path) -> None:
    kid = Task("c", id="c")
    summary = Task("まとめ", kind=TaskKind.SUMMARY, children=["c"])
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17))
    path = save_project(Project("p", tasks=[summary, kid, checkpoint]), tmp_path)
    _rewrite(path, lambda d: [t.update(parameters=["P"]) for t in (d["tasks"][0], d["tasks"][2])])
    assert [t.parameters for t in load_project(path).tasks] == [[], [], []]


def _weekly_project() -> Project:
    first = [Assignee("田中")]
    second = [Assignee("田中"), Assignee("鈴木", 0.5)]
    task = Task("a", id="t1", assignees=[Assignee("田中"), Assignee("鈴木", 0.5)], weekly_crew=[first, second])
    return Project("p", members=[Member("田中"), Member("鈴木")], tasks=[task])


def test_format_version_is_eleven() -> None:
    assert FORMAT_VERSION == 17


def test_weekly_crew_roundtrips_and_assignees_is_the_union(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    loaded = load_project(path).tasks[0]
    assert loaded.weekly_crew == [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木", 0.5)]]
    assert loaded.assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]
    saved = json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["weekly_crew"]
    assert [[ref["allocation"] for ref in week] for week in saved] == [[1.0], [1.0, 0.5]]
    assert all("member" in ref for week in saved for ref in week)


def test_the_union_wins_over_the_assignees_in_the_file(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignees=[]))
    assert load_project(path).tasks[0].assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]


def test_a_file_without_weekly_crew_loads_as_not_weekly(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].pop("weekly_crew"))
    task = load_project(path).tasks[0]
    assert task.weekly_crew == []
    assert task.assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]


def test_weekly_crew_in_an_older_version_is_not_read(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d.update(version=9))
    assert load_project(path).tasks[0].weekly_crew == []


def _bad_weeks(data: dict) -> list[object]:
    member = data["members"][0]["id"]
    ref = {"member": member, "allocation": 1.0}
    return [
        [[]],  # 担当者のいない週
        "x",
        ["x"],
        [[{"name": "田中", "allocation": 1.0}]],  # 旧キー name
        [[{"member": "no-such-id", "allocation": 1.0}]],
        [[ref, dict(ref)]],  # 同じ週に同じメンバー
        [[{"member": member, "allocation": 2.0}]],  # 範囲外
        [[ref] for _ in range(MAX_WEEKS + 1)],  # 上限超え
    ]


@pytest.mark.parametrize("index", range(8))
def test_bad_weekly_crew_is_rejected(index: int, tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(weekly_crew=_bad_weeks(d)[index]))
    with pytest.raises(ValueError):
        load_project(path)


def test_weekly_crew_is_dropped_for_a_checkpoint(tmp_path: Path) -> None:
    task = Task("c", id="c1", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), weekly_crew=[[Assignee("田中")]])
    path = save_project(Project("p", members=[Member("田中")], tasks=[task]), tmp_path)
    assert load_project(path).tasks[0].weekly_crew == []


def test_the_plantuml_notice_option_round_trips_and_defaults_to_on() -> None:
    assert Project("p").plantuml_overload_notice is True
    off = parse_project(dumps_project(Project("p", plantuml_overload_notice=False)), "p")
    assert off.plantuml_overload_notice is False
    assert json.loads(dumps_project(Project("p")))["plantuml_overload_notice"] is True


def test_an_old_file_without_the_plantuml_notice_option_reads_as_on() -> None:
    raw = json.loads(dumps_project(Project("p", plantuml_overload_notice=False)))
    raw["version"] = 11
    del raw["plantuml_overload_notice"]
    assert parse_project(json.dumps(raw), "p").plantuml_overload_notice is True
    raw["version"] = 11
    raw["plantuml_overload_notice"] = False  # version 11 ではまだ読まない
    assert parse_project(json.dumps(raw), "p").plantuml_overload_notice is True


@pytest.mark.parametrize("value", ["false", 0, 1, None, []])
def test_a_non_boolean_plantuml_notice_option_is_refused(value: object) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["plantuml_overload_notice"] = value
    with pytest.raises(ValueError, match="PlantUML の通知"):
        parse_project(json.dumps(raw), "p")


def test_the_ratio_limits_round_trip_and_default_to_none() -> None:
    project = Project("p", ratio_limit_upper=1.5, ratio_limit_lower=0.5)
    loaded = parse_project(dumps_project(project), "p")
    assert (loaded.ratio_limit_upper, loaded.ratio_limit_lower) == (1.5, 0.5)
    plain = parse_project(dumps_project(Project("p")), "p")
    assert (plain.ratio_limit_upper, plain.ratio_limit_lower) == (None, None)


def test_a_file_without_the_ratio_limit_keys_reads_as_no_limits() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw.pop("ratio_limit_upper")
    raw.pop("ratio_limit_lower")
    raw["version"] = 12
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.ratio_limits.upper is None and loaded.ratio_limits.lower is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ratio_limit_upper", "0.5"),
        ("ratio_limit_upper", True),
        ("ratio_limit_upper", float("nan")),
        ("ratio_limit_upper", 0.05),
        ("ratio_limit_upper", 3.1),
        ("ratio_limit_lower", 0.05),
        ("ratio_limit_lower", 3.1),
        ("ratio_limit_lower", -0.5),
        ("ratio_limit_lower", [0]),
    ],
)
def test_an_invalid_ratio_limit_is_rejected(key: str, value: object) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw[key] = value
    with pytest.raises(ValueError, match="相対比率の"):
        parse_project(json.dumps(raw), "p")


def test_the_ratio_limits_are_rounded_to_four_decimals() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["ratio_limit_upper"] = 1.123456
    assert parse_project(json.dumps(raw), "p").ratio_limit_upper == 1.1235


def test_a_lower_limit_above_the_upper_limit_is_rejected() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["ratio_limit_upper"], raw["ratio_limit_lower"] = 0.8, 1.2
    with pytest.raises(ValueError, match="下限"):
        parse_project(json.dumps(raw), "p")
    raw["ratio_limit_upper"] = raw["ratio_limit_lower"] = 1.0  # 同じ値は許す
    assert parse_project(json.dumps(raw), "p").ratio_limits.lower == 1.0


@pytest.mark.parametrize(("key", "value"), [("ratio_limit_upper", 1.6), ("ratio_limit_upper", 0.4), ("ratio_limit_lower", 1.6), ("ratio_limit_lower", 0.4)])
def test_a_ratio_limit_outside_the_default_range_is_rejected(key: str, value: float) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw[key] = value
    with pytest.raises(ValueError, match="50〜150%"):
        parse_project(json.dumps(raw), "p")


def test_ratio_limits_on_the_default_range_edges_are_accepted() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["ratio_limit_upper"], raw["ratio_limit_lower"] = 1.5, 0.5
    loaded = parse_project(json.dumps(raw), "p")
    assert (loaded.ratio_limit_upper, loaded.ratio_limit_lower) == (1.5, 0.5)


def test_a_base_ratio_outside_the_default_range_still_loads() -> None:
    project = Project("p", members=[Member("速い", 2.0), Member("遅い", 0.3)])
    loaded = parse_project(dumps_project(project), "p")
    assert [m.ratio for m in loaded.members] == [2.0, 0.3]  # 基本比率の入力範囲は 10〜300% のまま


def test_work_day_note_round_trips_and_is_stripped() -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17), note="夏季休暇")])
    text = dumps_project(Project("p", members=[member]))
    raw = json.loads(text)
    assert raw["version"] == 17
    assert raw["members"][0]["work_days"][0]["note"] == "夏季休暇"
    assert parse_project(text, "p").members[0].work_days[0].note == "夏季休暇"
    raw["members"][0]["work_days"][0]["note"] = "  通院  "
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == "通院"


def test_work_days_without_a_note_key_load_with_an_empty_note() -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17))])
    raw = json.loads(dumps_project(Project("p", members=[member])))
    del raw["members"][0]["work_days"][0]["note"]
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == ""
    raw["members"][0]["work_days"][0]["note"] = None
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == ""


def test_a_note_in_a_version_13_file_is_ignored() -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17), note="夏季休暇")])
    raw = json.loads(dumps_project(Project("p", members=[member])))
    raw["version"] = 13
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == ""


@pytest.mark.parametrize("note", [3, ["x"], "あ" * 31, "a\nb"])
def test_bad_work_day_notes_are_rejected(note: object) -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17))])
    raw = json.loads(dumps_project(Project("p", members=[member])))
    raw["members"][0]["work_days"][0]["note"] = note
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_event_closed_round_trips(tmp_path: Path) -> None:
    event = Event(date(2026, 10, 26), date(2026, 10, 28), "夏季休業", id="e1", closed=True)
    path = save_project(Project("p", events=[event]), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["events"][0]["closed"] is True
    assert load_project(path).events[0].closed is True


def test_events_without_a_closed_key_load_as_open() -> None:
    raw = json.loads(dumps_project(Project("p", events=[Event(date(2026, 10, 26), date(2026, 10, 28), "x", id="e1")])))
    del raw["events"][0]["closed"]
    assert parse_project(json.dumps(raw), "p").events[0].closed is False


def test_closed_in_a_version_14_file_is_ignored() -> None:
    event = Event(date(2026, 10, 26), date(2026, 10, 28), "x", id="e1", closed=True)
    raw = json.loads(dumps_project(Project("p", events=[event])))
    raw["version"] = 14
    assert parse_project(json.dumps(raw), "p").events[0].closed is False


@pytest.mark.parametrize("closed", [None, 1, "true", ["x"]])
def test_bad_event_closed_values_are_rejected(closed: object) -> None:
    raw = json.loads(dumps_project(Project("p", events=[Event(date(2026, 10, 26), date(2026, 10, 28), "x", id="e1")])))
    raw["events"][0]["closed"] = closed
    with pytest.raises(ValueError, match="休み"):
        parse_project(json.dumps(raw), "p")


def test_ratio_unclamped_round_trips() -> None:
    members = [Member("甲", 2.0, id="m1", ratio_unclamped=True), Member("乙", 1.0, id="m2")]
    text = dumps_project(Project("p", members=members))
    raw = json.loads(text)
    assert raw["version"] == 17
    assert [m["ratio_unclamped"] for m in raw["members"]] == [True, False]
    assert [m.ratio_unclamped for m in parse_project(text, "p").members] == [True, False]


def test_a_file_without_the_ratio_unclamped_key_loads_as_clamped() -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", 1.0, id="m1", ratio_unclamped=True)])))
    del raw["members"][0]["ratio_unclamped"]
    assert parse_project(json.dumps(raw), "p").members[0].ratio_unclamped is False


def test_ratio_unclamped_in_a_version_15_file_is_ignored() -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", 1.0, id="m1", ratio_unclamped=True)])))
    raw["version"] = 15
    assert parse_project(json.dumps(raw), "p").members[0].ratio_unclamped is False


@pytest.mark.parametrize("value", [1, "true", None, [True]])
def test_a_non_boolean_ratio_unclamped_is_rejected_on_load(value: object) -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", 1.0, id="m1")])))
    raw["members"][0]["ratio_unclamped"] = value
    with pytest.raises(ValueError, match="丸め"):
        parse_project(json.dumps(raw), "p")
