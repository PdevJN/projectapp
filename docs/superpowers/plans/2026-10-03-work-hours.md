# 稼働時間の設定画面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **コミットについて:** ユーザーから許可が出るまでコミットしない。各タスク末尾の Commit ステップは、許可が出てから実施する(許可前は `git status` で変更を確認するだけにする)。作業ブランチは `feature/work-hours`(`develop` から分岐済み)。

**Goal:** プロジェクトごとに、1日の稼働可能時間と始業時刻を設定ダイアログから変更できるようにし、変更時に、自動算出された終了日時だけを再計算する。

**Architecture:** 自動算出された終了を `Task.end_auto` で区別する。再計算は NiceGUI に依存しない純粋関数(`timeline.recalc_ends`)にする。入力の検証(`forms.build_work_settings`)とダイアログ(`forms.open_settings_dialog`)は `forms.py` に置き、`MainView.apply_settings` が値の更新・再計算・描き直し・通知を行う。

**Tech Stack:** Python 3.13、NiceGUI 3.17、pytest / pytest-asyncio / pytest-cov、ty、uv

**Spec:** `docs/superpowers/specs/2026-10-03-work-hours-design.md`

## Global Constraints

- Python 3.13 以上。パッケージャーは uv。UI 言語は日本語。
- すべての関数に型引数と戻り値の型ヒントを付ける。型チェックは `uvx ty check src`。
- コメントの説明は多くても3行以内。コードは PEP8 と The Zen of Python に従う。
- テストは pytest、カバレッジは pytest-cov。テストは `test/` に置く。
- 設定はプロジェクトごと。値は既存の `Project.daily_hours`(既定 6.5h)と `Project.work_start`(既定 9:00)に保存される。
- 再計算するのは、`end_auto` が `True` で開始があるタスクだけ。手入力の終了は変えない。`end_auto` のない古いファイルは `False`(手入力)として読む。
- 稼働時間は、有限の数で、0 より大きく 24 以下。始業時刻は `HH:MM`。**始業時刻 + 稼働時間が 24:00 を超える組み合わせは拒否**する。
- 適用は確認なしで、すぐ再計算する。通知は「稼働時間を変更しました(N件の終了を再計算)」。保存は自動では行わない(変更は `is_dirty` に入る)。
- 範囲外(作らない): 昼休みの設定、曜日ごと・メンバーごとの稼働時間、祝日の編集、設定の取り消しボタン、見積もりのバッファ換算、リソース割り当て比率。

## Review Focus

仕様が黙っているが、利用者が踏みやすい入力・状態。各行は、担当タスクのテストで固定する。

1. 始業時刻 + 稼働時間がちょうど 24:00(許可)と、超過(拒否)。小数の丸めで、ちょうどの組み合わせが弾かれない(Task 2)。
2. 手入力の終了と、`end_auto` のない古いファイルのタスクは、設定を変えても動かない(Task 1、Task 3)。
3. 編集ダイアログを開いて、終了に触れずに保存しても、`end_auto` が `False` に落ちない(Task 2)。
4. 稼働時間が未入力・NaN・inf・負の数(Task 2)。
5. 再計算で算出できないタスク(工数 0 など)は、古い終了のまま残り、件数に数えない(Task 1)。
6. 設定を変えたあと、保存せずに別のプロジェクトを開こうとすると、未保存の確認が出る(Task 3)。

---

## File Structure

| ファイル | 操作 | 責務 |
|---|---|---|
| `src/projectapp/models.py` | 変更 | `Task.end_auto` を追加 |
| `src/projectapp/storage.py` | 変更 | `end_auto` の復元 |
| `src/projectapp/timeline.py` | 変更 | `fill_end` が印を付ける。`recalc_ends` を追加 |
| `src/projectapp/forms.py` | 変更 | `build_task` が印を更新。`build_work_settings`、`open_settings_dialog` |
| `src/projectapp/views.py` | 変更 | 「設定」ボタン、`open_settings`、`apply_settings` |
| `test/test_storage.py` | 変更 | 印の保存・読込 |
| `test/test_timeline.py` | 変更 | `fill_end` の印、`recalc_ends` |
| `test/test_forms.py` | 変更 | 印の遷移、検証、ダイアログ |
| `test/test_views.py` | 変更 | 適用の流れ |
| `CLAUDE.md`(`projectapp/`)、`docs/development.md`、`.claude/MEMORY.md` | 変更 | 記述の更新 |

