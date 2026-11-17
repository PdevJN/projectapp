# 負荷の調整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードの`人ごとの負荷`で割り当て超過の人から、その人の担当(率の変更・他の人への移し替え・別の人の追加)を調整する`負荷の調整`ダイアログを作る。変えるたびに、負荷と完了予定・見込みの前後を見せ、適用は元に戻す 1 ステップにする。

**Architecture:** 計算は NiceGUI から切り離した純粋関数のモジュール`rebalance.py`(調整を当てた複製・前後の比較・入力から調整への変換)。画面は`rebalance_dialog.py`、入口はダッシュボードの`調整…`ボタン(`dashboard_view.py`)と、適用の受け口(`views.py`)。既存の`summarize_loads`・`summarize_backlog`の候補・`forecast_end`・`reassign`の見直しを再利用する。

**Tech Stack:** Python 3.13、NiceGUI、pytest(NiceGUI の`User`テスト)。

**Spec:** `docs/superpowers/specs/2026-11-17-load-rebalance-design.md`

## Global Constraints

- 言語は日本語(画面の文言・コメント・テスト名以外の説明)。Python 3.13 以上。
- ファイル形式は変えない(`version`は 23 のまま。保存する項目も増やさない)。
- 画面は NiceGUI の要素と CSS の自前描画。マーカーは`.mark("…")`で付ける。
- 実装の完了ごと: `uv run pytest -m smoke` → `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`(既存の 9 件以外が増えないこと)。smoke が失敗したときに限り`uv run pytest -n auto`。
- コミットメッセージの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。
- マージは利用者の指示を待つ(PR を作って止まる)。
- 割り当て率は`MIN_ALLOCATION`(0.01)〜`MAX_ALLOCATION`(1.0)(`models.py`)。
- ブランチは`feature/load-rebalance`(設計書のコミット済み)。

## Review Focus

1. 週ごと・日ごとの担当で、owner が一部の週にしかいないとき、いない週は変えない(Task 1)。
2. 移し先がすでにそのタスクの担当のとき、移し先の率を残し、重複させない(Task 1)。
3. ダイアログを開いている間にタスクが消えた・変わったとき、適用は何も変えず通知して`False`を返す(Task 4)。
4. 率の入力が範囲外(0%・150%)でも、ダイアログが落ちず、エラーを出して適用できない(Task 3)。
5. 余力の候補が空のとき(稼働日がなく期間が決まらない)も、移し先・追加先の選択肢が名前順で出る(Task 2・3)。

---

## File Structure

- Create: `src/projectapp/rebalance.py` — 調整の計算(純粋関数)。`Edit`・`adjustable`・`tasks_of`・`rate_of`・`rate_text`・`has_varying_rate`・`apply_edits`・`preview`・`LoadChange`・`TaskChange`・`Preview`・`stats_text`・`load_text`・`task_text`・`edit_from_inputs`・`target_options`。
- Create: `src/projectapp/rebalance_dialog.py` — `open_rebalance_dialog`。
- Modify: `src/projectapp/dashboard_view.py` — `on_rebalance`と`調整…`ボタン。
- Modify: `src/projectapp/views.py` — `open_rebalance`・`apply_rebalance`と、`DashboardView`への接続。
- Create: `test/test_rebalance.py`、`test/test_rebalance_dialog.py`。
- Modify: `test/test_dashboard_view.py`、`test/test_views.py`。
- Modify: `.claude/spec/dashboard.md`、`docs/requests.md`、`docs/development.md`、設計書。

---

### Task 1: 調整を当てる(`apply_edits`)

**Files:**
- Create: `src/projectapp/rebalance.py`
- Create: `test/test_rebalance.py`

**Interfaces:**
- Consumes: `daily_crew.rows_of`・`WEEK_DAYS`、`crew_trial.replace_task`、`reassign.needs_review`・`reviewed_end`、`timeline.conversion_rate`・`crew_of`、`models.union_assignees`。
- Produces:
  - `Edit(task_id: str, kind: Literal["rate","move","add"], name: str | None = None, rate: float | None = None)`(frozen dataclass)
  - `adjustable(task: Task, owner: str) -> bool`、`tasks_of(project: Project, owner: str) -> list[Task]`
  - `rate_of(task: Task, owner: str) -> float | None`(owner の率が 1 つに決まるとき。週・日で違うときは None)、`rate_text(task, owner) -> str`、`has_varying_rate(task, owner) -> bool`
  - `apply_edits(project: Project, owner: str, edits: Sequence[Edit], holidays: dict[date, str], now: datetime) -> Project`(複製を返す。不正は`ValueError`)
  - `ADD_DEFAULT_RATE = 0.5`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_rebalance.py`を新規作成する:

```python
"""負荷の調整(rebalance)の計算の確認。"""

from datetime import date, datetime

import pytest

