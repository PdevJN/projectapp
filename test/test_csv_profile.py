import pytest

from projectapp.csv_profile import (
    SMARTSHEET,
    CsvColumn,
    CsvField,
    CsvProfile,
    best_profile,
    guess_columns,
    header_key,
    profile_from_config,
    profile_to_config,
    profiles_from_config,
    resolve_columns,
    validate_profile,
)


def profile(
    *pairs: tuple[CsvField, str], name: str = "自作", **kw: object
) -> CsvProfile:
    return CsvProfile(name, tuple(CsvColumn(f, h) for f, h in pairs), **kw)  # type: ignore[arg-type]


def test_header_key_ignores_width_case_and_spaces() -> None:
    assert header_key(" Ｔask  Name ") == "taskname"


def test_smartsheet_has_the_template_columns_in_order() -> None:
    assert [c.header for c in SMARTSHEET.columns] == [
        "WBS 番号",
        "タスクのタイトル",
        "タスクオーナー",
        "開始日",
        "期限",
        "期間",
        "タスク完了率",
    ]
    assert SMARTSHEET.delimiter == "\t" and SMARTSHEET.blank_rows == 2
    assert SMARTSHEET.owner_separator == "" and SMARTSHEET.date_format == "ja"


def test_guess_columns_uses_aliases_and_keeps_the_original_header() -> None:
    cols = guess_columns(
        [
            "No",
            "Task Name",
            "Assignee",
            "Start Date",
            "Due",
            "% Complete",
            "Hours",
            "メモ",
        ]
    )
    assert {c.field: c.header for c in cols} == {
        CsvField.WBS: "No",
        CsvField.TITLE: "Task Name",
        CsvField.OWNER: "Assignee",
        CsvField.START: "Start Date",
        CsvField.END: "Due",
        CsvField.PROGRESS: "% Complete",
        CsvField.EFFORT: "Hours",
    }


def test_guess_columns_uses_a_field_once_even_with_duplicate_headers() -> None:
    cols = guess_columns(["名前", "名前", "担当"])
    assert [c.field for c in cols].count(CsvField.TITLE) == 1


