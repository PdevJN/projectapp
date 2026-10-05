# 実績の複数区間と記録方式の設定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プロジェクトの記録方式(簡易/区間)を設定でき、区間のときはタスク編集ダイアログで実績を複数の区間として入力でき、ガントチャートで区間の間が点線で見える。

**Architecture:** 保存形式(実績は区間のリスト)は変えず、`Project.actual_mode` を足す。検証は `forms.py` の純粋関数(`build_actual_intervals`)に置き、ダイアログは行の入力部品(`IntervalFields`)を足して `ActualFields` と同じ呼び出し口(`bind` / `filled` / `progress_value` / `state`)にそろえる。点線は `gantt.py` の `actual_bars` が、隣り合う区間の隙間に描く。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、`uvx ty check src`

**Spec:** `docs/superpowers/specs/2026-10-05-actual-intervals-design.md`

## Global Constraints

- 言語は日本語。画面の文言・エラーは日本語(例: 「区間 2: 前の区間と重なっています」)。
- 実績の保存形式は変えない(`actuals: [{start, end, progress}]`)。新しいキーは `actual_mode`(`"simple"` か `"intervals"`)だけ。
- キーのない古いファイルは `simple`。`actual_mode` の値が不正なら読込を拒否する(「開けませんでした」)。
- 読込では、区間の重なりと並び順を検証しない(既存の検証だけ)。
- 簡易で 2 区間以上のタスクは、今までどおり読み取り専用(保存しても実績は書き換えない)。
- 状態の色は `--scolor`(`STATUS_CLASSES` のクラスが持つ CSS 変数)。点線もこれを使う。
- テストは `uv run pytest -q`(全体は約3分かかるので、タスク中は対象のファイルだけ実行する)、型は `uvx ty check src`。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- 作業ブランチは `feature/actual-intervals`(`develop` から切ってある)。マージとプッシュは、ユーザーの許可を得てから。

## Review Focus

- 空の行(開始・終了・進捗度がすべて空)だけを残して保存したら、実績は 0 件になり、エラーにならない。→ Task 2
- 手で編集した、進行中の区間が途中にあるファイルを「区間」で開いて保存すると、保存できずに、どの区間かが分かるエラーが出る。→ Task 2, 4
- 行を削除したあとのエラー文の「区間 N」は、画面上の現在の位置(上から数えた番号)を指す。→ Task 4
- 重なり・逆順の実績を持つ手編集ファイルでも、ガントチャートの描画は落ちず、点線を出さない。→ Task 5
- 簡易で 2 区間以上のファイルは開けて、ダイアログは読み取り専用。「区間」に切り替えると編集できる。→ Task 3, 4
- 「区間」で、2 区間以上のタスクがあるときは、設定ダイアログで簡易に戻せない。→ Task 3

---

### Task 1: 記録方式のデータと保存(`models.py`、`storage.py`)

**Files:**
- Modify: `src/projectapp/models.py`(`Status` の下に `ActualMode`、`Project` に `actual_mode`)
- Modify: `src/projectapp/storage.py`(`_actual_mode` を追加、`load_project` で読む。インポートに `ActualMode`)
- Test: `test/test_storage.py`

**Interfaces:**
- Produces: `projectapp.models.ActualMode`(`StrEnum`: `SIMPLE = "simple"`、`INTERVALS = "intervals"`)、`Project.actual_mode: ActualMode = ActualMode.SIMPLE`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` のインポートを `from projectapp.models import Actual, ActualMode, Member, Priority, Project, Section, Status, Task` に直し、末尾に追加する。

```python
def test_actual_mode_roundtrip(tmp_path: Path) -> None:
    project = Project("demo", actual_mode=ActualMode.INTERVALS)
    assert load_project(save_project(project, tmp_path)).actual_mode is ActualMode.INTERVALS


