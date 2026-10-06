"""フォルダを、OS のファイラ(Finder・エクスプローラー・xdg-open の先)で開く。NiceGUI には依存しない。"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


def open_command(platform: str, path: Path) -> list[str]:
    """ファイラを起動するコマンド。シェルを通さず、パスは 1 つの引数のまま渡す。"""
    if platform == "darwin":
        return ["open", str(path)]
    if platform.startswith("win"):
        return ["explorer", str(path)]
    return ["xdg-open", str(path)]


def _launch(command: list[str]) -> object:
    return subprocess.Popen(command)  # 待たない(ファイラが閉じるまで画面を止めない)


def open_folder(
    path: Path,
    platform: str = sys.platform,
    launch: Callable[[list[str]], object] = _launch,
) -> None:
    """フォルダを開く。まだなければ作る。コマンドがない・起動できないときは OSError。"""
    path.mkdir(parents=True, exist_ok=True)
    launch(open_command(platform, path))
