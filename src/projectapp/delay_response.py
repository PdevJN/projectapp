"""遅延対応(要望 132)の帯・ダイアログ・CSS。"""

from collections.abc import Callable
from datetime import date

from nicegui import ui

# 紫系。赤(遅れ)・黄(警告)・緑(取り戻せた)とは別系統。枠は太い点線で、通常の帯と形でも区別する。
DELAY_RESPONSE_CSS = """
:root { --delay-bg: #ede7f6; --delay-fg: #311b92; --delay-accent: #7e57c2; }
body.body--dark { --delay-bg: #2a2140; --delay-fg: #d1c4e9; --delay-accent: #b39ddb; }
.delay-band { background: var(--delay-bg); color: var(--delay-fg);
  border: 3px dotted var(--delay-accent); border-radius: 6px; padding: 4px 10px; }
.trial-ghost { border: 2px dashed var(--delay-accent);
  background: color-mix(in srgb, var(--delay-accent) 22%, transparent);
  border-radius: 4px; pointer-events: none; z-index: 2; }
.trial-chip { border: 1px dashed var(--delay-accent); background: var(--delay-bg);
  color: var(--delay-fg); font-size: 10px; padding: 0 3px; border-radius: 3px;
  white-space: nowrap; }
.confirmed-add { background: var(--delay-accent); color: #fff; font-size: 10px;
  padding: 0 4px; border-radius: 3px; white-space: nowrap; z-index: 2; }
.week-added { box-shadow: inset 4px 0 0 var(--delay-accent); }
.trial-origin { border-left: 2px solid var(--delay-accent); pointer-events: none; }
.trial-label { color: var(--delay-fg); font-size: 11px; white-space: nowrap; }
"""


def delay_band(
    count: int,
    recovered: int,
    on_confirm: Callable[[], object],
    on_clear: Callable[[], object],
) -> None:
    """試算中に、ガントチャートの上に出す帯。"""
    with ui.row().classes("delay-band items-center gap-3 w-full").mark("delay-band"):
        ui.label("遅延対応").classes("text-bold")
        ui.label(f"試算中: {count} 件の増員 / 取り戻せたタスク {recovered} 件").mark(
            "delay-band-text"
        )
        ui.space()
        ui.button("確定", on_click=lambda: on_confirm()).props("dense flat").mark(
            "delay-band-confirm"
        )
        ui.button("すべてやめる", on_click=lambda: on_clear()).props("dense flat").mark(
            "delay-band-clear"
        )


def trial_dialog(
    members: list[str], today: date, on_ok: Callable[[list[str], date], object]
) -> None:
    """増員を試すメンバーと開始日を選ぶ小さなダイアログ。"""
    with ui.dialog() as dialog, ui.card().mark("trial-dialog"):
        ui.label("増員を試す")
        chosen = ui.select(members, multiple=True, label="メンバー").mark(
            "trial-dialog-member"
        )
        start = ui.input("開始日", value=today.isoformat()).mark("trial-dialog-start")

        def ok() -> None:
            try:
                day = date.fromisoformat(str(start.value).strip().replace("/", "-"))
            except ValueError:
                ui.notify("開始日は 2026-11-09 の形で入れてください")
                return
            if not chosen.value:
                ui.notify("メンバーを選んでください")
                return
            dialog.close()
            on_ok(list(chosen.value), day)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("試す", on_click=ok).mark("trial-dialog-ok")
    dialog.open()


def open_trial_save_dialog(
    count: int,
    on_confirm: Callable[[], object],
    on_keep: Callable[[], object],
    on_discard: Callable[[], object],
) -> None:
    """保存時に試算が残っているときの確認。黙って確定しない。"""
    with ui.dialog() as dialog, ui.card().mark("trial-save-dialog"):
        ui.label(f"{count} 件の増員を確定して保存します")
        ui.label("確定すると、担当に「週ごとの担当」として保存されます。").classes(
            "text-caption"
        )

        def pick(action: Callable[[], object]) -> None:
            dialog.close()
            action()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark(
                "trial-save-cancel"
            )
            ui.button("試算を捨てて保存", on_click=lambda: pick(on_discard)).props(
                "flat"
            ).mark("trial-save-discard")
            ui.button("確定せずに保存", on_click=lambda: pick(on_keep)).props(
                "flat"
            ).mark("trial-save-keep")
            ui.button("確定して保存", on_click=lambda: pick(on_confirm)).mark(
                "trial-save-confirm"
            )
    dialog.open()
