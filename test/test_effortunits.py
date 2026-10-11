import pytest

from projectapp.effortunits import (
    PRESET_HOURS,
    EffortUnit,
    from_hours,
    reference_text,
    to_hours,
)
from projectapp.forms import HOURS_DECIMALS


def test_the_decimals_match_the_form_rule() -> None:
    from projectapp.effortunits import DECIMALS

    assert DECIMALS == HOURS_DECIMALS


@pytest.mark.parametrize(
    "value, unit, hours",
    [
        (8, EffortUnit.HOURS, 8),
        (2, EffortUnit.DAYS, 13),
        (3, EffortUnit.WEEKS, 97.5),
        (1, EffortUnit.MONTHS, 130),
        (0.5, EffortUnit.DAYS, 3.25),
    ],
)
def test_to_hours(value: float, unit: EffortUnit, hours: float) -> None:
    assert to_hours(value, unit, 6.5) == hours


def test_hours_are_not_rounded_so_the_form_can_reject_extra_decimals() -> None:
    assert to_hours(1.234, EffortUnit.HOURS, 6.5) == 1.234


def test_other_units_round_to_two_decimals() -> None:
    assert to_hours(1.111, EffortUnit.DAYS, 6.5) == 7.22  # 7.2215


def test_from_hours_round_trips_exact_values() -> None:
    for unit in EffortUnit:
        assert from_hours(to_hours(2, unit, 6.5), unit, 6.5) == 2


def test_from_hours_rounds_the_display_to_two_decimals() -> None:
    assert from_hours(10, EffortUnit.DAYS, 6.5) == 1.54


@pytest.mark.parametrize("daily", [0, -1, float("nan"), float("inf")])
def test_an_unusable_daily_hours_uses_the_default(daily: float) -> None:
    assert to_hours(1, EffortUnit.DAYS, daily) == 6.5


def test_the_presets() -> None:
    assert PRESET_HOURS == (0.5, 1, 2, 4, 8)


def test_reference_text() -> None:
    assert reference_text(EffortUnit.HOURS, 6.5, 8) == ""
    assert reference_text(EffortUnit.DAYS, 6.5, 8) == "1日 = 6.5h(稼働可能時間)"
    assert reference_text(EffortUnit.WEEKS, 6.5, 8) == "1週 = 5日 × 6.5h = 32.5h"
    assert (
        reference_text(EffortUnit.MONTHS, 6.5, 8)
        == "1月 = 20日 × 6.5h = 130h / 参考: 標準 8h × 20日 = 160h"
    )
