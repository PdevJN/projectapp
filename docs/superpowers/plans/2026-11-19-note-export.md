# メモの書き出し・取り込み(要望 153) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクのメモを、CSV/TSV の`メモ`列(プレーンテキスト・改行は`\n`)として書き出し、取り込みでタスクのメモに戻せるようにする。

**Architecture:** 既存の列の仕組み(`CsvField`・`ColumnBuilder`)に`CsvField.NOTE`を足すだけで、書き出しダイアログの選択と並べ替えが使える。HTML⇔セルの変換は`notes.py`の純粋関数にする。取り込みは`CsvImport.notes`(新タスク id → HTML)を返し、`views`が保存する。

**Tech Stack:** Python 3.13・NiceGUI・pytest(`uv run pytest -m smoke`)・`uvx ruff`・`uvx ty check src`

**Spec:** `docs/superpowers/specs/2026-11-19-note-export-design.md`(Task 1 で、下の「設計書からの変更」を反映する)

## 設計書からの変更(利用者の確認が要る)

設計書の`pending_notes`(保存まで、メモをメモリに持つ)は**やめて、取り込み時にすぐ`notes/<プロジェクト名>/`へ書く**。理由:

- 保存前の新規プロジェクトのメモは、今もすぐ`notes/<名前>/`へ書き、`save_as_new`が`notes.copy_project`で新しい名前へコピーしている。同じ流れに乗れば、🗒️・メモのペイン・ごみ箱が、変更なしで動く。
- 設計書が避けたかった「同名の既存プロジェクトのメモの上書き」は、メモのファイル名がタスク id(ランダム)なので起きない。
- 代償: 取り込んだあと保存せずに捨てると、`notes/<CSV のファイル名>/`に使われないメモが残る。害はなく、同名のプロジェクトを開いても、タスク id が違うので出ない。

## Global Constraints

- 言語は日本語(コメント・ダイアログ・通知)。Python 3.13 以上。型ヒントは全関数に付ける。コメントは 3 行以内
- ファイル形式の`version`は 23 のまま(`project`のファイルは変えない)
- 既定ではメモを出さない(既定のプロファイル・Smartsheet の列に`メモ`を入れない)
- メモの改行は、すべて文字の`\n`(バックスラッシュと n)に置き換える。`\`は`\\`
- 取り込んだメモは必ず`notes.sanitize`を通す(`notes.save`が通す)。セルを HTML のタグとして読まない
- PlantUML・担当者向けファイルはメモを出さない(変更しない)
- 実装ごとに`uv run pytest -m smoke`。最後に`uvx ruff check`・`uvx ruff format src test`・`uvx ty check src`(ty の既存 9 件は無視)

## Review Focus

- メモが`\n`の文字を含む(書き出しで`\\n`になり、取り込みで文字の`\n`に戻る)
- メモに`<script>`・`<`・`&`を含む(取り込みで無害化され、書き出しで文字として残る)
- メモのないタスクだけ・全タスクメモなし(`メモ`列は空欄。取り込みで`notes`は空)
- `メモ`列だけに値があり、ほかの値がない行(セクション扱い。メモは付けない)
- 書き出し直前に、メモのペインで入力中の内容(保存前)がある(書き出しに含まれる)

---

### Task 1: メモ⇔セルの変換と設計書の更新

**Files:**
- Modify: `src/projectapp/notes.py`(`_Plain`・`MAX_NOTE_TEXT`・`to_cell`・`from_cell`を足す)
- Modify: `test/test_notes.py`
- Modify: `docs/superpowers/specs/2026-11-19-note-export-design.md`(「保存前の扱い」)

**Interfaces:**
- Produces: `notes.to_cell(html: str) -> str`、`notes.from_cell(text: str) -> str`、`notes.MAX_NOTE_TEXT: int = 10000`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_notes.py`の末尾に足す。ファイル先頭に`from projectapp import notes`があることを確かめる)

