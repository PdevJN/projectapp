import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.config import load_zoom, save_zoom
from projectapp.calendar import DayKind, save_cache
from projectapp.filtering import TaskFilter
from projectapp.gantt import KIND_COLORS
from projectapp.forms import build_task
from projectapp.handoff import JSON_FILE_TYPES
from projectapp.models import Assignee, Actual, ActualMode, Member, Project, Section, Task, TaskUrl, UrlTemplate
from projectapp.storage import load_project, save_project
from nicegui.events import KeyboardAction, KeyboardKey, KeyboardModifiers, KeyEventArguments

from projectapp.export import PNG_FILE_TYPES, ExportError
from projectapp.dashboard import PeriodKind
from projectapp.timeline import Scale
from projectapp.gantt import ViewOptions
from projectapp.views import HEADER_CSS, THEME_ICONS, MainView


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


async def test_opening_a_project_resets_the_filter_but_editing_keeps_it(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", members=[Member("田中")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.gantt.set_filter(TaskFilter(query="設"))
    view.apply_members([Member("鈴木")], {})
    assert view.gantt.task_filter == TaskFilter(query="設")
    assert view.is_dirty()  # メンバーの変更は編集中になる(条件は関係しない)
    view.open_project("既存")
    assert view.gantt.task_filter == TaskFilter()
    assert user.find(marker="search-input").elements.pop().value == ""


async def test_the_filter_does_not_make_the_project_dirty(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    assert not view.is_dirty()
    view.gantt.set_filter(TaskFilter(query="設", assignee=None))
    assert not view.is_dirty()


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
    user.find(marker="file-open").click()
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
    user.find(marker="file-open").click()
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


async def test_delete_task_removes_its_id_from_the_successors(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    a = Task("a", id="aaaaaaaa")
    b = Task("b", id="bbbbbbbb", predecessors=["aaaaaaaa"])
    save_project(Project("既存", tasks=[a, b]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.delete_task(None, 0)
    assert view.project.tasks[0].predecessors == []


async def test_the_edit_dialog_offers_other_tasks_as_predecessors(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    a = Task("a", id="aaaaaaaa")
    b = Task("b", id="bbbbbbbb", predecessors=["aaaaaaaa"])
    c = Task("c", id="cccccccc")
    save_project(Project("既存", tasks=[a, b, c]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="task-top-0")
    user.find(marker="task-top-0").click()  # a を開く: 後続の b と自分は候補から外れる
    select = user.find(marker="task-predecessors").elements.pop()
    assert select.options == {"cccccccc": "c"}


async def test_shift_task_does_not_go_before_the_predecessors_finish(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    a = Task("a", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=13)
    b = Task(
        "b",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 12, 9),
        effort_hours=1,
        predecessors=["aaaaaaaa"],
    )
    save_project(Project("既存", base_date=date(2026, 10, 5), tasks=[a, b]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.shift_task(None, 1, -30)  # 大きく左へ
    assert view.project.tasks[1].planned_start == datetime(2026, 10, 6, 9)  # 先行の完了の日まで


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
    view.project.tasks = [Task("a", assignees=[Assignee("田中")]), Task("b", assignees=[Assignee("鈴木")]), Task("c")]
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
    view.project.tasks = [Task("a", assignees=[Assignee("田中")])]
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


async def test_saving_a_task_that_overloads_the_assignee_warns(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中", 1.0)]
    view.save_task(
        None,
        None,
        Task(
            "a",
            planned_start=datetime(2026, 10, 5),
            planned_end=datetime(2026, 10, 9),
            assignees=[Assignee("田中", 0.6)],
        ),
    )
    assert not user.notify.contains("割り当て")
    view.save_task(
        None,
        None,
        Task(
            "b",
            planned_start=datetime(2026, 10, 7),
            planned_end=datetime(2026, 10, 12),
            assignees=[Assignee("田中", 0.6)],
        ),
    )
    assert user.notify.contains("田中 の割り当てが最大120%")
    assert len(view.project.tasks) == 2  # 警告しても保存はされる


async def test_saving_a_task_that_does_not_overload_shows_no_warning(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中", 1.0)]
    for name, start, end, allocation in (("a", 5, 9, 0.7), ("b", 7, 12, 0.3)):
        view.save_task(
            None,
            None,
            Task(
                name,
                planned_start=datetime(2026, 10, start),
                planned_end=datetime(2026, 10, end),
                assignees=[Assignee("田中", allocation)],
            ),
        )
    assert not user.notify.contains("割り当て")


async def test_swapping_two_member_names_swaps_the_assignees_once(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("A", 1.0), Member("B", 1.0)]
    view.project.tasks = [Task("t1", assignees=[Assignee("A")]), Task("t2", assignees=[Assignee("B")])]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-name-0").clear().type("B")
    user.find(marker="member-name-1").clear().type("A")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignee == "B")
    assert [t.assignee for t in view.project.tasks] == ["B", "A"]
    assert [m.name for m in view.project.members] == ["B", "A"]


async def test_move_task_moves_marks_dirty_and_redraws(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("開発")
    view.project.tasks.append(Task("上"))
    view.project.sections[0].tasks.extend([Task("a"), Task("b")])
    view.mark_clean()
    view.move_task((0, 0), (None, 1), False)
    assert [t.name for t in view.project.tasks] == ["上", "a"]
    assert [t.name for t in view.project.sections[0].tasks] == ["b"]
    assert view.is_dirty()
    await user.should_see(marker="task-top-1")


async def test_move_task_to_the_same_place_does_nothing(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.extend([Task("a"), Task("b")])
    view.mark_clean()
    view.move_task((None, 0), (None, 1), False)
    assert [t.name for t in view.project.tasks] == ["a", "b"]
    assert not view.is_dirty()


async def test_move_task_with_stale_positions_is_ignored(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(Task("a"))
    view.mark_clean()
    view.move_task((None, 5), (None, 0), False)
    view.move_task((3, 0), (None, 0), False)
    view.move_task((None, 0), (7, 0), False)
    view.move_task((None, 0), (None, -1), True)
    assert [t.name for t in view.project.tasks] == ["a"]
    assert not view.is_dirty()


async def test_copy_task_adds_a_copy_and_notifies(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("開発")
    view.project.tasks.append(Task("設計"))
    view.mark_clean()
    view.move_task((None, 0), (0, 0), True)
    assert [t.name for t in view.project.tasks] == ["設計"]
    assert [t.name for t in view.project.sections[0].tasks] == ["設計(コピー)"]
    assert view.is_dirty()
    await user.should_see("「設計」をコピーしました")


async def test_shift_task_moves_the_dates_and_marks_dirty(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(
        Task("a", planned_start=datetime(2026, 10, 5, 9), deadline=datetime(2026, 10, 9))
    )
    view.mark_clean()
    view.shift_task(None, 0, 2)
    task = view.project.tasks[0]
    assert task.planned_start == datetime(2026, 10, 7, 9)
    assert task.deadline == datetime(2026, 10, 9)
    assert view.is_dirty()


async def test_shift_task_ignores_zero_and_stale_positions(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(Task("a", planned_start=datetime(2026, 10, 5, 9)))
    view.mark_clean()
    view.shift_task(None, 0, 0)
    view.shift_task(None, 4, 1)
    view.shift_task(2, 0, 1)
    assert view.project.tasks[0].planned_start == datetime(2026, 10, 5, 9)
    assert not view.is_dirty()


async def test_shift_task_out_of_the_year_range_notifies_and_keeps_the_dates(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(Task("a", planned_start=datetime(2100, 12, 31, 9)))
    view.mark_clean()
    view.shift_task(None, 0, 1)
    assert view.project.tasks[0].planned_start == datetime(2100, 12, 31, 9)
    assert not view.is_dirty()
    await user.should_see("日付の範囲を超えるため動かせません")


async def test_shift_task_warns_when_the_assignee_goes_over_100_percent(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)  # 既定は「今日」。日付が進むと、基準日より前へは動かせず、テストが落ちる
    view.apply_members([Member("田中")], {})
    first = Task("a", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5, assignees=[Assignee("田中")])
    second = Task("b", planned_start=datetime(2026, 10, 6, 9), effort_hours=6.5, assignees=[Assignee("田中")])
    view.project.tasks.extend([first, second])
    view.shift_task(None, 1, -1)  # 同じ日に重なる(割り当て 100% + 100%)
    await user.should_see("田中 の割り当てが最大200%になる期間があります")


async def test_shift_task_stops_at_the_base_date(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 7, 9),
        planned_end=datetime(2026, 10, 8, 18),
        planned_end_manual=True,
    )
    view.project.tasks.append(task)
    view.mark_clean()
    view.shift_task(None, 0, -5)  # 基準日(10/5)で止まる = 2日分だけ左へ
    assert task.planned_start == datetime(2026, 10, 5, 9)
    assert task.planned_end == datetime(2026, 10, 6, 18)
    view.mark_clean()
    view.shift_task(None, 0, -1)  # すでに基準日なので、これ以上は左へ動かない
    assert task.planned_start == datetime(2026, 10, 5, 9)
    assert not view.is_dirty()
    view.shift_task(None, 0, 3)  # 右へは動く
    assert task.planned_start == datetime(2026, 10, 8, 9)


async def test_shift_task_before_the_base_date_can_only_move_right(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    task = Task("a", planned_start=datetime(2026, 10, 3, 9))
    view.project.tasks.append(task)
    view.shift_task(None, 0, -1)
    assert task.planned_start == datetime(2026, 10, 3, 9)
    view.shift_task(None, 0, 1)
    assert task.planned_start == datetime(2026, 10, 4, 9)


async def test_switching_the_theme_refreshes_the_chart_scrollbars(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    calls: list[str] = []
    views[0].gantt.refresh_scrollbars = lambda: calls.append("refresh")  # type: ignore[method-assign]
    views[0].set_theme("dark")
    assert calls == ["refresh"]
    assert views[0].theme == "dark"


async def test_opening_another_project_resets_the_chart_scroll(user: User, tmp_path: Path) -> None:
    save_project(Project("別", tasks=[Task("t")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    calls: list[str] = []
    views[0].gantt.reset_scroll = lambda: calls.append("reset")  # type: ignore[method-assign]
    await choose_in_combo(user, "別")
    assert calls == ["reset"]


async def test_editing_a_task_keeps_the_chart_scroll(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    calls: list[str] = []
    views[0].gantt.reset_scroll = lambda: calls.append("reset")  # type: ignore[method-assign]
    views[0].project.tasks.append(Task("追加"))
    views[0].gantt.set_project(views[0].project)  # 編集のあとの再描画
    assert calls == []


async def test_actual_mode_setting_is_applied_and_makes_the_project_dirty(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="open-settings").click()
    user.find(marker="settings-actual-mode").elements.pop().set_value("intervals")
    user.find(marker="settings-apply").click()
    assert view.project.actual_mode is ActualMode.INTERVALS
    assert await wait_until(lambda: view.is_dirty())


async def test_multi_interval_count_counts_tasks_with_two_or_more_actuals(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    two = [Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)), Actual(datetime(2026, 10, 6, 9))]
    view.save_task(None, None, Task("複数", actuals=two))
    view.save_task(None, None, Task("単独", actuals=two[:1]))
    assert view.multi_interval_count() == 1


PNG_BYTES = b"\x89PNG\r\n\x1a\nbody"


class FakeExporter:
    """画像化と保存先の選択の偽物。呼ばれた内容を記録する。"""

    def __init__(self, path: Path | None = None, error: Exception | None = None, available: bool = True) -> None:
        self.path, self.error, self._available = path, error, available
        self.captured: list[float] = []
        self.asked: list[str] = []
        self.asked_types: list[tuple[str, ...]] = []

    @property
    def available(self) -> bool:
        return self._available

    async def capture(self, pixel_ratio: float) -> bytes:
        self.captured.append(pixel_ratio)
        if self.error is not None:
            raise self.error
        return PNG_BYTES

    async def ask_path(self, filename: str, file_types: tuple[str, ...] = ()) -> Path | None:
        self.asked.append(filename)
        self.asked_types.append(file_types)
        return self.path


def mount_preview(base_dir: Path, views: list[MainView], exporter: FakeExporter) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []), exporter)
        views.append(view)
        view.build()


def planned_task() -> Task:
    return Task("設計", planned_start=datetime(2026, 10, 5, 12), planned_end=datetime(2026, 10, 7, 12), project_code="P")


async def open_preview(
    user: User, tmp_path: Path, exporter: FakeExporter, extra: Task | None = None
) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.save_task(None, None, planned_task())
    if extra is not None:
        view.save_task(None, None, extra)
    user.find(marker="export-preview").click()
    return view


def key_event(name: str, keydown: bool = True, ctrl: bool = False, shift: bool = False) -> KeyEventArguments:
    return KeyEventArguments(
        sender=None,  # type: ignore[arg-type]
        client=None,  # type: ignore[arg-type]
        action=KeyboardAction(keydown=keydown, keyup=not keydown, repeat=False),
        key=KeyboardKey(name=name, code=name, location=0),
        modifiers=KeyboardModifiers(alt=False, ctrl=ctrl, meta=False, shift=shift),
    )


async def test_the_preview_replaces_the_header_and_toolbar(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    assert view.preview is not None
    assert not view.header_box.visible  # user.find は、非表示の要素を見つけない
    assert not view.gantt.toolbar.visible
    assert user.find(marker="preview-bar").elements.pop().parent_slot.parent.visible
    assert view.gantt.options.read_only
    await user.should_not_see(marker="add-task-top")


async def test_the_preview_starts_with_the_visible_range_and_the_current_scale(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    settings = view.preview
    assert settings is not None
    assert settings.start == date(2026, 10, 5)
    assert settings.end >= date(2026, 10, 7)
    assert settings.scale is view.gantt.scale
    assert user.find(marker="preview-start").elements.pop().value == "2026-10-05"
    assert user.find(marker="preview-scale").elements.pop().value == view.gantt.scale.value


async def test_back_restores_the_header_toolbar_and_default_options(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-back").click()
    assert view.preview is None
    assert view.header_box.visible
    assert view.gantt.toolbar.visible
    assert view.gantt.options == ViewOptions()


async def test_escape_goes_back(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    view.on_key(key_event("Escape"))
    assert view.preview is None
    assert view.header_box.visible


async def test_other_keys_and_key_releases_do_not_go_back(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    view.on_key(key_event("Enter"))
    view.on_key(key_event("Escape", keydown=False))
    assert view.preview is not None


async def test_escape_does_nothing_outside_the_preview(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    views[0].on_key(key_event("Escape"))
    assert views[0].preview is None
    assert views[0].header_box.visible


async def test_the_filter_survives_the_preview_round_trip(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    view.gantt.set_filter(replace(view.gantt.task_filter, query="設計"))
    user.find(marker="preview-back").click()
    assert view.gantt.task_filter.query == "設計"


async def test_changing_the_settings_updates_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-start").clear().type("2026-10-06")
    assert view.gantt.options.period[0] == date(2026, 10, 6)
    user.find(marker="preview-chips").elements.pop().set_value(False)
    assert view.gantt.options.show_chips is False
    user.find(marker="preview-scale").elements.pop().set_value("週次")
    assert view.gantt.options.scale.value == "週次"
    assert view.gantt.scale.value == "日次"  # ツールバーのスケールは変わらない


async def test_a_bad_period_disables_saving_and_shows_the_reason(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter()
    await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-start").clear().type("2026-12-31")
    user.find(marker="preview-end").clear().type("2026-10-01")
    await user.should_see("開始日が終了日以前")
    assert not user.find(marker="preview-save").elements.pop().enabled
    user.find(marker="preview-end").clear().type("2027-01-31")
    assert user.find(marker="preview-save").elements.pop().enabled
    assert exporter.captured == []


async def test_a_large_image_shows_a_warning_but_can_still_be_saved(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-end").clear().type("2027-12-31")  # 日次で約 450 日 → 16,384px 超(上限 800 日の内側)
    await user.should_see("縮小して保存されます")
    assert user.find(marker="preview-save").elements.pop().enabled
    user.find(marker="preview-end").clear().type("2026-12-31")
    await user.should_not_see("縮小して保存されます")


async def test_save_writes_the_png_and_notifies(user: User, tmp_path: Path) -> None:
    target = tmp_path / "out" / "chart"
    target.parent.mkdir()
    exporter = FakeExporter(path=target)
    await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: (tmp_path / "out" / "chart.png").exists())
    assert (tmp_path / "out" / "chart.png").read_bytes() == PNG_BYTES
    assert exporter.asked == [f"新規プロジェクト_{date.today():%Y%m%d}.png"]
    assert exporter.asked_types == [PNG_FILE_TYPES]
    assert 0 < exporter.captured[0] <= 2.0
    await user.should_see("保存しました")


async def test_cancelling_the_save_dialog_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.glob("*.png"))
    assert view.preview is not None  # プレビューに留まる


async def test_a_capture_failure_is_reported_and_the_preview_stays(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(error=ExportError("boom"))
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    await user.should_see("画像を作れませんでした: boom")
    assert exporter.asked == []  # 保存先は聞かない
    assert view.preview is not None
    assert user.find(marker="preview-save").elements.pop().enabled  # もう一度押せる


async def test_a_write_failure_is_reported_and_leaves_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "missing" / "chart.png")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    await user.should_see("保存できませんでした")
    assert view.preview is not None
    assert not list(tmp_path.rglob("*.tmp"))


async def test_saving_cannot_be_started_twice(user: User, tmp_path: Path) -> None:
    gate = asyncio.Event()

    class SlowExporter(FakeExporter):
        async def capture(self, pixel_ratio: float) -> bytes:
            self.captured.append(pixel_ratio)
            await gate.wait()
            return PNG_BYTES

    exporter = SlowExporter(path=tmp_path / "chart.png")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: exporter.captured != [])
    assert not user.find(marker="preview-save").elements.pop().enabled  # 保存中は押せない
    await view.save_image()  # 直接呼んでも、二重には始まらない
    assert len(exporter.captured) == 1
    gate.set()
    assert await wait_until(lambda: (tmp_path / "chart.png").exists())
    assert user.find(marker="preview-save").elements.pop().enabled


async def test_saving_is_disabled_outside_the_native_window(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter(available=False))
    assert not user.find(marker="preview-save").elements.pop().enabled
    await user.should_see("ネイティブウィンドウでのみ")


async def test_the_default_exporter_is_unavailable_in_tests(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)  # exporter を渡さない = NativeImageExporter
    await user.open("/")
    user.find(marker="export-preview").click()
    assert not user.find(marker="preview-save").elements.pop().enabled


async def test_a_period_that_is_too_long_for_the_scale_is_rejected_without_redrawing(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    before = view.gantt.options
    user.find(marker="preview-start").clear().type("2000-01-01")
    user.find(marker="preview-end").clear().type("2026-12-31")
    await user.should_see("期間が長すぎます")
    assert not user.find(marker="preview-save").elements.pop().enabled
    assert view.gantt.options.period != (date(2000, 1, 1), date(2026, 12, 31))  # 描き直していない
    assert view.gantt.options.period[0] != date(2000, 1, 1)
    assert before is not None


async def test_the_same_long_period_is_allowed_at_a_coarser_scale(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-scale").elements.pop().set_value("月次")
    user.find(marker="preview-start").clear().type("2020-01-01")
    user.find(marker="preview-end").clear().type("2026-12-31")
    assert view.gantt.options.period == (date(2020, 1, 1), date(2026, 12, 31))
    assert user.find(marker="preview-save").elements.pop().enabled


async def test_leaving_and_changing_the_settings_are_ignored_while_saving(user: User, tmp_path: Path) -> None:
    gate = asyncio.Event()

    class SlowExporter(FakeExporter):
        async def capture(self, pixel_ratio: float) -> bytes:
            self.captured.append(pixel_ratio)
            await gate.wait()
            return PNG_BYTES

    exporter = SlowExporter(path=tmp_path / "chart.png")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: exporter.captured != [])
    options = view.gantt.options
    view.exit_preview()
    view.on_key(key_event("Escape"))
    user.find(marker="preview-chips").elements.pop().set_value(False)
    assert view.preview is not None  # 抜けられない
    assert view.gantt.options == options  # 描き直されない(撮っている途中の画面を変えない)
    gate.set()
    assert await wait_until(lambda: (tmp_path / "chart.png").exists())
    assert await wait_until(lambda: not view.saving)
    view.exit_preview()
    assert view.preview is None  # 保存が終われば、抜けられる


def next_year_task() -> Task:
    return Task("来年度の計画", planned_start=datetime(2027, 11, 1), planned_end=datetime(2027, 11, 30))


async def test_a_wide_project_opens_the_preview_at_a_coarser_scale_with_a_notice(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter(), extra=next_year_task())
    assert view.gantt.scale.value == "日次"  # メイン画面のスケールは、そのまま
    assert view.preview is not None and view.preview.scale.value == "週次"
    assert view.gantt.options.scale.value == "週次"
    assert user.find(marker="preview-scale").elements.pop().value == "週次"
    await user.should_see("幅が大きいため、週次で開きました(日次にするには、期間を狭めてください)")


async def test_a_narrow_project_opens_at_the_current_scale_without_a_notice(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    assert view.preview is not None and view.preview.scale is view.gantt.scale
    await user.should_not_see("幅が大きいため")


async def test_the_notice_goes_away_when_the_settings_are_changed(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter(), extra=next_year_task())
    await user.should_see("幅が大きいため")
    user.find(marker="preview-chips").elements.pop().set_value(False)
    await user.should_not_see("幅が大きいため")
    assert view.preview.scale.value == "週次"  # 利用者が選ぶまで、自動では変えない


async def test_the_user_can_go_back_to_the_finer_scale_after_narrowing_the_period(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter(), extra=next_year_task())
    user.find(marker="preview-end").clear().type("2026-12-31")
    user.find(marker="preview-scale").elements.pop().set_value("日次")
    assert view.preview.scale.value == "日次"
    assert view.gantt.options.scale.value == "日次"


async def test_the_native_notice_wins_over_the_scale_notice(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter(available=False), extra=next_year_task())
    await user.should_see("ネイティブウィンドウでのみ")
    await user.should_not_see("幅が大きいため")


async def test_an_empty_project_opens_the_preview_with_a_one_day_period(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    user.find(marker="export-preview").click()
    assert view.preview is not None
    assert view.preview.start == view.preview.end == date(2026, 10, 5)  # タスクがない: 基準日の 1 日
    assert user.find(marker="preview-start").elements.pop().value == "2026-10-05"
    assert user.find(marker="preview-end").elements.pop().value == "2026-10-05"
    assert view.gantt.options.period == (date(2026, 10, 5), date(2026, 10, 5))


async def test_adding_a_task_to_a_collapsed_section_expands_it(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    await user.should_not_see(marker="task-0-0")
    view.save_task(0, None, planned_task())
    assert view.gantt.collapsed == set()
    await user.should_see(marker="task-0-1")


async def test_editing_a_task_keeps_the_section_collapsed(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    view.save_task(0, 0, planned_task())
    assert view.gantt.collapsed == {0}


async def test_adding_a_top_level_task_keeps_collapsed_sections(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    view.save_task(None, None, planned_task())
    assert view.gantt.collapsed == {0}


async def test_opening_a_project_expands_every_section(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元", [planned_task()])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("今の", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    view.open_project("既存")
    assert view.gantt.collapsed == set()
    await user.should_see(marker="task-0-0")


async def test_collapsing_is_not_an_edit(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.mark_clean()
    view.gantt.toggle_section(0)
    assert not view.is_dirty()


async def test_the_preview_shows_a_collapsed_section_and_returns_to_it(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    await user.should_not_see(marker="task-0-0")
    user.find(marker="export-preview").click()
    await user.should_see(marker="task-0-0")
    await user.should_not_see(marker="section-toggle-0")
    view.exit_preview()
    await user.should_not_see(marker="task-0-0")
    assert view.gantt.collapsed == {0}


async def test_the_saved_name_width_is_restored_on_startup(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "name_width": 300}), encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].gantt.name_width == 300
    assert user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px"


async def test_a_bad_saved_name_width_falls_back_to_the_default(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"name_width": "abc"}), encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].gantt.name_width == 200


async def test_changing_the_name_width_saves_it_without_losing_the_theme(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    views[0].set_theme("dark")
    views[0].gantt.handle_name_width({"width": 260})
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved == {"theme": "dark", "name_width": 260}


async def test_the_preview_fits_the_scale_with_the_current_name_width(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    views[0].gantt.handle_name_width({"width": 333})
    seen: list[int] = []
    import projectapp.views as views_module

    original = views_module.fit_scale

    def spy(*args: object, **kwargs: object) -> object:
        seen.append(args[4] if len(args) > 4 else kwargs["name_width"])  # type: ignore[arg-type]
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(views_module, "fit_scale", spy)
    views[0].enter_preview()
    assert seen == [333]


async def test_a_failed_save_of_the_name_width_is_reported_and_does_not_raise(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")

    def failing_save(width: int, base_dir: Path) -> None:
        raise OSError("read-only")

    import projectapp.views as views_module

    monkeypatch.setattr(views_module, "save_name_width", failing_save)
    with views[0].gantt.client:
        views[0].gantt.handle_name_width({"width": 260})
    assert views[0].gantt.name_width == 260  # 画面の幅は、そのまま
    await user.should_see("名前の欄の幅を保存できませんでした")


async def open_handoff_view(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    return view


def assign(view: MainView) -> None:
    view.project.members = [Member("田中", 0.5)]
    view.save_task(None, None, Task("設計", assignees=[Assignee("田中")], planned_start=datetime(2026, 10, 5, 9), effort_hours=3))
    view.mark_clean()


async def test_handoff_needs_members(user: User, tmp_path: Path) -> None:
    await open_handoff_view(user, tmp_path, FakeExporter())
    user.find(marker="export-handoff").click()
    await user.should_see("メンバーが登録されていません")
    await user.should_not_see(marker="handoff-member")


async def test_handoff_needs_the_native_window(user: User, tmp_path: Path) -> None:
    view = await open_handoff_view(user, tmp_path, FakeExporter(available=False))
    assign(view)
    user.find(marker="export-handoff").click()
    await user.should_see("ネイティブウィンドウでのみ、書き出せます")
    await user.should_not_see(marker="handoff-member")


async def test_handoff_disables_export_without_unfinished_tasks(user: User, tmp_path: Path) -> None:
    view = await open_handoff_view(user, tmp_path, FakeExporter())
    view.project.members = [Member("田中", 0.5)]
    user.find(marker="export-handoff").click()
    await user.should_see("終了以外のタスクがありません")
    assert not user.find(marker="handoff-export").elements.pop().enabled


async def test_handoff_writes_todoapp_json_and_keeps_the_project_clean(user: User, tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    exporter = FakeExporter(path=tmp_path / "out" / "todos")
    view = await open_handoff_view(user, tmp_path, exporter)
    assign(view)
    user.find(marker="export-handoff").click()
    await user.should_see("終了以外のタスク: 1 件")
    user.find(marker="handoff-export").click()
    target = tmp_path / "out" / "todos.json"
    assert await wait_until(target.exists)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert [(i["name"], i["schedule_type"], i["estimate_hours"]) for i in data["items"]] == [("設計", "one_time", 6.0)]
    assert exporter.asked == ["todos-田中.json"]
    assert exporter.asked_types == [JSON_FILE_TYPES]
    await user.should_see("1 件を書き出しました")
    assert not view.is_dirty()


async def test_cancelling_the_save_dialog_keeps_the_dialog_open(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    view = await open_handoff_view(user, tmp_path, exporter)
    assign(view)
    user.find(marker="export-handoff").click()
    user.find(marker="handoff-export").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.rglob("todos*.json"))  # holidays.json(祝日のキャッシュ)は別
    await user.should_see(marker="handoff-member")
    assert await wait_until(lambda: user.find(marker="handoff-export").elements.pop().enabled)  # もう一度押せる


async def test_a_write_failure_is_reported_and_the_dialog_stays(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "missing" / "todos.json")
    view = await open_handoff_view(user, tmp_path, exporter)
    assign(view)
    user.find(marker="export-handoff").click()
    user.find(marker="handoff-export").click()
    await user.should_see("保存できませんでした")
    await user.should_see(marker="handoff-member")
    assert await wait_until(lambda: user.find(marker="handoff-export").elements.pop().enabled)


async def open_dashboard_view(user: User, tmp_path: Path, with_task: bool = True) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    view.now = lambda: datetime(2026, 10, 7, 12)
    view.project.base_date = date(2026, 10, 5)
    if with_task:
        view.project.members = [Member("田中", 1.0)]
        view.save_task(
            None,
            None,
            Task(
                "設計",
                assignees=[Assignee("田中")],
                planned_start=datetime(2026, 10, 6, 9),
                planned_end=datetime(2026, 10, 9, 12),
                deadline=datetime(2026, 10, 20, 17),
            ),
        )
    view.mark_clean()
    return view


async def test_the_dashboard_replaces_the_header_and_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    assert view.dashboard_kind == PeriodKind.WEEK
    assert not view.header_box.visible
    assert view.gantt.toolbar is not None and not view.gantt.toolbar.visible
    await user.should_see(marker="dashboard-back")
    await user.should_see(marker="dashboard-progress-percent")


async def test_back_restores_the_header_and_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    user.find(marker="dashboard-back").click()
    assert view.dashboard_kind is None
    assert view.header_box.visible
    assert view.gantt.toolbar is not None and view.gantt.toolbar.visible
    await user.should_not_see(marker="dashboard-back")


async def test_escape_closes_the_dashboard(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.on_key(key_event("Escape"))
    assert view.dashboard_kind is None and view.header_box.visible


async def test_changing_the_period_redraws_with_the_new_period(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-due-0")  # 今週: 10/9 の完了予定だけ(refresh は遅延実行なので、待つ)
    await user.should_not_see(marker="dashboard-due-1")
    user.find(marker="dashboard-period").elements.pop().set_value("今月")
    assert view.dashboard_kind == PeriodKind.MONTH
    await user.should_see(marker="dashboard-due-1")  # 今月: 10/20 の締切も入る


async def test_the_dashboard_leaves_the_chart_state_and_the_project_untouched(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    view.gantt.set_scale(Scale.WEEK)
    view.gantt.set_filter(TaskFilter(query="設"))
    user.find(marker="open-dashboard").click()
    user.find(marker="dashboard-back").click()
    assert view.gantt.scale == Scale.WEEK
    assert view.gantt.task_filter.query == "設"
    assert not view.is_dirty()


async def test_an_empty_project_shows_the_empty_messages(user: User, tmp_path: Path) -> None:
    await open_dashboard_view(user, tmp_path, with_task=False)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-empty-progress")
    await user.should_see(marker="dashboard-empty-due")


async def test_the_dashboard_and_the_preview_do_not_open_together(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="export-preview").click()
    view.open_dashboard()
    assert view.dashboard_kind is None
    view.exit_preview()
    user.find(marker="open-dashboard").click()
    view.enter_preview()
    assert view.preview is None


async def open_header_view(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    return views[0]


def menu_items(user: User, menu_marker: str) -> list[tuple[str, str]]:
    """メニューの項目(文言, マーカー)を、並んだ順に返す。"""
    menu = user.find(marker=menu_marker).elements.pop()
    return [
        (child.default_slot.children[0].text, next(iter(child._markers)))  # 文言は、項目の中の ItemSection
        for child in menu.default_slot.children
        if isinstance(child, ui.menu_item)
    ]


async def test_the_header_has_the_menus_the_dashboard_icon_and_the_theme_menu(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    for marker in ("menu-file", "menu-project", "menu-export", "menu-help", "open-dashboard", "menu-theme"):
        await user.should_see(marker=marker)
    await user.should_see("新規プロジェクト")  # タイトル


async def test_the_menus_list_their_items_in_order(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    assert menu_items(user, "menu-file-items") == [
        ("開く", "file-open"),
        ("上書き保存", "save-project"),
        ("名前をつけて保存", "file-save-as"),
        ("祝日を更新", "refresh-holidays"),
    ]
    assert menu_items(user, "menu-project-items") == [
        ("新規プロジェクト作成", "file-new"),
        ("設定", "open-settings"),
        ("メンバー", "open-members"),
    ]
    assert menu_items(user, "menu-export-items") == [
        ("チャートプレビュー", "export-preview"),
        ("担当者へ書き出し", "export-handoff"),
    ]
    assert menu_items(user, "menu-help-items") == [("ショートカットヘルプ", "help-shortcuts")]
    assert menu_items(user, "menu-theme-items") == [("自動", "theme-auto"), ("ライト", "theme-light"), ("ダーク", "theme-dark")]


async def test_the_file_menu_opens_the_file_list(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    user.find(marker="file-open").click()
    await user.should_see("プロジェクトファイルがありません")


async def test_the_help_menu_opens_the_shortcut_help(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    user.find(marker="help-shortcuts").click()
    await user.should_see("キー操作")
    await user.should_see("Ctrl/Cmd+S: 上書き保存")


async def test_the_theme_menu_marks_the_selected_theme_and_switches_it(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)

    def selected() -> list[str]:
        return [t for t in ("auto", "light", "dark") if user.find(marker=f"theme-{t}").elements.pop()._props.get("active")]

    def icon() -> str:
        return user.find(marker="menu-theme").elements.pop()._props["icon"]

    assert selected() == ["auto"] and icon() == THEME_ICONS["auto"]
    user.find(marker="theme-dark").click()
    assert view.theme == "dark"
    assert await wait_until(lambda: selected() == ["dark"] and icon() == THEME_ICONS["dark"])  # refresh は遅延実行


async def test_the_header_is_a_themed_band_with_small_fonts(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)
    assert "app-header" in view.header_box.classes
    assert isinstance(view.header_box, ui.header)  # 画面の上端・左右いっぱいに固定される四角い帯(ページの余白の内側に置かない)
    band_rule = next(line for line in HEADER_CSS.splitlines() if line.startswith(".app-header {"))
    assert "border-radius" not in band_rule  # 角丸にしない
    # 折り返さない: 帯・タイトル・メニューのボタンは 1 行のまま。狭いときに縮むのは、プロジェクト選択のコンボだけ
    assert "no-wrap" in view.header_box.classes and "flex-wrap: nowrap" in band_rule
    nowrap_rule = next(line for line in HEADER_CSS.splitlines() if line.startswith(".app-header .q-btn {"))
    assert "white-space: nowrap" in nowrap_rule and "flex: none" in nowrap_rule  # メニューのボタンは、縮めも折り返しもしない
    assert ".app-header .q-btn__content" in HEADER_CSS
    select = user.find(marker="project-select").elements.pop()
    assert "app-project-select" in select.classes and "w-64" not in select.classes  # 固定幅(16rem)をやめ、縮められるようにする
    select_rule = next(line for line in HEADER_CSS.splitlines() if line.startswith(".app-header .app-project-select {"))
    assert "flex: 0 1 16rem" in select_rule and "min-width" in select_rule
    # コンボの中に出るファイル名は 10px(選択中の値と、開いた一覧の項目)
    assert "app-select-popup" in str(select._props.get("popup-content-class"))
    value_rule = next(line for line in HEADER_CSS.splitlines() if ".q-field__native" in line)
    assert "font-size: 10px" in value_rule
    popup_rule = next(line for line in HEADER_CSS.splitlines() if line.startswith(".app-select-popup"))
    assert "font-size: 10px" in popup_rule
    assert "font-size: 12px" in HEADER_CSS  # 14px から -2
    assert "var(--q-primary)" in HEADER_CSS and "color: #fff" in HEADER_CSS  # テーマカラーの背景 + 白文字
    assert "body.body--dark .app-header" in HEADER_CSS and "color-mix" in HEADER_CSS  # ダークは暗めのテーマカラー
    title = next(e for e in user.find(kind=ui.label, content="新規プロジェクト").elements if e.text == "新規プロジェクト")  # ヘルプの「新規プロジェクト作成」と区別する
    assert "app-title" in title.classes
    assert not any(node is view.header_box for node in ancestors(title))  # タイトルは、ヘッダーの外(メイン側の左上)
    title_rule = next(line for line in HEADER_CSS.splitlines() if line.startswith(".app-title {"))
    assert "font-size: 12px" in title_rule and "font-weight: 700" in title_rule  # 他の文字と同じ大きさ。太さで区別する
    for marker in ("menu-file", "menu-project", "menu-export", "menu-help"):  # メニューは楕円型のボタン
        button = user.find(marker=marker).elements.pop()
        assert "rounded" in button._props and "unelevated" in button._props and "app-menu-btn" in button.classes
    assert "rgba(255, 255, 255, 0.18)" in HEADER_CSS and ".app-menu-btn:hover" in HEADER_CSS
    # 帯の上のボタンは、色を持たない(NiceGUI の既定は primary で、flat の文字が帯と同じ色になって見えなくなる)。
    # 色を持たなければ、文字は帯の白を引き継ぐ
    for marker in ("menu-file", "menu-project", "menu-export", "menu-help", "open-dashboard", "open-folder", "menu-theme"):
        assert not user.find(marker=marker).elements.pop()._props.get("color"), marker
    for marker in ("menu-file", "menu-project", "menu-export", "menu-help"):
        assert "icon-right" not in user.find(marker=marker).elements.pop()._props  # ▼ は出さない
    menu = user.find(marker="menu-file-items").elements.pop()
    assert "app-menu" in str(menu._props.get("content-class"))  # 開いたメニューも同じ大きさ


async def test_the_floating_buttons_are_gone(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    await user.should_not_see(kind=ui.page_sticky)
    await user.should_not_see(kind=ui.fab)


def ancestors(element: ui.element) -> list[ui.element]:
    nodes: list[ui.element] = []
    while element.parent_slot is not None and element.parent_slot.parent is not None:
        element = element.parent_slot.parent
        nodes.append(element)
    return nodes


async def test_the_menus_start_at_the_left_of_the_header_and_the_title_is_in_the_main_area(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)
    order = ["menu-file", "menu-project", "menu-export", "menu-help", "project-select", "open-dashboard", "open-folder", "menu-theme"]
    ids = [user.find(marker=marker).elements.pop().id for marker in order]
    assert ids == sorted(ids)  # 左から、メニュー 4 つ。右側に、コンボ・ダッシュボード・テーマ
    header_children = view.header_box.default_slot.children
    assert isinstance(header_children[0], ui.button)  # 先頭は、メニューのボタン(タイトルではない)
    title = next(e for e in user.find(kind=ui.label, content="新規プロジェクト").elements if e.text == "新規プロジェクト")  # ヘルプの「新規プロジェクト作成」と区別する
    assert view.header_box not in ancestors(title)


async def test_the_title_hides_and_returns_with_the_header(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    assert not view.header_box.visible and not view.title_box.visible
    user.find(marker="dashboard-back").click()
    assert view.header_box.visible and view.title_box.visible
    user.find(marker="export-preview").click()
    assert not view.header_box.visible and not view.title_box.visible
    view.exit_preview()
    assert view.header_box.visible and view.title_box.visible


async def test_the_folder_button_opens_the_project_folder(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)
    opened: list[Path] = []
    view.open_folder = opened.append  # type: ignore[method-assign]  # 実際には、ファイラを開かない
    await user.should_see(marker="open-folder")
    user.find(marker="open-folder").click()
    assert opened == [tmp_path]


async def test_the_folder_button_reports_a_failure(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)

    def fail(path: Path) -> None:
        raise FileNotFoundError("xdg-open")

    view.open_folder = fail  # type: ignore[method-assign]
    user.find(marker="open-folder").click()
    await user.should_see("フォルダを開けませんでした")


async def open_saved_view(user: User, tmp_path: Path) -> MainView:
    """「甲」(セクション「甲の中身」)を保存してから、開いた状態のメイン画面を返す。"""
    save_cache({}, tmp_path)
    save_project(Project("甲", sections=[Section("甲の中身")]), tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    views[0].request_open("甲")
    assert views[0].path == tmp_path / "甲.json"
    return views[0]


async def test_new_project_replaces_the_current_one_with_an_unsaved_empty_project(user: User, tmp_path: Path) -> None:
    view = await open_saved_view(user, tmp_path)
    user.find(marker="file-new").click()
    assert view.path is None and view.project.name == "新規プロジェクト"
    assert view.project.sections == [] and not view.is_dirty()
    assert view.file_select.value is None
    assert (tmp_path / "甲.json").exists()  # 新規作成では、ファイルを作らない・消さない
    await user.should_see("新規プロジェクト")


async def test_new_project_asks_before_dropping_unsaved_changes(user: User, tmp_path: Path) -> None:
    view = await open_saved_view(user, tmp_path)
    view.save_section("追加")
    assert view.is_dirty()
    user.find(marker="file-new").click()
    await user.should_see("保存されていない変更があります")
    await user.should_see("作成前に")
    user.find(marker="unsaved-cancel").click()
    assert view.path == tmp_path / "甲.json" and [s.name for s in view.project.sections] == ["甲の中身", "追加"]


async def test_new_project_can_discard_the_changes(user: User, tmp_path: Path) -> None:
    view = await open_saved_view(user, tmp_path)
    view.save_section("追加")
    user.find(marker="file-new").click()
    user.find(marker="unsaved-discard").click()
    assert view.path is None and view.project.sections == []
    assert [s.name for s in load_project(tmp_path / "甲.json").sections] == ["甲の中身"]  # 保存せず作成


async def test_new_project_can_save_first(user: User, tmp_path: Path) -> None:
    view = await open_saved_view(user, tmp_path)
    view.save_section("追加")
    user.find(marker="file-new").click()
    user.find(marker="unsaved-save").click()
    assert await wait_until(lambda: view.path is None and view.project.sections == [])
    assert [s.name for s in load_project(tmp_path / "甲.json").sections] == ["甲の中身", "追加"]


async def test_save_as_writes_a_new_file_and_switches_to_it(user: User, tmp_path: Path) -> None:
    view = await open_saved_view(user, tmp_path)
    view.save_section("追加")
    user.find(marker="file-save-as").click()
    name = user.find(marker="project-name").elements.pop()
    assert name.value == "甲"  # 初期値は、現在の名前
    user.find(marker="project-name").clear().type("乙")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "乙.json")
    assert view.project.name == "乙" and not view.is_dirty()
    assert [s.name for s in load_project(tmp_path / "乙.json").sections] == ["甲の中身", "追加"]
    assert [s.name for s in load_project(tmp_path / "甲.json").sections] == ["甲の中身"]  # 元のファイルは、そのまま
    assert "乙" in view.file_select.options and view.file_select.value == "乙"


async def test_save_as_does_not_overwrite_an_existing_project(user: User, tmp_path: Path) -> None:
    view = await open_saved_view(user, tmp_path)
    save_project(Project("乙"), tmp_path)
    user.find(marker="file-save-as").click()
    user.find(marker="project-name").clear().type("乙")
    user.find(marker="name-save").click()
    await user.should_see("同じ名前のプロジェクトがすでにあります")
    assert view.path == tmp_path / "甲.json" and view.project.name == "甲"
    assert load_project(tmp_path / "乙.json").sections == []


async def test_save_as_works_for_an_unsaved_project_too(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    user.find(marker="file-save-as").click()
    user.find(marker="project-name").clear().type("丙")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: views[0].path == tmp_path / "丙.json")


async def test_the_file_menu_has_a_separator_before_the_holiday_update(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    menu = user.find(marker="menu-file-items").elements.pop()
    kinds = [type(child).__name__ for child in menu.default_slot.children]
    assert kinds == ["MenuItem", "MenuItem", "MenuItem", "Separator", "MenuItem"]  # 開く・保存・名前をつけて保存 | 祝日を更新
    assert "menu-file-separator" in menu.default_slot.children[3]._markers
    assert "refresh-holidays" in menu.default_slot.children[4]._markers


async def test_templates_are_saved_with_the_project_and_mark_it_dirty(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="open-settings").click()
    user.find(marker="settings-template-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-template-0-name").type("チケット")
    user.find(marker="settings-template-0-pattern").type("https://example.com/{ID}")
    user.find(marker="settings-apply").click()
    assert await wait_until(lambda: view.is_dirty())
    await save_new_as(user, "テンプレート")
    assert await wait_until(lambda: (tmp_path / "テンプレート.json").exists())
    loaded = load_project(tmp_path / "テンプレート.json")
    assert loaded.url_templates == [UrlTemplate("チケット", "https://example.com/{ID}")]


async def test_deleting_a_used_template_turns_its_links_into_urls(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.url_templates = [UrlTemplate("チケット", "https://example.com/{ID}")]
    view.save_task(None, None, Task("設計", urls=[TaskUrl("課題", "チケット", {"ID": "231"})]))
    user.find(marker="open-settings").click()
    user.find(marker="settings-template-0-remove").click()
    user.find(marker="settings-apply").click()
    await user.should_see("1件")
    user.find(marker="settings-confirm-delete").click()
    assert view.project.url_templates == []
    assert view.project.tasks[0].urls == [TaskUrl("課題", None, {"URL": "https://example.com/231"})]


async def test_renaming_a_template_follows_the_links(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.url_templates = [UrlTemplate("チケット", "https://example.com/{ID}")]
    view.save_task(None, None, Task("設計", urls=[TaskUrl("", "チケット", {"ID": "1"})]))
    user.find(marker="open-settings").click()
    user.find(marker="settings-template-0-name").clear().type("課題")
    user.find(marker="settings-apply").click()
    assert view.project.tasks[0].urls[0].template == "課題"


SHORTCUT_METHODS = [
    (key_args, method)
    for key_args, method in [
        (("s", True, False), "save_project_clicked"),
        (("S", True, True), "save_as"),
        (("o", True, False), "show_file_list"),
        (("n", True, False), "request_new"),
        ((",", True, False), "open_settings"),
        (("e", True, False), "open_handoff"),
        (("p", True, False), "enter_preview"),
        (("d", False, False), "open_dashboard"),
    ]
]


async def shortcut_view(user: User, tmp_path: Path) -> tuple[MainView, list[str]]:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view, calls = views[0], []
    for _, method in SHORTCUT_METHODS:
        setattr(view, method, lambda method=method: calls.append(method))
    view.gantt.focus_search = lambda: calls.append("focus_search")
    return view, calls


@pytest.mark.parametrize(("key_args", "method"), SHORTCUT_METHODS)
async def test_a_shortcut_runs_its_menu_action(user: User, tmp_path: Path, key_args, method) -> None:
    view, calls = await shortcut_view(user, tmp_path)
    name, ctrl, shift = key_args
    view.on_key(key_event(name, ctrl=ctrl, shift=shift))
    assert calls == [method]


async def test_slash_focuses_the_search_input_and_question_mark_opens_the_help(user: User, tmp_path: Path) -> None:
    view, calls = await shortcut_view(user, tmp_path)
    view.on_key(key_event("/"))
    assert calls == ["focus_search"]
    view.on_key(key_event("?", shift=True))
    assert view.help_dialog.value


async def test_shortcuts_do_nothing_while_a_dialog_is_open(user: User, tmp_path: Path) -> None:
    view, calls = await shortcut_view(user, tmp_path)
    view.help_dialog.open()
    view.on_key(key_event("s", ctrl=True))
    view.on_key(key_event("d"))
    assert calls == []


async def test_shortcuts_do_nothing_in_the_preview_and_the_dashboard(user: User, tmp_path: Path) -> None:
    view, calls = await shortcut_view(user, tmp_path)
    view.preview = object()  # type: ignore[assignment]
    view.on_key(key_event("s", ctrl=True))
    view.preview = None
    view.dashboard_kind = PeriodKind.WEEK
    view.on_key(key_event("d"))
    assert calls == []


async def test_key_releases_do_not_run_shortcuts(user: User, tmp_path: Path) -> None:
    view, calls = await shortcut_view(user, tmp_path)
    view.on_key(key_event("s", keydown=False, ctrl=True))
    assert calls == []


async def test_the_help_dialog_lists_the_shortcuts(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].help_dialog.open()
    await user.should_see("Ctrl/Cmd+S: 上書き保存")
    await user.should_see("?: ショートカットヘルプ")


# --- 画面の拡大・縮小(Ctrl/Cmd + `+` / `-` / `0`) ---


def zoom_calls(calls: list[str]) -> list[str]:
    return [c for c in calls if "style.zoom" in c]


async def open_zoom_view(user: User, tmp_path: Path, exporter: FakeExporter | None = None) -> tuple[MainView, list[str]]:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    calls: list[str] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, make_transport(200, []), exporter or FakeExporter())
        view.run_js = lambda script, **_: calls.append(script)  # ブラウザの偽物
        views.append(view)
        view.build()

    await user.open("/")
    return views[0], calls


async def test_the_zoom_starts_at_100_percent_and_applies_it(user: User, tmp_path: Path) -> None:
    view, calls = await open_zoom_view(user, tmp_path)
    assert view.zoom == 100
    assert zoom_calls(calls) == ["document.body.style.zoom = 1.0"]


async def test_the_saved_zoom_is_restored_on_startup(user: User, tmp_path: Path) -> None:
    save_zoom(130, tmp_path)
    view, calls = await open_zoom_view(user, tmp_path)
    assert view.zoom == 130
    assert zoom_calls(calls) == ["document.body.style.zoom = 1.3"]


async def test_ctrl_plus_and_minus_zoom_in_and_out_and_save_it(user: User, tmp_path: Path) -> None:
    view, calls = await open_zoom_view(user, tmp_path)
    view.on_key(key_event("+", ctrl=True, shift=True))
    view.on_key(key_event("=", ctrl=True))
    assert view.zoom == 120
    view.on_key(key_event("-", ctrl=True))
    assert view.zoom == 110
    assert zoom_calls(calls)[-1] == "document.body.style.zoom = 1.1"
    assert load_zoom(tmp_path) == 110
    view.on_key(key_event("0", ctrl=True))
    assert (view.zoom, load_zoom(tmp_path)) == (100, 100)


async def test_the_zoom_stops_at_the_limits(user: User, tmp_path: Path) -> None:
    view, _ = await open_zoom_view(user, tmp_path)
    for _ in range(20):
        view.on_key(key_event("+", ctrl=True, shift=True))
    assert view.zoom == 200
    for _ in range(30):
        view.on_key(key_event("-", ctrl=True))
    assert view.zoom == 70


async def test_the_zoom_works_while_a_dialog_is_open_and_in_the_preview(user: User, tmp_path: Path) -> None:
    view, _ = await open_zoom_view(user, tmp_path)
    view.help_dialog.open()
    view.on_key(key_event("+", ctrl=True, shift=True))
    assert view.zoom == 110
    view.help_dialog.close()
    view.enter_preview()
    view.on_key(key_event("-", ctrl=True))
    assert view.zoom == 100


async def test_a_zoom_that_cannot_be_saved_still_applies_and_warns(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _ = await open_zoom_view(user, tmp_path)

    def fail(*_: object) -> None:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.save_zoom", fail)
    view.on_key(key_event("+", ctrl=True, shift=True))
    assert view.zoom == 110
    await user.should_see("倍率を保存できませんでした")


class ZoomSpyExporter(FakeExporter):
    """画像化の瞬間の、画面の倍率を記録する偽物。"""

    def __init__(self, calls: list[str]) -> None:
        super().__init__()
        self.calls = calls
        self.zoom_at_capture: str | None = None

    async def capture(self, pixel_ratio: float) -> bytes:
        self.zoom_at_capture = zoom_calls(self.calls)[-1]
        return await super().capture(pixel_ratio)


async def test_the_image_is_captured_at_100_percent_and_the_zoom_comes_back(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    exporter = ZoomSpyExporter(calls)
    save_zoom(150, tmp_path)
    view, view_calls = await open_zoom_view(user, tmp_path, exporter)
    exporter.calls = view_calls
    view.enter_preview()
    await view.save_image()
    assert exporter.zoom_at_capture == "document.body.style.zoom = 1.0"  # 倍率をかけたままだと、画像の大きさがずれる
    assert zoom_calls(view_calls)[-1] == "document.body.style.zoom = 1.5"
    assert view.zoom == 150


async def test_assigned_count_counts_tasks_where_the_member_is_one_of_the_assignees(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks = [
        Task("a", assignees=[Assignee("田中"), Assignee("鈴木")]),
        Task("b", assignees=[Assignee("鈴木")]),
        Task("c"),
    ]
    assert view.assigned_count("田中") == 1
    assert view.assigned_count("鈴木") == 2
    assert view.assigned_count("佐藤") == 0


async def test_renaming_a_member_renames_every_assignee_entry(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("A"), Member("B")]
    view.project.tasks = [Task("t", assignees=[Assignee("A", 0.5), Assignee("B", 0.25)])]
    view.apply_members([Member("B"), Member("A")], {"A": "B", "B": "A"})  # 入れ替え
    assert view.project.tasks[0].assignees == [Assignee("B", 0.5), Assignee("A", 0.25)]


async def test_saving_a_task_warns_for_each_overloaded_assignee(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中"), Member("鈴木")]

    def task(name: str, start: int, end: int) -> Task:
        return Task(
            name,
            planned_start=datetime(2026, 10, start),
            planned_end=datetime(2026, 10, end),
            assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.6)],
        )

    view.save_task(None, None, task("a", 5, 9))
    view.save_task(None, None, task("b", 7, 12))
    await user.should_see("田中 の割り当てが最大120%になる期間があります")
    await user.should_see("鈴木 の割り当てが最大120%になる期間があります")
