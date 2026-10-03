# プロジェクトの保存 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **コミットについて:** ユーザーから許可が出るまでコミットしない。各タスク末尾の Commit ステップは、許可が出てから実施する(許可前は `git status` で変更を確認するだけにする)。作業ブランチは実行時に確認する(現在は `feature/schedule-calc`。`.claude/BRANCH.md` の git-flow に従い、必要なら新しい feature ブランチを切る)。

**Goal:** 画面の「保存」ボタンで、編集したプロジェクトを `~/.projectapp/<名前>.json` に保存できるようにする。新規プロジェクトは、最初の保存時に名前を入力する。

**Architecture:** 名前の検証と書き込みの安全化は `storage.py` の関数に寄せ、NiceGUI から切り離す。名前入力ダイアログは `forms.py` に、既存の `open_section_dialog` と同じ作りで置く。`MainView` が保存先のパス(`path`)を持ち、`None` なら新規として名前入力ダイアログを経由する。

**Tech Stack:** Python 3.13、NiceGUI 3.17、pytest / pytest-asyncio / pytest-cov、ty、uv

**Spec:** `docs/superpowers/specs/2026-10-03-project-save-design.md`

## Global Constraints

- Python 3.13 以上。パッケージャーは uv。UI 言語は日本語。
- すべての関数に型引数と戻り値の型ヒントを付ける。型チェックは `uvx ty check src`。
- コメントの説明は多くても3行以内。コードは PEP8 と The Zen of Python に従う。
- テストは pytest、カバレッジは pytest-cov。テストは `test/` に置く。
- 保存は、明示的な「保存」ボタンのみ。自動保存はしない。
- 新規プロジェクトは、最初の保存時に名前入力ダイアログを出す。新規のうちはディスクにファイルを置かない。
- 開いて読み込んだプロジェクトは、同じ名前で上書き保存する。名前は変更できない。
- 読込時に `project.name` をファイル名(拡張子なし)にそろえる。
- 名前の検証で拒否するもの: 空・空白だけ、`/` `\` `:` `*` `?` `"` `<` `>` `|` と制御文字、`.` で始まる名前、予約名(`config`、`holidays`)、新規で同名のファイルがすでにある名前。前後の空白は取り除いてから検証し、保存にも取り除いた名前を使う。
- 範囲外(作らない): 削除、複製、別名で保存、プロジェクト名の変更、未保存の変更の警告、自動保存。

## Review Focus

仕様が黙っているが、利用者が踏みやすい入力・状態。各行は、担当タスクのテストで固定する。

1. 名前の前後の空白(全角空白を含む): 取り除いて検証・保存する(Task 1、Task 2)。
2. 保存に失敗(ディスク満杯、権限)しても、元のファイルと画面の状態(`path`、プロジェクト名)は変わらない(Task 1、Task 3)。
3. ファイル名を手で変えたファイルを開いて保存する: 読込時に名前をファイル名にそろえるので、別ファイルができない(Task 1)。
4. 検証のあと、保存の直前に同名のファイルが作られた: 新規保存では上書きせずエラーにする(Task 1、Task 3)。
5. `~/.projectapp` がまだ存在しない初回の保存: ディレクトリを作って保存できる(Task 1)。

---

## File Structure

| ファイル | 操作 | 責務 |
|---|---|---|
| `src/projectapp/storage.py` | 変更 | `validate_name`、一時ファイル経由の `save_project`、読込時の名前そろえ |
| `src/projectapp/forms.py` | 変更 | `open_name_dialog` |
| `src/projectapp/views.py` | 変更 | 「保存」ボタン、保存の流れ、保存後の一覧更新 |
| `test/test_storage.py` | 変更 | 名前の検証・書き込みのテスト |
| `test/test_forms.py` | 変更 | 名前入力ダイアログのテスト |
| `test/test_views.py` | 変更 | 保存の流れのテスト |
| `docs/development.md`、設計書 | 変更 | 記述の更新 |