```python
def test_to_cell_turns_blocks_into_escaped_newlines() -> None:
    assert notes.to_cell("<p>一行目</p><p>二行目</p>") == "一行目\\n二行目"
    assert notes.to_cell("<p>a<br>b</p>") == "a\\nb"
    assert notes.to_cell("<ul><li>x</li><li>y</li></ul>") == "- x\\n- y"


def test_to_cell_keeps_text_and_escapes_the_backslash() -> None:
    assert notes.to_cell("<p>a&lt;b&gt; &amp; C:\\temp</p>") == "a<b> & C:\\\\temp"
    assert notes.to_cell("<p>文字の\\n</p>") == "文字の\\\\n"


def test_to_cell_of_a_blank_note_is_empty() -> None:
    assert notes.to_cell("") == ""
    assert notes.to_cell("<p><br></p>") == ""
    assert notes.to_cell("<p>&nbsp;</p>") == ""


def test_to_cell_drops_scripts() -> None:
    assert notes.to_cell("<p>安全</p><script>alert(1)</script>") == "安全"


def test_from_cell_makes_a_paragraph_per_line() -> None:
    assert notes.from_cell("一行目\\n二行目") == "<p>一行目</p><p>二行目</p>"
    assert notes.from_cell("") == ""
    assert notes.from_cell("   ") == ""


def test_from_cell_never_reads_the_text_as_html() -> None:
    html = notes.from_cell("<script>alert(1)</script><b>x</b> & y")
    assert "<script" not in html and "<b>" not in html
    assert notes.to_cell(html) == "<script>alert(1)</script><b>x</b> & y"


def test_from_cell_restores_a_literal_backslash_n() -> None:
    html = notes.from_cell("文字の\\\\n と C:\\temp")
    assert notes.to_cell(html) == "文字の\\\\n と C:\\\\temp"


def test_from_cell_cuts_a_very_long_note() -> None:
    html = notes.from_cell("あ" * (notes.MAX_NOTE_TEXT + 500))
    assert notes.to_cell(html).count("あ") == notes.MAX_NOTE_TEXT


def test_the_cell_round_trip_is_stable() -> None:
    first = notes.to_cell("<p>経緯</p><p>a\\nb &lt;x&gt;</p><ul><li>c</li></ul>")
    assert notes.to_cell(notes.from_cell(first)) == first
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_notes.py -k "cell" -q`
Expected: FAIL(`module 'projectapp.notes' has no attribute 'to_cell'`)

- [ ] **Step 3: 実装する**(`notes.py`。`is_blank`の定義の後ろに足す)

```python
MAX_NOTE_TEXT = 10000  # 取り込む 1 件のメモの文字数の上限
_BLOCKS = frozenset(
    "p div ul ol li h1 h2 h3 h4 h5 h6 blockquote pre hr br".split()
)  # 前後で改行にするタグ
_ESCAPED = re.compile(r"\\([\\n])")


class _Plain(HTMLParser):
    """メモの HTML を、タグを落としたテキストにする(ブロックの境目は改行、リストの項目は`- `)。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def to_cell(html: str) -> str:
    """CSV のセルに入れる 1 行のテキスト。タグを落とし、`\\`を`\\\\`に、改行を文字の`\\n`にする。空のメモは空文字。"""
    if is_blank(html):
        return ""
    parser = _Plain()
    parser.feed(sanitize(html))
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ").replace("\r", "")
    lines = [line.rstrip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines).replace("\\", "\\\\").replace("\n", "\\n")


def from_cell(text: str) -> str:
    """`to_cell`の逆。`\\n`を改行に、`\\\\`を`\\`に戻し、1 行ごとの段落にする。タグとしては読まない。空なら空文字。"""
    text = text.strip()
    if not text:
        return ""
    plain = _ESCAPED.sub(lambda m: "\n" if m.group(1) == "n" else "\\", text)
    lines = plain[:MAX_NOTE_TEXT].split("\n")
    body = "".join(f"<p>{escape(line)}</p>" if line.strip() else "<p><br></p>" for line in lines)
    return sanitize(body)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_notes.py -q`
Expected: PASS。`test_the_cell_round_trip_is_stable`が落ちるなら、`sanitize`が`&lt;`をどう戻すかを確かめ、`_Plain`の実体参照の扱いを直す。

- [ ] **Step 5: 設計書を更新する**(`docs/superpowers/specs/2026-11-19-note-export-design.md`の`### 保存前の扱い(`views`)`の節を、次に置き換える)

