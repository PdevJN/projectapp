# タスクの進捗度 Implementation Plan

> **状態**: 実装済み — 要望 38 — マージ PR #22(3fe89a3。2026-10-16)。設計書は [`2026-10-16-task-progress-design.md`](../specs/2026-10-16-task-progress-design.md)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。
> **後の変更**: 区間の進捗度の優先と、欄の読み取り専用の仕様は廃止(PR #35)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 進捗度を、実績の区間に紐づけずに、タスクそのものの値(`Task.progress`)として持てるようにし、PlantUML の取り込みでも進捗度を取り込む。

**Architecture:** `Task.progress: int | None` を新設し(ファイル形式 version 5)、`timeline.current_progress` が「最後に進捗度の入っている区間の値 → なければ `Task.progress`」を返す。塗り・チップ・遅れの判定・ダッシュボード・PlantUML 出力は、この関数を通しているので変えない。編集ダイアログには入力欄を足し、区間に進捗度があるときは読み取り専用で区間の値を示す(保存では `Task.progress` を変えない)。`merge.py` は、`Task` の項目を一般的にほどいているので、表示名を足すだけ。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、ty(`uv run ty check src`)。

**Spec:** `docs/superpowers/specs/2026-10-16-task-progress-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。コードの識別子は英語。
- コード規約(`.claude/RULE.md`): すべての関数に型引数と戻り値の型ヒントを付ける。コメントの説明は多くても 3 行以内。型の検証は `ty`。
- `Task.progress` は 0〜100 の整数か `None`。ファイル形式は version 5(`models.FORMAT_VERSION`)。キーのない古いファイルは `None`。`progress` のキーは version 5 以上でだけ読み、version 4 以下の同名のキーは無視する。範囲外・整数以外・真偽値は読込を拒否する。
- チェックポイントは進捗度を持たない(読込で `None` にする。ダイアログに欄を出さない。保存で `None`)。
- 現在の進捗度: 進捗度の入っている最後の区間の値(0 は入力あり)→ なければ `Task.progress` → なければ `None`。
- 状態と進捗度は連動させない。区間の進捗度は廃止しない。
- 完了の確認は `uv run pytest -n auto` と `uv run ty check src`。コミットメッセージは日本語で、末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。ブランチは `feature/task-progress`。

## Review Focus

- `Task.progress` と区間の進捗度が食い違う(`Task.progress=10`・区間 60%): 区間が勝つ。区間の進捗度を消すと、`Task.progress` に戻る(Task 1・Task 3)。
- 区間に進捗度があるときにダイアログを保存: 読み取り専用の欄の値が `Task.progress` に書き込まれない(Task 3)。
- 手編集のファイルの不正な `progress`(`true`・`40.5`・`"40"`・`101`): 開けないが、落ちずにエラーになる。version 4 以下のファイルの `progress` は無視する(Task 1)。
- 通常タスクを `Task.progress` つきで保存したあと、チェックポイントに切り替えて保存: `progress` が `None` になる(Task 2・Task 3)。
- PlantUML の `is 0% completed`・`is 100% completed`(チェックポイント含む): 0 は `None`、100 は終了かつ `progress=100`、チェックポイントは `None`(Task 4)。

---

### Task 1: データ(モデル・ファイル形式・現在の進捗度・マージの表示名)

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION`、`Task`)
- Modify: `src/projectapp/storage.py`(`_progress`、`_task`、`_checkpoint`)
- Modify: `src/projectapp/timeline.py`(`current_progress`)
- Modify: `src/projectapp/merge.py`(`TASK_LABELS`)
- Modify: `test/test_storage.py`・`test/test_timeline.py`・`test/test_merge.py`・`test/test_dashboard.py`・`test/test_gantt.py`

