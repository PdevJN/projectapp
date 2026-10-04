# 進捗率に応じたバーの表現 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 進捗度と予定の経過を比べて、タスクを「通常・遅延・前倒し・完了・遅延完了」に判定し、予定の棒に進捗の塗り分け・状態の枠線・右の印で表す。

**Architecture:** 判定は `timeline.py` の純粋関数(`expected_progress`、`progress_state`)。表現は `gantt.py` の `task_row` で、予定の棒の内側に塗り(`progress_fill`)を足し、棒に枠線を付け、右に印(`progress_marker`)を出す。データ・保存形式は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、`ty`。

**Spec:** `docs/superpowers/specs/2026-10-04-progress-bar-design.md`

## Global Constraints

- テストは `test/` 配下。実行は `uv run pytest -q`、型チェックは `uvx ty check src`。
- 許容幅 `PROGRESS_TOLERANCE = 10`(パーセントポイント)。進んでいるはずの割合は暦の時間で計算する。
- 枠線の色: 遅延 `#b26a00`、前倒し `#00897b`、完了 `#757575`、遅延完了 `#8e24aa`。赤と橙(◆の色)は使わない。
- 印: 遅延 `▼`、前倒し `▲`、完了 `✓`、遅延完了 `✓!`。通常と `None` には出さない。
- 進捗度 `0` は「入力あり」。`if progress:` ではなく `is not None` で判定する。
- 塗りは `pointer-events: none`(棒のクリック・ドラッグを妨げない)。印はツールチップを出すため、マウスを受ける(棒の外にある小さな要素なので、棒の操作は妨げない)。
- 画面の文言は日本語。コメントは既存のコードに合わせて日本語で簡潔に。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

- 許容幅ちょうどの差は「通常」で、1 超えたときだけ遅延・前倒しになる(Task 1)。
- 進捗度 `0` が「未入力」と混同されない。判定にも塗り(幅 `0%`)にも使われる(Task 1, 2)。
- 状態が「終了」で、実績の終了がないタスクは「遅延完了」にならず「完了」になる。進捗度が空でも塗りは 100%(Task 1, 2)。
- 開始予定や完了予定がないタスク(棒がない)は、塗り・枠線・印のいずれも出ず、実績の棒だけのタスクは今のまま(Task 2, 3)。
- 長さ 0 の予定(開始予定 = 完了予定)で、判定が割り算で落ちない(Task 1)。
- 塗りがクリック・ドラッグを妨げず、割り当て超過の縞が塗りの上に残る(Task 2)。

---

### Task 1: 進捗の状態の判定

**Files:**
- Modify: `src/projectapp/timeline.py`
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: 既存の `current_progress(task) -> int | None`、`effective_end(task, project, holidays)`、`is_overdue(task, project, holidays, now)`、`Status`。
- Produces:
  - `timeline.ProgressState`(`StrEnum`: `NORMAL="通常"`、`DELAYED="遅延"`、`AHEAD="前倒し"`、`DONE="完了"`、`LATE_DONE="遅延完了"`)
  - `timeline.PROGRESS_TOLERANCE: int = 10`
  - `timeline.expected_progress(start: datetime, end: datetime, now: datetime) -> float`
  - `timeline.progress_state(task: Task, project: Project, holidays: dict[date, str], now: datetime) -> ProgressState | None`

- [ ] **Step 1: Write the failing tests**

`test/test_timeline.py` の import に `PROGRESS_TOLERANCE`、`ProgressState`、`expected_progress`、`progress_state` を足し(`timeline` からの import 一覧に追加)、末尾に追加する。

