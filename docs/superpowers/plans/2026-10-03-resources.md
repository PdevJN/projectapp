# 見積もりのバッファ換算とリソース割り当て比率 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 担当者をプロジェクトのメンバー(相対比率つき)として管理し、タスクの割り当て率とあわせて工数を日数に換算する。同じ担当者の割り当て合計が 100% を超える期間を、通知とガントの縞で示す。

**Architecture:** `Member.ratio`(相対比率)と `Task.allocation`(割り当て率)から換算率 = ratio × allocation を求め、`computed_end` が工数を換算率で割ってから `calc_end` に渡す。割り当て合計の超過は純粋関数 `overallocations` で求め、ガントは棒の内側に縞を重ねる。メンバーは専用ダイアログで管理し、タスクの担当者はメンバーから選ぶ。

**Tech Stack:** Python 3.13、NiceGUI 3.17、pytest(`uv run pytest -q`)、型チェック `uvx ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-03-resources-design.md`

## Global Constraints

- 言語は日本語。画面の文言、エラー文、コメント、コミットメッセージは日本語。識別子は英語。
- ブランチは `feature/resources`(設計書をコミット済み)を本体とする。関心ごとに `feature/resources-<関心ごと>` を本体から切り、テストが通ってから `git merge --no-ff` で本体に戻す。`develop` へのマージとプッシュは、ユーザーの許可を得てから行う。
- 各タスクの終わりで `uv run pytest -q` と `uvx ty check src` が通ること。
- コミットメッセージの末尾に、次の行を付ける: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- 範囲: 相対比率は 0.1 以上 3.0 以下(10%〜300%)、割り当て率は 0.01 以上 1.0 以下(1%〜100%)。保存は割合(1.0 = 100%)、画面は%。
- 工数(h)は、基準の人が全時間をかけた場合の時間。換算後の工数 = 工数 ÷ (ratio × allocation)。換算率が 0 以下・NaN・inf のときは換算しない(1.0)。
- 手で指定の完了予定は換算しない。締切・開始予定の翌日への代替は、今のまま。
- 割り当て合計の超過は、保存を妨げない(通知と縞だけ)。状態が「終了」のタスクは合計に数えない。ちょうど 100% は超過にしない(浮動小数の余裕 `1e-9`)。
- ガントの縞は、行の背景ではなく、棒の内側だけ。重ねる要素は `pointer-events: none`(クリックは棒に通す)。
- マーカー(`.mark`)の名前は、各タスクの Interfaces に書いたものを使う。

## Review Focus

仕様が含意するが、どのタスクのテストにも直接は出ない入力。各行のテストは、持ち主のタスクに入れてある。

1. 担当者名の前後に空白がある、空白だけ、メンバー名が重複 → 空白は取り除き、空白のみは担当者なし、重複は最初の1件(Task 1)。
2. 換算率が極端に小さい(10% × 1%)で工数が大きい → 例外にせず、算出できないときの代替(締切、なければ翌日)になる(Task 2)。
3. 割り当て 70% と 30%、10% + 20% + 70% のちょうど 100% → 浮動小数の誤差で超過にならない(Task 2)。
4. メンバー名の入れ替え(A↔B)、改名した名前が別のメンバーと衝突 → 担当者名が正しく入れ替わる、衝突は拒否(Task 3)。
5. 担当者を「(なし)」に戻す、工数を空にする → 割り当て率は 100% で保存、換算の表示は消える(Task 4)。
6. 縞が、細い棒(幅が最小幅)や棒の端をはみ出さない(Task 5)。

---

## Task 1: モデルと保存(`allocation`、メンバーの検証と自動追加)

**Branch:** `feature/resources-model`(`feature/resources` から切る)

**Files:**
- Modify: `src/projectapp/models.py`、`src/projectapp/storage.py`
- Test: `test/test_storage.py`

**Interfaces:**
- Produces:
  - `models.py`: 定数 `MIN_RATIO = 0.1`、`MAX_RATIO = 3.0`、`MIN_ALLOCATION = 0.01`、`MAX_ALLOCATION = 1.0`。`Task.allocation: float = 1.0`(末尾に追加)。`Project.all_tasks() -> list[Task]`(セクションなしのタスク + セクションのタスク)。
  - `storage.py` の読み込み: メンバーの `ratio` と `allocation` を検証(範囲外は `ValueError`)。担当者名の正規化(前後の空白を取り除く、空は `None`)。メンバーに無い担当者名は、メンバー(`ratio` 1.0)として末尾に追加。メンバー名の重複は最初の1件を残す。

- [ ] **Step 1: ブランチを切る**

```bash
cd /Users/jun/Documents/opt/work/projectapp
git checkout feature/resources
git checkout -b feature/resources-model
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_storage.py` の末尾に追加する(`Member`、`Section`、`Task`、`Project`、`pytest`、`json`、`_rewrite` は既存)。

```python
def test_allocation_roundtrip_and_default(tmp_path: Path) -> None:
    project = Project(
        "r",
        members=[Member("田中", 1.2)],
        tasks=[Task("a", assignee="田中", allocation=0.6), Task("b")],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [t.allocation for t in loaded.tasks] == [0.6, 1.0]
    assert loaded.members == [Member("田中", 1.2)]


def test_file_without_allocation_loads_as_one(tmp_path: Path) -> None:
    path = save_project(Project("old", tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].pop("allocation"))
    assert load_project(path).tasks[0].allocation == 1.0


@pytest.mark.parametrize("value", [0, -0.5, 0.0099, 1.01, float("nan"), float("inf"), True, "1", None, []])
def test_load_rejects_an_invalid_allocation(value: object, tmp_path: Path) -> None:
    path = save_project(Project("r", tasks=[Task("a")]), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(allocation=value))
    with pytest.raises(ValueError, match="割り当て率"):
        load_project(path)


@pytest.mark.parametrize("value", [0, 0.09, 3.01, -1, float("nan"), float("inf"), True, "1", None])
def test_load_rejects_an_invalid_member_ratio(value: object, tmp_path: Path) -> None:
    path = save_project(Project("r", members=[Member("田中")]), tmp_path)
    _rewrite(path, lambda d: d["members"][0].update(ratio=value))
    with pytest.raises(ValueError, match="相対比率"):
        load_project(path)


def test_load_accepts_the_ratio_and_allocation_boundaries(tmp_path: Path) -> None:
    project = Project(
        "r",
        members=[Member("低", 0.1), Member("高", 3.0)],
        tasks=[Task("a", assignee="低", allocation=0.01), Task("b", assignee="高", allocation=1.0)],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [m.ratio for m in loaded.members] == [0.1, 3.0]
    assert [t.allocation for t in loaded.tasks] == [0.01, 1.0]


def test_an_assignee_missing_from_the_members_is_added_as_a_member(tmp_path: Path) -> None:
    project = Project("old", members=[Member("田中", 1.2)], tasks=[Task("a", assignee="佐藤")])
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.members == [Member("田中", 1.2), Member("佐藤", 1.0)]
    assert loaded.tasks[0].assignee == "佐藤"


def test_added_members_are_not_duplicated_and_keep_the_task_order(tmp_path: Path) -> None:
    project = Project(
        "old",
        sections=[],
        tasks=[Task("a", assignee="佐藤"), Task("b", assignee="鈴木"), Task("c", assignee="佐藤")],
    )
    loaded = load_project(save_project(project, tmp_path))
    assert [m.name for m in loaded.members] == ["佐藤", "鈴木"]


def test_assignee_whitespace_is_trimmed_and_blank_becomes_none(tmp_path: Path) -> None:
    project = Project("old", tasks=[Task("a", assignee=" 佐藤 "), Task("b", assignee="  "), Task("c", assignee="")])
    loaded = load_project(save_project(project, tmp_path))
    assert [t.assignee for t in loaded.tasks] == ["佐藤", None, None]
    assert [m.name for m in loaded.members] == ["佐藤"]


def test_duplicate_member_names_keep_the_first(tmp_path: Path) -> None:
    project = Project("r", members=[Member("田中", 1.2), Member("田中", 0.5)])
    assert load_project(save_project(project, tmp_path)).members == [Member("田中", 1.2)]


def test_a_blank_member_name_is_dropped(tmp_path: Path) -> None:
    project = Project("r", members=[Member("  ", 1.0), Member("田中", 1.0)])
    assert [m.name for m in load_project(save_project(project, tmp_path)).members] == ["田中"]


def test_project_all_tasks_lists_top_level_then_sections() -> None:
    top, inner = Task("top"), Task("in")
    project = Project("p", tasks=[top], sections=[Section("s", [inner])])
    assert project.all_tasks() == [top, inner]
```

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_storage.py -q 2>&1 | tail -15`
Expected: FAIL(`Task` に `allocation` がない、`Project.all_tasks` がない など)

- [ ] **Step 4: モデルに足す**

`src/projectapp/models.py` の定数のところ(`MIN_YEAR, MAX_YEAR` の次)に追加する。

```python
MIN_RATIO, MAX_RATIO = 0.1, 3.0  # 相対比率(10%〜300%)
MIN_ALLOCATION, MAX_ALLOCATION = 0.01, 1.0  # 割り当て率(1%〜100%)
```

`Task` の末尾(`planned_end_manual` の次)に追加する。

```python
    allocation: float = 1.0  # 担当者の時間のうち、このタスクに使う割合(1.0 = 100%)
