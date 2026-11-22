# アサイン専用画面 段階 2(割り当て操作)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面に、チームごとのメンバー一覧と、ガントチャートの「割り当ての行」(週・日のセル)を足し、メンバーをドラッグアンドドロップで週(日)に割り当てられるようにする。

**Architecture:** 担当の操作は`daily_crew.py`の純粋関数(`add_member`・`remove_member`)。`GanttChart`に、埋め込みモードで各タスク行の直後に呼ぶ拡張点`task_extra`を足し、`AssignScreen`がそこへ割り当ての行(週・日のセル)を描く。ドラッグは`dashboard_drag.py`と同じ作り(document に委譲した HTML5 drag、種類は`application/x-assign-member`)。結果は試算のタスク(`weekly_crew`・`daily_crew`)に入れ、チャートを描き直す。確定までメインは変えない。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-22-assign-screen-stage2-design.md`(段階 1 は`docs/superpowers/specs/2026-11-22-assign-screen-stage1-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。試算は保存しない
- 持ち方は`Task.weekly_crew`(実効の開始日から 7 日ごと)と`Task.daily_crew`(日ごとの週)。割り当て率は 100% 固定。上限は`MAX_WEEKS`(52)
- 担当のいない週・日は作らない(`set_week_days`と同じ規則)。そのセルの最後の 1 人は外せない
- ドラッグできるのは一覧からセルへだけ(セル間の移動はない)。`dataTransfer`の種類は`application/x-assign-member`で、ガントチャート・ダッシュボードの drag と取り違えない
- 埋め込みのチャートのスクロール枠は`data-assign-scroll`(段階 1 のとおり)。割り当ての行のマーカーは`assign-`で始める
- メインのチャートの描画は変えない(`task_extra`は`None`のまま)
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは git-flow。`develop`から`feature/request-168-stage2`を切る(設計書の PR #270 が未マージなら、`docs/request-168-stage2-design`から切る)。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差)

- `add_member`には、設計書の引数に加えて、キーワード引数`weeks: int = 1`(週ごとにするときの週の数)を足す。純粋関数は日付を知らないので、週の数は呼び出し側(画面が`week_count`で出す)が渡す
- 「開始日がなく週に分けられない」の判定は、純粋関数ではなく画面が行う(開始日がなければセルを出さない)
- **担当者のいないタスク**には、「今の担当」がないので、最初のドロップは、週ごとに分けずタスク全体の担当(`assignees`)にする。2 回目以降は週ごと(`toggle_weeks`が「担当者のいないタスクは週ごとに分けられません」としているのと同じ理由。担当のいない週を作らない)

## Review Focus

- 担当者のいないタスクへ最初に落としたとき: 全体の担当になり、担当のいない週ができない
- 同じメンバーを同じセルへ落としたとき: 重複せず通知する。日ごとの週で、日を指定しない落としは 7 日すべてに足す
- 先の週(定義済みの週より後)へ落としたとき: 間が直前の担当のコピーで埋まる。52 週を超える週は拒否する
- 最後の 1 人の`×`: 外れず通知する。日ごとの週で一部の日だけ最後の 1 人のとき、`day`なしの外しは何も変えない
- 開始日のないタスク: セルを出さず通知文を出し、メンバー一覧は出す。メインのチャートの描画が変わらない

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/daily_crew.py`(変更) | `add_member`・`remove_member`を足す |
| `src/projectapp/assign_trial.py`(変更) | `TeamGroup`・`team_groups`・`cell_plan`(セルの原点の日と週の数)を足す |
| `src/projectapp/gantt.py`(変更) | `GanttChart.task_extra`を足し、`render`のルートのタスク行の直後で呼ぶ |
| `src/projectapp/assign_drag.py`(新規) | ドラッグの JS・CSS(定数だけ) |
| `src/projectapp/assign_screen.py`(変更) | メンバー一覧・割り当ての行・ドロップの処理 |
| `test/test_daily_crew_assign.py`(新規) | 純粋関数のテスト |
| `test/test_assign_trial.py`・`test/test_assign_screen.py`・`test/test_gantt.py`(変更) | 補助関数・画面・拡張点のテスト |
| `.claude/spec/dashboard.md`・`docs/development.md`・`docs/requests.md`(変更) | 仕様・構成・状態表記 |

---

### Task 1: 担当の操作(`add_member`・`remove_member`)

**Files:**
- Modify: `src/projectapp/daily_crew.py`(末尾に足す)
- Test: `test/test_daily_crew_assign.py`(新規)

**Interfaces:**
- Consumes: 既存の`copy_crew`・`copy_weekly`・`copy_daily`・`_is_daily`・`_tail`・`WEEK_DAYS`・`MAX_WEEKS`・`union_assignees`
- Produces:
  - `add_member(task: Task, name: str, week: int, day: int | None = None, *, weeks: int = 1) -> Task | None`
  - `remove_member(task: Task, name: str, week: int, day: int | None = None) -> Task | None`

- [ ] **Step 1: テストを書く**

`test/test_daily_crew_assign.py`:

```python
from projectapp.daily_crew import add_member, remove_member, split_week
from projectapp.models import Assignee, Task


def task(*names: str) -> Task:
    return Task("t", id="a", assignees=[Assignee(n) for n in names])


def names(crew: list[Assignee]) -> list[str]:
    return [a.name for a in crew]


def test_adding_to_a_plain_task_splits_it_into_weeks_and_adds_only_to_that_week() -> None:
    result = add_member(task("田中"), "鈴木", 2, weeks=4)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中"],
        ["田中"],
        ["田中", "鈴木"],
        ["田中"],
    ]
    assert names(result.assignees) == ["田中", "鈴木"]  # 和集合


def test_adding_to_a_task_without_assignees_makes_the_whole_task_assigned() -> None:
    result = add_member(task(), "鈴木", 1, weeks=3)
    assert result is not None
    assert result.weekly_crew == [] and names(result.assignees) == ["鈴木"]


