# タスクの追加・編集ダイアログの入力の見直し Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの追加・編集ダイアログを、レイアウトの切り替え・日付と時刻の省略入力・工数の単位とプリセット・担当者の割り当て率の出し入れで、登録しやすくする。

**Architecture:** 日付・時刻の整形と工数の単位換算は、NiceGUI に依存しない純粋関数(`dateinput.py`・`effortunits.py`)にする。ダイアログは同じ部品の表示・非表示でレイアウトを切り替え、値・変更判定・保存は今のまま。レイアウトの選択は `config.json` の `task_layout` に保存する。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、型検査は `uv run ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-11-task-dialog-input-design.md`

## Global Constraints

- コード規約(`.claude/RULE.md`): すべての関数に型引数と戻り値の型を書く。コメントは多くても 3 行以内。`uv run ty check src` を通す
- 画面の文言・コメント・コミットメッセージは日本語
- 保存形式(`version`)は変えない。工数は時間で保存する。隠した項目の値は保持し、保存でも失わない
- 既存のマーカー(`task-*`)は変えない。新しいマーカー: `task-layout`・`task-effort-unit`・`task-effort-preset-{0.5|1|2|4|8}`・`task-effort-reference`・`task-{start|end|deadline}-shortcut-{today|tomorrow|next-monday}`
- ダイアログの幅は `w-[44rem]`(`max-w-full` のまま)
- 日付の整形の `roll_forward`: 開始予定・完了予定・締切は真、実績は偽
- 工数の換算: `1日 = 稼働可能時間`、`1週 = 5日`、`1月 = 20日`。稼働可能時間が 0 以下・非有限なら 6.5h。時間の単位のときは丸めない(桁数の検証が、今のとおり働く)。ほかの単位は、時間を 2 桁に丸める
- コミットメッセージの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- テストの実行: `cd /Users/jun/Documents/opt/work/projectapp && uv run pytest -n auto -q`

## Review Focus

- 日付の省略形: うるう日(`2/29`)、年またぎ(12 月に `1/5`)、今日と同じ日(翌年にしない)、`2026-1` のような入力の途中の値を壊さない
- 工数: 単位を切り替えて戻しても時間が変わらない(丸めのずれを溜めない)、空欄・0・小数 3 桁の入力
- レイアウトを `予定・実績` に切り替えて保存しても、隠した項目(カテゴリ・担当・先行・優先度・リンク・色)が失われない
- チェックポイントとレイアウトの組み合わせ(どのレイアウトでも、開始予定・工数・担当・実績が隠れる)
- 割り当て率が隠れている行(メンバー「(なし)」)の値が、保存・変更判定に影響しない

---

### Task 1: 日付・時刻の整形(純粋関数)

**Files:**
- Create: `src/projectapp/dateinput.py`
- Test: `test/test_dateinput.py`

**Interfaces:**
- Produces:
  - `DATE_FORMAT = "%Y-%m-%d"`
  - `SHORTCUT_LABELS: dict[str, str]`(`{"today": "今日", "tomorrow": "明日", "next-monday": "来週月"}`)
  - `parse_date_input(text: str, today: date, roll_forward: bool) -> str | None`
  - `shortcut_dates(today: date) -> dict[str, date]`(キーは `SHORTCUT_LABELS` と同じ)
  - `parse_time_input(text: str) -> str | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dateinput.py`:

```python
from datetime import date

import pytest

from projectapp.dateinput import SHORTCUT_LABELS, parse_date_input, parse_time_input, shortcut_dates

TODAY = date(2026, 10, 12)  # 月曜


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026-10-15", "2026-10-15"),
        ("2026/1/5", "2026-01-05"),
        ("20261015", "2026-10-15"),
        ("10/15", "2026-10-15"),
        ("1015", "2026-10-15"),
        ("  10/15 ", "2026-10-15"),
        ("10/12", "2026-10-12"),  # 今日と同じ日は、翌年にしない
    ],
)
def test_parse_date_input_reads_the_short_forms(text: str, expected: str) -> None:
    assert parse_date_input(text, TODAY, roll_forward=True) == expected


def test_a_past_day_rolls_to_next_year_only_when_asked() -> None:
    assert parse_date_input("10/01", TODAY, roll_forward=True) == "2027-10-01"
    assert parse_date_input("0101", TODAY, roll_forward=True) == "2027-01-01"
    assert parse_date_input("10/01", TODAY, roll_forward=False) == "2026-10-01"


def test_a_full_date_never_rolls() -> None:
    assert parse_date_input("2026-10-01", TODAY, roll_forward=True) == "2026-10-01"


@pytest.mark.parametrize("text", ["", "abc", "2026-1", "10/", "13/01", "1032", "2026-02-30", "10-15", "１０/１５"])
def test_unreadable_dates_are_none(text: str) -> None:
    assert parse_date_input(text, TODAY, roll_forward=True) is None


def test_leap_day_needs_a_leap_year() -> None:
    assert parse_date_input("2/29", date(2027, 10, 1), roll_forward=False) is None  # 2027 は平年
    assert parse_date_input("2/29", date(2028, 1, 10), roll_forward=True) == "2028-02-29"
    assert parse_date_input("2/29", date(2028, 3, 1), roll_forward=True) is None  # 翌年(2029)は平年


def test_the_year_boundary_rolls_in_december() -> None:
    assert parse_date_input("1/5", date(2026, 12, 20), roll_forward=True) == "2027-01-05"


@pytest.mark.parametrize(
    "today, next_monday",
    [
        (date(2026, 10, 12), date(2026, 10, 19)),  # 月曜は +7 日
        (date(2026, 10, 14), date(2026, 10, 19)),  # 水曜
        (date(2026, 10, 18), date(2026, 10, 19)),  # 日曜は翌日
    ],
)
def test_shortcut_dates(today: date, next_monday: date) -> None:
    dates = shortcut_dates(today)
    assert list(dates) == list(SHORTCUT_LABELS)
    assert dates["today"] == today
    assert dates["tomorrow"] == date.fromordinal(today.toordinal() + 1)
    assert dates["next-monday"] == next_monday


@pytest.mark.parametrize(
    "text, expected",
    [("9", "09:00"), ("17", "17:00"), ("930", "09:30"), ("0930", "09:30"), ("1730", "17:30"), ("9:30", "09:30"), ("09:05", "09:05"), (" 9 ", "09:00")],
)
def test_parse_time_input_reads_the_short_forms(text: str, expected: str) -> None:
    assert parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "24", "24:00", "9:60", "975", "9:5", "12345", "9:3:0", "９"])
def test_unreadable_times_are_none(text: str) -> None:
    assert parse_time_input(text) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dateinput.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.dateinput'`)

