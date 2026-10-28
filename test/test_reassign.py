from copy import deepcopy
from datetime import date, datetime, time

import pytest

from projectapp.models import Actual, Assignee, Level, Member, Parameter, Project, RatioLimits, Status, Task, TaskKind
from projectapp.reassign import consumed_hours, limit_reviews, needs_review, reviewed_end

WORK_START = time(9, 0)
NOW = datetime(2026, 10, 14, 10, 0)  # 水曜


def task(**kwargs) -> Task:
    base = dict(name="設計", planned_start=datetime(2026, 10, 12, 9, 0), effort_hours=16.0, status=Status.RUNNING)
    return Task(**{**base, **kwargs})


def test_consumed_uses_the_progress_first() -> None:
    t = task(progress=50, actuals=[Actual(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 12))])
    assert consumed_hours(t, 1.0) == pytest.approx(8.0)


def test_consumed_falls_back_to_the_actual_time_times_the_old_rate() -> None:
    t = task(actuals=[Actual(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 13)),
                      Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 11))])
    assert consumed_hours(t, 1.5) == pytest.approx(9.0)  # 6h × 1.5


def test_consumed_ignores_a_running_interval_and_zero_progress() -> None:
    t = task(progress=0, actuals=[Actual(datetime(2026, 10, 12, 9), None)])
    assert consumed_hours(t, 1.0) == 0.0


def test_consumed_is_capped_at_the_effort() -> None:
    t = task(effort_hours=4.0, actuals=[Actual(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 18))])
    assert consumed_hours(t, 2.0) == pytest.approx(4.0)


def test_consumed_is_zero_without_effort_or_records() -> None:
    assert consumed_hours(task(effort_hours=0.0, progress=50), 1.0) == 0.0
    assert consumed_hours(task(), 1.0) == 0.0


@pytest.mark.parametrize("kwargs", [{"progress": 30}, {"actuals": [Actual(datetime(2026, 10, 12, 9), None)]}])
def test_needs_review_when_a_record_exists_and_the_rate_changes(kwargs) -> None:
    assert needs_review(task(**kwargs), 1.0, 0.5)


def test_needs_review_is_false_when_the_rate_is_unchanged() -> None:
    assert not needs_review(task(progress=30), 1.0, 1.0)
    assert not needs_review(task(progress=30), 1.0, 1.0 + 1e-12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # 実績も進捗度もない
        {"progress": 0},
        {"progress": 30, "effort_hours": 0.0},
        {"progress": 30, "status": Status.DONE},
        {"progress": 30, "kind": TaskKind.CHECKPOINT},
        {"progress": 30, "kind": TaskKind.SUMMARY},
    ],
)
def test_needs_review_is_false_for_the_excluded_tasks(kwargs) -> None:
    assert not needs_review(task(**kwargs), 1.0, 0.5)


def test_reviewed_end_converts_the_remaining_effort_with_the_new_rate() -> None:
    # 残り 8h ÷ 0.5 = 16h。水 10:00〜15:30 で 5.5h、木 6.5h、金 4h → 金 13:00
    t = task(progress=50)
    assert reviewed_end(t, 1.0, 0.5, 6.5, WORK_START, {}, NOW) == datetime(2026, 10, 16, 13, 0)


def test_reviewed_end_skips_holidays() -> None:
    t = task(progress=50)
    holidays = {date(2026, 10, 16): "休み"}
    assert reviewed_end(t, 1.0, 0.5, 6.5, WORK_START, holidays, NOW) == datetime(2026, 10, 19, 13, 0)


def test_reviewed_end_starts_from_the_planned_start_when_it_is_later() -> None:
    t = task(progress=50, planned_start=datetime(2026, 10, 19, 9, 0))
    assert reviewed_end(t, 1.0, 1.0, 6.5, WORK_START, {}, NOW) == datetime(2026, 10, 20, 10, 30)  # 月 6.5h + 火 1.5h


def test_reviewed_end_is_none_when_nothing_remains() -> None:
    assert reviewed_end(task(progress=100), 1.0, 0.5, 6.5, WORK_START, {}, NOW) is None


def test_reviewed_end_is_none_when_the_calculation_fails() -> None:
    assert reviewed_end(task(progress=50), 1.0, 0.5, 0.0, WORK_START, {}, NOW) is None


def _project_with(*tasks: Task) -> Project:
    parameters = [Parameter(n, [Level("高", 0.5)]) for n in ("a", "b", "c")]
    member = Member("田中", 1.0, {"a": "高", "b": "高", "c": "高"})
    return Project("p", members=[member], parameters=parameters, tasks=list(tasks), daily_hours=8.0)


def _worked(**extra: object) -> Task:
    base = dict(
        name="t", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50,
        planned_start=datetime(2026, 10, 5, 9),
    )
    return Task(**{**base, **extra})


def test_a_task_with_progress_needs_a_review_when_the_limit_changes_its_rate() -> None:
    t = _worked()
    result = limit_reviews(_project_with(t), RatioLimits(upper=1.0), {}, NOW)
    assert [task_ is t for task_, _ in result] == [True]
    assert result[0][1] > NOW


def test_nothing_needs_a_review_when_the_limits_do_not_change_the_rate() -> None:
    assert limit_reviews(_project_with(_worked()), RatioLimits(), {}, NOW) == []
    assert limit_reviews(_project_with(_worked()), RatioLimits(upper=1.5), {}, NOW) == []


@pytest.mark.parametrize(
    "skipped",
    [
        Task("未着手", assignees=[Assignee("田中", 1.0)], effort_hours=20.0),  # 実績も進捗度もない
        Task("終了", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.DONE, progress=50),
        Task("担当なし", effort_hours=20.0, status=Status.RUNNING, progress=50),
        Task("工数なし", assignees=[Assignee("田中", 1.0)], status=Status.RUNNING, progress=50),
        Task("メンバー外", assignees=[Assignee("鈴木", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50),
        Task(
            "週ごと", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50,
            weekly_crew=[[Assignee("田中", 1.0)]],
        ),
    ],
    ids=lambda t: t.name,
)
def test_tasks_outside_the_review_conditions_are_skipped(skipped: Task) -> None:
    assert limit_reviews(_project_with(skipped), RatioLimits(upper=1.0), {}, NOW) == []


def test_limit_reviews_does_not_change_the_project() -> None:
    project = _project_with(_worked())
    before = deepcopy(project)
    limit_reviews(project, RatioLimits(upper=1.0), {}, NOW)
    assert project == before
