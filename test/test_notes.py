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
