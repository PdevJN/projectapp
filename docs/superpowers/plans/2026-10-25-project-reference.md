# プロジェクト参照 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの種別`プロジェクト参照`を足し、他のプロジェクトの全体の予定・実績・進捗・遅延・負荷を、細かなタスクを見せずにガントチャートへ載せる(クリックで参照先へ切り替え。PNG・PlantUML 対応)。

**Architecture:** 参照値の算出は NiceGUI に依存しない純粋関数(`reference.py`)。参照の方式(`常に最新`/`スナップショット`)はプロジェクトの設定。`常に最新`はファイルの内容のハッシュでキャッシュしつつ表示のたびに算出し、`スナップショット`は参照行ごとに値を保存する。`Schedule` が参照値を受け取り、参照行の開始・完了を返す(先行・矢印・PlantUML は既存の経路をそのまま使う)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、型検査 `uv run ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-25-project-reference-design.md`(要望 56。記録は `docs/requests.md`)

## Global Constraints

- 言語・表示は日本語。コメント・docstring は既存の密度と文体にそろえる(日本語、「〜する」調)。
- `reference.py` と `models.py` の追加は NiceGUI に依存しない(`timeline.py` と同じ方針)。
- 保存形式は `version` を 10 → 11 に上げる。キーのない古いファイルは既定値(`reference_mode=live`、参照行なし)で読み、このアプリより新しい version は拒否し、不正な値は読込を拒否する。
- 参照行が持つのは、名前・色・先行・締切・`ref_project`・`ref_snapshot` だけ。工数・担当・週ごとの担当・実績・進捗度・パラメータ・カテゴリ・リンクは持たず、状態は`未着手`固定、優先度は`中`固定(読込と保存で空にそろえる)。
- 参照先の集計は、参照先の通常タスクとチェックポイントだけを数える(まとめ・参照行は数えない。参照が循環しても再帰しない)。自分自身は参照できない。
- 日付のヒント表記は `9/7`(`gantt.short_date`)。通知・ダイアログの文言はこの計画の文字列どおりにする。
- テスト関数は、既存のとおり、`async def test_...(user: User)` を `pytest-asyncio`/NiceGUI の `user` フィクスチャで書く(`@pytest.mark.anyio` は付けない)。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. 参照先のファイルが壊れている(JSON でない・version が新しい)とき: 参照行は残り、帯なしで`参照先を読めません`の理由が出る。アプリは止まらない(Task 4 の読めない場合、Task 7 の通知)。
2. 参照先にタスクが 1 件もないとき: 日程なしの参照値になり、帯は出ない。エラーにしない(Task 2)。
3. 参照先のプロジェクト名を自分と同じにしたとき(自己参照): 読込は拒否、ダイアログの選択肢には自分を出さない(Task 1・5)。
4. `スナップショット`で、参照先が見つからないとき: 保存した値で出す(Task 4・6)。スナップショットが空(切り替え前に参照を足したなど)のときは、帯なし。
5. 参照行を先行にしたタスクが、参照先の遅れで押し出される(Task 3)。参照先が全部終了していれば実績の終了を使う。
6. プロジェクトの切り替え直後(別のプロジェクトを開いた直後)に、古い参照先のキャッシュを使わない(Task 4: キャッシュはファイルの内容のハッシュと日付で引く)。

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/models.py`(変更) | `TaskKind.REFERENCE`・`ReferenceMode`・`ReferenceValue`・`OverloadSpan`・`Task.ref_project`/`ref_snapshot`・`Project.reference_mode`・`FORMAT_VERSION = 11` |
| `src/projectapp/storage.py`(変更) | 参照行・参照値・参照方式の読込検証。保存は `asdict` で自動 |
| `src/projectapp/reference.py`(新規) | 参照値の算出(`compute_reference`)・参照先の読み込みとキャッシュ(`ReferenceResolver`)・行ごとの参照(`Reference`・`build_references`・`take_snapshot`)・見つからないファイルの一覧 |
| `src/projectapp/timeline.py`(変更) | `Schedule(references=)`・参照行の開始/完了・先行としての完了・超過・進捗の状態 |
| `src/projectapp/dashboard.py`(変更) | 参照行を集計から外す |
| `src/projectapp/forms.py`(変更) | `build_task` の参照行・設定ダイアログの`参照の方式` |
| `src/projectapp/task_dialog.py`(変更) | 種別トグルに`プロジェクト参照`・参照先の選択欄 |
| `src/projectapp/gantt.py`(変更) | 参照行の描画・クリック・右クリックの`更新`・`GanttActions` |
| `src/projectapp/views.py`(変更) | 参照の解決・クリックの確認ダイアログ・`更新`・設定の適用・見つからない通知 |
| `src/projectapp/plantuml.py`(変更) | 参照行を帯で出す |
| `src/projectapp/merge.py`(変更) | 参照の項目を 3 者マージに載せる(確認のみ) |
| `test/test_reference.py`(新規) | 算出・読み込み・参照の組み立て |
| 既存テスト | 各 Task で足す(`test_storage*.py`、`test_timeline.py`、`test_gantt.py`、`test_views.py`、`test_task_dialog.py`、`test_plantuml.py`、`test_merge.py`) |

---

### Task 1: モデルと保存(version 11)

**Files:**
- Modify: `src/projectapp/models.py`(`TaskKind` の近く、`Task`、`Project`、`FORMAT_VERSION`)
- Modify: `src/projectapp/storage.py`(`_task`、`parse_project`、新しい検証関数)
- Test: `test/test_reference_storage.py`(新規)

**Interfaces:**
- Produces:
  - `TaskKind.REFERENCE = "プロジェクト参照"`
  - `ReferenceMode(StrEnum)`: `LIVE = "live"`、`SNAPSHOT = "snapshot"`
  - `OverloadSpan(member: str, start: datetime, end: datetime, total: float)`(frozen)
  - `ReferenceValue(planned_start, planned_end, actual_start, actual_end: datetime | None = None, progress: int | None = None, finished: bool = False, delayed: int = 0, peak_load: float = 0.0, peak_member: str = "", overloads: tuple[OverloadSpan, ...] = (), taken_at: datetime | None = None)`(frozen)と `same_as(other) -> bool`(`taken_at` を除いて比べる)
  - `Task.ref_project: str = ""`、`Task.ref_snapshot: ReferenceValue | None = None`、`Project.reference_mode: ReferenceMode = ReferenceMode.LIVE`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_reference_storage.py`:

```python
import json
from datetime import datetime

import pytest

from projectapp.models import (
    FORMAT_VERSION,
    OverloadSpan,
    Project,
    ReferenceMode,
    ReferenceValue,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.storage import dumps_project, parse_project

VALUE = ReferenceValue(
    planned_start=datetime(2026, 9, 7, 9),
    planned_end=datetime(2026, 11, 20, 17),
    actual_start=datetime(2026, 9, 7, 10),
    actual_end=None,
    progress=45,
    finished=False,
    delayed=3,
    peak_load=1.3,
    peak_member="田中",
    overloads=(OverloadSpan("田中", datetime(2026, 10, 1, 9), datetime(2026, 10, 3, 9), 1.3),),
    taken_at=datetime(2026, 10, 25, 10),
)


def reference_task(**kwargs: object) -> Task:
    return Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤", **kwargs)  # type: ignore[arg-type]


def test_format_version_is_11() -> None:
    assert FORMAT_VERSION == 11


def test_a_reference_task_round_trips_with_its_snapshot() -> None:
    project = Project("p", reference_mode=ReferenceMode.SNAPSHOT, sections=[Section("s", [reference_task(ref_snapshot=VALUE)])])
    loaded = parse_project(dumps_project(project), "p")
    task = loaded.sections[0].tasks[0]
    assert loaded.reference_mode is ReferenceMode.SNAPSHOT
    assert (task.kind, task.ref_project, task.ref_snapshot) == (TaskKind.REFERENCE, "基盤", VALUE)


def test_a_live_project_drops_the_snapshots_on_load() -> None:
    project = Project("p", reference_mode=ReferenceMode.LIVE, tasks=[reference_task(ref_snapshot=VALUE)])
    assert parse_project(dumps_project(project), "p").tasks[0].ref_snapshot is None


def test_an_old_file_reads_with_the_defaults() -> None:
    raw = json.loads(dumps_project(Project("p", tasks=[Task("a")])))
    raw["version"] = 10
    del raw["reference_mode"]
    for task in raw["tasks"]:
        del task["ref_project"], task["ref_snapshot"]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.reference_mode is ReferenceMode.LIVE and loaded.tasks[0].ref_project == ""


def test_unused_fields_of_a_reference_task_are_emptied_on_load() -> None:
    task = reference_task(effort_hours=8.0, status=Status.RUNNING, progress=30, urls=[], category_id=None)
    loaded = parse_project(dumps_project(Project("p", tasks=[task])), "p").tasks[0]
    assert (loaded.effort_hours, loaded.status, loaded.progress, loaded.assignees, loaded.actuals) == (
        0.0, Status.NOT_STARTED, None, [], [],
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw["tasks"][0].update(ref_project=""), "参照先"),
        (lambda raw: raw["tasks"][0].update(ref_project=3), "参照先"),
        (lambda raw: raw["tasks"][0].update(ref_project="p"), "自分自身"),
        (lambda raw: raw.update(reference_mode="auto"), "参照の方式"),
        (lambda raw: raw["tasks"][0].update(ref_snapshot={"progress": "x"}), "スナップショット"),
    ],
)
def test_invalid_references_are_rejected(change, message: str) -> None:
    project = Project("p", reference_mode=ReferenceMode.SNAPSHOT, tasks=[reference_task(ref_snapshot=VALUE)])
    raw = json.loads(dumps_project(project))
    change(raw)
    with pytest.raises(ValueError, match=message):
        parse_project(json.dumps(raw), "p")
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest test/test_reference_storage.py -q`
Expected: FAIL(`ImportError: cannot import name 'OverloadSpan'` など)

- [ ] **Step 3: `models.py` を書く**

`TaskKind` に追加:

```python
    REFERENCE = "プロジェクト参照"  # 他のプロジェクトを参照する行。日程・進捗・遅延・負荷は参照先から出す(自分の工数・担当・実績は持たない)
```

`ReferenceMode`・`OverloadSpan`・`ReferenceValue` を `Task` の前に追加(`from dataclasses import dataclass, field, replace` に `replace` が無ければ足す):

