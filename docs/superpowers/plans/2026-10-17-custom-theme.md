# カスタムテーマ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** テーマのメニューに`カスタム`を加え、primary・ヘッダーの背景・画面の背景・文字の色・基調(ライト / ダーク)を、プレビュー付きのダイアログで設定・保存できるようにする。

**Architecture:** 色の検証・コントラスト・CSS 変数の生成は、NiceGUI に依存しない純粋関数(`theme.py`)にする。`カスタム`のときだけ`body`にクラス`app-custom`と CSS 変数を設定し、既存の CSS(ヘッダー・ガントの固定列・スクロールバー・画像書き出し)は変数を先に見る形に直す(変数がなければ今の値になるので、自動・ライト・ダークの見た目は変わらない)。ダイアログは`theme_dialog.py`に分け、`MainView`が適用・キャンセル・保存をつなぐ。

**Tech Stack:** Python 3.13+, NiceGUI, pytest, ty, uv

**Spec:** `docs/superpowers/specs/2026-10-17-custom-theme-design.md`

## Global Constraints

- 言語は日本語。UI の文言・コメントは日本語。コメントは多くても 3 行以内(`.claude/RULE.md`)。
- すべての関数に、引数と戻り値の型ヒントを付ける。`uv run ty check src` が通ること。
- テストは pytest。実行は`uv run pytest`(全体)。
- `theme`は`auto`・`light`・`dark`・`custom`。不正な値は`auto`。
- `custom_theme`は`theme`とは別のキー。`カスタム`以外を選んでいる間も色は残る。ほかのキーは壊さない(`update_config`を使う)。
- `base`: `light`か`dark`。不正な値は`light`。
- `primary`・`background`・`foreground`: `#RRGGBB`のみ(大文字小文字は区別せず、保存は小文字)。不正な値は、そのキーだけ既定に戻す。
- `header`: `null`(primary に追従)か`#RRGGBB`。追従で基調がダークなら、primary を 55% 暗くする(`color-mix(in srgb, primary 55%, #000)`と同じ)。色を指定したときはそのまま使う。
- 既定値: ライトは primary `#5898d4`・背景 `#ffffff`・文字 `#000000`、ダークは primary `#5898d4`・背景 `#121212`・文字 `#ffffff`。
- コントラストの警告は 4.5:1 を下回ったとき。基調と背景の明るさの不一致は、相対輝度 0.179 を境にする。ヘッダーの文字は白か黒の良いほうを自動で選ぶので、ヘッダーは警告の対象にしない。
- 状態色・優先度色・土日祝・予定超過の色は変えない。自動・ライト・ダークの見た目は変えない。
- primary は`body`の`--q-primary`を直接設定して変える(`ui.colors()`は使わない)。変数の設定と解除は`ui.run_javascript`(`MainView.run_js`)の 1 回の呼び出しで行い、再描画はしない。テーマを切り替えるたびに`gantt.refresh_scrollbars()`を呼ぶ。
- カスタムテーマは Undo / Redo の履歴にも「未保存」の判定にも入れない。

## Review Focus

- `config.json`の`custom_theme`が配列・文字列・数値など、オブジェクトでない → 全体を既定(ライト)で読み、落ちない。
- `theme`が`custom`なのに`custom_theme`のキーがない(古いファイル・手編集) → ライトの既定色で起動し、落ちない。
- `#fff`(短縮形)・`#rrggbbaa`(透明度つき)・`red`(色名)・全角の入力 → 不正な色として扱う(入力欄のエラーと`適用`の無効化)。
- 保存に失敗した(書き込めない)ときの`適用` → 通知を出し、ダイアログは開いたまま、保存した設定は変わらない。
- プレビュー中のキャンセル・ESC・外側クリック → 開いた時点の`theme`・見た目に戻り、メニューの選択中の印も元のまま。

---

### Task 1: `theme.py`(純粋関数)

**Files:**
- Create: `src/projectapp/theme.py`
- Test: `test/test_theme.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `CustomTheme(base: str, primary: str, header: str | None, background: str, foreground: str)`(frozen dataclass)
  - `DEFAULTS: dict[str, CustomTheme]`(キーは`"light"`・`"dark"`)
  - `BASES: tuple[str, ...]`、`CUSTOM_CLASS: str`(`"app-custom"`)、`BODY_CSS: str`
  - `normalize_hex(text: object) -> str | None`
  - `parse_custom_theme(value: object) -> CustomTheme`
  - `custom_theme_to_dict(theme: CustomTheme) -> dict[str, str | None]`
  - `luminance(color: str) -> float`、`contrast_ratio(fg: str, bg: str) -> float`
  - `on_color(bg: str) -> str`(`"#ffffff"`か`"#000000"`)
  - `header_color(theme: CustomTheme) -> str`
  - `css_variables(theme: CustomTheme) -> dict[str, str]`
  - `theme_js(theme: CustomTheme | None) -> str`
  - `warnings(theme: CustomTheme) -> list[str]`
  - `MISMATCH_MESSAGE: str`

- [ ] **Step 1: Write the failing tests**

`test/test_theme.py`:

```python
import pytest

from projectapp.theme import (
    BASES,
    CUSTOM_CLASS,
    DEFAULTS,
    MISMATCH_MESSAGE,
    CustomTheme,
    contrast_ratio,
    css_variables,
    custom_theme_to_dict,
    header_color,
    normalize_hex,
    on_color,
    parse_custom_theme,
    theme_js,
    warnings,
)

LIGHT = DEFAULTS["light"]
DARK = DEFAULTS["dark"]


def test_defaults_match_the_current_look() -> None:
    assert LIGHT == CustomTheme("light", "#5898d4", None, "#ffffff", "#000000")
    assert DARK == CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff")
    assert BASES == ("light", "dark")


def test_default_primary_matches_nicegui_brand() -> None:
    from nicegui import app

    assert app.config.quasar_config["brand"]["primary"].lower() == LIGHT.primary


@pytest.mark.parametrize(
    ("text", "expected"),
    [("#AABBCC", "#aabbcc"), (" #aabbcc ", "#aabbcc"), ("#fff", None), ("#aabbccdd", None), ("red", None), ("aabbcc", None), ("#ａａｂｂｃｃ", None), ("", None), (None, None), (123, None)],
)
def test_normalize_hex(text: object, expected: str | None) -> None:
    assert normalize_hex(text) == expected


def test_parse_custom_theme_reads_a_valid_value_and_lowercases() -> None:
    value = {"base": "dark", "primary": "#7E57C2", "header": "#112233", "background": "#1E1E2E", "foreground": "#E6E6F0"}
    assert parse_custom_theme(value) == CustomTheme("dark", "#7e57c2", "#112233", "#1e1e2e", "#e6e6f0")


