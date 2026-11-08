# 変更履歴の日ごとのまとめと件数の上限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保存するときだけ、古い変更履歴を「タスク・日ごと」に 1 件へまとめ、件数の上限を超えたら古い日から捨てる(要望 128 段階 3 = 3a)。

**Architecture:** `history_log.compacted(project, now, keep)` を純粋関数として足し(元は変えず、まとめた履歴を持つ複製を返す)、`views.commit` が保存の直前にだけ呼ぶ。古さの日数と件数の上限は`config.json`に置き、`全体の設定`のダイアログから変える。ファイル形式(`version` 21)は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -m smoke`)、ruff、ty。

**Spec:** [`docs/superpowers/specs/2026-11-08-history-compaction-design.md`](../specs/2026-11-08-history-compaction-design.md)

## Global Constraints

- 言語は日本語(文言・コメント・テスト名の説明)。Python 3.13 以上。NiceGUI に依存しない部分(`history_log.py`・`config.py`)に NiceGUI を import しない。
- ファイル形式の`version`は 21 のまま。`FORMAT_VERSION`を変えない。
- `compacted`は引数のプロジェクトを書き換えない(`replace`で複製する)。
- 0 時の境目での`states_at`の結果は、まとめる前後で変わらない。
- 設定値の範囲外・不正は既定に戻して読む。`days` 7〜3650(既定 90)、`max_events` 1000〜1000000(既定 50000)。
- 作業のたびの検証順: `uv run pytest -m smoke` → `uvx ruff check` → `uvx ruff format src test` → `uvx ty check src`(失敗したときに限り全テスト`uv run pytest -n auto`)。
- コミットの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。マージは利用者の指示を待つ(PR で止まる)。
- ブランチは`feature/history-compaction`(作成済み)。

## Review Focus

- 同じ時刻の複数イベント(順序を保つこと)。
- 前後がつながらない履歴(先頭の前・末尾の後をそのまま取る)。
- 作った日に退場したタスク(前後がどちらも`なし`の項目を残し、復元が`なし`のまま)。
- `history_since`の境目(上限で捨てたあとの、捨てた翌日の 0 時以降の復元)。
- 1 日分だけで上限を超える場合(最新の日は捨てない)。

---

### Task 1: `compacted`(日ごとのまとめと上限)

**Files:**
- Modify: `src/projectapp/history_log.py`
- Test: `test/test_history_log.py`、`test/test_dashboard.py`

**Interfaces:**
- Consumes: `models.HISTORY_FIELDS`・`Change`・`HistoryEvent`・`Project`・`Value`、`history_log.states_at`・`events_by_task`。
- Produces:
  - 定数 `DEFAULT_DETAIL_DAYS = 90`・`MIN_DETAIL_DAYS = 7`・`MAX_DETAIL_DAYS = 3650`・`DEFAULT_MAX_EVENTS = 50_000`・`MIN_MAX_EVENTS = 1_000`・`MAX_MAX_EVENTS = 1_000_000`
  - `HistoryKeep(days: int = 90, max_events: int = 50_000)`(frozen dataclass)
  - `compacted(project: Project, now: datetime, keep: HistoryKeep) -> Project`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_history_log.py` の import に`HistoryKeep`・`compacted`を足し、末尾に追記)

