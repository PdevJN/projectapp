"""工数の入力の単位(時間・日・週・月)の換算。NiceGUI に依存しない。工数は時間で保存する。"""

from enum import Enum
from math import isfinite

from projectapp.models import DEFAULT_DAILY_HOURS

DECIMALS = 2  # 時間の小数点以下の桁数(forms.HOURS_DECIMALS と同じ)
WORKDAYS_PER_WEEK = 5
WORKDAYS_PER_MONTH = 20
PRESET_HOURS = (0.5, 1, 2, 4, 8)


class EffortUnit(Enum):
    HOURS = "時間"
    DAYS = "日"
    WEEKS = "週"
    MONTHS = "月"


def _daily(daily_hours: float) -> float:
    return daily_hours if isfinite(daily_hours) and daily_hours > 0 else DEFAULT_DAILY_HOURS


def _factor(unit: EffortUnit, daily_hours: float) -> float:
    """単位 1 つあたりの時間。"""
    days = {
        EffortUnit.HOURS: None,
        EffortUnit.DAYS: 1,
        EffortUnit.WEEKS: WORKDAYS_PER_WEEK,
        EffortUnit.MONTHS: WORKDAYS_PER_MONTH,
    }[unit]
    return 1.0 if days is None else days * _daily(daily_hours)


def to_hours(value: float, unit: EffortUnit, daily_hours: float) -> float:
    """入力の数値を時間にする。時間のときは丸めない(桁数は、保存時のフォームが検証する)。"""
    if unit is EffortUnit.HOURS:
        return value
    return round(value * _factor(unit, daily_hours), DECIMALS)


def from_hours(hours: float, unit: EffortUnit, daily_hours: float) -> float:
    """時間を、その単位の表示の数値にする(表示だけを丸める)。"""
    if unit is EffortUnit.HOURS:
        return hours
    return round(hours / _factor(unit, daily_hours), DECIMALS)


def reference_text(unit: EffortUnit, daily_hours: float, standard_hours: float) -> str:
    """単位の換算の参考。月のときは、標準稼働時間での合計も並べる。"""
    daily = _daily(daily_hours)
    if unit is EffortUnit.DAYS:
        return f"1日 = {daily:g}h(稼働可能時間)"
    if unit is EffortUnit.WEEKS:
        return f"1週 = {WORKDAYS_PER_WEEK}日 × {daily:g}h = {WORKDAYS_PER_WEEK * daily:g}h"
    if unit is EffortUnit.MONTHS:
        return (
            f"1月 = {WORKDAYS_PER_MONTH}日 × {daily:g}h = {WORKDAYS_PER_MONTH * daily:g}h"
            f" / 参考: 標準 {standard_hours:g}h × {WORKDAYS_PER_MONTH}日 = {WORKDAYS_PER_MONTH * standard_hours:g}h"
        )
    return ""
