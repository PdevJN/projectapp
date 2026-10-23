"""アプリのエントリポイント。"""

import argparse
import multiprocessing
import socket
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
    mode: Literal["both", "native", "web"]
    port: int


def port_number(text: str) -> int:
    port = int(text)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("1〜65535 で指定してください")
    return port


def parse_args(argv: Sequence[str] | None = None) -> LaunchOptions:
    parser = argparse.ArgumentParser(prog="projectapp")
    parser.add_argument("--mode", choices=["both", "native", "web"], default="native", help="native=ネイティブウィンドウのみ(既定)、both=ネイティブ+Web、web=ブラウザのみ")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT, help="Web のポート(both・web。既定 8080)")
    args = parser.parse_args(argv)
    return LaunchOptions(mode=args.mode, port=args.port)


def port_available(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex((LOCAL_HOST, port)) != 0


def run_kwargs(options: LaunchOptions) -> dict[str, Any]:
    """`ui.run` に渡す、モード別の引数。"""
    if options.mode == "native":
        return {"native": True}
    if options.mode == "both":
        return {"native": True, "host": LOCAL_HOST, "port": options.port}
    return {"native": False, "host": LOCAL_HOST, "port": options.port, "show": True}


def main() -> None:
    options = parse_args()
    if options.mode == "both" and multiprocessing.parent_process() is None:  # 子プロセスでは判定しない
        if port_available(options.port):
            print(f"Web: http://{LOCAL_HOST}:{options.port}")
        else:
            print(f"ポート {options.port} が使用中のため、Web なしのネイティブで起動します")
            options = LaunchOptions(mode="native", port=options.port)

    @ui.page("/")
    def index() -> None:
        MainView().build()

    register_static_files()
    ui.run(title="projectapp", reload=False, language="ja", **run_kwargs(options))


if __name__ in {"__main__", "__mp_main__"}:
    main()
