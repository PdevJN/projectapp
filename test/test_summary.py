from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import FORMAT_VERSION, Project, Section, Status, Task, TaskKind
from projectapp.timeline import Schedule, effective_end, effective_start, is_overdue, progress_state
from projectapp import arrange
from projectapp.decompose import MAX_PARTS, Part, can_make_section, decompose, default_parts, split_effort
from projectapp.models import Actual, Assignee, Category, TaskUrl
from projectapp.filtering import TaskFilter, hidden_by_summary, matches, section_has_match, visible_task_indexes
from projectapp.links import RowSlot, row_slots
from projectapp.linkgraph import drop_task_links, link_options
from datetime import date

from projectapp.dashboard import Period, summarize_due, summarize_loads, summarize_progress, summarize_workload
from projectapp.merge import merge_projects
from projectapp.models import Member
from projectapp.plantuml import build_plantuml
from projectapp.timeline import Scale
from projectapp.summary import children_of, drop_child, parent_map, revert_empty, summary_progress, summary_status
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


def child(name: str, status: Status = Status.NOT_STARTED, effort: float = 0.0, progress: int | None = None) -> Task:
    return Task(name, id=name, status=status, effort_hours=effort, progress=progress)


def test_parent_map_points_children_at_their_summary() -> None:
    assert parent_map(project_with_summary()) == {"a": "まとめ", "b": "まとめ"}


def test_children_of_keeps_the_order_and_skips_missing_ids() -> None:
    project = Project("p", tasks=[summary("m", "b", "x", "a"), child("a"), child("b")])
    assert [c.name for c in children_of(project.tasks[0], project.task_map())] == ["b", "a"]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([Status.DONE, Status.DONE], Status.DONE),
        ([Status.NOT_STARTED, Status.NOT_STARTED], Status.NOT_STARTED),
        ([Status.DONE, Status.NOT_STARTED], Status.RUNNING),
        ([Status.PAUSED, Status.NOT_STARTED], Status.RUNNING),
        ([Status.RUNNING, Status.NOT_STARTED], Status.RUNNING),
        ([], Status.NOT_STARTED),
    ],
)
def test_summary_status(statuses: list[Status], expected: Status) -> None:
    assert summary_status([child(f"c{i}", s) for i, s in enumerate(statuses)]) == expected


def test_summary_progress_is_weighted_by_effort() -> None:
    kids = [child("a", effort=6.0, progress=50), child("b", effort=2.0, progress=100)]
    assert summary_progress(kids) == 63  # (6*50 + 2*100) / 8 = 62.5 → 63 (四捨五入)


def test_summary_progress_counts_done_as_100_and_unset_as_0_and_no_effort_as_weight_1() -> None:
    kids = [child("a", Status.DONE), child("b")]
    assert summary_progress(kids) == 50


def test_summary_progress_is_none_when_no_child_has_progress_or_is_done() -> None:
    assert summary_progress([child("a"), child("b")]) is None


def test_drop_child_removes_the_id_and_reverts_an_empty_summary() -> None:
    project = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b")])
    drop_child(project, "a")
    assert project.tasks[0].children == ["b"] and project.tasks[0].kind is TaskKind.SUMMARY
    drop_child(project, "b")
    assert project.tasks[0].children == [] and project.tasks[0].kind is TaskKind.NORMAL


def test_revert_empty_leaves_other_summaries() -> None:
    project = Project("p", tasks=[summary("m", "a"), summary("n"), child("a")])
    revert_empty(project)
    assert [t.kind for t in project.tasks] == [TaskKind.SUMMARY, TaskKind.NORMAL, TaskKind.NORMAL]


D = datetime


def timed(name: str, start: datetime | None, end: datetime | None, **fields: object) -> Task:
    return Task(name, id=name, planned_start=start, planned_end=end, **fields)  # type: ignore[arg-type]


def span_project() -> Project:
    return Project(
        "p",
        tasks=[
            summary("m", "a", "b"),
            timed("a", D(2026, 10, 6, 9), D(2026, 10, 7, 17)),
            timed("b", D(2026, 10, 8, 9), D(2026, 10, 12, 17)),
            Task("after", id="after", predecessors=["m"], planned_start=D(2026, 10, 1, 9),
                 planned_end=D(2026, 10, 2, 9)),
        ],
    )