---

### Task 1: 自動算出の印と再計算(models.py / storage.py / timeline.py)

**Files:**
- Modify: `src/projectapp/models.py`
- Modify: `src/projectapp/storage.py`
- Modify: `src/projectapp/timeline.py`
- Test: `test/test_storage.py`
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: 既存の `calc_end(start, effort_hours, daily_hours, work_start, holidays) -> datetime | None`、`fill_end`、`Project`、`Task`
- Produces:
  - `Task.end_auto: bool = False`(`predecessors` の後ろに置く)
  - `fill_end` が、終了を補完したときだけ `end_auto=True` を付けて返す
  - `recalc_ends(project: Project, holidays: dict[date, str]) -> int`(終了を入れ替えた件数)

- [ ] **Step 1: Write the failing test**

`test/test_storage.py` の末尾に追加:

```python
def test_end_auto_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", sections=[Section("s", [Task("a", end_auto=True), Task("b")])])
    loaded = load_project(save_project(project, tmp_path))
    assert [t.end_auto for t in loaded.sections[0].tasks] == [True, False]


def test_old_file_without_end_auto_reads_as_manual(tmp_path: Path) -> None:
    path = save_project(Project("old", sections=[Section("s", [Task("a", end_auto=True)])]), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["sections"][0]["tasks"][0]["end_auto"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path).sections[0].tasks[0].end_auto is False
```

`test/test_timeline.py` の import に `recalc_ends,` を足し(`month_bands,` と `year_bands,` の間)、末尾に追加:

```python
def test_fill_end_marks_the_end_as_automatic() -> None:
    task = Task("t", start=datetime(2026, 10, 9, 9), effort_hours=15.0)
    assert fill_end(task, Project("p"), NO_HOLIDAYS).end_auto is True


def test_fill_end_does_not_mark_a_manual_end() -> None:
    task = Task("t", start=datetime(2026, 10, 9, 9), end=datetime(2026, 10, 30, 18), effort_hours=15.0)
    assert fill_end(task, Project("p"), NO_HOLIDAYS).end_auto is False


AUTO_START = datetime(2026, 10, 9, 9)  # 金曜
AUTO_END = datetime(2026, 10, 13, 11)  # 6.5h/日・工数15hの終了(火曜)


def auto_task(name: str = "t", **overrides: object) -> Task:
    values: dict[str, object] = {
        "start": AUTO_START,
        "end": AUTO_END,
        "effort_hours": 15.0,
        "end_auto": True,
    }
    values.update(overrides)
    return Task(name, **values)  # type: ignore[arg-type]


def test_recalc_ends_follows_daily_hours() -> None:
    project = project_with(auto_task())
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS) == 1
    task = project.sections[0].tasks[0]
    assert task.end == datetime(2026, 10, 12, 16)  # 金8h + 月7h
    assert task.end_auto is True


def test_recalc_ends_follows_work_start() -> None:
    project = project_with(auto_task())
    project.work_start = time(10, 0)
    assert recalc_ends(project, NO_HOLIDAYS) == 1
    assert project.sections[0].tasks[0].end == datetime(2026, 10, 13, 12)


def test_recalc_ends_follows_holidays() -> None:
    project = project_with(auto_task())
    assert recalc_ends(project, {date(2026, 10, 12): "祝日"}) == 1
    assert project.sections[0].tasks[0].end == datetime(2026, 10, 14, 11)


def test_recalc_ends_returns_zero_when_nothing_changes() -> None:
    project = project_with(auto_task())
    assert recalc_ends(project, NO_HOLIDAYS) == 0


def test_recalc_ends_leaves_manual_ends() -> None:
    manual = auto_task(end=datetime(2026, 10, 30, 18), end_auto=False)
    project = project_with(manual)
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS) == 0
    assert project.sections[0].tasks[0].end == datetime(2026, 10, 30, 18)


def test_recalc_ends_keeps_the_end_of_a_task_it_cannot_compute() -> None:
    project = project_with(auto_task(effort_hours=0.0), auto_task("no start", start=None))
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS) == 0
    assert [t.end for t in project.sections[0].tasks] == [AUTO_END, AUTO_END]


def test_recalc_ends_covers_sections_and_top_level_tasks_and_keeps_the_lists() -> None:
    project = Project("p", sections=[Section("s", [auto_task("a")])], tasks=[auto_task("b")])
    section_tasks, top_tasks = project.sections[0].tasks, project.tasks
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS) == 2
    assert project.sections[0].tasks is section_tasks
    assert project.tasks is top_tasks
    assert [t.end for t in section_tasks + top_tasks] == [datetime(2026, 10, 12, 16)] * 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_storage.py test/test_timeline.py -q`
