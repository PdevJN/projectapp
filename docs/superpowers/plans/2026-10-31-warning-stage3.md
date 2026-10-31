# 警告の状態 段階 3(要望 98 の `警告を含む` ボタン)実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードの `残りの工数と必要人数` で、遅れの判定を `遅延のみ`(予定超過)と `警告を含む`(予定超過と警告)で切り替えられるようにする。

**Architecture:** `dashboard.py` に `LateBasis`(`遅延のみ`・`警告を含む`)を足し、`_is_late` に渡す。基準は `summarize_backlog` / `summarize_cross_backlog` / `summarize` の引数で受け、結果の `Backlog.late_basis` に持たせる(画面は、これを見てボタンの選択を描く)。基準の状態は `MainView.dashboard_late_basis` に持ち、保存せず、ビューにも入れず、ダッシュボードを開くたびに `遅延のみ` に戻す。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、`ty`

**Spec:** [`docs/superpowers/specs/2026-10-31-warning-status-design.md`](../specs/2026-10-31-warning-status-design.md)(「要望 98 の `警告を含む` ボタン」。段階 1・2 はマージ済み)

## Global Constraints

- 切り替えは表示だけ。保存しない。ダッシュボードのビュー(`dashboard_views`)に入れない。ダッシュボードを開き直すと `遅延のみ`。ビューを切り替えても変えない(作業中の条件ではなく、このカードだけの表示の選択)。
- `遅延のみ` の結果は、今までと完全に同じ(既存のテストがそのまま通る)。
- `警告を含む` で遅れに数えるのは、予定超過のタスクと、警告のタスク(段階 1 の `pace.warning_pace`。参照先ではなく、集計するプロジェクト自身の稼働設定・祝日・イベントで判定する)。警告のタスクと予定超過のタスクは重ならない(警告は予定超過を除く)ので、二重に数えない。
- 遅れの分の工数は、そのタスクが集計に入れた残りの工数(`portion`)そのもの。見込み超過分(`残り − 稼働量`)だけではない。期間(`今週`・`今月`・`指定`)で按分したときは、按分した分だけ数える(遅れの工数が、合計の `hours` を超えない)。
- 見出しは `警告を含む` のとき `うち遅延・警告 N 件・X.Xh`(遅れがなければ `遅れなし`)。`遅れがなければ …` の比較の文言は変えない(中身は、選んだ基準で遅れを除いた不足)。凡例 `うち遅れ`・棒の色は変えない。
- メンバー・チームの絞り込みと `全プロジェクト` は、今までと同じに従う(`全プロジェクト` では各プロジェクトのタスクを、そのプロジェクト自身の設定で判定する)。
- 画面の文言に「要望 N」・「未実装」は残さない(ボタンのラベルは `警告を含む`、ホバーの `未実装です…` は消す)。
- 実装のたびに `uv run pytest -m smoke`。PR の前は `uv run pytest -n auto` と `uv run ty check src`(診断は変更前と同じ 1 件)。

## Review Focus

- `遅延のみ` が今までと同じ数字を出すこと(既定の引数を省略した呼び出しの結果が変わらない)。
- 警告のタスクが、`遅延のみ` では遅れに数えられず、`警告を含む` でだけ数えられること。予定超過のタスクが両方で 1 回だけ数えられること。
- 期間で按分したとき、遅れの工数が合計を超えないこと(`overdue_hours <= hours`)。
- `全プロジェクト` で、参照先ではなく重ねたプロジェクトそれぞれの設定で判定されること。
- ダッシュボードを閉じて開き直すと `遅延のみ` に戻ること。ビューの切り替えでは戻らないこと。5 分ごとの再集計で選択が保たれること。
- 選択中のボタンをもう一度押しても何も起きない(再集計の無駄を避けるだけで、壊れない)こと。

## ファイル構成

| ファイル | 内容 |
|---|---|
| `src/projectapp/dashboard.py` | `LateBasis`、`Backlog.late_basis`、`_is_late(basis)`、`_backlog_parts`・`summarize_backlog`・`summarize_cross_backlog`・`summarize` に基準の引数 |
| `src/projectapp/dashboard_view.py` | ボタンの有効化・選択の描き、見出しの文言、`on_late_basis_change` |
| `src/projectapp/views.py` | `dashboard_late_basis`・`change_dashboard_late_basis`・集計への受け渡し・開くときのリセット |
| `test/test_dashboard_backlog.py`・`test_dashboard_view.py`・`test_views.py` | テスト |
| `CLAUDE.md`・`docs/work-log.md`・`docs/requests.md`・`docs/request-history.md` | 仕様と記録 |

