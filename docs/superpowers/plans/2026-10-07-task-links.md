# タスク同士の矢印連結 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートのタスクを「先行 → 後続」で連結し、後続の開始を先行の完了まで押し出して、棒線型の矢印で表示する。

**Architecture:** `Task.id`(8 桁の 16 進)と `Task.predecessors`(id のリスト)を保存する。実効の開始・完了は保存せず、`timeline.Schedule`(遅延評価・メモ化)が算出し、`planned_start` を読む箇所はこれに置き換える。矢印は、純粋関数 `links.py` が折れ線を求め、`gantt.py` がチャート全体に重ねる 1 つの SVG(`ui.html` 1 要素)で描く。連結は編集ダイアログの「先行タスク」欄だけで作る。

**Tech Stack:** Python 3.13、NiceGUI(`ui.html`・`ui.select`)、pytest(`nicegui.testing.User`)、`uv`、`ty`。

**Spec:** `docs/superpowers/specs/2026-10-07-task-links-design.md`

## Global Constraints

- 連動は押し出しのみ: 後続の実効の開始 = `max(自分の開始予定, 先行の完了)`。保存しない。締切は動かさない。
- 連結は FS のみ・先行は複数・ラグなし。作り方は編集ダイアログの「先行タスク」欄だけ(ドラッグ連結・矢印クリックでの解除はやらない)。
- `Task.id` は `secrets.token_hex(4)`(8 桁の 16 進)。読込で、不正な `id`・`predecessors`・存在しない参照・自分自身・循環・重複は読込を拒否する。古いファイル(`id` なし)は読込時に id を振る。
- `timeline.effective_end(task, project, holidays)` の既存のシグネチャは変えない(キーワード引数 `schedule=None` の追加だけ)。
- 先行の完了: 状態が「終了」で実績の終了があればその時刻。それ以外は先行の実効の完了。求まらない先行は無視する。
- 手指定の完了予定と、工数なしの `planned_end` は、押し出された分(実効の開始 − `planned_start`)だけ同じ幅で後ろへずらす。`planned_start` が未入力のときはずらさない。
- 描画は NiceGUI の要素と CSS による自前描画。矢印は `ui.html` 1 要素の SVG(要素数を増やさない)。各経路に `data-link="先行ID-後続ID"` を付ける。
- コード規約(`.claude/RULE.md`): すべての関数に型ヒント(引数・戻り値)、`ty` で検証、コメントは多くても 3 行、PEP8。
- 担当者向けの書き出し(todoapp 形式)に独自のキーを足さない(`predecessors` を出さない。基準日だけ実効の開始)。
- 全体のテスト(約 1,271 件)・`uvx ty check src`・`uv run pytest -n auto` が通ること。テストは時間制限を付けずに実行する。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. 先行が複数あり、一部の完了予定が求まらない(先行の日付が空)とき、求まる先行だけで押し出す(`Task 2` のテスト)。
2. `planned_start` が空のタスクに先行があるとき、先行の完了を開始として棒を出す。手指定の完了予定はずらさない(`Task 2`)。
3. 行のコピー(`copy_task`)は `replace` で `id` まで複製するので、新しい `id` を振らないと、同じ `id` が 2 つになる(`Task 1` のテスト)。
4. 手で編集したファイルの `predecessors` に、存在しない id・自分自身・循環・重複する `id` があっても、開けない通知になり、アプリは落ちない(`Task 1`)。`Schedule` は、万一の循環でも無限再帰しない(`Task 2`)。
5. 押し出されているタスクのバーを横ドラッグしたとき、バーが戻って見える位置と、先行の完了より前へは動かさない制限(`Task 5`)。絞り込み・折りたたみで行が隠れたときに矢印だけが残らない(`Task 7`)。

---

## File Structure

| ファイル | 責務 |
|---|---|
| `src/projectapp/models.py`(変更) | `new_id()`、`Task.id`、`Task.predecessors` |
| `src/projectapp/linkgraph.py`(新規) | 連結のグラフ操作の純粋関数: `downstream_ids`、`validate_links`、`drop_task_links`、`link_options` |
| `src/projectapp/storage.py`(変更) | `id`・`predecessors` の読込と検証 |
| `src/projectapp/arrange.py`(変更) | コピーで新しい `id`、押し出されたタスクのずらし |
| `src/projectapp/timeline.py`(変更) | `Schedule`、`effective_start`、`effective_end`(`schedule` 引数) |
| `src/projectapp/forms.py`(変更) | `build_task` の `predecessors` 検証、`push_hint` |
| `src/projectapp/task_dialog.py`(変更) | 「先行タスク」欄とヒント |
| `src/projectapp/views.py`(変更) | 削除時の整合、ダイアログへの引数、ドラッグ |
| `src/projectapp/links.py`(新規) | 行の並び `RowSlot`、縦位置、折れ線(純粋関数) |
| `src/projectapp/gantt.py`(変更) | `Schedule` の利用、矢印の SVG、折りたたみでの更新 |
| `src/projectapp/dashboard.py`・`handoff.py`(変更) | 実効の開始へ置き換え |
| `docs/development.md`・`CLAUDE.md`(変更) | 文書の更新 |

テストは、新規ファイル(`test/test_linkgraph.py`、`test/test_schedule.py`、`test/test_links.py`)と、既存の `test_storage.py`・`test_arrange.py`・`test_forms.py`・`test_task_dialog.py`・`test_gantt.py`・`test_views.py`・`test_dashboard.py`・`test_handoff.py` へ足す。

---

### Task 1: データ(`id`・`predecessors`・保存と検証・コピー・削除)

**Files:**
- Modify: `src/projectapp/models.py`
- Create: `src/projectapp/linkgraph.py`
- Modify: `src/projectapp/storage.py:130-160`(`_task`)と `load_project`
- Modify: `src/projectapp/arrange.py:46-50`(`copy_task`)
- Modify: `src/projectapp/views.py:527-530`(`delete_task`)
- Test: `test/test_linkgraph.py`(新規)、`test/test_storage.py`、`test/test_arrange.py`、`test/test_views.py`

**Interfaces:**
- Produces:
  - `models.new_id() -> str`、`Task.id: str`(`compare=False`)、`Task.predecessors: list[str]`
  - `linkgraph.downstream_ids(project: Project, task_id: str) -> set[str]`(そのタスクを、直接・間接に先行にしているタスクの id)
  - `linkgraph.validate_links(tasks: list[Task]) -> None`(不正なら `ValueError`)
  - `linkgraph.drop_task_links(project: Project, task_id: str) -> None`
  - `linkgraph.link_options(project: Project, task: Task | None) -> dict[str, str]`(id → 「セクション名 / タスク名」。自分と、自分を先行にしているタスクを除く)

`Task.id` を `compare=False` にするのは、既存の約 1,271 件のテストの、`Task(...) == Task(...)` や `replace` の比較を壊さないため(`id` は乱数で、毎回違う)。`id` を確かめるテストは、明示的に比較する。

- [ ] **Step 1: `models.py` に `new_id` と `Task.id` を足す**

`import re` の下に `import secrets` を足し、`HEX_COLOR` の定義の後ろに追加する:

```python
def new_id() -> str:
    """タスクの id。8 桁の 16 進(プロジェクト内で重複しないことは、保存と読込が確かめる)。"""
    return secrets.token_hex(4)
```

`Task` の先頭の項目(`name`)の直後に追加する(デフォルト値のある項目なので、`name` の後ろ、`planned_start` の前でよい。`Task("x", datetime...)` のように位置引数で第 2 引数を渡すコードはない。`ty` で確かめる):

```python
    id: str = field(default_factory=new_id, compare=False)  # 連結の参照用。ファイルに保存する
```

位置引数の第 2 引数以降を使っている呼び出しがないか、`grep -rn "Task(\"[^\"]*\", " src test | grep -v "="` で確かめ、ある場合は `id` を末尾のフィールド(`project_code` の後ろ)へ移す。

- [ ] **Step 2: `test/test_linkgraph.py` を書く(失敗させる)**

```python
import pytest

from projectapp.linkgraph import downstream_ids, drop_task_links, link_options, validate_links
from projectapp.models import Project, Section, Task


def task(name: str, task_id: str, *predecessors: str) -> Task:
    return Task(name, id=task_id, predecessors=list(predecessors))


def test_downstream_ids_follow_direct_and_indirect_successors() -> None:
    a, b, c, d = task("a", "a"), task("b", "b", "a"), task("c", "c", "b"), task("d", "d")
    project = Project("p", tasks=[a, b, c, d])
    assert downstream_ids(project, "a") == {"b", "c"}
    assert downstream_ids(project, "c") == set()


def test_downstream_ids_terminate_on_a_cycle() -> None:
    a, b = task("a", "a", "b"), task("b", "b", "a")
    assert downstream_ids(Project("p", tasks=[a, b]), "a") == {"b", "a"}


def test_drop_task_links_removes_the_id_from_every_task() -> None:
    a, b = task("a", "a"), task("b", "b", "a", "x")
    project = Project("p", tasks=[a], sections=[Section("s", [b])])
    drop_task_links(project, "a")
    assert b.predecessors == ["x"]


def test_validate_links_accepts_a_valid_graph() -> None:
    validate_links([task("a", "a"), task("b", "b", "a")])


@pytest.mark.parametrize(
    "tasks",
    [
        [task("a", "a"), task("b", "a")],  # id の重複
        [task("a", "a", "zz")],  # 存在しない id
        [task("a", "a", "a")],  # 自分自身
        [task("a", "a", "b"), task("b", "b", "a")],  # 循環
        [task("a", "a"), task("b", "b", "a", "a")],  # 同じ先行の重複
    ],
)
def test_validate_links_rejects_bad_graphs(tasks: list[Task]) -> None:
    with pytest.raises(ValueError):
        validate_links(tasks)


def test_link_options_label_with_section_and_exclude_self_and_successors() -> None:
    a = task("設計", "a")
    b = task("実装", "b", "a")
    c = task("設計", "c")
    project = Project("p", tasks=[a], sections=[Section("開発", [b, c])])
    options = link_options(project, a)
    assert "a" not in options and "b" not in options  # 自分と、自分を先行にしている後続は除く
    assert options == {"c": "開発 / 設計"}
    everything = link_options(project, None)
    assert everything == {"a": "設計", "b": "開発 / 実装", "c": "開発 / 設計"}


def test_link_options_number_duplicate_labels() -> None:
    a, b = task("設計", "a"), task("設計", "b")
    options = link_options(Project("p", tasks=[a, b]), None)
    assert options == {"a": "設計", "b": "設計 (2)"}
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_linkgraph.py -q`
Expected: FAIL(`projectapp.linkgraph` がない)

- [ ] **Step 4: `src/projectapp/linkgraph.py` を書く**

