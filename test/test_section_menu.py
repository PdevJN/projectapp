from copy import deepcopy
from datetime import datetime

import pytest
from nicegui.testing import User

from projectapp import arrange
from projectapp.gantt import ViewOptions
from projectapp.linkgraph import validate_links
from projectapp.models import (
    Actual,
    Project,
    Section,
    SectionPath,
    Task,
    TaskKind,
    walk_sections,
)
from test_gantt import mount_chart, mount_with


def tree() -> Project:
    """開発 > [a, b(a 先行)], 子 > [c]。企画 > [d]。直下 z。"""
    return Project(
        "p",
        tasks=[Task("z", id="z")],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a"),
                    Task(
                        "b",
                        id="b",
                        predecessors=["a", "z"],
                        actuals=[
                            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12))
                        ],
                    ),
                ],
                [Section("子", [Task("c", id="c")], id="child")],
                id="dev",
            ),
            Section("企画", [Task("d", id="d")], id="plan"),
        ],
    )


def test_copy_section_puts_a_full_copy_right_after_the_original() -> None:
    project = tree()
    copy = arrange.copy_section(project, (0,))
    assert [s.name for s in project.sections] == ["開発", "開発(コピー)", "企画"]
    assert project.sections[1] is copy
    assert [t.name for t in copy.tasks] == ["a", "b"]
    assert [(s.name, [t.name for t in s.tasks]) for s in copy.sections] == [
        ("子", ["c"])
    ]
    ids = [t.id for t in project.all_tasks()] + [
        s.id for _, s in walk_sections(project.sections)
    ]
    assert len(set(ids)) == len(ids)  # すべて新しい id
    assert [t.name for t in project.sections[0].all_tasks()] == [
        "a",
        "b",
        "c",
    ]  # 元は変えない


def test_copy_section_relinks_inside_and_drops_outside_links_and_actuals() -> None:
    project = tree()
    copy = arrange.copy_section(project, (0,))
    new_a, new_b = copy.tasks
    assert new_b.predecessors == [new_a.id]  # 中の連結は付け替え、外(z)への先行は外す
    assert new_b.actuals == []
    assert project.sections[0].tasks[1].predecessors == ["a", "z"]
    validate_links(project.all_tasks())


def test_copy_of_a_nested_section_stays_in_its_parent() -> None:
    project = tree()
    arrange.copy_section(project, (0, 0))
    assert [s.name for s in project.sections[0].sections] == ["子", "子(コピー)"]


def test_copy_section_remaps_summary_children_and_reverts_a_summary_with_outside_children() -> (
    None
):
    project = Project(
        "p",
        tasks=[Task("outside", id="o"), Task("outside2", id="o2")],
        sections=[
            Section(
                "s",
                [
                    Task("m", id="m", kind=TaskKind.SUMMARY, children=["x", "o"]),
                    Task("x", id="x"),
                    Task("m2", id="m2", kind=TaskKind.SUMMARY, children=["o2"]),
                ],
                id="s",
            )
        ],
    )
    copy = arrange.copy_section(project, (0,))
    m, x, m2 = copy.tasks
    assert (m.kind, m.children) == (TaskKind.SUMMARY, [x.id])  # 外の子は外す
    assert (m2.kind, m2.children) == (
        TaskKind.NORMAL,
        [],
    )  # 子が 0 件になったら通常タスクへ
    validate_links(project.all_tasks())


def test_delete_section_moves_every_task_to_the_root_in_order() -> None:
    project = tree()
    moved = arrange.delete_section(project, (0,))
    assert [s.name for s in project.sections] == ["企画"]
    assert [t.name for t in moved] == [
        "a",
        "b",
        "c",
    ]  # 自分のタスク、続いてサブセクションのタスク
    assert [t.name for t in project.tasks] == ["z", "a", "b", "c"]
    validate_links(project.all_tasks())


def test_delete_a_nested_section() -> None:
    project = tree()
    arrange.delete_section(project, (0, 0))
    assert project.sections[0].sections == []
    assert [t.name for t in project.tasks] == ["z", "c"]


