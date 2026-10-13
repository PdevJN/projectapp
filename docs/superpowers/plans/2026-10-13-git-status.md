# git の状態表示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 格納先が git の作業ツリーのとき、ブランチ・未コミットの変更・ahead/behind を、ヘッダーの読み取り専用のチップで見られるようにする。

**Architecture:** `gitstate.py`(NiceGUI に依存しない)が`git`コマンドを直に呼び、`status --porcelain=v2 --branch`の出力 1 回を解析して`GitState`を返す。`MainView`は、`read_git`(差し替え可能)を`run.io_bound`で待って`git_state`に持ち、ヘッダーの`git_chip`(`ui.refreshable_method`)が描く。更新は、起動時・格納先の変更後・プロジェクトを開いたとき・保存の成功後・チップのクリックだけで、世代番号で古い結果を捨てる。

**Tech Stack:** Python 3.13、NiceGUI 3.17、`git`コマンド(`subprocess`)、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-12-git-status-design.md`(2026-10-13 確定)

## Global Constraints

- `git`は`subprocess.run`の直呼び(ライブラリは足さない)。シェルを通さない。環境変数に`GIT_OPTIONAL_LOCKS=0`と`LC_ALL=C`を足す。タイムアウトの既定は 5 秒。
- 作業フォルダは、`git -C <格納先>`で渡す(`Runner`は`cwd`を持たない)。
- `fetch`しない(ahead/behind は、取得済みのリモート追跡ブランチとの比較)。コミット・プッシュ・プルは、この計画に含まない。
- 「変更あり」の数え方は、`status --porcelain=v2 --branch --untracked-files=all -- ':(glob)*.json' ':(exclude)config.json' ':(exclude)holidays.json'`の変更行(`1 `・`2 `・`u `・`? `で始まる行)の数。パス指定は固定の文字列で、ファイル名を渡さない。
- 文言: `main`・`main ↑1`・`main ↓2`・`main ↑1 ↓2`・`main ●3`(0 は省く)。detached は`(abc1234)`。`NO_GIT`・`NOT_REPO`は空文字。`error`があるときは`git`。
- チップのマーカーは`git-state`。クラスは`app-git-chip`に、`app-git-error`(読めない)・`app-git-behind`(`behind > 0`)・`app-git-dirty`(`dirty > 0`)のどれか 1 つ(この優先順)。`NO_GIT`・`NOT_REPO`は非表示。`error`のときは通知を出さない。
- 更新の呼び出し: 起動時(`build`)・`change_project_dir`のあと・`open_project`のあと・`commit`の成功後・チップのクリック。定期実行はしない。
- 画面を持たないテストのため、`MainView.read_git: Callable[[Path], GitState]`を通して読む(既定は`views.read_git_state`)。`test/conftest.py`の autouse で、既定を`NOT_REPO`に差し替え、本物の`git`を呼ばない。
- 既存のテストは変更なしで通ること。
- コード規約: すべての関数に型ヒント。コメントは多くても 3 行。日本語で書く。
- テストは`uv run pytest -n auto`、型は`uv run ty check src`。実際のホームの`~/.projectapp`は読み書きしない(`tmp_path`を使う)。
- コミットメッセージの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。

## Review Focus

- 日本語のファイル名(`甲.json`)の変更: 引用符付き・8 進エスケープの出力でも、1 件として数える。→ Task 1
- 格納先がリポジトリのサブフォルダ: 親フォルダの`*.json`を数えない。`config.json`・`holidays.json`も数えない。→ Task 1
- `git`がない・応答しない・想定外の出力・格納先が消えた・上流が消えた: 例外を外へ出さず、`NO_GIT`か`error`になる。→ Task 1
- 遅い読み込みが、あとから始めた新しい読み込みの結果を上書きしない。→ Task 3
- 読めないとき(`error`)は通知を出さず、警告色のチップだけ。作業ツリーでない格納先では、チップを出さない。既存のテストが本物の`git`を呼ばない。→ Task 3

---

## File Structure

| ファイル | 変更 |
|---|---|
| `src/projectapp/gitstate.py` | 新規。`GitKind`・`GitState`・`Runner`・`read_git_state`・`describe`・`tooltip` |
| `src/projectapp/views.py` | `read_git`・`git_state`・`git_generation`、`git_chip`、`refresh_git`・`request_git_refresh`、更新の呼び出し 4 か所、`HEADER_CSS`にチップの CSS |
| `test/test_gitstate.py` | 新規。本物の`git init`と差し替えた`run`で`read_git_state`、`describe`・`tooltip` |
| `test/test_git_view.py` | 新規。チップの表示・更新・世代番号 |
| `test/conftest.py` | autouse で`views.read_git_state`を`NOT_REPO`に差し替え |
| `CLAUDE.md`(projectapp)・`docs/development.md`・`docs/request-history.md`・`.claude/MEMORY.md` | 仕様と記録の更新 |

---

### Task 1: 状態を読む関数(`gitstate.py`)

**Files:**
- Create: `src/projectapp/gitstate.py`
- Test: `test/test_gitstate.py`

**Interfaces:**
- Produces:
  - `class GitKind(Enum)`: `NO_GIT`・`NOT_REPO`・`OK`
  - `@dataclass(frozen=True) class GitState`: `kind: GitKind`・`branch: str | None = None`・`head: str = ""`・`upstream: str | None = None`・`ahead: int | None = None`・`behind: int | None = None`・`dirty: int = 0`・`error: str | None = None`
  - `Runner = Callable[[list[str], float], subprocess.CompletedProcess[str]]`(引数は、`git`に渡す引数と、タイムアウト秒)
  - `read_git_state(project_dir: Path, run: Runner = _run, timeout: float = DEFAULT_TIMEOUT) -> GitState`(例外を外へ出さない)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gitstate.py`(Task 2 のテストも、あとで同じファイルに足す):

