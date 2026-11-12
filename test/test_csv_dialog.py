import asyncio
from contextlib import suppress

from nicegui import ui
from nicegui.events import GenericEventArguments
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
    user.find(marker="csv-ic-item-title").elements.pop().set_value(False)  # ×で外す
    assert not user.find(marker="csv-import-confirm").elements.pop().enabled


async def test_choosing_the_same_column_twice_clears_the_earlier_field(
    user: User,
) -> None:
    await open_dialog(user)
    user.find(marker="csv-ic-item-owner").trigger("dblclick")
    await user.should_see(marker="csv-pick-select")
    user.find(marker="csv-pick-select").elements.pop().set_value(
        0
    )  # 担当にも「件名」の列
    user.find(marker="csv-pick-ok").click()
    await asyncio.sleep(0.05)
    await user.should_not_see(marker="csv-ic-item-title")  # 先の項目が外れる
    owner = user.find(marker="csv-ic-item-owner").elements.pop()
    assert "1: 件名" in owner.text
    assert not user.find(marker="csv-import-confirm").elements.pop().enabled


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


async def test_removing_a_column_chip_changes_the_profile(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-cb-item-duration").elements.pop().set_value(False)
    await asyncio.sleep(0.05)
    user.find(marker="csv-export-confirm").click()
    p = exported[0]
    assert "duration" not in [c.field.value for c in p.columns]
    assert p.blank_rows == 0  # 組み込みの形から外れたら、テンプレートの空行は入れない


async def test_export_is_disabled_without_the_title_column(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-cb-item-title").elements.pop().set_value(False)
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
    user.find(marker="csv-ic-item-title").trigger("dblclick")
    await user.should_see(marker="csv-pick-select")
    options = user.find(marker="csv-pick-select").elements.pop().options
    assert 0 in options and 1 not in options and 2 in options


async def test_dropping_a_column_chip_reorders_the_columns(user: User) -> None:
    from projectapp.template_builder_view import ColumnBuilder

    rows = [
        {"field": f, "use": f is not CsvField.END, "header": f.value}
        for f in (CsvField.WBS, CsvField.TITLE, CsvField.OWNER, CsvField.END)
    ]
    changed: list[bool] = []
    holder: dict = {}

    @ui.page("/")
    def index() -> None:
        holder["b"] = ColumnBuilder(
            rows, list(CsvField), lambda: changed.append(True), mark="t"
        )
        holder["b"].build()

    await user.open("/")
    builder = holder["b"]
    builder._on_event(
        GenericEventArguments(
            sender=builder.root,
            client=user.client,
            args={"root": builder.id, "op": "move", "from": 2, "to": 0},
        )
    )
    assert [r["field"] for r in rows if r["use"]] == [
        CsvField.OWNER,
        CsvField.WBS,
        CsvField.TITLE,
    ]
    builder._on_event(
        GenericEventArguments(
            sender=builder.root,
            client=user.client,
            args={"root": builder.id, "op": "insert", "key": "f:end", "index": 1},
        )
    )
    assert rows[1]["field"] is CsvField.END and rows[1]["use"]
    assert len(changed) == 2


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


async def test_the_percent_sign_can_be_turned_off_for_the_export(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-percent").elements.pop().set_value(False)
    user.find(marker="csv-export-confirm").click()
    assert exported[0].progress_percent is False


async def add_format_column(
    user: User, column: int, template_clicks: list[str]
) -> None:
    """`＋書式の列`で、列を選び、パレットのチップを順にクリックして書式を組み立てる。"""
    user.find(marker="csv-ic-pal-format").click()
    await user.should_see(marker="csv-fmt-dialog")
    user.find(marker="csv-fmt-column").elements.pop().set_value(column)
    for marker in template_clicks:
        user.find(marker=marker).click()


async def test_a_format_column_splits_one_column(user: User) -> None:
    data = "件名,期間\n設計,2026-10-05〜2026-10-09\n".encode()
    chosen, _ = await open_dialog(user, data=data)
    await add_format_column(
        user,
        1,
        ["csv-tb-pal-start", "csv-tb-sep-8", "csv-tb-pal-end"],
    )
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)
    await user.should_see(marker="csv-ic-item-start")  # 書式の列は 1 つのチップ
    await user.should_not_see(marker="csv-ic-item-end")
    user.find(marker="csv-import-confirm").click()
    profile = chosen[0][0].profile
    column = next(c for c in profile.columns if c.template)
    assert column.field is CsvField.START and column.header == "期間"
    assert column.template == "{開始日}/{期限}"
    assert CsvField.END not in {c.field for c in profile.columns}


async def test_a_format_without_a_column_is_not_applied(user: User) -> None:
    data = "件名,期間\n設計,2026-10-05〜2026-10-09\n".encode()
    await open_dialog(user, data=data)
    user.find(marker="csv-ic-pal-format").click()
    await user.should_see(marker="csv-fmt-dialog")
    user.find(marker="csv-tb-pal-start").click()
    user.find(marker="csv-tb-pal-end").click()
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)  # 区切りもなく、列も未選択
    await user.should_see(marker="csv-fmt-dialog")  # 閉じない
    await user.should_not_see(marker="csv-ic-item-start")


async def test_only_format_chips_have_the_right_click_menu(user: User) -> None:
    data = "件名,期間\n設計,2026-10-05〜2026-10-09\n".encode()
    await open_dialog(user, data=data)
    await user.should_not_see(marker="csv-ic-menu-edit-title")
    await add_format_column(
        user, 1, ["csv-tb-pal-start", "csv-tb-sep-8", "csv-tb-pal-end"]
    )
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)
    await user.should_see(marker="csv-ic-menu-edit-start")
    await user.should_not_see(marker="csv-ic-menu-edit-title")


