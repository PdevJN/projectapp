from projectapp.filtering import TaskFilter, matches, visible_task_indexes
from projectapp.models import Assignee, Section, Task


def test_an_empty_filter_is_inactive_and_matches_everything() -> None:
    task_filter = TaskFilter()
    assert not task_filter.active
    assert matches(Task("設計"), task_filter)
    assert matches(Task("設計", assignees=[Assignee("田中")]), task_filter)


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
    assert matches(Task("設計", assignees=[Assignee("田中")]), task_filter)
    assert not matches(Task("設計", assignees=[Assignee("田中さん")]), task_filter)
    assert not matches(Task("設計", assignees=[Assignee("鈴木")]), task_filter)


def test_a_task_without_an_assignee_is_hidden_when_an_assignee_is_chosen() -> None:
    assert not matches(Task("設計"), TaskFilter(assignee="田中"))


def test_query_and_assignee_are_combined_with_and() -> None:
    task_filter = TaskFilter(query="設", assignee="田中")
    assert matches(Task("設計", assignees=[Assignee("田中")]), task_filter)
    assert not matches(Task("設計", assignees=[Assignee("鈴木")]), task_filter)
    assert not matches(Task("実装", assignees=[Assignee("田中")]), task_filter)


def section_of_three() -> Section:
    return Section(
        "開発",
        [Task("設計", assignees=[Assignee("田中")]), Task("実装", assignees=[Assignee("鈴木")]), Task("試験", assignees=[Assignee("田中")])],
    )


def test_an_expanded_section_shows_every_task() -> None:
    assert visible_task_indexes(section_of_three(), TaskFilter(), collapsed=False) == [0, 1, 2]


def test_a_collapsed_section_shows_no_task() -> None:
    assert visible_task_indexes(section_of_three(), TaskFilter(), collapsed=True) == []


def test_an_active_filter_ignores_the_collapse() -> None:
    task_filter = TaskFilter(assignee="田中")
    assert visible_task_indexes(section_of_three(), task_filter, collapsed=True) == [0, 2]
    assert visible_task_indexes(section_of_three(), task_filter, collapsed=False) == [0, 2]


def test_an_active_filter_with_no_match_shows_nothing() -> None:
    assert visible_task_indexes(section_of_three(), TaskFilter(query="zzz"), collapsed=True) == []


def test_an_empty_section_shows_nothing() -> None:
    assert visible_task_indexes(Section("空"), TaskFilter(), collapsed=False) == []
