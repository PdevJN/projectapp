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
