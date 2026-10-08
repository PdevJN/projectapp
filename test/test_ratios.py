"""相対比率のパラメータ(実効比率の計算)。"""

import pytest

from projectapp.models import Level, Member, Parameter, Project
from projectapp.ratios import (
    ParameterEdit,
    apply_parameter_edit,
    deletion_impacts,
    effective_ratio,
    ratio_detail,
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
        (0.2, "初級", 0.0, 0.1, True),  # 下限に丸める
        (0.3, "初級", 0.1, 0.1, False),  # ちょうど下限
        (2.9, "上級", 3.1, 3.0, True),  # 上限に丸める
        (2.8, "上級", 3.0, 3.0, False),  # ちょうど上限
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
