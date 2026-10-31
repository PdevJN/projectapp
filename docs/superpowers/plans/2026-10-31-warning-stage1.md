# 警告の状態 段階 1(判定・ガントチャート・警告の色)実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 残りの工数と完了予定までの稼働量の比が 110% 以上のタスクを `警告` と判定し、ガントチャートの行と名前の欄に、予定超過(赤)とは別の色(設定で変えられる)で出す。

**Architecture:** 残りの工数の計算を `dashboard.py` から独立モジュール `remaining.py` に移して共有する。完了予定までの稼働量を数える純粋関数 `timeline.work_capacity` を足し、判定は新しい純粋モジュール `pace.py`(`Pace`・`pace`・`warning_pace`)に置く。表示は `gantt.py` の `task_row` で、予定超過と同じ場所に CSS 変数 `--warning` の色の薄い背景を重ねる。色は `config.json` の `warning_color`(今日の線の色と同じ仕組み)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、`ty`

**Spec:** [`docs/superpowers/specs/2026-10-31-warning-status-design.md`](../specs/2026-10-31-warning-status-design.md)(要望 103。この計画は段階 1。段階 2: ダッシュボードとメンバーの閾値、段階 3: 要望 98 のボタン)

## Global Constraints

- 判定は `残りの工数 ÷ 今から完了予定までの稼働量 ≥ 1.10`(固定)。稼働量が 0 で残りがあるときも警告。
- 警告にしないもの: まとめ・チェックポイント・プロジェクト参照、状態`終了`、工数がない・完了予定が決まらない・完了予定が今以前、予定超過(`is_overdue`)、残りの工数が 0 以下。
- 予定超過(赤)を優先する。警告は行と名前の欄の背景(薄い色)だけに使い、棒は状態色のまま。
- 表示は、予定超過の赤みと同じ表示項目(`ViewOptions.show_alerts`)に従う。PlantUML には出さない。
- 警告の色は `~/.projectapp/config.json` の `warning_color`(`#rrggbb`、全プロジェクト共通、ライト・ダークで同じ色)。元に戻す・やり直しの対象にしない。既定は `#fdd835`(黄。`dataviz` のバリデータで、赤 `#e53935`・橙 `#fb8c00` と ΔE 14.0 以上で区別できる)。
- 状態色(`STATUS_COLORS`)は変えない(要望 107)。ファイル形式(version)は変えない(段階 2 で 19)。
- 残りの工数の計算で使う工数は、`remaining.total_effort(task)` の 1 か所から取る(要望 105 で追加工数を足すため)。
- 画面の文言に「要望 N」は書かない。コメントには書いてよい。
- 実装のたびに `uv run pytest -m smoke`。失敗したら `uv run pytest -n auto` で詳細を確認する。PR・コミットの前は `uv run pytest -n auto` と `uv run ty check src`(診断は変更前と同じ 1 件)。

## Review Focus

- 予定どおりに進んでいるタスク(比 100%)が警告にならないこと(80% 基準だと全部警告になる。境界の 1.10 の両側をテストする)。
- 完了予定を手で指定して余裕があるタスクは警告にならないこと。完了予定が工数に対して短すぎるタスクは開始前でも警告になること。
- 予定超過(赤)のタスクに警告の色が重ならないこと。表示項目をオフにすると警告も消えること。
- 担当者の稼働日の上書き・祝日・週ごとの担当で、稼働量が `calc_end` の消化と同じ枠を数えること(工数ちょうどの稼働量で、終了が完了予定に一致する)。
- 警告の色が不正・空・保存失敗のときの挙動(不正は適用できない。空は既定。保存失敗は通知して保存済みの色を変えない)。

## ファイル構成

| ファイル | 内容 |
|---|---|
| `src/projectapp/remaining.py`(新規) | `total_effort`・`overlap_hours`・`open_hours`・`remaining_hours`(`dashboard.py` から移す) |
| `src/projectapp/pace.py`(新規) | `WARNING_RATIO`・`Pace`・`pace`・`warning_pace` |
| `src/projectapp/timeline.py` | `work_capacity` を足す |
| `src/projectapp/dashboard.py` | 移した関数を `remaining.py` から使う。工数は `total_effort` を通す |
| `src/projectapp/theme.py`・`config.py` | `parse_warning_color`・`warning_color_js`・`load_warning_color`・`save_warning_color` |
| `src/projectapp/theme_dialog.py` | `open_color_dialog`(共通化)・`open_warning_color_dialog` |
| `src/projectapp/views.py` | `警告の色…` のメニュー・保存・復元 |
| `src/projectapp/gantt.py` | `WARNING_COLOR`・`WARNING_BACKGROUND`・`WARNING_CSS`、`task_row` の背景とホバー |
| `test/test_remaining.py`(新規)・`test/test_pace.py`(新規)・`test_timeline.py`・`test_theme.py`・`test_config.py`・`test_theme_dialog.py`・`test_views.py`・`test_gantt.py` | テスト |
| `CLAUDE.md`・`docs/work-log.md`・`docs/requests.md`・`docs/request-history.md` | 仕様と記録 |

---

### Task 1: 残りの工数の計算を `remaining.py` に移す

**Files:**
- Create: `src/projectapp/remaining.py`
- Create: `test/test_remaining.py`
- Modify: `src/projectapp/dashboard.py`(`_overlap_hours`・`_open_hours`・`_remaining_hours` を削除し、`remaining.py` から使う)

**Interfaces:**
- Produces:
  - `total_effort(task: Task) -> float`
  - `overlap_hours(project: Project, holidays: dict[date, str], day: date, start: datetime, end: datetime, work_days: Mapping[date, WorkDay] | None = None) -> float`
  - `open_hours(task: Task, project: Project, holidays: dict[date, str], now: datetime, limit: float) -> float`
  - `remaining_hours(task: Task, project: Project, holidays: dict[date, str], now: datetime) -> float`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_remaining.py`:

```python
from datetime import date, datetime

from projectapp.models import Actual, Assignee, Member, Project, Status, Task
from projectapp.remaining import overlap_hours, remaining_hours, total_effort

NOW = datetime(2026, 10, 7, 12)  # 水曜。稼働の枠は 9:00〜15:30


def project_of(*tasks: Task, members: list[Member] | None = None) -> Project:
    return Project("P", base_date=date(2026, 10, 5), members=members or [Member("田中", 1.0)], tasks=list(tasks))


def test_total_effort_is_the_task_effort() -> None:
    assert total_effort(Task("a", effort_hours=12.5)) == 12.5


def test_overlap_hours_is_the_part_of_the_window_inside_the_range() -> None:
    project = project_of()
    assert overlap_hours(project, {}, date(2026, 10, 7), datetime(2026, 10, 7, 12), datetime(2026, 10, 7, 18)) == 3.5
    assert overlap_hours(project, {}, date(2026, 10, 10), datetime(2026, 10, 10, 9), datetime(2026, 10, 10, 18)) == 0.0  # 土曜