```python
import subprocess
from pathlib import Path

import pytest

from projectapp.gitstate import DEFAULT_TIMEOUT, GitKind, GitState, Runner, read_git_state


def git(cwd: Path, *args: str) -> None:
    """設定に依存しない`git`の呼び出し(署名なし・名前は引数で与える)。"""
    subprocess.run(
        ["git", "-c", "user.name=tester", "-c", "user.email=tester@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    return path


def commit_all(path: Path, message: str = "c") -> None:
    git(path, "add", "-A")
    git(path, "commit", "-m", message)


def with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """上流を持つ作業用リポジトリ(`origin/main`と同期済み)と、ローカルの bare リモート。"""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "-b", "main")
    work = init_repo(tmp_path / "work")
    (work / "a.json").write_text("{}")
    commit_all(work)
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-u", "origin", "main")
    return work, remote


def push_from_another_clone(tmp_path: Path, remote: Path) -> None:
    other = tmp_path / "other"
    git(tmp_path, "clone", str(remote), str(other))
    (other / "b.json").write_text("{}")
    commit_all(other, "other")
    git(other, "push", "origin", "main")


def test_outside_a_work_tree_is_not_a_repo(tmp_path: Path) -> None:
    state = read_git_state(tmp_path)
    assert state.kind is GitKind.NOT_REPO and state.error is None


def test_an_empty_repository_has_no_head_and_counts_untracked_project_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.json").write_text("{}")
    (repo / "b.json").write_text("{}")
    state = read_git_state(repo)
    assert state.kind is GitKind.OK and state.error is None
    assert (state.branch, state.head, state.dirty) == ("main", "", 2)
    assert (state.upstream, state.ahead, state.behind) == (None, None, None)


def test_a_clean_repository_reports_the_branch_and_the_short_hash(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.json").write_text("{}")
    commit_all(repo)
    full = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    state = read_git_state(repo)
    assert (state.branch, state.head, state.dirty) == ("main", full[:7], 0)


def test_modified_deleted_and_untracked_project_files_are_counted(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    for name in ("甲.json", "乙.json", "丙.json"):
        (repo / name).write_text("{}")
    commit_all(repo)
    (repo / "甲.json").write_text('{"changed": true}')
    (repo / "乙.json").unlink()
    (repo / "丁.json").write_text("{}")
    assert read_git_state(repo).dirty == 3  # 日本語の名前は、引用符付きの出力になるが、件数だけ数える


def test_files_other_than_project_files_are_not_counted(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    for name in ("a.json", "README.md", "config.json", "holidays.json"):
        (repo / name).write_text("1")
    commit_all(repo)
    for name in ("README.md", "config.json", "holidays.json"):
        (repo / name).write_text("2")
    (repo / "notes.txt").write_text("new")
    assert read_git_state(repo).dirty == 0


def test_a_project_dir_in_a_subfolder_counts_only_its_own_json_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    (repo / "top.json").write_text("1")
    (repo / "sub" / "a.json").write_text("1")
    commit_all(repo)
    (repo / "top.json").write_text("2")
    (repo / "sub" / "a.json").write_text("2")
    assert read_git_state(repo / "sub").dirty == 1


def test_a_repository_without_project_files_counts_nothing(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "README.md").write_text("1")
    commit_all(repo)
    (repo / "README.md").write_text("2")
    assert read_git_state(repo).dirty == 0


def test_a_detached_head_has_no_branch(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.json").write_text("{}")
    commit_all(repo)
    git(repo, "checkout", "--detach")
    state = read_git_state(repo)
    assert state.branch is None and len(state.head) == 7


def test_a_branch_without_an_upstream_has_no_ahead_or_behind(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.json").write_text("{}")
    commit_all(repo)
    state = read_git_state(repo)
    assert (state.upstream, state.ahead, state.behind) == (None, None, None)


def test_in_sync_with_the_upstream(tmp_path: Path) -> None:
    work, _ = with_remote(tmp_path)
    state = read_git_state(work)
    assert (state.upstream, state.ahead, state.behind) == ("origin/main", 0, 0)


def test_ahead_of_the_upstream(tmp_path: Path) -> None:
    work, _ = with_remote(tmp_path)
    (work / "c.json").write_text("{}")
    commit_all(work, "local")
    state = read_git_state(work)
    assert (state.ahead, state.behind) == (1, 0)


def test_behind_the_upstream_only_after_a_fetch(tmp_path: Path) -> None:
    work, remote = with_remote(tmp_path)
    push_from_another_clone(tmp_path, remote)
    assert read_git_state(work).behind == 0  # fetch していないので、相手のプッシュは見えない
    git(work, "fetch")
    state = read_git_state(work)
    assert (state.ahead, state.behind) == (0, 1)


def test_ahead_and_behind_together(tmp_path: Path) -> None:
    work, remote = with_remote(tmp_path)
    push_from_another_clone(tmp_path, remote)
    (work / "c.json").write_text("{}")
    commit_all(work, "local")
    git(work, "fetch")
    state = read_git_state(work)
    assert (state.ahead, state.behind) == (1, 1)


def test_a_vanished_upstream_keeps_the_name_but_has_no_counts(tmp_path: Path) -> None:
    work, _ = with_remote(tmp_path)
    git(work, "config", "branch.main.merge", "refs/heads/gone")
    state = read_git_state(work)
    assert state.kind is GitKind.OK and state.error is None
    assert (state.upstream, state.ahead, state.behind) == ("origin/gone", None, None)


def test_a_missing_project_dir_reports_an_error(tmp_path: Path) -> None:
    state = read_git_state(tmp_path / "gone")
    assert state.kind is GitKind.OK and state.error


def completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def scripted(*results: subprocess.CompletedProcess[str] | Exception) -> Runner:
    """呼ばれた順に、結果を返す(例外なら送出する)。`run`の差し替え用。"""
    queue = list(results)

    def run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return run


INSIDE = completed(stdout="true\n")


def test_no_git_command(tmp_path: Path) -> None:
    state = read_git_state(tmp_path, run=scripted(FileNotFoundError("git")))
    assert state == GitState(GitKind.NO_GIT)


def test_a_timeout_reports_an_error_in_the_first_call(tmp_path: Path) -> None:
    state = read_git_state(tmp_path, run=scripted(subprocess.TimeoutExpired("git", DEFAULT_TIMEOUT)))
    assert state.kind is GitKind.OK and state.error == "git が応答しません"


def test_a_timeout_reports_an_error_in_the_status_call(tmp_path: Path) -> None:
    state = read_git_state(tmp_path, run=scripted(INSIDE, subprocess.TimeoutExpired("git", DEFAULT_TIMEOUT)))
    assert state.error == "git が応答しません"


def test_an_unexpected_failure_reports_its_first_stderr_line(tmp_path: Path) -> None:
    state = read_git_state(tmp_path, run=scripted(completed(128, stderr="fatal: detected dubious ownership\nhint: x\n")))
    assert state.kind is GitKind.OK and state.error == "fatal: detected dubious ownership"


def test_a_failing_status_reports_an_error(tmp_path: Path) -> None:
    state = read_git_state(tmp_path, run=scripted(INSIDE, completed(1, stderr="fatal: boom")))
    assert state.error == "fatal: boom"


def test_inside_the_git_dir_is_not_a_work_tree(tmp_path: Path) -> None:
    assert read_git_state(tmp_path, run=scripted(completed(stdout="false\n"))).kind is GitKind.NOT_REPO


@pytest.mark.parametrize(
    "stdout",
    ["", "garbage\n", "# branch.oid abc\n", "# branch.head main\n# branch.ab +x -y\n"],
)
def test_an_unexpected_status_output_reports_an_error(tmp_path: Path, stdout: str) -> None:
    state = read_git_state(tmp_path, run=scripted(INSIDE, completed(stdout=stdout)))
    assert state.kind is GitKind.OK and state.error


def test_the_runner_receives_a_fixed_pathspec_and_the_project_dir(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return INSIDE if len(seen) == 1 else completed(stdout="# branch.oid abc1234def\n# branch.head main\n")

    read_git_state(tmp_path, run=run)
    assert seen[0][:2] == ["-C", str(tmp_path)]
    assert seen[1][:2] == ["-C", str(tmp_path)]
    assert seen[1][-4:] == ["--", ":(glob)*.json", ":(exclude)config.json", ":(exclude)holidays.json"]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gitstate.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.gitstate'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gitstate.py`:

