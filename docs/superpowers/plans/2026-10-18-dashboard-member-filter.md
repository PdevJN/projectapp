# ダッシュボードのメンバー絞り込みと内訳 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードを、メンバー 1 人に絞って見られるようにし、「進捗と遅れ」にメンバー別の進捗の行を足す。

**Architecture:** 集計の入口 `_tasks(project, member)` に絞り込みを足し、各 `summarize_*` へ `member` を通す(日程計算は絞り込まない元のプロジェクトで行う)。画面は期間のトグルの横にプルダウンを足し、状態は `MainView.dashboard_member` に持つ(保存しない)。ファイル形式は変えない。

**Tech Stack:** Python 3.13・NiceGUI・pytest・ty。

**Spec:** `docs/superpowers/specs/2026-10-18-dashboard-member-filter-design.md`

## Global Constraints

- `.claude/RULE.md`: すべての関数に型ヒント(引数と戻り値)。コメントは多くても 3 行以内。パッケージャーは uv(`uv run pytest`・`uv run ty check src/projectapp`)。
- 集計は NiceGUI から切り離した純粋関数(`dashboard.py`)。描画は NiceGUI の要素と CSS(`dashboard_view.py`)。
- ファイル形式(`version` は 7)は変えない。絞り込みは保存せず、元に戻す・やり直しの対象にしない。
- 共同タスクは 1 件として丸ごと数える。担当がメンバーでない人だけのタスクと担当なしのタスクは、どのメンバーの絞り込みにも入らない。
- テストの注意: `user.find(...).elements` は集合で順序がない(集合で比べる)。NiceGUI の `refresh` は遅延実行なので、`should_see` で描画を待ってから文言を読む。`pytest | tail` の終了コードは `tail` のものなので、全テストは出力をファイルに落として `$?` を見てからコミットする。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

- 絞り込んだメンバーに担当タスクが 1 件もない: 全カードが空表示になり、例外が出ない(Task 1・3)。
- 先行を持つタスクで、他のメンバーのタスクに押し出される日程: 絞り込んでも予定の時刻が変わらない(Task 1)。
- 担当なし・メンバーでない担当者だけのタスク: 絞り込みには入らず、内訳では `未割り当て` に入る(Task 1・2)。
- 絞り込み中に期間のトグルを切り替える: 絞り込みは保持される(Task 4)。
- 絞り込み中のメンバーが削除・改名された: `全員` に戻る(Task 4)。
- メンバーが 0 人: プルダウンは `全員` だけで、内訳の節は出ない(Task 3)。

---

### Task 1: 集計に `member` を通す

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: 既存の `_tasks`・`Schedule`・`summarize_*`。
- Produces:
  - `_tasks(project: Project, member: str | None = None) -> list[Task]`
  - `summarize_progress(project, holidays, now, member: str | None = None) -> Progress`
  - `summarize_team_progress(project, period=None, now=None, holidays=None, member: str | None = None) -> TeamProgress`
  - `summarize_loads(project, period, holidays, member: str | None = None) -> dict[str, LoadStats]`
  - `summarize_workload(project, period, now, holidays, member: str | None = None) -> list[WorkloadRow]`
  - `summarize_due(project, period, now, holidays, member: str | None = None) -> list[DueRow]`
  - `summarize(project, period, now, holidays, kind=PeriodKind.ALL, member: str | None = None) -> Dashboard`
  - `Dashboard.member: str | None = None`・`Dashboard.members: list[str]`(プロジェクトのメンバー名の順)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の末尾に足す(`Assignee`・`Member`・`dated`・`WEEK`・`NOW`・`project_of` は既存)。