**Interfaces:**
- Consumes: 既存の `Actual`・`MIN_PROGRESS`・`MAX_PROGRESS`・`_checkpoint`。
- Produces: `Task.progress: int | None = None`(`Task` の最後の項目)、`FORMAT_VERSION = 5`、`storage._progress(value: Any, label: str = "実績の進捗度") -> int | None`、`timeline.current_progress(task: Task) -> int | None`(上の優先順位)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py`: 既存の 3 か所の `4` を 5 に直す(773 行目付近の `raw["version"] == 4 and len(raw["categories"]) == 2`、794 行目付近の `raw["version"] == 4`、1302 行目付近の `raw["version"] == FORMAT_VERSION == 4`)。`models` の import に `TaskKind` がなければ足す。次のテストを `test_progress_boundaries_are_accepted` の次に足す:

```python
@pytest.mark.parametrize("value", [None, 0, 40, 100])
def test_task_progress_roundtrip(tmp_path: Path, value: int | None) -> None:
    loaded = load_project(save_project(Project("p", tasks=[Task("t", progress=value)]), tmp_path))
    assert loaded.tasks[0].progress == value


def _rewrite_task(path: Path, **changes: object) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0].update(changes)
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_file_without_task_progress_loads_as_none(tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("t", progress=40)]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["tasks"][0]["progress"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].progress is None


@pytest.mark.parametrize("bad", [True, False, 40.5, 40.0, "40", -1, 101, [40]])
def test_invalid_task_progress_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("p", tasks=[Task("t")]), tmp_path)
    _rewrite_task(path, progress=bad)
    with pytest.raises(ValueError, match="進捗度"):
        load_project(path)


def test_progress_key_in_a_version_4_file_is_ignored(tmp_path: Path) -> None:
    path = save_project(Project("p", tasks=[Task("t")]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 4
    raw["tasks"][0]["progress"] = 40
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].progress is None


def test_a_checkpoint_loads_without_progress(tmp_path: Path) -> None:
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 20, 17, 0))
    path = save_project(Project("p", tasks=[checkpoint]), tmp_path)
    _rewrite_task(path, progress=50)
    assert load_project(path).tasks[0].progress is None
```

`test/test_timeline.py`: `current_progress` のテストの次に足す:

```python
def test_current_progress_falls_back_to_the_task_value() -> None:
    assert current_progress(Task("t", progress=40)) == 40
    assert current_progress(Task("t", progress=0)) == 0
    assert current_progress(Task("t", actuals=[Actual(datetime(2026, 10, 5, 9))], progress=30)) == 30


def test_current_progress_prefers_the_actual_intervals() -> None:
    task = Task("t", progress=10, actuals=[Actual(datetime(2026, 10, 5, 9), None, 60)])
    assert current_progress(task) == 60
    task.actuals[0].progress = None
    assert current_progress(task) == 10
```

`test/test_merge.py`: `test_same_field_changed_differently_is_a_conflict` の次に足す:

```python
def test_task_progress_merges_field_by_field() -> None:
    base = proj(tasks=[task("a", "t1")])
    ours = proj(tasks=[task("a", "t1", progress=40)])
    theirs = proj(tasks=[task("a", "t1", effort_hours=2.0)])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert (merged.project.tasks[0].progress, merged.project.tasks[0].effort_hours) == (40, 2.0)


def test_task_progress_changed_differently_is_a_conflict_with_a_readable_label() -> None:
    base = proj(tasks=[task("a", "t1", progress=10)])
    ours = proj(tasks=[task("a", "t1", progress=40)])
    theirs = proj(tasks=[task("a", "t1", progress=70)])
    (conflict,) = merge_projects(base, ours, theirs).conflicts
    assert (conflict.field, conflict.ours, conflict.theirs) == ("進捗度", 40, 70)
```

`test/test_dashboard.py`: `test_progress_is_the_effort_weighted_average` の次に足す:

```python
def test_progress_uses_the_task_value_without_actuals() -> None:
    task = Task("A", effort_hours=10, status=Status.RUNNING, progress=50)
    assert summarize_progress(project_of(task), {}, NOW).percent == pytest.approx(50)
