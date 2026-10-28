from datetime import date, datetime, time

import pytest

from projectapp.merge import DELETED, OURS, THEIRS, Conflict, merge_projects
from projectapp.models import (
    ActualMode,
    Assignee,
    Category,
    Event,
    Level,
    Member,
    Parameter,
    Priority,
    Project,
    ReferenceMode,
    ReferenceValue,
    Section,
    Task,
    TaskKind,
    UrlTemplate,
    WorkDay,
    union_assignees,
)


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


def ev(id: str, start: str = "2026-10-01", end: str = "2026-10-03", text: str = "休み", color: str = "gray") -> Event:
    return Event(date.fromisoformat(start), date.fromisoformat(end), text, color, id=id)


def test_events_merge_by_id_field_by_field_and_stay_sorted() -> None:
    base = proj(events=[ev("e1")])
    ours = proj(events=[ev("e1", color="red")])
    theirs = proj(events=[ev("e1", end="2026-10-05"), ev("e2", "2026-09-20", "2026-09-21", "研修")])
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == []
    assert [(e.id, e.end.isoformat(), e.color) for e in result.project.events] == [("e2", "2026-09-21", "gray"), ("e1", "2026-10-05", "red")]


def test_event_changed_differently_is_a_conflict_with_a_readable_label() -> None:
    base = proj(events=[ev("e1")])
    ours = proj(events=[ev("e1", text="休暇")])
    theirs = proj(events=[ev("e1", text="研修")])
    result = merge_projects(base, ours, theirs, {("event", "e1", "文字列"): THEIRS})
    (conflict,) = result.conflicts
    assert (conflict.kind, conflict.label, conflict.field) == ("event", "休暇", "文字列")
    assert result.project.events[0].text == "研修"
    assert merge_projects(base, ours, theirs).project.events[0].text == "休暇"


def test_event_deleted_by_one_side_and_changed_by_the_other_is_a_conflict() -> None:
    base = proj(events=[ev("e1")])
    ours = proj(events=[])
    theirs = proj(events=[ev("e1", color="red")])
    result = merge_projects(base, ours, theirs, {("event", "e1", DELETED): THEIRS})
    assert [e.id for e in result.project.events] == ["e1"]
    assert merge_projects(base, ours, theirs).project.events == []


def test_event_deleted_by_one_side_and_unchanged_by_the_other_is_deleted() -> None:
    base = proj(events=[ev("e1"), ev("e2", "2026-10-10", "2026-10-11")])
    ours = proj(events=[ev("e2", "2026-10-10", "2026-10-11")])
    theirs = base
    assert [e.id for e in merge_projects(base, ours, theirs).project.events] == ["e2"]


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


def task(name: str, id: str, **kw) -> Task:
    return Task(name, id=id, **kw)


def names_of(project: Project) -> list[str]:
    return [t.name for t in project.all_tasks()]


def test_tasks_merge_field_by_field() -> None:
    base = proj(tasks=[task("調査", "t1", effort_hours=4.0)])
    ours = proj(tasks=[task("調査", "t1", effort_hours=8.0)])
    theirs = proj(tasks=[task("調査(改)", "t1", effort_hours=4.0)])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert (merged.project.tasks[0].name, merged.project.tasks[0].effort_hours) == ("調査(改)", 8.0)
    assert merged.project.tasks[0].id == "t1"


def test_same_field_changed_differently_is_a_conflict() -> None:
    base = proj(tasks=[task("a", "t1", effort_hours=4.0)])
    ours = proj(tasks=[task("a", "t1", effort_hours=8.0)])
    theirs = proj(tasks=[task("a", "t1", effort_hours=2.0)])
    result = merge_projects(base, ours, theirs)
    (conflict,) = result.conflicts
    assert (conflict.kind, conflict.key, conflict.field, conflict.ours, conflict.theirs) == ("task", "t1", "工数", 8.0, 2.0)
    assert result.project.tasks[0].effort_hours == 8.0
    assert merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project.tasks[0].effort_hours == 2.0


def test_task_progress_merges_field_by_field() -> None:
    base = proj(tasks=[task("a", "t1")])
    ours = proj(tasks=[task("a", "t1", progress=40)])
    theirs = proj(tasks=[task("a", "t1", effort_hours=2.0)])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert (merged.project.tasks[0].progress, merged.project.tasks[0].effort_hours) == (40, 2.0)


