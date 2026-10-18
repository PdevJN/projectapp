from nicegui import ui
from nicegui.testing import User

from projectapp.avatar import avatar


def mount_avatars(*specs: tuple[str, str, int]) -> None:
    @ui.page("/")
    def index() -> None:
        for number, (name, icon, size) in enumerate(specs):
            avatar(name, icon, size).mark(f"a{number}")


async def test_an_avatar_without_an_icon_shows_the_first_character(user: User) -> None:
    mount_avatars(("山田太郎", "", 16))
    await user.open("/")
    element = user.find(marker="a0").elements.pop()
    assert element.text == "山" and element._style["width"] == element._style["height"] == "16px"
    assert element._style["border-radius"] == "50%"


async def test_an_avatar_with_an_icon_is_a_round_image(user: User, icon: str) -> None:
    mount_avatars(("山田", icon, 28))
    await user.open("/")
    element = user.find(marker="a0").elements.pop()
    assert element.tag == "img" and element._props["src"] == icon
    assert element._style["width"] == "28px" and element._style["border-radius"] == "50%"


async def test_an_avatar_with_a_broken_icon_falls_back_to_the_first_character(user: User) -> None:
    mount_avatars(("山田", "data:image/png;base64,AAAA", 16), ("", "", 16), ("😀太郎", "", 16))
    await user.open("/")
    assert user.find(marker="a0").elements.pop().text == "山"
    assert user.find(marker="a1").elements.pop().text == "?"  # 名前が空でも落ちない
    assert user.find(marker="a2").elements.pop().text == "😀"
