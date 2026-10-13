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
