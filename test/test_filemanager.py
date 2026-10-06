from pathlib import Path

import pytest

from projectapp.filemanager import open_command, open_folder


@pytest.mark.parametrize(
    ("platform", "command"),
    [("darwin", "open"), ("win32", "explorer"), ("linux", "xdg-open"), ("freebsd14", "xdg-open")],
)
def test_the_command_depends_on_the_platform(platform: str, command: str, tmp_path: Path) -> None:
    assert open_command(platform, tmp_path) == [command, str(tmp_path)]


def test_a_path_with_spaces_or_a_leading_dash_is_one_argument(tmp_path: Path) -> None:
    folder = tmp_path / "-a b;c"
    assert open_command("linux", folder) == ["xdg-open", str(folder)]  # シェルを通さない。1 つの引数のまま渡る


def test_open_folder_creates_a_missing_folder_and_launches_the_file_manager(tmp_path: Path) -> None:
    folder = tmp_path / ".projectapp"
    launched: list[list[str]] = []
    open_folder(folder, platform="darwin", launch=launched.append)
    assert folder.is_dir()
    assert launched == [["open", str(folder)]]


def test_open_folder_lets_a_launch_failure_through(tmp_path: Path) -> None:
    def fail(command: list[str]) -> None:
        raise FileNotFoundError(command[0])

    with pytest.raises(OSError):
        open_folder(tmp_path, platform="linux", launch=fail)
