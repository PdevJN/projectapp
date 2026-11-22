# アサイン専用画面 段階 1(土台)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードのタスク行の右クリック`アサイン...`から、タスク 1 件の試算用の全画面ダイアログ(日/週/月のガントチャート・確定・キャンセル)を開けるようにする。

**Architecture:** 試算の状態(`assign_trial.py`)は NiceGUI に依存しない純粋関数。画面(`assign_screen.py`)は、対象タスク 1 件だけのプロジェクトのコピーを、`GanttChart` の埋め込みモード(`build_embedded`)で読み取り専用に描く。確定は`crew_trial.replace_task`で書き戻し、`MainView.after_edit`で履歴に 1 ステップ積む。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-22-assign-screen-stage1-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。試算は保存しない
- 描画は NiceGUI の要素と CSS による自前描画。外部のガントライブラリは使わない
- 対象は右クリックした 1 つのタスク。まとめ・節目・参照行・終了済みのタスクは対象外(メニューを出さない)
- 参照先のタスク(他のプロジェクトのタスク)は対象外。行データの`task_id`は、開いているプロジェクトのタスクだけに入れる
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは git-flow。`develop`から`feature/request-168-stage1`を切る。マージは利用者の指示を待つ(PR を作って止まる)
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Review Focus

- 対象タスクがまとめ・節目・参照行・終了済みのとき: メニューを出さない。`open_assign_screen`を直接呼ばれても、通知して開かない
- 画面を開いている間に、タスクが削除された・Undo で差し替わったとき: 確定は書き戻さず通知する(`assign_from_dashboard`と同じ)
- 変更がないのに確定したとき: `after_edit`は履歴を積まない(空の Undo ステップを作らない)
- Esc・×・キャンセルのどれでも、変更がなければ確認なしで閉じ、あれば確認する。確認で「戻る」を選ぶと画面に戻る
- 画面を開いたあと、メインのガントチャートの CSS・JS・イベントが二重に登録されない(`build_embedded`は登録しない)

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/assign_trial.py`(新規) | 試算の状態。`AssignTrial`・`start_trial`・`is_dirty`・`is_assignable`・`trial_project`・`apply_trial`。純粋関数 |
| `src/projectapp/assign_screen.py`(新規) | 全画面ダイアログ`AssignScreen`(日/週/月・確定・キャンセル・確認) |
| `src/projectapp/gantt.py`(変更) | `GanttChart.build_embedded()`を足す |
| `src/projectapp/dashboard.py`(変更) | `OverdueRow`・`StartDelayRow`・`DueRow`に`task_id`を足す |
| `src/projectapp/dashboard_view.py`(変更) | `on_assign_screen`・`assignable`・右クリックメニュー`assign_menu` |
| `src/projectapp/views.py`(変更) | `MainView.open_assign_screen`・配線 |
| `test/test_assign_trial.py`(新規) | 純粋関数のテスト |
| `test/test_assign_screen.py`(新規) | 画面のテスト |
| `test/test_dashboard_view.py`・`test/test_views.py`(変更) | 入口と確定・Undo のテスト |
| `.claude/spec/dashboard.md`・`docs/development.md`・`docs/requests.md`(変更) | 仕様・構成・状態表記 |

---

### Task 1: 試算の状態(`assign_trial.py`)

**Files:**
- Create: `src/projectapp/assign_trial.py`
- Test: `test/test_assign_trial.py`

**Interfaces:**
- Produces:
  - `AssignTrial(original: Task, task: Task)`(dataclass)
  - `start_trial(task: Task) -> AssignTrial`
  - `is_dirty(trial: AssignTrial) -> bool`
  - `is_assignable(task: Task) -> bool`
  - `trial_project(project: Project, trial: AssignTrial) -> Project`
  - `apply_trial(project: Project, trial: AssignTrial) -> bool`

- [ ] **Step 1: テストを書く**

`test/test_assign_trial.py`:

```python
from datetime import date

from projectapp.assign_trial import (
    apply_trial,
    is_assignable,
    is_dirty,
    start_trial,
    trial_project,
)
from projectapp.models import (
    Assignee,
    Member,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)


def project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        sections=[Section("開発", [Task("設計", id="a", effort_hours=8.0)])],
        tasks=[Task("直下", id="t")],
    )


def test_start_trial_copies_the_task() -> None:
    task = Task("設計", id="a")
    trial = start_trial(task)
    assert trial.task == task and trial.task is not task
    assert trial.original is not trial.task


def test_is_dirty_only_when_the_copy_differs() -> None:
    trial = start_trial(Task("設計", id="a"))
    assert is_dirty(trial) is False
    trial.task.assignees = [Assignee("田中")]
    assert is_dirty(trial) is True


