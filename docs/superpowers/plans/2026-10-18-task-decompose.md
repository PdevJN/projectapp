# タスクの分解(まとめ)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1 つのタスクを複数のタスクに分解し、元のタスクを「まとめ」として残す。まとめは折りたたみができ、期間・進捗・状態を子から算出する。

**Architecture:** `TaskKind.SUMMARY` と `Task.children`(子の id)を足す。まとめの日程は `timeline.Schedule._resolve` が子から算出し、進捗・状態は新しい純粋モジュール `summary.py` が算出する(保存しない)。分解の計算は純粋モジュール `decompose.py`。ガントチャートは `row_slots` に折りたたみを足し、`task_row` にまとめの帯を足す。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、`uv run ty check src`。

**Spec:** [`docs/superpowers/specs/2026-10-18-task-decompose-design.md`](../specs/2026-10-18-task-decompose-design.md)(モックアップは設計書の「まとめの見た目」)

## 設計書との差分(コードを読んで分かったこと。Task 11 で設計書に反映する)

1. **入口は編集ダイアログのボタンだけ**。ガントチャートに行のメニューはない(行のクリックが編集ダイアログを開く)。設計書の「行のメニューの`分解…`」は外す。
2. **`連結する`がオフのとき**、すべての子が元の先行を引き継ぐ(オンのときは、最初の子だけが引き継ぎ、残りは直前の子を先行にする)。
3. **まとめをコピー**すると、子を持たない通常タスク(工数 0)になる(`arrange.copy_task`)。子のコピーは通常タスクで、まとめの子にはならない。
4. **まとめを削除**すると、子は残り、通常タスクとして独立する。**子を削除**すると、まとめの`children`から外れ、子が 0 件になったまとめは通常タスクに戻る。
5. **まとめの`predecessors`は空**(分解のとき、元の先行は最初の子へ移す)。まとめを先行にする側(後続)はそのまま残す。
6. **子の先行にその親のまとめを指定できない**(循環になる)。読込・マージでは`validate_links`が循環として拒否し、編集ダイアログの候補(`link_options`)からは外す。
7. **まとめは 1 段のみ**。まとめの子はまとめにできない。1 つのタスクは 1 つのまとめにしか属さない。
8. **絞り込み**: まとめは、自分の名前が合うか、子のどれかが合うときに出す。

## Global Constraints

- Python 3.13 以上。ライブラリは NiceGUI。描画は NiceGUI の要素と CSS(外部のガントライブラリは使わない)。
- 日時から位置への変換や日程計算は、NiceGUI から切り離した純粋関数(`timeline.py` など)にする。
- ファイルの`version`は 5 → **6**。キーのない古いファイルは既定値(`children`なし)で読み、このアプリより新しい`version`は読込を拒否する。不正な値は読込を拒否する。
- タスク名は 50 文字以内で、改行・制御文字・ゼロ幅文字(`Cc`・`Cf`・`Zl`・`Zp`)は使えない。
- 折りたたみの状態は保存せず、元に戻す・やり直しの対象にしない。分解は 1 回の`after_edit`(= 元に戻す 1 ステップ)。
- 優先度の名前の欄の背景色は、まとめにも付ける。まとめに担当者のチップは出さない。
- 作業は`develop`から`feature/task-decompose`を切る(git-flow。`.claude/BRANCH.md`)。コミットの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。
- テストは`uv run pytest -n auto`、型は`uv run ty check src`。各 Task の終わりに、触ったテストファイルを通す。

## Review Focus

1. 子を持つまとめを含むプロジェクトを保存して読み直したとき、`children`の順序・内容が変わらないこと(`dumps_project` → `parse_project` の往復)。
2. 子を全部削除したまとめが、読込でも編集でも壊れないこと(読込は拒否、編集中は通常タスクに戻す)。
3. まとめを先行にした後続の日程が、子の最大の完了で押し出されること。子の日程が求まらないとき(全員が日程なし)に、まとめも日程なしになること。
4. 折りたたんだまとめの子の行が、セクションの開閉・絞り込み・読み取り専用(プレビュー)のどの組み合わせでも、表示の規則どおりになること。
5. ダッシュボードの工数・進捗・期限が、まとめを入れる前後で変わらないこと(二重計上なし)。

---

## File Structure

| ファイル | 変更 | 役割 |
| --- | --- | --- |
| `src/projectapp/models.py` | 変更 | `TaskKind.SUMMARY`・`Task.children`・`FORMAT_VERSION = 6`・`Project.task_map()` |
| `src/projectapp/storage.py` | 変更 | `children`の読み書き・まとめの検証と整形 |
| `src/projectapp/linkgraph.py` | 変更 | `children`の検証・循環・削除時の整理・候補の除外 |
| `src/projectapp/summary.py` | 新規 | まとめの規則(親の対応・状態・進捗・空のまとめを戻す)。純粋関数 |
| `src/projectapp/timeline.py` | 変更 | `Schedule._resolve` がまとめの期間を子から算出 |
| `src/projectapp/decompose.py` | 新規 | 分解の計算(`decompose`・`default_parts`)。純粋関数 |
| `src/projectapp/arrange.py` | 変更 | `copy_task`でまとめをコピーしたとき |
| `src/projectapp/filtering.py` | 変更 | まとめの絞り込み(`by_id`) |
| `src/projectapp/links.py` | 変更 | `row_slots`に折りたたみ(まとめ)を足す |
| `src/projectapp/gantt.py` | 変更 | 帯・矢印・件数チップ・折りたたみ |
| `src/projectapp/forms.py` | 変更 | `build_task`のまとめ分岐 |
| `src/projectapp/task_dialog.py` | 変更 | まとめの編集、`分解…`ボタン |
| `src/projectapp/decompose_dialog.py` | 新規 | 分解ダイアログ |
| `src/projectapp/views.py` | 変更 | 分解の実行、削除時の整理 |
| `src/projectapp/dashboard.py` | 変更 | まとめを集計から外す |
| `src/projectapp/plantuml.py` | 変更 | まとめの帯を出さず、矢印を引き直す |
| `src/projectapp/merge.py` | 変更 | `children`の統合 |
| `test/test_summary.py` | 新規 | モデル・保存・算出・分解・各連携のテスト |
| `test/test_decompose_ui.py` | 新規 | 折りたたみ・ダイアログ・画面のテスト |

---

### Task 1: モデルと保存(version 6)

**Files:**
- Modify: `src/projectapp/models.py:10,70-73,159-176`
- Modify: `src/projectapp/storage.py`(`_task`・`_kind` のあと・`parse_project` の最後)
- Modify: `src/projectapp/linkgraph.py`(`validate_links`・`_reject_cycle`)
- Create: `test/test_summary.py`

**Interfaces:**
- Produces: `TaskKind.SUMMARY`、`Task.children: list[str]`、`Project.task_map() -> dict[str, Task]`、`linkgraph.validate_links(tasks)`が`children`も検証する、`storage._summary(task)`(まとめの使わない項目を空にして返す)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_summary.py`:

```python
from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import FORMAT_VERSION, Project, Section, Status, Task, TaskKind
from projectapp.storage import dumps_project, load_project, parse_project, save_project
from test_storage import write_raw


def summary(name: str, *children: str, **fields: object) -> Task:
    return Task(name, id=name, kind=TaskKind.SUMMARY, children=list(children), **fields)  # type: ignore[arg-type]


def project_with_summary() -> Project:
    return Project(
        "p",
        sections=[Section("s", [summary("まとめ", "a", "b"), Task("a", id="a"), Task("b", id="b", predecessors=["a"])])],
    )


def test_version_is_6() -> None:
    assert FORMAT_VERSION == 6


def test_a_summary_roundtrips_with_its_children(tmp_path: Path) -> None:
    loaded = load_project(save_project(project_with_summary(), tmp_path))
    first = loaded.sections[0].tasks[0]
    assert (first.kind, first.children) == (TaskKind.SUMMARY, ["a", "b"])


def test_dumps_then_parse_keeps_the_children_order() -> None:
    project = Project("p", tasks=[summary("m", "b", "a"), Task("a", id="a"), Task("b", id="b")])
    assert parse_project(dumps_project(project), "p").tasks[0].children == ["b", "a"]


def test_a_summary_is_loaded_without_its_unused_fields(tmp_path: Path) -> None:
    raw = [
        {"name": "m", "id": "m", "kind": "まとめ", "children": ["a"], "effort_hours": 5.0, "status": "実行中",
         "planned_start": "2026-10-05T09:00:00", "progress": 30, "predecessors": ["a"]},
        {"name": "a", "id": "a"},
    ]
    task = load_project(write_raw(tmp_path, raw)).sections[0].tasks[0]
    assert (task.effort_hours, task.status, task.planned_start, task.progress, task.predecessors) == (
        0.0, Status.NOT_STARTED, None, None, [],
    )


def test_a_file_without_children_loads_as_empty(tmp_path: Path) -> None:
    assert load_project(write_raw(tmp_path, [{"name": "a"}])).sections[0].tasks[0].children == []


@pytest.mark.parametrize(
    "raw",
    [
        [{"name": "m", "id": "m", "kind": "まとめ", "children": []}],  # 子がない
        [{"name": "m", "id": "m", "kind": "まとめ"}],  # キーがない
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["zz"]}],  # 存在しない
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["m"]}],  # 自分自身
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["a", "a"]}, {"name": "a", "id": "a"}],  # 重複
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["a"]},
         {"name": "n", "id": "n", "kind": "まとめ", "children": ["a"]}, {"name": "a", "id": "a"}],  # 親が 2 つ
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["n"]},
         {"name": "n", "id": "n", "kind": "まとめ", "children": ["a"]}, {"name": "a", "id": "a"}],  # 入れ子
        [{"name": "a", "id": "a", "children": ["b"]}, {"name": "b", "id": "b"}],  # まとめでないのに子
        [{"name": "m", "id": "m", "kind": "まとめ", "children": ["a"]},
         {"name": "a", "id": "a", "predecessors": ["m"]}],  # 子が親を先行にする(循環)
        [{"name": "m", "id": "m", "kind": "まとめ", "children": "a"}],  # リストでない
    ],
)
def test_bad_summaries_are_rejected(tmp_path: Path, raw: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        load_project(write_raw(tmp_path, raw))


def test_a_version_5_file_with_children_key_ignores_it(tmp_path: Path) -> None:
    # version 5 以前に children はない。手編集でも、通常タスクの children は読まない
    path = write_raw(tmp_path, [{"name": "a", "id": "a", "children": ["zz"]}])
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = 5
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path).sections[0].tasks[0].children == []


def test_task_map_covers_every_section() -> None:
    project = Project("p", tasks=[Task("x", id="x")], sections=[Section("s", [Task("y", id="y")])])
    assert set(project.task_map()) == {"x", "y"}


def test_planned_start_is_not_kept_on_a_summary() -> None:
    task = parse_project(
        dumps_project(Project("p", tasks=[summary("m", "a", planned_start=datetime(2026, 10, 5, 9)), Task("a", id="a")])),
        "p",
    ).tasks[0]
    assert task.planned_start is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: FAIL(`TaskKind.SUMMARY` / `children` がない)

- [ ] **Step 3: 実装する**

`models.py`:

- `FORMAT_VERSION = 6` にし、コメントの末尾に`、6: まとめ(種別と子の id)`を足す。
- `TaskKind`:

```python
class TaskKind(StrEnum):
    NORMAL = "通常"
    CHECKPOINT = "チェックポイント"  # 締切だけを持つ節目。バーを持たず、◆ だけを出す
    SUMMARY = "まとめ"  # 分解した子のタスクをまとめる親。日程・工数・進捗・状態は子から算出し、保存しない
```

- `Task`に`children: list[str] = field(default_factory=list)  # まとめの子のタスクの id(まとめだけ)`を、`progress`の次に足す。
- `Project`に足す:

```python
    def task_map(self) -> dict[str, Task]:
        """id → タスク。"""
        return {task.id: task for task in self.all_tasks()}
```

`storage.py`:

```python
def _children(value: Any) -> list[str]:
    """まとめの子の id のリスト。キーがない・null は空。リストでない・文字列以外は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(cid, str) for cid in value):
        raise ValueError("まとめの子が文字列のリストではありません")
    return list(value)


def _summary(task: Task) -> Task:
    """まとめの使わない項目(日程・工数・担当・実績・進捗度・先行・締切)を空にし、状態を未着手にして返す。"""
    return replace(
        task,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=None,
        effort_hours=0.0,
        assignees=[],
        actuals=[],
        progress=None,
        predecessors=[],
        status=Status.NOT_STARTED,
    )
```

`_task`の`Task(...)`に`children=_children(raw.get("children")) if ctx.version >= 6 else [],`を足し、`result`の決定を次にする:

```python
    if kind is TaskKind.CHECKPOINT:
        result = _checkpoint(task)
    elif kind is TaskKind.SUMMARY:
        result = _summary(task)
    else:
        result = task
```

`linkgraph.py`: `validate_links`の`known = set(ids)`のあと、先行の検査の前に足す:

```python
    parents: dict[str, str] = {}
    by_id = {task.id: task for task in tasks}
    for task in tasks:
        if task.kind is not TaskKind.SUMMARY:
            if task.children:
                raise ValueError(f"まとめでないタスクが子を持っています: {task.name}")
            continue
        if not task.children:
            raise ValueError(f"まとめに子がありません: {task.name}")
        if len(set(task.children)) != len(task.children):
            raise ValueError(f"まとめの子が重複しています: {task.name}")
        for cid in task.children:
            child = by_id.get(cid)
            if cid == task.id or child is None:
                raise ValueError(f"まとめが存在しない子(または自分自身)を指しています: {task.name}")
            if child.kind is TaskKind.SUMMARY:
                raise ValueError(f"まとめの子をまとめにはできません: {task.name}")
            if cid in parents:
                raise ValueError(f"1 つのタスクが複数のまとめに属しています: {child.name}")
            parents[cid] = task.id
```

(`from projectapp.models import Project, Task, TaskKind, walk_sections`)。`_reject_cycle`の`visit`は、依存を`by_id[task_id].predecessors`から`[*by_id[task_id].predecessors, *by_id[task_id].children]`に変える。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py test/test_storage.py test/test_checkpoint.py test/test_models.py -q`
Expected: PASS(既存の`version`が 5 を前提にしたテストが落ちたら、期待値を 6 にする。落ちた箇所は`grep -rn "version.*5\|FORMAT_VERSION" test`で探す)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/models.py src/projectapp/storage.py src/projectapp/linkgraph.py test/test_summary.py test
git commit -m "feat: まとめ(種別と子の id)を持てるようにする(version 6)"
```

---

### Task 2: まとめの規則(`summary.py`)

**Files:**
- Create: `src/projectapp/summary.py`
- Modify: `test/test_summary.py`(追記)

**Interfaces:**
- Consumes: `Task.children`・`Project.task_map()`(Task 1)
- Produces:
  - `parent_map(project: Project) -> dict[str, str]`(子の id → まとめの id)
  - `children_of(task: Task, by_id: Mapping[str, Task]) -> list[Task]`(`by_id`にある子だけ、`children`の順)
  - `summary_status(children: Sequence[Task]) -> Status`
  - `summary_progress(children: Sequence[Task]) -> int | None`
  - `drop_child(project: Project, task_id: str) -> None`(全まとめの`children`から外し、空になったまとめを通常タスクに戻す)
  - `revert_empty(project: Project) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_summary.py`に追記:

```python
from projectapp.summary import children_of, drop_child, parent_map, revert_empty, summary_progress, summary_status


def child(name: str, status: Status = Status.NOT_STARTED, effort: float = 0.0, progress: int | None = None) -> Task:
    return Task(name, id=name, status=status, effort_hours=effort, progress=progress)


def test_parent_map_points_children_at_their_summary() -> None:
    assert parent_map(project_with_summary()) == {"a": "まとめ", "b": "まとめ"}


def test_children_of_keeps_the_order_and_skips_missing_ids() -> None:
    project = Project("p", tasks=[summary("m", "b", "x", "a"), child("a"), child("b")])
    assert [c.name for c in children_of(project.tasks[0], project.task_map())] == ["b", "a"]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([Status.DONE, Status.DONE], Status.DONE),
        ([Status.NOT_STARTED, Status.NOT_STARTED], Status.NOT_STARTED),
        ([Status.DONE, Status.NOT_STARTED], Status.RUNNING),
        ([Status.PAUSED, Status.NOT_STARTED], Status.RUNNING),
        ([Status.RUNNING, Status.NOT_STARTED], Status.RUNNING),
        ([], Status.NOT_STARTED),
    ],
)
def test_summary_status(statuses: list[Status], expected: Status) -> None:
    assert summary_status([child(f"c{i}", s) for i, s in enumerate(statuses)]) == expected


def test_summary_progress_is_weighted_by_effort() -> None:
    kids = [child("a", effort=6.0, progress=50), child("b", effort=2.0, progress=100)]
    assert summary_progress(kids) == 63  # (6*50 + 2*100) / 8 = 62.5 → 63 (四捨五入)


def test_summary_progress_counts_done_as_100_and_unset_as_0_and_no_effort_as_weight_1() -> None:
    kids = [child("a", Status.DONE), child("b")]
    assert summary_progress(kids) == 50


def test_summary_progress_is_none_when_no_child_has_progress_or_is_done() -> None:
    assert summary_progress([child("a"), child("b")]) is None


def test_drop_child_removes_the_id_and_reverts_an_empty_summary() -> None:
    project = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b")])
    drop_child(project, "a")
    assert project.tasks[0].children == ["b"] and project.tasks[0].kind is TaskKind.SUMMARY
    drop_child(project, "b")
    assert project.tasks[0].children == [] and project.tasks[0].kind is TaskKind.NORMAL


def test_revert_empty_leaves_other_summaries() -> None:
    project = Project("p", tasks=[summary("m", "a"), summary("n"), child("a")])
    revert_empty(project)
    assert [t.kind for t in project.tasks] == [TaskKind.SUMMARY, TaskKind.NORMAL, TaskKind.NORMAL]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: FAIL(`projectapp.summary`がない)

- [ ] **Step 3: 実装する**

`src/projectapp/summary.py`:

```python
"""まとめタスクの規則(状態・進捗の算出、親子の対応、空のまとめの扱い)。NiceGUI には依存しない純粋関数。

日程(開始・完了)は `timeline.Schedule` が算出する。
"""

from collections.abc import Mapping, Sequence
from math import isfinite

from projectapp.models import Project, Status, Task, TaskKind


def parent_map(project: Project) -> dict[str, str]:
    """子のタスクの id → まとめの id。"""
    return {cid: task.id for task in project.all_tasks() if task.kind is TaskKind.SUMMARY for cid in task.children}


def children_of(task: Task, by_id: Mapping[str, Task]) -> list[Task]:
    """まとめの子。`children` の順で、`by_id` にないものは飛ばす。"""
    return [by_id[cid] for cid in task.children if cid in by_id]


def summary_status(children: Sequence[Task]) -> Status:
    """全員が終了なら終了、1 つでも着手済み(実行中・一時停止・終了)なら実行中、それ以外は未着手。"""
    if children and all(c.status is Status.DONE for c in children):
        return Status.DONE
    if any(c.status is not Status.NOT_STARTED for c in children):
        return Status.RUNNING
    return Status.NOT_STARTED


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def summary_progress(children: Sequence[Task]) -> int | None:
    """子の進捗度を、工数(なければ 1)で重みづけした平均(四捨五入)。終了は 100、進捗度がないものは 0。
    どの子にも進捗度がなく、終了もないときは None。"""
    if not any(c.status is Status.DONE or c.progress is not None for c in children):
        return None
    weighted = total = 0.0
    for c in children:
        weight = _weight(c.effort_hours)
        percent = 100 if c.status is Status.DONE else (c.progress or 0)
        weighted += weight * percent
        total += weight
    return int(weighted / total + 0.5)  # 四捨五入(round は銀行丸めで、62.5 が 62 になる)


def revert_empty(project: Project) -> None:
    """子のいなくなったまとめを、通常タスクに戻す。"""
    for task in project.all_tasks():
        if task.kind is TaskKind.SUMMARY and not task.children:
            task.kind = TaskKind.NORMAL


def drop_child(project: Project, task_id: str) -> None:
    """全まとめの子から、その id を取り除く(タスクの削除のとき)。空になったまとめは通常タスクに戻す。"""
    for task in project.all_tasks():
        if task_id in task.children:
            task.children = [cid for cid in task.children if cid != task_id]
    revert_empty(project)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/summary.py test/test_summary.py
git commit -m "feat: まとめの状態・進捗の算出と、空のまとめの扱いを足す"
```

---

### Task 3: まとめの期間(`Schedule`)

**Files:**
- Modify: `src/projectapp/timeline.py:437-460,463-483,498-520`
- Modify: `test/test_summary.py`(追記)

**Interfaces:**
- Consumes: `children_of`(Task 2)
- Produces: `Schedule.start/end(summary)`が子の最小の開始・最大の完了を返す。`effective_start/end`もまとめに対応する。`is_overdue(summary, ...)`は常に False。`progress_state(summary, ...)`は None。

- [ ] **Step 1: 失敗するテストを書く**

```python
from projectapp.timeline import Schedule, effective_end, effective_start, is_overdue, progress_state

D = datetime


def timed(name: str, start: datetime | None, end: datetime | None, **fields: object) -> Task:
    return Task(name, id=name, planned_start=start, planned_end=end, **fields)  # type: ignore[arg-type]


def span_project() -> Project:
    return Project(
        "p",
        tasks=[
            summary("m", "a", "b"),
            timed("a", D(2026, 10, 6, 9), D(2026, 10, 7, 17)),
            timed("b", D(2026, 10, 8, 9), D(2026, 10, 12, 17)),
            Task("after", id="after", predecessors=["m"], planned_start=D(2026, 10, 1, 9),
                 planned_end=D(2026, 10, 2, 9)),
        ],
    )


def test_a_summary_spans_its_children() -> None:
    project = span_project()
    schedule = Schedule(project, {})
    assert (schedule.start(project.tasks[0]), schedule.end(project.tasks[0])) == (D(2026, 10, 6, 9), D(2026, 10, 12, 17))
    assert effective_start(project.tasks[0], project, {}) == D(2026, 10, 6, 9)
    assert effective_end(project.tasks[0], project, {}) == D(2026, 10, 12, 17)


def test_a_task_after_a_summary_is_pushed_to_the_latest_child_finish() -> None:
    project = span_project()
    assert Schedule(project, {}).start(project.tasks[3]) == D(2026, 10, 12, 17)


