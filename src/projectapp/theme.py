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
    "--app-header-border",
    "--app-header-label",
)
BRAND_PRIMARY = "#5898d4"  # NiceGUI の既定の primary。外すと Quasar の既定(#1976D2)に変わるので、戻すときは明示する
MISMATCH_MESSAGE = "基調と背景の明るさが合っていません。ダイアログの文字が読みにくくなることがあります"


@dataclass(frozen=True)
class CustomTheme:
    base: str  # "light" | "dark"
    primary: str  # "#rrggbb"
    header: str | None  # None = primary に追従
    background: str
    foreground: str


DEFAULTS: dict[str, CustomTheme] = {
    "light": CustomTheme("light", BRAND_PRIMARY, None, "#ffffff", "#000000"),
    "dark": CustomTheme("dark", BRAND_PRIMARY, None, "#121212", "#ffffff"),
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


def parse_today_color(value: object) -> str | None:
    """`config.json`の`today_color`の読み込み。`#RRGGBB`以外は未設定(既定の色)。"""
    return normalize_hex(value)


def today_color_js(color: str | None) -> str:
    """今日の線の色(`--today`)を`body`に設定する JS。None は外して、既定(ライト・ダークで別)へ戻す。"""
    if color is None:
        return 'document.body.style.removeProperty("--today")'
    return f"document.body.style.setProperty(\"--today\", {json.dumps(color)})"


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
        "--app-header-border": f"rgba({chip}, 0.24)",  # ヘッダーの中の入力欄(プロジェクトの切り替え)
        "--app-header-label": f"rgba({chip}, 0.7)",
    }


def theme_js(theme: CustomTheme | None) -> str:
    """`body`に変数とクラスを設定する JS。None は外して、primary は NiceGUI の既定へ戻す。"""
    if theme is None:
        removes = "".join(f"s.removeProperty({json.dumps(n)});" for n in VARIABLES if n != "--q-primary")
        restore = f"s.setProperty(\"--q-primary\", {json.dumps(BRAND_PRIMARY)});"
        return f"(() => {{ const b = document.body, s = b.style; {removes}{restore} b.classList.remove('{CUSTOM_CLASS}'); }})()"
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
