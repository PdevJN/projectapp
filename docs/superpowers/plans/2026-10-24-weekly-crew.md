# タスクの週ごとの担当割り当て(要望 54) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1 つのタスクの担当者を、開始の日から 7 日ごとの週ごとに変えられるようにし、完了予定を週ごとの換算率で算出する。

**Architecture:** `Task.weekly_crew: list[list[Assignee]]`(添字が週。空は週ごとに分けない)を足し、`assignees` は全週の和集合として保つ。日程計算は NiceGUI から切り離した `timeline.py` に `week_index`・`crew_on`・`crew_pieces` と、日ごとに担当者の集合を替える `calc_end(weeks=…)` を足し、割り当て超過・ダッシュボード・担当者向けファイルは同じ「区間ごとの担当者」を通す。ファイルは `version` 10。ダイアログに「週ごとに分ける」スイッチと週のブロックを足し、ガントチャートは棒の上に週ごとのチップを重ねる。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、型検査 `uv run ty check src`

**Spec:** `docs/superpowers/specs/2026-10-24-weekly-crew-design.md`

## Global Constraints

- 週の数え方: 実効の開始(先行による押し出しを反映した日)の日から 7 日(暦日)ごとに、第1週・第2週…。最後に定義した週より後は、最後の週の担当が続く。開始より前の日は第1週。
- 各週に担当者が最低 1 人。同じ週に同じメンバーは 1 回まで。割り当て率は週ごとに持つ(1〜100%、`MIN_ALLOCATION`〜`MAX_ALLOCATION`)。
- `weekly_crew` が空のタスクは、今までどおり `assignees` だけで動く(完了予定も変わらない)。`assignees` は週ごとのタスクでは全週の和集合(初出の順・割り当て率は各人の最大値)。
- `FORMAT_VERSION` は 9 → 10。キーのない古いファイルは「週ごとに分けない」として読む。不正な値(担当者のいない週・重複・存在しないメンバー・範囲外・配列でない)は読込を拒否する。まとめ・チェックポイントの `weekly_crew` は読込で空にする。
- 週数の上限は `MAX_WEEKS = 52`(設計書にない追加の防御。誤入力で配列が際限なく伸びるのを防ぐ)。ファイルの読込とダイアログの保存で拒否する。
- 相対比率は要望 51 のまま(付けたパラメータを反映)。換算率 = 相対比率 × 割り当て率。
- 週ごとのタスクは、担当の付け替え時の見直し確認(要望 32)の対象外にし、分解できない。PlantUML は和集合・各人の最大の割り当て率で出し、近似であることを通知する。
- 日本語のコメント・メッセージ。周囲のコードのコメントの量と書き方に合わせる。
- 各タスクの最後に、そのタスクが触るテストファイルを実行する。最後のタスクで `uv run pytest -q`(約 4 分。バックグラウンドで)と `uv run ty check src` を通す。
- テストは `test/` にある。この計画の新しいテストは、新規ファイル `test/test_weekly_crew.py`(日程・割り当て超過・ダッシュボード・担当者向けファイルなど、NiceGUI を使わないもの)と、既存の `test_storage.py`・`test_merge.py`・`test_task_dialog.py`・`test_gantt.py` に足す。

## Review Focus

- 先行の押し出しで実効の開始が動くタスク: 週は動いた開始から数える(`planned_start` からではない)。`test_weekly_crew.py`(Task 2)。
- 週の担当者がメンバーに一人もいない・3 者マージでメンバーが消えて週が空になる: 算出は換算率 1 の 1 人として続け(Task 2)、マージは隣の週と同じにして通知する(Task 4)。
- 定義した週より長い・短いタスク(棒が最初の週の途中で終わる、最後の週が何週も続く): 区間は棒の範囲に切る。`test_weekly_crew.py`(Task 3)と `test_gantt.py`(Task 8)。
- 週数の上限(52)を超えるファイル・入力: 読込と保存で拒否する。`test_storage.py`(Task 1)・`test_weekly_crew.py`(Task 7)。
- 「週ごとに分ける」のオン・オフで担当が消えない: オンは現在の担当が第1週、オフは第1週が全期間の担当になる。`test_task_dialog.py`(Task 7)。

---

## File Structure

| ファイル | 変更 |
| --- | --- |
| `src/projectapp/models.py` | `MAX_WEEKS`・`union_assignees`・`Task.weekly_crew`・`FORMAT_VERSION` 10 |
| `src/projectapp/storage.py` | `weekly_crew` の保存・読込、まとめ・チェックポイントで空にする |
| `src/projectapp/timeline.py` | `Worker` に名前・割り当て率、`week_index`・`crew_on`・`crew_pieces`・`counted_pieces`・`weekly_crews`・`consumed_slices`、`calc_end`/`computed_end` の `weeks`、割り当て超過の区間化 |
| `src/projectapp/merge.py` | `weekly_crew` の 3 者マージ |
| `src/projectapp/dashboard.py` | 負荷・予定工数・実績の按分を区間ごとの担当者で数える |
| `src/projectapp/handoff.py` | 週ごとのタスクの見積もり |
| `src/projectapp/arrange.py`・`decompose.py`・`reassign.py`・`views.py`・`plantuml.py` | コピー・分解不可・見直し対象外・改名・PlantUML の通知 |
| `src/projectapp/forms.py` | `build_task` の `weekly_crew` |
| `src/projectapp/task_dialog.py` | `AssigneeFields` の印の接頭辞、`WeeklyCrewFields`、スイッチ、換算率の表示 |
| `src/projectapp/gantt.py` | 棒の上の週ごとのチップ、名前の欄のホバー |
| `test/test_weekly_crew.py`(新規) | 日程・割り当て超過・ダッシュボード・担当者向けファイル・コピー・分解・見直し・PlantUML |
| `CLAUDE.md`・`docs/development.md`・`docs/requests.md`・設計書 | 仕様と記録の更新(Task 9) |

---

### Task 1: モデルと保存・読込

**Files:**
- Modify: `src/projectapp/models.py`
- Modify: `src/projectapp/storage.py`
- Test: `test/test_storage.py`, `test/test_models.py`

**Interfaces:**
- Produces: `models.MAX_WEEKS: int`(52)、`models.union_assignees(weeks: Sequence[Sequence[Assignee]]) -> list[Assignee]`、`Task.weekly_crew: list[list[Assignee]]`、`FORMAT_VERSION == 10`。以降のタスクがこれを使う。

- [ ] **Step 1: 失敗するテストを書く(`test/test_models.py` の末尾に追加)**

```python
def test_union_assignees_keeps_first_seen_order_and_the_largest_allocation() -> None:
    from projectapp.models import Assignee, union_assignees

    weeks = [
        [Assignee("田中", 0.5)],
        [Assignee("田中", 1.0), Assignee("鈴木", 0.25)],
        [Assignee("鈴木", 0.75)],
    ]
    assert union_assignees(weeks) == [Assignee("田中", 1.0), Assignee("鈴木", 0.75)]
    assert weeks[0][0].allocation == 0.5  # 元の週は書き換えない
    assert union_assignees([]) == []
```

`test/test_storage.py` の末尾に追加(`_rewrite` と `save_project`・`load_project` は既存):

```python
def _weekly_project() -> Project:
    first = [Assignee("田中")]
    second = [Assignee("田中"), Assignee("鈴木", 0.5)]
    task = Task("a", id="t1", assignees=[Assignee("田中"), Assignee("鈴木", 0.5)], weekly_crew=[first, second])
    return Project("p", members=[Member("田中"), Member("鈴木")], tasks=[task])


def test_format_version_is_ten() -> None:
    assert FORMAT_VERSION == 10


def test_weekly_crew_roundtrips_and_assignees_is_the_union(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    loaded = load_project(path).tasks[0]
    assert loaded.weekly_crew == [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木", 0.5)]]
    assert loaded.assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]
    saved = json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["weekly_crew"]
    assert [[ref["allocation"] for ref in week] for week in saved] == [[1.0], [1.0, 0.5]]
    assert all("member" in ref for week in saved for ref in week)


def test_the_union_wins_over_the_assignees_in_the_file(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignees=[]))
    assert load_project(path).tasks[0].assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]


def test_a_file_without_weekly_crew_loads_as_not_weekly(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].pop("weekly_crew"))
    task = load_project(path).tasks[0]
    assert task.weekly_crew == []
    assert task.assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]


def test_weekly_crew_in_an_older_version_is_not_read(tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d.update(version=9))
    assert load_project(path).tasks[0].weekly_crew == []


def _bad_weeks(data: dict) -> list[object]:
    member = data["members"][0]["id"]
    ref = {"member": member, "allocation": 1.0}
    return [
        [[]],  # 担当者のいない週
        "x",
        ["x"],
        [[{"name": "田中", "allocation": 1.0}]],  # 旧キー name
        [[{"member": "no-such-id", "allocation": 1.0}]],
        [[ref, dict(ref)]],  # 同じ週に同じメンバー
        [[{"member": member, "allocation": 2.0}]],  # 範囲外
        [[ref] for _ in range(MAX_WEEKS + 1)],  # 上限超え
    ]


@pytest.mark.parametrize("index", range(8))
def test_bad_weekly_crew_is_rejected(index: int, tmp_path: Path) -> None:
    path = save_project(_weekly_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(weekly_crew=_bad_weeks(d)[index]))
    with pytest.raises(ValueError):
        load_project(path)


def test_weekly_crew_is_dropped_for_a_checkpoint(tmp_path: Path) -> None:
    task = Task("c", id="c1", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), weekly_crew=[[Assignee("田中")]])
    path = save_project(Project("p", members=[Member("田中")], tasks=[task]), tmp_path)
    assert load_project(path).tasks[0].weekly_crew == []
```

`test/test_storage.py` の import に `MAX_WEEKS` を足す(`from projectapp.models import (...)` のブロックに `MAX_WEEKS,` を追加)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_models.py test/test_storage.py -q -k "union_assignees or weekly or format_version_is_ten"`
Expected: FAIL(`union_assignees`・`MAX_WEEKS`・`weekly_crew` が未定義)

- [ ] **Step 3: `models.py` を直す**

(a) import に `Sequence` を足す: `from collections.abc import Collection, Iterator` → `from collections.abc import Collection, Iterator, Sequence`

(b) `FORMAT_VERSION = 9 …` の行を、末尾の括弧の中を `9: タスクのパラメータ` のあとに `。10: タスクの週ごとの担当〔weekly_crew〕` を足した形にして、値を 10 にする。

(c) `MIN_ALLOCATION, MAX_ALLOCATION = 0.01, 1.0  # 割り当て率(1%〜100%)` の次の行に追加:

```python
MAX_WEEKS = 52  # 週ごとの担当の週数の上限。誤入力で配列が際限なく伸びるのを防ぐ
```

(d) `Assignee` の定義と `Task` のあいだに追加(`allocation: float = 1.0  # 担当者の時間のうち…` の行の後ろ、`@dataclass\nclass Task:` の前):

```python


def union_assignees(weeks: Sequence[Sequence[Assignee]]) -> list[Assignee]:
    """全週の担当者の和集合(初出の順)。割り当て率は各人の最大値。元の週は書き換えない。"""
    merged: dict[str, Assignee] = {}
    for week in weeks:
        for assignee in week:
            seen = merged.get(assignee.name)
            if seen is None:
                merged[assignee.name] = Assignee(assignee.name, assignee.allocation)
            elif assignee.allocation > seen.allocation:
                seen.allocation = assignee.allocation
    return list(merged.values())
```