```python
class ReferenceMode(StrEnum):
    LIVE = "live"  # 表示のたびに参照先を読む(保存しない)
    SNAPSHOT = "snapshot"  # 参照行ごとに、参照値を保存して表示する


@dataclass(frozen=True)
class OverloadSpan:
    """参照先の、担当者の割り当て合計が 100% を超える期間。total は期間内の合計の最大(1.0 = 100%)。"""

    member: str
    start: datetime
    end: datetime
    total: float


@dataclass(frozen=True)
class ReferenceValue:
    """参照先のプロジェクト全体の値(細かなタスクは持たない)。スナップショットは、これと取得日時を保存する。"""

    planned_start: datetime | None = None  # 全タスクの実効の開始の最小
    planned_end: datetime | None = None  # 全タスクの完了予定の最大
    actual_start: datetime | None = None  # 実績の区間の開始の最小
    actual_end: datetime | None = None  # 実績の終了の最大。進行中の区間があれば None
    progress: int | None = None  # 工数で重みづけした進捗率(0〜100)。数えるタスクがなければ None
    finished: bool = False  # 数えるタスクがすべて終了
    delayed: int = 0  # 予定超過(終了していない)のタスク数
    peak_load: float = 0.0  # 割り当て合計のピーク(1.0 = 100%)。超過がなければ 0
    peak_member: str = ""
    overloads: tuple[OverloadSpan, ...] = ()
    taken_at: datetime | None = None  # スナップショットを取った日時(保存した値だけ)

    def same_as(self, other: "ReferenceValue") -> bool:
        """取得日時を除いて同じ値か(スナップショットが古いかの判定)。"""
        return replace(self, taken_at=None) == replace(other, taken_at=None)
```

`Task` の末尾(`weekly_crew` の後)に:

```python
    ref_project: str = ""  # 参照先のプロジェクトのファイル名(拡張子なし)。プロジェクト参照だけが持つ
    ref_snapshot: ReferenceValue | None = None  # 参照の方式がスナップショットのときの、保存した参照値
```

`Project` の末尾に:

```python
    reference_mode: ReferenceMode = ReferenceMode.LIVE  # プロジェクト参照の方式
```

`FORMAT_VERSION = 11`(コメントの末尾に `11: プロジェクト参照〔reference_mode・ref_project・ref_snapshot〕` を足す)。

- [ ] **Step 4: `storage.py` を書く**

import に `OverloadSpan`、`ReferenceMode`、`ReferenceValue` を足す。`_checkpoint` の下に:

```python
def _reference_mode(value: Any) -> ReferenceMode:
    if value is None:
        return ReferenceMode.LIVE
    try:
        return ReferenceMode(value)
    except ValueError:
        raise ValueError(f"参照の方式が正しくありません: {value!r}") from None


def _ref_project(value: Any) -> str:
    """参照先のファイル名。空・文字列以外・使えない文字は ValueError。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("参照先のプロジェクトが正しくありません")
    if any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("参照先のプロジェクトに使えない文字が含まれています")
    return value


def _optional_moment(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"スナップショットの{label}が文字列ではありません")
    return _datetime(value)


def _reference_value(raw: Any) -> ReferenceValue | None:
    """保存したスナップショットを読む。null・キーなしは None。形が崩れていれば ValueError。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("スナップショットが正しくありません")
    try:
        progress = raw.get("progress")
        if progress is not None:
            progress = _progress(progress, "スナップショットの進捗率")
        delayed = raw.get("delayed", 0)
        if isinstance(delayed, bool) or not isinstance(delayed, int) or delayed < 0:
            raise ValueError("スナップショットの遅延の件数が正しくありません")
        peak = raw.get("peak_load", 0.0)
        if isinstance(peak, bool) or not isinstance(peak, int | float) or not isfinite(peak) or peak < 0:
            raise ValueError("スナップショットの負荷が正しくありません")
        spans = raw.get("overloads") or []
        if not isinstance(spans, list):
            raise ValueError("スナップショットの負荷の期間が正しくありません")
        overloads = tuple(
            OverloadSpan(
                str(span["member"]),
                _actual_moment(span["start"], "負荷の開始"),
                _actual_moment(span["end"], "負荷の終了"),
                float(span["total"]),
            )
            for span in spans
        )
        return ReferenceValue(
            planned_start=_optional_moment(raw.get("planned_start"), "開始予定"),
            planned_end=_optional_moment(raw.get("planned_end"), "完了予定"),
            actual_start=_optional_moment(raw.get("actual_start"), "実績の開始"),
            actual_end=_optional_moment(raw.get("actual_end"), "実績の終了"),
            progress=progress,
            finished=raw.get("finished") is True,
            delayed=delayed,
            peak_load=float(peak),
            peak_member=str(raw.get("peak_member") or ""),
            overloads=overloads,
            taken_at=_optional_moment(raw.get("taken_at"), "取得日時"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"スナップショットが正しくありません: {exc}") from None


def _reference(task: Task) -> Task:
    """プロジェクト参照を検証し、使わない項目(日程・工数・担当・実績・進捗度・状態・カテゴリ・リンクなど)を空にして返す。"""
    return replace(
        task,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        effort_hours=0.0,
        assignees=[],
        weekly_crew=[],
        actuals=[],
        progress=None,
        parameters=[],
        status=Status.NOT_STARTED,
        priority=Priority.MEDIUM,
        category_id=None,
        urls=[],
    )
```

`_task` の Task 生成に `ref_project=_ref_project(raw.get("ref_project")) if kind is TaskKind.REFERENCE and ctx.version >= 11 else ""`、`ref_snapshot=_reference_value(raw.get("ref_snapshot")) if ctx.version >= 11 else None` を足し、`kind` の分岐を:

```python
    if kind is TaskKind.CHECKPOINT:
        result = _checkpoint(task)
    elif kind is TaskKind.SUMMARY:
        result = _summary(task)
    elif kind is TaskKind.REFERENCE:
        result = _reference(task)
    else:
        result = task
```

(`_kind` が `TaskKind(value)` で読む実装ならそのまま通る。version 11 より前のファイルに参照種別はないので、`ctx.version < 11` で `プロジェクト参照` が出たら、`ref_project` が空になり検証で拒否される。)

`parse_project` の `Project(...)` に `reference_mode=_reference_mode(raw.get("reference_mode")) if ctx.version >= 11 else ReferenceMode.LIVE,` を足し、`validate_links` の前に:

```python
    for task in project.all_tasks():
        if task.kind is TaskKind.REFERENCE:
            if task.ref_project == name:
                raise ValueError(f"参照先が自分自身です: {task.name}")
            if project.reference_mode is ReferenceMode.LIVE:
                task.ref_snapshot = None  # 常に最新のプロジェクトは、スナップショットを持たない
        else:
            task.ref_project, task.ref_snapshot = "", None
```

`from math import isfinite` と `Priority` が storage.py に import 済みか確認し、足りなければ足す。

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest test/test_reference_storage.py -q`
Expected: PASS(8 件)

- [ ] **Step 6: 全体を流して、version の決め打ちを直す**

Run: `uv run pytest -q -x 2>&1 | tail -15`
Expected: `version: 10` を決め打ちしたテストが落ちたら、`11` に直す(過去のコミット `88364ee` と同じ手当て)。`Task`/`Project` を `asdict` で比べるテストが、新しいキー(`ref_project`・`ref_snapshot`・`reference_mode`)で落ちたら、期待値に足す。再実行して全件通す。

- [ ] **Step 7: 型検査とコミット**

Run: `uv run ty check src | tail -2` → `All checks passed!`

```bash
git add -A
git commit -m "feat: プロジェクト参照の種別・参照値・参照の方式を保存・読込する(version 11)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 参照値の算出(`reference.py` の純粋関数)

**Files:**
- Create: `src/projectapp/reference.py`
- Test: `test/test_reference.py`(新規)

**Interfaces:**
- Consumes: Task 1 の `ReferenceValue`・`OverloadSpan`、`timeline.Schedule`・`is_overdue`・`overallocations`、`dashboard._progress_weight`
- Produces: `compute_reference(project: Project, holidays: dict[date, str], now: datetime) -> ReferenceValue`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_reference.py`:

```python
from datetime import datetime

from projectapp.models import Actual, Assignee, Member, Project, Section, Status, Task, TaskKind
from projectapp.reference import compute_reference

NOW = datetime(2026, 10, 8, 10)


def D(month: int, day: int, hour: int = 9) -> datetime:
    return datetime(2026, month, day, hour)


def source() -> Project:
    return Project(
        "基盤",
        daily_hours=8.0,
        members=[Member("田中", 1.0)],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a", planned_start=D(10, 5), effort_hours=8.0, assignees=[Assignee("田中")],
                         status=Status.DONE, actuals=[Actual(D(10, 5), D(10, 5, 17))]),
                    Task("b", id="b", planned_start=D(10, 6), effort_hours=16.0, assignees=[Assignee("田中")],
                         progress=50, actuals=[Actual(D(10, 6), None)]),
                ],
            )
        ],
        tasks=[Task("c", id="c", planned_start=D(10, 20), effort_hours=8.0)],
    )


def test_the_span_progress_and_actuals_cover_the_whole_project() -> None:
    value = compute_reference(source(), {}, NOW)
    assert value.planned_start == D(10, 5)
    assert value.planned_end is not None and value.planned_end > D(10, 20)
    assert value.actual_start == D(10, 5)
    assert value.actual_end is None  # 実行中の区間がある
    assert value.finished is False
    # 工数の重み: a=8h で 100%、b=16h で 50%、c=8h で 0% → (800 + 800 + 0) / 32 = 50
    assert value.progress == 50


def test_delay_counts_unfinished_tasks_past_their_end() -> None:
    value = compute_reference(source(), {}, NOW)
    assert value.delayed == 1  # b は完了予定(10/7)を過ぎて終了していない。a は終了、c は先


def test_overlapping_assignments_become_a_peak_and_spans() -> None:
    project = Project(
        "基盤",
        members=[Member("田中", 1.0)],
        tasks=[
            Task("a", planned_start=D(10, 5), effort_hours=16.0, assignees=[Assignee("田中", 0.8)]),
            Task("b", planned_start=D(10, 5), effort_hours=16.0, assignees=[Assignee("田中", 0.5)]),
        ],
    )
    value = compute_reference(project, {}, NOW)
    assert value.peak_member == "田中" and round(value.peak_load, 2) == 1.3
    assert value.overloads and value.overloads[0].member == "田中"


