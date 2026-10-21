# 複数プロジェクトの並行稼働による負荷 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードの「人ごとの負荷」カードで、格納先の全プロジェクトを重ねた負荷(平均・最大・100%超の日数)とプロジェクト別の内訳を見られるようにする。

**Architecture:** 集計は `dashboard.py` に純粋関数 `summarize_cross_loads` を足す。ほかのプロジェクトの読込は NiceGUI から切り離した `portfolio.py`。画面は `dashboard_view.py` のカードの拡張で、状態(スイッチ・除外するプロジェクト)は `views.py` が持つ。ファイル形式は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、ty

**Spec:** `docs/superpowers/specs/2026-10-21-cross-project-load-design.md`

## Global Constraints

- 型ヒント: すべての関数に引数と戻り値の型を書く(`.claude/RULE.md`)。型チェックは `uv run ty check src`
- コメントは多くても 3 行以内。言語は日本語
- 同一人物の判定は、メンバー名の完全一致のみ
- 横断のスイッチ・除外するプロジェクトは保存しない(ダッシュボードを開き直すと、オフ・すべて)
- 開いているプロジェクトはメモリ上の内容、ほかはディスクの内容
- ファイル形式(`version` 7)は変えない
- 横断の読込は、横断がオンの表示のたびに行う(キャッシュしない)
- 実行: `uv run pytest -q`(並列は `-n auto`)。ブランチは `feature/cross-project-load`(作成済み)

## Review Focus

- 同じ人が 2 プロジェクトで同時刻に作業する(合計が 100% を超える)。1 プロジェクトずつは 100% 以内でも超過日に数える → Task 1
- 一方のプロジェクトが読めない(壊れた JSON)。ダッシュボードは止めず、残りで集計して理由を出す → Task 2・4
- 開いているプロジェクトが保存前の新規(ファイルなし)。格納先のファイルすべてが「ほかのプロジェクト」になる → Task 2
- 格納先が存在しない・フォルダでない。開いているプロジェクト 1 件で集計し、理由を出す → Task 2・4
- 横断をオフに戻したとき、別プロジェクトのメンバーを選んでいた絞り込みが全員に戻る → Task 4

---

### Task 1: 集計 `summarize_cross_loads`

**Files:**
- Modify: `src/projectapp/dashboard.py`(`LoadStats` の近く、`summarize_loads` の前後)
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: 既存の `_tasks`、`_workdays`、`_day_peak`、`Schedule`、`counted_span`、`counted_assignees`、`OVERLOAD_EPSILON`
- Produces:
  - `ProjectLoad(project: str, average: float, peak: float)`(frozen dataclass)
  - `CrossLoad(total: LoadStats, by_project: list[ProjectLoad])`(frozen dataclass)
  - `summarize_cross_loads(projects: list[Project], period: Period, holidays: dict[date, str], member: str | None = None) -> dict[str, CrossLoad]`。キーは、いずれかのプロジェクトのメンバー名(プロジェクトの並び順、その中の登場順で最初に出たもの)。`member` があればその 1 人だけ(どのプロジェクトにもいなければ空)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の import に `summarize_cross_loads` を足し、`test_loads_list_the_members_in_order_and_skip_non_members` の後ろ(`DAY = ...` の前)に追記する。