```python
def shared_project() -> Project:
    members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    mine = Task("田中の", effort_hours=2, status=Status.RUNNING, progress=50, assignees=[Assignee("田中", 1.0)])
    shared = Task("共同", effort_hours=6, assignees=[Assignee("田中", 0.5), Assignee("佐藤", 0.5)])
    other = Task("佐藤の", effort_hours=4, status=Status.DONE, assignees=[Assignee("佐藤", 1.0)])
    unassigned = Task("担当なし", effort_hours=1)
    ghost = Task("退職者の", effort_hours=1, assignees=[Assignee("退職者", 1.0)])
    return project_of(mine, shared, other, unassigned, ghost, members=members)


def test_the_member_filter_keeps_tasks_the_member_is_on_as_whole_tasks() -> None:
    progress = summarize_progress(shared_project(), {}, NOW, "田中")
    assert progress.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 0}
    assert progress.percent == pytest.approx(100 / 8)  # (2h × 50% + 6h × 0%) / 8h。共同タスクは丸ごと


def test_the_member_filter_leaves_out_unassigned_and_non_member_tasks() -> None:
    team = summarize_team_progress(shared_project(), member="佐藤")
    assert team.hours == {Status.NOT_STARTED: 6, Status.RUNNING: 0, Status.PAUSED: 0, Status.DONE: 4}
    assert team.tasks[Status.NOT_STARTED] == ["共同"]


def test_a_member_without_tasks_gives_empty_results_without_errors() -> None:
    project = shared_project()
    project.members.append(Member("山田", 1.0))
    assert summarize_progress(project, {}, NOW, "山田").percent is None
    assert summarize_team_progress(project, member="山田").percent is None
    assert summarize_due(project, WEEK, NOW, {}, "山田") == []
    assert summarize_loads(project, WEEK, {}, "山田")["山田"].peak == 0.0


def test_the_member_filter_limits_loads_and_workload_to_that_member() -> None:
    project = project_of(
        dated("田中の", 6, 7, assignees=[Assignee("田中", 1.0)]),
        dated("佐藤の", 6, 7, assignees=[Assignee("佐藤", 1.0)]),
        members=[Member("田中", 1.0), Member("佐藤", 1.0)],
    )
    loads = summarize_loads(project, WEEK, {}, "田中")
    assert list(loads) == ["田中"]
    assert loads["田中"] == summarize_loads(project, WEEK, {})["田中"]
    rows = summarize_workload(project, WEEK, NOW, {}, "田中")
    assert [row.name for row in rows] == ["田中"]
    assert rows[0] == next(row for row in summarize_workload(project, WEEK, NOW, {}) if row.name == "田中")


def test_the_member_filter_hides_the_unassigned_workload_row() -> None:
    project = project_of(dated("担当なし", 6, 7), dated("田中の", 6, 7, assignees=[Assignee("田中", 1.0)]))
    assert UNASSIGNED in [row.name for row in summarize_workload(project, WEEK, NOW, {})]
    assert [row.name for row in summarize_workload(project, WEEK, NOW, {}, "田中")] == ["田中"]


def test_the_member_filter_keeps_schedules_pushed_by_other_members_tasks() -> None:
    blocker = dated("佐藤の", 6, 9, assignees=[Assignee("佐藤", 1.0)])
    pushed = dated("田中の", 6, 7, assignees=[Assignee("田中", 1.0)], predecessors=[blocker.id])
    project = project_of(blocker, pushed, members=[Member("田中", 1.0), Member("佐藤", 1.0)])
    everyone = next(row for row in summarize_due(project, WEEK, NOW, {}) if row.name == "田中の")
    only = summarize_due(project, WEEK, NOW, {}, "田中")
    assert [row.name for row in only] == ["田中の"] and only[0].moment == everyone.moment


def test_summarize_passes_the_member_and_lists_the_member_names() -> None:
    project = shared_project()
    everyone = summarize(project, WEEK, NOW, {})
    assert everyone.member is None and everyone.members == ["田中", "佐藤"]
    only = summarize(project, WEEK, NOW, {}, member="田中")
    assert only.member == "田中" and only.members == ["田中", "佐藤"]
    assert only.progress.counts[Status.DONE] == 0 and everyone.progress.counts[Status.DONE] == 1
    assert list(only.loads) == ["田中"] and [row.name for row in only.workload] == ["田中"]
    assert only.team.tasks[Status.NOT_STARTED] == ["共同"]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: FAIL(`member` を受け取らない `TypeError`・`Dashboard.members` がない)。

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard.py` を次のように直す。

`_tasks`:

```python
def _tasks(project: Project, member: str | None = None) -> list[Task]:
    """集計の対象のタスク。まとめは、子の工数・進捗・期限を二重に数えないよう外す。`member`があれば、その人が担当のものだけ。"""
    return [
        task
        for task in project.all_tasks()
        if task.kind is not TaskKind.SUMMARY and (member is None or member in task.assignee_names)
    ]
```