from projectapp.models import (
    Assignee,
    Member,
    Project,
    Status,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.rebalance import (
    Edit,
    adjustable,
    apply_edits,
    has_varying_rate,
    rate_of,
    rate_text,
    tasks_of,
)

NOW = datetime(2026, 10, 5, 8)


def task(task_id: str, rate: float = 0.6, **kw: object) -> Task:
    return Task(
        task_id.upper(),
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=13,
        assignees=[Assignee("田中", rate)],
        id=task_id,
        **kw,  # type: ignore[arg-type]
    )


def project(*tasks: Task, others: tuple[str, ...] = ("鈴木",)) -> Project:
    members = [Member("田中", 1.0), *(Member(name, 1.0) for name in others)]
    return Project(
        "P", base_date=date(2026, 10, 5), members=members, tasks=list(tasks)
    )


def crew(item: Task) -> list[tuple[str, float]]:
    return [(a.name, a.allocation) for a in item.assignees]


def rows(weeks: list[list[Assignee]]) -> list[list[tuple[str, float]]]:
    return [[(a.name, a.allocation) for a in week] for week in weeks]


def weekly_task() -> Task:
    weekly = [
        [Assignee("田中", 1.0)],
        [Assignee("田中", 0.5), Assignee("鈴木", 1.0)],
    ]
    daily = {
        1: [[Assignee("田中", 0.5), Assignee("鈴木", 1.0)] for _ in range(3)]
        + [[Assignee("鈴木", 1.0)] for _ in range(4)]
    }
    return Task(
        "W",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=40,
        weekly_crew=weekly,
        daily_crew=daily,
        assignees=union_assignees(weekly),
        id="w",
    )


def test_adjustable_needs_a_normal_unfinished_task_the_owner_has() -> None:
    assert adjustable(task("a"), "田中")
    assert not adjustable(task("a"), "鈴木")
    assert not adjustable(task("a", status=Status.DONE), "田中")
    assert not adjustable(task("a", kind=TaskKind.CHECKPOINT), "田中")


def test_tasks_of_lists_only_the_owners_adjustable_tasks_in_order() -> None:
    other = Task("他", assignees=[Assignee("鈴木")], id="o")
    p = project(task("a"), other, task("d", status=Status.DONE), task("b"))
    assert [t.id for t in tasks_of(p, "田中")] == ["a", "b"]


def test_a_rate_edit_sets_the_owners_rate_and_keeps_the_original() -> None:
    p = project(task("a"))
    result = apply_edits(p, "田中", [Edit("a", "rate", rate=0.4)], {}, NOW)
    assert crew(result.task_map()["a"]) == [("田中", 0.4)]
    assert crew(p.task_map()["a"]) == [("田中", 0.6)]


def test_a_move_replaces_the_owner_keeping_the_rate_or_using_the_given_one() -> None:
    p = project(task("a"), task("b"))
    result = apply_edits(
        p,
        "田中",
        [Edit("a", "move", "鈴木"), Edit("b", "move", "鈴木", rate=0.4)],
        {},
        NOW,
    )
    assert crew(result.task_map()["a"]) == [("鈴木", 0.6)]
    assert crew(result.task_map()["b"]) == [("鈴木", 0.4)]


def test_a_move_keeps_the_targets_rate_when_the_target_is_already_there() -> None:
    both = task("a")
    both.assignees = [Assignee("田中", 0.6), Assignee("鈴木", 0.3)]
    result = apply_edits(
        project(both), "田中", [Edit("a", "move", "鈴木", rate=0.9)], {}, NOW
    )
    assert crew(result.task_map()["a"]) == [("鈴木", 0.3)]


def test_an_add_appends_the_target_at_fifty_percent_and_skips_an_existing_one() -> None:
    both = task("b")
    both.assignees = [Assignee("田中", 0.6), Assignee("鈴木", 0.3)]
    p = project(task("a"), both)
    result = apply_edits(
        p, "田中", [Edit("a", "add", "鈴木"), Edit("b", "add", "鈴木")], {}, NOW
    )
    assert crew(result.task_map()["a"]) == [("田中", 0.6), ("鈴木", 0.5)]
    assert crew(result.task_map()["b"]) == [("田中", 0.6), ("鈴木", 0.3)]


@pytest.mark.parametrize(
    "edit",
    [
        Edit("zz", "rate", rate=0.5),  # ないタスク
        Edit("a", "rate"),  # 率がない
        Edit("a", "rate", rate=0.0),
        Edit("a", "rate", rate=1.5),
        Edit("a", "move", "佐藤"),  # メンバーにいない
        Edit("a", "move", "田中"),  # 自分
        Edit("a", "move"),  # 名前がない
        Edit("a", "add", "鈴木", rate=2.0),
        Edit("d", "rate", rate=0.5),  # 終了したタスク
    ],
)
def test_a_bad_edit_is_refused(edit: Edit) -> None:
    p = project(task("a"), task("d", status=Status.DONE))
    with pytest.raises(ValueError):
        apply_edits(p, "田中", [edit], {}, NOW)


def test_the_same_task_cannot_be_edited_twice() -> None:
    p = project(task("a"))
    with pytest.raises(ValueError, match="2 回"):
        apply_edits(
            p,
            "田中",
            [Edit("a", "rate", rate=0.5), Edit("a", "add", "鈴木")],
            {},
            NOW,
        )


def test_the_end_is_reviewed_when_the_rate_changes_after_some_progress() -> None:
    p = project(task("p", progress=50, status=Status.RUNNING), task("a"))
    result = apply_edits(
        p,
        "田中",
        [Edit("p", "rate", rate=0.3), Edit("a", "rate", rate=0.3)],
        {},
        NOW,
    )
    reviewed, plain = result.task_map()["p"], result.task_map()["a"]
    assert reviewed.planned_end is not None and reviewed.planned_end_manual
    assert not plain.planned_end_manual  # 進捗も実績もないタスクは見直さない


def test_a_rate_edit_applies_to_every_week_and_day_the_owner_appears() -> None:
    p = project(weekly_task(), others=("鈴木", "佐藤"))
    new = apply_edits(p, "田中", [Edit("w", "rate", rate=0.3)], {}, NOW).task_map()["w"]
    assert rows(new.weekly_crew) == [
        [("田中", 0.3)],
        [("田中", 0.3), ("鈴木", 1.0)],
    ]
    assert rows(new.daily_crew[1])[:3] == [[("田中", 0.3), ("鈴木", 1.0)]] * 3
    assert rows(new.daily_crew[1])[3:] == [[("鈴木", 1.0)]] * 4  # いない日は変えない
    assert crew(new) == [("田中", 0.3), ("鈴木", 1.0)]


def test_a_move_replaces_the_owner_in_every_week_and_day_and_keeps_the_union() -> None:
    p = project(weekly_task(), others=("鈴木", "佐藤"))
    new = apply_edits(p, "田中", [Edit("w", "move", "佐藤")], {}, NOW).task_map()["w"]
    assert rows(new.weekly_crew) == [
        [("佐藤", 1.0)],
        [("佐藤", 0.5), ("鈴木", 1.0)],
    ]
    assert [[a.name for a in day] for day in new.daily_crew[1]] == (
        [["佐藤", "鈴木"]] * 3 + [["鈴木"]] * 4
    )
    assert sorted(a.name for a in new.assignees) == ["佐藤", "鈴木"]


def test_an_add_appends_in_every_week_the_owner_appears_and_keeps_existing_ones() -> None:
    p = project(weekly_task(), others=("鈴木", "佐藤"))
    new = apply_edits(p, "田中", [Edit("w", "add", "鈴木")], {}, NOW).task_map()["w"]
    assert rows(new.weekly_crew) == [
        [("田中", 1.0), ("鈴木", 0.5)],  # 鈴木のいなかった週には、50% で足す
        [("田中", 0.5), ("鈴木", 1.0)],  # すでにいる週は変えない
    ]


def test_an_edit_does_not_touch_weeks_where_the_owner_is_absent() -> None:
    weekly = [[Assignee("鈴木", 1.0)], [Assignee("田中", 0.5)]]
    only_second = Task(
        "W",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=40,
        weekly_crew=weekly,
        assignees=union_assignees(weekly),
        id="w",
    )
    new = apply_edits(
        project(only_second), "田中", [Edit("w", "rate", rate=0.2)], {}, NOW
    ).task_map()["w"]
    assert rows(new.weekly_crew) == [[("鈴木", 1.0)], [("田中", 0.2)]]


def test_rate_helpers_report_a_single_rate_or_a_range() -> None:
    simple, weekly = task("a"), weekly_task()
    assert rate_of(simple, "田中") == 0.6 and rate_text(simple, "田中") == "60%"
    assert not has_varying_rate(simple, "田中")
    assert rate_of(weekly, "田中") is None
    assert rate_text(weekly, "田中") == "50〜100%"
    assert has_varying_rate(weekly, "田中")
    assert rate_text(simple, "鈴木") == "-"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_rebalance.py -q 2>&1 | tail -5`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.rebalance'`)

- [ ] **Step 3: 実装する**

`src/projectapp/rebalance.py`を新規作成する:

