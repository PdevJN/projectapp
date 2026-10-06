"""ガントチャートのヘッダー(日付・曜日の行)を読むための、テスト用の補助。

日付・曜日の行は、1 つの `ui.html`(マーカー `label-row-cells`)で、列ごとに `data-col="<日付>"` のセルを持つ。
個々のラベルにマーカーは付かないので、この要素の内容から読む。
"""

import asyncio
import html
import re
from collections.abc import Callable

from nicegui.testing import User

CELL_START = re.compile(r'(?=<div[^>]*data-col=)')  # セルの開始タグの直前で分ける
DAY = re.compile(r'data-col="([^"]+)"')
LINE = re.compile(r"<div>(.*?)</div>", re.S)  # 属性のない <div> が、セルの中の行


def header_cells(user: User) -> dict[str, tuple[str, str | None]]:
    """日付(`2026-10-05`) → (日付のラベル, 曜日。曜日の行がなければ None)。ヘッダーがなければ空。"""
    elements = user.find(marker="label-row-cells").elements
    if not elements:
        return {}
    cells = {}
    for segment in CELL_START.split(elements.pop().content)[1:]:
        day = DAY.search(segment)
        assert day is not None
        lines = [html.unescape(line) for line in LINE.findall(segment)]
        cells[day.group(1)] = (lines[0], lines[1] if len(lines) > 1 else None)
    return cells


async def settles(user: User, condition: Callable[[dict[str, tuple[str, str | None]]], bool], retries: int = 6) -> None:
    """ヘッダーが `condition` を満たすまで待つ(描き直しは、背景タスクで起きる)。"""
    for _ in range(retries):
        if condition(header_cells(user)):
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"ヘッダーが条件を満たさなかった: {header_cells(user)}")


async def should_see_column(user: User, day: str) -> None:
    await settles(user, lambda cells: day in cells)


async def should_not_see_column(user: User, day: str) -> None:
    await settles(user, lambda cells: day not in cells)
