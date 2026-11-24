# アサイン専用画面 段階 4c(必要な割り当て率の逆算)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面のヘッダーに、基準日に間に合わせるのに要る割り当て率を、`必要な率: 今の ×1.7(鈴木 50→85%・田中 100%)`の形で出す。全員 100% でも足りないときは、足りない時間と人数を出す。

**Architecture:** 計算と文言は、4a・4b の`shortage.py`に足す純粋関数(`required_rate`・`required_rate_text`・`required_rate_hint`)。担当の率(タスク全体・週ごと・日ごと)を k 倍して各人 100% で頭打ちにした複製のタスクで、4a と同じ`work_capacity`を数え、残りの工数に届く最小の k を二分法で求める。画面は、ヘッダーの不足の行の下に 1 行足し、`render_shortage`と同じ流れで更新する。ファイル形式は変えない。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-24-assign-screen-stage4c-design.md`(4a は`2026-11-22-assign-screen-stage4a-design.md`、4b は`2026-11-24-assign-screen-stage4b-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。表示は試算に含めず、`is_dirty`は変えない。元のタスクの率は書き換えない(複製で数える)
- 稼働量の数え方は 4a と同じ(`work_capacity`。始点は`max(now, 実効の開始)`、終点は基準日)
- 不足のときだけ出す。余裕・ちょうど・出せない理由では行ごと隠す(理由は不足の行に出る)
- 率の上限は`MAX_ALLOCATION`(100%)。不足のときは k > 1 なので、下限(`MIN_ALLOCATION`)は割らない
- マーカーは`assign-`で始める(`assign-required-rate`)。メインのチャート・ダッシュボードの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは`feature/request-168-stage4c`。PR の base は`develop`。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差・補足)

- 設計書の「確かめること」の結果: ①率を k 倍した複製は、`dataclasses.replace`で`assignees`・`weekly_crew`・`daily_crew`を作り直せば足りる(`assign_trial`の関数は使わない。`set_allocation_all`は 1 人ずつの変更用)。②`weekly_crews(task, project)`は`weekly_crew`と`daily_crew`から作るので、複製で同じ k が効く。③`work_capacity`は 1 タスクの範囲を日ごとに数えるだけで、二分法 50 回でも軽い(Task 1 のテストで 52 週・50 回を実測する)
- 倍率の頭打ち: k の上限は`1 ÷ (どの週・日にもある最も低い率)`。それ以上は全員 100% で同じ稼働量になる
- 人ごとの「今の率」は、その人がいるすべての担当(全体・週・日)の最大の率。「必要な率」は`min(1.0, 今の率 × k)`
- 文言の丸めは切り上げ(`ceil`)。表示が足りない側にずれないようにする(倍率は小数 1 桁、率は整数%)
- `task_shortage`の稼働量の部分を`_capacity_of`として取り出し、`required_rate`と共有する(挙動は変えない。Task 1 の Step 1 で既存テストが通ることを確かめる)
- 設計書に、`RequiredRate.shortage`(4a の`Shortage`。ヒストの元)を持たせると書いていないので、Task 3 で設計書を直す

## Review Focus

- 率が 100% 未満の人だけで届く場合と、100% で頭打ちになる人が混ざる場合で、倍率と人ごとの率が合う
- 全員 100% でも届かないとき、倍率を出さず、足りない時間と人数が出る
- 週ごと・日ごとの担当で、倍率が全週・全日にかかる(人ごとの率は最大)
- 余裕・ちょうど・基準日なし・基準日を過ぎた・開始日なしでは、落ちず、行が隠れる
- 試算の元(`task`)の率を書き換えない
- 週が多い(52 週)・率が低い(1%)ときも遅くならない

---

### Task 1: `required_rate`・文言(`shortage.py`)

**Files:**
- Modify: `src/projectapp/shortage.py`
- Test: `test/test_shortage.py`