```python
P_START = datetime(2026, 10, 5, 12)
P_END = datetime(2026, 10, 7, 12)  # 48時間
P_MID = datetime(2026, 10, 6, 12)  # ちょうど50%


def running(progress: int | None, **overrides: object) -> Task:
    actuals = [Actual(P_START, None, progress)] if progress is not None else []
    values: dict[str, object] = {
        "planned_start": P_START,
        "planned_end": P_END,
        "status": Status.RUNNING,
        "actuals": actuals,
    }
    values.update(overrides)
    return Task("t", **values)  # type: ignore[arg-type]


def state_of(task: Task, now: datetime) -> ProgressState | None:
    return progress_state(task, project_with(task), {}, now)


def test_expected_progress_before_during_and_after() -> None:
    assert expected_progress(P_START, P_END, datetime(2026, 10, 5)) == 0.0
    assert expected_progress(P_START, P_END, P_MID) == 50.0
    assert expected_progress(P_START, P_END, datetime(2026, 10, 9)) == 100.0


def test_expected_progress_of_a_zero_length_plan() -> None:
    assert expected_progress(P_MID, P_MID, datetime(2026, 10, 6, 11)) == 0.0
    assert expected_progress(P_MID, P_MID, P_MID) == 100.0
    assert expected_progress(P_MID, P_MID, datetime(2026, 10, 6, 13)) == 100.0


def test_tolerance_is_ten_points() -> None:
    assert PROGRESS_TOLERANCE == 10


@pytest.mark.parametrize(
    ("progress", "expected"),
    [
        (39, ProgressState.DELAYED),
        (40, ProgressState.NORMAL),  # ちょうど許容幅の差は通常
        (50, ProgressState.NORMAL),
        (60, ProgressState.NORMAL),
        (61, ProgressState.AHEAD),
    ],
)
def test_progress_against_the_expected_ratio(progress: int, expected: ProgressState) -> None:
    assert state_of(running(progress), P_MID) is expected


@pytest.mark.parametrize(
    ("progress", "expected"), [(0, ProgressState.NORMAL), (10, ProgressState.NORMAL), (11, ProgressState.AHEAD)]
)
def test_before_the_planned_start_the_expected_ratio_is_zero(
    progress: int, expected: ProgressState
) -> None:
    assert state_of(running(progress), datetime(2026, 10, 4, 12)) is expected


def test_progress_zero_counts_as_entered_and_is_delayed_when_behind() -> None:
    assert state_of(running(0), datetime(2026, 10, 7)) is ProgressState.DELAYED


def test_no_state_without_progress_or_plan() -> None:
    assert state_of(running(None), P_MID) is None
    assert state_of(running(50, planned_start=None), P_MID) is None
    assert state_of(running(50, planned_end=None), P_MID) is None


def test_zero_length_plan_does_not_crash() -> None:
    task = running(50, planned_start=P_MID, planned_end=P_MID)
    assert state_of(task, datetime(2026, 10, 6, 11)) is ProgressState.AHEAD
    assert state_of(task, datetime(2026, 10, 6, 13)) is ProgressState.DELAYED


def test_done_in_time_is_done() -> None:
    task = running(100, status=Status.DONE, actuals=[Actual(P_START, datetime(2026, 10, 7, 10), 100)])
    assert state_of(task, datetime(2026, 10, 20)) is ProgressState.DONE


def test_done_after_the_planned_end_is_late_done() -> None:
    task = running(100, status=Status.DONE, actuals=[Actual(P_START, datetime(2026, 10, 8, 12), 100)])
    assert state_of(task, datetime(2026, 10, 20)) is ProgressState.LATE_DONE


def test_done_without_an_actual_end_is_done_not_late_done() -> None:
    assert state_of(running(None, status=Status.DONE), datetime(2026, 10, 20)) is ProgressState.DONE
    assert state_of(Task("t", status=Status.DONE), datetime(2026, 10, 20)) is ProgressState.DONE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_timeline.py -q`
