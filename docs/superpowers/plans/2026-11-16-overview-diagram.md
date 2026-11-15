# 俯瞰図(系統図)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** セクションとまとめの配下の階層を、ツリー状の図としてダイアログに出し、PDF にも書き出せるようにする(要望 147)。

**Architecture:** 階層の変換と座標の計算は、NiceGUI に依存しない純粋関数(`overview.py`)にする。画面(`overview_dialog.py`)と PDF(`overview_pdf.py`)は、同じ座標を使って描く。入口は、ガントチャートの右クリックメニューの`俯瞰図…`で、`GanttActions`のコールバック経由で`views.py`が開く。

**Tech Stack:** Python 3.13、NiceGUI 4、Pillow(PDF 化)、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-15-overview-diagram-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・docstring)。Python 3.13 以上。
- 描画は NiceGUI の要素と CSS による自前描画。外部のライブラリは増やさない(PDF は既存依存の Pillow だけ)。
- 日時・座標の計算は、NiceGUI から切り離した純粋関数にする(`overview.py`は`nicegui`を import しない)。
- ファイル形式は変えない(`version`は上げない)。チェックボックスの状態は保存しない。
- プレビュー(読み取り専用)では、右クリックメニュー自体を出さない(既存と同じ)。
- Web モードでは、PDF の保存を通知で断る(`self.exporter.available`が偽のとき)。
- `refreshable`の中でダイアログを作らない。開くたびに作るダイアログは`disposable(...)`で包む。
- 実装の完了時の確認の順: `uv run pytest -m smoke` → `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`(既存の 9 件以外が増えないこと)。smoke が失敗したときに限り`uv run pytest -n auto`。
- マージは利用者の指示を待つ(PR を作って止まる)。コミットの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。

## Review Focus

- 配下が空のセクション: 根のノード 1 つだけの図になり、落ちない(Task 1 のテスト)。
- まとめの子が、セクション直下にも重ねて出ない(まとめの子は、まとめの下だけに出す)(Task 1)。
- 工数が 0 や未入力・進捗の対象がないとき: 進捗・工数の行は出さず、`None`や 0 で割らない(Task 1・2)。
- 名前が長い・日本語・絵文字のとき: ノードの幅に収まり、PDF でも欠けない(Task 3)。
- 日本語フォントが見つからない環境: PDF を作らず、通知で理由を出す。既存のファイルを壊さない(Task 3・5)。
- 1000 ノード級の図: 座標の計算が一瞬で終わり、重ならない(Task 2)。
- 折りたたまれたセクション・まとめの中のタスクへ移る: 展開してからスクロールする(Task 4)。

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `src/projectapp/overview.py`(新規) | `OverviewNode`・`build_overview`・`node_lines`・`layout_overview`。純粋関数 |
| `src/projectapp/overview_pdf.py`(新規) | `find_font`・`render_pdf`(Pillow)。NiceGUI に依存しない |
| `src/projectapp/overview_dialog.py`(新規) | `open_overview_dialog`。図の描画・チェックボックス・PDF ボタン |
| `src/projectapp/gantt.py`(変更) | `GanttActions`に 2 つ足す。セクション・まとめのメニュー項目。`reveal_task` |
| `src/projectapp/views.py`(変更) | `open_overview_section`・`open_overview_summary`・PDF の書き出し |
| `test/test_overview.py`(新規) | Task 1・2 のテスト |
| `test/test_overview_pdf.py`(新規) | Task 3 のテスト |
| `test/test_overview_view.py`(新規) | Task 4・5 のテスト(メニュー・ダイアログ・ジャンプ) |
| `.claude/spec/gantt.md`・`docs/requests.md`・`docs/development.md`(変更) | Task 6 |

---

### Task 1: 階層の変換(`build_overview`)

**Files:**
- Create: `src/projectapp/overview.py`
- Test: `test/test_overview.py`

**Interfaces:**
- Consumes: `Project`・`Section`・`Task`・`TaskKind`・`Status`(`projectapp.models`)、`parent_map`・`children_of`・`summary_status`(`projectapp.summary`)、`Schedule`・`effective_end`・`is_overdue`(`projectapp.timeline`)、`_progress_weight`(`projectapp.dashboard`)
- Produces:
  - `class NodeKind(StrEnum)`: `SECTION`・`SUMMARY`・`TASK`・`CHECKPOINT`・`REFERENCE`
  - `@dataclass class OverviewNode`: `id: str`・`name: str`・`kind: NodeKind`・`status: Status`・`late: bool`・`progress: int | None`・`effort_hours: float | None`・`due: datetime | None`・`children: list[OverviewNode]`・`first_task_id: str | None`(クリックで移る先。タスク・まとめは自分の id、セクションは中の最初のタスクの id か`None`)
  - `build_overview(project: Project, holidays: dict[date, str], now: datetime, *, section_path: SectionPath | None = None, summary_id: str | None = None) -> OverviewNode`(どちらか一方だけを渡す。両方・どちらもなしは`ValueError`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_overview.py`:

```python
from datetime import datetime

import pytest

from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.overview import NodeKind, build_overview

NOW = datetime(2026, 10, 1)


def sample() -> Project:
    return Project(
        "demo",
        sections=[
            Section(
                "開発",
                [
                    Task("設計", id="a", effort_hours=8.0, status=Status.DONE),
                    Task(
                        "実装",
                        id="s",
                        kind=TaskKind.SUMMARY,
                        children=["c1", "c2"],
                    ),
                    Task("実装1", id="c1", effort_hours=4.0, progress=50),
                    Task("実装2", id="c2", effort_hours=12.0),
                ],
                sections=[Section("テスト", [Task("結合", id="t", effort_hours=2.0)])],
            ),
            Section("空", []),
        ],
    )


def test_a_section_becomes_a_tree_of_sections_summaries_and_tasks() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(0,))
    assert (root.name, root.kind) == ("開発", NodeKind.SECTION)
    # まとめの子は、まとめの下だけに出す(セクション直下には出さない)
    assert [(c.name, c.kind) for c in root.children] == [
        ("設計", NodeKind.TASK),
        ("実装", NodeKind.SUMMARY),
        ("テスト", NodeKind.SECTION),
    ]
    summary = root.children[1]
    assert [c.name for c in summary.children] == ["実装1", "実装2"]


