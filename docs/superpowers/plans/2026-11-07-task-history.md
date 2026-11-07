# 変更履歴と「期間中に進んだ分」の集計 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの状態・進捗度・工数の変化をプロジェクト全体のログに追記し、`チーム全体の進捗`に「期間中に進んだ分(進捗率の増分)」を出す(要望 128 の段階 1)。

**Architecture:** `models.py`に`HistoryEvent`・`Change`と`Project.history`・`history_since`を足し、ファイル形式を`version` 21 にする。記録・復元・補正・和集合は NiceGUI に依存しない新モジュール`history_log.py`に閉じ込める(将来データの持ち方を変えるときの境界)。記録の入口は`views.MainView.after_edit`(変更前後の`Project`の差分)と、CSV・PlantUML の取り込み。集計は`dashboard.summarize_progress_delta`、表示は`dashboard_view.team_card`の 1 行。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、ruff、ty。

**Spec:** `docs/superpowers/specs/2026-11-07-task-history-design.md`(この計画は下の「設計書との差」を含めて実装する。Task 8 で設計書も直す)

## 設計書との差(この計画で確定)

- `history_since`は「最初に保存した日時」ではなく、**最初に記録した編集の時刻**(`record_edit`の`now`)と、**取り込みの時刻**にする。保存は記録の条件にしない。
- 補正イベント(`reconcile`)は**マージの後だけ**。ファイルを開くときは、開いただけで内容が変わらないよう補正しない。
- メンバー・チームの絞り込みでの按分はしない。既存の`チーム全体の進捗`と同じく、`_entries(..., member)`が選んだタスクを丸ごと 1 回数える。
- 対象は`kind`が`NORMAL`のタスクだけ(まとめ・チェックポイント・参照は記録しない)。

## Global Constraints

- 言語は日本語(コメント・docstring・通知・コミットメッセージ)。Python 3.13 以上。ライブラリは NiceGUI。
- `FORMAT_VERSION`を 20 → 21 にする。キーのない古いファイルは`history=[]`・`history_since=None`で読む。不正な値は`ValueError`で拒否し、新しい`version`は既存の`_check_version`が拒否する。
- 保存は既存の`save_project`(一時ファイル経由)のまま変えない。
- 完了予定は保存しない・絞り込みや折りたたみは保存しない(既存の約束)。履歴は保存する。
- 集計は`timeline.py`と同様に NiceGUI から切り離した純粋関数にする(`history_log.py`・`dashboard.py`)。
- 実装の完了時: `uv run pytest -m smoke`(失敗したときに限り`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`。
- ブランチは git-flow(`develop`から`feature/task-history`)。マージは利用者の指示を待つ(PR を作って止まる)。
- コミットメッセージの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。

## Review Focus

- 一括編集 1 回で複数タスクが変わる: タスクごとに 1 件ずつ記録され、`元に戻す` 1 回で全部のイベントが消える(Task 2)。
- 元に戻す → やり直しで、イベントが元の日時のまま復活する(Task 2)。
- 状態だけ・進捗度だけ・工数だけの変更が、それぞれ変えた項目だけのイベントになり、変えていない項目は入らない(Task 2)。
- まとめ・チェックポイントを編集しても記録しない。通常タスクをまとめに変えたときも記録しない(Task 2)。
- 記録開始日より前の期間は「不明」で、現在の値で代用しない(Task 4・6)。
- 期間の途中で作られたタスクの進捗は「進んだ分」に入らず、`範囲`に入る(Task 6)。
- 双方が同じ項目を別の値に変えた 3 者マージで、現在の値とログの最後が食い違わない(補正イベント。Task 5)。
- v20 のファイルが開け、保存すると v21 になる。壊れた`history`は拒否される(Task 1)。
- 切り出したタスクのイベントが子へ移り、親に残らない(Task 7)。

---

## Task 1: モデル・ファイル形式(version 21)

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION`・新しい型・`Project`)
- Modify: `src/projectapp/storage.py`(`_dump`・`parse_project`・新しい`_history`)
- Create: `test/test_history_log.py`
- Modify: `test/test_storage.py`・`test/test_reference_storage.py`(`== 20` を 21 に)

**Interfaces:**
- Produces(以降のタスクが使う):
  - `models.HISTORY_FIELDS: tuple[str, ...] = ("status", "progress", "effort")`
  - `models.Value = str | int | float | None`
  - `models.Change(field: str, before: Value, after: Value)`(frozen)
  - `models.HistoryEvent(task: str, at: datetime, changes: tuple[Change, ...])`(frozen。`__deepcopy__`で自分を返す)
  - `Project.history: list[HistoryEvent]`、`Project.history_since: datetime | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_history_log.py`を新規作成:

```python
"""変更履歴(要望 128)。NiceGUI に依存しない部分。"""

import json
from copy import deepcopy
from datetime import datetime

import pytest

from projectapp.models import Change, HistoryEvent, Project
from projectapp.storage import dumps_project, parse_project

pytestmark = pytest.mark.smoke


def ev(task: str, at: datetime, **fields: tuple) -> HistoryEvent:
    """`ev("a", at, status=("未着手", "実行中"), progress=(None, 30))`。項目は status, progress, effort の順で渡す。"""
    return HistoryEvent(
        task, at, tuple(Change(name, b, a) for name, (b, a) in fields.items())
    )


NOV8 = datetime(2026, 11, 8, 10, 0)


def test_history_round_trips_through_the_file() -> None:
    project = Project(
        "p",
        history=[ev("t1", NOV8, status=("未着手", "実行中"), progress=(None, 30))],
        history_since=datetime(2026, 11, 8, 9, 0),
    )
    loaded = parse_project(dumps_project(project), "p")
    assert loaded.history == project.history
    assert loaded.history_since == project.history_since


def test_a_version_20_file_is_read_without_history() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = 20
    del raw["history"], raw["history_since"]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.history == [] and loaded.history_since is None


@pytest.mark.parametrize(
    "bad",
    [
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"status": ["未着手", "x"]}},
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"name": ["a", "b"]}},
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {}},
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"progress": [None, 101]}},
        {"task": "t", "at": "2026-11-08T10:00:00", "changes": {"effort": [None, -1]}},
        {"task": "", "at": "2026-11-08T10:00:00", "changes": {"progress": [0, 1]}},
        {"task": "t", "at": "not-a-date", "changes": {"progress": [0, 1]}},
        {"task": "t", "changes": {"progress": [0, 1]}},
    ],
)
def test_a_broken_history_entry_is_rejected(bad: dict) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["history"] = [bad]
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_copying_a_project_shares_the_events() -> None:
    event = ev("t1", NOV8, progress=(None, 30))
    assert deepcopy(event) is event
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_history_log.py -q`
Expected: FAIL(`ImportError: cannot import name 'Change'`)

- [ ] **Step 3: モデルを実装する**

`src/projectapp/models.py`:

1. `FORMAT_VERSION = 20` を 21 にし、末尾の括弧内の一覧に `。21: 変更履歴 history・history_since` を足す(`20: タスクの追加工数 extra_efforts` の後)。
2. `class ExtraEffort` の定義の後ろに追加:

```python
HISTORY_FIELDS = ("status", "progress", "effort")  # 変更履歴に残す項目(この順で並べる)
Value = str | int | float | None  # 変更履歴の値。状態は Status.value の文字列


