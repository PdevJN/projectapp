# チーム 段階 3(集計の按分) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードで、チームを選んだときの`人ごとの負荷`・`工数の予定と実績`・`残りの工数と必要人数`を、メンバーの所属の割合で按分し、`全員`のときは`残りの工数と必要人数`に`チーム別`の行を出す(要望 85 の段階 3)。

**Architecture:** `dashboard.Scope` に「`{メンバー名: 重み}`の辞書」を加える。チームを選ぶと `teams.team_weights` が `{名前: 所属の割合 / 100}` を作って渡し、各集計がメンバーの値に重みを掛ける。メンバーを選んだとき・全員のときは重み 1.0 と同じで、結果は変わらない。`チーム別`は、メンバーごとの残りの工数を所属の割合で配って作る。ファイル形式は変えない(version 17 のまま)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)。型は `uv run ty check src`。

**Spec:** [`docs/superpowers/specs/2026-10-30-teams-design.md`](../specs/2026-10-30-teams-design.md)(段階 3 の節)

## Global Constraints

- 前提: 段階 1・2 が済んでいる(`Member.teams`・`Membership.percent`・`teams.team_scope`・`dashboard.Scope`・`Dashboard.team_name`)。
- ファイル形式は変えない(`version` は 17 のまま)。集計は保存せず、表示のたびに計算する。
- 按分は、メンバーの値に所属の割合(`percent / 100`)を掛ける。例: 田中の負荷 80%・A 60%・B 40% → A に 48%、B に 32%。
- `人ごとの負荷`: 平均と最大に重みを掛ける。**100% 超の日数は、掛ける前の値で判定する**。
- `残りの工数と必要人数`: 担当者の分(割り当て率の比で按分した値)に重みを掛ける。今いる人員は `相対比率 × 重み` の合計。必要人数の日数は、絞ったタスクの完了予定・締切から今までどおり決める。
- `チーム別`の行は`全員`のときだけ。メンバーの残りの工数を所属の割合で各チームに配り、どのチームにも入っていないメンバーは`チームなし`、担当なしは`未割り当て`の行にする。合計は全員の合計と一致する。0 の行は出さない。メンバーのいるチームがないときは出さない。
- 按分しない: `進捗と遅れ`・`チーム全体の進捗`・`期限とマイルストーン`(共同タスクを丸ごと数える)。全プロジェクトを重ねる負荷(`summarize_cross_loads`)は、重みを掛けない。
- メンバーを選んだとき・全員のときの結果は、今までと変えない(既存テストが通ること)。
- ダッシュボードの既存の名前 `TeamProgress`・`Dashboard.team`・`summarize_team_progress` は「チーム全体の進捗」(円グラフ)のもので、別。名前を変えない。
- コミット末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. メンバーを選んだときと全員のときの数字が、今までと変わらないこと(重み 1.0 の経路)。
2. 兼務の人(A 60%・B 40%)が、`チーム別`の A・B に比どおり配られ、`チームなし`・`未割り当て`を含めた合計が全員の合計と一致すること。
3. 100% 超の日数が、割合を掛けても変わらないこと(田中 120%・A 60% で、最大は 72%、超過は 1 日のまま)。
4. 所属が 1 つのメンバー(100%)だけのチームでは、チームを選んでも数字が今までと同じになること。
5. チームを削除してメンバーがいなくなった・存在しないチーム名のとき、`team_weights` が None を返し、落ちずに`全員`の扱いになること。

---

## File Structure

- Modify: `src/projectapp/teams.py` — `team_weights`
- Modify: `src/projectapp/dashboard.py` — `Scope`・`_names`・`_factor`、`summarize_loads`・`summarize_workload`・`summarize_backlog`、`Backlog.by_team`、`summarize`
- Modify: `src/projectapp/dashboard_view.py` — `チーム別`の行、按分の注記
- Test: `test/test_teams.py`・`test/test_dashboard.py`・`test/test_dashboard_view.py`
- Modify: `CLAUDE.md`・`docs/development.md`・`docs/requests.md`・`docs/work-log.md`・`docs/superpowers/specs/2026-10-30-teams-design.md`(状態)