def test_summary_root_shows_only_its_children() -> None:
    root = build_overview(sample(), {}, NOW, summary_id="s")
    assert (root.name, root.kind) == ("実装", NodeKind.SUMMARY)
    assert [c.id for c in root.children] == ["c1", "c2"]


def test_progress_is_weighted_by_effort_and_done_counts_as_100() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(0,))
    done, summary, _ = root.children
    assert done.progress == 100
    # 実装1(4h・50%)と実装2(12h・0%): (4*50)/(4+12) = 12.5 → 13(四捨五入)
    assert summary.progress == 13
    assert summary.effort_hours == 16.0


def test_empty_section_is_a_single_node() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(1,))
    assert root.children == []
    assert root.progress is None and root.first_task_id is None


def test_section_first_task_id_points_to_the_first_task_inside() -> None:
    root = build_overview(sample(), {}, NOW, section_path=(0,))
    assert root.first_task_id == "a"


def test_checkpoint_has_no_effort_and_is_left_out_of_progress() -> None:
    project = Project(
        "p",
        sections=[
            Section("S", [Task("節目", id="k", kind=TaskKind.CHECKPOINT)]),
        ],
    )
    root = build_overview(project, {}, NOW, section_path=(0,))
    assert root.children[0].kind is NodeKind.CHECKPOINT
    assert root.children[0].effort_hours is None
    assert root.progress is None


