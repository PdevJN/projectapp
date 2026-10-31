import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.gitops import ChangeStatus, FileChange, GitResult
from projectapp.gitstate import GitKind, GitState
from projectapp.views import MainView

CHANGES = [
    FileChange("乙.json", ChangeStatus.MODIFIED),
    FileChange("甲.json", ChangeStatus.ADDED),
]
SYNCED = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=0, behind=0)
AHEAD = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=2, behind=0)


class Fakes:
    """`git`を呼ばずに、MainView の読み取り・コミット・プッシュを差し替える。"""

    def __init__(self, state: GitState = SYNCED) -> None:
        self.state = state
        self.reads = 0
        self.commits: list[tuple[Path, list[str], str]] = []
        self.pushes: list[Path] = []
        self.changes: list[FileChange] | GitResult = CHANGES
        self.commit_result = GitResult(True, "コミットしました", "abc1234")
        self.push_result = GitResult(True, "プッシュしました")
        self.gate: threading.Event | None = None
        self.commit_error: Exception | None = None

    def read_git(self, project_dir: Path) -> GitState:
        self.reads += 1
        return self.state

    def read_changes(self, project_dir: Path) -> list[FileChange] | GitResult:
        return self.changes

    def commit_files(
        self, project_dir: Path, names: list[str], message: str
    ) -> GitResult:
        self.commits.append((project_dir, names, message))
        if self.gate is not None:
            self.gate.wait(5)
        if self.commit_error is not None:
            raise self.commit_error
        return self.commit_result

    def push_remote(self, project_dir: Path) -> GitResult:
        self.pushes.append(project_dir)
        return self.push_result


def mount(base_dir: Path, views: list[MainView], fakes: Fakes) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(
            base_dir, httpx.MockTransport(lambda request: httpx.Response(200))
        )
        view.read_git = fakes.read_git
        view.read_changes = fakes.read_changes
        view.commit_files = fakes.commit_files
        view.push_remote = fakes.push_remote
        views.append(view)
        view.build()


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


async def open_with(user: User, tmp_path: Path, fakes: Fakes) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount(tmp_path, views, fakes)
    await user.open("/")
    view = views[0]
    assert await wait_until(lambda: fakes.reads >= 1 and view.git_state is fakes.state)
    return view


def menu_entry(view: MainView, marker: str) -> ui.menu_item:
    return view.menu_entries[marker]


def dialog_is_open(user: User) -> bool:
    try:
        return any(d.value for d in user.find(kind=ui.dialog).elements)
    except AssertionError:
        return False


async def test_the_git_menu_sits_between_export_and_help(
    user: User, tmp_path: Path
) -> None:
    await open_with(user, tmp_path, Fakes())
    order = ["menu-file", "menu-project", "menu-export", "menu-git", "menu-help"]
    ids = [user.find(marker=marker).elements.pop().id for marker in order]
    assert ids == sorted(ids)


async def test_the_git_menu_items(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, Fakes())
    entries = [menu_entry(view, m) for m in ("git-commit", "git-push", "git-refresh")]
    texts = [
        next(
            s.text
            for s in e.default_slot.children
            if isinstance(s, ui.item_section)
            and "avatar" not in s._props
            and "side" not in s._props
        )
        for e in entries
    ]
    assert texts == ["コミット…", "プッシュ", "状態を読み直す"]
    icons = [
        next(c._props["name"] for c in e.descendants() if isinstance(c, ui.icon))
        for e in entries
    ]
    assert icons == ["commit", "cloud_upload", "refresh"]
    hints = [
        [
            s.text
            for s in e.default_slot.children
            if isinstance(s, ui.item_section) and "side" in s._props
        ]
        for e in entries
    ]
    assert hints == [["Ctrl/Cmd+K"], ["Ctrl/Cmd+Shift+K"], []]


@pytest.mark.parametrize(
    ("state", "commit", "push", "refresh"),
    [
        (
            GitState(GitKind.NOT_REPO),
            "git の作業ツリーではありません",
            "git の作業ツリーではありません",
            None,
        ),  # 読み直しは、いつでもできる
        (
            GitState(GitKind.NO_GIT),
            "git の作業ツリーではありません",
            "git の作業ツリーではありません",
            None,
        ),
        (SYNCED, None, "未プッシュのコミットがありません", None),
        (AHEAD, None, None, None),
        (GitState(GitKind.OK, branch="main"), None, "上流がありません", None),
        (
            GitState(GitKind.OK, branch="main", upstream="origin/gone"),
            None,
            "上流が見つかりません",
            None,
        ),
        (GitState(GitKind.OK, error="boom"), None, "git の状態を読めていません", None),
    ],
)
async def test_git_reason(
    user: User,
    tmp_path: Path,
    state: GitState,
    commit: str | None,
    push: str | None,
    refresh: str | None,
) -> None:
    view = await open_with(user, tmp_path, Fakes(state))
    assert view.git_reason("commit") == commit
    assert view.git_reason("push") == push
    assert view.git_reason("refresh") == refresh
    assert menu_entry(view, "git-commit").enabled == (commit is None)
    assert menu_entry(view, "git-push").enabled == (push is None)
    assert menu_entry(view, "git-refresh").enabled == (refresh is None)
    assert view.git_menu_tips["git-push"].text == (push or "")


async def test_push_after_commit_ignores_the_ahead_count(
    user: User, tmp_path: Path
) -> None:
    view = await open_with(user, tmp_path, Fakes(SYNCED))
    assert (
        view.git_reason("push_after_commit") is None
    )  # 今回のコミットで増えるので、ahead が 0 でもよい
    view.git_state = GitState(GitKind.OK, branch="main")
    assert view.git_reason("push_after_commit") == "上流がありません"


