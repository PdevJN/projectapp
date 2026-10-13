import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.gitstate import GitKind, GitState
from projectapp.models import Project
from projectapp.storage import save_project
from projectapp.views import HEADER_CSS, MainView


def ok(**kwargs: object) -> GitState:
    return GitState(GitKind.OK, **kwargs)  # type: ignore[arg-type]


class FakeGit:
    """`MainView.read_git`の差し替え。`state`を返し、呼ばれた格納先を覚える。"""

    def __init__(self, state: GitState) -> None:
        self.state = state
        self.calls: list[Path] = []

    def __call__(self, project_dir: Path) -> GitState:
        self.calls.append(project_dir)
        return self.state


def mount(base_dir: Path, views: list[MainView], read_git: Callable[[Path], GitState] | None = None) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, httpx.MockTransport(lambda request: httpx.Response(200)))
        if read_git is not None:
            view.read_git = read_git
        views.append(view)
        view.build()


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


def chip(user: User) -> ui.element | None:
    try:
        return next(iter(user.find(marker="git-state").elements), None)
    except AssertionError:  # `find`は、見つからないと例外を出す
        return None


def chip_text(user: User) -> str | None:
    element = chip(user)
    return element.text if isinstance(element, ui.label) else None


def tooltip_text(element: ui.element) -> str:
    """チップのツールチップ(`target`でチップを指す、兄弟の要素)の文言。"""
    siblings = element.parent_slot.children if element.parent_slot is not None else []
    return next(c for c in siblings if isinstance(c, ui.tooltip) and c.props.get("target") == f"#{element.html_id}").text


async def open_with(user: User, tmp_path: Path, read_git: Callable[[Path], GitState] | None) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount(tmp_path, views, read_git)
    await user.open("/")
    return views[0]


async def test_no_chip_when_the_project_dir_is_not_a_work_tree(user: User, tmp_path: Path) -> None:
    view = await open_with(user, tmp_path, None)  # 既定は、conftest が NOT_REPO にしている
    assert view.read_git(tmp_path).kind is GitKind.NOT_REPO
    await asyncio.sleep(0.3)
    assert chip(user) is None


async def test_no_chip_without_the_git_command(user: User, tmp_path: Path) -> None:
    fake = FakeGit(GitState(GitKind.NO_GIT))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    await asyncio.sleep(0.2)
    assert chip(user) is None


async def test_the_chip_shows_the_state_at_startup(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main", head="abc1234", upstream="origin/main", ahead=1, behind=0, dirty=2))
    view = await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: chip_text(user) == "main ↑1 ●2")
    assert fake.calls == [tmp_path]
    assert view.git_state.dirty == 2
    element = chip(user)
    assert element is not None
    assert "app-git-chip" in element.classes and "app-git-dirty" in element.classes
    assert "ブランチ: main" in tooltip_text(element)


async def test_a_clean_chip_has_no_warning_class(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, FakeGit(ok(branch="main", ahead=0, behind=0)))
    assert await wait_until(lambda: chip_text(user) == "main")
    element = chip(user)
    assert element is not None
    assert not {"app-git-dirty", "app-git-behind", "app-git-error"} & set(element.classes)


async def test_behind_takes_the_attention_color_over_dirty(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, FakeGit(ok(branch="main", ahead=0, behind=2, dirty=1)))
    assert await wait_until(lambda: chip_text(user) == "main ↓2 ●1")
    element = chip(user)
    assert element is not None
    assert "app-git-behind" in element.classes and "app-git-dirty" not in element.classes


async def test_an_error_shows_a_warning_chip_without_a_notification(user: User, tmp_path: Path) -> None:
    await open_with(user, tmp_path, FakeGit(ok(error="git が応答しません")))
    assert await wait_until(lambda: chip_text(user) == "git")
    element = chip(user)
    assert element is not None
    assert "app-git-error" in element.classes
    assert "git が応答しません" in tooltip_text(element)
    assert not user.notify.contains("git")


async def test_clicking_the_chip_reads_again(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main", dirty=1))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: chip_text(user) == "main ●1")
    fake.state = ok(branch="main", dirty=0)
    user.find(marker="git-state").click()
    assert await wait_until(lambda: chip_text(user) == "main")
    assert len(fake.calls) == 2


async def test_the_chip_disappears_when_the_state_becomes_unavailable(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main"))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: chip_text(user) == "main")
    fake.state = GitState(GitKind.NOT_REPO)
    user.find(marker="git-state").click()
    assert await wait_until(lambda: chip(user) is None)


async def test_a_successful_save_reads_again(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main", dirty=0))
    await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    fake.state = ok(branch="main", dirty=1)
    user.find(marker="save-project").click()
    user.find(marker="project-name").type("新規保存")
    user.find(marker="name-save").click()
    assert await wait_until(lambda: chip_text(user) == "main ●1")
    assert len(fake.calls) == 2


async def test_a_failed_save_does_not_read_again(user: User, tmp_path: Path) -> None:
    fake = FakeGit(ok(branch="main"))
    view = await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    (tmp_path / "既存.json").write_text("{}")  # 同名のファイルがあって、新規保存は失敗する
    assert view.save_as_new("既存") is False
    await asyncio.sleep(0.3)
    assert len(fake.calls) == 1


async def test_opening_a_project_reads_again(user: User, tmp_path: Path) -> None:
    save_project(Project("既存"), tmp_path)
    fake = FakeGit(ok(branch="main"))
    view = await open_with(user, tmp_path, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    user.find(kind=ui.select).click()
    user.find("既存").click()
    assert await wait_until(lambda: view.path == tmp_path / "既存.json")
    assert await wait_until(lambda: len(fake.calls) == 2)


async def test_changing_the_project_dir_reads_the_new_one(user: User, tmp_path: Path) -> None:
    base, other = tmp_path / "config", tmp_path / "other"
    other.mkdir()
    fake = FakeGit(ok(branch="main"))
    view = await open_with(user, base, fake)
    assert await wait_until(lambda: len(fake.calls) == 1)
    view.change_project_dir(other)
    assert await wait_until(lambda: other in fake.calls)


class GatedGit:
    """1 回目の呼び出しだけ、`gate`が開くまで待つ。あとの呼び出しは、すぐ返す。"""

    OLD = ok(branch="old")
    NEW = ok(branch="new")

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.calls = 0

    def __call__(self, project_dir: Path) -> GitState:
        self.calls += 1
        if self.calls == 1:
            self.gate.wait(5)
            return self.OLD
        return self.NEW


async def test_a_slow_old_result_does_not_overwrite_a_newer_one(user: User, tmp_path: Path) -> None:
    gated = GatedGit()
    try:
        view = await open_with(user, tmp_path, gated)
        assert await wait_until(lambda: gated.calls == 1)  # 起動時の読み込みが、待たされている
        await view.refresh_git()  # 2 回目は、すぐ返る
        assert view.git_state is GatedGit.NEW
    finally:
        gated.gate.set()
    await asyncio.sleep(0.4)  # 待たされていた 1 回目が、あとから返る
    assert view.git_state is GatedGit.NEW
    assert chip_text(user) == "new"


def test_the_header_css_styles_the_chip() -> None:
    for name in ("app-git-chip", "app-git-dirty", "app-git-behind", "app-git-error"):
        assert f".{name}" in HEADER_CSS
