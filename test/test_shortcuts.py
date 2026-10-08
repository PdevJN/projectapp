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


def test_help_lists_every_shortcut_once_with_its_description():
    entries = help_entries()
    assert len(entries) == len(SHORTCUTS)
    assert ("Ctrl/Cmd+S", "上書き保存") in entries
    assert ("Ctrl/Cmd+Shift+S", "名前をつけて保存") in entries
    assert ("?", "ショートカットヘルプ") in entries
    assert ("ESC", "開いているダイアログを閉じる(プレビュー・ダッシュボードから戻る)") in entries


def test_only_ctrl_keys_are_listed_for_blocking_the_browser_default():
    from projectapp.shortcuts import ctrl_keys
    from projectapp.views import PREVENT_DEFAULT_JS

    assert ctrl_keys() == {"s", "o", "n", ",", "e", "p"}
    assert "preventDefault" in PREVENT_DEFAULT_JS
    assert "'p'" in PREVENT_DEFAULT_JS and "'d'" not in PREVENT_DEFAULT_JS
