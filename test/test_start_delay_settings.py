"""着工遅れの設定(要望 161): 既定値・保存と読み込み・古いファイル・不正な値。"""

import json

import pytest

from projectapp.models import (
    DEFAULT_START_DELAY_COLOR,
    FORMAT_VERSION,
    MAX_START_DELAY_GRACE,
    Project,
    StartDelaySettings,
    StartDelayStyle,
)
from projectapp.storage import dumps_project, parse_project


def test_the_defaults_show_everything_with_no_grace() -> None:
    project = Project("p")
    assert project.start_delay == StartDelaySettings(
        enabled=True, style=StartDelayStyle.BOTH, grace=0, color="#7e57c2"
    )
    assert DEFAULT_START_DELAY_COLOR == "#7e57c2"
    assert MAX_START_DELAY_GRACE == 30


def test_the_format_version_is_24() -> None:
    assert FORMAT_VERSION == 24


def test_the_settings_round_trip() -> None:
    project = Project(
        "p",
        start_delay_enabled=False,
        start_delay_style=StartDelayStyle.CHIP,
        start_delay_grace=3,
        start_delay_color="#112233",
    )
    raw = json.loads(dumps_project(project))
    assert raw["version"] == 24
    assert raw["start_delay_enabled"] is False
    assert raw["start_delay_style"] == "chip"
    assert raw["start_delay_grace"] == 3
    assert raw["start_delay_color"] == "#112233"
    loaded = parse_project(dumps_project(project), "p")
    assert loaded.start_delay == project.start_delay


def test_an_old_file_without_the_keys_gets_the_defaults() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = 23
    for key in (
        "start_delay_enabled",
        "start_delay_style",
        "start_delay_grace",
        "start_delay_color",
    ):
        del raw[key]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.start_delay == StartDelaySettings()
    assert json.loads(dumps_project(loaded))["version"] == 24


def test_the_color_is_stored_in_lower_case() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["start_delay_color"] = "#AABBCC"
    assert parse_project(json.dumps(raw), "p").start_delay_color == "#aabbcc"


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("start_delay_enabled", "yes"),
        ("start_delay_enabled", 1),
        ("start_delay_style", "stripe"),
        ("start_delay_style", None),
        ("start_delay_grace", -1),
        ("start_delay_grace", 31),
        ("start_delay_grace", 1.5),
        ("start_delay_grace", True),
        ("start_delay_color", "purple"),
        ("start_delay_color", "#12345"),
        ("start_delay_color", ""),
    ],
)
def test_a_bad_value_is_rejected(key: str, bad: object) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw[key] = bad
    with pytest.raises(ValueError, match="着工遅れ"):
        parse_project(json.dumps(raw), "p")