def test_a_summary_without_scheduled_children_has_no_span() -> None:
    project = Project("p", tasks=[summary("m", "a"), Task("a", id="a")])
    schedule = Schedule(project, {})
    assert (schedule.start(project.tasks[0]), schedule.end(project.tasks[0])) == (None, None)


def test_a_summary_uses_the_pushed_dates_of_its_children() -> None:
    project = Project(
        "p",
        tasks=[
            summary("m", "b"),
            timed("a", D(2026, 10, 6, 9), D(2026, 10, 9, 17)),
            timed("b", D(2026, 10, 6, 9), D(2026, 10, 7, 17), predecessors=["a"]),
        ],
    )
    assert Schedule(project, {}).start(project.tasks[0]) == D(2026, 10, 9, 17)  # b は a の完了まで押し出される


def test_a_summary_is_never_overdue_and_has_no_progress_state() -> None:
    project = span_project()
    now = D(2027, 1, 1)
    assert not is_overdue(project.tasks[0], project, {}, now)
    assert progress_state(project.tasks[0], project, {}, now) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`timeline.py`の先頭の import に`from projectapp.summary import children_of`を足す(循環しない: `summary.py`は`models`だけに依存)。

`Schedule._resolve`の、チェックポイントの分岐の直後に足す:

```python
        if task.kind is TaskKind.SUMMARY:  # 子の最小の開始と最大の完了。先行は持たない
            if task.id in self._active:
                return None, None
            self._active.add(task.id)
            try:
                spans = [self._resolve(child) for child in children_of(task, self._tasks)]
            finally:
                self._active.discard(task.id)
            starts = [s for s, _ in spans if s is not None]
            ends = [e for _, e in spans if e is not None]
            result = (min(starts, default=None), max(ends, default=None))
            self._done[task.id] = result
            return result
```

`effective_start`/`effective_end`の先頭(チェックポイントの分岐の次)に足す:

```python
    if task.kind is TaskKind.SUMMARY:
        return (schedule or Schedule(project, holidays)).start(task)
```

(`effective_end`は`.end(task)`)

`is_overdue`の先頭に`if task.kind is TaskKind.SUMMARY:\n        return False  # 超過は子に出る`を足す。`progress_state`の先頭に`if task.kind is TaskKind.SUMMARY:\n        return None`を足す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py test/test_timeline.py test/test_schedule.py test/test_checkpoint.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/timeline.py test/test_summary.py
git commit -m "feat: まとめの期間を子から算出する"
```

---

### Task 4: 分解の計算(`decompose.py`)

**Files:**
- Create: `src/projectapp/decompose.py`
- Modify: `test/test_summary.py`(追記)

**Interfaces:**
- Consumes: `arrange.tasks_at`・`arrange.section_at`・`models.new_id`・`MAX_SECTION_DEPTH`
- Produces:
  - `Part(name: str, effort_hours: float)`(frozen dataclass)
  - `MAX_PARTS = 20`
  - `default_parts(task: Task, count: int) -> list[Part]`(名前は`<元の名前> n`、工数は均等割り)
  - `split_effort(total: float, count: int) -> list[float]`
  - `can_make_section(path: SectionPath) -> str | None`(作れない理由。作れるなら None)
  - `decompose(project: Project, path: SectionPath, index: int, parts: Sequence[Part], *, chain: bool = True, new_section: bool = False) -> list[Task]`(プロジェクトを変更し、子を返す。不正は`ValueError`で、何も変えない)

- [ ] **Step 1: 失敗するテストを書く**

```python
from projectapp.decompose import MAX_PARTS, Part, can_make_section, decompose, default_parts, split_effort
from projectapp.models import Actual, Assignee, Category, TaskUrl


def original() -> Task:
    return Task(
        "実装", id="orig", planned_start=D(2026, 10, 6, 9), effort_hours=10.0, deadline=D(2026, 10, 20, 17),
        assignees=[Assignee("田中", 0.5)], category_id="cat", predecessors=["pre"],
        urls=[TaskUrl("t", values={"URL": "https://example.com"})], color="#112233",
    )


def decomposable() -> Project:
    return Project(
        "p",
        categories=[Category("開発", id="cat")],
        sections=[Section("開発", [Task("pre", id="pre"), original(), Task("post", id="post", predecessors=["orig"])])],
    )


PARTS = [Part("設計", 4.0), Part("実装", 4.0), Part("確認", 2.0)]


def test_split_effort_is_even_with_the_remainder_on_the_last() -> None:
    assert split_effort(10.0, 3) == [3.33, 3.33, 3.34]
    assert split_effort(0.0, 2) == [0.0, 0.0]
    assert sum(split_effort(7.0, 4)) == pytest.approx(7.0)


def test_default_parts_are_numbered_and_fit_the_name_limit() -> None:
    parts = default_parts(Task("x" * 50, effort_hours=4.0), 2)
    assert [len(p.name) for p in parts] == [50, 50]
    assert [p.effort_hours for p in parts] == [2.0, 2.0]


def test_decompose_makes_a_summary_and_children_after_it() -> None:
    project = decomposable()
    kids = decompose(project, (0,), 1, PARTS)
    tasks = project.sections[0].tasks
    assert [t.name for t in tasks] == ["pre", "実装", "設計", "実装", "確認", "post"]
    summary_task = tasks[1]
    assert (summary_task.kind, summary_task.children) == (TaskKind.SUMMARY, [k.id for k in kids])
    assert (summary_task.id, summary_task.effort_hours, summary_task.assignees, summary_task.predecessors) == ("orig", 0.0, [], [])
    assert summary_task.deadline is None and summary_task.planned_start is None


def test_children_inherit_the_attributes_and_split_the_effort() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS)
    assert [k.effort_hours for k in kids] == [4.0, 4.0, 2.0]
    for kid in kids:
        assert (kid.kind, kid.status, kid.category_id, kid.color) == (TaskKind.NORMAL, Status.NOT_STARTED, "cat", "#112233")
        assert [(a.name, a.allocation) for a in kid.assignees] == [("田中", 0.5)]
        assert kid.urls == original().urls and kid.urls is not original().urls
        assert kid.planned_start == D(2026, 10, 6, 9)
        assert kid.actuals == [] and kid.progress is None


def test_chain_links_the_children_in_order_and_the_first_takes_the_original_predecessors() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS, chain=True)
    assert [k.predecessors for k in kids] == [["pre"], [kids[0].id], [kids[1].id]]


def test_without_chain_every_child_takes_the_original_predecessors() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS, chain=False)
    assert [k.predecessors for k in kids] == [["pre"], ["pre"], ["pre"]]


def test_the_deadline_goes_to_the_last_child_only() -> None:
    kids = decompose(decomposable(), (0,), 1, PARTS)
    assert [k.deadline for k in kids] == [None, None, D(2026, 10, 20, 17)]


def test_successors_still_point_at_the_summary() -> None:
    project = decomposable()
    decompose(project, (0,), 1, PARTS)
    assert project.sections[0].tasks[-1].predecessors == ["orig"]


def test_new_section_puts_the_children_in_a_subsection_named_after_the_task() -> None:
    project = decomposable()
    kids = decompose(project, (0,), 1, PARTS, new_section=True)
    section = project.sections[0]
    assert [t.name for t in section.tasks] == ["pre", "実装", "post"]
    assert [(s.name, [t.id for t in s.tasks]) for s in section.sections] == [("実装", [k.id for k in kids])]


def test_new_section_gets_a_unique_name() -> None:
    project = decomposable()
    project.sections[0].sections.append(Section("実装"))
    decompose(project, (0,), 1, PARTS, new_section=True)
    assert [s.name for s in project.sections[0].sections] == ["実装", "実装#2"]


def test_can_make_section_explains_why_not() -> None:
    assert can_make_section((0,)) is None
    assert "セクション" in (can_make_section(()) or "")
    assert "3 階層" in (can_make_section((0, 0, 0)) or "")


@pytest.mark.parametrize("path", [(), (0, 0, 0)])
def test_new_section_is_refused_at_root_and_at_the_third_level(path: tuple[int, ...]) -> None:
    project = Project("p", tasks=[original()])
    if path:
        project = Project("p", sections=[Section("a", sections=[Section("b", sections=[Section("c", [original()])])])])
    before = repr(project)
    with pytest.raises(ValueError):
        decompose(project, path, 0, PARTS, new_section=True)
    assert repr(project) == before


@pytest.mark.parametrize(
    "parts",
    [
        [Part("a", 1.0)],  # 1 件
        [Part("a", 1.0), Part("", 1.0)],  # 名前が空
        [Part("a", 1.0), Part("b" * 51, 1.0)],  # 長い
        [Part("a", 1.0), Part("b\n", 1.0)],  # 制御文字
        [Part("a", 1.0), Part("b", -1.0)],  # 負の工数
        [Part("a", 1.0), Part("b", float("nan"))],
        [Part(str(n), 1.0) for n in range(MAX_PARTS + 1)],  # 多すぎる
    ],
)
def test_bad_parts_are_refused_without_changing_the_project(parts: list[Part]) -> None:
    project = decomposable()
    before = repr(project)
    with pytest.raises(ValueError):
        decompose(project, (0,), 1, parts)
    assert repr(project) == before


def test_a_task_with_actuals_cannot_be_decomposed() -> None:
    project = decomposable()
    project.sections[0].tasks[1].actuals = [Actual(D(2026, 10, 6, 9), D(2026, 10, 6, 12))]
    with pytest.raises(ValueError, match="実績"):
        decompose(project, (0,), 1, PARTS)


@pytest.mark.parametrize("kind", [TaskKind.CHECKPOINT, TaskKind.SUMMARY])
def test_only_normal_tasks_can_be_decomposed(kind: TaskKind) -> None:
    project = decomposable()
    project.sections[0].tasks[1].kind = kind
    with pytest.raises(ValueError):
        decompose(project, (0,), 1, PARTS)


def test_the_result_passes_the_load_validation() -> None:
    project = decomposable()
    decompose(project, (0,), 1, PARTS, new_section=True)
    parse_project(dumps_project(project), "p")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: FAIL(`projectapp.decompose`がない)

- [ ] **Step 3: 実装する**

`src/projectapp/decompose.py`:

```python
"""タスクの分解(1 つのタスクを、複数のタスクに割る)。NiceGUI には依存しない純粋関数。"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import isfinite

from projectapp.arrange import section_at, tasks_at
from projectapp.models import (
    HOURS_DECIMALS,
    MAX_SECTION_DEPTH,
    MAX_TASK_NAME_LENGTH,
    Assignee,
    Project,
    Section,
    SectionPath,
    Status,
    Task,
    TaskKind,
    has_control_char,
    new_id,
)

MAX_PARTS = 20  # 一度に分けられる数の上限


@dataclass(frozen=True)
class Part:
    name: str
    effort_hours: float


def split_effort(total: float, count: int) -> list[float]:
    """工数を count 等分する(小数点以下 2 桁)。端数は最後に寄せて、合計を保つ。"""
    each = round(total / count, 2)
    parts = [each] * (count - 1)
    return [*parts, round(total - each * (count - 1), 2)]


def default_parts(task: Task, count: int) -> list[Part]:
    """ダイアログの初期値。名前は`<元の名前> n`(上限に収める)、工数は均等割り。"""
    efforts = split_effort(task.effort_hours, count)
    width = len(str(count)) + 1
    base = task.name[: MAX_TASK_NAME_LENGTH - width]
    return [Part(f"{base} {n}", efforts[n - 1]) for n in range(1, count + 1)]


def can_make_section(path: SectionPath) -> str | None:
    """新しいセクションを作れない理由。作れるなら None。"""
    if not path:
        return "セクションに属さないタスクは、セクションにまとめられません"
    if len(path) >= MAX_SECTION_DEPTH:
        return f"セクションは {MAX_SECTION_DEPTH} 階層までです"
    return None


def _validate(task: Task, parts: Sequence[Part]) -> None:
    if task.kind is not TaskKind.NORMAL:
        raise ValueError("通常のタスクだけ分解できます")
    if task.actuals:
        raise ValueError("実績のあるタスクは分解できません")
    if not 2 <= len(parts) <= MAX_PARTS:
        raise ValueError(f"分解は 2〜{MAX_PARTS} 件で指定してください")
    for part in parts:
        name = part.name.strip()
        if not name:
            raise ValueError("名前を入力してください")
        if len(name) > MAX_TASK_NAME_LENGTH:
            raise ValueError(f"名前は{MAX_TASK_NAME_LENGTH}文字以内で入力してください")
        if has_control_char(name):
            raise ValueError("名前に改行・制御文字は使えません")
        if not isfinite(part.effort_hours) or part.effort_hours < 0:
            raise ValueError("工数は 0 以上の数値で入力してください")
        if round(part.effort_hours, HOURS_DECIMALS) != part.effort_hours:
            raise ValueError(f"工数は小数点以下{HOURS_DECIMALS}桁までで入力してください")


def _unique_name(name: str, taken: Sequence[str]) -> str:
    if name not in taken:
        return name
    n = 2
    while f"{name}#{n}" in taken:
        n += 1
    return f"{name}#{n}"


def decompose(
    project: Project,
    path: SectionPath,
    index: int,
    parts: Sequence[Part],
    *,
    chain: bool = True,
    new_section: bool = False,
) -> list[Task]:
    """`path` のセクションの `index` 番目のタスクを、`parts` の分だけの子に分解する。元のタスクはまとめとして残る。

    子は元の担当・カテゴリ・優先度・色・リンク・開始予定を引き継ぐ(工数は各行の値)。元の先行は最初の子へ移す
    (`chain` がオフなら全員が引き継ぐ)。締切は最後の子に渡す。不正なときは ValueError で、何も変えない。
    """
    tasks = tasks_at(project, path)
    task = tasks[index]
    _validate(task, parts)
    parent_section: Section | None = None
    if new_section:
        reason = can_make_section(path)
        if reason is not None:
            raise ValueError(reason)
        parent_section = section_at(project, path)
        assert parent_section is not None
    taken = project.used_ids()
    children: list[Task] = []
    for n, part in enumerate(parts):
        child_id = new_id(taken)
        taken.add(child_id)
        if n == 0 or not chain:
            predecessors = list(task.predecessors)
        else:
            predecessors = [children[n - 1].id]
        children.append(
            Task(
                part.name.strip(),
                id=child_id,
                planned_start=task.planned_start,
                effort_hours=part.effort_hours,
                priority=task.priority,
                status=Status.NOT_STARTED,
                color=task.color,
                assignees=[Assignee(a.name, a.allocation) for a in task.assignees],
                predecessors=predecessors,
                deadline=task.deadline if n == len(parts) - 1 else None,
                category_id=task.category_id,
                urls=[replace(u, values=dict(u.values)) for u in task.urls],
            )
        )
    tasks[index] = replace(
        task,
        kind=TaskKind.SUMMARY,
        children=[c.id for c in children],
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=None,
        effort_hours=0.0,
        assignees=[],
        predecessors=[],
        actuals=[],
        progress=None,
        status=Status.NOT_STARTED,
    )
    if parent_section is not None:
        name = _unique_name(task.name, [s.name for s in parent_section.sections])
        parent_section.sections.append(Section(name, list(children), id=new_id(taken)))
    else:
        tasks[index + 1 : index + 1] = children
    return children
```

