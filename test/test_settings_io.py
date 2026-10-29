import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from projectapp.models import (
    Actual,
    ActualMode,
    Category,
    Event,
    Level,
    Member,
    Membership,
    Parameter,
    Project,
    ReferenceMode,
    Section,
    Task,
    Team,
    UrlTemplate,
    WorkDay,
)
from projectapp.settings_io import (
    DEFAULT_FILENAME,
    SETTINGS_FILE_TYPES,
    ImportFile,
    ImportPlan,
    ProjectChange,
    SectionPlan,
    apply_import,
    build_settings,
    copy_into,
    parse_settings,
    plan_import,
    summary,
    write_settings,
)


def full_project() -> Project:
    return Project(
        "元",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        work_start=time(10, 0),
        actual_mode=ActualMode.INTERVALS,
        reference_mode=ReferenceMode.SNAPSHOT,
        plantuml_overload_notice=False,
        ratio_limit_upper=1.2,
        ratio_limit_lower=0.8,
        parameters=[Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])],
        members=[Member("田中", 1.2, {"経験": "上級"}, work_days=[WorkDay(date(2026, 10, 12), None, None, "休暇")])],
        categories=[Category("開発", kind="業務", color="red", prj_code="PRJ-1")],
        url_templates=[UrlTemplate("チケット", "https://example.com/{ID}")],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "orange", closed=True)],
        sections=[Section("開発", [Task("実装")])],
        tasks=[Task("雑務")],
    )


def test_the_file_names_its_kind_and_leaves_out_the_tasks() -> None:
    data = build_settings(full_project())
    assert data["kind"] == "projectapp-settings" and data["version"] == 1
    assert "tasks" not in data and "sections" not in data
    assert DEFAULT_FILENAME == "settings.json" and SETTINGS_FILE_TYPES == ("JSON ファイル (*.json)",)


def test_the_settings_round_trip_into_a_project_without_tasks() -> None:
    project = full_project()
    loaded = parse_settings(json.dumps(build_settings(project)))
    got = loaded.project
    assert loaded.has_project_settings
    assert (got.base_date, got.daily_hours, got.work_start) == (project.base_date, 7.0, time(10, 0))
    assert (got.actual_mode, got.reference_mode, got.plantuml_overload_notice) == (
        ActualMode.INTERVALS,
        ReferenceMode.SNAPSHOT,
        False,
    )
    assert (got.ratio_limit_upper, got.ratio_limit_lower) == (1.2, 0.8)
    assert got.members == project.members and got.parameters == project.parameters
    assert got.categories == project.categories and got.url_templates == project.url_templates
    assert got.events == project.events
    assert got.members[0].id == project.members[0].id  # 取り込み側で振り直すので、ここでは保つ
    assert got.tasks == [] and got.sections == []


def test_missing_sections_read_as_empty() -> None:
    loaded = parse_settings(json.dumps({"kind": "projectapp-settings", "version": 1, "members": []}))
    assert not loaded.has_project_settings
    assert loaded.project.members == [] and loaded.project.events == []


def test_the_file_is_written_as_json(tmp_path: Path) -> None:
    path = write_settings(tmp_path / "out", build_settings(full_project()))
    assert path.name == "out.json"  # 拡張子がなければ付ける
    assert json.loads(path.read_text(encoding="utf-8"))["kind"] == "projectapp-settings"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]  # 一時ファイルを残さない


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "JSON"),
        ("{", "JSON"),
        ("[]", "設定ファイルではありません"),
        (json.dumps({"kind": "other", "version": 1}), "設定ファイルではありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 2}), "新しい形式"),
        (json.dumps({"kind": "projectapp-settings", "version": 0}), "version"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "project_version": 999}), "project_version"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "members": "abc"}), "リストではありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "members": [1]}), "形式が正しくありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "daily_hours": 0}), "稼働可能時間"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "base_date": "x"}), "Invalid isoformat"),
    ],
)
def test_a_broken_file_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_settings(text)


def incoming_of(project: Project) -> ImportFile:
    return parse_settings(json.dumps(build_settings(project)))


