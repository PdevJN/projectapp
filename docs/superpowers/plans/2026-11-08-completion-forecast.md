# 完了見込み(要望 133) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 進捗(残りの工数)を見た「完了見込み」を、当初の完了予定とは別に算出し、ガントチャートの棒・下部パネル・ダッシュボードの遅れの一覧・警告のホバーに出す。

**Architecture:** 純粋関数 `forecast.forecast_end` が「今日(または実効の開始)から残りの工数を、今の担当で消化して終わる日」を返す。`timeline.calc_end` に `weeks_start` を通して週ごとの担当の区切りを保つ。要望 132 の試算(`crew_trial.evaluate` の `from_now` の枝)を同じ関数に置き換える。当初の完了予定(`effective_end`)・警告の式・ファイル形式(version 21)は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(NiceGUI `User` fixture)、ruff、ty。

**Spec:** `docs/superpowers/specs/2026-11-08-completion-forecast-design.md`(要望 132 の設計 `2026-11-08-delay-response-design.md` を前提にする)

## Global Constraints

- 言語は日本語。Python 3.13 以上。ライブラリは NiceGUI。
- `version` は 21 のまま。完了見込みは保存せず、表示のたびに算出する。
- 当初の完了予定(`effective_end`)・予定超過の判定(`完了予定 ≤ 今`)・警告の式(`残り ÷ 稼働量 ≥ 1.10`)・先行の押し出し・PlantUML・CSV・担当者向けファイルは変えない。
- 用語: 予定超過 / 期限超過 / 遅れ(赤)/ 警告(黄)/ 割り当て超過。`遅延`を赤の意味では使わない。紫は試算中専用。見込みの色は灰青(`--forecast`)。
- 日時から位置への変換や日程計算は NiceGUI から切り離した純粋関数にする(`forecast.py` は NiceGUI を import しない)。
- 算出できないときは `None`(例外にしない)。
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り `uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`。
- マージは利用者の指示を待つ(PR を作って止まる)。ベースは `develop`。

## Review Focus

1. 進捗情報のない通常タスク(遅れでも警告でもない)に、経過日数ぶんの「遅れ」見込みが出ない(`None`)。
2. 警告のタスクは必ず `見込み > 当初の完了予定`(同日を含まない)。
3. 要望 132 の試算の数字(`trial_end`・`baseline_end`・`days_earlier`)が、共通化の前後で変わらない。
4. 週ごとの担当のタスクで、週の区切りが開始から数えたまま(見込みの起点が開始より後でも)。
5. 隠す条件: 試算中・終了済み・開始が未来・残り 0・日付が同じ・`show_alerts` オフ。見込みの追加で描画が重くならない(300 タスク)。

## File Structure

- Create `src/projectapp/forecast.py` — `Forecast`・`forecast_end`(純粋)。
- Modify `src/projectapp/timeline.py` — `calc_end`/`_calc_end`/`_consume` に `weeks_start`。
- Modify `src/projectapp/crew_trial.py` — `evaluate` の `from_now` の枝を `forecast_end` に。
- Modify `src/projectapp/pace.py` — `Pace.hint(forecast)`。
- Modify `src/projectapp/gantt.py` — 見込みの点線・文言・キャッシュ・CSS・警告ホバー。
- Modify `src/projectapp/bottom_info.py` — `完了見込み` 行・ホバー。
- Modify `src/projectapp/dashboard.py`・`dashboard_view.py` — 遅れの一覧の `見込み m/d`。
- Tests: `test/test_forecast.py`(新規)、`test/test_timeline.py`(追記)、`test/test_crew_trial.py`(追記)、`test/test_forecast_view.py`(新規)。
- Docs: `.claude/spec/concept.md`・`gantt.md`・`dashboard.md`、`docs/development.md`、`docs/requests.md`、`docs/samples/完了見込みの確認.json`。

---

### Task 1: `calc_end` に `weeks_start`

**Files:**
- Modify: `src/projectapp/timeline.py`(`_consume` ~565、`_calc_end` ~604、`calc_end` ~471、`consumed_slices` ~496 は変えない)
- Test: `test/test_timeline.py`(追記)

**Interfaces:**
- Produces: `calc_end(..., crew=None, weeks=None, weeks_start: date | None = None) -> datetime | None`。`weeks_start` が `None` のときは従来どおり `start` の日から 7 日ごと。指定があれば、その日から 7 日ごと。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_calc_end_counts_weeks_from_weeks_start_when_given() -> None:
    from datetime import date, datetime, time

    from projectapp.timeline import Worker, calc_end

    weeks = [[Worker()], [Worker(rate=4.0)]]  # 第 2 週は 4 倍速
    start = datetime(2026, 11, 9, 9)  # 月曜。weeks_start(11/2)から数えると第 2 週
    fast = calc_end(
        start, 16.0, 8.0, time(9), {}, weeks=weeks, weeks_start=date(2026, 11, 2)
    )
    slow = calc_end(start, 16.0, 8.0, time(9), {}, weeks=weeks)  # 省略: start から数える
    assert fast is not None and slow is not None
    assert fast.date() == date(2026, 11, 9)  # 4 倍速で 4h → 当日
    assert slow.date() > fast.date()  # 第 1 週(等速)なので 2 日かかる
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_timeline.py -k weeks_start -q` / Expected: FAIL(`unexpected keyword argument 'weeks_start'`)

- [ ] **Step 3: 実装** — `_consume` に `weeks_start: date | None = None` を足し、`week_index(start.date(), …)` を `week_index(weeks_start or start.date(), …)` に。`_calc_end` と `calc_end` にも同じ引数を足して通す。

```python
def _consume(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crews: list[list[Worker]],
    weeks_start: date | None = None,
) -> Iterator[tuple[datetime, datetime, list[Worker]]]:
    remaining = effort_hours
    origin = weeks_start or start.date()
    day, cursor = start.date(), start
    while True:
        workers = crews[week_index(origin, day, len(crews))]
        ...  # 以降は変えない
