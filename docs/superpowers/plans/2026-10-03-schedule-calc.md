# 日程計算 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **コミットについて:** ユーザーから許可が出るまでコミットしない。各タスク末尾の Commit ステップは、許可が出てから実施する(許可前は `git status` で変更を確認するだけにする)。

**Goal:** 開始日時と工数から終了日時を稼働日ベースで算出して保存時に補完し、予定を超えた未完了のタスク行を赤系の背景で表示する。

**Architecture:** 算出と判定は NiceGUI に依存しない純粋関数(`timeline.py`)にする。`MainView` が保存前に `fill_end` を通し、`GanttChart` は再描画のたびに現在日時を取得して `is_overdue` で行の背景を決める。始業時刻は `Project.work_start` として保存・復元する。

**Tech Stack:** Python 3.13、NiceGUI 3.17、pytest / pytest-asyncio / pytest-cov、ty、uv

**Spec:** `docs/superpowers/specs/2026-10-03-schedule-calc-design.md`

## Global Constraints

- Python 3.13 以上。パッケージャーは uv。UI 言語は日本語。
- すべての関数に型引数と戻り値の型ヒントを付ける。型チェックは `uvx ty check src`。
- コメントの説明は多くても3行以内。コードは PEP8 と The Zen of Python に従う。
- テストは pytest、カバレッジは pytest-cov。テストは `test/` に置く。
- 稼働日は月〜金で、祝日でない日。1日の稼働枠は始業時刻から `Project.daily_hours`(既定 6.5h)時間で、連続(昼休みなし)。始業時刻は `Project.work_start`(既定 9:00)。
- 終了日時は、開始あり・終了なし・工数 > 0 のときだけ算出する。手で入れた終了は上書きしない。
- 予定超過は「終了あり・状態が `Status.DONE` でない・現在日時が終了より後」。バーの色は変えず、タスク行の背景だけを薄い赤(`rgba(239, 83, 80, 0.18)`)にする。
- 範囲外(作らない): 実績の入力と実績に基づく判定、稼働可能時間・始業時刻の設定画面、見積もりのバッファ換算、リソース割り当て比率、定期的な自動再描画。

## Review Focus

仕様が黙っているが、利用者が踏みやすい入力・状態。各行は、担当タスクのテストで固定する。

1. 開始が稼働枠の外(始業前・終業後)や、土日祝の非稼働日: 次の稼働日の始業から数える(Task 2)。
2. 工数が稼働枠ちょうど・整数倍(6.5h、13h): 終了は枠の終端で、翌日の始業にならない(Task 2)。
3. 祝日と土日が続く連休、年またぎをまたぐ長い工数(Task 2)。
4. 終了を手入力したタスクや、編集で工数だけを変えたタスク: 終了は自動では変わらない。終了を空にして保存すると再計算される(Task 4)。
5. `daily_hours` が 0 以下・24 超、工数が 0・負、開始なし: 例外にせず終了を空のままにする(Task 2)。

---

## File Structure

| ファイル | 操作 | 責務 |
|---|---|---|
| `src/projectapp/models.py` | 変更 | `Project.work_start` を追加 |
| `src/projectapp/storage.py` | 変更 | `work_start` の保存・復元 |
| `src/projectapp/timeline.py` | 変更 | `is_workday`、`calc_end`、`fill_end`、`is_overdue` |
| `src/projectapp/gantt.py` | 変更 | 予定超過の行の背景、現在日時の注入 |
| `src/projectapp/views.py` | 変更 | 保存前の終了補完 |
| `test/test_storage.py` | 変更 | `work_start` のテスト |
| `test/test_timeline.py` | 変更 | 純粋関数のテスト |
| `test/test_gantt.py` | 変更 | 赤背景のテスト |
| `test/test_views.py` | 変更 | 補完のテスト |
| `docs/development.md`、設計書 | 変更 | 記述の更新 |

---

### Task 1: 始業時刻の保存(models.py / storage.py)

**Files:**
- Modify: `src/projectapp/models.py`
- Modify: `src/projectapp/storage.py`
- Test: `test/test_storage.py`

**Interfaces:**
- Consumes: 既存の `Project`、`save_project`、`load_project`
- Produces: `Project.work_start: time`(既定 `time(9, 0)`)。保存は ISO 形式の文字列(例 `"09:00:00"`)。`work_start` のない古いファイルは `time(9, 0)` で読む。

