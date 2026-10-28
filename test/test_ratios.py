"""相対比率のパラメータ(実効比率の計算)。"""

import pytest

from projectapp.models import DEFAULT_RATIO_MAX, DEFAULT_RATIO_MIN, Level, Member, Parameter, Project, RatioLimits, Task
from projectapp.ratios import (
    ParameterEdit,
    apply_parameter_edit,
    deletion_impacts,
    effective_ratio,
    impact_lines,
    limit_note,
    ratio_detail,
    remap_levels,
    task_deletion_impacts,
    validate_parameters,
)

EXPERIENCE = Parameter("経験", [Level("初級", -0.2), Level("中級", 0.0), Level("上級", 0.2)])
FIELD = Parameter("専門", [Level("低", -0.1), Level("高", 0.15)])
PARAMETERS = [EXPERIENCE, FIELD]


def test_without_parameters_or_selections_the_base_ratio_is_used() -> None:
    assert effective_ratio(Member("a", 1.2), []) == pytest.approx(1.2)
    assert effective_ratio(Member("a", 1.2), PARAMETERS) == pytest.approx(1.2)  # 何も選んでいない


def test_the_selected_values_are_added_to_the_base_ratio() -> None:
    member = Member("a", 1.0, {"経験": "上級", "専門": "低"})
    detail = ratio_detail(member, PARAMETERS)
    assert detail.base == 1.0
    assert detail.adjustments == [("経験", "上級", 0.2), ("専門", "低", -0.1)]
    assert detail.raw == pytest.approx(1.1)
    assert detail.ratio == pytest.approx(1.1)
    assert detail.clamped is False
    assert effective_ratio(member, PARAMETERS) == pytest.approx(1.1)


def test_the_adjustments_follow_the_order_of_the_definition() -> None:
    member = Member("a", 1.0, {"専門": "高", "経験": "初級"})  # 辞書の順は逆
    assert [a[0] for a in ratio_detail(member, PARAMETERS).adjustments] == ["経験", "専門"]


@pytest.mark.parametrize(
    ("base", "level", "raw", "ratio", "clamped"),
    [
        (0.4, "初級", 0.2, 0.5, True),  # 下限(50%)に丸める
        (0.7, "初級", 0.5, 0.5, False),  # ちょうど下限
        (1.4, "上級", 1.6, 1.5, True),  # 上限(150%)に丸める
        (1.3, "上級", 1.5, 1.5, False),  # ちょうど上限
    ],
)
def test_the_result_is_rounded_into_the_ratio_range(base: float, level: str, raw: float, ratio: float, clamped: bool) -> None:
    detail = ratio_detail(Member("a", base, {"経験": level}), PARAMETERS)
    assert detail.raw == pytest.approx(raw)
    assert detail.ratio == pytest.approx(ratio)
    assert detail.clamped is clamped


def test_selections_that_point_nowhere_count_as_zero() -> None:
    member = Member("a", 1.0, {"消えた": "上級", "経験": "存在しない段階", "専門": "高"})
    detail = ratio_detail(member, PARAMETERS)
    assert detail.adjustments == [("専門", "高", 0.15)]
    assert detail.ratio == pytest.approx(1.15)


def test_a_parameter_without_levels_adds_nothing() -> None:
    assert effective_ratio(Member("a", 1.0, {"空": "x"}), [Parameter("空", [])]) == 1.0


def edit_of(parameters: list[Parameter], parameter_map: dict, level_map: dict | None = None) -> ParameterEdit:
    return ParameterEdit(parameters, parameter_map, level_map or {})


def project_with(*members: Member, parameters: list[Parameter]) -> Project:
    return Project("p", members=list(members), parameters=parameters)


def test_an_unchanged_edit_changes_nothing() -> None:
    edit = edit_of(
        PARAMETERS,
        {"経験": "経験", "専門": "専門"},
        {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}, "専門": {"低": "低", "高": "高"}},
    )
    assert edit.changes(PARAMETERS) is False
    assert edit_of(PARAMETERS, {"経験": "経験", "専門": None}).changes(PARAMETERS) is True  # 削除
    assert edit_of(PARAMETERS, {"経験": "経験"}, {"経験": {"初級": "弱"}}).changes(PARAMETERS) is True  # 段階の改名
    assert edit_of([Parameter("経験", [])], {"経験": "経験"}).changes(PARAMETERS) is True  # 内容の変更