```

`_calc_end(..., crews, weeks_start=None)` は `_consume(..., crews, weeks_start)` を呼ぶ。`calc_end` は docstring に「`weeks_start` があれば、その日から 7 日ごと(起点が開始より後でも週の区切りを保つ)」を足し、`_calc_end(..., crews, weeks_start)` を呼ぶ。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_timeline.py -q` / Expected: すべて PASS(`weeks_start` 省略の既存テストが従来どおり通る)

- [ ] **Step 5: Commit** — `git add src/projectapp/timeline.py test/test_timeline.py && git commit -m "feat: calc_end に週の区切りの起点 weeks_start を足す(要望 133)"`

---

### Task 2: `forecast.py`(純粋関数)

**Files:**
- Create: `src/projectapp/forecast.py`
- Test: `test/test_forecast.py`(新規)

**Interfaces:**
- Consumes: `timeline.calc_end(..., weeks_start=)`(Task 1)、`remaining.remaining_hours`、`pace.warning_pace`、`timeline.effective_start/effective_end/crew_of/crew_on`、`crew_trial` の `snap_week` と同じ式(循環 import を避けるため `forecast.py` に同じ定義を持たず、`snap_week` は **`forecast.py` に移し、`crew_trial.py` が import し直す**)。
- Produces:
  - `Forecast(end: datetime, planned_end: datetime | None)` と `days_later -> int | None`(`planned_end` が `None` なら `None`。`(end.date() - planned_end.date()).days`)。
  - `snap_week(anchor: date, day: date) -> int`(`crew_trial.snap_week` と同じ。`crew_trial` から `from projectapp.forecast import snap_week` で再公開し、既存テストの import を壊さない)。
  - `forecast_end(task, project, holidays, now, schedule, extra_crew: tuple[tuple[str, ...], date] | None = None) -> Forecast | None`。`extra_crew` は (増員の名前の列, 増員日)。

**Ruling(週の格子):** 週ごとの担当のあるタスクは格子を実効の開始から数え(`weeks_start=start.date()`)、増員は `snap_week(start.date(), max(増員日, 今日))` 週以降へ足す。週ごとの担当のないタスク(1 週ぶん)は格子を今日から数え(`weeks_start=origin.date()`)、増員は `snap_week(origin.date(), 増員日)`。後者は要望 132 の既存の数字を保つため。

- [ ] **Step 1: 失敗するテストを書く** — `test/test_forecast.py`

