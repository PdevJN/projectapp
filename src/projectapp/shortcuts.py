"""キーボードショートカットの割り当てと判定(NiceGUI に依存しない純粋関数)。"""

from dataclasses import dataclass
from enum import Enum


class Screen(Enum):
    """キーを受ける画面。プレビューとダッシュボードは、ヘッダーを隠している。"""

    MAIN = "main"
    PREVIEW = "preview"
    DASHBOARD = "dashboard"


@dataclass(frozen=True)
class Shortcut:
    key: str  # 小文字で持つ
    action: str
    desc: str
    ctrl: bool = False  # Ctrl(macOS では Cmd)
    shift: bool = False  # ctrl のときだけ区別する(文字キーでは、`?` のように Shift が要るため見ない)

    def label(self) -> str:
        if self.key == "escape":
            return "ESC"
        prefix = ("Ctrl/Cmd+" if self.ctrl else "") + ("Shift+" if self.shift else "")
        return prefix + self.key.upper() if len(self.key) == 1 and self.key.isalpha() else prefix + self.key


SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut("s", "save", "上書き保存", ctrl=True),
    Shortcut("s", "save_as", "名前をつけて保存", ctrl=True, shift=True),
    Shortcut("o", "open", "開く(ファイル一覧)", ctrl=True),
    Shortcut("n", "new", "新規プロジェクト作成", ctrl=True),
    Shortcut(",", "settings", "設定", ctrl=True),
    Shortcut("e", "handoff", "担当者へ書き出し", ctrl=True),
    Shortcut("p", "preview", "チャートプレビュー", ctrl=True),
    Shortcut("d", "dashboard", "ダッシュボード"),
    Shortcut("/", "search", "タスク名の検索欄へ移る"),
    Shortcut("?", "help", "ショートカットヘルプ"),
    Shortcut("escape", "escape", "開いているダイアログを閉じる(プレビュー・ダッシュボードから戻る)"),
)


def resolve(key: str, *, ctrl: bool, shift: bool, modal: bool, screen: Screen) -> str | None:
    """押されたキーに対応する操作名を返す。割り当てがない・今は効かないときは None。

    ESC は常に `escape`(何を閉じるかは呼び出し側が決める)。それ以外は、メイン画面で
    ダイアログが開いていないときだけ効く。
    """
    key = key.lower()
    if key == "escape":
        return "escape"
    if modal or screen is not Screen.MAIN:
        return None
    for shortcut in SHORTCUTS:
        if shortcut.key != key or shortcut.ctrl != ctrl:
            continue
        if ctrl and shortcut.shift != shift:
            continue
        return shortcut.action
    return None


def help_entries() -> list[tuple[str, str]]:
    """ショートカットヘルプの一覧(キー, 機能)。"""
    return [(s.label(), s.desc) for s in SHORTCUTS]


def ctrl_keys() -> set[str]:
    """Ctrl/Cmd と組み合わせるキー(ブラウザ既定の動きを止める対象)。"""
    return {s.key for s in SHORTCUTS if s.ctrl}


def plain_keys() -> set[str]:
    """修飾キーなしで割り当てたキー(ESC を含む)。"""
    return {s.key for s in SHORTCUTS if not s.ctrl}


def key_guard_js() -> str:
    """ブラウザ側のキーの下ごしらえをする JS。

    - 割り当てたキーの既定の動き(`Ctrl+S` の保存・`Ctrl+P` の印刷、macOS の警告音)を止める。
      文字キーは、入力欄の中では止めない。
    - 日本語 IME がオンだと、WebKit は入力欄での keydown の keyCode を 229 で返し、Quasar は ESC と
      見なさない(ダイアログが ESC で閉じない)。そのときだけ、keyCode 27 の keydown・keyup を送り直す。
    """
    return (
        "document.addEventListener('keydown', e => {"
        f" const ctrl = {sorted(ctrl_keys())!r}, plain = {sorted(plain_keys())!r};"
        " const key = e.key.toLowerCase(), t = e.target || {}, tag = (t.tagName || '').toLowerCase();"
        " const editable = ['input', 'textarea', 'select'].includes(tag) || t.isContentEditable === true;"
        " if (e.ctrlKey || e.metaKey ? ctrl.includes(key) : plain.includes(key) && !editable) e.preventDefault();"
        " if (e.code === 'Escape' && e.keyCode === 229 && !e.isComposing) {"
        " for (const type of ['keydown', 'keyup']) {"
        " const ev = new KeyboardEvent(type, { key: 'Escape', code: 'Escape', bubbles: true });"
        " Object.defineProperty(ev, 'keyCode', { get: () => 27 });"
        " window.dispatchEvent(ev); } }"
        " }, true);"
    )
