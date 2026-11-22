"""ヘッダーのタイトルのダブルクリックで、プロジェクトの名前を変える(要望 142)。"""

from pathlib import Path

import pytest

from nicegui.testing import User

from projectapp import notes
from projectapp.calendar import save_cache
from projectapp.models import Project, Section, Task, TaskKind
from projectapp.storage import load_project, save_project
from projectapp.views import MainView
from test_views import choose_in_combo, make_view


async def open_saved(user: User, tmp_path: Path, name: str = "旧") -> MainView:
    save_cache({}, tmp_path)
    save_project(
        Project(name, sections=[Section("S", tasks=[Task("t", id="t1")])]), tmp_path
    )
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    await choose_in_combo(user, name)
    return views[0]


async def test_double_click_shows_the_input_and_escape_cancels(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    user.find(marker="project-title").trigger("dblclick")
    await user.should_see(marker="title-input")
    user.find(marker="title-input").trigger("keydown.escape")
    await user.should_not_see(marker="title-input")
    await user.should_see(marker="project-title")
    assert view.project.name == "旧" and (tmp_path / "旧.json").exists()


async def test_enter_renames_the_file_and_keeps_the_view_clean(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    notes.save("旧", "t1", "<p>メモ</p>")
    user.find(marker="project-title").trigger("dblclick")
    await user.should_see(marker="title-input")
    user.find(marker="title-input").clear().type("新")
    user.find(marker="title-input").trigger("keydown.enter")
    assert view.project.name == "新"
    assert view.path == tmp_path / "新.json"
    assert not (tmp_path / "旧.json").exists()
    assert load_project(tmp_path / "新.json").name == "新"
    assert notes.load("新", "t1") == "<p>メモ</p>"
    assert notes.load("旧", "t1") is None
    assert view.is_dirty() is False
    await user.should_see(marker="project-title")


async def test_unsaved_edits_stay_unsaved_after_a_rename(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    view.save_task((), None, Task("追加"))
    assert view.is_dirty()
    view.begin_title_edit()
    view.commit_title("新")
    assert view.is_dirty()
    assert [t.name for t in load_project(tmp_path / "新.json").all_tasks()] == ["t"]


async def test_a_never_saved_project_only_changes_its_name(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.begin_title_edit()
    view.commit_title("最初の名前")
    assert view.project.name == "最初の名前" and view.path is None
    assert not (tmp_path / "最初の名前.json").exists()


async def test_invalid_and_duplicate_names_keep_the_input_open(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    save_project(Project("既存"), tmp_path)
    view.begin_title_edit()
    view.commit_title("a/b")
    assert view.title_editing and view.project.name == "旧"
    view.commit_title("既存")
    assert view.title_editing and view.project.name == "旧"
    assert (tmp_path / "旧.json").exists()


async def test_same_or_blank_name_ends_the_edit_without_renaming(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    view.begin_title_edit()
    view.commit_title("旧")
    assert not view.title_editing and view.project.name == "旧"


async def test_references_ask_for_confirmation_and_are_rewritten(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    referrer = Project("参照元")
    referrer.tasks.append(Task("参", id="r", kind=TaskKind.REFERENCE, ref_project="旧"))
    save_project(referrer, tmp_path)
    view.begin_title_edit()
    view.commit_title("新")
    assert view.project.name == "旧"  # 確認が出るまでは変えない
    user.find(marker="confirm-ok").click()
    assert view.project.name == "新"
    assert load_project(tmp_path / "参照元.json").tasks[0].ref_project == "新"


async def test_cancelling_the_confirmation_changes_nothing(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    referrer = Project("参照元")
    referrer.tasks.append(Task("参", id="r", kind=TaskKind.REFERENCE, ref_project="旧"))
    save_project(referrer, tmp_path)
    view.begin_title_edit()
    view.commit_title("新")
    user.find(marker="confirm-cancel").click()
    assert view.project.name == "旧" and (tmp_path / "旧.json").exists()
    assert load_project(tmp_path / "参照元.json").tasks[0].ref_project == "旧"


async def test_saving_right_after_a_rename_raises_no_external_change_warning(
    user: User, tmp_path: Path
) -> None:
    view = await open_saved(user, tmp_path)
    view.begin_title_edit()
    view.commit_title("新")
    view.save_task((), None, Task("追加"))
    assert view.write(overwrite=True) is True
    saved = load_project(tmp_path / "新.json")
    assert sorted(t.name for t in saved.all_tasks()) == ["t", "追加"]


async def test_notes_return_when_the_file_cannot_be_moved(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = await open_saved(user, tmp_path)
    notes.save("旧", "t1", "<p>メモ</p>")

    def boom(*args: object, **kwargs: object) -> list[str]:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.views.rename_project_files", boom)
    assert view.rename_project("新") is False
    assert view.project.name == "旧" and (tmp_path / "旧.json").exists()
    assert notes.load("旧", "t1") == "<p>メモ</p>"
    assert notes.load("新", "t1") is None


async def test_a_leftover_notes_folder_is_explained(user: User, tmp_path: Path) -> None:
    view = await open_saved(user, tmp_path)
    notes.save("旧", "t1", "<p>メモ</p>")
    notes.save(
        "新", "zzzz9999", "<p>残り</p>"
    )  # 削除したプロジェクトのメモが残った想定
    assert view.rename_project("新") is False
    assert user.notify.contains("メモのフォルダが残っています")
    assert (tmp_path / "旧.json").exists()
