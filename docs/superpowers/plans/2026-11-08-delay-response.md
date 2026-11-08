# 遅延対応(増員の試算と確定)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 遅れた分の増員を、ガントチャートに試算(表示のみ)として重ねて完了見込みを示し、確定すると `weekly_crew` に保存できるようにする(要望 132)。

**Architecture:** 試算は `crew_trial.py` の純粋関数(担当表の組み立て・完了見込み・確定時の変換)と、`MainView` が画面の中だけで持つ `TrialCrew` の辞書で表す。ガントチャートは `MainView` が計算した結果を受け取って重ね描きし、上に紫の点線枠の `遅延対応` の帯を出す。確定は通常の編集(`after_edit`)として `weekly_crew` を書き換える。

**Tech Stack:** Python 3.13、NiceGUI、pytest(NiceGUI の `User` フィクスチャ)。

**Spec:** `docs/superpowers/specs/2026-11-08-delay-response-design.md`

## Global Constraints

- ファイル形式の `version` は 21 のまま。`Project`・`Task` のフィールドを足さない。
- 試算は保存せず、`history_log.dirty_key`・元に戻す(`History`)に影響させない。確定は `views.after_edit` を通す。
- 増員日は週の境目(実効の開始から 7 日ごと)に**遅い側へ丸める**。週数の上限は `MAX_WEEKS`(52)。
- 手動指定の完了予定(`planned_end_manual` かつ `planned_end` あり)のタスクは、見込みを出さず、手動指定を優先する。
- 帯: 見出し `遅延対応`、紫系、枠線は太い点線(`3px dotted`)。赤・黄・緑は使わない(遅れ・警告・取り戻せたの色)。`遅延` を赤の意味では使わない。
- 日本語の UI 文言は設計書のとおり。marker は下記 Interfaces のとおり。
- 実装の完了時: `uv run pytest -m smoke` → `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`。smoke が失敗したときに限り `uv run pytest -n auto`。

## Review Focus

- 担当者のいないタスク・種別が通常でないタスク(まとめ・参照・チェックポイント)に試算を入れたとき、落ちずに無視される。
- 試算の対象タスクが削除された・担当が変わったあとに描き直しても落ちない(試算は捨てるか、再計算される)。
- 増員日が実効の開始より前・52 週より先のとき(前は第 1 週、先は上限で拒否)。
- 同じタスクに 2 回試算したとき、後の試算で置き換わる(増員が二重にならない)。
- 試算中に別プロジェクトへ切り替えたとき、試算が残らない。

---

### Task 1: 純粋関数 `crew_trial.py`

**Files:**
- Create: `src/projectapp/crew_trial.py`
- Test: `test/test_crew_trial.py`

**Interfaces:**
- Consumes: `models.Assignee, Task, TaskKind, Project, MAX_WEEKS, union_assignees`、`timeline.Schedule, calc_end, crew_of, effective_start, effective_end`。
- Produces:
  - `TrialCrew(task_id: str, names: tuple[str, ...], start: date)`(frozen dataclass)
  - `snap_week(anchor: date, day: date) -> int`(遅い側へ丸めた週の添字。0 始まり)
  - `trial_weeks(task: Task, trial: TrialCrew, anchor: date) -> list[list[Assignee]] | None`(週が 52 を超えるなら None)
  - `TrialResult(task_id, names, first_week, original_end, trial_end, manual)`(frozen dataclass。`days_earlier` プロパティ: 両方あるとき `(original_end.date() - trial_end.date()).days`、なければ None)
  - `evaluate(task, project, holidays, schedule, trial) -> TrialResult | None`(対象外のタスクは None)
  - `confirmed(task, project, holidays, schedule, trial) -> Task | None`(`weekly_crew` と `assignees` を書き換えたタスク。対象外は None)
  - `replace_task(project: Project, task: Task) -> bool`(同じ id のタスクを差し替える。なければ False)

- [ ] **Step 1: Write the failing tests**

