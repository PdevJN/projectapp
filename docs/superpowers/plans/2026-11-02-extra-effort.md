# 追加工数 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの工数を書き換えずに、後から`追加工数`(日付・時間・理由の履歴)を足せるようにし、完了予定・警告・ダッシュボードなどの計算に合計工数を使う。

**Architecture:** `Task.extra_efforts: list[ExtraEffort]` と、もとの見積もり + 追加の合計を返す`Task.total_effort`を足す。計算側は`effort_hours`の直接参照を`total_effort`に替える。足す操作は右クリックの小ダイアログ(進捗度は消化時間を保って再計算)、履歴の修正・削除は編集ダイアログのサブダイアログで行う。ファイル形式は`version` 20。

**Tech Stack:** Python 3.13・NiceGUI・pytest(`uv run`)・ruff(`uvx`)・ty。

**Spec:** [`docs/superpowers/specs/2026-11-02-extra-effort-design.md`](../specs/2026-11-02-extra-effort-design.md)(Task 7 で、実装に合わせて直す)

## Global Constraints

- 言語は日本語(画面の文言・エラーメッセージ・コメント)。Python 3.13 以上。型ヒントはすべての関数に付ける。コメントは 3 行以内。
- ファイル形式は`FORMAT_VERSION`を 19 → 20。`version` < 20 のファイルは、`extra_efforts`のキーがあっても無視して空で読む。新しい`version`は今までどおり拒否する。
- 追加工数の`hours`は 0 より大きい有限の数で、小数点以下 2 桁まで(`HOURS_DECIMALS = 2`)。`reason`は 100 文字以内で制御文字なし。1 タスクの履歴は 200 件まで。
- 追加できるのは、通常タスク(`TaskKind.NORMAL`)で、`effort_hours > 0`、状態が`終了`でないもの。
- 追加の日付は`MainView.now()`の日付(テストでは`view.now = lambda: …`で指定する)。
- 進捗度の再計算は、足す操作のときだけ: `round(旧進捗度 × 旧合計 ÷ 新合計)`(0〜100)。進捗度が`None`なら触らない。履歴の修正・削除では再計算しない。
- 一括編集の工数の増減(`bulk_edit.py`)は、`effort_hours`(もとの見積もり)を直す。追加分は変えない。
- 実装のたびに`uv run pytest -m smoke`、完了時に`uvx ruff check`・`uvx ruff format src test`・`uvx ty check src`(`days_text`の指摘 1 件は変更前からある)。全テスト(`uv run pytest -n auto`)は smoke が失敗したときに限る。
- コミットメッセージの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。マージは利用者の指示を待つ(PR を作って止まる)。

## Review Focus

1. 壊れた`extra_efforts`のファイル(時間が 0・負・非有限・文字列・小数 3 桁、日付の誤り、理由が長すぎる・制御文字)は読み込みを拒否する。(Task 1)
2. 進捗度が 0%・100%・未設定のタスクに足したとき、進捗度は 0〜100 に収まり、未設定は未設定のまま。(Task 3)
3. 完了予定を手で指定したタスクは、足しても完了予定が動かない。自動算出は追加分だけ延びる。(Task 2)
4. 工数 0・終了済み・まとめ・節目・プロジェクト参照のタスクには、足せない(メニューは押せず、関数は`ValueError`)。(Task 3・4)
5. 両方の側が別々に足したプロジェクトのマージは、黙って片方を捨てずに衝突として出す。(Task 1)
6. 追加工数のあるタスクを分解しても、子の工数の合計が合計工数に一致し、親(まとめ)に履歴が残らない。(Task 2)

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `src/projectapp/models.py` | `ExtraEffort`・`Task.extra_efforts`・`Task.total_effort`・定数・`FORMAT_VERSION` |
| `src/projectapp/storage.py` | `extra_efforts`の読み書き・検証・種別ごとのクリア |
| `src/projectapp/merge.py` | `TASK_LABELS`に`追加工数`を足す(項目まるごとのマージ) |
| `src/projectapp/remaining.py`・`timeline.py`・`reassign.py`・`handoff.py`・`decompose.py`・`decompose_dialog.py`・`summary.py`・`dashboard.py`・`bottom_info.py` | `effort_hours`の計算上の参照を`total_effort`に替える |
| `src/projectapp/forms.py` | `can_add_extra_effort`・`extra_effort_progress`・`add_extra_effort`・`build_extra_efforts`・`build_task(extra_efforts=)` |
| `src/projectapp/task_dialog.py` | `open_extra_effort_dialog`・`open_extra_effort_history_dialog`・編集ダイアログの補足とボタン |
| `src/projectapp/gantt.py`・`views.py` | 右クリックの`追加工数を足す…`・`MainView.add_extra_effort` |
| `test/test_storage.py`・`test_merge.py`・`test_extra_effort_calc.py`(新規)・`test_forms.py`(または既存の forms テスト)・`test_context_menu.py`・`test_views.py`・`test_bottom_info.py` | テスト |

---

### Task 1: モデル・保存・マージ

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION`・`ExtraEffort`・`Task`)
- Modify: `src/projectapp/storage.py`(`_task`・`_summary`・`_checkpoint`・`_reference`・新しい`_extra_efforts`)
- Modify: `src/projectapp/merge.py:TASK_LABELS`
- Modify: `test/test_reference_storage.py:44`・`test/test_summary.py:113`(`FORMAT_VERSION == 19` → `20`)
- Test: `test/test_storage.py`・`test/test_merge.py`

**Interfaces:**
- Produces: `models.ExtraEffort(day: date, hours: float, reason: str = "")`(frozen dataclass)、`models.MAX_EXTRA_EFFORTS = 200`、`models.MAX_EXTRA_REASON = 100`、`models.EXTRA_EFFORT_DECIMALS = 2`、`Task.extra_efforts: list[ExtraEffort]`、`Task.total_effort -> float`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py`の import に`ExtraEffort`を足し(`from projectapp.models import (…)`の並びに追加)、末尾に追記する:

```python
GOOD_EXTRA = {"day": "2026-10-07", "hours": 1.0, "reason": ""}


def test_extra_efforts_round_trip_and_default_to_empty() -> None:
    task = Task(
        "a",
        id="t1",
        effort_hours=10.0,
        extra_efforts=[
            ExtraEffort(date(2026, 10, 7), 5.0, "見つかった作業"),
            ExtraEffort(date(2026, 10, 8), 0.5),
        ],
    )
    project = Project("p", tasks=[task, Task("b", id="t2")])
    text = dumps_project(project)
    saved = json.loads(text)["tasks"]
    assert saved[0]["extra_efforts"] == [
        {"day": "2026-10-07", "hours": 5.0, "reason": "見つかった作業"},
        {"day": "2026-10-08", "hours": 0.5, "reason": ""},
    ]
    assert saved[1]["extra_efforts"] == []
    loaded = parse_project(text, "p").tasks
    assert loaded[0].extra_efforts == task.extra_efforts
    assert loaded[0].total_effort == 15.5
    assert loaded[1].extra_efforts == []


@pytest.mark.parametrize("version", [1, 10, 19])
def test_an_older_file_reads_no_extra_efforts(version: int) -> None:
    task = Task(
        "a",
        id="t1",
        effort_hours=4.0,
        extra_efforts=[ExtraEffort(date(2026, 10, 7), 1.0)],
    )
    raw = json.loads(dumps_project(Project("p", tasks=[task])))
    raw["version"] = version
    assert parse_project(json.dumps(raw), "p").tasks[0].extra_efforts == []


@pytest.mark.parametrize(
    "bad",
    [
        "x",
        {},
        [1],
        [{**GOOD_EXTRA, "hours": 0}],
        [{**GOOD_EXTRA, "hours": -1}],
        [{**GOOD_EXTRA, "hours": True}],
        [{**GOOD_EXTRA, "hours": "1"}],
        [{**GOOD_EXTRA, "hours": float("inf")}],
        [{**GOOD_EXTRA, "hours": 1.234}],
        [{**GOOD_EXTRA, "day": "2026-13-01"}],
        [{**GOOD_EXTRA, "day": None}],
        [{**GOOD_EXTRA, "reason": 5}],
        [{**GOOD_EXTRA, "reason": "x" * 101}],
        [{**GOOD_EXTRA, "reason": "a\u0007"}],
        [GOOD_EXTRA] * 201,
    ],
)
def test_invalid_extra_efforts_are_rejected(bad: object) -> None:
    raw = json.loads(
        dumps_project(Project("p", tasks=[Task("a", id="t1", effort_hours=4.0)]))
    )
    raw["tasks"][0]["extra_efforts"] = bad
    with pytest.raises(ValueError, match="追加工数"):
        parse_project(json.dumps(raw), "p")


def test_extra_efforts_are_cleared_for_a_checkpoint() -> None:
    node = Task("節目", id="c1", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 8, 17))
    raw = json.loads(dumps_project(Project("p", tasks=[node])))
    raw["tasks"][0]["extra_efforts"] = [GOOD_EXTRA]
    assert parse_project(json.dumps(raw), "p").tasks[0].extra_efforts == []
```

`test/test_merge.py`の import に`ExtraEffort`を足し、末尾に追記する:

```python
def test_extra_efforts_merge_as_one_item_and_conflict_when_both_add() -> None:
    first = ExtraEffort(date(2026, 10, 7), 2.0, "a")
    second = ExtraEffort(date(2026, 10, 8), 3.0, "b")
    base = proj(tasks=[task("a", "t1", effort_hours=4.0)])
    ours = proj(tasks=[task("a", "t1", effort_hours=4.0, extra_efforts=[first])])
    theirs = proj(tasks=[task("a", "t1", effort_hours=2.0)])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert merged.project.tasks[0].extra_efforts == [first]
    assert merged.project.tasks[0].effort_hours == 2.0
    other = proj(tasks=[task("a", "t1", effort_hours=4.0, extra_efforts=[second])])
    (conflict,) = merge_projects(base, ours, other).conflicts
    assert (conflict.field, conflict.ours, conflict.theirs) == (
        "追加工数",
        [first],
        [second],
    )
```

`test/test_reference_storage.py:44`と`test/test_summary.py:113`の`assert FORMAT_VERSION == 19`を`20`に直す。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_storage.py test/test_merge.py -q -n 0 -k "extra_effort"`
Expected: FAIL(`ImportError: cannot import name 'ExtraEffort'`)

- [ ] **Step 3: モデルを実装する**

`src/projectapp/models.py`:

1. `FORMAT_VERSION = 19` を `20` にし、後ろのコメントの末尾に`、20: タスクの追加工数 extra_efforts`を足す。
2. `Assignee`の定義(`class Assignee`)の直後に足す:

```python
MAX_EXTRA_EFFORTS = 200  # 1 タスクの追加工数の履歴の上限
MAX_EXTRA_REASON = 100  # 追加工数の理由の文字数の上限
EXTRA_EFFORT_DECIMALS = 2  # 追加工数の時間の小数点以下の桁数


@dataclass(frozen=True)
class ExtraEffort:
    """後から足した追加工数の 1 件(要望 105)。もとの見積もり(Task.effort_hours)は書き換えず、履歴として持つ。"""

    day: date
    hours: float
    reason: str = ""
```

3. `Task`の最後のフィールド(`weekly_crew`の次)に足す:

```python
    extra_efforts: list[ExtraEffort] = field(
        default_factory=list
    )  # 後から足した追加工数の履歴(通常タスクだけ。工数があるとき)

    @property
    def total_effort(self) -> float:
        """もとの見積もりと追加工数の合計[h]。計算(完了予定・残りの工数・按分)は、工数をここから取る。"""
        return round(self.effort_hours + sum(e.hours for e in self.extra_efforts), 6)