```python
from datetime import date, timedelta  # 既存の import に足す(datetime だけなら timedelta・date を追加)

from projectapp.history_log import HistoryKeep, compacted  # 既存の import に足す

NOW = datetime(2026, 11, 8, 12)
KEEP = HistoryKeep(days=7, max_events=50_000)  # カット線: 2026-11-01 0:00


def midnights(since: datetime, until: datetime) -> list[datetime]:
    """`since`より後の最初の 0 時から、`until`の日の 0 時まで、毎日の 0 時。"""
    first = datetime.combine(since.date() + timedelta(1), datetime.min.time())
    days = (until.date() - first.date()).days + 1
    return [first + timedelta(d) for d in range(days)]


def restored(project: Project, moments: list[datetime]) -> dict[str, list]:
    index = events_by_task(project)
    return {
        t.id: states_at(t, index.get(t.id, []), moments) for t in project.all_tasks()
    }


def long_project() -> Project:
    """a: 10/20 に作成 → 10/21 に着手(同じ日に 2 回進捗) → 10/25 に終了。b: 10/22 に作成。c: 10/23 に作成して 10/23 のうちに分解で退場。"""
    a = Task("a", id="a", effort_hours=10, status=Status.DONE, progress=100)
    b = Task("b", id="b", effort_hours=4, progress=20)
    c = Task("c", id="c", kind=TaskKind.SUMMARY, children=["x"])
    x = Task("x", id="x")
    events = [
        ev("a", datetime(2026, 10, 20, 9), status=(None, "未着手"), progress=(None, None), effort=(None, 10.0)),
        ev("a", datetime(2026, 10, 21, 9), status=("未着手", "実行中"), progress=(None, 30)),
        ev("a", datetime(2026, 10, 21, 15), progress=(30, 60)),
        ev("a", datetime(2026, 10, 25, 11), status=("実行中", "終了"), progress=(60, 100)),
        ev("b", datetime(2026, 10, 22, 9), status=(None, "未着手"), progress=(None, 20), effort=(None, 4.0)),
        ev("c", datetime(2026, 10, 23, 9), status=(None, "未着手"), progress=(None, None), effort=(None, 1.0)),
        ev("c", datetime(2026, 10, 23, 16), status=("未着手", None), progress=(None, None), effort=(1.0, None)),
        ev("b", datetime(2026, 11, 3, 10), progress=(20, 50)),
    ]
    return Project(
        "p", tasks=[a, b, c, x], history=events, history_since=datetime(2026, 10, 20, 8)
    )


def test_old_events_of_one_task_and_day_become_one_event() -> None:
    result = compacted(long_project(), NOW, KEEP)
    day = [e for e in result.history if e.task == "a" and e.at.date() == date(2026, 10, 21)]
    assert day == [
        ev("a", datetime(2026, 10, 21, 15), status=("未着手", "実行中"), progress=(None, 60))
    ]


def test_events_newer_than_the_cut_line_are_untouched() -> None:
    project = long_project()
    result = compacted(project, NOW, KEEP)
    assert ev("b", datetime(2026, 11, 3, 10), progress=(20, 50)) in result.history


def test_restoring_at_every_midnight_is_unchanged() -> None:
    project = long_project()
    moments = midnights(project.history_since, NOW)
    result = compacted(project, NOW, KEEP)
    assert len(result.history) < len(project.history)
    assert restored(result, moments) == restored(project, moments)


def test_compacting_twice_gives_the_same_result() -> None:
    once = compacted(long_project(), NOW, KEEP)
    assert compacted(once, NOW, KEEP) == once


def test_the_original_project_is_not_changed() -> None:
    project = long_project()
    before = list(project.history)
    compacted(project, NOW, KEEP)
    assert project.history == before
    assert project.history_since == datetime(2026, 10, 20, 8)


def test_a_task_created_and_retired_on_the_same_day_stays_nonexistent() -> None:
    project = long_project()
    result = compacted(project, NOW, KEEP)
    day = [e for e in result.history if e.task == "c"]
    assert len(day) == 1
    assert all(c.before is None and c.after is None for c in day[0].changes if c.field == "status")
    moments = midnights(project.history_since, NOW)
    assert all(s is None for s in restored(result, moments)["c"])


def test_events_of_deleted_tasks_are_dropped() -> None:
    project = long_project()
    project.history.append(ev("gone", datetime(2026, 10, 22, 9), status=(None, "未着手")))
    result = compacted(project, NOW, KEEP)
    assert all(e.task != "gone" for e in result.history)


def test_events_at_the_same_moment_keep_their_recorded_order() -> None:
    at = datetime(2026, 10, 21, 9)
    task = Task("a", id="a", progress=70)
    project = Project(
        "p",
        tasks=[task],
        history=[ev("a", at, progress=(None, 30)), ev("a", at, progress=(30, 70))],
        history_since=datetime(2026, 10, 20),
    )
    result = compacted(project, NOW, KEEP)
    assert result.history == [ev("a", at, progress=(None, 70))]


def test_a_field_that_returns_to_its_first_value_disappears() -> None:
    task = Task("a", id="a", progress=30)
    project = Project(
        "p",
        tasks=[task],
        history=[
            ev("a", datetime(2026, 10, 21, 9), progress=(30, 50)),
            ev("a", datetime(2026, 10, 21, 15), progress=(50, 30)),
        ],
        history_since=datetime(2026, 10, 20),
    )
    assert compacted(project, NOW, KEEP).history == []


def test_nothing_happens_without_history() -> None:
    project = Project("p", tasks=[Task("a", id="a")])
    assert compacted(project, NOW, KEEP) == project


def cap_project() -> Project:
    """a が 10/21〜10/24 の 4 日、毎日 1 件進む(合計 4 件)。"""
    task = Task("a", id="a", progress=40)
    events = [
        ev("a", datetime(2026, 10, 20, 9), status=(None, "実行中"), progress=(None, 0), effort=(None, 1.0)),
        ev("a", datetime(2026, 10, 21, 9), progress=(0, 10)),
        ev("a", datetime(2026, 10, 22, 9), progress=(10, 20)),
        ev("a", datetime(2026, 10, 23, 9), progress=(20, 40)),
    ]
    return Project("p", tasks=[task], history=events, history_since=datetime(2026, 10, 20, 8))


def test_over_the_cap_the_oldest_whole_days_go_and_the_start_moves() -> None:
    project = cap_project()
    result = compacted(project, NOW, HistoryKeep(days=7, max_events=2))
    assert [e.at.date() for e in result.history] == [date(2026, 10, 22), date(2026, 10, 23)]
    assert result.history_since == datetime(2026, 10, 22)
    moments = midnights(result.history_since - timedelta(1), NOW)  # 10/22 0:00 から
    assert restored(result, moments) == restored(project, moments)


def test_the_latest_day_is_never_dropped_even_over_the_cap() -> None:
    project = cap_project()
    result = compacted(project, NOW, HistoryKeep(days=7, max_events=0))
    assert [e.at.date() for e in result.history] == [date(2026, 10, 23)]
    assert result.history_since == datetime(2026, 10, 23)


def test_under_the_cap_the_start_does_not_move() -> None:
    project = cap_project()
    result = compacted(project, NOW, HistoryKeep(days=7, max_events=100))
    assert result.history_since == project.history_since
```