def test_task_progress_changed_differently_is_a_conflict_with_a_readable_label() -> None:
    base = proj(tasks=[task("a", "t1", progress=10)])
    ours = proj(tasks=[task("a", "t1", progress=40)])
    theirs = proj(tasks=[task("a", "t1", progress=70)])
    (conflict,) = merge_projects(base, ours, theirs).conflicts
    assert (conflict.field, conflict.ours, conflict.theirs) == ("進捗度", 40, 70)


def test_added_task_goes_after_its_predecessor_sibling() -> None:
    base = proj(tasks=[task("a", "t1"), task("b", "t2")])
    theirs = proj(tasks=[task("a", "t1"), task("new", "t3"), task("b", "t2")])
    ours = proj(tasks=[task("a", "t1", effort_hours=1.0), task("b", "t2")])
    assert names_of(merge_projects(base, ours, theirs).project) == ["a", "new", "b"]


def test_task_deleted_by_one_side_and_unchanged_by_the_other() -> None:
    base = proj(tasks=[task("a", "t1"), task("b", "t2")])
    theirs = proj(tasks=[task("b", "t2")])
    merged = merge_projects(base, base, theirs)
    assert names_of(merged.project) == ["b"] and merged.conflicts == []


def test_task_deleted_by_theirs_and_changed_by_ours_is_a_conflict() -> None:
    base = proj(tasks=[task("a", "t1")])
    ours = proj(tasks=[task("a", "t1", effort_hours=3.0)])
    result = merge_projects(base, ours, proj())
    (conflict,) = result.conflicts
    assert conflict.field == DELETED and conflict.theirs is None
    assert names_of(result.project) == ["a"]  # 既定は自分
    assert names_of(merge_projects(base, ours, proj(), {conflict.id: THEIRS}).project) == []


def test_task_moved_into_a_section_by_theirs() -> None:
    base = proj(sections=[Section("S", id="s1")], tasks=[task("a", "t1")])
    ours = proj(sections=[Section("S", id="s1")], tasks=[task("a", "t1", effort_hours=2.0)])
    theirs = proj(sections=[Section("S", tasks=[task("a", "t1")], id="s1")])
    merged = merge_projects(base, ours, theirs).project
    assert merged.tasks == [] and [t.name for t in merged.sections[0].tasks] == ["a"]
    assert merged.sections[0].tasks[0].effort_hours == 2.0


def test_sections_merge_and_keep_subsections() -> None:
    sub = Section("子", tasks=[task("x", "t9")], id="s2")
    base = proj(sections=[Section("親", sections=[sub], id="s1")])
    theirs = proj(sections=[Section("親改", sections=[sub], id="s1")])
    ours = proj(sections=[Section("親", sections=[Section("子", tasks=[task("x", "t9"), task("y", "t10")], id="s2")], id="s1")])
    merged = merge_projects(base, ours, theirs).project
    assert merged.sections[0].name == "親改"
    assert [t.name for t in merged.sections[0].sections[0].tasks] == ["x", "y"]


def test_predecessors_pointing_to_deleted_tasks_are_dropped() -> None:
    base = proj(tasks=[task("a", "t1"), task("b", "t2", predecessors=["t1"])])
    theirs = proj(tasks=[task("b", "t2", predecessors=["t1"])])
    merged = merge_projects(base, base, theirs).project
    assert merged.tasks[0].predecessors == []


def test_member_renamed_by_theirs_renames_the_assignees_of_ours_tasks() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 0.5)])])
    ours = proj(
        members=[Member("甲", 1.0, id="m1")],
        tasks=[task("a", "t1", assignees=[Assignee("甲", 0.5)]), task("b", "t2", assignees=[Assignee("甲", 1.0)])],
    )
    theirs = proj(members=[Member("甲改", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲改", 0.5)])])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert [(t.name, [a.name for a in t.assignees]) for t in merged.project.tasks] == [("a", ["甲改"]), ("b", ["甲改"])]


def test_assignee_of_a_deleted_member_is_dropped_with_a_note() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1")])
    ours = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)])])
    theirs = proj(members=[], tasks=[task("a", "t1")])  # メンバーの記録は自分が変えていないので、衝突なしで削除される
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == [] and merged.project.members == []
    assert merged.project.tasks[0].assignees == []
    assert any("担当者を外しました" in n and "a" in n for n in merged.notes)