```markdown
### 取り込んだあとの扱い(`views`)

- 保存前の新規プロジェクトのメモは、今もすぐ`notes/<名前>/`へ書き、`save_as_new`が`notes.copy_project`で新しい名前へコピーする。取り込んだメモも、同じ流れに乗せる(`apply_csv_import`が、`show_project`の前に`notes.save`で書く)
- 同名の既存プロジェクトのメモは、ファイル名がタスク id(ランダム)なので、上書きされない
- 保存せずに捨てたとき、`notes/<CSV のファイル名>/`に使われないメモが残る(害はない)
```

また、`### 変換`の「取り込みの上限」の行を「メモ 1 件は`notes.MAX_NOTE_TEXT`(10000 文字)で切り詰める」に直し、「テスト」の`pending_notes`の行を「`apply_csv_import`が、取り込んだメモを`notes/<名前>/`に書く」に直す。

- [ ] **Step 6: smoke と commit**

```bash
uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test
git add src/projectapp/notes.py test/test_notes.py docs/superpowers/specs/2026-11-19-note-export-design.md
git commit -m "feat: メモと CSV のセルの変換を足す(要望 153)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `メモ`の項目を足す

**Files:**
- Modify: `src/projectapp/csv_profile.py`(`CsvField`・`FIELD_LABELS`・`ALIASES`)
- Modify: `test/test_csv_profile.py`

**Interfaces:**
- Produces: `CsvField.NOTE`(値`"note"`)。`FIELD_LABELS[CsvField.NOTE] == "メモ"`。`EXPORT_FIELDS`・`IMPORT_FIELDS`に含まれる

- [ ] **Step 1: 失敗するテストを書く**(`test/test_csv_profile.py`の末尾。import に`EXPORT_FIELDS`・`IMPORT_FIELDS`・`SMARTSHEET`・`guess_columns`・`profile_from_config`・`profile_to_config`・`CsvColumn`・`CsvProfile`・`CsvField`が無ければ足す)

```python
def test_the_note_field_is_exported_and_imported_but_not_in_smartsheet() -> None:
    assert CsvField.NOTE in EXPORT_FIELDS and CsvField.NOTE in IMPORT_FIELDS
    assert CsvField.NOTE not in {c.field for c in SMARTSHEET.columns}


def test_the_guess_finds_a_note_column_by_alias() -> None:
    for header in ("メモ", "ノート", "Note", "NOTES"):
        found = guess_columns(["タスク名", header])
        assert [c.field for c in found] == [CsvField.TITLE, CsvField.NOTE]


def test_a_profile_with_the_note_column_survives_the_config() -> None:
    profile = CsvProfile(
        "メモ付き",
        (CsvColumn(CsvField.TITLE, "タスク名"), CsvColumn(CsvField.NOTE, "メモ")),
    )
    assert profile_from_config(profile_to_config(profile)) == profile
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_csv_profile.py -k "note" -q`
Expected: FAIL(`AttributeError: NOTE`)

- [ ] **Step 3: 実装する**(`csv_profile.py`)

`CsvField`の`SECTION = "section"`の次に`NOTE = "note"`を足す。`FIELD_LABELS`に`CsvField.NOTE: "メモ",`を足す。`ALIASES`に、`CsvField.SECTION`の次へ`CsvField.NOTE: ("メモ", "ノート", "備考メモ", "note", "notes"),`を足す(`header_key`で小文字・空白除去されるので、`Note`・`NOTES`も一致する)。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_csv_profile.py test/test_csv_dialog.py test/test_csv_import.py test/test_csv_export.py -q`
Expected: PASS(`FIELD_LABELS[f]`を全項目に引く場所が、`メモ`を持つので落ちない)

- [ ] **Step 5: smoke と commit**

