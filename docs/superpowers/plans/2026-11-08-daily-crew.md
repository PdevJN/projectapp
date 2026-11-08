# 日ごとの担当 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 担当を、週ごとの担当のうち選んだ 1 週だけ日ごとに変えられるようにし、遅延対応(132・133・134)の増員を、丸めずに翌日から効かせる(要望 135)。

**Architecture:** `Task.daily_crew`(週の添字 → 7 日分の担当)を足し、純粋関数のモジュール `daily_crew.py` に「区間の展開・増員日からの足し方・週の分割と戻し」を集める。計算(`timeline.py`)は、担当の並びを `CrewTrack`(要素ごとの日数 `step` を持つ list)で受けて日の位置で引く。`daily_crew` が空なら今までと同じ並び(step 7)になる。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、ruff、ty。

**Spec:** `docs/superpowers/specs/2026-11-08-daily-crew-design.md`(計画は設計書から、増員する人の休みの案内を「ダイアログ」から「通知」にしてよい、と補足する)

## Global Constraints

- 言語は日本語。Python 3.13 以上。ライブラリは NiceGUI。描画は NiceGUI の要素と CSS による自前描画。
- 日付・日程の計算は NiceGUI から切り離した純粋関数にする。日の位置は `date` の差(`(day - anchor).days`)だけで数え、月・年・閏年で場合分けしない。
- ファイル形式: `version` を **22** に上げる。キーのない古いファイルは`daily_crew = {}`で読む。不正は拒否し、新しい`version`も拒否する。保存は一時ファイル経由(既存のまま)。
- `daily_crew` が空のタスクの計算結果は、変更前と**完全に一致**させる。
- 当初の完了予定の意味・予定超過・警告の判定式は変えない。見込みと試算は保存しない。
- 完了時の検証: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`。
- 用語: 遅れ(赤)・警告(黄)・割り当て超過。`遅延`は赤の意味では使わない。
- マージは利用者の指示を待つ(PR を `develop` 向けに作って止まる)。`git checkout -p` のような対話コマンドは使わない。

## Review Focus

1. 増員日がプロジェクトの休み(土日祝・イベント 2026/12/28〜2027/01/03)の中: 効き始めは次の稼働日。増員日を 12/26 にしても 1/4 にしても、結果が同じになる。
2. 閏年の有無で 2月から 3月: 2028 は 2/28 の翌日が 2/29(稼働日)、2027 は 2/28(日)の翌日が 3/1。週の添字が暦日の差で一貫する。
3. 増員する人の個人の休み(稼働日の上書き): 休みの間は稼働量 0、効き始めはその人の次の稼働日。他のメンバーは影響を受けない。
4. 最後の週が日ごとのとき、その 7 日目の担当が以降も続く。
5. 右クリックの`週ごとをやめる`・担当の一括置き換え・種別変更が `daily_crew` を残さない(残ると孤児の日ごと担当が計算に効く)。`daily_crew` の添字が週の数を超える入力は計算で無視し、保存では拒否する。

---

## File Structure

- Create: `src/projectapp/daily_crew.py` — 日ごとの担当の純粋関数(区間・増員日からの足し方・週の分割と戻し・表示区間)。
- Modify: `src/projectapp/models.py`(`daily_crew` フィールド・`FORMAT_VERSION`)、`storage.py`(読み書き・検証)、`timeline.py`(`CrewTrack`・日の位置で引く)、`forecast.py`・`crew_trial.py`(日付のまま増員)、`views.py`(翌日の既定・編集)、`delay_response.py`(試算ダイアログ・CSS)、`task_dialog.py`(週・日のダイアログ)、`gantt.py`(日ごとのチップ)、`bottom_info.py`、`merge.py`、`bulk_edit.py`、`decompose.py`、`forms.py`、`arrange.py`、`plantuml.py`。
- Test: `test/test_daily_crew.py`(新規。純粋関数)、`test/test_daily_crew_timeline.py`(新規。計算・年末年始・閏年・個人の休み)、`test/test_daily_crew_storage.py`(新規)、`test/test_daily_crew_view.py`(新規。画面)、`test/test_daily_crew_others.py`(新規。マージ・一括編集ほか)、既存の `test_crew_trial.py`・`test_forecast.py`・`test_warning_add_crew.py`・`test_delay_response.py` を直す。

---

### Task 1: モデルと保存(version 22)

**Files:**
- Modify: `src/projectapp/models.py`(`Task.weekly_crew` の直後、`FORMAT_VERSION`)
- Modify: `src/projectapp/storage.py`(`refs_of` の変換 ~188、`_task` の読み込み ~396・412、`_weekly_crew` の直後)
- Test: `test/test_daily_crew_storage.py`(新規)、`test/test_reference_storage.py:44`・`test/test_summary.py:113`・`test/test_storage.py:1582`(`== 21` を `== 22` に)

**Interfaces:**
- Produces: `Task.daily_crew: dict[int, list[list[Assignee]]]`(既定 `{}`)。`FORMAT_VERSION == 22`。保存の形は `"daily_crew": {"<週の添字>": [[{"member": id, "allocation": x}, ...] × 7]}`。

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_daily_crew_storage.py
import json
from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import Assignee, Member, Project, Section, Task
from projectapp.storage import load_project, save_project

START = datetime(2026, 11, 2, 9)


def project_with_daily() -> Project:
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木", 0.5)]] * 4
    task = Task(
        "a",
        id="ta",
        planned_start=START,
        effort_hours=20.0,
        assignees=[Assignee("田中"), Assignee("鈴木", 0.5)],
        weekly_crew=[[Assignee("田中"), Assignee("鈴木", 0.5)], [Assignee("田中")]],
        daily_crew={0: [list(d) for d in days]},
    )
    return Project(
        name="p",
        base_date=START,
        members=[Member("田中"), Member("鈴木")],
        sections=[Section("s", tasks=[task])],
    )


def test_daily_crew_round_trips(tmp_path: Path) -> None:
    save_project(project_with_daily(), tmp_path)
    loaded = load_project("p", tmp_path)
    task = loaded.sections[0].tasks[0]
    assert sorted(task.daily_crew) == [0]
    assert [[a.name for a in d] for d in task.daily_crew[0]] == [["田中"]] * 3 + [
        ["田中", "鈴木"]
    ] * 4
    assert task.daily_crew[0][3][1].allocation == 0.5


def test_old_files_without_the_key_load_with_no_daily_crew(tmp_path: Path) -> None:
    save_project(project_with_daily(), tmp_path)
    path = tmp_path / "p.json"
    raw = json.loads(path.read_text("utf-8"))
    raw["version"] = 21
    for task in raw["sections"][0]["tasks"]:
        task.pop("daily_crew", None)
    path.write_text(json.dumps(raw), "utf-8")
    assert load_project("p", tmp_path).sections[0].tasks[0].daily_crew == {}


def edited(tmp_path: Path, change) -> Path:
    save_project(project_with_daily(), tmp_path)
    path = tmp_path / "p.json"
    raw = json.loads(path.read_text("utf-8"))
    change(raw["sections"][0]["tasks"][0])
    path.write_text(json.dumps(raw), "utf-8")
    return path


@pytest.mark.parametrize(
    "change",
    [
        lambda t: t["daily_crew"].update({"5": t["daily_crew"]["0"]}),  # 週の数を超える添字
        lambda t: t["daily_crew"]["0"].pop(),  # 7 日でない
        lambda t: t["daily_crew"]["0"].__setitem__(2, []),  # 担当のいない日
        lambda t: t["daily_crew"].update({"x": t["daily_crew"]["0"]}),  # 添字が整数でない
        lambda t: t["daily_crew"]["0"][0].append({"member": "nobody", "allocation": 1}),
        lambda t: t.__setitem__("daily_crew", [1]),  # 辞書でない
    ],
)
def test_bad_daily_crew_is_refused(tmp_path: Path, change) -> None:
    edited(tmp_path, change)
    with pytest.raises(ValueError):
        load_project("p", tmp_path)


def test_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = edited(tmp_path, lambda t: None)
    raw = json.loads(path.read_text("utf-8"))
    raw["version"] = 23
    path.write_text(json.dumps(raw), "utf-8")
    with pytest.raises(ValueError):
        load_project("p", tmp_path)
```

(`save_project`/`load_project` の名前と引数は、`test/test_storage.py` の冒頭の import と呼び出しに合わせる。違う名前なら、そのファイルで使っているものに置き換える。)

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_daily_crew_storage.py -q` / Expected: FAIL(`daily_crew` が未定義)

- [ ] **Step 3: 実装**

`models.py`: `Task.weekly_crew` の定義の直後に足す。

```python
    daily_crew: dict[int, list[list[Assignee]]] = field(
        default_factory=dict
    )  # 日ごとの担当(要望 135)。週の添字 → その週の 7 日ぶんの担当。添字は weekly_crew の週だけ。その週の weekly_crew は 7 日の担当の和集合
```

`FORMAT_VERSION = 21` を `22` にし、コメントの末尾の版の説明に `22: 日ごとの担当〔daily_crew〕` を足す(`python3` で `FORMAT_VERSION = 21` → `FORMAT_VERSION = 22` と、コメントの `)` の直前への追記)。

`storage.py`: 書き出しの変換(`task["weekly_crew"] = ...` の行の次)

```python
        task["daily_crew"] = {
            week: [refs_of(day) for day in days]
            for week, days in task["daily_crew"].items()
        }
```

読み込み(`weekly = ...` の直後)と `Task(...)` への受け渡し

```python
    daily = (
        _daily_crew(raw.get("daily_crew"), ctx, len(weekly)) if ctx.version >= 22 else {}
    )
```
```python
        weekly_crew=weekly,
        daily_crew=daily,
```

`_weekly_crew` の直後に検証関数を足す。

```python
def _daily_crew(
    value: Any, ctx: "_Context", weeks: int
) -> dict[int, list[list[Assignee]]]:
    """version 22 の日ごとの担当。キーは週の添字(週ごとの担当の範囲内)、値は 7 日ぶんの担当(各日 1 人以上)。不正は ValueError。"""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("日ごとの担当が辞書ではありません")
    result: dict[int, list[list[Assignee]]] = {}
    for key, days in value.items():
        try:
            week = int(key)
        except (TypeError, ValueError):
            raise ValueError(f"日ごとの担当の週が整数ではありません: {key!r}") from None
        if not 0 <= week < weeks:
            raise ValueError(f"日ごとの担当の週が範囲外です: {week}")
        if not isinstance(days, list) or len(days) != 7:
            raise ValueError("日ごとの担当は 7 日ぶん必要です")
        crews: list[list[Assignee]] = []
        for day in days:
            if not isinstance(day, list):
                raise ValueError("日の担当が配列ではありません")
            crew = _member_assignees(day, ctx.member_names)
            if not crew:
                raise ValueError("担当者のいない日があります")
            crews.append(crew)
        result[week] = crews
    return result
```

(`_member_assignees` はメンバーにいない id を拒否する既存の関数。拒否しない実装なら、`len(crew) != len(day)` のとき ValueError にする。)

3 つのテストの `== 21` を `== 22` にする。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_daily_crew_storage.py test/test_storage.py test/test_reference_storage.py test/test_summary.py -q -n auto` / Expected: PASS

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 日ごとの担当を保存する(version 22。要望 135)"`

---

### Task 2: 日ごとの担当の純粋関数 `daily_crew.py`

**Files:**
- Create: `src/projectapp/daily_crew.py`
- Test: `test/test_daily_crew.py`(新規)