```python
"""タスクの連結(先行 → 後続)のグラフ操作。NiceGUI には依存しない純粋関数。"""

from projectapp.models import Project, Task


def downstream_ids(project: Project, task_id: str) -> set[str]:
    """そのタスクを、直接・間接に先行にしているタスクの id。循環があっても止まる。"""
    tasks = project.all_tasks()
    found: set[str] = set()
    frontier = [task_id]
    while frontier:
        current = frontier.pop()
        for task in tasks:
            if current in task.predecessors and task.id not in found:
                found.add(task.id)
                frontier.append(task.id)
    return found


def validate_links(tasks: list[Task]) -> None:
    """id の重複、不正な先行(存在しない・自分自身・重複)、循環があれば ValueError。"""
    ids = [task.id for task in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("タスクの id が重複しています")
    known = set(ids)
    for task in tasks:
        if len(set(task.predecessors)) != len(task.predecessors):
            raise ValueError(f"先行タスクが重複しています: {task.name}")
        for pid in task.predecessors:
            if pid == task.id:
                raise ValueError(f"タスクが自分自身を先行にしています: {task.name}")
            if pid not in known:
                raise ValueError(f"存在しない先行タスクを指しています: {task.name}")
    _reject_cycle(tasks)


def _reject_cycle(tasks: list[Task]) -> None:
    by_id = {task.id: task for task in tasks}
    state: dict[str, int] = {}  # 1 = 探索中、2 = 済み

    def visit(task_id: str) -> None:
        if state.get(task_id) == 2:
            return
        if state.get(task_id) == 1:
            raise ValueError("先行タスクが循環しています")
        state[task_id] = 1
        for pid in by_id[task_id].predecessors:
            visit(pid)
        state[task_id] = 2

    for task_id in by_id:
        visit(task_id)


def drop_task_links(project: Project, task_id: str) -> None:
    """全タスクの先行から、その id を取り除く(タスクの削除のとき)。"""
    for task in project.all_tasks():
        if task_id in task.predecessors:
            task.predecessors = [pid for pid in task.predecessors if pid != task_id]


def link_options(project: Project, task: Task | None) -> dict[str, str]:
    """先行にできるタスクの候補(id → 「セクション名 / タスク名」)。

    自分と、自分を(直接・間接に)先行にしているタスクは除く(循環を防ぐ)。
    同じ表示が複数あるときは、2 件目以降に「 (2)」などを添える。
    """
    excluded: set[str] = set()
    if task is not None:
        excluded = {task.id, *downstream_ids(project, task.id)}
    labelled: list[tuple[str, str]] = [(t.id, t.name) for t in project.tasks]
    for section in project.sections:
        labelled += [(t.id, f"{section.name} / {t.name}") for t in section.tasks]
    seen: dict[str, int] = {}
    options: dict[str, str] = {}
    for task_id, label in labelled:
        seen[label] = seen.get(label, 0) + 1
        if task_id not in excluded:
            options[task_id] = label if seen[label] == 1 else f"{label} ({seen[label]})"
    return options
```

(同名の番号は、除外されるタスクも数える。除外の有無で番号が変わらないようにするため。)

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_linkgraph.py -q`
Expected: PASS

- [ ] **Step 6: `storage.py` のテストを足す(失敗させる)**

`test/test_storage.py` の末尾に追加する(import は既存の `json`・`Path`・`pytest`・`Project`・`Section`・`Task`・`load_project`・`save_project` を使う):

```python
def write_raw(tmp_path: Path, tasks: list[dict[str, object]]) -> Path:
    base = {
        "name": "t",
        "effort_hours": 0.0,
        "priority": "中",
        "status": "未着手",
        "color": "#4c8bf5",
        "predecessors": [],
    }
    data = {
        "base_date": "2026-10-05",
        "daily_hours": 6.5,
        "members": [],
        "sections": [{"name": "s", "tasks": [{**base, **raw} for raw in tasks]}],
    }
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_ids_and_predecessors_roundtrip(tmp_path: Path) -> None:
    a = Task("a", id="aaaaaaaa")
    b = Task("b", id="bbbbbbbb", predecessors=["aaaaaaaa"])
    path = save_project(Project("links", sections=[Section("s", [a, b])]), tmp_path)
    loaded = load_project(path).sections[0].tasks
    assert [(t.id, t.predecessors) for t in loaded] == [
        ("aaaaaaaa", []),
        ("bbbbbbbb", ["aaaaaaaa"]),
    ]


def test_a_file_without_ids_gets_unique_ids_and_empty_predecessors(tmp_path: Path) -> None:
    path = write_raw(tmp_path, [{"name": "a"}, {"name": "b"}])
    for raw in json.loads(path.read_text(encoding="utf-8"))["sections"][0]["tasks"]:
        assert "id" not in raw
    tasks = load_project(path).sections[0].tasks
    assert len({t.id for t in tasks}) == 2
    assert all(len(t.id) == 8 for t in tasks)
    path_no_key = write_raw(tmp_path, [{"name": "a"}])
    data = json.loads(path_no_key.read_text(encoding="utf-8"))
    del data["sections"][0]["tasks"][0]["predecessors"]
    path_no_key.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path_no_key).sections[0].tasks[0].predecessors == []


@pytest.mark.parametrize(
    "tasks",
    [
        [{"name": "a", "id": ""}],
        [{"name": "a", "id": 5}],
        [{"name": "a", "id": "x"}, {"name": "b", "id": "x"}],
        [{"name": "a", "id": "x", "predecessors": "x"}],
        [{"name": "a", "id": "x", "predecessors": [1]}],
        [{"name": "a", "id": "x", "predecessors": ["zz"]}],
        [{"name": "a", "id": "x", "predecessors": ["x"]}],
        [
            {"name": "a", "id": "x", "predecessors": ["y"]},
            {"name": "b", "id": "y", "predecessors": ["x"]},
        ],
    ],
)
def test_bad_ids_and_predecessors_are_rejected(
    tmp_path: Path, tasks: list[dict[str, object]]
) -> None:
    with pytest.raises(ValueError):
        load_project(write_raw(tmp_path, tasks))
