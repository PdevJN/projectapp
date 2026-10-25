from copy import deepcopy
import asyncio
import gc
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.config import load_project_dir, load_zoom, save_project_dir, save_zoom
from projectapp.calendar import DayKind, save_cache
from projectapp.filtering import TaskFilter
from projectapp.gantt import KIND_COLORS
from projectapp.forms import build_task
from projectapp.handoff import JSON_FILE_TYPES
from projectapp.categories import CategoryEdit
from projectapp.models import Assignee, Actual, ActualMode, Category, Event, Level, Member, Parameter, Project, Section, Task, TaskKind, TaskUrl, UrlTemplate, WorkDay, union_assignees
from projectapp.storage import load_project, save_project
from nicegui.events import KeyboardAction, KeyboardKey, KeyboardModifiers, KeyEventArguments

from projectapp.decompose import Part
from projectapp.export import PNG_FILE_TYPES, ExportError
from projectapp.plantuml import PLANTUML_FILE_TYPES
from projectapp.puml_import import PLANTUML_OPEN_FILE_TYPES
from projectapp.dashboard import PeriodKind
from projectapp.timeline import Scale, Schedule, effective_end, visible_range
from projectapp.gantt import ViewOptions
from projectapp.forms import MEMBER_TABLE_CSS
from projectapp.config import load_custom_theme, load_theme, save_custom_theme
from projectapp.theme import DEFAULTS, CustomTheme
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


def edit_from_menu(user: User, row_marker: str) -> None:
    """行を右クリックして、メニューの`編集`を押す(左クリックでは編集を開かない)。"""
    row = user.find(marker=row_marker).elements.pop()
    [listener] = [l for l in row._event_listeners.values() if l.type == "contextmenu"]
    listener.handler()
    user.find(marker="context-edit").click()


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
    edit_from_menu(user, "row-0-0")
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
    edit_from_menu(user, "row-top-0")
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
    view.save_task((), None, Task("a"))
    view.save_task((), 0, Task("b"))
    view.save_section("開発")
    view.save_task((0,), None, Task("x"))
    view.save_task((0,), 0, Task("y"))
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
    views[0].save_task((), None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    assert views[0].project.tasks[0].planned_end is None  # 完了予定は保存せず、その都度計算する
    await user.should_see(marker="bar-top-0")


async def test_a_task_with_only_a_start_shows_a_one_day_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].save_task((), None, Task("a", planned_start=datetime(2026, 10, 9, 9)))
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
    view.save_task((), None, Task("自動", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
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
    view.delete_task((), 0)
    assert [t.name for t in view.project.tasks] == ["b"]
    assert [t.name for t in view.project.sections[0].tasks] == ["x", "y"]
    view.delete_task((0,), 1)
    assert [t.name for t in view.project.sections[0].tasks] == ["x"]
    assert [t.name for t in view.project.tasks] == ["b"]
    assert view.is_dirty()


async def test_delete_task_keeps_the_summary_consistent(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(
        Project("既存", tasks=[
            Task("m", id="m", kind=TaskKind.SUMMARY, children=["a", "b"]), Task("a", id="a"), Task("b", id="b"),
        ]),
        tmp_path,
    )
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.delete_task((), 1)
    assert view.project.tasks[0].children == ["b"]
    view.delete_task((), 1)
    assert view.project.tasks[0].kind is TaskKind.NORMAL


async def test_decompose_task_makes_a_summary_in_one_undo_step(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("開発", [Task("実装", effort_hours=4.0)])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.apply_decompose((0,), 0, [Part("a", 2.0), Part("b", 2.0)], True, False)
    assert [t.name for t in view.project.sections[0].tasks] == ["実装", "a", "b"]
    assert view.is_dirty()
    view.undo()
    assert [t.name for t in view.project.sections[0].tasks] == ["実装"]
    assert view.project.sections[0].tasks[0].kind is TaskKind.NORMAL


async def open_edit_dialog_of_the_only_task(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("開発", [Task("実装", effort_hours=4.0)])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="task-0-0")
    edit_from_menu(user, "row-0-0")
    return view


def open_dialog_count(view: MainView) -> int:
    return sum(1 for e in view.client.elements.values() if isinstance(e, ui.dialog) and e.value)


async def test_decompose_stacks_over_the_edit_dialog_and_closes_both_on_success(user: User, tmp_path: Path) -> None:
    view = await open_edit_dialog_of_the_only_task(user, tmp_path)
    user.find(marker="task-decompose").click()
    assert open_dialog_count(view) == 2  # 閉じて開くと画面が一瞬消えるので、編集は開いたまま分解を重ねる
    user.find(marker="decompose-apply").click()
    assert [t.kind for t in view.project.sections[0].tasks][0] is TaskKind.SUMMARY
    assert len(view.project.sections[0].tasks) == 3
    assert open_dialog_count(view) == 0


async def test_cancelling_the_decompose_dialog_returns_to_the_edit_dialog(user: User, tmp_path: Path) -> None:
    view = await open_edit_dialog_of_the_only_task(user, tmp_path)
    user.find(marker="task-decompose").click()
    user.find(marker="decompose-cancel").click()
    assert open_dialog_count(view) == 1
    assert len(view.project.sections[0].tasks) == 1


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
    view.delete_task((), 0)
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
    edit_from_menu(user, "row-top-0")  # a を開く: 後続の b と自分は候補から外れる
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
    view.shift_task((), 1, -30)  # 大きく左へ
    assert view.project.tasks[1].planned_start == datetime(2026, 10, 6, 9)  # 先行の完了の日まで


async def test_delete_from_the_edit_dialog_removes_the_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-task-top").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see(marker="task-top-0")
    edit_from_menu(user, "row-top-0")
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
    view.save_task((), None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
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
    view.save_task((), None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
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


async def open_members_parameters(user: User) -> None:
    user.find(marker="open-members-parameters").click()
    await user.should_see(marker="members-parameters-panels")


async def test_the_shortcut_opens_the_members_parameters_dialog_once(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    with view.client:  # ダイアログを作るので、ページのコンテキストの中で呼ぶ
        view.on_key(key_event("m", ctrl=True, shift=True))
    await user.should_see(marker="members-parameters-panels")
    with view.client:
        view.on_key(key_event("m", ctrl=True, shift=True))  # 開いているあいだは、二重に開かない
    assert len(user.find(marker="members-parameters-panels").elements) == 1


async def test_the_members_parameters_dialog_opens_on_the_members_tab(user: User, tmp_path: Path) -> None:
    await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    panels = user.find(marker="members-parameters-panels").elements.pop()
    assert panels.value == "members"
    await user.should_see(marker="tab-members")
    await user.should_see(marker="tab-parameters")


async def test_the_tab_panels_do_not_shrink_so_the_card_scrolls_in_a_short_window(user: User, tmp_path: Path) -> None:
    await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    panels = user.find(marker="members-parameters-panels").elements.pop()
    # 縮むと、はみ出た分は overflow: hidden で切れて、2つ目以降のパラメータや段階に届かない(2026-10-11 に実機で見つけた)
    assert panels._style["flex-shrink"] == "0"


async def test_applying_the_members_tab_keeps_the_dialog_open(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["田中"])
    await user.should_see(marker="members-parameters-panels")  # 閉じない
    first = user.find(marker="member-name-0").elements.pop()
    assert await wait_until(lambda: user.find(marker="member-name-0").elements.pop() is not first)  # 行の作り直しを待つ
    user.find(marker="member-name-0").clear().type("田中太郎")  # 続けて適用できる(改名は 1 回分)
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["田中太郎"])


async def test_applying_parameters_rebuilds_the_member_columns_and_keeps_unapplied_member_edits(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")  # 未適用
    user.find(marker="parameter-add").click()
    await user.should_see(marker="parameter-name-0")
    user.find(marker="parameter-name-0").type("経験")
    user.find(marker="level-add-0").click()
    await user.should_see(marker="level-name-0-0")
    user.find(marker="level-name-0-0").type("上級")
    user.find(marker="level-value-0-0").clear().type("20")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: [p.name for p in view.project.parameters] == ["経験"])
    await user.should_see(marker="member-level-0-0")  # メンバーの表に、パラメータの列ができる
    await user.should_see(marker="member-effective-0")
    assert view.project.members == []  # メンバーは、まだ適用していない
    assert user.find(marker="member-name-0").elements.pop().value == "田中"


async def test_a_parameter_rename_carries_over_to_unapplied_member_rows(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2), Level("初級", -0.1)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"}, "m1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-name-0").clear().type("田中A")  # 未適用の編集
    user.find(marker="parameter-name-0").clear().type("経験値")
    user.find(marker="level-delete-0-1").click()  # 「初級」を削除(選んでいるメンバーはいない)
    await user.should_see(marker="level-add-0")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters[0].name == "経験値")
    assert view.project.members[0].levels == {"経験値": "上級"}
    assert user.find(marker="member-level-0-0").elements.pop().value == "上級"  # 未適用の行も追従する
    assert user.find(marker="member-name-0").elements.pop().value == "田中A"


async def test_the_tabs_show_a_mark_while_they_have_unapplied_edits(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    members_mark = user.find(marker="members-dirty").elements.pop()
    parameters_mark = user.find(marker="parameters-dirty").elements.pop()
    assert members_mark.text == "" and parameters_mark.text == ""
    user.find(marker="member-add").click()
    assert await wait_until(lambda: members_mark.text == "●")
    assert parameters_mark.text == ""
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: members_mark.text == "")
    assert view.project.members[0].name == "田中"
    user.find(marker="parameter-add").click()
    assert await wait_until(lambda: parameters_mark.text == "●")


async def settle() -> None:
    """未適用の印のタイマー(0.3 秒)が、少なくとも 1 回回るのを待つ。"""
    await asyncio.sleep(0.8)


def with_experience(view: MainView) -> None:
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2), Level("初級", -0.1)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"}, "m1")]
    view.mark_clean()


async def test_a_parameter_rename_and_delete_do_not_mark_the_members_tab_as_edited(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    with_experience(view)
    await open_members_parameters(user)
    members_mark = user.find(marker="members-dirty").elements.pop()
    user.find(marker="parameter-name-0").clear().type("経験値")
    user.find(marker="level-name-0-0").clear().type("エキスパート")  # 「上級」の改名
    user.find(marker="level-delete-0-1").click()  # 「初級」の削除
    await user.should_see(marker="level-add-0")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters[0].name == "経験値")
    assert view.project.members[0].levels == {"経験値": "エキスパート"}
    await settle()
    assert members_mark.text == ""  # メンバーの表は、プロジェクトに追従しただけで、編集ではない


async def test_a_parameter_apply_keeps_the_mark_of_a_real_member_edit(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    with_experience(view)
    await open_members_parameters(user)
    members_mark = user.find(marker="members-dirty").elements.pop()
    user.find(marker="member-name-0").clear().type("田中A")
    user.find(marker="parameter-name-0").clear().type("経験値")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters[0].name == "経験値")
    await settle()
    assert members_mark.text == "●"  # 名前の編集は、まだ適用していない


async def test_applying_members_uses_the_applied_parameters_not_the_unapplied_ones(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    with_experience(view)
    await open_members_parameters(user)
    parameters_mark = user.find(marker="parameters-dirty").elements.pop()
    user.find(marker="parameter-name-0").clear().type("経験値")  # 未適用
    user.find(marker="member-name-0").clear().type("田中A")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].name == "田中A")
    assert view.project.parameters[0].name == "経験"  # パラメータは、適用していない
    assert view.project.members[0].levels == {"経験": "上級"}  # 選択も、適用済みの定義のまま
    await settle()
    assert parameters_mark.text == "●"  # パラメータのタブの編集は、残る


async def test_applying_members_twice_renames_the_assigned_tasks_once_each(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0, {}, "m1")]
    view.project.tasks = [Task("a", assignees=[Assignee("田中")])]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-name-0").clear().type("田中A")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignees[0].name == "田中A")
    first = user.find(marker="member-name-0").elements.pop()
    assert await wait_until(lambda: user.find(marker="member-name-0").elements.pop() is not first)  # 行の作り直しを待つ
    user.find(marker="member-name-0").clear().type("田中B")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignees[0].name == "田中B")
    assert [m.id for m in view.project.members] == ["m1"]  # id は変わらない
    assert view.project.members[0].name == "田中B"


async def test_cancel_closes_the_dialog_and_discards_unapplied_edits(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")
    dialog = next(a for a in user.find(marker="members-parameters-panels").elements.pop().ancestors() if isinstance(a, ui.dialog))
    user.find(marker="members-parameters-cancel").click()
    assert not dialog.value
    assert view.project.members == []
    assert not view.is_dirty()


async def test_the_members_dialog_adds_a_member(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
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
    await open_members_parameters(user)
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
    await open_members_parameters(user)
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
    await open_members_parameters(user)
    user.find(marker="member-name-0").clear().type("田中太郎")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignee_names == ["田中太郎"])
    assert [t.assignee_names for t in view.project.tasks] == [["田中太郎"], ["鈴木"], []]
    assert [m.name for m in view.project.members] == ["田中太郎", "鈴木"]


async def test_a_member_with_tasks_cannot_be_deleted(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.project.tasks = [Task("a", assignees=[Assignee("田中")])]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-delete-0").click()
    user.find(marker="member-apply").click()
    await user.should_see("1件")
    assert view.project.members == [Member("田中", 1.0)]


async def test_a_member_without_tasks_can_be_deleted(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-delete-0").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [])


async def test_the_members_dialog_leaves_no_elements_after_hide(user: User, tmp_path: Path) -> None:
    await open_members_view(user, tmp_path)
    await open_members_parameters(user)
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
        (),
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
        (),
        None,
        Task(
            "b",
            planned_start=datetime(2026, 10, 7),
            planned_end=datetime(2026, 10, 12),
            assignees=[Assignee("田中", 0.6)],
        ),
    )
    assert user.notify.contains("田中 最大120%")
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
            (),
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
    await open_members_parameters(user)
    user.find(marker="member-name-0").clear().type("B")
    user.find(marker="member-name-1").clear().type("A")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignee_names == ["B"])
    assert [t.assignee_names for t in view.project.tasks] == [["B"], ["A"]]
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
    view.move_task(((0,), 0), ((), 1), False)
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
    view.move_task(((), 0), ((), 1), False)
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
    view.move_task(((), 5), ((), 0), False)
    view.move_task(((3,), 0), ((), 0), False)
    view.move_task(((), 0), ((7,), 0), False)
    view.move_task(((), 0), ((), -1), True)
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
    view.move_task(((), 0), ((0,), 0), True)
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
    view.shift_task((), 0, 2)
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
    view.shift_task((), 0, 0)
    view.shift_task((), 4, 1)
    view.shift_task((2,), 0, 1)
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
    view.shift_task((), 0, 1)
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
    view.shift_task((), 1, -1)  # 同じ日に重なる(割り当て 100% + 100%)
    await user.should_see("田中 最大200%になる期間があります")


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
    view.shift_task((), 0, -5)  # 基準日(10/5)で止まる = 2日分だけ左へ
    assert task.planned_start == datetime(2026, 10, 5, 9)
    assert task.planned_end == datetime(2026, 10, 6, 18)
    view.mark_clean()
    view.shift_task((), 0, -1)  # すでに基準日なので、これ以上は左へ動かない
    assert task.planned_start == datetime(2026, 10, 5, 9)
    assert not view.is_dirty()
    view.shift_task((), 0, 3)  # 右へは動く
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
    view.shift_task((), 0, -1)
    assert task.planned_start == datetime(2026, 10, 3, 9)
    view.shift_task((), 0, 1)
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
    view.save_task((), None, Task("複数", actuals=two))
    view.save_task((), None, Task("単独", actuals=two[:1]))
    assert view.multi_interval_count() == 1


PNG_BYTES = b"\x89PNG\r\n\x1a\nbody"


class FakeExporter:
    """画像化と保存先の選択の偽物。呼ばれた内容を記録する。"""

    def __init__(
        self,
        path: Path | None = None,
        error: Exception | None = None,
        available: bool = True,
        directory: Path | None = None,
        open_path: Path | None = None,
    ) -> None:
        self.path, self.error, self._available = path, error, available
        self.directory = directory
        self.asked_directory = 0
        self.open_path = open_path
        self.asked_open: list[tuple[str, ...]] = []
        self.captured: list[float] = []
        self.on_capture: Callable[[], object] | None = None  # 撮る瞬間に呼ぶ(描画の状態を調べる)
        self.asked: list[str] = []
        self.asked_types: list[tuple[str, ...]] = []

    @property
    def available(self) -> bool:
        return self._available

    async def capture(self, pixel_ratio: float) -> bytes:
        self.captured.append(pixel_ratio)
        if self.on_capture is not None:
            self.on_capture()
        if self.error is not None:
            raise self.error
        return PNG_BYTES

    async def ask_path(self, filename: str, file_types: tuple[str, ...] = ()) -> Path | None:
        self.asked.append(filename)
        self.asked_types.append(file_types)
        return self.path

    async def ask_open_path(self, file_types: tuple[str, ...] = ()) -> Path | None:
        self.asked_open.append(file_types)
        return self.open_path

    async def ask_directory(self) -> Path | None:
        self.asked_directory += 1
        return self.directory


def mount_preview(base_dir: Path, views: list[MainView], exporter: FakeExporter) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []), exporter)
        views.append(view)
        view.build()


