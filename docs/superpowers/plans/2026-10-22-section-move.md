# セクションの並べ替え(ドラッグ) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートのセクションの見出しをドラッグして、同じ親の兄弟のあいだで並べ替えられるようにする。

**Architecture:** 並べ替えと折りたたみの付け替えは、`arrange.py` の純粋関数にする。ブラウザ側は `gantt_drag.py` の JS に専用の drag 種別でセクションのドラッグを足し、`chart_move_section` で `GanttChart.handle_move_section` へ送る。反映は `views.py` の `move_section`(`copy_section`・`delete_section` と同じ流れ)で、履歴は `after_edit` が積む。

**Tech Stack:** Python 3.13、NiceGUI(`ui.on`・`emitEvent`)、pytest(`nicegui.testing.User`)、ty、uv。

**Spec:** `docs/superpowers/specs/2026-10-22-section-move-design.md`

## Global Constraints

- すべての関数に型ヒントを付ける(引数と戻り値)。型は `ty` で検証する。
- コメントは多くても 3 行以内。PEP8。
- 言語は日本語(コメント・通知・ドキュメント)。
- ファイル形式の `version` は変えない(保存するデータは変わらない)。
- 動かせるのは同じ親の兄弟の中だけ。絞り込み中とプレビュー(読み取り専用)では動かせない。
- 中のタスク・サブセクションの `id` と中身は変えない。折りたたみの状態はセクションに付けたまま動かす。
- テストは `test/`(`tests/` ではない)。実行は `uv run pytest test/<file> -q`。
- `ty check src/projectapp` の指摘数(802 件)は、変更の前後で増やさない。
- コマンドは `&&` でつなぐ(`;` だとテストが落ちてもコミットまで進む)。ブランチは `feature/section-move`。

## Review Focus

- 先頭のセクションを末尾へ、末尾を先頭へ動かす(端の番号)。
- 3 階層目のサブセクションを、同じ親の中で動かす(`(0, 1, 2)` のような深いパス)。
- 親が違う見出し(別のセクションのサブセクション、root とサブセクション)への落下は、何も変えない。
- 自分自身の見出しへ落とす・存在しない番号・不正な値は、何も変えず、履歴も積まない。
- 折りたたんだセクションと、その子孫が折りたたまれている状態で動かす。動かしたあとも、同じセクションが折りたたまれたままになる。
- タスクの行のドラッグ(行の移動・セクションへの追加)が、今までどおり動く。

---

### Task 1: 並べ替えの純粋関数(`arrange.py`)

**Files:**
- Modify: `src/projectapp/arrange.py`(`delete_section` の後ろに `move_section`・`reorder_collapsed`、`parse_shift` の後ろに `parse_section_move`)
- Test: `test/test_section_menu.py`(`remap_collapsed` のテストの後ろに足す)

**Interfaces:**
- Produces:
  - `arrange.move_section(project: Project, path: SectionPath, to_index: int) -> bool`
  - `arrange.reorder_collapsed(collapsed: set[SectionPath], parent: SectionPath, src: int, dst: int) -> set[SectionPath]`
  - `arrange.parse_section_move(args: object) -> tuple[SectionPath, SectionPath] | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_section_menu.py` の末尾(`test_every_section_header_opens_the_section_menu_on_right_click` の後ろ)に足す。