async def test_busy_blocks_commit_and_push(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, Fakes(AHEAD))
    view.git_busy = True
    assert (
        view.git_reason("commit") == "実行中です"
        and view.git_reason("push") == "実行中です"
    )
    assert view.git_reason("refresh") is None


async def test_the_commit_dialog_opens_with_the_changes_and_the_message(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes()
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    await user.should_see(marker="commit-message")
    assert (
        next(iter(user.find(marker="commit-message").elements)).value
        == "プロジェクトを更新: 乙, 甲"
    )
    await user.should_not_see(marker="commit-unsaved")


async def test_the_commit_dialog_warns_about_unsaved_edits(
    user: User, tmp_path: Path
) -> None:
    view = await open_with(user, tmp_path, Fakes())
    view.save_section("追加")  # 未保存の編集
    view.open_git_commit()
    await user.should_see(marker="commit-unsaved")


async def test_without_changes_no_dialog_opens(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.changes = []
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    assert await wait_until(
        lambda: user.notify.contains("コミットする変更がありません")
    )
    assert not dialog_is_open(user)


async def test_a_failed_listing_is_notified_and_opens_nothing(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes()
    fakes.changes = GitResult(False, "git が応答しません")
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    assert await wait_until(lambda: user.notify.contains("git が応答しません"))
    assert not dialog_is_open(user)


async def test_commit_runs_with_the_chosen_files_and_refreshes_the_chip(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes()
    view = await open_with(user, tmp_path, fakes)
    reads = fakes.reads
    view.open_git_commit()
    await user.should_see(marker="commit-message")
    user.find(marker="commit-submit").click()
    assert await wait_until(lambda: user.notify.contains("コミットしました(abc1234)"))
    assert fakes.commits == [
        (tmp_path, ["乙.json", "甲.json"], "プロジェクトを更新: 乙, 甲")
    ]
    assert fakes.pushes == []
    assert await wait_until(lambda: fakes.reads > reads)  # チップを読み直す
    assert not view.git_busy


async def test_commit_and_push_pushes_after_the_commit(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes(SYNCED)
    view = await open_with(user, tmp_path, fakes)
    view.open_git_commit()
    await user.should_see(marker="commit-message")
    user.find(marker="commit-submit-push").click()
    assert await wait_until(lambda: user.notify.contains("プッシュしました"))
    assert len(fakes.commits) == 1 and fakes.pushes == [tmp_path]


async def test_a_failed_commit_skips_the_push(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.commit_result = GitResult(False, "Author identity unknown")
    view = await open_with(user, tmp_path, fakes)
    await view.run_commit(["乙.json"], "m", True)
    assert user.notify.contains("Author identity unknown")
    assert fakes.pushes == [] and not view.git_busy


async def test_a_failed_push_after_a_commit_is_a_warning(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes()
    fakes.push_result = GitResult(
        False, "! [rejected] main -> main\n先にプルが必要です"
    )
    view = await open_with(user, tmp_path, fakes)
    await view.run_commit(["乙.json"], "m", True)
    assert user.notify.contains("コミットしました。プッシュに失敗しました")
    assert user.notify.contains("先にプルが必要です")
    assert not view.git_busy


async def test_busy_is_released_even_if_the_commit_raises(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes()
    fakes.commit_error = RuntimeError("boom")
    view = await open_with(user, tmp_path, fakes)
    with pytest.raises(RuntimeError):
        await view.run_commit(["乙.json"], "m", False)
    assert not view.git_busy


async def test_a_second_run_is_refused_while_busy(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.gate = threading.Event()
    view = await open_with(user, tmp_path, fakes)
    first = asyncio.create_task(view.run_commit(["乙.json"], "m", False))
    try:
        assert await wait_until(lambda: view.git_busy and len(fakes.commits) == 1)
        await view.run_commit(["甲.json"], "m2", False)  # 無視される
        view.open_git_commit()
        assert user.notify.contains("実行中です")
        assert len(fakes.commits) == 1
    finally:
        fakes.gate.set()
    await first
    assert not view.git_busy


async def test_push_runs_and_reports(user: User, tmp_path: Path) -> None:
    fakes = Fakes(AHEAD)
    view = await open_with(user, tmp_path, fakes)
    reads = fakes.reads
    view.start_git_push()
    assert await wait_until(lambda: user.notify.contains("プッシュしました"))
    assert fakes.pushes == [tmp_path]
    assert await wait_until(lambda: fakes.reads > reads)


async def test_a_failed_push_is_a_negative_notification(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes(AHEAD)
    fakes.push_result = GitResult(False, "fatal: no network")
    view = await open_with(user, tmp_path, fakes)
    await view.run_push()
    assert user.notify.contains("fatal: no network") and not view.git_busy


async def test_an_unavailable_action_notifies_the_reason_instead_of_doing_nothing(
    user: User, tmp_path: Path
) -> None:
    fakes = Fakes(SYNCED)
    view = await open_with(user, tmp_path, fakes)
    view.start_git_push()
    assert user.notify.contains("未プッシュのコミットがありません")
    view.git_state = GitState(GitKind.NOT_REPO)
    view.open_git_commit()
    assert user.notify.contains("git の作業ツリーではありません")
    assert fakes.pushes == [] and fakes.commits == []


async def test_the_refresh_item_reads_again(user: User, tmp_path: Path) -> None:
    fakes = Fakes()
    await open_with(user, tmp_path, fakes)
    reads = fakes.reads
    user.find(marker="git-refresh").click()
    assert await wait_until(lambda: fakes.reads > reads)