(e) `Task` の `parameters` の行の次に追加:

```python
    weekly_crew: list[list[Assignee]] = field(default_factory=list)  # 週ごとの担当(添字が週。開始の日から 7 日ごと)。空は週ごとに分けない。分けるときの assignees は全週の和集合
```

- [ ] **Step 4: `storage.py` を直す**

(a) `_dump` の担当者の参照を作る部分(`taken = project.used_ids()` から `return data` まで)を、次に置き換える:

```python
    taken = project.used_ids()

    def refs_of(assignees: list[dict[str, Any]]) -> list[dict[str, Any]]:
        refs = []
        for assignee in assignees:
            name = assignee["name"]
            if name not in ids:
                ids[name] = new_id(taken)
                taken.add(ids[name])
                data["members"].append({"name": name, "ratio": 1.0, "levels": {}, "id": ids[name], "icon": "", "work_days": []})
            refs.append({"member": ids[name], "allocation": assignee["allocation"]})
        return refs

    for task in _task_dicts(data["tasks"], data["sections"]):
        task["assignees"] = refs_of(task["assignees"])
        task["weekly_crew"] = [refs_of(week) for week in task["weekly_crew"]]
    return data
```

(b) `_task` の `actuals, legacy_progress = _actuals(raw.get("actuals"))` の次の行に追加し、`task = Task(` の `assignees=_assignees(raw, ctx),` を置き換える:

```python
    weekly = _weekly_crew(raw.get("weekly_crew"), ctx) if ctx.version >= 10 else []
    assignees = union_assignees(weekly) if weekly else _assignees(raw, ctx)  # 週ごとのタスクの担当は週の表が正
```
```python
        assignees=assignees,
        weekly_crew=weekly,
```
(`assignees=_assignees(raw, ctx),` の 1 行を、上の 2 行に置き換える)

(c) `_summary` の `status=Status.NOT_STARTED,\n        parameters=[],\n    )` を `status=Status.NOT_STARTED,\n        parameters=[],\n        weekly_crew=[],\n    )` に、`_checkpoint` の `progress=None,\n        parameters=[],\n    )` を `progress=None,\n        parameters=[],\n        weekly_crew=[],\n    )` に直す。

(d) `_assignees` の定義の直前(`_member_assignees` の後ろ)に追加:

```python
def _weekly_crew(value: Any, ctx: "_Context") -> list[list[Assignee]]:
    """version 10 の週ごとの担当。各週は担当者の配列(形式は assignees と同じ)。担当者のいない週・上限超えは拒否する。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("週ごとの担当が配列ではありません")
    if len(value) > MAX_WEEKS:
        raise ValueError(f"週ごとの担当は{MAX_WEEKS}週までです")
    weeks: list[list[Assignee]] = []
    for week in value:
        if not isinstance(week, list):
            raise ValueError("週の担当が配列ではありません")
        crew = _member_assignees(week, ctx.member_names)
        if not crew:
            raise ValueError("担当者のいない週があります")
        weeks.append(crew)
    return weeks
```

