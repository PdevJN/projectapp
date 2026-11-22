# アサイン専用画面 段階 5(負荷のヒストグラム)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面のチャートの下に、担当メンバーごとの稼働日ごとの負荷の棒(ヒストグラム)を、開閉できるエクスパンダーで出す。割り当てを変えるたびに描き直す。

**Architecture:** 計算は`dashboard.py`の純粋関数`daily_loads`(`_member_spans`・`_day_totals`・`_workdays`を再利用)。SVG と要約の文字列は NiceGUI に依存しない新しいモジュール`assign_load.py`(`dashboard_view.py`の`LOAD_COLOR`・`OVER_COLOR`・`LOAD_SCALE`を使う)。画面は`AssignScreen`に、エクスパンダー・メンバーのアイコンのトグル・行の描画を足し、`refresh`から呼ぶ。負荷の計算には、元のプロジェクトの複製に試算のタスクを`apply_trial`で差し戻したものを使う。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-22-assign-screen-stage5-design.md`(段階 1〜3b は`docs/superpowers/specs/2026-11-22-assign-screen-stage{1,2,3a,3b}-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。試算は保存しない。負荷の表示は試算に含めず、`is_dirty`は変えない
- 負荷の数え方はダッシュボードの`人ごとの負荷`と同じ(同時刻の割り当て率の合計の最大・終了したタスクは数えない・メンバーごとの稼働日の上書きを反映)。棒は 0〜200% で固定(`LOAD_SCALE`)
- SVG は自前で描く(外部のグラフライブラリは使わない)。マーカーは`assign-`で始める。ダイアログは再描画される要素の中で作らない
- メインのチャート・ダッシュボードの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは git-flow。設計書・計画のブランチ`docs/request-168-stage5-design`から`feature/request-168-stage5`を切る。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差・補足)

- SVG と要約の文字列は、画面から切り離してテストできるよう、新しいモジュール`assign_load.py`に置く(設計書は`assign_screen.py`の中に書いていた)
- 超過の色は、`dashboard_view.py`の既存の定数`LOAD_COLOR`・`OVER_COLOR`・`LOAD_SCALE`を import して共有する(設計書の「確かめること」への回答)
- 棒の幅は 4px・すき間 1px・高さ 48px の固定。稼働日が多い行は、行の中で横スクロールする
- 負荷の計算は、エクスパンダーが開いているときだけ行う。閉じている間の変更は、開いたときに描く
- 担当メンバー(トグルと行の対象)は、試算のタスクの`assignees`の名前(`union_assignees`の結果)

## Review Focus

- 試算で割り当てを変えたとき、その人の棒が変わる。元のプロジェクト(`self.project`)は変わらない
- 同じ期間に別のタスクが重なると、100% を超えて超過の色になる。終了したタスクは数えない
- 稼働日の上書き(休み)の日は、棒の並びに入らない。期間に稼働日がなければ、空の行にしない(`稼働日がありません`)
- 担当者が外れたメンバーのトグルと行が消え、隠していた選択も消える。担当者がいないタスクは`担当者がいません`
- 開始日のないタスク: `開始日がないため負荷を出せません`。エクスパンダーが閉じている間は計算しない

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/dashboard.py`(変更) | `daily_loads`を足す |
| `src/projectapp/assign_load.py`(新規) | `load_svg`・`load_summary`(文字列だけ。NiceGUI に依存しない) |
| `src/projectapp/assign_screen.py`(変更) | エクスパンダー・トグル・行・`refresh`からの描き直し |
| `test/test_dashboard_daily_loads.py`(新規)・`test/test_assign_load.py`(新規)・`test/test_assign_screen.py`(変更) | テスト |
| `.claude/spec/dashboard.md`・`docs/development.md`・`docs/requests.md`(変更) | 仕様・構成・状態表記 |

---

### Task 1: 負荷の計算(`daily_loads`)

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_loads`の次に足す)
- Test: `test/test_dashboard_daily_loads.py`(新規)

**Interfaces:**
- Consumes: 既存の`_member_spans`・`_day_totals`・`_workdays`・`_names`・`Period`・`Scope`・`work_day_map`
- Produces: `daily_loads(project: Project, holidays: dict[date, str], period: Period, member: Scope = None) -> dict[str, list[tuple[date, float]]]`(メンバー名 → (稼働日, 負荷)。1.0 = 100%。メンバーの順は`project.members`)

- [ ] **Step 1: Write the failing tests**

`test/test_dashboard_daily_loads.py`:

```python
from datetime import date, datetime

from projectapp.dashboard import Period, daily_loads, summarize_loads
from projectapp.models import Assignee, Member, Project, Status, Task, WorkDay

WEEK = Period(date(2026, 11, 16), date(2026, 11, 22))  # 月〜日


def task(task_id: str, *assignees: Assignee, status: Status = Status.NOT_STARTED) -> Task:
    return Task(
        task_id,
        id=task_id,
        planned_start=datetime(2026, 11, 16, 9),
        planned_end=datetime(2026, 11, 20, 17),
        effort_hours=40,
        assignees=list(assignees),
        status=status,
    )


def project(*tasks: Task, members: list[Member] | None = None) -> Project:
    return Project(
        "p",
        base_date=date(2026, 11, 16),
        members=members or [Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=list(tasks),
    )


def values(loads: dict[str, list[tuple[date, float]]], name: str) -> list[float]:
    return [round(total, 2) for _, total in loads[name]]


def test_a_single_task_loads_each_workday_of_the_assignee() -> None:
    loads = daily_loads(project(task("a", Assignee("田中"))), {}, WEEK)
    assert [day for day, _ in loads["田中"]] == [date(2026, 11, d) for d in range(16, 21)]
    assert values(loads, "田中") == [1.0] * 5
    assert values(loads, "鈴木") == [0.0] * 5


def test_overlapping_tasks_add_up_and_exceed_100_percent() -> None:
    both = project(task("a", Assignee("田中")), task("b", Assignee("田中", 0.5)))
    assert max(values(daily_loads(both, {}, WEEK), "田中")) > 1.0


def test_finished_tasks_are_not_counted() -> None:
    done = project(task("a", Assignee("田中"), status=Status.DONE))
    assert values(daily_loads(done, {}, WEEK), "田中") == [0.0] * 5


def test_a_day_off_is_left_out_of_the_workdays() -> None:
    off = Member("田中", 1.0, work_days=[WorkDay(date(2026, 11, 18))])
    loads = daily_loads(project(task("a", Assignee("田中")), members=[off]), {}, WEEK)
    assert date(2026, 11, 18) not in {day for day, _ in loads["田中"]}
    assert len(loads["田中"]) == 4


def test_a_period_without_workdays_gives_an_empty_list() -> None:
    weekend = Period(date(2026, 11, 21), date(2026, 11, 22))
    loads = daily_loads(project(task("a", Assignee("田中"))), {}, weekend)
    assert loads["田中"] == []


def test_the_member_scope_limits_the_result() -> None:
    loads = daily_loads(project(task("a", Assignee("田中"))), {}, WEEK, "田中")
    assert list(loads) == ["田中"]
    assert daily_loads(project(), {}, WEEK, frozenset({"いない人"})) == {}


def test_it_agrees_with_summarize_loads() -> None:
    both = project(task("a", Assignee("田中")), task("b", Assignee("田中", 0.5)))
    totals = [total for _, total in daily_loads(both, {}, WEEK)["田中"]]
    stats = summarize_loads(both, WEEK, {})["田中"]
    assert round(sum(totals) / len(totals), 6) == round(stats.average, 6)
    assert round(max(totals), 6) == round(stats.peak, 6)
    assert sum(1 for t in totals if t > 1.0 + 1e-9) == stats.overload_days
```

