import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import DayKind, save_cache
from projectapp.gantt import KIND_COLORS
from projectapp.forms import build_task
from projectapp.models import Member, Project, Section, Task
from projectapp.storage import load_project, save_project
from projectapp.views import MainView


def holiday_csv() -> bytes:
    today = date.today()
    row = f"{today.year}/{today.month}/{today.day},テスト祝日\n"
    return ("国民の祝日・休日月日,国民の祝日・休日名称\n" + row).encode("cp932")


def make_transport(status: int, calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, content=holiday_csv())

    return httpx.MockTransport(handler)


def mount(base_dir: Path, transport: httpx.MockTransport) -> None:
    @ui.page("/")
    def index() -> None:
        MainView(base_dir, transport).build()


def mount_capturing(base_dir: Path, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []))
        views.append(view)
        view.build()


async def choose_in_combo(user: User, name: str) -> None:
    user.find(kind=ui.select).click()
    user.find(name).click()


async def save_new_as(user: User, name: str) -> None:
    user.find(marker="save-project").click()
    user.find(marker="project-name").type(name)
    user.find(marker="name-save").click()


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


def stripes_have_holiday(user: User) -> bool:
    color = KIND_COLORS[DayKind.HOLIDAY]
    return any(color in e.content for e in user.find(marker="stripes").elements)


