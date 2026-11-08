from datetime import date, datetime
from pathlib import Path

from nicegui.testing import User

from projectapp import history_log
from projectapp.calendar import save_cache
from projectapp.models import Assignee, Member, Task
from projectapp.timeline import effective_end
from projectapp.views import MainView
from test_views import make_view

START = datetime(2026, 11, 2, 9)


def seed(view: MainView) -> None:
    view.project.members = [Member("田中"), Member("鈴木")]
    view.project.tasks.append(
        Task(
            "a",
            id="ta",
            planned_start=START,
            effort_hours=60.0,
            assignees=[Assignee("田中")],
        )
    )
    view.after_edit()
    view.mark_clean()


async def opened(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    seed(views[0])
    return views[0]


async def test_a_trial_changes_the_result_but_not_the_file_or_dirty_state(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    before = history_log.dirty_key(view.project)
    assert view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    assert not view.is_dirty()
    assert history_log.dirty_key(view.project) == before
    assert view.project.tasks[0].weekly_crew == []  # データは変わらない
    result = view.trial_results()["ta"]
    assert result.trial_end is not None and result.original_end is not None
    assert result.trial_end < result.original_end
    assert view.project == view.committed  # 元に戻す用の確定した状態も変わらない


async def test_the_same_task_is_replaced_not_doubled(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.try_crew("ta", ["鈴木"], date(2026, 11, 16))
    assert len(view.trials) == 1
    assert view.trials["ta"].start == date(2026, 11, 16)


async def test_an_unsuitable_task_is_refused(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.project.tasks.append(Task("b", id="tb", planned_start=START, effort_hours=8.0))
    view.after_edit()
    assert not view.try_crew("tb", ["鈴木"], date(2026, 11, 9))  # 担当なし
    assert not view.try_crew("nope", ["鈴木"], date(2026, 11, 9))  # 存在しない
    assert view.trials == {}


async def test_confirming_writes_weekly_crew_as_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    expected = view.trial_results()["ta"].trial_end
    assert view.confirm_trials() == 1
    assert view.trials == {}
    assert view.is_dirty()
    task = view.project.tasks[0]
    assert [a.name for a in task.assignees] == ["田中", "鈴木"]
    assert len(task.weekly_crew) == 2
    assert effective_end(task, view.project, view.holidays) == expected
    view.undo()
    assert view.project.tasks[0].weekly_crew == []


async def test_dropping_and_clearing_remove_trials(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.drop_trial("ta")
    assert view.trials == {}
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.clear_trials()
    assert view.trials == {}
    assert view.trial_results() == {}


async def test_a_trial_for_a_deleted_task_is_dropped_on_redraw(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.project.tasks.clear()
    view.after_edit()
    assert view.trial_results() == {}
    assert view.trials == {}


async def test_try_invest_on_gantt_puts_trials_on_overdue_tasks(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    view.project.tasks.append(
        Task(
            "late",
            id="tl",
            planned_start=datetime(2026, 10, 12, 9),
            effort_hours=16.0,
            assignees=[Assignee("田中")],
        )
    )
    view.project.tasks.append(
        Task(
            "ok",
            id="to",
            planned_start=datetime(2099, 1, 5, 9),
            effort_hours=8.0,
            assignees=[Assignee("田中")],
        )
    )
    view.after_edit()
    assert view.try_invest_on_gantt(("鈴木",)) == 1
    assert set(view.trials) == {"tl"}  # 遅れているタスクだけ
    assert view.dashboard_kind is None