```bash
uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test
git add src/projectapp/csv_profile.py test/test_csv_profile.py
git commit -m "feat: CSV の項目にメモを足す(要望 153)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 書き出しにメモの列を出す

**Files:**
- Modify: `src/projectapp/csv_export.py`(`build_table`)
- Modify: `test/test_csv_export.py`

**Interfaces:**
- Consumes: `notes.to_cell(html) -> str`(Task 1)、`CsvField.NOTE`(Task 2)
- Produces: `build_table(project, holidays, profile, references=None, note_for: Callable[[str], str | None] | None = None) -> TableExport`。`note_for(タスク id)`はメモの HTML か None

- [ ] **Step 1: 失敗するテストを書く**(`test/test_csv_export.py`の末尾。`rows()`・`Task`・`Project`・`Section`は既存の import を使う)

```python
NOTE_PROFILE = CsvProfile(
    "メモ付き",
    (
        CsvColumn(CsvField.TITLE, "タスク名"),
        CsvColumn(CsvField.NOTE, "メモ"),
        CsvColumn(CsvField.PROGRESS, "進捗"),
    ),
    delimiter="\t",
)


def note_project() -> tuple[Project, Task, Task]:
    with_note, without = Task("あり", id="a1"), Task("なし", id="b1")
    project = Project("p")
    project.tasks = [with_note, without]
    project.sections = [Section("節", id="s1", tasks=[Task("中", id="c1")])]
    return project, with_note, without


def test_the_note_column_holds_one_line_per_task() -> None:
    project, _, _ = note_project()
    notes_by_id = {"a1": "<p>一行目</p><p>二行目</p>", "c1": "<p>節の中</p>"}
    result = build_table(project, {}, NOTE_PROFILE, note_for=notes_by_id.get)
    table = rows(result.text)
    assert table[0] == ["タスク名", "メモ", "進捗"]
    by_title = {r[0]: r[1] for r in table[1:]}
    assert by_title["あり"] == "一行目\\n二行目"
    assert by_title["なし"] == ""
    assert by_title["中"] == "節の中"


def test_the_note_column_leaves_section_rows_empty() -> None:
    project, _, _ = note_project()
    profile = CsvProfile("p", NOTE_PROFILE.columns, delimiter="\t", section_mode="row")
    result = build_table(project, {}, profile, note_for=lambda _id: "<p>x</p>")
    section_row = next(r for r in rows(result.text) if r[0] == "節")
    assert section_row[1] == ""


def test_the_note_column_is_empty_without_a_note_source() -> None:
    project, _, _ = note_project()
    result = build_table(project, {}, NOTE_PROFILE)
    assert all(r[1] == "" for r in rows(result.text)[1:])


def test_the_default_profile_never_writes_notes() -> None:
    project, _, _ = note_project()
    result = build_table(project, {}, SMARTSHEET, note_for=lambda _id: "<p>秘密</p>")
    assert "秘密" not in result.text
```

(`CsvProfile`の引数名が`delimiter`・`section_mode`かを`csv_profile.py`の dataclass で確かめ、違えば合わせる。`rows`は既存ヘルパーで、区切りを推測できないなら、`csv.reader(StringIO(text), delimiter="\t")`で読む形にする。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_csv_export.py -k "note" -q`
Expected: FAIL(`unexpected keyword argument 'note_for'`)

- [ ] **Step 3: 実装する**(`csv_export.py`)

import に`from collections.abc import Callable`(既存の`Mapping`と同じ場所)と`from projectapp import notes`を足す。`build_table`の引数の末尾に`note_for: Callable[[str], str | None] | None = None,`を足し、docstring に「note_for はタスク id からメモの HTML を返す(なければ`メモ`の列は空)」を足す。`task_row`の`write({...})`の辞書で、`CsvField.CATEGORY`の次に足す。

```python
                CsvField.NOTE: notes.to_cell(note_for(task.id) or "")
                if note_for is not None
                else "",
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_csv_export.py -q`
Expected: PASS

- [ ] **Step 5: smoke と commit**

```bash
uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test
git add src/projectapp/csv_export.py test/test_csv_export.py
git commit -m "feat: CSV の書き出しにメモの列を出せるようにする(要望 153)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 取り込みでメモを読む

**Files:**
- Modify: `src/projectapp/csv_import.py`(`_Row`・`_rows`・`_Builder`・`CsvImport`・`parse_csv`)
- Modify: `test/test_csv_import.py`

**Interfaces:**
- Consumes: `notes.from_cell(text) -> str`(Task 1)、`CsvField.NOTE`(Task 2)
- Produces: `CsvImport.notes: dict[str, str]`(取り込んだ後のタスク id → メモの HTML。メモのあるタスクだけ)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_csv_import.py`の末尾。`parse_csv`・`CsvProfile`・`CsvColumn`・`CsvField`は import 済みか確かめる)