Expected: FAIL(`recalc_ends` を import できない。`Task` に `end_auto` がない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/models.py` の `Task` の `predecessors` の次の行に追加:

```python
    end_auto: bool = False  # 終了が自動算出で、利用者が書き換えていない
```

`src/projectapp/storage.py` の `_task` の `predecessors=...` の次の行に追加:

```python
        end_auto=raw.get("end_auto", False),
```

`src/projectapp/timeline.py` の `fill_end` の最後の行を次に置き換え、その後ろに `recalc_ends` を追加:

```python
    return task if end is None else replace(task, end=end, end_auto=True)


def recalc_ends(project: Project, holidays: dict[date, str]) -> int:
    """自動算出された終了(end_auto)だけを、現在の稼働設定で再計算する。変えた件数を返す。"""
    changed = 0

    def renew(task: Task) -> Task:
        nonlocal changed
        if not task.end_auto or task.start is None:
            return task
        end = calc_end(
            task.start, task.effort_hours, project.daily_hours, project.work_start, holidays
        )
        if end is None or end == task.end:
            return task
        changed += 1
        return replace(task, end=end)

    project.tasks[:] = [renew(t) for t in project.tasks]
    for section in project.sections:
        section.tasks[:] = [renew(t) for t in section.tasks]
    return changed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/models.py src/projectapp/storage.py src/projectapp/timeline.py test/test_storage.py test/test_timeline.py
git commit -m "feat: 自動算出された終了の印と再計算を追加"
```

---

### Task 2: 入力の検証と設定ダイアログ(forms.py)

**Files:**
- Modify: `src/projectapp/forms.py`
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: `Task.end_auto`(Task 1)
- Produces:
  - `build_task` が、終了が編集前(新規は `None`)と**違えば** `end_auto=False`、**同じなら**編集前の `end_auto` を引き継ぐ
  - `build_work_settings(hours: float | None, start: str) -> tuple[float, time]`(不正なら `ValueError`)
  - `open_settings_dialog(daily_hours: float, work_start: time, on_apply: Callable[[float, time], object]) -> None`。マーカー: 稼働時間 `settings-hours`、始業時刻 `settings-start`、適用 `settings-apply`、エラー `settings-error`

- [ ] **Step 1: Write the failing test**

`test/test_forms.py` の `from datetime import datetime` を `from datetime import datetime, time` に変え、`from projectapp.forms import (...)` に `build_work_settings,` と `open_settings_dialog,` を足す(アルファベット順の位置に)。末尾に追加:

```python
def test_build_task_keeps_end_auto_when_the_end_is_untouched() -> None:
    existing = Task("旧", end=datetime(2026, 10, 7, 18), end_auto=True)
    assert make(existing).end_auto is True


def test_build_task_clears_end_auto_when_the_end_is_edited() -> None:
    existing = Task("旧", end=datetime(2026, 10, 7, 18), end_auto=True)
    assert make(existing, end="2026-10-08T18:00").end_auto is False


def test_build_task_clears_end_auto_when_the_end_is_emptied() -> None:
    existing = Task("旧", end=datetime(2026, 10, 7, 18), end_auto=True)
    edited = make(existing, end="")
    assert edited.end is None
    assert edited.end_auto is False


def test_build_task_typed_end_of_a_new_task_is_manual() -> None:
    assert make().end_auto is False


@pytest.mark.parametrize(
    ("hours", "start"),
    [(6.5, "09:00"), (24.0, "00:00"), (0.5, "23:30"), (6.5, "17:30"), (8.0, "9:00"), (0.1, "23:54")],
)
def test_build_work_settings_accepts_valid_values(hours: float, start: str) -> None:
    assert build_work_settings(hours, start)[0] == hours


def test_build_work_settings_returns_hours_and_time() -> None:
    assert build_work_settings(6.5, " 9:05 ") == (6.5, time(9, 5))


@pytest.mark.parametrize(
    ("hours", "start"),
    [
        (None, "09:00"),
        (0.0, "09:00"),
        (-1.0, "09:00"),
        (24.5, "09:00"),
        (float("nan"), "09:00"),
        (float("inf"), "09:00"),
        (6.5, ""),
        (6.5, "25:00"),
        (6.5, "abc"),
        (6.5, "09:00:30"),
        (6.5, "17:31"),
        (24.0, "00:01"),
        (0.5, "23:31"),
    ],
)
def test_build_work_settings_rejects_invalid_values(hours: float | None, start: str) -> None:
    with pytest.raises(ValueError):
        build_work_settings(hours, start)


async def test_settings_dialog_prefills_rejects_then_applies(user: User) -> None:
    applied: list[tuple[float, time]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s: applied.append((h, s))
            ),
        )

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="settings-hours").elements.pop().value == 6.5
    assert user.find(marker="settings-start").elements.pop().value == "09:00"
    user.find(marker="settings-hours").clear().type("25")
    user.find(marker="settings-apply").click()
    await user.should_see("24以下")
    assert applied == []
    user.find(marker="settings-hours").clear().type("8")
    user.find(marker="settings-start").clear().type("10:00")
    user.find(marker="settings-apply").click()
    assert applied == [(8.0, time(10, 0))]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_forms.py -q`
Expected: FAIL(`build_work_settings` を import できない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/forms.py` の import を変更:

