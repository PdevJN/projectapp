# チーム 段階 2(絞り込み) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートの担当者の絞り込みと、ダッシュボードの期間の横のプルダウンで、メンバーのほかに「チーム」を選べるようにする(要望 85 の段階 2)。

**Architecture:** 1 つのプルダウンに、`全員`・メンバー・`チーム: 名前` を並べる(値は、チームだけ制御文字の接頭辞つき)。選択の読み書きは NiceGUI に依存しない `scope.py` に置く。チームの選択は「そのチームのメンバー名の集合」に解決して、既存のメンバー絞り込みを集合に一般化して使う(`filtering.TaskFilter` と `dashboard` の各集計)。チームの所属の割合による按分は段階 3 なので、この段階では絞り込みだけ(共同タスクは丸ごと数え、人の行は丸ごとの値)。ビューには `team` を足し、チーム名で保存する。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)。型は `uv run ty check src`。

**Spec:** [`docs/superpowers/specs/2026-10-30-teams-design.md`](../specs/2026-10-30-teams-design.md)(段階 2 の節)

## Global Constraints

- 前提: 段階 1(`plans/2026-10-30-teams-stage1.md`)が済んでいる。`Team`・`Membership`・`Member.teams`・`Project.teams`・`teams.team_member_names` を使う。
- チームとメンバーの絞り込みは、同じプルダウンのどちらか一方だけ(組み合わせない)。
- チームを選ぶと、そのチームのメンバーが担当に入っているタスクだけにする。共同タスクは 1 件として丸ごと数え、担当なしと、担当がチームのメンバーでないタスクは入らない(メンバーの絞り込みと同じ)。日程の計算は絞り込まない。
- プルダウンに出すチームは、所属するメンバーがいるものだけ。表示は `チーム: 名前`。
- ダッシュボードの`負荷`・`工数の予定と実績`は、チームを選ぶと、そのチームのメンバーの行だけにする(値は按分しない)。`全員`のときだけ`未割り当て`の行を出す(メンバーの絞り込みと同じ)。
- `全員`のとき、`進捗と遅れ`に`チーム別`の行(名前・進捗率・件数)を、`メンバー別`の隣に出す。メンバーが 0 人、またはメンバーのいるチームがないときは出さない。期間には影響されない。共同タスクは、担当が所属する全チームの行に数える。
- 保存済みのビューは、チームを名前で `team` に保存する(`ViewSpec.team`、`config.json` の `dashboard_views[].team`)。メンバーとチームの両方が書かれていたら、メンバーを優先する。保存したチームが今の名簿にない(またはメンバーがいない)ときは、画面だけ`全員`に戻す(ビューは書き換えず、`●`も出さない)。
- 全プロジェクトを重ねるとき、チームは開いているプロジェクトのもの。そのメンバー名を、全プロジェクトの同名のメンバーに当てて絞り込む。
- ガントチャートのチームの絞り込みは、名簿が変わったら追従する。チームが消えた(メンバーがいなくなった)ら外す。保存しない。
- ダッシュボードの既存の名前 `TeamProgress`・`Dashboard.team`・`summarize_team_progress` は「チーム全体の進捗」(円グラフ)のもので、今回のチームとは別。名前を変えない。新しいものは `team_name`・`by_team` などにする。
- コミット末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. メンバーを選んだときの既存の挙動が変わらないこと(`member` に文字列を渡す既存の呼び出しと既存テスト)。
2. チームを選んだまま、チームを削除する・チームのメンバーを外す・チーム名を変えたとき、ガントチャートとダッシュボードが落ちず、`全員`(絞り込みなし)に戻ること。
3. 保存済みのビューのチームが今の名簿にないとき、`●` が出ないこと。メンバーとチームの両方があるファイルの扱い。
4. `全プロジェクト`をオンにしたとき、チームの絞り込みが同名のメンバーに効くこと。
5. 兼務の人が複数のチームに入っているとき、`チーム別`の行が、それぞれのチームで数えること。

---

## File Structure

- Create: `src/projectapp/scope.py` — プルダウンの値の読み書き(メンバーかチームか)
- Modify: `src/projectapp/teams.py` — `teams_with_members`・`team_scope`
- Modify: `src/projectapp/filtering.py`・`src/projectapp/gantt.py` — ガントチャートの絞り込み
- Modify: `src/projectapp/dashboard.py` — 集計の絞り込みを集合に一般化、`by_team`、`Dashboard.team_name`・`teams`
- Modify: `src/projectapp/dashboard_views.py`・`src/projectapp/views.py`・`src/projectapp/dashboard_view.py` — ビューの保存、画面の状態、プルダウン、`チーム別`の行
- Test: `test/test_scope.py`(新規)・`test/test_teams.py`・`test/test_filtering.py`・`test/test_gantt.py`・`test/test_dashboard.py`・`test/test_dashboard_views.py`・`test/test_dashboard_view.py`・`test/test_views.py`
- Modify: `CLAUDE.md`・`docs/development.md`・`docs/request-history.md`

---

### Task 1: 選択の読み書き(`scope.py`)と `teams.py` の補助

**Files:**
- Create: `src/projectapp/scope.py`
- Modify: `src/projectapp/teams.py`
- Test: `test/test_scope.py`、`test/test_teams.py`

**Interfaces:**
- Produces(`scope.py`):
  - `ALL = ""`、`TEAM_KEY = "\x1fteam:"`
  - `team_key(name: str) -> str`
  - `read_scope(value: str | None) -> tuple[str | None, str | None]`(`(メンバー名, チーム名)`。どちらか一方だけ入る。`全員`・空は `(None, None)`)
  - `scope_value(member: str | None, team: str | None) -> str`
  - `scope_options(all_label: str, members: Sequence[str], teams: Sequence[str]) -> dict[str, str]`
