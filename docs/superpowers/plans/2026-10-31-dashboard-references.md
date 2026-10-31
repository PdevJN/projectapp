# ダッシュボードのプロジェクト参照行の進捗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 参照先のプロジェクトの通常タスク・節目を、ダッシュボードの `チーム全体の進捗` と `進捗と遅れ` に、親のタスクと同列に数える(要望 90)。

**Architecture:** `dashboard.py` に、タスクと所属プロジェクト・日程をまとめた `Entry` を足し、2 カードの集計だけが `Entry` を使う。参照先は `ChildProject(project, holidays)` として `summarize` に渡す。参照先の読み込みは `ReferenceResolver.project` と `load_children`(`reference.py`)、画面は `views.py` が組み立てる。保存形式は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、`uvx ty check src`

**Spec:** `docs/superpowers/specs/2026-10-31-dashboard-references-design.md`

## Global Constraints

- 保存形式・`version` は変えない(17 のまま)。
- 数えるのは参照先の通常タスクと節目。まとめと参照行は数えない(参照先の中の参照行は展開しない。1 段のみ)。
- 参照行そのものは数えない(従来どおり)。
- 同じ参照先は 1 回だけ数える。読めない・見つからない参照先は数えない。
- 期間の判定・予定超過の判定は、参照先自身の稼働設定・祝日・イベントで行う。
- 対象は `チーム全体の進捗` と `進捗と遅れ` だけ。負荷・工数・残りの工数・期限・`全プロジェクト` は変えない。
- 参照先のタスクの表示名は `タスク名(参照先名)`。
- 設計書からの1点の差: `summarize` に渡すのは `Mapping[str, Project]` ではなく、参照先自身の休み(イベント込み)を持つ `Mapping[str, ChildProject]`。設計書は Task 5 で直す。
- テストは `test/`、型チェックは `uvx ty check src`。コードのコメントの密度・命名は周囲に合わせる(日本語の docstring)。

## Review Focus

- 切り出した前後の数字の一致(`extract.extract` の結果で比べる)。Task 2 のテスト。
- 親にいない名前だけが担当の参照先タスクが `未割り当て` に入ること。Task 2 のテスト。
- 同じ参照先を指す参照行が 2 つあっても二重に数えないこと。Task 3 のテスト。
- 読めない・見つからない参照先で画面が止まらず、数えないこと。Task 3 のテスト。
- 参照先の中の参照行・まとめを数えないこと(二重・循環)。Task 1 のテスト。
- 参照先の日程が、参照先自身の休みで判定されること(親と休みが違うとき)。Task 1 のテスト。

---

## ファイル構成

- 変更: `src/projectapp/dashboard.py`(`ChildProject`・`Entry`・`_entries`、集計 4 関数と `Dashboard`・`summarize`)
- 変更: `src/projectapp/reference.py`(`ReferenceResolver.project`・`load_children`)
- 変更: `src/projectapp/views.py`(`refresh_dashboard` で `children` を渡す)
- 変更: `src/projectapp/dashboard_view.py`(`参照先 n 件を含む` の表示)
- 新規: `test/test_dashboard_references.py`
- 変更: `test/test_reference.py`(`project`・`load_children`)、`test/test_dashboard_view.py`(表示)
- 変更: `CLAUDE.md`(プロジェクト直下の仕様)、`docs/requests.md`・`docs/hidden-requests.md`・`docs/request-history.md`・`docs/work-log.md`、設計書

---

### Task 1: `Entry` と、チーム全体の進捗への展開

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Create: `test/test_dashboard_references.py`

**Interfaces:**
- Produces: `ChildProject(project: Project, holidays: dict[date, str])`(frozen dataclass)、`Entry(task, project, schedule, origin)`(`label` プロパティ)、`_entries(project, holidays, member=None, children=None) -> list[Entry]`、`summarize_team_progress(..., children: Mapping[str, ChildProject] | None = None)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_references.py`:

