import pytest

from projectapp.models import MAX_TASK_NAME_LENGTH, has_control_char, tidy_task_name


@pytest.mark.parametrize("text", ["a\nb", "a\tb", "a\rb", "a\x00b", "a\x7fb", "a\x85b"])
def test_has_control_char_detects_control_characters(text: str) -> None:
    assert has_control_char(text)


@pytest.mark.parametrize("text", ["", "設計", "a b", "a　b", "a-b_c.d", "記号!?#"])
def test_has_control_char_accepts_ordinary_text(text: str) -> None:
    assert not has_control_char(text)


def test_the_limit_is_fifty() -> None:
    assert MAX_TASK_NAME_LENGTH == 50


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("設計", "設計"),
        ("  設計  ", "設計"),
        ("a\nb", "a b"),
        ("a\tb", "a b"),
        ("a\x00b", "a b"),
        ("a\x85b", "a b"),
        ("あ" * 50, "あ" * 50),
        ("あ" * 51, "あ" * 50),
        ("a" * 49 + "\n" + "b", "a" * 49),  # 切り詰めたあとの末尾の空白も除く
        ("\n", ""),
        ("", ""),
    ],
)
def test_tidy_task_name(raw: str, expected: str) -> None:
    assert tidy_task_name(raw) == expected