def test_the_second_drop_on_an_unassigned_task_is_per_week() -> None:
    first = add_member(task(), "鈴木", 0, weeks=3)
    assert first is not None
    second = add_member(first, "田中", 1, weeks=3)
    assert second is not None
    assert [names(w) for w in second.weekly_crew] == [["鈴木"], ["鈴木", "田中"], ["鈴木"]]


def test_a_week_beyond_the_defined_ones_is_filled_with_the_last_crew() -> None:
    weekly = add_member(task("田中"), "鈴木", 0, weeks=2)
    assert weekly is not None
    result = add_member(weekly, "佐藤", 4)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中", "鈴木"],
        ["田中"],
        ["田中"],
        ["田中"],
        ["田中", "佐藤"],
    ]


def test_adding_a_duplicate_or_beyond_the_limit_is_rejected() -> None:
    assert add_member(task("田中"), "田中", 0, weeks=2) is None
    assert add_member(task("田中"), "鈴木", 52, weeks=2) is None
    assert add_member(task("田中"), "鈴木", -1, weeks=2) is None


def test_adding_to_a_daily_week_targets_one_day_or_all_days() -> None:
    weekly = add_member(task("田中"), "鈴木", 5, weeks=1)  # 6 週にする
    assert weekly is not None
    daily = split_week(weekly, 1)
    assert daily is not None
    one = add_member(daily, "佐藤", 1, 3)
    assert one is not None
    assert [names(d) for d in one.daily_crew[1]] == [
        ["田中"], ["田中"], ["田中"], ["田中", "佐藤"], ["田中"], ["田中"], ["田中"],
    ]
    every = add_member(daily, "佐藤", 1)
    assert every is not None
    assert all(names(d) == ["田中", "佐藤"] for d in every.daily_crew[1])
    assert names(every.weekly_crew[1]) == ["田中", "佐藤"]  # 週の担当は 7 日の和集合


def test_removing_a_member_from_a_week() -> None:
    added = add_member(task("田中"), "鈴木", 1, weeks=3)
    assert added is not None
    result = remove_member(added, "鈴木", 1)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [["田中"], ["田中"], ["田中"]]


def test_the_last_member_of_a_cell_cannot_be_removed() -> None:
    added = add_member(task("田中"), "鈴木", 1, weeks=3)
    assert added is not None
    assert remove_member(added, "田中", 0) is None  # 週 0 の最後の 1 人
    assert remove_member(task("田中"), "田中", 0) is None  # 週ごとでないタスク
    assert remove_member(added, "佐藤", 1) is None  # いない人


