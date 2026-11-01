"""ツールチップにタスク名をチップで並べる共通の部品(要望 118)。"""

from collections.abc import Sequence

from nicegui import ui

MAX_TIP_CHIPS = 10  # ツールチップに並べるチップの上限。超えた分は「+n件」にまとめる


def name_chips_tooltip(
    names: Sequence[str],
    chip_marker: str,
    *,
    more_marker: str | None = None,
    color: str | None = None,
    limit: int | None = MAX_TIP_CHIPS,
) -> None:
    """直前の`with`の要素に、タスク名のチップを並べたツールチップを付ける。

    地は、テーマによらず濃い灰色で、チップの枠と文字は白(`color`があればその色)。Quasar のチップは既定で
    テーマごとの文字色を持ち(ライトは黒、ダークは白)、地と合わず読めなくなるので、継承させる。
    `limit`を超えた分は`+n件`にまとめる(`None`なら全部)。名前がなければ何も付けない。
    """
    if not names:
        return
    shown = names if limit is None else names[:limit]
    tooltip = ui.tooltip().classes("bg-grey-9 text-white").style("max-width: 28rem")
    with tooltip, ui.row().classes("gap-1"):
        for name in shown:
            chip = ui.chip(name, color=None).props("dense square outline")
            chip.classes("ellipsis").mark(chip_marker)
            chip.style(f"color: {color or 'inherit'}")  # 枠と文字が currentColor になる
        if limit is not None and len(names) > limit:
            label = ui.label(f"+{len(names) - limit}件")
            if more_marker is not None:
                label.mark(more_marker)
