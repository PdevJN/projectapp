"""git の書き込み操作(コミット・プッシュ)と、コミットする変更の一覧。NiceGUI に依存しない。"""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from projectapp.gitstate import DEFAULT_TIMEOUT, PATHSPEC, Runner, failure_reason, run_git
from projectapp.storage import INVALID_NAME_CHARS, RESERVED


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


def _name_of(path: str) -> str:
    return path.rsplit("/", 1)[-1]


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
            found[_name_of(record[2:])] = ChangeStatus.ADDED
        elif kind == "1":
            fields = record.split(" ", 8)
            found[_name_of(fields[8])] = _status_of(fields[1])
        elif kind == "2":  # 改名: 新しい名前の追加と、次の記録の元の名前の削除
            fields = record.split(" ", 9)
            found[_name_of(fields[9])] = ChangeStatus.ADDED
            if index < len(records):
                found[_name_of(records[index])] = ChangeStatus.DELETED
                index += 1
        elif kind == "u":
            fields = record.split(" ", 10)
            found[_name_of(fields[10])] = ChangeStatus.MODIFIED
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
    except (ValueError, IndexError) as exc:
        return _failed(f"想定外の出力です: {exc}")


def default_message(names: list[str]) -> str:
    """コミットメッセージの案(`プロジェクトを更新: 甲, 乙`。4 件以上は`甲, 乙, 丙 ほか N 件`)。"""
    stems = [name.removesuffix(".json") for name in names]
    if not stems:
        return "プロジェクトを更新"
    if len(stems) <= 3:
        return "プロジェクトを更新: " + ", ".join(stems)
    return "プロジェクトを更新: " + ", ".join(stems[:3]) + f" ほか {len(stems) - 3} 件"


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