def test_remaining_is_the_full_effort_without_progress_or_actuals() -> None:
    task = Task("a", planned_start=datetime(2026, 10, 6, 9), effort_hours=10)
    assert remaining_hours(task, project_of(task), {}, NOW) == 10


def test_remaining_takes_the_progress_off() -> None:
    task = Task("a", planned_start=datetime(2026, 10, 6, 9), effort_hours=10, status=Status.RUNNING, progress=40)
    assert remaining_hours(task, project_of(task), {}, NOW) == 6


def test_remaining_takes_the_finished_intervals_off_by_the_conversion_rate() -> None:
    worked = [Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 13))]  # 4h
    task = Task("a", effort_hours=10, status=Status.RUNNING, assignees=[Assignee("田中")], actuals=worked)
    assert remaining_hours(task, project_of(task), {}, NOW) == 6


def test_remaining_counts_an_open_interval_up_to_now_inside_the_window() -> None:
    open_run = [Actual(datetime(2026, 10, 7, 9), None)]  # 9:00 から 12:00 まで 3h
    task = Task("a", effort_hours=10, status=Status.RUNNING, actuals=open_run)
    assert remaining_hours(task, project_of(task), {}, NOW) == 7
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_remaining.py -q -n 0`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.remaining'`)

- [ ] **Step 3: `remaining.py` を作る**

`src/projectapp/remaining.py`:

```python
"""残りの工数の計算(要望 98・103)。ダッシュボードと警告の判定が共有する。NiceGUI に依存しない純粋関数。"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta

from projectapp.models import Project, Task, WorkDay
from projectapp.reassign import consumed_hours
from projectapp.timeline import combine_rate, conversion_rate, day_window


def total_effort(task: Task) -> float:
    """タスクの工数の合計[h]。残りの工数・警告の判定・ダッシュボードの按分は、工数をここから取る。
    後から追加工数を足せるようにする(要望 105)ときは、ここに追加分を足す。"""
    return task.effort_hours


def overlap_hours(
    project: Project,
    holidays: dict[date, str],
    day: date,
    start: datetime,
    end: datetime,
    work_days: Mapping[date, WorkDay] | None = None,
) -> float:
    """その日の稼働の枠のうち、[start, end) と重なる時間[h]。work_days があれば、その人の上書きを反映する。"""
    window = day_window(day, project.daily_hours, project.work_start, holidays, work_days)
    if window is None:
        return 0.0
    return max(0.0, (min(end, window[1]) - max(start, window[0])).total_seconds() / 3600)


def open_hours(task: Task, project: Project, holidays: dict[date, str], now: datetime, limit: float) -> float:
    """終了のない実績の区間が、今までに稼働の枠の中で積んだ時間[h]。`limit` に達したら数えるのをやめる。"""
    total = 0.0
    for interval in task.actuals:
        if interval.end is not None or interval.start >= now:
            continue
        day = interval.start.date()
        while day <= now.date():
            total += overlap_hours(project, holidays, day, interval.start, now)
            if total >= limit:
                return total
            day += timedelta(days=1)
    return total


def remaining_hours(task: Task, project: Project, holidays: dict[date, str], now: datetime) -> float:
    """残りの工数。工数から消化分を引く。消化分は、進捗度があれば工数 × 進捗度、
    なければ実績の区間 × 換算率(開いたままの区間は、今までに稼働の枠で積んだ時間)。
    状態は手入力なので、未着手でも進捗度か実績があれば引く(なければ全量)。"""
    effort = total_effort(task)
    rate = conversion_rate(task, project)
    done = consumed_hours(task, rate)
    if not task.progress:  # 進捗度があれば、そちらを優先する(None と 0 は進捗度なし)
        factor = combine_rate(rate, 1.0)
        extra = open_hours(task, project, holidays, now, effort / factor)
        done = min(done + extra * factor, effort)
    return effort - done
```

注意: `consumed_hours(task, rate)` は工数を超えない値を返す既存の規則のまま(`reassign.consumed_hours`)。移す前の `_remaining_hours` の本体をそのまま写したものなので、挙動は変わらない。

- [ ] **Step 4: `dashboard.py` を `remaining.py` につなぐ**

```bash
python3 - <<'EOF'
p = "src/projectapp/dashboard.py"
s = open(p, encoding="utf-8").read()

# 1. 移した関数の定義を消す
a = s.index("def _overlap_hours(")
b = s.index("def _counted_fraction(")
s = s[:a] + s[b:]
a = s.index("def _open_hours(")
b = s.index("def _remaining_shares(")
s = s[:a] + s[b:]

# 2. 呼び出しの名前を直す
s = s.replace("_overlap_hours(", "overlap_hours(").replace("_remaining_hours(", "remaining_hours(")

# 3. 工数は total_effort を通す(残りの工数・按分・必要人数の集計)
for old, new in (
    ("    done = task.effort_hours - rest", "    done = total_effort(task) - rest"),
    ("        hours *= task.effort_hours / total  # 工数に合わせる", "        hours *= total_effort(task) / total  # 工数に合わせる"),
    ("        if not (isfinite(task.effort_hours) and task.effort_hours > 0):", "        if not (isfinite(total_effort(task)) and total_effort(task) > 0):"),
    ("        due = max(0.0, rest - task.effort_hours * (1 - fraction))", "        due = max(0.0, rest - total_effort(task) * (1 - fraction))"),
):
    assert s.count(old) == 1, old
    s = s.replace(old, new)

# 4. import
old = "from projectapp.reassign import consumed_hours\n"
assert old in s
s = s.replace(old, "from projectapp.remaining import overlap_hours, remaining_hours, total_effort\n")
open(p, "w", encoding="utf-8").write(s)
EOF
grep -n "consumed_hours\|combine_rate\|conversion_rate\|day_window" src/projectapp/dashboard.py
```

`grep` の結果に、`import` の行だけで本体では使っていない名前(`consumed_hours`・`combine_rate`・`conversion_rate`・`day_window` のいずれか)があれば、その `import` から外す。

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest test/test_remaining.py test/test_dashboard_backlog.py test/test_dashboard.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS(既存のダッシュボードのテストは、移しただけなのでそのまま通る)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/remaining.py src/projectapp/dashboard.py test/test_remaining.py
git commit -m "refactor: 残りの工数の計算を remaining.py に移し、工数を total_effort から取る"
```

---

### Task 2: 完了予定までの稼働量 `timeline.work_capacity`

**Files:**
- Modify: `src/projectapp/timeline.py`(`consumed_slices` の後に `work_capacity` を足す)
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: `Worker`・`day_window`・`week_index`・`MAX_WORKDAYS`(同じファイル)
- Produces: `work_capacity(start: datetime, end: datetime, daily_hours: float, work_start: time, holidays: dict[date, str], crew: Sequence[Worker] | None = None, weeks: Sequence[Sequence[Worker]] | None = None, weeks_start: date | None = None) -> float`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py` の末尾に足す(`from projectapp.timeline import (...)` の中に `Worker`・`calc_end`・`work_capacity` があるか確認し、なければ足す):

