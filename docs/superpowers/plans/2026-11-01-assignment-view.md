# 下部パネルの割り当て表示 実装計画(要望 116)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下部パネルに、担当者ごとの割り当て率を日・週・月の刻みで表にした`割り当て`ビューを足し、`Ctrl/Cmd + Alt/Option`の同時押し(とボタン)で入れ替えられるようにする。

**Architecture:** 表の計算は`bottom_info.py`の純粋関数(`assignment_table`)。負荷の基準は`dashboard._day_peak`(ガントチャートの縞と同じ)、列は`timeline.build_columns`の`Column`をそのまま使う。`BottomPanel`が`view`(`info`/`assignment`)を持ち、`assignment`の間は選択が変わっても内容を変えない。キーは既存の`shortcuts.py`の表に`alt`の項目を足し、`views.on_key`で振り分ける。

**Tech Stack:** Python 3.13、NiceGUI(`ui.keyboard`、`user`フィクスチャのテスト)、ruff・ty(`uvx`)

**Spec:** [`docs/superpowers/specs/2026-11-01-assignment-view-design.md`](../specs/2026-11-01-assignment-view-design.md)

## Global Constraints

- 言語は日本語(コメント・UI の文言・コミットメッセージ)。Python 3.13 以上
- ファイル形式(`version`)は変えない。ビューの状態は保存しない
- 新しい判定を作らない: 負荷は`dashboard._day_peak`、超過は`timeline.OVERLOAD_EPSILON`、稼働日は`timeline.is_workday`と`workdays.work_day_map`
- 実装完了時: smoke(`uv run pytest -m smoke`)→ 全テスト(`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(`dashboard_view.py`の`days_text`の指摘 1 件は既存)。コミットの前に`ruff check`を通す
- コミットメッセージの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- 最終レビューのサブエージェントは`model: "sonnet"`を必ず指定(opus・fable は使わない)
- マージは利用者の指示を待つ(PR を作って止まる)

## Review Focus

1. 週次・月次で、平均は 100% 以下でも、期間のどこかに 100% 超の日があれば`over`になる(Task 1 でテスト)
2. 稼働日の上書き(土曜に出勤)のあるメンバーは、土曜の列が`closed`にならない(Task 1)
3. 割り当てのあるメンバーがいない・列がない表で、落ちずに「割り当てのある担当者はいません」を出す(Task 2)
4. `Ctrl`だけ・`Alt`だけを押しても切り替わらない。押しっぱなしの連続入力(`repeat`)も無視(Task 4)
5. プレビュー(`read_only`)・ダッシュボードでは、切り替えても落ちず、何も起きない(Task 3・4)

## ファイル構成

| ファイル | 変更 |
|---|---|
| `src/projectapp/bottom_info.py` | `AssignmentCell`・`AssignmentRow`・`AssignmentTable`・`assignment_table`を足す |
| `src/projectapp/bottom_panel.py` | `PanelContent.assignment`、`BottomPanel.view`・`toggle_view`・`show_assignment`、切り替えボタン |
| `src/projectapp/gantt.py` | `toggle_assignment`、`bottom_content`に表を足す |
| `src/projectapp/shortcuts.py` | `alt`の項目と表記 |
| `src/projectapp/views.py` | `on_key`の振り分けと`toggle_assignment_view` |
| `test/test_bottom_info.py`・`test/test_bottom_panel.py`・`test/test_assignment_view.py`(新)・`test/test_shortcuts.py`・`test/test_views.py` | テスト |
| `.claude/spec/gantt.md`・`README.md`・設計書・`docs/requests.md`・`docs/request-history.md`・`docs/superpowers/README.md` | 文書 |

---

### Task 1: 割り当て表の純粋関数

**Files:**
- Modify: `src/projectapp/bottom_info.py`
- Test: `test/test_bottom_info.py`

**Interfaces:**
- Consumes: `timeline.Column(start: date, end: date〔終端を含まない〕, label: str)`、`timeline.counted_pieces`、`timeline.is_workday`、`timeline.OVERLOAD_EPSILON`、`dashboard._day_peak`、`dashboard.Span`、`workdays.work_day_map`
- Produces:
  - `AssignmentCell(load: float, over: bool, closed: bool)`
  - `AssignmentRow(name: str, cells: list[AssignmentCell])`
  - `AssignmentTable(labels: list[str], rows: list[AssignmentRow])`
  - `assignment_table(tasks: list[Task], project: Project, holidays: dict[date, str], schedule: Schedule, columns: list[Column]) -> AssignmentTable`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_bottom_info.py`の末尾。import に`assignment_table`・`Column`・`WorkDay`を足す)

