# 外部変更の検知(保存時の確認) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 別のプロセス・iCloud・git が書き換えたプロジェクトファイルを、「上書き保存」が黙って消さないように、保存の直前に内容のハッシュで検知して 3 択の確認を出す。

**Architecture:** `storage.py` に、ハッシュ・検査・退避の純粋な関数を足す。`MainView` は読み込みの前にハッシュを覚え、`write` の入口で検査する。`CHANGED` のときは `forms.py` の確認ダイアログを出し、「保存して開く・作成・変更」の続き(`after`)を、`write` → ダイアログ → 保存の経路に引き継ぐ。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-12-external-change-design.md`

## Global Constraints

- 判定は、ファイルの内容の SHA-256(16 進)。更新時刻とサイズは使わない。
- 検査は上書き保存(`overwrite=True`)で `self.path` があるときの、保存の直前だけ。新規保存・名前をつけて保存は検査しない。
- `MISSING`: 「ファイルが見つかりませんでした。新しく作成します」を通知してから保存する(確認は出さない)。
- `CHANGED`: 見出し「ファイルが外部で変更されています」、本文「読み込んだあとに、別のプロセスや git、同期などでファイルが変わりました。上書きすると、その変更は失われます。」。3 択は「上書き」「名前をつけて保存」「キャンセル」。マーカーは `conflict-overwrite`・`conflict-save-as`・`conflict-cancel`。
- `.bak` は、上書きを選んだときだけ、`<名前>.json.bak` に 1 世代(既存は置き換える)。退避に失敗したら上書きせず「バックアップを作れなかったため、保存しませんでした」を通知する。
- ハッシュは読み込みの**前**に取る。保存の成功後は、書いたファイルを読み直して取り直す。`show_project(project, None)`・新規プロジェクトでは `None`。
- 「保存して開く・作成・変更」の続きは、保存に成功したときだけ行う(確認の 3 択から保存したときも同じ)。
- 既存のテストは変更なしで通ること。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- テストは `uv run pytest -n auto`、型は `uv run ty check src`。実際のホームの `~/.projectapp` を読み書きするテストは作らない(`tmp_path` を使う)。

## Review Focus

- 内容が同じで更新時刻だけ変わった(git checkout・iCloud): 確認を出さない。→ Task 1
- 上書きを選んだあと、続けて保存する: 確認が出ない(ハッシュの取り直し)。→ Task 2
- 「保存して開く」で外部変更があり、キャンセルする: 別のプロジェクトへ切り替わらず、編集内容も残る。→ Task 2
- 「名前をつけて保存」を選び、既存の名前を入れる: ダイアログが開いたまま、相手の版は触られない。→ Task 2
- 退避に失敗する: 相手の版を上書きしない。→ Task 2
- 確認ダイアログを開いたまま、ファイルが消える: 退避は飛ばして保存する(落ちない)。→ Task 2

---

## File Structure

| ファイル | 変更 |
|---|---|
| `src/projectapp/storage.py` | `file_digest`・`ExternalChange`・`check_external_change`・`backup_file` を足す |
| `src/projectapp/forms.py` | `open_conflict_dialog` を足す |
| `src/projectapp/views.py` | `digest` を持つ。`write` の検査と続きの引き継ぎ。`show_project` に `digest` |
| `test/test_storage.py` | 検知・退避のテスト |
| `test/test_views.py` | 保存の流れのテスト |
| `CLAUDE.md`(projectapp)・`docs/development.md`・`.claude/MEMORY.md`・`docs/request-history.md` | 仕様と実績の更新 |

---

### Task 1: 検知と退避の関数(`storage.py`)

**Files:**
- Modify: `src/projectapp/storage.py`
- Test: `test/test_storage.py`

**Interfaces:**
- Produces:
  - `file_digest(path: Path) -> str | None`
  - `class ExternalChange(Enum)`: `UNCHANGED`・`CHANGED`・`MISSING`
  - `check_external_change(path: Path, digest: str | None) -> ExternalChange`
  - `backup_file(path: Path) -> Path`

- [ ] **Step 1: ブランチを切り、設計書をコミットする**

```bash
git switch -c feature/external-change
git add docs/superpowers/specs/2026-10-12-external-change-design.md docs/superpowers/plans/2026-10-12-external-change.md .claude/MEMORY.md docs/request-history.md
git commit -m "docs: 外部変更の検知の設計書と実装計画を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: 失敗するテストを書く**(`test/test_storage.py` の末尾。import に `ExternalChange, backup_file, check_external_change, file_digest` を足す)