```python
def test_work_capacity_counts_the_window_inside_the_range() -> None:
    from projectapp.timeline import work_capacity

    start, end = datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 15, 30)
    assert work_capacity(start, end, 6.5, time(9), {}) == 6.5
    assert work_capacity(datetime(2026, 10, 5, 12), end, 6.5, time(9), {}) == 3.5  # 枠の途中から


def test_work_capacity_skips_weekends_and_holidays() -> None:
    from projectapp.timeline import work_capacity

    fri, mon = datetime(2026, 10, 9, 9), datetime(2026, 10, 12, 15, 30)
    assert work_capacity(fri, mon, 6.5, time(9), {}) == 13.0  # 金と月。土日は枠がない
    holiday = {date(2026, 10, 12): "休み"}
    assert work_capacity(fri, mon, 6.5, time(9), holiday) == 6.5


def test_work_capacity_is_weighted_by_the_conversion_rate() -> None:
    from projectapp.timeline import Worker, work_capacity

    start, end = datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 15, 30)
    assert work_capacity(start, end, 6.5, time(9), {}, crew=[Worker(2.0)]) == 13.0
    assert work_capacity(start, end, 6.5, time(9), {}, crew=[Worker(1.0), Worker(0.5)]) == 9.75


def test_work_capacity_uses_each_workers_day_override() -> None:
    from projectapp.timeline import Worker, work_capacity

    day = date(2026, 10, 5)
    only_morning = Worker(1.0, work_day_map([WorkDay(day, time(9), time(12))]))
    start, end = datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 18)
    assert work_capacity(start, end, 6.5, time(9), {}, crew=[only_morning]) == 3.0  # 午前の 3h だけ
    assert work_capacity(start, end, 6.5, time(9), {}, crew=[only_morning, Worker(1.0)]) == 9.5  # 3h + 3h + 3.5h(重なりは合計)


def test_work_capacity_follows_the_weekly_crews_from_the_task_start() -> None:
    from projectapp.timeline import Worker, work_capacity

    weeks = [[Worker(1.0)], [Worker(2.0)]]  # 第 1 週は 1 人分、第 2 週は 2 倍
    start, end = datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 15, 30)  # タスクの開始(10/5)から 7 日後 = 第 2 週
    assert work_capacity(start, end, 6.5, time(9), {}, weeks=weeks, weeks_start=date(2026, 10, 5)) == 13.0
    assert work_capacity(start, end, 6.5, time(9), {}, weeks=weeks) == 6.5  # weeks_start がなければ start の日が第 1 週


def test_work_capacity_is_zero_for_an_empty_or_reversed_range() -> None:
    from projectapp.timeline import work_capacity

    moment = datetime(2026, 10, 5, 12)
    assert work_capacity(moment, moment, 6.5, time(9), {}) == 0.0
    assert work_capacity(moment, datetime(2026, 10, 5, 9), 6.5, time(9), {}) == 0.0


def test_work_capacity_matches_what_calc_end_consumes() -> None:
    from projectapp.timeline import Worker, calc_end, work_capacity

    start = datetime(2026, 10, 5, 9)
    crew = [Worker(1.5)]
    end = calc_end(start, 20.0, 6.5, time(9), {}, crew)
    assert end is not None
    assert work_capacity(start, end, 6.5, time(9), {}, crew=crew) == pytest.approx(20.0)
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_timeline.py -q -n 0 -k work_capacity`
Expected: FAIL(`ImportError: cannot import name 'work_capacity'`)

- [ ] **Step 3: 実装する**

`consumed_slices` の定義の直後(`def _consume(` の前)に足す:

```python
def work_capacity(
    start: datetime,
    end: datetime,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
    weeks_start: date | None = None,
) -> float:
    """[start, end) の間に、担当者の稼働の枠で積める、換算率つきの時間[h]。`calc_end` と同じ枠の扱いで、
    枠が重なる時刻は稼働中の担当者の換算率の合計で数える。crew が空なら換算率1の1人。
    weeks があれば、weeks_start(なければ start)の日から 7 日ごとにその週の担当者で数える(最後の週は以降も続く)。
    空の範囲・不正な稼働可能時間は 0。数える日数は MAX_WORKDAYS で打ち切る。"""
    if end <= start or not 0 < daily_hours <= 24:
        return 0.0
    crews = [list(week) or [Worker()] for week in weeks] if weeks else [list(crew) if crew else [Worker()]]
    origin = weeks_start or start.date()
    try:
        end = min(end, start + timedelta(days=MAX_WORKDAYS))
    except OverflowError:
        return 0.0
    total = 0.0
    day = start.date()
    while day <= end.date():
        workers = crews[week_index(origin, day, len(crews))]
        windows = [
            (w, window)
            for w in workers
            if (window := day_window(day, daily_hours, work_start, holidays, w.days)) is not None
        ]
        points = sorted({min(max(p, start), end) for _, window in windows for p in window})
        for left, right in zip(points, points[1:]):
            active = [w for w, (opens, closes) in windows if opens <= left and right <= closes]
            total += sum(w.rate for w in active) * (right - left).total_seconds() / 3600
        day += timedelta(days=1)
    return total
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest test/test_timeline.py -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "feat: 完了予定までの稼働量を数える work_capacity を足す"
```

---

### Task 3: 警告の判定 `pace.py`

**Files:**
- Create: `src/projectapp/pace.py`
- Create: `test/test_pace.py`