def test_renaming_a_parameter_and_a_level_carries_the_selection() -> None:
    project = project_with(Member("a", 1.0, {"経験": "上級"}), parameters=[EXPERIENCE])
    new = [Parameter("スキル", [Level("初級", -0.2), Level("エキスパート", 0.2)])]
    apply_parameter_edit(project, edit_of(new, {"経験": "スキル"}, {"経験": {"初級": "初級", "上級": "エキスパート"}}))
    assert project.parameters == new
    assert project.members[0].levels == {"スキル": "エキスパート"}


def test_swapping_two_parameter_names_updates_each_selection_once() -> None:
    a, b = Parameter("A", [Level("x", 0.1)]), Parameter("B", [Level("y", 0.2)])
    project = project_with(Member("m", 1.0, {"A": "x", "B": "y"}), parameters=[a, b])
    new = [Parameter("B", [Level("x", 0.1)]), Parameter("A", [Level("y", 0.2)])]
    apply_parameter_edit(project, edit_of(new, {"A": "B", "B": "A"}, {"A": {"x": "x"}, "B": {"y": "y"}}))
    assert project.members[0].levels == {"B": "x", "A": "y"}


def test_a_deleted_parameter_does_not_leak_into_a_renamed_one() -> None:
    # 古い「A」を削除し、「B」を「A」に改名する。古い「A」の選択が、新しい「A」に化けてはいけない
    old_a, old_b = Parameter("A", [Level("x", 0.1)]), Parameter("B", [Level("x", 0.3)])
    project = project_with(Member("m", 1.0, {"A": "x"}), Member("n", 1.0, {"B": "x"}), parameters=[old_a, old_b])
    new = [Parameter("A", [Level("x", 0.3)])]
    apply_parameter_edit(project, edit_of(new, {"A": None, "B": "A"}, {"B": {"x": "x"}}))
    assert project.members[0].levels == {}  # 古い A の選択は外れた
    assert project.members[1].levels == {"A": "x"}  # B からの引き継ぎ


def test_deleting_a_level_clears_only_that_selection() -> None:
    project = project_with(
        Member("a", 1.0, {"経験": "上級", "専門": "高"}), Member("b", 1.0, {"経験": "初級"}), parameters=PARAMETERS
    )
    new = [Parameter("経験", [Level("初級", -0.2), Level("中級", 0.0)]), FIELD]
    edit = edit_of(
        new,
        {"経験": "経験", "専門": "専門"},
        {"経験": {"初級": "初級", "中級": "中級", "上級": None}, "専門": {"低": "低", "高": "高"}},
    )
    apply_parameter_edit(project, edit)
    assert project.members[0].levels == {"専門": "高"}
    assert project.members[1].levels == {"経験": "初級"}