def test_a_summary_spans_its_children() -> None:
    project = span_project()
    schedule = Schedule(project, {})
    assert (schedule.start(project.tasks[0]), schedule.end(project.tasks[0])) == (D(2026, 10, 6, 9), D(2026, 10, 12, 17))
    assert effective_start(project.tasks[0], project, {}) == D(2026, 10, 6, 9)
    assert effective_end(project.tasks[0], project, {}) == D(2026, 10, 12, 17)


def test_a_task_after_a_summary_is_pushed_to_the_latest_child_finish() -> None:
    project = span_project()
    assert Schedule(project, {}).start(project.tasks[3]) == D(2026, 10, 12, 17)


def test_a_summary_without_scheduled_children_has_no_span() -> None:
    project = Project("p", tasks=[summary("m", "a"), Task("a", id="a")])
    schedule = Schedule(project, {})
    assert (schedule.start(project.tasks[0]), schedule.end(project.tasks[0])) == (None, None)


def test_a_summary_uses_the_pushed_dates_of_its_children() -> None:
    project = Project(
        "p",
        tasks=[
            summary("m", "b"),
            timed("a", D(2026, 10, 6, 9), D(2026, 10, 9, 17)),
            timed("b", D(2026, 10, 6, 9), D(2026, 10, 7, 17), predecessors=["a"]),
        ],
    )
    assert Schedule(project, {}).start(project.tasks[0]) == D(2026, 10, 9, 17)  # b は a の完了まで押し出される


def test_a_summary_is_never_overdue_and_has_no_progress_state() -> None:
    project = span_project()
    now = D(2027, 1, 1)
    assert not is_overdue(project.tasks[0], project, {}, now)
    assert progress_state(project.tasks[0], project, {}, now) is None


def original() -> Task:
    return Task(
        "実装", id="orig", planned_start=D(2026, 10, 6, 9), effort_hours=10.0, deadline=D(2026, 10, 20, 17),
        assignees=[Assignee("田中", 0.5)], category_id="cat", predecessors=["pre"],
        urls=[TaskUrl("t", values={"URL": "https://example.com"})], color="#112233",
    )


def decomposable() -> Project:
    return Project(
        "p",
        categories=[Category("開発", id="cat")],
        sections=[Section("開発", [Task("pre", id="pre"), original(), Task("post", id="post", predecessors=["orig"])])],
    )


PARTS = [Part("設計", 4.0), Part("実装", 4.0), Part("確認", 2.0)]


def test_split_effort_is_even_with_the_remainder_on_the_last() -> None:
    assert split_effort(10.0, 3) == [3.33, 3.33, 3.34]
    assert split_effort(0.0, 2) == [0.0, 0.0]
    assert sum(split_effort(7.0, 4)) == pytest.approx(7.0)


def test_default_parts_are_numbered_and_fit_the_name_limit() -> None:
    parts = default_parts(Task("x" * 50, effort_hours=4.0), 2)
    assert [len(p.name) for p in parts] == [50, 50]
    assert [p.effort_hours for p in parts] == [2.0, 2.0]


def test_decompose_makes_a_summary_and_children_after_it() -> None:
    project = decomposable()
    kids = decompose(project, (0,), 1, PARTS)
    tasks = project.sections[0].tasks
    assert [t.name for t in tasks] == ["pre", "実装", "設計", "実装", "確認", "post"]
    summary_task = tasks[1]
    assert (summary_task.kind, summary_task.children) == (TaskKind.SUMMARY, [k.id for k in kids])
    assert (summary_task.id, summary_task.effort_hours, summary_task.assignees, summary_task.predecessors) == ("orig", 0.0, [], [])
    assert summary_task.deadline is None and summary_task.planned_start is None