**Interfaces:**
- Consumes: `remaining.total_effort`・`remaining.remaining_hours`(Task 1)、`timeline.work_capacity`(Task 2)、`timeline.Schedule`・`effective_start`・`effective_end`・`is_overdue`・`crew_of`・`weekly_crews`
- Produces:
  - `WARNING_RATIO: float`(1.10)
  - `Pace(remaining: float, capacity: float)`(frozen dataclass)。`ratio: float`(稼働量が 0 以下なら `inf`)・`warning: bool`・`hint() -> str`
  - `pace(task, project, holidays, now, schedule=None) -> Pace | None`
  - `warning_pace(task, project, holidays, now, schedule=None) -> Pace | None`(警告のときだけ `Pace`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_pace.py`:

```python
from datetime import date, datetime

import pytest

from projectapp.models import Member, Project, Section, Status, Task, TaskKind
from projectapp.pace import WARNING_RATIO, Pace, pace, warning_pace

NOW = datetime(2026, 10, 7, 12)  # 水曜の昼。稼働の枠は 9:00〜15:30(残り 3.5h)
MON = datetime(2026, 10, 5, 9)


def project_of(*tasks: Task) -> Project:
    return Project("P", base_date=date(2026, 10, 5), members=[Member("田中", 1.0)], sections=[Section("s", list(tasks))])


def judged(task: Task, now: datetime = NOW) -> Pace | None:
    return pace(task, project_of(task), {}, now)


def test_the_warning_ratio_is_one_point_one() -> None:
    assert WARNING_RATIO == 1.10


def test_a_task_on_plan_is_not_a_warning() -> None:
    # 月曜 9:00 から 19.5h は水曜 15:30 まで。水曜の昼までに 16h 進めば、残り 3.5h は残りの稼働 3.5h にちょうど収まる
    task = Task("予定どおり", planned_start=MON, effort_hours=19.5, progress=82)
    value = judged(task)
    assert value is not None and value.ratio == pytest.approx(1.003, abs=0.001)
    assert not value.warning
    assert warning_pace(task, project_of(task), {}, NOW) is None


def test_a_task_behind_plan_is_a_warning() -> None:
    task = Task("遅れ気味", planned_start=MON, effort_hours=19.5, progress=50)
    value = warning_pace(task, project_of(task), {}, NOW)
    assert value is not None
    assert value.remaining == pytest.approx(9.75)
    assert value.capacity == pytest.approx(3.5)
    assert value.ratio == pytest.approx(2.786, abs=0.001)


def test_the_boundary_is_one_point_one() -> None:
    inside = Task("a", planned_start=MON, effort_hours=19.5, progress=81)  # 残り 3.705h → 約 106%
    over = Task("b", planned_start=MON, effort_hours=19.5, progress=80)  # 残り 3.9h → 約 111%
    assert not judged(inside).warning  # type: ignore[union-attr]
    assert judged(over).warning  # type: ignore[union-attr]


def test_a_manual_end_with_room_is_not_a_warning_until_the_room_is_used() -> None:
    task = Task("余裕あり", planned_start=MON, effort_hours=19.5, progress=50, planned_end=datetime(2026, 10, 9, 15, 30), planned_end_manual=True)
    value = judged(task)
    assert value is not None and not value.warning  # 残り 9.75h に対し、水曜の昼から金曜まで 16.5h


def test_a_plan_too_short_for_the_effort_warns_before_the_start() -> None:
    task = Task("足りない計画", planned_start=MON, effort_hours=40, planned_end=datetime(2026, 10, 6, 15, 30), planned_end_manual=True)
    value = judged(task, now=datetime(2026, 10, 5, 8))  # 開始前。稼働量は月・火の 13h
    assert value is not None and value.warning and value.ratio == pytest.approx(40 / 13)


def test_a_task_not_started_after_its_start_is_a_warning() -> None:
    task = Task("着手が遅れた", planned_start=MON, effort_hours=19.5)  # 進捗度・実績なし
    assert warning_pace(task, project_of(task), {}, NOW) is not None


def test_a_task_before_its_start_follows_the_plan() -> None:
    task = Task("まだ先", planned_start=datetime(2026, 10, 8, 9), effort_hours=6.5)
    value = judged(task)
    assert value is not None and value.ratio == pytest.approx(1.0) and not value.warning


def test_no_capacity_with_work_left_is_a_warning() -> None:
    task = Task("枠がない", planned_start=datetime(2026, 10, 9, 15, 30), effort_hours=1, planned_end=datetime(2026, 10, 10, 10), planned_end_manual=True)
    value = judged(task, now=datetime(2026, 10, 9, 16))  # 金曜の終業後から土曜の朝まで。枠がない
    assert value is not None and value.capacity == 0 and value.ratio == float("inf") and value.warning


def test_overdue_tasks_are_left_to_the_red_row() -> None:
    late_end = Task("完了予定を過ぎた", planned_start=MON, effort_hours=6.5)  # 月曜 15:30 に終わる予定
    late_deadline = Task("締切を過ぎた", planned_start=NOW, effort_hours=6.5, deadline=datetime(2026, 10, 7, 10))
    assert judged(late_end) is None
    assert judged(late_deadline) is None


@pytest.mark.parametrize(
    "task",
    [
        Task("終了", planned_start=MON, effort_hours=19.5, status=Status.DONE),
        Task("工数なし", planned_start=MON, planned_end=datetime(2026, 10, 9, 15, 30)),
        Task("日程なし", effort_hours=10),
        Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17)),
        Task("残りなし", planned_start=MON, effort_hours=19.5, progress=100),
    ],
)
def test_tasks_that_cannot_be_judged_give_none(task: Task) -> None:
    assert judged(task) is None


def test_the_hint_names_the_numbers() -> None:
    assert Pace(9.75, 3.5).hint() == "警告: 残り 9.8h / 稼働 3.5h(279%)"
    assert Pace(1.0, 0.0).hint() == "警告: 残り 1.0h / 稼働 0.0h"
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_pace.py -q -n 0`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.pace'`)

- [ ] **Step 3: 実装する**

`src/projectapp/pace.py`:

```python
"""警告の判定(要望 103)。残りの工数が、完了予定までの稼働量に収まるかを見る。NiceGUI に依存しない純粋関数。

予定どおりに進んでいれば、残りの工数と稼働量は同じ(比 100%)になる。比が WARNING_RATIO を超えると、
このペースでは完了予定を超える見込みなので警告にする。予定超過(`is_overdue`)になったタスクは、赤い行に任せる。"""

from dataclasses import dataclass
from datetime import date, datetime
from math import inf, isfinite

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import (
    Schedule,
    crew_of,
    effective_end,
    effective_start,
    is_overdue,
    weekly_crews,
    work_capacity,
)

WARNING_RATIO = 1.10  # 残りの工数 ÷ 稼働量 がこれ以上で警告(固定)
_EPSILON = 1e-9  # 比の比較の許容差(浮動小数の丸め)


@dataclass(frozen=True)
class Pace:
    remaining: float  # 残りの工数[h]
    capacity: float  # 今から完了予定までに積める稼働量[h](換算率つき)

    @property
    def ratio(self) -> float:
        """残りの工数 ÷ 稼働量。稼働量がないときは inf。"""
        return inf if self.capacity <= 0 else self.remaining / self.capacity

    @property
    def warning(self) -> bool:
        return self.ratio >= WARNING_RATIO - _EPSILON

    def hint(self) -> str:
        """ホバーの文字。稼働量がないときは、割合を出さない。"""
        head = f"警告: 残り {self.remaining:.1f}h / 稼働 {self.capacity:.1f}h"
        return head if self.capacity <= 0 else f"{head}({self.ratio * 100:.0f}%)"


def pace(
    task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule | None = None
) -> Pace | None:
    """タスクの残りの工数と稼働量。判定できないとき(通常タスクでない・終了・工数なし・日程なし・
    完了予定を過ぎた・予定超過・残りなし)は None。"""
    if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
        return None
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return None
    schedule = schedule or Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    end = effective_end(task, project, holidays, schedule)
    if start is None or end is None or end <= now:
        return None
    if is_overdue(task, project, holidays, now, schedule):
        return None
    rest = remaining_hours(task, project, holidays, now)
    if not rest > 0:
        return None
    weeks = weekly_crews(task, project)
    capacity = work_capacity(
        max(now, start),
        end,
        project.daily_hours,
        project.work_start,
        holidays,
        crew=crew_of(task.assignees, project.members, project.parameters, task.parameters, project.ratio_limits),
        weeks=weeks or None,
        weeks_start=start.date(),
    )
    return Pace(rest, capacity)


def warning_pace(
    task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule | None = None
) -> Pace | None:
    """警告のときだけ Pace を返す(行の背景とホバーに使う)。"""
    value = pace(task, project, holidays, now, schedule)
    return value if value is not None and value.warning else None
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest test/test_pace.py -q -n 0`
Expected: すべて PASS

