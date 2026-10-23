"""起動オプション(アプリ / Web)の解釈。"""

import pytest

from projectapp.main import LaunchOptions, parse_args, run_kwargs


def test_default_is_native() -> None:
    assert parse_args([]) == LaunchOptions(mode="native", port=8080)


def test_web_mode_and_port() -> None:
    assert parse_args(["--mode", "web", "--port", "9000"]) == LaunchOptions(mode="web", port=9000)


@pytest.mark.parametrize("argv", [["--mode", "lan"], ["--port", "x"], ["--port", "0"], ["--port", "65536"], ["--host", "0.0.0.0"]])
def test_invalid_arguments_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_native_run_kwargs() -> None:
    kwargs = run_kwargs(LaunchOptions(mode="native", port=8080))
    assert kwargs["native"] is True
    assert "host" not in kwargs


def test_web_run_kwargs_binds_to_localhost_and_opens_browser() -> None:
    kwargs = run_kwargs(LaunchOptions(mode="web", port=9000))
    assert kwargs["native"] is False
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9000
    assert kwargs["show"] is True
