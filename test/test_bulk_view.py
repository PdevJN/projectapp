from datetime import date, datetime
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.bulk_edit import BulkChanges, CategoryChange, CrewChange, CrewMode, EffortChange, EffortMode
from projectapp.models import Assignee, Member, Project, Section, Task, TaskKind
from projectapp.views import MainView


def make_project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        members=[Member("田中", id="m1"), Member("鈴木", id="m2")],
        tasks=[Task("a", id="a", effort_hours=8), Task("b", id="b", effort_hours=4)],
        sections=[Section("開発", [Task("c", id="c", effort_hours=2, assignees=[Assignee("田中", 1.0)])])],
    )


def mount(tmp_path: Path, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200)))
        views.append(view)
        view.build()
        view.project = make_project()
        view.mark_clean()
        view.reset_history()
        view.gantt.set_project(view.project)


async def open_view(user: User, tmp_path: Path) -> MainView:
    views: list[MainView] = []
    mount(tmp_path, views)
    await user.open("/")
    return views[0]


async def test_apply_bulk_edits_all_targets_in_one_undo_step(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.apply_bulk(["a", "b"], BulkChanges(effort=EffortChange(EffortMode.SET, 5)))
    assert [t.effort_hours for t in view.project.all_tasks()] == [5, 5, 2]
    assert view.is_dirty()
    view.undo()  # 1 回で全部戻る
    assert [t.effort_hours for t in view.project.all_tasks()] == [8, 4, 2]


async def test_replace_with_weekly_tasks_asks_first_and_applies_only_after_confirming(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    task = view.project.task_map()["c"]
    task.weekly_crew = [[Assignee("田中", 1.0)]]
    change = BulkChanges(crew=CrewChange(CrewMode.REPLACE, (Assignee("鈴木", 1.0),)))
    with user.client:  # 確認のダイアログを作るので、画面の文脈に入る
        view.apply_bulk(["a", "c"], change)
    await user.should_see("週ごと")  # 件数入りの確認
    assert view.project.task_map()["c"].weekly_crew  # まだ変わらない
    user.find(content="適用").click()
    assert view.project.task_map()["c"].weekly_crew == []


async def test_replace_without_weekly_tasks_applies_without_asking(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.apply_bulk(["a"], BulkChanges(crew=CrewChange(CrewMode.REPLACE, (Assignee("鈴木", 1.0),))))
    assert [a.name for a in view.project.task_map()["a"].assignees] == ["鈴木"]


async def test_bulk_delete_confirms_with_counts_removes_once_and_clears_the_selection(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.clicked_task("a", {"ctrl": True})
    view.gantt.clicked_task("c", {"ctrl": True})
    with user.client:
        view.confirm_bulk_delete(view.gantt.selected_ids())
    await user.should_see("2 件のタスクを削除します")
    user.find(marker="confirm-ok").click()
    assert [t.id for t in view.project.all_tasks()] == ["b"]
    assert not view.gantt.has_selection()
    view.undo()
    assert [t.id for t in view.project.all_tasks()] == ["a", "b", "c"]


async def test_escape_clears_the_selection_but_not_while_a_dialog_is_open(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.clicked_task("a", {"ctrl": True})
    view.escape_pressed()
    assert not view.gantt.has_selection()


async def test_opening_another_project_clears_the_selection(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.clicked_task("a", {"ctrl": True})
    view.show_project(make_project(), None)
    assert not view.gantt.has_selection()


async def test_warn_overallocation_with_a_limit_notifies_that_many_people_and_counts_the_rest(
    user: User, tmp_path: Path, monkeypatch
) -> None:
    view = await open_view(user, tmp_path)
    start, end = datetime(2026, 10, 5, 9), datetime(2026, 10, 6, 15, 30)
    people = ["田中", "鈴木", "佐藤", "高橋", "伊藤"]
    view.project.members = [Member(name) for name in people]
    tasks = [
        Task(f"t{i}-{n}", id=f"t{i}-{n}", planned_start=start, planned_end=end, planned_end_manual=True, assignees=[Assignee(n, 1.0)])
        for i in range(2)
        for n in people
    ]
    view.project.tasks = tasks
    messages: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda message, **_kw: messages.append(message))
    view.warn_overallocation(*tasks, limit=3)
    assert len([m for m in messages if "最大" in m]) == 3
    assert [m for m in messages if "ほか" in m] == ["ほか 2 人も割り当てが 100% を超える期間があります"]


async def test_delete_key_asks_to_delete_the_selection_and_does_nothing_without_one(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    with user.client:
        view.delete_selected()
    await user.should_not_see("件のタスクを削除します")
    view.gantt.clicked_task("a", {"ctrl": True})
    with user.client:
        view.delete_selected()
    await user.should_see("1 件のタスクを削除します")
    user.find(marker="confirm-ok").click()
    assert [t.id for t in view.project.all_tasks()] == ["b", "c"]
