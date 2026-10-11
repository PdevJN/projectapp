from datetime import date

import pytest

from projectapp.categories import (
    COLORS,
    UNDECIDED,
    CategoryEdit,
    apply_edit,
    by_id,
    chip_text,
    count_usage,
    migrate_legacy,
    next_color,
    parse_expiry,
    validate_categories,
)
from projectapp.models import Category, Project, Section, Task


def cat(name: str = "開発", **kwargs: object) -> Category:
    return Category(name, **kwargs)  # type: ignore[arg-type]


def test_valid_categories_pass() -> None:
    validate_categories([cat("開発", kind="業務", expiry_date=date(2026, 12, 31), prj_code="PRJ-1"), cat("保守")])


def test_empty_list_is_valid() -> None:
    validate_categories([])


@pytest.mark.parametrize(
    ("category", "message"),
    [
        (cat(""), "名前"),
        (cat("   "), "名前"),
        (cat(UNDECIDED), "未定"),
        (cat(" 未定 "), "未定"),
        (cat("a", color="gold"), "色"),
        (cat("あ" * 31), "名前"),
        (cat("a\nb"), "名前"),
        (cat("a", prj_code="P\nQ"), "PRJ"),
        (cat("a", prj_code="P\x00"), "PRJ"),
        (cat("a", prj_code="設計"), "PRJ"),
        (cat("a", prj_code="PRJ 1"), "PRJ"),
        (cat("a", prj_code="ＰＲＪ"), "PRJ"),
        (cat("a", prj_code="PRJ/1"), "PRJ"),
        (cat("a", kind="あ" * 21), "種別"),
        (cat("a", kind="業務\n開発"), "種別"),
        (cat("a", kind="業務\t"), "種別"),
        (cat("a", kind="業務\x7f"), "種別"),
        (cat("a", kind="業務\x85"), "種別"),
        (cat("a", kind="業\u200b務"), "種別"),
        (cat("a", kind="業務\u2028"), "種別"),
        (cat("開\u200b発"), "名前"),
        (cat("開\ufeff発"), "名前"),
        (cat("a", prj_code="A" * 21), "PRJ"),
        (cat("a", id=""), "id"),
    ],
)
def test_invalid_category_is_rejected(category: Category, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_categories([category])


@pytest.mark.parametrize("code", ["", "PRJ-001", "prj_1.2", "A" * 20, "0", "-_."])
def test_prj_codes_made_of_ascii_letters_digits_and_dash_underscore_dot_are_accepted(code: str) -> None:
    validate_categories([cat("a", prj_code=code)])


def test_boundary_lengths_are_accepted() -> None:
    validate_categories([cat("あ" * 30, kind="あ" * 20, prj_code="A" * 20)])


def test_duplicate_names_are_rejected_after_trimming() -> None:
    with pytest.raises(ValueError, match="重複"):
        validate_categories([cat("開発"), cat(" 開発 ")])


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="id"):
        validate_categories([cat("a", id="aaaaaaaa"), cat("b", id="aaaaaaaa")])


def test_parse_expiry() -> None:
    assert parse_expiry("2026-12-31") == date(2026, 12, 31)
    assert parse_expiry("  2026-12-31 ") == date(2026, 12, 31)
    assert parse_expiry("") is None
    assert parse_expiry("   ") is None


@pytest.mark.parametrize("bad", ["2026-13-01", "20261231", "2026-1-1", "2026-12-31T09:00", "1999-01-01", "2101-01-01", "abc"])
def test_parse_expiry_rejects_bad_dates(bad: str) -> None:
    with pytest.raises(ValueError, match="有効期限"):
        parse_expiry(bad)


def test_migrate_legacy_makes_one_category_per_code_in_order() -> None:
    a1, b, a2, none = Task("a1"), Task("b"), Task("a2"), Task("n")
    categories = migrate_legacy([(a1, "PRJ-A"), (b, "PRJ-B"), (a2, "PRJ-A"), (none, "")])
    assert [(c.name, c.prj_code, c.kind, c.expiry_date) for c in categories] == [
        ("PRJ-A", "PRJ-A", "", None),
        ("PRJ-B", "PRJ-B", "", None),
    ]
    assert [c.color for c in categories] == ["blue", "indigo"]
    assert a1.category_id == a2.category_id == categories[0].id
    assert b.category_id == categories[1].id
    assert none.category_id is None
    validate_categories(categories)


