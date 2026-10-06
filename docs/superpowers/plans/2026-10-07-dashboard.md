# ダッシュボード 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メイン画面に、進捗と遅れ・人ごとの負荷・工数の予定と実績・期限とマイルストーンの 4 つの柱を出すダッシュボード(期間は `今週`・`今月`・`全期間`)を足す(要望 6)。実機確認用のテストデータも 2 種類作る。

**Architecture:** 集計は NiceGUI に依存しない純粋関数(`dashboard.py`)。表示は `dashboard_view.py`(カードと横棒)。`views.py` は、ボタン・ESC・出入り・現在時刻と祝日の受け渡しだけを持つ。ガントチャートは作り直さず、`GanttChart.set_visible` で隠す・出すだけにする(隠すとスクロール位置が失われるので、JS で覚えて戻す)。保存データは増やさない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-07-dashboard-design.md`

## Global Constraints

- Python 3.13 以上。NiceGUI。画面の文言は日本語。
- 描画は NiceGUI の要素と CSS(外部のチャートライブラリは使わない)。
- 保存データ・ファイル形式は変えない。期間・表示は保存しない。ダッシュボードは読み取り専用で、プロジェクトを変更扱いにしない(`is_dirty()` を変えない)。
- 負荷は、既存の割り当て超過と同じ前提(`timeline.counted_span`。終了したタスクは数えない)。工数の予定は、終了したタスクも数える。
- 集計は、現在時刻を引数で受け取る(`now`)。テストで固定できること。
- テストは、実際のホーム(`~/.projectapp`)を読み書きしない(`tmp_path` を使う)。
- 検証: `uv run pytest -n auto -q` と `uvx ty check src`(どちらもサンドボックスの外で動かす必要がある)。

## Review Focus

- 稼働日が 0 日の期間(土日だけ・祝日だけ)で、割り算せず 0 になる(Task 3)。
- 終了したタスクは、負荷には数えず、工数の予定には数える(Task 3)。
- 実行中(`end` なし)の実績は `now` まで数え、期間をまたぐ区間は期間内の分だけ数える(Task 3)。
- ガントチャートを隠して戻したあと、絞り込み・スケール・スクロール位置が保たれる。スクロール位置は、ネイティブでの実機確認で見る(Task 4・6)。
- 期間のトグルを、画面を開き直すときに書き換えても、変更の通知が再帰しない(Task 5)。

---

## ファイル構成

| ファイル | 変更 |
|---|---|
| `src/projectapp/timeline.py` | `_counted_span` → `counted_span`(公開) |
| `src/projectapp/dashboard.py` | 新規。期間・4 つの集計・`summarize`(NiceGUI に依存しない) |
| `src/projectapp/gantt.py` | `set_visible`、`scroll_box`、`HIDE_CHART_JS`・`SHOW_CHART_JS` |
| `src/projectapp/dashboard_view.py` | 新規。`DashboardView`(カードと横棒) |
| `src/projectapp/views.py` | ボタン、`open_dashboard` / `close_dashboard` / `change_dashboard_period`、ESC、`now` |
| `test/test_timeline.py` | `counted_span` のテスト |
| `test/test_dashboard.py` | 新規。集計のテスト |
| `test/test_gantt.py` | `set_visible` のテスト |
| `test/test_dashboard_view.py` | 新規。表示のテスト |
| `test/test_views.py` | 出入りのテスト |
| `CLAUDE.md`・`docs/development.md`・`.claude/MEMORY.md` | 仕様・モジュール構成・作業記録 |

---

### Task 1: `counted_span` を公開する

**Files:**
- Modify: `src/projectapp/timeline.py`(`_counted_span` の定義と、2 か所の呼び出し)
- Modify: `test/test_timeline.py`(import に `counted_span` を足し、テストを足す)

**Interfaces:**
- Produces: `timeline.counted_span(task: Task, project: Project, holidays: dict[date, str]) -> tuple[datetime, datetime] | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py` の `from projectapp.timeline import (` の中に `counted_span,` を足し、ファイルの末尾に足す。

```python
def test_counted_span_is_the_span_that_overallocation_counts() -> None:
    counted = alloc_task("a", 5, 7, 0.5)
    project = Project("P", members=[Member("田中", 1.0)], tasks=[counted])
    assert counted_span(counted, project, {}) == (counted.planned_start, counted.planned_end)
    done = alloc_task("b", 5, 7, 0.5, status=Status.DONE)
    unassigned = Task("c", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 7))
    for task in (done, unassigned):
        assert counted_span(task, project, {}) is None
```

注: `alloc_task` は、このファイルに既にある補助関数(担当者「田中」・割り当て率を指定して作る)。シグネチャが違えば、そのまま使える形に合わせる。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_timeline.py -q`
Expected: FAIL / ERROR(`cannot import name 'counted_span'`)

- [ ] **Step 3: 実装する**

`src/projectapp/timeline.py` で、`_counted_span` を `counted_span` へ名前を変える(定義 1 か所と、`overallocations`・`clip_overloads` の呼び出し 2 か所)。docstring は変えない。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_timeline.py test/test_gantt.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "割り当て超過の対象の期間(counted_span)を公開する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 期間と進捗・予定超過の集計

**Files:**
- Create: `src/projectapp/dashboard.py`
- Create: `test/test_dashboard.py`

**Interfaces:**
- Consumes: `timeline.actual_end`・`current_progress`・`effective_end`・`is_overdue`
- Produces:
  - `PeriodKind`(`WEEK="今週"`・`MONTH="今月"`・`ALL="全期間"`)
  - `Period(start: date, end: date)`(frozen。両端を含む。`days() -> list[date]`、`bounds() -> tuple[datetime, datetime]`)
  - `period_for(kind: PeriodKind, today: date, project: Project, holidays: dict[date, str]) -> Period`
  - `OverdueRow(name: str, assignee: str | None, limit: datetime)`、`Progress(percent: float | None, counts: dict[Status, int], overdue: list[OverdueRow])`
  - `summarize_progress(project: Project, holidays: dict[date, str], now: datetime) -> Progress`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` を作る。

```python
from datetime import date, datetime

import pytest

from projectapp.dashboard import Period, PeriodKind, period_for, summarize_progress
from projectapp.models import Actual, Member, Project, Status, Task

TODAY = date(2026, 10, 7)  # 水曜
NOW = datetime(2026, 10, 7, 12)


def project_of(*tasks: Task, members: list[Member] | None = None) -> Project:
    chosen = [Member("田中", 1.0)] if members is None else members
    return Project("P", base_date=date(2026, 10, 5), members=chosen, tasks=list(tasks))


@pytest.mark.parametrize(
    ("today", "start", "end"),
    [
        (date(2026, 10, 7), date(2026, 10, 5), date(2026, 10, 11)),
        (date(2026, 10, 5), date(2026, 10, 5), date(2026, 10, 11)),  # 月曜
        (date(2026, 10, 11), date(2026, 10, 5), date(2026, 10, 11)),  # 日曜
        (date(2026, 12, 31), date(2026, 12, 28), date(2027, 1, 3)),  # 年またぎ
    ],
)
def test_the_week_runs_from_monday_to_sunday(today: date, start: date, end: date) -> None:
    assert period_for(PeriodKind.WEEK, today, project_of(), {}) == Period(start, end)


@pytest.mark.parametrize(
    ("today", "start", "end"),
    [
        (date(2026, 10, 7), date(2026, 10, 1), date(2026, 10, 31)),
        (date(2026, 12, 15), date(2026, 12, 1), date(2026, 12, 31)),
        (date(2028, 2, 10), date(2028, 2, 1), date(2028, 2, 29)),  # うるう年
    ],
)
def test_the_month_runs_from_the_first_to_the_last_day(today: date, start: date, end: date) -> None:
    assert period_for(PeriodKind.MONTH, today, project_of(), {}) == Period(start, end)