```python
"""負荷の調整(要望 145)。NiceGUI に依存しない純粋関数。

選んだ人(owner)の担当を、率の変更・他の人への移し替え・別の人の追加で調整した複製を作る。
週ごと・日ごとの担当を持つタスクは、owner が出てくる全週・全日に同じ操作を一括で当てる(いない週・日は変えない)。
"""

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from projectapp.crew_trial import replace_task
from projectapp.daily_crew import WEEK_DAYS, rows_of
from projectapp.models import (
    MAX_ALLOCATION,
    MIN_ALLOCATION,
    Assignee,
    Project,
    Status,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.reassign import needs_review, reviewed_end
from projectapp.timeline import conversion_rate, crew_of

ADD_DEFAULT_RATE = 0.5  # 足す人の割り当て率の既定(元の人の率は変えない)
RATE_EPSILON = 1e-9
Kind = Literal["rate", "move", "add"]


@dataclass(frozen=True)
class Edit:
    """1 タスクへの調整。rate: 新しい率 / move: 移し先(name)と移し先の率(rate。省くと元の率)
    / add: 足す人(name)と率(rate。省くと 50%)。"""

    task_id: str
    kind: Kind
    name: str | None = None
    rate: float | None = None


def adjustable(task: Task, owner: str) -> bool:
    """owner の調整の対象になるか。通常タスクで、終了しておらず、owner が担当しているもの。"""
    return (
        task.kind is TaskKind.NORMAL
        and task.status is not Status.DONE
        and owner in task.assignee_names
    )


def tasks_of(project: Project, owner: str) -> list[Task]:
    """owner の調整できるタスク(プロジェクトの並び順)。"""
    return [task for task in project.all_tasks() if adjustable(task, owner)]


def _rates_of(task: Task, owner: str) -> list[float]:
    weekly, daily = rows_of(task)
    crews = list(weekly)
    for days in daily.values():
        crews.extend(days)
    return [a.allocation for crew in crews for a in crew if a.name == owner]


def rate_of(task: Task, owner: str) -> float | None:
    """owner の割り当て率。週・日によって違う、またはいないときは None。"""
    rates = _rates_of(task, owner)
    if not rates or max(rates) - min(rates) >= RATE_EPSILON:
        return None
    return rates[0]


def has_varying_rate(task: Task, owner: str) -> bool:
    rates = _rates_of(task, owner)
    return bool(rates) and max(rates) - min(rates) >= RATE_EPSILON


def rate_text(task: Task, owner: str) -> str:
    """owner の今の割り当て率の表示。週・日によって違うときは`50〜100%`の範囲。"""
    rates = _rates_of(task, owner)
    if not rates:
        return "-"
    low, high = min(rates), max(rates)
    if high - low < RATE_EPSILON:
        return f"{low * 100:.0f}%"
    return f"{low * 100:.0f}〜{high * 100:.0f}%"


def _check_rate(rate: float | None, required: bool) -> None:
    if rate is None:
        if required:
            raise ValueError("割り当て率を入れてください")
        return
    if not MIN_ALLOCATION <= rate <= MAX_ALLOCATION:
        raise ValueError(
            f"割り当て率は{MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}%で入力してください"
        )


def _check(project: Project, owner: str, edit: Edit) -> Task:
    task = project.task_map().get(edit.task_id)
    if task is None:
        raise ValueError("タスクが見つかりません")
    if not adjustable(task, owner):
        raise ValueError(f"{task.name}は調整できません")
    if edit.kind == "rate":
        _check_rate(edit.rate, True)
    elif edit.kind in ("move", "add"):
        if edit.name is None or edit.name not in {m.name for m in project.members}:
            raise ValueError("メンバーを選んでください")
        if edit.name == owner:
            raise ValueError("同じ人には移せません")
        _check_rate(edit.rate, False)
    else:
        raise ValueError("調整の種類が正しくありません")
    return task


def _crew_edit(crew: list[Assignee], owner: str, edit: Edit) -> list[Assignee]:
    """1 つの担当の並び(1 週・1 日・タスク全体)に調整を当てる。owner がいない並びは変えない。"""
    copy = [Assignee(a.name, a.allocation) for a in crew]
    names = {a.name for a in crew}
    if owner not in names:
        return copy
    if edit.kind == "rate":
        assert edit.rate is not None
        return [
            Assignee(a.name, edit.rate if a.name == owner else a.allocation)
            for a in copy
        ]
    assert edit.name is not None
    if edit.kind == "add":
        if edit.name in names:
            return copy
        rate = ADD_DEFAULT_RATE if edit.rate is None else edit.rate
        return [*copy, Assignee(edit.name, rate)]
    moved: list[Assignee] = []
    for a in copy:
        if a.name != owner:
            moved.append(a)
        elif edit.name not in names:  # 移し先がすでにいるときは、いる側の率を残す
            moved.append(
                Assignee(edit.name, a.allocation if edit.rate is None else edit.rate)
            )
    return moved


def _edited(task: Task, owner: str, edit: Edit) -> Task:
    if not task.weekly_crew:
        return replace(task, assignees=_crew_edit(task.assignees, owner, edit))
    weekly, daily = rows_of(task)
    weekly = [_crew_edit(week, owner, edit) for week in weekly]
    daily = {
        number: [_crew_edit(day, owner, edit) for day in days]
        for number, days in daily.items()
    }
    for number, days in daily.items():
        if number < len(weekly) and len(days) == WEEK_DAYS:
            weekly[number] = union_assignees(days)
    return replace(
        task,
        weekly_crew=weekly,
        daily_crew=daily,
        assignees=union_assignees(weekly),
    )


def _reviewed(
    old: Task, new: Task, project: Project, holidays: dict[date, str], now: datetime
) -> Task:
    """換算率が変わるタスクの完了予定を、担当の付け替えと同じ規則で見直す(手で指定の完了予定にする)。"""
    old_rate, new_rate = conversion_rate(old, project), conversion_rate(new, project)
    if not needs_review(new, old_rate, new_rate):
        return new
    end = reviewed_end(
        new,
        old_rate,
        new_rate,
        project.daily_hours,
        project.work_start,
        holidays,
        now,
        crew_of(new.assignees, project.members),
    )
    if end is None:
        return new
    return replace(new, planned_end=end, planned_end_manual=True)


def apply_edits(
    project: Project,
    owner: str,
    edits: Sequence[Edit],
    holidays: dict[date, str],
    now: datetime,
) -> Project:
    """調整を当てた複製を返す(project は変えない)。正しくないときは ValueError。"""
    result = deepcopy(project)
    seen: set[str] = set()
    for edit in edits:
        if edit.task_id in seen:
            raise ValueError("同じタスクを 2 回調整できません")
        seen.add(edit.task_id)
        old = _check(result, owner, edit)
        new = _reviewed(old, _edited(old, owner, edit), result, holidays, now)
        replace_task(result, new)
    return result
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_rebalance.py -q 2>&1 | tail -5`
Expected: PASS(全件)。落ちたら、`weekly_task`・`project`の fixture と、実装の週・日の整合(`weekly[number] = union_assignees(days)`)を見直す。

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test -q && uvx ruff check -q
git add src/projectapp/rebalance.py test/test_rebalance.py
git commit -m "feat: 負荷の調整の計算(率の変更・移し替え・追加。週ごと・日ごとの担当は一括)を作る(要望 145)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 前後の比較(`preview`)・文言・入力の変換・選択肢

**Files:**
- Modify: `src/projectapp/rebalance.py`
- Modify: `test/test_rebalance.py`

**Interfaces:**
- Consumes: Task 1 の`Edit`・`apply_edits`・`tasks_of`、`dashboard.summarize_loads`・`summarize_backlog`・`LoadStats`・`Candidate`・`Period`・`PeriodKind`、`forecast.forecast_end`、`timeline.Schedule`・`effective_end`。
- Produces:
  - `LoadChange(name, before: LoadStats, after: LoadStats)`、`TaskChange(task_id, name, end_before, end_after, forecast_before, forecast_after, reviewed)`、`Preview(edited, loads, tasks, candidates)`(`review_count`プロパティ)
  - `preview(project, owner, edits, period, kind, now, holidays) -> Preview`
  - `stats_text(name: str, stats: LoadStats) -> str`、`load_text(change: LoadChange) -> str`、`task_text(change: TaskChange) -> str`
  - `edit_from_inputs(task_id, mode, name, percent, current) -> Edit | None`
  - `target_options(project, owner, candidates) -> dict[str, str]`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_rebalance.py`の import を次のとおりに直す(既存の import ブロックを置き換える):

```python
from datetime import date, datetime

import pytest