def test_exactly_one_of_section_path_and_summary_id_is_required() -> None:
    with pytest.raises(ValueError):
        build_overview(sample(), {}, NOW)
    with pytest.raises(ValueError):
        build_overview(sample(), {}, NOW, section_path=(0,), summary_id="s")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_overview.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.overview`)

- [ ] **Step 3: 最小の実装を書く**

`src/projectapp/overview.py`:

```python
"""俯瞰図(系統図)の、階層の変換と座標の計算。NiceGUI には依存しない純粋関数。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from projectapp.dashboard import _progress_weight
from projectapp.models import (
    Project,
    Section,
    SectionPath,
    Status,
    Task,
    TaskKind,
)
from projectapp.summary import children_of, parent_map, summary_status
from projectapp.timeline import Schedule, effective_end, is_overdue


class NodeKind(StrEnum):
    SECTION = "セクション"
    SUMMARY = "まとめ"
    TASK = "タスク"
    CHECKPOINT = "チェックポイント"
    REFERENCE = "プロジェクト参照"


@dataclass
class OverviewNode:
    id: str
    name: str
    kind: NodeKind
    status: Status
    late: bool = False  # 予定超過・期限超過(赤)
    progress: int | None = None  # 0〜100。出せないときは None
    effort_hours: float | None = None
    due: datetime | None = None
    children: list["OverviewNode"] = field(default_factory=list)
    first_task_id: str | None = None  # クリックで移る先のタスク


_KINDS = {
    TaskKind.SUMMARY: NodeKind.SUMMARY,
    TaskKind.CHECKPOINT: NodeKind.CHECKPOINT,
    TaskKind.REFERENCE: NodeKind.REFERENCE,
}


def _percent(tasks: list[Task]) -> int | None:
    """配下の通常タスクの、工数で重みづけした進捗率。数えるものがなければ None。"""
    pairs = [
        pair
        for task in tasks
        if task.kind is TaskKind.TASK  # まとめ・参照・節目は、二重に数えない
        if (pair := _progress_weight(task)) is not None
    ]
    total = sum(weight for weight, _ in pairs)
    if not pairs or total <= 0:
        return None
    return round(sum(weight * percent for weight, percent in pairs) / total)


def _hours(tasks: list[Task]) -> float | None:
    values = [t.total_effort for t in tasks if t.kind is TaskKind.TASK]
    return sum(values) if values else None


class _Builder:
    def __init__(
        self, project: Project, holidays: dict[date, str], now: datetime
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.now = now
        self.by_id = project.task_map()
        self.in_summary = set(parent_map(project))
        self.schedule = Schedule(project, holidays)

    def task_node(self, task: Task) -> OverviewNode:
        kind = _KINDS.get(task.kind, NodeKind.TASK)
        late = is_overdue(task, self.project, self.holidays, self.now, self.schedule)
        due = effective_end(task, self.project, self.holidays, self.schedule)
        if task.kind is TaskKind.SUMMARY:
            kids = children_of(task, self.by_id)
            node = OverviewNode(
                task.id,
                task.name,
                kind,
                summary_status(kids),
                late,
                _percent(kids),
                _hours(kids),
                due,
                [self.task_node(kid) for kid in kids],
                task.id,
            )
            return node
        percent = None
        if task.kind is TaskKind.TASK and (pair := _progress_weight(task)):
            percent = round(pair[1])
        return OverviewNode(
            task.id,
            task.name,
            kind,
            task.status,
            late,
            percent,
            task.total_effort if task.kind is TaskKind.TASK else None,
            due,
            [],
            task.id,
        )

    def section_node(self, section: Section) -> OverviewNode:
        tasks = section.all_tasks()
        # セクション直下のタスクのうち、まとめの子は、まとめの下だけに出す
        children = [
            self.task_node(task)
            for task in section.tasks
            if task.id not in self.in_summary
        ] + [self.section_node(child) for child in section.sections]
        leaves = [t for t in tasks if t.kind is TaskKind.TASK]
        return OverviewNode(
            section.id,
            section.name,
            NodeKind.SECTION,
            summary_status(leaves) if leaves else Status.NOT_STARTED,
            False,
            _percent(tasks),
            _hours(tasks),
            None,
            children,
            tasks[0].id if tasks else None,
        )


def build_overview(
    project: Project,
    holidays: dict[date, str],
    now: datetime,
    *,
    section_path: SectionPath | None = None,
    summary_id: str | None = None,
) -> OverviewNode:
    """セクション(パスで指す)かまとめ(id で指す)の配下を、ツリーにする。どちらか一方だけを渡す。"""
    if (section_path is None) == (summary_id is None):
        raise ValueError("section_path か summary_id のどちらか一方だけを渡してください")
    builder = _Builder(project, holidays, now)
    if summary_id is not None:
        task = builder.by_id.get(summary_id)
        if task is None or task.kind is not TaskKind.SUMMARY:
            raise ValueError(f"まとめが見つかりません: {summary_id}")
        return builder.task_node(task)
    assert section_path is not None
    section = project.sections
    node: Section | None = None
    for index in section_path:
        node = section[index]
        section = node.sections
    if node is None:
        raise ValueError("セクションのパスが空です")
    return builder.section_node(node)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_overview.py -v`
Expected: PASS(失敗した場合は、`Project`・`Task`のコンストラクタの引数名を`src/projectapp/models.py`で確かめて、テストの側の書き方を直す)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/overview.py test/test_overview.py
git commit -m "feat: 俯瞰図の階層をツリーに変換する(要望 147)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ノードの文言と座標(`node_lines`・`layout_overview`)

**Files:**
- Modify: `src/projectapp/overview.py`(末尾に足す)
- Test: `test/test_overview.py`(足す)

**Interfaces:**
- Consumes: Task 1 の`OverviewNode`
- Produces:
  - `node_lines(node: OverviewNode, show_progress: bool, show_effort: bool) -> list[str]`: 1 行目は名前。`show_progress`かつ進捗があれば`進捗 45%`。`show_effort`かつ工数か完了予定があれば`工数 8h・完了 11/20`(片方だけならその分だけ)
  - 定数: `NODE_WIDTH = 200`・`GAP_X = 48`・`GAP_Y = 12`・`LINE_HEIGHT = 18`・`PADDING = 8`
  - `@dataclass class Placed`: `node: OverviewNode`・`lines: list[str]`・`x: int`・`y: int`・`width: int`・`height: int`・`depth: int`
  - `@dataclass class Edge`: `x1: int`・`y1: int`・`x2: int`・`y2: int`
  - `@dataclass class Layout`: `placed: list[Placed]`・`edges: list[Edge]`・`width: int`・`height: int`
  - `layout_overview(root: OverviewNode, show_progress: bool, show_effort: bool) -> Layout`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_overview.py`に足す:

```python
from projectapp.overview import (
    GAP_Y,
    NODE_WIDTH,
    OverviewNode,
    layout_overview,
    node_lines,
)


def leaf(name: str, **kw: object) -> OverviewNode:
    return OverviewNode(name, name, NodeKind.TASK, Status.NOT_STARTED, **kw)  # type: ignore[arg-type]


def test_node_lines_follow_the_checkboxes() -> None:
    node = leaf("設計", progress=45, effort_hours=8.0, due=datetime(2026, 11, 20))
    assert node_lines(node, True, True) == ["設計", "進捗 45%", "工数 8h・完了 11/20"]
    assert node_lines(node, False, True) == ["設計", "工数 8h・完了 11/20"]
    assert node_lines(node, True, False) == ["設計", "進捗 45%"]
    assert node_lines(node, False, False) == ["設計"]


def test_node_lines_skip_items_that_do_not_exist() -> None:
    assert node_lines(leaf("空"), True, True) == ["空"]
    assert node_lines(leaf("a", effort_hours=0.5), True, True) == ["a", "工数 0.5h"]


def tree() -> OverviewNode:
    root = leaf("R")
    root.children = [leaf("a"), leaf("b"), leaf("c")]
    root.children[1].children = [leaf("b1"), leaf("b2")]
    return root


def test_columns_follow_depth_and_siblings_stack_without_overlap() -> None:
    layout = layout_overview(tree(), True, True)
    by_name = {p.node.name: p for p in layout.placed}
    assert by_name["R"].x == 0
    assert by_name["a"].x == by_name["b1"].x - (by_name["b1"].x - by_name["a"].x)
    assert by_name["b1"].depth == 2
    columns: dict[int, list] = {}
    for p in layout.placed:
        columns.setdefault(p.depth, []).append(p)
    for items in columns.values():
        items.sort(key=lambda p: p.y)
        for upper, lower in zip(items, items[1:]):
            assert upper.y + upper.height + GAP_Y <= lower.y


def test_parent_is_centered_on_its_children_and_edges_join_them() -> None:
    layout = layout_overview(tree(), False, False)
    by_name = {p.node.name: p for p in layout.placed}
    kids = [by_name[n] for n in ("a", "b", "c")]
    top, bottom = kids[0].y, kids[-1].y + kids[-1].height
    root = by_name["R"]
    assert root.y + root.height / 2 == pytest.approx((top + bottom) / 2, abs=1)
    assert len(layout.edges) == len(layout.placed) - 1
    edge = layout.edges[0]
    assert edge.x1 == root.x + NODE_WIDTH


def test_hidden_lines_make_nodes_shorter() -> None:
    tall = layout_overview(leaf("x", progress=1, effort_hours=1.0), True, True)
    short = layout_overview(leaf("x", progress=1, effort_hours=1.0), False, False)
    assert short.placed[0].height < tall.placed[0].height


def test_a_thousand_nodes_are_laid_out_without_overlap() -> None:
    root = leaf("R")
    root.children = [leaf(f"n{i}") for i in range(1000)]
    layout = layout_overview(root, True, True)
    ys = sorted(p.y for p in layout.placed if p.depth == 1)
    assert len(set(ys)) == 1000
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_overview.py -v`
Expected: FAIL(`ImportError: cannot import name 'node_lines'`)

- [ ] **Step 3: 実装を足す**

`src/projectapp/overview.py`の末尾に足す(先頭の import に`from math import ceil`は不要。追加の import はない):

```python
NODE_WIDTH = 200
GAP_X = 48
GAP_Y = 12
LINE_HEIGHT = 18
PADDING = 8


def _hours_text(hours: float) -> str:
    return f"{hours:g}h"


def node_lines(node: OverviewNode, show_progress: bool, show_effort: bool) -> list[str]:
    """ノードに出す文字(画面と PDF で共通)。1 行目は名前。"""
    lines = [node.name]
    if show_progress and node.progress is not None:
        lines.append(f"進捗 {node.progress}%")
    if show_effort:
        parts = []
        if node.effort_hours:
            parts.append(f"工数 {_hours_text(node.effort_hours)}")
        if node.due is not None:
            parts.append(f"完了 {node.due.month}/{node.due.day}")
        if parts:
            lines.append("・".join(parts))
    return lines


@dataclass
class Placed:
    node: OverviewNode
    lines: list[str]
    x: int
    y: int
    width: int
    height: int
    depth: int


@dataclass
class Edge:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class Layout:
    placed: list[Placed]
    edges: list[Edge]
    width: int
    height: int


def layout_overview(
    root: OverviewNode, show_progress: bool, show_effort: bool
) -> Layout:
    """左から右へ、深さが列、兄弟が縦に並ぶ座標。親は、子の範囲の中央に置く。"""
    placed: list[Placed] = []
    edges: list[Edge] = []
    cursor = [0]  # 次の葉を置く y

    def place(node: OverviewNode, depth: int) -> Placed:
        lines = node_lines(node, show_progress, show_effort)
        height = PADDING * 2 + LINE_HEIGHT * len(lines)
        kids = [place(child, depth + 1) for child in node.children]
        if kids:
            top = kids[0].y
            bottom = kids[-1].y + kids[-1].height
            y = round((top + bottom - height) / 2)
            y = max(y, 0)
        else:
            y = cursor[0]
        cursor[0] = max(cursor[0], y + height + GAP_Y)
        me = Placed(node, lines, depth * (NODE_WIDTH + GAP_X), y, NODE_WIDTH, height, depth)
        placed.append(me)
        for kid in kids:
            edges.append(
                Edge(me.x + NODE_WIDTH, y + height // 2, kid.x, kid.y + kid.height // 2)
            )
        return me

    place(root, 0)
    placed.sort(key=lambda p: (p.depth, p.y))
    width = max(p.x + p.width for p in placed)
    height = max(p.y + p.height for p in placed)
    return Layout(placed, edges, width, height)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_overview.py -v`
Expected: PASS(親が子より上に押される場合に、同じ列の兄弟が重なるなら、`cursor`の更新を見直す。テストの重なりの確認が、その検出に当たる)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/overview.py test/test_overview.py
git commit -m "feat: 俯瞰図のノードの文言と座標を計算する(要望 147)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: PDF 出力(`overview_pdf.py`)

**Files:**
- Create: `src/projectapp/overview_pdf.py`
- Test: `test/test_overview_pdf.py`

**Interfaces:**
- Consumes: `Layout`・`Placed`・`Edge`・`LINE_HEIGHT`・`PADDING`(Task 2)、`STATUS_COLORS`・`OVERDUE_COLOR`(`projectapp.gantt`)
- Produces:
  - `class OverviewPdfError(Exception)`
  - `FONT_CANDIDATES: tuple[str, ...]`
  - `find_font(candidates: Sequence[str] = FONT_CANDIDATES) -> Path | None`
  - `render_pdf(layout: Layout, path: Path, font_path: Path | None = None) -> Path`(`font_path`が`None`なら`find_font()`。見つからなければ`OverviewPdfError`。一時ファイルに書いてから置き換え、書いたパスを返す)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_overview_pdf.py`:

```python
from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import Status
from projectapp.overview import NodeKind, OverviewNode, layout_overview
from projectapp.overview_pdf import OverviewPdfError, find_font, render_pdf


def small_layout():
    root = OverviewNode(
        "r", "とても長い名前のセクション" * 5 + "😀", NodeKind.SECTION, Status.NOT_STARTED,
        progress=40, effort_hours=12.0, due=datetime(2026, 11, 20),
    )
    root.children = [OverviewNode("a", "設計", NodeKind.TASK, Status.DONE, late=True)]
    return layout_overview(root, True, True)


needs_font = pytest.mark.skipif(find_font() is None, reason="日本語フォントがない環境")


def test_find_font_skips_missing_files(tmp_path: Path) -> None:
    real = tmp_path / "f.ttf"
    real.write_bytes(b"x")
    assert find_font([str(tmp_path / "none.ttf"), str(real)]) == real
    assert find_font([str(tmp_path / "none.ttf")]) is None


def test_missing_font_is_refused_and_no_file_is_made(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    with pytest.raises(OverviewPdfError):
        render_pdf(small_layout(), out, font_path=tmp_path / "none.ttf")
    assert not out.exists()


@needs_font
def test_pdf_starts_with_the_pdf_header(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    assert render_pdf(small_layout(), out) == out
    assert out.read_bytes().startswith(b"%PDF")


@needs_font
def test_an_existing_file_is_replaced_and_no_temp_file_remains(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    out.write_bytes(b"old")
    render_pdf(small_layout(), out)
    assert out.read_bytes().startswith(b"%PDF")
    assert [p.name for p in tmp_path.iterdir()] == ["out.pdf"]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_overview_pdf.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.overview_pdf`)

- [ ] **Step 3: 実装する**

`src/projectapp/overview_pdf.py`:

```python
"""俯瞰図を PDF に書き出す。Pillow で画像に描き、PDF に包む。NiceGUI には依存しない。"""

import os
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from projectapp.gantt import OVERDUE_COLOR, STATUS_COLORS
from projectapp.overview import LINE_HEIGHT, PADDING, Layout

SCALE = 2  # 画面の 1 に対する、画像の倍率
MARGIN = 24
RESOLUTION = 72.0 * SCALE  # 1 単位が 1pt になる

FONT_CANDIDATES = (
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothR.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
)


class OverviewPdfError(Exception):
    """PDF を作れない(フォントがない・書き込みに失敗など)。"""


def find_font(candidates: Sequence[str] = FONT_CANDIDATES) -> Path | None:
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: float) -> str:
    """幅に収まるように、末尾を…で切る。"""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def render_pdf(layout: Layout, path: Path, font_path: Path | None = None) -> Path:
    font_file = font_path if font_path is not None else find_font()
    if font_file is None or not font_file.is_file():
        raise OverviewPdfError("日本語のフォントが見つからないため、PDF を作れません")
    try:
        font = ImageFont.truetype(str(font_file), 12 * SCALE)
    except OSError as exc:
        raise OverviewPdfError(f"フォントを読めません: {exc}") from exc
    size = (
        (layout.width + MARGIN * 2) * SCALE,
        (layout.height + MARGIN * 2) * SCALE,
    )
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)

    def at(value: float) -> float:
        return (value + MARGIN) * SCALE

    for edge in layout.edges:
        mid = (edge.x1 + edge.x2) / 2
        points = [
            (at(edge.x1), at(edge.y1)),
            (at(mid), at(edge.y1)),
            (at(mid), at(edge.y2)),
            (at(edge.x2), at(edge.y2)),
        ]
        draw.line(points, fill="#90a4ae", width=SCALE)
    for item in layout.placed:
        node = item.node
        left, top = at(item.x), at(item.y)
        right, bottom = at(item.x + item.width), at(item.y + item.height)
        color = STATUS_COLORS[node.status]
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=4 * SCALE,
            fill="#ffffff",
            outline=OVERDUE_COLOR if node.late else "#b0bec5",
            width=(2 if node.late else 1) * SCALE,
        )
        draw.rectangle((left, top, left + 5 * SCALE, bottom), fill=color)
        text_x = left + (PADDING + 4) * SCALE
        room = right - text_x - PADDING * SCALE
        for number, line in enumerate(item.lines):
            draw.text(
                (text_x, top + (PADDING + number * LINE_HEIGHT) * SCALE),
                _fit(draw, line, font, room),
                fill="#263238" if number == 0 else "#546e7a",
                font=font,
            )
    temp = path.with_name(f".{path.name}.tmp")
    try:
        image.save(temp, "PDF", resolution=RESOLUTION)
        os.replace(temp, path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise OverviewPdfError(f"保存できませんでした: {exc}") from exc
    return path
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_overview_pdf.py -v`
Expected: PASS(フォントのない環境では、フォントが要るテストは skip になる)。`OVERDUE_COLOR`の型が`rounded_rectangle`の`outline`に通る文字列であることを確かめる(違えば`gantt.py`の定義に合わせて変換する)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/overview_pdf.py test/test_overview_pdf.py
git commit -m "feat: 俯瞰図を PDF に書き出す(要望 147)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ガントチャートの入口(右クリックのメニューと`reveal_task`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions`:714 付近、メニュー:1960〜2015 付近、`open_menu`:2050 付近、`expand_section`:1289 付近)
- Modify: `test/test_gantt.py`(`Recorder`:154 付近に 2 つ足す)
- Test: `test/test_overview_view.py`

**Interfaces:**
- Consumes: 既存の`self.actions`・`self.section_menu_target`・`self.menu_target`・`self.collapsed`・`self.collapsed_summaries`・`parent_map`
- Produces:
  - `GanttActions.overview_section: Callable[[SectionPath], object] = lambda path: None`
  - `GanttActions.overview_summary: Callable[[str], object] = lambda task_id: None`
  - メニュー項目のマーカー: セクション`section-context-overview`、タスク`context-overview`
  - `GanttChart.reveal_task(task_id: str) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py`の`Recorder.__init__`の`GanttActions(...)`に、`rename_section=...`の次の行として足す:

```python
            overview_section=lambda path: self.events.append(("overview_section", (path,))),
            overview_summary=lambda task_id: self.events.append(("overview_summary", (task_id,))),
```

`test/test_overview_view.py`:

```python
from datetime import date

from nicegui.testing import User

from projectapp.models import Project, Section, Task, TaskKind
from test_gantt import mount_chart


def project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        sections=[
            Section(
                "開発",
                [
                    Task("通常", id="a", effort_hours=4.0),
                    Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["c"]),
                    Task("子", id="c", effort_hours=2.0),
                ],
            )
        ],
    )


async def test_section_menu_opens_the_overview_of_that_section(user: User) -> None:
    charts, recorder = mount_chart(project())
    await user.open("/")
    charts[0].open_section_menu((0,))
    user.find(marker="section-context-overview").click()
    assert recorder.events == [("overview_section", ((0,),))]


async def test_summary_row_menu_opens_the_overview_of_that_summary(user: User) -> None:
    charts, recorder = mount_chart(project())
    await user.open("/")
    charts[0].open_menu((0,), 1)
    user.find(marker="context-overview").click()
    assert recorder.events == [("overview_summary", ("s",))]


async def test_overview_is_not_offered_on_a_plain_task(user: User) -> None:
    charts, recorder = mount_chart(project())
    await user.open("/")
    charts[0].open_menu((0,), 0)
    assert charts[0].overview_item is not None
    assert not charts[0].overview_item.visible


async def test_reveal_task_unfolds_the_section_and_the_summary(user: User) -> None:
    charts, _ = mount_chart(project())
    await user.open("/")
    chart = charts[0]
    chart.collapsed.add((0,))
    chart.collapsed_summaries.add("s")
    chart.reveal_task("c")
    assert (0,) not in chart.collapsed
    assert "s" not in chart.collapsed_summaries
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_overview_view.py -v`
Expected: FAIL(`GanttActions`に`overview_section`がない)

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py`:

1. `GanttActions`の`rename_section`の次の行に足す:

```python
    overview_section: Callable[[SectionPath], object] = lambda path: None
    overview_summary: Callable[[str], object] = lambda task_id: None
```

2. `__init__`(`self.section_menu_target`の近く、890 行付近)に足す:

```python
        self.overview_item: ui.menu_item | None = None  # まとめの行のときだけ見せる
```

3. タスクのメニューで、`ui.menu_item("コピー", ...)`の直前に足す:

```python
            self.overview_item = ui.menu_item(
                "俯瞰図…", on_click=act(lambda p, t: self.open_overview_of_task(p, t))
            ).mark("context-overview")
```

4. セクションのメニューの`for label, marker, action in (...)`のタプルに、`名前の変更`の次の要素として足す:

```python
                (
                    "俯瞰図…",
                    "section-context-overview",
                    lambda p: self.actions.overview_section(p),
                ),
```

5. メソッドを足す(`act_on_section`の次):

```python
    def open_overview_of_task(self, path: SectionPath, ti: int) -> None:
        tasks = arrange.tasks_at(self.project, path)
        task = tasks[ti]
        if task.kind is TaskKind.SUMMARY:
            self.actions.overview_summary(task.id)

    def reveal_task(self, task_id: str) -> None:
        """そのタスクの行が見えるよう、折りたたみを開いて、その行へスクロールする。"""
        if not any(t.id == task_id for t in self.project.tasks):  # 直下のタスクは、セクションを開かない
            for path, section in walk_sections(self.project.sections):
                if any(t.id == task_id for t in section.tasks):
                    self.expand_section(path)
                    break
        parents = parent_map(self.project)
        current = task_id
        while current in parents:
            current = parents[current]
            self.collapsed_summaries.discard(current)
        self.render.refresh()
        ui.run_javascript(
            "setTimeout(() => document.querySelector("
            f"'[data-task-id={json.dumps(task_id)}]')"
            "?.scrollIntoView({block: 'center'}), 150)"
        )
```

(`json`・`walk_sections`・`parent_map`・`TaskKind`が未 import なら、ファイル先頭の import に足す。`data-task-id`のセレクタは、`'[data-task-id="abc"]'`の形になる。`json.dumps`が二重引用符で包むので、属性のセレクタとして有効)

6. `open_menu`の、メニューの状態を反映する箇所(`self.decompose_item`を設定している近く)に足す:

```python
        if self.overview_item is not None:
            current = arrange.tasks_at(self.project, path)[ti]
            self.overview_item.set_visibility(current.kind is TaskKind.SUMMARY)
```

(`open_menu`の冒頭の`if self.decompose_item is None: return`より前に置く。`tasks_at`が空のときに落ちないよう、`if ti < len(tasks)`で守る)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_overview_view.py test/test_context_menu.py test/test_gantt.py -q`
Expected: PASS。`render.refresh()`が`refreshable_method`の呼び方と合わないときは、`gantt.py`で他の再描画の呼び出し(`grep -n "render.refresh\|self.render(" src/projectapp/gantt.py`)に合わせる。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py test/test_gantt.py test/test_overview_view.py
git commit -m "feat: セクションとまとめの右クリックに俯瞰図を足し、行へ移る処理を作る(要望 147)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ダイアログと`views.py`の接続

**Files:**
- Create: `src/projectapp/overview_dialog.py`
- Modify: `src/projectapp/views.py`(`GanttActions(...)`の生成:624 付近、`rename_section`の近くにメソッドを足す)
- Test: `test/test_overview_view.py`(足す)

**Interfaces:**
- Consumes: Task 1〜3 の関数、`disposable`(`projectapp.forms`)、`GanttChart.reveal_task`(Task 4)
- Produces:
  - `open_overview_dialog(root: OverviewNode, on_jump: Callable[[str], object], on_pdf: Callable[[Layout], Awaitable[None]]) -> None`
  - マーカー: チェックボックス`overview-progress`・`overview-effort`、ボタン`overview-pdf`、ノード`overview-node-<id>`
  - `Views`(`views.py`の該当クラス)の`open_overview_section(path)`・`open_overview_summary(task_id)`・`async export_overview_pdf(layout)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_overview_view.py`に足す:

```python
from datetime import datetime

from nicegui import ui

from projectapp.models import Status
from projectapp.overview import NodeKind, OverviewNode, build_overview
from projectapp.overview_dialog import open_overview_dialog


def mount_dialog(jumps: list[str], pdfs: list) -> None:
    root = build_overview(project(), {}, datetime(2026, 10, 1), section_path=(0,))

    @ui.page("/")
    def index() -> None:
        async def on_pdf(layout) -> None:
            pdfs.append(layout)

        ui.button("開く", on_click=lambda: open_overview_dialog(root, jumps.append, on_pdf)).mark("open")


async def test_dialog_shows_nodes_and_hides_items_with_the_checkboxes(user: User) -> None:
    mount_dialog([], [])
    await user.open("/")
    user.find(marker="open").click()
    await user.should_see("開発")
    await user.should_see("進捗")
    user.find(marker="overview-progress").click()
    await user.should_not_see("進捗 ")


async def test_clicking_a_node_jumps_to_its_task_and_closes(user: User) -> None:
    jumps: list[str] = []
    mount_dialog(jumps, [])
    await user.open("/")
    user.find(marker="open").click()
    user.find(marker="overview-node-a").click()
    assert jumps == ["a"]


async def test_pdf_button_hands_the_current_layout_to_the_callback(user: User) -> None:
    pdfs: list = []
    mount_dialog([], pdfs)
    await user.open("/")
    user.find(marker="open").click()
    user.find(marker="overview-effort").click()  # 工数を隠した状態の座標が渡る
    user.find(marker="overview-pdf").click()
    assert len(pdfs) == 1
    assert all("工数" not in line for p in pdfs[0].placed for line in p.lines)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_overview_view.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.overview_dialog`)

- [ ] **Step 3: ダイアログを実装する**

`src/projectapp/overview_dialog.py`:

```python
"""俯瞰図のダイアログ。座標は`overview.py`の純粋関数で作り、ここは描くだけ。"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from projectapp.forms import disposable
from projectapp.gantt import OVERDUE_COLOR, STATUS_COLORS
from projectapp.overview import Layout, OverviewNode, layout_overview

