# タスク表示の拡張(ProjectCode・担当・進捗のチップと優先度の背景色) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートの名前の欄に、ProjectCode・担当者・進捗のチップを出し、優先度で名前の欄の背景に色を付ける。ProjectCode を、タスクのデータと編集ダイアログの入力に加える。

**Architecture:** `Task.project_code` を足して保存・入力する(Task 1・2)。名前の欄は、今のラベルを、同じマーカー・スタイル・クリック・ドラッグ属性を持つ横並びの枠(`ui.row`)に置き換え、名前を中の可変幅のラベルにする(Task 3)。優先度の色は CSS 変数 `--pbg`(状態の色 `--scolor` と同じ方式)で、枠の背景に使う(Task 3)。チップと進捗は枠の中に足す(Task 4)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、`uvx ty check src`

**Spec:** `docs/superpowers/specs/2026-10-05-task-chips-design.md`

## Global Constraints

- 言語は日本語。画面の文言・エラーは日本語。
- ProjectCode は、前後の空白を除いて最大 20 文字(`MAX_PROJECT_CODE_LENGTH = 20`)、空でもよい。保存のキーは `"project_code"`(空のときも `""` を出す)。キーなし・`null` は `""`。文字列以外と 20 文字超は、読込を拒否する(「開けませんでした」)。
- 名前の欄の幅 `NAME_WIDTH_PX = 200` と、行の高さは変えない。
- 優先度の背景色は、名前の欄の背景だけ。バー・行の背景・割り当て超過の縞・状態の色・点線は変えない。赤は使わない。
- 名前の欄の枠は、今のラベルのマーカー `task-<key>-<ti>`、スタイル(`position: sticky`、`left: 0px`、`z-index`、`align-self: stretch`)、クラス `gantt-sticky`、クリックで編集、ドラッグ属性(絞り込み中はなし)を引き継ぐ。枠は、行(`row-<key>-<ti>`)の直接の子にする(`row_background` が `parent_slot.parent` を行として読むため)。
- テストは `uv run pytest -q`(全体は約3〜4分。タスク中は対象のファイルだけ実行する)、型は `uvx ty check src`。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- 作業ブランチは `feature/task-chips`(`develop` から切ってある)。マージとプッシュは、ユーザーの許可を得てから。

## Review Focus

- ProjectCode が、ちょうど 20 文字は通り、21 文字は拒否される。空白だけは空になる。前後に空白のある 20 文字は通る(空白を除いたあとの長さで数える)。→ Task 1, 2
- 名前・ProjectCode・担当・進捗がすべて出るとき、名前が縮んで省略され、枠からはみ出さない(名前は `flex: 1 1 0; min-width: 0`、チップは `flex: none`)。→ Task 4
- チップや進捗を押しても、編集ダイアログが開く(枠のクリックに含まれる)。→ Task 4
- 絞り込み中は、チップがあっても、枠はドラッグできない。→ Task 3
- 予定超過のタスクの枠は、優先度の背景色の上に、赤みの `background-image` が重なる。→ Task 3
- 手で編集した、メンバーにいない担当者や、頭文字が複数のコードポイントの名前でも、描画が落ちない。→ Task 4

---

### Task 1: ProjectCode のデータと保存(`models.py`、`storage.py`)

**Files:**
- Modify: `src/projectapp/models.py`(`MAX_PROJECT_CODE_LENGTH`、`Task.project_code`)
- Modify: `src/projectapp/storage.py`(`_project_code`、`_task` で読む。保存は `asdict` が出す)
- Test: `test/test_storage.py`、`test/test_arrange.py`

**Interfaces:**
- Produces: `projectapp.models.MAX_PROJECT_CODE_LENGTH = 20`、`Task.project_code: str = ""`(`Task` の最後のフィールド)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の末尾に追加する(`json`、`pytest`、`Path`、`Project`、`Task`、`save_project`、`load_project` は既存のインポート)。