`Status`・`WorkDay`・`Member(work_days=…)`の名前や引数が違って import が通らないときは、`test/test_dashboard_backlog.py`(`WorkDay`・`Status`の使い方)に合わせる。重なりのテストで 100% を超えないときは、2 つ目のタスクの`Assignee("田中", 1.0)`にする。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_dashboard_daily_loads.py -q 2>&1 | tail -5`
Expected: FAIL(`ImportError: cannot import name 'daily_loads'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/dashboard.py`の`summarize_loads`の次に足す。

```python
def daily_loads(
    project: Project,
    holidays: dict[date, str],
    period: Period,
    member: Scope = None,
) -> dict[str, list[tuple[date, float]]]:
    """アサイン専用画面(要望 168 段階 5): メンバーごと・稼働日ごとの負荷(同時刻の割り当て率の合計の最大。1.0 = 100%)。

    数え方は`summarize_loads`と同じ(終了したタスクは数えない・メンバーごとの稼働日の上書きを反映)。
    稼働日がなければ空のリスト。`member`で対象のメンバーを絞る。"""
    spans = _member_spans(project, holidays, member)
    scoped = _names(member)
    result: dict[str, list[tuple[date, float]]] = {}
    for entry in project.members:
        if scoped is not None and entry.name not in scoped:
            continue
        days = _workdays(period, holidays, work_day_map(entry.work_days))
        result[entry.name] = list(zip(days, _day_totals(spans.get(entry.name, []), days)))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_dashboard_daily_loads.py -q 2>&1 | tail -5`
Expected: PASS(7 件)

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test
git switch -c feature/request-168-stage5
git add src/projectapp/dashboard.py test/test_dashboard_daily_loads.py
git commit -m "feat: メンバーごと・稼働日ごとの負荷を返す daily_loads を足す(要望 168 段階 5)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: SVG と要約(`assign_load.py`)

**Files:**
- Create: `src/projectapp/assign_load.py`
- Test: `test/test_assign_load.py`(新規)

**Interfaces:**
- Consumes: `projectapp.dashboard_view`の`LOAD_COLOR`・`OVER_COLOR`・`LOAD_SCALE`、`projectapp.timeline.OVERLOAD_EPSILON`
- Produces:
  - `BAR_PX = 4`・`BAR_GAP_PX = 1`・`CHART_HEIGHT_PX = 48`
  - `load_svg(days: list[tuple[date, float]]) -> str`
  - `load_summary(days: list[tuple[date, float]]) -> str`

- [ ] **Step 1: Write the failing tests**

`test/test_assign_load.py`:

```python
from datetime import date

from projectapp.assign_load import (
    BAR_GAP_PX,
    BAR_PX,
    CHART_HEIGHT_PX,
    load_summary,
    load_svg,
)
from projectapp.dashboard_view import LOAD_COLOR, OVER_COLOR


def days(*totals: float) -> list[tuple[date, float]]:
    return [(date(2026, 11, 16 + i), total) for i, total in enumerate(totals)]


def test_each_day_with_a_load_is_a_bar_with_a_tooltip() -> None:
    svg = load_svg(days(0.5, 1.0))
    assert svg.count("<rect") == 2
    assert "<title>11/16 50%</title>" in svg and "<title>11/17 100%</title>" in svg
    assert f'width="{2 * (BAR_PX + BAR_GAP_PX)}"' in svg


def test_a_day_without_a_load_has_no_bar() -> None:
    assert load_svg(days(0.0, 0.0)).count("<rect") == 0


def test_bars_over_100_percent_use_the_overload_color() -> None:
    svg = load_svg(days(1.0, 1.2))
    assert svg.count(f'fill="{OVER_COLOR}"') == 1
    assert svg.count(f'fill="{LOAD_COLOR}"') == 1


def test_the_bar_height_is_clamped_at_200_percent() -> None:
    svg = load_svg(days(1.0, 2.5))
    half = CHART_HEIGHT_PX / 2
    assert f'y="{half:.1f}" width="{BAR_PX}" height="{half:.1f}"' in svg  # 100%
    assert f'y="0.0" width="{BAR_PX}" height="{CHART_HEIGHT_PX:.1f}"' in svg  # 250% は端で止まる


def test_the_100_percent_reference_line_is_dotted() -> None:
    svg = load_svg(days(0.5))
    half = CHART_HEIGHT_PX / 2
    assert f'y1="{half:.1f}" y2="{half:.1f}"' in svg and "stroke-dasharray" in svg


def test_an_empty_list_still_draws_a_valid_svg() -> None:
    svg = load_svg([])
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "<rect" not in svg


def test_the_summary_names_the_peak_and_the_overloaded_days() -> None:
    assert load_summary(days(0.5, 1.3, 1.1, 1.0)) == "最大 130%・100% 超 2 日"
    assert load_summary(days(0.5, 1.0)) == "最大 100%・100% 超 0 日"
    assert load_summary([]) == "稼働日がありません"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_assign_load.py -q 2>&1 | tail -5`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.assign_load'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/assign_load.py`:

```python
"""アサイン専用画面(要望 168 段階 5)の負荷のヒストグラムの SVG と要約。文字列だけで、NiceGUI に依存しない。

棒は稼働日ごとの負荷(1.0 = 100%)。0〜200% で固定し(`LOAD_SCALE`)、100% に点線を引く。100% 超の棒は超過の色にする。
"""

from datetime import date

from projectapp.dashboard_view import LOAD_COLOR, LOAD_SCALE, OVER_COLOR
from projectapp.timeline import OVERLOAD_EPSILON

BAR_PX = 4
BAR_GAP_PX = 1
CHART_HEIGHT_PX = 48


def load_svg(days: list[tuple[date, float]]) -> str:
    """稼働日ごとの負荷の棒。負荷が 0 の日は棒を出さない。棒にマウスを重ねると`m/d 120%`。"""
    step = BAR_PX + BAR_GAP_PX
    width = max(len(days) * step, 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{CHART_HEIGHT_PX}"'
        f' viewBox="0 0 {width} {CHART_HEIGHT_PX}" role="img" style="display: block">'
    ]
    for index, (day, total) in enumerate(days):
        if total <= 0:
            continue
        height = CHART_HEIGHT_PX * min(total, LOAD_SCALE) / LOAD_SCALE
        color = OVER_COLOR if total > 1.0 + OVERLOAD_EPSILON else LOAD_COLOR
        parts.append(
            f'<rect x="{index * step}" y="{CHART_HEIGHT_PX - height:.1f}" width="{BAR_PX}"'
            f' height="{height:.1f}" fill="{color}">'
            f"<title>{day.month}/{day.day} {total * 100:.0f}%</title></rect>"
        )
    reference = CHART_HEIGHT_PX / LOAD_SCALE
    parts.append(
        f'<line x1="0" x2="{width}" y1="{reference:.1f}" y2="{reference:.1f}"'
        ' stroke="currentColor" stroke-opacity="0.6" stroke-width="1" stroke-dasharray="3 3"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


def load_summary(days: list[tuple[date, float]]) -> str:
    """`最大 130%・100% 超 3 日`。稼働日がなければ`稼働日がありません`。"""
    if not days:
        return "稼働日がありません"
    peak = max(total for _, total in days)
    over = sum(1 for _, total in days if total > 1.0 + OVERLOAD_EPSILON)
    return f"最大 {peak * 100:.0f}%・100% 超 {over} 日"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_load.py -q 2>&1 | tail -5`
Expected: PASS(7 件)。`import projectapp.dashboard_view`が循環 import や NiceGUI の初期化で失敗するときは、`LOAD_COLOR`・`OVER_COLOR`・`LOAD_SCALE`を`assign_load.py`に同じ値で書き、`test_assign_load.py`でその値が`dashboard_view`の定数と等しいことを確かめる(ledger に Ruling を書く)。

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test
git add src/projectapp/assign_load.py test/test_assign_load.py
git commit -m "feat: アサイン画面の負荷の棒の SVG と要約(要望 168 段階 5)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面(エクスパンダー・トグル・行)