```python
"""格納先の git の状態を読む(読み取り専用)。NiceGUI に依存しない。"""

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from projectapp.storage import RESERVED

DEFAULT_TIMEOUT = 5.0
NOT_REPO_MESSAGE = "not a git repository"
CHANGE_PREFIXES = ("1 ", "2 ", "u ", "? ")  # 変更行(通常・改名・衝突・未追跡)
PATHSPEC = [":(glob)*.json", *(f":(exclude){name}.json" for name in sorted(RESERVED))]
AHEAD_BEHIND = re.compile(r"\+(\d+) -(\d+)")

Runner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


class GitKind(Enum):
    NO_GIT = "git がない"
    NOT_REPO = "作業ツリーではない"
    OK = "読めた"


@dataclass(frozen=True)
class GitState:
    kind: GitKind
    branch: str | None = None  # detached は None
    head: str = ""  # 短いハッシュ。コミットがまだないときは空
    upstream: str | None = None
    ahead: int | None = None  # 上流がないとき(消えたときも)は None
    behind: int | None = None
    dirty: int = 0  # プロジェクトファイルの未コミットの変更数(未追跡も数える)
    error: str | None = None  # 読めなかった理由


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}  # 他の git のロックを取らない。出力の言語を固定
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )


def _failed(reason: str) -> GitState:
    return GitState(GitKind.OK, error=reason)


def _reason(result: subprocess.CompletedProcess[str]) -> str:
    for text in (result.stderr, result.stdout):
        for line in text.splitlines():
            if line.strip():
                return line.strip()
    return f"終了コード {result.returncode}"


def parse_status(text: str) -> GitState:
    """`status --porcelain=v2 --branch`の出力を解く。ブランチの行がなければ`ValueError`。"""
    branch: str | None = None
    head, upstream = "", None
    ahead = behind = None
    dirty = 0
    seen_head = False
    for line in text.splitlines():
        if line.startswith("# branch.oid "):
            oid = line.removeprefix("# branch.oid ")
            head = "" if oid == "(initial)" else oid[:7]
        elif line.startswith("# branch.head "):
            name = line.removeprefix("# branch.head ")
            branch = None if name == "(detached)" else name
            seen_head = True
        elif line.startswith("# branch.upstream "):
            upstream = line.removeprefix("# branch.upstream ")
        elif line.startswith("# branch.ab "):
            match = AHEAD_BEHIND.fullmatch(line.removeprefix("# branch.ab "))
            if match is None:
                raise ValueError(line)
            ahead, behind = int(match[1]), int(match[2])
        elif line.startswith(CHANGE_PREFIXES):
            dirty += 1
    if not seen_head:
        raise ValueError("ブランチの情報がありません")
    return GitState(GitKind.OK, branch, head, upstream, ahead, behind, dirty)


def read_git_state(project_dir: Path, run: Runner = _run, timeout: float = DEFAULT_TIMEOUT) -> GitState:
    """格納先の git の状態を読む。例外は外へ出さない(読めないときは`error`に理由を入れる)。"""
    where = ["-C", str(project_dir)]
    try:
        inside = run([*where, "rev-parse", "--is-inside-work-tree"], timeout)
        if inside.returncode != 0:
            if NOT_REPO_MESSAGE in inside.stderr:
                return GitState(GitKind.NOT_REPO)
            return _failed(_reason(inside))
        if inside.stdout.strip() != "true":
            return GitState(GitKind.NOT_REPO)  # .git の中など
        status = run(
            [*where, "status", "--porcelain=v2", "--branch", "--untracked-files=all", "--", *PATHSPEC], timeout
        )
    except FileNotFoundError:
        return GitState(GitKind.NO_GIT)
    except subprocess.TimeoutExpired:
        return _failed("git が応答しません")
    except OSError as exc:
        return _failed(str(exc))
    if status.returncode != 0:
        return _failed(_reason(status))
    try:
        return parse_status(status.stdout)
    except ValueError as exc:
        return _failed(f"想定外の出力です: {exc}")
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gitstate.py -v && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし。失敗したら、`git`の出力(`git status --porcelain=v2 --branch`)を手元で見て、解析かテストの前提を直す(出力の形はこの計画の作成時に実機で確認済み: 上流が消えたときは`# branch.upstream`のみで`# branch.ab`なし、空のリポジトリは`# branch.oid (initial)`、detached は`# branch.head (detached)`)。

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gitstate.py test/test_gitstate.py
git commit -m "feat: 格納先の git の状態を読む関数を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: チップの文言とマウスオーバー(`describe`・`tooltip`)