---

### Task 1: 名前の検証と安全な保存(storage.py)

**Files:**
- Modify: `src/projectapp/storage.py`
- Test: `test/test_storage.py`

**Interfaces:**
- Consumes: 既存の `Project`、`RESERVED`、`BASE_DIR`、`load_project`
- Produces:
  - `validate_name(name: str, base_dir: Path, *, new: bool) -> str | None`(エラー文、問題がなければ `None`)
  - `save_project(project: Project, base_dir: Path = BASE_DIR, *, overwrite: bool = True) -> Path`(名前が不正なら `ValueError`。`overwrite=False` で同名のファイルがあれば `FileExistsError`。書き込みの失敗は `OSError`)
  - `load_project(path)` が返す `Project.name` は `path.stem`

- [ ] **Step 1: Write the failing test**

`test/test_storage.py` の先頭の import に `import pytest` を足し、`from projectapp.storage import ...` を次に置き換える:

```python
from projectapp.storage import list_project_files, load_project, save_project, validate_name
```

末尾に追加:

```python
@pytest.mark.parametrize(
    "name",
    ["", "   ", "　", "a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b",
     "a\tb", ".hidden", "config", "holidays"],
)
def test_validate_name_rejects_unusable_names(name: str, tmp_path: Path) -> None:
    assert validate_name(name, tmp_path, new=True) is not None


def test_validate_name_accepts_japanese_and_strips_whitespace(tmp_path: Path) -> None:
    assert validate_name("デモ", tmp_path, new=True) is None
    assert validate_name("  デモ　", tmp_path, new=True) is None


def test_validate_name_detects_an_existing_file_only_for_new(tmp_path: Path) -> None:
    save_project(Project("demo"), tmp_path)
    assert validate_name("demo", tmp_path, new=True) is not None
    assert validate_name(" demo ", tmp_path, new=True) is not None
    assert validate_name("demo", tmp_path, new=False) is None


def test_validate_name_with_a_missing_base_dir(tmp_path: Path) -> None:
    assert validate_name("demo", tmp_path / "none", new=True) is None


@pytest.mark.parametrize("name", ["", "a/b", "config", ".x"])
def test_save_project_rejects_an_invalid_name(name: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_project(Project(name), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_save_project_strips_the_name_for_the_file(tmp_path: Path) -> None:
    assert save_project(Project(" demo "), tmp_path).name == "demo.json"


def test_save_project_creates_a_missing_base_dir(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path / ".projectapp")
    assert path.is_file()


def test_save_project_leaves_the_original_when_writing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = save_project(Project("demo", sections=[Section("元")]), tmp_path)
    before = path.read_text(encoding="utf-8")

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.storage.os.replace", boom)
    with pytest.raises(OSError):
        save_project(Project("demo", sections=[Section("新")]), tmp_path)
    assert path.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.json"]


def test_save_project_without_overwrite_creates_a_new_file(tmp_path: Path) -> None:
    path = save_project(Project("new"), tmp_path, overwrite=False)
    assert path.name == "new.json"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["new.json"]


def test_save_project_without_overwrite_refuses_an_existing_file(tmp_path: Path) -> None:
    path = save_project(Project("demo", sections=[Section("元")]), tmp_path)
    with pytest.raises(FileExistsError):
        save_project(Project("demo"), tmp_path, overwrite=False)
    assert load_project(path).sections[0].name == "元"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.json"]


def test_load_project_uses_the_file_name_as_the_name(tmp_path: Path) -> None:
    path = save_project(Project("demo"), tmp_path)
    renamed = path.rename(tmp_path / "other.json")
    assert load_project(renamed).name == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_storage.py -q`
