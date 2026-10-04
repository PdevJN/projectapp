# 絞り込み(検索・担当者) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートのタスクを、タスク名の検索と担当者の選択で絞り込めるようにする。

**Architecture:** 判定は NiceGUI に依存しない純粋関数(`filtering.py`)にする。`GanttChart` が条件(`TaskFilter`)を保持し、`render` が元の番号を保ったまま一致しない行を飛ばす。検索入力と担当者の選択はスケール切替の行に置く。条件は `Project` に入れず保存しない。

**Tech Stack:** Python 3.13、NiceGUI(`ui.input` / `ui.select`、`nicegui.testing.User`)、pytest(`asyncio_mode = "auto"`)、ty。

**Spec:** `docs/superpowers/specs/2026-10-04-filtering-design.md`

## Global Constraints

- 言語は日本語。UI の文言も日本語。
- Python 3.13 以上。すべての関数に型引数と戻り値の型を書く(`uvx ty check src` が通ること)。
- コメントは3行以内。
- 検索は、タスク名への部分一致。大文字小文字を区別せず、前後の空白は取り除く。
- 検索と担当者は AND。条件が空ならすべて表示する。
- 一致しない行は描かない。`edit_task(si, ti)` に渡す番号と `mark` の名前は、元の番号のまま。
- 割り当て超過(`overallocations`)は、絞り込みにかかわらずプロジェクト全体で計算する。
- 絞り込みの状態は保存せず、編集中の判定に影響させない。
- テストは `uv run pytest -q`、型チェックは `uvx ty check src`。開始時点で 539 件が通る。
- ブランチは `feature/filtering`(`develop` から作成済み)。コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。プッシュはしない。

## Review Focus

- 検索文字列が正規表現の記号や HTML(`.*`、`<b>`)を含む → 文字どおりの部分一致で、エラーにも誤一致にもならない(Task 1)。
- 空白だけの検索(全角空白を含む) → 条件なしとして扱い、すべて表示する(Task 1)。
- 絞り込み中にスケールを切り替える → 条件を保つ(Task 2)。
- タスクが1つもないプロジェクトで条件を入れる → 「一致しない」の表示を出さない(Task 2)。
- 担当者の選択中に、そのメンバーが削除・改名される、または別のプロジェクトに替わる → 未指定に戻り、選択肢と表示が食い違わない(Task 3)。

## ファイル構成

- 新規 `src/projectapp/filtering.py`: `TaskFilter` と `matches`。NiceGUI に依存しない。
- 変更 `src/projectapp/gantt.py`: 条件の保持、描画の絞り込み、0件の表示、検索入力と担当者の選択、スクロールのリセット、`reset_filter`。
- 変更 `src/projectapp/views.py`: `open_project` で `reset_filter` を呼ぶ。
- 新規 `test/test_filtering.py`、変更 `test/test_gantt.py`、`test/test_views.py`。
- 変更 `docs/development.md`(モジュール構成)、`.claude/MEMORY.md`(作業記録)。

---

### Task 1: 絞り込み条件と判定(`filtering.py`)

**Files:**
- Create: `src/projectapp/filtering.py`
- Test: `test/test_filtering.py`

**Interfaces:**
- Consumes: `projectapp.models.Task`(`name: str`、`assignee: str | None`)。
- Produces: `TaskFilter(query: str = "", assignee: str | None = None)`(`frozen=True` のデータクラス、プロパティ `active: bool`)、`matches(task: Task, task_filter: TaskFilter) -> bool`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_filtering.py`:

```python
from projectapp.filtering import TaskFilter, matches
from projectapp.models import Task


def test_an_empty_filter_is_inactive_and_matches_everything() -> None:
    task_filter = TaskFilter()
    assert not task_filter.active
    assert matches(Task("設計"), task_filter)
    assert matches(Task("設計", assignee="田中"), task_filter)


def test_query_is_a_case_insensitive_substring_match_on_the_name() -> None:
    task = Task("API Design")
    assert matches(task, TaskFilter(query="design"))
    assert matches(task, TaskFilter(query="API"))
    assert matches(task, TaskFilter(query="i d"))
    assert not matches(task, TaskFilter(query="test"))


def test_query_is_trimmed_and_blank_means_no_condition() -> None:
    assert matches(Task("設計"), TaskFilter(query="  設計 "))
    for blank in ("", " ", "　", " 　 "):
        task_filter = TaskFilter(query=blank)
        assert not task_filter.active
        assert matches(Task("設計"), task_filter)