async def test_clearing_a_format_restores_the_plain_column(user: User) -> None:
    data = "件名,期間\n設計,2026-10-05〜2026-10-09\n".encode()
    chosen, _ = await open_dialog(user, data=data)
    await add_format_column(
        user, 1, ["csv-tb-pal-start", "csv-tb-sep-8", "csv-tb-pal-end"]
    )
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)
    user.find(marker="csv-ic-menu-clear-start").click()
    await asyncio.sleep(0.05)
    await user.should_not_see(marker="csv-ic-menu-edit-start")
    user.find(marker="csv-import-confirm").click()
    assert not any(c.template for c in chosen[0][0].profile.columns)


async def test_the_breadcrumb_setting_reaches_the_profile_and_adds_the_menu(
    user: User,
) -> None:
    chosen, _ = await open_dialog(user)
    await user.should_not_see(marker="csv-ic-menu-edit-title")
    user.find(marker="csv-ic-pal-format").click()
    await user.should_see(marker="csv-fmt-dialog")
    user.find(marker="csv-fmt-breadcrumb").elements.pop().set_value(True)
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)
    await user.should_see(marker="csv-ic-menu-edit-title")  # 階層を読むタスク名
    user.find(marker="csv-import-confirm").click()
    assert chosen[0][0].profile.title_breadcrumb is True


async def test_the_title_chip_can_open_the_format_dialog_to_turn_it_off(
    user: User,
) -> None:
    chosen, _ = await open_dialog(user)
    user.find(marker="csv-ic-pal-format").click()
    await user.should_see(marker="csv-fmt-dialog")
    user.find(marker="csv-fmt-breadcrumb").elements.pop().set_value(True)
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)
    user.find(marker="csv-ic-menu-edit-title").click()
    await user.should_see(marker="csv-fmt-dialog")
    for box in user.find(marker="csv-fmt-breadcrumb").elements:  # 閉じた前の分も残る
        box.set_value(False)
    user.find(marker="csv-fmt-ok").click()
    await asyncio.sleep(0.05)
    user.find(marker="csv-import-confirm").click()
    assert chosen[0][0].profile.title_breadcrumb is False


async def test_an_unassigned_item_is_added_from_the_palette(user: User) -> None:
    data = "件名,担当,期限\nA,田中,2026-10-09\n".encode()
    chosen, _ = await open_dialog(user, data=data)
    user.find(marker="csv-ic-item-end").elements.pop().set_value(False)
    await asyncio.sleep(0.05)
    user.find(marker="csv-ic-pal-end").click()
    await user.should_see(marker="csv-pick-select")
    user.find(marker="csv-pick-select").elements.pop().set_value(2)
    user.find(marker="csv-pick-ok").click()
    await asyncio.sleep(0.05)
    user.find(marker="csv-import-confirm").click()
    fields = {c.field: c.header for c in chosen[0][0].profile.columns}
    assert fields[CsvField.END] == "期限"


async def test_an_invalid_quick_template_disables_the_export(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}{期限}")
    assert not user.find(marker="csv-export-confirm").elements.pop().enabled


async def test_the_column_list_is_inside_a_collapsed_expansion(user: User) -> None:
    await open_export(user)
    details = user.find(marker="csv-ex-details").elements.pop()
    assert details.value is False
    chip = user.find(marker="csv-ex-cb-item-title").elements.pop()
    assert any(a is details for a in chip.ancestors())


async def test_the_quick_template_is_ignored_while_its_checkbox_is_off(
    user: User,
) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}〜{期限}")
    user.find(marker="csv-export-confirm").click()
    assert not any(c.template for c in exported[0].columns)


async def test_the_available_items_are_offered_as_chips(user: User) -> None:
    await open_export(user)
    await user.should_see(marker="csv-ex-tb-pal-start")
    await user.should_see(marker="csv-ex-tb-pal-ratio")
    await user.should_see(marker="csv-ex-tb-sep-8")