def test_file_without_actual_mode_loads_as_simple(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["actual_mode"] == "simple"
    del raw["actual_mode"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).actual_mode is ActualMode.SIMPLE


@pytest.mark.parametrize("bad", ["weekly", None, 1, []])
def test_invalid_actual_mode_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("demo"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["actual_mode"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="記録方式"):
        load_project(path)


def test_simple_file_with_two_actuals_still_loads(tmp_path: Path) -> None:
    project = _project_with_actuals(
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    )
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.actual_mode is ActualMode.SIMPLE
    assert len(loaded.tasks[0].actuals) == 2
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_storage.py -q -k "actual_mode or two_actuals_still"`
Expected: FAIL(`ImportError: cannot import name 'ActualMode'`)

- [ ] **Step 3: 実装する**

`models.py`: `Status` の定義の直後に追加する。

```python
class ActualMode(StrEnum):
    SIMPLE = "simple"  # 簡易: 実績は 1 区間
    INTERVALS = "intervals"  # 区間: 実績を複数の区間で入力する
```

`Project` の最後のフィールド(`tasks`)の下に追加する(既存の位置引数を壊さないよう、末尾に置く)。

```python
    actual_mode: ActualMode = ActualMode.SIMPLE  # 実績の記録方式
```

`storage.py`: `from projectapp.models import (...)` に `ActualMode` を足す。`_work_start` の下に追加する。

```python
def _actual_mode(value: Any) -> ActualMode:
    """実績の記録方式。不正はValueError(開けませんでした)。"""
    try:
        return ActualMode(value)
    except ValueError:
        raise ValueError(f"実績の記録方式が正しくありません: {value!r}") from None
```

`load_project` の `Project(...)` に `actual_mode=_actual_mode(raw.get("actual_mode", "simple")),` を足す(`tasks=` の下)。保存は `asdict` が出すので変更不要。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_storage.py test/test_views.py -q`
Expected: PASS(新しい 7 件を含む。`test_views.py` は保存・読込の既存テストの確認)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_storage.py
git commit -m "実績の記録方式(簡易/区間)をプロジェクトに保存する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 区間の検証と状態の提案(`forms.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`ActualRow`、`build_actual_intervals`、`build_task` の引数、`suggest_status`)
- Test: `test/test_forms.py`

**Interfaces:**
- Produces:
  - `ActualRow = tuple[str, str, float | None]`(開始の文字列、終了の文字列、進捗度。文字列は `compose_actual` の結果)
  - `build_actual_intervals(rows: list[ActualRow]) -> list[Actual]`(不正は `ValueError`、文は「区間 N: …」)
  - `build_task(..., actual_rows: list[ActualRow] | None = None)`(`None` でなければ、`actual_start` などより優先して区間を作る)
  - `suggest_status(has_start: bool, has_end: bool, progress: float | None = None, intervals: bool = False) -> Status | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` のインポートに `build_actual_intervals` を足し、末尾に追加する。

```python
S1, E1 = "2026-10-05T09:00", "2026-10-05T12:00"
S2, E2 = "2026-10-06T09:00", "2026-10-06T12:00"


def test_intervals_build_in_order() -> None:
    result = build_actual_intervals([(S1, E1, 30), (S2, "", 60)])
    assert result == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), 30),
        Actual(datetime(2026, 10, 6, 9), None, 60),
    ]


def test_empty_rows_are_ignored() -> None:
    assert build_actual_intervals([("", "", None), (S1, E1, None), ("", "", None)]) == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), None)
    ]
    assert build_actual_intervals([("", "", None)]) == []
    assert build_actual_intervals([]) == []


def test_interval_errors_name_the_row() -> None:
    with pytest.raises(ValueError, match="区間 2: 実績の終了"):
        build_actual_intervals([(S1, E1, None), (S2, "2026-10-06T08:00", None)])
    with pytest.raises(ValueError, match="区間 1: 実績の開始"):
        build_actual_intervals([("", E1, None)])
    with pytest.raises(ValueError, match="区間 1: .*形式"):
        build_actual_intervals([("abc", "", None)])


def test_the_row_number_counts_the_ignored_empty_rows() -> None:
    with pytest.raises(ValueError, match="区間 3: 前の区間と重なっています"):
        build_actual_intervals(
            [(S1, "2026-10-05T12:00", None), ("", "", None), ("2026-10-05T11:00", E2, None)]
        )


def test_overlapping_intervals_are_rejected_but_touching_ones_are_not() -> None:
    with pytest.raises(ValueError, match="区間 2: 前の区間と重なっています"):
        build_actual_intervals([(S1, E1, None), ("2026-10-05T11:59", E2, None)])
    assert len(build_actual_intervals([(S1, E1, None), (E1, E2, None)])) == 2


def test_intervals_must_be_in_start_order() -> None:
    with pytest.raises(ValueError, match="開始の早い順"):
        build_actual_intervals([(S2, E2, None), (S1, E1, None)])


def test_only_the_last_interval_may_be_open() -> None:
    with pytest.raises(ValueError, match="区間 1: 終了のない区間は最後の1つだけ"):
        build_actual_intervals([(S1, "", None), (S2, E2, None)])
    assert len(build_actual_intervals([(S1, E1, None), (S2, "", None)])) == 2


def test_progress_must_not_decrease_across_intervals() -> None:
    with pytest.raises(ValueError, match="区間 3: 進捗度は前の区間以上"):
        build_actual_intervals(
            [(S1, E1, 50), ("2026-10-06T09:00", "2026-10-06T12:00", None), ("2026-10-07T09:00", "", 40)]
        )
    assert len(build_actual_intervals([(S1, E1, 50), (S2, E2, 50)])) == 2


def test_build_task_uses_the_rows_when_given() -> None:
    existing = Task("t", actuals=[Actual(datetime(2026, 1, 1, 9), None)])
    task = make(existing, actual_rows=[(S1, E1, None), (S2, "", None)], actual_start="2030-01-01T09:00")
    assert [a.start for a in task.actuals] == [datetime(2026, 10, 5, 9), datetime(2026, 10, 6, 9)]
    assert make(existing, actual_rows=[]).actuals == []
    assert make(existing, actual_rows=[("", "", None)]).actuals == []


def test_build_task_without_rows_keeps_the_simple_behaviour() -> None:
    kept = [Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)), Actual(datetime(2026, 10, 6, 9), None)]
    assert make(Task("t", actuals=list(kept)), actual_start="").actuals == kept


@pytest.mark.parametrize(
    ("has_start", "has_end", "progress", "expected"),
    [
        (False, False, None, None),
        (False, True, None, None),
        (True, False, None, Status.RUNNING),
        (True, False, 100, None),
        (True, True, None, Status.PAUSED),
        (True, True, 50, Status.PAUSED),
        (True, True, 99, Status.PAUSED),
        (True, True, 100, Status.DONE),
    ],
)
def test_suggest_status_for_intervals(
    has_start: bool, has_end: bool, progress: float | None, expected: Status | None
) -> None:
    assert suggest_status(has_start, has_end, progress, intervals=True) is expected


def test_suggest_status_for_simple_is_unchanged_by_the_intervals_flag_default() -> None:
    assert suggest_status(True, True, 50) is Status.DONE
```

(`Actual`、`Task`、`Status`、`datetime` は既存のインポートを使う。足りなければ足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py -q -k "interval or rows or only_the_last or row_number"`
Expected: FAIL(`ImportError: cannot import name 'build_actual_intervals'`)

- [ ] **Step 3: 実装する**

`forms.py`: `build_actuals` の下に追加する。

```python
ActualRow = tuple[str, str, float | None]  # 区間の1行の入力(開始・終了の文字列、進捗度)


def build_actual_intervals(rows: list[ActualRow]) -> list[Actual]:
    """区間の行の入力を検証して、区間のリストにする。すべて空の行は無視する(行番号は数える)。
    開始の昇順、重ならない、終了のない区間は最後の1つだけ、進捗度は前の入力以上。"""
    kept: list[tuple[int, Actual]] = []
    for number, (start_text, end_text, progress) in enumerate(rows, start=1):
        if not start_text and not end_text and progress is None:
            continue
        try:
            built = build_actuals(start_text, end_text, progress)
        except ValueError as exc:
            raise ValueError(f"区間 {number}: {exc}") from None
        kept.append((number, built[0]))
    previous: tuple[int, Actual] | None = None
    last_progress: int | None = None
    for number, actual in kept:
        if previous is not None:
            before_number, before = previous
            if before.end is None:
                raise ValueError(f"区間 {before_number}: 終了のない区間は最後の1つだけにしてください")
            if actual.start < before.start:
                raise ValueError("区間は開始の早い順に入れてください")
            if actual.start < before.end:
                raise ValueError(f"区間 {number}: 前の区間と重なっています")
        if actual.progress is not None:
            if last_progress is not None and actual.progress < last_progress:
                raise ValueError(f"区間 {number}: 進捗度は前の区間以上にしてください")
            last_progress = actual.progress
        previous = (number, actual)
    return [actual for _, actual in kept]
```

`build_task` のシグネチャの `actual_progress` の下に `actual_rows: list[ActualRow] | None = None,` を足す。実績を決める部分を次に置き換える。

```python
    if actual_rows is not None:
        actuals = build_actual_intervals(actual_rows)
    elif len(base.actuals) > 1:
        actuals = base.actuals
    else:
        actuals = build_actuals(actual_start, actual_end, actual_progress)
```

`suggest_status` を次に置き換える。

```python
def suggest_status(
    has_start: bool, has_end: bool, progress: float | None = None, intervals: bool = False
) -> Status | None:
    """実績の入力から、提案する状態。開始なし(終了だけを含む)は提案しない。
    終了が空で進捗度が100のときは、完了とはみなさず、状態を変えない。
    区間(intervals)のときは、最後の区間が終わっていて進捗度が100でなければ、一時停止を提案する。"""
    if not has_start:
        return None
    if has_end:
        if intervals and progress != MAX_PROGRESS:
            return Status.PAUSED
        return Status.DONE
    return None if progress == MAX_PROGRESS else Status.RUNNING
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py -q`
Expected: PASS(既存の `build_task`・`suggest_status` のテストも通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "実績の区間の検証と、区間のときの状態の提案を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 設定ダイアログと適用(`forms.py`、`views.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`open_settings_dialog`)
- Modify: `src/projectapp/views.py`(`open_settings`、`multi_interval_count`、`apply_settings`。インポートに `ActualMode`)
- Modify: `test/test_forms.py`(既存の `open_settings_dialog` の呼び出しを新しい署名に直す)
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `ActualMode`(Task 1)
- Produces:
  - `open_settings_dialog(daily_hours, work_start, on_apply: Callable[[float, time, ActualMode], object], actual_mode: ActualMode = ActualMode.SIMPLE, multi_interval_tasks: int = 0) -> None`
  - `MainView.apply_settings(hours: float, start: time, mode: ActualMode) -> None`
  - `MainView.multi_interval_count() -> int`(2 区間以上の実績を持つタスクの数)
  - マーカー: `settings-actual-mode`(`ui.toggle`。値は `"simple"` / `"intervals"`)、`settings-mode-locked`(戻せない理由のラベル)

- [ ] **Step 1: 既存のテストを新しい署名に直し、失敗するテストを書く**

`test/test_forms.py` で、`open_settings_dialog(` の `on_apply` を 3 引数にする。

- `lambda h, s: None` → `lambda h, s, m: None`(3 か所)
- `lambda h, s: applied.append((h, s))` → `lambda h, s, m: applied.append((h, s, m))`、`applied: list[tuple[float, time]]` → `list[tuple[float, time, ActualMode]]`、`assert applied == [(8.0, time(10, 0))]` → `assert applied == [(8.0, time(10, 0), ActualMode.SIMPLE)]`
- 388 行付近の呼び出しも、`grep -n "open_settings_dialog" test/test_forms.py` で見つけて、同じ形に直す。
- インポートに `ActualMode` を足す(`from projectapp.models import ...`)。

末尾に新しいテストを追加する。

```python
async def test_settings_dialog_applies_the_actual_mode(user: User) -> None:
    applied: list[tuple[float, time, ActualMode]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: applied.append((h, s, m))
            ),
        )

    await user.open("/")
    user.find("open").click()
    mode = user.find(marker="settings-actual-mode").elements.pop()
    assert mode.value == "simple"
    mode.set_value("intervals")
    user.find(marker="settings-apply").click()
    assert applied == [(6.5, time(9, 0), ActualMode.INTERVALS)]


async def test_settings_dialog_cannot_go_back_to_simple_with_multi_interval_tasks(
    user: User,
) -> None:
    applied: list[tuple[float, time, ActualMode]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda h, s, m: applied.append((h, s, m)),
                ActualMode.INTERVALS,
                multi_interval_tasks=2,
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_see("2件のタスクに複数の区間があるため、簡易には戻せません")
    mode = user.find(marker="settings-actual-mode").elements.pop()
    mode.set_value("simple")
    assert mode.value == "intervals"  # 選んでも、区間に戻る
    user.find(marker="settings-apply").click()
    assert applied == [(6.5, time(9, 0), ActualMode.INTERVALS)]


async def test_settings_dialog_hides_the_lock_message_without_multi_interval_tasks(
    user: User,
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: None, ActualMode.INTERVALS
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_not_see(marker="settings-mode-locked")
    user.find(marker="settings-actual-mode").elements.pop().set_value("simple")
    assert user.find(marker="settings-actual-mode").elements.pop().value == "simple"


async def test_settings_dialog_keeps_simple_with_multi_interval_tasks_when_it_was_simple(
    user: User,
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: None, ActualMode.SIMPLE, multi_interval_tasks=1
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_not_see(marker="settings-mode-locked")  # 簡易のままなら、制限はない
```

`test/test_views.py` の末尾に追加する(インポートに `ActualMode`、`Actual` を足す。`mount_capturing`、`save_cache` は既存のものを使う)。

```python
async def test_actual_mode_setting_is_applied_and_makes_the_project_dirty(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    user.find(marker="open-settings").click()
    user.find(marker="settings-actual-mode").elements.pop().set_value("intervals")
    user.find(marker="settings-apply").click()
    assert view.project.actual_mode is ActualMode.INTERVALS
    assert await wait_until(lambda: view.is_dirty())


async def test_multi_interval_count_counts_tasks_with_two_or_more_actuals(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    two = [Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)), Actual(datetime(2026, 10, 6, 9))]
    view.save_task(None, None, Task("複数", actuals=two))
    view.save_task(None, None, Task("単独", actuals=two[:1]))
    assert view.multi_interval_count() == 1
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -k "settings or actual_mode or multi_interval"`
Expected: FAIL(`open_settings_dialog` が 3 引数のコールバックを受け付けない、`multi_interval_count` がない、など)

- [ ] **Step 3: 実装する**

`forms.py` の `open_settings_dialog` を次のように変える(`from projectapp.models import ...` に `ActualMode` を足す)。

```python
def open_settings_dialog(
    daily_hours: float,
    work_start: time,
    on_apply: Callable[[float, time, ActualMode], object],
    actual_mode: ActualMode = ActualMode.SIMPLE,
    multi_interval_tasks: int = 0,
) -> None:
```

`start` の入力と時刻選択ダイアログのあと、`error = ui.label(...)` の前に追加する。

```python
        ui.label("実績の記録方式").classes("text-caption text-grey")
        mode = ui.toggle(
            {ActualMode.SIMPLE.value: "簡易", ActualMode.INTERVALS.value: "区間"},
            value=actual_mode.value,
        ).mark("settings-actual-mode")
        # 区間から簡易へは、2区間以上のタスクがあるあいだ戻せない(選んでも区間に戻す)
        locked = multi_interval_tasks > 0 and actual_mode is ActualMode.INTERVALS
        if locked:
            ui.label(
                f"{multi_interval_tasks}件のタスクに複数の区間があるため、簡易には戻せません"
            ).classes("text-caption text-grey").mark("settings-mode-locked")

            def keep_intervals(event: object) -> None:
                if getattr(event, "value", None) == ActualMode.SIMPLE.value:
                    mode.set_value(ActualMode.INTERVALS.value)

            mode.on_value_change(keep_intervals)
```

`apply` の `on_apply(*result)` を `on_apply(*result, ActualMode(mode.value))` に変える。

`views.py`: `from projectapp.models import ...` に `ActualMode` を足す。

```python
    def open_settings(self) -> None:
        open_settings_dialog(
            self.project.daily_hours,
            self.project.work_start,
            self.apply_settings,
            self.project.actual_mode,
            self.multi_interval_count(),
        )

    def multi_interval_count(self) -> int:
        """2区間以上の実績を持つタスクの数。簡易へ戻せるかの判定に使う。"""
        return sum(1 for task in self.project.all_tasks() if len(task.actuals) > 1)
```

```python
    def apply_settings(self, hours: float, start: time, mode: ActualMode) -> None:
        """稼働設定と記録方式を更新して再描画する。完了予定は表示のたびに計算されるので、再計算の処理は要らない。保存はしない。"""
        if (
            hours == self.project.daily_hours
            and start == self.project.work_start
            and mode is self.project.actual_mode
        ):
            return
        self.project.daily_hours, self.project.work_start = hours, start
        self.project.actual_mode = mode
        self.gantt.set_project(self.project)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q`
Expected: PASS(既存の設定のテストも通る。落ちる既存テストがあれば、`on_apply` の引数の数の直し漏れ)

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_forms.py test/test_views.py
git commit -m "設定ダイアログで実績の記録方式を選べるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: タスク編集ダイアログの区間の入力(`task_dialog.py`、`views.py`)

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`moment_column` の切り出し、`ActualFields.bind` / `rows`、`IntervalFields`、`open_task_dialog` の `actual_mode`)
- Modify: `src/projectapp/views.py`(`open_task_dialog` の 3 か所に `actual_mode=self.project.actual_mode`)
- Test: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: `ActualRow`、`build_task(actual_rows=...)`、`suggest_status(..., intervals=...)`(Task 2)、`ActualMode`(Task 1)
- Produces:
  - `open_task_dialog(..., actual_mode: ActualMode = ActualMode.SIMPLE) -> ui.dialog`
  - `IntervalFields(task: Task)`: `inputs() -> list[ui.input | ui.number]`、`bind(callback)`、`filled() -> tuple[bool, bool]`(最後の区間)、`progress_value() -> float | None`(最後の区間)、`state() -> tuple[object, ...]`、`rows() -> list[ActualRow]`(`ValueError` の文は「区間 N: …」)、`start_text()` / `end_text()`(常に `""`。区間は `rows()` を使う)
  - `ActualFields.bind(callback)`、`ActualFields.read_only`(既存)
  - マーカー: `task-interval-add`(追加ボタン)、行ごとに(`n` は、そのダイアログで行を作った順の 0 始まりの番号。削除しても詰めない)`task-interval-{n}-start-date` / `-start-time` / `-end-date` / `-end-time` / `-progress` / `-remove`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` の `mount_dialog` に `actual_mode: ActualMode = ActualMode.SIMPLE` を足して `open_task_dialog(..., actual_mode=actual_mode)` に渡す。インポートに `ActualMode` を足す。末尾に追加する。

```python
INTERVALS = ActualMode.INTERVALS


def interval_inputs(user: User, n: int, start: str, end: str = "", progress: str = "") -> None:
    day, clock = start.split(" ")
    user.find(marker=f"task-interval-{n}-start-date").clear().type(day)
    user.find(marker=f"task-interval-{n}-start-time").clear().type(clock)
    if end:
        day, clock = end.split(" ")
        user.find(marker=f"task-interval-{n}-end-date").clear().type(day)
        user.find(marker=f"task-interval-{n}-end-time").clear().type(clock)
    if progress:
        user.find(marker=f"task-interval-{n}-progress").clear().type(progress)


async def test_interval_mode_shows_no_rows_for_a_task_without_actuals(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    await user.should_see(marker="task-interval-add")
    await user.should_not_see(marker="task-interval-0-start-date")
    await user.should_not_see(marker="task-actual-start-date")


async def test_interval_rows_are_added_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00", "30")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 1, "2026-10-06 09:00", "", "60")
    user.find(marker="task-save").click()
    assert saved[0].actuals == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), 30),
        Actual(datetime(2026, 10, 6, 9), None, 60),
    ]


