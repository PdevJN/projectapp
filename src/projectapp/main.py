"""アプリのエントリポイント。"""

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, NoReturn

from nicegui import ui

from projectapp.export import STATIC_DIR, register_static_files
from projectapp.views import MainView

LOCAL_HOST = "127.0.0.1"  # Web 起動はこのマシンだけ(認証がないので LAN には出さない)
DEFAULT_PORT = 8080


@dataclass(frozen=True)
class LaunchOptions:
    mode: Literal["native", "web"]
    port: int


MODES = ("native", "web")


def port_number(text: str) -> int:
    if not text.isdecimal():
        raise argparse.ArgumentTypeError(f"値が正しくありません: {text!r}")
    port = int(text)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"値が正しくありません: {text!r}(1〜65535 で指定してください)")
    return port


class JapaneseParser(argparse.ArgumentParser):
    """argparse のエラー文を日本語にする。"""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: エラー: {self.translate(message)}\n")

    @staticmethod
    def translate(message: str) -> str:
        modes = " / ".join(MODES)
        if found := re.fullmatch(r"argument (\S+): expected one argument", message):
            hint = f"({modes})" if found[1] == "--mode" else ""
            return f"{found[1]} には値を指定してください{hint}"
        if found := re.fullmatch(r"argument (\S+): invalid choice: ('[^']*').*", message):
            return f"{found[1]} の値が正しくありません: {found[2]}({modes})"
        if found := re.fullmatch(r"argument (\S+): (値が.*)", message):
            return f"{found[1]} の{found[2]}"
        if found := re.fullmatch(r"argument (\S+): invalid \w+ value: ('[^']*')", message):
            return f"{found[1]} の値が正しくありません: {found[2]}"
        if found := re.fullmatch(r"unrecognized arguments: (.*)", message):
            return f"不明な引数です: {found[1]}"
        return message


def parse_args(argv: Sequence[str] | None = None) -> LaunchOptions:
    parser = JapaneseParser(prog="projectapp")
    parser.add_argument("--mode", choices=MODES, default="native", help="native=ネイティブウィンドウのみ(既定)、web=ブラウザのみ")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT, help="Web のポート(web。既定 8080)")
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
    ui.run(title="projectapp", favicon=STATIC_DIR / "favicon.svg", reload=False, language="ja", **run_kwargs(options))


if __name__ in {"__main__", "__mp_main__"}:
    main()
