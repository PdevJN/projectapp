"""タスクのメモ(要望 150)の画面のテスト。"""

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp import notes
from projectapp.csv_dialog import ImportChoice
from projectapp.csv_profile import CsvColumn, CsvField, CsvProfile
from projectapp.models import Section, Task
from projectapp.views import MainView
from test_views import open_dashboard_view


async def test_the_note_mark_appears_only_for_tasks_with_a_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    await user.should_not_see(marker=f"task-note-{task.id}")
    notes.save(view.project.name, task.id, "<p>メモ</p>")
    view.gantt.note_ids = notes.note_ids(view.project.name)
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")


async def test_the_note_mark_calls_open_note_with_the_task_id(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    opened: list[str] = []
    view.gantt.actions.open_note = opened.append
    notes.save(
        view.project.name, task.id, "<p>x</p>"
    )  # after_edit が、ファイルから🗒️を決める
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")
    user.find(marker=f"task-note-{task.id}").click()
    assert opened == [task.id]


async def test_the_context_menu_note_opens_the_pane_and_typing_saves(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    with user.client:
        view.note_at(path, index)
    await user.should_see(marker="note-editor")
    assert view.note_pane is not None
    assert (view.note_pane.name, view.note_pane.task_id) == (view.project.name, task.id)
    assert (
        notes.load(view.project.name, task.id) is None
    )  # 入力するまでファイルは作らない
    with user.client:
        view.note_pane.editor.set_value("<p>経緯</p>")
        view.note_pane.flush()
    assert notes.load(view.project.name, task.id) == "<p>経緯</p>"
    assert task.id in view.gantt.note_ids  # 🗒️が付く


async def test_opening_an_existing_note_shows_its_text_and_switching_saves_the_previous(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    first = view.project.all_tasks()[0]
    notes.save(view.project.name, first.id, "<p>既存</p>")
    with user.client:
        view.open_note(first.id)
    assert view.note_pane is not None
    assert view.note_pane.editor.value == "<p>既存</p>"
    with user.client:
        view.note_pane.editor.set_value("<p>書き換え</p>")
        view.open_note(first.id)  # 切り替えの前に、いまの入力を保存する
    assert notes.load(view.project.name, first.id) == "<p>書き換え</p>"


async def test_emptying_the_note_removes_the_file_and_the_mark(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>x</p>")
    view.gantt.note_ids = notes.note_ids(view.project.name)
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p><br></p>")
        view.note_pane.flush()
    assert notes.load(view.project.name, task.id) is None
    assert task.id not in view.gantt.note_ids


async def test_close_saves_pending_text_and_hides_the_pane(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>閉じる前</p>")
        view.note_pane.close()
    assert notes.load(view.project.name, task.id) == "<p>閉じる前</p>"
    assert view.note_pane.task_id is None


async def test_deleting_a_task_removes_its_note_and_undo_restores_it(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    notes.save(view.project.name, task.id, "<p>残す</p>")
    with user.client:
        view.delete_task(path, index)
    assert notes.load(view.project.name, task.id) is None
    assert task.id not in view.gantt.note_ids
    with user.client:
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>残す</p>"
    assert task.id in view.gantt.note_ids
    with user.client:
        view.redo()
        view.undo()
    assert (
        notes.load(view.project.name, task.id) == "<p>残す</p>"
    )  # 繰り返しても失われない


async def test_deleting_the_open_task_closes_the_pane_without_resurrecting_the_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>書いた</p>")
        view.delete_task(path, index)  # 保存してから消す(元に戻すで戻る)
    assert view.note_pane.task_id is None
    assert notes.load(view.project.name, task.id) is None
    with user.client:
        view.note_pane.flush()  # 閉じたあとに保存が走っても、ファイルは復活しない
    assert notes.load(view.project.name, task.id) is None
    with user.client:
        view.undo()
    assert notes.load(view.project.name, task.id) == "<p>書いた</p>"


async def test_copying_a_task_copies_its_note(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    path = () if task in view.project.tasks else (0,)
    index = view.tasks_in(path).index(task)
    notes.save(view.project.name, task.id, "<p>写す</p>")
    with user.client:
        view.copy_task_below(path, index)
    copies = [t for t in view.project.all_tasks() if t.id != task.id]
    assert len(copies) == 1
    assert notes.load(view.project.name, copies[0].id) == "<p>写す</p>"
    assert notes.load(view.project.name, task.id) == "<p>写す</p>"  # 元は残る
    assert copies[0].id in view.gantt.note_ids


async def test_copying_a_section_copies_the_notes_of_its_tasks(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path, with_task=False)
    inner = Task("中")
    view.project.sections = [Section("元", tasks=[inner])]
    notes.save(view.project.name, inner.id, "<p>中のメモ</p>")
    with user.client:
        view.copy_section((0,))
    copied = view.project.sections[1].all_tasks()[0]
    assert copied.id != inner.id
    assert notes.load(view.project.name, copied.id) == "<p>中のメモ</p>"
    assert notes.load(view.project.name, inner.id) == "<p>中のメモ</p>"


async def test_a_task_that_vanishes_outside_an_edit_keeps_its_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>外部</p>")
    view.project.tasks = [t for t in view.project.tasks if t.id != task.id]
    with user.client:
        view.reset_history()  # 外部の変更(git pull など)で消えた扱い
    assert notes.load(view.project.name, task.id) == "<p>外部</p>"


async def test_save_as_copies_the_notes_to_the_new_name(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    old = view.project.name
    notes.save(old, task.id, "<p>引き継ぐ</p>")
    with user.client:
        assert view.save_as_new("別名")
    assert notes.load("別名", task.id) == "<p>引き継ぐ</p>"
    assert notes.load(old, task.id) == "<p>引き継ぐ</p>"


async def test_typing_in_the_note_editor_does_not_reach_the_app_shortcuts(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    assert view.note_pane is not None
    listeners = [
        listener
        for listener in view.note_pane.editor._event_listeners.values()
        if listener.type == "keydown"
    ]
    # contenteditable の div は ui.keyboard の ignore をすり抜けるので、エディタの中で止める
    assert any(
        "stopPropagation" in (listener.js_handler or "") for listener in listeners
    )
    assert all(
        "Escape" in (listener.js_handler or "") for listener in listeners
    )  # ESC は通す


async def test_javascript_in_a_note_file_never_reaches_the_editor(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    folder = notes.NOTES_ROOT / view.project.name
    folder.mkdir(parents=True)
    (folder / f"{task.id}.html").write_text(
        '<p>安全</p><img src=x onerror="alert(1)"><script>alert(1)</script>'
        '<a href="javascript:alert(1)">リンク</a>',
        encoding="utf-8",
    )  # 他の端末から持ち込まれたメモのファイル
    with user.client:
        view.open_note(task.id)
    assert view.note_pane is not None
    shown = view.note_pane.editor.value.lower()
    assert "安全" in shown
    for bad in ("<script", "onerror", "javascript:", "<img"):
        assert bad not in shown
    with user.client:
        view.note_pane.editor.set_value(view.note_pane.editor.value + "<p>追記</p>")
        view.note_pane.flush()  # 保存し直しても、ファイルに危険なものは戻らない
    raw = (folder / f"{task.id}.html").read_text(encoding="utf-8").lower()
    assert "<script" not in raw and "onerror" not in raw and "javascript:" not in raw


def hover(user: User, task_id: str) -> str:
    """🗒️ にマウスを乗せたとき(ツールチップの before-show)を起こして、出る中身を返す。"""
    label = user.find(marker=f"task-note-{task_id}").elements.pop()
    tip = next(c for c in label.descendants() if isinstance(c, ui.tooltip))
    body = next(c for c in tip.descendants() if isinstance(c, ui.html))
    listeners = [
        i
        for i, listener in tip._event_listeners.items()
        if listener.type == "beforeShow"
    ]
    assert listeners, "ツールチップに before-show がない"
    for listener_id in listeners:
        tip._handle_event({"listener_id": listener_id, "args": {}})
    return str(body._props.get("innerHTML", ""))


async def test_hovering_the_note_mark_shows_the_note_in_a_tooltip(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p><b>太字</b>の経緯</p>")
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")
    with user.client:
        assert "<b>太字</b>の経緯" in hover(user, task.id)
        notes.save(view.project.name, task.id, "<p>書き換えた</p>")
        shown = hover(user, task.id)  # 乗せ直すと、新しい内容になる
    assert "書き換えた" in shown and "太字" not in shown


async def test_the_tooltip_shows_the_unsaved_text_of_the_open_note(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>保存済み</p>")
    with user.client:
        view.after_edit()
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>入力中</p>")
    await user.should_see(marker=f"task-note-{task.id}")
    with user.client:
        shown = hover(user, task.id)
    assert "入力中" in shown and "保存済み" not in shown


async def test_javascript_in_a_note_file_never_reaches_the_tooltip(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    folder = notes.NOTES_ROOT / view.project.name
    folder.mkdir(parents=True)
    (folder / f"{task.id}.html").write_text(
        '<p>安全</p><img src=x onerror="alert(1)"><script>alert(1)</script>'
        '<a href="javascript:alert(1)">リンク</a>',
        encoding="utf-8",
    )
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")
    with user.client:
        shown = hover(user, task.id).lower()
    assert "安全" in shown
    for bad in ("<script", "onerror", "javascript:", "<img"):
        assert bad not in shown


def test_the_note_tooltip_css_brings_headings_down_to_body_size() -> None:
    from projectapp.note_pane import NOTE_TIP_CSS

    for tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        assert f".note-tip {tag}" in NOTE_TIP_CSS
    assert "font-size: 1em" in NOTE_TIP_CSS and "font-weight: 700" in NOTE_TIP_CSS


async def test_the_note_tooltip_body_uses_the_note_tip_class(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<h2>見出し</h2>")
    with user.client:
        view.after_edit()
    await user.should_see(marker=f"task-note-{task.id}")
    label = user.find(marker=f"task-note-{task.id}").elements.pop()
    body = next(c for c in label.descendants() if isinstance(c, ui.html))
    assert "note-tip" in body.classes


NOTE_PROFILE = CsvProfile(
    "メモ付き",
    (CsvColumn(CsvField.TITLE, "タスク名"), CsvColumn(CsvField.NOTE, "メモ")),
    delimiter="\t",
)


async def test_the_csv_export_includes_the_note_when_the_column_is_chosen(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    notes.save(view.project.name, task.id, "<p>経緯</p>")
    out = tmp_path / "out.tsv"
    view.exporter.path = out  # type: ignore[attr-defined]
    with user.client:
        await view.write_csv_export(NOTE_PROFILE)
    assert "経緯" in out.read_text(encoding="utf-8")


async def test_the_csv_export_includes_a_note_not_yet_saved_in_the_pane(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    task = view.project.all_tasks()[0]
    with user.client:
        view.open_note(task.id)
        assert view.note_pane is not None
        view.note_pane.editor.set_value("<p>入力中</p>")
    out = tmp_path / "out2.tsv"
    view.exporter.path = out  # type: ignore[attr-defined]
    with user.client:
        await view.write_csv_export(NOTE_PROFILE)
    assert "入力中" in out.read_text(encoding="utf-8")


async def test_the_csv_import_writes_the_notes_before_showing_the_project(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    profile = CsvProfile(
        "メモ付き",
        (*NOTE_PROFILE.columns, CsvColumn(CsvField.PROGRESS, "進捗")),
        delimiter="\t",
    )  # 値のある列がないと、行はセクションになる
    text = "タスク名\tメモ\t進捗\n設計\t経緯\\n詳細\t0\n"
    with user.client:
        view.apply_csv_import(ImportChoice(profile, "\t", 0, "utf-8"), text, "取り込み")
    task = view.project.all_tasks()[0]
    assert notes.load(view.project.name, task.id) == "<p>経緯</p><p>詳細</p>"
    assert task.id in view.gantt.note_ids


CSV_PROFILE = CsvProfile(
    "メモ付き",
    (*NOTE_PROFILE.columns, CsvColumn(CsvField.PROGRESS, "進捗")),
    delimiter="\t",
)
CSV_TEXT = "タスク名\tメモ\t進捗\n設計\t経緯\t0\n"


def import_csv(view: MainView, stem: str) -> None:
    view.apply_csv_import(ImportChoice(CSV_PROFILE, "\t", 0, "utf-8"), CSV_TEXT, stem)


async def test_the_csv_import_does_not_mix_into_an_existing_projects_notes(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    (tmp_path / "既存.json").write_text("{}", encoding="utf-8")
    notes.save("既存", "a1b2c3d4", "<p>元のメモ</p>")
    with user.client:
        import_csv(view, "既存")
    assert view.project.name != "既存"
    task = view.project.all_tasks()[0]
    assert notes.load(view.project.name, task.id) == "<p>経緯</p>"
    assert notes.note_ids("既存") == frozenset({"a1b2c3d4"})


async def test_the_csv_import_keeps_the_notes_when_the_stem_is_not_a_valid_name(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    with user.client:
        import_csv(view, "a/b")
    task = view.project.all_tasks()[0]
    assert notes.load(view.project.name, task.id) == "<p>経緯</p>"
    assert task.id in view.gantt.note_ids


async def test_discarding_the_imported_project_removes_its_notes(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    with user.client:
        import_csv(view, "取り込み")
    assert notes.exists("取り込み")
    with user.client:
        view.new_project()
    assert not notes.exists("取り込み")


async def test_importing_again_removes_the_previous_staged_notes(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    with user.client:
        import_csv(view, "一回目")
        import_csv(view, "二回目")
    assert not notes.exists("一回目")
    assert notes.exists("二回目")


async def test_saving_the_imported_project_under_another_name_moves_the_notes(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    with user.client:
        import_csv(view, "取り込み")
    task = view.project.all_tasks()[0]
    with user.client:
        assert view.save_as_new("正式名")
    assert notes.load("正式名", task.id) == "<p>経緯</p>"
    assert not notes.exists("取り込み")


async def test_saving_the_imported_project_under_the_same_name_keeps_the_notes(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    with user.client:
        import_csv(view, "取り込み")
    task = view.project.all_tasks()[0]
    with user.client:
        assert view.save_as_new("取り込み")
        view.new_project()  # 保存したあとは、破棄の対象にならない
    assert notes.load("取り込み", task.id) == "<p>経緯</p>"


async def test_renaming_the_unsaved_imported_project_moves_the_notes(
    user: User, tmp_path: Path
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    with user.client:
        import_csv(view, "取り込み")
    task = view.project.all_tasks()[0]
    with user.client:
        assert view.rename_project("改名")
    assert notes.load("改名", task.id) == "<p>経緯</p>"
    assert not notes.exists("取り込み")
    with user.client:
        view.new_project()
    assert not notes.exists("改名")  # 改名しても、破棄の対象のまま


async def test_the_csv_import_tells_how_many_notes_could_not_be_written(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = await open_dashboard_view(user, tmp_path)
    monkeypatch.setattr(notes, "save", lambda *args: False)
    with user.client:
        import_csv(view, "取り込み")
    await user.should_see("メモ 1 件を書けませんでした")