```python
from datetime import date, datetime

from projectapp.forecast import Forecast, forecast_end
from projectapp.models import Assignee, Member, Project, Section, Status, Task
from projectapp.pace import warning_pace
from projectapp.timeline import Schedule, effective_end

START = datetime(2026, 11, 2, 9)  # 月曜
HOLIDAYS: dict[date, str] = {}


def sample(**changes: object) -> tuple[Project, Task]:
    task = Task(
        "a",
        id="ta",
        planned_start=START,
        effort_hours=60.0,
        assignees=[Assignee("田中")],
    )
    for key, value in changes.items():
        setattr(task, key, value)
    project = Project(
        name="p",
        base_date=START,
        members=[Member("田中"), Member("鈴木")],
        sections=[Section("s", tasks=[task])],
    )
    return project, task


def run(
    project: Project, task: Task, now: datetime, extra=None
) -> Forecast | None:
    return forecast_end(
        task, project, HOLIDAYS, now, Schedule(project, HOLIDAYS), extra
    )


def test_no_progress_info_and_not_late_means_no_forecast() -> None:
    project, task = sample()
    assert run(project, task, datetime(2026, 11, 4, 10)) is None  # 当初の予定が続く


def test_on_track_progress_forecasts_earlier_or_same_than_plan() -> None:
    project, task = sample(progress=50)  # 2 日で半分: 予定(15h/日換算でなく 8h/日)より速い
    fc = run(project, task, datetime(2026, 11, 4, 10))
    assert fc is not None and fc.planned_end is not None
    assert fc.end <= fc.planned_end


def test_behind_progress_forecasts_later_than_plan() -> None:
    project, task = sample(progress=10)
    fc = run(project, task, datetime(2026, 11, 9, 10))
    assert fc is not None and fc.days_later is not None and fc.days_later > 0


def test_overdue_without_progress_forecasts_full_effort_from_today() -> None:
    project, task = sample()
    now = datetime(2026, 11, 20, 10)
    assert effective_end(task, project, HOLIDAYS, Schedule(project, HOLIDAYS)) <= now
    fc = run(project, task, now)
    assert fc is not None and fc.end > now


def test_not_targets_return_none() -> None:
    project, task = sample(progress=100)
    assert run(project, task, datetime(2026, 11, 9, 10)) is None  # 残り 0
    project, task = sample(progress=10, status=Status.DONE)
    assert run(project, task, datetime(2026, 11, 9, 10)) is None  # 終了
    project, task = sample(progress=10)
    assert run(project, task, datetime(2026, 11, 1, 10)) is None  # 開始が未来


def test_manual_planned_end_still_gets_a_forecast() -> None:
    project, task = sample(
        progress=10, planned_end=datetime(2026, 11, 20, 18), planned_end_manual=True
    )
    assert run(project, task, datetime(2026, 11, 9, 10)) is not None


def test_a_warning_task_always_forecasts_after_the_planned_end() -> None:
    project, task = sample(progress=10)
    now = datetime(2026, 11, 4, 10)
    schedule = Schedule(project, HOLIDAYS)
    assert warning_pace(task, project, HOLIDAYS, now, schedule) is not None, (
        "前提: 警告になる値に調整する"
    )
    fc = run(project, task, now)
    assert fc is not None and fc.planned_end is not None
    assert fc.end > fc.planned_end  # 同日を含まない


def test_weekly_crew_keeps_week_boundaries_counted_from_the_start() -> None:
    weekly = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    project, task = sample(progress=10, weekly_crew=weekly)
    late = run(project, task, datetime(2026, 11, 9, 10))  # 第 2 週(2 人)に入ってから
    project2, single = sample(progress=10)  # 1 人のまま
    base = run(project2, single, datetime(2026, 11, 9, 10))
    assert late is not None and base is not None
    assert late.end < base.end  # 2 人なので早い(第 1 週の 1 人に戻らない)


def test_extra_crew_is_rounded_to_the_later_week_and_shortens_the_forecast() -> None:
    project, task = sample()
    now = datetime(2026, 11, 20, 10)  # 予定超過(進捗情報なし)
    base = run(project, task, now)
    boosted = run(project, task, now, (("鈴木",), date(2026, 11, 23)))
    assert base is not None and boosted is not None
    assert boosted.end < base.end
    # 今日以前の増員日は今日から
    now_boost = run(project, task, now, (("鈴木",), date(2026, 11, 1)))
    assert now_boost is not None and now_boost.end <= boosted.end


def test_unavailable_input_returns_none_without_raising() -> None:
    project, task = sample(progress=10, effort_hours=float("nan"))
    assert run(project, task, datetime(2026, 11, 9, 10)) is None
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_forecast.py -q` / Expected: FAIL(`ModuleNotFoundError: projectapp.forecast`)

- [ ] **Step 3: 実装** — `src/projectapp/forecast.py`

```python
"""完了見込み(要望 133): 進捗(残りの工数)を見た、今日からの完了日。NiceGUI に依存しない純粋関数。

当初の完了予定(`effective_end`)は変えない。見込みは保存せず、表示のたびに算出する。
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from math import isfinite

from projectapp.models import Assignee, Project, Status, Task, TaskKind
from projectapp.pace import warning_pace
from projectapp.remaining import remaining_hours
from projectapp.timeline import (
    Schedule,
    calc_end,
    crew_of,
    effective_end,
    effective_start,
)
from projectapp.models import MAX_WEEKS


@dataclass(frozen=True)
class Forecast:
    end: datetime  # 完了見込み
    planned_end: datetime | None  # 当初の完了予定(effective_end)

    @property
    def days_later(self) -> int | None:
        """見込み − 当初の予定の日数(早ければ負)。当初の予定がなければ None。"""
        if self.planned_end is None:
            return None
        return (self.end.date() - self.planned_end.date()).days


def snap_week(anchor: date, day: date) -> int:
    """増員日を、anchor から 7 日ごとの週の境目に、遅い側へ丸めた週の添字(0 始まり)。anchor より前は第 1 週。"""
    days = (day - anchor).days
    return 0 if days <= 0 else -(-days // 7)


def _has_progress(task: Task) -> bool:
    return bool(task.progress) or bool(task.actuals)


def _with_added(
    base: list[list[Assignee]], first: int, names: tuple[str, ...]
) -> list[list[Assignee]] | None:
    """base の週ごとの担当の、first 週以降に names を足す(重複なし)。上限を超えるなら None。"""
    if first >= MAX_WEEKS:
        return None
    while len(base) <= first:
        base.append([replace(a) for a in base[-1]])
    weeks: list[list[Assignee]] = []
    for number, week in enumerate(base):
        crew = [replace(a) for a in week]
        if number >= first:
            present = {a.name for a in crew}
            crew += [Assignee(n) for n in names if n not in present]
        weeks.append(crew)
    return weeks


def forecast_end(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule,
    extra_crew: tuple[tuple[str, ...], date] | None = None,
) -> Forecast | None:
    """今日(または実効の開始)から、残りの工数を今の担当で消化して終わる日時。出さないときは None。

    通常タスクで、終了しておらず、残りの工数があり、実効の開始が今日以前のものが対象。
    進捗度も実績もないタスクは、予定超過か警告のときだけ出す(経過日数ぶん常に遅く出るのを避ける)。
    extra_crew = (増員の名前の列, 増員日)は要望 132 の試算用。増員日は週の境目の遅い側に丸める。
    """
    if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None or start > now:
        return None
    planned = effective_end(task, project, holidays, schedule)
    rest = remaining_hours(task, project, holidays, now)
    if not (isfinite(rest) and rest > 0):
        return None
    if not _has_progress(task):
        overdue = planned is not None and planned <= now
        if not overdue and warning_pace(task, project, holidays, now, schedule) is None:
            return None
    origin = max(now, start)
    weekly = bool(task.weekly_crew)
    anchor = start.date() if weekly else origin.date()
    rows = [[replace(a) for a in w] for w in task.weekly_crew] or [
        [replace(a) for a in task.assignees]
    ]
    if extra_crew is not None:
        names, day = extra_crew
        first = snap_week(anchor, max(day, origin.date()) if weekly else day)
        added = _with_added(rows, first, names)
        if added is None:
            return None
        rows = added
    crews = [
        crew_of(
            week,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        )
        for week in rows
    ]
    end = calc_end(
        origin,
        rest,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=crews,
        weeks_start=anchor,
    )
    return None if end is None else Forecast(end, planned)
```

