from datetime import date, datetime

from projectapp.crew_trial import (
    TrialCrew,
    confirmed,
    evaluate,
    replace_task,
    trial_crews,
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
NOW = datetime(2026, 11, 2, 8)  # 開始の前(遅れていない)


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


def names(crew):
    return [a.name for a in crew]


def test_trial_crews_from_a_week_head_adds_to_the_week_and_carries_on() -> None:
    _, task = sample()
    weekly, daily = trial_crews(
        task, TrialCrew("ta", ("鈴木",), date(2026, 11, 9)), date(2026, 11, 2)
    )
    assert [names(w) for w in weekly] == [["田中"], ["田中", "鈴木"]] and daily == {}


def test_trial_crews_mid_week_makes_that_week_daily() -> None:
    _, task = sample()
    weekly, daily = trial_crews(
        task, TrialCrew("ta", ("鈴木",), date(2026, 11, 5)), date(2026, 11, 2)
    )
    assert list(daily) == [0]
    assert [names(d) for d in daily[0]] == [["田中"]] * 3 + [["田中", "鈴木"]] * 4
    assert names(weekly[0]) == ["田中", "鈴木"]


def test_trial_crews_keeps_existing_weeks_and_does_not_duplicate() -> None:
    _, task = sample(weekly_crew=[[Assignee("田中")], [Assignee("田中")]])
    weekly, daily = trial_crews(
        task, TrialCrew("ta", ("田中",), date(2026, 11, 9)), date(2026, 11, 2)
    )
    assert [names(w) for w in weekly] == [["田中"], ["田中"]] and daily == {}


def test_trial_crews_refuses_beyond_the_week_limit() -> None:
    _, task = sample()
    far = date.fromordinal(date(2026, 11, 2).toordinal() + 7 * MAX_WEEKS + 1)
    assert trial_crews(task, TrialCrew("ta", ("鈴木",), far), date(2026, 11, 2)) is None


def test_evaluate_shows_an_earlier_end_with_more_people() -> None:
    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    result = evaluate(
        task,
        project,
        HOLIDAYS,
        schedule,
        TrialCrew("ta", ("鈴木",), date(2026, 11, 9)),
        NOW,
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
    result = evaluate(task, project, HOLIDAYS, schedule, trial, NOW)
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
        task,
        project,
        HOLIDAYS,
        schedule,
        TrialCrew("ta", ("鈴木",), date(2026, 11, 9)),
        NOW,
    )
    assert result is not None
    assert result.manual and result.trial_end is None


def test_unsuitable_tasks_are_ignored() -> None:
    project, task = sample(assignees=[])
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    assert evaluate(task, project, HOLIDAYS, schedule, trial, NOW) is None
    project2, summary = sample(kind=TaskKind.SUMMARY)
    schedule2 = Schedule(project2, HOLIDAYS)
    assert evaluate(summary, project2, HOLIDAYS, schedule2, trial, NOW) is None
    assert confirmed(summary, project2, HOLIDAYS, schedule2, trial) is None


def test_replace_task_returns_false_for_an_unknown_id() -> None:
    project, task = sample()
    other = Task("x", id="nope")
    assert not replace_task(project, other)
    assert replace_task(project, task)


LATE = datetime(2026, 11, 20, 9)  # 完了予定(11/13 ごろ)を過ぎた今日


def test_an_overdue_task_is_estimated_from_todays_remaining_effort() -> None:
    project, task = sample(progress=50)
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 20))
    result = evaluate(task, project, HOLIDAYS, schedule, trial, LATE)
    assert result is not None and result.from_now
    assert result.trial_end is not None and result.baseline_end is not None
    assert result.baseline_end > LATE  # 追加なしでも、今日から残りを消化する
    assert result.trial_end < result.baseline_end  # 増員で早まる
    assert (result.days_earlier or 0) > 0  # 早まりは、追加なしの見込みとの差


def test_remaining_effort_follows_progress() -> None:
    project, half = sample(progress=50)
    _, none = sample()
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 20))
    a = evaluate(half, project, HOLIDAYS, schedule, trial, LATE)
    b = evaluate(none, project, HOLIDAYS, schedule, trial, LATE)
    assert a is not None and b is not None
    assert a.trial_end is not None and b.trial_end is not None
    assert a.trial_end < b.trial_end  # 進んだ分だけ早い


def test_a_task_not_yet_overdue_keeps_the_weekly_calculation() -> None:
    project, task = sample()
    result = evaluate(
        task,
        project,
        HOLIDAYS,
        Schedule(project, HOLIDAYS),
        TrialCrew("ta", ("鈴木",), date(2026, 11, 9)),
        NOW,
    )
    assert result is not None and not result.from_now


def test_confirming_an_overdue_task_does_not_shrink_the_past_bar() -> None:
    project, task = sample(progress=50)
    schedule = Schedule(project, HOLIDAYS)
    before = effective_end(task, project, HOLIDAYS, schedule)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 20))
    saved = confirmed(task, project, HOLIDAYS, schedule, trial)
    assert saved is not None
    assert replace_task(project, saved)
    # 増員は次の週の境目から。過去の週の担当は変わらず、完了予定は前倒しされない
    assert effective_end(saved, project, HOLIDAYS) == before
    assert [a.name for a in saved.weekly_crew[0]] == ["田中"]


def test_confirming_starts_on_the_given_day_and_makes_only_that_week_daily() -> None:
    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 10))  # 第 2 週(11/9〜)の火曜
    saved = confirmed(task, project, HOLIDAYS, schedule, trial)
    assert saved is not None
    assert [[a.name for a in w] for w in saved.weekly_crew] == [
        ["田中"],
        ["田中", "鈴木"],
    ]
    assert [[a.name for a in d] for d in saved.daily_crew[1]] == [["田中"]] + [
        ["田中", "鈴木"]
    ] * 6


def test_a_warning_task_is_estimated_from_todays_remaining_effort() -> None:
    project, task = sample(effort_hours=40.0, progress=10)
    now = datetime(2026, 11, 6, 10)  # 完了予定(11/10 ごろ)の手前。残りが稼働量を超える
    schedule = Schedule(project, HOLIDAYS)
    assert (end := effective_end(task, project, HOLIDAYS, schedule)) is not None
    assert end > now  # 遅れてはいない(警告)
    result = evaluate(
        task,
        project,
        HOLIDAYS,
        schedule,
        TrialCrew("ta", ("鈴木",), date(2026, 11, 6)),
        now,
    )
    assert result is not None and result.from_now
    assert result.trial_end is not None and result.baseline_end is not None
    assert result.baseline_end > end  # 追加なしでは、完了予定に間に合わない見込み
    assert result.trial_end < result.baseline_end  # 増員で早まる


def test_trial_end_equals_the_forecast_with_the_extra_crew_for_late_tasks() -> None:
    from projectapp.forecast import forecast_end

    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    now = datetime(2026, 11, 20, 10)  # 予定超過
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 23))
    result = evaluate(task, project, HOLIDAYS, schedule, trial, now)
    expected = forecast_end(
        task, project, HOLIDAYS, now, schedule, (trial.names, trial.start)
    )
    base = forecast_end(task, project, HOLIDAYS, now, schedule)
    assert result is not None and expected is not None and base is not None
    assert result.from_now
    assert result.trial_end == expected.end
    assert result.baseline_end == base.end