- [ ] **Step 3: 実装する**

`src/projectapp/dateinput.py`:

```python
"""日付と時刻の入力の整形(省略形の読み取りと、ショートカットの日付)。NiceGUI に依存しない。"""

import re
from datetime import date, timedelta

DATE_FORMAT = "%Y-%m-%d"
SHORTCUT_LABELS = {"today": "今日", "tomorrow": "明日", "next-monday": "来週月"}


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_day(today: date, month: int, day: int, roll_forward: bool) -> date | None:
    """年を省いた日付。年は今年で、その日が過ぎていて roll_forward なら、翌年にする。"""
    found = _make(today.year, month, day)
    if found is not None and roll_forward and found < today:
        return _make(today.year + 1, month, day)
    return found


def parse_date_input(text: str, today: date, roll_forward: bool) -> str | None:
    """日付の省略形を `YYYY-MM-DD` にする。読めないとき、存在しない日付のときは None。"""
    value = text.strip()
    found: date | None
    if m := re.fullmatch(r"([0-9]{4})[-/]([0-9]{1,2})[-/]([0-9]{1,2})", value):
        found = _make(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.fullmatch(r"([0-9]{4})([0-9]{2})([0-9]{2})", value):
        found = _make(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})", value):
        found = _month_day(today, int(m[1]), int(m[2]), roll_forward)
    elif m := re.fullmatch(r"([0-9]{2})([0-9]{2})", value):
        found = _month_day(today, int(m[1]), int(m[2]), roll_forward)
    else:
        return None
    return found.strftime(DATE_FORMAT) if found else None


def shortcut_dates(today: date) -> dict[str, date]:
    """ショートカットの日付。来週月は、今日が属する週(月曜始まり)の次の週の月曜。"""
    return {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "next-monday": today + timedelta(days=7 - today.weekday()),
    }


def parse_time_input(text: str) -> str | None:
    """時刻の省略形(`9`・`930`・`0930`・`9:30`)を `HH:MM` にする。読めないとき、範囲外のときは None。"""
    value = text.strip()
    if m := re.fullmatch(r"([0-9]{1,2}):([0-9]{2})", value):
        hour, minute = int(m[1]), int(m[2])
    elif m := re.fullmatch(r"[0-9]{1,2}", value):
        hour, minute = int(value), 0
    elif m := re.fullmatch(r"([0-9]{1,2})([0-9]{2})", value):
        hour, minute = int(m[1]), int(m[2])
    else:
        return None
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"
```

