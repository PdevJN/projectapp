from datetime import date

import pytest
from nicegui.testing import User

from projectapp.gantt import ViewOptions
from projectapp.models import Project, Section, Status, Task
from test_gantt import mount_chart, mount_with


def menu_project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        sections=[
            Section(
                "開発",
                [
                    Task("通常", id="a", effort_hours=4.0),
                    Task("実行中", id="b", status=Status.RUNNING),
                ],
            )
        ],
        tasks=[Task("直下", id="t")],
    )


@pytest.mark.parametrize(
    ("marker", "event"),
    [
        ("context-edit", "edit_task"),
        ("context-decompose", "decompose_task"),
        ("context-extra-effort", "add_extra_effort"),
        ("context-copy", "copy_task"),
        ("context-rename", "rename_task"),
        ("context-delete", "delete_task"),
    ],
)
async def test_each_menu_item_acts_on_the_right_clicked_task(
    user: User, marker: str, event: str
) -> None:
    charts, recorder = mount_chart(menu_project())
    await user.open("/")
    charts[0].open_menu((0,), 0)
    user.find(marker=marker).click()
    assert recorder.events == [(event, ((0,), 0))]


async def test_the_menu_acts_on_a_task_directly_under_the_root(user: User) -> None:
    charts, recorder = mount_chart(menu_project())
    await user.open("/")
    charts[0].open_menu((), 0)
    user.find(marker="context-rename").click()
    assert recorder.events == [("rename_task", ((), 0))]


async def test_decompose_is_disabled_for_a_task_that_cannot_be_decomposed(
    user: User,
) -> None:
    charts, _ = mount_chart(menu_project())
    await user.open("/")
    item = user.find(marker="context-decompose").elements.pop()
    charts[0].open_menu((0,), 1)  # 実行中
    assert item.props.get("disable") is True
    charts[0].open_menu((0,), 0)
    assert not item.props.get("disable")


async def test_every_row_opens_the_shared_menu_on_right_click(user: User) -> None:
    mount_chart(menu_project())
    await user.open("/")
    for marker in ("row-0-0", "row-0-1", "row-top-0"):
        row = user.find(marker=marker).elements.pop()
        listeners = [
            ev for ev in row._event_listeners.values() if ev.type == "contextmenu"
        ]
        handler = listeners[0].js_handler or ""
        assert "preventDefault" in handler
        assert (
            ".show(e)" in handler and "qRef" not in handler
        )  # QMenu は getElement が直接返す(qRef は無い)


async def test_read_only_rows_have_no_menu(user: User) -> None:
    mount_with(menu_project(), ViewOptions(read_only=True))
    await user.open("/")
    row = user.find(marker="row-0-0").elements.pop()
    assert not [ev for ev in row._event_listeners.values() if ev.type == "contextmenu"]


async def test_pressing_anywhere_outside_the_menu_closes_it(user: User) -> None:
    charts, _ = mount_chart(menu_project())
    await user.open("/")
    js = charts[0].menu_close_js()
    assert "pointerdown" in js and ".q-menu" in js
    assert f"getElement({charts[0].menu.id}).hide()" in js  # type: ignore[union-attr]


async def test_the_menu_is_compact(user: User) -> None:
    from projectapp.gantt import CONTEXT_MENU_CSS

    charts, _ = mount_chart(menu_project())
    await user.open("/")
    assert "app-context-menu" in charts[0].menu.classes  # type: ignore[union-attr]
    assert (
        "min-height: 26px" in CONTEXT_MENU_CSS and "font-size: 12px" in CONTEXT_MENU_CSS
    )


async def test_the_toolbar_shows_no_browser_menu_on_right_click(user: User) -> None:
    # 検索欄・担当の切り替えでは、WebView 標準のメニュー(サービス・自動入力など)を出さない
    mount_chart(menu_project())
    await user.open("/")
    toolbar = user.find(marker="chart-toolbar").elements.pop()
    listeners = [
        ev for ev in toolbar._event_listeners.values() if ev.type == "contextmenu"
    ]
    assert listeners and "preventDefault" in (listeners[0].js_handler or "")


async def test_extra_effort_is_enabled_only_for_a_task_that_can_take_it(
    user: User,
) -> None:
    charts, _ = mount_chart(menu_project())
    await user.open("/")
    item = user.find(marker="context-extra-effort").elements.pop()
    charts[0].open_menu((0,), 1)  # 実行中だが工数がない
    assert item.props.get("disable") is True
    charts[0].open_menu((0,), 0)  # 工数 4h の通常タスク
    assert not item.props.get("disable")
