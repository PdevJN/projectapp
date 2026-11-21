"""既存のプロジェクトから、設定(とタスク)を引き継いだ新規プロジェクトを作る(要望 77)。"""

from datetime import date, datetime, time

from projectapp.inherit import InheritScope, inherit_project
from projectapp.models import (
    Actual,
    Category,
    Event,
    ExtraEffort,
    Member,
    Project,
    ReferenceMode,
    Section,
    Status,
    Task,
    TaskKind,
    Team,
    UrlTemplate,
)

START = datetime(2026, 11, 24, 9)


def source_project() -> Project:
    done = Task(
        "終わった",
        id="a",
        status=Status.DONE,
        progress=100,
        planned_start=START,
        effort_hours=8,
        actuals=[Actual(START, datetime(2026, 11, 24, 17))],
        extra_efforts=[ExtraEffort(date(2026, 11, 25), 2.0, "追加")],
        deadline=datetime(2026, 11, 30, 17),
    )
    running = Task(
        "実行中",
        id="b",
        status=Status.RUNNING,
        progress=40,
        predecessors=["a"],
        actuals=[Actual(START)],
    )
    checkpoint = Task("節目", id="c", kind=TaskKind.CHECKPOINT, status=Status.DONE)
    summary = Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["k"])
    kid = Task("子", id="k", status=Status.PAUSED)
    return Project(
        "元",
        base_date=date(2026, 11, 1),
        daily_hours=6.0,
        work_start=time(8, 30),
        members=[Member("田中", 1.2, id="m1")],
        sections=[Section("開発", [done, running, summary, kid], id="sec")],
        tasks=[checkpoint],
        url_templates=[UrlTemplate("課題", "https://example.com/{id}")],
        categories=[Category("設計", id="cat")],
        events=[Event(date(2026, 12, 1), date(2026, 12, 3), "休み", id="ev")],
        teams=[Team("A班", id="t1")],
        reference_mode=ReferenceMode.SNAPSHOT,
        plantuml_overload_notice=False,
        actual_time_optional=False,
        ratio_limit_upper=1.3,
        ratio_limit_lower=0.7,
    )


def test_settings_only_keeps_the_settings_and_drops_the_tasks() -> None:
    result = inherit_project(source_project(), "新規", InheritScope.SETTINGS)
    assert result.name == "新規"
    assert (result.tasks, result.sections) == ([], [])
    assert (result.base_date, result.daily_hours, result.work_start) == (
        date(2026, 11, 1),
        6.0,
        time(8, 30),
    )
    assert [m.name for m in result.members] == ["田中"]
    assert [c.name for c in result.categories] == ["設計"]
    assert [e.text for e in result.events] == ["休み"]
    assert [u.name for u in result.url_templates] == ["課題"]
    assert [t.name for t in result.teams] == ["A班"]
    assert result.reference_mode is ReferenceMode.SNAPSHOT
    assert result.plantuml_overload_notice is False
    assert result.actual_time_optional is False
    assert (result.ratio_limit_upper, result.ratio_limit_lower) == (1.3, 0.7)


def test_the_change_history_is_not_carried() -> None:
    source = source_project()
    source.history_since = datetime(2026, 11, 2, 9)
    result = inherit_project(source, "新規", InheritScope.SETTINGS_AND_TASKS)
    assert result.history == [] and result.history_since is None


def test_with_tasks_keeps_the_structure_and_ids() -> None:
    result = inherit_project(
        source_project(), "新規", InheritScope.SETTINGS_AND_TASKS, reset_progress=False
    )
    assert [t.id for t in result.tasks] == ["c"]
    section = result.sections[0]
    assert (section.id, [t.id for t in section.tasks]) == ("sec", ["a", "b", "s", "k"])
    tasks = result.task_map()
    assert tasks["b"].predecessors == ["a"]
    assert tasks["s"].children == ["k"]
    assert tasks["a"].deadline == datetime(2026, 11, 30, 17)


def test_resetting_clears_status_actuals_and_progress_only() -> None:
    result = inherit_project(source_project(), "新規", InheritScope.SETTINGS_AND_TASKS)
    tasks = result.task_map()
    for task in tasks.values():
        assert task.status is Status.NOT_STARTED
        assert (task.actuals, task.progress) == ([], None)
    done = tasks["a"]
    assert done.effort_hours == 8 and done.planned_start == START
    assert [e.hours for e in done.extra_efforts] == [2.0]  # 追加工数は残す


def test_without_reset_the_records_are_kept() -> None:
    result = inherit_project(
        source_project(), "新規", InheritScope.SETTINGS_AND_TASKS, reset_progress=False
    )
    done = result.task_map()["a"]
    assert (done.status, done.progress, len(done.actuals)) == (Status.DONE, 100, 1)


def test_the_source_project_is_not_changed() -> None:
    source = source_project()
    result = inherit_project(source, "新規", InheritScope.SETTINGS_AND_TASKS)
    result.task_map()["a"].name = "書き換えた"
    result.members[0].name = "別人"
    assert source.task_map()["a"].name == "終わった"
    assert source.members[0].name == "田中"
    assert source.task_map()["a"].status is Status.DONE


def test_the_scopes_have_labels_for_the_dialog() -> None:
    assert [scope.value for scope in InheritScope] == ["設定のみ", "設定とタスク"]
