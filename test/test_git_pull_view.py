from collections.abc import Callable
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User
from test_git_ops_view import Fakes, menu_entry, wait_until

from projectapp.calendar import save_cache
from projectapp.gitops import GitResult, MergeFile, MergeSession, PullKind, PullPlan
from projectapp.gitstate import GitKind, GitState
from projectapp.models import Project, Task
from projectapp.storage import dumps_project
from projectapp.views import MainView

from datetime import date

BEHIND = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=0, behind=2)


class FakePullOps:
    def __init__(self) -> None:
        self.plan: PullPlan | GitResult = PullPlan(PullKind.UP_TO_DATE, "origin/main")
        self.session: MergeSession | GitResult = MergeSession("origin/main", [])
        self.ff_result = GitResult(True, "取り込みました")
        self.finish_result = GitResult(True, "取り込みました", "abc1234")
        self.calls: list[str] = []
        self.merged: dict[str, str] | None = None
        self.abort_result = GitResult(True, "中止")
        self.on_prepare: Callable[[], None] | None = None
        self.on_finish: Callable[[], None] | None = None

    def prepare(self, d: Path):
        self.calls.append("prepare")
        if self.on_prepare is not None:
            self.on_prepare()
        return self.plan

    def fast_forward(self, d: Path):
        self.calls.append("ff")
        return self.ff_result

    def start_merge(self, d: Path, upstream: str):
        self.calls.append("start")
        return self.session

    def finish_merge(self, d: Path, session: MergeSession, merged: dict[str, str]):
        self.calls.append("finish")
        self.merged = merged
        if self.on_finish is not None:
            self.on_finish()
        return self.finish_result

    def abort(self, d: Path):
        self.calls.append("abort")
        return self.abort_result


async def open_pull(
    user: User, tmp_path: Path, state: GitState = BEHIND
) -> tuple[MainView, FakePullOps]:
    fakes, ops = Fakes(state), FakePullOps()
    save_cache({}, tmp_path)
    views: list[MainView] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(
            tmp_path, httpx.MockTransport(lambda request: httpx.Response(200))
        )
        view.read_git = fakes.read_git
        view.pull_ops = ops
        views.append(view)
        view.build()

    await user.open("/")
    view = views[0]
    assert await wait_until(lambda: view.git_state is state)
    return view, ops


def project_text(effort: float) -> str:
    return dumps_project(
        Project(
            "甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=effort)]
        )
    )


async def test_the_pull_menu_item_and_reasons(user: User, tmp_path: Path) -> None:
    view, _ = await open_pull(user, tmp_path)
    entry = menu_entry(view, "git-pull")
    assert entry.enabled and view.git_reason("pull") is None
    view.git_state = GitState(
        GitKind.OK, branch="main", upstream="origin/main", ahead=0, behind=0, dirty=1
    )
    assert "未コミット" in (view.git_reason("pull") or "")
    view.git_state = GitState(GitKind.OK, branch="main")
    assert view.git_reason("pull") == "上流がありません"
    view.git_state = GitState(GitKind.NOT_REPO)
    assert view.git_reason("pull") == "git の作業ツリーではありません"
    view.git_state = BEHIND
    view.git_busy = True
    assert view.git_reason("pull") == "実行中です"


async def test_unsaved_edits_refuse_the_pull(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    view.save_section("追加")
    assert "保存されていない編集" in (view.git_reason("pull") or "")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("保存されていない編集"))
    assert ops.calls == []


async def test_up_to_date_just_notifies(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("最新です"))
    assert ops.calls == ["prepare"] and not view.git_busy


async def test_prepare_failure_is_reported(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = GitResult(False, "上流がありません")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("上流がありません"))
    assert not view.git_busy


async def test_fast_forward(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.FAST_FORWARD, "origin/main")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("取り込みました"))
    assert ops.calls == ["prepare", "ff"]


async def test_merge_without_conflicts_finishes_with_the_merged_text(
    user: User, tmp_path: Path
) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    base, ours = project_text(4.0), project_text(8.0)
    theirs = dumps_project(
        Project("甲", date(2026, 10, 1), tasks=[Task("a2", id="t1", effort_hours=4.0)])
    )
    ops.session = MergeSession(
        "origin/main", [MergeFile("甲.json", base, ours, theirs)]
    )
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("取り込みました"))
    assert ops.calls == ["prepare", "start", "finish"] and set(ops.merged) == {
        "甲.json"
    }
    assert '"a2"' in ops.merged["甲.json"] and "8.0" in ops.merged["甲.json"]


