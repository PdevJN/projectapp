# プロジェクトの格納先を指定する Implementation Plan

> **状態**: 実装済み — 要望 8 — マージ PR #11(210766f。2026-10-12)。設計書は [`2026-10-11-project-dir-design.md`](../specs/2026-10-11-project-dir-design.md)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プロジェクトファイルの置き場所(格納先)を、設定の置き場所(`~/.projectapp`)と分けて、ファイルメニューの「格納先を変更」で変えられるようにする。

**Architecture:** `config.json` に `project_dir` を足し、`MainView` に設定側の `base_dir` と格納先の `project_dir` を持たせる。検査と解決は `config.py` の関数にまとめ、フォルダ選択は `ImageExporter` に `ask_directory` として足す(ネイティブのみ)。

**Tech Stack:** Python 3.13、NiceGUI、pywebview、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-11-project-dir-design.md`

## Global Constraints

- 設定の置き場所は `~/.projectapp` の固定(`config.json`・`holidays.json`)。格納先を変えても動かさない。
- `config.json` のキーは `project_dir`(絶対パスの文字列)。未設定・空・文字列でない・相対パスは「未設定」として読む。`~` は展開して読む。
- 格納先の検査: 存在しない=「フォルダが見つかりません」、フォルダでない=「フォルダではありません」、書き込めない=「書き込めません」。空のフォルダは許可。検査は `os.access` だけで、ファイルを作らない。
- 起動時に使えない `project_dir` は、「格納先が見つからないため、既定の場所を使っています」を通知し、`base_dir` で起動する。`config.json` は書き換えない。
- `MainView` のコンストラクタの `base_dir` は設定側のままにする(既存のテストの呼び出しを変えない)。
- 「格納先を変更」のマーカーは `file-change-dir`、アイコンは `drive_file_move`。ファイルメニューの「祝日を更新」の前に置く。ネイティブウィンドウのみ。
- 編集中の確認は `open_unsaved_dialog(purpose="変更")`(ボタンは「保存して変更」「保存せず変更」「キャンセル」)。
- ショートカットは足さない。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- テストは `uv run pytest -n auto`、型は `uv run ty check src`。実際のホームの `~/.projectapp` を読み書きするテストは作らない(`tmp_path` を使う)。

## Review Focus

- 相対パスや空文字の `project_dir` が設定にある(手編集): 未設定として扱い、起動が落ちない。→ Task 1
- `project_dir` が `base_dir` と同じフォルダ: 分離しても、既存と同じに動く。→ Task 2(既存テストの全通過)
- 格納先を変えたあとに、古い格納先の「開いていたプロジェクト」が残らない: 新規の保存前プロジェクトになり、`file_select` の選択肢が新しい一覧になる。→ Task 4
- 同じフォルダを選び直す: 何も起きない(設定も書かない)。→ Task 4
- フォルダ選択をキャンセルする: 何も変わらない。→ Task 4
- 設定の保存に失敗(`OSError`): 格納先は変わらず、通知する。→ Task 4

---

## File Structure

| ファイル | 変更 |
|---|---|
| `src/projectapp/config.py` | `load_project_dir`・`save_project_dir`・`check_project_dir`・`resolve_project_dir` を足す |
| `src/projectapp/views.py` | `project_dir` を持つ。格納先を使う箇所を差し替える。「格納先を変更」を足す |
| `src/projectapp/export.py` | `ImageExporter.ask_directory` と `NativeImageExporter.ask_directory` を足す |
| `test/test_config.py` | 設定の読み書き・検査・解決のテスト |
| `test/test_views.py` | 分離・起動時のフォールバック・変更の操作のテスト。`FakeExporter` に `ask_directory`。メニューのテストを更新 |
| `CLAUDE.md`(projectapp) | 格納先の仕様に更新 |
| `docs/development.md` | 設定の置き場所と格納先の分離を追記 |
| `docs/request-history.md` | 要望 8 の状態を更新 |

---

### Task 1: 設定の読み書きと検査(`config.py`)

**Files:**
- Modify: `src/projectapp/config.py`
- Test: `test/test_config.py`

**Interfaces:**
- Consumes: `read_config(base_dir)`、`update_config(updates, base_dir)`(既存)
- Produces:
  - `load_project_dir(base_dir: Path = BASE_DIR) -> Path | None`
  - `save_project_dir(path: Path, base_dir: Path = BASE_DIR) -> None`
  - `check_project_dir(path: Path) -> str | None`
  - `resolve_project_dir(base_dir: Path = BASE_DIR) -> tuple[Path, str | None]`(使うフォルダ, 通知する文言)
  - `PROJECT_DIR_MISSING_MESSAGE: str`

- [ ] **Step 0: ブランチを切って、設計書をコミットする**

```bash
cd /Users/jun/Documents/opt/work/projectapp
git switch -c feature/project-dir
git add docs/superpowers/specs/2026-10-11-project-dir-design.md docs/superpowers/plans/2026-10-11-project-dir.md
git commit -m "docs: 要望 8(格納先の指定)の設計書と実装計画を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 1: 失敗するテストを書く**

