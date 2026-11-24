# アサイン専用画面 段階 4b(週ごとの消化の見通し)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面の割り当ての行の下に、週ごとの`消化 12.0h / 残り 28.0h`を並べ、残りの工数がどの週に減り、どの週で終わるかを、割り当てを変えるたびに見られるようにする。

**Architecture:** 計算と文言は、4a の`shortage.py`に足す純粋関数(`weekly_burn`・`burn_text`・`burn_hint`)。稼働量は`work_capacity`を週の範囲ごとに呼んで数える(4a・`pace.py`と同じ数え方)。画面は、`AssignScreen.assign_row`(チャートの`task_extra`)の末尾で`burn_row`を描く。チャートの再描画(`refresh`→`set_project`)のたびに描き直されるので、別の更新の経路は要らない。ファイル形式は変えない。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-24-assign-screen-stage4b-design.md`(4a は`2026-11-22-assign-screen-stage4a-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。表示は試算に含めず、`is_dirty`は変えない
- 稼働量の数え方は 4a・`pace.py`と同じ(`work_capacity`。週ごと・日ごとの担当・休み・祝日・稼働日の上書きを反映。始点は`max(now, 実効の開始)`)
- 週ごとの消化は、残りの工数を超えない。完了する週より後の週は`—`
- 基準日がなくても出す。基準日に関する理由は使わない
- 時間は小数 1 桁。マーカーは`assign-`で始める(`assign-burn-{週}`・行は`assign-burn-row`)。メインのチャート・ダッシュボードの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは`feature/request-168-stage4b`のまま実装する。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差・補足)

- 短い表記への切り替えは、「日ごとの週か」ではなく、**週の幅(px)が 120 未満か**で決める。日ごとの週も、ラベルは週ぜんたいで 1 つ出すので幅は同じで、狭くなるのは月次表示などのときだから。設計書の該当の 1 文は Task 3 で直す
- 4a の理由の判定のうち、タスクの種類・終了・工数の 3 つは、`_unfit`として取り出し、`task_shortage`と`weekly_burn`で共有する(順序は変えない)
- 画面の`burn_row`は、`assign_row`の末尾から呼ぶ(`task_extra`は 1 タスクにつき 1 回の呼び出しで、要素を複数置ける)。`plan`が`None`(開始日がない)のときは、`assign_row`が先に戻るので行は出ない
- `WeekBurn.last`は常に週の末(過ぎた週は`first == last`)。`WeekBurn.before`(週の初めの残り)を持つ。`done`は`before > 0 and left <= 0`

## Review Focus

- 割り当てを足す・率を下げると、消化と完了する週が動く(元のプロジェクトは変わらない)
- 今が週の途中・すでに過ぎた週・開始が未来の週で、消化が 0 や途中からになる
- 完了する週より後は`—`で、数字が負・残りが負にならない
- 基準日(締切・完了予定)がなくても行が出る
- 開始日がない・工数がない・終了したタスクでは、行を出さず、落ちない
- 担当者がいない週(稼働量 0 でなく換算率 1 の 1 人として数える)でも落ちない
- 週が多い(52 週)ときも遅くならない

---

### Task 1: `weekly_burn`・文言(`shortage.py`)

**Files:**
- Modify: `src/projectapp/shortage.py`
- Test: `test/test_shortage.py`

**Interfaces:**
- Consumes: `task_shortage`と同じ部品(`remaining_hours`・`total_effort`・`Schedule`・`effective_start`・`crew_of`・`weekly_crews`・`work_capacity`)
- Produces:
  - `@dataclass(frozen=True) WeekBurn(week: int, first: datetime, last: datetime, before: float, burn: float, left: float)` とプロパティ`done: bool`
    - `first`は`max(今, 開始, 週の頭)`を週の末で切った値、`last`は週の末。範囲が空(過ぎた週)のときは`first == last`
    - `before`は週の初めの残り、`burn`はその週の消化、`left`は週の終わりの残り(`before - burn`。0 以上)
  - `weekly_burn(task: Task, project: Project, holidays: dict[date, str], now: datetime, weeks: int, origin: date, schedule: Schedule | None = None) -> list[WeekBurn] | str`(長さは`weeks`。出せないときは理由の文字列)
  - `burn_text(value: WeekBurn, narrow: bool = False) -> str`
  - `burn_hint(value: WeekBurn) -> str`

