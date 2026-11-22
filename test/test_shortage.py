from datetime import date, datetime

import pytest

from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from projectapp.shortage import (
    Shortage,
    due_of,
    shortage_hint,
    shortage_text,
    task_shortage,
)

MON = datetime(2026, 10, 5, 9)  # 稼働の枠は 9:00〜15:30(6.5h)
FRI = datetime(2026, 10, 9, 17)  # 月〜金の稼働量は 5 日 × 6.5h = 32.5h


def project_of(*tasks: Task) -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        sections=[Section("s", list(tasks))],
    )


def task_of(**kwargs) -> Task:
    base = dict(
        planned_start=MON,
        effort_hours=40.0,
        deadline=FRI,
        assignees=[Assignee("田中")],
    )
    return Task("設計", **{**base, **kwargs})


def judged(task: Task, now: datetime = MON) -> Shortage | str:
    return task_shortage(task, project_of(task), {}, now)


def test_the_due_is_the_deadline_then_a_manual_planned_end() -> None:
    manual = datetime(2026, 10, 8, 17)
    assert due_of(task_of()) == (FRI, "締切")
    assert due_of(
        task_of(deadline=None, planned_end=manual, planned_end_manual=True)
    ) == (
        manual,
        "完了予定",
    )
    assert (
        due_of(task_of(deadline=None, planned_end=manual)) is None
    )  # 算出の完了予定は基準にしない
    assert due_of(task_of(deadline=None)) is None


def test_a_shortage_is_the_remaining_effort_minus_the_capacity_to_the_due() -> None:
    value = judged(task_of())
    assert isinstance(value, Shortage)
    assert value.remaining == pytest.approx(40.0)
    assert value.capacity == pytest.approx(32.5)
    assert value.gap == pytest.approx(7.5) and value.kind == "不足"
    assert value.unit == pytest.approx(32.5)
    assert value.people == pytest.approx(7.5 / 32.5)
    assert value.basis == "締切"


def test_a_lower_rate_makes_the_shortage_bigger() -> None:
    value = judged(task_of(assignees=[Assignee("田中", 0.5)]))
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(16.25) and value.gap == pytest.approx(23.75)


def test_more_members_make_a_margin() -> None:
    value = judged(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert isinstance(value, Shortage)
    assert value.gap == pytest.approx(-25.0) and value.kind == "余裕"
    assert value.people == pytest.approx(25.0 / 32.5)  # 絶対値


def test_a_gap_that_rounds_to_zero_is_just_right() -> None:
    value = judged(task_of(effort_hours=32.51))
    assert isinstance(value, Shortage) and value.kind == "ちょうど"
    assert shortage_text(value) == "ちょうど"


def test_progress_reduces_the_remaining_effort() -> None:
    value = judged(task_of(progress=50))
    assert isinstance(value, Shortage)
    assert value.remaining == pytest.approx(20.0) and value.kind == "余裕"


def test_a_task_without_assignees_has_no_capacity_but_the_unit_still_counts() -> None:
    value = judged(task_of(assignees=[]))
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(32.5)  # 担当者なしは換算率 1 の 1 人
    # (pace.py と同じ扱い)


def test_the_weekly_crew_changes_the_capacity() -> None:
    task = task_of(
        weekly_crew=[[Assignee("田中", 0.5)], [Assignee("田中")]],
        deadline=datetime(2026, 10, 16, 17),
    )
    value = judged(task)
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(16.25 + 32.5)


def test_a_future_start_counts_from_the_start() -> None:
    task = task_of(planned_start=datetime(2026, 10, 7, 9))  # 水曜から
    value = judged(task, now=MON)
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(3 * 6.5)


def test_holidays_do_not_count() -> None:
    task = task_of()
    value = task_shortage(task, project_of(task), {date(2026, 10, 7): "休み"}, MON)
    assert isinstance(value, Shortage) and value.capacity == pytest.approx(26.0)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        (task_of(effort_hours=0.0), "工数がありません"),
        (task_of(deadline=None), "基準日"),
        (task_of(planned_start=None), "開始日がありません"),
        (task_of(deadline=datetime(2026, 10, 1, 17)), "基準日を過ぎています"),
        (task_of(progress=100), "残りの工数がありません"),
        (task_of(status=Status.DONE), "終了"),
        (task_of(kind=TaskKind.CHECKPOINT), "通常"),
    ],
)
def test_reasons_when_it_cannot_be_shown(task: Task, reason: str) -> None:
    value = judged(task)
    assert isinstance(value, str) and reason in value


def test_the_text_and_the_hint() -> None:
    value = judged(task_of())
    assert isinstance(value, Shortage)
    assert shortage_text(value) == "あと 7.5h 足りません(約 0.2 人)"
    assert shortage_hint(value) == "残り 40.0h / 稼働 32.5h(10/09 17:00 まで。締切)"
    margin = judged(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert isinstance(margin, Shortage)
    assert shortage_text(margin) == "余裕 25.0h(約 0.8 人)"


def test_a_due_before_the_start_has_its_own_reason() -> None:
    value = judged(task_of(planned_start=datetime(2026, 10, 12, 9)), now=MON)
    assert isinstance(value, str) and "開始より前" in value


def test_a_tiny_gap_does_not_show_zero_people() -> None:
    value = judged(task_of(effort_hours=32.6))
    assert isinstance(value, Shortage)
    assert shortage_text(value) == "あと 0.1h 足りません"


def test_remaining_and_capacity_match_the_warning_pace() -> None:
    from projectapp.pace import pace

    task = task_of(deadline=None, planned_end=FRI, planned_end_manual=True)
    value = judged(task)
    expected = pace(task, project_of(task), {}, MON)
    assert isinstance(value, Shortage) and expected is not None
    assert value.remaining == pytest.approx(expected.remaining)
    assert value.capacity == pytest.approx(expected.capacity)
