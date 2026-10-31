from datetime import datetime

from projectapp.models import Actual, Assignee, Priority, Task, TaskUrl
from projectapp.task_sections import (
    actuals_summary,
    assignees_summary,
    has_values,
    initial_open,
    related_summary,
    section_of_error,
)


def test_a_new_task_has_no_values_in_any_section() -> None:
    task = Task("a")
    assert not any(has_values(key, task) for key in ("assignees", "actuals", "related"))


def test_has_values_per_section() -> None:
    assert has_values("assignees", Task("a", assignees=[Assignee("田中", 1.0)]))
    assert has_values("assignees", Task("a", parameters=["P"]))
    assert has_values("actuals", Task("a", progress=0))
    assert has_values(
        "actuals", Task("a", actuals=[Actual(datetime(2026, 10, 5, 9, 0), None)])
    )
    assert has_values("related", Task("a", predecessors=["p"]))
    assert has_values(
        "related",
        Task("a", urls=[TaskUrl("仕様", None, {"URL": "https://example.com"})]),
    )
    assert has_values("related", Task("a", priority=Priority.HIGH))
    assert has_values("related", Task("a", color="#123456"))
    assert not has_values("related", Task("a", priority=Priority.MEDIUM))


def test_initial_open_new_task_opens_nothing_without_a_saved_state() -> None:
    assert initial_open(None, None) == []


def test_initial_open_new_task_follows_the_saved_state() -> None:
    assert initial_open(None, ["related", "assignees"]) == ["assignees", "related"]


def test_initial_open_edit_opens_the_sections_with_values() -> None:
    task = Task("a", progress=40, priority=Priority.LOW)
    assert initial_open(task, None) == ["actuals", "related"]


def test_initial_open_edit_opens_valued_sections_even_if_the_saved_state_is_closed() -> (
    None
):
    task = Task("a", progress=40)
    assert initial_open(task, []) == ["actuals"]
    assert initial_open(task, ["assignees"]) == ["assignees", "actuals"]


def test_assignees_summary() -> None:
    assert assignees_summary([], 0) == ""
    assert assignees_summary([("田中", 1.0), ("鈴木", 0.5)], 0) == "田中 100%・鈴木 50%"
    assert assignees_summary([("田中", 1.0)], 2) == "田中 100%・パラメータ 2"
    assert assignees_summary([], 1) == "パラメータ 1"


def test_assignees_summary_caps_at_three_people() -> None:
    crew = [("A", 1.0), ("B", 1.0), ("C", 0.25), ("D", 1.0), ("E", 1.0)]
    assert assignees_summary(crew, 0) == "A 100%・B 100%・C 25%・ほか 2 人"


def test_actuals_summary() -> None:
    assert actuals_summary(0, True, None) == ""
    assert actuals_summary(2, True, 40) == "2区間・進捗 40%"
    assert actuals_summary(1, False, None) == "実績あり"
    assert actuals_summary(0, True, 0) == "進捗 0%"


def test_related_summary_omits_empty_items_and_the_default_priority() -> None:
    assert related_summary(0, 0, Priority.MEDIUM, False) == ""
    assert related_summary(2, 1, Priority.HIGH, False) == "先行 2・リンク 1・優先度 高"
    assert related_summary(0, 0, Priority.MEDIUM, True) == "色"


def test_section_of_error() -> None:
    assert section_of_error("区間 2: 前の区間と重なっています") == "actuals"
    assert section_of_error("区間は開始の早い順に入れてください") == "actuals"
    assert section_of_error("実績の終了は開始以降の日時にしてください") == "actuals"
    assert section_of_error("進捗度は0〜100の整数で入力してください") == "actuals"
    assert section_of_error("担当者が重複しています: 田中") == "assignees"
    assert section_of_error("先行タスクが正しくありません") == "related"
    assert section_of_error("色は#RRGGBBの形式で入力してください") == "related"
    assert section_of_error("リンク1行目: URL を入力してください") == "related"
    assert (
        section_of_error("リンク2行目: URL は http:// か https:// で始めてください")
        == "related"
    )
    assert section_of_error("割り当て率は1〜100%で入力してください") == "assignees"
    assert section_of_error("工数は0以上の数値で入力してください") is None