`summarize_progress`: 引数を `(project, holidays, now, member: str | None = None)` にし、ループを `for task in _tasks(project, member):` にする。

`summarize_team_progress`: 引数に `member: str | None = None` を足し、ループを `for task in _tasks(project, member):` にする。

`summarize_loads`: 引数を `(project, period, holidays, member: str | None = None)` にし、ループを `_tasks(project, member)` にする。メンバーのループ変数が引数と衝突するので、次のようにする。

```python
    loads: dict[str, LoadStats] = {}
    for entry in project.members:
        if member is not None and entry.name != member:
            continue
        items = spans.get(entry.name, [])
        totals = [_day_peak(items, day) for day in days]
        loads[entry.name] = LoadStats(
            sum(totals) / len(totals) if totals else 0.0,
            max(totals, default=0.0),
            sum(1 for total in totals if total > 1.0 + OVERLOAD_EPSILON),
        )
    return loads
```

`summarize_workload`: 引数を `(project, period, now, holidays, member: str | None = None)` にし、ループを `_tasks(project, member)` にする。行の作り方を次にする。

```python
    shown = [name for name in names if member is None or name == member]
    rows = [WorkloadRow(name, planned[name], actual[name]) for name in shown]
    if member is None and (planned[UNASSIGNED] or actual[UNASSIGNED]):
        rows.append(WorkloadRow(UNASSIGNED, planned[UNASSIGNED], actual[UNASSIGNED]))
    return rows
```

`summarize_due`: 引数に `member: str | None = None` を足し、ループを `_tasks(project, member)` にする。

`Dashboard` に足す(`team` の次):

```python
    member: str | None = None  # 絞り込み中のメンバー。None は全員
    members: list[str] = field(default_factory=list)  # プルダウンの選択肢(プロジェクトのメンバーの順)
```

`summarize`:

```python
def summarize(
    project: Project,
    period: Period,
    now: datetime,
    holidays: dict[date, str],
    kind: PeriodKind = PeriodKind.ALL,
    member: str | None = None,
) -> Dashboard:
    return Dashboard(
        period,
        summarize_progress(project, holidays, now, member),
        summarize_loads(project, period, holidays, member),
        summarize_workload(project, period, now, holidays, member),
        summarize_due(project, period, now, holidays, member),
        summarize_team_progress(project, None if kind is PeriodKind.ALL else period, now, holidays, member),
        member,
        [m.name for m in project.members],
    )
```

`period_for`(全期間の範囲)の `_tasks(project)` は変えない(絞り込みで期間の範囲を変えない)。

- [ ] **Step 4: テストと型検査を通す**

Run: `uv run pytest test/test_dashboard.py -q && uv run ty check src/projectapp`
Expected: PASS・`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: ダッシュボードの集計をメンバーで絞れるようにする(要望43)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: メンバー別の進捗(内訳)

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: Task 1 の `_tasks`・`summarize_progress(..., member)`、既存の `_progress_weight`・`UNASSIGNED`。
- Produces:
  - `@dataclass(frozen=True) class MemberProgress: name: str; percent: float | None; counts: dict[Status, int]`(`counts` を持つので frozen の `dict` 比較は等値のみ)
  - `Progress.by_member: list[MemberProgress]`(既定は空。`member` なしのときだけ `summarize_progress` が作る)
  - `summarize_member_progress(project: Project) -> list[MemberProgress]`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の import に `MemberProgress`・`summarize_member_progress` を足し、末尾に足す。

```python
def test_member_progress_has_a_row_per_member_and_counts_shared_tasks_for_each() -> None:
    rows = summarize_member_progress(shared_project())
    assert [row.name for row in rows] == ["田中", "佐藤", UNASSIGNED]
    tanaka, sato, nobody = rows
    assert tanaka.percent == pytest.approx(100 / 8)
    assert tanaka.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 0}
    assert sato.percent == pytest.approx(40)  # 共同(6h × 0%)と佐藤の(4h × 100%)
    assert sato.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 0, Status.PAUSED: 0, Status.DONE: 1}
    assert nobody.percent == pytest.approx(0)  # 担当なしと、メンバーでない担当者だけのタスク
    assert nobody.counts[Status.NOT_STARTED] == 2


