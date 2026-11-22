# アサイン専用画面 段階 3a(割り当て率のスライダー)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面で、セルの中のメンバーのアイコンをクリックすると小さなポップアップが開き、そのセル(週・日)の割り当て率をスライダーと数値欄で変えられるようにする。

**Architecture:** 率の操作は`daily_crew.py`の純粋関数(`current_allocation`・`set_allocation`・`set_allocation_all`)。`AssignScreen`は、画面の構築時にポップアップ(小さな`ui.dialog`)を 1 つだけ作って使い回す(チャートの再描画で消えないよう、再描画される要素の外に置く)。スライダーを離したとき・数値欄の確定で試算のタスクを更新し、チャートを描き直す。率が 100% でないアイコンには角に数字を重ねる。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-22-assign-screen-stage3a-design.md`(段階 1・2 は`docs/superpowers/specs/2026-11-22-assign-screen-stage{1,2}-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。試算は保存しない。`Assignee.allocation`を使う
- 割り当て率の範囲は`MIN_ALLOCATION`〜`MAX_ALLOCATION`(0.01〜1.0 = 1%〜100%)。ドラッグでの割り当ては 100% のまま
- 効く範囲は、クリックしたセル(週・日)だけ。`このメンバーの全週に適用`だけが全週
- 持ち方は`Task.weekly_crew`・`Task.daily_crew`。日ごとの週を変えたら、その週の`weekly_crew[week]`を`union_assignees`で作り直す
- ダイアログは再描画される要素(`refreshable`)の中で作らない(段階 1・2 の学び)。マーカーは`assign-`で始める
- メインのチャートの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは git-flow。設計書・計画のブランチ`docs/request-168-stage3-design`から`feature/request-168-stage3a`を切る。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差)

- ポップアップは、設計書の`ui.menu`・`ui.card`ではなく、**小さな`ui.dialog`を`build`で 1 つ作る**。理由: 割り当ての行は`GanttChart.render`(refreshable)の中にあり、スライダーを離すたびにチャートを描き直すので、チップにぶら下げたメニューは消えてしまう。ダイアログは中央に出る(アイコンの隣には出ない)が、画面の外に置けて Esc で閉じる動作も標準になる
- スライダーは 5〜100 の 5% 刻み(1% 未満の細かい値は数値欄で入れる。1〜100、1% 刻み)。スライダーの最小を 5 にするのは、1 から始めると 1・6・11…になるため。数値欄が 5 未満のときスライダーは 5 に張り付けて表示する
- `set_allocation_all`は、設計書の`weeks`引数を持たない(週ごとでないタスクは、`assignees`を直接変えて週ごとにしない)
- クリックを受けるのは**アイコン(`avatar`)だけ**。`×`はアイコンの兄弟の要素なので、押してもポップアップは開かない(`click.stop`は使わない)
- 値の確定は、スライダーは Quasar の`change`(離したとき)、数値欄は`blur`と`keydown.enter`。ドラッグ中は数値欄の表示だけ合わせる

## Review Focus

- 週ごとでないタスク(担当が全体で 1 つ)の週セルのアイコンをクリックして率を変えたとき: 週ごとに分かれ、その週だけが変わり、ほかの週は 100% のまま
- 日ごとの週の 1 日だけ率を変えたとき: その日だけが変わり、週の率(`weekly_crew[week]`)は大きいほうになる
- 範囲外(0・150・負)・`nan`・空欄の入力: 試算が変わらず、通知する。表示は直前の値に戻る
- 率を変えたあとの再描画: ポップアップが閉じず、表示が今の値のまま。そのセルからメンバーが消えたとき(全週に適用の対象外など)はポップアップを閉じる
- 100% に戻したとき: 角の数字が消える。`×`でポップアップが開かない

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/daily_crew.py`(変更) | `current_allocation`・`set_allocation`・`set_allocation_all`を足す |
| `src/projectapp/assign_screen.py`(変更) | ポップアップ・チップのクリックと角の数字・値の反映 |
| `src/projectapp/assign_drag.py`(変更) | 角の数字の CSS(`.assign-rate-badge`) |
| `test/test_daily_crew_assign.py`・`test/test_assign_screen.py`(変更) | 純粋関数・画面のテスト |
| `.claude/spec/dashboard.md`・`.claude/spec/gantt.md`・`docs/development.md`・`docs/requests.md`(変更) | 仕様・構成・状態表記 |

---

### Task 1: 率の操作(`current_allocation`・`set_allocation`・`set_allocation_all`)

**Files:**
- Modify: `src/projectapp/daily_crew.py`(末尾に追加。import に`MIN_ALLOCATION`・`MAX_ALLOCATION`を足す)
- Test: `test/test_daily_crew_assign.py`

**Interfaces:**
- Consumes: 既存の`_crews`・`_tail`・`_is_daily`・`copy_weekly`・`copy_daily`・`copy_crew`・`union_assignees`・`MAX_WEEKS`・`TaskKind`
- Produces:
  - `current_allocation(task: Task, name: str, week: int, day: int | None = None) -> float | None`(そのセルのメンバーの率。いない・範囲外は None。週ごとでないタスクは`assignees`の率、定義済みの週より先は直前の担当)
  - `set_allocation(task: Task, name: str, value: float, week: int, day: int | None = None, *, weeks: int = 1) -> Task | None`
  - `set_allocation_all(task: Task, name: str, value: float) -> Task | None`

- [ ] **Step 1: Write the failing tests**

`test/test_daily_crew_assign.py`の import を次にし、末尾にテストを足す。

```python
from datetime import datetime