```

`Project` の末尾にメソッドを追加する。

```python
    def all_tasks(self) -> list[Task]:
        """セクションなしのタスク、続いてセクションのタスク。"""
        return [*self.tasks, *(t for section in self.sections for t in section.tasks)]
```

- [ ] **Step 5: 読み込みを直す**

`src/projectapp/storage.py` の import に `MAX_ALLOCATION`、`MAX_RATIO`、`MIN_ALLOCATION`、`MIN_RATIO` を足す。`_task` の `Task(...)` の呼び出しを次の2か所だけ変える。

```python
        assignee=_assignee(raw.get("assignee")),
```
```python
        predecessors=list(raw["predecessors"]),
        allocation=_allocation(raw.get("allocation", 1.0)),
    )
```

`_daily_hours` の前に追加する。

```python
def _number_in_range(value: Any, low: float, high: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label}が数値ではありません")
    if not isfinite(value) or not low - 1e-9 <= value <= high + 1e-9:
        raise ValueError(f"{label}が範囲外です({low:g}以上{high:g}以下)")
    return float(value)


def _allocation(value: Any) -> float:
    return _number_in_range(value, MIN_ALLOCATION, MAX_ALLOCATION, "割り当て率")


def _assignee(value: Any) -> str | None:
    """担当者名。前後の空白を取り除き、空はNone。"""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _members(raw_members: list[dict[str, Any]]) -> list[Member]:
    """メンバーを読む。相対比率は検証し、空の名前と重複は(最初の1件を残して)捨てる。"""
    members: list[Member] = []
    seen: set[str] = set()
    for raw in raw_members:
        name = str(raw["name"]).strip()
        ratio = _number_in_range(raw.get("ratio", 1.0), MIN_RATIO, MAX_RATIO, "相対比率")
        if not name or name in seen:
            continue
        seen.add(name)
        members.append(Member(name, ratio))
    return members
```

`load_project` の `members = [Member(**m) for m in raw["members"]]` の行を、次に置き換える。

```python
    members = _members(raw["members"])
```

`load_project` の `return Project(...)` を、変数に受けて、メンバーを補ってから返す形にする。

```python
    project = Project(
        name=path.stem,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=_daily_hours(raw["daily_hours"]),
        work_start=_work_start(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t) for t in raw.get("tasks", [])],
    )
    known = {m.name for m in project.members}
    for task in project.all_tasks():  # 古いファイルの自由入力の担当者を、メンバーとして補う
        if task.assignee and task.assignee not in known:
            known.add(task.assignee)
            project.members.append(Member(task.assignee, 1.0))
    return project
```
(`all_tasks()` はセクションなし → セクションの順。テスト `test_added_members_are_not_duplicated_and_keep_the_task_order` はセクションなしのタスクだけなので、順序は一致する。)

- [ ] **Step 6: 通す**

Run: `uv run pytest -q 2>&1 | tail -8 && uvx ty check src | tail -2`
Expected: PASS。`Member` の `ratio` を `1` (int)で保存したテストなどが `float(1)` に変わっても等価なので、比較は通る。

- [ ] **Step 7: コミットして本体にマージする**

```bash
git add -A
git commit -m "割り当て率(allocation)を足し、メンバーと担当者の読み込みを検証・補完する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/resources
git merge --no-ff feature/resources-model -m "モデルと保存の拡張をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 2: 換算と超過の計算

**Branch:** `feature/resources-calc`

**Files:**
- Modify: `src/projectapp/timeline.py`
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: Task 1 の `Task.allocation`、`Member.ratio`、`Project.all_tasks()`、`MIN_*`/`MAX_*`。
- Produces:
  - `combine_rate(ratio: float, allocation: float) -> float`:`ratio × allocation`。0 以下・NaN・inf のときは 1.0。
  - `conversion_rate(task: Task, project: Project) -> float`:担当者がメンバーに見つかれば `combine_rate(member.ratio, task.allocation)`、なければ 1.0。
  - `computed_end(start, effort_hours, daily_hours, work_start, holidays, deadline=None, rate=1.0)`:`rate` を足す。算出の段で、`calc_end` に `effort_hours / rate_used` を渡す(`rate_used` = 0 以下・NaN・inf なら 1.0)。
  - `effective_end(task, project, holidays)`:`computed_end` に `conversion_rate(task, project)` を渡す。
  - `effort_days(effort_hours: float, rate: float, daily_hours: float) -> float | None`:工数が 0 より大きく有限、`daily_hours` が 0 より大きいとき `effort_hours / rate_used / daily_hours`、それ以外は `None`。
  - `Overload`(frozen dataclass): `member: str`、`start: datetime`、`end: datetime`、`total: float`。
  - `overallocations(project: Project, holidays: dict[date, str]) -> list[Overload]`
  - `clip_overloads(task: Task, project: Project, holidays: dict[date, str], overloads: list[Overload]) -> list[Overload]`:そのタスクが数えられるタスクのとき、同じ担当者の超過区間を、タスクの期間 [開始予定, 完了予定) に切り詰めて返す(重ならない区間は除く)。
  - `interval_span(start: datetime, end: datetime, columns: list[Column]) -> tuple[float, float]`:区間の(左端, 幅)を列の単位で返す(`bar_span` と同じ計算。開始・終了が揃っている前提)。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/resources
git checkout -b feature/resources-calc
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_timeline.py` の import に `Overload`、`clip_overloads`、`combine_rate`、`conversion_rate`、`effort_days`、`interval_span`、`overallocations` を足す(`Member` を `projectapp.models` から import)。末尾に追加する。

```python
def member_project(*members: Member, tasks: list[Task] | None = None) -> Project:
    return Project("p", base_date=BASE, members=list(members), tasks=tasks or [])


def test_combine_rate_multiplies_and_guards_bad_values() -> None:
    assert combine_rate(1.2, 0.5) == pytest.approx(0.6)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        assert combine_rate(bad, 1.0) == 1.0
        assert combine_rate(1.0, bad) == 1.0


def test_conversion_rate_uses_the_member_ratio_and_the_task_allocation() -> None:
    project = member_project(Member("田中", 1.2))
    assert conversion_rate(Task("t", assignee="田中", allocation=0.5), project) == pytest.approx(0.6)
    assert conversion_rate(Task("t"), project) == 1.0  # 担当者なし
    assert conversion_rate(Task("t", assignee="不明", allocation=0.5), project) == 1.0  # メンバーにいない


def test_a_faster_member_finishes_earlier() -> None:
    project = member_project(Member("田中", 1.5))
    base = eff(effort_hours=15.0)  # 10/13 11:00
    task = Task("t", planned_start=FRI_START, effort_hours=15.0, assignee="田中")
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert effective_end(task, project, {}) == datetime(2026, 10, 12, 12, 30)
    assert base == datetime(2026, 10, 13, 11)


def test_a_smaller_allocation_finishes_later() -> None:
    project = member_project(Member("田中", 1.0))
    task = Task("t", planned_start=FRI_START, effort_hours=6.5, assignee="田中", allocation=0.5)
    # 6.5h / 0.5 = 13h → 金6.5h + 月6.5h
    assert effective_end(task, project, {}) == datetime(2026, 10, 12, 15, 30)


def test_a_rate_of_one_changes_nothing() -> None:
    project = member_project(Member("田中", 1.0))
    task = Task("t", planned_start=FRI_START, effort_hours=15.0, assignee="田中")
    assert effective_end(task, project, {}) == datetime(2026, 10, 13, 11)


def test_a_manual_planned_end_is_not_converted() -> None:
    project = member_project(Member("田中", 0.1))
    task = Task(
        "t", planned_start=FRI_START, effort_hours=15.0, assignee="田中",
        planned_end=MANUAL_END, planned_end_manual=True,
    )
    assert effective_end(task, project, {}) == MANUAL_END