```python
from datetime import time, timedelta

from projectapp.bottom_info import assignment_table
from projectapp.timeline import Column
from projectapp.models import WorkDay


def day_columns(first: date, count: int) -> list[Column]:
    return [
        Column(first + timedelta(n), first + timedelta(n + 1), f"{n}")
        for n in range(count)
    ]


def crew(name: str, *people: str, **kw) -> Task:
    return planned(name, assignees=[Assignee(p, 1.0) for p in people], **kw)


def test_daily_cells_show_each_day_load() -> None:
    task = crew("設計", "田中")  # 13h = 月・火の 2 日
    project, schedule = env(task)
    table = assignment_table([task], project, {}, schedule, day_columns(date(2026, 10, 5), 3))
    assert [r.name for r in table.rows] == ["田中"]
    assert [c.load for c in table.rows[0].cells] == [1.0, 1.0, 0.0]
    assert not any(c.over or c.closed for c in table.rows[0].cells)


def test_overlapping_tasks_mark_the_day_as_over() -> None:
    a, b = crew("A", "田中"), crew("B", "田中")
    project, schedule = env(a, b)
    table = assignment_table([a, b], project, {}, schedule, day_columns(date(2026, 10, 5), 1))
    cell = table.rows[0].cells[0]
    assert cell.load == 2.0 and cell.over


def test_a_week_shows_the_workday_average_and_marks_over_if_any_day_is_over() -> None:
    a, b = crew("A", "田中"), crew("B", "田中")
    project, schedule = env(a, b)
    week = [Column(date(2026, 10, 5), date(2026, 10, 12), "10/5")]
    cell = assignment_table([a, b], project, {}, schedule, week).rows[0].cells[0]
    assert cell.load == pytest.approx((2 + 2 + 0 + 0 + 0) / 5)  # 平均は 100% 未満でも
    assert cell.over  # 月・火が 100% 超


def test_a_week_average_under_one_is_not_over() -> None:
    task = crew("A", "田中")
    project, schedule = env(task)
    week = [Column(date(2026, 10, 5), date(2026, 10, 12), "10/5")]
    cell = assignment_table([task], project, {}, schedule, week).rows[0].cells[0]
    assert cell.load == pytest.approx(0.4) and not cell.over


def test_a_weekend_column_is_closed_unless_the_member_works_that_day() -> None:
    task = crew("A", "田中")
    project, schedule = env(task)
    saturday = [Column(date(2026, 10, 10), date(2026, 10, 11), "土")]
    closed = assignment_table([task], project, {}, schedule, saturday).rows[0].cells[0]
    assert closed.closed and closed.load == 0.0
    project.members[0].work_days = [WorkDay(date(2026, 10, 10), time(9), time(15))]
    opened = assignment_table([task], project, {}, schedule, saturday).rows[0].cells[0]
    assert not opened.closed


def test_only_members_with_counted_work_get_a_row() -> None:
    mine, none = crew("A", "田中"), planned("B")
    project, schedule = env(mine, none)
    table = assignment_table([mine, none], project, {}, schedule, day_columns(date(2026, 10, 5), 2))
    assert [r.name for r in table.rows] == ["田中"]
    empty = assignment_table([none], project, {}, schedule, day_columns(date(2026, 10, 5), 2))
    assert empty.rows == [] and empty.labels == ["0", "1"]
```