---

### Task 1: 集計に遅れの基準(`LateBasis`)を足す

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Test: `test/test_dashboard_backlog.py`

**Interfaces:**
- Consumes: `pace.warning_pace`(`dashboard.py` に import 済み)
- Produces:
  - `LateBasis(StrEnum)`: `DELAY = "遅延のみ"`、`WARNING = "警告を含む"`
  - `Backlog.late_basis: LateBasis = LateBasis.DELAY`(`overdue_count` の次)
  - `_is_late(task, project, holidays, now, schedule, basis=LateBasis.DELAY) -> bool`
  - `summarize_backlog(..., member=None, basis=LateBasis.DELAY)`・`summarize_cross_backlog(..., member=None, basis=LateBasis.DELAY)`・`summarize(..., children=None, late_basis=LateBasis.DELAY)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_backlog.py` の `test_a_deadline_past_counts_as_overdue` の後ろに足す。`NOW`・`WEEK`・`project_of`・`todo` は既存。`from projectapp.dashboard import (...)` に `LateBasis`・`summarize_cross_backlog` を足す(なければ)。計算の根拠: 月曜 9:00 開始の 19.5h・進捗 50% は、`NOW`(水曜の昼)で残り 9.75h に対し稼働量 3.5h なので警告(段階 1 のテストと同じ数字)。

```python
MON = datetime(2026, 10, 5, 9)


def warned_todo(name: str = "警告", **kwargs: object) -> Task:
    return Task(name, planned_start=MON, effort_hours=19.5, progress=50, status=Status.RUNNING, **kwargs)  # type: ignore[arg-type]


def test_the_default_basis_leaves_a_warning_task_out_of_the_late_part() -> None:
    project = project_of(warned_todo())
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {})
    assert (backlog.overdue_hours, backlog.overdue_count, backlog.late_basis) == (0, 0, LateBasis.DELAY)


def test_the_warning_basis_counts_a_warning_task_as_late_with_its_whole_rest() -> None:
    project = project_of(warned_todo())
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.WARNING)
    assert backlog.hours == pytest.approx(9.75)
    assert (backlog.overdue_hours, backlog.overdue_count) == (pytest.approx(9.75), 1)  # 見込み超過分ではなく、残りの全量
    assert backlog.late_basis is LateBasis.WARNING


def test_an_overdue_task_is_counted_once_on_the_warning_basis() -> None:
    project = project_of(todo("遅れた", 6.5), warned_todo())
    delay = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.DELAY)
    both = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.WARNING)
    assert (delay.overdue_count, delay.overdue_hours) == (1, 6.5)
    assert (both.overdue_count, both.overdue_hours) == (2, pytest.approx(6.5 + 9.75))


def test_the_late_part_never_exceeds_the_total_when_the_period_cuts_the_task() -> None:
    project = project_of(warned_todo(), todo("先の作業", 8))
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}, basis=LateBasis.WARNING)
    assert 0 <= backlog.overdue_hours <= backlog.hours + 1e-9


def test_shortfall_without_late_uses_the_chosen_basis() -> None:
    project = project_of(warned_todo(), members=[Member("田中", 1.0)])
    delay = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.DELAY)
    both = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.WARNING)
    assert delay.shortfall_without_overdue == delay.shortfall  # 遅れなし → 差し引く分がない
    assert both.shortfall_without_overdue is not None and both.shortfall is not None
    assert both.shortfall_without_overdue < both.shortfall  # 警告の分を除いた不足は小さい


def test_cross_backlog_judges_each_project_with_its_own_settings() -> None:
    # 同じタスクでも、稼働可能時間が 3.25h の別プロジェクトでは完了予定が遅くなり、警告にならない
    own = project_of(warned_todo())
    other = Project("別", base_date=date(2026, 10, 5), daily_hours=3.25, members=[Member("田中", 1.0)], tasks=[warned_todo()])
    only_own = summarize_cross_backlog([own], own, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.WARNING)
    both = summarize_cross_backlog([own, other], own, WEEK, PeriodKind.ALL, NOW, {}, basis=LateBasis.WARNING)
    assert only_own.overdue_count == 1
    assert both.overdue_count == 1  # 別のプロジェクトのタスクは、そのプロジェクトの設定では警告にならない
```