- [ ] **Step 1: Write the failing tests**

`test/test_shortage.py`の import に`WeekBurn`・`burn_hint`・`burn_text`・`weekly_burn`を足し、末尾に追記する。既存の`MON`・`project_of`・`task_of`を使う(`MON` = 2026-10-05 月 9:00、稼働の枠は 6.5h、月〜金で 32.5h/週、工数 40h、担当は田中 100%)。

```python
from datetime import timedelta

ORIGIN = date(2026, 10, 5)


def burns(task: Task, now: datetime = MON, weeks: int = 3, holidays=None):
    return weekly_burn(task, project_of(task), holidays or {}, now, weeks, ORIGIN)


def test_the_burn_runs_out_in_the_second_week() -> None:
    value = burns(task_of(deadline=None))
    assert isinstance(value, list) and len(value) == 3
    first, second, third = value
    assert (first.before, first.burn, first.left) == pytest.approx((40.0, 32.5, 7.5))
    assert (second.before, second.burn, second.left) == pytest.approx((7.5, 7.5, 0.0))
    assert second.done and not first.done
    assert (third.before, third.burn, third.left) == (0.0, 0.0, 0.0)
    assert not third.done


def test_the_ranges_are_whole_weeks_from_the_origin() -> None:
    value = burns(task_of(deadline=None))
    assert isinstance(value, list)
    assert value[0].first == MON and value[0].last == datetime(2026, 10, 12)
    assert value[1].first == datetime(2026, 10, 12) and value[1].last == datetime(
        2026, 10, 19
    )


def test_a_lower_rate_stretches_the_burn_over_three_weeks() -> None:
    value = burns(task_of(deadline=None, assignees=[Assignee("田中", 0.5)]))
    assert isinstance(value, list)
    assert [round(w.burn, 2) for w in value] == [16.25, 16.25, 7.5]
    assert [w.done for w in value] == [False, False, True]


def test_the_first_week_counts_from_now_when_now_is_mid_week() -> None:
    value = burns(task_of(deadline=None), now=datetime(2026, 10, 7, 9))  # 水〜金の 3 日
    assert isinstance(value, list)
    assert value[0].first == datetime(2026, 10, 7, 9)
    assert value[0].burn == pytest.approx(19.5) and value[0].left == pytest.approx(20.5)


def test_a_week_already_past_burns_nothing() -> None:
    value = burns(task_of(deadline=None), now=datetime(2026, 10, 14, 9))  # 第 2 週の水
    assert isinstance(value, list)
    assert value[0].burn == 0.0 and value[0].left == pytest.approx(40.0)
    assert value[0].first == value[0].last
    assert value[1].burn == pytest.approx(19.5)


def test_a_start_in_the_future_starts_the_count_there() -> None:
    task = task_of(deadline=None, planned_start=datetime(2026, 10, 7, 9))
    value = weekly_burn(task, project_of(task), {}, MON, 3, date(2026, 10, 7))
    assert isinstance(value, list)
    assert value[0].first == datetime(2026, 10, 7, 9)  # 今ではなく開始から


def test_a_holiday_lowers_that_weeks_burn() -> None:
    value = burns(task_of(deadline=None), holidays={date(2026, 10, 7): "祝"})
    assert isinstance(value, list)
    assert value[0].burn == pytest.approx(26.0)


def test_weekly_crews_change_the_burn_week_by_week() -> None:
    task = task_of(
        deadline=None,
        weekly_crew=[[Assignee("田中", 0.5)], [Assignee("田中")]],
    )
    value = burns(task)
    assert isinstance(value, list)
    assert [round(w.burn, 2) for w in value] == [16.25, 23.75, 0.0]
    assert value[1].done


def test_a_daily_week_counts_each_day_with_its_own_crew() -> None:
    half = [Assignee("田中", 0.5)]
    task = task_of(
        deadline=None,
        weekly_crew=[[Assignee("田中")], [Assignee("田中")]],
        daily_crew={0: [half] * 7},
    )
    value = burns(task)
    assert isinstance(value, list)
    assert value[0].burn == pytest.approx(16.25)


def test_a_crew_without_anyone_counts_as_one_person() -> None:
    value = burns(task_of(deadline=None, assignees=[]))
    assert isinstance(value, list)
    assert value[0].burn == pytest.approx(32.5)


def test_progress_lowers_the_remaining_before_the_first_week() -> None:
    value = burns(task_of(deadline=None, progress=50))
    assert isinstance(value, list)
    assert value[0].before == pytest.approx(20.0)
    assert value[0].done  # 20h は第 1 週の稼働量 32.5h に収まる


def test_no_deadline_is_needed() -> None:
    assert isinstance(burns(task_of(deadline=None, planned_end=None)), list)


def test_the_total_burn_equals_the_capacity_to_the_due() -> None:
    task = task_of(effort_hours=100.0, deadline=datetime(2026, 10, 23, 17))  # 3 週
    short = judged(task)
    value = burns(task)
    assert isinstance(short, Shortage) and isinstance(value, list)
    assert sum(w.burn for w in value) == pytest.approx(short.capacity, abs=6.5 * 2)
    # 最終週の金曜 17:00 は枠の外(15:30 まで)なので、枠の終わりまでの 3 週の稼働量と一致する
    assert sum(w.burn for w in value) == pytest.approx(97.5)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        (task_of(kind=TaskKind.CHECKPOINT), "通常のタスクではありません"),
        (task_of(status=Status.DONE), "終了したタスクです"),
        (task_of(effort_hours=None), "工数がありません"),
        (task_of(planned_start=None), "開始日がありません"),
        (task_of(progress=100), "残りの工数がありません"),
    ],
)
def test_burn_reasons(task: Task, reason: str) -> None:
    assert burns(task) == reason


def test_many_weeks_are_cheap() -> None:
    value = burns(task_of(deadline=None, effort_hours=4000.0), weeks=52)
    assert isinstance(value, list) and len(value) == 52


def test_burn_text_shapes() -> None:
    first = WeekBurn(0, MON, datetime(2026, 10, 12), 40.0, 32.5, 7.5)
    last = WeekBurn(1, datetime(2026, 10, 12), datetime(2026, 10, 19), 7.5, 7.5, 0.0)
    after = WeekBurn(2, datetime(2026, 10, 19), datetime(2026, 10, 26), 0.0, 0.0, 0.0)
    assert burn_text(first) == "消化 32.5h / 残り 7.5h"
    assert burn_text(last) == "消化 7.5h / 完了"
    assert burn_text(after) == "—"
    assert burn_text(first, narrow=True) == "32.5h→7.5h"
    assert burn_text(last, narrow=True) == "7.5h 完了"
    assert burn_text(after, narrow=True) == "—"


def test_burn_hint_names_the_week_and_the_change() -> None:
    first = WeekBurn(0, MON, datetime(2026, 10, 12), 40.0, 32.5, 7.5)
    assert burn_hint(first) == "10/05〜10/11 の稼働 32.5h。残り 40.0h → 7.5h"
```

