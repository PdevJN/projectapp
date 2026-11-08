from datetime import date, datetime

from projectapp.forecast import Forecast, forecast_end
from projectapp.models import Assignee, Member, Project, Section, Status, Task
from projectapp.pace import warning_pace
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


def run(project: Project, task: Task, now: datetime, extra=None) -> Forecast | None:
    return forecast_end(
        task, project, HOLIDAYS, now, Schedule(project, HOLIDAYS), extra
    )


def test_no_progress_info_and_not_late_means_no_forecast() -> None:
    project, task = sample(
        effort_hours=30.0
    )  # 1 日 6.5h なので、4 日ちょっと。余裕がある
    assert run(project, task, datetime(2026, 11, 2, 9)) is None  # 当初の予定が続く


def test_on_track_progress_forecasts_earlier_or_same_than_plan() -> None:
    project, task = sample(
        progress=50
    )  # 2 日で半分: 予定(15h/日換算でなく 8h/日)より速い
    fc = run(project, task, datetime(2026, 11, 4, 10))
    assert fc is not None and fc.planned_end is not None
    assert fc.end <= fc.planned_end


def test_behind_progress_forecasts_later_than_plan() -> None:
    project, task = sample(progress=10)
    fc = run(project, task, datetime(2026, 11, 9, 10))
    assert fc is not None and fc.days_later is not None and fc.days_later > 0


def test_overdue_without_progress_forecasts_full_effort_from_today() -> None:
    project, task = sample()
    now = datetime(2026, 11, 20, 10)
    assert effective_end(task, project, HOLIDAYS, Schedule(project, HOLIDAYS)) <= now
    fc = run(project, task, now)
    assert fc is not None and fc.end > now


def test_not_targets_return_none() -> None:
    project, task = sample(progress=100)
    assert run(project, task, datetime(2026, 11, 9, 10)) is None  # 残り 0
    project, task = sample(progress=10, status=Status.DONE)
    assert run(project, task, datetime(2026, 11, 9, 10)) is None  # 終了
    project, task = sample(progress=10)
    assert run(project, task, datetime(2026, 11, 1, 10)) is None  # 開始が未来


def test_manual_planned_end_still_gets_a_forecast() -> None:
    project, task = sample(
        progress=10, planned_end=datetime(2026, 11, 20, 18), planned_end_manual=True
    )
    assert run(project, task, datetime(2026, 11, 9, 10)) is not None


def test_a_warning_task_always_forecasts_after_the_planned_end() -> None:
    project, task = sample(progress=10)
    now = datetime(2026, 11, 4, 10)
    schedule = Schedule(project, HOLIDAYS)
    assert warning_pace(task, project, HOLIDAYS, now, schedule) is not None, (
        "前提: 警告になる値に調整する"
    )
    fc = run(project, task, now)
    assert fc is not None and fc.planned_end is not None
    assert fc.end > fc.planned_end  # 同日を含まない


def test_weekly_crew_keeps_week_boundaries_counted_from_the_start() -> None:
    weekly = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    project, task = sample(progress=10, weekly_crew=weekly)
    late = run(project, task, datetime(2026, 11, 9, 10))  # 第 2 週(2 人)に入ってから
    project2, single = sample(progress=10)  # 1 人のまま
    base = run(project2, single, datetime(2026, 11, 9, 10))
    assert late is not None and base is not None
    assert late.end < base.end  # 2 人なので早い(第 1 週の 1 人に戻らない)


def test_extra_crew_is_rounded_to_the_later_week_and_shortens_the_forecast() -> None:
    project, task = sample()
    now = datetime(2026, 11, 20, 10)  # 予定超過(進捗情報なし)
    base = run(project, task, now)
    boosted = run(project, task, now, (("鈴木",), date(2026, 11, 23)))
    assert base is not None and boosted is not None
    assert boosted.end < base.end
    # 今日以前の増員日は今日から
    now_boost = run(project, task, now, (("鈴木",), date(2026, 11, 1)))
    assert now_boost is not None and now_boost.end <= boosted.end


def test_unavailable_input_returns_none_without_raising() -> None:
    project, task = sample(progress=10, effort_hours=float("nan"))
    assert run(project, task, datetime(2026, 11, 9, 10)) is None
