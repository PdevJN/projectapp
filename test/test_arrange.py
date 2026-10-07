from dataclasses import replace
from datetime import date, datetime

from projectapp import arrange
from projectapp.models import Actual, Priority, Project, Section, Status, Task


def names(tasks: list[Task]) -> list[str]:
    return [t.name for t in tasks]


def sample() -> Project:
    return Project(
        "p",
        tasks=[Task("t0"), Task("t1")],
        sections=[
            Section("A", [Task("a0"), Task("a1"), Task("a2")]),
            Section("B", []),
        ],
    )


def test_has_task_and_has_list() -> None:
    project = sample()
    assert arrange.has_task(project, (0, 2))
    assert arrange.has_task(project, (None, 1))
    assert not arrange.has_task(project, (0, 3))
    assert not arrange.has_task(project, (0, -1))
    assert not arrange.has_task(project, (2, 0))
    assert not arrange.has_task(project, (-1, 0))
    assert arrange.has_list(project, (1, 0))
    assert arrange.has_list(project, (None, 99))  # 番号は末尾に丸めるので大きくてよい
    assert not arrange.has_list(project, (0, -1))
    assert not arrange.has_list(project, (2, 0))
    assert not arrange.has_list(project, (-1, 0))


def test_move_forward_within_a_section_adjusts_the_index() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 0), (0, 3))  # 末尾へ
    assert names(project.sections[0].tasks) == ["a1", "a2", "a0"]
    project = sample()
    assert arrange.move_task(project, (0, 0), (0, 2))  # a1 の後ろ
    assert names(project.sections[0].tasks) == ["a1", "a0", "a2"]


def test_move_backward_within_a_section() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 2), (0, 0))
    assert names(project.sections[0].tasks) == ["a2", "a0", "a1"]


def test_move_to_the_same_place_or_right_next_to_it_changes_nothing() -> None:
    project = sample()
    assert not arrange.move_task(project, (0, 1), (0, 1))
    assert not arrange.move_task(project, (0, 1), (0, 2))
    assert names(project.sections[0].tasks) == ["a0", "a1", "a2"]


def test_move_across_sections_and_to_an_empty_section() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 1), (1, 0))
    assert names(project.sections[0].tasks) == ["a0", "a2"]
    assert names(project.sections[1].tasks) == ["a1"]


def test_move_between_the_top_list_and_sections() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 0), (None, 1))
    assert names(project.tasks) == ["t0", "a0", "t1"]
    assert arrange.move_task(project, (None, 0), (0, 1))
    assert names(project.tasks) == ["a0", "t1"]
    assert names(project.sections[0].tasks) == ["a1", "t0", "a2"]


def test_move_within_the_top_list() -> None:
    project = sample()
    assert arrange.move_task(project, (None, 0), (None, 2))
    assert names(project.tasks) == ["t1", "t0"]


def test_move_clamps_an_out_of_range_insert_index_to_the_end() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 0), (1, 99))
    assert names(project.sections[1].tasks) == ["a0"]


def test_copy_adds_a_suffix_clears_predecessors_and_keeps_the_rest() -> None:
    project = sample()
    original = project.sections[0].tasks[1]
    original.predecessors.append("a0")
    original.planned_start = datetime(2026, 10, 5, 9)
    original.effort_hours = 12.0
    original.priority = Priority.HIGH
    original.status = Status.PAUSED
    original.assignee = "田中"
    original.allocation = 0.5
    original.color = "#ff0000"
    copy = arrange.copy_task(project, (0, 1), (1, 0))
    assert project.sections[1].tasks == [copy]
    assert copy is not original
    assert copy.name == "a1(コピー)"
    assert copy.predecessors == []
    assert original.predecessors == ["a0"]
    assert original.name == "a1"
    assert replace(copy, name="a1", predecessors=["a0"]) == original
    assert names(project.sections[0].tasks) == ["a0", "a1", "a2"]


def test_copy_keeps_the_project_code() -> None:
    project = Project("p", tasks=[Task("t", project_code="PRJ-1")])
    copy = arrange.copy_task(project, (None, 0), (None, 1))
    assert copy.project_code == "PRJ-1"


def test_copy_inserts_at_the_position_and_clamps() -> None:
    project = sample()
    arrange.copy_task(project, (None, 0), (None, 1))
    assert names(project.tasks) == ["t0", "t0(コピー)", "t1"]
    arrange.copy_task(project, (None, 0), (0, 99))
    assert names(project.sections[0].tasks)[-1] == "t0(コピー)"


def test_shift_moves_start_and_end_and_keeps_deadline_and_time() -> None:
    task = Task(
        "x",
        planned_start=datetime(2026, 10, 5, 9, 30),
        planned_end=datetime(2026, 10, 7, 17, 45),
        deadline=datetime(2026, 10, 9, 12),
    )
    assert arrange.shift_task(task, 3)
    assert task.planned_start == datetime(2026, 10, 8, 9, 30)
    assert task.planned_end == datetime(2026, 10, 10, 17, 45)
    assert task.deadline == datetime(2026, 10, 9, 12)


def test_shift_backward_and_without_an_end() -> None:
    task = Task("x", planned_start=datetime(2026, 10, 5, 9))
    assert arrange.shift_task(task, -2)
    assert task.planned_start == datetime(2026, 10, 3, 9)
    assert task.planned_end is None


def test_shift_without_a_start_does_nothing() -> None:
    task = Task("x", planned_end=datetime(2026, 10, 7))
    assert not arrange.shift_task(task, 1)
    assert task.planned_end == datetime(2026, 10, 7)