@dataclass(frozen=True)
class Change:
    """変更履歴の 1 項目の変化。作成のときは、各項目の before が None。"""

    field: str
    before: Value
    after: Value


@dataclass(frozen=True)
class HistoryEvent:
    """1 回の編集で、1 タスクの対象項目が変わった記録(要望 128)。追記のみで、書き換えない。"""

    task: str
    at: datetime
    changes: tuple[Change, ...]

    def __deepcopy__(self, memo: dict) -> "HistoryEvent":
        return self  # 不変なので、元に戻すの複製で増やさない
```

3. `class Project` の`ratio_limit_lower`の次の行に追加:

```python
    history: list[HistoryEvent] = field(
        default_factory=list
    )  # タスクの状態・進捗度・工数の変更履歴(追記のみ。削除したタスクの分も残す)
    history_since: datetime | None = None  # 履歴を記録し始めた日時。これより前は不明
```

- [ ] **Step 4: 保存・読込を実装する**

`src/projectapp/storage.py`:

1. `from projectapp.models import (...)`に`HISTORY_FIELDS`・`Change`・`HistoryEvent`・`Value`を足す(`Status`が無ければ足す。`from math import isfinite`も足す)。
2. `_dump`の`data = {...}`の直後に追加:

```python
    data["history"] = [
        {
            "task": event.task,
            "at": event.at,
            "changes": {c.field: [c.before, c.after] for c in event.changes},
        }
        for event in project.history
    ]
```

3. `_history`と`_history_value`を、`_datetime`の下に追加:

```python
def _history_value(name: str, value: Any) -> Value:
    if value is None:
        return None
    if name == "status":
        try:
            return Status(value).value
        except ValueError:
            raise ValueError(f"history の状態が正しくありません: {value!r}") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"history の値が正しくありません: {name}={value!r}")
    if name == "progress":
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(f"history の進捗度が正しくありません: {value!r}")
        return value
    if not isfinite(value) or value < 0:
        raise ValueError(f"history の工数が正しくありません: {value!r}")
    return float(value)


def _history(raw: Any) -> list[HistoryEvent]:
    """変更履歴を読む。形が違う・未知の項目・範囲外の値は ValueError。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("history が正しくありません")
    events = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("history の要素が正しくありません")
        task = item.get("task")
        if not isinstance(task, str) or not task:
            raise ValueError(f"history の task が正しくありません: {task!r}")
        at = _datetime(item.get("at"))
        if at is None:
            raise ValueError("history の at がありません")
        raw_changes = item.get("changes")
        if not isinstance(raw_changes, dict) or not raw_changes:
            raise ValueError("history の changes が正しくありません")
        if unknown := set(raw_changes) - set(HISTORY_FIELDS):
            raise ValueError(f"history に知らない項目があります: {sorted(unknown)}")
        changes = []
        for name in HISTORY_FIELDS:
            if name not in raw_changes:
                continue
            pair = raw_changes[name]
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"history の {name} が正しくありません")
            changes.append(
                Change(name, _history_value(name, pair[0]), _history_value(name, pair[1]))
            )
        events.append(HistoryEvent(task, at, tuple(changes)))
    return events
```

4. `parse_project`の`Project(...)`の引数、`ratio_limit_lower=ratio_limits.lower,`の次に追加:

```python
        history=_history(raw.get("history")) if ctx.version >= 21 else [],
        history_since=_datetime(raw.get("history_since"))
        if ctx.version >= 21
        else None,
```

- [ ] **Step 5: 既存テストのバージョンを直す**

Run: `grep -n "== 20\b" test/test_storage.py test/test_reference_storage.py`

`FORMAT_VERSION == 20`は`FORMAT_VERSION == 21`に、保存して読んだ`raw["version"] == 20`は`== 21`に直す(古いファイルを作る側の`"version": 20`や、v20 のファイルを読むテストは直さない)。

- [ ] **Step 6: テストを通す**

Run: `uv run pytest test/test_history_log.py test/test_storage.py test/test_reference_storage.py -q`
Expected: すべて PASS

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/
git commit -m "feat: 変更履歴のモデルとファイル形式(version 21。要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 2: 編集の差分を記録する(`after_edit`)

**Files:**
- Create: `src/projectapp/history_log.py`
- Modify: `src/projectapp/views.py`(`after_edit`)
- Test: `test/test_history_log.py`、`test/test_bulk_view.py`

**Interfaces:**
- Consumes: Task 1 の`Change`・`HistoryEvent`・`HISTORY_FIELDS`・`Value`
- Produces:
  - `history_log.diff_events(before: Project, after: Project, now: datetime) -> list[HistoryEvent]`
  - `history_log.creation_events(project: Project, now: datetime) -> list[HistoryEvent]`
  - `history_log.record_edit(before: Project, after: Project, now: datetime) -> None`(`after.history`に足し、`history_since`が`None`なら`now`にする)
  - `history_log.stamp_creation(project: Project, now: datetime) -> None`(取り込み用)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_history_log.py`の末尾に追加(先頭の import に`from dataclasses import replace`、`from projectapp.history_log import diff_events, record_edit, stamp_creation`、`from projectapp.models import Section, Status, Task, TaskKind`を足す):

```python
NOW = datetime(2026, 11, 9, 9, 0)


def project_of(*tasks: Task) -> Project:
    return Project("p", tasks=list(tasks))


def test_a_status_change_records_only_the_changed_fields() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    after = deepcopy(before)
    after.tasks[0].status = Status.RUNNING
    assert diff_events(before, after, NOW) == [
        ev("a", NOW, status=("未着手", "実行中"))
    ]


def test_status_and_progress_changed_together_make_one_event() -> None:
    before = project_of(Task("a", id="a", effort_hours=8, progress=50, status=Status.RUNNING))
    after = deepcopy(before)
    after.tasks[0].status = Status.DONE
    after.tasks[0].progress = 100
    assert diff_events(before, after, NOW) == [
        ev("a", NOW, status=("実行中", "終了"), progress=(50, 100))
    ]


def test_an_effort_change_uses_the_total_with_extra_efforts() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    after = deepcopy(before)
    after.tasks[0].effort_hours = 12
    assert diff_events(before, after, NOW) == [ev("a", NOW, effort=(8.0, 12.0))]


def test_a_new_task_records_a_creation_event_with_every_field() -> None:
    before = project_of()
    after = project_of(Task("a", id="a", effort_hours=8))
    assert diff_events(before, after, NOW) == [
        ev("a", NOW, status=(None, "未着手"), progress=(None, None), effort=(None, 8.0))
    ]


def test_a_deleted_task_and_an_unchanged_one_record_nothing() -> None:
    before = project_of(Task("a", id="a"), Task("b", id="b"))
    after = project_of(Task("b", id="b"))
    assert diff_events(before, after, NOW) == []


def test_summaries_checkpoints_and_references_are_not_recorded() -> None:
    kinds = (TaskKind.SUMMARY, TaskKind.CHECKPOINT, TaskKind.REFERENCE)
    before = project_of()
    after = project_of(*[Task(k.name, id=k.name, kind=k) for k in kinds])
    assert diff_events(before, after, NOW) == []


def test_turning_a_normal_task_into_a_summary_records_nothing() -> None:
    before = project_of(Task("a", id="a", effort_hours=8))
    after = deepcopy(before)
    after.tasks[0].kind = TaskKind.SUMMARY
    assert diff_events(before, after, NOW) == []


def test_tasks_inside_sections_are_recorded() -> None:
    before = Project("p", sections=[Section("s", [Task("a", id="a")])])
    after = deepcopy(before)
    after.sections[0].tasks[0].progress = 20
    assert diff_events(before, after, NOW) == [ev("a", NOW, progress=(None, 20))]


def test_record_edit_appends_and_sets_the_start_once() -> None:
    before = project_of(Task("a", id="a"))
    after = deepcopy(before)
    after.tasks[0].progress = 20
    record_edit(before, after, NOW)
    assert after.history_since == NOW and len(after.history) == 1
    later = datetime(2026, 11, 10, 9, 0)
    again = deepcopy(after)
    again.tasks[0].progress = 40
    record_edit(after, again, later)
    assert again.history_since == NOW and len(again.history) == 2


def test_stamp_creation_records_every_normal_task_and_the_start() -> None:
    project = project_of(
        Task("a", id="a", effort_hours=2, progress=30, status=Status.RUNNING),
        Task("c", id="c", kind=TaskKind.CHECKPOINT),
    )
    stamp_creation(project, NOW)
    assert project.history_since == NOW
    assert project.history == [
        ev("a", NOW, status=(None, "実行中"), progress=(None, 30), effort=(None, 2.0))
    ]
```

`test/test_bulk_view.py`の末尾に追加(`open_view`・`BulkChanges`・`EffortChange`・`EffortMode`は既存の import を使う):

```python
async def test_a_bulk_edit_records_one_event_per_task_and_undo_removes_them(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    assert view.project.history == []
    view.apply_bulk(["a", "b"], BulkChanges(effort=EffortChange(EffortMode.SET, 5)))
    assert sorted(e.task for e in view.project.history) == ["a", "b"]
    assert view.project.history_since is not None
    redone_events = list(view.project.history)
    view.undo()
    assert view.project.history == []  # 元に戻すと、記録も戻る
    view.redo()
    assert view.project.history == redone_events  # やり直すと、同じ日時で復活する
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_history_log.py test/test_bulk_view.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.history_log`)

- [ ] **Step 3: `history_log.py`を実装する**

`src/projectapp/history_log.py`を新規作成:

```python
"""変更履歴(要望 128)。タスクの状態・進捗度・工数の変化を、プロジェクト全体のログ(`Project.history`)に追記する。

