import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from header_cells import settles, should_see_column
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
    assert recorder.events == [("move_task", (((), 0), ((0,), 1), True))]


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


def test_the_script_has_the_name_width_pieces() -> None:
    assert 'emitEvent("chart_name_width"' in CHART_DRAG_JS
    assert "gantt-name-resizable" in CHART_DRAG_JS
    for name in ("nameMin", "nameMax", "nameDefault", "nameEdge"):
        assert name in CHART_DRAG_JS
    assert "dblclick" in CHART_DRAG_JS


def test_the_resize_css_draws_a_column_resize_handle_of_the_edge_width() -> None:
    from projectapp.gantt_drag import NAME_RESIZE_CSS, RESIZE_EDGE_PX

    assert ".gantt-name-resizable::after" in NAME_RESIZE_CSS
    assert "cursor: col-resize" in NAME_RESIZE_CSS
    assert f"width: {RESIZE_EDGE_PX}px" in NAME_RESIZE_CSS


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
    await settles(user, lambda cells: "2026-10-05" in cells and cells["2026-10-05"][1] is None)  # 描画し直しを待つ
    bar = user.find(marker="bar-0-0").elements.pop()
    assert "data-bar" not in bar.props
    assert bar._style["cursor"] == "pointer"
    charts[0].set_scale(Scale.MONTH)
    await should_see_column(user, "2026-10-01")
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
    assert recorder.events == [("shift_task", ((0,), 0, -2)), ("shift_task", ((), 1, 5))]


async def test_handle_shift_ignores_bad_events_and_other_scales(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 3651})
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 1.5})
    charts[0].handle_shift({"si": "0.", "ti": 0, "days": 1})
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
const area = {  // chart-content。範囲と掴み場所の幅は、data-* 属性で渡される
  dataset: { nameMin: "120", nameMax: "480", nameDefault: "200", nameEdge: "6" },
  vars: { "--name-w": "200px" },
  style: { setProperty(name, value) { area.vars[name] = value; } },
};
global.getComputedStyle = (el) => ({ getPropertyValue: (name) => el.vars[name] });
global.document = {
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  querySelectorAll: () => [],
  querySelector: (selector) => (selector === "[data-chart-content]" ? area : null),
  body: { style: {} },
};
global.emitEvent = (name, message) => emitted.push([name, message]);
global.setTimeout = (fn) => { timers.push(fn); };
global.clearTimeout = () => {};
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

// 名前の欄の幅の調整(右端 6px を掴む)。欄の右端は x=200
const cell = {
  draggable: true,
  style: { width: "var(--name-w)" },
  closest(selector) { return selector === ".gantt-name-resizable" ? this : null; },
  getBoundingClientRect: () => ({ right: 200 }),
  setPointerCapture() {},
};
const other = { draggable: true, style: { width: "var(--name-w)" } };  // 同じ幅の、別の名前の欄
area.querySelectorAll = (selector) => (selector === ".gantt-name-resizable" ? [cell, other] : []);
const edge = (x) => ({ target: cell, button: 0, pointerId: 1, isPrimary: true, clientX: x, buttons: 1, preventDefault() {} });
const variable = () => area.vars["--name-w"];
const widths = () => [cell.style.width, other.style.width];
const escape = () => ({ key: "Escape", stopped: false, stopImmediatePropagation() { this.stopped = true; } });

// 通常: 右端を掴んで 100px 動かす。ドラッグ中は、名前の欄の幅だけが追従し(変数はそのまま)、離したときに変数を 1 回更新する
fire("pointerdown", edge(197)); fire("pointermove", edge(297));
const during = { variable: variable(), widths: widths(), draggable: cell.draggable, cursor: document.body.style.cursor };
fire("pointerup", edge(297));
scenarios.resize = {
  during, emitted: emitted.splice(0), variable: variable(), widths: widths(),
  draggable: cell.draggable, cursor: document.body.style.cursor, suppressed: click(),
};
flush();

// 範囲: 上限と下限で止まる(開始の幅 300 から)
fire("pointerdown", edge(197)); fire("pointermove", edge(1197));
const max = widths()[0];
fire("pointermove", edge(-1803));
const min = widths()[0];
fire("pointerup", edge(-1803));
scenarios.clamp = { max, min, variable: variable(), emitted: emitted.splice(0) };
click(); flush();

// 動かさずに離す: 送らないが、click は打ち消す(編集ダイアログを開かない)。時間が経てば、打ち消さない
fire("pointerdown", edge(197)); fire("pointerup", edge(197));
scenarios.noMove = { emitted: emitted.splice(0), variable: variable(), widths: widths(), suppressed: click() };
flush();
scenarios.clickWindowCloses = click();

// 右端の外: 何も始めない(click も打ち消さない)
fire("pointerdown", edge(100)); fire("pointermove", edge(150)); fire("pointerup", edge(150));
scenarios.outside = { emitted: emitted.splice(0), variable: variable(), widths: widths(), suppressed: click() };
flush();