def test_query_is_literal_not_a_pattern_or_markup() -> None:
    assert not matches(Task("設計"), TaskFilter(query=".*"))
    assert matches(Task("a.*b"), TaskFilter(query=".*"))
    assert matches(Task("<b>太字</b>"), TaskFilter(query="<b>"))
    assert not matches(Task("bold"), TaskFilter(query="<b>"))


def test_assignee_must_match_exactly() -> None:
    task_filter = TaskFilter(assignee="田中")
    assert task_filter.active
    assert matches(Task("設計", assignee="田中"), task_filter)
    assert not matches(Task("設計", assignee="田中さん"), task_filter)
    assert not matches(Task("設計", assignee="鈴木"), task_filter)


def test_a_task_without_an_assignee_is_hidden_when_an_assignee_is_chosen() -> None:
    assert not matches(Task("設計"), TaskFilter(assignee="田中"))


def test_query_and_assignee_are_combined_with_and() -> None:
    task_filter = TaskFilter(query="設", assignee="田中")
    assert matches(Task("設計", assignee="田中"), task_filter)
    assert not matches(Task("設計", assignee="鈴木"), task_filter)
    assert not matches(Task("実装", assignee="田中"), task_filter)
```

- [ ] **Step 2: 失敗することを確認する**

Run: `uv run pytest test/test_filtering.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.filtering'`)

- [ ] **Step 3: 実装する**

`src/projectapp/filtering.py`:

```python
"""タスクの絞り込み条件と判定。NiceGUI には依存しない。"""

from dataclasses import dataclass

from projectapp.models import Task


@dataclass(frozen=True)
class TaskFilter:
    query: str = ""  # タスク名への部分一致(大文字小文字を区別しない)
    assignee: str | None = None  # None なら全員

    @property
    def active(self) -> bool:
        return bool(self.query.strip()) or self.assignee is not None


def matches(task: Task, task_filter: TaskFilter) -> bool:
    """検索と担当者の両方に合うとき True。条件が空なら常に True。"""
    if task_filter.assignee is not None and task.assignee != task_filter.assignee:
        return False
    return task_filter.query.strip().casefold() in task.name.casefold()
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_filtering.py -q && uvx ty check src`
Expected: 7 passed、`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/filtering.py test/test_filtering.py
git commit -m "絞り込み条件と判定の純粋関数を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 描画の絞り込みと0件の表示(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(import、`__init__`、`set_project`、`render`、`section_rows`、`GanttChart` に `set_filter` を追加)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `TaskFilter`、`matches`(Task 1)。
- Produces: `GanttChart.task_filter: TaskFilter`(初期値 `TaskFilter()`)、`GanttChart.set_filter(task_filter: TaskFilter) -> None`(同じ条件なら何もしない。違えば更新して `render.refresh()`)。`set_project` は条件を保ち、担当者がメンバーにいなくなったときだけ担当者を `None` にする。描画: 一致しない行を飛ばす、一致のないセクションを隠す、0件のとき `mark("no-match")` のラベルを出す。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の import に `from projectapp.filtering import TaskFilter` を足し、末尾に追記する(`mount` と同じ流儀で、`GanttChart` を取り出せる `mount_chart` を足す)。

```python
def mount_chart(
    project: Project, holidays: dict[date, str] | None = None
) -> tuple[list[GanttChart], Recorder]:
    charts: list[GanttChart] = []
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, holidays or {}, recorder.actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    return charts, recorder


def filter_project() -> Project:
    def task(name: str, assignee: str) -> Task:
        return Task(
            name,
            planned_start=datetime(2026, 10, 5, 12),
            planned_end=datetime(2026, 10, 7, 12),
            assignee=assignee,
        )

    return Project(
        "demo",
        base_date=BASE,
        members=[Member("田中"), Member("鈴木")],
        tasks=[task("調査", "田中")],
        sections=[
            Section("開発", [task("設計", "田中"), task("実装", "鈴木")]),
            Section("試験", [task("結合試験", "鈴木")]),
        ],
    )


async def test_a_query_hides_rows_that_do_not_match(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="実"))
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")
    await user.should_not_see(marker="task-0-0")
    await user.should_not_see(marker="task-1-0")