from projectapp.dashboard import Candidate, LoadStats, Period, PeriodKind
from projectapp.models import (
    Assignee,
    Member,
    Project,
    Status,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.rebalance import (
    Edit,
    LoadChange,
    TaskChange,
    adjustable,
    apply_edits,
    edit_from_inputs,
    has_varying_rate,
    load_text,
    preview,
    rate_of,
    rate_text,
    stats_text,
    target_options,
    task_text,
    tasks_of,
)

NOW = datetime(2026, 10, 5, 8)
PERIOD = Period(date(2026, 10, 5), date(2026, 10, 11))
```

(`NOW = …`の元の 1 行は消す。)ファイルの末尾に足す:

```python
def overloaded() -> Project:
    """田中が A・B(各 60%)を同時に持ち、4 日間 120%(割り当て超過)になる。"""
    return project(task("a"), task("b"))


def run(edits: list[Edit], p: Project | None = None):  # noqa: ANN201
    return preview(p or overloaded(), "田中", edits, PERIOD, PeriodKind.WEEK, NOW, {})


def test_a_rate_edit_clears_the_overload_and_delays_the_end() -> None:
    result = run([Edit("b", "rate", rate=0.4)])
    (change,) = result.loads
    assert change.name == "田中"
    assert (change.before.overload_days, change.before.peak) == (4, pytest.approx(1.2))
    assert (change.after.overload_days, change.after.peak) == (0, pytest.approx(1.0))
    (moved,) = result.tasks
    assert moved.end_before is not None and moved.end_after is not None
    assert moved.end_after > moved.end_before  # 率を下げると、終わりが遅くなる


def test_a_move_shifts_the_load_to_the_target_and_keeps_the_end() -> None:
    result = run([Edit("b", "move", "鈴木")])
    assert [c.name for c in result.loads] == ["田中", "鈴木"]
    owner, target = result.loads
    assert owner.after.overload_days == 0
    assert target.before.peak == 0.0 and target.after.peak == pytest.approx(0.6)
    (moved,) = result.tasks
    assert moved.end_after == moved.end_before  # 率が同じなので、終わりは変わらない


def test_an_add_splits_the_load_and_brings_the_end_forward() -> None:
    result = run([Edit("b", "add", "鈴木")])
    (moved,) = result.tasks
    assert moved.end_before is not None and moved.end_after is not None
    assert moved.end_after < moved.end_before
    assert [c.name for c in result.loads] == ["田中", "鈴木"]


def test_a_preview_changes_nothing_and_counts_reviews() -> None:
    p = project(task("p", progress=50, status=Status.RUNNING), task("a"))
    result = run([Edit("p", "rate", rate=0.3)], p)
    assert result.review_count == 1 and result.tasks[0].reviewed
    assert crew(p.task_map()["p"]) == [("田中", 0.6)]  # 元は変わらない


def test_a_preview_reports_the_candidates_after_the_edit() -> None:
    result = run([Edit("b", "move", "鈴木")])
    assert {c.name for c in result.candidates} == {"田中", "鈴木"}


def test_a_preview_passes_on_a_bad_edit() -> None:
    with pytest.raises(ValueError):
        run([Edit("zz", "rate", rate=0.5)])


def test_the_texts_show_before_and_after() -> None:
    before, after = LoadStats(0.96, 1.2, 4), LoadStats(0.88, 1.0, 0)
    assert stats_text("田中", before) == "田中: 平均 96% / 最大 120% / 割り当て超過 4 日"
    assert (
        load_text(LoadChange("田中", before, after))
        == "田中: 平均 96% → 88% / 最大 120% → 100% / 割り当て超過 4 日 → 0 日"
    )
    plain = TaskChange(
        "b", "B", datetime(2026, 10, 8, 11, 10), datetime(2026, 10, 9, 15, 30),
        None, None, False,
    )  # fmt: skip
    assert task_text(plain) == "B: 完了予定 10/08 11:10 → 10/09 15:30"
    full = TaskChange(
        "b", "B", datetime(2026, 10, 8, 11, 10), None,
        datetime(2026, 10, 9, 9, 0), datetime(2026, 10, 10, 9, 0), True,
    )  # fmt: skip
    assert task_text(full) == (
        "B: 完了予定 10/08 11:10 → - / 完了見込み 10/09 09:00 → 10/10 09:00(完了予定を見直し)"
    )


def test_edit_from_inputs_builds_an_edit_only_for_a_real_change() -> None:
    assert edit_from_inputs("a", "none", None, None, 0.6) is None
    assert edit_from_inputs("a", "rate", None, None, 0.6) is None
    assert edit_from_inputs("a", "rate", None, 60.0, 0.6) is None  # 今と同じ
    assert edit_from_inputs("a", "rate", None, 40.0, 0.6) == Edit("a", "rate", rate=0.4)
    assert edit_from_inputs("a", "move", None, None, 0.6) is None  # 移し先がない
    assert edit_from_inputs("a", "move", "鈴木", None, 0.6) == Edit("a", "move", "鈴木")
    assert edit_from_inputs("a", "add", "鈴木", 30.0, 0.6) == Edit("a", "add", "鈴木", 0.3)


def test_target_options_rank_by_spare_hours_and_fall_back_to_the_member_order() -> None:
    p = project(task("a"), others=("鈴木", "佐藤"))
    ranked = target_options(
        p, "田中", [Candidate("佐藤", 20.0, 1.0), Candidate("鈴木", 6.5, 1.0)]
    )
    assert list(ranked) == ["佐藤", "鈴木"]  # 余力の多い順(田中は除く)
    assert ranked["佐藤"] == "佐藤(余力 20.0h)"
    assert list(target_options(p, "田中", [])) == ["鈴木", "佐藤"]  # 候補が空のとき
    assert target_options(p, "田中", [])["鈴木"] == "鈴木"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_rebalance.py -q 2>&1 | tail -5`
Expected: FAIL(`ImportError: cannot import name 'LoadChange'`)

- [ ] **Step 3: 実装する**

`src/projectapp/rebalance.py`の import を次のとおりに直す(先頭の import ブロックを置き換える):

```python
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from projectapp.crew_trial import replace_task
from projectapp.daily_crew import WEEK_DAYS, rows_of
from projectapp.dashboard import (
    Candidate,
    LoadStats,
    Period,
    PeriodKind,
    summarize_backlog,
    summarize_loads,
)
from projectapp.forecast import forecast_end
from projectapp.models import (
    MAX_ALLOCATION,
    MIN_ALLOCATION,
    Assignee,
    Project,
    Status,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.reassign import needs_review, reviewed_end
from projectapp.timeline import Schedule, conversion_rate, crew_of, effective_end
```

ファイルの末尾に足す:

```python
@dataclass(frozen=True)
class LoadChange:
    name: str
    before: LoadStats
    after: LoadStats


@dataclass(frozen=True)
class TaskChange:
    task_id: str
    name: str
    end_before: datetime | None  # 完了予定
    end_after: datetime | None
    forecast_before: datetime | None  # 完了見込み
    forecast_after: datetime | None
    reviewed: bool  # 完了予定を見直した


@dataclass(frozen=True)
class Preview:
    edited: Project
    loads: list[LoadChange]
    tasks: list[TaskChange]
    candidates: list[Candidate]  # 調整後の余力(余力の多い順)

    @property
    def review_count(self) -> int:
        return sum(1 for change in self.tasks if change.reviewed)


def preview(
    project: Project,
    owner: str,
    edits: Sequence[Edit],
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
) -> Preview:
    """調整の前後の負荷(owner と、移し先・追加先)・完了予定・完了見込み・余力。何も変えない。"""
    edited = apply_edits(project, owner, edits, holidays, now)
    before = summarize_loads(project, period, holidays)
    after = summarize_loads(edited, period, holidays)
    involved = list(
        dict.fromkeys(
            [owner, *(e.name for e in edits if e.name is not None and e.kind != "rate")]
        )
    )
    loads = [LoadChange(n, before[n], after[n]) for n in involved if n in before]
    schedule_before = Schedule(project, holidays)
    schedule_after = Schedule(edited, holidays)
    changes: list[TaskChange] = []
    for edit in edits:
        old, new = project.task_map()[edit.task_id], edited.task_map()[edit.task_id]
        found_before = forecast_end(old, project, holidays, now, schedule_before)
        found_after = forecast_end(new, edited, holidays, now, schedule_after)
        changes.append(
            TaskChange(
                edit.task_id,
                new.name,
                effective_end(old, project, holidays, schedule_before),
                effective_end(new, edited, holidays, schedule_after),
                None if found_before is None else found_before.end,
                None if found_after is None else found_after.end,
                new.planned_end_manual and new.planned_end != old.planned_end,
            )
        )
    return Preview(
        edited,
        loads,
        changes,
        summarize_backlog(edited, period, kind, now, holidays).candidates,
    )


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def stats_text(name: str, stats: LoadStats) -> str:
    return (
        f"{name}: 平均 {_percent(stats.average)} / 最大 {_percent(stats.peak)}"
        f" / 割り当て超過 {stats.overload_days} 日"
    )


def load_text(change: LoadChange) -> str:
    before, after = change.before, change.after
    return (
        f"{change.name}: 平均 {_percent(before.average)} → {_percent(after.average)}"
        f" / 最大 {_percent(before.peak)} → {_percent(after.peak)}"
        f" / 割り当て超過 {before.overload_days} 日 → {after.overload_days} 日"
    )


def _moment(value: datetime | None) -> str:
    return "-" if value is None else f"{value:%m/%d %H:%M}"


def task_text(change: TaskChange) -> str:
    text = (
        f"{change.name}: 完了予定 {_moment(change.end_before)} → {_moment(change.end_after)}"
    )
    if change.forecast_before is not None or change.forecast_after is not None:
        text += (
            f" / 完了見込み {_moment(change.forecast_before)}"
            f" → {_moment(change.forecast_after)}"
        )
    if change.reviewed:
        text += "(完了予定を見直し)"
    return text


def edit_from_inputs(
    task_id: str,
    mode: Literal["none", "rate", "move", "add"],
    name: str | None,
    percent: float | None,
    current: float | None,
) -> Edit | None:
    """1 行の入力(モード・相手・率[%])から調整を作る。変更にならないとき(そのまま・相手がない・今と同じ率)は None。"""
    rate = None if percent is None else percent / 100
    if mode == "rate":
        if rate is None or (current is not None and abs(rate - current) < RATE_EPSILON):
            return None
        return Edit(task_id, "rate", rate=rate)
    if mode == "move" and name is not None:
        return Edit(task_id, "move", name, rate)
    if mode == "add" and name is not None:
        return Edit(task_id, "add", name, rate)
    return None


def target_options(
    project: Project, owner: str, candidates: Sequence[Candidate]
) -> dict[str, str]:
    """移し先・追加先の選択肢(名前 → 表示)。余力の多い順で余力(時間)を添え、候補にいない人は名前だけで後ろに並べる。owner は除く。"""
    spare = {c.name: c.spare_hours for c in candidates}
    names = [n for n in spare if n != owner]
    names += [m.name for m in project.members if m.name != owner and m.name not in spare]
    return {n: (f"{n}(余力 {spare[n]:.1f}h)" if n in spare else n) for n in names}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_rebalance.py -q 2>&1 | tail -5`
Expected: PASS。`test_the_texts_show_before_and_after`の`# fmt: skip`が`ruff format`で外れる場合は、改行位置を直して良い(期待する文字列は変えない)。

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test -q && uvx ruff check -q
git add src/projectapp/rebalance.py test/test_rebalance.py
git commit -m "feat: 負荷の調整の前後の比較・文言・入力の変換・移し先の選択肢を作る(要望 145)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 負荷の調整ダイアログ

**Files:**
- Create: `src/projectapp/rebalance_dialog.py`
- Create: `test/test_rebalance_dialog.py`

**Interfaces:**
- Consumes: Task 1・2 の`Edit`・`tasks_of`・`rate_of`・`rate_text`・`has_varying_rate`・`preview`・`stats_text`・`load_text`・`task_text`・`edit_from_inputs`・`target_options`、`dashboard.summarize_backlog`・`summarize_loads`、`remaining.remaining_hours`(`remaining_hours(task, project, holidays, now) -> float`)、`forms.disposable`。
- Produces: `open_rebalance_dialog(owner: str, project: Project, period: Period, kind: PeriodKind, now: datetime, holidays: dict[date, str], on_apply: Callable[[list[Edit]], object]) -> None`。マーカー: `rebalance-title`・`rebalance-empty`・`rebalance-row-<task_id>`・`rebalance-mode-<id>`・`rebalance-rate-<id>`・`rebalance-target-<id>`・`rebalance-reset-<id>`・`rebalance-note-<id>`・`rebalance-load-<名前>`・`rebalance-task-<id>`・`rebalance-review`・`rebalance-error`・`rebalance-apply`・`rebalance-cancel`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_rebalance_dialog.py`を新規作成する:

```python
"""負荷の調整ダイアログの確認。"""

from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import Period, PeriodKind
from projectapp.models import Assignee, Member, Project, Task, union_assignees
from projectapp.rebalance import Edit
from projectapp.rebalance_dialog import open_rebalance_dialog

NOW = datetime(2026, 10, 5, 8)
PERIOD = Period(date(2026, 10, 5), date(2026, 10, 11))


def make(task_id: str, owner: str = "田中", rate: float = 0.6) -> Task:
    return Task(
        task_id.upper(),
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=13,
        assignees=[Assignee(owner, rate)],
        id=task_id,
    )


def sample() -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=[make("a"), make("b"), make("c", "鈴木", 0.5)],
    )


def mount(project: Project, applied: list[list[Edit]]) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_rebalance_dialog(
                "田中", project, PERIOD, PeriodKind.WEEK, NOW, {}, applied.append
            ),
        ).mark("open")


