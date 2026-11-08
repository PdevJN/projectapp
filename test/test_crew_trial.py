from datetime import date, datetime

from projectapp.crew_trial import (
    TrialCrew,
    confirmed,
    evaluate,
    replace_task,
    snap_week,
    trial_weeks,
)
from projectapp.models import (
    MAX_WEEKS,
    Assignee,
    Member,
    Project,
    Section,
    Task,
    TaskKind,
)
from projectapp.timeline import Schedule, effective_end

START = datetime(2026, 11, 2, 9)  # 月曜
HOLIDAYS: dict[date, str] = {}


def sample(**changes: object) -> tuple[Project, Task]:
    task = Task(
        "a",
        id="ta",
        planned_start=START,
        effort_hours=60.0,
        assignees=[Assignee("田中")],
    )
    for key, value in changes.items():
        setattr(task, key, value)
    project = Project(
        name="p",
        base_date=START,
        members=[Member("田中"), Member("鈴木")],
        sections=[Section("s", tasks=[task])],
    )
    return project, task


def test_snap_week_rounds_to_the_later_week_boundary() -> None:
    anchor = date(2026, 11, 2)
    assert snap_week(anchor, date(2026, 11, 2)) == 0
    assert snap_week(anchor, date(2026, 11, 1)) == 0  # 開始より前は第 1 週
    assert snap_week(anchor, date(2026, 11, 3)) == 1  # 週の途中は次の週頭
    assert snap_week(anchor, date(2026, 11, 9)) == 1  # ちょうど境目
    assert snap_week(anchor, date(2026, 11, 10)) == 2


def test_trial_weeks_adds_members_from_the_snapped_week_and_carries_on() -> None:
    _, task = sample()
    weeks = trial_weeks(
        task, TrialCrew("ta", ("鈴木",), date(2026, 11, 10)), date(2026, 11, 2)
    )
    assert weeks is not None
    names = [[a.name for a in w] for w in weeks]
    assert names == [["田中"], ["田中"], ["田中", "鈴木"]]


def test_trial_weeks_keeps_existing_weekly_crew_and_does_not_duplicate() -> None:
    _, task = sample(
        weekly_crew=[
            [Assignee("田中")],
            [Assignee("田中")],
            [Assignee("田中"), Assignee("鈴木")],
        ]
    )
    weeks = trial_weeks(
        task, TrialCrew("ta", ("鈴木",), date(2026, 11, 9)), date(2026, 11, 2)
    )
    assert weeks is not None
    assert [[a.name for a in w] for w in weeks] == [
        ["田中"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
    ]


def test_trial_weeks_refuses_beyond_the_week_limit() -> None:
    _, task = sample()
    far = date.fromordinal(date(2026, 11, 2).toordinal() + 7 * MAX_WEEKS + 1)
    assert trial_weeks(task, TrialCrew("ta", ("鈴木",), far), date(2026, 11, 2)) is None


def test_evaluate_shows_an_earlier_end_with_more_people() -> None:
    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    result = evaluate(
        task, project, HOLIDAYS, schedule, TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    )
    assert result is not None
    assert result.trial_end is not None and result.original_end is not None
    assert result.trial_end < result.original_end
    assert (result.days_earlier or 0) > 0
    assert result.first_week == 1


def test_confirmed_task_ends_where_the_trial_said() -> None:
    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    result = evaluate(task, project, HOLIDAYS, schedule, trial)
    saved = confirmed(task, project, HOLIDAYS, schedule, trial)
    assert result is not None and saved is not None
    assert [a.name for a in saved.assignees] == ["田中", "鈴木"]
    assert replace_task(project, saved)
    assert effective_end(saved, project, HOLIDAYS) == result.trial_end


def test_manual_end_wins_and_has_no_trial_end() -> None:
    project, task = sample(
        planned_end=datetime(2026, 11, 20, 18), planned_end_manual=True
    )
    schedule = Schedule(project, HOLIDAYS)
    result = evaluate(
        task, project, HOLIDAYS, schedule, TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    )
    assert result is not None
    assert result.manual and result.trial_end is None


def test_unsuitable_tasks_are_ignored() -> None:
    project, task = sample(assignees=[])
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    assert evaluate(task, project, HOLIDAYS, schedule, trial) is None
    project2, summary = sample(kind=TaskKind.SUMMARY)
    schedule2 = Schedule(project2, HOLIDAYS)
    assert evaluate(summary, project2, HOLIDAYS, schedule2, trial) is None
    assert confirmed(summary, project2, HOLIDAYS, schedule2, trial) is None


def test_replace_task_returns_false_for_an_unknown_id() -> None:
    project, task = sample()
    other = Task("x", id="nope")
    assert not replace_task(project, other)
    assert replace_task(project, task)