(`[0-9]` を使い、全角の数字は読まない。`re.fullmatch` の `\d` は全角にも一致するため。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dateinput.py -q`
Expected: PASS

- [ ] **Step 5: 型検査とコミット**

Run: `uv run ty check src`
Expected: `All checks passed!`

```bash
git add src/projectapp/dateinput.py test/test_dateinput.py
git commit -m "feat: 日付と時刻の省略形を読む純粋関数を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 工数の単位換算(純粋関数)

**Files:**
- Create: `src/projectapp/effortunits.py`
- Test: `test/test_effortunits.py`

**Interfaces:**
- Consumes: `projectapp.models.DEFAULT_DAILY_HOURS`
- Produces:
  - `class EffortUnit(Enum)`: `HOURS="時間"`・`DAYS="日"`・`WEEKS="週"`・`MONTHS="月"`
  - `WORKDAYS_PER_WEEK = 5`、`WORKDAYS_PER_MONTH = 20`、`PRESET_HOURS = (0.5, 1, 2, 4, 8)`
  - `to_hours(value: float, unit: EffortUnit, daily_hours: float) -> float`
  - `from_hours(hours: float, unit: EffortUnit, daily_hours: float) -> float`
  - `reference_text(unit: EffortUnit, daily_hours: float, standard_hours: float) -> str`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_effortunits.py`:

```python
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
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_effortunits.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 実装する**

`src/projectapp/effortunits.py`:

```python
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
    """入力の数値を時間にする。時間のときは丸めない(桁数の検証は、保存時のフォームが行う)。"""
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
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_effortunits.py -q`
Expected: PASS

- [ ] **Step 5: 型検査とコミット**

Run: `uv run ty check src`
Expected: `All checks passed!`

```bash
git add src/projectapp/effortunits.py test/test_effortunits.py
git commit -m "feat: 工数の単位(時間・日・週・月)の換算を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: レイアウトの選択の保存

**Files:**
- Modify: `src/projectapp/config.py`(`TASK_LAYOUTS`・`load_task_layout`・`save_task_layout`)
- Test: `test/test_config.py`

**Interfaces:**
- Produces: `TASK_LAYOUTS = ("all", "schedule")`、`load_task_layout(base_dir: Path = BASE_DIR) -> str`(不正・なし → `"all"`)、`save_task_layout(layout: str, base_dir: Path = BASE_DIR) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_config.py` の末尾に足す(import に `load_task_layout`・`save_task_layout` を足す。ファイルの `tmp_path` の使い方は既存のテストに合わせる)。

```python
def test_the_task_layout_defaults_to_all(tmp_path: Path) -> None:
    assert load_task_layout(tmp_path) == "all"


def test_the_task_layout_round_trips_and_keeps_other_keys(tmp_path: Path) -> None:
    save_zoom(120, tmp_path)
    save_task_layout("schedule", tmp_path)
    assert load_task_layout(tmp_path) == "schedule"
    assert load_zoom(tmp_path) == 120


@pytest.mark.parametrize("value", ["x", 1, None, True, ["all"]])
def test_an_invalid_task_layout_falls_back_to_all(tmp_path: Path, value: object) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"task_layout": value}), encoding="utf-8")
    assert load_task_layout(tmp_path) == "all"
```

(`json`・`pytest`・`save_zoom`・`load_zoom` が import されていなければ足す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 実装する**

`src/projectapp/config.py` の `THEMES = ...` の下に `TASK_LAYOUTS = ("all", "schedule")  # タスクのダイアログのレイアウト(すべて・予定と実績)` を足し、`save_theme` の下に足す。

```python
def load_task_layout(base_dir: Path = BASE_DIR) -> str:
    layout = read_config(base_dir).get("task_layout", "all")
    return layout if isinstance(layout, str) and layout in TASK_LAYOUTS else "all"


def save_task_layout(layout: str, base_dir: Path = BASE_DIR) -> None:
    update_config({"task_layout": layout}, base_dir)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/config.py test/test_config.py
git commit -m "feat: タスクのダイアログのレイアウトの選択を config.json に保存する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 日付・時刻の入力(省略形・ショートカット・コンパクト)

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`add_picker`:96、`moment_column`:109、`DateTimeFields._column`:187、ダイアログの幅:733)
- Test: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 の `parse_date_input`・`parse_time_input`・`shortcut_dates`・`SHORTCUT_LABELS`・`DATE_FORMAT`
- Produces:
  - `task_dialog.today() -> date`(テストで差し替える)
  - `add_picker(field, picker_factory, icon, key, fmt, normalize: Callable[[str], str | None] | None = None) -> None`(`preview.py` の呼び出しは、引数なしのまま動く)
  - マーカー `task-{key}-shortcut-{today|tomorrow|next-monday}`(`key` は `start`・`end`・`deadline`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` の import に `from nicegui import events` を足し、`open_dialog` の下に足す。

```python
TODAY = date(2026, 10, 12)  # 月曜


def blur(user: User, marker: str) -> None:
    """入力欄を離れたときの処理(blur)を呼ぶ。User のシミュレーションには、フォーカスの移動がないため。"""
    element = user.find(marker=marker).elements.pop()
    for listener in element._event_listeners.values():
        if listener.type == "blur":
            events.handle_event(
                listener.handler, events.GenericEventArguments(sender=element, client=element.client, args={})
            )


@pytest.fixture
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr("projectapp.task_dialog.today", lambda: TODAY)
    return TODAY
```

(`test_dates_only_fill_the_default_times` などの手前でなく、ファイルの末尾に足す。)

```python
async def test_blur_completes_short_dates_and_times(user: User, fixed_today: date) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-use-time").click()
    user.find(marker="task-start-date").type("10/15")
    blur(user, "task-start-date")
    assert user.find(marker="task-start-date").elements.pop().value == "2026-10-15"
    user.find(marker="task-start-time").clear().type("930")
    blur(user, "task-start-time")
    assert user.find(marker="task-start-time").elements.pop().value == "09:30"


async def test_planned_dates_roll_to_next_year_but_actual_dates_do_not(user: User, fixed_today: date) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-deadline-date").type("10/01")
    blur(user, "task-deadline-date")
    assert user.find(marker="task-deadline-date").elements.pop().value == "2027-10-01"
    user.find(marker="task-actual-start-date").type("10/01")
    blur(user, "task-actual-start-date")
    assert user.find(marker="task-actual-start-date").elements.pop().value == "2026-10-01"


async def test_blur_leaves_unreadable_text_as_typed(user: User, fixed_today: date) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-1")  # 入力の途中
    blur(user, "task-start-date")
    assert user.find(marker="task-start-date").elements.pop().value == "2026-1"


async def test_shortcut_chips_fill_the_date(user: User, fixed_today: date) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-shortcut-tomorrow").click()
    user.find(marker="task-deadline-shortcut-next-monday").click()
    assert user.find(marker="task-start-date").elements.pop().value == "2026-10-13"
    assert user.find(marker="task-deadline-date").elements.pop().value == "2026-10-19"
    user.find(marker="task-save").click()
    assert saved[0].planned_start == datetime(2026, 10, 13, 9, 0)
    assert saved[0].deadline == datetime(2026, 10, 19, 18, 0)


async def test_the_end_chips_show_only_while_the_end_is_editable(user: User, fixed_today: date) -> None:
    mount_dialog(Task("a", effort_hours=8.0), [])
    await open_dialog(user)
    await user.should_not_see(marker="task-end-shortcut-today")  # 工数があり、算出値のとき
    user.find(marker="task-end-manual").click()
    await user.should_see(marker="task-end-shortcut-today")


async def test_date_and_time_share_a_row_and_the_dialog_is_wider(user: User) -> None:
    mount_dialog(Task("a", planned_start=datetime(2026, 10, 5, 10, 0)), [])
    await open_dialog(user)
    day = user.find(marker="task-start-date").elements.pop()
    clock = user.find(marker="task-start-time").elements.pop()
    assert day.parent_slot.parent.parent_slot.parent is clock.parent_slot.parent.parent_slot.parent  # 同じ行
    card = next(a for a in day.ancestors() if isinstance(a, ui.card))
    assert "w-[44rem]" in card.classes
```