```

(`@property assignee_names`の前か後に置く。`date`は models.py で import 済み。)

- [ ] **Step 4: 保存・読込を実装する**

`src/projectapp/storage.py`:

1. import に`MAX_EXTRA_EFFORTS`・`MAX_EXTRA_REASON`・`EXTRA_EFFORT_DECIMALS`・`ExtraEffort`・`has_control_char`(すでにあれば不要)を`projectapp.models`から足す。
2. `_children`の前に足す:

```python
def _extra_efforts(value: Any) -> list[ExtraEffort]:
    """タスクの追加工数の履歴(version 20)。キーがない・null は空。形式の誤り・時間が 0 以下か非有限か桁が多い・日付の誤り・
    理由が長すぎる(制御文字)・件数が多すぎるときは ValueError(開けませんでした)。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("追加工数がリストではありません")
    if len(value) > MAX_EXTRA_EFFORTS:
        raise ValueError(f"追加工数は{MAX_EXTRA_EFFORTS}件までです")
    efforts: list[ExtraEffort] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("追加工数の形式が正しくありません")
        hours = raw.get("hours")
        if (
            isinstance(hours, bool)
            or not isinstance(hours, int | float)
            or not isfinite(hours)
            or hours <= 0
            or round(hours, EXTRA_EFFORT_DECIMALS) != hours
        ):
            raise ValueError(f"追加工数の時間が正しくありません: {hours!r}")
        day = raw.get("day")
        try:
            moment = date.fromisoformat(day) if isinstance(day, str) else None
        except ValueError:
            moment = None
        if moment is None:
            raise ValueError(f"追加工数の日付が正しくありません: {day!r}")
        reason = raw.get("reason", "")
        if (
            not isinstance(reason, str)
            or len(reason) > MAX_EXTRA_REASON
            or has_control_char(reason)
        ):
            raise ValueError("追加工数の理由が正しくありません")
        efforts.append(ExtraEffort(moment, float(hours), reason))
    return efforts
```

3. `_task`の`Task(...)`の呼び出しに、`ref_snapshot=…`の次の引数として足す:

```python
        extra_efforts=_extra_efforts(raw.get("extra_efforts"))
        if ctx.version >= 20
        else [],
```

4. `_summary`・`_checkpoint`・`_reference`の`replace(task, …)`のそれぞれに`extra_efforts=[],`を足す(`effort_hours=0.0,`の次の行)。

保存側は`asdict(project)`が`ExtraEffort`を辞書にし、`_encode`が`date`を ISO 文字列にするので、変更は要らない。

- [ ] **Step 5: マージを実装する**

`src/projectapp/merge.py`の`TASK_LABELS`に、`"weekly_crew": "週ごとの担当",`の次の行として足す:

```python
    "extra_efforts": "追加工数",
```

(`_flatten`は`fields(Task)`でフィールドを回すので、他の変更は要らない。)

- [ ] **Step 6: テストが通ることを確かめる**

Run: `uv run pytest test/test_storage.py test/test_merge.py test/test_reference_storage.py test/test_summary.py -q -n 0`
Expected: PASS(新しい 4 + 15 + 1 + 1 件を含む)

- [ ] **Step 7: smoke とコミット**

Run: `uv run pytest -m smoke -q`(PASS)、`uvx ruff format src test`
```bash
git add -A
git commit -m "feat: 追加工数のモデルと保存(version 20)・マージを足す(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 計算を合計工数にする

**Files:**
- Modify: `src/projectapp/remaining.py`(`total_effort`)、`src/projectapp/timeline.py:732,742`、`src/projectapp/reassign.py`、`src/projectapp/handoff.py:69,87,95,111`、`src/projectapp/decompose.py:63,82,125,149,182,190`、`src/projectapp/decompose_dialog.py:122,155`、`src/projectapp/summary.py:66`、`src/projectapp/dashboard.py:264`、`src/projectapp/bottom_info.py:182-183`
- Test: `test/test_extra_effort_calc.py`(新規)

**Interfaces:**
- Consumes: Task 1 の`Task.total_effort`・`ExtraEffort`。
- Produces: 完了予定・残りの工数・警告・按分・分解が合計工数で動く。`remaining.total_effort(task)`は`task.total_effort`を返す。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_extra_effort_calc.py`(新規):

```python
from datetime import date, datetime

import pytest

from projectapp.decompose import decompose, default_parts
from projectapp.models import (
    Assignee,
    ExtraEffort,
    Member,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import Schedule

MON = datetime(2026, 10, 5, 9)  # 月曜 9:00。稼働の枠は 9:00〜15:30(6.5h)
EXTRA = [ExtraEffort(date(2026, 10, 6), 6.5, "見つかった作業")]


def project_of(task: Task) -> Project:
    return Project(
        "P", base_date=date(2026, 10, 5), members=[Member("田中", 1.0)], tasks=[task]
    )


def task_with(extra: list[ExtraEffort] | None = None, **kw: object) -> Task:
    return Task(
        "a",
        id="t1",
        planned_start=MON,
        effort_hours=13.0,
        assignees=[Assignee("田中", 1.0)],
        extra_efforts=list(extra or []),
        **kw,  # type: ignore[arg-type]
    )


def test_total_effort_adds_the_extra_efforts() -> None:
    task = task_with(EXTRA)
    assert task.total_effort == 19.5
    assert total_effort(task) == 19.5


def test_the_computed_end_moves_by_the_extra_effort() -> None:
    plain, extended = task_with(), task_with(EXTRA)
    end_plain = Schedule(project_of(plain), {}).end(plain)
    end_extended = Schedule(project_of(extended), {}).end(extended)
    assert end_plain == datetime(2026, 10, 6, 15, 30)
    assert end_extended == datetime(2026, 10, 7, 15, 30)


def test_a_manual_end_does_not_move() -> None:
    manual = dict(planned_end=datetime(2026, 10, 9, 17), planned_end_manual=True)
    plain, extended = task_with(**manual), task_with(EXTRA, **manual)
    end_plain = Schedule(project_of(plain), {}).end(plain)
    end_extended = Schedule(project_of(extended), {}).end(extended)
    assert end_plain == end_extended == datetime(2026, 10, 9, 17)


def test_the_remaining_hours_count_the_extra_effort_with_the_progress_kept() -> None:
    now = datetime(2026, 10, 7, 12)
    plain = task_with(status=Status.RUNNING, progress=50)
    extended = task_with(EXTRA, status=Status.RUNNING, progress=50)
    assert remaining_hours(plain, project_of(plain), {}, now) == pytest.approx(6.5)
    assert remaining_hours(extended, project_of(extended), {}, now) == pytest.approx(
        9.75
    )


def test_decomposing_splits_the_total_and_leaves_no_history_on_the_summary() -> None:
    task = task_with(EXTRA)  # 合計 19.5h
    project = Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        sections=[Section("S", tasks=[task])],
    )
    parts = default_parts(task, 2)
    assert sum(part.effort_hours for part in parts) == pytest.approx(19.5)
    children = decompose(project, (0,), 0, parts, holidays={}, today=MON)
    summary = project.sections[0].tasks[0]
    assert summary.kind is TaskKind.SUMMARY and summary.extra_efforts == []
    assert sum(child.effort_hours for child in children) == pytest.approx(19.5)
    assert all(child.extra_efforts == [] for child in children)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_extra_effort_calc.py -q -n 0`
Expected: FAIL(完了予定・残りの工数・分解の各テストが、追加分を数えない)

- [ ] **Step 3: 参照を`total_effort`に替える**

次の置換を行う(各ファイルで`task.effort_hours`が Task のものだけを替える。`Part.effort_hours`・関数の引数名`effort_hours`・`replace(task, effort_hours=…)`は替えない):

```python
# remaining.py
def total_effort(task: Task) -> float:
    """タスクの工数の合計[h](もとの見積もり + 追加工数)。残りの工数・警告の判定・ダッシュボードの按分は、工数をここから取る。"""
    return task.total_effort
```

- `timeline.py:_own_end`: `task.effort_hours <= 0 or task.planned_end_manual` の`task.effort_hours`を`task.total_effort`に、`computed_end(start, task.effort_hours, …)`の第 2 引数も`task.total_effort`に。
- `reassign.py`: ファイル内の`task.effort_hours`をすべて`task.total_effort`に。
- `handoff.py`: 69・87・95・111 行目の`task.effort_hours`をすべて`task.total_effort`に。
- `decompose.py`: 63・82・125・149・182・190 行目の`task.effort_hours`をすべて`task.total_effort`に。
- `decompose_dialog.py`: 122・155 行目の`task.effort_hours`を`task.total_effort`に。
- `summary.py:66`: `_weight(child.effort_hours)`を`_weight(child.total_effort)`に。
- `dashboard.py:264`: `_weight(task.effort_hours)`を`_weight(task.total_effort)`に。
- `bottom_info.py:182-183`: `if task.effort_hours > 0: hours += task.effort_hours`を`total_effort`に(表示の 126 行目は Task 6 で扱う)。
- `decompose.py:326`の`effort_hours=0.0,`の次の行に`extra_efforts=[],`を足す(親のまとめに履歴を残さない)。

`grep -n "task.effort_hours\|child.effort_hours" src/projectapp/*.py`で、残りが`bulk_edit.py`・`forms.py`・`bottom_info.py:126`・`storage.py`・`merge.py`だけであることを確かめる。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest test/test_extra_effort_calc.py -q -n 0`
Expected: PASS

- [ ] **Step 5: smoke とコミット**

Run: `uv run pytest -m smoke -q`(PASS)、`uvx ruff format src test`
```bash
git add -A
git commit -m "feat: 完了予定・残りの工数・按分・分解を合計工数で数える(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 追加工数を足す処理(フォーム層)

**Files:**
- Modify: `src/projectapp/forms.py`(新しい関数と`build_task`・種別を変える 2 か所)
- Test: `test/test_forms.py`(なければ、既存の`build_task`のテストがあるファイルに追記。`grep -ln "build_task" test/*.py`で探す)

**Interfaces:**
- Consumes: Task 1 の`ExtraEffort`・定数。
- Produces:
  - `can_add_extra_effort(task: Task) -> bool`
  - `extra_effort_progress(task: Task, hours: float) -> int | None`
  - `add_extra_effort(task: Task, hours: float | None, reason: str, day: date) -> Task`
  - `ExtraEffortRow = tuple[str, float | None, str]`(日付の文字列, 時間, 理由)と`build_extra_efforts(rows: list[ExtraEffortRow]) -> list[ExtraEffort]`
  - `build_task(..., extra_efforts: list[ExtraEffort] | None = None)`(`None`は変えない)

- [ ] **Step 1: 失敗するテストを書く**

```python
from datetime import date

import pytest

from projectapp.forms import (
    add_extra_effort,
    build_extra_efforts,
    can_add_extra_effort,
    extra_effort_progress,
)
from projectapp.models import ExtraEffort, Status, Task, TaskKind

TODAY = date(2026, 10, 7)


def running(progress: int | None = 50, **kw: object) -> Task:
    return Task("a", effort_hours=10.0, status=Status.RUNNING, progress=progress, **kw)  # type: ignore[arg-type]


def test_adding_keeps_the_consumed_hours_by_lowering_the_progress() -> None:
    saved = add_extra_effort(running(50), 5.0, "見つかった", TODAY)
    assert saved.extra_efforts == [ExtraEffort(TODAY, 5.0, "見つかった")]
    assert saved.effort_hours == 10.0  # もとの見積もりは変えない
    assert saved.total_effort == 15.0
    assert saved.progress == 33  # 消化 5h は 15h の 33%


@pytest.mark.parametrize(("progress", "expected"), [(None, None), (0, 0), (100, 67)])
def test_the_progress_after_adding_stays_in_range(
    progress: int | None, expected: int | None
) -> None:
    assert extra_effort_progress(running(progress), 5.0) == expected


def test_a_second_addition_keeps_the_hours_consumed_so_far() -> None:
    once = add_extra_effort(running(50), 5.0, "", TODAY)
    twice = add_extra_effort(once, 15.0, "", TODAY)
    assert twice.total_effort == 30.0
    assert twice.progress == 17  # 消化 5h は 30h の約 17%


@pytest.mark.parametrize("hours", [None, 0, -1, float("inf"), float("nan"), 1.234])
def test_invalid_hours_are_rejected(hours: float | None) -> None:
    with pytest.raises(ValueError, match="追加工数|時間"):
        add_extra_effort(running(), hours, "", TODAY)


def test_the_reason_is_trimmed_and_checked() -> None:
    assert add_extra_effort(running(), 1.0, "  理由  ", TODAY).extra_efforts[0].reason == "理由"
    with pytest.raises(ValueError, match="理由"):
        add_extra_effort(running(), 1.0, "x" * 101, TODAY)
    with pytest.raises(ValueError, match="理由"):
        add_extra_effort(running(), 1.0, "a\u0007", TODAY)


@pytest.mark.parametrize(
    "task",
    [
        Task("工数なし", effort_hours=0.0),
        Task("終了", effort_hours=4.0, status=Status.DONE),
        Task("節目", kind=TaskKind.CHECKPOINT),
        Task("まとめ", kind=TaskKind.SUMMARY),
        Task("参照", kind=TaskKind.REFERENCE),
    ],
)
def test_extra_effort_cannot_be_added_to_these_tasks(task: Task) -> None:
    assert not can_add_extra_effort(task)
    with pytest.raises(ValueError, match="足せません"):
        add_extra_effort(task, 1.0, "", TODAY)


def test_the_history_is_limited() -> None:
    full = running(extra_efforts=[ExtraEffort(TODAY, 0.5)] * 200)
    with pytest.raises(ValueError, match="200"):
        add_extra_effort(full, 1.0, "", TODAY)


def test_build_extra_efforts_checks_each_row() -> None:
    rows = [("2026-10-07", 1.5, "a"), ("2026-10-08", 0.25, "")]
    assert build_extra_efforts(rows) == [
        ExtraEffort(date(2026, 10, 7), 1.5, "a"),
        ExtraEffort(date(2026, 10, 8), 0.25, ""),
    ]
    for bad in (
        [("2026-13-01", 1.0, "")],
        [("", 1.0, "")],
        [("2026-10-07", None, "")],
        [("2026-10-07", 0, "")],
        [("2026-10-07", 1.234, "")],
        [("2026-10-07", 1.0, "x" * 101)],
    ):
        with pytest.raises(ValueError, match="追加工数"):
            build_extra_efforts(bad)
```

同じファイルに、既存の`make`(`build_task`を呼ぶ補助関数)を使うテストも足す(import に`date`と`ExtraEffort`を足す):

```python
def test_build_task_keeps_or_replaces_the_extra_efforts() -> None:
    base = Task(
        "設計", effort_hours=8.0, extra_efforts=[ExtraEffort(date(2026, 10, 7), 2.0, "a")]
    )
    assert make(base).extra_efforts == base.extra_efforts  # 渡さなければ変えない
    other = [ExtraEffort(date(2026, 10, 8), 1.0)]
    assert make(base, extra_efforts=other).extra_efforts == other


def test_build_task_drops_the_extra_efforts_when_the_effort_is_cleared() -> None:
    base = Task(
        "設計", effort_hours=8.0, extra_efforts=[ExtraEffort(date(2026, 10, 7), 2.0)]
    )
    assert make(base, effort_hours=0.0).extra_efforts == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py -q -n 0 -k "extra"`(ファイル名は実際のものに合わせる)
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py`の import に`from datetime import date`(なければ)、`models`から`EXTRA_EFFORT_DECIMALS`・`MAX_EXTRA_EFFORTS`・`MAX_EXTRA_REASON`・`ExtraEffort`・`has_control_char`(なければ)を足し、`apply_quick_progress`の前に足す:

```python
ExtraEffortRow = tuple[str, float | None, str]  # (日付の文字列, 時間, 理由)


def can_add_extra_effort(task: Task) -> bool:
    """追加工数を足せるか。工数のある、終了していない通常タスクだけ。"""
    return (
        task.kind is TaskKind.NORMAL
        and isfinite(task.effort_hours)
        and task.effort_hours > 0
        and task.status is not Status.DONE
    )


def _check_extra_hours(hours: float | None) -> float:
    if hours is None:
        raise ValueError("追加工数の時間を入力してください")
    if not isfinite(hours) or hours <= 0:
        raise ValueError("追加工数の時間は0より大きい数値で入力してください")
    if exceeds_decimals(hours):
        raise ValueError(
            f"追加工数の時間は小数点以下{EXTRA_EFFORT_DECIMALS}桁までで入力してください"
        )
    return float(hours)


def _check_extra_reason(reason: str) -> str:
    clean = reason.strip()
    if has_control_char(clean):
        raise ValueError("追加工数の理由に使えない文字が含まれています")
    if len(clean) > MAX_EXTRA_REASON:
        raise ValueError(f"追加工数の理由は{MAX_EXTRA_REASON}文字以内で入力してください")
    return clean


def extra_effort_progress(task: Task, hours: float) -> int | None:
    """追加工数を足したあとの進捗度。消化時間を保つ(旧進捗度 × 旧合計 ÷ 新合計を丸める)。進捗度が未設定なら None。"""
    if task.progress is None:
        return None
    before = task.total_effort
    after = before + hours
    if not after > 0:
        return task.progress
    return min(MAX_PROGRESS, max(MIN_PROGRESS, round(task.progress * before / after)))


def add_extra_effort(task: Task, hours: float | None, reason: str, day: date) -> Task:
    """追加工数を 1 件足したコピーを返す。進捗度があれば、消化時間を保って直す。足せないタスク・不正な入力は ValueError。"""
    if not can_add_extra_effort(task):
        raise ValueError("このタスクには追加工数を足せません")
    if len(task.extra_efforts) >= MAX_EXTRA_EFFORTS:
        raise ValueError(f"追加工数は{MAX_EXTRA_EFFORTS}件までです")
    checked, clean = _check_extra_hours(hours), _check_extra_reason(reason)
    return replace(
        task,
        progress=extra_effort_progress(task, checked),
        extra_efforts=[*task.extra_efforts, ExtraEffort(day, checked, clean)],
    )


def build_extra_efforts(rows: list[ExtraEffortRow]) -> list[ExtraEffort]:
    """履歴の編集の入力を検証して、追加工数のリストにする(進捗度は直さない)。不正な入力は ValueError。"""
    if len(rows) > MAX_EXTRA_EFFORTS:
        raise ValueError(f"追加工数は{MAX_EXTRA_EFFORTS}件までです")
    efforts: list[ExtraEffort] = []
    for day_text, hours, reason in rows:
        try:
            day = date.fromisoformat(day_text.strip())
        except ValueError:
            raise ValueError("追加工数の日付は YYYY-MM-DD で入力してください") from None
        efforts.append(
            ExtraEffort(day, _check_extra_hours(hours), _check_extra_reason(reason))
        )
    return efforts
```

(`MAX_PROGRESS`・`MIN_PROGRESS`・`Status`・`TaskKind`は forms.py で import 済みか確認し、なければ足す。)

`build_task`: 引数に`extra_efforts: list[ExtraEffort] | None = None,`を足し、最後の`replace(base, …)`に次を足す:

```python
        extra_efforts=[]
        if hours <= 0
        else (base.extra_efforts if extra_efforts is None else extra_efforts),
```

種別を変えて工数を 0 にする 2 か所(`forms.py`の`effort_hours=0.0,`が 227 行目と 275 行目付近)に、それぞれ`extra_efforts=[],`を足す。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest test/test_forms.py -q -n 0`
Expected: PASS

- [ ] **Step 5: smoke とコミット**

Run: `uv run pytest -m smoke -q`(PASS)、`uvx ruff format src test`
```bash
git add -A
git commit -m "feat: 追加工数を足す処理(進捗度の再計算と検証)を足す(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 右クリックの`追加工数を足す…`

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`open_extra_effort_dialog`)、`src/projectapp/gantt.py`(`GanttActions.add_extra_effort`・メニュー項目・`open_menu`)、`src/projectapp/views.py`(`add_extra_effort`・配線)
- Test: `test/test_context_menu.py`、`test/test_gantt.py`(`Recorder`)、`test/test_views.py`

**Interfaces:**
- Consumes: Task 3 の`add_extra_effort`・`can_add_extra_effort`・`extra_effort_progress`。
- Produces: `task_dialog.open_extra_effort_dialog(task: Task, day: date, on_save: Callable[[Task], object]) -> None`、`GanttActions.add_extra_effort: Callable[[SectionPath, int], object]`、`MainView.add_extra_effort(path: SectionPath, index: int) -> None`。マーカー: `context-extra-effort`・`extra-hours`・`extra-reason`・`extra-note`・`extra-error`・`extra-save`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py`の`Recorder.__init__`の`GanttActions(...)`に、`decompose_task=…`の次の引数として足す:

```python
            add_extra_effort=lambda path, ti: self.events.append(
                ("add_extra_effort", (path, ti))
            ),
```

`test/test_context_menu.py`の`test_each_menu_item_acts_on_the_right_clicked_task`のパラメータに`("context-extra-effort", "add_extra_effort"),`を足す(`menu_project`の「通常」タスクは工数 0 で押せないので、`menu_project`の「通常」に`effort_hours=4.0`を足す)。末尾に追記する:

```python
async def test_extra_effort_is_enabled_only_for_a_task_that_can_take_it(
    user: User,
) -> None:
    charts, _ = mount_chart(menu_project())
    await user.open("/")
    item = user.find(marker="context-extra-effort").elements.pop()
    charts[0].open_menu((0,), 1)  # 実行中だが工数がない
    assert item.props.get("disable") is True
    charts[0].open_menu((0,), 0)  # 工数 4h の通常タスク
    assert not item.props.get("disable")
```

`test/test_views.py`の`test_the_quick_progress_dialog_saves_one_undo_step`の次に追記する:

```python
async def test_the_extra_effort_dialog_saves_one_undo_step_and_lowers_the_progress(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    view.save_task(path, index, replace(task, effort_hours=10.0, progress=50, status=Status.RUNNING))
    view.now = lambda: datetime(2026, 10, 7, 12)
    with user.client:
        view.add_extra_effort(path, index)
    await user.should_see(marker="extra-hours")
    with user.client:
        user.find(marker="extra-hours").elements.pop().set_value(5)
        user.find(marker="extra-reason").elements.pop().set_value("見つかった")
    assert "50% → 33%" in text_of(user, "extra-note")
    user.find(marker="extra-save").click()
    saved = view.tasks_in(path)[index]
    assert saved.extra_efforts[0].hours == 5.0
    assert saved.extra_efforts[0].day == date(2026, 10, 7)
    assert (saved.effort_hours, saved.total_effort, saved.progress) == (10.0, 15.0, 33)
    with user.client:
        view.undo()
    undone = view.tasks_in(path)[index]
    assert (undone.extra_efforts, undone.progress) == ([], 50)  # 元に戻す 1 ステップ


async def test_the_extra_effort_dialog_does_not_open_for_a_finished_task(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path, with_task=False)
    view.project.tasks = [Task("終了", effort_hours=4.0, status=Status.DONE)]
    with user.client:
        view.add_extra_effort((), 0)
    await user.should_not_see(marker="extra-hours")
```

(`replace`・`date`・`datetime`・`Status`は`test_views.py`で import 済みか確認し、なければ足す。`text_of`は同ファイルの既存のヘルパー。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_context_menu.py test/test_views.py -q -n 0 -k "extra_effort"`
Expected: FAIL

- [ ] **Step 3: 小ダイアログを実装する**

`src/projectapp/task_dialog.py`の`open_quick_progress_dialog`の次に足す(import に`add_extra_effort`・`extra_effort_progress`を`projectapp.forms`から、`date`を`datetime`から足す):

```python
def open_extra_effort_dialog(
    task: Task, day: date, on_save: Callable[[Task], object]
) -> None:
    """右クリックの`追加工数を足す…`で開く、時間と理由だけの小さなダイアログ。進捗度があれば、消化時間を保って直す(変化を見せる)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label(task.name).classes("text-h6 ellipsis").mark("extra-title")
        ui.label(f"今の工数 {task.total_effort:g}h").classes(
            "text-caption text-grey"
        ).mark("extra-current")
        hours = (
            ui.number("追加する時間(h)", value=None, min=0, step=0.5)
            .classes("w-full")
            .mark("extra-hours")
        )
        reason = ui.input("理由(任意)").classes("w-full").mark("extra-reason")
        note = ui.label("").classes("text-caption text-grey").mark("extra-note")
        error = ui.label("").classes("text-negative").mark("extra-error")

        def refresh(_event: object = None) -> None:
            value = hours.value
            if not value or not isfinite(value) or value <= 0:
                note.set_text("")
                return
            text = f"合計 {task.total_effort:g}h → {task.total_effort + value:g}h"
            after = extra_effort_progress(task, value)
            if after is not None and after != task.progress:
                text += f"・進捗度 {task.progress}% → {after}%"
            note.set_text(text)

        hours.on_value_change(refresh)

        def save() -> None:
            try:
                saved = add_extra_effort(task, hours.value, reason.value or "", day)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            dialog.close()
            on_save(saved)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("追加", on_click=save).mark("extra-save")
    dialog.open()