(`from projectapp.models import MAX_WEEKS` は上の import 行にまとめる。)

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_forecast.py -q` / Expected: PASS。`警告の前提` の assert が落ちたら、`progress` を調整して警告になる値にする(台帳に Ruling)。

- [ ] **Step 5: Commit** — `git add src/projectapp/forecast.py test/test_forecast.py && git commit -m "feat: 進捗を見た完了見込み forecast_end を足す(要望 133)"`

---

### Task 3: 要望 132 の試算を `forecast_end` に共通化

**Files:**
- Modify: `src/projectapp/crew_trial.py`(`snap_week`・`_with_added` を `forecast` から import、`evaluate` の `from_now` の枝)
- Test: `test/test_crew_trial.py`(追記)

**Interfaces:**
- Consumes: `forecast.forecast_end`・`forecast.snap_week`・`forecast._with_added`(`crew_trial._with_added` は `forecast` のものを再利用し、`crew_trial` の定義は削除。`trial_weeks` はそのまま使う)。
- Produces: `evaluate` の戻り値の形は不変(`TrialResult`)。

- [ ] **Step 1: 失敗するテストを書く(前後で数字が一致)** — 既存の `from_now` のテスト(`test/test_crew_trial.py` の遅れ・警告のケース)の期待値は変えない。追加:

```python
def test_trial_end_equals_the_forecast_with_the_extra_crew_for_late_tasks() -> None:
    from projectapp.forecast import forecast_end

    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    now = datetime(2026, 11, 20, 10)  # 予定超過
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 23))
    result = evaluate(task, project, HOLIDAYS, schedule, trial, now)
    expected = forecast_end(
        task, project, HOLIDAYS, now, schedule, (trial.names, trial.start)
    )
    base = forecast_end(task, project, HOLIDAYS, now, schedule)
    assert result is not None and expected is not None and base is not None
    assert result.from_now
    assert result.trial_end == expected.end
    assert result.baseline_end == base.end


def test_trial_falls_back_to_the_plan_based_calc_when_no_forecast() -> None:
    project, task = sample()
    result = evaluate(
        task, project, HOLIDAYS, Schedule(project, HOLIDAYS),
        TrialCrew("ta", ("鈴木",), date(2026, 11, 9)), NOW,
    )
    assert result is not None and not result.from_now  # 遅れでも警告でもない: 従来の計算
    assert result.trial_end is not None and result.original_end is not None
    assert result.trial_end < result.original_end
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_crew_trial.py -q` / Expected: 新テストは(共通化前でも数字が同じなら)通る可能性がある。通る場合は RED にならないので、**`forecast_end` が `None` を返す枝(下記の分岐)を最初に壊す**ことで確認する: Step 3 の前に、`evaluate` の `from_now` 判定を `forecast_end` の戻り値に差し替えただけの状態で既存+新規テストを流し、全 PASS であることを確認する(リファクタの回帰テスト)。

- [ ] **Step 3: 実装** — `evaluate` の `overdue ... if` ブロックを置き換える。

```python
    forecast = forecast_end(task, project, holidays, now, schedule)
    if forecast is not None:
        # 遅れ・警告・進捗のあるタスク: 今日を起点に、残りの工数を消化する見込み
        boosted = forecast_end(
            task, project, holidays, now, schedule, (trial.names, trial.start)
        )
        if boosted is None:
            return None
        return TrialResult(
            task.id,
            trial.names,
            first,
            original,
            boosted.end,
            False,
            from_now=True,
            baseline_end=forecast.end,
        )
    end = calc_end(...)  # 従来の当初の予定ベース(開始から全工数)。ここは変えない
