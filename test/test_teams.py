import pytest

from projectapp.models import Assignee, Member, Membership, Project, Team
from projectapp.teams import (
    TeamRow,
    add_team_members,
    build_teams,
    drop_teams,
    even_split,
    membership_error,
    membership_summary,
    normalize,
    removal_impacts,
    replace_teams,
    settle_memberships,
    team_member_names,
    team_name_error,
    team_scope,
    team_weights,
    teams_with_members,
)


def ms(*pairs: tuple[str, int]) -> list[Membership]:
    return [Membership(team_id, percent) for team_id, percent in pairs]


def test_team_ids_are_part_of_used_ids_and_not_of_equality() -> None:
    project = Project("p", teams=[Team("開発", id="t1")])
    assert "t1" in project.used_ids()
    assert Team("開発", id="a") == Team("開発", id="b")


def test_a_member_has_no_teams_by_default() -> None:
    assert Member("田中").teams == []


@pytest.mark.parametrize(
    ("name", "others", "expected"),
    [
        ("開発", (), None),
        ("  開発  ", (), None),
        ("", (), "チームの名前を入力してください"),
        ("   ", (), "チームの名前を入力してください"),
        ("開\n発", (), "チームの名前に使えない文字が含まれています"),
        ("開​発", (), "チームの名前に使えない文字が含まれています"),
        ("あ" * 31, (), "チームの名前は30文字以内で入力してください"),
        ("開発", ("開発",), "チームの名前が重複しています: 開発"),
    ],
)
def test_team_name_error(
    name: str, others: tuple[str, ...], expected: str | None
) -> None:
    assert team_name_error(name, others) == expected


def test_a_30_character_team_name_is_accepted() -> None:
    assert team_name_error("あ" * 30) is None


def test_membership_error_accepts_none_one_and_several_summing_to_100() -> None:
    ids = {"a", "b", "c"}
    assert membership_error([], ids) is None
    assert membership_error(ms(("a", 100)), ids) is None
    assert membership_error(ms(("a", 60), ("b", 40)), ids) is None


@pytest.mark.parametrize(
    "teams",
    [
        ms(("zzz", 100)),  # 存在しないチーム
        ms(("a", 50), ("a", 50)),  # 同じチームの重複
        ms(("a", 60), ("b", 30)),  # 合計が 100 でない
        ms(("a", 60), ("b", 50)),
        ms(("a", 0), ("b", 100)),  # 0%
        ms(("a", 101)),
    ],
)
def test_membership_error_rejects_bad_memberships(teams: list[Membership]) -> None:
    assert membership_error(teams, {"a", "b"}) is not None


def test_membership_error_rejects_non_integer_percents() -> None:
    assert membership_error([Membership("a", 60.5)], {"a"}) is not None  # type: ignore[arg-type]
    assert membership_error([Membership("a", True)], {"a"}) is not None  # type: ignore[arg-type]
    assert membership_error([Membership("a", None)], {"a"}) is not None  # type: ignore[arg-type]


def test_normalize_keeps_the_ratio_and_gives_the_remainder_to_the_largest() -> None:
    assert normalize(ms(("a", 60), ("b", 30))) == ms(("a", 67), ("b", 33))
    assert normalize(ms(("a", 50), ("b", 50))) == ms(("a", 50), ("b", 50))
    assert normalize(ms(("a", 30))) == ms(("a", 100))
    assert normalize([]) == []


def test_normalize_gives_a_tie_remainder_to_the_first() -> None:
    assert normalize(ms(("a", 1), ("b", 1), ("c", 1))) == ms(
        ("a", 34), ("b", 33), ("c", 33)
    )


def test_even_split_sums_to_100() -> None:
    assert even_split(1) == [100]
    assert even_split(2) == [50, 50]
    assert even_split(3) == [34, 33, 33]
    assert sum(even_split(7)) == 100


def test_settle_memberships_gives_a_single_team_100_percent_whatever_the_input() -> (
    None
):
    assert settle_memberships([("a", None)], {"a"}) == ms(("a", 100))


def test_settle_memberships_reads_whole_percents() -> None:
    assert settle_memberships([("a", 60.0), ("b", 40.0)], {"a", "b"}) == ms(
        ("a", 60), ("b", 40)
    )


def test_settle_memberships_of_nothing_is_nothing() -> None:
    assert settle_memberships([], {"a"}) == []


@pytest.mark.parametrize(
    "rows",
    [
        [("a", 60.5), ("b", 39.5)],
        [("a", None), ("b", 100.0)],
        [("a", float("nan")), ("b", 50.0)],
    ],
)
def test_settle_memberships_rejects_fractions_and_blanks(
    rows: list[tuple[str, float | None]],
) -> None:
    with pytest.raises(ValueError, match="1〜100 の整数"):
        settle_memberships(rows, {"a", "b"})


def test_settle_memberships_rejects_a_total_other_than_100() -> None:
    with pytest.raises(ValueError, match="合計を 100%"):
        settle_memberships([("a", 60.0), ("b", 30.0)], {"a", "b"})