`test/test_config.py` の import に `check_project_dir`・`load_project_dir`・`resolve_project_dir`・`save_project_dir`・`PROJECT_DIR_MISSING_MESSAGE` を足し、`import os` を先頭に足して、末尾に追記する。

```python
def test_project_dir_is_unset_by_default(tmp_path: Path) -> None:
    assert load_project_dir(tmp_path) is None


def test_project_dir_round_trips_and_keeps_the_other_keys(tmp_path: Path) -> None:
    save_theme("dark", tmp_path)
    folder = tmp_path / "shared"
    save_project_dir(folder, tmp_path)
    assert load_project_dir(tmp_path) == folder
    assert load_theme(tmp_path) == "dark"
    save_theme("light", tmp_path)  # ほかの設定を保存しても、格納先は消えない
    assert load_project_dir(tmp_path) == folder


@pytest.mark.parametrize("value", [None, "", "   ", 5, ["x"], "relative/dir"])
def test_an_invalid_project_dir_is_read_as_unset(tmp_path: Path, value: object) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"project_dir": value}), encoding="utf-8")
    assert load_project_dir(tmp_path) is None


def test_project_dir_expands_the_home_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / "config.json").write_text(json.dumps({"project_dir": "~/shared"}), encoding="utf-8")
    assert load_project_dir(tmp_path) == tmp_path / "shared"


def test_check_project_dir_accepts_an_existing_folder_even_if_empty(tmp_path: Path) -> None:
    assert check_project_dir(tmp_path) is None


def test_check_project_dir_rejects_a_missing_folder(tmp_path: Path) -> None:
    assert check_project_dir(tmp_path / "ない") == "フォルダが見つかりません"


def test_check_project_dir_rejects_a_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    assert check_project_dir(target) == "フォルダではありません"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="権限を外せない環境")
def test_check_project_dir_rejects_a_folder_that_cannot_be_written(tmp_path: Path) -> None:
    folder = tmp_path / "ro"
    folder.mkdir()
    folder.chmod(0o555)
    try:
        assert check_project_dir(folder) == "書き込めません"
    finally:
        folder.chmod(0o755)


def test_check_project_dir_does_not_create_files(tmp_path: Path) -> None:
    check_project_dir(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_resolve_project_dir_is_the_config_folder_when_unset(tmp_path: Path) -> None:
    assert resolve_project_dir(tmp_path) == (tmp_path, None)


def test_resolve_project_dir_uses_a_saved_usable_folder(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    save_project_dir(shared, tmp_path)
    assert resolve_project_dir(tmp_path) == (shared, None)


def test_resolve_project_dir_falls_back_without_touching_the_config(tmp_path: Path) -> None:
    missing = tmp_path / "ない"
    save_project_dir(missing, tmp_path)
    assert resolve_project_dir(tmp_path) == (tmp_path, PROJECT_DIR_MISSING_MESSAGE)
    assert load_project_dir(tmp_path) == missing  # 設定は残す(ドライブをつなぎ直せば戻る)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: FAIL(`ImportError: cannot import name 'check_project_dir'`)

- [ ] **Step 3: 実装する**

`src/projectapp/config.py` の末尾に追記する。

```python
PROJECT_DIR_MISSING_MESSAGE = "格納先が見つからないため、既定の場所を使っています"


def load_project_dir(base_dir: Path = BASE_DIR) -> Path | None:
    """プロジェクトの格納先。未設定・文字列でない・空・相対パスは None(`~` は展開する)。"""
    value = read_config(base_dir).get("project_dir")
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip()).expanduser()
    return path if path.is_absolute() else None