```python
NOTE_IMPORT = CsvProfile(
    "メモ付き",
    (
        CsvColumn(CsvField.TITLE, "タスク名"),
        CsvColumn(CsvField.PROGRESS, "進捗"),
        CsvColumn(CsvField.NOTE, "メモ"),
    ),
    delimiter="\t",
)


def parse_notes(text: str) -> CsvImport:
    return parse_csv(text, "p", {}, profile=NOTE_IMPORT, delimiter="\t")


def test_the_note_column_becomes_the_task_note() -> None:
    result = parse_notes("タスク名\t進捗\tメモ\n設計\t0\t一行目\\n二行目\n実装\t0\t\n")
    by_name = {t.name: t.id for t in result.project.all_tasks()}
    assert result.notes == {by_name["設計"]: "<p>一行目</p><p>二行目</p>"}


def test_no_note_column_means_no_notes() -> None:
    result = parse_csv(SAMPLE, "s", {})
    assert result.notes == {}


def test_a_note_never_runs_as_html() -> None:
    result = parse_notes("タスク名\t進捗\tメモ\n設計\t0\t<script>alert(1)</script>\n")
    (html,) = result.notes.values()
    assert "<script" not in html


def test_a_row_with_only_a_note_is_a_section_without_a_note() -> None:
    result = parse_notes("タスク名\t進捗\tメモ\n節\t\tメモだけ\n設計\t0\t\n")
    assert result.notes == {}
    assert [s.name for s in result.project.sections] == ["節"]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_csv_import.py -k "note" -q`
Expected: FAIL(`CsvImport`に`notes`がない)

- [ ] **Step 3: 実装する**(`csv_import.py`)

1. import: `from projectapp import notes`(`from projectapp.notes import ...`の既存があればそれに合わせる)。
2. `CsvImport`の末尾の`invalid_values: int = 0`の次に`notes: dict[str, str] = field(default_factory=dict)  # 取り込んだ後のタスク id → メモの HTML`を足す(`dataclasses`の`field`を import。frozen でも既定の dict は`default_factory`で可)。
3. `_Row`の`section: str = ""`の次に`note: str = ""`を足す。`blank_fields`には**足さない**(メモだけの行はセクション扱い。メモは付けない)。
4. `_rows`の`_Row(...)`の最後の引数`section,`の次に`cell(CsvField.NOTE),`を足す。
5. `_Builder.__init__`に`self.notes: dict[str, str] = {}`を足す。`add_task`の`holder.append(task)`の前に、次を足す。

```python
        html = notes.from_cell(row.note)
        if html:
            self.notes[task.id] = html
```

6. `parse_csv`の、`CsvImport(...)`を返す直前に、`parse_project`を通したあとのタスク id に絞る行を足し、`CsvImport`の最後の引数に渡す。

```python
    kept = {t.id for t in project.all_tasks()}
    saved_notes = {i: h for i, h in builder.notes.items() if i in kept}
```

`CsvImport(..., builder.invalid_values, saved_notes)`。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_csv_import.py -q`
Expected: PASS。`from_cell`は`cell()`が`strip`した文字列を受ける。

- [ ] **Step 5: smoke と commit**

```bash
uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test
git add src/projectapp/csv_import.py test/test_csv_import.py
git commit -m "feat: CSV の取り込みでメモの列を読む(要望 153)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 画面につなぐ(書き出し・取り込み・注意書き)

**Files:**
- Modify: `src/projectapp/views.py`(`write_csv_export`・`apply_csv_import`)
- Modify: `src/projectapp/csv_dialog.py`(書き出しダイアログの注意書き)
- Modify: `test/test_task_notes_view.py`・`test/test_csv_dialog.py`