def test_migrate_legacy_keeps_a_code_that_is_not_a_valid_prj_code_as_the_name_only() -> None:
    task = Task("t")
    (category,) = migrate_legacy([(task, "設計 A")])
    assert (category.name, category.prj_code) == ("設計 A", "")  # チップは名前を出すので、見た目は変わらない
    validate_categories([category])


def test_migrate_legacy_replaces_control_characters_in_the_name() -> None:
    first, second = Task("a"), Task("b")
    (category,) = migrate_legacy([(first, "A\nB"), (second, "A B")])
    assert (category.name, category.prj_code) == ("A B", "")
    assert first.category_id == second.category_id == category.id  # 整えた名前が同じなら 1 つにまとめる
    validate_categories([category])


def test_migrate_legacy_treats_a_code_of_only_control_characters_as_undecided() -> None:
    task = Task("t")
    assert migrate_legacy([(task, "\n\t")]) == []
    assert task.category_id is None


def test_migrate_legacy_treats_the_reserved_name_as_undecided() -> None:
    task = Task("t")
    assert migrate_legacy([(task, UNDECIDED)]) == []
    assert task.category_id is None


def test_migrate_legacy_cycles_the_ten_colors() -> None:
    tasks = [Task(f"t{i}") for i in range(11)]
    categories = migrate_legacy([(t, f"C{i}") for i, t in enumerate(tasks)])
    assert len(categories) == 11
    assert categories[10].color == categories[0].color == COLORS[0]
    assert len({c.id for c in categories}) == 11


def test_migrate_legacy_avoids_taken_ids() -> None:
    taken = {f"{n:08x}" for n in range(200)}
    categories = migrate_legacy([(Task(f"t{i}"), f"C{i}") for i in range(20)], taken)
    assert not ({c.id for c in categories} & taken)


def test_next_color_takes_the_first_unused_color() -> None:
    assert next_color([]) == "blue"
    assert next_color([cat("a", color="blue"), cat("b", color="red")]) == "indigo"


def test_next_color_cycles_when_every_color_is_used() -> None:
    used = [cat(f"c{i}", color=color) for i, color in enumerate(COLORS)]
    assert next_color(used) == COLORS[0]
    assert next_color(used + [cat("x", color="blue")]) == COLORS[1]


def test_count_usage_counts_tasks_in_sections_too() -> None:
    category = cat("a")
    project = Project(
        "p",
        tasks=[Task("1", category_id=category.id), Task("2")],
        sections=[Section("s", [Task("3", category_id=category.id)], [Section("c", [Task("4", category_id=category.id)])])],
        categories=[category],
    )
    assert count_usage(project, category.id) == 3
    assert count_usage(project, "zzzzzzzz") == 0


def test_apply_edit_replaces_the_list_and_resets_removed_categories_to_undecided() -> None:
    keep, drop = cat("keep"), cat("drop")
    project = Project(
        "p",
        tasks=[Task("1", category_id=keep.id), Task("2", category_id=drop.id)],
        sections=[Section("s", [Task("3", category_id=drop.id)])],
        categories=[keep, drop],
    )
    renamed = cat("keep2", id=keep.id)
    apply_edit(project, CategoryEdit([renamed], [drop.id]))
    assert project.categories == [renamed]
    assert [t.category_id for t in project.all_tasks()] == [keep.id, None, None]


def test_apply_edit_with_no_removal_keeps_the_tasks() -> None:
    a = cat("a")
    project = Project("p", tasks=[Task("1", category_id=a.id)], categories=[a])
    apply_edit(project, CategoryEdit([a, cat("b")], []))
    assert project.tasks[0].category_id == a.id
    assert [c.name for c in project.categories] == ["a", "b"]


def test_chip_text_prefers_the_prj_code_then_the_name() -> None:
    assert chip_text(cat("開発", prj_code="PRJ-1")) == "PRJ-1"
    assert chip_text(cat("開発")) == "開発"


def test_by_id() -> None:
    a, b = cat("a"), cat("b")
    assert by_id([a, b]) == {a.id: a, b.id: b}


def test_project_used_ids_include_the_categories() -> None:
    a = cat("a")
    assert a.id in Project("p", categories=[a]).used_ids()
