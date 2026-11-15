from datetime import datetime

import pytest

from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.overview import NodeKind, build_overview

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