(`pytest`を import する。`WorkDay`は`projectapp.models`にある。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_bottom_info.py -q`
Expected: FAIL(`assignment_table`の import エラー)

- [ ] **Step 3: 実装する**(`bottom_info.py`。import に`from projectapp.dashboard import Span, _day_peak, _progress_weight`、`from projectapp.timeline import OVERLOAD_EPSILON, Column, Schedule, counted_pieces, is_workday, overdue_reasons`、`from projectapp.workdays import work_day_map`を足す)

```python
@dataclass(frozen=True)
class AssignmentCell:
    load: float  # 日次はその日の負荷。週次・月次は、期間の稼働日の平均(1.0 = 100%)
    over: bool  # 期間のどこかに 100% 超の日がある
    closed: bool  # 期間に稼働日が 1 日もない


@dataclass(frozen=True)
class AssignmentRow:
    name: str
    cells: list[AssignmentCell]


@dataclass(frozen=True)
class AssignmentTable:
    labels: list[str]
    rows: list[AssignmentRow]


def assignment_table(
    tasks: list[Task],
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    columns: list[Column],
) -> AssignmentTable:
    """担当者×列の割り当て率。tasks(絞り込み後)で数える区間のある担当者だけを、メンバーの並びで行にする。"""
    spans: dict[str, list[Span]] = {}
    for task in tasks:
        for left, right, crew in counted_pieces(task, project, holidays, schedule):
            for assignee in crew:
                spans.setdefault(assignee.name, []).append(
                    (left, right, assignee.allocation)
                )
    rows: list[AssignmentRow] = []
    for member in project.members:
        items = spans.get(member.name)
        if not items:
            continue
        overrides = work_day_map(member.work_days)
        cells: list[AssignmentCell] = []
        for column in columns:
            days = [
                column.start + timedelta(days=n)
                for n in range((column.end - column.start).days)
            ]
            open_days = [d for d in days if is_workday(d, holidays, overrides)]
            if not open_days:
                cells.append(AssignmentCell(0.0, False, True))
                continue
            peaks = [_day_peak(items, d) for d in open_days]
            cells.append(
                AssignmentCell(
                    sum(peaks) / len(peaks),
                    any(p > 1.0 + OVERLOAD_EPSILON for p in peaks),
                    False,
                )
            )
        rows.append(AssignmentRow(member.name, cells))
    return AssignmentTable([c.label for c in columns], rows)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_bottom_info.py -q`
Expected: PASS(全件)

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/bottom_info.py test/test_bottom_info.py
git commit -m "feat: 担当者ごとの割り当て表を作る純粋関数を足す(要望 116)"
```
(末尾に Co-Authored-By を付ける)

---

### Task 2: 下部パネルの`割り当て`ビュー

**Files:**
- Modify: `src/projectapp/bottom_panel.py`
- Test: `test/test_bottom_panel.py`

**Interfaces:**
- Consumes: Task 1 の`AssignmentTable`
- Produces:
  - `PanelContent.assignment: AssignmentTable | None = None`(末尾の既定つきフィールド)
  - `BottomPanel(on_select=None, on_toggle_view=None)`。`BottomPanel.view: str`(`"info"`/`"assignment"`、既定`"info"`)、`BottomPanel.toggle_view() -> None`(`view`を入れ替えて描き直す)
  - マーカー: `bottom-assignment`(表全体)、`bottom-assignment-cell`(各セル)、`bottom-assignment-over`(超過のセルに追加)、`bottom-assignment-closed`(休みのセルに追加)、`bottom-assignment-empty`(行がないときの文)、`bottom-view-toggle`(切り替えボタン)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_bottom_panel.py`の末尾)

```python
from projectapp.bottom_info import AssignmentCell, AssignmentRow, AssignmentTable

TABLE = AssignmentTable(
    ["10/5", "10/6", "10/7"],
    [
        AssignmentRow(
            "田中",
            [
                AssignmentCell(1.0, False, False),
                AssignmentCell(2.0, True, False),
                AssignmentCell(0.0, False, True),
            ],
        )
    ],
)


def mount_assignment(content: PanelContent, toggled: list[int] | None = None):
    panels: list[BottomPanel] = []

    @ui.page("/")
    def index() -> None:
        panel = BottomPanel(
            on_toggle_view=(lambda: toggled.append(1)) if toggled is not None else None
        )
        panel.build()
        panel.update(content)
        panels.append(panel)

    return panels


async def test_the_assignment_view_shows_a_row_per_member_and_cell_markers(user: User) -> None:
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, TABLE))
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment")
    await user.should_not_see(marker="bottom-summary")
    assert len(user.find(marker="bottom-assignment-cell").elements) == 3
    assert len(user.find(marker="bottom-assignment-over").elements) == 1
    assert len(user.find(marker="bottom-assignment-closed").elements) == 1