```

`crews_of` は後段で使うので残す。不要になる import(`remaining_hours`・`warning_pace`・`crew_on`)を削除し、`snap_week` は `from projectapp.forecast import _with_added, snap_week`(`_with_added` を公開名 `with_added` にして import してよい)にする。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_crew_trial.py test/test_delay_response.py test/test_delay_response_view.py -q` / Expected: PASS。**週ごとの担当のある遅れたタスクの 132 のテストが落ちたら**、格子の変更(開始から数える)による意図した差か確認し、台帳に Ruling を書いたうえで期待値を直す(週ごとの担当のないタスクの数字は変わらないこと)。

- [ ] **Step 5: Commit** — `git add src/projectapp/crew_trial.py src/projectapp/forecast.py test/test_crew_trial.py && git commit -m "refactor: 遅延対応の試算を forecast_end に共通化する(要望 133)"`

---

### Task 4: ガントチャートの棒に見込みを出す

**Files:**
- Modify: `src/projectapp/gantt.py`(`__init__` ~727 と ~2252 でキャッシュを初期化、棒の描画 ~2864 の `trial_overlay` の呼び出しの次、`trial_overlay` の隣に `forecast_overlay`、CSS 定数と `ui.add_css`、警告ホバー ~2660)
- Modify: `src/projectapp/pace.py`(`Pace.hint(forecast: datetime | None = None)`)
- Test: `test/test_forecast_view.py`(新規)、`test/test_pace.py`(追記)

**Interfaces:**
- Consumes: `forecast.forecast_end`・`Forecast`。
- Produces: `GanttChart.forecast_of(task) -> Forecast | None`(描画の間キャッシュ。`self.schedule` を作り直すところでクリア)。`forecast_text(f: Forecast) -> str`(`見込み 11/16(+3 日)`、早い場合は `(−N 日)`)。マーカー `forecast-line-{key}-{ti}`・`forecast-label-{key}-{ti}`。CSS 変数 `--forecast`(ライト `#78909c`、ダーク `#90a4ae`)。

- [ ] **Step 1: 失敗するテストを書く** — `test/test_forecast_view.py`

```python
from datetime import datetime, timedelta
from pathlib import Path

from nicegui.testing import User

from projectapp import clock
from projectapp.gantt import FORECAST_CSS, forecast_text
from projectapp.forecast import Forecast
from projectapp.models import Assignee, Status, Task
from test_delay_response import opened


def test_forecast_text_shows_the_signed_days() -> None:
    end = datetime(2026, 11, 16, 18)
    assert forecast_text(Forecast(end, end - timedelta(days=3))) == "見込み 11/16(+3 日)"
    assert forecast_text(Forecast(end, end + timedelta(days=2))) == "見込み 11/16(−2 日)"


def test_forecast_colour_has_light_and_dark_values() -> None:
    assert "--forecast" in FORECAST_CSS and "body.body--dark" in FORECAST_CSS
    assert "dotted" in FORECAST_CSS


def late_task(**changes: object) -> Task:
    today = clock.now()
    task = Task(
        "late",
        id="tl",
        planned_start=today.replace(hour=9, minute=0, second=0, microsecond=0)
        - timedelta(days=6),
        effort_hours=20.0,
        assignees=[Assignee("田中")],
    )
    for key, value in changes.items():
        setattr(task, key, value)
    return task


async def put(user: User, tmp_path: Path, task: Task):
    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    view.project.tasks.append(task)
    view.after_edit()
    return view


async def test_a_late_task_shows_the_forecast_line_and_label(
    user: User, tmp_path: Path
) -> None:
    await put(user, tmp_path, late_task())
    await user.should_see(marker="forecast-line-top-0")
    await user.should_see(marker="forecast-label-top-0")


async def test_no_forecast_for_a_task_that_is_not_late_and_has_no_progress(
    user: User, tmp_path: Path
) -> None:
    await put(user, tmp_path, late_task(effort_hours=20.0, planned_start=clock.now()))
    await user.should_not_see(marker="forecast-label-top-0")


async def test_no_forecast_when_done_or_alerts_off_or_trial_active(
    user: User, tmp_path: Path
) -> None:
    view = await put(user, tmp_path, late_task())
    await user.should_see(marker="forecast-label-top-0")
    view.try_crew("tl", ["鈴木"], clock.now().date())
    await user.should_not_see(marker="forecast-label-top-0")  # 試算中は試算を優先
    view.trials.clear()
    view.after_edit()
    view.project.tasks[0].status = Status.DONE
    view.after_edit()
    await user.should_not_see(marker="forecast-label-top-0")


async def test_forecast_is_computed_once_per_task_per_render(
    user: User, tmp_path: Path, monkeypatch
) -> None:
    import projectapp.gantt as gantt

    calls: list[str] = []
    real = gantt.forecast_end

    def counting(task, *args, **kwargs):
        calls.append(task.id)
        return real(task, *args, **kwargs)

    monkeypatch.setattr(gantt, "forecast_end", counting)
    await put(user, tmp_path, late_task())
    await user.should_see(marker="forecast-label-top-0")
    assert calls.count("tl") <= 2  # 行の描画と警告ホバーで使い回す(描画ごとに 1 回)
```