NiceGUI に依存しない。データの持ち方を変えるときは、この境界の内側で変える(集計と画面はここの関数だけを通す)。
"""

from datetime import datetime

from projectapp.models import (
    HISTORY_FIELDS,
    Change,
    HistoryEvent,
    Project,
    Task,
    TaskKind,
    Value,
)


def _recordable(task: Task) -> bool:
    """記録の対象は通常タスクだけ。まとめは子から算出し、節目は進捗度を持たず、参照は参照先の値。"""
    return task.kind is TaskKind.NORMAL


def _values(task: Task) -> dict[str, Value]:
    return {
        "status": task.status.value,
        "progress": task.progress,
        "effort": task.total_effort,
    }


def creation_events(project: Project, now: datetime) -> list[HistoryEvent]:
    """いまある通常タスクすべての作成イベント(各項目の before は None)。"""
    return [
        HistoryEvent(
            task.id,
            now,
            tuple(Change(name, None, _values(task)[name]) for name in HISTORY_FIELDS),
        )
        for task in project.all_tasks()
        if _recordable(task)
    ]


def diff_events(before: Project, after: Project, now: datetime) -> list[HistoryEvent]:
    """編集の前後の差から、タスクごとに 1 件のイベントを作る。新しい通常タスクは作成イベント、消えたタスクは記録しない。"""
    old = {t.id: t for t in before.all_tasks() if _recordable(t)}
    events = []
    for task in after.all_tasks():
        if not _recordable(task):
            continue
        new = _values(task)
        if task.id not in old:
            changes = tuple(Change(name, None, new[name]) for name in HISTORY_FIELDS)
        else:
            was = _values(old[task.id])
            changes = tuple(
                Change(name, was[name], new[name])
                for name in HISTORY_FIELDS
                if was[name] != new[name]
            )
        if changes:
            events.append(HistoryEvent(task.id, now, changes))
    return events


def record_edit(before: Project, after: Project, now: datetime) -> None:
    """編集の前後の差を`after.history`に足す。記録を始めた日時は、最初の編集の時刻にする。"""
    after.history.extend(diff_events(before, after, now))
    if after.history_since is None:
        after.history_since = now


def stamp_creation(project: Project, now: datetime) -> None:
    """取り込んだ(保存前の新規の)プロジェクトに、作成イベントと記録の開始を入れる。"""
    project.history.extend(creation_events(project, now))
    project.history_since = now
```

- [ ] **Step 4: `after_edit`に組み込む**

`src/projectapp/views.py`の`after_edit`を次のようにする(`from projectapp import history_log`を import に足す。`clock`は既に import されている):

```python
    def after_edit(self) -> None:
        """編集のあとの共通の処理。直前の確定した状態と違えば履歴に積み、画面を描き直す(Undo の入口はここだけ)。
        変更履歴(要望 128)も、ここで前後の差から作る。元に戻す側の複製には新しいイベントを入れない。"""
        if self.project != self.committed:
            self.history.record(self.committed)
            history_log.record_edit(self.committed, self.project, clock.now())
            self.committed = deepcopy(self.project)
        self.gantt.set_project(self.project)
```

- [ ] **Step 5: テストを通す**

Run: `uv run pytest test/test_history_log.py test/test_bulk_view.py test/test_history.py -q`
Expected: すべて PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/history_log.py src/projectapp/views.py test/
git commit -m "feat: 編集の差分から変更履歴を記録する(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 3: 取り込み(CSV・PlantUML)で作成イベントを入れる

**Files:**
- Modify: `src/projectapp/csv_import.py`(`parse_csv`)
- Modify: `src/projectapp/puml_import.py`(`parse_plantuml`)
- Test: `test/test_csv_import.py`、`test/test_puml_import.py`

**Interfaces:**
- Consumes: Task 2 の`history_log.stamp_creation(project, now)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_csv_import.py`の末尾(`SAMPLE`は既存):

```python
def test_an_imported_project_starts_its_history_with_creation_events() -> None:
    project = parse_csv(SAMPLE, "x", {}).project
    normal = {t.id for t in project.all_tasks() if t.kind is TaskKind.NORMAL}
    assert normal and {e.task for e in project.history} == normal
    assert project.history_since is not None
    assert all(e.changes[0].before is None for e in project.history)
```

(先頭の`from projectapp.models import Status, Task`を`Status, Task, TaskKind`に直す)

`test/test_puml_import.py`の末尾:

```python
def test_an_imported_plantuml_project_starts_its_history_with_creation_events() -> None:
    project = parse("[設計] lasts 3 days", "[実装] lasts 2 days").project
    normal = {t.id for t in project.all_tasks() if t.kind is TaskKind.NORMAL}
    assert len(normal) == 2 and {e.task for e in project.history} == normal
    assert project.history_since is not None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_import.py test/test_puml_import.py -q -k creation_events`
Expected: FAIL(`project.history_since is not None`)

- [ ] **Step 3: 実装する**

`csv_import.py`: `from projectapp.history_log import stamp_creation`を足し、`parse_csv`の`return CsvImport(`の直前(`except`の後)に追加:

```python
    stamp_creation(project, clock.now())  # 取り込んだタスクの作成を、履歴の最初にする
```

`puml_import.py`: 同じ import を足し、`parse_plantuml`の`counts = builder.counts`の直前に同じ 1 行を追加。

- [ ] **Step 4: テストを通す**

Run: `uv run pytest test/test_csv_import.py test/test_puml_import.py -q`
Expected: すべて PASS(既存の取り込みテストが`Project`全体の等値比較をしていて失敗する場合は、`history`を除いた比較に直す)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/csv_import.py src/projectapp/puml_import.py test/
git commit -m "feat: 取り込んだプロジェクトの履歴を作成イベントから始める(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 4: 過去の値の復元と「不明」の判定

**Files:**
- Modify: `src/projectapp/history_log.py`
- Test: `test/test_history_log.py`

**Interfaces:**
- Produces:
  - `history_log.TaskState(status: Status, progress: int | None, effort: float)`(frozen dataclass)
  - `history_log.events_by_task(project: Project) -> dict[str, list[HistoryEvent]]`(各リストは日時順)
  - `history_log.is_known(project: Project, moment: datetime) -> bool`
  - `history_log.state_at(task: Task, events: Sequence[HistoryEvent], moment: datetime) -> TaskState | None`(`moment`の時点にタスクがなければ`None`。`events`は`task`の分)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_history_log.py`の末尾(import に`from projectapp.history_log import TaskState, events_by_task, is_known, state_at`を足す):

```python
SINCE = datetime(2026, 11, 1, 0, 0)


def running_then_done() -> tuple[Project, Task]:
    task = Task("a", id="a", effort_hours=10, status=Status.DONE, progress=100)
    project = Project(
        "p",
        tasks=[task],
        history_since=SINCE,
        history=[
            ev("a", datetime(2026, 11, 3, 10), status=("未着手", "実行中"), progress=(None, 50)),
            ev("a", datetime(2026, 11, 5, 10), status=("実行中", "終了"), progress=(50, 100)),
        ],
    )
    return project, task


def test_state_before_the_first_event_uses_that_events_before_values() -> None:
    project, task = running_then_done()
    events = events_by_task(project)["a"]
    assert state_at(task, events, datetime(2026, 11, 2)) == TaskState(Status.NOT_STARTED, None, 10.0)


def test_state_between_events_uses_the_latest_after_values() -> None:
    project, task = running_then_done()
    events = events_by_task(project)["a"]
    assert state_at(task, events, datetime(2026, 11, 4)) == TaskState(Status.RUNNING, 50, 10.0)
    assert state_at(task, events, datetime(2026, 11, 6)) == TaskState(Status.DONE, 100, 10.0)


def test_state_without_any_event_is_the_current_value() -> None:
    task = Task("b", id="b", effort_hours=4, progress=20, status=Status.RUNNING)
    assert state_at(task, [], datetime(2026, 11, 4)) == TaskState(Status.RUNNING, 20, 4.0)


def test_a_task_created_after_the_moment_did_not_exist() -> None:
    task = Task("c", id="c", effort_hours=4)
    created = [ev("c", datetime(2026, 11, 4), status=(None, "未着手"), progress=(None, None), effort=(None, 4.0))]
    assert state_at(task, created, datetime(2026, 11, 3)) is None
    assert state_at(task, created, datetime(2026, 11, 5)) == TaskState(Status.NOT_STARTED, None, 4.0)


def test_a_moment_exactly_at_an_event_does_not_include_it() -> None:
    project, task = running_then_done()
    events = events_by_task(project)["a"]
    assert state_at(task, events, datetime(2026, 11, 3, 10)).status is Status.NOT_STARTED


def test_history_is_unknown_before_it_started_or_when_never_recorded() -> None:
    project = Project("p", history_since=SINCE)
    assert not is_known(project, datetime(2026, 10, 31, 23, 59))
    assert is_known(project, SINCE)
    assert not is_known(Project("p"), datetime(2026, 11, 8))
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_history_log.py -q -k "state or unknown"`
Expected: FAIL(`ImportError: cannot import name 'TaskState'`)

- [ ] **Step 3: 実装する**

`history_log.py`の import を`from collections.abc import Sequence`、`from dataclasses import dataclass`、`Status`(`projectapp.models`から)を足す形に直し、末尾に追加:

```python
@dataclass(frozen=True)
class TaskState:
    """ある時点のタスクの、記録している 3 項目。"""

    status: Status
    progress: int | None
    effort: float


def events_by_task(project: Project) -> dict[str, list[HistoryEvent]]:
    """タスクの id ごとのイベント(日時順)。同じ日時は記録した順。"""
    index: dict[str, list[HistoryEvent]] = {}
    for event in sorted(project.history, key=lambda e: e.at):
        index.setdefault(event.task, []).append(event)
    return index


def is_known(project: Project, moment: datetime) -> bool:
    """`moment`の値を履歴から復元できるか。記録を始めた日時より前、または一度も記録していないときは不明。"""
    return project.history_since is not None and moment >= project.history_since


def state_at(
    task: Task, events: Sequence[HistoryEvent], moment: datetime
) -> TaskState | None:
    """`moment`(その時刻の直前まで)のタスクの値。`events`はこのタスクの分(日時順)。
    項目ごとに、直前のイベントの「後」。なければ、その後の最初のイベントの「前」。それもなければ現在の値。
    その時点で作られていなければ None。"""
    current = _values(task)
    found: dict[str, Value] = {}
    for name in HISTORY_FIELDS:
        touching = [(e.at, c) for e in events for c in e.changes if c.field == name]
        earlier = [c for at, c in touching if at < moment]
        later = [c for at, c in touching if at >= moment]
        if earlier:
            found[name] = earlier[-1].after
        elif later:
            found[name] = later[0].before
        else:
            found[name] = current[name]
    if found["status"] is None:
        return None
    progress, effort = found["progress"], found["effort"]
    return TaskState(
        Status(str(found["status"])),
        progress if isinstance(progress, int) else None,
        float(effort) if isinstance(effort, (int, float)) else 0.0,
    )
```

- [ ] **Step 4: テストを通す**

Run: `uv run pytest test/test_history_log.py -q`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/history_log.py test/test_history_log.py
git commit -m "feat: 変更履歴から過去の値を復元し、履歴のない期間を不明とする(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 5: 3 者マージで履歴を和集合にし、食い違いを補正する

**Files:**
- Modify: `src/projectapp/history_log.py`(`merge_logs`・`earliest`・`reconcile`)
- Modify: `src/projectapp/merge.py`(`merge_projects`)
- Test: `test/test_history_log.py`、`test/test_merge.py`

**Interfaces:**
- Produces:
  - `history_log.merge_logs(*logs: Sequence[HistoryEvent]) -> list[HistoryEvent]`(同じイベントは 1 件。日時順)
  - `history_log.earliest(*moments: datetime | None) -> datetime | None`
  - `history_log.reconcile(project: Project, at: datetime) -> int`(ログの最後の「後」と現在の値が違うタスクに、補正イベントを足す。足した件数)
  - `merge_projects(base, ours, theirs, choices=None, *, now: datetime | None = None)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_history_log.py`の末尾(import に`merge_logs, earliest, reconcile`を足す):

```python
def test_merge_logs_unions_dedupes_and_sorts() -> None:
    first = ev("a", datetime(2026, 11, 3), progress=(None, 10))
    second = ev("a", datetime(2026, 11, 4), progress=(10, 20))
    assert merge_logs([second, first], [first]) == [first, second]


def test_earliest_ignores_missing_moments() -> None:
    assert earliest(None, NOV8, SINCE) == SINCE
    assert earliest(None, None) is None


def test_reconcile_adds_a_correction_where_the_log_and_the_value_disagree() -> None:
    task = Task("a", id="a", progress=70, status=Status.RUNNING)
    project = Project(
        "p",
        tasks=[task],
        history=[ev("a", NOV8, status=("未着手", "実行中"), progress=(None, 50))],
    )
    assert reconcile(project, NOW) == 1
    assert project.history[-1] == ev("a", NOW, progress=(50, 70))


def test_reconcile_leaves_consistent_and_unlogged_tasks_alone() -> None:
    project = Project(
        "p",
        tasks=[
            Task("a", id="a", progress=50, status=Status.RUNNING),
            Task("b", id="b", progress=10),
        ],
        history=[ev("a", NOV8, status=("未着手", "実行中"), progress=(None, 50))],
    )
    assert reconcile(project, NOW) == 0 and len(project.history) == 1
```

`test/test_merge.py`の末尾(`from projectapp.history_log import ...`は不要。`ev`は同じ形で`HistoryEvent`・`Change`を import して定義する。先頭の import に`Change, HistoryEvent, Status`を足す):

```python
def hev(task: str, at: datetime, **fields: tuple) -> HistoryEvent:
    return HistoryEvent(
        task, at, tuple(Change(n, b, a) for n, (b, a) in fields.items())
    )


def test_both_sides_history_is_united_and_the_earlier_start_wins() -> None:
    base = proj(tasks=[Task("t", id="t1")])
    ours, theirs = replace_project(base), replace_project(base)
    ours.tasks[0].progress = 50
    ours.history = [hev("t1", datetime(2026, 11, 8, 10), progress=(None, 50))]
    ours.history_since = datetime(2026, 11, 8, 9)
    theirs.tasks[0].status = Status.RUNNING
    theirs.history = [hev("t1", datetime(2026, 11, 7, 10), status=("未着手", "実行中"))]
    theirs.history_since = datetime(2026, 11, 7, 9)
    merged = merge_projects(base, ours, theirs, now=datetime(2026, 11, 9)).project
    assert [e.at.day for e in merged.history] == [7, 8]  # 補正イベントは足されない
    assert merged.history_since == datetime(2026, 11, 7, 9)


def test_a_conflicting_value_gets_a_correction_event() -> None:
    base = proj(tasks=[Task("t", id="t1")])
    ours, theirs = replace_project(base), replace_project(base)
    ours.tasks[0].progress = 50
    ours.history = [hev("t1", datetime(2026, 11, 7, 10), progress=(None, 50))]
    theirs.tasks[0].progress = 30
    theirs.history = [hev("t1", datetime(2026, 11, 8, 10), progress=(None, 30))]
    now = datetime(2026, 11, 9)
    merged = merge_projects(base, ours, theirs, now=now).project
    assert merged.tasks[0].progress == 50  # 衝突は自分
    assert merged.history[-1] == hev("t1", now, progress=(30, 50))
```

`replace_project`は、このテストファイルの先頭付近に追加する小さな複製関数: `def replace_project(p: Project) -> Project: return copy.deepcopy(p)`(`import copy`を足す)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_history_log.py test/test_merge.py -q -k "reconcile or merge_logs or earliest or history or correction"`
Expected: FAIL(`ImportError` / `TypeError: unexpected keyword 'now'`)

- [ ] **Step 3: `history_log.py`に実装する**

末尾に追加:

```python
def merge_logs(*logs: Sequence[HistoryEvent]) -> list[HistoryEvent]:
    """複数のログの和集合。同じイベント(タスク・日時・変化が同じ)は 1 件にし、日時順に並べる。"""
    unique = dict.fromkeys(event for log in logs for event in log)
    return sorted(unique, key=lambda e: e.at)


def earliest(*moments: datetime | None) -> datetime | None:
    known = [m for m in moments if m is not None]
    return min(known) if known else None


def reconcile(project: Project, at: datetime) -> int:
    """ログの最後の「後」と現在の値が食い違うタスクに、`at`の補正イベントを足す(3 者マージの衝突の解決などで起きる)。
    ログのないタスクは対象外。足した件数を返す。"""
    index = events_by_task(project)
    added = 0
    for task in project.all_tasks():
        if not _recordable(task) or task.id not in index:
            continue
        last: dict[str, Value] = {}
        for event in index[task.id]:
            for change in event.changes:
                last[change.field] = change.after
        current = _values(task)
        changes = tuple(
            Change(name, last[name], current[name])
            for name in HISTORY_FIELDS
            if name in last and last[name] != current[name]
        )
        if changes:
            project.history.append(HistoryEvent(task.id, at, changes))
            added += 1
    return added
```

- [ ] **Step 4: `merge_projects`に組み込む**

`src/projectapp/merge.py`:

1. `from projectapp import clock`と`from projectapp.history_log import earliest, merge_logs, reconcile`を import に足す(`datetime`が無ければ`from datetime import datetime`も)。
2. シグネチャを変える:

```python
def merge_projects(
    base: Project,
    ours: Project,
    theirs: Project,
    choices: Choices | None = None,
    *,
    now: datetime | None = None,
) -> MergeResult:
```

3. 関数の最後、`return MergeResult(copy.deepcopy(project), merger.conflicts, notes)`の直前に追加:

```python
    project.history = merge_logs(ours.history, theirs.history)
    project.history_since = earliest(ours.history_since, theirs.history_since)
    reconcile(project, now or clock.now())
```

- [ ] **Step 5: テストを通す**

Run: `uv run pytest test/test_history_log.py test/test_merge.py -q`
Expected: すべて PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/history_log.py src/projectapp/merge.py test/
git commit -m "feat: 3 者マージで変更履歴を和集合にし、食い違いを補正する(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 6: 「進んだ分」の集計

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: Task 4 の`events_by_task`・`is_known`・`state_at`・`TaskState`
- Produces:
  - `dashboard.ProgressDelta(period: Period, percent: float | None, scope_hours: float, known: bool, since: date | None, counted: int)`(frozen)
  - `dashboard.previous_period(period: Period) -> Period`
  - `dashboard.summarize_progress_delta(project, period, now, holidays, member=None) -> ProgressDelta`
  - `Dashboard.delta: ProgressDelta | None`、`Dashboard.previous_delta: ProgressDelta | None`(`summarize`が`PeriodKind.ALL`以外で入れる)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py`の末尾(import に`ProgressDelta, previous_period, summarize_progress_delta, summarize`が無ければ足し、`from projectapp.models import Change, HistoryEvent`も足す):

```python
WEEK = Period(date(2026, 11, 2), date(2026, 11, 8))
D_NOW = datetime(2026, 11, 6, 12)


def hevent(task: str, at: datetime, **fields: tuple) -> HistoryEvent:
    return HistoryEvent(
        task, at, tuple(Change(n, b, a) for n, (b, a) in fields.items())
    )


def delta_project(**kw) -> Project:
    """a: 10h、今週のうちに 0% → 100%。b: 10h、動かず。どちらも締切が今週。"""
    a = Task("a", id="a", effort_hours=10, status=Status.DONE, progress=100,
             deadline=datetime(2026, 11, 5, 17))
    b = Task("b", id="b", effort_hours=10, deadline=datetime(2026, 11, 6, 17))
    return Project(
        "p",
        base_date=date(2026, 11, 2),
        tasks=[a, b],
        history_since=datetime(2026, 11, 1),
        history=[
            hevent("a", datetime(2026, 11, 3, 10), status=("未着手", "実行中"), progress=(None, 50)),
            hevent("a", datetime(2026, 11, 5, 10), status=("実行中", "終了"), progress=(50, 100)),
        ],
        **kw,
    )


def test_progress_delta_weights_by_effort_and_counts_only_tasks_that_existed() -> None:
    delta = summarize_progress_delta(delta_project(), WEEK, D_NOW, {})
    assert delta.known and delta.counted == 2
    assert delta.percent == pytest.approx(50.0)  # (10×100 + 10×0) ÷ 20
    assert delta.scope_hours == 0.0


def test_a_task_created_in_the_period_is_scope_not_progress() -> None:
    project = delta_project()
    project.tasks.append(
        Task("c", id="c", effort_hours=4, status=Status.DONE, progress=100,
             deadline=datetime(2026, 11, 6, 17))
    )
    project.history.append(
        hevent("c", datetime(2026, 11, 4, 9), status=(None, "未着手"), progress=(None, None), effort=(None, 4.0))
    )
    project.history.append(
        hevent("c", datetime(2026, 11, 4, 15), status=("未着手", "終了"), progress=(None, 100))
    )
    delta = summarize_progress_delta(project, WEEK, D_NOW, {})
    assert delta.percent == pytest.approx(50.0)  # c の完了は進んだ分に入れない
    assert delta.scope_hours == 4.0


def test_an_effort_change_is_scope_and_weights_by_the_end_effort() -> None:
    project = delta_project()
    project.tasks[1].effort_hours = 30
    project.history.append(hevent("b", datetime(2026, 11, 4, 9), effort=(10.0, 30.0)))
    delta = summarize_progress_delta(project, WEEK, D_NOW, {})
    assert delta.scope_hours == 20.0
    assert delta.percent == pytest.approx(10 * 100 / 40)


def test_the_period_before_the_history_started_is_unknown_not_zero() -> None:
    project = delta_project()
    delta = summarize_progress_delta(project, previous_period(WEEK), D_NOW, {})
    assert not delta.known and delta.percent is None
    assert delta.since == date(2026, 11, 1)


def test_a_project_with_no_history_is_unknown() -> None:
    delta = summarize_progress_delta(Project("p", tasks=[Task("a", id="a")]), WEEK, D_NOW, {})
    assert not delta.known and delta.since is None


def test_summaries_checkpoints_and_tasks_outside_the_period_are_not_counted() -> None:
    project = delta_project()
    project.tasks.append(Task("far", id="far", effort_hours=10, deadline=datetime(2026, 12, 20, 17)))
    project.tasks.append(Task("cp", id="cp", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 11, 5, 17)))
    assert summarize_progress_delta(project, WEEK, D_NOW, {}).counted == 2


def test_previous_period_has_the_same_length_just_before() -> None:
    assert previous_period(WEEK) == Period(date(2026, 10, 26), date(2026, 11, 1))


def test_summarize_fills_the_delta_except_for_the_whole_period() -> None:
    project = delta_project()
    week = summarize(project, WEEK, D_NOW, {}, PeriodKind.WEEK)
    assert week.delta is not None and week.previous_delta is not None
    assert summarize(project, WEEK, D_NOW, {}, PeriodKind.ALL).delta is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -q -k "delta or previous_period"`
Expected: FAIL(`ImportError: cannot import name 'ProgressDelta'`)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard.py`:

1. import に`from projectapp.history_log import TaskState, events_by_task, is_known, state_at`を足す。
2. `summarize_team_progress`の定義の後ろに追加:

```python
@dataclass(frozen=True)
class ProgressDelta:
    """期間中に進んだ分(要望 128)。`percent`は、期間の始めにあったタスクの工数で重みづけした進捗率の増分(%ポイント)。"""

    period: Period
    percent: float | None  # 対象のタスクがない・履歴が不明のとき None
    scope_hours: float  # 範囲の増加[h]。期間中に増えたタスクの工数と、工数の変更の増分
    known: bool  # 期間の始めまで履歴がある
    since: date | None  # 履歴を記録し始めた日
    counted: int  # 進んだ分を求めたタスクの件数


def previous_period(period: Period) -> Period:
    """同じ長さの、直前の期間。"""
    length = (period.end - period.start).days + 1
    return Period(
        period.start - timedelta(days=length), period.start - timedelta(days=1)
    )


def _effective(state: TaskState) -> float:
    """実効の進捗(0〜100)。終了なら 100、それ以外は進捗度(なければ 0)。"""
    return 100.0 if state.status is Status.DONE else float(state.progress or 0)


def summarize_progress_delta(
    project: Project,
    period: Period,
    now: datetime,
    holidays: dict[date, str],
    member: Scope = None,
) -> ProgressDelta:
    """期間中に進んだ分。対象は`チーム全体の進捗`と同じ集合(予定の期間・締切・実績が期間にかかる通常タスク)のうち、
    期間の始めにあったもの。工数のないタスクは 1 時間として数える。期間の始めが記録開始より前なら不明。"""
    low, high = period.bounds()
    since = project.history_since.date() if project.history_since else None
    if not is_known(project, low):
        return ProgressDelta(period, None, 0.0, False, since, 0)
    index = events_by_task(project)
    weighted = total = scope = 0.0
    counted = 0
    for entry in _entries(project, holidays, member, None):
        task = entry.task
        if task.kind is not TaskKind.NORMAL or not _touches(
            task, entry.schedule, period, now
        ):
            continue
        events = index.get(task.id, [])
        end = state_at(task, events, high)
        if end is None:
            continue
        weight = _weight(end.effort)
        start = state_at(task, events, low)
        if start is None:  # 期間の途中で作られた分は、進んだ分ではなく範囲の増加
            scope += weight
            continue
        scope += weight - _weight(start.effort)
        weighted += weight * (_effective(end) - _effective(start))
        total += weight
        counted += 1
    return ProgressDelta(
        period, weighted / total if total else None, scope, True, since, counted
    )
```

3. `Dashboard`の`heat`フィールドの次に追加:

```python
    delta: ProgressDelta | None = None  # 期間中に進んだ分。全期間は None
    previous_delta: ProgressDelta | None = None  # 同じ長さの直前の期間の分
```

4. `summarize`の`return Dashboard(`の直前に追加し、`references=len(children or {}),`の次の行に`delta=delta, previous_delta=previous,`を足す:

```python
    delta = previous = None
    if kind is not PeriodKind.ALL:
        delta = summarize_progress_delta(project, period, now, holidays, scope)
        previous = summarize_progress_delta(
            project, previous_period(period), now, holidays, scope
        )
```

(`timedelta`は`dashboard.py`で既に import 済み)

- [ ] **Step 4: テストを通す**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: 期間中に進んだ分と範囲の増加を集計する(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 7: 画面の 1 行と、切り出しでのイベントの移動

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`delta_line`・`team_card`)
- Modify: `src/projectapp/extract.py`(`extract`)
- Test: `test/test_dashboard_view.py`、`test/test_extract.py`

**Interfaces:**
- Consumes: Task 6 の`ProgressDelta`・`Dashboard.delta`・`Dashboard.previous_delta`
- Produces: `dashboard_view.delta_line(delta: ProgressDelta, previous: ProgressDelta | None) -> str`、マーカー`dashboard-team-delta`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py`の末尾(import に`from projectapp.dashboard import ProgressDelta`と`from projectapp.dashboard_view import delta_line`を足す):

```python
P = Period(date(2026, 10, 5), date(2026, 10, 11))


def delta(percent=12.4, scope=6.0, known=True, since=date(2026, 10, 1)) -> ProgressDelta:
    return ProgressDelta(P, percent, scope, known, since, 2)


def test_delta_line_shows_the_gain_the_previous_period_and_the_scope() -> None:
    assert delta_line(delta(), delta(8.2)) == "進んだ分 +12%(前の期間 +8%)  範囲 +6.0h"


def test_delta_line_omits_what_is_missing() -> None:
    assert delta_line(delta(scope=0.0), None) == "進んだ分 +12%"
    assert delta_line(delta(), delta(None, known=False)) == "進んだ分 +12%  範囲 +6.0h"
    assert delta_line(delta(-3.2, scope=-2.0), None) == "進んだ分 -3%  範囲 -2.0h"
    assert delta_line(delta(0.2, scope=0.0), None) == "進んだ分 +0%"


def test_delta_line_says_unknown_instead_of_zero() -> None:
    assert delta_line(delta(None, known=False), None) == "進んだ分: 履歴は 10/01 から(それ以前は不明)"
    assert delta_line(delta(None, known=False, since=None), None) == "進んだ分: 履歴はまだありません"
    assert delta_line(delta(None), None) == "進んだ分: 対象のタスクなし  範囲 +6.0h"


async def test_the_team_card_shows_the_delta_line(user: User) -> None:
    views, _, _ = mount()
    data = sample()
    data.delta, data.previous_delta = delta(), delta(8.2)
    await user.open("/")
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-delta")
    assert text(user, "dashboard-team-delta") == "進んだ分 +12%(前の期間 +8%)  範囲 +6.0h"


async def test_the_team_card_has_no_delta_line_for_the_whole_period(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.ALL)
    await user.should_not_see(marker="dashboard-team-delta")
```

`test/test_extract.py`の末尾(既存の import と同じ流儀で。`extract`・`Project`・`Task`は既存の import を使い、`Change, HistoryEvent`を足す):

```python
def test_extraction_moves_the_history_of_the_moved_tasks() -> None:
    at = datetime(2026, 11, 8, 10)
    project = Project(
        "p",
        tasks=[Task("a", id="a"), Task("b", id="b")],
        history=[
            HistoryEvent("a", at, (Change("progress", None, 30),)),
            HistoryEvent("b", at, (Change("progress", None, 40),)),
        ],
        history_since=at,
    )
    result = extract(project, ["a"], "child")
    assert [e.task for e in result.child.history] == ["a"]
    assert [e.task for e in result.parent.history] == ["b"]
    assert result.child.history_since == at and result.parent.history_since == at
    assert [e.task for e in project.history] == ["a", "b"]  # 元は変えない
```

(`datetime`が無ければ`from datetime import datetime`を足す)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py test/test_extract.py -q -k "delta or history"`
Expected: FAIL(`ImportError: cannot import name 'delta_line'`)

- [ ] **Step 3: 画面を実装する**

`src/projectapp/dashboard_view.py`:

1. `from projectapp.dashboard import (...)`に`ProgressDelta`を足す。
2. `days_text`の近くにモジュール関数を追加:

```python
def delta_line(delta: ProgressDelta, previous: ProgressDelta | None) -> str:
    """`チーム全体の進捗`の「進んだ分」の 1 行(要望 128)。履歴がない期間は、0 とせず不明と書く。"""
    if not delta.known:
        if delta.since is None:
            return "進んだ分: 履歴はまだありません"
        return f"進んだ分: 履歴は {delta.since:%m/%d} から(それ以前は不明)"
    if delta.percent is None:
        text = "進んだ分: 対象のタスクなし"
    else:
        text = f"進んだ分 {round(delta.percent):+d}%"
        if previous is not None and previous.percent is not None:
            text += f"(前の期間 {round(previous.percent):+d}%)"
    if abs(delta.scope_hours) >= 0.05:
        text += f"  範囲 {delta.scope_hours:+.1f}h"
    return text
```

3. `team_card`の`stacked_bar([...])`の呼び出しの後(`if team.unset:`の直前)に追加:

```python
            if data.delta is not None:
                ui.label(delta_line(data.delta, data.previous_delta)).classes(
                    "text-caption"
                ).mark("dashboard-team-delta")
```

注意: `if slices:`の外(`if team.unset:`と同じ字下げ)に置く。

- [ ] **Step 4: 切り出しを実装する**

`src/projectapp/extract.py`の`extract`:

1. `child = Project(`の引数、`ratio_limit_lower=project.ratio_limit_lower,`の次に追加:

```python
        history=[deepcopy(e) for e in project.history if e.task in moved],
        history_since=project.history_since,
```

2. `parent = deepcopy(project)`の直後に追加:

```python
    parent.history = [e for e in parent.history if e.task not in moved]
```

- [ ] **Step 5: テストを通す**

Run: `uv run pytest test/test_dashboard_view.py test/test_extract.py test/test_extract_view.py -q`
Expected: すべて PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/dashboard_view.py src/projectapp/extract.py test/
git commit -m "feat: チーム全体の進捗に進んだ分の行を出し、切り出しで履歴を移す(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 8: 仕様・文書の更新と全体の確認

**Files:**
- Modify: `.claude/spec/dashboard.md`・`.claude/spec/project-files.md`・`.claude/spec/header-git.md`・`.claude/spec/implementation.md`
- Modify: `CLAUDE.md`(`version`の現在値)・`docs/development.md`(モジュール構成)・`docs/requests.md`(要望 128 の状態)
- Modify: `docs/superpowers/specs/2026-11-07-task-history-design.md`(計画の「設計書との差」を反映)

- [ ] **Step 1: 該当箇所を探す**

Run: `grep -n "version\b.*20\|現在 20\|extra_efforts" CLAUDE.md .claude/spec/*.md docs/development.md | head -20`

- [ ] **Step 2: 仕様を直す**

- `CLAUDE.md`: 「先頭の`version`(現在 20)」を 21 にする。
- `.claude/spec/project-files.md`・`implementation.md`: `version` 21 と、`history`(`task`・`at`・`changes`)・`history_since`の説明を、20 の`extra_efforts`の記述に並べて足す。履歴の項目は`status`・`progress`・`effort`、追記のみ、削除したタスクの分も残す、元に戻すで戻る、古いファイルは履歴なしで読む、を書く。
- `.claude/spec/header-git.md`: 3 者マージで`history`は和集合(同じイベントは 1 件)・`history_since`は早いほう・マージ後に食い違いの補正イベントを足す、を書く。
- `.claude/spec/dashboard.md`: `チーム全体の進捗`の段落に、「期間が`今週`・`今月`・`指定`のとき、`進んだ分 +n%(前の期間 +m%)  範囲 +k h`の 1 行を出す。…」を足す。式(期間の始めにあったタスクの Σ工数×進捗の増分 ÷ Σ工数。工数なしは 1h)、範囲の増加の定義、履歴がない期間は不明と出すこと、まとめ・節目・参照先は含まないこと、遡った編集は入力した時刻の分になることを書く。既存の「状態は現在の値で履歴は持たないので、『今週進んだ分』は出せない」は、この行で出せるという書き方に直す。
- `docs/development.md`: `history_log.py`(変更履歴の記録・復元・補正・和集合)を足す。
- `docs/requests.md`: 要望 128 の状態を「段階 1 実装済み(PR 待ち)」にする。段階 2・3(担当者別の進んだ分、バーンダウン、古い履歴のまとめ)を未着手として残す。
- 設計書: 「設計書との差」の 4 点(`history_since`は最初の記録の編集・取り込みの時刻、補正はマージの後だけ、按分しない、対象は`NORMAL`)を本文に反映する。

- [ ] **Step 3: smoke → ruff → ty**

Run:
```bash
uv run pytest -m smoke -q
uvx ruff check
uvx ruff format src test
uvx ty check src
```
Expected: smoke は全部 PASS、ruff は`All checks passed!`、ty は指摘 0 件。smoke が失敗したときに限り`uv run pytest -n auto`で全テストを走らせる。

- [ ] **Step 4: 全テスト(広い範囲に触れたため)**

Run: `uv run pytest -n auto -q`
Expected: すべて PASS(約 1〜2 分)

- [ ] **Step 5: 速度とメモリを測る(結果は要望 128 の記録に書く)**

作業用フォルダ(スクラッチパッド)にスクリプトを書いて実行する。300 タスク・1 年分・イベント約 10,000 件の`Project`を作り、次を測って`docs/requests.md`の要望 128 に数字を残す:

```python
import time, tracemalloc
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta
from projectapp.dashboard import Period, summarize_progress_delta
from projectapp.models import Change, HistoryEvent, Project, Status, Task

tasks = [Task(f"t{i}", id=f"t{i}", effort_hours=8, deadline=datetime(2026, 11, 5, 17)) for i in range(300)]
history = [
    HistoryEvent(f"t{i}", datetime(2026, 1, 1) + timedelta(hours=k * 7 + i),
                 (Change("progress", k * 3 % 100, (k + 1) * 3 % 100),))
    for i in range(300) for k in range(33)
]
project = Project("p", base_date=date(2026, 11, 2), tasks=tasks, history=history, history_since=datetime(2026, 1, 1))
start = time.perf_counter(); asdict(project); print("asdict(is_dirty):", time.perf_counter() - start)
start = time.perf_counter(); deepcopy(project); print("deepcopy:", time.perf_counter() - start)
start = time.perf_counter()
summarize_progress_delta(project, Period(date(2026, 11, 2), date(2026, 11, 8)), datetime(2026, 11, 6, 12), {})
print("delta:", time.perf_counter() - start)
```

Expected: `delta`は 1 秒未満。`is_dirty`(`asdict`)が数百 ms を超えるなら、結果を記録して利用者に知らせる(対処は別の要望にする)。

- [ ] **Step 6: コミットして PR を作る**

```bash
git add -A
git commit -m "docs: 変更履歴の仕様と文書を更新する(要望 128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
GIT_TERMINAL_PROMPT=0 timeout 90 git push -u origin feature/task-history
gh pr create --base develop --title "feat: 変更履歴と、期間中に進んだ分の集計(要望 128 段階 1)" --body "<要約・測定結果・確認用データの有無>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

マージは利用者の指示を待つ。実機確認用に、履歴つきの`docs/samples/履歴確認.json`を作る場合は、`~/.projectapp`へのコピー前に利用者に聞く。
