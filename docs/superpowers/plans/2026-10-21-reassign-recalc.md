# 付け替え時の完了予定の見直し Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 実績か進捗度のあるタスクの担当を付け替えて換算率が変わるとき、保存の場で、残りの作業を新しい換算率で見直した完了予定にするかを選べるようにする(要望 32)。

**Architecture:** 計算は NiceGUI に依存しない純粋関数の新モジュール `reassign.py`(消化分・要否の判定・見直した完了予定)に置く。編集ダイアログ `task_dialog.py` の `save()` が、`build_task` の成功後に判定し、必要なら確認ダイアログ(`見直す`・`見直さない`・`編集に戻る`)を出す。`見直す`は、算出した日時を手指定の完了予定として保存する。ファイル形式は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User` のシミュレーション)、`uv run pytest`・`uv run ty check src`

**Spec:** `docs/superpowers/specs/2026-10-21-reassign-recalc-design.md`

## Global Constraints

- 言語は日本語。コメントは日本語で、周囲の密度に合わせる(docstring は 1〜2 行)。
- 工数・実績・進捗度は変えない。ファイル形式の`version`は変えない。
- 完了予定の算出は`timeline.calc_end`を使う(稼働可能時間・始業時刻・祝日を反映)。換算は`timeline.combine_rate(rate, 1.0)`で、使えない値を 1.0 にする。
- 選択を出すのは、既存タスクの編集のときだけ(新規追加では出さない)。
- 保存は、元に戻す 1 ステップのまま(`on_save` を 1 回だけ呼ぶ)。
- 全テストと`ty check`が通ること。

## Review Focus

- 進行中の区間(`end` が`None`)の実績だけがあるとき: 消化分に数えない(0 として見直す)。
- 進捗度が 100% のとき: 残りが 0 なので、確認を出さず、そのまま保存する。
- 開始予定が今より先のとき: 起点は開始予定(過去へ戻さない)。
- 工数がない・チェックポイント・状態が`終了`のとき: 確認を出さない。
- 割り当て率だけの変更(メンバーは同じ)でも換算率が変われば出す。換算率が変わらない保存(名前だけの変更など)では出さない。

---

## File Structure

| ファイル | 役割 |
| --- | --- |
| 作成: `src/projectapp/reassign.py` | 消化分・要否・見直した完了予定の純粋関数 |
| 作成: `test/test_reassign.py` | 上の単体テスト |
| 変更: `src/projectapp/task_dialog.py` | `save()` に確認ダイアログを挟む。`now` 引数を足す |
| 変更: `test/test_task_dialog.py` | `mount_dialog` に `now` を通し、確認ダイアログのテストを足す |
| 変更: `CLAUDE.md`・`docs/development.md`・`docs/requests.md`・`docs/request-history.md`・`.claude/MEMORY.md` | 仕様・構成・状態の反映 |

---

### Task 1: 純粋関数 `reassign.py`

**Files:**
- Create: `src/projectapp/reassign.py`
- Test: `test/test_reassign.py`

**Interfaces:**
- Consumes: `projectapp.models.Task`・`Actual`・`Status`・`TaskKind`、`projectapp.timeline.calc_end`・`combine_rate`
- Produces:
  - `consumed_hours(task: Task, old_rate: float) -> float`
  - `needs_review(task: Task, old_rate: float, new_rate: float) -> bool`
  - `reviewed_end(task: Task, old_rate: float, new_rate: float, daily_hours: float, work_start: time, holidays: dict[date, str], now: datetime) -> datetime | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_reassign.py` を作る。

```python
from datetime import date, datetime, time

import pytest

from projectapp.models import Actual, Status, Task, TaskKind
from projectapp.reassign import consumed_hours, needs_review, reviewed_end

WORK_START = time(9, 0)
NOW = datetime(2026, 10, 14, 10, 0)  # 水曜


def task(**kwargs) -> Task:
    base = dict(name="設計", planned_start=datetime(2026, 10, 12, 9, 0), effort_hours=16.0, status=Status.RUNNING)
    return Task(**{**base, **kwargs})


def test_consumed_uses_the_progress_first() -> None:
    t = task(progress=50, actuals=[Actual(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 12))])
    assert consumed_hours(t, 1.0) == pytest.approx(8.0)


def test_consumed_falls_back_to_the_actual_time_times_the_old_rate() -> None:
    t = task(actuals=[Actual(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 13)),
                      Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 11))])
    assert consumed_hours(t, 1.5) == pytest.approx(9.0)  # 6h × 1.5