def test_reference_rows_and_summaries_are_not_counted_and_an_empty_project_has_no_span() -> None:
    project = Project("基盤", tasks=[Task("ref", kind=TaskKind.REFERENCE, ref_project="x")])
    value = compute_reference(project, {}, NOW)
    assert (value.planned_start, value.planned_end, value.progress, value.finished) == (None, None, None, False)
    assert (value.delayed, value.peak_load, value.overloads) == (0, 0.0, ())


def test_a_finished_project_reports_its_last_actual_end() -> None:
    project = Project(
        "基盤",
        tasks=[Task("a", planned_start=D(10, 5), effort_hours=8.0, status=Status.DONE, actuals=[Actual(D(10, 5), D(10, 6))])],
    )
    value = compute_reference(project, {}, NOW)
    assert value.finished is True and value.actual_end == D(10, 6) and value.progress == 100
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_reference.py -q` → FAIL(`ModuleNotFoundError: projectapp.reference`)

- [ ] **Step 3: `reference.py` の算出を書く**

```python
"""プロジェクト参照: 参照先のプロジェクト全体の値の算出と、参照先の読み込み。NiceGUI に依存しない。"""

from datetime import date, datetime

from projectapp.dashboard import _progress_weight
from projectapp.models import OverloadSpan, Project, ReferenceValue, Status, Task, TaskKind
from projectapp.timeline import Schedule, is_overdue, overallocations

COUNTED_KINDS = (TaskKind.NORMAL, TaskKind.CHECKPOINT)  # 数えるのは通常タスクと節目だけ(まとめは二重になり、参照行は循環のもと)


def _counted(project: Project) -> list[Task]:
    return [task for task in project.all_tasks() if task.kind in COUNTED_KINDS]


def compute_reference(project: Project, holidays: dict[date, str], now: datetime) -> ReferenceValue:
    """参照先のプロジェクト全体の予定・実績・進捗・遅延・負荷。数えるタスクがなければ、日程なしの値。"""
    tasks = _counted(project)
    schedule = Schedule(project, holidays)
    starts = [moment for task in tasks if (moment := schedule.start(task)) is not None]
    ends = [moment for task in tasks if (moment := schedule.end(task)) is not None]
    intervals = [a for task in tasks for a in task.actuals]
    finished_ends = [a.end for a in intervals if a.end is not None]
    running = any(a.end is None for a in intervals)
    weights = [w for task in tasks if (w := _progress_weight(task)) is not None]
    total = sum(weight for weight, _ in weights)
    progress = round(sum(weight * percent for weight, percent in weights) / total) if total > 0 else None
    delayed = sum(1 for task in tasks if task.status is not Status.DONE and is_overdue(task, project, holidays, now, schedule))
    overloads = tuple(
        OverloadSpan(o.member, o.start, o.end, o.total) for o in overallocations(project, holidays, tasks)
    )
    peak = max(overloads, key=lambda o: o.total, default=None)
    return ReferenceValue(
        planned_start=min(starts, default=None),
        planned_end=max(ends, default=None),
        actual_start=min((a.start for a in intervals), default=None),
        actual_end=None if running or not finished_ends else max(finished_ends),
        progress=progress,
        finished=bool(tasks) and all(task.status is Status.DONE for task in tasks),
        delayed=delayed,
        peak_load=peak.total if peak else 0.0,
        peak_member=peak.member if peak else "",
        overloads=overloads,
    )
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_reference.py -q` → PASS(5 件)。落ちたら、`_progress_weight`(`dashboard.py`)の戻り値が `(重み, 進み具合 0〜100)` であること、`is_overdue` の引数の順を確かめて合わせる(算出式は変えない)。

- [ ] **Step 5: コミット**

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: 参照先のプロジェクト全体の値を算出する(reference.compute_reference)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 日程計算(`Schedule`)と集計からの除外

**Files:**
- Modify: `src/projectapp/timeline.py`(`Schedule.__init__`・`finish`・`_resolve`・`effective_start`・`effective_end`・`is_overdue`・`progress_state`)
- Modify: `src/projectapp/dashboard.py`(`_tasks`、`nobody`)
- Test: `test/test_timeline.py`、`test/test_reference.py`

**Interfaces:**
- Consumes: Task 1 のモデル
- Produces: `Schedule(project, holidays, references: Mapping[str, ReferenceValue] | None = None)`。参照行の `start`/`end` は `references[task.id]` の `planned_start`/`planned_end`(なければ `(None, None)`)。参照行を先行にしたとき、`Schedule.finish` は、参照先がすべて終了していて実績の終了があればそれ、なければ `planned_end`。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_reference.py` に足す)

```python
from projectapp.models import ReferenceValue
from projectapp.timeline import Schedule, effective_end, effective_start, is_overdue, progress_state


def ref_project(value: ReferenceValue | None, **kwargs: object) -> tuple[Project, Task]:
    ref = Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤", **kwargs)  # type: ignore[arg-type]
    after = Task("後続", id="after", planned_start=D(10, 1), effort_hours=8.0, predecessors=["ref"])
    return Project("p", daily_hours=8.0, tasks=[ref, after]), ref


def test_a_reference_row_takes_its_span_from_the_reference_value() -> None:
    project, ref = ref_project(None)
    value = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17))
    schedule = Schedule(project, {}, {"ref": value})
    assert (schedule.start(ref), schedule.end(ref)) == (D(10, 5), D(10, 20, 17))
    assert effective_start(ref, project, {}, schedule) == D(10, 5)
    assert effective_end(ref, project, {}, schedule) == D(10, 20, 17)
    assert Schedule(project, {}).start(ref) is None  # 参照値がなければ日程なし


def test_a_successor_is_pushed_by_the_reference_end_or_the_actual_end_when_finished() -> None:
    project, _ = ref_project(None)
    after = project.tasks[1]
    open_value = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17), actual_end=D(10, 19, 17))
    assert Schedule(project, {}, {"ref": open_value}).start(after) == D(10, 20, 17)
    done_value = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17), actual_end=D(10, 19, 17), finished=True)
    assert Schedule(project, {}, {"ref": done_value}).start(after) == D(10, 19, 17)


def test_a_reference_row_is_red_only_when_the_reference_end_passes_its_deadline() -> None:
    project, ref = ref_project(None, deadline=D(10, 15, 17))
    late = Schedule(project, {}, {"ref": ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17))})
    assert is_overdue(ref, project, {}, NOW, late)
    ontime = Schedule(project, {}, {"ref": ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 14, 17))})
    assert not is_overdue(ref, project, {}, NOW, ontime)
    assert progress_state(ref, project, {}, NOW, ontime) is None


def test_reference_rows_are_left_out_of_the_dashboard_counts() -> None:
    from projectapp.dashboard import _tasks

    project, _ = ref_project(None)
    assert [t.id for t in _tasks(project)] == ["after"]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_reference.py -q` → FAIL(`Schedule.__init__() takes 3 positional arguments` など)

- [ ] **Step 3: `timeline.py` を変える**

`Schedule.__init__`:

```python
    def __init__(
        self,
        project: Project,
        holidays: dict[date, str],
        references: Mapping[str, ReferenceValue] | None = None,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.references: Mapping[str, ReferenceValue] = references or {}  # プロジェクト参照の行(タスクの id)ごとの参照値
        ...
```

`finish` の先頭(`if pred.kind is TaskKind.SUMMARY:` の前)に:

```python
        if pred.kind is TaskKind.REFERENCE:  # 参照先がすべて終了していれば実績の終了、なければ完了予定
            value = self.references.get(pred.id)
            if value is None:
                return None
            return value.actual_end if value.finished and value.actual_end is not None else value.planned_end
```

`_resolve` の `CHECKPOINT` 分岐の下に:

```python
        if task.kind is TaskKind.REFERENCE:  # 参照先の全体の期間。自分の先行は持たない
            value = self.references.get(task.id)
            result = (value.planned_start, value.planned_end) if value is not None else (None, None)
            self._done[task.id] = result
            return result
```

`effective_start`/`effective_end` の `SUMMARY` 分岐を `task.kind in (TaskKind.SUMMARY, TaskKind.REFERENCE)` に変える(両方とも `(schedule or Schedule(project, holidays)).start/end(task)`)。

`is_overdue` の先頭の `SUMMARY` 判定の下に:

```python
    if task.kind is TaskKind.REFERENCE:  # 参照先の完了予定が、自分の締切を超えるときだけ
        end = (schedule or Schedule(project, holidays)).end(task)
        return task.deadline is not None and end is not None and end > task.deadline
```

`progress_state` の `if task.kind is TaskKind.SUMMARY:` を `in (SUMMARY, REFERENCE)` にする(`status` は未着手固定なので、`DONE` の分岐には入らない)。`from collections.abc import Mapping` と `ReferenceValue` の import を足す。

- [ ] **Step 4: `dashboard.py` を変える**

`_tasks` の条件を `task.kind not in (TaskKind.SUMMARY, TaskKind.REFERENCE)` にし、行 192 付近の `nobody` の内包に `and t.kind is not TaskKind.REFERENCE` を足す。`grep -n "TaskKind" src/projectapp/dashboard.py` で、ほかに `all_tasks()` を直接走査して数えている箇所がないか確かめ、あれば同じ除外を入れる。

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest test/test_reference.py test/test_timeline.py test/test_dashboard.py -q` → PASS

- [ ] **Step 6: コミット**

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: 参照行の日程を Schedule に載せ、集計から外す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 参照先の読み込みとキャッシュ・行ごとの参照

**Files:**
- Modify: `src/projectapp/reference.py`
- Test: `test/test_reference.py`

**Interfaces:**
- Consumes: `storage.file_digest(path)`・`storage.load_project(path)`・`storage.list_project_files`、Task 2 の `compute_reference`
- Produces:
  - `ReferenceResolver(project_dir: Callable[[], Path], holidays: Callable[[], dict[date, str]])` と `live(name: str, now: datetime) -> tuple[ReferenceValue | None, str]`(第 2 要素は、見つからない・読めない理由。正常は空文字)
  - `Reference(value: ReferenceValue | None, problem: str = "", source: ReferenceMode = LIVE, stale: bool = False)`(frozen)
  - `build_references(project, resolver, now) -> dict[str, Reference]`(キーは参照行のタスク id)
  - `take_snapshot(resolver, name, now) -> ReferenceValue | None`(`taken_at=now` を付ける。取れなければ None)
  - `missing_references(project, resolver, now) -> list[str]`(見つからない・読めない参照先のファイル名。重複なし。並びは初出順)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_reference.py` に足す)

