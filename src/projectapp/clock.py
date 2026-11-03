"""アプリの「今日・今」。デバッグ用に、環境変数で日時をずらしたり止めたりできる。NiceGUI に依存しない。

- `PROJECTAPP_TODAY`: `2026-11-15`(日付だけ。時刻は実際の時刻)・`2026-11-15T09:30`・`2026-11-15 09:30:00`。
  起動した瞬間をその日時として扱い、そこから実時間どおりに進める(実際の日時との差を起動時に 1 回だけ決める)。
- `PROJECTAPP_TODAY_FREEZE`: `1`・`true`・`yes`・`on` なら、時刻を進めず指定した日時で止める。
- 不正な値は警告を出し、実際の日時を使う。
"""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

ENV_TODAY = "PROJECTAPP_TODAY"
ENV_FREEZE = "PROJECTAPP_TODAY_FREEZE"
TRUE_WORDS = ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Simulation:
    """ずらした日時。`frozen`なら`fixed`のまま、そうでなければ実際の日時に`offset`を足す。"""

    offset: timedelta
    frozen: bool
    fixed: datetime  # 起動した瞬間の、ずらした日時


def parse_simulation(
    env: Mapping[str, str], real_now: datetime
) -> tuple[Simulation | None, str | None]:
    """環境変数から、ずらし方を読む。(ずらし方 または None, 警告 または None)。"""
    text = env.get(ENV_TODAY, "").strip()
    if not text:
        return None, None
    try:
        target = datetime.fromisoformat(text)
    except ValueError:
        return None, (
            f"{ENV_TODAY}={text!r} を読めません(例: 2026-11-15・2026-11-15T09:30)。"
            "実際の日時を使います"
        )
    if target.tzinfo is not None:
        return (
            None,
            f"{ENV_TODAY}={text!r} にタイムゾーンは指定できません。実際の日時を使います",
        )
    if len(text) <= 10:  # 日付だけ: 時刻は実際の時刻
        target = datetime.combine(target.date(), real_now.time())
    frozen = env.get(ENV_FREEZE, "").strip().lower() in TRUE_WORDS
    return Simulation(target - real_now, frozen, target), None


_simulation: Simulation | None = None


def configure(env: Mapping[str, str] | None = None) -> Simulation | None:
    """環境変数を読み直す(起動時に 1 回。テストでも使う)。不正な値は標準エラーに警告する。"""
    global _simulation
    found, warning = parse_simulation(
        os.environ if env is None else env, datetime.now()
    )
    if warning is not None:
        print(warning, file=sys.stderr)
    _simulation = found
    return found


def simulation() -> Simulation | None:
    return _simulation


def now() -> datetime:
    real = datetime.now()
    if _simulation is None:
        return real
    if _simulation.frozen:
        return _simulation.fixed
    return real + _simulation.offset


def today() -> date:
    return now().date()


configure()