```

- [ ] **Step 4: メニューと配線を実装する**

`src/projectapp/gantt.py`:
1. `GanttActions`の`decompose_task`の次に足す:

```python
    add_extra_effort: Callable[[SectionPath, int], object] = lambda path, ti: (
        None
    )  # 右クリック: 追加工数を足す
```

2. `__init__`の`self.decompose_item: ui.menu_item | None = None`の次に`self.extra_effort_item: ui.menu_item | None = None`を足す。
3. `build_menu`の`context-decompose`の項目の次に足す:

```python
            self.extra_effort_item = ui.menu_item(
                "追加工数を足す…",
                on_click=act(lambda p, t: self.actions.add_extra_effort(p, t)),
            ).mark("context-extra-effort")
```

4. `open_menu`の`self.decompose_item.props(…)`の次に足す(`can_add_extra_effort`は`projectapp.forms`から import。`gantt.py`が forms を import できない場合〔循環〕は、判定を`models`側の関数にせず、`task.kind is TaskKind.NORMAL and task.effort_hours > 0 and task.status is not Status.DONE`をその場に書く):

```python
        if self.extra_effort_item is not None:
            task = tasks[ti] if ti < len(tasks) else None
            can = task is not None and can_add_extra_effort(task)
            self.extra_effort_item.props(
                add="" if can else "disable", remove="disable" if can else ""
            )