```python
def _project_with_code(code: str) -> Project:
    return Project("demo", tasks=[Task("t", project_code=code)])


def test_project_code_roundtrip(tmp_path: Path) -> None:
    loaded = load_project(save_project(_project_with_code("PRJ-001"), tmp_path))
    assert loaded.tasks[0].project_code == "PRJ-001"


def test_empty_project_code_is_saved_as_an_empty_string(tmp_path: Path) -> None:
    path = save_project(_project_with_code(""), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["project_code"] == ""


@pytest.mark.parametrize("missing", ["delete", "null"])
def test_file_without_project_code_loads_as_empty(tmp_path: Path, missing: str) -> None:
    path = save_project(_project_with_code("X"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if missing == "delete":
        del raw["tasks"][0]["project_code"]
    else:
        raw["tasks"][0]["project_code"] = None
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].project_code == ""


def test_project_code_is_trimmed_on_load(tmp_path: Path) -> None:
    path = save_project(_project_with_code("X"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["project_code"] = "  " + "A" * 20 + "  "
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).tasks[0].project_code == "A" * 20


@pytest.mark.parametrize("bad", ["A" * 21, 1, ["x"], True])
def test_invalid_project_code_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(_project_with_code("X"), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["project_code"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="ProjectCode"):
        load_project(path)
```

`test/test_arrange.py` の末尾に追加する(インポートは既存のものに合わせる。`copy_task`、`Project`、`Task` が未インポートなら足す)。

```python
def test_copy_keeps_the_project_code() -> None:
    project = Project("p", tasks=[Task("t", project_code="PRJ-1")])
    copy = copy_task(project, (None, 0), (None, 1))
    assert copy.project_code == "PRJ-1"
```