**Interfaces:**
- Consumes: `Task.daily_crew`(Task 1)、`models.MAX_WEEKS`・`Assignee`・`union_assignees`。
- Produces(後続のタスクが使う):
  - `WEEK_DAYS = 7`、`DailyCrew = dict[int, list[list[Assignee]]]`
  - `copy_weekly(weekly) -> list[list[Assignee]]`、`copy_daily(daily) -> DailyCrew`
  - `rows_of(task) -> tuple[list[list[Assignee]], DailyCrew]`(週ごとでないタスクは `([assignees の複製], {})`)
  - `crew_spans(weekly, daily) -> list[tuple[int, list[Assignee]]]`(週は `(7, 担当)`、日ごとの週は `(1, 担当)` × 7)
  - `with_added_from(weekly, daily, offset: int, names) -> tuple[list[list[Assignee]], DailyCrew] | None`
  - `Segment`(`week`・`day`・`first`・`last`・`crew`・`carried`)、`segments(weekly, daily, start: date, last_day: date) -> list[Segment]`
  - `split_week(task, week) -> Task | None`、`merge_week(task, week) -> Task | None`、`set_week_days(task, week, days) -> Task | None`

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_daily_crew.py
from datetime import date

from projectapp.daily_crew import (
    crew_spans,
    merge_week,
    rows_of,
    segments,
    set_week_days,
    split_week,
    with_added_from,
)
from projectapp.models import Assignee, Task

T = [Assignee("田中")]
TS = [Assignee("田中"), Assignee("鈴木")]


def names(crew):
    return [a.name for a in crew]


def test_spans_are_seven_days_for_a_week_and_one_day_each_for_a_daily_week() -> None:
    days = [list(T)] * 3 + [list(TS)] * 4
    spans = crew_spans([list(TS), list(T)], {0: days})
    assert [d for d, _ in spans] == [1] * 7 + [7]
    assert names(spans[3][1]) == ["田中", "鈴木"] and names(spans[7][1]) == ["田中"]


def test_spans_ignore_a_daily_week_that_is_out_of_range_or_not_seven_days() -> None:
    assert [d for d, _ in crew_spans([list(T)], {3: [list(T)] * 7})] == [7]
    assert [d for d, _ in crew_spans([list(T)], {0: [list(T)] * 6})] == [7]


