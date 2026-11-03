from nicegui import ui
from nicegui.testing import User

from projectapp.csv_dialog import (
    ImportChoice,
    open_csv_export_dialog,
    open_csv_import_dialog,
)
from projectapp.csv_profile import SMARTSHEET, CsvColumn, CsvField, CsvProfile

DATA = "件名,担当,開始\n設計,田中,2026-10-05\n実装,鈴木,あした\n".encode()


async def open_dialog(user: User, data: bytes = DATA, profiles=(), last=None):
    chosen: list[tuple[ImportChoice, str]] = []
    saved: list[CsvProfile] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "開く",
            on_click=lambda: open_csv_import_dialog(
                data,
                list(profiles),
                last,
                lambda choice, text: chosen.append((choice, text)),
                lambda p: saved.append(p) or None,
            ),
        ).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="csv-import-dialog")
    return chosen, saved


async def test_the_guess_fills_the_mapping_and_import_returns_it(user: User) -> None:
    chosen, _ = await open_dialog(user)
    user.find(marker="csv-import-confirm").click()
    choice, text = chosen[0]
    assert {c.field: c.header for c in choice.profile.columns} == {
        CsvField.TITLE: "件名",
        CsvField.OWNER: "担当",
        CsvField.START: "開始",
    }
    assert choice.delimiter == "," and text.startswith("件名")


async def test_import_is_disabled_without_a_title_column(user: User) -> None:
    await open_dialog(user)
    user.find(marker="csv-map-title").elements.pop().set_value(-1)
    assert not user.find(marker="csv-import-confirm").elements.pop().enabled


async def test_choosing_the_same_column_twice_clears_the_earlier_field(
    user: User,
) -> None:
    await open_dialog(user)
    owner = user.find(marker="csv-map-owner").elements.pop()
    title = user.find(marker="csv-map-title").elements.pop()
    owner.set_value(title.value)  # 担当にも「件名」の列を選ぶ
    assert title.value == -1


async def test_the_preview_marks_unreadable_cells(user: User) -> None:
    await open_dialog(user)
    preview = user.find(marker="csv-preview").elements.pop()
    reds = [e for e in preview.descendants() if "text-negative" in e.classes]
    assert [e.text for e in reds] == ["あした"]


async def test_a_matching_saved_profile_is_preselected(user: User) -> None:
    p = CsvProfile(
        "自作", (CsvColumn(CsvField.TITLE, "件名"), CsvColumn(CsvField.OWNER, "担当"))
    )
    await open_dialog(user, profiles=[p])
    assert user.find(marker="csv-profile").elements.pop().value == "自作"


async def test_smartsheet_files_select_the_builtin_profile(user: User) -> None:
    sheet = (
        "WBS 番号\tタスクのタイトル\tタスクオーナー\t開始日\t期限\t期間\tタスク完了率\n"
        "1\tA\t\t\t\t\t\n"
    ).encode()
    await open_dialog(user, data=sheet)
    assert user.find(marker="csv-profile").elements.pop().value == SMARTSHEET.name


async def test_cancel_returns_nothing(user: User) -> None:
    chosen, _ = await open_dialog(user)
    user.find(marker="csv-cancel").click()
    assert chosen == []


async def test_saving_a_profile_passes_the_current_mapping(user: User) -> None:
    _, saved = await open_dialog(user)
    user.find(marker="csv-save-profile").click()
    await user.should_see(marker="csv-save-name")
    user.find(marker="csv-save-name").elements.pop().set_value("会社の形式")
    user.find(marker="csv-save-ok").click()
    assert [p.name for p in saved] == ["会社の形式"]
    assert [c.header for c in saved[0].columns] == ["件名", "担当", "開始"]


async def open_export(user: User, profiles=(), last=None):
    exported: list[CsvProfile] = []
    saved: list[CsvProfile] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "開く",
            on_click=lambda: open_csv_export_dialog(
                list(profiles),
                last,
                exported.append,
                lambda p: saved.append(p) or None,
            ),
        ).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="csv-export-dialog")
    return exported, saved


