from projectapp.filtering import TaskFilter, matches
from projectapp.models import Task


def test_an_empty_filter_is_inactive_and_matches_everything() -> None:
    task_filter = TaskFilter()
    assert not task_filter.active
    assert matches(Task("設計"), task_filter)
    assert matches(Task("設計", assignee="田中"), task_filter)


def test_query_is_a_case_insensitive_substring_match_on_the_name() -> None:
    task = Task("API Design")
    assert matches(task, TaskFilter(query="design"))
    assert matches(task, TaskFilter(query="API"))
    assert matches(task, TaskFilter(query="i d"))
    assert not matches(task, TaskFilter(query="test"))


def test_query_is_trimmed_and_blank_means_no_condition() -> None:
    assert matches(Task("設計"), TaskFilter(query="  設計 "))
    for blank in ("", " ", "　", " 　 "):
        task_filter = TaskFilter(query=blank)
        assert not task_filter.active
        assert matches(Task("設計"), task_filter)


def test_query_is_literal_not_a_pattern_or_markup() -> None:
    assert not matches(Task("設計"), TaskFilter(query=".*"))
    assert matches(Task("a.*b"), TaskFilter(query=".*"))
    assert matches(Task("<b>太字</b>"), TaskFilter(query="<b>"))
    assert not matches(Task("bold"), TaskFilter(query="<b>"))


def test_assignee_must_match_exactly() -> None:
    task_filter = TaskFilter(assignee="田中")
    assert task_filter.active
    assert matches(Task("設計", assignee="田中"), task_filter)
    assert not matches(Task("設計", assignee="田中さん"), task_filter)
    assert not matches(Task("設計", assignee="鈴木"), task_filter)


def test_a_task_without_an_assignee_is_hidden_when_an_assignee_is_chosen() -> None:
    assert not matches(Task("設計"), TaskFilter(assignee="田中"))


def test_query_and_assignee_are_combined_with_and() -> None:
    task_filter = TaskFilter(query="設", assignee="田中")
    assert matches(Task("設計", assignee="田中"), task_filter)
    assert not matches(Task("設計", assignee="鈴木"), task_filter)
    assert not matches(Task("実装", assignee="田中"), task_filter)