def test_shift_out_of_the_year_range_writes_nothing() -> None:
    task = Task("x", planned_start=datetime(2100, 12, 31, 9))
    assert not arrange.shift_task(task, 1)
    assert task.planned_start == datetime(2100, 12, 31, 9)
    assert not arrange.shift_task(task, 10**10)  # timedelta 自体が溢れる
    assert task.planned_start == datetime(2100, 12, 31, 9)


def test_shift_is_atomic_when_only_the_end_goes_out_of_range() -> None:
    task = Task(
        "x",
        planned_start=datetime(2100, 12, 20, 9),
        planned_end=datetime(2100, 12, 31, 18),
    )
    assert not arrange.shift_task(task, 1)
    assert task.planned_start == datetime(2100, 12, 20, 9)
    assert task.planned_end == datetime(2100, 12, 31, 18)


def test_parse_position() -> None:
    assert arrange.parse_position([None, 0]) == (None, 0)
    assert arrange.parse_position([2, 5]) == (2, 5)
    assert arrange.parse_position((1, 0)) == (1, 0)
    for bad in (None, 3, "ab", [1], [1, 2, 3], ["0", 1], [True, 1], [0, 1.5], [0, "1"], [0, True]):
        assert arrange.parse_position(bad) is None


def test_parse_move() -> None:
    ok = {"src": [0, 1], "dst": [None, 2], "copy": True}
    assert arrange.parse_move(ok) == ((0, 1), (None, 2), True)
    assert arrange.parse_move({**ok, "copy": False}) == ((0, 1), (None, 2), False)
    assert arrange.parse_move({**ok, "copy": 1}) is None
    assert arrange.parse_move({**ok, "src": "x"}) is None
    assert arrange.parse_move({"src": [0, 1], "copy": False}) is None
    assert arrange.parse_move([1, 2]) is None
    assert arrange.parse_move(None) is None


def test_parse_shift_accepts_integers_within_the_limit_only() -> None:
    assert arrange.parse_shift({"si": None, "ti": 0, "days": -3}) == ((None, 0), -3)
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": 3650}) == ((1, 2), 3650)
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": 3651}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": -3651}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": 1.5}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": True}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": "3"}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2}) is None
    assert arrange.parse_shift("x") is None


def test_min_shift_days_stops_at_the_base_date() -> None:
    base = date(2026, 10, 5)
    assert arrange.min_shift_days(Task("x", planned_start=datetime(2026, 10, 7, 15)), base) == -2
    assert arrange.min_shift_days(Task("x", planned_start=datetime(2026, 10, 5, 9)), base) == 0


def test_min_shift_days_lets_a_task_already_before_the_base_date_move_only_right() -> None:
    base = date(2026, 10, 5)
    assert arrange.min_shift_days(Task("x", planned_start=datetime(2026, 10, 3, 9)), base) == 0


def test_min_shift_days_without_a_start_is_zero() -> None:
    assert arrange.min_shift_days(Task("x"), date(2026, 10, 5)) == 0


def test_copy_does_not_copy_actuals() -> None:
    project = sample()
    original = project.sections[0].tasks[1]
    original.actuals = [Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12))]
    copy = arrange.copy_task(project, (0, 1), (1, 0))
    assert copy.actuals == []
    assert len(original.actuals) == 1


def test_shift_moves_only_the_planned_dates() -> None:
    actuals = [Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12))]
    task = Task("t", planned_start=datetime(2026, 10, 5, 9), actuals=list(actuals))
    assert arrange.shift_task(task, 2) is True
    assert task.planned_start == datetime(2026, 10, 7, 9)
    assert task.actuals == actuals


def test_move_keeps_actuals() -> None:
    project = sample()
    moved = project.sections[0].tasks[1]
    moved.actuals = [Actual(datetime(2026, 10, 5, 9), None)]
    arrange.move_task(project, (0, 1), (1, 0))
    assert project.sections[1].tasks[0].actuals == [Actual(datetime(2026, 10, 5, 9), None)]


def test_copy_task_gets_a_new_id_and_no_predecessors() -> None:
    original = Task("a0", id="aaaaaaaa", predecessors=["zzzzzzzz"])
    project = Project("p", sections=[Section("A", [original])])
    copy = arrange.copy_task(project, (0, 0), (0, 1))
    assert copy.id != "aaaaaaaa" and len(copy.id) == 8
    assert copy.predecessors == []
    assert original.predecessors == ["zzzzzzzz"]


def test_shift_task_of_a_pushed_task_starts_from_the_shown_start() -> None:
    task = Task(
        "b",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 5, 18),
    )
    shown = datetime(2026, 10, 8, 9)  # 先行に 3 日押し出されている
    assert arrange.shift_task(task, 2, shown)
    assert task.planned_start == datetime(2026, 10, 10, 9)
    assert task.planned_end == datetime(2026, 10, 10, 18)  # 5 + 3(押し出し)+ 2


def test_shift_task_without_a_push_is_unchanged() -> None:
    task = Task("b", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 9))
    assert arrange.shift_task(task, 1)
    assert (task.planned_start, task.planned_end) == (
        datetime(2026, 10, 6, 9),
        datetime(2026, 10, 7, 9),
    )


def test_min_shift_days_stops_at_the_base_date_and_the_predecessors_finish() -> None:
    task = Task("b", planned_start=datetime(2026, 10, 12, 9))
    base = date(2026, 10, 5)
    assert arrange.min_shift_days(task, base) == -7
    floor = datetime(2026, 10, 8, 15, 30)  # 先行の完了
    assert arrange.min_shift_days(task, base, None, floor) == -4  # 12 → 8
    pushed_shown = datetime(2026, 10, 8, 15, 30)
    assert arrange.min_shift_days(task, base, pushed_shown, floor) == 0
    assert arrange.min_shift_days(task, date(2026, 10, 10), None, floor) == -2  # 基準日が遅いとき
