from dataclasses import replace
from datetime import date

from projectapp.dashboard import PeriodKind
from projectapp.dashboard_views import (
    DEFAULT_ORDER,
    MAX_VIEW_NAME,
    MAX_VIEWS,
    STANDARD_NAME,
    CardId,
    ViewSpec,
    hidden_cards,
    hide_card,
    move_card,
    normalize_cards,
    parse_card_move,
    resolve_member,
    resolve_team,
    show_card,
    standard_view,
    validate_custom,
    validate_name,
    views_from_config,
    views_to_config,
)


def test_the_default_order_matches_the_current_dashboard() -> None:
    assert DEFAULT_ORDER == (
        CardId.TEAM,
        CardId.PROGRESS,
        CardId.LOAD,
        CardId.HEATMAP,
        CardId.HOURS,
        CardId.BACKLOG,
        CardId.DUE,
    )


def test_a_view_saved_before_the_backlog_card_hides_it() -> None:
    saved = normalize_cards(["team", "progress", "load", "heatmap", "hours", "due"])
    assert CardId.BACKLOG in hidden_cards(saved, False)


def test_the_standard_view_is_todays_dashboard() -> None:
    assert standard_view() == ViewSpec(
        STANDARD_NAME, PeriodKind.WEEK, None, False, DEFAULT_ORDER, None
    )


def test_validate_custom_accepts_up_to_400_days_and_rejects_the_rest() -> None:
    assert validate_custom(date(2026, 10, 1), date(2026, 10, 31)) is None
    assert (
        validate_custom(date(2026, 1, 1), date(2027, 2, 4)) is None
    )  # ちょうど 400 日
    assert "長すぎ" in (validate_custom(date(2026, 1, 1), date(2027, 2, 5)) or "")
    assert validate_custom(date(2026, 10, 31), date(2026, 10, 1)) is not None  # 逆順
    assert (
        validate_custom(date(1999, 12, 31), date(2000, 1, 2)) is not None
    )  # 年の範囲外
    assert validate_custom(date(2100, 12, 30), date(2101, 1, 2)) is not None


def test_normalize_cards_drops_unknown_and_duplicate_ids_but_keeps_order() -> None:
    assert normalize_cards(["due", "x", "team", "due", 3, None]) == (
        CardId.DUE,
        CardId.TEAM,
    )
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
    assert move_card(order, CardId.LOAD, CardId.TEAM) == (
        CardId.LOAD,
        CardId.TEAM,
        CardId.PROGRESS,
    )
    assert move_card(order, CardId.TEAM, None) == (
        CardId.PROGRESS,
        CardId.LOAD,
        CardId.TEAM,
    )
    assert move_card(order, CardId.TEAM, CardId.TEAM) == order  # 自分の手前は動かさない
    assert move_card(order, CardId.TEAM, CardId.DUE) == (
        CardId.PROGRESS,
        CardId.LOAD,
        CardId.TEAM,
    )  # 隠れた手前は末尾


def test_move_card_shows_a_hidden_card_at_the_position() -> None:
    order = (CardId.TEAM, CardId.LOAD)
    assert move_card(order, CardId.DUE, CardId.LOAD) == (
        CardId.TEAM,
        CardId.DUE,
        CardId.LOAD,
    )


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
    assert parse_card_move({"card": "load", "before": "team"}) == (
        CardId.LOAD,
        CardId.TEAM,
    )
    assert parse_card_move({"card": "load", "before": None}) == (CardId.LOAD, None)
    assert parse_card_move({"card": "x", "before": None}) is None
    assert parse_card_move({"card": "load", "before": "x"}) is None
    assert parse_card_move({"card": "load"}) == (CardId.LOAD, None)
    assert parse_card_move("load") is None
    assert parse_card_move(None) is None


def view(name: str = "月次", **changes: object) -> ViewSpec:
    base = ViewSpec(
        name, PeriodKind.MONTH, "田中", True, (CardId.LOAD, CardId.DUE), None
    )
    return replace(base, **changes)