```python
from datetime import datetime, time
from math import isfinite
```

(既存の `from datetime import datetime` を置き換え、`from collections.abc ...`、`from dataclasses ...` の並びに `from math import isfinite` を足す。)

`MIN_YEAR, MAX_YEAR = ...` の下に追加:

```python
MAX_DAILY_HOURS = 24.0
```

`build_task` の末尾の `return replace(` を次に置き換える(`existing or Task(clean)` を `base` にまとめる):

```python
    base = existing or Task(clean)
    existing_end = existing.end if existing else None
    return replace(
        base,
        name=clean,
        start=start_at,
        end=end_at,
        end_auto=base.end_auto and end_at == existing_end,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignee=assignee.strip() or None,
    )
```

`build_section_name` の前に追加:

```python
def build_work_settings(hours: float | None, start: str) -> tuple[float, time]:
    """稼働可能時間と始業時刻の入力を検証する。"""
    if hours is None:
        raise ValueError("稼働可能時間を入力してください")
    if not isfinite(hours) or not 0 < hours <= MAX_DAILY_HOURS:
        raise ValueError("稼働可能時間は0より大きく24以下で入力してください")
    try:
        work_start = datetime.strptime(start.strip(), "%H:%M").time()
    except ValueError:
        raise ValueError("始業時刻はHH:MMの形式で入力してください") from None
    minutes = work_start.hour * 60 + work_start.minute + hours * 60
    if minutes > 24 * 60 + 1e-9:  # 稼働枠が日をまたぐと算出が曖昧になる
        raise ValueError("始業時刻と稼働可能時間の合計が24時を超えています")
    return hours, work_start
```

ファイルの末尾に追加:

```python
def open_settings_dialog(
    daily_hours: float,
    work_start: time,
    on_apply: Callable[[float, time], object],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("稼働時間の設定").classes("text-h6")
        hours = ui.number("1日の稼働可能時間(h)", value=daily_hours, min=0, step=0.5).mark(
            "settings-hours"
        )
        start = ui.input("始業時刻(HH:MM)", value=work_start.strftime("%H:%M")).props(
            "type=time"
        ).mark("settings-start")
        error = ui.label("").classes("text-negative").mark("settings-error")

        def apply() -> None:
            try:
                result = build_work_settings(hours.value, start.value or "")
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_apply(*result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("settings-apply")
    dialog.open()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`(`test_build_task_keeps_end_auto_when_the_end_is_untouched` と `typed_end_of_a_new_task` は、実装前から通る。回帰を防ぐためのテスト。`ui.number` の `clear().type()` の挙動で落ちる場合は、`type` の代わりに `.elements.pop().set_value(...)` で値を入れる)

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "feat: 稼働時間の設定ダイアログと入力検証を追加"
```

---

### Task 3: 「設定」ボタンと適用(views.py)

**Files:**
- Modify: `src/projectapp/views.py`
- Modify: `CLAUDE.md`(`projectapp/` の直下)
- Modify: `docs/development.md`
- Modify: `.claude/MEMORY.md`
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `forms.open_settings_dialog`(Task 2)、`timeline.recalc_ends`(Task 1)、既存の `MainView.holidays`、`gantt.set_project`、`is_dirty`
- Produces:
  - `MainView.open_settings() -> None`(ダイアログを開く。マーカー `open-settings` のボタンから呼ぶ)
  - `MainView.apply_settings(hours: float, start: time) -> None`

- [ ] **Step 1: Write the failing test**

`test/test_views.py` の `from datetime import date, datetime` を `from datetime import date, datetime, time` に変える。末尾に追加:

```python
async def open_settings_and_apply(user: User, hours: str, start: str) -> None:
    user.find(marker="open-settings").click()
    user.find(marker="settings-hours").clear().type(hours)
    user.find(marker="settings-start").clear().type(start)
    user.find(marker="settings-apply").click()


