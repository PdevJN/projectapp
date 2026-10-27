"""ダッシュボードのカードのドラッグ用の JS と CSS(定数のみ)。

取っ手(`data-dash-handle`)を HTML5 の drag で掴み、カード(`data-dash-card`)か末尾の落とし場所(`data-dash-end`)に落とす。
結果だけを emitEvent で Python に返す。カードは再描画で作り直されるので、document に委譲する。
ガントチャートの drag とは、dataTransfer の種類で見分ける。
"""

DASHBOARD_DRAG_CSS = """
.dash-drop-before { box-shadow: inset 4px 0 0 0 #1976d2; }
[data-dash-handle] { cursor: grab; }
"""

DASHBOARD_DRAG_JS = """
(() => {
  if (window.__dashboardDragInstalled) return;
  window.__dashboardDragInstalled = true;
  const TYPE = "application/x-dashboard-card";
  let source = null;
  const isOurs = (event) => Array.from((event.dataTransfer || {}).types || []).includes(TYPE);
  const clearMarks = () => {
    document.querySelectorAll(".dash-drop-before").forEach((el) => el.classList.remove("dash-drop-before"));
  };
  const dropTarget = (event) =>
    event.target.closest ? event.target.closest("[data-dash-card], [data-dash-end]") : null;

  document.addEventListener("dragstart", (event) => {
    const handle = event.target.closest ? event.target.closest("[data-dash-handle]") : null;
    if (!handle) return;
    source = handle.dataset.dashHandle;
    event.dataTransfer.setData(TYPE, source);
    event.dataTransfer.effectAllowed = "move";
  });

  document.addEventListener("dragover", (event) => {
    if (!isOurs(event)) return;
    clearMarks();
    const el = dropTarget(event);
    if (!el) return;
    event.preventDefault();
    el.classList.add("dash-drop-before");
  });

  document.addEventListener("drop", (event) => {
    if (!isOurs(event) || source === null) return;
    const el = dropTarget(event);
    clearMarks();
    if (!el) { source = null; return; }
    event.preventDefault();
    const message = { card: source, before: el.dataset.dashCard || null };
    source = null;
    emitEvent("dashboard_move_card", message);
  });

  document.addEventListener("dragend", () => { clearMarks(); source = null; });
})();
"""