`test/test_pace.py` に追記:

```python
def test_hint_adds_the_forecast_date_when_given() -> None:
    from datetime import datetime

    from projectapp.pace import Pace

    pace = Pace(54.0, 40.0)
    assert "完了見込み 11/16" not in pace.hint()
    assert pace.hint(datetime(2026, 11, 16, 18)).endswith("完了見込み 11/16")
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_forecast_view.py test/test_pace.py -q` / Expected: FAIL(`cannot import name FORECAST_CSS`)

- [ ] **Step 3: 実装**

`pace.py`:
```python
    def hint(self, forecast: datetime | None = None) -> str:
        """ホバーの文字。稼働量がないときは、割合を出さない。見込みがあれば末尾に完了見込みを足す。"""
        head = f"警告: 残り {self.remaining:.1f}h / 稼働 {self.capacity:.1f}h"
        text = head if self.capacity <= 0 else f"{head}({self.ratio * 100:.0f}%)"
        return text if forecast is None else f"{text} 完了見込み {forecast:%m/%d}"
```
(`datetime` は既に import 済みか確認し、なければ足す。)

`gantt.py`:
```python
FORECAST_CSS = """
:root { --forecast: #78909c; }
body.body--dark { --forecast: #90a4ae; }
.forecast-line { border-top: 2px dotted var(--forecast); pointer-events: none; }
.forecast-label { color: var(--forecast); font-size: 11px; white-space: nowrap; }
"""


def forecast_text(forecast: Forecast) -> str:
    """棒の横に出す完了見込み。差が負(早まる)のときは `−N 日`。"""
    text = f"見込み {forecast.end:%m/%d}"
    days = forecast.days_later
    if days is None or days == 0:
        return text
    return f"{text}(+{days} 日)" if days > 0 else f"{text}(−{-days} 日)"
```
`ui.add_css(FORECAST_CSS)` を `ui.add_css(DELAY_RESPONSE_CSS)` の次に。`__init__` と ~2252 の `self.schedule = Schedule(...)` の直後に `self.forecast_cache: dict[str, Forecast | None] = {}` / `self.forecast_cache.clear()`。

```python
    def forecast_of(self, task: Task) -> Forecast | None:
        """タスクの完了見込み。描画の間は結果を使い回す。"""
        if task.id not in self.forecast_cache:
            self.forecast_cache[task.id] = forecast_end(
                task, self.project, self.holidays, self.now(), self.schedule
            )
        return self.forecast_cache[task.id]

    def forecast_overlay(self, key, ti, task, columns, width) -> None:
        """当初の完了予定の位置から見込みの位置まで細い灰青の点線を伸ばし、右に `見込み m/d(+N 日)` を出す。
        見込みの日付が当初の予定の日付と同じなら出さない。"""
        forecast = self.forecast_of(task)
        if (
            forecast is None
            or forecast.planned_end is None
            or forecast.days_later in (None, 0)
        ):
            return
        low, high = sorted((forecast.planned_end, forecast.end))
        span = bar_span(low, high, columns)
        if span is None:
            return
        ui.element("div").classes("forecast-line").style(
            f"position: absolute; left: {from_name(span[0] * width)};"
            f" width: {max(span[1] * width, 2):.1f}px; top: {BAR_TOP_PX + BAR_HEIGHT_PX // 2}px"
        ).mark(f"forecast-line-{key}-{ti}")
        ui.label(forecast_text(forecast)).classes("forecast-label").style(
            f"position: absolute; left: {from_name((span[0] + span[1]) * width + 4)};"
            f" top: {BAR_TOP_PX + 2}px"
        ).mark(f"forecast-label-{key}-{ti}")
```
棒の描画で、`trial_overlay` の呼び出しの `if/else` として:
```python
                if (result := self.trial_results.get(task.id)) is not None:
                    self.trial_overlay(...)
                elif self.options.show_alerts:
                    self.forecast_overlay(key, ti, task, columns, width)
```
警告ホバー(~2766 の `name.tooltip(warning.hint())`)は `warning.hint(f.end if (f := self.forecast_of(task)) else None)`。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_forecast_view.py test/test_pace.py test/test_gantt.py test/test_delay_response_view.py -q` / Expected: PASS。(`late_task` の `try_crew` の呼び出し・`opened` の使い方は `test_delay_response_view.py::test_the_ghost_of_an_overdue_task_starts_today_not_at_the_task_start` に倣う。)

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: ガントチャートに完了見込みの点線と文言を出す(要望 133)"`

---

### Task 5: 下部パネル・ダッシュボードの遅れの一覧