async def test_two_actuals_are_editable_in_interval_mode(user: User) -> None:
    saved: list[Task] = []
    two = [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), 30),
        Actual(datetime(2026, 10, 6, 9), None, 60),
    ]
    mount_dialog(Task("旧", actuals=list(two)), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    await user.should_not_see(marker="task-actuals-readonly")
    assert value_of(user, "task-interval-0-start-date") == "2026-10-05"
    assert value_of(user, "task-interval-1-start-time") == "09:00"
    assert value_of(user, "task-interval-1-progress") == 60
    user.find(marker="task-save").click()
    assert saved[0].actuals == two


async def test_a_row_can_be_removed(user: User) -> None:
    saved: list[Task] = []
    two = [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
    ]
    mount_dialog(Task("旧", actuals=list(two)), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-0-remove").click()
    await user.should_not_see(marker="task-interval-0-start-date")
    user.find(marker="task-save").click()
    assert saved[0].actuals == two[1:]


async def test_empty_rows_are_ignored_on_save(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12))]), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-0-remove").click()
    user.find(marker="task-interval-add").click()  # 空の行だけを残す
    user.find(marker="task-save").click()
    assert saved[0].actuals == []


async def test_overlapping_rows_show_the_error_and_keep_the_dialog(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 1, "2026-10-05 11:00", "2026-10-05 13:00")
    user.find(marker="task-save").click()
    await user.should_see("区間 2: 前の区間と重なっています")
    assert saved == []