```python
from datetime import date, datetime

from projectapp.dashboard import ChildProject, Period, summarize_team_progress
from projectapp.models import Actual, Assignee, Event, Member, Project, Status, Task, TaskKind

NOW = datetime(2026, 10, 7, 12)


def parent() -> Project:
    return Project(
        "親",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        tasks=[
            Task("p1", id="p1", effort_hours=8, status=Status.DONE, assignees=[Assignee("田中", 1.0)]),
            Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤"),
        ],
    )


def child() -> Project:
    return Project(
        "基盤",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("外部", 1.0)],
        tasks=[
            Task("c1", id="c1", effort_hours=4, status=Status.DONE, assignees=[Assignee("田中", 1.0)]),
            Task("c2", id="c2", effort_hours=4, status=Status.RUNNING, progress=50, assignees=[Assignee("外部", 1.0)]),
        ],
    )


def children(project: Project | None = None, holidays: dict[date, str] | None = None) -> dict[str, ChildProject]:
    chosen = project or child()
    return {chosen.name: ChildProject(chosen, holidays or {})}


def test_team_progress_counts_the_tasks_of_a_referenced_project_like_its_own() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, None, children())
    assert team.counts[Status.DONE] == 2  # 親の p1 と子の c1
    assert team.counts[Status.RUNNING] == 1
    assert team.hours[Status.DONE] == 12
    assert round(team.percent) == round((8 * 100 + 4 * 100 + 4 * 50) / 16)


def test_the_reference_row_itself_is_not_counted() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, None, None)
    assert sum(team.counts.values()) == 1  # 子を渡さなければ、今までどおり参照行は数えない


def test_a_referenced_task_is_named_with_its_project() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, None, children())
    assert team.tasks[Status.RUNNING] == ["c2(基盤)"]
    assert team.tasks[Status.DONE] == ["p1", "c1(基盤)"]


def test_summaries_and_references_inside_the_referenced_project_are_not_counted() -> None:
    inner = child()
    inner.tasks += [
        Task("S", id="S", kind=TaskKind.SUMMARY, children=["c1"]),
        Task("孫", id="g", kind=TaskKind.REFERENCE, ref_project="孫"),
    ]
    team = summarize_team_progress(parent(), None, NOW, {}, None, children(inner))
    assert sum(team.counts.values()) == 3  # p1・c1・c2 だけ


def test_the_member_filter_matches_referenced_tasks_by_name() -> None:
    team = summarize_team_progress(parent(), None, NOW, {}, "外部", children())
    assert sum(team.counts.values()) == 1 and team.tasks[Status.RUNNING] == ["c2(基盤)"]  # 親の名簿にいなくても、名前で当たる


def test_the_period_uses_the_schedule_of_the_referenced_project() -> None:
    late = child()
    late.tasks[1].deadline = datetime(2026, 12, 1, 18)  # 期間の外
    late.tasks[0].deadline = datetime(2026, 10, 8, 18)  # 期間の中
    period = Period(date(2026, 10, 5), date(2026, 10, 11))
    team = summarize_team_progress(parent(), period, NOW, {}, None, children(late))
    assert [n for names in team.tasks.values() for n in names] == ["c1(基盤)"]  # 親の p1 は日程も締切もなく期間にかからない


def test_the_period_uses_the_holidays_of_the_referenced_project() -> None:
    inner = child()
    inner.tasks[1].planned_start = datetime(2026, 10, 6, 9)
    inner.tasks[1].effort_hours = 8
    inner.events = [Event(date(2026, 10, 6), date(2026, 10, 9), "休業", "gray", closed=True)]
    from projectapp.events import effective_holidays

    holidays = effective_holidays(inner, {})
    period = Period(date(2026, 10, 12), date(2026, 10, 18))  # 休業で完了予定が来週に押される
    team = summarize_team_progress(parent(), period, NOW, {}, None, children(inner, holidays))
    assert team.counts[Status.RUNNING] == 1
    plain = summarize_team_progress(parent(), period, NOW, {}, None, children(inner, {}))  # 休みを渡さなければ今週で終わる
    assert plain.counts[Status.RUNNING] == 0
```