- [ ] **Step 1: Write the failing test**

`test/test_storage.py` の先頭の import の `from datetime import date, datetime` を `from datetime import date, datetime, time` にして、末尾に追加:

```python
def test_work_start_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", work_start=time(8, 30))
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.work_start == time(8, 30)


def test_file_without_work_start_loads_with_the_default(tmp_path: Path) -> None:
    path = save_project(Project("old"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["work_start"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).work_start == time(9, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_storage.py -q`
Expected: FAIL(`TypeError: Project.__init__() got an unexpected keyword argument 'work_start'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/models.py`: import を `from datetime import date, datetime, time` に変え、定数と項目を追加する。

```python
DEFAULT_DAILY_HOURS = 6.5
DEFAULT_WORK_START = time(9, 0)
```

`Project` の `daily_hours` の下に追加:

```python
    work_start: time = DEFAULT_WORK_START  # 稼働日の始業時刻
```

`src/projectapp/storage.py`: import を `from datetime import date, datetime, time` にし、`_encode` の判定を変更し、`load_project` に項目を足す。

```python
def _encode(value: object) -> str:
    """JSONにない日付・時刻型をISO形式の文字列にする。"""
    if isinstance(value, (date, time)):  # datetimeもdateのサブクラス
        return value.isoformat()
    raise TypeError(f"{type(value).__name__}はJSONに保存できません")
```

`load_project` の `Project(...)` 呼び出しに追加:

```python
        work_start=time.fromisoformat(raw.get("work_start", "09:00:00")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_storage.py
git commit -m "feat: 始業時刻(work_start)をプロジェクトに追加"
```

---

### Task 2: 日程計算の純粋関数(timeline.py)

**Files:**
- Modify: `src/projectapp/timeline.py`
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: `Project.daily_hours`、`Project.work_start`(Task 1)、`Task`、`Status`
- Produces:
  - `is_workday(day: date, holidays: dict[date, str]) -> bool`
  - `calc_end(start: datetime, effort_hours: float, daily_hours: float, work_start: time, holidays: dict[date, str]) -> datetime | None`(算出しない場合は `None`)
  - `fill_end(task: Task, project: Project, holidays: dict[date, str]) -> Task`
  - `is_overdue(task: Task, now: datetime) -> bool`

- [ ] **Step 1: Write the failing test**

`test/test_timeline.py` の import を次のように変える(`time` と新しい関数を追加):

```python
from datetime import date, datetime, time

import pytest

from projectapp.models import Project, Section, Status, Task
from projectapp.timeline import (
    Band,
    Scale,
    bar_span,
    build_columns,
    calc_end,
    fill_end,
    is_overdue,
    is_workday,
    month_bands,
    year_bands,
)
```

(既存の `Band, Scale, bar_span, build_columns, month_bands, year_bands` の import 行と、`from projectapp.models import Project, Section, Task` の行を、上のものに置き換える。)

末尾に追加:

```python
START = time(9, 0)
NO_HOLIDAYS: dict[date, str] = {}
OCT_12 = {date(2026, 10, 12): "スポーツの日"}  # 月曜


def end_of(start: datetime, effort: float, holidays: dict[date, str] = NO_HOLIDAYS) -> datetime | None:
    return calc_end(start, effort, 6.5, START, holidays)


def test_is_workday() -> None:
    assert is_workday(date(2026, 10, 5), NO_HOLIDAYS)  # 月
    assert not is_workday(date(2026, 10, 10), NO_HOLIDAYS)  # 土
    assert not is_workday(date(2026, 10, 11), NO_HOLIDAYS)  # 日
    assert not is_workday(date(2026, 10, 12), OCT_12)  # 祝日


def test_calc_end_spec_example_over_a_weekend() -> None:
    # 金曜9:00・15h・6.5h/日 → 金6.5h + 月6.5h + 火2.0h
    assert end_of(datetime(2026, 10, 9, 9), 15) == datetime(2026, 10, 13, 11)


def test_calc_end_skips_holidays() -> None:
    # 月曜が祝日なら、金6.5h + 火6.5h + 水2.0h
    assert end_of(datetime(2026, 10, 9, 9), 15, OCT_12) == datetime(2026, 10, 14, 11)


def test_calc_end_exact_slot_ends_at_the_slot_end_not_next_morning() -> None:
    assert end_of(datetime(2026, 10, 5, 9), 6.5) == datetime(2026, 10, 5, 15, 30)
    assert end_of(datetime(2026, 10, 5, 9), 13) == datetime(2026, 10, 6, 15, 30)


def test_calc_end_starting_inside_the_slot() -> None:
    assert end_of(datetime(2026, 10, 5, 10), 2) == datetime(2026, 10, 5, 12)
    # 月14:00から3h: 当日1.5h + 火9:00から1.5h
    assert end_of(datetime(2026, 10, 5, 14), 3) == datetime(2026, 10, 6, 10, 30)


def test_calc_end_before_the_work_start_counts_from_the_work_start() -> None:
    assert end_of(datetime(2026, 10, 5, 7), 1) == datetime(2026, 10, 5, 10)


def test_calc_end_after_the_slot_starts_next_workday() -> None:
    assert end_of(datetime(2026, 10, 5, 16), 1) == datetime(2026, 10, 6, 10)


def test_calc_end_starting_on_a_non_workday() -> None:
    assert end_of(datetime(2026, 10, 10, 10), 1) == datetime(2026, 10, 12, 10)  # 土
    assert end_of(datetime(2026, 10, 10, 10), 1, OCT_12) == datetime(2026, 10, 13, 10)


def test_calc_end_holiday_after_a_workday_slot() -> None:
    # 金15:00から1h: 当日0.5h + 月が祝日なので火9:00から0.5h
    assert end_of(datetime(2026, 10, 9, 15), 1, OCT_12) == datetime(2026, 10, 13, 9, 30)


def test_calc_end_across_the_new_year() -> None:
    holidays = {date(2027, 1, 1): "元日"}
    # 水12/30・木12/31で13h、残り6.5hは金1/1祝・土日を飛ばして月1/4
    assert end_of(datetime(2026, 12, 30, 9), 19.5, holidays) == datetime(2027, 1, 4, 15, 30)


def test_calc_end_with_another_work_start() -> None:
    assert calc_end(datetime(2026, 10, 5, 8, 30), 6.5, 6.5, time(8, 30), NO_HOLIDAYS) == datetime(
        2026, 10, 5, 15, 0
    )


@pytest.mark.parametrize("effort", [0, -1, 0.0])
def test_calc_end_without_positive_effort_is_none(effort: float) -> None:
    assert end_of(datetime(2026, 10, 5, 9), effort) is None


@pytest.mark.parametrize("daily", [0, -1, 24.5])
def test_calc_end_with_unusable_daily_hours_is_none(daily: float) -> None:
    assert calc_end(datetime(2026, 10, 5, 9), 8, daily, START, NO_HOLIDAYS) is None


def test_fill_end_fills_an_empty_end() -> None:
    project = Project("p")
    task = Task("t", start=datetime(2026, 10, 9, 9), effort_hours=15.0)
    filled = fill_end(task, project, NO_HOLIDAYS)
    assert filled.end == datetime(2026, 10, 13, 11)
    assert task.end is None  # 元のTaskは変えない


def test_fill_end_keeps_a_manual_end() -> None:
    manual = datetime(2026, 10, 30, 18)
    task = Task("t", start=datetime(2026, 10, 9, 9), end=manual, effort_hours=15.0)
    assert fill_end(task, Project("p"), NO_HOLIDAYS).end == manual


@pytest.mark.parametrize(
    "task",
    [Task("no start", effort_hours=8.0), Task("no effort", start=datetime(2026, 10, 9, 9))],
)
def test_fill_end_leaves_tasks_it_cannot_compute(task: Task) -> None:
    assert fill_end(task, Project("p"), NO_HOLIDAYS) is task


NOW = datetime(2026, 10, 8, 12)


def test_is_overdue() -> None:
    late = Task("t", end=datetime(2026, 10, 8, 11, 59), status=Status.RUNNING)
    assert is_overdue(late, NOW)
    assert not is_overdue(Task("t", end=NOW, status=Status.RUNNING), NOW)  # ちょうどは超過でない
    assert not is_overdue(Task("t", end=datetime(2026, 10, 9)), NOW)
    assert not is_overdue(Task("t"), NOW)  # 終了なし
    assert not is_overdue(Task("t", end=datetime(2026, 10, 1), status=Status.DONE), NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_timeline.py -q`
Expected: FAIL(`ImportError: cannot import name 'calc_end' from 'projectapp.timeline'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/timeline.py`: import を次のように変える。

```python
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
```

(`from projectapp.models import Project, Task` は `from projectapp.models import Project, Status, Task` にする。)

末尾に追加:

```python
def is_workday(day: date, holidays: dict[date, str]) -> bool:
    """月〜金で祝日でない日。"""
    return day.weekday() < 5 and day not in holidays


def _next_workday(day: date, holidays: dict[date, str]) -> date:
    day += timedelta(days=1)
    while not is_workday(day, holidays):
        day += timedelta(days=1)
    return day


def calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
) -> datetime | None:
    """稼働日の稼働枠(始業から連続daily_hours時間)に工数を割り当てた終了日時。

    工数が0以下、またはdaily_hoursが0以下・24超なら算出せずNone。
    """
    if effort_hours <= 0 or not 0 < daily_hours <= 24:
        return None
    slot = timedelta(hours=daily_hours)
    day = start.date()
    if is_workday(day, holidays) and start < datetime.combine(day, work_start) + slot:
        cursor = max(start, datetime.combine(day, work_start))
    else:
        cursor = datetime.combine(_next_workday(day, holidays), work_start)
    remaining = timedelta(hours=effort_hours)
    while True:
        available = datetime.combine(cursor.date(), work_start) + slot - cursor
        if remaining <= available:
            return cursor + remaining
        remaining -= available
        cursor = datetime.combine(_next_workday(cursor.date(), holidays), work_start)


def fill_end(task: Task, project: Project, holidays: dict[date, str]) -> Task:
    """開始あり・終了なし・工数ありのタスクに、算出した終了を入れて返す。"""
    if task.start is None or task.end is not None:
        return task
    end = calc_end(task.start, task.effort_hours, project.daily_hours, project.work_start, holidays)
    return task if end is None else replace(task, end=end)


def is_overdue(task: Task, now: datetime) -> bool:
    """終了予定を過ぎていて、状態が「終了」でない。"""
    return task.end is not None and task.status is not Status.DONE and now > task.end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_timeline.py -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`
(特定のケースで日付が合わない場合は、`datetime(2026, 10, 5)` が月曜、`2026-10-12` が月曜であることを確認する。計算ロジックではなくテストの期待値の曜日を疑う。)

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "feat: 稼働日ベースの終了日時算出と予定超過の判定を追加"
```

---

### Task 3: 予定超過の赤背景(gantt.py)

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `timeline.is_overdue(task, now) -> bool`(Task 2)
- Produces:
  - 定数 `OVERDUE_COLOR = "rgba(239, 83, 80, 0.18)"`
  - `GanttChart(project, holidays, actions, now: Callable[[], datetime] = datetime.now)`。タスク行(`task_row` の最も外側の行)に、予定超過のときだけ `background: OVERDUE_COLOR` を付ける。

- [ ] **Step 1: Write the failing test**

`test/test_gantt.py` の import に `OVERDUE_COLOR` を足し(`from projectapp.gantt import GRID_BORDER, KIND_COLORS, OVERDUE_COLOR, GanttActions, GanttChart`)、`mount` を次のように変える:

```python
def mount(
    project: Project,
    holidays: dict[date, str] | None = None,
    now: datetime = datetime(2026, 10, 1),
) -> Recorder:
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        GanttChart(project, holidays or {}, recorder.actions, now=lambda: now).build()

    return recorder
```

(既定の `now` は、サンプルのタスク(10/5〜10/7)より前なので、既存テストに赤背景は付かない。)

末尾に追加:

```python
def row_background(user: User, marker: str) -> str | None:
    row = user.find(marker=marker).elements.pop().parent_slot.parent
    return row._style.get("background")


async def test_overdue_task_row_is_red_and_others_are_not(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-0-0") == OVERDUE_COLOR  # 終了10/7 12:00を過ぎた
    assert row_background(user, "task-0-1") is None  # 終了なし


async def test_task_not_yet_overdue_is_not_red(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 6))
    await user.open("/")
    assert row_background(user, "task-0-0") is None


async def test_done_task_is_not_red(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].status = Status.DONE
    mount(project, now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-0-0") is None


async def test_overdue_keeps_the_bar_color(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert user.find(marker="bar-0-0").elements.pop()._style["background"] == "#ff0000"


async def test_overdue_applies_to_top_level_tasks(user: User) -> None:
    mount(top_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert row_background(user, "task-top-0") == OVERDUE_COLOR
```

`test/test_gantt.py` の `from projectapp.models import Project, Section, Task` に `Status` を足す(`Project, Section, Status, Task`)。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_gantt.py -q`
Expected: FAIL(`ImportError: cannot import name 'OVERDUE_COLOR' from 'projectapp.gantt'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/gantt.py`:

import に `datetime` と `is_overdue` を足す。

```python
from datetime import date, datetime
```

```python
from projectapp.timeline import (
    Band,
    Column,
    Scale,
    bar_span,
    build_columns,
    is_overdue,
    month_bands,
    year_bands,
)
```

定数を `GRID_BORDER` の近くに追加:

```python
OVERDUE_COLOR = "rgba(239, 83, 80, 0.18)"  # 予定超過のタスク行の背景
```

`GanttChart.__init__` に `now` を追加:

```python
    def __init__(
        self,
        project: Project,
        holidays: dict[date, str],
        actions: GanttActions,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.actions = actions
        self.now = now
        self.scale = Scale.DAY
```

`task_row` の先頭の行の作成を、予定超過のときだけ背景を足す形に変える。現在の

```python
        key = "top" if si is None else si
        with ui.row().classes("items-center no-wrap gap-0").style(ROW_STYLE):
```

を、次に置き換える:

```python
        key = "top" if si is None else si
        style = ROW_STYLE
        if is_overdue(task, self.now()):
            style += f"; background: {OVERDUE_COLOR}"
        with ui.row().classes("items-center no-wrap gap-0").style(style):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: 予定超過のタスク行を赤系の背景で表示"
```

---

### Task 4: 保存時の終了補完と仕上げ(views.py)

**Files:**
- Modify: `src/projectapp/views.py`
- Modify: `docs/development.md`
- Modify: `docs/superpowers/specs/2026-10-03-schedule-calc-design.md`
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `timeline.fill_end(task, project, holidays) -> Task`(Task 2)、`GanttChart` の予定超過表示(Task 3)
- Produces: `MainView.save_task` が、保存前に `fill_end(task, self.project, self.holidays)` を通す。

- [ ] **Step 1: Write the failing test**

`test/test_views.py` の import に `from datetime import date, datetime` の `datetime` を足し(`from datetime import date, datetime`)、末尾に追加:

```python
def make_view(tmp_path: Path, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, make_transport(200, []))
        views.append(view)
        view.build()


async def test_saving_start_and_effort_fills_the_end(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].save_task(None, None, Task("a", start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    assert views[0].project.tasks[0].end == datetime(2026, 10, 13, 11)
    await user.should_see(marker="bar-top-0")


async def test_fill_end_uses_the_loaded_holidays(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].holidays = {date(2026, 10, 12): "スポーツの日"}
    views[0].save_task(None, None, Task("a", start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    assert views[0].project.tasks[0].end == datetime(2026, 10, 14, 11)


async def test_manual_end_is_kept_and_is_not_recomputed_on_edit(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    manual = datetime(2026, 10, 30, 18)
    task = Task("a", start=datetime(2026, 10, 9, 9), end=manual, effort_hours=15.0)
    views[0].save_task(None, None, task)
    views[0].save_task(None, 0, replace(task, effort_hours=1.0))  # 工数だけ変える
    assert views[0].project.tasks[0].end == manual


async def test_clearing_the_end_recomputes_it(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    task = Task("a", start=datetime(2026, 10, 9, 9), end=datetime(2026, 10, 30), effort_hours=15.0)
    views[0].save_task(None, None, task)
    views[0].save_task(None, 0, replace(task, end=None))
    assert views[0].project.tasks[0].end == datetime(2026, 10, 13, 11)


async def test_task_without_effort_keeps_an_empty_end(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    views[0].save_task(None, None, Task("a", start=datetime(2026, 10, 9, 9)))
    assert views[0].project.tasks[0].end is None
```

`test/test_views.py` の先頭の import に `from dataclasses import replace` を追加する。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_views.py -q`
Expected: FAIL(`test_saving_start_and_effort_fills_the_end` などが `assert None == datetime(...)` で失敗)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/views.py`: import に `fill_end` を足す。

```python
from projectapp.timeline import fill_end
```

`save_task` の先頭で補完する。現在の

```python
        tasks = self.tasks_in(section_index)
        if task_index is None:
```

を、次に置き換える:

```python
        task = fill_end(task, self.project, self.holidays)
        tasks = self.tasks_in(section_index)
        if task_index is None:
```

`docs/development.md` のモジュール表の `timeline.py` の行を、次に置き換える:

```markdown
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換、稼働日ベースの終了日時算出と予定超過の判定(純粋関数) |
```

設計書 `docs/superpowers/specs/2026-10-03-schedule-calc-design.md` の算出ルールの「`daily_hours` が 0 以下」の行を、次に置き換える:

```markdown
- **`daily_hours` が 0 以下、または 24 超**: 算出しない(エラーにせず終了は空のまま)。無限ループにしない。24 超は、1日の稼働枠が日をまたぐため対象外とする。
```

設計書の「データの流れ」の2番目に、1文を足す: 「終了が入っているタスクは、工数を編集しても終了を自動では変えない。終了を空にして保存すると再計算される。」

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest --cov=projectapp -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: 手動確認(実機)**

Run: `uv run projectapp`
確認すること:
- 「タスク追加」で、開始日時(金曜 9:00)と工数 15 を入れ、終了を空にして保存する。終了が火曜 11:00(その週の月曜が祝日なら水曜 11:00)になり、バーが描かれる。
- 終了を手で入れて保存したタスクは、終了が変わらない。
- 終了が現在より前で、状態が「終了」でないタスクの行が薄い赤になる。状態を「終了」にすると赤が消える。バーの色は変わらない。

- [ ] **Step 6: Commit(許可が出てから)**

```bash
git add src/projectapp/views.py test/test_views.py docs/development.md docs/superpowers/specs/2026-10-03-schedule-calc-design.md
git commit -m "feat: 保存時に開始と工数から終了日時を補完"
```

---

## Self-Review(計画の作成者による確認)

**1. 設計書の網羅**
- `Project.work_start` と保存・復元(古いファイルは 9:00): Task 1。
- 稼働日・稼働枠・開始日時の扱い・工数の消費・枠ちょうど・工数 0・`daily_hours` の不正: Task 2。
- `fill_end`(終了が空のときだけ補完、手入力を優先): Task 2、Task 4。
- 予定超過の判定(`DONE` 除外、終了なし、境界)と赤表示(行の背景、バーの色は不変): Task 2、Task 3。
- 現在日時の注入、再描画のたびの判定: Task 3(`now`)。自動の定期更新は範囲外。
- 祝日データがなければ土日だけを除く: `MainView.holidays` が `{}` のとき(Task 4 のテストは `save_cache({})` で `{}`)。
- 抜けはなし。

**2. プレースホルダーの確認:** TBD、TODO、「適切に処理する」などの記述はなし。すべてのコード手順にコードを載せた。

**3. 型・名前の整合**
- `calc_end(start, effort_hours, daily_hours, work_start, holidays) -> datetime | None` は Task 2 の定義と `fill_end` の呼び出しで一致する。
- `GanttChart(..., now: Callable[[], datetime])` は Task 3 の定義とテストの `mount` で一致する。
- `fill_end(task, project, holidays)` は Task 2 の定義と Task 4 の `save_task` で一致する。
- Task 4 のテストの `make_view` は、`MainView(tmp_path, transport)` のコンストラクタ(既存)と一致する。

**4. Review Focus:** 5項目とも担当タスクのテストにある(1: Task 2 の `before_the_work_start`、`after_the_slot`、`non_workday`、`holiday_after_a_workday_slot`、2: `exact_slot_ends`、3: `skips_holidays`、`across_the_new_year`、4: Task 4 の `manual_end_is_kept...`、`clearing_the_end_recomputes_it`、5: `without_positive_effort_is_none`、`with_unusable_daily_hours_is_none`、`fill_end_leaves_tasks_it_cannot_compute`)。

**注意:** `fill_end` は編集ダイアログの終了欄に、以前に自動で入った終了が残るため、工数だけを変えても終了は変わらない(設計書の決定どおり)。終了欄を空にして保存すると再計算される。