async def open_members_view_with(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    return views[0]


async def test_choosing_an_icon_shows_it_and_applies_it(user: User, tmp_path: Path, make_png) -> None:
    path = tmp_path / "a.png"
    path.write_bytes(make_png())
    exporter = FakeExporter(open_path=path)
    view = await open_members_view_with(user, tmp_path, exporter)
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    user.find(marker="member-icon-pick-0").click()
    assert await wait_until(lambda: user.find(marker="member-icon-0").elements.pop().tag == "img")
    assert exporter.asked_open and "png" in exporter.asked_open[0][0]
    assert user.find(marker="members-dirty").elements.pop().text == "●"  # 未適用の編集
    assert view.project.members[0].icon == ""  # 適用までは変わらない
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].icon.startswith("data:image/png;base64,"))


async def test_clearing_an_icon_applies_the_removal(user: User, tmp_path: Path, icon: str) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter())
    view.project.members = [Member("田中", 1.0, icon=icon)]
    await open_members_parameters(user)
    user.find(marker="member-icon-clear-0").click()
    assert await wait_until(lambda: user.find(marker="member-icon-0").elements.pop().tag != "img")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].icon == "")


async def test_cancelling_the_file_choice_changes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=None)
    view = await open_members_view_with(user, tmp_path, exporter)
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    user.find(marker="member-icon-pick-0").click()
    assert await wait_until(lambda: bool(exporter.asked_open))
    assert user.find(marker="member-icon-0").elements.pop().tag != "img"
    assert user.find(marker="members-dirty").elements.pop().text == ""


async def test_an_unreadable_image_is_reported_and_changes_nothing(user: User, tmp_path: Path) -> None:
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    view = await open_members_view_with(user, tmp_path, FakeExporter(open_path=bad))
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    user.find(marker="member-icon-pick-0").click()
    await user.should_see("アイコンにできませんでした")
    assert user.find(marker="member-icon-0").elements.pop().tag != "img"


async def test_the_pick_button_is_hidden_without_a_native_window(user: User, tmp_path: Path, icon: str) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter(available=False))
    view.project.members = [Member("田中", 1.0, icon=icon)]
    await open_members_parameters(user)
    await user.should_see(marker="member-icon-0")
    await user.should_not_see(marker="member-icon-pick-0")
    await user.should_see(marker="member-icon-clear-0")  # 外すことはできる


async def test_the_icon_survives_a_rename_and_undo_restores_it(user: User, tmp_path: Path, icon: str) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter())
    view.project.members = [Member("田中", 1.0, icon=icon)]
    await open_members_parameters(user)
    first = user.find(marker="member-icon-clear-0").elements.pop()
    user.find(marker="member-name-0").clear().type("田中太郎")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["田中太郎"])
    assert view.project.members[0].icon == icon
    assert await wait_until(lambda: user.find(marker="member-icon-clear-0").elements.pop() is not first)  # 行の作り直しを待つ
    user.find(marker="member-icon-clear-0").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].icon == "")
    view.undo()
    assert view.project.members[0].icon == icon


def planned_task() -> Task:
    return Task("設計", planned_start=datetime(2026, 10, 5, 12), planned_end=datetime(2026, 10, 7, 12))


async def open_preview(
    user: User, tmp_path: Path, exporter: FakeExporter, extra: Task | None = None
) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.save_task((), None, planned_task())
    if extra is not None:
        view.save_task((), None, extra)
    user.find(marker="export-preview").click()
    await user.should_see(marker="task-top-0")
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


async def test_unchecking_preview_events_turns_off_the_event_options(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    assert view.gantt.options.show_events is True
    user.find(marker="preview-events").elements.pop().set_value(False)
    assert view.gantt.options.show_events is False
    assert view.preview is not None and view.preview.show_events is False


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


async def test_save_plantuml_writes_the_text_and_notifies(user: User, tmp_path: Path) -> None:
    target = tmp_path / "out" / "chart"
    target.parent.mkdir()
    exporter = FakeExporter(path=target)
    view = await open_preview(user, tmp_path, exporter)
    view.snapshot = asdict(view.project)  # open_preview がタスクを足すので、保存の直前を基準にする
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: (tmp_path / "out" / "chart.puml").exists())
    text = (tmp_path / "out" / "chart.puml").read_text(encoding="utf-8")
    assert text.startswith("@startgantt") and "[設計] as [T1] starts 2026-10-05 and ends 2026-10-07" in text
    assert "title 新規プロジェクト" in text
    assert exporter.asked == [f"新規プロジェクト_{date.today():%Y%m%d}.puml"]
    assert exporter.asked_types == [PLANTUML_FILE_TYPES]
    assert exporter.captured == []  # 画像化はしない
    await user.should_see("保存しました")
    assert view.preview is not None and not view.is_dirty()  # プロジェクトは変更扱いにならない


async def test_save_plantuml_uses_the_preview_settings(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    exporter = FakeExporter(path=target)
    await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-scale").elements.pop().set_value("週次")
    user.find(marker="preview-chips").elements.pop().set_value(False)
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    text = target.read_text(encoding="utf-8")
    assert "printscale weekly" in text and "completed" not in text


async def test_save_plantuml_with_no_tasks_notifies_and_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "chart.puml")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-start").clear().type("2030-01-01")
    user.find(marker="preview-end").clear().type("2030-01-31")  # 期間の外
    user.find(marker="preview-plantuml").click()
    await user.should_see("出力できるタスクがありません")
    assert exporter.asked == [] and not list(tmp_path.glob("*.puml"))
    assert view.preview is not None


async def test_save_plantuml_notes_skipped_tasks(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    far = Task("遠い", planned_start=datetime(2027, 6, 1, 9), planned_end=datetime(2027, 6, 2, 18))
    exporter = FakeExporter(path=target)
    await open_preview(user, tmp_path, exporter, extra=far)
    user.find(marker="preview-end").clear().type("2026-12-31")
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    await user.should_see("1 件を省きました")


async def test_cancelling_the_plantuml_dialog_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.glob("*.puml")) and view.preview is not None


async def test_a_plantuml_write_failure_is_reported_and_leaves_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "missing" / "chart.puml")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-plantuml").click()
    await user.should_see("保存できませんでした")
    assert view.preview is not None and not list(tmp_path.rglob("*.tmp"))
    assert user.find(marker="preview-plantuml").elements.pop().enabled  # もう一度押せる


async def test_the_plantuml_button_is_disabled_when_not_native(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter(available=False))
    assert not user.find(marker="preview-plantuml").elements.pop().enabled


async def test_the_plantuml_button_is_disabled_for_a_bad_period_and_back_on_when_fixed(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter())
    assert user.find(marker="preview-plantuml").elements.pop().enabled
    user.find(marker="preview-start").clear().type("2026-12-31")
    user.find(marker="preview-end").clear().type("2026-10-01")
    await user.should_see("開始日が終了日以前")
    assert not user.find(marker="preview-plantuml").elements.pop().enabled
    user.find(marker="preview-end").clear().type("2027-01-31")
    assert user.find(marker="preview-plantuml").elements.pop().enabled


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
    view.gantt.toggle_section((0,))
    await user.should_not_see(marker="task-0-0")
    view.save_task((0,), None, planned_task())
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
    view.gantt.toggle_section((0,))
    view.save_task((0,), 0, planned_task())
    assert view.gantt.collapsed == {(0,)}


