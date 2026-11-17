"""タスクのメモ(要望 150)の画面のテスト。"""

from pathlib import Path

from nicegui.testing import User

from projectapp import notes
from test_views import open_dashboard_view


async def test_the_note_mark_appears_only_for_tasks_with_a_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    await user.should_not_see(marker=f"task-note-{task.id}")
    notes.save(view.project.name, task.id, "<p>メモ</p>")
    view.gantt.note_ids = notes.note_ids(view.project.name)
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")


async def test_the_note_mark_calls_open_note_with_the_task_id(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    opened: list[str] = []
    view.gantt.actions.open_note = opened.append
    view.gantt.note_ids = frozenset({task.id})
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")
    user.find(marker=f"task-note-{task.id}").click()
    assert opened == [task.id]


async def test_the_context_menu_note_opens_the_pane_and_typing_saves(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    with user.client:
        view.note_at(path, index)
    await user.should_see(marker="note-editor")
    assert view.note_pane is not None
    assert (view.note_pane.name, view.note_pane.task_id) == (view.project.name, task.id)
    assert (
        notes.load(view.project.name, task.id) is None
    )  # 入力するまでファイルは作らない
    with user.client:
        view.note_pane.editor.set_value("<p>経緯</p>")
        view.note_pane.flush()
    assert notes.load(view.project.name, task.id) == "<p>経緯</p>"
    assert task.id in view.gantt.note_ids  # 🗒️が付く


async def test_opening_an_existing_note_shows_its_text_and_switching_saves_the_previous(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    first = view.project.all_tasks()[0]
    notes.save(view.project.name, first.id, "<p>既存</p>")
    with user.client:
        view.open_note(first.id)
    assert view.note_pane is not None
    assert view.note_pane.editor.value == "<p>既存</p>"
    with user.client:
        view.note_pane.editor.set_value("<p>書き換え</p>")
        view.open_note(first.id)  # 切り替えの前に、いまの入力を保存する
    assert notes.load(view.project.name, first.id) == "<p>書き換え</p>"


async def test_emptying_the_note_removes_the_file_and_the_mark(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>x</p>")
    view.gantt.note_ids = notes.note_ids(view.project.name)
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p><br></p>")
        view.note_pane.flush()
    assert notes.load(view.project.name, task.id) is None
    assert task.id not in view.gantt.note_ids


async def test_close_saves_pending_text_and_hides_the_pane(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>閉じる前</p>")
        view.note_pane.close()
    assert notes.load(view.project.name, task.id) == "<p>閉じる前</p>"
    assert view.note_pane.task_id is None