**Files:**
- Modify: `src/projectapp/gitstate.py`
- Test: `test/test_gitstate.py`

**Interfaces:**
- Consumes: Task 1 の`GitKind`・`GitState`
- Produces:
  - `describe(state: GitState) -> str`
  - `tooltip(state: GitState) -> str`(複数行。`\n`区切り)

- [ ] **Step 1: 失敗するテストを足す**

`test/test_gitstate.py`の先頭の import を`from projectapp.gitstate import DEFAULT_TIMEOUT, GitKind, GitState, Runner, describe, read_git_state, tooltip`に変え、末尾に足す:

```python
def ok(**kwargs: object) -> GitState:
    return GitState(GitKind.OK, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("state", "text"),
    [
        (ok(branch="main", head="abc1234"), "main"),
        (ok(branch="main", head="abc1234", upstream="origin/main", ahead=0, behind=0), "main"),
        (ok(branch="main", ahead=1, behind=0), "main ↑1"),
        (ok(branch="main", ahead=0, behind=2), "main ↓2"),
        (ok(branch="main", ahead=1, behind=2), "main ↑1 ↓2"),
        (ok(branch="main", dirty=3), "main ●3"),
        (ok(branch="main", ahead=1, behind=2, dirty=3), "main ↑1 ↓2 ●3"),
        (ok(branch=None, head="abc1234"), "(abc1234)"),
        (ok(branch=None, head="abc1234", dirty=1), "(abc1234) ●1"),
        (ok(branch="main", head=""), "main"),  # コミットがまだない
        (ok(branch="main", upstream="origin/gone"), "main"),  # 上流が消えた
        (ok(error="boom"), "git"),
        (GitState(GitKind.NO_GIT), ""),
        (GitState(GitKind.NOT_REPO), ""),
    ],
)
def test_describe(state: GitState, text: str) -> None:
    assert describe(state) == text


def test_tooltip_of_a_synced_branch() -> None:
    state = ok(branch="main", head="abc1234", upstream="origin/main", ahead=0, behind=0)
    assert tooltip(state).splitlines() == [
        "ブランチ: main",
        "上流: origin/main(最後に取得した時点)",
        "↑ 未プッシュ 0 件 / ↓ 未取得 0 件",
        "未コミットの変更: 0 件(プロジェクトファイルのみ)",
        "クリックで読み直す",
    ]


def test_tooltip_with_changes_and_counts() -> None:
    state = ok(branch="main", upstream="origin/main", ahead=1, behind=2, dirty=3)
    lines = tooltip(state).splitlines()
    assert "↑ 未プッシュ 1 件 / ↓ 未取得 2 件" in lines
    assert "未コミットの変更: 3 件(プロジェクトファイルのみ)" in lines


def test_tooltip_without_an_upstream_or_with_a_vanished_one() -> None:
    assert "上流: なし" in tooltip(ok(branch="main")).splitlines()
    assert "上流: origin/gone(見つかりません)" in tooltip(ok(branch="main", upstream="origin/gone")).splitlines()


def test_tooltip_of_a_detached_head() -> None:
    assert tooltip(ok(branch=None, head="abc1234")).splitlines()[0] == "ブランチ: なし(detached HEAD abc1234)"


def test_tooltip_of_an_error_shows_the_reason() -> None:
    assert tooltip(ok(error="git が応答しません")) == "git の状態を読めませんでした: git が応答しません\nクリックで読み直す"


def test_tooltip_is_empty_without_a_work_tree() -> None:
    assert tooltip(GitState(GitKind.NOT_REPO)) == "" and tooltip(GitState(GitKind.NO_GIT)) == ""
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gitstate.py -v -k "describe or tooltip"`
Expected: FAIL(`ImportError: cannot import name 'describe'`)