(`HOURS_DECIMALS`の定義元が`models.py`でなければ、`grep -rn "HOURS_DECIMALS" src`で場所を確かめ、その import にそろえる。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/decompose.py test/test_summary.py
git commit -m "feat: タスクの分解の計算を足す"
```

---

### Task 5: 削除・コピー・先行の候補

**Files:**
- Modify: `src/projectapp/linkgraph.py:55-60,63-82`(`drop_task_links`・`link_options`)
- Modify: `src/projectapp/arrange.py:71-87`(`copy_task`)
- Modify: `src/projectapp/views.py:1059-1064`(`delete_task`)
- Modify: `test/test_summary.py`(追記)、`test/test_views.py`(追記)

**Interfaces:**
- Consumes: `summary.drop_child`・`summary.parent_map`(Task 2)
- Produces: `linkgraph.drop_task_links(project, task_id)`が`children`も整理する。`link_options(project, task)`が、`task`の親のまとめを候補から外す。`arrange.copy_task`がまとめをコピーすると通常タスクになる。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_summary.py`:

```python
from projectapp import arrange
from projectapp.linkgraph import drop_task_links, link_options


def test_drop_task_links_removes_a_deleted_child_from_its_summary() -> None:
    project = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b")])
    drop_task_links(project, "a")
    assert project.tasks[0].children == ["b"]
    drop_task_links(project, "b")
    assert project.tasks[0].kind is TaskKind.NORMAL


def test_deleting_a_summary_leaves_the_children_as_plain_tasks() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a")])
    removed = project.tasks.pop(0)
    drop_task_links(project, removed.id)
    assert [(t.name, t.kind) for t in project.tasks] == [("a", TaskKind.NORMAL)]


def test_a_child_cannot_pick_its_own_summary_as_a_predecessor() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a"), child("other")])
    assert set(link_options(project, project.tasks[1])) == {"other"}


def test_a_summary_cannot_pick_its_own_child() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a"), child("other")])
    assert set(link_options(project, project.tasks[0])) == {"other"}


def test_copying_a_summary_gives_a_plain_task_without_children() -> None:
    project = Project("p", tasks=[summary("m", "a"), child("a")])
    copy = arrange.copy_task(project, ((), 0), ((), 2))
    assert (copy.kind, copy.children) == (TaskKind.NORMAL, [])
    assert project.tasks[0].children == ["a"]
```

`test/test_views.py`(`test_delete_task_removes_its_id_from_the_successors`の近くに追記。`mount_capturing`・`choose_in_combo`・`wait_until`・`save_cache` はこのファイルの既存の部品):

```python
async def test_delete_task_keeps_the_summary_consistent(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(
        Project("既存", tasks=[
            Task("m", id="m", kind=TaskKind.SUMMARY, children=["a", "b"]), Task("a", id="a"), Task("b", id="b"),
        ]),
        tmp_path,
    )
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.delete_task((), 1)
    assert view.project.tasks[0].children == ["b"]
    view.delete_task((), 1)
    assert view.project.tasks[0].kind is TaskKind.NORMAL
```

(`TaskKind`が`test_views.py`で import されていなければ足す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py test/test_views.py -q -k "summary or drop_task_links or copying or predecessor"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`linkgraph.py`:

```python
def drop_task_links(project: Project, task_id: str) -> None:
    """全タスクの先行から、その id を取り除く(タスクの削除のとき)。まとめの子からも外し、空になったまとめは通常タスクに戻す。"""
    for task in project.all_tasks():
        if task_id in task.predecessors:
            task.predecessors = [pid for pid in task.predecessors if pid != task_id]
    drop_child(project, task_id)
```

`link_options`の`excluded`を決める所に足す(`task is not None`のとき):

```python
        parents = parent_map(project)
        excluded = {task.id, *downstream_ids(project, task.id)}
        if task.id in parents:
            excluded.add(parents[task.id])  # 子が親のまとめを先行にすると循環する
        excluded |= set(task.children)  # まとめが自分の子を先行にすると循環する
```

(`from projectapp.summary import drop_child, parent_map`)

`arrange.copy_task`の`replace(...)`に`kind=TaskKind.NORMAL if original.kind is TaskKind.SUMMARY else original.kind, children=[],`を足す(`TaskKind`を import)。

`views.py`の`delete_task`は`drop_task_links`が整理するので、変更不要。(テストで確認する。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py test/test_views.py test/test_arrange.py test/test_linkgraph.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/linkgraph.py src/projectapp/arrange.py test
git commit -m "feat: まとめの削除・コピー・先行の候補を整える"
```

---

### Task 6: 絞り込みと行の並び(折りたたみの純粋な部分)

**Files:**
- Modify: `src/projectapp/filtering.py`
- Modify: `src/projectapp/links.py:25-70`(`row_slots`・`_section_slots`)
- Modify: `test/test_summary.py`(追記)

**Interfaces:**
- Consumes: `children_of`(Task 2)
- Produces:
  - `filtering.matches(task, task_filter, by_id=None)`、`visible_task_indexes(section, task_filter, collapsed, by_id=None)`、`section_has_match(section, task_filter, by_id=None)`。`by_id`を渡すと、まとめは子のどれかが合えば合う。
  - `filtering.hidden_by_summary(project, collapsed_summaries) -> set[str]`(折りたたんだまとめの子の id)
  - `links.row_slots(project, task_filter, collapsed, read_only, row_height, add_height, collapsed_summaries=frozenset())`。絞り込み中・読み取り専用では`collapsed_summaries`を無視する。

- [ ] **Step 1: 失敗するテストを書く**

```python
from projectapp.filtering import TaskFilter, hidden_by_summary, matches, section_has_match, visible_task_indexes
from projectapp.links import row_slots


def slot_project() -> Project:
    return Project(
        "p",
        sections=[Section("s", [summary("m", "a", "b"), child("a"), child("b"), child("other")])],
    )


def test_a_summary_matches_when_a_child_matches() -> None:
    project = slot_project()
    by_id = project.task_map()
    flt = TaskFilter(query="a")
    assert not matches(project.sections[0].tasks[0], flt)
    assert matches(project.sections[0].tasks[0], flt, by_id)


def test_a_summary_matches_by_its_own_name() -> None:
    project = slot_project()
    assert matches(project.sections[0].tasks[0], TaskFilter(query="m"))


def test_visible_task_indexes_include_the_summary_of_a_matching_child() -> None:
    project = slot_project()
    section = project.sections[0]
    flt = TaskFilter(query="b")
    assert visible_task_indexes(section, flt, False, project.task_map()) == [0, 2]  # m(子 b が合う)と b


def test_section_has_match_sees_a_summary_through_its_children() -> None:
    project = Project("p", sections=[Section("s", [summary("m", "a")]), Section("t", [child("a")])])
    flt = TaskFilter(query="a")
    assert section_has_match(project.sections[0], flt, project.task_map())


def test_hidden_by_summary() -> None:
    assert hidden_by_summary(slot_project(), {"m"}) == {"a", "b"}
    assert hidden_by_summary(slot_project(), set()) == set()


def shown(slots: list) -> list[str]:
    return [s.task_id for s in slots if s.kind == "task" and s.shown]


def test_collapsed_summary_hides_its_children_rows() -> None:
    slots = row_slots(slot_project(), TaskFilter(), set(), False, 32, 24, {"m"})
    assert shown(slots) == ["m", "other"]


def test_rows_are_kept_but_not_shown_so_the_layout_keeps_the_indexes() -> None:
    slots = row_slots(slot_project(), TaskFilter(), set(), False, 32, 24, {"m"})
    assert [s.task_id for s in slots if s.kind == "task"] == ["m", "a", "b", "other"]


def test_the_summary_collapse_is_ignored_while_filtering_and_in_read_only() -> None:
    project = slot_project()
    assert shown(row_slots(project, TaskFilter(query="a"), set(), False, 32, 24, {"m"})) == ["m", "a"]
    assert shown(row_slots(project, TaskFilter(), set(), True, 32, 24, {"m"})) == ["m", "a", "b", "other"]


def test_a_collapsed_section_still_hides_everything() -> None:
    slots = row_slots(slot_project(), TaskFilter(), {(0,)}, False, 32, 24, set())
    assert shown(slots) == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`filtering.py`:

```python
from collections.abc import Collection, Mapping

from projectapp.models import Project, Section, Task, TaskKind


def matches(task: Task, task_filter: TaskFilter, by_id: Mapping[str, Task] | None = None) -> bool:
    """検索と担当者の両方に合うとき True。条件が空なら常に True。`by_id` を渡すと、まとめは子のどれかが合っても合う。"""
    if task_filter.assignee is None or task_filter.assignee in task.assignee_names:
        if task_filter.query.strip().casefold() in task.name.casefold():
            return True
    if by_id is not None and task.kind is TaskKind.SUMMARY:
        return any(matches(by_id[cid], task_filter) for cid in task.children if cid in by_id)
    return False


def visible_task_indexes(
    section: Section, task_filter: TaskFilter, collapsed: bool, by_id: Mapping[str, Task] | None = None
) -> list[int]:
    ...  # 本体は `matches(task, task_filter, by_id)` に変える


def section_has_match(section: Section, task_filter: TaskFilter, by_id: Mapping[str, Task] | None = None) -> bool:
    ...  # `matches(task, task_filter, by_id)` と、再帰に `by_id` を渡す


def hidden_by_summary(project: Project, collapsed_summaries: Collection[str]) -> set[str]:
    """折りたたんだまとめの子の id。"""
    by_id = project.task_map()
    return {
        cid
        for sid in collapsed_summaries
        if (task := by_id.get(sid)) is not None and task.kind is TaskKind.SUMMARY
        for cid in task.children
    }
```

(`...`の行は、既存の本体で`matches(task, task_filter)`を`matches(task, task_filter, by_id)`に、`section_has_match(child, task_filter)`を`section_has_match(child, task_filter, by_id)`に置き換える。)

`links.py`: `row_slots`の引数に`collapsed_summaries: Collection[str] = frozenset()`を足し、先頭で:

```python
    by_id = project.task_map()
    folded = (
        hidden_by_summary(project, collapsed_summaries)
        if not task_filter.active and not read_only
        else set()
    )
```

root のタスクの行は`matches(task, task_filter, by_id)`と`task.id not in folded`を使い(`shown`に`task.id not in folded`を掛ける。root で`matches`が偽の行は今のとおり出さない)、`_section_slots`に`by_id`と`folded`を渡す。`_section_slots`では`section_has_match(section, task_filter, by_id)`、`visible_task_indexes(section, task_filter, own_collapsed, by_id)`を使い、`RowSlot("task", ..., not hidden and ti in visible and task.id not in folded, ...)`にする。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py test/test_filtering.py test/test_linkgraph.py test/test_gantt.py -q`
Expected: PASS(`test_gantt.py`は Task 7 まで`row_slots`の呼び出しが既定値で通る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/filtering.py src/projectapp/links.py test/test_summary.py
git commit -m "feat: まとめの絞り込みと折りたたみの行の並びを足す"
```

---

### Task 7: ガントチャートの描画(帯・矢印・件数・折りたたみ)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttChart.__init__`・`slots`・`toggle_section`・`render`・`section_rows`・`task_row`・`task_chips`・`fill_percent`の呼び出し)
- Create: `test/test_decompose_ui.py`

**Interfaces:**
- Consumes: `hidden_by_summary`・`row_slots(... collapsed_summaries)`(Task 6)、`summary_status`・`summary_progress`・`children_of`・`parent_map`(Task 2)
- Produces: `GanttChart.collapsed_summaries: set[str]`、`GanttChart.toggle_summary(task_id)`、マーカー `summary-toggle-{key}-{ti}`・`summary-band-{key}-{ti}`・`summary-count-{key}-{ti}`・`task-name-{key}-{ti}`(既存)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_decompose_ui.py`(`test_gantt.py`の`mount_chart`と同じ型。`BASE`・`Recorder`は`test_gantt`から import する):

```python
from datetime import datetime

from nicegui.testing import User

from projectapp.gantt import BAND_HEIGHT_PX, SUMMARY_BAND_HEIGHT_PX, ROW_HEIGHT_PX, GanttChart
from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from test_gantt import Recorder, mount_chart


def summary_project() -> Project:
    def kid(name: str, day: int, status: Status = Status.NOT_STARTED) -> Task:
        return Task(
            name, id=name, planned_start=datetime(2026, 10, day, 9), planned_end=datetime(2026, 10, day + 1, 17),
            status=status, effort_hours=4.0, assignees=[Assignee("田中")],
        )

    return Project(
        "demo",
        base_date=datetime(2026, 10, 5).date(),
        members=[Member("田中")],
        sections=[
            Section("開発", [
                Task("実装", id="m", kind=TaskKind.SUMMARY, children=["a", "b"]),
                kid("a", 6, Status.RUNNING),
                kid("b", 9),
                Task("後続", id="z", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 9)),
            ])
        ],
    )


async def test_a_summary_draws_a_thin_band_over_its_children(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    band = user.find(marker="summary-band-0-0").elements.pop()
    assert f"height: {SUMMARY_BAND_HEIGHT_PX}px" in band._style["height"] or band._style["height"] == f"{SUMMARY_BAND_HEIGHT_PX}px"
    await user.should_not_see(marker="bar-0-0")  # 通常の棒は出さない
    await user.should_see(marker="bar-0-1")


async def test_a_summary_name_is_bold_and_has_no_assignee_chip(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    name = user.find(marker="task-name-0-0").elements.pop()
    assert "font-weight" in name._style and name._style["font-weight"] == "700"
    await user.should_not_see(marker="task-assignee-0-0")
    await user.should_see(marker="task-assignee-0-1")


async def test_children_are_indented_one_level_more_than_other_tasks(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    child_cell = user.find(marker="task-0-1").elements.pop()
    other_cell = user.find(marker="task-0-3").elements.pop()
    assert child_cell._style["padding-left"] != other_cell._style["padding-left"]


async def test_the_arrow_collapses_and_expands_the_children(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    await user.should_not_see(marker="task-0-1")
    await user.should_not_see(marker="task-0-2")
    await user.should_see(marker="task-0-3")
    assert charts[0].collapsed_summaries == {"m"}
    await user.should_see(marker="summary-count-0-0")
    user.find(marker="summary-toggle-0-0").click()
    await user.should_see(marker="task-0-1")
    assert charts[0].collapsed_summaries == set()


async def test_clicking_the_summary_name_toggles_it_too(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="task-name-0-0").click()
    assert charts[0].collapsed_summaries == {"m"}


async def test_a_collapsed_summary_shows_the_child_count(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    assert user.find(marker="summary-count-0-0").elements.pop().text == "2件"


async def test_the_section_toggle_does_not_reopen_the_children_of_a_collapsed_summary(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    user.find(marker="section-toggle-0").click()
    user.find(marker="section-toggle-0").click()
    await user.should_not_see(marker="task-0-1")
    await user.should_see(marker="task-0-0")


async def test_filtering_ignores_the_summary_collapse(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    from projectapp.filtering import TaskFilter

    charts[0].set_filter(TaskFilter(query="b"))
    await user.should_see(marker="task-0-2")  # 子 b
    await user.should_see(marker="task-0-0")  # b を子に持つまとめ


async def test_a_summary_is_never_drawn_red(user: User) -> None:
    mount_chart(summary_project())  # now=2026-10-01 なので超過しない。超過した状態でも赤くならないことは別のテストで見る
    await user.open("/")
    row = user.find(marker="row-0-0").elements.pop()
    assert "background" not in row._style or "239, 83, 80" not in row._style["background"]
```

(`SUMMARY_BAND_HEIGHT_PX`は Step 3 で定義する。`BAND_HEIGHT_PX`と`ROW_HEIGHT_PX`の import は不要なら外す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_decompose_ui.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`gantt.py`:

1. 定数(`ACTUAL_TOP_PX`の次):

```python
SUMMARY_BAND_HEIGHT_PX = 9  # まとめの細い帯(通常の棒は BAR_HEIGHT_PX = 20)
SUMMARY_BAND_TOP_PX = (ROW_HEIGHT_PX - SUMMARY_BAND_HEIGHT_PX) // 2 - 1
SUMMARY_TIP_PX = 6  # 帯の両端の三角の半幅
SUMMARY_INDENT_PX = 12  # 子の名前の欄の字下げ
```

2. `SectionView`の隣に:

```python
@dataclass
class SummaryView:
    """描画したまとめの、折りたたみで切り替える部品。描き直すたびに作り直す。"""

    arrow: ui.button | None = None
    count: ui.element | None = None
```

3. `GanttChart.__init__`に`self.collapsed_summaries: set[str] = set()  # 折りたたんだまとめの id。保存しない`、`self.summary_views: dict[str, SummaryView] = {}`、`self.task_rows: dict[str, ui.element] = {}`、`self.parents: dict[str, str] = {}`を足す。

4. `render`の先頭(`self.section_views`を初期化している箇所)で`self.summary_views = {}`、`self.task_rows = {}`、`self.parents = parent_map(self.project)`にする。`slots()`の`row_slots(...)`の末尾に`self.collapsed_summaries`を足す。`task_row`の root とセクション内の`matches(task, self.task_filter)`は`matches(task, self.task_filter, self.by_id)`に(`self.by_id = self.project.task_map()`を`render`の先頭で作る)。`section_rows`の`visible_task_indexes(...)`・`section_has_match(...)`にも`self.by_id`を渡す。`no_match_message`の`matches`にも渡す。

5. 折りたたみ:

```python
    def toggle_summary(self, task_id: str) -> None:
        """まとめの折りたたみを切り替える。描き直さず、子の行の表示・矢印・件数だけを変える。"""
        self.collapsed_summaries.symmetric_difference_update({task_id})
        view = self.summary_views.get(task_id)
        if view is None or self.options.read_only:
            return
        folded = task_id in self.collapsed_summaries
        if view.arrow is not None:
            view.arrow.props(f"icon={ARROW_COLLAPSED if folded else ARROW_EXPANDED}")
        if view.count is not None:
            view.count.set_visibility(folded)
        self.sync_task_rows()
        self.update_links()

    def sync_task_rows(self) -> None:
        """行の表示を、`slots()`(セクション・まとめの折りたたみ・絞り込みをすべて見たもの)に合わせる。"""
        for slot in self.slots():
            row = self.task_rows.get(slot.task_id) if slot.task_id is not None else None
            if row is not None:
                row.set_visibility(slot.shown)
```

`toggle_section`の末尾の`self.apply_visibility(...)`のあとに`self.sync_task_rows()`を足す(セクションを開いても、折りたたんだまとめの子が出ないように)。`reset_collapsed`には`self.collapsed_summaries.clear()`も足す。`reset_collapsed`が`set_project`で呼ばれるとは限らないので、別のプロジェクトを開くとき(`views`が`reset_collapsed`を呼んでいる箇所)で足りることを`grep -n reset_collapsed src`で確かめる。

6. `task_row`: 行を作った直後に`self.task_rows[task.id] = row`。`section_rows`の`row.set_visibility(not hidden and ti in shown)`は`not hidden and ti in shown and task.id not in folded`にする(`folded = hidden_by_summary(self.project, self.collapsed_summaries) if not self.task_filter.active and not self.options.read_only else set()`を`section_rows`の先頭で求める)。

名前の欄(`with cell:`の中、`name = ui.label(...)`の前):

```python
                summary = task.kind is TaskKind.SUMMARY
                if summary and not self.options.read_only:
                    view = self.summary_views[task.id] = SummaryView()
                    folded_now = task.id in self.collapsed_summaries
                    view.arrow = ui.button(
                        icon=ARROW_COLLAPSED if folded_now else ARROW_EXPANDED,
                        on_click=lambda tid=task.id: self.toggle_summary(tid),
                    ).props("flat dense round size=sm").classes("shrink-0").mark(f"summary-toggle-{key}-{ti}")
```

名前の欄の左の字下げ: `cell_style`の`padding-left`に、子(`task.id in self.parents`)なら`SUMMARY_INDENT_PX`を足す。名前のラベルは、まとめなら`.style("font-weight: 700")`と、クリックで`toggle_summary`(読み取り専用では付けない。`edit_on_click`が行の編集を開くので、名前のラベルの click は`.on("click.stop", ...)`にする)。件数のチップは`task_chips`の先頭で、まとめなら:

```python
        if task.kind is TaskKind.SUMMARY:
            count = ui.label(f"{len(task.children)}件").style(PROGRESS_TEXT_STYLE).mark(f"summary-count-{key}-{ti}")
            count.set_visibility(task.id in self.collapsed_summaries)
            if task.id in self.summary_views:
                self.summary_views[task.id].count = count
```

(`task_chips`は`show_chips`のときだけ呼ばれる。件数は`show_chips`に関わらず出したいので、呼び出しを`task_row`の中の`if self.options.show_chips:`の外に出す別メソッド`summary_count(key, ti, task)`にしてもよい。カテゴリと進捗のチップは既存のまま出る。)

進捗のチップ: `percent = None if task.kind is TaskKind.CHECKPOINT else fill_percent(task)`を、まとめなら`summary_progress(children_of(task, self.by_id))`にする。

7. まとめの帯:`task_row`の`if task.kind is TaskKind.CHECKPOINT:`の次に:

```python
            if task.kind is TaskKind.SUMMARY:
                self.summary_band(path, key, ti, task, columns, width)
                return row
```

```python
    def summary_band(
        self, path: SectionPath, key: str, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """まとめの細い帯。子の期間を覆い、状態の色で塗る。両端に下向きの三角。"""
        start, end = self.schedule.start(task), self.schedule.end(task)
        span = bar_span(start, end, columns)
        if span is None or not self.bar_visible(start, end, columns):
            return
        left, length = span
        band_width = max(length * width, MIN_BAR_PX)
        kids = children_of(task, self.by_id)
        status = summary_status(kids)
        percent = summary_progress(kids)
        band = ui.element("div").style(
            f"position: absolute; left: {from_name(left * width)}; width: {band_width:.1f}px;"
            f" top: {SUMMARY_BAND_TOP_PX}px; height: {SUMMARY_BAND_HEIGHT_PX}px;"
            f" background: {STATUS_COLOR_VAR}; border-radius: 1px; cursor: pointer"
        )
        band.classes(STATUS_CLASSES[status])
        self.edit_on_click(band, path, ti)
        band.mark(f"summary-band-{key}-{ti}")
        with band:
            if percent:
                ui.element("div").style(
                    f"position: absolute; left: 0; top: 0; bottom: 0; width: {percent}%;"
                    " background: rgba(0, 0, 0, 0.25); pointer-events: none"
                )
            for side, offset in (("left", -SUMMARY_TIP_PX), ("right", -SUMMARY_TIP_PX)):
                ui.element("div").style(
                    f"position: absolute; {side}: {offset}px; top: {SUMMARY_BAND_HEIGHT_PX}px; width: 0; height: 0;"
                    f" border-top: {SUMMARY_TIP_PX + 1}px solid var(--scolor);"
                    f" border-left: {SUMMARY_TIP_PX}px solid transparent;"
                    f" border-right: {SUMMARY_TIP_PX}px solid transparent; pointer-events: none"
                )
```

帯のクリックで編集ダイアログを開く(`edit_on_click`)。`band`の`overflow`は`visible`のまま(三角が帯の外へ出る)。`STATUS_CLASSES[status]`は`--scolor`を決めるクラスなので、三角の`var(--scolor)`が帯の色と一致する。

8. 超過・進捗の状態:`task_row`の`overdue = ...`と`state = progress_state(...)`は、Task 3 でまとめに対して False / None を返すので、変更不要。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_decompose_ui.py test/test_gantt.py test/test_preview.py -q`
Expected: PASS。落ちた既存テストは、`row_slots`の引数追加か`by_id`の追加が原因なので、呼び出し側を直す(期待値は変えない)。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gantt.py test/test_decompose_ui.py
git commit -m "feat: ガントチャートにまとめの帯と折りたたみを足す"
```

---

### Task 8: 編集ダイアログ(まとめの編集と`分解…`ボタン)

**Files:**
- Modify: `src/projectapp/forms.py:262-303`(`build_task`)
- Modify: `src/projectapp/task_dialog.py:826-1148`(`open_task_dialog`)
- Modify: `test/test_task_dialog.py`(追記)、`test/test_forms.py`(追記)

**Interfaces:**
- Consumes: `decompose.can_make_section`(Task 4)は使わない(ダイアログは判定しない)。
- Produces:
  - `build_task(..., kind=TaskKind.SUMMARY)`は、既存のまとめの`name`・`category_id`・`priority`・`urls`だけを更新して返す(`existing`が必須。他の項目は引き継ぐ)。
  - `open_task_dialog(..., on_decompose: Callable[[], object] | None = None)`。マーカー`task-decompose`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py`:

```python
def test_build_task_for_a_summary_updates_only_the_shared_fields() -> None:
    existing = Task("m", id="m", kind=TaskKind.SUMMARY, children=["a"], color="#112233")
    built = build_task(
        existing, name=" 新 ", planned_start="", planned_end="", planned_end_manual=False, deadline="",
        effort_hours=5.0, priority=Priority.HIGH, status=Status.RUNNING, color="#ffffff",
        category_id="c", kind=TaskKind.SUMMARY,
    )
    assert (built.kind, built.children, built.name, built.priority, built.category_id) == (
        TaskKind.SUMMARY, ["a"], "新", Priority.HIGH, "c",
    )
    assert (built.effort_hours, built.status, built.color, built.predecessors) == (0.0, Status.NOT_STARTED, "#112233", [])
```

(`build_task`の引数名は`forms.py:250-266`の既存の定義に合わせる。上の呼び出しで足りない必須引数があれば、`test_forms.py`の既存の呼び出しにならって足す。)

`test/test_task_dialog.py`:

```python
async def test_a_summary_dialog_shows_only_name_category_priority_and_links(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("m", id="m", kind=TaskKind.SUMMARY, children=["a"]), saved)
    await user.open("/")
    user.find("開く").click()
    await user.should_see(marker="task-name")
    await user.should_see(marker="task-category")
    for marker in ("task-status", "task-kind", "task-predecessors", "task-color", "task-conversion"):
        await user.should_not_see(marker=marker)


async def test_a_summary_dialog_saves_a_summary(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("m", id="m", kind=TaskKind.SUMMARY, children=["a"]), saved)
    await user.open("/")
    user.find("開く").click()
    user.find(marker="task-name").type("改名")
    user.find(marker="task-save").click()
    assert (saved[0].kind, saved[0].children, saved[0].name.endswith("改名")) == (TaskKind.SUMMARY, ["a"], True)


async def test_the_kind_toggle_never_offers_summary_for_a_normal_task(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("x"), saved)
    await user.open("/")
    user.find("開く").click()
    toggle = user.find(marker="task-kind").elements.pop()
    assert TaskKind.SUMMARY not in toggle.options


async def test_decompose_button_is_shown_for_a_normal_saved_task_only(user: User) -> None:
    calls: list[str] = []
    mount_dialog(Task("x"), [], on_decompose=lambda: calls.append("go"))
    await user.open("/")
    user.find("開く").click()
    user.find(marker="task-decompose").click()
    assert calls == ["go"]


async def test_decompose_button_is_not_shown_for_a_new_task_a_checkpoint_or_a_task_with_actuals(user: User) -> None:
    for task in (None, Task("c", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 12, 17)),
                 Task("r", actuals=[Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12))])):
        mount_dialog(task, [], on_decompose=lambda: None)
        await user.open("/")
        user.find("開く").click()
        await user.should_not_see(marker="task-decompose")
```

(`mount_dialog`の引数に`on_decompose`を足して`open_task_dialog`へ渡す。`mount_dialog`の中のボタンの文言(`開く`)は`test_task_dialog.py:50`付近の既存の定義を確かめ、合わせる。同じ`user`で`mount_dialog`を繰り返すと`@ui.page("/")`が重なるので、最後のテストは 3 つに分けて書く。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py test/test_task_dialog.py -q -k "summary or decompose"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`forms.py`の`build_task`で、`base = existing or Task(clean)`の次に:

```python
    if kind is TaskKind.SUMMARY:
        if existing is None or existing.kind is not TaskKind.SUMMARY:
            raise ValueError("まとめは分解でだけ作れます")
        return replace(
            existing,
            name=clean,
            category_id=category_id,
            priority=priority,
            urls=existing.urls if urls is None else urls,
        )
```

`task_dialog.py`:

- シグネチャに`on_decompose: Callable[[], object] | None = None`を足す。
- `kind`のトグル:`options = {k: k.value for k in TaskKind if k is not TaskKind.SUMMARY}`。`initial.kind is TaskKind.SUMMARY`のときは、トグルを作るが`kind.set_visibility(False)`にし、値は`TaskKind.SUMMARY`(トグルの options にないので、`ui.toggle`の value は`TaskKind.NORMAL`で作り、保存時に`summary = initial.kind is TaskKind.SUMMARY`で`kind=TaskKind.SUMMARY`を渡す)。
- `refresh_visibility`の先頭に、まとめの分岐を足す:

```python
            if is_summary:
                for widget in (
                    fields.first_row, effort, conversion, actual_box, progress_field.container,
                    assignee_fields.container, predecessors, push, status, hint, color, kind_hint, layout_toggle,
                ):
                    widget.set_visibility(False)
                for widget in (category, priority_box, url_box):
                    widget.set_visibility(True)
                return
```

  `is_summary = initial.kind is TaskKind.SUMMARY`は`kind`の作成の前で定義する。`apply_kind`・`refresh_push`は、まとめでも呼ばれて壊れないこと(`status.set_options`は呼ばれてよい)を、テストで確かめる。
- `save()`の`build_task(...)`の`kind=`を`TaskKind.SUMMARY if is_summary else TaskKind(kind.value)`にする。
- ボタン:下部の`with ui.row().classes("w-full items-center"):`の、削除ボタンの次に:

```python
            if (
                task is not None
                and on_decompose is not None
                and task.kind is TaskKind.NORMAL
                and not task.actuals
            ):
                def decompose_now() -> None:
                    if current() != opened:
                        ui.notify("編集内容を保存してから分解してください", type="warning")
                        return
                    dialog.close()
                    on_decompose()

                ui.button("分解…", on_click=decompose_now).props("flat").mark("task-decompose")
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_forms.py test/test_task_dialog.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py test
git commit -m "feat: まとめの編集と、編集ダイアログの分解ボタンを足す"
```

---

### Task 9: 分解ダイアログと画面の配線

**Files:**
- Create: `src/projectapp/decompose_dialog.py`
- Modify: `src/projectapp/views.py:1021-1060`(`edit_task`)
- Modify: `test/test_decompose_ui.py`(追記)

**Interfaces:**
- Consumes: `decompose.Part`・`default_parts`・`can_make_section`・`decompose`(Task 4)、`open_task_dialog(on_decompose=...)`(Task 8)
- Produces:
  - `open_decompose_dialog(task: Task, section_reason: str | None, on_apply: Callable[[list[Part], bool, bool], object]) -> ui.dialog`。`on_apply(parts, chain, new_section)`が`ValueError`を投げたら、ダイアログを閉じず、エラー欄に出す。
  - `MainView.decompose_task(path: SectionPath, index: int) -> None`
  - マーカー: `decompose-name-{n}`・`decompose-effort-{n}`・`decompose-remove-{n}`・`decompose-add`・`decompose-chain`・`decompose-section`・`decompose-total`・`decompose-error`・`decompose-apply`・`decompose-cancel`

- [ ] **Step 1: 失敗するテストを書く**

```python
from projectapp.decompose import Part
from projectapp.decompose_dialog import open_decompose_dialog
from projectapp.models import Task
from nicegui import ui


def mount_decompose(task: Task, calls: list[tuple], reason: str | None = None, fail: str | None = None) -> None:
    @ui.page("/")
    def index() -> None:
        def on_apply(parts: list[Part], chain: bool, new_section: bool) -> None:
            if fail:
                raise ValueError(fail)
            calls.append((parts, chain, new_section))

        ui.button("開く", on_click=lambda: open_decompose_dialog(task, reason, on_apply))


async def test_the_dialog_starts_with_two_even_rows(user: User) -> None:
    mount_decompose(Task("実装", effort_hours=5.0), [])
    await user.open("/")
    user.find("開く").click()
    assert user.find(marker="decompose-name-0").elements.pop().value == "実装 1"
    assert user.find(marker="decompose-effort-0").elements.pop().value == 2.5
    assert user.find(marker="decompose-effort-1").elements.pop().value == 2.5


async def test_apply_passes_the_rows_and_the_options(user: User) -> None:
    calls: list[tuple] = []
    mount_decompose(Task("実装", effort_hours=4.0), calls)
    await user.open("/")
    user.find("開く").click()
    user.find(marker="decompose-apply").click()
    assert calls == [([Part("実装 1", 2.0), Part("実装 2", 2.0)], True, False)]


async def test_rows_can_be_added_and_removed_but_not_below_two(user: User) -> None:
    calls: list[tuple] = []
    mount_decompose(Task("実装", effort_hours=3.0), calls)
    await user.open("/")
    user.find("開く").click()
    user.find(marker="decompose-add").click()
    await user.should_see(marker="decompose-name-2")
    user.find(marker="decompose-remove-2").click()
    await user.should_not_see(marker="decompose-name-2")
    await user.should_not_see(marker="decompose-remove-1")  # 2 行のときは削除を出さない


async def test_the_total_warns_when_it_differs_from_the_original(user: User) -> None:
    mount_decompose(Task("実装", effort_hours=4.0), [])
    await user.open("/")
    user.find("開く").click()
    assert "一致" in user.find(marker="decompose-total").elements.pop().text or "4" in user.find(marker="decompose-total").elements.pop().text
    user.find(marker="decompose-effort-0").elements.pop().set_value(9.0)
    assert "元の工数" in user.find(marker="decompose-total").elements.pop().text


async def test_the_section_option_is_disabled_with_the_reason(user: User) -> None:
    mount_decompose(Task("実装"), [], reason="セクションは 3 階層までです")
    await user.open("/")
    user.find("開く").click()
    box = user.find(marker="decompose-section").elements.pop()
    assert not box.enabled
    await user.should_see("セクションは 3 階層までです")


async def test_an_error_from_the_callback_keeps_the_dialog_open(user: User) -> None:
    mount_decompose(Task("実装"), [], fail="実績のあるタスクは分解できません")
    await user.open("/")
    user.find("開く").click()
    user.find(marker="decompose-apply").click()
    await user.should_see("実績のあるタスクは分解できません")
    await user.should_see(marker="decompose-apply")
```

`MainView`の配線のテストを`test/test_views.py`に:

```python
async def test_decompose_task_makes_a_summary_in_one_undo_step(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("開発", [Task("実装", effort_hours=4.0)])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.apply_decompose((0,), 0, [Part("a", 2.0), Part("b", 2.0)], True, False)
    assert [t.name for t in view.project.sections[0].tasks] == ["実装", "a", "b"]
    view.undo()
    assert [t.name for t in view.project.sections[0].tasks] == ["実装"]
    assert view.project.sections[0].tasks[0].kind is TaskKind.NORMAL
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_decompose_ui.py test/test_views.py -q -k "decompose"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`src/projectapp/decompose_dialog.py`:

```python
"""タスクの分解ダイアログ。名前と工数の行を足し引きして、分解を指定する。"""

from collections.abc import Callable

from nicegui import ui

from projectapp.decompose import MAX_PARTS, Part, default_parts
from projectapp.models import MAX_TASK_NAME_LENGTH, Task

MIN_ROWS = 2


def total_text(rows: list[tuple[str, float]], original: float) -> str:
    total = round(sum(effort for _, effort in rows), 2)
    if round(original, 2) == total:
        return f"工数の合計 {total:g}h(元の工数と一致)"
    return f"工数の合計 {total:g}h(元の工数 {original:g}h と違います。このまま分解もできます)"


def open_decompose_dialog(
    task: Task,
    section_reason: str | None,
    on_apply: Callable[[list[Part], bool, bool], object],
) -> ui.dialog:
    """`on_apply(行, 連結する, 新しいセクションにまとめる)`。ValueError なら、閉じずにエラー欄へ出す。"""
    rows = default_parts(task, MIN_ROWS)
    with ui.dialog().props("persistent") as dialog, ui.card().classes("w-[36rem] max-w-full"):
        ui.label(f"「{task.name}」を分解").classes("text-h6")
        ui.label("元のタスクは「まとめ」として残ります。").classes("text-caption text-grey")
        box = ui.column().classes("w-full gap-1")
        total = ui.label("").classes("text-caption").mark("decompose-total")
        add = ui.button("行を足す", icon="add", on_click=lambda: add_row()).props("flat dense").mark("decompose-add")
        chain = ui.checkbox("順に連結する(前の行を先行にする)", value=True).mark("decompose-chain")
        section = ui.checkbox("新しいセクションにまとめる", value=False).mark("decompose-section")
        if section_reason is not None:
            section.set_enabled(False)
            ui.label(section_reason).classes("text-caption text-grey")
        error = ui.label("").classes("text-negative").mark("decompose-error")

        def refresh_total() -> None:
            total.set_text(total_text([(p.name, p.effort_hours) for p in rows], task.effort_hours))

        def redraw() -> None:
            box.clear()
            with box:
                for n, part in enumerate(rows):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        name = ui.input(value=part.name).props(f"dense maxlength={MAX_TASK_NAME_LENGTH}")
                        name.classes("grow").mark(f"decompose-name-{n}")
                        name.on_value_change(lambda e, n=n: rows.__setitem__(n, Part(e.value or "", rows[n].effort_hours)))
                        effort = ui.number(value=part.effort_hours, min=0, step=0.5, suffix="h").props("dense")
                        effort.classes("w-28").mark(f"decompose-effort-{n}")
                        effort.on_value_change(
                            lambda e, n=n: (rows.__setitem__(n, Part(rows[n].name, e.value or 0.0)), refresh_total())
                        )
                        if len(rows) > MIN_ROWS:
                            ui.button(icon="close", on_click=lambda n=n: remove_row(n)).props(
                                "flat dense round size=sm"
                            ).mark(f"decompose-remove-{n}")
            add.set_enabled(len(rows) < MAX_PARTS)
            refresh_total()

        def add_row() -> None:
            rows.append(Part(f"{task.name[: MAX_TASK_NAME_LENGTH - 3]} {len(rows) + 1}", 0.0))
            redraw()

        def remove_row(n: int) -> None:
            del rows[n]
            redraw()

        def apply() -> None:
            error.set_text("")
            try:
                on_apply(list(rows), bool(chain.value), bool(section.value) and section_reason is None)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            dialog.close()

        redraw()
        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("decompose-cancel")
            ui.button("分解", on_click=apply).mark("decompose-apply")
    dialog.open()
    return dialog
```

`views.py`:

```python
    def decompose_task(self, path: SectionPath, index: int) -> None:
        task = self.tasks_in(path)[index]
        open_decompose_dialog(
            task,
            can_make_section(path),
            lambda parts, chain, new_section: self.apply_decompose(path, index, parts, chain, new_section),
        )

    def apply_decompose(
        self, path: SectionPath, index: int, parts: list[Part], chain: bool, new_section: bool
    ) -> None:
        """分解して再描画する(元に戻すの 1 ステップ)。不正なときは ValueError(何も変えない)。"""
        decompose(self.project, path, index, parts, chain=chain, new_section=new_section)
        if path:
            self.gantt.expand_section(path)
        self.after_edit()
        ui.notify(f"「{self.tasks_in(path)[index].name}」を {len(parts)} 件に分解しました")
```

`edit_task`の`open_task_dialog(...)`に`on_decompose=lambda: self.decompose_task(path, task_index),`を足す。`views.py`の import に`Part, can_make_section, decompose`と`open_decompose_dialog`を足す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_decompose_ui.py test/test_views.py test/test_task_dialog.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/decompose_dialog.py src/projectapp/views.py test
git commit -m "feat: 分解ダイアログと、編集ダイアログからの分解を足す"
```

---

### Task 10: ダッシュボード・PlantUML・3 者マージ

**Files:**
- Modify: `src/projectapp/dashboard.py`(`period_for`・`summarize_progress`・`summarize_loads`・`summarize_workload`・`summarize_due`)
- Modify: `src/projectapp/plantuml.py:141-199`
- Modify: `src/projectapp/merge.py:208-213,300-317`
- Modify: `test/test_summary.py`(追記)

**Interfaces:**
- Consumes: `TaskKind.SUMMARY`、`Schedule`、`children_of`
- Produces: `dashboard._tasks(project) -> list[Task]`(まとめを除く)。`build_plantuml`はまとめを出さず、`skipped`にも数えず、矢印を最後の子から引く。`merge_projects`が`children`を統合する。

- [ ] **Step 1: 失敗するテストを書く**

```python
from datetime import date

from projectapp.dashboard import Period, PeriodKind, summarize_due, summarize_progress, summarize_workload
from projectapp.merge import merge_projects
from projectapp.plantuml import build_plantuml
from projectapp.filtering import TaskFilter
from projectapp.preview import Scale  # Scale の定義元は plantuml.py の import を確かめる


def dashboard_project(with_summary: bool) -> Project:
    a = timed("a", D(2026, 10, 6, 9), D(2026, 10, 7, 17), effort_hours=4.0, assignees=[Assignee("田中", 1.0)])
    b = timed("b", D(2026, 10, 8, 9), D(2026, 10, 9, 17), effort_hours=2.0, assignees=[Assignee("田中", 1.0)],
              deadline=D(2026, 10, 9, 17))
    tasks = [a, b]
    if with_summary:
        tasks.insert(0, summary("m", "a", "b"))
    return Project("p", base_date=date(2026, 10, 5), members=[Member("田中")], tasks=tasks)


NOW = D(2026, 10, 7, 12)
PERIOD = Period(date(2026, 10, 5), date(2026, 10, 11))


def test_the_dashboard_progress_ignores_the_summary() -> None:
    plain = summarize_progress(dashboard_project(False), {}, NOW)
    with_summary = summarize_progress(dashboard_project(True), {}, NOW)
    assert (with_summary.counts, with_summary.rate) == (plain.counts, plain.rate)


def test_the_dashboard_workload_and_due_ignore_the_summary() -> None:
    plain, withs = dashboard_project(False), dashboard_project(True)
    assert summarize_workload(withs, PERIOD, {}, NOW) == summarize_workload(plain, PERIOD, {}, NOW)
    assert summarize_due(withs, PERIOD, NOW, {}) == summarize_due(plain, PERIOD, NOW, {})


def puml(project: Project) -> str:
    return build_plantuml(
        project, {}, (date(2026, 10, 5), date(2026, 10, 18)), Scale.DAY, TaskFilter(), NOW
    ).text


def test_plantuml_does_not_draw_the_summary_and_does_not_count_it_as_skipped() -> None:
    project = dashboard_project(True)
    result = build_plantuml(project, {}, (date(2026, 10, 5), date(2026, 10, 18)), Scale.DAY, TaskFilter(), NOW)
    assert "[m]" not in result.text
    assert (result.task_count, result.skipped) == (2, 0)


def test_plantuml_draws_the_arrow_from_the_latest_child_for_a_successor_of_the_summary() -> None:
    project = dashboard_project(True)
    project.tasks.append(timed("after", D(2026, 10, 13, 9), D(2026, 10, 14, 9), predecessors=["m"]))
    text = puml(project)
    # a=T1, b=T2, after=T3。b の完了が最も遅い
    assert "[T2] -> [T3]" in text and "[T1] -> [T3]" not in text


def test_plantuml_draws_no_arrow_for_a_summary_without_drawn_children() -> None:
    project = Project("p", tasks=[summary("m", "a"), Task("a", id="a"), timed("z", D(2026, 10, 6, 9), D(2026, 10, 7, 9), predecessors=["m"])])
    assert "->" not in puml(project)


def test_merge_takes_the_one_sided_change_of_the_children() -> None:
    base = Project("p", tasks=[summary("m", "a"), child("a"), child("b")])
    ours = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b")])
    result = merge_projects(base, ours, base)
    assert result.project.tasks[0].children == ["a", "b"] and not result.conflicts


def test_merge_conflicts_when_both_sides_change_the_children() -> None:
    base = Project("p", tasks=[summary("m", "a"), child("a"), child("b"), child("c")])
    ours = Project("p", tasks=[summary("m", "a", "b"), child("a"), child("b"), child("c")])
    theirs = Project("p", tasks=[summary("m", "a", "c"), child("a"), child("b"), child("c")])
    assert [c.field for c in merge_projects(base, ours, theirs).conflicts] == ["children"]


def test_merge_drops_deleted_children_and_reverts_an_empty_summary() -> None:
    base = Project("p", tasks=[summary("m", "a"), child("a")])
    theirs = Project("p", tasks=[summary("m", "a")])  # a を削除(m の children は触っていない)
    result = merge_projects(base, base, theirs)
    assert result.project.tasks[0].kind is TaskKind.NORMAL and result.project.tasks[0].children == []
```

(`summarize_*`・`merge_projects`の戻り値の属性名は、既存のテスト(`test_dashboard.py`・`test_merge.py`)の使い方に合わせて直す。`Scale`の import 元も`plantuml.py`の先頭で確かめる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_summary.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`dashboard.py`:

```python
def _tasks(project: Project) -> list[Task]:
    """集計の対象のタスク。まとめは、子の工数・進捗・期限を二重に数えないよう外す。"""
    return [task for task in project.all_tasks() if task.kind is not TaskKind.SUMMARY]
```

`period_for`・`summarize_progress`・`summarize_loads`・`summarize_workload`・`summarize_due`の`for task in project.all_tasks():`を`for task in _tasks(project):`に置き換える(`grep -n "all_tasks()" src/projectapp/dashboard.py`で全箇所を確かめる)。

`plantuml.py`の`emit`の先頭(`start = effective_start(...)`の前)に:

```python
        if task.kind is TaskKind.SUMMARY:
            return  # 親子の構文がなく、帯を出すと子と二重になる。区切り(セクション)が親子を表す
```

矢印:

```python
    summaries = {t.id: t for t in project.all_tasks() if t.kind is TaskKind.SUMMARY}

    def source_alias(pid: str) -> str | None:
        """先行の別名。まとめは、出力した子のうち完了が最も遅いものから引く。"""
        if pid in aliases:
            return aliases[pid]
        summary_task = summaries.get(pid)
        if summary_task is None:
            return None
        drawn = [t for t in order if t.id in summary_task.children]
        if not drawn:
            return None
        latest = max(drawn, key=lambda t: schedule.end(t) or datetime.min)
        return aliases[latest.id]

    arrows = []
    for task in order:
        for pid in task.predecessors:
            alias = source_alias(pid)
            if alias is not None and pid != task.id:
                arrows.append(f"[{alias}] -> [{aliases[task.id]}]")
```

(`arrows`の既存の内包表記を置き換える。)

`merge.py`:`TASK_LABELS`に`"children": "子"`を足す。`make_task`:

```python
        data = {
            k: v for k, v in record.items()
            if k not in ("assignees", "parent", "predecessors", "category_id", "children")
        }
        ...
        children = [c for c in record["children"] if c in tasks]
        if record["kind"] == TaskKind.SUMMARY and not children:
            data["kind"] = TaskKind.NORMAL  # 子がいなくなったまとめは、通常タスクに戻す
        return Task(id=key, assignees=assignees, predecessors=predecessors, category_id=category,
                    children=children, **data)
```

(`TaskKind`を import。`record["kind"]`は`_flatten`の`getattr(t, "kind")`なので`TaskKind`。`children`はリストなので、`Record`の比較は既存の`predecessors`・`urls`と同じ「リスト全体を 1 項目」で働く。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_summary.py test/test_dashboard.py test/test_plantuml.py test/test_merge.py test/test_handoff.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/dashboard.py src/projectapp/plantuml.py src/projectapp/merge.py test/test_summary.py
git commit -m "feat: ダッシュボード・PlantUML・マージがまとめを扱えるようにする"
```

---

### Task 11: 仕様と記録の更新、全体の確認

**Files:**
- Modify: `CLAUDE.md`(`プロジェクトファイルの先頭に version`の行、ガントチャートの節)
- Modify: `docs/development.md`(モジュール構成の表、`version`の記述)
- Modify: `file-format.md`(プロジェクトファイルの形式の節。ファイルの有無を`ls`で確かめる)
- Modify: `docs/superpowers/specs/2026-10-18-task-decompose-design.md`(状態・差分の反映)
- Modify: `docs/superpowers/README.md`(一覧に 1 行)
- Modify: `docs/request-history.md`、`.claude/MEMORY.md`(要望 33 の状態)

- [ ] **Step 1: CLAUDE.md に仕様を書く**

「ガントチャート」の節に、次の趣旨を足す(既存の文体にそろえる):

- タスクの分解: 編集ダイアログの`分解…`で、名前と工数の行を足して分解する。元のタスクは`まとめ`として残る。実績のあるタスクは分解できない。
- `まとめ`は、子の期間を覆う細い帯で出し、期間・進捗・状態は子から算出する(保存しない)。編集では名前・カテゴリ・優先度・リンクだけを持つ。子が 0 件になったら通常タスクに戻る。
- 折りたたみ: まとめの行の矢印か名前のクリックで子の行を隠す。件数を出す。絞り込み中・プレビューでは無視する。保存せず、元に戻す・やり直しの対象にしない。
- 新しいセクションにまとめるオプション。root と 3 階層目では使えない。
- PlantUML の出力はまとめの帯を出さず、矢印は最後に完了する子から引く。ダッシュボードは、まとめを集計から外す。

`プロジェクトファイルの先頭にversion(整数。現在 5)`を`現在 6`にする。

- [ ] **Step 2: development.md と file-format.md**

モジュール構成の表に`summary.py`・`decompose.py`・`decompose_dialog.py`の行を足し、`models.py`の説明に`Task.children`を足し、`version`を 6 にする。`file-format.md`にタスクの`kind: "まとめ"`と`children`を足す(version 6)。

- [ ] **Step 3: 設計書と索引**

設計書の状態を`実装済み — 要望 33 — マージ PR #(マージ後に番号を入れる)`にし、「設計書との差分」(この計画の先頭の 8 項目)を設計書に反映する(入口は編集ダイアログのみ、`連結する`がオフのときの先行、コピー・削除、検証、絞り込み)。`docs/superpowers/README.md`の表に`| 2026-10-18 | タスクの分解(まとめ) | [設計](specs/2026-10-18-task-decompose-design.md) | [計画](plans/2026-10-18-task-decompose.md) | 要望 33 | (マージ後に記入) | — |`を足す。`docs/request-history.md`の要望 33 の状態を`実装済み`にし、`.claude/MEMORY.md`の要望 33 を更新する。

- [ ] **Step 4: 全体を確かめる**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS、`ty check`が通る。件数を報告に書く(以前は 2,827 件)。

- [ ] **Step 5: 実機で確かめる(ユーザーに依頼する前に、ブランチを`git branch --show-current`で確かめる)**

`uv run python -m projectapp.main`で起動し、次を目で確認する:タスクを開く → `分解…` → 3 行に分けて分解 → まとめの帯と子の行 → 矢印で折りたたみ → `Ctrl/Cmd+Z`で 1 回で戻る → `新しいセクションにまとめる`をオンで分解 → プレビューで子が全部出る → PlantUML として保存して中身を確かめる。

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs file-format.md .claude/MEMORY.md
git commit -m "docs: タスクの分解(まとめ)の仕様と記録を更新する(要望 33)"
```

---

## Self-Review(計画の書き手による確認)

- **設計書の網羅**:モデル・保存(Task 1)、状態・進捗(Task 2)、期間(Task 3)、分解の計算・セクション・引き継ぎ(Task 4)、削除・コピー(Task 5)、折りたたみ・絞り込み(Task 6・7)、見た目(Task 7)、編集ダイアログと入口(Task 8)、ダイアログと元に戻す 1 ステップ(Task 9)、ダッシュボード・PlantUML・マージ・担当者への書き出し(Task 10。書き出しは、まとめに担当がないので変更不要。`tasks_for`が担当者で絞る)、記録(Task 11)。
- **型の一致**:`row_slots(..., collapsed_summaries)`の位置引数の順は Task 6 と Task 7 で同じ(`add_height`の次)。`decompose(project, path, index, parts, *, chain, new_section)`は Task 4・9 で同じ。`Part(name, effort_hours)`は Task 4・9・10 で同じ。
- **未確認の前提**(実装者が最初に確かめる):`HOURS_DECIMALS`の定義元、`test_gantt.py`の`Recorder`・`mount_chart`の import 可否(`test_decompose_ui.py`から import できなければ、同じ定義を複製する)、`summarize_*`・`merge_projects`の戻り値の属性名、`mount_dialog`の開くボタンの文言。