また、`test/test_dashboard.py` の末尾に集計の不変テストを追記する(`delta_project`・`hevent`・`D_NOW`・`DELTA_WEEK`・`summarize_burndown`は既存。import に`from projectapp.history_log import HistoryKeep, compacted`を足す):

```python
def test_compacting_old_history_does_not_change_the_aggregates() -> None:
    project = delta_project()
    project.history = [  # 11/3 に 2 回進み、つながった履歴にする
        hevent("a", datetime(2026, 11, 3, 10), status=("未着手", "実行中"), progress=(None, 50)),
        hevent("a", datetime(2026, 11, 3, 15), progress=(50, 70)),
        hevent("a", datetime(2026, 11, 5, 10), status=("実行中", "終了"), progress=(70, 100)),
    ]
    result = compacted(project, D_NOW, HistoryKeep(days=1, max_events=50_000))
    assert len(result.history) == 2
    assert summarize_progress_delta(result, DELTA_WEEK, D_NOW, {}) == summarize_progress_delta(
        project, DELTA_WEEK, D_NOW, {}
    )
    assert summarize_burndown(result, DELTA_WEEK, D_NOW, {}) == summarize_burndown(
        project, DELTA_WEEK, D_NOW, {}
    )
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_history_log.py test/test_dashboard.py -q -k "compact or cap or latest_day or midnight or retired or deleted_tasks or same_moment or returns_to_its_first or nothing_happens or old_events or newer_than or original_project or twice or does_not_move"`
Expected: FAIL(ImportError: cannot import name 'compacted' / 'HistoryKeep')

- [ ] **Step 3: 実装する**(`src/projectapp/history_log.py`)

import を直す:

```python
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta
from math import isfinite
```

末尾に追記:

```python
DEFAULT_DETAIL_DAYS = 90  # 細かい履歴を残す日数
MIN_DETAIL_DAYS = 7
MAX_DETAIL_DAYS = 3650
DEFAULT_MAX_EVENTS = 50_000  # 履歴の件数の上限
MIN_MAX_EVENTS = 1_000
MAX_MAX_EVENTS = 1_000_000


@dataclass(frozen=True)
class HistoryKeep:
    """保存するときの履歴の残し方。`days`より古い分は日ごとにまとめ、`max_events`を超えたら古い日から捨てる。"""

    days: int = DEFAULT_DETAIL_DAYS
    max_events: int = DEFAULT_MAX_EVENTS


def _merge_day(events: Sequence[HistoryEvent]) -> HistoryEvent | None:
    """同じタスク・同じ日のイベント(記録した順)を 1 件にする。項目ごとに最初の前と最後の後を取り、
    前後が同じ項目は消す(前後がどちらも None の項目は、存在しないままを表すので残す)。変わった項目がなければ None。"""
    first: dict[str, Value] = {}
    last: dict[str, Value] = {}
    for event in events:
        for change in event.changes:
            first.setdefault(change.field, change.before)
            last[change.field] = change.after
    changes = tuple(
        Change(name, first[name], last[name])
        for name in HISTORY_FIELDS
        if name in first and (first[name] != last[name] or first[name] is None)
    )
    return HistoryEvent(events[-1].task, events[-1].at, changes) if changes else None


def _trim(
    events: list[HistoryEvent], since: datetime | None, limit: int
) -> tuple[list[HistoryEvent], datetime | None]:
    """件数が`limit`以下になるまで、古い日から日ごと丸ごと捨てる(最新の日は残す)。捨てたら記録の開始を、
    捨てた最後の日の翌日の 0 時へ進める(すでにそれより後ならそのまま)。"""
    counts = Counter(event.at.date() for event in events)
    total = len(events)
    dropped: date | None = None
    for day in sorted(counts)[:-1]:
        if total <= limit:
            break
        total -= counts[day]
        dropped = day
    if dropped is None:
        return events, since
    boundary = datetime.combine(dropped + timedelta(1), time.min)
    kept = [event for event in events if event.at >= boundary]
    return kept, boundary if since is None else max(since, boundary)


def compacted(project: Project, now: datetime, keep: HistoryKeep) -> Project:
    """保存用に、履歴をまとめた複製を返す(元は変えない)。今のプロジェクトにないタスクのイベントを捨て、
    「`now`の日の 0 時 − `keep.days`日」より古いイベントをタスク・日ごとに 1 件にし、件数が`keep.max_events`を
    超えるなら古い日から捨てる。0 時の境目での復元結果は変わらない。"""
    if not project.history:
        return project
    alive = {task.id for task in project.all_tasks()}
    events = sorted((e for e in project.history if e.task in alive), key=lambda e: e.at)
    cutoff = datetime.combine(now.date(), time.min) - timedelta(days=keep.days)
    days: dict[tuple[str, date], list[HistoryEvent]] = {}
    recent = []
    for event in events:
        if event.at < cutoff:
            days.setdefault((event.task, event.at.date()), []).append(event)
        else:
            recent.append(event)
    merged = [m for group in days.values() if (m := _merge_day(group)) is not None]
    merged.sort(key=lambda e: e.at)
    result = [*merged, *recent]
    since = project.history_since
    if len(result) > keep.max_events:
        result, since = _trim(result, since, keep.max_events)
    return replace(project, history=result, history_since=since)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_history_log.py test/test_dashboard.py -q`
Expected: PASS(新規テスト 14 件を含め全部)

- [ ] **Step 5: 検査してコミットする**

```bash
uvx ruff format src test && uvx ruff check && uvx ty check src
git add src/projectapp/history_log.py test/test_history_log.py test/test_dashboard.py
git commit -m "feat: 履歴を日ごとにまとめ、件数の上限をかける関数を足す(要望 128 段階 3)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 設定(`config.json`)の読み書き

**Files:**
- Modify: `src/projectapp/config.py`
- Test: `test/test_config.py`

**Interfaces:**
- Consumes: `history_log.HistoryKeep`・`DEFAULT_*`・`MIN_*`・`MAX_*`、`config.read_config`・`update_config`・`_finite_number`。
- Produces: `parse_history_keep(raw: dict) -> HistoryKeep`、`load_history_keep(base_dir=BASE_DIR) -> HistoryKeep`、`save_history_keep(keep: HistoryKeep, base_dir=BASE_DIR) -> None`(キーは`history_detail_days`・`history_max_events`)。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_config.py` の末尾。import に`load_history_keep`・`save_history_keep`と`from projectapp.history_log import HistoryKeep`を足す)