- [ ] **Step 3: 実装する**

`src/projectapp/gitstate.py`の末尾に足す:

```python
def describe(state: GitState) -> str:
    """チップの文言(`main ↑1 ↓2 ●3`。0 は省く)。作業ツリーでなければ空、読めなければ`git`。"""
    if state.kind is not GitKind.OK:
        return ""
    if state.error is not None:
        return "git"
    parts = [state.branch if state.branch is not None else f"({state.head})"]
    if state.ahead:
        parts.append(f"↑{state.ahead}")
    if state.behind:
        parts.append(f"↓{state.behind}")
    if state.dirty:
        parts.append(f"●{state.dirty}")
    return " ".join(parts)


def tooltip(state: GitState) -> str:
    """マウスオーバーの文言(複数行)。ahead/behind は、最後に取得した時点との比較であることを示す。"""
    if state.kind is not GitKind.OK:
        return ""
    if state.error is not None:
        return f"git の状態を読めませんでした: {state.error}\nクリックで読み直す"
    if state.branch is not None:
        lines = [f"ブランチ: {state.branch}"]
    else:
        lines = [f"ブランチ: なし(detached HEAD {state.head})"]
    if state.upstream is None:
        lines.append("上流: なし")
    elif state.ahead is None or state.behind is None:
        lines.append(f"上流: {state.upstream}(見つかりません)")
    else:
        lines.append(f"上流: {state.upstream}(最後に取得した時点)")
        lines.append(f"↑ 未プッシュ {state.ahead} 件 / ↓ 未取得 {state.behind} 件")
    lines.append(f"未コミットの変更: {state.dirty} 件(プロジェクトファイルのみ)")
    lines.append("クリックで読み直す")
    return "\n".join(lines)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gitstate.py -v && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gitstate.py test/test_gitstate.py
git commit -m "feat: git の状態のチップの文言とマウスオーバーを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ヘッダーのチップと更新(`views.py`)

**Files:**
- Modify: `src/projectapp/views.py`(import、`HEADER_CSS`、`__init__`、`open_project`、`change_project_dir`、`commit`、`build`、`header`、新しいメソッド)
- Modify: `test/conftest.py`
- Test: `test/test_git_view.py`

**Interfaces:**
- Consumes: Task 1・2 の`GitKind`・`GitState`・`describe`・`tooltip`・`read_git_state`
- Produces:
  - `MainView.read_git: Callable[[Path], GitState]`、`MainView.git_state: GitState`、`MainView.git_generation: int`
  - `MainView.git_chip()`(`ui.refreshable_method`)
  - `async MainView.refresh_git() -> None`
  - `MainView.request_git_refresh() -> None`

- [ ] **Step 1: conftest に、本物の git を呼ばない差し替えを足す**

`test/conftest.py`の import に`from projectapp.gitstate import GitKind, GitState`を足し、末尾に足す:

```python
@pytest.fixture(autouse=True)
def no_real_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """画面のテストは、本物の`git`を呼ばない(既定は、作業ツリーではない格納先)。`gitstate`の単体テストには影響しない。"""
    monkeypatch.setattr("projectapp.views.read_git_state", lambda project_dir: GitState(GitKind.NOT_REPO))
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_git_view.py`:

```python
import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.gitstate import GitKind, GitState
from projectapp.models import Project
from projectapp.storage import save_project
from projectapp.views import HEADER_CSS, MainView


def ok(**kwargs: object) -> GitState:
    return GitState(GitKind.OK, **kwargs)  # type: ignore[arg-type]


class FakeGit:
    """`MainView.read_git`の差し替え。`state`を返し、呼ばれた格納先を覚える。"""

    def __init__(self, state: GitState) -> None:
        self.state = state
        self.calls: list[Path] = []

    def __call__(self, project_dir: Path) -> GitState:
        self.calls.append(project_dir)
        return self.state


def mount(base_dir: Path, views: list[MainView], read_git: Callable[[Path], GitState] | None = None) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, httpx.MockTransport(lambda request: httpx.Response(200)))
        if read_git is not None:
            view.read_git = read_git
        views.append(view)
        view.build()


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


