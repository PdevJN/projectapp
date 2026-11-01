# 下部パネルと縦の分割 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メインパネルを縦に分け、上にガントチャート、下に状態で切り替わる情報パネル(詳細・集計・今日の予定・凡例)を置き、縦幅をドラッグと設定で変えられるようにする(要望 111・95)。

**Architecture:** 集計は NiceGUI に依存しない純粋関数(`bottom_info.py`)、描画は `bottom_panel.py`、分割と選択への連動は `gantt.py`、保存は `config.py`・`views.py` が受け持つ。保存形式(プロジェクトの JSON)は変えない。

**Tech Stack:** Python 3.13、NiceGUI(`ui.splitter`・`ui.refreshable_method`)、pytest(`user` fixture)、ruff、ty

**Spec:** `docs/superpowers/specs/2026-11-01-bottom-panel-design.md`

## Global Constraints

- 言語は日本語。Python 3.13 以上。ライブラリは NiceGUI
- 保存形式(プロジェクトの JSON の`version` = 19)は変えない。集計は保存しない
- 設定は`~/.projectapp/config.json`(全プロジェクト共通): `main_split`(ガントチャートの割合 30〜100。既定 100)・`bottom_open_ratio`(開くときの割合 50〜90、5 刻み。既定 70)
- 純粋関数は NiceGUI に依存しない。型ヒントは全関数に付ける。コメントは多くても 3 行
- 画像の書き出し(`[data-chart-content]`の`scrollHeight`)、スクロール位置の維持、名前欄の固定、`当日`の自動スクロール、矢印・今日の線の計算は変えない
- 実装完了時: `uv run pytest -m smoke` → `uv run pytest -n auto` → `uvx ruff check` → `uvx ruff format src test` → `uvx ty check src`(`ty`の既存の 1 件〔`dashboard_view.py`の`days_text`〕は対象外)

## Review Focus

- 保存した`main_split`・`bottom_open_ratio`が壊れている(文字列・負数・範囲外・真偽値)→ 既定または範囲内に収め、起動を妨げない
- 選んだタスクが、削除・絞り込み・折りたたみで見えなくなった → 詳細ではなく集計に戻り、例外を出さない
- タスクが 0 件、または工数・日程のあるタスクが 1 件もない → 集計は`—`などで出し、0 除算にしない
- プレビューに入る・出る → 比率を`config.json`へ保存せず、出たあとに元の比率へ戻る
- 下が畳まれている(100%)状態で選ぶ → `開くときの比率`に開く。開いているときは動かさない。選択を解除しても畳まない

---

### Task 1: 設定値 `main_split`・`bottom_open_ratio`(config.py)

**Files:**
- Modify: `src/projectapp/config.py`(`save_zoom`の後ろに追加)
- Test: `test/test_config.py`

**Interfaces:**
- Produces: `DEFAULT_MAIN_SPLIT = 100`、`MIN_MAIN_SPLIT = 30`、`DEFAULT_OPEN_RATIO = 70`、`MIN_OPEN_RATIO = 50`、`MAX_OPEN_RATIO = 90`、`OPEN_RATIO_STEP = 5`、`parse_main_split(value: object) -> int | None`、`parse_open_ratio(value: object) -> int | None`、`load_main_split(base_dir: Path = BASE_DIR) -> int`、`save_main_split(value: int, base_dir: Path = BASE_DIR) -> None`、`load_open_ratio(base_dir: Path = BASE_DIR) -> int`、`save_open_ratio(value: int, base_dir: Path = BASE_DIR) -> None`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_config.py`の末尾に追加。先頭の import に`from projectapp import config`があることを確認し、なければ足す)

```python
import math

import pytest

from projectapp import config


@pytest.mark.parametrize(
    ("value", "expected"),
    [(100, 100), (70, 70), (30, 30), (10, 30), (150, 100), (66.6, 67), (None, None),
     ("70", None), (True, None), (math.nan, None), (math.inf, None)],
)
def test_parse_main_split_clamps_numbers_and_rejects_others(value, expected) -> None:
    assert config.parse_main_split(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(70, 70), (72, 70), (73, 75), (10, 50), (99, 90), (None, None), ("70", None),
     (True, None), (math.nan, None)],
)
def test_parse_open_ratio_rounds_to_step_and_clamps(value, expected) -> None:
    assert config.parse_open_ratio(value) == expected


def test_main_split_defaults_to_100_and_round_trips(tmp_path) -> None:
    assert config.load_main_split(tmp_path) == config.DEFAULT_MAIN_SPLIT == 100
    config.save_main_split(60, tmp_path)
    assert config.load_main_split(tmp_path) == 60


def test_open_ratio_defaults_to_70_and_round_trips(tmp_path) -> None:
    assert config.load_open_ratio(tmp_path) == config.DEFAULT_OPEN_RATIO == 70
    config.save_open_ratio(55, tmp_path)
    assert config.load_open_ratio(tmp_path) == 55


def test_broken_saved_values_fall_back_to_defaults(tmp_path) -> None:
    config.update_config({"main_split": "abc", "bottom_open_ratio": [1]}, tmp_path)
    assert config.load_main_split(tmp_path) == 100
    assert config.load_open_ratio(tmp_path) == 70
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_config.py -q` → Expected: FAIL(`parse_main_split`がない)

- [ ] **Step 3: 実装**(`config.py`の`save_zoom`の後ろ)

```python
DEFAULT_MAIN_SPLIT = 100  # ガントチャートの割合(%)。100 は下部パネルを畳む
MIN_MAIN_SPLIT = 30
DEFAULT_OPEN_RATIO = 70  # 下部パネルを開くときの、ガントチャートの割合(%)
MIN_OPEN_RATIO, MAX_OPEN_RATIO, OPEN_RATIO_STEP = 50, 90, 5


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if isfinite(value) else None


def parse_main_split(value: object) -> int | None:
    """分割の位置(ガントチャートの割合)の検証。有限の数を丸めて 30〜100 に収める。それ以外は None。"""
    number = _finite_number(value)
    if number is None:
        return None
    return min(max(round(number), MIN_MAIN_SPLIT), 100)


def parse_open_ratio(value: object) -> int | None:
    """開くときの割合の検証。有限の数を 5 刻みに丸めて 50〜90 に収める。それ以外は None。"""
    number = _finite_number(value)
    if number is None:
        return None
    stepped = round(number / OPEN_RATIO_STEP) * OPEN_RATIO_STEP
    return min(max(stepped, MIN_OPEN_RATIO), MAX_OPEN_RATIO)


def load_main_split(base_dir: Path = BASE_DIR) -> int:
    value = parse_main_split(read_config(base_dir).get("main_split"))
    return DEFAULT_MAIN_SPLIT if value is None else value


