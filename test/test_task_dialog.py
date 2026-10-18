import asyncio
from collections.abc import Callable

import pytest
from datetime import date, datetime, time

from nicegui import events, ui
from nicegui.testing import User

from projectapp.browser import open_url as default_open_url
from projectapp.effortunits import EffortUnit
from projectapp.models import (
    Actual,
    ActualMode,
    Assignee,
    Category,
    Level,
    Member,
    Parameter,
    Priority,
    Status,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
)
from projectapp.task_dialog import open_task_dialog


def mount_dialog(
    task: Task | None,
    saved: list[Task],
    work_start: time = time(9, 0),
    deleted: list[str] | None = None,
    daily_hours: float = 6.5,
    holidays: dict[date, str] | None = None,
    members: list[Member] | None = None,
    actual_mode: ActualMode = ActualMode.SIMPLE,
    link_options: dict[str, str] | None = None,
    finish_of: Callable[[str], datetime | None] | None = None,
    url_templates: list[UrlTemplate] | None = None,
    opened: list[str] | None = None,
    parameters: list[Parameter] | None = None,
    categories: list[Category] | None = None,
    layout: str = "all",
    on_layout_change: Callable[[str], object] | None = None,
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
                actual_mode=actual_mode,
                link_options=link_options,
                finish_of=finish_of,
                url_templates=url_templates,
                parameters=parameters,
                categories=categories,
                layout=layout,
                on_layout_change=on_layout_change,
                open_url=(lambda url: opened.append(url)) if opened is not None else default_open_url,
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
    # 日付の入力は、側ごとの列の中の「編集用の入れ物」の、「日付と時刻の行」に入っている
    start_column = user.find(marker="task-start-date").elements.pop().parent_slot.parent.parent_slot.parent.parent_slot.parent
    end_column = user.find(marker="task-end-date").elements.pop().parent_slot.parent.parent_slot.parent.parent_slot.parent
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


def escape_listener_id(dialog: ui.dialog) -> str:
    """ダイアログの ESC を受けるリスナー。persistent の Quasar は escapeKey を送らないので、keydown で受ける。"""
    return next(i for i, listener in dialog._event_listeners.items() if listener.type == "keydown")


def press_escape(dialog: ui.dialog) -> None:
    dialog._handle_event({"listener_id": escape_listener_id(dialog), "args": {}})


async def test_the_dialog_is_persistent_and_listens_for_escape_as_a_keydown(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    dialog = dialog_of(user)
    assert dialog.props.get("persistent") is True
    # Quasar は、persistent のダイアログでは escapeKey を送らず、ゆらすだけ(実機で ESC が効かなかった)
    assert "escapeKey" not in {listener.type for listener in dialog._event_listeners.values()}
    assert "Escape" in (dialog._event_listeners[escape_listener_id(dialog)].js_handler or "")


async def test_escape_without_changes_closes_the_dialog(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    press_escape(dialog_of(user))
    assert dialog_of(user).value is False
    assert confirm_dialog_of(user).value is False


async def test_escape_with_changes_asks_first(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    press_escape(dialog_of(user))
    assert confirm_dialog_of(user).value is True
    assert dialog_of(user).value is True
    assert saved == []


def test_the_escape_handler_ignores_other_keys_and_composition():
    import json
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from projectapp.task_dialog import ESCAPE_KEYDOWN_JS

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので JS の動作を確かめない")
    script = (
        "let emitted = 0; const emit = () => { emitted += 1; };"
        f"const handler = {ESCAPE_KEYDOWN_JS};"
        "const run = (e) => { emitted = 0; handler({ ...e, stopPropagation() {} }); return emitted; };"
        "console.log(JSON.stringify({"
        " esc: run({ code: 'Escape', isComposing: false }),"
        " ime: run({ code: 'Escape', key: 'Process', keyCode: 229, isComposing: false }),"
        " composing: run({ code: 'Escape', isComposing: true }),"
        " other: run({ code: 'KeyA', isComposing: false }) }));"
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "escape.js"
        path.write_text(script)
        run = subprocess.run([node, str(path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {"esc": 1, "ime": 1, "composing": 0, "other": 0}  # 変換中の ESC は、変換の取り消し


def test_the_escape_handler_stops_the_keydown_so_quasar_does_not_close_the_confirm_on_keyup():
    """ESC の keydown で確認ダイアログを開くと、同じ ESC の keyup を Quasar が受けて、開いたばかりの確認ダイアログを閉じる
    (Quasar は window の keydown で ESC の印を付け、keyup で一番上のダイアログへ伝える)。印を付けさせないため、伝播を止める。"""
    import json
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from projectapp.task_dialog import ESCAPE_KEYDOWN_JS

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので JS の動作を確かめない")
    script = (
        "let emitted = 0; const emit = () => { emitted += 1; };"
        f"const handler = {ESCAPE_KEYDOWN_JS};"
        "const run = (init) => { emitted = 0; let stopped = 0;"
        " handler({ ...init, stopPropagation() { stopped += 1; } }); return { emitted, stopped }; };"
        "console.log(JSON.stringify({"
        " esc: run({ code: 'Escape', isComposing: false }),"
        " composing: run({ code: 'Escape', isComposing: true }),"
        " other: run({ code: 'KeyA', isComposing: false }) }));"
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "escape.js"
        path.write_text(script)
        run = subprocess.run([node, str(path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {
        "esc": {"emitted": 1, "stopped": 1},
        "composing": {"emitted": 0, "stopped": 0},  # 変換の取り消しの ESC は、Quasar に任せる
        "other": {"emitted": 0, "stopped": 0},
    }


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
    assert "翌日" in user.find(marker="task-end-hint").elements.pop().text


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
    await user.should_see(marker="task-end-computed")  # 手で指定でも、算出値を参考値として出す
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-13 11:00"
    assert computed.props["label"] == "算出値(参考)"
    assert "遅い" in user.find(marker="task-end-hint").elements.pop().text  # 10/20 は算出値の 10/13 より 7 日遅い
    assert "7 日" in user.find(marker="task-end-hint").elements.pop().text
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
    assert user.find(marker="task-end-computed").elements.pop().props["label"] == "算出値"


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
    hint = user.find(marker="task-end-hint").elements.pop().text
    assert "締切" in hint
    assert "翌日" in hint


async def test_the_end_hint_is_a_label_outside_the_input_row_so_it_cannot_overlap(user: User) -> None:
    """入力欄の hint は固定の高さで、時刻の入力が並んで欄が狭まり 2 行に折り返すと、下のチップに重なった(実機で見つけた)。"""
    mount_dialog(None, [])
    await open_dialog(user)
    end = user.find(marker="task-end-date").elements.pop()
    assert "hint" not in end.props
    row = end.parent_slot.parent  # 日付と時刻の行
    hint = user.find(marker="task-end-hint").elements.pop()
    assert hint.parent_slot.parent is row.parent_slot.parent  # 行の下に、同じ列の通常の流れで置く
    assert hint.parent_slot.parent is not row


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
    assert saved[0].assignees == [Assignee("田中", 1.0)]


async def test_without_an_assignee_the_allocation_is_hidden_and_nobody_is_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    await user.should_not_see(marker="task-allocation")
    user.find(marker="task-save").click()
    assert saved[0].assignees == []


async def test_the_allocation_shows_with_an_assignee_and_is_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    await user.should_see(marker="task-allocation")
    allocation = user.find(marker="task-allocation").elements.pop()
    with user.client:
        allocation.set_value(60)
    user.find(marker="task-save").click()
    assert saved[0].assignees[0].allocation == pytest.approx(0.6)


async def test_returning_the_assignee_to_none_saves_nobody(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", assignees=[Assignee("田中", 0.5)])
    mount_dialog(task, saved, members=[TANAKA])
    await open_dialog(user)
    assert user.find(marker="task-allocation").elements.pop().value == 50
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("")
    user.find(marker="task-save").click()
    assert saved[0].assignees == []


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
    assert conversion.text == "換算率 96%(田中 120%×80%)→ 15h は約 2.4日分"


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
    task = Task("旧", assignees=[Assignee("不明", 0.5)])
    mount_dialog(task, saved, members=[TANAKA])
    await open_dialog(user)
    assert user.find(marker="task-assignee").elements.pop().value == "不明"
    assert user.find(marker="task-allocation").elements.pop().value == 50
    user.find(marker="task-save").click()
    assert saved[0].assignees == [Assignee("不明", pytest.approx(0.5))]


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


def start_actual(user: User) -> None:
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-actual-start-time").type("09:00")


async def test_the_actual_has_no_progress_input(user: User) -> None:
    """進捗度の入力は、タスクの欄の 1 つだけ(実績の中には置かない)。"""
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_see(marker="task-progress")
    await user.should_not_see(marker="task-actual-progress")
    assert len(user.find("進捗度").elements) == 1


async def test_the_task_progress_is_editable_even_with_an_actual(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", progress=10, actuals=[Actual(datetime(2026, 10, 5, 9, 0), None)])
    mount_dialog(task, saved)
    await open_dialog(user)
    field = task_progress_input(user)
    assert field.value == 10 and field.enabled
    field.set_value(70)
    user.find(marker="task-save").click()
    assert saved[0].progress == 70 and saved[0].actuals == task.actuals


async def test_progress_can_be_entered_without_an_actual(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    task_progress_input(user).set_value(0)
    user.find(marker="task-save").click()
    assert saved[0].progress == 0 and saved[0].actuals == []


async def test_hundred_percent_without_an_end_does_not_suggest_a_status(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    task_progress_input(user).set_value(100)
    start_actual(user)
    assert value_of(user, "task-status") == Status.NOT_STARTED


async def test_two_actuals_are_kept_when_saved_in_the_simple_mode(user: User) -> None:
    saved: list[Task] = []
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    ]
    mount_dialog(Task("旧", actuals=list(kept)), saved)
    await open_dialog(user)
    user.find(marker="task-save").click()
    assert saved[0].actuals == kept


def task_progress_input(user: User):  # noqa: ANN202
    return user.find(marker="task-progress").elements.pop()


async def test_the_task_progress_is_entered_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    task_progress_input(user).set_value(40)
    user.find(marker="task-save").click()
    assert saved[0].progress == 40 and saved[0].actuals == []


async def test_the_existing_task_progress_is_shown_and_can_be_cleared(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", progress=70), saved)
    await open_dialog(user)
    assert task_progress_input(user).value == 70
    task_progress_input(user).set_value(None)
    user.find(marker="task-save").click()
    assert saved[0].progress is None


async def test_the_task_progress_is_hidden_for_a_checkpoint_and_cleared_on_save(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", progress=40, deadline=datetime(2026, 10, 9, 17, 0)), saved)
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-progress")
    user.find(marker="task-save").click()
    assert saved[0].kind is TaskKind.CHECKPOINT and saved[0].progress is None


async def test_the_task_progress_stays_in_the_schedule_layout(user: User) -> None:
    mount_dialog(Task("旧", progress=40), [], layout="schedule")
    await open_dialog(user)
    await user.should_see(marker="task-progress")


async def test_changing_the_task_progress_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(Task("旧"), [])
    await open_dialog(user)
    task_progress_input(user).set_value(40)
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_an_out_of_range_task_progress_is_an_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧"), saved)
    await open_dialog(user)
    task_progress_input(user).set_value(101)
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("進捗度")


INTERVALS = ActualMode.INTERVALS


def interval_inputs(user: User, n: int, start: str, end: str = "") -> None:
    day, clock = start.split(" ")
    user.find(marker=f"task-interval-{n}-start-date").clear().type(day)
    user.find(marker=f"task-interval-{n}-start-time").clear().type(clock)
    if end:
        day, clock = end.split(" ")
        user.find(marker=f"task-interval-{n}-end-date").clear().type(day)
        user.find(marker=f"task-interval-{n}-end-time").clear().type(clock)


async def test_interval_mode_shows_no_rows_for_a_task_without_actuals(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    await user.should_see(marker="task-interval-add")
    await user.should_not_see(marker="task-interval-0-start-date")
    await user.should_not_see(marker="task-actual-start-date")


async def test_interval_rows_are_added_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 1, "2026-10-06 09:00")
    user.find(marker="task-save").click()
    assert saved[0].actuals == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9), None),
    ]


async def test_two_actuals_are_editable_in_interval_mode(user: User) -> None:
    saved: list[Task] = []
    two = [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9), None),
    ]
    mount_dialog(Task("旧", actuals=list(two)), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    await user.should_not_see(marker="task-actuals-readonly")
    assert value_of(user, "task-interval-0-start-date") == "2026-10-05"
    assert value_of(user, "task-interval-1-start-time") == "09:00"
    await user.should_not_see(marker="task-interval-1-progress")
    user.find(marker="task-save").click()
    assert saved[0].actuals == two


async def test_a_row_can_be_removed(user: User) -> None:
    saved: list[Task] = []
    two = [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
    ]
    mount_dialog(Task("旧", actuals=list(two)), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-0-remove").click()
    await user.should_not_see(marker="task-interval-0-start-date")
    user.find(marker="task-save").click()
    assert saved[0].actuals == two[1:]


async def test_empty_rows_are_ignored_on_save(user: User) -> None:
    saved: list[Task] = []
    one = Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12))])
    mount_dialog(one, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-0-remove").click()
    user.find(marker="task-interval-add").click()  # 空の行だけを残す
    user.find(marker="task-save").click()
    assert saved[0].actuals == []


async def test_overlapping_rows_show_the_error_and_keep_the_dialog(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 1, "2026-10-05 11:00", "2026-10-05 13:00")
    user.find(marker="task-save").click()
    await user.should_see("区間 2: 前の区間と重なっています")
    assert saved == []


async def test_the_error_row_number_follows_the_position_after_a_removal(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    for _ in range(3):
        user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    interval_inputs(user, 1, "2026-10-06 09:00", "2026-10-06 12:00")
    interval_inputs(user, 2, "2026-10-06 11:00", "2026-10-06 13:00")
    user.find(marker="task-interval-0-remove").click()  # 残りは 2 行。重なりは 2 行目
    user.find(marker="task-save").click()
    await user.should_see("区間 2: 前の区間と重なっています")


async def test_a_half_typed_row_names_its_number(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    user.find(marker="task-interval-0-start-date").type("2026-10-05")  # 時刻がない
    user.find(marker="task-save").click()
    await user.should_see("区間 1: 日付と時刻を両方入れてください")


async def test_an_open_interval_in_the_middle_of_a_hand_edited_file_blocks_saving(
    user: User,
) -> None:
    saved: list[Task] = []
    broken = [
        Actual(datetime(2026, 10, 5, 9), None),
        Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
    ]
    mount_dialog(Task("旧", actuals=broken), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-save").click()
    await user.should_see("区間 1: 終了のない区間は最後の1つだけにしてください")
    assert saved == []


async def test_interval_mode_suggests_paused_when_the_last_interval_ended(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00")
    assert value_of(user, "task-status") == Status.RUNNING
    user.find(marker="task-interval-0-end-date").type("2026-10-05")
    user.find(marker="task-interval-0-end-time").type("12:00")
    assert value_of(user, "task-status") == Status.PAUSED
    task_progress_input(user).set_value(100)
    assert value_of(user, "task-status") == Status.DONE


async def test_interval_mode_suggestion_follows_the_last_row(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    assert value_of(user, "task-status") == Status.PAUSED
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 1, "2026-10-06 09:00")
    assert value_of(user, "task-status") == Status.RUNNING


async def test_closing_without_touching_the_rows_does_not_ask(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False
    assert confirm_dialog_of(user).value is False


async def test_adding_a_row_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-add").click()
    user.find(marker="task-cancel").click()
    assert confirm_dialog_of(user).value is True


async def test_simple_mode_keeps_two_actuals_read_only_with_the_mode_argument(user: User) -> None:
    kept = [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9), None),
    ]
    mount_dialog(Task("旧", actuals=list(kept)), [], actual_mode=ActualMode.SIMPLE)
    await open_dialog(user)
    await user.should_see(marker="task-actuals-readonly")
    await user.should_not_see(marker="task-interval-add")


DEV = Category("開発", prj_code="PRJ-1", id="aaaaaaaa")
OPS = Category("保守", id="bbbbbbbb")


BIG = Category("あ" * 20, "業務", None, "blue", "PRJ-9", "cccccccc")  # 名前が長いカテゴリ


async def test_category_options_show_the_kind_and_the_prj_code(user: User) -> None:
    mount_dialog(None, [], categories=[DEV, OPS, Category("ドキュメント", kind="社内", id="dddddddd"), BIG])
    await open_dialog(user)
    select = user.find(marker="task-category").elements.pop()
    assert list(select.options.values()) == [
        "未定",
        "開発(PRJ-1)",  # DEV は PRJコードだけ
        "保守",  # OPS は名前だけ
        "ドキュメント(社内)",
        "あ" * 12 + "…(業務・PRJ-9)",  # 長い名前だけを省略し、種別と PRJコードは残す
    ]
    assert list(select.options.keys()) == ["", "aaaaaaaa", "bbbbbbbb", "dddddddd", "cccccccc"]  # 値は id のまま


async def test_an_abbreviated_option_shows_its_full_text_on_hover(user: User) -> None:
    mount_dialog(None, [], categories=[DEV, BIG])
    await open_dialog(user)
    select = user.find(marker="task-category").elements.pop()
    full = "あ" * 20 + "(業務・PRJ-9)"
    for slot in ("option", "selected-item"):
        template = select.slots[slot].template
        assert ":title=" in template and "props.opt.value" in template  # NiceGUI の value は番号。番号で全文を引く
        assert full in template  # 全文が、マウスオーバーの文字として入っている
    option = select.slots["option"].template
    assert '&quot;&quot;' in option  # 省略しない選択肢(未定・開発)の全文は空で、マウスオーバーに何も出さない


async def test_category_is_saved_by_id_even_when_the_label_is_abbreviated(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, categories=[DEV, BIG])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-category").elements.pop().set_value("cccccccc")
    user.find(marker="task-save").click()
    assert saved[0].category_id == "cccccccc"


async def test_category_select_lists_undecided_first_and_defaults_to_it(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, categories=[DEV, OPS])
    await open_dialog(user)
    select = user.find(marker="task-category").elements.pop()
    assert select.value == ""
    assert list(select.options.values()) == ["未定", "開発(PRJ-1)", "保守"]
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    assert saved[0].category_id is None


async def test_category_is_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, categories=[DEV, OPS])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-category").elements.pop().set_value("bbbbbbbb")
    user.find(marker="task-save").click()
    assert saved[0].category_id == "bbbbbbbb"


async def test_existing_category_is_shown_and_kept(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", category_id="aaaaaaaa"), saved, categories=[DEV, OPS])
    await open_dialog(user)
    assert value_of(user, "task-category") == "aaaaaaaa"
    user.find(marker="task-save").click()
    assert saved[0].category_id == "aaaaaaaa"


async def test_a_category_that_no_longer_exists_is_shown_as_undecided(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", category_id="zzzzzzzz"), saved, categories=[DEV])
    await open_dialog(user)
    assert value_of(user, "task-category") == ""
    user.find(marker="task-save").click()
    assert saved[0].category_id is None


async def test_the_category_can_be_set_back_to_undecided(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", category_id="aaaaaaaa"), saved, categories=[DEV])
    await open_dialog(user)
    user.find(marker="task-category").elements.pop().set_value("")
    user.find(marker="task-save").click()
    assert saved[0].category_id is None


async def test_changing_the_category_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(None, [], categories=[DEV])
    await open_dialog(user)
    user.find(marker="task-category").elements.pop().set_value("aaaaaaaa")
    user.find(marker="task-cancel").click()
    assert confirm_dialog_of(user).value is True


async def test_a_checkpoint_keeps_its_category(user: User) -> None:
    saved: list[Task] = []
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), category_id="aaaaaaaa")
    mount_dialog(checkpoint, saved, categories=[DEV])
    await open_dialog(user)
    user.find(marker="task-save").click()
    assert saved[0].category_id == "aaaaaaaa"


async def test_predecessors_are_saved_from_the_select(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, link_options={"aaaaaaaa": "設計", "bbbbbbbb": "開発 / 実装"})
    await open_dialog(user)
    user.find(marker="task-name").type("テスト")
    select = user.find(marker="task-predecessors").elements.pop()
    select.set_value(["aaaaaaaa"])
    user.find(marker="task-save").click()
    assert saved[0].predecessors == ["aaaaaaaa"]


async def test_the_select_lists_only_the_given_options(user: User) -> None:
    mount_dialog(None, [], link_options={"aaaaaaaa": "設計"})
    await open_dialog(user)
    select = user.find(marker="task-predecessors").elements.pop()
    assert select.options == {"aaaaaaaa": "設計"}


async def test_the_hint_shows_only_when_pushed(user: User) -> None:
    task = Task(
        "後続",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 5, 9, 0),
        predecessors=["aaaaaaaa"],
    )
    mount_dialog(
        task,
        [],
        link_options={"aaaaaaaa": "設計"},
        finish_of=lambda pid: datetime(2026, 10, 12, 9, 0),
    )
    await open_dialog(user)
    hint = user.find(marker="task-predecessors-hint").elements.pop()
    assert hint.visible
    assert hint.text == "先行の完了により、実際の開始は 10/12 09:00 です"


async def test_the_hint_is_hidden_without_a_push(user: User) -> None:
    task = Task("後続", planned_start=datetime(2026, 10, 12, 9, 0), predecessors=["aaaaaaaa"])
    mount_dialog(
        task,
        [],
        link_options={"aaaaaaaa": "設計"},
        finish_of=lambda pid: datetime(2026, 10, 5, 9, 0),
    )
    await open_dialog(user)
    await user.should_not_see(marker="task-predecessors-hint")  # 非表示の要素は、User から見えない


async def test_changing_the_predecessors_counts_as_an_edit(user: User) -> None:
    task = Task("後続", id="bbbbbbbb")
    mount_dialog(task, [], link_options={"aaaaaaaa": "設計"})
    await open_dialog(user)
    user.find(marker="task-predecessors").elements.pop().set_value(["aaaaaaaa"])
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")  # 確認ダイアログが出る


async def set_kind(user: User, kind: TaskKind) -> None:
    user.find(marker="task-kind").elements.pop().set_value(kind)
    await asyncio.sleep(0.1)


async def test_the_kind_toggle_hides_and_shows_the_normal_fields(user: User) -> None:
    mount_dialog(None, [], members=[Member("佐藤")])
    await open_dialog(user)
    await user.should_see(marker="task-start-date")
    await set_kind(user, TaskKind.CHECKPOINT)
    for marker in (
        "task-start-date",
        "task-end-date",
        "task-effort",
        "task-assignee",
        "task-progress",
    ):
        await user.should_not_see(marker=marker)
    for marker in (
        "task-name",
        "task-deadline-date",
        "task-predecessors",
        "task-status",
        "task-category",
    ):
        await user.should_see(marker=marker)
    await set_kind(user, TaskKind.NORMAL)
    await user.should_see(marker="task-start-date")
    await user.should_see(marker="task-effort")


async def test_a_checkpoint_offers_only_two_statuses(user: User) -> None:
    task = Task("c", status=Status.RUNNING)
    mount_dialog(task, [])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    status = user.find(marker="task-status").elements.pop()
    assert list(status.options.values()) == ["未着手", "終了"]
    assert status.value == Status.NOT_STARTED  # 実行中は選べないので、未着手にする
    await set_kind(user, TaskKind.NORMAL)
    assert len(user.find(marker="task-status").elements.pop().options) == 4


async def test_saving_a_checkpoint_clears_the_normal_fields(user: User) -> None:
    saved: list[Task] = []
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 9, 0),
        effort_hours=5.0,
        assignees=[Assignee("佐藤")],
    )
    mount_dialog(task, saved, members=[Member("佐藤")])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-deadline-date").type("2026-10-12")
    user.find(marker="task-save").click()
    result = saved[0]
    assert result.kind is TaskKind.CHECKPOINT
    assert result.deadline == datetime(2026, 10, 12, 18, 0)  # 時刻を指定しない締切の、補う時刻
    assert (result.planned_start, result.effort_hours, result.assignees) == (None, 0.0, [])


async def test_a_checkpoint_without_a_deadline_shows_the_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("レビュー")
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-save").click()
    await user.should_see("チェックポイントには締切を入れてください")
    assert saved == []


async def test_the_hint_warns_that_normal_fields_will_be_cleared(user: User) -> None:
    task = Task("設計", planned_start=datetime(2026, 10, 5, 9, 0), effort_hours=5.0)
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-kind-hint")
    await set_kind(user, TaskKind.CHECKPOINT)
    hint = user.find(marker="task-kind-hint").elements.pop()
    assert hint.text == "保存すると、開始予定・工数・担当・実績は消えます"
    await set_kind(user, TaskKind.NORMAL)
    await user.should_not_see(marker="task-kind-hint")


async def test_a_new_checkpoint_has_no_hint(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-kind-hint")


async def test_changing_the_kind_counts_as_an_edit(user: User) -> None:
    mount_dialog(Task("設計"), [])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_a_checkpoint_never_shows_the_pushed_start_hint(user: User) -> None:
    """チェックポイントは押し出されないので、「実際の開始」のヒントは出さない。トグルでも更新される。"""
    task = Task("後続", planned_start=datetime(2026, 10, 5, 9, 0), predecessors=["aaaaaaaa"])
    mount_dialog(
        task,
        [],
        link_options={"aaaaaaaa": "設計"},
        finish_of=lambda pid: datetime(2026, 10, 12, 9, 0),
    )
    await open_dialog(user)
    await user.should_see(marker="task-predecessors-hint")  # 通常: 押し出される
    await set_kind(user, TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-predecessors-hint")
    await set_kind(user, TaskKind.NORMAL)
    await user.should_see(marker="task-predecessors-hint")


async def test_selecting_a_predecessor_of_a_new_checkpoint_shows_no_hint(user: User) -> None:
    mount_dialog(None, [], link_options={"aaaaaaaa": "設計"}, finish_of=lambda pid: datetime(2026, 10, 5, 15, 30))
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-predecessors").elements.pop().set_value(["aaaaaaaa"])
    await asyncio.sleep(0.1)
    await user.should_not_see(marker="task-predecessors-hint")


TICKET = UrlTemplate("チケット", "https://example.com/{ID}")


def element(user: User, marker: str) -> ui.element:
    return user.find(marker=marker).elements.pop()


async def test_a_link_by_template_is_saved_with_the_id(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, url_templates=[TICKET])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-1-title").type("課題")
    element(user, "task-url-1-template").set_value("チケット")
    user.find(marker="task-url-1-value").type("231")
    user.find(marker="task-save").click()
    assert saved[0].urls == [TaskUrl("課題", "チケット", {"ID": "231"})]


async def test_a_plain_url_link_is_the_default(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, url_templates=[TICKET])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-url-add").click()
    assert element(user, "task-url-1-template").value == ""
    user.find(marker="task-url-1-value").type("https://example.com/a")
    user.find(marker="task-save").click()
    assert saved[0].urls == [TaskUrl("", None, {"URL": "https://example.com/a"})]


async def test_the_value_label_and_text_follow_the_template_choice(user: User) -> None:
    mount_dialog(None, [], url_templates=[TICKET])
    await open_dialog(user)
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-1-value").type("https://example.com/a")
    assert element(user, "task-url-1-value").props["label"] == "URL"
    element(user, "task-url-1-template").set_value("チケット")
    assert element(user, "task-url-1-value").props["label"] == "ID"
    assert element(user, "task-url-1-value").value == ""  # なし → あり では、値を空にする
    user.find(marker="task-url-1-value").type("231")
    element(user, "task-url-1-template").set_value("")
    assert element(user, "task-url-1-value").props["label"] == "URL"
    assert element(user, "task-url-1-value").value == ""


async def test_an_incomplete_link_keeps_the_dialog_open_with_a_row_number(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, url_templates=[TICKET])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-url-add").click()
    element(user, "task-url-1-template").set_value("チケット")
    user.find(marker="task-save").click()
    await user.should_see("リンク1行目")
    assert saved == []


async def test_empty_rows_are_ignored_and_rows_can_be_removed(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-2-value").type("https://example.com/b")
    user.find(marker="task-url-1-remove").click()
    user.find(marker="task-url-add").click()  # 空の行
    user.find(marker="task-save").click()
    assert saved[0].urls == [TaskUrl("", None, {"URL": "https://example.com/b"})]


async def test_existing_links_are_shown_and_kept(user: User) -> None:
    saved: list[Task] = []
    task = Task("設計", urls=[TaskUrl("課題", "チケット", {"ID": "231"})])
    mount_dialog(task, saved, url_templates=[TICKET])
    await open_dialog(user)
    assert element(user, "task-url-1-title").value == "課題"
    assert element(user, "task-url-1-template").value == "チケット"
    assert element(user, "task-url-1-value").value == "231"
    user.find(marker="task-save").click()
    assert saved[0].urls == task.urls


async def test_the_open_button_opens_the_resolved_url(user: User) -> None:
    opened: list[str] = []
    task = Task("設計", urls=[TaskUrl("", "チケット", {"ID": "a b"})])
    mount_dialog(task, [], url_templates=[TICKET], opened=opened)
    await open_dialog(user)
    user.find(marker="task-url-1-open").click()
    assert opened == ["https://example.com/a%20b"]


async def test_the_open_button_refuses_an_unusable_row(user: User) -> None:
    opened: list[str] = []
    mount_dialog(None, [], opened=opened)
    await open_dialog(user)
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-1-value").type("javascript:alert(1)")
    user.find(marker="task-url-1-open").click()
    assert opened == []
    assert user.notify.contains("http")


async def test_a_failure_to_open_is_notified(user: User) -> None:
    def fail(url: str) -> None:
        raise OSError("ブラウザを開けませんでした")

    task = Task("設計", urls=[TaskUrl("", None, {"URL": "https://example.com/a"})])

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(task, lambda t: None, open_url=fail))

    await open_dialog(user)
    user.find(marker="task-url-1-open").click()
    assert user.notify.contains("ブラウザを開けませんでした")


async def test_an_untouched_link_section_does_not_ask_when_closing(user: User) -> None:
    task = Task("設計", urls=[TaskUrl("", None, {"URL": "https://example.com/a"})])
    mount_dialog(task, [])
    await open_dialog(user)
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False
    assert confirm_dialog_of(user).value is False


async def test_a_link_change_counts_as_an_edit_when_closing(user: User) -> None:
    mount_dialog(Task("設計"), [])
    await open_dialog(user)
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-1-value").type("https://example.com/a")
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is True
    assert confirm_dialog_of(user).value is True


async def test_a_checkpoint_can_hold_links(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("節目")
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-deadline-date").type("2026-10-20")
    user.find(marker="task-url-add").click()
    user.find(marker="task-url-1-value").type("https://example.com/doc")
    user.find(marker="task-save").click()
    assert saved[0].kind is TaskKind.CHECKPOINT
    assert saved[0].urls == [TaskUrl("", None, {"URL": "https://example.com/doc"})]


SATO = Member("佐藤", 1.0)


async def test_a_second_assignee_row_can_be_added_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
        user.find(marker="task-allocation-2").elements.pop().set_value(50)
    user.find(marker="task-save").click()
    assert saved[0].assignees == [Assignee("田中", 1.0), Assignee("鈴木", pytest.approx(0.5))]


async def test_a_member_chosen_in_one_row_is_not_offered_in_the_others(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA, SUZUKI, SATO])
    await open_dialog(user)
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    second = user.find(marker="task-assignee-2").elements.pop()
    assert second.options == {"": "(なし)", "鈴木": "鈴木", "佐藤": "佐藤"}
    first = user.find(marker="task-assignee").elements.pop()
    assert first.options == {"": "(なし)", "田中": "田中", "鈴木": "鈴木", "佐藤": "佐藤"}


async def test_removing_a_row_returns_the_member_to_the_others(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
    user.find(marker="task-assignee-remove-2").click()
    user.find(marker="task-save").click()
    assert saved[0].assignees == []


async def test_existing_assignees_open_as_rows(user: User) -> None:
    task = Task("旧", assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.25)])
    mount_dialog(task, [], members=[TANAKA, SUZUKI])
    await open_dialog(user)
    assert user.find(marker="task-assignee").elements.pop().value == "田中"
    assert user.find(marker="task-allocation").elements.pop().value == 50
    assert user.find(marker="task-assignee-2").elements.pop().value == "鈴木"
    assert user.find(marker="task-allocation-2").elements.pop().value == 25


async def test_the_conversion_adds_up_every_assignee(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
        user.find(marker="task-allocation-2").elements.pop().set_value(50)
    user.find(marker="task-effort").clear().type("19.5")
    # 換算率 1.0×100% + 1.0×50% = 150% → 19.5h / 1.5 / 6.5h = 2.0日
    assert conversion.text == "換算率 150%(田中 100%×100% + 鈴木 100%×50%)→ 19.5h は約 2.0日分"


async def test_two_assignees_shorten_the_computed_end(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
    user.find(marker="task-effort").clear().type("13")
    # 13h / 2.0 = 6.5h → 金のうちに終わる
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-09 15:30"


async def test_adding_a_row_counts_as_a_change_on_close(user: User) -> None:
    mount_dialog(Task("旧"), [], members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-assignee-add").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_the_assignee_rows_are_hidden_for_a_checkpoint(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    await user.should_see(marker="task-assignee-add")
    with user.client:
        user.find(marker="task-kind").elements.pop().set_value(TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-assignee-add")


async def test_the_conversion_uses_the_effective_ratio(user: User) -> None:
    members = [Member("田中", 1.0, {"経験": "上級"})]
    mount_dialog(None, [], members=members, parameters=[Parameter("経験", [Level("上級", 0.2)])])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    # 実効比率 120%。15h / 1.2 / 6.5h = 1.92日
    assert conversion.text == "換算率 120%(田中 120%×100%)→ 15h は約 1.9日分"


async def test_the_computed_end_follows_the_parameters_in_the_dialog(user: User) -> None:
    members = [Member("田中", 1.0, {"経験": "上級"})]
    mount_dialog(None, [], members=members, parameters=[Parameter("経験", [Level("上級", 0.5)])])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-12 12:30"


async def test_the_name_input_is_cut_to_the_limit_in_characters(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    name = user.find(marker="task-name").elements.pop()
    assert name._props.get("maxlength") is None  # ブラウザの maxlength は UTF-16 単位で、文字数とずれる
    name.set_value("あ" * 60)
    assert name.value == "あ" * 50
    name.set_value("😀" * 50)  # 絵文字は 1 文字と数える(UTF-16 では 2 単位)
    assert name.value == "😀" * 50
    name.set_value("a\nb" + "c" * 60)  # 改行は空白に替えてから切る
    assert name.value == "a b" + "c" * 47
    user.find(marker="task-save").click()
    assert len(saved[0].name) == 50


async def test_the_name_input_is_a_full_width_growing_textarea(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    name = user.find(marker="task-name").elements.pop()
    assert isinstance(name, ui.textarea)  # 長い名前は折り返す
    assert "w-full" in name.classes  # 他の入力欄と同じ幅
    assert name._props.get("autogrow") is True
    assert str(name._props.get("rows")) == "1"  # 短いうちは 1 行の高さ


async def test_enter_in_the_name_does_not_add_a_line_break(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    name = user.find(marker="task-name").elements.pop()
    assert any(l.type == "keydown.enter.prevent" for l in name._event_listeners.values())


async def test_a_pasted_line_break_in_the_name_becomes_a_space(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    name = user.find(marker="task-name").elements.pop()
    name.set_value("a\nb\tc")
    assert name.value == "a b c"
    user.find(marker="task-save").click()
    assert saved[0].name == "a b c"


TODAY = date(2026, 10, 12)  # 月曜


def blur(user: User, marker: str) -> None:
    """入力欄を離れたときの処理(blur)を呼ぶ。User のシミュレーションには、フォーカスの移動がないため。"""
    element = user.find(marker=marker).elements.pop()
    for listener in element._event_listeners.values():
        if listener.type == "blur":
            events.handle_event(
                listener.handler, events.GenericEventArguments(sender=element, client=element.client, args={})
            )


@pytest.fixture
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr("projectapp.task_dialog.today", lambda: TODAY)
    return TODAY


async def test_blur_completes_short_dates_and_times(user: User, fixed_today: date) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-start-date").type("10/15")
    blur(user, "task-start-date")
    assert user.find(marker="task-start-date").elements.pop().value == "2026-10-15"
    user.find(marker="task-start-time").clear().type("930")
    blur(user, "task-start-time")
    assert user.find(marker="task-start-time").elements.pop().value == "09:30"


async def test_planned_dates_roll_to_next_year_but_actual_dates_do_not(user: User, fixed_today: date) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-deadline-date").type("10/01")
    blur(user, "task-deadline-date")
    assert user.find(marker="task-deadline-date").elements.pop().value == "2027-10-01"
    user.find(marker="task-actual-start-date").type("10/01")
    blur(user, "task-actual-start-date")
    assert user.find(marker="task-actual-start-date").elements.pop().value == "2026-10-01"


async def test_blur_leaves_unreadable_text_as_typed(user: User, fixed_today: date) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-1")  # 入力の途中
    blur(user, "task-start-date")
    assert user.find(marker="task-start-date").elements.pop().value == "2026-1"


async def test_shortcut_chips_fill_the_date(user: User, fixed_today: date) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-shortcut-tomorrow").click()
    user.find(marker="task-deadline-shortcut-next-monday").click()
    assert user.find(marker="task-start-date").elements.pop().value == "2026-10-13"
    assert user.find(marker="task-deadline-date").elements.pop().value == "2026-10-19"
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 13, 9, 0)
    assert saved[0].deadline == datetime(2026, 10, 19, 18, 0)


async def test_the_end_chips_show_only_while_the_end_is_editable(user: User, fixed_today: date) -> None:
    mount_dialog(Task("a", effort_hours=8.0), [])
    await open_dialog(user)
    await user.should_not_see(marker="task-end-shortcut-today")  # 工数があり、算出値のとき
    user.find(marker="task-end-manual").click()
    await user.should_see(marker="task-end-shortcut-today")


async def test_date_and_time_share_a_row_and_the_dialog_is_wider(user: User) -> None:
    mount_dialog(Task("a", planned_start=datetime(2026, 10, 5, 10, 0)), [])
    await open_dialog(user)
    day = user.find(marker="task-start-date").elements.pop()
    clock = user.find(marker="task-start-time").elements.pop()
    assert day.parent_slot.parent is clock.parent_slot.parent  # 日付と時刻は、同じ行の直下
    assert isinstance(day.parent_slot.parent, ui.row)
    card = next(a for a in day.ancestors() if isinstance(a, ui.card))
    assert "w-[44rem]" in card.classes



def set_unit(user: User, unit: EffortUnit) -> None:
    user.find(marker="task-effort-unit").elements.pop().set_value(unit)


async def test_the_effort_unit_converts_to_hours_on_save(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort").type("2")
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 13.0  # 2日 × 6.5h


@pytest.mark.parametrize(
    "unit, typed, hours",
    [(EffortUnit.HOURS, "8", 8.0), (EffortUnit.WEEKS, "3", 97.5), (EffortUnit.MONTHS, "1", 130.0)],
)
async def test_each_unit_converts(user: User, unit: EffortUnit, typed: str, hours: float) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, unit)
    user.find(marker="task-effort").type(typed)
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == hours


async def test_the_unit_follows_the_daily_hours(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, daily_hours=8.0)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort").type("2")
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 16.0


async def test_switching_the_unit_does_not_change_the_hours(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-effort").type("10")
    set_unit(user, EffortUnit.DAYS)
    assert user.find(marker="task-effort").elements.pop().value == 1.54  # 表示だけ丸める
    set_unit(user, EffortUnit.HOURS)
    assert user.find(marker="task-effort").elements.pop().value == 10
    set_unit(user, EffortUnit.DAYS)  # 日のまま保存しても、時間は 10h
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 10.0


async def test_a_preset_chip_sets_the_hours_in_the_current_unit(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort-preset-4").click()
    assert user.find(marker="task-effort").elements.pop().value == 0.62  # 4h = 0.615日(表示)
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 4.0


async def test_the_reference_shows_the_month_comparison(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    reference = user.find(marker="task-effort-reference").elements.pop()
    assert reference.text == ""
    set_unit(user, EffortUnit.MONTHS)
    assert reference.text == "1月 = 20日 × 6.5h = 130h / 参考: 標準 8h × 20日 = 160h"
    set_unit(user, EffortUnit.DAYS)
    assert reference.text == "1日 = 6.5h(稼働可能時間)"


async def test_an_existing_effort_opens_in_hours(user: User) -> None:
    mount_dialog(Task("a", effort_hours=12.0), [])
    await open_dialog(user)
    assert user.find(marker="task-effort").elements.pop().value == 12.0
    assert user.find(marker="task-effort-unit").elements.pop().value is EffortUnit.HOURS


async def test_hours_with_three_decimals_are_rejected_with_a_message(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-effort").type("1.234")
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("工数は小数点以下2桁")


async def test_an_existing_three_decimal_effort_can_be_saved_untouched(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("a", effort_hours=1.234), saved)
    await open_dialog(user)
    user.find(marker="task-name").clear().type("改名")
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 1.234


async def test_the_effort_change_updates_the_computed_end_and_the_conversion(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-05")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort").type("2")
    assert user.find(marker="task-end-computed").elements.pop().value != ""  # 13h から算出


async def test_the_allocation_hides_again_when_cleared_and_keeps_its_value(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    select = user.find(marker="task-assignee").elements.pop()
    with user.client:
        select.set_value("田中")
        user.find(marker="task-allocation").elements.pop().set_value(50)
        select.set_value("")  # (なし)
    await user.should_not_see(marker="task-allocation")
    with user.client:
        select.set_value("田中")
    assert user.find(marker="task-allocation").elements.pop().value == 50  # 隠しても値は残る


def rich_task() -> Task:
    return Task(
        "a",
        category_id="c1",
        assignees=[Assignee("田中", 0.5)],
        predecessors=["p1"],
        priority=Priority.HIGH,
        color="#123456",
        urls=[TaskUrl("仕様", None, {"URL": "https://example.com/spec"})],
    )


HIDDEN_IN_SCHEDULE = [
    "task-category",
    "task-assignee",
    "task-predecessors",
    "priority-HIGH",
    "task-url-add",
    "task-color",
]
SHOWN_IN_SCHEDULE = [
    "task-name",
    "task-start-date",
    "task-end-date",
    "task-deadline-date",
    "task-effort",
    "task-actual-start-date",
    "task-status",
    "task-kind",
]


async def test_the_dialog_opens_in_the_layout_it_is_given(user: User) -> None:
    mount_dialog(rich_task(), [], layout="schedule", link_options={"p1": "先行"}, categories=[Category("開発", id="c1")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    for marker in SHOWN_IN_SCHEDULE:
        await user.should_see(marker=marker)
    for marker in HIDDEN_IN_SCHEDULE:
        await user.should_not_see(marker=marker)


async def test_the_toggle_switches_the_layout_and_reports_it(user: User) -> None:
    changed: list[str] = []
    mount_dialog(rich_task(), [], on_layout_change=changed.append, link_options={"p1": "先行"}, categories=[Category("開発", id="c1")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    for marker in HIDDEN_IN_SCHEDULE:
        await user.should_see(marker=marker)  # 既定は「すべて」
    user.find(marker="task-layout").elements.pop().set_value("schedule")
    for marker in HIDDEN_IN_SCHEDULE:
        await user.should_not_see(marker=marker)
    assert changed == ["schedule"]
    user.find(marker="task-layout").elements.pop().set_value("all")
    await user.should_see(marker="task-category")
    assert changed == ["schedule", "all"]


async def test_hidden_fields_keep_their_values_through_a_schedule_save(user: User) -> None:
    saved: list[Task] = []
    original = rich_task()
    mount_dialog(original, saved, layout="schedule", link_options={"p1": "先行"}, categories=[Category("開発", id="c1")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-name").clear().type("改名")
    user.find(marker="task-save").click()
    result = saved[0]
    assert result.name == "改名"
    assert result.category_id == "c1"
    assert [(a.name, a.allocation) for a in result.assignees] == [("田中", 0.5)]
    assert result.predecessors == ["p1"]
    assert result.priority is Priority.HIGH
    assert result.color == "#123456"
    assert result.urls == original.urls


async def test_a_layout_switch_alone_is_not_a_change(user: User) -> None:
    mount_dialog(rich_task(), [], link_options={"p1": "先行"}, categories=[Category("開発", id="c1")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-layout").elements.pop().set_value("schedule")
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False  # 切り替えは、変更に数えない(確認なしで閉じる)
    assert confirm_dialog_of(user).value is False


async def test_a_checkpoint_hides_the_normal_fields_in_every_layout(user: User) -> None:
    mount_dialog(None, [], layout="schedule")
    await open_dialog(user)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.CHECKPOINT)
    for marker in ("task-start-date", "task-effort", "task-actual-start-date"):
        await user.should_not_see(marker=marker)
    await user.should_see(marker="task-deadline-date")
    user.find(marker="task-layout").elements.pop().set_value("all")
    for marker in ("task-start-date", "task-effort", "task-actual-start-date", "task-assignee-add"):
        await user.should_not_see(marker=marker)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.NORMAL)
    await user.should_see(marker="task-effort")
    await user.should_see(marker="task-assignee-add")


async def test_back_to_normal_in_the_schedule_layout_keeps_the_assignees_hidden(user: User) -> None:
    mount_dialog(None, [], layout="schedule")
    await open_dialog(user)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.CHECKPOINT)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.NORMAL)
    await user.should_see(marker="task-effort")  # 通常の欄は戻る
    await user.should_not_see(marker="task-assignee-add")  # レイアウトが隠す欄は、隠れたまま


async def test_the_conversion_stays_visible_in_the_schedule_layout(user: User) -> None:
    task = Task("a", effort_hours=13.0, assignees=[Assignee("田中", 0.5)])
    mount_dialog(task, [], layout="schedule", members=[Member("田中", 0.5)])
    await open_dialog(user)
    await user.should_not_see(marker="task-assignee-add")  # 担当者の欄は隠れていても
    conversion = user.find(marker="task-conversion").elements.pop()  # 算出値を動かす換算の説明は、見える
    assert "換算率" in conversion.text


async def test_clearing_the_assignee_after_editing_the_hidden_allocation_is_not_a_change(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    select = user.find(marker="task-assignee").elements.pop()
    with user.client:
        select.set_value("田中")
        user.find(marker="task-allocation").elements.pop().set_value(50)
        select.set_value("")  # (なし)に戻す。割り当て率は隠れて、値だけが残る
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False  # 実質、何も変わっていないので、確認なしで閉じる
    assert confirm_dialog_of(user).value is False


async def test_a_real_allocation_change_still_asks_before_closing(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
        user.find(marker="task-allocation").elements.pop().set_value(50)
    user.find(marker="task-cancel").click()
    assert confirm_dialog_of(user).value is True
