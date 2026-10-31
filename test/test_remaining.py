from datetime import date, datetime

from projectapp.models import Actual, Assignee, Member, Project, Status, Task
from projectapp.remaining import overlap_hours, remaining_hours, total_effort

NOW = datetime(2026, 10, 7, 12)  # 水曜。稼働の枠は 9:00〜15:30


def project_of(*tasks: Task) -> Project:
    return Project("P", base_date=date(2026, 10, 5), members=[Member("田中", 1.0)], tasks=list(tasks))


def test_total_effort_is_the_task_effort() -> None:
    assert total_effort(Task("a", effort_hours=12.5)) == 12.5


def test_overlap_hours_is_the_part_of_the_window_inside_the_range() -> None:
    project = project_of()
    assert overlap_hours(project, {}, date(2026, 10, 7), datetime(2026, 10, 7, 12), datetime(2026, 10, 7, 18)) == 3.5
    assert overlap_hours(project, {}, date(2026, 10, 10), datetime(2026, 10, 10, 9), datetime(2026, 10, 10, 18)) == 0.0


def test_remaining_is_the_full_effort_without_progress_or_actuals() -> None:
    task = Task("a", planned_start=datetime(2026, 10, 6, 9), effort_hours=10)
    assert remaining_hours(task, project_of(task), {}, NOW) == 10


def test_remaining_takes_the_progress_off() -> None:
    task = Task("a", planned_start=datetime(2026, 10, 6, 9), effort_hours=10, status=Status.RUNNING, progress=40)
    assert remaining_hours(task, project_of(task), {}, NOW) == 6


def test_remaining_takes_the_finished_intervals_off() -> None:
    worked = [Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 13))]
    task = Task("a", effort_hours=10, status=Status.RUNNING, assignees=[Assignee("田中")], actuals=worked)
    assert remaining_hours(task, project_of(task), {}, NOW) == 6


def test_remaining_counts_an_open_interval_up_to_now_inside_the_window() -> None:
    task = Task("a", effort_hours=10, status=Status.RUNNING, actuals=[Actual(datetime(2026, 10, 7, 9), None)])
    assert remaining_hours(task, project_of(task), {}, NOW) == 7