PAGE_MARGIN = 16


def open_overview_dialog(
    root: OverviewNode,
    on_jump: Callable[[str], object],
    on_pdf: Callable[[Layout], Awaitable[None]],
) -> None:
    """俯瞰図を開く。チェックボックスの状態は、このダイアログの中だけで持つ(保存しない)。"""
    state = {"progress": True, "effort": True}
    with (
        disposable(ui.dialog()).props("maximized") as dialog,
        ui.card().classes("w-full h-full"),
    ):
        with ui.row().classes("items-center w-full gap-4"):
            ui.label(f"俯瞰図: {root.name}").classes("text-h6")
            ui.space()
            ui.checkbox(
                "進捗", value=True, on_change=lambda e: change("progress", e.value)
            ).mark("overview-progress")
            ui.checkbox(
                "工数・完了予定", value=True, on_change=lambda e: change("effort", e.value)
            ).mark("overview-effort")
            ui.button("PDF に出力", icon="picture_as_pdf", on_click=lambda: export()).props(
                "flat"
            ).mark("overview-pdf")
            ui.button(icon="close", on_click=dialog.close).props("flat round")

        def current() -> Layout:
            return layout_overview(root, state["progress"], state["effort"])

        def jump(task_id: str | None) -> None:
            dialog.close()
            if task_id is not None:
                on_jump(task_id)

        @ui.refreshable
        def diagram() -> None:
            layout = current()
            with ui.scroll_area().classes("w-full grow"):
                with ui.element("div").style(
                    f"position: relative; width: {layout.width + PAGE_MARGIN * 2}px;"
                    f" height: {layout.height + PAGE_MARGIN * 2}px"
                ):
                    for edge in layout.edges:
                        mid = (edge.x1 + edge.x2) // 2
                        line = "border-color: #90a4ae; border-style: solid; border-width: 0; position: absolute;"
                        top, bottom = sorted((edge.y1, edge.y2))
                        for style in (
                            f"left: {edge.x1 + PAGE_MARGIN}px; top: {edge.y1 + PAGE_MARGIN}px;"
                            f" width: {mid - edge.x1}px; border-top-width: 1px",
                            f"left: {mid + PAGE_MARGIN}px; top: {top + PAGE_MARGIN}px;"
                            f" height: {bottom - top}px; border-left-width: 1px",
                            f"left: {mid + PAGE_MARGIN}px; top: {edge.y2 + PAGE_MARGIN}px;"
                            f" width: {edge.x2 - mid}px; border-top-width: 1px",
                        ):
                            ui.element("div").style(line + style)
                    for item in layout.placed:
                        node = item.node
                        border = OVERDUE_COLOR if node.late else "#b0bec5"
                        box = ui.element("div").style(
                            f"position: absolute; left: {item.x + PAGE_MARGIN}px;"
                            f" top: {item.y + PAGE_MARGIN}px; width: {item.width}px;"
                            f" height: {item.height}px; box-sizing: border-box;"
                            f" border: {2 if node.late else 1}px solid {border};"
                            f" border-left: 5px solid {STATUS_COLORS[node.status]};"
                            " border-radius: 4px; padding: 8px 8px 8px 10px;"
                            " overflow: hidden; cursor: pointer; background: var(--q-card-bg, #fff)"
                        )
                        box.mark(f"overview-node-{node.id}")
                        box.on("click", lambda _, n=node: jump(n.first_task_id))
                        with box:
                            for number, text in enumerate(item.lines):
                                ui.label(text).classes(
                                    "ellipsis" + ("" if number == 0 else " text-caption")
                                ).style("line-height: 18px; height: 18px; white-space: nowrap")

        def change(key: str, value: bool) -> None:
            state[key] = bool(value)
            diagram.refresh()

        async def export() -> None:
            await on_pdf(current())

        diagram()
    dialog.open()