(e) `storage.py` の `from projectapp.models import (...)` に `MAX_WEEKS,` と `union_assignees,` を足す(`FORMAT_VERSION,` の並びに)。

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_models.py test/test_storage.py -q`
Expected: PASS。既存テストに `version` が 9 だと決め打ちしたものがあれば、`FORMAT_VERSION` を使う形か 10 に直す(`grep -n "== 9\|\"version\": 9" test/*.py` で探す)。

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_models.py test/test_storage.py
git commit -m "feat: タスクに週ごとの担当(weekly_crew)を持たせ、version 10 で保存・読込する"
```

---

### Task 2: 週ごとの担当で完了予定を算出する

**Files:**
- Modify: `src/projectapp/timeline.py`
- Create: `test/test_weekly_crew.py`

**Interfaces:**
- Consumes: Task 1 の `Task.weekly_crew`・`union_assignees`。
- Produces(`timeline.py`):
  - `Worker(rate, days, name="", allocation=1.0)`(`name`・`allocation` は比較に使わない)
  - `week_index(start: date, day: date, count: int) -> int`
  - `crew_on(task: Task, start: date, day: date) -> list[Assignee]`
  - `weekly_crews(task: Task, project: Project) -> list[list[Worker]]`
  - `calc_end(start, effort_hours, daily_hours, work_start, holidays, crew=None, weeks=None)`
  - `computed_end(..., crew=None, weeks=None)`
  - `consumed_slices(start, effort_hours, daily_hours, work_start, holidays, crew=None, weeks=None) -> list[tuple[datetime, datetime, list[Worker]]]`

- [ ] **Step 1: 失敗するテストを書く(新規 `test/test_weekly_crew.py`)**

```python
from datetime import date, datetime, time

import pytest

from projectapp.models import Assignee, Member, Project, Task, union_assignees
from projectapp.timeline import (
    Worker,
    calc_end,
    consumed_slices,
    crew_on,
    effective_end,
    week_index,
    weekly_crews,
)

OPEN = time(9, 0)
WED = datetime(2026, 10, 7, 9, 0)  # 水曜 9:00
MON = datetime(2026, 10, 5, 9, 0)
HOLIDAYS: dict[date, str] = {}


def workers(*rates: float) -> list[Worker]:
    return [Worker(rate) for rate in rates]


def people() -> list[Member]:
    return [Member("田中", 1.0), Member("鈴木", 1.0)]


def weekly_task(name: str, weeks: list[list[Assignee]], **kwargs: object) -> Task:
    return Task(name, id=name, assignees=union_assignees(weeks), weekly_crew=weeks, **kwargs)  # type: ignore[arg-type]


def project_of(*tasks: Task) -> Project:
    return Project("p", members=people(), tasks=list(tasks), daily_hours=6.5)


@pytest.mark.parametrize(
    ("day", "count", "expected"),
    [
        (date(2026, 10, 7), 3, 0),
        (date(2026, 10, 13), 3, 0),  # 6 日目
        (date(2026, 10, 14), 3, 1),  # 7 日目の次
        (date(2026, 10, 21), 3, 2),
        (date(2026, 11, 30), 3, 2),  # 最後の週より後は最後の週
        (date(2026, 10, 1), 3, 0),  # 開始より前は第1週
        (date(2026, 10, 20), 1, 0),
    ],
)
def test_week_index_counts_seven_calendar_days_from_the_start(day: date, count: int, expected: int) -> None:
    assert week_index(date(2026, 10, 7), day, count) == expected


def test_crew_on_picks_the_week_and_falls_back_to_the_assignees() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    weekly = weekly_task("w", [[a], [a, b]])
    assert crew_on(weekly, date(2026, 10, 7), date(2026, 10, 8)) == [a]
    assert crew_on(weekly, date(2026, 10, 7), date(2026, 10, 15)) == [a, b]
    plain = Task("p", assignees=[b])
    assert crew_on(plain, date(2026, 10, 7), date(2026, 10, 15)) == [b]


def test_the_second_week_runs_faster() -> None:
    # 第1週(水〜火の稼働日 5 日 = 32.5h)は 1 人。残り 7.5h を第2週の 2 人で 3.75h
    end = calc_end(WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)])
    assert end == datetime(2026, 10, 14, 12, 45)


def test_the_last_week_continues() -> None:
    end = calc_end(WED, 100.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)])
    assert end == datetime(2026, 10, 21, 10, 15)  # 第2週は 65h、残り 2.5h を同じ 2 人で 1.25h


def test_the_example_of_five_weeks() -> None:
    weeks = [workers(1.0), workers(1.0, 1.0), workers(1.0, 1.0), workers(1.0, 1.0, 1.0), workers(1.0)]
    assert calc_end(MON, 100.0, 6.5, OPEN, HOLIDAYS, weeks=weeks) == datetime(2026, 10, 19, 10, 15)


def test_one_week_is_the_same_as_a_plain_crew() -> None:
    plain = calc_end(WED, 9.0, 6.5, OPEN, HOLIDAYS, [Worker(1.5)])
    assert calc_end(WED, 9.0, 6.5, OPEN, HOLIDAYS, weeks=[[Worker(1.5)]]) == plain


def test_a_week_without_workers_runs_as_one_person() -> None:
    assert calc_end(WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[[], workers(1.0, 1.0)]) == calc_end(
        WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)]
    )


def test_invalid_effort_still_gives_none_with_weeks() -> None:
    assert calc_end(WED, 0.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0)]) is None
    assert calc_end(WED, float("inf"), 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0)]) is None


def test_the_schedule_uses_the_weekly_crew_of_the_task() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    task = weekly_task("a", [[a], [a, b]], planned_start=WED, effort_hours=40.0)
    assert effective_end(task, project_of(task), HOLIDAYS) == datetime(2026, 10, 14, 12, 45)


def test_weeks_are_counted_from_the_pushed_start_not_the_planned_start() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    before = Task("p", id="p", planned_start=WED, effort_hours=32.5)  # 水〜火の 5 日 → 10/13 15:30 に終わる
    task = weekly_task("b", [[a], [a, b]], planned_start=WED, effort_hours=13.0, predecessors=["p"])
    # 開始は 10/13 15:30。第1週(10/13〜19)は 1 人なので、水・木の 13h で 10/15 15:30(開始予定から数えると水曜が第2週で、10/14 に終わる)
    assert effective_end(task, project_of(before, task), HOLIDAYS) == datetime(2026, 10, 15, 15, 30)


def test_weekly_crews_make_workers_with_the_parameters_applied() -> None:
    a = Assignee("田中", 0.5)
    task = weekly_task("w", [[a]])
    [[worker]] = weekly_crews(task, project_of(task))
    assert worker.rate == pytest.approx(0.5)
    assert (worker.name, worker.allocation) == ("田中", 0.5)
    assert worker == Worker(0.5)  # 名前と割り当て率は比較に使わない


def test_consumed_slices_cover_the_whole_effort() -> None:
    slices = consumed_slices(WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)])
    assert slices[0][0] == WED and slices[-1][1] == datetime(2026, 10, 14, 12, 45)
    worked = sum(((right - left).total_seconds() / 3600) * sum(w.rate for w in active) for left, right, active in slices)
    assert worked == pytest.approx(40.0)
    assert consumed_slices(WED, 0.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0)]) == []
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_weekly_crew.py -q`
Expected: FAIL(`week_index` などの import エラー)

- [ ] **Step 3: `timeline.py` を直す**

(a) import: `from collections.abc import Callable, Collection, Iterable, Mapping, Sequence` に `Iterator` を足す。

(b) `Worker` を置き換える:

```python
@dataclass(frozen=True)
class Worker:
    """完了予定の算出に使う担当者 1 人。rate は換算率(相対比率 × 割り当て率)、days は日付 → 稼働日の上書き。
    name と allocation は、担当者向けの見積もりでの按分に使う(比較には使わない)。"""

    rate: float = 1.0
    days: Mapping[date, WorkDay] = field(default_factory=dict)
    name: str = field(default="", compare=False)
    allocation: float = field(default=1.0, compare=False)
```

(c) `crew_of` の `Worker(...)` の生成を置き換える:

```python
    return [
        Worker(
            combine_rate(effective_ratio(by_name[a.name], chosen, only), a.allocation),
            work_day_map(by_name[a.name].work_days),
            a.name,
            a.allocation,
        )
        for a in assignees
        if a.name in by_name
    ]
```

(d) `calc_end` と `_calc_end`(`def calc_end` から `_calc_end` の末尾まで)を、次に置き換える:

```python
def week_index(start: date, day: date, count: int) -> int:
    """開始の日から 7 日(暦日)ごとの週の添字(0 が第1週)。最後の週より後は最後の週。開始より前は第1週。"""
    return min(max((day - start).days, 0) // 7, count - 1)


def crew_on(task: Task, start: date, day: date) -> list[Assignee]:
    """その日の担当者。週ごとに分けないタスクは assignees。start は実効の開始の日。"""
    if not task.weekly_crew:
        return task.assignees
    return task.weekly_crew[week_index(start, day, len(task.weekly_crew))]


def _crews(
    effort_hours: float, daily_hours: float, crew: Sequence[Worker] | None, weeks: Sequence[Sequence[Worker]] | None
) -> list[list[Worker]] | None:
    """算出に使う週ごとの担当(週ごとに分けないときは 1 週ぶん)。算出できない入力は None。
    担当者のいない週は換算率 1 の 1 人。工数の上限の判定は、最も遅い週(換算率の合計が最小)で行う。"""
    crews = [list(week) or [Worker()] for week in weeks] if weeks else [list(crew) if crew else [Worker()]]
    total = min(sum(w.rate for w in c) for c in crews)
    if not isfinite(effort_hours) or effort_hours <= 0 or not 0 < daily_hours <= 24:
        return None
    if not isfinite(total) or total <= 0 or effort_hours / total > daily_hours * MAX_WORKDAYS:
        return None
    return crews


def calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
) -> datetime | None:
    """基準の人の工数を、担当者全員の稼働の枠(その人の上書き、なければ始業から稼働可能時間)に割り当てた終了日時。

    枠が重なる時刻は、稼働中の担当者の換算率の合計で工数を消化する。crew が空なら換算率1の1人。
    weeks があれば、start の日から 7 日ごとにその週の担当者で消化する(最後の週は以降も続く。crew は使わない)。
    工数が不正(NaN・inf・0以下・稼働日数の上限超え)、daily_hoursが0以下・24超、
    または日付が範囲を超えるときは、例外にせずNoneを返す。
    """
    crews = _crews(effort_hours, daily_hours, crew, weeks)
    if crews is None:
        return None
    try:
        return _calc_end(start, effort_hours, daily_hours, work_start, holidays, crews)
    except OverflowError:
        return None


def consumed_slices(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
) -> list[tuple[datetime, datetime, list[Worker]]]:
    """工数を消化する区間(左, 右, その区間で稼働している担当者)。算出できないときは空。"""
    crews = _crews(effort_hours, daily_hours, crew, weeks)
    if crews is None:
        return []
    try:
        return list(_consume(start, effort_hours, daily_hours, work_start, holidays, crews))
    except OverflowError:
        return []


def _consume(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crews: list[list[Worker]],
) -> Iterator[tuple[datetime, datetime, list[Worker]]]:
    remaining = effort_hours
    day, cursor = start.date(), start
    while True:
        workers = crews[week_index(start.date(), day, len(crews))]
        windows = [
            (w, window)
            for w in workers
            if (window := day_window(day, daily_hours, work_start, holidays, w.days)) is not None
        ]
        points = sorted({max(p, cursor) for _, window in windows for p in window})
        for left, right in zip(points, points[1:]):
            active = [w for w, (opens, closes) in windows if opens <= left and right <= closes]
            speed = sum(w.rate for w in active)
            if speed <= 0:
                continue
            capacity = speed * (right - left).total_seconds() / 3600
            if remaining <= capacity + CAPACITY_EPSILON:  # 浮動小数の丸めで、ちょうど枠の終わりで終わる工数が翌日に回らない
                yield left, min(left + timedelta(hours=remaining / speed), right), active
                return
            remaining -= capacity
            yield left, right, active
        day += timedelta(days=1)
        cursor = datetime.combine(day, time.min)


def _calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crews: list[list[Worker]],
) -> datetime:
    end = start
    for _, end, _ in _consume(start, effort_hours, daily_hours, work_start, holidays, crews):
        pass
    return end
```

(e) `conversion_rate` の次に追加:

```python
def weekly_crews(task: Task, project: Project) -> list[list[Worker]]:
    """週ごとの担当を算出用の Worker にしたもの(パラメータを反映)。週ごとに分けないタスクは空。"""
    return [crew_of(week, project.members, project.parameters, task.parameters) for week in task.weekly_crew]
```

(f) `computed_end` を置き換える:

```python
def computed_end(
    start: datetime | None,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    deadline: datetime | None = None,
    rate: float = 1.0,
    crew: Sequence[Worker] | None = None,
    weeks: Sequence[Sequence[Worker]] | None = None,
) -> datetime | None:
    """手入力を使わない完了予定。工数を換算率で割って算出し、算出できなければ締切、締切もなければ開始予定の1日後。"""
    if start is not None and effort_hours > 0:
        workers = list(crew) if crew else [Worker(combine_rate(rate, 1.0))]
        end = calc_end(start, effort_hours, daily_hours, work_start, holidays, workers, weeks)
        if end is not None:
            return end
    if deadline is not None:
        return deadline  # 開始予定より前でも、そのまま使う(遅れている状態が見える)
    if start is None:
        return None
    try:
        return start + timedelta(days=1)
    except OverflowError:
        return None
```

(g) `_own_end` の `computed_end(...)` 呼び出しの `crew=crew_of(...)` の行を、次の 2 行にする:

```python
        crew=crew_of(task.assignees, project.members, project.parameters, task.parameters),
        weeks=weekly_crews(task, project) or None,
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_timeline.py test/test_schedule.py -q`
Expected: PASS(既存の完了予定の算出テストが変わらない)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/timeline.py test/test_weekly_crew.py
git commit -m "feat: 完了予定を週ごとの担当の換算率で算出する"
```

---

### Task 3: 割り当て超過を週ごとの区間で数える

**Files:**
- Modify: `src/projectapp/timeline.py`
- Test: `test/test_weekly_crew.py`

**Interfaces:**
- Consumes: Task 2 の `Task.weekly_crew`。
- Produces(`timeline.py`):
  - `crew_pieces(task: Task, start: datetime, end: datetime) -> list[tuple[datetime, datetime, list[Assignee]]]`
  - `counted_pieces(task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None) -> list[tuple[datetime, datetime, list[Assignee]]]`(数えるタスクの区間と、その区間のメンバーの担当者。数えないタスクは空)

- [ ] **Step 1: 失敗するテストを書く(`test/test_weekly_crew.py` に追加)**

import に `Overload, clip_overloads, counted_pieces, crew_pieces, overallocations` を足す。

```python
def test_crew_pieces_cut_at_midnight_every_seven_days_from_the_start() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    task = weekly_task("w", [[a], [b]])
    end = datetime(2026, 10, 20, 15, 30)
    assert crew_pieces(task, WED, end) == [(WED, datetime(2026, 10, 14), [a]), (datetime(2026, 10, 14), end, [b])]


def test_crew_pieces_stop_where_the_task_ends() -> None:
    a, b, c = Assignee("田中"), Assignee("鈴木"), Assignee("田中", 0.5)
    task = weekly_task("w", [[a], [b], [c]])
    end = datetime(2026, 10, 10, 12)  # 第1週の中で終わる
    assert crew_pieces(task, WED, end) == [(WED, end, [a])]
    later = datetime(2026, 10, 16, 12)  # 第2週の中で終わる
    assert [crew for _, _, crew in crew_pieces(task, WED, later)] == [[a], [b]]


def test_crew_pieces_of_a_plain_task_is_one_piece() -> None:
    a = Assignee("田中")
    end = datetime(2026, 10, 20)
    assert crew_pieces(Task("p", assignees=[a]), WED, end) == [(WED, end, [a])]


def overload_project() -> Project:
    first, second = Assignee("田中"), Assignee("鈴木")
    # 田中は第1週、鈴木は第2週にこのタスクを担当する(工数 65h は 1 人で 10/20 15:30 まで)
    t1 = weekly_task("t1", [[first], [second]], planned_start=WED, effort_hours=65.0)
    end = datetime(2026, 10, 20, 15, 30)
    t2 = Task("t2", id="t2", planned_start=WED, planned_end=end, assignees=[Assignee("田中", 0.5)])
    t3 = Task("t3", id="t3", planned_start=WED, planned_end=end, assignees=[Assignee("鈴木", 0.5)])
    return project_of(t1, t2, t3)


def test_overloads_are_counted_per_week_of_the_crew() -> None:
    proj = overload_project()
    boundary = datetime(2026, 10, 14)
    assert overallocations(proj, HOLIDAYS) == [
        Overload("田中", WED, boundary, 1.5),
        Overload("鈴木", boundary, datetime(2026, 10, 20, 15, 30), 1.5),
    ]


def test_clip_overloads_keeps_only_the_weeks_of_the_member() -> None:
    proj = overload_project()
    overloads = overallocations(proj, HOLIDAYS)
    t1, t2, t3 = proj.tasks
    assert clip_overloads(t1, proj, HOLIDAYS, overloads) == overloads  # t1 は 2 人が各週に入る
    assert clip_overloads(t2, proj, HOLIDAYS, overloads) == [overloads[0]]  # 田中は第1週だけ超過
    assert clip_overloads(t3, proj, HOLIDAYS, overloads) == [overloads[1]]


def test_counted_pieces_skip_non_members_and_uncounted_tasks() -> None:
    proj = overload_project()
    ghost = weekly_task("g", [[Assignee("佐藤")], [Assignee("佐藤"), Assignee("田中")]], planned_start=WED, effort_hours=65.0)
    proj.tasks.append(ghost)
    pieces = counted_pieces(ghost, proj, HOLIDAYS)
    assert [[a.name for a in crew] for _, _, crew in pieces] == [[], ["田中"]]
    finished = weekly_task("f", [[Assignee("田中")]], planned_start=WED, effort_hours=6.5, status=Status.DONE)
    assert counted_pieces(finished, proj, HOLIDAYS) == []
```

import に `Status` を足す(`from projectapp.models import Assignee, Member, Project, Status, Task, union_assignees`)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_weekly_crew.py -q -k "pieces or overload"`
Expected: FAIL(`crew_pieces` などが未定義)

- [ ] **Step 3: `timeline.py` を直す**

(a) `counted_span` の直前に追加:

```python
def crew_pieces(task: Task, start: datetime, end: datetime) -> list[tuple[datetime, datetime, list[Assignee]]]:
    """[start, end) を、担当者の組み合わせごとの区間に切る。週ごとに分けないタスクは、全体で 1 区間。
    週ごとのタスクは、start の日から 7 日ごと(0 時)に切り、最後の週の担当は end まで続く。"""
    if not task.weekly_crew:
        return [(start, end, task.assignees)]
    pieces: list[tuple[datetime, datetime, list[Assignee]]] = []
    last = len(task.weekly_crew) - 1
    for week, crew in enumerate(task.weekly_crew):
        left = start if week == 0 else datetime.combine(start.date() + timedelta(days=7 * week), time.min)
        right = end if week == last else datetime.combine(start.date() + timedelta(days=7 * (week + 1)), time.min)
        left, right = max(left, start), min(right, end)
        if left < right:
            pieces.append((left, right, crew))
    return pieces
```

(b) `counted_span` の直後に追加:

```python
def counted_pieces(
    task: Task, project: Project, holidays: dict[date, str], schedule: Schedule | None = None
) -> list[tuple[datetime, datetime, list[Assignee]]]:
    """割り当ての合計に数えるタスクの区間と、その区間の担当者(メンバーにいる人だけ)。数えないタスクは空。"""
    span = counted_span(task, project, holidays, schedule)
    if span is None:
        return []
    names = {m.name for m in project.members}
    return [(left, right, [a for a in crew if a.name in names]) for left, right, crew in crew_pieces(task, *span)]
```

(c) `overallocations` の中の

```python
        counted = counted_span(task, project, holidays, schedule)
        if counted is not None:
            for assignee in counted_assignees(task, project):
                spans.setdefault(assignee.name, []).append((*counted, assignee.allocation))
```
を、次に置き換える:

```python
        for left, right, crew in counted_pieces(task, project, holidays, schedule):
            for assignee in crew:
                spans.setdefault(assignee.name, []).append((left, right, assignee.allocation))
```

(d) `clip_overloads` の本体(docstring の後ろから `return clipped` まで)を、次に置き換える:

```python
    pieces = counted_pieces(task, project, holidays, schedule)
    clipped: list[Overload] = []
    for overload in overloads:
        for start, end, crew in pieces:
            if overload.member not in {a.name for a in crew}:
                continue
            left, right = max(overload.start, start), min(overload.end, end)
            if left >= right:
                continue
            item = replace(overload, start=left, end=right)
            if clipped and clipped[-1].member == item.member and clipped[-1].end == item.start and clipped[-1].total == item.total:
                clipped[-1] = replace(clipped[-1], end=item.end)  # 週の境目で切れた同じ超過は、1 本の縞にする
            else:
                clipped.append(item)
    return clipped
```
(引数の `schedule` と `counted = counted_span(...)`・`if counted is None: return []`・`start, end = counted` の行は削除する。)

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_timeline.py test/test_schedule.py test/test_gantt.py -q`
Expected: PASS(既存の超過・縞のテストが変わらない)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/timeline.py test/test_weekly_crew.py
git commit -m "feat: 割り当て超過を週ごとの担当の区間で数える"
```

---

### Task 4: 3 者マージ

**Files:**
- Modify: `src/projectapp/merge.py`
- Test: `test/test_merge.py`

**Interfaces:**
- Consumes: Task 1 の `Task.weekly_crew`・`union_assignees`。
- Produces: マージの項目 `週ごとの担当`(リスト全体で 1 項目)。

- [ ] **Step 1: 失敗するテストを書く(`test/test_merge.py` の末尾に追加)**

import に `union_assignees` を足す(`from projectapp.models import (...)` のブロック)。

```python
def two() -> list[Member]:
    return [Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2")]


def weekly_task(*weeks: list[Assignee]) -> Task:
    return task("a", "t1", assignees=union_assignees(weeks), weekly_crew=[list(w) for w in weeks])


def week_names(t: Task) -> list[list[str]]:
    return [[a.name for a in week] for week in t.weekly_crew]


def test_a_weekly_crew_changed_by_one_side_is_taken() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")])])
    theirs = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("甲"), Assignee("乙")])])
    result = merge_projects(base, base, theirs)
    assert result.conflicts == []
    merged = result.project.tasks[0]
    assert week_names(merged) == [["甲"], ["甲", "乙"]]
    assert [a.name for a in merged.assignees] == ["甲", "乙"]


def test_a_weekly_crew_changed_on_both_sides_is_one_conflict() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")])])
    ours = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    theirs = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("甲"), Assignee("乙")])])
    result = merge_projects(base, ours, theirs)
    assert [c.field for c in result.conflicts] == ["週ごとの担当"]
    assert week_names(result.project.tasks[0]) == [["甲"], ["乙"]]  # 既定は自分
    chosen = merge_projects(base, ours, theirs, {result.conflicts[0].id: THEIRS}).project.tasks[0]
    assert week_names(chosen) == [["甲"], ["甲", "乙"]]


def test_a_week_emptied_by_a_deleted_member_takes_the_neighbouring_crew() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    theirs = proj(members=[Member("甲", 1.0, id="m1")], tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    result = merge_projects(base, base, theirs)
    assert result.conflicts == []
    assert week_names(result.project.tasks[0]) == [["甲"], ["甲"]]
    assert any("担当者を外しました" in n and "第2週" in n for n in result.notes)
    assert any("隣の週と同じ" in n and "第2週" in n for n in result.notes)


def test_when_every_week_is_emptied_the_task_is_no_longer_weekly() -> None:
    gone = weekly_task([Assignee("乙")], [Assignee("乙")])
    base = proj(members=two(), tasks=[gone])
    theirs = proj(members=[Member("甲", 1.0, id="m1")], tasks=[gone])
    result = merge_projects(base, base, theirs)
    merged = result.project.tasks[0]
    assert merged.weekly_crew == [] and merged.assignees == []
    assert any("週ごとの担当をすべて外しました" in n for n in result.notes)


def test_turning_weekly_off_on_one_side_gives_the_plain_assignees() -> None:
    base = proj(members=two(), tasks=[weekly_task([Assignee("甲")], [Assignee("乙")])])
    ours = proj(members=two(), tasks=[task("a", "t1", assignees=[Assignee("甲", 0.5)])])
    result = merge_projects(base, ours, base)
    assert result.conflicts == []
    merged = result.project.tasks[0]
    assert merged.weekly_crew == [] and merged.assignees == [Assignee("甲", 0.5)]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_merge.py -q -k "weekly or week"`
Expected: FAIL(`weekly_crew` がマージされない)

- [ ] **Step 3: `merge.py` を直す**

(a) `from projectapp.models import (...)` に `union_assignees,` を足す。

(b) `TASK_LABELS` の `"parameters": "パラメータ",` を `"parameters": "パラメータ", "weekly_crew": "週ごとの担当",` にする。

(c) `_flatten` の `visit` の中の 2 行

```python
            record: Record = {f.name: getattr(t, f.name) for f in fields(Task) if f.name not in ("id", "assignees")}
            record["assignees"] = [(ids.get(a.name, a.name), a.allocation) for a in t.assignees]
```
を、次に置き換える:

```python
            record: Record = {
                f.name: getattr(t, f.name) for f in fields(Task) if f.name not in ("id", "assignees", "weekly_crew")
            }
            # 週ごとのタスクの担当は週の表が正(和集合は持たない)なので、「担当」は空にして衝突させない
            record["assignees"] = [] if t.weekly_crew else [(ids.get(a.name, a.name), a.allocation) for a in t.assignees]
            record["weekly_crew"] = [[(ids.get(a.name, a.name), a.allocation) for a in week] for week in t.weekly_crew]
```

(d) `display` に分岐を足す:

```python
    def display(name: str, value: Any) -> Any:
        if name == "assignees":
            return [f"{shown.get(i, i)} {a:.0%}" for i, a in value]
        if name == "weekly_crew":
            return [
                f"第{n}週: " + "、".join(f"{shown.get(i, i)} {a:.0%}" for i, a in week)
                for n, week in enumerate(value, start=1)
            ]
        return value
```

(e) `merge_projects` の前(モジュールの関数として)に追加:

```python
def _fill_empty_weeks(weeks: list[list[Assignee]]) -> tuple[list[list[Assignee]], list[int]]:
    """担当者のいなくなった週を、前の週(なければ次の週)の担当にする。埋めた週の番号(1 始まり)も返す。
    すべての週が空なら空のリスト(週ごとに分けない)。"""
    if not any(weeks):
        return [], []
    result = [list(week) for week in weeks]
    filled: list[int] = []
    for index, week in enumerate(result):
        if week:
            continue
        source = next((result[i] for i in range(index - 1, -1, -1) if result[i]), None) or next(w for w in result if w)
        result[index] = [Assignee(a.name, a.allocation) for a in source]
        filled.append(index + 1)
    return result, filled
```

(f) `make_task` を次に置き換える(`names`・`shown`・`notes`・`categories`・`tasks` は外側の変数のまま):

```python
    def make_task(key: str, record: Record) -> Task:
        assignees = []
        for member_id, allocation in record["assignees"]:
            if member_id in names:
                assignees.append(Assignee(names[member_id], allocation))
            else:
                notes.append(f"担当者を外しました: 「{record['name']}」の{shown.get(member_id, member_id)}")
        weeks: list[list[Assignee]] = []
        for number, week in enumerate(record["weekly_crew"], start=1):
            crew = []
            for member_id, allocation in week:
                if member_id in names:
                    crew.append(Assignee(names[member_id], allocation))
                else:
                    notes.append(f"担当者を外しました: 「{record['name']}」の第{number}週の{shown.get(member_id, member_id)}")
            weeks.append(crew)
        weeks, filled = _fill_empty_weeks(weeks)
        for number in filled:
            notes.append(f"担当者がいなくなった週を、隣の週と同じにしました: 「{record['name']}」の第{number}週")
        if record["weekly_crew"] and not weeks:
            notes.append(f"週ごとの担当をすべて外しました: 「{record['name']}」")
        data = {
            k: v
            for k, v in record.items()
            if k not in ("assignees", "weekly_crew", "parent", "predecessors", "category_id", "children")
        }
        category = record["category_id"]
        if category is not None and category not in categories:
            notes.append(f"カテゴリを外しました: 「{record['name']}」")
            category = None
        predecessors = [p for p in record["predecessors"] if p in tasks]
        children = [c for c in record["children"] if c in tasks]
        if data["kind"] is TaskKind.SUMMARY and not children:
            data["kind"] = TaskKind.NORMAL  # 子がいなくなったまとめは、通常タスクに戻す
        return Task(
            id=key,
            assignees=union_assignees(weeks) if weeks else assignees,
            weekly_crew=weeks,
            predecessors=predecessors,
            category_id=category,
            children=children,
            **data,
        )
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_merge.py test/test_gitpull.py test/test_conflict_dialog.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/merge.py test/test_merge.py
git commit -m "feat: 週ごとの担当を3者マージの項目にする"
```

---

### Task 5: ダッシュボードと担当者向けファイル

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Modify: `src/projectapp/handoff.py`
- Test: `test/test_weekly_crew.py`

**Interfaces:**
- Consumes: Task 2 の `crew_on`・`weekly_crews`・`consumed_slices`、Task 3 の `crew_pieces`・`counted_pieces`。

- [ ] **Step 1: 失敗するテストを書く(`test/test_weekly_crew.py` に追加)**

import に `from projectapp.dashboard import Period, _member_spans, summarize_workload` と `from projectapp.handoff import build_todos`、`from projectapp.models import Actual` を足す。

```python
def split_project() -> Project:
    # 10/5(月)〜10/19(月)。田中が第1週、鈴木が第2週以降
    task = weekly_task(
        "t",
        [[Assignee("田中")], [Assignee("鈴木")]],
        planned_start=MON,
        planned_end=datetime(2026, 10, 19, 15, 30),
        actuals=[Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 11))],
    )
    return project_of(task)


def test_member_spans_follow_the_weeks_of_the_crew() -> None:
    spans = _member_spans(split_project(), HOLIDAYS, None)
    boundary = datetime(2026, 10, 12)
    assert spans == {
        "田中": [(MON, boundary, 1.0)],
        "鈴木": [(boundary, datetime(2026, 10, 19, 15, 30), 1.0)],
    }


def test_workload_plans_each_week_for_its_own_crew_and_splits_the_actual_by_the_week() -> None:
    period = Period(date(2026, 10, 5), date(2026, 10, 25))
    rows = {r.name: r for r in summarize_workload(split_project(), period, datetime(2026, 10, 20), HOLIDAYS)}
    assert rows["田中"].planned_hours == pytest.approx(32.5)  # 10/5〜9 の 5 日
    assert rows["鈴木"].planned_hours == pytest.approx(39.0)  # 10/12〜16 と 10/19 の 6 日
    assert rows["田中"].actual_hours == pytest.approx(0.0)
    assert rows["鈴木"].actual_hours == pytest.approx(2.0)  # 10/13 は第2週(鈴木)


def test_handoff_estimates_each_member_from_the_weeks_they_work() -> None:
    a, b = Assignee("田中"), Assignee("鈴木", 0.5)
    task = weekly_task("t", [[a], [a, b]], planned_start=MON, effort_hours=50.0)
    project = project_of(task)
    # 第1週 32.5h は田中だけ。残り 17.5h は第2週の 田中+鈴木(0.5) で、10/12 に 9.75h、10/13 に 7.75h(= 5.1667h の稼働)
    todos = build_todos(project, "田中", HOLIDAYS)
    assert todos.data["items"][0]["estimate_hours"] == pytest.approx(44.17)
    other = build_todos(project, "鈴木", HOLIDAYS)
    assert other.data["items"][0]["estimate_hours"] == pytest.approx(5.83)  # 11.6667h の稼働 × 割り当て率 0.5


def test_handoff_estimate_of_a_plain_task_is_unchanged() -> None:
    task = Task("p", id="p", planned_start=MON, effort_hours=13.0, assignees=[Assignee("田中", 0.5), Assignee("鈴木")])
    todos = build_todos(project_of(task), "田中", HOLIDAYS)
    assert todos.data["items"][0]["estimate_hours"] == pytest.approx(13.0 * 0.5 / 1.5)  # 換算率の合計は 0.5 + 1.0
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_weekly_crew.py -q -k "member_spans or workload or handoff"`
Expected: FAIL(ダッシュボードが和集合で数える・見積もりが一律の式)

- [ ] **Step 3: `dashboard.py` を直す**

(a) import: `from projectapp.models import Project, Status, Task, TaskKind, WorkDay` に `Assignee` を足し、`from projectapp.timeline import (...)` の `counted_assignees,`・`counted_span,` を `counted_pieces,`・`crew_on,`・`crew_pieces,` に置き換える。

(b) `_member_spans` のループを置き換える:

```python
    for task in _tasks(project, member):
        for left, right, crew in counted_pieces(task, project, holidays, schedule):
            for assignee in crew:
                spans.setdefault(assignee.name, []).append((left, right, assignee.allocation))
    return spans
```
(元の `counted = counted_span(...)` から `return spans` までを置き換える。)

(c) `_shares` を置き換える(タスクではなく、その時点の担当者のリストを受け取る):

```python
def _shares(assignees: list[Assignee], names: list[str]) -> list[tuple[str, float, float]]:
    """(集計先, 割り当て率, 実績の按分の比)。メンバーでない担当者と担当なしは「未割当」。"""
    if not assignees:
        return [(UNASSIGNED, 1.0, 1.0)]
    total = sum(a.allocation for a in assignees)
    usable = isfinite(total) and total > 0
    return [
        (
            a.name if a.name in names else UNASSIGNED,
            a.allocation,
            a.allocation / total if usable else 1 / len(assignees),
        )
        for a in assignees
    ]
```

(d) `summarize_workload` の `for task in _tasks(project, member):` のブロック全体(`start, end = …` から `actual[key] += seconds / 3600 * share` まで)を置き換える:

```python
    for task in _tasks(project, member):
        start, end = schedule.start(task), schedule.end(task)
        if start is not None and end is not None and end > start:
            for left, right, crew in crew_pieces(task, start, end):  # 週ごとのタスクは、週の区間ごとの担当者で数える
                for key, allocation, _ in _shares(crew, names):
                    if isfinite(allocation):
                        planned[key] += allocation * sum(h for day, h in table(key) if _covers(left, right, day))
        for interval in task.actuals:
            seconds = (min(interval.end or now, high) - max(interval.start, low)).total_seconds()
            if seconds <= 0:
                continue
            # 実績は、区間の開始の日の担当者で按分する(週ごとのタスクは、その週の担当者)
            crew = crew_on(task, start.date(), interval.start.date()) if start is not None else task.assignees
            for key, _, share in _shares(crew, names):
                actual[key] += seconds / 3600 * share
```

- [ ] **Step 4: `handoff.py` を直す**

(a) import: `from projectapp.timeline import conversion_rate, effective_end, effective_start` に `consumed_slices, weekly_crews` を足す。

(b) `_estimate_hours` を置き換える(呼び出し元の `build_todos` も `holidays` を渡す形にする):

```python
def _estimate_hours(task: Task, project: Project, member_name: str, holidays: dict[date, str]) -> float:
    """担当者自身の時間での見積もり = 工数 × そのメンバーの割り当て率 ÷ 担当者全員の換算率の合計。
    担当が 1 人なら 工数 ÷ 相対比率 と同じ。週ごとのタスクは、工数を消化する区間のうち、そのメンバーが稼働した時間 × 割り当て率の合計。"""
    if not isfinite(task.effort_hours) or task.effort_hours <= 0:
        return 0.0
    if task.weekly_crew and (start := effective_start(task, project, holidays)) is not None:
        slices = consumed_slices(
            start,
            task.effort_hours,
            project.daily_hours,
            project.work_start,
            holidays,
            weeks=weekly_crews(task, project),
        )
        own = sum(
            (right - left).total_seconds() / 3600 * worker.allocation
            for left, right, active in slices
            for worker in active
            if worker.name == member_name
        )
        if own > 0:
            return round(own, 2)
    mine = next((a for a in task.assignees if a.name == member_name), None)
    allocation = mine.allocation if mine is not None else 1.0
    return round(task.effort_hours * allocation / conversion_rate(task, project), 2)
```
`"estimate_hours": _estimate_hours(task, project, member_name)` を `_estimate_hours(task, project, member_name, holidays)` にする。`handoff.py` の先頭の import に `date` がなければ `from datetime import date, …` に足す(`date` は既に使っていれば不要)。

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_dashboard.py test/test_dashboard_view.py test/test_handoff.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/dashboard.py src/projectapp/handoff.py test/test_weekly_crew.py
git commit -m "feat: ダッシュボードと担当者向けの見積もりを週ごとの担当で数える"
```

---

### Task 6: コピー・分解不可・見直し対象外・改名・PlantUML の通知

**Files:**
- Modify: `src/projectapp/arrange.py`, `src/projectapp/decompose.py`, `src/projectapp/reassign.py`, `src/projectapp/views.py`, `src/projectapp/plantuml.py`
- Test: `test/test_weekly_crew.py`, `test/test_views.py`, `test/test_plantuml.py`

- [ ] **Step 1: 失敗するテストを書く(`test/test_weekly_crew.py` に追加)**

import に `from projectapp.arrange import _plain_copy`、`from projectapp.decompose import decompose_block_reason`、`from projectapp.reassign import needs_review` を足す。

```python
def test_a_copy_has_its_own_weekly_crew() -> None:
    original = weekly_task("w", [[Assignee("田中")], [Assignee("鈴木", 0.5)]])
    copy = _plain_copy(original, "new", "w(コピー)")
    assert copy.weekly_crew == original.weekly_crew
    copy.weekly_crew[0][0].allocation = 0.1
    assert original.weekly_crew[0][0].allocation == 1.0


def test_a_weekly_task_cannot_be_decomposed() -> None:
    task = weekly_task("w", [[Assignee("田中")]])
    reason = decompose_block_reason(project_of(task), task)
    assert reason is not None and "週ごと" in reason


def test_a_weekly_task_is_not_reviewed_when_the_rate_changes() -> None:
    task = weekly_task("w", [[Assignee("田中")]], effort_hours=10.0, progress=50)
    assert not needs_review(task, 1.0, 0.5)
```

`test/test_views.py` の `test_renaming_a_member_renames_every_assignee_entry` の次に追加:

```python
async def test_renaming_a_member_renames_the_weekly_crew_too(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("A"), Member("B")]
    weeks = [[Assignee("A", 0.5)], [Assignee("A", 0.5), Assignee("B", 0.25)]]
    view.project.tasks = [Task("t", assignees=union_assignees(weeks), weekly_crew=weeks)]
    view.apply_members([Member("A改"), Member("B")], {"A": "A改"})
    task = view.project.tasks[0]
    assert [[a.name for a in week] for week in task.weekly_crew] == [["A改"], ["A改", "B"]]
    assert [a.name for a in task.assignees] == ["A改", "B"]
```
(import に `union_assignees` を足す。)

`test/test_plantuml.py` の末尾に追加:

```python
def test_weekly_tasks_are_counted_for_the_approximation_notice() -> None:
    weeks = [[Assignee("田中")], [Assignee("鈴木")]]
    weekly = task("a", "2026-10-12T09:00", "2026-10-20T17:00", assignees=[Assignee("田中"), Assignee("鈴木")], weekly_crew=weeks)
    plain = task("b", "2026-10-12T09:00", "2026-10-14T17:00", assignees=[Assignee("田中")])
    project = Project("p", members=[Member("田中"), Member("鈴木")], tasks=[weekly, plain])
    assert build(project).weekly_tasks == 1
    assert build(project, show_chips=False).weekly_tasks == 0  # 担当者を出さないときは近似にならない
    assert weekly_crew_notice(1) == "週ごとの担当は近似で出力しました(1 件。和集合の担当者を、各人の最大の割り当て率で出しています)"
    assert weekly_crew_notice(0) is None
```
import に `weekly_crew_notice` を足す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_views.py test/test_plantuml.py -q -k "weekly or copy or decomposed or reviewed or renaming"`
Expected: FAIL

- [ ] **Step 3: 本体を直す**

(a) `arrange.py` の `_plain_copy` の `assignees=[replace(a) for a in original.assignees],` の次の行に追加:

```python
        weekly_crew=[[replace(a) for a in week] for week in original.weekly_crew],
```

(b) `decompose.py` の `decompose_block_reason` の `if task.kind is not TaskKind.NORMAL:` ブロックの直後に追加:

```python
    if task.weekly_crew:
        return "週ごとに分けたタスクは分解できません"
```

(c) `reassign.py` の `needs_review` の `and task.status is not Status.DONE` の次の行に追加:

```python
        and not task.weekly_crew  # 週ごとのタスクは見直しの対象外(完了予定は自動算出のまま追従する)
```

(d) `views.py` の `apply_members` の改名のループを置き換える:

```python
        if renames:
            for task in self.project.all_tasks():
                for assignee in [*task.assignees, *(a for week in task.weekly_crew for a in week)]:
                    if assignee.name in renames:
                        assignee.name = renames[assignee.name]
```
(和集合と週は別々の `Assignee` なので、どちらも 1 回ずつ改名される。入れ替えでも取り違えない。)

(e) `plantuml.py`: `PlantUml` に項目を足す:

```python
    # 週ごとの担当を持つ出力したタスクの数(担当者を出したときだけ)。PlantUML は週ごとを表せず、和集合・最大の割り当て率の近似で出す
    weekly_tasks: int = 0
```
`day_overload_notice` の次に追加:

```python
def weekly_crew_notice(count: int) -> str | None:
    """週ごとの担当を近似で出力したことの通知。なければ None。"""
    if count <= 0:
        return None
    return f"週ごとの担当は近似で出力しました({count} 件。和集合の担当者を、各人の最大の割り当て率で出しています)"
```
`build_plantuml` の末尾の `return PlantUml(...)` を置き換える:

```python
    weekly_tasks = sum(1 for t in order if t.weekly_crew) if show_chips else 0
    return PlantUml("\n".join(lines) + "\n", len(aliases), skipped, day_overloads, weekly_tasks)
```

(f) `views.py` の `save_plantuml` の `day_overload_notice` の通知の次に追加(import に `weekly_crew_notice` を足す):

```python
            if (approx := weekly_crew_notice(result.weekly_tasks)) is not None:
                ui.notify(approx, type="warning", timeout=10000)
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_views.py test/test_plantuml.py test/test_summary.py test/test_arrange.py test/test_reassign.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/arrange.py src/projectapp/decompose.py src/projectapp/reassign.py src/projectapp/views.py src/projectapp/plantuml.py test/
git commit -m "feat: 週ごとのタスクのコピー・分解不可・見直し対象外・改名・PlantUML の通知を足す"
```

---

### Task 7: 編集ダイアログ

**Files:**
- Modify: `src/projectapp/forms.py`
- Modify: `src/projectapp/task_dialog.py`
- Test: `test/test_weekly_crew.py`, `test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 の `MAX_WEEKS`・`union_assignees`・`Task.weekly_crew`、Task 2 の `computed_end(weeks=…)`・`Worker`。
- Produces: `build_task(..., weekly_crew: list[list[tuple[str, float | None]]] | None = None)`(None は既存のまま、`[]` は週ごとに分けない)。`AssigneeFields(assignees, members, on_change, marker="task", title="担当者")`・`.assignee_list()`・`.set_assignees(assignees)`。`WeeklyCrewFields(weeks, members, on_change)`・`.weeks`・`.rows()`・`.crews()`・`.state()`・`.reset(weeks)`。印: `task-weekly`(スイッチ)・`task-week-add`・`task-week-N-remove`・`task-week-N-assignee[-k]`・`task-week-N-allocation[-k]`・`task-week-N-assignee-add`(N は 1 始まりの週、k は 2 行目以降の通し番号)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_weekly_crew.py` に追加(import に `build_task`・`Priority`・`DEFAULT_COLOR`・`MAX_WEEKS`・`TaskKind` を足す):

```python
def built(existing: Task | None = None, **kwargs: object) -> Task:
    values: dict[str, object] = dict(
        name="a", planned_start="", planned_end="", deadline="", effort_hours=None,
        priority=Priority.MEDIUM, status=Status.NOT_STARTED, color=DEFAULT_COLOR,
    )
    return build_task(existing, **{**values, **kwargs})  # type: ignore[arg-type]


def test_build_task_makes_the_weeks_and_the_union() -> None:
    rows = [[("田中", 100.0)], [("田中", 50.0), ("鈴木", 100.0)]]
    task = built(weekly_crew=rows)
    assert task.weekly_crew == [[Assignee("田中", 1.0)], [Assignee("田中", 0.5), Assignee("鈴木", 1.0)]]
    assert task.assignees == [Assignee("田中", 1.0), Assignee("鈴木", 1.0)]


def test_build_task_rejects_an_empty_week_and_a_duplicate_with_the_week_number() -> None:
    with pytest.raises(ValueError, match="第2週"):
        built(weekly_crew=[[("田中", 100.0)], [("", None)]])
    with pytest.raises(ValueError, match="第1週"):
        built(weekly_crew=[[("田中", 100.0), ("田中", 50.0)]])


def test_build_task_rejects_too_many_weeks() -> None:
    with pytest.raises(ValueError, match=str(MAX_WEEKS)):
        built(weekly_crew=[[("田中", 100.0)] for _ in range(MAX_WEEKS + 1)])
    assert len(built(weekly_crew=[[("田中", 100.0)] for _ in range(MAX_WEEKS)]).weekly_crew) == MAX_WEEKS


def test_build_task_keeps_the_weeks_when_none_and_clears_them_when_empty() -> None:
    existing = weekly_task("w", [[Assignee("田中")], [Assignee("鈴木")]])
    assert built(existing, assignees=[("田中", 100.0)]).weekly_crew == existing.weekly_crew
    cleared = built(existing, assignees=[("田中", 100.0)], weekly_crew=[])
    assert cleared.weekly_crew == [] and cleared.assignees == [Assignee("田中", 1.0)]


def test_a_checkpoint_has_no_weekly_crew() -> None:
    existing = weekly_task("w", [[Assignee("田中")]])
    checkpoint = built(existing, kind=TaskKind.CHECKPOINT, deadline="2026-10-09 17:00")
    assert checkpoint.weekly_crew == [] and checkpoint.assignees == []
```

`test/test_task_dialog.py` の末尾に追加:

```python
WEEKS = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木", 0.5)]]


def weekly_task_of(**kwargs) -> Task:
    return Task("週", assignees=[Assignee("田中"), Assignee("鈴木", 0.5)], weekly_crew=[list(w) for w in WEEKS], **kwargs)


async def test_the_weekly_switch_is_off_for_a_plain_task(user: User) -> None:
    mount_dialog(Task("通常", assignees=[Assignee("田中")]), [], members=[TANAKA, SUZUKI])
    await open_dialog(user)
    assert user.find(marker="task-weekly").elements.pop().value is False
    await user.should_see(marker="task-assignee")
    await user.should_not_see(marker="task-week-1-assignee")


async def test_a_weekly_task_shows_its_weeks_and_saves_them_unchanged(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(weekly_task_of(), saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    await user.should_see(marker="task-week-2-assignee-2")
    await user.should_not_see(marker="task-assignee")
    assert user.find(marker="task-week-2-assignee-2").elements.pop().value == "鈴木"
    assert user.find(marker="task-week-2-allocation-2").elements.pop().value == 50
    user.find(marker="task-save").click()
    assert saved[0].weekly_crew == WEEKS
    assert saved[0].assignees == [Assignee("田中"), Assignee("鈴木", 0.5)]


async def test_turning_weekly_on_starts_from_the_current_assignees_and_adds_weeks(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
        user.find(marker="task-weekly").elements.pop().set_value(True)
    await user.should_see(marker="task-week-1-assignee")
    assert user.find(marker="task-week-1-assignee").elements.pop().value == "田中"
    user.find(marker="task-week-add").click()
    await user.should_see(marker="task-week-2-assignee")  # 直前の週のコピー
    assert user.find(marker="task-week-2-assignee").elements.pop().value == "田中"
    user.find(marker="task-week-2-assignee-add").click()
    await user.should_see(marker="task-week-2-assignee-2")
    with user.client:
        user.find(marker="task-week-2-assignee-2").elements.pop().set_value("鈴木")
    user.find(marker="task-save").click()
    assert saved[0].weekly_crew == [[Assignee("田中", 1.0)], [Assignee("田中", 1.0), Assignee("鈴木", 1.0)]]
    assert saved[0].assignees == [Assignee("田中", 1.0), Assignee("鈴木", 1.0)]


async def test_a_week_without_an_assignee_is_an_error(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(weekly_task_of(), saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    with user.client:
        user.find(marker="task-week-2-assignee").elements.pop().set_value("")
        user.find(marker="task-week-2-assignee-2").elements.pop().set_value("")
    user.find(marker="task-save").click()
    assert "第2週" in user.find(marker="form-error").elements.pop().text
    assert saved == []


async def test_removing_a_week_renumbers_the_rest(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(weekly_task_of(), saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-week-1-remove").click()
    await user.should_not_see(marker="task-week-2-assignee")
    assert user.find(marker="task-week-1-assignee").elements.pop().value == "田中"
    assert user.find(marker="task-week-1-assignee-2").elements.pop().value == "鈴木"
    user.find(marker="task-save").click()
    assert saved[0].weekly_crew == [WEEKS[1]]


async def test_turning_weekly_off_gives_the_first_week_back_to_the_assignees(user: User) -> None:
    saved: list[Task] = []
    weeks = [[Assignee("鈴木", 0.5)], [Assignee("田中")]]
    task = Task("週", assignees=[Assignee("鈴木", 0.5), Assignee("田中")], weekly_crew=weeks)
    mount_dialog(task, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    with user.client:
        user.find(marker="task-weekly").elements.pop().set_value(False)
    await user.should_see(marker="task-assignee")
    user.find(marker="task-save").click()
    assert saved[0].weekly_crew == []
    assert saved[0].assignees == [Assignee("鈴木", 0.5)]


async def test_the_conversion_lists_each_week(user: User) -> None:
    mount_dialog(weekly_task_of(effort_hours=20.0), [], members=[TANAKA, SUZUKI])
    await open_dialog(user)
    text = user.find(marker="task-conversion").elements.pop().text
    assert text == "換算率 第1週: 田中 120%×100% = 120% / 第2週: 田中 120%×100% + 鈴木 100%×50% = 170%"


async def test_the_computed_end_follows_the_weeks(user: User) -> None:
    a, b = Member("田中", 1.0), Member("鈴木", 1.0)
    task = Task(
        "週",
        planned_start=datetime(2026, 10, 7, 9, 0),
        effort_hours=40.0,
        assignees=[Assignee("田中"), Assignee("鈴木")],
        weekly_crew=[[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]],
    )
    mount_dialog(task, [], members=[a, b])
    await open_dialog(user)
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-14 12:45"


async def test_the_decompose_button_is_hidden_for_a_weekly_task(user: User) -> None:
    mount_dialog(weekly_task_of(), [], members=[TANAKA, SUZUKI], on_decompose=lambda close: None)
    await open_dialog(user)
    await user.should_not_see(marker="task-decompose")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_task_dialog.py -q -k "weekly or build_task or week"`
Expected: FAIL

- [ ] **Step 3: `forms.py` を直す**

(a) import: `from projectapp.models import (...)` に `MAX_WEEKS,` と `union_assignees,` を足す。

(b) `_build_assignees` の直後に追加:

```python
def _build_weekly_crew(weeks: list[list[tuple[str, float | None]]]) -> list[list[Assignee]]:
    """週ごとの担当の入力を検証する。各週に担当者が最低 1 人で、週数は上限まで。エラーには週の番号を添える。"""
    if len(weeks) > MAX_WEEKS:
        raise ValueError(f"週は{MAX_WEEKS}週までです")
    result: list[list[Assignee]] = []
    for number, rows in enumerate(weeks, start=1):
        try:
            crew = _build_assignees(rows)
        except ValueError as exc:
            raise ValueError(f"第{number}週: {exc}") from None
        if not crew:
            raise ValueError(f"第{number}週に担当者を選んでください")
        result.append(crew)
    return result
```

(c) `build_task` の引数 `parameters: list[str] | None = None,` の次に追加:

```python
    weekly_crew: list[list[tuple[str, float | None]]] | None = None,
```
(docstring に「`weekly_crew` は None なら既存のまま、空なら週ごとに分けない」を一文足す。)

(d) `assignee_list = _build_assignees(assignees or [])` の次の行に追加:

```python
    weeks = [list(week) for week in base.weekly_crew] if weekly_crew is None else _build_weekly_crew(weekly_crew)
```
最後の `replace(...)` の `assignees=assignee_list,` を、次の 2 行に置き換える:

```python
        assignees=union_assignees(weeks) if weeks else assignee_list,
        weekly_crew=weeks,
```

(e) `_build_checkpoint` の `replace(...)` の `assignees=[],` の次の行に `weekly_crew=[],` を足す。

- [ ] **Step 4: `task_dialog.py` を直す**

(a) import: `from projectapp.models import (...)` に `MAX_WEEKS,` を足し、`from projectapp.timeline import Worker, assignees_rate, combine_rate, computed_end, crew_of, effort_days` はそのまま使う。

(b) `AssigneeFields` を直す。`__init__` の定義を次にする(`marker`・`title` を足す):

```python
    def __init__(
        self,
        assignees: list[Assignee],
        members: list[Member],
        on_change: Callable[[], object],
        marker: str = "task",
        title: str = "担当者",
    ) -> None:
        self.members = members
        self.on_change = on_change
        self.marker = marker
```
(元の `self.members = members` と `self.on_change = on_change` の 2 行は、この中に含めて置き換える。)

`ui.label("担当者").classes("text-caption text-grey")` を `ui.label(title).classes("text-caption text-grey")` に、`.mark(\n                "task-assignee-add"\n            )` を `.mark(\n                f"{self.marker}-assignee-add"\n            )` に、`_add_row` の `.mark(f"task-assignee{suffix}")`・`.mark(f"task-allocation{suffix}")`・`.mark(f"task-assignee-remove{suffix}")` を、それぞれ `f"{self.marker}-assignee{suffix}"`・`f"{self.marker}-allocation{suffix}"`・`f"{self.marker}-assignee-remove{suffix}"` にする。

`rows` の前に 2 つのメソッドを足す:

```python
    def assignee_list(self) -> list[Assignee]:
        """メンバーを選んだ行を Assignee にしたもの(割り当て率の空は 100%)。"""
        return [Assignee(name, (percent or 100) / 100) for name, percent in self.rows() if name]

    def set_assignees(self, assignees: list[Assignee]) -> None:
        """行を作り直す(オフにしたとき、第1週の担当を全期間の担当に戻す)。"""
        for item in self.items:
            item.row.delete()
        self.items.clear()
        self.counter = 0
        for assignee in assignees or [None]:
            self._add_row(assignee)
        self._sync()
        self.on_change()
```

(c) `AssigneeFields` の後ろ、`def _title_table` の前に追加:

```python
class WeeklyCrewFields:
    """週ごとの担当の節。1 週が 1 ブロックで、中は担当者の欄(AssigneeFields)。印は task-week-N-…(N は 1 始まり)。"""

    def __init__(self, weeks: list[list[Assignee]], members: list[Member], on_change: Callable[[], object]) -> None:
        self.members = members
        self.on_change = on_change
        self.weeks: list[AssigneeFields] = []
        self._removes: list[ui.button] = []
        self.container = ui.column().classes("w-full gap-2")
        with self.container:
            ui.label("週ごとの担当(開始予定の日から 7 日ごと。最後の週の担当は、その後も続く)").classes(
                "text-caption text-grey"
            )
            self.box = ui.column().classes("w-full gap-2")
            self.add_button = (
                ui.button("週を追加", icon="add", on_click=self._add_copy).props("flat dense").mark("task-week-add")
            )
        for week in weeks or [[]]:
            self._add(week)
        self._sync()

    def _remover(self, number: int) -> Callable[[], None]:
        return lambda: self._remove(number - 1)

    def _add(self, assignees: list[Assignee]) -> None:
        number = len(self.weeks) + 1
        with self.box:
            with ui.column().classes("w-full gap-1"):
                with ui.row().classes("w-full items-center"):
                    ui.label(f"第{number}週").classes("text-subtitle2")
                    ui.space()
                    remove = (
                        ui.button(icon="delete", on_click=self._remover(number))
                        .props("flat dense color=negative")
                        .mark(f"task-week-{number}-remove")
                    )
                fields = AssigneeFields(assignees, self.members, self.on_change, marker=f"task-week-{number}")
        self.weeks.append(fields)
        self._removes.append(remove)

    def _sync(self) -> None:
        self.add_button.set_enabled(len(self.weeks) < MAX_WEEKS)
        for remove in self._removes:
            remove.set_visibility(len(self.weeks) > 1)

    def _add_copy(self) -> None:
        """直前の週の担当をコピーして、週を足す。"""
        if len(self.weeks) >= MAX_WEEKS:
            return
        self._add(self.weeks[-1].assignee_list() if self.weeks else [])
        self._sync()
        self.on_change()

    def _remove(self, index: int) -> None:
        if len(self.weeks) <= 1:
            return
        weeks = self.crews()
        del weeks[index]
        self.reset(weeks)

    def reset(self, weeks: list[list[Assignee]]) -> None:
        """週のブロックを作り直す(番号を振り直すため)。"""
        self.box.clear()
        self.weeks.clear()
        self._removes.clear()
        for week in weeks or [[]]:
            self._add(week)
        self._sync()
        self.on_change()

    def crews(self) -> list[list[Assignee]]:
        return [fields.assignee_list() for fields in self.weeks]

    def rows(self) -> list[list[AssigneeRow]]:
        return [fields.rows() for fields in self.weeks]

    def state(self) -> tuple[tuple[AssigneeRow, ...], ...]:
        return tuple(fields.state() for fields in self.weeks)
```

(d) `DateTimeFields`: `__init__` の引数 `crew: Sequence[Worker] = (),` の次に `weeks: Sequence[Sequence[Worker]] = (),` を足し、`self._crew = list(crew)` の次に `self._weeks = [list(week) for week in weeks]` を足す。`set_crew` を置き換える:

```python
    def set_crew(self, crew: Sequence[Worker], weeks: Sequence[Sequence[Worker]] = ()) -> None:
        self._crew = list(crew)
        self._weeks = [list(week) for week in weeks]
        self._refresh_end()
```
`_computed_end` の `crew=self._crew,` の次の行に `weeks=self._weeks or None,` を足す。

(e) `open_task_dialog` の中:

- `fields = DateTimeFields(initial, work_start, daily_hours, holidays or {}, crew_of(initial.assignees, member_list))` を、`weeks=[crew_of(week, member_list) for week in initial.weekly_crew]` を足した形にする(複数行に整える)。
- `assignee_fields = AssigneeFields(initial.assignees, member_list, lambda: refresh_conversion())` を、次の 3 行に置き換える:

```python
        weekly_switch = ui.switch("週ごとに分ける", value=bool(initial.weekly_crew)).mark("task-weekly")
        assignee_fields = AssigneeFields(initial.assignees, member_list, lambda: refresh_conversion())
        weekly_fields = WeeklyCrewFields(
            initial.weekly_crew or [initial.assignees], member_list, lambda: refresh_conversion()
        )
```
- `refresh_conversion` を置き換える:

```python
        def refresh_conversion(_event: object = None) -> None:
            tagged = f"・{'・'.join(chosen_parameters)}を反映" if chosen_parameters else ""
            if weekly_switch.value:
                weeks = [week.chosen() for week in weekly_fields.weeks]
                fields.set_crew(
                    [],
                    [[Worker(combine_rate(m.ratio, f), work_day_map(m.work_days)) for m, f in week] for week in weeks],
                )
                if not (effort.value or 0.0) > 0 or not any(weeks):
                    conversion.set_text("")
                    return
                parts = []
                for number, week in enumerate(weeks, start=1):
                    rate = sum(combine_rate(m.ratio, f) for m, f in week) if week else 1.0
                    detail = " + ".join(f"{m.name} {m.ratio * 100:g}%×{f * 100:g}%" for m, f in week) or "担当なし"
                    parts.append(f"第{number}週: {detail} = {rate * 100:g}%")
                conversion.set_text(f"換算率 {' / '.join(parts)}{tagged}")
                return
            chosen = assignee_fields.chosen()
            rate = sum(combine_rate(m.ratio, f) for m, f in chosen) if chosen else 1.0
            fields.set_crew([Worker(combine_rate(m.ratio, f), work_day_map(m.work_days)) for m, f in chosen])
            days = effort_days(effort.value or 0.0, rate, daily_hours) if chosen else None
            if not chosen or days is None:
                conversion.set_text("")
                return
            detail = " + ".join(f"{m.name} {m.ratio * 100:g}%×{f * 100:g}%" for m, f in chosen)
            conversion.set_text(f"換算率 {rate * 100:g}%({detail}{tagged})→ {effort.value:g}h は約 {days:.1f}日分")
```
(元の `refresh_conversion` の `detail`・`tagged` の組み立てと同じ文面を保つこと。非週ごとの文面は変えない。)

- `effort.on_value_change(on_effort_change)` の次に追加:

```python
        def on_weekly_change(event: ValueChangeEventArguments) -> None:
            if event.value:  # 今の担当を第1週にして始める
                weekly_fields.reset([assignee_fields.assignee_list()])
            else:  # 第1週の担当を、全期間の担当に戻す
                first = weekly_fields.crews()[:1]
                assignee_fields.set_assignees(first[0] if first else [])
            refresh_visibility()
            refresh_conversion()

        weekly_switch.on_value_change(on_weekly_change)
```

- `refresh_visibility` のまとめの分岐の隠す一覧に `weekly_switch, weekly_fields.container,` を足す(`assignee_fields.container,` の隣)。通常の分岐の `assignee_fields.container.set_visibility(full and normal)` を、次に置き換える:

```python
            weekly = bool(weekly_switch.value)
            weekly_switch.set_visibility(full and normal)
            assignee_fields.container.set_visibility(full and normal and not weekly)
            weekly_fields.container.set_visibility(full and normal and weekly)
```

- `current()` の `assignee_fields.state(),` の次に `weekly_switch.value, weekly_fields.state() if weekly_switch.value else (),` を足す。
- `build_task(...)` の呼び出しの `assignees=assignee_fields.rows(),` の次に `weekly_crew=weekly_fields.rows() if weekly_switch.value else [],` を足す。
- `if task is not None and needs_review(result, initial_rate, new_rate)` を `if task is not None and not task.weekly_crew and needs_review(result, initial_rate, new_rate)` にする(週ごとだったタスクを通常に戻す保存で、意味のない見直しを出さない)。
- 分解ボタンの条件 `and task.progress is None\n            ):` を `and task.progress is None\n                and not task.weekly_crew\n            ):` にする。

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_weekly_crew.py test/test_task_dialog.py test/test_forms.py test/test_decompose_ui.py -q`
Expected: PASS(既存のダイアログのテストの印 `task-assignee…` は `marker="task"` の既定で変わらない)

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py test/
git commit -m "feat: タスクの編集ダイアログで担当を週ごとに分けられるようにする"
```

---

### Task 8: ガントチャートの棒の上の週ごとのチップ

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: Task 3 の `crew_pieces`。
- Produces(`gantt.py`): `week_chip_text(names: list[str], width_px: float, scale: Scale) -> str`・`week_summary(task: Task) -> str`・`GanttChart.week_chips(...)`。印: `week-chip-{key}-{ti}-{n}`(n は 0 始まりの区間)。

- [ ] **Step 1: 失敗するテストを書く(`test/test_gantt.py` の末尾に追加)**

import に `week_chip_text`・`week_summary` を足す(`from projectapp.gantt import (...)` のブロック)。`Scale` が未 import なら `from projectapp.timeline import Scale` を足す。

```python
def weekly_chart_project() -> Project:
    weeks = [[Assignee("田中")], [Assignee("鈴木", 0.5)]]
    task = Task(
        "週",
        planned_start=datetime(2026, 10, 5),
        planned_end=datetime(2026, 10, 19),
        assignees=[Assignee("田中"), Assignee("鈴木", 0.5)],
        weekly_crew=weeks,
    )
    return Project("demo", base_date=BASE, members=[Member("田中"), Member("鈴木")], tasks=[task])


def test_week_chip_text_shows_initials_only_on_the_day_scale_with_room() -> None:
    assert week_chip_text(["田中", "鈴木"], 200.0, Scale.DAY) == "田鈴"
    assert week_chip_text(["田中", "鈴木", "佐藤", "高橋", "伊藤"], 200.0, Scale.DAY) == "田鈴佐+2"
    assert week_chip_text(["田中"], 10.0, Scale.DAY) == ""  # 幅が足りない
    assert week_chip_text(["田中"], 200.0, Scale.WEEK) == ""  # 週次・月次は区切りだけ
    assert week_chip_text([], 200.0, Scale.DAY) == ""


def test_week_summary_lists_each_week_for_the_hover() -> None:
    task = Task("w", weekly_crew=[[Assignee("田中")], [Assignee("田中", 0.5), Assignee("鈴木")]])
    assert week_summary(task) == "第1週: 田中 100%\n第2週: 田中 50%、鈴木 100%"
    assert week_summary(Task("p", assignees=[Assignee("田中")])) == ""


async def test_the_bar_carries_one_chip_per_week(user: User) -> None:
    mount(weekly_chart_project())
    await user.open("/")
    first = user.find(marker="week-chip-top-0-0").elements.pop()
    second = user.find(marker="week-chip-top-0-1").elements.pop()
    # 10/5〜10/19 の棒。1 日 40px なので、第1週(10/5〜11)は左 0・幅 280、第2週は左 280・幅 280
    assert (first._style["left"], first._style["width"]) == ("0.0px", "280.0px")
    assert (second._style["left"], second._style["width"]) == ("280.0px", "280.0px")
    assert (first.text, second.text) == ("田", "鈴")
    assert "border-left" not in first._style and "border-left" in second._style  # 区切り線は 2 つ目から


async def test_the_chips_follow_the_chip_option(user: User) -> None:
    mount_with(weekly_chart_project(), ViewOptions(show_chips=False))
    await user.open("/")
    await user.should_not_see(marker="week-chip-top-0-0")


async def test_a_plain_task_has_no_week_chips(user: User) -> None:
    mount(overloaded_project())
    await user.open("/")
    await user.should_not_see(marker="week-chip-top-0-0")


async def test_a_bar_that_ends_in_the_first_week_has_one_chip(user: User) -> None:
    project = weekly_chart_project()
    project.tasks[0].planned_end = datetime(2026, 10, 8)
    mount(project)
    await user.open("/")
    await user.should_see(marker="week-chip-top-0-0")
    await user.should_not_see(marker="week-chip-top-0-1")
    assert user.find(marker="week-chip-top-0-0").elements.pop()._style["width"] == "120.0px"  # 3 日
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "week"`
Expected: FAIL

- [ ] **Step 3: `gantt.py` を直す**

(a) import: `from projectapp.timeline import (...)` に `crew_pieces,` を足す。

(b) 定数を `MAX_ASSIGNEE_CHIPS = 3 …` の近くに追加:

```python
WEEK_CHIP_HEIGHT_PX = 12  # 棒の上の週ごとのチップの高さ
MIN_WEEK_CHIP_TEXT_PX = 24  # 週ごとのチップに頭文字を出す最小の幅(これより狭いときは区切りだけ)
```

(c) モジュールの関数として追加(`fill_percent` の近く):

```python
def week_chip_text(names: list[str], width_px: float, scale: Scale) -> str:
    """棒の上の週ごとのチップの文字。日次で幅が足りるときだけ頭文字を出す(4 人目以降は +n)。"""
    if scale is not Scale.DAY or width_px < MIN_WEEK_CHIP_TEXT_PX or not names:
        return ""
    rest = len(names) - MAX_ASSIGNEE_CHIPS
    return "".join(name[0] for name in names[:MAX_ASSIGNEE_CHIPS]) + (f"+{rest}" if rest > 0 else "")


def week_summary(task: Task) -> str:
    """週ごとの担当の説明(マウスオーバー用)。週ごとに分けないタスクは空。"""
    return "\n".join(
        f"第{number}週: " + "、".join(f"{a.name} {round(a.allocation * 100)}%" for a in week)
        for number, week in enumerate(task.weekly_crew, start=1)
    )
```

(d) `task_row` の `with bar:` ブロックを直す。`self.overload_stripes(...)` の `if self.options.show_alerts:` ブロックの次に追加:

```python
                    if self.options.show_chips and task.weekly_crew:
                        self.week_chips(key, ti, task, start, end, left, bar_width, columns, width)
```

(e) `overload_stripes` の直前にメソッドを追加:

```python
    def week_chips(
        self,
        key: int | str,
        ti: int,
        task: Task,
        start: datetime,
        end: datetime,
        bar_left: float,
        bar_width: float,
        columns: list[Column],
        width: int,
    ) -> None:
        """棒の上に、週ごと(実効の開始の日から 7 日ごと)の担当のチップを重ねる。2 つ目からは左端に区切り線を付ける。"""
        pieces = crew_pieces(task, start, end)
        for n, (left, right, crew) in enumerate(pieces):
            origin, length = interval_span(left, right, columns)
            left_px = max((origin - bar_left) * width, 0.0)
            width_px = min(length * width, bar_width - left_px)
            if width_px <= 0:
                continue
            divider = " border-left: 1px solid rgba(255,255,255,0.8);" if n else ""
            chip = ui.label(week_chip_text([a.name for a in crew], width_px, self.view_scale)).style(
                f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px; top: 0;"
                f" height: {WEEK_CHIP_HEIGHT_PX}px; font-size: 10px; line-height: {WEEK_CHIP_HEIGHT_PX}px;"
                f" color: #fff; background: rgba(0,0,0,0.3); padding-left: 3px; overflow: hidden;"
                f" white-space: nowrap;{divider}"
            )
            last = n == len(pieces) - 1 and len(pieces) == len(task.weekly_crew)
            title = f"第{n + 1}週{'以降' if last else ''}: " + "、".join(
                f"{a.name} {round(a.allocation * 100)}%" for a in crew
            )
            chip.tooltip(title).mark(f"week-chip-{key}-{ti}-{n}")
```

(f) `task_chips` を直す。ループの前に `note = f"\n{summary}" if (summary := week_summary(task)) else ""` を足し、担当者のアバターのツールチップを `f"{assignee.name} {round(assignee.allocation * 100)}%{note}"` に、「+n」のツールチップを `"\n".join(...) + note` にする。

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `uv run pytest test/test_gantt.py test/test_preview.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: ガントチャートの棒の上に週ごとの担当のチップを出す"
```

---

### Task 9: 仕様と記録を更新して、全体を確認する

**Files:**
- Modify: `CLAUDE.md`(`projectapp/CLAUDE.md`)、`docs/development.md`、`docs/requests.md`、`docs/superpowers/specs/2026-10-24-weekly-crew-design.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

(a) 「人的リソース1人に対して、project内で、最大`100%`まで分散できる」の行の直前に追加:

```
- タスクの担当者は、`週ごとに分ける`で、開始の日から 7 日(暦日)ごとの週ごとに変えられる(編集ダイアログの`すべて`レイアウトの担当欄のスイッチ。オンにすると今の担当が第1週になり、`週を追加`は直前の週をコピーする。オフにすると第1週の担当が全期間の担当に戻る)。各週に担当者が最低 1 人で、割り当て率は週ごとに持つ。週は先行による押し出しを反映した実効の開始から数え、最後の週の担当はその後も続く。週数の上限は 52。完了予定は、その日の担当者の換算率の合計で工数を消化して算出する(週ごとに分けないタスクは今までどおり)。割り当て超過・ダッシュボードの負荷と予定工数・担当者向けファイルの見積もりも、週ごとの担当で数える。`assignees`は全週の和集合(割り当て率は各人の最大値)で、名前の欄のチップはこれを使う。ガントチャートの棒の上には、週ごとの担当のチップを重ねる(日次は頭文字、週次・月次は区切りだけ。表示項目のチップに従う)。週ごとのタスクは、担当の付け替え時の見直し確認の対象外で、分解できない。PlantUML は和集合・各人の最大の割り当て率で出し、近似であることを通知する。3 者マージは`weekly_crew`をリスト全体で 1 項目として比べ、消えたメンバーで空になった週は隣の週と同じにして通知する
```

(b) 「プロジェクトファイルの先頭に`version`(整数。現在 9。8 でメンバーの`work_days`を、9 でタスクの`parameters`を足した)」を「(整数。現在 10。8 でメンバーの`work_days`を、9 でタスクの`parameters`を、10 でタスクの`weekly_crew`を足した)」に直す。

- [ ] **Step 2: `docs/development.md` を更新する**

`grep -n "version\|parameters" docs/development.md` で、ファイル形式の注意の節を探し、`version` 10 と `tasks[].weekly_crew`(週の配列。各週は`assignees`と同じ形の配列。`assignees`は読込で和集合に整える)を追記する。モジュール構成の表に、`timeline.py` の`crew_on`・`crew_pieces`・`calc_end(weeks=…)`、`task_dialog.py` の`WeeklyCrewFields` を一行ずつ足す。

- [ ] **Step 3: `docs/requests.md` と設計書の状態を更新する**

`docs/requests.md` の要望 54 の`> **状態**:` の行を「実装済み(2026-10-24。実機確認待ち)。設計書 …、実装計画 `2026-10-24-weekly-crew.md`。」に直す。設計書の先頭の状態の行も「実装済み(実機確認待ち)」にし、「決めたこと」の表の後ろに 2 行を足す:

```
| 週数の上限 | 52 週(読込とダイアログの保存で拒否する。設計の後で足した防御) |
| ダイアログの換算率 | 週ごとに内訳と換算率を出す。日数の換算は、週ごとには意味がないので出さない |
```

- [ ] **Step 4: 全体を確認する**

Run: `uv run ty check src`
Expected: エラーなし

Run(バックグラウンド): `uv run pytest -q`
Expected: すべて PASS(約 4 分)

- [ ] **Step 5: 実機で確認してもらう項目を整理する**

`uv run projectapp` で、次をユーザーに確認してもらう(実機確認はユーザーが行う):
1. 3 人のメンバーで、例の 5 週(A / A,B / B,C / A,B,C / A)を入力し、棒の上のチップが読めて、完了予定が人数の多い週に早く進む。
2. 週ごとのスイッチのオン・オフで担当が消えない。
3. 同じメンバーの別タスクと重なる週だけに、割り当て超過の縞が出る。
4. 保存・読込で週ごとの担当が残る。

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "docs: 要望 54(週ごとの担当割り当て)の仕様と記録を更新する"
```
