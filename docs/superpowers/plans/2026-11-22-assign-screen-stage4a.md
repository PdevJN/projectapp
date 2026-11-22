# アサイン専用画面 段階 4a(不足と余裕)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面の上の行に、このタスクが基準日(締切、なければ手で決めた完了予定)までに終わるのに、稼働量が足りているかを、不足・余裕の時間と人数で出す。割り当てを変えるたびに更新する。

**Architecture:** 計算は新しい純粋関数のモジュール`shortage.py`(`pace.py`と同じ`work_capacity`で、基準日までの稼働量を数える)。文言も同じモジュールの純粋関数(画面から切り離してテストする)。画面は`AssignScreen`の上の行にラベルを 1 つ足し、`refresh`から更新する。ファイル形式は変えない。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-22-assign-screen-stage4a-design.md`(段階 1〜5 は同じディレクトリの`2026-11-22-assign-screen-stage*-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。試算は保存しない。不足の表示は試算に含めず、`is_dirty`は変えない
- 基準日は、締切。なければ、手で決めた完了予定(`planned_end_manual`が真の`planned_end`)。算出された完了予定は基準にしない
- 稼働量の数え方は`pace.py`と同じ(`work_capacity`。週ごと・日ごとの担当・休み・祝日・稼働日の上書きを反映。始点は`max(now, 実効の開始)`)
- 不足・余裕の時間は小数 1 桁。表示の桁で 0.0 になる差は`ちょうど`
- マーカーは`assign-`で始める。メインのチャート・ダッシュボードの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは git-flow。設計書のブランチ`feature/request-168-stage4a`のまま実装する。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差・補足)

- 不足の行は、チャートの上ではなく、ヘッダー行(タイトルと`日次/週次/月次`の切り替えの間)に置く。チャートの領域は高さが固定の`flex`で、行を足すと崩れるため
- ホバーの文言は、ラベルの`title`属性で出す(`ui.tooltip`は再描画のたびに増えるため)
- `Shortage`の人数は、不足・余裕とも絶対値で持つ(`people`)。符号は`kind`で表す
- `now`は`AssignScreen`が持つ`self.now()`(既存。テストで差し替えられる)

## Review Focus

- 率を下げる・担当を外すと不足が増え、範囲で増員すると不足が減る(元のプロジェクトは変わらない)
- 締切も手で決めた完了予定もないタスクは、不足を出さず理由を出す(完了予定が算出のときに 0 と出さない)
- 基準日を過ぎたタスク・開始日のないタスク・工数のないタスク・残りのないタスクは、理由を出して落ちない
- 担当者がいないタスク(稼働量 0)は、不足が工数そのままで、人数が出せるときは出す
- 進捗度・実績があるタスクは、消化分を引いた残りで数える
- 開始が未来のタスクは、始点を開始にする(今日から数えない)

---

### Task 1: `shortage.py`(計算と文言)

**Files:**
- Create: `src/projectapp/shortage.py`
- Test: `test/test_shortage.py`

**Interfaces:**
- Consumes: `pace.py`と同じ部品。`remaining.remaining_hours(task, project, holidays, now)`・`remaining.total_effort(task)`・`timeline.Schedule`・`timeline.effective_start(task, project, holidays, schedule)`・`timeline.crew_of(assignees, members, parameters, only, limits)`・`timeline.weekly_crews(task, project)`・`timeline.work_capacity(start, end, daily_hours, work_start, holidays, crew=None, weeks=None, weeks_start=None)`
- Produces:
  - `due_of(task: Task) -> tuple[datetime, str] | None` — (基準日, `"締切"`または`"完了予定"`)
  - `@dataclass(frozen=True) Shortage(remaining: float, capacity: float, unit: float, due: datetime, basis: str)` とプロパティ`gap: float`・`kind: str`(`"不足"`/`"余裕"`/`"ちょうど"`)・`people: float | None`
  - `task_shortage(task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule | None = None) -> Shortage | str`(出せないときは理由の文字列)
  - `shortage_text(value: Shortage) -> str`・`shortage_hint(value: Shortage) -> str`

- [ ] **Step 1: Write the failing tests**

`test/test_shortage.py`:

```python
from datetime import date, datetime

import pytest

from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from projectapp.shortage import (
    Shortage,
    due_of,
    shortage_hint,
    shortage_text,
    task_shortage,
)

MON = datetime(2026, 10, 5, 9)  # 稼働の枠は 9:00〜15:30(6.5h)
FRI = datetime(2026, 10, 9, 17)  # 月〜金の稼働量は 5 日 × 6.5h = 32.5h


def project_of(*tasks: Task) -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        sections=[Section("s", list(tasks))],
    )


def task_of(**kwargs) -> Task:
    base = dict(
        planned_start=MON,
        effort_hours=40.0,
        deadline=FRI,
        assignees=[Assignee("田中")],
    )
    return Task("設計", **{**base, **kwargs})


def judged(task: Task, now: datetime = MON) -> Shortage | str:
    return task_shortage(task, project_of(task), {}, now)


def test_the_due_is_the_deadline_then_a_manual_planned_end() -> None:
    manual = datetime(2026, 10, 8, 17)
    assert due_of(task_of()) == (FRI, "締切")
    assert due_of(task_of(deadline=None, planned_end=manual, planned_end_manual=True)) == (
        manual,
        "完了予定",
    )
    assert due_of(task_of(deadline=None, planned_end=manual)) is None  # 算出の完了予定は基準にしない
    assert due_of(task_of(deadline=None)) is None


def test_a_shortage_is_the_remaining_effort_minus_the_capacity_to_the_due() -> None:
    value = judged(task_of())
    assert isinstance(value, Shortage)
    assert value.remaining == pytest.approx(40.0)
    assert value.capacity == pytest.approx(32.5)
    assert value.gap == pytest.approx(7.5) and value.kind == "不足"
    assert value.unit == pytest.approx(32.5)
    assert value.people == pytest.approx(7.5 / 32.5)
    assert value.basis == "締切"


def test_a_lower_rate_makes_the_shortage_bigger() -> None:
    value = judged(task_of(assignees=[Assignee("田中", 0.5)]))
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(16.25) and value.gap == pytest.approx(23.75)


def test_more_members_make_a_margin() -> None:
    value = judged(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert isinstance(value, Shortage)
    assert value.gap == pytest.approx(-25.0) and value.kind == "余裕"
    assert value.people == pytest.approx(25.0 / 32.5)  # 絶対値


def test_a_gap_that_rounds_to_zero_is_just_right() -> None:
    value = judged(task_of(effort_hours=32.51))
    assert isinstance(value, Shortage) and value.kind == "ちょうど"
    assert shortage_text(value) == "ちょうど"


def test_progress_reduces_the_remaining_effort() -> None:
    value = judged(task_of(progress=50))
    assert isinstance(value, Shortage)
    assert value.remaining == pytest.approx(20.0) and value.kind == "余裕"


def test_a_task_without_assignees_has_no_capacity_but_the_unit_still_counts() -> None:
    value = judged(task_of(assignees=[]))
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(32.5)  # 担当者なしは換算率 1 の 1 人
    # (pace.py と同じ扱い)


def test_the_weekly_crew_changes_the_capacity() -> None:
    task = task_of(
        weekly_crew=[[Assignee("田中", 0.5)], [Assignee("田中")]],
        deadline=datetime(2026, 10, 16, 17),
    )
    value = judged(task)
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(16.25 + 32.5)


def test_a_future_start_counts_from_the_start() -> None:
    task = task_of(planned_start=datetime(2026, 10, 7, 9))  # 水曜から
    value = judged(task, now=MON)
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(3 * 6.5)


def test_holidays_do_not_count() -> None:
    task = task_of()
    value = task_shortage(
        task, project_of(task), {date(2026, 10, 7): "休み"}, MON
    )
    assert isinstance(value, Shortage) and value.capacity == pytest.approx(26.0)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        (task_of(effort_hours=0.0), "工数がありません"),
        (task_of(deadline=None), "基準日"),
        (task_of(planned_start=None), "開始日がありません"),
        (task_of(deadline=datetime(2026, 10, 1, 17)), "基準日を過ぎています"),
        (task_of(progress=100), "残りの工数がありません"),
        (task_of(status=Status.DONE), "終了"),
        (task_of(kind=TaskKind.MILESTONE), "通常"),
    ],
)
def test_reasons_when_it_cannot_be_shown(task: Task, reason: str) -> None:
    value = judged(task)
    assert isinstance(value, str) and reason in value


def test_the_text_and_the_hint() -> None:
    value = judged(task_of())
    assert isinstance(value, Shortage)
    assert shortage_text(value) == "あと 7.5h 足りません(約 0.2 人)"
    assert shortage_hint(value) == "残り 40.0h / 稼働 32.5h(10/09 17:00 まで。締切)"
    margin = judged(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert isinstance(margin, Shortage)
    assert shortage_text(margin) == "余裕 25.0h(約 0.8 人)"
```