**Files:**
- Modify: `src/projectapp/bottom_info.py`(`task_detail` の `完了予定` の次に行、`_notes` のホバー)
- Modify: `src/projectapp/dashboard.py`(`OverdueRow.forecast`、`summarize_progress`)、`src/projectapp/dashboard_view.py`(~1158)
- Test: `test/test_bottom_info.py`・`test/test_dashboard.py`・`test/test_forecast_view.py`(追記)

**Interfaces:**
- Consumes: `forecast_end`・`Forecast.days_later`・`forecast_text` ではなく下部パネル用に `forecast_line(forecast) -> str`(`bottom_info.py`。`11/16(+3 日)` の形。`完了見込み` はラベル側)。
- Produces: `OverdueRow(..., forecast: datetime | None = None)`(末尾に追加。既存の生成箇所は変えない)。

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_bottom_info.py
def test_detail_has_a_forecast_line_under_the_planned_end_when_late() -> None:
    from datetime import date, datetime

    from projectapp.bottom_info import task_detail
    from projectapp.models import Assignee, Project, Section, Task
    from projectapp.timeline import Schedule

    task = Task("a", id="ta", planned_start=datetime(2026, 11, 2, 9),
                effort_hours=20.0, assignees=[Assignee("田中")])
    project = Project(name="p", base_date=datetime(2026, 11, 2, 9),
                      sections=[Section("s", tasks=[task])])
    now = datetime(2026, 11, 20, 10)
    detail = task_detail(task, project, {}, now, Schedule(project, {}))
    labels = [label for label, _ in detail.lines]
    assert "完了見込み" in labels
    assert labels.index("完了見込み") == labels.index("完了予定") + 1
    value = dict(detail.lines)["完了見込み"]
    assert "(+" in value  # 日数の差


def test_detail_has_no_forecast_line_when_nothing_to_forecast() -> None:
    ...  # 進捗なし・遅れなし(now を開始の前)で "完了見込み" がない
```
(2 つ目は同じ組み立てで `now = datetime(2026, 11, 1, 10)` とし `assert "完了見込み" not in labels` を書く。)

```python
# test/test_dashboard.py
def test_overdue_rows_carry_the_forecast() -> None:
    # 予定超過のタスク 1 件の Project で summarize_progress を呼び、
    # progress.overdue[0].forecast が now より後であること
    ...
```
具体形(既存の `test_dashboard.py` の overdue のテストの組み立てに合わせる): 予定超過のタスクを 1 件作り `row = summarize_progress(project, {}, now).overdue[0]` として `assert row.forecast is not None and row.forecast > now`。完了済み(DONE)は一覧に出ないので対象外。

```python
# test/test_forecast_view.py に追記
async def test_dashboard_overdue_row_shows_the_forecast(
    user: User, tmp_path: Path
) -> None:
    view = await put(user, tmp_path, late_task())
    view.show_dashboard()  # 既存のダッシュボードへ切り替える操作に合わせる
    await user.should_see(marker="dashboard-overdue-forecast-0")
```
(ダッシュボードの切り替えは `test_dashboard_view.py` の既存の開き方に倣う。)

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_bottom_info.py test/test_dashboard.py test/test_forecast_view.py -q` / Expected: FAIL

- [ ] **Step 3: 実装**

`bottom_info.py`:
```python
def _forecast_value(forecast: Forecast) -> str:
    text = f"{forecast.end:%m/%d}"
    days = forecast.days_later
    if days is None or days == 0:
        return text
    return f"{text}(+{days} 日)" if days > 0 else f"{text}(−{-days} 日)"
```
`task_detail` で `lines += [...]` の `完了予定` の要素の後に、見込みがあれば `("完了見込み", _forecast_value(f))` を挿入(リストを 2 段に分けてよい)。`f = forecast_end(task, project, holidays, now, schedule)` を `task_detail` の先頭近くで 1 回だけ呼び、`_notes(..., forecast=f)` にも渡して `pace.hint(f.end if f else None)` とする。

`dashboard.py`: `OverdueRow` に `forecast: datetime | None = None` を末尾に追加。`summarize_progress` の `overdue.append(OverdueRow(entry.label, assignee_label(task), limit, tuple(task.assignee_names)))` を、

```python
            predicted = forecast_end(task, entry.project, holidays, now, entry.schedule)
            overdue.append(
                OverdueRow(
                    entry.label,
                    assignee_label(task),
                    limit,
                    tuple(task.assignee_names),
                    predicted.end if predicted else None,
                )
            )
```
`dashboard_view.py`(~1158): 名前ラベルと担当チップの間に
```python
                    if row.forecast is not None:
                        ui.label(f"見込み {row.forecast:%m/%d}").classes(
                            "text-grey text-caption"
                        ).mark(f"dashboard-overdue-forecast-{index}")
```

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_bottom_info.py test/test_dashboard.py test/test_dashboard_view.py test/test_forecast_view.py -q` / Expected: PASS

- [ ] **Step 5: Commit** — `git add -A src test && git commit -m "feat: 下部パネルとダッシュボードの遅れの一覧に完了見込みを出す(要望 133)"`

---

### Task 6: 性能・仕上げ・文書

**Files:**
- Test: `test/test_forecast.py`(性能・確定との整合を追記)
- Modify: `.claude/spec/concept.md`・`.claude/spec/gantt.md`・`.claude/spec/dashboard.md`、`docs/development.md`、`docs/requests.md`
- Create: `docs/samples/完了見込みの確認.json`

- [ ] **Step 1: 失敗しうるテストを足す**

```python
def test_300_tasks_forecast_in_under_a_tenth_of_a_second() -> None:
    import time

    project, _ = sample()
    tasks = [
        Task(f"t{i}", id=f"t{i}", planned_start=START, effort_hours=40.0,
             assignees=[Assignee("田中")], progress=10)
        for i in range(300)
    ]
    project.sections[0].tasks = tasks
    schedule = Schedule(project, HOLIDAYS)
    now = datetime(2026, 11, 9, 10)
    began = time.perf_counter()
    for task in tasks:
        forecast_end(task, project, HOLIDAYS, now, schedule)
    assert time.perf_counter() - began < 0.1