**Interfaces:**
- Consumes: `build_table(..., note_for=...)`(Task 3)、`CsvImport.notes`(Task 4)、`notes.save(name, task_id, html)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_notes_view.py`の末尾(`FakeExporter`の保存先の扱いは、`test_views.py`の CSV 書き出しのテストを探して合わせる。`grep -n "write_csv_export\|run_csv_export" test/test_views.py`)。

```python
async def test_the_csv_export_includes_the_note_when_the_column_is_chosen(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>経緯</p>")
    profile = CsvProfile(
        "メモ付き",
        (CsvColumn(CsvField.TITLE, "タスク名"), CsvColumn(CsvField.NOTE, "メモ")),
        delimiter="\t",
    )
    out = tmp_path / "out.tsv"
    view.exporter.ask_path = lambda *_a: _done(out)  # 既存のテストの書き方に合わせる
    with user.client:
        await view.write_csv_export(profile)
    assert "経緯" in out.read_text(encoding="utf-8-sig")


async def test_the_csv_export_includes_a_note_not_yet_saved_in_the_pane(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>入力中</p>")
    # 書き出しの前に、ペインを flush して保存する
    profile = CsvProfile(
        "メモ付き",
        (CsvColumn(CsvField.TITLE, "タスク名"), CsvColumn(CsvField.NOTE, "メモ")),
        delimiter="\t",
    )
    out = tmp_path / "out2.tsv"
    view.exporter.ask_path = lambda *_a: _done(out)
    with user.client:
        await view.write_csv_export(profile)
    assert "入力中" in out.read_text(encoding="utf-8-sig")


async def test_the_csv_import_writes_the_notes_before_showing_the_project(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    profile = CsvProfile(
        "メモ付き",
        (CsvColumn(CsvField.TITLE, "タスク名"), CsvColumn(CsvField.NOTE, "メモ")),
        delimiter="\t",
    )
    text = "タスク名\tメモ\n設計\t経緯\\n詳細\n"
    with user.client:
        view.apply_csv_import(ImportChoice(profile, "\t", None), text, "取り込み")
    task = view.project.all_tasks()[0]
    assert notes.load(view.project.name, task.id) == "<p>経緯</p><p>詳細</p>"
    assert task.id in view.gantt.note_ids
```

(`_done`は`async def _done(value): return value`を同じファイルに足す。`ImportChoice`の引数の形は`csv_dialog.py`の定義を見て合わせる。`apply_csv_import`が`CsvImportError`にならないよう、タスクの日付がなくても読めることを確かめる。落ちたら進捗の列を足す。)

`test/test_csv_dialog.py`の末尾に、注意書きのテストを足す。

```python
async def test_choosing_the_note_column_shows_the_notice(user: User) -> None:
    # 書き出しダイアログで`メモ`の行を使うにすると、注意書きが出る(既定では出ない)
    ...
```

このテストは、`open_csv_export_dialog`の既存テスト(`grep -n "csv-ex-cb" test/test_csv_dialog.py`)の開き方と、列の「使う」のチェックの`mark`(`ColumnBuilder`の`mark="csv-ex-cb"`から作られる名前。`template_builder_view.py`を見て決める)に合わせて書く。`csv-ex-notice`(Step 3 で付ける mark)が、初めは見えず、`メモ`の行を使うにすると見えることを確かめる。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_notes_view.py test/test_csv_dialog.py -k "note" -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`views.py`:

1. `write_csv_export`の先頭、`result = build_table(...)`の前に、ペインの入力を保存してから、メモを渡す形にする(`notes`は`write_csv_export`の後半でローカル変数名に使われているので、別の名前に直すか、先頭でだけ使う。後半の`notes = [...]`を`messages = [...]`に改名して、すべての参照を直す)。

```python
        if self.note_pane is not None:
            self.note_pane.flush()  # メモを入力中なら、先に保存してから書き出す
        name = self.project.name
        result = build_table(
            self.project,
            self.holidays,
            profile,
            self.csv_references(),
            note_for=lambda task_id: notes.load(name, task_id),
        )
```

2. `apply_csv_import`の`self.show_project(result.project, None)`の前に足す。

```python
        for task_id, html in result.notes.items():
            notes.save(result.project.name, task_id, html)  # 保存前でも、🗒️とペインが読める
```

`csv_dialog.py`(書き出しダイアログ):