```

- [ ] **Step 4: `views.py`へ接続する**

`GanttActions(...)`の`rename_section=self.rename_section,`の次の行に足す:

```python
                overview_section=self.open_overview_section,
                overview_summary=self.open_overview_summary,
```

`rename_section`のメソッドの近くにメソッドを足す(`views.py`の import に、`from projectapp.overview import build_overview`・`from projectapp.overview_dialog import open_overview_dialog`・`from projectapp.overview_pdf import OverviewPdfError, render_pdf`・`from projectapp.overview import Layout`を足す):

```python
    def open_overview_section(self, path: SectionPath) -> None:
        root = build_overview(self.project, self.holidays, clock.now(), section_path=path)
        self.show_overview(root)

    def open_overview_summary(self, task_id: str) -> None:
        root = build_overview(self.project, self.holidays, clock.now(), summary_id=task_id)
        self.show_overview(root)

    def show_overview(self, root) -> None:
        open_overview_dialog(root, self.gantt.reveal_task, self.export_overview_pdf)

    async def export_overview_pdf(self, layout: Layout) -> None:
        """俯瞰図を PDF に書き出す。プロジェクトは変えない(保存も、変更扱いもしない)。"""
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        path = await self.exporter.ask_path("overview.pdf", ("PDF (*.pdf)",))
        if path is None:
            return
        try:
            written = render_pdf(layout, path)
        except OverviewPdfError as exc:
            ui.notify(str(exc), type="negative")
            return
        ui.notify(f"書き出しました({written.name})")