---

### Task 1: 重みつきの絞り込み(`team_weights`・`Scope`)

**Files:**
- Modify: `src/projectapp/teams.py`(`team_scope` の直後)
- Modify: `src/projectapp/dashboard.py:125-132`(`Scope`・`_names`)、`summarize`(`scope` の作り方)
- Test: `test/test_teams.py`、`test/test_dashboard.py`

**Interfaces:**
- Produces:
  - `teams.team_weights(project: Project, team: str | None) -> dict[str, float] | None` — `{メンバー名: percent / 100}`(メンバーの並び順)。None・存在しない・メンバーがいないチームは None
  - `dashboard.Scope = str | frozenset[str] | Mapping[str, float] | None`
  - `dashboard._factor(scope: Scope, name: str) -> float` — 辞書ならその重み、それ以外は 1.0
  - `dashboard._names` は辞書のキーの集合を返す

- [ ] **Step 1: 失敗するテストを書く**(`test/test_teams.py` の末尾に追加。`team_weights` を import に足す)

```python
def test_team_weights_give_each_member_the_share_in_that_team() -> None:
    project = Project(
        "P",
        members=[
            Member("田中", 1.0, teams=ms(("a", 100))),
            Member("佐藤", 1.0, teams=ms(("a", 60), ("b", 40))),
            Member("山田", 1.0),
        ],
        teams=[Team("開発", id="a"), Team("QA", id="b"), Team("空", id="z")],
    )
    assert team_weights(project, "開発") == {"田中": 1.0, "佐藤": 0.6}
    assert team_weights(project, "QA") == {"佐藤": 0.4}


def test_team_weights_are_none_for_no_unknown_or_empty_team() -> None:
    project = Project("P", members=[Member("田中", 1.0)], teams=[Team("空", id="z")])
    assert team_weights(project, None) is None
    assert team_weights(project, "ない") is None
    assert team_weights(project, "空") is None
```

`test/test_dashboard.py` の `teamed_project` の後ろ(`test_a_string_scope_still_means_one_member` の近く)に追加:

```python
def test_a_weighted_scope_selects_its_keys_like_a_set() -> None:
    progress = summarize_progress(teamed_project(), {}, NOW, {"田中": 1.0, "鈴木": 1.0})
    assert progress.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 1}
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_teams.py test/test_dashboard.py -k "weights or weighted" -v`
Expected: FAIL(`ImportError: cannot import name 'team_weights'`)

- [ ] **Step 3: 実装する**

`src/projectapp/teams.py`(`team_scope` の直後):

```python
def team_weights(project: Project, team: str | None) -> dict[str, float] | None:
    """チーム名 → {メンバー名: そのチームの所属の割合(1.0 = 100%)}(メンバーの並び順)。None・存在しない・メンバーがいないチームは None。"""
    if team is None:
        return None
    for entry in project.teams:
        if entry.name == team:
            weights = {
                m.name: s.percent / 100 for m in project.members for s in m.teams if s.team_id == entry.id
            }
            return weights or None
    return None
```

`src/projectapp/dashboard.py`:

```python
Scope = str | frozenset[str] | Mapping[str, float] | None  # 絞り込み。文字列は 1 人、集合はそのうちの誰か(チーム)、辞書は名前 → 重み(チームの所属の割合)。None は全員


def _names(scope: Scope) -> frozenset[str] | None:
    """絞り込みを、メンバー名の集合にする。全員は None。"""
    if scope is None:
        return None
    if isinstance(scope, str):
        return frozenset({scope})
    return frozenset(scope)  # 集合はそのまま、辞書はキー


def _factor(scope: Scope, name: str) -> float:
    """メンバーの値に掛ける重み。チーム(辞書)なら所属の割合、それ以外は 1.0。"""
    return scope.get(name, 1.0) if isinstance(scope, Mapping) else 1.0
```