```python
def test_file_digest_is_the_same_for_the_same_content_and_none_when_missing(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    a.write_text("同じ", encoding="utf-8")
    b.write_text("同じ", encoding="utf-8")
    c.write_text("違う", encoding="utf-8")
    assert file_digest(a) == file_digest(b)
    assert file_digest(a) != file_digest(c)
    assert file_digest(tmp_path / "ない.json") is None


def test_check_external_change_unchanged_changed_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("元", encoding="utf-8")
    digest = file_digest(path)
    assert check_external_change(path, digest) is ExternalChange.UNCHANGED
    path.write_text("変更", encoding="utf-8")
    assert check_external_change(path, digest) is ExternalChange.CHANGED
    path.unlink()
    assert check_external_change(path, digest) is ExternalChange.MISSING


def test_check_external_change_ignores_a_modification_time_change_alone(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("元", encoding="utf-8")
    digest = file_digest(path)
    os.utime(path, (1_000_000_000, 1_000_000_000))
    assert check_external_change(path, digest) is ExternalChange.UNCHANGED


def test_check_external_change_without_a_remembered_digest_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("元", encoding="utf-8")
    assert check_external_change(path, None) is ExternalChange.UNCHANGED


def test_backup_file_copies_next_to_the_file_and_replaces_the_old_backup(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("一つ目", encoding="utf-8")
    backup = backup_file(path)
    assert backup == tmp_path / "p.json.bak"
    assert backup.read_text(encoding="utf-8") == "一つ目"
    path.write_text("二つ目", encoding="utf-8")
    backup_file(path)
    assert backup.read_text(encoding="utf-8") == "二つ目"


def test_backup_file_is_not_listed_as_a_project(tmp_path: Path) -> None:
    save_project(Project("p"), tmp_path)
    backup_file(tmp_path / "p.json")
    assert [f.name for f in list_project_files(tmp_path)] == ["p.json"]


def test_backup_file_raises_oserror_when_the_file_is_missing(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        backup_file(tmp_path / "ない.json")
```

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_storage.py -k "digest or external_change or backup" -v`
Expected: FAIL(ImportError: `file_digest` などがない)

- [ ] **Step 4: 実装する**(`storage.py`。`import hashlib`・`import shutil`・`from enum import Enum` を足し、`save_project` の前に置く)

```python
class ExternalChange(Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"


def file_digest(path: Path) -> str | None:
    """ファイルの内容の SHA-256(16 進)。なければ None。更新時刻は使わない(git や同期は内容が同じでも変える)。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def check_external_change(path: Path, digest: str | None) -> ExternalChange:
    """読み込んだときのハッシュ `digest` と、いまのファイルを比べる。覚えていなければ判定できないので UNCHANGED。"""
    current = file_digest(path)
    if current is None:
        return ExternalChange.MISSING
    if digest is None or current == digest:
        return ExternalChange.UNCHANGED
    return ExternalChange.CHANGED


def backup_file(path: Path) -> Path:
    """同じ場所の `<名前>.json.bak` に退避する(1 世代。既存は置き換える)。失敗は OSError のまま通す。"""
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    return backup
```

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest test/test_storage.py -v && uv run ty check src`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/storage.py test/test_storage.py
git commit -m "feat: ファイルの内容のハッシュで外部変更を検知する関数を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 保存の流れと確認ダイアログ(`forms.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`open_unsaved_dialog` の後ろ)
- Modify: `src/projectapp/views.py:231-262`(`save_then`・`open_project`・`show_project`)、`:336`(`save_as`)、`:656-690`(`save_project_clicked`・`save_as_new`・`write`)、`storage` の import(`:81`)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `file_digest`・`ExternalChange`・`check_external_change`・`backup_file`
- Produces:
  - `open_conflict_dialog(on_overwrite: Callable[[], object], on_save_as: Callable[[], object]) -> None`
  - `MainView.digest: str | None`
  - `MainView.write(*, overwrite: bool, after: Callable[[], object] | None = None) -> bool`(成功したら `after` を呼ぶ。確認を出したときは `False`)
  - `MainView.commit(*, overwrite: bool, after: Callable[[], object] | None) -> bool`(検査なしの保存)
  - `MainView.save_as_new(name: str, after: Callable[[], object] | None = None) -> bool`
  - `MainView.save_as_then(after: Callable[[], object] | None) -> None`
  - `MainView.show_project(project, path, digest: str | None = None)`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_views.py` の末尾。import の `projectapp.storage` に `file_digest` は不要。`pytest` は既存)

```python
async def open_with_external_change(user: User, tmp_path: Path) -> MainView:
    """「既存」を開き、自分の編集のあとで、相手がファイルを書き換えた状態にする。"""
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("元")]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    view.save_section("自分")
    save_project(Project("既存", sections=[Section("相手")]), tmp_path)
    return view


def section_names(path: Path) -> list[str]:
    return [s.name for s in load_project(path).sections]


async def test_save_after_an_external_change_asks_and_overwrite_keeps_the_other_version_as_bak(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    await user.should_see(marker="conflict-overwrite")
    assert section_names(tmp_path / "既存.json") == ["相手"]  # まだ書いていない
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: user.notify.contains("保存しました"))
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]
    assert section_names(tmp_path / "既存.json.bak") == ["相手"]
    assert not view.is_dirty()


async def test_save_after_overwriting_does_not_ask_again(user: User, tmp_path: Path) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: not view.is_dirty())
    view.save_section("さらに")
    user.find(marker="save-project").click()
    assert await wait_until(lambda: section_names(tmp_path / "既存.json") == ["元", "自分", "さらに"])
    await user.should_not_see(marker="conflict-overwrite")


async def test_external_change_cancel_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-cancel").click()
    await user.should_not_see(marker="conflict-cancel")
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert not (tmp_path / "既存.json.bak").exists()
    assert view.is_dirty()


async def test_external_change_save_as_leaves_the_other_version_and_switches(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-save-as").click()
    user.find(marker="project-name").clear().type("別名")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "別名.json")
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert section_names(tmp_path / "別名.json") == ["元", "自分"]
    assert not (tmp_path / "既存.json.bak").exists()


async def test_external_change_save_as_with_an_existing_name_keeps_the_dialog_open(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-save-as").click()
    user.find(marker="project-name").clear().type("既存")
    user.find(marker="name-save").click()
    await user.should_see(marker="project-name")
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert view.path == tmp_path / "既存.json"


async def test_external_change_with_a_failing_backup_does_not_overwrite(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(path: Path) -> Path:
        raise OSError("読み取り専用")

    monkeypatch.setattr("projectapp.views.backup_file", fail)
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: user.notify.contains("バックアップを作れなかったため、保存しませんでした"))
    assert section_names(tmp_path / "既存.json") == ["相手"]
    assert view.is_dirty()


async def test_overwrite_after_the_file_vanished_in_the_dialog_still_saves(
    user: User, tmp_path: Path
) -> None:
    view = await open_with_external_change(user, tmp_path)
    user.find(marker="save-project").click()
    await user.should_see(marker="conflict-overwrite")
    (tmp_path / "既存.json").unlink()
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: not view.is_dirty())
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]


async def test_save_when_the_file_vanished_notifies_and_creates_it(user: User, tmp_path: Path) -> None:
    view = await open_with_external_change(user, tmp_path)
    (tmp_path / "既存.json").unlink()
    user.find(marker="save-project").click()
    assert await wait_until(lambda: user.notify.contains("ファイルが見つかりませんでした。新しく作成します"))
    assert await wait_until(lambda: not view.is_dirty())
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]


async def test_save_and_open_continues_only_after_the_external_change_is_overwritten(
    user: User, tmp_path: Path
) -> None:
    save_project(Project("乙", sections=[Section("乙の中身")]), tmp_path)
    view = await open_with_external_change(user, tmp_path)
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    await user.should_see(marker="conflict-overwrite")
    assert view.path == tmp_path / "既存.json"
    user.find(marker="conflict-overwrite").click()
    assert await wait_until(lambda: view.path == tmp_path / "乙.json")
    assert section_names(tmp_path / "既存.json") == ["元", "自分"]


async def test_save_and_open_stays_when_the_external_change_dialog_is_cancelled(
    user: User, tmp_path: Path
) -> None:
    save_project(Project("乙"), tmp_path)
    view = await open_with_external_change(user, tmp_path)
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    user.find(marker="conflict-cancel").click()
    await user.should_not_see(marker="conflict-cancel")
    assert view.path == tmp_path / "既存.json"
    assert view.is_dirty()


async def test_save_and_open_with_save_as_continues_after_the_new_file_is_saved(
    user: User, tmp_path: Path
) -> None:
    save_project(Project("乙"), tmp_path)
    view = await open_with_external_change(user, tmp_path)
    await choose_in_combo(user, "乙")
    user.find(marker="unsaved-save").click()
    user.find(marker="conflict-save-as").click()
    user.find(marker="project-name").clear().type("別名")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: view.path == tmp_path / "乙.json")
    assert section_names(tmp_path / "別名.json") == ["元", "自分"]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -k "external_change or vanished" -v`
Expected: FAIL(`conflict-overwrite` が見つからない)

- [ ] **Step 3: 確認ダイアログを足す**(`forms.py`、`open_unsaved_dialog` の直後)

```python
def open_conflict_dialog(
    on_overwrite: Callable[[], object], on_save_as: Callable[[], object]
) -> None:
    """保存の直前に、ファイルが外部で変わっていたときの 3 択の確認(キャンセルは何もしない)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-96"):
        ui.label("ファイルが外部で変更されています").classes("text-h6")
        ui.label(
            "読み込んだあとに、別のプロセスや git、同期などでファイルが変わりました。"
            "上書きすると、その変更は失われます。"
        )

        def run(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("conflict-cancel")
            ui.button("名前をつけて保存", on_click=lambda: run(on_save_as)).props("flat").mark(
                "conflict-save-as"
            )
            ui.button("上書き", on_click=lambda: run(on_overwrite)).props("color=negative").mark(
                "conflict-overwrite"
            )
    dialog.open()
```

- [ ] **Step 4: `views.py` を変える**

`forms` の import に `open_conflict_dialog`、`storage` の import に `ExternalChange, backup_file, check_external_change, file_digest` を足す。

`__init__`(`self.path = None` の隣、`:164`)に足す:

```python
        self.digest: str | None = None
```

`save_then`・`open_project`・`show_project` を置き換える:

```python
    def save_then(self, after: Callable[[], object]) -> None:
        """保存に成功したときだけ、続きの処理を行う(外部変更の確認を挟んだときも、続きは引き継ぐ)。"""
        if self.path is None:
            open_name_dialog(
                lambda name: self.save_as_new(name, after),
                lambda name: validate_name(name, self.project_dir, new=True),
            )
        else:
            self.write(overwrite=True, after=after)

    def open_project(self, name: str) -> None:
        path = self.files[name]
        digest = file_digest(path)  # 読み込みの前に取る。間にファイルが変わっても、保存時に CHANGED になる側へ倒れる
        try:
            project = load_project(path)
        except (OSError, ValueError, KeyError) as exc:
            ui.notify(f"開けませんでした: {exc}", type="negative")
            self.file_select.set_value(self.current_name())
            return
        self.show_project(project, path, digest)

    def show_project(self, project: Project, path: Path | None, digest: str | None = None) -> None:
        """別のプロジェクトに切り替える(開いたとき・新規作成のとき)。保存済みの状態から始める。"""
        self.path, self.project, self.digest = path, project, digest
```
(`show_project` の残りの本体は変えない)

`save_as` を置き換える:

```python
    def save_as(self) -> None:
        """名前をつけて保存する。成功したら、新しいファイルが現在のプロジェクトになる(元のファイルは残る)。"""
        self.save_as_then(None)

    def save_as_then(self, after: Callable[[], object] | None) -> None:
        open_name_dialog(
            lambda name: self.save_as_new(name, after),
            lambda name: validate_name(name, self.project_dir, new=True),
            title="名前をつけて保存",
            initial=self.project.name,
        )
```

`save_project_clicked` の新規側の `open_name_dialog(self.save_as_new, ...)` はそのまま。`save_as_new` と `write` を置き換える:

```python
    def save_as_new(self, name: str, after: Callable[[], object] | None = None) -> bool:
        previous = self.project.name
        self.project.name = name
        if self.write(overwrite=False, after=after):
            return True
        self.project.name = previous
        return False

    def write(self, *, overwrite: bool, after: Callable[[], object] | None = None) -> bool:
        """保存して画面を更新する。成功したら `after` を呼ぶ。失敗したら通知だけ出し、状態は変えない。

        上書き保存の直前に、読み込んだあとの外部変更を調べる。変更があれば確認を出して False を返し、
        続きの `after` は、確認の結果の保存に引き継ぐ。
        """
        if overwrite and self.path is not None:
            change = check_external_change(self.path, self.digest)
            if change is ExternalChange.CHANGED:
                open_conflict_dialog(
                    on_overwrite=lambda: self.overwrite_external(after),
                    on_save_as=lambda: self.save_as_then(after),
                )
                return False
            if change is ExternalChange.MISSING:
                ui.notify("ファイルが見つかりませんでした。新しく作成します", type="warning")
        return self.commit(overwrite=overwrite, after=after)

    def overwrite_external(self, after: Callable[[], object] | None) -> None:
        """外部変更を承知で上書きする。相手の版は `.bak` に退避し、退避できなければ保存しない。"""
        if self.path is not None:
            try:
                backup_file(self.path)
            except FileNotFoundError:
                pass  # 確認の間に消えた。退避するものがない
            except OSError:
                ui.notify("バックアップを作れなかったため、保存しませんでした", type="negative")
                return
        self.commit(overwrite=True, after=after)

    def commit(self, *, overwrite: bool, after: Callable[[], object] | None) -> bool:
        """検査なしで保存する(`write` の本体)。"""
        try:
            path = save_project(self.project, self.project_dir, overwrite=overwrite)
        except FileExistsError:
            ui.notify("同じ名前のファイルがすでにあります", type="negative")
            return False
        except (ValueError, OSError) as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return False
        self.path = path
        self.digest = file_digest(path)  # 書いたファイルを読み直して覚える
        self.mark_clean()
        self.files[path.stem] = path
        self.file_select.set_options(sorted(self.files), value=path.stem)
        self.title.refresh()
        ui.notify("保存しました")
        if after is not None:
            after()
        return True
```

- [ ] **Step 5: 全体を通す**

Run: `uv run pytest -n auto && uv run ty check src`
Expected: PASS(新規 11 件 + 既存すべて)。落ちたら、`save_then` の変更で既存の「保存して開く」系が変わっていないか確認する。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_views.py
git commit -m "feat: 上書き保存の直前に外部変更を確認する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ドキュメントの更新

**Files:**
- Modify: `CLAUDE.md`(projectapp。「プロジェクトファイル」の節の末尾)
- Modify: `docs/development.md`(`storage.py` の行〔32 行目〕と、実装メモ〔132 行目の格納先の項の後〕)
- Modify: `.claude/MEMORY.md`・`docs/request-history.md`

- [ ] **Step 1: `CLAUDE.md` の「プロジェクトファイル」の節に足す**

```markdown
- 上書き保存の直前に、読み込んだあとにファイルが外部(別のプロセス・git・同期)で変わっていないかを、内容のハッシュで調べる(更新時刻は使わない)。変わっていたら、`上書き`・`名前をつけて保存`・`キャンセル`の確認ダイアログを表示する。`上書き`は、相手の版を`<名前>.json.bak`に 1 世代退避してから保存する(退避できなければ保存しない)。ファイルが消えていたら、通知して新しく作成する。`保存して開く`・`作成`・`変更`の保存でも同じ確認を挟み、続きは保存に成功したときだけ行う
```

- [ ] **Step 2: `docs/development.md` を更新する**

`storage.py` の行に「・外部変更の検知(`file_digest`・`check_external_change`)・`.bak` の退避(`backup_file`)」を足す。実装メモに次を足す:

```markdown
- 外部変更の検知(要望 10 の 2 番目の子): `MainView.digest` は、`open_project` が**読み込みの前**に取る(間にファイルが変わっても、保存時に `CHANGED` になる厳しい側へ倒れる)。保存の成功後は、書いたファイルを読み直して取り直す。検査は `write(overwrite=True)` の入口だけ。`write` と `save_then` は、続きの処理 `after` を引き継ぐ形で、`CHANGED` のときは `open_conflict_dialog` を出して `False` を返し、`上書き`(`overwrite_external` → `commit`)と`名前をつけて保存`(`save_as_then` → `save_as_new`)の保存の成功後に `after` を呼ぶ。`.bak` は上書きのときだけで、`*.json` に一致しないので一覧に出ない。
```

- [ ] **Step 3: `MEMORY.md` と `request-history.md` を更新する**

要望 10 の②を「実装済み(マージ待ち)」に、次にやることの 5 を「(完了)」にし、テスト件数(`uv run pytest -n auto` の結果)を書く。③ git の状態表示が次の子であることを残す。

- [ ] **Step 4: 確認してコミット**

Run: `uv run pytest -n auto && uv run ty check src`
Expected: PASS

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md docs/request-history.md
git commit -m "docs: 外部変更の検知の仕様と開発メモを更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
