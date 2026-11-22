from projectapp.assign_drag import ASSIGN_DRAG_CSS, ASSIGN_DRAG_JS, ASSIGN_DROP_EVENT


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
