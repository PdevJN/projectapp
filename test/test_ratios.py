"""相対比率のパラメータ(実効比率の計算)。"""

import pytest

from projectapp.models import Level, Member, Parameter
from projectapp.ratios import effective_ratio, ratio_detail

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