- Produces(`teams.py`):
  - `teams_with_members(project: Project) -> list[str]`(メンバーがいるチームの名前。チームの並び順)
  - `team_scope(project: Project, team: str | None) -> frozenset[str] | None`(チーム名 → 所属するメンバー名の集合。`None`・存在しない・メンバーがいないチームは `None`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_scope.py`:

```python
from projectapp.scope import ALL, TEAM_KEY, read_scope, scope_options, scope_value, team_key


def test_a_member_name_is_its_own_value() -> None:
    assert read_scope("田中") == ("田中", None)
    assert scope_value("田中", None) == "田中"


def test_everyone_is_the_empty_value() -> None:
    assert ALL == ""
    assert read_scope("") == (None, None)
    assert read_scope(None) == (None, None)
    assert scope_value(None, None) == ""


def test_a_team_value_carries_the_prefix_and_round_trips() -> None:
    assert team_key("開発").startswith(TEAM_KEY)
    assert read_scope(team_key("開発")) == (None, "開発")
    assert scope_value(None, "開発") == team_key("開発")


def test_a_member_named_like_a_team_label_is_still_a_member() -> None:
    assert read_scope("チーム: 開発") == ("チーム: 開発", None)


def test_the_team_wins_when_both_are_given() -> None:
    assert scope_value("田中", "開発") == team_key("開発")


def test_an_empty_team_name_means_everyone() -> None:
    assert read_scope(TEAM_KEY) == (None, None)


def test_options_list_everyone_then_members_then_labelled_teams() -> None:
    options = scope_options("全員", ["田中", "鈴木"], ["開発"])
    assert list(options.items()) == [("", "全員"), ("田中", "田中"), ("鈴木", "鈴木"), (team_key("開発"), "チーム: 開発")]


def test_options_without_teams_are_the_member_list_only() -> None:
    assert scope_options("すべての担当者", ["田中"], []) == {"": "すべての担当者", "田中": "田中"}
```

`test/test_teams.py` の末尾に足す(import に `teams_with_members`・`team_scope` を足す)。

```python
def test_teams_with_members_skips_empty_teams_in_team_order() -> None:
    project = Project(
        "p",
        teams=[Team("空", id="c"), Team("開発", id="a"), Team("QA", id="b")],
        members=[Member("甲", teams=ms(("b", 100))), Member("乙", teams=ms(("a", 50), ("b", 50)))],
    )
    assert teams_with_members(project) == ["開発", "QA"]


def test_team_scope_is_the_set_of_member_names() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="a"), Team("空", id="c")],
        members=[Member("甲", teams=ms(("a", 100))), Member("乙")],
    )
    assert team_scope(project, "開発") == frozenset({"甲"})


def test_team_scope_is_none_for_unknown_empty_or_missing() -> None:
    project = Project("p", teams=[Team("空", id="c")], members=[Member("甲")])
    assert team_scope(project, "空") is None
    assert team_scope(project, "ない") is None
    assert team_scope(project, None) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_scope.py test/test_teams.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.scope`、`ImportError: teams_with_members`)。

- [ ] **Step 3: 実装する**

`src/projectapp/scope.py`:

```python
"""メンバー・チームの絞り込みの選択肢。ガントチャートとダッシュボードのプルダウンが共有する。NiceGUI に依存しない。"""

from collections.abc import Sequence

ALL = ""  # `全員`・`すべての担当者`の値。メンバー名は空にできない
TEAM_KEY = "\x1fteam:"  # チームの値の接頭辞。制御文字なので、メンバー名とぶつからない


def team_key(name: str) -> str:
    return f"{TEAM_KEY}{name}"


def read_scope(value: str | None) -> tuple[str | None, str | None]:
    """プルダウンの値 → (メンバー名, チーム名)。どちらか一方だけ入る。`全員`・空は (None, None)。"""
    if not value:
        return None, None
    if value.startswith(TEAM_KEY):
        return None, value[len(TEAM_KEY) :] or None
    return value, None


def scope_value(member: str | None, team: str | None) -> str:
    """(メンバー名, チーム名) → プルダウンの値。両方あるときはチーム。"""
    if team:
        return team_key(team)
    return member or ALL


def scope_options(all_label: str, members: Sequence[str], teams: Sequence[str]) -> dict[str, str]:
    """プルダウンの選択肢。`全員`、メンバー、`チーム: 名前` の順。"""
    options = {ALL: all_label}
    options.update({name: name for name in members})
    options.update({team_key(name): f"チーム: {name}" for name in teams})
    return options
```

`src/projectapp/teams.py` の `team_member_names` の次に足す。

```python
def teams_with_members(project: Project) -> list[str]:
    """メンバーがいるチームの名前(チームの並び順)。絞り込みの選択肢に出す。"""
    return [t.name for t in project.teams if team_member_names(project.members, t.id)]


def team_scope(project: Project, team: str | None) -> frozenset[str] | None:
    """チーム名 → 所属するメンバー名の集合。None・存在しない・メンバーがいないチームは None(絞り込まない)。"""
    if team is None:
        return None
    for entry in project.teams:
        if entry.name == team:
            names = team_member_names(project.members, entry.id)
            return frozenset(names) if names else None
    return None
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_scope.py test/test_teams.py -q`
Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/scope.py src/projectapp/teams.py test/test_scope.py test/test_teams.py
git commit -m "feat: メンバー・チームの絞り込みの選択の読み書きを足す(要望 85 段階 2)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ガントチャートの絞り込み

**Files:**
- Modify: `src/projectapp/filtering.py`
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_filtering.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: Task 1 の `read_scope`・`scope_value`・`scope_options`・`teams_with_members`・`team_scope`。
- Produces: `TaskFilter.team: str | None = None`、`TaskFilter.team_members: frozenset[str] = frozenset()`。`active` と `matches` がチームを見る。ガントチャートの担当者のプルダウン(`assignee-filter`)に `チーム: 名前` が並び、選ぶとチームの絞り込みになる。

- [ ] **Step 1: 失敗するテストを書く(filtering)**

`test/test_filtering.py` の末尾に足す(`Assignee`・`Task`・`TaskFilter`・`matches` は import 済み)。

```python
def test_a_team_filter_keeps_tasks_any_member_is_on() -> None:
    team_filter = TaskFilter(team="開発", team_members=frozenset({"田中", "鈴木"}))
    assert matches(Task("設計", assignees=[Assignee("田中")]), team_filter)
    assert matches(Task("共同", assignees=[Assignee("佐藤"), Assignee("鈴木")]), team_filter)  # 共同タスクは丸ごと
    assert not matches(Task("別", assignees=[Assignee("佐藤")]), team_filter)
    assert not matches(Task("担当なし"), team_filter)


def test_a_team_filter_is_active_and_combines_with_the_query() -> None:
    team_filter = TaskFilter(query="設", team="開発", team_members=frozenset({"田中"}))
    assert team_filter.active
    assert matches(Task("設計", assignees=[Assignee("田中")]), team_filter)
    assert not matches(Task("実装", assignees=[Assignee("田中")]), team_filter)