Expected: FAIL(`validate_name` を import できない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/storage.py` の import に追加:

```python
import os
import tempfile
```

`RESERVED = ...` の下に追加:

```python
INVALID_NAME_CHARS = set('/\\:*?"<>|')
```

`save_project` を次に置き換え、その前に `validate_name` を置く:

```python
def validate_name(name: str, base_dir: Path, *, new: bool) -> str | None:
    """プロジェクト名を検証する。問題があればエラー文、なければNone。"""
    name = name.strip()
    if not name:
        return "名前を入力してください"
    if any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in name):
        return "名前に使えない文字が含まれています"
    if name.startswith("."):
        return "名前は「.」で始められません"
    if name in RESERVED:
        return "この名前は使えません"
    if new and (base_dir / f"{name}.json").exists():
        return "同じ名前のプロジェクトがすでにあります"
    return None


def save_project(
    project: Project, base_dir: Path = BASE_DIR, *, overwrite: bool = True
) -> Path:
    """一時ファイルへ書いてから置き換える。overwrite=Falseは既存ファイルを壊さない。"""
    name = project.name.strip()
    if error := validate_name(name, base_dir, new=False):
        raise ValueError(error)
    data = json.dumps(asdict(project), ensure_ascii=False, indent=2, default=_encode)
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{name}.json"
    fd, tmp_name = tempfile.mkstemp(dir=base_dir, prefix=".save-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(data)
        tmp.chmod(0o644)  # mkstempは所有者のみの権限で作る
        if overwrite:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)  # 既存ならFileExistsError
    finally:
        tmp.unlink(missing_ok=True)
    return path
