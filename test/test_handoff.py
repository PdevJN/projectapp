import json
from datetime import date, datetime
from pathlib import Path

import pytest

from projectapp.handoff import (
    CATEGORY_COLORS,
    JSON_FILE_TYPES,
    Handoff,
    build_todos,
    default_filename,
    summary,
    tasks_for,
    write_json,
)
from projectapp.models import Assignee, Actual, Level, Member, Parameter, Project, Section, Status, Task

BASE = date(2026, 10, 5)  # 月曜


def make_project(*tasks: Task, members: list[Member] | None = None, sections: list[Section] | None = None) -> Project:
    chosen = [Member("田中", 0.5)] if members is None else members
    return Project("案件", base_date=BASE, members=chosen, tasks=list(tasks), sections=sections or [])


def task(name: str = "設計", **kwargs) -> Task:
    kwargs.setdefault("assignees", [Assignee("田中")])
    return Task(name, **kwargs)


def build(project: Project, member: str = "田中") -> Handoff:
    return build_todos(project, member, {})


def assert_todoapp_shape(data: dict) -> None:
    """`file-format.md` の必須キーと型。"""
    assert set(data) == {"version", "items", "records", "categories"}
    assert data["version"] == 1
    category_ids = {c["id"] for c in data["categories"]}
    item_ids = {i["id"] for i in data["items"]}
    for category in data["categories"]:
        assert set(category) == {"id", "name", "kind", "expiry_date", "color", "prj_code"}
        assert category["color"] in CATEGORY_COLORS
        assert category["expiry_date"] is None
    for item in data["items"]:
        assert set(item) == {"id", "name", "schedule_type", "anchor_date", "estimate_hours", "category_id", "done_date"}
        assert isinstance(item["id"], str) and len(item["id"]) == 32
        assert item["schedule_type"] in {"daily", "weekly", "monthly", "one_time"}
        date.fromisoformat(item["anchor_date"])
        assert isinstance(item["estimate_hours"], float)
        assert item["category_id"] is None or item["category_id"] in category_ids
        assert item["done_date"] is None
    for record in data["records"]:
        assert set(record) == {"id", "item_id", "item_name", "start_time", "end_time"}
        assert record["item_id"] in item_ids
        datetime.fromisoformat(record["start_time"])
        assert record["end_time"] is None or datetime.fromisoformat(record["end_time"])


def test_only_unfinished_tasks_of_the_member_are_exported_in_order() -> None:
    project = make_project(
        task("a"),
        task("done", status=Status.DONE),
        task("other", assignees=[Assignee("鈴木")]),
        task("nobody", assignees=[]),
        sections=[Section("S", [task("s1", status=Status.RUNNING)])],
    )
    result = build(project)
    assert [i["name"] for i in result.data["items"]] == ["a", "s1"]
    assert result.task_count == 2
    assert [t.name for t in tasks_for(project, "田中")] == ["a", "s1"]
    assert_todoapp_shape(result.data)


@pytest.mark.parametrize(
    ("kwargs", "schedule_type", "anchor"),
    [
        (dict(planned_start=datetime(2026, 10, 5, 9), effort_hours=3), "one_time", "2026-10-05"),  # 6h で 1 日に収まる
        (dict(planned_start=datetime(2026, 10, 5, 9), effort_hours=13), "daily", "2026-10-05"),  # 26h で 4 日
        ({}, "one_time", "2026-10-05"),  # 開始予定なし → 基準日
        (dict(planned_start=datetime(2026, 10, 6, 9)), "one_time", "2026-10-06"),  # 期間の情報がない
        (dict(planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 6, 17)), "one_time", "2026-10-06"),
        (dict(planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 7, 0, 0)), "one_time", "2026-10-06"),
        (dict(planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 8, 12)), "daily", "2026-10-06"),
        (dict(planned_start=datetime(2026, 10, 6, 9), deadline=datetime(2026, 10, 9, 17)), "daily", "2026-10-06"),
    ],
    ids=["one-day", "multi-day", "no-start", "no-span", "same-day-end", "midnight-end", "later-end", "deadline-only"],
)
def test_schedule_type_and_anchor_date(kwargs: dict, schedule_type: str, anchor: str) -> None:
    item = build(make_project(task(**kwargs))).data["items"][0]
    assert (item["schedule_type"], item["anchor_date"]) == (schedule_type, anchor)


