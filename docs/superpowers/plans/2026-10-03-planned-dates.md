# 開始予定・完了予定・締切 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの「開始」「終了」を「開始予定」「完了予定」に改め、締切(納期)を足す。完了予定は保存せず、開始予定・工数・稼働設定・祝日からその都度計算する。

**Architecture:** `Task` を `planned_start` / `planned_end` / `planned_end_manual` / `deadline` に改め、完了予定は純粋関数 `effective_end`(`timeline.py`)で求める。`end_auto`・`fill_end`・`recalc_ends` は削除する。古いファイルは読み込み時に変換する(旧 `end` は締切)。ガントは `effective_end` で棒を描き、締切に「◆」を出す。

**Tech Stack:** Python 3.13、NiceGUI 3.17、pytest(`uv run pytest -q`)、型チェック `uvx ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-03-planned-dates-design.md`

## Global Constraints

- 言語は日本語。画面の文言、エラー文、コメント、コミットメッセージは日本語。識別子は英語。
- ブランチは `feature/planned-dates`(設計書をコミット済み)を本体とする。関心ごとに `feature/planned-dates-<関心ごと>` を本体から切り、テストが通ってから `git merge --no-ff` で本体に戻す(`feature/planned-dates/…` は Git の参照名の制約で作れない)。`develop` へのマージとプッシュは、ユーザーの許可を得てから行う。
- 各タスクの終わりで `uv run pytest -q` と `uvx ty check src` が通ること。
- コミットメッセージの末尾に、次の行を付ける: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- 完了予定は保存しない値を基本とし、手で指定するときだけ `planned_end` を使う。工数が 0 以下のときは `planned_end` を直接使う。空なら開始予定の1日後(同じ時刻)。
- 予定超過は、状態が「終了」でないタスクが、締切か完了予定のどちらかを過ぎたとき(1色)。
- 締切は開始予定より前でもよい。完了予定は、有効なとき(工数 0 以下、または手で指定)だけ、開始予定以降を要求する。
- 年は 2000〜2100 の範囲(開始予定・完了予定・締切の3つとも)。タイムゾーン付きの日時と、負・NaN・inf の工数は拒否する。
- 時刻を指定しないときの時刻: 開始予定は始業、完了予定と締切は `default_times` の終了側(始業 + 8h + 昼休憩 1h)。
- マーカー(`.mark`)のキーは、内部の呼び名 `start` / `end` / `deadline` のまま(画面の文言だけ変える)。
- 実績の「開始」「終了」は項目を持たない(後続機能)。

## Review Focus

仕様が含意するが、どのタスクのテストにも直接は出ない入力。各行のテストは、持ち主のタスクに入れてある。

1. 手編集のファイルの `planned_end_manual` が bool でない(`"true"`、`1`、`null`)→ 偽として読む(Task 4)。
2. 旧形式で `end` だけあり `start` がない → 開始予定なし・締切ありで読み、棒は出ない(Task 4)。
3. 工数が inf、または開始予定が `datetime.max` → 例外にせず、完了予定が翌日または `None` になる(Task 3)。
4. 手編集で完了予定が開始予定より前 → 細い棒で出て、表示範囲の計算も落ちない(Task 4)。
5. 締切が表示範囲の外、または開始予定のないタスクに締切だけある → 外なら目印なし、開始予定がなくても目印は出る(Task 6)。
6. ダイアログで「手で指定」がオンのまま工数を 0 または空にする → 完了予定の欄は編集できる状態に戻り、`planned_end_manual` は偽で保存される(Task 5)。

---

## Task 1: `start` を `planned_start` に改名する

**Branch:** `feature/planned-dates-rename`

**Files:**
- Modify: `src/projectapp/models.py`、`src/projectapp/storage.py`、`src/projectapp/timeline.py`、`src/projectapp/forms.py`、`src/projectapp/task_dialog.py`、`src/projectapp/gantt.py`(`grep` で出た箇所)
- Modify: `test/*.py`(`Task(` の `start=` と、タスクの `.start` 参照)
- Test: `test/test_storage.py`

**Interfaces:**
- Produces: `Task.planned_start: datetime | None`。保存は `planned_start` キー。読み込みは `planned_start`、なければ旧 `start` を読む。`build_task` の引数名 `start` は、このタスクでは変えない(Task 4 で変える)。

- [ ] **Step 1: ブランチを切る**

```bash
cd /Users/jun/Documents/opt/work/projectapp
git checkout feature/planned-dates
git checkout -b feature/planned-dates-rename
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_storage.py` の末尾に追加する(`json`、`datetime`、`Project`、`Task`、`save_project`、`load_project` は既に import 済み)。

```python
def test_planned_start_is_saved_and_the_legacy_start_key_is_still_read(tmp_path: Path) -> None:
    project = Project("p", tasks=[Task("a", planned_start=datetime(2026, 10, 5, 9))])
    path = save_project(project, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tasks"][0]["planned_start"] == "2026-10-05T09:00:00"
    assert "start" not in data["tasks"][0]

    legacy = dict(data["tasks"][0])
    legacy["start"] = legacy.pop("planned_start")
    data["tasks"][0] = legacy
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(path).tasks[0].planned_start == datetime(2026, 10, 5, 9)
```

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_storage.py::test_planned_start_is_saved_and_the_legacy_start_key_is_still_read -q`
Expected: FAIL(`Task` に `planned_start` がない)

- [ ] **Step 4: モデルを改名する**

`src/projectapp/models.py` の `Task`:

```python
    planned_start: datetime | None = None
```
(`start: datetime | None = None` をこれに置き換える)

- [ ] **Step 5: 保存・読み込みを直す**

`src/projectapp/storage.py` の `_task` の `start=_datetime(raw.get("start")),` を、次に置き換える。

```python
        planned_start=_datetime(raw.get("planned_start", raw.get("start"))),  # 旧形式は start