def test_consumed_ignores_a_running_interval_and_zero_progress() -> None:
    t = task(progress=0, actuals=[Actual(datetime(2026, 10, 12, 9), None)])
    assert consumed_hours(t, 1.0) == 0.0


def test_consumed_is_capped_at_the_effort() -> None:
    t = task(effort_hours=4.0, actuals=[Actual(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 18))])
    assert consumed_hours(t, 2.0) == pytest.approx(4.0)


def test_consumed_is_zero_without_effort_or_records() -> None:
    assert consumed_hours(task(effort_hours=0.0, progress=50), 1.0) == 0.0
    assert consumed_hours(task(), 1.0) == 0.0


@pytest.mark.parametrize("kwargs", [{"progress": 30}, {"actuals": [Actual(datetime(2026, 10, 12, 9), None)]}])
def test_needs_review_when_a_record_exists_and_the_rate_changes(kwargs) -> None:
    assert needs_review(task(**kwargs), 1.0, 0.5)


def test_needs_review_is_false_when_the_rate_is_unchanged() -> None:
    assert not needs_review(task(progress=30), 1.0, 1.0)
    assert not needs_review(task(progress=30), 1.0, 1.0 + 1e-12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # 実績も進捗度もない
        {"progress": 0},
        {"progress": 30, "effort_hours": 0.0},
        {"progress": 30, "status": Status.DONE},
        {"progress": 30, "kind": TaskKind.CHECKPOINT},
        {"progress": 30, "kind": TaskKind.SUMMARY},
    ],
)
def test_needs_review_is_false_for_the_excluded_tasks(kwargs) -> None:
    assert not needs_review(task(**kwargs), 1.0, 0.5)


def test_reviewed_end_converts_the_remaining_effort_with_the_new_rate() -> None:
    # 残り 8h ÷ 0.5 = 16h。水 10:00〜15:30 で 5.5h、木 6.5h、金 4h → 金 13:00
    t = task(progress=50)
    assert reviewed_end(t, 1.0, 0.5, 6.5, WORK_START, {}, NOW) == datetime(2026, 10, 16, 13, 0)


def test_reviewed_end_skips_holidays() -> None:
    t = task(progress=50)
    holidays = {date(2026, 10, 16): "休み"}
    assert reviewed_end(t, 1.0, 0.5, 6.5, WORK_START, holidays, NOW) == datetime(2026, 10, 19, 13, 0)


def test_reviewed_end_starts_from_the_planned_start_when_it_is_later() -> None:
    t = task(progress=50, planned_start=datetime(2026, 10, 19, 9, 0))
    assert reviewed_end(t, 1.0, 1.0, 6.5, WORK_START, {}, NOW) == datetime(2026, 10, 20, 11, 30)  # 月 6.5h + 火 1.5h


def test_reviewed_end_is_none_when_nothing_remains() -> None:
    assert reviewed_end(task(progress=100), 1.0, 0.5, 6.5, WORK_START, {}, NOW) is None


def test_reviewed_end_is_none_when_the_calculation_fails() -> None:
    assert reviewed_end(task(progress=50), 1.0, 0.5, 0.0, WORK_START, {}, NOW) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_reassign.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.reassign'`)

- [ ] **Step 3: 実装する**

`src/projectapp/reassign.py` を作る。