```

`src/projectapp/views.py`:
1. `GanttActions(...)`の組み立て(`edit_progress=self.edit_progress,`の行の近く)に`add_extra_effort=self.add_extra_effort,`を足す。
2. `edit_progress`の次にメソッドを足す(import に`open_extra_effort_dialog`と`can_add_extra_effort`を足す):

```python
    def add_extra_effort(self, path: SectionPath, index: int) -> None:
        """右クリックの`追加工数を足す…`。足せる通常タスクだけ、時間と理由の小さなダイアログを開く(保存は元に戻す 1 ステップ)。"""
        if not arrange.has_task(self.project, (path, index)):
            return
        task = self.tasks_in(path)[index]
        if not can_add_extra_effort(task):
            return
        open_extra_effort_dialog(
            task,
            self.now().date(),
            lambda saved: self.save_task(path, index, saved),
        )
```

- [ ] **Step 5: テストが通ることを確かめる**

Run: `uv run pytest test/test_context_menu.py test/test_gantt.py test/test_views.py -q -n 0 -k "extra_effort or context"`
Expected: PASS

- [ ] **Step 6: smoke とコミット**

Run: `uv run pytest -m smoke -q`(PASS)、`uvx ruff format src test`
```bash
git add -A
git commit -m "feat: 右クリックから追加工数を足せるようにする(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 編集ダイアログの補足と履歴の修正・削除

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`open_extra_effort_history_dialog`・`open_task_dialog`)
- Test: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 3 の`build_extra_efforts`・`ExtraEffortRow`・`build_task(extra_efforts=)`。
- Produces: `task_dialog.open_extra_effort_history_dialog(efforts: list[ExtraEffort], base_hours: float, on_apply: Callable[[list[ExtraEffort]], object]) -> None`。マーカー: `task-extra-box`・`task-extra-note`・`task-extra-history`・`extra-history-row-{n}`・`extra-history-day-{n}`・`extra-history-hours-{n}`・`extra-history-reason-{n}`・`extra-history-delete-{n}`・`extra-history-error`・`extra-history-ok`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py`の import に`ExtraEffort`(`projectapp.models`)と`replace`(`dataclasses`)を足し、末尾に追記する(`mount_dialog`・`open_dialog`は既存):

```python
EXTRA_TASK = Task(
    "設計",
    effort_hours=10.0,
    extra_efforts=[ExtraEffort(date(2026, 10, 7), 5.0, "見落とし")],
)