def chip(user: User) -> ui.element | None:
    found = user.find(marker="git-state").elements
    return next(iter(found), None)


def chip_text(user: User) -> str | None:
    element = chip(user)
    return element.text if isinstance(element, ui.label) else None


def tooltip_text(element: ui.element) -> str:
    return next(child for child in element.default_slot.children if isinstance(child, ui.tooltip)).text


async def open_with(user: User, tmp_path: Path, read_git: Callable[[Path], GitState] | None) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount(tmp_path, views, read_git)
    await user.open("/")
    return views[0]


async def test_no_chip_when_the_project_dir_is_not_a_work_tree(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, None)  # 既定は、conftest が NOT_REPO にしている
    assert view.read_git(tmp_path).kind is GitKind.NOT_REPO
    await asyncio.sleep(0.3)
    assert chip(user) is None


async def test_no_chip_without_the_git_command(user: User, tmp_path: Path) -> None:
    fake = FakeGit(GitState(GitKind.NO_GIT))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    await asyncio.sleep(0.2)
    assert chip(user) is None


async def test_the_chip_shows_the_state_at_startup(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main", head="abc1234", upstream="origin/main", ahead=1, behind=0, dirty=2))
    view = await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: chip_text(user) == "main ↑1 ●2")
    assert fake.calls == [tmp_path]
    assert view.git_state.dirty == 2
    element = chip(user)
    assert element is not None
    assert "app-git-chip" in element.classes and "app-git-dirty" in element.classes
    assert "ブランチ: main" in tooltip_text(element)


async def test_a_clean_chip_has_no_warning_class(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, FakeGit(ok(branch="main", ahead=0, behind=0)))
    assert await wait_until(lambda: chip_text(user) == "main")
    element = chip(user)
    assert element is not None
    assert not {"app-git-dirty", "app-git-behind", "app-git-error"} & set(element.classes)


async def test_behind_takes_the_attention_color_over_dirty(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, FakeGit(ok(branch="main", ahead=0, behind=2, dirty=1)))
    assert await wait_until(lambda: chip_text(user) == "main ↓2 ●1")
    element = chip(user)
    assert element is not None
    assert "app-git-behind" in element.classes and "app-git-dirty" not in element.classes


async def test_an_error_shows_a_warning_chip_without_a_notification(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, FakeGit(ok(error="git が応答しません")))
    assert await wait_until(lambda: chip_text(user) == "git")
    element = chip(user)
    assert element is not None
    assert "app-git-error" in element.classes
    assert "git が応答しません" in tooltip_text(element)
    assert not user.notify.contains("git")