もし `test_the_boundary_is_one_point_one` の境界が合わないときは、`remaining` と `capacity` の実測値を `print` して、進捗度(80・81)と期待する比を計算し直してから、テストの数字を直す(計算: 工数 19.5h で進捗度 p% のとき、残り = 19.5 × (100 − p)/100、稼働量 = 3.5h)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/pace.py test/test_pace.py
git commit -m "feat: 残りの工数と稼働量の比で警告を判定する pace を足す"
```

---

### Task 4: 警告の色の読み込み・保存(`theme.py`・`config.py`)

**Files:**
- Modify: `src/projectapp/theme.py`(`today_color_js` の後)
- Modify: `src/projectapp/config.py`(`save_today_color` の後)
- Test: `test/test_theme.py`・`test/test_config.py`

**Interfaces:**
- Produces:
  - `parse_warning_color(value: object) -> str | None`
  - `warning_color_js(color: str | None) -> str`
  - `load_warning_color(base_dir: Path = BASE_DIR) -> str | None`
  - `save_warning_color(color: str | None, base_dir: Path = BASE_DIR) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_theme.py` の末尾に:

```python
def test_parse_warning_color_reads_a_valid_color_and_lowercases() -> None:
    from projectapp.theme import parse_warning_color

    assert parse_warning_color("#FDD835") == "#fdd835"


@pytest.mark.parametrize("value", [None, "", "yellow", "#12345", "#gggggg", 5, [], {}])
def test_parse_warning_color_reads_anything_else_as_unset(value: object) -> None:
    from projectapp.theme import parse_warning_color

    assert parse_warning_color(value) is None


def test_warning_color_js_sets_and_removes_the_variable() -> None:
    from projectapp.theme import warning_color_js

    assert warning_color_js("#fdd835") == 'document.body.style.setProperty("--warning", "#fdd835")'
    assert warning_color_js(None) == 'document.body.style.removeProperty("--warning")'
```

`test/test_config.py` の末尾に:

```python
def test_the_warning_color_defaults_to_none(tmp_path: Path) -> None:
    from projectapp.config import load_warning_color

    assert load_warning_color(tmp_path) is None


def test_the_warning_color_round_trips_and_keeps_other_keys(tmp_path: Path) -> None:
    from projectapp.config import load_today_color, load_warning_color, save_today_color, save_warning_color

    save_today_color("#1e88e5", tmp_path)
    save_warning_color("#fdd835", tmp_path)
    assert load_warning_color(tmp_path) == "#fdd835"
    assert load_today_color(tmp_path) == "#1e88e5"
    save_warning_color(None, tmp_path)  # 既定に戻す
    assert load_warning_color(tmp_path) is None
    assert load_today_color(tmp_path) == "#1e88e5"


@pytest.mark.parametrize("value", ["yellow", "#12345", 5, [], {}])
def test_an_invalid_warning_color_is_read_as_none(tmp_path: Path, value: object) -> None:
    from projectapp.config import load_warning_color

    (tmp_path / "config.json").write_text(json.dumps({"warning_color": value}), encoding="utf-8")
    assert load_warning_color(tmp_path) is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_theme.py test/test_config.py -q -n 0 -k warning`
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 実装する**

`src/projectapp/theme.py` の `today_color_js` の後に:

```python
def parse_warning_color(value: object) -> str | None:
    """`config.json`の`warning_color`の読み込み。`#RRGGBB`以外は未設定(既定の色)。"""
    return normalize_hex(value)


def warning_color_js(color: str | None) -> str:
    """警告の色(`--warning`)を`body`に設定する JS。None は外して、既定の色へ戻す。"""
    if color is None:
        return 'document.body.style.removeProperty("--warning")'
    return f"document.body.style.setProperty(\"--warning\", {json.dumps(color)})"
```

`src/projectapp/config.py`: 先頭の import `from projectapp.theme import CustomTheme, custom_theme_to_dict, parse_custom_theme, parse_today_color` に `parse_warning_color` を足し、`save_today_color` の後に:

```python
def load_warning_color(base_dir: Path = BASE_DIR) -> str | None:
    """警告の色(`#rrggbb`)。未設定・不正は None(既定の色)。"""
    return parse_warning_color(read_config(base_dir).get("warning_color"))


def save_warning_color(color: str | None, base_dir: Path = BASE_DIR) -> None:
    """None は既定に戻す(キーを消す代わりに null を書く)。"""
    update_config({"warning_color": color}, base_dir)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest test/test_theme.py test/test_config.py -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/theme.py src/projectapp/config.py test/test_theme.py test/test_config.py