@pytest.mark.parametrize(
    ("paths", "parent", "index", "delta", "expected"),
    [
        (
            {(1,), (2, 0)},
            (),
            1,
            1,
            {(2,), (3, 0)},
        ),  # 番号 1 に挿入: 1 以降が 1 つずれる
        ({(0,), (1,)}, (), 1, 1, {(0,), (2,)}),
        (
            {(0,), (1,), (1, 0), (2,)},
            (),
            1,
            -1,
            {(0,), (1,)},
        ),  # 番号 1 を削除: 中の分は消え、後ろが詰まる
        ({(0, 1), (0, 2)}, (0,), 1, -1, {(0, 1)}),  # 親の中の兄弟
    ],
)
def test_remap_collapsed_follows_the_shifted_sections(
    paths, parent, index, delta, expected
) -> None:  # noqa: ANN001
    assert arrange.remap_collapsed(paths, parent, index, delta) == expected


@pytest.mark.parametrize(
    ("marker", "event"),
    [
        ("section-context-copy", "copy_section"),
        ("section-context-rename", "rename_section"),
        ("section-context-delete", "delete_section"),
    ],
)
async def test_each_section_menu_item_acts_on_the_right_clicked_section(
    user: User, marker: str, event: str
) -> None:
    charts, recorder = mount_chart(tree())
    await user.open("/")
    charts[0].open_section_menu((0, 0))  # サブセクションにも出す
    user.find(marker=marker).click()
    assert recorder.events == [(event, ((0, 0),))]


async def test_the_section_menu_has_no_edit_or_decompose_item(user: User) -> None:
    mount_chart(tree())
    await user.open("/")
    await user.should_not_see(marker="section-context-edit")
    await user.should_not_see(marker="section-context-decompose")


async def test_every_section_header_opens_the_section_menu_on_right_click(
    user: User,
) -> None:
    mount_chart(tree())
    await user.open("/")
    for marker in ("section-0", "section-0.0", "section-1"):
        header = user.find(marker=marker).elements.pop()
        listeners = [
            ev for ev in header._event_listeners.values() if ev.type == "contextmenu"
        ]
        handler = listeners[0].js_handler or ""
        assert "preventDefault" in handler and ".show(e)" in handler


async def test_read_only_section_headers_have_no_menu(user: User) -> None:
    mount_with(tree(), ViewOptions(read_only=True))
    await user.open("/")
    header = user.find(marker="section-0").elements.pop()
    assert not [
        ev for ev in header._event_listeners.values() if ev.type == "contextmenu"
    ]


async def test_pressing_outside_closes_both_menus(user: User) -> None:
    charts, _ = mount_chart(tree())
    await user.open("/")
    js = charts[0].menu_close_js()
    assert f"getElement({charts[0].menu.id}).hide()" in js  # type: ignore[union-attr]
    assert f"getElement({charts[0].section_menu.id}).hide()" in js  # type: ignore[union-attr]


def three_roots() -> Project:
    """root に A・B・C。A の中にサブセクション x・y・z(z の中に孫 w)。"""
    return Project(
        "p",
        sections=[
            Section(
                "A",
                [Task("ta", id="ta")],
                [
                    Section("x", id="x"),
                    Section("y", id="y"),
                    Section("z", [], [Section("w", id="w")], id="z"),
                ],
                id="A",
            ),
            Section("B", [Task("tb", id="tb")], id="B"),
            Section("C", id="C"),
        ],
    )


def names(sections: list[Section]) -> list[str]:
    return [s.name for s in sections]


@pytest.mark.parametrize(
    ("path", "to_index", "expected"),
    [
        ((0,), 2, ["B", "C", "A"]),  # 先頭を末尾へ
        ((2,), 0, ["C", "A", "B"]),  # 末尾を先頭へ
        ((0,), 1, ["B", "A", "C"]),
        ((1,), 0, ["B", "A", "C"]),
    ],
)
def test_move_section_reorders_the_roots(
    path: SectionPath, to_index: int, expected: list[str]
) -> None:
    project = three_roots()
    assert arrange.move_section(project, path, to_index) is True
    assert names(project.sections) == expected