Expected: FAIL(`ImportError: cannot import name 'PROGRESS_TOLERANCE'`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/timeline.py` の `is_overdue` の後ろ(ファイルのこの付近。`current_progress` より後ならどこでもよい)に追加する。

```python
class ProgressState(StrEnum):
    NORMAL = "通常"
    DELAYED = "遅延"
    AHEAD = "前倒し"
    DONE = "完了"
    LATE_DONE = "遅延完了"


PROGRESS_TOLERANCE = 10  # 進んでいるはずの割合との差の許容幅(パーセントポイント)


def expected_progress(start: datetime, end: datetime, now: datetime) -> float:
    """現在時刻までに進んでいるはずの割合(0〜100)。暦の時間で、開始〜完了予定の経過割合。"""
    if end <= start:
        return 100.0 if now >= end else 0.0
    ratio = (now - start) / (end - start)
    return min(max(ratio, 0.0), 1.0) * 100


def progress_state(
    task: Task, project: Project, holidays: dict[date, str], now: datetime
) -> ProgressState | None:
    """進捗の状態。終了は完了か遅延完了(超過の判定は is_overdue)。それ以外は、進捗度を
    進んでいるはずの割合と比べる。進捗度か予定がなければ判定できず None。"""
    if task.status is Status.DONE:
        late = is_overdue(task, project, holidays, now)
        return ProgressState.LATE_DONE if late else ProgressState.DONE
    percent = current_progress(task)
    end = effective_end(task, project, holidays)
    if percent is None or task.planned_start is None or end is None:
        return None
    expected = expected_progress(task.planned_start, end, now)
    if percent < expected - PROGRESS_TOLERANCE:
        return ProgressState.DELAYED
    if percent > expected + PROGRESS_TOLERANCE:
        return ProgressState.AHEAD
    return ProgressState.NORMAL
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_timeline.py -q`
Expected: PASS(既存のテストも通る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "進捗の状態(通常・遅延・前倒し・完了・遅延完了)を判定する関数を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 予定の棒の進捗の塗り分け

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `timeline.current_progress`、`Status`。
- Produces: `gantt.fill_percent(task: Task) -> int | None`、マーク `progress-fill-{key}-{ti}`(塗りの `div`)。

- [ ] **Step 1: Write the failing tests**

`test/test_gantt.py` の import(`from projectapp.gantt import (...)`)に `fill_percent` を足し、`test_actual_bar_clips_its_progress_text` の後ろに追加する。

```python
def progress_project(progress: int | None, **overrides: object) -> Project:
    actuals = [Actual(datetime(2026, 10, 5, 12), None, progress)] if progress is not None else []
    values: dict[str, object] = {
        "planned_start": datetime(2026, 10, 5, 12),
        "planned_end": datetime(2026, 10, 7, 12),
        "color": "#ff0000",
        "status": Status.RUNNING,
        "actuals": actuals,
    }
    values.update(overrides)
    task = Task("設計", **values)  # type: ignore[arg-type]
    return Project("demo", base_date=BASE, sections=[Section("開発", [task])])


def test_fill_percent() -> None:
    assert fill_percent(Task("t", actuals=[Actual(datetime(2026, 10, 5, 9), None, 40)])) == 40
    assert fill_percent(Task("t", actuals=[Actual(datetime(2026, 10, 5, 9), None, 0)])) == 0
    assert fill_percent(Task("t")) is None
    assert fill_percent(Task("t", status=Status.DONE)) == 100
    done = Task("t", status=Status.DONE, actuals=[Actual(datetime(2026, 10, 5, 9), None, 80)])
    assert fill_percent(done) == 80


async def test_planned_bar_is_filled_by_the_progress(user: User) -> None:
    mount(progress_project(40))
    await user.open("/")
    fill = user.find(marker="progress-fill-0-0").elements.pop()
    assert fill._style["width"] == "40%"
    assert fill._style["left"] == "0"
    assert fill._style["background"] == "#ff0000"
    assert fill._style["pointer-events"] == "none"


async def test_progress_zero_makes_a_zero_width_fill(user: User) -> None:
    mount(progress_project(0))
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "0%"


async def test_no_fill_without_progress(user: User) -> None:
    mount(progress_project(None))
    await user.open("/")
    await user.should_see(marker="bar-0-0")
    await user.should_not_see(marker="progress-fill-0-0")


async def test_done_without_progress_is_filled_completely(user: User) -> None:
    mount(progress_project(None, status=Status.DONE))
    await user.open("/")
    assert user.find(marker="progress-fill-0-0").elements.pop()._style["width"] == "100%"


async def test_no_fill_without_a_planned_bar(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 6, 12), None, 40)])
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see(marker="actual-0-0-0")
    await user.should_not_see(marker="progress-fill-0-0")