```python
def test_history_keep_defaults_when_nothing_is_saved(tmp_path: Path) -> None:
    assert load_history_keep(tmp_path) == HistoryKeep(90, 50_000)


def test_history_keep_round_trips(tmp_path: Path) -> None:
    save_history_keep(HistoryKeep(30, 20_000), tmp_path)
    assert load_history_keep(tmp_path) == HistoryKeep(30, 20_000)
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["history_detail_days"] == 30 and raw["history_max_events"] == 20_000


@pytest.mark.parametrize(
    ("days", "max_events", "expected"),
    [
        (1, 10, HistoryKeep(7, 1_000)),  # 下限へ寄せる
        (99999, 10**9, HistoryKeep(3650, 1_000_000)),  # 上限へ寄せる
        ("x", None, HistoryKeep(90, 50_000)),  # 不正は既定
        (True, [1], HistoryKeep(90, 50_000)),
        (45.6, 2500.4, HistoryKeep(46, 2500)),  # 丸める
    ],
)
def test_history_keep_is_clamped_or_defaulted(
    tmp_path: Path, days: object, max_events: object, expected: HistoryKeep
) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps({"history_detail_days": days, "history_max_events": max_events}),
        encoding="utf-8",
    )
    assert load_history_keep(tmp_path) == expected
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_config.py -q -k history_keep`
Expected: FAIL(ImportError)

- [ ] **Step 3: 実装する**(`src/projectapp/config.py`。`from projectapp.history_log import (...)` を import に足し、`save_open_ratio`の後に追記)

```python
from projectapp.history_log import (
    DEFAULT_DETAIL_DAYS,
    DEFAULT_MAX_EVENTS,
    MAX_DETAIL_DAYS,
    MAX_MAX_EVENTS,
    MIN_DETAIL_DAYS,
    MIN_MAX_EVENTS,
    HistoryKeep,
)


def _clamped_int(value: object, low: int, high: int, default: int) -> int:
    number = _finite_number(value)
    return default if number is None else min(max(round(number), low), high)


def parse_history_keep(raw: dict) -> HistoryKeep:
    """履歴の残し方の検証。有限の数を丸めて範囲に収め、それ以外は既定にする。"""
    return HistoryKeep(
        _clamped_int(
            raw.get("history_detail_days"),
            MIN_DETAIL_DAYS,
            MAX_DETAIL_DAYS,
            DEFAULT_DETAIL_DAYS,
        ),
        _clamped_int(
            raw.get("history_max_events"),
            MIN_MAX_EVENTS,
            MAX_MAX_EVENTS,
            DEFAULT_MAX_EVENTS,
        ),
    )


def load_history_keep(base_dir: Path = BASE_DIR) -> HistoryKeep:
    return parse_history_keep(read_config(base_dir))


def save_history_keep(keep: HistoryKeep, base_dir: Path = BASE_DIR) -> None:
    update_config(
        {"history_detail_days": keep.days, "history_max_events": keep.max_events},
        base_dir,
    )
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_config.py -q`
Expected: PASS

- [ ] **Step 5: 検査してコミットする**

```bash
uvx ruff format src test && uvx ruff check && uvx ty check src
git add src/projectapp/config.py test/test_config.py
git commit -m "feat: 履歴の残し方(古さの日数・件数の上限)を config.json に持つ(要望 128 段階 3)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 保存への組み込みと通知

**Files:**
- Modify: `src/projectapp/views.py`(`__init__`・`commit`)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `history_log.compacted`・`HistoryKeep`、`config.load_history_keep`、`MainView.now`・`base_dir`・`project`。
- Produces: `MainView.history_keep: HistoryKeep`(設定ダイアログが更新する)。`commit`は保存の直前に`compacted(self.project, self.now(), self.history_keep)`を`save_project`に渡す。上限で`history_since`が進んだときだけ、保存後に`履歴が上限を超えたため、m/d より前の履歴を捨てました`と通知する。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_views.py` の末尾。`make_view`・`save_cache`・`wait_until`・`mount_capturing`は既存。import に`HistoryKeep`・`HistoryEvent`・`Change`が足りなければ足す)