def test_an_extreme_rate_falls_back_instead_of_raising() -> None:
    project = member_project(Member("田中", 0.1))
    task = Task(
        "t", planned_start=FRI_START, effort_hours=1000.0, assignee="田中",
        allocation=0.01, deadline=DEADLINE,
    )
    assert effective_end(task, project, {}) == DEADLINE  # 1,000,000h は算出できない
    no_deadline = Task("t", planned_start=FRI_START, effort_hours=1000.0, assignee="田中", allocation=0.01)
    assert effective_end(no_deadline, project, {}) == datetime(2026, 10, 10, 9)


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf")])
def test_computed_end_ignores_an_unusable_rate(rate: float) -> None:
    assert computed_end(FRI_START, 15.0, 6.5, time(9, 0), {}, None, rate) == datetime(2026, 10, 13, 11)


def test_effort_days() -> None:
    assert effort_days(15.0, 1.0, 6.5) == pytest.approx(15 / 6.5)
    assert effort_days(15.0, 1.2 * 0.8, 6.5) == pytest.approx(15 / 0.96 / 6.5)
    assert effort_days(15.0, 0.0, 6.5) == pytest.approx(15 / 6.5)  # 使えない換算率は1.0
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        assert effort_days(bad, 1.0, 6.5) is None
    assert effort_days(8.0, 1.0, 0.0) is None


A_START = datetime(2026, 10, 5)


def alloc_task(name: str, start_day: int, end_day: int, allocation: float, **fields: object) -> Task:
    return Task(
        name,
        planned_start=datetime(2026, 10, start_day),
        planned_end=datetime(2026, 10, end_day),
        assignee="田中",
        allocation=allocation,
        **fields,  # type: ignore[arg-type]
    )


def over(*tasks: Task) -> list[Overload]:
    return overallocations(member_project(Member("田中"), tasks=list(tasks)), {})


def test_no_overload_when_the_periods_do_not_overlap() -> None:
    assert over(alloc_task("a", 5, 7, 1.0), alloc_task("b", 7, 9, 1.0)) == []  # 端が接するだけ


def test_exactly_one_hundred_percent_is_not_an_overload() -> None:
    assert over(alloc_task("a", 5, 9, 0.7), alloc_task("b", 5, 9, 0.3)) == []
    assert over(alloc_task("a", 5, 9, 0.1), alloc_task("b", 5, 9, 0.2), alloc_task("c", 5, 9, 0.7)) == []


def test_an_overload_is_reported_with_the_overlapping_period_and_total() -> None:
    result = over(alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6))
    assert result == [Overload("田中", datetime(2026, 10, 7), datetime(2026, 10, 9), pytest.approx(1.2))]


def test_three_tasks_partially_overlapping_merge_into_one_period_with_the_peak() -> None:
    result = over(alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6), alloc_task("c", 8, 10, 0.3))
    assert len(result) == 1
    assert (result[0].start, result[0].end) == (datetime(2026, 10, 7), datetime(2026, 10, 9))
    assert result[0].total == pytest.approx(1.5)  # 10/8〜10/9 が 0.6+0.6+0.3


def test_separate_overload_periods_stay_separate() -> None:
    result = over(
        alloc_task("a", 5, 8, 0.6), alloc_task("b", 6, 8, 0.6),
        alloc_task("c", 12, 15, 0.6), alloc_task("d", 13, 15, 0.6),
    )
    assert [(o.start.day, o.end.day) for o in result] == [(6, 8), (13, 15)]


def test_done_tasks_unassigned_tasks_and_tasks_without_a_start_are_not_counted() -> None:
    done = alloc_task("a", 5, 9, 0.6, status=Status.DONE)
    other = Task("b", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9), allocation=0.6)
    no_start = Task("c", planned_end=datetime(2026, 10, 9), assignee="田中", allocation=0.6)
    assert over(done, other, no_start, alloc_task("d", 5, 9, 0.6)) == []


def test_a_task_that_ends_before_it_starts_is_not_counted() -> None:
    reversed_task = alloc_task("a", 9, 5, 0.6)
    assert over(reversed_task, alloc_task("b", 5, 9, 0.6)) == []


def test_tasks_of_other_members_do_not_mix() -> None:
    mine = alloc_task("a", 5, 9, 0.6)
    theirs = Task(
        "b", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9),
        assignee="鈴木", allocation=0.6,
    )
    project = member_project(Member("田中"), Member("鈴木"), tasks=[mine, theirs])
    assert overallocations(project, {}) == []


def test_clip_overloads_returns_the_part_inside_the_task() -> None:
    a, b = alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6)
    project = member_project(Member("田中"), tasks=[a, b])
    overloads = overallocations(project, {})
    assert [(o.start.day, o.end.day) for o in clip_overloads(a, project, {}, overloads)] == [(7, 9)]
    assert [(o.start.day, o.end.day) for o in clip_overloads(b, project, {}, overloads)] == [(7, 9)]


def test_clip_overloads_is_empty_for_tasks_that_are_not_counted() -> None:
    a, b = alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6)
    done = alloc_task("c", 5, 12, 0.6, status=Status.DONE)
    project = member_project(Member("田中"), tasks=[a, b, done])
    overloads = overallocations(project, {})
    assert clip_overloads(done, project, {}, overloads) == []
    assert clip_overloads(Task("t"), project, {}, overloads) == []


def test_interval_span_matches_bar_span() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    start, end = datetime(2026, 10, 5, 12), datetime(2026, 10, 7, 12)
    assert interval_span(start, end, columns) == bar_span(start, end, columns) == (0.5, 2.0)
```

(`eff`、`FRI_START`、`MANUAL_END`、`DEADLINE`、`BASE` は既存のテストの定義を使う。`A_START` は使わなければ削除する。)

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_timeline.py -q 2>&1 | tail -6`
Expected: FAIL / ERROR(import できない)

- [ ] **Step 4: 実装する**

`src/projectapp/timeline.py`:

1. import に `replace`(`from dataclasses import dataclass, replace`)を足す。`Task`、`Project`、`Status` は既存の import を使う。
2. `computed_end` を次に置き換える(`rate` を足す)。

```python
def computed_end(
    start: datetime | None,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    deadline: datetime | None = None,
    rate: float = 1.0,
) -> datetime | None:
    """手入力を使わない完了予定。工数を換算率で割って算出し、算出できなければ締切、締切もなければ開始予定の1日後。"""
    if start is not None and effort_hours > 0:
        end = calc_end(start, effort_hours / combine_rate(rate, 1.0), daily_hours, work_start, holidays)
        if end is not None:
            return end
    if deadline is not None:
        return deadline  # 開始予定より前でも、そのまま使う(遅れている状態が見える)
    if start is None:
        return None
    try:
        return start + timedelta(days=1)
    except OverflowError:
        return None
```
3. `effective_end` の `computed_end(...)` 呼び出しの末尾に `conversion_rate(task, project),` を足す。
4. `computed_end` の前に追加する。

```python
def combine_rate(ratio: float, allocation: float) -> float:
    """換算率 = 相対比率 × 割り当て率。使えない値(0以下・NaN・inf)のときは換算しない(1.0)。"""
    rate = ratio * allocation
    return rate if isfinite(rate) and rate > 0 else 1.0


def conversion_rate(task: Task, project: Project) -> float:
    member = next((m for m in project.members if m.name == task.assignee), None)
    if member is None:
        return 1.0
    return combine_rate(member.ratio, task.allocation)


def effort_days(effort_hours: float, rate: float, daily_hours: float) -> float | None:
    """基準の人の工数(h)を、換算率と稼働可能時間で日数にする。使えない値はNone。"""
    if not isfinite(effort_hours) or effort_hours <= 0:
        return None
    if not isfinite(daily_hours) or daily_hours <= 0:
        return None
    return effort_hours / combine_rate(rate, 1.0) / daily_hours
```
5. `deadline_position` の後ろに追加する。