def test_no_team_means_nobody_is_excluded_by_team() -> None:
    assert not TaskFilter().active
    assert matches(Task("設計"), TaskFilter(team_members=frozenset({"田中"})))  # team が None なら見ない
```

- [ ] **Step 2: 失敗するテストを書く(gantt)**

`test/test_gantt.py` の末尾に足す(`Membership`・`Team` を `projectapp.models` の import に足す)。

```python
from projectapp.scope import team_key


def teamed_project() -> Project:
    project = filter_project()
    project.teams = [Team("開発", id="a"), Team("空", id="z")]
    project.members = [Member("田中", teams=[Membership("a", 100)]), Member("鈴木")]
    return project


async def test_the_assignee_select_lists_teams_that_have_members_and_filters_by_team(user: User) -> None:
    mount_chart(teamed_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    assert select.options == {
        "": "すべての担当者",
        "田中": "田中",
        "鈴木": "鈴木",
        team_key("開発"): "チーム: 開発",
    }  # メンバーのいない「空」は出ない
    select.set_value(team_key("開発"))
    await user.should_see(marker="task-top-0")  # 田中の調査
    await user.should_see(marker="task-0-0")  # 田中の設計
    await user.should_not_see(marker="task-0-1")  # 鈴木の実装
    select.set_value("")
    await user.should_see(marker="task-0-1")


async def test_choosing_a_member_after_a_team_replaces_the_team_filter(user: User) -> None:
    charts, _ = mount_chart(teamed_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value(team_key("開発"))
    select.set_value("鈴木")
    assert charts[0].task_filter.assignee == "鈴木" and charts[0].task_filter.team is None
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")


async def test_set_project_drops_a_team_that_lost_its_members(user: User) -> None:
    charts, _ = mount_chart(teamed_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value(team_key("開発"))
    other = teamed_project()
    other.members = [Member("田中"), Member("鈴木")]  # 開発のメンバーがいなくなった
    charts[0].set_project(other)
    assert charts[0].task_filter.team is None and charts[0].task_filter.team_members == frozenset()
    assert select.value == ""
    assert team_key("開発") not in select.options


async def test_set_project_follows_a_roster_change_of_the_chosen_team(user: User) -> None:
    charts, _ = mount_chart(teamed_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value(team_key("開発"))
    other = teamed_project()
    other.members = [Member("田中"), Member("鈴木", teams=[Membership("a", 100)])]  # 田中が外れ、鈴木が入った
    charts[0].set_project(other)
    assert charts[0].task_filter.team == "開発"
    assert charts[0].task_filter.team_members == frozenset({"鈴木"})
    assert select.value == team_key("開発")
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_filtering.py test/test_gantt.py -k "team" -q`
Expected: FAIL。

- [ ] **Step 4: 実装する**

`src/projectapp/filtering.py`:

```python
@dataclass(frozen=True)
class TaskFilter:
    query: str = ""  # タスク名への部分一致(大文字小文字を区別しない)
    assignee: str | None = None  # None なら全員
    exclude: frozenset[str] = frozenset()  # 描かないタスクの id(画像の書き出しで、チェックを外したものを除く)
    team: str | None = None  # 絞り込み中のチーム名。assignee とは同時に使わない
    team_members: frozenset[str] = frozenset()  # そのチームのメンバー名(名簿が変わったら gantt が更新する)

    @property
    def active(self) -> bool:
        return bool(self.query.strip()) or self.assignee is not None or self.team is not None or bool(self.exclude)
```

`matches` の `own = (...)` を直す。

```python
    own = (
        (task_filter.assignee is None or task_filter.assignee in task.assignee_names)
        and (task_filter.team is None or not task_filter.team_members.isdisjoint(task.assignee_names))
        and (task_filter.query.strip().casefold() in task.name.casefold())
    )
```

`src/projectapp/gantt.py`:

1. import に `from projectapp.scope import read_scope, scope_options, scope_value` と `from projectapp.teams import team_scope, teams_with_members` を足す。
2. `set_project` の、担当者がいなくなったときの処理を直す。

```python
        names = {member.name for member in project.members}
        if self.task_filter.assignee not in (None, *names):
            self.task_filter = replace(self.task_filter, assignee=None)
        if self.task_filter.team is not None:  # チームの絞り込みは、名簿の変更に追従し、消えたら外す
            members = team_scope(project, self.task_filter.team)
            if members is None:
                self.task_filter = replace(self.task_filter, team=None, team_members=frozenset())
            elif members != self.task_filter.team_members:
                self.task_filter = replace(self.task_filter, team_members=members)
```

3. `assignee_options` を置き換える。

```python
    def assignee_options(self) -> dict[str, str]:
        return scope_options(
            "すべての担当者", [member.name for member in self.project.members], teams_with_members(self.project)
        )
```

4. `sync_assignee_select` の `value = self.task_filter.assignee or ALL_ASSIGNEES` を `value = scope_value(self.task_filter.assignee, self.task_filter.team)` にする。
5. プルダウンを作る箇所(`self.assignee_select = (ui.select(self.assignee_options(), value=..., on_change=...))`)を直す。`value=` を `scope_value(self.task_filter.assignee, self.task_filter.team)` にし、`on_change` を `self.on_assignee_filter` にする。メソッドを `assignee_options` の前に足す。

```python
    def on_assignee_filter(self, value: str | None) -> None:
        """担当者のプルダウンの選択。メンバーかチームのどちらか一方だけを絞り込みに入れる。"""
        member, team = read_scope(value)
        members = team_scope(self.project, team)
        if members is None:
            team = None  # 消えた・メンバーのいないチームは、絞り込まない
        self.set_filter(
            replace(self.task_filter, assignee=member, team=team, team_members=members or frozenset())
        )
```

   ラムダは `on_change=lambda e: self.on_assignee_filter(e.value)` とする。
6. `ALL_ASSIGNEES` はそのまま残す(`reset_filter` が使う)。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_filtering.py test/test_gantt.py -q`
Expected: PASS(既存の `assignee-filter` のテストも通る)。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/filtering.py src/projectapp/gantt.py test/test_filtering.py test/test_gantt.py
git commit -m "feat: ガントチャートの担当者の絞り込みにチームを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ダッシュボードの集計(`dashboard.py`)

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: Task 1 の `team_scope`・`teams_with_members`。
- Produces:
  - `Scope = str | frozenset[str] | None`。`_tasks`・`summarize_progress`・`summarize_loads`・`summarize_cross_loads`・`summarize_workload`・`summarize_due`・`summarize_backlog`・`summarize_team_progress` の `member` 引数が `Scope` を受ける(文字列は 1 人の集合)。
  - `Progress.by_team: list[MemberProgress]`(`全員`のときだけ。メンバーのいるチームごと)。
  - `summarize_team_rows(project: Project) -> list[MemberProgress]`。
  - `Dashboard.team_name: str | None = None`、`Dashboard.teams: list[str]`(プルダウンに出すチーム名)。
  - `summarize(project, period, now, holidays, kind=PeriodKind.ALL, member=None, team=None)`。`member` があれば `team` は無視する。`team` が存在しない・メンバーがいないときは絞り込まない(`team_name` は `None`)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の末尾に足す。`Membership`・`Team` を `projectapp.models` の import に足し、`summarize_team_rows` を `projectapp.dashboard` の import に足す。`dated` は既存のヘルパー(`dated("名前", 開始日, 終了日, assignees=[...])`)で、使い方は 640 行付近の既存テストにある。

```python
def teamed_project() -> Project:
    members = [
        Member("田中", 1.0, teams=[Membership("a", 100)]),
        Member("佐藤", 1.0, teams=[Membership("a", 60), Membership("b", 40)]),
        Member("鈴木", 1.0, teams=[Membership("b", 100)]),
        Member("山田", 1.0),
    ]
    tasks = [
        Task("田中の", effort_hours=2, status=Status.RUNNING, progress=50, assignees=[Assignee("田中", 1.0)]),
        Task("共同", effort_hours=6, assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)]),
        Task("鈴木の", effort_hours=4, status=Status.DONE, assignees=[Assignee("鈴木", 1.0)]),
        Task("山田の", effort_hours=1, assignees=[Assignee("山田", 1.0)]),
        Task("担当なし", effort_hours=1),
    ]
    project = project_of(*tasks, members=members)
    project.teams = [Team("開発", id="a"), Team("QA", id="b"), Team("空", id="z")]
    return project


def test_a_set_scope_keeps_tasks_any_of_the_names_is_on() -> None:
    progress = summarize_progress(teamed_project(), {}, NOW, frozenset({"田中", "鈴木"}))
    assert progress.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 1}
    assert progress.by_member == [] and progress.by_team == []  # 絞り込み中は、メンバー別・チーム別を出さない


def test_a_string_scope_still_means_one_member() -> None:
    assert summarize_progress(teamed_project(), {}, NOW, "山田").counts[Status.NOT_STARTED] == 1


def test_summarize_with_a_team_filters_loads_and_workload_to_its_members() -> None:
    data = summarize(teamed_project(), WEEK, NOW, {}, team="開発")
    assert data.team_name == "開発" and data.member is None
    assert list(data.loads) == ["田中", "佐藤"]
    assert [row.name for row in data.workload] == ["田中", "佐藤"]  # 未割り当てを出さない
    assert data.team.tasks[Status.NOT_STARTED] == ["共同"]  # 田中が入る共同タスクだけ(鈴木のだけは入らない)


def test_summarize_lists_the_teams_that_have_members_for_the_dropdown() -> None:
    data = summarize(teamed_project(), WEEK, NOW, {})
    assert data.teams == ["開発", "QA"]  # メンバーのいない「空」は出ない
    assert data.team_name is None


def test_a_member_wins_over_a_team() -> None:
    data = summarize(teamed_project(), WEEK, NOW, {}, member="山田", team="開発")
    assert data.member == "山田" and data.team_name is None
    assert list(data.loads) == ["山田"]


def test_an_unknown_or_empty_team_filters_nothing() -> None:
    everyone = summarize(teamed_project(), WEEK, NOW, {})
    for team in ("ない", "空"):
        data = summarize(teamed_project(), WEEK, NOW, {}, team=team)
        assert data.team_name is None
        assert list(data.loads) == list(everyone.loads)


def test_the_backlog_for_a_team_counts_the_team_members_shares_and_supply() -> None:
    project = teamed_project()
    everyone = summarize(project, WEEK, NOW, {}).backlog
    team = summarize(project, WEEK, NOW, {}, team="開発").backlog
    names = dict(team.by_member)
    assert set(names) <= {"田中", "佐藤"}
    assert team.supply == pytest.approx(2.0)  # 田中と佐藤の相対比率の合計
    assert team.hours < everyone.hours


def test_the_due_rows_for_a_team_only_list_its_tasks() -> None:
    project = teamed_project()
    assert all(
        row.name in {"田中の", "共同"} for row in summarize(project, WEEK, NOW, {}, team="開発").due
    )


def test_the_cross_loads_for_a_name_set_only_include_those_members() -> None:
    project = teamed_project()
    loads = summarize_cross_loads([project], WEEK, {}, frozenset({"田中", "佐藤"}))
    assert list(loads) == ["田中", "佐藤"]


def test_by_team_has_a_row_per_team_with_members_and_counts_shared_tasks_for_each() -> None:
    rows = summarize_team_rows(teamed_project())
    assert [row.name for row in rows] == ["開発", "QA"]
    dev, qa = rows
    assert dev.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 0}
    assert qa.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 0, Status.PAUSED: 0, Status.DONE: 1}  # 共同(鈴木)と鈴木の
    assert dev.percent == pytest.approx(100 / 8)  # 田中の(2h × 50%)と共同(6h × 0%)
    assert qa.percent == pytest.approx(40)  # 共同(6h × 0%)と鈴木の(4h × 100%)


def test_by_team_is_built_for_everyone_only_and_skipped_without_teams() -> None:
    project = teamed_project()
    assert [row.name for row in summarize_progress(project, {}, NOW).by_team] == ["開発", "QA"]
    assert summarize_progress(project, {}, NOW, "田中").by_team == []
    bare = project_of(Task("作業", effort_hours=2))
    assert summarize_team_rows(bare) == [] and summarize_progress(bare, {}, NOW).by_team == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard.py -k "scope or team or cross_loads_for" -q`
Expected: FAIL(`ImportError: cannot import name 'summarize_team_rows'` など)。

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard.py`:

1. import に `from projectapp.teams import team_scope, teams_with_members` を足す。`Scope` と変換関数を、`_tasks` の前に足す。

```python
Scope = str | frozenset[str] | None  # 絞り込み。文字列は 1 人、集合はそのうちの誰か(チーム)。None は全員


def _names(scope: Scope) -> frozenset[str] | None:
    """絞り込みを、メンバー名の集合にする。全員は None。"""
    if scope is None:
        return None
    return frozenset({scope}) if isinstance(scope, str) else scope
```

2. `Progress` に `by_team: list[MemberProgress] = field(default_factory=list)  # チームごと。絞り込み中は空` を足す。
3. `_tasks` を直す。

```python
def _tasks(project: Project, member: Scope = None) -> list[Task]:
    """集計の対象のタスク。まとめは、子の工数・進捗・期限を二重に数えないよう外す。`member`があれば、その人(チームなら誰か)が担当のものだけ。"""
    names = _names(member)
    return [
        task
        for task in project.all_tasks()
        if task.kind not in (TaskKind.SUMMARY, TaskKind.REFERENCE)
        and (names is None or not names.isdisjoint(task.assignee_names))
    ]
```

4. `summarize_member_progress` の次に足す。

```python
def summarize_team_rows(project: Project) -> list[MemberProgress]:
    """チームごとの進捗(メンバーのいるチームだけ)。共同タスクは、担当が所属する全チームの行に数える。"""
    tasks = _tasks(project)
    rows = []
    for name in teams_with_members(project):
        names = team_scope(project, name)
        assert names is not None
        rows.append(_member_row(name, [t for t in tasks if not names.isdisjoint(t.assignee_names)]))
    return rows
```

   (`_member_row` は `MemberProgress` を返す。)
5. `summarize_progress` の末尾を直す。

```python
    by_member = summarize_member_progress(project) if member is None else []
    by_team = summarize_team_rows(project) if member is None else []
    return Progress(weighted / total if total else None, counts, overdue, by_member, by_team)
```

   シグネチャの `member: str | None = None` を `member: Scope = None` にする。
6. 次の関数の `member: str | None` を `member: Scope` にし、判定を集合にする。
   - `summarize_team_progress`・`summarize_due`・`summarize_backlog`・`summarize_workload`・`summarize_loads`・`summarize_cross_loads`・`_member_spans`: 引数の型を `Scope` に。本文の先頭で `names = _names(member)` を取り、`member is None or entry.name == member` を `names is None or entry.name in names` に、`member is None or key == member` を `names is None or key in names`、`member is None or m.name == member` を `names is None or m.name in names`、`member is None or name == member` を `names is None or name in names` に置き換える。`if member is None and (planned[UNASSIGNED] ...)` と `by_member = ... if member is None` は `member is None` のまま(全員のときだけ)。
   - `summarize_backlog` の `split = {name: 0.0 ...}` などで変数 `names` が使われているので、集合の変数名は `scope_names` にする(`names` は既存のメンバー名のリスト)。`summarize_workload` も同様(`names` が既存)。`summarize_cross_loads` は `names = dict.fromkeys(...)` が既存なので `scope_names` にする。
7. `Dashboard` に足す。

```python
    team_name: str | None = None  # 絞り込み中のチーム名。member とは同時に使わない
    teams: list[str] = field(default_factory=list)  # プルダウンの選択肢のチーム(メンバーのいるものだけ)
```

8. `summarize` を直す。

```python
def summarize(
    project: Project,
    period: Period,
    now: datetime,
    holidays: dict[date, str],
    kind: PeriodKind = PeriodKind.ALL,
    member: str | None = None,
    team: str | None = None,
) -> Dashboard:
    team_members = team_scope(project, team) if member is None else None
    scope: Scope = member if member is not None else team_members
    return Dashboard(
        period,
        summarize_progress(project, holidays, now, scope),
        summarize_loads(project, period, holidays, scope),
        summarize_workload(project, period, now, holidays, scope),
        summarize_due(project, period, now, holidays, scope),
        summarize_team_progress(project, None if kind is PeriodKind.ALL else period, now, holidays, scope),
        member,
        [m.name for m in project.members],
        backlog=summarize_backlog(project, period, kind, now, holidays, scope),
        team_name=team if team_members is not None else None,
        teams=teams_with_members(project),
    )
```

   (`Dashboard` のフィールド順: `member` の次が `members`。`team_name`・`teams` はキーワードで渡すので順序は問わない。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard.py test/test_dashboard_backlog.py -q`
Expected: PASS(文字列の `member` を渡す既存のテストも通る)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: ダッシュボードの集計で、メンバーの絞り込みをチーム(集合)に一般化する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ビューの保存と画面の状態(`dashboard_views.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/dashboard_views.py`
- Modify: `src/projectapp/views.py`
- Test: `test/test_dashboard_views.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 3 の `summarize(..., team=)`・`Dashboard.team_name`・`Dashboard.teams`。Task 1 の `teams_with_members`。
- Produces:
  - `ViewSpec.team: str | None = None`(`custom` のあと)。`views_to_config` が `"team"` を書き、`views_from_config` が読む(文字列でない・空は `None`)。
  - `resolve_team(team: str | None, names: Iterable[str]) -> str | None`。
  - `MainView.dashboard_team: str | None`、`MainView.change_dashboard_team(name: str | None) -> None`。`change_dashboard_member` は `dashboard_team` を `None` に、`change_dashboard_team` は `dashboard_member` を `None` にする。`working_spec` が `team` を持つ。`dashboard_dirty` が、保存したチームが今の名簿にないときは全員とみなす。`apply_dashboard_view` が `team` を取り込む(メンバーがあればメンバー優先)。`refresh_dashboard` が、名簿にないチームを `None` に戻す。全プロジェクトのときは、チームのメンバー名で絞る。

- [ ] **Step 1: 失敗するテストを書く(dashboard_views)**

`test/test_dashboard_views.py` の既存の `views_to_config`・`views_from_config` のテストの書き方に合わせて、次を足す(`ViewSpec` の組み立ては既存のテストの helper に合わせる。ここでは `spec(...)` という既存の helper がないものとして直接組み立てる)。

```python
def test_team_round_trips_through_the_config() -> None:
    spec = ViewSpec("開発ビュー", PeriodKind.WEEK, None, False, DEFAULT_ORDER, team="開発")
    [loaded] = views_from_config(views_to_config([spec]))
    assert loaded.team == "開発" and loaded.member is None


def test_a_view_without_team_reads_as_no_team() -> None:
    raw = [{"name": "旧", "period": "week", "member": None, "cross": False, "cards": [c.value for c in DEFAULT_ORDER]}]
    [loaded] = views_from_config(raw)
    assert loaded.team is None


def test_a_non_string_or_empty_team_reads_as_no_team() -> None:
    base = {"name": "x", "period": "week", "member": None, "cross": False, "cards": [c.value for c in DEFAULT_ORDER]}
    for bad in (3, "", None, ["開発"]):
        [loaded] = views_from_config([{**base, "team": bad}])
        assert loaded.team is None


def test_resolve_team_returns_none_for_a_team_that_left_the_roster() -> None:
    assert resolve_team("開発", ["開発", "QA"]) == "開発"
    assert resolve_team("消えた", ["開発"]) is None
    assert resolve_team(None, ["開発"]) is None
```

   `PeriodKind` の値の文字列(`"week"` など)は、既存の `views_to_config` のテストの期待値に合わせる(`PeriodKind.WEEK.value`)。`resolve_team`・`ViewSpec`・`DEFAULT_ORDER` を import に足す。

- [ ] **Step 2: 失敗するテストを書く(画面)**

`test/test_views.py` の末尾に足す。ダッシュボードを開く既存のテストの書き方(`open_dashboard` 相当の helper。`grep -n "dashboard-member" test/test_views.py` で見つかる)に合わせて、`view.project` にチームを入れてから、ダッシュボードを開く。

```python
async def open_team_dashboard(user: User, tmp_path: Path) -> MainView:
    view = await open_members_view(user, tmp_path)
    view.project.teams = [Team("開発", id="t1")]
    view.project.members = [Member("甲", 1.0, id="m1", teams=[Membership("t1", 100)]), Member("乙", 1.0, id="m2")]
    view.project.tasks = [Task("甲の", assignees=[Assignee("甲", 1.0)]), Task("乙の", assignees=[Assignee("乙", 1.0)])]
    view.mark_clean()
    with view.client:
        view.open_dashboard()
    await user.should_see(marker="dashboard-member")
    return view


async def test_the_dashboard_dropdown_lists_teams_and_choosing_one_filters(user: User, tmp_path: Path) -> None:
    view = await open_team_dashboard(user, tmp_path)
    select = user.find(marker="dashboard-member").elements.pop()
    assert team_key("開発") in select.options and select.options[team_key("開発")] == "チーム: 開発"
    with view.client:
        select.set_value(team_key("開発"))
    assert await wait_until(lambda: view.dashboard_team == "開発")
    assert view.dashboard_member is None
    assert await wait_until(lambda: "開発" in user.find(marker="dashboard-team-scope").elements.pop().text)


async def test_choosing_a_member_after_a_team_clears_the_team(user: User, tmp_path: Path) -> None:
    view = await open_team_dashboard(user, tmp_path)
    select = user.find(marker="dashboard-member").elements.pop()
    with view.client:
        select.set_value(team_key("開発"))
    assert await wait_until(lambda: view.dashboard_team == "開発")
    with view.client:
        select.set_value("乙")
    assert await wait_until(lambda: view.dashboard_member == "乙")
    assert view.dashboard_team is None


async def test_a_team_that_vanished_from_the_roster_returns_to_everyone(user: User, tmp_path: Path) -> None:
    view = await open_team_dashboard(user, tmp_path)
    with view.client:
        view.change_dashboard_team("開発")
    view.project.members[0].teams = []  # 開発のメンバーがいなくなった
    with view.client:
        view.refresh_dashboard()
    assert view.dashboard_team is None


async def test_the_working_view_carries_the_team_and_a_vanished_saved_team_is_not_dirty(
    user: User, tmp_path: Path
) -> None:
    view = await open_team_dashboard(user, tmp_path)
    with view.client:
        view.change_dashboard_team("開発")
    assert view.working_spec("x").team == "開発" and view.working_spec("x").member is None
    saved = ViewSpec("保存済み", PeriodKind.WEEK, None, False, DEFAULT_ORDER, team="消えたチーム")
    view.dashboard_views = [saved]
    with view.client:
        view.apply_dashboard_view(saved)
        view.refresh_dashboard()  # 名簿にないチームは全員に戻る
    assert view.dashboard_team is None
    assert not view.dashboard_dirty()  # 戻しただけでは ● を出さない


async def test_a_view_with_both_member_and_team_uses_the_member(user: User, tmp_path: Path) -> None:
    view = await open_team_dashboard(user, tmp_path)
    with view.client:
        view.apply_dashboard_view(ViewSpec("両方", PeriodKind.WEEK, "乙", False, DEFAULT_ORDER, team="開発"))
    assert view.dashboard_member == "乙" and view.dashboard_team is None
```

   import に `team_key`(`projectapp.scope`)・`ViewSpec`・`DEFAULT_ORDER`(`projectapp.dashboard_views`)・`PeriodKind` を足す(未 import のものだけ)。`MainView` の「ダッシュボードを開く」メソッドの実際の名前は `grep -n "def open_dashboard\|def show_dashboard" src/projectapp/views.py` で確かめ、テストの `open_dashboard()` を合わせる。

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_views.py -k "team" -q; uv run pytest test/test_views.py -k "team and dashboard" -q`
Expected: FAIL。

- [ ] **Step 4: `dashboard_views.py` を実装する**

1. `ViewSpec` に足す。

```python
    team: str | None = None  # 絞り込み中のチーム名(メンバーとは同時に使わない。メンバーがあればメンバー優先)
```

2. `resolve_member` の次に足す。

```python
def resolve_team(team: str | None, names: Iterable[str]) -> str | None:
    """保存したチームが今の名簿にいなければ(メンバーのいるチームの名前になければ)、全員(None)。"""
    return team if team is not None and team in set(names) else None
```

3. `views_to_config` の `entry` に `"team": spec.team,` を足す(`"member"` の次)。
4. `views_from_config` が 1 件を読む関数(`ViewSpec(name, period, member if ..., cross if ..., normalize_cards(...), custom)` を返すところ)を直す。

```python
    team = raw.get("team")
    return ViewSpec(
        name,
        period,
        member if isinstance(member, str) and member else None,
        cross if isinstance(cross, bool) else False,
        normalize_cards(raw.get("cards")),
        custom,
        team if isinstance(team, str) and team else None,
    )
```

- [ ] **Step 5: `views.py` を実装する**

1. import の `from projectapp.dashboard_views import (...)` に `resolve_team` を足し、`from projectapp.scope import ...` は不要(プルダウンの値の読み書きは `dashboard_view.py` が行う)。`from projectapp.teams import removal_impacts, replace_teams` を `from projectapp.teams import removal_impacts, replace_teams, team_scope, teams_with_members` にする。
2. `self.dashboard_member: str | None = None` の次の行に足す。

```python
        self.dashboard_team: str | None = None  # ダッシュボードで絞り込み中のチーム名。メンバーとは同時に使わない。保存しない
```

3. `refresh_dashboard` の、メンバーを名簿に戻す処理の次に足し、`summarize(...)` と `summarize_cross_loads(...)` を直す。

```python
        team_names = teams_with_members(self.project)
        if self.dashboard_team not in (None, *team_names) or self.dashboard_member is not None:
            self.dashboard_team = None  # 消えたチームは全員に戻す。メンバーを選んでいるときはチームを使わない
        scope = self.dashboard_scope()
        data = summarize(
            self.project, period, now, self.holidays, self.dashboard_kind, self.dashboard_member, self.dashboard_team
        )
        if self.dashboard_cross:
            chosen = [p for p in projects if p.name not in self.dashboard_excluded]
            loads = summarize_cross_loads(chosen, period, self.base_holidays, scope)
```

   `scope` を作る小さなメソッドを `refresh_dashboard` の前に足す(全プロジェクトのとき、チームのメンバー名を同名の人に当てる)。

```python
    def dashboard_scope(self) -> str | frozenset[str] | None:
        """集計の絞り込み。メンバーがあればその人、チームならそのメンバー名の集合(開いているプロジェクトの名簿)。"""
        if self.dashboard_member is not None:
            return self.dashboard_member
        return team_scope(self.project, self.dashboard_team)
```

   既存の `data = summarize(self.project, period, now, self.holidays, self.dashboard_kind, self.dashboard_member)` と `loads = summarize_cross_loads(chosen, period, self.base_holidays, self.dashboard_member)` は、上のコードに置き換える。
4. `change_dashboard_member` を直し、`change_dashboard_team` を足す。

```python
    def change_dashboard_member(self, name: str | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_member = name
        self.dashboard_team = None  # メンバーとチームは、どちらか一方
        self.refresh_dashboard()

    def change_dashboard_team(self, name: str | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_team = name
        self.dashboard_member = None
        self.refresh_dashboard()
```

5. `working_spec` の `ViewSpec(...)` の末尾に `self.dashboard_team` を足す(`custom` のあと)。
6. `dashboard_dirty` を直す。

```python
        saved = replace(
            saved,
            member=resolve_member(saved.member, self.dashboard_names),
            team=resolve_team(saved.team, teams_with_members(self.project)),
        )
```

   保存したメンバーとチームの両方があるときは、メンバーが優先なので、`apply_dashboard_view` と同じ正規化を `dashboard_dirty` でも行う: 上の `replace` のあとに足す。

```python
        if saved.member is not None:
            saved = replace(saved, team=None)
```

7. `apply_dashboard_view` の `self.dashboard_member = spec.member` の次に足す。

```python
        self.dashboard_team = None if spec.member is not None else spec.team
```

8. `DashboardView(...)` の呼び出しに、`self.change_dashboard_member,` の次の引数として `on_team_change=self.change_dashboard_team` を足す。位置引数の並びが `on_member_change`、`on_cross_change`、… なので、キーワードで渡す。`DashboardView(...)` 呼び出しの末尾の `actions=...` の前に `on_team_change=self.change_dashboard_team,` を置く。

- [ ] **Step 6: `dashboard_view.py` を実装する(プルダウン・表示・`チーム別`)**

1. import に `from projectapp.scope import ALL, read_scope, scope_options, scope_value` を足す。`ALL_MEMBERS = ""` の定義は残し、`ALL_MEMBERS = ALL` にする(値は同じ)。
2. `DashboardView.__init__` の引数に `on_team_change: Callable[[str | None], object] | None = None,` を `on_custom_change` の次に足し、`self.on_team_change = on_team_change` を `self.on_custom_change = on_custom_change` の次に足す。
3. `on_member` を直す。

```python
    def on_member(self, event: ValueChangeEventArguments) -> None:
        if self.syncing:
            return
        member, team = read_scope(event.value)
        if team is not None:
            if self.on_team_change is not None:
                self.on_team_change(team)
        elif self.on_member_change is not None:
            self.on_member_change(member)
```

4. プルダウンの選択肢を更新する箇所を直す。

```python
        if self.member_select is not None:
            options = scope_options("全員", data.members, data.teams)
            self.syncing = True
            try:
                self.member_select.set_options(options, value=scope_value(data.member, data.team_name))
            finally:
                self.syncing = False
```

5. `team_card` の `if data.member: scope = f"{data.member}・{scope}"` を直す。

```python
            if data.member:
                scope = f"{data.member}・{scope}"
            elif data.team_name:
                scope = f"チーム「{data.team_name}」・{scope}"
```

6. `progress_card` の`メンバー別`の次に`チーム別`を足す。

```python
            if progress.by_team:
                ui.label("チーム別").classes("text-subtitle2")
                for row in progress.by_team:
                    self.member_progress_row(row)
```

   `member_progress_row(row)` のマーカーは `dashboard-member-progress-{row.name}` で、メンバー名とチーム名が同じとき重なる。`member_progress_row` に `marker: str = "dashboard-member"` 引数を足し、チーム別では `marker="dashboard-team-row"` を渡す(中のマーカーは `f"{marker}-progress-{row.name}"` と `f"{marker}-icon-{row.name}"`。チーム別では `avatar` を出さないよう、`icons` に名前がなければ頭文字になる既存の動作に任せる)。既存のマーカー `dashboard-member-progress-…`・`dashboard-member-icon-…` は変えない。

- [ ] **Step 7: `dashboard_view` の表示のテストを足す**

`test/test_dashboard_view.py` に、既存の `DashboardView` を直接組み立てるテストの書き方に合わせて足す。

```python
async def test_the_team_row_and_dropdown_show_for_everyone(user: User) -> None:
    project = teamed_dashboard_project()  # 下の helper
    data = summarize(project, WEEK, NOW, {})
    calls: list[tuple[str, str | None]] = []
    mount_view(data, on_member=lambda n: calls.append(("member", n)), on_team=lambda n: calls.append(("team", n)))
    await user.open("/")
    select = user.find(marker="dashboard-member").elements.pop()
    assert team_key("開発") in select.options
    await user.should_see(marker="dashboard-member-progress-田中")
    await user.should_see(marker="dashboard-team-row-progress-開発")  # チーム別の行
    select.set_value(team_key("開発"))
    assert calls == [("team", "開発")]
    select.set_value("田中")
    assert calls[-1] == ("member", "田中")
```

   `teamed_dashboard_project`・`mount_view`・`WEEK`・`NOW` は、`test_dashboard_view.py` の既存の helper に合わせて作る(`grep -n "^def \|^async def " test/test_dashboard_view.py | head -20` で既存の組み立て方を見る。`mount_view` が `on_team` を受けない場合は、`DashboardView(..., on_team_change=...)` を渡すように helper を直す)。

- [ ] **Step 8: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_views.py test/test_dashboard_view.py test/test_views.py test/test_dashboard.py -q -n auto`
Expected: PASS。

- [ ] **Step 9: コミット**

```bash
git add src/projectapp/dashboard_views.py src/projectapp/views.py src/projectapp/dashboard_view.py test/test_dashboard_views.py test/test_dashboard_view.py test/test_views.py
git commit -m "feat: ダッシュボードのプルダウンにチームを足し、ビューに保存する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 仕様書・記録・全体の確認

**Files:**
- Modify: `CLAUDE.md`、`docs/development.md`、`docs/request-history.md`、`docs/superpowers/specs/2026-10-30-teams-design.md`

- [ ] **Step 1: `CLAUDE.md` を直す**

1. 段階 1 で足した`チーム`の項目の末尾「絞り込みと集計への利用は後続機能(要望 85 の段階 2・3)」を「ガントチャートとダッシュボードの絞り込みに使える(下記)。集計の按分は後続機能(要望 85 の段階 3)」に直す。
2. 「ガントチャート」の、`ガントチャート`の表示は…「一人担当に注目するフォーカスや、検索による絞り込み」の項目の近く、またはメンバーの項目の次に足す。

```
- ガントチャートの担当者のプルダウン(`すべての担当者`)に、メンバーのほかに`チーム: 名前`(所属するメンバーがいるチームだけ)を並べる。チームを選ぶと、そのチームのメンバーが担当に入っているタスクだけを出す(共同タスクは丸ごと。担当なしは出さない)。メンバーとチームは同時に選べない。名簿が変わると追従し、チームが消えた(メンバーがいなくなった)ら外す。保存しない
```

3. 「ダッシュボード」の、メンバーのプルダウンの項目(「期間の横のプルダウンで、`全員`かメンバー 1 人を選べる…」)に足す。

```
プルダウンには`チーム: 名前`(所属するメンバーがいるチームだけ)も並ぶ。チームを選ぶと、全カードがそのチームのメンバーのだれかが担当に入っているタスクだけになり(共同タスクは丸ごと)、負荷と工数はそのチームのメンバーの行だけになる(値はメンバーのまま。所属の割合による按分は後続)。メンバーとチームはどちらか一方。`全員`のときは、`進捗と遅れ`に`チーム別`の行(名前・進捗率・件数。メンバーのいるチームだけ。共同タスクは、担当が所属する全チームの行に数える。期間には影響されない)を、`メンバー別`の隣に出す。全プロジェクトを重ねるときは、開いているプロジェクトのチームのメンバー名を、同名のメンバーに当てて絞る
```

4. 「ビュー」の項目(「期間・メンバー・`全プロジェクト`・カードの出し入れと順を、名前を付けた「ビュー」として…」)の「メンバー」の後に「・チーム(名前で保存)」を足し、「保存したメンバーが今の名簿にいないときは、画面だけ`全員`に戻す」を「保存したメンバー・チームが今の名簿にいないときは…」に直し、「メンバーとチームの両方が書かれていればメンバーを優先する」を足す。
5. 「データの保存先」の`dashboard_views` の記述がある箇所に「(チームは `team`)」を足す。

- [ ] **Step 2: `docs/development.md`・記録を直す**

`docs/development.md` のモジュール表に足す。

```
| `scope.py` | メンバー・チームの絞り込みのプルダウンの値(要望 85 段階 2)。`read_scope`・`scope_value`・`scope_options`・`team_key`(チームの値は制御文字の接頭辞 `TEAM_KEY` つき)。ガントチャートとダッシュボードが共有する。NiceGUI に依存しない |
```

ファイル形式の注意の、段階 1 で足したチームの項目の末尾「段階 2・3(絞り込み・集計)は未実装。」を「段階 2(絞り込み)は実装済み: `TaskFilter.team`・`team_members`、`dashboard.Scope`(文字列 = 1 人、集合 = チーム)、`ViewSpec.team`(`config.json` の `dashboard_views[].team`)。段階 3(集計の按分)は未実装。」に直す。

`docs/request-history.md` の要望 85 の行の状態を「段階 1・2 実装済み(PR 前)。段階 3(集計の按分)は未着手」にし、計画の列に`[計画(段階 2)](superpowers/plans/2026-10-30-teams-stage2.md)`を足す。`docs/superpowers/specs/2026-10-30-teams-design.md` の状態に「段階 2 の計画 `plans/2026-10-30-teams-stage2.md`」を足す。`docs/hidden-requests.md`(git 管理外)の要望 85 の行も同じ状態に直す。

- [ ] **Step 3: 全体のテストと型を通す**

Run: `uv run pytest -q -n auto 2>&1 | tail -5`
Expected: すべて PASS。

Run: `uv run ty check src`
Expected: エラーなし。

- [ ] **Step 4: 実機で確かめる項目を整理する(コミットはしない)**

`uv run projectapp` で、次を確かめて結果を報告する。

1. チームを 2 つ作り、メンバーを所属させる(兼務の人を 1 人入れる)。
2. ガントチャートの担当者のプルダウンに`チーム: …`が並び、選ぶとそのチームのメンバーが担当のタスクだけになる。メンバーを選ぶとチームの絞り込みは外れる。
3. ダッシュボードのプルダウンで、チームを選ぶと全カードが絞られ、`チーム別`の行が`全員`のときだけ出る。
4. ビューに保存して、アプリを開き直しても同じチームで開く。チームを削除したあとにそのビューを開くと、`全員`に戻り、`●` は出ない。
5. `全プロジェクト`をオンにして、チームを選んでも落ちない。

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md docs/development.md docs/request-history.md docs/superpowers/specs/2026-10-30-teams-design.md
git commit -m "docs: チームの絞り込み(要望 85 段階 2)の仕様と記録を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
