from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp import clock
from projectapp.calendar import save_cache
from projectapp.views import MainView

REAL = datetime(2026, 11, 3, 8, 15, 30)


def test_unset_uses_the_real_clock() -> None:
    assert clock.parse_simulation({}, REAL) == (None, None)
    assert clock.parse_simulation({clock.ENV_TODAY: "  "}, REAL) == (None, None)


def test_a_date_only_keeps_the_real_time_of_day() -> None:
    sim, warning = clock.parse_simulation({clock.ENV_TODAY: "2026-12-01"}, REAL)
    assert warning is None and sim is not None
    assert sim.fixed == datetime(2026, 12, 1, 8, 15, 30)
    assert REAL + sim.offset == sim.fixed and not sim.frozen


@pytest.mark.parametrize("text", ["2026-12-01T09:30", "2026-12-01 09:30:00"])
def test_a_datetime_sets_the_time_too(text: str) -> None:
    sim, _ = clock.parse_simulation({clock.ENV_TODAY: text}, REAL)
    assert sim is not None and sim.fixed.hour == 9 and sim.fixed.minute == 30
    assert sim.offset == sim.fixed - REAL


@pytest.mark.parametrize("word", ["1", "true", "YES", "on"])
def test_freeze_words(word: str) -> None:
    sim, _ = clock.parse_simulation(
        {clock.ENV_TODAY: "2026-12-01T09:30", clock.ENV_FREEZE: word}, REAL
    )
    assert sim is not None and sim.frozen


@pytest.mark.parametrize("text", ["tomorrow", "2026-13-40", "2026-12-01T09:30+09:00"])
def test_a_bad_value_warns_and_falls_back(text: str) -> None:
    sim, warning = clock.parse_simulation({clock.ENV_TODAY: text}, REAL)
    assert sim is None and warning is not None and clock.ENV_TODAY in warning


@pytest.fixture
def restore_clock():
    yield
    clock.configure({})


def test_now_follows_the_offset_and_ticks(restore_clock: None) -> None:
    clock.configure({clock.ENV_TODAY: "2030-01-02T03:04:05"})
    first = clock.now()
    assert first.date() == date(2030, 1, 2)
    assert clock.now() >= first  # 実時間で進む
    assert clock.today() == date(2030, 1, 2)


def test_a_frozen_clock_does_not_move(restore_clock: None) -> None:
    clock.configure({clock.ENV_TODAY: "2030-01-02T03:04:05", clock.ENV_FREEZE: "1"})
    assert clock.now() == clock.now() == datetime(2030, 1, 2, 3, 4, 5)


def test_unset_is_close_to_real(restore_clock: None) -> None:
    clock.configure({})
    assert abs(clock.now() - datetime.now()) < timedelta(seconds=2)
    assert clock.simulation() is None


async def open_view(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)

    @ui.page("/")
    def index() -> None:
        MainView(
            tmp_path, httpx.MockTransport(lambda request: httpx.Response(200))
        ).build()

    await user.open("/")


async def test_the_debug_chip_shows_only_when_simulating(
    user: User, tmp_path: Path, restore_clock: None
) -> None:
    clock.configure({clock.ENV_TODAY: "2030-01-02T03:04", clock.ENV_FREEZE: "1"})
    await open_view(user, tmp_path)
    chip = user.find(marker="debug-clock").elements.pop()
    assert isinstance(chip, ui.label) and chip.text == "DEBUG 2030-01-02 03:04 固定"


async def test_no_debug_chip_in_normal_use(user: User, tmp_path: Path) -> None:
    clock.configure({})
    await open_view(user, tmp_path)
    with pytest.raises(AssertionError):
        user.find(marker="debug-clock")
