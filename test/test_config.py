import json
from pathlib import Path

import pytest

from projectapp.config import (
    DEFAULT_NAME_WIDTH_PX,
    MAX_NAME_WIDTH_PX,
    MIN_NAME_WIDTH_PX,
    load_name_width,
    load_theme,
    parse_name_width,
    save_name_width,
    save_theme,
)


def test_the_width_constants() -> None:
    assert (MIN_NAME_WIDTH_PX, DEFAULT_NAME_WIDTH_PX, MAX_NAME_WIDTH_PX) == (120, 200, 480)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (200, 200),
        (120, 120),
        (480, 480),
        (119, 120),  # 範囲外は、範囲に収める
        (481, 480),
        (-5, 120),
        (10**400, 480),  # float に直せない大きさでも、落ちない
        (250.4, 250),  # 小数は、丸める
        (250.6, 251),
    ],
)
def test_parse_name_width_accepts_numbers_and_clamps(value: object, expected: int) -> None:
    assert parse_name_width(value) == expected


@pytest.mark.parametrize(
    "value", [True, False, None, "200", "abc", [], {}, float("nan"), float("inf"), -float("inf")]
)
def test_parse_name_width_rejects_other_values(value: object) -> None:
    assert parse_name_width(value) is None


def test_load_name_width_defaults_without_a_file(tmp_path: Path) -> None:
    assert load_name_width(tmp_path) == DEFAULT_NAME_WIDTH_PX


def test_load_name_width_defaults_without_the_key(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    assert load_name_width(tmp_path) == DEFAULT_NAME_WIDTH_PX


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(300, 300), (9999, 480), (-5, 120), ("abc", 200), (True, 200), (None, 200), (1e999, 200), (10**400, 480)],
)
def test_load_name_width_reads_the_stored_value_safely(
    tmp_path: Path, stored: object, expected: int
) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"name_width": stored}), encoding="utf-8")
    assert load_name_width(tmp_path) == expected


def test_save_name_width_creates_the_file_and_round_trips(tmp_path: Path) -> None:
    base = tmp_path / "new"  # まだ存在しない
    save_name_width(260, base)
    assert load_name_width(base) == 260
    assert json.loads((base / "config.json").read_text(encoding="utf-8")) == {"name_width": 260}


def test_saving_the_width_keeps_the_theme_and_other_keys(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "other": 1}), encoding="utf-8")
    save_name_width(300, tmp_path)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {
        "theme": "dark",
        "other": 1,
        "name_width": 300,
    }
    assert load_theme(tmp_path) == "dark"


def test_saving_the_theme_keeps_the_width(tmp_path: Path) -> None:
    save_name_width(300, tmp_path)
    save_theme("light", tmp_path)
    assert load_name_width(tmp_path) == 300
    assert load_theme(tmp_path) == "light"


def test_a_config_that_is_not_an_object_reads_as_empty_and_is_replaced_on_save(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("[1, 2]", encoding="utf-8")
    assert load_name_width(tmp_path) == DEFAULT_NAME_WIDTH_PX
    assert load_theme(tmp_path) == "auto"
    save_name_width(250, tmp_path)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {"name_width": 250}