// 主ボタン・主ポインタ以外は、始めない
fire("pointerdown", { ...edge(197), isPrimary: false }); fire("pointermove", edge(297)); fire("pointerup", edge(297));
scenarios.notPrimary = { emitted: emitted.splice(0), widths: widths(), suppressed: click() };
flush();

// ダブルクリック: 既定の幅に戻して送る(2 回の click は、どちらも打ち消す)
fire("pointerdown", edge(197)); fire("pointerup", edge(197)); const firstClick = click();
fire("pointerdown", edge(197)); fire("pointerup", edge(197)); const secondClick = click();
fire("dblclick", edge(197));
scenarios.reset = { emitted: emitted.splice(0), variable: variable(), clicks: [firstClick, secondClick] };
flush();

// すでに既定の幅なら、ダブルクリックでも、送らない
fire("dblclick", edge(197));
scenarios.resetAlreadyDefault = { emitted: emitted.splice(0), variable: variable() };
flush();

// pointercancel: 名前の欄の幅を元に戻し、何も送らない
fire("pointerdown", edge(197)); fire("pointermove", edge(297)); fire("pointercancel", edge(297));
fire("pointermove", edge(397)); fire("pointerup", edge(397));
scenarios.resizeCancel = { emitted: emitted.splice(0), variable: variable(), widths: widths(), draggable: cell.draggable };
flush();

// ボタンが離れているのに pointermove が来たら、掴んだ状態を捨てる
fire("pointerdown", edge(197)); fire("pointermove", edge(297));
fire("pointermove", { ...edge(397), buttons: 0 });
fire("pointermove", edge(497)); fire("pointerup", edge(497));
scenarios.resizeReleased = { emitted: emitted.splice(0), variable: variable(), widths: widths() };
flush();

// Esc: 元の幅に戻し、送らない。離したあとの click は打ち消す。Esc は、ほかの処理へ渡さない
fire("pointerdown", edge(197)); fire("pointermove", edge(297));
const escapeKey = escape();
fire("keydown", escapeKey);
const afterEscape = widths();
fire("pointermove", edge(397)); fire("pointerup", edge(397));
scenarios.escape = {
  afterEscape, stopped: escapeKey.stopped, emitted: emitted.splice(0), variable: variable(), widths: widths(),
  suppressed: click(),
};
flush();
const idleEscape = escape();
fire("keydown", idleEscape);
scenarios.idleEscapeStopped = idleEscape.stopped;  // 調整中でなければ、Esc は止めない

// 掴んでいる間は、行の移動(HTML5 の drag)を始めない
fire("pointerdown", edge(197));
const dragEvent = { target: cell, prevented: false, preventDefault() { this.prevented = true; } };
fire("dragstart", dragEvent);
scenarios.dragstart = dragEvent.prevented;
fire("pointerup", edge(197)); click(); flush();

// 画面を 150% に拡大(CSS の zoom)しているとき: 画面上の移動量(clientX)を、CSS の px へ戻して計算する
const zoomBar = {
  dataset: { si: "0", ti: "0", dayWidth: "40", minDays: "-5" },
  style: {}, isConnected: true, offsetWidth: 40,
  getBoundingClientRect: () => ({ width: 60 }),
  setPointerCapture() {},
  closest(selector) { return selector === "[data-bar]" ? this : null; },
};
const zoomPointer = (x) => ({ target: zoomBar, button: 0, pointerId: 1, clientX: x, buttons: 1 });
fire("pointerdown", zoomPointer(0)); fire("pointermove", zoomPointer(120));
const zoomDuring = zoomBar.style.transform;  // 画面上の 120px は CSS の 80px = 2日
fire("pointerup", zoomPointer(120));
scenarios.zoomBar = { during: zoomDuring, emitted: emitted.splice(0) };
click(); flush();

cell.offsetWidth = 200;
cell.getBoundingClientRect = () => ({ right: 300, width: 300 });  // 画面上は 300px(CSS の 200px の 1.5 倍)
fire("pointerdown", edge(295)); fire("pointermove", edge(445));  // 掴み場所の幅(6px)も 1.5 倍。150px は CSS の 100px
const zoomResizeDuring = widths()[0];
fire("pointerup", edge(445));
scenarios.zoomResize = { during: zoomResizeDuring, variable: variable(), emitted: emitted.splice(0) };
click(); flush();
fire("pointerdown", edge(285));  // 画面上 15px の内側は、掴み場所の外(CSS では 10px)
scenarios.zoomOutsideEdge = { widths: widths(), emitted: emitted.splice(0) };
fire("pointerup", edge(285));

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


