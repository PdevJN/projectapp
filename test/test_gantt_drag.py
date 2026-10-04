import json
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
from projectapp.timeline import Scale
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


async def test_day_scale_bars_are_draggable_with_the_column_width(user: User) -> None:
    mount(project_with_top())
    await user.open("/")
    bar = props_of(user, "bar-0-0")
    assert "data-bar" in bar
    assert (bar["data-si"], bar["data-ti"], bar["data-day-width"]) == ("0", "0", "40")
    assert bar["data-min-days"] == "0"  # 開始が基準日(10/5)なので、左へは動かせない
    style = user.find(marker="bar-0-0").elements.pop()._style
    assert style["cursor"] == "grab"


async def test_other_scales_have_no_draggable_bars(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_scale(Scale.WEEK)
    await user.should_not_see(marker="weekday-2026-10-05")  # 描画し直しを待つ
    bar = user.find(marker="bar-0-0").elements.pop()
    assert "data-bar" not in bar.props
    assert bar._style["cursor"] == "pointer"
    charts[0].set_scale(Scale.MONTH)
    await user.should_see(marker="col-2026-10-01")
    assert "data-bar" not in props_of(user, "bar-0-0")


async def test_bars_stay_draggable_while_filtering(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="task-top-0")  # 描画し直しを待つ
    assert "data-bar" in props_of(user, "bar-0-0")


async def test_handle_shift_passes_valid_events_on_the_day_scale(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_shift({"si": 0, "ti": 0, "days": -2})
    charts[0].handle_shift({"si": None, "ti": 1, "days": 5})
    assert recorder.events == [("shift_task", (0, 0, -2)), ("shift_task", (None, 1, 5))]


async def test_handle_shift_ignores_bad_events_and_other_scales(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 3651})
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 1.5})
    charts[0].handle_shift({"si": "0", "ti": 0, "days": 1})
    charts[0].handle_shift(None)
    charts[0].set_scale(Scale.WEEK)
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 1})
    assert recorder.events == []


def test_the_script_has_the_bar_drag_pieces() -> None:
    assert 'emitEvent("chart_shift"' in CHART_DRAG_JS
    assert "pointerdown" in CHART_DRAG_JS
    assert "Escape" in CHART_DRAG_JS
    assert "minDays" in CHART_DRAG_JS


# --- JS の状態機械を、偽の document で実際に動かす(Node がなければ skip) ---

HARNESS = r"""
const fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const emitted = [];
const timers = [];
global.window = {};
global.document = {
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  querySelectorAll: () => [],
};
global.emitEvent = (name, message) => emitted.push([name, message]);
global.setTimeout = (fn) => { timers.push(fn); };
eval(code);
const fire = (type, event) => (listeners[type] || []).forEach((fn) => fn(event));
const bar = {
  dataset: { si: "0", ti: "0", dayWidth: "40", minDays: "-5" },
  style: {},
  isConnected: true,
  setPointerCapture() {},
  closest(selector) { return selector === "[data-bar]" ? this : null; },
};
const pointer = (x) => ({ target: bar, button: 0, pointerId: 1, clientX: x, buttons: 1 });
const scenarios = {};

const click = () => {
  const event = { stopped: false, stopPropagation() { this.stopped = true; }, preventDefault() {} };
  fire("click", event);
  return event.stopped;
};
const flush = () => timers.splice(0).forEach((fn) => fn());

// 通常の移動(100px = 3日に吸着)
fire("pointerdown", pointer(0)); fire("pointermove", pointer(100)); fire("pointerup", pointer(100));
scenarios.normal = { emitted: emitted.splice(0), transform: bar.style.transform, suppressed: click() };
// 再描画で要素が置き換わるまで位置を保ち(元に戻って見えないように)、残っていたら保険で戻す
scenarios.afterUp = bar.style.transform;
flush();
scenarios.afterTimeout = bar.style.transform;

// 再描画で要素が置き換わったなら、古い要素には触らない
bar.style.transform = "";
fire("pointerdown", pointer(0)); fire("pointermove", pointer(100)); fire("pointerup", pointer(100));
bar.isConnected = false; bar.style.transform = "kept";
flush();
scenarios.replaced = bar.style.transform;
bar.isConnected = true; bar.style.transform = "";
emitted.splice(0); click();

// 0日のままなら、送らずにすぐ戻す
fire("pointerdown", pointer(0)); fire("pointermove", pointer(10)); fire("pointerup", pointer(10));
scenarios.zero = { emitted: emitted.splice(0), transform: bar.style.transform };
click(); flush();

// pointercancel のあとは、動かしても放しても何も送らず、バーを戻す
fire("pointerdown", pointer(0)); fire("pointermove", pointer(100));
fire("pointercancel", pointer(100));
fire("pointermove", pointer(200)); fire("pointerup", pointer(200));
scenarios.cancel = { emitted: emitted.splice(0), transform: bar.style.transform };

// ボタンが離れているのに pointermove が来たら、つかんだ状態を捨てる
fire("pointerdown", pointer(0)); fire("pointermove", pointer(100));
fire("pointermove", { ...pointer(200), buttons: 0 });
fire("pointermove", pointer(300)); fire("pointerup", pointer(300));
scenarios.released = { emitted: emitted.splice(0), transform: bar.style.transform };

// 動かす前に Esc → クリックとして扱う(打ち消さない)
fire("pointerdown", pointer(0)); fire("keydown", { key: "Escape" }); fire("pointerup", pointer(0));
scenarios.escapeBeforeMove = { emitted: emitted.splice(0), suppressed: click() };
flush();

// 動かしている途中で Esc → 送らず、そのあとの click は打ち消す
fire("pointerdown", pointer(0)); fire("pointermove", pointer(100)); fire("keydown", { key: "Escape" });
fire("pointerup", pointer(100));
scenarios.escapeAfterMove = { emitted: emitted.splice(0), suppressed: click() };
flush();

// 行の drag: 自分が始めた drag でないもの(外から持ち込んだ物)の drop は無視する
const handle = { dataset: { si: "top", ti: "1" }, textContent: "x", closest(s) { return s === "[data-drag-handle]" ? this : null; } };
const row = { dataset: { drop: "row", si: "0", ti: "0" }, classList: { add() {} }, getBoundingClientRect: () => ({ top: 0, height: 10 }), closest(s) { return s === "[data-drop]" ? this : null; } };
const transfer = { types: [], setData(type) { this.types.push(type); } };
fire("dragstart", { target: handle, dataTransfer: transfer });
const drop = (types) => { fire("drop", { target: row, clientY: 1, altKey: true, dataTransfer: { types }, preventDefault() {} }); return emitted.splice(0); };
scenarios.foreignDrop = drop(["Files"]);
fire("dragstart", { target: handle, dataTransfer: transfer });
scenarios.ownDrop = drop(transfer.types);

console.log(JSON.stringify(scenarios));
"""