def test_resolve_columns_prefers_the_profile_header_then_aliases() -> None:
    p = profile((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"))
    assert resolve_columns(p, ["x", "件名", "担当者"]) == {
        CsvField.TITLE: 1,
        CsvField.OWNER: 2,
    }


def test_resolve_columns_takes_the_first_of_duplicate_headers() -> None:
    p = profile((CsvField.TITLE, "名前"))
    assert resolve_columns(p, ["名前", "名前"]) == {CsvField.TITLE: 0}


def test_smartsheet_accepts_the_other_owner_spelling() -> None:
    header = ["WBS 番号", "タスクのタイトル", "タスクのオーナー"]
    assert resolve_columns(SMARTSHEET, header)[CsvField.OWNER] == 2


def test_best_profile_needs_half_of_the_columns_to_match() -> None:
    a = profile((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), name="A")
    b = profile((CsvField.TITLE, "Subject"), (CsvField.OWNER, "Who"), name="B")
    assert best_profile(["件名", "担当", "開始"], [a, b]) is a
    assert best_profile(["x", "y"], [a, b]) is None


@pytest.mark.parametrize(
    ("bad", "word"),
    [
        (profile((CsvField.OWNER, "担当")), "タスク名"),
        (profile((CsvField.TITLE, "a"), (CsvField.TITLE, "b")), "重複"),
        (profile((CsvField.TITLE, "")), "見出し"),
        (profile((CsvField.TITLE, "a"), name=""), "名前"),
        (profile((CsvField.TITLE, "a"), name="Smartsheet"), "予約"),
        (profile((CsvField.TITLE, "a"), delimiter="|"), "区切り"),
        (profile((CsvField.TITLE, "a"), encoding="latin-1"), "文字コード"),
        (profile((CsvField.TITLE, "a"), owner_separator="abcd"), "担当の区切り"),
    ],
)
def test_validate_profile_rejects(bad: CsvProfile, word: str) -> None:
    assert word in (validate_profile(bad) or "")


def test_validate_profile_accepts_a_good_one() -> None:
    good = profile((CsvField.TITLE, "件名"), delimiter=";", encoding="cp932")
    assert validate_profile(good) is None


def test_config_round_trip() -> None:
    p = profile(
        (CsvField.TITLE, "件名"),
        (CsvField.EFFORT, "工数"),
        delimiter=";",
        encoding="utf-8-sig",
        date_format="ymd-slash",
        owner_separator="/",
    )
    assert profile_from_config(profile_to_config(p)) == p


def test_profiles_from_config_drops_only_the_broken_ones() -> None:
    good = profile_to_config(profile((CsvField.TITLE, "件名"), name="良"))
    dup = profile_to_config(profile((CsvField.TITLE, "別"), name="良"))
    raw = [good, {"name": "壊", "columns": "x"}, 5, dup, {"name": "無題"}]
    assert [p.name for p in profiles_from_config(raw)] == ["良"]
    assert profiles_from_config("x") == [] and profiles_from_config(None) == []


def test_progress_percent_defaults_on_and_round_trips() -> None:
    assert SMARTSHEET.progress_percent is True
    p = profile((CsvField.TITLE, "件名"), progress_percent=False)
    assert profile_from_config(profile_to_config(p)) == p
    old = profile_to_config(profile((CsvField.TITLE, "件名")))
    del old["progress_percent"]
    assert profile_from_config(old).progress_percent is True  # type: ignore[union-attr]


from projectapp.csv_profile import (  # noqa: E402
    FIELD_LABELS,
    render_template,
    split_template,
    template_problem,
)

SD = {CsvField.START: "2026-10-05", CsvField.END: "2026-10-09"}


def test_render_template_fills_the_values() -> None:
    assert render_template("{開始日}〜{期限}", SD, False) == "2026-10-05〜2026-10-09"


@pytest.mark.parametrize(
    ("values", "expected_drop", "expected_keep"),
    [
        ({CsvField.START: "A"}, "A", "A〜"),
        ({CsvField.END: "B"}, "B", "〜B"),
        ({}, "", "〜"),
    ],
)
def test_empty_fields_drop_their_separator_unless_kept(
    values: dict, expected_drop: str, expected_keep: str
) -> None:
    assert render_template("{開始日}〜{期限}", values, False) == expected_drop
    assert render_template("{開始日}〜{期限}", values, True) == expected_keep


def test_literals_around_the_fields_stay_when_something_is_present() -> None:
    t = "【{担当}・{担当の割合}】"
    assert render_template(t, {CsvField.OWNER: "田中"}, False) == "【田中】"
    assert render_template(t, {}, False) == ""


def test_split_template_reverses_render_template() -> None:
    assert split_template("{開始日}〜{期限}", "2026-10-05〜2026-10-09") == {
        CsvField.START: "2026-10-05",
        CsvField.END: "2026-10-09",
    }
    assert split_template("{開始日}〜{期限}", "2026-10-05") == {
        CsvField.START: "2026-10-05",
        CsvField.END: "",
    }
    assert split_template("{WBS 番号} {タスク名}", "1.1 設計 案") == {
        CsvField.WBS: "1.1",
        CsvField.TITLE: "設計 案",
    }
    assert split_template("{開始日}〜{期限}", "")[CsvField.START] == ""


@pytest.mark.parametrize(
    ("template", "word"),
    [
        ("{開始日}{期限}", "区切り"),
        ("{開始日}〜{開始日}", "重複"),
        ("{未知}", "書式"),
        ("開始", "項目"),
        ("{開始日", "書式"),
    ],
)
def test_template_problem(template: str, word: str) -> None:
    assert word in (template_problem(template) or "")


def test_a_template_column_covers_its_fields_and_round_trips() -> None:
    p = CsvProfile(
        "結合",
        (
            CsvColumn(CsvField.TITLE, "件名"),
            CsvColumn(CsvField.START, "期間", "{開始日}〜{期限}"),
        ),
        keep_separators=True,
    )
    assert validate_profile(p) is None
    assert p.all_fields == [CsvField.TITLE, CsvField.START, CsvField.END]
    assert resolve_columns(p, ["件名", "期間"]) == {
        CsvField.TITLE: 0,
        CsvField.START: 1,
        CsvField.END: 1,
    }
    assert profile_from_config(profile_to_config(p)) == p


def test_a_field_cannot_be_both_in_a_template_and_its_own_column() -> None:
    p = CsvProfile(
        "重複",
        (
            CsvColumn(CsvField.TITLE, "件名"),
            CsvColumn(CsvField.START, "期間", "{開始日}〜{期限}"),
            CsvColumn(CsvField.END, "期限"),
        ),
    )
    assert "重複" in (validate_profile(p) or "")


def test_the_template_title_may_be_inside_a_template() -> None:
    p = CsvProfile(
        "WBS付き", (CsvColumn(CsvField.WBS, "名前", "{WBS 番号} {タスク名}"),)
    )
    assert validate_profile(p) is None


def test_a_template_column_may_have_no_header_but_a_plain_column_may_not() -> None:
    ok = CsvProfile(
        "見出しなし",
        (
            CsvColumn(CsvField.TITLE, "件名"),
            CsvColumn(CsvField.START, "", "{開始日}〜{期限}"),
        ),
    )
    assert validate_profile(ok) is None
    assert profile_from_config(profile_to_config(ok)) == ok
    bad = CsvProfile("見出しなし", (CsvColumn(CsvField.TITLE, ""),))
    assert "見出し" in (validate_profile(bad) or "")


def test_a_template_may_hold_up_to_seven_fields() -> None:
    seven = "/".join(f"{{{FIELD_LABELS[f]}}}" for f in list(CsvField)[:7])
    eight = "/".join(f"{{{FIELD_LABELS[f]}}}" for f in list(CsvField)[:8])
    assert template_problem(seven) is None
    assert "1〜7" in (template_problem(eight) or "")


def test_seven_fields_render_and_split_back() -> None:
    fields = list(CsvField)[:7]
    template = "/".join(f"{{{FIELD_LABELS[f]}}}" for f in fields)
    values = {f: f"v{i}" for i, f in enumerate(fields)}
    text = render_template(template, values, False)
    assert split_template(template, text) == values
    assert split_template(template, "v0/v1") is not None  # 後ろが空の形も読む


def test_hierarchy_options_default_to_the_current_behaviour_and_round_trip() -> None:
    from projectapp.csv_profile import (
        CsvColumn,
        CsvField,
        CsvProfile,
        profile_from_config,
        profile_to_config,
    )

    base = CsvProfile("p", (CsvColumn(CsvField.TITLE, "名前"),))
    assert (base.summary_rows, base.section_mode) == (False, "row")
    raw = profile_to_config(base)
    raw.pop("summary_rows"), raw.pop("section_mode"), raw.pop("title_breadcrumb")
    assert profile_from_config(raw) == base  # キーのない古い設定
    custom = CsvProfile(
        "p",
        base.columns,
        summary_rows=True,
        section_mode="breadcrumb",
        title_breadcrumb=True,
    )
    assert profile_from_config(profile_to_config(custom)) == custom
    raw = profile_to_config(base) | {"section_mode": "bogus"}
    assert profile_from_config(raw) is None