def test_the_plan_splits_new_items_from_duplicates() -> None:
    current = Project(
        "現", base_date=date(2026, 10, 5), members=[Member("田中")], parameters=[Parameter("経験", [Level("上級", 0.2)])]
    )
    source = Project(
        "入",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        members=[Member("田中", 1.5), Member("鈴木")],
        parameters=[Parameter("経験", [Level("上級", 0.3)])],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")],
    )
    plan = plan_import(current, incoming_of(source))
    assert plan == ImportPlan(
        sections=(
            SectionPlan("members", ("鈴木",), ("田中",), True),
            SectionPlan("parameters", (), ("経験",), True),
            SectionPlan("events", ("2026-10-10〜2026-10-12 合宿",), (), False),
        ),
        project_changes=(ProjectChange("稼働可能時間", "6.5h", "7h"),),
    )


def test_a_file_with_nothing_new_makes_an_empty_plan() -> None:
    project = Project("同じ", base_date=date(2026, 10, 5))
    assert plan_import(project, incoming_of(project)) == ImportPlan((), ())


def test_apply_adds_new_items_with_fresh_ids_and_keeps_the_current_ones() -> None:
    current = Project("現", members=[Member("田中", 1.0)], categories=[Category("開発")])
    source = Project(
        "入",
        members=[Member("田中", 1.5), Member("鈴木", 1.1)],
        categories=[Category("開発", color="red"), Category("保守")],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")],
        url_templates=[UrlTemplate("チケット", "https://example.com/{ID}")],
    )
    result = apply_import(current, incoming_of(source), {"members", "categories", "events", "url_templates"}, set())
    members = result.project.members
    assert [(m.name, m.ratio) for m in members] == [("田中", 1.0), ("鈴木", 1.1)]  # 重複は既定でスキップ
    assert [c.name for c in result.project.categories] == ["開発", "保守"]
    assert result.project.categories[0].color == "blue"
    assert [e.text for e in result.project.events] == ["合宿"]
    assert [t.name for t in result.project.url_templates] == ["チケット"]
    all_ids = [x.id for x in (*members, *result.project.categories, *result.project.events)]
    assert len(set(all_ids)) == len(all_ids)
    assert result.counts == {"project": 0, "members": 1, "parameters": 0, "categories": 1, "url_templates": 1, "events": 1}
    assert result.skipped == 2  # 田中と開発
    assert current.members == [Member("田中", 1.0)]  # 元は変えない


def test_apply_overwrites_the_chosen_duplicates_and_keeps_their_ids() -> None:
    current = Project(
        "現",
        members=[Member("田中", 1.0)],
        categories=[Category("開発")],
        parameters=[Parameter("経験", [Level("上級", 0.2)])],
        url_templates=[UrlTemplate("チケット", "https://old/{ID}")],
    )
    member_id, category_id = current.members[0].id, current.categories[0].id
    source = Project(
        "入",
        members=[Member("田中", 1.5, work_days=[WorkDay(date(2026, 10, 12), None, None, "休")])],
        categories=[Category("開発", kind="業務", color="red", prj_code="P-1")],
        parameters=[Parameter("経験", [Level("上級", 0.3)])],
        url_templates=[UrlTemplate("チケット", "https://new/{ID}")],
    )
    overwrite = {("members", "田中"), ("categories", "開発"), ("parameters", "経験"), ("url_templates", "チケット")}
    result = apply_import(current, incoming_of(source), {"members", "categories", "parameters", "url_templates"}, overwrite)
    member, category = result.project.members[0], result.project.categories[0]
    assert (member.id, member.ratio, len(member.work_days)) == (member_id, 1.5, 1)
    assert (category.id, category.kind, category.color, category.prj_code) == (category_id, "業務", "red", "P-1")
    assert result.project.parameters[0].levels == [Level("上級", 0.3)]
    assert result.project.url_templates[0].pattern == "https://new/{ID}"
    assert result.skipped == 0


def test_unchecked_sections_are_left_alone() -> None:
    current = Project("現")
    source = Project("入", members=[Member("鈴木")], parameters=[Parameter("経験", [Level("上級", 0.2)])])
    result = apply_import(current, incoming_of(source), {"parameters"}, set())
    assert result.project.members == [] and [p.name for p in result.project.parameters] == ["経験"]
    assert result.skipped == 0


def test_a_duplicate_event_in_the_file_is_added_once() -> None:
    event = Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")
    source = Project("入", events=[event, Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")])
    result = apply_import(Project("現"), incoming_of(source), {"events"}, set())
    assert len(result.project.events) == 1


def test_a_duplicate_event_is_never_overwritten_or_added() -> None:
    event = Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "red")
    current = Project("現", events=[event])
    source = Project("入", events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "blue")])
    result = apply_import(current, incoming_of(source), {"events"}, {("events", "2026-10-10〜2026-10-12 合宿")})
    assert [e.color for e in result.project.events] == ["red"] and result.skipped == 1