@pytest.fixture(scope="module")
def js_scenarios(tmp_path_factory: pytest.TempPathFactory) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので JS の動作を確かめない")
    directory = tmp_path_factory.mktemp("js")
    (directory / "drag.js").write_text(CHART_DRAG_JS, encoding="utf-8")
    (directory / "harness.js").write_text(HARNESS, encoding="utf-8")
    result = subprocess.run(
        [node, str(directory / "harness.js"), str(directory / "drag.js")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_js_normal_shift_emits_the_snapped_days_and_swallows_the_click(js_scenarios: dict) -> None:
    normal = js_scenarios["normal"]
    assert normal["emitted"] == [["chart_shift", {"si": 0, "ti": 0, "days": 3}]]
    assert normal["suppressed"] is True


def test_js_the_bar_keeps_its_place_until_the_redraw_then_a_fallback_resets_it(
    js_scenarios: dict,
) -> None:
    assert js_scenarios["afterUp"] == "translateX(120px)"
    assert js_scenarios["afterTimeout"] == ""
    assert js_scenarios["replaced"] == "kept"  # 置き換わった古い要素には触らない


def test_js_a_zero_day_move_goes_back_at_once_without_sending(js_scenarios: dict) -> None:
    assert js_scenarios["zero"] == {"emitted": [], "transform": ""}


def test_js_pointercancel_releases_the_bar_without_sending(js_scenarios: dict) -> None:
    assert js_scenarios["cancel"] == {"emitted": [], "transform": ""}


def test_js_a_pointermove_without_buttons_drops_the_grab(js_scenarios: dict) -> None:
    assert js_scenarios["released"] == {"emitted": [], "transform": ""}


def test_js_escape_before_moving_is_still_a_click(js_scenarios: dict) -> None:
    assert js_scenarios["escapeBeforeMove"] == {"emitted": [], "suppressed": False}


def test_js_escape_after_moving_sends_nothing_and_swallows_the_click(js_scenarios: dict) -> None:
    assert js_scenarios["escapeAfterMove"] == {"emitted": [], "suppressed": True}


def test_js_a_drop_that_did_not_start_from_a_row_is_ignored(js_scenarios: dict) -> None:
    assert js_scenarios["foreignDrop"] == []
    assert js_scenarios["ownDrop"] == [
        ["chart_move", {"src": [None, 1], "dst": [0, 0], "copy": True}]
    ]
