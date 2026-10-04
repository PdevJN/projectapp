# ドラッグ&ドロップ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートで、タスクの行をドラッグして移動・コピーし、日次スケールではバーを横にドラッグして開始予定をずらせるようにする。

**Architecture:** 「何をどう変えるか」は NiceGUI に依存しない純粋関数(`arrange.py`)にする。行は HTML5 の drag、バーは pointer イベントで、JS は 1 つのスクリプト(`gantt_drag.py`の定数)にまとめて `document` に委譲で取り付け、結果だけを `emitEvent`(`chart_move`・`chart_shift`)で Python に返す。`GanttChart` が値を検証して `GanttActions` に渡し、`MainView` が `Project` を書き換えて再描画する。

**Tech Stack:** Python 3.13、NiceGUI 3.17(`ui.on`、`ui.add_head_html`、`ui.add_css`、`nicegui.testing.User`)、pytest(`asyncio_mode = "auto"`)、ty。

**Spec:** `docs/superpowers/specs/2026-10-04-drag-and-drop-design.md`

## Global Constraints

- 言語は日本語。UI の文言も日本語。
- Python 3.13 以上。すべての関数に型引数と戻り値の型を書く(`uvx ty check src` が通ること)。
- コメントは3行以内。
- 行の縦移動は、セクションをまたぐ移動を含む。コピーは Alt/Option を押しながらドロップ。
- コピーしたタスクは、名前の末尾に「(コピー)」を付け、`predecessors` は空にし、それ以外は全項目を複製する。
- バーの横移動は日次スケールだけ。開始予定を日単位でずらし、手指定を含め `planned_end` が入っていれば同じ日数ずらす。締切は動かさない。
- 絞り込み中は、行の移動とコピーを無効にする。バーの横移動は絞り込み中も使える。
- 取り消し(元に戻す)は付けない。保存は自動では行わない。「編集中」の判定は既存の `asdict(project)` と `snapshot` の比較に任せる。
- 年は 2000〜2100(`models.MIN_YEAR` / `MAX_YEAR`)。範囲を超えるずらしは、何も書き換えず通知する。
- テストは `uv run pytest -q`、型チェックは `uvx ty check src`。開始時点で 572 件が通る。テストは `test/` に置く。
- ブランチは `feature/drag-and-drop`(`develop` から作る)。コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。プッシュはしない。

## Review Focus

- 空のセクション・空のセクションなし一覧への移動とコピー → 見出し(または追加行)に落とすと末尾に入る(Task 2・Task 4)。
- 再描画との行き違いで、範囲外・型の誤り(文字列、真偽値、小数)・巨大な日数のイベントが届く → 何もせず、通知もせず、データを壊さない(Task 2・Task 3)。
- 年が 2000〜2100 を超えるずらし(開始予定は範囲内で、完了予定だけ超える場合を含む) → 何も書き換えず、「日付の範囲を超えるため動かせません」と通知する(Task 2・Task 3)。
- 同じ位置・すぐ隣への移動 → 何も変わらず、再描画もせず、「編集中」にもならない(Task 2・Task 3)。
- バーを実際に動かしたあと → 編集ダイアログが開かない。動かさずにクリックしたときは開く。絞り込み中は行の `draggable` が付かない(Task 4・Task 5・Task 6 の実機確認)。

## ファイル構成

- 新規 `src/projectapp/arrange.py`: `move_task` / `copy_task` / `shift_task`、位置の検査(`has_task`・`has_list`)、JS から届く値の検証(`parse_move`・`parse_shift`)。NiceGUI に依存しない。
- 新規 `src/projectapp/gantt_drag.py`: 行・バーの JS(`CHART_DRAG_JS`)と、落とす位置の表示の CSS(`CHART_DRAG_CSS`)の定数だけ。
- 変更 `src/projectapp/gantt.py`: `GanttActions` に 2 つ足す。`data-*` 属性・`draggable`、`ui.on`、`handle_move` / `handle_shift`。
- 変更 `src/projectapp/views.py`: `MainView.move_task` / `shift_task`、`GanttActions` への配線。
- 新規 `test/test_arrange.py`、`test/test_gantt_drag.py`、変更 `test/test_gantt.py`(`Recorder`)、`test/test_views.py`。
- 変更 `docs/development.md`(モジュール構成)、`.claude/MEMORY.md`(作業記録)。

---

### Task 1: ブランチと、Option を押した drag の試作(使い捨て)

設計書のリスク: macOS の WebView(pywebview の WKWebView)で、Option を押した drag の `altKey` が `drop` で取れるか。取れなければ、行の drag は pointer イベントに切り替える必要があり、**この計画は Task 4 の前で止めて、利用者に知らせる**。

**Files:**
- Create(コミットしない): `.superpowers/probe_alt_drag.py`(`.superpowers/` は `.git/info/exclude` で除外済み)

- [ ] **Step 1: ブランチを切る**

```bash
git switch develop
git switch -c feature/drag-and-drop
```

- [ ] **Step 2: 試作を書く**

```python
"""Option を押した drag の altKey が、drop で取れるかを確かめる使い捨て。"""

from nicegui import ui

PAGE = """
<div id="src" draggable="true"
  ondragstart="event.dataTransfer.setData('text/plain','x'); event.dataTransfer.effectAllowed='copyMove'"
  style="border:1px solid gray;padding:12px;width:240px;margin:12px">ドラッグ元(Option を押して動かす)</div>
<div id="dst" style="border:2px dashed gray;padding:24px;width:240px;margin:12px">ここに落とす</div>
<div id="out" style="margin:12px">未実行</div>
<script>
document.addEventListener('dragover', e => {
  e.preventDefault();
  e.dataTransfer.dropEffect = e.altKey ? 'copy' : 'move';
});
document.addEventListener('drop', e => {
  e.preventDefault();
  document.getElementById('out').textContent =
    'drop altKey=' + e.altKey + ' dropEffect=' + e.dataTransfer.dropEffect;
});
</script>
"""


@ui.page("/")
def index() -> None:
    ui.html(PAGE, sanitize=False)


ui.run(native=True, reload=False, window_size=(520, 360), title="alt drag probe")
```

