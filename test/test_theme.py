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
    [
        ("#AABBCC", "#aabbcc"),
        (" #aabbcc ", "#aabbcc"),
        ("#fff", None),
        ("#aabbccdd", None),
        ("red", None),
        ("aabbcc", None),
        ("#ａａｂｂｃｃ", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_normalize_hex(text: object, expected: str | None) -> None:
    assert normalize_hex(text) == expected


def test_parse_custom_theme_reads_a_valid_value_and_lowercases() -> None:
    value = {
        "base": "dark",
        "primary": "#7E57C2",
        "header": "#112233",
        "background": "#1E1E2E",
        "foreground": "#E6E6F0",
    }
    assert parse_custom_theme(value) == CustomTheme(
        "dark", "#7e57c2", "#112233", "#1e1e2e", "#e6e6f0"
    )


@pytest.mark.parametrize("value", [None, [], "dark", 3, True])
def test_parse_custom_theme_falls_back_to_the_light_default_when_not_an_object(
    value: object,
) -> None:
    assert parse_custom_theme(value) == LIGHT


def test_parse_custom_theme_reads_old_files_with_missing_keys_as_defaults() -> None:
    assert parse_custom_theme({}) == LIGHT
    assert parse_custom_theme({"base": "dark"}) == DARK


def test_parse_custom_theme_resets_only_the_invalid_keys() -> None:
    value = {
        "base": "dark",
        "primary": "#fff",
        "header": "red",
        "background": "#101010",
        "foreground": 5,
    }
    assert parse_custom_theme(value) == CustomTheme(
        "dark", DARK.primary, None, "#101010", DARK.foreground
    )


def test_parse_custom_theme_invalid_base_is_light() -> None:
    assert parse_custom_theme({"base": "blue", "background": "#101010"}).base == "light"


def test_custom_theme_to_dict_round_trips() -> None:
    theme = CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0")
    assert custom_theme_to_dict(theme) == {
        "base": "dark",
        "primary": "#7e57c2",
        "header": None,
        "background": "#1e1e2e",
        "foreground": "#e6e6f0",
    }
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
    assert (
        header_color(CustomTheme("light", "#5898d4", None, "#ffffff", "#000000"))
        == "#5898d4"
    )


def test_header_color_darkens_primary_to_55_percent_on_dark() -> None:
    assert (
        header_color(CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff"))
        == "#305475"
    )  # 88,152,212 の 55%


def test_header_color_uses_the_given_color_as_is() -> None:
    assert (
        header_color(CustomTheme("dark", "#5898d4", "#ffeb3b", "#121212", "#ffffff"))
        == "#ffeb3b"
    )


def test_css_variables() -> None:
    variables = css_variables(
        CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff")
    )
    assert variables["--q-primary"] == "#5898d4"
    assert variables["--app-bg"] == "#121212"
    assert variables["--app-fg"] == "#ffffff"
    assert variables["--app-header"] == "#305475"
    assert variables["--app-header-fg"] == "#ffffff"
    assert variables["--app-header-chip"] == "rgba(255, 255, 255, 0.18)"
    assert variables["--app-header-chip-hover"] == "rgba(255, 255, 255, 0.3)"


def test_css_variables_use_a_translucent_black_for_a_light_header() -> None:
    variables = css_variables(
        CustomTheme("light", "#5898d4", "#ffeb3b", "#ffffff", "#000000")
    )
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
    for name in (
        "--app-bg",
        "--app-fg",
        "--app-header",
        "--app-header-fg",
        "--app-header-chip",
        "--app-header-chip-hover",
        "--app-header-border",
        "--app-header-label",
    ):
        assert f'removeProperty("{name}")' in js


def test_theme_js_none_restores_the_nicegui_primary_instead_of_removing_it() -> None:
    js = theme_js(None)  # 外すと、Quasar の既定(#1976D2)になってしまう
    assert 'removeProperty("--q-primary")' not in js
    assert 'setProperty("--q-primary", "#5898d4")' in js
    assert js.count("setProperty") == 1


def test_css_variables_make_the_header_field_follow_the_header_text_color() -> None:
    dark_text = css_variables(
        CustomTheme("light", "#5898d4", "#ffeb3b", "#ffffff", "#000000")
    )
    assert dark_text["--app-header-border"] == "rgba(0, 0, 0, 0.24)"
    assert dark_text["--app-header-label"] == "rgba(0, 0, 0, 0.7)"
    white_text = css_variables(
        CustomTheme("dark", "#5898d4", None, "#121212", "#ffffff")
    )
    assert white_text["--app-header-border"] == "rgba(255, 255, 255, 0.24)"
    assert white_text["--app-header-label"] == "rgba(255, 255, 255, 0.7)"


def test_no_warnings_for_the_defaults() -> None:
    assert warnings(LIGHT) == []
    assert warnings(DARK) == []


def test_low_contrast_warns_with_the_ratio_floored_to_one_decimal() -> None:
    result = warnings(CustomTheme("light", "#5898d4", None, "#ffffff", "#999999"))
    assert result == [
        "文字と背景のコントラスト比が 2.8:1 です。読みにくい可能性があります"
    ]


def test_contrast_of_exactly_4_5_does_not_warn() -> None:
    assert (
        warnings(CustomTheme("light", "#5898d4", None, "#ffffff", "#767676")) == []
    )  # 4.54:1


def test_mismatched_brightness_warns() -> None:
    assert warnings(CustomTheme("light", "#5898d4", None, "#000000", "#ffffff")) == [
        MISMATCH_MESSAGE
    ]
    assert warnings(CustomTheme("dark", "#5898d4", None, "#ffffff", "#000000")) == [
        MISMATCH_MESSAGE
    ]


def test_both_warnings_can_appear_together() -> None:
    result = warnings(CustomTheme("light", "#5898d4", None, "#101010", "#202020"))
    assert len(result) == 2 and MISMATCH_MESSAGE in result


def test_parse_today_color_reads_a_valid_color_and_lowercases() -> None:
    from projectapp.theme import parse_today_color

    assert parse_today_color("#1E88E5") == "#1e88e5"


@pytest.mark.parametrize("value", [None, "", "red", "#12345", "#gggggg", 5, [], {}])
def test_parse_today_color_reads_anything_else_as_unset(value: object) -> None:
    from projectapp.theme import parse_today_color

    assert parse_today_color(value) is None


def test_today_color_js_sets_the_variable_on_the_body() -> None:
    from projectapp.theme import today_color_js

    assert (
        today_color_js("#1e88e5")
        == 'document.body.style.setProperty("--today", "#1e88e5")'
    )


def test_today_color_js_none_removes_the_variable_so_the_default_returns() -> None:
    from projectapp.theme import today_color_js

    assert today_color_js(None) == 'document.body.style.removeProperty("--today")'


def test_parse_warning_color_reads_a_valid_color_and_lowercases() -> None:
    from projectapp.theme import parse_warning_color

    assert parse_warning_color("#FDD835") == "#fdd835"


@pytest.mark.parametrize("value", [None, "", "yellow", "#12345", "#gggggg", 5, [], {}])
def test_parse_warning_color_reads_anything_else_as_unset(value: object) -> None:
    from projectapp.theme import parse_warning_color

    assert parse_warning_color(value) is None


def test_warning_color_js_sets_and_removes_the_variable() -> None:
    from projectapp.theme import warning_color_js

    assert (
        warning_color_js("#fdd835")
        == 'document.body.style.setProperty("--warning", "#fdd835")'
    )
    assert warning_color_js(None) == 'document.body.style.removeProperty("--warning")'