注意: `task_of`の`kind`・`status`・`progress`は`Task`のフィールド名。`TaskKind.CHECKPOINT`などの名前が違えば、`models.py`で確かめて合わせる(`effort_hours=None`・`planned_start=None`・`progress=100`は 4a のテストと同じ書き方)。`test_the_total_burn_equals_the_capacity_to_the_due`の最初の`assert`は緩い確認なので、2 つ目の厳密な`assert`だけを残してよい。

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_shortage.py -q`
Expected: FAIL(`ImportError: cannot import name 'weekly_burn'`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/shortage.py`の import を直す:

```python
from datetime import date, datetime, time, timedelta
```

`task_shortage`の先頭の 3 つの判定を、共有の`_unfit`に取り出す(順序は同じ)。`task_shortage`の中の

```python
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクではありません"
    if task.status is Status.DONE:
        return "終了したタスクです"
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return "工数がありません"
```

を、次に置き換える:

```python
    reason = _unfit(task)
    if reason is not None:
        return reason
```

そして`due_of`の上に、次を足す:

```python
def _unfit(task: Task) -> str | None:
    """不足・消化の見通しを出せないタスクの理由。通常のタスクで、終了しておらず、工数があれば None。"""
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクではありません"
    if task.status is Status.DONE:
        return "終了したタスクです"
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return "工数がありません"
    return None
```

