from projectapp.assign_drag import (
    ASSIGN_DRAG_CSS,
    ASSIGN_DRAG_JS,
    ASSIGN_DROP_EVENT,
    ASSIGN_SELECT_EVENT,
)


def test_the_drag_js_uses_its_own_data_transfer_type_and_event() -> None:
    assert "application/x-assign-member" in ASSIGN_DRAG_JS
    assert "application/x-dashboard-card" not in ASSIGN_DRAG_JS
    assert f'emitEvent("{ASSIGN_DROP_EVENT}"' in ASSIGN_DRAG_JS
    assert (
        "data-assign-member" in ASSIGN_DRAG_JS and "data-assign-cell" in ASSIGN_DRAG_JS
    )


def test_the_drag_js_installs_only_once_and_ignores_foreign_drags() -> None:
    assert "__assignDragInstalled" in ASSIGN_DRAG_JS
    assert "isOurs" in ASSIGN_DRAG_JS


def test_the_css_marks_the_cell_under_the_pointer() -> None:
    assert ".assign-drop-over" in ASSIGN_DRAG_CSS


def test_the_drag_js_emits_the_drop_with_name_week_and_day(tmp_path) -> None:
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので動きを確かめない")
    script = tmp_path / "sim.js"
    script.write_text(
        """
const listeners = {};
const emitted = [];
const classes = new Set();
global.window = {};
global.document = {
  addEventListener: (type, fn) => { listeners[type] = fn; },
  querySelectorAll: () => [{ classList: { remove: (c) => classes.delete(c) } }],
};
global.emitEvent = (name, msg) => emitted.push([name, msg]);
%s
const chip = { dataset: { assignMember: "鈴木" } };
const mk = (selector, el) => ({ closest: (s) => (s.includes(selector) ? el : null) });
const types = ["application/x-assign-member"];
const store = {};
const dt = { types, setData: (t, v) => { store[t] = v; }, effectAllowed: "" };
listeners.dragstart({ target: mk("data-assign-member", chip), dataTransfer: dt });
const cell = { dataset: { week: "2", day: "3" }, classList: { add: (c) => classes.add(c) } };
let prevented = false;
listeners.dragover({ target: mk("data-assign-cell", cell), dataTransfer: dt, preventDefault: () => { prevented = true; } });
listeners.drop({ target: mk("data-assign-cell", cell), dataTransfer: dt, preventDefault: () => {} });
// 別の種類の drag は無視する
const foreign = { types: ["application/x-dashboard-card"] };
listeners.drop({ target: mk("data-assign-cell", cell), dataTransfer: foreign, preventDefault: () => {} });
console.log(JSON.stringify({ emitted, prevented }));
"""
        % ASSIGN_DRAG_JS,
        encoding="utf-8",
    )
    result = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["prevented"] is True
    assert out["emitted"] == [
        ["assign_drop_member", {"name": "鈴木", "week": 2, "day": 3}]
    ]


def test_the_select_js_emits_its_own_event_and_the_css_marks_the_selection() -> None:
    assert ASSIGN_SELECT_EVENT == "assign_select_range"
    assert f'emitEvent("{ASSIGN_SELECT_EVENT}"' in ASSIGN_DRAG_JS
    assert ".assign-select-over" in ASSIGN_DRAG_CSS
    assert ".assign-selected" in ASSIGN_DRAG_CSS