async def test_the_assignment_view_ignores_a_selection_until_it_is_toggled_back(user: User) -> None:
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, TABLE))
    await user.open("/")
    panels[0].toggle_view()
    panels[0].update(PanelContent(DETAIL, SUMMARY, TODAY, TABLE))  # 選択した
    await user.should_see(marker="bottom-assignment")
    await user.should_not_see(marker="bottom-detail")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-detail")


async def test_an_empty_table_says_so_instead_of_failing(user: User) -> None:
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, AssignmentTable([], [])))
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment-empty")


async def test_the_toggle_button_calls_the_callback(user: User) -> None:
    toggled: list[int] = []
    mount_assignment(PanelContent(None, SUMMARY, TODAY), toggled)
    await user.open("/")
    user.find(marker="bottom-view-toggle").click()
    await asyncio.sleep(0.2)
    assert toggled == [1]
```

(`asyncio`を import する。既存の`PanelContent(None, SUMMARY, TODAY)`の 3 引数の呼び出しは、`assignment`に既定があるのでそのまま通る。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_bottom_panel.py -q`
Expected: FAIL(`on_toggle_view`・`toggle_view`・`assignment`がない)

- [ ] **Step 3: 実装する**(`bottom_panel.py`)

`PanelContent`に`assignment: AssignmentTable | None = None`を足す(`AssignmentTable`を import)。`BottomPanel`:

```python
def __init__(self, on_select=None, on_toggle_view: Callable[[], None] | None = None) -> None:
    ...  # 既存
    self.on_toggle_view = on_toggle_view
    self.view = "info"  # "info" | "assignment"。保存しない

def build(self) -> None:
    with ui.element("div").classes("w-full h-full").style("position: relative; overflow: hidden"):
        ui.button(
            icon="calendar_view_week",
            on_click=lambda: self.on_toggle_view() if self.on_toggle_view else self.toggle_view(),
        ).props("flat dense round size=sm").classes("text-grey-8").style(
            "position: absolute; top: 2px; right: 8px; z-index: 5"
        ).mark("bottom-view-toggle").tooltip("割り当て表示の切り替え(Ctrl/Cmd+Alt/Option)")
        with ui.column().classes("w-full h-full gap-1 p-2").style("overflow: auto").mark("bottom-panel"):
            self.body()

def toggle_view(self) -> None:
    self.view = "info" if self.view == "assignment" else "assignment"
    self.body.refresh()
```

`body`の先頭(`content is None`の判定のあと)に追加:

```python
if self.view == "assignment":
    self.show_assignment(self.content.assignment)
    return
```

```python
CELL_STYLE = "min-width: 3.4em; text-align: center; padding: 1px 2px; font-size: 12px"
LOAD_COLOR = "rgba(76, 139, 245, {alpha:.2f})"
OVER_STRIPE = "repeating-linear-gradient(45deg, rgba(220, 53, 69, 0.6) 0 4px, transparent 4px 8px)"

def show_assignment(self, table: AssignmentTable | None) -> None:
    """担当者×列の割り当て率。濃さが負荷、縞が 100% 超、灰色が休み。独立して横にスクロールする。"""
    with ui.element("div").classes("w-full").style("overflow-x: auto").mark("bottom-assignment"):
        if table is None or not table.rows:
            ui.label("割り当てのある担当者はいません").classes("text-grey").mark("bottom-assignment-empty")
            return
        grid = ui.element("div").style(
            f"display: grid; grid-template-columns: 8em repeat({len(table.labels)}, 3.4em); width: max-content"
        )
        with grid:
            ui.label("")
            for label in table.labels:
                ui.label(label).classes("text-caption text-grey").style(CELL_STYLE)
            for row in table.rows:
                ui.label(row.name).classes("text-bold").style("padding: 1px 4px")
                for cell in row.cells:
                    self.show_assignment_cell(cell)

def show_assignment_cell(self, cell: AssignmentCell) -> None:
    markers = "bottom-assignment-cell"
    if cell.closed:
        background = "rgba(128, 128, 128, 0.18)"
        markers += " bottom-assignment-closed"
    else:
        background = LOAD_COLOR.format(alpha=min(cell.load, 1.0) * 0.7)
        if cell.over:
            background = f"{OVER_STRIPE}, {background}"
            markers += " bottom-assignment-over"
    text = "" if cell.closed or cell.load <= 0 else f"{cell.load * 100:.0f}"
    ui.label(text).style(f"{CELL_STYLE}; background: {background}").mark(markers)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_bottom_panel.py test/test_bottom_split.py -q`