async def test_export_dialog_starts_with_smartsheet_and_exports_it(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-export-confirm").click()
    p = exported[0]
    assert p.name == "Smartsheet" and p.delimiter == "\t" and p.blank_rows == 2
    assert [c.header for c in p.columns][:2] == ["WBS 番号", "タスクのタイトル"]


async def test_unchecking_and_moving_columns_changes_the_profile(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-use-duration").elements.pop().set_value(False)
    user.find(marker="csv-ex-down-wbs").click()
    user.find(marker="csv-export-confirm").click()
    p = exported[0]
    fields = [c.field.value for c in p.columns]
    assert "duration" not in fields and fields[:2] == ["title", "wbs"]
    assert p.blank_rows == 0  # 組み込みの形から外れたら、テンプレートの空行は入れない


async def test_export_is_disabled_without_the_title_column(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-use-title").elements.pop().set_value(False)
    assert not user.find(marker="csv-export-confirm").elements.pop().enabled


async def test_choosing_a_saved_profile_loads_its_settings(user: User) -> None:
    p = CsvProfile(
        "自作",
        (CsvColumn(CsvField.TITLE, "件名"), CsvColumn(CsvField.EFFORT, "工数")),
        delimiter=";",
        encoding="cp932",
        date_format="ymd-slash",
        owner_separator="/",
    )
    exported, _ = await open_export(user, profiles=[p], last="自作")
    user.find(marker="csv-export-confirm").click()
    q = exported[0]
    assert (q.name, q.delimiter, q.encoding) == ("自作", ";", "cp932")
    assert (q.date_format, q.owner_separator) == ("ymd-slash", "/")
    assert [(c.field, c.header) for c in q.columns] == [
        (CsvField.TITLE, "件名"),
        (CsvField.EFFORT, "工数"),
    ]


async def test_export_dialog_saves_the_current_settings(user: User) -> None:
    _, saved = await open_export(user)
    user.find(marker="csv-ex-delimiter").elements.pop().set_value(",")
    user.find(marker="csv-ex-save").click()
    await user.should_see(marker="csv-ex-save-name")
    user.find(marker="csv-ex-save-name").elements.pop().set_value("カンマ版")
    user.find(marker="csv-ex-save-ok").click()
    assert [p.name for p in saved] == ["カンマ版"] and saved[0].delimiter == ","


async def test_the_second_of_two_equal_headings_cannot_be_chosen(user: User) -> None:
    await open_dialog(user, data="名前,名前,担当\nA,B,田中\n".encode())
    options = user.find(marker="csv-map-title").elements.pop().options
    assert 0 in options and 1 not in options and 2 in options


async def test_dragging_a_row_onto_another_moves_it_there(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-row-owner").trigger("dragstart")
    user.find(marker="csv-ex-row-wbs").trigger("drop.prevent")
    user.find(marker="csv-export-confirm").click()
    fields = [c.field.value for c in exported[0].columns]
    assert fields[:3] == ["owner", "wbs", "title"]


async def test_the_progress_field_is_named_shinchoku(user: User) -> None:
    from projectapp.csv_profile import FIELD_LABELS

    assert FIELD_LABELS[CsvField.PROGRESS] == "進捗率"


async def test_export_option_labels_are_not_truncated(user: User) -> None:
    await open_export(user)
    for marker in (
        "csv-ex-profile",
        "csv-ex-delimiter",
        "csv-ex-encoding",
        "csv-ex-date",
        "csv-ex-owner-sep",
    ):
        select = user.find(marker=marker).elements.pop()
        assert "min-w-[12rem]" in select.classes, marker
    checkbox = user.find(marker="csv-ex-use-owner").elements.pop()
    assert "w-40" not in checkbox.classes and "min-w-[12rem]" in checkbox.classes


async def test_the_percent_sign_can_be_turned_off_for_the_export(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-percent").elements.pop().set_value(False)
    user.find(marker="csv-export-confirm").click()
    assert exported[0].progress_percent is False


async def test_a_template_in_the_import_dialog_splits_one_column(user: User) -> None:
    data = "件名,期間\n設計,2026-10-05〜2026-10-09\n".encode()
    chosen, _ = await open_dialog(user, data=data)
    user.find(marker="csv-map-start").elements.pop().set_value(1)
    user.find(marker="csv-template-start").elements.pop().set_value("{開始日}〜{期限}")
    assert user.find(marker="csv-map-end").elements.pop().value == 1
    user.find(marker="csv-import-confirm").click()
    profile = chosen[0][0].profile
    column = next(c for c in profile.columns if c.template)
    assert column.field is CsvField.START and column.header == "期間"
    assert CsvField.END not in {c.field for c in profile.columns}


async def test_an_invalid_template_is_not_applied(user: User) -> None:
    data = "件名,期間\n設計,2026-10-05〜2026-10-09\n".encode()
    chosen, _ = await open_dialog(user, data=data)
    user.find(marker="csv-map-start").elements.pop().set_value(1)
    user.find(marker="csv-template-start").elements.pop().set_value("{開始日}{期限}")
    user.find(marker="csv-import-confirm").click()
    assert not any(c.template for c in chosen[0][0].profile.columns)


async def test_an_invalid_quick_template_disables_the_export(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}{期限}")
    assert not user.find(marker="csv-export-confirm").elements.pop().enabled


async def test_the_column_list_is_inside_a_collapsed_expansion(user: User) -> None:
    await open_export(user)
    details = user.find(marker="csv-ex-details").elements.pop()
    assert details.value is False
    row = user.find(marker="csv-ex-use-title").elements.pop()
    assert any(a is details for a in row.ancestors())


async def test_the_quick_template_is_ignored_while_its_checkbox_is_off(
    user: User,
) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}〜{期限}")
    user.find(marker="csv-export-confirm").click()
    assert not any(c.template for c in exported[0].columns)


async def test_the_available_items_are_listed_as_a_reference(user: User) -> None:
    await open_export(user)
    hint = user.find(marker="csv-ex-quick-hint").elements.pop()
    assert "{開始日}" in hint.text and "{担当の割合}" in hint.text


async def test_the_drag_image_is_an_opaque_copy_of_the_row(user: User) -> None:
    await open_export(user)
    row = user.find(marker="csv-ex-row-title").elements.pop()
    listener = next(x for x in row._event_listeners.values() if x.type == "dragstart")
    script = listener.js_handler or ""
    assert "setDragImage" in script and "backgroundColor" in script


async def test_a_free_format_replaces_the_column_list(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value(
        "{開始日}/{期限}: {タスク名}"
    )
    user.find(marker="csv-ex-quick-header").elements.pop().set_value("予定")
    user.find(marker="csv-export-confirm").click()
    columns = exported[0].columns
    assert len(columns) == 1  # 通常の項目の列は出さない
    assert columns[0].template == "{開始日}/{期限}: {タスク名}"
    assert columns[0].header == "予定" and columns[0].field is CsvField.START


async def test_the_column_list_is_disabled_while_the_free_format_is_on(
    user: User,
) -> None:
    await open_export(user)
    markers = ("csv-ex-use-title", "csv-ex-header-title", "csv-ex-up-title")
    assert all(user.find(marker=m).elements.pop().enabled for m in markers)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    assert not any(user.find(marker=m).elements.pop().enabled for m in markers)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(False)
    assert all(user.find(marker=m).elements.pop().enabled for m in markers)


async def test_an_empty_free_format_cannot_be_exported(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    assert not user.find(marker="csv-export-confirm").elements.pop().enabled


async def test_the_free_format_may_have_no_header(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("【{タスク名}】")
    user.find(marker="csv-ex-quick-header").elements.pop().set_value("")
    assert user.find(marker="csv-export-confirm").elements.pop().enabled
    user.find(marker="csv-export-confirm").click()
    assert exported[0].columns[0].header == ""


async def test_a_saved_free_format_comes_back_in_the_quick_fields(user: User) -> None:
    p = CsvProfile(
        "結合",
        (CsvColumn(CsvField.START, "予定", "{開始日}〜{タスク名}"),),
    )
    exported, _ = await open_export(user, profiles=[p], last="結合")
    assert (
        user.find(marker="csv-ex-quick").elements.pop().value == "{開始日}〜{タスク名}"
    )
    user.find(marker="csv-export-confirm").click()
    assert [c.template for c in exported[0].columns] == ["{開始日}〜{タスク名}"]