async def test_a_column_header_is_edited_in_place_by_double_click(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-cb-item-title").trigger("dblclick")
    await user.should_see(marker="csv-ex-cb-header-input")
    user.find(marker="csv-ex-cb-header-input").elements.pop().set_value("件名")
    user.find(marker="csv-ex-cb-header-input").trigger("keydown.enter")
    await asyncio.sleep(0.05)
    user.find(marker="csv-export-confirm").click()
    assert (
        next(c.header for c in exported[0].columns if c.field is CsvField.TITLE)
        == "件名"
    )


async def test_an_unused_item_is_added_from_the_palette_by_click(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-cb-item-duration").elements.pop().set_value(False)
    await asyncio.sleep(0.05)
    user.find(marker="csv-ex-cb-pal-duration").click()
    await asyncio.sleep(0.05)
    user.find(marker="csv-export-confirm").click()
    assert exported[0].columns[-1].field is CsvField.DURATION


async def set_header(user: User, text: str) -> None:
    """見出しのチップをダブルクリックして入力欄に変え、確定する。"""
    user.find(marker="csv-ex-tb-header").trigger("dblclick")
    await user.should_see(marker="csv-ex-tb-header-input")
    user.find(marker="csv-ex-tb-header-input").elements.pop().set_value(text)
    user.find(marker="csv-ex-tb-header-input").trigger("keydown.enter")


async def test_a_free_format_replaces_the_column_list(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value(
        "{開始日}/{期限}: {タスク名}"
    )
    await set_header(user, "予定")
    user.find(marker="csv-export-confirm").click()
    columns = exported[0].columns
    assert len(columns) == 1  # 通常の項目の列は出さない
    assert columns[0].template == "{開始日}/{期限}: {タスク名}"
    assert columns[0].header == "予定" and columns[0].field is CsvField.START


async def test_the_column_list_is_disabled_while_the_free_format_is_on(
    user: User,
) -> None:
    await open_export(user)

    def locked() -> bool:
        chip = user.find(marker="csv-ex-cb-item-title").elements.pop()
        return any("pointer-events-none" in a.classes for a in chip.ancestors())

    assert not locked()
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    assert locked()
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(False)
    assert not locked()


async def test_an_empty_free_format_cannot_be_exported(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    assert not user.find(marker="csv-export-confirm").elements.pop().enabled


async def test_the_free_format_may_have_no_header(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("【{タスク名}】")
    await set_header(user, "")
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


async def builder_items(user: User) -> list[str]:
    await asyncio.sleep(0.05)  # 描画の更新は背景で走る
    found = []
    for index in range(20):
        with suppress(AssertionError):
            found.append(
                user.find(marker=f"csv-ex-tb-item-{index}").elements.pop().text
            )
            continue
        break
    return found


async def test_clicking_the_palette_builds_the_template(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-tb-pal-start").click()
    user.find(marker="csv-ex-tb-sep-8").click()  # /
    user.find(marker="csv-ex-tb-pal-end").click()
    user.find(marker="csv-ex-tb-sep-1").click()  # :
    user.find(marker="csv-ex-tb-sep-9").click()  # 空白
    user.find(marker="csv-ex-tb-pal-title").click()
    assert await builder_items(user) == ["開始日", "/", "期限", ":", "␣", "タスク名"]
    assert user.find(marker="csv-ex-quick").elements.pop().value == (
        "{開始日}/{期限}: {タスク名}"
    )


async def test_typing_the_template_rebuilds_the_chips(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}〜{タスク名}")
    assert await builder_items(user) == ["開始日", "〜", "タスク名"]


async def test_a_custom_separator_can_be_typed(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-tb-pal-start").click()
    user.find(marker="csv-ex-tb-custom").elements.pop().set_value("〜")
    user.find(marker="csv-ex-tb-custom-add").click()
    user.find(marker="csv-ex-tb-pal-end").click()
    assert user.find(marker="csv-ex-quick").elements.pop().value == "{開始日}〜{期限}"


async def test_a_selected_chip_receives_the_next_one_on_its_right(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}/{タスク名}")
    await builder_items(user)
    user.find(marker="csv-ex-tb-item-1").click()  # /
    user.find(marker="csv-ex-tb-pal-end").click()
    assert user.find(marker="csv-ex-quick").elements.pop().value == (
        "{開始日}/{期限}{タスク名}"
    )


async def test_removing_a_chip_updates_the_template(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("{開始日}/{タスク名}")
    await builder_items(user)
    user.find(marker="csv-ex-tb-item-1").elements.pop().set_value(False)
    assert user.find(marker="csv-ex-quick").elements.pop().value == "{開始日}{タスク名}"


async def test_the_builder_is_disabled_while_the_free_format_is_off(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-tb-pal-start").click()
    assert user.find(marker="csv-ex-quick").elements.pop().value == ""


async def test_double_clicking_the_header_chip_edits_it_in_place(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-quick-on").elements.pop().set_value(True)
    user.find(marker="csv-ex-quick").elements.pop().set_value("【{タスク名}】")
    await user.should_see("見出し: まとめ")
    await set_header(user, "予定")
    await user.should_see("見出し: 予定")
    user.find(marker="csv-export-confirm").click()
    assert exported[0].columns[0].header == "予定"


async def test_summary_and_section_choices_reach_the_exported_profile(
    user: User,
) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-summary").elements.pop().set_value(True)
    user.find(marker="csv-ex-section").elements.pop().set_value("breadcrumb")
    user.find(marker="csv-export-confirm").click()
    assert exported[0].summary_rows is True
    assert exported[0].section_mode == "breadcrumb"