def test_the_whole_period_is_today_when_nothing_has_a_date() -> None:
    assert period_for(PeriodKind.ALL, TODAY, project_of(Task("a")), {}) == Period(TODAY, TODAY)


def test_the_whole_period_spans_planned_dates_deadlines_and_actuals() -> None:
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 6, 9),
        planned_end=datetime(2026, 10, 9, 12),
        deadline=datetime(2026, 10, 20, 17),
        actuals=[Actual(datetime(2026, 10, 3, 9), datetime(2026, 10, 3, 12))],
    )
    assert period_for(PeriodKind.ALL, TODAY, project_of(task), {}) == Period(date(2026, 10, 3), date(2026, 10, 20))


def test_a_period_lists_its_days_and_its_bounds() -> None:
    period = Period(date(2026, 10, 5), date(2026, 10, 7))
    assert period.days() == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    assert period.bounds() == (datetime(2026, 10, 5), datetime(2026, 10, 8))


def test_progress_is_the_effort_weighted_average() -> None:
    a = Task("A", effort_hours=10, status=Status.RUNNING, actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), progress=50)])
    b = Task("B", status=Status.DONE)  # 工数なしは重み 1。終了は 100%
    c = Task("C", effort_hours=10)  # 進捗の入力なしは 0%
    progress = summarize_progress(project_of(a, b, c), {}, NOW)
    assert progress.percent == pytest.approx(600 / 21)
    assert progress.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 1}


def test_progress_is_none_without_tasks() -> None:
    progress = summarize_progress(project_of(), {}, NOW)
    assert progress.percent is None
    assert set(progress.counts.values()) == {0}
    assert progress.overdue == []


