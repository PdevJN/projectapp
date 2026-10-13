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