3. `note = ui.label("").classes("text-negative")`の次に、注意書きを足す。

```python
        notice = (
            ui.label("メモの列を含みます。メモは git 管理の外の内容で、そのまま書き出されます。")
            .classes("text-warning")
            .mark("csv-ex-notice")
        )
        notice.set_visibility(False)
```

4. `refresh_state`で、`メモ`の行を使う(自由書式のあいだは出さない)ときだけ見せる。

```python
        notice.set_visibility(
            not quick["on"] and any(r["use"] and r["field"] is CsvField.NOTE for r in rows)
        )
```

(`refresh_state`は`columns`の変更で呼ばれる。`notice`は`refresh_state`より前に作られているので参照できる。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_notes_view.py test/test_csv_dialog.py test/test_views.py -q -n auto`
Expected: PASS

- [ ] **Step 5: smoke・ruff・ty と commit**

```bash
uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ty check src
git add src/projectapp/views.py src/projectapp/csv_dialog.py test/test_task_notes_view.py test/test_csv_dialog.py
git commit -m "feat: CSV の書き出し・取り込みをメモとつなぐ(要望 153)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 往復のテストと文書

**Files:**
- Modify: `test/test_task_notes_view.py`(往復)
- Modify: `.claude/spec/import-export.md`
- Modify: `docs/requests.md`(要望 153 の状態)
- Modify: `docs/development.md`(テストの一覧に追記があれば)

- [ ] **Step 1: 往復のテストを書く**(`build_table`→`parse_csv`。画面なしの純粋なテストで`test/test_csv_export.py`の末尾に足す)

```python
def test_notes_round_trip_through_a_table() -> None:
    project, _, _ = note_project()
    html = {"a1": "<p>一行目</p><p>文字の\\n と &lt;b&gt;</p>", "c1": "<p>節</p>"}
    text = build_table(project, {}, NOTE_PROFILE, note_for=html.get).text
    result = parse_csv(text, "p", {}, profile=NOTE_PROFILE, delimiter="\t")
    by_name = {t.name: t.id for t in result.project.all_tasks()}
    assert notes.to_cell(result.notes[by_name["あり"]]) == notes.to_cell(html["a1"])
    assert notes.to_cell(result.notes[by_name["中"]]) == "節"
    assert by_name["なし"] not in result.notes
```

(import に`from projectapp import notes`を足す。`parse_csv`は既に import 済み。)

- [ ] **Step 2: 通ることを確かめる**

Run: `uv run pytest test/test_csv_export.py -q`
Expected: PASS

- [ ] **Step 3: 仕様の文書を更新する**

`.claude/spec/import-export.md`の CSV/TSV の節に、次を足す(既存の書き方・見出しの階層に合わせる)。

```markdown
- **メモの列**(要望 153): 書き出しダイアログの列の一覧に`メモ`がある(既定は使わない。選ぶと注意書きが出る)。メモはプレーンテキストで、改行は文字の`\n`、`\`は`\\`。取り込みは、`メモ`の見出し(`メモ`・`ノート`・`note`・`notes`)の列があれば、新しいタスクのメモにする(`notes.sanitize`を通す・1 件 10000 文字まで)。列がなければメモなし。メモだけの行はセクション扱いで、メモは付けない。PlantUML・担当者向けファイルには出さない。
```

`docs/requests.md`の要望 153 の`### 状態`を、「実装済み(PR は作成後に追記)。決定: 用途は別の端末へ渡す往復・プレーンテキスト・ダイアログの列の選択・改行は`\n`・`メモ`列がなければメモなし。設計書`docs/superpowers/specs/2026-11-19-note-export-design.md`・計画`docs/superpowers/plans/2026-11-19-note-export.md`」に置き換え、「決めたい点」の節は残す(経緯として)。

- [ ] **Step 4: 最終確認と commit**

```bash
uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ruff format --check src test && uvx ty check src
git add -A test .claude/spec/import-export.md docs/requests.md
git commit -m "docs: 要望 153 の仕様を反映し、メモの往復のテストを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

その後、最終レビュー(サブエージェントのモデルは`sonnet`を指定する)→ PR を作って止まる(マージは利用者の指示を待つ)。
