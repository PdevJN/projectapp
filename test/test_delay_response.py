from datetime import date, datetime
from pathlib import Path

from nicegui.testing import User

from projectapp import history_log
from projectapp.calendar import save_cache
from projectapp.models import Assignee, Member, Task
from projectapp.timeline import effective_end
from projectapp.views import MainView
from test_views import make_view, wait_until

START = datetime(2099, 1, 5, 9)


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
    assert view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
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
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    view.try_crew("ta", ["鈴木"], date(2099, 1, 19))
    assert len(view.trials) == 1
    assert view.trials["ta"].start == date(2099, 1, 19)


async def test_an_unsuitable_task_is_refused(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.project.tasks.append(Task("b", id="tb", planned_start=START, effort_hours=8.0))
    view.after_edit()
    assert not view.try_crew("tb", ["鈴木"], date(2099, 1, 12))  # 担当なし
    assert not view.try_crew("nope", ["鈴木"], date(2099, 1, 12))  # 存在しない
    assert view.trials == {}


async def test_confirming_writes_weekly_crew_as_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
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
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    view.drop_trial("ta")
    assert view.trials == {}
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    view.clear_trials()
    assert view.trials == {}
    assert view.trial_results() == {}


async def test_a_trial_for_a_deleted_task_is_dropped_on_redraw(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
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


async def saved_with_trial(user: User, tmp_path: Path) -> MainView:
    view = await opened(user, tmp_path)
    assert view.save_as_new("確認")  # 最初の保存でファイルを作る
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    user.find(marker="save-project").click()
    await user.should_see(marker="trial-save-dialog")
    return view


async def test_saving_with_trials_asks_and_confirm_saves_the_weekly_crew(
    user: User, tmp_path: Path
) -> None:
    view = await saved_with_trial(user, tmp_path)
    await user.should_see("1 件の増員を確定して保存します")
    user.find(marker="trial-save-confirm").click()
    assert await wait_until(lambda: view.trials == {} and not view.is_dirty())
    assert view.project.tasks[0].weekly_crew != []


async def test_keep_saves_without_confirming_and_leaves_the_trial(
    user: User, tmp_path: Path
) -> None:
    view = await saved_with_trial(user, tmp_path)
    user.find(marker="trial-save-keep").click()
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    assert "ta" in view.trials
    assert view.project.tasks[0].weekly_crew == []


async def test_discard_drops_the_trial_and_saves(user: User, tmp_path: Path) -> None:
    view = await saved_with_trial(user, tmp_path)
    user.find(marker="trial-save-discard").click()
    assert await wait_until(lambda: view.trials == {})
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    assert view.project.tasks[0].weekly_crew == []


async def test_cancel_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await saved_with_trial(user, tmp_path)
    user.find(marker="trial-save-cancel").click()
    assert "ta" in view.trials and view.project.tasks[0].weekly_crew == []


async def test_saving_without_trials_does_not_ask(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    assert view.save_as_new("確認")
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    await user.should_not_see(marker="trial-save-dialog")


async def test_an_overdue_task_gets_a_from_now_estimate_that_is_earlier(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    view.project.tasks.append(
        Task(
            "late",
            id="tl",
            planned_start=datetime(2026, 10, 12, 9),
            effort_hours=40.0,
            assignees=[Assignee("田中")],
        )
    )
    view.after_edit()
    assert view.try_invest_on_gantt(("鈴木",)) == 1
    result = view.trial_results()["tl"]
    assert result.from_now
    assert result.trial_end is not None and result.baseline_end is not None
    assert result.trial_end < result.baseline_end
    assert (result.days_earlier or 0) > 0


async def test_try_invest_on_gantt_includes_warning_tasks_when_warnings_count_as_late(
    user: User, tmp_path: Path, monkeypatch
) -> None:
    from projectapp import views as views_module
    from projectapp.dashboard import LateBasis

    view = await opened(user, tmp_path)  # 将来の通常タスク ta(遅れていない)
    monkeypatch.setattr(
        views_module, "warning_pace", lambda task, *args, **kwargs: object()
    )
    view.dashboard_late_basis = LateBasis.DELAY
    assert view.try_invest_on_gantt(("鈴木",)) == 0  # 遅れのみ: 警告は対象外
    view.dashboard_late_basis = LateBasis.WARNING
    assert view.try_invest_on_gantt(("鈴木",)) == 1  # 警告を含む: 対象
    assert set(view.trials) == {"ta"}


async def test_try_invest_on_gantt_starts_the_next_day(
    user: User, tmp_path: Path
) -> None:
    from datetime import timedelta

    from projectapp import clock

    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    view.project.tasks.append(
        Task(
            "late",
            id="tl",
            planned_start=datetime(2026, 10, 12, 9),
            effort_hours=40.0,
            assignees=[Assignee("田中")],
        )
    )
    view.after_edit()
    assert view.try_invest_on_gantt(("鈴木",)) == 1
    assert view.trials["tl"].start == clock.now().date() + timedelta(days=1)


async def test_try_invest_on_gantt_skips_the_tasks_left_out(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    for name, ident in (("one", "t1"), ("two", "t2")):
        view.project.tasks.append(
            Task(
                name,
                id=ident,
                planned_start=datetime(2026, 10, 12, 9),
                effort_hours=16.0,
                assignees=[Assignee("田中")],
            )
        )
    view.after_edit()
    assert view.try_invest_on_gantt(("鈴木",), ("t1",)) == 1
    assert set(view.trials) == {"t2"}
