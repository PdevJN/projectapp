from datetime import date

from projectapp.dashboard import PeriodKind
from projectapp.dashboard_views import (
    DEFAULT_ORDER,
    MAX_VIEW_NAME,
    STANDARD_NAME,
    CardId,
    ViewSpec,
    hidden_cards,
    hide_card,
    move_card,
    normalize_cards,
    parse_card_move,
    resolve_member,
    show_card,
    standard_view,
    validate_custom,
    validate_name,
)


def test_the_default_order_matches_the_current_dashboard() -> None:
    assert DEFAULT_ORDER == (
        CardId.TEAM, CardId.PROGRESS, CardId.LOAD, CardId.HEATMAP, CardId.HOURS, CardId.DUE,
    )


def test_the_standard_view_is_todays_dashboard() -> None:
    assert standard_view() == ViewSpec(STANDARD_NAME, PeriodKind.WEEK, None, False, DEFAULT_ORDER, None)


def test_validate_custom_accepts_up_to_400_days_and_rejects_the_rest() -> None:
    assert validate_custom(date(2026, 10, 1), date(2026, 10, 31)) is None
    assert validate_custom(date(2026, 1, 1), date(2027, 2, 4)) is None  # ちょうど 400 日
    assert "長すぎ" in (validate_custom(date(2026, 1, 1), date(2027, 2, 5)) or "")
    assert validate_custom(date(2026, 10, 31), date(2026, 10, 1)) is not None  # 逆順
    assert validate_custom(date(1999, 12, 31), date(2000, 1, 2)) is not None  # 年の範囲外
    assert validate_custom(date(2100, 12, 30), date(2101, 1, 2)) is not None


def test_normalize_cards_drops_unknown_and_duplicate_ids_but_keeps_order() -> None:
    assert normalize_cards(["due", "x", "team", "due", 3, None]) == (CardId.DUE, CardId.TEAM)
    assert normalize_cards([]) == ()  # 全部隠したビュー
    assert normalize_cards("team") == DEFAULT_ORDER  # リストでなければ既定の順
    assert normalize_cards(None) == DEFAULT_ORDER


def test_validate_name_rejects_empty_long_control_standard_and_duplicates() -> None:
    assert validate_name("週次", ["月次"]) is None
    assert validate_name("a" * MAX_VIEW_NAME, []) is None
    assert validate_name("", []) is not None
    assert validate_name("a" * (MAX_VIEW_NAME + 1), []) is not None
    assert validate_name("a\nb", []) is not None
    assert validate_name(STANDARD_NAME, []) is not None
    assert validate_name("月次", ["月次"]) is not None


def test_move_card_inserts_before_the_target_or_at_the_end() -> None:
    order = (CardId.TEAM, CardId.PROGRESS, CardId.LOAD)
    assert move_card(order, CardId.LOAD, CardId.TEAM) == (CardId.LOAD, CardId.TEAM, CardId.PROGRESS)
    assert move_card(order, CardId.TEAM, None) == (CardId.PROGRESS, CardId.LOAD, CardId.TEAM)
    assert move_card(order, CardId.TEAM, CardId.TEAM) == order  # 自分の手前は動かさない
    assert move_card(order, CardId.TEAM, CardId.DUE) == (CardId.PROGRESS, CardId.LOAD, CardId.TEAM)  # 隠れた手前は末尾


def test_move_card_shows_a_hidden_card_at_the_position() -> None:
    order = (CardId.TEAM, CardId.LOAD)
    assert move_card(order, CardId.DUE, CardId.LOAD) == (CardId.TEAM, CardId.DUE, CardId.LOAD)


def test_hide_and_show_card() -> None:
    order = (CardId.TEAM, CardId.LOAD)
    assert hide_card(order, CardId.TEAM) == (CardId.LOAD,)
    assert hide_card(order, CardId.DUE) == order
    assert show_card(order, CardId.DUE) == (CardId.TEAM, CardId.LOAD, CardId.DUE)
    assert show_card(order, CardId.TEAM) == order


def test_hidden_cards_skips_the_heatmap_unless_cross_is_on() -> None:
    order = (CardId.TEAM,)
    assert CardId.HEATMAP not in hidden_cards(order, cross=False)
    assert CardId.HEATMAP in hidden_cards(order, cross=True)
    assert hidden_cards(order, cross=True)[0] is CardId.PROGRESS  # 既定の順


def test_resolve_member_falls_back_to_everyone() -> None:
    assert resolve_member("田中", ["田中", "佐藤"]) == "田中"
    assert resolve_member("鈴木", ["田中"]) is None
    assert resolve_member(None, ["田中"]) is None


def test_parse_card_move_accepts_only_known_ids() -> None:
    assert parse_card_move({"card": "load", "before": "team"}) == (CardId.LOAD, CardId.TEAM)
    assert parse_card_move({"card": "load", "before": None}) == (CardId.LOAD, None)
    assert parse_card_move({"card": "x", "before": None}) is None
    assert parse_card_move({"card": "load", "before": "x"}) is None
    assert parse_card_move({"card": "load"}) == (CardId.LOAD, None)
    assert parse_card_move("load") is None
    assert parse_card_move(None) is None