**Interfaces:**
- Consumes: `task_shortage`・`Shortage`・`shortage_hint`・`Schedule`・`effective_start`・`crew_of`・`weekly_crews`・`work_capacity`(いずれも`shortage.py`内かその import)
- Produces:
  - `@dataclass(frozen=True) RequiredRate(factor: float | None, members: tuple[tuple[str, float, float], ...], short_hours: float, short_people: float | None, shortage: Shortage)`
    - `factor`: 倍率 k。全員 100% でも届かないときは None
    - `members`: 人ごとの (名前, 今の率, 必要な率)。率は 0〜1。届かないときは空
    - `short_hours`・`short_people`: 届かないときの、足りない時間と 100% の人への換算人数(届くときは 0.0・None)
  - `required_rate(task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule | None = None) -> RequiredRate | str`(不足でないとき・出せないときは理由の文字列。不足でないときは`不足していません`)
  - `required_rate_text(value: RequiredRate) -> str`
  - `required_rate_hint(value: RequiredRate) -> str`

- [ ] **Step 1: 既存の挙動を固定してから、稼働量の部分を取り出す**

`src/projectapp/shortage.py`の`task_shortage`の中の、`capacity = work_capacity(...)`と`unit = work_capacity(...)`を、次の関数に取り出す(挙動は変えない)。

```python
def _capacity_of(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    origin: datetime,
    due_at: datetime,
    start: datetime,
) -> float:
    """今から基準日までに、このタスクの担当で積める稼働量[h](換算率つき)。`task_shortage`と`required_rate`で共有する。"""
    return work_capacity(
        origin,
        due_at,
        project.daily_hours,
        project.work_start,
        holidays,
        crew=crew_of(
            task.assignees,
            project.members,
            project.parameters,
            task.parameters,
            project.ratio_limits,
        ),
        weeks=weekly_crews(task, project) or None,
        weeks_start=start.date(),
    )
```

`task_shortage`の該当部分は次にする。

```python
    capacity = _capacity_of(task, project, holidays, origin, due_at, start)
    unit = work_capacity(
        origin, due_at, project.daily_hours, project.work_start, holidays
    )
    return Shortage(rest, capacity, unit, due_at, basis)
```

Run: `uv run pytest test/test_shortage.py -q`
Expected: 既存のテストがすべて PASS(取り出しで挙動が変わっていない)

- [ ] **Step 2: Write the failing tests**

`test/test_shortage.py`の import に`RequiredRate`・`required_rate`・`required_rate_hint`・`required_rate_text`を足し、末尾に追記する(`MON`・`FRI`・`project_of`・`task_of`は既存。`MON` = 2026-10-05 月 9:00、月〜金で 1 人 32.5h)。