async def test_fill_is_inside_the_bar_and_below_the_overload_stripes(user: User) -> None:
    mount(progress_project(40))
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    markers = [m for child in bar.default_slot.children for m in child._markers]
    assert markers[0].startswith("progress-fill-")  # 縞(overload-)より先に置く = 縞が手前
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_gantt.py -q -k "fill"`
Expected: FAIL(`cannot import name 'fill_percent'`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/gantt.py`:

import を追加・拡張する。`from projectapp.models import DEFAULT_COLOR, Project, Section, Task, is_hex_color` を次に置き換える。

```python
from projectapp.models import DEFAULT_COLOR, Project, Section, Status, Task, is_hex_color
```

`from projectapp.timeline import (...)` の一覧に `current_progress` を足す(`clip_overloads` の次)。

モジュールレベル関数を `planned_background` の後ろに追加する。

```python
def fill_percent(task: Task) -> int | None:
    """予定の棒を塗る進捗度の割合。進捗度がなくても、終了なら100。それ以外で進捗度がなければ None。"""
    percent = current_progress(task)
    if percent is None and task.status is Status.DONE:
        return 100
    return percent
```

`task_row` の `with bar:` ブロックを置き換える。

```python
                with bar:
                    self.progress_fill(key, ti, task)
                    self.overload_stripes(key, ti, task, left, bar_width, columns, width)
```

`actual_bars` の前にメソッドを追加する。

```python
    def progress_fill(self, key: int | str, ti: int, task: Task) -> None:
        """予定の棒の左端から、進捗度の割合の幅を、タスクの色で不透明に塗る。縞より先に置いて、縞を手前にする。"""
        percent = fill_percent(task)
        if percent is None:
            return
        color = task.color if is_hex_color(task.color) else DEFAULT_COLOR
        ui.element("div").style(
            f"position: absolute; left: 0; top: 0; bottom: 0; width: {percent}%;"
            f" background: {color}; pointer-events: none"
        ).mark(f"progress-fill-{key}-{ti}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_gantt.py -q`