async def test_an_empty_filter_shows_every_row(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="実"))
    charts[0].set_filter(TaskFilter())
    for marker in ("task-top-0", "task-0-0", "task-0-1", "task-1-0"):
        await user.should_see(marker=marker)


async def test_original_indexes_are_kept_for_clicks_and_markers(user: User) -> None:
    charts, recorder = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(assignee="鈴木"))
    await user.should_see(marker="bar-0-1")
    await user.should_see(marker="bar-1-0")
    await user.should_not_see(marker="bar-0-0")
    user.find(marker="task-0-1").click()
    user.find(marker="bar-1-0").click()
    assert recorder.events == [("edit_task", (0, 1)), ("edit_task", (1, 0))]


async def test_query_and_assignee_are_combined(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="計", assignee="田中"))
    await user.should_see(marker="task-0-0")
    await user.should_not_see(marker="task-top-0")
    await user.should_not_see(marker="task-0-1")
    await user.should_not_see(marker="task-1-0")


async def test_a_section_without_a_match_is_hidden_with_its_add_button(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_see(marker="add-task-0")
    await user.should_not_see(marker="add-task-1")


async def test_an_empty_section_is_hidden_only_while_filtering(user: User) -> None:
    project = filter_project()
    project.sections.append(Section("空", []))
    charts, _ = mount_chart(project)
    await user.open("/")
    await user.should_see(marker="add-task-2")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="add-task-2")


async def test_the_top_add_row_stays_while_filtering(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="zzz"))
    await user.should_see(marker="add-task-top")


async def test_no_match_message_appears_only_when_nothing_matches(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    await user.should_not_see(marker="no-match")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="no-match")
    charts[0].set_filter(TaskFilter(query="zzz"))
    await user.should_see(marker="no-match")
    await user.should_see("条件に一致するタスクがありません")


async def test_no_match_message_is_not_shown_for_a_project_without_tasks(user: User) -> None:
    charts, _ = mount_chart(Project("空", base_date=BASE))
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="何か"))
    await user.should_not_see(marker="no-match")


async def test_stripes_do_not_change_while_filtering(user: User) -> None:
    charts, _ = mount_chart(overloaded_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="A"))
    a = user.find(marker="overload-top-0-0").elements.pop()
    assert (a._style["left"], a._style["width"]) == ("80.0px", "80.0px")
    await user.should_not_see(marker="bar-top-1")


async def test_the_filter_survives_a_scale_change(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="実"))
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.WEEK)
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-0-0")


async def test_set_project_keeps_the_filter_but_drops_a_vanished_assignee(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    chart = charts[0]
    chart.set_filter(TaskFilter(query="設", assignee="田中"))
    chart.set_project(filter_project())
    assert chart.task_filter == TaskFilter(query="設", assignee="田中")
    other = filter_project()
    other.members = [Member("鈴木")]
    chart.set_project(other)
    assert chart.task_filter == TaskFilter(query="設", assignee=None)
```

- [ ] **Step 2: 失敗することを確認する**

Run: `uv run pytest test/test_gantt.py -q -k "filter or hides or match or survives or vanished or filtering or empty_section or top_add"`
Expected: FAIL(`AttributeError: 'GanttChart' object has no attribute 'set_filter'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py` の import を変える。

```python
from dataclasses import dataclass, replace
```

`from projectapp.calendar import DayKind, day_kind` の下に足す。

```python
from projectapp.filtering import TaskFilter, matches
```

`__init__` の `self.scale = Scale.DAY` の下に足す。

```python
        self.task_filter = TaskFilter()
```

`set_project` を置き換え、直後に `set_filter` を足す。

```python
    def set_project(self, project: Project) -> None:
        """条件は保つ。担当者がメンバーからいなくなったときだけ、担当者の指定を外す。"""
        self.project = project
        names = {member.name for member in project.members}
        if self.task_filter.assignee not in (None, *names):
            self.task_filter = replace(self.task_filter, assignee=None)
        self.render.refresh()

    def set_filter(self, task_filter: TaskFilter) -> None:
        if task_filter == self.task_filter:
            return
        self.task_filter = task_filter
        self.render.refresh()
```

`render` の、`self.header(columns, width)` から末尾までを置き換える。

```python
                self.header(columns, width)
                self.no_match_message()
                for ti, task in enumerate(self.project.tasks):
                    if matches(task, self.task_filter):
                        self.task_row(None, ti, task, columns, width)
                self.top_add_row()
                for si, section in enumerate(self.project.sections):
                    self.section_rows(si, section, columns, width)

    def no_match_message(self) -> None:
        """絞り込み中に1件も一致しないとき(タスクが1つもないときは出さない)。"""
        tasks = self.project.all_tasks()
        if not (self.task_filter.active and tasks):
            return
        if any(matches(task, self.task_filter) for task in tasks):
            return
        ui.label("条件に一致するタスクがありません").classes("text-caption").style(
            "position: relative; padding: 8px 16px"
        ).mark("no-match")
```

`section_rows` を置き換える。

```python
    def section_rows(
        self, si: int, section: Section, columns: list[Column], width: int
    ) -> None:
        if self.task_filter.active and not any(
            matches(task, self.task_filter) for task in section.tasks
        ):
            return
        with ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE):
            ui.label(section.name).classes("text-subtitle2")
            ui.button(
                icon="add", on_click=lambda si=si: self.actions.add_task(si)
            ).props("flat dense round size=sm").tooltip("タスク追加").mark(f"add-task-{si}")
        for ti, task in enumerate(section.tasks):
            if matches(task, self.task_filter):
                self.task_row(si, ti, task, columns, width)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py -q && uvx ty check src`
Expected: すべて passed、`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "ガントチャートの描画を絞り込み条件で絞る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 検索入力・担当者の選択・スクロール・リセット(`gantt.py`)