`import` の `team_scope` の隣に `team_weights` を足し、`summarize` を変える:

```python
    team_members = team_scope(project, team) if member is None else None
    weights = team_weights(project, team) if member is None else None
    scope: Scope = member if member is not None else weights
```

(`team_name=team if team_members is not None else None` は今のまま。`team_scope` は `team_name` の判定だけに使う。)

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_teams.py test/test_dashboard.py -v 2>&1 | tail -5`
Expected: 全部 PASS(重みはまだどこにも掛けていないので、既存の結果は変わらない)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/teams.py src/projectapp/dashboard.py test/test_teams.py test/test_dashboard.py
git commit -m "feat: チームの所属の割合を、集計の絞り込みの重みとして渡せるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `人ごとの負荷`と`工数の予定と実績`の按分

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_loads`、`summarize_workload`)
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: `_factor(scope, name)`(Task 1)
- Produces: `summarize_loads(..., member: Scope)` が、辞書の重みで `average`・`peak` を掛け、`overload_days` は掛ける前の値のまま返す。`summarize_workload` が、`planned_hours`・`actual_hours` に重みを掛けた行を返す

- [ ] **Step 1: 失敗するテストを書く**(`test/test_dashboard.py`。`span_task`・`WEEK`・`NOW` は既存)

```python
def test_loads_for_a_weighted_scope_scale_average_and_peak_but_not_the_overload_days() -> None:
    project = project_of(span_task("a", 5, 6, 0.8), span_task("b", 5, 6, 0.4))  # 田中は 120%
    plain = summarize_loads(project, WEEK, {})["田中"]
    scaled = summarize_loads(project, WEEK, {}, {"田中": 0.6})["田中"]
    assert scaled.average == pytest.approx(plain.average * 0.6)
    assert scaled.peak == pytest.approx(plain.peak * 0.6)
    assert scaled.peak < 1.0 < plain.peak
    assert scaled.overload_days == plain.overload_days > 0  # 超過は、掛ける前の値で判定する


def test_loads_for_a_set_or_a_string_scope_are_not_scaled() -> None:
    project = project_of(span_task("a", 5, 6, 0.8))
    plain = summarize_loads(project, WEEK, {})["田中"]
    assert summarize_loads(project, WEEK, {}, "田中")["田中"] == plain
    assert summarize_loads(project, WEEK, {}, frozenset({"田中"}))["田中"] == plain


def test_workload_for_a_weighted_scope_scales_planned_and_actual() -> None:
    task = span_task("作業", 5, 6, 1.0, actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 13))])
    project = project_of(task)
    plain = summarize_workload(project, WEEK, NOW, {})[0]
    scaled = summarize_workload(project, WEEK, NOW, {}, {"田中": 0.6})[0]
    assert plain.planned_hours > 0 and plain.actual_hours == pytest.approx(4)
    assert scaled.planned_hours == pytest.approx(plain.planned_hours * 0.6)
    assert scaled.actual_hours == pytest.approx(4 * 0.6)
```

`summarize_loads`・`summarize_workload` が import されていなければ足す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -k "weighted_scope" -v`
Expected: FAIL(平均・最大が掛かっていない)

- [ ] **Step 3: 実装する**

`summarize_loads`:

```python
def _scaled(stats: LoadStats, factor: float) -> LoadStats:
    """平均と最大に重みを掛ける。超過の日数は、掛ける前の値で判定したままにする。"""
    if factor == 1.0:
        return stats
    return LoadStats(stats.average * factor, stats.peak * factor, stats.overload_days)


def summarize_loads(
    project: Project, period: Period, holidays: dict[date, str], member: Scope = None
) -> dict[str, LoadStats]:
    spans = _member_spans(project, holidays, member)
    scoped = _names(member)
    return {
        entry.name: _scaled(
            _load_stats(spans.get(entry.name, []), _workdays(period, holidays, work_day_map(entry.work_days))),
            _factor(member, entry.name),
        )
        for entry in project.members
        if scoped is None or entry.name in scoped
    }
