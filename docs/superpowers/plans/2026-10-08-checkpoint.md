# チェックポイント用のタスク Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 締切の日時しか持たない「チェックポイント」を、タスクの種別として登録でき、ガントチャートに大きめの ◆ だけで表示する。

**Architecture:** `Task.kind`(`通常` / `チェックポイント`)を足す。チェックポイントは、`Schedule` では実効の開始・完了がどちらも締切(押し出されず、先行にすると後続を押し出す)。描画は、バーの代わりに ◆ を 1 つ出す(`task_row` の早期 return)。編集ダイアログは、種別のトグルで欄を出し入れする。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、`uv`、`ty`。

**Spec:** `docs/superpowers/specs/2026-10-08-checkpoint-design.md`

## Global Constraints

- チェックポイントは、締切が必須。状態は「未着手」「終了」だけ。開始予定・完了予定・工数・担当・割り当て率・実績・進捗度を持たない(保存で空にする。読込では、入っていても使わない)。
- 優先度・色・ProjectCode・先行タスクは、通常と同じ。
- 実効の開始・完了は、どちらも締切。押し出されない。先行にしたとき、後続は締切まで押し出される。
- `is_overdue`: チェックポイントは、状態が「終了」でなく、先行の完了(`Schedule.latest_finish`)が締切より後なら超過。通常タスクの判定は変えない。
- ◆: 状態の色(`STATUS_COLOR_VAR`)、大きさ `CHECKPOINT_MARKER_PX`、締切の位置・行の中央。クリックで編集。ドラッグはしない。通常タスクの締切の小さな橙の ◆ は変えない。
- 担当者の負荷・工数の予定と実績・担当者向けの書き出しは、コードを変えず、対象外になる(テストで確かめる)。
- 保存の形式: `"kind"`。キーがない・`null` は通常。不正な値は読込を拒否する。
- コード規約(`.claude/RULE.md`): すべての関数に型ヒント、`ty` で検証、コメントは多くても 3 行、PEP8。
- 全体のテスト(1,353 件)・`uvx ty check src`・`uv run pytest -n auto` が通ること。テストは時間制限を付けずに実行する。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. 手編集のファイルで、チェックポイントに開始予定・工数・担当・実績が入っていても、読み込めて、バーが出ず、負荷の集計に出ない(`Task 1`・`Task 4`・`Task 5`)。
2. 値のある通常タスクをチェックポイントへ切り替え、隠した欄に不正な文字が入っていても保存できる。実行中の状態から切り替えたとき、状態が「未着手」になる。戻すと欄が現れる(`Task 3`)。
3. 先行したチェックポイントより後に、すでに開始予定のある後続は、前に戻らない(`max` の規則)。終了済みのチェックポイントは、超過にならない(`Task 2`)。
4. チェックポイントだけのプロジェクトで、ダッシュボードの進捗率が空(None)になり、見込みの超過の一覧が例外にならない(`Task 5`)。
5. 担当者の絞り込みで ◆ が隠れても、矢印・行の並びがずれない。表示範囲の外の ◆ と、その矢印は出ない(`Task 4`)。

---

## File Structure

| ファイル | 責務 |
|---|---|
| `src/projectapp/models.py`(変更) | `TaskKind`、`CHECKPOINT_STATUSES`、`Task.kind` |
| `src/projectapp/storage.py`(変更) | `kind` の読込と、チェックポイントの検証・正規化 |
| `src/projectapp/timeline.py`(変更) | `Schedule`・`effective_*`・`is_overdue` のチェックポイントの扱い |
| `src/projectapp/forms.py`(変更) | `build_task` の `kind` |
| `src/projectapp/task_dialog.py`(変更) | 種別のトグルと、欄の出し入れ |
| `src/projectapp/gantt.py`(変更) | ◆ の描画、チップ、矢印の端 |
| `src/projectapp/dashboard.py`(変更) | 進捗率からの除外、見込みの超過の一覧 |
| `docs/development.md`・`CLAUDE.md`・`.claude/MEMORY.md`(変更) | 文書 |

新規のテストは `test/test_checkpoint.py`(データ・日程・フォーム・ダッシュボード)、ほかは既存の `test_task_dialog.py`・`test_gantt.py`・`test_dashboard.py` へ足す。

---

### Task 1: データ(`TaskKind`・保存と検証・コピー)

**Files:**
- Modify: `src/projectapp/models.py`
- Modify: `src/projectapp/storage.py`(`_task`)
- Test: `test/test_checkpoint.py`(新規)

**Interfaces:**
- Produces: `models.TaskKind`(`NORMAL = "通常"`、`CHECKPOINT = "チェックポイント"`)、`models.CHECKPOINT_STATUSES: tuple[Status, ...]`(`(Status.NOT_STARTED, Status.DONE)`)、`Task.kind: TaskKind`(既定は通常)

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_checkpoint.py`:

```python
from datetime import datetime
from pathlib import Path

import pytest

from projectapp import arrange
from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.storage import load_project, save_project
from test_storage import write_raw

DEADLINE = datetime(2026, 10, 12, 17, 0)


def checkpoint(name: str, deadline: datetime | None = DEADLINE, **fields: object) -> Task:
    return Task(name, id=name, kind=TaskKind.CHECKPOINT, deadline=deadline, **fields)  # type: ignore[arg-type]


def test_kind_roundtrip(tmp_path: Path) -> None:
    project = Project("cp", sections=[Section("s", [checkpoint("レビュー")])])
    loaded = load_project(save_project(project, tmp_path)).sections[0].tasks[0]
    assert (loaded.kind, loaded.deadline, loaded.planned_start) == (
        TaskKind.CHECKPOINT,
        DEADLINE,
        None,
    )


def test_a_file_without_kind_loads_as_normal(tmp_path: Path) -> None:
    path = write_raw(tmp_path, [{"name": "a"}])
    assert load_project(path).sections[0].tasks[0].kind is TaskKind.NORMAL