def save_main_split(value: int, base_dir: Path = BASE_DIR) -> None:
    update_config({"main_split": value}, base_dir)


def load_open_ratio(base_dir: Path = BASE_DIR) -> int:
    value = parse_open_ratio(read_config(base_dir).get("bottom_open_ratio"))
    return DEFAULT_OPEN_RATIO if value is None else value


def save_open_ratio(value: int, base_dir: Path = BASE_DIR) -> None:
    update_config({"bottom_open_ratio": value}, base_dir)
```

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_config.py -q` → Expected: PASS
- [ ] **Step 5: Commit** — `git add src/projectapp/config.py test/test_config.py && git commit -m "feat: 分割の位置と開くときの比率の設定値を足す(要望 111)"`(末尾に Co-Authored-By 行)

---

### Task 2: 集計の純粋関数(bottom_info.py)

**Files:**
- Create: `src/projectapp/bottom_info.py`
- Test: `test/test_bottom_info.py`

**Interfaces:**
- Consumes: `timeline.Schedule`(`start(task)`・`end(task)`)・`timeline.overdue_reasons(task, project, holidays, now, schedule)`・`pace.warning_pace(task, project, holidays, now, schedule)`(`Pace.hint()`)・`dashboard._progress_weight(task)`(`reference.py`も同じく import している)
- Produces:
  - `DetailLine = tuple[str, str]`(見出し, 値)
  - `TaskDetail(title: str, kind: str, lines: list[DetailLine], notes: list[str], others: int)`
  - `PeriodSummary(total: int, counts: dict[Status, int], hours: float, no_effort: int, percent: float | None, overdue: int, warned: int)`
  - `TodayRow(name: str, assignees: str, progress: int | None, end: datetime | None)`
  - `LegendEntry(group: str, label: str, css_class: str, note: str)`
  - `task_detail(task, project, holidays, now, schedule, others=0) -> TaskDetail`
  - `period_summary(tasks, project, holidays, now, schedule, period: tuple[date, date] | None) -> PeriodSummary`
  - `today_plan(tasks, schedule, now) -> list[TodayRow]`
  - `LEGEND: list[LegendEntry]`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_bottom_info.py`)

```python
from datetime import date, datetime

from projectapp.bottom_info import (
    LEGEND, period_summary, task_detail, today_plan,
)
from projectapp.models import (
    Assignee, Member, Project, Section, Status, Task, TaskKind,
)
from projectapp.timeline import Schedule

NOW = datetime(2026, 10, 7, 12)  # 水曜の昼
MON = datetime(2026, 10, 5, 9)


def project_of(*tasks: Task) -> Project:
    return Project(
        "P", base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        sections=[Section("s", list(tasks))],
    )


def env(*tasks: Task):
    project = project_of(*tasks)
    return project, Schedule(project, {})


def planned(name: str, **kw) -> Task:
    kw.setdefault("planned_start", MON)
    kw.setdefault("effort_hours", 13.0)
    return Task(name, **kw)


def test_detail_lists_status_crew_dates_effort_and_progress() -> None:
    task = planned("設計", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)],
                   progress=40, status=Status.RUNNING, deadline=datetime(2026, 10, 9, 18))
    project, schedule = env(task)
    detail = task_detail(task, project, {}, NOW, schedule)
    lines = dict(detail.lines)
    assert detail.title == "設計" and detail.kind == "通常"
    assert lines["状態"] == "実行中"
    assert lines["担当"] == "田中 100%・鈴木 50%"
    assert lines["工数"] == "13.0h" and lines["進捗度"] == "40%"
    assert lines["締切"] == "10/09 18:00"
    assert "開始予定" in lines and "完了予定" in lines


def test_detail_explains_overdue_and_warning() -> None:
    late = planned("遅れ", planned_end=datetime(2026, 10, 6, 12), planned_end_manual=True,
                   assignees=[Assignee("田中", 1.0)])
    project, schedule = env(late)
    detail = task_detail(late, project, {}, NOW, schedule)
    assert any("予定超過" in note for note in detail.notes)


def test_detail_marks_how_many_other_tasks_are_selected() -> None:
    task = planned("a")
    project, schedule = env(task)
    assert task_detail(task, project, {}, NOW, schedule, others=2).others == 2


def test_detail_of_a_task_without_dates_or_crew_uses_dashes() -> None:
    task = Task("空")
    project, schedule = env(task)
    lines = dict(task_detail(task, project, {}, NOW, schedule).lines)
    assert lines["担当"] == "—" and lines["工数"] == "—" and lines["進捗度"] == "—"


def test_checkpoint_detail_shows_only_deadline_and_status() -> None:
    task = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 18))
    project, schedule = env(task)
    detail = task_detail(task, project, {}, NOW, schedule)
    assert detail.kind == "チェックポイント"
    assert [k for k, _ in detail.lines] == ["状態", "締切"]


def test_summary_counts_states_hours_and_weighted_percent() -> None:
    done = planned("終", status=Status.DONE, effort_hours=10.0)
    half = planned("半", status=Status.RUNNING, effort_hours=10.0, progress=50)
    project, schedule = env(done, half)
    s = period_summary([done, half], project, {}, NOW, schedule, None)
    assert s.total == 2 and s.counts[Status.DONE] == 1 and s.counts[Status.RUNNING] == 1
    assert s.hours == 20.0 and s.percent == 75.0


def test_summary_skips_summaries_checkpoints_and_counts_missing_effort() -> None:
    kid = planned("子")
    summary = Task("まとめ", kind=TaskKind.SUMMARY, children=[kid.id])
    mark = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9))
    bare = Task("工数なし", planned_start=MON)
    project, schedule = env(summary, kid, mark, bare)
    s = period_summary([summary, kid, mark, bare], project, {}, NOW, schedule, None)
    assert s.total == 2 and s.no_effort == 1


def test_summary_of_nothing_has_no_percent_and_no_division_error() -> None:
    project, schedule = env()
    s = period_summary([], project, {}, NOW, schedule, None)
    assert s.total == 0 and s.percent is None and s.hours == 0.0


def test_summary_period_keeps_only_tasks_overlapping_it() -> None:
    inside = planned("内", planned_start=MON)
    outside = planned("外", planned_start=datetime(2026, 12, 1, 9))
    project, schedule = env(inside, outside)
    s = period_summary([inside, outside], project, {}, NOW, schedule,
                       (date(2026, 10, 1), date(2026, 10, 31)))
    assert s.total == 1


def test_summary_counts_overdue_and_warned_separately() -> None:
    late = planned("遅", planned_end=datetime(2026, 10, 6, 12), planned_end_manual=True,
                   assignees=[Assignee("田中", 1.0)])
    behind = planned("警告", planned_start=MON, effort_hours=19.5, progress=10,
                     planned_end=datetime(2026, 10, 8, 15, 30), planned_end_manual=True,
                     assignees=[Assignee("田中", 1.0)], status=Status.RUNNING)
    project, schedule = env(late, behind)
    s = period_summary([late, behind], project, {}, NOW, schedule, None)
    assert s.overdue == 1 and s.warned == 1