async def open_dialog(user: User) -> None:
    await user.open("/")
    user.find("open").click()


def element(user: User, marker: str):  # noqa: ANN202
    return user.find(marker=marker).elements.pop()


async def test_the_dialog_lists_the_owners_tasks_and_the_current_load(
    user: User,
) -> None:
    mount(sample(), [])
    await open_dialog(user)
    assert element(user, "rebalance-title").text == "負荷の調整: 田中"
    await user.should_see(marker="rebalance-row-a")
    await user.should_see(marker="rebalance-row-b")
    await user.should_not_see(marker="rebalance-row-c")  # 他の人のタスク
    assert element(user, "rebalance-load-田中").text == (
        "田中: 平均 96% / 最大 120% / 割り当て超過 4 日"
    )
    assert not element(user, "rebalance-apply").enabled  # 変更がないうちは押せない


async def test_a_rate_change_shows_the_result_and_applies(user: User) -> None:
    applied: list[list[Edit]] = []
    mount(sample(), applied)
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("rate")
        element(user, "rebalance-rate-b").set_value(40)
    assert "割り当て超過 4 日 → 0 日" in element(user, "rebalance-load-田中").text
    assert "完了予定" in element(user, "rebalance-task-b").text
    assert element(user, "rebalance-apply").enabled
    user.find(marker="rebalance-apply").click()
    assert applied == [[Edit("b", "rate", rate=0.4)]]


async def test_a_move_lists_candidates_with_spare_hours_and_shows_both_loads(
    user: User,
) -> None:
    applied: list[list[Edit]] = []
    mount(sample(), applied)
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("move")
    options = element(user, "rebalance-target-b").options
    assert options["鈴木"].startswith("鈴木(余力 ")
    assert "田中" not in options  # 自分には移せない
    with user.client:
        element(user, "rebalance-target-b").set_value("鈴木")
    assert "→" in element(user, "rebalance-load-鈴木").text
    user.find(marker="rebalance-apply").click()
    (edits,) = applied
    assert [(e.task_id, e.kind, e.name) for e in edits] == [("b", "move", "鈴木")]