```python
def old_history_project(name: str = "p") -> Project:
    task = Task("a", id="a", progress=60)
    return Project(
        name,
        tasks=[task],
        history=[
            HistoryEvent("a", datetime(2026, 1, 5, 9), (Change("progress", None, 30),)),
            HistoryEvent("a", datetime(2026, 1, 5, 15), (Change("progress", 30, 60),)),
            HistoryEvent("a", datetime(2026, 1, 6, 9), (Change("effort", 1.0, 2.0),)),
        ],
        history_since=datetime(2026, 1, 1),
    )


async def test_saving_writes_the_compacted_history_and_keeps_memory_as_it_is(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.now = lambda: datetime(2026, 11, 8, 12)
    view.project = old_history_project()
    memory = list(view.project.history)
    assert view.commit(overwrite=True, after=None)
    saved = load_project(tmp_path / "p.json")
    assert len(saved.history) == 2  # 1/5 の 2 件が 1 件に
    assert view.project.history == memory  # 画面のデータは細かいまま
    assert not view.is_dirty()  # 保存後は未保存の扱いにならない


async def test_a_save_that_only_compacts_does_not_notify_about_dropping(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.now = lambda: datetime(2026, 11, 8, 12)
    view.project = old_history_project()
    view.commit(overwrite=True, after=None)
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    assert not user.notify.contains("履歴が上限を超えた")


async def test_going_over_the_cap_drops_old_days_and_tells_the_user(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.now = lambda: datetime(2026, 11, 8, 12)
    view.history_keep = HistoryKeep(days=7, max_events=1)
    view.project = old_history_project()
    view.commit(overwrite=True, after=None)
    saved = load_project(tmp_path / "p.json")
    assert [e.at.date() for e in saved.history] == [date(2026, 1, 6)]
    assert saved.history_since == datetime(2026, 1, 6)
    assert await wait_until(
        lambda: user.notify.contains("履歴が上限を超えたため、01/06 より前の履歴を捨てました")
    )
```

