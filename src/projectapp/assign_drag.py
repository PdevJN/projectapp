"""アサイン専用画面(要望 168 段階 2)のメンバーのドラッグ用の JS と CSS(定数のみ)。

一覧のチップ(`data-assign-member`)を HTML5 の drag で掴み、割り当ての行のセル(`data-assign-cell`)に落とす。
結果(名前・週・日)だけを emitEvent で Python に返す。`dashboard_drag.py`と同じ作りで、`dataTransfer`の種類で
ほかの drag(ガントチャート・ダッシュボード)と見分ける。セルは再描画で作り直されるので、document に委譲する。
"""

ASSIGN_DROP_EVENT = "assign_drop_member"
ASSIGN_SELECT_EVENT = "assign_select_range"

ASSIGN_DRAG_CSS = """
[data-assign-member] { cursor: grab; }
.assign-chip { position: relative; width: 18px; height: 18px; flex: none; }
.assign-chip .assign-remove { position: absolute; top: -5px; right: -5px; opacity: 0; min-width: 0; min-height: 0; width: 12px; height: 12px; padding: 0; background: rgba(0,0,0,0.65); color: #fff; }
.assign-chip:hover .assign-remove { opacity: 1; }
.assign-rate-badge { position: absolute; right: -3px; bottom: -4px; font-size: 8px; line-height: 9px; padding: 0 2px; border-radius: 3px; background: rgba(0,0,0,0.65); color: #fff; pointer-events: none; }
.assign-drop-over { outline: 2px solid #1976d2; outline-offset: -2px; background: rgba(25, 118, 210, 0.12); }
[data-assign-cell] { user-select: none; }
.assign-select-over, .assign-selected { outline: 2px solid #ff9800; outline-offset: -2px; background: rgba(255, 152, 0, 0.18); }
"""

ASSIGN_DRAG_JS = """
(() => {
  if (window.__assignDragInstalled) return;
  window.__assignDragInstalled = true;
  const TYPE = "application/x-assign-member";
  let source = null;
  const isOurs = (event) => Array.from((event.dataTransfer || {}).types || []).includes(TYPE);
  const clearMarks = () => {
    document.querySelectorAll(".assign-drop-over").forEach((el) => el.classList.remove("assign-drop-over"));
  };
  const dropTarget = (event) =>
    event.target.closest ? event.target.closest("[data-assign-cell]") : null;

  document.addEventListener("dragstart", (event) => {
    const chip = event.target.closest ? event.target.closest("[data-assign-member]") : null;
    if (!chip) return;
    source = chip.dataset.assignMember;
    event.dataTransfer.setData(TYPE, source);
    event.dataTransfer.effectAllowed = "copy";
  });

  document.addEventListener("dragover", (event) => {
    if (!isOurs(event)) return;
    clearMarks();
    const el = dropTarget(event);
    if (!el) return;
    event.preventDefault();
    el.classList.add("assign-drop-over");
  });

  document.addEventListener("drop", (event) => {
    if (!isOurs(event) || source === null) return;
    const el = dropTarget(event);
    clearMarks();
    if (!el) { source = null; return; }
    event.preventDefault();
    const day = el.dataset.day;
    const message = {
      name: source,
      week: Number(el.dataset.week),
      day: day === undefined || day === "" ? null : Number(day),
    };
    source = null;
    emitEvent("assign_drop_member", message);
  });

  document.addEventListener("dragend", () => { clearMarks(); source = null; });

  // 範囲の選択(要望 168 段階 3b): 割り当ての行のセルを、マウスでなぞる
  const cellOf = (event) =>
    event.target.closest ? event.target.closest("[data-assign-cell]") : null;
  const blocked = (event) =>
    event.target.closest
      ? event.target.closest(".assign-chip, button, [data-assign-member]")
      : null;
  const clearSwipe = () => {
    document
      .querySelectorAll(".assign-select-over")
      .forEach((el) => el.classList.remove("assign-select-over"));
  };
  const place = (el) => ({
    week: Number(el.dataset.week),
    day: el.dataset.day === undefined || el.dataset.day === "" ? null : Number(el.dataset.day),
  });
  let swipeFrom = null;
  let swiping = false;

  document.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    const cell = cellOf(event);
    if (!cell || blocked(event)) return;
    swipeFrom = cell;
    swiping = false;
  });

  document.addEventListener("mouseover", (event) => {
    if (swipeFrom === null) return;
    const cell = cellOf(event);
    if (!cell) return;
    if (cell !== swipeFrom) swiping = true;
    clearSwipe();
    const cells = Array.from(document.querySelectorAll("[data-assign-cell]"));
    let a = cells.indexOf(swipeFrom);
    let b = cells.indexOf(cell);
    if (a < 0 || b < 0) return;
    if (a > b) [a, b] = [b, a];
    cells.slice(a, b + 1).forEach((el) => el.classList.add("assign-select-over"));
  });

  document.addEventListener("mouseup", (event) => {
    if (swipeFrom === null) return;
    const start = swipeFrom;
    const moved = swiping;
    swipeFrom = null;
    swiping = false;
    clearSwipe();
    const cell = cellOf(event);
    if (!moved || !cell || cell === start) return;
    emitEvent("assign_select_range", { first: place(start), last: place(cell) });
  });
})();
"""