**Files:**
- Modify: `src/projectapp/assign_screen.py`
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`daily_loads`・`Period`(`projectapp.dashboard`)、Task 2 の`load_svg`・`load_summary`、`apply_trial`(`assign_trial`)
- Produces(テストが使う): `AssignScreen.load_hidden: set[str]`・`load_open: bool`・`load_project() -> Project`・`load_period() -> Period | None`・`render_load()`・`toggle_load(name)`・`on_load_toggle(value)`。マーカー: `assign-load`(エクスパンダー)・`assign-load-toggle-<name>`・`assign-load-row-<name>`・`assign-load-summary-<name>`・`assign-load-none`・`assign-load-empty`

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`の import に`from projectapp.assign_trial import AssignTrial, is_dirty`(あれば追加なし)を確かめ、末尾にテストを足す。

```python
async def test_the_load_panel_shows_a_toggle_and_a_row_for_each_assignee(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_see(marker="assign-load")
    await user.should_see(marker="assign-load-toggle-田中")
    await user.should_see(marker="assign-load-row-田中")
    summary = user.find(marker="assign-load-summary-田中").elements.pop()
    assert summary.text.startswith("最大 ")


async def test_tapping_a_toggle_hides_and_shows_the_row(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.toggle_load("田中")
    assert screen.load_hidden == {"田中"}
    await user.should_not_see(marker="assign-load-row-田中")
    await user.should_see(marker="assign-load-toggle-田中")  # トグルは残る
    screen.toggle_load("田中")
    assert screen.load_hidden == set()
    await user.should_see(marker="assign-load-row-田中")


async def test_dropping_a_member_adds_a_row_for_that_member(user: User) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_not_see(marker="assign-load-row-鈴木")
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-load-row-鈴木")
    await user.should_see(marker="assign-load-toggle-鈴木")


async def test_the_load_uses_the_trial_task_without_touching_the_original(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    loaded = screen.load_project()
    names = {a.name for a in loaded.all_tasks().__next__().assignees} if False else {
        a.name for task in loaded.all_tasks() for a in task.assignees
    }
    assert "鈴木" in names
    original = {a.name for task in screen.project.all_tasks() for a in task.assignees}
    assert "鈴木" not in original


async def test_a_removed_assignee_loses_the_toggle_and_the_hidden_mark(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.toggle_load("鈴木")
    assert "鈴木" in screen.load_hidden
    screen.remove_member_at("鈴木", 1, None)
    screen.render_load()
    assert "鈴木" not in screen.load_hidden


async def test_no_start_date_says_the_load_cannot_be_shown(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.plan = None
    screen.render_load()
    await user.should_see(marker="assign-load-none")


async def test_a_closed_panel_is_not_drawn_until_it_is_opened(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.on_load_toggle(False)
    screen.drop_member("鈴木", 1, None)
    await user.should_not_see(marker="assign-load-row-鈴木")
    screen.on_load_toggle(True)
    await user.should_see(marker="assign-load-row-鈴木")


async def test_the_load_display_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.toggle_load("田中")
    screen.on_load_toggle(False)
    assert not is_dirty(screen.trial)
```

`test_the_load_uses_the_trial_task…`の`names`の行は読みにくいので、Step 3 の前に`names = {a.name for task in loaded.all_tasks() for a in task.assignees}`だけにそろえる(`if False else`の分岐は書かない)。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_assign_screen.py -q -k "load" 2>&1 | tail -8`
Expected: FAIL(`AttributeError: … has no attribute 'toggle_load'` など)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/assign_screen.py`:

1. import: `from copy import deepcopy`を足し、`from projectapp.assign_load import load_summary, load_svg`、`from projectapp.dashboard import Period, daily_loads`、`from projectapp.assign_trial import (...)`に`apply_trial`を足す。
2. `__init__`の末尾に足す。

```python
        self.load_box: ui.element | None = None
        self.load_hidden: set[str] = set()
        self.load_open = True
```

3. `build`の、`self.build_rate_popup()`の直前(本体の行のブロックの次)に`self.build_load_panel()`を足す。
4. メソッドを足す(`# --- 割り当て率のポップアップ`の前)。

```python
    # --- 負荷のヒストグラム(要望 168 段階 5) ---

    def build_load_panel(self) -> None:
        """チャートの下の`負荷`エクスパンダー。再描画される要素の外に置く。"""
        with ui.expansion("負荷", value=True).classes("w-full").mark(
            "assign-load"
        ) as panel:
            panel.on_value_change(lambda e: self.on_load_toggle(e.value))
            self.load_box = (
                ui.column()
                .classes("w-full gap-1")
                .style("max-height: 14rem; overflow-y: auto")
            )
            self.render_load()

    def on_load_toggle(self, value: bool) -> None:
        self.load_open = bool(value)
        if self.load_open:
            self.render_load()

    def toggle_load(self, name: str) -> None:
        self.load_hidden ^= {name}
        self.render_load()

    def load_project(self) -> Project:
        """負荷の計算に使う、試算のタスクを差し戻したプロジェクトの複製。元のプロジェクトは変えない。"""
        loaded = deepcopy(self.project)
        apply_trial(loaded, self.trial)
        return loaded

    def load_period(self) -> Period | None:
        """割り当ての行のセルが覆う日付(原点から週数ぶん)。開始日がなければ None。"""
        if self.plan is None:
            return None
        weeks = max(self.plan.weeks, len(self.trial.task.weekly_crew))
        return Period(
            self.plan.origin,
            self.plan.origin + timedelta(days=WEEK_DAYS * weeks - 1),
        )

    def render_load(self) -> None:
        """担当メンバーのトグルと、メンバーごとの日ごとの負荷の棒を描き直す。閉じている間は描かない。"""
        if self.load_box is None or not self.load_open:
            return
        self.load_box.clear()
        names = [a.name for a in self.trial.task.assignees]
        self.load_hidden &= set(names)
        period = self.load_period()
        with self.load_box:
            if period is None:
                ui.label("開始日がないため負荷を出せません").classes("text-grey").mark(
                    "assign-load-none"
                )
                return
            if not names:
                ui.label("担当者がいません").classes("text-grey").mark(
                    "assign-load-empty"
                )
                return
            loads = daily_loads(
                self.load_project(), self.holidays, period, frozenset(names)
            )
            with ui.row().classes("items-center gap-1"):
                for name in names:
                    self.load_toggle(name)
            for name in names:
                if name not in self.load_hidden:
                    self.load_row(name, loads.get(name, []))

    def load_toggle(self, name: str) -> None:
        icon = next((m.icon for m in self.project.members if m.name == name), "")
        hidden = name in self.load_hidden
        avatar(name, icon, 22).tooltip(name).style(
            "cursor: pointer" + ("; opacity: 0.35" if hidden else "")
        ).on("click", lambda n=name: self.toggle_load(n)).mark(
            f"assign-load-toggle-{name}"
        )

    def load_row(self, name: str, days: list[tuple[date, float]]) -> None:
        icon = next((m.icon for m in self.project.members if m.name == name), "")
        with ui.row().classes("items-center no-wrap gap-2 w-full").mark(
            f"assign-load-row-{name}"
        ):
            avatar(name, icon, 20)
            ui.label(name).classes("text-body2").style("width: 6rem; flex: none")
            with ui.element("div").style("flex: 1 1 0; min-width: 0; overflow-x: auto"):
                ui.html(load_svg(days), sanitize=False)
            ui.label(load_summary(days)).classes("text-caption text-grey").style(
                "flex: none"
            ).mark(f"assign-load-summary-{name}")

```

5. `refresh`の末尾(メンバー一覧の再構築の次)に`self.render_load()`を足す。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py test/test_assign_load.py -q 2>&1 | tail -8`
Expected: PASS(全件)。既存のテストが、エクスパンダーの追加で落ちるときは、`user.find`のマーカーの重複(`assign-`の接頭辞は使っているが、`assign-load`が既存の`assign-load-…`と衝突していないか)を確かめる。

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test && uvx ty check src 2>&1 | tail -1
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン画面のチャートの下に、メンバーごとの負荷の棒を出す(要望 168 段階 5)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 仕様・構成・状態表記と、全体の確認

**Files:**
- Modify: `.claude/spec/dashboard.md`(要望 168 のアサイン専用画面の段落の末尾に段階 5 を足す)・`docs/development.md`(`dashboard.py`・`assign_screen.py`の行と`assign_load.py`の行)・`docs/requests.md`(要望 168 の状態)

- [ ] **Step 1: 仕様・構成・状態を書く**

- `.claude/spec/dashboard.md`: 段階 5 の説明を足す。チャートの下に開閉できる`負荷`のエクスパンダー(初期値は開く。保存しない)。この試算のタスクの担当メンバーのアイコンのトグル(タップで行を出す・隠す。初期値は全員)と、メンバーごとの行(アイコン・名前・稼働日ごとの棒・`最大 130%・100% 超 3 日`)。負荷は、プロジェクトのすべてのタスク(試算を反映。終了は数えない・稼働日の上書きを反映。`人ごとの負荷`と同じ数え方)。期間はセルが覆う日付。棒は 0〜200% で固定・100% に点線・100% 超は超過の色・ホバーに`m/d 120%`。割り当てを変えるたびに描き直す(閉じている間は描かない)。開始日がなければ`開始日がないため負荷を出せません`。確定までメインは変えない
- `docs/development.md`: `dashboard.py`の行に`daily_loads`、新しい行`assign_load.py`(負荷の棒の SVG と要約)、`assign_screen.py`の行に負荷のエクスパンダー(`build_load_panel`・`render_load`)を足す
- `docs/requests.md`の要望 168 の状態: 段階 5 は実装済み(設計書: `docs/superpowers/specs/2026-11-22-assign-screen-stage5-design.md`・計画: `docs/superpowers/plans/2026-11-22-assign-screen-stage5.md`。PR は作成後に記す。実機確認待ち)・段階 4 は未着手

- [ ] **Step 2: 全体の確認**

Run: `uv run pytest -m smoke -q 2>&1 | tail -3 && uv run pytest -q -n auto test/test_dashboard_daily_loads.py test/test_assign_load.py test/test_assign_screen.py test/test_assign_trial.py test/test_assign_drag.py test/test_daily_crew_assign.py test/test_gantt.py test/test_context_menu.py test/test_dashboard_view.py test/test_views.py 2>&1 | tail -3 && uvx ruff check src test && uvx ty check src 2>&1 | tail -1`
Expected: smoke・関連テストが通る。ty は 9 件(既存)

- [ ] **Step 3: Commit**

```bash
git add .claude/spec docs/development.md docs/requests.md
git commit -m "docs: アサイン画面の負荷のヒストグラム(段階 5)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実装後、全体のレビュー(sonnet の subagent)→ 指摘の修正 1 回 → push して PR を作って止まる(マージは利用者の指示を待つ)。
