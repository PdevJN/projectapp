from datetime import datetime

import pytest

from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.overview import (
    GAP_Y,
    NODE_WIDTH,
    NodeKind,
    OverviewNode,
    build_overview,
    layout_overview,
    node_lines,
)

NOW = datetime(2026, 10, 1)


def sample() -> Project:
    return Project(
        "demo",
        sections=[
            Section(
                "開発",
                [
                    Task("設計", id="a", effort_hours=8.0, status=Status.DONE),
                    Task(
                        "実装",
                        id="s",
                        kind=TaskKind.SUMMARY,
                        children=["c1", "c2"],
                    ),
                    Task("実装1", id="c1", effort_hours=4.0, progress=50),
                    Task("実装2", id="c2", effort_hours=12.0),
                ],
                sections=[Section("テスト", [Task("結合", id="t", effort_hours=2.0)])],
            ),
            Section("空", []),
        ],
    )


def test_a_section_becomes_a_tree_of_sections_summaries_and_tasks() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(0,))
    assert (root.name, root.kind) == ("開発", NodeKind.SECTION)
    # まとめの子は、まとめの下だけに出す(セクション直下には出さない)
    assert [(c.name, c.kind) for c in root.children] == [
        ("設計", NodeKind.TASK),
        ("実装", NodeKind.SUMMARY),
        ("テスト", NodeKind.SECTION),
    ]
    summary = root.children[1]
    assert [c.name for c in summary.children] == ["実装1", "実装2"]


def test_summary_root_shows_only_its_children() -> None:
    root = build_overview(sample(), {}, NOW, summary_id="s")
    assert (root.name, root.kind) == ("実装", NodeKind.SUMMARY)
    assert [c.id for c in root.children] == ["c1", "c2"]


def test_progress_is_weighted_by_effort_and_done_counts_as_100() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(0,))
    done, summary, _ = root.children
    assert done.progress == 100
    # 実装1(4h・50%)と実装2(12h・0%): (4*50)/(4+12) = 12.5 → 12(Python の round は偶数丸め)
    assert summary.progress == 12
    assert summary.effort_hours == 16.0


def test_empty_section_is_a_single_node() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(1,))
    assert root.children == []
    assert root.progress is None and root.first_task_id is None


def test_section_first_task_id_points_to_the_first_task_inside() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(0,))
    assert root.first_task_id == "a"


def test_checkpoint_has_no_effort_and_is_left_out_of_progress() -> None:
    project = Project(
        "p",
        sections=[
            Section("S", [Task("節目", id="k", kind=TaskKind.CHECKPOINT)]),
        ],
    )
    root = build_overview(project, {}, NOW, section_path=(0,))
    assert root.children[0].kind is NodeKind.CHECKPOINT
    assert root.children[0].effort_hours is None
    assert root.progress is None


def test_exactly_one_of_section_path_and_summary_id_is_required() -> None:
    with pytest.raises(ValueError):
        build_overview(sample(), {}, NOW)
    with pytest.raises(ValueError):
        build_overview(sample(), {}, NOW, section_path=(0,), summary_id="s")


def leaf(name: str, **kw: object) -> OverviewNode:
    return OverviewNode(name, name, NodeKind.TASK, Status.NOT_STARTED, **kw)  # type: ignore[arg-type]


def test_node_lines_follow_the_checkboxes() -> None:
    node = leaf("設計", progress=45, effort_hours=8.0, due=datetime(2026, 11, 20))
    assert node_lines(node, True, True) == ["設計", "進捗 45%", "工数 8h・完了 11/20"]
    assert node_lines(node, False, True) == ["設計", "工数 8h・完了 11/20"]
    assert node_lines(node, True, False) == ["設計", "進捗 45%"]
    assert node_lines(node, False, False) == ["設計"]


def test_node_lines_skip_items_that_do_not_exist() -> None:
    assert node_lines(leaf("空"), True, True) == ["空"]
    assert node_lines(leaf("a", effort_hours=0.5), True, True) == ["a", "工数 0.5h"]


def tree() -> OverviewNode:
    root = leaf("R")
    root.children = [leaf("a"), leaf("b"), leaf("c")]
    root.children[1].children = [leaf("b1"), leaf("b2")]
    return root


def test_columns_follow_depth_and_siblings_stack_without_overlap() -> None:
    layout = layout_overview(tree(), True, True)
    by_name = {p.node.name: p for p in layout.placed}
    assert by_name["R"].x == 0
    assert by_name["a"].x == by_name["b"].x == by_name["c"].x > 0
    assert by_name["b1"].depth == 2 and by_name["b1"].x > by_name["a"].x
    columns: dict[int, list] = {}
    for p in layout.placed:
        columns.setdefault(p.depth, []).append(p)
    for items in columns.values():
        items.sort(key=lambda p: p.y)
        for upper, lower in zip(items, items[1:]):
            assert upper.y + upper.height + GAP_Y <= lower.y


def test_parent_is_centered_on_its_children_and_edges_join_them() -> None:
    layout = layout_overview(tree(), False, False)
    by_name = {p.node.name: p for p in layout.placed}
    kids = [by_name[n] for n in ("a", "b", "c")]
    top, bottom = kids[0].y, kids[-1].y + kids[-1].height
    root = by_name["R"]
    assert root.y + root.height / 2 == pytest.approx((top + bottom) / 2, abs=1)
    assert len(layout.edges) == len(layout.placed) - 1
    assert any(e.x1 == root.x + NODE_WIDTH for e in layout.edges)


def test_hidden_lines_make_nodes_shorter() -> None:
    tall = layout_overview(leaf("x", progress=1, effort_hours=1.0), True, True)
    short = layout_overview(leaf("x", progress=1, effort_hours=1.0), False, False)
    assert short.placed[0].height < tall.placed[0].height


def test_a_thousand_nodes_are_laid_out_without_overlap() -> None:
    root = leaf("R")
    root.children = [leaf(f"n{i}") for i in range(1000)]
    layout = layout_overview(root, True, True)
    ys = sorted(p.y for p in layout.placed if p.depth == 1)
    assert len(set(ys)) == 1000
    for upper, lower in zip(ys, ys[1:]):
        assert upper < lower


def test_a_tall_parent_with_a_short_child_does_not_overlap_its_sibling() -> None:
    root = leaf("R")
    tall = leaf("B", progress=1, effort_hours=1.0, due=datetime(2026, 11, 20))
    tall.children = [leaf("b1")]
    root.children = [leaf("A"), tall]
    layout = layout_overview(root, True, True)
    column = sorted((p for p in layout.placed if p.depth == 1), key=lambda p: p.y)
    for upper, lower in zip(column, column[1:]):
        assert upper.y + upper.height + GAP_Y <= lower.y