def test_is_assignable_excludes_non_normal_and_done_tasks() -> None:
    assert is_assignable(Task("通常", id="a")) is True
    assert is_assignable(Task("実行中", id="b", status=Status.RUNNING)) is True
    assert is_assignable(Task("終了", id="c", status=Status.DONE)) is False
    for kind in (TaskKind.CHECKPOINT, TaskKind.REFERENCE, TaskKind.SUMMARY):
        assert is_assignable(Task("x", id="d", kind=kind)) is False


def test_trial_project_holds_only_the_one_task_and_keeps_the_original_project() -> None:
    base = project()
    trial = start_trial(base.task_map()["a"])
    copy = trial_project(base, trial)
    assert [t.id for t in copy.all_tasks()] == ["a"]
    assert copy.members == base.members and copy.base_date == base.base_date
    assert [t.id for t in base.all_tasks()] == ["a", "t"]  # 元は変えない


def test_apply_trial_writes_the_copy_back_to_the_same_task() -> None:
    base = project()
    trial = start_trial(base.task_map()["a"])
    trial.task.name = "詳細設計"
    assert apply_trial(base, trial) is True
    assert base.task_map()["a"].name == "詳細設計"


def test_apply_trial_returns_false_when_the_task_is_gone() -> None:
    base = project()
    trial = start_trial(base.task_map()["a"])
    base.sections[0].tasks.clear()
    assert apply_trial(base, trial) is False
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assign_trial.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.assign_trial`)

- [ ] **Step 3: 実装する**

`src/projectapp/assign_trial.py`:

```python
"""アサイン専用画面(要望 168)の試算の状態。NiceGUI に依存しない純粋関数。

試算は保存しない(ファイル形式は変えない)。開いた時点のタスクのコピーを画面の中で持ち、確定したときだけ
`crew_trial.replace_task`で書き戻す。
"""

from copy import deepcopy
from dataclasses import dataclass, replace

from projectapp.crew_trial import replace_task
from projectapp.models import Project, Status, Task, TaskKind


@dataclass
class AssignTrial:
    original: Task  # 開いた時点のタスク(変更の有無を比べる基準)
    task: Task  # 画面の中で編集するコピー


def start_trial(task: Task) -> AssignTrial:
    return AssignTrial(deepcopy(task), deepcopy(task))


def is_dirty(trial: AssignTrial) -> bool:
    return trial.task != trial.original


def is_assignable(task: Task) -> bool:
    """アサインの対象になるタスク: 通常で、終了していないもの。"""
    return task.kind is TaskKind.NORMAL and task.status is not Status.DONE


def trial_project(project: Project, trial: AssignTrial) -> Project:
    """試算のタスク 1 件だけを持つプロジェクトのコピー(ガントチャートの描画用)。元は変えない。"""
    copy = deepcopy(project)
    return replace(copy, tasks=[deepcopy(trial.task)], sections=[])


def apply_trial(project: Project, trial: AssignTrial) -> bool:
    """試算のコピーを、同じ id のタスクへ書き戻す。タスクがなければ False。"""
    return replace_task(project, deepcopy(trial.task))
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assign_trial.py -v`
Expected: PASS(6 件)。`replace`が`Project`で失敗するときは、`Project`が dataclass であること(`models.py:440`)を確かめ、`copy.tasks = [...]`・`copy.sections = []`の代入に変える。

- [ ] **Step 5: コミット**

```bash
git checkout develop && git pull -q origin develop && git checkout -b feature/request-168-stage1
git add src/projectapp/assign_trial.py test/test_assign_trial.py
git commit -m "feat: アサイン専用画面の試算の状態(要望 168 段階 1)"
```

---

### Task 2: `GanttChart.build_embedded`(埋め込みモード)

`build()`は、ページ全体の CSS・JS・`ui.on`の登録とツールバー・下部パネルを作る。2 つ目の`GanttChart`でそのまま呼ぶと二重に登録されるので、**描画だけ**を作る`build_embedded`を足す。

**Files:**
- Modify: `src/projectapp/gantt.py`(`build`の直前、1806 行付近)
- Test: `test/test_assign_screen.py`(新規。この Task で作り、Task 3 で足す)

**Interfaces:**
- Consumes: `GanttChart(project, holidays, actions, ...)`・`GanttChart.render`・`GanttChart.set_scale(scale)`
- Produces: `GanttChart.build_embedded() -> None`。メインの`build()`が済んだページの中で、読み取り専用の描画だけを作る

- [ ] **Step 1: テストを書く**

`test/test_assign_screen.py`(新規。`test_gantt.py`の`mount_chart`の書き方に合わせる。先に`test/test_gantt.py`の`mount_chart`を読む):

```python
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import Project, Task
from projectapp.timeline import Scale


