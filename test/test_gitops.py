import subprocess
from pathlib import Path

import pytest

from projectapp.gitops import (
    PULL_HINT,
    ChangeStatus,
    FileChange,
    GitResult,
    commit,
    default_message,
    list_changes,
    parse_changes,
    push,
)


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
        FileChange("丁.json", ChangeStatus.ADDED),
        FileChange("乙.json", ChangeStatus.DELETED),
        FileChange("甲.json", ChangeStatus.MODIFIED),
    ]  # 名前順(文字コード順。丁 U+4E01 < 乙 U+4E59 < 甲 U+7532)


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


def log_subjects(repo: Path) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%s"], cwd=repo, check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def files_in_head(repo: Path) -> set[str]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "show", "--no-renames", "--name-only", "--format=", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {line for line in out.splitlines() if line}


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
    assert [c.name for c in changes_of(repo)] == ["甲.json"]


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
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)
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
