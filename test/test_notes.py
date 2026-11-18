"""notes.py(タスクのメモの保存・同期)の単体テスト。"""

from pathlib import Path

from projectapp import notes


def test_save_then_load_round_trips_the_html(isolated_notes: Path) -> None:
    notes.save("案件", "a1b2c3d4", "<p>こんにちは</p>")
    assert notes.load("案件", "a1b2c3d4") == "<p>こんにちは</p>"
    assert (isolated_notes / "案件" / "a1b2c3d4.html").is_file()


def test_load_returns_none_when_there_is_no_note() -> None:
    assert notes.load("案件", "a1b2c3d4") is None


def test_save_blank_html_removes_the_file() -> None:
    for blank in ("", "   ", "<p><br></p>", "<div>&nbsp;</div>"):
        notes.save("案件", "a1b2c3d4", "<p>x</p>")
        notes.save("案件", "a1b2c3d4", blank)
        assert notes.load("案件", "a1b2c3d4") is None
        assert notes.note_ids("案件") == frozenset()


def test_is_blank_ignores_tags_and_nbsp() -> None:
    assert notes.is_blank("<p><br></p>")
    assert notes.is_blank("<p>&nbsp;</p>")
    assert not notes.is_blank("<p>a</p>")
    assert not notes.is_blank("<img src='x'>テキスト")


def test_load_survives_a_broken_file(isolated_notes: Path) -> None:
    folder = isolated_notes / "案件"
    folder.mkdir()
    (folder / "a1b2c3d4.html").write_bytes(b"\xff\xfe\x00broken")
    assert notes.load("案件", "a1b2c3d4") is None  # 例外を出さず、メモなしとして扱う


def test_unsafe_ids_and_names_are_rejected(isolated_notes: Path) -> None:
    for bad in ("../x", "a/b", "", "a" * 65, "あ"):
        notes.save("案件", bad, "<p>x</p>")
        assert notes.load("案件", bad) is None
    notes.save("../escape", "a1b2c3d4", "<p>x</p>")
    notes.save("a/b", "a1b2c3d4", "<p>x</p>")
    assert list(isolated_notes.rglob("*.html")) == []  # notes の外へ書かない
    assert notes.note_ids("../escape") == frozenset()


def test_note_ids_lists_only_valid_html_files(isolated_notes: Path) -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    notes.save("案件", "bbbb2222", "<p>2</p>")
    (isolated_notes / "案件" / "memo.txt").write_text("x")
    (isolated_notes / "案件" / "bad id.html").write_text("x")
    assert notes.note_ids("案件") == frozenset({"aaaa1111", "bbbb2222"})
    assert notes.note_ids("ない") == frozenset()


def test_delete_returns_the_removed_html() -> None:
    notes.save("案件", "a1b2c3d4", "<p>x</p>")
    assert notes.delete("案件", "a1b2c3d4") == "<p>x</p>"
    assert notes.load("案件", "a1b2c3d4") is None
    assert notes.delete("案件", "a1b2c3d4") is None


def test_copy_and_copy_many() -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    notes.save("案件", "bbbb2222", "<p>2</p>")
    notes.copy("案件", "aaaa1111", "cccc3333")
    notes.copy_many("案件", [("bbbb2222", "dddd4444"), ("eeee5555", "ffff6666")])
    assert notes.load("案件", "cccc3333") == "<p>1</p>"
    assert notes.load("案件", "dddd4444") == "<p>2</p>"
    assert notes.load("案件", "ffff6666") is None  # 元のメモがなければ作らない
    assert notes.load("案件", "aaaa1111") == "<p>1</p>"  # 元は残る


def test_copy_project_copies_the_folder_and_keeps_the_source() -> None:
    notes.save("旧", "aaaa1111", "<p>1</p>")
    notes.copy_project("旧", "新")
    assert notes.load("新", "aaaa1111") == "<p>1</p>"
    assert notes.load("旧", "aaaa1111") == "<p>1</p>"
    notes.copy_project("ない", "新2")  # 元がなければ何もしない
    assert notes.note_ids("新2") == frozenset()
    notes.copy_project("旧", "旧")  # 同じ名前なら何もしない
    assert notes.load("旧", "aaaa1111") == "<p>1</p>"


def test_sync_moves_a_removed_note_to_the_trash_and_restores_it() -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    trash: dict[str, str] = {}
    gone = notes.sync("案件", {"aaaa1111", "bbbb2222"}, {"bbbb2222"}, trash)
    assert gone == {"aaaa1111"}
    assert notes.load("案件", "aaaa1111") is None
    assert trash == {"aaaa1111": "<p>1</p>"}
    notes.sync("案件", {"bbbb2222"}, {"aaaa1111", "bbbb2222"}, trash)  # 元に戻す
    assert notes.load("案件", "aaaa1111") == "<p>1</p>"
    assert trash == {}


def test_sync_survives_delete_undo_redo_undo() -> None:
    notes.save("案件", "aaaa1111", "<p>1</p>")
    trash: dict[str, str] = {}
    present, absent = {"aaaa1111"}, set()
    for before, after in [
        (present, absent),
        (absent, present),
        (present, absent),
        (absent, present),
    ]:
        notes.sync("案件", set(before), set(after), trash)
    assert notes.load("案件", "aaaa1111") == "<p>1</p>"
    assert trash == {}