def test_js_resizing_moves_the_name_cells_live_and_updates_the_variable_once_on_release(
    js_scenarios: dict,
) -> None:
    resize = js_scenarios["resize"]
    # ドラッグ中は、名前の欄の幅だけを直接動かす(変数を動かすと、約 1,800 要素のスタイルを再計算して、カクつく)
    assert resize["during"] == {
        "variable": "200px",
        "widths": ["300px", "300px"],
        "draggable": False,  # 欄の drag は止める
        "cursor": "col-resize",
    }
    assert resize["emitted"] == [["chart_name_width", {"width": 300}]]
    assert resize["variable"] == "300px"  # 離したときに、変数を 1 回だけ更新する
    assert resize["widths"] == ["var(--name-w)", "var(--name-w)"]  # 直接の幅をやめ、変数に任せる
    assert resize["draggable"] is True  # 離したら、欄の drag を戻す
    assert resize["cursor"] == ""
    assert resize["suppressed"] is True  # 離したあとの click で、編集ダイアログを開かない


def test_js_the_width_stops_at_the_range_limits(js_scenarios: dict) -> None:
    clamp = js_scenarios["clamp"]
    assert (clamp["max"], clamp["min"]) == ("480px", "120px")
    assert clamp["variable"] == "120px"
    assert clamp["emitted"] == [["chart_name_width", {"width": 120}]]


def test_js_releasing_without_moving_sends_nothing_but_swallows_the_click(js_scenarios: dict) -> None:
    assert js_scenarios["noMove"] == {
        "emitted": [],
        "variable": "120px",
        "widths": ["var(--name-w)", "var(--name-w)"],
        "suppressed": True,
    }


def test_js_the_click_window_after_a_resize_closes(js_scenarios: dict) -> None:
    # 打ち消すのは、離した直後の短い間だけ(次の、ふつうの click まで巻き込まない)
    assert js_scenarios["clickWindowCloses"] is False


def test_js_outside_the_right_edge_nothing_starts(js_scenarios: dict) -> None:
    assert js_scenarios["outside"] == {
        "emitted": [],
        "variable": "120px",
        "widths": ["var(--name-w)", "var(--name-w)"],
        "suppressed": False,
    }


def test_js_a_non_primary_pointer_does_not_start_a_resize(js_scenarios: dict) -> None:
    assert js_scenarios["notPrimary"] == {
        "emitted": [],
        "widths": ["var(--name-w)", "var(--name-w)"],
        "suppressed": False,
    }


def test_js_double_clicking_the_edge_resets_to_the_default_width(js_scenarios: dict) -> None:
    reset = js_scenarios["reset"]
    assert reset["emitted"] == [["chart_name_width", {"width": 200}]]
    assert reset["variable"] == "200px"
    assert reset["clicks"] == [True, True]  # 2 回の click は、どちらも編集を開かない


def test_js_double_clicking_at_the_default_width_sends_nothing(js_scenarios: dict) -> None:
    assert js_scenarios["resetAlreadyDefault"] == {"emitted": [], "variable": "200px"}


def test_js_pointercancel_restores_the_cells_without_sending(js_scenarios: dict) -> None:
    assert js_scenarios["resizeCancel"] == {
        "emitted": [],
        "variable": "200px",
        "widths": ["var(--name-w)", "var(--name-w)"],
        "draggable": True,
    }


def test_js_a_pointermove_without_buttons_drops_the_resize(js_scenarios: dict) -> None:
    assert js_scenarios["resizeReleased"] == {
        "emitted": [],
        "variable": "200px",
        "widths": ["var(--name-w)", "var(--name-w)"],
    }


def test_js_escape_restores_the_widths_and_still_swallows_the_click(js_scenarios: dict) -> None:
    assert js_scenarios["escape"] == {
        "afterEscape": ["var(--name-w)", "var(--name-w)"],
        "stopped": True,  # ほかの Esc の処理(プレビューを閉じるなど)へ渡さない
        "emitted": [],
        "variable": "200px",
        "widths": ["var(--name-w)", "var(--name-w)"],
        "suppressed": True,
    }


def test_js_escape_is_not_stopped_when_no_resize_is_in_progress(js_scenarios: dict) -> None:
    assert js_scenarios["idleEscapeStopped"] is False


def test_js_the_row_drag_does_not_start_while_resizing(js_scenarios: dict) -> None:
    assert js_scenarios["dragstart"] is True


async def test_min_days_stops_at_the_predecessors_finish(user: User) -> None:
    a = Task("先行", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=13)
    b = Task(
        "後続",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 12, 9),
        effort_hours=1,
        predecessors=["aaaaaaaa"],
    )
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [a, b])]))
    await user.open("/")
    # 先行の完了は火曜(10/6)の 15:30。後続の開始 10/12 から 10/6 まで -6 日
    assert props_of(user, "bar-0-1")["data-min-days"] == "-6"


def test_a_zoomed_page_converts_pointer_distances_back_to_css_pixels(js_scenarios: dict) -> None:
    assert js_scenarios["zoomBar"]["during"] == "translateX(80px)"
    assert js_scenarios["zoomBar"]["emitted"] == [["chart_shift", {"si": 0, "ti": 0, "days": 2}]]
    assert js_scenarios["zoomResize"]["during"] == "300px"
    assert js_scenarios["zoomResize"]["variable"] == "300px"
    assert js_scenarios["zoomResize"]["emitted"] == [["chart_name_width", {"width": 300}]]
    assert js_scenarios["zoomOutsideEdge"]["emitted"] == []