def test_level_choices_that_no_longer_match_are_dropped_and_counted() -> None:
    current = Project("現", parameters=[Parameter("経験", [Level("上級", 0.2)])], members=[Member("田中", 1.0, {"経験": "上級"})])
    source = Project("入", parameters=[Parameter("経験", [Level("中級", 0.1)])])
    result = apply_import(current, incoming_of(source), {"parameters"}, {("parameters", "経験")})
    assert result.project.members[0].levels == {}
    assert result.dropped_levels == 1


def test_project_settings_are_applied_together() -> None:
    current = Project("現", base_date=date(2026, 10, 5))
    source = Project(
        "入",
        base_date=date(2026, 11, 1),
        daily_hours=7.0,
        work_start=time(10, 0),
        plantuml_overload_notice=False,
        ratio_limit_upper=1.2,
        ratio_limit_lower=0.8,
    )
    result = apply_import(current, incoming_of(source), {"project"}, set())
    got = result.project
    assert (got.base_date, got.daily_hours, got.work_start) == (date(2026, 11, 1), 7.0, time(10, 0))
    assert (got.plantuml_overload_notice, got.ratio_limits.upper, got.ratio_limits.lower) == (False, 1.2, 0.8)
    assert result.counts["project"] == 1


def test_the_simple_record_mode_is_refused_while_a_task_has_several_intervals() -> None:
    task = Task(
        "実装",
        actuals=[
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 10)),
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 10)),
        ],
    )
    current = Project("現", actual_mode=ActualMode.INTERVALS, tasks=[task])
    source = Project("入", actual_mode=ActualMode.SIMPLE, daily_hours=7.0)
    result = apply_import(current, incoming_of(source), {"project"}, set())
    assert result.project.actual_mode is ActualMode.INTERVALS and result.project.daily_hours == 7.0
    assert result.notes == ["記録方式は、2 区間以上のタスクがあるため変えませんでした"]


def test_an_invalid_result_raises_and_changes_nothing() -> None:
    current = Project("現", categories=[Category("開発")])
    incoming = incoming_of(Project("入", categories=[Category("保守")]))
    incoming.project.categories[0].color = "nope"  # 読み込み後に壊す(適用後の検証で拾う)
    with pytest.raises(ValueError):
        apply_import(current, incoming, {"categories"}, set())
    assert [c.name for c in current.categories] == ["開発"]


def test_copy_into_moves_every_field_and_keeps_the_target_object() -> None:
    target, source = Project("現"), Project("入", daily_hours=7.0, members=[Member("鈴木")])
    copy_into(target, source)
    assert target.name == "入" and target.daily_hours == 7.0 and [m.name for m in target.members] == ["鈴木"]


def test_the_summary_lists_the_counts_and_the_leftovers() -> None:
    current = Project("現", members=[Member("田中")])
    source = Project("入", members=[Member("田中"), Member("鈴木")], parameters=[Parameter("経験", [Level("上級", 0.2)])])
    result = apply_import(current, incoming_of(source), {"members", "parameters"}, set())
    assert summary(result) == "取り込みました(メンバー 1 件、パラメータ 1 件)。重複 1 件は取り込んでいません"
    empty = apply_import(current, incoming_of(Project("入")), {"members"}, set())
    assert summary(empty) == "取り込む項目はありませんでした"


def test_apply_overwrite_also_replaces_ratio_unclamped() -> None:
    current = Project("現", members=[Member("田中", 1.0)])
    source = Project("入", members=[Member("田中", 2.0, ratio_unclamped=True)])
    result = apply_import(current, incoming_of(source), {"members"}, {("members", "田中")})
    assert result.project.members[0].ratio_unclamped is True


def test_settings_file_round_trips_ratio_unclamped() -> None:
    incoming = incoming_of(Project("p", members=[Member("田中", 2.0, ratio_unclamped=True)]))
    assert incoming.project.members[0].ratio_unclamped is True


def test_the_settings_file_has_no_teams_and_members_have_no_memberships() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="t1")],
        members=[Member("甲", id="m1", teams=[Membership("t1", 100)])],
    )
    data = build_settings(project)
    assert "teams" not in data
    assert data["members"][0]["teams"] == []
    imported = parse_settings(json.dumps(data))  # 読める(未知のチームを指す所属が残っていない)
    assert imported.project.members[0].teams == []