```python
def needed(task: Task, now: datetime = MON) -> RequiredRate | str:
    return required_rate(task, project_of(task), {}, now)


def rates(value: RequiredRate) -> dict[str, tuple[float, float]]:
    return {name: (now_rate, need) for name, now_rate, need in value.members}


def test_a_shortage_that_reaches_scales_everyone_by_the_same_factor() -> None:
    task = task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)])
    value = needed(task)  # 残り 40h・稼働 32.5h
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(40 / 32.5, rel=1e-4)
    assert rates(value)["田中"][1] == pytest.approx(0.5 * 40 / 32.5, rel=1e-4)
    assert rates(value)["鈴木"] == pytest.approx((0.5, 0.5 * 40 / 32.5), rel=1e-4)
    assert value.short_hours == 0.0 and value.short_people is None


def test_a_member_already_at_100_percent_stays_and_the_others_make_up_the_rest() -> None:
    task = task_of(
        effort_hours=60.0, assignees=[Assignee("田中"), Assignee("鈴木", 0.5)]
    )  # 稼働 32.5 + 16.25 = 48.75h。田中は 100% のまま、鈴木が 0.846 まで
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(1.6923, rel=1e-3)
    assert rates(value)["田中"] == pytest.approx((1.0, 1.0))
    assert rates(value)["鈴木"] == pytest.approx((0.5, 0.8462), rel=1e-3)


def test_when_even_everyone_at_100_percent_falls_short_there_is_no_factor() -> None:
    value = needed(task_of())  # 田中 100%・残り 40h・稼働 32.5h
    assert isinstance(value, RequiredRate)
    assert value.factor is None and value.members == ()
    assert value.short_hours == pytest.approx(7.5)
    assert value.short_people == pytest.approx(7.5 / 32.5)


def test_weekly_crews_are_scaled_in_every_week() -> None:
    task = task_of(
        effort_hours=30.0,
        assignees=[Assignee("田中", 0.5)],
        weekly_crew=[[Assignee("田中", 0.5)]],
    )  # 稼働 16.25h
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(30 / 16.25, rel=1e-4)


def test_daily_crews_use_the_peak_rate_for_the_member() -> None:
    days = [[Assignee("田中", 0.5)] for _ in range(3)] + [
        [Assignee("田中")] for _ in range(4)
    ]  # 月〜水 50%・木〜日 100%。稼働 9.75 + 13 = 22.75h
    task = task_of(
        effort_hours=30.0,
        assignees=[Assignee("田中")],
        weekly_crew=[[Assignee("田中")]],
        daily_crew={0: days},
    )
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(1.7436, rel=1e-3)
    assert rates(value)["田中"] == pytest.approx((1.0, 1.0))


def test_the_original_task_is_not_changed() -> None:
    task = task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)])
    needed(task)
    assert [a.allocation for a in task.assignees] == [0.5, 0.5]


def test_no_shortage_or_no_due_gives_a_reason_string() -> None:
    assert needed(task_of(effort_hours=20.0)) == "不足していません"
    reason = needed(task_of(deadline=None))
    assert isinstance(reason, str) and "基準日" in reason
    assert needed(task_of(), now=datetime(2026, 10, 12, 9)) == "基準日を過ぎています"


def test_the_text_names_the_factor_and_each_members_rate() -> None:
    task = task_of(
        effort_hours=60.0, assignees=[Assignee("田中"), Assignee("鈴木", 0.5)]
    )
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert required_rate_text(value) == "必要な率: 今の ×1.7(田中 100%・鈴木 50→85%)"


def test_the_text_lists_three_members_and_counts_the_rest() -> None:
    members = tuple((f"m{i}", 0.5, 0.6) for i in range(5))
    shortage = Shortage(40.0, 32.5, 32.5, FRI, "締切")
    value = RequiredRate(1.2, members, 0.0, None, shortage)
    assert required_rate_text(value) == "必要な率: 今の ×1.2(m0 50→60%・m1 50→60%・m2 50→60%・ほか 2 人)"


def test_the_text_when_even_everyone_at_100_percent_falls_short() -> None:
    value = needed(task_of())
    assert isinstance(value, RequiredRate)
    assert required_rate_text(value) == "全員 100% でもあと 7.5h 足りません(約 0.2 人)"


def test_the_hint_gives_the_remaining_the_capacity_and_the_due() -> None:
    value = needed(task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)]))
    assert isinstance(value, RequiredRate)
    hint = required_rate_hint(value)
    assert "残り 40.0h / 稼働 32.5h" in hint and "10/09 17:00 まで。締切" in hint
    assert "×1.23" in hint


def test_a_52_week_task_with_the_lowest_rate_is_fast() -> None:
    import time

    task = task_of(
        effort_hours=400.0,
        deadline=datetime(2027, 10, 1, 17),
        assignees=[Assignee("田中", 0.01)],
    )
    began = time.perf_counter()
    needed(task)
    assert time.perf_counter() - began < 2.0
```

