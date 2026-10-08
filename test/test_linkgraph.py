import pytest

from projectapp.linkgraph import downstream_ids, drop_task_links, link_options, validate_links
from projectapp.models import Project, Section, Task


def task(name: str, task_id: str, *predecessors: str) -> Task:
    return Task(name, id=task_id, predecessors=list(predecessors))


def test_downstream_ids_follow_direct_and_indirect_successors() -> None:
    a, b, c, d = task("a", "a"), task("b", "b", "a"), task("c", "c", "b"), task("d", "d")
    project = Project("p", tasks=[a, b, c, d])
    assert downstream_ids(project, "a") == {"b", "c"}
    assert downstream_ids(project, "c") == set()


def test_downstream_ids_terminate_on_a_cycle() -> None:
    a, b = task("a", "a", "b"), task("b", "b", "a")
    assert downstream_ids(Project("p", tasks=[a, b]), "a") == {"b", "a"}


def test_drop_task_links_removes_the_id_from_every_task() -> None:
    a, b = task("a", "a"), task("b", "b", "a", "x")
    project = Project("p", tasks=[a], sections=[Section("s", [b])])
    drop_task_links(project, "a")
    assert b.predecessors == ["x"]


def test_validate_links_accepts_a_valid_graph() -> None:
    validate_links([task("a", "a"), task("b", "b", "a")])


@pytest.mark.parametrize(
    "tasks",
    [
        [task("a", "a"), task("b", "a")],  # id の重複
        [task("a", "a", "zz")],  # 存在しない id
        [task("a", "a", "a")],  # 自分自身
        [task("a", "a", "b"), task("b", "b", "a")],  # 循環
        [task("a", "a"), task("b", "b", "a", "a")],  # 同じ先行の重複
    ],
)
def test_validate_links_rejects_bad_graphs(tasks: list[Task]) -> None:
    with pytest.raises(ValueError):
        validate_links(tasks)


def test_link_options_label_with_section_and_exclude_self_and_successors() -> None:
    a = task("設計", "a")
    b = task("実装", "b", "a")
    c = task("設計", "c")
    project = Project("p", tasks=[a], sections=[Section("開発", [b, c])])
    options = link_options(project, a)
    assert "a" not in options and "b" not in options  # 自分と、自分を先行にしている後続は除く
    assert options == {"c": "開発 / 設計"}
    everything = link_options(project, None)
    assert everything == {"a": "設計", "b": "開発 / 実装", "c": "開発 / 設計"}


def test_link_options_number_duplicate_labels() -> None:
    a, b = task("設計", "a"), task("設計", "b")
    options = link_options(Project("p", tasks=[a, b]), None)
    assert options == {"a": "設計", "b": "設計 (2)"}


def test_link_options_label_nested_tasks_with_every_section_name() -> None:
    deep = Section("孫", [Task("深い", id="g")])
    project = Project(
        "p",
        tasks=[Task("根", id="r")],
        sections=[Section("親", [Task("上", id="u")], [Section("子", [Task("中", id="m")], [deep])])],
    )
    options = link_options(project, None)
    assert options == {"r": "根", "u": "親 / 上", "m": "親 / 子 / 中", "g": "親 / 子 / 孫 / 深い"}