def test_tasks_of_a_deleted_section_move_to_the_root_with_a_note() -> None:
    base = proj(sections=[Section("S", id="s1")])
    ours = proj(sections=[])  # 自分が(変更のない)セクションを削除
    theirs = proj(sections=[Section("S", tasks=[task("new", "t1")], id="s1")])
    merged = merge_projects(base, ours, theirs)
    assert [t.name for t in merged.project.tasks] == ["new"] and merged.project.sections == []
    assert any("ルートへ移しました" in n for n in merged.notes)


def test_category_removed_by_theirs_unsets_ours_tasks() -> None:
    base = proj(categories=[Category("開発", id="c1")], tasks=[task("a", "t1")])
    ours = proj(categories=[Category("開発", id="c1")], tasks=[task("a", "t1", category_id="c1")])
    theirs = proj(categories=[], tasks=[task("a", "t1")])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == [] and merged.project.categories == []
    assert merged.project.tasks[0].category_id is None
    assert any("カテゴリを外しました" in n for n in merged.notes)


def test_merge_files_round_trips_through_text() -> None:
    from projectapp.merge import merge_files
    from projectapp.storage import dumps_project, parse_project

    base = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)], effort_hours=4.0)])
    ours = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)], effort_hours=8.0)])
    theirs = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)], effort_hours=4.0, priority=Priority.HIGH)])
    result = merge_files("p.json", dumps_project(base), dumps_project(ours), dumps_project(theirs))
    assert result.conflicts == []
    merged = parse_project(result.text, "p")
    assert merged.tasks[0].effort_hours == 8.0 and merged.tasks[0].priority.value == "高"


def test_merge_files_rejects_unreadable_text() -> None:
    from projectapp.merge import merge_files

    with pytest.raises(ValueError):
        merge_files("p.json", "{", "{", "{")


def test_same_name_members_added_on_both_sides_keep_both_after_a_round_trip() -> None:
    """同名で id の違うメンバーは、読み直すと片方が捨てられる。名前を変えて両方残し、通知する。"""
    from projectapp.merge import merge_files
    from projectapp.storage import dumps_project, parse_project

    base = proj()
    ours = proj(members=[Member("丁", 1.0, id="a1")], tasks=[task("x", "t1", assignees=[Assignee("丁", 1.0)])])
    theirs = proj(members=[Member("丁", 1.5, id="b1")], tasks=[task("y", "t2", assignees=[Assignee("丁", 1.0)])])
    result = merge_files("p.json", dumps_project(base), dumps_project(ours), dumps_project(theirs))
    merged = parse_project(result.text, "p")
    assert {m.id: m.ratio for m in merged.members} == {"a1": 1.0, "b1": 1.5}  # 両方残る
    assert len({m.name for m in merged.members}) == 2 and {m.name for m in merged.members} == {"丁", "丁 (2)"}
    ratio_of = {m.name: m.ratio for m in merged.members}
    by_task = {t.name: [ratio_of[a.name] for a in t.assignees] for t in merged.tasks}
    assert by_task == {"x": [1.0], "y": [1.5]}  # 担当者は、それぞれ元のメンバーを指したまま
    assert any("丁 (2)" in n for n in result.notes)


def test_a_member_icon_changed_on_one_side_is_taken(icon: str) -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[Member("甲", 1.0, id="m1", icon=icon)])
    result = merge_projects(base, ours, base)
    assert result.conflicts == [] and result.project.members[0].icon == icon


def test_different_member_icons_on_both_sides_conflict(make_png) -> None:
    from projectapp.icons import make_icon

    one, two = make_icon(make_png(color=(255, 0, 0, 255))), make_icon(make_png(color=(0, 0, 255, 255)))
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[Member("甲", 1.0, id="m1", icon=one)])
    theirs = proj(members=[Member("甲", 1.0, id="m1", icon=two)])
    result = merge_projects(base, ours, theirs, {("member", "m1", "アイコン"): THEIRS})
    (conflict,) = result.conflicts
    assert (conflict.kind, conflict.field) == ("member", "アイコン")
    assert result.project.members[0].icon == two