```

`views.py`の`HANDOFF_NOT_NATIVE_MESSAGE`は 436 行にある。`self.holidays`・`clock`・`self.gantt`は既存の名前(`copy_section`が`self.gantt`を使っている)。

- [ ] **Step 5: 通ることを確かめ、Views 側のテストを足す**

`test/test_views.py`の末尾に足す(`FakeExporter`・`open_for_import`・`wait_until`は同じファイルにある。`export_settings`のテストと同じ組み立て):

```python
from projectapp.overview import NodeKind, OverviewNode, layout_overview
from projectapp.models import Status


def overview_layout():
    root = OverviewNode("r", "開発", NodeKind.SECTION, Status.NOT_STARTED)
    return layout_overview(root, True, True)


async def test_overview_pdf_is_refused_outside_the_native_window(
    user: User, tmp_path: Path
) -> None:
    exporter = FakeExporter(path=tmp_path / "x.pdf", available=False)
    view = await open_for_import(user, tmp_path, exporter)
    await view.export_overview_pdf(overview_layout())
    await user.should_see("ネイティブウィンドウでのみ、書き出せます")
    assert exporter.asked == []


async def test_cancelling_the_overview_pdf_dialog_writes_nothing(
    user: User, tmp_path: Path
) -> None:
    exporter = FakeExporter(path=None)
    view = await open_for_import(user, tmp_path, exporter)
    await view.export_overview_pdf(overview_layout())
    assert exporter.asked == ["overview.pdf"]
    assert not list(tmp_path.glob("*.pdf"))