def save_project_dir(path: Path, base_dir: Path = BASE_DIR) -> None:
    update_config({"project_dir": str(path)}, base_dir)


def check_project_dir(path: Path) -> str | None:
    """格納先として使えるか。使えなければ理由を返す(ファイルは作らない。空のフォルダは使える)。"""
    if not path.exists():
        return "フォルダが見つかりません"
    if not path.is_dir():
        return "フォルダではありません"
    if not os.access(path, os.W_OK | os.X_OK):
        return "書き込めません"
    return None


def resolve_project_dir(base_dir: Path = BASE_DIR) -> tuple[Path, str | None]:
    """起動時に使う格納先と、通知する文言。保存した格納先が使えなければ、`base_dir` を使う(設定は書き換えない)。"""
    saved = load_project_dir(base_dir)
    if saved is None:
        return base_dir, None
    if check_project_dir(saved) is not None:
        return base_dir, PROJECT_DIR_MISSING_MESSAGE
    return saved, None
```

あわせて、ファイル先頭の docstring は変えない(設定の置き場所の説明のまま)。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_config.py -q && uv run ty check src`
Expected: PASS、ty にエラーなし

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/config.py test/test_config.py
git commit -m "feat: config.json に project_dir を足し、格納先の検査と起動時の解決を作る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `MainView` の設定側と格納先の分離

**Files:**
- Modify: `src/projectapp/views.py`(import、`__init__`、`show_file_list`、`save_as`、`save_then`、`open_project_folder`、`write`、`save_as_new`、`build`)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `resolve_project_dir`(Task 1)
- Produces: `MainView.project_dir: Path`、`MainView(base_dir, transport, exporter, project_dir: Path | None = None)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の import に `load_project_dir`・`save_project_dir`(`projectapp.config`)を足す(既存の `from projectapp.config import ...` があればそこへ)。`mount_preview` の近く(`open_header_view` の前)に追記する。

```python
def mount_with_project_dir(base_dir: Path, project_dir: Path | None, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []), FakeExporter(), project_dir=project_dir)
        views.append(view)
        view.build()


async def test_projects_live_in_the_project_dir_and_settings_stay_in_the_config_dir(
    user: User, tmp_path: Path
) -> None:
    base, shared = tmp_path / "config", tmp_path / "shared"
    save_cache({}, base)
    save_project(Project("共有"), shared)
    views: list[MainView] = []
    mount_with_project_dir(base, shared, views)
    await user.open("/")
    view = views[0]
    assert set(view.files) == {"共有"}  # 設定側にあるファイルは見ない
    view.set_theme("dark")
    assert view.save_as_new("デモ")
    assert (shared / "デモ.json").exists() and not (base / "デモ.json").exists()
    assert (base / "config.json").exists() and not (shared / "config.json").exists()
    assert (base / "holidays.json").exists() and not (shared / "holidays.json").exists()


async def test_a_saved_project_dir_is_used_when_none_is_given(user: User, tmp_path: Path) -> None:
    base, shared = tmp_path / "config", tmp_path / "shared"
    save_cache({}, base)
    shared.mkdir()
    save_project_dir(shared, base)
    views: list[MainView] = []
    mount_with_project_dir(base, None, views)
    await user.open("/")
    assert views[0].project_dir == shared


async def test_an_unusable_saved_project_dir_falls_back_with_a_notice_and_keeps_the_setting(
    user: User, tmp_path: Path
) -> None:
    base, missing = tmp_path / "config", tmp_path / "ない"
    save_cache({}, base)
    save_project_dir(missing, base)
    views: list[MainView] = []
    mount_with_project_dir(base, None, views)
    await user.open("/")
    assert views[0].project_dir == base
    await user.should_see("既定の場所を使っています")
    assert load_project_dir(base) == missing


async def test_the_folder_button_opens_the_project_dir(user: User, tmp_path: Path) -> None:
    base, shared = tmp_path / "config", tmp_path / "shared"
    save_cache({}, base)
    shared.mkdir()
    views: list[MainView] = []
    mount_with_project_dir(base, shared, views)
    await user.open("/")
    opened: list[Path] = []
    views[0].open_folder = opened.append  # type: ignore[method-assign]
    user.find(marker="open-folder").click()
    assert opened == [shared]