```python
from pathlib import Path

from projectapp.models import ReferenceMode
from projectapp.reference import Reference, ReferenceResolver, build_references, missing_references, take_snapshot
from projectapp.storage import save_project


def resolver_for(folder: Path) -> ReferenceResolver:
    return ReferenceResolver(lambda: folder, lambda: {})


def referencing(mode: ReferenceMode = ReferenceMode.LIVE, **kwargs: object) -> Project:
    ref = Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤", **kwargs)  # type: ignore[arg-type]
    return Project("p", reference_mode=mode, tasks=[ref])


def test_a_live_reference_reads_the_file_and_caches_by_content(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    value, problem = resolver.live("基盤", NOW)
    assert problem == "" and value is not None and value.planned_start == D(10, 5)
    again, _ = resolver.live("基盤", NOW)
    assert again is value  # 内容が同じ間は、同じ値を返す
    changed = source()
    changed.tasks.append(Task("d", id="d", planned_start=D(12, 1), effort_hours=8.0))
    save_project(changed, tmp_path)
    after, _ = resolver.live("基盤", NOW)
    assert after is not value and after is not None and after.planned_end != value.planned_end


def test_a_missing_or_broken_file_gives_a_reason_not_an_error(tmp_path: Path) -> None:
    resolver = resolver_for(tmp_path)
    assert resolver.live("基盤", NOW) == (None, "「基盤.json」が格納先にありません")
    (tmp_path / "基盤.json").write_text("{ not json", encoding="utf-8")
    value, problem = resolver.live("基盤", NOW)
    assert value is None and problem.startswith("「基盤.json」を読めません")


def test_build_references_in_live_mode_uses_the_file(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    refs = build_references(referencing(), resolver_for(tmp_path), NOW)
    assert refs["ref"].value is not None and refs["ref"].stale is False and refs["ref"].source is ReferenceMode.LIVE


def test_build_references_in_snapshot_mode_uses_the_saved_value_and_flags_stale(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    taken = take_snapshot(resolver, "基盤", NOW)
    assert taken is not None and taken.taken_at == NOW
    project = referencing(ReferenceMode.SNAPSHOT, ref_snapshot=taken)
    fresh = build_references(project, resolver, NOW)["ref"]
    assert fresh.value == taken and fresh.stale is False
    project.tasks[0].ref_snapshot = ReferenceValue(planned_start=D(1, 1), planned_end=D(1, 2))
    old = build_references(project, resolver, NOW)["ref"]
    assert old.stale is True and old.value == project.tasks[0].ref_snapshot  # 保存した値のまま出す
    empty = referencing(ReferenceMode.SNAPSHOT)
    assert build_references(empty, resolver, NOW)["ref"].value is None  # スナップショットがなければ帯なし


def test_snapshot_mode_keeps_the_saved_value_when_the_file_is_missing(tmp_path: Path) -> None:
    saved = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20), taken_at=NOW)
    project = referencing(ReferenceMode.SNAPSHOT, ref_snapshot=saved)
    ref = build_references(project, resolver_for(tmp_path), NOW)["ref"]
    assert ref.value == saved and "格納先にありません" in ref.problem and ref.stale is False


def test_missing_references_lists_each_file_once(tmp_path: Path) -> None:
    project = Project("p", tasks=[
        Task("a", id="a", kind=TaskKind.REFERENCE, ref_project="ない"),
        Task("b", id="b", kind=TaskKind.REFERENCE, ref_project="ない"),
        Task("c", id="c", kind=TaskKind.REFERENCE, ref_project="基盤"),
    ])
    save_project(source(), tmp_path)
    assert missing_references(project, resolver_for(tmp_path), NOW) == ["ない"]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_reference.py -q` → FAIL(`ImportError: cannot import name 'ReferenceResolver'`)

- [ ] **Step 3: `reference.py` に追記する**

```python
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from projectapp.models import ReferenceMode
from projectapp.storage import file_digest, load_project


@dataclass(frozen=True)
class Reference:
    """参照行 1 つぶんの、表示に使う参照。value が None なら、帯・チップ・縞は出さない。"""

    value: ReferenceValue | None
    problem: str = ""  # 見つからない・読めない理由(正常は空)
    source: ReferenceMode = ReferenceMode.LIVE
    stale: bool = False  # スナップショットが、今の参照先の値と違う


class ReferenceResolver:
    """参照先のファイルを読んで、参照値にする。内容のハッシュと日付が同じ間は、同じ値を返す。"""

    def __init__(self, project_dir: Callable[[], Path], holidays: Callable[[], dict[date, str]]) -> None:
        self.project_dir = project_dir
        self.holidays = holidays
        self._cache: dict[str, tuple[tuple[str, date], ReferenceValue | None, str]] = {}

    def live(self, name: str, now: datetime) -> tuple[ReferenceValue | None, str]:
        path = self.project_dir() / f"{name}.json"
        digest = file_digest(path)
        if digest is None:
            return None, f"「{name}.json」が格納先にありません"
        key = (digest, now.date())  # 超過の判定が日付で変わるので、日付も鍵にする
        cached = self._cache.get(name)
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        try:
            value, problem = compute_reference(load_project(path), self.holidays(), now), ""
        except Exception as exc:  # noqa: BLE001 他人のファイルの形の崩れで、画面を止めない
            value, problem = None, f"「{name}.json」を読めません({exc or type(exc).__name__})"
        self._cache[name] = (key, value, problem)
        return value, problem


def build_references(project: Project, resolver: ReferenceResolver, now: datetime) -> dict[str, Reference]:
    """参照行(タスクの id)ごとの参照。常に最新は参照先を読み、スナップショットは保存した値で出す(古さも調べる)。"""
    result: dict[str, Reference] = {}
    for task in project.all_tasks():
        if task.kind is not TaskKind.REFERENCE:
            continue
        live, problem = resolver.live(task.ref_project, now)
        if project.reference_mode is ReferenceMode.SNAPSHOT:
            saved = task.ref_snapshot
            stale = live is not None and (saved is None or not saved.same_as(live))
            result[task.id] = Reference(saved, problem, ReferenceMode.SNAPSHOT, stale)
        else:
            result[task.id] = Reference(live, problem, ReferenceMode.LIVE)
    return result


def take_snapshot(resolver: ReferenceResolver, name: str, now: datetime) -> ReferenceValue | None:
    """今の参照先の値に取得日時を付けたスナップショット。取れなければ None。"""
    value, _ = resolver.live(name, now)
    return replace(value, taken_at=now) if value is not None else None


def missing_references(project: Project, resolver: ReferenceResolver, now: datetime) -> list[str]:
    """見つからない・読めない参照先のファイル名(重複なし・初出の順)。"""
    names = dict.fromkeys(t.ref_project for t in project.all_tasks() if t.kind is TaskKind.REFERENCE)
    return [name for name in names if resolver.live(name, now)[0] is None]
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_reference.py -q` → PASS。`reference.py` の先頭 import は、重複しないよう 1 か所にまとめる。

