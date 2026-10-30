from datetime import date
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.models import Assignee, Member, Project, Section, Task, TaskKind
from projectapp.storage import load_project
from projectapp.views import MainView


def make_project() -> Project:
    return Project(
        "親",
        base_date=date(2026, 10, 5),
        members=[Member("田中", id="m1")],
        tasks=[Task("a", id="a", effort_hours=8), Task("b", id="b", effort_hours=4)],
        sections=[Section("開発", [Task("c", id="c", effort_hours=2, assignees=[Assignee("田中", 1.0)])], id="s1")],
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


async def test_extract_saves_the_child_and_replaces_the_tasks_with_a_reference(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    assert view.apply_extract(["a", "c"], "子") is not False
    child = load_project(view.project_dir / "子.json")
    assert {t.id for t in child.all_tasks()} == {"a", "c"}
    kinds = [t.kind for t in view.project.all_tasks()]
    assert kinds.count(TaskKind.REFERENCE) == 1 and "a" not in view.project.task_map()
    assert view.is_dirty()


async def test_extract_is_one_undo_step_and_keeps_the_child_file(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.apply_extract(["a", "c"], "子")
    view.undo()
    assert set(view.project.task_map()) == {"a", "b", "c"}
    assert (view.project_dir / "子.json").exists()  # 元に戻しても、保存した子のファイルは残る


async def test_extract_leaves_the_parent_untouched_when_the_child_cannot_be_saved(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    (view.project_dir / "子.json").write_text("{}", encoding="utf-8")  # ダイアログの検証のあとに、同名のファイルができた
    before = view.project.task_map().keys()
    assert view.apply_extract(["a"], "子") is False
    assert set(view.project.task_map()) == set(before) and not view.is_dirty()
    assert (view.project_dir / "子.json").read_text(encoding="utf-8") == "{}"  # 上書きしない


async def test_extract_clears_the_selection(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.bulk.ids.update({"a", "b"})
    view.apply_extract(["a", "b"], "子")
    assert not view.gantt.has_selection()


async def test_extract_takes_a_snapshot_when_the_reference_mode_is_snapshot(user: User, tmp_path: Path) -> None:
    from projectapp.models import ReferenceMode

    view = await open_view(user, tmp_path)
    view.project.reference_mode = ReferenceMode.SNAPSHOT
    view.apply_extract(["a"], "子")
    reference = next(t for t in view.project.all_tasks() if t.kind is TaskKind.REFERENCE)
    assert reference.ref_snapshot is not None and reference.ref_snapshot.taken_at is not None


async def test_extract_notifies_the_count_and_dropped_predecessors(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.project.tasks[1].predecessors = ["a"]  # b は外の a を先行にしている
    view.apply_extract(["b"], "子")
    await user.should_see("「子」に 1 件を切り出しました")
    await user.should_see("先行 1 件を外しました")


async def test_the_selection_bar_and_the_context_menu_have_the_entry(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.bulk.ids.update({"a", "b"})
    view.gantt.sync_bulk()
    await user.should_see(marker="bulk-extract")
    view.gantt.open_menu((), 0)
    assert view.gantt.extract_label is not None
    assert view.gantt.extract_label.text == "選択中 2 件を子プロジェクトに切り出し…"


async def test_extract_adds_the_child_to_the_file_list_and_refreshes_git(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    refreshed: list[bool] = []
    view.request_git_refresh = lambda: refreshed.append(True)  # type: ignore[method-assign]
    view.apply_extract(["a"], "子")
    assert "子" in view.files and view.files["子"] == view.project_dir / "子.json"
    assert "子" in view.file_select.options
    assert view.file_select.value == view.current_name()  # 開いているプロジェクトの選択は変えない
    assert refreshed == [True]


async def test_extract_tells_that_the_child_file_stays_after_undo(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.apply_extract(["a"], "子")
    await user.should_see("元に戻しても子のファイルは残ります")
