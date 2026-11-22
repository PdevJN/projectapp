"""アサイン専用画面(要望 168 段階 2)のメンバーのドラッグ用の JS と CSS(定数のみ)。

一覧のチップ(`data-assign-member`)を HTML5 の drag で掴み、割り当ての行のセル(`data-assign-cell`)に落とす。
結果(名前・週・日)だけを emitEvent で Python に返す。`dashboard_drag.py`と同じ作りで、`dataTransfer`の種類で
ほかの drag(ガントチャート・ダッシュボード)と見分ける。セルは再描画で作り直されるので、document に委譲する。
"""

ASSIGN_DROP_EVENT = "assign_drop_member"

ASSIGN_DRAG_CSS = """
[data-assign-member] { cursor: grab; }
.assign-drop-over { outline: 2px solid #1976d2; outline-offset: -2px; background: rgba(25, 118, 210, 0.12); }
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
})();
"""