def noop_actions() -> GanttActions:
    return GanttActions(
        add_section=lambda: None,
        add_task=lambda path: None,
        add_top_task=lambda: None,
        edit_task=lambda path, ti: None,
        move_task=lambda src, dst, copy: None,
        shift_task=lambda path, ti, days: None,
        set_name_width=lambda width: None,
    )


def one_task_project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        tasks=[
            Task(
                "設計",
                id="a",
                planned_start=datetime(2026, 10, 6, 9),
                planned_end=datetime(2026, 10, 9, 12),
            )
        ],
    )


async def test_embedded_chart_draws_the_bar_without_a_second_toolbar(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        embedded = GanttChart(one_task_project(), {}, noop_actions())
        embedded.build_embedded()
        charts.extend([main, embedded])

    await user.open("/")
    main, embedded = charts
    assert embedded.toolbar is None and embedded.splitter is None
    assert embedded.options.read_only is True
    assert len(embedded.task_rows) == 1
    embedded.set_scale(Scale.WEEK)  # ツールバーがなくても切り替えられる
    assert embedded.scale is Scale.WEEK
    assert main.scale is Scale.DAY  # メインには影響しない
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assign_screen.py -v`
Expected: FAIL(`AttributeError: 'GanttChart' object has no attribute 'build_embedded'`)

- [ ] **Step 3: 実装する**

`gantt.py`の`def build(self) -> None:`の直前に足す(`replace`は`dataclasses`から。`gantt.py`に既に import があるか確かめ、なければ足す):

```python
    def build_embedded(self) -> None:
        """読み取り専用の埋め込み(アサイン専用画面。要望 168)。描画だけを作る。

        ページ全体の CSS・JS・`ui.on`の登録は、メインの`build()`が済ませている前提で重ねない。ツールバー・
        絞り込み・下部パネル・右クリックメニューは作らない(`toolbar`・`splitter`・`menu`は`None`のまま)。
        """
        self.client = context.client
        self.options = replace(self.options, read_only=True)
        scroll = ui.element("div").classes("w-full").style(
            f"overflow: auto; height: 100%; padding-bottom: {SCROLLBAR_ROOM_PX}px"
        )
        self.scroll_box = scroll
        with scroll.mark("assign-chart-scroll"):
            self.render()
```

- [ ] **Step 4: 通ることを確かめる・描画の穴を直す**

Run: `uv run pytest test/test_assign_screen.py -v`
Expected: PASS。`render`の途中で`self.menu`・`self.bottom`などが`None`で落ちたら、落ちた箇所を`if ... is not None`で守る(最小の変更。`render`の通常の挙動は変えない)。直した箇所は Step 5 のコミットメッセージに書く。直せないほど広がるなら、実装を止めて設計書の「確かめること」に戻る(利用者に確認する)。

併せて、`uv run pytest test/test_gantt.py test/test_context_menu.py test/test_bottom_split.py -q`が通ることを確かめる(メインの挙動を変えていない確認)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_assign_screen.py
git commit -m "feat: GanttChart の埋め込みモード(build_embedded)を足す(要望 168 段階 1)"
```

---

### Task 3: アサイン専用画面(`assign_screen.py`)

**Files:**
- Create: `src/projectapp/assign_screen.py`
- Test: `test/test_assign_screen.py`(足す)

**Interfaces:**
- Consumes: `AssignTrial`・`start_trial`・`is_dirty`・`trial_project`(Task 1)、`GanttChart.build_embedded`(Task 2)
- Produces:
  - `AssignScreen(project: Project, task: Task, holidays: dict[date, str], on_confirm: Callable[[AssignTrial], object], *, now=clock.now, name_width=..., fiscal_start_month=...)`
  - `AssignScreen.open() -> None`・`.cancel() -> None`・`.confirm() -> None`
  - 属性`trial: AssignTrial`・`chart: GanttChart | None`・`dialog: ui.dialog | None`
  - マーカー: `assign-screen`・`assign-task-title`・`assign-scale`・`assign-confirm`・`assign-cancel`・`assign-discard-yes`・`assign-discard-no`

- [ ] **Step 1: テストを書く**

`test/test_assign_screen.py`に足す:

```python
from projectapp.assign_screen import AssignScreen
from projectapp.assign_trial import AssignTrial


def mount_screen(confirmed: list[AssignTrial], screens: list[AssignScreen]) -> None:
    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        project = one_task_project()
        screen = AssignScreen(
            project, project.tasks[0], {}, on_confirm=confirmed.append
        )
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")


async def test_open_shows_the_title_and_the_chart(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-screen")
    await user.should_see("設計")
    assert screens[0].chart is not None and len(screens[0].chart.task_rows) == 1


async def test_scale_toggle_changes_only_the_embedded_chart(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-scale")
    screens[0].set_scale(Scale.MONTH)
    assert screens[0].chart is not None and screens[0].chart.scale is Scale.MONTH


async def test_confirm_calls_back_with_the_trial_and_closes(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-confirm")
    screens[0].trial.task.name = "詳細設計"
    user.find(marker="assign-confirm").click()
    assert [t.task.name for t in confirmed] == ["詳細設計"]
    await user.should_not_see(marker="assign-screen")


async def test_cancel_without_changes_closes_without_asking(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    user.find(marker="assign-cancel").click()
    await user.should_not_see(marker="assign-screen")
    assert confirmed == []


async def test_cancel_with_changes_asks_and_keeps_the_screen_on_no(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    screens[0].trial.task.name = "変更"
    user.find(marker="assign-cancel").click()
    await user.should_see(marker="assign-discard-no")
    user.find(marker="assign-discard-no").click()
    await user.should_see(marker="assign-screen")  # 画面に戻る
    user.find(marker="assign-cancel").click()
    user.find(marker="assign-discard-yes").click()
    await user.should_not_see(marker="assign-screen")
    assert confirmed == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assign_screen.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.assign_screen`)