async def test_the_error_row_number_follows_the_position_after_a_removal(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    for _ in range(3):
        user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    interval_inputs(user, 1, "2026-10-06 09:00", "2026-10-06 12:00")
    interval_inputs(user, 2, "2026-10-06 11:00", "2026-10-06 13:00")
    user.find(marker="task-interval-0-remove").click()  # 残りは 2 行。重なりは 2 行目
    user.find(marker="task-save").click()
    await user.should_see("区間 2: 前の区間と重なっています")


async def test_a_half_typed_row_names_its_number(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    user.find(marker="task-interval-0-start-date").type("2026-10-05")  # 時刻がない
    user.find(marker="task-save").click()
    await user.should_see("区間 1: 日付と時刻を両方入れてください")


async def test_an_open_interval_in_the_middle_of_a_hand_edited_file_blocks_saving(user: User) -> None:
    saved: list[Task] = []
    broken = [
        Actual(datetime(2026, 10, 5, 9), None),
        Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
    ]
    mount_dialog(Task("旧", actuals=broken), saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-save").click()
    await user.should_see("区間 1: 終了のない区間は最後の1つだけにしてください")
    assert saved == []


async def test_interval_mode_suggests_paused_when_the_last_interval_ended(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00")
    assert value_of(user, "task-status") == Status.RUNNING
    user.find(marker="task-interval-0-end-date").type("2026-10-05")
    user.find(marker="task-interval-0-end-time").type("12:00")
    assert value_of(user, "task-status") == Status.PAUSED
    user.find(marker="task-interval-0-progress").type("100")
    assert value_of(user, "task-status") == Status.DONE


async def test_interval_mode_suggestion_follows_the_last_row(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 0, "2026-10-05 09:00", "2026-10-05 12:00")
    assert value_of(user, "task-status") == Status.PAUSED
    user.find(marker="task-interval-add").click()
    interval_inputs(user, 1, "2026-10-06 09:00")
    assert value_of(user, "task-status") == Status.RUNNING


async def test_adding_a_row_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-cancel").click()
    await user.should_not_see(marker="close-save")  # 変更なしなら、確認なしで閉じる
    await open_dialog(user)
    user.find(marker="task-interval-add").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_simple_mode_keeps_two_actuals_read_only_with_the_mode_argument(user: User) -> None:
    kept = [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9), None),
    ]
    mount_dialog(Task("旧", actuals=list(kept)), [], actual_mode=ActualMode.SIMPLE)
    await open_dialog(user)
    await user.should_see(marker="task-actuals-readonly")
    await user.should_not_see(marker="task-interval-add")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_task_dialog.py -q -k "interval or rows or row_number or half_typed or open_interval or empty_rows or two_actuals_are_editable or adding_a_row or paused"`
Expected: FAIL(`open_task_dialog() got an unexpected keyword argument 'actual_mode'`)

- [ ] **Step 3: 実装する**

`task_dialog.py`:

(a) インポートに `ActualRow`(`projectapp.forms`)と `ActualMode`(`projectapp.models`)を足し、`from dataclasses import dataclass` を足す。

(b) `add_picker` の下に、日付と時刻の入力の組を切り出す。

```python
def moment_column(
    label: str, mark: str, picker: str, moment: datetime | None
) -> tuple[ui.input, ui.input]:
    """実績の日付と時刻の入力の組。マーカーは `{mark}-date` と `{mark}-time`。"""
    with ui.column().classes("flex-1 gap-0"):
        day = ui.input(f"{label}の日付", value=moment.strftime("%Y-%m-%d") if moment else "")
        day.classes("w-full").mark(f"{mark}-date")
        add_picker(day, ui.date, "event", f"{picker}-date", "%Y-%m-%d")
        clock = ui.input(f"{label}の時刻", value=moment.strftime("%H:%M") if moment else "")
        clock.classes("w-full").mark(f"{mark}-time")
        add_picker(clock, ui.time, "access_time", f"{picker}-time", "%H:%M")
    return day, clock
```

(c) `ActualFields._column` を委譲に置き換える。

```python
    def _column(self, label: str, key: str, moment: datetime | None) -> tuple[ui.input, ui.input]:
        return moment_column(label, f"task-actual-{key}", f"actual-{key}", moment)
```

(d) `ActualFields` に `bind` を足す。

```python
    def bind(self, callback: Callable[[object], None]) -> None:
        """入力が変わったときに呼ぶ関数を、すべての入力に付ける。"""
        for widget in self.inputs():
            widget.on_value_change(callback)
```

(e) `ActualFields` の下に `IntervalFields` を足す。

```python
@dataclass
class IntervalRow:
    card: ui.card
    start_day: ui.input
    start_time: ui.input
    end_day: ui.input
    end_time: ui.input
    progress: ui.number


class IntervalFields:
    """実績の区間を、行を足していく形で入力する(記録方式が「区間」のとき)。
    ActualFields と同じ呼び出し口(bind / filled / progress_value / state)にそろえる。
    状態の提案は、最後の行で判定する。"""

    read_only = False

    def __init__(self, task: Task) -> None:
        self._rows: list[IntervalRow] = []
        self._counter = 0  # マーカーの番号。行を削除しても詰めない
        self._on_change: Callable[[object], None] | None = None
        ui.label("実績(区間)").classes("text-caption text-grey")
        self._container = ui.column().classes("w-full gap-2")
        for actual in task.actuals:
            self._add_row(actual)
        ui.button("区間を追加", icon="add", on_click=lambda: self._add_row(None)).props(
            "flat dense"
        ).mark("task-interval-add")

    def _add_row(self, actual: Actual | None) -> None:
        n = self._counter
        self._counter += 1
        with self._container:
            with ui.card().classes("w-full").props("flat bordered") as card:
                with ui.row().classes("w-full no-wrap gap-4"):
                    start_day, start_time = moment_column(
                        "開始",
                        f"task-interval-{n}-start",
                        f"interval-{n}-start",
                        actual.start if actual else None,
                    )
                    end_day, end_time = moment_column(
                        "終了",
                        f"task-interval-{n}-end",
                        f"interval-{n}-end",
                        actual.end if actual else None,
                    )
                progress = (
                    ui.number(
                        "進捗度(%)",
                        value=actual.progress if actual else None,
                        min=MIN_PROGRESS,
                        max=MAX_PROGRESS,
                        precision=0,
                    )
                    .classes("w-full")
                    .mark(f"task-interval-{n}-progress")
                )
                ui.button(
                    "削除", icon="delete", on_click=lambda c=card: self._remove(c)
                ).props("flat dense color=negative").mark(f"task-interval-{n}-remove")
        row = IntervalRow(card, start_day, start_time, end_day, end_time, progress)
        self._rows.append(row)
        if self._on_change is not None:
            for widget in self._widgets(row):
                widget.on_value_change(self._on_change)
            self._on_change(None)

    def _remove(self, card: ui.card) -> None:
        self._rows = [row for row in self._rows if row.card is not card]
        card.delete()
        if self._on_change is not None:
            self._on_change(None)

    @staticmethod
    def _widgets(row: IntervalRow) -> list[ui.input | ui.number]:
        return [row.start_day, row.start_time, row.end_day, row.end_time, row.progress]

    def bind(self, callback: Callable[[object], None]) -> None:
        self._on_change = callback
        for widget in self.inputs():
            widget.on_value_change(callback)

    def inputs(self) -> list[ui.input | ui.number]:
        return [widget for row in self._rows for widget in self._widgets(row)]

    def rows(self) -> list[ActualRow]:
        """保存用の入力。日付と時刻の片方だけの行は、「区間 N: …」のエラーにする(N は現在の位置)。"""
        result: list[ActualRow] = []
        for number, row in enumerate(self._rows, start=1):
            try:
                start = compose_actual(row.start_day.value or "", row.start_time.value or "")
                end = compose_actual(row.end_day.value or "", row.end_time.value or "")
            except ValueError as exc:
                raise ValueError(f"区間 {number}: {exc}") from None
            result.append((start, end, row.progress.value))
        return result

    def start_text(self) -> str:
        return ""  # 区間は rows() を使う

    def end_text(self) -> str:
        return ""  # 区間は rows() を使う

    def filled(self) -> tuple[bool, bool]:
        """最後の区間の、開始・終了の日付と時刻がそろっているか(状態の提案に使う)。"""
        if not self._rows:
            return False, False
        last = self._rows[-1]
        return (
            _parses(last.start_day.value, last.start_time.value),
            _parses(last.end_day.value, last.end_time.value),
        )

    def progress_value(self) -> float | None:
        return self._rows[-1].progress.value if self._rows else None

    def state(self) -> tuple[object, ...]:
        """変更の判定に使う入力値。行の数と、各行の値(進捗度は 0 と空を区別する)。"""
        values: list[object] = [len(self._rows)]
        for row in self._rows:
            values += [
                row.start_day.value or "",
                row.start_time.value or "",
                row.end_day.value or "",
                row.end_time.value or "",
                row.progress.value,
            ]
        return tuple(values)
```

(f) `open_task_dialog` を変える。シグネチャの `members` の下に `actual_mode: ActualMode = ActualMode.SIMPLE,` を足す。`actual_fields = ActualFields(initial)` を次に置き換える。

```python
        intervals = actual_mode is ActualMode.INTERVALS
        actual_fields: ActualFields | IntervalFields = (
            IntervalFields(initial) if intervals else ActualFields(initial)
        )
```

`on_actual_change` の `suggest_status(...)` 呼び出しを次にする。

```python
            suggested = suggest_status(
                *actual_fields.filled(), actual_fields.progress_value(), intervals=intervals
            )
```

`for widget in actual_fields.inputs(): widget.on_value_change(on_actual_change)` を `actual_fields.bind(on_actual_change)` に置き換える。`save()` の `build_task(...)` に `actual_rows=actual_fields.rows() if isinstance(actual_fields, IntervalFields) else None,` を足す(`actual_progress=...` の下)。

`views.py`: `add_task`、`add_top_task`、`edit_task` の `open_task_dialog(...)` に `actual_mode=self.project.actual_mode,` を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_task_dialog.py test/test_views.py -q`
Expected: PASS(既存の実績・進捗度のテストも通る)

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/task_dialog.py src/projectapp/views.py test/test_task_dialog.py
git commit -m "タスク編集ダイアログで、実績を複数の区間として入力できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 区間の間の点線(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`ACTUAL_GAP_BACKGROUND` と、`actual_bars` の点線)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `interval_span`、`STATUS_CLASSES`(既存)
- Produces: マーカー `actual-gap-{key}-{ti}-{n}`(`n` は、前側の区間の番号。`key` は `"top"` かセクション番号)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の末尾に追加する(`actual_project`、`mount`、`BASE`、`STATUS_CLASSES` は既存)。

```python
async def test_a_dashed_line_joins_two_intervals(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
        )
    )
    await user.open("/")
    gap = user.find(marker="actual-gap-0-0-0").elements.pop()
    assert gap._style["left"] == "220.0px"  # 前の区間の終了 10/5 12:00 = 0.5日
    assert gap._style["width"] == "75.0px"  # 次の開始 10/7 9:00 = 2.375日。(2.375 - 0.5) * 40
    assert gap._style["top"] == f"{ACTUAL_TOP_PX}px"
    assert gap._style["height"] == f"{ACTUAL_HEIGHT_PX}px"
    assert "repeating-linear-gradient" in gap._style["background"]
    assert "var(--scolor)" in gap._style["background"]
    assert STATUS_CLASSES[Status.NOT_STARTED] in gap.classes


async def test_there_is_one_line_per_gap(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
            Actual(datetime(2026, 10, 7, 9), None),
        ),
        now=datetime(2026, 10, 7, 12),
    )
    await user.open("/")
    await user.should_see(marker="actual-gap-0-0-0")
    await user.should_see(marker="actual-gap-0-0-1")
    await user.should_not_see(marker="actual-gap-0-0-2")


async def test_no_line_without_a_gap(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 5, 15)),  # 隙間なし
        )
    )
    await user.open("/")
    await user.should_not_see(marker="actual-gap-0-0-0")


async def test_no_line_and_no_crash_for_a_hand_edited_overlap_or_open_interval(user: User) -> None:
    mount(
        actual_project(
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 15)),
            Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 5, 18)),  # 重なり
            Actual(datetime(2026, 10, 4, 9), None),  # 逆順で進行中
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),  # 進行中の後ろ
        ),
        now=datetime(2026, 10, 6, 15),
    )
    await user.open("/")
    await user.should_see(marker="actual-0-0-3")
    await user.should_not_see(marker="actual-gap-0-0-0")
    await user.should_not_see(marker="actual-gap-0-0-1")
    await user.should_not_see(marker="actual-gap-0-0-2")


async def test_the_line_is_in_the_status_color(user: User) -> None:
    project = actual_project(
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
    )
    project.sections[0].tasks[0].status = Status.PAUSED
    mount(project)
    await user.open("/")
    gap = user.find(marker="actual-gap-0-0-0").elements.pop()
    assert STATUS_CLASSES[Status.PAUSED] in gap.classes
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "dashed or one_line_per or no_line or the_line_is"`
Expected: FAIL(`actual-gap-0-0-0` が見つからない)

- [ ] **Step 3: 実装する**

`gantt.py` の定数(`STATUS_COLOR_VAR` の下)に追加する。

```python
# 実績の区間の間(休んでいた期間)の点線。実績の棒の中央の高さに、1px の破線を引く
ACTUAL_GAP_BACKGROUND = (
    f"repeating-linear-gradient(90deg, {STATUS_COLOR_VAR} 0 4px, transparent 4px 8px)"
    " center / 100% 1px no-repeat"
)
```

`actual_bars` の `for n, actual in enumerate(task.actuals):` ループのあと(同じメソッドの最後)に追加する。

```python
        for n in range(len(task.actuals) - 1):
            before, after = task.actuals[n], task.actuals[n + 1]
            if before.end is None or after.start <= before.end:
                continue  # 進行中の区間の後ろ、隙間なし、重なり・逆順(手で編集したファイル)は引かない
            left, length = interval_span(before.end, after.start, columns)
            gap = ui.element("div").style(
                f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                f" width: {length * width:.1f}px;"
                f" top: {ACTUAL_TOP_PX}px; height: {ACTUAL_HEIGHT_PX}px;"
                f" background: {ACTUAL_GAP_BACKGROUND}; cursor: pointer; user-select: none"
            ).classes(STATUS_CLASSES[task.status])
            gap.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
            gap.mark(f"actual-gap-{key}-{ti}-{n}")
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py -q`
Expected: PASS

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "実績の区間の間に点線を引く

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ドキュメントと作業記録、全体の確認

**Files:**
- Modify: `CLAUDE.md`(projectapp。「ガントチャート」の節)
- Modify: `docs/development.md`
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: `CLAUDE.md` に 2 行を足す**

「`予定`と`実績`管理ができ、…」の行の下に追加する。

```markdown
- 実績の記録方式を、設定ダイアログでプロジェクトごとに`簡易`(1区間)・`区間`(複数)から選べる。区間では、タスク編集ダイアログで区間の行を足していく(開始の早い順・重ならない・終了のない区間は最後の1つだけ)。2区間以上のタスクがあるあいだは、簡易へ戻せない
- 実績の区間の間(休んでいた期間)は、ガントチャートで細い点線で結ぶ
```

- [ ] **Step 2: `docs/development.md` に説明を足す**

実績に関する既存の記述の近くに、次の内容を足す(既存の文体にそろえる)。

- `Project.actual_mode`(`ActualMode`。`"simple"` / `"intervals"`。キーのない古いファイルは `simple`、不正な値は読込を拒否)。実績の保存形式は方式にかかわらず区間のリスト。
- 検証は `forms.build_actual_intervals`(すべて空の行は無視、行番号は数える。開始の昇順、重ならない、終了のない区間は最後の1つだけ、進捗度は前の入力以上)。読込では、重なりと並び順を検証しない。
- `suggest_status(..., intervals=True)` は、最後の区間が終わっていて進捗度が100でなければ一時停止、100なら終了を提案する。
- ダイアログは `IntervalFields`(区間)と `ActualFields`(簡易)。簡易で2区間以上のタスクは読み取り専用。
- 点線は `gantt.actual_bars` が、隣り合う区間の隙間(前の終了 < 次の開始)にだけ引く(`ACTUAL_GAP_BACKGROUND`。マーカー `actual-gap-<key>-<ti>-<n>`)。
- 設定ダイアログは、区間から簡易へ戻す選択を、2区間以上のタスクがあるあいだは区間へ戻す。

- [ ] **Step 3: 全体のテストと型チェック**

Run: `uv run pytest -q`(約3分。バックグラウンドで実行して、終わりを待つ)
Expected: すべて PASS(824 件 + 新しいテスト)

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 4: `.claude/MEMORY.md` を更新する**

- 先頭の「最終更新」を、要望15の実装(`feature/actual-intervals`、未マージ)に直す。
- 「現在の状況」の先頭に、要望15の実装の記録を足す: ブランチ、設計書 `2026-10-05-actual-intervals-design.md`、実装計画 `2026-10-05-actual-intervals.md`、テストの件数、方式(`actual_mode`、`IntervalFields`、点線)、`develop` へは未マージ・未プッシュ、実機での確認はこれから、保留(区間が多いときのダイアログの縦の長さ、区間ごとの進捗度の見た目)。
- 「今後の要望」の 15 の行に `(完了)` を付ける。1 の行にも `(完了)` を付ける(進捗度は実装済み。付け忘れの訂正)。
- 「次にやること」の「後続のサブプロジェクト」から、要望15に当たる項目があれば更新する。
- 「参照先」に、設計書と実装計画を足す。

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md
git commit -m "作業記録: 実績の複数区間と記録方式の設定の実装を反映

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実機での確認用のデータは、`~/.projectapp/` に新しいファイルとして作る(既存のファイルを上書きしない)。
