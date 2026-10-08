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


def test_the_config_is_replaced_through_a_temporary_file_and_a_failure_keeps_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import projectapp.config as config_module

    save_name_width(300, tmp_path)

    def failing_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(config_module.os, "replace", failing_replace)
    with pytest.raises(OSError):
        save_theme("dark", tmp_path)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {"name_width": 300}  # 元のまま
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]  # 一時ファイルが残らない


def test_the_zoom_constants() -> None:
    from projectapp.config import DEFAULT_ZOOM_PERCENT, MAX_ZOOM_PERCENT, MIN_ZOOM_PERCENT, ZOOM_STEP_PERCENT

    assert (MIN_ZOOM_PERCENT, DEFAULT_ZOOM_PERCENT, MAX_ZOOM_PERCENT, ZOOM_STEP_PERCENT) == (70, 100, 200, 10)


@pytest.mark.parametrize(
    ("current", "direction", "expected"),
    [
        (100, 1, 110),
        (100, -1, 90),
        (200, 1, 200),  # 上限で止まる
        (70, -1, 70),  # 下限で止まる
        (195, 1, 200),  # 刻みからずれていても、上限を超えない
        (75, -1, 70),
        (105, 1, 110),  # 刻みからずれた値は、次の刻みへそろえる
        (105, -1, 100),
        (100, 0, 100),  # 0 は、既定へ戻す
        (150, 0, 100),
    ],
)
def test_step_zoom_moves_by_the_step_and_stays_in_range(current: int, direction: int, expected: int) -> None:
    from projectapp.config import step_zoom

    assert step_zoom(current, direction) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(100, 100), (130, 130), (69, 70), (201, 200), (125.4, 125), (True, None), ("abc", None), (None, None), (1e999, None)],
)
def test_parse_zoom_accepts_numbers_and_clamps(value: object, expected: int | None) -> None:
    from projectapp.config import parse_zoom

    assert parse_zoom(value) == expected


def test_load_zoom_defaults_and_round_trips_keeping_other_keys(tmp_path: Path) -> None:
    from projectapp.config import load_zoom, save_zoom

    assert load_zoom(tmp_path) == 100
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "name_width": 300}), encoding="utf-8")
    save_zoom(130, tmp_path)
    assert load_zoom(tmp_path) == 130
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {
        "theme": "dark",
        "name_width": 300,
        "zoom": 130,
    }


def test_load_zoom_ignores_a_broken_value(tmp_path: Path) -> None:
    from projectapp.config import load_zoom

    (tmp_path / "config.json").write_text(json.dumps({"zoom": "big"}), encoding="utf-8")
    assert load_zoom(tmp_path) == 100
