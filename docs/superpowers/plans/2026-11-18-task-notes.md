# タスクのメモ(要望 150)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクごとに、git 管理の外(`~/.projectapp/notes/`)へ HTML で保存するリッチテキストのメモを持ち、右ペインで書けるようにする。

**Architecture:** 保存と同期は NiceGUI に依存しない`notes.py`に置く。画面は、Quasar の`right_drawer`に`ui.editor`を入れた`note_pane.py`と、`views.py`・`gantt.py`の小さな足し込み(右クリックの`メモ…`・名前の後ろの`🗒️`)。削除と元に戻すは、`history`にメモを持たせず、ビューが編集・元に戻す・やり直しのたびにタスク id の増減を比べ、消えたメモをメモリ上のごみ箱へ移す・戻った id のメモを書き戻す。

**Tech Stack:** Python 3.13、NiceGUI(`ui.right_drawer`・`ui.editor`)、pytest(NiceGUI の`User`シミュレーション)。

**Spec:** `docs/superpowers/specs/2026-11-18-task-notes-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・コミットメッセージ)。Python 3.13 以上。型ヒントは全関数に付ける(`uvx ty check src`で検証)
- 保存先は`~/.projectapp/notes/<プロジェクト名>/<タスクid>.html`。プロジェクトのファイルの形は変えない(`version`は 23 のまま)
- メモは PlantUML・CSV・担当者向けファイルに出さない。計算(完了予定・工数・進捗・マージ)はメモを読まない
- ファイルの書き込みは一時ファイル経由。タスク id は`[A-Za-z0-9_-]{1,64}`だけ受ける(パスの混入を防ぐ)
- 要素数を増やさない: メモのないタスクの描画は変えない(`🗒️`はメモのあるタスクにだけ付ける)
- コメントは多くても 3 行以内。コミットメッセージの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- 実装ごとに smoke(`uv run pytest -m smoke`)→ `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`(ty は既存の 9 件を超えないこと)

## Review Focus

- 空に近いメモ(`<p><br></p>`・`&nbsp;`だけ)を保存しても、ファイルと`🗒️`が残らないこと(Task 1 の`test_save_blank_html_removes_the_file`)
- 壊れたファイル・読めないファイル・存在しないフォルダで、例外を画面に出さないこと(Task 1)
- プロジェクト名やタスク id にパス区切りが入っても、`notes/`の外に書かないこと(Task 1)
- タスクを削除してすぐ元に戻す・やり直す・また元に戻すを繰り返しても、メモが失われず、二重にならないこと(Task 2・5)
- ペインを開いたまま、そのタスクを削除しても、閉じたあとにメモのファイルが復活しないこと(Task 5)
- `git pull`などの外部の変更でタスクが消えても、メモは消さないこと(Task 5 は、`after_edit`と`restore`以外の経路で消えた id に触らないことをテストで確かめる)

---

## File Structure

- 新規 `src/projectapp/notes.py`: 保存・読み込み・存在の一覧・削除・コピー・同期。NiceGUI に依存しない。
- 新規 `src/projectapp/note_pane.py`: 右ペイン(`NotePane`)。保存の仕方は呼び出し側から受ける。
- 変更 `src/projectapp/gantt.py`: `note_ids`・`🗒️`・右クリックの`メモ…`・`Actions`の 2 つの操作。
- 変更 `src/projectapp/views.py`: ペインの生成・開く・保存・同期・コピー・名前をつけて保存。
- 変更 `test/conftest.py`: メモの保存先をテストごとに一時フォルダへ向ける autouse フィクスチャ。
- 新規 `test/test_notes.py`: `notes.py`の単体テスト。新規 `test/test_task_notes_view.py`: 画面のテスト。
- 変更 文書: `.claude/spec/gantt.md`・`.claude/spec/project-files.md`・`docs/development.md`・`docs/requests.md`。

---

### Task 1: メモの保存(`notes.py`)

**Files:**
- Create: `src/projectapp/notes.py`
- Modify: `test/conftest.py`(末尾にフィクスチャを足す)
- Test: `test/test_notes.py`

**Interfaces:**
- Produces(後の Task が使う。すべて`name`はプロジェクト名、`task_id`はタスク id):
  - `NOTES_ROOT: Path`(モジュール変数。テストが差し替える)
  - `is_blank(html: str) -> bool`
  - `load(name: str, task_id: str) -> str | None`
  - `save(name: str, task_id: str, html: str) -> None`(空なら削除)
  - `delete(name: str, task_id: str) -> str | None`(消した中身を返す。なければ None)
  - `note_ids(name: str) -> frozenset[str]`
  - `copy(name: str, src_id: str, dst_id: str) -> None`
  - `copy_many(name: str, pairs: list[tuple[str, str]]) -> None`
  - `copy_project(src_name: str, dst_name: str) -> None`

- [ ] **Step 1: テストの保存先を差し替えるフィクスチャを足す**

`test/conftest.py`の末尾に追記する(`pytest`・`Path`は既に import 済みか、なければ足す):

```python
@pytest.fixture(autouse=True)
def isolated_notes(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """メモの保存先(`~/.projectapp/notes`)を、テストごとの一時フォルダへ向ける。本物の設定フォルダを触らない。"""
    root = tmp_path_factory.mktemp("notes")
    monkeypatch.setattr("projectapp.notes.NOTES_ROOT", root)
    return root
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_notes.py`:

```python
"""notes.py(タスクのメモの保存・同期)の単体テスト。"""

from pathlib import Path

from projectapp import notes


def test_save_then_load_round_trips_the_html(isolated_notes: Path) -> None:
    notes.save("案件", "a1b2c3d4", "<p>こんにちは</p>")
    assert notes.load("案件", "a1b2c3d4") == "<p>こんにちは</p>"
    assert (isolated_notes / "案件" / "a1b2c3d4.html").is_file()


def test_load_returns_none_when_there_is_no_note() -> None:
    assert notes.load("案件", "a1b2c3d4") is None


def test_save_blank_html_removes_the_file(isolated_notes: Path) -> None:
    notes.save("案件", "a1b2c3d4", "<p>x</p>")
    for blank in ("", "   ", "<p><br></p>", "<div>&nbsp;</div>"):
        notes.save("案件", "a1b2c3d4", "<p>x</p>")
        notes.save("案件", "a1b2c3d4", blank)
        assert notes.load("案件", "a1b2c3d4") is None
        assert notes.note_ids("案件") == frozenset()


def test_is_blank_ignores_tags_and_nbsp() -> None:
    assert notes.is_blank("<p><br></p>")
    assert notes.is_blank("<p>&nbsp;</p>")
    assert not notes.is_blank("<p>a</p>")
    assert not notes.is_blank("<img src='x'>テキスト")


def test_load_survives_a_broken_file(isolated_notes: Path) -> None:
    folder = isolated_notes / "案件"
    folder.mkdir()
    (folder / "a1b2c3d4.html").write_bytes(b"\xff\xfe\x00broken")
    assert notes.load("案件", "a1b2c3d4") is None  # 例外を出さず、メモなしとして扱う


def test_unsafe_ids_and_names_are_rejected(isolated_notes: Path) -> None:
    for bad in ("../x", "a/b", "", "a" * 65, "あ"):
        notes.save("案件", bad, "<p>x</p>")
        assert notes.load("案件", bad) is None
    notes.save("../escape", "a1b2c3d4", "<p>x</p>")
    notes.save("a/b", "a1b2c3d4", "<p>x</p>")
    assert list(isolated_notes.rglob("*.html")) == []  # notes の外へ書かない
    assert notes.note_ids("../escape") == frozenset()


def test_note_ids_lists_only_valid_html_files(isolated_notes: Path) -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    notes.save("案件", "bbbb2222", "<p>2</p>")
    (isolated_notes / "案件" / "memo.txt").write_text("x")
    (isolated_notes / "案件" / "bad id.html").write_text("x")
    assert notes.note_ids("案件") == frozenset({"aaaa1111", "bbbb2222"})
    assert notes.note_ids("ない") == frozenset()


def test_delete_returns_the_removed_html() -> None:
    notes.save("案件", "a1b2c3d4", "<p>x</p>")
    assert notes.delete("案件", "a1b2c3d4") == "<p>x</p>"
    assert notes.load("案件", "a1b2c3d4") is None
    assert notes.delete("案件", "a1b2c3d4") is None


def test_copy_and_copy_many() -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    notes.save("案件", "bbbb2222", "<p>2</p>")
    notes.copy("案件", "aaaa1111", "cccc3333")
    notes.copy_many("案件", [("bbbb2222", "dddd4444"), ("eeee5555", "ffff6666")])
    assert notes.load("案件", "cccc3333") == "<p>1</p>"
    assert notes.load("案件", "dddd4444") == "<p>2</p>"
    assert notes.load("案件", "ffff6666") is None  # 元のメモがなければ作らない
    assert notes.load("案件", "aaaa1111") == "<p>1</p>"  # 元は残る


def test_copy_project_copies_the_folder_and_keeps_the_source() -> None:
    notes.save("旧", "aaaa1111", "<p>1</p>")
    notes.copy_project("旧", "新")
    assert notes.load("新", "aaaa1111") == "<p>1</p>"
    assert notes.load("旧", "aaaa1111") == "<p>1</p>"
    notes.copy_project("ない", "新2")  # 元がなければ何もしない
    assert notes.note_ids("新2") == frozenset()
    notes.copy_project("旧", "旧")  # 同じ名前なら何もしない
    assert notes.load("旧", "aaaa1111") == "<p>1</p>"
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_notes.py -q`
Expected: FAIL(`projectapp.notes`がない、または`NOTES_ROOT`の差し替えで AttributeError)

- [ ] **Step 4: 実装する**

`src/projectapp/notes.py`:

```python
"""タスクのメモ(要望 150)の保存。`~/.projectapp/notes/<プロジェクト名>/<タスクid>.html`で、git 管理の外。NiceGUI に依存しない。"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from projectapp.storage import BASE_DIR, INVALID_NAME_CHARS

NOTES_ROOT = BASE_DIR / "notes"
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_TAGS = re.compile(r"<[^>]*>")


def _folder(name: str) -> Path | None:
    """プロジェクトのメモのフォルダ。名前がフォルダ名に使えなければ None。"""
    if (
        not name
        or name in {".", ".."}
        or any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in name)
    ):
        return None
    return NOTES_ROOT / name


def _file(name: str, task_id: str) -> Path | None:
    folder = _folder(name)
    if folder is None or not _ID.fullmatch(task_id):
        return None
    return folder / f"{task_id}.html"


def is_blank(html: str) -> bool:
    """タグと空白だけで、書いた中身がないか。"""
    return not _TAGS.sub("", html).replace("&nbsp;", " ").strip()


def load(name: str, task_id: str) -> str | None:
    path = _file(name, task_id)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None  # 読めないメモは、メモなしとして扱う


def save(name: str, task_id: str, html: str) -> None:
    """保存する。中身が空なら、ファイルを消す。書けないとき(OSError)は、何もしない。"""
    path = _file(name, task_id)
    if path is None:
        return
    if is_blank(html):
        delete(name, task_id)
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(html)
        os.replace(tmp.name, path)
    except OSError:
        return


def delete(name: str, task_id: str) -> str | None:
    """消して、消した中身を返す(なければ None)。"""
    html = load(name, task_id)
    path = _file(name, task_id)
    if path is not None:
        path.unlink(missing_ok=True)
    return html


def note_ids(name: str) -> frozenset[str]:
    """メモのあるタスク id。"""
    folder = _folder(name)
    if folder is None or not folder.is_dir():
        return frozenset()
    return frozenset(
        p.stem for p in folder.glob("*.html") if _ID.fullmatch(p.stem)
    )


def copy(name: str, src_id: str, dst_id: str) -> None:
    html = load(name, src_id)
    if html is not None:
        save(name, dst_id, html)


def copy_many(name: str, pairs: list[tuple[str, str]]) -> None:
    for src_id, dst_id in pairs:
        copy(name, src_id, dst_id)


def copy_project(src_name: str, dst_name: str) -> None:
    """名前をつけて保存のとき、メモのフォルダを新しい名前へコピーする(元は残す)。"""
    src, dst = _folder(src_name), _folder(dst_name)
    if src is None or dst is None or src == dst or not src.is_dir():
        return
    try:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    except OSError:
        return
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_notes.py -q`
Expected: PASS(全件)

- [ ] **Step 6: コミット**

```bash
uvx ruff check src test && uvx ruff format src test
git add src/projectapp/notes.py test/conftest.py test/test_notes.py
git commit -m "feat: タスクのメモの保存(notes.py)を作る(要望 150)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 削除と元に戻すの同期(`notes.sync`)

**Files:**
- Modify: `src/projectapp/notes.py`(末尾に足す)
- Test: `test/test_notes.py`(末尾に足す)

**Interfaces:**
- Consumes: Task 1 の`delete`・`save`
- Produces: `sync(name: str, before: set[str], after: set[str], trash: dict[str, str]) -> set[str]`。`before`から`after`への id の増減を見て、消えた id のメモをごみ箱(`trash`。id → HTML)へ移してファイルを消し、ごみ箱にある id が戻ればファイルへ書き戻す。**消えた id の集合**を返す(ペインを閉じるかの判定に使う)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_notes.py`の末尾へ:

```python
def test_sync_moves_a_removed_note_to_the_trash_and_restores_it() -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    trash: dict[str, str] = {}
    gone = notes.sync("案件", {"aaaa1111", "bbbb2222"}, {"bbbb2222"}, trash)
    assert gone == {"aaaa1111"}
    assert notes.load("案件", "aaaa1111") is None
    assert trash == {"aaaa1111": "<p>1</p>"}
    notes.sync("案件", {"bbbb2222"}, {"aaaa1111", "bbbb2222"}, trash)  # 元に戻す
    assert notes.load("案件", "aaaa1111") == "<p>1</p>"
    assert trash == {}


def test_sync_survives_delete_undo_redo_undo() -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    trash: dict[str, str] = {}
    present, absent = {"aaaa1111"}, set()
    for before, after in [(present, absent), (absent, present), (present, absent), (absent, present)]:
        notes.sync("案件", set(before), set(after), trash)
    assert notes.load("案件", "aaaa1111") == "<p>1</p>"
    assert trash == {}


def test_sync_ignores_ids_without_a_note_and_unchanged_ids() -> None:
    trash: dict[str, str] = {}
    assert notes.sync("案件", {"aaaa1111"}, {"aaaa1111"}, trash) == set()
    assert notes.sync("案件", {"aaaa1111"}, set(), trash) == {"aaaa1111"}
    assert trash == {}  # メモがなければ、ごみ箱にも入れない
    assert notes.sync("案件", set(), {"zzzz9999"}, trash) == set()  # 新しい id でごみ箱にもない
    assert notes.note_ids("案件") == frozenset()
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_notes.py -k sync -q`
Expected: FAIL(`notes.sync`がない)

- [ ] **Step 3: 実装する**

`src/projectapp/notes.py`の末尾へ:

```python
def sync(
    name: str, before: set[str], after: set[str], trash: dict[str, str]
) -> set[str]:
    """タスク id の増減に、メモを合わせる。消えた id のメモはごみ箱へ(元に戻すで書き戻す)。消えた id を返す。"""
    gone = before - after
    for task_id in gone:
        html = delete(name, task_id)
        if html is not None:
            trash[task_id] = html
    for task_id in after - before:
        html = trash.pop(task_id, None)
        if html is not None:
            save(name, task_id, html)
    return gone
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_notes.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff check src test && uvx ruff format src test
git add src/projectapp/notes.py test/test_notes.py
git commit -m "feat: タスク id の増減にメモを合わせる同期を作る(要望 150)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ガントの`🗒️`と右クリックの`メモ…`

**Files:**
- Modify: `src/projectapp/gantt.py`
- Test: `test/test_task_notes_view.py`(新規)

**Interfaces:**
- Consumes: Task 1 の`notes.note_ids`
- Produces:
  - `GanttChart.note_ids: frozenset[str]`(メモのあるタスク id。既定は空)
  - `Actions.open_note: Callable[[str], object]`(タスク id)・`Actions.note_at: Callable[[SectionPath, int], object]`(右クリックの行)
  - マーカー: `task-note-<id>`(`🗒️`)・`context-note`(右クリックの項目)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_notes_view.py`(`open_dashboard_view`・`text_of`は`test/test_views.py`から import する。`test_views.py`の import 形式に合わせる):

```python
"""タスクのメモ(要望 150)の画面のテスト。"""

from pathlib import Path

from nicegui.testing import User

from projectapp import notes
from test.test_views import open_dashboard_view  # noqa: E402


async def test_the_note_mark_appears_only_for_tasks_with_a_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    await user.should_not_see(marker=f"task-note-{task.id}")
    notes.save(view.project.name, task.id, "<p>メモ</p>")
    view.gantt.note_ids = notes.note_ids(view.project.name)
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")


async def test_the_note_mark_calls_open_note_with_the_task_id(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    opened: list[str] = []
    view.gantt.actions.open_note = opened.append
    view.gantt.note_ids = frozenset({task.id})
    with user.client:
        view.after_edit()
    user.find(marker=f"task-note-{task.id}").click()
    assert opened == [task.id]
```

(`test_views.py`の import 形式が`from test.test_views import ...`でない場合は、そのファイルの他のテスト(`test/test_daily_crew_view.py`の冒頭)がヘルパーをどう import しているかに合わせる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_notes_view.py -q`
Expected: FAIL(`task-note-…`が見つからない)

- [ ] **Step 3: `gantt.py`に足す**

1. `Actions`の定義(`add_extra_effort: Callable[[SectionPath, int], object] = ...`の直後)へ:

```python
    open_note: Callable[[str], object] = lambda task_id: None  # タスクのメモを右ペインで開く
    note_at: Callable[[SectionPath, int], object] = lambda path, ti: (
        None
    )  # 右クリックの`メモ…`
```

2. `GanttChart.__init__`の`self.trial_pool_ids: frozenset[str] = (`(826 行付近)の直前へ:

```python
        self.note_ids: frozenset[str] = frozenset()  # メモのあるタスクの id(要望 150)
```

3. 名前の欄の描画(`name.mark(f"task-name-{key}-{ti}")`の直後、`if summary and not self.options.read_only:`の前)へ:

```python
                if task.id in self.note_ids:
                    ui.label("🗒️").classes("cursor-pointer shrink-0").props(
                        "data-no-quick-add"
                    ).on(
                        "click",
                        lambda tid=task.id: self.actions.open_note(tid),
                        js_handler=PLAIN_CLICK_JS,
                    ).mark(f"task-note-{task.id}")
```

4. 右クリックのメニュー(`context-extra-effort`の`.mark(...)`の直後)へ:

```python
            ui.menu_item(
                "メモ…", on_click=act(lambda p, t: self.actions.note_at(p, t))
            ).mark("context-note")
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_notes_view.py -q`
Expected: PASS(2 件)。`PLAIN_CLICK_JS`は`gantt.py`で既に定義・使用されているので import は不要。

- [ ] **Step 5: smoke とコミット**

```bash
uv run pytest -m smoke -q 2>&1 | tail -3
uvx ruff check src test && uvx ruff format src test
git add src/projectapp/gantt.py test/test_task_notes_view.py
git commit -m "feat: ガントのタスク名の後ろに🗒️を出し、右クリックにメモ…を足す(要望 150)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 右ペイン(`note_pane.py`)とビューへの接続

**Files:**
- Create: `src/projectapp/note_pane.py`
- Modify: `src/projectapp/views.py`
- Test: `test/test_task_notes_view.py`(足す)

**Interfaces:**
- Consumes: Task 1 の`notes.load`・`notes.save`・`notes.note_ids`、Task 3 の`Actions.open_note`・`note_at`・`GanttChart.note_ids`
- Produces:
  - `NotePane(save: Callable[[str, str, str], object], load: Callable[[str, str], str | None])`。属性`name`・`task_id`・`dirty`・`editor`・`drawer`。メソッド`open(name: str, task_id: str, title: str) -> None`・`flush() -> None`・`close(save: bool = True) -> None`。マーカー: `note-title`・`note-close`・`note-editor`
  - `MainView.note_pane: NotePane | None`・`MainView.open_note(task_id: str) -> None`・`MainView.note_at(path, index) -> None`・`MainView.save_note(name: str, task_id: str, html: str) -> None`
  - `MainView.note_trash: dict[str, str]`(Task 5 が使う)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_notes_view.py`の末尾へ(`Status`などは不要):

```python
async def test_the_context_menu_note_opens_the_pane_and_typing_saves(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    with user.client:
        view.note_at(path, index)
    await user.should_see(marker="note-editor")
    assert view.note_pane is not None
    assert (view.note_pane.name, view.note_pane.task_id) == (view.project.name, task.id)
    assert notes.load(view.project.name, task.id) is None  # 入力するまでファイルは作らない
    with user.client:
        view.note_pane.editor.set_value("<p>経緯</p>")
        view.note_pane.flush()
    assert notes.load(view.project.name, task.id) == "<p>経緯</p>"
    assert task.id in view.gantt.note_ids  # 🗒️が付く


async def test_opening_an_existing_note_shows_its_text_and_switching_saves_the_previous(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    first = view.project.all_tasks()[0]
    notes.save(view.project.name, first.id, "<p>既存</p>")
    with user.client:
        view.open_note(first.id)
    assert view.note_pane is not None
    assert view.note_pane.editor.value == "<p>既存</p>"
    with user.client:
        view.note_pane.editor.set_value("<p>書き換え</p>")
        view.open_note(first.id)  # 切り替えの前に、いまの入力を保存する
    assert notes.load(view.project.name, first.id) == "<p>書き換え</p>"


async def test_emptying_the_note_removes_the_file_and_the_mark(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>x</p>")
    view.gantt.note_ids = notes.note_ids(view.project.name)
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p><br></p>")
        view.note_pane.flush()
    assert notes.load(view.project.name, task.id) is None
    assert task.id not in view.gantt.note_ids


async def test_close_saves_pending_text_and_hides_the_pane(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>閉じる前</p>")
        view.note_pane.close()
    assert notes.load(view.project.name, task.id) == "<p>閉じる前</p>"
    assert view.note_pane.task_id is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_notes_view.py -q`
Expected: FAIL(`view.note_at`がない)

- [ ] **Step 3: `note_pane.py`を作る**

```python
"""タスクのメモの右ペイン(要望 150)。`right_drawer`に`ui.editor`を入れ、入力が止まって約 1 秒後に自動で保存する。"""

from collections.abc import Callable

from nicegui import ui

WIDTH_PX = 360
SAVE_SECONDS = 1.0


class NotePane:
    def __init__(
        self,
        save: Callable[[str, str, str], object],
        load: Callable[[str, str], str | None],
    ) -> None:
        self._save = save
        self._load = load
        self.name: str | None = None
        self.task_id: str | None = None
        self.dirty = False
        self._loading = False
        self.drawer = (
            ui.right_drawer(value=False, fixed=True, bordered=True)
            .props(f"width={WIDTH_PX} behavior=desktop")
            .mark("note-pane")
        )
        with self.drawer:
            with ui.row().classes("w-full items-center no-wrap"):
                self.title = (
                    ui.label("").classes("text-subtitle1 ellipsis flex-1").mark("note-title")
                )
                ui.button(icon="close", on_click=lambda: self.close()).props(
                    "flat dense round"
                ).mark("note-close")
            self.editor = ui.editor(placeholder="メモ").classes("w-full").mark("note-editor")
        self.editor.on_value_change(self._edited)
        self.drawer.on("keydown.esc", lambda: self.close())
        ui.timer(SAVE_SECONDS, self.flush)

    def open(self, name: str, task_id: str, title: str) -> None:
        """メモを開く。開いていたメモの入力は、先に保存する。"""
        self.flush()
        self.name, self.task_id = name, task_id
        self.title.set_text(title)
        self._loading = True
        try:
            self.editor.set_value(self._load(name, task_id) or "")
        finally:
            self._loading = False
        self.dirty = False
        self.drawer.show()

    def _edited(self, _event: object = None) -> None:
        if not self._loading:
            self.dirty = True

    def flush(self) -> None:
        if self.dirty and self.name is not None and self.task_id is not None:
            self.dirty = False
            self._save(self.name, self.task_id, self.editor.value or "")

    def close(self, save: bool = True) -> None:
        """閉じる。save が偽なら、入力を捨てる(開いていたタスクが消えたとき)。"""
        if save:
            self.flush()
        self.dirty = False
        self.name = self.task_id = None
        self.drawer.hide()
```

- [ ] **Step 4: `views.py`に足す**

1. import(他の`from projectapp...`の並びに合わせてアルファベット順の位置へ):

```python
from projectapp import notes
from projectapp.note_pane import NotePane
```

2. `MainView.__init__`の`self.history = History()`(579 行付近)の直後へ:

```python
        self.note_pane: NotePane | None = None  # タスクのメモの右ペイン(build で作る)
        self.note_trash: dict[str, str] = {}  # 削除したタスクのメモ(元に戻すで書き戻す。メモリだけ)
```

3. `MainView.build`の`self.gantt.build()`の直前へ(`trial_band`の行の後):

```python
        self.gantt.note_ids = notes.note_ids(self.project.name)
        self.note_pane = NotePane(save=self.save_note, load=notes.load)
```

4. `after_edit`の定義の前に、メソッドを 4 つ足す:

```python
    def open_note(self, task_id: str) -> None:
        """タスクのメモを右ペインで開く(いまのメモの入力は先に保存する)。"""
        task = self.project.task_map().get(task_id)
        if task is not None and self.note_pane is not None:
            self.note_pane.open(self.project.name, task_id, task.name)

    def note_at(self, path: SectionPath, index: int) -> None:
        """右クリックの`メモ…`。"""
        if arrange.has_task(self.project, (path, index)):
            self.open_note(self.tasks_in(path)[index].id)

    def save_note(self, name: str, task_id: str, html: str) -> None:
        """ペインの保存。メモの有無が変わったときだけ、ガントの🗒️を描き直す。"""
        notes.save(name, task_id, html)
        if name != self.project.name:
            return
        ids = notes.note_ids(name)
        if ids != self.gantt.note_ids:
            self.gantt.note_ids = ids
            self.gantt.set_project(self.project)
```

5. `MainView.build`の`self.gantt.build()`より前に`self.gantt.actions`へつなぐ。`add_extra_effort=self.add_extra_effort,`(646 行付近)の直後へ:

```python
                open_note=self.open_note,
                note_at=self.note_at,
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_task_notes_view.py -q`
Expected: PASS(Task 3 の 2 件と合わせて 6 件)

- [ ] **Step 6: smoke とコミット**

```bash
uv run pytest -m smoke -q 2>&1 | tail -3
uvx ruff check src test && uvx ruff format src test
git add src/projectapp/note_pane.py src/projectapp/views.py test/test_task_notes_view.py
git commit -m "feat: タスクのメモの右ペインを作り、右クリックと🗒️から開く(要望 150)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 削除・元に戻す・複製・名前をつけて保存との連動

**Files:**
- Modify: `src/projectapp/views.py`
- Test: `test/test_task_notes_view.py`(足す)

**Interfaces:**
- Consumes: Task 2 の`notes.sync`、Task 1 の`notes.copy_many`・`notes.copy_project`・`notes.note_ids`、Task 4 の`MainView.note_pane`・`note_trash`・`save_note`
- Produces: `MainView.sync_notes(before: Project, after: Project) -> None`。`after_edit`・`restore`・`reset_history`・`move_task`(複製)・`copy_section`・`save_as_new`が、メモと連動する。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_notes_view.py`の末尾へ(必要な import: `from dataclasses import replace`・`from projectapp.models import Task`):

```python
async def test_deleting_a_task_removes_its_note_and_undo_restores_it(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    notes.save(view.project.name, task.id, "<p>残す</p>")
    with user.client:
        view.delete_task(path, index)
    assert notes.load(view.project.name, task.id) is None
    assert task.id not in view.gantt.note_ids
    with user.client:
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>残す</p>"
    assert task.id in view.gantt.note_ids
    with user.client:
        view.redo()
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>残す</p>"  # 繰り返しても失われない


async def test_deleting_the_open_task_closes_the_pane_without_resurrecting_the_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>書いた</p>")
        view.delete_task(path, index)  # 保存してから消す(元に戻すで戻る)
    assert view.note_pane.task_id is None
    assert notes.load(view.project.name, task.id) is None
    with user.client:
        view.note_pane.flush()  # 閉じたあとに保存が走っても、ファイルは復活しない
    assert notes.load(view.project.name, task.id) is None
    with user.client:
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>書いた</p>"


async def test_copying_a_task_copies_its_note(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    notes.save(view.project.name, task.id, "<p>写す</p>")
    with user.client:
        view.copy_task_below(path, index)
    copies = [t for t in view.project.all_tasks() if t.id != task.id]
    assert len(copies) == 1
    assert notes.load(view.project.name, copies[0].id) == "<p>写す</p>"
    assert notes.load(view.project.name, task.id) == "<p>写す</p>"  # 元は残る
    assert copies[0].id in view.gantt.note_ids


async def test_a_task_that_vanishes_outside_an_edit_keeps_its_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>外部</p>")
    view.project.tasks = [t for t in view.project.tasks if t.id != task.id]
    view.reset_history()  # 外部の変更(git pull など)で消えた扱い。after_edit も restore も通らない
    assert notes.load(view.project.name, task.id) == "<p>外部</p>"


async def test_save_as_copies_the_notes_to_the_new_name(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    old = view.project.name
    notes.save(old, task.id, "<p>引き継ぐ</p>")
    with user.client:
        assert view.save_as_new("別名")
    assert notes.load("別名", task.id) == "<p>引き継ぐ</p>"
    assert notes.load(old, task.id) == "<p>引き継ぐ</p>"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_notes_view.py -q`
Expected: FAIL(削除してもメモが残る、など)

- [ ] **Step 3: `views.py`に足す**

1. `save_note`の直後に`sync_notes`を足す:

```python
    def sync_notes(self, before: Project, after: Project) -> None:
        """編集・元に戻す・やり直しのタスク id の増減に、メモを合わせる(外部の変更では呼ばない)。"""
        before_ids = {t.id for t in before.all_tasks()}
        after_ids = {t.id for t in after.all_tasks()}
        if before_ids == after_ids:
            return
        if self.note_pane is not None:
            self.note_pane.flush()  # 消える前に、最後の入力を保存して、ごみ箱に載せる
        gone = notes.sync(self.project.name, before_ids, after_ids, self.note_trash)
        if self.note_pane is not None and self.note_pane.task_id in gone:
            self.note_pane.close(save=False)
```

(`Project`は`views.py`で既に import 済み。なければ`from projectapp.models import Project`を足す。)

2. `after_edit`: `if self.project != self.committed:`の中、`self.history.record(self.committed)`の直前へ `self.sync_notes(self.committed, self.project)` を足し、`self.gantt.set_project(self.project)`の直前へ `self.gantt.note_ids = notes.note_ids(self.project.name)` を足す。

3. `restore`: 先頭の`folded = ...`の直前へ `self.sync_notes(self.project, project)` を足し、`self.gantt.set_project(self.project)`の直前へ `self.gantt.note_ids = notes.note_ids(project.name)` を足す。

4. `reset_history`: `self.history.clear()`の直後へ:

```python
        if self.note_pane is not None:
            self.note_pane.close()  # 開いていた(切り替え前の)メモは、保存して閉じる
        self.note_trash = {}
        self.gantt.note_ids = notes.note_ids(self.project.name)
```

5. `move_task`の複製の分岐を差し替える:

```python
        if copy:
            original = arrange.tasks_at(self.project, src[0])[src[1]]
            kid_ids = [k.id for k in children_of(original, self.project.task_map())]
            copied = arrange.copy_task(self.project, src, dst)
            notes.copy_many(
                self.project.name,
                [(original.id, copied.id), *zip(kid_ids, copied.children)],
            )
            ui.notify(f"「{name}」をコピーしました")
```

(`children_of`は`projectapp.summary`にある。`from projectapp.summary import children_of`を足す。`views.py`に既存の import があればそれを使う。)

6. `copy_section`: `arrange.copy_section(self.project, path)`を次に差し替える:

```python
        original_ids = [t.id for t in section.all_tasks()]
        copied = arrange.copy_section(self.project, path)
        notes.copy_many(
            self.project.name,
            list(zip(original_ids, [t.id for t in copied.all_tasks()])),
        )
```

7. `save_as_new`: `if self.write(overwrite=False, after=after):`の直後、`self.reset_history()`の前へ:

```python
            if self.note_pane is not None:
                self.note_pane.flush()
            notes.copy_project(previous, name)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_notes_view.py test/test_notes.py -q`
Expected: PASS(全件)

- [ ] **Step 5: smoke・全体の確認・コミット**

```bash
uv run pytest -m smoke -q 2>&1 | tail -3
uvx ruff check src test && uvx ruff format src test
uvx ty check src 2>&1 | tail -2   # 9 件を超えないこと
git add src/projectapp/views.py test/test_task_notes_view.py
git commit -m "feat: タスクのメモを、削除・元に戻す・複製・名前をつけて保存と連動させる(要望 150)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 文書の更新

**Files:**
- Modify: `.claude/spec/gantt.md`、`.claude/spec/project-files.md`、`docs/development.md`、`docs/requests.md`

- [ ] **Step 1: 仕様書に書く**

`.claude/spec/gantt.md`の右クリックの節(`追加工数を足す…`の項を含む行 27)の項目の並びに`メモ…`を足し、追加工数の項(行 28)の直後に次の項を足す:

```markdown
- タスクのメモ(要望 150): タスクごとに、git 管理の外にリッチテキストのメモを持てる。右クリックの`メモ…`、またはタスク名の後ろの`🗒️`(メモのあるタスクにだけ付く)のクリックで、ガントの右に右ペイン(幅 360px 固定)を開く。上にタスク名、下に`ui.editor`。入力が約 1 秒止まったとき・別のメモを開くとき・閉じるときに自動で保存し、空にすると消えて`🗒️`も外れる。保存先・形式は`project-files.md`。タスクを削除したらメモも消し(元に戻す・やり直しで戻る)、複製(タスク・セクション)はメモもコピーする。PlantUML・CSV・担当者向けファイルには出さない。
```

`.claude/spec/project-files.md`に、データの保存先の項へ次を足す:

```markdown
- タスクのメモ(要望 150)は、`~/.projectapp/notes/<プロジェクト名>/<タスクid>.html`(git 管理の外。HTML)。プロジェクトのファイルは変えない(`version`据え置き)。メモはその端末のローカルで、別の端末・別のクローンには出ない。名前をつけて保存は、メモのフォルダも新しい名前へコピーする(元は残す)。タスクの削除は、メモをメモリ上のごみ箱へ移してファイルを消し、元に戻す・やり直しで書き戻す(プロジェクトを閉じる・切り替えると戻せない)。外部の変更(`git pull`など)で消えたタスクのメモには触らない。
```

- [ ] **Step 2: 開発者向けメモと要望の状態を更新する**

`docs/development.md`のモジュール構成の表(`overview_dialog.py`の行の後)へ:

```markdown
| `notes.py` | タスクのメモ(要望 150)の保存(`~/.projectapp/notes/<名前>/<id>.html`)・読み込み・一覧・削除・コピー、タスク id の増減との同期(`sync`。ごみ箱は呼び出し側が持つ)。NiceGUI に依存しない |
| `note_pane.py` | メモの右ペイン(`NotePane`。`right_drawer`+`ui.editor`。約 1 秒で自動保存) |
```

`docs/requests.md`の要望 150 に、状態を足す(見出しの「(…に受領)」は変えない):

```markdown
### 状態
実装済み(`feature/task-notes`)。実機確認とマージの指示待ち。設計は`docs/superpowers/specs/2026-11-18-task-notes-design.md`、計画は`docs/superpowers/plans/2026-11-18-task-notes.md`。
```

- [ ] **Step 3: 検証とコミット**

```bash
uv run pytest -m smoke -q 2>&1 | tail -3
git add .claude/spec docs
git commit -m "docs: タスクのメモの仕様・保存先・モジュール構成・要望の状態を更新する(要望 150)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実機で確認すること(PR の本文に書く): ペインを開いたときのガントの見え方と、倍率(70%・100% 超)の見え方、日本語入力の変換中に自動保存がエディタの入力を壊さないこと、削除→元に戻すでメモが戻ること。