async def test_adding_a_top_level_task_keeps_collapsed_sections(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section((0,))
    view.save_task((), None, planned_task())
    assert view.gantt.collapsed == {(0,)}


async def test_opening_a_project_expands_every_section(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元", [planned_task()])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("今の", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section((0,))
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
    view.gantt.toggle_section((0,))
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
    view.gantt.toggle_section((0,))
    await user.should_not_see(marker="task-0-0")
    user.find(marker="export-preview").click()
    await user.should_see(marker="task-0-0")
    await user.should_not_see(marker="section-toggle-0")
    view.exit_preview()
    await user.should_not_see(marker="task-0-0")
    assert view.gantt.collapsed == {(0,)}


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
    view.save_task((), None, Task("設計", assignees=[Assignee("田中")], planned_start=datetime(2026, 10, 5, 9), effort_hours=3))
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
            (),
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


def text_of(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


def other_project(name: str, start_day: int, end_day: int, allocation: float) -> Project:
    return Project(
        name,
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        tasks=[
            Task(
                "別の作業",
                assignees=[Assignee("田中", allocation)],
                planned_start=datetime(2026, 10, start_day, 9),
                planned_end=datetime(2026, 10, end_day, 17),
            )
        ],
    )


async def test_the_cross_switch_overlays_the_other_projects_in_the_storage(user: User, tmp_path: Path) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-load-田中")
    assert view.dashboard_cross is False
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-cross-project-別")
    assert "超過 0 日" not in text_of(user, "dashboard-load-田中")
    assert view.dashboard_excluded == set()


async def test_excluding_a_project_removes_it_from_the_total(user: User, tmp_path: Path) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-cross-project-別")
    view.change_dashboard_project("別", False)
    assert view.dashboard_excluded == {"別"}
    await asyncio.sleep(0.3)  # refresh は遅延実行なので、描き直されるのを待つ
    assert "超過 0 日" in text_of(user, "dashboard-load-田中")


async def test_a_same_named_project_is_told_apart_from_the_open_one(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    save_project(other_project(view.project.name, 6, 7, 1.0), tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    await user.should_see(marker=f"dashboard-cross-project-{view.project.name}(開いている)")
    await user.should_see(marker=f"dashboard-cross-project-{view.project.name}")
    view.change_dashboard_project(view.project.name, False)  # ファイル側だけが外れる
    await asyncio.sleep(0.3)  # refresh は遅延実行なので、描き直されるのを待つ
    assert user.find(marker=f"dashboard-cross-project-{view.project.name}(開いている)").elements.pop().value is True
    assert user.find(marker=f"dashboard-cross-project-{view.project.name}").elements.pop().value is False


async def test_the_heatmap_follows_the_cross_switch_and_the_excluded_projects(user: User, tmp_path: Path) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-load-田中")
    await user.should_not_see(marker="dashboard-heatmap")  # 横断オフでは出ない
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-heatmap-table")
    assert "別 100%" in user.find(marker="dashboard-heatmap-table").elements.pop().content
    view.change_dashboard_project("別", False)
    await asyncio.sleep(0.3)  # refresh は遅延実行なので、描き直されるのを待つ
    assert "別 100%" not in user.find(marker="dashboard-heatmap-table").elements.pop().content
    view.change_dashboard_cross(False)
    await asyncio.sleep(0.3)
    await user.should_not_see(marker="dashboard-heatmap")


async def test_an_unreadable_file_is_shown_and_the_rest_is_still_summed(user: User, tmp_path: Path) -> None:
    (tmp_path / "壊れた.json").write_text("{not json", encoding="utf-8")
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-cross-failure-0")
    await user.should_see(marker="dashboard-load-田中")


async def test_reopening_the_dashboard_turns_the_cross_switch_off_and_includes_everything(
    user: User, tmp_path: Path
) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    view.change_dashboard_project("別", False)
    view.close_dashboard()
    view.open_dashboard()
    assert view.dashboard_cross is False
    assert view.dashboard_excluded == set()


async def test_a_member_of_another_project_falls_back_to_everyone_when_the_switch_goes_off(
    user: User, tmp_path: Path
) -> None:
    other = other_project("別", 6, 7, 0.5)
    other.members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    save_project(other, tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    view.change_dashboard_member("佐藤")
    assert view.dashboard_member == "佐藤"
    view.change_dashboard_cross(False)
    assert view.dashboard_member is None


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


async def test_the_member_filter_narrows_the_dashboard_and_resets_when_reopened(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-member")
    user.find(marker="dashboard-member").elements.pop().set_value("田中")
    assert view.dashboard_member == "田中"
    await user.should_see("田中・10/05〜10/11 にかかるタスク")
    user.find(marker="dashboard-back").click()
    user.find(marker="open-dashboard").click()
    assert view.dashboard_member is None


async def test_the_member_filter_stays_when_the_period_changes(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-member")
    user.find(marker="dashboard-member").elements.pop().set_value("田中")
    user.find(marker="dashboard-period").elements.pop().set_value("今月")
    assert view.dashboard_member == "田中" and view.dashboard_kind == PeriodKind.MONTH


async def test_a_removed_member_falls_back_to_everyone(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-member")
    view.change_dashboard_member("消えた人")
    assert view.dashboard_member is None
    view.change_dashboard_member("田中")
    assert view.dashboard_member == "田中"
    view.project.members = [Member("佐藤", 1.0)]
    view.refresh_dashboard()
    assert view.dashboard_member is None


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


def mount_with_project_dir(base_dir: Path, project_dir: Path | None, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []), FakeExporter(), project_dir=project_dir)
        views.append(view)
        view.build()


async def test_projects_live_in_the_project_dir_and_settings_stay_in_the_config_dir(
    user: User, tmp_path: Path
) -> None:
    base, shared = tmp_path / "config", tmp_path / "shared"
    save_cache({}, base)
    save_project(Project("共有"), shared)
    views: list[MainView] = []
    mount_with_project_dir(base, shared, views)
    await user.open("/")
    view = views[0]
    assert set(view.files) == {"共有"}  # 設定側にあるファイルは見ない
    view.set_theme("dark")
    assert view.save_as_new("デモ")
    assert (shared / "デモ.json").exists() and not (base / "デモ.json").exists()
    assert (base / "config.json").exists() and not (shared / "config.json").exists()
    assert (base / "holidays.json").exists() and not (shared / "holidays.json").exists()


async def test_a_saved_project_dir_is_used_when_none_is_given(user: User, tmp_path: Path) -> None:
    base, shared = tmp_path / "config", tmp_path / "shared"
    save_cache({}, base)
    shared.mkdir()
    save_project_dir(shared, base)
    views: list[MainView] = []
    mount_with_project_dir(base, None, views)
    await user.open("/")
    assert views[0].project_dir == shared


async def test_an_unusable_saved_project_dir_falls_back_with_a_notice_and_keeps_the_setting(
    user: User, tmp_path: Path
) -> None:
    base, missing = tmp_path / "config", tmp_path / "ない"
    save_cache({}, base)
    save_project_dir(missing, base)
    views: list[MainView] = []
    mount_with_project_dir(base, None, views)
    await user.open("/")
    assert views[0].project_dir == base
    await user.should_see("既定の場所を使っています")
    assert load_project_dir(base) == missing


async def test_the_folder_button_opens_the_project_dir(user: User, tmp_path: Path) -> None:
    base, shared = tmp_path / "config", tmp_path / "shared"
    save_cache({}, base)
    shared.mkdir()
    views: list[MainView] = []
    mount_with_project_dir(base, shared, views)
    await user.open("/")
    opened: list[Path] = []
    views[0].open_folder = opened.append  # type: ignore[method-assign]
    user.find(marker="open-folder").click()
    assert opened == [shared]


async def open_header_view(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    return views[0]


def label_section(item: ui.menu_item) -> ui.item_section:
    """項目の文言の ItemSection(アイコンでも、右端のキーでもないもの)。"""
    return next(c for c in item.default_slot.children if c.text and "side" not in c._props)


def menu_items(user: User, menu_marker: str) -> list[tuple[str, str]]:
    """メニューの項目(文言, マーカー)を、並んだ順に返す。"""
    menu = user.find(marker=menu_marker).elements.pop()
    return [
        (label_section(child).text, next(iter(child._markers)))
        for child in menu.default_slot.children
        if isinstance(child, ui.menu_item)
    ]


def menu_icons(user: User, menu_marker: str) -> list[str]:
    menu = user.find(marker=menu_marker).elements.pop()
    return [
        next(c for c in child.default_slot.children if "avatar" in c._props).default_slot.children[0]._props["name"]
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
        ("PlantUML を取り込む", "file-import-plantuml"),
        ("新規プロジェクト作成", "file-new"),
        ("上書き保存", "save-project"),
        ("名前をつけて保存", "file-save-as"),
        ("格納先を変更", "file-change-dir"),
        ("祝日を更新", "refresh-holidays"),
    ]
    assert menu_items(user, "menu-project-items") == [
        ("設定", "open-settings"),
        ("メンバーとパラメータ", "open-members-parameters"),
        ("ダッシュボード", "menu-open-dashboard"),
    ]
    assert menu_icons(user, "menu-file-items") == ["folder_open", "upload_file", "note_add", "save", "save_as", "drive_file_move", "event_repeat"]
    assert menu_icons(user, "menu-project-items") == ["settings", "groups", "dashboard"]
    assert menu_icons(user, "menu-export-items") == ["visibility", "ios_share"]
    assert menu_icons(user, "menu-help-items") == ["keyboard"]
    assert menu_icons(user, "menu-theme-items") == ["brightness_auto", "light_mode", "dark_mode", "palette", "tune"]
    assert menu_items(user, "menu-export-items") == [
        ("チャートプレビュー", "export-preview"),
        ("担当者へ書き出し", "export-handoff"),
    ]
    assert menu_items(user, "menu-help-items") == [("ショートカットヘルプ", "help-shortcuts")]
    assert menu_items(user, "menu-theme-items") == [("自動", "theme-auto"), ("ライト", "theme-light"), ("ダーク", "theme-dark"), ("カスタム", "theme-custom"), ("カスタムの色…", "theme-custom-settings")]


async def test_the_file_menu_separates_open_save_and_update(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    menu = user.find(marker="menu-file-items").elements.pop()
    kinds = ["sep" if isinstance(c, ui.separator) else "item" for c in menu.default_slot.children]
    assert kinds == ["item", "item", "item", "sep", "item", "item", "sep", "item", "item"]


async def test_the_project_menu_dashboard_item_opens_the_dashboard(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    user.find(marker="menu-open-dashboard").click()
    assert await wait_until(lambda: view.dashboard_kind is not None)


async def test_the_dashboard_menu_item_shows_the_key_hint(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    menu = user.find(marker="menu-project-items").elements.pop()
    item = next(c for c in menu.default_slot.children if isinstance(c, ui.menu_item) and "menu-open-dashboard" in c._markers)
    assert [c.text for c in item.default_slot.children if "side" in c._props] == ["D"]


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
        return [t for t in ("auto", "light", "dark", "custom") if user.find(marker=f"theme-{t}").elements.pop()._props.get("active")]

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
    assert "var(--q-primary)" in HEADER_CSS and "var(--app-header-fg, #fff)" in HEADER_CSS  # テーマカラーの背景 + 白文字
    assert "body.body--dark .app-header" in HEADER_CSS and "color-mix" in HEADER_CSS  # ダークは暗めのテーマカラー
    title = next(e for e in user.find(kind=ui.label, content="新規プロジェクト").elements if e.text == "新規プロジェクト")  # ヘルプの「新規プロジェクト作成」と区別する
    assert "app-title" in title.classes
    assert not any(node is view.header_box for node in ancestors(title))  # タイトルは、ヘッダーの外(メイン側の左上)
    title_rule = next(line for line in HEADER_CSS.splitlines() if line.startswith(".app-title {"))
    assert "font-size: 12px" in title_rule and "font-weight: 700" in title_rule  # 他の文字と同じ大きさ。太さで区別する
    for marker in ("menu-file", "menu-project", "menu-export", "menu-git", "menu-help"):  # メニューは楕円型のボタン
        button = user.find(marker=marker).elements.pop()
        assert "rounded" in button._props and "unelevated" in button._props and "app-menu-btn" in button.classes
    assert "rgba(255, 255, 255, 0.18)" in HEADER_CSS and ".app-menu-btn:hover" in HEADER_CSS
    # 帯の上のボタンは、色を持たない(NiceGUI の既定は primary で、flat の文字が帯と同じ色になって見えなくなる)。
    # 色を持たなければ、文字は帯の白を引き継ぐ
    for marker in ("menu-file", "menu-project", "menu-export", "menu-git", "menu-help", "open-dashboard", "open-folder", "menu-theme"):
        assert not user.find(marker=marker).elements.pop()._props.get("color"), marker
    for marker in ("menu-file", "menu-project", "menu-export", "menu-git", "menu-help"):
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
    order = ["menu-file", "menu-project", "menu-export", "menu-git", "menu-help", "project-select", "open-dashboard", "open-folder", "menu-theme"]
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


async def open_dir_view(
    user: User, tmp_path: Path, directory: Path | None, *, available: bool = True
) -> tuple[MainView, FakeExporter]:
    """設定側 tmp_path/config に「甲」を置いて開いた状態。フォルダ選択は、directory を返す。"""
    base = tmp_path / "config"
    save_cache({}, base)
    save_project(Project("甲", sections=[Section("甲の中身")]), base)
    exporter = FakeExporter(directory=directory, available=available)
    views: list[MainView] = []
    mount_preview(base, views, exporter)
    await user.open("/")
    views[0].request_open("甲")
    assert views[0].path == base / "甲.json"
    return views[0], exporter


async def test_changing_the_project_dir_switches_the_list_and_starts_a_new_project(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    save_project(Project("乙"), shared)
    view, _ = await open_dir_view(user, tmp_path, shared)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: view.project_dir == shared)
    assert load_project_dir(tmp_path / "config") == shared
    assert set(view.files) == {"乙"} and list(view.file_select.options) == ["乙"]
    assert view.path is None and view.project.name == "新規プロジェクト" and view.file_select.value is None
    assert (tmp_path / "config" / "甲.json").exists()  # 古い格納先のファイルは、そのまま残す


async def test_changing_to_an_empty_folder_is_allowed(user: User, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    view, _ = await open_dir_view(user, tmp_path, empty)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: view.project_dir == empty)
    assert view.files == {}


async def test_an_unusable_folder_is_rejected_and_nothing_changes(user: User, tmp_path: Path) -> None:
    view, _ = await open_dir_view(user, tmp_path, tmp_path / "ない")
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: user.notify.contains("このフォルダは使えません"))
    assert view.project_dir == tmp_path / "config" and view.path == tmp_path / "config" / "甲.json"
    assert load_project_dir(tmp_path / "config") is None


async def test_cancelling_the_folder_dialog_changes_nothing(user: User, tmp_path: Path) -> None:
    view, exporter = await open_dir_view(user, tmp_path, None)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: exporter.asked_directory == 1)
    assert view.project_dir == tmp_path / "config" and view.path is not None
    assert load_project_dir(tmp_path / "config") is None


async def test_choosing_the_current_folder_does_nothing(user: User, tmp_path: Path) -> None:
    view, exporter = await open_dir_view(user, tmp_path, tmp_path / "config")
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: exporter.asked_directory == 1)
    assert view.path is not None  # プロジェクトを閉じない
    assert load_project_dir(tmp_path / "config") is None  # 設定も書かない


async def test_choosing_the_default_folder_after_a_fallback_start_fixes_the_setting(user: User, tmp_path: Path) -> None:
    base = tmp_path / "config"
    view, exporter = await open_dir_view(user, tmp_path, base)
    save_project_dir(tmp_path / "ない", base)  # 保存した格納先が使えず、既定の場所で起動した状態
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: exporter.asked_directory == 1)
    assert await wait_until(lambda: load_project_dir(base) == base)  # 次の起動から警告が出ない
    assert view.path is not None  # 今のフォルダと同じなので、プロジェクトは閉じない


async def test_a_failure_to_save_the_setting_keeps_the_old_folder(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, _ = await open_dir_view(user, tmp_path, shared)

    def fail(path: Path, base_dir: Path) -> None:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.save_project_dir", fail)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: user.notify.contains("保存できませんでした"))
    assert view.project_dir == tmp_path / "config" and view.path is not None


async def test_changing_the_folder_is_native_only(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, exporter = await open_dir_view(user, tmp_path, shared, available=False)
    user.find(marker="file-change-dir").click()
    await user.should_see("ネイティブウィンドウでのみ")
    assert exporter.asked_directory == 0 and view.project_dir == tmp_path / "config"


async def test_changing_the_folder_asks_before_dropping_unsaved_changes(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, exporter = await open_dir_view(user, tmp_path, shared)
    view.save_section("追加")
    user.find(marker="file-change-dir").click()
    await user.should_see("変更前に")
    assert exporter.asked_directory == 0  # 確認より先に、フォルダを選ばせない
    user.find(marker="unsaved-cancel").click()
    assert exporter.asked_directory == 0 and view.project_dir == tmp_path / "config"


async def test_changing_the_folder_can_discard_the_changes(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, _ = await open_dir_view(user, tmp_path, shared)
    view.save_section("追加")
    user.find(marker="file-change-dir").click()
    user.find(marker="unsaved-discard").click()
    assert await wait_until(lambda: view.project_dir == shared)
    assert [s.name for s in load_project(tmp_path / "config" / "甲.json").sections] == ["甲の中身"]


async def test_changing_the_folder_can_save_first(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, _ = await open_dir_view(user, tmp_path, shared)
    view.save_section("追加")
    user.find(marker="file-change-dir").click()
    user.find(marker="unsaved-save").click()
    assert await wait_until(lambda: view.project_dir == shared)
    assert [s.name for s in load_project(tmp_path / "config" / "甲.json").sections] == ["甲の中身", "追加"]


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


async def test_the_file_menu_separators_are_marked_and_the_holiday_update_is_last(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    menu = user.find(marker="menu-file-items").elements.pop()
    children = menu.default_slot.children
    assert "menu-file-separator" in children[3]._markers and "menu-file-separator" in children[6]._markers
    assert "file-change-dir" in children[7]._markers and "refresh-holidays" in children[8]._markers


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
    view.save_task((), None, Task("設計", urls=[TaskUrl("課題", "チケット", {"ID": "231"})]))
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
    view.save_task((), None, Task("設計", urls=[TaskUrl("", "チケット", {"ID": "1"})]))
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
        (("k", True, False), "open_git_commit"),
        (("K", True, True), "start_git_push"),
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


async def test_renaming_a_member_renames_the_weekly_crew_too(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("A"), Member("B")]
    weeks = [[Assignee("A", 0.5)], [Assignee("A", 0.5), Assignee("B", 0.25)]]
    view.project.tasks = [Task("t", assignees=union_assignees(weeks), weekly_crew=weeks)]
    view.apply_members([Member("A改"), Member("B")], {"A": "A改"})
    task = view.project.tasks[0]
    assert [[a.name for a in week] for week in task.weekly_crew] == [["A改"], ["A改", "B"]]
    assert [a.name for a in task.assignees] == ["A改", "B"]


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

    view.save_task((), None, task("a", 5, 9))
    view.save_task((), None, task("b", 7, 12))
    await user.should_see("田中 最大120%になる期間があります")
    await user.should_see("鈴木 最大120%になる期間があります")


async def test_the_parameters_dialog_adds_a_parameter_with_levels(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="parameter-add").click()
    await user.should_see(marker="parameter-name-0")
    user.find(marker="parameter-name-0").type("経験")
    user.find(marker="level-add-0").click()
    await user.should_see(marker="level-name-0-0")
    user.find(marker="level-name-0-0").type("上級")
    user.find(marker="level-value-0-0").clear().type("20")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters == [Parameter("経験", [Level("上級", 0.2)])])
    assert view.is_dirty()


async def test_the_parameters_dialog_shows_the_error_and_does_not_apply(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="parameter-add").click()
    await user.should_see(marker="parameter-name-0")
    user.find(marker="parameter-apply").click()  # 名前が空
    await user.should_see("名前")
    assert view.project.parameters == []


async def test_applying_the_same_parameters_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="parameter-apply").click()
    await wait_until(lambda: True)
    assert not view.is_dirty()


async def test_renaming_a_parameter_renames_the_selection_of_members(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"})]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="parameter-name-0").clear().type("スキル")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.members[0].levels == {"スキル": "上級"})
    assert view.project.parameters[0].name == "スキル"


async def test_deleting_a_used_level_asks_first_and_clears_the_selection(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"}), Member("鈴木", 1.0, {"経験": "上級"})]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="level-delete-0-1").click()
    user.find(marker="parameter-apply").click()
    await user.should_see("「経験」の「上級」を選んでいるメンバーが2人います")
    assert view.project.members[0].levels == {"経験": "上級"}  # まだ変わらない
    user.find(marker="parameter-delete-confirm").click()
    assert await wait_until(lambda: view.project.members[0].levels == {})
    assert [lv.name for lv in view.project.parameters[0].levels] == ["初級"]


async def test_deleting_a_parameter_attached_to_tasks_asks_first_and_detaches_it(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.tasks = [Task("a", parameters=["経験", "ない"]), Task("b", parameters=["経験"])]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="parameter-delete-0").click()
    user.find(marker="parameter-apply").click()
    await user.should_see("「経験」を付けているタスクが2件あります")
    assert view.project.tasks[0].parameters == ["経験", "ない"]  # まだ変わらない
    user.find(marker="parameter-delete-confirm").click()
    assert await wait_until(lambda: view.project.tasks[0].parameters == ["ない"])
    assert view.project.tasks[1].parameters == []


async def test_cancelling_the_delete_confirmation_keeps_everything(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"})]
    await open_members_parameters(user)
    user.find(marker="parameter-delete-0").click()
    user.find(marker="parameter-apply").click()
    await user.should_see("「経験」を選んでいるメンバーが1人います")
    user.find(marker="parameter-delete-cancel").click()
    assert view.project.parameters != []
    assert view.project.members[0].levels == {"経験": "上級"}


async def test_deleting_an_unused_parameter_needs_no_confirmation(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    await open_members_parameters(user)
    user.find(marker="parameter-delete-0").click()
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters == [])


async def test_a_parameter_edit_changes_the_computed_end(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"})]
    task = Task("t", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0, assignees=[Assignee("田中")])
    view.project.tasks = [task]
    view.gantt.set_project(view.project)
    # 15h / 1.2 = 12.5h → 金6.5h + 月6.0h
    assert effective_end(task, view.project, {}) == datetime(2026, 10, 12, 15, 0)
    await open_members_parameters(user)
    user.find(marker="level-value-0-0").clear().type("50")
    user.find(marker="parameter-apply").click()
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert await wait_until(lambda: effective_end(task, view.project, {}) == datetime(2026, 10, 12, 12, 30))


def params_view_setup(view: MainView) -> None:
    view.project.parameters = [Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()


async def test_the_members_dialog_without_parameters_looks_as_before(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    await user.should_see(marker="member-ratio-0")
    assert user.find(marker="member-header-name").elements.pop().text == "名前"
    assert user.find(marker="member-header-ratio").elements.pop().text == "相対比率(%)"
    await user.should_not_see(marker="member-header-effective")
    await user.should_not_see(marker="member-effective-0")
    await user.should_not_see(marker="member-level-0-0")


async def test_the_members_dialog_with_parameters_shows_selects_and_the_effective_ratio(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    await open_members_parameters(user)
    await user.should_see(marker="member-level-0-0")
    assert user.find(marker="member-header-ratio").elements.pop().text == "基本比率(%)"
    assert user.find(marker="member-header-level-0").elements.pop().text == "経験"
    assert user.find(marker="member-header-effective").elements.pop().text == "相対比率"
    select = user.find(marker="member-level-0-0").elements.pop()
    assert select.options == {"": "(なし)", "初級": "初級 -20%", "上級": "上級 +20%"}
    assert user.find(marker="member-effective-0").elements.pop().text == "相対比率 100%"
    with user.client:
        select.set_value("上級")
    assert user.find(marker="member-effective-0").elements.pop().text == "相対比率 120%"
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [Member("田中", 1.0, {"経験": "上級"})])
    assert view.is_dirty()


async def test_the_effective_ratio_follows_the_base_ratio_and_shows_the_rounding(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    await open_members_parameters(user)
    await user.should_see(marker="member-level-0-0")
    with user.client:
        user.find(marker="member-level-0-0").elements.pop().set_value("上級")
    user.find(marker="member-ratio-0").clear().type("290")
    assert user.find(marker="member-effective-0").elements.pop().text == "相対比率 300%(範囲に丸めました)"


async def test_applying_members_drops_selections_that_point_nowhere(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    view.project.members = [Member("田中", 1.0, {"経験": "存在しない", "消えた": "x"})]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].levels == {})


async def test_a_new_member_row_has_no_selection_and_is_saved(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-1")
    user.find(marker="member-name-1").type("鈴木")
    with user.client:
        user.find(marker="member-level-1-0").elements.pop().set_value("初級")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: len(view.project.members) == 2)
    assert view.project.members[1] == Member("鈴木", 1.0, {"経験": "初級"})


def grid_columns(user: User) -> list[str]:
    return user.find(marker="member-grid").elements.pop()._style["grid-template-columns"].split()


async def test_the_members_dialog_is_a_table_whose_columns_follow_the_parameters(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    await user.should_see(marker="member-grid")
    # アイコン・名前・相対比率・稼働日・削除
    assert len(grid_columns(user)) == 5


async def test_the_table_gets_a_column_per_parameter(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    view.project.parameters.append(Parameter("専門性", [Level("高", 0.1)]))
    await open_members_parameters(user)
    await user.should_see(marker="member-grid")
    # アイコン・名前・基本比率・経験・専門性・相対比率・稼働日・削除
    assert len(grid_columns(user)) == 8
    assert user.find(marker="member-header-level-1").elements.pop().text == "専門性"


async def test_the_table_scrolls_sideways_and_keeps_the_name_column_wide(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    view.project.parameters += [Parameter(f"P{n}", [Level("高", 0.1)]) for n in range(6)]
    await open_members_parameters(user)
    await user.should_see(marker="member-grid")
    scroll = user.find(marker="member-scroll").elements.pop()
    assert scroll._style["overflow-x"] == "auto"  # パラメータが多くて広がっても、横にスクロールできる
    assert scroll._style["flex-shrink"] == "0"  # タブの flex の中で縮んで、行が 1 行しか見えなくならない
    grid = user.find(marker="member-grid").elements.pop()
    assert "min-width" in grid._style  # 列を押しつぶさない
    assert grid_columns(user)[1] == "7rem"  # 名前の列は、列の数にかかわらず固定(狭くも広くもならない)
    assert len(grid_columns(user)) == 3 + 7 + 3


async def test_the_table_area_grows_with_the_rows(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    await open_members_parameters(user)
    await user.should_see(marker="member-grid")
    before = int(user.find(marker="member-scroll").elements.pop()._style["min-height"].removesuffix("px"))
    user.find(marker="member-add").click()
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-2")
    after = int(user.find(marker="member-scroll").elements.pop()._style["min-height"].removesuffix("px"))
    assert after - before == 2 * 40  # 追加した 2 行ぶん(行 36px + 間隔 4px)


async def test_the_table_inputs_have_no_floating_labels(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    await open_members_parameters(user)
    await user.should_see(marker="member-name-0")
    for marker in ("member-name-0", "member-ratio-0", "member-level-0-0"):
        props = user.find(marker=marker).elements.pop().props
        assert not props.get("label")  # 見出しの行が列の意味を示す
        assert props.get("dense") in (True, "")


async def test_the_name_column_is_a_narrow_fixed_width_with_or_without_parameters(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    await user.should_see(marker="member-grid")
    assert grid_columns(user) == ["6rem", "7rem", "7rem", "7rem", "3rem"]  # アイコン・名前・相対比率・稼働日・削除


async def test_the_dialog_width_follows_the_columns_without_the_old_wide_name(user: User, tmp_path: Path) -> None:
    from projectapp.forms import member_table_min_rem

    # アイコン 6rem + 名前 7rem + 比率 7rem + 稼働日 7rem + 削除 3rem + 列の間隔。以前の名前 12rem 以上の幅ではない
    assert member_table_min_rem(0, False) == 6 + 7 + 7 + 7 + 3 + 2 * 5
    assert member_table_min_rem(2, True) == 6 + 7 + 7 + 9 * 2 + 11 + 7 + 3 + 2 * 8


async def test_the_member_table_uses_14px_controls(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    await open_members_parameters(user)
    await user.should_see(marker="member-level-0-0")
    assert "member-table" in user.find(marker="member-grid").elements.pop().classes
    select = user.find(marker="member-level-0-0").elements.pop()
    assert "member-popup" in str(select.props.get("popup-content-class"))
    assert ".member-table .q-field__native" in MEMBER_TABLE_CSS and "font-size: 14px" in MEMBER_TABLE_CSS
    assert ".member-popup .q-item" in MEMBER_TABLE_CSS
    assert "height: 36px" in MEMBER_TABLE_CSS  # 14px の文字に合わせて、行の高さは 36px
    assert "member-table" in user.client.head_html  # ページに CSS が入っている


async def open_nested_view(user: User, tmp_path: Path) -> MainView:
    view = await open_members_view(user, tmp_path)
    view.project.sections = [Section("親", [Task("p0")], [Section("子", [Task("c0")])])]
    view.project.tasks = [Task("r0")]
    view.gantt.set_project(view.project)
    return view


async def open_two_sections_view(user: User, tmp_path: Path) -> MainView:
    view = await open_nested_view(user, tmp_path)
    view.project.sections.append(Section("兄弟", [Task("s0")]))
    view.gantt.set_project(view.project)
    view.history.clear()
    view.committed = deepcopy(view.project)
    return view


async def test_move_section_reorders_marks_dirty_and_undoes_in_one_step(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    view.move_section((1,), (0,))
    assert [s.name for s in view.project.sections] == ["兄弟", "親"]
    assert view.is_dirty()
    view.undo()
    assert [s.name for s in view.project.sections] == ["親", "兄弟"]
    view.redo()
    assert [s.name for s in view.project.sections] == ["兄弟", "親"]


async def test_move_section_carries_the_collapsed_state_with_the_section(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})  # 親とその子が折りたたみ
    view.move_section((0,), (1,))
    assert [s.name for s in view.project.sections] == ["兄弟", "親"]
    assert view.gantt.collapsed == {(1,), (1, 0)}


async def test_undo_and_redo_keep_the_collapsed_state_on_the_same_section(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})  # 親とその子が折りたたみ
    view.move_section((0,), (1,))
    assert view.gantt.collapsed == {(1,), (1, 0)}
    view.undo()
    assert [s.name for s in view.project.sections] == ["親", "兄弟"]
    assert view.gantt.collapsed == {(0,), (0, 0)}  # 折りたたみは親に付いて戻る(兄弟が閉じない)
    view.redo()
    assert view.gantt.collapsed == {(1,), (1, 0)}


async def test_move_section_ignores_other_parents_and_noops_without_a_history_step(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    before = deepcopy(view.project)
    view.move_section((1,), (0, 0))  # 親が違う
    view.move_section((0,), (0,))  # 同じ位置
    view.move_section((0,), (9,))  # 範囲外
    view.move_section((), (0,))
    assert view.project == before
    assert len(view.history.undo_stack) == 0


async def test_a_task_is_saved_into_a_nested_section(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.save_task((0, 0), None, Task("新しい"))
    assert [t.name for t in view.project.sections[0].sections[0].tasks] == ["c0", "新しい"]
    await user.should_see(marker="task-0.0-1")


async def test_saving_into_a_nested_section_opens_it_and_its_parents(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})
    view.save_task((0, 0), None, Task("新しい"))
    assert view.gantt.collapsed == set()


async def test_a_nested_task_can_be_deleted_and_shifted(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.project.sections[0].sections[0].tasks[0].planned_start = datetime(2026, 10, 7, 9)
    view.shift_task((0, 0), 0, 2)
    assert view.project.sections[0].sections[0].tasks[0].planned_start == datetime(2026, 10, 9, 9)
    view.delete_task((0, 0), 0)
    assert view.project.sections[0].sections[0].tasks == []
    assert view.tasks_in((0,))[0].name == "p0"


async def test_shift_ignores_a_path_that_does_not_exist(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.shift_task((0, 5), 0, 1)  # 存在しない。落ちない
    view.shift_task((9,), 0, 1)


async def test_adding_a_subsection_through_the_dialog(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    await user.should_see(marker="add-subsection-0")  # 描き直しを待つ
    user.find(marker="add-subsection-0").click()
    user.find(marker="section-name").type("新しい子")
    user.find(marker="section-save").click()
    assert [s.name for s in view.project.sections[0].sections] == ["子", "新しい子"]
    await user.should_see(marker="section-0.1")
    assert view.is_dirty()


async def test_a_subsection_can_be_added_to_a_subsection_but_not_below_level_three(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.save_subsection((0, 0), "孫")
    assert view.project.sections[0].sections[0].sections[0].name == "孫"
    view.save_subsection((0, 0, 0), "ひ孫")  # 3 階層目の親には足せない
    assert view.project.sections[0].sections[0].sections[0].sections == []


async def test_save_subsection_ignores_a_missing_parent(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.save_subsection((7,), "どこにも")
    view.save_subsection((), "root は別の操作")
    assert [s.name for s in view.project.sections] == ["親"]


async def test_adding_a_subsection_opens_the_parent_chain(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})
    view.save_subsection((0, 0), "孫")
    assert view.gantt.collapsed == set()


async def test_the_subsection_dialog_has_its_own_title(user: User, tmp_path: Path) -> None:
    await open_nested_view(user, tmp_path)
    await user.should_see(marker="add-subsection-0")  # 描き直しを待つ
    user.find(marker="add-subsection-0").click()
    await user.should_see("サブセクションの追加")


async def test_new_sections_and_tasks_get_ids_that_are_not_used(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, make_transport(200, []))
        views.append(view)
        view.build()

    await user.open("/")
    view = views[0]
    view.save_section("A")
    view.save_subsection((0,), "A-1")
    clash = Task("x", id=view.project.sections[0].id)  # セクションと同じ id のタスク
    view.save_task((0,), None, clash)
    assert clash.id != view.project.sections[0].id
    assert len(view.project.used_ids()) == 3
    assert len(view.project.sections[0].id) == 8 and len(view.project.sections[0].sections[0].id) == 8


async def test_apply_categories_updates_the_project_and_resets_removed_categories(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    keep, drop = Category("keep"), Category("drop")
    view.project.categories = [keep, drop]
    view.save_task((), None, Task("a", category_id=keep.id))
    view.save_task((), None, Task("b", category_id=drop.id))
    view.snapshot = asdict(view.project)
    view.apply_categories(CategoryEdit([keep], [drop.id]))
    assert view.project.categories == [keep]
    assert [t.category_id for t in view.project.all_tasks()] == [keep.id, None]
    assert view.is_dirty()  # 保存はしない(編集中の判定に入る)


async def test_apply_members_with_work_days_marks_dirty_and_the_end_date_follows(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.base_date = date(2026, 10, 12)
    view.project.members = [Member("甲", id="m1")]
    task = Task("t", planned_start=datetime(2026, 10, 16, 9), effort_hours=8.5, id="t1", assignees=[Assignee("甲", 1.0)])
    view.project.tasks = [task]
    view.gantt.set_project(view.project)
    view.snapshot = asdict(view.project)
    view.committed = deepcopy(view.project)
    assert Schedule(view.project, {}).end(task) == datetime(2026, 10, 19, 11)
    work = [WorkDay(date(2026, 10, 17), time(13), time(16))]
    view.apply_members([Member("甲", id="m1", work_days=work)], {})
    assert view.project.members[0].work_days == work
    assert Schedule(view.project, {}).end(task) == datetime(2026, 10, 17, 15)
    assert view.is_dirty()
    view.undo()
    assert view.project.members[0].work_days == []


async def test_apply_events_marks_the_project_dirty_and_redraws(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    view.snapshot = asdict(view.project)
    day = view.project.base_date
    event = Event(day, day, "x", "red", id="e1")
    view.apply_events([event])
    assert view.project.events == [event]
    assert view.is_dirty()
    await user.should_see(marker="event-bar-e1")


async def test_the_task_layout_is_loaded_and_saved(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"task_layout": "schedule"}', encoding="utf-8")
    view = await open_members_view(user, tmp_path)
    assert view.task_layout == "schedule"
    view.set_task_layout("all")
    assert view.task_layout == "all"
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["task_layout"] == "all"


async def test_the_task_dialogs_get_the_saved_layout(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"task_layout": "schedule"}', encoding="utf-8")
    view = await open_members_view(user, tmp_path)
    with view.client:
        view.add_top_task()
    await user.should_see(marker="task-layout")
    assert user.find(marker="task-layout").elements.pop().value == "schedule"
    await user.should_not_see(marker="task-color")


async def open_with_external_change(user: User, tmp_path: Path) -> MainView:
    """「既存」を開き、自分の編集のあとで、相手がファイルを書き換えた状態にする。"""
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    view.save_section("自分")
    save_project(Project("既存", sections=[Section("相手")]), tmp_path)
    return view


def section_names(path: Path) -> list[str]:
    return [s.name for s in load_project(path).sections]


async def test_save_after_an_external_change_asks_and_overwrite_keeps_the_other_version_as_bak(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    await user.should_see(marker="conflict-overwrite")
    assert section_names(tmp_path / "既存.json") == ["相手"]  # まだ書いていない
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]
    assert section_names(tmp_path / "既存.json.bak") == ["相手"]
    assert not view.is_dirty()


async def test_save_after_overwriting_does_not_ask_again(user: User, tmp_path: Path) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: not view.is_dirty())
    view.save_section("さらに")
    user.find(marker="save-project").click()
    assert await wait_until(lambda: section_names(tmp_path / "既存.json") == ["元", "自分", "さらに"])


async def test_external_change_cancel_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-cancel").click()
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert not (tmp_path / "既存.json.bak").exists()
    assert view.is_dirty()


async def test_external_change_save_as_leaves_the_other_version_and_switches(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-save-as").click()
    user.find(marker="project-name").clear().type("別名")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "別名.json")
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert section_names(tmp_path / "別名.json") == ["元", "自分"]
    assert not (tmp_path / "既存.json.bak").exists()


async def test_external_change_save_as_name_dialog_survives_the_conflict_dialog_being_deleted(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    conflict = user.find(marker="conflict-save-as").elements.pop()
    while not isinstance(conflict, ui.dialog):
        conflict = conflict.parent_slot.parent
    user.find(marker="conflict-save-as").click()
    await user.should_see(marker="name-save")
    conflict.delete()  # 確認ダイアログは、閉じたあとの hide で自分を削除する
    gc.collect()
    await asyncio.sleep(0.2)
    await user.should_see(marker="name-save")
    user.find(marker="project-name").clear().type("別名")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "別名.json")


async def test_external_change_save_as_with_an_existing_name_keeps_the_dialog_open(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-save-as").click()
    user.find(marker="project-name").clear().type("既存")
    user.find(marker="name-save").click()
    await user.should_see(marker="project-name")
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert view.path == tmp_path / "既存.json"


async def test_external_change_with_a_failing_backup_does_not_overwrite(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(path: Path) -> Path:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.backup_file", fail)
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: user.notify.contains("バックアップを作れなかったため、保存しませんでした"))
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert view.is_dirty()


async def test_overwrite_after_the_file_vanished_in_the_dialog_still_saves(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    await user.should_see(marker="conflict-overwrite")
    (tmp_path / "既存.json").unlink()
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: not view.is_dirty())
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]


async def test_save_when_the_file_vanished_notifies_and_creates_it(user: User, tmp_path: Path) -> None:
    view = await open_with_external_change(user, tmp_path)
    (tmp_path / "既存.json").unlink()
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("ファイルが見つかりませんでした。新しく作成します"))
    assert await wait_until(lambda: not view.is_dirty())
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]


async def test_save_and_open_continues_only_after_the_external_change_is_overwritten(
    user: User, tmp_path: Path
) -> None:
    save_project(Project("乙", sections=[Section("乙の中身")]), tmp_path)
    view = await open_with_external_change(user, tmp_path)
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    await user.should_see(marker="conflict-overwrite")
    assert view.path == tmp_path / "既存.json"
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: view.path == tmp_path / "乙.json")
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]


async def test_save_and_open_stays_when_the_external_change_dialog_is_cancelled(
    user: User, tmp_path: Path
) -> None:
    save_project(Project("乙"), tmp_path)
    view = await open_with_external_change(user, tmp_path)
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    user.find(marker="conflict-cancel").click()
    assert view.path == tmp_path / "既存.json"
    assert view.is_dirty()


async def test_save_and_open_with_save_as_continues_after_the_new_file_is_saved(
    user: User, tmp_path: Path
) -> None:
    save_project(Project("乙"), tmp_path)
    view = await open_with_external_change(user, tmp_path)
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    user.find(marker="conflict-save-as").click()
    user.find(marker="project-name").clear().type("別名")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "乙.json")
    assert section_names(tmp_path / "別名.json") == ["元", "自分"]


async def test_save_when_the_file_became_unreadable_notifies_instead_of_crashing(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    path = tmp_path / "既存.json"
    path.chmod(0o000)
    try:
        user.find(marker="save-project").click()
        assert await wait_until(lambda: user.notify.contains("保存できませんでした"))
    finally:
        path.chmod(0o644)
    assert view.is_dirty()


IMPORT_SAMPLE = """@startgantt
title 取込元
Project starts 2026-10-12
-- 開発 --
[設計] on {田中} starts 2026-10-13 and ends 2026-10-14
@endgantt
"""


def write_puml(tmp_path: Path, text: str = IMPORT_SAMPLE) -> Path:
    folder = tmp_path / "other"
    folder.mkdir(exist_ok=True)
    source = folder / "in.puml"
    source.write_text(text, encoding="utf-8")
    return source


async def open_for_import(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    return views[0]


async def test_import_plantuml_opens_an_unsaved_project(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    assert await wait_until(lambda: view.project.name == "取込元")
    assert view.path is None and view.is_dirty()  # 保存前の新規。ファイルは作らない
    assert [t.name for t in view.project.sections[0].tasks] == ["設計"]
    assert [m.name for m in view.project.members] == ["田中"]
    assert exporter.asked_open == [PLANTUML_OPEN_FILE_TYPES]
    await user.should_see("取り込みました(タスク 1 件、メンバー 1 人を作成)")
    assert not [f for f in tmp_path.glob("*.json") if f.name != "holidays.json"]


async def test_cancelling_the_import_dialog_changes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=None)
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    assert await wait_until(lambda: exporter.asked_open != [])
    assert view.project.name == "新規プロジェクト" and not view.is_dirty()


async def test_import_plantuml_refuses_a_text_without_a_diagram(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path, "hello"))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    await user.should_see("取り込めませんでした")
    assert view.project.name == "新規プロジェクト" and not view.is_dirty()


async def test_import_plantuml_needs_the_native_window(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path), available=False)
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    await user.should_see("ネイティブウィンドウでのみ、取り込めます")
    assert exporter.asked_open == [] and view.project.name == "新規プロジェクト"


async def test_import_plantuml_asks_before_dropping_unsaved_edits(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    view.save_section("追加")
    user.find(marker="file-import-plantuml").click()
    await user.should_see(marker="unsaved-discard")
    assert exporter.asked_open == []
    user.find(marker="unsaved-discard").click()
    assert await wait_until(lambda: view.project.name == "取込元")
    assert [s.name for s in view.project.sections] == ["開発"]


async def test_cancelling_the_unsaved_dialog_does_not_start_the_import(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    view.save_section("追加")
    user.find(marker="file-import-plantuml").click()
    await user.should_see(marker="unsaved-cancel")
    user.find(marker="unsaved-cancel").click()
    assert exporter.asked_open == [] and [s.name for s in view.project.sections] == ["追加"]


async def test_an_imported_project_asks_before_another_project_is_opened(user: User, tmp_path: Path) -> None:
    save_project(Project("既存"), tmp_path)
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    assert await wait_until(lambda: view.project.name == "取込元")
    await choose_in_combo(user, "既存")
    await user.should_see(marker="unsaved-save")


async def test_the_name_dialog_survives_the_unsaved_dialog_being_deleted(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    view.save_section("追加")  # 保存前の新規プロジェクトを編集中
    user.find(marker="file-new").click()
    confirm = next(e for e in user.find(marker="unsaved-save").elements)
    unsaved = confirm
    while not isinstance(unsaved, ui.dialog):
        unsaved = unsaved.parent_slot.parent
    user.find(marker="unsaved-save").click()
    await user.should_see(marker="name-save")
    unsaved.delete()  # 確認ダイアログは、閉じたあとの hide で自分を削除する
    gc.collect()  # ダイアログは、作られた場所の要素が消えると、自分も消える
    await asyncio.sleep(0.2)
    await user.should_see(marker="name-save")
    user.find(marker="project-name").type("保存名")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: (tmp_path / "保存名.json").exists())


def task_names(view: MainView) -> list[str]:
    return [t.name for t in view.project.tasks]


async def test_undo_and_redo_walk_through_task_edits(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.save_task((), 0, Task("b"))
    view.undo()
    assert task_names(view) == ["a"]
    view.undo()
    assert task_names(view) == []
    view.undo()  # もう戻せない。何も変わらない
    assert task_names(view) == []
    view.redo()
    view.redo()
    assert task_names(view) == ["b"]
    view.redo()  # もうやり直せない
    assert task_names(view) == ["b"]


async def test_undo_redraws_the_chart(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].save_task((), None, Task("a"))
    await user.should_see(marker="task-top-0")
    views[0].undo()
    await user.should_not_see(marker="task-top-0")


async def test_undo_covers_delete_settings_and_sections(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("開発")
    view.save_task((0,), None, Task("x"))
    view.apply_settings(5.0, view.project.work_start, view.project.actual_mode)
    view.delete_task((0,), 0)
    assert view.project.sections[0].tasks == []
    view.undo()
    assert [t.name for t in view.project.sections[0].tasks] == ["x"]
    view.undo()
    assert view.project.daily_hours != 5.0
    view.undo()
    assert view.project.sections[0].tasks == []
    view.undo()
    assert view.project.sections == []


async def test_an_edit_that_changes_nothing_adds_no_step(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.apply_settings(view.project.daily_hours, view.project.work_start, view.project.actual_mode)
    view.apply_events(list(view.project.events))
    view.undo()  # 無変更の適用は積まれないので、1 回で「a」を足す前に戻る
    assert task_names(view) == []
    assert not view.history.can_undo()


async def test_a_new_edit_after_undo_drops_the_redo(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.undo()
    view.save_task((), None, Task("b"))
    view.redo()  # やり直す操作はない
    assert task_names(view) == ["b"]


async def test_undoing_to_the_saved_state_clears_dirty_and_going_further_sets_it(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    await save_new_as(user, "p")  # 最初の保存は名前を付けるので、履歴は空から始まる
    assert not view.is_dirty()
    view.save_task((), None, Task("a"))
    assert view.is_dirty()
    view.undo()
    assert not view.is_dirty()  # 保存済みの内容に戻った
    view.redo()
    view.save_project_clicked()
    assert not view.is_dirty()
    view.undo()  # 保存をまたいで戻る
    assert task_names(view) == []
    assert view.is_dirty()  # 保存した内容とは違うので、未保存に戻る
    view.redo()
    assert not view.is_dirty()


async def test_history_is_dropped_when_another_project_is_opened(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("other"), tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.open_project("other")
    assert view.project.name == "other"
    assert not view.history.can_undo()
    assert not view.history.can_redo()
    view.undo()
    assert view.project.name == "other"


async def test_history_is_dropped_on_a_new_project(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.new_project()
    assert not view.history.can_undo()


async def test_save_as_drops_the_history_and_the_rename_is_not_a_step(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    assert view.save_as_new("copy")
    assert not view.history.can_undo()
    view.save_task((), None, Task("b"))
    view.undo()
    assert view.project.name == "copy"  # 名前の変更は戻らない
    assert task_names(view) == ["a"]
    assert not view.history.can_undo()  # 名前の変更が 1 ステップとして積まれていない


async def test_ctrl_z_undoes_and_ctrl_shift_z_redoes(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.on_undo_key(key_event("z", ctrl=True))
    assert task_names(view) == []
    view.on_undo_key(key_event("z", ctrl=True, shift=True))
    assert task_names(view) == ["a"]


async def test_ctrl_z_is_ignored_in_inputs(user: User, tmp_path: Path) -> None:
    """入力欄にフォーカスがあるときは、NiceGUI が `on_plain_key` に送らない。Ctrl 付きを全部受ける側では、受けない。"""
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.on_modified_key(key_event("z", ctrl=True))  # 入力欄でも受ける側
    view.on_modified_key(key_event("z", ctrl=True, shift=True))
    view.on_plain_key(key_event("z", ctrl=True))  # 文字キー用の側も、Ctrl+Z は受けない(二重に Undo しない)
    assert task_names(view) == ["a"]
    assert view.history.can_undo()  # 履歴も動いていない


async def test_other_ctrl_keys_still_go_through_the_modified_handler(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    calls: list[str] = []
    view.open_settings = lambda: calls.append("settings")  # type: ignore[method-assign]
    view.on_plain_key(key_event(",", ctrl=True))  # 入力欄を除く側は、Ctrl+Z 以外の Ctrl 付きを受けない
    assert calls == []
    view.on_modified_key(key_event(",", ctrl=True))
    assert calls == ["settings"]


async def test_ctrl_z_does_nothing_while_a_dialog_is_open(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    with view.client:
        view.add_section()  # ダイアログを開く
    assert view.dialog_open()
    view.on_undo_key(key_event("z", ctrl=True))
    assert task_names(view) == ["a"]


async def test_the_three_keyboards_ignore_the_right_elements(user: User, tmp_path: Path) -> None:
    """入力欄で Undo が誤爆しない(文字キー用と Undo 用が入力欄を無視する)ことと、ボタンにフォーカスがあっても
    Undo が届く(Undo 用は button を無視しない)ことは、NiceGUI の `ignore` の構成で決まるので、構成そのものを確かめる。"""
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    ignores = sorted(
        sorted(e._props["ignore"]) for e in views[0].client.elements.values() if isinstance(e, ui.keyboard)
    )
    assert ignores == [
        [],  # Ctrl/Cmd 付き(Undo・Redo 以外)は、入力欄でも受ける
        ["button", "input", "select", "textarea"],  # 文字キー用: 入力欄・ボタンでは受けない
        ["input", "select", "textarea"],  # Undo・Redo 用: 入力欄では受けず、ボタンにフォーカスがあっても受ける
    ]


async def test_undo_works_when_a_button_has_the_focus(user: User, tmp_path: Path) -> None:
    """ボタンにフォーカスがあると、文字キー用は NiceGUI が送らない。Undo 用の側だけで、1 回だけ戻ること。"""
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task((), None, Task("a"))
    view.save_task((), None, Task("b"))
    view.on_undo_key(key_event("z", ctrl=True))
    assert task_names(view) == ["a"]  # 1 回で 1 ステップ


def test_header_css_reads_the_custom_variables_and_keeps_the_current_defaults() -> None:
    assert "background: var(--app-header, var(--q-primary)); color: var(--app-header-fg, #fff)" in HEADER_CSS
    assert "body.body--dark .app-header { background: var(--app-header, color-mix(in srgb, var(--q-primary) 55%, #000)); }" in HEADER_CSS
    assert ".app-header .app-menu-btn { background: var(--app-header-chip, rgba(255, 255, 255, 0.18));" in HEADER_CSS
    assert ".app-header .app-menu-btn:hover { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }" in HEADER_CSS
    assert "border-radius: 9999px; background: var(--app-header-chip, rgba(255, 255, 255, 0.18))" in HEADER_CSS
    assert ".app-git-chip:hover { background: var(--app-header-chip-hover, rgba(255, 255, 255, 0.3)); }" in HEADER_CSS


async def test_apply_theme_custom_sets_dark_mode_from_the_base_and_the_variables(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    scripts: list[str] = []
    view.run_js = lambda script, **kw: scripts.append(script)  # type: ignore[method-assign]
    view.custom_theme = CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0")
    view.apply_theme("custom")
    assert view.theme == "custom" and view.dark.value is True
    assert len(scripts) == 1 and 'setProperty("--app-bg", "#1e1e2e")' in scripts[0]
    view.apply_theme("light")
    assert view.dark.value is False
    assert len(scripts) == 2 and 'setProperty("--q-primary", "#5898d4")' in scripts[1] and 'removeProperty("--app-bg")' in scripts[1]


async def test_apply_theme_with_a_preview_color_does_not_change_the_saved_color(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    scripts: list[str] = []
    view.run_js = lambda script, **kw: scripts.append(script)  # type: ignore[method-assign]
    saved = view.custom_theme
    view.apply_theme("custom", CustomTheme("dark", "#112233", None, "#000000", "#ffffff"))
    assert view.custom_theme == saved
    assert '"#112233"' in scripts[0] and view.dark.value is True


async def test_starting_with_the_custom_theme_applies_the_saved_colors(user: User, tmp_path: Path) -> None:
    save_custom_theme(CustomTheme("dark", "#7e57c2", None, "#1e1e2e", "#e6e6f0"), tmp_path, select=True)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].theme == "custom" and views[0].dark.value is True
    assert views[0].custom_theme.primary == "#7e57c2"


async def test_starting_with_custom_and_no_colors_uses_the_light_default(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "custom"}), encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].theme == "custom" and views[0].dark.value is False


async def test_selecting_custom_in_the_menu_saves_the_theme_and_keeps_the_colors(user: User, tmp_path: Path) -> None:
    view = await open_header_view(user, tmp_path)
    user.find(marker="theme-custom").click()
    assert view.theme == "custom"
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path) == view.custom_theme


async def test_theme_dialog_preview_then_cancel_restores_the_previous_theme(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.set_theme("dark")
    user.find(marker="theme-custom-settings").click()
    user.find(marker="theme-primary").elements.pop().set_value("#7e57c2")
    assert view.theme == "custom"  # プレビュー中
    user.find(marker="theme-cancel").click()
    assert view.theme == "dark" and view.dark.value is True
    assert load_theme(tmp_path) == "dark"
    assert load_custom_theme(tmp_path) == DEFAULTS["light"]  # 何も保存していない


async def test_theme_dialog_apply_saves_the_colors_and_selects_custom(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="theme-custom-settings").click()
    user.find(marker="theme-primary").elements.pop().set_value("#7e57c2")
    user.find(marker="theme-apply").click()
    assert view.theme == "custom" and view.custom_theme.primary == "#7e57c2"
    assert load_theme(tmp_path) == "custom"
    assert load_custom_theme(tmp_path).primary == "#7e57c2"


async def test_theme_dialog_apply_failure_notifies_and_keeps_saved_state(user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.save_custom_theme", fail)
    user.find(marker="theme-custom-settings").click()
    user.find(marker="theme-primary").elements.pop().set_value("#7e57c2")
    user.find(marker="theme-apply").click()
    await user.should_see("テーマを保存できませんでした")
    assert view.custom_theme == DEFAULTS["light"]  # 保存済みの色は変えない
    await user.should_see(marker="theme-apply")  # ダイアログは開いたまま


async def test_selecting_custom_settings_in_the_menu_opens_the_dialog(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    user.find(marker="theme-custom-settings").click()
    await user.should_see(marker="theme-apply")


def test_header_project_select_follows_the_header_text_color_and_keeps_the_defaults() -> None:
    assert ".app-header .app-project-select .q-field__native" in HEADER_CSS
    assert "color: var(--app-header-fg, #fff)" in HEADER_CSS.split(".app-header .app-project-select {")[1].split("\n")[0] or "var(--app-header-fg, #fff)" in HEADER_CSS
    assert "var(--app-header-border, hsla(0, 0%, 100%, 0.24))" in HEADER_CSS
    assert "var(--app-header-label, rgba(255, 255, 255, 0.7))" in HEADER_CSS


def selects(view: MainView) -> list[ui.select]:
    return [e for e in view.client.elements.values() if isinstance(e, ui.select)]


async def test_selects_open_their_options_in_a_dialog_while_zoomed(user: User, tmp_path: Path) -> None:
    """CSS の zoom 中は、Quasar のメニューが画面の高さを誤るので、下の候補が画面の外に出る。zoom 中は専用の枠で出す。"""
    view, _ = await open_zoom_view(user, tmp_path)
    assert selects(view)
    assert all("behavior" not in s.props for s in selects(view))
    for _ in range(4):
        view.on_key(key_event("=", ctrl=True))
    assert view.zoom == 140
    assert all(s.props.get("behavior") == "dialog" for s in selects(view))
    view.on_key(key_event("0", ctrl=True))
    assert all("behavior" not in s.props for s in selects(view))


async def test_selects_created_while_zoomed_also_open_in_a_dialog(user: User, tmp_path: Path) -> None:
    view, _ = await open_zoom_view(user, tmp_path)
    view.on_key(key_event("=", ctrl=True))
    with view.client:
        later = ui.select(["a", "b"])
    assert later.props.get("behavior") == "dialog"
    view.on_key(key_event("0", ctrl=True))
    with view.client:
        assert "behavior" not in ui.select(["a"]).props
    assert "behavior" not in later.props


async def test_starting_zoomed_opens_selects_in_a_dialog(user: User, tmp_path: Path) -> None:
    save_zoom(130, tmp_path)
    view, _ = await open_zoom_view(user, tmp_path)
    assert selects(view)
    assert all(s.props.get("behavior") == "dialog" for s in selects(view))


async def test_apply_base_date_changes_marks_dirty_and_undoes(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.apply_base_date(date(2026, 10, 5))
    view.mark_clean()
    view.apply_base_date(date(2026, 11, 2))
    assert view.project.base_date == date(2026, 11, 2)
    assert view.is_dirty()
    view.undo()
    assert view.project.base_date == date(2026, 10, 5)


async def test_apply_base_date_with_the_same_day_does_nothing(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.mark_clean()
    view.apply_base_date(date(2026, 10, 5))
    assert not view.is_dirty()
    assert not view.history.can_undo()


async def test_settings_dialog_changes_the_base_date_of_the_project(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.mark_clean()
    user.find(marker="open-settings").click()
    user.find(marker="settings-base-date").clear().type("2026-11-02")
    user.find(marker="settings-apply").click()
    assert view.project.base_date == date(2026, 11, 2)
    assert view.is_dirty()


async def test_a_later_base_date_keeps_earlier_tasks_and_moves_the_drag_limit(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    task = Task("a", planned_start=datetime(2026, 10, 7, 9), planned_end=datetime(2026, 10, 8, 18), planned_end_manual=True)
    view.project.base_date = date(2026, 10, 5)
    view.project.tasks.append(task)
    view.apply_base_date(date(2026, 10, 20))  # タスクより後ろの基準日(案 A)
    start, _ = visible_range(view.project)
    assert start == date(2026, 10, 7)  # タスクは表示範囲に残る
    view.shift_task((), 0, -3)  # 基準日より前にあるので、左へは動かない
    assert task.planned_start == datetime(2026, 10, 7, 9)
    view.shift_task((), 0, 2)  # 右へは動く
    assert task.planned_start == datetime(2026, 10, 9, 9)


async def test_decompose_button_is_not_shown_for_a_summary_child(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    child = Task("子", id="c1", effort_hours=2.0)
    parent = Task("親", id="p1", kind=TaskKind.SUMMARY, children=["c1"])
    save_project(Project("既存", sections=[Section("開発", [parent, child])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="task-0-1")
    edit_from_menu(user, "row-0-1")
    await user.should_see(marker="task-save")
    await user.should_not_see(marker="task-decompose")


async def test_decompose_without_chain_warns_about_the_overallocation(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.apply_members([Member("田中")], {})
    view.project.tasks.append(
        Task("a", planned_start=datetime(2026, 10, 5, 9), effort_hours=13.0, assignees=[Assignee("田中")])
    )
    view.apply_decompose((), 0, [Part("x", 6.5), Part("y", 6.5)], chain=False, new_section=False)
    await user.should_see("田中 最大200%になる期間があります")
    assert len([n for n in user.notify.messages if "田中 最大" in n]) == 1  # 子の数だけ出さない


async def test_decompose_with_chain_does_not_warn(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.apply_members([Member("田中")], {})
    view.project.tasks.append(
        Task("a", planned_start=datetime(2026, 10, 5, 9), effort_hours=13.0, assignees=[Assignee("田中")])
    )
    view.apply_decompose((), 0, [Part("x", 6.5), Part("y", 6.5)], chain=True, new_section=False)
    assert not user.notify.contains("割り当て")


async def open_context_menu_on_the_only_task(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("開発", [Task("実装", effort_hours=4.0)])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="task-0-0")
    view.gantt.open_menu((0,), 0)
    return view


async def test_context_menu_copy_puts_the_copy_right_after(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="context-copy").click()
    assert [t.name for t in view.project.sections[0].tasks] == ["実装", "実装(コピー)"]
    assert view.is_dirty()


async def test_context_menu_rename_changes_only_the_name(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    before = view.project.sections[0].tasks[0]
    user.find(marker="context-rename").click()
    user.find(marker="project-name").elements.pop().set_value("設計")
    user.find(marker="name-save").click()
    after = view.project.sections[0].tasks[0]
    assert (after.name, after.id, after.effort_hours) == ("設計", before.id, 4.0)
    assert view.is_dirty()


async def test_context_menu_rename_rejects_an_invalid_name(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="context-rename").click()
    user.find(marker="project-name").elements.pop().set_value("   ")
    user.find(marker="name-save").click()
    await user.should_see("名前を入力してください")
    assert view.project.sections[0].tasks[0].name == "実装"


async def test_context_menu_delete_asks_first(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="context-delete").click()
    await user.should_see("「実装」を削除しますか?")
    assert len(view.project.sections[0].tasks) == 1
    user.find(marker="confirm-ok").click()
    assert view.project.sections[0].tasks == []


async def test_context_menu_delete_can_be_cancelled(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="context-delete").click()
    user.find(marker="confirm-cancel").click()
    assert len(view.project.sections[0].tasks) == 1


async def test_context_menu_decompose_opens_the_decompose_dialog(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="context-decompose").click()
    user.find(marker="decompose-apply").click()
    assert view.project.sections[0].tasks[0].kind is TaskKind.SUMMARY
    assert len(view.project.sections[0].tasks) == 3


async def open_section_menu_on_a_project(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    project = Project(
        "既存",
        tasks=[Task("直下", id="top")],
        sections=[
            Section("開発", [Task("a", id="a")], [Section("子", [Task("c", id="c")])]),
            Section("企画", [Task("d", id="d")]),
        ],
    )
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="section-0")
    return view


async def test_section_menu_copy_puts_the_copy_after_it_and_follows_the_collapsed_state(user: User, tmp_path: Path) -> None:
    view = await open_section_menu_on_a_project(user, tmp_path)
    view.gantt.collapsed.add((1,))  # 企画を折りたたむ
    view.gantt.open_section_menu((0,))
    user.find(marker="section-context-copy").click()
    assert [s.name for s in view.project.sections] == ["開発", "開発(コピー)", "企画"]
    assert view.gantt.collapsed == {(2,)}  # 企画は番号が 1 つ後ろへずれた
    assert view.is_dirty()
    await user.should_see("セクション「開発」をコピーしました")


async def test_section_menu_rename_changes_only_the_name(user: User, tmp_path: Path) -> None:
    view = await open_section_menu_on_a_project(user, tmp_path)
    view.gantt.open_section_menu((0, 0))  # サブセクション
    user.find(marker="section-context-rename").click()
    user.find(marker="project-name").elements.pop().set_value("設計")
    user.find(marker="name-save").click()
    child = view.project.sections[0].sections[0]
    assert (child.name, [t.name for t in child.tasks]) == ("設計", ["c"])
    assert view.is_dirty()


async def test_section_menu_rename_rejects_an_empty_name(user: User, tmp_path: Path) -> None:
    view = await open_section_menu_on_a_project(user, tmp_path)
    view.gantt.open_section_menu((0,))
    user.find(marker="section-context-rename").click()
    user.find(marker="project-name").elements.pop().set_value("  ")
    user.find(marker="name-save").click()
    await user.should_see("名前を入力してください")
    assert view.project.sections[0].name == "開発"


async def test_section_menu_delete_asks_then_moves_the_tasks_to_the_root_and_notifies(user: User, tmp_path: Path) -> None:
    view = await open_section_menu_on_a_project(user, tmp_path)
    view.gantt.collapsed.update({(0,), (1,)})
    view.gantt.open_section_menu((0,))
    user.find(marker="section-context-delete").click()
    await user.should_see("セクション「開発」を削除しますか?")
    assert [s.name for s in view.project.sections] == ["開発", "企画"]  # 確認するまでは消さない
    user.find(marker="confirm-ok").click()
    assert [s.name for s in view.project.sections] == ["企画"]
    assert [t.name for t in view.project.tasks] == ["直下", "a", "c"]
    assert view.gantt.collapsed == {(0,)}  # 企画の分だけ残り、番号は詰まる
    await user.should_see("セクション「開発」を削除しました(タスク 2 件は、セクションなしへ移しました)")


async def test_section_menu_delete_can_be_cancelled(user: User, tmp_path: Path) -> None:
    view = await open_section_menu_on_a_project(user, tmp_path)
    view.gantt.open_section_menu((1,))
    user.find(marker="section-context-delete").click()
    user.find(marker="confirm-cancel").click()
    assert [s.name for s in view.project.sections] == ["開発", "企画"]


async def test_double_click_and_enter_adds_a_named_task_below_and_it_can_be_undone(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="task-0-0").trigger("dblclick")
    await user.should_see(marker="quick-add-input")
    user.find(marker="quick-add-input").trigger("keydown.enter", args="追加した")
    assert [t.name for t in view.project.sections[0].tasks] == ["実装", "追加した"]
    added = view.project.sections[0].tasks[1]
    assert (added.effort_hours, added.planned_start, added.assignees) == (0.0, None, [])
    assert view.is_dirty()
    await user.should_see("追加した")
    await user.should_not_see(marker="quick-add-input")
    view.undo()
    assert [t.name for t in view.project.sections[0].tasks] == ["実装"]


async def test_shift_double_click_and_enter_adds_a_named_section_and_it_can_be_undone(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    user.find(marker="task-0-0").trigger("dblclick", args=True)
    await user.should_see(marker="quick-add-input")
    user.find(marker="quick-add-input").trigger("keydown.enter", args="新しい節")
    assert [s.name for s in view.project.sections[0].sections] == ["新しい節"]
    assert view.is_dirty()
    await user.should_see("新しい節")
    await user.should_not_see(marker="quick-add-input")
    view.undo()
    assert view.project.sections[0].sections == []


async def test_shift_double_click_on_the_end_row_adds_a_top_level_section(user: User, tmp_path: Path) -> None:
    view = await open_context_menu_on_the_only_task(user, tmp_path)
    count = len(view.project.sections)
    user.find(marker="top-end").trigger("dblclick", args=True)
    await user.should_see(marker="quick-add-input")
    user.find(marker="quick-add-input").trigger("keydown.enter", args="最上位")
    assert [s.name for s in view.project.sections][count:] == ["最上位"]


async def test_member_work_days_are_edited_in_a_sub_dialog_and_applied_with_the_tab(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("甲", 1.0, {}, "m1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-workday-open-0").click()
    await user.should_see(marker="member-workday-add")
    user.find(marker="member-workday-add").click()
    await user.should_see(marker="member-workday-0-day")
    user.find(marker="member-workday-0-day").type("2026-10-17")
    user.find(marker="member-workday-0-start").type("13")
    user.find(marker="member-workday-0-end").type("16")
    user.find(marker="member-workday-close").click()
    await settle()
    assert user.find(marker="members-dirty").elements.pop().text == "●"  # 未適用の編集がある
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].work_days == [WorkDay(date(2026, 10, 17), time(13), time(16))])
    assert view.is_dirty()


async def test_a_rest_work_day_disables_the_time_inputs_and_a_bad_window_shows_the_error(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("甲", 1.0, {}, "m1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-workday-open-0").click()
    await user.should_see(marker="member-workday-add")
    user.find(marker="member-workday-add").click()
    await user.should_see(marker="member-workday-0-day")
    user.find(marker="member-workday-0-day").type("2026-10-17")
    user.find(marker="member-workday-0-rest").click()
    await settle()
    assert not user.find(marker="member-workday-0-start").elements.pop().enabled
    user.find(marker="member-workday-0-rest").click()  # 休みを外して、開始 > 終了にする
    await settle()
    user.find(marker="member-workday-0-start").type("16")
    user.find(marker="member-workday-0-end").type("13")
    user.find(marker="member-workday-close").click()
    await settle()
    user.find(marker="member-apply").click()
    await settle()
    assert "甲" in user.find(marker="member-error").elements.pop().text
    assert view.project.members[0].work_days == []


async def test_work_day_inputs_have_calendar_and_time_pickers(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("甲", 1.0, {}, "m1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-workday-open-0").click()
    await user.should_see(marker="member-workday-add")
    user.find(marker="member-workday-add").click()
    for field in ("day", "start", "end"):
        await user.should_see(marker=f"open-member-workday-0-{field}-picker")
    def picker_open() -> bool:
        element = user.find(marker="member-workday-0-start-picker").elements.pop()
        while not isinstance(element, ui.dialog):
            element = element.parent_slot.parent
        return element.value

    user.find(marker="member-workday-0-rest").click()  # 休みのあいだは、時刻の選択を開かない
    await settle()
    user.find(marker="open-member-workday-0-start-picker").click()
    await settle()
    assert not picker_open()
    user.find(marker="member-workday-0-rest").click()
    await settle()
    user.find(marker="open-member-workday-0-start-picker").click()
    await settle()
    assert picker_open()


def task_box(user: User) -> ui.checkbox:
    return user.find(marker="select-task-top-0").elements.pop()


async def test_the_preview_starts_with_everything_selected(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    assert view.preview is not None and view.preview.excluded == frozenset()
    assert task_box(user).value is True
    assert user.find(marker="preview-select-all").elements.pop().value is True
    assert user.find(marker="preview-select-count").elements.pop().text == "1 / 1 件を出力"


async def test_unchecking_a_task_excludes_it_and_updates_the_select_all_box(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter(), extra=Task("実装"))
    ids = [t.id for t in view.project.tasks]
    task_box(user).set_value(False)
    assert view.preview is not None and view.preview.excluded == frozenset({ids[0]})
    assert user.find(marker="preview-select-all").elements.pop().value is None  # 中間
    assert user.find(marker="preview-select-count").elements.pop().text == "1 / 2 件を出力"


async def test_the_select_all_box_unchecks_and_rechecks_every_task(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter(), extra=Task("実装"))
    user.find(marker="preview-select-all").elements.pop().set_value(False)
    assert view.preview is not None and view.preview.excluded == {t.id for t in view.project.tasks}
    assert user.find(marker="preview-select-all").elements.pop().value is False
    user.find(marker="preview-select-all").elements.pop().set_value(True)
    assert view.preview.excluded == frozenset()


async def test_the_selection_survives_changing_the_preview_settings(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    task_box(user).set_value(False)
    user.find(marker="preview-scale").elements.pop().set_value("週次")
    assert view.preview is not None and len(view.preview.excluded) == 1


async def test_a_new_preview_starts_with_everything_selected_again(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    task_box(user).set_value(False)
    view.exit_preview()
    view.enter_preview()
    assert view.preview is not None and view.preview.excluded == frozenset()


async def test_save_plantuml_leaves_out_the_unchecked_tasks(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    view = await open_preview(user, tmp_path, FakeExporter(path=target), extra=Task("外す", planned_start=datetime(2026, 10, 8, 9), planned_end=datetime(2026, 10, 9, 18)))
    user.find(marker="select-task-top-1").elements.pop().set_value(False)
    view.snapshot = asdict(view.project)  # open_preview がタスクを足すので、保存の直前を基準にする
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    text = target.read_text(encoding="utf-8")
    assert "[設計]" in text and "[外す]" not in text
    assert view.preview is not None and not view.is_dirty()


async def test_save_plantuml_with_every_task_unchecked_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "chart.puml")
    await open_preview(user, tmp_path, exporter)
    task_box(user).set_value(False)
    user.find(marker="preview-plantuml").click()
    await user.should_see("出力できるタスクがありません")
    assert exporter.asked == []


async def test_save_image_leaves_out_the_unchecked_rows_and_restores_them(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "chart.png")
    view = await open_preview(user, tmp_path, exporter, extra=Task("実装"))
    seen: list[tuple[int, int]] = []
    exporter.on_capture = lambda: seen.append(
        (len(view.gantt.task_rows), sum("select-task-top-0" in e._markers for e in view.gantt.client.elements.values()))
    )
    user.find(marker="select-task-top-1").elements.pop().set_value(False)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: (tmp_path / "chart.png").exists())
    assert seen == [(1, 0)]  # 撮る間は、外した行もチェックボックスもない
    assert await wait_until(lambda: len(view.gantt.task_rows) == 2)
    await user.should_see(marker="select-task-top-1")  # 撮ったあとは、もとに戻る
    assert view.preview is not None and len(view.preview.excluded) == 1


async def test_save_image_with_every_task_unchecked_notifies_and_captures_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "chart.png")
    await open_preview(user, tmp_path, exporter)
    task_box(user).set_value(False)
    user.find(marker="preview-save").click()
    await user.should_see("出力するタスクがありません")
    assert exporter.captured == [] and exporter.asked == []


async def test_save_plantuml_warns_when_a_same_day_handover_looks_over_100_percent(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    members = [Member("田中")]
    a = Task("前", planned_start=datetime(2026, 10, 13, 9), planned_end=datetime(2026, 10, 14, 12), assignees=[Assignee("田中", 0.6)])
    b = Task("後", planned_start=datetime(2026, 10, 14, 13), planned_end=datetime(2026, 10, 15, 18), assignees=[Assignee("田中", 0.6)])
    view = await open_preview(user, tmp_path, FakeExporter(path=target), extra=a)
    view.project.members = members
    view.save_task((), None, b)
    view.snapshot = asdict(view.project)
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    await user.should_see("田中 10/14")
    await user.should_see("保存しました")


async def test_save_plantuml_shows_no_overload_warning_normally(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    await open_preview(user, tmp_path, FakeExporter(path=target))
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    await user.should_see("保存しました")
    await user.should_not_see("日単位")


async def test_editing_one_week_changes_only_that_week_and_the_union(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    weeks = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    task = Task(
        "実装",
        planned_start=datetime(2026, 10, 5),
        planned_end=datetime(2026, 10, 19),
        effort_hours=20.0,
        assignees=[Assignee("田中"), Assignee("鈴木")],
        weekly_crew=weeks,
    )
    project = Project("既存", members=[Member("田中"), Member("鈴木")], sections=[Section("開発", [task])])
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="task-0-0")
    with user.client:
        view.edit_week_crew((0,), 0, 1)
    await user.should_see("第2週")
    with user.client:
        user.find(marker="week-edit-assignee-2").elements.pop().set_value("")
    user.find(marker="week-edit-save").click()
    after = view.project.sections[0].tasks[0]
    assert after.weekly_crew == [[Assignee("田中")], [Assignee("田中")]]
    assert after.assignees == [Assignee("田中")]  # 和集合に整う
    assert view.is_dirty()


async def test_editing_a_week_past_the_defined_ones_adds_the_weeks_in_between(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    weeks = [[Assignee("田中")], [Assignee("田中")]]
    task = Task(
        "実装",
        planned_start=datetime.combine(date.today(), time.min),
        planned_end=datetime.combine(date.today() + timedelta(days=21), time.min),  # 3 週ぶんの棒。第3週は定義がなく、最後の週の担当が続く
        assignees=[Assignee("田中")],
        weekly_crew=weeks,
    )
    project = Project(
        "既存", base_date=date.today(), members=[Member("田中"), Member("鈴木")], sections=[Section("開発", [task])]
    )
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    await user.should_see(marker="week-chip-0-0-2")
    user.find(marker="week-chip-0-0-2").click()
    await user.should_see("第3週")
    user.find(marker="week-edit-assignee-add").click()
    await user.should_see(marker="week-edit-assignee-2")
    with user.client:
        user.find(marker="week-edit-assignee-2").elements.pop().set_value("鈴木")
    user.find(marker="week-edit-save").click()
    after = view.project.sections[0].tasks[0]
    assert after.weekly_crew == [[Assignee("田中")], [Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    assert after.assignees == [Assignee("田中"), Assignee("鈴木")]


async def test_toggle_weeks_splits_into_every_week_and_back(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    task = Task(
        "実装",
        planned_start=datetime.combine(date.today(), time.min),
        planned_end=datetime.combine(date.today() + timedelta(days=15), time.min),
        assignees=[Assignee("田中")],
    )
    project = Project(
        "既存", base_date=date.today(), members=[Member("田中")], sections=[Section("開発", [task])]
    )
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.toggle_weeks((0,), 0)
    assert view.project.sections[0].tasks[0].weekly_crew == [[Assignee("田中")]] * 3  # 15 日 = 3 週
    assert view.is_dirty()
    view.project.sections[0].tasks[0].weekly_crew[0] = [Assignee("田中", 0.5)]
    view.toggle_weeks((0,), 0)
    back = view.project.sections[0].tasks[0]
    assert (back.weekly_crew, back.assignees) == ([], [Assignee("田中", 0.5)])  # 第1週の担当が全期間の担当に戻る