Expected: PASS(既存のテストも通る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "予定の棒を、進捗度の割合だけタスクの色で塗る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 状態の枠線と印

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: Task 1 の `ProgressState`、`progress_state`、`expected_progress`。Task 2 の `progress_project`(テストのヘルパー)。
- Produces: `gantt.PROGRESS_STATE_COLORS: dict[ProgressState, str]`、`gantt.PROGRESS_STATE_MARKS: dict[ProgressState, str]`、マーク `progress-state-{key}-{ti}`(印の `label`)。

- [ ] **Step 1: Write the failing tests**

`test/test_gantt.py` の import に `PROGRESS_STATE_COLORS`、`PROGRESS_STATE_MARKS` を足し(`from projectapp.timeline import Scale` は `Scale, ProgressState` に)、Task 2 のテストの後ろに追加する。

```python
MID = datetime(2026, 10, 6, 12)  # 予定の中間(進んでいるはずの割合は50%)


def test_state_colors_and_marks_cover_the_visible_states() -> None:
    assert PROGRESS_STATE_COLORS == {
        ProgressState.DELAYED: "#b26a00",
        ProgressState.AHEAD: "#00897b",
        ProgressState.DONE: "#757575",
        ProgressState.LATE_DONE: "#8e24aa",
    }
    assert PROGRESS_STATE_MARKS == {
        ProgressState.DELAYED: "▼",
        ProgressState.AHEAD: "▲",
        ProgressState.DONE: "✓",
        ProgressState.LATE_DONE: "✓!",
    }


@pytest.mark.parametrize(
    ("progress", "state"),
    [(10, ProgressState.DELAYED), (90, ProgressState.AHEAD)],
)
async def test_bar_outline_and_mark_follow_the_state(
    user: User, progress: int, state: ProgressState
) -> None:
    mount(progress_project(progress), now=MID)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["outline"] == f"2px solid {PROGRESS_STATE_COLORS[state]}"
    assert bar._style["outline-offset"] == "-2px"
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert mark.text == PROGRESS_STATE_MARKS[state]
    assert mark._style["color"] == PROGRESS_STATE_COLORS[state]
    assert mark._style["left"] == "304.0px"  # 200 + 0.5 * 40 + 2.0 * 40 + 4


async def test_normal_state_has_no_outline_and_no_mark(user: User) -> None:
    mount(progress_project(50), now=MID)
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert "outline" not in bar._style
    await user.should_not_see(marker="progress-state-0-0")


async def test_no_state_without_progress_has_no_outline_and_no_mark(user: User) -> None:
    mount(progress_project(None), now=MID)
    await user.open("/")
    assert "outline" not in user.find(marker="bar-0-0").elements.pop()._style
    await user.should_not_see(marker="progress-state-0-0")


async def test_done_state_is_marked(user: User) -> None:
    in_time = Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 7, 10), 100)
    mount(progress_project(100, status=Status.DONE, actuals=[in_time]), now=datetime(2026, 10, 20))
    await user.open("/")
    assert user.find(marker="progress-state-0-0").elements.pop().text == "✓"


async def test_late_done_state_is_marked(user: User) -> None:
    late = Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 8, 12), 100)
    mount(progress_project(100, status=Status.DONE, actuals=[late]), now=datetime(2026, 10, 20))
    await user.open("/")
    assert user.find(marker="progress-state-0-0").elements.pop().text == "✓!"
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["outline"] == f"2px solid {PROGRESS_STATE_COLORS[ProgressState.LATE_DONE]}"


async def test_state_mark_tooltips(user: User) -> None:
    mount(progress_project(10), now=MID)
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    tooltips = [c for c in mark.default_slot.children if isinstance(c, ui.tooltip)]
    assert [t.text for t in tooltips] == ["遅延(進捗 10% / 予定 50%)"]


async def test_done_mark_tooltip_has_no_progress_part(user: User) -> None:
    mount(progress_project(None, status=Status.DONE), now=datetime(2026, 10, 20))
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    tooltips = [c for c in mark.default_slot.children if isinstance(c, ui.tooltip)]
    assert [t.text for t in tooltips] == ["完了"]


async def test_no_outline_or_mark_without_a_planned_bar(user: User) -> None:
    task = Task("設計", status=Status.DONE, actuals=[Actual(datetime(2026, 10, 6, 12), None, 40)])
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see(marker="actual-0-0-0")
    await user.should_not_see(marker="progress-state-0-0")


async def test_overdue_background_and_state_outline_coexist(user: User) -> None:
    late = Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 8, 12), 100)
    mount(progress_project(100, status=Status.DONE, actuals=[late]), now=datetime(2026, 10, 20))
    await user.open("/")
    row = user.find(marker="row-0-0").elements.pop()
    assert OVERDUE_COLOR in row._style["background"]
```

(`pytest` は `test_gantt.py` で import 済み。`OVERDUE_COLOR` が import されていなければ `from projectapp.gantt import (...)` に足す。)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/test_gantt.py -q -k "state or outline or late_done"`
Expected: FAIL(`cannot import name 'PROGRESS_STATE_COLORS'`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/gantt.py`:

`from projectapp.timeline import (...)` の一覧に `ProgressState`、`expected_progress`、`progress_state` を足す(アルファベット順の位置に)。

定数を `OVERDUE_COLOR` の次の行に追加する。

```python
# 進捗の状態を示す枠線の色と印。赤は予定超過の背景、橙は◆(締切)と競合するので使わない。通常は何も出さない
PROGRESS_STATE_COLORS = {
    ProgressState.DELAYED: "#b26a00",
    ProgressState.AHEAD: "#00897b",
    ProgressState.DONE: "#757575",
    ProgressState.LATE_DONE: "#8e24aa",
}
PROGRESS_STATE_MARKS = {
    ProgressState.DELAYED: "▼",
    ProgressState.AHEAD: "▲",
    ProgressState.DONE: "✓",
    ProgressState.LATE_DONE: "✓!",
}
```

`task_row` の予定の棒の作成部を置き換える。`bar = ui.element("div").style(...)` の前に状態を求め、スタイルに枠線を足し、棒の後ろに印を出す。

```python
            end = effective_end(task, self.project, self.holidays)
            span = bar_span(task.planned_start, end, columns)
            if span is not None:
                left, length = span
                bar_width = max(length * width, MIN_BAR_PX)
                draggable = self.scale is Scale.DAY
                cursor = "grab" if draggable else "pointer"
                state = progress_state(task, self.project, self.holidays, self.now())
                outline = ""
                if state in PROGRESS_STATE_COLORS:
                    outline = f" outline: 2px solid {PROGRESS_STATE_COLORS[state]}; outline-offset: -2px;"
                bar = ui.element("div").style(
                    f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                    f" width: {bar_width:.1f}px; top: {BAR_TOP_PX}px;"
                    f" height: {BAR_HEIGHT_PX}px;"
                    f" background: {planned_background(task.color if is_hex_color(task.color) else DEFAULT_COLOR)};"
                    f" border-radius: 4px; cursor: {cursor}; overflow: hidden;{outline}"
                    " user-select: none; touch-action: none"
                )
```

(`bar.on(...)`・`bar.mark(...)`・`if draggable:`・`with bar:` はそのまま。)`with bar:` ブロックの直後(`self.actual_bars(...)` の前、`if span is not None:` の内側)に追加する。

```python
                self.progress_marker(
                    key, ti, task, state, NAME_WIDTH_PX + left * width + bar_width, end
                )
```

`progress_fill` の後ろにメソッドを追加する。

```python
    def progress_marker(
        self,
        key: int | str,
        ti: int,
        task: Task,
        state: ProgressState | None,
        bar_right: float,
        end: datetime | None,
    ) -> None:
        """棒の右に、状態の印を小さく出す。通常と判定できないときは出さない。"""
        if state not in PROGRESS_STATE_MARKS:
            return
        color = PROGRESS_STATE_COLORS[state]
        tip = state.value
        percent = current_progress(task)
        if state in (ProgressState.DELAYED, ProgressState.AHEAD) and percent is not None:
            if task.planned_start is not None and end is not None:
                expected = expected_progress(task.planned_start, end, self.now())
                tip = f"{state.value}(進捗 {percent}% / 予定 {expected:.0f}%)"
        ui.label(PROGRESS_STATE_MARKS[state]).style(
            f"position: absolute; left: {bar_right + 4:.1f}px; top: {BAR_TOP_PX}px;"
            f" line-height: {BAR_HEIGHT_PX}px; font-size: 11px; color: {color}"
        ).tooltip(tip).mark(f"progress-state-{key}-{ti}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_gantt.py -q && uvx ty check src`
Expected: PASS、`All checks passed!`(既存の棒・実績・縞のテストも通る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "予定の棒に、進捗の状態を示す枠線と印を出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 開発者向け文書と全体の確認

**Files:**
- Modify: `docs/development.md`
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: Update docs**

`docs/development.md` の「ファイル形式の注意」の前(「コマンド」の節の後ろ)ではなく、既存の進捗度の記述(`timeline.current_progress` を述べた項目)の直後に、次の項目を足す。

```text
- ガントチャートの進捗の状態(`timeline.progress_state`)は、状態が「終了」なら完了か遅延完了(`is_overdue` で決める)、それ以外は進捗度を「進んでいるはずの割合」(`expected_progress`。開始予定〜完了予定の経過割合を暦の時間で計算し、稼働時間・祝日は見ない)と比べ、許容幅 `PROGRESS_TOLERANCE`(10pt)を超えた差で遅延・前倒しにする。進捗度か予定がないと判定せず、棒は塗り・枠線・印なしになる。判定はファイルには保存しない。
```

`.claude/MEMORY.md` の「今後の要望」の 14 を `14. (完了)進捗率に応じたバーの表現: ...` に変え、末尾に「対応: `timeline.progress_state`(通常・遅延・前倒し・完了・遅延完了)。予定の棒の塗り・枠線・右の印。許容幅10pt、暦の時間で計算。状態別の色は要望12。」を足す。

- [ ] **Step 2: Run the full verification**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 3: Commit**

```bash
git add docs/development.md .claude/MEMORY.md
git commit -m "作業記録: 進捗率に応じたバーの表現の実装を反映

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実機での確認(ユーザーが行う): 進捗度を入れたタスクで、棒が進捗の幅だけ濃く塗られること。遅延・前倒しで枠線と `▼` / `▲` が出ること。「終了」にして、間に合えば灰の枠と `✓`、遅れれば紫の枠と `✓!`(赤い背景のまま)になること。
