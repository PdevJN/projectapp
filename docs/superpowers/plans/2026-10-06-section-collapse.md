# セクションの折りたたみ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートのセクション見出しで、タスク行を折りたたみ・展開できるようにする(要望 19)。

**Architecture:** 状態は `GanttChart.collapsed: set[int]`(セクションの添字)で持ち、保存しない。描く行の決定は、NiceGUI に依存しない純粋関数 `visible_task_indexes`(`filtering.py`)に切り出す。絞り込み中と読み取り専用(プレビュー)は、折りたたみを無視する。`MainView` は、折りたたみ中のセクションへタスクを追加したら展開し、プロジェクトを開き直したら全展開に戻す。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-06-section-collapse-design.md`

## Global Constraints

- 言語は日本語(画面の文言・コメント・コミットメッセージ)。識別子は英語。
- Python 3.13 以上。外部ライブラリは足さない。
- 折りたたみ状態は保存しない(ファイル形式・`config.json` は変えない)。
- 名前の欄の幅 `NAME_WIDTH_PX`(200)と行の高さは変えない。
- 日付に依存するテストは `base_date` を固定する。
- 全体テストは約 5.5 分かかる。時間制限(`timeout`)を付けず、バックグラウンドで実行し、`done` の行まで待つ。型チェックは `uvx ty check src`。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- ブランチは `feature/section-collapse`(作成済み)。マージとプッシュは、許可を得てから行う。

## Review Focus

- 件数 0 のセクション(空)を折りたたむ・開く: 落ちず、見出しに `(0)` が出る。
- 折りたたみ中のセクションで、絞り込みに一致するタスクがない: 見出しごと隠れる(今のとおり)。解除すると、折りたたみのまま戻る。
- セクションのないタスク(最上段)は、折りたたみの影響を受けない。
- 折りたたみ中の見出しでも、タスク追加ボタンとドロップ先(`data-drop`)が残る。
- プレビューを開いて戻っても、折りたたみ状態が変わらない。

---

## ファイル構成

- 変更: `src/projectapp/filtering.py` — 純粋関数 `visible_task_indexes` を足す。
- 変更: `src/projectapp/gantt.py` — `collapsed`・`toggle_section`・`expand_section`・`reset_collapsed`、`section_rows` の見出し(矢印・件数)と行の選択。
- 変更: `src/projectapp/views.py` — `save_task` で展開、`open_project` で全展開に戻す。
- 変更: `test/test_filtering.py`、`test/test_gantt.py`、`test/test_views.py`
- 変更: `docs/development.md`、`README.md`、`.claude/MEMORY.md`(記録)

---

### Task 1: 純粋関数と、チャートの開閉・描画

**Files:**
- Modify: `src/projectapp/filtering.py`
- Modify: `src/projectapp/gantt.py`(`__init__`、`section_rows`、`reset_filter` の近くにメソッド追加)
- Test: `test/test_filtering.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: `TaskFilter`、`matches`(`filtering.py`)、`Section`(`models.py`)、`ViewOptions.read_only`
- Produces:
  - `visible_task_indexes(section: Section, task_filter: TaskFilter, collapsed: bool) -> list[int]`
  - `GanttChart.collapsed: set[int]`
  - `GanttChart.toggle_section(si: int) -> None`(切り替えて再描画)
  - `GanttChart.expand_section(si: int) -> None`(`discard` だけ。再描画はしない)
  - `GanttChart.reset_collapsed() -> None`(`clear` だけ。再描画はしない)
  - マーカー: `section-toggle-{si}`(矢印ボタン)、`section-count-{si}`(件数ラベル。テキストは `(n)`)

- [ ] **Step 1: 純粋関数の失敗するテストを書く**

`test/test_filtering.py` の先頭の import を次に変え、末尾にテストを足す。

```python
from projectapp.filtering import TaskFilter, matches, visible_task_indexes
from projectapp.models import Section, Task
```