async def test_merge_with_a_conflict_waits_for_the_choice(
    user: User, tmp_path: Path
) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession(
        "origin/main",
        [MergeFile("甲.json", project_text(4.0), project_text(8.0), project_text(2.0))],
    )
    view.start_git_pull()
    await user.should_see(marker="conflict-apply")
    assert ops.calls == ["prepare", "start"]
    user.find(marker="conflict-apply").click()  # 既定は相手
    assert await wait_until(lambda: "finish" in ops.calls)
    assert "2.0" in ops.merged["甲.json"]


async def test_cancelling_the_conflict_dialog_aborts(
    user: User, tmp_path: Path
) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession(
        "origin/main",
        [MergeFile("甲.json", project_text(4.0), project_text(8.0), project_text(2.0))],
    )
    view.start_git_pull()
    await user.should_see(marker="conflict-abort")
    user.find(marker="conflict-abort").click()
    assert await wait_until(lambda: "abort" in ops.calls)
    assert "finish" not in ops.calls and not view.git_busy


async def test_unreadable_files_abort_the_merge(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession("origin/main", [MergeFile("甲.json", "{", "{", "{")])
    view.start_git_pull()
    assert await wait_until(lambda: "abort" in ops.calls)
    assert "finish" not in ops.calls and not view.git_busy


async def test_pull_reloads_the_open_project_and_refreshes_git(
    user: User, tmp_path: Path
) -> None:
    from projectapp.storage import save_project

    save_project(
        Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=4.0)]),
        tmp_path,
    )
    view, ops = await open_pull(user, tmp_path)
    view.files = {"甲": tmp_path / "甲.json"}
    view.open_project("甲")
    save_project(
        Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=9.0)]),
        tmp_path,
    )  # プルで書き換わった想定
    ops.plan = PullPlan(PullKind.FAST_FORWARD, "origin/main")
    view.start_git_pull()
    assert await wait_until(lambda: view.project.tasks[0].effort_hours == 9.0)
    assert not view.is_dirty()


async def test_an_unexpected_error_while_merging_aborts(
    user: User, tmp_path: Path, monkeypatch
) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession(
        "origin/main",
        [MergeFile("甲.json", project_text(4.0), project_text(8.0), project_text(4.0))],
    )

    def boom(*args, **kwargs):
        raise RuntimeError("想定外")

    monkeypatch.setattr("projectapp.views.merge_files", boom)
    view.start_git_pull()
    assert await wait_until(lambda: "abort" in ops.calls)
    assert "finish" not in ops.calls and not view.git_busy
    assert await wait_until(lambda: user.notify.contains("想定外"))


async def test_a_failed_abort_is_reported_not_hidden(
    user: User, tmp_path: Path
) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession(
        "origin/main",
        [MergeFile("甲.json", project_text(4.0), project_text(8.0), project_text(2.0))],
    )
    ops.abort_result = GitResult(False, "index.lock が残っています")
    view.start_git_pull()
    await user.should_see(marker="conflict-abort")
    user.find(marker="conflict-abort").click()
    assert await wait_until(lambda: user.notify.contains("index.lock が残っています"))
    assert not user.notify.contains("取り込みを中止しました")


async def test_an_edit_made_while_fetching_stops_the_pull(
    user: User, tmp_path: Path
) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.FAST_FORWARD, "origin/main")
    ops.on_prepare = lambda: view.save_section("取得中の編集")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("保存されていない編集"))
    assert ops.calls == ["prepare"] and not view.git_busy


async def test_an_edit_made_while_merging_is_not_discarded_by_the_reload(
    user: User, tmp_path: Path
) -> None:
    from projectapp.storage import save_project

    save_project(
        Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=4.0)]),
        tmp_path,
    )
    view, ops = await open_pull(user, tmp_path)
    view.files = {"甲": tmp_path / "甲.json"}
    view.open_project("甲")
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession(
        "origin/main",
        [MergeFile("甲.json", project_text(4.0), project_text(4.0), project_text(4.0))],
    )
    ops.on_finish = lambda: view.save_section("取り込み中の編集")
    view.start_git_pull()
    assert await wait_until(lambda: "finish" in ops.calls and not view.git_busy)
    assert any(
        s.name == "取り込み中の編集" for s in view.project.sections
    )  # 読み直しで捨てない
    assert await wait_until(lambda: user.notify.contains("読み直していません"))