(「同じ行」の検査は、`ui.input` の親(`add_picker` の slot をまたぐので、要素の親を 1 つたどった先)が一致するかを見る。たどり方がずれて落ちるときは、`day.parent_slot.parent` と `clock.parent_slot.parent` が同じ `ui.row` になる形に、`_column` を合わせて、検査をその 1 段に直す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -k "blur or shortcut or share_a_row"`
Expected: FAIL(`today` がない / マーカーがない)

- [ ] **Step 3: 実装する**

`task_dialog.py` の import に足す。

```python
from projectapp.dateinput import (
    DATE_FORMAT,
    SHORTCUT_LABELS,
    parse_date_input,
    parse_time_input,
    shortcut_dates,
)
```

`add_picker` の前に足す。

```python
def today() -> date:
    """今日。テストで差し替える。"""
    return date.today()


def date_normalizer(roll_forward: bool) -> Callable[[str], str | None]:
    return lambda text: parse_date_input(text, today(), roll_forward)


def normalize_field(field: ui.input, normalize: Callable[[str], str | None]) -> None:
    """入力欄を離れたとき、省略形を正式な形へ直す。読めない値(入力の途中を含む)は、そのまま残す。"""
    text = field.value or ""
    fixed = normalize(text) if text.strip() else None
    if fixed is not None and fixed != text:
        field.set_value(fixed)
```

`add_picker` の定義を、引数 `normalize: Callable[[str], str | None] | None = None` を足し、本体の先頭に足す。

```python
    if normalize is not None:
        field.on("blur", lambda _e: normalize_field(field, normalize))
```

`moment_column`(実績の日付・時刻)の 2 つの `add_picker` に、順に `date_normalizer(False)`・`parse_time_input` を渡す。

`DateTimeFields._column` を次に置き換える。

```python
    def _column(
        self,
        label: str,
        key: str,
        moment: datetime | None,
        use_time: bool,
        header: Callable[[], None] | None = None,
    ) -> tuple[ui.input, ui.input, ui.checkbox, ui.column]:
        default = self._defaults[key]
        with ui.column().classes("flex-1 gap-0 min-w-0"):
            ui.label(label).classes("text-caption text-grey")
            if header is not None:
                header()
            with ui.column().classes("w-full gap-0") as editable:
                with ui.row().classes("w-full items-start no-wrap gap-2"):
                    day = ui.input("日付", value=moment.strftime(DATE_FORMAT) if moment else "")
                    day.classes("flex-1 min-w-0").mark(f"task-{key}-date")
                    add_picker(day, ui.date, "event", f"{key}-date", "%Y-%m-%d", date_normalizer(True))
                    clock = ui.input("時刻", value=(moment.time() if moment else default).strftime("%H:%M"))
                    clock.classes("w-28").mark(f"task-{key}-time")
                    add_picker(clock, ui.time, "access_time", f"{key}-time", "%H:%M", parse_time_input)
                with ui.row().classes("w-full items-center no-wrap gap-1"):
                    for name, text in SHORTCUT_LABELS.items():
                        ui.chip(
                            text,
                            on_click=lambda _e, n=name, d=day: d.set_value(
                                shortcut_dates(today())[n].strftime(DATE_FORMAT)
                            ),
                        ).props("dense clickable outline size=sm").mark(f"task-{key}-shortcut-{name}")
                    ui.space()
                    checkbox = (
                        ui.checkbox("時刻を指定", value=use_time, on_change=lambda e, k=key: self._show_time(k, e.value))
                        .props("dense")
                        .mark(f"task-{key}-use-time")
                    )
        return day, clock, checkbox, editable
```

`open_task_dialog` の `ui.card().classes("w-[36rem] max-w-full")` を `w-[44rem]` にする。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py -q`
Expected: PASS(既存のテストも通る。落ちたら、旧い並び(縦)を前提にした検査だけを、新しい並びに直す)

- [ ] **Step 5: 型検査とコミット**

Run: `uv run ty check src && uv run pytest -n auto -q`
Expected: `All checks passed!`、全件 PASS

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "feat: 日付・時刻の省略形とショートカットを足し、開始・完了の並びをコンパクトにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 工数の単位・プリセット・参考値

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`EffortField` を足す。`open_task_dialog` の工数:777 付近と `on_effort_change`)
- Test: `test/test_task_dialog.py`(工数のラベルを前提にした既存のテストがあれば直す)