```python
def three_roots() -> Project:
    """root に A・B・C。A の中にサブセクション x・y・z(z の中に孫 w)。"""
    return Project(
        "p",
        sections=[
            Section(
                "A",
                [Task("ta", id="ta")],
                [Section("x", id="x"), Section("y", id="y"), Section("z", [], [Section("w", id="w")], id="z")],
                id="A",
            ),
            Section("B", [Task("tb", id="tb")], id="B"),
            Section("C", id="C"),
        ],
    )


def names(sections: list[Section]) -> list[str]:
    return [s.name for s in sections]


@pytest.mark.parametrize(
    ("path", "to_index", "expected"),
    [
        ((0,), 2, ["B", "C", "A"]),  # 先頭を末尾へ
        ((2,), 0, ["C", "A", "B"]),  # 末尾を先頭へ
        ((0,), 1, ["B", "A", "C"]),
        ((1,), 0, ["B", "A", "C"]),
    ],
)
def test_move_section_reorders_the_roots(path, to_index, expected) -> None:  # noqa: ANN001
    project = three_roots()
    assert arrange.move_section(project, path, to_index) is True
    assert names(project.sections) == expected


def test_move_section_reorders_subsections_and_keeps_contents_and_ids() -> None:
    project = three_roots()
    assert arrange.move_section(project, (0, 0), 2) is True
    parent = project.sections[0]
    assert names(parent.sections) == ["y", "z", "x"]
    assert [s.id for s in parent.sections] == ["y", "z", "x"]
    assert [t.name for t in parent.tasks] == ["ta"]
    assert names(parent.sections[1].sections) == ["w"]  # 孫は z に付いたまま


def test_move_section_reorders_a_third_level_section() -> None:
    project = Project("p", sections=[Section("A", [], [Section("B", [], [Section("c1"), Section("c2")])])])
    assert arrange.move_section(project, (0, 0, 1), 0) is True
    assert names(project.sections[0].sections[0].sections) == ["c2", "c1"]


@pytest.mark.parametrize(
    ("path", "to_index"),
    [((1,), 1), ((0,), 3), ((0,), -1), ((5,), 0), ((), 0), ((0, 9), 0), ((9, 0), 0), ((0, 0), 3)],
)
def test_move_section_returns_false_and_changes_nothing_for_a_noop_or_bad_target(path, to_index) -> None:  # noqa: ANN001
    project = three_roots()
    before = deepcopy(project)
    assert arrange.move_section(project, path, to_index) is False
    assert project == before


@pytest.mark.parametrize(
    ("paths", "parent", "src", "dst", "expected"),
    [
        ({(0,), (1,), (2,)}, (), 0, 2, {(2,), (0,), (1,)}),  # 先頭を末尾へ: 動かした分は 2 に、間は 1 つ前へ
        ({(2,)}, (), 2, 0, {(0,)}),  # 末尾を先頭へ
        ({(1,)}, (), 0, 2, {(0,)}),  # 間の兄弟は 1 つ前へ
        ({(1,)}, (), 2, 0, {(2,)}),  # 間の兄弟は 1 つ後ろへ
        ({(3,)}, (), 0, 2, {(3,)}),  # 範囲の外は変えない
        ({(0, 1, 0), (0, 2)}, (0,), 1, 2, {(0, 2, 0), (0, 1)}),  # 子孫は動かしたセクションに付いていく
        ({(1, 0), (2,)}, (0,), 0, 1, {(1, 0), (2,)}),  # 別の親は変えない
        ({(0,)}, (), 1, 1, {(0,)}),  # 同じ位置は何も変えない
    ],
)
def test_reorder_collapsed_follows_the_moved_sections(paths, parent, src, dst, expected) -> None:  # noqa: ANN001
    assert arrange.reorder_collapsed(paths, parent, src, dst) == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"src": "0", "dst": "2"}, ((0,), (2,))),
        ({"src": "0.1", "dst": "0.2"}, ((0, 1), (0, 2))),
        ({"src": "0.1.2", "dst": "0.1.0"}, ((0, 1, 2), (0, 1, 0))),
        ({"src": "0", "dst": "0.1"}, None),  # 親が違う
        ({"src": "0.1", "dst": "1.1"}, None),
        ({"src": "top", "dst": "0"}, None),  # root(タスク側)は動かせない
        ({"src": "0", "dst": "top"}, None),
        ({"src": "0", "dst": 2}, None),
        ({"src": "x", "dst": "0"}, None),
        ({"src": "0"}, None),
        ("0", None),
        (None, None),
    ],
)
def test_parse_section_move_accepts_only_siblings(args, expected) -> None:  # noqa: ANN001
    assert arrange.parse_section_move(args) == expected
```