async def test_clicking_the_chip_reads_again(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main", dirty=1))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: chip_text(user) == "main ●1")
    fake.state = ok(branch="main", dirty=0)
    user.find(marker="git-state").click()
    assert await wait_until(lambda: chip_text(user) == "main")
    assert len(fake.calls) == 2


async def test_the_chip_disappears_when_the_state_becomes_unavailable(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main"))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: chip_text(user) == "main")
    fake.state = GitState(GitKind.NOT_REPO)
    user.find(marker="git-state").click()
    assert await wait_until(lambda: chip(user) is None)


async def test_a_successful_save_reads_again(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main", dirty=0))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    fake.state = ok(branch="main", dirty=1)
    user.find(marker="save-project").click()
    user.find(marker="project-name").type("新規保存")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: chip_text(user) == "main ●1")
    assert len(fake.calls) == 2


async def test_a_failed_save_does_not_read_again(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main"))
    view = await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    (tmp_path / "既存.json").write_text("{}")  # 同名のファイルがあって、新規保存は失敗する
    assert view.save_as_new("既存") is False
    await asyncio.sleep(0.3)
    assert len(fake.calls) == 1


async def test_opening_a_project_reads_again(user: User, tmp_path: Path) -> None:
    save_project(Project("既存"), tmp_path)
    fake = FakeGit(ok(branch="main"))
    view = await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    user.find(kind=ui.select).click()
    user.find("既存").click()
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    assert await wait_until(lambda: len(fake.calls) == 2)


async def test_changing_the_project_dir_reads_the_new_one(user: User, tmp_path: Path) -> None:
    base, other = tmp_path / "config", tmp_path / "other"
    other.mkdir()
    fake = FakeGit(ok(branch="main"))
    view = await open_with(user, base, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    view.change_project_dir(other)
    assert await wait_until(lambda: other in fake.calls)


class GatedGit:
    """1 回目の呼び出しだけ、`gate`が開くまで待つ。あとの呼び出しは、すぐ返す。"""

    OLD = ok(branch="old")
    NEW = ok(branch="new")

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.calls = 0

    def __call__(self, project_dir: Path) -> GitState:
        self.calls += 1
        if self.calls == 1:
            self.gate.wait(5)
            return self.OLD
        return self.NEW


async def test_a_slow_old_result_does_not_overwrite_a_newer_one(user: User, tmp_path: Path) -> None:
    gated = GatedGit()
    try:
        view = await open_with(user, tmp_path, gated)
        assert await wait_until(lambda: gated.calls == 1)  # 起動時の読み込みが、待たされている
        await view.refresh_git()  # 2 回目は、すぐ返る
        assert view.git_state is GatedGit.NEW
    finally:
        gated.gate.set()
    await asyncio.sleep(0.4)  # 待たされていた 1 回目が、あとから返る
    assert view.git_state is GatedGit.NEW
    assert chip_text(user) == "new"


async def test_the_header_css_styles_the_chip() -> None:
    for name in ("app-git-chip", "app-git-dirty", "app-git-behind", "app-git-error"):
        assert f".{name}" in HEADER_CSS
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_git_view.py -v`
Expected: FAIL(`AttributeError: 'MainView' object has no attribute 'git_state'` など)。`test_the_header_css_styles_the_chip`は、`async`のままでよい(`User`は使わないが、`asyncio_mode`の設定に合わせる)。同期関数のほうが他のテストと揃うなら、`async`を外してよい。

- [ ] **Step 4: `views.py`に実装する**

(a) import。`from nicegui import ui`を`from nicegui import run, ui`に変え、`projectapp`の import 群(`projectapp.storage`などが並ぶ所)に足す:

```python
from projectapp.gitstate import GitKind, GitState, describe, read_git_state, tooltip
```

(b) `HEADER_CSS`の末尾(`.app-menu .q-item { ... }`の次の行)に足す:

```css
.app-git-chip { flex: none; font-size: 10px; line-height: 1; padding: 4px 8px; border-radius: 9999px; background: rgba(255, 255, 255, 0.18); white-space: nowrap; cursor: pointer; }
.app-git-chip:hover { background: rgba(255, 255, 255, 0.3); }
.app-git-chip.app-git-dirty { background: #ffd54f; color: #3e2723; }
.app-git-chip.app-git-behind { background: #ffb74d; color: #3e2723; }
.app-git-chip.app-git-error { background: #ef9a9a; color: #3e2723; }
.q-tooltip { white-space: pre-line; }
```

(c) `MainView.__init__`の`self.digest`の次の行に足す:

```python
        self.read_git: Callable[[Path], GitState] = read_git_state  # テストで差し替える(本物の git を呼ばない)
        self.git_state = GitState(GitKind.NOT_REPO)  # 最後に読んだ結果。読むまでは出さない
        self.git_generation = 0  # 読み込みのたびに進める。古い結果を捨てる印
```

(d) `open_project`の最後の行`self.show_project(project, path, digest)`の次に足す:

```python
        self.request_git_refresh()
```

(e) `change_project_dir`の最後の行`self.new_project()`の次に足す:

```python
        self.request_git_refresh()
```

(f) `commit`の`ui.notify("保存しました")`の次(`if after is not None:`の前)に足す:

```python
        self.request_git_refresh()
```

(g) `build`の`self.client = ui.context.client`の次の行に足す:

```python
        self.request_git_refresh()
```

(h) `header`の`ui.space()`の次の行(`self.file_select = ...`の前)に足す:

```python
            self.git_chip()
```

(i) `title`の定義(`@ui.refreshable_method def title`)の前に、メソッドを足す:

```python
    def request_git_refresh(self) -> None:
        """git の状態の読み直しを予約する(ダイアログが閉じても残るよう、タイマーは画面の直下に置く)。"""
        with self.client:
            ui.timer(0, self.refresh_git, once=True)

    async def refresh_git(self) -> None:
        """git の状態を読んでチップを更新する。画面は止めない。あとから始めた読み込みがあれば、この結果は捨てる。"""
        self.git_generation += 1
        generation = self.git_generation
        state = await run.io_bound(self.read_git, self.project_dir)
        if generation != self.git_generation:
            return
        self.git_state = state
        self.git_chip.refresh()

    @ui.refreshable_method
    def git_chip(self) -> None:
        """ヘッダーの git の状態のチップ(読み取り専用。押すと読み直す)。作業ツリーでなければ出さない。"""
        text = describe(self.git_state)
        if not text:
            return
        chip = ui.label(text).classes("app-git-chip").tooltip(tooltip(self.git_state)).mark("git-state")
        chip.on("click", self.request_git_refresh)
        if self.git_state.error is not None:
            chip.classes("app-git-error")
        elif self.git_state.behind:
            chip.classes("app-git-behind")
        elif self.git_state.dirty:
            chip.classes("app-git-dirty")
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_git_view.py test/test_gitstate.py -v && uv run ty check src`
Expected: 全 PASS。つまずきやすい所:
- `chip.on("click", ...)`が`User`の`click()`で呼ばれない場合は、`user.find(...).click()`の対象が`ui.label`であることを確認する(クリックのハンドラは要素の`_event_listeners`から呼ばれる)。
- `ui.tooltip`の`text`が取れない場合は、`tooltip_text`を`next(c for c in ... if isinstance(c, ui.tooltip))._props`などの実態に合わせて直す(テストの読み取り方だけの問題)。
- `test_a_failed_save_does_not_read_again`の`save_as_new`は UI の外から呼ぶ。通知で失敗する場合は、`save_new_as`の流れ(`save-project`→`project-name`→`name-save`)で既存の名前を入れる形に変える。

- [ ] **Step 6: 既存のテスト全体が変更なしで通ることを確かめる**

Run: `uv run pytest -n auto -q`
Expected: 全 PASS(既存のヘッダーの順序のテスト`test_the_menus_start_at_the_left_of_the_header...`も含む。チップは作業ツリーでないと出ないので、順序に影響しない)。

- [ ] **Step 7: Commit**

```bash
git add src/projectapp/views.py test/conftest.py test/test_git_view.py
git commit -m "feat: ヘッダーに git の状態のチップを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ドキュメントと記録の更新、全体の確認

**Files:**
- Modify: `CLAUDE.md`(projectapp)、`docs/development.md`、`docs/request-history.md`、`.claude/MEMORY.md`

**Interfaces:** なし(記録のみ)

- [ ] **Step 1: `CLAUDE.md`(projectapp)の「ヘッダー」の節を更新する**

「メイン画面の上部に、1 行のヘッダーを置く」の項目の「右側に、プロジェクトの切り替えのコンボボックス・…」を「右側に、git の状態のチップ・プロジェクトの切り替えのコンボボックス・…」にし、その項目の次に足す:

```markdown
- git の状態のチップ(プロジェクトの切り替えのコンボの左。読み取り専用): 格納先が git の作業ツリーのときだけ出す(`git`がない・作業ツリーでないときは出さない)。文言は`main ↑1 ↓2 ●3`(ブランチ・未プッシュ・未取得・未コミットの変更。0 は省く。detached は`(abc1234)`)。「変更」は、格納先のプロジェクトファイル(直下の`*.json`。`config`・`holidays`を除く)だけを数える。ahead/behind は、最後に`fetch`した時点のリモートとの比較で、アプリは`fetch`しない。未取得があると橙、未コミットがあると黄、読めないと赤(文言は`git`、マウスオーバーに理由。通知は出さない)。マウスオーバーに、ブランチ・上流・件数の意味を出す。更新は、起動時・格納先の変更後・プロジェクトを開いたとき・保存の成功後・チップのクリックだけ(定期実行はしない)。コミット・プッシュ・プルは後続機能
```

- [ ] **Step 2: `docs/development.md`を更新する**

モジュールの表の`filemanager.py`の行の次に足す:

```markdown
| `gitstate.py` | 格納先の git の状態を読む(読み取りだけ。`read_git_state`・`GitState`・`describe`・`tooltip`)。`git`は直呼びで、`status --porcelain=v2 --branch`の 1 回で、ブランチ・上流・ahead/behind・変更数を読む。純粋に近い関数(NiceGUI に依存しない)で、`run`は差し替えられる |
```

「ファイル形式の注意」の末尾(最後の箇条書きの次)に足す:

```markdown
- git の状態(`gitstate.py`)は、`status --porcelain=v2 --branch`を 1 回だけ呼んで解く(ブランチ・ahead/behind・変更行が 1 回で取れ、`git`を何度も起動しない)。変更の対象は、固定のパス指定(`:(glob)*.json`と、予約名の`:(exclude)`)で絞るので、ファイル名は`git`に渡さない(`*`や`:`を含む名前でも安全。削除済みのファイルも数えられる)。`fetch`しない(ネットワークに触れない・遅くならない)ので、ahead/behind は取得済みの追跡ブランチとの比較。`GIT_OPTIONAL_LOCKS=0`で他の`git`のロックを取らず、`LC_ALL=C`で「not a git repository」の判定を言語に依存させない。画面は`MainView.read_git`を`run.io_bound`で待ち、`git_generation`で、遅れて返った古い結果を捨てる。画面のテストは`read_git`を差し替え、`conftest.py`の autouse が`views.read_git_state`を`NOT_REPO`にして、本物の`git`を呼ばない。出力の形(上流が消えたときは`# branch.upstream`だけで`# branch.ab`なし、空のリポジトリは`# branch.oid (initial)`)は、実機の`git 2.54`で確かめた(2026-10-13)。
```

- [ ] **Step 3: `docs/request-history.md`と`.claude/MEMORY.md`を更新する**

`request-history.md`: 要望 10 の行の「2 番目は`external-change`(実装済み・マージ待ち。テスト 2,275 件)」を「2 番目は`external-change`(完了。PR #12)。3 番目は`git-status`(実装済み・マージ待ち)」にし、「要望 10 の分割」の表の 3 番目の状態を「実装済み(マージ待ち)」に、「未着手の整理」の 10 の「次の一歩」を「3 番目(git の状態表示)をマージし、4 番目(コミットとプッシュ)を設計する」に直す。

`.claude/MEMORY.md`: 「現在の状況」の先頭に 2026-10-13 の項を足す(PR #12 を`develop`へマージ。`feature/git-status`で 3 番目の子を実装。設計書`2026-10-12-git-status-design.md`〔2026-10-13 確定〕、実装計画`2026-10-13-git-status.md`。確定時に直したこと: パス指定を固定にした・`Runner`は`-C`・`describe`が`error`を扱う。次は、マージ後に 4 番目〔コミットとプッシュ〕の設計)。テスト件数は、Step 4 の結果を書く。

- [ ] **Step 4: 全体を確認する**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: 全 PASS、`ty`にエラーなし(件数を控える)。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/development.md docs/request-history.md .claude/MEMORY.md
git commit -m "docs: git の状態表示の仕様と開発メモを更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 実機確認を依頼する(ユーザー)**

ネイティブで起動し、次を確かめてもらう: (1) 格納先が`git clone`したフォルダのときだけ、チップが出る。(2) プロジェクトファイルを保存すると`●1`が付き、コミットすると消える(保存のあと自動で更新される)。(3) 外部で`git fetch`したあと、チップをクリックすると`↓`が付く。(4) 通常のフォルダでは、チップが出ない。ヘッダーの高さ・折り返し・ダークテーマでの色が崩れていないこと。
