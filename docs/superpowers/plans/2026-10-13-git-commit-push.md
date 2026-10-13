# git のコミットとプッシュ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 変更のあるプロジェクトファイルを一覧から選んでコミットし、プッシュして共有できるようにする(ヘッダーの 5 つ目のメニュー「Git」とショートカット)。

**Architecture:** 書き込み系を、NiceGUI に依存しない`gitops.py`に分ける(`gitstate.py`は読み取り専用のまま。`run_git`・`failure_reason`を共有する)。画面は、`forms.py`のコミットのダイアログと、`MainView`の「Git」メニュー・押せない理由の判定(`git_reason`)・実行(`run.io_bound`、`git_busy`)で組む。実行のあとは、3 番目の子のチップを読み直す。

**Tech Stack:** Python 3.13、NiceGUI 3.17、`git`コマンド(`subprocess`)、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-13-git-commit-push-design.md`(2026-10-13 承認)

## Global Constraints

- `git`は`subprocess.run`の直呼び(`gitstate.run_git`)。シェルを通さない。環境は、`GIT_DIR`・`GIT_WORK_TREE`・`GIT_INDEX_FILE`を除き、`GIT_OPTIONAL_LOCKS=0`・`LC_ALL=C`・`GIT_TERMINAL_PROMPT=0`を足す。標準入力なし。Windows ではコンソール窓なし。
- 作業フォルダは`git -C <格納先>`で渡す。ファイル名を渡す`add`・`commit`には`--literal-pathspecs`を付ける。
- プロジェクトファイルの範囲は、3 番目の子と同じ固定のパス指定(`gitstate.PATHSPEC`: `:(glob)*.json`と、予約名`config`・`holidays`の除外)。
- コミットは`git add -A -- <名前>`のあと`git commit --only -m <メッセージ> -- <名前>`。利用者が別に stage したファイルは、コミットに入れず、その stage も変えない。変更のない名前を含むときは、`git commit`を呼ばない。
- タイムアウト: `list_changes`は 5 秒、`commit`は 30 秒、`push`は 60 秒。
- `gitops`の関数は、例外を外へ出さず、`GitResult(ok=False, message=理由)`で返す。
- メニュー「Git」: ヘッダーの左から 4 つ目(順は「ファイル」「プロジェクト」「エクスポート」「Git」「ヘルプ」)。マーカー`menu-git`、項目のマーカーは`git-commit`・`git-push`・`git-refresh`。アイコンは`commit`・`cloud_upload`・`refresh`。文言は「コミット…」「プッシュ」「状態を読み直す」。右端のキーは、`Ctrl/Cmd+K`・`Ctrl/Cmd+Shift+K`(「状態を読み直す」にはなし)。
- ショートカット: `Ctrl/Cmd+K`=`git_commit`(コミット)、`Ctrl/Cmd+Shift+K`=`git_push`(プッシュ)。押せないときは、理由を通知する。
- 押せない理由の文言: `git の作業ツリーではありません`・`実行中です`・`git の状態を読めていません`・`上流がありません`・`上流が見つかりません`・`未プッシュのコミットがありません`。
- コミットのダイアログのマーカー: `commit-file-<名前>`(チェックボックス)、`commit-message`、`commit-unsaved`、`commit-submit`(コミット)、`commit-submit-push`(コミットしてプッシュ)、`commit-cancel`。
- 通知の文言: 成功は`コミットしました(<短いハッシュ>)`・`プッシュしました`、変更なしは`コミットする変更がありません`、コミット成功でプッシュ失敗は`コミットしました。プッシュに失敗しました: <理由>`(`warning`)、拒否には`先にプルが必要です(プルは後続機能)`を添える。
- 既存のテストは、この計画で直すと明記したもの以外、変更なしで通ること。
- コード規約: すべての関数に型ヒント。コメントは多くても 3 行。日本語で書く。
- テストは`uv run pytest -n auto`、型は`uv run ty check src`。実際のホームの`~/.projectapp`は読み書きしない(`tmp_path`を使う)。
- コミットメッセージの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。

## Review Focus

- 利用者が別に stage したファイルが、選んだファイルのコミットに入らず、その stage も残る。→ Task 3
- 日本語名・削除・未追跡・改名・サブフォルダの格納先で、名前が正しく取れる(`-z`のパスはルート基準)。→ Task 2
- 実行中に二重で始めない。コミットが例外で落ちても`git_busy`が下りる。→ Task 5
- プッシュの拒否・上流なし・認証の入力待ち(`GIT_TERMINAL_PROMPT=0`)で止まらない。→ Task 1・3
- 未保存の編集の警告が出る。ショートカットで押せないとき、何も起きないのではなく理由が通知される。→ Task 4・5

---

## File Structure

| ファイル | 変更 |
|---|---|
| `src/projectapp/gitstate.py` | `_run`→`run_git`、`_reason`→`failure_reason`に公開。`GIT_TERMINAL_PROMPT=0`を足す |
| `src/projectapp/gitops.py` | 新規。`ChangeStatus`・`FileChange`・`GitResult`・`list_changes`・`default_message`・`commit`・`push` |
| `src/projectapp/forms.py` | `open_commit_dialog`を足す |
| `src/projectapp/shortcuts.py` | `git_commit`・`git_push`、`label_for(action)`を足す |
| `src/projectapp/views.py` | メニュー「Git」、`git_reason`、`update_git_menu`、実行(`run_commit`・`run_push`)、`git_busy`、`later` |
| `test/test_gitstate.py` | 公開名への追従と、環境のテスト |
| `test/test_gitops.py` | 新規 |
| `test/test_commit_dialog.py` | 新規 |
| `test/test_git_ops_view.py` | 新規。メニュー・実行の流れ |
| `test/test_shortcuts.py`・`test/test_views.py` | 新しいキーとメニューへの追従 |
| `CLAUDE.md`・`docs/development.md`・`docs/request-history.md`・`.claude/MEMORY.md` | 仕様と記録の更新 |

---

### Task 1: `gitstate.py`の共有部分を公開する

**Files:**
- Modify: `src/projectapp/gitstate.py`
- Test: `test/test_gitstate.py`

**Interfaces:**
- Produces:
  - `run_git(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]`(旧`_run`。環境に`GIT_TERMINAL_PROMPT=0`を足す)
  - `failure_reason(result: subprocess.CompletedProcess[str]) -> str`(旧`_reason`)
  - `Runner`・`PATHSPEC`・`DEFAULT_TIMEOUT`(既存。`gitops`が使う)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gitstate.py`の import の`_run`を`run_git`に直し、`test_git_runs_without_stdin_and_without_a_console_window`の中の`_run(["status"], 1.0)`を`run_git(["status"], 1.0)`に直す。末尾に足す:

```python
def test_git_never_waits_for_a_credential_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_git(["status"], 1.0)
    env = seen["env"]
    assert isinstance(env, dict) and env["GIT_TERMINAL_PROMPT"] == "0"  # 認証の入力待ちで止まらず、失敗にする
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gitstate.py -q`
Expected: FAIL(`ImportError: cannot import name 'run_git'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gitstate.py`で、関数名`_run`を`run_git`に、`_reason`を`failure_reason`に変え(定義と、`read_git_state`の既定引数`run: Runner = run_git`、`_failed(_reason(...))`の呼び出しすべて)、環境の行を次にする:

```python
    env |= {"GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"}  # ロックを取らない。出力の言語を固定。認証の入力待ちで止めない
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gitstate.py test/test_gitstate.py
git commit -m "refactor: git の呼び出しの共有部分を公開し、認証の入力待ちで止まらないようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 変更の一覧とメッセージの案(`gitops.py`)

**Files:**
- Create: `src/projectapp/gitops.py`
- Test: `test/test_gitops.py`

**Interfaces:**
- Consumes: Task 1 の`run_git`・`failure_reason`・`Runner`・`PATHSPEC`・`DEFAULT_TIMEOUT`
- Produces:
  - `class ChangeStatus(Enum)`: `MODIFIED = "変更"`・`ADDED = "追加"`・`DELETED = "削除"`
  - `@dataclass(frozen=True) class FileChange`: `name: str`・`status: ChangeStatus`
  - `@dataclass(frozen=True) class GitResult`: `ok: bool`・`message: str`・`detail: str = ""`
  - `list_changes(project_dir: Path, run: Runner = run_git, timeout: float = DEFAULT_TIMEOUT) -> list[FileChange] | GitResult`(名前順。ファイル名だけ)
  - `default_message(names: list[str]) -> str`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gitops.py`(Task 3 のテストも、あとで同じファイルに足す):

```python
import subprocess
from pathlib import Path

import pytest

from projectapp.gitops import ChangeStatus, FileChange, GitResult, default_message, list_changes, parse_changes


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def init_repo(path: Path) -> Path:
    """設定に依存しないリポジトリ(署名なし・名前はリポジトリの設定)。"""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "tester")
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "commit.gpgsign", "false")
    return path


def commit_all(path: Path, message: str = "c") -> None:
    git(path, "add", "-A")
    git(path, "commit", "-m", message)


def changes_of(path: Path) -> list[FileChange]:
    result = list_changes(path)
    assert not isinstance(result, GitResult), result
    return result


def test_modified_added_and_deleted_project_files_are_listed_by_name(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    for name in ("甲.json", "乙.json", "丙.json"):
        (repo / name).write_text("{}")
    commit_all(repo)
    (repo / "甲.json").write_text('{"changed": true}')
    (repo / "乙.json").unlink()
    (repo / "丁.json").write_text("{}")
    assert changes_of(repo) == [
        FileChange("乙.json", ChangeStatus.DELETED),
        FileChange("丁.json", ChangeStatus.ADDED),
        FileChange("甲.json", ChangeStatus.MODIFIED),
    ]  # 名前順(文字コード順)


def test_nothing_is_listed_when_nothing_changed(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.json").write_text("{}")
    commit_all(repo)
    assert changes_of(repo) == []


def test_files_other_than_project_files_are_not_listed(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    for name in ("a.json", "README.md", "config.json", "holidays.json"):
        (repo / name).write_text("1")
    commit_all(repo)
    for name in ("README.md", "config.json", "holidays.json"):
        (repo / name).write_text("2")
    (repo / "notes.txt").write_text("new")
    assert changes_of(repo) == []


def test_a_subfolder_project_dir_lists_bare_file_names_of_its_own_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    (repo / "top.json").write_text("1")
    (repo / "sub" / "a.json").write_text("1")
    commit_all(repo)
    (repo / "top.json").write_text("2")
    (repo / "sub" / "a.json").write_text("2")
    assert changes_of(repo / "sub") == [FileChange("a.json", ChangeStatus.MODIFIED)]  # `sub/`を含まない


def test_a_staged_rename_is_an_addition_and_a_deletion(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "古.json").write_text("{}")
    commit_all(repo)
    git(repo, "mv", "古.json", "新.json")
    assert changes_of(repo) == [FileChange("古.json", ChangeStatus.DELETED), FileChange("新.json", ChangeStatus.ADDED)]


def test_a_staged_addition_and_a_staged_deletion(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.json").write_text("{}")
    (repo / "b.json").write_text("{}")
    commit_all(repo)
    (repo / "c.json").write_text("{}")
    git(repo, "add", "c.json")
    git(repo, "rm", "b.json")
    assert changes_of(repo) == [FileChange("b.json", ChangeStatus.DELETED), FileChange("c.json", ChangeStatus.ADDED)]


def test_listing_outside_a_work_tree_fails_without_raising(tmp_path: Path) -> None:
    result = list_changes(tmp_path)
    assert isinstance(result, GitResult) and not result.ok and result.message


def fake_status(stdout: str, returncode: int = 0):
    def run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, returncode, stdout, "fatal: boom" if returncode else "")

    return run


def test_git_errors_become_failed_results(tmp_path: Path) -> None:
    assert list_changes(tmp_path, run=fake_status("", 128)) == GitResult(False, "fatal: boom")

    def missing(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    def slow(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("git", timeout)

    assert list_changes(tmp_path, run=missing) == GitResult(False, "git が見つかりません")
    assert list_changes(tmp_path, run=slow) == GitResult(False, "git が応答しません")


def test_an_unexpected_record_is_a_failed_result(tmp_path: Path) -> None:
    result = list_changes(tmp_path, run=fake_status("x garbage\0"))
    assert isinstance(result, GitResult) and not result.ok


def test_parse_changes_reads_paths_with_spaces() -> None:
    record = "1 .M N... 100644 100644 100644 " + "a" * 40 + " " + "b" * 40 + " sub/my file.json\0"
    assert parse_changes(record) == [FileChange("my file.json", ChangeStatus.MODIFIED)]


@pytest.mark.parametrize(
    ("names", "text"),
    [
        (["甲.json"], "プロジェクトを更新: 甲"),
        (["甲.json", "乙.json"], "プロジェクトを更新: 甲, 乙"),
        (["甲.json", "乙.json", "丙.json"], "プロジェクトを更新: 甲, 乙, 丙"),
        (["甲.json", "乙.json", "丙.json", "丁.json"], "プロジェクトを更新: 甲, 乙, 丙 ほか 1 件"),
        (["a.json", "b.json", "c.json", "d.json", "e.json"], "プロジェクトを更新: a, b, c ほか 2 件"),
        ([], "プロジェクトを更新"),
    ],
)
def test_default_message(names: list[str], text: str) -> None:
    assert default_message(names) == text
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gitops.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.gitops'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gitops.py`:

```python
"""git の書き込み操作(コミット・プッシュ)と、コミットする変更の一覧。NiceGUI に依存しない。"""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from projectapp.gitstate import DEFAULT_TIMEOUT, PATHSPEC, Runner, failure_reason, run_git


class ChangeStatus(Enum):
    MODIFIED = "変更"
    ADDED = "追加"
    DELETED = "削除"


@dataclass(frozen=True)
class FileChange:
    name: str  # ファイル名(例: 甲.json)。格納先の直下だけを見るので、ディレクトリは含まない
    status: ChangeStatus


@dataclass(frozen=True)
class GitResult:
    ok: bool
    message: str  # 成功時は短い文言、失敗時は理由
    detail: str = ""  # コミットの成功時は短いハッシュ


def _failed(message: str) -> GitResult:
    return GitResult(False, message)


def _status_of(xy: str) -> ChangeStatus:
    if "D" in xy:
        return ChangeStatus.DELETED
    if xy[0] == "A":
        return ChangeStatus.ADDED
    return ChangeStatus.MODIFIED


def parse_changes(text: str) -> list[FileChange]:
    """`status --porcelain=v2 -z`の出力を、ファイル名ごとの変更に解く。想定外の記録は`ValueError`。

    パス指定が直下の`*.json`だけなので、パス(リポジトリのルート基準)の最後の`/`以降が名前になる。
    """
    records = text.split("\0")
    found: dict[str, ChangeStatus] = {}
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        kind = record[0]
        if kind == "?":
            found[record[2:].rsplit("/", 1)[-1]] = ChangeStatus.ADDED
        elif kind == "1":
            fields = record.split(" ", 8)
            found[fields[8].rsplit("/", 1)[-1]] = _status_of(fields[1])
        elif kind == "2":  # 改名: 新しい名前の追加と、次の記録の元の名前の削除
            fields = record.split(" ", 9)
            found[fields[9].rsplit("/", 1)[-1]] = ChangeStatus.ADDED
            if index < len(records):
                found[records[index].rsplit("/", 1)[-1]] = ChangeStatus.DELETED
                index += 1
        elif kind == "u":
            fields = record.split(" ", 10)
            found[fields[10].rsplit("/", 1)[-1]] = ChangeStatus.MODIFIED
        elif kind not in "!#":
            raise ValueError(record)
    return [FileChange(name, found[name]) for name in sorted(found)]


def list_changes(
    project_dir: Path, run: Runner = run_git, timeout: float = DEFAULT_TIMEOUT
) -> list[FileChange] | GitResult:
    """格納先の、変更のあるプロジェクトファイル。読めなければ失敗の`GitResult`(例外は出さない)。"""
    args = ["-C", str(project_dir), "status", "--porcelain=v2", "-z", "--untracked-files=all", "--", *PATHSPEC]
    try:
        result = run(args, timeout)
    except FileNotFoundError:
        return _failed("git が見つかりません")
    except subprocess.TimeoutExpired:
        return _failed("git が応答しません")
    except OSError as exc:
        return _failed(str(exc))
    if result.returncode != 0:
        return _failed(failure_reason(result))
    try:
        return parse_changes(result.stdout)
    except ValueError as exc:
        return _failed(f"想定外の出力です: {exc}")


def default_message(names: list[str]) -> str:
    """コミットメッセージの案(`プロジェクトを更新: 甲, 乙`。4 件以上は`甲, 乙, 丙 ほか N 件`)。"""
    stems = [name.removesuffix(".json") for name in names]
    if not stems:
        return "プロジェクトを更新"
    if len(stems) <= 3:
        return "プロジェクトを更新: " + ", ".join(stems)
    return "プロジェクトを更新: " + ", ".join(stems[:3]) + f" ほか {len(stems) - 3} 件"
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gitops.py -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし。失敗したら、`git status --porcelain=v2 -z`の実際の出力(`| tr '\0' '|'`)を見て、解析かテストの前提を直す(計画の作成時に実機で確認済み: パスはルート基準、改名は`2 `の記録のあとに元の名前が続く、ステージ済みの追加は`A.`、削除は`D.`か`.D`)。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gitops.py test/test_gitops.py
git commit -m "feat: コミットする変更の一覧とメッセージの案を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: コミットとプッシュ(`gitops.py`)

**Files:**
- Modify: `src/projectapp/gitops.py`
- Test: `test/test_gitops.py`

**Interfaces:**
- Consumes: Task 2 の`list_changes`・`GitResult`・`FileChange`、Task 1 の`run_git`・`failure_reason`
- Produces:
  - `commit(project_dir: Path, names: list[str], message: str, run: Runner = run_git) -> GitResult`(成功時の`detail`は短いハッシュ)
  - `push(project_dir: Path, run: Runner = run_git) -> GitResult`
  - `PULL_HINT = "先にプルが必要です(プルは後続機能)"`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gitops.py`の先頭の import を`from projectapp.gitops import PULL_HINT, ChangeStatus, FileChange, GitResult, commit, default_message, list_changes, parse_changes, push`に変え、末尾に足す:

```python
def log_subjects(repo: Path) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%s"], cwd=repo, check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def files_in_head(repo: Path) -> set[str]:
    out = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    return {line.strip('"') for line in out.splitlines() if line}


def porcelain(repo: Path) -> str:
    return subprocess.run(["git", "status", "--porcelain=v1"], cwd=repo, check=True, capture_output=True, text=True).stdout


def seeded_repo(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path / "repo")
    for name in ("甲.json", "乙.json", "丙.json"):
        (repo / name).write_text("{}")
    (repo / "other.txt").write_text("1")
    commit_all(repo, "init")
    return repo


def test_only_the_chosen_files_are_committed(tmp_path: Path) -> None:
    repo = seeded_repo(tmp_path)
    (repo / "甲.json").write_text('{"a": 1}')
    (repo / "乙.json").unlink()
    (repo / "丁.json").write_text("{}")
    (repo / "丙.json").write_text('{"b": 2}')  # 選ばない
    result = commit(repo, ["甲.json", "乙.json", "丁.json"], "  選んだ分  ")
    assert result.ok and result.detail
    assert log_subjects(repo)[0] == "選んだ分"  # 前後の空白は除く
    assert files_in_head(repo) == {"甲.json", "乙.json", "丁.json"}
    assert [c.name for c in changes_of(repo)] == ["丙.json"]  # 選ばなかった変更は残る


def test_another_staged_file_is_neither_committed_nor_unstaged(tmp_path: Path) -> None:
    repo = seeded_repo(tmp_path)
    (repo / "other.txt").write_text("2")
    git(repo, "add", "other.txt")  # 利用者が別に stage したファイル
    (repo / "甲.json").write_text('{"a": 1}')
    assert commit(repo, ["甲.json"], "m").ok
    assert files_in_head(repo) == {"甲.json"}
    assert porcelain(repo) == "M  other.txt\n"  # stage のまま残る


def test_the_detail_is_the_short_hash_of_the_new_commit(tmp_path: Path) -> None:
    repo = seeded_repo(tmp_path)
    (repo / "甲.json").write_text('{"a": 1}')
    result = commit(repo, ["甲.json"], "m")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, check=True, capture_output=True, text=True)
    assert result.detail == head.stdout.strip()


def test_a_name_without_a_change_is_refused_before_git_commit_runs(tmp_path: Path) -> None:
    repo = seeded_repo(tmp_path)
    (repo / "甲.json").write_text('{"a": 1}')
    before = log_subjects(repo)
    result = commit(repo, ["甲.json", "乙.json"], "m")  # 乙は変更なし
    assert not result.ok and "乙.json" in result.message
    assert log_subjects(repo) == before
    assert [c.name for c in changes_of(repo)] == ["甲.json"]  # 何も stage されていない


@pytest.mark.parametrize(
    ("names", "message"),
    [
        ([], "m"),
        (["甲.json"], "   "),
        (["../x.json"], "m"),
        (["sub/甲.json"], "m"),
        (["a\\b.json"], "m"),
        (["甲.txt"], "m"),
        (["config.json"], "m"),
        (["holidays.json"], "m"),
        ([".json"], "m"),
        (["*.json"], "m"),
    ],
)
def test_invalid_input_is_refused_without_running_git(names: list[str], message: str, tmp_path: Path) -> None:
    def never(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError("git を呼んではいけない")

    result = commit(tmp_path, names, message, run=never)
    assert not result.ok and result.message


def test_a_special_character_name_is_taken_literally(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a[1].json").write_text("1")
    (repo / "a1.json").write_text("1")
    commit_all(repo, "init")
    (repo / "a[1].json").write_text("2")
    (repo / "a1.json").write_text("2")
    assert commit(repo, ["a[1].json"], "m").ok
    assert files_in_head(repo) == {"a[1].json"}  # `[1]`をパターンとして a1.json に当てない


def test_a_missing_identity_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = seeded_repo(tmp_path)
    git(repo, "config", "--unset", "user.name")
    git(repo, "config", "--unset", "user.email")
    git(repo, "config", "user.useConfigOnly", "true")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    (repo / "甲.json").write_text('{"a": 1}')
    result = commit(repo, ["甲.json"], "m")
    assert not result.ok and result.message


def test_commit_errors_never_raise(tmp_path: Path) -> None:
    changed = "1 .M N... 100644 100644 100644 " + "a" * 40 + " " + "b" * 40 + " 甲.json\0"

    def run_with(failure: Exception):
        def run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            if "status" in args:
                return subprocess.CompletedProcess(args, 0, changed, "")
            raise failure

        return run

    assert commit(tmp_path, ["甲.json"], "m", run=run_with(FileNotFoundError("git"))) == GitResult(False, "git が見つかりません")
    assert commit(tmp_path, ["甲.json"], "m", run=run_with(subprocess.TimeoutExpired("git", 30))) == GitResult(
        False, "git が応答しません"
    )


def with_remote(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "-b", "main")
    work = init_repo(tmp_path / "work")
    (work / "a.json").write_text("{}")
    commit_all(work)
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-u", "origin", "main")
    return work, remote


def head_of(repo: Path, ref: str = "HEAD") -> str:
    return subprocess.run(["git", "rev-parse", ref], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_push_sends_the_commit_to_the_upstream(tmp_path: Path) -> None:
    work, remote = with_remote(tmp_path)
    (work / "a.json").write_text('{"x": 1}')
    assert commit(work, ["a.json"], "m").ok
    result = push(work)
    assert result.ok and result.message == "プッシュしました"
    assert head_of(remote, "main") == head_of(work)


def test_a_rejected_push_says_the_pull_is_needed(tmp_path: Path) -> None:
    work, remote = with_remote(tmp_path)
    other = tmp_path / "other"
    git(tmp_path, "clone", str(remote), str(other))
    git(other, "config", "user.name", "o")
    git(other, "config", "user.email", "o@example.com")
    (other / "b.json").write_text("{}")
    commit_all(other, "other")
    git(other, "push", "origin", "main")
    (work / "a.json").write_text('{"x": 1}')
    assert commit(work, ["a.json"], "m").ok
    result = push(work)
    assert not result.ok
    assert "rejected" in result.message and result.message.endswith(PULL_HINT)


def test_a_push_without_an_upstream_fails_with_the_git_message(tmp_path: Path) -> None:
    repo = seeded_repo(tmp_path)
    result = push(repo)
    assert not result.ok and result.message and PULL_HINT not in result.message


def test_push_errors_never_raise(tmp_path: Path) -> None:
    def missing(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    def slow(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("git", timeout)

    assert push(tmp_path, run=missing) == GitResult(False, "git が見つかりません")
    assert push(tmp_path, run=slow) == GitResult(False, "git が応答しません")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gitops.py -q`
Expected: FAIL(`ImportError: cannot import name 'commit'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gitops.py`の import に`from projectapp.storage import INVALID_NAME_CHARS, RESERVED`を足し、定数と関数を末尾に足す:

```python
COMMIT_TIMEOUT = 30.0
PUSH_TIMEOUT = 60.0
PULL_HINT = "先にプルが必要です(プルは後続機能)"
REJECTION_MARKERS = ("rejected", "non-fast-forward", "fetch first")


def valid_name(name: str) -> bool:
    """コミットできるファイル名か(プロジェクト名の規則に合う、予約名でない`*.json`)。`git`に渡す前の検査。
    `[`などは名前に使えるので許し、`--literal-pathspecs`で、パターンとして解釈されないようにする。"""
    stem = name.removesuffix(".json")
    return (
        name.endswith(".json")
        and bool(stem)
        and not any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in name)
        and stem not in RESERVED
    )


def _call(run: Runner, args: list[str], timeout: float) -> subprocess.CompletedProcess[str] | GitResult:
    try:
        return run(args, timeout)
    except FileNotFoundError:
        return _failed("git が見つかりません")
    except subprocess.TimeoutExpired:
        return _failed("git が応答しません")
    except OSError as exc:
        return _failed(str(exc))


def commit(project_dir: Path, names: list[str], message: str, run: Runner = run_git) -> GitResult:
    """選んだプロジェクトファイルだけをコミットする。別に stage されたファイルは入れず、その stage も変えない。"""
    message = message.strip()
    if not message:
        return _failed("メッセージを入力してください")
    if not names:
        return _failed("コミットするファイルを選んでください")
    for name in names:
        if not valid_name(name):
            return _failed(f"コミットできないファイル名です: {name}")
    changes = list_changes(project_dir, run)
    if isinstance(changes, GitResult):
        return changes
    changed = {change.name for change in changes}
    for name in names:
        if name not in changed:
            return _failed(f"変更がありません: {name}")  # 空のコミットは実行しない
    where = ["--literal-pathspecs", "-C", str(project_dir)]
    steps = [
        [*where, "add", "-A", "--", *names],
        [*where, "commit", "--only", "-m", message, "--", *names],
    ]
    for args in steps:
        done = _call(run, args, COMMIT_TIMEOUT)
        if isinstance(done, GitResult):
            return done
        if done.returncode != 0:
            return _failed(failure_reason(done))
    head = _call(run, ["-C", str(project_dir), "rev-parse", "--short", "HEAD"], COMMIT_TIMEOUT)
    short = head.stdout.strip() if not isinstance(head, GitResult) and head.returncode == 0 else ""
    return GitResult(True, "コミットしました", short)


def _push_reason(result: subprocess.CompletedProcess[str]) -> str:
    """プッシュの失敗の理由(`!`・`error:`・`fatal:`の最初の行。なければ最初の行)。"""
    for line in result.stderr.splitlines():
        text = line.strip()
        if text.startswith(("fatal:", "error:", "!")):
            return text
    return failure_reason(result)


def push(project_dir: Path, run: Runner = run_git) -> GitResult:
    """上流へプッシュする。拒否(リモートが先に進んでいる)には、プルが要ることを添える。"""
    done = _call(run, ["-C", str(project_dir), "push"], PUSH_TIMEOUT)
    if isinstance(done, GitResult):
        return done
    if done.returncode == 0:
        return GitResult(True, "プッシュしました")
    reason = _push_reason(done)
    if any(marker in done.stderr for marker in REJECTION_MARKERS):
        reason = f"{reason}\n{PULL_HINT}"
    return _failed(reason)
```

(拒否のテストは`message.endswith(PULL_HINT)`なので、`\n`区切りでよい。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gitops.py -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし。`test_a_missing_identity_is_reported`が環境によって通らない(`git`が名前を自動で補う)ときは、`GIT_AUTHOR_NAME`・`GIT_COMMITTER_NAME`などの環境変数が設定されていないかを確かめ、`monkeypatch.delenv(..., raising=False)`で外す。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gitops.py test/test_gitops.py
git commit -m "feat: 選んだプロジェクトファイルのコミットとプッシュを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: コミットのダイアログ(`forms.py`)

**Files:**
- Modify: `src/projectapp/forms.py`
- Test: `test/test_commit_dialog.py`

**Interfaces:**
- Consumes: Task 2 の`FileChange`・`ChangeStatus`
- Produces: `open_commit_dialog(changes: list[FileChange], make_message: Callable[[list[str]], str], push_blocked: str | None, unsaved: bool, on_commit: Callable[[list[str], str, bool], object]) -> None`
  - `on_commit(選んだ名前, メッセージ, プッシュするか)`は、確定したあと(ダイアログを閉じてから)呼ぶ。選んだ名前は、`changes`の並び順。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_commit_dialog.py`:

```python
from pathlib import Path

from nicegui import ui
from nicegui.testing import User

from projectapp.forms import open_commit_dialog
from projectapp.gitops import ChangeStatus, FileChange, default_message

CHANGES = [
    FileChange("乙.json", ChangeStatus.DELETED),
    FileChange("丁.json", ChangeStatus.ADDED),
    FileChange("甲.json", ChangeStatus.MODIFIED),
]


def mount(calls: list[tuple], *, push_blocked: str | None = None, unsaved: bool = False) -> None:
    @ui.page("/")
    def index() -> None:
        open_commit_dialog(
            CHANGES, default_message, push_blocked, unsaved, lambda names, message, push: calls.append((names, message, push))
        )


def element(user: User, marker: str) -> ui.element:
    return next(iter(user.find(marker=marker).elements))


def checked(user: User) -> list[str]:
    return [c.name for c in CHANGES if element(user, f"commit-file-{c.name}").value]


async def test_every_file_is_checked_with_the_default_message(user: User) -> None:
    mount([])
    await user.open("/")
    assert checked(user) == ["乙.json", "丁.json", "甲.json"]
    assert element(user, "commit-message").value == "プロジェクトを更新: 乙, 丁, 甲"
    await user.should_see("削除")
    await user.should_see("追加")
    await user.should_see("変更")


async def test_unchecking_updates_the_untouched_message(user: User) -> None:
    mount([])
    await user.open("/")
    user.find(marker="commit-file-丁.json").click()
    assert checked(user) == ["乙.json", "甲.json"]
    assert element(user, "commit-message").value == "プロジェクトを更新: 乙, 甲"


async def test_an_edited_message_is_not_overwritten(user: User) -> None:
    mount([])
    await user.open("/")
    user.find(marker="commit-message").clear().type("自分の文")
    user.find(marker="commit-file-丁.json").click()
    assert element(user, "commit-message").value == "自分の文"


async def test_commit_passes_the_chosen_names_message_and_no_push(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="commit-file-乙.json").click()
    user.find(marker="commit-submit").click()
    assert calls == [(["丁.json", "甲.json"], "プロジェクトを更新: 丁, 甲", False)]
    await user.should_not_see(marker="commit-message")  # 閉じる


async def test_commit_and_push_asks_for_the_push(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="commit-submit-push").click()
    assert calls == [(["乙.json", "丁.json", "甲.json"], "プロジェクトを更新: 乙, 丁, 甲", True)]


async def test_cancel_does_nothing(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="commit-cancel").click()
    assert calls == []
    await user.should_not_see(marker="commit-message")


async def test_nothing_checked_or_an_empty_message_blocks_both_buttons(user: User) -> None:
    mount([])
    await user.open("/")
    for change in CHANGES:
        user.find(marker=f"commit-file-{change.name}").click()
    assert not element(user, "commit-submit").enabled and not element(user, "commit-submit-push").enabled
    user.find(marker="commit-file-甲.json").click()
    assert element(user, "commit-submit").enabled
    user.find(marker="commit-message").clear()
    assert not element(user, "commit-submit").enabled and not element(user, "commit-submit-push").enabled


async def test_a_blocked_push_disables_only_commit_and_push(user: User) -> None:
    mount([], push_blocked="上流がありません")
    await user.open("/")
    assert element(user, "commit-submit").enabled
    assert not element(user, "commit-submit-push").enabled


async def test_the_unsaved_warning_is_shown_only_when_needed(user: User) -> None:
    mount([], unsaved=True)
    await user.open("/")
    await user.should_see(marker="commit-unsaved")


async def test_no_unsaved_warning_by_default(user: User) -> None:
    mount([])
    await user.open("/")
    await user.should_not_see(marker="commit-unsaved")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_commit_dialog.py -q`
Expected: FAIL(`ImportError: cannot import name 'open_commit_dialog'`)

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py`の import に`from projectapp.gitops import FileChange`を足し、`open_conflict_dialog`の次に足す:

```python
def open_commit_dialog(
    changes: list[FileChange],
    make_message: Callable[[list[str]], str],
    push_blocked: str | None,
    unsaved: bool,
    on_commit: Callable[[list[str], str, bool], object],
) -> None:
    """コミットのダイアログ。変更のあるファイルを選び(既定はすべて)、メッセージ(自動の案つき)を確かめて確定する。

    `push_blocked`は、「コミットしてプッシュ」を押せない理由(押せるときは None)。`unsaved`は、
    開いているプロジェクトに未保存の編集があるとき(コミットされないことを知らせる)。
    """
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[32rem]"):
        ui.label("コミット").classes("text-h6")
        if unsaved:
            ui.label("保存されていない編集は、コミットされません").classes("text-warning").mark("commit-unsaved")
        boxes: dict[str, ui.checkbox] = {}
        for change in changes:
            with ui.row().classes("items-center no-wrap"):
                boxes[change.name] = ui.checkbox(change.name, value=True).mark(f"commit-file-{change.name}")
                ui.label(change.status.value).classes("text-caption text-grey")
        message = ui.input("メッセージ").props("outlined dense").classes("w-full").mark("commit-message")
        auto = {"text": ""}  # 最後に入れた自動の案。利用者が直していなければ、選択の変更に合わせて更新する

        def chosen() -> list[str]:
            return [name for name, box in boxes.items() if box.value]

        def sync() -> None:
            names = chosen()
            suggestion = make_message(names)
            if (message.value or "") in ("", auto["text"]):
                message.value = suggestion
            auto["text"] = suggestion
            ready = bool(names) and bool((message.value or "").strip())
            submit.set_enabled(ready)
            submit_push.set_enabled(ready and push_blocked is None)

        def submit_with(push: bool) -> None:
            names, text = chosen(), (message.value or "").strip()
            dialog.close()
            on_commit(names, text, push)

        with ui.row().classes("justify-end w-full"):
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("commit-cancel")
            submit = ui.button("コミット", on_click=lambda: submit_with(False)).mark("commit-submit")
            submit_push = ui.button("コミットしてプッシュ", on_click=lambda: submit_with(True)).mark("commit-submit-push")
            if push_blocked is not None:
                submit_push.tooltip(push_blocked)
        for box in boxes.values():
            box.on_value_change(sync)
        message.on_value_change(sync)
        sync()
    dialog.open()
```

注: `message.on_value_change(sync)`が`sync`の中の`message.value = suggestion`で再入するが、`message.value`が案と同じになれば終わる(無限再帰にならない)。ほかの`on_value_change`の使い方が違う場合(NiceGUI 3.17 は`on_value_change(callback)`)は、`box.on("update:model-value", ...)`などに合わせる。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_commit_dialog.py -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/forms.py test/test_commit_dialog.py
git commit -m "feat: コミットのダイアログを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 「Git」メニュー・ショートカット・実行(`shortcuts.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/shortcuts.py`、`src/projectapp/views.py`
- Modify(追従): `test/test_shortcuts.py`、`test/test_views.py`
- Test: `test/test_git_ops_view.py`

**Interfaces:**
- Consumes: Task 2〜4 の`list_changes`・`default_message`・`commit`・`push`・`GitResult`・`FileChange`・`open_commit_dialog`、3 番目の子の`MainView.git_state`・`request_git_refresh`
- Produces:
  - `shortcuts.label_for(action: str) -> str`(例: `label_for("git_commit")` → `"Ctrl/Cmd+K"`)
  - `MainView.read_changes: Callable[[Path], list[FileChange] | GitResult]`、`MainView.commit_files: Callable[[Path, list[str], str], GitResult]`、`MainView.push_remote: Callable[[Path], GitResult]`(テストで差し替える)
  - `MainView.git_busy: bool`、`MainView.git_reason(action: str) -> str | None`(`action`は`commit`・`push`・`push_after_commit`・`refresh`)
  - `MainView.open_git_commit()`・`MainView.start_git_push()`(同期。メニューとショートカットの入口)
  - `async MainView.run_commit(names, message, push)`・`async MainView.run_push()`

- [ ] **Step 1: ショートカットの失敗するテストを書き、追従する**

`test/test_shortcuts.py`:
- `test_main_screen_keys_resolve_to_actions`の表に足す: `("k", True, False, "git_commit")`、`("K", True, True, "git_push")`、`("k", True, True, "git_push")`。
- `test_unassigned_combinations_resolve_to_nothing`の表に足す: `("k", False, False)`。
- `test_the_key_lists_for_the_browser_guard_come_from_the_table`の`ctrl_keys()`の期待集合に`"k"`を足す。
- 末尾に足す:

```python
def test_label_for_gives_the_key_label_of_an_action() -> None:
    from projectapp.shortcuts import label_for

    assert label_for("git_commit") == "Ctrl/Cmd+K"
    assert label_for("git_push") == "Ctrl/Cmd+Shift+K"


def test_help_lists_the_git_shortcuts() -> None:
    entries = help_entries()
    assert ("Ctrl/Cmd+K", "コミット") in entries
    assert ("Ctrl/Cmd+Shift+K", "プッシュ") in entries
```

Run: `uv run pytest test/test_shortcuts.py -q`
Expected: FAIL(`git_commit`が解決されない、`label_for`がない)

- [ ] **Step 2: ショートカットを実装する**

`src/projectapp/shortcuts.py`の`SHORTCUTS`の`Shortcut("p", "preview", ...)`の次に足す:

```python
    Shortcut("k", "git_commit", "コミット", ctrl=True),
    Shortcut("k", "git_push", "プッシュ", ctrl=True, shift=True),
```

`help_entries`の次に足す:

```python
def label_for(action: str) -> str:
    """操作に割り当てたキーの表記(メニューの右端に添える)。"""
    return next(s.label() for s in SHORTCUTS if s.action == action)
```

Run: `uv run pytest test/test_shortcuts.py -q`
Expected: PASS

- [ ] **Step 3: 画面の失敗するテストを書く**

`test/test_git_ops_view.py`:

```python
import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.gitops import ChangeStatus, FileChange, GitResult
from projectapp.gitstate import GitKind, GitState
from projectapp.views import MainView

CHANGES = [FileChange("乙.json", ChangeStatus.MODIFIED), FileChange("甲.json", ChangeStatus.ADDED)]
SYNCED = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=0, behind=0)
AHEAD = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=2, behind=0)


class Fakes:
    """`git`を呼ばずに、MainView の読み取り・コミット・プッシュを差し替える。"""

    def __init__(self, state: GitState = SYNCED) -> None:
        self.state = state
        self.reads = 0
        self.commits: list[tuple[Path, list[str], str]] = []
        self.pushes: list[Path] = []
        self.changes: list[FileChange] | GitResult = CHANGES
        self.commit_result = GitResult(True, "コミットしました", "abc1234")
        self.push_result = GitResult(True, "プッシュしました")
        self.gate: threading.Event | None = None
        self.commit_error: Exception | None = None

    def read_git(self, project_dir: Path) -> GitState:
        self.reads += 1
        return self.state

    def read_changes(self, project_dir: Path) -> list[FileChange] | GitResult:
        return self.changes

    def commit_files(self, project_dir: Path, names: list[str], message: str) -> GitResult:
        self.commits.append((project_dir, names, message))
        if self.gate is not None:
            self.gate.wait(5)
        if self.commit_error is not None:
            raise self.commit_error
        return self.commit_result

    def push_remote(self, project_dir: Path) -> GitResult:
        self.pushes.append(project_dir)
        return self.push_result


def mount(base_dir: Path, views: list[MainView], fakes: Fakes) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, httpx.MockTransport(lambda request: httpx.Response(200)))
        view.read_git = fakes.read_git
        view.read_changes = fakes.read_changes
        view.commit_files = fakes.commit_files
        view.push_remote = fakes.push_remote
        views.append(view)
        view.build()


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


async def open_with(user: User, tmp_path: Path, fakes: Fakes) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount(tmp_path, views, fakes)
    await user.open("/")
    view = views[0]
    assert await wait_until(lambda: fakes.reads >= 1 and view.git_state is fakes.state)
    return view


def menu_entry(view: MainView, marker: str) -> ui.menu_item:
    return view.menu_entries[marker]


async def test_the_git_menu_sits_between_export_and_help(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, Fakes())
    order = ["menu-file", "menu-project", "menu-export", "menu-git", "menu-help"]
    ids = [user.find(marker=marker).elements.pop().id for marker in order]
    assert ids == sorted(ids)
    labels = [e.text for e in user.find(marker="menu-git").elements if isinstance(e, ui.button)]
    assert labels == ["Git"]


async def test_the_git_menu_items(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, Fakes())
    assert list(menu_entry(view, m) for m in ("git-commit", "git-push", "git-refresh"))  # 3 項目がある
    menu = user.find(marker="menu-git-items").elements.pop()
    items = [c for c in menu.default_slot.children if isinstance(c, ui.menu_item)]
    texts = [next(s.text for s in i.default_slot.children if isinstance(s, ui.item_section) and "avatar" not in s._props and "side" not in s._props) for i in items]
    assert texts == ["コミット…", "プッシュ", "状態を読み直す"]
    icons = [next(c.props["name"] for c in i.descendants() if isinstance(c, ui.icon)) for i in items]
    assert icons == ["commit", "cloud_upload", "refresh"]
    hints = [[s.text for s in i.default_slot.children if "side" in s._props] for i in items]
    assert hints == [["Ctrl/Cmd+K"], ["Ctrl/Cmd+Shift+K"], []]


@pytest.mark.parametrize(
    ("state", "commit", "push", "refresh"),
    [
        (GitState(GitKind.NOT_REPO), "git の作業ツリーではありません", "git の作業ツリーではありません", "git の作業ツリーではありません"),
        (GitState(GitKind.NO_GIT), "git の作業ツリーではありません", "git の作業ツリーではありません", "git の作業ツリーではありません"),
        (SYNCED, None, "未プッシュのコミットがありません", None),
        (AHEAD, None, None, None),
        (GitState(GitKind.OK, branch="main"), None, "上流がありません", None),
        (GitState(GitKind.OK, branch="main", upstream="origin/gone"), None, "上流が見つかりません", None),
        (GitState(GitKind.OK, error="boom"), None, "git の状態を読めていません", None),
    ],
)
async def test_git_reason(user: User, tmp_path: Path, state: GitState, commit: str | None, push: str | None, refresh: str | None) -> None:
    view = await open_with(user, tmp_path, Fakes(state))
    assert view.git_reason("commit") == commit
    assert view.git_reason("push") == push
    assert view.git_reason("refresh") == refresh
    assert menu_entry(view, "git-commit").enabled == (commit is None)
    assert menu_entry(view, "git-push").enabled == (push is None)
    assert menu_entry(view, "git-refresh").enabled == (refresh is None)
    assert view.git_menu_tips["git-push"].text == (push or "")


async def test_push_after_commit_ignores_the_ahead_count(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, Fakes(SYNCED))
    assert view.git_reason("push_after_commit") is None  # 今回のコミットで増えるので、ahead が 0 でもよい
    view.git_state = GitState(GitKind.OK, branch="main")
    assert view.git_reason("push_after_commit") == "上流がありません"


async def test_busy_blocks_commit_and_push(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, Fakes(AHEAD))
    view.git_busy = True
    assert view.git_reason("commit") == "実行中です" and view.git_reason("push") == "実行中です"
    assert view.git_reason("refresh") is None


async def test_the_commit_dialog_opens_with_the_changes_and_the_message(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    await user.should_see(marker="commit-message")
    assert next(iter(user.find(marker="commit-message").elements)).value == "プロジェクトを更新: 乙, 甲"
    await user.should_not_see(marker="commit-unsaved")


async def test_the_commit_dialog_warns_about_unsaved_edits(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, Fakes())
    view.save_section("追加")  # 未保存の編集
    view.open_git_commit()
    await user.should_see(marker="commit-unsaved")


async def test_without_changes_no_dialog_opens(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.changes = []
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    assert await wait_until(lambda: user.notify.contains("コミットする変更がありません"))
    await user.should_not_see(marker="commit-message")


async def test_a_failed_listing_is_notified_and_opens_nothing(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.changes = GitResult(False, "git が応答しません")
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    assert await wait_until(lambda: user.notify.contains("git が応答しません"))
    await user.should_not_see(marker="commit-message")


async def test_commit_runs_with_the_chosen_files_and_refreshes_the_chip(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    view = await open_with(user, tmp_path, fakes)
    reads = fakes.reads
    view.open_git_commit()
    await user.should_see(marker="commit-message")
    user.find(marker="commit-submit").click()
    assert await wait_until(lambda: user.notify.contains("コミットしました(abc1234)"))
    assert fakes.commits == [(tmp_path, ["乙.json", "甲.json"], "プロジェクトを更新: 乙, 甲")]
    assert fakes.pushes == []
    assert await wait_until(lambda: fakes.reads > reads)  # チップを読み直す
    assert not view.git_busy


async def test_commit_and_push_pushes_after_the_commit(user: User, tmp_path: Path) -> None:
    fakes = Fakes(SYNCED)
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    await user.should_see(marker="commit-message")
    user.find(marker="commit-submit-push").click()
    assert await wait_until(lambda: user.notify.contains("プッシュしました"))
    assert len(fakes.commits) == 1 and fakes.pushes == [tmp_path]


async def test_a_failed_commit_skips_the_push(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.commit_result = GitResult(False, "Author identity unknown")
    view = await open_with(user, tmp_path, fakes)
    await view.run_commit(["乙.json"], "m", True)
    assert user.notify.contains("Author identity unknown")
    assert fakes.pushes == [] and not view.git_busy


async def test_a_failed_push_after_a_commit_is_a_warning(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.push_result = GitResult(False, "! [rejected] main -> main\n先にプルが必要です(プルは後続機能)")
    view = await open_with(user, tmp_path, fakes)
    await view.run_commit(["乙.json"], "m", True)
    assert user.notify.contains("コミットしました。プッシュに失敗しました")
    assert user.notify.contains("先にプルが必要です")
    assert not view.git_busy


async def test_busy_is_released_even_if_the_commit_raises(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.commit_error = RuntimeError("boom")
    view = await open_with(user, tmp_path, fakes)
    with pytest.raises(RuntimeError):
        await view.run_commit(["乙.json"], "m", False)
    assert not view.git_busy


async def test_a_second_run_is_refused_while_busy(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.gate = threading.Event()
    view = await open_with(user, tmp_path, fakes)
    first = asyncio.create_task(view.run_commit(["乙.json"], "m", False))
    try:
        assert await wait_until(lambda: view.git_busy and len(fakes.commits) == 1)
        await view.run_commit(["甲.json"], "m2", False)  # 無視される
        view.open_git_commit()
        assert user.notify.contains("実行中です")
        assert len(fakes.commits) == 1
    finally:
        fakes.gate.set()
    await first
    assert not view.git_busy


async def test_push_runs_and_reports(user: User, tmp_path: Path) -> None:
    fakes = Fakes(AHEAD)
    view = await open_with(user, tmp_path, fakes)
    reads = fakes.reads
    view.start_git_push()
    assert await wait_until(lambda: user.notify.contains("プッシュしました"))
    assert fakes.pushes == [tmp_path]
    assert await wait_until(lambda: fakes.reads > reads)


async def test_a_failed_push_is_a_negative_notification(user: User, tmp_path: Path) -> None:
    fakes = Fakes(AHEAD)
    fakes.push_result = GitResult(False, "fatal: no network")
    view = await open_with(user, tmp_path, fakes)
    await view.run_push()
    assert user.notify.contains("fatal: no network") and not view.git_busy


async def test_an_unavailable_action_notifies_the_reason_instead_of_doing_nothing(user: User, tmp_path: Path) -> None:
    fakes = Fakes(SYNCED)
    view = await open_with(user, tmp_path, fakes)
    view.start_git_push()
    assert user.notify.contains("未プッシュのコミットがありません")
    view.git_state = GitState(GitKind.NOT_REPO)
    view.open_git_commit()
    assert user.notify.contains("git の作業ツリーではありません")
    assert fakes.pushes == [] and fakes.commits == []


async def test_the_refresh_item_reads_again(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    view = await open_with(user, tmp_path, fakes)
    reads = fakes.reads
    user.find(marker="git-refresh").click()
    assert await wait_until(lambda: fakes.reads > reads)
```

Run: `uv run pytest test/test_git_ops_view.py -q`
Expected: FAIL(`AttributeError: ... 'read_changes'` など)

- [ ] **Step 4: `views.py`を実装する**

(a) import。`from projectapp.gitstate import GitKind, GitState, describe, read_git_state, tooltip`の次に足す:

```python
from projectapp.gitops import FileChange, GitResult, default_message, list_changes
from projectapp.gitops import commit as commit_files_in_git
from projectapp.gitops import push as push_to_remote
```

`projectapp.forms`の import 群(`open_handoff_dialog`の並び)に`open_commit_dialog`を、`projectapp.shortcuts`の import に`label_for`を足す。

(b) `SHORTCUT_METHODS`に足す:

```python
        "git_commit": "open_git_commit",
        "git_push": "start_git_push",
```

(c) `MainView.__init__`の`self.git_generation = 0`の次に足す:

```python
        self.read_changes: Callable[[Path], list[FileChange] | GitResult] = list_changes  # テストで差し替える
        self.commit_files: Callable[[Path, list[str], str], GitResult] = commit_files_in_git
        self.push_remote: Callable[[Path], GitResult] = push_to_remote
        self.git_busy = False  # コミット・プッシュの実行中。二重に始めない
        self.menu_entries: dict[str, ui.menu_item] = {}  # メニューの項目(マーカー → 項目)
        self.git_menu_tips: dict[str, ui.tooltip] = {}  # 押せない理由を出すツールチップ
```

(d) `header_menu`の項目を作る行を、項目を覚える形にする:

```python
                    self.menu_entries[item.marker] = self.menu_entry(item.text, item.icon, item.handler, item.marker, item.key)
```

(e) `header`の「エクスポート」メニューの次、「ヘルプ」の前に足す:

```python
            self.header_menu(
                "Git",
                "menu-git",
                [
                    MenuItem("コミット…", "commit", self.open_git_commit, "git-commit", label_for("git_commit")),
                    MenuItem("プッシュ", "cloud_upload", self.start_git_push, "git-push", label_for("git_push")),
                    MenuItem("状態を読み直す", "refresh", self.request_git_refresh, "git-refresh"),
                ],
            )
```

`header`の最後(`self.theme_menu()`の次)に足す:

```python
            self.update_git_menu()
```

(f) `refresh_git`の`self.git_chip.refresh()`の次に足す:

```python
        self.update_git_menu()
```

(g) `request_git_refresh`の前に、メソッドを足す:

```python
    NOT_WORK_TREE = "git の作業ツリーではありません"
    GIT_MENU = (("commit", "git-commit"), ("push", "git-push"), ("refresh", "git-refresh"))

    def git_reason(self, action: str) -> str | None:
        """Git メニューの操作が、今できない理由(できるときは None)。`action`は commit・push・push_after_commit・refresh。
        `push_after_commit`は、コミットのあとにプッシュするとき(今は未プッシュが 0 でもよい)。"""
        state = self.git_state
        if state.kind is not GitKind.OK:
            return self.NOT_WORK_TREE
        if action == "refresh":
            return None
        if self.git_busy:
            return "実行中です"
        if action in ("push", "push_after_commit"):
            if state.error is not None:
                return "git の状態を読めていません"
            if state.upstream is None:
                return "上流がありません"
            if state.ahead is None:
                return "上流が見つかりません"
            if action == "push" and state.ahead == 0:
                return "未プッシュのコミットがありません"
        return None

    def update_git_menu(self) -> None:
        """Git メニューの項目を、押せるかどうかと、押せない理由のツールチップに合わせる。"""
        for action, marker in self.GIT_MENU:
            entry = self.menu_entries[marker]
            reason = self.git_reason(action)
            entry.set_enabled(reason is None)
            tip = self.git_menu_tips.get(marker)
            if tip is None:
                with entry:
                    tip = ui.tooltip("")
                self.git_menu_tips[marker] = tip
            tip.set_text(reason or "")
            tip.set_visibility(reason is not None)

    def set_git_busy(self, busy: bool) -> None:
        self.git_busy = busy
        self.update_git_menu()

    def later(self, handler: Callable[[], object]) -> None:
        """処理を画面の直下のタイマーで始める(ダイアログが閉じても残る。同期の入口から、非同期の処理を始める)。"""
        with self.client:
            ui.timer(0, handler, once=True)

    def open_git_commit(self) -> None:
        """コミットのダイアログを開く(メニューとショートカットの入口)。できないときは、理由を通知する。"""
        reason = self.git_reason("commit")
        if reason is not None:
            ui.notify(reason, type="warning")
            return
        self.later(self.show_commit_dialog)

    async def show_commit_dialog(self) -> None:
        changes = await run.io_bound(self.read_changes, self.project_dir)
        if changes is None:  # アプリの終了中
            return
        if isinstance(changes, GitResult):
            ui.notify(changes.message, type="negative")
            return
        if not changes:
            ui.notify("コミットする変更がありません")
            return
        open_commit_dialog(
            changes,
            default_message,
            self.git_reason("push_after_commit"),
            self.is_dirty(),
            lambda names, message, push: self.later(lambda: self.run_commit(names, message, push)),
        )

    async def run_commit(self, names: list[str], message: str, push: bool) -> None:
        """選んだファイルをコミットし、`push`ならプッシュする。終わったらチップを読み直す。"""
        if self.git_busy:
            return
        self.set_git_busy(True)
        try:
            result = await run.io_bound(self.commit_files, self.project_dir, names, message)
            if result is None:  # アプリの終了中
                return
            if not result.ok:
                ui.notify(result.message, type="negative")
                return
            ui.notify(f"コミットしました({result.detail})")
            if push:
                pushed = await run.io_bound(self.push_remote, self.project_dir)
                if pushed is None:
                    return
                if pushed.ok:
                    ui.notify(pushed.message)
                else:
                    ui.notify(f"コミットしました。プッシュに失敗しました: {pushed.message}", type="warning")
        finally:
            self.set_git_busy(False)
            self.request_git_refresh()

    def start_git_push(self) -> None:
        """プッシュを始める(メニューとショートカットの入口)。できないときは、理由を通知する。"""
        reason = self.git_reason("push")
        if reason is not None:
            ui.notify(reason, type="warning")
            return
        self.later(self.run_push)

    async def run_push(self) -> None:
        if self.git_busy:
            return
        self.set_git_busy(True)
        try:
            result = await run.io_bound(self.push_remote, self.project_dir)
            if result is None:
                return
            ui.notify(result.message, type="positive" if result.ok else "negative")
        finally:
            self.set_git_busy(False)
            self.request_git_refresh()
```

- [ ] **Step 5: 既存のテストを新しいメニューとキーに追従させる**

`test/test_views.py`:
- `SHORTCUT_METHODS`(テスト側のリスト)に足す: `(("k", True, False), "open_git_commit")`、`(("K", True, True), "start_git_push")`。
- `test_the_menus_start_at_the_left_of_the_header_and_the_title_is_in_the_main_area`の`order`を`["menu-file", "menu-project", "menu-export", "menu-git", "menu-help", "project-select", "open-dashboard", "open-folder", "menu-theme"]`にする。
- `test_the_menus_are_ellipse_buttons...`(`for marker in ("menu-file", "menu-project", "menu-export", "menu-help")`が 2 か所ある)の 2 つの`for`の組に`"menu-git"`を足す(`"open-dashboard"`などを含む色の検査のほうにも足す)。

- [ ] **Step 6: 通ることを確かめる**

Run: `uv run pytest test/test_git_ops_view.py test/test_shortcuts.py test/test_views.py -q`
Expected: 全 PASS。つまずきやすい所:
- メニュー項目のテキスト・アイコンを読むテスト(`test_the_git_menu_items`)は、`test_views.py`の`label_section`・`menu_items`・`menu_icons`の読み方に合わせて書き直してよい(読み取り方だけの問題)。ツールチップを項目の子に置いたことで、既存の補助関数が子の順序に依存するなら、そちらを`isinstance(child, ui.item_section)`で絞る。
- `ui.menu_item.set_enabled`が効かない場合は、`entry.props.update(disable=not enabled)`と`entry.update()`にする(`enabled`プロパティを読むテストは、`"disable" not in entry.props`に合わせる)。
- `ui.timer(0, handler, once=True)`に`lambda`で`run_commit(...)`(コルーチン)を返すハンドラを渡せない場合は、`functools.partial(self.run_commit, names, message, push)`にする。
- 押せない項目のツールチップが、実機で出るかは、Task 6 の実機確認で見る。

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし

- [ ] **Step 7: Commit**

```bash
git add src/projectapp/shortcuts.py src/projectapp/views.py test/test_shortcuts.py test/test_views.py test/test_git_ops_view.py
git commit -m "feat: Git メニューとショートカットで、コミットとプッシュを実行できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ドキュメントと記録の更新、全体の確認

**Files:**
- Modify: `CLAUDE.md`(projectapp)、`docs/development.md`、`docs/request-history.md`、`.claude/MEMORY.md`

**Interfaces:** なし(記録のみ)

- [ ] **Step 1: `CLAUDE.md`(projectapp)を更新する**

「ヘッダー」の節:
- 「メイン画面の上部に、1 行のヘッダーを置く(左から、メニュー 4 つ。」を「左から、メニュー 5 つ。」にする。
- 「`エクスポート`メニュー」の項目の次に足す: ``- `Git`メニュー: `コミット…`・`プッシュ`・`状態を読み直す`(左にアイコン、右端にキー)。作業ツリーでないときは、3 項目とも押せない。`プッシュ`は、上流がない・未プッシュが 0 のときも押せない。押せない理由は、項目のマウスオーバーに出す(ショートカットで押したときは通知する)``
- git の状態のチップの項目の最後の「コミット・プッシュ・プルは後続機能」を「プルは後続機能」にする。
- キーボードショートカットの一覧に`Ctrl/Cmd+K` コミット、`Ctrl/Cmd+Shift+K` プッシュ を足す。

「機能の詳細」(「ヘッダー」の節の前か後)に節「git のコミットとプッシュ」を足す:

```markdown
## git のコミットとプッシュ

- `Git`メニューの`コミット…`で、変更のあるプロジェクトファイル(格納先直下の`*.json`。`config`・`holidays`を除く)を、状態(変更・追加・削除)つきで一覧にし、選んでコミットする(既定はすべて選択)。メッセージは自動の案(`プロジェクトを更新: 甲, 乙`。4 件以上は`甲, 乙, 丙 ほか N 件`)が入り、編集できる。空では確定できない
- ボタンは`コミット`と`コミットしてプッシュ`。コミット済みで未プッシュのときは、`プッシュ`だけもできる。上流のないブランチでは、プッシュは押せない
- コミットは選んだファイルだけ(別に stage されたファイルは入れず、その stage も変えない)。開いているプロジェクトに未保存の編集があるときは、コミットされない(ディスクのファイルが対象)ことを、ダイアログに出す
- プッシュは`git push`(上流へ)。リモートが先に進んでいて拒否されたら、`git`のメッセージに「先にプルが必要です(プルは後続機能)」を添える。認証の入力待ちでは止まらず、失敗にする(認証・`user.name`・`user.email`は各自の環境に任せる)。コミットが成功してプッシュが失敗したときは、そう分かる通知を出す
- 実行中は、新しい実行を始めない。実行のあと、git の状態のチップを自動で読み直す
- ブランチの切り替え・プル・`fetch`・マージは含まない
```

- [ ] **Step 2: `docs/development.md`・`docs/request-history.md`・`.claude/MEMORY.md`を更新する**

`docs/development.md`: モジュールの表の`gitstate.py`の行の次に足す:

```markdown
| `gitops.py` | git の書き込み操作(`list_changes`・`commit`・`push`・`default_message`)。NiceGUI に依存しない。`gitstate.run_git`を共有し、`run`は差し替えられる。名前の検査(`valid_name`)と、`--literal-pathspecs`・`commit --only`で、選んだファイルだけをコミットする |
```

「ファイル形式の注意」の末尾に足す: ``- git のコミットとプッシュ(`gitops.py`)は、`add -A -- <名前>`のあと`commit --only -m <メッセージ> -- <名前>`で、選んだファイルだけをコミットする(別に stage したファイルは入らず、その stage も残る。実機で確認、2026-10-13)。名前は`valid_name`(プロジェクト名の規則〔`storage.INVALID_NAME_CHARS`と制御文字を含まない〕に合う、予約名でない`*.json`。`[`は許す)で検査し、さらに`--literal-pathspecs`を付けるので、`a[1].json`のような名前を別のファイルへのパターンと取り違えない。`status --porcelain=v2 -z`の出力のパスは、作業フォルダ基準でなくリポジトリのルート基準(`sub/甲.json`)なので、直下の`*.json`だけに絞るパス指定を使って、最後の`/`以降を名前にする。改名(`2 `の記録)は、新しい名前の追加と、次の記録の元の名前の削除の 2 件にする。変更のない名前を含むときは`git commit`を呼ばない(空のコミットを避ける)。プッシュは`GIT_TERMINAL_PROMPT=0`で認証の入力待ちを失敗にし、拒否(`rejected`・`non-fast-forward`・`fetch first`)には「先にプルが必要」を添える。画面は、`MainView.git_reason`(メニューの押せる・押せない、理由の通知、ダイアログの「コミットしてプッシュ」の可否)と、`git_busy`(二重実行の防止。`finally`で下ろす)で組む。ショートカットは同期の入口(`open_git_commit`・`start_git_push`)から、`later`(画面の直下のタイマー)で非同期の処理を始める。``

`docs/request-history.md`: 要望 10 の行の「3 番目は`git-status`(…)」の次に「4 番目は`git-commit-push`(実装済み・マージ待ち)」を足し、分割の表の 4 番目の状態を「実装済み(マージ待ち)」に、「未着手の整理」の 10 の次の一歩を「4 番目の子(コミットとプッシュ)をマージし、5 番目(プルとマージ)を設計する」にする。

`.claude/MEMORY.md`: 「現在の状況」の先頭に 2026-10-13 の項を足す(ブランチ`feature/git-commit-push`。設計書`2026-10-13-git-commit-push-design.md`、実装計画`2026-10-13-git-commit-push.md`。`gitops.py`と`Git`メニュー。決めたこと: 一覧から選ぶ・メッセージは案つきで編集可・コミットとプッシュは別ボタン・ブランチ切り替えは入れない・メニューは 5 つ目。実機確認は未)。

- [ ] **Step 3: 全体を確認する**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし(件数を控え、`request-history.md`と`MEMORY.md`の件数を直す)。

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/development.md docs/request-history.md .claude/MEMORY.md
git commit -m "docs: git のコミットとプッシュの仕様と開発メモを更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: 実機確認を依頼する(ユーザー)**

ネイティブで、`git clone`した格納先を開き、次を確かめてもらう: (1) ヘッダーの`Git`メニューが「エクスポート」の次にあり、作業ツリーでない格納先では 3 項目とも押せず、マウスオーバーで理由が出る。(2) プロジェクトを 2 つ変えて`コミット…`を開くと、2 件が全選択で並び、メッセージが案になっている。1 件のチェックを外すと案が変わり、自分で直したあとは変わらない。(3) `コミット`でコミットされ、チップの`●`が消える(外したファイルは`●1`で残る)。(4) 別に`git add`したファイルが、コミットに入らない。(5) `コミットしてプッシュ`で、リモートに届き、`↑`が消える。(6) 別の場所から先にプッシュしてから`プッシュ`すると、「先にプルが必要です」が出る。(7) `Ctrl/Cmd+K`・`Ctrl/Cmd+Shift+K`が効き、押せないときは理由が通知される。(8) 未保存の編集があるときの警告。(9) ダークテーマ・狭いウィンドウでヘッダーが崩れない(メニューが 1 つ増えた)。(10) 押せない項目のマウスオーバーの理由が、実際に出るか。
