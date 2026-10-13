import subprocess
from pathlib import Path

import pytest

from projectapp.gitstate import DEFAULT_TIMEOUT, GitKind, GitState, Runner, describe, read_git_state, tooltip


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
