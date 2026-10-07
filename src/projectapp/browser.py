"""URL を、OS の既定のブラウザで開く。NiceGUI には依存しない。"""

import webbrowser
from collections.abc import Callable

from projectapp.urls import has_allowed_scheme


def open_url(url: str, opener: Callable[[str], bool] = webbrowser.open) -> None:
    """URL を開く。http(s) 以外と、開けなかったときは OSError。opener はテストで差し替える。"""
    if not has_allowed_scheme(url):
        raise OSError(f"開けない URL です: {url}")
    if not opener(url):
        raise OSError("ブラウザを開けませんでした")
