import pytest

from projectapp.models import Project, Section, Task, TaskUrl, UrlTemplate
from projectapp.urls import (
    TemplateEdit,
    apply_template_edit,
    count_usage,
    expand_template,
    has_allowed_scheme,
    rename_templates,
    resolve,
    validate_templates,
    validate_urls,
)

TICKET = UrlTemplate("チケット", "https://example.com/{ID}")
WIKI = UrlTemplate("Wiki", "https://wiki.example.com/{ID}")


def by_id(value: str, template: str = "チケット") -> TaskUrl:
    return TaskUrl("", template, {"ID": value})


def plain(value: str) -> TaskUrl:
    return TaskUrl("", None, {"URL": value})


def test_resolve_replaces_the_placeholder_with_the_id() -> None:
    assert resolve(by_id("231"), [TICKET]) == "https://example.com/231"


def test_resolve_encodes_the_id() -> None:
    assert resolve(by_id("a b/#?"), [TICKET]) == "https://example.com/a%20b%2F%23%3F"
    assert resolve(by_id("日本"), [TICKET]) == "https://example.com/%E6%97%A5%E6%9C%AC"


def test_resolve_does_not_replace_a_placeholder_typed_as_the_id() -> None:
    assert resolve(by_id("{ID}"), [TICKET]) == "https://example.com/%7BID%7D"


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("https://x.test/{ID}/edit/{ID}", "https://x.test/7/edit/7"),
        ("https://x.test/fixed", "https://x.test/fixed"),
        ("https://x.test/{a}/{ID}", "https://x.test/{a}/7"),
        ("https://x.test/{", "https://x.test/{"),
    ],
)
def test_resolve_handles_patterns_without_formatting_errors(pattern: str, expected: str) -> None:
    assert resolve(by_id("7", "t"), [UrlTemplate("t", pattern)]) == expected


def test_resolve_uses_a_plain_url_as_it_is() -> None:
    assert resolve(plain(" https://example.com/a?b=1 "), []) == "https://example.com/a?b=1"


def test_the_scheme_check_ignores_case() -> None:
    assert has_allowed_scheme("HTTPS://Example.com")
    assert resolve(plain("HTTP://example.com"), []) == "HTTP://example.com"


@pytest.mark.parametrize(
    "value", ["javascript:alert(1)", "file:///etc/passwd", "ftp://x.test", "example.com", "  ", ""]
)
def test_resolve_rejects_urls_that_are_not_http(value: str) -> None:
    with pytest.raises(ValueError):
        resolve(plain(value), [])


def test_resolve_rejects_an_empty_id_and_an_unknown_template() -> None:
    with pytest.raises(ValueError, match="ID"):
        resolve(by_id("  "), [TICKET])
    with pytest.raises(ValueError, match="見つかりません"):
        resolve(by_id("1", "なし"), [TICKET])


def test_resolve_rejects_a_template_whose_pattern_is_not_http() -> None:
    with pytest.raises(ValueError):
        resolve(by_id("1", "t"), [UrlTemplate("t", "javascript:{ID}")])


def test_validate_templates_accepts_valid_ones() -> None:
    validate_templates([TICKET, WIKI])
    validate_templates([])


@pytest.mark.parametrize(
    ("templates", "message"),
    [
        ([UrlTemplate("  ", "https://x.test/{ID}")], "名前"),
        ([TICKET, UrlTemplate("チケット", "https://y.test/{ID}")], "重複"),
        ([UrlTemplate("a", "javascript:{ID}")], "http"),
        ([UrlTemplate("a", "")], "http"),
    ],
)
def test_validate_templates_rejects_invalid_ones(templates: list[UrlTemplate], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_templates(templates)


def test_validate_urls_checks_every_link() -> None:
    validate_urls([by_id("1"), plain("https://example.com")], [TICKET])
    with pytest.raises(ValueError):
        validate_urls([by_id("1"), plain("javascript:x")], [TICKET])


def make_project() -> Project:
    first = Task("a", urls=[by_id("1"), TaskUrl("メモ", "Wiki", {"ID": "Top"})])
    second = Task("b", urls=[by_id("2"), plain("https://example.com/x")])
    return Project(
        "p", sections=[Section("s", [first])], tasks=[second], url_templates=[TICKET, WIKI]
    )


def test_count_usage_counts_links_across_all_tasks() -> None:
    project = make_project()
    assert count_usage(project, "チケット") == 2
    assert count_usage(project, "Wiki") == 1
    assert count_usage(project, "なし") == 0


def test_expand_template_turns_links_into_plain_urls_and_keeps_titles() -> None:
    project = make_project()
    assert expand_template(project, "Wiki") == 1
    memo = project.sections[0].tasks[0].urls[1]
    assert memo == TaskUrl("メモ", None, {"URL": "https://wiki.example.com/Top"})
    assert project.sections[0].tasks[0].urls[0].template == "チケット"  # 他のテンプレートは触らない


def test_rename_templates_swaps_names_in_one_pass() -> None:
    project = make_project()
    rename_templates(project, {"チケット": "Wiki", "Wiki": "チケット"})
    first = project.sections[0].tasks[0].urls
    assert [link.template for link in first] == ["Wiki", "チケット"]


def test_apply_template_edit_expands_removed_renames_and_replaces() -> None:
    project = make_project()
    edit = TemplateEdit(
        templates=[UrlTemplate("課題", "https://example.com/{ID}")],
        renames={"チケット": "課題"},
        removed=["Wiki"],
    )
    apply_template_edit(project, edit)
    assert project.url_templates == [UrlTemplate("課題", "https://example.com/{ID}")]
    first = project.sections[0].tasks[0].urls
    assert first[0].template == "課題"
    assert first[1] == TaskUrl("メモ", None, {"URL": "https://wiki.example.com/Top"})


def test_a_deleted_and_recreated_name_expands_with_the_old_pattern() -> None:
    project = make_project()
    edit = TemplateEdit(
        templates=[UrlTemplate("Wiki", "https://new.example.com/{ID}"), TICKET],
        renames={},
        removed=["Wiki"],
    )
    apply_template_edit(project, edit)
    memo = project.sections[0].tasks[0].urls[1]
    assert memo == TaskUrl("メモ", None, {"URL": "https://wiki.example.com/Top"})
    assert count_usage(project, "Wiki") == 0