def test_the_icon_survives_the_rename_of_a_same_name_member(icon: str) -> None:
    base = proj()
    ours = proj(members=[Member("甲", 1.0, id="m1", icon=icon)])
    theirs = proj(members=[Member("甲", 1.0, id="m2")])
    merged = merge_projects(base, ours, theirs).project
    assert sorted(m.name for m in merged.members) == ["甲", "甲 (2)"]
    assert {m.id: m.icon for m in merged.members} == {"m1": icon, "m2": ""}  # 改名されても、アイコンは持ち主に付く


def test_format_value_shortens_an_image_data_uri(icon: str) -> None:
    from projectapp.merge import format_value

    text = format_value(icon)
    assert text.startswith("画像(") and "data:" not in text and len(text) < 30


def wd(day: str, end: int = 16) -> WorkDay:
    return WorkDay(date.fromisoformat(day), time(13), time(end))


def mem(*days: WorkDay) -> Member:
    return Member("甲", 1.0, id="m1", work_days=list(days))


def test_member_work_days_merge_by_member_and_date() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[mem(wd("2026-10-17"), wd("2026-10-18", 12))])
    theirs = proj(members=[mem(wd("2026-10-17", 17))])
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == []
    assert [(w.day, w.end) for w in result.project.members[0].work_days] == [
        (date(2026, 10, 17), time(17)),
        (date(2026, 10, 18), time(12)),
    ]


def test_member_work_day_window_is_one_item() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[mem(WorkDay(date(2026, 10, 17)))])
    theirs = proj(members=[mem(wd("2026-10-17", 18))])
    result = merge_projects(base, ours, theirs, {("work_day", "m1:2026-10-17", "時間帯"): THEIRS})
    (conflict,) = result.conflicts
    assert (conflict.ours, conflict.theirs) == ("休み", "13:00〜18:00")
    assert result.project.members[0].work_days == [wd("2026-10-17", 18)]


def test_work_days_of_a_deleted_member_are_dropped() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[])
    theirs = proj(members=[mem(wd("2026-10-17"))])
    assert merge_projects(base, ours, theirs).project.members == []


def test_member_work_day_conflict_is_labelled_with_the_member_and_date() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[mem(wd("2026-10-17", 17))])
    theirs = proj(members=[mem(wd("2026-10-17", 18))])
    (conflict,) = merge_projects(base, ours, theirs).conflicts
    assert conflict.label == "甲: 2026-10-17"


def test_task_parameters_take_the_side_that_changed_them() -> None:
    base = proj(tasks=[task("a", "t1")])
    ours = proj(tasks=[task("a", "t1", parameters=["Python"])])
    theirs = proj(tasks=[task("a", "t1", effort_hours=2.0)])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert (merged.project.tasks[0].parameters, merged.project.tasks[0].effort_hours) == (["Python"], 2.0)


def test_task_parameters_changed_differently_are_one_conflict_named_parameters() -> None:
    base = proj(tasks=[task("a", "t1")])
    ours = proj(tasks=[task("a", "t1", parameters=["Python"])])
    theirs = proj(tasks=[task("a", "t1", parameters=["Java"])])
    result = merge_projects(base, ours, theirs)
    (conflict,) = result.conflicts
    assert (conflict.kind, conflict.field, conflict.ours, conflict.theirs) == ("task", "パラメータ", ["Python"], ["Java"])
    assert result.project.tasks[0].parameters == ["Python"]
    assert merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project.tasks[0].parameters == ["Java"]


def two() -> list[Member]:
    return [Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2")]


def weekly_task(*weeks: list[Assignee]) -> Task:
    return task("a", "t1", assignees=union_assignees(weeks), weekly_crew=[list(w) for w in weeks])


def week_names(t: Task) -> list[list[str]]:
    return [[a.name for a in week] for week in t.weekly_crew]


def test_a_weekly_crew_changed_by_one_side_is_taken() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")])])
    theirs = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("甲"), Assignee("乙")])])
    result = merge_projects(base, base, theirs)
    assert result.conflicts == []
    merged = result.project.tasks[0]
    assert week_names(merged) == [["甲"], ["甲", "乙"]]
    assert [a.name for a in merged.assignees] == ["甲", "乙"]