```python
def named(name: str, *tasks: Task, members: list[Member] | None = None) -> Project:
    project = project_of(*tasks, members=members)
    project.name = name
    return project


def test_cross_load_with_one_project_matches_the_single_project_load() -> None:
    project = project_of(span_task("a", 5, 6, 0.6), span_task("b", 5, 6, 0.6))
    cross = summarize_cross_loads([project], WEEK, {})["田中"]
    assert cross.total == summarize_loads(project, WEEK, {})["田中"]


def test_cross_load_adds_the_same_person_across_projects_and_counts_the_overload() -> None:
    first = named("A", span_task("a", 5, 6, 0.6))
    second = named("B", span_task("b", 5, 6, 0.6))
    cross = summarize_cross_loads([first, second], WEEK, {})["田中"]
    assert (cross.total.peak, cross.total.overload_days) == (pytest.approx(1.2), 2)  # 1 件ずつは 60%
    assert [(p.project, p.peak) for p in cross.by_project] == [("A", 0.6), ("B", 0.6)]


def test_cross_load_does_not_add_projects_that_do_not_overlap() -> None:
    first = named("A", span_task("a", 5, 5, 0.6))
    second = named("B", span_task("b", 6, 6, 0.6))
    cross = summarize_cross_loads([first, second], WEEK, {})["田中"]
    assert (cross.total.peak, cross.total.overload_days) == (0.6, 0)


def test_cross_load_skips_finished_tasks() -> None:
    first = named("A", span_task("a", 5, 6, 0.9))
    second = named("B", span_task("b", 5, 6, 0.9, status=Status.DONE))
    cross = summarize_cross_loads([first, second], WEEK, {})["田中"]
    assert cross.total.overload_days == 0


def test_cross_load_overlays_projects_with_different_working_hours_by_date_and_time() -> None:
    first = named("A", span_task("a", 5, 6, 0.6))
    second = named("B", span_task("b", 5, 6, 0.6))
    second.daily_hours = 4.0
    cross = summarize_cross_loads([first, second], WEEK, {})["田中"]
    assert cross.total.peak >= 0.6  # 期間は各自の設定で求め、日時のまま重ねる(手指定の終了なので位置は同じ)
    assert cross.total.peak == pytest.approx(1.2)


def test_cross_load_lists_a_person_who_is_only_in_one_project_with_that_project_only() -> None:
    first = named("A", span_task("a", 5, 6, 0.5))
    second = named("B", members=[Member("佐藤", 1.0)])
    loads = summarize_cross_loads([first, second], WEEK, {})
    assert list(loads) == ["田中", "佐藤"]
    assert [p.project for p in loads["田中"].by_project] == ["A"]
    assert [p.project for p in loads["佐藤"].by_project] == ["B"]


def test_cross_load_filters_to_one_member_by_name() -> None:
    first = named("A", span_task("a", 5, 6, 0.5))
    second = named("B", members=[Member("佐藤", 1.0)])
    assert list(summarize_cross_loads([first, second], WEEK, {}, "佐藤")) == ["佐藤"]
    assert summarize_cross_loads([first, second], WEEK, {}, "鈴木") == {}


def test_cross_load_without_projects_is_empty() -> None:
    assert summarize_cross_loads([], WEEK, {}) == {}
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -q -k cross_load`
Expected: FAIL(`ImportError: cannot import name 'summarize_cross_loads'`)

- [ ] **Step 3: 実装する**

`dashboard.py` で `summarize_loads` を次のように置き換える(期間の集め方を `_member_spans` に切り出し、両方で使う)。`LoadStats` の定義の下に `ProjectLoad`・`CrossLoad` を足す。

```python
@dataclass(frozen=True)
class ProjectLoad:
    project: str
    average: float  # そのプロジェクトだけで見た、稼働日ごとの負荷の平均
    peak: float


@dataclass(frozen=True)
class CrossLoad:
    total: LoadStats  # 全プロジェクトを重ねた負荷
    by_project: list[ProjectLoad]  # その人がメンバーのプロジェクトごと
```