**Interfaces:**
- Consumes: Task 2 の `EffortUnit`・`PRESET_HOURS`・`to_hours`・`from_hours`・`reference_text`、`forms.STANDARD_WORK_HOURS`
- Produces: `class EffortField`
  - `__init__(self, hours: float | None, daily_hours: float, standard_hours: float) -> None`
  - `value -> float | None`(property。常に時間)
  - `on_value_change(self, callback: Callable[[float | None], object]) -> None`
  - `set_visibility(self, visible: bool) -> None`
  - マーカー: 数値 `task-effort`、単位 `task-effort-unit`、プリセット `task-effort-preset-{0.5|1|2|4|8}`、参考 `task-effort-reference`

- [ ] **Step 1: 失敗するテストを書く**

```python
from projectapp.effortunits import EffortUnit


def set_unit(user: User, unit: EffortUnit) -> None:
    user.find(marker="task-effort-unit").elements.pop().set_value(unit)


async def test_the_effort_unit_converts_to_hours_on_save(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort").type("2")
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 13.0  # 2日 × 6.5h


@pytest.mark.parametrize(
    "unit, typed, hours",
    [(EffortUnit.HOURS, "8", 8.0), (EffortUnit.WEEKS, "3", 97.5), (EffortUnit.MONTHS, "1", 130.0)],
)
async def test_each_unit_converts(user: User, unit: EffortUnit, typed: str, hours: float) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, unit)
    user.find(marker="task-effort").type(typed)
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == hours


async def test_the_unit_follows_the_daily_hours(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, daily_hours=8.0)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort").type("2")
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 16.0


async def test_switching_the_unit_does_not_change_the_hours(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-effort").type("10")
    set_unit(user, EffortUnit.DAYS)
    assert user.find(marker="task-effort").elements.pop().value == 1.54  # 表示だけ丸める
    set_unit(user, EffortUnit.HOURS)
    assert user.find(marker="task-effort").elements.pop().value == 10
    set_unit(user, EffortUnit.DAYS)  # 日のまま保存しても、時間は 10h
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 10.0


async def test_a_preset_chip_sets_the_hours_in_the_current_unit(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort-preset-4").click()
    assert user.find(marker="task-effort").elements.pop().value == 0.62  # 4h = 0.615日(表示)
    user.find(marker="task-save").click()
    assert saved[0].effort_hours == 4.0


async def test_the_reference_shows_the_month_comparison(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    reference = user.find(marker="task-effort-reference").elements.pop()
    assert reference.text == ""
    set_unit(user, EffortUnit.MONTHS)
    assert reference.text == "1月 = 20日 × 6.5h = 130h / 参考: 標準 8h × 20日 = 160h"
    set_unit(user, EffortUnit.DAYS)
    assert reference.text == "1日 = 6.5h(稼働可能時間)"


async def test_an_existing_effort_opens_in_hours(user: User) -> None:
    mount_dialog(Task("a", effort_hours=12.0), [])
    await open_dialog(user)
    assert user.find(marker="task-effort").elements.pop().value == 12.0
    assert user.find(marker="task-effort-unit").elements.pop().value is EffortUnit.HOURS


async def test_hours_with_three_decimals_are_still_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-effort").type("1.234")
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("小数点以下")


async def test_the_effort_change_updates_the_computed_end_and_the_conversion(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-05")
    set_unit(user, EffortUnit.DAYS)
    user.find(marker="task-effort").type("2")
    assert user.find(marker="task-end-computed").elements.pop().value != ""  # 13h から算出
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -k "effort or unit or preset or reference"`
Expected: FAIL(`task-effort-unit` がない)

- [ ] **Step 3: 実装する**

import に足す。

```python
from projectapp.effortunits import PRESET_HOURS, EffortUnit, from_hours, reference_text, to_hours
```

`forms` からの import に `STANDARD_WORK_HOURS` を足す。`PriorityChips` の前に足す。

