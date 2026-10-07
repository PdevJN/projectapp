from projectapp.filtering import TaskFilter
from projectapp.links import (
    Bar,
    RowSlot,
    link_points,
    path_data,
    row_centers,
    row_slots,
    total_height,
)
from projectapp.models import Project, Section, Task

ROW, ADD = 32, 24


def project() -> Project:
    return Project(
        "p",
        tasks=[Task("t0", id="t0"), Task("t1", id="t1")],
        sections=[
            Section("A", [Task("a0", id="a0"), Task("a1", id="a1")]),
            Section("B", [Task("b0", id="b0")]),
        ],
    )


def slots(
    task_filter: TaskFilter | None = None,
    collapsed: set[int] | None = None,
    read_only: bool = False,
) -> list[RowSlot]:
    return row_slots(project(), task_filter or TaskFilter(), collapsed or set(), read_only, ROW, ADD)


def test_slots_follow_the_render_order() -> None:
    kinds = [(s.kind, s.task_id) for s in slots()]
    assert kinds == [
        ("task", "t0"),
        ("task", "t1"),
        ("top-add", None),
        ("section", None),
        ("task", "a0"),
        ("task", "a1"),
        ("section", None),
        ("task", "b0"),
    ]


def test_read_only_has_no_add_row() -> None:
    assert all(s.kind != "top-add" for s in slots(read_only=True))


def test_centers_use_each_rows_height() -> None:
    centers = row_centers(slots(), top=100)
    assert centers["t0"] == 100 + ROW / 2
    assert centers["t1"] == 100 + ROW + ROW / 2
    assert centers["a0"] == 100 + 2 * ROW + ADD + ROW + ROW / 2  # 追加行と見出しを挟む
    assert total_height(slots(), top=100) == 100 + 2 * ROW + ADD + ROW + 2 * ROW + ROW + ROW


def test_a_collapsed_section_has_hidden_rows_that_take_no_space() -> None:
    result = slots(collapsed={0})
    assert [s.shown for s in result if s.task_id in ("a0", "a1")] == [False, False]
    centers = row_centers(result, top=0)
    assert "a0" not in centers and "a1" not in centers
    assert centers["b0"] == 2 * ROW + ADD + ROW + ROW + ROW / 2


def test_a_filter_keeps_only_matching_tasks_and_ignores_collapse() -> None:
    result = slots(task_filter=TaskFilter(query="a1"), collapsed={0})
    assert [(s.kind, s.task_id) for s in result] == [
        ("top-add", None),
        ("section", None),
        ("task", "a1"),
    ]
    assert all(s.shown for s in result)


def test_link_points_for_a_normal_arrow() -> None:
    pred = Bar(left=40, right=100)
    succ = Bar(left=160, right=200)
    assert link_points(pred, 16, succ, 48, ROW) == [(100, 16), (106, 16), (106, 48), (160, 48)]


def test_link_points_for_a_close_arrow_go_between_the_rows() -> None:
    pred = Bar(left=40, right=100)
    succ = Bar(left=105, right=200)  # 12px 未満
    assert link_points(pred, 16, succ, 48, ROW) == [
        (100, 16),
        (106, 16),
        (106, 32),
        (99, 32),
        (99, 48),
        (105, 48),
    ]


def test_link_points_for_an_upward_arrow_use_the_row_above() -> None:
    pred = Bar(left=40, right=100)
    succ = Bar(left=100, right=150)
    points = link_points(pred, 48, succ, 16, ROW)
    assert points[2] == (106, 32) and points[3] == (94, 32)  # 行の間(上側)を通る


def test_path_data_is_an_svg_move_and_lines() -> None:
    assert path_data([(1, 2), (3.5, 2), (3.5, 8)]) == "M1,2 L3.5,2 L3.5,8"
