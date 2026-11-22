# アサイン専用画面 段階 3b(範囲を選んでの集中増員)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面の割り当ての行で、セルをなぞって範囲を選び、範囲の中へメンバーのチップを落とすと、範囲のすべてのセルに足せるようにする。

**Architecture:** 担当の操作は`daily_crew.py`の純粋関数(`add_member_range`・`cell_in_range`・`ordered_cells`・`range_cells`)。`add_member`・`remove_member`は 3a で足した`_padded`・`_cell_crews`・`_rebuilt`に寄せて重複をなくす。範囲の選択は`assign_drag.py`の JS(mousedown→mouseover→mouseup を document に委譲し、結果を`emitEvent("assign_select_range", …)`で返す)。画面は選択を`AssignScreen.selection`に持ち、選択のセルに色を付け、落とし先が選択の中なら`add_member_range`を使う。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)・node(JS のシミュレーションテスト)

**Spec:** `docs/superpowers/specs/2026-11-22-assign-screen-stage3b-design.md`(段階 1〜3a は`docs/superpowers/specs/2026-11-22-assign-screen-stage{1,2,3a}-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。試算は保存しない。選択は試算に含めず、`is_dirty`は変えない
- 範囲はセル単位だけ(週のセルは週ごと、日ごとにした週は日ごと)。週の途中からの範囲を作るために週を自動で日ごとにしない
- 範囲で足すメンバーの割り当て率は 100%(変えるのは 3a のポップアップ)。上限は`MAX_WEEKS`(52)
- ダイアログは再描画される要素の中で作らない。マーカーは`assign-`で始める。メインのチャートの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは git-flow。設計書・計画のブランチ`docs/request-168-stage3b-design`から`feature/request-168-stage3b`を切る。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差・補足)

- 設計書の`add_member_range(task, name, first, last, …)`の`first`・`last`は、`Cell = tuple[int, int | None]`(`(週, 日 or None)`)。選択の持ち方(`AssignScreen.selection`)も同じ型の組
- 範囲の判定・並べ替え・セルの列挙は、純粋関数として`ordered_cells`・`cell_in_range`・`range_cells`に出す(画面は`cell_in_range`だけ使う。`range_cells`は`add_member_range`が使う)
- 担当者のいないタスクは、`add_member`の規則(最初の 1 回は全体の担当)により、範囲で足しても全体の担当になるだけで週ごとにならない。範囲の 2 つ目以降は重複扱いで飛ばす
- 選択の解除: 落とした成功時・`日ごと`/`週に戻す`・`選択を解除`ボタン。落とし先が範囲の外のときは選択を残す
- 範囲で一部のセルにだけメンバーがいるときは、いないセルだけに足す。通知(`すでに割り当てています`)は、すべてのセルにいるときだけ

## Review Focus

- 始点と終点が逆(右から左へなぞる)でも、同じ範囲になる
- 週のセルと日ごとの週の日のセルが混ざる範囲(例: 週 0 から週 1 の 3 日目まで)で、日ごとの週は範囲の日だけに足す
- 範囲の一部のセルにだけすでにメンバーがいるとき: 重複せず、いないセルだけに足す
- 定義済みの週より先を含む範囲・52 週を超える範囲・担当者のいないタスク
- チップ・`×`・`日ごと`ボタンの上から始めたマウスの動きは、範囲の選択にならない。同じセルのクリックだけでは選ばない

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/daily_crew.py`(変更) | `Cell`・`ordered_cells`・`cell_in_range`・`range_cells`・`add_member_range`を足し、`add_member`・`remove_member`を整理する |
| `src/projectapp/assign_drag.py`(変更) | 範囲の選択の JS・CSS・`ASSIGN_SELECT_EVENT` |
| `src/projectapp/assign_screen.py`(変更) | 選択の状態・色付け・解除ボタン・範囲へのドロップ・選択のイベントの受け口 |
| `test/test_daily_crew_assign.py`・`test/test_assign_drag.py`・`test/test_assign_screen.py`(変更) | テスト |
| `.claude/spec/dashboard.md`・`docs/development.md`・`docs/requests.md`(変更) | 仕様・構成・状態表記 |

---

### Task 1: 担当の操作(整理と`add_member_range`)

**Files:**
- Modify: `src/projectapp/daily_crew.py`
- Test: `test/test_daily_crew_assign.py`

**Interfaces:**
- Consumes: 3a の`_padded`・`_cell_crews`・`_rebuilt`・`_is_daily`、`add_member`
- Produces:
  - `Cell = tuple[int, int | None]`
  - `ordered_cells(first: Cell, last: Cell) -> tuple[Cell, Cell]`(日付の順に並べ替える。キーは`(week, day or 0)`)
  - `cell_in_range(first: Cell, last: Cell, week: int, day: int | None) -> bool`
  - `range_cells(daily: DailyCrew, first: Cell, last: Cell) -> list[Cell]`
  - `add_member_range(task: Task, name: str, first: Cell, last: Cell, *, weeks: int = 1) -> Task | None`

- [ ] **Step 1: Write the failing tests**

`test/test_daily_crew_assign.py`の import の`from projectapp.daily_crew import (...)`に`add_member_range`・`cell_in_range`・`ordered_cells`・`range_cells`・`to_weekly`を足し、末尾にテストを足す。

```python
def test_a_range_adds_the_member_to_every_week_in_it() -> None:
    result = add_member_range(task("田中"), "鈴木", (1, None), (2, None), weeks=4)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
        ["田中"],
    ]
    assert names(result.assignees) == ["田中", "鈴木"]


def test_a_range_is_the_same_when_first_and_last_are_swapped() -> None:
    forward = add_member_range(task("田中"), "鈴木", (1, None), (2, None), weeks=4)
    backward = add_member_range(task("田中"), "鈴木", (2, None), (1, None), weeks=4)
    assert forward is not None and forward == backward


def test_a_range_skips_cells_that_already_have_the_member() -> None:
    base = add_member(task("田中"), "鈴木", 1, weeks=4)
    assert base is not None
    result = add_member_range(base, "鈴木", (0, None), (2, None))
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中", "鈴木"],
        ["田中", "鈴木"],  # 重複しない
        ["田中", "鈴木"],
        ["田中"],
    ]


def test_a_range_returns_none_when_every_cell_already_has_the_member() -> None:
    base = add_member_range(task("田中"), "鈴木", (0, None), (2, None), weeks=3)
    assert base is not None
    assert add_member_range(base, "鈴木", (0, None), (2, None)) is None


def test_a_range_across_a_daily_week_adds_only_the_days_in_it() -> None:
    weekly = to_weekly(task("田中"), 3)
    assert weekly is not None
    base = split_week(weekly, 1)
    assert base is not None
    result = add_member_range(base, "鈴木", (0, None), (1, 2))
    assert result is not None
    assert "鈴木" in names(result.weekly_crew[0])
    days = result.daily_crew[1]
    assert ["鈴木" in names(d) for d in days] == [True, True, True] + [False] * 4
    assert "鈴木" in names(result.weekly_crew[1])  # 日の和集合
    assert "鈴木" not in names(result.weekly_crew[2])


def test_a_range_can_start_in_the_middle_of_a_daily_week() -> None:
    weekly = to_weekly(task("田中"), 3)
    assert weekly is not None
    base = split_week(weekly, 1)
    assert base is not None
    result = add_member_range(base, "鈴木", (1, 4), (2, None))
    assert result is not None
    assert ["鈴木" in names(d) for d in result.daily_crew[1]] == [False] * 4 + [True] * 3
    assert "鈴木" in names(result.weekly_crew[2])


def test_a_range_beyond_the_defined_weeks_fills_with_the_tail() -> None:
    result = add_member_range(task("田中"), "鈴木", (2, None), (4, None), weeks=1)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中"],
        ["田中"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
    ]


def test_a_range_on_an_unassigned_task_makes_the_whole_task_assigned() -> None:
    result = add_member_range(task(), "鈴木", (0, None), (2, None), weeks=3)
    assert result is not None
    assert result.weekly_crew == [] and names(result.assignees) == ["鈴木"]


def test_a_range_refuses_what_it_cannot_do() -> None:
    assert add_member_range(task("田中"), "鈴木", (0, None), (52, None)) is None
    assert add_member_range(task("田中"), "鈴木", (-1, None), (1, None)) is None
    summary = Task("s", id="s", kind=TaskKind.SUMMARY, assignees=[Assignee("田中")])
    assert add_member_range(summary, "鈴木", (0, None), (1, None)) is None


def test_cell_in_range_follows_week_and_day_boundaries() -> None:
    assert cell_in_range((1, None), (2, None), 1, None)
    assert cell_in_range((1, None), (2, None), 2, 5)  # 日ごとの週の日も週の範囲に入る
    assert not cell_in_range((1, None), (2, None), 0, None)
    assert not cell_in_range((1, None), (2, None), 3, None)
    assert cell_in_range((1, 2), (3, 4), 1, 2) and not cell_in_range((1, 2), (3, 4), 1, 1)
    assert cell_in_range((1, 2), (3, 4), 3, 4) and not cell_in_range((1, 2), (3, 4), 3, 5)
    assert cell_in_range((3, 4), (1, 2), 2, None)  # 逆順でも同じ


def test_ordered_cells_and_range_cells() -> None:
    assert ordered_cells((3, 4), (1, None)) == ((1, None), (3, 4))
    daily = {1: [[] for _ in range(7)]}
    assert range_cells(daily, (0, None), (1, 2)) == [(0, None), (1, 0), (1, 1), (1, 2)]
    assert range_cells(daily, (1, 5), (2, None)) == [(1, 5), (1, 6), (2, None)]
```

`test_a_range_beyond_the_defined_weeks…`は、`task("田中")`に`weeks=1`で`add_member`が週ごとにするため、週 0・1 が「田中」だけで埋まる想定。実装後の実際の並びと違うときは、`add_member`の同じ週の結果(`test_adding_to_a_plain_task_…`)に合わせて期待値を直す。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_daily_crew_assign.py -q 2>&1 | tail -6`
Expected: FAIL(`ImportError: cannot import name 'add_member_range'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/daily_crew.py`:

1. `DailyCrew = ...`の次の行に`Cell = tuple[int, int | None]`を足す。
2. `add_member`の本体(docstring は残す)を次にする。

```python
    if not 0 <= week < MAX_WEEKS or task.kind is not TaskKind.NORMAL:
        return None
    if not task.weekly_crew and not task.assignees:
        return replace(task, assignees=[Assignee(name)])
    padded = _padded(task, week, weeks)
    assert padded is not None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None:
        return None
    missing = [crew for crew in crews if name not in {a.name for a in crew}]
    if not missing:
        return None
    for crew in missing:
        crew.append(Assignee(name))
    return _rebuilt(task, weekly, daily)
```

3. `remove_member`の本体(docstring は残す)を次にする。

```python
    padded = _padded(task, week, weeks)
    if padded is None:
        return None
    weekly, daily = padded
    crews = _cell_crews(weekly, daily, week, day)
    if crews is None:
        return None
    if any(name not in {a.name for a in crew} or len(crew) <= 1 for crew in crews):
        return None  # いない・最後の 1 人は外せない
    for crew in crews:
        crew[:] = [a for a in crew if a.name != name]
    return _rebuilt(task, weekly, daily)
```

4. 末尾に足す。

```python
def ordered_cells(first: Cell, last: Cell) -> tuple[Cell, Cell]:
    """2 つのセルを日付の順(週、日。日がなければ 0)に並べる。"""

    def key(cell: Cell) -> tuple[int, int]:
        return cell[0], cell[1] or 0

    return (first, last) if key(first) <= key(last) else (last, first)


def cell_in_range(first: Cell, last: Cell, week: int, day: int | None) -> bool:
    """アサイン専用画面: `first`〜`last`(両端を含む。逆順でもよい)の範囲に、セル`(week, day)`が入るか。
    日ごとでない週(`day`が None)は、その週が範囲の週にかかれば入る。"""
    low, high = ordered_cells(first, last)
    if not low[0] <= week <= high[0]:
        return False
    if day is None:
        return True
    if week == low[0] and low[1] is not None and day < low[1]:
        return False
    return not (week == high[0] and high[1] is not None and day > high[1])


def range_cells(daily: DailyCrew, first: Cell, last: Cell) -> list[Cell]:
    """範囲のセルの並び。日ごとの週は日のセル(範囲の端の週は範囲の日だけ)、そうでない週は週のセル。"""
    low, high = ordered_cells(first, last)
    cells: list[Cell] = []
    for week in range(low[0], high[0] + 1):
        if not _is_daily(daily, week):
            cells.append((week, None))
            continue
        start = low[1] if week == low[0] and low[1] is not None else 0
        end = high[1] if week == high[0] and high[1] is not None else WEEK_DAYS - 1
        cells.extend((week, day) for day in range(start, end + 1))
    return cells


def add_member_range(
    task: Task, name: str, first: Cell, last: Cell, *, weeks: int = 1
) -> Task | None:
    """アサイン専用画面(要望 168 段階 3b): `first`〜`last`の範囲のすべてのセルに、メンバーを 100% で足す。
    すでにいるセルは飛ばす。週ごとでないタスク・担当者のいないタスク・定義済みの週より先は`add_member`と同じ。
    `None`(何も変えない): すべてのセルにすでにいる・範囲が 0 未満か`MAX_WEEKS`以上の週にかかる・通常でないタスク。"""
    low, high = ordered_cells(first, last)
    if low[0] < 0 or high[0] >= MAX_WEEKS or task.kind is not TaskKind.NORMAL:
        return None
    result = task
    changed = False
    for week, day in range_cells(task.daily_crew, low, high):
        step = add_member(result, name, week, day, weeks=weeks)
        if step is not None:
            result = step
            changed = True
    return result if changed else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_daily_crew_assign.py test/test_daily_crew.py test/test_assign_screen.py -q 2>&1 | tail -6`
Expected: PASS(全件。`add_member`・`remove_member`の整理で、既存のテストが 1 件も変わらず通ること)

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test
git switch -c feature/request-168-stage3b
git add src/projectapp/daily_crew.py test/test_daily_crew_assign.py
git commit -m "feat: 範囲のセルへ足す add_member_range を足し、add_member・remove_member を整理する(要望 168 段階 3b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 範囲の選択の JS・CSS

**Files:**
- Modify: `src/projectapp/assign_drag.py`
- Test: `test/test_assign_drag.py`

**Interfaces:**
- Consumes: 割り当ての行のセル(`data-assign-cell`・`data-week`・`data-day`)、チップ(`.assign-chip`)、メンバー一覧のチップ(`data-assign-member`)
- Produces: `ASSIGN_SELECT_EVENT = "assign_select_range"`。イベントの引数は`{first: {week, day}, last: {week, day}}`(`day`は日ごとの週のセルだけ数値、そうでなければ`null`)。CSS クラス`assign-select-over`(なぞっている最中)・`assign-selected`(確定した選択。画面が付ける)

- [ ] **Step 1: Write the failing tests**

`test/test_assign_drag.py`の import に`ASSIGN_SELECT_EVENT`を足し、末尾にテストを足す。

```python
def test_the_select_js_emits_its_own_event_and_the_css_marks_the_selection() -> None:
    assert ASSIGN_SELECT_EVENT == "assign_select_range"
    assert f'emitEvent("{ASSIGN_SELECT_EVENT}"' in ASSIGN_DRAG_JS
    assert ".assign-select-over" in ASSIGN_DRAG_CSS
    assert ".assign-selected" in ASSIGN_DRAG_CSS


def test_the_select_js_emits_the_range_swiped_across_cells(tmp_path) -> None:
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので動きを確かめない")
    script = tmp_path / "sim_select.js"
    script.write_text(
        """
const listeners = {};
const emitted = [];
global.window = {};
const mkCell = (week, day) => {
  const set = new Set();
  return { dataset: day === null ? { week: String(week) } : { week: String(week), day: String(day) },
           classList: { add: (c) => set.add(c), remove: (c) => set.delete(c), has: (c) => set.has(c) },
           set };
};
const cells = [mkCell(0, null), mkCell(1, 0), mkCell(1, 1), mkCell(1, 2), mkCell(2, null)];
global.document = {
  addEventListener: (type, fn) => { listeners[type] = fn; },
  querySelectorAll: (selector) =>
    selector === "[data-assign-cell]" ? cells : cells.filter((c) => c.set.has("assign-select-over")),
};
global.emitEvent = (name, msg) => emitted.push([name, msg]);
%s
// event.target.closest(selector) が、含まれる祖先(または自分)を返す形の模擬
const at = (cell, extra) => ({ closest: (s) => {
  if (extra && extra.some((e) => s.includes(e))) return {};
  return s.includes("data-assign-cell") ? cell : null;
} });
const down = (cell, extra) => listeners.mousedown({ button: 0, target: at(cell, extra) });
const over = (cell) => listeners.mouseover({ target: at(cell) });
const up = (cell) => listeners.mouseup({ target: at(cell) });

// 1) 週 0 から日 (1,2) までなぞる
down(cells[0]); over(cells[1]); over(cells[2]); over(cells[3]);
const marked = cells.filter((c) => c.set.has("assign-select-over")).length;
up(cells[3]);
const afterUp = cells.filter((c) => c.set.has("assign-select-over")).length;
// 2) 同じセルのクリックだけでは選ばない
down(cells[4]); up(cells[4]);
// 3) チップの上から始めたなぞりは選ばない
down(cells[0], [".assign-chip"]); over(cells[2]); up(cells[2]);
// 4) セルの外で離したときは選ばない
down(cells[0]); over(cells[1]); listeners.mouseup({ target: { closest: () => null } });
// 5) 右から左へなぞる
down(cells[4]); over(cells[2]); up(cells[2]);
console.log(JSON.stringify({ emitted, marked, afterUp }));
"""
        % ASSIGN_DRAG_JS,
        encoding="utf-8",
    )
    result = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["marked"] == 4  # (0) (1,0) (1,1) (1,2)
    assert out["afterUp"] == 0  # 離したら色を外す
    assert out["emitted"] == [
        [ASSIGN_SELECT_EVENT, {"first": {"week": 0, "day": None}, "last": {"week": 1, "day": 2}}],
        [ASSIGN_SELECT_EVENT, {"first": {"week": 2, "day": None}, "last": {"week": 1, "day": 1}}],
    ]
```

模擬の`down(cells[4], ...)`の 5 番目の`over`は`cells[2]`(週 1 の日 1)なので、`last`は`{week:1, day:1}`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_assign_drag.py -q 2>&1 | tail -6`
Expected: FAIL(`ImportError: cannot import name 'ASSIGN_SELECT_EVENT'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/assign_drag.py`:

1. `ASSIGN_DROP_EVENT = "assign_drop_member"`の次の行に`ASSIGN_SELECT_EVENT = "assign_select_range"`を足す。
2. `ASSIGN_DRAG_CSS`に足す(`.assign-drop-over`の行の次)。

```css
[data-assign-cell] { user-select: none; }
.assign-select-over, .assign-selected { outline: 2px solid #ff9800; outline-offset: -2px; background: rgba(255, 152, 0, 0.18); }
```

3. `ASSIGN_DRAG_JS`の最後の`document.addEventListener("dragend", …);`の次の行(`})();`の前)に足す。

```js
  // 範囲の選択(要望 168 段階 3b): 割り当ての行のセルを、マウスでなぞる
  const cellOf = (event) =>
    event.target.closest ? event.target.closest("[data-assign-cell]") : null;
  const blocked = (event) =>
    event.target.closest
      ? event.target.closest(".assign-chip, button, [data-assign-member]")
      : null;
  const clearSwipe = () => {
    document
      .querySelectorAll(".assign-select-over")
      .forEach((el) => el.classList.remove("assign-select-over"));
  };
  const place = (el) => ({
    week: Number(el.dataset.week),
    day: el.dataset.day === undefined || el.dataset.day === "" ? null : Number(el.dataset.day),
  });
  let swipeFrom = null;
  let swiping = false;

  document.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    const cell = cellOf(event);
    if (!cell || blocked(event)) return;
    swipeFrom = cell;
    swiping = false;
  });

  document.addEventListener("mouseover", (event) => {
    if (swipeFrom === null) return;
    const cell = cellOf(event);
    if (!cell) return;
    if (cell !== swipeFrom) swiping = true;
    clearSwipe();
    const cells = Array.from(document.querySelectorAll("[data-assign-cell]"));
    let a = cells.indexOf(swipeFrom);
    let b = cells.indexOf(cell);
    if (a < 0 || b < 0) return;
    if (a > b) [a, b] = [b, a];
    cells.slice(a, b + 1).forEach((el) => el.classList.add("assign-select-over"));
  });

  document.addEventListener("mouseup", (event) => {
    if (swipeFrom === null) return;
    const start = swipeFrom;
    const moved = swiping;
    swipeFrom = null;
    swiping = false;
    clearSwipe();
    const cell = cellOf(event);
    if (!moved || !cell || cell === start) return;
    emitEvent("assign_select_range", { first: place(start), last: place(cell) });
  });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_drag.py -q 2>&1 | tail -6`
Expected: PASS(既存のドラッグのシミュレーションも通ること。`node`がなければ skip)

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test
git add src/projectapp/assign_drag.py test/test_assign_drag.py
git commit -m "feat: アサイン画面の割り当ての行で、セルをなぞって範囲を選ぶ JS・CSS(要望 168 段階 3b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面(選択の状態・色付け・解除・範囲へのドロップ)

**Files:**
- Modify: `src/projectapp/assign_screen.py`
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`add_member_range`・`cell_in_range`・`ordered_cells`・`Cell`、Task 2 の`ASSIGN_SELECT_EVENT`
- Produces(テストが使う):
  - `AssignScreen.selection: tuple[Cell, Cell] | None`
  - `select_range(first: Cell, last: Cell)`・`clear_selection()`
  - モジュール関数`select_on_active(client_id: str, args: dict)`・`cell_of(item: dict) -> Cell`
  - マーカー: `assign-selection-clear`。選択のセルは CSS クラス`assign-selected`

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`の import に`select_on_active`(`from projectapp.assign_screen import ROW_HEIGHT_PX, AssignScreen, row_height, select_on_active`)を足し、末尾にテストを足す。

```python
async def test_selecting_a_range_marks_its_cells_and_shows_the_clear_button(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((0, None), (0, None))
    assert screen.selection == ((0, None), (0, None))
    await user.should_see(marker="assign-selection-clear")
    assert any(
        "assign-selected" in e.classes
        for e in user.find(marker="assign-cell-0").elements
    )


async def test_the_selection_is_ordered_whatever_the_swipe_direction(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((2, None), (1, None))
    assert screen.selection == ((1, None), (2, None))


async def test_dropping_inside_the_selection_adds_to_every_cell_in_it(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((1, None), (2, None))
    screen.drop_member("鈴木", 2, None)
    crews = [[a.name for a in w] for w in screen.trial.task.weekly_crew]
    assert crews[0] == ["田中"]
    assert crews[1] == ["田中", "鈴木"] and crews[2] == ["田中", "鈴木"]
    assert screen.selection is None  # 足したら選択を外す


async def test_dropping_outside_the_selection_adds_only_that_cell(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((1, None), (2, None))
    screen.drop_member("鈴木", 0, None)
    crews = [[a.name for a in w] for w in screen.trial.task.weekly_crew]
    assert crews[0] == ["田中", "鈴木"]
    assert all("鈴木" not in c for c in crews[1:])
    assert screen.selection == ((1, None), (2, None))  # 範囲の外なので選択は残る


async def test_dropping_when_everyone_is_already_in_the_range_changes_nothing(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.drop_member("鈴木", 2, None)
    before = screen.trial.task
    screen.select_range((1, None), (2, None))
    screen.drop_member("鈴木", 1, None)
    assert screen.trial.task == before
    assert screen.selection == ((1, None), (2, None))


async def test_the_clear_button_and_daily_toggle_remove_the_selection(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((0, None), (1, None))
    await user.should_see(marker="assign-selection-clear")
    user.find(marker="assign-selection-clear").click()
    assert screen.selection is None
    screen.select_range((0, None), (1, None))
    screen.toggle_daily(0)  # セルの並びが変わるので外す
    assert screen.selection is None


async def test_a_selection_without_a_start_date_is_ignored(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.plan = None
    screen.select_range((0, None), (1, None))
    assert screen.selection is None


async def test_the_select_event_is_routed_to_the_active_screen(user: User) -> None:
    screen, _ = await open_team_screen(user)
    select_on_active(
        screen.client_id,
        {"first": {"week": 0, "day": None}, "last": {"week": 1, "day": None}},
    )
    assert screen.selection == ((0, None), (1, None))
    select_on_active("other", {"first": {"week": 0, "day": None}, "last": {"week": 2, "day": None}})
    assert screen.selection == ((0, None), (1, None))  # 知らないクライアントは無視


async def test_a_range_selection_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((0, None), (1, None))
    assert not is_dirty(screen.trial)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_assign_screen.py -q -k "selection or select or range" 2>&1 | tail -8`
Expected: FAIL(`ImportError: cannot import name 'select_on_active'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/assign_screen.py`:

1. import: `from projectapp.assign_drag import (ASSIGN_DRAG_CSS, ASSIGN_DRAG_JS, ASSIGN_DROP_EVENT, ASSIGN_SELECT_EVENT)`にし、`from projectapp.daily_crew import (...)`に`Cell`・`add_member_range`・`cell_in_range`・`ordered_cells`を足し、`from projectapp.models import (...)`に`MAX_WEEKS`を足す。
2. `__init__`の末尾に`self.selection: tuple[Cell, Cell] | None = None`を足す。
3. `open`の`REGISTERED`のブロックで、`ui.on(ASSIGN_DROP_EVENT, …)`の次の行に足す。

```python
                ui.on(
                    ASSIGN_SELECT_EVENT,
                    lambda e: select_on_active(client_id, e.args),
                )
```

4. `cell`の先頭(`left, span = …`の次)に`selected = self.selection is not None and cell_in_range(*self.selection, week, day)`を足し、`.classes("items-start")`を`.classes("items-start assign-selected" if selected else "items-start")`にする。
5. `assign_row`の`with row:`の先頭(`for seg in segs:`の前)に足す。

```python
            if self.selection is not None:
                ui.button("選択を解除", on_click=self.clear_selection).props(
                    "flat dense size=xs"
                ).style(
                    "position: absolute; left: 4px; top: -2px; z-index: 2;"
                    " min-height: 16px; padding: 0 4px"
                ).mark("assign-selection-clear")
```

6. メソッドを足す(`drop_member`の前)。

```python
    def select_range(self, first: Cell, last: Cell) -> None:
        """割り当ての行で選んだ範囲(両端を含む)を、日付の順にして持つ。開始日がない・範囲外の週なら無視する。"""
        if self.plan is None:
            return
        for week, day in (first, last):
            if not 0 <= week < MAX_WEEKS or (
                day is not None and not 0 <= day < WEEK_DAYS
            ):
                return
        self.selection = ordered_cells(first, last)
        self.refresh()

    def clear_selection(self) -> None:
        if self.selection is not None:
            self.selection = None
            self.refresh()
```

7. `drop_member`の、名簿の確認(`このメンバーは名簿にいません`)の直後・`result = add_member(…)`の前に足す。

```python
        selection = self.selection
        if selection is not None and cell_in_range(*selection, week, day):
            ranged = add_member_range(
                self.trial.task, name, *selection, weeks=self.plan.weeks
            )
            if ranged is None:
                ui.notify("すでに割り当てています", type="warning")
                return
            self.trial.task = ranged
            self.selection = None
            self.refresh()
            return
```

8. `toggle_daily`の、`self.trial.task = result`の直前に`self.selection = None`を足す。
9. モジュール関数を`drop_on_active`の次に足す。

```python
def cell_of(item: dict) -> Cell:
    """JS から来た`{week, day}`を`(週, 日 or None)`にする。"""
    day = item["day"]
    return int(item["week"]), None if day is None else int(day)


def select_on_active(client_id: str, args: dict) -> None:
    """範囲の選択のイベントを、そのクライアントで今開いている画面に渡す。"""
    screen = ACTIVE.get(client_id)
    if screen is not None:
        screen.select_range(cell_of(args["first"]), cell_of(args["last"]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py test/test_assign_drag.py -q 2>&1 | tail -6`
Expected: PASS(全件)

- [ ] **Step 5: Format, lint, commit**

```bash
uvx ruff format src test -q && uvx ruff check src test && uvx ty check src 2>&1 | tail -1
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン画面で、選んだ範囲のセルへメンバーをまとめて足す(要望 168 段階 3b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 仕様・構成・状態表記と、全体の確認

**Files:**
- Modify: `.claude/spec/dashboard.md`(`段階 3a(割り当て率)`の段落の末尾の`一定区間からの集中増員は段階 3b。`)・`docs/development.md`(`daily_crew.py`・`assign_screen.py`・`assign_drag.py`の行)・`docs/requests.md`(要望 168 の状態)

- [ ] **Step 1: 仕様・構成・状態を書く**

- `.claude/spec/dashboard.md`: `一定区間からの集中増員は段階 3b。`を、段階 3b の説明に置き換える: 割り当ての行のセルをマウスでなぞると、範囲(週をまたいでよい。日ごとの週は日単位)を選べ、色が付く。選べるのは表示中のセル単位だけ(週の途中から選ぶときは先に`日ごと`にする)。選んだ範囲の中のセルへメンバーを落とすと、範囲のすべてのセルに 100% で足す(すでにいるセルは飛ばす)。範囲の外へ落とすと、そのセルだけ。足したら選択を外す。`選択を解除`のボタンでも外せる。`日ごと`/`週に戻す`でも外す。選択は試算に含めない
- `docs/development.md`: `daily_crew.py`の行に`add_member_range`・`cell_in_range`・`range_cells`・`ordered_cells`、`assign_drag.py`の行(なければ`assign_screen.py`の行)に範囲の選択の JS、`assign_screen.py`の行に`selection`を足す
- `docs/requests.md`の要望 168 の状態: 段階 3b は実装済み(設計書: `docs/superpowers/specs/2026-11-22-assign-screen-stage3b-design.md`・計画: `docs/superpowers/plans/2026-11-22-assign-screen-stage3b.md`。PR は作成後に記す。実機確認待ち)・4・5 は未着手

- [ ] **Step 2: 全体の確認**

Run: `uv run pytest -m smoke -q 2>&1 | tail -3 && uv run pytest -q -n auto test/test_daily_crew_assign.py test/test_daily_crew.py test/test_assign_screen.py test/test_assign_trial.py test/test_assign_drag.py test/test_gantt.py test/test_context_menu.py test/test_dashboard_view.py test/test_views.py 2>&1 | tail -3 && uvx ruff check src test && uvx ty check src 2>&1 | tail -1`
Expected: smoke・関連テストが通る。ty は 9 件(既存)

- [ ] **Step 3: Commit**

```bash
git add .claude/spec docs/development.md docs/requests.md
git commit -m "docs: アサイン画面の範囲を選んでの集中増員(段階 3b)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実装後、全体のレビュー(sonnet の subagent)→ 指摘の修正 1 回 → push して PR を作って止まる(マージは利用者の指示を待つ)。