Run: `uv run pytest test/test_shortage.py -q -k "scales or at_100 or no_factor or scaled or peak or not_changed or reason_string or the_text or the_hint or 52_week"`
Expected: FAIL(`ImportError: cannot import name 'RequiredRate'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/shortage.py`の先頭の import に、`from dataclasses import dataclass, replace`・`from math import ceil, isfinite`を揃え、`from projectapp.models import (...)`に`MAX_ALLOCATION`を足す。ファイルの末尾に追記する。

```python
@dataclass(frozen=True)
class RequiredRate:
    factor: float | None  # 倍率 k。全員 100% でも届かないときは None
    members: tuple[tuple[str, float, float], ...]  # (名前, 今の率, 必要な率)。届かないときは空
    short_hours: float  # 届かないときの、足りない時間[h]
    short_people: float | None  # 同じく、100% の人に換算した人数
    shortage: Shortage  # 4a の不足(ヒントに使う)


BISECT_STEPS = 50  # 倍率の二分法の回数(k の上限は最大 100 なので、十分に細かい)


def _crews(task: Task) -> list[list[Assignee]]:
    """全体・週ごと・日ごとのすべての担当。"""
    return [
        task.assignees,
        *task.weekly_crew,
        *(crew for days in task.daily_crew.values() for crew in days),
    ]


def _scaled(task: Task, factor: float) -> Task:
    """担当の率を factor 倍(各人 100% で頭打ち)にした複製。元は変えない。"""

    def scale(crew: list[Assignee]) -> list[Assignee]:
        return [
            replace(a, allocation=min(MAX_ALLOCATION, a.allocation * factor))
            for a in crew
        ]

    return replace(
        task,
        assignees=scale(task.assignees),
        weekly_crew=[scale(crew) for crew in task.weekly_crew],
        daily_crew={
            week: [scale(crew) for crew in days]
            for week, days in task.daily_crew.items()
        },
    )


def required_rate(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> RequiredRate | str:
    """基準日に間に合う、担当の率の倍率(要望 168 段階 4c)。不足のときだけ出す。出せないときは理由の文字列。
    担当の全員の率(全体・週ごと・日ごと)を k 倍して各人 100% で頭打ちにし、稼働量が残りの工数に届く最小の k を求める。"""
    schedule = schedule or Schedule(project, holidays)
    value = task_shortage(task, project, holidays, now, schedule)
    if isinstance(value, str):
        return value
    if value.kind != "不足":
        return "不足していません"
    start = effective_start(task, project, holidays, schedule)
    if start is None:  # task_shortage が通っているので起きないが、型のために
        return "開始日がありません"
    origin = max(now, start)

    def capacity(factor: float) -> float:
        return _capacity_of(
            _scaled(task, factor), project, holidays, origin, value.due, start
        )

    allocations = [a.allocation for crew in _crews(task) for a in crew]
    upper = 1.0 / min(allocations) if allocations else 1.0  # これ以上は全員 100% で同じ
    best = capacity(upper)
    if best < value.remaining - 1e-9:
        short = value.remaining - best
        people = None if value.unit <= 0 else short / value.unit
        return RequiredRate(None, (), short, people, value)
    low, high = 1.0, upper
    for _ in range(BISECT_STEPS):
        mid = (low + high) / 2
        if capacity(mid) >= value.remaining:
            high = mid
        else:
            low = mid
    peaks: dict[str, float] = {}
    for crew in _crews(task):
        for a in crew:
            peaks[a.name] = max(peaks.get(a.name, 0.0), a.allocation)
    members = tuple(
        (name, peak, min(MAX_ALLOCATION, peak * high)) for name, peak in peaks.items()
    )
    return RequiredRate(high, members, 0.0, None, value)


def _up(value: float, digits: int = 0) -> float:
    """表示の桁で、足りない側にずれないよう切り上げる(浮動小数点の誤差は除く)。"""
    scale = 10**digits
    return ceil(value * scale - 1e-6) / scale


MEMBERS_SHOWN = 3  # 文言に出す人数(これを超える分は`ほか n 人`)


def required_rate_text(value: RequiredRate) -> str:
    """`必要な率: 今の ×1.7(田中 100%・鈴木 50→85%)`・`全員 100% でもあと 7.5h 足りません(約 0.2 人)`。"""
    if value.factor is None:
        people = value.short_people
        tail = "" if people is None or round(people, 1) == 0 else f"(約 {people:.1f} 人)"
        return f"全員 100% でもあと {value.short_hours:.1f}h 足りません{tail}"
    parts = []
    for name, now_rate, need in value.members[:MEMBERS_SHOWN]:
        before, after = round(now_rate * 100), int(_up(need * 100))
        parts.append(f"{name} {before}→{after}%" if after != before else f"{name} {before}%")
    rest = len(value.members) - MEMBERS_SHOWN
    if rest > 0:
        parts.append(f"ほか {rest} 人")
    return f"必要な率: 今の ×{_up(value.factor, 1):.1f}({'・'.join(parts)})"


def required_rate_hint(value: RequiredRate) -> str:
    """ホバーの文字。4a の不足のヒントに、倍率の前提を足す。"""
    base = shortage_hint(value.shortage)
    if value.factor is None:
        return f"{base}。全員の率を 100% にしても、残りの工数に届きません"
    return f"{base}。全員の率を ×{value.factor:.2f}(上限 100%)にすると、稼働が残りの工数に届きます"
```

注: `Assignee`・`MAX_ALLOCATION`は`projectapp.models`から import する(`from projectapp.models import Assignee, MAX_ALLOCATION, Project, Status, Task, TaskKind`。ruff の import 順に合わせる)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_shortage.py -q`
Expected: すべて PASS。`test_the_text_names_...`の期待が丸めで合わないときは、実装の値(`_up`の使い方)でなく、計算の例(鈴木 0.8462 → 85%・倍率 1.6923 → ×1.7)に合わせて直す。`test_the_text_when_even_everyone...`は、7.5 ÷ 32.5 = 0.23 → `約 0.2 人`

- [ ] **Step 5: Commit**

```bash
uvx ruff format src test && uvx ruff check
git add src/projectapp/shortage.py test/test_shortage.py
git commit -m "feat: 基準日に間に合う割り当て率の倍率 required_rate を足す(要望 168 段階 4c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ヘッダーに必要な率の行を出す(`assign_screen.py`)

**Files:**
- Modify: `src/projectapp/assign_screen.py`(import・ヘッダー約 184 行・`render_shortage`の次・`refresh`約 748 行・`open`の約 226 行)
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`required_rate`・`required_rate_text`・`required_rate_hint`・`RequiredRate`
- Produces: `AssignScreen.required_label: ui.label | None`・`AssignScreen.render_required_rate(project: Project | None = None) -> None`。マーカーは`assign-required-rate`

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`の末尾に追記する(`open_team_screen`・`label_text`・`datetime`は既存。試算のタスクは、工数 40h・担当は田中 100%・11/16 月開始)。

```python
async def test_the_required_rate_row_shows_when_everyone_at_100_percent_falls_short(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)  # 稼働 32.5h・残り 40h
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("全員 100% でもあと 7.5h 足りません")
    label = user.find(marker="assign-required-rate").elements.pop()
    assert "--warning" in str(label._style)


async def test_the_required_rate_row_gives_the_factor_when_it_can_reach(
    user: User,
) -> None:
    from projectapp.daily_crew import set_allocation_all

    screen, _ = await open_team_screen(user)
    screen.trial.task.effort_hours = 20.0
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)
    changed = set_allocation_all(screen.trial.task, "田中", 0.5)  # 稼働 16.25h
    assert changed is not None
    screen.trial.task = changed
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("必要な率: 今の ×1.3(田中 50→62%)")
    label = user.find(marker="assign-required-rate").elements.pop()
    assert "--warning" not in str(label._style)
    assert "title" in label.props