- [ ] **Step 3: 実装する**

`src/projectapp/assign_screen.py`:

```python
"""アサイン専用の全画面ダイアログ(要望 168 段階 1)。

対象タスク 1 件の試算のコピーを持ち、`GanttChart`の埋め込みモードで読み取り専用に描く。確定で
`on_confirm(trial)`を呼び、キャンセルでは何も反映しない。変更があるとき(`is_dirty`)だけ、捨てる確認を出す。
段階 2 以降で、左にメンバーのアイコン列、下に負荷のヒストグラムを足す。
"""

from collections.abc import Callable
from datetime import date

from nicegui import ui

from projectapp import clock
from projectapp.assign_trial import AssignTrial, is_dirty, start_trial, trial_project
from projectapp.forms import disposable
from projectapp.gantt import (
    DEFAULT_NAME_WIDTH_PX,
    GanttActions,
    GanttChart,
)
from projectapp.models import Project, Task
from projectapp.timeline import DEFAULT_FISCAL_START_MONTH, Scale

ASSIGN_SCALES = (Scale.DAY, Scale.WEEK, Scale.MONTH)


def read_only_actions() -> GanttActions:
    """読み取り専用の画面なので、チャートからの操作は何もしない(必須のコールバックだけ空で渡す)。"""
    return GanttActions(
        add_section=lambda: None,
        add_task=lambda path: None,
        add_top_task=lambda: None,
        edit_task=lambda path, ti: None,
        move_task=lambda src, dst, copy: None,
        shift_task=lambda path, ti, days: None,
        set_name_width=lambda width: None,
    )


class AssignScreen:
    def __init__(
        self,
        project: Project,
        task: Task,
        holidays: dict[date, str],
        on_confirm: Callable[[AssignTrial], object],
        *,
        now: Callable[[], object] = clock.now,
        name_width: int = DEFAULT_NAME_WIDTH_PX,
        fiscal_start_month: int = DEFAULT_FISCAL_START_MONTH,
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.on_confirm = on_confirm
        self.now = now
        self.name_width = name_width
        self.fiscal_start_month = fiscal_start_month
        self.trial = start_trial(task)
        self.chart: GanttChart | None = None
        self.dialog: ui.dialog | None = None

    def open(self) -> None:
        with (
            disposable(ui.dialog()).props("persistent maximized") as dialog,
            ui.card().classes("w-full h-full no-wrap").mark("assign-screen"),
        ):
            self.dialog = dialog
            dialog.on("escape-key", lambda _e: self.cancel())
            with ui.row().classes("w-full items-center no-wrap gap-4"):
                ui.label(self.trial.task.name).classes("text-h6 col ellipsis").mark(
                    "assign-task-title"
                )
                ui.toggle(
                    {scale: scale.value for scale in ASSIGN_SCALES},
                    value=Scale.DAY,
                    on_change=lambda e: self.set_scale(Scale(e.value)),
                ).mark("assign-scale")
                ui.button("キャンセル", on_click=self.cancel).props("flat").mark(
                    "assign-cancel"
                )
                ui.button("確定", on_click=self.confirm).props("color=primary").mark(
                    "assign-confirm"
                )
            with ui.element("div").classes("w-full").style("flex: 1 1 0; min-height: 0"):
                self.chart = GanttChart(
                    trial_project(self.project, self.trial),
                    self.holidays,
                    read_only_actions(),
                    now=self.now,  # type: ignore[arg-type]
                    name_width=self.name_width,
                    fiscal_start_month=self.fiscal_start_month,
                )
                self.chart.build_embedded()
        dialog.open()

    def set_scale(self, scale: Scale) -> None:
        if self.chart is not None:
            self.chart.set_scale(scale)

    def confirm(self) -> None:
        self.close()
        self.on_confirm(self.trial)

    def cancel(self) -> None:
        if not is_dirty(self.trial):
            self.close()
            return
        with (
            disposable(ui.dialog()) as ask,
            ui.card().mark("assign-discard"),
        ):
            ui.label("変更を捨てますか?")
            with ui.row():
                ui.button("戻る", on_click=ask.close).props("flat").mark(
                    "assign-discard-no"
                )
                ui.button(
                    "捨てる", on_click=lambda: (ask.close(), self.close())
                ).props("color=negative").mark("assign-discard-yes")
        ask.open()

    def close(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assign_screen.py -v`