```python
def section_of_three() -> Section:
    return Section(
        "開発",
        [Task("設計", assignee="田中"), Task("実装", assignee="鈴木"), Task("試験", assignee="田中")],
    )


def test_an_expanded_section_shows_every_task() -> None:
    assert visible_task_indexes(section_of_three(), TaskFilter(), collapsed=False) == [0, 1, 2]


def test_a_collapsed_section_shows_no_task() -> None:
    assert visible_task_indexes(section_of_three(), TaskFilter(), collapsed=True) == []


def test_an_active_filter_ignores_the_collapse() -> None:
    task_filter = TaskFilter(assignee="田中")
    assert visible_task_indexes(section_of_three(), task_filter, collapsed=True) == [0, 2]
    assert visible_task_indexes(section_of_three(), task_filter, collapsed=False) == [0, 2]


def test_an_active_filter_with_no_match_shows_nothing() -> None:
    assert visible_task_indexes(section_of_three(), TaskFilter(query="zzz"), collapsed=True) == []


def test_an_empty_section_shows_nothing() -> None:
    assert visible_task_indexes(Section("空"), TaskFilter(), collapsed=False) == []
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_filtering.py -q`
Expected: FAIL(`ImportError: cannot import name 'visible_task_indexes'`)

- [ ] **Step 3: 純粋関数を書く**

`src/projectapp/filtering.py` の import を `from projectapp.models import Section, Task` に変え、末尾に足す。

```python
def visible_task_indexes(section: Section, task_filter: TaskFilter, collapsed: bool) -> list[int]:
    """セクションで描くタスクの添字。絞り込み中は折りたたみを無視し、一致したものだけを返す。"""
    if task_filter.active:
        return [i for i, task in enumerate(section.tasks) if matches(task, task_filter)]
    return [] if collapsed else list(range(len(section.tasks)))
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_filtering.py -q`
Expected: PASS

- [ ] **Step 5: チャートの失敗するテストを書く**

`test/test_gantt.py` の `filter_project` の定義より後(`test_a_query_hides_rows_that_do_not_match` の前)に足す。`filter_project` は、セクション 0(開発: 設計・実装)、セクション 1(試験: 結合試験)、最上段のタスク「調査」を持つ。

```python
async def test_the_arrow_collapses_and_expands_a_section(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-0").click()
    await user.should_not_see(marker="task-0-0")
    await user.should_not_see(marker="task-0-1")
    await user.should_see(marker="task-1-0")  # 別のセクションは変わらない
    user.find(marker="section-toggle-0").click()
    await user.should_see(marker="task-0-0")
    await user.should_see(marker="task-0-1")
    assert charts[0].collapsed == set()


async def test_clicking_the_section_name_toggles_it(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-label-0").click()
    await user.should_not_see(marker="task-0-0")
    assert charts[0].collapsed == {0}


async def test_the_header_shows_the_task_count_open_or_collapsed(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    count = lambda si: user.find(marker=f"section-count-{si}").elements.pop().text  # noqa: E731
    assert count(0) == "(2)"
    assert count(1) == "(1)"
    user.find(marker="section-toggle-0").click()
    assert count(0) == "(2)"


async def test_a_collapsed_header_keeps_the_add_button(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-0").click()
    await user.should_see(marker="add-task-0")
    user.find(marker="add-task-0").click()
    assert charts[0].collapsed == {0}  # 追加ボタンは開閉しない


async def test_a_collapsed_header_stays_a_drop_target(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-0").click()
    props = user.find(marker="section-0").elements.pop()._props
    assert props["data-drop"] == "section"


async def test_a_filter_opens_collapsed_sections_and_clearing_it_collapses_again(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-0").click()
    charts[0].set_filter(TaskFilter(query="実"))
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="task-0-0")
    assert charts[0].collapsed == {0}  # 絞り込みでは変えない
    charts[0].set_filter(TaskFilter())
    await user.should_not_see(marker="task-0-0")
    await user.should_not_see(marker="task-0-1")


async def test_a_filter_with_no_match_hides_a_collapsed_section_header(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-1").click()
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="section-1")
    charts[0].set_filter(TaskFilter())
    await user.should_see(marker="section-1")
    await user.should_not_see(marker="task-1-0")


async def test_collapsing_does_not_touch_top_level_tasks(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-0").click()
    user.find(marker="section-toggle-1").click()
    await user.should_see(marker="task-top-0")


async def test_an_empty_section_can_be_collapsed_and_expanded(user: User) -> None:
    project = filter_project()
    project.sections.append(Section("空", []))
    charts, _ = mount_chart(project)
    await user.open("/")
    assert user.find(marker="section-count-2").elements.pop().text == "(0)"
    user.find(marker="section-toggle-2").click()
    user.find(marker="section-toggle-2").click()
    assert charts[0].collapsed == set()
    await user.should_see(marker="add-task-2")


async def test_read_only_shows_every_row_without_arrows_and_keeps_the_state(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    user.find(marker="section-toggle-0").click()
    charts[0].set_options(ViewOptions(read_only=True))
    await user.should_see(marker="task-0-0")
    await user.should_see(marker="task-0-1")
    await user.should_not_see(marker="section-toggle-0")
    assert user.find(marker="section-count-0").elements.pop().text == "(2)"
    charts[0].set_options(ViewOptions())
    await user.should_not_see(marker="task-0-0")
    assert charts[0].collapsed == {0}


async def test_expand_and_reset_clear_the_state_without_drawing(user: User) -> None:
    charts, _ = mount_chart(filter_project())
    await user.open("/")
    charts[0].toggle_section(0)
    charts[0].toggle_section(1)
    charts[0].expand_section(0)
    assert charts[0].collapsed == {1}
    charts[0].reset_collapsed()
    assert charts[0].collapsed == set()
```

