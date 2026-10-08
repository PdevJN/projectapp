"""モデルの小さな規則(セクションの入れ子)。"""

from projectapp.models import Project, Section, Task, walk_sections


def tree() -> Project:
    deep = Section("孫", [Task("g")])
    child = Section("子", [Task("c")], [deep])
    return Project(
        "p",
        tasks=[Task("r")],
        sections=[Section("親", [Task("p1")], [child, Section("子2", [Task("c2")])]), Section("別", [Task("o")])],
    )


def test_all_tasks_runs_depth_first_after_the_root_tasks() -> None:
    assert [t.name for t in tree().all_tasks()] == ["r", "p1", "c", "g", "c2", "o"]


def test_a_section_lists_its_own_and_its_descendants_tasks() -> None:
    parent = tree().sections[0]
    assert [t.name for t in parent.all_tasks()] == ["p1", "c", "g", "c2"]
    assert [t.name for t in parent.sections[0].all_tasks()] == ["c", "g"]


def test_walk_sections_yields_paths_depth_first() -> None:
    paths = [(path, section.name) for path, section in walk_sections(tree().sections)]
    assert paths == [((0,), "親"), ((0, 0), "子"), ((0, 0, 0), "孫"), ((0, 1), "子2"), ((1,), "別")]


def test_a_flat_project_is_unchanged() -> None:
    project = Project("p", tasks=[Task("r")], sections=[Section("A", [Task("a")])])
    assert [t.name for t in project.all_tasks()] == ["r", "a"]