```python
class EffortField:
    """工数の入力。数値・単位・プリセットのチップ・換算の参考。値(`value`)は、常に時間。
    数値を編集すると時間を持ち直し、単位だけを切り替えたときは、時間を変えずに表示だけを直す。"""

    def __init__(self, hours: float | None, daily_hours: float, standard_hours: float) -> None:
        self._hours = hours
        self._unit = EffortUnit.HOURS
        self._daily = daily_hours
        self._standard = standard_hours
        self._syncing = False
        self._callbacks: list[Callable[[float | None], object]] = []
        with ui.column().classes("flex-1 gap-0 min-w-0") as self.container:
            with ui.row().classes("w-full items-start no-wrap gap-2"):
                self.number = ui.number("工数", value=hours, min=0).classes("flex-1 min-w-0").mark("task-effort")
                self.unit = (
                    ui.select({u: u.value for u in EffortUnit}, value=EffortUnit.HOURS)
                    .classes("w-24")
                    .mark("task-effort-unit")
                )
            with ui.row().classes("w-full items-center no-wrap gap-1"):
                for preset in PRESET_HOURS:
                    ui.chip(f"{preset:g}h", on_click=lambda _e, p=preset: self._set_hours(float(p))).props(
                        "dense clickable outline size=sm"
                    ).mark(f"task-effort-preset-{preset:g}")
            self.reference = ui.label("").classes("text-caption text-grey").mark("task-effort-reference")
        self.number.on_value_change(self._number_changed)
        self.unit.on_value_change(self._unit_changed)

    @property
    def value(self) -> float | None:
        return self._hours

    def on_value_change(self, callback: Callable[[float | None], object]) -> None:
        self._callbacks.append(callback)

    def set_visibility(self, visible: bool) -> None:
        self.container.set_visibility(visible)

    def _notify(self) -> None:
        for callback in self._callbacks:
            callback(self._hours)

    def _number_changed(self, event: ValueChangeEventArguments) -> None:
        if self._syncing:
            return
        self._hours = None if event.value is None else to_hours(event.value, self._unit, self._daily)
        self._update_reference()
        self._notify()

    def _unit_changed(self, event: ValueChangeEventArguments) -> None:
        self._unit = event.value
        self._show_number()
        self._update_reference()

    def _set_hours(self, hours: float) -> None:
        self._hours = hours
        self._show_number()
        self._update_reference()
        self._notify()

    def _show_number(self) -> None:
        self._syncing = True
        try:
            self.number.set_value(None if self._hours is None else from_hours(self._hours, self._unit, self._daily))
        finally:
            self._syncing = False

    def _update_reference(self) -> None:
        self.reference.set_text(reference_text(self._unit, self._daily, self._standard))
```

`open_task_dialog` の工数を置き換える(`with fields.second_row:` の中)。

```python
        with fields.second_row:
            effort = EffortField(initial.effort_hours, daily_hours, STANDARD_WORK_HOURS)
```

`on_effort_change` を、値を直接受ける形に直す。

```python
        def on_effort_change(value: float | None) -> None:
            fields.set_effort(value)
            refresh_conversion()
```

(`effort.on_value_change(on_effort_change)` の呼び出しはそのまま。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py -q`
Expected: PASS(「工数(時間)」の文言を探す既存のテストがあれば、「工数」に直す)

- [ ] **Step 5: 型検査とコミット**

Run: `uv run ty check src && uv run pytest -n auto -q`
Expected: `All checks passed!`、全件 PASS

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "feat: 工数に単位(時間・日・週・月)とプリセット、換算の参考を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 割り当て率を、メンバーを選んだ行だけ出す

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`AssigneeFields._sync`)
- Test: `test/test_task_dialog.py`(`task-allocation` の `enabled` を見ている既存の 2 件:`test_...allocation...`:824・:838 付近)

**Interfaces:**
- Produces: 割り当て率(`task-allocation`・`task-allocation-N`)は、メンバーを選んだ行だけ見える。隠しても値は保持する

- [ ] **Step 1: 既存のテストを直し、失敗させる**

`enabled is False` を見ているテストを、見えないことの検査に、`enabled is True` を見ているテストを、見えることの検査に直す。

```python
async def test_the_allocation_is_hidden_until_an_assignee_is_chosen(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0)])
    await open_dialog(user)
    await user.should_not_see(marker="task-allocation")


async def test_the_allocation_shows_with_an_assignee_and_hides_again_when_cleared(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-assignee").elements.pop().set_value("田中")
    await user.should_see(marker="task-allocation")
    user.find(marker="task-allocation").elements.pop().set_value(50)
    user.find(marker="task-assignee").elements.pop().set_value("")  # (なし)
    await user.should_not_see(marker="task-allocation")
    user.find(marker="task-assignee").elements.pop().set_value("田中")
    assert user.find(marker="task-allocation").elements.pop().value == 50  # 隠しても値は残る
```

(既存の 2 件を、上の 2 件で置き換える。名前の付け方は、ファイルの並びに合わせる。)

Run: `uv run pytest test/test_task_dialog.py -q -k allocation`
Expected: FAIL(今は `set_enabled` なので、見えている)

- [ ] **Step 2: 実装する**

`AssigneeFields._sync` の `item.allocation.set_enabled(bool(item.member.value))` を次にする。

```python
            item.allocation.set_visibility(bool(item.member.value))
```

- [ ] **Step 3: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py -q`
Expected: PASS(割り当て率を `find` で探す既存のテストは、メンバーを選んだあとなので、そのまま通る。通らないものは、選ぶ手順を足す)

- [ ] **Step 4: コミット**

Run: `uv run ty check src && uv run pytest -n auto -q`
Expected: 全件 PASS

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "feat: 割り当て率を、メンバーを選んだ行だけ出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: レイアウトの切り替え・保存の配線・ドキュメント

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`open_task_dialog` の引数・切り替え・`apply_layout`)
- Modify: `src/projectapp/views.py`(`task_layout`・`set_task_layout`・`link_args`)
- Test: `test/test_task_dialog.py`、`test/test_views.py`
- Modify: `CLAUDE.md`(`projectapp/`)、`docs/development.md`

**Interfaces:**
- Consumes: Task 3 の `load_task_layout`・`save_task_layout`
- Produces:
  - `open_task_dialog(..., layout: str = "all", on_layout_change: Callable[[str], object] | None = None)`
  - `LAYOUT_LABELS = {"schedule": "予定・実績", "all": "すべて"}`
  - マーカー `task-layout`(`ui.toggle`。値は `"schedule"` か `"all"`)
  - `MainView.task_layout: str`、`MainView.set_task_layout(layout: str) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` に足す。