- [ ] **Step 3: 実機で確かめる(利用者に依頼する)**

Run: `uv run python .superpowers/probe_alt_drag.py`

利用者に次を確認してもらう:
1. 「ドラッグ元」を、Option を**押さずに**「ここに落とす」へ落とす → 下に `drop altKey=false` と出る。
2. 「ドラッグ元」を、Option を**押しながら**落とす → `drop altKey=true` と出る(カーソルに「+」が付けば、なお良い)。

Expected: 1 は `false`、2 は `true`。

- 2 が `false` のままなら、**ここで止める**。利用者に結果を伝え、行の drag を pointer イベントで作る設計の変更(設計書「リスクと最初にやること」)を相談する。
- 取れたら、試作を削除して先に進む。

- [ ] **Step 4: 試作を削除する**

```bash
rm .superpowers/probe_alt_drag.py
git status --short
```

Expected: 何も表示されない(試作はコミットしていない)。

---

### Task 2: データ操作と値の検証(`arrange.py`)

**Files:**
- Create: `src/projectapp/arrange.py`
- Test: `test/test_arrange.py`

**Interfaces:**
- Consumes: `projectapp.models` の `Project`・`Section`・`Task`・`MIN_YEAR`・`MAX_YEAR`。
- Produces(Task 3・4・5 が使う):
  - `Position = tuple[int | None, int]`(セクション番号または `None`、番号)
  - `COPY_SUFFIX = "(コピー)"`、`MAX_SHIFT_DAYS = 3650`
  - `tasks_at(project: Project, section: int | None) -> list[Task]`
  - `has_task(project: Project, position: Position) -> bool`
  - `has_list(project: Project, position: Position) -> bool`(セクション番号が有効で、番号が 0 以上)
  - `move_task(project: Project, src: Position, dst: Position) -> bool`
  - `copy_task(project: Project, src: Position, dst: Position) -> Task`
  - `shift_task(task: Task, days: int) -> bool`
  - `parse_position(value: object) -> Position | None`
  - `parse_move(args: object) -> tuple[Position, Position, bool] | None`
  - `parse_shift(args: object) -> tuple[Position, int] | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_arrange.py`:

```python
from dataclasses import replace
from datetime import datetime

from projectapp import arrange
from projectapp.models import Priority, Project, Section, Status, Task


def names(tasks: list[Task]) -> list[str]:
    return [t.name for t in tasks]


def sample() -> Project:
    return Project(
        "p",
        tasks=[Task("t0"), Task("t1")],
        sections=[
            Section("A", [Task("a0"), Task("a1"), Task("a2")]),
            Section("B", []),
        ],
    )


def test_has_task_and_has_list() -> None:
    project = sample()
    assert arrange.has_task(project, (0, 2))
    assert arrange.has_task(project, (None, 1))
    assert not arrange.has_task(project, (0, 3))
    assert not arrange.has_task(project, (0, -1))
    assert not arrange.has_task(project, (2, 0))
    assert not arrange.has_task(project, (-1, 0))
    assert arrange.has_list(project, (1, 0))
    assert arrange.has_list(project, (None, 99))  # 番号は末尾に丸めるので大きくてよい
    assert not arrange.has_list(project, (0, -1))
    assert not arrange.has_list(project, (2, 0))
    assert not arrange.has_list(project, (-1, 0))


def test_move_forward_within_a_section_adjusts_the_index() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 0), (0, 3))  # 末尾へ
    assert names(project.sections[0].tasks) == ["a1", "a2", "a0"]
    project = sample()
    assert arrange.move_task(project, (0, 0), (0, 2))  # a1 の後ろ
    assert names(project.sections[0].tasks) == ["a1", "a0", "a2"]


def test_move_backward_within_a_section() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 2), (0, 0))
    assert names(project.sections[0].tasks) == ["a2", "a0", "a1"]


def test_move_to_the_same_place_or_right_next_to_it_changes_nothing() -> None:
    project = sample()
    assert not arrange.move_task(project, (0, 1), (0, 1))
    assert not arrange.move_task(project, (0, 1), (0, 2))
    assert names(project.sections[0].tasks) == ["a0", "a1", "a2"]


def test_move_across_sections_and_to_an_empty_section() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 1), (1, 0))
    assert names(project.sections[0].tasks) == ["a0", "a2"]
    assert names(project.sections[1].tasks) == ["a1"]


def test_move_between_the_top_list_and_sections() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 0), (None, 1))
    assert names(project.tasks) == ["t0", "a0", "t1"]
    assert arrange.move_task(project, (None, 0), (0, 1))
    assert names(project.tasks) == ["a0", "t1"]
    assert names(project.sections[0].tasks) == ["a1", "t0", "a2"]


def test_move_within_the_top_list() -> None:
    project = sample()
    assert arrange.move_task(project, (None, 0), (None, 2))
    assert names(project.tasks) == ["t1", "t0"]


def test_move_clamps_an_out_of_range_insert_index_to_the_end() -> None:
    project = sample()
    assert arrange.move_task(project, (0, 0), (1, 99))
    assert names(project.sections[1].tasks) == ["a0"]


def test_copy_adds_a_suffix_clears_predecessors_and_keeps_the_rest() -> None:
    project = sample()
    original = project.sections[0].tasks[1]
    original.predecessors.append("a0")
    original.planned_start = datetime(2026, 10, 5, 9)
    original.effort_hours = 12.0
    original.priority = Priority.HIGH
    original.status = Status.PAUSED
    original.assignee = "田中"
    original.allocation = 0.5
    original.color = "#ff0000"
    copy = arrange.copy_task(project, (0, 1), (1, 0))
    assert project.sections[1].tasks == [copy]
    assert copy is not original
    assert copy.name == "a1(コピー)"
    assert copy.predecessors == []
    assert original.predecessors == ["a0"]
    assert original.name == "a1"
    assert replace(copy, name="a1", predecessors=["a0"]) == original
    assert names(project.sections[0].tasks) == ["a0", "a1", "a2"]


def test_copy_inserts_at_the_position_and_clamps() -> None:
    project = sample()
    arrange.copy_task(project, (None, 0), (None, 1))
    assert names(project.tasks) == ["t0", "t0(コピー)", "t1"]
    arrange.copy_task(project, (None, 0), (0, 99))
    assert names(project.sections[0].tasks)[-1] == "t0(コピー)"


def test_shift_moves_start_and_end_and_keeps_deadline_and_time() -> None:
    task = Task(
        "x",
        planned_start=datetime(2026, 10, 5, 9, 30),
        planned_end=datetime(2026, 10, 7, 17, 45),
        deadline=datetime(2026, 10, 9, 12),
    )
    assert arrange.shift_task(task, 3)
    assert task.planned_start == datetime(2026, 10, 8, 9, 30)
    assert task.planned_end == datetime(2026, 10, 10, 17, 45)
    assert task.deadline == datetime(2026, 10, 9, 12)


def test_shift_backward_and_without_an_end() -> None:
    task = Task("x", planned_start=datetime(2026, 10, 5, 9))
    assert arrange.shift_task(task, -2)
    assert task.planned_start == datetime(2026, 10, 3, 9)
    assert task.planned_end is None


def test_shift_without_a_start_does_nothing() -> None:
    task = Task("x", planned_end=datetime(2026, 10, 7))
    assert not arrange.shift_task(task, 1)
    assert task.planned_end == datetime(2026, 10, 7)


def test_shift_out_of_the_year_range_writes_nothing() -> None:
    task = Task("x", planned_start=datetime(2100, 12, 31, 9))
    assert not arrange.shift_task(task, 1)
    assert task.planned_start == datetime(2100, 12, 31, 9)
    assert not arrange.shift_task(task, 10**10)  # timedelta 自体が溢れる
    assert task.planned_start == datetime(2100, 12, 31, 9)


def test_shift_is_atomic_when_only_the_end_goes_out_of_range() -> None:
    task = Task(
        "x",
        planned_start=datetime(2100, 12, 20, 9),
        planned_end=datetime(2100, 12, 31, 18),
    )
    assert not arrange.shift_task(task, 1)
    assert task.planned_start == datetime(2100, 12, 20, 9)
    assert task.planned_end == datetime(2100, 12, 31, 18)


def test_parse_position() -> None:
    assert arrange.parse_position([None, 0]) == (None, 0)
    assert arrange.parse_position([2, 5]) == (2, 5)
    assert arrange.parse_position((1, 0)) == (1, 0)
    for bad in (None, 3, "ab", [1], [1, 2, 3], ["0", 1], [True, 1], [0, 1.5], [0, "1"], [0, True]):
        assert arrange.parse_position(bad) is None


def test_parse_move() -> None:
    ok = {"src": [0, 1], "dst": [None, 2], "copy": True}
    assert arrange.parse_move(ok) == ((0, 1), (None, 2), True)
    assert arrange.parse_move({**ok, "copy": False}) == ((0, 1), (None, 2), False)
    assert arrange.parse_move({**ok, "copy": 1}) is None
    assert arrange.parse_move({**ok, "src": "x"}) is None
    assert arrange.parse_move({"src": [0, 1], "copy": False}) is None
    assert arrange.parse_move([1, 2]) is None
    assert arrange.parse_move(None) is None


def test_parse_shift_accepts_integers_within_the_limit_only() -> None:
    assert arrange.parse_shift({"si": None, "ti": 0, "days": -3}) == ((None, 0), -3)
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": 3650}) == ((1, 2), 3650)
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": 3651}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": -3651}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": 1.5}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": True}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2, "days": "3"}) is None
    assert arrange.parse_shift({"si": 1, "ti": 2}) is None
    assert arrange.parse_shift("x") is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_arrange.py -q`
Expected: FAIL(`ImportError: cannot import name 'arrange'`)

- [ ] **Step 3: 実装する**

`src/projectapp/arrange.py`:

```python
"""タスクの移動・コピー・日程のずらし(純粋関数)と、画面から届く値の検証。"""

from dataclasses import replace
from datetime import timedelta

from projectapp.models import MAX_YEAR, MIN_YEAR, Project, Task

Position = tuple[int | None, int]  # (セクション番号。Noneはセクションなし, 番号)
COPY_SUFFIX = "(コピー)"
MAX_SHIFT_DAYS = 3650


def tasks_at(project: Project, section: int | None) -> list[Task]:
    return project.tasks if section is None else project.sections[section].tasks


def valid_section(project: Project, section: int | None) -> bool:
    return section is None or 0 <= section < len(project.sections)


def has_task(project: Project, position: Position) -> bool:
    section, index = position
    return valid_section(project, section) and 0 <= index < len(tasks_at(project, section))


def has_list(project: Project, position: Position) -> bool:
    """挿入先として使えるか。番号は末尾に丸めるので、0 以上ならよい。"""
    section, index = position
    return valid_section(project, section) and index >= 0


def move_task(project: Project, src: Position, dst: Position) -> bool:
    """`dst` の番号は、取り除く前の一覧での挿入位置。位置が変わらないときは False。"""
    source = tasks_at(project, src[0])
    target = tasks_at(project, dst[0])
    index = min(dst[1], len(target))
    if source is target:
        if index in (src[1], src[1] + 1):
            return False
        if index > src[1]:
            index -= 1
    target.insert(index, source.pop(src[1]))
    return True


def copy_task(project: Project, src: Position, dst: Position) -> Task:
    original = tasks_at(project, src[0])[src[1]]
    copy = replace(original, name=f"{original.name}{COPY_SUFFIX}", predecessors=[])
    target = tasks_at(project, dst[0])
    target.insert(min(dst[1], len(target)), copy)
    return copy


def shift_task(task: Task, days: int) -> bool:
    """開始予定と、入っていれば完了予定を同じ日数ずらす(締切は動かさない)。範囲外なら何も書き換えない。"""
    if task.planned_start is None:
        return False
    try:
        delta = timedelta(days=days)
        start = task.planned_start + delta
        end = None if task.planned_end is None else task.planned_end + delta
    except OverflowError:
        return False
    for moment in (start, end):
        if moment is not None and not MIN_YEAR <= moment.year <= MAX_YEAR:
            return False
    task.planned_start, task.planned_end = start, end
    return True


def as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_position(value: object) -> Position | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    section, raw_index = value
    index = as_int(raw_index)
    if index is None:
        return None
    if section is None:
        return None, index
    number = as_int(section)
    return None if number is None else (number, index)


def parse_move(args: object) -> tuple[Position, Position, bool] | None:
    if not isinstance(args, dict):
        return None
    src = parse_position(args.get("src"))
    dst = parse_position(args.get("dst"))
    copy = args.get("copy")
    if src is None or dst is None or not isinstance(copy, bool):
        return None
    return src, dst, copy


def parse_shift(args: object) -> tuple[Position, int] | None:
    if not isinstance(args, dict):
        return None
    position = parse_position([args.get("si"), args.get("ti")])
    days = as_int(args.get("days"))
    if position is None or days is None or abs(days) > MAX_SHIFT_DAYS:
        return None
    return position, days
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_arrange.py -q && uvx ty check src`
Expected: すべて PASS、`All checks passed!`

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/arrange.py test/test_arrange.py
git commit -m "$(cat <<'EOF'
タスクの移動・コピー・日程のずらしと、届く値の検証を追加

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `GanttActions` と `MainView` の処理

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions`)
- Modify: `src/projectapp/views.py`(`MainView.move_task` / `shift_task`、配線)
- Modify: `test/test_gantt.py`(`Recorder`)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 2 の `arrange`。
- Produces(Task 4・5 が使う):
  - `GanttActions.move_task: Callable[[Position, Position, bool], object]`(`src`, `dst`, `copy`)
  - `GanttActions.shift_task: Callable[[int | None, int, int], object]`(セクション番号, 番号, 日数)
  - `MainView.move_task(src, dst, copy) -> None`、`MainView.shift_task(section, index, days) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` に追加(`mount_capturing` を使う。`datetime` と `Section` と `Task` は import 済み。`Project` も同様):

```python
async def test_move_task_moves_marks_dirty_and_redraws(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("開発")
    view.project.tasks.append(Task("上"))
    view.project.sections[0].tasks.extend([Task("a"), Task("b")])
    view.mark_clean()
    view.move_task((0, 0), (None, 1), False)
    assert [t.name for t in view.project.tasks] == ["上", "a"]
    assert [t.name for t in view.project.sections[0].tasks] == ["b"]
    assert view.is_dirty()
    await user.should_see(marker="task-top-1")


async def test_move_task_to_the_same_place_does_nothing(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.extend([Task("a"), Task("b")])
    view.mark_clean()
    view.move_task((None, 0), (None, 1), False)
    assert [t.name for t in view.project.tasks] == ["a", "b"]
    assert not view.is_dirty()


async def test_move_task_with_stale_positions_is_ignored(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(Task("a"))
    view.mark_clean()
    view.move_task((None, 5), (None, 0), False)
    view.move_task((3, 0), (None, 0), False)
    view.move_task((None, 0), (7, 0), False)
    view.move_task((None, 0), (None, -1), True)
    assert [t.name for t in view.project.tasks] == ["a"]
    assert not view.is_dirty()


async def test_copy_task_adds_a_copy_and_notifies(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.save_section("開発")
    view.project.tasks.append(Task("設計"))
    view.mark_clean()
    view.move_task((None, 0), (0, 0), True)
    assert [t.name for t in view.project.tasks] == ["設計"]
    assert [t.name for t in view.project.sections[0].tasks] == ["設計(コピー)"]
    assert view.is_dirty()
    await user.should_see("「設計」をコピーしました")


async def test_shift_task_moves_the_dates_and_marks_dirty(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(
        Task("a", planned_start=datetime(2026, 10, 5, 9), deadline=datetime(2026, 10, 9))
    )
    view.mark_clean()
    view.shift_task(None, 0, 2)
    task = view.project.tasks[0]
    assert task.planned_start == datetime(2026, 10, 7, 9)
    assert task.deadline == datetime(2026, 10, 9)
    assert view.is_dirty()


async def test_shift_task_ignores_zero_and_stale_positions(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(Task("a", planned_start=datetime(2026, 10, 5, 9)))
    view.mark_clean()
    view.shift_task(None, 0, 0)
    view.shift_task(None, 4, 1)
    view.shift_task(2, 0, 1)
    assert view.project.tasks[0].planned_start == datetime(2026, 10, 5, 9)
    assert not view.is_dirty()


async def test_shift_task_out_of_the_year_range_notifies_and_keeps_the_dates(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks.append(Task("a", planned_start=datetime(2100, 12, 31, 9)))
    view.mark_clean()
    view.shift_task(None, 0, 1)
    assert view.project.tasks[0].planned_start == datetime(2100, 12, 31, 9)
    assert not view.is_dirty()
    await user.should_see("日付の範囲を超えるため動かせません")


async def test_shift_task_warns_when_the_assignee_goes_over_100_percent(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.apply_members([Member("田中")], {})
    first = Task("a", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5, assignee="田中")
    second = Task("b", planned_start=datetime(2026, 10, 6, 9), effort_hours=6.5, assignee="田中")
    view.project.tasks.extend([first, second])
    view.shift_task(None, 1, -1)  # 同じ日に重なる(割り当て 100% + 100%)
    await user.should_see("田中 の割り当てが最大200%になる期間があります")
```

`test/test_gantt.py` の `Recorder` を、2 つの操作を受けるように変える:

```python
class Recorder:
    """操作のコールバックを記録する。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[object, ...]]] = []
        self.actions = GanttActions(
            add_section=lambda: self.events.append(("add_section", ())),
            add_task=lambda si: self.events.append(("add_task", (si,))),
            add_top_task=lambda: self.events.append(("add_top_task", ())),
            edit_task=lambda si, ti: self.events.append(("edit_task", (si, ti))),
            move_task=lambda src, dst, copy: self.events.append(("move_task", (src, dst, copy))),
            shift_task=lambda si, ti, days: self.events.append(("shift_task", (si, ti, days))),
        )
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k "move_task or copy_task or shift_task"`
Expected: FAIL(`MainView` に `move_task` がない)。`test_gantt.py` は `GanttActions` の引数不足で FAIL する。

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py` の import に `from projectapp.arrange import Position` を足し、`GanttActions` を変える:

```python
@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[int], object]
    add_top_task: Callable[[], object]
    edit_task: Callable[[int | None, int], object]  # セクション番号(Noneはセクションなし), タスク番号
    move_task: Callable[[Position, Position, bool], object]  # 元, 挿入先, コピーか
    shift_task: Callable[[int | None, int, int], object]  # セクション番号, タスク番号, 日数
```

`src/projectapp/views.py`: import に `from projectapp import arrange` を足す。`GanttActions(...)` の引数に `move_task=self.move_task, shift_task=self.shift_task,` を足す。`delete_task` の後に追加する:

```python
    def move_task(self, src: arrange.Position, dst: arrange.Position, copy: bool) -> None:
        """行を動かす(copy が真なら複製を置く)。位置が不正・変化なしなら何もしない。"""
        if not arrange.has_task(self.project, src) or not arrange.has_list(self.project, dst):
            return
        name = arrange.tasks_at(self.project, src[0])[src[1]].name
        if copy:
            arrange.copy_task(self.project, src, dst)
            ui.notify(f"「{name}」をコピーしました")
        elif not arrange.move_task(self.project, src, dst):
            return
        self.gantt.set_project(self.project)

    def shift_task(self, section_index: int | None, task_index: int, days: int) -> None:
        """開始予定(と入っていれば完了予定)を days 日ずらす。締切は動かさない。"""
        if days == 0 or not arrange.has_task(self.project, (section_index, task_index)):
            return
        task = self.tasks_in(section_index)[task_index]
        if not arrange.shift_task(task, days):
            if task.planned_start is not None:
                ui.notify("日付の範囲を超えるため動かせません", type="warning")
            return
        self.gantt.set_project(self.project)
        self.warn_overallocation(task)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: すべて PASS(572 件 + Task 2 の分 + 追加分)、`All checks passed!`

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/gantt.py src/projectapp/views.py test/test_gantt.py test/test_views.py
git commit -m "$(cat <<'EOF'
行の移動・コピーとバーの横移動を MainView で受ける

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 行の縦移動とコピー(画面と JS)

**Files:**
- Create: `src/projectapp/gantt_drag.py`
- Modify: `src/projectapp/gantt.py`(`build`、`task_row`、`section_rows`、`top_add_row`、`handle_move`)
- Test: `test/test_gantt_drag.py`

**Interfaces:**
- Consumes: `arrange.parse_move`、`GanttActions.move_task`(Task 2・3)。
- Produces(Task 5 が使う): `gantt_drag.CHART_DRAG_JS`(Task 5 でバーの処理を足す)、`gantt_drag.CHART_DRAG_CSS`、`GanttChart.handle_move(args: object) -> None`。
- 属性の約束(JS と Python で共有): ドロップ先は `data-drop`(`row` / `section` / `top-end`)、`data-si`(セクション番号か `top`)、`data-ti`(行のみ)、`data-count`(見出し・追加行のみ。そのセクションのタスク数)。つかむ場所は `draggable=true` と `data-drag-handle`、`data-si`、`data-ti`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt_drag.py`:

```python
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.filtering import TaskFilter
from projectapp.gantt import GanttChart
from projectapp.gantt_drag import CHART_DRAG_JS
from projectapp.models import Project, Section, Task
from test_gantt import BASE, Recorder


def project_with_top() -> Project:
    return Project(
        "demo",
        base_date=BASE,
        tasks=[Task("上1"), Task("上2")],
        sections=[
            Section("開発", [Task("設計", planned_start=datetime(2026, 10, 5, 9))]),
            Section("空", []),
        ],
    )


def mount(project: Project) -> tuple[Recorder, list[GanttChart]]:
    recorder = Recorder()
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, recorder.actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    return recorder, charts


def props_of(user: User, marker: str) -> dict:
    return user.find(marker=marker).elements.pop().props


async def test_task_labels_are_draggable_handles_and_rows_are_drop_targets(user: User) -> None:
    mount(project_with_top())
    await user.open("/")
    label = props_of(user, "task-top-1")
    assert label["draggable"] == "true"
    assert "data-drag-handle" in label
    assert (label["data-si"], label["data-ti"]) == ("top", 1)
    label = props_of(user, "task-0-0")
    assert (label["data-si"], label["data-ti"]) == (0, 0)
    row = props_of(user, "row-0-0")
    assert row["data-drop"] == "row"
    assert (row["data-si"], row["data-ti"]) == (0, 0)


async def test_section_headers_and_the_top_add_row_are_drop_targets_with_counts(
    user: User,
) -> None:
    mount(project_with_top())
    await user.open("/")
    section = props_of(user, "section-1")
    assert section["data-drop"] == "section"
    assert (section["data-si"], section["data-count"]) == (1, 0)
    assert props_of(user, "section-0")["data-count"] == 1
    top = props_of(user, "top-end")
    assert top["data-drop"] == "top-end"
    assert (top["data-si"], top["data-count"]) == ("top", 2)


async def test_no_drag_attributes_while_filtering(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="上"))
    await user.should_see(marker="task-top-0")
    label = props_of(user, "task-top-0")
    assert "draggable" not in label
    assert "data-drag-handle" not in label
    assert "data-drop" not in props_of(user, "row-top-0")
    assert "data-drop" not in props_of(user, "top-end")


async def test_handle_move_passes_valid_events_to_the_action(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_move({"src": [None, 0], "dst": [0, 1], "copy": True})
    assert recorder.events == [("move_task", ((None, 0), (0, 1), True))]


async def test_handle_move_ignores_bad_events_and_filtering(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_move({"src": "x", "dst": [0, 1], "copy": True})
    charts[0].handle_move({"src": [None, 0], "dst": [0, 1], "copy": "yes"})
    charts[0].handle_move(None)
    charts[0].set_filter(TaskFilter(query="上"))
    charts[0].handle_move({"src": [None, 0], "dst": [0, 1], "copy": False})
    assert recorder.events == []


def test_the_script_is_valid_javascript(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので構文を確かめない")
    script = tmp_path / "drag.js"
    script.write_text(CHART_DRAG_JS, encoding="utf-8")
    result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_script_emits_the_events_the_python_side_listens_to() -> None:
    assert 'emitEvent("chart_move"' in CHART_DRAG_JS
```

注: `from test_gantt import BASE, Recorder` は、`test/` に `__init__.py` がないため、rootdir 基準の import が通るかを実行して確かめる。通らなければ、`BASE`(`date(2026, 10, 5)`)と `Recorder` を `test_gantt_drag.py` 内に複製してよい(複製した場合も `Recorder` は Task 3 の形に合わせる)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt_drag.py -q`
Expected: FAIL(`projectapp.gantt_drag` がない)

- [ ] **Step 3: JS と CSS を書く**

`src/projectapp/gantt_drag.py`:

```python
"""ガントチャートのドラッグ操作用の JS と CSS(定数のみ)。

行は HTML5 の drag、バーは pointer イベント(Task 5)。要素の `data-*` 属性を読み、
結果だけを emitEvent で Python に返す。`render` が作り直されるので、document に委譲する。
"""

CHART_DRAG_CSS = """
.drop-before { box-shadow: inset 0 3px 0 0 #1976d2; }
.drop-after { box-shadow: inset 0 -3px 0 0 #1976d2; }
.drop-into { outline: 2px solid #1976d2; outline-offset: -2px; }
[data-drag-handle] { cursor: grab; }
"""

CHART_DRAG_JS = """
(() => {
  if (window.__ganttDragInstalled) return;
  window.__ganttDragInstalled = true;
  const section = (value) => (value === "top" ? null : Number(value));
  let source = null;

  const clearMarks = () => {
    document.querySelectorAll(".drop-before, .drop-after, .drop-into").forEach((el) => {
      el.classList.remove("drop-before", "drop-after", "drop-into");
    });
  };
  const upperHalf = (el, event) => {
    const rect = el.getBoundingClientRect();
    return event.clientY < rect.top + rect.height / 2;
  };
  const target = (event) => (event.target.closest ? event.target.closest("[data-drop]") : null);

  document.addEventListener("dragstart", (event) => {
    const handle = event.target.closest ? event.target.closest("[data-drag-handle]") : null;
    if (!handle) return;
    source = [section(handle.dataset.si), Number(handle.dataset.ti)];
    event.dataTransfer.effectAllowed = "copyMove";
    event.dataTransfer.setData("text/plain", handle.textContent || "");
  });

  document.addEventListener("dragover", (event) => {
    const el = source ? target(event) : null;
    if (!el) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = event.altKey ? "copy" : "move";
    clearMarks();
    if (el.dataset.drop === "row") {
      el.classList.add(upperHalf(el, event) ? "drop-before" : "drop-after");
    } else {
      el.classList.add("drop-into");
    }
  });

  document.addEventListener("drop", (event) => {
    const el = source ? target(event) : null;
    if (!el) return;
    event.preventDefault();
    const index = el.dataset.drop === "row"
      ? Number(el.dataset.ti) + (upperHalf(el, event) ? 0 : 1)
      : Number(el.dataset.count);
    const message = {
      src: source,
      dst: [section(el.dataset.si), index],
      copy: event.altKey,
    };
    clearMarks();
    source = null;
    emitEvent("chart_move", message);
  });

  document.addEventListener("dragend", () => {
    clearMarks();
    source = null;
  });
})();
"""
```

- [ ] **Step 4: 画面を実装する**

`src/projectapp/gantt.py`:

import に `from projectapp import arrange` と `from projectapp.gantt_drag import CHART_DRAG_CSS, CHART_DRAG_JS` を足す。

`build` の先頭(`self.client = context.client` の次)に、ドラッグの準備を足す:

```python
        ui.add_css(CHART_DRAG_CSS)
        ui.add_head_html(f"<script>{CHART_DRAG_JS}</script>")
        ui.on("chart_move", lambda e: self.handle_move(e.args))
```

`reset_filter` の前あたりに、メソッドを足す:

```python
    def handle_move(self, args: object) -> None:
        """行のドロップを受ける。絞り込み中と、不正な値は無視する。"""
        if self.task_filter.active:
            return
        parsed = arrange.parse_move(args)
        if parsed is not None:
            self.actions.move_task(*parsed)

    def drag_props(self, kind: str, key: int | str, **extra: object) -> str:
        """ドロップ先の `data-*` 属性。絞り込み中は空(ドロップできない)。"""
        if self.task_filter.active:
            return ""
        parts = [f"data-drop={kind}", f"data-si={key}"]
        parts += [f"data-{name}={value}" for name, value in extra.items()]
        return " ".join(parts)
```

`top_add_row` の行に属性とマークを付ける:

```python
        row = ui.row().classes("items-center no-wrap gap-0").style(ADD_ROW_STYLE)
        row.props(self.drag_props("top-end", "top", count=len(self.project.tasks)))
        row.mark("top-end")
        with row:
            cell = ui.row().classes("items-center justify-end no-wrap")
            ...(以降は既存のまま)
```

`section_rows` の見出し行を変える:

```python
        header = ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE)
        header.props(self.drag_props("section", si, count=len(section.tasks)))
        header.mark(f"section-{si}")
        with header:
            ui.label(section.name).classes("text-subtitle2")
            ui.button(...)  # 既存のまま
```

`task_row` の行と名前のラベルを変える(`ui.row()` の結果を変数に受け、`with` で入る。ラベルの `props` は絞り込み中でないときだけ):

```python
        row = ui.row().classes("items-center no-wrap gap-0").style(style)
        row.props(self.drag_props("row", key, ti=ti)).mark(f"row-{key}-{ti}")
        with row:
            label = ui.label(task.name).classes("ellipsis cursor-pointer").style(
                f"width: {NAME_WIDTH_PX}px; padding-left: 16px"
            )
            label.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
            label.mark(f"task-{key}-{ti}")
            if not self.task_filter.active:
                label.props(f"draggable=true data-drag-handle data-si={key} data-ti={ti}")
            ...(以降の棒・締切は既存のまま、インデントを `with row:` の中に保つ)
```

注: `props("")` は何も足さない(空文字は無害)ことを、テストで確かめる(`test_no_drag_attributes_while_filtering`)。`props` の値が数値の `data-si=0` は、`props_of` で `0`(int)として返る場合と `"0"` の場合がありうる。テストが通らないときは、実際の値(`print(props)`)を見て、期待値の型をそろえる。`"top"` は文字列で返る。

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: すべて PASS(Node がなければ構文の確認はスキップ)、`All checks passed!`

- [ ] **Step 6: 実機で行の移動とコピーを確かめる(利用者に依頼する)**

Run: `uv run projectapp`

サンプルとして、セクション 2 つ(1 つは空)とセクションなしのタスク数件を作ってもらい、次を確認する。確認できない項目があれば、そこで止めて報告する。
1. 行を、同じセクション内の別の行の上半分・下半分に落とす → 線が出て、その位置に入る。
2. 別のセクションの行、見出し、空のセクションの見出しに落とす → そのセクションの末尾(行の上なら前)に入る。
3. 「タスク追加」の行に落とす → セクションなしの末尾に入る。
4. Option を押しながら落とす → 「(コピー)」付きの複製ができ、「コピーしました」と通知が出る。元は残る。
5. 動かしたあとに「編集中」の表示になる。
6. 名前をクリックすると、これまでどおり編集ダイアログが開く。
7. 検索で絞り込んでいる間は、行をつかめない。

- [ ] **Step 7: コミットする**

```bash
git add src/projectapp/gantt_drag.py src/projectapp/gantt.py test/test_gantt_drag.py
git commit -m "$(cat <<'EOF'
行のドラッグで移動・コピーできるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: バーの横移動(日次のみ)

**Files:**
- Modify: `src/projectapp/gantt_drag.py`(JS に pointer の処理を足す)
- Modify: `src/projectapp/gantt.py`(バーの属性、`handle_shift`)
- Test: `test/test_gantt_drag.py`

**Interfaces:**
- Consumes: `arrange.parse_shift`、`GanttActions.shift_task`(Task 2・3)、Task 4 の `ui.on` と JS。
- Produces: `GanttChart.handle_shift(args: object) -> None`。バーの属性は `data-bar`、`data-si`、`data-ti`、`data-day-width`(日次のみ)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt_drag.py` に追加:

```python
from projectapp.timeline import Scale


async def test_day_scale_bars_are_draggable_with_the_column_width(user: User) -> None:
    mount(project_with_top())
    await user.open("/")
    bar = props_of(user, "bar-0-0")
    assert "data-bar" in bar
    assert (bar["data-si"], bar["data-ti"], bar["data-day-width"]) == (0, 0, 40)
    assert "grab" in user.find(marker="bar-0-0").elements.pop()._style.get("cursor", "")


async def test_other_scales_have_no_draggable_bars(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_scale(Scale.WEEK)
    await user.should_see(marker="bar-0-0")
    assert "data-bar" not in props_of(user, "bar-0-0")
    charts[0].set_scale(Scale.MONTH)
    await user.should_see(marker="bar-0-0")
    assert "data-bar" not in props_of(user, "bar-0-0")


async def test_bars_stay_draggable_while_filtering(user: User) -> None:
    _, charts = mount(project_with_top())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="設計"))
    await user.should_see(marker="bar-0-0")
    assert "data-bar" in props_of(user, "bar-0-0")


async def test_handle_shift_passes_valid_events_on_the_day_scale(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_shift({"si": 0, "ti": 0, "days": -2})
    charts[0].handle_shift({"si": None, "ti": 1, "days": 5})
    assert recorder.events == [("shift_task", (0, 0, -2)), ("shift_task", (None, 1, 5))]


async def test_handle_shift_ignores_bad_events_and_other_scales(user: User) -> None:
    recorder, charts = mount(project_with_top())
    await user.open("/")
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 3651})
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 1.5})
    charts[0].handle_shift({"si": "0", "ti": 0, "days": 1})
    charts[0].handle_shift(None)
    charts[0].set_scale(Scale.WEEK)
    charts[0].handle_shift({"si": 0, "ti": 0, "days": 1})
    assert recorder.events == []


def test_the_script_has_the_bar_drag_pieces() -> None:
    assert 'emitEvent("chart_shift"' in CHART_DRAG_JS
    assert "pointerdown" in CHART_DRAG_JS
    assert "Escape" in CHART_DRAG_JS
```

注: `_style` は NiceGUI の `Element` の内部属性。取れなければ、`element.style` の文字列ではなく、`bar` の `_style` の代わりに `user.find(marker=...).elements.pop().style` が dict か確かめて合わせる。スタイルの確認が難しければ、このアサーションは外し、`data-bar` の確認だけにしてよい。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt_drag.py -q`
Expected: 追加分が FAIL

- [ ] **Step 3: JS を足す**

`src/projectapp/gantt_drag.py` の `CHART_DRAG_JS` の末尾(最後の `})();` の直前)に、次を足す:

```javascript
  // バーの横移動。1日分の列幅に吸着し、放したときに日数だけを送る。
  const MOVE_THRESHOLD_PX = 4;
  let bar = null;
  let suppressClick = false;

  document.addEventListener("pointerdown", (event) => {
    const el = event.target.closest ? event.target.closest("[data-bar]") : null;
    if (!el || event.button !== 0) return;
    bar = {
      el, x0: event.clientX, width: Number(el.dataset.dayWidth),
      moved: false, cancelled: false, days: 0,
    };
    el.setPointerCapture(event.pointerId);
  });

  document.addEventListener("pointermove", (event) => {
    if (!bar || bar.cancelled) return;
    const dx = event.clientX - bar.x0;
    if (!bar.moved && Math.abs(dx) < MOVE_THRESHOLD_PX) return;
    bar.moved = true;
    bar.days = Math.round(dx / bar.width);
    bar.el.style.transform = `translateX(${bar.days * bar.width}px)`;
  });

  document.addEventListener("pointerup", () => {
    if (!bar) return;
    const done = bar;
    bar = null;
    done.el.style.transform = "";
    if (!done.moved && !done.cancelled) return;
    suppressClick = true;  // 動かしたあとの click で編集ダイアログが開かないようにする
    setTimeout(() => { suppressClick = false; }, 0);
    if (!done.cancelled && done.days !== 0) {
      emitEvent("chart_shift", {
        si: section(done.el.dataset.si), ti: Number(done.el.dataset.ti), days: done.days,
      });
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !bar) return;
    bar.cancelled = true;
    bar.el.style.transform = "";
  });

  document.addEventListener("click", (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);
```

- [ ] **Step 4: 画面を実装する**

`src/projectapp/gantt.py`: `handle_move` の次にメソッドを足す:

```python
    def handle_shift(self, args: object) -> None:
        """バーの横移動を受ける。日次スケール以外と、不正な値は無視する。"""
        if self.scale is not Scale.DAY:
            return
        parsed = arrange.parse_shift(args)
        if parsed is not None:
            (section, index), days = parsed
            self.actions.shift_task(section, index, days)
```

`ui.on("chart_move", ...)` の次に `ui.on("chart_shift", lambda e: self.handle_shift(e.args))` を足す。

`task_row` の棒の要素を変える(`with ui.element("div").style(...)` の部分)。日次のときだけ `data-bar` などを付け、`cursor` を `grab` にする:

```python
                draggable = self.scale is Scale.DAY
                cursor = "grab" if draggable else "pointer"
                bar = ui.element("div").style(
                    f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                    f" width: {bar_width:.1f}px; top: 6px;"
                    f" height: {ROW_HEIGHT_PX - 12}px;"
                    f" background: {task.color if is_hex_color(task.color) else DEFAULT_COLOR};"
                    f" border-radius: 4px; cursor: {cursor}; overflow: hidden;"
                    " user-select: none; touch-action: none"
                )
                bar.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
                bar.mark(f"bar-{key}-{ti}")
                if draggable:
                    bar.props(f"data-bar data-si={key} data-ti={ti} data-day-width={width}")
                with bar:
                    self.overload_stripes(key, ti, task, left, bar_width, columns, width)
```

注: 既存の `style` は `cursor: pointer; overflow: hidden` を含んでいた。上の形に置き換えること(`cursor` を二重に書かない)。

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: すべて PASS、`All checks passed!`

- [ ] **Step 6: 実機でバーの横移動を確かめる(利用者に依頼する)**

Run: `uv run projectapp`(日次スケール)

1. バーを右・左へ動かす → 1 日分ずつ吸着して動き、放すと開始予定がずれる(締切の「◆」は動かない)。完了予定を手で指定したタスクは、終了も同じ日数ずれる。
2. 動かして元の位置(0 日)に戻して放す → 何も起きず、「編集中」にもならない。
3. 動かしている間に Esc → 元の位置に戻り、日程は変わらない。
4. 動かしたあとに、編集ダイアログが開かない。動かさずにクリックすると、開く。
5. 同じ担当者のタスクを重ねる → 「割り当てが最大…%になる期間があります」と通知が出る。
6. 週次・月次に切り替える → バーをつかめない(カーソルはポインターのまま)。クリックで編集は開く。
7. 検索で絞り込んでいる間も、バーは動かせる。

- [ ] **Step 7: コミットする**

```bash
git add src/projectapp/gantt_drag.py src/projectapp/gantt.py test/test_gantt_drag.py
git commit -m "$(cat <<'EOF'
日次スケールでバーを横にドラッグして開始予定をずらせるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: ドキュメントと作業記録

**Files:**
- Modify: `docs/development.md`(モジュール構成の表)
- Modify: `.claude/MEMORY.md`(作業記録)

- [ ] **Step 1: `docs/development.md` を更新する**

モジュール構成の表の `filtering.py` の行の次に、2 行足す:

```markdown
| `arrange.py` | タスクの移動(`move_task`)・コピー(`copy_task`)・日程のずらし(`shift_task`)と、画面から届く値の検証(`parse_move`・`parse_shift`)(純粋関数) |
| `gantt_drag.py` | ガントチャートのドラッグ操作用の JS と CSS(定数のみ。行は HTML5 の drag、バーは pointer イベント) |
```

`gantt.py` の行の説明に「、行のドラッグ移動・コピー、バーの横移動」を足す。

- [ ] **Step 2: `.claude/MEMORY.md` を更新する**

- 「最終更新」と「現在の状況」の先頭に、ドラッグ&ドロップをブランチ `feature/drag-and-drop` で実装済み(実機確認の結果、テスト件数、`ty check` の結果)と書く。設計書 `2026-10-04-drag-and-drop-design.md`、実装計画 `2026-10-04-drag-and-drop.md`。
- 「実装済みの機能」に、行のドラッグ(移動・Option でコピー)とバーの横移動(日次のみ)の要約を足す。
- 「次にやること(候補)」から、ドラッグ&ドロップを外す。

- [ ] **Step 3: 全体を確かめてコミットする**

Run: `uv run pytest -q && uvx ty check src`
Expected: すべて PASS、`All checks passed!`

```bash
git add docs/development.md .claude/MEMORY.md
git commit -m "$(cat <<'EOF'
作業記録: ドラッグ&ドロップの実装を記録

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: 仕上げ**

`superpowers:finishing-a-development-branch` に従い、`develop` へのマージ方法を利用者に確認する(マージとプッシュは、許可を得てから行う)。