- [ ] **Step 5: コミット**

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: 参照先の読み込みとキャッシュ、行ごとの参照を組み立てる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 追加・編集ダイアログ(`build_task` と種別トグル)

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task`、新しい `_build_reference`)
- Modify: `src/projectapp/task_dialog.py`(`open_task_dialog` の引数・種別トグル・参照先の選択欄・表示の出し入れ)
- Modify: `src/projectapp/views.py`(`open_task_dialog` を呼ぶ箇所に参照先の候補を渡す)
- Test: `test/test_forms.py` 相当(`build_task` を試している既存ファイルに足す。`grep -ln "build_task" test/*.py`)、`test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 のモデル
- Produces: `build_task(..., ref_project: str = "")`(`kind is TaskKind.REFERENCE` のとき、`ref_project` が空なら `ValueError("参照先のプロジェクトを選んでください")`)。`open_task_dialog(..., reference_choices: list[str] | None = None)`(参照先の候補。`None` は`プロジェクト参照`を種別の選択肢に出さない)

- [ ] **Step 1: `build_task` の失敗するテストを書く**

```python
def test_build_task_makes_a_reference_row_with_only_the_shared_fields() -> None:
    task = built(kind=TaskKind.REFERENCE, ref_project="基盤", deadline="2026-12-01 17:00", color="#112233", name="基盤開発")
    assert (task.kind, task.ref_project, task.deadline) == (TaskKind.REFERENCE, "基盤", datetime(2026, 12, 1, 17))
    assert (task.effort_hours, task.assignees, task.actuals, task.status) == (0.0, [], [], Status.NOT_STARTED)


def test_build_task_needs_a_reference_target() -> None:
    with pytest.raises(ValueError, match="参照先のプロジェクトを選んでください"):
        built(kind=TaskKind.REFERENCE, ref_project="")
```

(`built` は `test_summary.py` の補助関数と同じ形。`build_task` を試す既存ファイルの補助関数を使う。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest <そのファイル> -q -k reference` → FAIL(`unexpected keyword argument 'ref_project'`)

- [ ] **Step 3: `forms.py`**

`build_task` の引数に `ref_project: str = "",` を足し、`CHECKPOINT` の分岐の下に:

```python
    if kind is TaskKind.REFERENCE:
        return _build_reference(base, clean, ref_project, deadline, color, predecessors, linkable_ids)
```

`_build_checkpoint` の下に:

```python
def _build_reference(
    base: Task,
    name: str,
    ref_project: str,
    deadline: str,
    color: str,
    predecessors: list[str] | None,
    linkable_ids: frozenset[str] | None,
) -> Task:
    """プロジェクト参照。参照先・締切(任意)・色・先行だけを検証し、使わない項目は空にする(隠した欄の入力は見ない)。"""
    if not ref_project.strip():
        raise ValueError("参照先のプロジェクトを選んでください")
    try:
        deadline_at = parse_datetime(deadline)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    if deadline_at is not None and not MIN_YEAR <= deadline_at.year <= MAX_YEAR:
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if not is_hex_color(color):
        raise ValueError("色は#RRGGBBの形式で入力してください")
    return replace(
        base,
        kind=TaskKind.REFERENCE,
        name=name,
        ref_project=ref_project,
        planned_start=None,
        planned_end=None,
        planned_end_manual=False,
        deadline=deadline_at,
        effort_hours=0.0,
        priority=Priority.MEDIUM,
        status=Status.NOT_STARTED,
        color=color,
        assignees=[],
        weekly_crew=[],
        actuals=[],
        progress=None,
        parameters=[],
        category_id=None,
        urls=[],
        predecessors=_links(base, predecessors, linkable_ids),
    )
```

(`_build_checkpoint` が `predecessors` を `_links(...)` で作っているなら同じ呼び方にそろえる。`ref_snapshot` は `base` から引き継ぐ。参照先を変えたときは、スナップショットを捨てる: `ref_snapshot=base.ref_snapshot if base.ref_project == ref_project else None` を `replace(...)` に足す。)

- [ ] **Step 4: ダイアログのテストを書く**(`test/test_task_dialog.py`)

既存の `open_task_dialog` を開くテストの形(`ui.button("open", on_click=...)` で開く)に合わせる:

```python
async def test_the_dialog_saves_a_project_reference(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def page() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append, reference_choices=["基盤", "共通"])).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="task-kind")
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.REFERENCE)
    await user.should_see(marker="task-ref-project")
    user.find(marker="task-name").type("基盤開発")
    user.find(marker="task-ref-project").elements.pop().set_value("基盤")
    user.find(marker="task-save").click()  # 保存ボタンの marker は、既存テストと同じものを使う
    assert [(t.kind, t.ref_project, t.name) for t in saved] == [(TaskKind.REFERENCE, "基盤", "基盤開発")]


async def test_the_reference_kind_is_offered_only_with_choices_and_hides_the_normal_fields(user: User) -> None:
    @ui.page("/")
    def page() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, lambda t: None)).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    toggle = user.find(marker="task-kind").elements.pop()
    assert TaskKind.REFERENCE not in toggle.options  # 候補がなければ選択肢に出さない
```

Run: 失敗を確認する(`unexpected keyword argument 'reference_choices'`)。保存ボタンの marker は `grep -n "mark(\"task-save\|ui.button(\"保存" src/projectapp/task_dialog.py` で確かめて合わせる。

- [ ] **Step 5: `task_dialog.py`**

引数に `reference_choices: list[str] | None = None,` を足す。種別トグルの選択肢を:

```python
        offered = [k for k in TaskKind if k is not TaskKind.SUMMARY and (k is not TaskKind.REFERENCE or reference_choices is not None or initial.kind is TaskKind.REFERENCE)]
        kind = ui.toggle({k: k.value for k in offered}, value=TaskKind.NORMAL if is_summary else initial.kind).mark("task-kind")
```

`color` 欄の前に、参照先の選択欄を足す(候補に今の `ref_project` が含まれなければ足して、見つからない参照先も保存で失わない):

```python
        choices = list(dict.fromkeys([*(reference_choices or []), *([initial.ref_project] if initial.ref_project else [])]))
        ref_project = ui.select(choices, value=initial.ref_project or None, label="参照先のプロジェクト").classes("w-full").mark("task-ref-project")
```

`apply_kind` の `kind_hint.set_visibility(...)` の条件を、`kind.value in (TaskKind.CHECKPOINT, TaskKind.REFERENCE) and initial.kind is TaskKind.NORMAL and has_normal_data` にする。`refresh_visibility` で、`normal = kind.value not in (TaskKind.CHECKPOINT, TaskKind.REFERENCE)` とし、参照のときだけ出す・隠すものを足す:

```python
            reference = kind.value == TaskKind.REFERENCE
            ref_project.set_visibility(reference)
            for widget in (status, category, priority_box, url_box):
                if reference:
                    widget.set_visibility(False)
```

(`full` のときの `for widget in (category, predecessors, priority_box, url_box, color): widget.set_visibility(full)` は、参照行で `category`・`priority_box`・`url_box` を隠したままにするため、その後ろに `if reference: ...set_visibility(False)` を置く。`status` は既存の `refresh_visibility` で明示的に出し入れしていないなら、`apply_kind` の中で `status.set_visibility(not reference)` にする。)

`current()` に `ref_project.value or ""` を足し、`save()` の `build_task(...)` に `ref_project=ref_project.value or "",` を渡す。

- [ ] **Step 6: `views.py` で候補を渡す**

`open_task_dialog(...)` を呼んでいる箇所(`grep -n "open_task_dialog(" src/projectapp/views.py`)に、`reference_choices=sorted(name for name in self.files if name != self.current_name()),` を足す(`self.files` は格納先のプロジェクト名→パス。呼ぶ直前に `self.files` を読み直す処理が既にあれば、それを使う)。

- [ ] **Step 7: 通ることを確認してコミット**

Run: `uv run pytest test/test_task_dialog.py -q` と `build_task` のテストファイル → PASS。種別の選択肢を数えている既存テストが落ちたら、`reference_choices=None` のときは今までと同じ選択肢なので、期待値は変わらないはず(変わったら実装の条件を見直す)。

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: 追加・編集ダイアログで、種別プロジェクト参照と参照先を選べるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ガントチャートの参照行(描画・クリック・右クリックの`更新`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions`、`GanttChart.__init__`・`render`・`row`・`task_chips`・`build_menu`・`open_menu`、新しい `reference_band`・`reference_chips`、CSS)
- Test: `test/test_gantt.py`(`Recorder` に新しい操作を足し、参照行のテストを足す)

**Interfaces:**
- Consumes: Task 3 の `Schedule(references=)`、Task 4 の `Reference`
- Produces:
  - `GanttActions.open_reference: Callable[[str], object]`(参照行のタスク id)、`GanttActions.refresh_reference: Callable[[SectionPath, int], object]`
  - `GanttChart(..., references: Callable[[], dict[str, Reference]] = lambda: {})`
  - マーカー: 帯 `bar-{key}-{ti}`(既存と同じ)、チップ `ref-delay-{key}-{ti}`・`ref-load-{key}-{ti}`、見つからない `ref-missing-{key}-{ti}`、名前 `task-name-{key}-{ti}`(既存)、縞 `overload-{key}-{ti}-{n}`(既存と同じ形)、右クリックの`更新` `context-refresh`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の `Recorder` に `open_reference`・`refresh_reference` の記録を足し(`edit_week_crew` と同じ形)、参照行の補助とテストを足す:

```python
def reference_chart(
    value: ReferenceValue | None, problem: str = "", *, mode: ReferenceMode = ReferenceMode.LIVE, stale: bool = False
) -> tuple[Project, Recorder]:
    ref = Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤")
    project = Project("p", base_date=date(2026, 10, 1), reference_mode=mode, tasks=[ref])
    refs = {"ref": Reference(value, problem, mode, stale)}
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        GanttChart(project, {}, recorder.actions, now=lambda: datetime(2026, 10, 8), references=lambda: refs).build()

    return project, recorder


SPAN = ReferenceValue(
    planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 16, 17), progress=45, delayed=3,
    peak_load=1.3, peak_member="田中",
    overloads=(OverloadSpan("田中", datetime(2026, 10, 8, 9), datetime(2026, 10, 9, 17), 1.3),),
)


async def test_a_reference_row_draws_one_band_with_delay_and_load_chips(user: User) -> None:
    reference_chart(SPAN)
    await user.open("/")
    await user.should_see(marker="bar-top-0")
    assert "遅延 3件" in user.find(marker="ref-delay-top-0").elements.pop().text
    assert "負荷 130%" in user.find(marker="ref-load-top-0").elements.pop().text
    await user.should_see(marker="overload-top-0-0")  # 超過の期間に縞


async def test_the_reference_hover_says_it_opens_on_click_and_the_band_underlines(user: User) -> None:
    reference_chart(SPAN)
    await user.open("/")
    bar = user.find(marker="bar-top-0").elements.pop()
    text = tooltips_targeting(bar)[0]
    assert "基盤開発 10/5〜10/16" in text and "遅延 3 件" in text and "ピーク負荷 130%(田中)" in text
    assert text.endswith("クリックすると開く")
    assert "ref-link" in bar.classes


async def test_clicking_the_band_or_the_name_opens_the_reference(user: User) -> None:
    _, recorder = reference_chart(SPAN)
    await user.open("/")
    user.find(marker="bar-top-0").click()
    user.find(marker="task-name-top-0").click()
    assert recorder.opened_references == ["ref", "ref"]


async def test_a_missing_reference_keeps_the_row_without_a_band(user: User) -> None:
    reference_chart(None, "「基盤.json」が格納先にありません")
    await user.open("/")
    await user.should_not_see(marker="bar-top-0")
    await user.should_see(marker="ref-missing-top-0")
    assert "参照先が見つかりません" in user.find(marker="ref-missing-top-0").elements.pop().text


async def test_a_snapshot_row_shows_the_saved_value_with_its_date_and_no_chips_when_not_shown(user: User) -> None:
    saved = replace(SPAN, taken_at=datetime(2026, 10, 7, 10))
    reference_chart(saved, mode=ReferenceMode.SNAPSHOT)
    await user.open("/")
    text = tooltips_targeting(user.find(marker="bar-top-0").elements.pop())[0]
    assert "スナップショット 10/7" in text


async def test_the_refresh_menu_item_is_only_enabled_for_snapshot_references(user: User) -> None:
    chart_project, recorder = reference_chart(SPAN, mode=ReferenceMode.SNAPSHOT)
    await user.open("/")
    user.find(marker="row-top-0").trigger("contextmenu")
    item = user.find(marker="context-refresh").elements.pop()
    assert "disable" not in item.props
    user.find(marker="context-refresh").click()
    assert recorder.refreshed == [((), 0)]
```

```python
async def test_decompose_and_weeks_are_disabled_on_a_reference_row(user: User) -> None:
    reference_chart(SPAN)
    await user.open("/")
    user.find(marker="row-top-0").trigger("contextmenu")
    assert "disable" in user.find(marker="context-decompose").elements.pop().props
    assert "disable" in user.find(marker="context-weeks").elements.pop().props
```

(`tooltips_targeting`・`Recorder` の形は既存の同名の補助関数に合わせる。`row-top-0` の右クリックは、既存の右クリックのテスト(`test/test_context_menu.py`)の開き方を真似る。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "reference or refresh"` → FAIL(`unexpected keyword argument 'references'`)

- [ ] **Step 3: `gantt.py` の入口を変える**

`GanttActions` に追加:

```python
    open_reference: Callable[[str], object] = lambda task_id: None  # プロジェクト参照の行のクリック(タスクの id)
    refresh_reference: Callable[[SectionPath, int], object] = lambda path, ti: None  # スナップショットの更新
```

`GanttChart.__init__` の引数に `references: Callable[[], dict[str, Reference]] = lambda: {},` を足し、`self.references_of = references`、`self.refs: dict[str, Reference] = {}` を持つ。`render` の `self.schedule = Schedule(self.project, self.holidays)` を:

```python
        self.refs = self.references_of()
        self.schedule = Schedule(
            self.project, self.holidays, {tid: ref.value for tid, ref in self.refs.items() if ref.value is not None}
        )
```

(`__init__` 側の初期 `Schedule(project, holidays)` はそのままでよい。`from projectapp.reference import Reference` を足す。)

- [ ] **Step 4: 行の描画**

`row()` の `if task.kind is TaskKind.CHECKPOINT:` の分岐の下に:

```python
            if task.kind is TaskKind.REFERENCE:  # 参照先全体の帯だけ。自分の棒・実績・締切の矢印は出さない(締切は目印だけ)
                self.reference_band(path, key, ti, task, columns, width)
                self.deadline_marker(path, ti, task, columns, width)
                return row
```

名前の label を作った直後(`if finished:` の前)に、参照行の名前のクリックを足す:

```python
                if task.kind is TaskKind.REFERENCE and not self.options.read_only:
                    name.classes("ref-link").props("data-no-quick-add")
                    name.on("click", lambda tid=task.id: self.actions.open_reference(tid), js_handler="(e) => { e.stopPropagation(); emit(); }")
```

`task_chips` の先頭(`category = ...` の前)に:

```python
        if task.kind is TaskKind.REFERENCE:
            self.reference_chips(key, ti, task)
            return
```

新しいメソッドを `checkpoint_marker` の前に足す:

```python
    def reference_chips(self, key: int | str, ti: int, task: Task) -> None:
        """参照行の、名前の右のチップ: 遅延の件数・負荷のピーク・進捗・見つからない理由。名前の欄の枠の中で呼ぶ。"""
        ref = self.refs.get(task.id)
        if ref is None:
            return
        if ref.problem and ref.value is None:
            ui.label("(参照先が見つかりません)").classes("text-caption text-grey").tooltip(ref.problem).mark(f"ref-missing-{key}-{ti}")
            return
        value = ref.value
        if value is None:
            return
        if self.options.show_alerts and value.delayed:
            ui.label(f"遅延 {value.delayed}件").style(ASSIGNEE_CHIP_STYLE + f" background: {OVERDUE_COLOR};").mark(f"ref-delay-{key}-{ti}")
        if self.options.show_alerts and value.peak_load > 1.0:
            ui.label(f"負荷 {round(value.peak_load * 100)}%").style(ASSIGNEE_CHIP_STYLE).mark(f"ref-load-{key}-{ti}")
        if value.progress is not None:
            ui.label(f"{value.progress}%").style(PROGRESS_TEXT_STYLE).mark(f"task-progress-{key}-{ti}")

    def reference_text(self, task: Task, ref: Reference) -> str:
        """参照行の帯のマウスオーバー(細かなタスクは出さない)。"""
        value = ref.value
        assert value is not None
        lines = [task.name]
        if value.planned_start is not None and value.planned_end is not None:
            lines[0] += f" {short_date(value.planned_start.date())}〜{short_date(value.planned_end.date())}"
        if value.actual_start is not None:
            tail = short_date(value.actual_end.date()) if value.actual_end is not None else ""
            lines.append(f"実績 {short_date(value.actual_start.date())}〜{tail}")
        lines.append(f"遅延 {value.delayed} 件")
        lines.append(f"ピーク負荷 {round(value.peak_load * 100)}%({value.peak_member})" if value.peak_load > 1.0 else "負荷の超過なし")
        if ref.source is ReferenceMode.SNAPSHOT and value.taken_at is not None:
            lines.append(f"スナップショット {short_date(value.taken_at.date())}" + (" (古い)" if ref.stale else ""))
        if ref.problem:
            lines.append(ref.problem)
        if not self.options.read_only:
            lines.append("クリックすると開く")
        return "\n".join(lines)

    def reference_band(
        self, path: SectionPath, key: int | str, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        """参照先全体の予定の帯(進捗の塗りと、超過期間の縞)。参照値がなければ出さない。"""
        ref = self.refs.get(task.id)
        start, end = self.schedule.start(task), self.schedule.end(task)
        span = bar_span(start, end, columns)
        if ref is None or ref.value is None or span is None or not self.bar_visible(start, end, columns):
            return
        left, length = span
        bar_width = max(length * width, MIN_BAR_PX)
        late = self.options.show_alerts and ref.value.delayed > 0
        bar = ui.element("div").style(
            f"position: absolute; left: {from_name(left * width)}; width: {bar_width:.1f}px; top: {BAR_TOP_PX}px;"
            f" height: {BAR_HEIGHT_PX}px; background: {planned_background(task.color if not late else OVERDUE_COLOR)};"
            f" border-radius: 4px; overflow: hidden; user-select: none"
        )
        bar.mark(f"bar-{key}-{ti}")
        if not self.options.read_only:
            bar.classes("ref-link").on("click", lambda tid=task.id: self.actions.open_reference(tid), js_handler="(e) => { e.stopPropagation(); emit(); }")
        bar.tooltip(self.reference_text(task, ref))
        with bar:
            if ref.value.progress:
                ui.element("div").style(
                    f"position: absolute; left: 0; top: 0; bottom: 0; width: {ref.value.progress}%;"
                    f" background: {task.color}; opacity: 0.6; pointer-events: none"
                )
            if self.options.show_alerts:
                for n, over in enumerate(ref.value.overloads):
                    origin, length_cols = interval_span(over.start, over.end, columns)
                    left_px = max((origin - left) * width, 0.0)
                    width_px = min(length_cols * width, bar_width - left_px)
                    if width_px > 0:
                        ui.element("div").style(
                            f"position: absolute; left: {left_px:.1f}px; width: {width_px:.1f}px; top: 0; bottom: 0;"
                            f" background: {OVERLOAD_STRIPES}; pointer-events: none"
                        ).mark(f"overload-{key}-{ti}-{n}")
```

CSS を `ui.add_css(EVENT_CSS)` の並びに追加(`REFERENCE_CSS = ".ref-link { cursor: pointer; } .ref-link:hover { text-decoration: underline; }"`)。`short_date`・`ReferenceMode`・`OVERDUE_COLOR` など、gantt.py 内の既存の import・定義を使う(足りなければ足す)。

- [ ] **Step 5: 右クリックのメニュー**

`build_menu` の `名前の変更` の上に:

```python
            self.refresh_item = ui.menu_item("更新", on_click=act(lambda p, t: self.actions.refresh_reference(p, t))).mark("context-refresh")
```

`__init__` に `self.refresh_item: ui.menu_item | None = None` を持ち、`open_menu`(`blocked = ...` の下)で:

```python
        if self.refresh_item is not None:
            task = tasks[ti] if ti < len(tasks) else None
            is_reference = task is not None and task.kind is TaskKind.REFERENCE
            can = is_reference and self.project.reference_mode is ReferenceMode.SNAPSHOT
            self.refresh_item.set_visibility(is_reference)
            self.refresh_item.props(add="" if can else "disable", remove="disable" if can else "")
            if is_reference and not can:
                self.refresh_item.tooltip("参照の方式が「スナップショット」のときだけ更新できます")
```

- [ ] **Step 6: 通ることを確認してコミット**

Run: `uv run pytest test/test_gantt.py test/test_context_menu.py -q` → PASS。既存の「右クリックのメニューの項目数・並び」を数えるテストが落ちたら、`更新` が参照行以外では出ない(`set_visibility(False)`)ことを確かめ、並びの期待値を直す。

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: ガントチャートにプロジェクト参照の行(帯・チップ・縞・クリック・更新)を出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 画面の結線(設定・クリックの確認・更新・見つからない通知)

**Files:**
- Modify: `src/projectapp/forms.py`(`open_settings_dialog` に `参照の方式`、新しい `open_stale_reference_dialog`)
- Modify: `src/projectapp/views.py`(`MainView.__init__`・`show_project`・`open_settings`・新しいメソッド)
- Test: `test/test_views.py`、`test/test_settings*.py`(設定ダイアログを試している既存ファイル。`grep -ln "open_settings_dialog" test/*.py`)

**Interfaces:**
- Consumes: Task 4 の `ReferenceResolver`・`build_references`・`take_snapshot`・`missing_references`、Task 6 の `GanttActions`
- Produces:
  - `open_settings_dialog(..., reference_mode: ReferenceMode = ReferenceMode.LIVE, on_reference_mode: Callable[[ReferenceMode], object] | None = None)`(トグルの marker `settings-reference-mode`。`適用` で、変わったときだけ `on_reference_mode`)
  - `open_stale_reference_dialog(name: str, on_update: Callable[[], object], on_skip: Callable[[], object]) -> None`(ボタン marker: `stale-cancel`・`stale-skip`・`stale-update`)
  - `MainView.apply_reference_mode(mode)`・`MainView.open_reference(task_id)`・`MainView.refresh_reference(path, index)`

- [ ] **Step 1: 設定ダイアログのテストを書く**

```python
async def test_the_settings_dialog_reports_a_changed_reference_mode(user: User) -> None:
    applied: list[ReferenceMode] = []

    @ui.page("/")
    def page() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(
            6.5, time(9), lambda *a: None, reference_mode=ReferenceMode.LIVE, on_reference_mode=applied.append
        )).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    user.find(marker="settings-reference-mode").elements.pop().set_value(ReferenceMode.SNAPSHOT.value)
    user.find(marker="settings-apply").click()  # 適用ボタンの marker は、既存の設定ダイアログのテストと同じものを使う
    assert applied == [ReferenceMode.SNAPSHOT]
```

Run: FAIL を確認(`unexpected keyword argument 'reference_mode'`)。適用ボタンの marker は `grep -n "mark(\"settings-" src/projectapp/forms.py` で確かめる。

- [ ] **Step 2: `forms.py` の設定ダイアログ**

引数に `reference_mode: ReferenceMode = ReferenceMode.LIVE`、`on_reference_mode: Callable[[ReferenceMode], object] | None = None` を足す。`実績の記録方式` のトグルの後に:

```python
        reference = None
        if on_reference_mode is not None:
            ui.label("プロジェクト参照の方式").classes("text-caption text-grey")
            reference = ui.toggle(
                {ReferenceMode.LIVE.value: "常に最新", ReferenceMode.SNAPSHOT.value: "スナップショット"},
                value=reference_mode.value,
            ).mark("settings-reference-mode")
            ui.label("スナップショットは、参照行の値を保存します(右クリックの「更新」で取り直す)").classes("text-caption text-grey")
```

適用処理の `on_base_date(base)` の呼び出し(`forms.py:1376` 付近)の次に:

```python
            if reference is not None and on_reference_mode is not None and ReferenceMode(reference.value) is not reference_mode:
                on_reference_mode(ReferenceMode(reference.value))
```

確認ダイアログを `open_unsaved_dialog` の下に足す:

```python
def open_stale_reference_dialog(name: str, on_update: Callable[[], object], on_skip: Callable[[], object]) -> None:
    """スナップショットが古いときの、参照先を開く前の確認(更新して開く / 更新せず開く / キャンセル)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("スナップショットが古くなっています").classes("text-h6")
        ui.label(f"「{name}」の参照値は、保存したあとに変わっています。更新してから開きますか。")

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("stale-cancel")
            ui.button("更新せず開く", on_click=lambda: run(on_skip)).props("flat").mark("stale-skip")
            ui.button("更新して開く", on_click=lambda: run(on_update)).mark("stale-update")
    dialog.open()
```

Run: 設定ダイアログのテスト → PASS。

- [ ] **Step 3: views のテストを書く**

`test_views.py` の `mount_capturing(base_dir, views)` を使う(`views[0]` が `MainView`)。格納先に参照先ファイルを保存して、確認の流れを見る:

```python
def reference_setup(tmp_path: Path, mode: ReferenceMode = ReferenceMode.LIVE) -> Project:
    save_project(Project("基盤", tasks=[Task("x", planned_start=datetime(2026, 10, 5, 9), effort_hours=8.0)]), tmp_path)
    ref = Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤")
    return Project("本体", reference_mode=mode, tasks=[ref])


async def test_clicking_a_live_reference_opens_the_project(user: User, tmp_path: Path) -> None:
    save_project(reference_setup(tmp_path), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.request_open("本体")
    view.open_reference("ref")
    assert view.current_name() == "基盤"


async def test_a_stale_snapshot_asks_before_opening_and_update_makes_it_unsaved_then_asks_to_save(user: User, tmp_path: Path) -> None:
    project = reference_setup(tmp_path, ReferenceMode.SNAPSHOT)
    project.tasks[0].ref_snapshot = ReferenceValue(planned_start=datetime(2026, 1, 1), planned_end=datetime(2026, 1, 2))
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.request_open("本体")
    view.open_reference("ref")
    await user.should_see(marker="stale-update")
    user.find(marker="stale-update").click()
    await user.should_see(marker="unsaved-save")  # 更新で未保存になったので、続けて保存の確認
    user.find(marker="unsaved-save").click()
    assert view.current_name() == "基盤"
    assert load_project(tmp_path / "本体.json").tasks[0].ref_snapshot is not None  # 更新した値が保存された


async def test_skipping_the_stale_dialog_opens_without_changing_the_snapshot(user: User, tmp_path: Path) -> None:
    project = reference_setup(tmp_path, ReferenceMode.SNAPSHOT)
    project.tasks[0].ref_snapshot = ReferenceValue(planned_start=datetime(2026, 1, 1), planned_end=datetime(2026, 1, 2))
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.request_open("本体")
    view.open_reference("ref")
    user.find(marker="stale-skip").click()
    assert view.current_name() == "基盤"


async def test_a_missing_target_notifies_once_when_the_project_is_opened(user: User, tmp_path: Path) -> None:
    ref = Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="ない")
    save_project(Project("本体", tasks=[ref]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    views[0].request_open("本体")
    assert user.notify.contains("参照先のプロジェクトが見つかりません: ない")


async def test_refreshing_a_snapshot_takes_the_current_value_and_marks_the_project_dirty(user: User, tmp_path: Path) -> None:
    project = reference_setup(tmp_path, ReferenceMode.SNAPSHOT)
    save_project(project, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.request_open("本体")
    view.refresh_reference((), 0)
    assert view.project.tasks[0].ref_snapshot is not None and view.is_dirty()


async def test_switching_the_mode_takes_or_drops_the_snapshots(user: User, tmp_path: Path) -> None:
    save_project(reference_setup(tmp_path), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.request_open("本体")
    view.apply_reference_mode(ReferenceMode.SNAPSHOT)
    assert view.project.tasks[0].ref_snapshot is not None
    view.apply_reference_mode(ReferenceMode.LIVE)
    assert view.project.tasks[0].ref_snapshot is None
```

(`mount_capturing` が `MainView` を作る形は既存のテストを見て合わせる。`view.request_open` は `self.files` を引くので、`mount_capturing` が格納先を走査していること、またはテストの冒頭で `view.files` を更新していることを確かめる。)

Run: FAIL を確認(`AttributeError: ... 'open_reference'`)。

- [ ] **Step 4: `views.py`**

`MainView.__init__` で、`self.project_dir` と `self.holidays` が決まったあと、`GanttChart(...)` を作る前に:

```python
        self.reference_resolver = ReferenceResolver(lambda: self.project_dir, lambda: self.holidays)
```

`GanttChart(...)` の引数に `references=lambda: build_references(self.project, self.reference_resolver, datetime.now()),` を足し、`GanttActions(...)` に `open_reference=self.open_reference, refresh_reference=self.refresh_reference,` を足す。

メソッドを足す(`apply_settings` の近く):

```python
    def apply_reference_mode(self, mode: ReferenceMode) -> None:
        """参照の方式を変える。スナップショットへは、全参照行のスナップショットをそのとき取り、常に最新へは捨てる。保存はしない。"""
        if mode is self.project.reference_mode:
            return
        now = datetime.now()
        self.project.reference_mode = mode
        for task in self.project.all_tasks():
            if task.kind is not TaskKind.REFERENCE:
                continue
            task.ref_snapshot = take_snapshot(self.reference_resolver, task.ref_project, now) if mode is ReferenceMode.SNAPSHOT else None
        self.after_edit()

    def refresh_reference(self, path: SectionPath, index: int) -> None:
        """参照行のスナップショットを、今の参照先の値に取り直す(スナップショットの方式のときだけ)。"""
        task = self.tasks_in(path)[index]
        if task.kind is not TaskKind.REFERENCE or self.project.reference_mode is not ReferenceMode.SNAPSHOT:
            return
        taken = take_snapshot(self.reference_resolver, task.ref_project, datetime.now())
        if taken is None:
            ui.notify(f"「{task.ref_project}」を読めないため、更新できません", type="warning")
            return
        task.ref_snapshot = taken
        self.after_edit()
        ui.notify(f"「{task.name}」のスナップショットを更新しました")

    def open_reference(self, task_id: str) -> None:
        """参照先のプロジェクトへ切り替える。スナップショットが古ければ、先に更新の確認を出す。更新すると未保存になるので、続けて保存の確認が出る。"""
        task = self.project.task_map().get(task_id)
        if task is None or task.kind is not TaskKind.REFERENCE:
            return
        self.files = {p.stem: p for p in list_project_files(self.project_dir)}
        name = task.ref_project
        if name not in self.files:
            ui.notify(f"参照先のプロジェクトが見つかりません: {name}", type="warning")
            return
        ref = build_references(self.project, self.reference_resolver, datetime.now()).get(task_id)
        if ref is not None and ref.stale:
            def update_then_open() -> None:
                path, index = self.locate(task_id)
                self.refresh_reference(path, index)
                self.request_open(name)

            open_stale_reference_dialog(name, update_then_open, lambda: self.request_open(name))
            return
        self.request_open(name)
```

`self.locate(task_id) -> tuple[SectionPath, int]` が無ければ、`arrange` にある「タスクの位置を探す」関数(`grep -n "def .*locate\|def find_task\|def position_of" src/projectapp/arrange.py`)を使うか、`refresh_reference` を `task` を直接受ける内部関数 `_refresh(task)` に分けて、`update_then_open` はそれを呼ぶ(`refresh_reference(path, index)` は `_refresh(self.tasks_in(path)[index])` を呼ぶだけにする)。後者のほうが簡単なので、こちらにする。

`show_project` の末尾(`self.gantt.reset_scroll()` の後)に:

```python
        for name in missing_references(project, self.reference_resolver, datetime.now()):
            ui.notify(f"参照先のプロジェクトが見つかりません: {name}", type="warning")
```

`open_settings` に `reference_mode=self.project.reference_mode, on_reference_mode=self.apply_reference_mode,` を足す。

- [ ] **Step 5: 通ることを確認してコミット**

Run: `uv run pytest test/test_views.py test/test_settings*.py -q` → PASS。全体も流す: `uv run pytest -q 2>&1 | tail -5`

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: プロジェクト参照の設定・クリックの確認・更新・見つからない通知をつなぐ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: PlantUML(と PNG の確認)

**Files:**
- Modify: `src/projectapp/plantuml.py`(`build_plantuml` の引数と `emit`)
- Modify: `src/projectapp/views.py`(`build_plantuml` の呼び出しに参照を渡す)
- Test: `test/test_plantuml.py`、`test/test_views.py`(PNG)

**Interfaces:**
- Consumes: Task 3 の `Schedule(references=)`
- Produces: `build_plantuml(..., references: Mapping[str, ReferenceValue] | None = None)`。参照行は、`[基盤開発(参照)] as [T1] starts … and ends …`(担当者・進捗は出さない)。遅延があり`show_alerts`なら赤、なければ状態の色(未着手)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_plantuml.py` の既存の `build_plantuml(...)` の呼び方(引数の組み)に合わせる:

```python
def test_a_reference_row_is_one_band_named_with_the_reference_mark() -> None:
    ref = Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤")
    project = Project("本体", base_date=date(2026, 10, 1), tasks=[ref])
    value = ReferenceValue(planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 16, 17), progress=45, delayed=2)
    result = build_plantuml(project, {}, PERIOD, Scale.DAY, NOW, references={"ref": value})
    assert "[基盤開発(参照)] as [T1] starts 2026-10-05 and ends 2026-10-16" in result.text
    assert "[T1] is colored in" in result.text and "completed" not in result.text  # 進捗は出さない
    assert result.drawn == 1


def test_a_reference_row_without_a_value_is_skipped_and_counted() -> None:
    ref = Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤")
    project = Project("本体", base_date=date(2026, 10, 1), tasks=[ref])
    result = build_plantuml(project, {}, PERIOD, Scale.DAY, NOW)
    assert result.drawn == 0 and result.skipped == 1
```

(`PERIOD`・`NOW`・`result.drawn` の名前は、`test_plantuml.py` が使っている定数と `PlantUml` のフィールド名に合わせる。)

Run: FAIL を確認(`unexpected keyword argument 'references'`)。

- [ ] **Step 2: `plantuml.py`**

引数に `references: Mapping[str, ReferenceValue] | None = None,` を足し、`schedule = Schedule(project, holidays, references)` にする。`emit` の `CHECKPOINT` 分岐の前に:

```python
        if task.kind is TaskKind.REFERENCE:
            label = unique(_safe(f"{task.name}(参照)"))
            aliases[task.id] = alias
            order.append(task)
            drawn_days[task.id] = (first, last)
            target.append(f"[{label}] as [{alias}] starts {first.isoformat()} and ends {last.isoformat()}")
            value = (references or {}).get(task.id)
            late = show_alerts and value is not None and value.delayed > 0
            target.append(f"[{alias}] is colored in {OVERDUE_COLOR if late else STATUS_COLORS[Status.NOT_STARTED]}")
            return
```

(この分岐は、既存の `alias = ...`・`label = ...` の採番の後に入れる。`label` の二重採番にならないよう、既存の `label = unique(_safe(task.name))` の位置を、参照行のときは `名前(参照)` で作るように分岐させる。実装は、既存の `label = unique(_safe(task.name))` を `label = unique(_safe(f"{task.name}(参照)" if task.kind is TaskKind.REFERENCE else task.name))` に変え、上の分岐は `alias`・`label` の採番の直後に置いて、`CHECKPOINT` の `if` を `elif` の並びにする。)

`overdue` の行は、参照行では上の分岐で `return` するので通らない。

- [ ] **Step 3: views の呼び出し**

`build_plantuml(` を呼んでいる箇所(`grep -n "build_plantuml(" src/projectapp/views.py`)に、`references={tid: ref.value for tid, ref in build_references(self.project, self.reference_resolver, datetime.now()).items() if ref.value is not None},` を足す。

- [ ] **Step 4: PNG の確認テスト**

PNG はプレビューと同じ DOM を撮るので、実装は要らない。`test/test_views.py` に、プレビュー中に参照行が描かれることを確かめるテストを足す(`mount_preview` の既存テストの形):

```python
async def test_the_preview_draws_the_reference_band_without_the_click_handler(user: User, tmp_path: Path) -> None:
    save_project(reference_setup(tmp_path), tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    views[0].request_open("本体")
    views[0].enter_preview()  # 既存のテストがプレビューを開く呼び出しに合わせる
    await user.should_see(marker="bar-top-0")
    assert "ref-link" not in user.find(marker="bar-top-0").elements.pop().classes  # 読み取り専用では、クリックで開かない
```

- [ ] **Step 5: 通ることを確認してコミット**

Run: `uv run pytest test/test_plantuml.py test/test_views.py -q` → PASS

```bash
uv run ty check src | tail -1
git add -A
git commit -m "feat: プロジェクト参照を PlantUML の帯で出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 3 者マージ・コピー・ほかの機能・文書

**Files:**
- Modify: `src/projectapp/merge.py`(項目の名前の対応表)
- Modify: `src/projectapp/arrange.py`(コピー。必要なら)
- Test: `test/test_merge.py`、`test/test_arrange*.py`
- Modify: `CLAUDE.md`、`docs/requests.md`、`docs/superpowers/specs/2026-10-25-project-reference-design.md`、`docs/development.md`

**Interfaces:**
- Consumes: Task 1 のモデル

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_reference_fields_are_merged_per_item() -> None:
    base = Project("p", tasks=[Task("基盤開発", id="r", kind=TaskKind.REFERENCE, ref_project="基盤")])
    mine = replace_task(base, ref_project="基盤2")  # 自分が参照先を変えた
    theirs = replace_task(base, name="基盤の開発")  # 相手が名前を変えた
    result = merge_projects(base, mine, theirs)
    task = result.project.tasks[0]
    assert (task.ref_project, task.name) == ("基盤2", "基盤の開発")
    assert not result.conflicts


def test_a_copied_reference_row_keeps_its_target_and_snapshot() -> None:
    value = ReferenceValue(planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 6))
    project = Project("p", tasks=[Task("基盤開発", id="r", kind=TaskKind.REFERENCE, ref_project="基盤", ref_snapshot=value)])
    arrange.copy_task(project, ((), 0), ((), 1))
    copy = project.tasks[1]
    assert (copy.kind, copy.ref_project, copy.ref_snapshot) == (TaskKind.REFERENCE, "基盤", value) and copy.id != "r"
```

(`replace_task`・`merge_projects` の戻り値の形は、`test_merge.py` の既存の補助関数・戻り値に合わせる。)

Run: `uv run pytest test/test_merge.py test/test_arrange.py -q -k reference`

- [ ] **Step 2: 実装を確かめて直す**

`merge.py` の項目の対応表(`232` 行付近の `"urls": "リンク", ..., "weekly_crew": "週ごとの担当"` の辞書)に `"ref_project": "参照先", "ref_snapshot": "スナップショット"` を足す。`fields(Task)` で全項目を比べているので、この 2 つの値は項目ごとに比べられる(`ReferenceValue` は frozen dataclass なので `==` で比べられる)。`merge.py:384` 付近の「リスト以外の項目」の分岐で、`ref_snapshot` がそのまま `Task(**data)` に渡ることを確かめる。`arrange.copy_task`/`_plain_copy` は `replace(...)` で全項目を引き継ぐので、`ref_*` も引き継がれる(落ちたら、`_plain_copy` が項目を列挙していないか確かめて足す)。

- [ ] **Step 3: 通ることを確認する**

Run: `uv run pytest test/test_merge.py test/test_arrange.py -q` → PASS

- [ ] **Step 4: 文書を直す**

- `CLAUDE.md`(`projectapp/CLAUDE.md`): 「ガントチャート」の節に、プロジェクト参照の項目を足す(種別・参照の方式・帯・チップ・縞・ホバー・クリック・確認ダイアログ 2 種・見つからないとき・右クリックの`更新`・先行・締切・PlantUML・PNG・集計から外す)。「データの保存先」に`version` を 11 にしたことと、`reference_mode`・`ref_project`・`ref_snapshot` を足す。「ヘッダー」の設定ダイアログの説明に`参照の方式`を足す。
- `docs/requests.md`: 要望 56 の状態を「実装済み(2026-10-25。実機確認待ち)」にする。
- 設計書: 「クリックで開く」の節の、両方に当てはまるときの順序を、実装に合わせて直す: 「スナップショットが古いときは、先に更新の確認を出す。`更新して開く`で更新すると未保存になるので、続けて未保存の確認(`保存して開く`・`保存せず開く`・`キャンセル`)が出る。古くないときは、未保存の編集があれば、未保存の確認だけが出る」。
- `docs/development.md`: モジュール構成に`reference.py`(参照値の算出・参照先の読み込み)を足し、ファイル形式の注意に version 11 を足す。

- [ ] **Step 5: 全体の検証とコミット**

Run: `uv run pytest -q 2>&1 | tail -4` → 全件 PASS。`uv run ty check src | tail -1` → `All checks passed!`

```bash
git add -A
git commit -m "feat: プロジェクト参照を 3 者マージ・コピーに載せ、仕様を反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 実機で確認する(ネイティブで起動)**

`uv run projectapp` で、(1) 2 つのプロジェクト(`基盤`・`本体`)を作り、`本体`に`基盤`を参照する行を足す。(2) 帯・チップ・縞・ホバー・下線を確かめる。(3) クリックで`基盤`へ切り替わる(未保存の編集があれば確認が出る)。(4) 設定で`スナップショット`にし、`基盤`を編集して保存したあと、`本体`でクリックして`スナップショットが古くなっています`が出ることと、右クリックの`更新`を確かめる。(5) `基盤.json`を退避して`本体`を開き、通知と`(参照先が見つかりません)`を確かめる。(6) PNG と PlantUML に帯が出ることを確かめる。結果を `docs/requests.md` の要望 56 に記録する。

---

## Self-Review(計画の見直し)

**Spec coverage**

| 設計書の項目 | Task |
|---|---|
| 種別・`ref_project`・`ref_snapshot`・`reference_mode`・version 11・検証 | 1 |
| 参照値の算出(予定・実績・進捗・遅延・負荷) | 2 |
| 参照行の日程・先行・超過・集計からの除外 | 3 |
| 参照先の読み込み・キャッシュ・スナップショット・見つからない | 4 |
| 追加・編集ダイアログ | 5 |
| 帯・チップ・縞・ホバー・下線・クリック・見つからない表示・右クリックの`更新`・`分解`/`週ごと`の不可 | 6 |
| 設定の切り替え・クリックの 2 種類の確認・更新・見つからない通知 | 7 |
| PlantUML・PNG | 8 |
| 3 者マージ・コピー・文書 | 9 |

`分解…`・`週ごとに分ける`が参照行で押せないことは、既存の `decompose_block_reason`(通常タスク以外は不可)と `toggle_weeks` の可否判定(担当者のいるタスクだけ)で、すでに満たされる。Task 6 の Step 1 に、右クリックのメニューで 2 つが `disable` であることのテストを入れてある。

**型の整合**: `ReferenceValue`・`OverloadSpan`(Task 1)→ `compute_reference`(Task 2)→ `Schedule(references=Mapping[str, ReferenceValue])`(Task 3)→ `Reference`・`build_references`・`take_snapshot`(Task 4)→ `GanttChart(references=Callable[[], dict[str, Reference]])`(Task 6)→ `MainView`(Task 7)の名前・引数は、この計画の中で一致している。`build_plantuml(references=Mapping[str, ReferenceValue])`(Task 8)は、`Reference.value` を取り出した辞書を渡す。

**既知の前提(実装者が最初に確かめること)**: テストの補助(`Recorder`・`mount_capturing`・`mount_preview`・`FakeExporter`・`built`・`PERIOD`)の正確な形、`task_dialog.py` の保存ボタンと `status`/`category`/`priority_box`/`url_box` の変数名は、該当する既存のテストとコードを開いて合わせる(この計画の該当箇所に、確かめる手がかりを書いた)。