(`Task`の`kind`・`status`・`planned_end_manual`の引数名は`models.py`で確かめ、合わせる。`Status.DONE`・`TaskKind.MILESTONE`が違えば、`models.py`にある名前にする。)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_shortage.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.shortage`)

- [ ] **Step 3: Write the implementation**

`src/projectapp/shortage.py`:

```python
"""アサイン専用画面の不足と余裕(要望 168 段階 4a。要望 158 の不足の定義)。NiceGUI に依存しない純粋関数。

基準日(締切、なければ手で決めた完了予定)までに、このタスクの担当で積める稼働量が、残りの工数に足りているかを見る。
算出された完了予定は基準にしない(割り当てから決まるので、常に足りてしまう)。稼働量の数え方は警告の判定(`pace.py`)と同じ。"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import (
    Schedule,
    crew_of,
    effective_start,
    weekly_crews,
    work_capacity,
)

GAP_EPSILON = 0.05  # 時間を小数 1 桁で表したとき 0.0 になる差(これ未満は`ちょうど`)


@dataclass(frozen=True)
class Shortage:
    remaining: float  # 残りの工数[h]
    capacity: float  # 今から基準日までに、このタスクの担当で積める稼働量[h](換算率つき)
    unit: float  # 同じ範囲に、100% の人 1 人が積める稼働量[h](人数への換算の分母)
    due: datetime  # 基準日
    basis: str  # `締切`か`完了予定`

    @property
    def gap(self) -> float:
        """残りの工数 − 稼働量。正なら不足、負なら余裕。"""
        return self.remaining - self.capacity

    @property
    def kind(self) -> str:
        if abs(self.gap) < GAP_EPSILON:
            return "ちょうど"
        return "不足" if self.gap > 0 else "余裕"

    @property
    def people(self) -> float | None:
        """不足(余裕)を、100% の人の数に換算した値(絶対値)。換算の分母がないときは None。"""
        return None if self.unit <= 0 else abs(self.gap) / self.unit


def due_of(task: Task) -> tuple[datetime, str] | None:
    """基準日と、その種類。締切があればそれ、なければ手で決めた完了予定。どちらもなければ None。"""
    if task.deadline is not None:
        return task.deadline, "締切"
    if task.planned_end_manual and task.planned_end is not None:
        return task.planned_end, "完了予定"
    return None


def task_shortage(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    schedule: Schedule | None = None,
) -> Shortage | str:
    """不足と余裕。出せないときは、その理由の文字列を返す。"""
    if task.kind is not TaskKind.NORMAL:
        return "通常のタスクではありません"
    if task.status is Status.DONE:
        return "終了したタスクです"
    effort = total_effort(task)
    if not (isfinite(effort) and effort > 0):
        return "工数がありません"
    due = due_of(task)
    if due is None:
        return "基準日(締切か、手で決めた完了予定)がありません"
    schedule = schedule or Schedule(project, holidays)
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return "開始日がありません"
    rest = remaining_hours(task, project, holidays, now)
    if not rest > 0:
        return "残りの工数がありません"
    origin = max(now, start)
    due_at, basis = due
    if due_at <= origin:
        return "基準日を過ぎています"
    capacity = work_capacity(
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
    unit = work_capacity(
        origin, due_at, project.daily_hours, project.work_start, holidays
    )
    return Shortage(rest, capacity, unit, due_at, basis)


def shortage_text(value: Shortage) -> str:
    """`あと 12.0h 足りません(約 0.8 人)`・`余裕 6.0h(約 0.4 人)`・`ちょうど`。人数は 100% の人に換算した数。"""
    kind = value.kind
    if kind == "ちょうど":
        return "ちょうど"
    hours = abs(value.gap)
    people = value.people
    tail = "" if people is None else f"(約 {people:.1f} 人)"
    if kind == "不足":
        return f"あと {hours:.1f}h 足りません{tail}"
    return f"余裕 {hours:.1f}h{tail}"


def shortage_hint(value: Shortage) -> str:
    """ホバーの文字。`残り 40.0h / 稼働 28.0h(11/30 17:00 まで。締切)`。"""
    return (
        f"残り {value.remaining:.1f}h / 稼働 {value.capacity:.1f}h"
        f"({value.due:%m/%d %H:%M} まで。{value.basis})"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest test/test_shortage.py -q`
Expected: PASS。`担当者なし`のテスト(`test_a_task_without_assignees_…`)は、`work_capacity`が空の担当者を換算率 1 の 1 人で数えるので 32.5 になる。違えば実装ではなくテストの期待値を確かめて直す(`pace.py`と同じ扱いにする)。`Task`の引数名が違えば、テストの`task_of`を合わせる。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/shortage.py test/test_shortage.py
git commit -m "feat: 基準日までの稼働量に対する不足と余裕を数える shortage を足す(要望 168 段階 4a)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 画面の行

**Files:**
- Modify: `src/projectapp/assign_screen.py`(`build`のヘッダー行・`refresh`・新しいメソッド`render_shortage`)
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`task_shortage`・`shortage_text`・`shortage_hint`・`Shortage`。`AssignScreen.now`(`Callable[[], datetime]`)・`self.trial.task`・`self.holidays`・`trial_project(self.project, self.trial)`(試算のタスクを差し戻したプロジェクト)
- Produces: マーカー`assign-shortage`のラベル。`AssignScreen.render_shortage()`(`refresh`と`build`から呼ぶ)

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`に足す(`team_project`・`open_team_screen`は既存。`team_project`の「設計」は`2026-11-16`〜`11-30`・工数 40h・担当は田中 100%・締切なし。テストでは、画面の試算のタスクに締切を入れてから`refresh`する):

```python
def label_text(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


async def test_without_a_deadline_the_shortage_row_says_why(user: User) -> None:
    await open_team_screen(user)
    await user.should_see(marker="assign-shortage")
    assert "基準日" in label_text(user, "assign-shortage")


async def test_the_shortage_row_follows_the_assignment(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)  # 11/16 月〜20 金: 5 日 × 6.5h
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("あと 7.5h 足りません")
    screen.drop_member("鈴木", 0, None)  # 週 0 に 鈴木 を足す(100%)
    await user.should_see("余裕")
    text = label_text(user, "assign-shortage")
    assert text.startswith("余裕 25.0h")


async def test_the_shortage_row_hint_names_the_due(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("あと 7.5h 足りません")
    label = user.find(marker="assign-shortage").elements.pop()
    assert "11/20 17:00 まで。締切" in str(label.props.get("title", ""))


async def test_the_shortage_row_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = None
    screen.refresh()
    assert not is_dirty(screen.trial)
```

(最後のテストは、`deadline`を触っても`is_dirty`が変わらない確認ではなく、行の表示が試算を変えないことの確認。`screen.trial.task.deadline`への代入が`is_dirty`を変えるなら、代入しないで`refresh()`だけにする。`datetime`は既に import 済み。`drop_member`の第 2・3 引数は`(name, week, day)`。)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_assign_screen.py -q -k shortage`
Expected: FAIL(`assign-shortage`のマーカーがない)

- [ ] **Step 3: Write the implementation**

`assign_screen.py`:

- import に`from projectapp.shortage import Shortage, shortage_hint, shortage_text, task_shortage`を足す
- `__init__`に`self.shortage_label: ui.label | None = None`を足す
- `build`のヘッダー行の、タイトルのラベルと`ui.toggle`の間に、次を置く:

```python
                self.shortage_label = ui.label("").classes("text-body2").mark(
                    "assign-shortage"
                )
```

- `build`の最後の`dialog.open()`の前(`self.build_rate_popup()`の次)で`self.render_shortage()`を呼ぶ。`refresh`の末尾の`self.render_load()`の次にも`self.render_shortage()`を足す
- メソッド:

```python
    def render_shortage(self) -> None:
        """基準日までの不足・余裕を、ヘッダーの 1 行に出す。出せないときは理由を薄く出す。"""
        label = self.shortage_label
        if label is None:
            return
        value = task_shortage(
            self.trial.task,
            trial_project(self.project, self.trial),
            self.holidays,
            self.now(),
        )
        if isinstance(value, str):
            label.set_text(f"不足は出せません: {value}")
            label.classes(replace="text-body2 text-grey")
            label.props(remove="title")
            return
        label.set_text(shortage_text(value))
        color = "text-body2" + (" text-bold" if value.kind == "不足" else "")
        label.classes(replace=color)
        label.style(
            "color: var(--warning)" if value.kind == "不足" else "color: inherit"
        )
        label.props(f'title="{shortage_hint(value)}"')
```

(`trial_project`は既存の import を使う。`Shortage`の import は型注釈に使わなければ入れない。ruff の未使用を避ける。)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py test/test_shortage.py -q`
Expected: PASS(既存のアサイン画面のテストも通る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン画面のヘッダーに不足と余裕を出す(要望 168 段階 4a)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 文書

**Files:**
- Modify: `.claude/spec/dashboard.md`(`段階 5`の段落の次に`段階 4a`を追記)
- Modify: `docs/development.md`(モジュール表に`shortage.py`を足し、`test_shortage.py`を足す)
- Modify: `docs/requests.md`(要望 168 の状態・要望 158 の状態)

- [ ] **Step 1: 仕様書**

`.claude/spec/dashboard.md`の`段階 5(負荷のヒストグラム)`の段落の末尾に、次を足す: `段階 4a(不足と余裕): ヘッダー(タイトルの右)に、基準日までの不足・余裕を 1 行で出す。基準日は締切、なければ手で決めた完了予定(算出の完了予定は基準にしない)。不足は残りの工数(消化分を引く)から、今(開始が先なら開始)から基準日までの、このタスクの担当の稼働量(週ごと・日ごとの担当・休み・祝日・稼働日の上書きを反映。警告の判定と同じ数え方)を引いた時間で、人数は 100% の人に換算した数。`あと 7.5h 足りません(約 0.2 人)`(警告の色)・`余裕 25.0h(約 0.8 人)`・`ちょうど`(表示の桁で 0.0)。出せないときは理由を薄く出す(`基準日がありません`など)。ホバーに`残り 40.0h / 稼働 32.5h(11/20 17:00 まで。締切)`。割り当てを変えるたびに更新する。試算には含めない(`shortage.py`)。`

- [ ] **Step 2: 開発文書・要望**

`docs/development.md`のモジュール表に、`assign_load.py`の行の次へ次を足す: `| `shortage.py` | アサイン専用画面の不足と余裕(`Shortage`・`task_shortage`・`shortage_text`。要望 168 段階 4a・要望 158 の不足の定義。NiceGUI に依存しない) |`。テストの一覧があれば`test_shortage.py`も足す。

`docs/requests.md`: 要望 168 の状態の末尾に`段階 4a(不足と余裕)は実装済み(設計書: …-stage4a-design.md・計画: …-stage4a.md。PR は作成後に記す。実機確認待ち)。段階 4b〜4d は未着手。`を足す。要望 158 の状態に、`段階 4a のアサイン専用画面で、不足の定義(基準日は締切、なければ手で決めた完了予定。残りの工数 − 基準日までの稼働量)を決めて実装した。ガントチャートの編集ダイアログなど、ほかの入口への展開は未着手。`を足す。

- [ ] **Step 3: 検証とコミット**

Run: `uv run pytest -m smoke -q && uvx ruff check src test && uvx ruff format src test && uvx ty check src`
Expected: smoke PASS・ruff OK・ty は既存の 9 件のみ

```bash
git add .claude/spec/dashboard.md docs/development.md docs/requests.md
git commit -m "docs: アサイン画面の不足と余裕(段階 4a)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