git commit -m "feat: 警告の色(warning_color)の読み込みと保存を足す"
```

---

### Task 5: 色のダイアログの共通化と `警告の色…`(`theme_dialog.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/theme_dialog.py`(`open_today_color_dialog` を `open_color_dialog` に共通化し、`open_warning_color_dialog` を足す)
- Modify: `src/projectapp/views.py`(import・ラベル・状態・メニュー・保存・復元)
- Modify: `src/projectapp/gantt.py`(`WARNING_COLOR`・`WARNING_BACKGROUND`・`WARNING_CSS` の定義と `ui.add_css(WARNING_CSS)`。行の描画は Task 6)
- Test: `test/test_theme_dialog.py`・`test/test_views.py`

**Interfaces:**
- Consumes: `load_warning_color`・`save_warning_color`・`warning_color_js`(Task 4)
- Produces:
  - `theme_dialog.open_color_dialog(title: str, hint: str, prefix: str, initial: str | None, on_preview, on_apply, on_cancel) -> None`(マーク: `{prefix}-color`・`{prefix}-reset`・`{prefix}-cancel`・`{prefix}-apply`)
  - `theme_dialog.open_warning_color_dialog(initial, on_preview, on_apply, on_cancel)`(マークの接頭辞は `warning`)
  - `MainView.warning_color: str | None`・`MainView.open_warning_color_dialog()`・`MainView.apply_warning_color(color) -> bool`
  - `gantt.WARNING_COLOR = "#fdd835"`・`gantt.WARNING_BACKGROUND`・`gantt.WARNING_CSS`
  - メニューの項目 `警告の色…`(マーク `theme-warning-color`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `test_today_color_apply_failure_notifies_and_keeps_saved_state` の後に足す(先頭の import `from projectapp.config import load_custom_theme, load_theme, load_today_color, save_custom_theme, save_today_color` に `load_warning_color`・`save_warning_color` を足す):

```python
async def test_warning_color_dialog_apply_saves_the_color_without_touching_the_theme(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    assert view.warning_color is None
    user.find(marker="theme-warning-color").click()
    user.find(marker="warning-color").elements.pop().set_value("#FDD835")
    user.find(marker="warning-apply").click()
    assert view.warning_color == "#fdd835"
    assert load_warning_color(tmp_path) == "#fdd835"
    assert view.theme == "auto" and load_theme(tmp_path) == "auto"  # テーマは変えない
    assert load_today_color(tmp_path) is None  # 今日の線の色も変えない


async def test_warning_color_dialog_cancel_keeps_the_saved_color(user: User, tmp_path: Path) -> None:
    save_warning_color("#fdd835", tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    assert view.warning_color == "#fdd835"
    user.find(marker="theme-warning-color").click()
    user.find(marker="warning-color").elements.pop().set_value("#e53935")
    user.find(marker="warning-cancel").click()
    assert view.warning_color == "#fdd835" and load_warning_color(tmp_path) == "#fdd835"


async def test_warning_color_dialog_reset_then_apply_returns_to_the_default(user: User, tmp_path: Path) -> None:
    save_warning_color("#fdd835", tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="theme-warning-color").click()
    user.find(marker="warning-reset").click()
    user.find(marker="warning-apply").click()
    assert view.warning_color is None and load_warning_color(tmp_path) is None


async def test_warning_color_apply_failure_notifies_and_keeps_saved_state(user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.save_warning_color", fail)
    user.find(marker="theme-warning-color").click()
    user.find(marker="warning-color").elements.pop().set_value("#fdd835")
    user.find(marker="warning-apply").click()
    await user.should_see("警告の色を保存できませんでした")
    assert view.warning_color is None
    await user.should_see(marker="warning-apply")  # ダイアログは開いたまま
```

既存のテーマのメニューの項目を確かめるテスト(`test/test_views.py` の `menu_items(user, "menu-theme-items") == [...]`、3304 行付近)に `("警告の色…", "theme-warning-color")` を、`("今日の線の色…", "theme-today-color")` の後に足す。

`test/test_gantt.py` に、定義のテストを足す:

```python
def test_the_warning_css_defines_the_default_color_and_a_tint_that_follows_it() -> None:
    from projectapp.gantt import WARNING_BACKGROUND, WARNING_COLOR, WARNING_CSS

    assert WARNING_COLOR == "#fdd835"
    assert f"--warning: {WARNING_COLOR}" in WARNING_CSS
    assert "var(--warning)" in WARNING_BACKGROUND
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py test/test_gantt.py -q -n 0 -k "warning"`
Expected: FAIL

- [ ] **Step 3: `theme_dialog.py` を共通化する**

`open_today_color_dialog` を、次の 3 つの関数に置き換える(中身は元のコードのマーク名だけを `prefix` にしたもの):

```python
def open_color_dialog(
    title: str,
    hint: str,
    prefix: str,
    initial: str | None,
    on_preview: Callable[[str | None], object],
    on_apply: Callable[[str | None], bool],
    on_cancel: Callable[[], object],
) -> None:
    """1 色を入れる小さなダイアログ。空欄は既定の色(None)。色を変えるたびに`on_preview`を呼ぶ。
    `適用`は`on_apply`が真のときだけ閉じる。適用せずに閉じたら`on_cancel`。
    マークは`{prefix}-color`(入力欄)・`{prefix}-reset`・`{prefix}-cancel`・`{prefix}-apply`。"""
    applied = False
    current = initial

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[24rem] max-w-full"):
        ui.label(title).classes("text-h6")

        def edit(value: str | None) -> None:
            nonlocal current
            text = (value or "").strip()
            color = normalize_hex(text)
            valid = color is not None or not text
            apply_button.set_enabled(valid)
            if valid:
                current = color
                on_preview(color)

        field = color_field("色", initial or "", edit, f"{prefix}-color", allow_empty=True)
        ui.label(hint).classes("text-caption text-grey")

        def apply() -> None:
            nonlocal applied
            if on_apply(current):
                applied = True
                dialog.close()

        with ui.row().classes("w-full justify-between"):
            ui.button("既定に戻す", on_click=lambda: field.set_value("")).props("flat no-caps").mark(f"{prefix}-reset")
            with ui.row():
                ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark(f"{prefix}-cancel")
                apply_button = ui.button("適用", on_click=apply).props("no-caps").mark(f"{prefix}-apply")
        dialog.on_value_change(lambda e: None if e.value or applied else on_cancel())
    dialog.open()


def open_today_color_dialog(
    initial: str | None,
    on_preview: Callable[[str | None], object],
    on_apply: Callable[[str | None], bool],
    on_cancel: Callable[[], object],
) -> None:
    """今日の線の色のダイアログ。"""
    open_color_dialog(
        "今日の線の色",
        "空欄は既定の色(ライトは赤、ダークは明るい赤)です",
        "today",
        initial,
        on_preview,
        on_apply,
        on_cancel,
    )


def open_warning_color_dialog(
    initial: str | None,
    on_preview: Callable[[str | None], object],
    on_apply: Callable[[str | None], bool],
    on_cancel: Callable[[], object],
) -> None:
    """警告の色のダイアログ(要望 103)。"""
    open_color_dialog(
        "警告の色",
        "空欄は既定の色(黄)です。警告のタスクの行と名前の欄の背景に、薄く重ねます",
        "warning",
        initial,
        on_preview,
        on_apply,
        on_cancel,
    )
```

既存の今日の線の色のダイアログのテスト(`test_theme_dialog.py`・`test_views.py` の `today-*`)が、そのまま通ることを確認する。

- [ ] **Step 4: `gantt.py` に定義を足す**

`TODAY_CSS = ...` の行の後に:

```python
WARNING_COLOR = "#fdd835"  # 警告のタスクの行・名前の欄の背景(薄く重ねる)。設定で変えられる(--warning)
WARNING_BACKGROUND = "color-mix(in srgb, var(--warning) 22%, transparent)"
WARNING_CSS = f":root {{ --warning: {WARNING_COLOR}; }}"
```

`ui.add_css(TODAY_CSS)` の次の行に `ui.add_css(WARNING_CSS)` を足す。

- [ ] **Step 5: `views.py` をつなぐ**

1. `from projectapp.theme import BODY_CSS, CustomTheme, theme_js, today_color_js` に `warning_color_js` を足す。
2. `from projectapp.theme_dialog import open_today_color_dialog as show_today_color_dialog` の次に `from projectapp.theme_dialog import open_warning_color_dialog as show_warning_color_dialog`。
3. `load_today_color`・`save_today_color` の import に、`load_warning_color`・`save_warning_color` を足す(同じ `from projectapp.config import (...)` の中)。
4. `TODAY_COLOR_LABEL = "今日の線の色…"` の次に `WARNING_COLOR_LABEL = "警告の色…"`。
5. `self.today_color = load_today_color(base_dir)` の次の行に `self.warning_color = load_warning_color(base_dir)  # 警告の色。None は既定(黄)`。
6. `apply_today_color` の後に:

```python
    def open_warning_color_dialog(self) -> None:
        """警告の色のダイアログ。色を変えると画面に反映し(プレビュー)、キャンセルで保存済みの色に戻す。"""
        show_warning_color_dialog(
            self.warning_color,
            lambda color: self.run_js(warning_color_js(color)),
            self.apply_warning_color,
            lambda: self.run_js(warning_color_js(self.warning_color)),
        )

    def apply_warning_color(self, color: str | None) -> bool:
        """警告の色を保存する。失敗したら通知して False(保存済みの色は変えない)。"""
        try:
            save_warning_color(color, self.base_dir)
        except OSError:
            ui.notify("警告の色を保存できませんでした", type="warning")
            return False
        self.warning_color = color
        self.run_js(warning_color_js(color))
        return True
```

7. 画面を組み立てる箇所の `if self.today_color is not None: self.run_js(today_color_js(self.today_color))` の次に:

```python
        if self.warning_color is not None:
            self.run_js(warning_color_js(self.warning_color))
```

8. テーマのメニューの `self.menu_entry(TODAY_COLOR_LABEL, ...)` の次の行に:

```python
                self.menu_entry(WARNING_COLOR_LABEL, "warning_amber", self.open_warning_color_dialog, "theme-warning-color")
```

- [ ] **Step 6: テストが通ることを確認する**

Run: `uv run pytest test/test_views.py test/test_gantt.py test/test_theme_dialog.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/theme_dialog.py src/projectapp/views.py src/projectapp/gantt.py test/test_views.py test/test_gantt.py test/test_theme_dialog.py
git commit -m "feat: 警告の色を設定するダイアログ(警告の色…)を足す"
```

---

### Task 6: ガントチャートの行と名前の欄に警告を出す

**Files:**
- Modify: `src/projectapp/gantt.py`(`task_row`)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `pace.warning_pace`(Task 3)、`WARNING_BACKGROUND`(Task 5)、`Pace.hint()`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の `test_done_task_is_not_red` の後に足す:

```python
WARN_NOW = datetime(2026, 10, 7, 12)  # 水曜の昼


def warning_project() -> Project:
    behind = Task("遅れ気味", planned_start=datetime(2026, 10, 5, 9), effort_hours=19.5, progress=50)
    on_plan = Task("予定どおり", planned_start=datetime(2026, 10, 5, 9), effort_hours=19.5, progress=82)
    return Project("demo", base_date=BASE, sections=[Section("開発", [behind, on_plan])])


def name_cell_image(user: User, marker: str) -> str | None:
    return user.find(marker=marker).elements.pop()._style.get("background-image")


async def test_a_warning_task_row_and_name_cell_get_the_warning_tint(user: User) -> None:
    from projectapp.gantt import WARNING_BACKGROUND

    mount(warning_project(), now=WARN_NOW)
    await user.open("/")
    assert row_background(user, "task-0-0") == WARNING_BACKGROUND
    assert name_cell_image(user, "task-0-0") == f"linear-gradient({WARNING_BACKGROUND}, {WARNING_BACKGROUND})"
    assert row_background(user, "task-0-1") is None  # 予定どおりのタスクは出さない
    assert name_cell_image(user, "task-0-1") is None


async def test_the_warning_name_has_a_tooltip_with_the_numbers(user: User) -> None:
    mount(warning_project(), now=WARN_NOW)
    await user.open("/")
    name = user.find(marker="task-name-0-0").elements.pop()
    tooltips = [c for c in name.default_slot.children if isinstance(c, ui.tooltip)]
    assert [t.text for t in tooltips] == ["警告: 残り 9.8h / 稼働 3.5h(279%)"]
    other = user.find(marker="task-name-0-1").elements.pop()
    assert not [c for c in other.default_slot.children if isinstance(c, ui.tooltip)]


async def test_an_overdue_task_stays_red_and_gets_no_warning(user: User) -> None:
    mount(warning_project(), now=datetime(2026, 10, 8))  # 完了予定(10/7 15:30)を過ぎた
    await user.open("/")
    assert row_background(user, "task-0-0") == OVERDUE_COLOR


async def test_a_done_task_gets_no_warning(user: User) -> None:
    project = warning_project()
    project.sections[0].tasks[0].status = Status.DONE
    mount(project, now=WARN_NOW)
    await user.open("/")
    assert row_background(user, "task-0-0") is None


async def test_show_alerts_false_hides_the_warning_tint(user: User) -> None:
    mount_with(warning_project(), ViewOptions(show_alerts=False), now=WARN_NOW)
    await user.open("/")
    assert row_background(user, "task-0-0") is None
    assert name_cell_image(user, "task-0-0") is None


async def test_the_warning_tint_keeps_the_bar_color(user: User) -> None:
    mount(warning_project(), now=WARN_NOW)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["background"] == planned_background(STATUS_COLOR_VAR)  # 棒は状態色のまま
```

`STATUS_COLOR_VAR`・`planned_background`・`mount_with`・`ViewOptions`・`OVERDUE_COLOR`・`Status`・`Section` は `test_gantt.py` に既にある(なければ同じ import に足す)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -n 0 -k "warning"`
Expected: FAIL(`row_background` が `None`)

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py`:

1. import に `from projectapp.pace import warning_pace` を足す。
2. `task_row` の `overdue = is_overdue(...) and self.options.show_alerts` の次に:

```python
        warning = None
        if self.options.show_alerts and not overdue:  # 予定超過(赤)を優先する
            warning = warning_pace(task, self.project, self.holidays, now, self.schedule)
```

3. `if overdue: style += f"; background: {OVERDUE_COLOR}"` を:

```python
        if overdue:
            style += f"; background: {OVERDUE_COLOR}"
        elif warning is not None:
            style += f"; background: {WARNING_BACKGROUND}"
```

4. 名前の欄の `if overdue:  # 不透明な背景の上に、行と同じ赤みを重ねる` のブロックの直後に:

```python
            elif warning is not None:  # 警告の色も、同じ場所に重ねる
                cell_style += f"; background-image: linear-gradient({WARNING_BACKGROUND}, {WARNING_BACKGROUND})"
```

(`if overdue:` の次に `elif` が来る位置にする。`if overdue: ... cell_style += (...)` の閉じ括弧の直後。)

5. 名前の `name = ui.label(...)` を作った後(`if finished:` の前)に:

```python
                if warning is not None:
                    name.tooltip(warning.hint())
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest test/test_gantt.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: 見た目を確かめる(目視)**

`~/.projectapp/` に、警告が出るデータが要る。確認用データ `docs/samples/警告の確認.json` を、次で作る:

```bash
uv run python - <<'EOF'
from datetime import date, datetime
from pathlib import Path
from projectapp.models import Assignee, Member, Project, Section, Status, Task
from projectapp.storage import dumps_project

mon = datetime(2026, 10, 26, 9)
tasks = [
    Task("警告: 進捗が遅れている", planned_start=mon, effort_hours=26, progress=40, assignees=[Assignee("田中")]),
    Task("警告: 着手が遅れている", planned_start=mon, effort_hours=19.5, assignees=[Assignee("鈴木")]),
    Task("予定どおり", planned_start=mon, effort_hours=26, progress=60, assignees=[Assignee("田中")]),
    Task("余裕あり(完了予定を手で指定)", planned_start=mon, effort_hours=13, progress=20, planned_end=datetime(2026, 11, 20, 15, 30), planned_end_manual=True),
    Task("予定超過(赤)", planned_start=datetime(2026, 10, 20, 9), effort_hours=6.5),
    Task("終了", planned_start=mon, effort_hours=6.5, status=Status.DONE),
]
project = Project("警告の確認", base_date=date(2026, 10, 26), members=[Member("田中", 1.0), Member("鈴木", 1.0)], sections=[Section("確認", tasks)])
Path("docs/samples/警告の確認.json").write_text(dumps_project(project), encoding="utf-8")
EOF
```

「警告: …」の 2 件が、黄色の薄い背景(行と名前の欄)になり、ホバーに数字が出ること、赤い行・予定どおり・余裕あり・終了にはつかないこと、`警告の色…` で色を変えるとすぐ反映されることを、実機(`uv run projectapp`。今日の日付で判定が変わるので、`警告の確認.json` の日付が古ければ、日付を今週に直す)で確かめる。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py docs/samples/警告の確認.json
git commit -m "feat: 警告のタスクの行と名前の欄に警告の色を出す"
```

---

### Task 7: 仕様と記録を更新する

**Files:**
- Modify: `CLAUDE.md`・`docs/work-log.md`・`docs/requests.md`・`docs/request-history.md`
- Modify: `docs/superpowers/specs/2026-10-31-warning-status-design.md`(状態の行を「実装済み(段階 1)」に)

- [ ] **Step 1: `CLAUDE.md` に仕様を足す**

`## ガントチャート` の、`締切または完了予定を過ぎた、終了していないタスクは、...` の項目の次に足す:

```markdown
- 完了予定を過ぎる見込みのタスクは、`警告`として、予定超過(赤)とは別の色で出す(要望 103)。判定は`残りの工数 ÷ 今から完了予定までの稼働量`(基準の人の時間。稼働量は、担当者の稼働日の上書き・祝日・イベントの休み・週ごとの担当を反映した換算率つきの時間)が 110% 以上(固定。予定どおりなら比は 100%)。対象は、通常タスクで、終了でなく、工数があり、完了予定が今より先で、予定超過でなく、残りの工数があるもの(稼働量が 0 で残りがあるときも警告)。完了予定を手で指定して余裕があるタスクは、余裕を使い切るまで警告にならない。行の背景と名前の欄の背景に、警告の色(既定は黄`#fdd835`)を薄く重ね(棒は状態色のまま)、名前のホバーに`警告: 残り 12.0h / 稼働 10.0h(120%)`を出す。予定超過の赤みと同じ表示項目に従い、プレビュー・画像にも出す(PlantUML には出さない)。警告の色は、テーマのメニューの`警告の色…`で入力する(`#RRGGBB`。空欄は既定。`~/.projectapp/config.json`の`warning_color`。全プロジェクト共通。元に戻す・やり直しの対象にしない)。ダッシュボードへの表示と、メンバーごとの件数の閾値は、続く段階で足す
```

- [ ] **Step 2: ほかの文書を更新する**

- `docs/requests.md` の要望 103 の状態の行を、`> **状態**: 段階 1(判定・ガントチャート・警告の色)を実装済み(PR 作成中)。設計書 [...](...)、計画 [...](...)。残りは段階 2(ダッシュボード・メンバーの閾値)・段階 3(要望 98 のボタン)。` の形に直す(設計書・計画へのリンクは相対パスで)。
- `docs/request-history.md` の要望 103 の行の状態を `段階 1 実装済み(PR 作成中)` に、設計書 / 実装計画の列に両方のリンクを入れる。
- `docs/work-log.md` の末尾に、要望 103 の段階 1 の記録(判定を 110% にした理由〔80% では予定どおりが全部警告になる〕・`remaining.py` への移動・`work_capacity`・`pace.py`・警告の色・確認用データ・テスト件数)を足す。
- 設計書の状態の行を `> **状態**: 設計(2026-10-31 に承認済み)。段階 1 は実装済み(計画 [...](../plans/2026-10-31-warning-stage1.md))。要望 103。` に直す。

- [ ] **Step 3: 全体の確認**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS。`ty` の診断は変更前と同じ 1 件。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs
git commit -m "docs: 要望 103 の段階 1 の仕様と記録を更新する"
```

---

## Self-Review

**Spec coverage**(設計書の段階 1 の範囲):
- 判定(110%・対象と除外・計算・追加工数への備え)→ Task 1(`total_effort`)・2(`work_capacity`)・3(`pace`)
- 残りの工数の計算の移動 → Task 1
- ガントチャートの行と名前の欄・ホバー・予定超過との優先・表示項目 → Task 6。プレビュー・画像は、同じ `task_row` と `show_alerts` を通るので Task 6 に含まれる(`test_show_alerts_false_hides_the_warning_tint`)
- 警告の色の設定・保存・既定 → Task 4・5
- PlantUML に出さない → 変更しない(何もしない)
- 段階 2(ダッシュボード・メンバーの閾値・version 19)・段階 3(98 のボタン)→ この計画の範囲外。段階 1 のあとに計画を書く。

**Placeholder scan**: 「TBD」「あとで」はなし。Task 7 の文書の更新は、書く内容を指定している(日付・PR 番号は実行時に入る)。

**Type consistency**: `Pace(remaining, capacity)`・`ratio`・`warning`・`hint()` は Task 3 で定義し、Task 6 は `warning_pace(...).hint()` だけを使う。`work_capacity` の引数名(`crew`・`weeks`・`weeks_start`)は Task 2 と Task 3 で一致。`WARNING_BACKGROUND` は Task 5 で定義して Task 6 が使う。`open_color_dialog` のマークの接頭辞(`warning`)は Task 5 のテストと一致。

**Review Focus**: 上の「Review Focus」の 5 項目は、`test_a_task_on_plan_is_not_a_warning`・`test_the_boundary_is_one_point_one`(1)、`test_a_manual_end_with_room_is_not_a_warning_until_the_room_is_used`・`test_a_plan_too_short_for_the_effort_warns_before_the_start`(2)、`test_an_overdue_task_stays_red_and_gets_no_warning`・`test_show_alerts_false_hides_the_warning_tint`(3)、`test_work_capacity_*` と `test_work_capacity_matches_what_calc_end_consumes`(4)、`test_warning_color_*`(5)で押さえている。
