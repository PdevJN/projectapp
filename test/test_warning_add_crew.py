from datetime import datetime
from pathlib import Path

import pytest
from nicegui.testing import User

from projectapp import clock, history_log
from projectapp.calendar import save_cache
from projectapp.models import Assignee, Member, Task
from projectapp.views import MainView
from test_views import make_view

NOW = datetime(2026, 10, 7, 12)  # 水曜の昼


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


async def opened(user: User, tmp_path: Path, **changes: object) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中"), Member("鈴木")]
    task = Task(
        "遅れ気味",
        id="tw",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=19.5,
        progress=50,
        assignees=[Assignee("田中")],
    )
    for key, value in changes.items():
        setattr(task, key, value)
    view.project.tasks.append(task)
    view.after_edit()
    view.mark_clean()
    return view


async def test_adding_crew_starts_the_next_day_in_a_daily_week_as_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    before = history_log.dirty_key(view.project)
    assert view.add_crew_to_warning("tw", "鈴木")
    task = view.project.tasks[0]
    assert [a.name for a in task.assignees] == ["田中", "鈴木"]
    assert list(task.daily_crew) == [0]  # 10/5(月)起点の週に、10/8(木)から
    assert [[a.name for a in d] for d in task.daily_crew[0]] == [["田中"]] * 3 + [
        ["田中", "鈴木"]
    ] * 4
    assert view.is_dirty()
    view.undo()
    assert view.project.tasks[0].weekly_crew == []
    assert view.project.tasks[0].daily_crew == {}
    assert history_log.dirty_key(view.project) == before


async def test_adding_a_person_who_is_off_tells_when_it_takes_effect(
    user: User, tmp_path: Path
) -> None:
    from datetime import date

    from projectapp.models import WorkDay

    view = await opened(user, tmp_path)
    view.project.members[1].work_days = [
        WorkDay(date(2026, 10, 8)),
        WorkDay(date(2026, 10, 9)),
    ]
    assert view.add_crew_to_warning("tw", "鈴木")
    # 10/8・9 は個人の休み、10/10・11 は土日。効き始めは 10/12(月)
    await user.should_see("10/12")


async def test_adding_crew_is_refused_when_the_task_is_no_longer_a_warning(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path, progress=90)
    assert not view.add_crew_to_warning("tw", "鈴木")
    assert view.project.tasks[0].weekly_crew == []


async def test_adding_crew_is_refused_for_an_unknown_task_or_member_or_existing_crew(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    assert not view.add_crew_to_warning("none", "鈴木")
    assert not view.add_crew_to_warning("tw", "だれか")
    assert not view.add_crew_to_warning("tw", "田中")
    assert view.project.tasks[0].weekly_crew == []