def test_confirmed_forecast_matches_the_trial_when_added_at_a_week_boundary() -> None:
    from projectapp.crew_trial import TrialCrew, confirmed, evaluate

    project, task = sample()
    now = datetime(2026, 11, 20, 10)  # 予定超過
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 30))  # 開始(11/2)から 4 週後の週頭
    result = evaluate(task, project, HOLIDAYS, schedule, trial, now)
    done = confirmed(task, project, HOLIDAYS, schedule, trial)
    assert result is not None and done is not None and result.trial_end is not None
    after = forecast_end(done, project, HOLIDAYS, now, schedule)
    assert after is not None
    assert after.end == result.trial_end
```
(最後のテストが落ちる場合は、週の格子の違い(試算は今日から・確定後は開始から)が原因。台帳に Ruling を書き、増員日が「今日から数えた週頭」かつ「開始から数えた週頭」の両方に当たる値(今日 11/20 → 11/23 は開始 11/2 の格子では 3 週後の週頭ではない)を選び直す。)

- [ ] **Step 2: 実行** — Run: `uv run pytest test/test_forecast.py -q` / Expected: PASS(性能が不安定なら閾値でなく実装を見直す)

- [ ] **Step 3: 文書** — 
  - `.claude/spec/concept.md`: 「完了見込み」の定義(今日からの残りの工数を今の担当で消化して終わる日。当初の完了予定とは別。進捗情報がなければ予定超過か警告のときだけ。保存しない)。
  - `.claude/spec/gantt.md`: 棒の灰青の点線と `見込み m/d(+N 日)`(隠す条件)・警告ホバー・下部パネルの行。
  - `.claude/spec/dashboard.md`: 遅れの一覧の `見込み m/d`。
  - `docs/development.md`: `forecast.py` と `calc_end` の `weeks_start`。
  - `docs/requests.md`: 要望 133 を「対応済み」にし、実績(共通化で 132 の試算と一致・限界)を書く。
  - `docs/samples/完了見込みの確認.json`: `cp docs/samples/遅延対応の確認.json docs/samples/完了見込みの確認.json`(予定超過・警告のタスクが入っている)。`~/.projectapp` へのコピーは利用者に確認してから。
  - 設計書 `2026-11-08-completion-forecast-design.md` の §2 担当の項に、週の格子の扱い(週ごとの担当のあるタスクは開始から、ないタスクは今日から)を 1 行足す。

- [ ] **Step 4: 完了時の検証** — Run: `uv run pytest -m smoke`(失敗時のみ `uv run pytest -n auto`)→ `uvx ruff check` → `uvx ruff format src test` → `uvx ty check src` / Expected: すべて成功。

- [ ] **Step 5: Commit** — `git add -A docs test src .claude && git commit -m "docs: 完了見込み(要望 133)の仕様・開発文書・確認用データを更新する"`

---

## Self-Review

- **Spec coverage:** §2 計算 → Task 1・2、132 共通化 → Task 3、§3 ガント → Task 4、下部パネル・ダッシュボード・警告ホバー → Task 4・5、§5 テスト(純粋関数・`weeks_start` 既定不変・警告 ⇒ 見込み > 予定・132 一致・画面・性能)→ Task 1〜6、§6 文書 → Task 6。確定後の見込みと試算の一致は Task 6。
- **Placeholder scan:** Task 5 の `test_dashboard.py` / 2 つ目の下部パネルのテストは組み立てを文章で指示している(既存テストの組み立てに依存するため)。実装者は同ファイルの overdue の既存テストの組み立てを複製して書く。
- **Type consistency:** `forecast_end(..., extra_crew: tuple[tuple[str, ...], date] | None)`、`Forecast.end/planned_end/days_later`、`OverdueRow.forecast: datetime | None`、`Pace.hint(forecast: datetime | None)`、マーカー名は Task 4 の定義と Task 5 で一致。
- **Review Focus の対応:** 1 → Task 2 の最初のテスト、2 → Task 2 の警告テスト、3 → Task 3、4 → Task 2 の週ごとのテスト、5 → Task 4 のテストと Task 6 の性能。