```python
# test/test_crew_trial.py
from datetime import date, datetime

from projectapp.crew_trial import (
    TrialCrew,
    confirmed,
    evaluate,
    replace_task,
    snap_week,
    trial_weeks,
)
from projectapp.models import (
    MAX_WEEKS,
    Assignee,
    Member,
    Project,
    Section,
    Task,
    TaskKind,
)
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


def test_snap_week_rounds_to_the_later_week_boundary() -> None:
    anchor = date(2026, 11, 2)
    assert snap_week(anchor, date(2026, 11, 2)) == 0
    assert snap_week(anchor, date(2026, 11, 1)) == 0  # 開始より前は第 1 週
    assert snap_week(anchor, date(2026, 11, 3)) == 1  # 週の途中は次の週頭
    assert snap_week(anchor, date(2026, 11, 9)) == 1  # ちょうど境目
    assert snap_week(anchor, date(2026, 11, 10)) == 2


def test_trial_weeks_adds_members_from_the_snapped_week_and_carries_on() -> None:
    _, task = sample()
    weeks = trial_weeks(task, TrialCrew("ta", ("鈴木",), date(2026, 11, 10)), date(2026, 11, 2))
    assert weeks is not None
    names = [[a.name for a in w] for w in weeks]
    assert names == [["田中"], ["田中"], ["田中", "鈴木"]]


def test_trial_weeks_keeps_existing_weekly_crew_and_does_not_duplicate() -> None:
    _, task = sample(
        weekly_crew=[[Assignee("田中")], [Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]
    )
    weeks = trial_weeks(task, TrialCrew("ta", ("鈴木",), date(2026, 11, 9)), date(2026, 11, 2))
    assert weeks is not None
    assert [[a.name for a in w] for w in weeks] == [
        ["田中"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
    ]


def test_trial_weeks_refuses_beyond_the_week_limit() -> None:
    _, task = sample()
    far = date(2026, 11, 2).fromordinal(date(2026, 11, 2).toordinal() + 7 * MAX_WEEKS + 1)
    assert trial_weeks(task, TrialCrew("ta", ("鈴木",), far), date(2026, 11, 2)) is None


def test_evaluate_shows_an_earlier_end_with_more_people() -> None:
    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    result = evaluate(task, project, HOLIDAYS, schedule, TrialCrew("ta", ("鈴木",), date(2026, 11, 9)))
    assert result is not None
    assert result.trial_end is not None and result.original_end is not None
    assert result.trial_end < result.original_end
    assert (result.days_earlier or 0) > 0
    assert result.first_week == 1


def test_confirmed_task_ends_where_the_trial_said() -> None:
    project, task = sample()
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    result = evaluate(task, project, HOLIDAYS, schedule, trial)
    saved = confirmed(task, project, HOLIDAYS, schedule, trial)
    assert result is not None and saved is not None
    assert [a.name for a in saved.assignees] == ["田中", "鈴木"]
    assert replace_task(project, saved)
    assert effective_end(saved, project, HOLIDAYS) == result.trial_end


def test_manual_end_wins_and_has_no_trial_end() -> None:
    project, task = sample(planned_end=datetime(2026, 11, 20, 18), planned_end_manual=True)
    schedule = Schedule(project, HOLIDAYS)
    result = evaluate(task, project, HOLIDAYS, schedule, TrialCrew("ta", ("鈴木",), date(2026, 11, 9)))
    assert result is not None
    assert result.manual and result.trial_end is None


def test_unsuitable_tasks_are_ignored() -> None:
    project, task = sample(assignees=[])
    schedule = Schedule(project, HOLIDAYS)
    trial = TrialCrew("ta", ("鈴木",), date(2026, 11, 9))
    assert evaluate(task, project, HOLIDAYS, schedule, trial) is None
    project2, summary = sample(kind=TaskKind.SUMMARY)
    assert evaluate(summary, project2, HOLIDAYS, Schedule(project2, HOLIDAYS), trial) is None
    assert confirmed(summary, project2, HOLIDAYS, Schedule(project2, HOLIDAYS), trial) is None


def test_replace_task_returns_false_for_an_unknown_id() -> None:
    project, task = sample()
    other = Task("x", id="nope")
    assert not replace_task(project, other)
    assert replace_task(project, task)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_crew_trial.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'projectapp.crew_trial'`

- [ ] **Step 3: Write the implementation**

```python
# src/projectapp/crew_trial.py
"""遅延対応(要望 132): 遅れた分の増員の試算。NiceGUI に依存しない純粋関数。

試算は保存しない。確定すると `Task.weekly_crew` に乗る(ファイル形式は変えない)。
"""

from dataclasses import dataclass, replace
from datetime import date, datetime

from projectapp.models import (
    MAX_WEEKS,
    Assignee,
    Project,
    Section,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.timeline import (
    Schedule,
    calc_end,
    crew_of,
    effective_end,
    effective_start,
)


@dataclass(frozen=True)
class TrialCrew:
    """だれを・どのタスクに・いつから増員するかの試算(画面の中だけ)。start は丸める前の指定日。"""

    task_id: str
    names: tuple[str, ...]
    start: date


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    names: tuple[str, ...]
    first_week: int  # 増員が始まる週(0 始まり)
    original_end: datetime | None
    trial_end: datetime | None  # 手動指定の完了予定のタスクは None
    manual: bool

    @property
    def days_earlier(self) -> int | None:
        if self.original_end is None or self.trial_end is None:
            return None
        return (self.original_end.date() - self.trial_end.date()).days


def snap_week(anchor: date, day: date) -> int:
    """増員日を、実効の開始から 7 日ごとの週の境目に、遅い側へ丸めた週の添字(0 始まり)。開始より前は第 1 週。"""
    days = (day - anchor).days
    return 0 if days <= 0 else -(-days // 7)


def trial_weeks(task: Task, trial: TrialCrew, anchor: date) -> list[list[Assignee]] | None:
    """今の担当に増員分を足した週ごとの担当。週数が上限を超えるなら None。"""
    first = snap_week(anchor, trial.start)
    if first >= MAX_WEEKS:
        return None
    base = [list(w) for w in task.weekly_crew] or [list(task.assignees)]
    while len(base) <= first:
        base.append([replace(a) for a in base[-1]])
    weeks: list[list[Assignee]] = []
    for number, week in enumerate(base):
        crew = [replace(a) for a in week]
        if number >= first:
            present = {a.name for a in crew}
            crew += [Assignee(n) for n in trial.names if n not in present]
        weeks.append(crew)
    return weeks


def _target(task: Task) -> bool:
    return task.kind is TaskKind.NORMAL and bool(task.assignees or task.weekly_crew)


def _manual(task: Task) -> bool:
    return task.planned_end is not None and task.planned_end_manual


def evaluate(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    trial: TrialCrew,
) -> TrialResult | None:
    """増員後の完了見込み。対象外(担当なし・通常でない・開始なし・上限超え)は None。"""
    if not _target(task):
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    weeks = trial_weeks(task, trial, start.date())
    if weeks is None:
        return None
    original = effective_end(task, project, holidays, schedule)
    first = snap_week(start.date(), trial.start)
    if _manual(task):
        return TrialResult(task.id, trial.names, first, original, None, True)
    crews = [
        crew_of(week, project.members, project.parameters, task.parameters, project.ratio_limits)
        for week in weeks
    ]
    end = calc_end(
        start,
        task.total_effort,
        project.daily_hours,
        project.work_start,
        holidays,
        weeks=crews,
    )
    return TrialResult(task.id, trial.names, first, original, end, False)


def confirmed(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    trial: TrialCrew,
) -> Task | None:
    """試算を確定したタスク(weekly_crew に乗せ、assignees は和集合)。対象外は None。"""
    if not _target(task):
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    weeks = trial_weeks(task, trial, start.date())
    if weeks is None:
        return None
    return replace(task, weekly_crew=weeks, assignees=union_assignees(weeks))


def _replace_in(section_tasks: list[Task], task: Task) -> bool:
    for index, existing in enumerate(section_tasks):
        if existing.id == task.id:
            section_tasks[index] = task
            return True
    return False


def _replace_in_sections(sections: list[Section], task: Task) -> bool:
    for section in sections:
        if _replace_in(section.tasks, task) or _replace_in_sections(section.sections, task):
            return True
    return False


def replace_task(project: Project, task: Task) -> bool:
    """同じ id のタスクを差し替える。なければ False。"""
    return _replace_in(project.tasks, task) or _replace_in_sections(project.sections, task)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_crew_trial.py -v`
