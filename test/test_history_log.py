"""変更履歴(要望 128)。NiceGUI に依存しない部分。"""

import json
from copy import deepcopy
from datetime import datetime

import pytest

from projectapp.models import Change, HistoryEvent, Project
from projectapp.storage import dumps_project, parse_project

pytestmark = pytest.mark.smoke


def ev(task: str, at: datetime, **fields: tuple) -> HistoryEvent:
    """`ev("a", at, status=("未着手", "実行中"), progress=(None, 30))`。項目は status, progress, effort の順で渡す。"""
    return HistoryEvent(
        task, at, tuple(Change(name, b, a) for name, (b, a) in fields.items())
    )


NOV8 = datetime(2026, 11, 8, 10, 0)


def test_history_round_trips_through_the_file() -> None:
    project = Project(
        "p",
        history=[ev("t1", NOV8, status=("未着手", "実行中"), progress=(None, 30))],
        history_since=datetime(2026, 11, 8, 9, 0),
    )
    loaded = parse_project(dumps_project(project), "p")
    assert loaded.history == project.history
    assert loaded.history_since == project.history_since


def test_a_version_20_file_is_read_without_history() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = 20
    del raw["history"], raw["history_since"]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.history == [] and loaded.history_since is None


@pytest.mark.parametrize(
    "bad",
    [
        {
            "task": "t",
            "at": "2026-11-08T10:00:00",
            "changes": {"status": ["未着手", "x"]},
        },
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"name": ["a", "b"]}},
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {}},
        {
            "task": "t",
            "at": "2026-11-08T10:00:00",
            "changes": {"progress": [None, 101]},
        },
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"effort": [None, -1]}},
        {"task": "", "at": "2026-11-08T10:00:00", "changes": {"progress": [0, 1]}},
        {"task": "t", "at": "not-a-date", "changes": {"progress": [0, 1]}},
        {"task": "t", "changes": {"progress": [0, 1]}},
    ],
)
def test_a_broken_history_entry_is_rejected(bad: dict) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["history"] = [bad]
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_copying_a_project_shares_the_events() -> None:
    event = ev("t1", NOV8, progress=(None, 30))
    assert deepcopy(event) is event
