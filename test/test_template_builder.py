import pytest

from projectapp.csv_profile import MAX_TEMPLATE_FIELDS, CsvField, template_problem
from projectapp.template_builder import (
    SEPARATORS,
    insert_token,
    move_token,
    remove_token,
    template_of,
    token_label,
    tokens_of,
)

pytestmark = pytest.mark.smoke

S, E, T = CsvField.START, CsvField.END, CsvField.TITLE


def test_a_template_round_trips_through_chips() -> None:
    text = "{開始日}/{期限}: {タスク名}"
    tokens = tokens_of(text)
    assert tokens == [S, "/", E, ": ", T]
    assert template_of(tokens) == text


def test_an_unreadable_template_gives_none() -> None:
    assert tokens_of("{開始日") is None
    assert tokens_of("{知らない}") is None
    assert tokens_of("") == []


def test_separators_are_the_requested_ones() -> None:
    assert SEPARATORS == (";", ":", ",", "-", "_", "+", "|", "\\", "/", " ")
    assert token_label(" ") == "␣" and token_label("|") == "|"
    assert token_label(S) == "開始日"


def test_insert_goes_to_the_position_or_the_end() -> None:
    assert insert_token([S, "/"], E, None) == [S, "/", E]
    assert insert_token([S, "/"], T, 0) == [T, S, "/"]
    assert insert_token([S], "/", 99) == [S, "/"]


def test_inserting_a_field_already_present_moves_it() -> None:
    assert insert_token([S, "/", E], S, 3) == ["/", E, S]
    assert insert_token([S, "/", E], E, 0) == [E, S, "/"]


def test_a_separator_can_repeat() -> None:
    assert insert_token([S, "/"], "/", None) == [S, "/", "/"]


def test_fields_stop_at_the_limit() -> None:
    fields = list(CsvField)[:MAX_TEMPLATE_FIELDS]
    extra = next(f for f in CsvField if f not in fields)
    assert insert_token(fields, extra, None) == fields


def test_move_and_remove() -> None:
    assert move_token([S, "/", E], 2, 0) == [E, S, "/"]
    assert move_token([S, "/", E], 0, 2) == ["/", E, S]
    assert move_token([S], 5, 0) == [S]
    assert remove_token([S, "/", E], 1) == [S, E]
    assert remove_token([S], 3) == [S]


def test_the_built_template_is_checked_by_the_existing_rule() -> None:
    assert template_problem(template_of([S, E, T])) is not None  # 区切りがない
    assert template_problem(template_of([S, "/", E, ": ", T])) is None