```

注: `FakeExporter` は `test_views.py` の 1429 行付近で定義されている。関数本体の中で使うだけなので、定義の順序は問題ない。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "project_dir or folder_button_opens_the_project_dir"`
Expected: FAIL(`TypeError: MainView.__init__() got an unexpected keyword argument 'project_dir'`)

- [ ] **Step 3: 実装する**

`src/projectapp/views.py`:

1. `from projectapp.config import (...)` に `resolve_project_dir` を足す(アルファベット順の位置)。
2. `__init__` のシグネチャと冒頭を次のようにする。

```python
    def __init__(
        self,
        base_dir: Path = BASE_DIR,
        transport: httpx.AsyncBaseTransport | None = None,
        exporter: ImageExporter | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self.base_dir = base_dir  # 設定(config.json)と祝日のキャッシュの置き場所。固定
        self.startup_notice: str | None = None
        if project_dir is None:
            project_dir, self.startup_notice = resolve_project_dir(base_dir)
        self.project_dir = project_dir  # プロジェクトファイルの格納先
```

3. `self.files = {p.stem: p for p in list_project_files(base_dir)}`(`__init__` 内)を `list_project_files(self.project_dir)` にする。
4. 次の箇所の `self.base_dir` を `self.project_dir` に変える(設定・祝日の `self.base_dir` は変えない)。
   - `save_then` の `validate_name(name, self.base_dir, new=True)`
   - `open_project_folder` の `self.open_folder(self.base_dir)`
   - `save_as` の `validate_name(name, self.base_dir, new=True)`
   - `show_file_list` の `list_project_files(self.base_dir)`
   - `save_as_new`(`self.project` の保存と同じ関数にある `validate_name(name, self.base_dir, new=True)`)
   - `write` の `save_project(self.project, self.base_dir, overwrite=overwrite)`
   
   実際の行は `grep -n "self.base_dir" src/projectapp/views.py` で確かめる。残る `self.base_dir` は、`save_theme`・`save_name_width`・`save_zoom`・`save_task_layout`・`download_holidays` だけにする。
5. `build` の `if self.needs_first_fetch:` の前に追記する。

```python
        if self.startup_notice:
            ui.notify(self.startup_notice, type="warning")
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全体が PASS(既存のテストは `base_dir` と格納先が同じなので、変更なしで通る)、ty にエラーなし

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: 設定の置き場所とプロジェクトの格納先を分ける

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 「格納先を変更」の操作

**Files:**
- Modify: `src/projectapp/export.py`(`ImageExporter`、`NativeImageExporter`)
- Modify: `src/projectapp/views.py`(メニュー、`request_change_project_dir` ほか)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `check_project_dir`・`save_project_dir`(Task 1)、`MainView.project_dir`(Task 2)、`open_unsaved_dialog`(既存)
- Produces: `ImageExporter.ask_directory() -> Path | None`、`MainView.request_change_project_dir()`、`MainView.change_project_dir(path: Path)`

- [ ] **Step 1: 失敗するテストを書く**

`FakeExporter` を拡張する(`test/test_views.py`)。`__init__` の引数に `directory: Path | None = None` を足し、本体に次を足す。

```python
        self.directory = directory
        self.asked_directory = 0
```

クラスの末尾に足す。

```python
    async def ask_directory(self) -> Path | None:
        self.asked_directory += 1
        return self.directory
```

テストを追記する(`open_saved_view` の近く)。

```python
async def open_dir_view(user: User, tmp_path: Path, directory: Path | None, *, available: bool = True) -> tuple[MainView, FakeExporter]:
    """設定側 tmp_path/config に「甲」を置いて開いた状態。フォルダ選択は、directory を返す。"""
    base = tmp_path / "config"
    save_cache({}, base)
    save_project(Project("甲", sections=[Section("甲の中身")]), base)
    exporter = FakeExporter(directory=directory, available=available)
    views: list[MainView] = []
    mount_preview(base, views, exporter)
    await user.open("/")
    views[0].request_open("甲")
    assert views[0].path == base / "甲.json"
    return views[0], exporter


async def test_changing_the_project_dir_switches_the_list_and_starts_a_new_project(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    save_project(Project("乙"), shared)
    view, _ = await open_dir_view(user, tmp_path, shared)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: view.project_dir == shared)
    assert load_project_dir(tmp_path / "config") == shared
    assert set(view.files) == {"乙"} and list(view.file_select.options) == ["乙"]
    assert view.path is None and view.project.name == "新規プロジェクト" and view.file_select.value is None
    assert (tmp_path / "config" / "甲.json").exists()  # 古い格納先のファイルは、そのまま残す