Expected: PASS(全件)。`Member`・`Project` のコンストラクタが違って落ちたときは、`test/test_timeline.py` の組み立てに合わせてテストの `sample` を直す(ledger に Ruling を残す)。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/crew_trial.py test/test_crew_trial.py
git commit -m "feat: 増員の試算と確定の純粋関数を足す(要望 132)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `MainView` の試算の保持・確定・保存時の確認

**Files:**
- Modify: `src/projectapp/views.py`(`__init__` 付近、`after_edit`、`write`、プロジェクト切り替えの入口)
- Test: `test/test_delay_response.py`(新規)

**Interfaces:**
- Consumes: Task 1 の `TrialCrew, evaluate, confirmed, replace_task`。
- Produces(`MainView`):
  - `trials: dict[str, TrialCrew]`(task id → 試算)
  - `try_crew(task_id: str, names: list[str], start: date) -> bool`(対象外・上限超えなら通知して False。同じタスクは置き換え)
  - `drop_trial(task_id: str) -> None`、`clear_trials() -> None`
  - `trial_results() -> dict[str, TrialResult]`(今の計算結果)
  - `confirm_trials() -> int`(確定した件数。通常の編集として 1 回の `after_edit`)
  - `save_project_clicked` は、試算が残っていれば `open_trial_save_dialog` を出す(Task 5)。この Task では保存の確認を Task 5 に残し、試算の保持・確定・やめるだけを作る。
  - 試算は、プロジェクトを切り替える・開き直す・新規を作る入口で `clear_trials()` する(`reset_history` の中で呼ぶ)。

- [ ] **Step 1: Write the failing tests**

```python
# test/test_delay_response.py
from datetime import date, datetime
from pathlib import Path

from nicegui import ui
from nicegui.testing import User

from projectapp import history_log
from projectapp.cache import save_cache
from projectapp.models import Assignee, Member, Task
from projectapp.views import MainView
from test.test_views import make_view  # 既存の補助

START = datetime(2026, 11, 2, 9)


def seed(view: MainView) -> None:
    view.project.members = [Member("田中"), Member("鈴木")]
    view.project.tasks.append(
        Task("a", id="ta", planned_start=START, effort_hours=60.0, assignees=[Assignee("田中")])
    )
    view.after_edit()
    view.mark_clean()


async def test_a_trial_changes_the_result_but_not_the_file_or_dirty_state(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    before = history_log.dirty_key(view.project)
    assert view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    assert not view.is_dirty()
    assert history_log.dirty_key(view.project) == before
    assert view.project.tasks[0].weekly_crew == []  # データは変わらない
    result = view.trial_results()["ta"]
    assert result.trial_end is not None and result.original_end is not None
    assert result.trial_end < result.original_end
    assert view.history.undo(view.project) is None  # 元に戻す履歴に入らない


async def test_the_same_task_is_replaced_not_doubled(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.try_crew("ta", ["鈴木"], date(2026, 11, 16))
    assert len(view.trials) == 1
    assert view.trials["ta"].start == date(2026, 11, 16)


async def test_an_unsuitable_task_is_refused(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.project.tasks.append(Task("b", id="tb", planned_start=START, effort_hours=8.0))
    view.after_edit()
    assert not view.try_crew("tb", ["鈴木"], date(2026, 11, 9))  # 担当なし
    assert not view.try_crew("nope", ["鈴木"], date(2026, 11, 9))  # 存在しない
    assert view.trials == {}


async def test_confirming_writes_weekly_crew_as_one_undoable_edit(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    expected = view.trial_results()["ta"].trial_end
    assert view.confirm_trials() == 1
    assert view.trials == {}
    assert view.is_dirty()
    task = view.project.tasks[0]
    assert [a.name for a in task.assignees] == ["田中", "鈴木"]
    assert len(task.weekly_crew) == 2
    from projectapp.timeline import effective_end

    assert effective_end(task, view.project, view.holidays) == expected
    view.undo()
    assert view.project.tasks[0].weekly_crew == []


async def test_dropping_and_clearing_remove_trials(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.drop_trial("ta")
    assert view.trials == {}
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.clear_trials()
    assert view.trials == {}
    assert view.trial_results() == {}


async def test_a_trial_for_a_deleted_task_is_dropped_on_redraw(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.project.tasks.clear()
    view.after_edit()
    assert view.trial_results() == {}
    assert view.trials == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_delay_response.py -v`
Expected: FAIL with `AttributeError: 'MainView' object has no attribute 'try_crew'`

- [ ] **Step 3: Implement in `views.py`**

`__init__` で `self.trials: dict[str, TrialCrew] = {}`(`self.dashboard_catch_up = CatchUp()` の近く)。メソッドを `toggle_weeks` の前に足す:

```python
    # --- 遅延対応(要望 132): 増員の試算 -------------------------------------
    def try_crew(self, task_id: str, names: list[str], start: date) -> bool:
        """増員の試算を入れる(同じタスクは置き換え)。保存せず、元に戻す履歴にも入れない。"""
        task = self.project.task_map().get(task_id)
        trial = TrialCrew(task_id, tuple(names), start)
        schedule = Schedule(self.project, self.holidays)
        if (
            task is None
            or not names
            or evaluate(task, self.project, self.holidays, schedule, trial) is None
        ):
            ui.notify("このタスクには増員を試せません")
            return False
        self.trials[task_id] = trial
        self.refresh_trials()
        return True

    def drop_trial(self, task_id: str) -> None:
        if self.trials.pop(task_id, None) is not None:
            self.refresh_trials()

    def clear_trials(self) -> None:
        if self.trials:
            self.trials = {}
            self.refresh_trials()

    def trial_results(self) -> dict[str, TrialResult]:
        """試算の今の結果。消えた・対象外になったタスクの試算は捨てる。"""
        schedule = Schedule(self.project, self.holidays)
        tasks = self.project.task_map()
        results: dict[str, TrialResult] = {}
        for task_id, trial in list(self.trials.items()):
            task = tasks.get(task_id)
            result = (
                evaluate(task, self.project, self.holidays, schedule, trial)
                if task is not None
                else None
            )
            if result is None:
                del self.trials[task_id]
            else:
                results[task_id] = result
        return results

    def confirm_trials(self) -> int:
        """試算を確定する(weekly_crew に乗せる)。通常の編集 1 回分(元に戻せる)。確定した件数を返す。"""
        schedule = Schedule(self.project, self.holidays)
        tasks = self.project.task_map()
        count = 0
        for task_id, trial in list(self.trials.items()):
            task = tasks.get(task_id)
            saved = (
                confirmed(task, self.project, self.holidays, schedule, trial)
                if task is not None
                else None
            )
            if saved is not None and replace_task(self.project, saved):
                count += 1
        self.trials = {}
        if count:
            self.after_edit()
        else:
            self.refresh_trials()
        return count

    def refresh_trials(self) -> None:
        """帯とチャートを描き直す(Task 3 で帯を足す)。"""
        self.gantt.set_trials(self.trial_results())
```

`reset_history` に `self.trials = {}` を足す。`after_edit` の末尾 `self.gantt.set_project(self.project)` の直前に `self.gantt.set_trials(self.trial_results())` を足す(Task 3 で `set_trials` を作るまでは、ガントチャートに `def set_trials(self, results: dict[str, TrialResult]) -> None: self.trial_results = results` の最小実装を Step 3 の一部として `gantt.py` に足す)。import に `from projectapp.crew_trial import TrialCrew, TrialResult, confirmed, evaluate, replace_task` を足す。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_delay_response.py test/test_crew_trial.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/views.py src/projectapp/gantt.py test/test_delay_response.py
git commit -m "feat: 増員の試算を保持し、確定で weekly_crew に乗せる(要望 132)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ガントチャートの表示 — 帯・重ね描き・右クリック

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions`、`GanttChart.set_trials`・`render`・行の描画・右クリックメニュー)
- Modify: `src/projectapp/views.py`(帯の部品と `GanttActions` の配線)
- Create: `src/projectapp/delay_response.py`(`DELAY_RESPONSE_CSS`、`delay_band(...)`、`trial_dialog(...)`)
- Test: `test/test_delay_response_view.py`(新規)

**Interfaces:**
- Consumes: Task 2 の `trials`・`try_crew`・`drop_trial`・`clear_trials`・`confirm_trials`・`trial_results`。
- Produces:
  - `GanttActions.try_crew: Callable[[SectionPath, int], object]`(右クリック `増員を試す…`)、`GanttActions.drop_trial: Callable[[SectionPath, int], object]`
  - `GanttChart.set_trials(results: dict[str, TrialResult]) -> None`(受け取って再描画)
  - marker: 帯 `delay-band`、帯の件数 `delay-band-text`、`delay-band-confirm`、`delay-band-clear`、重ね描きの先の枠 `trial-ghost-<key>-<ti>`、増員チップ `trial-chip-<key>-<ti>`、元の完了予定の線 `trial-origin-<key>-<ti>`、見込みの文言 `trial-label-<key>-<ti>`、右クリック `context-try-crew`・`context-drop-trial`、ダイアログ `trial-dialog`・`trial-dialog-member`・`trial-dialog-start`・`trial-dialog-ok`。
  - `delay_response.DELAY_RESPONSE_CSS`: ライト/ダークの CSS 変数 `--delay-bg`・`--delay-fg`・`--delay-accent` と、`.delay-band`(`border: 3px dotted var(--delay-accent)`)。

- [ ] **Step 1: Write the failing tests**

```python
# test/test_delay_response_view.py
from datetime import date, datetime
from pathlib import Path

from nicegui.testing import User

from projectapp.cache import save_cache
from projectapp.delay_response import DELAY_RESPONSE_CSS
from projectapp.models import Assignee, Member, Task
from projectapp.views import MainView
from test.test_views import make_view

START = datetime(2026, 11, 2, 9)


def seed(view: MainView) -> None:
    view.project.members = [Member("田中"), Member("鈴木")]
    view.project.tasks.append(
        Task("a", id="ta", planned_start=START, effort_hours=60.0, assignees=[Assignee("田中")])
    )
    view.after_edit()
    view.mark_clean()


def test_the_band_css_uses_a_thick_dotted_border_and_its_own_colours() -> None:
    assert "3px dotted" in DELAY_RESPONSE_CSS
    assert "--delay-accent" in DELAY_RESPONSE_CSS
    assert "body.body--dark" in DELAY_RESPONSE_CSS  # ダークの値がある
    for banned in ("red", "#f44336", "#ffc107", "green"):
        assert banned not in DELAY_RESPONSE_CSS  # 遅れ・警告・取り戻せたの色は使わない