```

- [ ] **Step 6: 残りの本体を機械的に改名する**

```bash
grep -n "\.start\b\|\bstart=" src/projectapp/*.py
```

出た行のうち、**タスクの開始**を指すものだけを `planned_start` にする。ルール:
- `task.start`、`existing.start`、`initial.start`、`replace(base, start=…)`、`Task(…, start=…)` → `planned_start`
- `column.start`、`c.start`、`Column(start=…)`、`work_start`、`build_task` の引数 `start=`(`forms.py` の `build_task` のシグネチャと、`task_dialog.py` の `build_task(... start=fields.start_text(), ...)` の呼び出し)、`DateTimeFields` の `start` は**変えない**。

`forms.py` の `build_task` の本体では、`replace(base, … start=start_at, …)` のキーだけ `planned_start=start_at` にし、`existing.start` を `existing.planned_start` にする。`timeline.py` の `visible_range`・`bar_span`・`fill_end`・`recalc_ends` の `task.start` も同様。

- [ ] **Step 7: テストを機械的に改名する**

```bash
grep -n "start=" test/*.py | grep -v "work_start\|column"
grep -n "\.start\b" test/*.py | grep -v "column\|c\.start\|columns\["
```

ルールは Step 6 と同じ。`Task(` の中の `start=` と、タスクの `.start` 参照だけを `planned_start` にする。`make(start=…)`、`build_task(start=…)` の呼び出しは変えない。

- [ ] **Step 8: テストと型チェックを通す**

Run: `uv run pytest -q && uvx ty check src`
Expected: すべて PASS。失敗が出たら、`AttributeError` / `TypeError` の箇所が改名漏れなので、そのルールに従って直す。

- [ ] **Step 9: コミットして本体にマージする**

```bash
git add -A
git commit -m "タスクの start を planned_start に改名する(旧 start キーも読める)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/planned-dates
git merge --no-ff feature/planned-dates-rename -m "start の改名をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 2: 締切(`deadline`)を足す

**Branch:** `feature/planned-dates-deadline`

**Files:**
- Modify: `src/projectapp/models.py`、`src/projectapp/forms.py`(`build_task`)、`src/projectapp/timeline.py`(`is_overdue`)
- Test: `test/test_storage.py`、`test/test_forms.py`、`test/test_timeline.py`

**Interfaces:**
- Consumes: Task 1 の `Task.planned_start`。
- Produces: `Task.deadline: datetime | None`(末尾に追加)。`build_task(..., deadline: str | None = None)`:`None` は既存の締切を保つ、文字列は解析して置き換える(空文字は `None`)。`is_overdue(task, now)` は、締切を過ぎていれば `True` も返す(この時点の署名)。ダイアログに締切の欄はまだ出さない(Task 5)。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/planned-dates
git checkout -b feature/planned-dates-deadline
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_storage.py` の末尾:

```python
def test_deadline_roundtrip(tmp_path: Path) -> None:
    project = Project(
        "d",
        sections=[Section("s", [Task("a", deadline=datetime(2026, 10, 9, 18, 0)), Task("b")])],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [t.deadline for t in loaded.sections[0].tasks] == [datetime(2026, 10, 9, 18, 0), None]
```

`test/test_forms.py` の末尾(`make` は既存のヘルパー。`deadline` は `build_task` のキーワードに渡る):

```python
def test_deadline_is_parsed_and_may_precede_the_start() -> None:
    task = make(deadline="2026-10-01T18:00")
    assert task.deadline == datetime(2026, 10, 1, 18, 0)  # 開始予定(10/5)より前でもよい


def test_blank_deadline_clears_it_and_none_keeps_it() -> None:
    existing = Task("旧", deadline=datetime(2026, 10, 9, 18))
    assert make(existing, deadline="").deadline is None
    values = {"deadline": None}
    assert make(existing, **values).deadline == datetime(2026, 10, 9, 18)


@pytest.mark.parametrize("deadline", ["1999-12-31T18:00", "2101-01-01T00:00"])
def test_deadline_year_is_limited(deadline: str) -> None:
    with pytest.raises(ValueError, match="年は"):
        make(deadline=deadline)


def test_deadline_rejects_a_bad_format_and_a_timezone() -> None:
    for bad in ("abc", "2026-10-05T18:00+09:00"):
        with pytest.raises(ValueError, match="日時"):
            make(deadline=bad)
```

`test/test_timeline.py` の末尾:

```python
def test_is_overdue_when_the_deadline_has_passed() -> None:
    task = Task("t", deadline=datetime(2026, 10, 1, 18), status=Status.RUNNING)
    assert is_overdue(task, datetime(2026, 10, 2)) is True
    assert is_overdue(task, datetime(2026, 10, 1, 17)) is False


def test_is_not_overdue_by_deadline_when_done() -> None:
    task = Task("t", deadline=datetime(2026, 10, 1, 18), status=Status.DONE)
    assert is_overdue(task, datetime(2026, 10, 2)) is False
```

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_storage.py test/test_forms.py test/test_timeline.py -q`
Expected: FAIL(`deadline` がない)

- [ ] **Step 4: モデルに足す**

`src/projectapp/models.py` の `Task` の末尾(`end_auto` の次)に追加:

```python
    deadline: datetime | None = None  # 締切(納期)
```

- [ ] **Step 5: `build_task` を直す**

`src/projectapp/forms.py` の `build_task` の引数の末尾に `deadline: str | None = None,` を足し、解析と検証の部分を次のようにする。

```python
    try:
        start_at, end_at = parse_datetime(start), parse_datetime(end)
        deadline_at = parse_datetime(deadline) if deadline is not None else None
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    for moment in (start_at, end_at, deadline_at):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
```

`return replace(base, …)` に、キーワードを1つ足す。

```python
        deadline=base.deadline if deadline is None else deadline_at,
```

- [ ] **Step 6: `is_overdue` を直す**

`src/projectapp/timeline.py`:

```python
def is_overdue(task: Task, now: datetime) -> bool:
    """終了予定か締切を過ぎていて、状態が「終了」でない。"""
    if task.status is Status.DONE:
        return False
    if task.deadline is not None and now > task.deadline:
        return True
    return task.end is not None and now > task.end
```

- [ ] **Step 7: 通す**

Run: `uv run pytest -q && uvx ty check src`
Expected: PASS

- [ ] **Step 8: コミットして本体にマージする**

```bash
git add -A
git commit -m "タスクに締切(deadline)を足し、締切超過も予定超過にする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/planned-dates
git merge --no-ff feature/planned-dates-deadline -m "締切の追加をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 3: 完了予定の項目と `effective_end` を足す(足すだけ)

**Branch:** `feature/planned-dates-effective-end`(Task 4 も同じブランチで続ける)

**Files:**
- Modify: `src/projectapp/models.py`、`src/projectapp/timeline.py`
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: `calc_end`(既存)、`Project.daily_hours`、`Project.work_start`。
- Produces:
  - `Task.planned_end: datetime | None = None`、`Task.planned_end_manual: bool = False`
  - `computed_end(start: datetime | None, effort_hours: float, daily_hours: float, work_start: time, holidays: dict[date, str]) -> datetime | None`(規則 3・4・5)
  - `effective_end(task: Task, project: Project, holidays: dict[date, str]) -> datetime | None`(規則 1〜5)

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/planned-dates
git checkout -b feature/planned-dates-effective-end
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_timeline.py` の import に `Project`、`computed_end`、`effective_end` が無ければ足し、末尾に追加する(開始 2026-10-09(金)9:00 から工数 15h・1日 6.5h の完了は、祝日なしで 10/13 11:00)。

```python
FRI_START = datetime(2026, 10, 9, 9, 0)
MANUAL_END = datetime(2026, 10, 20, 18, 0)


def eff(project: Project | None = None, holidays: dict[date, str] | None = None, **fields: object) -> datetime | None:
    values: dict[str, object] = {"planned_start": FRI_START}
    values.update(fields)
    task = Task("t", **values)  # type: ignore[arg-type]
    return effective_end(task, project or Project("p"), holidays or {})


def test_effective_end_uses_planned_end_when_there_is_no_effort() -> None:
    assert eff(planned_end=MANUAL_END) == MANUAL_END


def test_effective_end_ignores_planned_end_when_effort_is_not_manual() -> None:
    assert eff(planned_end=MANUAL_END, effort_hours=15.0) == datetime(2026, 10, 13, 11)


def test_effective_end_uses_planned_end_when_manual() -> None:
    assert eff(planned_end=MANUAL_END, planned_end_manual=True, effort_hours=15.0) == MANUAL_END


def test_effective_end_computes_when_manual_but_planned_end_is_empty() -> None:
    assert eff(planned_end_manual=True, effort_hours=15.0) == datetime(2026, 10, 13, 11)


def test_effective_end_follows_the_project_settings_and_holidays() -> None:
    project = Project("p", daily_hours=8.0)
    assert eff(project, effort_hours=15.0) == datetime(2026, 10, 12, 16)
    assert eff(holidays={date(2026, 10, 12): "祝日"}, effort_hours=15.0) == datetime(2026, 10, 14, 11)
    project.work_start = time(10, 0)
    assert eff(project, effort_hours=15.0) == datetime(2026, 10, 13, 12)


def test_effective_end_is_the_next_day_without_effort_and_planned_end() -> None:
    assert eff() == datetime(2026, 10, 10, 9, 0)


@pytest.mark.parametrize("effort", [float("inf"), float("nan"), 10**9])
def test_effective_end_falls_back_to_the_next_day_when_it_cannot_compute(effort: float) -> None:
    assert eff(effort_hours=effort) == datetime(2026, 10, 10, 9, 0)


def test_effective_end_is_none_without_a_start() -> None:
    assert eff(planned_start=None) is None
    assert eff(planned_start=None, effort_hours=8.0) is None


def test_effective_end_returns_planned_end_even_without_a_start() -> None:
    assert eff(planned_start=None, planned_end=MANUAL_END) == MANUAL_END


def test_effective_end_does_not_crash_at_the_end_of_time() -> None:
    assert eff(planned_start=datetime.max) is None


def test_computed_end_ignores_planned_end_fields() -> None:
    assert computed_end(FRI_START, 15.0, 6.5, time(9, 0), {}) == datetime(2026, 10, 13, 11)
    assert computed_end(None, 15.0, 6.5, time(9, 0), {}) is None
```

(`pytest`、`date`、`time`、`datetime`、`Task` は既存の import を使う。足りなければ足す。)

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_timeline.py -q`
Expected: FAIL(`effective_end` が import できない)

- [ ] **Step 4: 項目を足す**

`src/projectapp/models.py` の `Task` の `deadline` の次に追加:

```python
    planned_end: datetime | None = None  # 完了予定の手入力値
    planned_end_manual: bool = False  # 工数があるときに、完了予定を手で指定するか
```

- [ ] **Step 5: 関数を足す**

`src/projectapp/timeline.py` の `calc_end`/`_calc_end` の後(`fill_end` の前)に追加:

```python
def computed_end(
    start: datetime | None,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
) -> datetime | None:
    """手入力を使わない完了予定。工数があれば算出し、算出できなければ開始予定の1日後。"""
    if start is None:
        return None
    if effort_hours > 0:
        end = calc_end(start, effort_hours, daily_hours, work_start, holidays)
        if end is not None:
            return end
    try:
        return start + timedelta(days=1)
    except OverflowError:
        return None


def effective_end(task: Task, project: Project, holidays: dict[date, str]) -> datetime | None:
    """完了予定。工数が無い、または手で指定のときは planned_end、それ以外は算出する。"""
    if task.planned_end is not None and (task.effort_hours <= 0 or task.planned_end_manual):
        return task.planned_end
    return computed_end(
        task.planned_start, task.effort_hours, project.daily_hours, project.work_start, holidays
    )
```

`task.effort_hours <= 0` は NaN で偽になる。NaN は「工数あり」側に倒れ、`computed_end` の `effort_hours > 0` も偽なので、翌日になる。テスト `test_effective_end_falls_back_to_the_next_day_when_it_cannot_compute[nan]` がこれを固定する(`planned_end` が空のときの結果)。

- [ ] **Step 6: 通す**

Run: `uv run pytest test/test_timeline.py -q && uvx ty check src`
Expected: PASS

- [ ] **Step 7: コミットする(マージは Task 4 のあと)**

```bash
git add -A
git commit -m "完了予定の項目(planned_end、手で指定)と effective_end を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 4: `end` / `end_auto` を完了予定に切り替える

**Branch:** `feature/planned-dates-effective-end`(Task 3 の続き)

**Files:**
- Modify: `src/projectapp/models.py`、`src/projectapp/storage.py`、`src/projectapp/timeline.py`、`src/projectapp/forms.py`、`src/projectapp/task_dialog.py`、`src/projectapp/gantt.py`、`src/projectapp/views.py`
- Modify/Test: `test/test_storage.py`、`test/test_timeline.py`、`test/test_forms.py`、`test/test_task_dialog.py`、`test/test_views.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: Task 1〜3 の `planned_start`、`deadline`、`planned_end`、`planned_end_manual`、`effective_end`、`computed_end`。
- Produces:
  - `Task` から `end`・`end_auto` を削除。
  - `is_overdue(task: Task, project: Project, holidays: dict[date, str], now: datetime) -> bool`
  - `visible_range(project: Project, holidays: dict[date, str] | None = None)`、`build_columns(project: Project, scale: Scale, holidays: dict[date, str] | None = None)`
  - `bar_span(start: datetime | None, end: datetime | None, columns: list[Column]) -> tuple[float, float] | None`
  - `build_task(existing, *, name, planned_start: str, planned_end: str, planned_end_manual: bool = False, deadline: str | None = None, effort_hours, priority, status, color, assignee)`(`planned_end_manual` は工数が 0 より大きいときだけ保存)
  - 削除: `fill_end`、`recalc_ends`、`Recalc`、`MainView.warn_unresolved`、`DateTimeFields` の `end_auto` 引数と終了のロック。
  - 読み込み: `planned_end_manual` キーがあれば新形式、なければ旧形式(旧 `end` は、`end_auto` が `true` のときは捨て、それ以外は締切)。

- [ ] **Step 1: 失敗するテストを書く(保存と読み込み)**

`test/test_storage.py` の末尾に追加する。

```python
def _legacy_file(tmp_path: Path, raw_task: dict[str, object]) -> Path:
    """新形式で保存したファイルの最初のタスクを、旧形式の項目で置き換える。"""
    path = save_project(Project("old", tasks=[Task("a")]), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = {
        k: v
        for k, v in data["tasks"][0].items()
        if k not in ("planned_start", "planned_end", "planned_end_manual", "deadline")
    }
    data["tasks"][0] = {**kept, **raw_task}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_legacy_manual_end_becomes_the_deadline(tmp_path: Path) -> None:
    path = _legacy_file(
        tmp_path,
        {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00", "end_auto": False},
    )
    task = load_project(path).tasks[0]
    assert task.planned_start == datetime(2026, 10, 5, 9)
    assert task.deadline == datetime(2026, 10, 7, 18)
    assert (task.planned_end, task.planned_end_manual) == (None, False)


def test_legacy_end_without_end_auto_is_treated_as_manual(tmp_path: Path) -> None:
    path = _legacy_file(tmp_path, {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00"})
    assert load_project(path).tasks[0].deadline == datetime(2026, 10, 7, 18)


def test_legacy_auto_end_is_dropped(tmp_path: Path) -> None:
    path = _legacy_file(
        tmp_path,
        {"start": "2026-10-05T09:00:00", "end": "2026-10-07T18:00:00", "end_auto": True},
    )
    assert load_project(path).tasks[0].deadline is None


def test_legacy_end_without_a_start_still_becomes_the_deadline(tmp_path: Path) -> None:
    path = _legacy_file(tmp_path, {"end": "2026-10-07T18:00:00", "end_auto": False})
    task = load_project(path).tasks[0]
    assert (task.planned_start, task.deadline) == (None, datetime(2026, 10, 7, 18))


def test_new_format_roundtrip_keeps_the_planned_fields(tmp_path: Path) -> None:
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 18),
        planned_end_manual=True,
        deadline=datetime(2026, 10, 12, 18),
        effort_hours=8.0,
    )
    loaded = load_project(save_project(Project("n", tasks=[task]), tmp_path)).tasks[0]
    assert loaded == task


def test_new_format_has_no_end_or_end_auto(tmp_path: Path) -> None:
    path = save_project(Project("n", tasks=[Task("a")]), tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))["tasks"][0]
    assert "end" not in saved and "end_auto" not in saved and "start" not in saved


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, []])
def test_planned_end_manual_that_is_not_a_bool_reads_as_false(
    value: object, tmp_path: Path
) -> None:
    path = save_project(Project("n", tasks=[Task("a", planned_end_manual=True)]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(planned_end_manual=value))
    assert load_project(path).tasks[0].planned_end_manual is False
```

さらに、旧テスト `test_end_auto_roundtrip`、`test_old_file_without_end_auto_reads_as_manual`、`test_end_auto_that_is_not_a_bool_reads_as_manual` は **削除**する(`end_auto` を参照するもの)。

- [ ] **Step 2: 失敗するテストを書く(日程計算)**

`test/test_timeline.py`:

- `fill_end`・`recalc_ends`・`Recalc` に関するテスト(`test_recalc_ends_*`、`test_fill_end_*`、`auto_task`、`AUTO_END` の定義)は **すべて削除**し、import から `fill_end`、`recalc_ends` を外す。
- `Task(` の `end=` は、完了予定の手入力なので `planned_end=` に直す(`start=` は Task 1 で済んでいる)。
- `bar_span` のテスト3つを、次に置き換える。

```python
def test_bar_span_in_day_scale() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 5, 12), planned_end=datetime(2026, 10, 7, 12))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task.planned_start, task.planned_end, columns) == (0.5, 2.0)


def test_bar_span_in_week_scale() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 12))
    columns = build_columns(project_with(task), Scale.WEEK)
    assert bar_span(task.planned_start, task.planned_end, columns) == (0.0, 1.0)


def test_bar_span_is_none_without_a_start_or_an_end() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert bar_span(None, datetime(2026, 10, 7), columns) is None
    assert bar_span(datetime(2026, 10, 7), None, columns) is None
```
(`test_bar_span_in_month_scale_is_proportional` も同じ形で `bar_span(task.planned_start, task.planned_end, columns)` に直す。)

- 次を追加する。

```python
def overdue_project() -> Project:
    return Project("p")


NOW = datetime(2026, 10, 10, 12)


def overdue(task: Task, project: Project | None = None, holidays: dict[date, str] | None = None) -> bool:
    return is_overdue(task, project or overdue_project(), holidays or {}, NOW)


def test_overdue_by_deadline() -> None:
    assert overdue(Task("t", deadline=datetime(2026, 10, 9, 18))) is True


def test_overdue_by_planned_end() -> None:
    assert overdue(Task("t", planned_start=datetime(2026, 10, 1, 9), planned_end=datetime(2026, 10, 2))) is True


def test_overdue_by_the_computed_end_without_a_planned_end() -> None:
    # 開始予定の1日後(10/2 9:00)を過ぎている
    assert overdue(Task("t", planned_start=datetime(2026, 10, 1, 9))) is True


def test_not_overdue_when_neither_has_passed() -> None:
    task = Task(
        "t", planned_start=datetime(2026, 10, 10, 9), deadline=datetime(2026, 10, 30), effort_hours=1.0
    )
    assert overdue(task) is False


def test_not_overdue_when_done_or_without_any_date() -> None:
    done = Task("t", planned_start=datetime(2026, 10, 1, 9), deadline=datetime(2026, 10, 2), status=Status.DONE)
    assert overdue(done) is False
    assert overdue(Task("t")) is False


def test_visible_range_uses_the_effective_end() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0)  # 完了予定は 10/13 11:00
    first, last = visible_range(project_with(task))
    assert last == date(2026, 10, 14)


def test_visible_range_survives_a_planned_end_before_the_start() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 9, 9), planned_end=datetime(2026, 10, 1, 9))
    first, last = visible_range(project_with(task))
    assert first == date(2026, 10, 1)

```
既存の `is_overdue` のテスト(旧署名 `is_overdue(task, now)`)は、新署名 `is_overdue(task, Project("p"), {}, now)` に直す。`visible_range`、`Project` が import に無ければ足す。

- [ ] **Step 3: 失敗するテストを書く(フォーム)**

`test/test_forms.py`:

- `make` を次の形に置き換える。

```python
def make(existing: Task | None = None, **overrides: object) -> Task:
    values: dict[str, object] = {
        "name": "設計",
        "planned_start": "2026-10-05T09:00",
        "planned_end": "2026-10-07T18:00",
        "planned_end_manual": False,
        "deadline": "",
        "effort_hours": 8.0,
        "priority": Priority.HIGH,
        "status": Status.RUNNING,
        "color": "#112233",
        "assignee": "",
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]
```
- `start=` / `end=` を渡しているテストは `planned_start=` / `planned_end=` に直す。`test_build_task_normalizes_input` の `task.start`/`task.end` は `task.planned_start`/`task.planned_end` に直す。
- `end_auto`、`SECONDS_END`、`auto_existing`、「再計算」「automatic end」を扱うテスト(`grep -n "end_auto\|SECONDS_END\|auto_existing\|automatic" test/test_forms.py` で出るもの)は **すべて削除**する。
- Task 2 で足した `make(existing, **values)` の `deadline: None` のテストは、`make` のキーワードが `deadline` を既定で `""` に持つので、`make(existing, deadline=None)` に直す。
- 次を追加する。

```python
def test_planned_end_before_the_start_is_rejected_without_effort() -> None:
    with pytest.raises(ValueError, match="完了予定は開始予定以降"):
        make(effort_hours=0.0, planned_end="2026-10-04T09:00")


def test_planned_end_before_the_start_is_rejected_when_manual() -> None:
    with pytest.raises(ValueError, match="完了予定は開始予定以降"):
        make(effort_hours=8.0, planned_end_manual=True, planned_end="2026-10-04T09:00")


def test_a_hidden_planned_end_is_not_validated() -> None:
    task = make(effort_hours=8.0, planned_end_manual=False, planned_end="2026-10-04T09:00")
    assert task.planned_end == datetime(2026, 10, 4, 9)  # 工数あり・手で指定なしなので無視される値
    assert task.planned_end_manual is False


def test_planned_end_manual_is_saved_only_with_effort() -> None:
    assert make(effort_hours=8.0, planned_end_manual=True).planned_end_manual is True
    assert make(effort_hours=0.0, planned_end_manual=True).planned_end_manual is False
    assert make(effort_hours=None, planned_end_manual=True).planned_end_manual is False


def test_planned_end_year_is_limited() -> None:
    with pytest.raises(ValueError, match="年は"):
        make(planned_end="2101-01-01T00:00")
```

- [ ] **Step 4: 失敗するテストを書く(画面)**

`test/test_views.py`:

- 次のテストは **削除**する: `test_fill_end_uses_the_loaded_holidays`、`test_apply_settings_recalculates_only_auto_ends`、`test_apply_settings_without_recalculated_tasks_shows_no_notification`、`test_editing_the_start_of_an_auto_end_task_recalculates_the_end`、`test_apply_settings_warns_about_ends_that_cannot_be_recalculated`、`test_refreshing_holidays_recalculates_auto_ends`、および `end_auto` を参照する保存・読込のテスト(`grep -n "end_auto" test/test_views.py`)。
- 次を追加する。

```python
async def test_apply_settings_rerenders_without_a_recalculation_notice(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    await user.should_see(marker="bar-top-0")
    before = user.find(marker="bar-top-0").elements.pop()._style["width"]
    await open_settings_and_apply(user, "8", "09:00")
    assert await wait_until(lambda: view.project.daily_hours == 8.0)
    after = user.find(marker="bar-top-0").elements.pop()._style["width"]
    assert after != before  # 稼働時間が変わると、完了予定が変わり、棒の長さが変わる
    assert not user.notify.contains("再計算")
    assert view.project.tasks[0].planned_end is None  # 完了予定は保存されない


async def test_refreshing_holidays_rerenders_the_bar(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_task(None, None, Task("a", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0))
    before = user.find(marker="bar-top-0").elements.pop()._style["width"]

    async def fake_download(base_dir: Path, transport: object = None) -> dict[date, str]:
        return {date(2026, 10, 12): "スポーツの日"}

    monkeypatch.setattr("projectapp.views.download_holidays", fake_download)
    await view.refresh_holidays()
    after = user.find(marker="bar-top-0").elements.pop()._style["width"]
    assert after != before
    assert user.notify.contains("祝日データを更新しました")
```
`test_refresh_holidays_survives_a_cache_write_failure` などの既存テストは、`end` を使っていなければそのまま。`Task(` の `end=` は `planned_end=` に直す。

- [ ] **Step 5: 失敗を確認する**

Run: `uv run pytest -q 2>&1 | tail -30`
Expected: FAIL / ERROR が多数(`end`、`end_auto`、署名の不一致)。ここから実装で通していく。

- [ ] **Step 6: モデルから `end` と `end_auto` を外す**

`src/projectapp/models.py` の `Task` から次の2行を削除する。

```python
    end: datetime | None = None
    end_auto: bool = False  # 終了が自動算出で、利用者が書き換えていない
```
(`end` は `planned_start` の次の行にある。位置は `grep -n "end" src/projectapp/models.py` で確認。)

- [ ] **Step 7: 読み込みを直す**

`src/projectapp/storage.py` の `_task` を次に置き換える。

```python
def _task(raw: dict[str, Any]) -> Task:
    if "planned_end_manual" in raw:  # 新形式
        planned_start = _datetime(raw.get("planned_start"))
        planned_end = _datetime(raw.get("planned_end"))
        manual = raw["planned_end_manual"] is True  # bool以外(手編集の誤り)は偽
        deadline = _datetime(raw.get("deadline"))
    else:  # 旧形式: start は開始予定、手入力の end は締切、自動算出の end は捨てる
        planned_start = _datetime(raw.get("planned_start", raw.get("start")))
        planned_end, manual = None, False
        legacy_end = None if raw.get("end_auto") is True else _datetime(raw.get("end"))
        deadline = legacy_end or _datetime(raw.get("deadline"))
    return Task(
        name=raw["name"],
        planned_start=planned_start,
        planned_end=planned_end,
        planned_end_manual=manual,
        deadline=deadline,
        effort_hours=raw["effort_hours"],
        priority=Priority(raw["priority"]),
        status=Status(raw["status"]),
        color=raw["color"],
        assignee=raw.get("assignee"),
        predecessors=list(raw["predecessors"]),
    )
```

- [ ] **Step 8: 日程計算を直す**

`src/projectapp/timeline.py`:

1. `from dataclasses import dataclass, replace` を `from dataclasses import dataclass` に、`from typing import NamedTuple` の行を削除する。
2. `fill_end`、`Recalc`、`recalc_ends` を削除する。
3. `visible_range`、`build_columns`、`bar_span`、`is_overdue` を次に置き換える。

```python
def visible_range(
    project: Project, holidays: dict[date, str] | None = None
) -> tuple[date, date]:
    """基準日とバーを持つタスクから、表示範囲[開始日, 終了日)を返す。"""
    holidays = holidays or {}
    start = end = project.base_date
    tasks = [*project.tasks, *(t for section in project.sections for t in section.tasks)]
    for task in tasks:
        task_end = effective_end(task, project, holidays)
        if task.planned_start is None or task_end is None:
            continue
        first, last = sorted((task.planned_start.date(), task_end.date()))
        start = min(start, first)
        end = max(end, last + timedelta(days=1))
    return start, end


def build_columns(
    project: Project, scale: Scale, holidays: dict[date, str] | None = None
) -> list[Column]:
    start, end = visible_range(project, holidays)
    if scale is Scale.WEEK:
        return _week_columns(start, end)
    if scale is Scale.MONTH:
        return _month_columns(start, end)
    return _day_columns(start, end)
```

```python
def bar_span(
    start: datetime | None, end: datetime | None, columns: list[Column]
) -> tuple[float, float] | None:
    """バーの(左端, 幅)を列の単位で返す。開始・終了が無ければNone。"""
    if start is None or end is None:
        return None
    left = _position(start, columns)
    right = _position(end, columns)
    return left, max(right - left, 0.0)
```

```python
def is_overdue(
    task: Task, project: Project, holidays: dict[date, str], now: datetime
) -> bool:
    """締切か完了予定を過ぎていて、状態が「終了」でない。"""
    if task.status is Status.DONE:
        return False
    if task.deadline is not None and now > task.deadline:
        return True
    end = effective_end(task, project, holidays)
    return end is not None and now > end
```

- [ ] **Step 9: `build_task` を直す**

`src/projectapp/forms.py` の `build_task` を、次に置き換える。

```python
def build_task(
    existing: Task | None,
    *,
    name: str,
    planned_start: str,
    planned_end: str,
    planned_end_manual: bool = False,
    deadline: str | None = None,
    effort_hours: float | None,
    priority: Priority,
    status: Status,
    color: str,
    assignee: str,
) -> Task:
    """入力値からTaskを作る。編集時はフォームにない項目を引き継ぐ。

    deadlineがNoneのときは、既存の締切を保つ(空文字は締切なし)。
    """
    clean = name.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    try:
        start_at, end_at = parse_datetime(planned_start), parse_datetime(planned_end)
        deadline_at = parse_datetime(deadline) if deadline is not None else None
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    for moment in (start_at, end_at, deadline_at):
        if moment and not MIN_YEAR <= moment.year <= MAX_YEAR:
            raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    hours = effort_hours or 0.0
    if not isfinite(hours) or hours < 0:
        raise ValueError("工数は0以上の数値で入力してください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    manual = planned_end_manual and hours > 0
    uses_planned_end = hours <= 0 or manual  # 工数ありで手指定なしの値は、使われないので検証しない
    if uses_planned_end and start_at and end_at and end_at < start_at:
        raise ValueError("完了予定は開始予定以降の日時にしてください")
    base = existing or Task(clean)
    return replace(
        base,
        name=clean,
        planned_start=start_at,
        planned_end=end_at,
        planned_end_manual=manual,
        deadline=base.deadline if deadline is None else deadline_at,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignee=assignee.strip() or None,
    )
```
`format_datetime` は `needs_*` などで使われているので残す。

- [ ] **Step 10: ダイアログを最小限に合わせる**

`src/projectapp/task_dialog.py`(完全な画面は Task 5):

1. `DateTimeFields.__init__` の引数から `end_auto` を削除し、`lock_end` の行と、`self._column(... lock_end)` の引数、`_column` の `locked` 引数と `if locked:` ブロックを削除する。
2. `if key == "end": day.props('hint="空にして保存すると、開始と工数から算出します"')` を削除する。
3. 呼び出し側を次にする。

```python
        fields = DateTimeFields(initial.planned_start, initial.planned_end, work_start)
```
4. `build_task(` の呼び出しを次にする。

```python
                result = build_task(
                    task,
                    name=name.value or "",
                    planned_start=fields.start_text(),
                    planned_end=fields.end_text(),
                    planned_end_manual=bool(fields.end_text()),  # 暫定: Task 5 で「手で指定」のチェックに置き換える
                    effort_hours=effort.value,
                    priority=priority.value,
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                )
```
5. 画面の見出しはまだ「開始」「終了」のままでよい(Task 5・7 で改める)。
6. ダイアログのテスト(`test/test_task_dialog.py`)のうち、`end_auto`、ロック、「空にして保存すると」のヒントを扱うもの(`grep -n "end_auto\|locked\|hint\|explains" test/test_task_dialog.py`)は削除し、`Task(` の `end=` は `planned_end=` に、`saved[0].start`/`.end` は `.planned_start`/`.planned_end` に直す。

- [ ] **Step 11: ガントを直す**

`src/projectapp/gantt.py`:

1. import の `is_overdue` の並びに `effective_end` を足す。
2. `render` の `columns = build_columns(self.project, self.scale)` を次にする。

```python
        columns = build_columns(self.project, self.scale, self.holidays)
```
3. `task_row` の予定超過と棒の部分を次にする。

```python
        if is_overdue(task, self.project, self.holidays, self.now()):
            style += f"; background: {OVERDUE_COLOR}"
```
```python
            end = effective_end(task, self.project, self.holidays)
            span = bar_span(task.planned_start, end, columns)
```
(他の行は変えない。)

- [ ] **Step 12: 画面(`views.py`)を直す**

1. `from projectapp.timeline import fill_end, recalc_ends` の行を削除する。
2. `apply_settings` を次にする。

```python
    def apply_settings(self, hours: float, start: time) -> None:
        """稼働設定を更新して再描画する。完了予定は表示のたびに計算されるので、再計算の処理は要らない。保存はしない。"""
        if hours == self.project.daily_hours and start == self.project.work_start:
            return
        self.project.daily_hours, self.project.work_start = hours, start
        self.gantt.set_project(self.project)
```
3. `warn_unresolved` を削除する。
4. `save_task` の `task = fill_end(task, self.project, self.holidays)` の行を削除する。
5. `refresh_holidays` を次にする。

```python
    async def refresh_holidays(self, quiet: bool = False) -> None:
        """祝日を取得してチャートに反映する。失敗しても画面は変えず通知だけ出す。"""
        try:
            self.holidays = await download_holidays(self.base_dir, self.transport)
        except (httpx.HTTPError, ValueError, OSError):  # OSErrorはキャッシュの書き込み失敗
            ui.notify("祝日データを取得できませんでした", type="warning")
            return
        self.gantt.set_holidays(self.holidays)
        if not quiet:
            ui.notify("祝日データを更新しました")
```

- [ ] **Step 13: 通す**

Run: `uv run pytest -q 2>&1 | tail -30; uvx ty check src`
Expected: すべて PASS。失敗が残ったら、次のルールで直す。
- `AttributeError: … has no attribute 'end'` / `'end_auto'` → `planned_end` に直すか、そのテストが再計算を扱うなら削除する。
- 開始予定だけを持つタスクが、1日の棒として出るようになった(完了予定が翌日になる)。「棒が出ない」ことを期待していたテストは、`Task` から `planned_start` を外す。
- 赤い行のテストで、開始予定だけのタスクが赤くなる場合は、開始予定を未来にするか、期待を直す。

- [ ] **Step 14: 古い参照が残っていないことを確認する**

```bash
grep -rn "end_auto\|fill_end\|recalc_ends\|Recalc\b\|\.end\b" src/projectapp/ | grep -v "column\|\.end\b.*date\|c\.end\|first\.end"
```
Expected: タスクの `end` / `end_auto` に関するヒットなし(`Column.end`・`b.start` などの列の参照は残ってよい)。

- [ ] **Step 15: コミットして本体にマージする**

```bash
git add -A
git commit -m "終了と end_auto を、完了予定(その都度計算)と締切に切り替える

旧 end は締切として読み込む。再計算の処理と通知を削除する。

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/planned-dates
git merge --no-ff feature/planned-dates-effective-end -m "完了予定への切り替えをマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 5: 編集ダイアログの並びと完了予定の切り替え

**Branch:** `feature/planned-dates-dialog`

**Files:**
- Modify: `src/projectapp/task_dialog.py`、`src/projectapp/views.py`、`src/projectapp/forms.py`(`build_task` の `deadline` を必須の文字列にする)
- Test: `test/test_task_dialog.py`、`test/test_forms.py`

**Interfaces:**
- Consumes: Task 4 の `build_task`、`computed_end`、`parse_datetime`、`compose_datetime`、`default_times`、`needs_start_time`、`needs_end_time`。
- Produces:
  - `open_task_dialog(task, on_save, work_start=DEFAULT_WORK_START, on_delete=None, daily_hours=DEFAULT_DAILY_HOURS, holidays=None)`
  - `DateTimeFields(task: Task, work_start: time, daily_hours: float, holidays: dict[date, str])`:属性 `start_day` / `start_time` / `use_start_time`、`end_day` / `end_time` / `use_end_time`、`deadline_day` / `deadline_time` / `use_deadline_time`、`manual`(チェック)、`computed`(読み取り専用の欄)、`second_row`(締切と工数の行)。メソッド `set_effort(value: float | None)`、`start_text()`、`end_text()`、`deadline_text()`、`state()`。
  - マーカー: `task-end-manual`(手で指定のチェック)、`task-end-computed`(算出値の欄)、`task-deadline-date`、`task-deadline-use-time`、`task-deadline-time`、`open-deadline-date-picker`、`open-deadline-time-picker`。
  - `build_task(..., deadline: str, ...)`:`str` を必須にする(`None` の「保つ」を廃止する)。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/planned-dates
git checkout -b feature/planned-dates-dialog
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_task_dialog.py` の `mount_dialog` を、`daily_hours` と `holidays` を渡せる形にする(既存の呼び出しは変えなくてよい)。

```python
def mount_dialog(
    task: Task | None,
    saved: list[Task],
    work_start: time = time(9, 0),
    deleted: list[str] | None = None,
    daily_hours: float = 6.5,
    holidays: dict[date, str] | None = None,
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_task_dialog(
                task,
                saved.append,
                work_start=work_start,
                on_delete=None if deleted is None else lambda: deleted.append("deleted"),
                daily_hours=daily_hours,
                holidays=holidays,
            ),
        )
```
(`from datetime import date, datetime, time` に直す。)

次を追加する。

```python
async def test_without_effort_the_planned_end_is_editable_and_has_no_manual_check(
    user: User,
) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_see(marker="task-end-date")
    await user.should_not_see(marker="task-end-manual")
    await user.should_not_see(marker="task-end-computed")
    end = user.find(marker="task-end-date").elements.pop()
    assert "翌日" in end.props["hint"]


async def test_with_effort_the_planned_end_is_computed_and_read_only(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    await user.should_see(marker="task-end-manual")
    await user.should_see(marker="task-end-computed")
    await user.should_not_see(marker="task-end-date")
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-13 11:00"
    assert computed.props.get("readonly") is not None


async def test_the_computed_end_follows_the_start_and_effort(user: User) -> None:
    mount_dialog(None, [], daily_hours=8.0)
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    computed = user.find(marker="task-end-computed").elements.pop()
    assert computed.value == "2026-10-12 16:00"  # 金8h + 月7h
    user.find(marker="task-start-date").clear().type("2026-10-12")
    assert computed.value == "2026-10-13 15:00"  # 月8h + 火7h


async def test_the_computed_end_follows_the_holidays(user: User) -> None:
    mount_dialog(None, [], holidays={date(2026, 10, 12): "祝日"})
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-14 11:00"


async def test_manual_check_makes_the_planned_end_editable_and_keeps_the_typed_value(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-end-date").type("2026-10-20")
    user.find(marker="task-effort").clear().type("15")
    await user.should_not_see(marker="task-end-date")  # 工数ありで手指定なしなので隠れる
    user.find(marker="task-end-manual").click()
    await user.should_see(marker="task-end-date")
    assert user.find(marker="task-end-date").elements.pop().value == "2026-10-20"  # 値は保たれている
    await user.should_not_see(marker="task-end-computed")
    user.find(marker="task-save").click()
    assert saved[0].planned_end_manual is True
    assert saved[0].planned_end == datetime(2026, 10, 20, 18, 0)


async def test_unchecking_manual_returns_to_the_computed_value(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    user.find(marker="task-end-manual").click()
    user.find(marker="task-end-manual").click()
    await user.should_see(marker="task-end-computed")
    await user.should_not_see(marker="task-end-date")


async def test_clearing_the_effort_while_manual_is_on_makes_the_end_editable_and_not_manual(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-09")
    user.find(marker="task-effort").clear().type("15")
    user.find(marker="task-end-manual").click()
    user.find(marker="task-effort").clear()
    await user.should_see(marker="task-end-date")
    await user.should_not_see(marker="task-end-manual")
    user.find(marker="task-save").click()
    assert saved[0].planned_end_manual is False


async def test_the_deadline_is_entered_with_a_date_and_an_optional_time(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-deadline-date").type("2026-10-30")
    await user.should_not_see(marker="task-deadline-time")
    user.find(marker="task-save").click()
    assert saved[0].deadline == datetime(2026, 10, 30, 18, 0)  # 時刻なしは終業時刻
    assert saved[0].planned_start is None


async def test_the_deadline_time_can_be_specified(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-deadline-date").type("2026-10-30")
    user.find(marker="task-deadline-use-time").click()
    user.find(marker="task-deadline-time").clear().type("12:00")
    user.find(marker="task-save").click()
    assert saved[0].deadline == datetime(2026, 10, 30, 12, 0)


async def test_an_existing_task_opens_with_its_values(user: User) -> None:
    task = Task(
        "旧",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 15, 30),
        planned_end_manual=True,
        deadline=datetime(2026, 10, 12, 18),
        effort_hours=8.0,
    )
    mount_dialog(task, [])
    await open_dialog(user)
    assert user.find(marker="task-end-manual").elements.pop().value is True
    assert user.find(marker="task-end-date").elements.pop().value == "2026-10-09"
    assert user.find(marker="task-end-time").elements.pop().value == "15:30"
    assert user.find(marker="task-deadline-date").elements.pop().value == "2026-10-12"


async def test_closing_asks_for_confirmation_after_the_manual_check_changes(user: User) -> None:
    task = Task("旧", planned_start=datetime(2026, 10, 5, 9), effort_hours=8.0)
    mount_dialog(task, [])
    await open_dialog(user)
    user.find(marker="task-end-manual").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")
```

`test/test_forms.py` に追加する(`deadline` を必須の文字列にするため、`make` の `deadline` の既定 `""` はそのまま使える)。

```python
def test_build_task_requires_the_deadline_text() -> None:
    with pytest.raises(TypeError):
        build_task(  # type: ignore[call-arg]
            None, name="a", planned_start="", planned_end="", effort_hours=0.0,
            priority=Priority.HIGH, status=Status.RUNNING, color="#112233", assignee="",
        )
```
(`test_blank_deadline_clears_it_and_none_keeps_it` の `None` の部分は削除する。)

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_task_dialog.py test/test_forms.py -q 2>&1 | tail -20`
Expected: FAIL(マーカーがない、署名が違う)

- [ ] **Step 4: `build_task` の `deadline` を必須にする**

`src/projectapp/forms.py` の `build_task` で、`deadline: str | None = None,` を `deadline: str,` に変え(キーワード専用なので順序は自由)、本体を直す。

```python
        deadline_at = parse_datetime(deadline)
```
```python
        deadline=deadline_at,
```
docstring の「deadlineがNoneのときは…」の行を削除する。

- [ ] **Step 5: `DateTimeFields` を作り直す**

`src/projectapp/task_dialog.py` の `DateTimeFields` クラスを、次に置き換える。import に `date`、`computed_end`(`from projectapp.timeline import computed_end`)、`parse_datetime`(forms から)を足す。

```python
class DateTimeFields:
    """開始予定・完了予定・締切を、日付の入力と、側ごとのチェックで出す時刻の入力で受け取る。

    完了予定は、工数があって「手で指定」がオフのときは、算出値を読み取り専用で出す
    (入力欄は隠すだけで、入力済みの値は保つ)。
    """

    def __init__(
        self,
        task: Task,
        work_start: time,
        daily_hours: float,
        holidays: dict[date, str],
    ) -> None:
        default_start, default_end = default_times(work_start)
        self._defaults = {"start": default_start, "end": default_end, "deadline": default_end}
        self._work_start, self._daily_hours, self._holidays = work_start, daily_hours, holidays
        self.effort = task.effort_hours
        with ui.row().classes("w-full no-wrap gap-4"):
            self.start_day, self.start_time, self.use_start_time, _ = self._column(
                "開始予定", "start", task.planned_start,
                needs_start_time(task.planned_start, work_start),
            )
            self.end_day, self.end_time, self.use_end_time, self.end_editable = self._column(
                "完了予定", "end", task.planned_end,
                needs_end_time(task.planned_end, work_start),
                header=lambda: self._end_header(task.planned_end_manual),
            )
        self.second_row = ui.row().classes("w-full no-wrap gap-4")
        with self.second_row:
            self.deadline_day, self.deadline_time, self.use_deadline_time, _ = self._column(
                "締切", "deadline", task.deadline,
                needs_end_time(task.deadline, work_start),
            )
        for key in ("start", "end", "deadline"):
            self._show_time(key, self._use(key).value)
        for widget in (self.start_day, self.start_time):
            widget.on_value_change(self._refresh_end)
        self.use_start_time.on_value_change(self._refresh_end)
        self._refresh_end()

    def _end_header(self, manual: bool) -> None:
        self.manual = ui.checkbox(
            "手で指定", value=manual, on_change=self._refresh_end
        ).mark("task-end-manual")
        self.computed = (
            ui.input("算出値", value="")
            .props("readonly")
            .classes("w-full")
            .mark("task-end-computed")
        )

    def _column(
        self,
        label: str,
        key: str,
        moment: datetime | None,
        use_time: bool,
        header: Callable[[], None] | None = None,
    ) -> tuple[ui.input, ui.input, ui.checkbox, ui.column]:
        default = self._defaults[key]
        with ui.column().classes("flex-1 gap-0"):
            ui.label(label).classes("text-caption text-grey")
            if header is not None:
                header()
            with ui.column().classes("w-full gap-0") as editable:
                day = ui.input("日付", value=moment.strftime("%Y-%m-%d") if moment else "")
                day.classes("w-full").mark(f"task-{key}-date")
                add_picker(day, ui.date, "event", f"{key}-date", "%Y-%m-%d")
                checkbox = ui.checkbox(
                    "時刻を指定",
                    value=use_time,
                    on_change=lambda e, k=key: self._show_time(k, e.value),
                ).mark(f"task-{key}-use-time")
                clock = ui.input(
                    "時刻", value=(moment.time() if moment else default).strftime("%H:%M")
                )
                clock.classes("w-full").mark(f"task-{key}-time")
                add_picker(clock, ui.time, "access_time", f"{key}-time", "%H:%M")
        return day, clock, checkbox, editable

    def _use(self, key: str) -> ui.checkbox:
        return getattr(self, f"use_{key}_time")

    def _time(self, key: str) -> ui.input:
        return getattr(self, f"{key}_time")

    def _day(self, key: str) -> ui.input:
        return getattr(self, f"{key}_day")

    def _show_time(self, key: str, show: bool) -> None:
        """側ごとに時刻入力を出し入れする。隠しても入力の値は保ち、入れ直すと元の値が出る。"""
        self._time(key).set_visibility(show)

    def _clock(self, key: str) -> str:
        """保存と変更判定に使う時刻。チェックのない側は、入力の値ではなく補う時刻を使う。"""
        if self._use(key).value:
            return self._time(key).value or ""
        return self._defaults[key].strftime("%H:%M")

    def set_effort(self, value: float | None) -> None:
        self.effort = value or 0.0
        self._refresh_end()

    def _has_effort(self) -> bool:
        return (self.effort or 0.0) > 0

    def _refresh_end(self, _event: object = None) -> None:
        """完了予定の欄を、工数と「手で指定」に合わせて切り替え、算出値を更新する。"""
        has_effort = self._has_effort()
        computed_mode = has_effort and not self.manual.value
        self.manual.set_visibility(has_effort)
        self.computed.set_visibility(computed_mode)
        self.end_editable.set_visibility(not computed_mode)
        hint = (
            "空なら工数から算出します" if has_effort else "空なら開始予定の翌日になります"
        )
        self.end_day.props(f'hint="{hint}"')
        self.computed.set_value(self._computed_text())

    def _computed_text(self) -> str:
        try:
            start = parse_datetime(self.start_text())
        except ValueError:
            return ""
        end = computed_end(
            start, self.effort or 0.0, self._daily_hours, self._work_start, self._holidays
        )
        return end.strftime("%Y-%m-%d %H:%M") if end else ""

    def start_text(self) -> str:
        return compose_datetime(self.start_day.value or "", self._clock("start"))

    def end_text(self) -> str:
        return compose_datetime(self.end_day.value or "", self._clock("end"))

    def deadline_text(self) -> str:
        return compose_datetime(self.deadline_day.value or "", self._clock("deadline"))

    def state(self) -> tuple[object, ...]:
        """入力の生の値。開いた時点との比較(変更の判定)に使う。隠れた時刻は含めない。"""
        return (
            self.start_day.value or "",
            self._clock("start"),
            self.end_day.value or "",
            self._clock("end"),
            bool(self.manual.value),
            self.deadline_day.value or "",
            self._clock("deadline"),
        )
```

注意:
- `self.manual` と `self.computed` は `header` の中で作られる。`__init__` の `_column` 呼び出しの後で参照するので順序は安全。
- `start_text()` は不正な時刻で `ValueError` を投げる。`_computed_text` が `except ValueError` で受ける。保存時の `ValueError` は `save()` の既存の捕捉に任せる。

- [ ] **Step 6: `open_task_dialog` を直す**

同じファイルの `open_task_dialog` を直す。

署名:

```python
def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
    on_delete: Callable[[], object] | None = None,
    daily_hours: float = DEFAULT_DAILY_HOURS,
    holidays: dict[date, str] | None = None,
) -> ui.dialog:
```
(import に `DEFAULT_DAILY_HOURS` を足す。)

本体の並びを次にする(`fields` の生成から `effort` まで)。

```python
        name = ui.input("名前", value=initial.name).mark("task-name")
        fields = DateTimeFields(initial, work_start, daily_hours, holidays or {})
        with fields.second_row:
            effort = (
                ui.number("工数(時間)", value=initial.effort_hours, min=0)
                .classes("flex-1")
                .mark("task-effort")
            )
        effort.on_value_change(lambda e: fields.set_effort(e.value))
        priority = PriorityChips(initial.priority)
```
`build_task` の呼び出しを次にする。

```python
                result = build_task(
                    task,
                    name=name.value or "",
                    planned_start=fields.start_text(),
                    planned_end=fields.end_text(),
                    planned_end_manual=bool(fields.manual.value),
                    deadline=fields.deadline_text(),
                    effort_hours=effort.value,
                    priority=priority.value,
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                )
```
`fields.state()` は `current()` 内で `*fields.state()` として展開済みなので、そのまま使える。

- [ ] **Step 7: `views.py` の呼び出しを直す**

`add_task`・`add_top_task`・`edit_task` の `open_task_dialog(...)` の呼び出し3か所に、引数を足す。

```python
            daily_hours=self.project.daily_hours,
            holidays=self.holidays,
```
(`work_start=self.project.work_start,` の次の行。)

- [ ] **Step 8: 通す**

Run: `uv run pytest -q 2>&1 | tail -30; uvx ty check src`
Expected: PASS。`should_not_see(marker=…)` が、隠した親の中の子で期待どおり働かないテストがあれば、その要素の親(`end_editable` など)の `visible` を直接アサートする形に直す。`ui.number` の `clear().type("15")` で値が変わらない場合は、`element.set_value(15)` を `with user.client:` の中で呼ぶ。

- [ ] **Step 9: コミットして本体にマージする**

```bash
git add -A
git commit -m "編集ダイアログを開始予定・完了予定・締切の並びにし、完了予定を工数で切り替える

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/planned-dates
git merge --no-ff feature/planned-dates-dialog -m "編集ダイアログの見直しをマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 6: ガントに締切の目印(◆)を出す

**Branch:** `feature/planned-dates-gantt-marker`

**Files:**
- Modify: `src/projectapp/timeline.py`、`src/projectapp/gantt.py`
- Test: `test/test_timeline.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: `Column`、`_position`(timeline 内)、`effective_end`、`Task.deadline`。
- Produces: `deadline_position(deadline: datetime, columns: list[Column]) -> float | None`(表示範囲の外なら `None`)。ガント: マーカー `deadline-{key}-{ti}`(`key` は `"top"` かセクション番号)。定数 `DEADLINE_MARKER_HALF_PX = 6`、`DEADLINE_COLOR = "#f57c00"`。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/planned-dates
git checkout -b feature/planned-dates-gantt-marker
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_timeline.py`(import に `deadline_position` を足す):

```python
def test_deadline_position_inside_the_range() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert deadline_position(datetime(2026, 10, 7, 12), columns) == 2.5


def test_deadline_position_outside_the_range_is_none() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert deadline_position(datetime(2026, 10, 4, 23, 59), columns) is None
    assert deadline_position(datetime.combine(columns[-1].end, time.min), columns) is None


def test_deadline_position_at_the_boundaries() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert deadline_position(datetime(2026, 10, 5, 0, 0), columns) == 0.0
    last = datetime.combine(columns[-1].end, time.min) - timedelta(minutes=1)
    assert deadline_position(last, columns) is not None
```
(`timedelta`、`time` が import に無ければ足す。)

`test/test_gantt.py`:

```python
async def test_the_deadline_marker_is_placed_at_the_deadline(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].deadline = datetime(2026, 10, 8, 12)  # BASE は 10/5
    mount(project)
    await user.open("/")
    marker = user.find(marker="deadline-0-0").elements.pop()
    assert marker._style["left"] == f"{200 + 3.5 * 40 - DEADLINE_MARKER_HALF_PX:.1f}px"


async def test_a_task_without_a_start_still_shows_its_deadline_marker(user: User) -> None:
    project = Project(
        "demo", base_date=BASE, tasks=[Task("締切のみ", deadline=datetime(2026, 10, 8, 12))]
    )
    mount(project)
    await user.open("/")
    await user.should_see(marker="deadline-top-0")
    await user.should_not_see(marker="bar-top-0")


async def test_a_deadline_outside_the_range_has_no_marker(user: User) -> None:
    project = Project(
        "demo", base_date=BASE, tasks=[Task("遠い", deadline=datetime(2030, 1, 1))]
    )
    mount(project)
    await user.open("/")
    await user.should_not_see(marker="deadline-top-0")


async def test_clicking_the_deadline_marker_edits_the_task(user: User) -> None:
    project = sample_project()
    project.sections[0].tasks[0].deadline = datetime(2026, 10, 8, 12)
    recorder = mount(project)
    await user.open("/")
    user.find(marker="deadline-0-0").click()
    assert recorder.edited == [(0, 0)]
```
(`Recorder` は既存のヘルパーで、編集の呼び出しを記録する。`recorder.edited` の名前は既存の定義に合わせる: `grep -n "class Recorder" -A12 test/test_gantt.py` で確認し、クリックのテスト `test_clicking_a_bar_*`(`bar-0-0` をクリックする既存のもの)と同じ形にそろえる。import に `DEADLINE_MARKER_HALF_PX` を足す。)

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_timeline.py test/test_gantt.py -q 2>&1 | tail -15`
Expected: FAIL(`deadline_position` がない)

- [ ] **Step 4: 位置の関数を足す**

`src/projectapp/timeline.py` の `bar_span` の後に追加:

```python
def deadline_position(deadline: datetime, columns: list[Column]) -> float | None:
    """締切の位置(列の単位)。表示範囲の外ならNone。"""
    begin = datetime.combine(columns[0].start, time.min)
    finish = datetime.combine(columns[-1].end, time.min)
    if not begin <= deadline < finish:
        return None
    return _position(deadline, columns)
```

- [ ] **Step 5: ガントに目印を足す**

`src/projectapp/gantt.py`:

1. 定数を足す(`MIN_BAR_PX` の次)。

```python
DEADLINE_MARKER_HALF_PX = 6  # 「◆」の幅の半分。締切の位置が目印の中心に来るようにずらす
DEADLINE_COLOR = "#f57c00"  # 赤は予定超過の背景と競合するので使わない
```
2. import に `deadline_position` を足す。
3. `task_row` の棒の部分を、早期 `return` をやめる形にする。次のように、棒を描く部分を `if span is not None:` で囲み、その後に目印を呼ぶ。

```python
            end = effective_end(task, self.project, self.holidays)
            span = bar_span(task.planned_start, end, columns)
            if span is not None:
                left, length = span
                ui.element("div").style(
                    f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                    f" width: {max(length * width, MIN_BAR_PX):.1f}px; top: 6px;"
                    f" height: {ROW_HEIGHT_PX - 12}px;"
                    f" background: {task.color if is_hex_color(task.color) else DEFAULT_COLOR};"
                    " border-radius: 4px; cursor: pointer"
                ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                    f"bar-{key}-{ti}"
                )
            self.deadline_marker(si, ti, task, columns, width)
```
(既存の `if span is None: return` と、`left, length = span` 以降の `ui.element("div")…` をこの形に置き換える。棒のスタイル文字列は既存のものを変えない。)

4. メソッドを足す。

```python
    def deadline_marker(
        self, si: int | None, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """締切がある行に、締切の位置へ「◆」を出す。表示範囲の外なら出さない。"""
        if task.deadline is None:
            return
        position = deadline_position(task.deadline, columns)
        if position is None:
            return
        key = "top" if si is None else si
        left = NAME_WIDTH_PX + position * width - DEADLINE_MARKER_HALF_PX
        ui.label("◆").style(
            f"position: absolute; left: {left:.1f}px; top: 4px; line-height: 1;"
            f" color: {DEADLINE_COLOR}; cursor: pointer"
        ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).tooltip(
            f"締切 {task.deadline:%Y-%m-%d %H:%M}"
        ).mark(f"deadline-{key}-{ti}")
```

- [ ] **Step 6: 通す**

Run: `uv run pytest -q && uvx ty check src`
Expected: PASS

- [ ] **Step 7: コミットして本体にマージする**

```bash
git add -A
git commit -m "ガントに締切の目印(◆)を出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/planned-dates
git merge --no-ff feature/planned-dates-gantt-marker -m "締切の目印をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 7: 用語と文書を更新する

**Branch:** `feature/planned-dates-docs`

**Files:**
- Modify: `CLAUDE.md`(`projectapp/CLAUDE.md`)、`README.md`、`docs/development.md`、`.claude/MEMORY.md`、`src/projectapp/*.py`(画面の文言)
- Test: `test/test_task_dialog.py`(文言のテスト)

**Interfaces:**
- Consumes: Task 1〜6 の完成した動作。
- Produces: 文書と画面の用語が「開始予定」「完了予定」「締切」にそろう。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/planned-dates
git checkout -b feature/planned-dates-docs
```

- [ ] **Step 2: 画面の文言に古い用語が残っていないか調べる**

```bash
grep -rn "終了\|開始" src/projectapp/*.py | grep -v "^src/projectapp/.*#\|Status\|STARTED\|DONE\|開始日\|work_start\|始業"
```
Expected: 状態の列挙(「開始」「終了」は `Status` の値)以外で、タスクの日付を指す文言が残っていれば、「開始予定」「完了予定」「締切」に直す。エラー文(`build_task`)は Task 2〜4 で済んでいる。残りの候補: 追加行や見出しの文言。

- [ ] **Step 3: 文言のテストを足す**

`test/test_task_dialog.py`:

```python
async def test_the_dialog_uses_the_planned_wording(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_see("開始予定")
    await user.should_see("完了予定")
    await user.should_see("締切")
```

Run: `uv run pytest test/test_task_dialog.py -q -k planned_wording`
Expected: PASS(Task 5 で済んでいるはず。落ちたら文言を直す)

- [ ] **Step 4: `CLAUDE.md` を更新する**

`/Users/jun/Documents/opt/work/projectapp/CLAUDE.md` で、次の行を置き換える。

置き換え前:

```
- `ガントチャート`には、`開始日時`、`終了日時`、`工数`（時間単位）で設定ができ、`開始日時`+`工数`で完了予定時刻の自動算出も可能とする
```
置き換え後:

```
- `ガントチャート`のタスクには、`開始予定`、`完了予定`、`締切`、`工数`（時間単位）を設定できる
- `完了予定`は、工数があれば`開始予定`+`工数`から自動算出する（稼働可能時間と祝日を反映し、設定の変更はすぐ反映される）。`手で指定`のチェックで手入力に切り替えられる。工数がないときは直接入力し、空欄なら`開始予定`の翌日になる
- `締切`（納期）は、日付と任意の時刻で設定でき、ガントチャートに目印（◆）で表示する
- `開始`・`終了`は、実際に作業した日時（実績）のために空けた名前で、実績の入力は後続機能とする
```

置き換え前:

```
- `予定`と`実績`管理ができ、終了予定は、見積もりの日程が予定として登録ができる
- 予定を超えたタスクは、`赤`を基準とした`背景色`で表示される
```
置き換え後:

```
- `予定`と`実績`管理ができ、完了予定は、見積もりの日程が予定として登録ができる（実績は後続機能）
- 締切または完了予定を過ぎた、終了していないタスクは、`赤`を基準とした`背景色`で表示される
```

また、「設定ダイアログで、…変更すると、自動算出された終了日時は再計算される(手入力の終了日時は変わらない)」の行を、次にする。

```
- 設定ダイアログで、プロジェクトごとに`稼働可能時間`と`始業時刻`を変更できる。変更すると、自動算出された完了予定がすぐ変わる（手で指定した完了予定と締切は変わらない）
```

- [ ] **Step 5: `docs/development.md` と `README.md` を更新する**

`docs/development.md`:

- モジュール表の `timeline.py` の説明の「自動算出された終了の再計算」を「完了予定の算出(`effective_end`)、締切の位置」に直す。`models.py` の説明の「`Task.end_auto` は自動算出された終了の印」を「`Task.planned_end` / `planned_end_manual` / `deadline`」に直す。
- 「ファイル形式の注意」の節を次に置き換える。

```markdown
## ファイル形式の注意

- タスクの日付は、`planned_start`(開始予定)、`planned_end`(完了予定の手入力値)、`planned_end_manual`(手で指定)、`deadline`(締切)。完了予定は保存せず、`effective_end` で表示のたびに計算する。
- `planned_end_manual` のキーがないファイルは旧形式として読む。旧 `start` は開始予定、旧 `end` は締切になる(`end_auto` が `true` のものは自動算出だったので捨てる)。旧形式のファイルは、保存すると新形式になる。
- 読み込み時に `daily_hours`(有限の数値で、0より大きく24以下)と `work_start`(`HH:MM[:SS]` の文字列)を検証し、不正なファイルは「開けませんでした」と通知する。`planned_end_manual` は `true` のときだけ真として扱う。
```

`README.md`:「主な機能」が空欄のままなら、このタスクでは触らない(別件)。

- [ ] **Step 6: 作業記録(`.claude/MEMORY.md`)を更新する**

- 「現在の状況」に、開始予定・完了予定・締切の変更を実装したことと、未マージであることを書く。
- 「実装済みの機能」の「稼働時間の設定」「日程計算」「タスク編集ダイアログ」の `end_auto`、`recalc_ends`、「終了」の記述を、新しい仕様(完了予定をその都度計算、`planned_end_manual`、締切、◆)に書き換える。
- 「保留中の軽微な指摘(稼働時間の設定画面)」にある、`end_auto` と再計算に関する項目は、この変更で解消したので削除する。
- 「次にやること」に、実績の入力(開始・終了)を、後続機能の先頭として残す。

- [ ] **Step 7: 通す**

Run: `uv run pytest -q && uvx ty check src`
Expected: PASS

- [ ] **Step 8: コミットして本体にマージする**

```bash
git add -A
git commit -m "用語を開始予定・完了予定・締切にそろえ、文書を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/planned-dates
git merge --no-ff feature/planned-dates-docs -m "用語と文書の更新をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 8: 全体の確認と引き渡し

**Files:** なし(確認のみ)

- [ ] **Step 1: 全体を通す**

```bash
git checkout feature/planned-dates
uv run pytest --cov=projectapp -q
uvx ty check src
git status --short
```
Expected: すべて PASS、未コミットの変更なし。

- [ ] **Step 2: 古い参照が残っていないことを確認する**

```bash
grep -rn "end_auto\|fill_end\|recalc_ends" src test docs/development.md CLAUDE.md
```
Expected: ヒットなし(旧形式の読み込みのコードとテストの中の、`end_auto` のキー名だけは残ってよい。`src/projectapp/storage.py` の `_task` と `test/test_storage.py` のレガシー変換のテスト)。

- [ ] **Step 3: ユーザーに実機の確認を依頼する**

次を確認してもらう(`uv run projectapp`)。
1. 編集ダイアログの並び(1行目: 開始予定・完了予定、2行目: 締切・工数)と幅、小さなウィンドウで切れないこと。
2. 工数を入力すると、完了予定が算出値(読み取り専用)に切り替わり、「手で指定」で編集できること。工数を消すと編集に戻ること。
3. 空の完了予定が、開始予定の翌日になること(棒が1日分)。
4. 締切の目印(◆)の位置と、クリックで編集ダイアログが開くこと。ライト/ダークで見えること。
5. 稼働時間の設定や祝日の更新で、棒の長さが変わること。
6. 旧形式のファイル(`~/.projectapp/デモ.json` など)を開き、旧 `end` が締切になり、棒が変わること(開く前に、ファイルのバックアップを取っておく)。
7. 締切超過、完了予定超過の行が赤くなること。

- [ ] **Step 4: 承認を待ってから `develop` にマージする**

ユーザーの許可を得てから:

```bash
git checkout develop
git merge --no-ff feature/planned-dates -m "開始予定・完了予定・締切をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
uv run pytest -q && uvx ty check src
```
マージ後、`feature/planned-dates*` のブランチを削除してよいか、ユーザーに確認する。プッシュは別に許可を得る。
