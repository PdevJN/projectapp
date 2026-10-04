"""ガントチャートのドラッグ操作用の JS と CSS(定数のみ)。

行は HTML5 の drag、バーは pointer イベント。要素の `data-*` 属性を読み、
結果だけを emitEvent で Python に返す。`render` が作り直されるので、document に委譲する。
"""

CHART_DRAG_CSS = """
.drop-before { box-shadow: inset 0 3px 0 0 #1976d2; }
.drop-after { box-shadow: inset 0 -3px 0 0 #1976d2; }
.drop-into { outline: 2px solid #1976d2; outline-offset: -2px; }
[data-drag-handle] { cursor: grab; }
"""

CHART_DRAG_JS = """
(() => {
  if (window.__ganttDragInstalled) return;
  window.__ganttDragInstalled = true;
  const section = (value) => (value === "top" ? null : Number(value));
  let source = null;

  const clearMarks = () => {
    document.querySelectorAll(".drop-before, .drop-after, .drop-into").forEach((el) => {
      el.classList.remove("drop-before", "drop-after", "drop-into");
    });
  };
  const upperHalf = (el, event) => {
    const rect = el.getBoundingClientRect();
    return event.clientY < rect.top + rect.height / 2;
  };
  const target = (event) => (event.target.closest ? event.target.closest("[data-drop]") : null);

  document.addEventListener("dragstart", (event) => {
    const handle = event.target.closest ? event.target.closest("[data-drag-handle]") : null;
    if (!handle) return;
    source = [section(handle.dataset.si), Number(handle.dataset.ti)];
    event.dataTransfer.effectAllowed = "copyMove";
    event.dataTransfer.setData("text/plain", handle.textContent || "");
  });

  document.addEventListener("dragover", (event) => {
    const el = source ? target(event) : null;
    if (!el) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = event.altKey ? "copy" : "move";
    clearMarks();
    if (el.dataset.drop === "row") {
      el.classList.add(upperHalf(el, event) ? "drop-before" : "drop-after");
    } else {
      el.classList.add("drop-into");
    }
  });

  document.addEventListener("drop", (event) => {
    const el = source ? target(event) : null;
    if (!el) return;
    event.preventDefault();
    const index = el.dataset.drop === "row"
      ? Number(el.dataset.ti) + (upperHalf(el, event) ? 0 : 1)
      : Number(el.dataset.count);
    const message = {
      src: source,
      dst: [section(el.dataset.si), index],
      copy: event.altKey,
    };
    clearMarks();
    source = null;
    emitEvent("chart_move", message);
  });

  document.addEventListener("dragend", () => {
    clearMarks();
    source = null;
  });
})();
"""