(`view.project.name`が`"p"`でないと`save_project`の名前検査で失敗する。`old_history_project()`の既定名`"p"`で満たす。`load_project`は`projectapp.storage`、`date`は`datetime`と同じ import に足す。`view.is_dirty()`は、既存の未保存判定のメソッド名に合わせる。`views.py:803`付近の`def`名を確認して使うこと。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k "compacted_history or only_compacts or over_the_cap"`
Expected: FAIL(`MainView`に`history_keep`がない / 履歴がまとまらない)

- [ ] **Step 3: 実装する**(`src/projectapp/views.py`)

import に足す: `from projectapp.history_log import HistoryKeep, compacted`(`history_log`は既に`import`されているので、モジュール参照なら`history_log.compacted`でもよい。既存の流儀は`history_log.record_edit`なので、`history_log.compacted(...)`を使い、`HistoryKeep`の型注釈のために`from projectapp.history_log import HistoryKeep`を足す)と、`config`の import 群に`load_history_keep`を足す。

`__init__`の`self.open_ratio = load_open_ratio(base_dir)`の次の行に:

```python
        self.history_keep: HistoryKeep = load_history_keep(
            base_dir
        )  # 保存するときの履歴の残し方。全プロジェクト共通
```

`commit`を次のように直す(`save_project`の呼び出しと、成功後の通知):

```python
        stored = history_log.compacted(self.project, self.now(), self.history_keep)
        try:
            path = save_project(stored, self.project_dir, overwrite=overwrite)
        except FileExistsError:
```

`ui.notify("保存しました")`の直後に足す:

```python
        if stored.history_since != self.project.history_since and stored.history_since:
            ui.notify(
                f"履歴が上限を超えたため、{stored.history_since:%m/%d} より前の履歴を捨てました",
                type="warning",
            )
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_views.py -q -k "compacted_history or only_compacts or over_the_cap"` の後、`uv run pytest -m smoke -q`
Expected: PASS

- [ ] **Step 5: 検査してコミットする**

```bash
uvx ruff format src test && uvx ruff check && uvx ty check src
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: 保存するときだけ履歴をまとめ、上限で捨てたら通知する(要望 128 段階 3)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `全体の設定`のダイアログに数値欄を足す

**Files:**
- Modify: `src/projectapp/global_settings_dialog.py`、`src/projectapp/views.py`(`open_global_settings`・`apply_open_ratio`の周り)
- Test: `test/test_global_settings.py`

**Interfaces:**
- Consumes: `config.save_history_keep`・`load_history_keep`、`HistoryKeep`と`MIN_*`・`MAX_*`、`MainView.history_keep`・`apply_open_ratio`。
- Produces: `open_global_settings_dialog(initial_ratio, initial_keep, on_preview, on_apply, on_cancel)`(`on_apply: Callable[[int, HistoryKeep], bool]`)、マーカー`global-settings-history-days`・`global-settings-history-max`、`MainView.apply_global_settings(ratio, keep) -> bool`。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_global_settings.py` の末尾。`from projectapp.history_log import HistoryKeep`を足す)

```python
async def test_the_dialog_shows_the_history_keep_and_applies_and_saves_it(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    await user.should_see(marker="global-settings-history-days")
    days = user.find(marker="global-settings-history-days").elements.pop()
    maximum = user.find(marker="global-settings-history-max").elements.pop()
    assert days.value == 90 and maximum.value == 50_000
    days.set_value(30)
    maximum.set_value(20_000)
    user.find(marker="global-settings-apply").click()
    assert config.load_history_keep(tmp_path) == HistoryKeep(30, 20_000)
    assert view.history_keep == HistoryKeep(30, 20_000)


async def test_cancelling_does_not_save_the_history_keep(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    await user.should_see(marker="global-settings-history-days")
    user.find(marker="global-settings-history-days").elements.pop().set_value(30)
    user.find(marker="global-settings-cancel").click()
    assert config.load_history_keep(tmp_path) == HistoryKeep(90, 50_000)
    assert view.history_keep == HistoryKeep(90, 50_000)


async def test_out_of_range_values_are_clamped_when_applied(
    user: User, tmp_path: Path
) -> None:
    view = await open_view(user, tmp_path)
    user.find(marker="open-global-settings").click()
    await user.should_see(marker="global-settings-history-days")
    user.find(marker="global-settings-history-days").elements.pop().set_value(1)
    user.find(marker="global-settings-history-max").elements.pop().set_value(10**9)
    user.find(marker="global-settings-apply").click()
    assert view.history_keep == HistoryKeep(7, 1_000_000)
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_global_settings.py -q -k history_keep`
Expected: FAIL(マーカーが見つからない)

- [ ] **Step 3: 実装する**

`src/projectapp/global_settings_dialog.py`: docstring を「全体の設定のダイアログ(全プロジェクト共通の値)。下部パネルを開くときの比率と、保存するときの履歴の残し方。」に直し、import に`from projectapp.history_log import (MAX_DETAIL_DAYS, MAX_MAX_EVENTS, MIN_DETAIL_DAYS, MIN_MAX_EVENTS, HistoryKeep)`を足す。関数を次のようにする:

```python
def open_global_settings_dialog(
    initial_ratio: int,
    initial_keep: HistoryKeep,
    on_preview: Callable[[int], object],
    on_apply: Callable[[int, HistoryKeep], bool],
    on_cancel: Callable[[], object],
) -> None:
    """動かすとすぐ反映し(プレビュー)、`適用`で保存。適用せずに閉じたら`on_cancel`で元に戻す。"""
    applied = False
    current = initial_ratio
    keep = initial_keep
```

スライダーの注記ラベルの後(`def apply` の前)に追加:

```python
        ui.separator()
        ui.label("保存するときの履歴の残し方").classes("text-caption")

        def set_days(event: ValueChangeEventArguments) -> None:
            nonlocal keep
            if event.value is not None:
                keep = HistoryKeep(int(event.value), keep.max_events)

        def set_max(event: ValueChangeEventArguments) -> None:
            nonlocal keep
            if event.value is not None:
                keep = HistoryKeep(keep.days, int(event.value))

        ui.number(
            "細かい履歴を残す日数",
            value=initial_keep.days,
            format="%d",
            on_change=set_days,
        ).classes("w-full").mark("global-settings-history-days")
        ui.number(
            "履歴の件数の上限",
            value=initial_keep.max_events,
            format="%d",
            on_change=set_max,
        ).classes("w-full").mark("global-settings-history-max")
        ui.label(
            f"残す日数より古い履歴は、保存のときに日ごとにまとめます({MIN_DETAIL_DAYS}〜{MAX_DETAIL_DAYS} 日)。"
            f"件数が上限({MIN_MAX_EVENTS}〜{MAX_MAX_EVENTS})を超えたら、古い日から捨てます。"
        ).classes("text-caption text-grey")
```

`apply`内の`if on_apply(current):`を`if on_apply(current, keep):`にする。

`src/projectapp/views.py`: import に`save_history_keep`と`parse_history_keep`を足す。`show_global_settings_dialog(...)`の呼び出しを:

```python
        show_global_settings_dialog(
            self.open_ratio,
            self.history_keep,
            preview,
            self.apply_global_settings,
            cancel,
        )
```

にし、`apply_open_ratio`の前に追加:

```python
    def apply_global_settings(self, ratio: int, keep: HistoryKeep) -> bool:
        """開くときの割合と履歴の残し方を保存する。範囲外は範囲に収める。失敗したら通知して False。"""
        keep = parse_history_keep(
            {"history_detail_days": keep.days, "history_max_events": keep.max_events}
        )
        if not self.apply_open_ratio(ratio):
            return False
        try:
            save_history_keep(keep, self.base_dir)
        except OSError:
            ui.notify("全体の設定を保存できませんでした", type="warning")
            return False
        self.history_keep = keep
        return True
```

(`parse_history_keep`は`config`の公開関数。`apply_open_ratio`は既存のまま残す。)

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_global_settings.py -q` の後、`uv run pytest -m smoke -q`
Expected: PASS(既存のスライダーのテストも通る)

- [ ] **Step 5: 検査してコミットする**

```bash
uvx ruff format src test && uvx ruff check && uvx ty check src
git add src/projectapp/global_settings_dialog.py src/projectapp/views.py test/test_global_settings.py
git commit -m "feat: 全体の設定に、履歴を残す日数と件数の上限の欄を足す(要望 128 段階 3)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 性能の測定と文書の更新

**Files:**
- Modify: `.claude/spec/project-files.md`、`.claude/spec/header-git.md`、`docs/development.md`、`docs/requests.md`、`docs/superpowers/specs/2026-11-08-history-compaction-design.md`
- Test: `test/test_history_log.py`(性能の回帰テスト)

**Interfaces:**
- Consumes: Task 1〜4 の実装。
- Produces: 仕様・開発メモ・要望の状態の更新。

- [ ] **Step 1: 性能を測り、回帰テストを足す**(`test/test_history_log.py` の末尾)

```python
def test_compacting_a_years_history_of_300_tasks_is_fast() -> None:
    import time as clock

    tasks = [Task(f"t{i}", id=f"t{i}", progress=50) for i in range(300)]
    events = []
    start = datetime(2025, 11, 8, 9)
    for i in range(300):
        for step in range(33):  # 約 9,900 件
            events.append(
                ev(f"t{i}", start + timedelta(days=step * 11, hours=i % 8), progress=(step, step + 1))
            )
    project = Project("p", tasks=tasks, history=events, history_since=start)
    began = clock.perf_counter()
    result = compacted(project, NOW, HistoryKeep())
    took = clock.perf_counter() - began
    assert len(result.history) <= len(events)
    assert took < 1.0  # 目安は 0.1 秒未満。遅い環境でも落ちないよう 1 秒で見張る
```

Run: `uv run pytest test/test_history_log.py -q -k years_history` Expected: PASS。実測は`-s`付きの一時スクリプトか`--durations=3`で読み、設計書の「性能」に記録する。

- [ ] **Step 2: 設計書を直す**

`docs/superpowers/specs/2026-11-08-history-compaction-design.md` の 3 節で「保存の入口(`views.py` の`save_project` 2 か所)」を「保存の入口(`views.commit`の 1 か所。切り出しの子の保存は対象外)」に直し、7 節の末尾に実測値(Step 1)を 1 行足す。

- [ ] **Step 3: 仕様と文書を更新する**

- `.claude/spec/project-files.md`: 保存の項に「保存するときだけ、古い履歴〔`全体の設定`の日数より前〕をタスク・日ごとに 1 件にまとめ、件数が上限を超えたら古い日から捨てる(捨てたら記録の開始が進み、通知する)。画面のデータは細かいまま」を足す。
- `.claude/spec/header-git.md`の`全体の設定`の項(40 行目付近)に、2 つの数値欄(`細かい履歴を残す日数` 7〜3650・既定 90、`履歴の件数の上限` 1,000〜1,000,000・既定 50,000。`適用`で`config.json`の`history_detail_days`・`history_max_events`に保存)を足し、「今の項目は…だけ」の記述を直す。
- `docs/development.md`の`history_log.py`の行に`HistoryKeep`・`compacted`を足し、`global_settings_dialog.py`の行に履歴の残し方の欄を足す。
- `docs/requests.md`の要望 128 の状態を「段階 3(3a)は実装済み・PR 待ち」に直し、決定の追記(日ごとのまとめ・件数の上限・保存のときだけ・設定は`config.json`)を 1 段落足す。要望 129 の状態はそのまま。

- [ ] **Step 4: 全体を検査する**

Run: `uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: すべて通る。smoke が失敗したときに限り`uv run pytest -n auto`。

- [ ] **Step 5: コミットする**

```bash
git add -A
git commit -m "docs: 履歴のまとめと上限の仕様・開発メモ・要望の状態を更新する(要望 128 段階 3)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