Expected: PASS(既存の`bottom-panel`のマーカーの位置が変わっても通ること。通らなければ、ラッパー`div`が原因なので、既存テストの期待ではなく実装を直す)

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/bottom_panel.py test/test_bottom_panel.py
git commit -m "feat: 下部パネルに割り当てビューと切り替えボタンを足す(要望 116)"
```

---

### Task 3: ガントチャートとの連携(切り替えと表の更新)

**Files:**
- Modify: `src/projectapp/gantt.py`
- Create: `test/test_assignment_view.py`

**Interfaces:**
- Consumes: Task 1・2 の成果、`build_columns(project, scale, holidays, period, references)`、`GanttChart.view_scale`・`view_period`・`reference_values()`・`visible_task_ids()`・`open_bottom()`・`bottom_open`
- Produces: `GanttChart.toggle_assignment() -> None`(畳んでいれば開いて`割り当て`ビューにする。開いていれば入れ替える。`read_only`では何もしない)。`bottom_content()`は、`bottom.view == "assignment"`のときだけ`PanelContent.assignment`に表を入れる

- [ ] **Step 1: 失敗するテストを書く**(新規`test/test_assignment_view.py`)

```python
import asyncio
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import GanttChart, ViewOptions
from projectapp.models import Assignee, Member, Project, Task
from projectapp.timeline import Scale
from test_gantt import Recorder

BASE = date(2026, 10, 5)


def project() -> Project:
    return Project(
        "demo",
        base_date=BASE,
        members=[Member("田中", 1.0)],
        tasks=[
            Task("a", id="a", planned_start=datetime(2026, 10, 5, 9), effort_hours=13,
                 assignees=[Assignee("田中", 1.0)]),
            Task("b", id="b"),
        ],
    )


def mount():
    charts: list[GanttChart] = []
    recorder = Recorder()
    recorder.actions.set_main_split = lambda value: None

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project(), {}, recorder.actions, now=lambda: datetime(2026, 10, 7, 12))
        charts.append(chart)
        chart.build()

    return charts


async def test_toggling_opens_a_folded_panel_on_the_assignment_view(user: User) -> None:
    charts = mount()
    await user.open("/")
    assert not charts[0].bottom_open
    charts[0].toggle_assignment()
    assert charts[0].bottom_open and charts[0].bottom.view == "assignment"
    await user.should_see(marker="bottom-assignment")
    assert [r.name for r in charts[0].bottom.content.assignment.rows] == ["田中"]