`Event` の引数名は `models.py` で確認して合わせる(`Event(start, end, text, color, closed=)`)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_references.py -q`
Expected: FAIL(`ChildProject` を import できない)

- [ ] **Step 3: 実装する**

`dashboard.py` の `_tasks` の下に足す(`NamedTuple` と `Schedule` は import 済み):

```python
@dataclass(frozen=True)
class ChildProject:
    """参照先のプロジェクトと、その休み(参照先自身のイベントを反映したもの)。"""

    project: Project
    holidays: dict[date, str]


class Entry(NamedTuple):
    """集計の 1 件。タスクと、それが属するプロジェクトの日程(参照先のタスクは参照先自身の日程)。"""

    task: Task
    project: Project
    schedule: Schedule
    origin: str  # 参照先のタスクなら参照先の名前。開いているプロジェクトのタスクは空

    @property
    def label(self) -> str:
        return f"{self.task.name}({self.origin})" if self.origin else self.task.name


def _entries(
    project: Project,
    holidays: dict[date, str],
    member: Scope = None,
    children: Mapping[str, ChildProject] | None = None,
) -> list[Entry]:
    """進捗の集計の対象。開いているプロジェクトのタスクに、参照先のタスクが続く(参照先の順)。"""
    own = Schedule(project, holidays)
    entries = [Entry(task, project, own, "") for task in _tasks(project, member)]
    for name, child in (children or {}).items():
        schedule = Schedule(child.project, child.holidays)
        entries += [Entry(task, child.project, schedule, name) for task in _tasks(child.project, member)]
    return entries
```

`summarize_team_progress` を差し替える(`_touches` はそのまま。`children` を末尾に追加):

```python
def summarize_team_progress(
    project: Project,
    period: Period | None = None,
    now: datetime | None = None,
    holidays: dict[date, str] | None = None,
    member: Scope = None,
    children: Mapping[str, ChildProject] | None = None,
) -> TeamProgress:
    """チーム全体の進捗。担当者に関わらず、1 タスクを 1 回だけ数える。`period` があれば、期間にかかるタスクだけ。参照先のタスクも同列に数える。"""
    hours = {status: 0.0 for status in Status}
    counts = {status: 0 for status in Status}
    names: dict[Status, list[str]] = {status: [] for status in Status}
    weighted = total = 0.0
    moment = now or datetime.now()
    for entry in _entries(project, holidays or {}, member, children):
        task = entry.task
        weight_and_percent = _progress_weight(task)
        if weight_and_percent is None or (period is not None and not _touches(task, entry.schedule, period, moment)):
            continue
        weight, percent = weight_and_percent
        hours[task.status] += weight
        counts[task.status] += 1
        names[task.status].append(entry.label)
        weighted += weight * percent
        total += weight
    return TeamProgress(weighted / total if total else None, hours, period, counts, names)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard_references.py test/test_dashboard.py -q`
Expected: PASS(既存の `summarize_team_progress` のテストも通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard_references.py
git commit -m "feat: チーム全体の進捗に、参照先のタスクを同列に数える(要望 90)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 進捗と遅れへの展開と `summarize` の配線

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_progress`・`summarize_member_progress`・`summarize_team_rows`・`Dashboard`・`summarize`)
- Modify: `test/test_dashboard_references.py`

**Interfaces:**
- Consumes: Task 1 の `ChildProject`・`Entry`・`_entries`
- Produces: `summarize_progress(project, holidays, now, member=None, children=None)`、`summarize_member_progress(project, children=None)`、`summarize_team_rows(project, children=None)`、`summarize(..., children: Mapping[str, ChildProject] | None = None)`、`Dashboard.references: int`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_references.py` に足す(import に `extract`・`PeriodKind`・`summarize`・`summarize_progress` を足す):

```python
from projectapp.dashboard import PeriodKind, summarize, summarize_progress
from projectapp.extract import extract
from projectapp.models import Section, Team, Membership


def test_progress_counts_the_referenced_tasks_and_names_overdue_rows_with_the_project() -> None:
    inner = child()
    inner.tasks[1].deadline = datetime(2026, 10, 6, 18)  # 実行中で締切を過ぎた
    progress = summarize_progress(parent(), {}, NOW, None, children(inner))
    assert progress.counts[Status.DONE] == 2 and progress.counts[Status.RUNNING] == 1
    assert [row.name for row in progress.overdue] == ["c2(基盤)"]
    assert progress.overdue[0].assignee == "外部"