def test_sync_ignores_ids_without_a_note_and_unchanged_ids() -> None:
    trash: dict[str, str] = {}
    assert notes.sync("案件", {"aaaa1111"}, {"aaaa1111"}, trash) == set()
    assert notes.sync("案件", {"aaaa1111"}, set(), trash) == {"aaaa1111"}
    assert trash == {}  # メモがなければ、ごみ箱にも入れない
    assert notes.sync("案件", set(), {"zzzz9999"}, trash) == set()
    assert notes.note_ids("案件") == frozenset()


def test_delete_does_not_raise_when_the_file_cannot_be_removed(
    isolated_notes: Path,
) -> None:
    (isolated_notes / "案件" / "aaaa1111.html").mkdir(parents=True)  # unlink できない形
    assert notes.delete("案件", "aaaa1111") is None
    notes.save("案件", "aaaa1111", "<p><br></p>")  # 空で保存しても例外を出さない
    assert notes.sync("案件", {"aaaa1111"}, set(), {}) == {"aaaa1111"}


def test_copy_between_copies_notes_to_another_project() -> None:
    notes.save("親", "aaaa1111", "<p>1</p>")
    notes.save("親", "bbbb2222", "<p>2</p>")
    notes.copy_between("親", "子", ["aaaa1111", "cccc3333"])
    assert notes.load("子", "aaaa1111") == "<p>1</p>"
    assert notes.load("子", "bbbb2222") is None  # 指定した id だけ
    assert notes.load("子", "cccc3333") is None  # 元になければ作らない
    assert (
        notes.load("親", "aaaa1111") == "<p>1</p>"
    )  # 元は残る(親では after_edit が消す)


EVIL = [
    "<p>安全</p><script>alert(1)</script>",
    "<p>安全</p><ScRiPt src=//evil.example/x.js></ScRiPt>",
    '<p>安全</p><img src=x onerror="alert(1)">',
    '<p onclick="alert(1)" onmouseover=alert(1)>安全</p>',
    '<p>安全</p><a href="javascript:alert(1)">リンク</a>',
    '<p>安全</p><a href="  jav&#x61;script:alert(1)">リンク</a>',
    '<p>安全</p><a href="java\tscript:alert(1)">リンク</a>',
    '<p>安全</p><a href="data:text/html,<script>alert(1)</script>">リンク</a>',
    '<p>安全</p><iframe src="javascript:alert(1)"></iframe>',
    "<p>安全</p><svg onload=alert(1)><circle/></svg>",
    "<p>安全</p><style>body{background:url(javascript:alert(1))}</style>",
    "<p>安全</p><object data=x></object><embed src=x><form action=x><input></form>",
    '<p style="background:url(javascript:alert(1))">安全</p>',
    "<p>安全</p><!--<script>alert(1)</script>-->",
    "<p>安全</p><scr<script>ipt>alert(1)</script>",
]
DANGEROUS = ("<script", "javascript:", "onerror", "onclick", "onmouseover", "onload")


def test_sanitize_removes_every_way_to_run_javascript() -> None:
    for html in EVIL:
        cleaned = notes.sanitize(html).lower()
        assert "安全" in cleaned, html  # 普通の文字は残す
        for bad in DANGEROUS:
            assert bad not in cleaned, (html, cleaned)
        for tag in ("<iframe", "<svg", "<style", "<object", "<embed", "<form", "<img"):
            assert tag not in cleaned, (html, cleaned)


def test_sanitize_keeps_the_editor_formatting_and_safe_links() -> None:
    html = (
        "<h2>見出し</h2><p><b>太字</b>と<i>斜体</i>・<u>下線</u></p>"
        "<ul><li>一</li><li>二</li></ul><ol><li>三</li></ol>"
        '<p><a href="https://example.com/a?b=1&amp;c=2">リンク</a>と&nbsp;&lt;タグ&gt;</p>'
        "<blockquote>引用</blockquote><pre>コード</pre>"
    )
    cleaned = notes.sanitize(html)
    for keep in (
        "<h2>見出し</h2>",
        "<b>太字</b>",
        "<i>斜体</i>",
        "<u>下線</u>",
        "<ul>",
        "<ol>",
        "<li>一</li>",
        "&nbsp;",
        "&lt;タグ&gt;",
        "<blockquote>引用</blockquote>",
        "<pre>コード</pre>",
    ):
        assert keep in cleaned, keep
    assert 'href="https://example.com/a?b=1&amp;c=2"' in cleaned


def test_a_file_with_javascript_is_cleaned_when_it_is_loaded(
    isolated_notes: Path,
) -> None:
    folder = isolated_notes / "案件"
    folder.mkdir()
    for i, html in enumerate(EVIL):
        (folder / f"aaaa{i:04d}.html").write_text(
            html, encoding="utf-8"
        )  # 外から持ち込まれたファイル
        loaded = notes.load("案件", f"aaaa{i:04d}") or ""
        assert "安全" in loaded
        for bad in DANGEROUS:
            assert bad not in loaded.lower(), (html, loaded)


def test_what_is_saved_never_contains_javascript(isolated_notes: Path) -> None:
    notes.save(
        "案件",
        "aaaa1111",
        '<p>安全</p><img src=x onerror="alert(1)"><script>alert(1)</script>',
    )
    raw = (isolated_notes / "案件" / "aaaa1111.html").read_text(encoding="utf-8")
    assert "<script" not in raw and "onerror" not in raw
    assert "安全" in raw


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