```python
Span = tuple[datetime, datetime, float]


def _member_spans(project: Project, holidays: dict[date, str], member: str | None) -> dict[str, list[Span]]:
    """担当者名 → (開始, 終了, 割り当て率)。数えないタスクは入れない。"""
    spans: dict[str, list[Span]] = {}
    schedule = Schedule(project, holidays)
    for task in _tasks(project, member):
        counted = counted_span(task, project, holidays, schedule)
        if counted is not None:
            for assignee in counted_assignees(task, project):
                spans.setdefault(assignee.name, []).append((*counted, assignee.allocation))
    return spans


def _load_stats(items: list[Span], days: list[date]) -> LoadStats:
    totals = [_day_peak(items, day) for day in days]
    return LoadStats(
        sum(totals) / len(totals) if totals else 0.0,
        max(totals, default=0.0),
        sum(1 for total in totals if total > 1.0 + OVERLOAD_EPSILON),
    )


def summarize_loads(
    project: Project, period: Period, holidays: dict[date, str], member: str | None = None
) -> dict[str, LoadStats]:
    days = _workdays(period, holidays)
    spans = _member_spans(project, holidays, member)
    return {
        entry.name: _load_stats(spans.get(entry.name, []), days)
        for entry in project.members
        if member is None or entry.name == member
    }


def summarize_cross_loads(
    projects: list[Project], period: Period, holidays: dict[date, str], member: str | None = None
) -> dict[str, CrossLoad]:
    """複数のプロジェクトを重ねた負荷。同じ名前のメンバーを同一人物とみなす。"""
    days = _workdays(period, holidays)
    per_project = [(project, _member_spans(project, holidays, member)) for project in projects]
    names = dict.fromkeys(m.name for project in projects for m in project.members if member is None or m.name == member)
    loads: dict[str, CrossLoad] = {}
    for name in names:
        rows: list[ProjectLoad] = []
        everything: list[Span] = []
        for project, spans in per_project:
            if name not in {m.name for m in project.members}:
                continue
            items = spans.get(name, [])
            everything += items
            stats = _load_stats(items, days)
            rows.append(ProjectLoad(project.name, stats.average, stats.peak))
        loads[name] = CrossLoad(_load_stats(everything, days), rows)
    return loads
```

- [ ] **Step 4: 通ることを確認する(既存の負荷テストを含む)**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: PASS(全件)

- [ ] **Step 5: 型チェックとコミット**

```bash
uv run ty check src
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: プロジェクトを重ねた負荷を集計する(要望31)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 読込 `portfolio.load_others`

**Files:**
- Create: `src/projectapp/portfolio.py`
- Modify: `src/projectapp/dashboard.py`(`LoadFailure` を足す)
- Test: `test/test_portfolio.py`(新規)

**Interfaces:**
- Consumes: `storage.list_project_files(base_dir: Path) -> list[Path]`、`storage.load_project(path: Path) -> Project`
- Produces:
  - `LoadFailure(name: str, reason: str)`(`dashboard.py` の NamedTuple)
  - `portfolio.load_others(project_dir: Path, current: Path | None) -> tuple[list[Project], list[LoadFailure]]`。`current` と同じファイルは除く。格納先がフォルダでないときは、プロジェクトなし、失敗 1 件(`LoadFailure(str(project_dir), "格納先を読めません")`)

- [ ] **Step 1: 失敗するテストを書く**

```python
from pathlib import Path

from projectapp.models import Project
from projectapp.portfolio import load_others
from projectapp.storage import save_cache, save_project


def test_load_others_skips_the_open_project_and_reads_the_rest(tmp_path: Path) -> None:
    current = save_project(Project("開いている"), tmp_path)
    save_project(Project("ほか"), tmp_path)
    projects, failures = load_others(tmp_path, current)
    assert [p.name for p in projects] == ["ほか"]
    assert failures == []


def test_load_others_reads_everything_when_the_open_project_is_unsaved(tmp_path: Path) -> None:
    save_project(Project("甲"), tmp_path)
    save_project(Project("乙"), tmp_path)
    projects, _ = load_others(tmp_path, None)
    assert sorted(p.name for p in projects) == ["乙", "甲"]


