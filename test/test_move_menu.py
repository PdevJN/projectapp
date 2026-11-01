import asyncio
from datetime import date
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.shortcuts import label_for
from projectapp.views import MainView

KEYS = {
    "today": "go_today",
    "base": "go_base",
    "first": "go_first_task",
    "date": "go_date",
    "prev": "go_prev_week",
    "next": "go_next_week",
}


async def open_view(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(
            tmp_path, httpx.MockTransport(lambda request: httpx.Response(200))
        )
        views.append(view)
        view.build()

    await user.open("/")
    return views[0]


async def test_the_move_menu_has_the_six_items_in_order(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    assert list(view.gantt.move_items) == list(KEYS)
    ids = [user.find(marker=f"move-{key}").elements.pop().id for key in KEYS]
    assert ids == sorted(ids)
    await user.should_not_see(marker="today-button")
    await user.should_not_see(marker="move-button")


async def test_the_items_show_their_keys_and_a_reason_when_they_cannot_go(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    chart = view.gantt
    # 日程のあるタスクがないので、最初のタスクだけは押せず、右端に理由を出す
    assert chart.first_task_day() is None
    assert not chart.move_items["first"][0].enabled
    assert chart.move_items["first"][1].text == "移れるタスクがありません"
    for key in ("date", "prev", "next"):
        item, hint = chart.move_items[key]
        assert item.enabled and hint.text == label_for(KEYS[key])
    chart.set_period((date(2000, 1, 1), date(2000, 1, 31)))
    for _ in range(40):
        if "表示期間の外" in chart.move_items["base"][1].text:
            break
        await asyncio.sleep(0.05)
    assert "表示期間の外" in chart.move_items["base"][1].text


async def test_clicking_an_item_moves_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    sent: list[str] = []
    assert view.gantt.client is not None
    view.gantt.client.run_javascript = lambda code, **_: sent.append(code)  # type: ignore[method-assign]
    user.find(marker="move-next").click()
    assert len(sent) == 1
    user.find(marker="move-date").click()
    assert view.gantt.goto_dialog is not None and view.gantt.goto_dialog.value
