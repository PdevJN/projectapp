"""タスクのメモ(要望 150)の画面のテスト。"""

from pathlib import Path

from nicegui.testing import User

from projectapp import notes
from projectapp.models import Section, Task
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
    notes.save(
        view.project.name, task.id, "<p>x</p>"
    )  # after_edit が、ファイルから🗒️を決める
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


async def test_deleting_a_task_removes_its_note_and_undo_restores_it(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    notes.save(view.project.name, task.id, "<p>残す</p>")
    with user.client:
        view.delete_task(path, index)
    assert notes.load(view.project.name, task.id) is None
    assert task.id not in view.gantt.note_ids
    with user.client:
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>残す</p>"
    assert task.id in view.gantt.note_ids
    with user.client:
        view.redo()
        view.undo()
    assert (
        notes.load(view.project.name, task.id) == "<p>残す</p>"
    )  # 繰り返しても失われない


async def test_deleting_the_open_task_closes_the_pane_without_resurrecting_the_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>書いた</p>")
        view.delete_task(path, index)  # 保存してから消す(元に戻すで戻る)
    assert view.note_pane.task_id is None
    assert notes.load(view.project.name, task.id) is None
    with user.client:
        view.note_pane.flush()  # 閉じたあとに保存が走っても、ファイルは復活しない
    assert notes.load(view.project.name, task.id) is None
    with user.client:
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>書いた</p>"


async def test_copying_a_task_copies_its_note(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    notes.save(view.project.name, task.id, "<p>写す</p>")
    with user.client:
        view.copy_task_below(path, index)
    copies = [t for t in view.project.all_tasks() if t.id != task.id]
    assert len(copies) == 1
    assert notes.load(view.project.name, copies[0].id) == "<p>写す</p>"
    assert notes.load(view.project.name, task.id) == "<p>写す</p>"  # 元は残る
    assert copies[0].id in view.gantt.note_ids


async def test_copying_a_section_copies_the_notes_of_its_tasks(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path, with_task=False)
    inner = Task("中")
    view.project.sections = [Section("元", tasks=[inner])]
    notes.save(view.project.name, inner.id, "<p>中のメモ</p>")
    with user.client:
        view.copy_section((0,))
    copied = view.project.sections[1].all_tasks()[0]
    assert copied.id != inner.id
    assert notes.load(view.project.name, copied.id) == "<p>中のメモ</p>"
    assert notes.load(view.project.name, inner.id) == "<p>中のメモ</p>"


async def test_a_task_that_vanishes_outside_an_edit_keeps_its_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>外部</p>")
    view.project.tasks = [t for t in view.project.tasks if t.id != task.id]
    with user.client:
        view.reset_history()  # 外部の変更(git pull など)で消えた扱い
    assert notes.load(view.project.name, task.id) == "<p>外部</p>"


async def test_save_as_copies_the_notes_to_the_new_name(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    old = view.project.name
    notes.save(old, task.id, "<p>引き継ぐ</p>")
    with user.client:
        assert view.save_as_new("別名")
    assert notes.load("別名", task.id) == "<p>引き継ぐ</p>"
    assert notes.load(old, task.id) == "<p>引き継ぐ</p>"
