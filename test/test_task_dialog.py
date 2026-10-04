import asyncio

import pytest
from datetime import date, datetime, time

from nicegui import ui
from nicegui.testing import User

from projectapp.models import Actual, Member, Status, Task
from projectapp.task_dialog import open_task_dialog


def mount_dialog(
    task: Task | None,
    saved: list[Task],
    work_start: time = time(9, 0),
    deleted: list[str] | None = None,
    daily_hours: float = 6.5,
    holidays: dict[date, str] | None = None,
    members: list[Member] | None = None,
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_task_dialog(
                task,
                saved.append,
                work_start=work_start,
                on_delete=None if deleted is None else lambda: deleted.append("deleted"),
                daily_hours=daily_hours,
                holidays=holidays,
                members=members,
            ),
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
    assert saved[0].planned_start == datetime(2026, 10, 5, 9, 0)
    assert saved[0].planned_end == datetime(2026, 10, 7, 18, 0)


async def test_default_times_follow_the_work_start(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, work_start=time(8, 30))
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 5, 8, 30)
    assert saved[0].planned_end == datetime(2026, 10, 7, 17, 30)


async def test_time_inputs_are_hidden_until_the_checkbox_is_checked(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")
    await user.should_not_see(marker="task-end-time")
    user.find(marker="task-start-use-time").click()
    await user.should_see(marker="task-start-time")
    await user.should_not_see(marker="task-end-time")  # 終了は、終了のチェックで出る
    user.find(marker="task-end-use-time").click()
    await user.should_see(marker="task-end-time")


async def test_checked_times_are_used(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-end-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-end-time").clear().type("16:45")
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 5, 10, 15)
    assert saved[0].planned_end == datetime(2026, 10, 7, 16, 45)


async def test_unchecking_resets_the_times_to_the_defaults(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-end-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-end-time").clear().type("16:45")
    user.find(marker="task-start-use-time").click()  # 開始だけ外す
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 5, 9, 0)  # 開始は補う時刻に戻る
    assert saved[0].planned_end == datetime(2026, 10, 7, 16, 45)  # 終了は変わらない


async def test_a_typed_start_time_is_kept_when_the_checkbox_is_toggled(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-start-time").clear().type("11:00")
    user.find(marker="task-start-use-time").click()  # 外す
    user.find(marker="task-start-use-time").click()  # 入れ直す
    assert user.find(marker="task-start-time").elements.pop().value == "11:00"


async def test_an_existing_end_time_is_kept_when_the_checkbox_is_toggled(user: User) -> None:
    task = Task("旧", planned_start=datetime(2026, 10, 5, 9, 0), planned_end=datetime(2026, 10, 5, 15, 30))
    mount_dialog(task, [])
    await open_dialog(user)
    user.find(marker="task-end-use-time").click()  # 外す
    user.find(marker="task-end-use-time").click()  # 入れ直す
    assert user.find(marker="task-end-time").elements.pop().value == "15:30"


async def test_unchecked_end_is_saved_with_the_default_time_even_if_a_time_was_typed(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-end-use-time").click()
    user.find(marker="task-end-time").clear().type("16:45")
    user.find(marker="task-end-use-time").click()  # 外す: 値は残るが、保存には使わない
    user.find(marker="task-save").click()
    assert saved[0].planned_end == datetime(2026, 10, 7, 18, 0)


async def test_a_hidden_time_left_behind_is_not_a_change(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-start-time").clear().type("11:00")
    user.find(marker="task-start-use-time").click()  # 外す
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False


async def test_only_the_start_time_can_be_specified(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 5, 10, 15)
    assert saved[0].planned_end == datetime(2026, 10, 7, 18, 0)  # 終了は補う時刻のまま


async def test_only_the_end_time_can_be_specified(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-end-use-time").click()
    user.find(marker="task-end-time").clear().type("16:45")
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 5, 9, 0)  # 開始は補う時刻のまま
    assert saved[0].planned_end == datetime(2026, 10, 7, 16, 45)


async def test_a_task_with_non_default_times_opens_with_the_times_shown(user: User) -> None:
    task = Task("既存", planned_start=datetime(2026, 10, 5, 10, 15), planned_end=datetime(2026, 10, 7, 16, 45))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_see(marker="task-start-time")
    await user.should_see(marker="task-end-time")
    assert user.find(marker="task-start-time").elements.pop().value == "10:15"
    assert user.find(marker="task-end-time").elements.pop().value == "16:45"


async def test_a_task_with_default_times_opens_with_the_times_hidden(user: User) -> None:
    task = Task("既存", planned_start=datetime(2026, 10, 5, 9, 0), planned_end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")
    await user.should_not_see(marker="task-end-time")


async def test_an_automatic_end_shows_only_the_end_time(user: User) -> None:
    # 開始は始業時刻のままなので、時刻入力が出るのは終了側だけ
    task = Task("旧", planned_start=datetime(2026, 10, 5, 9, 0), planned_end=datetime(2026, 10, 5, 15, 30))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")
    await user.should_see(marker="task-end-time")


async def test_an_automatic_end_is_kept_when_nothing_is_edited(user: User) -> None:
    # 工数から算出された終了(15:30)は補う終了(18:00)と違うので、時刻を出した状態で開く
    saved: list[Task] = []
    task = Task(
        "旧",
        planned_start=datetime(2026, 10, 5, 9, 0),
        planned_end=datetime(2026, 10, 5, 15, 30),
        effort_hours=0.0,
    )
    mount_dialog(task, saved)
    await open_dialog(user)
    await user.should_see(marker="task-end-time")
    user.find(marker="task-save").click()
    assert saved[0].planned_end == datetime(2026, 10, 5, 15, 30)


async def test_checked_but_empty_time_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-start-use-time").click()
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
    await user.should_see("完了予定は開始予定以降の日時にしてください")
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
    task = Task("既存", planned_start=datetime(2026, 10, 5, 9, 0), planned_end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, saved)
    await open_dialog(user)
    user.find(marker="task-end-date").clear()
    user.find(marker="task-save").click()
    assert saved[0].planned_end is None


async def test_start_and_end_are_side_by_side(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    # 日付の入力は、側ごとの列の中の「編集用の入れ物」に入っている
    start_column = user.find(marker="task-start-date").elements.pop().parent_slot.parent.parent_slot.parent
    end_column = user.find(marker="task-end-date").elements.pop().parent_slot.parent.parent_slot.parent
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
    user.find(marker="task-end-use-time").click()
    user.find(marker="open-end-time-picker").click()
    picker = user.find(marker="end-time-picker").elements.pop()
    field = user.find(marker="task-end-time").elements.pop()
    assert picker.value == "18:00"
    with user.client:
        picker.set_value("15:30")
    assert field.value == "15:30"


def dialog_of(user: User) -> ui.dialog:
    """画面にある、タスク編集ダイアログ(`persistent` なダイアログ)。"""
    return next(
        e
        for e in user.client.elements.values()
        if isinstance(e, ui.dialog) and e.props.get("persistent")
    )


def confirm_dialog_of(user: User) -> ui.dialog:
    """閉じる確認のダイアログ(「保存」ボタンを含むダイアログ)。"""
    element = user.find(marker="close-save").elements.pop()
    while not isinstance(element, ui.dialog):
        element = element.parent_slot.parent
    return element


async def test_the_dialog_is_persistent_and_listens_for_escape(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    dialog = dialog_of(user)
    assert dialog.props.get("persistent") is True
    assert "escapeKey" in {listener.type for listener in dialog._event_listeners.values()}


async def test_cancel_without_changes_closes_without_asking(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False
    assert confirm_dialog_of(user).value is False


async def test_cancel_with_changes_asks_first(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    assert confirm_dialog_of(user).value is True
    assert dialog_of(user).value is True
    assert saved == []


async def test_close_confirm_save_saves_and_closes(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    user.find(marker="close-save").click()
    assert [t.name for t in saved] == ["設計"]
    assert dialog_of(user).value is False


async def test_close_confirm_discard_closes_without_saving(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    user.find(marker="close-discard").click()
    assert saved == []
    assert dialog_of(user).value is False


async def test_close_confirm_back_keeps_the_dialog_and_the_input(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    user.find(marker="close-back").click()
    assert dialog_of(user).value is True
    assert user.find(marker="task-name").elements.pop().value == "設計"


async def test_close_confirm_save_with_an_invalid_input_shows_the_error_and_stays(
    user: User,
) -> None:
    # 名前を空にしたまま「保存」を選ぶ: エラーを出して、編集ダイアログに入力を残す
    saved: list[Task] = []
    mount_dialog(Task("既存", effort_hours=2.0), saved)
    await open_dialog(user)
    user.find(marker="task-name").clear()
    user.find(marker="task-cancel").click()
    user.find(marker="close-save").click()
    await user.should_see("名前を入力してください")
    assert dialog_of(user).value is True
    assert saved == []


async def test_changing_only_the_checkbox_is_not_a_change(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-end-use-time").click()
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False


async def test_changing_a_date_counts_as_a_change(user: User) -> None:
    task = Task("既存", planned_start=datetime(2026, 10, 5, 9, 0), planned_end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, [])
    await open_dialog(user)
    user.find(marker="task-end-date").clear().type("2026-10-08")
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_priority_changes_count_as_changes(user: User) -> None:
    mount_dialog(Task("既存"), [])
    await open_dialog(user)
    user.find(marker="priority-HIGH").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_a_new_task_has_no_delete_button(user: User) -> None:
    mount_dialog(None, [], deleted=[])
    await open_dialog(user)
    await user.should_not_see(marker="task-delete")


async def test_an_existing_task_without_a_delete_callback_has_no_delete_button(
    user: User,
) -> None:
    mount_dialog(Task("既存"), [])
    await open_dialog(user)
    await user.should_not_see(marker="task-delete")


async def test_delete_asks_for_confirmation_and_cancel_keeps_the_task(user: User) -> None:
    deleted: list[str] = []
    mount_dialog(Task("既存"), [], deleted=deleted)
    await open_dialog(user)
    user.find(marker="task-delete").click()
    await user.should_see("「既存」を削除しますか?")
    user.find(marker="delete-cancel").click()
    assert deleted == []
    assert dialog_of(user).value is True


async def test_delete_confirm_calls_the_callback_and_closes_the_dialog(user: User) -> None:
    deleted: list[str] = []
    mount_dialog(Task("既存"), [], deleted=deleted)
    await open_dialog(user)
    user.find(marker="task-delete").click()
    user.find(marker="delete-confirm").click()
    assert deleted == ["deleted"]
    assert dialog_of(user).value is False


async def test_delete_does_not_ask_about_unsaved_changes(user: User) -> None:
    deleted: list[str] = []
    mount_dialog(Task("既存"), [], deleted=deleted)
    await open_dialog(user)
    user.find(marker="task-name").type("変更")
    user.find(marker="task-delete").click()
    user.find(marker="delete-confirm").click()
    assert deleted == ["deleted"]
    assert confirm_dialog_of(user).value is False


async def test_a_manual_end_with_a_custom_time_can_still_be_unchecked(user: User) -> None:
    task = Task("手入力", planned_start=datetime(2026, 10, 5, 9, 0), planned_end=datetime(2026, 10, 5, 15, 30))
    mount_dialog(task, [])
    await open_dialog(user)
    checkbox = user.find(marker="task-end-use-time").elements.pop()
    assert checkbox.value is True
    assert checkbox.enabled is True


async def test_hiding_the_dialog_removes_its_elements(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    dialog = dialog_of(user)
    assert user.find(marker="task-name").elements
    with user.client:
        dialog.close()
    user.find(kind=ui.dialog).trigger("hide")
    assert dialog.id not in user.client.elements
    await user.should_not_see(marker="task-name")


async def test_reopening_does_not_pile_up_dialogs(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    with user.client:
        dialog_of(user).close()
    user.find(kind=ui.dialog).trigger("hide")
    user.find("open").click()
    assert len(user.find(marker="task-name").elements) == 1


async def test_a_half_typed_date_is_not_passed_to_the_picker(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="open-start-date-picker").click()
    picker = user.find(marker="start-date-picker").elements.pop()
    user.find(marker="task-start-date").clear().type("2026-1")
    await asyncio.sleep(0.3)
    assert picker.value is None
    user.find(marker="task-start-date").clear().type("2026-10-12")
    await asyncio.sleep(0.3)
    assert picker.value == "2026-10-12"


async def test_a_half_typed_time_is_not_passed_to_the_picker(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-end-use-time").click()
    user.find(marker="open-end-time-picker").click()
    picker = user.find(marker="end-time-picker").elements.pop()
    user.find(marker="task-end-time").clear().type("1")
    await asyncio.sleep(0.3)
    assert picker.value is None
    user.find(marker="task-end-time").clear().type("15:30")
    await asyncio.sleep(0.3)
    assert picker.value == "15:30"


async def test_without_effort_the_planned_end_is_editable_and_has_no_manual_check(
    user: User,
) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_see(marker="task-end-date")
    await user.should_not_see(marker="task-end-manual")
    await user.should_not_see(marker="task-end-computed")
    end = user.find(marker="task-end-date").elements.pop()
    assert "翌日" in end.props["hint"]


async def test_with_effort_the_planned_end_is_computed_and_read_only(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    await user.should_see(marker="task-end-manual")
    await user.should_see(marker="task-end-computed")
    await user.should_not_see(marker="task-end-date")
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-13 11:00"
    assert computed.props.get("readonly") is not None


async def test_the_computed_end_follows_the_start_and_effort(user: User) -> None:
    mount_dialog(None, [], daily_hours=8.0)
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-12 16:00"  # 金8h + 月7h
    user.find(marker="task-start-date").clear().type("2026-10-12")
    assert computed.value == "2026-10-13 16:00"  # 月8h(9-17時) + 火7h


async def test_the_computed_end_follows_the_holidays(user: User) -> None:
    mount_dialog(None, [], holidays={date(2026, 10, 12): "祝日"})
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-14 11:00"


async def test_manual_check_makes_the_planned_end_editable_and_keeps_the_typed_value(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-end-date").type("2026-10-20")
    user.find(marker="task-effort").clear().type("15")
    await user.should_not_see(marker="task-end-date")  # 工数ありで手指定なしなので隠れる
    user.find(marker="task-end-manual").click()
    await user.should_see(marker="task-end-date")
    assert user.find(marker="task-end-date").elements.pop().value == "2026-10-20"  # 値は保たれている
    await user.should_not_see(marker="task-end-computed")
    user.find(marker="task-save").click()
    assert saved[0].planned_end_manual is True
    assert saved[0].planned_end == datetime(2026, 10, 20, 18, 0)


async def test_unchecking_manual_returns_to_the_computed_value(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    user.find(marker="task-end-manual").click()
    user.find(marker="task-end-manual").click()
    await user.should_see(marker="task-end-computed")
    await user.should_not_see(marker="task-end-date")


async def test_clearing_the_effort_while_manual_is_on_makes_the_end_editable_and_not_manual(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    user.find(marker="task-end-manual").click()
    user.find(marker="task-effort").clear()
    await user.should_see(marker="task-end-date")
    await user.should_not_see(marker="task-end-manual")
    user.find(marker="task-save").click()
    assert saved[0].planned_end_manual is False


async def test_the_deadline_is_entered_with_a_date_and_an_optional_time(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-deadline-date").type("2026-10-30")
    await user.should_not_see(marker="task-deadline-time")
    user.find(marker="task-save").click()
    assert saved[0].deadline == datetime(2026, 10, 30, 18, 0)  # 時刻なしは終業時刻
    assert saved[0].planned_start is None


async def test_the_deadline_time_can_be_specified(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-deadline-date").type("2026-10-30")
    user.find(marker="task-deadline-use-time").click()
    user.find(marker="task-deadline-time").clear().type("12:00")
    user.find(marker="task-save").click()
    assert saved[0].deadline == datetime(2026, 10, 30, 12, 0)


async def test_an_existing_task_opens_with_its_values(user: User) -> None:
    task = Task(
        "旧",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 15, 30),
        planned_end_manual=True,
        deadline=datetime(2026, 10, 12, 18),
        effort_hours=8.0,
    )
    mount_dialog(task, [])
    await open_dialog(user)
    assert user.find(marker="task-end-manual").elements.pop().value is True
    assert user.find(marker="task-end-date").elements.pop().value == "2026-10-09"
    assert user.find(marker="task-end-time").elements.pop().value == "15:30"
    assert user.find(marker="task-deadline-date").elements.pop().value == "2026-10-12"


async def test_closing_asks_for_confirmation_after_the_manual_check_changes(user: User) -> None:
    task = Task("旧", planned_start=datetime(2026, 10, 5, 9), effort_hours=8.0)
    mount_dialog(task, [])
    await open_dialog(user)
    user.find(marker="task-end-manual").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_the_dialog_uses_the_planned_wording(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_see("開始予定")
    await user.should_see("完了予定")
    await user.should_see("締切")


async def test_the_end_hint_mentions_the_deadline(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    end = user.find(marker="task-end-date").elements.pop()
    assert "締切" in end.props["hint"]
    assert "翌日" in end.props["hint"]


async def test_the_computed_end_falls_back_to_the_deadline_when_it_cannot_compute(
    user: User,
) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-deadline-date").type("2026-10-30")
    user.find(marker="task-effort").clear().type("1000000000")
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-30 18:00"  # 締切(時刻なしは終業時刻)


async def test_changing_the_deadline_updates_the_computed_end(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("1000000000")
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-10 09:00"  # 締切なしは開始予定の翌日
    user.find(marker="task-deadline-date").type("2026-10-30")
    assert computed.value == "2026-10-30 18:00"


TANAKA = Member("田中", 1.2)
SUZUKI = Member("鈴木", 1.0)


async def test_the_assignee_is_chosen_from_the_members(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    select = user.find(marker="task-assignee").elements.pop()
    assert select.options == {"": "(なし)", "田中": "田中", "鈴木": "鈴木"}
    with user.client:
        select.set_value("田中")
    user.find(marker="task-save").click()
    assert saved[0].assignee == "田中"


async def test_without_an_assignee_the_allocation_is_disabled_and_saved_as_one(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    allocation = user.find(marker="task-allocation").elements.pop()
    assert allocation.enabled is False
    user.find(marker="task-save").click()
    assert saved[0].assignee is None and saved[0].allocation == 1.0


async def test_the_allocation_is_enabled_with_an_assignee_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    allocation = user.find(marker="task-allocation").elements.pop()
    assert allocation.enabled is True
    with user.client:
        allocation.set_value(60)
    user.find(marker="task-save").click()
    assert saved[0].allocation == pytest.approx(0.6)


async def test_returning_the_assignee_to_none_saves_an_allocation_of_one(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", assignee="田中", allocation=0.5)
    mount_dialog(task, saved, members=[TANAKA])
    await open_dialog(user)
    assert user.find(marker="task-allocation").elements.pop().value == 50
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("")
    user.find(marker="task-save").click()
    assert saved[0].assignee is None and saved[0].allocation == 1.0


async def test_the_conversion_is_shown_with_an_assignee_and_effort(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    assert conversion.text == ""
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
        user.find(marker="task-allocation").elements.pop().set_value(80)
    user.find(marker="task-effort").clear().type("15")
    # 15h / (1.2 * 0.8) / 6.5h = 2.40日
    assert conversion.text == "15h → 2.4日分(相対比率 120% × 割り当て 80%)"


async def test_the_conversion_disappears_without_effort_or_assignee(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    assert conversion.text != ""
    user.find(marker="task-effort").clear()
    assert conversion.text == ""
    user.find(marker="task-effort").type("15")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("")
    assert conversion.text == ""


async def test_the_computed_end_reflects_the_conversion(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.5)])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-12 12:30"


async def test_changing_the_assignee_asks_for_confirmation_on_close(user: User) -> None:
    mount_dialog(Task("旧"), [], members=[TANAKA])
    await open_dialog(user)
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_an_assignee_missing_from_the_members_is_kept_when_saving(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", assignee="不明", allocation=0.5)
    mount_dialog(task, saved, members=[TANAKA])
    await open_dialog(user)
    assert user.find(marker="task-assignee").elements.pop().value == "不明"
    assert user.find(marker="task-allocation").elements.pop().value == 50
    user.find(marker="task-save").click()
    assert saved[0].assignee == "不明"
    assert saved[0].allocation == pytest.approx(0.5)


def value_of(user: User, marker: str) -> object:
    return user.find(marker=marker).elements.pop().value


async def test_actual_inputs_save_an_actual(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-actual-start-time").type("09:15")
    user.find(marker="task-actual-end-date").type("2026-10-05")
    user.find(marker="task-actual-end-time").type("17:45")
    user.find(marker="task-save").click()
    assert saved[0].actuals == [Actual(datetime(2026, 10, 5, 9, 15), datetime(2026, 10, 5, 17, 45))]


async def test_existing_actual_is_shown_in_the_inputs(user: User) -> None:
    task = Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9, 15), None)])
    mount_dialog(task, [])
    await open_dialog(user)
    assert value_of(user, "task-actual-start-date") == "2026-10-05"
    assert value_of(user, "task-actual-start-time") == "09:15"
    assert value_of(user, "task-actual-end-date") == ""


async def test_a_date_without_a_time_is_an_error_and_not_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("日付と時刻を両方入れてください")


async def test_an_end_without_a_start_is_an_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-actual-end-date").type("2026-10-05")
    user.find(marker="task-actual-end-time").type("17:00")
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("実績の開始を入れてください")


async def test_clearing_the_actual_inputs_removes_the_actual(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9, 15), None)])
    mount_dialog(task, saved)
    await open_dialog(user)
    user.find(marker="task-actual-start-date").clear()
    user.find(marker="task-actual-start-time").clear()
    user.find(marker="task-save").click()
    assert saved[0].actuals == []


async def test_entering_a_start_suggests_running(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-actual-start-time").type("09:00")
    assert value_of(user, "task-status") == Status.RUNNING
    await user.should_see("実績に合わせて状態を変えました")


async def test_entering_an_end_suggests_done(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    for marker, text in (
        ("task-actual-start-date", "2026-10-05"),
        ("task-actual-start-time", "09:00"),
        ("task-actual-end-date", "2026-10-05"),
        ("task-actual-end-time", "17:00"),
    ):
        user.find(marker=marker).type(text)
    assert value_of(user, "task-status") == Status.DONE


async def test_no_suggestion_while_the_actual_is_empty(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    assert value_of(user, "task-status") == Status.NOT_STARTED
    await user.should_not_see("実績に合わせて状態を変えました")


async def test_a_manual_status_choice_stops_the_suggestions(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-status").elements.pop().set_value(Status.PAUSED)  # 手で選ぶ
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-actual-start-time").type("09:00")
    assert value_of(user, "task-status") == Status.PAUSED


async def test_changing_the_actual_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")  # 確認が出る


async def test_two_actuals_are_read_only_and_kept_on_save(user: User) -> None:
    saved: list[Task] = []
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    ]
    mount_dialog(Task("旧", actuals=list(kept)), saved)
    await open_dialog(user)
    await user.should_see(marker="task-actuals-readonly")
    await user.should_not_see(marker="task-actual-start-date")
    user.find(marker="task-save").click()
    assert saved[0].actuals == kept


async def test_a_partly_typed_date_does_not_suggest_a_status(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-actual-start-time").type("09:00")  # 時刻を先に入れる
    user.find(marker="task-actual-start-date").type("2026-1")  # 日付は入力の途中
    assert value_of(user, "task-status") == Status.NOT_STARTED
    await user.should_not_see("実績に合わせて状態を変えました")
    user.find(marker="task-actual-start-date").clear().type("2026-10-05")
    assert value_of(user, "task-status") == Status.RUNNING


def progress_input(user: User):  # noqa: ANN202
    return user.find(marker="task-actual-progress").elements.pop()


def start_actual(user: User) -> None:
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-actual-start-time").type("09:00")


async def test_progress_input_saves_into_the_actual(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    start_actual(user)
    progress_input(user).set_value(40)
    user.find(marker="task-save").click()
    assert saved[0].actuals[0].progress == 40


async def test_progress_zero_is_saved_as_zero(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    start_actual(user)
    progress_input(user).set_value(0)
    user.find(marker="task-save").click()
    assert saved[0].actuals[0].progress == 0


async def test_existing_progress_is_shown(user: User) -> None:
    task = Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9, 0), None, 70)])
    mount_dialog(task, [])
    await open_dialog(user)
    assert progress_input(user).value == 70


async def test_clearing_the_progress_saves_none(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9, 0), None, 70)])
    mount_dialog(task, saved)
    await open_dialog(user)
    progress_input(user).set_value(None)
    user.find(marker="task-save").click()
    assert saved[0].actuals[0].progress is None


async def test_progress_without_a_start_is_an_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    progress_input(user).set_value(40)
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("実績の開始を入れてください")


async def test_progress_out_of_range_is_an_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    start_actual(user)
    progress_input(user).set_value(120)
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("進捗度は0〜100の整数で入力してください")


async def test_hundred_percent_without_an_end_does_not_suggest_a_status(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    progress_input(user).set_value(100)
    start_actual(user)
    assert value_of(user, "task-status") == Status.NOT_STARTED


async def test_changing_the_progress_counts_as_a_change_when_closing(user: User) -> None:
    task = Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9, 0), None, 10)])
    mount_dialog(task, [])
    await open_dialog(user)
    progress_input(user).set_value(20)
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_two_actuals_keep_their_progress_and_hide_the_input(user: User) -> None:
    saved: list[Task] = []
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 30),
        Actual(datetime(2026, 10, 6, 9, 0), None, 60),
    ]
    mount_dialog(Task("旧", actuals=list(kept)), saved)
    await open_dialog(user)
    await user.should_not_see(marker="task-actual-progress")
    user.find(marker="task-save").click()
    assert saved[0].actuals == kept
