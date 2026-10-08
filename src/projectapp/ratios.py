"""相対比率のパラメータ(要望 20)。NiceGUI に依存しない純粋関数。

相対比率 = 基本比率 + 選んだ段階の判定値の合計。10〜300% に丸めて使う。
"""

from dataclasses import dataclass
from math import isfinite

from projectapp.models import MAX_RATIO, MIN_RATIO, Member, Parameter


@dataclass(frozen=True)
class RatioDetail:
    base: float  # 基本比率
    adjustments: list[tuple[str, str, float]]  # (パラメータ名, 段階名, 判定値)。パラメータの定義の順。存在する選択だけ
    raw: float  # 丸める前の合計
    ratio: float  # 丸めたあと(計算に使う値)
    clamped: bool  # 範囲に丸めたか


def ratio_detail(member: Member, parameters: list[Parameter]) -> RatioDetail:
    """メンバーの相対比率の内訳。存在しないパラメータ・段階への選択は、判定値 0% として数えない。"""
    adjustments: list[tuple[str, str, float]] = []
    for parameter in parameters:
        chosen = member.levels.get(parameter.name)
        level = next((lv for lv in parameter.levels if lv.name == chosen), None) if chosen is not None else None
        if level is not None:
            adjustments.append((parameter.name, level.name, level.value))
    # 保存する値は小数点以下 4 桁までなので、足し算の誤差(0.3 - 0.2 = 0.0999…)で境界を外さないよう丸める
    raw = round(member.ratio + sum(value for _, _, value in adjustments), 4)
    ratio = min(max(raw, MIN_RATIO), MAX_RATIO) if isfinite(raw) else member.ratio
    return RatioDetail(member.ratio, adjustments, raw, ratio, ratio != raw)


def effective_ratio(member: Member, parameters: list[Parameter]) -> float:
    """計算に使う相対比率。"""
    return ratio_detail(member, parameters).ratio
