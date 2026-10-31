import asyncio
from collections.abc import Callable

from nicegui import ui
from nicegui.testing import User

from projectapp.theme_dialog import open_today_color_dialog


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


class Recorder:
    def __init__(self, apply_result: bool = True) -> None:
        self.previews: list[str | None] = []
        self.applied: list[str | None] = []
        self.cancelled = 0
        self.apply_result = apply_result

    def on_apply(self, color: str | None) -> bool:
        self.applied.append(color)
        return self.apply_result

    def mount(self, initial: str | None) -> None:
        @ui.page("/")
        def index() -> None:
            ui.button(
                "open",
                on_click=lambda: open_today_color_dialog(
                    initial,
                    self.previews.append,
                    self.on_apply,
                    lambda: setattr(self, "cancelled", self.cancelled + 1),
                ),
            )


def field(user: User) -> ui.input:
    return user.find(marker="today-color").elements.pop()  # type: ignore[return-value]


def apply_enabled(user: User) -> bool:
    return user.find(marker="today-apply").elements.pop().enabled


async def test_the_field_starts_with_the_saved_color_or_empty(user: User) -> None:
    rec = Recorder()
    rec.mount("#1e88e5")
    await user.open("/")
    user.find("open").click()
    assert field(user).value == "#1e88e5"


async def test_the_field_is_empty_when_unset(user: User) -> None:
    rec = Recorder()
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    assert not field(user).value


async def test_editing_previews_the_lowercased_color(user: User) -> None:
    rec = Recorder()
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    field(user).set_value("#1E88E5")
    assert rec.previews[-1] == "#1e88e5"


async def test_apply_passes_the_color_and_closes_without_cancelling(user: User) -> None:
    rec = Recorder()
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    field(user).set_value("#1e88e5")
    user.find(marker="today-apply").click()
    assert rec.applied == ["#1e88e5"] and rec.cancelled == 0


async def test_an_empty_field_means_the_default_and_can_be_applied(user: User) -> None:
    rec = Recorder()
    rec.mount("#1e88e5")
    await user.open("/")
    user.find("open").click()
    field(user).set_value("")
    assert rec.previews[-1] is None and apply_enabled(user)
    user.find(marker="today-apply").click()
    assert rec.applied == [None]


async def test_reset_empties_the_field_and_previews_the_default(user: User) -> None:
    rec = Recorder()
    rec.mount("#1e88e5")
    await user.open("/")
    user.find("open").click()
    user.find(marker="today-reset").click()
    assert not field(user).value and rec.previews[-1] is None


async def test_an_invalid_color_disables_apply_and_keeps_the_last_preview(
    user: User,
) -> None:
    rec = Recorder()
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    field(user).set_value("#1e88e5")
    count = len(rec.previews)
    for bad in ("#fff", "red", "#1e88e5ff"):
        field(user).set_value(bad)
        assert not apply_enabled(user)
        assert len(rec.previews) == count
    field(user).set_value("#336699")
    assert apply_enabled(user)


async def test_cancel_restores_without_applying(user: User) -> None:
    rec = Recorder()
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    field(user).set_value("#1e88e5")
    user.find(marker="today-cancel").click()
    assert rec.cancelled == 1 and rec.applied == []


async def test_closing_without_applying_also_cancels(user: User) -> None:
    rec = Recorder()
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    next(iter(user.find(kind=ui.dialog).elements)).close()  # ESC・外側クリックと同じ
    assert await wait_until(lambda: rec.cancelled == 1)


async def test_a_failed_apply_keeps_the_dialog_open_and_does_not_cancel(
    user: User,
) -> None:
    rec = Recorder(apply_result=False)
    rec.mount(None)
    await user.open("/")
    user.find("open").click()
    field(user).set_value("#1e88e5")
    user.find(marker="today-apply").click()
    assert len(rec.applied) == 1 and rec.cancelled == 0
    await user.should_see(marker="today-apply")