```

`summarize_workload` の最後(`rows = ...`)を変える:

```python
    rows = [
        WorkloadRow(name, planned[name] * _factor(member, name), actual[name] * _factor(member, name))
        for name in shown
    ]
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard.py -v 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: チームを選んだ負荷と工数に、所属の割合を掛ける

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `残りの工数と必要人数`の按分

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_backlog`)
- Test: `test/test_dashboard.py`(`test_the_backlog_for_a_team_counts_only_the_team_members` を直す)

**Interfaces:**
- Consumes: `_factor`(Task 1)
- Produces: `summarize_backlog(..., member: Scope)` が、辞書の重みで `hours`・`by_member`・`by_status`・`supply`・`required` を按分した値を返す

- [ ] **Step 1: 失敗するテストを書く**

既存の `test_the_backlog_for_a_team_counts_only_the_team_members` の `team.supply == pytest.approx(2.0)` を、佐藤が開発に 60% で入っているため `1.6` に直す(田中 1.0 × 1.0 + 佐藤 1.0 × 0.6):

```python
    assert team.supply == pytest.approx(1.6)  # 田中 100% + 佐藤 60% の相対比率
```

追加:

```python
def test_the_backlog_for_a_weighted_scope_scales_each_members_share() -> None:
    project = project_of(
        Task("共同", effort_hours=8, assignees=[Assignee("田中", 0.5), Assignee("佐藤", 0.5)]),
        members=[Member("田中", 1.0), Member("佐藤", 1.0)],
    )
    plain = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {})
    scaled = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, {"田中": 1.0, "佐藤": 0.25})
    assert plain.hours == pytest.approx(8)
    assert dict(scaled.by_member) == {"田中": pytest.approx(4.0), "佐藤": pytest.approx(1.0)}
    assert scaled.hours == pytest.approx(5.0)
    assert sum(scaled.by_status.values()) == pytest.approx(5.0)
    assert scaled.supply == pytest.approx(1.25)
    assert scaled.days == plain.days  # 日数は、絞ったタスクの日程から決める。重みでは変わらない


def test_the_backlog_for_a_single_membership_team_is_the_same_as_the_member_scope() -> None:
    project = project_of(Task("作業", effort_hours=6, assignees=[Assignee("田中", 1.0)]))
    by_name = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, "田中")
    by_team = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, {"田中": 1.0})
    assert by_team == by_name
```

`summarize_backlog` が import されていなければ足す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -k "backlog" -v`
Expected: FAIL(重みが掛かっていない。`1.6` のテストは supply が 2.0 のまま)

- [ ] **Step 3: 実装する**

`summarize_backlog` の担当者ごとのループ・合計・供給を変える(`split` は重みを掛ける前のメンバーごとの値のまま持つ。`チーム別`〔Task 4〕がこれを使う):

```python
        for key, _, share in _shares(task.assignees, names):
            portion = rest * fraction * share
            split[key] += portion
            if scoped is None or key in scoped:
                by_status[task.status] += portion * _factor(member, key)
    shown = [name for name in (*names, UNASSIGNED) if scoped is None or name in scoped]
    hours = sum(split[name] * _factor(member, name) for name in shown)
    ...
    supply = sum(
        effective_ratio(m, project.parameters, None, project.ratio_limits) * _factor(member, m.name)
        for m in project.members
        if scoped is None or m.name in scoped
    )
    rows = [(name, split[name] * _factor(member, name)) for name in shown if split[name] > 0]
```

(`UNASSIGNED` は辞書に入らないので `_factor` は 1.0。ただし `shown` は `scoped` の絞り込みで未割り当てを含まない。)`...` の部分(`days`・`required`)は今のまま。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard.py -v 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: チームを選んだ残りの工数と今いる人員に、所属の割合を掛ける

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `チーム別`の行(集計と画面)