```

`load_project` の `name=raw["name"],` を `name=path.stem,` に変更する。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`(既存のテストが落ちたら、名前とファイル名が食い違うテストがないか確認して直す)

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/storage.py test/test_storage.py
git commit -m "feat: プロジェクト名の検証と安全な保存を追加"
```

---

### Task 2: 名前入力ダイアログ(forms.py)

**Files:**
- Modify: `src/projectapp/forms.py`
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: なし(Task 1 の `validate_name` は `views` が `validate` として渡す)
- Produces: `open_name_dialog(on_submit: Callable[[str], object], validate: Callable[[str], str | None]) -> None`。保存ボタンで、前後の空白を取り除いた名前を `validate` に渡し、エラー文が返れば `name-error` のラベルに出して閉じない。`None` なら `on_submit(名前)` を呼んで閉じる。マーカー: 入力 `project-name`、保存 `name-save`、エラー `name-error`。

- [ ] **Step 1: Write the failing test**

`test/test_forms.py` の `from projectapp.forms import (...)` に `open_name_dialog,` を足し、末尾に追加:

```python
async def test_name_dialog_rejects_then_accepts_a_stripped_name(user: User) -> None:
    saved: list[str] = []
    seen: list[str] = []

    def validate(name: str) -> str | None:
        seen.append(name)
        return "使えない名前です" if name == "bad" else None

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_name_dialog(saved.append, validate))

    await user.open("/")
    user.find("open").click()
    user.find(marker="project-name").type("bad")
    user.find(marker="name-save").click()
    await user.should_see("使えない名前です")
    assert saved == []
    user.find(marker="project-name").clear().type("　デモ ")
    user.find(marker="name-save").click()
    assert saved == ["デモ"]
    assert seen == ["bad", "デモ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_forms.py::test_name_dialog_rejects_then_accepts_a_stripped_name -q`
Expected: FAIL(`open_name_dialog` を import できない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/forms.py` の末尾に追加:

```python
def open_name_dialog(
    on_submit: Callable[[str], object], validate: Callable[[str], str | None]
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("プロジェクトの保存").classes("text-h6")
        name = ui.input("プロジェクト名").mark("project-name")
        error = ui.label("").classes("text-negative").mark("name-error")

        def save() -> None:
            clean = (name.value or "").strip()
            if message := validate(clean):
                error.set_text(message)
                return
            on_submit(clean)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("name-save")
    dialog.open()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "feat: プロジェクト名の入力ダイアログを追加"
```

---

### Task 3: 保存ボタンと保存の流れ(views.py)

**Files:**
- Modify: `src/projectapp/views.py`
- Modify: `docs/development.md`
- Modify: `docs/superpowers/specs/2026-10-03-project-save-design.md`
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `storage.validate_name`、`storage.save_project(project, base_dir, *, overwrite)`(Task 1)、`forms.open_name_dialog`(Task 2)
- Produces:
  - `MainView.path: Path | None`(`None` は未保存の新規)
  - `MainView.file_select`(プロジェクトファイルの選択欄。マーカー `project-select`)
  - `MainView.save_project_clicked() -> None`(「保存」ボタン。マーカー `save-project`)
  - `MainView.write(*, overwrite: bool) -> bool`(保存して画面を更新する。失敗したら通知を出して `False`)

- [ ] **Step 1: Write the failing test**

`test/test_views.py` の import に追加:

```python
import pytest

from projectapp.models import Project, Section, Task
from projectapp.storage import load_project, save_project
```

(既存の `from projectapp.models import Task` は、上の行に統合する。)`mount` の下に補助関数を追加:

```python
def mount_capturing(base_dir: Path, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []))
        views.append(view)
        view.build()


async def save_new_as(user: User, name: str) -> None:
    user.find(marker="save-project").click()
    user.find(marker="project-name").type(name)
    user.find(marker="name-save").click()
```

末尾にテストを追加:

```python
async def test_save_new_project_asks_for_a_name_then_writes_the_file(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await save_new_as(user, "デモ")
    assert await wait_until(lambda: (tmp_path / "デモ.json").exists())
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    view = views[0]
    assert view.path == tmp_path / "デモ.json"
    assert "デモ" in view.file_select.options
    await user.should_see("デモ")


async def test_save_new_project_rejects_an_existing_name(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    original = save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await save_new_as(user, "既存")
    await user.should_see("同じ名前のプロジェクトがすでにあります")
    assert load_project(original).sections[0].name == "元"
    assert views[0].path is None


async def test_save_an_opened_project_overwrites_without_asking(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.selected = "既存"
    user.find("開く").click()
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    view.save_section("追加")
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    await user.should_not_see(marker="project-name")
    saved = load_project(tmp_path / "既存.json")
    assert [s.name for s in saved.sections] == ["元", "追加"]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (OSError("disk full"), "保存できませんでした"),
        (FileExistsError(), "同じ名前のファイルがすでにあります"),
    ],
)
async def test_failed_save_keeps_the_state(
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
    message: str,
) -> None:
    save_cache({}, tmp_path)

    def boom(*args: object, **kwargs: object) -> Path:
        raise error

    monkeypatch.setattr("projectapp.views.save_project", boom)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    await save_new_as(user, "デモ")
    assert await wait_until(lambda: user.notify.contains(message))
    view = views[0]
    assert view.path is None
    assert view.project.name == "新規プロジェクト"
    assert not (tmp_path / "デモ.json").exists()


async def test_saving_with_an_unusable_name_notifies(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.path = tmp_path / "x.json"
    view.project.name = "a:b"
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("名前に使えない文字が含まれています"))
    assert view.path == tmp_path / "x.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_views.py -q`
Expected: FAIL(`save-project` が見つからない、`file_select` がない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/views.py` を変更する。

import:

```python
from projectapp.forms import open_name_dialog, open_section_dialog, open_task_dialog
from projectapp.storage import BASE_DIR, list_project_files, load_project, save_project, validate_name
```

(長い行は、既存の書式に合わせて括弧で折り返す。)

`__init__` の `self.selected: str | None = None` の下に追加:

```python
        self.path: Path | None = None
```

`open_selected` を次に置き換える:

```python
    def open_selected(self) -> None:
        if self.selected is None:
            return
        self.path = self.files[self.selected]
        self.project = load_project(self.path)
        self.title.refresh()
        self.gantt.set_project(self.project)

    def save_project_clicked(self) -> None:
        if self.path is None:
            open_name_dialog(
                self.save_as_new,
                lambda name: validate_name(name, self.base_dir, new=True),
            )
            return
        self.write(overwrite=True)

    def save_as_new(self, name: str) -> None:
        previous = self.project.name
        self.project.name = name
        if not self.write(overwrite=False):
            self.project.name = previous

    def write(self, *, overwrite: bool) -> bool:
        """保存して画面を更新する。失敗したら通知だけ出し、状態は変えない。"""
        try:
            path = save_project(self.project, self.base_dir, overwrite=overwrite)
        except FileExistsError:
            ui.notify("同じ名前のファイルがすでにあります", type="negative")
            return False
        except (ValueError, OSError) as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return False
        self.path = path
        self.files[path.stem] = path
        self.file_select.set_options(sorted(self.files), value=path.stem)
        self.title.refresh()
        ui.notify("保存しました")
        return True
```

`header` の `ui.select(...)` から `ui.button("開く", ...)` までを次に置き換える:

```python
                self.file_select = ui.select(
                    list(self.files),
                    label="プロジェクトファイル",
                    on_change=lambda e: setattr(self, "selected", e.value),
                ).classes("w-64").mark("project-select")
                ui.button("開く", icon="folder_open", on_click=self.open_selected)
                ui.button("保存", icon="save", on_click=self.save_project_clicked).mark(
                    "save-project"
                )
```

`docs/development.md` のモジュール表を更新する: `forms.py` の行を「タスク・セクションの追加・編集ダイアログ、プロジェクト名の入力ダイアログと入力検証」に、`storage.py` の行を「`~/.projectapp/<名前>.json` の走査・名前の検証・保存(一時ファイル経由)・読込」に変える。

設計書 `2026-10-03-project-save-design.md` の「構成」の表の `storage.py` の行に、次を足す: 「`save_project(project, base_dir, *, overwrite=True)` の `overwrite=False` は、同名のファイルがあれば `FileExistsError` にする(新規保存の競合対策)」。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest --cov=projectapp -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: 手動確認(実機)**

Run: `uv run projectapp`
確認すること:
- 起動直後に「保存」を押すと、名前入力ダイアログが出る。空、`a/b`、`config` ではエラーが出て閉じない。
- 正しい名前(例: `デモ`)で保存すると、「保存しました」と通知され、タイトルが変わり、選択欄に `デモ` が入る。`~/.projectapp/デモ.json` ができている。
- タスクを足してもう一度「保存」を押すと、ダイアログなしで上書きされる。
- アプリを再起動し、選択欄から `デモ` を選んで「開く」を押すと、保存した内容が表示される。
- 再起動後、新規の状態で `デモ` の名前を入れて保存すると、「同じ名前のプロジェクトがすでにあります」と出る。

- [ ] **Step 6: Commit(許可が出てから)**

```bash
git add src/projectapp/views.py test/test_views.py docs/development.md docs/superpowers/specs/2026-10-03-project-save-design.md
git commit -m "feat: プロジェクトの保存ボタンと保存の流れを追加"
```

---

## Self-Review(計画の作成者による確認)

- **仕様の網羅**: 保存ボタン・新規の名前入力・上書き(Task 3)、名前の検証(Task 1、Task 2)、一覧とタイトルの更新(Task 3)、失敗時の通知と状態保持(Task 1、Task 3)、一時ファイル経由と競合対策(Task 1)、読込時の名前そろえ(Task 1)。範囲外の項目は作らない。
- **プレースホルダ**: なし。
- **型・名前の一貫性**: `validate_name(name, base_dir, *, new)`、`save_project(..., *, overwrite)`、`open_name_dialog(on_submit, validate)`、`MainView.path` / `file_select` / `save_project_clicked` / `write`、マーカー `project-name` / `name-save` / `name-error` / `save-project` / `project-select` は、全タスクで同じ。
- **設計書との差分**: `save_project` の `overwrite` 引数は、設計書の「競合は上書きせずエラー」を実現するための追加で、Task 3 で設計書にも反映する。