@pytest.mark.parametrize(
    ("effort", "members", "expected"),
    [
        (13.0, [Member("田中", 0.5)], 26.0),  # 相対比率 50% → 担当者は 2 倍の時間
        (13.0, [], 13.0),  # メンバーにいない担当者は 100%
        (0.0, [Member("田中", 0.5)], 0.0),
        (1.0, [Member("田中", 0.3)], 3.33),  # 小数第 2 位に丸める
    ],
)
def test_estimate_hours_divides_by_the_relative_ratio(effort: float, members: list[Member], expected: float) -> None:
    item = build(make_project(task(effort_hours=effort), members=members)).data["items"][0]
    assert item["estimate_hours"] == expected


def test_the_allocation_does_not_change_the_estimate() -> None:
    item = build(make_project(task(effort_hours=13.0, assignees=[Assignee("田中", 0.25)]))).data["items"][0]
    assert item["estimate_hours"] == 26.0


def test_categories_follow_project_codes() -> None:
    project = make_project(
        task("A", project_code="PRJ-1"), task("B", project_code="PRJ-2"), task("C", project_code="PRJ-1"), task("D")
    )
    data = build(project).data
    first, second = data["categories"]
    assert [first["name"], second["name"]] == ["PRJ-1", "PRJ-2"]
    assert (first["prj_code"], first["kind"]) == ("PRJ-1", "")
    assert [first["color"], second["color"]] == ["blue", "indigo"]
    assert [i["category_id"] for i in data["items"]] == [first["id"], second["id"], first["id"], None]
    assert_todoapp_shape(data)


def test_category_colors_cycle_after_ten_codes() -> None:
    project = make_project(*(task(f"t{i}", project_code=f"C{i}") for i in range(11)))
    categories = build(project).data["categories"]
    assert len(categories) == 11
    assert categories[10]["color"] == categories[0]["color"] == "blue"


def test_actuals_become_records() -> None:
    work = task(actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 10, 30, 15)), Actual(datetime(2026, 10, 6, 9))])
    result = build(make_project(work))
    item = result.data["items"][0]
    first, second = result.data["records"]
    assert (first["start_time"], first["end_time"]) == ("2026-10-05T09:00:00", "2026-10-05T10:30:15")
    assert (second["start_time"], second["end_time"]) == ("2026-10-06T09:00:00", None)
    assert first["item_id"] == second["item_id"] == item["id"]
    assert first["item_name"] == "設計"
    assert first["id"] != second["id"]
    assert result.skipped_records == 0
    assert_todoapp_shape(result.data)


def test_only_the_latest_running_record_is_kept() -> None:
    a = task("a", actuals=[Actual(datetime(2026, 10, 4, 9), datetime(2026, 10, 4, 10)), Actual(datetime(2026, 10, 5, 9))])
    b = task("b", actuals=[Actual(datetime(2026, 10, 6, 9))])
    result = build(make_project(a, b))
    items = {i["name"]: i["id"] for i in result.data["items"]}
    running = [r for r in result.data["records"] if r["end_time"] is None]
    assert [r["item_id"] for r in running] == [items["b"]]
    assert len(result.data["records"]) == 2  # a の終了した区間と、b の実行中
    assert result.skipped_records == 1


def test_ids_are_stable_across_exports_and_task_changes() -> None:
    first, second = task("同名"), task("同名")
    before = build(make_project(first, second)).data
    assert before == build(make_project(first, second)).data
    ids = [i["id"] for i in before["items"]]
    assert ids[0] != ids[1]
    first.status = Status.DONE  # 対象から外れても、残るタスクの id は変わらない
    after = build(make_project(first, second)).data
    assert [i["id"] for i in after["items"]] == [ids[1]]