```python
from projectapp.models import Priority


def rich_task() -> Task:
    return Task(
        "a",
        category_id="c1",
        assignees=[Assignee("田中", 0.5)],
        predecessors=["p1"],
        priority=Priority.HIGH,
        color="#123456",
        urls=[TaskUrl("仕様", None, {"url": "https://example.com/spec"})],
    )


HIDDEN_IN_SCHEDULE = [
    "task-category",
    "task-assignee",
    "task-predecessors",
    "priority-HIGH",
    "task-url-add",
    "task-color",
]
SHOWN_IN_SCHEDULE = [
    "task-name",
    "task-start-date",
    "task-end-date",
    "task-deadline-date",
    "task-effort",
    "task-actual-start-date",
    "task-status",
    "task-kind",
]


async def test_the_dialog_opens_in_the_layout_it_is_given(user: User) -> None:
    mount_dialog(rich_task(), [], layout="schedule", link_options={"p1": "先行"}, categories=[Category("c1", "開発")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    for marker in SHOWN_IN_SCHEDULE:
        await user.should_see(marker=marker)
    for marker in HIDDEN_IN_SCHEDULE:
        await user.should_not_see(marker=marker)


async def test_the_toggle_switches_the_layout_and_reports_it(user: User) -> None:
    changed: list[str] = []
    mount_dialog(rich_task(), [], on_layout_change=changed.append, link_options={"p1": "先行"}, categories=[Category("c1", "開発")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    for marker in HIDDEN_IN_SCHEDULE:
        await user.should_see(marker=marker)  # 既定は「すべて」
    user.find(marker="task-layout").elements.pop().set_value("schedule")
    for marker in HIDDEN_IN_SCHEDULE:
        await user.should_not_see(marker=marker)
    assert changed == ["schedule"]
    user.find(marker="task-layout").elements.pop().set_value("all")
    await user.should_see(marker="task-category")
    assert changed == ["schedule", "all"]


async def test_hidden_fields_keep_their_values_through_a_schedule_save(user: User) -> None:
    saved: list[Task] = []
    original = rich_task()
    mount_dialog(original, saved, layout="schedule", link_options={"p1": "先行"}, categories=[Category("c1", "開発")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-name").clear().type("改名")
    user.find(marker="task-save").click()
    result = saved[0]
    assert result.name == "改名"
    assert result.category_id == "c1"
    assert [(a.name, a.allocation) for a in result.assignees] == [("田中", 0.5)]
    assert result.predecessors == ["p1"]
    assert result.priority is Priority.HIGH
    assert result.color == "#123456"
    assert result.urls == original.urls


async def test_a_layout_switch_alone_is_not_a_change(user: User) -> None:
    mount_dialog(rich_task(), [], link_options={"p1": "先行"}, categories=[Category("c1", "開発")], members=[Member("田中", 1.0)])
    await open_dialog(user)
    user.find(marker="task-layout").elements.pop().set_value("schedule")
    user.find(marker="task-cancel").click()
    await user.should_not_see("編集内容を確定しますか?")  # 切り替えは、変更に数えない(確認なしで閉じる)


async def test_a_checkpoint_hides_the_normal_fields_in_every_layout(user: User) -> None:
    mount_dialog(None, [], layout="schedule")
    await open_dialog(user)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.CHECKPOINT)
    for marker in ("task-start-date", "task-effort", "task-actual-start-date"):
        await user.should_not_see(marker=marker)
    await user.should_see(marker="task-deadline-date")
    user.find(marker="task-layout").elements.pop().set_value("all")
    for marker in ("task-start-date", "task-effort", "task-actual-start-date", "task-assignee-add"):
        await user.should_not_see(marker=marker)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.NORMAL)
    await user.should_see(marker="task-effort")
    await user.should_see(marker="task-assignee-add")
```

`mount_dialog` に引数 `layout: str = "all"`・`on_layout_change: Callable[[str], object] | None = None` を足し、`open_task_dialog` へ渡す。

`test/test_views.py` に足す。

```python
async def test_the_task_layout_is_loaded_and_saved(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"task_layout": "schedule"}', encoding="utf-8")
    view = await open_members_view(user, tmp_path)
    assert view.task_layout == "schedule"
    view.set_task_layout("all")
    assert view.task_layout == "all"
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["task_layout"] == "all"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py test/test_views.py -q -k "layout or checkpoint_hides or hidden_fields"`
Expected: FAIL(`layout` の引数がない)

- [ ] **Step 3: ダイアログを実装する**

`open_task_dialog` に引数 `layout: str = "all"`、`on_layout_change: Callable[[str], object] | None = None` を足す。モジュールに足す。

```python
LAYOUT_LABELS = {"schedule": "予定・実績", "all": "すべて"}
```

タイトルの直後に切り替えを足す。

```python
        layout_toggle = ui.toggle(LAYOUT_LABELS, value=layout if layout in LAYOUT_LABELS else "all").mark("task-layout")
```

`PriorityChips` と `UrlFields` を、それぞれ列で包む(隠す単位にするため)。

```python
        with ui.column().classes("w-full gap-1") as priority_box:
            priority = PriorityChips(initial.priority)
```

```python
        with ui.column().classes("w-full gap-1") as url_box:
            url_fields = UrlFields(initial.urls, templates, open_url)
```

`refresh_push` の末尾を、レイアウトを見る形にする。

```python
            push.set_visibility(bool(text) and layout_toggle.value == "all")
```

