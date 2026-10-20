from datetime import date, datetime, time

import pytest

from projectapp.models import Actual, Status, Task, TaskKind
from projectapp.reassign import consumed_hours, needs_review, reviewed_end

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
    assert reviewed_end(t, 1.0, 1.0, 6.5, WORK_START, {}, NOW) == datetime(2026, 10, 20, 11, 30)  # 月 6.5h + 火 1.5h


def test_reviewed_end_is_none_when_nothing_remains() -> None:
    assert reviewed_end(task(progress=100), 1.0, 0.5, 6.5, WORK_START, {}, NOW) is None


def test_reviewed_end_is_none_when_the_calculation_fails() -> None:
    assert reviewed_end(task(progress=50), 1.0, 0.5, 0.0, WORK_START, {}, NOW) is None