- [ ] **Step 6: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "collapse or section_name or task_count or drop_target or opens_collapsed or no_match_hides or top_level or empty_section_can or read_only_shows or expand_and_reset"`
Expected: FAIL(`section-toggle-0` が見つからない、`collapsed` 属性がない)

- [ ] **Step 7: チャートの状態とメソッドを足す**

`src/projectapp/gantt.py`:

1. import に `visible_task_indexes` を足す(`from projectapp.filtering import TaskFilter, matches` の行を `from projectapp.filtering import TaskFilter, matches, visible_task_indexes` にする。実際の import の書き方に合わせる)。
2. `GanttChart.__init__` の `self.task_filter = TaskFilter()` の次の行に足す。

```python
        self.collapsed: set[int] = set()  # 折りたたんだセクションの添字。保存しない
```

3. `reset_filter` メソッドの直前に足す。

```python
    def toggle_section(self, si: int) -> None:
        """セクションの折りたたみを切り替えて、描き直す。"""
        self.collapsed.symmetric_difference_update({si})
        self.render.refresh()

    def expand_section(self, si: int) -> None:
        """セクションを展開する(描き直しは、呼び出し側のあとの処理に任せる)。"""
        self.collapsed.discard(si)

    def reset_collapsed(self) -> None:
        """すべて展開に戻す(描き直しは、呼び出し側のあとの処理に任せる)。"""
        self.collapsed.clear()
```

- [ ] **Step 8: 見出しと行の選択を書き換える**

`section_rows` の冒頭の絞り込み判定を、次に置き換える(現在の `if self.task_filter.active and not any(...): return` の 4 行)。

```python
        collapsed = si in self.collapsed and not self.options.read_only
        visible = visible_task_indexes(section, self.task_filter, collapsed)
        if self.task_filter.active and not visible:
            return