async def test_a_move_without_a_target_is_not_a_change(user: User) -> None:
    mount(sample(), [])
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("move")
    assert not element(user, "rebalance-apply").enabled


async def test_reset_puts_a_row_back_and_disables_apply(user: User) -> None:
    mount(sample(), [])
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("rate")
        element(user, "rebalance-rate-b").set_value(40)
    assert element(user, "rebalance-apply").enabled
    user.find(marker="rebalance-reset-b").click()
    assert element(user, "rebalance-mode-b").value == "none"
    assert not element(user, "rebalance-apply").enabled


async def test_an_out_of_range_rate_shows_an_error_and_cannot_be_applied(
    user: User,
) -> None:
    mount(sample(), [])
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("rate")
        element(user, "rebalance-rate-b").set_value(150)
    assert "割り当て率は" in element(user, "rebalance-error").text
    assert not element(user, "rebalance-apply").enabled
    with user.client:
        element(user, "rebalance-rate-b").set_value(0)
    assert "割り当て率は" in element(user, "rebalance-error").text


async def test_the_dialog_says_when_there_is_nothing_to_adjust(user: User) -> None:
    project = Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=[make("c", "鈴木", 0.5)],
    )
    mount(project, [])
    await open_dialog(user)
    await user.should_see(marker="rebalance-empty")


async def test_a_weekly_task_is_marked_as_applying_to_every_week(user: User) -> None:
    weekly = [
        [Assignee("田中", 1.0)],
        [Assignee("田中", 0.5), Assignee("鈴木", 1.0)],
    ]
    varying = Task(
        "W",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=40,
        weekly_crew=weekly,
        assignees=union_assignees(weekly),
        id="w",
    )
    project = Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=[varying],
    )
    mount(project, [])
    await open_dialog(user)
    note = element(user, "rebalance-note-w").text
    assert "全週に適用" in note and "50〜100%" in note and "上書き" in note
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_rebalance_dialog.py -q 2>&1 | tail -5`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.rebalance_dialog'`)

- [ ] **Step 3: 実装する**

`src/projectapp/rebalance_dialog.py`を新規作成する:

```python
"""負荷の調整ダイアログ(要望 145)。選んだ人のタスクごとに、率の変更・移す・追加を選び、変えるたびに結果を見せる。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from nicegui import ui

from projectapp.dashboard import Period, PeriodKind, summarize_backlog, summarize_loads
from projectapp.forms import disposable
from projectapp.models import Project, Task
from projectapp.rebalance import (
    ADD_DEFAULT_RATE,
    Edit,
    edit_from_inputs,
    has_varying_rate,
    load_text,
    preview,
    rate_of,
    rate_text,
    stats_text,
    target_options,
    task_text,
    tasks_of,
)
from projectapp.remaining import remaining_hours

Mode = Literal["none", "rate", "move", "add"]
MODES = {"none": "そのまま", "rate": "率を変える", "move": "移す", "add": "追加"}


@dataclass
class _Row:
    mode: Mode = "none"
    name: str | None = None
    percent: float | None = None


def open_rebalance_dialog(
    owner: str,
    project: Project,
    period: Period,
    kind: PeriodKind,
    now: datetime,
    holidays: dict[date, str],
    on_apply: Callable[[list[Edit]], object],
) -> None:
    """`適用`を押すと、選んだ調整の一覧を`on_apply`に渡して閉じる。"""
    tasks = tasks_of(project, owner)
    options = target_options(
        project, owner, summarize_backlog(project, period, kind, now, holidays).candidates
    )
    state = {task.id: _Row() for task in tasks}

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[44rem] max-w-full"):
        ui.label(f"負荷の調整: {owner}").classes("text-h6").mark("rebalance-title")
        if not tasks:
            ui.label("調整できるタスクがありません").classes("text-grey").mark(
                "rebalance-empty"
            )
        rows_box = ui.column().classes("w-full gap-2")
        loads_box = ui.column().classes("w-full gap-0")
        tasks_box = ui.column().classes("w-full gap-0")
        error = ui.label("").classes("text-negative").mark("rebalance-error")
        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark(
                "rebalance-cancel"
            )
            apply_button = ui.button("適用").mark("rebalance-apply")
            apply_button.set_enabled(False)

        def edits_now() -> list[Edit]:
            found: list[Edit] = []
            for task in tasks:
                row = state[task.id]
                edit = edit_from_inputs(
                    task.id, row.mode, row.name, row.percent, rate_of(task, owner)
                )
                if edit is not None:
                    found.append(edit)
            return found

        def update() -> None:
            edits = edits_now()
            loads_box.clear()
            tasks_box.clear()
            error.set_text("")
            apply_button.set_enabled(False)
            if not edits:
                current = summarize_loads(project, period, holidays).get(owner)
                if current is not None:
                    with loads_box:
                        ui.label(stats_text(owner, current)).mark(
                            f"rebalance-load-{owner}"
                        )
                return
            try:
                result = preview(project, owner, edits, period, kind, now, holidays)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            with loads_box:
                for change in result.loads:
                    better = change.after.overload_days < change.before.overload_days
                    worse = change.after.overload_days > change.before.overload_days
                    ui.label(load_text(change)).classes(
                        "text-positive" if better else "text-negative" if worse else ""
                    ).mark(f"rebalance-load-{change.name}")
            with tasks_box:
                for change in result.tasks:
                    ui.label(task_text(change)).classes("text-caption").mark(
                        f"rebalance-task-{change.task_id}"
                    )
                if result.review_count:
                    ui.label(
                        f"完了予定を見直したタスク {result.review_count} 件"
                        "(手で指定の完了予定になります)"
                    ).classes("text-caption text-grey").mark("rebalance-review")
            apply_button.set_enabled(True)

        def build_row(task: Task) -> None:
            row = state[task.id]
            current = rate_of(task, owner)
            varying = has_varying_rate(task, owner)
            with rows_box:
                with ui.column().classes("w-full gap-1").mark(f"rebalance-row-{task.id}"):
                    ui.label(
                        f"{task.name}(残り {remaining_hours(task, project, holidays, now):.1f}h"
                        f" / 率 {rate_text(task, owner)})"
                    ).classes("ellipsis")
                    if task.weekly_crew:
                        note = "全週に適用"
                        if varying:
                            note += f"(今の率は{rate_text(task, owner)}。率を変えると全週が同じ率に上書きされます)"
                        ui.label(note).classes("text-caption text-grey").mark(
                            f"rebalance-note-{task.id}"
                        )
                    with ui.row().classes("items-center gap-2"):
                        mode = ui.toggle(MODES, value="none").mark(
                            f"rebalance-mode-{task.id}"
                        )
                        percent = (
                            ui.number("率(%)", min=1, max=100, precision=0)
                            .classes("w-24")
                            .mark(f"rebalance-rate-{task.id}")
                        )
                        target = (
                            ui.select(options, label="相手", value=None)
                            .classes("w-56")
                            .mark(f"rebalance-target-{task.id}")
                        )
                        reset = (
                            ui.button("戻す", on_click=lambda: mode.set_value("none"))
                            .props("flat dense")
                            .mark(f"rebalance-reset-{task.id}")
                        )
                    percent.set_visibility(False)
                    target.set_visibility(False)
                    reset.set_visibility(False)

            def on_mode(event: object) -> None:
                chosen: Mode = getattr(event, "value", "none")
                row.mode = chosen
                row.name = None if chosen in ("none", "rate") else row.name
                shown = chosen != "none"
                percent.set_visibility(shown)
                target.set_visibility(chosen in ("move", "add"))
                reset.set_visibility(shown)
                if chosen == "none":
                    percent.set_value(None)
                    target.set_value(None)
                    row.percent = None
                elif chosen == "add":
                    percent.set_value(ADD_DEFAULT_RATE * 100)
                else:
                    percent.set_value(None if current is None else current * 100)
                update()

            def on_percent(event: object) -> None:
                value = getattr(event, "value", None)
                row.percent = None if value is None else float(value)
                update()

            def on_target(event: object) -> None:
                row.name = getattr(event, "value", None)
                update()

            mode.on_value_change(on_mode)
            percent.on_value_change(on_percent)
            target.on_value_change(on_target)

        for task in tasks:
            build_row(task)
        update()

        def apply() -> None:
            edits = edits_now()
            dialog.close()
            on_apply(edits)

        apply_button.on_click(apply)
    dialog.open()
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_rebalance_dialog.py -q 2>&1 | tail -8`
Expected: PASS。落ちたときの確認先: ①`ui.toggle`の`set_value`が`on_value_change`を呼ぶか(呼ばれないなら、`mode.on_value_change`ではなく`mode.on("update:model-value", ...)`の形は使わず、テスト側を`with user.client`の中で呼んでいるか確かめる)。②`ui.select`の`options`が辞書で返るか(`ui.select(options_dict)`では`.options`が辞書。違う型なら、テストの添字アクセスをその型に合わせる)。③`rebalance-load-田中`が、更新のたびに作り直されるので、`element()`で取り直しているか。

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test -q && uvx ruff check -q && uvx ty check src 2>&1 | tail -1
git add src/projectapp/rebalance_dialog.py test/test_rebalance_dialog.py
git commit -m "feat: 負荷の調整ダイアログを作る(要望 145)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ダッシュボードの入口と適用(元に戻す 1 ステップ)

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`__init__`の引数・`load_row`)
- Modify: `src/projectapp/views.py`(`DashboardView`の生成:675 付近、`add_crew_from_dashboard`の近くにメソッドを足す)
- Modify: `test/test_dashboard_view.py`・`test/test_views.py`

