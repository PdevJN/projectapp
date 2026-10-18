from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import FORMAT_VERSION, Project, Section, Status, Task, TaskKind
from projectapp.storage import dumps_project, load_project, parse_project, save_project
import json


def write_v6(tmp_path: Path, tasks: list[dict[str, object]]) -> Path:
    """version 6 のファイル(セクション 1 つ)。`write_raw` は version のない旧形式なので、`children` を読ませるにはこちらを使う。"""
    base = {
        "name": "t",
        "effort_hours": 0.0,
        "priority": "中",
        "status": "未着手",
        "color": "#4c8bf5",
        "predecessors": [],
        "assignees": [],
    }
    data = {
        "version": 6,
        "base_date": "2026-10-05",
        "daily_hours": 6.5,
        "members": [],
        "sections": [{"name": "s", "id": "sec00001", "tasks": [{**base, **raw} for raw in tasks], "sections": []}],
    }
    path = tmp_path / "v6.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def summary(name: str, *children: str, **fields: object) -> Task:
    return Task(name, id=name, kind=TaskKind.SUMMARY, children=list(children), **fields)  # type: ignore[arg-type]


def project_with_summary() -> Project:
    return Project(
        "p",
        sections=[Section("s", [summary("まとめ", "a", "b"), Task("a", id="a"), Task("b", id="b", predecessors=["a"])])],
    )


def test_version_is_6() -> None:
    assert FORMAT_VERSION == 6


def test_a_summary_roundtrips_with_its_children(tmp_path: Path) -> None:
    loaded = load_project(save_project(project_with_summary(), tmp_path))
    first = loaded.sections[0].tasks[0]
    assert (first.kind, first.children) == (TaskKind.SUMMARY, ["a", "b"])


def test_dumps_then_parse_keeps_the_children_order() -> None:
    project = Project("p", tasks=[summary("m", "b", "a"), Task("a", id="a"), Task("b", id="b")])
    assert parse_project(dumps_project(project), "p").tasks[0].children == ["b", "a"]


def test_a_summary_is_loaded_without_its_unused_fields(tmp_path: Path) -> None:
    raw = [
        {"name": "m", "id": "m", "kind": "まとめ", "children": ["a"], "effort_hours": 5.0, "status": "実行中",
         "planned_start": "2026-10-05T09:00:00", "progress": 30, "predecessors": ["a"]},
        {"name": "a", "id": "a"},
    ]
    task = load_project(write_v6(tmp_path, raw)).sections[0].tasks[0]
    assert (task.effort_hours, task.status, task.planned_start, task.progress, task.predecessors) == (
        0.0, Status.NOT_STARTED, None, None, [],
    )


def test_a_file_without_children_loads_as_empty(tmp_path: Path) -> None:
    assert load_project(write_v6(tmp_path, [{"name": "a"}])).sections[0].tasks[0].children == []


@pytest.mark.parametrize(
    "raw",
    [
        [{"name": "m", "id": "m", "kind": "まとめ", "children": []}],  # 子がない
        [{"name": "m", "id": "m", "kind": "まとめ"}],  # キーがない
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["zz"]}],  # 存在しない
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["m"]}],  # 自分自身
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["a", "a"]}, {"name": "a", "id": "a"}],  # 重複
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["a"]},
         {"name": "n", "id": "n", "kind": "まとめ", "children": ["a"]}, {"name": "a", "id": "a"}],  # 親が 2 つ
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["n"]},
         {"name": "n", "id": "n", "kind": "まとめ", "children": ["a"]}, {"name": "a", "id": "a"}],  # 入れ子
        [{"name": "a", "id": "a", "children": ["b"]}, {"name": "b", "id": "b"}],  # まとめでないのに子
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["a"]},
         {"name": "a", "id": "a", "predecessors": ["m"]}],  # 子が親を先行にする(循環)
        [{"name": "m", "id": "m", "kind": "まとめ", "children": "a"}],  # リストでない
    ],
)
def test_bad_summaries_are_rejected(tmp_path: Path, raw: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        load_project(write_v6(tmp_path, raw))


def test_a_version_5_file_with_children_key_ignores_it(tmp_path: Path) -> None:
    # version 5 以前に children はない。手編集でも、通常タスクの children は読まない
    path = write_v6(tmp_path, [{"name": "a", "id": "a", "children": ["zz"]}])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = 5
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path).sections[0].tasks[0].children == []


def test_task_map_covers_every_section() -> None:
    project = Project("p", tasks=[Task("x", id="x")], sections=[Section("s", [Task("y", id="y")])])
    assert set(project.task_map()) == {"x", "y"}


def test_planned_start_is_not_kept_on_a_summary() -> None:
    task = parse_project(
        dumps_project(Project("p", tasks=[summary("m", "a", planned_start=datetime(2026, 10, 5, 9)), Task("a", id="a")])),
        "p",
    ).tasks[0]
    assert task.planned_start is None