def test_member_progress_marks_a_member_without_tasks_and_skips_an_empty_unassigned_row() -> None:
    project = project_of(
        Task("田中の", effort_hours=1, assignees=[Assignee("田中", 1.0)]),
        members=[Member("田中", 1.0), Member("山田", 1.0)],
    )
    rows = summarize_member_progress(project)
    assert [row.name for row in rows] == ["田中", "山田"]  # 未割り当ては、該当するタスクがあるときだけ
    assert rows[1].percent is None and sum(rows[1].counts.values()) == 0


def test_member_progress_ignores_summaries_and_does_not_depend_on_the_period() -> None:
    child = Task("子", effort_hours=4, status=Status.DONE, assignees=[Assignee("田中", 1.0)])
    summary = Task("まとめ", kind=TaskKind.SUMMARY, children=[child.id], assignees=[Assignee("田中", 1.0)])
    rows = summarize_member_progress(project_of(summary, child))
    assert rows[0].counts[Status.DONE] == 1 and rows[0].percent == pytest.approx(100)


def test_by_member_is_built_for_everyone_only() -> None:
    project = shared_project()
    assert [row.name for row in summarize_progress(project, {}, NOW).by_member] == ["田中", "佐藤", UNASSIGNED]
    assert summarize_progress(project, {}, NOW, "田中").by_member == []
    assert [row.name for row in summarize(project, WEEK, NOW, {}).progress.by_member][0] == "田中"
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: FAIL(`MemberProgress` を import できない)。

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard.py` の `Progress` の前に足す。

```python
@dataclass(frozen=True)
class MemberProgress:
    name: str
    percent: float | None  # 工数で重みづけした進捗率(0〜100)。担当のタスクがなければ None
    counts: dict[Status, int]
```

`Progress` の末尾にフィールドを足す。

```python
    by_member: list[MemberProgress] = field(default_factory=list)  # メンバーごと。絞り込み中は空
```

`summarize_progress` の前に関数を足す(`UNASSIGNED` はモジュール内で後に定義されるが、呼び出し時に解決される)。

```python
def _member_row(name: str, tasks: list[Task]) -> MemberProgress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    for task in tasks:
        counts[task.status] += 1
        if (weight_and_percent := _progress_weight(task)) is not None:  # 節目は重みに入れない
            weight, percent = weight_and_percent
            weighted += weight * percent
            total += weight
    return MemberProgress(name, weighted / total if total else None, counts)


def summarize_member_progress(project: Project) -> list[MemberProgress]:
    """メンバーごとの進捗。共同タスクは担当の全員の行に数える。メンバーが担当にいないタスクは`未割り当て`。"""
    tasks = _tasks(project)
    names = {member.name for member in project.members}
    rows = [_member_row(member.name, [t for t in tasks if member.name in t.assignee_names]) for member in project.members]
    nobody = [t for t in tasks if not names.intersection(t.assignee_names)]
    if nobody:
        rows.append(_member_row(UNASSIGNED, nobody))
    return rows
```

`summarize_progress` の `return` を直す。

```python
    overdue.sort(key=lambda row: row.limit)
    by_member = summarize_member_progress(project) if member is None else []
    return Progress(weighted / total if total else None, counts, overdue, by_member)
```

- [ ] **Step 4: テストと型検査を通す**

Run: `uv run pytest test/test_dashboard.py -q && uv run ty check src/projectapp`
Expected: PASS・`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: ダッシュボードにメンバー別の進捗の集計を足す(要望43)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面(プルダウン・メンバー別の行・円グラフの対象)

**Files:**
- Modify: `src/projectapp/dashboard_view.py`
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: Task 1・2 の `Dashboard.member`・`Dashboard.members`・`Progress.by_member`・`MemberProgress`。
- Produces:
  - `ALL_MEMBERS = ""`(プルダウンの `全員` の値)
  - `DashboardView(on_back, on_change, on_member_change: Callable[[str | None], object] | None = None)`
  - マーカー: `dashboard-member`(プルダウン)・`dashboard-member-progress-<名前>`(メンバー別の行の文言)・`dashboard-member-icon-<名前>`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` を直す。import に `MemberProgress` を足す。`sample()` の `Progress(...)` に `by_member` を足し、`Dashboard(...)` の末尾に `members` を足す。

```python
        Progress(
            42.4,
            {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 3},
            [OverdueRow("遅れた作業", "田中", datetime(2026, 10, 6, 17))],
            [
                MemberProgress("田中", 40.0, {Status.NOT_STARTED: 1, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 0}),
                MemberProgress("佐藤", None, {status: 0 for status in Status}),
            ],
        ),