Expected: PASS。`GanttChart`の`now`の型、`DEFAULT_NAME_WIDTH_PX`・`DEFAULT_FISCAL_START_MONTH`の import 元が違えば(`gantt.py`・`timeline.py`で確かめる)直す。`# type: ignore`は使わず、`now: Callable[[], datetime]`の型にそろえる。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン専用の全画面ダイアログ(要望 168 段階 1)"
```

---

### Task 4: 行データに`task_id`を足す(`dashboard.py`)

`OverdueRow`・`StartDelayRow`・`DueRow`は名前しか持たない。右クリックの対象を特定するため、`task_id`を足す。**開いているプロジェクトのタスクだけ**に入れ、参照先のタスクは空にする。

**Files:**
- Modify: `src/projectapp/dashboard.py`(`OverdueRow` 208 行付近・`StartDelayRow` 254 行付近・`DueRow` 897 行付近と、3 つの生成箇所 770・825・1191 行付近)
- Test: `test/test_dashboard.py`

**Interfaces:**
- Produces: `OverdueRow.task_id: str = ""`・`StartDelayRow.task_id: str = ""`・`DueRow.task_id: str = ""`(いずれも末尾の既定値つきフィールドで`compare=False`。既存の位置引数の呼び出しと`==`の比較を壊さない)

- [ ] **Step 1: 生成箇所を読む**

`dashboard.py`の 3 つの生成箇所の周りを読み、`task`と`entry`(`entry.project`・`entry.label`)・`project`(開いているプロジェクト)の名前を確かめる。`summarize_due`は開いているプロジェクト自身のタスクだけを数える(`_tasks(project, member)`)ので、`DueRow`の`task_id`は常に`task.id`でよい。`OverdueRow`・`StartDelayRow`は`entry.project is project`で参照先を外す。

- [ ] **Step 2: テストを書く**

`test/test_dashboard.py`に、既存のテストの組み立て(`summarize_progress`・`due_rows`などを呼ぶ既存のテスト)をまねて足す。

```python
def test_overdue_and_due_rows_carry_the_task_id() -> None:
    late = Task(
        "late",
        id="late-id",
        status=Status.RUNNING,
        deadline=datetime(2026, 10, 6, 17),
        assignees=[Assignee("田中")],
    )
    project = project_of(late)
    due = summarize_due(project, WEEK, NOW, {})
    assert [row.task_id for row in due] == ["late-id"]
    progress = summarize_progress(project, WEEK, NOW, {})
    assert [row.task_id for row in progress.overdue] == ["late-id"]


def test_task_id_does_not_change_row_equality() -> None:
    """既存のテストは`DueRow(...)`と`==`で比べる。`task_id`は比較に入れない。"""
    a = DueRow(datetime(2026, 10, 5), "締切", "x", None, False, task_id="a")
    b = DueRow(datetime(2026, 10, 5), "締切", "x", None, False, task_id="b")
    assert a == b
```

着工遅れ(`StartDelayRow`)は、`test_dashboard.py`の既存の着工遅れの集計のテスト(`start_delays`で検索)のデータをそのまま使い、`row.task_id == その task.id`を 1 行足す。参照先のタスク(`test_dashboard_references.py`のデータ)では`row.task_id == ""`を足す。`summarize_progress`の引数は、`test_dashboard.py`の既存の呼び出し(`summarize_progress(` で検索)に合わせる。

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard.py -k task_id -v`
Expected: FAIL(`task_id`がない)

- [ ] **Step 4: 実装する**

3 つのデータクラスの末尾に足す:

```python
    task_id: str = field(
        default="", compare=False
    )  # 開いているプロジェクトのタスクの id。参照先のタスクは空(アサイン画面の対象外。要望 168)。既存のテストは行を`==`で比べるので、比較には入れない
```

`dashboard.py`の`from dataclasses import ...`に`field`を足す(なければ)。

生成箇所に`task_id`を渡す(`entry.project is project`のように、開いているプロジェクトのタスクだけ):

```python
OverdueRow(
    entry.label,
    assignee_label(task),
    limit,
    tuple(task.assignee_names),
    predicted.end if predicted else None,
    task_id=task.id if entry.project is project else "",
)
```

`StartDelayRow`・`DueRow`も同様。`_start_delay_rows`に`project`が渡っていなければ、引数に足して呼び出し側(`summarize_progress`内の 1 か所)から渡す。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard.py test/test_dashboard_references.py test/test_dashboard_backlog.py -q`
Expected: PASS(既存のテストが壊れていない)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: ダッシュボードの遅れ・着工遅れ・期限の行にタスク id を持たせる(要望 168 段階 1)"
```

---

### Task 5: ダッシュボードの右クリック`アサイン...`(`dashboard_view.py`)

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`DashboardView.__init__` 602 行付近、遅れの行 1166 行付近、`start_delay_list` 1189 行、`期限とマイルストーン` 1974 行付近、担当なし・警告のチップ 1238〜1255 行)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `OverdueRow.task_id`・`StartDelayRow.task_id`・`DueRow.task_id`・`UnassignedTask.id`・`WarningTask.id`(Task 4)
- Produces:
  - `DashboardView(..., on_assign_screen: Callable[[str], object] | None = None, assignable: Callable[[str], bool] | None = None)`
  - `DashboardView.assign_menu(element: ui.element, task_id: str, marker: str) -> None`: `task_id`が空・コールバックなし・`assignable`が偽のときは何も付けない。付けるときは、`element`に`ui.context_menu()`を付け、`アサイン...`の項目(マーカーは`marker`)を置く