```python
"""担当の付け替えで換算率が変わったときの、完了予定の見直し(純粋関数。NiceGUI に依存しない)。"""

from datetime import date, datetime, time

from projectapp.models import Status, Task, TaskKind
from projectapp.timeline import calc_end, combine_rate

RATE_TOLERANCE = 1e-9  # 換算率が変わったとみなす差


def consumed_hours(task: Task, old_rate: float) -> float:
    """消化分(基準の人の時間)。進捗度があれば 工数 × 進捗度、なければ 実績の区間の合計時間 × 旧換算率。"""
    if task.effort_hours <= 0:
        return 0.0
    if task.progress:  # None と 0 は、進捗度なし
        done = task.effort_hours * task.progress / 100
    else:
        worked = sum(  # 進行中の区間(終了なし)は数えない
            (a.end - a.start).total_seconds() / 3600 for a in task.actuals if a.end is not None and a.end > a.start
        )
        done = worked * combine_rate(old_rate, 1.0)
    return min(max(done, 0.0), task.effort_hours)


def needs_review(task: Task, old_rate: float, new_rate: float) -> bool:
    """付け替えの保存で、完了予定の見直しを選ばせるか。task は編集後のタスク。"""
    return (
        task.kind is TaskKind.NORMAL
        and task.effort_hours > 0
        and task.status is not Status.DONE
        and bool(task.actuals or (task.progress or 0) >= 1)
        and abs(old_rate - new_rate) > RATE_TOLERANCE
    )


def reviewed_end(
    task: Task,
    old_rate: float,
    new_rate: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    now: datetime,
) -> datetime | None:
    """残りの工数(工数 − 消化分)を新換算率で割り当てた完了予定。残りがない・算出できないときは None。"""
    remaining = task.effort_hours - consumed_hours(task, old_rate)
    if remaining <= 0:
        return None
    start = max(now, task.planned_start) if task.planned_start else now
    return calc_end(start, remaining / combine_rate(new_rate, 1.0), daily_hours, work_start, holidays)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_reassign.py -q && uv run ty check src`
Expected: すべて PASS、`ty` はエラーなし

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/reassign.py test/test_reassign.py docs/superpowers/specs/2026-10-21-reassign-recalc-design.md
git commit -m "feat: 付け替え時の完了予定の見直しの計算(reassign.py)を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 編集ダイアログの確認

**Files:**
- Modify: `src/projectapp/task_dialog.py`(import は 66 行付近、`open_task_dialog` の引数は 825 行付近、`save()` は 1079 行付近、確認ダイアログは 1110 行付近)
- Test: `test/test_task_dialog.py`(`mount_dialog` は 30 行付近)

**Interfaces:**
- Consumes: Task 1 の `needs_review`・`reviewed_end`、既存の `initial_rate`(開いたときの換算率)・`member_list`・`assignees_rate`
- Produces: `open_task_dialog(..., now: Callable[[], datetime] = datetime.now)`。マーカー`reassign-text`・`reassign-apply`・`reassign-skip`・`reassign-back`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` の `mount_dialog` に引数 `now: Callable[[], datetime] | None = None` を足し、`open_task_dialog(...)` の呼び出しへ `now=now or datetime.now,` を足す(`on_decompose=on_decompose,` の下)。ファイル末尾に次を足す。

```python
REASSIGN_NOW = datetime(2026, 10, 14, 10, 0)  # 水曜
FAST = Member("早", 1.0)
SLOW = Member("遅", 0.5)


def reassign_task(**kwargs) -> Task:
    base = dict(
        name="設計", planned_start=datetime(2026, 10, 12, 9, 0), effort_hours=16.0, status=Status.RUNNING,
        progress=50, assignees=[Assignee("早", 1.0)],
    )
    return Task(**{**base, **kwargs})


async def switch_to_slow(user: User, saved: list[Task], task: Task) -> None:
    mount_dialog(task, saved, members=[FAST, SLOW], now=lambda: REASSIGN_NOW)
    await open_dialog(user)
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("遅")
    user.find(marker="task-save").click()


async def test_switching_a_member_with_progress_asks_for_a_review(user: User) -> None:
    saved: list[Task] = []
    await switch_to_slow(user, saved, reassign_task())
    await user.should_see(marker="reassign-text")
    assert saved == []
    assert "2026-10-16 13:00" in user.find(marker="reassign-text").elements.pop().text


async def test_applying_the_review_saves_the_end_as_manual(user: User) -> None:
    saved: list[Task] = []
    await switch_to_slow(user, saved, reassign_task())
    user.find(marker="reassign-apply").click()
    assert len(saved) == 1
    assert saved[0].planned_end == datetime(2026, 10, 16, 13, 0)
    assert saved[0].planned_end_manual is True
    assert saved[0].effort_hours == 16.0
    assert saved[0].progress == 50
    assert saved[0].assignees == [Assignee("遅", 1.0)]


async def test_skipping_the_review_saves_without_touching_the_end(user: User) -> None:
    saved: list[Task] = []
    await switch_to_slow(user, saved, reassign_task())
    user.find(marker="reassign-skip").click()
    assert len(saved) == 1
    assert saved[0].planned_end is None
    assert saved[0].planned_end_manual is False
    assert saved[0].assignees == [Assignee("遅", 1.0)]