```

`sample()` の `Dashboard(` の最後の引数(`TeamProgress(...)` の後)に `member=None, members=["田中", "佐藤"]` を足す(`TeamProgress(...)` の閉じ括弧の後に `None, ["田中", "佐藤"],`)。

`mount()` を、メンバー変更の記録を任意で受けるように直す(戻り値は変えない)。

```python
def mount(member_changes: list[str | None] | None = None) -> tuple[list[DashboardView], list[int], list[PeriodKind]]:
    views: list[DashboardView] = []
    backs: list[int] = []
    changes: list[PeriodKind] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(
            lambda: backs.append(1),
            changes.append,
            member_changes.append if member_changes is not None else None,
        )
        views.append(view)
        view.build()

    return views, backs, changes
```

末尾にテストを足す。

```python
async def test_the_member_select_lists_everyone_and_the_members_and_reports_changes(user: User) -> None:
    picked: list[str | None] = []
    views, _, _ = mount(picked)
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member")
    select = user.find(marker="dashboard-member").elements.pop()
    assert select.options == {"": "全員", "田中": "田中", "佐藤": "佐藤"}
    assert select.value == ""
    assert picked == []  # 表示を合わせるだけでは通知しない
    select.set_value("田中")
    assert picked == ["田中"]
    select.set_value("")
    assert picked == ["田中", None]


async def test_the_member_select_follows_the_dashboard_data(user: User) -> None:
    views, _, _ = mount([])
    await user.open("/")
    data = sample()
    data.member = "佐藤"
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member")
    assert user.find(marker="dashboard-member").elements.pop().value == "佐藤"


async def test_the_progress_card_lists_progress_per_member(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-progress-田中")
    assert text(user, "dashboard-member-progress-田中") == "40% / 3件"
    assert text(user, "dashboard-member-progress-佐藤") == "タスクなし"


async def test_the_member_rows_are_not_shown_while_filtering(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.member = "田中"
    data.progress.by_member = []
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    await user.should_not_see(marker="dashboard-member-progress-田中")


async def test_the_team_card_scope_starts_with_the_member(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.member = "田中"
    views[0].show(data, PeriodKind.ALL)
    await user.should_see("田中・すべてのタスク")


async def test_without_members_the_select_has_only_everyone_and_no_member_section(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.members, data.progress.by_member = [], []
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    assert user.find(marker="dashboard-member").elements.pop().options == {"": "全員"}
    await user.should_not_see("メンバー別")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -q`
Expected: FAIL(`dashboard-member` がない・`DashboardView` が 3 引数を受けない)。

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_view.py` を直す。import に `MemberProgress` を足す(`from projectapp.dashboard import Dashboard, MemberProgress, PeriodKind, TeamProgress` の形)。定数を足す。

```python
ALL_MEMBERS = ""  # プルダウンの`全員`の値
```

`__init__`:

```python
    def __init__(
        self,
        on_back: Callable[[], object],
        on_change: Callable[[PeriodKind], object],
        on_member_change: Callable[[str | None], object] | None = None,
    ) -> None:
        self.on_back, self.on_change, self.on_member_change = on_back, on_change, on_member_change
        self.box: ui.column | None = None
        self.toggle: ui.toggle | None = None
        self.member_select: ui.select | None = None
```

(`self.data`・`self.icons`・`self.syncing` の行は残す。)

`build` の期間のトグルの直後に足す。

```python
                self.member_select = (
                    ui.select({ALL_MEMBERS: "全員"}, value=ALL_MEMBERS, on_change=self.on_member)
                    .props("dense outlined options-dense")
                    .style("min-width: 8rem")
                    .mark("dashboard-member")
                )
```

`on_toggle` の次に足す。

```python
    def on_member(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and self.on_member_change is not None:
            self.on_member_change(event.value or None)
```

`show` の、トグルを合わせるブロックの直後(`if self.box is not None:` の前)に足す。

```python
        if self.member_select is not None:
            options = {ALL_MEMBERS: "全員", **{name: name for name in data.members}}
            self.syncing = True
            try:
                self.member_select.set_options(options, value=data.member or ALL_MEMBERS)
            finally:
                self.syncing = False
```

`progress_card` の、状態別の件数の行(`with ui.row().classes("gap-4"):` のブロック)の直後、`ui.label("予定超過")` の前に足す。

```python
            if progress.by_member:
                ui.label("メンバー別").classes("text-subtitle2")
                for row in progress.by_member:
                    self.member_progress_row(row)
```

`progress_card` の次にメソッドを足す。

```python
    def member_progress_row(self, row: MemberProgress) -> None:
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("items-center no-wrap gap-2"):
                if icon := self.icons.get(row.name):
                    avatar(row.name, icon, 20).mark(f"dashboard-member-icon-{row.name}")
                ui.label(row.name)
            if row.percent is None:
                ui.label("タスクなし").classes("text-caption text-grey").mark(f"dashboard-member-progress-{row.name}")
                return
            ui.label(f"{row.percent:.0f}% / {sum(row.counts.values())}件").classes("text-caption").mark(
                f"dashboard-member-progress-{row.name}"
            )
            bar(row.percent / 100, LOAD_COLOR)
```

`team_card` の対象の表示を直す。

```python
            scope = "すべてのタスク" if period is None else f"{period.start:%m/%d}〜{period.end:%m/%d} にかかるタスク"
            if data.member:
                scope = f"{data.member}・{scope}"
```

- [ ] **Step 4: テストと型検査を通す**

Run: `uv run pytest test/test_dashboard_view.py test/test_dashboard.py -q && uv run ty check src/projectapp`
Expected: PASS・`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: ダッシュボードにメンバーのプルダウンとメンバー別の進捗を出す(要望43)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 状態の持ち方と、記録

**Files:**
- Modify: `src/projectapp/views.py`(`__init__`:約 202 行・`open_dashboard`・`refresh_dashboard`・`change_dashboard_period` の次・`DashboardView` の生成:約 255 行)
- Modify: `CLAUDE.md`(ダッシュボードの節)、`docs/requests.md`、`docs/request-history.md`、`docs/superpowers/README.md`、`.claude/MEMORY.md`、設計書の先頭の状態
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 1〜3 の `summarize(..., member=)`・`DashboardView(..., on_member_change)`。
- Produces: `MainView.dashboard_member: str | None`・`MainView.change_dashboard_member(name: str | None) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `test_changing_the_period_redraws_with_the_new_period` の次に足す(`open_dashboard_view`・`Member`・`Assignee`・`Task` は既存)。

```python
async def test_the_member_filter_narrows_the_dashboard_and_resets_when_reopened(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-member")
    user.find(marker="dashboard-member").elements.pop().set_value("田中")
    assert view.dashboard_member == "田中"
    await user.should_see("田中・10/05〜10/11 にかかるタスク")
    user.find(marker="dashboard-back").click()
    user.find(marker="open-dashboard").click()
    assert view.dashboard_member is None


async def test_the_member_filter_stays_when_the_period_changes(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-member")
    user.find(marker="dashboard-member").elements.pop().set_value("田中")
    user.find(marker="dashboard-period").elements.pop().set_value("今月")
    assert view.dashboard_member == "田中" and view.dashboard_kind == PeriodKind.MONTH


async def test_a_removed_member_falls_back_to_everyone(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-member")
    view.change_dashboard_member("消えた人")
    assert view.dashboard_member is None
    view.change_dashboard_member("田中")
    view.project.members = [Member("佐藤", 1.0)]
    view.refresh_dashboard()
    assert view.dashboard_member is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k "member_filter or removed_member"`
Expected: FAIL(`dashboard_member` がない)。

- [ ] **Step 3: 実装する**

`src/projectapp/views.py`:

`__init__` の `self.dashboard_kind ...` の次の行に足す。

```python
        self.dashboard_member: str | None = None  # ダッシュボードで絞り込み中のメンバー。保存しない
```

`open_dashboard`: `self.dashboard_kind = PeriodKind.WEEK` の次に `self.dashboard_member = None` を足す。

`refresh_dashboard`:

```python
    def refresh_dashboard(self) -> None:
        if self.dashboard_kind is None:
            return
        if self.dashboard_member not in {m.name for m in self.project.members}:
            self.dashboard_member = None  # 削除・改名されたメンバーは、全員に戻す
        now = self.now()
        period = period_for(self.dashboard_kind, now.date(), self.project, self.holidays)
        icons = {m.name: m.icon for m in self.project.members if m.icon}
        data = summarize(self.project, period, now, self.holidays, self.dashboard_kind, self.dashboard_member)
        self.dashboard_view.show(data, self.dashboard_kind, icons)
```

`change_dashboard_period` の次に足す。

```python
    def change_dashboard_member(self, name: str | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_member = name
        self.refresh_dashboard()
```

注意: `None not in {...}` は真になるので、`全員`(None)でも代入は `None` のままで害はない。

`DashboardView` の生成を直す。

```python
        self.dashboard_view = DashboardView(
            self.close_dashboard, self.change_dashboard_period, self.change_dashboard_member
        )
```

- [ ] **Step 4: 全テストと型検査を通す**

Run(終了コードを見る):

```bash
uv run pytest -q > /tmp/claude-501/full.txt 2>&1; code=$?; tail -2 /tmp/claude-501/full.txt; echo "exit=$code"; uv run ty check src/projectapp | tail -1
```

Expected: `exit=0`・`All checks passed!`

- [ ] **Step 5: 仕様と記録を更新する**

- `CLAUDE.md` のダッシュボードの節(`チーム全体の進捗`の項目の次)に追記する。

  `- 期間の横のプルダウンで、`全員`かメンバー 1 人を選べる。選ぶと、全カードがそのメンバーが担当に入っているタスクだけになる(共同タスクは 1 件として丸ごと数える。担当なしと、担当がメンバーでないタスクは入らない)。負荷と工数は、そのメンバーの行だけになる。日程の計算は絞り込まない。`全員`のときは、`進捗と遅れ`に`メンバー別`の行(アイコン・名前・進捗率・件数。担当がメンバーでないタスクは`未割り当て`)を出す(期間には影響されない)。絞り込みは保存せず、開き直すと`全員`に戻る`

- `docs/requests.md`: 要望 41〜46 の見出しの「41・42 は実装済み」を「41〜43 は実装済み」に直し、「ダッシュボードを、メンバー 1 人に絞って…」の行に実装済みの注記を足す。
- `docs/request-history.md`: 要望 42 の行の次に要望 43 の行を足す(設計・計画へのリンクつき、状態は「実装済み・実機確認待ち」)。
- `docs/superpowers/README.md`: 表の末尾に `2026-10-18 | ダッシュボードのメンバー絞り込みと内訳 | 設計 | 計画 | 要望 43 | PR 待ち | —` の行を足す。
- 設計書の先頭の状態を `実装済み・実機確認待ち — 要望 43 — feature/dashboard-member-filter(PR 待ち)` に直す。
- `.claude/MEMORY.md`: 要望 43 の項目を実装済みにし、「現在の状況」のブランチを `feature/dashboard-member-filter` に直す。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: ダッシュボードのメンバー絞り込みの状態を持ち、記録を更新する(要望43)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage**: 絞り込みの単位・対象のタスク(Task 1)/共同タスク(Task 1)/工数の按分と行の絞り込み(Task 1)/プルダウンと全カードへの効き(Task 1・3・4)/保存しない・開き直しで全員(Task 4)/ファイル形式不変(変更なし)/メンバー別の内訳と `未割り当て`(Task 2・3)/対象の表示(Task 3)/メンバー削除での全員への復帰(Task 4)/テスト(各 Task)。
- **Placeholders**: なし。
- **Type consistency**: `member: str | None` を全 `summarize_*` で統一。`DashboardView` の第 3 引数は `Callable[[str | None], object] | None`、`MainView.change_dashboard_member(name: str | None)` と一致。`Dashboard.members`・`Dashboard.member` は Task 1 で定義し Task 3 で使う。`MemberProgress` は Task 2 で定義し Task 3 で使う。