def test_member_rows_match_referenced_tasks_by_name_and_the_rest_are_unassigned() -> None:
    rows = {row.name: row for row in summarize_progress(parent(), {}, NOW, None, children()).by_member}
    assert rows["田中"].counts[Status.DONE] == 2  # 親の p1 と、子の c1(同名の田中)
    assert rows["未割り当て"].counts[Status.RUNNING] == 1  # 外部は親の名簿にいない


def test_team_rows_count_referenced_tasks_of_the_team_members() -> None:
    project = parent()
    project.members[0].id = "m1"
    project.teams = [Team("開発", id="t1")]
    project.members[0].teams = [Membership("t1", 100)]
    rows = {row.name: row for row in summarize_progress(project, {}, NOW, None, children()).by_team}
    assert rows["開発"].counts[Status.DONE] == 2


def test_filtering_by_member_filters_the_referenced_tasks_too() -> None:
    progress = summarize_progress(parent(), {}, NOW, "田中", children())
    assert progress.counts[Status.DONE] == 2 and progress.counts[Status.RUNNING] == 0
    assert progress.by_member == []  # 絞り込み中は従来どおり空


def test_summarize_reports_how_many_referenced_projects_it_counted() -> None:
    period = Period(date(2026, 10, 5), date(2026, 10, 11))
    assert summarize(parent(), period, NOW, {}, PeriodKind.ALL, None, None, children()).references == 1
    assert summarize(parent(), period, NOW, {}, PeriodKind.ALL).references == 0


def test_numbers_match_before_and_after_extracting_tasks_into_a_child() -> None:
    whole = Project(
        "親",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a", effort_hours=8, status=Status.DONE, assignees=[Assignee("田中", 1.0)]),
                    Task("b", id="b", effort_hours=4, status=Status.RUNNING, progress=25, assignees=[Assignee("田中", 1.0)]),
                    Task("c", id="c", effort_hours=6, assignees=[Assignee("田中", 1.0)]),
                ],
                id="s1",
            )
        ],
    )
    period = Period(date(2026, 10, 5), date(2026, 10, 11))
    before = summarize(whole, period, NOW, {}, PeriodKind.ALL)
    result = extract(whole, ["b", "c"], "子")
    after = summarize(
        result.parent, period, NOW, {}, PeriodKind.ALL, None, None, {"子": ChildProject(result.child, {})}
    )
    assert after.progress.percent == before.progress.percent
    assert after.progress.counts == before.progress.counts
    assert after.team.percent == before.team.percent
    assert after.team.hours == before.team.hours
    assert after.team.counts == before.team.counts
    assert [row.counts for row in after.progress.by_member] == [row.counts for row in before.progress.by_member]
```

`Team`・`Membership` のコンストラクタ引数は `models.py` と `test/test_dashboard.py` の既存テスト(`Team`・`Membership` を使うもの)に合わせて直す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_references.py -q`
Expected: FAIL(`children` を受け取らない・`references` がない)

- [ ] **Step 3: 実装する**

`_member_row` は変えない。次の 3 関数を差し替える:

```python
def summarize_member_progress(project: Project, children: Mapping[str, ChildProject] | None = None) -> list[MemberProgress]:
    """メンバーごとの進捗。共同タスクは担当の全員の行に数える。メンバーが担当にいないタスクは`未割り当て`。参照先のタスクは名前で当てる。"""
    if not project.members:
        return []
    tasks = [entry.task for entry in _entries(project, {}, None, children)]
    names = {member.name for member in project.members}
    rows = [_member_row(m.name, [t for t in tasks if m.name in t.assignee_names]) for m in project.members]
    # 節目は担当を持てず、進捗の重みもないので、割り当て漏れには数えない
    nobody = [t for t in tasks if t.kind not in (TaskKind.CHECKPOINT, TaskKind.REFERENCE) and not names.intersection(t.assignee_names)]
    if nobody:
        rows.append(_member_row(UNASSIGNED, nobody))
    return rows


def summarize_team_rows(project: Project, children: Mapping[str, ChildProject] | None = None) -> list[MemberProgress]:
    """チームごとの進捗(メンバーのいるチームだけ)。共同タスクは、担当が所属する全チームの行に数える。"""
    tasks = [entry.task for entry in _entries(project, {}, None, children)]
    rows = []
    for name in teams_with_members(project):
        scoped = team_scope(project, name)
        assert scoped is not None
        rows.append(_member_row(name, [t for t in tasks if not scoped.isdisjoint(t.assignee_names)]))
    return rows


def summarize_progress(
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    member: Scope = None,
    children: Mapping[str, ChildProject] | None = None,
) -> Progress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    overdue: list[OverdueRow] = []
    for entry in _entries(project, holidays, member, children):
        task = entry.task
        counts[task.status] += 1
        if (weight_and_percent := _progress_weight(task)) is not None:  # 節目は進捗率の重みに入れない
            weight, percent = weight_and_percent
            weighted += weight * percent
            total += weight
        if task.status is not Status.DONE and is_overdue(task, entry.project, entry.schedule.holidays, now, entry.schedule):
            moment = actual_end(task) or now
            limits = [
                limit
                for limit in (task.deadline, entry.schedule.end(task))
                if limit is not None and moment > limit
            ]
            limit = min(limits, default=task.deadline or now)  # 見込みの超過は、締切を基準にする
            overdue.append(OverdueRow(entry.label, assignee_label(task), limit))
    overdue.sort(key=lambda row: row.limit)
    by_member = summarize_member_progress(project, children) if member is None else []
    by_team = summarize_team_rows(project, children) if member is None else []
    return Progress(weighted / total if total else None, counts, overdue, by_member, by_team)
```

`Dashboard`(dataclass)に `references: int = 0  # 進捗に数えた参照先のプロジェクトの数` を足す。`summarize` に引数 `children: Mapping[str, ChildProject] | None = None` を末尾に足し、`summarize_progress(project, holidays, now, scope, children)`、`summarize_team_progress(..., scope, children)` に渡し、`Dashboard(...)` に `references=len(children or {})` を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard_references.py test/test_dashboard.py test/test_dashboard_backlog.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard_references.py
git commit -m "feat: 進捗と遅れに、参照先のタスクを同列に数える(要望 90)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 参照先の読み込み(`ReferenceResolver.project`・`load_children`)

**Files:**
- Modify: `src/projectapp/reference.py`
- Modify: `test/test_reference.py`

**Interfaces:**
- Consumes: `ChildProject`(Task 1)
- Produces: `ReferenceResolver.project(name: str) -> tuple[Project | None, str]`、`load_children(project, resolver, base_holidays) -> dict[str, ChildProject]`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_reference.py` の末尾に足す(既存の `source()`・`resolver_for` を使う。import に `load_children`、`Event`、`Task`、`TaskKind` を足す):

```python
def parent_with_references(*names: str) -> Project:
    return Project(
        "親",
        tasks=[Task(n, id=f"r{i}", kind=TaskKind.REFERENCE, ref_project=n) for i, n in enumerate(names)],
    )