@pytest.mark.parametrize("value", [None, [], "dark", 3, True])
def test_parse_custom_theme_falls_back_to_the_light_default_when_not_an_object(value: object) -> None:
    assert parse_custom_theme(value) == LIGHT


def test_parse_custom_theme_reads_old_files_with_missing_keys_as_defaults() -> None:
    assert parse_custom_theme({}) == LIGHT
    assert parse_custom_theme({"base": "dark"}) == DARK


def test_parse_custom_theme_resets_only_the_invalid_keys() -> None:
    value = {"base": "dark", "primary": "#fff", "header": "red", "background": "#101010", "foreground": 5}
    assert parse_custom_theme(value) == CustomTheme("dark", DARK.primary, None, "#101010", DARK.foreground)


def test_parse_custom_theme_invalid_base_is_light() -> None:
    assert parse_custom_theme({"base": "blue", "background": "#101010"}).base == "light"


def test_custom_theme_to_dict_round_trips() -> None:
    theme = CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0")
    assert custom_theme_to_dict(theme) == {"base": "dark", "primary": "#7e57c2", "header": None, "background": "#1e1e2e", "foreground": "#e6e6f0"}
    assert parse_custom_theme(custom_theme_to_dict(theme)) == theme


def test_contrast_ratio_known_pairs() -> None:
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#336699", "#336699") == pytest.approx(1.0)


def test_on_color_picks_white_on_dark_and_black_on_light() -> None:
    assert on_color("#000000") == "#ffffff"
    assert on_color("#121212") == "#ffffff"
    assert on_color("#ffffff") == "#000000"
    assert on_color("#ffeb3b") == "#000000"


def test_on_color_always_reaches_about_4_58_to_1() -> None:
    for color in ("#767676", "#777777", "#757575", "#808080", "#5898d4"):
        assert contrast_ratio(on_color(color), color) >= 4.5


def test_header_color_follows_primary_on_light() -> None:
    assert header_color(CustomTheme("light", "#5898d4", None, "#ffffff", "#000000")) == "#5898d4"