**Interfaces:**
- Consumes: Task 1〜3 の`Edit`・`apply_edits`・`open_rebalance_dialog`、`crew_trial.replace_task`(views は import 済み)、`MainView.after_edit`・`warn_overallocation`・`refresh_dashboard`・`now`・`undo`。
- Produces: `DashboardView(..., on_rebalance: Callable[[str], object] | None = None)`、マーカー`dashboard-rebalance-<名前>`、`MainView.open_rebalance(owner: str) -> None`、`MainView.apply_rebalance(owner: str, edits: Sequence[Edit]) -> bool`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py`の`mount_assign`の近く(`unassigned_sample`のテスト群の後)に足す:

```python
def mount_rebalance(picked: list[str]) -> list[DashboardView]:
    views: list[DashboardView] = []

    @ui.page("/")
    def index() -> None:
        view = DashboardView(lambda: None, lambda kind: None, on_rebalance=picked.append)
        views.append(view)
        view.build()

    return views


async def test_the_rebalance_button_is_shown_only_for_an_overloaded_member(
    user: User,
) -> None:
    picked: list[str] = []
    views = mount_rebalance(picked)
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-rebalance-田中")  # 割り当て超過 2 日
    await user.should_not_see(marker="dashboard-rebalance-佐藤")  # 超過なし
    user.find(marker="dashboard-rebalance-田中").click()
    assert picked == ["田中"]