async def test_overview_pdf_reports_a_missing_font_and_keeps_the_project(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("projectapp.overview_pdf.find_font", lambda *a, **k: None)
    target = tmp_path / "out.pdf"
    exporter = FakeExporter(path=target)
    view = await open_for_import(user, tmp_path, exporter)
    dirty = view.is_dirty()
    await view.export_overview_pdf(overview_layout())
    await user.should_see("日本語のフォントが見つからない")
    assert not target.exists() and view.is_dirty() == dirty
```

(`render_pdf`は、`font_path`が`None`のとき、モジュール内の`find_font`を呼ぶので、`monkeypatch`で`None`を返すと、フォントなしの経路を通る。`pytest`の import が`test_views.py`になければ足す)

Run: `uv run pytest test/test_overview_view.py test/test_views.py -k "overview" -q` → PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/overview_dialog.py src/projectapp/views.py test/test_overview_view.py
git commit -m "feat: 俯瞰図のダイアログと PDF の書き出しを、メニューにつなぐ(要望 147)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 仕様・文書と、最終の確認

**Files:**
- Modify: `.claude/spec/gantt.md`(セクション・タスクの右クリックの記述の近くに追記)
- Modify: `docs/requests.md`(要望 147 と 141 の「状態」)
- Modify: `docs/development.md`(モジュール構成)

- [ ] **Step 1: `.claude/spec/gantt.md`に追記する**

セクションの右クリックの項(16 行目の`コピー`・`名前の変更`・`削除`を述べた箇所)に、`俯瞰図…`を足す。続けて、新しい項を足す:

```markdown
- 俯瞰図(要望 147): セクションの見出しと、まとめの行の右クリックの`俯瞰図…`で、その配下の階層をツリー状の図にしてダイアログに出す(先行・後続の矢印は出さない)。左から右へ、深さが列、兄弟が縦に並ぶ。ノードには、名前と状態の色の印(予定超過・期限超過は赤い枠)を出し、上部のチェックボックス`進捗`・`工数・完了予定`で、それぞれの行を隠せる(既定は表示。保存しない)。セクション・まとめの進捗は、配下の通常タスクの工数で重みづけした率。プロジェクト参照は 1 ノードの葉で、進捗を出さない。ノードをクリックすると、ダイアログを閉じ、ガントチャートのその行へスクロールする(折りたたみは開く。セクションのノードは、中の最初のタスクの行へ)。`PDF に出力`は、今の表示のまま 1 ページの PDF にする(Pillow で画像に描いて包む。日本語フォントは OS のものを探し、なければ通知で断る)。保存先はネイティブのファイル保存ダイアログで選び、Web モードでは通知で断る。プレビュー(読み取り専用)では、右クリックのメニュー自体を出さない
```

- [ ] **Step 2: `docs/requests.md`・`docs/development.md`を直す**

- 要望 147 の`### 状態`を、`実装済み・マージ指示待ち(設計は`docs/superpowers/specs/2026-11-15-overview-diagram-design.md`)。`の形に直し、`### 決めたい点`の見出しを`### 決めた点(設計書で決定済み)`に直す。
- 要望 141 の`### 状態`が「実装済み・マージ指示待ち」なら、「実装済み(PR #240 マージ済み)」に直す。
- `docs/development.md`のモジュール構成の表に、`overview.py`(階層の変換と座標)・`overview_dialog.py`(ダイアログ)・`overview_pdf.py`(PDF)を足す。テストの一覧にも`test_overview*.py`を足す。

- [ ] **Step 3: 最終の確認**

Run:
```bash
uv run pytest -m smoke
uvx ruff check
uvx ruff format src test
uvx ty check src
```
Expected: smoke が PASS。ruff が通る。ty は、既存の 9 件以外が増えない。smoke が失敗したときに限り`uv run pytest -n auto`で全テストを確かめる。

- [ ] **Step 4: 実機で確認するための確認用データを作る**

`docs/samples/俯瞰図の確認.json`を、セクション 3 階層・まとめ(子 3 件)・遅れ・チェックポイント・プロジェクト参照を含む形で作り、`~/.projectapp/`にもコピーする(形式は既存の`docs/samples/遅れ多数の確認.json`に合わせる)。`uv run projectapp`で、右クリック → 俯瞰図 → チェックボックス → ノードのクリック → PDF の書き出しを確かめ、PDF を開いて日本語が欠けないことを見る。

- [ ] **Step 5: コミットして PR を作る(マージは指示を待つ)**

```bash
git add .claude/spec/gantt.md docs/requests.md docs/development.md docs/samples
git commit -m "docs: 俯瞰図の仕様・要望の状態・モジュール構成を更新する(要望 147)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/overview-diagram
gh pr create --base develop --title "feat: 俯瞰図(系統図)を、ダイアログと PDF で出せるようにする(要望 147)" --body "設計書: docs/superpowers/specs/2026-11-15-overview-diagram-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR を作ったら止まり、実機の確認とマージの指示を待つ。