def test_membership_summary() -> None:
    teams = [Team("開発", id="a"), Team("QA", id="b")]
    assert membership_summary([], teams) == "チーム"
    assert membership_summary(ms(("a", 100)), teams) == "開発"
    assert membership_summary(ms(("a", 60), ("b", 40)), teams) == "開発 60%・QA 40%"


def test_team_member_names_keeps_member_order() -> None:
    members = [
        Member("甲", teams=ms(("a", 100))),
        Member("乙"),
        Member("丙", teams=ms(("a", 50), ("b", 50))),
    ]
    assert team_member_names(members, "a") == ["甲", "丙"]
    assert team_member_names(members, "b") == ["丙"]
    assert team_member_names(members, "zzz") == []


def test_drop_teams_renormalizes_what_is_left() -> None:
    project = Project(
        "p",
        members=[
            Member("甲", teams=ms(("a", 60), ("b", 30), ("c", 10))),
            Member("乙", teams=ms(("c", 100))),
            Member("丙", teams=ms(("a", 100))),
        ],
    )
    assert drop_teams(project, {"c"}) == 2
    assert project.members[0].teams == ms(("a", 67), ("b", 33))
    assert project.members[1].teams == []
    assert project.members[2].teams == ms(("a", 100))


def test_drop_teams_with_one_left_gives_100() -> None:
    project = Project("p", members=[Member("甲", teams=ms(("a", 60), ("b", 40)))])
    drop_teams(project, {"b"})
    assert project.members[0].teams == ms(("a", 100))


def test_build_teams_keeps_existing_ids_and_gives_new_ones() -> None:
    rows = [TeamRow("t1", " 開発 "), TeamRow(None, "QA")]
    teams = build_teams(rows, {"t1", "x"})
    assert [t.name for t in teams] == ["開発", "QA"]
    assert teams[0].id == "t1"
    assert teams[1].id not in {"t1", "x"}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([TeamRow(None, "")], "名前を入力"),
        ([TeamRow(None, "A"), TeamRow(None, "A")], "重複"),
        ([TeamRow(None, "あ" * 31)], "30文字以内"),
    ],
)
def test_build_teams_rejects_bad_rows(rows: list[TeamRow], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_teams(rows, set())


def test_replace_teams_drops_memberships_of_removed_teams() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="a"), Team("QA", id="b")],
        members=[Member("甲", teams=ms(("a", 60), ("b", 40)))],
    )
    changed = replace_teams(project, [Team("開発", id="a")])
    assert changed == 1
    assert [t.id for t in project.teams] == ["a"]
    assert project.members[0].teams == ms(("a", 100))


def test_removal_impacts_lists_only_removed_teams_that_have_members() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="a"), Team("QA", id="b"), Team("空", id="c")],
        members=[
            Member("甲", teams=ms(("a", 100))),
            Member("乙", teams=ms(("a", 50), ("b", 50))),
        ],
    )
    assert removal_impacts(project, [Team("QA", id="b"), Team("空", id="c")]) == [
        "チーム「開発」: 所属 2 人"
    ]
    assert removal_impacts(project, project.teams) == []


def test_add_team_members_adds_and_updates() -> None:
    current = [Assignee("甲", 0.5), Assignee("丙", 1.0)]
    result = add_team_members(current, ["甲", "乙"], 0.8)
    assert result == [Assignee("甲", 0.8), Assignee("丙", 1.0), Assignee("乙", 0.8)]
    assert current == [Assignee("甲", 0.5), Assignee("丙", 1.0)]  # 元は変えない


def test_teams_with_members_skips_empty_teams_in_team_order() -> None:
    project = Project(
        "p",
        teams=[Team("空", id="c"), Team("開発", id="a"), Team("QA", id="b")],
        members=[
            Member("甲", teams=ms(("b", 100))),
            Member("乙", teams=ms(("a", 50), ("b", 50))),
        ],
    )
    assert teams_with_members(project) == ["開発", "QA"]


def test_team_scope_is_the_set_of_member_names() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="a"), Team("空", id="c")],
        members=[Member("甲", teams=ms(("a", 100))), Member("乙")],
    )
    assert team_scope(project, "開発") == frozenset({"甲"})


def test_team_scope_is_none_for_unknown_empty_or_missing() -> None:
    project = Project("p", teams=[Team("空", id="c")], members=[Member("甲")])
    assert team_scope(project, "空") is None
    assert team_scope(project, "ない") is None
    assert team_scope(project, None) is None


def test_team_weights_give_each_member_the_share_in_that_team() -> None:
    project = Project(
        "P",
        members=[
            Member("田中", 1.0, teams=ms(("a", 100))),
            Member("佐藤", 1.0, teams=ms(("a", 60), ("b", 40))),
            Member("山田", 1.0),
        ],
        teams=[Team("開発", id="a"), Team("QA", id="b"), Team("空", id="z")],
    )
    assert team_weights(project, "開発") == {"田中": 1.0, "佐藤": 0.6}
    assert team_weights(project, "QA") == {"佐藤": 0.4}


def test_team_weights_are_none_for_no_unknown_or_empty_team() -> None:
    project = Project("P", members=[Member("田中", 1.0)], teams=[Team("空", id="z")])
    assert team_weights(project, None) is None
    assert team_weights(project, "ない") is None
    assert team_weights(project, "空") is None
