import json
import os
from pathlib import Path

import pytest

from projectapp.config import (
    DEFAULT_NAME_WIDTH_PX,
    MAX_NAME_WIDTH_PX,
    MIN_NAME_WIDTH_PX,
    PROJECT_DIR_MISSING_MESSAGE,
    check_project_dir,
    load_custom_theme,
    load_name_width,
    load_project_dir,
    load_theme,
    parse_name_width,
    resolve_project_dir,
    save_custom_theme,
    save_name_width,
    save_project_dir,
    save_theme,
)

from projectapp.theme import DEFAULTS, CustomTheme


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


def test_the_task_layout_defaults_to_all(tmp_path: Path) -> None:
    from projectapp.config import load_task_layout

    assert load_task_layout(tmp_path) == "all"


def test_the_task_layout_round_trips_and_keeps_other_keys(tmp_path: Path) -> None:
    from projectapp.config import load_task_layout, load_zoom, save_task_layout, save_zoom

    save_zoom(120, tmp_path)
    save_task_layout("schedule", tmp_path)
    assert load_task_layout(tmp_path) == "schedule"
    assert load_zoom(tmp_path) == 120


@pytest.mark.parametrize("value", ["x", 1, None, True, ["all"]])
def test_an_invalid_task_layout_falls_back_to_all(tmp_path: Path, value: object) -> None:
    from projectapp.config import load_task_layout

    (tmp_path / "config.json").write_text(json.dumps({"task_layout": value}), encoding="utf-8")
    assert load_task_layout(tmp_path) == "all"


def test_project_dir_is_unset_by_default(tmp_path: Path) -> None:
    assert load_project_dir(tmp_path) is None


def test_project_dir_round_trips_and_keeps_the_other_keys(tmp_path: Path) -> None:
    save_theme("dark", tmp_path)
    folder = tmp_path / "shared"
    save_project_dir(folder, tmp_path)
    assert load_project_dir(tmp_path) == folder
    assert load_theme(tmp_path) == "dark"
    save_theme("light", tmp_path)  # ほかの設定を保存しても、格納先は消えない
    assert load_project_dir(tmp_path) == folder


@pytest.mark.parametrize("value", [None, "", "   ", 5, ["x"], "relative/dir"])
def test_an_invalid_project_dir_is_read_as_unset(tmp_path: Path, value: object) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"project_dir": value}), encoding="utf-8")
    assert load_project_dir(tmp_path) is None


def test_project_dir_expands_the_home_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / "config.json").write_text(json.dumps({"project_dir": "~/shared"}), encoding="utf-8")
    assert load_project_dir(tmp_path) == tmp_path / "shared"


def test_check_project_dir_accepts_an_existing_folder_even_if_empty(tmp_path: Path) -> None:
    assert check_project_dir(tmp_path) is None


def test_check_project_dir_rejects_a_missing_folder(tmp_path: Path) -> None:
    assert check_project_dir(tmp_path / "ない") == "フォルダが見つかりません"


def test_check_project_dir_rejects_a_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    assert check_project_dir(target) == "フォルダではありません"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="権限を外せない環境")
def test_check_project_dir_rejects_a_folder_that_cannot_be_written(tmp_path: Path) -> None:
    folder = tmp_path / "ro"
    folder.mkdir()
    folder.chmod(0o555)
    try:
        assert check_project_dir(folder) == "書き込めません"
    finally:
        folder.chmod(0o755)


def test_check_project_dir_does_not_create_files(tmp_path: Path) -> None:
    check_project_dir(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_resolve_project_dir_is_the_config_folder_when_unset(tmp_path: Path) -> None:
    assert resolve_project_dir(tmp_path) == (tmp_path, None)


def test_resolve_project_dir_uses_a_saved_usable_folder(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    save_project_dir(shared, tmp_path)
    assert resolve_project_dir(tmp_path) == (shared, None)


def test_resolve_project_dir_falls_back_without_touching_the_config(tmp_path: Path) -> None:
    missing = tmp_path / "ない"
    save_project_dir(missing, tmp_path)
    assert resolve_project_dir(tmp_path) == (tmp_path, PROJECT_DIR_MISSING_MESSAGE)
    assert load_project_dir(tmp_path) == missing  # 設定は残す(ドライブをつなぎ直せば戻る)


def test_theme_accepts_custom(tmp_path: Path) -> None:
    save_theme("custom", tmp_path)
    assert load_theme(tmp_path) == "custom"


def test_custom_theme_defaults_to_light_when_missing(tmp_path: Path) -> None:
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]
    (tmp_path / "config.json").write_text(json.dumps({"theme": "custom"}), encoding="utf-8")
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]


@pytest.mark.parametrize("raw", [[], "dark", 3, None, True])
def test_custom_theme_that_is_not_an_object_reads_as_the_default(tmp_path: Path, raw: object) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"custom_theme": raw}), encoding="utf-8")
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]


def test_save_custom_theme_round_trips_and_keeps_other_keys(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "name_width": 300, "other": 1}), encoding="utf-8")
    theme = CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0")
    save_custom_theme(theme, tmp_path)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["theme"] == "dark" and saved["name_width"] == 300 and saved["other"] == 1
    assert load_custom_theme(tmp_path) == theme


def test_save_custom_theme_with_select_also_sets_the_theme(tmp_path: Path) -> None:
    save_custom_theme(DEFAULTS["dark"], tmp_path, select=True)
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path) == DEFAULTS["dark"]


def test_saving_the_theme_keeps_the_custom_colors(tmp_path: Path) -> None:
    save_custom_theme(DEFAULTS["dark"], tmp_path, select=True)
    save_theme("light", tmp_path)
    assert load_custom_theme(tmp_path) == DEFAULTS["dark"]