def test_today_plan_lists_open_normal_tasks_covering_today() -> None:
    now_task = planned("今日", planned_end=datetime(2026, 10, 8, 12), planned_end_manual=True,
                       assignees=[Assignee("田中", 1.0)], progress=30)
    done = planned("終", status=Status.DONE, planned_end=datetime(2026, 10, 8, 12), planned_end_manual=True)
    later = planned("後", planned_start=datetime(2026, 10, 12, 9))
    nodate = Task("日程なし")
    project, schedule = env(now_task, done, later, nodate)
    rows = today_plan([now_task, done, later, nodate], schedule, NOW)
    assert [r.name for r in rows] == ["今日"]
    assert rows[0].assignees == "田中" and rows[0].progress == 30


def test_today_plan_treats_midnight_end_as_the_previous_day() -> None:
    task = planned("昨日まで", planned_end=datetime(2026, 10, 7, 0), planned_end_manual=True)
    project, schedule = env(task)
    assert today_plan([task], schedule, NOW) == []


def test_legend_covers_states_priorities_and_marks() -> None:
    groups = {e.group for e in LEGEND}
    assert groups == {"状態", "優先度", "印"}
    classes = {e.css_class for e in LEGEND}
    assert {"status-not-started", "status-running", "status-paused", "status-done",
            "prio-high", "prio-medium", "prio-low"} <= classes