- [ ] **Step 1: テストを書く**

`test/test_dashboard_view.py`に足す(`mount`の`DashboardView(...)`にコールバックを渡せるよう、`mount`に`assign_screens: list[str] | None = None`と`assignable`の引数を足す。既存の`try_changes`の足し方に合わせる):

```python
async def test_due_rows_get_an_assign_item_that_opens_the_screen(user: User) -> None:
    opened: list[str] = []
    views, _, _ = mount(assign_screens=opened)
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-due-0")
    user.find(marker="dashboard-due-assign-0").click()
    assert opened == [sample_due_task_id]  # sample() の期限の行のタスク id に置き換える


async def test_no_assign_item_for_tasks_that_are_not_assignable(user: User) -> None:
    opened: list[str] = []
    views, _, _ = mount(assign_screens=opened, assignable=lambda task_id: False)
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-due-0")
    await user.should_not_see(marker="dashboard-due-assign-0")


async def test_assign_menu_skips_an_empty_task_id(user: User) -> None:
    opened: list[str] = []
    views, _, _ = mount(assign_screens=opened)
    await user.open("/")
    with ui.column() as box:
        views[0].assign_menu(box, "", "x-assign")  # 参照先のタスクは task_id が空
    await user.should_not_see(marker="x-assign")
```