def test_views_round_trip_including_a_custom_period() -> None:
    views = [
        view(),
        view(
            "十月",
            period=PeriodKind.CUSTOM,
            custom=(date(2026, 10, 1), date(2026, 10, 31)),
            member=None,
        ),
    ]
    assert views_from_config(views_to_config(views)) == views
    assert views_to_config(views)[1]["custom"] == {
        "start": "2026-10-01",
        "end": "2026-10-31",
    }
    assert "custom" not in views_to_config(views)[0]


def test_views_from_config_drops_only_the_bad_entries() -> None:
    good = views_to_config([view("月次")])[0]
    raw = [
        good,
        "x",
        {**good, "name": ""},
        {**good, "name": STANDARD_NAME},
        {**good, "name": "週", "period": "未知"},
        {**good, "name": "月次"},  # 重複は最初の 1 件だけ
        {**good, "name": "カード", "cards": ["due", "zzz", "due"]},
        {**good, "name": "文字列", "cards": "due"},
        {**good, "name": "メンバー", "member": 3, "cross": "yes"},
    ]
    views = views_from_config(raw)
    assert [v.name for v in views] == ["月次", "カード", "文字列", "メンバー"]
    assert views[1].cards == (CardId.DUE,)
    assert views[2].cards == DEFAULT_ORDER
    assert (views[3].member, views[3].cross) == (None, False)


def test_views_from_config_ignores_bad_dates_but_keeps_the_view() -> None:
    good = views_to_config(
        [
            view(
                "十月",
                period=PeriodKind.CUSTOM,
                custom=(date(2026, 10, 1), date(2026, 10, 31)),
            )
        ]
    )[0]
    for custom in (
        {"start": "2026-10-31", "end": "2026-10-01"},  # 逆順
        {"start": "2026-01-01", "end": "2027-02-05"},  # 401 日
        {"start": "1999-01-01", "end": "1999-01-02"},  # 範囲外の年
        {"start": "x", "end": "y"},
        {"start": "2026-10-01"},
        "2026-10-01",
        None,
    ):
        (loaded,) = views_from_config([{**good, "custom": custom}])
        assert (
            loaded.name == "十月"
            and loaded.period is PeriodKind.CUSTOM
            and loaded.custom is None
        )
    month = views_to_config([view("月次")])[0]
    (loaded,) = views_from_config(
        [{**month, "custom": {"start": "2026-10-01", "end": "2026-10-31"}}]
    )
    assert loaded.custom is None  # `指定` 以外のビューは日付を持たない


def test_views_from_config_caps_the_count_and_rejects_non_lists() -> None:
    raw = [
        {**views_to_config([view("a")])[0], "name": f"v{i}"}
        for i in range(MAX_VIEWS + 5)
    ]
    assert len(views_from_config(raw)) == MAX_VIEWS
    for bad in (None, "x", 3, {"a": 1}):
        assert views_from_config(bad) == []


def test_team_round_trips_through_the_config() -> None:
    spec = ViewSpec(
        "開発ビュー", PeriodKind.WEEK, None, False, DEFAULT_ORDER, team="開発"
    )
    [loaded] = views_from_config(views_to_config([spec]))
    assert loaded.team == "開発" and loaded.member is None


def test_a_view_without_team_reads_as_no_team() -> None:
    raw = [
        {
            "name": "旧",
            "period": PeriodKind.WEEK.value,
            "member": None,
            "cross": False,
            "cards": [c.value for c in DEFAULT_ORDER],
        }
    ]
    [loaded] = views_from_config(raw)
    assert loaded.team is None


def test_a_non_string_or_empty_team_reads_as_no_team() -> None:
    base = {
        "name": "x",
        "period": PeriodKind.WEEK.value,
        "member": None,
        "cross": False,
        "cards": [c.value for c in DEFAULT_ORDER],
    }
    for bad in (3, "", None, ["開発"]):
        [loaded] = views_from_config([{**base, "team": bad}])
        assert loaded.team is None


def test_resolve_team_returns_none_for_a_team_that_left_the_roster() -> None:
    assert resolve_team("開発", ["開発", "QA"]) == "開発"
    assert resolve_team("消えた", ["開発"]) is None
    assert resolve_team(None, ["開発"]) is None
