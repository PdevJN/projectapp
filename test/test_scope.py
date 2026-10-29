from projectapp.scope import ALL, TEAM_KEY, read_scope, scope_options, scope_value, team_key


def test_a_member_name_is_its_own_value() -> None:
    assert read_scope("田中") == ("田中", None)
    assert scope_value("田中", None) == "田中"


def test_everyone_is_the_empty_value() -> None:
    assert ALL == ""
    assert read_scope("") == (None, None)
    assert read_scope(None) == (None, None)
    assert scope_value(None, None) == ""


def test_a_team_value_carries_the_prefix_and_round_trips() -> None:
    assert team_key("開発").startswith(TEAM_KEY)
    assert read_scope(team_key("開発")) == (None, "開発")
    assert scope_value(None, "開発") == team_key("開発")


def test_a_member_named_like_a_team_label_is_still_a_member() -> None:
    assert read_scope("チーム: 開発") == ("チーム: 開発", None)


def test_the_team_wins_when_both_are_given() -> None:
    assert scope_value("田中", "開発") == team_key("開発")


def test_an_empty_team_name_means_everyone() -> None:
    assert read_scope(TEAM_KEY) == (None, None)


def test_options_list_everyone_then_members_then_labelled_teams() -> None:
    options = scope_options("全員", ["田中", "鈴木"], ["開発"])
    assert list(options.items()) == [("", "全員"), ("田中", "田中"), ("鈴木", "鈴木"), (team_key("開発"), "チーム: 開発")]


def test_options_without_teams_are_the_member_list_only() -> None:
    assert scope_options("すべての担当者", ["田中"], []) == {"": "すべての担当者", "田中": "田中"}