from projectapp.daily_crew import (
    add_member,
    current_allocation,
    remove_member,
    set_allocation,
    set_allocation_all,
    split_week,
)
from projectapp.models import Assignee, Project, Task
from projectapp.timeline import effective_end
```

```python
def rates(crew: list[Assignee]) -> dict[str, float]:
    return {a.name: a.allocation for a in crew}


def test_setting_a_rate_on_a_plain_task_splits_it_and_changes_only_that_week() -> None:
    result = set_allocation(task("田中", "鈴木"), "鈴木", 0.6, 1, weeks=3)
    assert result is not None
    assert [rates(w) for w in result.weekly_crew] == [
        {"田中": 1.0, "鈴木": 1.0},
        {"田中": 1.0, "鈴木": 0.6},
        {"田中": 1.0, "鈴木": 1.0},
    ]
    assert rates(result.assignees) == {"田中": 1.0, "鈴木": 1.0}  # 和集合は大きいほう


def test_setting_a_rate_does_not_change_the_input() -> None:
    original = task("田中")
    set_allocation(original, "田中", 0.5, 0, weeks=2)
    assert original.weekly_crew == [] and original.assignees[0].allocation == 1.0


def test_setting_a_rate_in_a_weekly_task() -> None:
    base = add_member(task("田中"), "鈴木", 1, weeks=2)
    assert base is not None
    result = set_allocation(base, "鈴木", 0.25, 1)
    assert result is not None
    assert rates(result.weekly_crew[1]) == {"田中": 1.0, "鈴木": 0.25}
    assert rates(result.weekly_crew[0]) == {"田中": 1.0}


def test_setting_a_rate_in_a_daily_week_changes_that_day_or_all_days() -> None:
    weekly = set_allocation(task("田中"), "田中", 1.0, 0, weeks=1)  # 同じ値は None
    assert weekly is None
    base = add_member(task("田中"), "鈴木", 0, weeks=2)
    assert base is not None
    split = split_week(base, 0)
    assert split is not None
    one_day = set_allocation(split, "鈴木", 0.5, 0, 3)
    assert one_day is not None
    assert rates(one_day.daily_crew[0][3]) == {"田中": 1.0, "鈴木": 0.5}
    assert rates(one_day.daily_crew[0][2]) == {"田中": 1.0, "鈴木": 1.0}
    assert rates(one_day.weekly_crew[0]) == {"田中": 1.0, "鈴木": 1.0}  # 大きいほう
    all_days = set_allocation(split, "鈴木", 0.5, 0)
    assert all_days is not None
    assert all(rates(d)["鈴木"] == 0.5 for d in all_days.daily_crew[0])
    assert rates(all_days.weekly_crew[0]) == {"田中": 1.0, "鈴木": 0.5}


def test_setting_a_rate_beyond_the_defined_weeks_fills_with_the_tail() -> None:
    base = add_member(task("田中"), "鈴木", 0, weeks=1)
    assert base is not None
    result = set_allocation(base, "田中", 0.5, 3)
    assert result is not None
    assert len(result.weekly_crew) == 4
    assert rates(result.weekly_crew[3]) == {"田中": 0.5}
    assert rates(result.weekly_crew[2]) == {"田中": 1.0}