> **改訂(2026-10-04、ユーザーの指示)**: 検索の確定は 300ms のデバウンスではなく Enter キー(IME の変換確定の Enter は無視)。入力欄が空になったときだけ、すぐ条件を外す。このタスクの検索入力に関する記述は、設計書の「決定事項」を優先する。実装は `commit_query` と `on_search_changed`、定数 `SEARCH_ENTER_JS`。

**Files:**
- Modify: `src/projectapp/gantt.py`(import、定数、`__init__`、`set_project`、`set_filter`、`build`、新規メソッド)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `GanttChart.task_filter`、`set_filter`、`set_project`(Task 2)。
- Produces: 定数 `ALL_ASSIGNEES = ""`(選択肢の「すべての担当者」の値)。`GanttChart.search_input: ui.input | None`、`assignee_select: ui.select | None`(`build` で作る。`mark("search-input")`、`mark("assignee-filter")`)。`assignee_options() -> dict[str, str]`、`sync_assignee_select() -> None`、`scroll_to_top() -> None`、`reset_filter() -> None`(条件を空にして、入力欄と選択にも反映し、再描画してスクロールを先頭へ)。`set_filter` は条件が変わったときにスクロールを先頭へ戻す(`set_project` では戻さない)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の末尾に追記する。

```python
async def test_the_search_input_filters_the_rows(user: User) -> None:
    mount_chart(filter_project())
    await user.open("/")
    await user.should_see(marker="search-input")
    user.find(marker="search-input").type("実")
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")


async def test_clearing_the_search_input_shows_every_row_again(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    box = user.find(marker="search-input").elements.pop()
    box.set_value("実")
    await user.should_not_see(marker="task-top-0")
    box.set_value(None)
    assert charts[0].task_filter == TaskFilter()
    await user.should_see(marker="task-top-0")


async def test_the_assignee_select_lists_the_members_and_filters(user: User) -> None:
    mount_chart(filter_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    assert select.options == {"": "すべての担当者", "田中": "田中", "鈴木": "鈴木"}
    assert select.value == ""
    select.set_value("鈴木")
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-top-0")
    select.set_value("")
    await user.should_see(marker="task-top-0")


async def test_set_project_updates_the_assignee_options_and_resets_a_vanished_choice(
    user: User,
) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value("田中")
    other = filter_project()
    other.members = [Member("鈴木"), Member("佐藤")]
    charts[0].set_project(other)
    assert select.options == {"": "すべての担当者", "鈴木": "鈴木", "佐藤": "佐藤"}
    assert select.value == ""
    assert charts[0].task_filter.assignee is None


async def test_set_project_keeps_a_chosen_assignee_that_still_exists(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    select = user.find(marker="assignee-filter").elements.pop()
    select.set_value("鈴木")
    charts[0].set_project(filter_project())
    assert select.value == "鈴木"
    assert charts[0].task_filter.assignee == "鈴木"


async def test_reset_filter_clears_the_inputs_and_shows_every_row(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="search-input").elements.pop().set_value("実")
    user.find(marker="assignee-filter").elements.pop().set_value("鈴木")
    charts[0].reset_filter()
    assert charts[0].task_filter == TaskFilter()
    assert user.find(marker="search-input").elements.pop().value == ""
    assert user.find(marker="assignee-filter").elements.pop().value == ""
    await user.should_see(marker="task-top-0")
    await user.should_see(marker="task-1-0")


async def test_changing_the_filter_scrolls_to_the_top_but_set_project_does_not(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    calls: list[str] = []
    monkeypatch.setattr(charts[0], "scroll_to_top", lambda: calls.append("scroll"))
    charts[0].set_filter(TaskFilter(query="実"))
    charts[0].set_filter(TaskFilter(query="実"))  # 同じ条件では動かない
    assert calls == ["scroll"]
    charts[0].set_project(filter_project())
    assert calls == ["scroll"]
    charts[0].reset_filter()
    assert calls == ["scroll", "scroll"]
```