async def test_going_back_keeps_the_dialog_open_and_saves_nothing(user: User) -> None:
    saved: list[Task] = []
    await switch_to_slow(user, saved, reassign_task())
    user.find(marker="reassign-back").click()
    assert saved == []
    await user.should_see(marker="task-save")


async def test_changing_only_the_allocation_also_asks(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(reassign_task(), saved, members=[FAST, SLOW], now=lambda: REASSIGN_NOW)
    await open_dialog(user)
    with user.client:
        user.find(marker="task-allocation").elements.pop().set_value(50)
    user.find(marker="task-save").click()
    await user.should_see(marker="reassign-text")


async def test_a_task_without_records_is_saved_without_asking(user: User) -> None:
    saved: list[Task] = []
    await switch_to_slow(user, saved, reassign_task(progress=None))
    assert len(saved) == 1


async def test_an_unchanged_rate_is_saved_without_asking(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(reassign_task(), saved, members=[FAST, SLOW], now=lambda: REASSIGN_NOW)
    await open_dialog(user)
    user.find(marker="task-name").type("改")
    user.find(marker="task-save").click()
    assert len(saved) == 1


async def test_a_finished_progress_is_saved_without_asking(user: User) -> None:
    saved: list[Task] = []
    await switch_to_slow(user, saved, reassign_task(progress=100))
    assert len(saved) == 1


async def test_a_new_task_is_saved_without_asking(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[FAST, SLOW], now=lambda: REASSIGN_NOW)
    await open_dialog(user)
    user.find(marker="task-name").type("新規")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("遅")
    user.find(marker="task-save").click()
    assert len(saved) == 1
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -k "review or asking or without_asking or going_back"`
Expected: FAIL(`open_task_dialog() got an unexpected keyword argument 'now'`)

- [ ] **Step 3: 実装する**

`task_dialog.py` の import を足す(`from projectapp.ratios import effective_ratio` の下)。

```python
from projectapp.reassign import needs_review, reviewed_end
```

`open_task_dialog` の引数に、`on_decompose` の下へ足す。

```python
    now: Callable[[], datetime] = datetime.now,
```

`save()` の中の `on_save(result)` / `dialog.close()`(`except ValueError` の直後の 2 行)を、次に置き換える。

```python
            new_rate = assignees_rate(result.assignees, member_list)
            new_end = (
                reviewed_end(result, initial_rate, new_rate, daily_hours, work_start, holidays or {}, now())
                if task is not None and needs_review(result, initial_rate, new_rate)
                else None
            )
            if new_end is None:
                on_save(result)
                dialog.close()
                return
            pending["task"], pending["end"] = result, new_end
            review_text.set_text(
                f"担当の付け替えで、換算率が {initial_rate:.2f} → {new_rate:.2f} に変わります。\n"
                f"残りの作業を新しい担当で見直すと、完了予定は {new_end:%Y-%m-%d %H:%M} です。"
            )
            review.open()
```

`save()` の定義より前(`opened = current()` の下)に、状態とダイアログを足す。

```python
        pending: dict[str, object] = {}  # 確認待ちの保存内容(task)と、見直した完了予定(end)

        def finish(apply: bool) -> None:
            review.close()
            result = pending["task"]
            assert isinstance(result, Task)
            if apply:
                end = pending["end"]
                assert isinstance(end, datetime)
                result.planned_end = end
                result.planned_end_manual = True
            on_save(result)
            dialog.close()

        with ui.dialog() as review, ui.card():
            review_text = ui.label("").classes("whitespace-pre-line").mark("reassign-text")
            with ui.row():
                ui.button("見直す", on_click=lambda: finish(True)).mark("reassign-apply")
                ui.button("見直さない", on_click=lambda: finish(False)).props("flat").mark("reassign-skip")
                ui.button("編集に戻る", on_click=lambda: review.close()).props("flat").mark("reassign-back")
```

(既存の確認ダイアログ `with ui.dialog() as confirm, ui.card():` と同じく、`save` と同じ関数スコープに置く。`finish` は`review`を実行時に参照するので、定義順はこのままでよい。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py test/test_reassign.py -q && uv run ty check src`
Expected: すべて PASS。既存の保存のテストも通る

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "feat: 担当の付け替えで換算率が変わるとき、完了予定の見直しを選べるようにする(要望32)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 仕様・構成・状態の反映と全体の確認

**Files:**
- Modify: `CLAUDE.md`(「ガントチャート」の節。タスクの分解の項の前後)
- Modify: `docs/development.md`(モジュール表。`ratios.py` の行の下)
- Modify: `docs/requests.md`(要望 32 の見出し付近)・`docs/request-history.md`(13・14・51・95 行付近)
- Modify: `.claude/MEMORY.md`(要望 32 の項と「現在の状況」)

**Interfaces:**
- Consumes: Task 1・2 の実装
- Produces: なし

- [ ] **Step 1: `CLAUDE.md` に仕様を足す**

「タスクの分解:」の項の直前に、次の項を足す。

```markdown
- 担当の付け替えと完了予定の見直し: 既存のタスクの編集で、担当の追加・削除・入れ替えや割り当て率の変更により換算率が変わり、通常タスクで、工数があり、状態が`終了`でなく、実績か進捗度(1% 以上)があるとき、保存の前に確認を出す(`見直す`・`見直さない`・`編集に戻る`)。`見直す`は、完了予定を`max(今, 開始予定)`から`(工数 − 消化分) ÷ 新しい換算率`を稼働可能時間・始業時刻・祝日に割り当てた日時にして、手で指定の完了予定として保存する(設定を変えても追従しない)。消化分は、進捗度があれば`工数 × 進捗度`、なければ実績の区間(終了のあるもの)の合計時間 × 旧換算率(工数を超えない)。工数・実績・進捗度は変えない。残りがない(進捗度 100% など)ときは確認を出さない。新規追加では出さない
```

- [ ] **Step 2: `docs/development.md` のモジュール表に足す**

`ratios.py` の行の下に足す。

```markdown
| `reassign.py` | 担当の付け替えで換算率が変わったときの、完了予定の見直し。`consumed_hours`(消化分)・`needs_review`(確認を出すか)・`reviewed_end`(残りを新換算率で割り当てた完了予定)。純粋関数。編集ダイアログの`save()`が使う |
```

- [ ] **Step 3: `docs/requests.md`・`docs/request-history.md` を更新する**

`docs/requests.md` の要望 32 の見出しの下に、状態と決定を足す。

```markdown
> **状態**: 実装済み(2026-10-21)。設計書 `2026-10-21-reassign-recalc-design.md`、実装計画 `2026-10-21-reassign-recalc.md`。決定: 完了予定だけを見直す(工数は書き換えない)/ 手で指定の完了予定として保存 / 進捗度を優先し、なければ実績の時間 × 旧換算率 / 換算率が変わる保存すべてで出す。
```

`docs/request-history.md` は、13・14 行の件数表で 32 を「完了」の行へ移し(未着手は`5・24・30・31・35`)、51 行の状態を`完了`・日付・設計書の欄で更新し、95 行の「決めたい点」の 32 の行を削除する。形式は隣の完了行(33)に合わせる。

- [ ] **Step 4: 全体を確認する**

Run: `uv run pytest -n auto -q 2>&1 | tail -5 && uv run ty check src`
Expected: すべて PASS(3,152 件 + 新規)、`ty` はエラーなし

- [ ] **Step 5: `.claude/MEMORY.md` を更新してコミットする**

要望 32 の項(168 行付近)を`(実装済み・実機確認待ち)`に直して要点を足し、「現在の状況」の先頭行を`feature/reassign-recalc`に更新する。

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "docs: 付け替え時の完了予定の見直し(要望32)を仕様と記録に反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **設計書との対応**: 消化分・要否・見直しの式 → Task 1。確認ダイアログ・手指定での保存・新規追加の除外・元に戻す 1 ステップ → Task 2。仕様・記録 → Task 3。
- **型の一貫性**: `consumed_hours(task, old_rate)`・`needs_review(task, old_rate, new_rate)`・`reviewed_end(task, old_rate, new_rate, daily_hours, work_start, holidays, now)` は Task 1 の定義と Task 2 の呼び出しで一致。マーカー名は Task 2 の実装とテストで一致。
- **Review Focus**: 進行中の区間(Task 1 `test_consumed_ignores_a_running_interval_and_zero_progress`)、進捗度 100%(Task 1・2)、開始予定が先(Task 1)、除外条件(Task 1 のパラメータ化)、割り当て率だけの変更と換算率不変(Task 2)。
- **注意**: `test_task_dialog.py` の既存テストが`datetime.now`に依存しないことは、Task 2 Step 4 の全件実行で確かめる。`task-assignee` の選択肢は、既存テストと同じく先頭の行を使う。