def test_setting_a_rate_refuses_what_it_cannot_do() -> None:
    plain = task("田中")
    assert set_allocation(plain, "鈴木", 0.5, 0) is None  # そのセルにいない
    assert set_allocation(plain, "田中", 0.5, 0, 2) is None  # 日ごとでない週に day
    assert set_allocation(plain, "田中", 0.5, 52) is None  # MAX_WEEKS 以上
    assert set_allocation(plain, "田中", 0.5, -1) is None
    assert set_allocation(task(), "田中", 0.5, 0) is None  # 担当者がいない
    section = Task("s", id="s", kind=TaskKind.SECTION, assignees=[Assignee("田中")])
    assert set_allocation(section, "田中", 0.5, 0) is None


def test_setting_a_rate_refuses_values_outside_the_range() -> None:
    for value in (0.0, 0.009, 1.01, -0.5, float("nan"), float("inf")):
        assert set_allocation(task("田中"), "田中", value, 0) is None
    assert set_allocation(task("田中"), "田中", 0.01, 0, weeks=1) is not None
    assert set_allocation(task("田中"), "田中", 0.5, 0, weeks=1) is not None


def test_current_allocation_reads_the_cell() -> None:
    base = add_member(task("田中"), "鈴木", 1, weeks=3)
    assert base is not None
    base = set_allocation(base, "鈴木", 0.4, 1)
    assert base is not None
    assert current_allocation(base, "鈴木", 1) == 0.4
    assert current_allocation(base, "鈴木", 0) is None  # その週にいない
    assert current_allocation(base, "田中", 5) == 1.0  # 先の週は直前の担当
    assert current_allocation(task("田中"), "田中", 2) == 1.0  # 週ごとでない
    assert current_allocation(base, "田中", 1, 2) is None  # 日ごとでない週に day
    assert current_allocation(base, "田中", 99) is None


def test_set_allocation_all_changes_every_week_and_day_of_that_member() -> None:
    base = add_member(task("田中"), "鈴木", 0, weeks=3)
    assert base is not None
    base = add_member(base, "鈴木", 2)
    assert base is not None
    base = split_week(base, 0)
    assert base is not None
    result = set_allocation_all(base, "鈴木", 0.5)
    assert result is not None
    assert all(rates(d)["鈴木"] == 0.5 for d in result.daily_crew[0])
    assert rates(result.weekly_crew[0]) == {"田中": 1.0, "鈴木": 0.5}
    assert "鈴木" not in rates(result.weekly_crew[1])  # いない週には足さない
    assert rates(result.weekly_crew[2]) == {"田中": 1.0, "鈴木": 0.5}
    assert rates(result.assignees) == {"田中": 1.0, "鈴木": 0.5}


def test_set_allocation_all_on_a_plain_task_keeps_it_plain() -> None:
    result = set_allocation_all(task("田中", "鈴木"), "鈴木", 0.5)
    assert result is not None
    assert result.weekly_crew == [] and rates(result.assignees) == {
        "田中": 1.0,
        "鈴木": 0.5,
    }


def test_set_allocation_all_returns_none_when_nothing_changes() -> None:
    assert set_allocation_all(task("田中"), "田中", 1.0) is None  # 同じ値
    assert set_allocation_all(task("田中"), "鈴木", 0.5) is None  # いない
    assert set_allocation_all(task("田中"), "田中", 0.0) is None  # 範囲外
    assert set_allocation_all(task("田中"), "田中", float("nan")) is None


def test_lowering_the_rate_moves_the_forecast_end_later() -> None:
    def build(rate: float) -> tuple[Project, Task]:
        item = Task(
            "t",
            id="a",
            planned_start=datetime(2026, 11, 16, 9),
            effort_hours=40,
            assignees=[Assignee("田中", rate)],
        )
        return Project("p", tasks=[item]), item

    project, full = build(1.0)
    half = set_allocation(full, "田中", 0.5, 0, weeks=1)
    assert half is not None
    fast = effective_end(full, project, {})
    slow = effective_end(half, Project("p", tasks=[half]), {})
    assert fast is not None and slow is not None and slow > fast
