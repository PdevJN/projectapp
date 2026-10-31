"""メンバーの丸いアイコン。アイコンがなければ(壊れていても)頭文字のチップを出す。"""

import html

from nicegui import ui

from projectapp.icons import is_valid_icon

ICON_BORDER = "1px solid rgba(128, 128, 128, 0.6)"


def avatar(name: str, icon: str, size: int) -> ui.element:
    """`size`px 四方の丸。有効なアイコンがあれば画像、なければ名前の頭文字(名前が空なら `?`)。"""
    base = f"flex: none; width: {size}px; height: {size}px; border-radius: 50%;"
    if icon and is_valid_icon(icon):
        return ui.element("img").props(f'src="{icon}" alt=""').style(
            base + f" object-fit: cover; border: {ICON_BORDER}"
        )
    return ui.label(name[:1] or "?").style(
        base
        + f" line-height: {size}px; text-align: center; font-size: {max(8, size * 5 // 8)}px;"
        + " background: rgba(128, 128, 128, 0.3)"
    )


def avatar_html(name: str, icon: str, size: int) -> str:
    """`avatar`の HTML 文字列版(ヒートマップの表のように、要素を置けない場所用)。名前・アイコンはエスケープする。"""
    base = f"display: inline-block; vertical-align: middle; margin-right: 4px; width: {size}px; height: {size}px; border-radius: 50%;"
    if icon and is_valid_icon(icon):
        style = base + f" object-fit: cover; border: {ICON_BORDER}"
        return f'<img src="{html.escape(icon)}" alt="" style="{style}">'
    style = (
        base
        + f" line-height: {size}px; text-align: center; font-size: {max(8, size * 5 // 8)}px;"
        + " background: rgba(128, 128, 128, 0.3)"
    )
    return f'<span style="{style}">{html.escape(name[:1] or "?")}</span>'
