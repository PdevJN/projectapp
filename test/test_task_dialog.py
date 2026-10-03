from datetime import datetime, time

from nicegui import ui
from nicegui.testing import User

from projectapp.models import Task
from projectapp.task_dialog import open_task_dialog


def mount_dialog(
    task: Task | None, saved: list[Task], work_start: time = time(9, 0)
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_task_dialog(task, saved.append, work_start=work_start),
        )


async def open_dialog(user: User) -> None:
    await user.open("/")
    user.find("open").click()


async def test_dates_only_fill_the_default_times(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 9, 0)
    assert saved[0].end == datetime(2026, 10, 7, 18, 0)


async def test_default_times_follow_the_work_start(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, work_start=time(8, 30))
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 8, 30)
    assert saved[0].end == datetime(2026, 10, 7, 17, 30)


async def test_time_inputs_are_hidden_until_the_checkbox_is_checked(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")
    await user.should_not_see(marker="task-end-time")
    user.find(marker="task-use-time").click()
    await user.should_see(marker="task-start-time")
    await user.should_see(marker="task-end-time")


async def test_checked_times_are_used(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-end-time").clear().type("16:45")
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 10, 15)
    assert saved[0].end == datetime(2026, 10, 7, 16, 45)


async def test_unchecking_resets_the_times_to_the_defaults(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-use-time").click()  # 外す
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 9, 0)


async def test_a_task_with_non_default_times_opens_with_the_times_shown(user: User) -> None:
    task = Task("既存", start=datetime(2026, 10, 5, 10, 15), end=datetime(2026, 10, 7, 16, 45))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_see(marker="task-start-time")
    assert user.find(marker="task-start-time").elements.pop().value == "10:15"
    assert user.find(marker="task-end-time").elements.pop().value == "16:45"


async def test_a_task_with_default_times_opens_with_the_times_hidden(user: User) -> None:
    task = Task("既存", start=datetime(2026, 10, 5, 9, 0), end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")


async def test_an_automatic_end_is_kept_when_nothing_is_edited(user: User) -> None:
    # 工数から算出された終了(15:30)は補う終了(18:00)と違うので、時刻を出した状態で開く
    saved: list[Task] = []
    task = Task(
        "旧",
        start=datetime(2026, 10, 5, 9, 0),
        end=datetime(2026, 10, 5, 15, 30),
        effort_hours=6.5,
        end_auto=True,
    )
    mount_dialog(task, saved)
    await open_dialog(user)
    await user.should_see(marker="task-end-time")
    user.find(marker="task-save").click()
    assert saved[0].end == datetime(2026, 10, 5, 15, 30)
    assert saved[0].end_auto is True


async def test_checked_but_empty_time_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-use-time").click()
    user.find(marker="task-start-time").clear()
    user.find(marker="task-save").click()
    await user.should_see("時刻の形式が正しくありません")
    assert saved == []


async def test_an_end_date_before_the_start_date_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-07")
    user.find(marker="task-end-date").type("2026-10-05")
    user.find(marker="task-save").click()
    await user.should_see("終了は開始以降の日時にしてください")
    assert saved == []


async def test_an_impossible_date_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-13-45")
    user.find(marker="task-save").click()
    await user.should_see("日時の形式が正しくありません")
    assert saved == []


async def test_clearing_the_end_date_saves_an_empty_end(user: User) -> None:
    saved: list[Task] = []
    task = Task("既存", start=datetime(2026, 10, 5, 9, 0), end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, saved)
    await open_dialog(user)
    user.find(marker="task-end-date").clear()
    user.find(marker="task-save").click()
    assert saved[0].end is None


async def test_start_and_end_are_side_by_side(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    start_column = user.find(marker="task-start-date").elements.pop().parent_slot.parent
    end_column = user.find(marker="task-end-date").elements.pop().parent_slot.parent
    assert start_column is not end_column
    assert start_column.parent_slot.parent is end_column.parent_slot.parent
    assert isinstance(start_column.parent_slot.parent, ui.row)


async def test_date_picker_and_field_stay_in_sync(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="open-start-date-picker").click()
    picker = user.find(marker="start-date-picker").elements.pop()
    field = user.find(marker="task-start-date").elements.pop()
    with user.client:
        picker.set_value("2026-10-09")
    assert field.value == "2026-10-09"
    user.find(marker="task-start-date").clear().type("2026-10-12")
    assert picker.value == "2026-10-12"


async def test_time_picker_and_field_stay_in_sync(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-use-time").click()
    user.find(marker="open-end-time-picker").click()
    picker = user.find(marker="end-time-picker").elements.pop()
    field = user.find(marker="task-end-time").elements.pop()
    assert picker.value == "18:00"
    with user.client:
        picker.set_value("15:30")
    assert field.value == "15:30"