def test_children_inherit_the_attributes_and_split_the_effort() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS)
    assert [k.effort_hours for k in kids] == [4.0, 4.0, 2.0]
    for kid in kids:
        assert (kid.kind, kid.status, kid.category_id, kid.color) == (TaskKind.NORMAL, Status.NOT_STARTED, "cat", "#112233")
        assert [(a.name, a.allocation) for a in kid.assignees] == [("田中", 0.5)]
        assert kid.urls == original().urls and kid.urls is not original().urls
        assert kid.planned_start == D(2026, 10, 6, 9)
        assert kid.actuals == [] and kid.progress is None


def test_chain_links_the_children_in_order_and_the_first_takes_the_original_predecessors() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS, chain=True)
    assert [k.predecessors for k in kids] == [["pre"], [kids[0].id], [kids[1].id]]


def test_without_chain_every_child_takes_the_original_predecessors() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS, chain=False)
    assert [k.predecessors for k in kids] == [["pre"], ["pre"], ["pre"]]


def test_the_deadline_goes_to_the_last_child_only() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS)
    assert [k.deadline for k in kids] == [None, None, D(2026, 10, 20, 17)]


def test_successors_still_point_at_the_summary() -> None:
    project = decomposable()
    decompose(project, (0,), 1, PARTS)
    assert project.sections[0].tasks[-1].predecessors == ["orig"]


def test_new_section_puts_the_children_in_a_subsection_named_after_the_task() -> None:
    project = decomposable()
    kids = decompose(project, (0,), 1, PARTS, new_section=True)
    section = project.sections[0]
    assert [t.name for t in section.tasks] == ["pre", "実装", "post"]
    assert [(s.name, [t.id for t in s.tasks]) for s in section.sections] == [("実装", [k.id for k in kids])]


def test_new_section_gets_a_unique_name() -> None:
    project = decomposable()
    project.sections[0].sections.append(Section("実装"))
    decompose(project, (0,), 1, PARTS, new_section=True)
    assert [s.name for s in project.sections[0].sections] == ["実装", "実装#2"]


def test_can_make_section_explains_why_not() -> None:
    assert can_make_section((0,)) is None
    assert "セクション" in (can_make_section(()) or "")
    assert "3 階層" in (can_make_section((0, 0, 0)) or "")


@pytest.mark.parametrize("path", [(), (0, 0, 0)])
def test_new_section_is_refused_at_root_and_at_the_third_level(path: tuple[int, ...]) -> None:
    project = Project("p", tasks=[original()])
    if path:
        project = Project("p", sections=[Section("a", sections=[Section("b", sections=[Section("c", [original()])])])])
    before = repr(project)
    with pytest.raises(ValueError):
        decompose(project, path, 0, PARTS, new_section=True)
    assert repr(project) == before


@pytest.mark.parametrize(
    "parts",
    [
        [Part("a", 1.0)],  # 1 件
        [Part("a", 1.0), Part("", 1.0)],  # 名前が空
        [Part("a", 1.0), Part("b" * 51, 1.0)],  # 長い
        [Part("a", 1.0), Part("b\nc", 1.0)],  # 制御文字
        [Part("a", 1.0), Part("b", -1.0)],  # 負の工数
        [Part("a", 1.0), Part("b", float("nan"))],
        [Part("a", 1.0), Part("b", 1.234)],  # 小数点以下 3 桁
        [Part(str(n), 1.0) for n in range(MAX_PARTS + 1)],  # 多すぎる
    ],
)
def test_bad_parts_are_refused_without_changing_the_project(parts: list[Part]) -> None:
    project = decomposable()
    before = repr(project)
    with pytest.raises(ValueError):
        decompose(project, (0,), 1, parts)
    assert repr(project) == before


def test_a_task_with_actuals_cannot_be_decomposed() -> None:
    project = decomposable()
    project.sections[0].tasks[1].actuals = [Actual(D(2026, 10, 6, 9), D(2026, 10, 6, 12))]
    with pytest.raises(ValueError, match="実績"):
        decompose(project, (0,), 1, PARTS)


@pytest.mark.parametrize("kind", [TaskKind.CHECKPOINT, TaskKind.SUMMARY])
def test_only_normal_tasks_can_be_decomposed(kind: TaskKind) -> None:
    project = decomposable()
    project.sections[0].tasks[1].kind = kind
    with pytest.raises(ValueError):
        decompose(project, (0,), 1, PARTS)