あわせて、ファイルの先頭の import に `from copy import deepcopy` を足す(`from datetime import datetime` の上)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_section_menu.py -q -k "move_section or reorder_collapsed or parse_section_move"`
Expected: FAIL(`AttributeError: module 'projectapp.arrange' has no attribute 'move_section'`)

- [ ] **Step 3: 実装する**

`src/projectapp/arrange.py` の `delete_section` の後ろ(`remap_collapsed` の前)に足す。

```python
def move_section(project: Project, path: SectionPath, to_index: int) -> bool:
    """セクションを、同じ親の一覧の to_index の位置へ移す。範囲外・同じ位置なら何もせず False。"""
    if not path or (len(path) > 1 and section_at(project, path[:-1]) is None):
        return False
    siblings = _sections_list(project, path)
    index = path[-1]
    if not (0 <= index < len(siblings) and 0 <= to_index < len(siblings)) or index == to_index:
        return False
    siblings.insert(to_index, siblings.pop(index))
    return True


def reorder_collapsed(
    collapsed: set[SectionPath], parent: SectionPath, src: int, dst: int
) -> set[SectionPath]:
    """兄弟の src を dst へ移したぶん、折りたたみのパスを付け替える(子孫は動かしたセクションに付く)。"""
    result: set[SectionPath] = set()
    depth = len(parent)
    for path in collapsed:
        if len(path) <= depth or path[:depth] != parent:
            result.add(path)
            continue
        number = path[depth]
        if number == src:
            number = dst
        elif src < number <= dst:
            number -= 1
        elif dst <= number < src:
            number += 1
        result.add((*parent, number, *path[depth + 1 :]))
    return result
```

`parse_shift` の後ろ(ファイル末尾)に足す。

```python
def parse_section_move(args: object) -> tuple[SectionPath, SectionPath] | None:
    """セクションのドロップ。両方がセクションのパスで、同じ親の兄弟のときだけ通す。"""
    if not isinstance(args, dict):
        return None
    src = parse_section(args.get("src"))
    dst = parse_section(args.get("dst"))
    if not src or not dst or src[:-1] != dst[:-1]:
        return None
    return src, dst
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_section_menu.py -q`
Expected: すべて PASS(既存のテストも)

- [ ] **Step 5: 型を確かめてコミット**

```bash
uv run ty check src/projectapp 2>&1 | tail -3
git add src/projectapp/arrange.py test/test_section_menu.py
git commit -m "feat: セクションの並べ替えと、折りたたみの付け替えの純粋関数を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Expected: ty の指摘数が 802 件のまま(増えていない)。

---

### Task 2: ドラッグの受け取りと反映(`gantt_drag.py`・`gantt.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/gantt_drag.py`(`CHART_DRAG_JS` にセクションのドラッグを足す)
- Modify: `src/projectapp/gantt.py`(`GanttActions` に `move_section`、`GanttChart` に `handle_move_section`・`reorder_collapsed`、`ui.on("chart_move_section")`、見出しの属性)
- Modify: `src/projectapp/views.py`(`GanttActions(...)` の組み立てと `move_section`)
- Test: `test/test_gantt.py`(`Recorder` に `move_section`)、`test/test_gantt_drag.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `arrange.move_section`・`reorder_collapsed`・`parse_section_move`、既存の `arrange.section_key`・`GanttChart.drag_props`・`section_at`。
- Produces:
  - `GanttActions.move_section: Callable[[SectionPath, SectionPath], object]`(元, 落とした先の見出し。既定は何もしない)
  - `GanttChart.handle_move_section(args: object) -> None`
  - `GanttChart.reorder_collapsed(parent: SectionPath, src: int, dst: int) -> None`
  - `MainView.move_section(src: SectionPath, dst: SectionPath) -> None`
  - 見出しの属性: ヘッダーの行に `data-parent=<親のキー>`(`top` か`0`など)、名前の欄(マーカー `section-name-<キー>`)に `draggable=true`・`data-section-handle`・`data-si`・`data-parent`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の `Recorder` の `GanttActions(...)` に 1 行足す(`delete_section=` の次)。

```python
            move_section=lambda src, dst: self.events.append(("move_section", (src, dst))),