async def test_the_rebalance_button_is_hidden_without_a_handler(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    await user.should_not_see(marker="dashboard-rebalance-田中")


async def test_the_rebalance_button_is_hidden_while_editing_the_cards(
    user: User,
) -> None:
    views = mount_rebalance([])
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-rebalance-田中")
    views[0].edit_mode = True
    views[0].cards.refresh()
    await asyncio.sleep(0.3)  # refresh は遅延実行
    await user.should_not_see(marker="dashboard-rebalance-田中")
```

`test/test_views.py`の末尾に足す(足りない import があれば、同じファイルの import の並びに足す: `from datetime import date, datetime`・`from projectapp.dashboard import PeriodKind`・`from projectapp.models import Assignee, Member, Task`・`from projectapp.rebalance import Edit`):

```python
def rebalance_task(task_id: str) -> Task:
    return Task(
        task_id.upper(),
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=13,
        assignees=[Assignee("田中", 0.6)],
        id=task_id,
    )


async def open_rebalance_view(user: User, tmp_path: Path) -> MainView:
    view = await open_members_view(user, tmp_path)
    view.now = lambda: datetime(2026, 10, 5, 8)
    view.project.base_date = date(2026, 10, 5)
    view.project.members = [Member("田中", 1.0), Member("鈴木", 1.0)]
    view.project.tasks = [rebalance_task("a"), rebalance_task("b")]
    with view.client:
        view.after_edit()  # ここまでを確定した状態にする
    return view


async def test_apply_rebalance_changes_the_tasks_as_one_undo_step(
    user: User, tmp_path: Path
) -> None:
    view = await open_rebalance_view(user, tmp_path)
    with view.client:
        assert view.apply_rebalance("田中", [Edit("b", "move", "鈴木")]) is True
    assert view.project.task_map()["b"].assignee_names == ["鈴木"]
    assert view.project.task_map()["a"].assignee_names == ["田中"]
    assert view.is_dirty()
    with view.client:
        view.undo()
    assert view.project.task_map()["b"].assignee_names == ["田中"]


async def test_apply_rebalance_refuses_a_task_that_changed(
    user: User, tmp_path: Path
) -> None:
    view = await open_rebalance_view(user, tmp_path)
    with view.client:
        done = view.apply_rebalance("田中", [Edit("zz", "rate", rate=0.5)])
    assert done is False
    assert view.project.task_map()["b"].assignee_names == ["田中"]


async def test_open_rebalance_opens_the_dialog_for_the_member(
    user: User, tmp_path: Path
) -> None:
    view = await open_rebalance_view(user, tmp_path)
    view.dashboard_kind = PeriodKind.WEEK
    with view.client:
        view.open_rebalance("田中")
    await user.should_see(marker="rebalance-title")


async def test_open_rebalance_does_nothing_outside_the_dashboard(
    user: User, tmp_path: Path
) -> None:
    view = await open_rebalance_view(user, tmp_path)
    with view.client:
        view.open_rebalance("田中")
    await user.should_not_see(marker="rebalance-title")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_view.py test/test_views.py -q -k "rebalance" 2>&1 | tail -8`
Expected: FAIL(`TypeError: ... unexpected keyword argument 'on_rebalance'`・`AttributeError: ... apply_rebalance`)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_view.py`:

- `DashboardView.__init__`の引数の末尾(`on_try_on_gantt`の次)に足す:

```python
        on_rebalance: Callable[[str], object] | None = None,
```

- `__init__`の本体の、`self.on_try_on_gantt = on_try_on_gantt`の次に足す:

```python
        self.on_rebalance = on_rebalance
```

- `load_row`の、`ui.label(f"平均 … 割り当て超過 …").…mark(f"dashboard-load-{name}")`の直後(同じ`with ui.row()`の中)に足す:

```python
            handler = self.on_rebalance
            if (
                over
                and handler is not None
                and not self.edit_mode
                and self.data is not None
                and self.data.cross is None
            ):
                ui.button(
                    "調整…", on_click=lambda _=None, n=name: handler(n)
                ).props("flat dense size=sm").style("flex: none").mark(
                    f"dashboard-rebalance-{name}"
                )
```

`src/projectapp/views.py`:

- import を足す(既存の import の並びに合わせる): `from projectapp.rebalance import Edit, apply_edits`・`from projectapp.rebalance_dialog import open_rebalance_dialog`。`Sequence`が未 import なら`from collections.abc import Sequence`。
- `DashboardView`の生成の`on_add_crew=self.add_crew_from_dashboard,`の次に足す:

```python
            on_rebalance=self.open_rebalance,
```

- `add_crew_to_warning`の次にメソッドを足す:

```python
    def open_rebalance(self, owner: str) -> None:
        """ダッシュボードの`調整…`。その人の担当を調整するダイアログを開く(要望 145)。"""
        if self.dashboard_kind is None:
            return
        now = self.now()
        period = period_for(
            self.dashboard_kind,
            now.date(),
            self.project,
            self.holidays,
            self.dashboard_custom,
        )
        open_rebalance_dialog(
            owner,
            self.project,
            period,
            self.dashboard_kind,
            now,
            self.holidays,
            lambda edits: self.apply_rebalance(owner, edits),
        )

    def apply_rebalance(self, owner: str, edits: Sequence[Edit]) -> bool:
        """選んだ調整を、元に戻す 1 ステップで適用する(要望 145)。ダイアログを開いている間にタスクが変わったときは、何も変えず通知して False。"""
        try:
            edited = apply_edits(self.project, owner, edits, self.holidays, self.now())
        except ValueError:
            ui.notify("タスクが変わったため、調整しませんでした", type="warning")
            self.refresh_dashboard(sync_field=False)
            return False
        changed = [edited.task_map()[edit.task_id] for edit in edits]
        for task in changed:
            replace_task(self.project, task)
        self.after_edit()
        self.warn_overallocation(*changed)
        self.refresh_dashboard(sync_field=False)
        return True
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_view.py test/test_views.py test/test_rebalance.py test/test_rebalance_dialog.py -q -n auto 2>&1 | tail -4`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test -q && uvx ruff check -q && uvx ty check src 2>&1 | tail -1
git add src test
git commit -m "feat: ダッシュボードの割り当て超過の人から、負荷の調整を開いて適用できるようにする(要望 145)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 文書・最終確認・PR

**Files:**
- Modify: `.claude/spec/dashboard.md`、`docs/requests.md`、`docs/development.md`、`docs/superpowers/specs/2026-11-17-load-rebalance-design.md`

- [ ] **Step 1: 設計書を実装に合わせて直す**

`docs/superpowers/specs/2026-11-17-load-rebalance-design.md`を次のとおりに直す:

- 画面の入口の`マーカーは\`dashboard-rebalance-<人の番号>\``を`マーカーは\`dashboard-rebalance-<名前>\``に直す。
- 対象と対象外の、`調整できない(行に理由を出し、操作を無効にする): まとめ・…`の段落を、`調整できないタスク(まとめ・プロジェクト参照・チェックポイント・終了したタスク)は、その人の担当として負荷に数えない・調整しても影響しないため、一覧に出さない。`に直す。
- 週ごと・日ごとの担当の`追加: 全週・全日に、足す人を足す(すでにいる週・日は変えない)。`を`追加: その人が出てくる全週・全日に、足す人を足す(その人がいない週・日、足す人がすでにいる週・日は変えない)。`に直す。
- 適用の`編集後に\`担当\`が空になるタスク…作れない(…)。`を`率は 1〜100% の範囲だけ許す(範囲外は\`ValueError\`。画面ではエラーを出して\`適用\`を押せない)。移す・追加では、担当が空になることはない。`に直す。
- 設計書の末尾の`## 未決`の`なし。…`は変えない。

- [ ] **Step 2: 仕様を書き足す**

`.claude/spec/dashboard.md`の、`人ごとの負荷`と`負荷の日ごとの推移`の人の扱い(要望 125)の項の次に、次の項を足す:

```markdown
- 負荷の調整(要望 145): `人ごとの負荷`の、割り当て超過の人の行に`調整…`ボタンを出す(全プロジェクトのオン・`カードを編集`中・ハンドラなしでは出さない)。押すと`負荷の調整`ダイアログを開く(カードの期間で計算)。その人が担当する、終了していない通常タスクごとに、`そのまま`・`率を変える`・`移す`・`追加`を選ぶ。移す・追加の相手は、余力の多い順(要望 131 の余力。候補が空のときはメンバーの順)に余力を添えて並べ、足す人の率の既定は 50%。割り当て率は 1〜100%。週ごと・日ごとの担当のタスクは、その人が出てくる全週・全日に同じ操作を一括で当てる(率を変えると全週が同じ率に上書きされる)。変えるたびに、関わる人(元の人と移し先・追加先)の負荷(平均・最大・割り当て超過の日数)と、変えたタスクの完了予定・完了見込みを、変更前→変更後で出す。率が変わって見直しが要るタスクは、担当の付け替えと同じ規則で完了予定を見直し、手で指定の完了予定にする(件数を出す)。`適用`は元に戻す 1 ステップ。ダイアログを開いている間にタスクが変わったときは、何も変えず通知する。計算は`rebalance.py`、画面は`rebalance_dialog.py`。ファイル形式は変えない
```

`docs/development.md`のモジュールの表(`crew_trial.py`・`forecast.py`の行の近く)に足す:

```markdown
| `rebalance.py` | 負荷の調整(要望 145)。`Edit`(率の変更・移す・追加)・`apply_edits`(複製に当てる。週ごと・日ごとの担当は一括。完了予定の見直しを含む)・`preview`(前後の負荷・完了予定・見込み・余力)・`edit_from_inputs`・`target_options`・文言の関数。NiceGUI に依存しない |
| `rebalance_dialog.py` | `負荷の調整`ダイアログ(`open_rebalance_dialog`)。ダッシュボードの`調整…`から開く |
```

`docs/requests.md`の要望 145 の`### 決めたい点`の見出しを`### 決めた点(設計書で決定済み。2026-11-17)`にして、中身を次に置き換える:

```markdown
- 入口: ダッシュボードの`人ごとの負荷`の、割り当て超過の人から(`調整…`)。
- 操作: 割り当て率の変更・他の人への移し替え(余力の多い順の候補)・別の人の追加(率の既定 50%)。週ごと・日ごとの担当は、全週・全日に一括で当てる。
- 結果: ダイアログの中で、変えるたびに、負荷(平均・最大・割り当て超過の日数)と完了予定・見込みを、変更前→変更後で見せる。適用は元に戻す 1 ステップ。
```

同じ項の`### 状態`を`実装済み(\`feature/load-rebalance\`)。実機確認とマージの指示待ち。設計は\`docs/superpowers/specs/2026-11-17-load-rebalance-design.md\`。`に直す。

- [ ] **Step 3: 最終の確認**

Run:
```bash
uv run pytest -m smoke
uvx ruff check
uvx ruff format src test
uvx ty check src
uv run pytest test/test_rebalance.py test/test_rebalance_dialog.py test/test_dashboard_view.py test/test_views.py test/test_dashboard.py -q -n auto
```
Expected: smoke が PASS。ruff が通る。ty は既存の 9 件以外が増えない。最後のテストの一式が PASS。smoke が失敗したときに限り`uv run pytest -n auto`で全テストを確かめる。

- [ ] **Step 4: コミットして PR を作る(マージは指示を待つ)**

```bash
git add -A src test docs .claude
git commit -m "docs: 負荷の調整の仕様・要望の状態・モジュール構成を更新する(要望 145)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/load-rebalance
gh pr create --base develop --title "feat: 負荷の調整を足す(ダッシュボードの割り当て超過の人から。要望 145)" --body "設計書: docs/superpowers/specs/2026-11-17-load-rebalance-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR を作ったら止まり、実機の確認とマージの指示を待つ。