```

見出しの `with name.mark(...)` ブロックの中を、次に置き換える(ラベルの前に矢印、後ろに件数を足す。追加ボタンは今のまま)。

```python
            with name.mark(f"section-name-{si}"):
                if not self.options.read_only:
                    arrow = "chevron_right" if collapsed else "expand_more"
                    ui.button(
                        icon=arrow, on_click=lambda si=si: self.toggle_section(si)
                    ).props("flat dense round size=sm").classes("shrink-0").mark(
                        f"section-toggle-{si}"
                    )
                label = ui.label(section.name).classes("text-subtitle2 ellipsis")
                label.style("min-width: 0; padding-left: 4px")  # 長い名前は縮めて、ボタンを残す
                label.tooltip(section.name).mark(f"section-label-{si}")
                if not self.options.read_only:
                    label.classes("cursor-pointer").on("click", lambda si=si: self.toggle_section(si))
                ui.label(f"({len(section.tasks)})").classes("text-caption shrink-0").mark(
                    f"section-count-{si}"
                )
                if not self.options.read_only:
                    ui.button(
                        icon="add", on_click=lambda si=si: self.actions.add_task(si)
                    ).props("flat dense round size=sm").classes("shrink-0").tooltip(
                        "タスク追加"
                    ).mark(f"add-task-{si}")
```

末尾のタスク行のループを、次に置き換える。

```python
        for ti in visible:
            self.task_row(si, ti, section.tasks[ti], columns, width)
```

(`matches` は `render` の最上段のタスクでまだ使うので、import は残す。)

- [ ] **Step 9: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py test/test_filtering.py test/test_gantt_drag.py -q`
Expected: PASS(新しいテストと、既存のテストの両方)。落ちた既存のテストがあれば、見出しの要素の増加(矢印・件数)が原因かを確認して直す。

- [ ] **Step 10: 型チェックとコミット**

Run: `uvx ty check src`
Expected: `All checks passed!`