`test/test_gantt.py` の import に `import pytest` を足す(先頭の `import asyncio` の下)。

- [ ] **Step 2: 失敗することを確認する**

Run: `uv run pytest test/test_gantt.py -q -k "search_input or assignee or reset_filter or scrolls"`
Expected: FAIL(`search-input` が見つからない、`reset_filter` がない)

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py` の import を変える。

```python
from nicegui import context, ui
```

定数を足す(`ADD_ROW_STYLE` の下)。

```python
ALL_ASSIGNEES = ""  # 担当者の選択で「すべて」を表す値。メンバー名は空にできない
```

`__init__` の `self.task_filter = TaskFilter()` の下に足す。

```python
        self.search_input: ui.input | None = None
        self.assignee_select: ui.select | None = None
        self.client: Client | None = None
```

import は `from nicegui import Client, context, ui` に変える(上の `from nicegui import context, ui` の代わり)。

`set_project` を置き換え、`set_filter` を置き換え、新しいメソッドを足す。

```python
    def set_project(self, project: Project) -> None:
        """条件は保つ。担当者がメンバーからいなくなったときだけ、担当者の指定を外す。"""
        self.project = project
        names = {member.name for member in project.members}
        if self.task_filter.assignee not in (None, *names):
            self.task_filter = replace(self.task_filter, assignee=None)
        self.sync_assignee_select()
        self.render.refresh()

    def set_filter(self, task_filter: TaskFilter) -> None:
        if task_filter == self.task_filter:
            return
        self.task_filter = task_filter
        self.render.refresh()
        self.scroll_to_top()

    def reset_filter(self) -> None:
        """条件を空に戻し、入力欄と選択にも反映する。別のプロジェクトを開いたときに使う。"""
        self.task_filter = TaskFilter()
        if self.search_input is not None:
            self.search_input.set_value("")
        if self.assignee_select is not None:
            self.assignee_select.set_value(ALL_ASSIGNEES)
        self.render.refresh()
        self.scroll_to_top()

    def assignee_options(self) -> dict[str, str]:
        options = {ALL_ASSIGNEES: "すべての担当者"}
        options.update({member.name: member.name for member in self.project.members})
        return options

    def sync_assignee_select(self) -> None:
        if self.assignee_select is not None:
            value = self.task_filter.assignee or ALL_ASSIGNEES
            self.assignee_select.set_options(self.assignee_options(), value=value)

    def scroll_to_top(self) -> None:
        if self.client is not None:
            self.client.run_javascript("window.scrollTo({top: 0})")
```

`build` を置き換える。

```python
    def build(self) -> None:
        self.client = context.client
        with ui.row().classes("w-full items-center gap-4"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).mark("scale-toggle")
            ui.button("セクション追加", icon="add", on_click=self.actions.add_section).props(
                "flat"
            ).mark("add-section")
            self.search_input = (
                ui.input(
                    placeholder="タスク名で検索",
                    value=self.task_filter.query,
                    on_change=lambda e: self.set_filter(
                        replace(self.task_filter, query=e.value or "")
                    ),
                )
                .props("clearable dense outlined debounce=300")
                .classes("w-64")
                .mark("search-input")
            )
            self.assignee_select = (
                ui.select(
                    self.assignee_options(),
                    value=self.task_filter.assignee or ALL_ASSIGNEES,
                    on_change=lambda e: self.set_filter(
                        replace(
                            self.task_filter,
                            assignee=None if e.value == ALL_ASSIGNEES else e.value,
                        )
                    ),
                )
                .props("dense outlined")
                .classes("w-48")
                .mark("assignee-filter")
            )
        self.render()
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py -q && uvx ty check src`
Expected: すべて passed、`All checks passed!`
`ty` が `self.client` や `set_options` の型で失敗したら、型注釈を直す(`# type: ignore` で黙らせない)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "検索入力と担当者の選択を追加し、絞り込み変更でスクロールを先頭へ戻す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: プロジェクトを開いたときのリセットと文書(`views.py`、`docs`)