def test_nothing_about_other_people_is_exported() -> None:
    project = make_project(task("自分"), task("別件", assignees=[Assignee("鈴木")]), members=[Member("田中", 0.5), Member("鈴木", 2.0)])
    text = json.dumps(build(project).data, ensure_ascii=False)
    assert "鈴木" not in text and "別件" not in text and "assignee" not in text


def test_an_empty_result_is_valid() -> None:
    result = build(make_project())
    assert result.task_count == 0
    assert result.data == {"version": 1, "items": [], "records": [], "categories": []}


def test_summary_mentions_skipped_records_only_when_there_are_some() -> None:
    assert summary(Handoff({}, 3, 0)) == "3 件を書き出しました"
    assert summary(Handoff({}, 3, 2)) == "3 件を書き出しました(実行中の記録が複数あったため、2 件は書き出していません)"


@pytest.mark.parametrize(
    ("member", "expected"),
    [("田中", "todos-田中.json"), ("a/b:c", "todos-a_b_c.json"), ("  ", "todos-member.json"), ("..x", "todos-x.json")],
)
def test_default_filename(member: str, expected: str) -> None:
    assert default_filename(member) == expected


def test_write_json_writes_pretty_utf8_and_adds_the_extension(tmp_path: Path) -> None:
    data = {"version": 1, "items": [{"name": "設計"}]}
    path = write_json(tmp_path / "todos", data)
    assert path == tmp_path / "todos.json"
    text = path.read_text(encoding="utf-8")
    assert "設計" in text and '\n  "version": 1' in text and text.endswith("\n")
    assert json.loads(text) == data
    assert [p.name for p in tmp_path.iterdir()] == ["todos.json"]


def test_write_json_leaves_nothing_on_failure(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_json(tmp_path / "todos.json", {"x": object()})
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(OSError):
        write_json(tmp_path / "missing" / "todos.json", {})


def test_json_file_types_name_the_extension() -> None:
    assert any("*.json" in t for t in JSON_FILE_TYPES)


def test_the_anchor_date_is_the_pushed_start() -> None:
    from projectapp.handoff import _schedule

    a = Task("a", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=13)
    b = Task(
        "b",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=1,
        predecessors=["aaaaaaaa"],
    )
    project = Project("p", tasks=[a, b])
    assert _schedule(b, project, {}) == ("daily", "2026-10-06")  # 火 15:30 開始 → 水 9:00〜10:00


def test_a_task_is_exported_for_every_assignee() -> None:
    shared = task("共同", assignees=[Assignee("田中"), Assignee("鈴木")])
    project = make_project(shared, members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    assert [t.name for t in tasks_for(project, "田中")] == ["共同"]
    assert [t.name for t in tasks_for(project, "鈴木")] == ["共同"]


def test_the_estimate_is_the_assignees_own_share_of_the_effort() -> None:
    shared = task("共同", effort_hours=15.0, assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)])
    project = make_project(shared, members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    # 換算率は 1.0 + 0.5 = 1.5。田中は 15 × 1.0 / 1.5 = 10h、鈴木は 15 × 0.5 / 1.5 = 5h
    assert build(project, "田中").data["items"][0]["estimate_hours"] == pytest.approx(10.0)
    assert build(project, "鈴木").data["items"][0]["estimate_hours"] == pytest.approx(5.0)


def test_the_estimate_follows_the_parameters() -> None:
    solo = task("単独", effort_hours=15.0, assignees=[Assignee("田中", 1.0)])
    project = make_project(solo, members=[Member("田中", 1.0, {"経験": "上級"})])
    project.parameters = [Parameter("経験", [Level("上級", 0.5)])]
    assert build(project, "田中").data["items"][0]["estimate_hours"] == pytest.approx(10.0)  # 15 / 1.5