async def test_selecting_while_in_the_assignment_view_keeps_it_until_toggled_back(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    charts[0].clicked_task("a", {"ctrl": True})
    await user.should_see(marker="bottom-assignment")
    await user.should_not_see(marker="bottom-detail")
    charts[0].toggle_assignment()
    await user.should_see(marker="bottom-detail")


async def test_the_table_follows_the_scale(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    days = len(charts[0].bottom.content.assignment.labels)
    charts[0].set_scale(Scale.WEEK)
    await asyncio.sleep(0.2)
    weeks = len(charts[0].bottom.content.assignment.labels)
    assert 0 < weeks < days


async def test_the_info_view_does_not_compute_the_table(user: User) -> None:
    charts = mount()
    await user.open("/")
    assert charts[0].bottom.content.assignment is None


async def test_toggling_does_nothing_in_the_preview(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].set_options(ViewOptions(read_only=True))
    charts[0].toggle_assignment()
    assert charts[0].bottom.view == "info"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assignment_view.py -q`
Expected: FAIL(`toggle_assignment`がない)

- [ ] **Step 3: 実装する**(`gantt.py`)

`__init__`の`self.bottom = BottomPanel(on_select=self.select_tasks)`を`BottomPanel(on_select=self.select_tasks, on_toggle_view=self.toggle_assignment)`に。`open_bottom`の近くに:

```python
def toggle_assignment(self) -> None:
    """`割り当て`ビューと元の内容を入れ替える。畳んでいれば開いて`割り当て`にする。プレビューでは何もしない。"""
    if self.splitter is None or self.options.read_only:
        return
    if not self.bottom_open:
        self.bottom.view = "assignment"
        self.open_bottom()
    else:
        self.bottom.view = "info" if self.bottom.view == "assignment" else "assignment"
    self.refresh_bottom()
```

`bottom_content`の`return PanelContent(...)`に第 4 引数を足す:

```python
assignment = None
if self.bottom.view == "assignment":
    columns = build_columns(
        self.project, self.view_scale, self.holidays, self.view_period, self.reference_values()
    )
    assignment = assignment_table(tasks, self.project, self.holidays, self.schedule, columns)
return PanelContent(detail, period_summary(...), today_plan(tasks, self.schedule, now), assignment)
```

(`assignment_table`を import。`open_bottom`が畳んでいる状態の`set_value`で`split_changed`→`refresh`を呼ぶので、`view`は`open_bottom`の前に切り替える。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assignment_view.py test/test_bottom_split.py test/test_bottom_panel.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/gantt.py test/test_assignment_view.py
git commit -m "feat: ガントチャートと割り当てビューをつなぐ(要望 116)"
```

---

### Task 4: `Ctrl/Cmd + Alt/Option`のショートカット

**Files:**
- Modify: `src/projectapp/shortcuts.py`、`src/projectapp/views.py`
- Test: `test/test_shortcuts.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `GanttChart.toggle_assignment`(Task 3)、`shortcuts.resolve`、`Shortcut`、`views.SHORTCUT_METHODS`、`views.on_key`
- Produces: `Shortcut("alt", "assignment_view", ...)`。`label()`は`Ctrl/Cmd+Alt/Option`。`views`の`toggle_assignment_view()`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_shortcuts.py`:

```python
@pytest.mark.parametrize("key", ["Alt", "alt", "Control", "Meta"])
def test_ctrl_and_alt_together_resolve_to_the_assignment_view(key: str) -> None:
    assert resolve(key, ctrl=True, shift=False, modal=False, screen=Screen.MAIN) == "assignment_view"


def test_alt_alone_does_not_resolve() -> None:
    assert resolve("Alt", ctrl=False, shift=False, modal=False, screen=Screen.MAIN) is None


def test_the_assignment_view_shortcut_is_ignored_in_dialogs_and_other_screens() -> None:
    assert resolve("Alt", ctrl=True, shift=False, modal=True, screen=Screen.MAIN) is None
    assert resolve("Alt", ctrl=True, shift=False, modal=False, screen=Screen.DASHBOARD) is None


def test_the_help_lists_the_assignment_view_key() -> None:
    assert ("Ctrl/Cmd+Alt/Option", "割り当て表示の切り替え") in help_entries()
```

`test/test_views.py`: `key_event`に`alt: bool = False, repeat: bool = False`を足す(`KeyboardAction(repeat=repeat)`、`KeyboardModifiers(alt=alt, ...)`)。既存の`test_the_date_move_keys_reach_the_chart…`(2042 行付近)と同じ作りで、次の 3 件を書く:

```python
async def test_ctrl_and_alt_together_toggle_the_assignment_view(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    view.on_key(key_event("Alt", ctrl=True, alt=True))
    assert view.gantt.bottom.view == "assignment"
    view.on_key(key_event("Alt", ctrl=True, alt=True, repeat=True))  # 押しっぱなしは無視
    assert view.gantt.bottom.view == "assignment"
    view.on_key(key_event("Control", ctrl=True, alt=True))  # Alt を先に押した順でも効く
    assert view.gantt.bottom.view == "info"


async def test_ctrl_or_alt_alone_does_not_toggle(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    view.on_key(key_event("Control", ctrl=True))
    view.on_key(key_event("Alt", alt=True))
    assert view.gantt.bottom.view == "info"


async def test_the_assignment_key_is_ignored_on_the_dashboard(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    view.open_dashboard()
    view.on_key(key_event("Alt", ctrl=True, alt=True))
    assert view.gantt.bottom.view == "info"
```

(`key_event`は`alt`・`repeat`を足した形。ダイアログが開いている間に効かないことは、`resolve`の`modal`のテストで押さえる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_shortcuts.py test/test_views.py -q -k "assignment or alt"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`shortcuts.py`: `SHORTCUTS`の末尾付近に追加

```python
Shortcut("alt", "assignment_view", "割り当て表示の切り替え", ctrl=True, aliases=("control", "meta")),
```
`Shortcut.label()`の先頭に`if self.key == "alt": return "Ctrl/Cmd+Alt/Option"`を足す。(`control`・`meta`は、Alt を先に押してから Ctrl/Cmd を押した順でも拾うための別名。)

`views.py`: `SHORTCUT_METHODS`に`"assignment_view": "toggle_assignment_view"`を足し、`on_key`の`action = resolve(...)`の直後に

```python
if action == "assignment_view" and (not event.modifiers.alt or event.action.repeat):
    return  # Ctrl/Alt の片方だけ・押しっぱなしの連続入力では切り替えない
```
メソッド:

```python
def toggle_assignment_view(self) -> None:
    self.gantt.toggle_assignment()
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_shortcuts.py test/test_views.py -q`
Expected: PASS(`help_entries`の件数を固定しているテストがあれば、実装ではなくテストの期待を 1 件増やす)

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/shortcuts.py src/projectapp/views.py test/test_shortcuts.py test/test_views.py
git commit -m "feat: Ctrl/Cmd + Alt/Option で割り当てビューを切り替える(要望 116)"
```

---

### Task 5: 文書と全体の確認

**Files:**
- Modify: `.claude/spec/gantt.md`、`README.md`、設計書(状態)、`docs/requests.md`、`docs/request-history.md`、`docs/superpowers/README.md`

**Interfaces:** なし(文書のみ)

- [ ] **Step 1: 文書を更新する**
  - `.claude/spec/gantt.md`の下部パネルの項に、`割り当て`ビュー(切り替え・行・数字〔日次はその日、週次・月次は稼働日の平均〕・100% 超の縞・休みの灰色・絞り込みに従う・表示中は選択でも内容を変えない・独立して横にスクロール)を足す
  - `README.md`のキーボード操作の表に`Ctrl/Cmd + Alt/Option`の行、下部パネルの説明に`割り当て`ビューを足す
  - 設計書・`docs/requests.md`(要望 116)・`docs/request-history.md`・`docs/superpowers/README.md`の状態を、`実装済み(実機確認待ち。ブランチ feature/assignment-view)`に、計画へのリンクを足す
- [ ] **Step 2: 全体を検証する**

Run: `uv run pytest -m smoke -q && uv run pytest -n auto -q`
Expected: 全件 PASS

Run: `uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: ruff は問題なし。ty は`dashboard_view.py`の`days_text`の 1 件だけ

- [ ] **Step 3: コミット**

```bash
git add -A .claude README.md docs
git commit -m "docs: 下部パネルの割り当て表示を仕様・文書に反映する(要望 116)"
```

実機で確認してもらう項目(ブラウザなしでは確かめられない): `Ctrl/Cmd + Alt/Option`の同時押しが macOS のネイティブウィンドウで効く・Alt を先に押す順でも効く・ブラウザ(Web モード)で Alt が URL バーなどに奪われない・表の見た目(濃さ・縞・休み)と横スクロール・日次/週次/月次の切り替えへの追従・絞り込みへの追従・畳んでいるときに開く。