**Files:**
- Modify: `src/projectapp/views.py:117-129`(`open_project`)、`docs/development.md`(モジュール構成の表)、`.claude/MEMORY.md`
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `GanttChart.reset_filter()`、`set_filter`、`task_filter`(Task 2・3)、`MainView.apply_members`、`MainView.open_project`。
- Produces: `open_project` が、`gantt.set_project` のあとに `gantt.reset_filter()` を呼ぶ。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の import に `from projectapp.filtering import TaskFilter` を足し、`test_choosing_in_the_combo_opens_a_clean_project_at_once` の下に追記する。

```python
async def test_opening_a_project_resets_the_filter_but_editing_keeps_it(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", members=[Member("田中")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.gantt.set_filter(TaskFilter(query="設"))
    view.apply_members([Member("鈴木")], {})
    assert view.gantt.task_filter == TaskFilter(query="設")
    assert view.is_dirty()  # メンバーの変更は編集中になる(条件は関係しない)
    view.open_project("既存")
    assert view.gantt.task_filter == TaskFilter()
    assert user.find(marker="search-input").elements.pop().value == ""


async def test_the_filter_does_not_make_the_project_dirty(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    assert not view.is_dirty()
    view.gantt.set_filter(TaskFilter(query="設", assignee=None))
    assert not view.is_dirty()
```

- [ ] **Step 2: 失敗することを確認する**

Run: `uv run pytest test/test_views.py -q -k "filter"`
Expected: 1つ目が FAIL(`open_project` のあとも `task_filter` が `TaskFilter(query="設")` のまま)。2つ目は通る(判定に影響しないことの確認)。

- [ ] **Step 3: 実装する**

`src/projectapp/views.py` の `open_project` の末尾を変える。

```python
        self.title.refresh()
        self.gantt.set_project(self.project)
        self.gantt.reset_filter()
```

`docs/development.md` の表に行を足し、`gantt.py` の行を直す。

```markdown
| `filtering.py` | 絞り込み条件(`TaskFilter`)とタスクの判定(`matches`)(純粋関数) |
| `gantt.py` | ガントチャートの描画とスケール切替、検索・担当者の絞り込み |
```

(`gantt.py` の既存の行を、2行目の文言で置き換える。`filtering.py` の行は `timeline.py` の行の下に足す。)

`.claude/MEMORY.md` に、絞り込みの設計書・実装計画・実装済みの内容(実機確認はまだ)を、次のサブプロジェクト(ドラッグ&ドロップ)への申し送りとともに、既存の書き方に合わせて追記する。

- [ ] **Step 4: すべてを確認する**

Run: `uv run pytest --cov=projectapp -q && uvx ty check src`
Expected: すべて passed(539 件 + 追加分)、`All checks passed!`

- [ ] **Step 5: 実機で確認する**

Run: `uv run projectapp`
確認する項目:
- 検索入力に文字を打つと、約0.3秒後に行が絞られ、一致の先頭が一番上に来る。クリアボタンで戻る。
- 担当者の選択で絞れる。検索との AND になる。
- 一致なしで「条件に一致するタスクがありません」が出る。セクションなしの「タスク追加」は残る。
- 縦に長いチャートでスクロールしてから絞り込むと、先頭に戻る。
- 日次・週次・月次の切替で、条件が保たれる。
- メンバーの削除・改名後、選択中の担当者が消えると「すべての担当者」に戻る。
- 別のプロジェクトを開くと、検索欄と担当者が空に戻る。
- ライト・ダークの両方で、入力欄と選択の見た目が崩れない。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/views.py test/test_views.py docs/development.md .claude/MEMORY.md
git commit -m "プロジェクトを開いたときに絞り込み条件を空に戻す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