```python
def interval_span(
    start: datetime, end: datetime, columns: list[Column]
) -> tuple[float, float]:
    """区間の(左端, 幅)を列の単位で返す。幅は0以上。"""
    left = _position(start, columns)
    right = _position(end, columns)
    return left, max(right - left, 0.0)


@dataclass(frozen=True)
class Overload:
    """担当者の割り当て合計が100%を超える期間。totalは期間内の合計の最大値(1.0 = 100%)。"""

    member: str
    start: datetime
    end: datetime
    total: float


OVERLOAD_EPSILON = 1e-9  # 浮動小数の誤差で、ちょうど100%を超過にしない


def _counted_span(
    task: Task, project: Project, holidays: dict[date, str]
) -> tuple[datetime, datetime] | None:
    """割り当ての合計に数えるタスクの期間。数えない(担当者なし・終了・開始予定なしなど)ときはNone。"""
    if not task.assignee or task.status is Status.DONE or task.planned_start is None:
        return None
    if all(m.name != task.assignee for m in project.members):
        return None
    end = effective_end(task, project, holidays)
    if end is None or end <= task.planned_start:
        return None
    return task.planned_start, end


def overallocations(project: Project, holidays: dict[date, str]) -> list[Overload]:
    """同じ担当者の、期間が重なるタスクの割り当て率の合計が100%を超える期間。"""
    spans: dict[str, list[tuple[datetime, datetime, float]]] = {}
    for task in project.all_tasks():
        counted = _counted_span(task, project, holidays)
        if counted is not None and task.assignee is not None:
            spans.setdefault(task.assignee, []).append((*counted, task.allocation))
    result: list[Overload] = []
    for name, items in spans.items():
        points = sorted({p for start, end, _ in items for p in (start, end)})
        current: Overload | None = None
        for left, right in zip(points, points[1:]):
            total = sum(a for start, end, a in items if start <= left and right <= end)
            if total > 1.0 + OVERLOAD_EPSILON:
                if current is not None and current.end == left:
                    current = replace(current, end=right, total=max(current.total, total))
                else:
                    if current is not None:
                        result.append(current)
                    current = Overload(name, left, right, total)
            elif current is not None:
                result.append(current)
                current = None
        if current is not None:
            result.append(current)
    return result


def clip_overloads(
    task: Task, project: Project, holidays: dict[date, str], overloads: list[Overload]
) -> list[Overload]:
    """そのタスクの期間に重なる超過区間を、タスクの期間に切り詰めて返す。"""
    counted = _counted_span(task, project, holidays)
    if counted is None:
        return []
    start, end = counted
    clipped: list[Overload] = []
    for overload in overloads:
        if overload.member != task.assignee:
            continue
        left, right = max(overload.start, start), min(overload.end, end)
        if left < right:
            clipped.append(replace(overload, start=left, end=right))
    return clipped
```
6. `bar_span` の本体を `interval_span` を使う形に直してもよいが、変えなくてよい。

- [ ] **Step 5: 通す**

Run: `uv run pytest -q 2>&1 | tail -6 && uvx ty check src | tail -2`
Expected: PASS。`test_a_faster_member_finishes_earlier` の期待値(10/12 12:30)は、15h / 1.5 = 10h を、金 6.5h + 月 3.5h(9:00 + 3.5h = 12:30)で割り当てた値。違う場合は、`calc_end` の規則(始業 9:00 から連続 6.5h)で再計算して、テストの期待値を直す(実装ではなく)。`test_a_smaller_allocation_finishes_later` も同様に、13h = 金 6.5h + 月 6.5h(9:00 + 6.5h = 15:30)。

- [ ] **Step 6: コミットして本体にマージする**

```bash
git add -A
git commit -m "担当者の換算率を完了予定の算出に反映し、割り当て合計の超過を求める

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/resources
git merge --no-ff feature/resources-calc -m "換算と超過の計算をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 3: メンバーの管理

**Branch:** `feature/resources-members`

**Files:**
- Modify: `src/projectapp/forms.py`、`src/projectapp/views.py`
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `Member`、`MIN_RATIO`/`MAX_RATIO`、`Project.all_tasks()`。`exceeds_decimals`、`HOURS_DECIMALS`、`disposable`(既存)。
- Produces:
  - `forms.py`: `MemberRow(original: str | None, name: str, ratio_percent: float | None)`(dataclass)。`build_members(rows: list[MemberRow], originals: list[str], assigned: Callable[[str], int]) -> tuple[list[Member], dict[str, str]]`(メンバー一覧と、改名の対応 `{旧: 新}`)。`open_members_dialog(members: list[Member], assigned: Callable[[str], int], on_apply: Callable[[list[Member], dict[str, str]], object]) -> None`。
  - マーカー: `open-members`(ヘッダーのボタン)、`member-name-{i}`、`member-ratio-{i}`、`member-delete-{i}`、`member-add`、`member-apply`、`member-error`。
  - `views.py`: `MainView.open_members()`、`MainView.assigned_count(name: str) -> int`、`MainView.apply_members(members: list[Member], renames: dict[str, str]) -> None`。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/resources
git checkout -b feature/resources-members
```

- [ ] **Step 2: 失敗するテストを書く(検証)**

`test/test_forms.py` の import に `MemberRow`、`build_members` を足す(`Member` を `projectapp.models` から)。末尾に追加する。

```python
def rows(*pairs: tuple[str | None, str, float | None]) -> list[MemberRow]:
    return [MemberRow(o, n, r) for o, n, r in pairs]


def no_tasks(_name: str) -> int:
    return 0


def test_build_members_converts_percent_to_ratio_and_trims_names() -> None:
    members, renames = build_members(rows((None, " 田中 ", 120.0)), [], no_tasks)
    assert members == [Member("田中", 1.2)]
    assert renames == {}


def test_build_members_rejects_a_blank_name() -> None:
    with pytest.raises(ValueError, match="名前"):
        build_members(rows((None, "  ", 100.0)), [], no_tasks)


def test_build_members_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="重複"):
        build_members(rows((None, "田中", 100.0), (None, "田中 ", 80.0)), [], no_tasks)


@pytest.mark.parametrize("ratio", [None, 9.99, 300.01, 0.0, -10.0, float("nan"), float("inf"), 100.123])
def test_build_members_rejects_a_bad_ratio(ratio: float | None) -> None:
    with pytest.raises(ValueError, match="相対比率"):
        build_members(rows((None, "田中", ratio)), [], no_tasks)


@pytest.mark.parametrize("ratio", [10.0, 300.0, 100.25])
def test_build_members_accepts_the_boundaries(ratio: float) -> None:
    members, _ = build_members(rows((None, "田中", ratio)), [], no_tasks)
    assert members[0].ratio == pytest.approx(ratio / 100)


def test_build_members_reports_renames() -> None:
    _, renames = build_members(rows(("田中", "田中太郎", 100.0)), ["田中"], no_tasks)
    assert renames == {"田中": "田中太郎"}


def test_build_members_allows_swapping_two_names() -> None:
    _, renames = build_members(
        rows(("A", "B", 100.0), ("B", "A", 100.0)), ["A", "B"], no_tasks
    )
    assert renames == {"A": "B", "B": "A"}


def test_build_members_rejects_deleting_a_member_with_tasks() -> None:
    counts = {"田中": 2}
    with pytest.raises(ValueError, match="田中.*2件"):
        build_members([], ["田中"], lambda name: counts.get(name, 0))


def test_build_members_allows_deleting_a_member_without_tasks() -> None:
    members, _ = build_members([], ["田中"], no_tasks)
    assert members == []


def test_build_members_rejects_taking_the_name_of_a_member_that_is_deleted_with_tasks() -> None:
    counts = {"B": 1}
    with pytest.raises(ValueError, match="B.*1件"):
        build_members(rows(("A", "B", 100.0)), ["A", "B"], lambda name: counts.get(name, 0))
```

- [ ] **Step 3: 失敗するテストを書く(画面)**

`test/test_views.py` の末尾に追加する(`mount_capturing`、`wait_until`、`save_cache`、`Member`、`Task` は既存の import を使う。`Member` が未 import なら足す)。