**Files:**
- Modify: `src/projectapp/dashboard.py`(`Backlog`・`summarize_backlog`)
- Modify: `src/projectapp/dashboard_view.py:715-719`(`backlog_card`)、`:508` の近くの注記
- Test: `test/test_dashboard.py`、`test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `split`(重みを掛ける前のメンバーごとの残りの工数。Task 3)
- Produces:
  - `dashboard.NO_TEAM = "チームなし"`
  - `Backlog.by_team: list[tuple[str, float]]` — `全員`のときだけ入る。チームの並び順、続けて`チームなし`、`未割り当て`。0 は除く。メンバーのいるチームがなければ空
  - 画面のマーク: `dashboard-backlog-team-{名前}`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py`:

```python
def test_backlog_by_team_hands_a_members_hours_to_each_team_by_percent() -> None:
    project = teamed_project()  # 田中 A100 / 佐藤 A60・B40 / 鈴木 B100 / 山田 チームなし
    project.tasks = [
        Task("田中", effort_hours=10, assignees=[Assignee("田中", 1.0)]),
        Task("佐藤", effort_hours=10, assignees=[Assignee("佐藤", 1.0)]),
        Task("鈴木", effort_hours=10, assignees=[Assignee("鈴木", 1.0)]),
        Task("山田", effort_hours=10, assignees=[Assignee("山田", 1.0)]),
        Task("担当なし", effort_hours=10),
    ]
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {})
    rows = dict(backlog.by_team)
    assert rows["開発"] == pytest.approx(10 + 6)  # 田中 + 佐藤の 60%
    assert rows["QA"] == pytest.approx(10 + 4)  # 鈴木 + 佐藤の 40%
    assert rows[NO_TEAM] == pytest.approx(10)
    assert rows[UNASSIGNED] == pytest.approx(10)
    assert sum(rows.values()) == pytest.approx(backlog.hours) == pytest.approx(50)
    assert list(rows) == ["開発", "QA", NO_TEAM, UNASSIGNED]


def test_backlog_by_team_is_empty_with_a_filter_or_without_teams() -> None:
    project = teamed_project()
    assert summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, "田中").by_team == []
    assert summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, {"田中": 1.0}).by_team == []
    bare = project_of(Task("作業", effort_hours=2, assignees=[Assignee("田中", 1.0)]))
    assert summarize_backlog(bare, WEEK, PeriodKind.ALL, NOW, {}).by_team == []
```

`NO_TEAM`・`UNASSIGNED` を `projectapp.dashboard` から import する(`UNASSIGNED` が未 import なら足す)。`teamed_project` の `tasks` は上のテストで差し替えるので、他のテストに影響しない(関数ごとに新しく作られる)。

`test/test_dashboard_view.py`(`test_the_backlog_card_shows_hours_required_people_and_the_shortfall` の後ろ。`with_backlog`・`mount`・`text` は既存):

```python
async def test_the_backlog_card_lists_the_team_rows(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(26.0, 0, 3, 2.0, 1.5, [("田中", 16.0)], by_team=[("開発", 16.0), ("チームなし", 10.0)])
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-team-開発")
    assert text(user, "dashboard-backlog-team-開発") == "開発 16.0h"
    assert text(user, "dashboard-backlog-team-チームなし") == "チームなし 10.0h"


async def test_the_backlog_card_hides_the_team_heading_without_team_rows(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-member-田中")
    await user.should_not_see("チーム別")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py test/test_dashboard_view.py -k "by_team or team_rows" -v`
Expected: FAIL(`NO_TEAM` なし・`by_team` なし)

- [ ] **Step 3: 実装する**

`dashboard.py`:

```python
NO_TEAM = "チームなし"
```

(`UNASSIGNED` の隣に置く。)`Backlog` の末尾に:

```python
    by_team: list[tuple[str, float]] = field(default_factory=list)  # (チーム, 残りの工数)。全員のときだけ。メンバーの分を所属の割合で配る
```

`summarize_backlog` の `return` の前:

```python
    by_team = _backlog_by_team(project, split) if scoped is None else []
    return Backlog(
        hours, unset, days, required, supply, rows, {k: v for k, v in by_status.items() if v > 0}, by_team
    )
```

新しい関数:

```python
def _backlog_by_team(project: Project, split: dict[str, float]) -> list[tuple[str, float]]:
    """メンバーごとの残りの工数を、所属の割合で各チームに配る。チームに入っていない人は`チームなし`、担当なしは`未割り当て`。
    メンバーのいるチームがなければ空(チーム別を出さない)。"""
    names = {entry.id: entry.name for entry in project.teams}
    hours: dict[str, float] = {name: 0.0 for name in teams_with_members(project)}
    if not hours:
        return []
    hours[NO_TEAM] = 0.0
    for member in project.members:
        if not member.teams:
            hours[NO_TEAM] += split.get(member.name, 0.0)
        for membership in member.teams:
            hours[names[membership.team_id]] += split.get(member.name, 0.0) * membership.percent / 100
    hours[UNASSIGNED] = split.get(UNASSIGNED, 0.0)
    return [(name, value) for name, value in hours.items() if value > 0]
```

(`teams_with_members` の順がチームの並び順。`names[...]` はファイルの検証で存在が保証されている。)

`dashboard_view.py` の `backlog_card`、`by_member` の表示の後ろに:

```python
            if backlog.by_team:
                ui.label("チーム別").classes("text-subtitle2")
                top = max(hours for _, hours in backlog.by_team)
                for name, hours in backlog.by_team:
                    ui.label(f"{name} {hours:.1f}h").classes("text-caption").mark(f"dashboard-backlog-team-{name}")
                    bar(hours / top, PLANNED_COLOR)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard.py test/test_dashboard_view.py -v 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py src/projectapp/dashboard_view.py test/test_dashboard.py test/test_dashboard_view.py
git commit -m "feat: 残りの工数に、チーム別の行を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 按分の注記・仕様書・記録

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(チームを選んでいるときの注記)
- Modify: `CLAUDE.md`(27 行目の`集計の按分は後続機能(要望 85 の段階 3)`、83 行目の`(値はメンバーのまま。所属の割合による按分は後続)`)
- Modify: `docs/development.md:169`(段階 3 は未実装)、`docs/requests.md`(要望 85 の状態)、`docs/work-log.md`、`docs/hidden-requests.md`(要望 88 の備考)、`docs/superpowers/specs/2026-10-30-teams-design.md`(状態)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `Dashboard.team_name`(段階 2)
- Produces: チームを選んでいるとき、`人ごとの負荷`・`工数の予定と実績`・`残りの工数と必要人数`の各カードに、注記 `チーム「名前」の所属の割合で按分しています`(マーク `dashboard-weighted-note-load`・`-hours`・`-backlog`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py`(上の続き):

```python
async def test_the_cards_note_the_weighting_only_when_a_team_is_selected(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)]))
    data.team_name = "開発"
    views[0].show(data, PeriodKind.WEEK)
    for key in ("load", "hours", "backlog"):
        await user.should_see(marker=f"dashboard-weighted-note-{key}")
    assert text(user, "dashboard-weighted-note-backlog") == "チーム「開発」の所属の割合で按分しています"


async def test_the_cards_do_not_note_the_weighting_without_a_team(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    await user.should_not_see(marker="dashboard-weighted-note-backlog")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -k "weighting" -v`
Expected: FAIL

- [ ] **Step 3: 実装する**

`dashboard_view.py` に共通の小さな関数を足し(`empty_message` の近く)、3 つのカード(`load_card`・`hours_card`・`backlog_card`)の `with card(...)` の直後で、`weighted_note(data, "load")`・`weighted_note(data, "hours")`・`weighted_note(data, "backlog")` をそれぞれ呼ぶ(早期 return より前に置く):