def test_the_result_passes_the_load_validation() -> None:
    project = decomposable()
    decompose(project, (0,), 1, PARTS, new_section=True)
    parse_project(dumps_project(project), "p")


def test_drop_task_links_removes_a_deleted_child_from_its_summary() -> None:
    project = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b")])
    drop_task_links(project, "a")
    assert project.tasks[0].children == ["b"]
    drop_task_links(project, "b")
    assert project.tasks[0].kind is TaskKind.NORMAL


def test_deleting_a_summary_leaves_the_children_as_plain_tasks() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a")])
    removed = project.tasks.pop(0)
    drop_task_links(project, removed.id)
    assert [(t.name, t.kind) for t in project.tasks] == [("a", TaskKind.NORMAL)]


def test_a_child_cannot_pick_its_own_summary_as_a_predecessor() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a"), child("other")])
    assert set(link_options(project, project.tasks[1])) == {"other"}


def test_a_summary_cannot_pick_its_own_child() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a"), child("other")])
    assert set(link_options(project, project.tasks[0])) == {"other"}


def test_copying_a_summary_gives_a_plain_task_without_children() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a")])
    copy = arrange.copy_task(project, ((), 0), ((), 2))
    assert (copy.kind, copy.children) == (TaskKind.NORMAL, [])
    assert project.tasks[0].children == ["a"]


def slot_project() -> Project:
    return Project(
        "p",
        sections=[Section("s", [summary("m", "a", "b"), child("a"), child("b"), child("other")])],
    )


def test_a_summary_matches_when_a_child_matches() -> None:
    project = slot_project()
    flt = TaskFilter(query="a")
    assert not matches(project.sections[0].tasks[0], flt)
    assert matches(project.sections[0].tasks[0], flt, project.task_map())


def test_a_summary_matches_by_its_own_name() -> None:
    project = slot_project()
    assert matches(project.sections[0].tasks[0], TaskFilter(query="m"))


def test_visible_task_indexes_include_the_summary_of_a_matching_child() -> None:
    project = slot_project()
    section = project.sections[0]
    flt = TaskFilter(query="b")
    assert visible_task_indexes(section, flt, False, project.task_map()) == [0, 2]  # m(子 b が合う)と b


def test_section_has_match_sees_a_summary_through_its_children() -> None:
    project = Project("p", sections=[Section("s", [summary("m", "a")]), Section("t", [child("a")])])
    flt = TaskFilter(query="a")
    assert section_has_match(project.sections[0], flt, project.task_map())


def test_hidden_by_summary() -> None:
    assert hidden_by_summary(slot_project(), {"m"}) == {"a", "b"}
    assert hidden_by_summary(slot_project(), set()) == set()


def shown(slots: list[RowSlot]) -> list[str | None]:
    return [s.task_id for s in slots if s.kind == "task" and s.shown]


def test_collapsed_summary_hides_its_children_rows() -> None:
    slots = row_slots(slot_project(), TaskFilter(), set(), False, 32, 24, {"m"})
    assert shown(slots) == ["m", "other"]


def test_rows_are_kept_but_not_shown_so_the_layout_keeps_the_indexes() -> None:
    slots = row_slots(slot_project(), TaskFilter(), set(), False, 32, 24, {"m"})
    assert [s.task_id for s in slots if s.kind == "task"] == ["m", "a", "b", "other"]


def test_the_summary_collapse_is_ignored_while_filtering_and_in_read_only() -> None:
    project = slot_project()
    assert shown(row_slots(project, TaskFilter(query="a"), set(), False, 32, 24, {"m"})) == ["m", "a"]
    assert shown(row_slots(project, TaskFilter(), set(), True, 32, 24, {"m"})) == ["m", "a", "b", "other"]


def test_a_collapsed_section_still_hides_everything() -> None:
    slots = row_slots(slot_project(), TaskFilter(), {(0,)}, False, 32, 24, set())
    assert shown(slots) == []