def test_selections_that_point_nowhere_are_dropped_by_an_edit() -> None:
    project = project_with(Member("a", 1.0, {"消えた": "x", "経験": "上級"}), parameters=[EXPERIENCE])
    edit = edit_of([EXPERIENCE], {"経験": "経験"}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    apply_parameter_edit(project, edit)
    assert project.members[0].levels == {"経験": "上級"}


def test_changing_a_level_value_changes_the_effective_ratio_at_once() -> None:
    project = project_with(Member("a", 1.0, {"経験": "上級"}), parameters=[EXPERIENCE])
    new = [Parameter("経験", [Level("初級", -0.2), Level("中級", 0.0), Level("上級", 0.5)])]
    edit = edit_of(new, {"経験": "経験"}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    apply_parameter_edit(project, edit)
    assert effective_ratio(project.members[0], project.parameters) == pytest.approx(1.5)


def test_deletion_impacts_count_members_per_deleted_parameter_and_level() -> None:
    project = project_with(
        Member("a", 1.0, {"経験": "上級", "専門": "高"}),
        Member("b", 1.0, {"経験": "上級"}),
        Member("c", 1.0, {"経験": "初級"}),
        parameters=PARAMETERS,
    )
    new = [Parameter("経験", [Level("初級", -0.2), Level("中級", 0.0)])]
    edit = edit_of(new, {"経験": "経験", "専門": None}, {"経験": {"初級": "初級", "中級": "中級", "上級": None}})
    assert deletion_impacts(project, edit) == [("「経験」の「上級」", 2), ("「専門」", 1)]


def test_deleting_something_nobody_uses_has_no_impact() -> None:
    project = project_with(Member("a", 1.0, {"経験": "初級"}), parameters=PARAMETERS)
    edit = edit_of([EXPERIENCE], {"経験": "経験", "専門": None}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    assert deletion_impacts(project, edit) == []


@pytest.mark.parametrize(
    "bad",
    [
        [Parameter("", [])],
        [Parameter("  ", [])],
        [Parameter("A", []), Parameter("A", [])],
        [Parameter("A", [Level("", 0.1)])],
        [Parameter("A", [Level("x", 0.1), Level("x", 0.2)])],
        [Parameter("A", [Level("x", -0.91)])],
        [Parameter("A", [Level("x", 2.91)])],
        [Parameter("A", [Level("x", float("nan"))])],
        [Parameter("A", [Level("x", float("inf"))])],
    ],
)
def test_validate_parameters_rejects_bad_definitions(bad: list[Parameter]) -> None:
    with pytest.raises(ValueError):
        validate_parameters(bad)


def test_validate_parameters_accepts_boundaries_and_empty_levels() -> None:
    validate_parameters([Parameter("A", [Level("lo", -0.9), Level("hi", 2.9)]), Parameter("B", [])])
    validate_parameters([])


def test_remap_levels_follows_renames_and_drops_deleted() -> None:
    edit = ParameterEdit(
        [Parameter("経験値", [Level("上", 0.2)])],
        {"経験": "経験値", "言語": None},
        {"経験": {"上級": "上", "初級": None}, "言語": {"日本語": None}},
    )
    levels = {"経験": "上級", "言語": "日本語", "不明": "x"}
    assert remap_levels(levels, edit) == {"経験値": "上"}
    assert remap_levels({"経験": "初級"}, edit) == {}


def test_remap_levels_does_not_change_its_argument() -> None:
    edit = ParameterEdit([Parameter("a", [])], {"a": "a"}, {"a": {}})
    levels = {"a": "x"}
    remap_levels(levels, edit)
    assert levels == {"a": "x"}


def test_only_the_named_parameters_are_added() -> None:
    member = Member("a", 1.0, {"経験": "上級", "専門": "低"})
    assert effective_ratio(member, PARAMETERS, only=["経験"]) == pytest.approx(1.2)
    assert effective_ratio(member, PARAMETERS, only=["専門"]) == pytest.approx(0.9)
    detail = ratio_detail(member, PARAMETERS, only=["経験"])
    assert detail.adjustments == [("経験", "上級", 0.2)]
    assert detail.raw == pytest.approx(1.2)


def test_no_or_empty_only_means_every_parameter() -> None:
    member = Member("a", 1.0, {"経験": "上級", "専門": "低"})
    assert effective_ratio(member, PARAMETERS, only=None) == pytest.approx(1.1)
    assert effective_ratio(member, PARAMETERS, only=[]) == pytest.approx(1.1)


def test_a_named_parameter_without_a_chosen_level_adds_nothing() -> None:
    member = Member("a", 1.0, {"経験": "上級"})  # 専門は未選択
    assert effective_ratio(member, PARAMETERS, only=["専門"]) == pytest.approx(1.0)


def test_unregistered_names_are_ignored_and_the_result_is_still_clamped() -> None:
    member = Member("a", 1.4, {"経験": "上級"})
    assert effective_ratio(member, PARAMETERS, only=["ない"]) == pytest.approx(1.4)
    big = [Parameter("経験", [Level("上級", 0.5)])]
    assert effective_ratio(member, big, only=["経験"]) == pytest.approx(1.5)  # 1.9 を 150% に丸める


def test_renaming_follows_in_tasks_and_deleting_removes_the_name() -> None:
    project = project_with(Member("a", 1.0), parameters=PARAMETERS)
    project.tasks.append(Task("t", parameters=["経験", "専門", "ない"]))
    new = [Parameter("スキル", [Level("初級", -0.2)])]
    edit = edit_of(new, {"経験": "スキル", "専門": None}, {"経験": {"初級": "初級"}})
    apply_parameter_edit(project, edit)
    assert project.tasks[0].parameters == ["スキル", "ない"]  # 改名は追従、削除は外す、登録外は触らない


def test_task_deletion_impacts_count_tasks_per_deleted_parameter() -> None:
    project = project_with(Member("a", 1.0), parameters=PARAMETERS)
    project.tasks += [Task("x", parameters=["専門"]), Task("y", parameters=["専門", "経験"]), Task("z", parameters=["経験"])]
    edit = edit_of([EXPERIENCE], {"経験": "経験", "専門": None}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    assert task_deletion_impacts(project, edit) == [("「専門」", 2)]


def test_impact_lines_list_members_then_tasks() -> None:
    project = project_with(Member("a", 1.0, {"専門": "高"}), parameters=PARAMETERS)
    project.tasks.append(Task("x", parameters=["専門"]))
    edit = edit_of([EXPERIENCE], {"経験": "経験", "専門": None}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    assert impact_lines(project, edit) == [
        "「専門」を選んでいるメンバーが1人います",
        "「専門」を付けているタスクが1件あります",
    ]


BIG = Parameter("大", [Level("高", 0.5), Level("低", -0.5)])
BIG2 = Parameter("大2", [Level("高", 0.5)])
BIG3 = Parameter("大3", [Level("高", 0.5)])
PILE = [BIG, BIG2, BIG3]
ALL_HIGH = {"大": "高", "大2": "高", "大3": "高"}


def test_without_limits_the_default_range_applies() -> None:
    member = Member("a", 1.0, ALL_HIGH)  # 加算分 +150% → 250% を、既定の上限 150% に丸める
    assert effective_ratio(member, PILE) == pytest.approx(1.5)
    assert effective_ratio(member, PILE, limits=RatioLimits()) == pytest.approx(1.5)
    assert effective_ratio(member, PILE, limits=None) == pytest.approx(1.5)


def test_the_upper_limit_caps_the_ratio_itself() -> None:
    detail = ratio_detail(Member("a", 1.0, ALL_HIGH), PILE, limits=RatioLimits(upper=1.5))
    assert detail.raw == pytest.approx(2.5)
    assert detail.ratio == pytest.approx(1.5)
    assert detail.limited is True and detail.clamped is True


def test_the_lower_limit_floors_the_ratio_itself() -> None:
    detail = ratio_detail(Member("a", 1.0, {"大": "低"}), PILE, limits=RatioLimits(lower=0.7))
    assert detail.raw == pytest.approx(0.5)
    assert detail.ratio == pytest.approx(0.7)
    assert detail.limited is True


def test_a_ratio_inside_the_limits_is_not_limited() -> None:
    detail = ratio_detail(Member("a", 1.0, {"経験": "上級"}), PARAMETERS, limits=RatioLimits(lower=0.5, upper=1.5))
    assert detail.limited is False and detail.clamped is False
    assert detail.ratio == pytest.approx(1.2)


def test_a_ratio_exactly_on_a_limit_is_not_reported_as_limited() -> None:
    detail = ratio_detail(Member("a", 1.0, {"大": "高"}), PILE, limits=RatioLimits(upper=1.5))
    assert detail.limited is False and detail.clamped is False
    assert detail.ratio == pytest.approx(1.5)


def test_the_limits_also_apply_to_the_base_ratio_alone() -> None:
    limits = RatioLimits(lower=0.5, upper=1.5)
    assert effective_ratio(Member("fast", 2.0), PILE, limits=limits) == pytest.approx(1.5)
    assert effective_ratio(Member("slow", 0.3), PILE, limits=limits) == pytest.approx(0.5)


def test_the_limits_apply_to_the_tagged_parameters_only() -> None:
    member = Member("a", 1.0, ALL_HIGH)
    assert effective_ratio(member, PILE, ["大"], RatioLimits(upper=1.2)) == pytest.approx(1.2)
    assert effective_ratio(member, PILE, ["大"], RatioLimits(upper=1.8)) == pytest.approx(1.5)  # 制限内


def test_only_a_configured_limit_counts_as_limited() -> None:
    high = ratio_detail(Member("a", 1.0, ALL_HIGH), PILE)  # 既定の範囲(50〜150%)の丸めは制限と呼ばない
    assert high.ratio == pytest.approx(1.5) and high.clamped is True and high.limited is False
    over = ratio_detail(Member("b", 3.5), PILE)
    assert over.ratio == pytest.approx(1.5) and over.clamped is True and over.limited is False


def test_limit_note_names_the_limit_only_when_it_was_applied() -> None:
    up = RatioLimits(upper=1.5)
    assert limit_note(ratio_detail(Member("a", 1.0, ALL_HIGH), PILE, limits=up), up) == "相対比率 250% → 上限 150% に制限"
    down = RatioLimits(lower=0.7)
    low = Member("b", 1.0, {"大": "低"})
    assert limit_note(ratio_detail(low, PILE, limits=down), down) == "相対比率 50% → 下限 70% に制限"
    assert limit_note(ratio_detail(Member("a", 1.0, ALL_HIGH), PILE), None) == ""
    wide = RatioLimits(upper=3.0)
    assert limit_note(ratio_detail(Member("a", 1.0, ALL_HIGH), PILE, limits=wide), wide) == ""


@pytest.mark.parametrize("levels", [{}, {"経験": "上級"}, {"経験": "初級", "専門": "高"}, {"専門": "低"}])
@pytest.mark.parametrize("only", [None, ["経験"], ["専門"]])
def test_no_limits_gives_the_same_detail_as_before(levels: dict[str, str], only: list[str] | None) -> None:
    member = Member("a", 1.0, levels)
    plain = ratio_detail(member, PARAMETERS, only)
    for limits in (None, RatioLimits(), RatioLimits(None, None)):
        detail = ratio_detail(member, PARAMETERS, only, limits)
        assert (detail.base, detail.adjustments, detail.raw, detail.ratio, detail.clamped) == (
            plain.base,
            plain.adjustments,
            plain.raw,
            plain.ratio,
            plain.clamped,
        )
        assert detail.limited is False


def test_the_default_range_is_fifty_to_one_fifty_percent() -> None:
    assert (DEFAULT_RATIO_MIN, DEFAULT_RATIO_MAX) == (0.5, 1.5)
    fast = ratio_detail(Member("fast", 2.0), PILE)
    slow = ratio_detail(Member("slow", 0.3), PILE)
    assert (fast.ratio, fast.clamped, fast.limited) == (1.5, True, False)
    assert (slow.ratio, slow.clamped, slow.limited) == (0.5, True, False)
    assert effective_ratio(Member("a", 1.0, ALL_HIGH), PILE) == pytest.approx(1.5)  # 加算分 +150% も 150% で止まる
    assert effective_ratio(Member("ok", 1.4), PILE) == pytest.approx(1.4)


def test_a_configured_limit_narrows_the_default_range() -> None:
    limits = RatioLimits(upper=1.2, lower=0.8)
    assert effective_ratio(Member("a", 1.0, ALL_HIGH), PILE, limits=limits) == pytest.approx(1.2)
    assert effective_ratio(Member("b", 0.6), PILE, limits=limits) == pytest.approx(0.8)
    assert effective_ratio(Member("c", 1.0), PILE, limits=RatioLimits(upper=1.2)) == pytest.approx(1.0)