@pytest.mark.parametrize(
    "raw",
    [
        {"name": "a", "kind": "zz"},
        {"name": "a", "kind": 1},
        {"name": "a", "kind": "チェックポイント"},  # 締切なし
        {"name": "a", "kind": "チェックポイント", "deadline": "2026-10-12T17:00:00", "status": "実行中"},
        {"name": "a", "kind": "チェックポイント", "deadline": "2026-10-12T17:00:00", "status": "一時停止"},
    ],
)
def test_bad_kinds_are_rejected(tmp_path: Path, raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        load_project(write_raw(tmp_path, [raw]))


def test_a_checkpoint_with_stray_fields_is_loaded_without_them(tmp_path: Path) -> None:
    path = write_raw(
        tmp_path,
        [
            {
                "name": "a",
                "kind": "チェックポイント",
                "deadline": "2026-10-12T17:00:00",
                "planned_end_manual": True,
                "planned_start": "2026-10-05T09:00:00",
                "planned_end": "2026-10-07T18:00:00",
                "effort_hours": 5.0,
                "assignee": "佐藤",
                "allocation": 0.5,
                "actuals": [{"start": "2026-10-05T09:00:00"}],
            }
        ],
    )
    loaded = load_project(path)
    task = loaded.sections[0].tasks[0]
    assert (task.planned_start, task.planned_end, task.planned_end_manual) == (None, None, False)
    assert (task.effort_hours, task.assignee, task.allocation, task.actuals) == (0.0, None, 1.0, [])
    assert task.deadline == DEADLINE
    assert loaded.members == []  # 担当は使わないので、メンバーも補わない


def test_copy_keeps_the_kind() -> None:
    project = Project("p", sections=[Section("A", [checkpoint("c")])])
    copy = arrange.copy_task(project, (0, 0), (0, 1))
    assert copy.kind is TaskKind.CHECKPOINT and copy.deadline == DEADLINE
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_checkpoint.py -q`
Expected: FAIL(`TaskKind` がない)

- [ ] **Step 3: `models.py` を直す**

`Status` の定義の後に追加:

```python
class TaskKind(StrEnum):
    NORMAL = "通常"
    CHECKPOINT = "チェックポイント"  # 締切だけを持つ節目。バーを持たず、◆ だけを出す


CHECKPOINT_STATUSES = (Status.NOT_STARTED, Status.DONE)  # チェックポイントが取れる状態
```

`Task` の最後の項目(`project_code`)の次に追加:

```python
    kind: TaskKind = TaskKind.NORMAL  # チェックポイントは、締切だけを持つ(他の日時・工数・担当・実績は持たない)
```

- [ ] **Step 4: `storage.py` を直す**

`from dataclasses import asdict` を `from dataclasses import asdict, replace` にし、`from projectapp.models import (` の一覧に `CHECKPOINT_STATUSES,` と `TaskKind,` を足す。`_task` の `return Task(` を `task = Task(` に変えて、閉じ括弧の後ろに追加する。`Task(` の引数の末尾の `project_code=_project_code(raw.get("project_code")),` の次の行に `kind=kind,` を足し、`_task` の先頭に `kind = _kind(raw.get("kind"))` を足す:

```python
    return _checkpoint(task) if task.kind is TaskKind.CHECKPOINT else task
```

`_task_id` の前に追加する:

```python
def _kind(value: Any) -> TaskKind:
    """タスクの種別。キーがない・null は通常。不正は ValueError(開けませんでした)。"""
    if value is None:
        return TaskKind.NORMAL
    try:
        return TaskKind(value)
    except ValueError:
        raise ValueError(f"タスクの種別が正しくありません: {value!r}") from None


def _checkpoint(task: Task) -> Task:
    """チェックポイントを検証し、使わない項目(開始予定・工数・担当・実績など)を空にして返す。"""
    if task.deadline is None:
        raise ValueError(f"チェックポイントに締切がありません: {task.name}")
    if task.status not in CHECKPOINT_STATUSES:
        raise ValueError(f"チェックポイントの状態は未着手か終了です: {task.name}")
    return replace(
        task,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        effort_hours=0.0,
        assignee=None,
        allocation=1.0,
        actuals=[],
    )
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_checkpoint.py -q`
Expected: PASS

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_checkpoint.py
git commit -m "feat: タスクの種別(チェックポイント)の保存と検証

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 日程(`Schedule`・`effective_*`・`is_overdue`)

**Files:**
- Modify: `src/projectapp/timeline.py`(`Schedule._resolve`、`effective_start`、`effective_end`、`is_overdue`)
- Test: `test/test_checkpoint.py`

**Interfaces:**
- Consumes: `Task.kind`、`TaskKind`(Task 1)
- Produces: チェックポイントの `Schedule.start(task) == Schedule.end(task) == task.deadline`、`effective_start/end` も同じ。`is_overdue` の、見込みの超過。

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_checkpoint.py` の import に `from projectapp.timeline import Schedule, effective_end, effective_start, is_overdue` を足し、末尾に追加する:

```python
MON = datetime(2026, 10, 5, 9, 0)
WED_NOON = datetime(2026, 10, 7, 12, 0)


def work(name: str, *predecessors: str, **fields: object) -> Task:
    return Task(name, id=name, predecessors=list(predecessors), **fields)  # type: ignore[arg-type]


def project(*tasks: Task) -> Project:
    return Project("p", tasks=list(tasks), daily_hours=6.5)


def test_a_checkpoints_start_and_end_are_its_deadline() -> None:
    cp = checkpoint("c", planned_start=MON, effort_hours=5.0)  # 使われない値が入っていても
    proj = project(cp)
    assert effective_start(cp, proj, {}) == DEADLINE
    assert effective_end(cp, proj, {}) == DEADLINE
    schedule = Schedule(proj, {})
    assert (schedule.start(cp), schedule.end(cp)) == (DEADLINE, DEADLINE)


def test_a_checkpoint_pushes_its_successor_to_the_deadline() -> None:
    friday = datetime(2026, 10, 9, 17, 0)
    c = checkpoint("c", friday)
    b = work("b", "c", planned_start=MON, effort_hours=1)
    proj = project(c, b)
    assert effective_start(b, proj, {}) == friday


def test_a_successor_already_later_is_not_pulled_back() -> None:
    c = checkpoint("c", datetime(2026, 10, 7, 12, 0))
    later = datetime(2026, 10, 9, 9, 0)
    b = work("b", "c", planned_start=later, effort_hours=1)
    assert effective_start(b, project(c, b), {}) == later


def test_a_checkpoint_is_not_pushed_by_its_predecessors() -> None:
    a = work("a", planned_start=MON, effort_hours=26)  # 木曜 15:30 まで
    c = checkpoint("c", WED_NOON, "a")
    assert effective_start(c, project(a, c), {}) == WED_NOON


def test_a_checkpoint_is_overdue_when_its_predecessors_will_finish_after_the_deadline() -> None:
    a = work("a", planned_start=MON, effort_hours=26)  # 木曜 15:30 まで
    c = checkpoint("c", WED_NOON, "a")
    proj = project(a, c)
    assert is_overdue(c, proj, {}, MON)  # まだ締切の前でも、間に合わない見込み


def test_a_checkpoint_is_not_overdue_when_the_predecessors_finish_in_time() -> None:
    a = work("a", planned_start=MON, effort_hours=1)
    c = checkpoint("c", WED_NOON, "a")
    assert not is_overdue(c, project(a, c), {}, MON)


def test_a_done_checkpoint_is_never_overdue() -> None:
    a = work("a", planned_start=MON, effort_hours=26)
    c = checkpoint("c", WED_NOON, "a", status=Status.DONE)
    assert not is_overdue(c, project(a, c), {}, datetime(2026, 10, 20))


def test_a_checkpoint_is_overdue_after_its_deadline() -> None:
    c = checkpoint("c", WED_NOON)
    assert is_overdue(c, project(c), {}, datetime(2026, 10, 8))
    assert not is_overdue(c, project(c), {}, MON)


def test_a_normal_task_is_not_overdue_just_because_it_will_miss_the_deadline() -> None:
    a = work("a", planned_start=MON, effort_hours=26)
    b = work("b", "a", planned_start=MON, effort_hours=1, deadline=WED_NOON)
    assert not is_overdue(b, project(a, b), {}, MON)  # 通常タスクは、現在時刻だけで判定する(従来どおり)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_checkpoint.py -q -k "start_and_end or pushes or pulled or pushed_by or overdue or missing"`
Expected: FAIL

- [ ] **Step 3: `timeline.py` を直す**

`from projectapp.models import Project, Status, Task` を `from projectapp.models import Project, Status, Task, TaskKind` にする。`Schedule._resolve` の、`if task.id in self._done:` の返しの直後に追加する:

```python
        if task.kind is TaskKind.CHECKPOINT:  # 締切に固定。先行で押し出さない
            result = (task.deadline, task.deadline)
            self._done[task.id] = result
            return result
```

`effective_start` と `effective_end` の先頭(`if schedule is None and not task.predecessors:` の前)に、それぞれ追加する:

```python
    if task.kind is TaskKind.CHECKPOINT:
        return task.deadline
```

`is_overdue` の、`moment` を決めるブロックの直後(`if task.deadline is not None and moment > task.deadline:` の前)に追加する:

```python
    if task.kind is TaskKind.CHECKPOINT and task.deadline is not None and task.predecessors:
        floor = (schedule or Schedule(project, holidays)).latest_finish(task)
        if floor is not None and floor > task.deadline:
            return True  # 先行の完了が締切を超える見込み
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_checkpoint.py -q`
Expected: PASS

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/timeline.py test/test_checkpoint.py
git commit -m "feat: チェックポイントの日程(締切に固定・先行にすると後続を押し出す・見込みの超過)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 保存の検証(`build_task`)と編集ダイアログ

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task`)
- Modify: `src/projectapp/task_dialog.py`(`DateTimeFields.__init__`、`open_task_dialog`)
- Test: `test/test_checkpoint.py`(`build_task`)、`test/test_task_dialog.py`

**Interfaces:**
- Consumes: `TaskKind`、`CHECKPOINT_STATUSES`(Task 1)
- Produces: `forms.build_task(..., kind: TaskKind = TaskKind.NORMAL)`。ダイアログのマーカー `task-kind`(トグル)、`task-kind-hint`(ヒント)。

- [ ] **Step 1: `build_task` のテストを書く(失敗させる)**

`test/test_checkpoint.py` の import に `from projectapp.forms import build_task` を足し、末尾に追加する:

```python
def make(existing: Task | None = None, **overrides: object) -> Task:
    values: dict[str, object] = {
        "name": "レビュー",
        "planned_start": "",
        "planned_end": "",
        "deadline": "2026-10-12T17:00",
        "effort_hours": None,
        "priority": Priority.HIGH,
        "status": Status.NOT_STARTED,
        "color": "#112233",
        "assignee": "",
        "allocation_percent": None,
        "kind": TaskKind.CHECKPOINT,
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]


def test_a_checkpoint_keeps_only_the_deadline() -> None:
    task = make(
        planned_start="日付ではない",  # 隠した欄の不正な入力は、保存を妨げない
        planned_end="2026-10-07T18:00",
        effort_hours=-3.0,
        assignee="佐藤",
        allocation_percent=500.0,
        actual_start="2026-10-05T09:00",
    )
    assert task.kind is TaskKind.CHECKPOINT
    assert task.deadline == DEADLINE
    assert (task.planned_start, task.planned_end, task.planned_end_manual) == (None, None, False)
    assert (task.effort_hours, task.assignee, task.allocation, task.actuals) == (0.0, None, 1.0, [])
    assert task.priority is Priority.HIGH and task.color == "#112233"


def test_a_checkpoint_needs_a_deadline() -> None:
    with pytest.raises(ValueError, match="締切"):
        make(deadline="")


@pytest.mark.parametrize("status", [Status.RUNNING, Status.PAUSED])
def test_a_checkpoint_rejects_the_other_statuses(status: Status) -> None:
    with pytest.raises(ValueError, match="状態"):
        make(status=status)


def test_a_checkpoint_can_become_normal_again() -> None:
    existing = checkpoint("x")
    task = make(
        existing,
        kind=TaskKind.NORMAL,
        planned_start="2026-10-05T09:00",
        planned_end="2026-10-07T18:00",
        effort_hours=8.0,
        status=Status.RUNNING,
        allocation_percent=100.0,
    )
    assert task.kind is TaskKind.NORMAL and task.id == "x"
    assert task.planned_start == datetime(2026, 10, 5, 9, 0)


def test_a_normal_task_keeps_building_as_before() -> None:
    task = make(kind=TaskKind.NORMAL, planned_start="2026-10-05T09:00", effort_hours=8.0)
    assert task.kind is TaskKind.NORMAL and task.effort_hours == 8.0
```

import に `Priority` を足す(`from projectapp.models import Priority, Project, Section, Status, Task, TaskKind`)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_checkpoint.py -q -k "keeps_only or needs_a_deadline or other_statuses or normal_again or keeps_building"`
Expected: FAIL(`kind` を受け付けない)

- [ ] **Step 3: `forms.py` を直す**

`from projectapp.models import (` の一覧に `CHECKPOINT_STATUSES,` と `TaskKind,` を足す。`build_task` のシグネチャの `linkable_ids: frozenset[str] | None = None,` の次に `kind: TaskKind = TaskKind.NORMAL,` を足す。`base = existing or Task(clean)` の次の行に追加する:

```python
    if kind is TaskKind.CHECKPOINT:
        return _build_checkpoint(
            base, clean, code, deadline, priority, status, color, predecessors, linkable_ids
        )
```

通常のタスクの `return replace(` に `kind=TaskKind.NORMAL,` を足す(チェックポイントから戻すため)。リンクの検証を関数に切り出す: 既存の

```python
    links = list(base.predecessors) if predecessors is None else list(dict.fromkeys(predecessors))
    if predecessors is not None and (
        base.id in links or (linkable_ids is not None and not set(links) <= linkable_ids)
    ):
        raise ValueError("先行タスクが正しくありません")
```

を次の 1 行に置き換える:

```python
    links = _links(base, predecessors, linkable_ids)
```

`build_task` の前に追加する:

```python
def _links(
    base: Task, predecessors: list[str] | None, linkable_ids: frozenset[str] | None
) -> list[str]:
    """先行タスクの入力を検証する。None は既存のまま。重複は除く(順序は保つ)。"""
    links = list(base.predecessors) if predecessors is None else list(dict.fromkeys(predecessors))
    if predecessors is not None and (
        base.id in links or (linkable_ids is not None and not set(links) <= linkable_ids)
    ):
        raise ValueError("先行タスクが正しくありません")
    return links


def _build_checkpoint(
    base: Task,
    name: str,
    code: str,
    deadline: str,
    priority: Priority,
    status: Status,
    color: str,
    predecessors: list[str] | None,
    linkable_ids: frozenset[str] | None,
) -> Task:
    """チェックポイント。締切だけを検証し、開始予定・工数・担当・実績は空にする(隠した欄の入力は見ない)。"""
    try:
        deadline_at = parse_datetime(deadline)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    if deadline_at is None:
        raise ValueError("チェックポイントには締切を入れてください")
    if not MIN_YEAR <= deadline_at.year <= MAX_YEAR:
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if status not in CHECKPOINT_STATUSES:
        raise ValueError("チェックポイントの状態は、未着手か終了にしてください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    return replace(
        base,
        kind=TaskKind.CHECKPOINT,
        name=name,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=deadline_at,
        effort_hours=0.0,
        priority=priority,
        status=status,
        color=color,
        assignee=None,
        allocation=1.0,
        actuals=[],
        project_code=code,
        predecessors=_links(base, predecessors, linkable_ids),
    )
```

(`build_task` の `links = _links(...)` の位置は、`return replace(` の直前のままでよい。チェックポイントの分岐が先に return するので、通常側だけがそれを使う。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_checkpoint.py test/test_forms.py -q`
Expected: PASS

- [ ] **Step 5: ダイアログのテストを書く(失敗させる)**

`test/test_task_dialog.py` の import に `from projectapp.models import ... Status, Task, TaskKind` を足し(`Member`・`Status`・`Task` は既存)、末尾に追加する:

```python
async def set_kind(user: User, kind: TaskKind) -> None:
    user.find(marker="task-kind").elements.pop().set_value(kind)
    await asyncio.sleep(0.1)


async def test_the_kind_toggle_hides_and_shows_the_normal_fields(user: User) -> None:
    mount_dialog(None, [], members=[Member("佐藤")])
    await open_dialog(user)
    await user.should_see(marker="task-start-date")
    await set_kind(user, TaskKind.CHECKPOINT)
    for marker in ("task-start-date", "task-end-date", "task-effort", "task-assignee", "task-actual-progress"):
        await user.should_not_see(marker=marker)
    for marker in ("task-name", "task-deadline-date", "task-predecessors", "task-status", "task-project-code"):
        await user.should_see(marker=marker)
    await set_kind(user, TaskKind.NORMAL)
    await user.should_see(marker="task-start-date")
    await user.should_see(marker="task-effort")


async def test_a_checkpoint_offers_only_two_statuses(user: User) -> None:
    task = Task("c", status=Status.RUNNING)
    mount_dialog(task, [])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    status = user.find(marker="task-status").elements.pop()
    assert list(status.options.values()) == ["未着手", "終了"]
    assert status.value == Status.NOT_STARTED  # 実行中は選べないので、未着手にする
    await set_kind(user, TaskKind.NORMAL)
    assert len(user.find(marker="task-status").elements.pop().options) == 4


async def test_saving_a_checkpoint_clears_the_normal_fields(user: User) -> None:
    saved: list[Task] = []
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 9, 0),
        effort_hours=5.0,
        assignee="佐藤",
    )
    mount_dialog(task, saved, members=[Member("佐藤")])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-deadline-date").type("2026-10-12")
    user.find(marker="task-save").click()
    result = saved[0]
    assert result.kind is TaskKind.CHECKPOINT
    assert result.deadline == datetime(2026, 10, 12, 18, 0)  # 時刻を指定しない締切の、補う時刻
    assert (result.planned_start, result.effort_hours, result.assignee) == (None, 0.0, None)


async def test_a_checkpoint_without_a_deadline_shows_the_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("レビュー")
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-save").click()
    await user.should_see("チェックポイントには締切を入れてください")
    assert saved == []


async def test_the_hint_warns_that_normal_fields_will_be_cleared(user: User) -> None:
    task = Task("設計", planned_start=datetime(2026, 10, 5, 9, 0), effort_hours=5.0)
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-kind-hint")
    await set_kind(user, TaskKind.CHECKPOINT)
    hint = user.find(marker="task-kind-hint").elements.pop()
    assert hint.text == "保存すると、開始予定・工数・担当・実績は消えます"
    await set_kind(user, TaskKind.NORMAL)
    await user.should_not_see(marker="task-kind-hint")


async def test_a_new_checkpoint_has_no_hint(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-kind-hint")


async def test_changing_the_kind_counts_as_an_edit(user: User) -> None:
    mount_dialog(Task("設計"), [])
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")
```

(新規のタスクのダイアログを開く `mount_dialog(None, ...)` は、既存のヘルパーを使う。`datetime`・`asyncio`・`Member` は、ファイルの先頭で import 済み。)

- [ ] **Step 6: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -k "kind or checkpoint"`
Expected: FAIL(`task-kind` がない)

- [ ] **Step 7: `task_dialog.py` を直す**

import に `CHECKPOINT_STATUSES`、`TaskKind` を足す(`from projectapp.models import ...` の既存の一覧に)。

`DateTimeFields.__init__` の、開始予定・完了予定の行を、後で隠せるようにする。次の 2 行

```python
        with ui.row().classes("w-full no-wrap gap-4"):
            self.start_day, self.start_time, self.use_start_time, _ = self._column(
```

を次に置き換える(インデントのある中身は、そのまま):

```python
        self.first_row = ui.row().classes("w-full no-wrap gap-4")
        with self.first_row:
            self.start_day, self.start_time, self.use_start_time, _ = self._column(
```

`open_task_dialog` の、`ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")` の次に追加する(名前の入力の前):

```python
        kind = ui.toggle({k: k.value for k in TaskKind}, value=initial.kind).mark("task-kind")
        kind_hint = ui.label("保存すると、開始予定・工数・担当・実績は消えます").classes(
            "text-caption text-grey"
        ).mark("task-kind-hint")
```

担当者の行を、隠せるようにする。次の 1 行

```python
        with ui.row().classes("w-full no-wrap gap-4"):
            assignee = (
```

を次に置き換える:

```python
        assignee_row = ui.row().classes("w-full no-wrap gap-4")
        with assignee_row:
            assignee = (
```

実績の入力を、1 つの枠に入れる。次の 3 行

```python
        actual_fields: ActualFields | IntervalFields = (
            IntervalFields(initial) if intervals else ActualFields(initial)
        )
```

を次に置き換える:

```python
        with ui.column().classes("w-full") as actual_box:
            actual_fields: ActualFields | IntervalFields = (
                IntervalFields(initial) if intervals else ActualFields(initial)
            )
```

`actual_fields.bind(on_actual_change)` の次の行(`color = ui.color_input(` の前)に追加する:

```python
        has_normal_data = bool(
            initial.planned_start
            or initial.planned_end
            or initial.effort_hours
            or initial.assignee
            or initial.actuals
        )

        def apply_kind(_event: object = None) -> None:
            """チェックポイントでは、開始予定・完了予定・工数・担当・実績の欄を隠し、状態を 2 つにする。"""
            checkpoint = kind.value == TaskKind.CHECKPOINT
            for widget in (fields.first_row, effort, assignee_row, conversion, actual_box):
                widget.set_visibility(not checkpoint)
            allowed = CHECKPOINT_STATUSES if checkpoint else tuple(Status)
            suggest["setting"] = True
            try:
                status.set_options(
                    {s: s.value for s in allowed},
                    value=status.value if status.value in allowed else Status.NOT_STARTED,
                )
            finally:
                suggest["setting"] = False
            kind_hint.set_visibility(
                checkpoint and initial.kind is TaskKind.NORMAL and has_normal_data
            )

        kind.on_value_change(apply_kind)
        apply_kind()
```

`current()` の `name.value,` の次の行に `kind.value,` を足す。`save()` の `build_task(` の引数の `predecessors=merged_predecessors(),` の次の行に `kind=TaskKind(kind.value),` を足す。

- [ ] **Step 8: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py test/test_checkpoint.py -q`
Expected: PASS

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS(既存のダイアログのテストは、トグルの追加で壊れないこと。壊れたら、レイアウトの前提を確かめて直す)

- [ ] **Step 9: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py test/
git commit -m "feat: 編集ダイアログに種別のトグルを足し、チェックポイントの保存を検証する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ガントチャートの描画(◆・チップ・矢印)

**Files:**
- Modify: `src/projectapp/gantt.py`(定数、`task_row`、`task_chips`、`link_bars`、`checkpoint_marker`)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `Task.kind`、`Schedule`(Task 1・2)
- Produces: マーカー `checkpoint-<key>-<ti>`(◆)、定数 `CHECKPOINT_MARKER_PX`

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_gantt.py` の import(`from projectapp.gantt import (...)`)に `CHECKPOINT_MARKER_PX,` を足し、`from projectapp.models import ...` に `TaskKind` を足す。末尾に追加する:

```python
def checkpoint_project(**fields: object) -> Project:
    cp = Task(
        "中間レビュー",
        id="cccccccc",
        kind=TaskKind.CHECKPOINT,
        deadline=datetime(2026, 10, 7, 12, 0),
        **fields,  # type: ignore[arg-type]
    )
    normal = Task("通常", id="nnnnnnnn", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5)
    return Project("demo", base_date=BASE, sections=[Section("開発", [cp, normal])])


async def test_a_checkpoint_is_a_diamond_without_a_bar(user: User) -> None:
    mount(checkpoint_project())
    await user.open("/")
    marker = user.find(marker="checkpoint-0-0").elements.pop()
    day = COLUMN_WIDTH_PX[Scale.DAY]
    assert marker._style["left"] == from_name(2.5 * day - CHECKPOINT_MARKER_PX / 2)  # 10/7 12:00
    assert marker._style["color"] == STATUS_COLOR_VAR
    assert marker._style["font-size"] == f"{CHECKPOINT_MARKER_PX}px"
    assert "status-not-started" in marker.classes
    assert "◆" in marker.text
    await user.should_not_see(marker="bar-0-0")
    await user.should_not_see(marker="deadline-0-0")  # 締切の小さな ◆ は出さない
    user.find(marker="bar-0-1")  # 通常タスクは、これまでどおり


async def test_clicking_a_checkpoint_opens_the_editor(user: User) -> None:
    recorder = mount(checkpoint_project())
    await user.open("/")
    user.find(marker="checkpoint-0-0").click()
    assert ("edit_task", (0, 0)) in recorder.events


async def test_a_finished_checkpoint_is_grey_and_struck_through_without_chips(user: User) -> None:
    mount(checkpoint_project(status=Status.DONE))
    await user.open("/")
    assert "status-done" in user.find(marker="checkpoint-0-0").elements.pop().classes
    assert user.find(marker="task-name-0-0").elements.pop()._style["text-decoration"] == "line-through"
    await user.should_not_see(marker="task-progress-0-0")  # 進捗度はないので、100% のチップも出さない


async def test_a_checkpoint_row_is_red_after_its_deadline(user: User) -> None:
    mount(checkpoint_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    assert user.find(marker="row-0-0").elements.pop()._style["background"] == OVERDUE_COLOR


async def test_a_checkpoint_row_is_red_when_its_predecessors_will_miss_it(user: User) -> None:
    project = checkpoint_project(predecessors=["nnnnnnnn"])
    project.sections[0].tasks[1].effort_hours = 26  # 木曜 15:30 まで。締切(水曜 12:00)に間に合わない
    mount(project)  # 現在時刻は 10/1(締切の前)
    await user.open("/")
    assert user.find(marker="row-0-0").elements.pop()._style["background"] == OVERDUE_COLOR


async def test_a_normal_row_is_not_red_before_its_deadline(user: User) -> None:
    mount(checkpoint_project())
    await user.open("/")
    assert "background" not in user.find(marker="row-0-0").elements.pop()._style


async def test_an_arrow_ends_at_the_diamonds_left_edge(user: User) -> None:
    project = checkpoint_project(predecessors=["nnnnnnnn"])
    mount(project)
    await user.open("/")
    day = COLUMN_WIDTH_PX[Scale.DAY]
    pred_right = 15.5 / 24 * day  # 通常タスク: 月 15:30 まで
    cp_left = 2.5 * day - CHECKPOINT_MARKER_PX / 2  # ◆ の左端
    first_row = ADD_ROW_HEIGHT_PX + ROW_HEIGHT_PX  # 追加行と見出しの下が、行の上端
    cp_y = first_row + ROW_HEIGHT_PX / 2  # 1 行目: チェックポイント
    normal_y = first_row + ROW_HEIGHT_PX + ROW_HEIGHT_PX / 2  # 2 行目: 通常タスク
    content = user.find(marker="links").elements.pop().content
    found = re.search(r'<path data-link="nnnnnnnn-cccccccc" d="([^"]+)"', content)
    assert found is not None
    assert found.group(1) == (
        f"M{pred_right:g},{normal_y:g} L{pred_right + 6:g},{normal_y:g}"
        f" L{pred_right + 6:g},{cp_y:g} L{cp_left:g},{cp_y:g}"
    )


async def test_a_checkpoint_is_hidden_by_the_assignee_filter(user: User) -> None:
    project = checkpoint_project()
    project.members.append(Member("佐藤"))
    charts, _ = mount_chart(project)
    await user.open("/")
    charts[0].set_filter(TaskFilter(assignee="佐藤"))
    await user.should_not_see(marker="checkpoint-0-0")


async def test_a_checkpoint_outside_the_period_has_no_diamond(user: User) -> None:
    project = checkpoint_project()
    project.sections[0].tasks[0].deadline = datetime(2026, 12, 1, 12, 0)  # 最小列数(42 日)の外
    charts, _ = mount_chart(project)
    await user.open("/")
    charts[0].set_options(ViewOptions(period=(date(2026, 10, 5), date(2026, 10, 5)), read_only=True))
    await user.should_not_see(marker="checkpoint-0-0")
```

(通常タスクは 2 行目にあり、先行(通常)から後続(チェックポイント)への矢印は、上向きになる。`Status`・`Member`・`re`・`date`・`TaskFilter`・`ViewOptions`・`OVERDUE_COLOR`・`STATUS_COLOR_VAR`・`ADD_ROW_HEIGHT_PX`・`ROW_HEIGHT_PX`・`from_name`・`mount_chart` は、`test_gantt.py` に import・定義済み。無ければ import に足す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "checkpoint or diamond"`
Expected: FAIL(`CHECKPOINT_MARKER_PX` がない)

- [ ] **Step 3: `gantt.py` を直す**

import の `from projectapp.models import Priority, Project, Section, Status, Task` に `TaskKind` を足す。`DEADLINE_COLOR = ...` の次に定数を追加する:

```python
CHECKPOINT_MARKER_PX = 20  # チェックポイントの ◆ の大きさ(締切の小さな ◆ より大きい)
```

`task_row` の、名前の欄の `with cell:` ブロックを閉じた直後の行(`end = effective_end(...)` ではなく、`start = self.schedule.start(task)` の直前。`with cell:` と同じインデント位置)に追加する:

```python
            if task.kind is TaskKind.CHECKPOINT:  # バーも実績もなく、◆ だけを出す
                self.checkpoint_marker(si, ti, task, columns, width)
                return row
```

(`return row` は、`with row:` の中にある。`task_row` の末尾の `return row` と同じ値を返す。)

`task_chips` の進捗のチップを、通常のタスクだけにする。次の 3 行

```python
        percent = fill_percent(task)
        if percent is not None:
```

を次に置き換える:

```python
        percent = None if task.kind is TaskKind.CHECKPOINT else fill_percent(task)
        if percent is not None:
```

`deadline_marker` の前に追加する:

```python
    def checkpoint_marker(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """チェックポイントの ◆。締切の位置・行の中央。表示範囲の外なら出さない。"""
        if task.deadline is None:
            return
        position = deadline_position(task.deadline, columns)
        if position is None:
            return
        key = "top" if si is None else si
        left = position * width - CHECKPOINT_MARKER_PX / 2
        marker = ui.label("◆").style(
            f"position: absolute; left: {from_name(left)}; top: 0; width: {CHECKPOINT_MARKER_PX}px;"
            f" height: {ROW_HEIGHT_PX}px; line-height: {ROW_HEIGHT_PX}px; text-align: center;"
            f" font-size: {CHECKPOINT_MARKER_PX}px; color: {STATUS_COLOR_VAR}; cursor: pointer;"
            " user-select: none"
        ).classes(STATUS_CLASSES[task.status])
        self.edit_on_click(marker, si, ti)
        marker.tooltip(f"チェックポイント {task.deadline:%Y-%m-%d %H:%M}").mark(
            f"checkpoint-{key}-{ti}"
        )
```

`link_bars` の、棒の左端・右端を作る 2 行

```python
            left = span[0] * width
            bars[task.id] = Bar(left, left + max(span[1] * width, MIN_BAR_PX))
```

を次に置き換える:

```python
            left = span[0] * width
            if task.kind is TaskKind.CHECKPOINT:  # ◆ の左右の端に、矢印をつなぐ
                half = CHECKPOINT_MARKER_PX / 2
                bars[task.id] = Bar(left - half, left + half)
            else:
                bars[task.id] = Bar(left, left + max(span[1] * width, MIN_BAR_PX))
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "checkpoint or diamond"`
Expected: PASS(座標の期待値の差は、`link_points` の規則から計算し直して、実装でなくテストの式を直す。先行の右端と ◆ の左端の間が 12px 以上なので、4 点の経路になる)

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: チェックポイントの ◆ をガントチャートに描き、矢印をつなぐ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ダッシュボードと文書

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_progress`)
- Modify: `docs/development.md`、`CLAUDE.md`(`projectapp/CLAUDE.md`)、`.claude/MEMORY.md`
- Test: `test/test_checkpoint.py`

**Interfaces:**
- Consumes: `Task.kind`(Task 1)、`is_overdue` の見込みの超過(Task 2)

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_checkpoint.py` の import に追加する:

```python
from projectapp.dashboard import Period, summarize_due, summarize_progress, summarize_workload
```

末尾に追加する:

```python
def test_a_project_of_only_checkpoints_has_no_progress_percent() -> None:
    progress = summarize_progress(project(checkpoint("c")), {}, MON)
    assert progress.percent is None
    assert progress.counts[Status.NOT_STARTED] == 1  # 件数には含める


def test_checkpoints_do_not_weigh_the_progress_percent() -> None:
    done = work("a", effort_hours=10, status=Status.DONE)
    progress = summarize_progress(project(done, checkpoint("c")), {}, MON)
    assert progress.percent == 100.0


def test_a_missed_checkpoint_is_listed_as_overdue_with_its_deadline() -> None:
    a = work("a", planned_start=MON, effort_hours=26)  # 木曜 15:30 まで
    c = checkpoint("c", WED_NOON, "a")
    progress = summarize_progress(project(a, c), {}, MON)  # 現在時刻は締切の前でも、見込みで超過
    rows = [row for row in progress.overdue if row.name == "c"]
    assert len(rows) == 1 and rows[0].limit == WED_NOON


def test_a_checkpoint_appears_once_in_the_due_list() -> None:
    c = checkpoint("c", WED_NOON)
    period = Period(datetime(2026, 10, 5).date(), datetime(2026, 10, 9).date())
    rows = summarize_due(project(c), period, MON, {})
    assert [(row.kind, row.name) for row in rows] == [("締切", "c")]


def test_checkpoints_are_left_out_of_the_workload() -> None:
    period = Period(datetime(2026, 10, 5).date(), datetime(2026, 10, 9).date())
    assert summarize_workload(project(checkpoint("c", WED_NOON)), period, MON, {}) == []
```

(`DueRow` の項目名は `dashboard.py` の定義に合わせる。`kind` と `name` でなければ直す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_checkpoint.py -q -k "progress or overdue_with or due_list or workload"`
Expected: FAIL(進捗率・見込みの超過の例外)

- [ ] **Step 3: `dashboard.py` を直す**

import に `from projectapp.models import Project, Status, TaskKind` を直す(`Status` と `Project` の既存の import に `TaskKind` を足す)。`summarize_progress` のループを、次のとおりにする:

```python
    for task in project.all_tasks():
        counts[task.status] += 1
        if task.kind is not TaskKind.CHECKPOINT:  # 節目は、工数がないので進捗率の重みに入れない
            weight = _weight(task.effort_hours)
            percent = 100 if task.status is Status.DONE else (current_progress(task) or 0)
            weighted += weight * percent
            total += weight
        if task.status is not Status.DONE and is_overdue(task, project, holidays, now, schedule):
            moment = actual_end(task) or now
            limits = [
                limit
                for limit in (task.deadline, schedule.end(task))
                if limit is not None and moment > limit
            ]
            limit = min(limits, default=task.deadline or now)  # 見込みの超過は、締切を基準にする
            overdue.append(OverdueRow(task.name, task.assignee, limit))
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_checkpoint.py -q`
Expected: PASS

- [ ] **Step 5: 文書を更新する**

`docs/development.md` の「ファイル形式の注意」の、「`Task.id`(8 桁の 16 進…」の項目の前に追加する:

```markdown
- `Task.kind`(`TaskKind`。`"通常"` / `"チェックポイント"`)。保存は `"kind"`(キーなし・`null` は通常。不正な値は読込を拒否)。チェックポイントは、締切が必須で、状態は未着手か終了だけ(`CHECKPOINT_STATUSES`)。読込(`storage._checkpoint`)は、締切なし・状態の不正を拒否し、開始予定・完了予定・工数・担当・割り当て率・実績が入っていても使わず空にする。保存(`forms.build_task`)も、それらを空にし、隠した欄の入力は検証しない。`Schedule` は、チェックポイントの実効の開始・完了をどちらも締切にする(押し出されない。先行にすると後続を締切まで押し出す)。`is_overdue` は、チェックポイントだけ、先行の完了が締切を超える見込みでも超過とする(通常タスクは現在時刻だけ)。ガントチャートは、バー・実績・縞・進捗のチップを出さず、`checkpoint-<key>-<ti>` の大きめの ◆(状態の色。`CHECKPOINT_MARKER_PX`)を、締切の位置・行の中央に出す(`task_row` の早期 return)。矢印は ◆ の左右の端につなぐ。ダッシュボードは、状態別の件数に含め、進捗率の重みからは外す。人ごとの負荷・工数・担当者向けの書き出しは、担当と工数がないので対象外。編集ダイアログは、種別のトグル(`task-kind`)で、開始予定・完了予定・工数・担当・実績の欄を隠し、状態を 2 つにする。
```

`CLAUDE.md`(`projectapp/CLAUDE.md`)の、「`ガントチャート`のアイテムの状態は…」の行の次に追加する:

```markdown
- タスクには種別(`通常`・`チェックポイント`)があり、編集ダイアログのトグルで選ぶ。`チェックポイント`は、`締切`だけを持つ節目(必須。状態は`未着手`・`終了`だけ)で、`開始予定`・`完了予定`・`工数`・`担当`・`実績`は持たない。ガントチャートでは、バーを出さず、状態の色の大きめの`◆`を、締切の位置に出す(通常タスクの締切の小さな橙の`◆`とは区別する)。先行にすると、その日時まで後続が押し出され、後続にすると、先行の完了が締切を超える見込みのとき、行を赤くする(通常タスクは、現在時刻が締切を過ぎたときだけ)
```

`.claude/MEMORY.md` の「次にやること」「今後の要望」の、要望 21 の行に `(完了)` を足し、「現在の状況」の要約に、チェックポイントの項目(日付 2026-10-08、ブランチ `feature/checkpoint`、設計書 `2026-10-08-checkpoint-design.md`、実装計画 `2026-10-08-checkpoint.md`、実機確認待ち)を足す。参照先の設計書・実装計画の一覧にも、2 つのファイル名を足す。

- [ ] **Step 6: 最終確認と、コミット**

Run: `uv run pytest -n auto -q`、`uvx ty check src`、`uv run pytest -q`(直列)
Expected: すべて PASS

Run: `grep -rn "task.kind\|TaskKind" src/projectapp | grep -v "^src/projectapp/\(models\|storage\|forms\|task_dialog\|timeline\|gantt\|dashboard\).py"`
Expected: 出力なし(上の 7 つ以外に、種別の分岐がないこと)

```bash
git add src/projectapp/dashboard.py test/test_checkpoint.py docs/development.md CLAUDE.md .claude/MEMORY.md
git commit -m "feat: ダッシュボードのチェックポイントの扱いと、文書を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実機確認(ネイティブ。`uv run projectapp`): 確認用に `~/.projectapp/チェックポイントテスト.json` を作り、◆ の見た目(ライト・ダーク、日次・週次・月次)、先行・後続の矢印(◆ の左右の端)、赤み(締切超過・見込みの超過)、ダイアログの切り替え(欄の出し入れ・状態の選択肢・ヒント)、通常タスクへ戻す、プレビューと PNG、ダッシュボードを確かめる。

---

## Self-Review(計画の作成者の確認)

**設計書との対応:** §2 データ → Task 1。§3 日程 → Task 2。§4 ダイアログ → Task 3。§5 描画 → Task 4。§6 ダッシュボード・書き出し → Task 5(書き出し・負荷・工数は、テストで対象外を確かめる)。§8 テスト → 各タスク。実機確認 → Task 5 の最後。

**型・名前の一貫性:** `TaskKind`、`CHECKPOINT_STATUSES`、`Task.kind`、`_checkpoint`(storage)、`_build_checkpoint`・`_links`(forms)、`apply_kind`・`kind_hint`・`assignee_row`・`actual_box`・`fields.first_row`(dialog)、`checkpoint_marker`・`CHECKPOINT_MARKER_PX`(gantt)は、定義するタスクと使うタスクで同じ。マーカー `task-kind`・`task-kind-hint`・`checkpoint-<key>-<ti>` も、テストと実装で同じ。

**実装時に実行して確かめる点:** Task 3 の既存のダイアログのテストが、トグル追加と実績の枠(`ui.column`)で壊れないこと(レイアウトの前提)、Task 4 の矢印の座標(`link_points` の 4 点の経路)、Task 5 の `DueRow` の項目名。
