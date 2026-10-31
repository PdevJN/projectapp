from datetime import date

import pytest

from projectapp.extract import check, expand_ids, extract, name_error, selection_error
from projectapp.models import (
    Assignee,
    Category,
    Event,
    Level,
    Member,
    Membership,
    Parameter,
    Project,
    Section,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
    ActualMode,
)


def make() -> Project:
    return Project(
        "親",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        members=[Member("田中", id="m1"), Member("鈴木", id="m2"), Member("佐藤", id="m3")],
        tasks=[Task("root", id="r")],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a", effort_hours=8, assignees=[Assignee("田中", 1.0)]),
                    Task("b", id="b", effort_hours=4, predecessors=["a"], assignees=[Assignee("鈴木", 1.0)]),
                    Task("c", id="c", predecessors=["b"]),
                ],
                id="s1",
            )
        ],
    )


def summary_project() -> Project:
    """まとめ S1(子 k1・k2)と、まとめ S2(子 k3)。"""
    return Project(
        "親",
        sections=[
            Section(
                "開発",
                [
                    Task("S1", id="S1", kind=TaskKind.SUMMARY, children=["k1", "k2"]),
                    Task("k1", id="k1"),
                    Task("k2", id="k2"),
                    Task("S2", id="S2", kind=TaskKind.SUMMARY, children=["k3"]),
                    Task("k3", id="k3"),
                ],
                id="s1",
            )
        ],
    )


def ids_of(tasks: list[Task]) -> list[str]:
    return [t.id for t in tasks]


def test_selected_tasks_move_with_ids_and_sections_and_leave_a_reference() -> None:
    project = make()
    result = extract(project, ["a", "b"], "子")
    child, parent = result.child, result.parent
    assert child.name == "子" and child.tasks == []
    assert [s.name for s in child.sections] == ["開発"] and child.sections[0].id == "s1"
    assert ids_of(child.sections[0].tasks) == ["a", "b"]
    kept = parent.sections[0].tasks
    assert [t.kind for t in kept] == [TaskKind.REFERENCE, TaskKind.NORMAL]
    assert kept[0].id == result.reference_id and kept[0].name == "子" and kept[0].ref_project == "子"
    assert kept[0].ref_snapshot is None
    assert result.moved == 2
    assert ids_of(parent.tasks) == ["r"]
    assert ids_of(project.sections[0].tasks) == ["a", "b", "c"]  # 元の project は変えない


def test_root_tasks_stay_at_the_root_of_the_child() -> None:
    result = extract(make(), ["r"], "子")
    assert ids_of(result.child.tasks) == ["r"] and result.child.sections == []
    assert result.parent.tasks[0].kind is TaskKind.REFERENCE


def test_predecessors_across_the_boundary() -> None:
    result = extract(make(), ["b"], "子")
    assert result.child.sections[0].tasks[0].predecessors == []  # b は外の a を先行にしていた
    assert result.dropped == 1
    c = result.parent.sections[0].tasks[-1]
    assert c.id == "c" and c.predecessors == [result.reference_id]  # c は b を先行にしていた
    assert "a" in ids_of(result.parent.sections[0].tasks)


def test_predecessors_inside_the_selection_are_kept() -> None:
    result = extract(make(), ["a", "b"], "子")
    assert result.child.sections[0].tasks[1].predecessors == ["a"] and result.dropped == 0


def test_the_reference_goes_where_the_first_selected_task_was() -> None:
    result = extract(make(), ["b", "c"], "子")
    assert [t.kind for t in result.parent.sections[0].tasks] == [TaskKind.NORMAL, TaskKind.REFERENCE]


def test_only_the_members_in_the_selected_tasks_are_carried() -> None:
    project = make()
    project.members[0].teams = [Membership("t1", 100)]
    result = extract(project, ["a", "b"], "子")
    assert [m.name for m in result.child.members] == ["田中", "鈴木"]
    assert all(m.teams == [] for m in result.child.members)
    assert result.child.teams == []
    assert [m.name for m in result.parent.members] == ["田中", "鈴木", "佐藤"]  # 親の名簿は変えない


def test_the_warning_limit_goes_with_the_members_who_move() -> None:
    project = make()
    project.members[0].warning_limit = 3
    result = extract(project, ["a", "b"], "子")
    assert next(m for m in result.child.members if m.name == "田中").warning_limit == 3


def test_members_in_weekly_crew_are_carried() -> None:
    project = make()
    task = project.sections[0].tasks[0]
    task.weekly_crew = [[Assignee("田中", 1.0)], [Assignee("佐藤", 0.5)]]
    task.assignees = [Assignee("田中", 1.0), Assignee("佐藤", 0.5)]
    result = extract(project, ["a"], "子")
    assert [m.name for m in result.child.members] == ["田中", "佐藤"]