(`copy_task` の位置引数の型が違ってテストが型エラーになるときは、同じファイルの既存の `copy_task` のテストの呼び方に合わせる。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_storage.py test/test_arrange.py -q -k "project_code"`
Expected: FAIL(`TypeError: Task.__init__() got an unexpected keyword argument 'project_code'`)

- [ ] **Step 3: 実装する**

`models.py`: 定数の並びに追加する(`MIN_PROGRESS, MAX_PROGRESS` の下)。

```python
MAX_PROJECT_CODE_LENGTH = 20  # ProjectCode の最大文字数
```

`Task` の最後のフィールド(`actuals`)の下に追加する(既存の位置引数を壊さないため末尾に置く)。

```python
    project_code: str = ""  # ProjectCode。前後の空白は除く。最大 MAX_PROJECT_CODE_LENGTH 文字
```

`storage.py`: `from projectapp.models import (...)` に `MAX_PROJECT_CODE_LENGTH` を足す。`_assignee` の下に追加する。

```python
def _project_code(value: Any) -> str:
    """ProjectCode。キーがない・nullは空。文字列以外と長すぎるものはValueError(開けませんでした)。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"ProjectCodeが文字列ではありません: {value!r}")
    code = value.strip()
    if len(code) > MAX_PROJECT_CODE_LENGTH:
        raise ValueError(f"ProjectCodeが{MAX_PROJECT_CODE_LENGTH}文字を超えています")
    return code
```

`_task` の `Task(...)` の `actuals=_actuals(raw.get("actuals")),` の下に `project_code=_project_code(raw.get("project_code")),` を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_storage.py test/test_arrange.py -q`
Expected: PASS

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_storage.py test/test_arrange.py
git commit -m "タスクに ProjectCode を持たせて保存する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ProjectCode の入力と検証(`forms.py`、`task_dialog.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task` の引数と検証。インポートに `MAX_PROJECT_CODE_LENGTH`)
- Modify: `src/projectapp/task_dialog.py`(入力欄、変更の判定、保存)
- Test: `test/test_forms.py`、`test/test_task_dialog.py`

**Interfaces:**
- Consumes: `Task.project_code`、`MAX_PROJECT_CODE_LENGTH`(Task 1)
- Produces: `build_task(..., project_code: str = "")`(前後の空白を除く。超過は `ValueError("ProjectCode は20文字以内で入力してください")`)、マーカー `task-project-code`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の末尾に追加する(`make`、`pytest`、`Task` は既存)。

```python
def test_project_code_is_trimmed_and_saved() -> None:
    assert make(project_code="  PRJ-001 ").project_code == "PRJ-001"


def test_project_code_defaults_to_empty_and_keeps_nothing_from_the_existing_task() -> None:
    assert make().project_code == ""
    assert make(Task("t", project_code="OLD")).project_code == ""  # 入力が空なら空にできる


def test_project_code_length_is_checked_after_trimming() -> None:
    assert make(project_code="A" * 20).project_code == "A" * 20
    assert make(project_code=" " + "A" * 20 + " ").project_code == "A" * 20
    with pytest.raises(ValueError, match="20文字以内"):
        make(project_code="A" * 21)


def test_a_blank_project_code_becomes_empty() -> None:
    assert make(project_code="   ").project_code == ""
```

`test/test_task_dialog.py` の末尾に追加する(`mount_dialog`、`open_dialog`、`value_of` は既存)。

```python
async def test_project_code_is_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-project-code").type("PRJ-001")
    user.find(marker="task-save").click()
    assert saved[0].project_code == "PRJ-001"


async def test_existing_project_code_is_shown_and_kept(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(Task("旧", project_code="PRJ-9"), saved)
    await open_dialog(user)
    assert value_of(user, "task-project-code") == "PRJ-9"
    user.find(marker="task-save").click()
    assert saved[0].project_code == "PRJ-9"


async def test_a_too_long_project_code_shows_the_error_and_keeps_the_dialog(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-project-code").type("A" * 21)
    user.find(marker="task-save").click()
    await user.should_see("ProjectCode は20文字以内で入力してください")
    assert saved == []


async def test_changing_the_project_code_counts_as_a_change_when_closing(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-project-code").type("X")
    user.find(marker="task-cancel").click()
    assert confirm_dialog_of(user).value is True
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_task_dialog.py -q -k "project_code"`
Expected: FAIL(`unexpected keyword argument 'project_code'`、マーカーが見つからない)

- [ ] **Step 3: 実装する**

`forms.py`: `from projectapp.models import (...)` に `MAX_PROJECT_CODE_LENGTH` を足す。`build_task` のシグネチャの `actual_rows` の下に `project_code: str = "",` を足す。名前の確認(`if not clean: raise ...`)の直後に追加する。

```python
    code = project_code.strip()
    if len(code) > MAX_PROJECT_CODE_LENGTH:
        raise ValueError(f"ProjectCode は{MAX_PROJECT_CODE_LENGTH}文字以内で入力してください")
```

`return replace(base, ...)` の `actuals=actuals,` の下に `project_code=code,` を足す。

`task_dialog.py`: `name = ui.input("名前", value=initial.name).mark("task-name")` の下に追加する。

```python
        project_code = (
            ui.input("ProjectCode", value=initial.project_code).classes("w-full").mark("task-project-code")
        )
```

`current()` の `name.value,` の下に `project_code.value or "",` を足す。`save()` の `build_task(...)` に `project_code=project_code.value or "",` を足す(`name=name.value or "",` の下)。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py test/test_task_dialog.py -q`
Expected: PASS

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py test/test_forms.py test/test_task_dialog.py
git commit -m "編集ダイアログで ProjectCode を入力できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 名前の欄を枠にして、優先度の背景色を付ける(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(定数 `PRIORITY_*`、`PRIORITY_CSS`、`ui.add_css`、`task_row`)
- Modify: `test/test_gantt.py`(取り消し線のテスト 3 か所を、名前の文字のマーカーに直す。新しいテストを追加)
- Test: `test/test_gantt.py`、`test/test_gantt_drag.py`、`test/test_views.py`

**Interfaces:**
- Consumes: なし(Task 1・2 とは独立)
- Produces:
  - 定数 `PRIORITY_BACKGROUNDS` / `PRIORITY_DARK_BACKGROUNDS`(`dict[Priority, str]`)、`PRIORITY_CLASSES`(`dict[Priority, str]`)、`PRIORITY_CSS`(`str`)、`PRIORITY_BACKGROUND_VAR = "var(--pbg)"`
  - 名前の欄の枠(`ui.row`)。マーカー `task-<key>-<ti>`。中の名前のラベルのマーカー `task-name-<key>-<ti>`(取り消し線は、このラベルに付く)
  - Task 4 は、枠の `with` の中(名前のラベルの後ろ)にチップを足す

- [ ] **Step 1: 既存のテストを直し、失敗するテストを書く**

`test/test_gantt.py` の取り消し線の 3 つのテスト(`test_finished_task_has_a_gray_actual_bar_and_a_struck_through_name`、`test_running_task_keeps_its_color_and_name`、`test_finished_task_without_a_planned_bar_is_also_grayed`)で、名前の文字を見ている行を、名前のラベルのマーカーに直す。

```python
# 変更前 → 変更後
name = user.find(marker="task-0-0").elements.pop()
→ name = user.find(marker="task-name-0-0").elements.pop()

assert "text-decoration" not in user.find(marker="task-0-0").elements.pop()._style
→ assert "text-decoration" not in user.find(marker="task-name-0-0").elements.pop()._style

assert user.find(marker="task-0-0").elements.pop()._style["text-decoration"] == "line-through"
→ assert user.find(marker="task-name-0-0").elements.pop()._style["text-decoration"] == "line-through"
```

(各行は、`grep -n 'text-decoration' test/test_gantt.py` で見つける。)

インポートに `PRIORITY_BACKGROUND_VAR`、`PRIORITY_BACKGROUNDS`、`PRIORITY_CLASSES`、`PRIORITY_CSS`、`PRIORITY_DARK_BACKGROUNDS` を足し(`from projectapp.gantt import (...)` へ)、`Priority` を `from projectapp.models import ...` に足す。末尾に追加する。

```python
def test_priority_backgrounds_cover_every_priority_in_both_themes() -> None:
    assert set(PRIORITY_BACKGROUNDS) == set(Priority) == set(PRIORITY_DARK_BACKGROUNDS) == set(PRIORITY_CLASSES)
    assert len(set(PRIORITY_BACKGROUNDS.values())) == len(Priority)
    for priority, cls in PRIORITY_CLASSES.items():
        assert f".{cls} {{ --pbg: {PRIORITY_BACKGROUNDS[priority]}; }}" in PRIORITY_CSS
        assert f"body.body--dark .{cls} {{ --pbg: {PRIORITY_DARK_BACKGROUNDS[priority]}; }}" in PRIORITY_CSS


@pytest.mark.parametrize("priority", list(Priority))
async def test_the_name_cell_has_the_priority_background(user: User, priority: Priority) -> None:
    project = sample_project()
    project.sections[0].tasks[0].priority = priority
    mount(project)
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    assert PRIORITY_CLASSES[priority] in cell.classes
    assert cell._style["background-color"] == PRIORITY_BACKGROUND_VAR
    assert "background-color" not in user.find(marker="row-0-0").elements.pop()._style  # 行は変えない
    assert "background-color" not in user.find(marker="bar-0-0").elements.pop()._style  # 棒は変えない


async def test_the_name_cell_is_one_row_with_the_name_inside(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    name = user.find(marker="task-name-0-0").elements.pop()
    assert isinstance(cell, ui.row)
    assert name.parent_slot.parent is cell
    assert name.text == "設計"
    assert cell.parent_slot.parent is user.find(marker="row-0-0").elements.pop()  # 行の直接の子
    assert cell._style["width"] == "200px"
    assert "padding-left" in cell._style
    assert "flex" in name._style and "min-width" in name._style  # チップの分だけ名前が縮む
    assert "ellipsis" in name.classes


async def test_the_overdue_tint_is_laid_over_the_priority_background(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 8))
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    assert cell._style["background-color"] == PRIORITY_BACKGROUND_VAR
    assert OVERDUE_COLOR in cell._style["background-image"]


async def test_the_name_cell_is_a_drag_handle_without_a_filter(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert user.find(marker="task-0-0").elements.pop().props.get("draggable") == "true"
```

(絞り込み中にドラッグ属性がないことは、既存の `test_gantt_drag.py` の確認(`"data-drag-handle" not in label`)が、枠に対して成り立つことで担保する。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "priority or name_cell or overdue_tint or struck_through or keeps_its_color or also_grayed"`
Expected: FAIL(`ImportError: cannot import name 'PRIORITY_BACKGROUND_VAR'`)

- [ ] **Step 3: 実装する**

`gantt.py`: `from projectapp.models import Project, Section, Status, Task` に `Priority` を足す。`STATUS_CSS` の定義の下に追加する。

```python
# 優先度ごとの、名前の欄の背景色。赤は予定超過の背景と競合するので使わない。CSS 変数 --pbg 経由
PRIORITY_BACKGROUNDS = {
    Priority.HIGH: "#ffe0b2",
    Priority.MEDIUM: "#fff9c4",
    Priority.LOW: "#bbdefb",
}
PRIORITY_DARK_BACKGROUNDS = {  # ダークテーマでは、暗い背景に合う濃さに替える
    Priority.HIGH: "#6b4a1f",
    Priority.MEDIUM: "#5f5a1c",
    Priority.LOW: "#1f3f5f",
}
PRIORITY_CLASSES = {
    Priority.HIGH: "prio-high",
    Priority.MEDIUM: "prio-medium",
    Priority.LOW: "prio-low",
}
PRIORITY_BACKGROUND_VAR = "var(--pbg)"
PRIORITY_CSS = "\n".join(
    f".{cls} {{ --pbg: {PRIORITY_BACKGROUNDS[priority]}; }}\n"
    f"body.body--dark .{cls} {{ --pbg: {PRIORITY_DARK_BACKGROUNDS[priority]}; }}"
    for priority, cls in PRIORITY_CLASSES.items()
)
```

`ui.add_css(STATUS_CSS)` の下に `ui.add_css(PRIORITY_CSS)` を足す。

`task_row` の `with row:` の中の、`label = ui.label(task.name)...` から `label.props(...)`(ドラッグ属性)までを、次に置き換える。

```python
            cell = ui.row().classes(
                f"items-center no-wrap gap-1 cursor-pointer gantt-sticky {PRIORITY_CLASSES[task.priority]}"
            )
            cell_style = (
                f"width: {NAME_WIDTH_PX}px; padding-left: 16px; padding-right: 4px;"
                f" align-self: stretch; background-color: {PRIORITY_BACKGROUND_VAR};"
                f" {sticky_left(STICKY_Z_NAME)}"
            )
            if overdue:  # 不透明な背景の上に、行と同じ赤みを重ねる
                cell_style += (
                    f"; background-image: linear-gradient({OVERDUE_COLOR}, {OVERDUE_COLOR})"
                )
            cell.style(cell_style)
            cell.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
            cell.mark(f"task-{key}-{ti}")
            if not self.task_filter.active:
                cell.props(f"draggable=true data-drag-handle data-si={key} data-ti={ti}")
            with cell:
                name = ui.label(task.name).classes("ellipsis").style(
                    f"flex: 1 1 0; min-width: 0; line-height: {ROW_HEIGHT_PX - 1}px"
                )
                if finished:  # 終了したタスクは、名前に取り消し線を引く
                    name.style("text-decoration: line-through")
                name.mark(f"task-name-{key}-{ti}")
```

(以降の `end = effective_end(...)` などは、`with row:` の中のまま、変えない。`label` という名前をほかで使っていないことを `grep -n "label" src/projectapp/gantt.py` で確認する。)

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py test/test_gantt_drag.py test/test_views.py -q`
Expected: PASS(既存の固定表示・ドラッグ・クリックのテストが、枠で通る。落ちるテストがあれば、枠への移行の漏れとして直す)

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "名前の欄を枠にして、優先度の背景色を付ける

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ProjectCode・担当・進捗のチップ(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(定数 `CODE_CHIP_STYLE` など、`task_chips`、`task_row` から呼ぶ)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: 名前の欄の枠(`with cell:`、Task 3)、`Task.project_code`(Task 1)、`fill_percent`(既存)
- Produces: `GanttChart.task_chips(key, ti, task)`、マーカー `task-code-<key>-<ti>`、`task-assignee-<key>-<ti>`、`task-progress-<key>-<ti>`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の末尾に追加する(`Actual`、`Task`、`Project`、`Section`、`Status`、`BASE`、`mount`、`sample_project` は既存)。

```python
def project_with(task: Task) -> Project:
    return Project("demo", base_date=BASE, sections=[Section("開発", [task])])


def chip(user: User, marker: str):  # noqa: ANN202
    return user.find(marker=marker).elements.pop()


def tooltip_texts(element: ui.element) -> list[str]:
    return [c.text for c in element.default_slot.children if isinstance(c, ui.tooltip)]


async def test_no_chips_for_a_plain_task(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    for marker in ("task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        await user.should_not_see(marker=marker)


async def test_project_code_chip(user: User) -> None:
    mount(project_with(Task("設計", project_code="PRJ-001")))
    await user.open("/")
    code = chip(user, "task-code-0-0")
    assert code.text == "PRJ-001"
    assert code._style["max-width"] == "56px"
    assert "ellipsis" in code.classes
    assert tooltip_texts(code) == ["PRJ-001"]
    assert code.parent_slot.parent is chip(user, "task-0-0")  # 名前の欄の枠の中


async def test_assignee_chip_shows_the_first_character_and_the_name_on_hover(user: User) -> None:
    mount(project_with(Task("設計", assignee="山田太郎")))
    await user.open("/")
    who = chip(user, "task-assignee-0-0")
    assert who.text == "山"
    assert tooltip_texts(who) == ["山田太郎"]
    assert who._style["width"] == who._style["height"] == "16px"
    assert who.parent_slot.parent is chip(user, "task-0-0")


async def test_assignee_who_is_not_a_member_and_an_emoji_name_do_not_break_the_chart(
    user: User,
) -> None:
    mount(project_with(Task("設計", assignee="👨‍👩‍👧 家族")))  # メンバーにいない・複数のコードポイントの先頭
    await user.open("/")
    assert chip(user, "task-assignee-0-0").text == "👨"


async def test_progress_text(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        actuals=[Actual(datetime(2026, 10, 5, 12), None, 40)],
    )
    mount(project_with(task), now=datetime(2026, 10, 6, 12))
    await user.open("/")
    assert chip(user, "task-progress-0-0").text == "40%"


async def test_no_progress_text_without_progress(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 5, 12), None)])  # 進捗度なし
    mount(project_with(task))
    await user.open("/")
    await user.should_not_see(marker="task-progress-0-0")


async def test_a_finished_task_without_progress_shows_100_percent(user: User) -> None:
    mount(project_with(Task("設計", status=Status.DONE)))
    await user.open("/")
    assert chip(user, "task-progress-0-0").text == "100%"


async def test_a_zero_progress_is_shown(user: User) -> None:
    task = Task("設計", actuals=[Actual(datetime(2026, 10, 5, 12), None, 0)])
    mount(project_with(task))
    await user.open("/")
    assert chip(user, "task-progress-0-0").text == "0%"


async def test_the_strike_through_covers_the_name_only(user: User) -> None:
    mount(project_with(Task("設計", status=Status.DONE, project_code="P", assignee="山")))
    await user.open("/")
    assert chip(user, "task-name-0-0")._style["text-decoration"] == "line-through"
    for marker in ("task-0-0", "task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        assert "text-decoration" not in chip(user, marker)._style


async def test_the_chips_do_not_shrink_and_the_name_does(user: User) -> None:
    mount(project_with(Task("とても長いタスクの名前" * 3, project_code="PRJ-LONG-CODE-0001", assignee="山")))
    await user.open("/")
    for marker in ("task-code-0-0", "task-assignee-0-0"):
        assert chip(user, marker)._style["flex"] == "none"
    name = chip(user, "task-name-0-0")
    assert "flex" in name._style and name._style["min-width"] == "0"


async def test_clicking_a_chip_opens_the_editor(user: User) -> None:
    recorder = mount(project_with(Task("設計", project_code="PRJ-1", assignee="山", status=Status.DONE)))
    await user.open("/")
    for marker in ("task-code-0-0", "task-assignee-0-0", "task-progress-0-0", "task-name-0-0"):
        user.find(marker=marker).click()
    assert recorder.events == [("edit_task", (0, 0))] * 4
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "chip or progress_text or progress_without or shows_100 or zero_progress or covers_the_name or do_not_shrink or no_chips"`
Expected: FAIL(`task-code-0-0` などが見つからない)

- [ ] **Step 3: 実装する**

`gantt.py` の定数(`PRIORITY_CSS` の下)に追加する。

```python
# 名前の右のチップ。名前だけが縮み、チップは縮めない
CODE_CHIP_STYLE = (
    "flex: none; max-width: 56px; padding: 0 6px; font-size: 10px; line-height: 16px;"
    " border: 1px solid rgba(128, 128, 128, 0.6); border-radius: 8px"
)
ASSIGNEE_CHIP_STYLE = (
    "flex: none; width: 16px; height: 16px; line-height: 16px; text-align: center;"
    " font-size: 10px; border-radius: 50%; background: rgba(128, 128, 128, 0.3)"
)
PROGRESS_TEXT_STYLE = "flex: none; font-size: 10px"
```

`GanttChart`(`task_row` を持つクラス)に、`task_row` の下(`progress_fill` の前)にメソッドを足す。

```python
    def task_chips(self, key: int | str, ti: int, task: Task) -> None:
        """名前の右の、ProjectCode・担当・進捗。空のものは出さない。名前の欄の枠の中で呼ぶ。"""
        if task.project_code:
            ui.label(task.project_code).classes("ellipsis").style(CODE_CHIP_STYLE).tooltip(
                task.project_code
            ).mark(f"task-code-{key}-{ti}")
        if task.assignee:
            ui.label(task.assignee[0]).style(ASSIGNEE_CHIP_STYLE).tooltip(task.assignee).mark(
                f"task-assignee-{key}-{ti}"
            )
        percent = fill_percent(task)
        if percent is not None:
            ui.label(f"{percent}%").style(PROGRESS_TEXT_STYLE).mark(f"task-progress-{key}-{ti}")
```

`task_row` の `with cell:` の中、名前のラベルの `name.mark(...)` の後ろに `self.task_chips(key, ti, task)` を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py test/test_gantt_drag.py -q`
Expected: PASS

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "名前の欄に、ProjectCode・担当・進捗のチップを出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ドキュメントと作業記録、全体の確認

**Files:**
- Modify: `CLAUDE.md`(projectapp。「ガントチャート」の節)
- Modify: `docs/development.md`
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: `CLAUDE.md` に 2 行を足す**

「ガントチャートの棒の色は、タスクの状態で決まる…」の行の下に追加する。

```markdown
- タスクには、任意の`ProjectCode`(最大20文字の短い文字列)を設定できる。ガントチャートの名前の欄に、名前の右へ ProjectCode・担当者(頭1文字。マウスオーバーで名前)・進捗(`40%`)のチップを並べる
- タスクの優先度(`高`・`中`・`低`)は、名前の欄の背景色(オレンジ・黄・青。ダークテーマでは暗い色)で表す。バーや行は変えない
```

- [ ] **Step 2: `docs/development.md` に説明を足す**

タスクの表示に関する既存の記述の近くに、次の内容を足す(既存の文体にそろえる)。

- `Task.project_code`(最大 `MAX_PROJECT_CODE_LENGTH` = 20 文字、前後の空白は除く)。保存は `"project_code"`(空は `""`。キーなし・`null` は空。文字列以外と超過は読込を拒否)。編集ダイアログの入力は `build_task(project_code=...)` で検証する。
- 名前の欄は、`task_row` の `ui.row` の枠(マーカー `task-<key>-<ti>`。固定表示・クリック・ドラッグ属性は枠が持つ)。中に、名前のラベル(`task-name-<key>-<ti>`。可変幅で省略。取り消し線は名前だけ)と、`task_chips` のチップ(`task-code-` / `task-assignee-` / `task-progress-`)を並べる。チップは縮まない。進捗は `fill_percent` の値で、棒の塗りと同じ。
- 優先度の背景色は、枠の `background-color: var(--pbg)`。`prio-*` クラスが `--pbg` を持ち、ダークは `body.body--dark .prio-*` で替える(`PRIORITY_BACKGROUNDS`、`PRIORITY_DARK_BACKGROUNDS`)。予定超過の赤みは、`background-image` で重ねる。

- [ ] **Step 3: 全体のテストと型チェック**

Run: `uv run pytest -q`(約3〜4分。バックグラウンドで実行して、終わりを待つ)
Expected: すべて PASS(875 件 + 新しいテスト)

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 4: `.claude/MEMORY.md` を更新する**

- 先頭の「最終更新」を、要望9・3の実装(`feature/task-chips`、未マージ)に直す。
- 「現在の状況」の先頭に、要望9・3と優先度の背景色の実装の記録を足す: ブランチ、設計書 `2026-10-05-task-chips-design.md`、実装計画 `2026-10-05-task-chips.md`、テストの件数、方式(`Task.project_code`、名前の欄の枠、チップ、`--pbg`)、`develop` へは未マージ・未プッシュ、実機での確認はこれから、保留(名前の欄の幅 200px で ProjectCode が長いとき、頭文字が同じ担当者の区別)。
- 「今後の要望」の 3 と 9 の行に `(完了)` を付ける。優先度の背景色の追加(2026-10-05)を、9 の行の後ろに追記する。
- 「参照先」に、設計書と実装計画を足す。

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md
git commit -m "作業記録: タスク表示の拡張の実装を反映

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実機での確認用のデータは、`~/.projectapp/` に新しいファイルとして作る(既存のファイルを上書きしない)。