```python
async def open_members_dialog_view(user: User, tmp_path: Path) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    return views[0]


async def test_the_members_dialog_adds_a_member(user: User, tmp_path: Path) -> None:
    view = await open_members_dialog_view(user, tmp_path)
    user.find(marker="open-members").click()
    user.find(marker="member-add").click()
    user.find(marker="member-name-0").type("田中")
    user.find(marker="member-ratio-0").clear().type("120")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [Member("田中", 1.2)])
    assert view.is_dirty()


async def test_the_members_dialog_rejects_a_duplicate_name(user: User, tmp_path: Path) -> None:
    view = await open_members_dialog_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-add").click()
    user.find(marker="member-name-1").type("田中")
    user.find(marker="member-apply").click()
    await user.should_see("重複")
    assert view.project.members == [Member("田中", 1.0)]


async def test_applying_the_same_members_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_members_dialog_view(user, tmp_path)
    view.project.members = [Member("田中", 1.2)]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-apply").click()
    await asyncio.sleep(0.3)
    assert not view.is_dirty()


async def test_renaming_a_member_renames_the_assignee_of_its_tasks(user: User, tmp_path: Path) -> None:
    view = await open_members_dialog_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0), Member("鈴木", 1.0)]
    view.project.tasks = [Task("a", assignee="田中"), Task("b", assignee="鈴木"), Task("c")]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-name-0").clear().type("田中太郎")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.tasks[0].assignee == "田中太郎")
    assert [t.assignee for t in view.project.tasks] == ["田中太郎", "鈴木", None]
    assert [m.name for m in view.project.members] == ["田中太郎", "鈴木"]


async def test_a_member_with_tasks_cannot_be_deleted(user: User, tmp_path: Path) -> None:
    view = await open_members_dialog_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.project.tasks = [Task("a", assignee="田中")]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-delete-0").click()
    user.find(marker="member-apply").click()
    await user.should_see("1件")
    assert view.project.members == [Member("田中", 1.0)]


async def test_a_member_without_tasks_can_be_deleted(user: User, tmp_path: Path) -> None:
    view = await open_members_dialog_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-delete-0").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [])


async def test_the_members_dialog_leaves_no_elements_after_hide(user: User, tmp_path: Path) -> None:
    await open_members_dialog_view(user, tmp_path)
    user.find(marker="open-members").click()
    await user.should_see(marker="member-add")
    user.find(kind=ui.dialog).trigger("hide")
    await user.should_not_see(marker="member-add")
```
(`asyncio`、`ui`、`Member` が `test_views.py` の import に無ければ足す。ヘルプなど他のダイアログも `ui.dialog` なので、`trigger("hide")` で一緒に消えてよい。)