def test_load_others_collects_unreadable_files_and_keeps_going(tmp_path: Path) -> None:
    save_project(Project("良い"), tmp_path)
    (tmp_path / "壊れた.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "新しい.json").write_text('{"version": 999}', encoding="utf-8")
    projects, failures = load_others(tmp_path, None)
    assert [p.name for p in projects] == ["良い"]
    assert sorted(f.name for f in failures) == ["壊れた", "新しい"]
    assert all(f.reason for f in failures)


def test_load_others_does_not_read_config_or_holidays(tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert load_others(tmp_path, None) == ([], [])


def test_load_others_reports_a_missing_directory(tmp_path: Path) -> None:
    projects, failures = load_others(tmp_path / "ない", None)
    assert projects == []
    assert [f.reason for f in failures] == ["格納先を読めません"]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_portfolio.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.portfolio`)

- [ ] **Step 3: 実装する**

`dashboard.py`(`LoadStats` の上)に追加する。`NamedTuple` を `typing` から import する。

```python
class LoadFailure(NamedTuple):
    name: str
    reason: str
```

`src/projectapp/portfolio.py`:

```python
"""格納先の、開いているプロジェクト以外のプロジェクトを読む。NiceGUI に依存しない。"""

from pathlib import Path

from projectapp.dashboard import LoadFailure
from projectapp.models import Project
from projectapp.storage import list_project_files, load_project


def load_others(project_dir: Path, current: Path | None) -> tuple[list[Project], list[LoadFailure]]:
    """`current`(開いているファイル)を除く、格納先のプロジェクト。読めないものは理由とともに返す。"""
    if not project_dir.is_dir():
        return [], [LoadFailure(str(project_dir), "格納先を読めません")]
    projects: list[Project] = []
    failures: list[LoadFailure] = []
    for path in list_project_files(project_dir):
        if current is not None and path.resolve() == current.resolve():
            continue
        try:
            projects.append(load_project(path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures.append(LoadFailure(path.stem, str(exc)))
    return projects, failures
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_portfolio.py -q`
Expected: PASS

- [ ] **Step 5: 型チェックとコミット**

```bash
uv run ty check src
git add src/projectapp/portfolio.py src/projectapp/dashboard.py test/test_portfolio.py
git commit -m "feat: 格納先のほかのプロジェクトを読む(要望31)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面 `DashboardView`

**Files:**
- Modify: `src/projectapp/dashboard.py`(`CrossSummary` と `Dashboard.cross`)
- Modify: `src/projectapp/dashboard_view.py`(`__init__`・`build`・`show`・`load_card`)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: Task 1 の `CrossLoad`・`ProjectLoad`、Task 2 の `LoadFailure`
- Produces:
  - `CrossSummary(loads: dict[str, CrossLoad], projects: list[str], excluded: set[str], failures: list[LoadFailure])`(dataclass)。`projects` は、チェックの並び(開いているプロジェクトが先)
  - `Dashboard.cross: CrossSummary | None = None`(`members` の後ろ。既定値あり)
  - `DashboardView(on_back, on_change, on_member_change=None, on_cross_change: Callable[[bool], object] | None = None, on_project_change: Callable[[str, bool], object] | None = None)`
  - マーカー: スイッチ `dashboard-cross`、チェック `dashboard-cross-project-{名前}`、注記 `dashboard-cross-note`、失敗 `dashboard-cross-failure-{i}`、合計の行 `dashboard-load-{名前}`(既存と同じ書式)、内訳 `dashboard-cross-detail-{名前}-{i}`(`{プロジェクト}: 平均 n% / 最大 n%`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` に追記する(`mount` に引数を足す前に、`DashboardView` を直接組む小さな関数を使う)。

```python
from projectapp.dashboard import CrossLoad, CrossSummary, LoadFailure, ProjectLoad


def cross_sample() -> Dashboard:
    data = sample()
    data.cross = CrossSummary(
        {"田中": CrossLoad(LoadStats(0.7, 1.2, 1), [ProjectLoad("A", 0.4, 0.6), ProjectLoad("B", 0.3, 0.6)])},
        ["A", "B", "C"],
        {"C"},
        [LoadFailure("壊れた", "invalid")],
    )
    return data


def mount_cross() -> tuple[list[DashboardView], list[bool], list[tuple[str, bool]]]:
    views: list[DashboardView] = []
    crosses: list[bool] = []
    projects: list[tuple[str, bool]] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(
            lambda: None,
            lambda kind: None,
            None,
            crosses.append,
            lambda name, on: projects.append((name, on)),
        )
        views.append(view)
        view.build()

    return views, crosses, projects


async def test_the_cross_load_card_shows_the_total_and_the_project_breakdown(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert text(user, "dashboard-load-田中") == "平均 70% / 最大 120% / 超過 1 日"
    assert text(user, "dashboard-cross-detail-田中-0") == "A: 平均 40% / 最大 60%"
    assert text(user, "dashboard-cross-detail-田中-1") == "B: 平均 30% / 最大 60%"
    await user.should_see(marker="dashboard-cross-note")


async def test_the_cross_load_card_lists_failures_and_the_project_checks(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-cross-failure-0")
    assert text(user, "dashboard-cross-failure-0") == "読み込めなかったファイル: 壊れた(invalid)"
    assert user.find(marker="dashboard-cross-project-A").elements.pop().value is True
    assert user.find(marker="dashboard-cross-project-C").elements.pop().value is False


async def test_toggling_the_switch_and_a_project_check_calls_back(user: User) -> None:
    views, crosses, projects = mount_cross()
    await user.open("/")
    views[0].show(cross_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-cross-project-A")
    user.find(marker="dashboard-cross").elements.pop().set_value(False)
    user.find(marker="dashboard-cross-project-A").elements.pop().set_value(False)
    assert crosses == [False]
    assert projects == [("A", False)]


async def test_without_cross_the_load_card_is_unchanged_and_the_switch_is_off(user: User) -> None:
    views, crosses, _ = mount_cross()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    assert text(user, "dashboard-load-田中") == "平均 50% / 最大 120% / 超過 2 日"
    await user.should_not_see(marker="dashboard-cross-note")
    assert user.find(marker="dashboard-cross").elements.pop().value is False
    assert crosses == []  # 表示の同期では通知しない
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -k cross`
Expected: FAIL(import error)

- [ ] **Step 3: 実装する**

`dashboard.py`:

```python
@dataclass
class CrossSummary:
    loads: dict[str, CrossLoad]
    projects: list[str]  # チェックの並び。開いているプロジェクトが先
    excluded: set[str]
    failures: list[LoadFailure]
```

`Dashboard` の `members` の後ろに `cross: CrossSummary | None = None` を足す。

`dashboard_view.py`:
- `__init__` に引数 `on_cross_change`・`on_project_change` を足し、`self.cross_switch: ui.switch | None = None` を持つ。
- `build()` で、メンバーのプルダウンの後ろに、`self.cross_switch = ui.switch("全プロジェクト", value=False, on_change=self.on_cross).mark("dashboard-cross")`。
- `on_cross(event)` は `if not self.syncing and self.on_cross_change is not None: self.on_cross_change(bool(event.value))`。
- `show()` で、メンバーの同期と同じ `syncing` の枠の中で `self.cross_switch.value = data.cross is not None`(違うときだけ)。
- `load_card` を、`data.cross` が `None` なら今のまま、あれば `cross_load_card` を使う形に分ける。行の描画は `load_row(name, stats, scale)` に切り出して共有する(中身は今の 1 行分。ラベルのマーカーは `dashboard-load-{name}`)。

```python
    def load_row(self, name: str, stats: LoadStats, scale: float) -> None:
        over = stats.overload_days > 0
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("items-center no-wrap gap-2"):
                if icon := self.icons.get(name):
                    avatar(name, icon, 20).mark(f"dashboard-load-icon-{name}")
                ui.label(name)
            ui.label(
                f"平均 {stats.average * 100:.0f}% / 最大 {stats.peak * 100:.0f}% / 超過 {stats.overload_days} 日"
            ).classes("text-caption" + (" text-negative" if over else "")).mark(f"dashboard-load-{name}")
            bar(stats.average / scale, OVER_COLOR if over else LOAD_COLOR, tick=stats.peak / scale)

    def cross_load_card(self, cross: CrossSummary) -> None:
        ui.label("同じ名前のメンバーを同一人物として、全プロジェクトを重ねています。開いているプロジェクト以外は保存済みの内容です。").classes(
            "text-caption text-grey"
        ).mark("dashboard-cross-note")
        with ui.row().classes("w-full gap-2"):
            for name in cross.projects:
                ui.checkbox(
                    name,
                    value=name not in cross.excluded,
                    on_change=lambda event, name=name: self.on_project(name, bool(event.value)),
                ).mark(f"dashboard-cross-project-{name}")
        for index, failure in enumerate(cross.failures):
            ui.label(f"読み込めなかったファイル: {failure.name}({failure.reason})").classes(
                "text-caption text-negative"
            ).mark(f"dashboard-cross-failure-{index}")
        if not cross.loads:
            empty_message("dashboard-empty-load")
            return
        scale = max(1.0, *(entry.total.peak for entry in cross.loads.values()))
        for name, entry in cross.loads.items():
            self.load_row(name, entry.total, scale)
            with ui.expansion("プロジェクト別").classes("w-full text-caption"):
                for index, row in enumerate(entry.by_project):
                    ui.label(f"{row.project}: 平均 {row.average * 100:.0f}% / 最大 {row.peak * 100:.0f}%").mark(
                        f"dashboard-cross-detail-{name}-{index}"
                    )
```

`load_card` は、`with card(...)` の中で `if data.cross is not None: self.cross_load_card(data.cross); return` を先頭に置く(それ以外は既存の `if not data.loads: ...` 以降を `load_row` で回す形に直す)。`on_project(name, on)` は `if not self.syncing and self.on_project_change is not None: self.on_project_change(name, on)`。

- [ ] **Step 4: 通ることを確認する(既存のビューのテストを含む)**

Run: `uv run pytest test/test_dashboard_view.py -q`
Expected: PASS(全件)

- [ ] **Step 5: 型チェックとコミット**

```bash
uv run ty check src
git add src/projectapp/dashboard.py src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: 人ごとの負荷のカードに、プロジェクトを重ねる表示を足す(要望31)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 配線 `MainView`

**Files:**
- Modify: `src/projectapp/views.py`(`__init__`・`DashboardView` の生成・`open_dashboard`・`refresh_dashboard`・ハンドラ 2 つ)
- Test: `test/test_views.py`(`open_dashboard_view` の近く)

**Interfaces:**
- Consumes: `portfolio.load_others`、`dashboard.summarize_cross_loads`・`CrossSummary`、Task 3 の `DashboardView` の引数
- Produces: `MainView.dashboard_cross: bool`、`MainView.dashboard_excluded: set[str]`、`change_dashboard_cross(on: bool)`、`change_dashboard_project(name: str, included: bool)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `test_the_dashboard_replaces_the_header_and_the_chart` の前後に追記する。`open_dashboard_view` は `tmp_path` を格納先にしているので、先に別のプロジェクトのファイルを `tmp_path` に置く。

```python
def other_project(name: str, start_day: int, end_day: int, allocation: float) -> Project:
    return Project(
        name,
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        tasks=[
            Task(
                "別の作業",
                assignees=[Assignee("田中", allocation)],
                planned_start=datetime(2026, 10, start_day, 9),
                planned_end=datetime(2026, 10, end_day, 17),
            )
        ],
    )


async def test_the_cross_switch_overlays_the_other_projects_in_the_storage(user: User, tmp_path: Path) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-load-田中")
    assert view.dashboard_cross is False
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-cross-project-別")
    assert "超過" in text_of(user, "dashboard-load-田中")
    assert view.dashboard_excluded == set()


async def test_excluding_a_project_removes_it_from_the_total(user: User, tmp_path: Path) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-cross-project-別")
    view.change_dashboard_project("別", False)
    assert view.dashboard_excluded == {"別"}
    assert "超過 0 日" in text_of(user, "dashboard-load-田中")


async def test_an_unreadable_file_is_shown_and_the_rest_is_still_summed(user: User, tmp_path: Path) -> None:
    (tmp_path / "壊れた.json").write_text("{not json", encoding="utf-8")
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-cross-failure-0")
    await user.should_see(marker="dashboard-load-田中")


async def test_reopening_the_dashboard_turns_the_cross_switch_off_and_includes_everything(
    user: User, tmp_path: Path
) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    view.change_dashboard_project("別", False)
    view.close_dashboard()
    view.open_dashboard()
    assert view.dashboard_cross is False
    assert view.dashboard_excluded == set()


async def test_a_member_of_another_project_falls_back_to_everyone_when_the_switch_goes_off(
    user: User, tmp_path: Path
) -> None:
    other = other_project("別", 6, 7, 0.5)
    other.members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    save_project(other, tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    view.change_dashboard_cross(True)
    view.change_dashboard_member("佐藤")
    assert view.dashboard_member == "佐藤"
    view.change_dashboard_cross(False)
    assert view.dashboard_member is None
```

(`text_of(user, marker)` は `user.find(marker=marker).elements.pop().text` を返すヘルパー。`test/test_views.py` になければ、`other_project` の上に足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k "cross or excluding or unreadable or reopening_the_dashboard"`
Expected: FAIL(`AttributeError: ... dashboard_cross`)

- [ ] **Step 3: 実装する**

`views.py`:
- import: `from projectapp.dashboard import CrossSummary, PeriodKind, period_for, summarize, summarize_cross_loads` と `from projectapp.portfolio import load_others`。
- `__init__`(`dashboard_member` の下): `self.dashboard_cross = False  # 全プロジェクトを重ねるか。保存しない` と `self.dashboard_excluded: set[str] = set()  # 重ねるのから外したプロジェクトの名前。保存しない`。
- `DashboardView(...)` の生成に、`self.change_dashboard_cross, self.change_dashboard_project` を渡す。
- `open_dashboard`: `self.dashboard_cross = False` と `self.dashboard_excluded = set()` を足す。
- `refresh_dashboard` を次の形にする。

```python
    def refresh_dashboard(self) -> None:
        if self.dashboard_kind is None:
            return
        now = self.now()
        period = period_for(self.dashboard_kind, now.date(), self.project, self.holidays)
        cross: CrossSummary | None = None
        names = [m.name for m in self.project.members]
        projects = [self.project]
        if self.dashboard_cross:
            others, failures = load_others(self.project_dir, self.path)
            projects += others
            names = list(dict.fromkeys(m.name for p in projects for m in p.members))
        if self.dashboard_member not in names:
            self.dashboard_member = None  # 削除・改名・横断オフで見えなくなったメンバーは、全員に戻す
        data = summarize(self.project, period, now, self.holidays, self.dashboard_kind, self.dashboard_member)
        if self.dashboard_cross:
            chosen = [p for p in projects if p.name not in self.dashboard_excluded]
            loads = summarize_cross_loads(chosen, period, self.holidays, self.dashboard_member)
            cross = CrossSummary(loads, [p.name for p in projects], self.dashboard_excluded & {p.name for p in projects}, failures)
            data.loads = {}
            data.members = names
            data.cross = cross
        icons = {m.name: m.icon for p in projects for m in p.members if m.icon}
        self.dashboard_view.show(data, self.dashboard_kind, icons)
```

  (`icons` は、横断のときは全プロジェクトのメンバーのアイコン〔先に見つかったもの〕。`dict` の後勝ちを避けるため、`for p in reversed(projects)` で組む。)
- ハンドラ:

```python
    def change_dashboard_cross(self, on: bool) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cross = on
        self.refresh_dashboard()

    def change_dashboard_project(self, name: str, included: bool) -> None:
        if self.dashboard_kind is None:
            return
        (self.dashboard_excluded.discard if included else self.dashboard_excluded.add)(name)
        self.refresh_dashboard()
```

- [ ] **Step 4: 通ることを確認する(ダッシュボード関連の既存テストを含む)**

Run: `uv run pytest test/test_views.py test/test_dashboard_view.py test/test_dashboard.py test/test_portfolio.py -q`
Expected: PASS(全件)

- [ ] **Step 5: 全体のテストと型チェック、コミット**

```bash
uv run pytest -n auto -q
uv run ty check src
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: ダッシュボードで全プロジェクトを重ねる操作をつなぐ(要望31)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 文書

**Files:**
- Modify: `CLAUDE.md`(ダッシュボードの節の「人ごとの負荷」)
- Modify: `docs/development.md`(モジュール表に `portfolio.py`)
- Modify: `.claude/MEMORY.md`(要望 31 を完了にする。冒頭の「未着手は…」から 31 を外す)
- Modify: `docs/requests.md`(要望 31 に状態の行)
- Modify: `docs/superpowers/specs/2026-10-21-cross-project-load-design.md`(状態を「実装済み」にする)

- [ ] **Step 1: `CLAUDE.md` に追記する**

ダッシュボードの節の末尾(「集計は、表示のたびに…」の前)に次を足す。

```
- 期間の横の`全プロジェクト`のスイッチ(初期値はオフ。保存しない)をオンにすると、`人ごとの負荷`が、格納先の全プロジェクトを重ねた値になる。同じ名前のメンバーを同一人物とみなし、各タスクの期間はそのプロジェクト自身の稼働設定で求めて、日時のまま重ねる。行を開くと、プロジェクト別の平均・最大が出る。プロジェクトごとのチェックで重ねるのから外せる(保存しない)。開いているプロジェクトはメモリ上の内容、ほかは保存済みの内容。読めないファイルは名前と理由を出し、残りで集計する。メンバーのプルダウンは、全プロジェクトの和集合になる。ほかのカードは、開いているプロジェクトのまま
```

- [ ] **Step 2: `docs/development.md` のモジュール表に追記する**

`dashboard_view.py` の行の下に:

```
| `portfolio.py` | 格納先の、開いているプロジェクト以外のプロジェクトを読む(`load_others`。読めないものは `LoadFailure` に集める)。ダッシュボードの横断の負荷(`dashboard.summarize_cross_loads`)が使う。NiceGUI に依存しない |
```

- [ ] **Step 3: `MEMORY.md`・`requests.md`・設計書の状態を更新する**

`MEMORY.md` の 31 を `(完了。<PR 番号>。実機確認は未)` に書き換え、冒頭の「未着手は 5・24・30・31・35…」から 31 を外す。`docs/requests.md` の要望 31 の見出しの下に `> **状態**: 実装済み(2026-10-21)。設計書 ...` を足す。設計書の状態行を `実装済み` にする。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "docs: 要望31の仕様と記録を反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** 集計(Task 1)・読込(Task 2)・画面のスイッチ/チェック/内訳/注記/失敗(Task 3)・状態の保存しない/開き直しでリセット/プルダウンの和集合/格納先を読めないとき(Task 4)・文書(Task 5)。「1 件のとき `summarize_loads` と一致」「重ならなければ足されない」「終了を数えない」「稼働設定違い」「絞り込み」はすべて Task 1 のテストにある。
- **Placeholder scan:** なし。
- **Type consistency:** `CrossLoad.total`/`by_project`、`ProjectLoad.project/average/peak`、`CrossSummary.loads/projects/excluded/failures`、`LoadFailure.name/reason`、`DashboardView` の新引数の順(`on_cross_change`, `on_project_change`)、`views` のメソッド名は各 Task で一致している。