async def test_changing_to_an_empty_folder_is_allowed(user: User, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    view, _ = await open_dir_view(user, tmp_path, empty)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: view.project_dir == empty)
    assert view.files == {}


async def test_an_unusable_folder_is_rejected_and_nothing_changes(user: User, tmp_path: Path) -> None:
    view, _ = await open_dir_view(user, tmp_path, tmp_path / "ない")
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: user.notify.contains("このフォルダは使えません"))
    assert view.project_dir == tmp_path / "config" and view.path == tmp_path / "config" / "甲.json"
    assert load_project_dir(tmp_path / "config") is None


async def test_cancelling_the_folder_dialog_changes_nothing(user: User, tmp_path: Path) -> None:
    view, exporter = await open_dir_view(user, tmp_path, None)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: exporter.asked_directory == 1)
    assert view.project_dir == tmp_path / "config" and view.path is not None
    assert load_project_dir(tmp_path / "config") is None


async def test_choosing_the_current_folder_does_nothing(user: User, tmp_path: Path) -> None:
    view, exporter = await open_dir_view(user, tmp_path, tmp_path / "config")
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: exporter.asked_directory == 1)
    assert view.path is not None  # プロジェクトを閉じない
    assert load_project_dir(tmp_path / "config") is None  # 設定も書かない