def test_header_color_darkens_primary_to_55_percent_on_dark() -> None:
    assert header_color(CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff")) == "#305475"  # 88,152,212 の 55%


def test_header_color_uses_the_given_color_as_is() -> None:
    assert header_color(CustomTheme("dark", "#5898d4", "#ffeb3b", "#121212", "#ffffff")) == "#ffeb3b"


def test_css_variables() -> None:
    variables = css_variables(CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff"))
    assert variables["--q-primary"] == "#5898d4"
    assert variables["--app-bg"] == "#121212"
    assert variables["--app-fg"] == "#ffffff"
    assert variables["--app-header"] == "#305475"
    assert variables["--app-header-fg"] == "#ffffff"
    assert variables["--app-header-chip"] == "rgba(255, 255, 255, 0.18)"
    assert variables["--app-header-chip-hover"] == "rgba(255, 255, 255, 0.3)"


def test_css_variables_use_a_translucent_black_for_a_light_header() -> None:
    variables = css_variables(CustomTheme("light", "#5898d4", "#ffeb3b", "#ffffff", "#000000"))
    assert variables["--app-header-fg"] == "#000000"
    assert variables["--app-header-chip"] == "rgba(0, 0, 0, 0.18)"
    assert variables["--app-header-chip-hover"] == "rgba(0, 0, 0, 0.3)"


def test_theme_js_sets_the_variables_and_the_class() -> None:
    js = theme_js(LIGHT)
    assert f"classList.add('{CUSTOM_CLASS}')" in js
    assert 'setProperty("--app-bg", "#ffffff")' in js
    assert 'setProperty("--q-primary", "#5898d4")' in js


def test_theme_js_none_removes_everything() -> None:
    js = theme_js(None)
    assert f"classList.remove('{CUSTOM_CLASS}')" in js
    for name in ("--q-primary", "--app-bg", "--app-fg", "--app-header", "--app-header-fg", "--app-header-chip", "--app-header-chip-hover"):
        assert f'removeProperty("{name}")' in js
    assert "setProperty" not in js


def test_no_warnings_for_the_defaults() -> None:
    assert warnings(LIGHT) == []
    assert warnings(DARK) == []


def test_low_contrast_warns_with_the_ratio_floored_to_one_decimal() -> None:
    result = warnings(CustomTheme("light", "#5898d4", None, "#ffffff", "#999999"))
    assert result == ["文字と背景のコントラスト比が 2.8:1 です。読みにくい可能性があります"]


def test_contrast_of_exactly_4_5_does_not_warn() -> None:
    assert warnings(CustomTheme("light", "#5898d4", None, "#ffffff", "#767676")) == []  # 4.54:1


def test_mismatched_brightness_warns() -> None:
    assert warnings(CustomTheme("light", "#5898d4", None, "#000000", "#ffffff")) == [MISMATCH_MESSAGE]
    assert warnings(CustomTheme("dark", "#5898d4", None, "#ffffff", "#000000")) == [MISMATCH_MESSAGE]


def test_both_warnings_can_appear_together() -> None:
    result = warnings(CustomTheme("light", "#5898d4", None, "#101010", "#202020"))
    assert len(result) == 2 and MISMATCH_MESSAGE in result

```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_theme.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.theme`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/theme.py`:

```python
"""カスタムテーマ(色の検証・コントラスト・CSS 変数)。NiceGUI に依存しない純粋関数。"""

import json
import math
import re
from dataclasses import asdict, dataclass

BASES = ("light", "dark")
CUSTOM_CLASS = "app-custom"
BODY_CSS = f"body.{CUSTOM_CLASS} {{ background: var(--app-bg); color: var(--app-fg); }}"
HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")
CONTRAST_AA = 4.5
LUMINANCE_BOUNDARY = 0.179  # 白と黒に対するコントラスト比が等しくなる相対輝度
HEADER_DARKEN = 0.55  # ダークで primary に追従するときの、ヘッダーの明るさ(今の CSS の color-mix と同じ)
VARIABLES = (
    "--q-primary",
    "--app-bg",
    "--app-fg",
    "--app-header",
    "--app-header-fg",
    "--app-header-chip",
    "--app-header-chip-hover",
)
MISMATCH_MESSAGE = "基調と背景の明るさが合っていません。ダイアログの文字が読みにくくなることがあります"


@dataclass(frozen=True)
class CustomTheme:
    base: str  # "light" | "dark"
    primary: str  # "#rrggbb"
    header: str | None  # None = primary に追従
    background: str
    foreground: str


DEFAULTS: dict[str, CustomTheme] = {
    "light": CustomTheme("light", "#5898d4", None, "#ffffff", "#000000"),
    "dark": CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff"),
}


def normalize_hex(text: object) -> str | None:
    """`#RRGGBB`の検証と小文字化(前後の空白は除く)。不正は None。"""
    if not isinstance(text, str):
        return None
    text = text.strip()
    return text.lower() if HEX_PATTERN.fullmatch(text) else None


def parse_custom_theme(value: object) -> CustomTheme:
    """`config.json`の`custom_theme`の読み込み。不正なキーだけ既定に戻す。オブジェクトでなければ全体を既定にする。"""
    if not isinstance(value, dict):
        return DEFAULTS["light"]
    base = value.get("base")
    base = base if base in BASES else "light"
    default = DEFAULTS[base]

    def color(key: str, fallback: str) -> str:
        return normalize_hex(value.get(key)) or fallback

    return CustomTheme(
        base,
        color("primary", default.primary),
        normalize_hex(value.get("header")),
        color("background", default.background),
        color("foreground", default.foreground),
    )


def custom_theme_to_dict(theme: CustomTheme) -> dict[str, str | None]:
    return asdict(theme)


def _channels(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def luminance(color: str) -> float:
    """WCAG の相対輝度。"""

    def linear(channel: int) -> float:
        s = channel / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in _channels(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    high, low = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def on_color(bg: str) -> str:
    """背景に対して、白か黒のうち、コントラスト比の高いほう。"""
    return "#ffffff" if contrast_ratio("#ffffff", bg) >= contrast_ratio("#000000", bg) else "#000000"


def header_color(theme: CustomTheme) -> str:
    """実際のヘッダーの背景。追従のとき、ダークは primary を 55% に暗くする。"""
    if theme.header is not None:
        return theme.header
    if theme.base == "dark":
        r, g, b = (round(c * HEADER_DARKEN) for c in _channels(theme.primary))
        return f"#{r:02x}{g:02x}{b:02x}"
    return theme.primary


def css_variables(theme: CustomTheme) -> dict[str, str]:
    header = header_color(theme)
    fg = on_color(header)
    chip = "255, 255, 255" if fg == "#ffffff" else "0, 0, 0"
    return {
        "--q-primary": theme.primary,
        "--app-bg": theme.background,
        "--app-fg": theme.foreground,
        "--app-header": header,
        "--app-header-fg": fg,
        "--app-header-chip": f"rgba({chip}, 0.18)",
        "--app-header-chip-hover": f"rgba({chip}, 0.3)",
    }


def theme_js(theme: CustomTheme | None) -> str:
    """`body`に変数とクラスを設定する JS。None は全部外す(NiceGUI の既定の primary に戻る)。"""
    if theme is None:
        removes = "".join(f"s.removeProperty({json.dumps(name)});" for name in VARIABLES)
        return f"(() => {{ const b = document.body, s = b.style; {removes} b.classList.remove('{CUSTOM_CLASS}'); }})()"
    sets = "".join(f"s.setProperty({json.dumps(n)}, {json.dumps(v)});" for n, v in css_variables(theme).items())
    return f"(() => {{ const b = document.body, s = b.style; {sets} b.classList.add('{CUSTOM_CLASS}'); }})()"


def warnings(theme: CustomTheme) -> list[str]:
    """警告の文言。文字と背景のコントラスト比が 4.5:1 を下回る、基調と背景の明るさが合わない、の 2 種類。"""
    found: list[str] = []
    ratio = contrast_ratio(theme.foreground, theme.background)
    if ratio < CONTRAST_AA:
        shown = math.floor(ratio * 10) / 10  # 切り捨て(4.46 を 4.5 と見せて、警告の理由が分からなくならないように)
        found.append(f"文字と背景のコントラスト比が {shown:.1f}:1 です。読みにくい可能性があります")
    bright = luminance(theme.background)
    if (theme.base == "light" and bright < LUMINANCE_BOUNDARY) or (theme.base == "dark" and bright > LUMINANCE_BOUNDARY):
        found.append(MISMATCH_MESSAGE)
    return found
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_theme.py -q && uv run ty check src`
Expected: PASS / `All checks passed`
(`test_default_primary_matches_nicegui_brand`が`quasar_config`の形で落ちたら、`python -c "from nicegui import app; print(app.config.quasar_config)"`で実際のキーを確かめ、テストのアクセス方法だけを直す。既定値の`#5898d4`は変えない。)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/theme.py test/test_theme.py
git commit -m "feat: カスタムテーマの純粋関数(theme.py)を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `config.py`(保存と読込)

**Files:**
- Modify: `src/projectapp/config.py`(`THEMES`、`load_custom_theme`・`save_custom_theme`)
- Test: `test/test_config.py`

**Interfaces:**
- Consumes: `parse_custom_theme`・`custom_theme_to_dict`・`CustomTheme`(Task 1)
- Produces:
  - `THEMES == ("auto", "light", "dark", "custom")`
  - `load_custom_theme(base_dir: Path = BASE_DIR) -> CustomTheme`
  - `save_custom_theme(theme: CustomTheme, base_dir: Path = BASE_DIR, select: bool = False) -> None`(`select`が真なら`theme`も`custom`にして、1 回の書き込みで保存する)

- [ ] **Step 1: Write the failing tests**

`test/test_config.py`の import に`load_custom_theme`・`save_custom_theme`を足し、末尾に追加(`json`・`Path`・`save_theme`・`load_theme`は既に import 済み。`CustomTheme`・`DEFAULTS`は`from projectapp.theme import CustomTheme, DEFAULTS`を足す):

```python
def test_theme_accepts_custom(tmp_path: Path) -> None:
    save_theme("custom", tmp_path)
    assert load_theme(tmp_path) == "custom"


def test_custom_theme_defaults_to_light_when_missing(tmp_path: Path) -> None:
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]
    (tmp_path / "config.json").write_text(json.dumps({"theme": "custom"}), encoding="utf-8")
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]


@pytest.mark.parametrize("raw", [[], "dark", 3, None, True])
def test_custom_theme_that_is_not_an_object_reads_as_the_default(tmp_path: Path, raw: object) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"custom_theme": raw}), encoding="utf-8")
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]


def test_save_custom_theme_round_trips_and_keeps_other_keys(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "name_width": 300, "other": 1}), encoding="utf-8")
    theme = CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0")
    save_custom_theme(theme, tmp_path)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["theme"] == "dark" and saved["name_width"] == 300 and saved["other"] == 1
    assert load_custom_theme(tmp_path) == theme


def test_save_custom_theme_with_select_also_sets_the_theme(tmp_path: Path) -> None:
    save_custom_theme(DEFAULTS["dark"], tmp_path, select=True)
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path) == DEFAULTS["dark"]


def test_saving_the_theme_keeps_the_custom_colors(tmp_path: Path) -> None:
    save_custom_theme(DEFAULTS["dark"], tmp_path, select=True)
    save_theme("light", tmp_path)
    assert load_custom_theme(tmp_path) == DEFAULTS["dark"]
```

(ファイルの先頭に`import pytest`がなければ足す。)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_config.py -q`
Expected: FAIL(`ImportError: cannot import name 'load_custom_theme'`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/config.py`:

1. import に`from projectapp.theme import CustomTheme, custom_theme_to_dict, parse_custom_theme`を足す。
2. `THEMES = ("auto", "light", "dark")` → `THEMES = ("auto", "light", "dark", "custom")`
3. `save_theme`の下に追加:

```python
def load_custom_theme(base_dir: Path = BASE_DIR) -> CustomTheme:
    return parse_custom_theme(read_config(base_dir).get("custom_theme"))


def save_custom_theme(theme: CustomTheme, base_dir: Path = BASE_DIR, select: bool = False) -> None:
    """カスタムの色を保存する。`select`が真なら、テーマも`custom`にして、1 回の書き込みで保存する。"""
    updates: dict = {"custom_theme": custom_theme_to_dict(theme)}
    if select:
        updates["theme"] = "custom"
    update_config(updates, base_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_config.py test/test_theme.py -q && uv run ty check src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/config.py test/test_config.py
git commit -m "feat: カスタムテーマの色を config.json に保存・読込する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: CSS を変数経由にする(見た目は変えない)と、画像書き出しの背景

**Files:**
- Modify: `src/projectapp/views.py`(`HEADER_CSS`、`build`の`ui.add_css`)
- Modify: `src/projectapp/gantt.py`(`STICKY_CSS`)
- Modify: `src/projectapp/export.py`(`CAPTURE_JS`)
- Test: `test/test_views.py`、`test/test_gantt.py`、`test/test_export.py`

**Interfaces:**
- Consumes: `BODY_CSS`・`CUSTOM_CLASS`(Task 1)
- Produces: CSS 変数`--app-bg`・`--app-fg`・`--app-header`・`--app-header-fg`・`--app-header-chip`・`--app-header-chip-hover`を、定義されていなければ今の値になる形で参照する CSS。

- [ ] **Step 1: Write the failing tests**

`test/test_views.py`に追加(`HEADER_CSS`は`from projectapp.views import ...`に足す):

```python
def test_header_css_reads_the_custom_variables_and_keeps_the_current_defaults() -> None:
    assert "background: var(--app-header, var(--q-primary)); color: var(--app-header-fg, #fff)" in HEADER_CSS
    assert "body.body--dark .app-header { background: var(--app-header, color-mix(in srgb, var(--q-primary) 55%, #000)); }" in HEADER_CSS
    assert ".app-header .app-menu-btn { background: var(--app-header-chip, rgba(255, 255, 255, 0.18));" in HEADER_CSS
    assert ".app-header .app-menu-btn:hover { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }" in HEADER_CSS
    assert "border-radius: 9999px; background: var(--app-header-chip, rgba(255, 255, 255, 0.18))" in HEADER_CSS
    assert ".app-git-chip:hover { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }" in HEADER_CSS
```

`test/test_gantt.py`に追加(`STICKY_CSS`を import に足す):

```python
def test_sticky_css_reads_the_app_variables_and_keeps_the_current_defaults() -> None:
    assert ".gantt-sticky { background-color: var(--app-bg, #fff); }" in STICKY_CSS
    assert "body.body--dark .gantt-sticky { background-color: var(--app-bg, var(--q-dark-page, #121212)); }" in STICKY_CSS
    assert "var(--q-dark-page, #121212)" not in STICKY_CSS.replace("var(--app-bg, var(--q-dark-page, #121212))", "")
```

`test/test_export.py`に追加(`CAPTURE_JS`を import に足す):

```python
def test_capture_uses_the_body_background_for_the_custom_theme() -> None:
    assert "document.body.classList.contains('app-custom')" in CAPTURE_JS
    assert "(dark || custom) ? getComputedStyle(document.body).backgroundColor : '#ffffff'" in CAPTURE_JS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_views.py test/test_gantt.py test/test_export.py -q -k "custom_variables or app_variables or custom_theme"`
Expected: FAIL(3 件)

- [ ] **Step 3: Write the implementation**

`views.py`の`HEADER_CSS`を、次の置き換えで直す(ほかの行は変えない):

- `.app-header { background: var(--q-primary); color: #fff;` → `.app-header { background: var(--app-header, var(--q-primary)); color: var(--app-header-fg, #fff);`
- `body.body--dark .app-header { background: color-mix(in srgb, var(--q-primary) 55%, #000); }` → `body.body--dark .app-header { background: var(--app-header, color-mix(in srgb, var(--q-primary) 55%, #000)); }`
- `.app-header .app-menu-btn { background: rgba(255, 255, 255, 0.18);` → `.app-header .app-menu-btn { background: var(--app-header-chip, rgba(255, 255, 255, 0.18));`
- `.app-header .app-menu-btn:hover { background: rgba(255, 255, 255, 0.3); }` → `... { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }`
- `.app-git-chip { ... background: rgba(255, 255, 255, 0.18);` → `background: var(--app-header-chip, rgba(255, 255, 255, 0.18));`
- `.app-git-chip:hover { background: rgba(255, 255, 255, 0.3); }` → `background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3));`

`build`(`ui.add_css(HEADER_CSS)`の次の行)に`ui.add_css(BODY_CSS)`を足し、`from projectapp.theme import BODY_CSS`を import する。

`gantt.py`の`STICKY_CSS`:

```python
STICKY_CSS = """
.gantt-sticky { background-color: var(--app-bg, #fff); }
body.body--dark .gantt-sticky { background-color: var(--app-bg, var(--q-dark-page, #121212)); }
body.body--dark [data-chart-scroll] { color-scheme: dark; background-color: var(--app-bg, var(--q-dark-page, #121212)); }
body.body--dark [data-chart-scroll]::-webkit-scrollbar { width: 12px; height: 12px; }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-track { background: var(--app-bg, var(--q-dark-page, #121212)); }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-thumb { background: #555; border-radius: 6px; }
body.body--dark [data-chart-scroll]::-webkit-scrollbar-corner { background: var(--app-bg, var(--q-dark-page, #121212)); }
"""
```

`export.py`の`CAPTURE_JS`の 2 行を置き換える:

```js
  const dark = document.body.classList.contains('body--dark');
  const custom = document.body.classList.contains('app-custom');
  const bg = (dark || custom) ? getComputedStyle(document.body).backgroundColor : '#ffffff';
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: 全件 PASS(既存のテストが落ちたら、CSS の文字列を直しすぎていないか確かめる。見た目の既定値は変えていない)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/views.py src/projectapp/gantt.py src/projectapp/export.py test/test_views.py test/test_gantt.py test/test_export.py
git commit -m "feat: ヘッダー・ガントの背景・画像書き出しの背景を、カスタムテーマの変数経由にする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `MainView`の`apply_theme`とテーマのメニュー

**Files:**
- Modify: `src/projectapp/views.py`(`THEME_LABELS`・`THEME_ICONS`、`__init__`、`apply_theme`、`set_theme`、`build`、`theme_menu`)
- Test: `test/test_views.py`(新規 + 既存の 3 件の期待値を直す)

**Interfaces:**
- Consumes: `load_custom_theme`(Task 2)、`theme_js`・`CustomTheme`(Task 1)
- Produces:
  - `MainView.custom_theme: CustomTheme`(保存済みの色)
  - `MainView.apply_theme(theme: str, custom: CustomTheme | None = None) -> None`(`custom`を渡すと、保存せずその色で見せる〔プレビュー〕。`theme`が`custom`でないときは変数を外す)
  - `MainView.open_theme_dialog()`(Task 5 で実装。この Task ではメニューの項目が呼ぶだけの空の入口を置く〔下記〕)
  - メニューのマーカー: `theme-custom`・`theme-custom-settings`

- [ ] **Step 1: Write the failing tests**

`test/test_views.py`に追加:

```python
async def test_apply_theme_custom_sets_dark_mode_from_the_base_and_the_variables(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    scripts: list[str] = []
    view.run_js = lambda script, **kw: scripts.append(script)  # type: ignore[method-assign]
    view.custom_theme = CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0")
    view.apply_theme("custom")
    assert view.theme == "custom" and view.dark.value is True
    assert len(scripts) == 1 and 'setProperty("--app-bg", "#1e1e2e")' in scripts[0]
    view.apply_theme("light")
    assert view.dark.value is False
    assert len(scripts) == 2 and "setProperty" not in scripts[1] and 'removeProperty("--q-primary")' in scripts[1]


async def test_apply_theme_with_a_preview_color_does_not_change_the_saved_color(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    scripts: list[str] = []
    view.run_js = lambda script, **kw: scripts.append(script)  # type: ignore[method-assign]
    saved = view.custom_theme
    view.apply_theme("custom", CustomTheme("dark", "#112233", None, "#000000", "#ffffff"))
    assert view.custom_theme == saved
    assert '"#112233"' in scripts[0] and view.dark.value is True


async def test_starting_with_the_custom_theme_applies_the_saved_colors(user: User, tmp_path: Path) -> None:
    save_custom_theme(CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0"), tmp_path, select=True)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].theme == "custom" and views[0].dark.value is True
    assert views[0].custom_theme.primary == "#7e57c2"


async def test_starting_with_custom_and_no_colors_uses_the_light_default(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "custom"}), encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].theme == "custom" and views[0].dark.value is False


async def test_selecting_custom_in_the_menu_saves_the_theme_and_keeps_the_colors(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)
    user.find(marker="theme-custom").click()
    assert view.theme == "custom"
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path) == view.custom_theme
```

(`CustomTheme`・`save_custom_theme`・`load_custom_theme`・`load_theme`は、必要なものを import に足す。)

既存テストの期待値を直す:

- `test_the_menus_list_their_items_in_order`の`menu_icons(user, "menu-theme-items")` → `["brightness_auto", "light_mode", "dark_mode", "palette", "tune"]`
- 同じく`menu_items(user, "menu-theme-items")` → `[("自動", "theme-auto"), ("ライト", "theme-light"), ("ダーク", "theme-dark"), ("カスタム", "theme-custom"), ("カスタムの色…", "theme-custom-settings")]`
- `test_the_theme_menu_marks_the_selected_theme_and_switches_it`の`selected()`の`("auto", "light", "dark")` → `("auto", "light", "dark", "custom")`

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_views.py -q -k "theme"`
Expected: FAIL

- [ ] **Step 3: Write the implementation**

`views.py`:

1. 定数:

```python
THEME_LABELS = {"auto": "自動", "light": "ライト", "dark": "ダーク", "custom": "カスタム"}
THEME_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode", "custom": "palette"}
CUSTOM_COLORS_LABEL = "カスタムの色…"
```

2. import に`load_custom_theme`(config)、`CustomTheme`・`theme_js`(theme)を足す。
3. `__init__`の`self.theme = load_theme(base_dir)`の次に`self.custom_theme = load_custom_theme(base_dir)  # 保存済みのカスタムの色`を足す。`self.apply_theme(self.theme)`は、`__init__`ではダークモードの値だけを決めるので、このまま呼んでよい(`run_js`は`build`で流す。下の 5)。
4. `apply_theme`:

```python
    def apply_theme(self, theme: str, custom: CustomTheme | None = None) -> None:
        """テーマを画面に反映する(保存はしない)。`custom`を渡すと、保存済みでなくその色で見せる(プレビュー)。"""
        self.theme = theme
        if theme == "custom":
            colors = custom or self.custom_theme
            self.dark.value = colors.base == "dark"
            self.run_js(theme_js(colors))
        else:
            self.dark.value = None if theme == "auto" else theme == "dark"
            self.run_js(theme_js(None))
```

   `__init__`から呼ぶと`run_js`が`__init__`中に走る(ページ構築中。`run_js`は`__init__`の先頭近くで設定済み)。ただし接続前の呼び出しで落ちる場合は、`__init__`では`apply_theme`を呼ばず、`self.theme`と`self.dark.value`だけを設定して、`build`で`self.run_js(theme_js(self.custom_theme if self.theme == "custom" else None))`を流す形にする(実行して確かめ、落ちたほうを採る)。既存テストで`run_js`の呼び出し回数を数えているものが落ちたら、`theme`が`custom`以外のときは`build`で流さない。

5. `set_theme`はそのまま(`apply_theme(theme)` → `refresh_scrollbars` → `save_theme` → `theme_menu.refresh`)。
6. `theme_menu`:

```python
                for theme in THEMES:
                    item = self.menu_entry(
                        THEME_LABELS[theme], THEME_ICONS[theme], lambda t=theme: self.set_theme(t), f"theme-{theme}"
                    )
                    if theme == self.theme:
                        item.props("active")
                ui.separator().mark("theme-separator")
                self.menu_entry(CUSTOM_COLORS_LABEL, "tune", self.open_theme_dialog, "theme-custom-settings")
```

7. 空の入口(Task 5 で本体に置き換える):

```python
    def open_theme_dialog(self) -> None:
        """カスタムの色のダイアログ。"""
        raise NotImplementedError
```

(Task 4 のテストはこの入口を呼ばない。)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ty check src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: テーマのメニューに「カスタム」を足し、保存した色で起動・切り替えできるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: カスタムの色のダイアログ(`theme_dialog.py`)と`MainView`との接続

**Files:**
- Create: `src/projectapp/theme_dialog.py`
- Modify: `src/projectapp/views.py`(`open_theme_dialog`の本体、`preview_custom`・`restore_theme`・`apply_custom`)
- Test: `test/test_theme_dialog.py`(ダイアログ単体)、`test/test_views.py`(接続)

**Interfaces:**
- Consumes: `CustomTheme`・`DEFAULTS`・`normalize_hex`・`header_color`・`warnings`(Task 1)、`disposable`(`forms.py`)、`save_custom_theme`(Task 2)、`MainView.apply_theme`(Task 4)
- Produces:
  - `open_theme_dialog(initial: CustomTheme, on_preview: Callable[[CustomTheme], object], on_apply: Callable[[CustomTheme], bool], on_cancel: Callable[[], object]) -> None`
    - 色や基調を変えるたびに`on_preview(theme)`。`適用`は`on_apply(theme)`が真を返したときだけ閉じる(偽なら開いたまま)。`キャンセル`・ESC・外側クリックで閉じたとき、適用していなければ`on_cancel()`。
  - マーカー: `theme-base`(トグル)、`theme-primary`・`theme-header`・`theme-background`・`theme-foreground`(色の入力欄)、`theme-header-follow`(チェック)、`theme-reset`・`theme-apply`・`theme-cancel`(ボタン)、`theme-warnings`(警告の枠)、`theme-warning`(警告 1 行)、`theme-error-<key>`は使わない〔エラーは入力欄の`validation`で出す〕。
  - `MainView.preview_custom(theme: CustomTheme) -> None`、`MainView.restore_theme(theme: str) -> None`、`MainView.apply_custom(theme: CustomTheme) -> bool`

- [ ] **Step 1: Write the failing tests for the dialog**

`test/test_theme_dialog.py`(ページを 1 つ作り、ボタンでダイアログを開く。入力は`.elements.pop().set_value(...)`で行う):

```python
from nicegui import ui
from nicegui.testing import User

from projectapp.theme import DEFAULTS, MISMATCH_MESSAGE, CustomTheme
from projectapp.theme_dialog import open_theme_dialog

pytest_plugins = ["nicegui.testing.user_plugin"]


class Recorder:
    def __init__(self, apply_result: bool = True) -> None:
        self.previews: list[CustomTheme] = []
        self.applied: list[CustomTheme] = []
        self.cancelled = 0
        self.apply_result = apply_result

    def on_apply(self, theme: CustomTheme) -> bool:
        self.applied.append(theme)
        return self.apply_result

    def mount(self, initial: CustomTheme) -> None:
        @ui.page("/")
        def index() -> None:
            ui.button(
                "open",
                on_click=lambda: open_theme_dialog(
                    initial, self.previews.append, self.on_apply, lambda: setattr(self, "cancelled", self.cancelled + 1)
                ),
            )


def field(user: User, marker: str) -> ui.input:
    return user.find(marker=marker).elements.pop()  # type: ignore[return-value]


def warnings_text(user: User) -> list[str]:
    return [e.text for e in user.find(marker="theme-warning").elements]


async def test_editing_a_color_previews_it_immediately(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7E57C2")
    assert rec.previews[-1].primary == "#7e57c2"
    field(user, "theme-background").set_value("#fafafa")
    assert rec.previews[-1].background == "#fafafa" and rec.previews[-1].primary == "#7e57c2"


async def test_apply_closes_and_passes_the_edited_theme(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7e57c2")
    user.find(marker="theme-apply").click()
    assert rec.applied == [CustomTheme("light", "#7e57c2", None, "#ffffff", "#000000")]
    assert rec.cancelled == 0


async def test_cancel_restores_without_applying(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7e57c2")
    user.find(marker="theme-cancel").click()
    assert rec.cancelled == 1 and rec.applied == []


async def test_closing_without_applying_also_cancels(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    dialog = user.find(marker="theme-apply").elements.pop().parent_slot.parent.parent_slot.parent  # ボタン → 行 → カード → ダイアログ
    while not isinstance(dialog, ui.dialog):
        dialog = dialog.parent_slot.parent
    dialog.close()  # ESC・外側クリックと同じ(hide が飛ぶ)
    assert await wait_hidden(dialog)
    assert rec.cancelled == 1


async def test_a_failed_apply_keeps_the_dialog_open_and_does_not_cancel(user: User) -> None:
    rec = Recorder(apply_result=False)
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    user.find(marker="theme-apply").click()
    assert len(rec.applied) == 1
    await user.should_see(marker="theme-apply")  # まだ開いている
    assert rec.cancelled == 0


async def test_invalid_color_disables_apply_and_keeps_the_last_valid_preview(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7e57c2")
    count = len(rec.previews)
    for bad in ("#fff", "#7e57c2ff", "red", ""):
        field(user, "theme-primary").set_value(bad)
        assert not user.find(marker="theme-apply").elements.pop().enabled
        assert len(rec.previews) == count and rec.previews[-1].primary == "#7e57c2"
    field(user, "theme-primary").set_value("#336699")
    assert user.find(marker="theme-apply").elements.pop().enabled


async def test_header_follow_checkbox_hides_the_header_input_and_sends_none(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    follow = user.find(marker="theme-header-follow").elements.pop()
    assert follow.value is True and not field(user, "theme-header").visible
    follow.set_value(False)
    assert field(user, "theme-header").visible
    assert rec.previews[-1].header is not None
    field(user, "theme-header").set_value("#ffeb3b")
    assert rec.previews[-1].header == "#ffeb3b"
    follow.set_value(True)
    assert rec.previews[-1].header is None


async def test_an_invalid_header_does_not_block_apply_while_following(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    follow = user.find(marker="theme-header-follow").elements.pop()
    follow.set_value(False)
    field(user, "theme-header").set_value("zzz")
    assert not user.find(marker="theme-apply").elements.pop().enabled
    follow.set_value(True)
    assert user.find(marker="theme-apply").elements.pop().enabled


async def test_reset_puts_the_defaults_of_the_selected_base(user: User) -> None:
    rec = Recorder()
    rec.mount(CustomTheme("dark", "#7e57c2", "#ffeb3b", "#1e1e2e", "#e6e6f0"))
    await user.open("/")
    user.find("open").click()
    user.find(marker="theme-reset").click()
    assert rec.previews[-1] == DEFAULTS["dark"]
    assert rec.applied == []  # 保存は適用のとき
    user.find(marker="theme-apply").click()
    assert rec.applied == [DEFAULTS["dark"]]


async def test_switching_the_base_changes_only_the_base_and_warns_on_mismatch(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    assert warnings_text(user) == []
    user.find(marker="theme-base").elements.pop().set_value("dark")
    assert rec.previews[-1] == CustomTheme("dark", "#5898d4", None, "#ffffff", "#000000")
    assert warnings_text(user) == [MISMATCH_MESSAGE]


async def test_low_contrast_shows_an_orange_warning_but_apply_stays_enabled(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-foreground").set_value("#999999")
    assert warnings_text(user) == ["文字と背景のコントラスト比が 2.8:1 です。読みにくい可能性があります"]
    assert user.find(marker="theme-apply").elements.pop().enabled
```

`wait_hidden`は、`test/test_views.py`の`wait_until`と同じ形の小さな補助をこのファイルに書く(`dialog.value is False`になるまで 0.05 秒ずつ最大 2 秒待つ。`await asyncio.sleep`)。

- [ ] **Step 2: Write the failing tests for the MainView wiring**

`test/test_views.py`に追加:

```python
async def test_theme_dialog_preview_then_cancel_restores_the_previous_theme(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.set_theme("dark")
    view.open_theme_dialog()
    user.find(marker="theme-primary").elements.pop().set_value("#7e57c2")
    assert view.theme == "custom"  # プレビュー中
    user.find(marker="theme-cancel").click()
    assert view.theme == "dark" and view.dark.value is True
    assert load_theme(tmp_path) == "dark"
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]  # 何も保存していない


async def test_theme_dialog_apply_saves_the_colors_and_selects_custom(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.open_theme_dialog()
    user.find(marker="theme-primary").elements.pop().set_value("#7e57c2")
    user.find(marker="theme-apply").click()
    assert view.theme == "custom" and view.custom_theme.primary == "#7e57c2"
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path).primary == "#7e57c2"


async def test_theme_dialog_apply_failure_notifies_and_keeps_saved_state(user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.save_custom_theme", fail)
    view.open_theme_dialog()
    user.find(marker="theme-primary").elements.pop().set_value("#7e57c2")
    user.find(marker="theme-apply").click()
    await user.should_see("テーマを保存できませんでした")
    assert view.custom_theme == DEFAULTS["light"]  # 保存済みの色は変えない
    await user.should_see(marker="theme-apply")  # ダイアログは開いたまま


async def test_selecting_custom_settings_in_the_menu_opens_the_dialog(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    user.find(marker="theme-custom-settings").click()
    await user.should_see(marker="theme-apply")
```

(`pytest`・`DEFAULTS`の import が足りなければ足す。`monkeypatch`先は`views.py`が`from projectapp.config import save_custom_theme`で import した名前。)

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest test/test_theme_dialog.py test/test_views.py -q -k "theme"`
Expected: FAIL(`ModuleNotFoundError: projectapp.theme_dialog` ほか)

- [ ] **Step 4: Write the dialog**

`src/projectapp/theme_dialog.py`:

```python
"""カスタムテーマの色のダイアログ(プレビュー・適用・キャンセル)。"""

from collections.abc import Callable
from dataclasses import replace

from nicegui import ui

from projectapp.forms import disposable
from projectapp.theme import DEFAULTS, CustomTheme, header_color, normalize_hex, warnings

INVALID_COLOR_MESSAGE = "#RRGGBB の形で入力してください"
COLOR_FIELDS = (
    ("primary", "primary", "theme-primary"),
    ("background", "画面の背景", "theme-background"),
    ("foreground", "文字の色", "theme-foreground"),
)


def open_theme_dialog(
    initial: CustomTheme,
    on_preview: Callable[[CustomTheme], object],
    on_apply: Callable[[CustomTheme], bool],
    on_cancel: Callable[[], object],
) -> None:
    """色を変えるたびに`on_preview`を呼ぶ。`適用`は`on_apply`が真のときだけ閉じる。適用せずに閉じたら`on_cancel`。"""
    current = initial
    applied = False
    invalid: set[str] = set()
    inputs: dict[str, ui.color_input] = {}

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[28rem] max-w-full"):
        ui.label("カスタムの色").classes("text-h6")
        base = ui.toggle({"light": "ライト", "dark": "ダーク"}, value=initial.base).mark("theme-base")

        def update(**fields: str | None) -> None:
            nonlocal current
            current = replace(current, **fields)
            show_warnings()
            on_preview(current)

        def edit(key: str, value: str | None) -> None:
            color = normalize_hex(value or "")
            if color is None:
                invalid.add(key)
            else:
                invalid.discard(key)
                update(**{key: color})
            apply_button.set_enabled(not invalid)

        for key, label, marker in COLOR_FIELDS:
            inputs[key] = ui.color_input(
                label,
                value=getattr(initial, key),
                on_change=lambda e, k=key: edit(k, e.value),
                validation={INVALID_COLOR_MESSAGE: lambda v: normalize_hex(v or "") is not None},
            ).classes("w-full").mark(marker)

        follow = ui.checkbox("ヘッダーの背景を primary に追従", value=initial.header is None).mark("theme-header-follow")
        header_input = ui.color_input(
            "ヘッダーの背景",
            value=initial.header or header_color(initial),
            on_change=lambda e: edit("header", e.value) if not follow.value else None,
            validation={INVALID_COLOR_MESSAGE: lambda v: normalize_hex(v or "") is not None},
        ).classes("w-full").mark("theme-header")
        header_input.set_visibility(initial.header is not None)

        def toggle_follow(event: object) -> None:
            if follow.value:
                invalid.discard("header")
                header_input.set_visibility(False)
                update(header=None)
            else:
                header_input.set_visibility(True)
                edit("header", header_input.value)
            apply_button.set_enabled(not invalid)

        follow.on_value_change(toggle_follow)
        base.on_value_change(lambda e: update(base=e.value))

        warning_box = ui.column().classes("w-full gap-0").mark("theme-warnings")

        def show_warnings() -> None:
            warning_box.clear()
            with warning_box:
                for text in warnings(current):
                    ui.label(text).classes("text-caption text-orange").mark("theme-warning")

        def reset() -> None:
            nonlocal current
            defaults = DEFAULTS[current.base]
            invalid.clear()
            current = defaults
            for key, _, _ in COLOR_FIELDS:
                inputs[key].set_value(getattr(defaults, key))
            follow.set_value(True)
            header_input.set_value(header_color(defaults))
            show_warnings()
            on_preview(current)
            apply_button.set_enabled(True)

        def apply() -> None:
            nonlocal applied
            if on_apply(current):
                applied = True
                dialog.close()

        with ui.row().classes("w-full justify-between"):
            ui.button("既定に戻す", on_click=reset).props("flat no-caps").mark("theme-reset")
            with ui.row():
                ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark("theme-cancel")
                apply_button = ui.button("適用", on_click=apply).props("no-caps").mark("theme-apply")
        show_warnings()
        dialog.on("hide", lambda: None if applied else on_cancel())
    dialog.open()
```

実装の注意(テストを通すために確かめる点):

- `reset`は`set_value`で`edit`を呼ぶ。`edit`が`update`を呼ぶので、`reset`の最後の`on_preview(current)`と重複しても、結果は同じ。`current`は`set_value`の連鎖の中で`replace`されるので、`reset`の最後に`current = defaults`をもう一度代入してから`on_preview`を呼ぶ形にして、最終状態を必ず既定にそろえる。
- `follow.set_value(True)`が`toggle_follow`を呼び、`update(header=None)`が走る。`header_input.set_value(...)`は`follow.value`が真なので`edit`を呼ばない。
- `ui.color_input`の`validation`は、値が空のときも`INVALID_COLOR_MESSAGE`を出す。`edit("...", "")`は`invalid`へ入れる(テスト `test_invalid_color_...` の `""`)。

- [ ] **Step 5: Write the MainView wiring**

`views.py`の`open_theme_dialog`(Task 4 の空の入口)を置き換え、近くに 3 つのメソッドを足す。import に`save_custom_theme`(config)と`from projectapp.theme_dialog import open_theme_dialog as show_theme_dialog`を足す:

```python
    def open_theme_dialog(self) -> None:
        """カスタムの色のダイアログ。色を変えると画面に反映し(プレビュー)、キャンセルで開く前に戻す。"""
        previous = self.theme
        show_theme_dialog(self.custom_theme, self.preview_custom, self.apply_custom, lambda: self.restore_theme(previous))

    def preview_custom(self, theme: CustomTheme) -> None:
        self.apply_theme("custom", theme)
        self.gantt.refresh_scrollbars()

    def restore_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        self.gantt.refresh_scrollbars()

    def apply_custom(self, theme: CustomTheme) -> bool:
        """色と`theme: custom`を 1 回の書き込みで保存する。失敗したら通知して False(保存済みの色は変えない)。"""
        try:
            save_custom_theme(theme, self.base_dir, select=True)
        except OSError:
            ui.notify("テーマを保存できませんでした", type="warning")
            return False
        self.custom_theme = theme
        self.apply_theme("custom")
        self.theme_menu.refresh()
        return True
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ty check src`
Expected: PASS(ダイアログが開いている間、既存のショートカットが ESC と拡大・縮小以外を無視することも、`test_shortcuts`・`test_views`が通ることで確かめる)

- [ ] **Step 7: Commit**

```bash
git add src/projectapp/theme_dialog.py src/projectapp/views.py test/test_theme_dialog.py test/test_views.py
git commit -m "feat: カスタムの色のダイアログ(プレビュー・適用・キャンセル・警告)を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 文書への反映と全体の確認

**Files:**
- Modify: `CLAUDE.md`(「テーマ・ヘルプ」とヘッダーの記載)
- Modify: `docs/development.md`(モジュール構成に`theme.py`・`theme_dialog.py`、`config.py`の行)
- Modify: `.claude/MEMORY.md`(作業記録。`RULE.md`の「状況記録」)

**Interfaces:**
- Consumes: Task 1〜5 の実装
- Produces: 現在の仕様の記述

- [ ] **Step 1: `CLAUDE.md`を直す**

`projectapp/CLAUDE.md`の次の 2 か所を直す:

- `## ヘッダー`の右側の記載の「テーマのメニュー」に`カスタム`が加わったことは、`## テーマ・ヘルプ`の節で説明する。
- `## テーマ・ヘルプ`の「ヘッダー右端のテーマのメニューから、テーマを`自動`…」の行を、`自動`・`ライト`・`ダーク`・`カスタム`の 4 つにし、続けて次を足す:

```markdown
- `カスタム`は、primary・ヘッダーの背景(`primary に追従`も選べる)・画面の背景・文字の色・基調(ライト / ダーク)を設定できる。テーマのメニューの`カスタムの色…`でダイアログを開き、色を変えるとすぐ画面に反映する(プレビュー)。`適用`で保存し、`キャンセル`・ESC・外側クリックで開く前に戻す。`既定に戻す`は、選んでいる基調の既定値を入れる(保存は`適用`)
- 色は`#RRGGBB`のみ(不正な値は入力欄にエラーを出し、`適用`を押せなくする)。コントラスト比(文字と画面の背景)が 4.5:1 を下回るとき、基調と背景の明るさが合わないときは、橙の警告を出す(適用はできる)。ヘッダーの文字は白か黒の良いほうを自動で選ぶ
- カスタムの色は`~/.projectapp/config.json`の`custom_theme`(`theme`とは別のキー。`カスタム`以外を選んでいる間も残る。全プロジェクト共通)。状態色・優先度色・土日祝の色は変えない。カスタムの色は、元に戻す・やり直しの対象にしない
```

- [ ] **Step 2: `docs/development.md`を直す**

モジュール構成の表に追記する(`config.py`の行の前):

```markdown
| `theme.py` | カスタムテーマ。`CustomTheme`・`DEFAULTS`(基調ごとの既定。今の見た目と一致)・`parse_custom_theme`(不正なキーだけ既定に戻す)・`normalize_hex`・`contrast_ratio`・`on_color`・`header_color`(追従・ダークは primary を 55% に)・`css_variables`・`theme_js`(`body`の変数とクラス`app-custom`。None で全部外す)・`warnings`・`BODY_CSS`。純粋関数(NiceGUI に依存しない)。CSS 側は`var(--app-bg, <今の値>)`の形で変数を先に見るので、`カスタム`以外では見た目が変わらない |
| `theme_dialog.py` | カスタムの色のダイアログ(`open_theme_dialog`)。色を変えるたびに`on_preview`、`適用`は`on_apply`が真のときだけ閉じる、適用せずに閉じたら`on_cancel`。`MainView.open_theme_dialog`が、`preview_custom`・`apply_custom`・`restore_theme`につなぐ |
```

`config.py`の行の「テーマ・名前の欄の幅…」に`・カスタムテーマの色(custom_theme)`を足す。

- [ ] **Step 3: 全体の確認**

Run: `uv run pytest -q && uv run ty check src`
Expected: 全件 PASS / `All checks passed`

- [ ] **Step 4: 作業記録を更新する**

`.claude/MEMORY.md`の「要望 28」の項目(なければ、直近の作業の並びに新しく 1 項目)を、次の内容で更新する: ブランチ`feature/custom-theme`、設計書と実装計画のパス、実装済みの範囲、**実機確認はこれから**(下の一覧)。

実機(ネイティブ)で確かめる項目(設計書「テスト」の実機):

1. ライトの`body`の実際の文字色が既定の`#000000`と一致する(`getComputedStyle(document.body).color`)。違えば`DEFAULTS["light"].foreground`と`test_theme.py`を直す。
2. ダーク基調で、チャートのスクロールバーが描き直される。
3. 画像(PNG)の書き出しの背景が、カスタムの画面の背景になる。
4. ヘッダーが明るい色(例 `#ffeb3b`)のとき、文字が黒になり、メニューのボタンとチップが見える。
5. ダイアログでのプレビューと、キャンセル・ESC・外側クリックでの復元。`適用`後に再起動して、色が復元される。
6. 自動・ライト・ダークの見た目が、変更前と変わっていない。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md docs/superpowers/plans/2026-10-17-custom-theme.md
git commit -m "docs: カスタムテーマを仕様・開発メモ・作業記録に反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