`task_shortage`のあとに、次を足す:

```python
@dataclass(frozen=True)
class WeekBurn:
    week: int  # 週の番号(0 始まり。`CellPlan`と同じ)
    first: datetime  # その週の数える範囲 [first, last)。過ぎた週・範囲が空の週は first == last
    last: datetime
    before: float  # 週の初めの残りの工数[h]
    burn: float  # その週に消化できる工数[h](換算率つき。残りを超えない)
    left: float  # 週の終わりの残りの工数[h](0 以上)

    @property
    def done(self) -> bool:
        """この週で残りが 0 になったか。"""
        return self.before > 0 and self.left <= 0


def weekly_burn(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    weeks: int,
    origin: date,
    schedule: Schedule | None = None,
) -> list[WeekBurn] | str:
    """週ごとの消化の見通し(要望 168 段階 4b)。週 w は [origin + 7w 日, origin + 7(w+1) 日)。
    出せないときは、その理由の文字列を返す。基準日は要らない。"""
    reason = _unfit(task)
    if reason is not None:
        return reason
    schedule = schedule or Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return "開始日がありません"
    rest = remaining_hours(task, project, holidays, now)
    if not rest > 0:
        return "残りの工数がありません"
    counted_from = max(now, start)
    crew = crew_of(
        task.assignees,
        project.members,
        project.parameters,
        task.parameters,
        project.ratio_limits,
    )
    track = weekly_crews(task, project) or None
    result: list[WeekBurn] = []
    left = rest
    for week in range(weeks):
        head = datetime.combine(origin + timedelta(days=7 * week), time.min)
        tail = head + timedelta(days=7)
        first = min(max(head, counted_from), tail)
        capacity = (
            work_capacity(
                first,
                tail,
                project.daily_hours,
                project.work_start,
                holidays,
                crew=crew,
                weeks=track,
                weeks_start=origin,
            )
            if first < tail
            else 0.0
        )
        before = left
        burn = min(capacity, before)
        left = before - burn
        result.append(WeekBurn(week, first, tail, before, burn, left))
    return result


def burn_text(value: WeekBurn, narrow: bool = False) -> str:
    """`消化 12.0h / 残り 28.0h`・`消化 6.0h / 完了`・`—`(完了したあとの週)。狭いときは`12.0h→28.0h`・`6.0h 完了`。"""
    if value.before <= 0:
        return "—"
    if value.done:
        return f"{value.burn:.1f}h 完了" if narrow else f"消化 {value.burn:.1f}h / 完了"
    if narrow:
        return f"{value.burn:.1f}h→{value.left:.1f}h"
    return f"消化 {value.burn:.1f}h / 残り {value.left:.1f}h"


def burn_hint(value: WeekBurn) -> str:
    """ホバーの文字。`10/05〜10/11 の稼働 32.5h。残り 40.0h → 7.5h`。期間は週の頭から末日まで。"""
    head = value.last - timedelta(days=7)
    last_day = value.last - timedelta(days=1)
    return (
        f"{head:%m/%d}〜{last_day:%m/%d} の稼働 {value.burn:.1f}h。"
        f"残り {value.before:.1f}h → {value.left:.1f}h"
    )
```

注意: `WeekBurn.last`は常に週の末(`tail`)で、`burn_hint`が期間をそこから出す。`first`は`min(max(週の頭, 今と開始の遅いほう), tail)`なので、過ぎた週では`first == last`になる(`test_a_week_already_past_burns_nothing`が確かめる)。

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest test/test_shortage.py -q`
Expected: PASS(4a の既存のテストも通る)

- [ ] **Step 5: Commit**

```bash
uvx ruff format src test && uvx ruff check
git add src/projectapp/shortage.py test/test_shortage.py
git commit -m "feat: 週ごとの消化の見通し weekly_burn を足す(要望 168 段階 4b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 画面の`burn_row`(`assign_screen.py`)

