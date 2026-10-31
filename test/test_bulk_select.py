from projectapp.bulk_select import BulkSelection, with_children
from projectapp.models import Task, TaskKind


def tasks() -> dict[str, Task]:
    items = [
        Task("a", id="a"),
        Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["c0", "c1"]),
        Task("c0", id="c0"),
        Task("c1", id="c1"),
        Task("b", id="b"),
    ]
    return {t.id: t for t in items}


VISIBLE = ["a", "s", "c0", "c1", "b"]


def test_with_children_expands_only_summaries_and_skips_missing_children() -> None:
    by_id = tasks()
    assert with_children("a", by_id) == ["a"]
    assert with_children("s", by_id) == ["s", "c0", "c1"]
    assert with_children("zzz", by_id) == []
    by_id["s"].children.append("gone")
    assert with_children("s", by_id) == ["s", "c0", "c1"]


def test_toggle_adds_then_removes_and_moves_the_anchor() -> None:
    sel, by_id = BulkSelection(), tasks()
    sel.toggle("a", by_id)
    assert sel.ids == {"a"} and sel.anchor == "a"
    sel.toggle("a", by_id)
    assert sel.ids == set() and sel.anchor == "a"


def test_toggling_a_summary_takes_its_children_and_a_child_can_be_dropped_alone() -> (
    None
):
    sel, by_id = BulkSelection(), tasks()
    sel.toggle("s", by_id)
    assert sel.ids == {"s", "c0", "c1"}
    sel.toggle("c0", by_id)
    assert sel.ids == {"s", "c1"}
    sel.toggle("s", by_id)  # まとめを外すと子も外れる
    assert sel.ids == set()


def test_extend_selects_the_visible_range_between_anchor_and_target() -> None:
    sel, by_id = BulkSelection(), tasks()
    sel.toggle("a", by_id)
    sel.extend(VISIBLE, "c1", by_id)
    assert sel.ids == {"a", "s", "c0", "c1"}
    assert sel.anchor == "a"  # Shift は基点を動かさない
    sel.extend(VISIBLE, "b", by_id)
    assert sel.ids == set(VISIBLE)


def test_extend_works_upwards_and_includes_children_of_a_collapsed_summary() -> None:
    sel, by_id = BulkSelection(), tasks()
    visible = ["a", "s", "b"]  # まとめは折りたたまれ、子は見えない
    sel.toggle("b", by_id)
    sel.extend(visible, "a", by_id)
    assert sel.ids == {"a", "s", "c0", "c1", "b"}


def test_extend_without_a_usable_anchor_acts_like_toggle() -> None:
    sel, by_id = BulkSelection(), tasks()
    sel.extend(VISIBLE, "b", by_id)
    assert sel.ids == {"b"}
    sel.anchor = "hidden"  # 見えていない行が基点
    sel.extend(VISIBLE, "a", by_id)
    assert sel.ids == {"a", "b"}


def test_effective_keeps_only_visible_rows_in_render_order() -> None:
    sel, by_id = BulkSelection(), tasks()
    for tid in ("b", "a", "c1"):
        sel.toggle(tid, by_id)
    assert sel.effective(["a", "c1", "b"]) == ["a", "c1", "b"]
    assert sel.effective(["a", "b"]) == ["a", "b"]  # 隠れた c1 は対象外
    assert sel.ids == {"a", "b", "c1"}  # 集合そのものは変えない


def test_prune_drops_missing_ids_and_a_missing_anchor_and_clear_empties() -> None:
    sel, by_id = BulkSelection(), tasks()
    sel.toggle("a", by_id)
    sel.toggle("b", by_id)
    del by_id["b"]
    sel.prune(by_id)
    assert sel.ids == {"a"} and sel.anchor is None
    sel.clear()
    assert sel.ids == set()