async def test_a_failure_to_save_the_setting_keeps_the_old_folder(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, _ = await open_dir_view(user, tmp_path, shared)

    def fail(path: Path, base_dir: Path) -> None:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.save_project_dir", fail)
    user.find(marker="file-change-dir").click()
    assert await wait_until(lambda: user.notify.contains("保存できませんでした"))
    assert view.project_dir == tmp_path / "config" and view.path is not None


async def test_changing_the_folder_is_native_only(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, exporter = await open_dir_view(user, tmp_path, shared, available=False)
    user.find(marker="file-change-dir").click()
    await user.should_see("ネイティブウィンドウでのみ")
    assert exporter.asked_directory == 0 and view.project_dir == tmp_path / "config"


async def test_changing_the_folder_asks_before_dropping_unsaved_changes(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, exporter = await open_dir_view(user, tmp_path, shared)
    view.save_section("追加")
    user.find(marker="file-change-dir").click()
    await user.should_see("変更前に")
    assert exporter.asked_directory == 0  # 確認より先に、フォルダを選ばせない
    user.find(marker="unsaved-cancel").click()
    assert exporter.asked_directory == 0 and view.project_dir == tmp_path / "config"


async def test_changing_the_folder_can_discard_the_changes(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, _ = await open_dir_view(user, tmp_path, shared)
    view.save_section("追加")
    user.find(marker="file-change-dir").click()
    user.find(marker="unsaved-discard").click()
    assert await wait_until(lambda: view.project_dir == shared)
    assert [s.name for s in load_project(tmp_path / "config" / "甲.json").sections] == ["甲の中身"]


async def test_changing_the_folder_can_save_first(user: User, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    view, _ = await open_dir_view(user, tmp_path, shared)
    view.save_section("追加")
    user.find(marker="file-change-dir").click()
    user.find(marker="unsaved-save").click()
    assert await wait_until(lambda: view.project_dir == shared)
    assert [s.name for s in load_project(tmp_path / "config" / "甲.json").sections] == ["甲の中身", "追加"]
```

既存のメニューのテストを更新する(`test_the_menus_list_their_items_in_order` と `test_the_file_menu_separates_open_save_and_update`)。

```python
    assert menu_items(user, "menu-file-items") == [
        ("開く", "file-open"),
        ("新規プロジェクト作成", "file-new"),
        ("上書き保存", "save-project"),
        ("名前をつけて保存", "file-save-as"),
        ("格納先を変更", "file-change-dir"),
        ("祝日を更新", "refresh-holidays"),
    ]
    ...
    assert menu_icons(user, "menu-file-items") == ["folder_open", "note_add", "save", "save_as", "drive_file_move", "event_repeat"]
```

```python
    assert kinds == ["item", "item", "sep", "item", "item", "sep", "item", "item"]
```

(区切りは変えない。「格納先を変更」と「祝日を更新」は、同じグループに並ぶ。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "changing or project_dir or menus_list or file_menu_separates or unusable_folder or cancelling_the_folder or choosing_the_current"`
Expected: FAIL(`file-change-dir` がない・`ask_directory` がない)

- [ ] **Step 3: 実装する**

`src/projectapp/export.py`:

`ImageExporter` に足す。

```python
    async def ask_directory(self) -> Path | None: ...
```

`NativeImageExporter` に足す(`ask_path` の次)。

```python
    async def ask_directory(self) -> Path | None:
        import webview  # ネイティブのときだけ使う

        window = app.native.main_window
        if window is None:
            return None
        result = await window.create_file_dialog(  # ty: ignore[unresolved-attribute]
            dialog_type=webview.FileDialog.FOLDER,
        )
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])
```

`src/projectapp/views.py`:

1. import に `check_project_dir`・`save_project_dir`(`projectapp.config`)を足す。
2. 定数を `HANDOFF_NOT_NATIVE_MESSAGE` の隣に足す。

```python
CHANGE_DIR_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、格納先を変更できます"
```

3. ファイルメニューの `MenuItem("祝日を更新", ...)` の前に足す(水平線の後ろ)。

```python
                    MenuItem("格納先を変更", "drive_file_move", self.request_change_project_dir, "file-change-dir"),
```

4. `request_new` の後ろにメソッドを足す。

```python
    def request_change_project_dir(self) -> None:
        """格納先を変える(ネイティブのみ)。編集中は、確認してからフォルダを選ばせる。"""
        if not self.exporter.available:
            ui.notify(CHANGE_DIR_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not self.is_dirty():
            self.pick_project_dir()
            return
        open_unsaved_dialog(
            on_save=lambda: self.save_then(self.pick_project_dir),
            on_discard=self.pick_project_dir,
            purpose="変更",
        )

    def pick_project_dir(self) -> None:
        """フォルダ選択を始める。確認ダイアログは閉じると消えるので、タイマーは画面の直下に置く。"""
        with self.client:
            ui.timer(0, self.choose_project_dir, once=True)

    async def choose_project_dir(self) -> None:
        path = await self.exporter.ask_directory()
        if path is not None:
            self.change_project_dir(path)

    def change_project_dir(self, path: Path) -> None:
        """検査に通れば、格納先を保存して、ファイル一覧を読み直し、保存前の新規プロジェクトにする。"""
        if path.resolve() == self.project_dir.resolve():
            return
        if error := check_project_dir(path):
            ui.notify(f"このフォルダは使えません: {error}", type="negative")
            return
        try:
            save_project_dir(path, self.base_dir)
        except OSError as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        self.project_dir = path
        self.files = {p.stem: p for p in list_project_files(path)}
        self.file_select.set_options(sorted(self.files), value=None)
        self.new_project()
```

注: `self.client` は `build` で `ui.context.client` から設定される。`with self.client:` が効かない場合(NiceGUI のバージョンで挙動が違う場合)は、`ui.timer` の代わりに `background_tasks.create(self.choose_project_dir())` を使い、テストが通ることを確かめる。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全体が PASS、ty にエラーなし

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/export.py src/projectapp/views.py test/test_views.py
git commit -m "feat: ファイルメニューに「格納先を変更」を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ドキュメントの更新と最終確認

**Files:**
- Modify: `CLAUDE.md`(projectapp 直下)
- Modify: `docs/development.md`
- Modify: `docs/request-history.md`

**Interfaces:**
- Consumes: Task 1〜3 の実装
- Produces: 仕様と実装の記述の一致

- [ ] **Step 1: `CLAUDE.md` を更新する**

次の箇所を、`Edit` で書き換える。

1. 「プロジェクトファイル」の節:
   `- プロジェクトファイルは、`~/.projectapp/プロジェクトの名前.json`というjsonファイルで管理できる` を
   `- プロジェクトファイルは、格納先(既定は`~/.projectapp`)の`プロジェクトの名前.json`というjsonファイルで管理できる`
   に変え、続けて次の項目を足す。
   `- 格納先は、`ファイル`メニューの`格納先を変更`で、OS のフォルダ選択から変えられる(ネイティブウィンドウのみ)。選んだ格納先は、`~/.projectapp/config.json`の`project_dir`に保存する。存在しない・フォルダでない・書き込めないフォルダは、理由を通知して変えない(空のフォルダは選べる)。変えると、ファイル一覧を読み直し、保存前の新規プロジェクトにする(編集中は、`保存して変更`・`保存せず変更`・`キャンセル`の確認ダイアログを表示する。古い格納先のファイルは動かさない)。起動時に、保存した格納先が使えないときは、通知して`~/.projectapp`で起動する(設定は書き換えない)`
2. 「基準ディレクトリ」を指す箇所(起動時の節の `基準ディレクトリのプロジェクトファイルを走査する`、プロジェクトファイルの節の `projectファイルは、基準ディレクトリに配置ができ`)を、`格納先`に言い換える。
3. 「データの保存先」の節:
   `- プロジェクト(...)は、`~/.projectapp/プロジェクトの名前.json`に1ファイルずつ保存する` を `...は、格納先の`プロジェクトの名前.json`に1ファイルずつ保存する(既定は`~/.projectapp`)` に変える。
   `- テーマと名前の欄の幅と画面の倍率は`~/.projectapp/config.json`、...` に、`格納先(`project_dir`)`を加える。設定と祝日のキャッシュは、格納先を変えても`~/.projectapp`に残る旨を一文足す。
4. 「ヘッダー」の節の `ファイル`メニュー: `名前をつけて保存`・(水平線)・`祝日を更新` を `名前をつけて保存`・(水平線)・`格納先を変更`・`祝日を更新` にする。プロジェクト格納フォルダのアイコンの説明の `~/.projectapp` を `格納先` にする。

- [ ] **Step 2: `docs/development.md` を更新する**

`config.py` の行(33 行付近の表)を次に変える。
`| `config.py` | テーマ・名前の欄の幅・倍率・レイアウト・格納先(`project_dir`)の設定(`config.json`。読んで更新して書く)。格納先の検査(`check_project_dir`)と起動時の解決(`resolve_project_dir`) |`

実装メモの節(132 行付近の「画面の倍率」の前)に項目を足す。

`- 格納先(要望 8): 設定(`config.json`・`holidays.json`)の置き場所 `MainView.base_dir`(固定の `~/.projectapp`)と、プロジェクトファイルの格納先 `MainView.project_dir` は別。`project_dir` は `config.json` の `project_dir`(絶対パス。相対・空・不正は未設定)で、起動時に `resolve_project_dir` が決める(使えなければ通知して `base_dir`。設定は書き換えない)。コンストラクタの `base_dir` は設定側のまま、`project_dir` 引数で上書きできる(テスト用)。ファイルメニューの「格納先を変更」(`file-change-dir`)は、`ImageExporter.ask_directory`(ネイティブのみ)で選び、`change_project_dir` が検査 → 保存 → 一覧の読み直し → 新規プロジェクトの順に行う。確認ダイアログは閉じると消えるので、フォルダ選択の `ui.timer` は `self.client` の直下に置く。`storage.py` の関数は、引数のディレクトリを格納先として扱う(設定側のことは知らない)。`

- [ ] **Step 3: `docs/request-history.md` を更新する**

要望 8 の行を、状態「完了」・設計書 `project-dir`・マージは「(PR 後に記入)」にする代わりに、実際のマージ後に書く。この段階では、備考に `設計書・実装計画あり。実装済み(ブランチ feature/project-dir)` と書く。集計(1〜36)の「完了」「未着手」の件数と番号は、マージ後に更新するので、ここでは変えない。「未着手の整理」の要望 8 の行は、次の一歩を `実装済み。マージ待ち` にする。

- [ ] **Step 4: 全体の確認**

Run: `uv run pytest -n auto -q && uv run ty check src && git status -sb`
Expected: 全テスト PASS、ty にエラーなし、変更は上の3ファイルだけ

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md docs/development.md docs/request-history.md
git commit -m "docs: 格納先の指定(要望 8)の仕様と開発メモを更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## 実機で確認すること(自動テストの外)

- ネイティブで、「格納先を変更」のフォルダ選択ダイアログが開き、選んだフォルダに切り替わる。
- 切り替えたあと、アプリを再起動しても、同じ格納先で起動する。
- 格納先のフォルダを消して(または名前を変えて)起動すると、通知が出て、`~/.projectapp` で起動する。`config.json` の `project_dir` が残っている。
- フォルダを開くボタンが、新しい格納先を Finder で開く。
- テーマ・倍率・名前の欄の幅が、格納先を変えても保たれる。
