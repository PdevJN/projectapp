"""git の書き込み操作(コミット・プッシュ)と、コミットする変更の一覧。NiceGUI に依存しない。"""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from projectapp.gitstate import (
    DEFAULT_TIMEOUT,
    PATHSPEC,
    Runner,
    failure_reason,
    run_git,
)
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
    args = [
        "-C",
        str(project_dir),
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--",
        *PATHSPEC,
    ]
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
PULL_HINT = "先にプルが必要です"
REJECTION_MARKERS = ("rejected", "non-fast-forward", "fetch first")


def valid_name(name: str) -> bool:
    """コミットできるファイル名か(プロジェクト名の規則に合う、予約名でない`*.json`)。`git`に渡す前の検査。
    `[`などは名前に使えるので許し、`--literal-pathspecs`で、パターンとして解釈されないようにする。"""
    stem = name.removesuffix(".json")
    return (
        name.endswith(".json")
        and bool(stem)
        and not any(
            c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in name
        )
        and stem not in RESERVED
    )


def _call(
    run: Runner, args: list[str], timeout: float
) -> subprocess.CompletedProcess[str] | GitResult:
    try:
        return run(args, timeout)
    except FileNotFoundError:
        return _failed("git が見つかりません")
    except subprocess.TimeoutExpired:
        return _failed("git が応答しません")
    except OSError as exc:
        return _failed(str(exc))


def commit(
    project_dir: Path, names: list[str], message: str, run: Runner = run_git
) -> GitResult:
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
    head = _call(
        run, ["-C", str(project_dir), "rev-parse", "--short", "HEAD"], COMMIT_TIMEOUT
    )
    short = (
        head.stdout.strip()
        if not isinstance(head, GitResult) and head.returncode == 0
        else ""
    )
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


class PullKind(Enum):
    UP_TO_DATE = "最新"
    FAST_FORWARD = "早送り"
    MERGE = "マージ"


@dataclass(frozen=True)
class PullPlan:
    kind: PullKind
    upstream: str  # 例: origin/main


@dataclass(frozen=True)
class MergeFile:
    """両側が変えたプロジェクトファイル 1 つの、共通祖先・自分・相手の本文。"""

    name: str
    base: str
    ours: str
    theirs: str


@dataclass(frozen=True)
class MergeSession:
    upstream: str
    files: list[MergeFile]


def _git(
    run: Runner, project_dir: Path, args: list[str], timeout: float = COMMIT_TIMEOUT
):
    return _call(run, ["-C", str(project_dir), *args], timeout)


def _out(done: subprocess.CompletedProcess[str] | GitResult) -> str | GitResult:
    """成功した出力の本文(前後の空白を除く)。失敗は`GitResult`。"""
    if isinstance(done, GitResult):
        return done
    if done.returncode != 0:
        return _failed(failure_reason(done))
    return done.stdout.strip()


def pull_prepare(project_dir: Path, run: Runner = run_git) -> PullPlan | GitResult:
    """プルの前提を確かめて`fetch`し、何をするか(最新・早送り・マージ)を決める。"""
    upstream = _git(
        run, project_dir, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )
    if isinstance(upstream, GitResult):
        return upstream
    if upstream.returncode != 0:
        return _failed("上流がありません")
    changes = list_changes(project_dir, run)
    if isinstance(changes, GitResult):
        return changes
    if changes:
        return _failed(
            "先に保存・コミットしてください: "
            + ", ".join(change.name for change in changes)
        )
    fetched = _out(_git(run, project_dir, ["fetch"], PUSH_TIMEOUT))
    if isinstance(fetched, GitResult):
        return fetched
    counts = _out(
        _git(run, project_dir, ["rev-list", "--left-right", "--count", "HEAD...@{u}"])
    )
    if isinstance(counts, GitResult):
        return counts
    try:
        ahead, behind = (int(part) for part in counts.split())
    except ValueError:
        return _failed(f"想定外の出力です: {counts}")
    name = upstream.stdout.strip()
    if behind == 0:
        return PullPlan(PullKind.UP_TO_DATE, name)
    return PullPlan(PullKind.FAST_FORWARD if ahead == 0 else PullKind.MERGE, name)


def pull_fast_forward(project_dir: Path, run: Runner = run_git) -> GitResult:
    out = _out(_git(run, project_dir, ["merge", "--ff-only", "@{u}"]))
    return out if isinstance(out, GitResult) else GitResult(True, "取り込みました")


def pull_abort(project_dir: Path, run: Runner = run_git) -> GitResult:
    out = _out(_git(run, project_dir, ["merge", "--abort"]))
    return (
        out if isinstance(out, GitResult) else GitResult(True, "取り込みを中止しました")
    )


def _abort_with(
    project_dir: Path, run: Runner, message: str, restore: list[str] | None = None
) -> GitResult:
    """マージを中止して元に戻す。`restore`は、アプリが書き換えたファイル(index の内容に戻してから中止する。
    書き換えたまま未 stage だと、`merge --abort`が「not uptodate」で通らない)。戻せなかったときは、そう伝える。"""
    if restore:
        _git(
            run, project_dir, ["--literal-pathspecs", "checkout", "--", *restore]
        )  # 未統合のパスは戻せないが、中止が戻す
    aborted = pull_abort(project_dir, run)
    if not aborted.ok:
        message += f"\n中止できませんでした(`git merge --abort`を手で実行してください): {aborted.message}"
    return _failed(message)


