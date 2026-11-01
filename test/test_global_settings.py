from pathlib import Path

from nicegui.testing import User

from projectapp import config
from projectapp.views import MainView
from projectapp.calendar import save_cache
from test_views import make_view


async def open_view(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    return views[0]


def marker_order(view: MainView) -> list[str]:
    """ヘッダーの子要素のマーカーを、左から順に返す。"""
    return [
        marker
        for element in view.header_box.descendants()
        for marker in element._markers
    ]


async def test_the_header_has_a_settings_button_left_of_the_theme_button(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    await user.should_see(marker="open-global-settings")
    order = marker_order(view)
    assert order.index("open-folder") < order.index("open-global-settings")
    assert order.index("open-global-settings") < order.index("menu-theme")


async def test_the_dialog_slider_previews_applies_and_saves(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    user.find(marker="global-settings-ratio").elements.pop().set_value(80)
    assert view.gantt.open_ratio == 80  # すぐ反映
    user.find(marker="global-settings-apply").click()
    assert config.load_open_ratio(tmp_path) == 80
    assert view.open_ratio == 80


async def test_cancelling_the_dialog_restores_the_open_ratio(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    user.find(marker="global-settings-ratio").elements.pop().set_value(85)
    user.find(marker="global-settings-cancel").click()
    assert view.gantt.open_ratio == 70
    assert config.load_open_ratio(tmp_path) == 70


async def test_an_open_panel_follows_the_slider_preview_and_cancel_restores_it(
    user: User, tmp_path: Path
) -> None:
    config.save_main_split(70, tmp_path)
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    user.find(marker="global-settings-ratio").elements.pop().set_value(85)
    assert view.gantt.splitter.value == 85
    user.find(marker="global-settings-cancel").click()
    assert view.gantt.splitter.value == 70


async def test_a_folded_panel_stays_folded_while_the_slider_moves(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    user.find(marker="global-settings-ratio").elements.pop().set_value(85)
    assert view.gantt.splitter.value == 100


async def test_the_split_is_restored_at_start_and_saved_on_flush(
    user: User, tmp_path: Path
) -> None:
    config.save_main_split(60, tmp_path)
    view = await open_view(user, tmp_path)
    assert view.gantt.splitter.value == 60
    view.set_main_split(45)
    view.flush_main_split()
    assert config.load_main_split(tmp_path) == 45


async def test_flush_with_nothing_pending_writes_nothing(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    view.flush_main_split()
    assert "main_split" not in config.read_config(tmp_path)