def test_a_weekly_crew_changed_on_both_sides_is_one_conflict() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")])])
    ours = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    theirs = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("甲"), Assignee("乙")])])
    result = merge_projects(base, ours, theirs)
    assert [c.field for c in result.conflicts] == ["週ごとの担当"]
    assert week_names(result.project.tasks[0]) == [["甲"], ["乙"]]  # 既定は自分
    chosen = merge_projects(base, ours, theirs, {result.conflicts[0].id: THEIRS}).project.tasks[0]
    assert week_names(chosen) == [["甲"], ["甲", "乙"]]


def test_a_week_emptied_by_a_deleted_member_takes_the_neighbouring_crew() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    theirs = proj(members=[Member("甲", 1.0, id="m1")], tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    result = merge_projects(base, base, theirs)
    assert result.conflicts == []
    assert week_names(result.project.tasks[0]) == [["甲"], ["甲"]]
    assert any("担当者を外しました" in n and "第2週" in n for n in result.notes)
    assert any("隣の週と同じ" in n and "第2週" in n for n in result.notes)


def test_when_every_week_is_emptied_the_task_is_no_longer_weekly() -> None:
    gone = weekly_task([Assignee("乙")], [Assignee("乙")])
    base = proj(members=two(), tasks=[gone])
    theirs = proj(members=[Member("甲", 1.0, id="m1")], tasks=[gone])
    result = merge_projects(base, base, theirs)
    merged = result.project.tasks[0]
    assert merged.weekly_crew == [] and merged.assignees == []
    assert any("週ごとの担当をすべて外しました" in n for n in result.notes)


def test_turning_weekly_off_on_one_side_gives_the_plain_assignees() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    ours = proj(members=two(), tasks=[task("a", "t1", assignees=[Assignee("甲", 0.5)])])
    result = merge_projects(base, ours, base)
    assert result.conflicts == []
    merged = result.project.tasks[0]
    assert merged.weekly_crew == [] and merged.assignees == [Assignee("甲", 0.5)]


def test_reference_fields_are_merged_per_item() -> None:
    ref = dict(kind=TaskKind.REFERENCE)
    base = proj(tasks=[task("基盤開発", "r", ref_project="基盤", **ref)])
    ours = proj(tasks=[task("基盤開発", "r", ref_project="基盤2", **ref)])  # 自分が参照先を変えた
    theirs = proj(tasks=[task("基盤の開発", "r", ref_project="基盤", **ref)])  # 相手が名前を変えた
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    result = merged.project.tasks[0]
    assert (result.kind, result.ref_project, result.name) == (TaskKind.REFERENCE, "基盤2", "基盤の開発")


def test_a_snapshot_changed_on_both_sides_is_a_conflict_with_a_readable_label() -> None:
    def with_snapshot(day: int) -> Project:
        value = ReferenceValue(planned_start=datetime(2026, 10, day), planned_end=datetime(2026, 10, 20))
        return proj(tasks=[task("基盤開発", "r", kind=TaskKind.REFERENCE, ref_project="基盤", ref_snapshot=value)])

    merged = merge_projects(with_snapshot(1), with_snapshot(2), with_snapshot(3))
    assert [c.field for c in merged.conflicts] == ["スナップショット"]


def test_the_reference_mode_merges_as_a_setting() -> None:
    merged = merge_projects(proj(), proj(reference_mode=ReferenceMode.SNAPSHOT), proj())
    assert merged.project.reference_mode is ReferenceMode.SNAPSHOT


def test_the_plantuml_notice_option_merges_as_a_setting() -> None:
    merged = merge_projects(proj(), proj(plantuml_overload_notice=False), proj())
    assert merged.project.plantuml_overload_notice is False
    both = merge_projects(proj(), proj(plantuml_overload_notice=False), proj(plantuml_overload_notice=False))
    assert both.project.plantuml_overload_notice is False and both.conflicts == []


def test_the_ratio_limits_merge_as_settings() -> None:
    merged = merge_projects(proj(), proj(ratio_limit_upper=0.5), proj(ratio_limit_lower=-0.5))
    assert merged.project.ratio_limit_upper == 0.5
    assert merged.project.ratio_limit_lower == -0.5 and merged.conflicts == []


def test_different_limits_on_both_sides_are_a_conflict_with_a_readable_label() -> None:
    merged = merge_projects(proj(), proj(ratio_limit_upper=0.5), proj(ratio_limit_upper=0.3))
    assert [c.field for c in merged.conflicts] == ["相対比率の上限"]