def test_the_select_js_emits_the_range_swiped_across_cells(tmp_path) -> None:
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので動きを確かめない")
    script = tmp_path / "sim_select.js"
    script.write_text(
        """
const listeners = {};
const emitted = [];
global.window = {};
const mkCell = (week, day) => {
  const set = new Set();
  return { dataset: day === null ? { week: String(week) } : { week: String(week), day: String(day) },
           classList: { add: (c) => set.add(c), remove: (c) => set.delete(c), has: (c) => set.has(c) },
           set };
};
const cells = [mkCell(0, null), mkCell(1, 0), mkCell(1, 1), mkCell(1, 2), mkCell(2, null)];
global.document = {
  addEventListener: (type, fn) => { listeners[type] = fn; },
  querySelectorAll: (selector) =>
    selector === "[data-assign-cell]" ? cells : cells.filter((c) => c.set.has("assign-select-over")),
};
global.emitEvent = (name, msg) => emitted.push([name, msg]);
%s
// event.target.closest(selector) が、含まれる祖先(または自分)を返す形の模擬
const at = (cell, extra) => ({ closest: (s) => {
  if (extra && extra.some((e) => s.includes(e))) return {};
  return s.includes("data-assign-cell") ? cell : null;
} });
const down = (cell, extra) => listeners.mousedown({ button: 0, target: at(cell, extra) });
const over = (cell) => listeners.mouseover({ target: at(cell) });
const up = (cell) => listeners.mouseup({ target: at(cell) });

// 1) 週 0 から日 (1,2) までなぞる
down(cells[0]); over(cells[1]); over(cells[2]); over(cells[3]);
const marked = cells.filter((c) => c.set.has("assign-select-over")).length;
up(cells[3]);
const afterUp = cells.filter((c) => c.set.has("assign-select-over")).length;
// 2) 同じセルのクリックだけでは選ばない
down(cells[4]); up(cells[4]);
// 3) チップの上から始めたなぞりは選ばない
down(cells[0], [".assign-chip"]); over(cells[2]); up(cells[2]);
// 4) セルの外で離したときは選ばない
down(cells[0]); over(cells[1]); listeners.mouseup({ target: { closest: () => null } });
// 5) 右から左へなぞる
down(cells[4]); over(cells[2]); up(cells[2]);
console.log(JSON.stringify({ emitted, marked, afterUp }));
"""
        % ASSIGN_DRAG_JS,
        encoding="utf-8",
    )
    result = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["marked"] == 4  # (0) (1,0) (1,1) (1,2)
    assert out["afterUp"] == 0  # 離したら色を外す
    assert out["emitted"] == [
        [
            ASSIGN_SELECT_EVENT,
            {"first": {"week": 0, "day": None}, "last": {"week": 1, "day": 2}},
        ],
        [
            ASSIGN_SELECT_EVENT,
            {"first": {"week": 2, "day": None}, "last": {"week": 1, "day": 1}},
        ],
    ]


def test_the_select_css_also_has_the_webkit_prefix() -> None:
    assert "-webkit-user-select: none" in ASSIGN_DRAG_CSS  # WKWebView(ネイティブ表示)用


def test_a_swipe_ends_when_the_mouse_up_was_missed(tmp_path) -> None:
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので動きを確かめない")
    script = tmp_path / "sim_cancel.js"
    script.write_text(
        """
const listeners = {};
const emitted = [];
global.window = {};
const mkCell = (week) => {
  const set = new Set();
  return { dataset: { week: String(week) },
           classList: { add: (c) => set.add(c), remove: (c) => set.delete(c) }, set };
};
const cells = [mkCell(0), mkCell(1), mkCell(2)];
global.document = {
  addEventListener: (type, fn) => { listeners[type] = fn; },
  querySelectorAll: (selector) =>
    selector === "[data-assign-cell]" ? cells : cells.filter((c) => c.set.has("assign-select-over")),
};
global.emitEvent = (name, msg) => emitted.push([name, msg]);
%s
const at = (cell) => ({ closest: (s) => (s.includes("data-assign-cell") ? cell : null) });
// ボタンを押していない mouseover(mouseup を取り逃がした)で、なぞりが終わる
listeners.mousedown({ button: 0, target: at(cells[0]) });
listeners.mouseover({ buttons: 1, target: at(cells[1]) });
listeners.mouseover({ buttons: 0, target: at(cells[2]) });
const marked = cells.filter((c) => c.set.has("assign-select-over")).length;
listeners.mouseup({ target: at(cells[2]) });
// contextmenu(Ctrl+クリック)でも終わる
listeners.mousedown({ button: 0, target: at(cells[0]) });
listeners.mouseover({ buttons: 1, target: at(cells[1]) });
listeners.contextmenu({});
listeners.mouseup({ target: at(cells[2]) });
console.log(JSON.stringify({ emitted, marked }));
"""
        % ASSIGN_DRAG_JS,
        encoding="utf-8",
    )
    result = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["emitted"] == []
    assert out["marked"] == 0