def _paths(run: Runner, project_dir: Path, args: list[str]) -> list[str] | GitResult:
    out = _git(run, project_dir, args)
    if isinstance(out, GitResult):
        return out
    if out.returncode != 0:
        return _failed(failure_reason(out))
    return [path for path in out.stdout.split("\0") if path]


def _show(run: Runner, project_dir: Path, rev: str, name: str) -> str | None:
    done = _git(run, project_dir, ["show", f"{rev}:./{name}"])
    if isinstance(done, GitResult) or done.returncode != 0:
        return None
    return done.stdout


def pull_start_merge(
    project_dir: Path, upstream: str, run: Runner = run_git
) -> MergeSession | GitResult:
    """`git merge --no-commit --no-ff`を始め、両側が変えたプロジェクトファイルの 3 版を取り出す。
    アプリが統合できないとき(プロジェクトファイル以外の衝突・ファイル単位の衝突)は、中止して元に戻す。"""
    merged = _git(run, project_dir, ["merge", "--no-commit", "--no-ff", "@{u}"])
    if isinstance(merged, GitResult):
        return merged
    unmerged = _paths(
        run, project_dir, ["diff", "--name-only", "--diff-filter=U", "-z"]
    )
    if isinstance(unmerged, GitResult):
        return _abort_with(project_dir, run, unmerged.message)
    if merged.returncode != 0 and not unmerged:
        return _abort_with(
            project_dir, run, failure_reason(merged)
        )  # 衝突ではない失敗(未コミットの変更など)
    prefix = _out(_git(run, project_dir, ["rev-parse", "--show-prefix"]))
    base = _out(_git(run, project_dir, ["merge-base", "HEAD", "@{u}"]))
    for item in (prefix, base):
        if isinstance(item, GitResult):
            return _abort_with(project_dir, run, item.message)
    assert isinstance(prefix, str) and isinstance(base, str)
    tail = ["--name-only", "--relative", "--no-renames", "-z"]
    ours_changed = _paths(
        run, project_dir, ["diff", *tail, base, "HEAD", "--", *PATHSPEC]
    )
    theirs_changed = _paths(
        run, project_dir, ["diff", *tail, base, "@{u}", "--", *PATHSPEC]
    )
    for item in (ours_changed, theirs_changed):
        if isinstance(item, GitResult):
            return _abort_with(project_dir, run, item.message)
    assert isinstance(ours_changed, list) and isinstance(theirs_changed, list)
    both = sorted(
        name for name in set(ours_changed) & set(theirs_changed) if valid_name(name)
    )
    stray = sorted(set(unmerged) - {prefix + name for name in both})
    if stray:
        return _abort_with(
            project_dir,
            run,
            "プロジェクトファイル以外に衝突があります: " + ", ".join(stray),
        )
    files = []
    for name in both:
        base_text, ours_text, theirs_text = (
            _show(run, project_dir, rev, name) for rev in (base, "HEAD", "@{u}")
        )
        if base_text is None or ours_text is None or theirs_text is None:
            return _abort_with(
                project_dir,
                run,
                f"ファイル単位の衝突(追加・削除)のため、自動で取り込めません: {name}",
            )
        files.append(MergeFile(name, base_text, ours_text, theirs_text))
    return MergeSession(upstream, files)


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pull-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def pull_finish_merge(
    project_dir: Path,
    session: MergeSession,
    merged: dict[str, str],
    run: Runner = run_git,
) -> GitResult:
    """統合したファイルを書いて stage し、マージコミットを作る。どこで失敗しても、中止して元に戻す。"""
    names = sorted(merged)
    for name in names:
        if not valid_name(name):
            return _abort_with(project_dir, run, f"書けないファイル名です: {name}")
    written: list[
        str
    ] = []  # 実際に書き換えたもの(戻すのはこれだけ。書けなかった名前を含めると、`checkout`が全体で失敗する)
    try:
        for name in names:
            _write_atomic(project_dir / name, merged[name])
            written.append(name)
    except OSError as exc:
        return _abort_with(project_dir, run, str(exc), written)
    steps = []
    if names:
        steps.append(["--literal-pathspecs", "add", "--", *names])
    steps.append(["commit", "-m", f"マージ: {session.upstream}"])
    for args in steps:
        out = _out(_git(run, project_dir, args))
        if isinstance(out, GitResult):
            return _abort_with(project_dir, run, out.message, names)
    head = _out(_git(run, project_dir, ["rev-parse", "--short", "HEAD"]))
    return GitResult(True, "取り込みました", head if isinstance(head, str) else "")


class PullOps:
    """プルの各段階(`MainView`が持ち、テストで差し替える)。"""

    def prepare(self, project_dir: Path) -> PullPlan | GitResult:
        return pull_prepare(project_dir)

    def fast_forward(self, project_dir: Path) -> GitResult:
        return pull_fast_forward(project_dir)

    def start_merge(self, project_dir: Path, upstream: str) -> MergeSession | GitResult:
        return pull_start_merge(project_dir, upstream)

    def finish_merge(
        self, project_dir: Path, session: MergeSession, merged: dict[str, str]
    ) -> GitResult:
        return pull_finish_merge(project_dir, session, merged)

    def abort(self, project_dir: Path) -> GitResult:
        return pull_abort(project_dir)
