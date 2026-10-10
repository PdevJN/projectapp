"""モデルの小さな規則(セクションの入れ子)。"""

import pytest

import projectapp.models as models
from projectapp.models import Member, Project, Section, Task, new_id, walk_sections


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


def test_new_id_is_8_hex_digits() -> None:
    value = new_id()
    assert len(value) == 8 and int(value, 16) >= 0


def test_new_id_does_not_return_a_taken_id(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter(["aaaaaaaa", "aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr(models.secrets, "token_hex", lambda nbytes: next(values))
    assert new_id({"aaaaaaaa"}) == "bbbbbbbb"


def test_member_and_section_get_ids_that_do_not_affect_equality() -> None:
    assert len(Member("田中").id) == 8 and len(Section("s").id) == 8
    assert Member("田中", 1.2) == Member("田中", 1.2)
    assert Section("s", [Task("a")]) == Section("s", [Task("a")])
    assert Member("田中").id != Member("田中").id


def test_used_ids_collects_tasks_members_and_nested_sections() -> None:
    project = tree()
    project.members = [Member("田中"), Member("鈴木")]
    expected = (
        {t.id for t in project.all_tasks()}
        | {m.id for m in project.members}
        | {s.id for _, s in walk_sections(project.sections)}
    )
    assert project.used_ids() == expected
    assert len(expected) == 6 + 2 + 5