```

- [ ] **Step 7: 失敗を確かめる**

Run: `uv run pytest test/test_storage.py -q`
Expected: 追加した 3 つが FAIL

- [ ] **Step 8: `storage.py` を直す**

import に `from projectapp.linkgraph import validate_links` と、`from projectapp.models import` の一覧に `new_id` を足す。`_task` の `predecessors=list(raw["predecessors"]),` を次に置き換え、`Task(` の `name=raw["name"],` の次の行に `id=_task_id(raw.get("id")),` を足す:

```python
        name=raw["name"],
        id=_task_id(raw.get("id")),
        # (planned_start から color までは、変更なし)
        assignee=_assignee(raw.get("assignee")),
        predecessors=_predecessors(raw.get("predecessors")),
```

`_assignee` の前に追加する:

```python
def _task_id(value: Any) -> str:
    """タスクの id。キーがない・null は新しく振る(古いファイル)。空・文字列以外は ValueError。"""
    if value is None:
        return new_id()
    if not isinstance(value, str) or not value:
        raise ValueError(f"タスクの id が正しくありません: {value!r}")
    return value


def _predecessors(value: Any) -> list[str]:
    """先行タスクの id のリスト。キーがない・null は空。リストでない・文字列以外は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(pid, str) for pid in value):
        raise ValueError("先行タスクが文字列のリストではありません")
    return list(value)
```

`load_project` の、`known = {m.name ...}` の直前に追加する:

```python
    validate_links(project.all_tasks())
```

- [ ] **Step 9: 通ることを確かめる**

Run: `uv run pytest test/test_storage.py test/test_linkgraph.py -q`
Expected: PASS

- [ ] **Step 10: コピーと削除のテストを足す(失敗させる)**

`test/test_arrange.py` の末尾に追加する(`arrange`・`Project`・`Section`・`Task` は import 済み):

```python
def test_copy_task_gets_a_new_id_and_no_predecessors() -> None:
    original = Task("a0", id="aaaaaaaa", predecessors=["zzzzzzzz"])
    project = Project("p", sections=[Section("A", [original])])
    copy = arrange.copy_task(project, (0, 0), (0, 1))
    assert copy.id != "aaaaaaaa" and len(copy.id) == 8
    assert copy.predecessors == []
    assert original.predecessors == ["zzzzzzzz"]
```

`test/test_views.py` の `test_delete_task_removes_only_that_task_and_makes_the_view_dirty` の直後に追加する(`save_cache`・`save_project`・`mount_capturing`・`wait_until`・`choose_in_combo` は、上のテストと同じ使い方をする。上のテストの 655〜660 行を写す):

```python
async def test_delete_task_removes_its_id_from_the_successors(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    a = Task("a", id="aaaaaaaa")
    b = Task("b", id="bbbbbbbb", predecessors=["aaaaaaaa"])
    save_project(Project("既存", tasks=[a, b]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.delete_task(None, 0)
    assert view.project.tasks[0].predecessors == []
```

- [ ] **Step 11: 失敗を確かめて、直す**

Run: `uv run pytest test/test_arrange.py test/test_views.py -q -k "new_id or successors"`
Expected: FAIL

`arrange.py` の import に `from projectapp.models import MAX_YEAR, MIN_YEAR, Project, Task, new_id` とし、`copy_task` を直す:

```python
    copy = replace(
        original, name=f"{original.name}{COPY_SUFFIX}", id=new_id(), predecessors=[], actuals=[]
    )
```

`views.py` の import に `from projectapp.linkgraph import drop_task_links` を足し、`delete_task` を直す:

```python
        removed = self.tasks_in(section_index).pop(task_index)
        drop_task_links(self.project, removed.id)
        self.gantt.set_project(self.project)
```

- [ ] **Step 12: 全体を確かめて、コミット**

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS、ty はエラーなし

```bash
git add src/projectapp/models.py src/projectapp/linkgraph.py src/projectapp/storage.py src/projectapp/arrange.py src/projectapp/views.py test/
git commit -m "feat: タスクの id と先行(predecessors)の保存・検証・コピー・削除

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 日程の計算(`Schedule`・`effective_start`)

**Files:**
- Modify: `src/projectapp/timeline.py`(`visible_range`、`counted_span`、`overallocations`、`clip_overloads`、`effective_end`、`is_overdue`、`progress_state`)
- Test: `test/test_schedule.py`(新規)

**Interfaces:**
- Consumes: `Task.id`、`Task.predecessors`(Task 1)
- Produces:
  - `class Schedule(project: Project, holidays: dict[date, str])`: `start(task) -> datetime | None`、`end(task) -> datetime | None`、`finish(pred) -> datetime | None`(先行としての完了)、`latest_finish(task) -> datetime | None`(先行の完了の最大。なければ None)
  - `effective_start(task, project, holidays, schedule: Schedule | None = None) -> datetime | None`
  - `effective_end(task, project, holidays, schedule: Schedule | None = None) -> datetime | None`
  - `counted_span`・`overallocations`・`clip_overloads`・`is_overdue`・`progress_state` に、キーワード引数 `schedule: Schedule | None = None`

先行がないタスクは、`Schedule` を作らずに従来の計算をする(速度と、既存のテストの動作を保つ)。

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_schedule.py`:

```python
from datetime import date, datetime

import pytest

from projectapp.models import Actual, Project, Status, Task
from projectapp.timeline import (
    Schedule,
    counted_span,
    effective_end,
    effective_start,
    is_overdue,
    overallocations,
    visible_range,
)

HOLIDAYS: dict[date, str] = {}
MON = datetime(2026, 10, 5, 9, 0)  # 月曜 9:00


def task(name: str, *predecessors: str, **fields: object) -> Task:
    return Task(name, id=name, predecessors=list(predecessors), **fields)  # type: ignore[arg-type]


def project(*tasks: Task) -> Project:
    return Project("p", tasks=list(tasks), daily_hours=6.5)


def start_of(proj: Project, name: str) -> datetime | None:
    found = next(t for t in proj.all_tasks() if t.name == name)
    return effective_start(found, proj, HOLIDAYS)


def end_of(proj: Project, name: str) -> datetime | None:
    found = next(t for t in proj.all_tasks() if t.name == name)
    return effective_end(found, proj, HOLIDAYS)


def test_no_predecessors_keeps_the_planned_start() -> None:
    proj = project(task("a", planned_start=MON, effort_hours=6.5))
    assert start_of(proj, "a") == MON
    assert end_of(proj, "a") == datetime(2026, 10, 5, 15, 30)


def test_a_late_predecessor_pushes_the_start() -> None:
    a = task("a", planned_start=MON, effort_hours=13)  # 月 9:00 → 火 15:30
    b = task("b", "a", planned_start=MON, effort_hours=6.5)
    proj = project(a, b)
    assert start_of(proj, "b") == datetime(2026, 10, 6, 15, 30)
    assert end_of(proj, "b") == datetime(2026, 10, 7, 15, 30)  # 火 15:30 は枠の終わり → 水


def test_an_early_predecessor_does_not_pull_the_start_back() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_start=datetime(2026, 10, 8, 9, 0), effort_hours=1)
    assert start_of(project(a, b), "b") == datetime(2026, 10, 8, 9, 0)


def test_the_latest_of_several_predecessors_wins() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    c = task("c", planned_start=MON, effort_hours=13)
    b = task("b", "a", "c", planned_start=MON, effort_hours=1)
    assert start_of(project(a, c, b), "b") == datetime(2026, 10, 6, 15, 30)


def test_a_chain_is_resolved() -> None:
    a = task("a", planned_start=MON, effort_hours=6.5)  # 月 15:30 まで
    b = task("b", "a", planned_start=MON, effort_hours=6.5)  # 火 9:00 開始 → 火 15:30
    c = task("c", "b", planned_start=MON, effort_hours=1)
    proj = project(a, b, c)
    assert start_of(proj, "b") == datetime(2026, 10, 5, 15, 30)
    assert start_of(proj, "c") == end_of(proj, "b")


def test_no_planned_start_uses_the_predecessors_finish() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", effort_hours=1)
    proj = project(a, b)
    assert start_of(proj, "b") == datetime(2026, 10, 5, 10, 0)
    assert end_of(proj, "b") == datetime(2026, 10, 5, 11, 0)


def test_no_predecessor_finish_and_no_start_stays_empty() -> None:
    a = task("a")  # 開始予定も締切もなく、完了予定が求まらない
    b = task("b", "a")
    assert start_of(project(a, b), "b") is None


def test_a_predecessor_without_an_end_is_ignored() -> None:
    a = task("a")
    c = task("c", planned_start=MON, effort_hours=1)
    b = task("b", "a", "c", planned_start=MON, effort_hours=1)
    assert start_of(project(a, c, b), "b") == datetime(2026, 10, 5, 10, 0)


def test_a_finished_predecessor_uses_its_actual_end() -> None:
    a = task(
        "a",
        planned_start=MON,
        effort_hours=1,
        status=Status.DONE,
        actuals=[Actual(MON, datetime(2026, 10, 7, 12, 0))],
    )
    b = task("b", "a", planned_start=MON, effort_hours=1)
    assert start_of(project(a, b), "b") == datetime(2026, 10, 7, 12, 0)


def test_a_finished_predecessor_without_actuals_uses_the_planned_end() -> None:
    a = task("a", planned_start=MON, effort_hours=1, status=Status.DONE)
    b = task("b", "a", planned_start=MON, effort_hours=1)
    assert start_of(project(a, b), "b") == datetime(2026, 10, 5, 10, 0)


def test_a_manual_end_shifts_by_the_pushed_amount() -> None:
    a = task("a", planned_start=MON, effort_hours=13)  # 火 15:30 まで
    b = task(
        "b",
        "a",
        planned_start=MON,
        planned_end=datetime(2026, 10, 5, 18, 0),
        planned_end_manual=True,
        effort_hours=4,
    )
    shift = datetime(2026, 10, 6, 15, 30) - MON
    assert end_of(project(a, b), "b") == datetime(2026, 10, 5, 18, 0) + shift


def test_a_planned_end_without_effort_shifts_by_the_pushed_amount() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, planned_end=datetime(2026, 10, 5, 18, 0))
    shift = datetime(2026, 10, 6, 15, 30) - MON
    assert end_of(project(a, b), "b") == datetime(2026, 10, 5, 18, 0) + shift


def test_a_manual_end_without_a_planned_start_is_not_shifted() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_end=datetime(2026, 10, 9, 18, 0))
    assert end_of(project(a, b), "b") == datetime(2026, 10, 9, 18, 0)


def test_the_deadline_never_moves() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, effort_hours=1, deadline=datetime(2026, 10, 6, 12, 0))
    proj = project(a, b)
    found = proj.tasks[1]
    assert found.deadline == datetime(2026, 10, 6, 12, 0)
    assert is_overdue(found, proj, HOLIDAYS, datetime(2026, 10, 1))  # 押し出されて締切を過ぎる


def test_a_cycle_does_not_recurse_forever() -> None:
    a = task("a", "b", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_start=MON, effort_hours=1)
    proj = project(a, b)
    assert start_of(proj, "a") is not None
    assert start_of(proj, "b") is not None


def test_a_missing_predecessor_is_ignored() -> None:
    b = task("b", "zz", planned_start=MON, effort_hours=1)
    assert start_of(project(b), "b") == MON


def test_a_schedule_matches_the_single_task_calls() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, effort_hours=2)
    c = task("c", "b", planned_start=MON, effort_hours=2)
    proj = project(a, b, c)
    schedule = Schedule(proj, HOLIDAYS)
    for t in proj.all_tasks():
        assert schedule.start(t) == effective_start(t, proj, HOLIDAYS)
        assert schedule.end(t) == effective_end(t, proj, HOLIDAYS)
        assert effective_end(t, proj, HOLIDAYS, schedule) == schedule.end(t)


def test_latest_finish_is_none_without_predecessors() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_start=MON, effort_hours=1)
    schedule = Schedule(project(a, b), HOLIDAYS)
    assert schedule.latest_finish(a) is None
    assert schedule.latest_finish(b) == datetime(2026, 10, 5, 10, 0)


def test_counted_span_and_overallocations_use_the_pushed_start() -> None:
    from projectapp.models import Member

    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, effort_hours=2, assignee="x")
    c = task("c", planned_start=datetime(2026, 10, 6, 15, 30), effort_hours=2, assignee="x")
    proj = Project("p", tasks=[a, b, c], members=[Member("x")])
    span = counted_span(b, proj, HOLIDAYS)
    assert span is not None and span[0] == datetime(2026, 10, 6, 15, 30)
    assert overallocations(proj, HOLIDAYS)  # b と c が、押し出された b の期間で重なる


def test_visible_range_includes_the_pushed_end() -> None:
    a = task("a", planned_start=MON, effort_hours=65)  # 10 稼働日
    b = task("b", "a", planned_start=MON, effort_hours=1)
    _, end = visible_range(project(a, b), HOLIDAYS)
    assert end >= date(2026, 10, 20)
```

(`test_a_late_predecessor_pushes_the_start` の期待値は、`calc_end` の規則から算出する。 月 9:00 から 13h は、月 6.5h(15:30)+火 6.5h(15:30)で火 15:30。b は火 15:30 開始: 火は 15:30 が枠の終わりなので、次の稼働日 水 9:00 から 6.5h で水 15:30。実装後に実行して差があれば、`calc_end` の既存テストで規則を確かめたうえで、期待値を直す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_schedule.py -q`
Expected: FAIL(`Schedule`・`effective_start` がない)

- [ ] **Step 3: `Schedule` を実装する**

`timeline.py` で、既存の `effective_end` を次の構成に置き換える。`actual_end` は後ろで定義されているが、呼び出しは実行時なので順序は問題ない。

```python
def _own_end(
    task: Task, project: Project, holidays: dict[date, str], start: datetime | None
) -> datetime | None:
    """開始を `start` としたときの完了予定。手指定・工数なしの planned_end は、押し出された分ずらす。"""
    if task.planned_end is not None and (task.effort_hours <= 0 or task.planned_end_manual):
        if task.planned_start is None or start is None or start <= task.planned_start:
            return task.planned_end
        try:
            return task.planned_end + (start - task.planned_start)
        except OverflowError:
            return task.planned_end
    return computed_end(
        start,
        task.effort_hours,
        project.daily_hours,
        project.work_start,
        holidays,
        task.deadline,
        conversion_rate(task, project),
    )


class Schedule:
    """タスクの id から、実効の開始・完了への対応。必要なものだけ算出して使い回す(保存しない)。"""

    def __init__(self, project: Project, holidays: dict[date, str]) -> None:
        self.project = project
        self.holidays = holidays
        self._tasks = {task.id: task for task in project.all_tasks()}
        self._done: dict[str, tuple[datetime | None, datetime | None]] = {}
        self._active: set[str] = set()

    def start(self, task: Task) -> datetime | None:
        return self._resolve(task)[0]

    def end(self, task: Task) -> datetime | None:
        return self._resolve(task)[1]

    def latest_finish(self, task: Task) -> datetime | None:
        """先行の完了の最大。先行がない、または完了が求まる先行がなければ None。"""
        finishes = [
            finish
            for pid in task.predecessors
            if pid != task.id and (pred := self._tasks.get(pid)) is not None
            if (finish := self.finish(pred)) is not None
        ]
        return max(finishes, default=None)

    def finish(self, pred: Task) -> datetime | None:
        """先行としての完了。終了済みで実績の終了があればその時刻、なければ実効の完了。"""
        if pred.status is Status.DONE:
            actual = actual_end(pred)
            if actual is not None:
                return actual
        return self._resolve(pred)[1]

    def _resolve(self, task: Task) -> tuple[datetime | None, datetime | None]:
        if task.id in self._done:
            return self._done[task.id]
        if task.id in self._active:  # 循環(手編集のファイルなど)。押し出しなしで扱う
            return task.planned_start, _own_end(task, self.project, self.holidays, task.planned_start)
        self._active.add(task.id)
        try:
            floor = self.latest_finish(task)
        finally:
            self._active.discard(task.id)
        start = task.planned_start
        if floor is not None and (start is None or floor > start):
            start = floor
        result = (start, _own_end(task, self.project, self.holidays, start))
        self._done[task.id] = result
        return result
```

(`latest_finish` の中で `_resolve` が呼ばれるので、`_active` を `latest_finish` の呼び出しの間だけ持つ。`_resolve` の中で `task.id` を `_active` に入れてから `latest_finish` を呼ぶ構成になっていること。循環の検出は、先行を辿って自分に戻ったとき。)

`effective_start` と `effective_end` を置き換える:

```python
def effective_start(
    task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None
) -> datetime | None:
    """実効の開始。先行がなければ開始予定。あれば、開始予定と先行の完了の遅いほう。"""
    if schedule is None and not task.predecessors:
        return task.planned_start
    return (schedule or Schedule(project, holidays)).start(task)


def effective_end(
    task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None
) -> datetime | None:
    """完了予定。工数が無い、または手で指定のときは planned_end、それ以外は算出する。先行の押し出しを含む。"""
    if schedule is None and not task.predecessors:
        return _own_end(task, project, holidays, task.planned_start)
    return (schedule or Schedule(project, holidays)).end(task)
```

- [ ] **Step 4: 他の関数に `schedule` を通す**

`visible_range`: 先頭で `schedule = Schedule(project, holidays)`、ループ内を次に直す:

```python
        task_start, task_end = schedule.start(task), schedule.end(task)
        if task_start is None or task_end is None:
            continue
        first, last = sorted((task_start.date(), task_end.date()))
```

`counted_span` は、シグネチャを `(task, project, holidays, schedule: Schedule | None = None)` にし、本体を次に直す:

```python
    if not task.assignee or task.status is Status.DONE:
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    if all(m.name != task.assignee for m in project.members):
        return None
    end = effective_end(task, project, holidays, schedule)
    if end is None or end <= start:
        return None
    return start, end
```

`overallocations` は先頭で `schedule = Schedule(project, holidays)` を作り、`counted_span(task, project, holidays, schedule)` を呼ぶ。`clip_overloads` は引数に `schedule: Schedule | None = None` を足し、`counted_span(task, project, holidays, schedule)` へ渡す。`is_overdue` と `progress_state` も `schedule: Schedule | None = None` を足し、中の `effective_end(task, project, holidays)` を `effective_end(task, project, holidays, schedule)` にする。`progress_state` の `task.planned_start is None` と `expected_progress(task.planned_start, end, now)` は、`start = effective_start(task, project, holidays, schedule)` を使う:

```python
    percent = current_progress(task)
    start = effective_start(task, project, holidays, schedule)
    end = effective_end(task, project, holidays, schedule)
    if percent is None or start is None or end is None:
        return None
    expected = expected_progress(start, end, now)
```

`progress_state` の中の `is_overdue(task, project, holidays, now)` にも `schedule=schedule` を渡す。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_schedule.py -q`
Expected: PASS(期待値の差は、Step 1 の注記のとおり直す)

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS(既存の呼び出しは `schedule` を渡さないので、動作は変わらない)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/timeline.py test/test_schedule.py
git commit -m "feat: 先行の完了で後続の開始を押し出す日程の計算(Schedule)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `planned_start` を読む箇所の置き換え(`gantt.py`・`dashboard.py`・`handoff.py`)

**Files:**
- Modify: `src/projectapp/gantt.py:576-585`(`render`)、`768-769`、`840`、`889-890`、`task_row` の `is_overdue`/`progress_state`、`overload_stripes`
- Modify: `src/projectapp/dashboard.py:48`、`180`、ほか `effective_end(`・`is_overdue(`・`progress_state(` の呼び出し
- Modify: `src/projectapp/handoff.py:51`(`_schedule`)
- Test: `test/test_gantt.py`、`test/test_dashboard.py`、`test/test_handoff.py`

**Interfaces:**
- Consumes: `Schedule`、`effective_start`、`effective_end(..., schedule=)`(Task 2)
- Produces: `GanttChart.schedule: Schedule`(`render` のたびに作る。Task 7 が使う)

- [ ] **Step 1: 取りこぼしを洗い出す**

Run: `grep -rn "planned_start\|\.planned_end" src/projectapp | grep -v "^src/projectapp/\(models\|storage\|forms\|task_dialog\).py"`

次の表と突き合わせる(`timeline.py`・`arrange.py` は Task 2・Task 5 で扱う)。表にない読み取りが出たら、同じ方針(表示・判定は実効の開始、入力・保存は自分の開始予定)で扱う。

| 場所 | 扱い |
|---|---|
| `gantt.py` `task_row`(`bar_span`・`bar_visible`) | 実効の開始 |
| `gantt.py` `clipped_fill_percent` | 実効の開始 |
| `gantt.py` `progress_marker`(`expected_progress`) | 実効の開始 |
| `gantt.py` `overload_stripes` | `clip_overloads` に `schedule` を渡す |
| `views.py` `shift_task`(`if task.planned_start is not None` の通知の判定) | そのまま(「バーがあるか」の判定。開始予定が空ならずらせない) |
| `dashboard.py` 48・180 行付近 | 実効の開始 |
| `handoff.py` `_schedule` | 実効の開始 |

- [ ] **Step 2: ガントのテストを書く(失敗させる)**

`test/test_gantt.py` の末尾へ追加する(`mount`・`BASE`・`Project`・`Section`・`Task`・`datetime`・`from_name`・`COLUMN_WIDTH_PX` は import 済み。バーのスタイルの読み方は、既存の `test_bar_geometry_and_color` を写す):

```python
async def test_a_pushed_task_is_drawn_from_its_effective_start(user: User) -> None:
    a = Task("先行", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=13)
    b = Task(
        "後続",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=6.5,
        predecessors=["aaaaaaaa"],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [a, b])])
    mount(project)
    await user.open("/")
    bar = user.find(marker="bar-0-1").elements.pop()
    day = COLUMN_WIDTH_PX[Scale.DAY]
    # 火曜 15:30 = 基準日(月曜)から 1 日と 15.5/24 日
    expected_left = (1 + 15.5 / 24) * day
    assert from_name(expected_left) in bar.props["style"]
```

(`bar.props["style"]` は、既存テストが バーのスタイルを読む方法に合わせる。`test_bar_geometry_and_color` が別の読み方なら、それに揃える。)

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py -q -k pushed`
Expected: FAIL(バーが自分の開始予定の位置にある)

- [ ] **Step 4: `gantt.py` を直す**

import に `Schedule`、`effective_start` を足す。`GanttChart.__init__` の `self.overloads` の次に `self.schedule = Schedule(project, holidays)` を足す。`render` の先頭(`columns = ...` の前)に次を足し、`overallocations` を `self.overloads = overallocations(self.project, self.holidays)` のままにする(内部で `Schedule` を作る):

```python
        self.schedule = Schedule(self.project, self.holidays)
```

`task_row` の先頭の `is_overdue(...)`・`progress_state(...)` に `schedule=self.schedule` を渡す。`end = effective_end(...)` の行から `if span is not None and self.bar_visible(...)` までを置き換える:

```python
            start = self.schedule.start(task)
            end = self.schedule.end(task)
            span = bar_span(start, end, columns)
            if span is not None and self.bar_visible(start, end, columns):
```

`clipped_fill_percent` の `start = task.planned_start` を `start = self.schedule.start(task)` に。`progress_marker` の `if task.planned_start is not None and end is not None:` と `expected_progress(task.planned_start, end, self.now())` を次に:

```python
            start = self.schedule.start(task)
            if start is not None and end is not None:
                expected = expected_progress(start, end, self.now())
```

`overload_stripes` の `clip_overloads(task, self.project, self.holidays, self.overloads)` に `self.schedule` を第 5 引数(`schedule=self.schedule`)として足す。`effective_end`・`effective_start` の未使用の import は消す(`ty`・ruff で確かめる)。

- [ ] **Step 5: `dashboard.py`・`handoff.py` を直す**

`dashboard.py`: `from projectapp.timeline import ...` に `Schedule` を足す。`period_for` の `else` 側(全期間)の先頭で `schedule = Schedule(project, holidays)` を作り、ループ内を次に:

```python
        for moment in (
            schedule.start(task),
            task.deadline,
            schedule.end(task),
        ):
```

`summarize_workload` は先頭で `schedule = Schedule(project, holidays)` を作り、`start, end = task.planned_start, effective_end(task, project, holidays)` を `start, end = schedule.start(task), schedule.end(task)` にする。同じファイルの、残りの `effective_end(`・`is_overdue(`・`progress_state(` の呼び出しを `grep -n "effective_end(\|is_overdue(\|progress_state(" src/projectapp/dashboard.py` で洗い出し、各 `summarize_*` の先頭で `schedule = Schedule(project, holidays)` を 1 回作って、`schedule=schedule` を渡す(関数の先頭で作るので、1 回の集計で使い回せる)。`Schedule` を渡せない小さな補助関数は、引数に `schedule` を足す。

`handoff.py` の `_schedule`: 先頭の `start = task.planned_start` を `start = effective_start(task, project, holidays)` にし、import に `effective_start` を足す。

- [ ] **Step 6: ダッシュボードと書き出しのテストを足す**

`test/test_dashboard.py` の末尾へ追加する。既存のテストが `summarize_workload` を呼ぶ形(引数の並び: `project, period, now, holidays`)に合わせる:

```python
def test_workload_uses_the_pushed_start() -> None:
    from datetime import date, datetime
    from projectapp.dashboard import Period, summarize_workload
    from projectapp.models import Member, Project, Task

    a = Task("a", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5 * 5)
    b = Task(
        "b",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=6.5,
        assignee="x",
        predecessors=["aaaaaaaa"],
    )
    project = Project("p", tasks=[a, b], members=[Member("x")])
    first_week = Period(date(2026, 10, 5), date(2026, 10, 9))
    rows = summarize_workload(project, first_week, datetime(2026, 10, 1), {})
    # b は、a が終わる金曜の 15:30 以降に始まるので、この週に数える稼働日は 1 日以下
    assert next(r for r in rows if r.name == "x").planned <= 6.5
```

(`WorkloadRow` の項目名が `planned` でなければ、`dashboard.py` の定義に合わせる。)

`test/test_handoff.py` の末尾へ追加する(`build_todos` の戻り値の読み方は、既存のテストを写す):

```python
def test_the_anchor_date_is_the_pushed_start() -> None:
    from datetime import datetime
    from projectapp.handoff import _schedule
    from projectapp.models import Project, Task

    a = Task("a", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=13)
    b = Task(
        "b",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=1,
        predecessors=["aaaaaaaa"],
    )
    project = Project("p", tasks=[a, b])
    assert _schedule(b, project, {}) == ("one_time", "2026-10-06")
```

- [ ] **Step 7: 全体を確かめて、コミット**

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

```bash
git add src/projectapp/gantt.py src/projectapp/dashboard.py src/projectapp/handoff.py test/
git commit -m "feat: バー・集計・書き出しの基準を実効の開始へ置き換える

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 編集ダイアログの「先行タスク」欄

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task`、`push_hint` を追加)
- Modify: `src/projectapp/task_dialog.py:478-`(`open_task_dialog`)
- Modify: `src/projectapp/views.py`(`add_task`・`add_top_task`・`edit_task`)
- Test: `test/test_forms.py`、`test/test_task_dialog.py`

**Interfaces:**
- Consumes: `linkgraph.link_options`(Task 1)、`Schedule.latest_finish`(Task 2)
- Produces:
  - `forms.build_task(..., predecessors: list[str] | None = None, linkable_ids: frozenset[str] | None = None)`: `predecessors` が None なら既存の値を引き継ぐ(新規は空)。指定したら、重複を取り除き(順序は保つ)、`linkable_ids` が渡されていれば、その外の id、自分自身はエラー(`ValueError("先行タスクが正しくありません")`)
  - `forms.push_hint(start: datetime | None, finishes: list[datetime]) -> str`: 先行の完了が開始より後のとき `先行の完了により、実際の開始は 10/12 09:00 です`、それ以外は空文字
  - `open_task_dialog(..., link_options: dict[str, str] | None = None, finish_of: Callable[[str], datetime | None] | None = None)`

- [ ] **Step 1: `forms` のテストを書く(失敗させる)**

`test/test_forms.py` の末尾へ。既存の `build_task` の呼び出しの引数(必須のキーワード引数)は、ファイル内の他のテストが使うヘルパーに合わせる。ヘルパーがなければ次の `fields()` を使う:

```python
def link_fields(**extra: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        name="後続",
        planned_start="",
        planned_end="",
        deadline="",
        effort_hours=None,
        priority=Priority.MEDIUM,
        status=Status.NOT_STARTED,
        color="#4c8bf5",
        assignee="",
        allocation_percent=None,
    )
    return {**base, **extra}


def test_build_task_sets_and_dedupes_predecessors() -> None:
    task = build_task(
        None,
        **link_fields(predecessors=["a", "b", "a"], linkable_ids=frozenset({"a", "b"})),  # type: ignore[arg-type]
    )
    assert task.predecessors == ["a", "b"]


def test_build_task_keeps_existing_predecessors_when_not_given() -> None:
    existing = Task("x", id="xxxxxxxx", predecessors=["a"])
    task = build_task(existing, **link_fields())  # type: ignore[arg-type]
    assert task.predecessors == ["a"] and task.id == "xxxxxxxx"


@pytest.mark.parametrize("bad", [["zz"], ["xxxxxxxx"]])
def test_build_task_rejects_unlinkable_predecessors(bad: list[str]) -> None:
    existing = Task("x", id="xxxxxxxx")
    with pytest.raises(ValueError, match="先行タスク"):
        build_task(
            existing,
            **link_fields(predecessors=bad, linkable_ids=frozenset({"a"})),  # type: ignore[arg-type]
        )


def test_push_hint_only_when_the_start_is_pushed() -> None:
    start = datetime(2026, 10, 5, 9, 0)
    assert push_hint(start, []) == ""
    assert push_hint(start, [datetime(2026, 10, 5, 8, 0)]) == ""
    assert push_hint(start, [datetime(2026, 10, 12, 9, 0)]) == (
        "先行の完了により、実際の開始は 10/12 09:00 です"
    )
    assert push_hint(None, [datetime(2026, 10, 12, 9, 0)]).endswith("10/12 09:00 です")
```

import に `push_hint`、`pytest`、`datetime`、`Priority`、`Status`、`Task` を足す(なければ)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py -q -k "predecessors or push_hint"`
Expected: FAIL

- [ ] **Step 3: `forms.py` を直す**

`build_task` のシグネチャの `project_code: str = "",` の次に追加:

```python
    predecessors: list[str] | None = None,
    linkable_ids: frozenset[str] | None = None,
```

`return replace(` の直前に追加し、`replace` に `predecessors=links,` を足す:

```python
    links = list(base.predecessors) if predecessors is None else list(dict.fromkeys(predecessors))
    if predecessors is not None and (
        base.id in links or (linkable_ids is not None and not set(links) <= linkable_ids)
    ):
        raise ValueError("先行タスクが正しくありません")
```

`build_task` の前に追加する:

```python
def push_hint(start: datetime | None, finishes: list[datetime]) -> str:
    """先行の完了が開始より後のときの、1 行のヒント。押し出されていなければ空。"""
    if not finishes:
        return ""
    latest = max(finishes)
    if start is not None and latest <= start:
        return ""
    return f"先行の完了により、実際の開始は {latest:%m/%d %H:%M} です"
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_forms.py -q`
Expected: PASS

- [ ] **Step 5: ダイアログのテストを書く(失敗させる)**

`test/test_task_dialog.py` の `mount_dialog` に、`link_options`・`finish_of` を渡せる引数を足す:

```python
    link_options: dict[str, str] | None = None,
    finish_of: Callable[[str], datetime | None] | None = None,
```

`open_task_dialog(...)` の呼び出しに `link_options=link_options, finish_of=finish_of,` を足す(`from collections.abc import Callable` を import)。末尾にテストを追加:

```python
async def test_predecessors_are_saved_from_the_select(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, link_options={"aaaaaaaa": "設計", "bbbbbbbb": "開発 / 実装"})
    await open_dialog(user)
    user.find(marker="task-name").type("テスト")
    select = user.find(marker="task-predecessors").elements.pop()
    select.set_value(["aaaaaaaa"])
    user.find(marker="task-save").click()
    assert saved[0].predecessors == ["aaaaaaaa"]


async def test_the_select_lists_only_the_given_options(user: User) -> None:
    mount_dialog(None, [], link_options={"aaaaaaaa": "設計"})
    await open_dialog(user)
    select = user.find(marker="task-predecessors").elements.pop()
    assert select.options == {"aaaaaaaa": "設計"}


async def test_the_hint_shows_only_when_pushed(user: User) -> None:
    task = Task(
        "後続",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 5, 9, 0),
        predecessors=["aaaaaaaa"],
    )
    mount_dialog(
        task,
        [],
        link_options={"aaaaaaaa": "設計"},
        finish_of=lambda pid: datetime(2026, 10, 12, 9, 0),
    )
    await open_dialog(user)
    hint = user.find(marker="task-predecessors-hint").elements.pop()
    assert hint.visible
    assert hint.text == "先行の完了により、実際の開始は 10/12 09:00 です"


async def test_the_hint_is_hidden_without_a_push(user: User) -> None:
    task = Task("後続", planned_start=datetime(2026, 10, 12, 9, 0), predecessors=["aaaaaaaa"])
    mount_dialog(
        task,
        [],
        link_options={"aaaaaaaa": "設計"},
        finish_of=lambda pid: datetime(2026, 10, 5, 9, 0),
    )
    await open_dialog(user)
    assert not user.find(marker="task-predecessors-hint").elements  # 非表示は find で見つからない


async def test_changing_the_predecessors_counts_as_an_edit(user: User) -> None:
    task = Task("後続", id="bbbbbbbb")
    mount_dialog(task, [], link_options={"aaaaaaaa": "設計"})
    await open_dialog(user)
    user.find(marker="task-predecessors").elements.pop().set_value(["aaaaaaaa"])
    user.find(marker="task-cancel").click()
    user.should_see(marker="close-save")  # 確認ダイアログが出る
```

- [ ] **Step 6: 失敗を確かめて、`task_dialog.py` を直す**

Run: `uv run pytest test/test_task_dialog.py -q -k "predecessors or hint"`
Expected: FAIL

`open_task_dialog` のシグネチャに追加:

```python
    link_options: dict[str, str] | None = None,
    finish_of: Callable[[str], datetime | None] | None = None,
```

(`from datetime import date, datetime, time` になっていることを確かめる。)

`assignee`・`allocation` の行と `conversion` ラベルの後、`priority = PriorityChips(...)` の前に追加する。先行の欄は、候補が空でも出す(空のときは選べないだけ):

```python
        options = dict(link_options or {})
        kept = [pid for pid in initial.predecessors if pid in options]  # 候補にない参照は、欄に出さない
        predecessors = (
            ui.select(options, label="先行タスク", value=kept, multiple=True)
            .props("use-chips")
            .classes("w-full")
            .mark("task-predecessors")
        )
        push = ui.label("").classes("text-caption text-grey").mark("task-predecessors-hint")

        def refresh_push(_event: object = None) -> None:
            finishes = [
                finish
                for pid in predecessors.value or []
                if finish_of is not None and (finish := finish_of(pid)) is not None
            ]
            start_text = fields.start_text()
            try:
                start_at = parse_datetime(start_text)
            except ValueError:
                start_at = None
            text = push_hint(start_at, finishes)
            push.set_text(text)
            push.set_visibility(bool(text))

        predecessors.on_value_change(refresh_push)
        refresh_push()
```

import に `from projectapp.forms import ..., parse_datetime, push_hint` を足す(`task_dialog.py` の既存の forms の import に合わせる)。`current()` の `allocation.value,` の次に `tuple(predecessors.value or []),` を足す。`save()` の `build_task(` に追加:

```python
                    predecessors=list(predecessors.value or []),
                    linkable_ids=frozenset(options),
```

候補にない参照(`kept` から落ちたもの)が保存で消えるのを避けるため、`predecessors=` は、候補にあるものだけを書き換えるようにする。`save()` の直前に次を足し、上の `predecessors=` を `predecessors=merged_predecessors(),` にする:

```python
        def merged_predecessors() -> list[str]:
            """欄の値。候補にない既存の参照(通常はない)は、そのまま残す。"""
            hidden = [pid for pid in initial.predecessors if pid not in options]
            return [*(predecessors.value or []), *hidden]
```

`linkable_ids` には、隠れた参照も含める: `linkable_ids=frozenset(options) | frozenset(initial.predecessors)`。

- [ ] **Step 7: `views.py` から渡す**

import に `from projectapp.linkgraph import drop_task_links, link_options` と、`from projectapp.timeline import Schedule` を足す(既存の import に合わせる)。`MainView` に追加する:

```python
    def link_args(self, task: Task | None) -> dict[str, object]:
        """編集ダイアログの「先行タスク」欄に渡す引数。"""
        schedule = Schedule(self.project, self.holidays)
        by_id = {t.id: t for t in self.project.all_tasks()}

        def finish_of(task_id: str) -> datetime | None:
            pred = by_id.get(task_id)
            return None if pred is None else schedule.finish(pred)

        return {"link_options": link_options(self.project, task), "finish_of": finish_of}
```

`add_task`・`add_top_task`・`edit_task` の `open_task_dialog(...)` に `**self.link_args(None)`(編集は `**self.link_args(task)`)を足す。`datetime` を import する(未 import なら)。

- [ ] **Step 8: 全体を確かめて、コミット**

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py src/projectapp/views.py test/
git commit -m "feat: 編集ダイアログに先行タスクの欄とヒントを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: バーの横ドラッグへの反映

**Files:**
- Modify: `src/projectapp/arrange.py:53-77`(`shift_task`、`min_shift_days`)
- Modify: `src/projectapp/views.py:544-557`(`shift_task`)
- Modify: `src/projectapp/gantt.py`(`task_row` の `data-min-days`)
- Test: `test/test_arrange.py`、`test/test_views.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: `Schedule.start`、`Schedule.latest_finish`(Task 2、4)
- Produces:
  - `arrange.shift_task(task: Task, days: int, shown_start: datetime | None = None) -> bool`: 新しい開始予定 = `shown_start`(省略時は `planned_start`)+ `days` 日。完了予定は `planned_end + (押し出し分) + days` 日。
  - `arrange.min_shift_days(task: Task, base_date: date, shown_start: datetime | None = None, floor: datetime | None = None) -> int`: 基準日と先行の完了の日(`floor`)の遅いほうより前へは動かさない。

- [ ] **Step 1: `arrange` のテストを書く(失敗させる)**

`test/test_arrange.py` の末尾へ(`date`・`datetime` は import 済み):

```python
def test_shift_task_of_a_pushed_task_starts_from_the_shown_start() -> None:
    task = Task(
        "b",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 5, 18),
    )
    shown = datetime(2026, 10, 8, 9)  # 先行に 3 日押し出されている
    assert arrange.shift_task(task, 2, shown)
    assert task.planned_start == datetime(2026, 10, 10, 9)
    assert task.planned_end == datetime(2026, 10, 10, 18)  # 5 + 3(押し出し)+ 2


def test_shift_task_without_a_push_is_unchanged() -> None:
    task = Task("b", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 9))
    assert arrange.shift_task(task, 1)
    assert (task.planned_start, task.planned_end) == (
        datetime(2026, 10, 6, 9),
        datetime(2026, 10, 7, 9),
    )


def test_min_shift_days_stops_at_the_base_date_and_the_predecessors_finish() -> None:
    task = Task("b", planned_start=datetime(2026, 10, 12, 9))
    base = date(2026, 10, 5)
    assert arrange.min_shift_days(task, base) == -7
    floor = datetime(2026, 10, 8, 15, 30)  # 先行の完了
    assert arrange.min_shift_days(task, base, None, floor) == -4  # 12 → 8
    pushed_shown = datetime(2026, 10, 8, 15, 30)
    assert arrange.min_shift_days(task, base, pushed_shown, floor) == 0
    assert arrange.min_shift_days(task, date(2026, 10, 10), None, floor) == -2  # 基準日が遅いとき
```

- [ ] **Step 2: 失敗を確かめて、`arrange.py` を直す**

Run: `uv run pytest test/test_arrange.py -q -k "shown_start or min_shift"`
Expected: FAIL

```python
def shift_task(task: Task, days: int, shown_start: datetime | None = None) -> bool:
    """開始予定と、入っていれば完了予定を同じ日数ずらす(締切は動かさない)。範囲外なら何も書き換えない。

    押し出されているタスクは、見えている開始(shown_start)を基準にずらす。完了予定は押し出し分も含める。
    """
    if task.planned_start is None:
        return False
    shown = task.planned_start if shown_start is None else max(shown_start, task.planned_start)
    try:
        delta = timedelta(days=days)
        pushed = shown - task.planned_start
        start = shown + delta
        end = None if task.planned_end is None else task.planned_end + pushed + delta
    except OverflowError:
        return False
    for moment in (start, end):
        if moment is not None and not MIN_YEAR <= moment.year <= MAX_YEAR:
            return False
    task.planned_start, task.planned_end = start, end
    return True


def min_shift_days(
    task: Task,
    base_date: date,
    shown_start: datetime | None = None,
    floor: datetime | None = None,
) -> int:
    """左へずらせる限度(0 以下の日数)。見えている開始は、基準日と先行の完了の日より前へは動かさない。"""
    shown = task.planned_start if shown_start is None else shown_start
    if shown is None:
        return 0
    limit = base_date if floor is None else max(base_date, floor.date())
    start = shown.date()
    return (min(limit, start) - start).days
```

import に `datetime` を足す(`from datetime import date, datetime, timedelta`)。

- [ ] **Step 3: 通ることを確かめる**

Run: `uv run pytest test/test_arrange.py -q`
Expected: PASS

- [ ] **Step 4: `views.py` と `gantt.py` のテストを書く(失敗させる)**

`test/test_gantt.py`(バーの `data-min-days` を読む既存のテストを探して同じ読み方にする: `grep -n "data-min-days" test/test_gantt.py`):

```python
async def test_min_days_for_a_task_with_a_predecessor(user: User) -> None:
    a = Task("先行", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5 * 2)
    b = Task(
        "後続",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 12, 9),
        effort_hours=1,
        predecessors=["aaaaaaaa"],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [a, b])])
    mount(project)
    await user.open("/")
    bar = user.find(marker="bar-0-1").elements.pop()
    assert "data-min-days=-5" in str(bar.props) or bar.props.get("data-min-days") in ("-5", -5)
    # 先行の完了は火曜 15:30。後続の開始 10/12 から 10/6 までの -6 日ではなく、基準日 10/5 と
    # 先行の完了の日 10/6 の遅いほう(10/6)までの -6 日
```

(先行 13h は月 9:00 → 火 15:30。完了の日 10/6、後続の開始 10/12 なので、`min_shift_days` は `(10/6 − 10/12)` = **-6**。上のアサートは `-6` に直し、コメントも合わせること。`data-min-days` の読み方は、既存テストに揃える。)

`test/test_views.py` に、`shift_task` の動作を足す。`mount_capturing` で `MainView` を作り、ファイルから開く手順は `test_delete_task_removes_only_that_task...` と同じにする:

```python
async def test_shift_task_does_not_go_before_the_predecessors_finish(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    a = Task("a", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=13)
    b = Task(
        "b",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 12, 9),
        effort_hours=1,
        predecessors=["aaaaaaaa"],
    )
    save_project(Project("既存", base_date=date(2026, 10, 5), tasks=[a, b]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.shift_task(None, 1, -30)  # 大きく左へ
    assert view.project.tasks[1].planned_start == datetime(2026, 10, 6, 9)  # 先行の完了の日まで
```

- [ ] **Step 5: 失敗を確かめて、直す**

Run: `uv run pytest test/test_gantt.py test/test_views.py -q -k "min_days or predecessors_finish"`
Expected: FAIL

`views.py` の `shift_task` を直す(`Schedule` は Task 4 で import 済み):

```python
        task = self.tasks_in(section_index)[task_index]
        schedule = Schedule(self.project, self.holidays)
        shown = schedule.start(task)
        floor = schedule.latest_finish(task)
        least = arrange.min_shift_days(task, self.project.base_date, shown, floor)
        days = max(days, least)
        if days == 0:
            return
        if not arrange.shift_task(task, days, shown):
```

`gantt.py` の `task_row` の `least = arrange.min_shift_days(task, self.project.base_date)` を次に:

```python
                    least = arrange.min_shift_days(
                        task, self.project.base_date, start, self.schedule.latest_finish(task)
                    )
```

(`start` は Task 3 で作った、実効の開始。)

- [ ] **Step 6: 全体を確かめて、コミット**

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

```bash
git add src/projectapp/arrange.py src/projectapp/views.py src/projectapp/gantt.py test/
git commit -m "feat: 押し出されたタスクのドラッグを、実効の開始を基準にする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 矢印の計算(`links.py`・行の並び)

**Files:**
- Create: `src/projectapp/links.py`
- Test: `test/test_links.py`

**Interfaces:**
- Consumes: `filtering.TaskFilter`・`visible_task_indexes`・`matches`(既存)
- Produces:
  - `RowSlot`(frozen dataclass): `kind: Literal["task", "section", "top-add"]`、`si: int | None`、`ti: int | None`、`task_id: str | None`、`shown: bool`(折りたたみで隠れる行は False)、`height: int`
  - `row_slots(project, task_filter, collapsed, read_only, row_height, add_height) -> list[RowSlot]`
  - `row_centers(slots, top) -> dict[str, float]`(`shown` のタスクの、行の中央の縦位置。`top` は見出しの高さ)
  - `total_height(slots, top) -> float`
  - `Bar`(frozen dataclass): `left: float`、`right: float`(名前の欄の右端からの px)
  - `link_points(pred: Bar, pred_y: float, succ: Bar, succ_y: float, row_height: int) -> list[tuple[float, float]]`
  - `path_data(points) -> str`(SVG の `d`)

`row_slots` は、`gantt.render` が描く行の並びと同じ規則(セクションなしのタスク → 追加行(読み取り専用では出さない)→ 各セクション[見出し・タスク])で作る。絞り込み中は、一致するタスクだけ・一致がないセクションは見出しごと出さない。折りたたみ中(絞り込みなし)のタスクの行は、作るが `shown=False`。

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_links.py`:

```python
from projectapp.filtering import TaskFilter
from projectapp.links import (
    Bar,
    link_points,
    path_data,
    row_centers,
    row_slots,
    total_height,
)
from projectapp.models import Project, Section, Task

ROW, ADD = 32, 24


def project() -> Project:
    return Project(
        "p",
        tasks=[Task("t0", id="t0"), Task("t1", id="t1")],
        sections=[
            Section("A", [Task("a0", id="a0"), Task("a1", id="a1")]),
            Section("B", [Task("b0", id="b0")]),
        ],
    )


def slots(**kw: object):  # type: ignore[no-untyped-def]
    args: dict[str, object] = dict(
        task_filter=TaskFilter(), collapsed=set(), read_only=False, row_height=ROW, add_height=ADD
    )
    return row_slots(project(), **{**args, **kw})  # type: ignore[arg-type]


def test_slots_follow_the_render_order() -> None:
    kinds = [(s.kind, s.task_id) for s in slots()]
    assert kinds == [
        ("task", "t0"),
        ("task", "t1"),
        ("top-add", None),
        ("section", None),
        ("task", "a0"),
        ("task", "a1"),
        ("section", None),
        ("task", "b0"),
    ]


def test_read_only_has_no_add_row() -> None:
    assert all(s.kind != "top-add" for s in slots(read_only=True))


def test_centers_use_each_rows_height() -> None:
    centers = row_centers(slots(), top=100)
    assert centers["t0"] == 100 + ROW / 2
    assert centers["t1"] == 100 + ROW + ROW / 2
    assert centers["a0"] == 100 + 2 * ROW + ADD + ROW + ROW / 2  # 追加行と見出しを挟む
    assert total_height(slots(), top=100) == 100 + 2 * ROW + ADD + ROW + 2 * ROW + ROW + ROW


def test_a_collapsed_section_has_hidden_rows_that_take_no_space() -> None:
    result = slots(collapsed={0})
    assert [s.shown for s in result if s.task_id in ("a0", "a1")] == [False, False]
    centers = row_centers(result, top=0)
    assert "a0" not in centers and "a1" not in centers
    assert centers["b0"] == 2 * ROW + ADD + ROW + ROW + ROW / 2


def test_a_filter_keeps_only_matching_tasks_and_ignores_collapse() -> None:
    result = slots(task_filter=TaskFilter(query="a1"), collapsed={0})
    assert [(s.kind, s.task_id) for s in result] == [
        ("top-add", None),
        ("section", None),
        ("task", "a1"),
    ]
    assert all(s.shown for s in result)


def test_link_points_for_a_normal_arrow() -> None:
    pred = Bar(left=40, right=100)
    succ = Bar(left=160, right=200)
    assert link_points(pred, 16, succ, 48, ROW) == [(100, 16), (106, 16), (106, 48), (160, 48)]


def test_link_points_for_a_close_arrow_go_between_the_rows() -> None:
    pred = Bar(left=40, right=100)
    succ = Bar(left=105, right=200)  # 12px 未満
    assert link_points(pred, 16, succ, 48, ROW) == [
        (100, 16),
        (106, 16),
        (106, 32),
        (99, 32),
        (99, 48),
        (105, 48),
    ]


def test_link_points_for_an_upward_arrow_use_the_row_above() -> None:
    pred = Bar(left=40, right=100)
    succ = Bar(left=100, right=150)
    points = link_points(pred, 48, succ, 16, ROW)
    assert points[2] == (106, 32) and points[3] == (94, 32)  # 行の間(上側)を通る


def test_path_data_is_an_svg_move_and_lines() -> None:
    assert path_data([(1, 2), (3.5, 2), (3.5, 8)]) == "M1,2 L3.5,2 L3.5,8"
```

(近接の折れ線は、設計書の「4 区間」ではなく、実際は右 6px・縦・左へ・縦・右の 5 区間になる。点列で確かめる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_links.py -q`
Expected: FAIL(`projectapp.links` がない)

- [ ] **Step 3: `links.py` を書く**

```python
"""矢印の連結の計算(行の並び・縦位置・折れ線)。NiceGUI には依存しない純粋関数。"""

from dataclasses import dataclass
from typing import Literal

from projectapp.filtering import TaskFilter, matches, visible_task_indexes
from projectapp.models import Project

STUB_PX = 6  # 先行の棒の右端から出る長さ。後続の棒の左端へ入る手前も同じ長さ
MIN_GAP_PX = 2 * STUB_PX  # 後続の左端がこれ未満のときは、行の間を通る経路にする


@dataclass(frozen=True)
class RowSlot:
    """描く行 1 つ。折りたたみで隠れる行は、作るが shown=False(高さを持たない)。"""

    kind: Literal["task", "section", "top-add"]
    si: int | None
    ti: int | None
    task_id: str | None
    shown: bool
    height: int


def row_slots(
    project: Project,
    task_filter: TaskFilter,
    collapsed: set[int],
    read_only: bool,
    row_height: int,
    add_height: int,
) -> list[RowSlot]:
    """gantt.render が描く行の並び。描画と矢印の計算の、両方がこの並びを使う。"""
    slots: list[RowSlot] = []
    for ti, task in enumerate(project.tasks):
        if matches(task, task_filter):
            slots.append(RowSlot("task", None, ti, task.id, True, row_height))
    if not read_only:
        slots.append(RowSlot("top-add", None, None, None, True, add_height))
    for si, section in enumerate(project.sections):
        is_collapsed = si in collapsed and not read_only
        shown = visible_task_indexes(section, task_filter, is_collapsed)
        if task_filter.active and not shown:
            continue
        slots.append(RowSlot("section", si, None, None, True, row_height))
        visible = set(shown)
        for ti, task in enumerate(section.tasks):
            if task_filter.active and ti not in visible:
                continue
            slots.append(RowSlot("task", si, ti, task.id, ti in visible, row_height))
    return slots


def row_centers(slots: list[RowSlot], top: float) -> dict[str, float]:
    """表示中のタスクの id から、行の中央の縦位置。top は、行の並びの上端(見出しの高さ)。"""
    centers: dict[str, float] = {}
    y = top
    for slot in slots:
        if not slot.shown:
            continue
        if slot.task_id is not None:
            centers[slot.task_id] = y + slot.height / 2
        y += slot.height
    return centers


def total_height(slots: list[RowSlot], top: float) -> float:
    return top + sum(slot.height for slot in slots if slot.shown)


@dataclass(frozen=True)
class Bar:
    """棒の左端と右端。名前の欄の右端(境界)からの距離(px)。"""

    left: float
    right: float


def link_points(
    pred: Bar, pred_y: float, succ: Bar, succ_y: float, row_height: int
) -> list[tuple[float, float]]:
    """先行の棒の右端から、後続の棒の左端までの折れ線(直角)。"""
    out = (pred.right, pred_y)
    if succ.left - pred.right >= MIN_GAP_PX:
        elbow = pred.right + STUB_PX
        return [out, (elbow, pred_y), (elbow, succ_y), (succ.left, succ_y)]
    between = pred_y + row_height / 2 if succ_y > pred_y else pred_y - row_height / 2
    right, left = pred.right + STUB_PX, succ.left - STUB_PX
    return [out, (right, pred_y), (right, between), (left, between), (left, succ_y), (succ.left, succ_y)]


def path_data(points: list[tuple[float, float]]) -> str:
    """SVG の path の d 属性。"""
    (x0, y0), *rest = points
    return f"M{x0:g},{y0:g} " + " ".join(f"L{x:g},{y:g}" for x, y in rest)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_links.py -q` と `uvx ty check src`
Expected: PASS

(`test_centers_use_each_rows_height` の `total_height` の期待値は、`top + 行(32)×2 + 追加行(24)+ 見出し(32)+ 2 タスク(64)+ 見出し(32)+ 1 タスク(32)` = `100 + 64 + 24 + 32 + 64 + 32 + 32`。式が合わなければ、実装でなく期待値の式を直す。)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/links.py test/test_links.py
git commit -m "feat: 矢印の折れ線と行の並びの計算(links.py)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 矢印の描画(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`render`、`toggle_section`、定数・CSS)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `links.row_slots`・`row_centers`・`total_height`・`link_points`・`path_data`・`Bar`(Task 6)、`self.schedule`(Task 3)
- Produces: マーカー `links` の `ui.html`(1 要素)。経路は `data-link="先行ID-後続ID"`。`GanttChart.update_links()`(折りたたみで SVG だけ作り直す)

要点:
- 行の並びは `self.slots()`(`row_slots(...)` を `self.project`・`self.task_filter`・`self.collapsed`・`self.options.read_only`・`ROW_HEIGHT_PX`・`ADD_ROW_HEIGHT_PX` で呼ぶ)。
- 見出しの高さ(行の並びの上端)= `BAND_HEIGHT_PX * (1 if MONTH else 2) + (HEADER_HEIGHT_PX if DAY else ROW_HEIGHT_PX)`。
- 棒の位置は `task_row` と同じ式: `left = span[0] * width`、`right = left + max(span[1] * width, MIN_BAR_PX)`。`bar_visible` が偽、または `bar_span` が None の棒は、矢印を出さない。
- SVG は、`gridlines`・`stripes`・`header` の後、最初の行の前に置く(DOM の順で、棒より下・名前の列(sticky)より下になる)。

- [ ] **Step 1: テストを書く(失敗させる)**

`test/test_gantt.py` の末尾へ追加する(`mount`・`BASE` などは import 済み)。`GanttChart` のインスタンスは、`mount` が返す `Recorder` からは取れないので、既存の、チャートを直接操作しているテスト(`chart.toggle_section` を呼ぶもの。`grep -n "toggle_section" test/test_gantt.py`)の作り方を写して `charts` を得る:

```python
def linked_project() -> Project:
    a = Task("先行", id="aaaaaaaa", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5)
    b = Task(
        "後続",
        id="bbbbbbbb",
        planned_start=datetime(2026, 10, 7, 9),
        effort_hours=6.5,
        predecessors=["aaaaaaaa"],
    )
    return Project("demo", base_date=BASE, sections=[Section("開発", [a, b])])


def link_paths(user: User) -> list[str]:
    elements = user.find(marker="links").elements
    if not elements:
        return []
    content = elements.pop().content
    return re.findall(r'data-link="([^"]+)"', content)


async def test_an_arrow_is_drawn_for_each_link(user: User) -> None:
    mount(linked_project())
    await user.open("/")
    assert link_paths(user) == ["aaaaaaaa-bbbbbbbb"]


async def test_the_arrows_are_one_html_element(user: User) -> None:
    mount(linked_project())
    await user.open("/")
    assert len(user.find(marker="links").elements) == 1


async def test_no_links_means_no_arrow_paths(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert link_paths(user) == []


async def test_the_arrow_connects_the_bars(user: User) -> None:
    mount(linked_project())
    await user.open("/")
    content = user.find(marker="links").elements.pop().content
    day = COLUMN_WIDTH_PX[Scale.DAY]
    pred_right = 15.5 / 24 * day  # 月 15:30(基準日の月曜が 0 列目)
    succ_left = (2 + 9 / 24) * day  # 水 9:00
    rows_top = BAND_HEIGHT_PX * 2 + HEADER_HEIGHT_PX  # 日次: 年・月の帯 + 日付の行
    first = rows_top + ADD_ROW_HEIGHT_PX + ROW_HEIGHT_PX + ROW_HEIGHT_PX / 2  # 追加行・見出しの次
    second = first + ROW_HEIGHT_PX
    found = re.search(r'<path data-link="aaaaaaaa-bbbbbbbb" d="([^"]+)"', content)
    assert found is not None
    assert found.group(1) == (
        f"M{pred_right:g},{first:g} L{pred_right + 6:g},{first:g}"
        f" L{pred_right + 6:g},{second:g} L{succ_left:g},{second:g}"
    )


絞り込み・折りたたみ・範囲外のテスト(`mount` が `GanttChart` を返さないため、`mount_chart` ヘルパーを足す):

```python
def mount_chart(project: Project, holder: list[GanttChart]) -> None:
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, recorder.actions, now=lambda: datetime(2026, 10, 1))
        holder.append(chart)
        chart.build()


async def test_an_arrow_disappears_when_a_filter_hides_a_row(user: User) -> None:
    holder: list[GanttChart] = []
    mount_chart(linked_project(), holder)
    await user.open("/")
    holder[0].set_filter(TaskFilter(query="先行"))
    await settles()
    assert link_paths(user) == []


async def test_collapsing_the_section_updates_only_the_arrows(user: User) -> None:
    holder: list[GanttChart] = []
    mount_chart(linked_project(), holder)
    await user.open("/")
    chart = holder[0]
    element_before = user.find(marker="links").elements.pop()
    chart.toggle_section(0)
    assert link_paths(user) == []
    assert user.find(marker="links").elements.pop() is element_before  # 同じ要素の内容だけ変わる
    chart.toggle_section(0)
    assert link_paths(user) == ["aaaaaaaa-bbbbbbbb"]


async def test_an_arrow_is_hidden_when_a_bar_is_outside_the_period(user: User) -> None:
    holder: list[GanttChart] = []
    mount_chart(linked_project(), holder)
    await user.open("/")
    holder[0].set_options(ViewOptions(period=(date(2026, 10, 5), date(2026, 10, 5)), read_only=True))
    await settles()
    assert link_paths(user) == []  # 後続の棒が期間外


async def test_the_arrows_are_drawn_in_every_scale_and_in_the_preview(user: User) -> None:
    holder: list[GanttChart] = []
    mount_chart(linked_project(), holder)
    await user.open("/")
    for scale in (Scale.WEEK, Scale.MONTH, Scale.DAY):
        holder[0].set_scale(scale)
        await settles()
        assert link_paths(user) == ["aaaaaaaa-bbbbbbbb"]
    holder[0].set_options(ViewOptions(read_only=True))
    await settles()
    assert link_paths(user) == ["aaaaaaaa-bbbbbbbb"]


async def test_the_arrow_svg_uses_theme_variables_and_ignores_the_pointer(user: User) -> None:
    mount(linked_project())
    await user.open("/")
    element = user.find(marker="links").elements.pop()
    assert "pointer-events: none" in element.props["style"]
    assert "var(--link-color)" in element.content
    assert "body.body--dark .gantt-links" in LINK_CSS


async def test_the_slots_match_the_rendered_rows(user: User) -> None:
    holder: list[GanttChart] = []
    mount_chart(linked_project(), holder)
    await user.open("/")
    chart = holder[0]
    chart.toggle_section(0)
    for slot in chart.slots():
        marker = (
            f"row-{'top' if slot.si is None else slot.si}-{slot.ti}"
            if slot.kind == "task"
            else {"top-add": "top-end", "section": f"section-{slot.si}"}[slot.kind]
        )
        if slot.shown:
            user.should_see(marker=marker)
        else:
            user.should_not_see(marker=marker)
```

(`settles`・`re`・`date`・`ViewOptions`・`TaskFilter` は、`test_gantt.py` の先頭で import 済み。`BAND_HEIGHT_PX`・`HEADER_HEIGHT_PX`・`ADD_ROW_HEIGHT_PX`・`ROW_HEIGHT_PX`・`LINK_CSS` は `projectapp.gantt` から import に足す。`LINK_CSS` は、下の実装で作る定数。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "arrow or slots_match or links"`
Expected: FAIL

- [ ] **Step 3: `gantt.py` に定数と CSS を足す**

import に `from projectapp.links import Bar, RowSlot, link_points, path_data, row_centers, row_slots, total_height` を足す。`GRID_BORDER` の定義の近くに追加する:

```python
LINK_CSS = """
.gantt-links { --link-color: #757575; }
body.body--dark .gantt-links { --link-color: #bdbdbd; }
"""
LINK_STYLE = "stroke: var(--link-color); stroke-width: 1.5; fill: none"
LINK_HEAD = (
    '<defs><marker id="link-head" markerWidth="6" markerHeight="6" refX="6" refY="3"'
    ' orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L6,3 L0,6 z"'
    ' style="fill: var(--link-color)"/></marker></defs>'
)
```

`build()` の `ui.add_css(PRIORITY_CSS)` の次に `ui.add_css(LINK_CSS)` を足す。

- [ ] **Step 4: 矢印のメソッドを足す**

`GanttChart.__init__` に `self.links_html: ui.html | None = None`、`self.link_layout: tuple[list[Column], int] | None = None` を足す。`bar_visible` の次にメソッドを追加する:

```python
    def slots(self) -> list[RowSlot]:
        return row_slots(
            self.project,
            self.task_filter,
            self.collapsed,
            self.options.read_only,
            ROW_HEIGHT_PX,
            ADD_ROW_HEIGHT_PX,
        )

    def rows_top(self) -> int:
        """行の並びの上端(年・月の帯と、日付の行の高さ)。"""
        bands = BAND_HEIGHT_PX * (1 if self.view_scale is Scale.MONTH else 2)
        return bands + (HEADER_HEIGHT_PX if self.view_scale is Scale.DAY else ROW_HEIGHT_PX)

    def link_bars(self, columns: list[Column], width: int) -> dict[str, Bar]:
        """矢印を出せる棒(表示範囲にあるもの)の、境界からの左端・右端。"""
        bars: dict[str, Bar] = {}
        for task in self.project.all_tasks():
            start, end = self.schedule.start(task), self.schedule.end(task)
            span = bar_span(start, end, columns)
            if span is None or not self.bar_visible(start, end, columns):
                continue
            left = span[0] * width
            bars[task.id] = Bar(left, left + max(span[1] * width, MIN_BAR_PX))
        return bars

    def links_markup(self, columns: list[Column], width: int) -> str:
        """矢印の SVG。内容は数値と、保存時に検証した id(16 進)だけで、利用者の文字列を含まない。"""
        slots = self.slots()
        top = self.rows_top()
        centers = row_centers(slots, top)
        bars = self.link_bars(columns, width)
        paths: list[str] = []
        for task in self.project.all_tasks():
            for pid in task.predecessors:
                if pid not in bars or task.id not in bars:
                    continue
                if pid not in centers or task.id not in centers:
                    continue
                points = link_points(bars[pid], centers[pid], bars[task.id], centers[task.id], ROW_HEIGHT_PX)
                paths.append(
                    f'<path data-link="{html.escape(pid)}-{html.escape(task.id)}"'
                    f' d="{path_data(points)}" style="{LINK_STYLE}" marker-end="url(#link-head)"/>'
                )
        size = f'width="{width * len(columns):g}" height="{total_height(slots, top):g}"'
        return f'<svg {size} style="overflow: visible">{LINK_HEAD}{"".join(paths)}</svg>'

    def links(self, columns: list[Column], width: int) -> None:
        """棒より下、格子線・縞より上に、矢印をまとめて 1 要素で置く。"""
        self.link_layout = (columns, width)
        self.links_html = ui.html(self.links_markup(columns, width), sanitize=False)
        self.links_html.classes("gantt-links").style(
            "position: absolute; top: 0; left: var(--name-w); pointer-events: none"
        ).mark("links")

    def update_links(self) -> None:
        """折りたたみの切り替えで、再描画せず、矢印だけ作り直す。"""
        if self.links_html is not None and self.link_layout is not None:
            self.links_html.content = self.links_markup(*self.link_layout)
```

`render` の、`self.no_match_message()` の次(最初の行の前)に `self.links(columns, width)` を足す。`toggle_section` の末尾(`for row in view.rows:` ループの後、`if not self.task_filter.active:` の外)に `self.update_links()` を足す(`return` の早期脱出より後ろ、折りたたみの状態を変えた直後に必ず呼ぶ位置に置く。`view is None or read_only` の `return` の前に呼べば足りるが、読み取り専用では矢印は変わらないので、`return` の後でよい)。

`render` を `refresh` するたびに `self.links_html` が作り直される(`ui.refreshable` が子ごと作り直す)ので、古い参照が残らないことを `test_collapsing_the_section_updates_only_the_arrows` が確かめる。

- [ ] **Step 5: `ui.html` の `content` の更新を確かめる**

Run: `uv run python -c "from nicegui import ui; e = ui.html('a', sanitize=False); e.content = 'b'; print(e.content)"`
Expected: `b`(出ない場合は `e.set_content('b')` を使い、`update_links` を直す)

- [ ] **Step 6: 通ることを確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "arrow or slots_match or links"`
Expected: PASS(期待値の座標は、`from_name` ではなく SVG 内の px なので、`pred_right`・`succ_left` の式をそのまま使う。差があれば、実装でなく `task_row` と同じ式で期待値を直す)

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: タスク同士の矢印をチャート全体の 1 つの SVG で描く

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 文書の更新と、最終確認

**Files:**
- Modify: `docs/development.md`(「ファイル形式の注意」)
- Modify: `CLAUDE.md`(`projectapp/CLAUDE.md`。ガントチャートの連結の記述)
- Modify: `.claude/MEMORY.md`(作業記録)

- [ ] **Step 1: `docs/development.md` の「ファイル形式の注意」に追記する**

「タスクの日付は…」の項目の前に、次を足す:

```markdown
- `Task.id`(8 桁の 16 進。`models.new_id`)と `Task.predecessors`(先行タスクの `id` のリスト)を保存する。`id` のないファイルは、読込時に振る(移行は要らず、保存し直すと残る)。`predecessors` のキーがない・`null` は空。読込(`storage.load_project` → `linkgraph.validate_links`)は、`id` が空・文字列以外・重複、`predecessors` がリストでない・文字列以外を含む・重複、存在しない `id`、自分自身、循環を拒否する。`Task.id` は `compare=False`(乱数で、タスクの比較に使わない)。コピーは新しい `id` で `predecessors` は空。削除は、ほかのタスクの `predecessors` から外す(`linkgraph.drop_task_links`)。
- 実効の開始・完了は保存しない。`timeline.Schedule`(必要なものだけ算出してメモする)が、`max(開始予定, 先行の完了)` で押し出し、手指定の完了予定と工数なしの `planned_end` は押し出した幅だけ後ろへずらす(締切は動かさない)。先行の完了は、状態が「終了」で実績の終了があればその時刻、なければ先行の実効の完了。循環があっても無限再帰しない(押し出しなし)。`effective_start` / `effective_end` は `schedule` を渡さなければ、その場で上流だけを解く(先行がなければ従来の計算)。表示・判定で開始を読むときは `planned_start` を直接読まず、これを使う(入力・保存の `forms`・`task_dialog`・`storage` は自分の開始予定を扱う)。
- 矢印は `links.py`(行の並び `row_slots`・縦位置・折れ線の純粋関数)と、`gantt.GanttChart.links`(チャート全体で 1 つの `ui.html`。マーカー `links`、経路は `data-link="先行ID-後続ID"`)。DOM の順で、格子線・縞・見出しの後、行の前に置く(棒・名前の列より下)。行の高さの並びは `row_slots` を描画と共有し、見出しの高さは `GanttChart.rows_top`。折りたたみは `update_links` で SVG の内容だけを作り直す。絞り込みで隠れた行・折りたたみで隠れた行・期間の外の棒には出さない。
- 押し出されたタスクのバーのドラッグは、見えている開始を基準にずらし(`arrange.shift_task(task, days, shown_start)`)、基準日と先行の完了の日より前へは動かさない(`arrange.min_shift_days`)。
```

- [ ] **Step 2: `CLAUDE.md`(`projectapp/CLAUDE.md`)の連結の記述を直す**

「ガントチャート同士は、後続タスク、先頭タスクなど、連結ができ連結は、棒線型の矢印で紐付けされる」の行を、次に置き換える:

```markdown
- タスクは、編集ダイアログの`先行タスク`欄(複数選択)で連結でき、連結は棒線型の矢印で表示される。後続の実際の開始は、`自分の開始予定`と`先行の完了`の遅いほうになる(先行が早まっても、自分の開始予定より前には戻らない。保存しない)。終了済みの先行は、実績の終了を使う。手指定の完了予定は、押し出された分だけ同じ幅でずれ、締切は動かさない。矢印は、絞り込み・折りたたみで行が隠れたとき、棒が表示範囲の外のときは出さない。ドラッグでの連結と矢印のクリックでの解除は、後続機能
```

- [ ] **Step 3: 最終確認(自動)**

Run: `uv run pytest -n auto -q`、`uvx ty check src`、`uv run pytest -q`(直列。バックグラウンドで、結果の行まで待つ)
Expected: すべて PASS、ty はエラーなし

Run: `grep -rn "planned_start" src/projectapp | grep -v "^src/projectapp/\(models\|storage\|forms\|task_dialog\|timeline\|arrange\).py"`
Expected: `views.py` の通知の判定と `gantt.py` に残る `Task` 作成以外が出ないこと(出たものは、Task 3 の表の方針で確かめる)。

- [ ] **Step 4: 実機確認(ネイティブ。`uv run projectapp`)**

次を目で確かめ、結果を作業記録に書く:
- 先行・後続を編集ダイアログで連結し、矢印が棒の端に正しく出る(ライト・ダーク)。
- 日次・週次・月次で矢印が出て、棒と行がずれない。後続が近い(12px 未満)ときの経路。
- セクションの折りたたみ・絞り込みで、矢印が消える・戻る。名前の欄の幅を変えても、矢印が棒に付いてくる。
- 先行側のバーをドラッグすると、後続が追従する。押し出された後続を左へドラッグしても、先行の完了より前へ行かない。
- チャートプレビューと PNG に矢印が入る。ダッシュボード・担当者へ書き出しが落ちない。
- 120 タスク程度でも、描画が体感で遅くならない(`docs/development.md` の測り方で、矢印の前後の時間を比べる)。

- [ ] **Step 5: 作業記録を更新して、コミット**

`.claude/MEMORY.md` の「進行中: タスク同士の矢印連結」を、実装済み(コミットの範囲・テスト件数・実機確認の結果・未確認の点)に書き換え、「次にやること」の 4 の「着手」を「実装済み」に直す。

```bash
git add docs/development.md CLAUDE.md .claude/MEMORY.md
git commit -m "docs: タスク同士の矢印連結の文書と作業記録を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

マージとプッシュは、ユーザーの許可を得てから行う(`develop` へ)。

---

## Self-Review(計画の作成者の確認)

**設計書との対応:** §2 データ → Task 1。§3.1〜3.3 → Task 2。§3.4 の表 → Task 3(grep と突き合わせる手順つき)。§3.5 → Task 5。§4 ダイアログ → Task 4。§5 矢印 → Task 6・7。§6・§7(テスト)・§8 → 各タスクと Task 8。実機確認 → Task 8 Step 4。

**設計書との違い(2 点):**
1. 近接のときの経路は、設計書の「4 区間」ではなく 5 区間(右 6px → 縦 → 左 → 縦 → 右)になる。点列をテストで固定している。
2. `Task.id` を `compare=False` にした(乱数で、既存の約 1,271 件のテストの比較を壊さないため)。

**型の一貫性:** `Schedule.start/end/latest_finish/finish`、`effective_start/end(..., schedule=)`、`shift_task(task, days, shown_start)`、`min_shift_days(task, base_date, shown_start, floor)`、`RowSlot`・`row_slots`・`row_centers`・`total_height`・`Bar`・`link_points`・`path_data`、`link_options`・`finish_of`、`build_task(predecessors, linkable_ids)`・`push_hint` は、定義したタスクと使うタスクで同じ名前・並び。`Schedule._finish` は Task 4 で `finish` に改める(Task 2 の `latest_finish` の呼び出しも同時に直す)。

**既知の確認点(実装時に、実行して確かめる):** Task 2 のテストの期待値(`calc_end` の枠の規則から手計算)、Task 3・5・7 のテストでの、バーの `props` の読み方(既存テストに揃える)、`ui.html.content` の更新(Task 7 Step 5)。