def test_removing_from_all_days_changes_nothing_when_one_day_would_be_empty() -> None:
    weekly = add_member(task("田中"), "鈴木", 1, weeks=2)
    assert weekly is not None
    daily = split_week(weekly, 1)
    assert daily is not None
    one_day = add_member(daily, "佐藤", 1, 2)  # 3 日目だけ佐藤を足す(田中・鈴木・佐藤)
    assert one_day is not None
    # 田中と鈴木は 7 日すべてにいる。どの日も 2 人以上なので、鈴木を全日から外せる
    result = remove_member(one_day, "鈴木", 1)
    assert result is not None and all("鈴木" not in names(d) for d in result.daily_crew[1])
    only = remove_member(result, "田中", 1)  # 3 日目は田中・佐藤だが、ほかの日は田中だけなので外せない
    assert only is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_daily_crew_assign.py -v`
Expected: FAIL(`ImportError: cannot import name 'add_member'`)

- [ ] **Step 3: 実装する**

`daily_crew.py`の末尾に足す(`MAX_WEEKS`・`union_assignees`は既に import 済み。なければ足す):

```python
def _crews(task: Task, weeks: int) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週ごとの担当を返す。週ごとでないタスクは、現在の担当を`weeks`週ぶんに写す。担当者がなければ None。"""
    if task.weekly_crew:
        return copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    if not task.assignees:
        return None
    return [copy_crew(task.assignees) for _ in range(max(weeks, 1))], {}


def add_member(
    task: Task, name: str, week: int, day: int | None = None, *, weeks: int = 1
) -> Task | None:
    """アサイン専用画面(要望 168 段階 2): メンバーを週(日)のセルに、割り当て率 100% で足す。

    週ごとでないタスクは、現在の担当を`weeks`週ぶんに写して週ごとにし、落とした週だけに足す。担当者のいないタスクは
    週ごとにできない(担当のいない週を作らない)ので、全体の担当にする。定義済みの週より先は、直前の担当で間を埋める。
    重複・範囲外(`week`が 0 未満か`MAX_WEEKS`以上、`day`が日ごとの週の 0〜6 の外)は None(何も変えない)。
    """
    if not 0 <= week < MAX_WEEKS or not task.kind is TaskKind.NORMAL:
        return None
    if not task.weekly_crew and not task.assignees:
        return replace(task, assignees=[Assignee(name)])
    crews = _crews(task, min(weeks, MAX_WEEKS))
    assert crews is not None
    weekly, daily = crews
    while len(weekly) <= week:
        weekly.append(copy_crew(_tail(weekly, daily)))
    if _is_daily(daily, week):
        targets = range(WEEK_DAYS) if day is None else [day]
        if any(not 0 <= j < WEEK_DAYS for j in targets):
            return None
        if all(name in {a.name for a in daily[week][j]} for j in targets):
            return None
        for j in targets:
            if name not in {a.name for a in daily[week][j]}:
                daily[week][j].append(Assignee(name))
        weekly[week] = union_assignees(daily[week])
    else:
        if day is not None or name in {a.name for a in weekly[week]}:
            return None
        weekly[week].append(Assignee(name))
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def remove_member(
    task: Task, name: str, week: int, day: int | None = None
) -> Task | None:
    """アサイン専用画面: メンバーを週(日)のセルから外す。そのセルの最後の 1 人・いない人・週ごとでないタスクは None。
    日ごとの週で`day`がなければ 7 日すべてから外す(どれかの日で最後の 1 人なら None)。"""
    if not task.weekly_crew or not 0 <= week < len(task.weekly_crew):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    if _is_daily(daily, week):
        targets = range(WEEK_DAYS) if day is None else [day]
        if any(not 0 <= j < WEEK_DAYS for j in targets):
            return None
        for j in targets:
            crew = [a for a in daily[week][j] if a.name != name]
            if len(crew) == len(daily[week][j]) or not crew:
                return None
            daily[week][j] = crew
        weekly[week] = union_assignees(daily[week])
    else:
        crew = [a for a in weekly[week] if a.name != name]
        if day is not None or len(crew) == len(weekly[week]) or not crew:
            return None
        weekly[week] = crew
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )
```

(`TaskKind`は`models`から import する。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_daily_crew_assign.py test/test_daily_crew.py -v`
Expected: PASS。最後のテストのコメントは、実行して読んだ結果に合わせて直す(ロジックの期待値は変えない)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/daily_crew.py test/test_daily_crew_assign.py
git commit -m "feat: 週(日)のセルへメンバーを足す・外す純粋関数(要望 168 段階 2)"
```

---

### Task 2: 補助関数(`team_groups`・`cell_plan`)

**Files:**
- Modify: `src/projectapp/assign_trial.py`
- Test: `test/test_assign_trial.py`

**Interfaces:**
- Consumes: `Project`・`Member`・`Team`・`Membership`、`timeline.effective_start`・`effective_end`・`week_count`・`Schedule`、`models.MAX_WEEKS`
- Produces:
  - `TeamGroup(name: str, members: list[Member])`(dataclass)
  - `team_groups(project: Project) -> list[TeamGroup]`: チームの並び順に、所属するメンバー(複数チームの人は各チームに出す)。どのチームにも入っていない人は最後の`チームなし`(`NO_TEAM = "チームなし"`)。メンバーがいなければ空
  - `CellPlan(origin: date, weeks: int)`(dataclass)
  - `cell_plan(project: Project, task: Task, holidays: dict[date, str]) -> CellPlan | None`: 実効の開始の日(週 0 の最初の日)と、週の数(元のタスクの日程が覆う週の数と`len(task.weekly_crew)`の大きいほう。最低 1・最大`MAX_WEEKS`)。開始日がなければ`None`

- [ ] **Step 1: テストを書く**

`test/test_assign_trial.py`に足す:

```python
def test_team_groups_list_teams_in_order_then_no_team() -> None:
    from projectapp.assign_trial import NO_TEAM, team_groups
    from projectapp.models import Membership, Team

    dev, ops = Team("開発", id="t1"), Team("運用", id="t2")
    members = [
        Member("田中", 1.0, teams=[Membership("t1")]),
        Member("佐藤", 1.0, teams=[Membership("t1", 50), Membership("t2", 50)]),
        Member("鈴木", 1.0),
    ]
    project = Project("p", base_date=date(2026, 11, 16), members=members, teams=[dev, ops])
    groups = team_groups(project)
    assert [(g.name, [m.name for m in g.members]) for g in groups] == [
        ("開発", ["田中", "佐藤"]),
        ("運用", ["佐藤"]),
        (NO_TEAM, ["鈴木"]),
    ]


def test_team_groups_skip_empty_teams_and_handle_no_members() -> None:
    from projectapp.assign_trial import team_groups
    from projectapp.models import Team

    assert team_groups(Project("p", base_date=date(2026, 11, 16))) == []
    empty = Project("p", base_date=date(2026, 11, 16), teams=[Team("空", id="t1")])
    assert team_groups(empty) == []


def test_cell_plan_covers_the_task_span_and_the_defined_weeks() -> None:
    from projectapp.assign_trial import cell_plan

    task = Task(
        "t",
        id="a",
        planned_start=datetime(2026, 11, 16, 9),
        planned_end=datetime(2026, 11, 30, 17),
        effort_hours=40,
    )
    project = Project("p", base_date=date(2026, 11, 16), tasks=[task])
    plan = cell_plan(project, task, {})
    assert plan is not None
    assert plan.origin == date(2026, 11, 16) and plan.weeks >= 2
    no_start = Task("n", id="b")
    assert cell_plan(Project("p", base_date=date(2026, 11, 16), tasks=[no_start]), no_start, {}) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assign_trial.py -v`
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 実装する**

`assign_trial.py`に足す(import を整える):

```python
from datetime import date

from projectapp.models import MAX_WEEKS, Member, Project, Status, Task, TaskKind
from projectapp.timeline import Schedule, effective_end, effective_start, week_count

NO_TEAM = "チームなし"


@dataclass
class TeamGroup:
    name: str
    members: list[Member]


def team_groups(project: Project) -> list[TeamGroup]:
    """メンバー一覧用: チームの並び順に、所属するメンバー(複数チームの人は各チームに出す)。
    どのチームにも入っていない人は最後に`チームなし`。メンバーのいないチームは出さない。"""
    groups: list[TeamGroup] = []
    for team in project.teams:
        members = [
            m for m in project.members if any(s.team_id == team.id for s in m.teams)
        ]
        if members:
            groups.append(TeamGroup(team.name, members))
    free = [m for m in project.members if not m.teams]
    if free:
        groups.append(TeamGroup(NO_TEAM, free))
    return groups


@dataclass(frozen=True)
class CellPlan:
    origin: date  # 週 0 の最初の日(実効の開始の日)
    weeks: int  # セルの週の数


def cell_plan(
    project: Project, task: Task, holidays: dict[date, str]
) -> CellPlan | None:
    """割り当ての行のセルの原点と週の数。開始日がなければ None(週に分けられない)。"""
    schedule = Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    end = effective_end(task, project, holidays, schedule)
    span = week_count(start, end) if end is not None and end > start else 1
    weeks = min(max(span, len(task.weekly_crew), 1), MAX_WEEKS)
    return CellPlan(start.date(), weeks)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assign_trial.py -v`
Expected: PASS(`Membership`の引数、`Team`の`id`の渡し方は`models.py`の定義に合わせる)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/assign_trial.py test/test_assign_trial.py
git commit -m "feat: メンバー一覧のチーム分けと、割り当ての行のセルの計画(要望 168 段階 2)"
```

---

### Task 3: `GanttChart.task_extra`(拡張点)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttChart.__init__`の属性・`render`のルートのタスク行のループ)
- Test: `test/test_gantt.py`

**Interfaces:**
- Produces: `GanttChart.task_extra: Callable[[Task, list[Column], int], object] | None = None`。`render`のルートのタスク行(`self.task_row((), ti, task, columns, width)`)を作った直後、折りたたまれていなければ、`task_extra(task, columns, width)`を呼ぶ(`width`は 1 列の px)。呼び出しはチャートの内側(`chart-content`の中)の文脈で行われる

- [ ] **Step 1: テストを書く**

`test/test_gantt.py`に足す(`Recorder`・`sample_project`の使い方は既存のテストに合わせる):

```python
async def test_task_extra_is_called_after_each_root_task_row_with_columns_and_width(
    user: User,
) -> None:
    calls: list[tuple[str, int, int]] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions)

        def extra(task: Task, columns: list[Column], width: int) -> None:
            calls.append((task.id, len(columns), width))
            ui.label("extra").mark(f"extra-{task.id}")

        chart.task_extra = extra
        chart.build()

    await user.open("/")
    root_ids = [t.id for t in sample_project().tasks]
    assert [c[0] for c in calls][: len(root_ids)] == root_ids
    assert all(c[1] > 0 and c[2] > 0 for c in calls)


async def test_the_chart_draws_the_same_without_task_extra(user: User) -> None:
    mount_chart(sample_project())
    await user.open("/")
    await user.should_not_see(marker="extra-anything")  # 既定は None で、何も足さない
```

(`Task`・`Column`・`ui`・`GanttChart`は`test_gantt.py`で既に import 済みか確かめ、なければ足す。ルートにタスクがある`sample_project()`でなければ、`menu_project()`(`test_context_menu.py`)のようにルートのタスクを持つプロジェクトを使う。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py -v -k task_extra`
Expected: FAIL(`task_extra`を呼ぶと`calls`が空)

- [ ] **Step 3: 実装する**

`GanttChart.__init__`の属性に足す:

```python
        self.task_extra: Callable[[Task, list[Column], int], object] | None = (
            None  # 各ルートのタスク行の直後に呼ぶ(アサイン専用画面の割り当ての行。要望 168)
        )
```

`render`のルートのタスクのループを変える(`task_row`の直後):

```python
            for ti, task in enumerate(self.project.tasks):
                if matches(task, self.task_filter, self.tasks_by_id):
                    self.task_row((), ti, task, columns, width).set_visibility(
                        task.id not in folded
                    )
                    if self.task_extra is not None and task.id not in folded:
                        self.task_extra(task, columns, width)
                    self.quick_add_here((), ti + 1)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gantt.py test/test_context_menu.py test/test_bottom_split.py test/test_assign_screen.py -q`
Expected: PASS(メインの描画が変わっていない確認を含む)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: GanttChart に、タスク行の直後に呼ぶ拡張点 task_extra を足す(要望 168 段階 2)"
```

---

### Task 4: ドラッグの JS・CSS(`assign_drag.py`)

**Files:**
- Create: `src/projectapp/assign_drag.py`
- Test: `test/test_assign_drag.py`

**Interfaces:**
- Produces: `ASSIGN_DRAG_CSS: str`・`ASSIGN_DRAG_JS: str`・`ASSIGN_DROP_EVENT = "assign_drop_member"`。JS は、`[data-assign-member]`のチップを掴み、`[data-assign-cell]`(`data-week`・`data-day`)に落とすと`emitEvent("assign_drop_member", {name, week, day})`を送る(`day`は日ごとのセルのときだけ数値、なければ`null`)。`dataTransfer`の種類は`application/x-assign-member`

- [ ] **Step 1: テストを書く**

`test/test_assign_drag.py`:

```python
from projectapp.assign_drag import ASSIGN_DRAG_CSS, ASSIGN_DRAG_JS, ASSIGN_DROP_EVENT


def test_the_drag_js_uses_its_own_data_transfer_type_and_event() -> None:
    assert "application/x-assign-member" in ASSIGN_DRAG_JS
    assert "application/x-dashboard-card" not in ASSIGN_DRAG_JS
    assert f'emitEvent("{ASSIGN_DROP_EVENT}"' in ASSIGN_DRAG_JS
    assert "data-assign-member" in ASSIGN_DRAG_JS and "data-assign-cell" in ASSIGN_DRAG_JS


def test_the_drag_js_installs_only_once_and_ignores_foreign_drags() -> None:
    assert "__assignDragInstalled" in ASSIGN_DRAG_JS
    assert "isOurs" in ASSIGN_DRAG_JS


def test_the_css_marks_the_cell_under_the_pointer() -> None:
    assert ".assign-drop-over" in ASSIGN_DRAG_CSS
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assign_drag.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 実装する**

`src/projectapp/assign_drag.py`:

```python
"""アサイン専用画面(要望 168 段階 2)のメンバーのドラッグ用の JS と CSS(定数のみ)。

