# 割り当て表の横スクロール連動 実装計画(要望 117)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下部パネルの`割り当て`表の列を、ガントチャートの列と同じ幅・同じ左端にそろえ、横スクロールを両方向に連動させる。

**Architecture:** 列幅の決め方は NiceGUI に依存しない小さな値クラス(`AssignmentLayout`)にする。`GanttChart`が刻み(`COLUMN_WIDTH_PX`)と名前欄の幅(`name_width`)から`AssignmentLayout`を作って`PanelContent`で渡し、`BottomPanel`が px で描く。連動は、ページに一度だけ仕掛ける JS(`document`の`scroll`をキャプチャし、値が違うときだけ相手の`scrollLeft`を合わせる)と、表を描くたびに走る位置合わせの JS で行う。

**Tech Stack:** Python 3.13、NiceGUI(`user`フィクスチャのテスト)、ruff・ty(`uvx`)、JS の構文確認に`node --check`

**Spec:** [`docs/superpowers/specs/2026-11-01-assignment-scroll-sync-design.md`](../specs/2026-11-01-assignment-scroll-sync-design.md)

## Global Constraints

- 言語は日本語(コメント・UI の文言・コミットメッセージ)。Python 3.13 以上
- ファイル形式(`version`)は変えない。連動・ビューの状態は保存しない
- 既存の`TRACK_SCROLL_JS`・`SHOW_CHART_JS`・`today_scroll_js`を壊さない(チャートの`scroll`の処理は変えず、連動は`document`側で足す)
- テストの運用(2026-11-01 決定): 実装完了時は smoke(`uv run pytest -m smoke`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(`dashboard_view.py`の`days_text`の指摘 1 件は既存)。**全テストは smoke が失敗したときに限って**流す。コミットの前に`ruff check`の出力を読む
- コミットメッセージの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- 最終レビューのサブエージェントは`model: "sonnet"`を必ず指定(opus・fable は使わない)
- マージは利用者の指示を待つ(PR を作って止まる)

## Review Focus

1. 担当者の列とチャートの名前欄の幅が同じで、日付の列が`COLUMN_WIDTH_PX`と同じ px になる(刻みを変えても追従する)(Task 1・2・4)
2. 選択やスクロールでパネルが描き直されても、表の横位置が先頭に戻らず、チャートの位置に合う(Task 3)
3. 連動がループしない(片方を合わせたときに起きる`scroll`で、もう片方を動かし返さない)(Task 3)
4. `割り当て`ビューを出していないとき・表が空のとき、連動の JS が落ちない(相手の要素がない)(Task 3)
5. 名前欄の幅をドラッグで変えると、表の担当者列が追従する。ドラッグ中ではなく、離したときでよい(Task 4)

## ファイル構成

| ファイル | 変更 |
|---|---|
| `src/projectapp/bottom_info.py` | `AssignmentLayout`(名前列と日付列の px 幅) |
| `src/projectapp/bottom_panel.py` | `PanelContent.layout`、px 幅の描画、名前列の sticky と省略表示、`data-assignment-scroll`、連動の JS(`ASSIGNMENT_SYNC_JS`・`ASSIGNMENT_ALIGN_JS`) |
| `src/projectapp/gantt.py` | `bottom_content`でレイアウトを渡す、連動の JS を仕掛ける、名前欄の幅の変更でパネルを更新 |
| `test/test_bottom_info.py`・`test/test_bottom_panel.py`・`test/test_assignment_view.py` | テスト |
| `.claude/spec/gantt.md`・`README.md`・設計書・`docs/requests.md`・`docs/request-history.md`・`docs/superpowers/README.md`・`docs/superpowers/specs/2026-11-01-assignment-view-design.md` | 文書 |

---

### Task 1: 列幅の値クラス

**Files:**
- Modify: `src/projectapp/bottom_info.py`
- Test: `test/test_bottom_info.py`

**Interfaces:**
- Consumes: なし
- Produces: `AssignmentLayout(name_px: int, column_px: int)`(frozen dataclass)。`grid_columns(count: int) -> str`(`"200px repeat(3, 40px)"`)、`total_width(count: int) -> int`(`name_px + column_px * count`)

- [ ] **Step 1: 失敗するテストを書く**(`test_bottom_info.py`の末尾。import に`AssignmentLayout`を足す)

```python
def test_layout_grid_columns_use_px_widths() -> None:
    layout = AssignmentLayout(name_px=200, column_px=40)
    assert layout.grid_columns(3) == "200px repeat(3, 40px)"
    assert layout.total_width(3) == 320


def test_layout_with_no_columns_is_just_the_name_column() -> None:
    layout = AssignmentLayout(name_px=200, column_px=56)
    assert layout.grid_columns(0) == "200px"
    assert layout.total_width(0) == 200
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_bottom_info.py -q`
Expected: FAIL(`AssignmentLayout`の import エラー)

- [ ] **Step 3: 実装する**(`bottom_info.py`の`AssignmentTable`の近く)

```python
@dataclass(frozen=True)
class AssignmentLayout:
    """割り当て表の列幅(px)。ガントチャートの名前欄と日付の列にそろえる。"""

    name_px: int  # 担当者の列(チャートの名前欄の幅)
    column_px: int  # 日付の列 1 つ(チャートの`COLUMN_WIDTH_PX`)

    def grid_columns(self, count: int) -> str:
        if count <= 0:  # 列がなくても不正な CSS にしない
            return f"{self.name_px}px"
        return f"{self.name_px}px repeat({count}, {self.column_px}px)"

    def total_width(self, count: int) -> int:
        return self.name_px + self.column_px * max(count, 0)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_bottom_info.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/bottom_info.py test/test_bottom_info.py
git commit -m "feat: 割り当て表の列幅の値クラスを足す(要望 117)"
```
(末尾に Co-Authored-By を付ける)

---

### Task 2: 表を px 幅で描く(担当者列は sticky・省略表示)

**Files:**
- Modify: `src/projectapp/bottom_panel.py`
- Test: `test/test_bottom_panel.py`

**Interfaces:**
- Consumes: Task 1 の`AssignmentLayout`
- Produces:
  - `PanelContent.layout: AssignmentLayout | None = None`(末尾の既定つき。`None`は`AssignmentLayout(160, 40)`)
  - マーカー: `bottom-assignment-grid`(グリッド)、`bottom-assignment-name`(担当者のセル。`gantt-sticky`クラス・`position: sticky; left: 0`・幅は`name_px`・名前は省略表示・`title`に全文)
  - スクロール枠(`bottom-assignment`)に`data-assignment-scroll`の属性

- [ ] **Step 1: 失敗するテストを書く**(`test_bottom_panel.py`。`TABLE`・`mount_assignment`・`SUMMARY`・`TODAY`は既存)

```python
from projectapp.bottom_info import AssignmentLayout


async def test_the_grid_uses_the_chart_widths(user: User) -> None:
    panels = mount_assignment(
        PanelContent(None, SUMMARY, TODAY, TABLE, AssignmentLayout(200, 56))
    )
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment")
    grid = user.find(marker="bottom-assignment-grid").elements.pop()
    assert grid._style["grid-template-columns"] == "200px repeat(3, 56px)"
    scroll = user.find(marker="bottom-assignment").elements.pop()
    assert "data-assignment-scroll" in scroll._props


async def test_the_name_cell_is_sticky_with_the_chart_name_width(user: User) -> None:
    panels = mount_assignment(
        PanelContent(None, SUMMARY, TODAY, TABLE, AssignmentLayout(200, 40))
    )
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment")
    cell = user.find(marker="bottom-assignment-name").elements.pop()
    assert "gantt-sticky" in cell.classes
    assert cell._style["position"] == "sticky" and cell._style["left"] == "0px"
    assert cell._style["width"] == "200px"
    assert cell._props["title"] == "田中"


async def test_without_a_layout_it_falls_back_to_a_default(user: User) -> None:
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, TABLE))
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment")
    grid = user.find(marker="bottom-assignment-grid").elements.pop()
    assert grid._style["grid-template-columns"] == "160px repeat(3, 40px)"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_bottom_panel.py -q`
Expected: FAIL(`PanelContent`に第 5 引数がない)

- [ ] **Step 3: 実装する**(`bottom_panel.py`)

`PanelContent`に`layout: AssignmentLayout | None = None`を足す(`AssignmentLayout`を import)。定数に`DEFAULT_LAYOUT = AssignmentLayout(160, 40)`、`CELL_STYLE`は`font-size`と`text-align`だけ残し、幅は`min-width`をやめる(`width`はグリッドが決める)。`show_assignment`を次のように置き換える:

```python
def show_assignment(self, table: AssignmentTable | None) -> None:
    """担当者×列の割り当て率。列の幅はガントチャートと同じ px。担当者の列は左に固定する。"""
    layout = (self.content.layout if self.content else None) or DEFAULT_LAYOUT
    with (
        ui.element("div")
        .classes("w-full")
        .props("data-assignment-scroll")
        .style("overflow-x: auto")
        .mark("bottom-assignment")
    ):
        if table is None or not table.rows:
            ui.label("割り当てのある担当者はいません").classes("text-grey").mark(
                "bottom-assignment-empty"
            )
            return
        with (
            ui.element("div")
            .style(
                f"display: grid; width: {layout.total_width(len(table.labels))}px;"
                f" grid-template-columns: {layout.grid_columns(len(table.labels))}"
            )
            .mark("bottom-assignment-grid")
        ):
            ui.element("div").classes("gantt-sticky").style(
                "position: sticky; left: 0px; z-index: 2"
            )  # 左上の空き
            for label in table.labels:
                ui.label(label).classes("text-caption text-grey").style(CELL_STYLE)
            for row in table.rows:
                with (
                    ui.row()
                    .classes("items-center gap-1 no-wrap gantt-sticky")
                    .props(f'title="{row.name}"')
                    .style(
                        "position: sticky; left: 0px; z-index: 2; overflow: hidden;"
                        f" width: {layout.name_px}px; padding: 1px 4px"
                    )
                    .mark("bottom-assignment-name")
                ):
                    avatar(row.name, row.icon, 18).mark("bottom-assignment-avatar")
                    ui.label(row.name).classes("text-bold ellipsis")
                for cell in row.cells:
                    self.show_assignment_cell(cell)
```

(`title`に入る名前の`"`は、`html.escape`で逃がす。`ui.run_javascript(ASSIGNMENT_ALIGN_JS)`は Task 3 で足す。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_bottom_panel.py test/test_assignment_view.py -q`
Expected: PASS(既存の`bottom-assignment-*`のテストが通ること。担当者名のラベルのマーカー位置が変わって落ちるテストは、実装ではなくテストの探し方を直す)

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/bottom_panel.py test/test_bottom_panel.py
git commit -m "feat: 割り当て表を px 幅で描き、担当者の列を左に固定する(要望 117)"
```

---

### Task 3: 横スクロールの連動(JS)

**Files:**
- Modify: `src/projectapp/bottom_panel.py`、`src/projectapp/gantt.py`
- Test: `test/test_bottom_panel.py`

**Interfaces:**
- Consumes: Task 2 の`data-assignment-scroll`、チャートの`data-chart-scroll`
- Produces: `bottom_panel.ASSIGNMENT_SYNC_JS`(ページに一度だけ仕掛ける連動)、`bottom_panel.ASSIGNMENT_ALIGN_JS`(表を描いたあとの位置合わせ)。`GanttChart.build`が`ASSIGNMENT_SYNC_JS`を`ui.add_head_html`で仕掛け、`BottomPanel.show_assignment`が描くたびに`ASSIGNMENT_ALIGN_JS`を`ui.run_javascript`で走らせる

- [ ] **Step 1: 失敗するテストを書く**(`test_bottom_panel.py`)

```python
import shutil
import subprocess

import pytest

from projectapp import bottom_panel


def test_the_sync_js_connects_the_chart_and_the_table_without_looping() -> None:
    js = bottom_panel.ASSIGNMENT_SYNC_JS
    assert "data-chart-scroll" in js and "data-assignment-scroll" in js
    assert "Math.abs" in js  # 値が同じなら合わせ直さない(ループ防止)
    assert "true)" in js  # scroll は伝わらないので、キャプチャで拾う


def test_the_align_js_copies_the_chart_position_and_tolerates_missing_elements() -> None:
    js = bottom_panel.ASSIGNMENT_ALIGN_JS
    assert "data-chart-scroll" in js and "data-assignment-scroll" in js
    assert "if (" in js  # 相手がいないときは何もしない


@pytest.mark.skipif(shutil.which("node") is None, reason="node がない")
@pytest.mark.parametrize("name", ["ASSIGNMENT_SYNC_JS", "ASSIGNMENT_ALIGN_JS"])
def test_the_js_is_syntactically_valid(name: str, tmp_path) -> None:
    path = tmp_path / "x.js"
    path.write_text(getattr(bottom_panel, name), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


async def test_drawing_the_table_runs_the_align_js(user: User, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(bottom_panel.ui, "run_javascript", lambda js, **kw: calls.append(js))
    panels = mount_assignment(PanelContent(None, SUMMARY, TODAY, TABLE))
    await user.open("/")
    panels[0].toggle_view()
    await user.should_see(marker="bottom-assignment")
    assert bottom_panel.ASSIGNMENT_ALIGN_JS in calls
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_bottom_panel.py -q`
Expected: FAIL(`ASSIGNMENT_SYNC_JS`がない)

- [ ] **Step 3: 実装する**(`bottom_panel.py`の定数)

```python
# ガントチャートと割り当て表の横スクロールを連動させる(ページに一度だけ)。scroll は親に伝わらないので、キャプチャで拾う。
# 相手の位置が(ほぼ)同じなら合わせ直さない。これで、合わせた側の scroll イベントが、もう一度こちらを動かすことがない
ASSIGNMENT_SYNC_JS = """
(() => {
  if (window.__assignmentSync) return;
  window.__assignmentSync = true;
  document.addEventListener('scroll', (e) => {
    const t = e.target;
    if (!t || !t.matches) return;
    let other = null;
    if (t.matches('[data-chart-scroll]')) other = document.querySelector('[data-assignment-scroll]');
    else if (t.matches('[data-assignment-scroll]')) other = document.querySelector('[data-chart-scroll]');
    if (other && Math.abs(other.scrollLeft - t.scrollLeft) > 0.5) other.scrollLeft = t.scrollLeft;
  }, true);
})();
"""
# 表を描き直したあと、チャートの横位置へ合わせる(描き直しで先頭に戻らないように)
ASSIGNMENT_ALIGN_JS = (
    "requestAnimationFrame(() => {"
    " const chart = document.querySelector('[data-chart-scroll]');"
    " const table = document.querySelector('[data-assignment-scroll]');"
    " if (chart && table) table.scrollLeft = chart.scrollLeft; })"
)
```

`show_assignment`の、表(またはメッセージ)を描いた直後に`ui.run_javascript(ASSIGNMENT_ALIGN_JS)`を足す。空のとき(`return`の前)でも呼んでよい(相手がいなくても落ちない)。

`gantt.py`: `build`の`ui.add_head_html(f"<script>{SHIFT_TRACK_JS}</script>")`の次に、`ui.add_head_html(f"<script>{ASSIGNMENT_SYNC_JS}</script>")`を足し、`from projectapp.bottom_panel import ASSIGNMENT_SYNC_JS, BottomPanel, PanelContent`に直す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_bottom_panel.py test/test_assignment_view.py test/test_gantt.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/bottom_panel.py src/projectapp/gantt.py test/test_bottom_panel.py
git commit -m "feat: 割り当て表とガントチャートの横スクロールを連動させる(要望 117)"
```

---

### Task 4: ガントチャートからの列幅の受け渡し

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_assignment_view.py`

**Interfaces:**
- Consumes: Task 1・2 の成果、`COLUMN_WIDTH_PX`、`GanttChart.name_width`・`view_scale`・`handle_name_width`
- Produces: `bottom_content`が`割り当て`ビューのとき`PanelContent.layout = AssignmentLayout(self.name_width, COLUMN_WIDTH_PX[self.view_scale])`を渡す。`handle_name_width`は、`割り当て`ビューを出していれば`refresh_bottom()`を呼ぶ

- [ ] **Step 1: 失敗するテストを書く**(`test/test_assignment_view.py`。import に`AssignmentLayout`を足す。`mount`の`recorder.actions`には`set_name_width`が既にあるが、なければ`recorder.actions.set_name_width = lambda width: None`を足す)

```python
async def test_the_layout_follows_the_scale_and_the_name_width(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    assert charts[0].bottom.content.layout == AssignmentLayout(200, 40)
    charts[0].set_scale(Scale.WEEK)
    await asyncio.sleep(0.2)
    assert charts[0].bottom.content.layout == AssignmentLayout(200, 56)


async def test_dragging_the_name_width_updates_the_table(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].toggle_assignment()
    charts[0].handle_name_width({"width": 300})
    assert charts[0].bottom.content.layout.name_px == 300


async def test_the_name_width_change_is_harmless_in_the_info_view(user: User) -> None:
    charts = mount()
    await user.open("/")
    charts[0].handle_name_width({"width": 300})
    assert charts[0].bottom.content.layout is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_assignment_view.py -q`
Expected: FAIL(`layout`が`None`のまま)

- [ ] **Step 3: 実装する**(`gantt.py`)

`bottom_content`の`assignment = None`の隣に`layout = None`を足し、`if self.bottom.view == "assignment":`の中で`layout = AssignmentLayout(self.name_width, COLUMN_WIDTH_PX[self.view_scale])`を作り、`PanelContent(..., assignment, layout)`で渡す(`AssignmentLayout`を import)。`handle_name_width`の`self.actions.set_name_width(width)`の後に:

```python
if self.bottom.view == "assignment":
    self.refresh_bottom()  # 表の担当者列も、名前欄の新しい幅に合わせる
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_assignment_view.py test/test_bottom_panel.py test/test_bottom_split.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff check && uvx ruff format src test
git add src/projectapp/gantt.py test/test_assignment_view.py
git commit -m "feat: 割り当て表の列幅を、刻みと名前欄の幅に合わせる(要望 117)"
```

---

### Task 5: 文書と全体の確認

**Files:**
- Modify: `.claude/spec/gantt.md`、`README.md`(必要なら)、`docs/superpowers/specs/2026-11-01-assignment-view-design.md`、設計書(状態)、`docs/requests.md`、`docs/request-history.md`、`docs/superpowers/README.md`

**Interfaces:** なし(文書のみ)

- [ ] **Step 1: 文書を更新する**
  - `.claude/spec/gantt.md`の`割り当て`ビューの項に、列幅がチャートと同じ(担当者列は名前欄と同じ幅で左に固定、日付の列は`日次 40・週次 56・月次 80`px)、横スクロールが両方向に連動、描き直しても位置が戻らない、縦は連動しない、名前欄の幅を変えると離したときに追従、を足す。「独立して横にスクロールする」の記述は、連動に直す
  - `docs/superpowers/specs/2026-11-01-assignment-view-design.md`の`位置`の行を、要望 117 で連動したことに直す(第 2 段階は完了)
  - 設計書(要望 117)・`docs/requests.md`・`docs/request-history.md`・`docs/superpowers/README.md`の状態を、`実装済み(実機確認待ち。ブランチ feature/assignment-scroll-sync)`にし、計画へのリンクを足す
- [ ] **Step 2: 検証する**(全テストは流さない。smoke が失敗したときだけ流す)

Run: `uv run pytest -m smoke -q`
Expected: 全件 PASS(失敗したら、そのときに限って`uv run pytest -n auto -q`)

Run: `uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: ruff は問題なし。ty は`dashboard_view.py`の`days_text`の 1 件だけ

- [ ] **Step 3: コミット**

```bash
git add -A .claude README.md docs
git commit -m "docs: 割り当て表の横スクロール連動を仕様・文書に反映する(要望 117)"
```

実機で確認してもらう項目(ブラウザなしでは確かめられない): チャートを動かすと表がついてくる・表を動かすとチャートがついてくる・日次/週次/月次で同じ日の列が縦に揃う・ループや震えがない・名前欄の幅をドラッグして離すと表の担当者列が追従する・`当日`への移動で表も動く・拡大/縮小でも揃う・タスクを選んでも(表が描き直されても)横位置が戻らない・担当者列が左に固定され背景が透けない(ダークテーマも)・長い名前が`…`になりホバーで全文が出る・日次の 3 桁の数字が列に収まる。
