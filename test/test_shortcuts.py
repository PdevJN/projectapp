"""キーボードショートカットの判定(NiceGUI に依存しない純粋関数)。"""

import pytest

from projectapp.shortcuts import SHORTCUTS, Screen, help_entries, resolve


@pytest.mark.parametrize(
    ("key", "ctrl", "shift", "action"),
    [
        ("s", True, False, "save"),
        ("S", True, True, "save_as"),
        ("s", True, True, "save_as"),
        ("o", True, False, "open"),
        ("n", True, False, "new"),
        (",", True, False, "settings"),
        ("e", True, False, "handoff"),
        ("p", True, False, "preview"),
        ("d", False, False, "dashboard"),
        ("/", False, False, "search"),
        ("?", False, True, "help"),
        ("?", False, False, "help"),
    ],
)
def test_main_screen_keys_resolve_to_actions(key, ctrl, shift, action):
    assert resolve(key, ctrl=ctrl, shift=shift, modal=False, screen=Screen.MAIN) == action


@pytest.mark.parametrize(
    ("key", "ctrl", "shift"),
    [("s", False, False), ("d", True, False), ("x", True, False), ("x", False, False), ("e", True, True)],
)
def test_unassigned_combinations_resolve_to_nothing(key, ctrl, shift):
    assert resolve(key, ctrl=ctrl, shift=shift, modal=False, screen=Screen.MAIN) is None


@pytest.mark.parametrize("screen", [Screen.PREVIEW, Screen.DASHBOARD])
def test_nothing_resolves_while_the_header_is_hidden(screen):
    assert resolve("s", ctrl=True, shift=False, modal=False, screen=screen) is None
    assert resolve("d", ctrl=False, shift=False, modal=False, screen=screen) is None


def test_nothing_resolves_while_a_dialog_is_open():
    assert resolve("s", ctrl=True, shift=False, modal=True, screen=Screen.MAIN) is None
    assert resolve("d", ctrl=False, shift=False, modal=True, screen=Screen.MAIN) is None


@pytest.mark.parametrize(
    ("key", "shift", "action"),
    [
        ("+", True, "zoom_in"),
        ("+", False, "zoom_in"),
        ("=", False, "zoom_in"),  # US 配列の `+` は Shift+`=`、日本語配列は Shift+`;`
        ("=", True, "zoom_in"),
        (";", True, "zoom_in"),
        (";", False, "zoom_in"),
        ("-", False, "zoom_out"),
        ("0", False, "zoom_reset"),
    ],
)
@pytest.mark.parametrize(
    ("modal", "screen"),
    [(False, Screen.MAIN), (True, Screen.MAIN), (False, Screen.PREVIEW), (False, Screen.DASHBOARD)],
)
def test_zoom_keys_work_in_every_state(key, shift, action, modal, screen):
    assert resolve(key, ctrl=True, shift=shift, modal=modal, screen=screen) == action


def test_zoom_keys_need_ctrl():
    assert resolve("-", ctrl=False, shift=False, modal=False, screen=Screen.MAIN) is None
    assert resolve("0", ctrl=False, shift=False, modal=False, screen=Screen.MAIN) is None


def test_help_lists_the_zoom_keys():
    entries = help_entries()
    assert ("Ctrl/Cmd++", "画面を拡大(=・; でも可)") in entries
    assert ("Ctrl/Cmd+-", "画面を縮小") in entries
    assert ("Ctrl/Cmd+0", "画面の大きさを 100% に戻す") in entries


def test_help_lists_every_shortcut_once_with_its_description():
    entries = help_entries()
    assert len(entries) == len(SHORTCUTS)
    assert ("Ctrl/Cmd+S", "上書き保存") in entries
    assert ("Ctrl/Cmd+Shift+S", "名前をつけて保存") in entries
    assert ("?", "ショートカットヘルプ") in entries
    assert ("ESC", "開いているダイアログを閉じる(プレビュー・ダッシュボードから戻る)") in entries


def test_the_key_lists_for_the_browser_guard_come_from_the_table():
    from projectapp.shortcuts import ctrl_keys, plain_keys

    assert ctrl_keys() == {"s", "o", "n", ",", "e", "p", "+", "=", ";", "-", "0"}
    assert plain_keys() == {"escape", "d", "/", "?"}


HARNESS = """
const fs = require("fs");
const listeners = [];
global.document = { addEventListener: (type, fn) => listeners.push({ type, fn }) };
eval(fs.readFileSync(process.argv[2], "utf8"));
function press(init) {
  const ev = { ctrlKey: false, metaKey: false, key: "", code: "", keyCode: 0, isComposing: false,
    target: { tagName: "DIV" }, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...init };
  for (const l of listeners.filter((l) => l.type === "keydown")) l.fn(ev);
  return { prevented: ev.defaultPrevented };
}
console.log(JSON.stringify({
  ctrlS: press({ ctrlKey: true, key: "s", code: "KeyS", keyCode: 83 }),
  cmdP: press({ metaKey: true, key: "p", code: "KeyP", keyCode: 80 }),
  ctrlX: press({ ctrlKey: true, key: "x", code: "KeyX", keyCode: 88 }),
  d: press({ key: "d", code: "KeyD", keyCode: 68 }),
  slash: press({ key: "/", code: "Slash", keyCode: 191 }),
  esc: press({ key: "Escape", code: "Escape", keyCode: 27 }),
  dInInput: press({ key: "d", code: "KeyD", keyCode: 68, target: { tagName: "INPUT" } }),
  x: press({ key: "x", code: "KeyX", keyCode: 88 }),
}));
"""


def test_the_key_guard_blocks_the_browser_default_and_the_beep(tmp_path):
    import json
    import shutil
    import subprocess

    from projectapp.views import KEY_GUARD_JS

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので JS の動作を確かめない")
    (tmp_path / "guard.js").write_text(KEY_GUARD_JS)
    (tmp_path / "harness.js").write_text(HARNESS)
    run = subprocess.run(
        [node, str(tmp_path / "harness.js"), str(tmp_path / "guard.js")], capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    for name in ("ctrlS", "cmdP", "d", "slash", "esc"):
        assert out[name]["prevented"], name  # ブラウザ既定の動き・macOS の警告音を止める
    for name in ("ctrlX", "dInInput", "x"):
        assert not out[name]["prevented"], name  # 割り当てのないキーと、入力欄の文字は止めない
