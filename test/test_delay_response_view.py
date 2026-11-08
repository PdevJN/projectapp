from datetime import date
from pathlib import Path

from nicegui.testing import User

from projectapp.delay_response import DELAY_RESPONSE_CSS
from test_delay_response import opened


def test_the_band_css_uses_a_thick_dotted_border_and_its_own_colours() -> None:
    assert "3px dotted" in DELAY_RESPONSE_CSS
    assert "--delay-accent" in DELAY_RESPONSE_CSS
    assert "body.body--dark" in DELAY_RESPONSE_CSS  # ダークの値がある
    for banned in ("red", "#f44336", "#ffc107", "green"):
        assert banned not in DELAY_RESPONSE_CSS  # 遅れ・警告・取り戻せたの色は使わない


async def test_no_band_without_trials_and_a_band_with_them(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    await user.should_not_see(marker="delay-band")
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see(marker="delay-band")
    await user.should_see(marker="trial-ghost-top-0")
    await user.should_see(marker="trial-origin-top-0")
    await user.should_see(marker="trial-chip-top-0")
    await user.should_see(marker="trial-label-top-0")


async def test_the_band_shows_the_title_and_counts(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see("遅延対応")
    await user.should_see("試算中: 1 件の増員")


async def test_clear_button_removes_the_band(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see(marker="delay-band-clear")
    user.find(marker="delay-band-clear").click()
    await user.should_not_see(marker="delay-band")
    assert view.trials == {}


async def test_confirm_button_writes_weekly_crew(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see(marker="delay-band-confirm")
    user.find(marker="delay-band-confirm").click()
    await user.should_not_see(marker="delay-band")
    assert view.project.tasks[0].weekly_crew != []
    assert view.is_dirty()


async def test_context_menu_has_try_crew_and_drop(user: User, tmp_path: Path) -> None:
    await opened(user, tmp_path)
    await user.should_see(marker="context-try-crew")
    await user.should_see(marker="context-drop-trial")


async def test_week_chips_are_unchanged_when_there_are_no_trials(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.toggle_weeks((), 0)
    await user.should_see(marker="week-chip-top-0-0")
    await user.should_not_see(marker="delay-band")
    assert view.trial_results() == {}


async def test_the_drop_action_removes_the_trial(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.drop_trial_at((), 0)
    assert view.trials == {}
    await user.should_not_see(marker="delay-band")