(`sample()`と`show`の引数は既存のテストに合わせる。`sample_due_task_id`は、`sample()`が作る期限の行のタスク id に置き換える。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_view.py -k assign -v`
Expected: FAIL

- [ ] **Step 3: 実装する**

`DashboardView.__init__`に、`on_assign`の隣へ足す:

```python
        on_assign_screen: Callable[[str], object] | None = None,
        assignable: Callable[[str], bool] | None = None,
```

```python
        self.on_assign_screen = on_assign_screen
        self.assignable = assignable
```

メソッドを足す(`edit_toggle`の近く):

```python
    def assign_menu(self, element: ui.element, task_id: str, marker: str) -> None:
        """タスク名の行・チップの右クリックに`アサイン...`を付ける(要望 168)。対象外のタスクには付けない。"""
        if not task_id or self.on_assign_screen is None:
            return
        if self.assignable is not None and not self.assignable(task_id):
            return
        handler = self.on_assign_screen
        with element, ui.context_menu():
            ui.menu_item("アサイン...", on_click=lambda t=task_id: handler(t)).mark(
                marker
            )
```

各行に付ける(行の`with ui.row()...`の要素を変数に取り、その行で呼ぶ):

- 遅れの行(1166 行付近): `with ui.row().classes(...) as line:`のあとに`self.assign_menu(line, row.task_id, f"dashboard-overdue-assign-{index}")`
- `start_delay_list`: 同様に`f"dashboard-start-delay-assign-{index}"`
- 期限とマイルストーンの行(1974 行付近): `f"dashboard-due-assign-{index}"`
- 担当なしのチップ(1238 行付近): `chip`に`self.assign_menu(chip, task.id, f"dashboard-unassigned-assign-{index}")`
- 警告のチップ(1250 行付近): `f"dashboard-warning-assign-{index}"`

(行を`as line`に取るために、各`with ui.row()...:`を読んで最小の変更にする。表示は変えない。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_view.py -q`
Expected: PASS(新しい 3 件と既存)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: ダッシュボードの行の右クリックに アサイン... を足す(要望 168 段階 1)"
```

---

### Task 6: `MainView`の配線と、確定・Undo

**Files:**
- Modify: `src/projectapp/views.py`(`DashboardView(...)`の生成 690 行付近、`assign_from_dashboard` 1828 行の近く)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `AssignScreen`(Task 3)・`is_assignable`・`apply_trial`(Task 1)・`DashboardView(on_assign_screen=..., assignable=...)`(Task 5)
- Produces: `MainView.open_assign_screen(task_id: str) -> None`・`MainView.assign_screen: AssignScreen | None`

- [ ] **Step 1: テストを書く**

`test/test_views.py`の`open_dashboard_view`・`open_dashboard`(3275〜3305 行)を使う。この`open_dashboard_view`のタスク「設計」は、期限(`planned_end`が 10/9)が今週にあるので、`期限とマイルストーン`に行が出る。

```python
async def test_assign_screen_confirm_writes_back_and_undo_restores_in_one_step(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    task_id = view.project.tasks[0].id
    user.find(marker="dashboard-due-assign-0").click()
    await user.should_see(marker="assign-screen")
    assert view.assign_screen is not None
    view.assign_screen.trial.task.name = "詳細設計"
    user.find(marker="assign-confirm").click()
    assert view.project.task_map()[task_id].name == "詳細設計"
    view.undo()  # 実際の元に戻すの入口(views.py:999 付近の`undo`)に合わせる
    assert view.project.task_map()[task_id].name == "設計"


async def test_assign_screen_cancel_leaves_the_project_untouched(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    task_id = view.project.tasks[0].id
    user.find(marker="dashboard-due-assign-0").click()
    await user.should_see(marker="assign-cancel")
    assert view.assign_screen is not None
    view.assign_screen.trial.task.name = "変更"
    user.find(marker="assign-cancel").click()
    user.find(marker="assign-discard-yes").click()
    assert view.project.task_map()[task_id].name == "設計"
    assert view.history.can_undo is False  # 履歴に積んでいない(属性名は History の実際の名前に合わせる)


async def test_confirm_without_changes_leaves_no_undo_step(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    user.find(marker="dashboard-due-assign-0").click()
    await user.should_see(marker="assign-confirm")
    user.find(marker="assign-confirm").click()
    assert view.history.can_undo is False


async def test_confirm_notifies_when_the_task_was_deleted_meanwhile(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    user.find(marker="dashboard-due-assign-0").click()
    await user.should_see(marker="assign-confirm")
    assert view.assign_screen is not None
    view.assign_screen.trial.task.name = "変更"
    view.project.tasks.clear()
    user.find(marker="assign-confirm").click()
    await user.should_see("タスクが変わったため")


async def test_open_assign_screen_ignores_done_tasks(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    view.project.tasks[0].status = Status.DONE
    view.open_assign_screen(view.project.tasks[0].id)
    assert view.assign_screen is None
```

(`undo`・`history`の実際の名前は`views.py:999`付近と`history.py`で確かめて合わせる。最後のテストは async にして`open_dashboard_view`を使う。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -k assign_screen -v`
Expected: FAIL

- [ ] **Step 3: 実装する**

`views.py`の import に足す:

```python
from projectapp.assign_screen import AssignScreen
from projectapp.assign_trial import AssignTrial, apply_trial, is_assignable
```

`__init__`の属性に足す(`self.history = ...`の近く):

```python
        self.assign_screen: AssignScreen | None = None  # 開いているアサイン専用画面(要望 168)
```

`DashboardView(...)`の生成に足す(`on_assign=...`の隣):

```python
            on_assign_screen=self.open_assign_screen,
            assignable=self.is_assignable_task,
```

`assign_from_dashboard`の近くにメソッドを足す:

```python
    def is_assignable_task(self, task_id: str) -> bool:
        task = self.project.task_map().get(task_id)
        return task is not None and is_assignable(task)

    def open_assign_screen(self, task_id: str) -> None:
        """ダッシュボードの右クリック`アサイン...`(要望 168 段階 1)。確定するまでメインは変えない。"""
        task = self.project.task_map().get(task_id)
        if task is None or not is_assignable(task):
            ui.notify("このタスクはアサインできません", type="warning")
            return

        def confirm(trial: AssignTrial) -> None:
            # 画面を開いている間に、削除・Undo などで差し替わることがあるので、書き戻せなければ通知する
            if not apply_trial(self.project, trial):
                ui.notify("タスクが変わったため、反映しませんでした", type="warning")
                self.refresh_dashboard(sync_field=False)
                return
            self.after_edit()  # 変更があるときだけ履歴に 1 ステップ積む
            self.refresh_dashboard(sync_field=False)

        self.assign_screen = AssignScreen(
            self.project,
            task,
            self.holidays,
            confirm,
            now=self.now,
            name_width=self.gantt.name_width,
            fiscal_start_month=self.fiscal_start_month,
        )
        self.assign_screen.open()
```

(テストの`should_see("タスクが変わったため")`に合わせ、通知の文言は`タスクが変わったため、反映しませんでした`とする。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_views.py -k assign_screen -v`、続けて`uv run pytest test/test_assign_screen.py test/test_assign_trial.py test/test_dashboard_view.py -q`
Expected: PASS

- [ ] **Step 5: smoke の印を付ける**

確定→Undo のテスト(`test_assign_screen_confirm_writes_back_and_undo_restores_in_one_step`)に`@pytest.mark.smoke`を付ける(コア機能の確認。smoke は 1 分以内を保つ)。

Run: `uv run pytest -m smoke -q`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: アサイン専用画面の確定とキャンセルをメインへつなぐ(要望 168 段階 1)"
```

---

### Task 7: 仕様・構成・状態表記と最終確認

**Files:**
- Modify: `.claude/spec/dashboard.md`・`docs/development.md`・`docs/requests.md`

- [ ] **Step 1: 仕様を更新する**

`.claude/spec/dashboard.md`の、`ガントチャートで試す`の記述(31 行付近)の次に、箇条書きを 1 つ足す:

```markdown
- アサイン専用画面(要望 168 段階 1): `遅れ`・`着工遅れ`・`期限とマイルストーン`の行と、`担当なし`・`警告`のタスク名のチップを右クリックすると`アサイン...`が出る(通常で終了していないタスクだけ。まとめ・節目・参照行・参照先のタスクは出さない)。押すと全画面のダイアログを開き、そのタスク 1 件のガントチャート(読み取り専用。`日次`・`週次`・`月次`の切り替え)を出す。開いた時点のタスクのコピーを試算として持ち、`確定`でメインへ書き戻して元に戻すの 1 ステップに積む(変更がなければ積まない)。`キャンセル`・×・Esc は何も反映せず、変更があるときだけ`変更を捨てますか?`と確認する。試算は保存しない(ファイル形式は変えない)。割り当ての操作は段階 2 以降
```

- [ ] **Step 2: 構成を更新する**

`docs/development.md`のモジュール一覧に、`assign_trial.py`(試算の状態)・`assign_screen.py`(専用画面)を、他のモジュールの書き方に合わせて足す。テストの一覧にも`test_assign_trial.py`・`test_assign_screen.py`を足す。

- [ ] **Step 3: 状態表記を更新する**

`docs/requests.md`の要望 168 の`### 状態`を、`段階 1 は実装済み(PR #…。実機確認待ち)。段階 2〜5 は未着手。`に直す(PR 番号は PR を作ったあとに入れる)。

- [ ] **Step 4: 全体の確認**

Run: `uv run pytest -m smoke -q`
Expected: PASS(失敗したときに限り`uv run pytest -n auto`)

Run: `uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: ruff はエラーなし・整形後に差分があればコミットに含める・ty は既存の 9 件のまま(新しい指摘を足さない)

- [ ] **Step 5: コミットと PR**

```bash
git add -A
git commit -m "docs: アサイン専用画面(段階 1)の仕様と構成を書く(要望 168)"
git push -u origin feature/request-168-stage1
gh pr create --base develop --title "feat: アサイン専用画面の土台(要望 168 段階 1)" --body "ダッシュボードの右クリック アサイン... から、タスク 1 件の試算用の全画面ダイアログを開く。確定でメインへ反映(Undo 1 ステップ)、キャンセルで反映なし。割り当ての操作は段階 2 以降。

設計書: docs/superpowers/specs/2026-11-22-assign-screen-stage1-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR を作ったら止まる。実機確認とマージの指示を待つ。

---

## Self-Review

- **Spec coverage**: 入口(Task 4・5)・対象外のタスク(Task 1・5・6)・試算の状態(Task 1)・画面と日/週/月(Task 3)・確定の書き戻しと Undo 1 ステップ(Task 6)・キャンセルと確認(Task 3)・埋め込みの確かめ(Task 2)・テスト(各 Task)・仕様の更新(Task 7)。欠けなし。
- **Type consistency**: `AssignTrial(original, task)`・`start_trial`・`is_dirty`・`is_assignable`・`trial_project`・`apply_trial`は Task 1 の定義のまま Task 3・6 で使う。`AssignScreen(project, task, holidays, on_confirm, *, now, name_width, fiscal_start_month)`は Task 3 の定義と Task 6 の呼び出しが一致。マーカー`dashboard-{overdue,start-delay,due,unassigned,warning}-assign-{index}`は Task 5 と Task 6 のテストで一致。
- **既知の確認点**: Task 2 の`render`の`None`ガード(足りなければ最小限で直す。広がるなら設計書に戻る)・Task 4 の`DueRow`の生成箇所に`project`が渡るか・Task 6 の`undo`・`History`の属性名。いずれも実装時に実コードで確かめて合わせる手順を各 Step に書いた。