**Files:**
- Modify: `src/projectapp/assign_screen.py`(import の`shortage`の行・`assign_row`の末尾・新しい`burn_row`)
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`weekly_burn`・`burn_text`・`burn_hint`、既存の`self.edges`・`self.plan`・`self.trial`・`self.project`・`self.holidays`・`self.now()`・`trial_project`・`from_name`
- Produces: マーカー`assign-burn-row`(行)・`assign-burn-{週}`(各週のラベル。`title`にヒント)

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`の末尾に追記する(`team_project`は、11/16 月開始・工数 40h・田中 100%。週 0 の稼働量は 32.5h):

```python
async def test_the_burn_row_shows_each_weeks_burn(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see(marker="assign-burn-row")
    assert label_text(user, "assign-burn-0") == "消化 32.5h / 残り 7.5h"
    assert label_text(user, "assign-burn-1") == "消化 7.5h / 完了"
    assert label_text(user, "assign-burn-2") == "—"


async def test_the_burn_row_follows_the_assignment(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.drop_member("鈴木", 0, None)  # 週 0 だけ 2 人(65h)
    await user.should_see("消化 40.0h / 完了")
    assert label_text(user, "assign-burn-0") == "消化 40.0h / 完了"
    assert label_text(user, "assign-burn-1") == "—"


async def test_the_burn_row_needs_no_deadline(user: User) -> None:
    screen, _ = await open_team_screen(user)
    assert screen.trial.task.deadline is None
    await user.should_see(marker="assign-burn-0")


async def test_the_burn_hint_names_the_week(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see(marker="assign-burn-0")
    label = user.find(marker="assign-burn-0").elements.pop()
    assert "11/16〜11/22 の稼働 32.5h" in str(label.props.get("title", ""))


async def test_the_burn_row_is_not_drawn_without_a_start_date(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.planned_start = None
    screen.refresh()
    await user.should_not_see(marker="assign-burn-row")


async def test_the_burn_row_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    assert not is_dirty(screen.trial)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_assign_screen.py -q -k burn`
Expected: FAIL(`assign-burn-row`が見つからない)

- [ ] **Step 3: Write the implementation**

`assign_screen.py`の import を直す:

```python
from projectapp.shortage import (
    burn_hint,
    burn_text,
    shortage_hint,
    shortage_text,
    task_shortage,
    weekly_burn,
)
```

定数を、`LINE_STEP_PX`の下に足す:

```python
BURN_ROW_PX = 18  # 消化の行の高さ
BURN_NARROW_PX = 120  # 週の幅がこれ未満なら、短い表記にする
```

`assign_row`の末尾(`if task.weekly_crew or task.assignees:`のブロックの後。`with row:`の外、関数のインデントの階層)に、次を足す:

```python
        self.burn_row(weeks, columns, width)
```

`no_start_row`の上に、`burn_row`を足す:

```python
    def burn_row(self, weeks: int, columns: list[Column], width: int) -> None:
        """割り当ての行の下に、週ごとの消化と残りを並べる(要望 168 段階 4b)。出せないときは何も出さない(理由は不足の行が言う)。"""
        if self.plan is None:
            return
        value = weekly_burn(
            self.trial.task,
            trial_project(self.project, self.trial),
            self.holidays,
            self.now(),
            weeks,
            self.plan.origin,
        )
        if isinstance(value, str):
            return
        with (
            ui.element("div")
            .style(f"height: {BURN_ROW_PX}px; position: relative; width: 100%")
            .mark("assign-burn-row")
        ):
            for item in value:
                first = self.plan.origin + timedelta(days=WEEK_DAYS * item.week)
                left, span = self.edges(
                    first, first + timedelta(days=WEEK_DAYS - 1), columns, width
                )
                narrow = span < BURN_NARROW_PX
                ui.label(burn_text(item, narrow)).classes("text-caption").style(
                    f"position: absolute; left: {from_name(left)};"
                    f" width: {max(span - 2, 0):.0f}px; top: 0; text-align: center;"
                    " overflow: hidden; white-space: nowrap; text-overflow: ellipsis;"
                    f" opacity: {0.5 if item.before <= 0 else 1}"
                ).props(f'title="{burn_hint(item)}"').mark(f"assign-burn-{item.week}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py -q`
Expected: PASS(既存のテストも通る)。もし`assign-burn-2`が出ないなど週の数が合わないときは、`assign_row`の`weeks`(`max(self.plan.weeks, len(task.weekly_crew))`)を渡していることを確かめる

- [ ] **Step 5: 画面を実機で確かめる**

Run: `uv run projectapp`(確認用データは`docs/samples`か`~/.projectapp`。消してよい範囲はメモリ`reference-projectapp-sample-data`)で、ダッシュボードの右クリックから`アサイン...`を開き、次を見る。
- 週のセルの下に、週ごとの消化の行が出る。メンバーを足す・率を下げると数字が動く
- 日次・週次・月次の切り替えで、幅が狭いと短い表記になる
- 縦のスクロール・横スクロールの連動と、負荷のヒストグラム・不足の行が崩れない

結果は報告に書く(利用者の実機確認はマージ前)。

- [ ] **Step 6: Commit**

```bash
uvx ruff format src test && uvx ruff check
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン画面に週ごとの消化の行を出す(要望 168 段階 4b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 仕様・設計書・要望の文書

**Files:**
- Modify: `.claude/spec/gantt.md`か、アサイン画面の記述がある`.claude/spec/`のファイル(`grep -ln "不足" .claude/spec/*.md`で、4a の記述がある所を探す)
- Modify: `docs/development.md`(`shortage.py`の行に`weekly_burn`を足す)
- Modify: `docs/requests.md`(要望 168 の`### 状態`に、4b の実装済みを足す)
- Modify: `docs/superpowers/specs/2026-11-24-assign-screen-stage4b-design.md`(狭い表記の切り替え)

- [ ] **Step 1: 設計書を直す**

設計書の「日ごとにした週は、幅が狭いので、`12.0h→28.0h`の短い形にする(幅で切り替える。`lines_for`と同じ考え方)」を、次に置き換える:

「ラベルは週ぜんたいで 1 つなので、日ごとの週も幅は同じ。週の幅が 120px 未満(月次表示など)のときに、`12.0h→28.0h`・`6.0h 完了`の短い形にする。」

- [ ] **Step 2: 仕様を書く**

4a の不足の記述の下に、次の趣旨を足す(既存の文体に合わせる): アサイン画面の割り当ての行の下に、週ごとに`消化 X h / 残り Y h`を出す。消化はその週の担当(週ごと・日ごとを含む)の稼働量で、残りの工数を超えない。完了する週は`完了`、その後は`—`。基準日は要らない。狭いときは短い表記。試算に含めず、保存しない。

- [ ] **Step 3: 構成と要望を直す**

`docs/development.md`の`shortage.py`の説明に`weekly_burn`(週ごとの消化)を足す。`docs/requests.md`の要望 168 の`### 状態`の末尾の「段階 4b(週ごとの消化の見通し)・4c(逆算)・4d(試算の前後の比較)は未着手。」を、「段階 4b(週ごとの消化の見通し)は実装済み(設計書: `docs/superpowers/specs/2026-11-24-assign-screen-stage4b-design.md`・計画: `docs/superpowers/plans/2026-11-24-assign-screen-stage4b.md`。実機確認待ち)。段階 4c(逆算)・4d(試算の前後の比較)は未着手。」に直す。

- [ ] **Step 4: 全体の確認**

Run: `uv run pytest -m smoke`
Expected: PASS(失敗したときに限り`uv run pytest -n auto`。`test_300_tasks…`の速度テストは並列の負荷で揺れる)

Run: `uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: ruff は問題なし。ty は既存の 9 件のみ

- [ ] **Step 5: Commit と PR**

```bash
git add .claude/spec docs
git commit -m "docs: アサイン画面の週ごとの消化の見通し(段階 4b)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/request-168-stage4b
gh pr create --base develop --title "feat: アサイン画面の週ごとの消化の見通し(要望 168 段階 4b)" --body "設計書: docs/superpowers/specs/2026-11-24-assign-screen-stage4b-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR を作ったところで止まる(マージは利用者の指示を待つ)。