```bash
git add src/projectapp/filtering.py src/projectapp/gantt.py test/test_filtering.py test/test_gantt.py
git commit -m "セクションの折りたたみ: 純粋関数と、チャートの開閉・件数の表示

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 画面(MainView)との接続とドキュメント

**Files:**
- Modify: `src/projectapp/views.py`(`save_task`、`open_project`)
- Test: `test/test_views.py`
- Modify: `docs/development.md`、`README.md`、`.claude/MEMORY.md`

**Interfaces:**
- Consumes: `GanttChart.expand_section(si)`、`GanttChart.reset_collapsed()`、`GanttChart.toggle_section(si)`、`GanttChart.collapsed`(Task 1)
- Produces: なし

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の末尾に足す(`planned_task`・`mount_capturing`・`save_cache`・`save_project` は、このファイルにある)。

```python
async def test_adding_a_task_to_a_collapsed_section_expands_it(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    await user.should_not_see(marker="task-0-0")
    view.save_task(0, None, planned_task())
    assert view.gantt.collapsed == set()
    await user.should_see(marker="task-0-1")


async def test_editing_a_task_keeps_the_section_collapsed(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    view.save_task(0, 0, planned_task())
    assert view.gantt.collapsed == {0}


async def test_adding_a_top_level_task_keeps_collapsed_sections(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    view.save_task(None, None, planned_task())
    assert view.gantt.collapsed == {0}


async def test_opening_a_project_expands_every_section(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元", [planned_task()])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("今の", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    view.open_project("既存")
    assert view.gantt.collapsed == set()
    await user.should_see(marker="task-0-0")


async def test_collapsing_is_not_an_edit(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.mark_clean()
    view.gantt.toggle_section(0)
    assert not view.is_dirty()


async def test_the_preview_shows_a_collapsed_section_and_returns_to_it(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.project.sections.append(Section("開発", [planned_task()]))
    view.gantt.set_project(view.project)
    view.gantt.toggle_section(0)
    await user.should_not_see(marker="task-0-0")
    user.find(marker="export-preview").click()
    await user.should_see(marker="task-0-0")
    await user.should_not_see(marker="section-toggle-0")
    view.exit_preview()
    await user.should_not_see(marker="task-0-0")
    assert view.gantt.collapsed == {0}
```

先頭の import に `Section`・`date` がなければ足す(`grep -n "^from\|^import" test/test_views.py` で確認する)。`view.mark_clean` / `view.is_dirty` は、既存のテストで使われている。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k "collapsed or expands_every or collapsing_is_not or preview_shows_a_collapsed"`
Expected: FAIL(`test_adding_a_task_to_a_collapsed_section_expands_it` と `test_opening_a_project_expands_every_section` が落ちる。ほかは、今のコードでも通る場合がある)

- [ ] **Step 3: `views.py` を直す**

`save_task` の `self.gantt.set_project(self.project)` の直前に足す。

```python
        if task_index is None and section_index is not None:
            self.gantt.expand_section(section_index)  # 追加したタスクが見えるように
```

`open_project` の `self.gantt.set_project(self.project)` の直前に足す。

```python
        self.gantt.reset_collapsed()  # 折りたたみは保存しない。別のプロジェクトは全展開から始める
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_views.py -q -k "collapsed or expands_every or collapsing_is_not or preview_shows_a_collapsed"`
Expected: PASS

- [ ] **Step 5: ドキュメントを直す**

- `docs/development.md`:
  - `filtering.py` の行を「絞り込み条件(`TaskFilter`)とタスクの判定(`matches`)、セクションで描くタスクの決定(`visible_task_indexes`)(純粋関数)」に変える。
  - `gantt.py` の行に「セクションの折りたたみ」を足す。
  - 設計書の表(`絞り込み・ドラッグ操作` の行の近く)に、`セクションの折りたたみ | 2026-10-06-section-collapse-design.md` を足す。実装計画の表があれば、同様に `2026-10-06-section-collapse.md` を足す。
  - 「ファイル形式の注意」の近くに 1 項目足す: 折りたたみ(`GanttChart.collapsed`、添字の集合)は保存しない。セクションの並べ替え・削除を足すときは、同時に添字をずらすこと。
- `README.md`: 「操作」の行(27 行目付近)に「セクション見出しの矢印で、タスクを折りたたむ」を足す。
- `CLAUDE.md`(`projectapp/CLAUDE.md`): 「ガントチャート」の節に 1 行足す: `ガントチャート`の`セクション`は、見出しの矢印か名前のクリックで折りたためる。見出しにタスク件数を出す。絞り込み中は折りたたみを無視して、一致したタスクを出す。折りたたみは保存しない。「データの保存先」の `絞り込み(検索・担当者)とプレビューの設定は保存しない` の行は `絞り込み(検索・担当者)・セクションの折りたたみ・プレビューの設定は保存しない` に変える。
- `.claude/MEMORY.md`: 要望 19 を `(完了)` にし、現在の状況の要約と各作業の記録に、折りたたみの実装(ブランチ・方式・テスト数)を足す。実機の確認待ちの項目に「セクションの折りたたみ(矢印・件数・絞り込み・プレビュー)」を足す。

- [ ] **Step 6: 全体のテストと型チェック**

Run(バックグラウンド。`done` の行まで待つ): `uv run pytest -q 2>&1 | tail -15; echo done`
Expected: すべて PASS(1,034 件 + 新しいテスト)

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/views.py test/test_views.py docs README.md CLAUDE.md .claude/MEMORY.md
git commit -m "セクションの折りたたみ: 追加で展開・開き直しで全展開・ドキュメント

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** 状態の持ち方・保存しない(Task 1・2)、矢印と名前のクリック(Task 1)、件数(Task 1)、追加ボタンは開閉しない・追加で展開(Task 1・2)、絞り込み中は無視(Task 1)、プレビューは全展開で矢印なし・状態は残る(Task 1・2)、ドロップ先が残る(Task 1)、純粋関数(Task 1)、開き直しで全展開(Task 2)。ドキュメントと注意(添字のずれ)は Task 2 の Step 5。
- **Placeholder scan:** なし。
- **Type consistency:** `visible_task_indexes(section, task_filter, collapsed)`、`toggle_section` / `expand_section` / `reset_collapsed`、マーカー `section-toggle-{si}` / `section-count-{si}` は、全タスクで一致。
- **Review Focus:** 空のセクション・一致なし・最上段のタスク・見出しのドロップ先と追加ボタン・プレビューの往復を、Task 1・2 のテストが押さえる。
