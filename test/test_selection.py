from projectapp.models import Project, Section, Task, TaskKind
from projectapp.selection import CheckState, check_state, set_checked, task_ids_of


def leaf(name: str) -> Task:
    return Task(name)


def test_task_ids_of_a_normal_task_is_itself() -> None:
    t = leaf("a")
    assert task_ids_of(t, {t.id: t}) == [t.id]


def test_task_ids_of_a_summary_are_its_children_only() -> None:
    c1, c2 = leaf("c1"), leaf("c2")
    s = Task("s", kind=TaskKind.SUMMARY, children=[c1.id, c2.id])
    by_id = {t.id: t for t in (c1, c2, s)}
    assert task_ids_of(s, by_id) == [c1.id, c2.id]


def test_task_ids_of_a_section_skip_summaries_themselves() -> None:
    c = leaf("c")
    s = Task("s", kind=TaskKind.SUMMARY, children=[c.id])
    sub = Section("sub", tasks=[leaf("x")])
    sec = Section("sec", tasks=[s, c], sections=[sub])
    project = Project("p", sections=[sec])
    ids = task_ids_of(sec, project.task_map())
    assert ids == [c.id, sub.tasks[0].id]


def test_check_state_is_on_off_mixed_or_none() -> None:
    assert check_state(["a", "b"], frozenset()) is CheckState.ON
    assert check_state(["a", "b"], frozenset({"a", "b"})) is CheckState.OFF
    assert check_state(["a", "b"], frozenset({"a"})) is CheckState.MIXED
    assert check_state([], frozenset()) is None


def test_set_checked_adds_or_removes_only_the_given_ids() -> None:
    assert set_checked(frozenset({"z"}), ["a", "b"], False) == frozenset({"z", "a", "b"})
    assert set_checked(frozenset({"z", "a"}), ["a"], True) == frozenset({"z"})


def test_clicking_a_mixed_state_checks_everything() -> None:
    from projectapp.selection import toggled

    assert toggled(CheckState.MIXED) is True
    assert toggled(CheckState.ON) is False
    assert toggled(CheckState.OFF) is True
