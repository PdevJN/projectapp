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
REDIRECTING_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")  # `-C`で指した格納先とは別のリポジトリを指させる
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


def run_git(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTING_ENV}
    env |= {"GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"}  # ロックを取らない。出力の言語を固定。認証の入力待ちで止めない
    return subprocess.run(
        ["git", *args],
        stdin=subprocess.DEVNULL,  # GUI には標準入力がなく、継承すると失敗することがある
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows でコンソール窓を出さない
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


def failure_reason(result: subprocess.CompletedProcess[str]) -> str:
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


def read_git_state(project_dir: Path, run: Runner = run_git, timeout: float = DEFAULT_TIMEOUT) -> GitState:
    """格納先の git の状態を読む。例外は外へ出さない(読めないときは`error`に理由を入れる)。"""
    where = ["-C", str(project_dir)]
    try:
        inside = run([*where, "rev-parse", "--is-inside-work-tree"], timeout)
        if inside.returncode != 0:
            if NOT_REPO_MESSAGE in inside.stderr:
                return GitState(GitKind.NOT_REPO)
            return _failed(failure_reason(inside))
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
        return _failed(failure_reason(status))
    try:
        return parse_status(status.stdout)
    except ValueError as exc:
        return _failed(f"想定外の出力です: {exc}")


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
