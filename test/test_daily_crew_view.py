from datetime import date, datetime
from pathlib import Path

from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.models import Assignee, Member, Task, WorkDay
from projectapp.views import MainView
from test_views import make_view

START = datetime(2099, 1, 5, 9)  # 月曜


async def opened(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中"), Member("鈴木")]
    view.project.tasks.append(
        Task(
            "a",
            id="ta",
            planned_start=START,
            effort_hours=60.0,
            assignees=[Assignee("田中")],
            weekly_crew=[[Assignee("田中")], [Assignee("田中")]],
        )
    )
    view.after_edit()
    view.mark_clean()
    return view


def text_of(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


async def test_split_edit_and_merge_a_week_are_each_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 1)
    task = view.project.tasks[0]
    assert list(task.daily_crew) == [1] and view.is_dirty()
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木")]] * 4
    view.save_week_days((), 0, 1, days)
    task = view.project.tasks[0]
    assert [a.name for a in task.weekly_crew[1]] == ["田中", "鈴木"]
    assert [a.name for a in task.assignees] == ["田中", "鈴木"]
    view.merge_week_days((), 0, 1)
    task = view.project.tasks[0]
    assert task.daily_crew == {} and [a.name for a in task.weekly_crew[1]] == ["田中"]
    view.undo()
    assert list(view.project.tasks[0].daily_crew) == [1]
    view.undo()
    view.undo()
    assert view.project.tasks[0].daily_crew == {}


async def test_stopping_weekly_crew_drops_the_daily_crew(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 0)
    view.toggle_weeks((), 0)
    task = view.project.tasks[0]
    assert task.weekly_crew == [] and task.daily_crew == {}


async def test_clicking_a_week_offers_to_split_and_a_daily_week_opens_the_day_dialog(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    with user.client:
        view.edit_week_crew((), 0, 0)
    await user.should_see(marker="week-edit-split")
    user.find(marker="week-edit-split").click()
    assert list(view.project.tasks[0].daily_crew) == [0]
    with user.client:
        view.edit_week_crew((), 0, 0)
    await user.should_see(marker="day-edit-title")
    assert text_of(user, "day-edit-title").startswith("第1週")
    await user.should_see(marker="day-edit-merge")
    await user.should_see(marker="day-edit-row-4")  # 平日(月〜金)の行
    await user.should_not_see(marker="day-edit-row-5")  # 土日は休みなので出さない
    await user.should_not_see(marker="day-edit-row-6")


async def test_a_holiday_is_hidden_from_the_day_dialog_and_keeps_its_crew(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.holidays[date(2099, 1, 7)] = "祝"  # 水曜
    view.split_week_days((), 0, 0)
    with user.client:
        view.edit_week_crew((), 0, 0)
    await user.should_see(marker="day-edit-row-1")
    await user.should_not_see(marker="day-edit-row-2")
    await user.should_see(marker="day-edit-row-3")
    user.find(marker="day-edit-save").click()
    task = view.project.tasks[0]
    assert [a.name for a in task.daily_crew[0][2]] == ["田中"]


def tooltips(user: User, marker: str) -> list[str]:
    from nicegui import ui

    chip = user.find(marker=marker).elements.pop()
    return [
        c.text
        for c in chip.parent_slot.children
        if isinstance(c, ui.tooltip) and c.props.get("target") == f"#{chip.html_id}"
    ]


async def test_a_daily_week_shows_seven_thin_chips_apart_from_the_weekly_chip(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 0)
    for j in range(7):
        await user.should_see(marker=f"day-chip-top-0-0-{j}")
    await user.should_not_see(marker="week-chip-top-0-0")
    await user.should_see(marker="week-chip-top-0-1")
    day = user.find(marker="day-chip-top-0-0-2").elements.pop()
    assert "day-chip" in day.classes
    assert "week-chip" not in day.classes
    assert "第1週 1/7(水)" in tooltips(user, "day-chip-top-0-0-2")[0]
    assert "第2週 1/12〜1/18" in tooltips(user, "week-chip-top-0-1")[0]


async def test_the_added_mark_follows_the_day_the_person_appears(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 1)
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木")]] * 4
    view.save_week_days((), 0, 1, days)
    await user.should_not_see(marker="week-added-top-0-1-2")
    await user.should_see(marker="week-added-top-0-1-3")
    await user.should_not_see(marker="week-added-top-0-1-4")


async def test_renaming_a_member_reaches_the_daily_crew(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 0)
    members = [Member("田中太郎"), Member("鈴木")]
    view.apply_members(members, {"田中": "田中太郎"})
    task = view.project.tasks[0]
    assert all(a.name == "田中太郎" for d in task.daily_crew[0] for a in d)


async def test_editing_a_week_beyond_a_daily_last_week_continues_its_last_day(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    task = view.project.tasks[0]
    task.weekly_crew = [[Assignee("田中"), Assignee("鈴木")]]
    task.daily_crew = {
        0: [[Assignee("田中")]] * 6 + [[Assignee("田中"), Assignee("鈴木")]]
    }
    view.after_edit()
    with user.client:
        view.edit_week_crew((), 0, 2)
    await user.should_see(marker="week-edit-save")
    user.find(marker="week-edit-save").click()
    weeks = view.project.tasks[0].weekly_crew
    assert [a.name for a in weeks[1]] == ["田中", "鈴木"]  # 7 日目の担当が続く


async def test_a_day_chip_on_a_holiday_is_faded_without_a_name_and_the_mark_moves_on(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.base_holidays[date(2099, 1, 7)] = "祝"  # 水曜
    view.split_week_days((), 0, 1)  # 第 2 週: 1/12(月)〜
    view.base_holidays[date(2099, 1, 14)] = "祝"  # 第 2 週の水曜
    days = [[Assignee("田中")]] * 2 + [[Assignee("田中"), Assignee("鈴木")]] * 5
    view.save_week_days((), 0, 1, days)
    view.after_edit()
    await user.should_see(marker="day-chip-top-0-1-2")
    off = user.find(marker="day-chip-top-0-1-2").elements.pop()  # 1/14(水)
    assert "day-off" in off.classes and off.text == ""
    assert "休みの日" in tooltips(user, "day-chip-top-0-1-2")[0]
    await user.should_not_see(marker="week-added-top-0-1-2")  # 休みの日には付けない
    await user.should_see(marker="week-added-top-0-1-3")  # 最初の稼働日(木)に付く
    working = user.find(marker="day-chip-top-0-1-1").elements.pop()
    assert "day-off" not in working.classes


async def test_a_bar_ending_on_a_day_off_is_drawn_through_the_next_working_day(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    gantt = view.gantt
    end = datetime(2099, 1, 10, 12)  # 土曜
    assert gantt.through_next_working_day(end).date() == date(2099, 1, 12)  # 月曜
    weekday = datetime(2099, 1, 9, 12)
    assert gantt.through_next_working_day(weekday) == weekday


async def test_a_day_chip_is_faded_when_everyone_on_it_has_a_personal_day_off(
    user: User, tmp_path: Path
) -> None:
    from projectapp.models import WorkDay

    view = await opened(user, tmp_path)
    view.project.members[1].work_days = [WorkDay(date(2099, 1, 14), None, None)]
    view.split_week_days((), 0, 1)
    days = [[Assignee("田中")]] * 2 + [[Assignee("鈴木")]] + [[Assignee("田中")]] * 4
    view.save_week_days((), 0, 1, days)
    view.after_edit()
    await user.should_see(marker="day-chip-top-0-1-2")
    assert "day-off" in user.find(marker="day-chip-top-0-1-2").elements.pop().classes
    assert (
        "day-off" not in user.find(marker="day-chip-top-0-1-1").elements.pop().classes
    )


async def test_a_late_task_with_added_crew_is_drawn_through_the_forecast(
    user: User, tmp_path: Path
) -> None:
    from datetime import timedelta

    view = await opened(user, tmp_path)
    task = view.project.tasks[0]
    task.effort_hours = 13.0
    task.weekly_crew = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    view.after_edit()
    gantt = view.gantt
    planned = gantt.schedule.bar_end(task)
    assert planned is not None
    gantt.now = lambda: planned + timedelta(days=2)  # 予定超過
    gantt.forecast_cache.clear()
    view.after_edit()
    await user.should_see(marker="planned-end-tick-top-0")
    await user.should_not_see(marker="forecast-line-top-0")
    await user.should_see(marker="forecast-label-top-0")


async def test_confirming_and_investing_notify_when_a_day_off_delays_the_start(
    user: User, tmp_path: Path
) -> None:
    from unittest.mock import patch

    view = await opened(user, tmp_path)
    view.project.members[1].work_days = [WorkDay(date(2099, 1, 12), None, None)]
    from projectapp.crew_trial import TrialCrew

    view.trials = {"ta": TrialCrew("ta", ("鈴木",), date(2099, 1, 12))}
    with user.client, patch("projectapp.views.ui.notify") as notify:
        view.confirm_trials()
    assert any(
        "鈴木 は 1/13 から効きます" in str(c.args[0]) for c in notify.call_args_list
    )