async def test_no_band_without_trials_and_a_band_with_them(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    await user.should_not_see(marker="delay-band")
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see(marker="delay-band")
    await user.should_see(marker="trial-ghost-0-0") if False else None  # key は実装の値に合わせる(Step 4 で確認)


async def test_the_band_shows_the_title_and_counts(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see("遅延対応")
    await user.should_see("試算中: 1 件の増員")


async def test_clear_button_removes_the_band(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see(marker="delay-band-clear")
    user.find(marker="delay-band-clear").click()
    await user.should_not_see(marker="delay-band")
    assert view.trials == {}


async def test_confirm_button_writes_weekly_crew(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    await user.should_see(marker="delay-band-confirm")
    user.find(marker="delay-band-confirm").click()
    await user.should_not_see(marker="delay-band")
    assert view.project.tasks[0].weekly_crew != []
    assert view.is_dirty()


async def test_context_menu_has_try_crew_and_drop(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    await user.should_see(marker="context-try-crew")
    await user.should_see(marker="context-drop-trial")
```

(マーカーのキー `<key>-<ti>` は、既存の `bar-{key}-{ti}`〔`test/test_gantt.py` の例〕と同じ値になる。`trial-ghost-*` の確認は、`bar-` のテストの引き方に合わせて、実装後に `user.find(marker=...)` で足す。)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_delay_response_view.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'projectapp.delay_response'`

- [ ] **Step 3: Implement**

`src/projectapp/delay_response.py`:

```python
"""遅延対応(要望 132)の帯・ダイアログ・CSS。"""

from collections.abc import Callable
from datetime import date

from nicegui import ui

# 紫系。赤(遅れ)・黄(警告)・緑(取り戻せた)とは別系統。枠は太い点線で、通常の帯と形でも区別する。
DELAY_RESPONSE_CSS = """
:root { --delay-bg: #ede7f6; --delay-fg: #311b92; --delay-accent: #7e57c2; }
body.body--dark { --delay-bg: #2a2140; --delay-fg: #d1c4e9; --delay-accent: #b39ddb; }
.delay-band { background: var(--delay-bg); color: var(--delay-fg);
  border: 3px dotted var(--delay-accent); border-radius: 6px; padding: 4px 10px; }
.trial-ghost { border: 2px dashed var(--delay-accent); background: transparent;
  border-radius: 4px; pointer-events: none; }
.trial-chip { border: 1px dashed var(--delay-accent); background: var(--delay-bg);
  color: var(--delay-fg); font-size: 10px; padding: 0 3px; border-radius: 3px; }
.trial-origin { border-left: 2px solid var(--delay-accent); pointer-events: none; }
.trial-label { color: var(--delay-fg); font-size: 11px; white-space: nowrap; }
"""


def delay_band(
    count: int, recovered: int, on_confirm: Callable[[], object], on_clear: Callable[[], object]
) -> None:
    """試算中に、ガントチャートの上に出す帯。"""
    with ui.row().classes("delay-band items-center gap-3 w-full").mark("delay-band"):
        ui.label("遅延対応").classes("text-bold")
        ui.label(f"試算中: {count} 件の増員 / 取り戻せたタスク {recovered} 件").mark(
            "delay-band-text"
        )
        ui.space()
        ui.button("確定", on_click=lambda: on_confirm()).props("dense flat").mark(
            "delay-band-confirm"
        )
        ui.button("すべてやめる", on_click=lambda: on_clear()).props("dense flat").mark(
            "delay-band-clear"
        )


def trial_dialog(
    members: list[str], today: date, on_ok: Callable[[list[str], date], object]
) -> None:
    """増員を試すメンバーと開始日を選ぶ小さなダイアログ。"""
    chosen: list[str] = []
    start = {"day": today}
    with ui.dialog() as dialog, ui.card().mark("trial-dialog"):
        ui.label("増員を試す")
        ui.select(members, multiple=True, label="メンバー", on_change=lambda e: chosen.__setitem__(slice(None), e.value)).mark(
            "trial-dialog-member"
        )
        ui.input("開始日", value=today.isoformat(), on_change=lambda e: _set_day(start, e.value)).mark(
            "trial-dialog-start"
        )

        def ok() -> None:
            if chosen:
                on_ok(list(chosen), start["day"])
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("試す", on_click=ok).mark("trial-dialog-ok")
    dialog.open()


def _set_day(box: dict[str, date], text: str) -> None:
    try:
        box["day"] = date.fromisoformat(text)
    except ValueError:
        pass
```

`gantt.py`:
1. `from projectapp.delay_response import DELAY_RESPONSE_CSS` を import し、`ui.add_css(WARNING_CSS)` の列(1613 行付近)に `ui.add_css(DELAY_RESPONSE_CSS)` を足す。
2. `GanttActions` に `try_crew` と `drop_trial`(`lambda path, ti: None` の既定)を足す。
3. `GanttChart.__init__` に `self.trial_results: dict[str, TrialResult] = {}`。Task 2 の最小実装の `set_trials` を、`self.trial_results = results` のあと `self.render_trigger()`(既存の再描画の入口。`set_project` が使っているもの。`grep -n "def set_project" -A40 gantt.py` で名前を確認して合わせる)を呼ぶ形にする。
4. 棒の描画(`bar.mark(...)` の `with bar:` ブロックのあと、`mark_left = ...` の前)に次を足す。`(result := self.trial_results.get(task.id)) is not None and result.trial_end is not None` のとき:

```python
                if (result := self.trial_results.get(task.id)) is not None:
                    self.trial_overlay(key, ti, task, result, start, columns, width, left, bar_width)
```

```python
    def trial_overlay(
        self, key, ti, task, result, start, columns, width, bar_left, bar_width
    ) -> None:
        """増員の試算を、棒に重ねる: 試算後の完了までの点線の枠、元の完了予定の縦線、増員チップ、見込みの文言。"""
        if start is None:
            return
        if result.trial_end is not None:
            span = bar_span(start, result.trial_end, columns)
            if span is not None:
                left, length = span
                ui.element("div").classes("trial-ghost").style(
                    f"position: absolute; left: {left * width:.1f}px; width: {max(length * width, MIN_BAR_PX):.1f}px;"
                    f" top: {BAR_TOP_PX - 2}px; height: {BAR_HEIGHT_PX + 4}px"
                ).mark(f"trial-ghost-{key}-{ti}")
        if result.original_end is not None:
            line = bar_span(result.original_end, result.original_end, columns)
            if line is not None:
                ui.element("div").classes("trial-origin").style(
                    f"position: absolute; left: {line[0] * width:.1f}px; top: {BAR_TOP_PX - 4}px;"
                    f" height: {BAR_HEIGHT_PX + 8}px"
                ).mark(f"trial-origin-{key}-{ti}")
        ui.label("+" + "・".join(result.names)).classes("trial-chip").style(
            f"position: absolute; left: {bar_left * width + bar_width + 4:.1f}px; top: {BAR_TOP_PX}px"
        ).mark(f"trial-chip-{key}-{ti}")
        ui.label(self.trial_text(result)).classes("trial-label").style(
            f"position: absolute; left: {bar_left * width + bar_width + 4:.1f}px; top: {BAR_TOP_PX + 14}px"
        ).mark(f"trial-label-{key}-{ti}")

    @staticmethod
    def trial_text(result: TrialResult) -> str:
        if result.manual or result.trial_end is None:
            return "完了予定は手で指定されています(見込みなし)"
        text = f"見込み {result.trial_end:%m/%d}"
        days = result.days_earlier
        if days is not None and days > 0:
            text += f"({days} 日早まる)"
        return text
```

(`bar_span` の戻り値は `(left, length)` の相対位置。`bar_left` も `left` と同じ単位なので、`left * width` が px。既存の `bar` 描画と同じ式を使う。実装時に `bar_span(start, end, columns)` が `None` を返す場合の分岐を落とさない。)

5. 右クリックメニュー(`context-weeks` の項目の直後)に:

```python
            self.try_crew_item = ui.menu_item(
                "増員を試す…", on_click=act(lambda p, t: self.actions.try_crew(p, t))
            ).mark("context-try-crew")
            self.drop_trial_item = ui.menu_item(
                "この増員をやめる", on_click=act(lambda p, t: self.actions.drop_trial(p, t))
            ).mark("context-drop-trial")
```

メニューを開くときの有効/無効の切り替え(`weeks_item` を切り替えている箇所の隣)で、`drop_trial_item` を「そのタスクの id が `self.trial_results` にあるとき」だけ有効にし、`try_crew_item` は「通常のタスクで担当者があるとき」だけ有効にする。

`views.py`:
- `GanttActions(...)` に `try_crew=self.open_try_crew, drop_trial=self.drop_trial_at` を足す。
- `open_try_crew(path, index)`: タスクを引き、`trial_dialog([m.name for m in project.members], clock.now().date(), lambda names, day: self.try_crew(task.id, names, day))`。`drop_trial_at(path, index)`: `self.drop_trial(self.tasks_in(path)[index].id)`。
- 帯: `build()` の中のガントチャートの直上に `self.trial_band = ui.column().classes("w-full")` を置き、`refresh_trials()` で `self.trial_band.clear()` → 試算があれば `with self.trial_band: delay_band(len(results), recovered, self.confirm_trials, self.clear_trials)`。`recovered` は、`trial_end` があり、`trial_end <= 締切`(あれば)または `trial_end <= original_end` のうち元の予定超過(`is_overdue` が真)だったものを数える簡易定義: `result.days_earlier` が 1 以上のタスクの件数。`confirm_trials()` の最後と `clear_trials` からも `refresh_trials()` が呼ばれる(Task 2 の実装のとおり)。`after_edit` の `set_trials` 呼び出しは `refresh_trials()` に置き換える。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_delay_response_view.py test/test_delay_response.py test/test_crew_trial.py -v`
Expected: PASS。Step 1 の最初のテストの `if False else None` の行は、`await user.should_see(marker=...)` に置き換え、実際の `key-ti`(根のタスクは `0-0` か `root-0` など、`test/test_gantt.py` の `bar-` の例に合わせる)で `trial-ghost-<key>-<ti>` と `trial-label-<key>-<ti>` を確認する。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/delay_response.py src/projectapp/gantt.py src/projectapp/views.py test/test_delay_response_view.py
git commit -m "feat: 遅延対応の帯と、ガントチャートへの増員の重ね描き・右クリック(要望 132)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ダッシュボードの `ガントチャートで試す`

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`invest_controls`、`DashboardView.__init__` の引数)
- Modify: `src/projectapp/views.py`(`DashboardView(...)` の配線、`try_invest_on_gantt`)
- Test: `test/test_dashboard_view.py`(追記)、`test/test_delay_response.py`(追記)

**Interfaces:**
- Consumes: Task 2 の `try_crew`・`clear_trials`、`CatchUp.invest`(投入候補で選んだ人の名前のタプル)。
- Produces: `DashboardView(..., on_try_on_gantt: Callable[[tuple[str, ...]], object] | None = None)`、marker `dashboard-backlog-try-gantt`、`MainView.try_invest_on_gantt(names: tuple[str, ...]) -> int`(試算を入れたタスクの件数。ガントチャートへ切り替える)。

- [ ] **Step 1: Write the failing tests**

`test/test_dashboard_view.py` に追記(既存の `mount`・`with_backlog` を使う。`mount` に `try_changes: list[tuple[str, ...]] | None = None` を足し、`on_try_on_gantt=try_changes.append if try_changes is not None else None` を渡す):

```python
async def test_the_try_on_gantt_button_needs_a_chosen_person(user: User) -> None:
    tried: list[tuple[str, ...]] = []
    views, _, _ = mount(try_changes=tried)
    await user.open("/")
    backlog = late_backlog_with_candidates()  # 既存の「投入の候補」のテストと同じデータの作り方を使う
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_not_see(marker="dashboard-backlog-try-gantt")  # 選んでいない
    backlog_with_pick = replace(backlog, catch_up=replace(backlog.catch_up, invest=("鈴木",)))
    views[0].show(with_backlog(backlog_with_pick), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-try-gantt")
    user.find(marker="dashboard-backlog-try-gantt").click()
    assert tried == [("鈴木",)]
```

(`late_backlog_with_candidates` は、`test_dashboard_view.py` の要望131のテスト〔`dashboard-backlog-candidate-` を使うもの〕のデータ作りをそのまま関数に切り出す。)

`test/test_delay_response.py` に追記:

```python
async def test_try_invest_on_gantt_puts_trials_on_overdue_tasks(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中"), Member("鈴木")]
    view.project.tasks.append(
        Task(
            "late",
            id="tl",
            planned_start=datetime(2020, 1, 6, 9),
            effort_hours=16.0,
            assignees=[Assignee("田中")],
        )
    )
    view.project.tasks.append(
        Task("ok", id="to", planned_start=datetime(2099, 1, 5, 9), effort_hours=8.0,
             assignees=[Assignee("田中")])
    )
    view.after_edit()
    assert view.try_invest_on_gantt(("鈴木",)) == 1
    assert set(view.trials) == {"tl"}  # 遅れているタスクだけ
    assert view.dashboard_kind is None  # ガントチャートへ切り替わっている
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_dashboard_view.py -k try_on_gantt test/test_delay_response.py -k try_invest -v`
Expected: FAIL(`unexpected keyword 'try_changes'` / `no attribute 'try_invest_on_gantt'`)

- [ ] **Step 3: Implement**

`dashboard_view.py`: `DashboardView.__init__` に `on_try_on_gantt: Callable[[tuple[str, ...]], object] | None = None` を足して `self.on_try_on_gantt` に保持。`invest_controls` の `investment = backlog.investment` の直後(`if investment is None: return` の前)に:

```python
        if rule.invest and self.on_try_on_gantt is not None:
            ui.button(
                "ガントチャートで試す",
                on_click=lambda names=rule.invest: self.on_try_on_gantt(names),
            ).props("dense flat").mark("dashboard-backlog-try-gantt")
```

`views.py`: `DashboardView(...)` に `on_try_on_gantt=self.try_invest_on_gantt` を渡す。

```python
    def try_invest_on_gantt(self, names: tuple[str, ...]) -> int:
        """投入候補で選んだ人を、遅れているタスクに今日の次の週頭から増員する試算にして、ガントチャートへ切り替える。"""
        now = clock.now()
        schedule = Schedule(self.project, self.holidays)
        self.trials = {}
        for task in self.project.all_tasks():
            if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
                continue
            if not is_overdue(task, self.project, self.holidays, now, schedule):
                continue
            trial = TrialCrew(task.id, names, now.date())
            if evaluate(task, self.project, self.holidays, schedule, trial) is not None:
                self.trials[task.id] = trial
        if self.dashboard_kind is not None:
            self.close_dashboard()
        self.refresh_trials()
        if not self.trials:
            ui.notify("増員を試せる遅れたタスクがありません")
        return len(self.trials)
```

(`now.date()` は `snap_week` が次の週頭へ丸める。`Status`・`is_overdue`・`TaskKind` は `views.py` で import 済みか確認し、なければ足す。)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_dashboard_view.py test/test_delay_response.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/dashboard_view.py src/projectapp/views.py test/test_dashboard_view.py test/test_delay_response.py
git commit -m "feat: ダッシュボードの投入候補から、ガントチャートで増員を試す(要望 132)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 保存時の確認(4 択)

**Files:**
- Modify: `src/projectapp/delay_response.py`(`open_trial_save_dialog`)
- Modify: `src/projectapp/views.py`(`save_project_clicked`)
- Test: `test/test_delay_response.py`(追記)

**Interfaces:**
- Consumes: `confirm_trials`・`clear_trials`・`write`。
- Produces: `open_trial_save_dialog(count: int, on_confirm: Callable[[], object], on_keep: Callable[[], object], on_discard: Callable[[], object]) -> None`。marker: `trial-save-dialog`、`trial-save-confirm`(`確定して保存`)、`trial-save-keep`(`確定せずに保存`)、`trial-save-discard`(`試算を捨てて保存`)、キャンセルは `trial-save-cancel`。`MainView.save_project_clicked`: `self.trials` が空でなければ(保存先が決まっているとき)ダイアログを出し、選択後に保存する。`確定せずに保存` では試算を残したまま保存する。

- [ ] **Step 1: Write the failing tests**

```python
async def test_saving_with_trials_asks_and_confirm_saves_the_weekly_crew(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    assert view.write(overwrite=False)  # 最初の保存でファイルを作る
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.save_project_clicked()
    await user.should_see("1 件の増員を確定して保存します")
    user.find(marker="trial-save-confirm").click()
    await wait_until(lambda: not view.is_dirty())
    assert view.trials == {}
    assert view.project.tasks[0].weekly_crew != []


async def test_keep_saves_without_confirming_and_leaves_the_trial(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    assert view.write(overwrite=False)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.save_project_clicked()
    await user.should_see(marker="trial-save-keep")
    user.find(marker="trial-save-keep").click()
    await wait_until(lambda: "ta" in view.trials)
    assert view.project.tasks[0].weekly_crew == []


async def test_discard_drops_the_trial_and_saves(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    assert view.write(overwrite=False)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.save_project_clicked()
    await user.should_see(marker="trial-save-discard")
    user.find(marker="trial-save-discard").click()
    await wait_until(lambda: view.trials == {})
    assert view.project.tasks[0].weekly_crew == []


async def test_cancel_changes_nothing(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    assert view.write(overwrite=False)
    view.try_crew("ta", ["鈴木"], date(2026, 11, 9))
    view.save_project_clicked()
    await user.should_see(marker="trial-save-cancel")
    user.find(marker="trial-save-cancel").click()
    assert "ta" in view.trials and view.project.tasks[0].weekly_crew == []


async def test_saving_without_trials_does_not_ask(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    assert view.write(overwrite=False)
    view.save_project_clicked()
    await user.should_not_see(marker="trial-save-dialog")
```

`wait_until` は `test/test_views.py` の既存の補助(`from test.test_views import make_view, wait_until`)。

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_delay_response.py -k "saving or keep or discard or cancel" -v`
Expected: FAIL(ダイアログが出ない)

- [ ] **Step 3: Implement**

`delay_response.py`:

```python
def open_trial_save_dialog(
    count: int,
    on_confirm: Callable[[], object],
    on_keep: Callable[[], object],
    on_discard: Callable[[], object],
) -> None:
    """保存時に試算が残っているときの確認。黙って確定しない。"""
    with ui.dialog() as dialog, ui.card().mark("trial-save-dialog"):
        ui.label(f"{count} 件の増員を確定して保存します")
        ui.label("確定すると、担当に「週ごとの担当」として保存されます。").classes("text-caption")

        def pick(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("trial-save-cancel")
            ui.button("試算を捨てて保存", on_click=lambda: pick(on_discard)).props("flat").mark(
                "trial-save-discard"
            )
            ui.button("確定せずに保存", on_click=lambda: pick(on_keep)).props("flat").mark(
                "trial-save-keep"
            )
            ui.button("確定して保存", on_click=lambda: pick(on_confirm)).mark("trial-save-confirm")
    dialog.open()
```

`views.py` の `save_project_clicked`: `self.path is None` の分岐のあと、`self.write(overwrite=True)` の前に:

```python
        if self.trials:
            open_trial_save_dialog(
                len(self.trials),
                on_confirm=lambda: (self.confirm_trials(), self.write(overwrite=True)),
                on_keep=lambda: self.write(overwrite=True),
                on_discard=lambda: (self.clear_trials(), self.write(overwrite=True)),
            )
            return
```

(`save_then` など保存の他の入口〔`self.save_then(after)`〕も `self.trials` が残っていれば試算のまま保存する。確認を出すのは明示の保存操作〔`save_project_clicked`〕だけにする。ledger に Ruling を残す。)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_delay_response.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/delay_response.py src/projectapp/views.py test/test_delay_response.py
git commit -m "feat: 試算が残ったまま保存するときの確認(確定・確定せず・捨てる・キャンセル)(要望 132)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 既存表示の回帰・仕様と文書の更新・確認用データ

**Files:**
- Modify: `.claude/spec/gantt.md`、`.claude/spec/dashboard.md`、`.claude/spec/theme.md`、`.claude/spec/header-git.md`、`docs/development.md`、`docs/requests.md`
- Create: `docs/samples/遅延対応の確認.json`
- Test: `test/test_delay_response_view.py`(追記)

**Interfaces:**
- Consumes: Task 1〜5 の全部。

- [ ] **Step 1: Write the failing regression test**

```python
async def test_week_chips_are_unchanged_when_there_are_no_trials(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    seed(view)
    view.toggle_weeks((), 0)
    await user.should_see(marker="week-chip-0-0-0")  # key-ti は既存の week-chip のテストに合わせる
    await user.should_not_see(marker="delay-band")
    assert view.trial_results() == {}
```

- [ ] **Step 2: Run, then fix until it passes**

Run: `uv run pytest test/test_delay_response_view.py -v`
Expected: 失敗したら(`week-chip` の key が違う等)`test/test_gantt.py` の既存の `week-chip-` の使い方に合わせてテストを直し、`PASS` にする。

- [ ] **Step 3: Update docs**

設計書 §9 のとおり。`.claude/spec/gantt.md` に「試算・帯・右クリック(`増員を試す…`/`この増員をやめる`)・重ね描き」、`dashboard.md` に `ガントチャートで試す`、`theme.md` に `遅延対応` の色(`--delay-bg`・`--delay-fg`・`--delay-accent`)と太い点線、`header-git.md` に保存時の確認(4 択)、`docs/development.md` に `crew_trial.py`・`delay_response.py`、`docs/requests.md` の要望 132 の状態を「実装済み(PR 待ち)」にする。

- [ ] **Step 4: Make the sample data**

`docs/samples/遅延対応の確認.json` は、`docs/samples/投入の候補の確認.json` を土台に作る(遅れたタスク 2 件・余力のあるメンバー 2 人。`version` 21)。確認の観点(ダッシュボードで投入候補を選び `ガントチャートで試す` → 紫の帯・点線の枠・見込みの表示 → `確定` で週チップになる → 保存の確認 4 択)を PR 本文に書く。`~/.projectapp` へのコピーは利用者に聞いてから行う。

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest -m smoke`、`uvx ruff check`、`uvx ruff format src test`、`uvx ty check src`
Expected: すべて通る。smoke が失敗したときに限り `uv run pytest -n auto`。

```bash
git add -A .claude/spec docs test
git commit -m "docs: 遅延対応の仕様・開発文書・確認用データを更新する(要望 132)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