- [ ] **Step 4: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q 2>&1 | tail -6`
Expected: FAIL / ERROR(`MemberRow` が import できない)

- [ ] **Step 5: 検証関数を実装する**

`src/projectapp/forms.py` の import に `dataclass`(`from dataclasses import dataclass, replace`)、`MAX_RATIO`、`MIN_RATIO`、`Member` を足す。`build_work_settings` の後に追加する。

```python
@dataclass
class MemberRow:
    """メンバーのダイアログの1行。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    ratio_percent: float | None


def build_members(
    rows: list[MemberRow], originals: list[str], assigned: Callable[[str], int]
) -> tuple[list[Member], dict[str, str]]:
    """ダイアログの行を検証して、メンバー一覧と、改名の対応({旧: 新})を返す。"""
    members: list[Member] = []
    renames: dict[str, str] = {}
    seen: set[str] = set()
    low, high = MIN_RATIO * 100, MAX_RATIO * 100
    for row in rows:
        name = (row.name or "").strip()
        if not name:
            raise ValueError("名前を入力してください")
        if name in seen:
            raise ValueError(f"名前が重複しています: {name}")
        seen.add(name)
        ratio = row.ratio_percent
        if ratio is None or not isfinite(ratio) or not low - 1e-9 <= ratio <= high + 1e-9:
            raise ValueError(f"相対比率は{low:g}〜{high:g}%で入力してください")
        if exceeds_decimals(ratio):
            raise ValueError(f"相対比率は小数点以下{HOURS_DECIMALS}桁までで入力してください")
        members.append(Member(name, round(ratio / 100, 4)))
        if row.original is not None and row.original != name:
            renames[row.original] = name
    kept = {row.original for row in rows if row.original is not None}
    for original in originals:
        if original not in kept and (count := assigned(original)):
            raise ValueError(f"{original} を担当するタスクが{count}件あります")
    return members, renames
```
(`exceeds_decimals` は `Decimal(repr(hours))` を使うので、ratio の float にもそのまま使える。`100.123` は 3 桁なので拒否される。)

- [ ] **Step 6: ダイアログを実装する**

`src/projectapp/forms.py` の `open_settings_dialog` の後に追加する。

```python
def open_members_dialog(
    members: list[Member],
    assigned: Callable[[str], int],
    on_apply: Callable[[list[Member], dict[str, str]], object],
) -> None:
    rows = [MemberRow(m.name, m.name, round(m.ratio * 100, 2)) for m in members]
    originals = [m.name for m in members]
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[28rem] max-w-full"):
        ui.label("メンバー").classes("text-h6")

        @ui.refreshable
        def table() -> None:
            with ui.column().classes("w-full gap-1"):
                if not rows:
                    ui.label("メンバーがいません").classes("text-grey")
                for index, row in enumerate(rows):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.input(
                            "名前",
                            value=row.name,
                            on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                        ).classes("flex-1").mark(f"member-name-{index}")
                        ui.number(
                            "相対比率(%)",
                            value=row.ratio_percent,
                            min=MIN_RATIO * 100,
                            max=MAX_RATIO * 100,
                            step=5,
                            on_change=lambda e, r=row: setattr(r, "ratio_percent", e.value),
                        ).classes("w-32").mark(f"member-ratio-{index}")
                        ui.button(icon="delete", on_click=lambda r=row: remove(r)).props(
                            "flat dense round"
                        ).mark(f"member-delete-{index}")

        def remove(row: MemberRow) -> None:
            rows.remove(row)
            table.refresh()

        def add() -> None:
            rows.append(MemberRow(None, "", 100.0))
            table.refresh()

        table()
        ui.button("メンバーを追加", icon="add", on_click=add).props("flat").mark("member-add")
        error = ui.label("").classes("text-negative").mark("member-error")

        def apply() -> None:
            try:
                result = build_members(rows, originals, assigned)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_apply(*result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("member-apply")
    dialog.open()
```

- [ ] **Step 7: `views.py` に足す**

import に `open_members_dialog` と `Member` を足す。`open_settings` の次にメソッドを追加する。

```python
    def open_members(self) -> None:
        open_members_dialog(self.project.members, self.assigned_count, self.apply_members)

    def assigned_count(self, name: str) -> int:
        return sum(1 for task in self.project.all_tasks() if task.assignee == name)

    def apply_members(self, members: list[Member], renames: dict[str, str]) -> None:
        """メンバーを更新し、改名をタスクの担当者に伝える。保存はしない(編集中の判定に入る)。"""
        if members == self.project.members and not renames:
            return
        self.project.members = members
        if renames:
            for task in self.project.all_tasks():
                if task.assignee in renames:
                    task.assignee = renames[task.assignee]
        self.gantt.set_project(self.project)
```
`header()` の「設定」ボタンの次に追加する。

```python
                ui.button("メンバー", icon="group", on_click=self.open_members).mark(
                    "open-members"
                )
```

- [ ] **Step 8: 通す**

Run: `uv run pytest -q 2>&1 | tail -8 && uvx ty check src | tail -2`
Expected: PASS。`ui.number` の `clear().type("120")` で値が変わらないテストがあれば、`with user.client:` の中で `element.set_value(120)` を使う。

- [ ] **Step 9: コミットして本体にマージする**

```bash
git add -A
git commit -m "メンバーのダイアログ(追加・改名・削除・相対比率)を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/resources
git merge --no-ff feature/resources-members -m "メンバーの管理をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 4: タスクのダイアログ(担当者、割り当て率、換算の表示、警告)

**Branch:** `feature/resources-dialog`

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task`)、`src/projectapp/task_dialog.py`、`src/projectapp/views.py`
- Test: `test/test_forms.py`、`test/test_task_dialog.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1〜3 の `Task.allocation`、`Member`、`combine_rate`、`effort_days`、`overallocations`、`clip_overloads`、`effective_end`。
- Produces:
  - `build_task(..., assignee: str, allocation_percent: float | None)`:`allocation_percent`(必須のキーワード)。担当者(空白を取り除いた後)が空なら `allocation` は 1.0。担当者がいるとき `allocation_percent` が `None`・NaN・inf・1〜100 の範囲外なら `ValueError("割り当て率は1〜100%で入力してください")`。保存は `round(percent / 100, 4)`。
  - `open_task_dialog(task, on_save, work_start=..., on_delete=None, daily_hours=..., holidays=None, members: list[Member] | None = None)`
  - `DateTimeFields(task, work_start, daily_hours, holidays, rate: float = 1.0)` と `DateTimeFields.set_rate(rate: float) -> None`。
  - マーカー: `task-assignee`(選択)、`task-allocation`(割り当て率の数値欄)、`task-conversion`(換算の表示)。
  - `MainView.save_task` が保存後に割り当て超過を通知(`MainView.warn_overallocation(task)`)。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/resources
git checkout -b feature/resources-dialog
```

- [ ] **Step 2: 失敗するテストを書く(`build_task`)**

`test/test_forms.py` の `make` のキーに `"allocation_percent": 100.0,` を足す(`"assignee": "",` の次)。末尾に追加する。

```python
def test_allocation_is_stored_as_a_fraction_when_there_is_an_assignee() -> None:
    task = make(assignee="田中", allocation_percent=60.0)
    assert task.allocation == pytest.approx(0.6)


def test_allocation_is_one_without_an_assignee() -> None:
    assert make(assignee="", allocation_percent=60.0).allocation == 1.0
    assert make(assignee="  ", allocation_percent=None).allocation == 1.0


@pytest.mark.parametrize("percent", [None, 0.0, 0.99, 100.01, -5.0, float("nan"), float("inf")])
def test_a_bad_allocation_is_rejected_when_there_is_an_assignee(percent: float | None) -> None:
    with pytest.raises(ValueError, match="割り当て率"):
        make(assignee="田中", allocation_percent=percent)


@pytest.mark.parametrize("percent", [1.0, 100.0, 33.33])
def test_allocation_boundaries_are_accepted(percent: float) -> None:
    assert make(assignee="田中", allocation_percent=percent).allocation == pytest.approx(percent / 100)
```
さらに、`build_task` を `allocation_percent` なしで呼ぶ `test_build_task_requires_the_deadline_text` は、`TypeError` のままで通る(キーワード不足)。

- [ ] **Step 3: 失敗するテストを書く(ダイアログ)**

`test/test_task_dialog.py` の `mount_dialog` に `members: list[Member] | None = None` を足し、`open_task_dialog(...)` の呼び出しに `members=members,` を渡す(`Member` を `projectapp.models` から import)。末尾に追加する。

```python
TANAKA = Member("田中", 1.2)
SUZUKI = Member("鈴木", 1.0)


async def test_the_assignee_is_chosen_from_the_members(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    select = user.find(marker="task-assignee").elements.pop()
    assert select.options == {"": "(なし)", "田中": "田中", "鈴木": "鈴木"}
    with user.client:
        select.set_value("田中")
    user.find(marker="task-save").click()
    assert saved[0].assignee == "田中"


async def test_without_an_assignee_the_allocation_is_disabled_and_saved_as_one(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    allocation = user.find(marker="task-allocation").elements.pop()
    assert allocation.enabled is False
    user.find(marker="task-save").click()
    assert saved[0].assignee is None and saved[0].allocation == 1.0


async def test_the_allocation_is_enabled_with_an_assignee_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    allocation = user.find(marker="task-allocation").elements.pop()
    assert allocation.enabled is True
    with user.client:
        allocation.set_value(60)
    user.find(marker="task-save").click()
    assert saved[0].allocation == pytest.approx(0.6)


async def test_returning_the_assignee_to_none_saves_an_allocation_of_one(user: User) -> None:
    saved: list[Task] = []
    task = Task("旧", assignee="田中", allocation=0.5)
    mount_dialog(task, saved, members=[TANAKA])
    await open_dialog(user)
    assert user.find(marker="task-allocation").elements.pop().value == 50
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("")
    user.find(marker="task-save").click()
    assert saved[0].assignee is None and saved[0].allocation == 1.0


async def test_the_conversion_is_shown_with_an_assignee_and_effort(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    assert conversion.text == ""
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
        user.find(marker="task-allocation").elements.pop().set_value(80)
    user.find(marker="task-effort").clear().type("15")
    # 15h / (1.2 * 0.8) / 6.5h = 2.40日
    assert conversion.text == "15h → 2.4日分(相対比率 120% × 割り当て 80%)"


async def test_the_conversion_disappears_without_effort_or_assignee(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    assert conversion.text != ""
    user.find(marker="task-effort").clear()
    assert conversion.text == ""
    user.find(marker="task-effort").type("15")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("")
    assert conversion.text == ""


async def test_the_computed_end_reflects_the_conversion(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.5)])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-12 12:30"


async def test_changing_the_assignee_asks_for_confirmation_on_close(user: User) -> None:
    mount_dialog(Task("旧"), [], members=[TANAKA])
    await open_dialog(user)
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")
```
(選択肢が dict で返らない場合は、`list(select.options)` などの形に合わせる。)

- [ ] **Step 4: 失敗するテストを書く(警告)**

`test/test_views.py` の末尾に追加する。

```python
async def test_saving_a_task_that_overloads_the_assignee_warns(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中", 1.0)]
    view.save_task(
        None, None,
        Task("a", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9),
             assignee="田中", allocation=0.6),
    )
    assert not user.notify.contains("割り当て")
    view.save_task(
        None, None,
        Task("b", planned_start=datetime(2026, 10, 7), planned_end=datetime(2026, 10, 12),
             assignee="田中", allocation=0.6),
    )
    assert user.notify.contains("田中 の割り当てが最大120%")
    assert len(view.project.tasks) == 2  # 警告しても保存はされる


async def test_saving_a_task_that_does_not_overload_shows_no_warning(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中", 1.0)]
    view.save_task(
        None, None,
        Task("a", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9),
             assignee="田中", allocation=0.7),
    )
    view.save_task(
        None, None,
        Task("b", planned_start=datetime(2026, 10, 7), planned_end=datetime(2026, 10, 12),
             assignee="田中", allocation=0.3),
    )
    assert not user.notify.contains("割り当て")
```

- [ ] **Step 5: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_task_dialog.py test/test_views.py -q 2>&1 | tail -8`
Expected: FAIL(`allocation_percent` がない、`task-assignee` マーカーがない など)

- [ ] **Step 6: `build_task` を直す**

`src/projectapp/forms.py` の `build_task` の引数に `allocation_percent: float | None,` を足す(`assignee: str,` の次)。本体の `base = existing or Task(clean)` の次あたりに、検証を足す。

```python
    assignee_name = assignee.strip()
    allocation = 1.0
    if assignee_name:
        if (
            allocation_percent is None
            or not isfinite(allocation_percent)
            or not MIN_ALLOCATION * 100 <= allocation_percent <= MAX_ALLOCATION * 100
        ):
            raise ValueError(
                f"割り当て率は{MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}%で入力してください"
            )
        allocation = round(allocation_percent / 100, 4)
```
(`base` の行は検証の前にある。`return replace(...)` の `assignee=assignee.strip() or None,` はそのままにし、`allocation=allocation,` を足す。import に `MAX_ALLOCATION`、`MIN_ALLOCATION` を足す。)

- [ ] **Step 7: `DateTimeFields` に換算率を足す**

`src/projectapp/task_dialog.py` の `DateTimeFields.__init__` の引数の末尾に `rate: float = 1.0,` を足し、`self._rate = rate` を `self.effort = task.effort_hours` の次の行に置く。メソッドを追加する。

```python
    def set_rate(self, rate: float) -> None:
        self._rate = rate
        self._refresh_end()
```
`_computed_text` の `computed_end(...)` の呼び出しの引数の末尾に `self._rate,` を足す(`deadline,` の次)。

- [ ] **Step 8: ダイアログを直す**

`src/projectapp/task_dialog.py`:

1. import に `Member`(`projectapp.models`)、`combine_rate`、`effort_days`(`projectapp.timeline`)を足す。
2. `open_task_dialog` の引数の末尾に `members: list[Member] | None = None,` を足す。
3. `DateTimeFields(...)` の呼び出しの前に、メンバーと換算率の準備を足す。

```python
    member_list = members or []
    initial_member = next((m for m in member_list if m.name == initial.assignee), None)
    initial_rate = (
        combine_rate(initial_member.ratio, initial.allocation) if initial_member else 1.0
    )
```
そして `DateTimeFields(initial, work_start, daily_hours, holidays or {}, initial_rate)` にする。
4. `effort` の行の次(`effort.on_value_change(...)` の前後)に、担当者と割り当て率の行と換算の表示を足す。`second_row` の外側に置く。

```python
        with ui.row().classes("w-full no-wrap gap-4"):
            assignee = (
                ui.select(
                    {"": "(なし)", **{m.name: m.name for m in member_list}},
                    label="担当者",
                    value=initial.assignee if initial_member else "",
                )
                .classes("flex-1")
                .mark("task-assignee")
            )
            allocation = (
                ui.number(
                    "割り当て率(%)",
                    value=round(initial.allocation * 100, 2),
                    min=MIN_ALLOCATION * 100,
                    max=MAX_ALLOCATION * 100,
                    step=5,
                )
                .classes("flex-1")
                .mark("task-allocation")
            )
        conversion = ui.label("").classes("text-caption text-grey").mark("task-conversion")

        def current_member() -> Member | None:
            return next((m for m in member_list if m.name == assignee.value), None)

        def refresh_conversion(_event: object = None) -> None:
            member = current_member()
            allocation.set_enabled(member is not None)
            fraction = (allocation.value or 100) / 100 if member else 1.0
            rate = combine_rate(member.ratio, fraction) if member else 1.0
            fields.set_rate(rate)
            days = effort_days(effort.value or 0.0, rate, daily_hours) if member else None
            if member is None or days is None:
                conversion.set_text("")
                return
            conversion.set_text(
                f"{effort.value:g}h → {days:.1f}日分"
                f"(相対比率 {member.ratio * 100:g}% × 割り当て {fraction * 100:g}%)"
            )

        assignee.on_value_change(refresh_conversion)
        allocation.on_value_change(refresh_conversion)
        refresh_conversion()
```
`effort.on_value_change(lambda e: fields.set_effort(e.value))` を、次に置き換える(換算の表示も更新する)。

```python
        effort.on_value_change(
            lambda e: (fields.set_effort(e.value), refresh_conversion())
        )
```
(`refresh_conversion` が定義される前に `effort.on_value_change` を置かないよう、この行を `refresh_conversion()` の呼び出しの後ろに移す。)
5. 古い `assignee = ui.input("担当者", ...)` の行を削除する。
6. `current()` の `assignee.value` はそのまま、`allocation.value` を足す。
7. `build_task(...)` の呼び出しを次のようにする。

```python
                    assignee=assignee.value or "",
                    allocation_percent=allocation.value,
```
8. import に `MAX_ALLOCATION`、`MIN_ALLOCATION` を足す。

- [ ] **Step 9: `views.py` を直す**

1. `add_task`・`add_top_task`・`edit_task` の `open_task_dialog(...)` の呼び出しに `members=self.project.members,` を足す。
2. import に `clip_overloads`、`effective_end`、`overallocations` を `projectapp.timeline` から足す。
3. `save_task` の末尾(`self.gantt.set_project(self.project)` の後)に `self.warn_overallocation(task)` を足し、メソッドを追加する。

```python
    def warn_overallocation(self, task: Task) -> None:
        """保存したタスクが担当者の割り当て合計の超過に関わるなら、通知する(保存は妨げない)。"""
        if not task.assignee:
            return
        overloads = overallocations(self.project, self.holidays)
        mine = clip_overloads(task, self.project, self.holidays, overloads)
        if mine:
            peak = max(o.total for o in mine)
            ui.notify(
                f"{task.assignee} の割り当てが最大{round(peak * 100)}%になる期間があります",
                type="warning",
            )
```

- [ ] **Step 10: 通す**

Run: `uv run pytest -q 2>&1 | tail -10 && uvx ty check src | tail -2`
Expected: PASS。既存の `test_task_dialog.py` / `test_forms.py` のうち、担当者の自由入力(`ui.input`)を前提にしたもの(`grep -n "担当者\|assignee" test/test_task_dialog.py test/test_forms.py`)は、メンバーを渡す形に直す。`test_blank_assignee_and_dates_become_none` のように、`build_task` の入力を直接検証するものは、`allocation_percent` が `make` の既定で入るので、そのまま通る。

- [ ] **Step 11: コミットして本体にマージする**

```bash
git add -A
git commit -m "タスクのダイアログに担当者(メンバーから選択)と割り当て率、換算の表示、超過の警告を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/resources
git merge --no-ff feature/resources-dialog -m "タスクのダイアログの拡張をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 5: ガントの縞

**Branch:** `feature/resources-gantt`

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: Task 2 の `overallocations`、`clip_overloads`、`interval_span`、`Overload`。
- Produces: 棒の内側の縞(マーカー `overload-{key}-{ti}-{n}`。`key` は `"top"` かセクション番号、`n` は区間の番号)。棒のツールチップ(超過があるとき)。定数 `OVERLOAD_STRIPES`(CSS の背景)。

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/resources
git checkout -b feature/resources-gantt
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_gantt.py` の import に `Member`(`projectapp.models`)を足す。末尾に追加する(`BASE` は 2026-10-05(月)。日次スケールの列の幅は 40px、名前の列は 200px)。

```python
def overloaded_project() -> Project:
    a = Task(
        "A", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9),
        assignee="田中", allocation=0.6,
    )
    b = Task(
        "B", planned_start=datetime(2026, 10, 7), planned_end=datetime(2026, 10, 12),
        assignee="田中", allocation=0.6,
    )
    return Project("demo", base_date=BASE, members=[Member("田中")], tasks=[a, b])


async def test_stripes_cover_only_the_overloaded_part_of_each_bar(user: User) -> None:
    mount(overloaded_project())
    await user.open("/")
    a = user.find(marker="overload-top-0-0").elements.pop()
    b = user.find(marker="overload-top-1-0").elements.pop()
    # 超過は 10/7〜10/9。Aの棒は 10/5 から、Bの棒は 10/7 から始まる
    assert (a._style["left"], a._style["width"]) == ("80.0px", "80.0px")
    assert (b._style["left"], b._style["width"]) == ("0.0px", "80.0px")


async def test_stripes_do_not_block_clicks_on_the_bar(user: User) -> None:
    recorder = mount(overloaded_project())
    await user.open("/")
    assert user.find(marker="overload-top-0-0").elements.pop()._style["pointer-events"] == "none"
    user.find(marker="bar-top-0").click()
    assert recorder.events == [("edit_task", (None, 0))]


async def test_the_bar_tooltip_names_the_member_and_the_peak(user: User) -> None:
    mount(overloaded_project())
    await user.open("/")
    bar = user.find(marker="bar-top-0").elements.pop()
    tooltips = [c for c in bar.default_slot.children if isinstance(c, ui.tooltip)]
    assert len(tooltips) == 1
    assert "田中 の割り当てが最大120%" in tooltips[0].text
    assert "2026-10-07" in tooltips[0].text


async def test_no_stripes_without_an_overload(user: User) -> None:
    project = overloaded_project()
    project.tasks[1].allocation = 0.4  # 合計ちょうど100%
    mount(project)
    await user.open("/")
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="overload-top-0-0")
    await user.should_not_see(marker="overload-top-1-0")


async def test_tasks_that_are_done_or_unassigned_get_no_stripes(user: User) -> None:
    project = overloaded_project()
    project.tasks[1].status = Status.DONE
    mount(project)
    await user.open("/")
    await user.should_not_see(marker="overload-top-0-0")
    await user.should_not_see(marker="overload-top-1-0")


async def test_stripes_stay_inside_a_thin_bar(user: User) -> None:
    a = Task(
        "A", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 5, 0, 1),
        assignee="田中", allocation=0.6,
    )
    b = Task(
        "B", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 5, 0, 1),
        assignee="田中", allocation=0.6,
    )
    mount(Project("demo", base_date=BASE, members=[Member("田中")], tasks=[a, b]))
    await user.open("/")
    stripe = user.find(marker="overload-top-0-0").elements.pop()
    bar = user.find(marker="bar-top-0").elements.pop()
    bar_width = float(bar._style["width"].removesuffix("px"))
    left = float(stripe._style["left"].removesuffix("px"))
    width = float(stripe._style["width"].removesuffix("px"))
    assert 0.0 <= left and left + width <= bar_width + 1e-6
```
(`Status` が import されていなければ足す。`recorder.events` の形は既存の `Recorder` に合わせる。ツールチップは `ui.tooltip`(`TextElement`)なので `.text` で読む。構造が合わなければ、`bar.default_slot.children` の中身を確認して合わせる。)

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "stripes or tooltip or overload" 2>&1 | tail -6`
Expected: FAIL(マーカーがない)

- [ ] **Step 4: 実装する**

`src/projectapp/gantt.py`:

1. import に `Overload`、`clip_overloads`、`interval_span`、`overallocations` を足す。
2. 定数を足す(`DEADLINE_COLOR` の次)。

```python
OVERLOAD_STRIPES = (  # 割り当て合計が100%を超える期間の縞。タスクの色に依存しないよう白と黒の半透明を重ねる
    "repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 4px, rgba(0,0,0,0.35) 4px 8px)"
)
```
3. `render` で、描画のたびに超過を求めて `task_row` に渡す。`render` の `columns = build_columns(...)` の次に追加する。

```python
        self.overloads = overallocations(self.project, self.holidays)
```
(`__init__` に `self.overloads: list[Overload] = []` も足す。)
4. `task_row` の棒を作る部分を、棒を変数に受けて、縞とツールチップを足す形に直す。

```python
            if span is not None:
                left, length = span
                bar_width = max(length * width, MIN_BAR_PX)
                with ui.element("div").style(
                    f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                    f" width: {bar_width:.1f}px; top: 6px;"
                    f" height: {ROW_HEIGHT_PX - 12}px;"
                    f" background: {task.color if is_hex_color(task.color) else DEFAULT_COLOR};"
                    " border-radius: 4px; cursor: pointer; overflow: hidden"
                ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                    f"bar-{key}-{ti}"
                ):
                    self.overload_stripes(key, ti, task, left, bar_width, columns, width)
```

5. メソッドを追加する。

```python
    def overload_stripes(
        self,
        key: int | str,
        ti: int,
        task: Task,
        bar_left: float,
        bar_width: float,
        columns: list[Column],
        width: int,
    ) -> None:
        """棒の内側に、割り当て合計が100%を超える期間の縞を重ねる。棒の外にははみ出さない。"""
        clipped = clip_overloads(task, self.project, self.holidays, self.overloads)
        for n, overload in enumerate(clipped):
            start, length = interval_span(overload.start, overload.end, columns)
            left_px = max((start - bar_left) * width, 0.0)
            width_px = min(length * width, bar_width - left_px)
            if width_px <= 0:
                continue
            ui.element("div").style(
                f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px;"
                f" top: 0; bottom: 0; background: {OVERLOAD_STRIPES}; pointer-events: none"
            ).mark(f"overload-{key}-{ti}-{n}")
        if clipped:
            peak = round(max(o.total for o in clipped) * 100)
            first, last = clipped[0], clipped[-1]
            ui.tooltip(
                f"{first.member} の割り当てが最大{peak}%"
                f"({first.start:%Y-%m-%d}〜{last.end:%Y-%m-%d})"
            )
```
(`overflow: hidden` を足したので、棒の角丸の内側に縞が収まる。◆ の締切の目印は、棒の外の行の子なので、影響を受けない。)

- [ ] **Step 5: 通す**

Run: `uv run pytest -q 2>&1 | tail -8 && uvx ty check src | tail -2`
Expected: PASS。`overflow: hidden` で既存の棒のテスト(`_style` の期待値)が変わる場合は、`overflow` を含まない比較に直す。

- [ ] **Step 6: コミットして本体にマージする**

```bash
git add -A
git commit -m "ガントの棒の内側に、割り当て合計が100%を超える期間の縞を重ねる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/resources
git merge --no-ff feature/resources-gantt -m "ガントの縞をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 6: 文書

**Branch:** `feature/resources-docs`

**Files:**
- Modify: `CLAUDE.md`、`docs/development.md`、`docs/superpowers/specs/2026-10-03-resources-design.md`(関数の署名のずれ)、`.claude/MEMORY.md`

- [ ] **Step 1: ブランチを切る**

```bash
git checkout feature/resources
git checkout -b feature/resources-docs
```

- [ ] **Step 2: `CLAUDE.md` を更新する**

`CLAUDE.md` のコンセプトに、次の行を足す(`人的リソース1人に対して、project内で、最大100%まで分散できる` の行の前後)。

```
- `メンバー`（担当者）は、プロジェクトごとに名前と`相対比率`（基準の人を100%とした作業速度。10〜300%）で管理する
- タスクの担当者は`メンバー`から選び、そのタスクに使う`割り当て率`（担当者の時間の1〜100%）を設定できる
- 工数（時間）は、基準の人が全時間をかけた場合の時間とし、`工数 ÷（相対比率 × 割り当て率）`を稼働可能時間（バッファ）の枠に割り当てて`完了予定`を算出する。ダイアログには日数に換算した値を表示する
- 同じ担当者の、期間が重なるタスクの`割り当て率`の合計が100%を超える期間は、ガントチャートの棒の内側に縞で示し、保存時に通知する（保存はできる。状態が「終了」のタスクは数えない）
```

- [ ] **Step 3: `docs/development.md` を更新する**

モジュール表の `timeline.py` の説明に「換算率(`conversion_rate`)、日工数(`effort_days`)、割り当て合計の超過(`overallocations`)」を足す。`forms.py` の説明に「メンバーのダイアログと検証(`build_members`)」を足す。「ファイル形式の注意」に次を足す。

```markdown
- メンバーの `ratio`(0.1〜3.0)とタスクの `allocation`(0.01〜1.0)は、読み込み時に検証し、範囲外は「開けませんでした」と通知する。`allocation` のないファイルは 1.0 で読む。
- メンバー一覧にない担当者名は、読み込み時にメンバー(相対比率 1.0)として追加する(古いファイルの自由入力の担当者を失わないため)。担当者名の前後の空白は取り除き、空白のみは担当者なしとする。メンバー名の重複は最初の1件を残す。
```

- [ ] **Step 4: 設計書の関数の署名のずれを直す**

`docs/superpowers/specs/2026-10-03-resources-design.md` の「日工数」の節を、実装に合わせる。

置き換え前:

```
`effort_days(task, project) -> float | None`:工数が 0 より大きく、有限のとき、`工数 ÷ 換算率 ÷ project.daily_hours`。それ以外は `None`。ダイアログの表示に使う。
```
置き換え後:

```
`effort_days(effort_hours, rate, daily_hours) -> float | None`:工数が 0 より大きく有限、`daily_hours` が 0 より大きいとき、`工数 ÷ 換算率 ÷ daily_hours`。それ以外は `None`。ダイアログの表示に使う(入力途中の値で計算するため、タスクではなく数値を受け取る)。
```
同じ節の `overloads_for(task, overloads)` は、実装の名前 `clip_overloads(task, project, holidays, overloads)` に直す。

- [ ] **Step 5: 作業記録(`.claude/MEMORY.md`)を更新する**

- 「現在の状況」に、見積もりのバッファ換算とリソース割り当て比率を `feature/resources` に実装したことと、`develop` へのマージが未実施であることを書く。テスト件数を更新する。
- 「実装済みの機能」に、メンバー、割り当て率、換算、超過の縞を書く。
- 「次にやること」から、「見積もりのバッファ換算、リソース割り当て比率(最大 100%)」を外す。

- [ ] **Step 6: 通す**

Run: `uv run pytest -q 2>&1 | tail -2 && uvx ty check src | tail -1`
Expected: PASS

- [ ] **Step 7: コミットして本体にマージする**

```bash
git add -A
git commit -m "メンバーと割り当て率の文書を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git checkout feature/resources
git merge --no-ff feature/resources-docs -m "文書の更新をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 7: 全体の確認と引き渡し

- [ ] **Step 1: 全体を通す**

```bash
git checkout feature/resources
uv run pytest --cov=projectapp -q
uvx ty check src
git status --short
```
Expected: すべて PASS、未コミットの変更なし。

- [ ] **Step 2: ユーザーに実機の確認を依頼する**

`uv run projectapp` で、次を確認してもらう(旧形式のファイルは、事前にバックアップを取る)。
1. ヘッダーの「メンバー」ボタン。ダイアログの見た目と幅、追加・改名・削除・相対比率の入力、担当するタスクがあるメンバーの削除が拒否されること、改名がタスクの担当者に伝わること。
2. タスクのダイアログ: 担当者の選択欄(先頭の「(なし)」)、割り当て率の欄(担当者なしのとき無効)、換算の表示(例: 「15h → 2.4日分(相対比率 120% × 割り当て 80%)」)、完了予定の算出値が換算を反映すること。
3. 同じ担当者の期間が重なるタスクを、合計 100% 超で保存すると、警告が通知されること。ちょうど 100% では通知されないこと。
4. ガント: 超過している期間だけ、棒の内側に縞が出ること。縞が棒の外にはみ出さないこと。ライト/ダークで見えること。棒のクリックで編集ダイアログが開くこと。ホバーのツールチップ。
5. 旧形式のファイル(自由入力の担当者を持つもの)を開くと、担当者がメンバーとして追加されること。開いただけでは「編集中」にならないこと。
6. 工数を空にする、担当者を「(なし)」に戻す: 換算の表示が消え、割り当て率が 100% で保存されること。

- [ ] **Step 3: 承認を待ってから `develop` にマージする**

ユーザーの許可を得てから:

```bash
git checkout develop
git merge --no-ff feature/resources -m "メンバーと割り当て率をマージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
uv run pytest -q && uvx ty check src
```
マージ後、`feature/resources*` のブランチを削除してよいか、ユーザーに確認する。プッシュは別に許可を得る。
