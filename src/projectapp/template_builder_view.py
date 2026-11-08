"""CSV の書式を、項目と区切りのチップを並べて組み立てる部品(要望 119)。

組み立て欄のチップは`ui.chip`で、ドラッグで並べ替え、パレットのチップをドラッグして足せる。
ドラッグ中は、落とす位置へチップを JS でその場に動かして見せる(落とした結果だけを`emitEvent`で Python に返す)。
パレットのチップはクリックでも足せる(選択中のチップの右隣。なければ末尾)。
書式の文字列との変換は`template_builder.py`の純粋関数。
"""

import itertools
from collections.abc import Callable, Sequence

from nicegui import ui
from nicegui.events import GenericEventArguments

from projectapp.csv_profile import FIELD_LABELS, CsvField, template_problem
from projectapp.template_builder import (
    SEPARATORS,
    Row,
    Token,
    add_row,
    insert_token,
    move_token,
    remove_row,
    remove_token,
    reorder_rows,
    template_of,
    token_label,
    tokens_of,
    used_rows,
)

_ids = itertools.count(1)

TEMPLATE_BUILDER_JS = """
(() => {
  if (window.__templateBuilderInstalled) return;
  window.__templateBuilderInstalled = true;
  const style = document.createElement("style");
  style.textContent = `
    [data-tb-item], [data-tb-palette] { cursor: grab; }
    .tb-ghost { outline: 2px dashed #1976d2; opacity: .7; }
    .tb-dragging { opacity: .45; }
    .tb-zone { min-height: 2.6rem; border: 1px dashed #9e9e9e; border-radius: 6px; padding: 4px 6px; }
  `;
  document.head.appendChild(style);

  let drag = null;
  const itemsOf = (box, extra) =>
    Array.from(box.querySelectorAll(":scope > [data-tb-item]" + (extra ? ", :scope > [data-tb-ghost]" : "")));
  const boxOf = (root) => root.querySelector("[data-tb-items]");

  // 並びが変わったとき、動いたチップが元の位置から滑って見えるようにする。
  const flip = (box, mutate) => {
    const nodes = itemsOf(box, true);
    const first = new Map(nodes.map((n) => [n, n.getBoundingClientRect()]));
    mutate();
    nodes.forEach((n) => {
      const a = first.get(n), b = n.getBoundingClientRect();
      const dx = a.left - b.left, dy = a.top - b.top;
      if (!dx && !dy) return;
      n.style.transition = "none";
      n.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        n.style.transition = "transform 120ms ease";
        n.style.transform = "";
      });
    });
  };

  const makeGhost = (source) => {
    const ghost = source.cloneNode(true);
    ghost.removeAttribute("data-tb-palette");
    ghost.removeAttribute("id");
    ghost.setAttribute("data-tb-ghost", "1");
    ghost.classList.add("tb-ghost");
    ghost.draggable = false;
    return ghost;
  };

  const place = (box, node, x, y) => {
    const list = itemsOf(box, true);
    const others = list.filter((n) => n !== node);
    let before = null;
    for (const other of others) {
      const r = other.getBoundingClientRect();
      if (y < r.top || (y <= r.bottom && x < r.left + r.width / 2)) { before = other; break; }
    }
    const target = before ? others.indexOf(before) : others.length;
    if (node.parentNode === box && list.indexOf(node) === target) return;
    flip(box, () => box.insertBefore(node, before));
  };

  const restore = () => {
    if (!drag) return;
    const box = boxOf(drag.root);
    if (drag.kind === "move") {
      flip(box, () => drag.order.forEach((n) => box.appendChild(n)));
    } else if (drag.ghost) {
      drag.ghost.remove();
      drag.ghost = null;
    }
  };

  document.addEventListener("dragstart", (event) => {
    const el = event.target.closest ? event.target.closest("[data-tb-item], [data-tb-palette]") : null;
    if (!el) return;
    const root = el.closest("[data-tb-root]");
    if (!root) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", "");
    if (el.hasAttribute("data-tb-item")) {
      drag = { root, kind: "move", node: el, order: itemsOf(boxOf(root)), from: Number(el.dataset.tbItem), dropped: false };
      setTimeout(() => el.classList.add("tb-dragging"), 0);
    } else {
      drag = { root, kind: "palette", key: el.dataset.tbPalette, source: el, ghost: null, dropped: false };
    }
  });

  const zoneOf = (event) => {
    if (!drag || !event.target.closest) return null;
    const zone = event.target.closest("[data-tb-zone]");
    return zone && zone.closest("[data-tb-root]") === drag.root ? zone : null;
  };

  // ライブで動かした直後はポインタの下の要素が変わる。そこで dragover が来る前に離しても落とせるよう、dragenter でも受ける。
  document.addEventListener("dragenter", (event) => {
    if (drag && zoneOf(event)) event.preventDefault();
  });

  document.addEventListener("dragover", (event) => {
    if (!drag || !zoneOf(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const box = boxOf(drag.root);
    if (drag.kind === "palette" && !drag.ghost) drag.ghost = makeGhost(drag.source);
    place(box, drag.kind === "move" ? drag.node : drag.ghost, event.clientX, event.clientY);
  });

  // relatedTarget は Chrome・WebKit で null になりやすいので、ポインタが枠の外に出たかを座標で見る。
  document.addEventListener("dragleave", (event) => {
    if (!drag || !event.target.closest) return;
    const zone = event.target.closest("[data-tb-zone]");
    if (!zone || zone.closest("[data-tb-root]") !== drag.root) return;
    const r = zone.getBoundingClientRect();
    const x = event.clientX, y = event.clientY;
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) restore();
  });

  document.addEventListener("drop", (event) => {
    if (!drag || !zoneOf(event)) return;
    event.preventDefault();
    const box = boxOf(drag.root);
    const rootId = drag.root.dataset.tbRoot;
    drag.dropped = true;
    if (drag.kind === "move") {
      emitEvent("template_builder", { root: rootId, op: "move", from: drag.from, to: itemsOf(box).indexOf(drag.node) });
    } else if (drag.ghost) {
      const index = itemsOf(box, true).indexOf(drag.ghost);
      emitEvent("template_builder", { root: rootId, op: "insert", key: drag.key, index });
    }
  });

  document.addEventListener("dragend", () => {
    if (!drag) return;
    const finished = drag;
    if (!finished.dropped) restore();
    if (finished.kind === "move") finished.node.classList.remove("tb-dragging");
    if (finished.ghost) setTimeout(() => finished.ghost && finished.ghost.remove(), 200);
    drag = null;
  });
})();
"""