def dashboard_project(with_summary: bool) -> Project:
    a = timed("a", D(2026, 10, 6, 9), D(2026, 10, 7, 17), effort_hours=4.0, assignees=[Assignee("田中", 1.0)])
    b = timed("b", D(2026, 10, 8, 9), D(2026, 10, 9, 17), effort_hours=2.0, assignees=[Assignee("田中", 1.0)],
              deadline=D(2026, 10, 9, 17))
    tasks = [a, b]
    if with_summary:
        tasks.insert(0, summary("m", "a", "b"))
    return Project("p", base_date=date(2026, 10, 5), members=[Member("田中")], tasks=tasks)


NOW = D(2026, 10, 12, 12)
PERIOD = Period(date(2026, 10, 5), date(2026, 10, 11))


def test_the_dashboard_progress_ignores_the_summary() -> None:
    plain = summarize_progress(dashboard_project(False), {}, NOW)
    with_summary = summarize_progress(dashboard_project(True), {}, NOW)
    assert (with_summary.counts, with_summary.percent, with_summary.overdue) == (plain.counts, plain.percent, plain.overdue)
    assert len(with_summary.overdue) == 2  # 比較が空同士にならないよう、超過が出ていることを確かめる


def test_the_dashboard_workload_loads_and_due_ignore_the_summary() -> None:
    plain, withs = dashboard_project(False), dashboard_project(True)
    assert summarize_workload(withs, PERIOD, NOW, {}) == summarize_workload(plain, PERIOD, NOW, {})
    assert summarize_loads(withs, PERIOD, {}) == summarize_loads(plain, PERIOD, {})
    assert summarize_due(withs, PERIOD, NOW, {}) == summarize_due(plain, PERIOD, NOW, {})
    assert summarize_due(plain, PERIOD, NOW, {})  # 空同士の比較にならない


def puml(project: Project):
    return build_plantuml(project, {}, (date(2026, 10, 5), date(2026, 10, 18)), Scale.DAY, TaskFilter(), NOW)


def test_plantuml_does_not_draw_the_summary_and_does_not_count_it_as_skipped() -> None:
    result = puml(dashboard_project(True))
    assert "[m]" not in result.text
    assert (result.task_count, result.skipped) == (2, 0)


def test_plantuml_draws_the_arrow_from_the_latest_child_for_a_successor_of_the_summary() -> None:
    project = dashboard_project(True)
    project.tasks.append(timed("after", D(2026, 10, 13, 9), D(2026, 10, 14, 9), predecessors=["m"]))
    text = puml(project).text
    # a=T1, b=T2, after=T3。b の完了が最も遅い
    assert "[T2] -> [T3]" in text and "[T1] -> [T3]" not in text


def test_plantuml_draws_no_arrow_for_a_summary_without_drawn_children() -> None:
    project = Project(
        "p",
        tasks=[summary("m", "a"), Task("a", id="a"), timed("z", D(2026, 10, 6, 9), D(2026, 10, 7, 9), predecessors=["m"])],
    )
    assert "->" not in puml(project).text


def test_merge_takes_the_one_sided_change_of_the_children() -> None:
    base = Project("p", tasks=[summary("m", "a"), child("a"), child("b")])
    ours = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b")])
    result = merge_projects(base, ours, base)
    assert result.project.tasks[0].children == ["a", "b"] and not result.conflicts


def test_merge_conflicts_when_both_sides_change_the_children() -> None:
    base = Project("p", tasks=[summary("m", "a"), child("a"), child("b"), child("c")])
    ours = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b"), child("c")])
    theirs = Project("p", tasks=[summary("m", "a", "c"), child("a"), child("b"), child("c")])
    assert [c.field for c in merge_projects(base, ours, theirs).conflicts] == ["子"]


def test_merge_drops_deleted_children_and_reverts_an_empty_summary() -> None:
    base = Project("p", tasks=[summary("m", "a"), child("a")])
    theirs = Project("p", tasks=[summary("m", "a")])  # a を削除(m の children は触っていない)
    result = merge_projects(base, base, theirs)
    assert result.project.tasks[0].kind is TaskKind.NORMAL and result.project.tasks[0].children == []
