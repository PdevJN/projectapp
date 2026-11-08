import json
from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import Assignee, Member, Project, Section, Task
from projectapp.storage import load_project, save_project

START = datetime(2026, 11, 2, 9)


def project_with_daily() -> Project:
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木", 0.5)]] * 4
    task = Task(
        "a",
        id="ta",
        planned_start=START,
        effort_hours=20.0,
        assignees=[Assignee("田中"), Assignee("鈴木", 0.5)],
        weekly_crew=[[Assignee("田中"), Assignee("鈴木", 0.5)], [Assignee("田中")]],
        daily_crew={0: [list(d) for d in days]},
    )
    return Project(
        name="p",
        base_date=START.date(),
        members=[Member("田中"), Member("鈴木")],
        sections=[Section("s", tasks=[task])],
    )


def test_daily_crew_round_trips(tmp_path: Path) -> None:
    loaded = load_project(save_project(project_with_daily(), tmp_path))
    task = loaded.sections[0].tasks[0]
    assert sorted(task.daily_crew) == [0]
    assert [[a.name for a in d] for d in task.daily_crew[0]] == [["田中"]] * 3 + [
        ["田中", "鈴木"]
    ] * 4
    assert task.daily_crew[0][3][1].allocation == 0.5


def edited(tmp_path: Path, change) -> Path:
    path = save_project(project_with_daily(), tmp_path)
    raw = json.loads(path.read_text("utf-8"))
    change(raw["sections"][0]["tasks"][0], raw)
    path.write_text(json.dumps(raw), "utf-8")
    return path


def test_old_files_without_the_key_load_with_no_daily_crew(tmp_path: Path) -> None:
    def old(task, raw):
        raw["version"] = 21
        task.pop("daily_crew", None)

    path = edited(tmp_path, old)
    assert load_project(path).sections[0].tasks[0].daily_crew == {}


def member_id(raw: dict) -> str:
    return raw["members"][0]["id"]


@pytest.mark.parametrize(
    "change",
    [
        lambda t, r: t["daily_crew"].update(
            {"5": t["daily_crew"]["0"]}
        ),  # 週の数を超える添字
        lambda t, r: t["daily_crew"]["0"].pop(),  # 7 日でない
        lambda t, r: t["daily_crew"]["0"].__setitem__(2, []),  # 担当のいない日
        lambda t, r: t["daily_crew"].update(
            {"x": t["daily_crew"]["0"]}
        ),  # 添字が整数でない
        lambda t, r: t["daily_crew"]["0"][0].append(
            {"member": "nobody", "allocation": 1}
        ),  # メンバーにいない人
        lambda t, r: t.__setitem__("daily_crew", [1]),  # 辞書でない
    ],
)
def test_bad_daily_crew_is_refused(tmp_path: Path, change) -> None:
    path = edited(tmp_path, change)
    with pytest.raises(ValueError):
        load_project(path)


def test_a_newer_version_is_refused(tmp_path: Path) -> None:
    def newer(task, raw):
        raw["version"] = 23

    path = edited(tmp_path, newer)
    with pytest.raises(ValueError, match="新しい"):
        load_project(path)
