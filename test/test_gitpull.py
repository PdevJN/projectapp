import subprocess
from pathlib import Path

import pytest

from projectapp.gitops import (
    GitResult,
    MergeSession,
    PullKind,
    PullPlan,
    pull_abort,
    pull_fast_forward,
    pull_finish_merge,
    pull_prepare,
    pull_start_merge,
)


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout


def configure(path: Path) -> None:
    git(path, "config", "user.name", "tester")
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "commit.gpgsign", "false")


def write(path: Path, name: str, text: str) -> None:
    (path / name).write_text(text, encoding="utf-8")


def commit_all(path: Path, message: str) -> None:
    git(path, "add", "-A")
    git(path, "commit", "-m", message)


BASE_TEXT = "1\n2\n3\n4\n5\n6\n7\n8\n9\n"


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """bare のリモートと、同じ内容から始まる 2 つのクローン(a・b)。甲.json と README.md がある。"""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    a = tmp_path / "a"
    a.mkdir()
    git(a, "init", "-b", "main")
    configure(a)
    write(a, "甲.json", BASE_TEXT)
    write(a, "README.md", "r\n")
    commit_all(a, "init")
    git(a, "remote", "add", "origin", str(remote))
    git(a, "push", "-u", "origin", "main")
    b = tmp_path / "b"
    git(tmp_path, "clone", str(remote), str(b))
    configure(b)
    return a, b


def push_change(clone: Path, name: str, text: str, message: str = "change") -> None:
    write(clone, name, text)
    commit_all(clone, message)
    git(clone, "push")


def parents(path: Path) -> list[str]:
    return git(path, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]


def test_up_to_date(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    assert pull_prepare(a) == PullPlan(PullKind.UP_TO_DATE, "origin/main")


def test_fast_forward(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("2", "二"))
    plan = pull_prepare(a)
    assert isinstance(plan, PullPlan) and plan.kind is PullKind.FAST_FORWARD
    assert pull_fast_forward(a).ok
    assert (a / "甲.json").read_text(encoding="utf-8").splitlines()[1] == "二"


def test_diverged_is_merge(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("2", "二"))
    write(a, "甲.json", BASE_TEXT.replace("8", "八"))
    commit_all(a, "mine")
    plan = pull_prepare(a)
    assert isinstance(plan, PullPlan) and plan.kind is PullKind.MERGE and plan.upstream == "origin/main"


def test_uncommitted_project_changes_refuse_the_pull(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    write(a, "甲.json", BASE_TEXT + "x\n")
    result = pull_prepare(a)
    assert isinstance(result, GitResult) and not result.ok and "甲.json" in result.message


def test_no_upstream_refuses(tmp_path: Path) -> None:
    repo = tmp_path / "solo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    configure(repo)
    write(repo, "甲.json", "x\n")
    commit_all(repo, "c")
    result = pull_prepare(repo)
    assert isinstance(result, GitResult) and result.message == "上流がありません"


def test_merge_with_a_textual_conflict_is_finished_with_the_apps_text(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("5", "B"))
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    session = pull_start_merge(a, "origin/main")
    assert isinstance(session, MergeSession)
    (file,) = session.files
    assert file.name == "甲.json" and file.base == BASE_TEXT
    assert "A" in file.ours and "B" in file.theirs
    done = pull_finish_merge(a, session, {"甲.json": BASE_TEXT.replace("5", "AB")})
    assert done.ok and done.detail
    assert len(parents(a)) == 2
    assert (a / "甲.json").read_text(encoding="utf-8") == BASE_TEXT.replace("5", "AB")
    assert git(a, "status", "--porcelain") == ""
    assert git(a, "log", "-1", "--format=%s").strip() == "マージ: origin/main"


def test_merge_without_overlap_in_project_files_needs_no_app_merge(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "README.md", "r2\n")
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    session = pull_start_merge(a, "origin/main")
    assert isinstance(session, MergeSession) and session.files == []
    assert pull_finish_merge(a, session, {}).ok
    assert len(parents(a)) == 2 and (a / "README.md").read_text() == "r2\n"


def test_conflict_outside_project_files_aborts_and_restores(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "README.md", "b\n")
    write(a, "README.md", "a\n")
    commit_all(a, "mine")
    git(a, "fetch")
    result = pull_start_merge(a, "origin/main")
    assert isinstance(result, GitResult) and not result.ok and "README.md" in result.message
    assert not (a / ".git" / "MERGE_HEAD").exists()
    assert (a / "README.md").read_text() == "a\n"


def test_file_level_conflict_aborts(pair: tuple[Path, Path]) -> None:
    a, b = pair
    git(b, "rm", "甲.json")
    commit_all(b, "delete")
    git(b, "push")
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    result = pull_start_merge(a, "origin/main")
    assert isinstance(result, GitResult) and not result.ok
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_failed_merge_commit_aborts_and_restores(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("5", "B"))
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    session = pull_start_merge(a, "origin/main")
    assert isinstance(session, MergeSession)
    hook = a / ".git" / "hooks" / "commit-msg"  # 環境の identity に左右されないよう、フックでコミットを失敗させる
    hook.write_text("#!/bin/sh\necho rejected-by-hook >&2\nexit 1\n")
    hook.chmod(0o755)
    git(a, "config", "core.hooksPath", str(hook.parent))  # 環境のグローバルな hooksPath を上書きする
    done = pull_finish_merge(a, session, {"甲.json": BASE_TEXT})
    assert not done.ok and "rejected-by-hook" in done.message
    assert not (a / ".git" / "MERGE_HEAD").exists()
    assert (a / "甲.json").read_text(encoding="utf-8") == BASE_TEXT.replace("5", "A")


def test_abort_restores(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("5", "B"))
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    assert isinstance(pull_start_merge(a, "origin/main"), MergeSession)
    assert pull_abort(a).ok
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_a_missing_git_does_not_raise(tmp_path: Path) -> None:
    def missing(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    result = pull_prepare(tmp_path, missing)
    assert isinstance(result, GitResult) and not result.ok
    assert not pull_fast_forward(tmp_path, missing).ok
    assert not pull_abort(tmp_path, missing).ok
