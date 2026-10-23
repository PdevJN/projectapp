"""アプリのエントリポイント。"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from nicegui import ui

from projectapp.export import register_static_files
from projectapp.views import MainView

LOCAL_HOST = "127.0.0.1"  # Web 起動はこのマシンだけ(認証がないので LAN には出さない)
DEFAULT_PORT = 8080


@dataclass(frozen=True)
class LaunchOptions:
    mode: Literal["native", "web"]
    port: int


def port_number(text: str) -> int:
    port = int(text)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("1〜65535 で指定してください")
    return port


def parse_args(argv: Sequence[str] | None = None) -> LaunchOptions:
    parser = argparse.ArgumentParser(prog="projectapp")
    parser.add_argument("--mode", choices=["native", "web"], default="native", help="native=ネイティブウィンドウ(既定)、web=ブラウザ")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT, help="web のポート(既定 8080)")
    args = parser.parse_args(argv)
    return LaunchOptions(mode=args.mode, port=args.port)


def run_kwargs(options: LaunchOptions) -> dict[str, Any]:
    """`ui.run` に渡す、モード別の引数。"""
    if options.mode == "native":
        return {"native": True}
    return {"native": False, "host": LOCAL_HOST, "port": options.port, "show": True}


def main() -> None:
    options = parse_args()

    @ui.page("/")
    def index() -> None:
        MainView().build()

    register_static_files()
    ui.run(title="projectapp", reload=False, language="ja", **run_kwargs(options))


if __name__ in {"__main__", "__mp_main__"}:
    main()
