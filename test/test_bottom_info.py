from datetime import date, datetime

from projectapp.bottom_info import (
    LEGEND,
    period_summary,
    task_detail,
    today_plan,
)
from projectapp.models import (
    Assignee,
    Member,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.timeline import Schedule

NOW = datetime(2026, 10, 7, 12)  # 水曜の昼
MON = datetime(2026, 10, 5, 9)


def project_of(*tasks: Task) -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        sections=[Section("s", list(tasks))],
    )


def env(*tasks: Task):
    project = project_of(*tasks)
    return project, Schedule(project, {})


def planned(name: str, **kw) -> Task:
    kw.setdefault("planned_start", MON)
    kw.setdefault("effort_hours", 13.0)
    return Task(name, **kw)


def test_detail_lists_status_crew_dates_effort_and_progress() -> None:
    task = planned(
        "設計",
        assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)],
        progress=40,
        status=Status.RUNNING,
        deadline=datetime(2026, 10, 9, 18),
    )
    project, schedule = env(task)
    detail = task_detail(task, project, {}, NOW, schedule)
    lines = dict(detail.lines)
    assert detail.title == "設計" and detail.kind == "通常"
    assert lines["状態"] == "実行中"
    assert lines["担当"] == "田中 100%・鈴木 50%"
    assert lines["工数"] == "13.0h" and lines["進捗度"] == "40%"
    assert lines["締切"] == "10/09 18:00"
    assert "開始予定" in lines and "完了予定" in lines


def test_detail_explains_overdue_and_warning() -> None:
    late = planned(
        "遅れ",
        planned_end=datetime(2026, 10, 6, 12),
        planned_end_manual=True,
        assignees=[Assignee("田中", 1.0)],
    )
    project, schedule = env(late)
    detail = task_detail(late, project, {}, NOW, schedule)
    assert any("予定超過" in note for note in detail.notes)


def test_detail_marks_how_many_other_tasks_are_selected() -> None:
    task = planned("a")
    project, schedule = env(task)
    assert task_detail(task, project, {}, NOW, schedule, others=2).others == 2


def test_detail_of_a_task_without_dates_or_crew_uses_dashes() -> None:
    task = Task("空")
    project, schedule = env(task)
    lines = dict(task_detail(task, project, {}, NOW, schedule).lines)
    assert lines["担当"] == "—" and lines["工数"] == "—" and lines["進捗度"] == "—"


def test_checkpoint_detail_shows_only_deadline_and_status() -> None:
    task = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 18))
    project, schedule = env(task)
    detail = task_detail(task, project, {}, NOW, schedule)
    assert detail.kind == "チェックポイント"
    assert [k for k, _ in detail.lines] == ["状態", "締切"]


def test_summary_counts_states_hours_and_weighted_percent() -> None:
    done = planned("終", status=Status.DONE, effort_hours=10.0)
    half = planned("半", status=Status.RUNNING, effort_hours=10.0, progress=50)
    project, schedule = env(done, half)
    s = period_summary([done, half], project, {}, NOW, schedule, None)
    assert s.total == 2 and s.counts[Status.DONE] == 1 and s.counts[Status.RUNNING] == 1
    assert s.hours == 20.0 and s.percent == 75.0


def test_summary_skips_summaries_checkpoints_and_counts_missing_effort() -> None:
    kid = planned("子")
    summary = Task("まとめ", kind=TaskKind.SUMMARY, children=[kid.id])
    mark = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9))
    bare = Task("工数なし", planned_start=MON)
    project, schedule = env(summary, kid, mark, bare)
    s = period_summary([summary, kid, mark, bare], project, {}, NOW, schedule, None)
    assert s.total == 2 and s.no_effort == 1


def test_summary_of_nothing_has_no_percent_and_no_division_error() -> None:
    project, schedule = env()
    s = period_summary([], project, {}, NOW, schedule, None)
    assert s.total == 0 and s.percent is None and s.hours == 0.0


def test_summary_period_keeps_only_tasks_overlapping_it() -> None:
    inside = planned("内", planned_start=MON)
    outside = planned("外", planned_start=datetime(2026, 12, 1, 9))
    project, schedule = env(inside, outside)
    s = period_summary(
        [inside, outside],
        project,
        {},
        NOW,
        schedule,
        (date(2026, 10, 1), date(2026, 10, 31)),
    )
    assert s.total == 1


def test_summary_counts_overdue_and_warned_separately() -> None:
    late = planned(
        "遅",
        planned_end=datetime(2026, 10, 6, 12),
        planned_end_manual=True,
        assignees=[Assignee("田中", 1.0)],
    )
    behind = planned(
        "警告",
        planned_start=MON,
        effort_hours=19.5,
        progress=10,
        planned_end=datetime(2026, 10, 8, 15, 30),
        planned_end_manual=True,
        assignees=[Assignee("田中", 1.0)],
        status=Status.RUNNING,
    )
    project, schedule = env(late, behind)
    s = period_summary([late, behind], project, {}, NOW, schedule, None)
    assert s.overdue == 1 and s.warned == 1


def test_today_plan_lists_open_normal_tasks_covering_today() -> None:
    now_task = planned(
        "今日",
        planned_end=datetime(2026, 10, 8, 12),
        planned_end_manual=True,
        assignees=[Assignee("田中", 1.0)],
        progress=30,
    )
    done = planned(
        "終",
        status=Status.DONE,
        planned_end=datetime(2026, 10, 8, 12),
        planned_end_manual=True,
    )
    later = planned("後", planned_start=datetime(2026, 10, 12, 9))
    nodate = Task("日程なし")
    project, schedule = env(now_task, done, later, nodate)
    rows = today_plan([now_task, done, later, nodate], schedule, NOW)
    assert [r.name for r in rows] == ["今日"]
    assert rows[0].assignees == "田中" and rows[0].progress == 30


def test_today_plan_treats_midnight_end_as_the_previous_day() -> None:
    task = planned(
        "昨日まで", planned_end=datetime(2026, 10, 7, 0), planned_end_manual=True
    )
    project, schedule = env(task)
    assert today_plan([task], schedule, NOW) == []


def test_legend_covers_states_priorities_and_marks() -> None:
    groups = {e.group for e in LEGEND}
    assert groups == {"状態", "優先度", "印"}
    classes = {e.css_class for e in LEGEND}
    assert {
        "status-not-started",
        "status-running",
        "status-paused",
        "status-done",
        "prio-high",
        "prio-medium",
        "prio-low",
    } <= classes


def test_legend_classes_match_the_chart_constants() -> None:
    from projectapp.gantt import PRIORITY_CLASSES, STATUS_CLASSES

    classes = {e.css_class for e in LEGEND}
    assert set(STATUS_CLASSES.values()) <= classes
    assert set(PRIORITY_CLASSES.values()) <= classes