class TemplateBuilder:
    """書式を、項目と区切りのチップの並びで組み立てる。`on_change`は、チップの操作で書式の文字列が変わるたびに呼ぶ。"""

    def __init__(
        self,
        template: str,
        fields: Sequence[CsvField],
        on_change: Callable[[str], None],
        *,
        header: str | None = None,
        on_header: Callable[[str], None] | None = None,
        mark: str = "tb",
    ) -> None:
        self.id = f"tb{next(_ids)}"
        self.fields = tuple(fields)
        self.on_change = on_change
        self.header = header  # None なら見出しのチップを出さない(取り込み)
        self.on_header = on_header
        self.mark = mark
        self.tokens: list[Token] = tokens_of(template) or []
        self.selected: int | None = None
        self.editing_header = False
        self.enabled = True
        self.composer = ui.refreshable(self._render_composer)
        self.header_part = ui.refreshable(self._render_header)
        self._palette_keys: dict[str, Token] = {}
        for field in self.fields:
            self._palette_keys[f"f:{field.value}"] = field
        for index, text in enumerate(SEPARATORS):
            self._palette_keys[f"s:{index}"] = text

    # ---- 組み立て ----
    def build(self) -> None:
        ui.run_javascript(TEMPLATE_BUILDER_JS)
        with (
            ui.column().classes("w-full gap-1").props(f"data-tb-root={self.id}") as root
        ):
            self.root = root
            ui.on("template_builder", self._on_event)
            self.composer()
            self._palette("項目", [(f"f:{f.value}", f) for f in self.fields], "pal")
            self._palette(
                "区切り",
                [(f"s:{i}", text) for i, text in enumerate(SEPARATORS)],
                "sep",
            )
            with ui.row().classes("items-center gap-2 no-wrap"):
                self.custom = (
                    ui.input(placeholder="区切りの文字を入力")
                    .props("dense outlined")
                    .classes("w-48")
                    .mark(f"{self.mark}-custom")
                    .on("keydown.enter", lambda _: self.add_custom())
                )
                ui.button("追加", on_click=self.add_custom).props("flat dense").mark(
                    f"{self.mark}-custom-add"
                )
            self.caption = (
                ui.label()
                .classes("text-negative text-caption")
                .mark(f"{self.mark}-problem")
            )
        self._caption()
        self.set_enabled(self.enabled)

    def _palette(
        self, title: str, entries: list[tuple[str, Token]], prefix: str
    ) -> None:
        with ui.row().classes("items-center gap-1"):
            ui.label(title).classes("text-caption text-grey w-12")
            for key, token in entries:
                name = token.value if isinstance(token, CsvField) else key[2:]
                chip = (
                    ui.chip(
                        token_label(token),
                        color="primary" if isinstance(token, CsvField) else "grey-4",
                        text_color="white" if isinstance(token, CsvField) else "black",
                    )
                    .props(f"draggable=true data-tb-palette={key}")
                    .mark(f"{self.mark}-{prefix}-{name}")
                )
                chip.on("click", lambda _, k=key: self.add(self._palette_keys[k]))

    def _render_composer(self) -> None:
        with (
            ui.row()
            .classes("items-center w-full gap-1 tb-zone")
            .props("data-tb-zone=1")
        ):
            if self.header is not None:
                self.header_part()
            with ui.row().classes("items-center gap-1 grow").props("data-tb-items=1"):
                for index, token in enumerate(self.tokens):
                    self._item(index, token)
            if not self.tokens:
                ui.label("ここに項目と区切りをドロップ").classes(
                    "text-grey text-caption"
                )

    def _item(self, index: int, token: Token) -> None:
        field = isinstance(token, CsvField)
        chosen = self.selected == index
        chip = (
            ui.chip(
                token_label(token),
                removable=True,
                color="accent" if chosen else ("primary" if field else "grey-4"),
                text_color="white" if (field or chosen) else "black",
                on_value_change=lambda e, i=index: e.value is False and self.remove(i),
            )
            .props(f"draggable=true data-tb-item={index}")
            .mark(f"{self.mark}-item-{index}")
        )
        chip.on("click", lambda _, i=index: self.select(i))

    def _render_header(self) -> None:
        if self.editing_header:
            box = (
                ui.input(value=self.header or "", placeholder="列の見出し")
                .props("dense outlined autofocus")
                .classes("w-40")
                .mark(f"{self.mark}-header-input")
            )
            box.on("keydown.enter", lambda _: self.commit_header(box.value))
            box.on("keydown.escape", lambda _: self.cancel_header())
            box.on("blur", lambda _: self.commit_header(box.value))
        else:
            label = f"見出し: {self.header}" if self.header else "見出しなし"
            chip = (
                ui.chip(label, icon="title", color="amber-3", text_color="black")
                .mark(f"{self.mark}-header")
                .tooltip("ダブルクリックで見出しを編集")
            )
            chip.on("dblclick", lambda _: self.start_header())

    # ---- 見出し ----
    def start_header(self) -> None:
        if not self.enabled:
            return
        self.editing_header = True
        self.header_part.refresh()

    def commit_header(self, value: str | None) -> None:
        if not self.editing_header:
            return
        self.editing_header = False
        self.header = str(value or "").strip()
        self.header_part.refresh()
        if self.on_header:
            self.on_header(self.header)

    def cancel_header(self) -> None:
        self.editing_header = False
        self.header_part.refresh()

    def set_header(self, header: str) -> None:
        if self.header is None or header == self.header:
            return
        self.header = header
        self.editing_header = False
        self.header_part.refresh()

    # ---- 操作 ----
    def add(self, token: Token, index: int | None = None) -> None:
        """パレットのクリック(選択中の右隣か末尾)とドロップ(`index`)の両方がここへ来る。"""
        if not self.enabled:
            return
        if index is None and self.selected is not None:
            index = self.selected + 1
        self._set(insert_token(self.tokens, token, index))

    def add_custom(self) -> None:
        text = str(self.custom.value or "")
        if not text or "{" in text or "}" in text:
            return
        self.custom.set_value("")
        self.add(text)

    def select(self, index: int) -> None:
        self.selected = None if self.selected == index else index
        self.composer.refresh()

    def remove(self, index: int) -> None:
        if self.enabled:
            self._set(remove_token(self.tokens, index))

    def _set(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.selected = None
        self._changed()

    def _changed(self) -> None:
        self.composer.refresh()
        self._caption()
        self.on_change(template_of(self.tokens))

    def _caption(self) -> None:
        text = template_of(self.tokens)
        self.caption.set_text((template_problem(text) or "") if self.tokens else "")

    def _on_event(self, event: GenericEventArguments) -> None:
        args = event.args if isinstance(event.args, dict) else {}
        if args.get("root") != self.id or not self.enabled:
            return
        if args.get("op") == "move":
            source, target = args.get("from"), args.get("to")
            if isinstance(source, int) and isinstance(target, int):
                self._set(move_token(self.tokens, source, target))
                return
        elif args.get("op") == "insert":
            token = self._palette_keys.get(str(args.get("key")))
            index = args.get("index")
            if token is not None and isinstance(index, int):
                self.add(token, index)
                return
        self.composer.refresh()  # 画面が先に動いているので、元の並びへ戻す

    # ---- 外から ----
    def set_template(self, template: str) -> None:
        """文字列の書式が外で直されたとき、チップの並びを作り直す(読めない書式は直るまで変えない)。"""
        tokens = tokens_of(template)
        if tokens is None or template_of(self.tokens) == template:
            return
        self.tokens = tokens
        self.selected = None
        self.composer.refresh()
        self._caption()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.root.classes(remove="pointer-events-none opacity-50")
        else:
            self.root.classes("pointer-events-none opacity-50")


class ColumnBuilder:
    """書き出しの列(項目と見出し)を、チップの並びで組み立てる(`列の詳細設定`)。

    `rows`(`{"field", "use", "header"}`の一覧。ダイアログが持つもの)をその場で書き換え、変わるたびに`on_change`を呼ぶ。
    チップは使う列の順。ダブルクリックで見出しをその場で編集、ドラッグで並べ替え、×で使わない列にする。
    パレットには、使っていない項目が並ぶ。
    """

    def __init__(
        self,
        rows: list[Row],
        fields: Sequence[CsvField],
        on_change: Callable[[], None],
        *,
        mark: str = "cb",
    ) -> None:
        self.id = f"tb{next(_ids)}"
        self.rows = rows
        self.fields = tuple(fields)
        self.on_change = on_change
        self.mark = mark
        self.editing: int | None = None  # 見出しを編集中のチップの番号
        self.enabled = True
        self.composer = ui.refreshable(self._render_composer)
        self.palette = ui.refreshable(self._render_palette)

    def build(self) -> None:
        ui.run_javascript(TEMPLATE_BUILDER_JS)
        with (
            ui.column().classes("w-full gap-1").props(f"data-tb-root={self.id}") as root
        ):
            self.root = root
            ui.on("template_builder", self._on_event)
            self.composer()
            self.palette()
        self.set_enabled(self.enabled)

    def refresh(self) -> None:
        """`rows`が外で作り直されたとき(プロファイルの切り替え)。"""
        self.editing = None
        self.composer.refresh()
        self.palette.refresh()

    def _render_composer(self) -> None:
        with (
            ui.row()
            .classes("items-center w-full gap-1 tb-zone")
            .props("data-tb-zone=1")
        ):
            with ui.row().classes("items-center gap-1 grow").props("data-tb-items=1"):
                for index, row in enumerate(used_rows(self.rows)):
                    self._item(index, row)
            if not used_rows(self.rows):
                ui.label("ここに項目をドロップ").classes("text-grey text-caption")

    def _item(self, index: int, row: Row) -> None:
        field: CsvField = row["field"]
        if self.editing == index:
            box = (
                ui.input(value=str(row["header"]), placeholder="列の見出し")
                .props(f"dense outlined autofocus data-tb-item={index}")
                .classes("w-40")
                .mark(f"{self.mark}-header-input")
            )
            box.on("keydown.enter", lambda _, i=index: self.commit(i, box.value))
            box.on("keydown.escape", lambda _: self.cancel())
            box.on("blur", lambda _, i=index: self.commit(i, box.value))
            return
        header = str(row["header"])
        label = FIELD_LABELS[field] + (
            f" → {header}" if header != FIELD_LABELS[field] else ""
        )
        chip = (
            ui.chip(
                label,
                removable=True,
                color="primary",
                text_color="white",
                on_value_change=lambda e, i=index: e.value is False and self.remove(i),
            )
            .props(f"draggable=true data-tb-item={index}")
            .mark(f"{self.mark}-item-{field.value}")
            .tooltip("ダブルクリックで見出しを編集")
        )
        chip.on("dblclick", lambda _, i=index: self.start(i))

    def _render_palette(self) -> None:
        with ui.row().classes("items-center gap-1"):
            ui.label("項目").classes("text-caption text-grey w-12")
            used = {r["field"] for r in used_rows(self.rows)}
            for field in self.fields:
                if field in used:
                    continue
                chip = (
                    ui.chip(FIELD_LABELS[field], color="grey-4", text_color="black")
                    .props(f"draggable=true data-tb-palette=f:{field.value}")
                    .mark(f"{self.mark}-pal-{field.value}")
                )
                chip.on("click", lambda _, f=field: self.add(f))

    # ---- 操作 ----
    def start(self, index: int) -> None:
        if self.enabled:
            self.editing = index
            self.composer.refresh()

    def commit(self, index: int, value: str | None) -> None:
        if self.editing != index:
            return
        self.editing = None
        used = used_rows(self.rows)
        if 0 <= index < len(used):
            used[index]["header"] = str(value or "").strip()
        self._changed()

    def cancel(self) -> None:
        self.editing = None
        self.composer.refresh()

    def add(self, field: CsvField, index: int | None = None) -> None:
        if self.enabled:
            add_row(self.rows, field, index)
            self._changed()

    def remove(self, index: int) -> None:
        if self.enabled:
            remove_row(self.rows, index)
            self._changed()

    def _changed(self) -> None:
        self.composer.refresh()
        self.palette.refresh()
        self.on_change()

    def _on_event(self, event: GenericEventArguments) -> None:
        args = event.args if isinstance(event.args, dict) else {}
        if args.get("root") != self.id or not self.enabled:
            return
        self.editing = None
        if args.get("op") == "move":
            source, target = args.get("from"), args.get("to")
            if isinstance(source, int) and isinstance(target, int):
                reorder_rows(self.rows, source, target)
                self._changed()
                return
        elif args.get("op") == "insert":
            key, index = str(args.get("key")), args.get("index")
            field = next((f for f in self.fields if f"f:{f.value}" == key), None)
            if field is not None and isinstance(index, int):
                self.add(field, index)
                return
        self.composer.refresh()  # 画面が先に動いているので、元の並びへ戻す

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.root.classes(remove="pointer-events-none opacity-50")
        else:
            self.root.classes("pointer-events-none opacity-50")
