import asyncio
from collections.abc import Callable

from nicegui import ui
from nicegui.testing import User

from projectapp.theme import DEFAULTS, MISMATCH_MESSAGE, CustomTheme
from projectapp.theme_dialog import open_theme_dialog

async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


class Recorder:
    def __init__(self, apply_result: bool = True) -> None:
        self.previews: list[CustomTheme] = []
        self.applied: list[CustomTheme] = []
        self.cancelled = 0
        self.apply_result = apply_result

    def on_apply(self, theme: CustomTheme) -> bool:
        self.applied.append(theme)
        return self.apply_result

    def mount(self, initial: CustomTheme) -> None:
        @ui.page("/")
        def index() -> None:
            ui.button(
                "open",
                on_click=lambda: open_theme_dialog(
                    initial, self.previews.append, self.on_apply, lambda: setattr(self, "cancelled", self.cancelled + 1)
                ),
            )


def field(user: User, marker: str) -> ui.input:
    return user.find(marker=marker).elements.pop()  # type: ignore[return-value]


def shown(user: User, marker: str) -> bool:
    """マーカーの要素があり、見えている(隠れた要素は`user.find`に出ない)。"""
    return any(marker in e._markers and e.visible for e in user.client.elements.values())


def warnings_text(user: User) -> list[str]:
    return [e.text for e in user.client.elements.values() if "theme-warning" in e._markers]


async def test_editing_a_color_previews_it_immediately(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7E57C2")
    assert rec.previews[-1].primary == "#7e57c2"
    field(user, "theme-background").set_value("#fafafa")
    assert rec.previews[-1].background == "#fafafa" and rec.previews[-1].primary == "#7e57c2"


async def test_apply_closes_and_passes_the_edited_theme(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7e57c2")
    user.find(marker="theme-apply").click()
    assert rec.applied == [CustomTheme("light", "#7e57c2", None, "#ffffff", "#000000")]
    assert rec.cancelled == 0


async def test_cancel_restores_without_applying(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7e57c2")
    user.find(marker="theme-cancel").click()
    assert rec.cancelled == 1 and rec.applied == []


async def test_closing_without_applying_also_cancels(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    dialog = next(e for e in user.find(kind=ui.dialog).elements)
    dialog.close()  # ESC・外側クリックと同じ(hide が飛ぶ)
    assert await wait_until(lambda: rec.cancelled == 1)


async def test_a_failed_apply_keeps_the_dialog_open_and_does_not_cancel(user: User) -> None:
    rec = Recorder(apply_result=False)
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    user.find(marker="theme-apply").click()
    assert len(rec.applied) == 1
    await user.should_see(marker="theme-apply")  # まだ開いている
    assert rec.cancelled == 0


async def test_invalid_color_disables_apply_and_keeps_the_last_valid_preview(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-primary").set_value("#7e57c2")
    count = len(rec.previews)
    for bad in ("#fff", "#7e57c2ff", "red", ""):
        field(user, "theme-primary").set_value(bad)
        assert not user.find(marker="theme-apply").elements.pop().enabled
        assert len(rec.previews) == count and rec.previews[-1].primary == "#7e57c2"
    field(user, "theme-primary").set_value("#336699")
    assert user.find(marker="theme-apply").elements.pop().enabled


async def test_header_follow_checkbox_hides_the_header_input_and_sends_none(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    follow = user.find(marker="theme-header-follow").elements.pop()
    assert follow.value is True and not shown(user, "theme-header")
    follow.set_value(False)
    assert shown(user, "theme-header")
    assert rec.previews[-1].header is not None
    field(user, "theme-header").set_value("#ffeb3b")
    assert rec.previews[-1].header == "#ffeb3b"
    follow.set_value(True)
    assert rec.previews[-1].header is None


async def test_an_invalid_header_does_not_block_apply_while_following(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    follow = user.find(marker="theme-header-follow").elements.pop()
    follow.set_value(False)
    field(user, "theme-header").set_value("zzz")
    assert not user.find(marker="theme-apply").elements.pop().enabled
    follow.set_value(True)
    assert user.find(marker="theme-apply").elements.pop().enabled


async def test_reset_puts_the_defaults_of_the_selected_base(user: User) -> None:
    rec = Recorder()
    rec.mount(CustomTheme("dark", "#7e57c2", "#ffeb3b", "#1e1e2e", "#e6e6f0"))
    await user.open("/")
    user.find("open").click()
    user.find(marker="theme-reset").click()
    assert rec.previews[-1] == DEFAULTS["dark"]
    assert rec.applied == []  # 保存は適用のとき
    user.find(marker="theme-apply").click()
    assert rec.applied == [DEFAULTS["dark"]]


async def test_switching_the_base_changes_only_the_base_and_warns_on_mismatch(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    assert warnings_text(user) == []
    user.find(marker="theme-base").elements.pop().set_value("dark")
    assert rec.previews[-1] == CustomTheme("dark", "#5898d4", None, "#ffffff", "#000000")
    assert warnings_text(user) == [MISMATCH_MESSAGE]


async def test_low_contrast_shows_an_orange_warning_but_apply_stays_enabled(user: User) -> None:
    rec = Recorder()
    rec.mount(DEFAULTS["light"])
    await user.open("/")
    user.find("open").click()
    field(user, "theme-foreground").set_value("#999999")
    assert warnings_text(user) == ["文字と背景のコントラスト比が 2.8:1 です。読みにくい可能性があります"]
    assert user.find(marker="theme-apply").elements.pop().enabled