def test_legend_classes_match_the_chart_constants() -> None:
    from projectapp.gantt import PRIORITY_CLASSES, STATUS_CLASSES
    classes = {e.css_class for e in LEGEND}
    assert set(STATUS_CLASSES.values()) <= classes
    assert set(PRIORITY_CLASSES.values()) <= classes
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_bottom_info.py -q` → Expected: FAIL(モジュールがない)

- [ ] **Step 3: 実装**(`src/projectapp/bottom_info.py`)

```python
"""ガントチャートの下部パネルの内容(要望 95)。NiceGUI に依存しない純粋関数。判定は既存の関数に任せる。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from projectapp.dashboard import _progress_weight
from projectapp.models import Project, Status, Task, TaskKind
from projectapp.pace import warning_pace
from projectapp.timeline import Schedule, overdue_reasons

DetailLine = tuple[str, str]
DASH = "—"
KIND_LABELS = {
    TaskKind.NORMAL: "通常",
    TaskKind.SUMMARY: "まとめ",
    TaskKind.CHECKPOINT: "チェックポイント",
    TaskKind.REFERENCE: "プロジェクト参照",
}


@dataclass(frozen=True)
class TaskDetail:
    title: str
    kind: str
    lines: list[DetailLine]
    notes: list[str] = field(default_factory=list)  # 遅れ・警告の理由
    others: int = 0  # ほかに選んでいる件数


@dataclass(frozen=True)
class PeriodSummary:
    total: int
    counts: dict[Status, int]
    hours: float
    no_effort: int
    percent: float | None  # 工数で重みづけした進捗率。数えるタスクがなければ None
    overdue: int
    warned: int


@dataclass(frozen=True)
class TodayRow:
    name: str
    assignees: str
    progress: int | None
    end: datetime | None


@dataclass(frozen=True)
class LegendEntry:
    group: str
    label: str
    css_class: str  # gantt.py の状態・優先度のクラス名。印は空
    note: str = ""


def _stamp(value: datetime | None) -> str:
    return DASH if value is None else f"{value:%m/%d %H:%M}"


def _crew(task: Task) -> str:
    if not task.assignees:
        return DASH
    return "・".join(f"{a.name} {round(a.allocation * 100)}%" for a in task.assignees)


def task_detail(
    task: Task, project: Project, holidays: dict[date, str], now: datetime,
    schedule: Schedule, others: int = 0,
) -> TaskDetail:
    """選んだタスクの詳細。種別ごとに、持っている項目だけを出す。"""
    kind = KIND_LABELS[task.kind]
    lines: list[DetailLine] = [("状態", task.status.value)]
    if task.kind is TaskKind.CHECKPOINT:
        lines.append(("締切", _stamp(task.deadline)))
        return TaskDetail(task.name, kind, lines, _notes(task, project, holidays, now, schedule), others)
    if task.kind is TaskKind.SUMMARY:
        lines.append(("子", f"{len(task.children)} 件"))
    lines += [
        ("担当", _crew(task)),
        ("開始予定", _stamp(schedule.start(task))),
        ("完了予定", _stamp(schedule.end(task)) + ("(手指定)" if task.planned_end_manual else "")),
        ("締切", _stamp(task.deadline)),
        ("工数", f"{task.effort_hours:.1f}h" if task.effort_hours > 0 else DASH),
        ("進捗度", f"{task.progress}%" if task.progress is not None else DASH),
        ("実績", f"{len(task.actuals)} 区間" if task.actuals else DASH),
        ("リンク", f"{len(task.urls)} 件" if task.urls else DASH),
        ("先行", f"{len(task.predecessors)} 件" if task.predecessors else DASH),
    ]
    return TaskDetail(task.name, kind, lines, _notes(task, project, holidays, now, schedule), others)


def _notes(task: Task, project: Project, holidays: dict[date, str], now: datetime, schedule: Schedule) -> list[str]:
    notes = overdue_reasons(task, project, holidays, now, schedule)
    pace = warning_pace(task, project, holidays, now, schedule)
    if pace is not None:
        notes.append(pace.hint())
    return notes


def _overlaps(task: Task, schedule: Schedule, period: tuple[date, date]) -> bool:
    start, end = schedule.start(task), schedule.end(task)
    if start is None and end is None:
        return False
    first = (start or end).date()
    last = (end or start).date()
    return first <= period[1] and last >= period[0]


def period_summary(
    tasks: list[Task], project: Project, holidays: dict[date, str], now: datetime,
    schedule: Schedule, period: tuple[date, date] | None,
) -> PeriodSummary:
    """見えているタスクの集計。まとめ・チェックポイント・プロジェクト参照は数えない。period があれば、かかるタスクだけ。"""
    counts = {status: 0 for status in Status}
    weighted = hours = total_weight = 0.0
    no_effort = overdue = warned = total = 0
    for task in tasks:
        if task.kind is not TaskKind.NORMAL:
            continue
        if period is not None and not _overlaps(task, schedule, period):
            continue
        total += 1
        counts[task.status] += 1
        if task.effort_hours > 0:
            hours += task.effort_hours
        else:
            no_effort += 1
        weight_and_percent = _progress_weight(task)
        if weight_and_percent is not None:
            weight, percent = weight_and_percent
            weighted += weight * percent
            total_weight += weight
        if overdue_reasons(task, project, holidays, now, schedule):
            overdue += 1
        elif warning_pace(task, project, holidays, now, schedule) is not None:
            warned += 1
    percent = weighted / total_weight if total_weight > 0 else None
    return PeriodSummary(total, counts, hours, no_effort, percent, overdue, warned)


def today_plan(tasks: list[Task], schedule: Schedule, now: datetime) -> list[TodayRow]:
    """今日が日程にかかる、未終了の通常タスク。完了予定が 0 時ちょうどなら前日までとする。"""
    today = now.date()
    rows: list[TodayRow] = []
    for task in tasks:
        if task.kind is not TaskKind.NORMAL or task.status is Status.DONE:
            continue
        start, end = schedule.start(task), schedule.end(task)
        if start is None or end is None:
            continue
        last = (end - timedelta(microseconds=1)).date() if end.time() == time(0) else end.date()
        if start.date() <= today <= last:
            rows.append(TodayRow(task.name, "・".join(task.assignee_names) or DASH, task.progress, end))
    return rows


LEGEND = [
    LegendEntry("状態", "未着手", "status-not-started", "棒の色"),
    LegendEntry("状態", "実行中", "status-running", "棒の色"),
    LegendEntry("状態", "一時停止", "status-paused", "棒の色"),
    LegendEntry("状態", "終了", "status-done", "棒の色"),
    LegendEntry("優先度", "高", "prio-high", "名前欄の背景"),
    LegendEntry("優先度", "中", "prio-medium", "名前欄の背景"),
    LegendEntry("優先度", "低", "prio-low", "名前欄の背景"),
    LegendEntry("印", "赤い行", "", "遅れ(完了予定か締切を過ぎた)"),
    LegendEntry("印", "黄色い行", "", "警告(完了予定を過ぎそう)"),
    LegendEntry("印", "縞", "", "割り当て超過(同じ人の割り当てが 100% 超)"),
    LegendEntry("印", "◆", "", "締切(大きい◆はチェックポイント)"),
    LegendEntry("印", "赤い縦線", "", "今日"),
]
```

注: `Assignee`の割り当て率の属性は`allocation`(確認済み)。`overdue_reasons`は`list[str]`を返す(確認済み)。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_bottom_info.py -q` → Expected: PASS(失敗した属性名・日付の期待は、テストと実装の両方を実コードに合わせて直す)
- [ ] **Step 5: Commit** — `git add src/projectapp/bottom_info.py test/test_bottom_info.py && git commit -m "feat: 下部パネルの詳細・集計・今日の予定・凡例の純粋関数を足す(要望 95)"`

---

### Task 3: 下部パネルの描画(bottom_panel.py)

**Files:**
- Create: `src/projectapp/bottom_panel.py`
- Test: `test/test_bottom_panel.py`

**Interfaces:**
- Consumes: Task 2 の`TaskDetail`・`PeriodSummary`・`TodayRow`・`LEGEND`
- Produces: `PanelContent(detail: TaskDetail | None, summary: PeriodSummary, today: list[TodayRow])`、`BottomPanel`(`build() -> None`・`update(content: PanelContent) -> None`・`tab: str`)。マーカー: `bottom-panel`(外枠)、`bottom-detail`、`bottom-summary`、`bottom-tabs`、`bottom-tab-today`、`bottom-tab-legend`、`bottom-today`、`bottom-legend`、`bottom-others`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_bottom_panel.py`)

```python
from datetime import datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.bottom_info import PeriodSummary, TaskDetail, TodayRow
from projectapp.bottom_panel import BottomPanel, PanelContent
from projectapp.models import Status

SUMMARY = PeriodSummary(3, {s: (1 if s is Status.RUNNING else 0) for s in Status}, 26.0, 1, 40.0, 1, 0)
DETAIL = TaskDetail("設計", "通常", [("状態", "実行中"), ("担当", "田中 100%")], ["予定超過(完了予定 10/06 12:00 を過ぎています)"], 2)
TODAY = [TodayRow("実装", "田中", 30, datetime(2026, 10, 8, 12))]


def mount() -> list[BottomPanel]:
    panels: list[BottomPanel] = []

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel()
        panel.build()
        panel.update(PanelContent(None, SUMMARY, TODAY))
        panels.append(panel)

    return panels


async def test_without_a_selection_it_shows_the_summary_and_the_today_tab(user: User) -> None:
    mount()
    await user.open("/")
    await user.should_see(marker="bottom-summary")
    await user.should_see(marker="bottom-today")
    await user.should_not_see(marker="bottom-detail")


async def test_the_legend_tab_replaces_the_today_tab(user: User) -> None:
    mount()
    await user.open("/")
    user.find(marker="bottom-tab-legend").click()
    await user.should_see(marker="bottom-legend")
    await user.should_not_see(marker="bottom-today")


async def test_a_selection_shows_only_the_detail_and_the_other_count(user: User) -> None:
    panels = mount()
    await user.open("/")
    panels[0].update(PanelContent(DETAIL, SUMMARY, TODAY))
    await user.should_see(marker="bottom-detail")
    await user.should_see(marker="bottom-others")
    await user.should_not_see(marker="bottom-summary")
    await user.should_see("予定超過")


async def test_clearing_the_selection_returns_to_the_summary_and_keeps_the_tab(user: User) -> None:
    panels = mount()
    await user.open("/")
    user.find(marker="bottom-tab-legend").click()
    panels[0].update(PanelContent(DETAIL, SUMMARY, TODAY))
    panels[0].update(PanelContent(None, SUMMARY, TODAY))
    await user.should_see(marker="bottom-summary")
    await user.should_see(marker="bottom-legend")


async def test_an_empty_summary_shows_dashes(user: User) -> None:
    panels = mount()
    await user.open("/")
    empty = PeriodSummary(0, {s: 0 for s in Status}, 0.0, 0, None, 0, 0)
    panels[0].update(PanelContent(None, empty, []))
    await user.should_see(marker="bottom-summary")
    await user.should_see("—")
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_bottom_panel.py -q` → Expected: FAIL(モジュールがない)

- [ ] **Step 3: 実装**(`src/projectapp/bottom_panel.py`)

```python
"""ガントチャートの下部パネルの描画(要望 95)。内容は`PanelContent`で受け取り、計算はしない。"""

from dataclasses import dataclass

from nicegui import ui

from projectapp.bottom_info import DASH, LEGEND, PeriodSummary, TaskDetail, TodayRow
from projectapp.models import Status

TABS = {"today": "今日の予定", "legend": "凡例"}


@dataclass
class PanelContent:
    detail: TaskDetail | None
    summary: PeriodSummary
    today: list[TodayRow]


class BottomPanel:
    def __init__(self) -> None:
        self.content: PanelContent | None = None
        self.tab = "today"  # 保存しない。開くたびに今日の予定

    def build(self) -> None:
        with ui.column().classes("w-full h-full gap-1 p-2").style("overflow: auto").mark("bottom-panel"):
            self.body()

    def update(self, content: PanelContent) -> None:
        self.content = content
        self.body.refresh()

    @ui.refreshable_method
    def body(self) -> None:
        if self.content is None:
            return
        if self.content.detail is not None:
            self.show_detail(self.content.detail)
            return
        with ui.row().classes("w-full items-start gap-6 no-wrap"):
            self.show_summary(self.content.summary)
            with ui.column().classes("grow gap-1"):
                self.show_tabs()

    def show_detail(self, detail: TaskDetail) -> None:
        with ui.column().classes("w-full gap-1").mark("bottom-detail"):
            ui.label(f"{detail.title}({detail.kind})").classes("text-subtitle2 text-bold")
            if detail.others:
                ui.label(f"ほか {detail.others} 件を選択中").classes("text-caption text-grey").mark("bottom-others")
            with ui.grid(columns="auto 1fr").classes("gap-x-4 gap-y-0"):
                for label, value in detail.lines:
                    ui.label(label).classes("text-caption text-grey")
                    ui.label(value)
            for note in detail.notes:
                ui.label(note).classes("text-caption text-negative")

    def show_summary(self, s: PeriodSummary) -> None:
        with ui.column().classes("gap-0 shrink-0").mark("bottom-summary"):
            ui.label("表示中のタスクの集計").classes("text-subtitle2 text-bold")
            percent = DASH if s.percent is None else f"{s.percent:.0f}%"
            ui.label(f"{s.total} 件 / 進捗 {percent}")
            ui.label("工数 " + (f"{s.hours:.1f}h" if s.hours > 0 else DASH) + (f"(工数未設定 {s.no_effort} 件)" if s.no_effort else ""))
            ui.label("・".join(f"{status.value} {s.counts[status]}" for status in Status))
            ui.label(f"遅れ {s.overdue} 件・警告 {s.warned} 件")

    def show_tabs(self) -> None:
        with ui.tabs(value=self.tab, on_change=self.set_tab).props("dense align=left").mark("bottom-tabs"):
            for key, label in TABS.items():
                ui.tab(key, label=label).mark(f"bottom-tab-{key}")
        if self.tab == "today":
            self.show_today()
        else:
            self.show_legend()

    def set_tab(self, event) -> None:
        if event.value != self.tab:
            self.tab = event.value
            self.body.refresh()

    def show_today(self) -> None:
        rows = self.content.today if self.content else []
        with ui.column().classes("w-full gap-0").mark("bottom-today"):
            if not rows:
                ui.label(DASH).classes("text-grey")
            for row in rows:
                progress = "" if row.progress is None else f" {row.progress}%"
                end = "" if row.end is None else f" 〜{row.end:%m/%d %H:%M}"
                ui.label(f"{row.name}({row.assignees}){progress}{end}")

    def show_legend(self) -> None:
        with ui.column().classes("w-full gap-0").mark("bottom-legend"):
            group = ""
            for entry in LEGEND:
                if entry.group != group:
                    group = entry.group
                    ui.label(group).classes("text-caption text-grey")
                with ui.row().classes("items-center gap-2"):
                    chip = ui.label(entry.label).classes("px-2")
                    if entry.css_class:
                        chip.classes(entry.css_class).style("background: var(--pbg, var(--scolor)); color: #fff" if entry.group == "状態" else "background: var(--pbg)")
                    ui.label(entry.note).classes("text-caption text-grey")
```

注: 状態・優先度のチップの色は、`gantt.py`が`ui.add_css`で登録済みのクラス(`status-*`は`--scolor`、`prio-*`は`--pbg`)に任せる。実機で見た目を確かめ、足りなければ`gantt.STATUS_CSS`・`PRIORITY_CSS`のクラス定義に合わせて`style`を直す。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_bottom_panel.py -q` → Expected: PASS
- [ ] **Step 5: Commit** — `git add src/projectapp/bottom_panel.py test/test_bottom_panel.py && git commit -m "feat: ガントチャートの下部パネルの描画を足す(要望 95)"`

---

### Task 4: 縦の分割と選択への連動(gantt.py)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions`の末尾に`set_main_split`を足す。`__init__`の引数・属性、`build`の枠、`set_visible`、`set_options`、`clicked_task`、`sync_bulk`、`render`の末尾)
- Test: `test/test_bottom_split.py`

**Interfaces:**
- Consumes: Task 1(値)・Task 2・Task 3
- Produces: `GanttChart(main_split: int = 100, open_ratio: int = 70, ...)`、`chart.splitter`、`chart.bottom`、`chart.open_bottom() -> None`、`chart.bottom_open -> bool`、`GanttActions.set_main_split: Callable[[int], object]`(既定は何もしない)、定数`CHART_SPLIT_HEIGHT`(`= CHART_MAX_HEIGHT`)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_bottom_split.py`。`mount_chart`は`test/test_gantt.py`のもの。`GanttChart`に`main_split`・`open_ratio`を渡すテストは、同じ作りの`mount`をこのファイルに書く)

```python
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import GanttActions, GanttChart, ViewOptions
from projectapp.models import Project, Section, Task
from test_gantt import Recorder, mount_chart

BASE = date(2026, 10, 5)


def project() -> Project:
    return Project("demo", base_date=BASE,
                   tasks=[Task("a", id="a", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5),
                          Task("b", id="b")])


def mount(main_split: int = 100, open_ratio: int = 70):
    charts: list[GanttChart] = []
    recorder = Recorder()
    saved: list[int] = []
    actions = recorder.actions
    actions.set_main_split = saved.append

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project(), {}, actions, now=lambda: datetime(2026, 10, 7, 12),
                           main_split=main_split, open_ratio=open_ratio)
        charts.append(chart)
        chart.build()

    return charts, saved


async def test_the_first_start_folds_the_bottom_panel(user: User) -> None:
    charts, _ = mount()
    await user.open("/")
    assert charts[0].splitter.value == 100
    assert not charts[0].bottom_open


async def test_a_saved_split_is_restored(user: User) -> None:
    charts, _ = mount(main_split=60)
    await user.open("/")
    assert charts[0].splitter.value == 60 and charts[0].bottom_open
    await user.should_see(marker="bottom-summary")


async def test_selecting_a_task_opens_a_folded_panel_at_the_open_ratio(user: User) -> None:
    charts, _ = mount(open_ratio=75)
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    assert charts[0].splitter.value == 75
    await user.should_see(marker="bottom-detail")


async def test_selecting_does_not_move_an_open_panel(user: User) -> None:
    charts, _ = mount(main_split=55)
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    assert charts[0].splitter.value == 55


async def test_clearing_the_selection_keeps_the_panel_open_and_shows_the_summary(user: User) -> None:
    charts, _ = mount()
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    charts[0].clear_selection()
    assert charts[0].splitter.value == 70
    await user.should_see(marker="bottom-summary")


async def test_moving_the_splitter_reports_the_new_value(user: User) -> None:
    charts, saved = mount()
    await user.open("/")
    charts[0].splitter.set_value(65)
    assert saved[-1] == 65


async def test_a_selected_task_that_gets_filtered_out_falls_back_to_the_summary(user: User) -> None:
    from projectapp.filtering import TaskFilter
    charts, _ = mount()
    await user.open("/")
    charts[0].clicked_task("a", {"ctrl": True})
    charts[0].set_filter(TaskFilter(query="zzz"))
    await user.should_see(marker="bottom-summary")


async def test_the_preview_hides_the_panel_and_does_not_report_the_split(user: User) -> None:
    charts, saved = mount(main_split=60)
    await user.open("/")
    saved.clear()
    charts[0].set_options(ViewOptions(read_only=True))
    assert charts[0].splitter.value == 100 and saved == []
    charts[0].set_options(ViewOptions())
    assert charts[0].splitter.value == 60 and saved == []
```

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_bottom_split.py -q` → Expected: FAIL(`main_split`引数がない)

- [ ] **Step 3: 実装**(`gantt.py`)

(a) import と定数:

```python
from projectapp.bottom_info import period_summary, task_detail, today_plan
from projectapp.bottom_panel import BottomPanel, PanelContent
from projectapp.config import DEFAULT_MAIN_SPLIT, DEFAULT_OPEN_RATIO, MIN_MAIN_SPLIT

CHART_SPLIT_HEIGHT = CHART_MAX_HEIGHT  # 分割の全体の高さ。畳んだときの見た目は、これまでの枠の上限と同じ
SPLIT_LOCK_CSS = ".split-locked .q-splitter__separator, .split-locked .q-splitter__after { display: none; }"
```

(b) `GanttActions`の末尾(既定値つきのフィールドは最後):

```python
    set_main_split: Callable[[int], object] = lambda value: None  # 分割の位置を変えたとき(保存は呼び出し側)
```

(c) `__init__`に引数`main_split: int = DEFAULT_MAIN_SPLIT, open_ratio: int = DEFAULT_OPEN_RATIO`を足し、属性を作る:

```python
        self.main_split = main_split  # 畳んでいないときの、ガントチャートの割合(%)
        self.open_ratio = open_ratio
        self.splitter: ui.splitter | None = None
        self.split_box: ui.element | None = None
        self.bottom = BottomPanel()
        self.split_before_preview: int | None = None
```

(d) `build`の末尾(`scroll_style`から`self.render()`まで)を、分割に入れ替える:

```python
        ui.add_css(SPLIT_LOCK_CSS)
        box = ui.element("div").classes("w-full").style(f"height: {CHART_SPLIT_HEIGHT}")
        self.split_box = box
        with box:
            self.splitter = ui.splitter(
                horizontal=True,
                value=self.main_split,
                limits=(MIN_MAIN_SPLIT, 100),
                on_change=self.split_changed,
            ).classes("w-full h-full").mark("bottom-split")
            with self.splitter.before:
                scroll_style = f"overflow: auto; height: 100%; padding-bottom: {SCROLLBAR_ROOM_PX}px"
                scroll = ui.element("div").classes("w-full").style(scroll_style)
                self.scroll_box = scroll
                scroll.on("scroll", js_handler=TRACK_SCROLL_JS)
                with scroll.props("data-chart-scroll").mark("chart-scroll"):
                    self.render()
            with self.splitter.after:
                self.bottom.build()
        self.refresh_bottom()
```

(`render()`の中から`refresh_bottom`を呼ぶので、`self.bottom.build()`の前に呼ばれても`content is None`で何も出ない。`build`の最後の`refresh_bottom()`で初回の内容を入れる。)

(e) 分割まわりのメソッド:

```python
    @property
    def bottom_open(self) -> bool:
        return self.splitter is not None and self.splitter.value < 100

    def split_changed(self, event) -> None:
        """境界を動かしたとき。プレビュー中は、一時的に 100% にしているだけなので、保存しない。"""
        if self.options.read_only:
            return
        self.main_split = int(event.value)
        self.actions.set_main_split(self.main_split)

    def open_bottom(self) -> None:
        """畳まれているときだけ、開くときの比率で開く。開いているときは動かさない。"""
        if self.splitter is not None and not self.options.read_only and not self.bottom_open:
            self.splitter.set_value(self.open_ratio)

    def sync_split_mode(self) -> None:
        """プレビューでは分割を畳んで境界を隠し、戻ると元の位置へ戻す。"""
        if self.splitter is None or self.split_box is None:
            return
        if self.options.read_only:
            if self.split_before_preview is None:
                self.split_before_preview = int(self.splitter.value)
            self.splitter.set_value(100)
            self.splitter.props("disable")
            self.split_box.classes("split-locked")
        elif self.split_before_preview is not None:
            self.split_box.classes(remove="split-locked")
            self.splitter.props(remove="disable")
            restore, self.split_before_preview = self.split_before_preview, None
            self.splitter.set_value(restore)

    def bottom_content(self) -> PanelContent:
        now = self.now()
        tasks = [self.tasks_by_id[i] for i in self.visible_task_ids() if i in self.tasks_by_id]
        selected = [i for i in self.selected_ids() if i in self.tasks_by_id]
        detail = None
        if selected:
            anchor = self.bulk.anchor if self.bulk.anchor in selected else selected[-1]
            detail = task_detail(self.tasks_by_id[anchor], self.project, self.holidays,
                                 now, self.schedule, len(selected) - 1)
        return PanelContent(
            detail,
            period_summary(tasks, self.project, self.holidays, now, self.schedule, self.period),
            today_plan(tasks, self.schedule, now),
        )

    def refresh_bottom(self) -> None:
        if self.splitter is not None and not self.options.read_only:
            self.bottom.update(self.bottom_content())
```

(f) 呼び出し: `set_options`の末尾で`self.sync_split_mode()`、`render()`の末尾と`sync_bulk()`の末尾で`self.refresh_bottom()`、`clicked_task`で選択を変えたあと(`sync_bulk`を呼ぶ箇所の直前)に`if self.bulk.ids: self.open_bottom()`。`set_visible`は`self.split_box`も表示・非表示にする:

```python
        if self.split_box is not None:
            self.split_box.set_visibility(visible)
```

注: `clicked_task`・`set_options`・`render`・`sync_bulk`・`set_visible`の既存の本文は、`grep -n`で位置を確かめて、上の追加だけを入れる(既存の処理は変えない)。`self.tasks_by_id`・`self.holidays`・`self.schedule`は既存の属性。`render`が`schedule`を作り直す箇所のあとで`refresh_bottom`を呼ぶこと。

- [ ] **Step 4: 通過を確認** — Run: `uv run pytest test/test_bottom_split.py test/test_gantt.py test/test_bulk_gantt.py test/test_bulk_view.py -q` → Expected: PASS。既存テストが`max-height`や`scroll_box`の高さを見ていて落ちたら、`CHART_SPLIT_HEIGHT`と分割の枠に合わせて直す(挙動は同じ)。
- [ ] **Step 5: smoke** — Run: `uv run pytest -m smoke -q` → Expected: PASS
- [ ] **Step 6: Commit** — `git add src/projectapp/gantt.py test/test_bottom_split.py && git commit -m "feat: ガントチャートを縦に分け、下部パネルを選択に連動させる(要望 111・95)"`

---

### Task 5: 保存と復元・設定アイコン・全体の設定ダイアログ(views.py ほか)

**Files:**
- Create: `src/projectapp/global_settings_dialog.py`
- Modify: `src/projectapp/views.py`(import、`__init__`の設定読込、`GanttChart`の生成、`GanttActions`、`build`、`header`)
- Test: `test/test_global_settings.py`

**Interfaces:**
- Consumes: Task 1 の`load_*`・`save_*`、Task 4 の`GanttChart.open_ratio`・`splitter`・`bottom_open`
- Produces: `open_global_settings_dialog(initial_ratio: int, on_preview: Callable[[int], object], on_apply: Callable[[int], bool], on_cancel: Callable[[], object]) -> None`。マーカー: `global-settings-ratio`(スライダー)・`global-settings-cancel`・`global-settings-apply`、ヘッダーのボタン`open-global-settings`。`MainView.open_global_settings() -> None`・`set_main_split(value: int) -> None`・`flush_main_split() -> None`・`apply_open_ratio(value: int) -> bool`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_global_settings.py`。`MainView`の作り方は`test/test_views.py`の先頭の`open_view`相当の補助を使う〔`grep -n "def open_view\|def make_view" test/test_views.py`で確認し、同じ引数で呼ぶ〕)

```python
import pytest
from nicegui.testing import User

from projectapp import config
# from test_views import <MainView を作る補助>  # 実際の補助名に合わせる


async def test_the_header_has_a_settings_button_left_of_the_theme_button(user: User, tmp_path) -> None:
    view = await open_view(user, tmp_path)  # 補助名は実コードに合わせる
    await user.should_see(marker="open-global-settings")
    html = user.find(marker="header-box").elements.pop()
    markers = [c.mark_text for c in html.descendants() if getattr(c, "_markers", None)]  # 順序の確認は実際の API に合わせる
    assert markers.index("open-global-settings") < markers.index("menu-theme")


async def test_the_dialog_slider_previews_applies_and_saves(user: User, tmp_path) -> None:
    view = await open_view(user, tmp_path)
    view.open_global_settings()
    slider = user.find(marker="global-settings-ratio").elements.pop()
    slider.set_value(80)
    assert view.gantt.open_ratio == 80  # すぐ反映
    user.find(marker="global-settings-apply").click()
    assert config.load_open_ratio(tmp_path) == 80


async def test_cancelling_the_dialog_restores_the_open_ratio(user: User, tmp_path) -> None:
    view = await open_view(user, tmp_path)
    view.open_global_settings()
    user.find(marker="global-settings-ratio").elements.pop().set_value(85)
    user.find(marker="global-settings-cancel").click()
    assert view.gantt.open_ratio == 70
    assert config.load_open_ratio(tmp_path) == 70


async def test_an_open_panel_follows_the_slider_preview_and_cancel_restores_it(user: User, tmp_path) -> None:
    config.save_main_split(70, tmp_path)
    view = await open_view(user, tmp_path)
    view.open_global_settings()
    user.find(marker="global-settings-ratio").elements.pop().set_value(85)
    assert view.gantt.splitter.value == 85
    user.find(marker="global-settings-cancel").click()
    assert view.gantt.splitter.value == 70


async def test_the_split_is_restored_at_start_and_saved_on_flush(user: User, tmp_path) -> None:
    config.save_main_split(60, tmp_path)
    view = await open_view(user, tmp_path)
    assert view.gantt.splitter.value == 60
    view.set_main_split(45)
    view.flush_main_split()
    assert config.load_main_split(tmp_path) == 45


async def test_flush_with_nothing_pending_writes_nothing(user: User, tmp_path) -> None:
    view = await open_view(user, tmp_path)
    view.flush_main_split()
    assert "main_split" not in config.read_config(tmp_path)
```

(`open_view`は`test/test_views.py`の補助に合わせる。ヘッダーのボタンの左右の確認は、ヘッダーの子要素の順序を取れる API〔`header_box.default_slot.children`のマーカー〕に合わせて書き直してよい。)

- [ ] **Step 2: 失敗を確認** — Run: `uv run pytest test/test_global_settings.py -q` → Expected: FAIL

- [ ] **Step 3: ダイアログを実装**(`src/projectapp/global_settings_dialog.py`。`theme_dialog.open_color_dialog`と同じ作り)

```python
"""全体の設定のダイアログ(全プロジェクト共通の値)。今は下部パネルを開くときの比率だけ。"""

from collections.abc import Callable

from nicegui import ui

from projectapp.config import MAX_OPEN_RATIO, MIN_OPEN_RATIO, OPEN_RATIO_STEP
from projectapp.forms import disposable


def open_global_settings_dialog(
    initial_ratio: int,
    on_preview: Callable[[int], object],
    on_apply: Callable[[int], bool],
    on_cancel: Callable[[], object],
) -> None:
    """動かすとすぐ反映し(プレビュー)、`適用`で保存。適用せずに閉じたら`on_cancel`で元に戻す。"""
    applied = False
    current = initial_ratio
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[26rem] max-w-full"):
        ui.label("全体の設定").classes("text-h6")
        ui.label("下部パネルを開くときの、ガントチャートの割合").classes("text-caption")

        def change(event) -> None:
            nonlocal current
            current = int(event.value)
            on_preview(current)

        ui.slider(min=MIN_OPEN_RATIO, max=MAX_OPEN_RATIO, step=OPEN_RATIO_STEP,
                  value=initial_ratio, on_change=change).props("label-always").mark("global-settings-ratio")
        ui.label("タスクを選んで下部パネルが畳まれているとき、この割合で開きます(下は残り)").classes("text-caption text-grey")

        def apply() -> None:
            nonlocal applied
            if on_apply(current):
                applied = True
                dialog.close()

        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=dialog.close).props("flat no-caps").mark("global-settings-cancel")
            ui.button("適用", on_click=apply).props("no-caps").mark("global-settings-apply")
        dialog.on_value_change(lambda e: None if e.value or applied else on_cancel())
    dialog.open()
```

`disposable`は`forms.py:110`の定義。`forms.py`が`global_settings_dialog`を import しないこと(循環しない)を確かめる。

- [ ] **Step 4: views.py を実装**
  - import: `from nicegui import app, ui`(`app`がなければ足す)、`from projectapp.config import load_main_split, load_open_ratio, save_main_split, save_open_ratio`、`from projectapp.global_settings_dialog import open_global_settings_dialog as show_global_settings_dialog`
  - `__init__`(`self.today_color = ...`の近く): `self.main_split = load_main_split(self.base_dir)`、`self.open_ratio = load_open_ratio(self.base_dir)`、`self.pending_split: int | None = None`、`self.split_timer: ui.timer | None = None`
  - `GanttChart(...)`の生成に`main_split=self.main_split, open_ratio=self.open_ratio`を足し、`GanttActions(...)`に`set_main_split=self.set_main_split`を足す
  - メソッド:

```python
    def set_main_split(self, value: int) -> None:
        """分割の位置が変わった。ドラッグ中に書き続けないよう、止まってから保存する。"""
        self.pending_split = value
        if self.split_timer is not None:
            self.split_timer.cancel()
        self.split_timer = ui.timer(0.6, self.flush_main_split, once=True)

    def flush_main_split(self) -> None:
        """保存待ちの分割の位置を書く(アプリの終了時にも呼ぶ)。保存できなくても画面はそのまま。"""
        value, self.pending_split = self.pending_split, None
        if value is None:
            return
        try:
            save_main_split(value, self.base_dir)
        except OSError:
            ui.notify("分割の位置を保存できませんでした", type="warning")

    def open_global_settings(self) -> None:
        """全体の設定のダイアログ。動かすとすぐ反映し、キャンセルで元の比率・分割の位置に戻す。"""
        before_ratio = self.open_ratio
        before_split = int(self.gantt.splitter.value) if self.gantt.splitter else 100

        def preview(value: int) -> None:
            self.gantt.open_ratio = value
            if self.gantt.bottom_open and self.gantt.splitter is not None:
                self.gantt.splitter.set_value(value)

        def cancel() -> None:
            self.gantt.open_ratio = before_ratio
            if self.gantt.splitter is not None:
                self.gantt.splitter.set_value(before_split)

        show_global_settings_dialog(self.open_ratio, preview, self.apply_open_ratio, cancel)

    def apply_open_ratio(self, value: int) -> bool:
        """開くときの比率を保存する。失敗したら通知して False(画面は閉じない)。"""
        try:
            save_open_ratio(value, self.base_dir)
        except OSError:
            ui.notify("全体の設定を保存できませんでした", type="warning")
            return False
        self.open_ratio = value
        self.gantt.open_ratio = value
        return True
```

  - `build`の先頭近くに`app.on_shutdown(self.flush_main_split)`
  - `header`の右側で、`theme_menu()`の直前に:

```python
            ui.button(icon="settings", color=None, on_click=self.open_global_settings).props(
                "flat round dense"
            ).tooltip("全体の設定").mark("open-global-settings")
```

  - `header`の docstring の「テーマ」の前に「設定」を足す

- [ ] **Step 5: 通過を確認** — Run: `uv run pytest test/test_global_settings.py test/test_views.py -q` → Expected: PASS(ヘッダーの子要素の数・順序を見る既存テストがあれば、設定ボタンの分を直す)
- [ ] **Step 6: Commit** — `git add src/projectapp/global_settings_dialog.py src/projectapp/views.py test/test_global_settings.py && git commit -m "feat: 分割の位置の保存と復元、ヘッダーの設定アイコンと全体の設定ダイアログを足す(要望 111)"`

---

### Task 6: 仕様・文書の更新と最終確認

**Files:**
- Modify: `.claude/spec/gantt.md`(`下部パネル`の項目を足す)、`.claude/spec/header-git.md`(ヘッダー右側に設定アイコンを足す)、`.claude/spec/project-files.md`(`config.json`のキー)、`.claude/spec/theme.md`(`全体の設定`への言及)、`docs/development.md`(モジュール表に`bottom_info.py`・`bottom_panel.py`・`global_settings_dialog.py`)、`docs/request-history.md`・`docs/requests.md`(要望 111・95 を完了に)、`docs/superpowers/README.md`(索引に 1 行)、`docs/superpowers/specs/2026-11-01-bottom-panel-design.md`(状態を完了に)、`README.md`(「できること」に一言)
- Test: 全テスト

- [ ] **Step 1: 仕様ファイルを更新**
  - `gantt.md`: 「メインパネルは縦に分かれ、上がガントチャート、下が情報パネル」「初回は 100% で畳む。タスクを選ぶと、畳まれていれば`開くときの比率`(既定 70%)で開く。開いているときは動かさず、解除しても畳まない」「選択中は詳細(複数選択は最後に選んだ行。`ほか n 件`)、未選択は集計と、`今日の予定`/`凡例`のタブ」「集計の対象と除外」「プレビュー・ダッシュボードでは出さない」を、設計書の「決めたこと」「内容」から転記する
  - `header-git.md`: ヘッダー右側の並び(…・格納フォルダ・設定・テーマ)と、`全体の設定`ダイアログ(下部パネルを開くときの比率のスライダー 50〜90%・5% 刻み)
  - `project-files.md`: `config.json`に`main_split`(アプリ終了時とドラッグ後に保存)・`bottom_open_ratio`
  - `docs/development.md`: 3 モジュールの行
  - 要望 111・95 の状態: 完了(PR 番号は PR 作成後に入れる)
- [ ] **Step 2: 全体の確認** — Run: `uv run pytest -n auto -q`、`uvx ruff check`、`uvx ruff format src test`、`uvx ruff format --check src test`、`uvx ty check src` → Expected: テストが全件通り、ruff が 0 件、ty は既存の 1 件だけ
- [ ] **Step 3: Commit** — `git add -A && git commit -m "docs: 下部パネルと縦の分割を仕様・文書に反映する(要望 111・95)"`
- [ ] **Step 4: 実機確認の依頼** — `uv run projectapp`で起動し、次を利用者に確認してもらう: 初回が 100%、タスクの`Cmd`クリックで 70/30 に開く、境界のドラッグ、アプリを閉じて開き直すと位置が復元される、設定アイコンのスライダー、プレビューとダッシュボードで出ない、画像の書き出し、`当日`のスクロール、画面の拡大・縮小。PR の作成とマージは、利用者の指示を待つ