async def test_the_required_rate_row_hides_when_there_is_no_shortage(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see(marker="assign-required-rate")
    screen.drop_member("鈴木", 0, None)  # 余裕になる
    await user.should_see("余裕")
    await user.should_not_see(marker="assign-required-rate")


async def test_the_required_rate_row_is_hidden_without_a_due(user: User) -> None:
    await open_team_screen(user)
    await user.should_see(marker="assign-shortage")
    await user.should_not_see(marker="assign-required-rate")


async def test_the_required_rate_row_does_not_make_the_screen_dirty(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    assert not is_dirty(screen.trial)
```

Run: `uv run pytest test/test_assign_screen.py -q -k required_rate`
Expected: FAIL(`assign-required-rate`が見つからない)

- [ ] **Step 2: Write minimal implementation**

`assign_screen.py`の`from projectapp.shortage import (...)`に`required_rate`・`required_rate_hint`・`required_rate_text`を足す(`RequiredRate`は不要)。`__init__`の`self.shortage_label`の次に`self.required_label: ui.label | None = None`を足す。

ヘッダーの不足の行(約 185 行)を、2 行を縦に並べる列にする。

```python
                with ui.column().classes("gap-0"):
                    self.shortage_label = (
                        ui.label("").classes("text-body2").mark("assign-shortage")
                    )
                    self.required_label = (
                        ui.label("")
                        .classes("text-body2")
                        .mark("assign-required-rate")
                    )
                    self.required_label.set_visibility(False)
```

`render_shortage`の次に追加する。

```python
    def render_required_rate(self, project: Project | None = None) -> None:
        """基準日に間に合う率の倍率を、不足の行の下に出す。不足でないとき・出せないときは行ごと隠す。"""
        label = self.required_label
        if label is None:
            return
        value = required_rate(
            self.trial.task,
            project or trial_project(self.project, self.trial),
            self.holidays,
            self.now(),
        )
        if isinstance(value, str):
            label.set_visibility(False)
            return
        label.set_text(required_rate_text(value))
        label.style(
            "color: var(--warning)" if value.factor is None else "color: inherit"
        )
        label.props(f'title="{required_rate_hint(value)}"')
        label.set_visibility(True)
```

注: `render_shortage`と同じく、`label.style(...)`は足し算なので、切り替えのときに前の色が残らないよう`label.style(replace="color: ...")`にする。ヒントの`title`が`"`を含まないことは文言で保証する(`required_rate_hint`は`"`を使わない)。

呼び出しは、`open`の`self.render_shortage()`(約 226 行)の次と、`refresh`の`self.render_shortage(trial)`(約 748 行)の次に`render_required_rate`を足す。

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py -q`
Expected: すべて PASS。`should_not_see`が隠した行で通らないときは、`set_visibility(False)`でなく`label.visible`の値を直接確かめる形に直す

- [ ] **Step 4: smoke・lint・型**

Run: `uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: smoke 全 PASS・ruff 問題なし・ty は既存の 9 件のみ

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン画面のヘッダーに必要な割り当て率の行を出す(要望 168 段階 4c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 文書・設計書の更新と PR

**Files:**
- Modify: `docs/superpowers/specs/2026-11-24-assign-screen-stage4c-design.md`・`docs/requests.md`・`docs/development.md`・`.claude/spec/dashboard.md`

- [ ] **Step 1: 設計書を実装に合わせる**

設計書の`RequiredRate`の項目に、`shortage: Shortage`(4a の不足。ヒントに使う)を足す。「確かめること」の 3 点に、結果(複製は`replace`で作る・週ごと日ごとも同じ k・二分法 50 回で 52 週も軽い)を 1 行ずつ書く。

- [ ] **Step 2: 仕様・構成・要望の記録を更新する**

- `.claude/spec/dashboard.md`: `grep -n "週ごとの消化" .claude/spec/dashboard.md`で見つかる 4b の記述の次に、4c の説明を足す(不足のときだけ、ヘッダーの不足の行の下に、`必要な率: 今の ×k(人ごとの率)`を出す。全員を k 倍・各人 100% で頭打ち・届かないときは`全員 100% でもあと Xh 足りません(約 Y 人)`・基準日の定義は 4a と同じ)
- `docs/development.md`の`shortage.py`の行に、`RequiredRate`・`required_rate`(必要な割り当て率。要望 168 段階 4c)を足す
- `docs/requests.md`: 要望 168 の状態の段階 4c を`実装済み(設計書: ...stage4c-design.md・計画: ...stage4c.md。実機確認待ち)`にし、`段階 4d(試算の前後の比較)は未着手`だけを残す。要望 160 の状態に、`率の逆算は 168 段階 4c で実装した。着工遅れの入力欄は未着手`を足す

- [ ] **Step 3: 全体の確認と PR**

Run: `uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: 通る

```bash
git add docs .claude/spec
git commit -m "docs: アサイン画面の必要な割り当て率(段階 4c)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/request-168-stage4c
gh pr create --base develop --title "feat: アサイン画面の必要な割り当て率の逆算(要望 168 段階 4c)" --body "..."
```

PR の本文は、変更の要約・テスト結果・実機確認の手順(基準日のあるタスクで、率を下げて不足にし、ヘッダーに倍率が出る・率を上げて余裕になると消える・全員 100% でも足りないときの文言が警告色になる)を書き、末尾に`🤖 Generated with [Claude Code](https://claude.com/claude-code)`を付ける。PR を作って止まる。マージは利用者の指示を待つ。
