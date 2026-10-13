from nicegui import ui
from nicegui.testing import User

from projectapp.forms import open_commit_dialog
from projectapp.gitops import ChangeStatus, FileChange, default_message

CHANGES = [
    FileChange("乙.json", ChangeStatus.DELETED),
    FileChange("丁.json", ChangeStatus.ADDED),
    FileChange("甲.json", ChangeStatus.MODIFIED),
]


def mount(calls: list[tuple], *, push_blocked: str | None = None, unsaved: bool = False) -> None:
    @ui.page("/")
    def index() -> None:
        open_commit_dialog(
            CHANGES, default_message, push_blocked, unsaved, lambda names, message, push: calls.append((names, message, push))
        )


def element(user: User, marker: str) -> ui.element:
    return next(iter(user.find(marker=marker).elements))


def dialog_is_open(user: User) -> bool:
    """`User`のシミュレーションは`hide`を送らないので、要素の消去ではなく、ダイアログの開閉で見る。"""
    return any(d.value for d in user.find(kind=ui.dialog).elements)


def checked(user: User) -> list[str]:
    return [c.name for c in CHANGES if element(user, f"commit-file-{c.name}").value]


async def test_every_file_is_checked_with_the_default_message(user: User) -> None:
    mount([])
    await user.open("/")
    assert checked(user) == ["乙.json", "丁.json", "甲.json"]
    assert element(user, "commit-message").value == "プロジェクトを更新: 乙, 丁, 甲"
    await user.should_see("削除")
    await user.should_see("追加")
    await user.should_see("変更")


async def test_unchecking_updates_the_untouched_message(user: User) -> None:
    mount([])
    await user.open("/")
    user.find(marker="commit-file-丁.json").click()
    assert checked(user) == ["乙.json", "甲.json"]
    assert element(user, "commit-message").value == "プロジェクトを更新: 乙, 甲"


async def test_an_edited_message_is_not_overwritten(user: User) -> None:
    mount([])
    await user.open("/")
    user.find(marker="commit-message").clear().type("自分の文")
    user.find(marker="commit-file-丁.json").click()
    assert element(user, "commit-message").value == "自分の文"


async def test_commit_passes_the_chosen_names_message_and_no_push(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="commit-file-乙.json").click()
    user.find(marker="commit-submit").click()
    assert calls == [(["丁.json", "甲.json"], "プロジェクトを更新: 丁, 甲", False)]
    assert not dialog_is_open(user)


async def test_commit_and_push_asks_for_the_push(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="commit-submit-push").click()
    assert calls == [(["乙.json", "丁.json", "甲.json"], "プロジェクトを更新: 乙, 丁, 甲", True)]


async def test_cancel_does_nothing(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="commit-cancel").click()
    assert calls == []
    assert not dialog_is_open(user)


async def test_nothing_checked_or_an_empty_message_blocks_both_buttons(user: User) -> None:
    mount([])
    await user.open("/")
    for change in CHANGES:
        user.find(marker=f"commit-file-{change.name}").click()
    assert not element(user, "commit-submit").enabled and not element(user, "commit-submit-push").enabled
    user.find(marker="commit-file-甲.json").click()
    assert element(user, "commit-submit").enabled
    user.find(marker="commit-message").clear()
    assert not element(user, "commit-submit").enabled and not element(user, "commit-submit-push").enabled


async def test_a_blocked_push_disables_only_commit_and_push(user: User) -> None:
    mount([], push_blocked="上流がありません")
    await user.open("/")
    assert element(user, "commit-submit").enabled
    assert not element(user, "commit-submit-push").enabled


async def test_the_unsaved_warning_is_shown_only_when_needed(user: User) -> None:
    mount([], unsaved=True)
    await user.open("/")
    await user.should_see(marker="commit-unsaved")


async def test_no_unsaved_warning_by_default(user: User) -> None:
    mount([])
    await user.open("/")
    await user.should_not_see(marker="commit-unsaved")
