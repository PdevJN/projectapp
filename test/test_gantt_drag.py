import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.filtering import TaskFilter
from projectapp.gantt import GanttChart
from projectapp.gantt_drag import CHART_DRAG_JS
from projectapp.models import Project, Section, Task
from test_gantt import BASE, Recorder


def project_with_top() -> Project:
    return Project(
        "demo",
        base_date=BASE,
        tasks=[Task("上1"), Task("上2")],
        sections=[
            Section("開発", [Task("設計", planned_start=datetime(2026, 10, 5, 9))]),
            Section("空", []),
        ],
    )


def mount(project: Project) -> tuple[Recorder, list[GanttChart]]:
    recorder = Recorder()
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, recorder.actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    return recorder, charts


def props_of(user: User, marker: str) -> dict:
    return user.find(marker=marker).elements.pop().props


async def test_task_labels_are_draggable_handles_and_rows_are_drop_targets(user: User) -> None:
    mount(project_with_top())
    await user.open("/")
    label = props_of(user, "task-top-1")
    assert label["draggable"] == "true"
    assert "data-drag-handle" in label
    assert (label["data-si"], label["data-ti"]) == ("top", "1")
    label = props_of(user, "task-0-0")
    assert (label["data-si"], label["data-ti"]) == ("0", "0")
    row = props_of(user, "row-0-0")
    assert row["data-drop"] == "row"
    assert (row["data-si"], row["data-ti"]) == ("0", "0")


async def test_section_headers_and_the_top_add_row_are_drop_targets_with_counts(
    user: User,
) -> None:
    mount(project_with_top())
    await user.open("/")
    section = props_of(user, "section-1")
    assert section["data-drop"] == "section"
    assert (section["data-si"], section["data-count"]) == ("1", "0")
    assert props_of(user, "section-0")["data-count"] == "1"
    top = props_of(user, "top-end")
    assert top["data-drop"] == "top-end"
    assert (top["data-si"], top["data-count"]) == ("top", "2")


async def test_no_drag_attributes_while_filtering(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="上"))
    await user.should_not_see(marker="task-0-0")  # 描画し直しを待つ
    label = props_of(user, "task-top-0")
    assert "draggable" not in label
    assert "data-drag-handle" not in label
    assert "data-drop" not in props_of(user, "row-top-0")
    assert "data-drop" not in props_of(user, "top-end")


async def test_handle_move_passes_valid_events_to_the_action(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_move({"src": [None, 0], "dst": [0, 1], "copy": True})
    assert recorder.events == [("move_task", ((None, 0), (0, 1), True))]


async def test_handle_move_ignores_bad_events_and_filtering(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_move({"src": "x", "dst": [0, 1], "copy": True})
    charts[0].handle_move({"src": [None, 0], "dst": [0, 1], "copy": "yes"})
    charts[0].handle_move(None)
    charts[0].set_filter(TaskFilter(query="上"))
    charts[0].handle_move({"src": [None, 0], "dst": [0, 1], "copy": False})
    assert recorder.events == []


def test_the_script_is_valid_javascript(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので構文を確かめない")
    script = tmp_path / "drag.js"
    script.write_text(CHART_DRAG_JS, encoding="utf-8")
    result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_script_emits_the_events_the_python_side_listens_to() -> None:
    assert 'emitEvent("chart_move"' in CHART_DRAG_JS
