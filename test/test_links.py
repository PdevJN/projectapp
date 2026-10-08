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
    collapsed: set[tuple[int, ...]] | None = None,
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
    result = slots(collapsed={(0,)})
    assert [s.shown for s in result if s.task_id in ("a0", "a1")] == [False, False]
    centers = row_centers(result, top=0)
    assert "a0" not in centers and "a1" not in centers
    assert centers["b0"] == 2 * ROW + ADD + ROW + ROW + ROW / 2


def test_a_filter_keeps_only_matching_tasks_and_ignores_collapse() -> None:
    result = slots(task_filter=TaskFilter(query="a1"), collapsed={(0,)})
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


def nested_project() -> Project:
    deep = Section("孫", [Task("g", id="g")])
    child = Section("子", [Task("c", id="c")], [deep])
    return Project(
        "p",
        tasks=[Task("r", id="r")],
        sections=[
            Section("親", [Task("p", id="p")], [child, Section("子2", [Task("c2", id="c2")])]),
            Section("別", [Task("o", id="o")]),
        ],
    )


def summary(result: list[RowSlot]) -> list[tuple[str, tuple[int, ...], int | None, bool]]:
    return [(slot.kind, slot.path, slot.ti, slot.shown) for slot in result]


def test_nested_sections_make_slots_depth_first() -> None:
    result = row_slots(nested_project(), TaskFilter(), set(), False, ROW, ADD)
    assert summary(result) == [
        ("task", (), 0, True),
        ("top-add", (), None, True),
        ("section", (0,), None, True),
        ("task", (0,), 0, True),
        ("section", (0, 0), None, True),
        ("task", (0, 0), 0, True),
        ("section", (0, 0, 0), None, True),
        ("task", (0, 0, 0), 0, True),
        ("section", (0, 1), None, True),
        ("task", (0, 1), 0, True),
        ("section", (1,), None, True),
        ("task", (1,), 0, True),
    ]


def test_collapsing_a_parent_hides_its_descendants_but_keeps_the_childs_own_state() -> None:
    def shown(collapsed: set[tuple[int, ...]]) -> dict[tuple[str, tuple[int, ...], int | None], bool]:
        result = row_slots(nested_project(), TaskFilter(), collapsed, False, ROW, ADD)
        return {(s.kind, s.path, s.ti): s.shown for s in result}

    parent_closed = shown({(0,)})
    assert parent_closed[("section", (0,), None)] is True  # 閉じた親の見出し自身は見える
    assert parent_closed[("task", (0,), 0)] is False
    assert parent_closed[("section", (0, 0), None)] is False
    assert parent_closed[("task", (0, 0, 0), 0)] is False
    assert parent_closed[("section", (1,), None)] is True and parent_closed[("task", (1,), 0)] is True
    reopened = shown({(0, 0)})  # 親を開いても、子は閉じたまま
    assert reopened[("section", (0, 0), None)] is True
    assert reopened[("task", (0, 0), 0)] is False
    assert reopened[("section", (0, 0, 0), None)] is False
    assert reopened[("task", (0, 1), 0)] is True
    both = shown({(0,), (0, 0)})
    assert both[("section", (0, 1), None)] is False


def test_a_filter_ignores_collapse_and_keeps_the_parents_of_matches() -> None:
    result = row_slots(nested_project(), TaskFilter(query="g"), {(0,), (0, 0)}, False, ROW, ADD)
    assert [(s.kind, s.path, s.ti) for s in result if s.kind != "top-add"] == [
        ("section", (0,), None),
        ("section", (0, 0), None),
        ("section", (0, 0, 0), None),
        ("task", (0, 0, 0), 0),
    ]
    assert all(s.shown for s in result)


def test_read_only_ignores_collapse_and_has_no_add_row() -> None:
    result = row_slots(nested_project(), TaskFilter(), {(0,)}, True, ROW, ADD)
    assert all(s.shown for s in result) and not any(s.kind == "top-add" for s in result)


def test_row_centers_skip_hidden_nested_rows() -> None:
    result = row_slots(nested_project(), TaskFilter(), {(0,)}, False, ROW, ADD)
    centers = row_centers(result, 0)
    assert "p" not in centers and "c" not in centers and "g" not in centers
    assert "r" in centers and "o" in centers