async def test_the_edit_dialog_shows_the_extra_effort_note(user: User) -> None:
    mount_dialog(EXTRA_TASK, [])
    await open_dialog(user)
    await user.should_see(marker="task-extra-box")
    note = user.find(marker="task-extra-note").elements.pop().text
    assert note == "もとの見積もり 10h。追加 +5h で合計 15h"


async def test_the_extra_effort_box_needs_a_normal_task_with_an_effort(
    user: User,
) -> None:
    mount_dialog(Task("工数なし"), [])
    await open_dialog(user)
    await user.should_not_see(marker="task-extra-box")


async def test_the_history_dialog_edits_the_hours_and_keeps_the_progress(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(replace(EXTRA_TASK, progress=40, status=Status.RUNNING), saved)
    await open_dialog(user)
    user.find(marker="task-extra-history").click()
    await user.should_see(marker="extra-history-row-0")
    with user.client:
        user.find(marker="extra-history-hours-0").elements.pop().set_value(2)
    user.find(marker="extra-history-ok").click()
    user.find(marker="task-save").click()
    assert saved[0].extra_efforts[0].hours == 2.0
    assert saved[0].progress == 40  # 履歴を直しても進捗度は変えない


async def test_the_history_dialog_can_delete_a_row(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(EXTRA_TASK, saved)
    await open_dialog(user)
    user.find(marker="task-extra-history").click()
    await user.should_see(marker="extra-history-row-0")
    user.find(marker="extra-history-delete-0").click()
    user.find(marker="extra-history-ok").click()
    user.find(marker="task-save").click()
    assert saved[0].extra_efforts == []


async def test_the_history_dialog_rejects_zero_hours_and_stays_open(
    user: User,
) -> None:
    mount_dialog(EXTRA_TASK, [])
    await open_dialog(user)
    user.find(marker="task-extra-history").click()
    await user.should_see(marker="extra-history-row-0")
    with user.client:
        user.find(marker="extra-history-hours-0").elements.pop().set_value(0)
    user.find(marker="extra-history-ok").click()
    assert "追加工数" in user.find(marker="extra-history-error").elements.pop().text
    await user.should_see(marker="extra-history-ok")  # 閉じない
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -n 0 -k "extra"`
Expected: FAIL

- [ ] **Step 3: 履歴ダイアログを実装する**

`src/projectapp/task_dialog.py`の`open_extra_effort_dialog`の次に足す(import に`build_extra_efforts`・`ExtraEffort`を足す):

```python
def open_extra_effort_history_dialog(
    efforts: list[ExtraEffort],
    base_hours: float,
    on_apply: Callable[[list[ExtraEffort]], object],
) -> None:
    """編集ダイアログの`履歴…`。追加工数の日付・時間・理由を直し、行を消す(進捗度は直さない)。OK で on_apply に渡す。"""
    rows: list[dict[str, object]] = []
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[32rem]"):
        ui.label("追加工数の履歴").classes("text-h6")
        ui.label(f"もとの見積もり {base_hours:g}h").classes(
            "text-caption text-grey"
        ).mark("extra-history-base")
        box = ui.column().classes("w-full gap-1")
        error = ui.label("").classes("text-negative").mark("extra-history-error")

        def add_row(effort: ExtraEffort) -> None:
            number = len(rows)
            with box:
                with ui.row().classes("w-full items-center no-wrap").mark(
                    f"extra-history-row-{number}"
                ) as line:
                    day = ui.input("日付", value=effort.day.isoformat()).classes("w-32")
                    day.mark(f"extra-history-day-{number}")
                    hours = ui.number("時間(h)", value=effort.hours, min=0, step=0.5)
                    hours.classes("w-24").mark(f"extra-history-hours-{number}")
                    reason = ui.input("理由", value=effort.reason).classes("grow")
                    reason.mark(f"extra-history-reason-{number}")
                    remove = ui.button(icon="delete").props("flat dense")
                    remove.mark(f"extra-history-delete-{number}")
            item: dict[str, object] = {
                "line": line, "day": day, "hours": hours, "reason": reason,
            }
            rows.append(item)

            def delete() -> None:
                line.delete()
                rows.remove(item)

            remove.on_click(delete)

        for effort in efforts:
            add_row(effort)

        def apply() -> None:
            try:
                built = build_extra_efforts(
                    [
                        (str(r["day"].value), r["hours"].value, str(r["reason"].value or ""))  # type: ignore[attr-defined]
                        for r in rows
                    ]
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            dialog.close()
            on_apply(built)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("OK", on_click=apply).mark("extra-history-ok")
    dialog.open()
```

(行の削除後に番号が飛んでもよい。マーカーは行の作成時の番号のまま。)

- [ ] **Step 4: 編集ダイアログに補足とボタンを足す**

`open_task_dialog`の中で:

1. `conversion = ui.label("")…mark("task-conversion")`の次(同じ`with basic_box:`の中)に足す:

```python
            extra_state: dict[str, list[ExtraEffort]] = {
                "items": list(initial.extra_efforts)
            }
            with ui.column().classes("w-full gap-1") as extra_box:
                extra_note = (
                    ui.label("").classes("text-caption text-grey").mark("task-extra-note")
                )
                ui.button(
                    "追加工数の履歴…",
                    icon="history",
                    on_click=lambda: open_extra_effort_history_dialog(
                        extra_state["items"],
                        effort.value or 0.0,
                        apply_extra,
                    ),
                ).props("flat dense no-caps").mark("task-extra-history")
            extra_box.mark("task-extra-box")
```

2. `on_effort_change`の前に足す:

```python
        def refresh_extra() -> None:
            """補足と表示を更新する。追加のあるときだけ、もとの見積もりと合計を出す。通常タスクで工数のあるときだけ見せる。"""
            items = extra_state["items"]
            base_hours = effort.value or 0.0
            added = sum(e.hours for e in items)
            extra_note.set_text(
                f"もとの見積もり {base_hours:g}h。追加 +{added:g}h で合計 {base_hours + added:g}h"
                if items
                else ""
            )
            normal = not is_summary and kind.value not in (
                TaskKind.CHECKPOINT,
                TaskKind.REFERENCE,
            )
            extra_box.set_visibility(normal and base_hours > 0)

        def apply_extra(items: list[ExtraEffort]) -> None:
            extra_state["items"] = items
            refresh_extra()

        refresh_extra()
```

`on_effort_change`の末尾に`refresh_extra()`を足す。

3. `refresh_visibility`の最初の文として`refresh_extra()`を呼ぶ(種別を切り替えたときに、補足の表示を決め直す。`extra_box`は、ほかの欄のリストには入れない)。
4. `current()`の末尾に`tuple(extra_state["items"]),`を足す。
5. `build_task(...)`の引数に`extra_efforts=extra_state["items"],`を足す。

- [ ] **Step 5: テストが通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -n 0`
Expected: PASS

- [ ] **Step 6: smoke とコミット**

Run: `uv run pytest -m smoke -q`(PASS)、`uvx ruff format src test`
```bash
git add -A
git commit -m "feat: 編集ダイアログで追加工数の履歴を直せるようにする(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 下部パネルの詳細に、追加工数を出す

**Files:**
- Modify: `src/projectapp/bottom_info.py:126`
- Test: `test/test_bottom_info.py`

**Interfaces:**
- Consumes: Task 1 の`Task.total_effort`。
- Produces: 詳細の`工数`の行が、追加があるとき`18.0h(もと 13.0h + 追加 5.0h)`のようになる。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_bottom_info.py`の import に`ExtraEffort`・`date`を足し、`test_detail_lists_status_crew_dates_effort_and_progress`の次に追記する(`planned`・`env`・`NOW`は既存):

```python
def test_detail_shows_the_extra_effort_breakdown() -> None:
    task = planned("設計", extra_efforts=[ExtraEffort(date(2026, 10, 7), 5.0)])
    project, schedule = env(task)
    lines = dict(task_detail(task, project, {}, NOW, schedule).lines)
    assert lines["工数"] == "18.0h(もと 13.0h + 追加 5.0h)"
```

追加なしの`13.0h`は既存のテストが、工数 0 の`—`は既存の「工数なし」のテストが確かめている。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_bottom_info.py -q -n 0 -k "extra"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`bottom_info.py:126`を次に置き換える:

```python
        ("工数", _effort_text(task)),
```

同ファイルの上の方(他の補助関数の近く)に足す:

```python
def _effort_text(task: Task) -> str:
    """詳細の工数。追加工数があるときは、もとの見積もりと追加の内訳も出す。"""
    if task.total_effort <= 0:
        return DASH
    if not task.extra_efforts:
        return f"{task.total_effort:.1f}h"
    extra = task.total_effort - task.effort_hours
    return f"{task.total_effort:.1f}h(もと {task.effort_hours:.1f}h + 追加 {extra:.1f}h)"
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest test/test_bottom_info.py -q -n 0`
Expected: PASS

- [ ] **Step 5: smoke とコミット**

Run: `uv run pytest -m smoke -q`(PASS)、`uvx ruff format src test`
```bash
git add -A
git commit -m "feat: 下部パネルの詳細に追加工数の内訳を出す(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 文書・確認用データ・仕上げ

**Files:**
- Modify: `docs/superpowers/specs/2026-11-02-extra-effort-design.md`(実装との差を直す)
- Modify: `.claude/spec/gantt.md`・`.claude/spec/project-files.md`・`.claude/spec/dashboard.md`(該当箇所)・`CLAUDE.md`(`version`を 20 に)
- Modify: `docs/requests.md`・`docs/request-history.md`(要望 105 の状態)
- Create: `docs/samples/追加工数の確認.json`
- Modify: `docs/samples/遅れの取り戻し確認C(タスクごとの期限).json`(メンバーの不備を直した再生成。すでに作業ツリーにある変更をコミットする)

- [ ] **Step 1: 設計書を実装に合わせて直す**

`2026-11-02-extra-effort-design.md`:
- `ExtraEffort(id, date, hours, reason)` → `ExtraEffort(day, hours, reason)`(`id`なし。日付のキーは`day`)。
- 3 者マージ: `id`ごとのマージ → 項目まるごと(`actuals`・`urls`と同じ。両方の側が変えたら衝突)。
- 編集ダイアログ: `追加工数`の節 → 基本の節の補足とボタン`追加工数の履歴…`(サブダイアログ)。
- 追加できるタスクに、`状態が終了でない`を足す。
- 書き出しの項(担当者向けファイルは合計工数)。PlantUML・CSV/TSV は工数を出していないので、変更なし。

- [ ] **Step 2: `.claude/spec/`と`CLAUDE.md`を更新する**

`.claude/spec/gantt.md`に、右クリックの`追加工数を足す…`(対象・進捗度の再計算・元に戻す 1 ステップ)と、編集ダイアログの`追加工数の履歴…`を書く。`.claude/spec/project-files.md`の形式の項に`version` 20(タスクの`extra_efforts`)を書く。`.claude/spec/dashboard.md`・`concept.md`のうち、工数を説明している箇所に「合計工数 = もとの見積もり + 追加工数」を書く。`CLAUDE.md`の`version`(現在 19)を 20 にする(200 行以内を保つ)。

- [ ] **Step 3: 確認用データを作る**

スクラッチパッドのスクリプト(コミットしない)で`docs/samples/追加工数の確認.json`を作る。基準日 2026-11-02(月)、メンバー田中・鈴木(担当は`Assignee("田中", 1.0)`のように**名前**で渡す)。タスク: ① 実行中・工数 10h・進捗 50%・追加なし(右クリックで足して 50% → 33% を見る)、② 未着手・工数 13h・追加 6.5h「仕様の見落とし」1 件(完了予定が 1 日延びる・下部パネルの内訳・履歴の編集を見る)、③ 完了予定を手で指定・工数 13h・追加 6.5h(完了予定が動かない)、④ 終了・工数 4h(メニューが押せない)、⑤ 工数なしの通常タスク(同上)。生成後、`parse_project`で読み戻せること、メンバーが 2 人だけであることを確かめる。

- [ ] **Step 4: 要望の状態を更新する**

`docs/requests.md`の要望 105 の状態を「実装済み(2026-11-02。ブランチ`feature/extra-effort`。実機確認待ち)」に直し、決定(履歴のリスト・進捗度は消化時間を保つ・右クリックと履歴ダイアログ・マージは項目まるごと・終了済みは対象外・設計書と計画へのリンク・確認用データ)を書く。`docs/request-history.md`の 105 の行も更新する。

- [ ] **Step 5: 全体の確認**

Run: `uvx ruff check`(All checks passed)、`uvx ruff format src test`、`uv run pytest -m smoke -q`(PASS)、`uvx ty check src`(`days_text`の 1 件だけ)
smoke が失敗したときだけ、`uv run pytest -n auto`。

- [ ] **Step 6: コミットと PR**

```bash
git add -A
git commit -m "docs: 追加工数の仕様・確認用データ・要望の状態を更新する(要望 105)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/extra-effort
gh pr create --base develop --title "feat: 後から追加工数を足せるようにする(要望 105)" --body "…(概要・確認・確認用データ・マージは実機確認後の指示待ち。末尾に 🤖 Generated with [Claude Code](https://claude.com/claude-code))"
```

その後、最終レビュー(レビュアーは`sonnet`を指定)を回し、指摘を利用者に報告する。マージは利用者の指示を待つ。
