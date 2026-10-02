from datetime import datetime

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.forms import (
    build_section_name,
    build_task,
    open_section_dialog,
    open_task_dialog,
    parse_datetime,
)
from projectapp.models import Priority, Status, Task


def make(existing: Task | None = None, **overrides: object) -> Task:
    values: dict[str, object] = {
        "name": "設計",
        "start": "2026-10-05T09:00",
        "end": "2026-10-07T18:00",
        "effort_hours": 8.0,
        "priority": Priority.HIGH,
        "status": Status.RUNNING,
        "color": "#112233",
        "assignee": "",
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]


def test_build_task_normalizes_input() -> None:
    task = make(name="  設計  ", assignee=" 佐藤 ")
    assert task.name == "設計"
    assert task.start == datetime(2026, 10, 5, 9, 0)
    assert task.end == datetime(2026, 10, 7, 18, 0)
    assert task.effort_hours == 8.0
    assert task.assignee == "佐藤"


def test_blank_assignee_and_dates_become_none() -> None:
    task = make(start="", end="", assignee="  ", effort_hours=None)
    assert (task.start, task.end, task.assignee, task.effort_hours) == (None, None, None, 0.0)


@pytest.mark.parametrize("name", ["", "   ", "　"])
def test_blank_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="名前"):
        make(name=name)


def test_end_before_start_is_rejected_but_equal_is_allowed() -> None:
    with pytest.raises(ValueError, match="終了"):
        make(start="2026-10-07T09:00", end="2026-10-05T09:00")
    assert make(start="2026-10-05T09:00", end="2026-10-05T09:00").name == "設計"


@pytest.mark.parametrize(
    "text", ["abc", "2026-13-01T00:00", "2026-10-05T09:00+09:00", "2026-10-05T09:00Z"]
)
def test_bad_or_timezone_aware_datetime_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="形式"):
        make(start=text)


@pytest.mark.parametrize("text", ["0026-10-05T09:00", "1999-12-31T23:59", "2101-01-01T00:00", "2926-10-05T09:00"])
def test_year_outside_range_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="年"):
        make(start=text, end="")
    with pytest.raises(ValueError, match="年"):
        make(start="", end=text)


def test_year_boundaries_are_accepted() -> None:
    task = make(start="2000-01-01T00:00", end="2100-12-31T23:59")
    assert task.start == datetime(2000, 1, 1)
    assert task.end == datetime(2100, 12, 31, 23, 59)


def test_negative_effort_is_rejected() -> None:
    with pytest.raises(ValueError, match="工数"):
        make(effort_hours=-1.0)


def test_editing_keeps_fields_not_in_the_form() -> None:
    existing = Task("旧", predecessors=["x"])
    edited = make(existing)
    assert edited.predecessors == ["x"]
    assert existing.name == "旧"


def test_parse_datetime_accepts_date_only() -> None:
    assert parse_datetime("2026-10-05") == datetime(2026, 10, 5)


def test_build_section_name() -> None:
    assert build_section_name(" 開発 ") == "開発"
    with pytest.raises(ValueError, match="名前"):
        build_section_name("  ")


async def test_task_dialog_saves_a_valid_task(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start").type("2026-10-05T09:00")
    user.find(marker="task-end").type("2026-10-07T18:00")
    user.find(marker="task-save").click()
    assert [t.name for t in saved] == ["設計"]
    assert saved[0].end == datetime(2026, 10, 7, 18, 0)


async def test_task_dialog_shows_error_and_does_not_save(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-save").click()
    await user.should_see("名前を入力してください")
    assert saved == []


async def test_task_dialog_prefills_when_editing(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        task = Task("既存", start=datetime(2026, 10, 5, 9), end=datetime(2026, 10, 6, 9))
        ui.button("open", on_click=lambda: open_task_dialog(task, lambda t: None))

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="task-name").elements.pop().value == "既存"
    assert user.find(marker="task-start").elements.pop().value == "2026-10-05T09:00"


async def test_section_dialog(user: User) -> None:
    saved: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_section_dialog(saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="section-save").click()
    await user.should_see("名前を入力してください")
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    assert saved == ["開発"]