async def test_main_view(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    await user.should_see("新規プロジェクト")
    await user.should_see("開く")
    await user.should_see(marker="scale-toggle")


async def test_first_launch_fetches_holidays_once(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    mount(tmp_path, make_transport(200, calls))
    await user.open("/")
    assert await wait_until(lambda: stripes_have_holiday(user))
    assert (tmp_path / "holidays.json").exists()
    assert len(calls) == 1


async def test_cached_holidays_are_not_fetched_again(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    mount(tmp_path, make_transport(200, calls))
    await user.open("/")
    await asyncio.sleep(0.3)
    assert calls == []


async def test_first_fetch_failure_keeps_the_screen_and_retries_next_time(
    user: User, tmp_path: Path
) -> None:
    mount(tmp_path, make_transport(500, []))
    await user.open("/")
    assert await wait_until(lambda: user.notify.contains("祝日データを取得できませんでした"))
    await user.should_see("新規プロジェクト")
    assert not (tmp_path / "holidays.json").exists()


async def test_refresh_button_fetches_again(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    mount(tmp_path, make_transport(200, calls))
    await user.open("/")
    user.find(marker="refresh-holidays").click()
    assert await wait_until(lambda: user.notify.contains("祝日データを更新しました"))
    assert len(calls) == 1
    assert await wait_until(lambda: stripes_have_holiday(user))


async def test_add_section_then_task_shows_a_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-section").click()
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    await user.should_see(marker="add-task-0")
    user.find(marker="add-task-0").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    await user.should_see(marker="bar-0-0")


async def test_edit_task_updates_the_name(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-section").click()
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    await user.should_see(marker="add-task-0")
    user.find(marker="add-task-0").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see(marker="task-0-0")
    user.find(marker="task-0-0").click()
    await user.should_see("タスクの編集")


async def test_top_add_row_creates_a_task_without_a_section(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-task-top").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="add-task-0")


async def test_top_add_row_stays_out_of_sections(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-section").click()
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    await user.should_see(marker="add-task-0")
    user.find(marker="add-task-top").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see(marker="task-top-0")
    await user.should_not_see(marker="task-0-0")


async def test_edit_top_level_task_opens_the_edit_dialog(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-task-top").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see(marker="task-top-0")
    user.find(marker="task-top-0").click()
    await user.should_see("タスクの編集")


async def test_save_task_adds_then_replaces(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, make_transport(200, []))
        views.append(view)
        view.build()

    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("a"))
    view.save_task(None, 0, Task("b"))
    view.save_section("開発")
    view.save_task(0, None, Task("x"))
    view.save_task(0, 0, Task("y"))
    assert [t.name for t in view.project.tasks] == ["b"]
    assert [t.name for t in view.project.sections[0].tasks] == ["y"]
    await user.should_see(marker="task-top-0")
    await user.should_see(marker="task-0-0")


async def test_refresh_holidays_button_is_right_next_to_the_project_title(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    title = user.find(content="新規プロジェクト").elements.pop()
    button = user.find(marker="refresh-holidays").elements.pop()
    row = button.parent_slot.parent
    ancestors = []
    node = title
    while node.parent_slot is not None and node.parent_slot.parent is not None:
        node = node.parent_slot.parent
        ancestors.append(node)
    assert row in ancestors  # タイトルとボタンは同じ行にある
    assert title.id < button.id  # ボタンはタイトルの右


def make_view(tmp_path: Path, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, make_transport(200, []))
        views.append(view)
        view.build()


async def test_saving_start_and_effort_shows_a_bar_without_storing_the_end(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].save_task(None, None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    assert views[0].project.tasks[0].planned_end is None  # 完了予定は保存せず、その都度計算する
    await user.should_see(marker="bar-top-0")


async def test_a_task_with_only_a_start_shows_a_one_day_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].save_task(None, None, Task("a", planned_start=datetime(2026, 10, 9, 9)))
    assert views[0].project.tasks[0].planned_end is None
    await user.should_see(marker="bar-top-0")
    bar = user.find(marker="bar-top-0").elements.pop()
    assert bar._style["width"] == "40.0px"  # 完了予定は開始予定の翌日


async def test_save_new_project_asks_for_a_name_then_writes_the_file(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await save_new_as(user, "デモ")
    assert await wait_until(lambda: (tmp_path / "デモ.json").exists())
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    view = views[0]
    assert view.path == tmp_path / "デモ.json"
    assert "デモ" in view.file_select.options
    await user.should_see("デモ")


async def test_save_new_project_rejects_an_existing_name(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    original = save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await save_new_as(user, "既存")
    await user.should_see("同じ名前のプロジェクトがすでにあります")
    assert load_project(original).sections[0].name == "元"
    assert views[0].path is None


async def test_save_an_opened_project_overwrites_without_asking(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    view.save_section("追加")
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    await user.should_not_see(marker="project-name")
    saved = load_project(tmp_path / "既存.json")
    assert [s.name for s in saved.sections] == ["元", "追加"]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (OSError("disk full"), "保存できませんでした"),
        (FileExistsError(), "同じ名前のファイルがすでにあります"),
    ],
)
async def test_failed_save_keeps_the_state(
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
    message: str,
) -> None:
    save_cache({}, tmp_path)

    def boom(*args: object, **kwargs: object) -> Path:
        raise error

    monkeypatch.setattr("projectapp.views.save_project", boom)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await save_new_as(user, "デモ")
    assert await wait_until(lambda: user.notify.contains(message))
    view = views[0]
    assert view.path is None
    assert view.project.name == "新規プロジェクト"
    assert not (tmp_path / "デモ.json").exists()


async def test_saving_with_an_unusable_name_notifies(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.path = tmp_path / "x.json"
    view.project.name = "a:b"
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("名前に使えない文字が含まれています"))
    assert view.path == tmp_path / "x.json"


async def test_failed_open_keeps_the_current_project_and_path(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    (tmp_path / "壊れ.json").write_text("{not json", encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "壊れ")
    assert await wait_until(lambda: user.notify.contains("開けませんでした"))
    assert view.path is None
    assert view.project.name == "新規プロジェクト"


async def test_choosing_in_the_combo_opens_a_clean_project_at_once(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await choose_in_combo(user, "既存")
    view = views[0]
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    assert view.project.sections[0].name == "元"
    await user.should_not_see(marker="unsaved-save")


async def test_is_dirty_follows_open_edit_and_save(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存"), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    assert not view.is_dirty()
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    assert not view.is_dirty()
    view.save_section("追加")
    assert view.is_dirty()
    user.find(marker="save-project").click()
    assert await wait_until(lambda: not view.is_dirty())


async def test_saving_a_new_project_does_not_reload_it(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    before = view.project
    view.save_section("追加")
    await save_new_as(user, "デモ")
    assert await wait_until(lambda: view.path == tmp_path / "デモ.json")
    assert view.project is before
    assert view.file_select.value == "デモ"


async def test_dirty_project_asks_before_switching_and_cancel_keeps_it(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("追加")
    await choose_in_combo(user, "既存")
    await user.should_see(marker="unsaved-save")
    assert view.path is None
    assert view.file_select.value is None
    user.find(marker="unsaved-cancel").click()
    assert view.path is None
    assert [s.name for s in view.project.sections] == ["追加"]


async def test_discard_and_open_drops_the_changes(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("追加")
    await choose_in_combo(user, "既存")
    user.find(marker="unsaved-discard").click()
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    assert [s.name for s in view.project.sections] == ["元"]
    assert not view.is_dirty()


async def test_save_and_open_saves_the_saved_project_first(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("甲"), tmp_path)
    save_project(Project("乙", sections=[Section("乙の中身")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "甲")
    assert await wait_until(lambda: view.path == tmp_path / "甲.json")
    view.save_section("追加")
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "乙.json")
    assert [s.name for s in load_project(tmp_path / "甲.json").sections] == ["追加"]
    assert [s.name for s in view.project.sections] == ["乙の中身"]


async def test_save_and_open_for_a_new_project_goes_through_the_name_dialog(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("追加")
    await choose_in_combo(user, "既存")
    user.find(marker="unsaved-save").click()
    user.find(marker="project-name").type("新規保存")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    assert (tmp_path / "新規保存.json").exists()
    assert [s.name for s in view.project.sections] == ["元"]


async def test_save_and_open_does_not_switch_when_the_save_fails(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)

    def boom(*args: object, **kwargs: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.views.save_project", boom)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("追加")
    await choose_in_combo(user, "既存")
    user.find(marker="unsaved-save").click()
    user.find(marker="project-name").type("デモ")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: user.notify.contains("保存できませんでした"))
    assert view.path is None
    assert [s.name for s in view.project.sections] == ["追加"]


async def test_failed_open_from_the_combo_restores_the_display(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    (tmp_path / "壊れ.json").write_text("{not json", encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await choose_in_combo(user, "壊れ")
    assert await wait_until(lambda: user.notify.contains("開けませんでした"))
    assert views[0].file_select.value is None


async def test_open_button_lists_files_and_opens_the_chosen_one(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("甲", sections=[Section("甲の中身")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    save_project(Project("後から"), tmp_path)  # 起動後に増えたファイルも一覧に出る
    user.find("開く").click()
    await user.should_see(marker="file-0")
    await user.should_see("後から")
    user.find(marker="file-1").click()
    assert await wait_until(lambda: view.path == tmp_path / "甲.json")
    assert [s.name for s in view.project.sections] == ["甲の中身"]
    assert "後から" in view.file_select.options


async def test_open_button_with_no_files_says_so(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find("開く").click()
    await user.should_see("プロジェクトファイルがありません")


async def open_settings_and_apply(user: User, hours: str, start: str) -> None:
    user.find(marker="open-settings").click()
    user.find(marker="settings-hours").clear().type(hours)
    user.find(marker="settings-start").clear().type(start)
    user.find(marker="settings-apply").click()


async def test_apply_settings_with_the_same_values_does_nothing(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="open-settings").click()
    user.find(marker="settings-apply").click()
    await asyncio.sleep(0.3)
    assert not user.notify.contains("稼働時間を変更しました")
    assert not view.is_dirty()


async def test_invalid_settings_keep_the_dialog_and_the_values(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await open_settings_and_apply(user, "25", "09:00")
    await user.should_see("1以上8以下")
    assert view.project.daily_hours == 6.5


async def test_settings_are_saved_with_the_project(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("自動", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    await open_settings_and_apply(user, "8", "10:00")
    assert await wait_until(lambda: view.is_dirty())
    await save_new_as(user, "設定")
    assert await wait_until(lambda: (tmp_path / "設定.json").exists())
    saved = load_project(tmp_path / "設定.json")
    assert saved.daily_hours == 8.0
    assert saved.work_start == time(10, 0)
    assert saved.tasks[0].planned_end is None


async def test_changed_settings_ask_before_switching_projects(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存"), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await open_settings_and_apply(user, "8", "09:00")
    assert await wait_until(lambda: views[0].is_dirty())
    await choose_in_combo(user, "既存")
    await user.should_see(marker="unsaved-save")
    assert views[0].path is None


async def test_delete_task_removes_only_that_task_and_makes_the_view_dirty(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(
        Project(
            "既存",
            tasks=[Task("a"), Task("b")],
            sections=[Section("開発", [Task("x"), Task("y")])],
        ),
        tmp_path,
    )
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    assert not view.is_dirty()
    view.delete_task(None, 0)
    assert [t.name for t in view.project.tasks] == ["b"]
    assert [t.name for t in view.project.sections[0].tasks] == ["x", "y"]
    view.delete_task(0, 1)
    assert [t.name for t in view.project.sections[0].tasks] == ["x"]
    assert [t.name for t in view.project.tasks] == ["b"]
    assert view.is_dirty()


async def test_delete_from_the_edit_dialog_removes_the_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-task-top").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see(marker="task-top-0")
    user.find(marker="task-top-0").click()
    user.find(marker="task-delete").click()
    user.find(marker="delete-confirm").click()
    await user.should_not_see(marker="task-top-0")


async def test_refresh_holidays_survives_a_cache_write_failure(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_cache({date(2026, 10, 12): "スポーツの日"}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")

    async def failing_download(base_dir: Path, transport: object = None) -> dict[date, str]:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.views.download_holidays", failing_download)
    await views[0].refresh_holidays()
    assert user.notify.contains("祝日データを取得できませんでした")
    assert views[0].holidays == {date(2026, 10, 12): "スポーツの日"}


async def test_save_as_new_refuses_a_file_created_after_the_name_was_checked(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    save_project(Project("競合", sections=[Section("先客")]), tmp_path)  # 検証のあとに作られた想定
    assert view.save_as_new("競合") is False
    assert user.notify.contains("同じ名前のファイルがすでにあります")
    assert view.path is None
    assert view.project.name != "競合"
    assert load_project(tmp_path / "競合.json").sections[0].name == "先客"


async def test_name_dialog_keeps_the_input_when_the_save_fails(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")

    def boom(*args: object, **kwargs: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.views.save_project", boom)
    user.find(marker="save-project").click()
    user.find(marker="project-name").type("デモ")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: user.notify.contains("保存できませんでした"))
    await user.should_see(marker="project-name")  # ダイアログは開いたまま
    assert views[0].path is None


def bar_width(user: User) -> str | None:
    found = user.find(marker="bar-top-0").elements
    return next(iter(found))._style["width"] if found else None


async def test_apply_settings_rerenders_without_a_recalculation_notice(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    await user.should_see(marker="bar-top-0")
    before = bar_width(user)
    await open_settings_and_apply(user, "8", "09:00")
    assert await wait_until(lambda: view.project.daily_hours == 8.0)
    assert await wait_until(lambda: bar_width(user) != before)  # 稼働時間で完了予定が変わり、棒の長さが変わる
    assert not user.notify.contains("再計算")
    assert view.project.tasks[0].planned_end is None  # 完了予定は保存されない


async def test_refreshing_holidays_rerenders_the_bar(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    await user.should_see(marker="bar-top-0")
    before = bar_width(user)

    async def fake_download(base_dir: Path, transport: object = None) -> dict[date, str]:
        return {date(2026, 10, 12): "スポーツの日"}

    monkeypatch.setattr("projectapp.views.download_holidays", fake_download)
    await view.refresh_holidays()
    assert await wait_until(lambda: bar_width(user) != before)
    assert user.notify.contains("祝日データを更新しました")


async def open_members_view(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    return views[0]


async def test_the_members_dialog_adds_a_member(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    user.find(marker="open-members").click()
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")  # 再描画を待つ
    user.find(marker="member-name-0").type("田中")
    user.find(marker="member-ratio-0").clear().type("120")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [Member("田中", 1.2)])
    assert view.is_dirty()


async def test_the_members_dialog_rejects_a_duplicate_name(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-1")
    user.find(marker="member-name-1").type("田中")
    user.find(marker="member-apply").click()
    await user.should_see("重複")
    assert view.project.members == [Member("田中", 1.0)]


async def test_applying_the_same_members_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.2)]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-apply").click()
    await asyncio.sleep(0.3)
    assert not view.is_dirty()


async def test_renaming_a_member_renames_the_assignee_of_its_tasks(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0), Member("鈴木", 1.0)]
    view.project.tasks = [Task("a", assignee="田中"), Task("b", assignee="鈴木"), Task("c")]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-name-0").clear().type("田中太郎")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignee == "田中太郎")
    assert [t.assignee for t in view.project.tasks] == ["田中太郎", "鈴木", None]
    assert [m.name for m in view.project.members] == ["田中太郎", "鈴木"]


async def test_a_member_with_tasks_cannot_be_deleted(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.project.tasks = [Task("a", assignee="田中")]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-delete-0").click()
    user.find(marker="member-apply").click()
    await user.should_see("1件")
    assert view.project.members == [Member("田中", 1.0)]


async def test_a_member_without_tasks_can_be_deleted(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-delete-0").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [])


async def test_the_members_dialog_leaves_no_elements_after_hide(user: User, tmp_path: Path) -> None:
    await open_members_view(user, tmp_path)
    user.find(marker="open-members").click()
    await user.should_see(marker="member-add")
    user.find(kind=ui.dialog).trigger("hide")
    await user.should_not_see(marker="member-add")
