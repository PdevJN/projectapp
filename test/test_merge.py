from datetime import date, time

import pytest

from projectapp.merge import DELETED, OURS, THEIRS, Conflict, merge_projects
from projectapp.models import ActualMode, Category, Level, Member, Parameter, Project, UrlTemplate


def proj(**kw) -> Project:
    return Project(name="p", base_date=date(2026, 10, 1), **kw)


def test_unchanged_projects_merge_to_the_same() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    result = merge_projects(base, base, base)
    assert result.conflicts == [] and result.notes == []
    assert result.project == base


def test_settings_take_each_sides_change() -> None:
    base = proj()
    ours = proj(daily_hours=7.0)
    theirs = proj(work_start=time(10, 0))
    merged = merge_projects(base, ours, theirs).project
    assert merged.daily_hours == 7.0 and merged.work_start == time(10, 0)


def test_settings_conflict_defaults_to_ours_and_follows_choices() -> None:
    base, ours, theirs = proj(), proj(daily_hours=7.0), proj(daily_hours=5.0)
    result = merge_projects(base, ours, theirs)
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.kind == "setting" and conflict.ours == 7.0 and conflict.theirs == 5.0
    assert result.project.daily_hours == 7.0
    chosen = merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project
    assert chosen.daily_hours == 5.0


def test_same_value_on_both_sides_is_not_a_conflict() -> None:
    base, ours, theirs = proj(), proj(daily_hours=7.0), proj(daily_hours=7.0)
    assert merge_projects(base, ours, theirs).conflicts == []


def test_actual_mode_merges() -> None:
    merged = merge_projects(proj(), proj(actual_mode=ActualMode.INTERVALS), proj()).project
    assert merged.actual_mode is ActualMode.INTERVALS


def test_members_merge_by_id_field_by_field() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2")])
    ours = proj(members=[Member("甲", 1.2, id="m1"), Member("乙", 1.0, id="m2")])  # 比率を変えた
    theirs = proj(members=[Member("甲改", 1.0, id="m1"), Member("乙", 1.0, id="m2"), Member("丙", 0.8, id="m3")])
    merged = merge_projects(base, ours, theirs).project
    assert [(m.id, m.name, m.ratio) for m in merged.members] == [("m1", "甲改", 1.2), ("m2", "乙", 1.0), ("m3", "丙", 0.8)]


def test_member_deleted_on_one_side_and_unchanged_on_the_other_is_deleted() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2")])
    theirs = proj(members=[Member("甲", 1.0, id="m1")])
    merged = merge_projects(base, base, theirs)
    assert [m.id for m in merged.project.members] == ["m1"] and merged.conflicts == []


def test_delete_versus_change_is_a_conflict_with_both_choices() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[])  # 自分が削除
    theirs = proj(members=[Member("甲", 0.5, id="m1")])  # 相手が変更
    result = merge_projects(base, ours, theirs)
    (conflict,) = result.conflicts
    assert conflict.field == DELETED and conflict.ours is None and conflict.theirs is not None
    assert result.project.members == []  # 既定は自分
    kept = merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project
    assert [(m.id, m.ratio) for m in kept.members] == [("m1", 0.5)]


def test_same_name_members_added_on_both_sides_both_stay() -> None:
    base = proj()
    ours = proj(members=[Member("丁", 1.0, id="a1")])
    theirs = proj(members=[Member("丁", 1.0, id="b1")])
    merged = merge_projects(base, ours, theirs).project
    assert {m.id for m in merged.members} == {"a1", "b1"}


def test_categories_merge_by_id() -> None:
    base = proj(categories=[Category("開発", id="c1")])
    ours = proj(categories=[Category("開発", color="red", id="c1")])
    theirs = proj(categories=[Category("開発", prj_code="PRJ-1", id="c1"), Category("保守", id="c2")])
    merged = merge_projects(base, ours, theirs).project
    assert [(c.id, c.color, c.prj_code) for c in merged.categories] == [("c1", "red", "PRJ-1"), ("c2", "blue", "")]


def test_parameters_and_url_templates_merge_by_name() -> None:
    p1 = Parameter("経験", [Level("低", -0.1), Level("高", 0.2)])
    base = proj(parameters=[p1], url_templates=[UrlTemplate("チケット", "https://e.com/{ID}")])
    ours = proj(parameters=[Parameter("経験", [Level("低", -0.1), Level("高", 0.3)])], url_templates=base.url_templates)
    theirs = proj(parameters=[p1, Parameter("言語", [Level("日", 0.0)])], url_templates=[UrlTemplate("チケット", "https://e.com/t/{ID}")])
    merged = merge_projects(base, ours, theirs).project
    assert [p.name for p in merged.parameters] == ["経験", "言語"]
    assert merged.parameters[0].levels[1].value == 0.3
    assert merged.url_templates[0].pattern == "https://e.com/t/{ID}"


def test_added_items_follow_the_theirs_predecessor_and_one_sided_reorders_win() -> None:
    a, b, c = (Member(n, 1.0, id=n) for n in "abc")
    base = proj(members=[a, b, c])
    theirs = proj(members=[c, a, b])  # 相手だけが並べ替えた
    assert [m.id for m in merge_projects(base, base, theirs).project.members] == ["c", "a", "b"]
    d = Member("d", 1.0, id="d")
    theirs = proj(members=[a, d, b, c])  # 相手が a の次に追加
    ours = proj(members=[b, a, c])  # 自分が並べ替えた
    assert [m.id for m in merge_projects(base, ours, theirs).project.members] == ["b", "a", "d", "c"]


@pytest.mark.parametrize(
    ("value", "text"),
    [(None, "(削除)"), (True, "はい"), (3, "3"), ([], "(なし)"), (["a", "b"], "a, b")],
)
def test_format_value(value: object, text: str) -> None:
    from projectapp.merge import format_value

    assert format_value(value) == text
