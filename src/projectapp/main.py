"""アプリのエントリポイント。"""

from nicegui import ui

from projectapp.views import MainView


def main() -> None:
    @ui.page("/")
    def index() -> None:
        MainView().build()

    ui.run(title="projectapp", native=True, reload=False, language="ja")


if __name__ in {"__main__", "__mp_main__"}:
    main()