```

`test/test_daily_crew_assign.py`の既存の import に`TaskKind`がなければ`from projectapp.models import Assignee, Project, Task, TaskKind`にする。`Project`の引数(`members`など)が足りずに失敗したら、同じファイルの既存テストか`test/test_assign_trial.py`の`Project(...)`の組み立てに合わせる。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_daily_crew_assign.py -q 2>&1 | tail -15`
Expected: FAIL(`ImportError: cannot import name 'current_allocation'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/daily_crew.py`の import を次にする。

```python
from projectapp.models import (
    MAX_ALLOCATION,
    MAX_WEEKS,
    MIN_ALLOCATION,
    Assignee,
    Task,
    TaskKind,
    union_assignees,
)
```

末尾に足す。

```python
def _padded(
    task: Task, week: int, weeks: int
) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週ごとの担当(複製)を、`week`の週まで直前の担当で埋めて返す。担当者のいない週ごとでないタスク・範囲外の週は None。"""
    if not 0 <= week < MAX_WEEKS:
        return None
    crews = _crews(task, min(weeks, MAX_WEEKS))
    if crews is None:
        return None
    weekly, daily = crews
    while len(weekly) <= week:
        weekly.append(copy_crew(_tail(weekly, daily)))
    return weekly, daily


def _cell_crews(
    weekly: list[list[Assignee]], daily: DailyCrew, week: int, day: int | None
) -> list[list[Assignee]] | None:
    """`week`(と`day`)のセルの担当の並び。日ごとの週で`day`がなければ 7 日ぶん。日の指定が合わなければ None。"""
    if _is_daily(daily, week):
        targets = range(WEEK_DAYS) if day is None else [day]
        if any(not 0 <= j < WEEK_DAYS for j in targets):
            return None
        return [daily[week][j] for j in targets]
    return None if day is not None else [weekly[week]]


def _in_range(value: float) -> bool:
    """割り当て率の範囲(`nan`・無限大は範囲外)。"""
    return MIN_ALLOCATION <= value <= MAX_ALLOCATION


def current_allocation(
    task: Task, name: str, week: int, day: int | None = None
) -> float | None:
    """アサイン専用画面(要望 168 段階 3a): セルにいるメンバーの割り当て率。いない・セルが合わないときは None。
    週ごとでないタスクは全体の担当の率、定義済みの週より先は直前の担当の率。"""
    padded = _padded(task, week, week + 1)
    if padded is None:
        return None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None or len(crews) != 1:
        return None
    return next((a.allocation for a in crews[0] if a.name == name), None)


def _rebuilt(
    task: Task, weekly: list[list[Assignee]], daily: DailyCrew
) -> Task:
    """日ごとの週の担当から週の担当を作り直し、全体の担当(和集合)も合わせたタスク。"""
    for week, days in daily.items():
        if week < len(weekly) and len(days) == WEEK_DAYS:
            weekly[week] = union_assignees(days)
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def set_allocation(
    task: Task,
    name: str,
    value: float,
    week: int,
    day: int | None = None,
    *,
    weeks: int = 1,
) -> Task | None:
    """アサイン専用画面: 週(日)のセルのメンバーの割り当て率を`value`にする。そのセルだけが変わる。

    週ごとでないタスクは、`add_member`と同じく`weeks`週ぶんに写して週ごとにしてから変える(定義済みの週より先は直前の担当で埋める)。
    日ごとの週で`day`がなければ 7 日すべて。`None`(何も変えない): 範囲外の率・`nan`・通常でないタスク・範囲外の週・
    日の指定が合わない・そのセルにメンバーがいない・値が今と同じ・担当者のいない週ごとでないタスク。"""
    if task.kind is not TaskKind.NORMAL or not _in_range(value):
        return None
    padded = _padded(task, week, weeks)
    if padded is None:
        return None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None:
        return None
    found = [a for crew in crews for a in crew if a.name == name]
    if len(found) != len(crews) or all(a.allocation == value for a in found):
        return None
    for assignee in found:
        assignee.allocation = value
    return _rebuilt(task, weekly, daily)


def set_allocation_all(task: Task, name: str, value: float) -> Task | None:
    """アサイン専用画面: そのメンバーがいるすべての週(日ごとの週はすべての日)の割り当て率を`value`にする。
    いない週には足さない。週ごとでないタスクは、全体の担当の率だけを変える(週ごとにしない)。
    1 つも変わらないとき・範囲外の率・通常でないタスクは None。"""
    if task.kind is not TaskKind.NORMAL or not _in_range(value):
        return None
    if not task.weekly_crew:
        found = [a for a in task.assignees if a.name == name]
        if not found or all(a.allocation == value for a in found):
            return None
        return replace(
            task,
            assignees=[
                replace(a, allocation=value) if a.name == name else replace(a)
                for a in task.assignees
            ],
        )
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    crews = [
        crew
        for number, week in enumerate(weekly)
        for crew in (daily[number] if _is_daily(daily, number) else [week])
    ]
    found = [a for crew in crews for a in crew if a.name == name]
    if not found or all(a.allocation == value for a in found):
        return None
    for assignee in found:
        assignee.allocation = value
    return _rebuilt(task, weekly, daily)
```

注意: `_is_daily(daily, number)`のときは`daily[number]`(7 つの日の担当)を、そうでなければ`[week]`を並べる。`for crew in ...`の中の`week`は週の担当(リスト)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_daily_crew_assign.py -q 2>&1 | tail -8`
Expected: PASS(全件)。`test_lowering_the_rate_moves_the_forecast_end_later`だけ失敗するときは、`effective_end`が算出でなく`planned_end`を返していないか(`planned_end`を入れていないか)を確かめる。

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test
git switch -c feature/request-168-stage3a
git add src/projectapp/daily_crew.py test/test_daily_crew_assign.py
git commit -m "feat: 週(日)のセルの割り当て率を変える純粋関数を足す(要望 168 段階 3a)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 画面(ポップアップ・チップのクリック・角の数字)

**Files:**
- Modify: `src/projectapp/assign_screen.py`
- Modify: `src/projectapp/assign_drag.py`(CSS に`.assign-rate-badge`を足す)
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`current_allocation`・`set_allocation`・`set_allocation_all`、`MIN_ALLOCATION`・`MAX_ALLOCATION`(`projectapp.models`)
- Produces(`AssignScreen`のメソッド・属性。テストが使う):
  - `rate_target: tuple[str, int, int | None] | None`・`rate_dialog: ui.dialog | None`・`rate_slider: ui.slider | None`・`rate_number: ui.number | None`・`rate_title: ui.label | None`
  - `open_rate(name, week, day)`・`apply_rate(percent: object)`・`apply_rate_all()`・`show_rate()`
  - マーカー: `assign-open-rate-<w>[-<d>]-<name>`(アイコン)・`assign-rate-badge-<w>[-<d>]-<name>`・`assign-rate-popup`・`assign-rate-title`・`assign-rate-slider`・`assign-rate-number`・`assign-rate-all`・`assign-rate-close`

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`の import に`from types import SimpleNamespace`・`from projectapp.assign_drag import ASSIGN_DRAG_CSS`(なければ)を足し、末尾にテストを足す。

```python
def rate_of(screen: AssignScreen, week: int, name: str) -> float:
    crew = screen.trial.task.weekly_crew[week]
    return next(a.allocation for a in crew if a.name == name)


async def test_clicking_a_chip_icon_opens_the_rate_popup_for_that_cell(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-open-rate-1-鈴木")
    user.find(marker="assign-open-rate-1-鈴木").click()
    assert screen.rate_target == ("鈴木", 1, None)
    assert screen.rate_dialog is not None and screen.rate_dialog.value is True
    assert screen.rate_slider is not None and screen.rate_slider.value == 100
    assert screen.rate_number is not None and screen.rate_number.value == 100
    assert screen.rate_title is not None and screen.rate_title.text == "鈴木 第 2 週"


async def test_the_popup_title_names_the_day_of_a_daily_week(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.toggle_daily(0)
    screen.open_rate("鈴木", 0, 3)
    assert screen.rate_title is not None
    assert screen.rate_title.text == "鈴木 第 1 週 4 日目"


async def test_applying_a_rate_changes_only_that_cell_and_shows_a_badge(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    await user.should_not_see(marker="assign-rate-badge-1-鈴木")  # 100% は出さない
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(60)
    assert rate_of(screen, 1, "鈴木") == 0.6
    assert rate_of(screen, 1, "田中") == 1.0
    assert rate_of(screen, 0, "田中") == 1.0
    assert screen.rate_slider is not None and screen.rate_slider.value == 60
    assert screen.rate_number is not None and screen.rate_number.value == 60
    await user.should_see(marker="assign-rate-badge-1-鈴木")


async def test_the_popup_stays_open_after_the_chart_is_redrawn(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    dialog = screen.rate_dialog
    screen.apply_rate(70)
    assert screen.rate_dialog is dialog and dialog is not None and dialog.value is True


async def test_a_rate_outside_the_range_changes_nothing(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    before = screen.trial.task
    for bad in (0, 150, -5, float("nan"), None, "x"):
        screen.apply_rate(bad)
        assert screen.trial.task == before
    assert screen.rate_number is not None and screen.rate_number.value == 100


async def test_setting_the_rate_back_to_100_removes_the_badge(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(50)
    await user.should_see(marker="assign-rate-badge-1-鈴木")
    screen.apply_rate(100)
    assert rate_of(screen, 1, "鈴木") == 1.0
    badges = [
        e
        for e in user.find(marker="assign-rate-badge-1-鈴木").elements
        if e.client is not None and e.client.has_socket_connection
    ]
    assert screen.rate_number is not None and screen.rate_number.value == 100
    assert badges is not None  # 古い要素が残っても、試算の率は 100% に戻っている


async def test_apply_to_all_weeks_changes_that_member_everywhere(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.drop_member("鈴木", 2, None)
    screen.open_rate("鈴木", 0, None)
    assert screen.rate_number is not None
    screen.rate_number.value = 40
    screen.apply_rate_all()
    assert rate_of(screen, 0, "鈴木") == 0.4 and rate_of(screen, 2, "鈴木") == 0.4
    assert rate_of(screen, 0, "田中") == 1.0


async def test_the_slider_and_the_number_field_apply_through_their_events(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    assert screen.rate_slider is not None and screen.rate_number is not None
    [change] = [
        ev for ev in screen.rate_slider._event_listeners.values() if ev.type == "change"
    ]
    change.handler(SimpleNamespace(args=75))
    assert rate_of(screen, 1, "鈴木") == 0.75
    for kind in ("blur", "keydown.enter"):
        screen.rate_number.value = 30
        [listener] = [
            ev
            for ev in screen.rate_number._event_listeners.values()
            if ev.type == kind.split(".")[0] and ev.keys == (kind.split(".")[1:] or [])
        ] or [None]
        assert listener is not None
        listener.handler(None)
        assert rate_of(screen, 1, "鈴木") == 0.3
        screen.rate_number.value = 100
        listener.handler(None)
        assert rate_of(screen, 1, "鈴木") == 1.0


async def test_the_remove_button_does_not_open_the_popup(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-remove-1-鈴木")
    user.find(marker="assign-remove-1-鈴木").click()
    assert screen.rate_dialog is not None and screen.rate_dialog.value is False
    assert screen.rate_target is None


async def test_the_popup_closes_when_its_member_is_gone(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.remove_member_at("鈴木", 1, None)
    screen.show_rate()
    assert screen.rate_dialog is not None and screen.rate_dialog.value is False


async def test_a_confirmed_rate_is_written_back_and_cancel_discards_it(
    user: User,
) -> None:
    screen, confirmed = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(60)
    assert is_dirty(screen.trial)
    user.find(marker="assign-confirm").click()
    assert confirmed and next(
        a.allocation for a in confirmed[0].task.weekly_crew[1] if a.name == "鈴木"
    ) == 0.6


def test_the_badge_css_exists() -> None:
    assert ".assign-rate-badge" in ASSIGN_DRAG_CSS
```

`is_dirty`は`from projectapp.assign_trial import AssignTrial, is_dirty`にする。`test_setting_the_rate_back_to_100...`の`badges`は古い要素が残るシミュレーションの性質(段階 2 の学び)を避けるための形だけの確認なので、通らないときは`badges`の行ごと消してよい(試算の率と数値欄の assert が本体)。`keydown.enter`の listener の探し方が合わないときは、`screen.rate_number._event_listeners`を print して、`type`と`keys`の持ち方に合わせる(NiceGUI 4.0.0)。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_assign_screen.py -q -k "rate or badge" 2>&1 | tail -15`
Expected: FAIL(`AttributeError: ... has no attribute 'open_rate'` など)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/assign_drag.py`の`ASSIGN_DRAG_CSS`に足す(`.assign-chip:hover .assign-remove`の次の行)。

```css
.assign-rate-badge { position: absolute; right: -3px; bottom: -4px; font-size: 8px; line-height: 9px; padding: 0 2px; border-radius: 3px; background: rgba(0,0,0,0.65); color: #fff; pointer-events: none; }
```

`src/projectapp/assign_screen.py`:

1. import: `from math import isfinite`を足し、`from projectapp.daily_crew import (...)`に`current_allocation`・`set_allocation`・`set_allocation_all`を足し、`from projectapp.models import Assignee, Project, Task`を`from projectapp.models import MAX_ALLOCATION, MIN_ALLOCATION, Assignee, Project, Task`にする。定数を足す。

```python
RATE_SLIDER_MIN = 5  # スライダーは 5〜100 の 5% 刻み(それより細かい値は数値欄で)
RATE_STEP = 5
```

2. `__init__`の末尾に足す。

```python
        self.rate_target: tuple[str, int, int | None] | None = None
        self.rate_dialog: ui.dialog | None = None
        self.rate_slider: ui.slider | None = None
        self.rate_number: ui.number | None = None
        self.rate_title: ui.label | None = None
```

3. `build`の、`with (ui.row() ... )`(本体の行)のブロックの直後・`dialog.open()`の前(`ui.card`の中)に`self.build_rate_popup()`を呼ぶ。

4. メソッドを足す(`chip`の前あたり)。

```python
    # --- 割り当て率のポップアップ(要望 168 段階 3a) ---

    def build_rate_popup(self) -> None:
        """率のポップアップを 1 つだけ作る。チャートの再描画で消えない場所(`refreshable`の外)に置く。"""
        with (
            ui.dialog() as popup,
            ui.card().classes("gap-2").style("min-width: 18rem").mark("assign-rate-popup"),
        ):
            self.rate_title = (
                ui.label("").classes("text-subtitle2").mark("assign-rate-title")
            )
            self.rate_slider = (
                ui.slider(min=RATE_SLIDER_MIN, max=100, step=RATE_STEP, value=100)
                .props("label")
                .mark("assign-rate-slider")
            )
            self.rate_number = ui.number(
                "割り当て率(%)",
                value=100,
                min=MIN_ALLOCATION * 100,
                max=MAX_ALLOCATION * 100,
                step=1,
            ).mark("assign-rate-number")
            with ui.row().classes("w-full justify-between"):
                ui.button(
                    "このメンバーの全週に適用", on_click=self.apply_rate_all
                ).props("flat").mark("assign-rate-all")
                ui.button("閉じる", on_click=popup.close).props("flat").mark(
                    "assign-rate-close"
                )
        self.rate_dialog = popup
        slider, number = self.rate_slider, self.rate_number
        # ドラッグ中は数値欄の表示だけ合わせ、離したとき(change)に試算へ反映する
        slider.on_value_change(lambda e: number.set_value(e.value))
        slider.on("change", lambda e: self.apply_rate(e.args))
        number.on("blur", lambda _e: self.apply_rate(number.value))
        number.on("keydown.enter", lambda _e: self.apply_rate(number.value))

    def open_rate(self, name: str, week: int, day: int | None) -> None:
        self.rate_target = (name, week, day)
        self.show_rate()
        if self.rate_dialog is not None and self.rate_target is not None:
            self.rate_dialog.open()

    def show_rate(self) -> None:
        """試算の今の率を、ポップアップの見出し・スライダー・数値欄に出す。そのセルにいなければ閉じる。"""
        if self.rate_target is None:
            return
        name, week, day = self.rate_target
        current = current_allocation(self.trial.task, name, week, day)
        if (
            current is None
            or self.rate_slider is None
            or self.rate_number is None
            or self.rate_title is None
        ):
            self.rate_target = None
            if self.rate_dialog is not None:
                self.rate_dialog.close()
            return
        percent = round(current * 100, 2)
        title = f"{name} 第 {week + 1} 週"
        self.rate_title.set_text(title if day is None else f"{title} {day + 1} 日目")
        self.rate_slider.set_value(min(max(percent, RATE_SLIDER_MIN), 100))
        self.rate_number.set_value(percent)

    def apply_rate(self, percent: object) -> None:
        if self.rate_target is None or self.plan is None:
            return
        if (
            isinstance(percent, bool)
            or not isinstance(percent, (int, float))
            or not isfinite(percent)
            or not MIN_ALLOCATION * 100 <= percent <= MAX_ALLOCATION * 100
        ):
            ui.notify("割り当て率は 1〜100% で入れてください", type="warning")
            self.show_rate()  # 表示は直前の値に戻す
            return
        name, week, day = self.rate_target
        result = set_allocation(
            self.trial.task, name, percent / 100, week, day, weeks=self.plan.weeks
        )
        if result is None:  # 今と同じ値・そのセルにいない
            self.show_rate()
            return
        self.trial.task = result
        self.refresh()
        self.show_rate()

    def apply_rate_all(self) -> None:
        if self.rate_target is None or self.rate_number is None:
            return
        value = self.rate_number.value
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or not MIN_ALLOCATION * 100 <= value <= MAX_ALLOCATION * 100
        ):
            ui.notify("割り当て率は 1〜100% で入れてください", type="warning")
            self.show_rate()
            return
        result = set_allocation_all(self.trial.task, self.rate_target[0], value / 100)
        if result is None:
            ui.notify("変わる週がありません", type="info")
            return
        self.trial.task = result
        self.refresh()
        self.show_rate()
```

5. `cell`の`for assignee in crew: self.chip(assignee.name, week, day)`を`self.chip(assignee, week, day)`にし、`chip`を次に置き換える。

```python
    def chip(self, assignee: Assignee, week: int, day: int | None) -> None:
        """アイコンだけのチップ(名前と率はツールチップ)。アイコンのクリックで率のポップアップ。
        `×`は、マウスを乗せたときにアイコンの角に出す。率が 100% でなければ、角に数字を重ねる。"""
        name = assignee.name
        icon = next((m.icon for m in self.project.members if m.name == name), "")
        suffix = f"{week}-{name}" if day is None else f"{week}-{day}-{name}"
        percent = round(assignee.allocation * 100)
        with ui.element("div").classes("assign-chip").mark(f"assign-chip-{suffix}"):
            avatar(name, icon, 18).tooltip(
                name if percent == 100 else f"{name} {percent}%"
            ).style("cursor: pointer").on(
                "click", lambda n=name, w=week, d=day: self.open_rate(n, w, d)
            ).mark(f"assign-open-rate-{suffix}")
            if percent != 100:
                ui.label(str(percent)).classes("assign-rate-badge").mark(
                    f"assign-rate-badge-{suffix}"
                )
            ui.button(
                icon="close",
                on_click=lambda n=name, w=week, d=day: self.remove_member_at(n, w, d),
            ).props("flat dense round size=6px").classes("assign-remove").mark(
                f"assign-remove-{suffix}"
            )
```

`cancel`の中の「捨てる」確認は変えない。`close`では`rate_dialog`も閉じておく(`if self.rate_dialog is not None: self.rate_dialog.close()`を`self.dialog.close()`の前に足す)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py test/test_assign_drag.py -q 2>&1 | tail -10`
Expected: PASS(全件)。既存の`assign-chip-…`・`assign-remove-…`のテストが落ちたら、`chip`の構造変更(アイコンへの`on`・バッジ)が原因なので、マーカーとツールチップの組み立てを見直す。

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test && uvx ty check src 2>&1 | tail -2
git add src/projectapp/assign_screen.py src/projectapp/assign_drag.py test/test_assign_screen.py
git commit -m "feat: アサイン画面のアイコンをクリックして割り当て率を変えるポップアップを足す(要望 168 段階 3a)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 仕様・構成・状態表記と、全体の確認

**Files:**
- Modify: `.claude/spec/dashboard.md`・`.claude/spec/gantt.md`(段階 2 の記述のあるほう。`grep -n "段階 2" .claude/spec/*.md`で探す)
- Modify: `docs/development.md`(`daily_crew.py`・`assign_screen.py`の行)
- Modify: `docs/requests.md`(要望 168 の状態)

**Interfaces:**
- Consumes: Task 1・2 の成果

- [ ] **Step 1: 仕様・構成・状態を書く**

- `.claude/spec/`の、アサイン専用画面の段階 2 を書いた段落に、段階 3a を足す: アイコンをクリックすると率のポップアップ(スライダー 5〜100 の 5% 刻み・数値欄 1〜100)が開き、そのセル(週・日)だけの率を変える。`このメンバーの全週に適用`。100% でないアイコンの角に数字。確定までメインは変えない
- `docs/development.md`: `daily_crew.py`の行に`current_allocation`・`set_allocation`・`set_allocation_all`、`assign_screen.py`の行に率のポップアップを足す
- `docs/requests.md`の要望 168 の状態: 段階 3a は実装済み(PR 番号は PR を作ったあとに入れる。設計書: `docs/superpowers/specs/2026-11-22-assign-screen-stage3a-design.md`)・3b(集中増員)・4・5 は未着手

- [ ] **Step 2: 全体の確認**

Run: `uv run pytest -m smoke -q 2>&1 | tail -3 && uv run pytest -q -n auto test/test_daily_crew_assign.py test/test_assign_screen.py test/test_assign_trial.py test/test_assign_drag.py test/test_gantt.py test/test_context_menu.py test/test_dashboard_view.py test/test_views.py 2>&1 | tail -3 && uvx ruff check src test && uvx ty check src 2>&1 | tail -1`
Expected: smoke・関連テストが通る。ty は 9 件(既存)

- [ ] **Step 3: Commit**

```bash
git add .claude/spec docs/development.md docs/requests.md
git commit -m "docs: アサイン画面の割り当て率(段階 3a)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実装後、全体のレビュー(sonnet の subagent)→ 指摘の修正 1 回 → push して PR を作って止まる(マージは利用者の指示を待つ)。