`color = ui.color_input(...)` の直後(`error = ui.label(...)` の前)に足す。

```python
        def apply_layout(_event: object = None) -> None:
            """レイアウトに合わせて、欄を出し入れする。値は消さない。チェックポイントでは、開始・工数・担当・実績を、どのレイアウトでも隠す。"""
            full = layout_toggle.value == "all"
            normal = kind.value != TaskKind.CHECKPOINT
            for widget in (category, predecessors, priority_box, url_box, color):
                widget.set_visibility(full)
            for widget in (assignee_fields.container, conversion):
                widget.set_visibility(full and normal)
            refresh_push()

        kind.on_value_change(apply_layout)  # apply_kind の後に走る(同じ欄の可視性を、レイアウトを含めて決め直す)
        layout_toggle.on_value_change(apply_layout)
        if on_layout_change is not None:
            layout_toggle.on_value_change(lambda e: on_layout_change(e.value))
        apply_layout()
```

`current()` の中身は変えない(レイアウトを含めない)。

- [ ] **Step 4: views をつなぐ**

`views.py` の import に `load_task_layout`・`save_task_layout` を足し、`self.zoom = load_zoom(base_dir)` の下に足す。

```python
        self.task_layout = load_task_layout(base_dir)  # タスクのダイアログのレイアウト。全プロジェクト共通
```

`change_zoom` の下に足す。

```python
    def set_task_layout(self, layout: str) -> None:
        """タスクのダイアログのレイアウトを覚える。保存できなくても、画面には反映する(通知だけ出す)。"""
        self.task_layout = layout
        try:
            save_task_layout(layout, self.base_dir)
        except OSError:
            ui.notify("レイアウトを保存できませんでした", type="warning")
```

`link_args` の戻り値の辞書に足す。

```python
            "layout": self.task_layout,
            "on_layout_change": self.set_task_layout,
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py test/test_views.py -q`
Expected: PASS

- [ ] **Step 6: ドキュメントを直す**

`CLAUDE.md`(`projectapp/`)の「ガントチャート」節に足す。

```
- タスクの追加・編集ダイアログは、タイトルの下の切り替えで、レイアウトを`予定・実績`(名前・種別・開始予定・完了予定・工数・締切・実績・状態)か`すべて`(カテゴリ・担当・先行・優先度・リンク・色も出す)から選べる。選んだものは`~/.projectapp/config.json`の`task_layout`に保存し、次回も使う(既定は`すべて`。全プロジェクト共通)。隠した項目の値は保持し、保存でも失わない
- 日付の入力は、`10/15`・`1015`・`20261015`でも書け、入力欄を離れたときに`YYYY-MM-DD`に整える(開始予定・完了予定・締切は、過ぎた日なら翌年。実績は今年のまま)。時刻は、`9`・`930`・`9:30`を`HH:MM`に整える。開始予定・完了予定・締切の日付には、`今日`・`明日`・`来週月`のチップがある
- 工数の入力は、単位(`時間`・`日`・`週`・`月`)を選べる(`1日`=稼働可能時間、`1週`=5日、`1月`=20日。保存は時間)。`0.5`・`1`・`2`・`4`・`8`時間のチップがあり、`月`のときは、`1月`の稼働可能時間の合計と標準稼働時間(8h)での合計を並べて出す
- 担当者の割り当て率は、メンバーを選んだ行だけ出す
```

`docs/development.md` のモジュール表に足す(`forms.py` の行の下)。

```
| `dateinput.py` | 日付と時刻の入力の整形。`parse_date_input`(省略形 → `YYYY-MM-DD`。`roll_forward` で、過ぎた日を翌年にする)・`parse_time_input`(→ `HH:MM`)・`shortcut_dates`(今日・明日・来週月)。純粋関数。`task_dialog.add_picker` の `normalize` が、blur で使う。テストは `task_dialog.today` を差し替えて日付を固定する |
| `effortunits.py` | 工数の単位(時間・日・週・月)の換算 `to_hours` / `from_hours` と、参考 `reference_text`。純粋関数。時間のときは丸めない(桁数の検証はフォーム)。`task_dialog.EffortField` が使い、時間を正本として持つ(単位の切り替えで丸めのずれを溜めない) |
```

`config.py` の説明に `task_layout` を足す(既存の `zoom` の記述の隣)。

- [ ] **Step 7: 全体の確認**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全件 PASS、`All checks passed!`

- [ ] **Step 8: 実機の確認**

`run` スキルで、ブラウザ版を一時的な HOME で起動し(`~/.projectapp` に触れない)、ヘッドレス Chrome で確かめる。ウィンドウの高さは 520px と 900px の 2 つで見る。① レイアウトの切り替えで欄が出入りし、再び開くと前回の選択になる、② `10/15`・`930` が、欄を離れると整う、③ チップで日付が入る、④ 開始・完了が横に並び、日付と時刻が 1 行になる、⑤ 工数の単位・プリセット・月の参考値、⑥ メンバーを選ぶと割り当て率が出る、⑦ 低いウィンドウで、下まで届く(スクロールできる)。見つけた不具合は、その場で直し、テストを足す。

- [ ] **Step 9: コミット**

```bash
git add src/projectapp/task_dialog.py src/projectapp/views.py test CLAUDE.md docs/development.md
git commit -m "feat: タスクのダイアログに、予定・実績とすべてのレイアウトの切り替えを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