(`Status`・`Project`・`Member`・`date`・`pytest` が import されていなければ足す。`summarize_cross_backlog` の引数は `(projects, base, period, kind, now, holidays, member=None)`。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_backlog.py -q -n 0 -k "basis or late_part or cross_backlog_judges"`
Expected: FAIL(`ImportError: cannot import name 'LateBasis'`)

- [ ] **Step 3: 実装する**

`dashboard.py`:

1. `PeriodKind` の近く(クラス定義の並び)に:

```python
class LateBasis(StrEnum):
    """遅れの判定の基準(要望 98・103)。`警告を含む` は、予定超過のほかに、警告のタスクも遅れに数える。"""

    DELAY = "遅延のみ"
    WARNING = "警告を含む"
```

2. `Backlog` の `overdue_count` の次に `late_basis: LateBasis = LateBasis.DELAY  # 遅れの判定の基準`。
3. `_is_late` を:

```python
def _is_late(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule,
    basis: LateBasis = LateBasis.DELAY,
) -> bool:
    """遅れたタスクか(要望 98)。予定超過(ガントチャートの赤みと同じ判定)。`警告を含む` なら、警告のタスクも数える。"""
    if is_overdue(task, project, holidays, now, schedule):
        return True
    return basis is LateBasis.WARNING and warning_pace(task, project, holidays, now, schedule) is not None
```

4. `_backlog_parts(project, period, kind, now, holidays, member, basis=LateBasis.DELAY)`: `late = _is_late(task, project, holidays, now, schedule, basis)`。
5. `_assemble_backlog(..., supply_from, basis=LateBasis.DELAY)`: `Backlog(...)` の最後の引数 `sum(part.overdue_count ...)` の次に `basis` を渡す(`late_basis` は `overdue_count` の次のフィールド)。
6. `summarize_backlog(..., member=None, basis=LateBasis.DELAY)`: `_backlog_parts(..., member, basis)`・`_assemble_backlog(..., basis)`。`summarize_cross_backlog` も同様(`parts = [_backlog_parts(p, ..., member, basis) for p in projects]`)。
7. `summarize(..., children=None, late_basis=LateBasis.DELAY)`: `summarize_backlog(project, period, kind, now, holidays, scope, late_basis)`。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard_backlog.py test/test_dashboard.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS(`遅延のみ` の既存のテストは、そのまま通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard_backlog.py
git commit -m "feat: 残りの工数の遅れの判定に、警告を含める基準(LateBasis)を足す"
```

---

### Task 2: カードのボタンと見出し

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`DashboardView.__init__`・`backlog_card` の見出し・`late_line`)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `LateBasis`・`Backlog.late_basis`(Task 1)
- Produces: `DashboardView(..., on_late_basis_change: Callable[[LateBasis], object] | None = None)`。マーカー: ボタン `dashboard-backlog-late-delay`・`dashboard-backlog-late-warning`(今までと同じ)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py`:
- 先頭の `from projectapp.dashboard import (...)` に `LateBasis` を足す。
- `mount` に `late_basis_changes: list[LateBasis] | None = None` を足して `DashboardView(..., on_late_basis_change=late_basis_changes.append if late_basis_changes is not None else None)` に渡す(既存の呼び出しは変えない)。
- `test_the_warning_basis_is_not_selectable_yet` を次の 3 件に置き換える:

```python
async def test_both_late_bases_are_selectable_and_the_current_one_is_filled(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    delay = next(iter(user.find(marker="dashboard-backlog-late-delay").elements))
    warning = next(iter(user.find(marker="dashboard-backlog-late-warning").elements))
    assert delay.props.get("disable") is None and warning.props.get("disable") is None
    assert delay.text == "遅延のみ" and warning.text == "警告を含む"  # 「未実装」は残さない
    assert "outline" not in delay.props and "outline" in warning.props  # 選んでいる側が塗りつぶし


async def test_the_warning_basis_button_is_filled_when_chosen(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], late_basis=LateBasis.WARNING)
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    delay = next(iter(user.find(marker="dashboard-backlog-late-delay").elements))
    warning = next(iter(user.find(marker="dashboard-backlog-late-warning").elements))
    assert "outline" in delay.props and "outline" not in warning.props


async def test_pressing_the_other_basis_notifies_and_the_current_one_does_nothing(user: User) -> None:
    changes: list[LateBasis] = []
    views, _, _ = mount(late_basis_changes=changes)
    await user.open("/")
    views[0].show(with_backlog(Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)])), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-late-basis")
    user.find(marker="dashboard-backlog-late-delay").click()  # 選んでいる側
    assert changes == []
    user.find(marker="dashboard-backlog-late-warning").click()
    assert changes == [LateBasis.WARNING]


async def test_the_headline_names_warnings_on_the_warning_basis(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    backlog = Backlog(20.0, 0, 2, 4.0, 3.0, [("田中", 20.0)], overdue_hours=10.0, overdue_count=2, late_basis=LateBasis.WARNING)
    views[0].show(with_backlog(backlog), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 20.0h(うち遅延・警告 2 件・10.0h)"
    clean = Backlog(6.5, 0, 3, 1.0, 1.5, [("田中", 6.5)], late_basis=LateBasis.WARNING)
    views[0].show(with_backlog(clean), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-backlog-hours")
    assert text(user, "dashboard-backlog-hours") == "残りの工数 6.5h(遅れなし)"
```

(`user.find(...).click()` で `ui.button` の `on_click` が呼ばれることは、他のダッシュボードのテスト〔`dashboard-view-save` のクリックなど〕で使われている形。`props` に `outline` が `True` として入るか、文字列で入るかは `ui.button(...).props("outline")` の仕様で、`"outline" in element.props` で確かめる。違えば `element.props.get("outline") is not None` に直す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -n 0 -k "late_basis or both_late or headline_names"`
Expected: FAIL(`on_late_basis_change` が未定義、ボタンが `disable`)

- [ ] **Step 3: 実装する**

`dashboard_view.py`:
1. import に `LateBasis` を足す(`from projectapp.dashboard import (...)`)。
2. `DashboardView.__init__` の引数に `on_late_basis_change: Callable[[LateBasis], object] | None = None` を足し、`self.on_late_basis_change = on_late_basis_change`。
3. 見出し(`late = f"うち遅延 {backlog.overdue_count} 件..."`、792 行付近)を:

```python
            label = "遅延・警告" if backlog.late_basis is LateBasis.WARNING else "遅延"
            late = f"うち{label} {backlog.overdue_count} 件・{backlog.overdue_hours:.1f}h" if backlog.overdue_count else "遅れなし"
```

4. `late_line` のボタン群を:

```python
        with ui.button_group().props("flat dense").mark("dashboard-backlog-late-basis"):
            for basis, marker in ((LateBasis.DELAY, "delay"), (LateBasis.WARNING, "warning")):
                chosen = backlog.late_basis is basis
                props = "dense no-caps color=primary size=sm" + ("" if chosen else " outline")
                ui.button(basis.value, on_click=lambda b=basis: self.pick_late_basis(b)).props(props).mark(
                    f"dashboard-backlog-late-{marker}"
                )
```

   docstring の「警告を含める選択は、…押せない。」の文を消し、`遅れの判定の選択(遅延のみ・警告を含む)を置く。` にする。選択を返す関数を足す:

```python
    def pick_late_basis(self, basis: LateBasis) -> None:
        """遅れの判定の基準を選ぶ。今の基準と同じなら何もしない。"""
        if self.data is not None and self.data.backlog.late_basis is basis:
            return
        if self.on_late_basis_change is not None:
            self.on_late_basis_change(basis)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: 残りの工数のカードで、遅れの判定に警告を含める選択を有効にする"
```

---

### Task 3: メイン画面の状態とつなぐ

**Files:**
- Modify: `src/projectapp/views.py`
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `LateBasis`(Task 1)、`DashboardView(on_late_basis_change=...)`(Task 2)
- Produces: `MainView.dashboard_late_basis: LateBasis`・`MainView.change_dashboard_late_basis(basis: LateBasis) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `test_the_cross_switch_overlays_the_other_projects_in_the_storage` の近く(`open_dashboard_view`・`text_of` を使うテストの並び)に足す。`warning` のタスクが 1 件あるプロジェクトを、そのテストのファイルにある既存の組み立て(`open_dashboard_view(user, tmp_path)` が返す `view` の `view.project` を書き換える形。`view.project.tasks` に追加し、`view.now = lambda: datetime(2026, 10, 7, 12)` で今を固定する)で用意する:

```python
def warned_dashboard_project(view: MainView) -> None:
    view.project.members = [Member("田中", 1.0)]
    view.project.tasks = [
        Task("警告", planned_start=datetime(2026, 10, 5, 9), effort_hours=19.5, progress=50, status=Status.RUNNING)
    ]
    view.now = lambda: datetime(2026, 10, 7, 12)  # 水曜の昼


async def test_the_late_basis_defaults_to_delay_and_switches_the_backlog_card(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    warned_dashboard_project(view)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-backlog-hours")
    assert view.dashboard_late_basis is LateBasis.DELAY
    assert text_of(user, "dashboard-backlog-hours").endswith("(遅れなし)")
    view.change_dashboard_late_basis(LateBasis.WARNING)
    await asyncio.sleep(0.3)  # refresh は遅延実行なので、描き直されるのを待つ
    assert "うち遅延・警告 1 件" in text_of(user, "dashboard-backlog-hours")


async def test_the_late_basis_goes_back_to_delay_when_the_dashboard_is_reopened(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    warned_dashboard_project(view)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-backlog-hours")
    view.change_dashboard_late_basis(LateBasis.WARNING)
    view.close_dashboard()
    view.open_dashboard()
    assert view.dashboard_late_basis is LateBasis.DELAY


async def test_switching_the_dashboard_view_keeps_the_late_basis(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-backlog-hours")
    view.change_dashboard_late_basis(LateBasis.WARNING)
    view.select_dashboard_view(STANDARD_NAME)
    assert view.dashboard_late_basis is LateBasis.WARNING


async def test_the_late_basis_is_not_saved_in_the_dashboard_view(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-backlog-hours")
    view.change_dashboard_late_basis(LateBasis.WARNING)
    assert not view.dashboard_view_dirty()  # 基準を変えても「変更あり」(●)にならない
```

(`open_dashboard_view`・`text_of` はそのファイルの既存のヘルパー。「変更あり」の判定の関数名は `grep -n "dirty" src/projectapp/views.py` で確かめて合わせる〔`dashboard_view_dirty` が無ければ、`view.dashboard_view_state()` の `dirty` を使う〕。`LateBasis`・`STANDARD_NAME`・`Member`・`Task`・`Status`・`datetime` は import に足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -n 0 -k "late_basis"`
Expected: FAIL(`dashboard_late_basis` が無い)

- [ ] **Step 3: 実装する**

`views.py`:
1. `from projectapp.dashboard import (...)` に `LateBasis` を足す。
2. `self.dashboard_cross = False` の次の行に `self.dashboard_late_basis = LateBasis.DELAY  # 残りの工数の遅れの判定。保存しない・ビューに入れない`。
3. `DashboardView(...)` の引数に `on_late_basis_change=self.change_dashboard_late_basis,` を足す。
4. `open_dashboard` の `self.dashboard_kind = PeriodKind.WEEK` の次の行に `self.dashboard_late_basis = LateBasis.DELAY`(開き直すと `遅延のみ`)。`apply_dashboard_view` では触らない。
5. `refresh_dashboard` の `summarize(...)` の呼び出しに、`children` の次の引数として `self.dashboard_late_basis` を渡す(`late_basis=`)。`summarize_cross_backlog(...)` の呼び出しの最後に `basis=self.dashboard_late_basis` を足す。
6. `change_dashboard_cross` の近くに:

```python
    def change_dashboard_late_basis(self, basis: LateBasis) -> None:
        """残りの工数の遅れの判定の基準を切り替える。表示だけで、保存しない(ビューにも入れない)。"""
        if self.dashboard_kind is None or basis is self.dashboard_late_basis:
            return
        self.dashboard_late_basis = basis
        self.refresh_dashboard()
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_views.py test/test_dashboard_view.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: 確認用データと見た目の確認(目視)**

`docs/samples/警告の確認.json`(「今」= 2026-11-04 12:00)をそのまま使う。`FAKE_NOW=2026-11-04T12:00` で起動し、`D` でダッシュボード、期間を `全期間` にして、`残りの工数と必要人数`:
- 初期は `遅延のみ` が塗りつぶしで、見出しが `残りの工数 …h(うち遅延 1 件・6.5h)`(予定超過の 1 件)。
- `警告を含む` を押すと、見出しが `うち遅延・警告 4 件・…h` に変わり、必要の棒の遅れ(赤橙)が伸び、`遅れがなければ …` の数字が変わる。
- `遅延のみ` に戻すと元の数字に戻る。ダッシュボードを閉じて開き直すと `遅延のみ`。ビューの `保存`/`●` は、基準を変えても出ない。
- `全プロジェクト` をオンにしても、ボタンが動くこと。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: ダッシュボードの遅れの判定の基準を、画面の状態としてつなぐ"
```

---

### Task 4: 仕様と記録を更新する

**Files:**
- Modify: `CLAUDE.md`・`docs/work-log.md`・`docs/requests.md`・`docs/request-history.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

`## ダッシュボード` の、`残りの工数と必要人数`の長い項の中の `遅れの判定の選択(`遅延のみ`・`警告を含む`)のボタンを置き、`警告を含む(未実装)`は押せない(警告の状態を作るときに有効にする。選択はまだ保存しない)。` を、次に置き換える:

```
遅れの判定の選択(`遅延のみ`・`警告を含む`)のボタンを置く。`警告を含む`は、予定超過のほかに、警告のタスク(ガントチャートと同じ判定。集計するプロジェクト自身の設定で判定する)も遅れに数える(遅れの工数は、そのタスクが集計に入れた残りの工数そのもので、期間で按分したときは按分した分。見込み超過分だけではない)。見出しは`うち遅延・警告 5 件・38.0h`になり、`遅れがなければ …`の比較も、選んだ基準で遅れを除いた不足を示す。選択は表示だけで、保存せず、ビューにも入れない(ダッシュボードを開き直すと`遅延のみ`。ビューを切り替えても変えない)。
```

- [ ] **Step 2: ほかの文書を更新する**

- `docs/requests.md`: 要望 98 の項の、`「警告を含む」の選択は要望 103 で有効にする(今は押せない)` を `「警告を含む」の選択は要望 103 の段階 3 で有効にした` に直す。要望 103 の状態を `完了(段階 1: PR #161、段階 2: PR #162、段階 3: PR 作成中)` の形に更新する(PR 番号は作成後に入れる)。`docs/request-history.md` の 98・103 の行も同様。
- `docs/work-log.md` の末尾に、段階 3 の記録(基準を`Backlog.late_basis`に持たせて画面の状態を持たないこと、状態は`MainView`に持ち保存しないこと、遅れの工数を`portion`にした理由〔見込み超過分ではなく、集計に入れた残りの工数。期間で按分したとき合計を超えないため〕、確認用データ、テスト件数)を足す。

- [ ] **Step 3: 全体の確認**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS。`ty` の診断は変更前と同じ 1 件。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs
git commit -m "docs: 要望 103 の段階 3 の仕様と記録を更新する"
```

---

## Self-Review

**Spec coverage**(設計書の「要望 98 の `警告を含む` ボタン」):
- ボタンを有効にして、`遅延のみ`・`警告を含む` を切り替える → Task 2
- 切り替えると `残りの工数と必要人数` を集計し直す → Task 1(集計)・Task 3(再集計)
- 表示だけで保存しない・ビューに入れない・開き直すと `遅延のみ` → Task 3
- 見出し `うち遅延・警告 5 件・38.0h` → Task 2
- 警告のタスクは残りの工数の全量を数える → Task 1(`portion`。ruling は Global Constraints に明記: 期間で按分したときは按分した分)
- 遅れの判定を `_is_late` に `LateBasis` を渡す形 → Task 1
- `遅れがなければ` の比較は、警告を除いた不足 → Task 1(`shortfall_without_overdue` が `overdue_required` から計算されるので、基準を変えるだけで追従する)

**Placeholder scan:** Task 3 のテストの組み立て(`open_dashboard_view`・`text_of`・「変更あり」の判定の関数名)は、既存のヘルパーに合わせる指示で、探し方(`grep`)を書いた。それ以外に TBD はない。

**Type consistency:** `LateBasis.DELAY`/`WARNING` は Task 1 で定義し、Task 2 の `backlog.late_basis is basis`・Task 3 の `dashboard_late_basis` が同じ名前で使う。`Backlog.late_basis` は `overdue_count` の次のフィールドで、Task 1 の `_assemble_backlog` が位置引数で渡す順と一致させる(`... overdue_hours, overdue_count, basis`)。`on_late_basis_change` は Task 2 で定義し、Task 3 が渡す。

**Review Focus:** `遅延のみ` の同一性(Task 1 の既存テストが通ること)、警告のタスクの扱い(`test_the_default_basis_...`・`test_the_warning_basis_counts_...`)、二重に数えない(`test_an_overdue_task_is_counted_once_...`)、按分(`test_the_late_part_never_exceeds_...`)、全プロジェクト(`test_cross_backlog_judges_...`)、開き直しとビューの切り替え(Task 3 の 3 件)、選んでいるボタンの再押下(Task 2 `test_pressing_the_other_basis_...`)をそれぞれ押さえている。
