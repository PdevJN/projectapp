"""メンバーの丸いアイコン。アイコンがなければ(壊れていても)頭文字のチップを出す。"""

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