async def test_apply_settings_recalculates_only_auto_ends(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("自動", start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    manual_end = datetime(2026, 10, 30, 18)
    view.save_task(
        None, None, Task("手動", start=datetime(2026, 10, 9, 9), end=manual_end, effort_hours=15.0)
    )
    assert view.project.tasks[0].end == datetime(2026, 10, 13, 11)
    await open_settings_and_apply(user, "8", "09:00")
    assert await wait_until(lambda: user.notify.contains("1件の終了を再計算"))
    assert view.project.daily_hours == 8.0
    assert view.project.tasks[0].end == datetime(2026, 10, 12, 16)
    assert view.project.tasks[1].end == manual_end


async def test_apply_settings_with_the_same_values_does_nothing(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="open-settings").click()
    user.find(marker="settings-apply").click()
    await asyncio.sleep(0.3)
    assert not user.notify.contains("稼働時間を変更しました")
    assert not view.is_dirty()


async def test_invalid_settings_keep_the_dialog_and_the_values(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await open_settings_and_apply(user, "25", "09:00")
    await user.should_see("24以下")
    assert view.project.daily_hours == 6.5


async def test_settings_are_saved_with_the_project(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("自動", start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    await open_settings_and_apply(user, "8", "10:00")
    assert await wait_until(lambda: view.is_dirty())
    await save_new_as(user, "設定")
    assert await wait_until(lambda: (tmp_path / "設定.json").exists())
    saved = load_project(tmp_path / "設定.json")
    assert saved.daily_hours == 8.0
    assert saved.work_start == time(10, 0)
    assert saved.tasks[0].end_auto is True


async def test_changed_settings_ask_before_switching_projects(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存"), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await open_settings_and_apply(user, "8", "09:00")
    assert await wait_until(lambda: views[0].is_dirty())
    await choose_in_combo(user, "既存")
    await user.should_see(marker="unsaved-save")
    assert views[0].path is None
```

`test/test_views.py` の先頭に `asyncio` の import があることを確認する(`import asyncio` は既存)。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_views.py -q`
Expected: FAIL(`open-settings` が見つからない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/views.py` を変更する。

import:

```python
from datetime import date, time
```

(既存の `from datetime import date` を置き換える。)`from projectapp.forms import (...)` に `open_settings_dialog,` を足し(`open_section_dialog,` の次)、`from projectapp.timeline import fill_end` を次に置き換える:

```python
from projectapp.timeline import fill_end, recalc_ends
```

`save_project_clicked` の前に追加:

```python
    def open_settings(self) -> None:
        open_settings_dialog(
            self.project.daily_hours, self.project.work_start, self.apply_settings
        )

    def apply_settings(self, hours: float, start: time) -> None:
        """稼働設定を更新し、自動算出された終了だけを再計算する。保存はしない。"""
        if hours == self.project.daily_hours and start == self.project.work_start:
            return
        self.project.daily_hours, self.project.work_start = hours, start
        count = recalc_ends(self.project, self.holidays)
        self.gantt.set_project(self.project)
        ui.notify(f"稼働時間を変更しました({count}件の終了を再計算)")

```

`header` の「保存」ボタンの直後(`"save-project"` の `)` の次)に追加:

```python
                ui.button("設定", icon="settings", on_click=self.open_settings).mark(
                    "open-settings"
                )
```

`CLAUDE.md`(`projectapp/` の直下)の、次の行の直後に1行追加する。

直前の行: `- 予定を超えたタスクは、`赤`を基準とした`背景色`で表示される`

追加する行: `- 設定ダイアログで、プロジェクトごとに`稼働可能時間`と`始業時刻`を変更できる。変更すると、自動算出された終了日時は再計算される(手入力の終了日時は変わらない)`

`docs/development.md` の表を更新する:
- `forms.py` の行に「、稼働時間の設定ダイアログ」を、「入力検証」の前に足す。
- `timeline.py` の行の「予定超過の判定」の前に「自動算出された終了の再計算、」を足す。
- `models.py` の行に「(`Task.end_auto` は自動算出された終了の印)」を足す。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest --cov=projectapp -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`(`ui.number` の `clear().type()` の挙動で落ちる場合は、Task 2 と同じ対処をする)

- [ ] **Step 5: 手動確認(実機)**

Run: `uv run projectapp`
確認すること:
- 「設定」を押すと、稼働時間(6.5)と始業時刻(09:00)が入ったダイアログが出る。
- 稼働時間に `25`、または始業時刻 `20:00` と稼働時間 `6.5` を入れて「適用」を押すと、エラーが出て閉じない。
- タスクを足し(開始と工数を入れて終了は空)、稼働時間を `8` にして「適用」を押すと、「稼働時間を変更しました(1件の終了を再計算)」と通知され、バーが変わる。手で終了を入れたタスクは変わらない。
- 値を `6.5` に戻して適用すると、バーが元に戻る。
- 「保存」して再起動し、「開く」で読み込むと、設定とタスクが残っている。
- 設定を変えたあと、保存せずに別のファイルを選ぶと、未保存の確認が出る。

- [ ] **Step 6: 作業記録の更新**

`.claude/MEMORY.md` を更新する:
- 「現在の状況」を、作業ブランチ `feature/work-hours` と、稼働時間の設定画面の実装(テスト件数は `uv run pytest -q` の結果)に更新する。
- 「実装済みの機能」に、稼働時間の設定(ダイアログ、`end_auto`、`recalc_ends`)を足す。
- 「次にやること」から、「稼働可能時間・始業時刻の設定画面」を外す。

- [ ] **Step 7: Commit(許可が出てから)**

```bash
git add src/projectapp/views.py test/test_views.py CLAUDE.md docs/development.md .claude/MEMORY.md
git commit -m "feat: 稼働時間の設定ダイアログと再計算を追加"
```

---

## Self-Review(計画の作成者による確認)

- **仕様の網羅**: 印と保存・読込・古いファイル(Task 1)、`fill_end` の印と `recalc_ends`(Task 1)、`build_task` の印の遷移(Task 2)、検証と 24:00 の制約(Task 2)、設定ダイアログ(Task 2)、適用・通知・同じ値で何もしない・編集中の判定・保存(Task 3)、ドキュメント(Task 3)。範囲外の項目は作らない。
- **プレースホルダ**: なし。
- **型・名前の一貫性**: `Task.end_auto`、`recalc_ends(project, holidays) -> int`、`build_work_settings(hours, start) -> tuple[float, time]`、`open_settings_dialog(daily_hours, work_start, on_apply)`、`MainView.open_settings` / `apply_settings`、マーカー `open-settings` / `settings-hours` / `settings-start` / `settings-apply` / `settings-error` は、全タスクで同じ。
- **設計書との差**: `forms.py` に `MAX_DAILY_HOURS` を置き、検証の許容誤差(`1e-9`)を設けた。24:00 ちょうどの組み合わせが、小数の丸めで弾かれないため(設計書の「24:00 を超える」に沿う)。
