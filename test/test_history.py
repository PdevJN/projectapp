"""元に戻す・やり直しの履歴(NiceGUI に依存しない)。"""

from projectapp.history import HISTORY_LIMIT, History
from projectapp.models import Project, Task


def project_with(*names: str) -> Project:
    return Project("p", tasks=[Task(name) for name in names])


def test_an_empty_history_has_nothing_to_undo_or_redo():
    history = History()
    assert not history.can_undo()
    assert not history.can_redo()
    assert history.undo(project_with("a")) is None
    assert history.redo(project_with("a")) is None


def test_undo_returns_the_recorded_state_and_redo_returns_the_one_left():
    history = History()
    before, after = project_with("a"), project_with("a", "b")
    history.record(before)
    restored = history.undo(after)
    assert restored == before
    assert history.can_redo()
    assert history.redo(restored) == after
    assert history.can_undo()


def test_recording_a_new_edit_drops_the_redo_side():
    history = History()
    history.record(project_with())
    history.undo(project_with("a"))
    assert history.can_redo()
    history.record(project_with())
    assert not history.can_redo()


def test_recording_the_same_state_twice_in_a_row_adds_one_step():
    history = History()
    history.record(project_with("a"))
    history.record(project_with("a"))
    assert history.undo(project_with("a", "b")) == project_with("a")
    assert not history.can_undo()


def test_the_history_keeps_copies_so_later_edits_do_not_change_it():
    history = History()
    live = project_with("a")
    history.record(live)
    live.tasks[0].name = "changed"
    restored = history.undo(project_with("x"))
    assert restored is not None
    assert restored.tasks[0].name == "a"


def test_the_state_given_to_undo_is_copied_for_redo():
    history = History()
    history.record(project_with())
    live = project_with("a")
    history.undo(live)
    live.tasks[0].name = "changed"
    redone = history.redo(project_with())
    assert redone is not None
    assert redone.tasks[0].name == "a"


def test_the_oldest_step_is_dropped_past_the_limit():
    history = History()
    for i in range(HISTORY_LIMIT + 1):
        history.record(project_with(str(i)))
    current = project_with("now")
    seen = []
    while (restored := history.undo(current)) is not None:
        seen.append(restored.tasks[0].name)
        current = restored
    assert len(seen) == HISTORY_LIMIT
    assert seen[0] == str(HISTORY_LIMIT)
    assert seen[-1] == "1"  # "0" は上限を超えて失われた


def test_clear_empties_both_sides():
    history = History()
    history.record(project_with())
    history.undo(project_with("a"))
    history.clear()
    assert not history.can_undo()
    assert not history.can_redo()