def test_project_returns_the_referenced_project_and_caches_by_content(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    first, problem = resolver.project("基盤")
    assert problem == "" and first is not None and first.name == "基盤"
    assert resolver.project("基盤")[0] is first  # ファイルが同じ間は同じ物を返す
    changed = source()
    changed.tasks.append(Task("d", id="d"))
    save_project(changed, tmp_path)
    assert resolver.project("基盤")[0] is not first


def test_project_gives_a_reason_for_a_missing_or_broken_file(tmp_path: Path) -> None:
    resolver = resolver_for(tmp_path)
    assert resolver.project("無い")[0] is None
    (tmp_path / "壊れ.json").write_text("{", encoding="utf-8")
    value, problem = resolver.project("壊れ")
    assert value is None and "壊れ" in problem


def test_load_children_reads_each_referenced_project_once_and_skips_unreadable_ones(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    parent = parent_with_references("基盤", "基盤", "無い")
    children = load_children(parent, resolver, {})
    assert list(children) == ["基盤"]  # 重複は 1 回、読めないものは外す
    assert children["基盤"].project.name == "基盤"


def test_load_children_gives_the_child_its_own_closed_event_holidays(tmp_path: Path) -> None:
    inner = source()
    inner.events = [Event(date(2026, 10, 12), date(2026, 10, 12), "休業", "gray", closed=True)]
    save_project(inner, tmp_path)
    children = load_children(parent_with_references("基盤"), resolver_for(tmp_path), {})
    assert date(2026, 10, 12) in children["基盤"].holidays


def test_load_children_skips_a_reference_to_the_project_itself(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    own = parent_with_references("基盤")
    own.name = "基盤"
    assert load_children(own, resolver_for(tmp_path), {}) == {}
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_reference.py -q`
Expected: FAIL(`project`・`load_children` がない)

- [ ] **Step 3: 実装する**

`reference.py` の import に `from projectapp.dashboard import ChildProject, _progress_weight` を足す。`ReferenceResolver.__init__` に `self._projects: dict[str, tuple[str, Project]] = {}` を足し、`live` の下にメソッドを足す:

```python
    def project(self, name: str) -> tuple[Project | None, str]:
        """参照先のプロジェクトそのもの(ダッシュボードの展開用)。内容のハッシュが同じ間は同じ物を返す。"""
        path = self.project_dir() / f"{name}.json"
        digest = file_digest(path)
        if digest is None:
            return None, f"「{name}.json」が格納先にありません"
        cached = self._projects.get(name)
        if cached is not None and cached[0] == digest:
            return cached[1], ""
        try:
            loaded = load_project(path)
        except Exception as exc:  # noqa: BLE001 他人のファイルの形の崩れで、画面を止めない
            return None, f"「{name}.json」を読めません({exc or type(exc).__name__})"
        self._projects[name] = (digest, loaded)
        return loaded, ""
```

(`now` は使わないが、`live` と呼び方をそろえて受け取る。使わないなら引数から外してもよいが、その場合はテストと Task 4 の呼び出しも合わせること。→ 未使用の引数は付けない。シグネチャは `project(self, name: str)` とし、上のテストの `resolver.project("基盤")` は `resolver.project("基盤")` に書き換える。)

ファイル末尾に足す:

```python
def load_children(
    project: Project, resolver: ReferenceResolver, base_holidays: dict[date, str]
) -> dict[str, ChildProject]:
    """参照行が指す参照先を、ダッシュボードに数える形で読む(重複は 1 回、自分自身と読めないものは外す)。"""
    names = dict.fromkeys(t.ref_project for t in project.all_tasks() if t.kind is TaskKind.REFERENCE)
    children: dict[str, ChildProject] = {}
    for name in names:
        if name == project.name:
            continue
        child, _ = resolver.project(name)
        if child is not None:
            children[name] = ChildProject(child, effective_holidays(child, base_holidays))
    return children
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_reference.py test/test_dashboard_references.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/reference.py test/test_reference.py
git commit -m "feat: 参照先のプロジェクトを、ダッシュボードの展開用に読む(要望 90)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 画面の配線と `参照先 n 件を含む` の表示

**Files:**
- Modify: `src/projectapp/views.py`(`refresh_dashboard`)
- Modify: `src/projectapp/dashboard_view.py`(`team_card`・`progress_card`)
- Modify: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `load_children`(Task 3)、`summarize(..., children=)`・`Dashboard.references`(Task 2)
- Produces: マーカー `dashboard-team-references`・`dashboard-progress-references`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` に足す(既存の `sample()` と `mount()` の作りに合わせる。`Dashboard` を作る箇所で `references` を指定できる):

```python
async def test_the_team_and_progress_cards_note_how_many_referenced_projects_are_counted(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    data.references = 2
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-references")
    assert text(user, "dashboard-team-references") == "参照先 2 件を含む"
    assert text(user, "dashboard-progress-references") == "参照先 2 件を含む"


async def test_the_cards_do_not_note_references_when_none_are_counted(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-percent")
    await user.should_not_see(marker="dashboard-team-references")
    await user.should_not_see(marker="dashboard-progress-references")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -k references`
Expected: FAIL

- [ ] **Step 3: 実装する**

`dashboard_view.py`: `team_card` の `ui.label(scope)...` の直後に、`progress_card` の `if progress.percent is None:` の前(`with card(...)` の直後)に、次の呼び出しを足す。カードが空のときも出すため、`empty_message` の前に置く。

```python
            references_note(data, "team")
```
```python
            references_note(data, "progress")
```

モジュールの関数として足す(`weighted_note` の近く):

```python
def references_note(data: Dashboard, key: str) -> None:
    """参照先のプロジェクトのタスクを数えているときの注記。`key`はカードごとのマークの末尾(team・progress)。"""
    if data.references:
        ui.label(f"参照先 {data.references} 件を含む").classes("text-caption text-grey").mark(f"dashboard-{key}-references")
```

`views.py` の `refresh_dashboard`: `reference` から `load_children` を import に足し、`summarize(...)` の呼び出しを次にする。

```python
        data = summarize(
            self.project,
            period,
            now,
            self.holidays,
            self.dashboard_kind,
            self.dashboard_member,
            self.dashboard_team,
            load_children(self.project, self.reference_resolver, self.base_holidays),
        )
```

- [ ] **Step 4: 通ることと全体を確認する**

Run: `uv run pytest -q` と `uvx ty check src`
Expected: すべて PASS、型エラーなし

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/views.py src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: ダッシュボードに参照先を数え、件数を注記する(要望 90)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 仕様・記録の更新と実機確認

**Files:**
- Modify: `CLAUDE.md`(プロジェクト直下。ダッシュボードの節)、設計書、`docs/requests.md`・`docs/hidden-requests.md`・`docs/request-history.md`・`docs/work-log.md`

- [ ] **Step 1: 仕様を更新する**

`CLAUDE.md` のダッシュボードの節に追記する: `チーム全体の進捗`と`進捗と遅れ`は、プロジェクト参照行の参照先の通常タスク・節目を、親のタスクと同列に数える(参照行そのものと、参照先の中のまとめ・参照行は数えない。1 段のみ。同じ参照先は 1 回。読めない参照先は数えない。方式〔常に最新・スナップショット〕に関わらず、参照先のファイルを読む。期間・予定超過は参照先自身の稼働設定・祝日・イベントで判定。メンバー・チームは名前で当てる〔親にいなければ`未割り当て`〕。参照先のタスクの表示名は`タスク名(参照先名)`。カードに`参照先 n 件を含む`を出す)。`プロジェクト参照`の項の「ダッシュボード…では数えない」を、「負荷・工数・割り当て超過・担当者向けファイル・PlantUML の取り込みでは数えない(ダッシュボードの進捗系の 2 カードは参照先の中身を数える)」に直す。設計書の `children` の型の記述を `Mapping[str, ChildProject]` に直す。

- [ ] **Step 2: 記録を更新する**

`requests.md` に要望 90 の節を足す(状態・決めた点・関連)。`hidden-requests.md` の要望 90 の行は取り除き(要望 89 までの完了済みの扱いにならう)、`request-history.md` に行を足す(完了・設計書・計画・PR 番号は後で)。`work-log.md` に、設計の決定(展開・スナップショットは常に最新を読む・対象の 2 カード)と結果を足す。

- [ ] **Step 3: 実機確認(利用者と一緒に)**

`uv run projectapp` で、要望 89 で切り出したプロジェクトの親を開き、ダッシュボードで次を確かめる: 切り出し前と進捗率・状態別の件数・予定超過が一致する / 凡例のホバーに `タスク名(参照先名)` が出る / `参照先 n 件を含む` が出る / 子のファイルを消すと数えない(`参照先 0` で注記が消える)。確認用データ `docs/samples/` に必要なら 1 つ足す。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs
git commit -m "docs: ダッシュボードの参照行の進捗(要望 90)の仕様と記録を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