```

`test/test_gantt_drag.py` の `test_the_script_has_the_name_width_pieces` の前に足す。`project_with_top()` は root のセクションが 2 つ(`開発`・`空`)。

```python
async def test_section_name_cells_are_draggable_handles_with_their_parent(user: User) -> None:
    mount(project_with_top())
    await user.open("/")
    name = props_of(user, "section-name-0")
    assert name["draggable"] == "true"
    assert "data-section-handle" in name
    assert (name["data-si"], name["data-parent"]) == ("0", "top")
    assert props_of(user, "section-0")["data-parent"] == "top"  # 落とし先の見出しも親を持つ


async def test_nested_section_headers_know_their_parent(user: User) -> None:
    project = Project("demo", base_date=BASE, sections=[Section("親", [], [Section("子", [])])])
    mount(project)
    await user.open("/")
    assert props_of(user, "section-name-0.0")["data-parent"] == "0"
    assert props_of(user, "section-0.0")["data-parent"] == "0"


async def test_no_section_drag_attributes_while_filtering(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_not_see(marker="task-top-0")  # 描画し直しを待つ
    name = props_of(user, "section-name-0")
    assert "draggable" not in name
    assert "data-section-handle" not in name


async def test_handle_move_section_passes_sibling_drops_to_the_action(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_move_section({"src": "0", "dst": "1"})
    assert recorder.events == [("move_section", ((0,), (1,)))]


async def test_handle_move_section_ignores_bad_events_other_parents_and_filtering(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_move_section({"src": "0", "dst": "0.1"})  # 親が違う
    charts[0].handle_move_section({"src": "x", "dst": "1"})
    charts[0].handle_move_section(None)
    charts[0].set_filter(TaskFilter(query="設計"))
    charts[0].handle_move_section({"src": "0", "dst": "1"})
    assert recorder.events == []


async def test_handle_move_section_is_ignored_in_read_only(user: User) -> None:
    recorder = Recorder()
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(
            project_with_top(), {}, recorder.actions, now=lambda: datetime(2026, 10, 1),
            options=ViewOptions(read_only=True),
        )
        charts.append(chart)
        chart.build()

    await user.open("/")
    charts[0].handle_move_section({"src": "0", "dst": "1"})
    assert recorder.events == []
    assert "draggable" not in props_of(user, "section-name-0")


def test_reorder_collapsed_follows_the_moved_sections() -> None:
    chart = GanttChart(project_with_top(), {}, Recorder().actions)
    chart.collapsed = {(0,), (1, 0)}
    chart.reorder_collapsed((), 0, 1)
    assert chart.collapsed == {(1,), (0, 0)}
```

同じファイルの `test_the_script_emits_the_events_the_python_side_listens_to` の後ろに足す。

```python
def test_the_script_has_the_section_drag_pieces() -> None:
    assert 'emitEvent("chart_move_section"' in CHART_DRAG_JS
    assert "application/x-gantt-section" in CHART_DRAG_JS
    assert "data-section-handle" in CHART_DRAG_JS
```

同じファイルの import に `ViewOptions` を足す(`from projectapp.gantt import GanttChart` を `from projectapp.gantt import GanttChart, ViewOptions` にする)。

`test/test_views.py` の `test_adding_a_subsection_through_the_dialog` の前(`open_nested_view` の定義の後ろ)に足す。`open_nested_view` は root に `親`(中に`子`)を持つ。

```python
async def open_two_sections_view(user: User, tmp_path: Path) -> MainView:
    view = await open_nested_view(user, tmp_path)
    view.project.sections.append(Section("兄弟", [Task("s0")]))
    view.gantt.set_project(view.project)
    return view


async def test_move_section_reorders_marks_dirty_and_undoes_in_one_step(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    view.history.clear()
    view.committed = deepcopy(view.project)
    view.move_section((1,), (0,))
    assert [s.name for s in view.project.sections] == ["兄弟", "親"]
    assert view.is_dirty()
    view.undo()
    assert [s.name for s in view.project.sections] == ["親", "兄弟"]
    view.redo()
    assert [s.name for s in view.project.sections] == ["兄弟", "親"]


async def test_move_section_carries_the_collapsed_state_with_the_section(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})  # 親とその子が折りたたみ
    view.move_section((0,), (1,))
    assert [s.name for s in view.project.sections] == ["兄弟", "親"]
    assert view.gantt.collapsed == {(1,), (1, 0)}


async def test_move_section_ignores_other_parents_and_noops_without_a_history_step(user: User, tmp_path: Path) -> None:
    view = await open_two_sections_view(user, tmp_path)
    before = deepcopy(view.project)
    steps = len(view.history.undo_stack) if hasattr(view.history, "undo_stack") else None
    view.move_section((1,), (0, 0))  # 親が違う
    view.move_section((0,), (0,))  # 同じ位置
    view.move_section((0,), (9,))  # 範囲外
    view.move_section((), (0,))
    assert view.project == before
    if steps is not None:
        assert len(view.history.undo_stack) == steps
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt_drag.py test/test_views.py -q -k "section"`
Expected: FAIL(`TypeError: GanttActions.__init__() got an unexpected keyword argument 'move_section'` など)

(`view.history` の中身の属性名が違えば、`test_views.py` の最後のテストの `steps` の取り方は、`grep -n "class History" -A12 src/projectapp/history.py` で確認して合わせる。履歴の件数を読める手段がなければ、`view.undo()` を呼んで `view.project == before` を確かめる形に書き換える。)

- [ ] **Step 3: 実装する(`gantt.py`)**

`GanttActions` の `delete_section` の次に足す。

```python
    move_section: Callable[[SectionPath, SectionPath], object] = lambda src, dst: None  # 元, 落とした先の見出し(同じ親)
```

`GanttChart.handle_move` の後ろ(`after_folded_children` の前)に足す。

```python
    def handle_move_section(self, args: object) -> None:
        """セクションの見出しのドロップを受ける。絞り込み中・読み取り専用・同じ親でない・不正な値は無視する。"""
        if self.task_filter.active or self.options.read_only:
            return
        parsed = arrange.parse_section_move(args)
        if parsed is not None and all(arrange.valid_section(self.project, p) for p in parsed):
            self.actions.move_section(*parsed)
```

`remap_collapsed` メソッドの後ろに足す。

```python
    def reorder_collapsed(self, parent: SectionPath, src: int, dst: int) -> None:
        """セクションの並べ替えで番号がずれたぶん、折りたたみの状態を付け替える(再描画は呼び出し側)。"""
        self.collapsed = arrange.reorder_collapsed(self.collapsed, parent, src, dst)
```

`ui.on("chart_move", ...)` の次の行に足す。

```python
        ui.on("chart_move_section", lambda e: self.handle_move_section(e.args))
```

`section_rows` の中の、`header.props(self.drag_props("section", key, count=len(section.tasks)))` を次に変える。

```python
        parent_key = section_key(path[:-1])
        header.props(self.drag_props("section", key, count=len(section.tasks), parent=parent_key))
```

同じ関数で、`with name.mark(f"section-name-{key}"):` の直前(`name.style(...)` の後ろ)に足す。

```python
            if not self.options.read_only and not self.task_filter.active:  # つかんで動かせるのは、絞り込みなし・編集時だけ
                name.props(f"draggable=true data-section-handle data-si={key} data-parent={parent_key}")
```

(`name.style(...)` は複数行の式なので、その閉じ括弧の後ろ、`with name.mark(...)` の前に置く。)

- [ ] **Step 4: 実装する(`gantt_drag.py`)**

`CHART_DRAG_JS` の `const ROW_TYPE = ...` の次の行に足す。

```javascript
  const SECTION_TYPE = "application/x-gantt-section";  // セクションの見出しの drag
  let sectionSource = null;  // {si, parent}
```

`isRowDrag` の次に足す。

```javascript
  const isSectionDrag = (event) => Array.from((event.dataTransfer || {}).types || []).includes(SECTION_TYPE);
  const sectionTarget = (event) => {  // 同じ親の、別の見出しだけ落とせる
    const el = event.target.closest ? event.target.closest('[data-drop="section"]') : null;
    const ok = el && sectionSource && el.dataset.parent === sectionSource.parent && el.dataset.si !== sectionSource.si;
    return ok ? el : null;
  };
```

`dragstart` のリスナーで、`const handle = event.target.closest ? ...` の直前に足す。

```javascript
    const sectionHandle = event.target.closest ? event.target.closest("[data-section-handle]") : null;
    if (sectionHandle) {
      sectionSource = { si: sectionHandle.dataset.si, parent: sectionHandle.dataset.parent };
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData(SECTION_TYPE, "1");
      event.dataTransfer.setData("text/plain", sectionHandle.textContent || "");
      return;
    }
```

`drop` のリスナーの後ろ、`dragend` のリスナーの前に足す。

```javascript
  document.addEventListener("dragover", (event) => {
    if (!sectionSource || !isSectionDrag(event)) return;
    clearMarks();
    const el = sectionTarget(event);
    if (!el) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    el.classList.add("drop-into");
  });

  document.addEventListener("drop", (event) => {
    if (!sectionSource || !isSectionDrag(event)) return;
    const el = sectionTarget(event);
    if (!el) return;
    event.preventDefault();
    const message = { src: sectionSource.si, dst: el.dataset.si };
    clearMarks();
    sectionSource = null;
    emitEvent("chart_move_section", message);
  });
```

既存の `dragend` のリスナーを次に変える。

```javascript
  document.addEventListener("dragend", () => {
    clearMarks();
    source = null;
    sectionSource = null;
  });
```

- [ ] **Step 5: 実装する(`views.py`)**

`GanttActions(...)` を組み立てている箇所の `delete_section=self.confirm_delete_section,` の次に足す。

```python
                move_section=self.move_section,
```

`delete_section` メソッドの後ろ(`apply_decompose` の前)に足す。

```python
    def move_section(self, src: SectionPath, dst: SectionPath) -> None:
        """セクションを、同じ親の dst の位置へ動かす。親が違う・変化なしなら何もしない(履歴も積まない)。"""
        if not src or not dst or src[:-1] != dst[:-1]:
            return
        if arrange.move_section(self.project, src, dst[-1]):
            self.gantt.reorder_collapsed(src[:-1], src[-1], dst[-1])
            self.after_edit()
```

- [ ] **Step 6: 通ることを確かめる**

Run: `uv run pytest test/test_gantt_drag.py test/test_gantt.py test/test_section_menu.py test/test_views.py test/test_history.py -q -n auto`
Expected: すべて PASS

- [ ] **Step 7: 型を確かめてコミット**

```bash
uv run ty check src/projectapp 2>&1 | tail -3
git add src/projectapp/gantt_drag.py src/projectapp/gantt.py src/projectapp/views.py test/test_gantt.py test/test_gantt_drag.py test/test_views.py
git commit -m "feat: セクションの見出しをドラッグして、同じ親の中で並べ替える

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Expected: ty の指摘数が 802 件のまま。

---

### Task 3: 仕様書・記録の更新と全体の確認

**Files:**
- Modify: `CLAUDE.md`(プロジェクトの仕様。サブセクションの記述と、セクションの見出しの節)
- Modify: `docs/superpowers/specs/2026-10-22-section-move-design.md`(状態)
- Modify: `docs/superpowers/README.md`(索引に 1 行)
- Modify: `.claude/MEMORY.md`(現在の状況に 1 項目)

- [ ] **Step 1: `CLAUDE.md` を直す**

`CLAUDE.md`(プロジェクト直下)で、次の語句を探して置き換える。

```text
改名・コピー・削除は、見出しの右クリックのメニューでできる。移動はできない）
```
を
```text
改名・コピー・削除は、見出しの右クリックのメニューでできる。並べ替えは、見出しのドラッグでできる）
```
に。

`ガントチャートのセクションの見出し(1〜3 階層すべて)を右クリックすると` で始まる箇条書きの末尾(`プレビューでは出さない。`の後ろ)に、次の文を足す。

```text
セクションの並べ替え: 見出しの名前の欄をつかんで、同じ親の兄弟の見出しに落とすと、その位置に入る(上へ動かせばその手前、下へ動かせばその後ろ。落とせる見出しは枠線で囲む)。中のタスク・サブセクションは一緒に動き、折りたたみの状態はセクションに付いて動く。別の親・階層へは移せない。絞り込み中とプレビューでは動かせない。元に戻せる。
```

- [ ] **Step 2: 設計書の状態と索引・記録を更新する**

設計書の先頭の `> **状態**:` の行を `> **状態**: 実装済み(2026-10-22。実機確認待ち)— 番号のない要望 — \`feature/section-move\`。現在の仕様は [\`CLAUDE.md\`](../../../CLAUDE.md) に反映済み。` にする。

`docs/superpowers/README.md` の索引の表の末尾に 1 行足す(列は他の行と同じ。PR 番号はマージ後に直す)。

```markdown
| 2026-10-22 | セクションの並べ替え(ドラッグ) | [設計](specs/2026-10-22-section-move-design.md) | [計画](plans/2026-10-22-section-move.md) | — | 未マージ(`feature/section-move`) | — |
```

`.claude/MEMORY.md` の「現在の状況」の先頭の箇条書きの次に足す。

```markdown
- 2026-10-22: セクションの並べ替え(ドラッグ。番号のない要望)を`feature/section-move`で実装。設計書`2026-10-22-section-move-design.md`・計画`2026-10-22-section-move.md`(native 方式)。同じ親の中だけ。実機確認と PR は未了。
```

- [ ] **Step 3: 全体を確かめる**

```bash
uv run pytest -n auto -q 2>&1 | tail -5
uv run ty check src/projectapp 2>&1 | tail -3
git status -sb | head
```

Expected: テストがすべて PASS。ty の指摘数は 802 件のまま。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-10-22-section-move-design.md docs/superpowers/README.md .claude/MEMORY.md
git commit -m "docs: セクションの並べ替えを仕様書と記録に反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: 実機確認を頼む(ネイティブ)**

`git branch --show-current` が `feature/section-move` であることを確かめてから、ユーザーに次の項目の確認を頼む(`uv run` で起動)。

1. 見出しをつかんで、同じ親の別の見出しへ落とすと、その位置に入る(上へ・下へ)。落とせる見出しが枠線で囲まれる。
2. 親が違う見出し(サブセクションと root のセクション)の上では、枠線が出ず、落とせない。
3. 折りたたんだセクションを動かしても、折りたたみのまま。子孫の折りたたみも付いてくる。
4. 元に戻す(`Cmd+Z`)で 1 回で戻る。やり直しもできる。
5. 絞り込み中とプレビューでは動かせない。
6. タスクの行のドラッグ(行の移動・`Alt` でコピー・セクションの見出しへ落として追加)、見出しのクリック(折りたたみ)・ダブルクリック(名前だけのタスク)・右クリックのメニュー、名前の欄の右端の幅の調整が、今までどおり動く。
7. ダークテーマで枠線が見える。