def test_move_section_reorders_subsections_and_keeps_contents_and_ids() -> None:
    project = three_roots()
    assert arrange.move_section(project, (0, 0), 2) is True
    parent = project.sections[0]
    assert names(parent.sections) == ["y", "z", "x"]
    assert [s.id for s in parent.sections] == ["y", "z", "x"]
    assert [t.name for t in parent.tasks] == ["ta"]
    assert names(parent.sections[1].sections) == ["w"]  # 孫は z に付いたまま


def test_move_section_reorders_a_third_level_section() -> None:
    project = Project(
        "p",
        sections=[Section("A", [], [Section("B", [], [Section("c1"), Section("c2")])])],
    )
    assert arrange.move_section(project, (0, 0, 1), 0) is True
    assert names(project.sections[0].sections[0].sections) == ["c2", "c1"]


@pytest.mark.parametrize(
    ("path", "to_index"),
    [
        ((1,), 1),
        ((0,), 3),
        ((0,), -1),
        ((5,), 0),
        ((), 0),
        ((0, 9), 0),
        ((9, 0), 0),
        ((0, 0), 3),
    ],
)
def test_move_section_returns_false_and_changes_nothing_for_a_noop_or_bad_target(
    path: SectionPath, to_index: int
) -> None:
    project = three_roots()
    before = deepcopy(project)
    assert arrange.move_section(project, path, to_index) is False
    assert project == before


@pytest.mark.parametrize(
    ("paths", "parent", "src", "dst", "expected"),
    [
        (
            {(0,), (1,), (2,)},
            (),
            0,
            2,
            {(2,), (0,), (1,)},
        ),  # 先頭を末尾へ: 動かした分は 2 に、間は 1 つ前へ
        ({(2,)}, (), 2, 0, {(0,)}),  # 末尾を先頭へ
        ({(1,)}, (), 0, 2, {(0,)}),  # 間の兄弟は 1 つ前へ
        ({(1,)}, (), 2, 0, {(2,)}),  # 間の兄弟は 1 つ後ろへ
        ({(3,)}, (), 0, 2, {(3,)}),  # 範囲の外は変えない
        (
            {(0, 1, 0), (0, 2)},
            (0,),
            1,
            2,
            {(0, 2, 0), (0, 1)},
        ),  # 子孫は動かしたセクションに付いていく
        ({(1, 0), (2,)}, (0,), 0, 1, {(1, 0), (2,)}),  # 別の親は変えない
        ({(0,)}, (), 1, 1, {(0,)}),  # 同じ位置は何も変えない
    ],
)
def test_reorder_collapsed_follows_the_moved_sections(
    paths: set[SectionPath],
    parent: SectionPath,
    src: int,
    dst: int,
    expected: set[SectionPath],
) -> None:
    assert arrange.reorder_collapsed(paths, parent, src, dst) == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"src": "0", "dst": "2"}, ((0,), (2,))),
        ({"src": "0.1", "dst": "0.2"}, ((0, 1), (0, 2))),
        ({"src": "0.1.2", "dst": "0.1.0"}, ((0, 1, 2), (0, 1, 0))),
        ({"src": "0", "dst": "0.1"}, None),  # 親が違う
        ({"src": "0.1", "dst": "1.1"}, None),
        ({"src": "top", "dst": "0"}, None),  # root(タスク側)は動かせない
        ({"src": "0", "dst": "top"}, None),
        ({"src": "0", "dst": 2}, None),
        ({"src": "x", "dst": "0"}, None),
        ({"src": "0"}, None),
        ("0", None),
        (None, None),
    ],
)
def test_parse_section_move_accepts_only_siblings(
    args: object, expected: tuple[SectionPath, SectionPath] | None
) -> None:
    assert arrange.parse_section_move(args) == expected


def test_collapsed_ids_and_paths_round_trip_through_a_reorder() -> None:
    project = three_roots()
    ids = arrange.collapsed_ids(
        project, {(0,), (0, 2, 0), (9,)}
    )  # 存在しないパスは無視する
    assert ids == {"A", "w"}
    arrange.move_section(project, (0,), 2)  # A が末尾へ
    assert arrange.collapsed_paths(project, ids) == {(2,), (2, 2, 0)}
    assert arrange.collapsed_paths(project, {"gone"}) == set()
