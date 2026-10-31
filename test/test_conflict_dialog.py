from nicegui import ui
from nicegui.testing import User

from projectapp.forms import open_merge_conflict_dialog
from projectapp.merge import DELETED, OURS, THEIRS, Conflict

CONFLICTS = [
    Conflict("task", "t1", "調査", "工数", 8.0, 2.0),
    Conflict("task", "t2", "設計", DELETED, None, {"name": "設計"}),
]


def mount(applied: list[dict], cancelled: list[bool]) -> None:
    @ui.page("/")
    def index() -> None:
        open_merge_conflict_dialog(
            "甲.json", CONFLICTS, applied.append, lambda: cancelled.append(True)
        )


def element(user: User, marker: str) -> ui.element:
    return next(iter(user.find(marker=marker).elements))


async def test_defaults_to_theirs_and_applies_the_choices(user: User) -> None:
    applied: list[dict] = []
    cancelled: list[bool] = []
    mount(applied, cancelled)
    await user.open("/")
    await user.should_see("甲.json の衝突")
    radios = [element(user, f"conflict-choice-{i}") for i in range(2)]
    assert [r.value for r in radios] == [THEIRS, THEIRS]
    radios[0].set_value(OURS)
    user.find(marker="conflict-apply").click()
    assert applied == [{("task", "t1", "工数"): OURS, ("task", "t2", DELETED): THEIRS}]
    assert cancelled == []


async def test_deleted_conflicts_are_worded_as_delete_or_keep(user: User) -> None:
    mount([], [])
    await user.open("/")
    await user.should_see("自分: 削除する")
    await user.should_see("相手: 残す")


async def test_abort_cancels_once(user: User) -> None:
    applied: list[dict] = []
    cancelled: list[bool] = []
    mount(applied, cancelled)
    await user.open("/")
    user.find(marker="conflict-abort").click()
    assert cancelled == [True] and applied == []


async def test_hide_cancels_even_though_disposable_deletes_the_dialog(
    user: User,
) -> None:
    """ESC・外側のクリックは`hide`で届く。`disposable`の削除より前に、中止が呼ばれること。"""
    applied: list[dict] = []
    cancelled: list[bool] = []
    mount(applied, cancelled)
    await user.open("/")
    dialog = next(e for e in user.client.elements.values() if isinstance(e, ui.dialog))
    for listener in list(dialog._event_listeners.values()):
        if listener.type == "hide":
            user.client.handle_event(
                {"id": dialog.id, "listener_id": listener.id, "args": []}
            )
    assert cancelled == [True] and applied == []
