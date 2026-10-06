"""ガントチャートのドラッグ操作用の JS と CSS(定数のみ)。

行は HTML5 の drag、バーは pointer イベント。要素の `data-*` 属性を読み、
結果だけを emitEvent で Python に返す。`render` が作り直されるので、document に委譲する。
"""

RESIZE_EDGE_PX = 6  # 名前の欄の右端の、幅の調整の掴み場所の幅
# 名前の欄の右端の掴み場所。疑似要素なので、要素は増えない(欄は position: sticky なので、基準になる)
NAME_RESIZE_CSS = f"""
.gantt-name-resizable::after {{
  content: ""; position: absolute; top: 0; right: 0; bottom: 0;
  width: {RESIZE_EDGE_PX}px; cursor: col-resize;
}}
"""

CHART_DRAG_CSS = """
.drop-before { box-shadow: inset 0 3px 0 0 #1976d2; }
.drop-after { box-shadow: inset 0 -3px 0 0 #1976d2; }
.drop-into { outline: 2px solid #1976d2; outline-offset: -2px; }
/* 左に固定した列は不透明な背景で行の線を隠すので、同じ線を列にも出す */
.drop-before > .gantt-sticky { box-shadow: inset 0 3px 0 0 #1976d2; }
.drop-after > .gantt-sticky { box-shadow: inset 0 -3px 0 0 #1976d2; }
.drop-into > .gantt-sticky { box-shadow: inset 2px 2px 0 0 #1976d2, inset 0 -2px 0 0 #1976d2; }
[data-drag-handle] { cursor: grab; }
"""

CHART_DRAG_JS = """
(() => {
  if (window.__ganttDragInstalled) return;
  window.__ganttDragInstalled = true;
  const section = (value) => (value === "top" ? null : Number(value));
  const ROW_TYPE = "application/x-gantt-row";  // 自分が始めた drag かを見分ける
  let source = null;
  let resize = null;  // 名前の欄の幅の調整中の状態

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
    if (resize) {  // 幅の調整中は、欄の drag(行の移動)を始めない
      event.preventDefault();
      return;
    }
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

  // 名前の欄の幅の調整。右端を掴み、--name-w を書き換えるだけにする(再描画しない)。離したときだけ幅を送る
  const content = () => document.querySelector("[data-chart-content]");
  const edgeCell = (event) => {  // ポインタが、名前の欄の右端にあれば、その欄を返す
    const cell = event.target.closest ? event.target.closest(".gantt-name-resizable") : null;
    const area = content();
    if (!cell || !area) return null;
    const right = cell.getBoundingClientRect().right;
    return event.clientX <= right && event.clientX >= right - Number(area.dataset.nameEdge) ? cell : null;
  };
  const setWidth = (area, value) => area.style.setProperty("--name-w", `${value}px`);
  const endResize = (restore) => {  // 掴んだ状態を捨てる。restore なら、掴む前の幅に戻す
    if (!resize) return null;
    const done = resize;
    resize = null;
    if (restore) setWidth(done.area, done.start);
    done.cell.draggable = done.draggable;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    return done;
  };

  document.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const cell = edgeCell(event);
    if (!cell) return;
    event.preventDefault();
    const area = content();
    const start = parseFloat(getComputedStyle(area).getPropertyValue("--name-w"));
    resize = { cell, area, x0: event.clientX, start, width: start, draggable: cell.draggable, cancelled: false };
    cell.draggable = false;  // 欄は行の移動の掴み場所でもあるので、幅の調整中は止める
    cell.setPointerCapture(event.pointerId);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("pointermove", (event) => {
    if (!resize) return;
    if (event.buttons === 0) {  // 放したのに pointerup が届かなかった
      endResize(true);
      return;
    }
    if (resize.cancelled) return;
    const min = Number(resize.area.dataset.nameMin);
    const max = Number(resize.area.dataset.nameMax);
    resize.width = Math.round(Math.min(Math.max(resize.start + event.clientX - resize.x0, min), max));
    setWidth(resize.area, resize.width);
  });

  document.addEventListener("pointerup", () => {
    const done = endResize(false);
    if (!done) return;
    suppressClick = true;  // 離したあとの click で、編集ダイアログが開かないようにする(動かさなくても)
    setTimeout(() => { suppressClick = false; }, 0);
    if (!done.cancelled && done.width !== done.start) {
      emitEvent("chart_name_width", { width: done.width });
    }
  });

  document.addEventListener("pointercancel", () => endResize(true));
  document.addEventListener("lostpointercapture", () => endResize(true));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !resize || resize.cancelled) return;
    resize.cancelled = true;  // 離すまで掴んだままにし、離したあとの click だけ打ち消す
    setWidth(resize.area, resize.start);
  });

  document.addEventListener("dblclick", (event) => {  // 右端のダブルクリックで、既定の幅へ戻す
    if (!edgeCell(event)) return;
    const area = content();
    const width = Number(area.dataset.nameDefault);
    setWidth(area, width);
    emitEvent("chart_name_width", { width });
  });
})();
"""
