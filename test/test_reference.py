from datetime import datetime

from projectapp.models import Actual, Assignee, Member, Project, Section, Status, Task, TaskKind
from projectapp.reference import compute_reference

NOW = datetime(2026, 10, 8, 10)


def D(month: int, day: int, hour: int = 9) -> datetime:
    return datetime(2026, month, day, hour)


def source() -> Project:
    return Project(
        "基盤",
        daily_hours=8.0,
        members=[Member("田中", 1.0)],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a", planned_start=D(10, 5), effort_hours=8.0, assignees=[Assignee("田中")],
                         status=Status.DONE, actuals=[Actual(D(10, 5), D(10, 5, 17))]),
                    Task("b", id="b", planned_start=D(10, 6), effort_hours=16.0, assignees=[Assignee("田中")],
                         progress=50, actuals=[Actual(D(10, 6), None)]),
                ],
            )
        ],
        tasks=[Task("c", id="c", planned_start=D(10, 20), effort_hours=8.0)],
    )


def test_the_span_progress_and_actuals_cover_the_whole_project() -> None:
    value = compute_reference(source(), {}, NOW)
    assert value.planned_start == D(10, 5)
    assert value.planned_end is not None and value.planned_end > D(10, 20)
    assert value.actual_start == D(10, 5)
    assert value.actual_end is None  # 実行中の区間がある
    assert value.finished is False
    # 工数の重み: a=8h で 100%、b=16h で 50%、c=8h で 0% → (800 + 800 + 0) / 32 = 50
    assert value.progress == 50


def test_delay_counts_unfinished_tasks_past_their_end() -> None:
    value = compute_reference(source(), {}, NOW)
    assert value.delayed == 1  # b は完了予定(10/7)を過ぎて終了していない。a は終了、c は先


def test_overlapping_assignments_become_a_peak_and_spans() -> None:
    project = Project(
        "基盤",
        members=[Member("田中", 1.0)],
        tasks=[
            Task("a", planned_start=D(10, 5), effort_hours=16.0, assignees=[Assignee("田中", 0.8)]),
            Task("b", planned_start=D(10, 5), effort_hours=16.0, assignees=[Assignee("田中", 0.5)]),
        ],
    )
    value = compute_reference(project, {}, NOW)
    assert value.peak_member == "田中" and round(value.peak_load, 2) == 1.3
    assert value.overloads and value.overloads[0].member == "田中"


def test_reference_rows_and_summaries_are_not_counted_and_an_empty_project_has_no_span() -> None:
    project = Project("基盤", tasks=[Task("ref", kind=TaskKind.REFERENCE, ref_project="x")])
    value = compute_reference(project, {}, NOW)
    assert (value.planned_start, value.planned_end, value.progress, value.finished) == (None, None, None, False)
    assert (value.delayed, value.peak_load, value.overloads) == (0, 0.0, ())


def test_a_finished_project_reports_its_last_actual_end() -> None:
    project = Project(
        "基盤",
        tasks=[Task("a", planned_start=D(10, 5), effort_hours=8.0, status=Status.DONE, actuals=[Actual(D(10, 5), D(10, 6))])],
    )
    value = compute_reference(project, {}, NOW)
    assert value.finished is True and value.actual_end == D(10, 6) and value.progress == 100