def test_only_used_parameters_are_carried_when_every_task_picks_its_own() -> None:
    project = make()
    project.parameters = [Parameter("経験", [Level("高", 0.2)]), Parameter("慣れ", [Level("低", -0.1)])]
    project.members[0].levels = {"経験": "高", "慣れ": "低"}
    for task in project.sections[0].tasks[:2]:
        task.parameters = ["経験"]
    result = extract(project, ["a", "b"], "子")
    assert [p.name for p in result.child.parameters] == ["経験"]
    assert result.child.members[0].levels == {"経験": "高"}


def test_all_parameters_are_carried_when_a_task_uses_them_all() -> None:
    project = make()
    project.parameters = [Parameter("経験", [Level("高", 0.2)]), Parameter("慣れ", [Level("低", -0.1)])]
    project.sections[0].tasks[0].parameters = ["経験"]  # b は parameters が空 = 全パラメータの合計
    result = extract(project, ["a", "b"], "子")
    assert [p.name for p in result.child.parameters] == ["経験", "慣れ"]


def test_only_used_categories_and_url_templates_are_carried() -> None:
    project = make()
    project.categories = [Category("開発", id="c1"), Category("運用", id="c2")]
    project.url_templates = [UrlTemplate("チケット", "https://e/{ID}"), UrlTemplate("文書", "https://d/{ID}")]
    task = project.sections[0].tasks[0]
    task.category_id = "c1"
    task.urls = [TaskUrl(template="チケット", values={"ID": "1"})]
    result = extract(project, ["a"], "子")
    assert [c.id for c in result.child.categories] == ["c1"]
    assert [u.name for u in result.child.url_templates] == ["チケット"]


def test_settings_and_events_are_carried_but_not_teams() -> None:
    project = make()
    project.actual_mode = ActualMode.INTERVALS
    project.ratio_limit_upper = 1.2
    project.events = [Event(date(2026, 10, 7), date(2026, 10, 8), "休み", id="e1")]
    child = extract(project, ["a"], "子").child
    assert (child.base_date, child.daily_hours, child.work_start) == (project.base_date, 7.0, project.work_start)
    assert child.actual_mode is ActualMode.INTERVALS and child.ratio_limit_upper == 1.2
    assert [e.id for e in child.events] == ["e1"]


def test_selecting_a_summary_moves_its_children_too() -> None:
    result = extract(summary_project(), ["S1"], "子")
    assert ids_of(result.child.sections[0].tasks) == ["S1", "k1", "k2"]
    assert result.child.sections[0].tasks[0].kind is TaskKind.SUMMARY
    assert ids_of(result.parent.sections[0].tasks) == [result.reference_id, "S2", "k3"]
    assert result.moved == 3


def test_a_child_alone_becomes_a_reference_inside_its_summary() -> None:
    result = extract(summary_project(), ["k1"], "子")
    tasks = result.parent.sections[0].tasks
    assert ids_of(tasks) == ["S1", result.reference_id, "k2", "S2", "k3"]
    assert tasks[0].children == [result.reference_id, "k2"]
    assert tasks[1].kind is TaskKind.REFERENCE
    assert ids_of(result.child.sections[0].tasks) == ["k1"]
    assert result.child.sections[0].tasks[0].kind is TaskKind.NORMAL  # まとめは持ち越さない


def test_summary_left_without_children_becomes_normal() -> None:
    result = extract(summary_project(), ["k1", "k3"], "子")  # 参照行は S1 の中。S2 は子を全部失う
    by_id = {t.id: t for t in result.parent.all_tasks()}
    assert by_id["S2"].kind is TaskKind.NORMAL and by_id["S2"].children == []
    assert by_id["S1"].kind is TaskKind.SUMMARY and by_id["S1"].children == [result.reference_id, "k2"]


def test_expand_ids_adds_summary_children_in_display_order() -> None:
    assert expand_ids(summary_project(), ["S2", "k1"]) == ["k1", "S2", "k3"]
    assert expand_ids(summary_project(), ["missing"]) == []


def test_selection_errors() -> None:
    assert selection_error(make(), []) == "切り出すタスクがありません"
    project = make()
    project.tasks.append(Task("参照", id="ref", kind=TaskKind.REFERENCE, ref_project="x"))
    assert selection_error(project, ["a", "ref"]) == "プロジェクト参照の行は切り出せません"
    assert selection_error(project, ["a"]) is None
    with pytest.raises(ValueError):
        extract(project, ["ref"], "子")


def test_name_errors() -> None:
    project = make()
    assert name_error(project, "  ", []) == "名前を入力してください"
    assert "50文字以内" in (name_error(project, "あ" * 51, []) or "")
    assert name_error(project, "あ" * 50, []) is None
    assert name_error(project, "a\nb", []) == "名前に改行・制御文字は使えません"
    assert name_error(project, "親", []) == "今のプロジェクトと同じ名前にはできません"
    assert name_error(project, "子", ["子"]) == "同じ名前のプロジェクトがすでにあります"
    assert name_error(project, "子", ["孫"]) is None


def test_both_results_pass_the_load_validation() -> None:
    for ids in (["a", "b"], ["r"], ["b"]):
        check(extract(make(), ids, "子"))
    check(extract(summary_project(), ["k1"], "子"))
    check(extract(summary_project(), ["S1"], "子"))
