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