一覧のチップ(`data-assign-member`)を HTML5 の drag で掴み、割り当ての行のセル(`data-assign-cell`)に落とす。
結果(名前・週・日)だけを emitEvent で Python に返す。`dashboard_drag.py`と同じ作りで、`dataTransfer`の種類で
ほかの drag(ガントチャート・ダッシュボード)と見分ける。セルは再描画で作り直されるので、document に委譲する。
"""

ASSIGN_DROP_EVENT = "assign_drop_member"

ASSIGN_DRAG_CSS = """
[data-assign-member] { cursor: grab; }
.assign-drop-over { outline: 2px solid #1976d2; outline-offset: -2px; background: rgba(25, 118, 210, 0.12); }
"""

ASSIGN_DRAG_JS = """
(() => {
  if (window.__assignDragInstalled) return;
  window.__assignDragInstalled = true;
  const TYPE = "application/x-assign-member";
  let source = null;
  const isOurs = (event) => Array.from((event.dataTransfer || {}).types || []).includes(TYPE);
  const clearMarks = () => {
    document.querySelectorAll(".assign-drop-over").forEach((el) => el.classList.remove("assign-drop-over"));
  };
  const dropTarget = (event) =>
    event.target.closest ? event.target.closest("[data-assign-cell]") : null;

  document.addEventListener("dragstart", (event) => {
    const chip = event.target.closest ? event.target.closest("[data-assign-member]") : null;
    if (!chip) return;
    source = chip.dataset.assignMember;
    event.dataTransfer.setData(TYPE, source);
    event.dataTransfer.effectAllowed = "copy";
  });

  document.addEventListener("dragover", (event) => {
    if (!isOurs(event)) return;
    clearMarks();
    const el = dropTarget(event);
    if (!el) return;
    event.preventDefault();
    el.classList.add("assign-drop-over");
  });

  document.addEventListener("drop", (event) => {
    if (!isOurs(event) || source === null) return;
    const el = dropTarget(event);
    clearMarks();
    if (!el) { source = null; return; }
    event.preventDefault();
    const day = el.dataset.day;
    const message = {
      name: source,
      week: Number(el.dataset.week),
      day: day === undefined || day === "" ? null : Number(day),
    };
    source = null;
    emitEvent("assign_drop_member", message);
  });

  document.addEventListener("dragend", () => { clearMarks(); source = null; });
})();
"""
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assign_drag.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/assign_drag.py test/test_assign_drag.py
git commit -m "feat: アサイン専用画面のメンバーのドラッグの JS と CSS(要望 168 段階 2)"
```

---

### Task 5: 画面(メンバー一覧・割り当ての行・ドロップの処理)

**Files:**
- Modify: `src/projectapp/assign_screen.py`
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: `add_member`・`remove_member`・`split_week`・`merge_week`(Task 1)、`team_groups`・`cell_plan`・`TeamGroup`・`CellPlan`(Task 2)、`GanttChart.task_extra`(Task 3)、`ASSIGN_DRAG_CSS`・`ASSIGN_DRAG_JS`・`ASSIGN_DROP_EVENT`(Task 4)、`daily_crew.segments`・`Segment`、`avatar(name, icon, size)`、`interval_span`・`COLUMN_WIDTH_PX`・`from_name`(`gantt.py`)
- Produces(`AssignScreen`の追加):
  - `AssignScreen.drop_member(name: str, week: int, day: int | None) -> None`(ドロップの処理。`None`のときは通知する)
  - `AssignScreen.remove_member_at(name: str, week: int, day: int | None) -> None`
  - `AssignScreen.toggle_daily(week: int) -> None`(`日ごとにする`/`週に戻す`)
  - `AssignScreen.refresh() -> None`(試算のタスクから複製を作り直してチャートを描き直す)
  - 属性`plan: CellPlan | None`
  - マーカー: `assign-members`・`assign-team-<名前>`・`assign-member-<名前>`・`assign-member-assigned-<名前>`(担当者の枠)・`assign-cell-<週>`・`assign-cell-<週>-<日>`・`assign-chip-<週>-<名前>`・`assign-chip-<週>-<日>-<名前>`・`assign-remove-<週>-<名前>`・`assign-daily-<週>`・`assign-no-start`・`assign-no-members`

- [ ] **Step 1: テストを書く**

`test/test_assign_screen.py`に足す(段階 1 の`mount_screen`・`one_task_project`を使う。メンバー・チーム・担当者を持つプロジェクトを`team_project()`として足す):

```python
def team_project() -> Project:
    from projectapp.models import Assignee, Member, Membership, Team

    task = Task(
        "設計",
        id="a",
        planned_start=datetime(2026, 11, 16, 9),
        planned_end=datetime(2026, 11, 30, 17),
        effort_hours=40,
        assignees=[Assignee("田中")],
    )
    return Project(
        "p",
        base_date=date(2026, 11, 16),
        members=[
            Member("田中", 1.0, teams=[Membership("t1")]),
            Member("鈴木", 1.0, teams=[Membership("t1")]),
            Member("佐藤", 1.0),
        ],
        teams=[Team("開発", id="t1")],
        tasks=[task],
    )


def mount_team_screen(
    confirmed: list[AssignTrial], screens: list[AssignScreen]
) -> None:
    @ui.page("/")
    def index() -> None:
        main = GanttChart(team_project(), {}, noop_actions())
        main.build()
        project = team_project()
        screen = AssignScreen(project, project.tasks[0], {}, on_confirm=confirmed.append)
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")


async def open_team_screen(user: User) -> tuple[AssignScreen, list[AssignTrial]]:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_team_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-members")
    return screens[0], confirmed


async def test_member_list_shows_teams_and_marks_the_tasks_assignees(user: User) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_see(marker="assign-team-開発")
    await user.should_see(marker="assign-team-チームなし")
    for name in ("田中", "鈴木", "佐藤"):
        await user.should_see(marker=f"assign-member-{name}")
    await user.should_see(marker="assign-member-assigned-田中")
    await user.should_not_see(marker="assign-member-assigned-鈴木")


async def test_dropping_a_member_on_a_week_cell_adds_only_that_week(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    crews = [[a.name for a in w] for w in screen.trial.task.weekly_crew]
    assert crews[1] == ["田中", "鈴木"] and crews[0] == ["田中"]
    await user.should_see(marker="assign-chip-1-鈴木")
    await user.should_not_see(marker="assign-chip-0-鈴木")


async def test_dropping_a_duplicate_is_rejected_with_a_notice(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    before = [list(w) for w in screen.trial.task.weekly_crew]
    screen.drop_member("鈴木", 1, None)
    assert screen.trial.task.weekly_crew == before
    await user.should_see("すでに割り当てています")


async def test_the_remove_button_removes_but_not_the_last_member(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.remove_member_at("鈴木", 1, None)
    assert [a.name for a in screen.trial.task.weekly_crew[1]] == ["田中"]
    screen.remove_member_at("田中", 1, None)  # 最後の 1 人
    assert [a.name for a in screen.trial.task.weekly_crew[1]] == ["田中"]
    await user.should_see("最後の 1 人は外せません")


async def test_a_week_can_be_split_into_days_and_back(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.toggle_daily(0)
    assert 0 in screen.trial.task.daily_crew
    await user.should_see(marker="assign-cell-0-3")
    screen.drop_member("佐藤", 0, 3)
    assert [a.name for a in screen.trial.task.daily_crew[0][3]] == ["田中", "鈴木", "佐藤"]
    screen.toggle_daily(0)
    assert 0 not in screen.trial.task.daily_crew


async def test_a_task_without_a_start_date_shows_no_cells(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []

    @ui.page("/")
    def index() -> None:
        main = GanttChart(team_project(), {}, noop_actions())
        main.build()
        project = team_project()
        project.tasks[0].planned_start = None
        project.tasks[0].planned_end = None
        screen = AssignScreen(project, project.tasks[0], {}, on_confirm=confirmed.append)
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")

    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-no-start")
    await user.should_see(marker="assign-members")  # 一覧は出す
    assert screens[0].plan is None


async def test_the_chart_updates_after_a_drop(user: User) -> None:
    screen, _ = await open_team_screen(user)
    assert screen.chart is not None
    before = screen.chart.project.tasks[0].weekly_crew
    screen.drop_member("鈴木", 1, None)
    assert screen.chart.project.tasks[0].weekly_crew != before  # 複製が作り直されている


async def test_confirm_returns_the_changed_trial(user: User) -> None:
    screen, confirmed = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    user.find(marker="assign-confirm").click()
    assert [a.name for a in confirmed[0].task.weekly_crew[1]] == ["田中", "鈴木"]


async def test_the_screen_without_members_says_so(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)  # one_task_project はメンバーがいない
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-no-members")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assign_screen.py -v`
Expected: FAIL(`assign-members`が出ない・`drop_member`がない)

- [ ] **Step 3: 実装する**

`assign_screen.py`を次のとおりに変える(段階 1 の部分は残し、追加・変更する部分を示す)。

import を足す:

```python
from datetime import timedelta

from projectapp.assign_drag import (
    ASSIGN_DRAG_CSS,
    ASSIGN_DRAG_JS,
    ASSIGN_DROP_EVENT,
)
from projectapp.assign_trial import (
    CellPlan,
    TeamGroup,
    cell_plan,
    team_groups,
)
from projectapp.avatar import avatar
from projectapp.daily_crew import (
    WEEK_DAYS,
    add_member,
    merge_week,
    remove_member,
    segments,
    split_week,
)
from projectapp.gantt import COLUMN_WIDTH_PX, from_name
from projectapp.models import Column  # Column の import 元は timeline.py(`from projectapp.timeline import Column`)に合わせる
from projectapp.timeline import interval_span
```

`__init__`に足す:

```python
        self.plan: CellPlan | None = cell_plan(project, self.trial.task, holidays)
        self.original_weeks = self.plan.weeks if self.plan is not None else 0
```

`build`のレイアウトを、左の欄+チャートの横並びに変える(チャートの`GanttChart`は`task_extra`を持たせる):

```python
            with ui.row().classes("w-full no-wrap gap-2").style("flex: 1 1 0; min-height: 0"):
                self.members_panel(team_groups(self.project))
                with ui.element("div").classes("col").style("min-width: 0; height: 100%"):
                    self.chart = GanttChart(
                        trial_project(self.project, self.trial),
                        self.holidays,
                        read_only_actions(),
                        now=self.now,
                        name_width=self.name_width,
                        fiscal_start_month=self.fiscal_start_month,
                    )
                    self.chart.task_extra = self.assign_row
                    self.chart.build_embedded(
                        ViewOptions(
                            read_only=True,
                            excluded=hidden_ids(self.project, self.trial),
                            hide_excluded=True,
                        )
                    )
```

`open`の先頭付近(ダイアログを作る前)に、ドラッグの登録とイベントを足す(ページに 1 回だけでよいことは、JS 側の`__assignDragInstalled`が守る。`ui.on`は画面を開くたびに足されないよう、`self.registered`で 1 回にする):

```python
        ui.add_css(ASSIGN_DRAG_CSS)
        ui.add_head_html(f"<script>{ASSIGN_DRAG_JS}</script>")
        ui.on(
            ASSIGN_DROP_EVENT,
            lambda e: self.drop_member(
                str(e.args["name"]), int(e.args["week"]), e.args["day"]
            ),
        )
```

メソッドを足す:

```python
    def members_panel(self, groups: list[TeamGroup]) -> None:
        assigned = {a.name for a in self.trial.task.assignees}
        with ui.column().classes("gap-2").style("width: 14rem; flex: none; overflow: auto").mark("assign-members"):
            ui.label("メンバー").classes("text-subtitle2")
            if not groups:
                ui.label("メンバーがいません").classes("text-grey").mark("assign-no-members")
            for group in groups:
                ui.label(group.name).classes("text-caption text-grey").mark(
                    f"assign-team-{group.name}"
                )
                with ui.row().classes("gap-1"):
                    for member in group.members:
                        chip = (
                            ui.row()
                            .classes("items-center no-wrap gap-1 q-px-xs")
                            .props(f'draggable=true data-assign-member="{member.name}"')
                            .style("border: 1px solid rgba(128,128,128,0.5); border-radius: 12px")
                            .mark(f"assign-member-{member.name}")
                        )
                        with chip:
                            avatar(member.name, member.icon, 24)
                            ui.label(member.name).classes("text-body2")
                        if member.name in assigned:
                            chip.style("border-color: #1976d2; border-width: 2px")
                            chip.mark(f"assign-member-assigned-{member.name}")

    def assign_row(self, task: Task, columns: list[Column], width: int) -> None:
        """タスク行の直下の割り当ての行(`GanttChart.task_extra`)。週ごとのセルを列に合わせて置く。"""
        if task.id != self.trial.task.id:
            return
        row = (
            ui.row()
            .classes("no-wrap")
            .style(f"height: 40px; position: relative; width: 100%")
            .mark("assign-row")
        )
        with row:
            if self.plan is None:
                ui.label("開始日がないため週に分けられません").classes(
                    "text-caption text-grey"
                ).style(f"position: absolute; left: {from_name(8)}; top: 10px").mark(
                    "assign-no-start"
                )
                return
            weeks = max(self.plan.weeks, len(task.weekly_crew))
            last_day = self.plan.origin + timedelta(days=WEEK_DAYS * weeks - 1)
            crews = task.weekly_crew or [list(task.assignees)] * weeks
            for seg in segments(crews, task.daily_crew, self.plan.origin, last_day):
                self.cell(seg.week, seg.day, seg.first, seg.last, seg.crew, columns, width)
            for week in range(weeks):
                self.daily_toggle(week, columns, width)

    def cell(self, week, day, first, last, crew, columns, width) -> None:
        left, span = interval_span(
            datetime.combine(first, time.min),
            datetime.combine(last + timedelta(days=1), time.min),
            columns,
        )
        marker = f"assign-cell-{week}" if day is None else f"assign-cell-{week}-{day}"
        with (
            ui.row()
            .classes("items-center no-wrap gap-1")
            .props(f'data-assign-cell data-week="{week}"' + (f' data-day="{day}"' if day is not None else ""))
            .style(
                f"position: absolute; left: {from_name(left * width)}; width: {span * width - 2:.0f}px;"
                " top: 2px; height: 36px; border: 1px dashed rgba(128,128,128,0.6); border-radius: 4px;"
                " overflow: hidden; padding: 0 2px"
            )
            .mark(marker)
        ):
            for assignee in crew:
                self.chip(assignee.name, week, day)

    def chip(self, name: str, week: int, day: int | None) -> None:
        icon = next((m.icon for m in self.project.members if m.name == name), "")
        suffix = f"{week}-{name}" if day is None else f"{week}-{day}-{name}"
        with ui.row().classes("items-center no-wrap gap-0").mark(f"assign-chip-{suffix}"):
            avatar(name, icon, 20).tooltip(name)
            ui.button(
                icon="close",
                on_click=lambda n=name, w=week, d=day: self.remove_member_at(n, w, d),
            ).props("flat dense round size=xs").mark(f"assign-remove-{suffix}")

    def daily_toggle(self, week: int, columns, width) -> None:
        assert self.plan is not None
        left, _ = interval_span(
            datetime.combine(self.plan.origin + timedelta(days=WEEK_DAYS * week), time.min),
            datetime.combine(self.plan.origin + timedelta(days=WEEK_DAYS * week + 1), time.min),
            columns,
        )
        daily = week in self.trial.task.daily_crew
        ui.button(
            "週に戻す" if daily else "日ごと",
            on_click=lambda w=week: self.toggle_daily(w),
        ).props("flat dense size=xs").style(
            f"position: absolute; left: {from_name(left * width)}; top: -14px; z-index: 2"
        ).mark(f"assign-daily-{week}")

    def refresh(self) -> None:
        """試算のタスクから複製を作り直し、チャート(棒・完了予定・警告)と割り当ての行を描き直す。"""
        if self.chart is not None:
            self.chart.set_project(trial_project(self.project, self.trial))

    def drop_member(self, name: str, week: int, day: int | None) -> None:
        if self.plan is None:
            ui.notify("開始日がないため週に分けられません", type="warning")
            return
        if name not in {m.name for m in self.project.members}:
            ui.notify("このメンバーは名簿にいません", type="warning")
            return
        result = add_member(self.trial.task, name, week, day, weeks=self.plan.weeks)
        if result is None:
            ui.notify("すでに割り当てているか、この週には割り当てられません", type="warning")
            return
        self.trial.task = result
        self.refresh()

    def remove_member_at(self, name: str, week: int, day: int | None) -> None:
        result = remove_member(self.trial.task, name, week, day)
        if result is None:
            ui.notify("最後の 1 人は外せません", type="warning")
            return
        self.trial.task = result
        self.refresh()

    def toggle_daily(self, week: int) -> None:
        task = self.trial.task
        result = (
            merge_week(task, week)
            if week in task.daily_crew
            else split_week(task, week)
        )
        if result is None:
            ui.notify("この週は日ごとに変えられません", type="warning")
            return
        self.trial.task = result
        self.refresh()
```

(通知の文言は、テストの`すでに割り当てています`に合わせて、重複のときは`すでに割り当てています`、それ以外は`この週には割り当てられません`と分けて通知する。`datetime`・`time`は`datetime`から import する。`Column`は`from projectapp.timeline import Column`。`GanttChart`は`self.trial`を直接見ず`project`の複製を見るので、`refresh`で必ず`set_project`を呼ぶ。`COLUMN_WIDTH_PX`は使わなければ import しない。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assign_screen.py test/test_assign_trial.py -v`
Expected: PASS。落ちたら、次の順で見る。
1. `GanttChart.set_project`が描き直さないとき: `refresh`で`self.chart.render.refresh()`も呼ぶ。
2. セルの位置(`interval_span`の戻り値)が列の単位でないとき: `timeline.interval_span`の docstring(列の単位)を確かめ、`width`(1 列の px)を掛ける。
3. 月次・四半期でセルが極端に細いとき: 設計書の「確かめること」。`date_x`・`interval_span`が使えない(範囲の外で`None`・例外)なら、設計書を直して利用者に確認する。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン専用画面にメンバー一覧と割り当ての行(ドラッグでの割り当て)を足す(要望 168 段階 2)"
```

---

### Task 6: 確定との接続・文書・最終確認

**Files:**
- Modify: `test/test_views.py`・`.claude/spec/dashboard.md`・`docs/development.md`・`docs/requests.md`

**Interfaces:**
- Consumes: `MainView.open_assign_screen`・`MainView.assign_screen`(段階 1)・`AssignScreen.drop_member`

- [ ] **Step 1: テストを書く(確定で書き戻し、Undo 1 ステップ)**

`test/test_views.py`に足す:

```python
@pytest.mark.smoke
async def test_assign_screen_drop_then_confirm_writes_weekly_crew_and_undo_restores(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    task_id = view.project.tasks[0].id
    steps = len(view.history.undo_stack)
    user.find(marker="dashboard-due-assign-0").click()
    await user.should_see(marker="assign-screen")
    assert view.assign_screen is not None
    view.project.members.append(Member("鈴木", 1.0))  # 一覧に出す(画面は開いた時点の名簿)
    view.assign_screen.project.members.append(Member("鈴木", 1.0))
    view.assign_screen.drop_member("鈴木", 0, None)
    user.find(marker="assign-confirm").click()
    saved = view.project.task_map()[task_id]
    assert saved.weekly_crew and [a.name for a in saved.weekly_crew[0]] == ["田中", "鈴木"]
    assert len(view.history.undo_stack) == steps + 1
    view.undo()
    assert not view.project.task_map()[task_id].weekly_crew
```

(`open_dashboard_view`のタスク「設計」は田中が担当で、開始・完了が入っているので週に分けられる。`Member`は`test_views.py`で import 済み。名簿への足し方は、`open_dashboard_view`が`view.project.members = [Member("田中", 1.0)]`としているので、テストの最初に`view.project.members = [Member("田中", 1.0), Member("鈴木", 1.0)]`に変えるほうが素直。その形に直してよい。)

- [ ] **Step 2: 失敗を確かめ、通す**

Run: `uv run pytest test/test_views.py -k "drop_then_confirm" -v`
Expected: Task 5 までの実装で PASS(確定は段階 1 のとおり`apply_trial`で書き戻す。FAIL なら、画面が`self.project`の名簿を開いた時点のコピーで持つこと・`trial.task`への反映を確かめる)

- [ ] **Step 3: 仕様を更新する**

`.claude/spec/dashboard.md`の、アサイン専用画面の項(段階 1)の末尾の`割り当ての操作は段階 2 以降。`を、次の文に置き換える:

```
段階 2(割り当て操作): 画面の左に、チームごとのメンバーのアイコン+名前のチップを並べる(複数チームの人は各チームに出す。チームのない人は`チームなし`。この試算のタスクの担当者は枠を付ける)。ガントチャートのタスク行の直下に割り当ての行を足し、日付の列に合わせた週ごとのセルを並べる(`GanttChart.task_extra`)。チップをセルへドラッグアンドドロップすると、その週だけに足す(割り当て率 100% 固定)。週ごとでないタスクは最初の 1 回で週ごとに分け、ほかの週は今の担当のまま(担当者のいないタスクは、最初の 1 回は全体の担当にする)。定義済みの週より先へ落としたときは、間を直前の担当で埋める(52 週まで)。各チップの`×`で外す(そのセルの最後の 1 人は外せない)。週のヘッダーの`日ごと`/`週に戻す`で、その週を日ごと(7 日のセル)にできる。開始日のないタスクは、セルを出さず`開始日がないため週に分けられません`と出す(一覧は出す)。操作のたびに棒・完了予定・警告を描き直す。確定するまでメインは変えない。割り当て率の調整・一定区間からの集中増員は段階 3。
```

`docs/development.md`のモジュール一覧の`assign_screen.py`の行に、`メンバー一覧・割り当ての行(task_extra)・ドロップの処理(段階 2)`を足し、`assign_drag.py`(メンバーのドラッグの JS・CSS)の行を足す。`docs/requests.md`の要望 168 の`### 状態`を、`段階 1・2 は実装済み(段階 2 は実機確認待ち)。段階 3〜5 は未着手。`に直す。

- [ ] **Step 4: 全体の確認**

Run: `uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: ruff はエラーなし・ty は既存の 9 件のまま(新しい指摘を足さない)

Run: `uv run pytest -m smoke -q`
Expected: PASS(失敗したときに限り`uv run pytest -n auto`)

Run: `uv run pytest test/test_gantt.py test/test_context_menu.py test/test_bottom_split.py test/test_assign_screen.py test/test_assign_trial.py test/test_assign_drag.py test/test_daily_crew.py test/test_daily_crew_assign.py -q -n auto`
Expected: PASS(メインの描画が変わっていない確認)

- [ ] **Step 5: コミットと PR**

```bash
git add -A
git commit -m "docs: アサイン専用画面(段階 2)の仕様と構成を書く(要望 168)"
git push -u origin feature/request-168-stage2
gh pr create --base develop --title "feat: アサイン専用画面の割り当て操作(要望 168 段階 2)" --body "メンバー一覧(チームごと)と、ガントチャートの割り当ての行(週・日のセル)を足し、ドラッグアンドドロップで週(日)に割り当てられるようにする。確定でメインへ反映(Undo 1 ステップ)。割り当て率の調整は段階 3。

設計書: docs/superpowers/specs/2026-11-22-assign-screen-stage2-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR を作ったら止まる。実機確認とマージの指示を待つ。

---

## Self-Review

- **Spec coverage**: 担当の操作(Task 1)・メンバー一覧のチーム分け(Task 2・5)・`task_extra`(Task 3)・ドラッグ(Task 4)・割り当ての行・`×`・日ごとの切り替え・開始日なし・通知・描き直し・確定(Task 5・6)・仕様の更新(Task 6)。欠けなし。
- **Type consistency**: `add_member(task, name, week, day=None, *, weeks=1)`・`remove_member(task, name, week, day=None)`は Task 1 の定義のまま Task 5 で使う。`CellPlan(origin, weeks)`・`cell_plan`・`team_groups`・`TeamGroup`は Task 2 と Task 5 で一致。`GanttChart.task_extra(task, columns, width)`は Task 3 と Task 5 の`assign_row`で一致。マーカー`assign-cell-<週>[-<日>]`・`assign-chip-…`・`assign-remove-…`・`assign-daily-<週>`は Task 5 のテストと実装で一致。ドラッグのイベント名`assign_drop_member`は Task 4 と Task 5 で一致。
- **既知の確認点**: Task 3 の`render`のルートのタスクのループ(`task_row`の戻り値と`folded`)・Task 5 の`interval_span`の戻り値の単位(列)と月次・四半期でのセルの幅・`GanttChart.set_project`が描き直すか・`Membership`・`Team`の引数・`Column`の import 元。いずれも実装時に実コードで確かめる手順を各 Step に書いた。