```python
def weighted_note(data: Dashboard, key: str) -> None:
    """チームを選んでいるときの注記。`key`はカードごとのマークの末尾(load・hours・backlog)。"""
    if data.team_name:
        ui.label(f"チーム「{data.team_name}」の所属の割合で按分しています").classes("text-caption text-grey").mark(
            f"dashboard-weighted-note-{key}"
        )
```

`CLAUDE.md` の更新:
- 27 行目の末尾 `集計の按分は後続機能(要望 85 の段階 3)` → `集計の按分は下記(ダッシュボード)`
- 83 行目の `(値はメンバーのまま。所属の割合による按分は後続)` → `(負荷と工数は、メンバーの値に所属の割合を掛ける。負荷は平均と最大に掛け、100% 超の日数は掛ける前の値で判定する。残りの工数と必要人数は、担当者の分に割合を掛け、今いる人員は相対比率に割合を掛けて合計する。`チーム別`の行は、`全員`のとき`残りの工数と必要人数`の担当別の隣に出し、メンバーの分を所属の割合で配る〔チームに入っていないメンバーは`チームなし`、担当なしは`未割り当て`。合計は全員と一致〕。`進捗と遅れ`・円グラフ・`期限とマイルストーン`は按分しない。全プロジェクトを重ねる負荷にも掛けない)`
- 該当する箇所に `チームを選ぶと、按分している旨の注記を 3 つのカードに出す` を添える

`docs/development.md:169` の `段階 3(集計の按分)は未実装。` → `段階 3(集計の按分)は実装済み: `teams.team_weights`、`dashboard.Scope` の辞書(名前 → 重み)・`_factor`、`summarize_loads`・`summarize_workload`・`summarize_backlog` の按分、`Backlog.by_team`(`NO_TEAM`)。`

`docs/requests.md`・`docs/work-log.md` の要望 85 の記録に段階 3 の実装日・PR 番号(マージ後に記入)・テスト件数を足す。`docs/hidden-requests.md` の要望 88 に、段階 3 で按分は開いているプロジェクトのチームだけと決めた旨を足す。`docs/superpowers/specs/2026-10-30-teams-design.md` の状態を `段階 3 は実装済み(計画 [`plans/2026-10-30-teams-stage3.md`](../plans/2026-10-30-teams-stage3.md))` にする。

- [ ] **Step 4: 全体を確認する**

Run: `uv run pytest -q 2>&1 | tail -5` と `uv run ty check src`
Expected: 全テスト PASS・`ty` 通過

- [ ] **Step 5: 実機で確認する**(`uv run projectapp`。メンバー 3 人・チーム 2 つ・兼務 1 人のプロジェクトで)

ダッシュボードを開き、①`全員`で`残りの工数と必要人数`に`チーム別`が出て合計が合う ②チームを選ぶと 3 つのカードに注記が出て、負荷・工数・必要人数が按分される ③メンバーを選ぶと今までと同じ数字、を確かめる。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "docs: チームの集計の按分(要望 85 段階 3)の注記と記録を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage**: 残りの工数・必要人数の按分(Task 3)・`チーム別`の行(Task 4)・負荷の按分と超過の判定(Task 2)・工数の予定と実績(Task 2)・按分しない集計と全プロジェクトの負荷(Global Constraints。コードは変えない)・テスト(各 Task)。漏れなし。
- **Placeholder scan**: 全 Task に具体的なテストとコードを載せた。
- **Type consistency**: `Scope`・`_factor`・`team_weights`・`Backlog.by_team`・`NO_TEAM`・`dashboard-backlog-team-{名前}`・`dashboard-weighted-note` は全 Task で同じ名前。
- **既存テストへの影響**: `test_the_backlog_for_a_team_counts_only_the_team_members` の `supply` を 2.0 → 1.6 に直す(Task 3)。ほかは重み 1.0 の経路で変わらない。
