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
  const ROW_TYPE = "application/x-gantt-row";  // 自分が始めた drag かを見分ける
  let source = null;

  const isRowDrag = (event) => Array.from((event.dataTransfer || {}).types || []).includes(ROW_TYPE);
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
    event.dataTransfer.setData(ROW_TYPE, "1");
    event.dataTransfer.setData("text/plain", handle.textContent || "");
  });

  document.addEventListener("dragover", (event) => {
    const el = source && isRowDrag(event) ? target(event) : null;
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
    const el = source && isRowDrag(event) ? target(event) : null;
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

  // バーの横移動。1日分の列幅に吸着し、放したときに日数だけを送る。
  const MOVE_THRESHOLD_PX = 4;
  const RESET_MS = 1500;  // サーバーが受け付けず、再描画されなかったときの保険
  let bar = null;
  let suppressClick = false;

  const abortBar = () => {  // 送らずに、つかんだ状態を捨てる
    if (!bar) return;
    bar.el.style.transform = "";
    bar = null;
  };

  document.addEventListener("pointerdown", (event) => {
    const el = event.target.closest ? event.target.closest("[data-bar]") : null;
    if (!el || event.button !== 0) return;
    abortBar();
    bar = {
      el, x0: event.clientX, width: Number(el.dataset.dayWidth),
      minDays: Number(el.dataset.minDays),  // 基準日より前へは動かさない
      moved: false, cancelled: false, days: 0,
    };
    el.setPointerCapture(event.pointerId);
  });

  document.addEventListener("pointermove", (event) => {
    if (!bar) return;
    if (event.buttons === 0) {  // 放したのに pointerup が届かなかった
      abortBar();
      return;
    }
    if (bar.cancelled) return;
    const dx = event.clientX - bar.x0;
    if (!bar.moved && Math.abs(dx) < MOVE_THRESHOLD_PX) return;
    bar.moved = true;
    bar.days = Math.max(Math.round(dx / bar.width), bar.minDays);
    bar.el.style.transform = `translateX(${bar.days * bar.width}px)`;
  });

  document.addEventListener("pointerup", () => {
    if (!bar) return;
    const done = bar;
    bar = null;
    if (!done.moved) {  // 動かしていなければ、ふつうのクリック
      done.el.style.transform = "";
      return;
    }
    suppressClick = true;  // 動かしたあとの click で編集ダイアログが開かないようにする
    setTimeout(() => { suppressClick = false; }, 0);
    if (done.cancelled || done.days === 0) {
      done.el.style.transform = "";
      return;
    }
    // 再描画で要素が置き換わるまで位置を保つ(元に戻って見えないように)。残っていたら戻す
    setTimeout(() => { if (done.el.isConnected) done.el.style.transform = ""; }, RESET_MS);
    emitEvent("chart_shift", {
      si: section(done.el.dataset.si), ti: Number(done.el.dataset.ti), days: done.days,
    });
  });

  document.addEventListener("pointercancel", abortBar);
  document.addEventListener("lostpointercapture", abortBar);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !bar) return;
    bar.cancelled = true;
    bar.el.style.transform = "";
  });

  document.addEventListener("click", (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);
})();
"""