def test_with_added_from_a_week_head_does_not_make_a_daily_week() -> None:
    weekly, daily = with_added_from([list(T)], {}, 0, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中", "鈴木"]] and daily == {}
    weekly, daily = with_added_from([list(T)], {}, 7, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中"], ["田中", "鈴木"]] and daily == {}


def test_with_added_from_mid_week_makes_only_that_week_daily() -> None:
    weekly, daily = with_added_from([list(T), list(T), list(T)], {}, 10, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中"], ["田中", "鈴木"], ["田中", "鈴木"]]
    assert list(daily) == [1]
    assert [names(d) for d in daily[1]] == [["田中"]] * 3 + [["田中", "鈴木"]] * 4


def test_with_added_from_pads_weeks_and_refuses_beyond_the_limit() -> None:
    weekly, daily = with_added_from([list(T)], {}, 17, ("鈴木",))
    assert len(weekly) == 3 and list(daily) == [2]
    assert with_added_from([list(T)], {}, 7 * 52, ("鈴木",)) is None
    assert with_added_from([list(T)], {}, 7 * 52 - 1, ("鈴木",)) is not None


def test_with_added_from_an_earlier_offset_is_the_first_day() -> None:
    weekly, daily = with_added_from([list(T)], {}, -5, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中", "鈴木"]] and daily == {}


def test_with_added_from_does_not_duplicate_and_keeps_an_existing_daily_week() -> None:
    days = [list(T)] * 7
    weekly, daily = with_added_from([list(T)], {0: days}, 2, ("田中", "鈴木"))
    assert [names(d) for d in daily[0]] == [["田中"]] * 2 + [["田中", "鈴木"]] * 5
    weekly, daily = with_added_from([list(T), list(T)], {0: days}, 7, ("鈴木",))
    assert names(weekly[1]) == ["田中", "鈴木"] and len(daily[0]) == 7
    assert all(names(d) == ["田中"] for d in daily[0])  # 前の週は変えない


def test_with_added_from_does_not_change_its_inputs() -> None:
    weekly, daily = [list(T)], {0: [list(T)] * 7}
    with_added_from(weekly, daily, 3, ("鈴木",))
    assert names(weekly[0]) == ["田中"] and all(names(d) == ["田中"] for d in daily[0])


def test_rows_of_a_task_without_weeks_is_one_week_of_the_assignees() -> None:
    weekly, daily = rows_of(Task("a", assignees=list(T)))
    assert [names(w) for w in weekly] == [["田中"]] and daily == {}


def test_segments_mix_weeks_and_days_and_carry_the_last_crew() -> None:
    days = [list(T)] * 3 + [list(TS)] * 4
    start = date(2026, 11, 2)
    seg = segments([list(TS), list(T)], {1: days}, start, date(2026, 11, 30))
    assert [(s.week, s.day) for s in seg] == [(0, None)] + [(1, j) for j in range(7)] + [
        (2, None),
        (3, None),
        (4, None),
    ]
    assert seg[1].first == date(2026, 11, 9) == seg[1].last
    assert seg[0].first == start and seg[0].last == date(2026, 11, 8)
    assert [s.carried for s in seg] == [False] * 8 + [True] * 3
    assert names(seg[-1].crew) == ["田中", "鈴木"]  # 最後の日ごとの週の 7 日目が続く


def test_segments_stop_at_the_last_day() -> None:
    seg = segments([list(T)], {0: [list(T)] * 7}, date(2026, 11, 2), date(2026, 11, 4))
    assert [(s.week, s.day) for s in seg] == [(0, 0), (0, 1), (0, 2)]


def test_split_merge_and_set_week_days() -> None:
    task = Task("a", assignees=list(TS), weekly_crew=[list(TS), list(T)])
    split = split_week(task, 1)
    assert split is not None and list(split.daily_crew) == [1]
    assert all(names(d) == ["田中"] for d in split.daily_crew[1])
    days = [list(T)] * 3 + [list(TS)] * 4
    edited = set_week_days(split, 1, days)
    assert edited is not None and names(edited.weekly_crew[1]) == ["田中", "鈴木"]
    back = merge_week(edited, 1)
    assert back is not None and back.daily_crew == {}
    assert names(back.weekly_crew[1]) == ["田中"]  # 1 日目の担当


def test_split_pads_a_carried_week_with_the_last_crew_and_refuses_other_cases() -> None:
    task = Task("a", assignees=list(T), weekly_crew=[list(T)])
    split = split_week(task, 2)
    assert split is not None and len(split.weekly_crew) == 3
    assert split_week(Task("a", assignees=list(T)), 0) is None  # 週ごとでない
    assert split_week(task, 52) is None
    assert merge_week(task, 0) is None  # 日ごとでない
    assert set_week_days(task, 0, [list(T)] * 7) is None
    split0 = split_week(task, 0)
    assert split0 is not None
    assert set_week_days(split0, 0, [list(T)] * 6) is None
    assert set_week_days(split0, 0, [list(T)] * 6 + [[]]) is None
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_daily_crew.py -q` / Expected: FAIL(モジュールがない)

- [ ] **Step 3: 実装**

```python
# src/projectapp/daily_crew.py
"""日ごとの担当(要望 135)。NiceGUI に依存しない純粋関数。

週ごとの担当(`Task.weekly_crew`。実効の開始の日から 7 日ごと)のうち、選んだ週だけを日ごとにできる
(`Task.daily_crew`)。日の位置は、起点との暦日の差だけで数える(月・年・閏年で場合分けしない)。
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta

from projectapp.models import MAX_WEEKS, Assignee, Task, union_assignees

WEEK_DAYS = 7
DailyCrew = dict[int, list[list[Assignee]]]


def copy_crew(crew: list[Assignee]) -> list[Assignee]:
    return [replace(a) for a in crew]


def copy_weekly(weekly: list[list[Assignee]]) -> list[list[Assignee]]:
    return [copy_crew(week) for week in weekly]


def copy_daily(daily: DailyCrew) -> DailyCrew:
    return {week: [copy_crew(day) for day in days] for week, days in daily.items()}


def rows_of(task: Task) -> tuple[list[list[Assignee]], DailyCrew]:
    """タスクの週ごとの担当と日ごとの担当の複製。週ごとでないタスクは、担当 1 週ぶん(日ごとなし)。"""
    if not task.weekly_crew:
        return [copy_crew(task.assignees)], {}
    return copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)


def _is_daily(daily: DailyCrew, week: int) -> bool:
    days = daily.get(week)
    return days is not None and len(days) == WEEK_DAYS


def crew_spans(
    weekly: list[list[Assignee]], daily: DailyCrew
) -> list[tuple[int, list[Assignee]]]:
    """(日数, 担当) の並び。週は (7, 担当)、日ごとの週は (1, 担当) × 7。最後の要素は以降も続く。
    週の数を超える添字・7 日でない日ごとの担当は無視する。"""
    spans: list[tuple[int, list[Assignee]]] = []
    for number, week in enumerate(weekly):
        if _is_daily(daily, number):
            spans.extend((1, day) for day in daily[number])
        else:
            spans.append((WEEK_DAYS, week))
    return spans


def _tail(weekly: list[list[Assignee]], daily: DailyCrew) -> list[Assignee]:
    """最後の週の、以降も続く担当(最後の週が日ごとなら、その 7 日目)。"""
    last = len(weekly) - 1
    return daily[last][-1] if _is_daily(daily, last) else weekly[last]


def _plus(crew: list[Assignee], names: tuple[str, ...]) -> list[Assignee]:
    present = {a.name for a in crew}
    return copy_crew(crew) + [Assignee(n) for n in names if n not in present]


def with_added_from(
    weekly: list[list[Assignee]],
    daily: DailyCrew,
    offset: int,
    names: tuple[str, ...],
) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週の起点から offset 日目(負は 0)以降に names を足した、週ごとの担当と日ごとの担当。
    offset が週頭(7 の倍数)なら日ごとにせず、その週以降の担当に足す。週の途中なら、その週だけを日ごとにする。
    定義済みの最後の週より先は、直前の担当のコピーで間を埋める。52 週以上になるなら None。入力は変えない。"""
    offset = max(offset, 0)
    week, day = divmod(offset, WEEK_DAYS)
    if week >= MAX_WEEKS:
        return None
    rows = copy_weekly(weekly)
    days_by_week = copy_daily(daily)
    while len(rows) <= week:
        rows.append(copy_crew(_tail(rows, days_by_week)))
    for number in range(week, len(rows)):
        first = day if number == week else 0
        if first == 0 and not _is_daily(days_by_week, number):
            rows[number] = _plus(rows[number], names)
            continue
        days = days_by_week[number] if _is_daily(days_by_week, number) else [
            copy_crew(rows[number]) for _ in range(WEEK_DAYS)
        ]
        days = [d if i < first else _plus(d, names) for i, d in enumerate(days)]
        days_by_week[number] = days
        rows[number] = union_assignees(days)
    return rows, days_by_week


@dataclass(frozen=True)
class Segment:
    """棒の上のチップ 1 つぶん。週(day が None)か、日ごとの週の 1 日。"""

    week: int  # 0 始まりの週
    day: int | None  # 日ごとの週の 0〜6。週のままは None
    first: date
    last: date  # この区間の最後の日(含む)
    crew: list[Assignee]
    carried: bool  # 定義済みの週より後(最後の担当が続く)


def segments(
    weekly: list[list[Assignee]], daily: DailyCrew, start: date, last_day: date
) -> list[Segment]:
    """start から last_day(含む)までの表示区間。週は 7 日ぶんで 1 つ、日ごとの週は 1 日ずつ。"""
    result: list[Segment] = []
    number = 0
    while (first := start + timedelta(days=WEEK_DAYS * number)) <= last_day:
        if number < len(weekly) and _is_daily(daily, number):
            for j, crew in enumerate(daily[number]):
                day = first + timedelta(days=j)
                if day > last_day:
                    break
                result.append(Segment(number, j, day, day, crew, False))
        else:
            defined = number < len(weekly)
            crew = weekly[number] if defined else _tail(weekly, daily)
            last = first + timedelta(days=WEEK_DAYS - 1)
            result.append(Segment(number, None, first, last, crew, not defined))
        number += 1
    return result


def split_week(task: Task, week: int) -> Task | None:
    """週を日ごとに分ける(その週の担当を 7 日すべてにコピー)。週ごとでない・上限超えは None。
    定義済みの最後の週より先なら、直前の担当のコピーで間を埋める。"""
    if not task.weekly_crew or not 0 <= week < MAX_WEEKS:
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    while len(weekly) <= week:
        weekly.append(copy_crew(_tail(weekly, daily)))
    if _is_daily(daily, week):
        return None
    daily[week] = [copy_crew(weekly[week]) for _ in range(WEEK_DAYS)]
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def merge_week(task: Task, week: int) -> Task | None:
    """日ごとの週を週に戻す(その週の 1 日目の担当を週の担当にする)。日ごとでなければ None。"""
    if not _is_daily(task.daily_crew, week) or week >= len(task.weekly_crew):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    weekly[week] = copy_crew(daily.pop(week)[0])
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def set_week_days(
    task: Task, week: int, days: list[list[Assignee]]
) -> Task | None:
    """日ごとの週の 7 日ぶんの担当を差し替える。日ごとでない週・7 日でない・担当のいない日は None。"""
    if (
        not _is_daily(task.daily_crew, week)
        or week >= len(task.weekly_crew)
        or len(days) != WEEK_DAYS
        or not all(days)
    ):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    daily[week] = [copy_crew(day) for day in days]
    weekly[week] = union_assignees(daily[week])
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )
```

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_daily_crew.py -q` / Expected: PASS(落ちたら、テストの期待が設計書と食い違っていないか確認してから、実装を直す)

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 日ごとの担当の純粋関数を足す(要望 135)"`

---

### Task 3: 計算(`timeline.py`)を日の位置で引く

**Files:**
- Modify: `src/projectapp/timeline.py`(`crew_pieces` ~236、`week_index` ~434、`crew_on` ~439、`_crews` ~446、`work_capacity` ~521、`_consume` ~569、`weekly_crews` ~682)
- Test: `test/test_daily_crew_timeline.py`(新規)

**Interfaces:**
- Consumes: `daily_crew.crew_spans`・`WEEK_DAYS`(Task 2)。
- Produces:
  - `CrewTrack(list[list[Worker]])` に属性 `step: int`(要素ごとの日数。週 7、日ごと 1)。
  - `crew_track(weekly, daily, to_workers) -> CrewTrack`
  - `week_index(start, day, count, step=7)`(既定の動作は変えない)
  - `weekly_crews(task, project) -> CrewTrack`(`daily_crew` が空なら step 7 の週の並び)
  - `crew_on`・`crew_pieces` が日ごとの週を扱う。`calc_end`・`consumed_slices`・`work_capacity` は `weeks` に `CrewTrack` を渡すと step を使う(普通の list は step 7)。

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_daily_crew_timeline.py
from datetime import date, datetime, time

from projectapp.models import Assignee, Task, WorkDay
from projectapp.timeline import (
    CrewTrack,
    Worker,
    calc_end,
    consumed_slices,
    crew_on,
    crew_pieces,
    crew_track,
    work_capacity,
)
from projectapp.workdays import work_day_map

START = datetime(2026, 11, 2, 9)  # 月曜
NONE: dict[date, str] = {}
A = Worker(1.0, {}, "田中")
B = Worker(1.0, {}, "鈴木")


def end_of(effort, weeks, holidays=NONE, start=START, weeks_start=None):
    return calc_end(
        start, effort, 6.5, time(9, 0), holidays, weeks=weeks, weeks_start=weeks_start
    )


def test_a_plain_list_of_weeks_still_works_as_seven_day_steps() -> None:
    weeks = [[A], [A, B]]
    assert end_of(60.0, weeks) == end_of(60.0, CrewTrack(weeks, 7))


def test_seven_identical_days_equal_the_week() -> None:
    week = CrewTrack([[A]], 7)
    daily = CrewTrack([[A]] * 7, 1)
    for effort in (10.0, 40.0, 60.0, 130.0):
        assert end_of(effort, week) == end_of(effort, daily)
    for stop in (datetime(2026, 11, 20, 12), datetime(2026, 12, 25, 12)):
        assert work_capacity(START, stop, 6.5, time(9, 0), NONE, weeks=week) == (
            work_capacity(START, stop, 6.5, time(9, 0), NONE, weeks=daily)
        )


def test_a_person_joining_mid_week_speeds_up_from_that_day() -> None:
    alone = end_of(26.0, CrewTrack([[A]] * 7, 1))  # 4 日(月〜木)
    joined = end_of(26.0, CrewTrack([[A]] * 2 + [[A, B]] * 5, 1))  # 水から 2 人
    assert joined < alone
    # 月・火は 1 人(13h)。水から 2 人で 13h は 1 日(6.5h × 2)
    assert joined == datetime(2026, 11, 4, 15, 30)


def test_the_last_daily_week_carries_its_seventh_day_on() -> None:
    track = CrewTrack([[A]] * 6 + [[A, B]], 1)  # 7 日目から 2 人、以降も 2 人
    assert end_of(130.0, track) == end_of(130.0, CrewTrack([[A]] * 6 + [[A, B]] * 40, 1))


def test_crew_on_and_crew_pieces_follow_the_days() -> None:
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木")]] * 4
    task = Task(
        "a",
        assignees=[Assignee("田中"), Assignee("鈴木")],
        weekly_crew=[[Assignee("田中"), Assignee("鈴木")], [Assignee("田中")]],
        daily_crew={0: days},
    )
    start = date(2026, 11, 2)
    assert [a.name for a in crew_on(task, start, date(2026, 11, 4))] == ["田中"]
    assert [a.name for a in crew_on(task, start, date(2026, 11, 5))] == ["田中", "鈴木"]
    assert [a.name for a in crew_on(task, start, date(2026, 11, 9))] == ["田中"]
    assert [a.name for a in crew_on(task, start, date(2026, 12, 31))] == ["田中"]
    pieces = crew_pieces(task, START, datetime(2026, 11, 14, 17))
    assert len(pieces) == 8  # 日ごとの 7 日 + 次の週
    assert pieces[0][0] == START and pieces[-1][1] == datetime(2026, 11, 14, 17)
    assert pieces[3][0] == datetime(2026, 11, 5, 0)


def test_without_daily_crew_pieces_and_crew_on_are_unchanged() -> None:
    task = Task(
        "a",
        assignees=[Assignee("田中")],
        weekly_crew=[[Assignee("田中")], [Assignee("鈴木")]],
    )
    pieces = crew_pieces(task, START, datetime(2026, 11, 20, 17))
    assert [(p[0], p[1]) for p in pieces] == [
        (START, datetime(2026, 11, 9)),
        (datetime(2026, 11, 9), datetime(2026, 11, 20, 17)),
    ]


# --- 休みの扱い -----------------------------------------------------------

YEAR_END = {date(2026, 12, d): "年末年始" for d in (28, 29, 30, 31)} | {
    date(2027, 1, d): "年末年始" for d in (1, 2, 3)
}


def joining(day: date, start=datetime(2026, 12, 7, 9)) -> CrewTrack:
    """start から数えた週で、day から B が加わる担当の並び(日ごと 1 日刻み)。"""
    offset = (day - start.date()).days
    return CrewTrack([[A]] * offset + [[A, B]] * 400, 1)


def test_joining_inside_the_year_end_break_equals_joining_after_it() -> None:
    # 12/26(土)・12/27(日)・12/28〜1/3 のイベントは誰も稼働しない。効き始めは 1/4(月)
    start = datetime(2026, 12, 7, 9)
    reference = end_of(200.0, joining(date(2027, 1, 4)), YEAR_END, start)
    for day in (date(2026, 12, 26), date(2026, 12, 27), date(2026, 12, 28), date(2027, 1, 3)):
        assert end_of(200.0, joining(day), YEAR_END, start) == reference
    assert end_of(200.0, joining(date(2026, 12, 25)), YEAR_END, start) < reference


def test_a_daily_week_that_spans_the_new_year_counts_each_calendar_day() -> None:
    # 週の起点 12/30(水)。7 日 = 12/30〜1/5。1/4・1/5 だけ 2 人
    start = datetime(2026, 12, 30, 9)
    crews = [[A]] * 5 + [[A, B]] * 2
    capacity = work_capacity(
        start, datetime(2027, 1, 6), 6.5, time(9, 0), YEAR_END, weeks=CrewTrack(crews, 1)
    )
    assert capacity == 6.5 * 2 * 2  # 1/4・1/5 の 2 日 × 2 人 × 6.5h(12/30〜1/3 は休み)


def test_leap_day_is_a_working_day_only_in_a_leap_year() -> None:
    # 2028 は閏年: 2/28(月)の翌日 2/29(火)が稼働日。2027 は 2/28(日)の翌日 3/1(月)
    leap = datetime(2028, 2, 21, 9)
    plain = datetime(2027, 2, 22, 9)
    on_29 = end_of(120.0, joining(date(2028, 2, 29), leap), NONE, leap)
    on_mar1 = end_of(120.0, joining(date(2028, 3, 1), leap), NONE, leap)
    assert on_29 < on_mar1  # 2/29 から効くほうが早い
    sunday = end_of(120.0, joining(date(2027, 2, 28), plain), NONE, plain)
    monday = end_of(120.0, joining(date(2027, 3, 1), plain), NONE, plain)
    assert sunday == monday  # 日曜は誰も稼働しない


def test_week_index_counts_calendar_days_across_a_leap_day() -> None:
    from projectapp.timeline import week_index

    assert week_index(date(2028, 2, 26), date(2028, 3, 4), 9) == 0  # 閏年: 2/26 + 7 日 = 3/4(第 1 週の最終日)
    assert week_index(date(2028, 2, 26), date(2028, 3, 4), 9, 1) == 7
    assert week_index(date(2027, 2, 26), date(2027, 3, 5), 9) == 0  # 平年: 2/26 + 7 日 = 3/5
    assert week_index(date(2027, 2, 26), date(2027, 3, 5), 9, 1) == 7


# --- 増員する人の個人の休み ----------------------------------------------------

def off(*days: date) -> Worker:
    return Worker(1.0, work_day_map([WorkDay(d) for d in days]), "鈴木")


def test_a_person_who_is_off_adds_nothing_on_their_days_off() -> None:
    start = datetime(2026, 11, 2, 9)
    # 鈴木は 11/4・11/5 が個人の休み。11/4 から加わっても、効き始めは 11/6
    off_b = off(date(2026, 11, 4), date(2026, 11, 5))
    from_4 = CrewTrack([[A]] * 2 + [[A, off_b]] * 400, 1)
    from_6 = CrewTrack([[A]] * 4 + [[A, off_b]] * 400, 1)
    assert end_of(60.0, from_4, NONE, start) == end_of(60.0, from_6, NONE, start)
    always = CrewTrack([[A]] * 2 + [[A, B]] * 400, 1)
    assert end_of(60.0, always, NONE, start) < end_of(60.0, from_4, NONE, start)


def test_the_others_are_not_affected_by_a_person_off() -> None:
    start = datetime(2026, 11, 2, 9)
    solo = CrewTrack([[A]] * 400, 1)
    with_off = CrewTrack([[A, off(date(2026, 11, 3))]] * 400, 1)
    assert work_capacity(
        start, datetime(2026, 11, 3, 23), 6.5, time(9, 0), NONE, weeks=with_off
    ) == work_capacity(start, datetime(2026, 11, 3, 23), 6.5, time(9, 0), NONE, weeks=solo) + 6.5


def test_no_one_working_on_a_day_means_no_progress_that_day() -> None:
    start = datetime(2026, 11, 2, 9)
    both_off = CrewTrack([[off(date(2026, 11, 3))]] * 400, 1)
    one_day = end_of(6.5, both_off, NONE, start)
    assert one_day == datetime(2026, 11, 2, 15, 30)  # 月曜で終わる
    two_days = end_of(13.0, both_off, NONE, start)
    assert two_days == datetime(2026, 11, 4, 15, 30)  # 火曜(休み)を飛ばして水曜


def test_working_on_a_normally_closed_day_counts_extra_capacity() -> None:
    sat = date(2026, 11, 7)
    weekend = Worker(1.0, work_day_map([WorkDay(sat, time(9, 0), time(17, 0))]), "鈴木")
    days = [[A]] * 5 + [[A, weekend]] + [[A]]
    capacity = work_capacity(
        START, datetime(2026, 11, 8), 6.5, time(9, 0), NONE, weeks=CrewTrack(days, 1)
    )
    assert capacity > 6.5 * 5  # 土曜に鈴木が稼働する


def test_consumed_slices_name_the_working_people_per_day() -> None:
    slices = consumed_slices(
        START, 13.0, 6.5, time(9, 0), NONE, weeks=CrewTrack([[A]] + [[A, B]] * 6, 1)
    )
    assert [sorted(w.name for w in s[2]) for s in slices] == [["田中"], ["田中", "鈴木"]]


def test_crew_track_expands_weeks_to_days_only_when_there_is_a_daily_week() -> None:
    weekly = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    plain = crew_track(weekly, {}, lambda crew: [Worker(1.0, {}, a.name) for a in crew])
    assert plain.step == 7 and len(plain) == 2
    daily = {0: [[Assignee("田中")]] * 7}
    mixed = crew_track(weekly, daily, lambda crew: [Worker(1.0, {}, a.name) for a in crew])
    assert mixed.step == 1 and len(mixed) == 7 + 7
```

(`work_day_map` の引数はリスト。`WorkDay(d)` は休み。個人の稼働日の Worker は `days` に日付 → `WorkDay` を持つ。別の形なら `timeline.py` の `Worker` と `workdays.py` の定義に合わせる。期待値の日時は、`daily_hours=6.5`・始業 9:00・稼働は 9:00〜15:30 であることから出している。実行して食い違う期待値は、手で再計算してから直す。計算の実装を合わせて直さない。)

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_daily_crew_timeline.py -q` / Expected: FAIL(`CrewTrack`・`crew_track` がない)

- [ ] **Step 3: 実装**

`timeline.py` の import に `from projectapp.daily_crew import WEEK_DAYS, DailyCrew, crew_spans` を足し、`Worker` の定義の後に追加する。

```python
class CrewTrack(list[list[Worker]]):
    """日の位置で引く担当の並び。要素ごとに step 日ぶん(週は 7、日ごとは 1)。最後の要素は以降も続く。
    普通の list を渡したときは、1 要素 = 1 週(step 7)として扱う。"""

    def __init__(self, crews: Iterable[list[Worker]] = (), step: int = WEEK_DAYS) -> None:
        super().__init__(crews)
        self.step = step


def crew_track(
    weekly: list[list[Assignee]],
    daily: DailyCrew,
    to_workers: Callable[[list[Assignee]], list[Worker]],
) -> CrewTrack:
    """週ごとの担当と日ごとの担当から、算出用の並びを作る。日ごとの週がなければ 1 要素 = 1 週。ある場合は 1 要素 = 1 日に展開する。"""
    if not daily:
        return CrewTrack([to_workers(week) for week in weekly], WEEK_DAYS)
    track = CrewTrack([], 1)
    for days, crew in crew_spans(weekly, daily):
        workers = to_workers(crew)
        track.extend([workers] * days)
    return track
```

`week_index` を差し替える。

```python
def week_index(start: date, day: date, count: int, step: int = WEEK_DAYS) -> int:
    """起点の日から step 日(暦日)ごとの添字(週なら 0 が第1週)。最後の要素より後は最後の要素。起点より前は先頭。"""
    return min(max((day - start).days, 0) // step, count - 1)
```

`crew_on` を差し替える。

```python
def crew_on(task: Task, start: date, day: date) -> list[Assignee]:
    """その日の担当者。週ごとに分けないタスクは assignees。start は実効の開始の日。日ごとの週はその日の担当。"""
    if not task.weekly_crew:
        return task.assignees
    spans = crew_spans(task.weekly_crew, task.daily_crew)
    offset = max((day - start).days, 0)
    for days, crew in spans:
        if offset < days:
            return crew
        offset -= days
    return spans[-1][1]
```

`crew_pieces` の本体を差し替える(署名・docstring の最初の 1 文はそのまま。「日ごとの週は 1 日ごとに切る」を足す)。

```python
    if not task.weekly_crew:
        return [(start, end, task.assignees)]
    pieces: list[tuple[datetime, datetime, list[Assignee]]] = []
    spans = crew_spans(task.weekly_crew, task.daily_crew)
    offset = 0
    for number, (days, crew) in enumerate(spans):
        left = (
            start
            if number == 0
            else datetime.combine(start.date() + timedelta(days=offset), time.min)
        )
        right = (
            end
            if number == len(spans) - 1
            else datetime.combine(start.date() + timedelta(days=offset + days), time.min)
        )
        offset += days
        left, right = max(left, start), min(right, end)
        if left < right:
            pieces.append((left, right, crew))
    return pieces
```

`_crews` と `work_capacity` が `weeks` から並びを作る部分を、step を保つ形にする。

```python
def _track(
    crew: Sequence[Worker] | None, weeks: Sequence[Sequence[Worker]] | None
) -> CrewTrack:
    """算出に使う担当の並び。weeks があればその step を保ち、なければ 1 要素 = 1 週。担当者のいない要素は換算率 1 の 1 人。"""
    if weeks:
        step = getattr(weeks, "step", WEEK_DAYS)
        return CrewTrack([list(week) or [Worker()] for week in weeks], step)
    return CrewTrack([list(crew) if crew else [Worker()]], WEEK_DAYS)
```

`_crews` の `crews = (... )` の式を `crews = _track(crew, weeks)` に、`work_capacity` の同じ式も `crews = _track(crew, weeks)` に置き換える(戻り値の型は `CrewTrack | None`)。`_consume` の `crews: list[list[Worker]]` の型注釈を `CrewTrack` にし、`work_capacity` と `_consume` の `week_index(origin, day, len(crews))` を `week_index(origin, day, len(crews), crews.step)` にする。`_calc_end` の `crews` の型注釈も `CrewTrack`。

`weekly_crews` を差し替える。

```python
def weekly_crews(task: Task, project: Project) -> CrewTrack:
    """週ごとの担当を算出用の Worker にしたもの(パラメータを反映)。日ごとの週があれば 1 日ごとに展開する。週ごとに分けないタスクは空。"""
    return crew_track(
        task.weekly_crew,
        task.daily_crew if task.weekly_crew else {},
        lambda crew: crew_of(
            crew,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        ),
    )
```

(`Iterable`・`Callable` が未 import なら `collections.abc` から足す。`consumed_slices`・`calc_end` は `_crews` を通るので変更不要。)

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_daily_crew_timeline.py test/test_timeline.py test/test_weekly_crew.py test/test_pace.py -q -n auto` / Expected: PASS(既存の timeline・weekly_crew・pace は期待値を変えずに通る)

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 計算を日の位置で引く(CrewTrack。要望 135)"`

---

### Task 4: 完了見込みと増員の試算を、増員日そのままで計算する

**Files:**
- Modify: `src/projectapp/forecast.py`(`snap_week`・`with_added`・`forecast_end`)、`src/projectapp/crew_trial.py`(`trial_weeks`・`evaluate`・`confirmed`)
- Test: `test/test_crew_trial.py`(`snap_week`・`trial_weeks` のテストを置き換える)、`test/test_forecast.py`、`test/test_daily_crew_timeline.py` に追記

**Interfaces:**
- Consumes: `daily_crew.rows_of`・`with_added_from`・`copy_*`(Task 2)、`timeline.crew_track`(Task 3)。
- Produces:
  - `forecast_end(..., extra_crew: tuple[tuple[str, ...], date] | None)`: 増員日は丸めずに使う。起点は常に実効の開始の日。
  - `crew_trial.trial_crews(task, trial, anchor: date) -> tuple[list[list[Assignee]], DailyCrew] | None`
  - `forecast.snap_week`・`forecast.with_added`・`crew_trial.trial_weeks` は削除する。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_crew_trial.py` の `snap_week`・`trial_weeks` に関する 5 件のテスト(`test_snap_week_*`・`test_trial_weeks_*`)と import を消し、次を足す。

```python
from datetime import date

from projectapp.crew_trial import TrialCrew, trial_crews
from projectapp.models import Assignee, Task

T = [Assignee("田中")]


def names(crew):
    return [a.name for a in crew]


def task_with(weeks=None) -> Task:
    return Task("a", id="ta", assignees=list(T), weekly_crew=weeks or [])


def test_trial_crews_from_a_week_head_adds_to_the_week_and_carries_on() -> None:
    weekly, daily = trial_crews(
        task_with(), TrialCrew("ta", ("鈴木",), date(2026, 11, 9)), date(2026, 11, 2)
    )
    assert [names(w) for w in weekly] == [["田中"], ["田中", "鈴木"]] and daily == {}


def test_trial_crews_mid_week_makes_that_week_daily() -> None:
    weekly, daily = trial_crews(
        task_with(), TrialCrew("ta", ("鈴木",), date(2026, 11, 5)), date(2026, 11, 2)
    )
    assert list(daily) == [0]
    assert [names(d) for d in daily[0]] == [["田中"]] * 3 + [["田中", "鈴木"]] * 4
    assert names(weekly[0]) == ["田中", "鈴木"]


def test_trial_crews_keeps_existing_weeks_and_does_not_duplicate() -> None:
    weekly, _ = trial_crews(
        task_with([list(T), list(T)]),
        TrialCrew("ta", ("田中",), date(2026, 11, 9)),
        date(2026, 11, 2),
    )
    assert [names(w) for w in weekly] == [["田中"], ["田中"]]


def test_trial_crews_refuses_beyond_the_week_limit() -> None:
    far = date(2026, 11, 2).replace(year=2028)
    assert trial_crews(task_with(), TrialCrew("ta", ("鈴木",), far), date(2026, 11, 2)) is None
```

`test/test_forecast.py` に足す(`sample()`・`run()`・`START`・`HOLIDAYS` はそのファイルのもの)。

```python
def test_extra_crew_is_not_rounded_to_a_week_head() -> None:
    project, task = sample(effort_hours=60.0)
    now = datetime(2026, 11, 20, 10)
    tuesday = run(project, task, now, (("鈴木",), date(2026, 11, 24)))
    wednesday = run(project, task, now, (("鈴木",), date(2026, 11, 25)))
    next_monday = run(project, task, now, (("鈴木",), date(2026, 11, 30)))
    assert tuesday and wednesday and next_monday
    assert tuesday.end < wednesday.end < next_monday.end  # 1 日ずつ効き方が変わる


def test_extra_crew_from_a_week_head_equals_the_old_week_head_result() -> None:
    project, task = sample(effort_hours=60.0)
    now = datetime(2026, 11, 20, 10)
    head = run(project, task, now, (("鈴木",), date(2026, 11, 30)))
    assert head and head.end == datetime(2026, 12, 1, 13, 30)  # 変更前の週頭の結果(11/30 から 2 人)
```

`test/test_daily_crew_timeline.py` に追記する(確定後の見込み = 試算。休み・年末年始・閏年でも)。

```python
from projectapp.crew_trial import TrialCrew, confirmed, evaluate
from projectapp.forecast import forecast_end
from projectapp.models import Member, Project, Section
from projectapp.timeline import Schedule


def project_of(task: Task, *members: Member, start=START) -> Project:
    return Project(
        name="p",
        base_date=start,
        members=list(members) or [Member("田中"), Member("鈴木")],
        sections=[Section("s", tasks=[task])],
    )


def check_confirmed_equals_trial(day: date, now: datetime, start: datetime, holidays=NONE, members=None):
    task = Task("a", id="ta", planned_start=start, effort_hours=120.0, assignees=[Assignee("田中")])
    project = project_of(task, *(members or [Member("田中"), Member("鈴木")]), start=start)
    schedule = Schedule(project, holidays)
    trial = TrialCrew("ta", ("鈴木",), day)
    result = evaluate(task, project, holidays, schedule, trial, now)
    done = confirmed(task, project, holidays, schedule, trial)
    assert result is not None and done is not None and result.trial_end is not None
    after = forecast_end(done, project, holidays, now, schedule)
    assert after is not None and after.end == result.trial_end
    return result.trial_end


def test_confirmed_forecast_equals_the_trial_for_a_mid_week_day() -> None:
    end = check_confirmed_equals_trial(date(2026, 11, 20), datetime(2026, 11, 19, 10), START)
    assert end > datetime(2026, 11, 19, 10)


def test_confirmed_equals_the_trial_across_the_year_end_break() -> None:
    start = datetime(2026, 12, 7, 9)
    now = datetime(2026, 12, 25, 10)  # 金曜
    results = {
        day: check_confirmed_equals_trial(day, now, start, YEAR_END)
        for day in (date(2026, 12, 26), date(2026, 12, 27), date(2026, 12, 28), date(2027, 1, 4))
    }
    assert len(set(results.values())) == 1  # 休みの間のどの日に指定しても、効き始めは 1/4


def test_confirmed_equals_the_trial_across_a_leap_day_and_a_plain_year() -> None:
    check_confirmed_equals_trial(date(2028, 2, 29), datetime(2028, 2, 28, 10), datetime(2028, 2, 14, 9))
    check_confirmed_equals_trial(date(2028, 3, 1), datetime(2028, 2, 29, 10), datetime(2028, 2, 14, 9))
    check_confirmed_equals_trial(date(2027, 3, 1), datetime(2027, 2, 28, 10), datetime(2027, 2, 15, 9))


def test_a_person_off_delays_the_effect_to_their_next_working_day() -> None:
    members = [
        Member("田中"),
        Member("鈴木", work_days=[WorkDay(date(2026, 11, 20)), WorkDay(date(2026, 11, 23))]),
    ]
    now = datetime(2026, 11, 19, 10)
    from_20 = check_confirmed_equals_trial(date(2026, 11, 20), now, START, NONE, members)
    from_24 = check_confirmed_equals_trial(date(2026, 11, 24), now, START, NONE, members)
    assert from_20 == from_24  # 11/20 は個人の休み、11/21・22 は土日、11/23 は個人の休み
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_crew_trial.py test/test_forecast.py test/test_daily_crew_timeline.py -q` / Expected: FAIL(`trial_crews` がない、増員日が週頭に丸められる)

- [ ] **Step 3: 実装**

`forecast.py`: `snap_week`・`with_added` と、それ専用の import(`MAX_WEEKS`・`Assignee` が他で使われなければ)を消し、`forecast_end` の起点から後ろを差し替える。

```python
    origin = max(now, start)
    anchor = start.date()  # 週の区切りは常に実効の開始から数える(確定後の担当と同じ)
    weekly, daily = rows_of(task)
    if extra_crew is not None:
        names, day = extra_crew
        added = with_added_from(weekly, daily, (day - anchor).days, names)
        if added is None:
            return None
        weekly, daily = added
    track = crew_track(
        weekly,
        daily,
        lambda crew: crew_of(
            crew,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        ),
    )
    end = calc_end(
        origin,
        rest,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=track,
        weeks_start=anchor,
    )
    return None if end is None else Forecast(end, planned)
```

docstring の「増員日は週の境目の遅い側に丸める」を「増員日はそのまま使う(週頭ならその週以降、週の途中ならその週だけ日ごと)」に直す。import は `from projectapp.daily_crew import rows_of, with_added_from` と `from projectapp.timeline import ... crew_track`。

`crew_trial.py`: `trial_weeks` を差し替える。

```python
def trial_crews(
    task: Task, trial: TrialCrew, anchor: date
) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """今の担当に増員分を足した、週ごとの担当と日ごとの担当。増員日はそのまま使う(丸めない)。週数が上限を超えるなら None。"""
    weekly, daily = rows_of(task)
    return with_added_from(weekly, daily, (trial.start - anchor).days, trial.names)
```

`evaluate` の `weeks = trial_weeks(...)` を `crews = trial_crews(task, trial, start.date())`(None なら `return None`)にし、`first = snap_week(...)` を `first = max((trial.start - start.date()).days, 0) // 7` に、`crews_of` の内側関数と最後の `calc_end` を次にする。

```python
    weekly, daily = crews
    ...
    end = calc_end(
        start,
        task.total_effort,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=crew_track(
            weekly,
            daily,
            lambda crew: crew_of(
                crew,
                project.members,
                project.parameters,
                task.parameters,
                project.ratio_limits,
            ),
        ),
    )
```

`confirmed` の末尾を差し替える。

```python
    crews = trial_crews(task, trial, start.date())
    if crews is None:
        return None
    weekly, daily = crews
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )
```

`TrialCrew` の docstring の「start は丸める前の指定日」を「start は増員を始める日(丸めない)」に、`confirmed` の docstring の「増員は次の週の境目から載せる」を「増員日から載せる(過去の週の担当を変えないので、過去の棒は縮まない)」に直す。import の `snap_week, with_added` を消し、`from projectapp.daily_crew import DailyCrew, rows_of, with_added_from` と `crew_track` を足す。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_crew_trial.py test/test_forecast.py test/test_daily_crew_timeline.py test/test_delay_response.py test/test_warning_add_crew.py test/test_forecast_view.py -q -n auto`

Expected: 新規は PASS。`test_warning_add_crew.py::test_adding_crew_writes_weekly_crew_from_the_next_week_as_one_undoable_edit` は、増員日が週頭でなくなったので落ちる。Task 5 で直す(この時点で落ちるのはこの 1 件だけ)。他の既存テストが落ちたら、増員日が週頭でないケースかを確認し、そうでなければ実装の誤りなので直す。

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 増員日を週頭に丸めず日付のまま使う(要望 135)"`

---

### Task 5: 入口の既定の増員日を翌日にし、効き始めを知らせる

**Files:**
- Modify: `src/projectapp/crew_trial.py`(`effect_day` を足す)、`src/projectapp/views.py`(`add_crew_to_warning` ~1700、`try_invest_on_gantt` ~2860、`try_crew_dialog` ~2877)、`src/projectapp/delay_response.py`(ラベル)
- Test: `test/test_warning_add_crew.py`(期待値を直し、追加)、`test/test_delay_response.py`、`test/test_daily_crew_timeline.py`

**Interfaces:**
- Consumes: Task 4 の `TrialCrew`・`confirmed`。
- Produces: `crew_trial.effect_day(project, holidays, name, day, limit=366) -> date | None`(その人が最初に稼働できる日。`day` 以降。見つからなければ None)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_warning_add_crew.py` の最初のテストを、翌日(2026-10-08 木)の増員に合わせて差し替える。

```python
async def test_adding_crew_starts_the_next_day_in_a_daily_week_as_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    before = history_log.dirty_key(view.project)
    assert view.add_crew_to_warning("tw", "鈴木")
    task = view.project.tasks[0]
    assert [a.name for a in task.assignees] == ["田中", "鈴木"]
    assert list(task.daily_crew) == [0]  # 10/5(月)起点の週に、10/8(木)から
    assert [[a.name for a in d] for d in task.daily_crew[0]] == [["田中"]] * 3 + [
        ["田中", "鈴木"]
    ] * 4
    assert view.is_dirty()
    view.undo()
    assert view.project.tasks[0].weekly_crew == []
    assert view.project.tasks[0].daily_crew == {}
    assert history_log.dirty_key(view.project) == before
```

同ファイルに足す(個人の休みの案内)。

```python
async def test_adding_a_person_who_is_off_tells_when_it_takes_effect(
    user: User, tmp_path: Path
) -> None:
    from projectapp.models import WorkDay
    from datetime import date

    view = await opened(user, tmp_path)
    view.project.members[1].work_days = [WorkDay(date(2026, 10, 8)), WorkDay(date(2026, 10, 9))]
    assert view.add_crew_to_warning("tw", "鈴木")
    await user.should_see("10/12")  # 10/8・9 は個人の休み、10/10・11 は土日。効き始めは 10/12(月)
```

`test/test_delay_response.py` に足す。

```python
async def test_try_invest_on_gantt_starts_the_next_day(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    view.project.tasks.append(
        Task("late", id="tl", planned_start=datetime(2026, 10, 12, 9), effort_hours=40.0,
             assignees=[Assignee("田中")])
    )
    view.after_edit()
    assert view.try_invest_on_gantt(("鈴木",)) == 1
    assert view.trials["tl"].start == clock.now().date() + timedelta(days=1)
```

(`clock`・`timedelta` を import する。)`test/test_daily_crew_timeline.py` に `effect_day` のテストを足す。

```python
from projectapp.crew_trial import effect_day


def test_effect_day_skips_weekends_holidays_events_and_personal_days_off() -> None:
    project = project_of(
        Task("a"),
        Member("田中"),
        Member("鈴木", work_days=[WorkDay(date(2027, 1, 4))]),
    )
    assert effect_day(project, YEAR_END, "田中", date(2026, 12, 26)) == date(2027, 1, 4)
    assert effect_day(project, YEAR_END, "鈴木", date(2026, 12, 26)) == date(2027, 1, 5)
    assert effect_day(project, NONE, "田中", date(2026, 11, 2)) == date(2026, 11, 2)
    assert effect_day(project, NONE, "だれか", date(2026, 11, 2)) is None
    assert effect_day(project, YEAR_END, "田中", date(2028, 2, 28)) == date(2028, 2, 28)
    assert effect_day(project, NONE, "田中", date(2028, 2, 26)) == date(2028, 2, 28)  # 土曜 → 月曜
    assert effect_day(project, NONE, "田中", date(2027, 2, 27)) == date(2027, 3, 1)  # 平年: 土曜 → 3/1(月)
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_warning_add_crew.py test/test_delay_response.py test/test_daily_crew_timeline.py -q` / Expected: FAIL

- [ ] **Step 3: 実装**

`crew_trial.py` に足す(`timedelta`・`day_window`・`work_day_map` を import)。

```python
def effect_day(
    project: Project,
    holidays: dict[date, str],
    name: str,
    day: date,
    limit: int = 366,
) -> date | None:
    """name が day 以降で最初に稼働できる日(プロジェクトの休み・個人の休みを除く)。メンバーにいない・limit 日以内にない場合は None。"""
    member = next((m for m in project.members if m.name == name), None)
    if member is None:
        return None
    days = work_day_map(member.work_days)
    for offset in range(limit):
        candidate = day + timedelta(days=offset)
        if (
            day_window(
                candidate, project.daily_hours, project.work_start, holidays, days
            )
            is not None
        ):
            return candidate
    return None
```

`views.py`:
- `add_crew_to_warning`: `now.date()` を `start = now.date() + timedelta(days=1)` にし、`TrialCrew(task_id, (name,), start)` に渡す。docstring を「翌日から」に直す。成功後(`self.after_edit()` の後)に、効き始めの案内を出す。

```python
        if (first := effect_day(self.project, self.holidays, name, start)) is not None and first != start:
            ui.notify(f"{name} は {first.month}/{first.day} から効きます(休みのため)")
```
- `try_invest_on_gantt`: `TrialCrew(task.id, names, now.date())` を `now.date() + timedelta(days=1)` にする。docstring の「今日から」を「翌日から」に。
- 試算ダイアログを開く箇所(`trial_dialog(..., clock.now().date(), ...)`)は `clock.now().date() + timedelta(days=1)` を渡す。`delay_response.trial_dialog` の引数名 `today` を `default_day` に変え、ラベルは `開始日`のまま。`try_crew` の成功後に同じ案内を出す(`names` の各人について `effect_day` が `day` と違うとき)。
- `from datetime import timedelta`・`effect_day` を import する。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_warning_add_crew.py test/test_delay_response.py test/test_daily_crew_timeline.py test/test_dashboard_view.py -q -n auto` / Expected: PASS

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 増員の既定を翌日にし、休みの効き始めを知らせる(要望 135)"`

---

### Task 6: 日ごとの編集(ダイアログと操作)

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`open_week_crew_dialog` ~997、`open_day_crew_dialog` を足す)、`src/projectapp/views.py`(`toggle_weeks`・`edit_week_crew` ~2888-2937、新しい操作)、`src/projectapp/gantt.py`(`ViewActions` ~675)
- Test: `test/test_daily_crew_view.py`(新規)

**Interfaces:**
- Consumes: `daily_crew.split_week`・`merge_week`・`set_week_days`(Task 2)。
- Produces:
  - `MainView.split_week_days(path, index, week)`、`merge_week_days(path, index, week)`、`save_week_days(path, index, week, days)`(いずれも元に戻せる 1 回の編集。割り当て超過の通知は `warn_overallocation`)
  - `open_day_crew_dialog(number, labels, days, members, on_save, on_merge, period="")`
  - `open_week_crew_dialog(..., on_split=None)`: `日ごとに分ける`ボタン(マーカー `week-edit-split`)。

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_daily_crew_view.py
from datetime import datetime
from pathlib import Path

from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.models import Assignee, Member, Task
from projectapp.views import MainView
from test_views import make_view

START = datetime(2099, 1, 5, 9)  # 月曜


async def opened(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中"), Member("鈴木")]
    view.project.tasks.append(
        Task("a", id="ta", planned_start=START, effort_hours=60.0,
             assignees=[Assignee("田中")], weekly_crew=[[Assignee("田中")], [Assignee("田中")]])
    )
    view.after_edit()
    view.mark_clean()
    return view


async def test_split_edit_and_merge_a_week_are_each_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 1)
    task = view.project.tasks[0]
    assert list(task.daily_crew) == [1] and view.is_dirty()
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木")]] * 4
    view.save_week_days((), 0, 1, days)
    task = view.project.tasks[0]
    assert [a.name for a in task.weekly_crew[1]] == ["田中", "鈴木"]
    assert [a.name for a in task.assignees] == ["田中", "鈴木"]
    view.merge_week_days((), 0, 1)
    task = view.project.tasks[0]
    assert task.daily_crew == {} and [a.name for a in task.weekly_crew[1]] == ["田中"]
    view.undo()
    assert list(view.project.tasks[0].daily_crew) == [1]
    view.undo()
    view.undo()
    assert view.project.tasks[0].daily_crew == {}


async def test_stopping_weekly_crew_drops_the_daily_crew(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 0)
    view.toggle_weeks((), 0)
    task = view.project.tasks[0]
    assert task.weekly_crew == [] and task.daily_crew == {}


async def test_clicking_a_daily_week_opens_the_day_dialog(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.edit_week_crew((), 0, 0)
    await user.should_see(marker="week-edit-split")
    user.find(marker="week-edit-split").click()
    await user.should_see(marker="day-edit-title")
    assert text_of(user, "day-edit-title").startswith("第1週")
    await user.should_see(marker="day-edit-merge")
    await user.should_see(marker="day-edit-row-6")  # 7 日ぶんの行


def text_of(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_daily_crew_view.py -q` / Expected: FAIL

- [ ] **Step 3: 実装**

`views.py`: 次の 3 つのメソッドを `edit_week_crew` の前に足す。

```python
    def _replace_task_at(self, path: SectionPath, index: int, saved: Task | None) -> None:
        if saved is None:
            ui.notify("この週は日ごとに変えられません")
            return
        self.tasks_in(path)[index] = saved
        self.after_edit()
        self.warn_overallocation(saved)

    def split_week_days(self, path: SectionPath, index: int, week: int) -> None:
        """週を日ごとに分ける(その週の担当を 7 日すべてにコピー。元に戻せる 1 回の編集)。"""
        self._replace_task_at(path, index, split_week(self.tasks_in(path)[index], week))

    def merge_week_days(self, path: SectionPath, index: int, week: int) -> None:
        """日ごとの週を週に戻す(1 日目の担当を週の担当にする)。"""
        self._replace_task_at(path, index, merge_week(self.tasks_in(path)[index], week))

    def save_week_days(
        self, path: SectionPath, index: int, week: int, days: list[list[Assignee]]
    ) -> None:
        """日ごとの週の 7 日ぶんの担当を保存する。"""
        self._replace_task_at(
            path, index, set_week_days(self.tasks_in(path)[index], week, days)
        )
```

`toggle_weeks` の「週ごとをやめる」の `replace(task, weekly_crew=[], assignees=list(task.weekly_crew[0]))` に `daily_crew={}` を足す。`edit_week_crew` を、日ごとの週ならば日のダイアログを開くように差し替える。

```python
    def edit_week_crew(self, path: SectionPath, index: int, week: int) -> None:
        """週ごとのタスクの、1 週ぶんの担当だけを直す(ガントチャートのチップのクリック)。日ごとの週は、7 日ぶんを直すダイアログを開く。"""
        task = self.tasks_in(path)[index]
        if not task.weekly_crew or week >= MAX_WEEKS:
            return
        period_start: date | None = None
        schedule = Schedule(self.project, self.holidays)
        if (start := effective_start(task, self.project, self.holidays, schedule)) is not None:
            period_start = start.date() + timedelta(days=7 * week)
        period = (
            f"{short_date(period_start)}〜{short_date(period_start + timedelta(days=6))}"
            if period_start is not None
            else ""
        )
        if week in task.daily_crew and week < len(task.weekly_crew):
            labels = [
                f"{short_date(period_start + timedelta(days=j))}({WEEKDAYS[(period_start + timedelta(days=j)).weekday()]})"
                if period_start is not None
                else f"{j + 1}日目"
                for j in range(7)
            ]
            open_day_crew_dialog(
                week + 1,
                labels,
                task.daily_crew[week],
                self.project.members,
                lambda days: self.save_week_days(path, index, week, days),
                lambda: self.merge_week_days(path, index, week),
                period,
            )
            return
        shown = task.weekly_crew[min(week, len(task.weekly_crew) - 1)]  # 定義した週より後は、最後の週の担当が続いている

        def apply(crew: list[Assignee]) -> None:
            ...(既存の apply をそのまま)

        open_week_crew_dialog(
            week + 1,
            shown,
            self.project.members,
            apply,
            period,
            on_split=lambda: self.split_week_days(path, index, week),
        )
```

(`apply` の本体は既存のものを移す。`WEEKDAYS` は `gantt.py` の定数を import するか、`"月火水木金土日"[weekday]` を使う。`split_week`・`merge_week`・`set_week_days` を `daily_crew` から import する。)

`task_dialog.py`: `open_week_crew_dialog` に引数 `on_split: Callable[[], object] | None = None` を足し、`ui.row()` のボタン行に次を足す。

```python
            if on_split is not None:
                ui.button(
                    "日ごとに分ける",
                    on_click=lambda: (dialog.close(), on_split()),
                ).props("flat").mark("week-edit-split")
```

同じファイルに日ごとのダイアログを足す。

```python
def open_day_crew_dialog(
    number: int,
    labels: list[str],
    days: list[list[Assignee]],
    members: list[Member],
    on_save: Callable[[list[list[Assignee]]], object],
    on_merge: Callable[[], object],
    period: str = "",
) -> None:
    """日ごとの週の、7 日ぶんの担当を直すダイアログ。タイトルは「第N週 期間(日ごと)」。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label(f"第{number}週 {period}(日ごと)".replace("  ", " ")).classes(
            "text-h6"
        ).mark("day-edit-title")
        rows: list[AssigneeFields] = []
        with ui.column().classes("w-full gap-2").style("max-height: 60vh; overflow-y: auto"):
            for j, (label, crew) in enumerate(zip(labels, days)):
                ui.label(label).classes("text-caption text-grey").mark(f"day-edit-label-{j}")
                with ui.column().classes("w-full").mark(f"day-edit-row-{j}"):
                    rows.append(
                        AssigneeFields(crew, members, lambda: None, marker=f"day-edit-{j}")
                    )
        error = ui.label("").classes("text-negative").mark("day-edit-error")

        def save() -> None:
            chosen: list[list[Assignee]] = []
            for j, fields in enumerate(rows):
                try:
                    crew = _build_assignees(fields.rows())
                except ValueError as exc:
                    error.set_text(f"{labels[j]}: {exc}")
                    return
                if not crew:
                    error.set_text(f"{labels[j]}: 担当者を選んでください")
                    return
                chosen.append(crew)
            dialog.close()
            on_save(chosen)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button(
                "週ごとに戻す", on_click=lambda: (dialog.close(), on_merge())
            ).props("flat").mark("day-edit-merge")
            ui.button("保存", on_click=save).mark("day-edit-save")
    dialog.open()
```

`gantt.py` の `ViewActions` は変更不要(チップのクリックは `edit_week_crew(path, ti, week)` のまま)。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_daily_crew_view.py test/test_weekly_crew.py test/test_views.py -q -n auto` / Expected: PASS

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 週を日ごとに分ける・戻す・直す(要望 135)"`

---

### Task 7: ガントの日ごとのチップと表示の区別

**Files:**
- Modify: `src/projectapp/gantt.py`(`week_summary` ~550、`week_chips` ~3287-3372)、`src/projectapp/delay_response.py`(`DELAY_RESPONSE_CSS` に `.day-chip`)、`src/projectapp/bottom_info.py`(~142)
- Test: `test/test_daily_crew_view.py` に追記、`test/test_bottom_info.py`

**Interfaces:**
- Consumes: `daily_crew.segments`・`Segment`(Task 2)。
- Produces: マーカー `day-chip-{key}-{ti}-{week}-{day}`(日ごとのチップ)、`week-chip-{key}-{ti}-{week}`(週のチップ。既存のまま)、`week-added-…` は両方に付く。`week_summary(task, start)` に日ごとの週の行が入る。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_daily_crew_view.py` に足す。`opened` で作ったタスクは、実績のない通常タスク。`view.split_week_days((), 0, 0)` の後に描画を待つ。

```python
async def test_a_daily_week_shows_seven_day_chips_and_a_weekly_one_shows_one(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    await user.should_see(marker="week-chip-top-0-0")
    view.split_week_days((), 0, 0)
    for j in range(7):
        await user.should_see(marker=f"day-chip-top-0-0-{j}")
    await user.should_not_see(marker="week-chip-top-0-0")
    await user.should_see(marker="week-chip-top-0-1")  # 次の週は週のまま


async def test_day_chips_have_a_distinct_class_and_a_dated_hover(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 0)
    await user.should_see(marker="day-chip-top-0-0-2")
    chip = user.find(marker="day-chip-top-0-0-2").elements.pop()
    assert "day-chip" in chip.classes
    tip = [e for e in chip.default_slot.children if hasattr(e, "text")]
    assert any("第1週 1/7(水)" in getattr(t, "text", "") for t in tip)


async def test_a_person_joining_mid_week_marks_the_day_chip_as_added(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.split_week_days((), 0, 0)
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木")]] * 4
    view.save_week_days((), 0, 0, days)
    await user.should_see(marker="day-chip-top-0-0-3")
    await user.should_see(marker="week-added-top-0-0-3")
    await user.should_not_see(marker="week-added-top-0-0-4")  # 前の日と同じ顔ぶれは増員の目印なし
```

(`tooltip` の中身の取り出し方は、既存の週チップのテスト(`grep -n "week-chip" test/test_gantt.py` と `test_weekly_crew.py`)に合わせる。上の `chip.default_slot` の読み方が合わなければ、既存テストが週チップのホバーを読む方法に置き換える。)

`test/test_bottom_info.py` に足す。

```python
def test_detail_marks_a_task_that_has_a_daily_week() -> None:
    task = Task(
        "a",
        id="ta",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=20.0,
        assignees=[Assignee("田中")],
        weekly_crew=[[Assignee("田中")]],
        daily_crew={0: [[Assignee("田中")]] * 7},
    )
    project, schedule, now = env(task)  # 既存の組み立て関数に合わせる
    detail = task_detail(task, project, {}, now, schedule)
    assert "日ごとの週あり" in dict(detail.lines)["担当"]
```

(`env()` の戻り値の形は、`test_bottom_info.py:39` の定義に合わせる。)

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_daily_crew_view.py test/test_bottom_info.py -q` / Expected: FAIL

- [ ] **Step 3: 実装**

`delay_response.py` の `DELAY_RESPONSE_CSS` に足す(増員の紫とは別の色。日ごとは青緑の下線と、濃い背景と、日ごとの細い区切り)。

```css
:root { --day-accent: #26a69a; }
body.body--dark { --day-accent: #4db6ac; }
.day-chip { background: rgba(0,0,0,0.45) !important; box-sizing: border-box;
  border-bottom: 3px solid var(--day-accent); border-left: 1px dotted rgba(255,255,255,0.9); }
```

(`:root` と `body.body--dark` の行は既存の定義の近くに置き、既存のブロックと混ぜない。)

`gantt.py` の `week_summary` を差し替える。

```python
def week_summary(task: Task, start: date | None = None) -> str:
    """週ごとの担当の説明(マウスオーバー用)。週ごとに分けないタスクは空。日ごとの週は 1 日ずつ行を足す。"""
    lines = []
    for number, week in enumerate(task.weekly_crew, start=1):
        first = start + timedelta(days=7 * (number - 1)) if start is not None else None
        period = (
            f" {short_date(first)}〜{short_date(first + timedelta(days=6))}"
            if first is not None
            else ""
        )
        days = task.daily_crew.get(number - 1)
        if days is None or len(days) != 7:
            lines.append(f"第{number}週{period}: {crew_text(week)}")
            continue
        lines.append(f"第{number}週{period}(日ごと)")
        for j, crew in enumerate(days):
            label = (
                f"{short_date(first + timedelta(days=j))}({WEEKDAYS[(first + timedelta(days=j)).weekday()]})"
                if first is not None
                else f"{j + 1}日目"
            )
            lines.append(f"  {label}: {crew_text(crew)}")
    return "\n".join(lines)
```

`week_chips` の本体を `segments` で回すように差し替える。`defined = len(task.weekly_crew)`〜`while ...` のループ全体を次にする(`ui.label` の生成・アイコン・オーバーロード表示・`week-added`・クリックは既存のまま。`index` を `Segment` から決め、日ごとのチップには `day-chip` クラスと日付つきの見出しを付ける)。

```python
        last_day = (end - timedelta(microseconds=1)).date()
        previous: list[Assignee] | None = None
        for seg in segments(task.weekly_crew, task.daily_crew, start.date(), last_day):
            left = start if seg.first == start.date() else datetime.combine(seg.first, time.min)
            right = min(datetime.combine(seg.last + timedelta(days=1), time.min), end)
            crew = seg.crew
            index = seg.week
            origin, length = interval_span(left, right, columns)
            left_px = max((origin - bar_left) * width, 0.0)
            width_px = min(length * width, bar_width - left_px)
            before, previous = previous, crew
            if width_px <= 0:
                continue
            daily = seg.day is not None
            divider = (
                " border-left: 1px solid rgba(255,255,255,0.8);"
                if (index and not daily)
                else ""
            )
            text = week_chip_text([a.name for a in crew], width_px, self.view_scale)
            shown = crew[:MAX_ASSIGNEE_CHIPS]
            with_icons = bool(text) and any(self.icon_lookup.get(a.name) for a in shown)
            chip = ui.label("" if with_icons else text).style(
                f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px; top: 0;"
                f" height: {WEEK_CHIP_HEIGHT_PX}px; font-size: 10px; line-height: {WEEK_CHIP_HEIGHT_PX}px;"
                f" color: #fff; background: rgba(0,0,0,0.3); padding-left: 3px; overflow: hidden;"
                f" white-space: nowrap; z-index: 1; text-shadow: {WEEK_CHIP_TEXT_SHADOW};{divider}"
            )
            if daily:
                chip.classes("day-chip")
            ...(アイコン表示・見出し・負荷・増員の目印は既存のまま。次の 3 点だけ変える)
```

変える 3 点:
- 見出し `title`: 週は `第{N}週 {m/d}〜{m/d}{carried}`、日ごとは `第{N}週 {m/d}({曜}) 日ごと`(`carried` は `seg.carried` のとき `(第{defined}週の担当が続く)`、日ごとの週の後ろで続くときは `(最後の日の担当が続く)`)。`last_day` の変数名は上の外側のものと衝突するので、ループ内では `seg.last` を使う。
- 増員の目印: `if before is not None and not seg.carried:` で、`{a.name for a in crew} - {a.name for a in before}` が空でなければ `week-added` を付ける(元の `1 <= index < defined` の条件の一般化)。
- マーカー: 週は `week-chip-{key}-{ti}-{index}`(既存)、日ごとは `day-chip-{key}-{ti}-{index}-{seg.day}`。`week-added-{key}-{ti}-{index}` は日ごとでは `week-added-{key}-{ti}-{index}-{seg.day}`。
- クリック: 日ごとのチップも `edit_week_crew(path, ti, seg.week)`(週全体のダイアログ)。

`from projectapp.daily_crew import segments` を import する。

`bottom_info.py`: `("担当", _crew(task)),` を次にする。

```python
        ("担当", _crew(task) + (" (日ごとの週あり)" if task.daily_crew else "")),
```

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_daily_crew_view.py test/test_bottom_info.py test/test_weekly_crew.py test/test_gantt.py -q -n auto` / Expected: PASS(既存の週チップのテストは、`week-chip-*` のマーカーと見出しが変わらないので通る)

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: ガントに日ごとのチップを出し、週と区別する(要望 135)"`

---

### Task 8: 周辺機能(マージ・一括編集・分解・複製・PlantUML ほか)

**Files:**
- Modify: `src/projectapp/merge.py`(~349 の項目名、~383-395 の平坦化、~554 の表示、~596-645 の復元)、`src/projectapp/bulk_edit.py`(~253-292)、`src/projectapp/decompose.py`(~137 と `weekly_crew=[]` の箇所)、`src/projectapp/forms.py`(~238・287・442・465)、`src/projectapp/arrange.py`(~137)、`src/projectapp/task_dialog.py`(~1376)、`src/projectapp/plantuml.py`(~54-70・336)、`src/projectapp/views.py`(~2233)
- Test: `test/test_daily_crew_others.py`(新規)

**Interfaces:**
- Consumes: Task 1〜3 の `daily_crew`・`crew_on`・`crew_track`。

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_daily_crew_others.py
from datetime import date, datetime

from projectapp.arrange import duplicate_task  # 既存の複製関数の名前に合わせる
from projectapp.bulk_edit import CrewChange, CrewMode, apply_bulk  # 既存の名前に合わせる
from projectapp.models import Assignee, Member, Project, Section, Task

T = [Assignee("田中")]
TS = [Assignee("田中"), Assignee("鈴木")]
DAYS = [list(T)] * 3 + [list(TS)] * 4


def daily_task() -> Task:
    return Task(
        "a",
        id="ta",
        planned_start=datetime(2026, 11, 2, 9),
        effort_hours=20.0,
        assignees=list(TS),
        weekly_crew=[list(TS), list(T)],
        daily_crew={0: [list(d) for d in DAYS]},
    )


def names(crew):
    return [a.name for a in crew]
```

各領域の具体的なテストは、実装の直前に既存のテスト(`test_bulk_edit.py`・`test_merge.py`・`test_decompose.py`・`test_plantuml.py`)の組み立てを複製して書く。必須の確認事項は次のとおり。

1. **一括編集 ADD**: `daily_crew` の日ごとの週に、足した人が全日に入り、`weekly_crew[0]` は和集合のまま。
2. **一括編集 REMOVE**: 日ごとの週から人を外すと、各日から外れ、担当のいなくなった日は(その週の外した後の担当で)埋まる。全週が空になれば `weekly_crew=[]`・`daily_crew={}`・担当なし。
3. **一括編集 REPLACE**: `daily_crew == {}`、`weeks_dropped` を数える。
4. **マージ**: 3 者マージで、片側だけが日ごとの週を直したときはその変更が入る。両側が同じ週を別々に直したときは衝突が週単位で出る。メンバーを外すと、その人は日から外れ、空の日は週の担当で埋まる。
5. **分解**: 実績のあるタスクの分解で、`crew_on` が日ごとの担当を返し(今日の担当)、親(まとめ)になったタスクは `daily_crew == {}`。
6. **複製**: `daily_crew` が写される(元を変えても複製は変わらない)。
7. **種別変更**: 通常 → チェックポイントなどに変えたタスクは `weekly_crew == []` と `daily_crew == {}`。
8. **フォーム**: 編集ダイアログで保存しても `daily_crew` が消えない。
9. **PlantUML**: 日ごとの週を持つタスクを `weekly_tasks` に数え、通知に `日ごとの週あり n 件` が入る。
10. **担当者向けファイル**: 日ごとの週のある担当者の見積もりが、日ごとの担当で按分される(`handoff` は `weekly_crews` を通るので、日ごとに展開された並びで数える)。

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_daily_crew_others.py -q` / Expected: FAIL

- [ ] **Step 3: 実装**

`bulk_edit.py` `_crew_applied`: 週ごとのタスク(`weeks` が空でない)の分岐に、日ごとの扱いを足す。

```python
    daily = task.daily_crew
```
- ADD: `added = [add(w) for w in weeks]` の後で `days = {k: [add(d) for d in ds] for k, ds in daily.items()}` とし、`replace(task, weekly_crew=added, daily_crew=days, assignees=union_assignees(added))`。日ごとの週の `weekly_crew[k]` は、`add` が和集合に人を足すだけなので和集合のまま。
- REMOVE: `filled, empties = fill_empty_weeks([drop(w) for w in weeks])` の後で、日ごとの週ごとに `days = [drop(d) or _copy(filled[k]) for d in ds]` とし、`filled[k] = union_assignees(days)`、`daily_crew` を作り直す。全週が空の分岐は `replace(task, weekly_crew=[], daily_crew={}, assignees=[])`。
- REPLACE: `replace(task, weekly_crew=[], daily_crew={}, assignees=_copy(change.members))`。

`merge.py`:
- 項目名の表(~349)に `"daily_crew": "日ごとの担当"` を足す。
- 平坦化(~383): `if f.name not in ("id", "assignees", "weekly_crew")` に `"daily_crew"` を足し、`record["daily_crew"] = {week: [[(ids.get(a.name, a.name), a.allocation) for a in day] for day in days] for week, days in t.daily_crew.items()}` を足す。
- 表示(~554): `daily_crew` は、`第{週+1}週(日ごと): 月 田中 100%、…` の行にする。
- 復元(~596〜): `weekly_crew` と同じ手順で、メンバーを名前に戻す(いない人は外して `notes` に`日ごとの担当から外しました`を足す)。空になった日は、その週の担当(`weeks[k]`)で埋める。`weeks` に存在しない週の添字は捨てる。`make_task` の `data` の除外リストに `"daily_crew"` を足し、`Task(..., daily_crew=daily, ...)` で渡す。

`decompose.py`: ~137 の `task.weekly_crew[week_index(anchor, today.date(), len(task.weekly_crew))] if task.weekly_crew else task.assignees` を `crew_on(task, anchor, today.date())` に差し替える(`crew_on` は週ごとでなければ `assignees`)。~330 の `weekly_crew=[]` が `replace(` の呼び出しなら、`daily_crew={}` を並べる。`Task(` の構築なら既定値で足りる。

`forms.py`: ~238・~287 の `weekly_crew=[]` が `replace(base, ...)` の中なら `daily_crew={}` を並べる。~442・~465 の保存では、`daily_crew=base.daily_crew`(複製)を `replace` に渡して消えないようにする。`arrange.py` ~137: `daily_crew=copy_daily(original.daily_crew)` を並べる。`task_dialog.py` ~1376: `weeks=[crew_of(week, member_list) for week in initial.weekly_crew]` を `weeks=crew_track(initial.weekly_crew, initial.daily_crew, lambda crew: crew_of(crew, member_list))` に差し替える(`DateTimeFields` の `weeks` の型注釈を `Sequence[Sequence[Worker]]` のままで受けられることを確認する)。

`storage.py` の ~797・~818・~954 の `weekly_crew=[]`(参照・チェックポイントなど別種別の `Task(` の構築)は既定値で足りる。`replace(` の呼び出しなら `daily_crew={}` を並べる。

`plantuml.py`: `PlantUmlResult`(~54)に `daily_tasks: int = 0` を足し、~336 に `daily_tasks = sum(1 for t in order if t.daily_crew) if show_chips else 0` を足して結果に渡す。`weekly_crew_notice(count, daily=0)` の文末に、`daily > 0` のとき `(うち日ごとの週あり {daily} 件)` を足す。`views.py` ~2233 は `weekly_crew_notice(result.weekly_tasks, result.daily_tasks)`。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_daily_crew_others.py test/test_bulk_edit.py test/test_merge.py test/test_decompose.py test/test_plantuml.py test/test_handoff.py test/test_forms.py -q -n auto` / Expected: PASS

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 日ごとの担当を、マージ・一括編集・分解・複製・書き出しで扱う(要望 135)"`

---

### Task 9: 文書・確認用データ・全体の検証

**Files:**
- Modify: `.claude/spec/concept.md`(週ごとの担当の項と完了見込みの項)、`.claude/spec/gantt.md`(増員の試算の項・完了見込みの項・日ごとのチップ)、`.claude/spec/dashboard.md`(要望 134 の項)、`.claude/spec/project-files.md`(version 22)、`docs/development.md`(`daily_crew.py`)、`docs/requests.md`(要望 135 を完了に)、`CLAUDE.md`(現在 21 → 22)、`docs/superpowers/specs/2026-11-08-daily-crew-design.md`(休みの案内を通知に)
- Create: `docs/samples/日ごとの担当の確認.json`

- [ ] **Step 1: 仕様を更新する**
  - `concept.md`: 週ごとの担当の項に、`日ごとに分ける`(選んだ 1 週だけ。`daily_crew`)と、`日ごとの週でも weekly_crew はその週の担当の和集合`を足す。完了見込みの項の「週の区切りの数え方が試算は今日から、確定後は開始から」の限界の文を削除し、`増員日はそのまま使うので、確定後の見込みは試算と同じ日になる`に直す。
  - `gantt.md`: 増員の試算の項の`増員日は… 7 日ごとの週の境目に遅い側へ丸める`を、`増員日はそのまま使う(週頭なら日ごとにせず、週の途中ならその週だけ日ごと)。既定は翌日`に直す。日ごとのチップ(週チップと色・区切り・ホバーが違う)と、週チップのダイアログの`日ごとに分ける`・`週ごとに戻す`を足す。増員する人が休みのときは、効き始めを通知で知らせる。
  - `dashboard.md`: 134 の項の`今日の次の週頭から`を`翌日から(増員日を含む週だけ日ごと)`に直す。
  - `project-files.md`: version 22(`daily_crew`)を足す。`CLAUDE.md` の`現在 21`を`現在 22`に。
  - `docs/development.md`: `daily_crew.py`(日ごとの担当の純粋関数)と `timeline.CrewTrack` を足す。
  - `docs/requests.md`: 要望 135 の状態を`完了`にし、実績(設計書・計画・年末年始と閏年と個人の休みのテスト)を書く。
  - 設計書: 「ダイアログに`この人は… 休みです`を出す」を「通知に`{名前} は m/d から効きます(休みのため)`を出す」に直す。

- [ ] **Step 2: 確認用データ** — `cp docs/samples/完了見込みの確認.json docs/samples/日ごとの担当の確認.json`(警告・予定超過のタスクを含む)。`~/.projectapp` へのコピーは利用者に確認してから。

- [ ] **Step 3: 全体の検証** — Run: `uv run pytest -m smoke` → `uvx ruff check` → `uvx ruff format src test` → `uvx ty check src` / Expected: すべて成功。smoke が落ちたときだけ `uv run pytest -n auto` を走らせ、原因を直す。

- [ ] **Step 4: 最終レビュー** — sonnet のサブエージェントに、`git diff develop...HEAD` を設計書と照らしてレビューさせる(Review Focus の 5 項目と、`daily_crew` が空のときの結果の一致を重点に)。指摘は、仕様に反するものだけ直す。

- [ ] **Step 5: Commit と PR** — `git add -A docs src test .claude CLAUDE.md && git commit -m "docs: 日ごとの担当(要望 135)の仕様・開発文書・確認用データを更新する"`。`git push -u origin feature/daily-crew` のあと、`develop` 向けの PR を作って止まる(マージは利用者の指示を待つ)。

---

### Task 10: Artifact の資料を更新する(試算と見込みの考え方)

**Files:**
- Modify: `/private/tmp/claude-501/-Users-jun-Documents-opt-work-projectapp/4fc6227d-93d4-4cea-ab31-08a374885967/scratchpad/forecast-vs-trial.html`(Artifact `https://claude.ai/code/artifact/6c481c81-6934-46b7-a834-18dffaa79da8`)

実装が確定したあと(PR を作ったあと)に行う。利用者の依頼:「試算と見込みの考え方が更新されたので、Artifacts の資料も更新する」。

- [ ] **Step 1: 内容を直す**
  - 図 2(増員の試算): 増員日を `11/30`(週頭)から、`翌日(11/24)` に変え、**週の途中から効く**ようにする。棒が 11/24 から太くなり、増員日の線のラベルを`増員日(丸めない)`に直す。「3 日早まる」などの数値は、例のまま整合するように計算し直す。
  - 図 1(完了見込み)・共通の計算の図: 「週ごとの担当」に加えて「日ごとの週」を描く。共通の計算の図の確定の戻り(点線)に`増員日を含む週だけ日ごと`を足す。
  - 比較表: 「週の数え方」の行を`増員日を丸めず、増員日を含む週だけ日ごとに分ける。確定後の見込みは試算と同じ日になる`に直す。「決めてほしいこと」の節は、決着したので`日ごとの担当(要望 135)`の節に置き換える(休み・年末年始・閏年・個人の休みの扱いを 3 行で)。
- [ ] **Step 2: 公開** — 同じファイルパスで Artifact を再公開する(`edits` か Edit のあと、同じパスで publish)。URL は変わらない。
- [ ] **Step 3: 報告** — 更新した URL と、直した点を利用者に伝える。

---

## Self-Review

- **Spec coverage:** 設計書 §2 データ → Task 1・2、§3 計算 → Task 3、§4 遅延対応との接続 → Task 4・5、§5 画面 → Task 6・7、§6 影響する機能 → Task 8、§7 テスト(1 互換・2 等価 → Task 3、3 日ごとの効き方 → Task 3、4 増員日の位置 → Task 2・4、5 翌日と休み・6 年末年始・7 閏年・8 一致・9 個人の休み → Task 3・4・5、10 ファイル → Task 1、11 画面 → Task 6・7、12 マージほか → Task 8、13 性能 → Task 9 の smoke と既存の性能テスト)、§8 守ること → Global Constraints。文書 → Task 9、Artifact → Task 10。
- **Placeholder scan:** Task 8 の各テストは、既存のテストの組み立てを複製して書く指示にした(関数名・引数が実装を読まないと決まらないため)。必須の確認事項を 10 項目に列挙している。Task 7 の `week_chips` の「既存のまま」の部分は、置き換えるループの前後が元のコードにある範囲を指す。
- **Type consistency:** `DailyCrew`・`rows_of`・`with_added_from`・`crew_spans`・`segments`・`split_week`・`merge_week`・`set_week_days`(Task 2)、`CrewTrack`・`crew_track`・`week_index(step)`(Task 3)、`trial_crews`・`forecast_end(extra_crew)`(Task 4)、`effect_day`(Task 5)、`split_week_days`・`merge_week_days`・`save_week_days`・`open_day_crew_dialog`(Task 6)、マーカー `day-chip-{key}-{ti}-{week}-{day}`(Task 7)で一致している。
- **Review Focus の対応:** 1 → Task 3・4 の年末年始のテスト、2 → Task 3・4・5 の閏年のテスト、3 → Task 3・4・5 の個人の休みのテスト、4 → Task 2・3 の最後の日ごとの週のテスト、5 → Task 6 の`週ごとをやめる`・Task 8 の置き換え・種別変更・Task 1 の添字の拒否。
