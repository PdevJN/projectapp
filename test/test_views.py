from nicegui.testing import User

from projectapp.views import MainView


async def test_main_view(user: User) -> None:
    from nicegui import ui

    @ui.page("/")
    def index() -> None:
        MainView().build()

    await user.open("/")
    await user.should_see("新規プロジェクト")
    await user.should_see("開く")