```

`test/test_gantt.py`: `fill_percent(Task("t", actuals=[Actual(datetime(2026, 10, 5, 9), None, 40)])) == 40` を含むテストの次に足す:

```python
def test_fill_percent_uses_the_task_progress() -> None:
    assert fill_percent(Task("t", progress=40)) == 40
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_storage.py test/test_timeline.py test/test_merge.py test/test_dashboard.py test/test_gantt.py -q -n auto`
Expected: FAIL(`Task` が `progress` を受け取らない `TypeError`、バージョンが 4 のまま)

- [ ] **Step 3: 実装する**

`src/projectapp/models.py`: `FORMAT_VERSION = 4` を `5` にし、コメントの括弧の末尾に `。5: タスクの進捗度` を足す。`Task` の最後(`urls` の次)に足す:

```python
    progress: int | None = None  # タスクの進捗度(0〜100%)。実績の区間に進捗度があれば、そちらを優先する
```

`src/projectapp/storage.py`: `_progress` を差し替える:

```python
def _progress(value: Any, label: str = "実績の進捗度") -> int | None:
    """進捗度を読む。null・キーなしは未入力。整数(boolは不可)で0〜100。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label}が整数ではありません")
    if not MIN_PROGRESS <= value <= MAX_PROGRESS:
        raise ValueError(f"{label}は{MIN_PROGRESS}〜{MAX_PROGRESS}で指定してください")
    return value
```

`_task` の `Task(...)` に、`urls=...` の次の行として足す:

```python
        progress=_progress(raw.get("progress"), "進捗度") if ctx.version >= 5 else None,
```

`_checkpoint` の `replace(` に `progress=None,` を足す(`actuals=[],` の次)。docstring の「使わない項目(…)」に「進捗度」を足す。

`src/projectapp/timeline.py`: `current_progress` を差し替える:

```python
def current_progress(task: Task) -> int | None:
    """進捗度の入っている最後の区間の値(累積)。なければ、タスクの進捗度。どちらもなければ None。0 は入力ありとして返す。"""
    for actual in reversed(task.actuals):
        if actual.progress is not None:
            return actual.progress
    return task.progress
```

`src/projectapp/merge.py`: `TASK_LABELS` に `"progress": "進捗度",` を足す(`"actuals": "実績"` の次)。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS、ty はエラーなし

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/models.py src/projectapp/storage.py src/projectapp/timeline.py src/projectapp/merge.py test/
git commit -m "$(cat <<'EOF'
feat: タスクの進捗度を持てるようにする(ファイル形式 version 5)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: フォームの検証(`build_task`)

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task`、`_build_checkpoint`)
- Modify: `test/test_forms.py`

**Interfaces:**
- Consumes: Task 1 の `Task.progress`。既存の `_check_progress(value: float | None) -> int | None`。
- Produces: `build_task(..., progress: float | None = None, ...)`(既定は `None` = 空。通常タスクは `_check_progress` を通した値を `Task.progress` に入れる。チェックポイントは常に `None`)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の `test_bad_progress_is_rejected` の次に足す:

```python
def test_the_task_progress_is_saved_apart_from_the_actuals() -> None:
    task = make(progress=40)
    assert task.progress == 40 and task.actuals == []


def test_the_task_progress_accepts_zero_hundred_and_empty() -> None:
    assert make(progress=0).progress == 0
    assert make(progress=100.0).progress == 100
    assert make(Task("t", progress=40), progress=None).progress is None


@pytest.mark.parametrize("bad", [-1, 101, 40.5, float("nan"), float("inf")])
def test_a_bad_task_progress_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="進捗度"):
        make(progress=bad)


def test_the_task_progress_does_not_touch_the_actual_progress() -> None:
    task = make(progress=10, actual_start="2026-10-05T09:00", actual_progress=60)
    assert (task.progress, task.actuals[0].progress) == (10, 60)


def test_a_checkpoint_drops_the_task_progress() -> None:
    task = make(
        Task("t", progress=40),
        kind=TaskKind.CHECKPOINT,
        deadline="2026-10-09T17:00",
        status=Status.NOT_STARTED,
        progress=40,
    )
    assert task.progress is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py -q -n auto -k task_progress`
Expected: FAIL(`build_task() got an unexpected keyword argument 'progress'`)

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py` の `build_task`: 引数に、`actual_rows` の次の行として `progress: float | None = None,` を足す。docstring の末尾に「`progress` はタスクの進捗度(区間の進捗度とは別)」を足す。通常タスクの `replace(` に `progress=task_progress,` を足し、その直前(`links = _links(...)` の次の行)に次を足す:

```python
    task_progress = _check_progress(progress)
```

`_build_checkpoint` の `replace(` に `progress=None,` を足す(`planned_end_manual=False,` の次)。`docstring` の「開始予定・工数・担当・実績」に「進捗度」を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py -q -n auto && uv run ty check src`
Expected: PASS、ty はエラーなし

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "$(cat <<'EOF'
feat: build_task でタスクの進捗度を検証して保存する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 編集ダイアログの進捗度の欄

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`ActualFields`・`IntervalFields`・新しい `TaskProgressField`・`open_task_dialog`)
- Modify: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 の `Task.progress`、Task 2 の `build_task(progress=...)`。既存の `ActualFields.progress`(`ui.number`)・`IntervalFields._rows`(各行の `progress: ui.number`)・`bind`。
- Produces:
  - `ActualFields.interval_progress(self) -> float | None`・`IntervalFields.interval_progress(self) -> float | None`: 区間の進捗度(入っている最後のものの値。なければ `None`)。`ActualFields` は、2 件以上で読み取り専用のときも、保持している区間の最後の値を返す。
  - `TaskProgressField(own: int | None)`(`container`・`input`・`hint`・`own`・`sync(interval: float | None) -> None`・`state() -> tuple[object, ...]`)。マーカー: 欄 `task-progress`、説明 `task-progress-hint`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` の `test_two_actuals_keep_their_progress_and_hide_the_input` の次に足す:

```python
def task_progress_input(user: User):  # noqa: ANN202
    return user.find(marker="task-progress").elements.pop()


async def test_the_task_progress_is_entered_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    task_progress_input(user).set_value(40)
    user.find(marker="task-save").click()
    assert saved[0].progress == 40 and saved[0].actuals == []


async def test_the_existing_task_progress_is_shown_and_can_be_cleared(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", progress=70), saved)
    await open_dialog(user)
    assert task_progress_input(user).value == 70
    task_progress_input(user).set_value(None)
    user.find(marker="task-save").click()
    assert saved[0].progress is None


async def test_an_interval_progress_is_shown_read_only_and_the_task_value_is_kept(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", progress=10, actuals=[Actual(datetime(2026, 10, 5, 9, 0), None, 60)])
    mount_dialog(task, saved)
    await open_dialog(user)
    field = task_progress_input(user)
    assert field.value == 60 and not field.enabled
    await user.should_see(marker="task-progress-hint")
    user.find(marker="task-save").click()
    assert saved[0].progress == 10 and saved[0].actuals[0].progress == 60


async def test_the_field_returns_to_the_task_value_when_the_interval_progress_is_cleared(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", progress=10, actuals=[Actual(datetime(2026, 10, 5, 9, 0), None, 60)])
    mount_dialog(task, saved)
    await open_dialog(user)
    progress_input(user).set_value(None)
    field = task_progress_input(user)
    assert field.value == 10 and field.enabled
    await user.should_not_see(marker="task-progress-hint")
    field.set_value(20)
    user.find(marker="task-save").click()
    assert saved[0].progress == 20


async def test_the_interval_mode_reads_the_last_entered_interval(user: User) -> None:
    task = Task(
        "旧",
        progress=10,
        actuals=[
            Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 30),
            Actual(datetime(2026, 10, 6, 9, 0), None, None),
        ],
    )
    mount_dialog(task, [], actual_mode=INTERVALS)
    await open_dialog(user)
    assert task_progress_input(user).value == 30


async def test_two_actuals_in_the_simple_mode_lock_the_field_to_their_last_value(user: User) -> None:
    saved: list[Task] = []
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 30),
        Actual(datetime(2026, 10, 6, 9, 0), None, 60),
    ]
    mount_dialog(Task("旧", progress=10, actuals=list(kept)), saved)
    await open_dialog(user)
    field = task_progress_input(user)
    assert field.value == 60 and not field.enabled
    user.find(marker="task-save").click()
    assert saved[0].progress == 10 and saved[0].actuals == kept


async def test_the_task_progress_is_hidden_for_a_checkpoint_and_cleared_on_save(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", progress=40, deadline=datetime(2026, 10, 9, 17, 0)), saved)
    await open_dialog(user)
    await set_kind(user, TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-progress")
    user.find(marker="task-save").click()
    assert saved[0].kind is TaskKind.CHECKPOINT and saved[0].progress is None


async def test_the_task_progress_stays_in_the_schedule_layout(user: User) -> None:
    mount_dialog(Task("旧", progress=40), [], layout="schedule")
    await open_dialog(user)
    await user.should_see(marker="task-progress")


async def test_changing_the_task_progress_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(Task("旧"), [])
    await open_dialog(user)
    task_progress_input(user).set_value(40)
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_an_out_of_range_task_progress_is_an_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧"), saved)
    await open_dialog(user)
    task_progress_input(user).set_value(101)
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("進捗度")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_task_dialog.py -q -n auto -k "task_progress or interval_progress or last_entered or lock_the_field"`
Expected: FAIL(マーカー `task-progress` の要素がない)

- [ ] **Step 3: 実装する**

`src/projectapp/task_dialog.py`:

(1) `ActualFields.__init__` の先頭(`self.read_only = ...` の次)に `self._actuals = list(task.actuals)` を足し、メソッドを足す(`progress_value` の次):

```python
    def interval_progress(self) -> float | None:
        """区間の進捗度(入っている最後の値)。2 件以上で編集できないときは、保持している区間の値。"""
        if self.read_only:
            return next((a.progress for a in reversed(self._actuals) if a.progress is not None), None)
        return self.progress.value
```

(2) `IntervalFields` に足す(`progress_value` の次):

```python
    def interval_progress(self) -> float | None:
        """進捗度の入っている最後の行の値。なければ None。"""
        return next((row.progress.value for row in reversed(self._rows) if row.progress.value is not None), None)
```

(3) `IntervalFields` の定義の次(`NO_TEMPLATE = ""` の前)に足す:

```python
class TaskProgressField:
    """タスクの進捗度の欄。区間に進捗度があるときは、その値を読み取り専用で示し、タスクの値(`own`)は変えない。"""

    def __init__(self, own: int | None) -> None:
        self.own: float | None = own
        self._syncing = False
        with ui.column().classes("w-full gap-0") as self.container:
            self.input = (
                ui.number("進捗度(%)", value=own, min=MIN_PROGRESS, max=MAX_PROGRESS, precision=0)
                .classes("w-full")
                .mark("task-progress")
            )
            self.hint = (
                ui.label("実績の区間の値を使っています").classes("text-caption text-grey").mark("task-progress-hint")
            )
        self.hint.set_visibility(False)
        self.input.on_value_change(self._edited)

    def _edited(self, _event: object) -> None:
        if not self._syncing:
            self.own = self.input.value

    def sync(self, interval: float | None) -> None:
        """区間の進捗度があれば、その値を読み取り専用で示す。なければ、タスクの値に戻して編集できるようにする。"""
        locked = interval is not None
        self._syncing = True
        try:
            self.input.set_value(interval if locked else self.own)
        finally:
            self._syncing = False
        self.input.set_enabled(not locked)
        self.hint.set_visibility(locked)

    def state(self) -> tuple[object, ...]:
        """変更の判定に使う入力値(進捗度は 0 と空を区別する)。"""
        return (self.own,)
```

(4) `open_task_dialog` の中。`actual_box` を作る `with ui.column()...` ブロックの次の行に足す:

```python
        progress_field = TaskProgressField(initial.progress)
        progress_field.sync(actual_fields.interval_progress())
```

`actual_fields.bind(on_actual_change)` の次の行に足す:

```python
        actual_fields.bind(lambda _event: progress_field.sync(actual_fields.interval_progress()))
```

`has_normal_data` の式に `or initial.progress is not None` を足す(`or initial.actuals` の次)。

`refresh_visibility` の `for widget in (fields.first_row, effort, conversion, actual_box):` を `(fields.first_row, effort, conversion, actual_box, progress_field.container)` にする。

`current()` の `*actual_fields.state(),` の次に `*progress_field.state(),` を足す。

`save()` の `build_task(` に `progress=progress_field.own,` を足す(`actual_rows=...` の次)。

注: `ActualFields` は、2 件以上のとき `bind` で何も付けない(`inputs()` が空)ので、`sync` は開いたときの 1 回だけ。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_task_dialog.py -q -n auto && uv run ty check src`
Expected: すべて PASS、ty はエラーなし

- [ ] **Step 5: 全体を確認して Commit**

Run: `uv run pytest -n auto -q`
Expected: すべて PASS

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "$(cat <<'EOF'
feat: 編集ダイアログにタスクの進捗度の欄を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: PlantUML の取り込みで進捗度を取り込む

**Files:**
- Modify: `src/projectapp/puml_import.py`(`PlantUmlImport`・`_Counts`・`_Builder._task`・`summary`)
- Modify: `test/test_puml_import.py`

**Interfaces:**
- Consumes: Task 1 の `Task.progress`。既存の `_Raw.progress: int | None`・`_status`。
- Produces: `PlantUmlImport` から `dropped_progress` を除く(項目は `project`・`task_count`・`created_members`・`skipped_lines`・`unresolved`・`clamped_allocations`)。通常タスクは `Task.progress = N`(1〜100)、0・未指定は `None`。チェックポイントは `None`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_puml_import.py`:

- `test_progress_decides_only_the_status` の `assert task.status is status and task.actuals == []` の次に、`parametrize` に合わせて期待値を足す: 関数の引数を `(line: str, status: Status, progress: int | None)` にし、パラメータを次に差し替える:

```python
    ("line", "status", "progress"),
    [
        ("[A] starts 2026-10-13", Status.NOT_STARTED, None),
        ("[A] starts 2026-10-13 and is 0% completed", Status.NOT_STARTED, None),
        ("[A] starts 2026-10-13 and is 1% completed", Status.RUNNING, 1),
        ("[A] starts 2026-10-13 and is 99% completed", Status.RUNNING, 99),
        ("[A] starts 2026-10-13 and is 100% completed", Status.DONE, 100),
    ],
```

関数の本体は次にする(関数名は `test_progress_decides_the_status_and_is_kept_as_the_task_value` に変える):

```python
    result = parse(line)
    task = task_named(result, "A")
    assert task.status is status and task.progress == progress and task.actuals == []
```

- `test_progress_on_a_separate_line_and_the_dropped_count` を次に差し替える(名前は `test_progress_on_a_separate_line_is_kept`):

```python
def test_progress_on_a_separate_line_is_kept() -> None:
    result = parse("[A] as [T1] starts 2026-10-13", "[T1] is 40% completed", "[B] starts 2026-10-13", "[C] is 0% completed")
    assert (task_named(result, "A").status, task_named(result, "A").progress) == (Status.RUNNING, 40)
    assert task_named(result, "B").progress is None and task_named(result, "C").progress is None
```

- `test_a_checkpoint_is_done_only_at_100_percent` の末尾に足す:

```python
    assert task_named(parse("[M] happens on 2026-10-23 and is 100% completed"), "M").progress is None
```

- `test_a_milestone_without_a_date_is_a_plain_unscheduled_task` の次に足す:

```python
def test_a_milestone_without_a_date_keeps_its_progress_as_a_plain_task() -> None:
    task = task_named(parse("[M] happens at [Z]'s end and is 30% completed"), "M")
    assert task.kind is TaskKind.NORMAL and task.progress == 30
```

- `test_the_summary_lists_counts_and_notes` を次に差し替える:

```python
def test_the_summary_lists_counts_and_notes() -> None:
    result = parse("[A] on {田中:0%} starts 2026-10-13 and is 50% completed", "[B] starts at [Z]'s end", "foo bar baz")
    text = summary(result)
    assert text.startswith("取り込みました(タスク 2 件、メンバー 1 人を作成)")
    for note in ("読み飛ばした行 1 行", "日程が求まらないタスク 1 件", "割り当て率を 100% にした担当 1 件"):
        assert note in text
    assert "進捗度" not in text
    assert summary(parse("[A] starts 2026-10-13")) == "取り込みました(タスク 1 件)"
```

- `test_the_output_of_build_plantuml_comes_back` の `first = Task(...)` に `progress=40,` を足し(`assignees=[Assignee("田中", 1.0)]` の次)、末尾の `assert [s.name ...]` の次に足す:

```python
    assert by_name["設計 (田中)"].progress == 40 and by_name["設計 (田中)"].status is Status.RUNNING
```

ただし `first` の状態は既定の `未着手` なので、`status=Status.RUNNING,` も `first` に足す(出力の `is 40% completed` が取り込みで `実行中` になる)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_puml_import.py -q -n auto`
Expected: FAIL(`progress` が `None` のまま、`dropped_progress` を参照していて通知に進捗度の項目が出る)

- [ ] **Step 3: 実装する**

`src/projectapp/puml_import.py`:

- `PlantUmlImport` から `dropped_progress: int  # ...` の行を消す。`_Counts` から `dropped_progress: int = 0` を消す。`parse_plantuml` の `PlantUmlImport(...)` 呼び出しから `counts.dropped_progress,` を消す。
- `_Builder._task` を差し替える:

```python
    def _task(self, index: int, raw: _Raw) -> Task:
        start, end = self.resolver.span(index)
        task = Task(tidy_task_name(raw.name) or UNNAMED, id=self._fresh())
        task.status = _status(raw.progress)
        task.progress = raw.progress or None  # 0 は入れない(未着手と区別しない)
        if start is None or end is None:
            self.counts.unresolved += 1
        elif raw.milestone:
            task.kind = TaskKind.CHECKPOINT
            task.deadline = self._end_of_day(start)
            task.status = Status.DONE if task.status is Status.DONE else Status.NOT_STARTED
            task.progress = None  # チェックポイントは進捗度を持たない
            return task
        else:
            task.planned_start = datetime.combine(start, self.project.work_start)
            task.planned_end = self._end_of_day(end)
        task.assignees = self._assignees(raw)
        return task
```

(今の `if raw.progress: self.counts.dropped_progress += 1` の 2 行は、上の差し替えで消える。)

- `summary` の `notes` から、`進捗度を取り込まなかったタスク` の 1 行を消す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS(`java` と `plantuml.jar` があれば、描画のテストも走る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/puml_import.py test/test_puml_import.py
git commit -m "$(cat <<'EOF'
feat: PlantUML の取り込みで進捗度をタスクの値として取り込む

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 文書の更新と最終確認

**Files:**
- Modify: `CLAUDE.md`(`projectapp/` 直下)
- Modify: `docs/development.md`
- Modify: `docs/superpowers/specs/2026-10-16-plantuml-import-design.md`
- Modify: `docs/superpowers/specs/2026-10-16-task-progress-design.md`
- Modify: `docs/request-history.md`・`docs/requests.md`・`.claude/MEMORY.md`

**Interfaces:**
- Consumes: Task 1〜4 の実装。
- Produces: 仕様書・開発者向けメモ・設計書・要望の記録が実装と一致する。

- [ ] **Step 1: 仕様書(`CLAUDE.md`)を更新する**

- 「ガントチャート」の節の、タスクの状態の項目の次に足す: `タスクの進捗度(0〜100%)を、編集ダイアログの欄で入れられる(実績を作らなくてよい)。実績の区間に進捗度があるときは、区間(入っている最後の値)を優先し、欄は読み取り専用でその値を示す(タスクの値は変えない)。なければ、タスクの値。チェックポイントは進捗度を持たない。状態とは連動しない`
- 「PlantUML の取り込み」の節の、進捗の記述を直す。「進捗は状態だけを決める(0=未着手・1〜99=実行中・100=終了)。進捗度は取り込まない」を「進捗は、状態(0=未着手・1〜99=実行中・100=終了)と、タスクの進捗度(1〜100%。0 は入れない)に取り込む。チェックポイントは進捗度を持たない」にする。通知の説明から「進捗度を取り込まなかったタスク」を外す。
- 「実装上の注意」の `version`(整数。現在 4)を 5 にする。

- [ ] **Step 2: 開発者向けメモ(`docs/development.md`)を更新する**

- イベント(version 4)の項目の次に足す: `- タスクの進捗度(version 5)は `Task.progress: int | None`(0〜100)。保存は `"progress"`。version 4 以下の同名のキーは読まない(`events` と同じ)。読込(`storage._progress`)は、整数でない・範囲外・bool を拒否し、チェックポイントは `None` にする。現在の値は `timeline.current_progress`(最後に進捗度の入っている区間 → なければ `Task.progress`)だけを通す。編集ダイアログは `TaskProgressField`(区間に進捗度があるときは読み取り専用で、`own`〔タスクの値〕は変えない)。`merge.py` は `fields(Task)` で項目をほどくので、`TASK_LABELS` に表示名を足すだけ`
- 「既知の見送り事項」の「PlantUML の取り込み」から、進捗度の取り込みの行を消す(残りの 1 行は残す)。

- [ ] **Step 3: 設計書を直す**

- `docs/superpowers/specs/2026-10-16-plantuml-import-design.md`: 進捗度に触れている決定事項・進捗と状態・失敗と通知・含まないもの・テストの記述の末尾(または該当の行)に、「(要望 38 で、`Task.progress` として取り込むようになった)」を足す。
- `docs/superpowers/specs/2026-10-16-task-progress-design.md` の「文書の更新」から、`file-format.md`(todoapp 用のファイルで、このアプリの形式ではない)への言及を消す。

- [ ] **Step 4: 要望の記録を更新する**

- `docs/request-history.md`: 要望 38 の行を「実装済み(PR レビュー待ち)」にして、ブランチ `task-progress` を書く。未着手の件数の行から 38 を外す。要望 37 の行に「進捗度は要望 38 で取り込み」を足す。
- `docs/requests.md`: 要望 38 の節の見出しに「(実装済み)」を足す。
- `.claude/MEMORY.md`: 最終更新と、2026-10-16 の作業に、要望 38 の実装を足す(設計の決定: 区間を優先・入力欄・状態と非連動・取り込みは 0 を入れない)。「今後の要望」の 38 を完了にする。

- [ ] **Step 5: 最終確認**

Run: `uv run pytest -n auto && uv run ty check src`
Expected: すべて PASS、ty はエラーなし

- [ ] **Step 6: 実機で確かめる**

Run: `uv run projectapp`

手順: ① タスクを開き、`進捗度`の欄に 40 を入れて保存 → ガントの棒が 40% 塗られ、チップに `40%` が出る。② 実績の開始を入れ、実績の進捗度に 70 を入れる → `進捗度`の欄が 70 の読み取り専用になり、説明が出る。保存して開き直すと、タスクの値(40)が残る。③ 実績の進捗度を消す → 欄が 40 に戻って編集できる。④ 種別をチェックポイントにする → 欄が消える。⑤ `PlantUML を取り込む` で、`is 40% completed` のある `.puml` を取り込む → タスクに進捗度 40% が入る。

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "$(cat <<'EOF'
docs: タスクの進捗度を仕様と開発者向けメモに反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```