def test_overdue_rows_use_the_earliest_passed_limit_and_are_sorted() -> None:
    late = Task("late", status=Status.RUNNING, deadline=datetime(2026, 10, 6, 17), assignee="田中")
    ended = Task(
        "ended",
        status=Status.RUNNING,
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 6, 12),
        deadline=datetime(2026, 10, 9),
    )
    both = Task(
        "both",
        status=Status.PAUSED,
        planned_start=datetime(2026, 10, 4, 9),
        planned_end=datetime(2026, 10, 5, 17),
        deadline=datetime(2026, 10, 6, 17),
    )
    fine = Task("fine", deadline=datetime(2026, 10, 8))
    done_late = Task(
        "done",
        status=Status.DONE,
        deadline=datetime(2026, 10, 6),
        actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 7, 9))],
    )
    rows = summarize_progress(project_of(late, ended, both, fine, done_late), {}, NOW).overdue
    assert [(r.name, r.limit) for r in rows] == [
        ("both", datetime(2026, 10, 5, 17)),
        ("ended", datetime(2026, 10, 6, 12)),
        ("late", datetime(2026, 10, 6, 17)),
    ]
    assert rows[2].assignee == "田中"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: FAIL / ERROR(`ModuleNotFoundError: No module named 'projectapp.dashboard'`)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard.py` を作る。

```python
"""ダッシュボードの集計。NiceGUI に依存しない純粋関数。"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from math import isfinite

from projectapp.models import Project, Status
from projectapp.timeline import actual_end, current_progress, effective_end, is_overdue


class PeriodKind(StrEnum):
    WEEK = "今週"
    MONTH = "今月"
    ALL = "全期間"


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # 両端を含む

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    def bounds(self) -> tuple[datetime, datetime]:
        """[開始日の 0 時, 終了日の翌日の 0 時)。"""
        return datetime.combine(self.start, time.min), datetime.combine(self.end + timedelta(days=1), time.min)


def period_for(kind: PeriodKind, today: date, project: Project, holidays: dict[date, str]) -> Period:
    if kind is PeriodKind.WEEK:
        start = today - timedelta(days=today.weekday())
        return Period(start, start + timedelta(days=6))
    if kind is PeriodKind.MONTH:
        return Period(today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1]))
    moments: list[datetime] = []
    for task in project.all_tasks():
        for moment in (task.planned_start, task.deadline, effective_end(task, project, holidays)):
            if moment is not None:
                moments.append(moment)
        for actual in task.actuals:
            moments.append(actual.start)
            if actual.end is not None:
                moments.append(actual.end)
    if not moments:
        return Period(today, today)
    return Period(min(moments).date(), max(moments).date())


@dataclass(frozen=True)
class OverdueRow:
    name: str
    assignee: str | None
    limit: datetime  # 過ぎている基準(締切と完了予定のうち、早いほう)


@dataclass
class Progress:
    percent: float | None  # 工数で重みづけした進捗率(0〜100)。タスクがなければ None
    counts: dict[Status, int]
    overdue: list[OverdueRow]


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def summarize_progress(project: Project, holidays: dict[date, str], now: datetime) -> Progress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    overdue: list[OverdueRow] = []
    for task in project.all_tasks():
        counts[task.status] += 1
        weight = _weight(task.effort_hours)
        percent = 100 if task.status is Status.DONE else (current_progress(task) or 0)
        weighted += weight * percent
        total += weight
        if task.status is not Status.DONE and is_overdue(task, project, holidays, now):
            moment = actual_end(task) or now
            limits = [
                limit
                for limit in (task.deadline, effective_end(task, project, holidays))
                if limit is not None and moment > limit
            ]
            overdue.append(OverdueRow(task.name, task.assignee, min(limits)))
    overdue.sort(key=lambda row: row.limit)
    return Progress(weighted / total if total else None, counts, overdue)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard.py -q` と `uvx ty check src`
Expected: PASS / All checks passed!

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "ダッシュボード: 期間と、進捗・予定超過の集計を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 負荷・工数・期限の集計と `summarize`

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Modify: `test/test_dashboard.py`

**Interfaces:**
- Consumes: `timeline.counted_span`・`is_workday`・`OVERLOAD_EPSILON`・`effective_end`・`is_overdue`、Task 2 の型
- Produces:
  - `UNASSIGNED = "未割り当て"`
  - `LoadStats(average: float, peak: float, overload_days: int)`(frozen。割合は 1.0 = 100%)
  - `WorkloadRow(name: str, planned_hours: float, actual_hours: float)`
  - `DueRow(moment: datetime, kind: str, name: str, assignee: str | None, overdue: bool)`(`kind` は `"締切"` か `"完了予定"`)
  - `summarize_loads(project, period, holidays) -> dict[str, LoadStats]`(メンバーの順)
  - `summarize_workload(project, period, now, holidays) -> list[WorkloadRow]`
  - `summarize_due(project, period, now, holidays) -> list[DueRow]`
  - `Dashboard(period, progress, loads, workload, due)`(`planned_total`・`actual_total` のプロパティ)
  - `summarize(project: Project, period: Period, now: datetime, holidays: dict[date, str]) -> Dashboard`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の import を次に直し、末尾にテストを足す。

```python
from projectapp.dashboard import (
    UNASSIGNED,
    DueRow,
    Period,
    PeriodKind,
    period_for,
    summarize,
    summarize_due,
    summarize_loads,
    summarize_progress,
    summarize_workload,
)
from projectapp.timeline import overallocations
```

```python
WEEK = Period(date(2026, 10, 5), date(2026, 10, 11))


def span_task(name: str, start_day: int, end_day: int, allocation: float, **kwargs) -> Task:
    return Task(
        name,
        planned_start=datetime(2026, 10, start_day, 9),
        planned_end=datetime(2026, 10, end_day, 17),
        assignee="田中",
        allocation=allocation,
        **kwargs,
    )


def test_load_averages_over_workdays_and_tracks_the_peak() -> None:
    stats = summarize_loads(project_of(span_task("a", 5, 7, 0.5)), WEEK, {})["田中"]
    assert stats.average == pytest.approx(0.3)  # 月〜水に 50%、木・金は 0
    assert stats.peak == 0.5
    assert stats.overload_days == 0


def test_load_counts_days_over_one_hundred_percent_like_the_stripes() -> None:
    project = project_of(span_task("a", 5, 6, 0.6), span_task("b", 5, 6, 0.6))
    stats = summarize_loads(project, WEEK, {})["田中"]
    assert (stats.peak, stats.overload_days) == (pytest.approx(1.2), 2)
    assert stats.average == pytest.approx(0.48)
    assert overallocations(project, {})  # 縞と同じタスクの重なりを数えている


def test_exactly_one_hundred_percent_is_not_an_overload() -> None:
    project = project_of(span_task("a", 5, 6, 0.5), span_task("b", 5, 6, 0.5))
    assert summarize_loads(project, WEEK, {})["田中"].overload_days == 0


def test_finished_tasks_do_not_load_a_member() -> None:
    project = project_of(span_task("a", 5, 7, 0.9, status=Status.DONE))
    stats = summarize_loads(project, WEEK, {})["田中"]
    assert (stats.average, stats.peak, stats.overload_days) == (0.0, 0.0, 0)


def test_holidays_are_not_workdays() -> None:
    stats = summarize_loads(project_of(span_task("a", 5, 7, 0.5)), WEEK, {date(2026, 10, 6): "祝"})["田中"]
    assert stats.average == pytest.approx(0.25)  # 月・水・木・金の 4 日で割る


def test_a_period_without_workdays_is_zero_and_does_not_divide() -> None:
    weekend = Period(date(2026, 10, 10), date(2026, 10, 11))
    stats = summarize_loads(project_of(span_task("a", 5, 12, 0.5)), weekend, {})["田中"]
    assert (stats.average, stats.peak, stats.overload_days) == (0.0, 0.0, 0)


def test_loads_list_the_members_in_order_and_skip_non_members() -> None:
    members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    stranger = span_task("x", 5, 7, 0.5)
    stranger.assignee = "鈴木"
    loads = summarize_loads(project_of(span_task("a", 5, 7, 0.5), stranger, members=members), WEEK, {})
    assert list(loads) == ["田中", "佐藤"]
    assert loads["佐藤"].peak == 0.0


DAY = Period(date(2026, 10, 6), date(2026, 10, 6))


def test_planned_hours_use_allocation_and_daily_hours_and_include_finished_tasks() -> None:
    project = project_of(span_task("a", 5, 7, 0.5, status=Status.DONE))
    rows = summarize_workload(project, DAY, NOW, {})
    assert [(r.name, r.planned_hours) for r in rows] == [("田中", 0.5 * 6.5)]
    assert summarize_workload(project, Period(date(2026, 10, 5), date(2026, 10, 7)), NOW, {})[0].planned_hours == pytest.approx(9.75)


def test_unassigned_work_is_grouped_and_only_listed_when_it_has_hours() -> None:
    unassigned = Task("u", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 17))
    members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    rows = summarize_workload(project_of(unassigned, members=members), DAY, NOW, {})
    assert [(r.name, r.planned_hours) for r in rows] == [("田中", 0.0), ("佐藤", 0.0), (UNASSIGNED, 6.5)]
    assert [r.name for r in summarize_workload(project_of(members=members), DAY, NOW, {})] == ["田中", "佐藤"]


def test_actual_hours_clip_to_the_period_and_run_until_now() -> None:
    crossing = Actual(datetime(2026, 10, 5, 22), datetime(2026, 10, 6, 2))  # 期間内は 2 時間
    running = Actual(datetime(2026, 10, 6, 9))  # now(11:30)まで 2.5 時間
    outside = Actual(datetime(2026, 10, 1, 9), datetime(2026, 10, 1, 12))
    project = project_of(Task("a", assignee="田中", actuals=[crossing, running, outside]))
    rows = summarize_workload(project, DAY, datetime(2026, 10, 6, 11, 30), {})
    assert rows[0].actual_hours == pytest.approx(4.5)


def test_dashboard_totals_add_up_the_rows() -> None:
    project = project_of(span_task("a", 6, 6, 1.0, actuals=[Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12))]))
    dashboard = summarize(project, DAY, NOW, {})
    assert dashboard.planned_total == pytest.approx(6.5)
    assert dashboard.actual_total == pytest.approx(3.0)
    assert dashboard.period == DAY
    assert list(dashboard.loads) == ["田中"]


def test_due_rows_list_deadlines_and_planned_ends_in_the_period_sorted() -> None:
    both = Task(
        "t1",
        assignee="田中",
        deadline=datetime(2026, 10, 8, 17),
        planned_start=datetime(2026, 10, 6, 9),
        planned_end=datetime(2026, 10, 9, 12),
    )
    late = Task("late", status=Status.RUNNING, deadline=datetime(2026, 10, 6, 17))
    edge_in = Task("in", deadline=datetime(2026, 10, 5, 0, 0))  # 期間の開始ちょうどは入る
    edge_out = Task("out", deadline=datetime(2026, 10, 12, 0, 0))  # 終了日の翌日 0 時は入らない
    outside = Task("far", deadline=datetime(2026, 10, 20, 17))
    done = Task("done", status=Status.DONE, deadline=datetime(2026, 10, 7, 9))
    rows = summarize_due(project_of(both, late, edge_in, edge_out, outside, done), WEEK, NOW, {})
    assert rows == [
        DueRow(datetime(2026, 10, 5, 0, 0), "締切", "in", None, True),
        DueRow(datetime(2026, 10, 6, 17), "締切", "late", None, True),
        DueRow(datetime(2026, 10, 8, 17), "締切", "t1", "田中", False),
        DueRow(datetime(2026, 10, 9, 12), "完了予定", "t1", "田中", False),
    ]
```

注: `in` は 10/5 0:00 の締切で、`NOW`(10/7 12:00)より前なので、予定超過(`overdue=True`)になる。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: FAIL / ERROR(`cannot import name 'UNASSIGNED'`)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard.py` の import を直し、末尾に足す。

```python
from projectapp.timeline import (
    OVERLOAD_EPSILON,
    actual_end,
    counted_span,
    current_progress,
    effective_end,
    is_overdue,
    is_workday,
)
```

```python
UNASSIGNED = "未割り当て"
DEADLINE = "締切"
PLANNED_END = "完了予定"


@dataclass(frozen=True)
class LoadStats:
    average: float  # 稼働日の、割り当て率の合計の平均(1.0 = 100%)
    peak: float
    overload_days: int  # 100% を超えた稼働日の数


@dataclass(frozen=True)
class WorkloadRow:
    name: str
    planned_hours: float
    actual_hours: float


@dataclass(frozen=True)
class DueRow:
    moment: datetime
    kind: str
    name: str
    assignee: str | None
    overdue: bool


def _workdays(period: Period, holidays: dict[date, str]) -> list[date]:
    return [day for day in period.days() if is_workday(day, holidays)]


def _covers(start: datetime, end: datetime, day: date) -> bool:
    """[start, end) が、その日(0 時から翌 0 時)と重なる。"""
    return start < datetime.combine(day + timedelta(days=1), time.min) and end > datetime.combine(day, time.min)


def summarize_loads(project: Project, period: Period, holidays: dict[date, str]) -> dict[str, LoadStats]:
    days = _workdays(period, holidays)
    spans: dict[str, list[tuple[datetime, datetime, float]]] = {}
    for task in project.all_tasks():
        counted = counted_span(task, project, holidays)
        if counted is not None and task.assignee is not None:
            spans.setdefault(task.assignee, []).append((*counted, task.allocation))
    loads: dict[str, LoadStats] = {}
    for member in project.members:
        items = spans.get(member.name, [])
        totals = [sum(a for start, end, a in items if _covers(start, end, day)) for day in days]
        loads[member.name] = LoadStats(
            sum(totals) / len(totals) if totals else 0.0,
            max(totals, default=0.0),
            sum(1 for total in totals if total > 1.0 + OVERLOAD_EPSILON),
        )
    return loads


def summarize_workload(
    project: Project, period: Period, now: datetime, holidays: dict[date, str]
) -> list[WorkloadRow]:
    names = [member.name for member in project.members]
    planned = {name: 0.0 for name in (*names, UNASSIGNED)}
    actual = {name: 0.0 for name in (*names, UNASSIGNED)}
    days = _workdays(period, holidays)
    low, high = period.bounds()
    for task in project.all_tasks():
        key = task.assignee if task.assignee in names else UNASSIGNED
        start, end = task.planned_start, effective_end(task, project, holidays)
        if start is not None and end is not None and end > start and isfinite(task.allocation):
            count = sum(1 for day in days if _covers(start, end, day))
            planned[key] += task.allocation * project.daily_hours * count
        for interval in task.actuals:
            seconds = (min(interval.end or now, high) - max(interval.start, low)).total_seconds()
            if seconds > 0:
                actual[key] += seconds / 3600
    rows = [WorkloadRow(name, planned[name], actual[name]) for name in names]
    if planned[UNASSIGNED] or actual[UNASSIGNED]:
        rows.append(WorkloadRow(UNASSIGNED, planned[UNASSIGNED], actual[UNASSIGNED]))
    return rows


def summarize_due(
    project: Project, period: Period, now: datetime, holidays: dict[date, str]
) -> list[DueRow]:
    low, high = period.bounds()
    rows: list[DueRow] = []
    for task in project.all_tasks():
        if task.status is Status.DONE:
            continue
        late = is_overdue(task, project, holidays, now)
        for kind, moment in ((DEADLINE, task.deadline), (PLANNED_END, effective_end(task, project, holidays))):
            if kind == PLANNED_END and moment == task.deadline:
                continue  # 締切だけのタスクは、完了予定が締切と同じになる。同じ日時の 2 行にしない
            if moment is not None and low <= moment < high:
                rows.append(DueRow(moment, kind, task.name, task.assignee, late))
    rows.sort(key=lambda row: (row.moment, row.kind))
    return rows


@dataclass
class Dashboard:
    period: Period
    progress: Progress
    loads: dict[str, LoadStats]
    workload: list[WorkloadRow]
    due: list[DueRow]

    @property
    def planned_total(self) -> float:
        return sum(row.planned_hours for row in self.workload)

    @property
    def actual_total(self) -> float:
        return sum(row.actual_hours for row in self.workload)


def summarize(project: Project, period: Period, now: datetime, holidays: dict[date, str]) -> Dashboard:
    return Dashboard(
        period,
        summarize_progress(project, holidays, now),
        summarize_loads(project, period, holidays),
        summarize_workload(project, period, now, holidays),
        summarize_due(project, period, now, holidays),
    )
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard.py test/test_timeline.py -q` と `uvx ty check src`
Expected: PASS / All checks passed!(落ちたテストは、期待値を先に疑わず、設計書の対応を確かめる)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "ダッシュボード: 負荷・工数の予定と実績・期限の集計を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ガントチャートを隠す・出す(`set_visible`)

**Files:**
- Modify: `src/projectapp/gantt.py`(定数、`__init__`、`build`、メソッド)
- Modify: `test/test_gantt.py`(import と末尾のテスト)

**Interfaces:**
- Produces: `GanttChart.scroll_box: ui.element | None`、`GanttChart.set_visible(visible: bool) -> None`、`gantt.HIDE_CHART_JS`、`gantt.SHOW_CHART_JS`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の `from projectapp.gantt import (` の中に `HIDE_CHART_JS,`・`SHOW_CHART_JS,` を足し、末尾に足す。

```python
async def test_set_visible_hides_and_shows_the_toolbar_and_the_chart_box(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    chart = charts[0]
    assert chart.toolbar is not None and chart.scroll_box is not None
    sent = record_javascript(chart)
    chart.set_visible(False)
    assert not chart.toolbar.visible and not chart.scroll_box.visible
    assert sent == [HIDE_CHART_JS]  # 隠す前に、スクロール位置を覚える
    chart.set_visible(True)
    assert chart.toolbar.visible and chart.scroll_box.visible
    assert sent == [HIDE_CHART_JS, SHOW_CHART_JS]  # 出したあとに、位置を戻す


async def test_set_visible_does_not_redraw_the_chart(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    before = user.find(marker="chart-scroll").elements.pop()
    charts[0].set_visible(False)
    charts[0].set_visible(True)
    after = user.find(marker="chart-scroll").elements.pop()
    assert after is before and not before.is_deleted


async def test_set_visible_keeps_the_toolbar_hidden_when_read_only(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    chart = charts[0]
    chart.set_options(ViewOptions(read_only=True))
    chart.set_visible(False)
    chart.set_visible(True)
    assert chart.toolbar is not None and not chart.toolbar.visible


def test_the_scroll_position_is_remembered_and_restored() -> None:
    assert "scrollTop" in HIDE_CHART_JS and "scrollLeft" in HIDE_CHART_JS
    assert "[data-chart-scroll]" in HIDE_CHART_JS and "[data-chart-scroll]" in SHOW_CHART_JS
    assert "scrollTo" in SHOW_CHART_JS and "requestAnimationFrame" in SHOW_CHART_JS
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "set_visible or remembered"`
Expected: FAIL / ERROR(`cannot import name 'HIDE_CHART_JS'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py`: `SCROLL_TO_TOP_JS` の定義の近くに、定数を足す。

```python
# 非表示(display: none)にすると、枠のスクロール位置が失われる。隠す前に覚え、出したあとの次のフレームで戻す
HIDE_CHART_JS = (
    "(() => { const el = document.querySelector('[data-chart-scroll]');"
    " if (el) { el.dataset.top = el.scrollTop; el.dataset.left = el.scrollLeft; } })()"
)
SHOW_CHART_JS = (
    "requestAnimationFrame(() => { const el = document.querySelector('[data-chart-scroll]');"
    " if (el) el.scrollTo({top: Number(el.dataset.top || 0), left: Number(el.dataset.left || 0)}); })"
)
```

`GanttChart.__init__` の `self.toolbar: ui.row | None = None` の次の行に足す。

```python
        self.scroll_box: ui.element | None = None
```

`build` の、`scroll = ui.element("div")...` の次の行に足す(`with scroll.props(...)` の前)。

```python
        self.scroll_box = scroll
```

`set_options` の前にメソッドを足す。

```python
    def set_visible(self, visible: bool) -> None:
        """ツールバーとチャートを、出す・隠す(描き直さない)。位置は、隠す前に覚え、出したあとに戻す。"""
        if self.toolbar is None or self.scroll_box is None:
            return
        if visible:
            self.toolbar.set_visibility(not self.options.read_only)
            self.scroll_box.set_visibility(True)
            if self.client is not None:
                self.client.run_javascript(SHOW_CHART_JS)
        else:
            if self.client is not None:
                self.client.run_javascript(HIDE_CHART_JS)
            self.toolbar.set_visibility(False)
            self.scroll_box.set_visibility(False)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gantt.py -q` と `uvx ty check src`
Expected: PASS / All checks passed!

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "ガントチャートを描き直さずに隠す・出す(スクロール位置を保つ)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ダッシュボードの表示(`DashboardView`)

**Files:**
- Create: `src/projectapp/dashboard_view.py`
- Create: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: Task 3 の `Dashboard`・`LoadStats`・`WorkloadRow`・`DueRow`・`Progress`・`OverdueRow`・`UNASSIGNED`・`PeriodKind`
- Produces: `DashboardView(on_back: Callable[[], object], on_change: Callable[[PeriodKind], object])`(`build()`・`show(data: Dashboard, kind: PeriodKind)`・`hide()`)、`percent_width(fraction: float) -> str`。マーカー: `dashboard-box`・`dashboard-period`・`dashboard-back`・`dashboard-progress-percent`・`dashboard-count-<状態名の英名>`(`NOT_STARTED`・`RUNNING`・`PAUSED`・`DONE`)・`dashboard-overdue-name-<i>`・`dashboard-overdue-none`・`dashboard-load-<メンバー名>`・`dashboard-hours-<名前>`・`dashboard-hours-total`・`dashboard-due-<i>`・`dashboard-due-kind-<i>`・`dashboard-empty-progress|load|hours|due`

- [ ] **Step 1: `dataviz` スキルを読む**

`Skill` の `dataviz` を呼び、色・凡例・数値の見せ方の指針を確かめる。Step 3 の色の定数(`LOAD_COLOR` など)が指針に反するときは、定数の値だけを直す(構造は変えない)。

- [ ] **Step 2: 失敗するテストを書く**

`test/test_dashboard_view.py` を作る。

```python
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import (
    UNASSIGNED,
    Dashboard,
    DueRow,
    LoadStats,
    OverdueRow,
    Period,
    PeriodKind,
    Progress,
    WorkloadRow,
)
from projectapp.dashboard_view import DashboardView, percent_width
from projectapp.models import Status


def sample() -> Dashboard:
    return Dashboard(
        Period(date(2026, 10, 5), date(2026, 10, 11)),
        Progress(
            42.4,
            {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 3},
            [OverdueRow("遅れた作業", "田中", datetime(2026, 10, 6, 17))],
        ),
        {"田中": LoadStats(0.5, 1.2, 2), "佐藤": LoadStats(0.0, 0.0, 0)},
        [WorkloadRow("田中", 9.5, 3.0), WorkloadRow("佐藤", 0.0, 0.0), WorkloadRow(UNASSIGNED, 6.5, 0.0)],
        [
            DueRow(datetime(2026, 10, 8, 17), "締切", "設計", "田中", False),
            DueRow(datetime(2026, 10, 9, 12), "完了予定", "遅れ", None, True),
        ],
    )


def empty() -> Dashboard:
    day = Period(date(2026, 10, 7), date(2026, 10, 7))
    return Dashboard(day, Progress(None, {status: 0 for status in Status}, []), {}, [], [])


def mount() -> tuple[list[DashboardView], list[int], list[PeriodKind]]:
    views: list[DashboardView] = []
    backs: list[int] = []
    changes: list[PeriodKind] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(lambda: backs.append(1), changes.append)
        views.append(view)
        view.build()

    return views, backs, changes


def text(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


def test_percent_width_is_clamped() -> None:
    assert [percent_width(f) for f in (-1.0, 0.0, 0.5, 2.0)] == ["0.0%", "0.0%", "50.0%", "100.0%"]


async def test_the_view_is_hidden_until_shown_and_can_be_hidden_again(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    await user.should_not_see(marker="dashboard-back")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-back")
    views[0].hide()
    await user.should_not_see(marker="dashboard-back")


async def test_the_progress_card_shows_percent_counts_and_overdue_rows(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    assert text(user, "dashboard-progress-percent") == "42%"
    assert text(user, "dashboard-count-RUNNING") == "実行中 2"
    assert text(user, "dashboard-count-DONE") == "終了 3"
    assert text(user, "dashboard-overdue-name-0") == "遅れた作業"


async def test_the_load_card_shows_average_peak_and_overload_days(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    label = user.find(marker="dashboard-load-田中").elements.pop()
    assert label.text == "平均 50% / 最大 120% / 超過 2 日"
    assert "text-negative" in label.classes  # 100% を超える日があれば強調する
    assert "text-negative" not in user.find(marker="dashboard-load-佐藤").elements.pop().classes


async def test_the_hours_card_lists_members_unassigned_and_the_total(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    assert text(user, "dashboard-hours-田中") == "予定 9.5h / 実績 3.0h"
    assert text(user, f"dashboard-hours-{UNASSIGNED}") == "予定 6.5h / 実績 0.0h"
    assert text(user, "dashboard-hours-total") == "合計 予定 16.0h / 実績 3.0h"


async def test_the_due_card_lists_rows_in_order_and_marks_overdue(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    assert [text(user, "dashboard-due-0"), text(user, "dashboard-due-kind-0")] == ["設計", "締切"]
    assert [text(user, "dashboard-due-1"), text(user, "dashboard-due-kind-1")] == ["遅れ", "完了予定"]
    assert "text-negative" not in user.find(marker="dashboard-due-0").elements.pop().classes
    assert "text-negative" in user.find(marker="dashboard-due-1").elements.pop().classes


async def test_every_card_shows_a_message_without_data(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(empty(), PeriodKind.WEEK)
    for card in ("progress", "load", "hours", "due"):
        await user.should_see(marker=f"dashboard-empty-{card}")


async def test_changing_the_period_notifies_but_showing_does_not(user: User) -> None:
    views, backs, changes = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    user.find(marker="dashboard-period").elements.pop().set_value("今月")
    assert changes == [PeriodKind.MONTH]
    views[0].show(sample(), PeriodKind.ALL)  # 開き直しでトグルを書き換えても、通知しない
    assert changes == [PeriodKind.MONTH]
    assert user.find(marker="dashboard-period").elements.pop().value == "全期間"
    user.find(marker="dashboard-back").click()
    assert backs == [1]
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_view.py -q`
Expected: FAIL / ERROR(`No module named 'projectapp.dashboard_view'`)

- [ ] **Step 4: 実装する**

`src/projectapp/dashboard_view.py` を作る。

```python
"""ダッシュボードの表示。集計(dashboard.py)の結果を、カードと横棒で描く。"""

from collections.abc import Callable

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from projectapp.dashboard import Dashboard, PeriodKind
from projectapp.models import Status

TRACK_STYLE = (
    "height: 10px; width: 100%; border-radius: 5px; overflow: hidden;"
    " background: rgba(128, 128, 128, 0.25); position: relative"
)
TICK_STYLE = "position: absolute; top: 0; bottom: 0; width: 2px; background: currentColor"
GRID_STYLE = "display: grid; grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr)); gap: 16px; width: 100%"
LOAD_COLOR = "#1e88e5"  # 負荷・進捗
OVER_COLOR = "#ef5350"  # 100% を超える日がある負荷(予定超過の赤と同じ系統)
PLANNED_COLOR = "#78909c"  # 予定の時間(未着手の灰青と同じ)
ACTUAL_COLOR = "#43a047"  # 実績の時間
EMPTY = "データがありません"


def percent_width(fraction: float) -> str:
    """割合(0〜1)を、棒の幅(%)にする。範囲外は端に丸める。"""
    return f"{min(max(fraction, 0.0), 1.0) * 100:.1f}%"


def bar(fraction: float, color: str, tick: float | None = None) -> None:
    """横棒。`tick` があれば、その位置に縦の印を出す(最大値など)。"""
    with ui.element("div").style(TRACK_STYLE):
        ui.element("div").style(f"height: 100%; width: {percent_width(fraction)}; background: {color}")
        if tick is not None:
            ui.element("div").style(f"{TICK_STYLE}; left: {percent_width(tick)}")


def card(title: str, marker: str) -> ui.card:
    box = ui.card().classes("w-full gap-2").mark(marker)
    with box:
        ui.label(title).classes("text-subtitle1 text-weight-bold")
    return box


def empty_message(marker: str) -> None:
    ui.label(EMPTY).classes("text-grey").mark(marker)


def moment_text(moment) -> str:  # noqa: ANN001 datetime
    return f"{moment:%m/%d %H:%M}"


class DashboardView:
    """メイン画面の切り替え先。`show` で集計を受け取って描き、`hide` で隠す。"""

    def __init__(self, on_back: Callable[[], object], on_change: Callable[[PeriodKind], object]) -> None:
        self.on_back, self.on_change = on_back, on_change
        self.box: ui.column | None = None
        self.toggle: ui.toggle | None = None
        self.data: Dashboard | None = None
        self.syncing = False  # 開き直しでトグルの値を書き換えるあいだは、変更を通知しない

    def build(self) -> None:
        with ui.column().classes("w-full gap-4") as box:
            self.box = box
            box.mark("dashboard-box")
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("ダッシュボード").classes("text-h5")
                self.toggle = ui.toggle(
                    {kind.value: kind.value for kind in PeriodKind},
                    value=PeriodKind.WEEK.value,
                    on_change=self.on_toggle,
                ).mark("dashboard-period")
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props("flat").mark(
                    "dashboard-back"
                )
            self.cards()
        box.set_visibility(False)

    def on_toggle(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing:
            self.on_change(PeriodKind(event.value))

    def show(self, data: Dashboard, kind: PeriodKind) -> None:
        self.data = data
        if self.toggle is not None and self.toggle.value != kind.value:
            self.syncing = True
            try:
                self.toggle.value = kind.value
            finally:
                self.syncing = False
        if self.box is not None:
            self.box.set_visibility(True)
        self.cards.refresh()

    def hide(self) -> None:
        if self.box is not None:
            self.box.set_visibility(False)

    @ui.refreshable_method
    def cards(self) -> None:
        data = self.data
        if data is None:
            return
        with ui.element("div").style(GRID_STYLE):
            self.progress_card(data)
            self.load_card(data)
            self.hours_card(data)
            self.due_card(data)

    def progress_card(self, data: Dashboard) -> None:
        progress = data.progress
        with card("進捗と遅れ", "dashboard-progress"):
            if progress.percent is None:
                empty_message("dashboard-empty-progress")
                return
            ui.label(f"{progress.percent:.0f}%").classes("text-h4").mark("dashboard-progress-percent")
            bar(progress.percent / 100, LOAD_COLOR)
            with ui.row().classes("gap-4"):
                for status in Status:
                    ui.label(f"{status.value} {progress.counts[status]}").mark(f"dashboard-count-{status.name}")
            ui.label("予定超過").classes("text-subtitle2")
            if not progress.overdue:
                ui.label("なし").classes("text-grey").mark("dashboard-overdue-none")
            for index, row in enumerate(progress.overdue):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.label(moment_text(row.limit)).classes("text-negative")
                    ui.label(row.name).classes("col ellipsis").mark(f"dashboard-overdue-name-{index}")
                    ui.label(row.assignee or "").classes("text-caption")

    def load_card(self, data: Dashboard) -> None:
        with card("人ごとの負荷", "dashboard-load"):
            if not data.loads:
                empty_message("dashboard-empty-load")
                return
            scale = max(1.0, *(stats.peak for stats in data.loads.values()))
            for name, stats in data.loads.items():
                over = stats.overload_days > 0
                with ui.column().classes("w-full gap-1"):
                    ui.label(name)
                    ui.label(
                        f"平均 {stats.average * 100:.0f}% / 最大 {stats.peak * 100:.0f}% / 超過 {stats.overload_days} 日"
                    ).classes("text-caption" + (" text-negative" if over else "")).mark(f"dashboard-load-{name}")
                    bar(stats.average / scale, OVER_COLOR if over else LOAD_COLOR, tick=stats.peak / scale)

    def hours_card(self, data: Dashboard) -> None:
        with card("工数の予定と実績", "dashboard-hours"):
            if not data.workload:
                empty_message("dashboard-empty-hours")
                return
            scale = max((max(row.planned_hours, row.actual_hours) for row in data.workload), default=0.0) or 1.0
            for row in data.workload:
                with ui.column().classes("w-full gap-1"):
                    ui.label(row.name)
                    ui.label(f"予定 {row.planned_hours:.1f}h / 実績 {row.actual_hours:.1f}h").classes(
                        "text-caption"
                    ).mark(f"dashboard-hours-{row.name}")
                    bar(row.planned_hours / scale, PLANNED_COLOR)
                    bar(row.actual_hours / scale, ACTUAL_COLOR)
            ui.label(f"合計 予定 {data.planned_total:.1f}h / 実績 {data.actual_total:.1f}h").classes(
                "text-subtitle2"
            ).mark("dashboard-hours-total")

    def due_card(self, data: Dashboard) -> None:
        with card("期限とマイルストーン", "dashboard-due"):
            if not data.due:
                empty_message("dashboard-empty-due")
                return
            for index, row in enumerate(data.due):
                color = " text-negative" if row.overdue else ""
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.label(moment_text(row.moment)).classes(color.strip())
                    ui.label(row.kind).classes("text-caption" + color).mark(f"dashboard-due-kind-{index}")
                    ui.label(row.name).classes("col ellipsis" + color).mark(f"dashboard-due-{index}")
                    ui.label(row.assignee or "").classes("text-caption")
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_view.py -q` と `uvx ty check src`
Expected: PASS / All checks passed!(`moment_text` の型注釈は、`datetime` を import して `moment: datetime` に直し、`noqa` を外す)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "ダッシュボード: 4 つのカードと横棒の表示を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: メイン画面への組み込み

**Files:**
- Modify: `src/projectapp/views.py`
- Modify: `test/test_views.py`(import と末尾のテスト)

**Interfaces:**
- Consumes: `dashboard.period_for`・`summarize`・`PeriodKind`、`DashboardView`、`GanttChart.set_visible`
- Produces: `MainView.now: Callable[[], datetime]`(既定 `datetime.now`。テストで差し替える)、`MainView.dashboard_kind: PeriodKind | None`、`open_dashboard()`・`refresh_dashboard()`・`change_dashboard_period(kind)`・`close_dashboard()`。マーカー `open-dashboard`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の import に足す: `from projectapp.dashboard import PeriodKind`、`from projectapp.timeline import Scale`(`TaskFilter` は既にある)。末尾に足す。

```python
async def open_dashboard_view(user: User, tmp_path: Path, with_task: bool = True) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    view.now = lambda: datetime(2026, 10, 7, 12)
    view.project.base_date = date(2026, 10, 5)
    if with_task:
        view.project.members = [Member("田中", 1.0)]
        view.save_task(
            None,
            None,
            Task(
                "設計",
                assignee="田中",
                planned_start=datetime(2026, 10, 6, 9),
                planned_end=datetime(2026, 10, 9, 12),
                deadline=datetime(2026, 10, 20, 17),
            ),
        )
    view.mark_clean()
    return view


async def test_the_dashboard_replaces_the_header_and_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    assert view.dashboard_kind == PeriodKind.WEEK
    assert not view.header_box.visible
    assert view.gantt.toolbar is not None and not view.gantt.toolbar.visible
    await user.should_see(marker="dashboard-back")
    await user.should_see(marker="dashboard-progress-percent")


async def test_back_restores_the_header_and_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    user.find(marker="dashboard-back").click()
    assert view.dashboard_kind is None
    assert view.header_box.visible
    assert view.gantt.toolbar is not None and view.gantt.toolbar.visible
    await user.should_not_see(marker="dashboard-back")


async def test_escape_closes_the_dashboard(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.on_key(key_event("Escape"))
    assert view.dashboard_kind is None and view.header_box.visible


async def test_changing_the_period_redraws_with_the_new_period(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    assert user.find(marker="dashboard-due-0").elements  # 今週: 10/9 の完了予定だけ
    assert not user.find(marker="dashboard-due-1").elements
    user.find(marker="dashboard-period").elements.pop().set_value("今月")
    assert view.dashboard_kind == PeriodKind.MONTH
    assert user.find(marker="dashboard-due-1").elements  # 今月: 10/20 の締切も入る


async def test_the_dashboard_leaves_the_chart_state_and_the_project_untouched(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    view.gantt.set_scale(Scale.WEEK)
    view.gantt.set_filter(TaskFilter(query="設"))
    user.find(marker="open-dashboard").click()
    user.find(marker="dashboard-back").click()
    assert view.gantt.scale == Scale.WEEK
    assert view.gantt.task_filter.query == "設"
    assert not view.is_dirty()


async def test_an_empty_project_shows_the_empty_messages(user: User, tmp_path: Path) -> None:
    await open_dashboard_view(user, tmp_path, with_task=False)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-empty-progress")
    await user.should_see(marker="dashboard-empty-due")


async def test_the_dashboard_and_the_preview_do_not_open_together(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="export-preview").click()
    view.open_dashboard()
    assert view.dashboard_kind is None
    view.exit_preview()
    user.find(marker="open-dashboard").click()
    view.enter_preview()
    assert view.preview is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k dashboard`
Expected: FAIL(`open-dashboard` が見つからない)

- [ ] **Step 3: 実装する**

`src/projectapp/views.py`:

import: `from datetime import date, time, timedelta` を `from datetime import date, datetime, time, timedelta` に直す。次を足す。

```python
from projectapp.dashboard import PeriodKind, period_for, summarize
from projectapp.dashboard_view import DashboardView
```

`MainView.__init__` の、`self.preview_notice` の次の行に足す。

```python
        self.now: Callable[[], datetime] = datetime.now  # テストで差し替える
        self.dashboard_kind: PeriodKind | None = None  # 開いているときの期間。保存しない
```

`self.preview_bar = PreviewBar(...)` の次の行に足す。

```python
        self.dashboard_view = DashboardView(self.close_dashboard, self.change_dashboard_period)
```

`build` の `self.preview_bar.build()` の次の行に足す。

```python
        self.dashboard_view.build()
```

`on_key` を、次に置き換える。

```python
    def on_key(self, event: KeyEventArguments) -> None:
        """ESC で、プレビューまたはダッシュボードから戻る。"""
        if event.action.keydown and event.key == "Escape":
            if self.preview is not None:
                self.exit_preview()
            elif self.dashboard_kind is not None:
                self.close_dashboard()
```

`enter_preview` の先頭の `if self.preview is not None:` を `if self.preview is not None or self.dashboard_kind is not None:` に直す。`enter_preview` の前にメソッドを足す。

```python
    def open_dashboard(self) -> None:
        """メイン画面を、ダッシュボードに切り替える(期間の初期値は今週)。プレビュー中は開かない。"""
        if self.preview is not None or self.dashboard_kind is not None:
            return
        self.dashboard_kind = PeriodKind.WEEK
        self.header_box.set_visibility(False)
        self.gantt.set_visible(False)
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        if self.dashboard_kind is None:
            return
        now = self.now()
        period = period_for(self.dashboard_kind, now.date(), self.project, self.holidays)
        self.dashboard_view.show(summarize(self.project, period, now, self.holidays), self.dashboard_kind)

    def change_dashboard_period(self, kind: PeriodKind) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_kind = kind
        self.refresh_dashboard()

    def close_dashboard(self) -> None:
        """ダッシュボードから戻る。ガントチャートは作り直さない(絞り込み・スケール・位置はそのまま)。"""
        if self.dashboard_kind is None:
            return
        self.dashboard_kind = None
        self.dashboard_view.hide()
        self.header_box.set_visibility(True)
        self.gantt.set_visible(True)
```

ヘッダーの「担当者へ書き出し」ボタンの前に足す。

```python
                ui.button("ダッシュボード", icon="dashboard", on_click=self.open_dashboard).mark(
                    "open-dashboard"
                )
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_views.py -q -k "dashboard or preview"` → PASS。続けて `uv run pytest -n auto -q` と `uvx ty check src`。
Expected: すべて PASS / All checks passed!

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "ダッシュボード: メイン画面のボタンと出入り(ESC・戻る・期間の切り替え)を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: ドキュメントと、実機確認用のテストデータ(2 種類)

**Files:**
- Modify: `CLAUDE.md`(「担当者向けファイル」の節の後ろ)
- Modify: `docs/development.md`(モジュール表・設計書表)
- Modify: `.claude/MEMORY.md`
- 作成(リポジトリの外): `~/.projectapp/ダッシュボード_標準.json`、`~/.projectapp/ダッシュボード_境界.json`(確認後に削除してよい)
- 作成(使い捨て): スクラッチパッドの `make_dashboard_data.py`(リポジトリには入れない)

- [ ] **Step 1: `CLAUDE.md` に仕様を足す**

「## 担当者向けファイル」の節の後ろに足す。

```markdown
## ダッシュボード

- メイン画面の「ダッシュボード」で、ガントチャートとダッシュボードを切り替える(ESC か「戻る」で戻る。読み取り専用)
- 期間は`今週`・`今月`・`全期間`から選ぶ(今日が基準。初期値は`今週`。保存しない)
- 4 つの柱: `進捗と遅れ`(工数で重みづけした進捗率・状態別の件数・予定超過の一覧。期間に影響されない)、`人ごとの負荷`(稼働日の割り当て率の平均・最大・100%超の日数。割り当て超過の縞と同じ前提で、終了したタスクは数えない)、`工数の予定と実績`(予定=稼働可能時間×割り当て率×稼働日、終了したタスクも数える。実績=実績の区間の、期間内の長さ)、`期限とマイルストーン`(期間内の締切と完了予定)
- 集計は、表示のたびにプロジェクトから計算する(保存しない)
```

- [ ] **Step 2: `docs/development.md` を直す**

モジュール表の `handoff.py` の行の後ろに足す。

```markdown
| `dashboard.py` | ダッシュボードの集計(期間 `period_for`、進捗・負荷・工数・期限、`summarize`)。純粋関数(NiceGUI に依存しない)。負荷は `timeline.counted_span` を使い、割り当て超過の縞と同じ前提 |
| `dashboard_view.py` | ダッシュボードの表示(カードと横棒。`DashboardView`) |
```

`gantt.py` の行の末尾に「、ツールバーとチャートの表示・非表示(`set_visible`。スクロール位置を覚えて戻す)」を足す。設計書の表の末尾に足す。

```markdown
| ダッシュボード | `2026-10-07-dashboard-design.md` |
```

- [ ] **Step 3: テストデータを作る(2 種類)**

スクラッチパッドに `make_dashboard_data.py` を作る。日付は、実行した日(今日)を基準にするので、「今週」「今月」にデータが入る。

```python
from datetime import date, datetime, timedelta

from projectapp.models import Actual, Member, Priority, Project, Section, Status, Task
from projectapp.storage import save_project

today = date.today()
monday = today - timedelta(days=today.weekday())


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    """今週の月曜から、day_offset 日後の hour 時。"""
    return datetime.combine(monday + timedelta(days=day_offset), datetime.min.time()).replace(hour=hour, minute=minute)


# 種類 1: 標準(ふつうの使われ方。4 つの柱のすべてに、見える値が入る)
standard = Project(
    "ダッシュボード_標準",
    base_date=monday - timedelta(days=7),
    members=[Member("田中", 1.0), Member("佐藤", 0.8), Member("鈴木", 1.2)],
    sections=[
        Section(
            "設計",
            [
                Task("要件整理", planned_start=at(-5, 9), planned_end=at(-3, 17), effort_hours=12, assignee="田中", status=Status.DONE, project_code="PRJ-A",
                     actuals=[Actual(at(-5, 9), at(-5, 17), progress=60), Actual(at(-4, 9), at(-3, 16), progress=100)]),
                Task("画面設計", planned_start=at(0, 9), planned_end=at(2, 17), effort_hours=10, assignee="田中", allocation=0.6, status=Status.RUNNING, project_code="PRJ-A",
                     actuals=[Actual(at(0, 9), at(0, 12), progress=30)]),
                Task("DB 設計", planned_start=at(0, 9), planned_end=at(3, 17), effort_hours=12, assignee="田中", allocation=0.6, status=Status.RUNNING, project_code="PRJ-A"),
            ],
        ),
        Section(
            "開発",
            [
                Task("API 実装", planned_start=at(1, 9), planned_end=at(4, 17), effort_hours=20, assignee="佐藤", status=Status.RUNNING, priority=Priority.HIGH, project_code="PRJ-B",
                     actuals=[Actual(at(1, 9), None, progress=20)]),
                Task("画面実装", planned_start=at(3, 9), planned_end=at(9, 17), effort_hours=24, assignee="鈴木", status=Status.NOT_STARTED, project_code="PRJ-B"),
                Task("認証", planned_start=at(-3, 9), planned_end=at(-1, 17), effort_hours=8, assignee="佐藤", status=Status.PAUSED, deadline=at(-1, 17), project_code="PRJ-B",
                     actuals=[Actual(at(-3, 9), at(-3, 15), progress=40)]),
            ],
        ),
        Section(
            "テスト",
            [
                Task("結合テスト", planned_start=at(10, 9), planned_end=at(14, 17), effort_hours=16, assignee="鈴木", deadline=at(16, 17)),
                Task("リリース判定", deadline=at(4, 17)),  # 締切だけ(今週)
                Task("調査(担当未定)", planned_start=at(0, 9), planned_end=at(1, 17), effort_hours=6),
            ],
        ),
    ],
)
save_project(standard)

# 種類 2: 境界(端の値。空・ゼロ・極端な比率・期間またぎ・大量)
edge_tasks = [
    Task("週末だけ", planned_start=at(5, 9), planned_end=at(6, 17), assignee="田中"),  # 土日だけ(稼働日 0)
    Task("日付なし", assignee="佐藤"),  # 開始予定なし
    Task("終了が開始より前", planned_start=at(3, 9), planned_end=at(1, 9), assignee="田中"),
    Task("0時ちょうどに終わる", planned_start=at(0, 9), planned_end=at(1, 0), assignee="田中", allocation=0.5),
    Task("ちょうど100%(前半)", planned_start=at(0, 9), planned_end=at(1, 17), assignee="鈴木", allocation=0.5),
    Task("ちょうど100%(後半)", planned_start=at(0, 9), planned_end=at(1, 17), assignee="鈴木", allocation=0.5),
    Task("月をまたぐ長い作業", planned_start=at(-20, 9), planned_end=at(40, 17), assignee="田中", allocation=0.1),
    Task("実行中が 2 件(1)", assignee="佐藤", status=Status.RUNNING, actuals=[Actual(at(0, 9), None)]),
    Task("実行中が 2 件(2)", assignee="鈴木", status=Status.RUNNING, actuals=[Actual(at(1, 9), None)]),
    Task("週の頭をまたぐ実績", assignee="田中", actuals=[Actual(at(-1, 22), at(0, 2))]),  # 日曜の夜から月曜の朝
    Task("終了して遅れた", status=Status.DONE, deadline=at(-2, 17), assignee="佐藤", actuals=[Actual(at(-3, 9), at(-1, 12), progress=100)]),
    Task("締切だけ(今月)", deadline=at(12, 17)),
]
edge_tasks += [
    Task(f"大量{i:02d}", planned_start=at(i % 5, 9), planned_end=at(i % 5 + 2, 17), effort_hours=4 + i % 7, assignee=["田中", "佐藤", "鈴木"][i % 3], allocation=0.2, deadline=at(i % 10, 17))
    for i in range(60)
]
edge = Project(
    "ダッシュボード_境界",
    base_date=monday - timedelta(days=21),
    members=[Member("田中", 0.1), Member("佐藤", 3.0), Member("鈴木", 1.0), Member("高橋", 1.0)],  # 比率の両端と、タスクのないメンバー
    sections=[Section("境界", edge_tasks)],
)
save_project(edge)
print("作成:", standard.name, edge.name)
```

実行する(`~/.projectapp` への書き込みは、サンドボックスの外で行う必要がある。ユーザーが依頼した作業なので、そのコマンドだけ `dangerouslyDisableSandbox` で実行する)。

Run: `uv run python <スクラッチパッド>/make_dashboard_data.py`
Expected: `作成: ダッシュボード_標準 ダッシュボード_境界`

続けて、両ファイルを読み込めることを確かめる(読込が不正な値を拒否するため、作ったデータが形式に合っているかの確認になる)。

Run: `uv run python -c "from pathlib import Path; from projectapp.storage import load_project; [print(p.stem, len(load_project(p).all_tasks())) for p in sorted(Path.home().joinpath('.projectapp').glob('ダッシュボード_*.json'))]"`
Expected: `ダッシュボード_境界 72` と `ダッシュボード_標準 9` が出る(エラーなし)

- [ ] **Step 4: `.claude/MEMORY.md` を直す**

要望 6 の状況(ブランチ `feature/dashboard`、設計書・実装計画の名前、`dashboard.py`・`dashboard_view.py`、テスト件数、実機確認待ち、確認用データ `ダッシュボード_標準.json`・`ダッシュボード_境界.json`)を、「現在の状況」の要約・「今後の要望」の 6・「参照先」に足す。確認用のデータの一覧にも、2 ファイルを足す。件数は、`uv run pytest -n auto -q` の結果を使う。

- [ ] **Step 5: 全体の確認とコミット**

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS / All checks passed!

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md
git commit -m "ダッシュボード: 仕様・開発メモ・作業記録を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## 完了の条件

- `uv run pytest -n auto -q` と `uvx ty check src` が通る。
- `~/.projectapp/ダッシュボード_標準.json` と `ダッシュボード_境界.json` が、読込エラーなしで開ける。
- 実機(ネイティブウィンドウ)で、次をユーザーが確かめる(自動テストでは見えない)。
  - 「ダッシュボード」→ 4 つのカードが出る。`今週`・`今月`・`全期間` で値が変わる。ESC・「戻る」で戻る。
  - ライト・ダークの両方で、棒と文字が読める。ウィンドウを狭くすると、カードが 1 列になる。
  - ガントチャートの縦横のスクロール位置・絞り込み・スケールが、戻ったあとも変わらない(特にスクロール位置)。
  - `ダッシュボード_境界` で、空の柱・100% 超・稼働日のない期間・大量のタスクでも、崩れない。
- マージ・プッシュは、ユーザーの許可を得てから行う。
