"""相対比率のパラメータ(要望 20)。NiceGUI に依存しない純粋関数。

相対比率 = 基本比率 + 選んだ段階の判定値の合計。50〜150%(プロジェクトの設定で狭められる)に丸めて使う。
"""

from collections.abc import Collection
from dataclasses import dataclass
from math import isfinite

from projectapp.models import (
    DEFAULT_RATIO_MAX,
    DEFAULT_RATIO_MIN,
    MAX_LEVEL_VALUE,
    MAX_RATIO,
    MIN_LEVEL_VALUE,
    MIN_RATIO,
    Member,
    Parameter,
    Project,
    RatioLimits,
)


@dataclass(frozen=True)
class RatioDetail:
    base: float  # 基本比率
    adjustments: list[tuple[str, str, float]]  # (パラメータ名, 段階名, 判定値)。パラメータの定義の順。存在する選択だけ
    raw: float  # 丸める前の合計
    ratio: float  # 丸めたあと(計算に使う値)
    clamped: bool  # 範囲に丸めたか
    limited: bool = False  # 設定の上限か下限で収めたか(既定の 50〜150% の丸めは含めない)。丸め対象外では、安全範囲で収めたか
    unclamped: bool = False  # 丸め対象外のメンバー(安全範囲 10〜300% だけで収めた)


def ratio_detail(
    member: Member,
    parameters: list[Parameter],
    only: Collection[str] | None = None,
    limits: RatioLimits | None = None,
) -> RatioDetail:
    """メンバーの相対比率の内訳。存在しないパラメータ・段階への選択は、判定値 0% として数えない。
    only があれば、その名前のパラメータだけ足す(None か空は全パラメータ。タスクに付けたパラメータの指定)。
    メンバーが丸め対象外(ratio_unclamped)なら、limits は見ず、10〜300% だけで収める。
    limits があれば、相対比率(基本比率 + 判定値の合計)を設定の下限・上限に収める(空欄の側は 50〜150%)。"""
    counted = set(only) if only else None
    adjustments: list[tuple[str, str, float]] = []
    for parameter in parameters:
        if counted is not None and parameter.name not in counted:
            continue
        chosen = member.levels.get(parameter.name)
        level = next((lv for lv in parameter.levels if lv.name == chosen), None) if chosen is not None else None
        if level is not None:
            adjustments.append((parameter.name, level.name, level.value))
    # 保存する値は小数点以下 4 桁までなので、足し算の誤差(0.3 - 0.2 = 0.0999…)で境界を外さないよう丸める
    raw = round(member.ratio + sum(value for _, _, value in adjustments), 4)
    if member.ratio_unclamped:
        # 丸め対象外: 既定の 50〜150% も設定の上限・下限も使わず、安全範囲(10〜300%)だけで収める
        ratio = min(max(raw, MIN_RATIO), MAX_RATIO) if isfinite(raw) else member.ratio
        return RatioDetail(member.ratio, adjustments, raw, ratio, ratio != raw, ratio != raw, True)
    lower = DEFAULT_RATIO_MIN if limits is None or limits.lower is None else limits.lower
    upper = DEFAULT_RATIO_MAX if limits is None or limits.upper is None else limits.upper
    ratio = min(max(raw, lower), upper) if isfinite(raw) else member.ratio
    limited = limits is not None and (
        (limits.upper is not None and raw > limits.upper) or (limits.lower is not None and raw < limits.lower)
    )
    return RatioDetail(member.ratio, adjustments, raw, ratio, ratio != raw, limited)


def effective_ratio(
    member: Member,
    parameters: list[Parameter],
    only: Collection[str] | None = None,
    limits: RatioLimits | None = None,
) -> float:
    """計算に使う相対比率。"""
    return ratio_detail(member, parameters, only, limits).ratio


def limit_note(detail: RatioDetail, limits: RatioLimits | None) -> str:
    """内訳に添える注記。設定の上限・下限で収めたときだけ。例: 相対比率 250% → 上限 150% に制限。"""
    if detail.unclamped:
        if not detail.limited:
            return ""
        edge = "上限 300%" if detail.raw > detail.ratio else "下限 10%"
        return f"相対比率 {detail.raw * 100:g}% → 安全範囲の{edge} に制限"
    if limits is None or not detail.limited:
        return ""
    if limits.upper is not None and detail.raw > limits.upper:
        return f"相対比率 {detail.raw * 100:g}% → 上限 {limits.upper * 100:g}% に制限"
    assert limits.lower is not None
    return f"相対比率 {detail.raw * 100:g}% → 下限 {limits.lower * 100:g}% に制限"


@dataclass(frozen=True)
class ParameterEdit:
    """パラメータの定義の編集。旧い名前から新しい名前への対応(削除は None)で、メンバーの選択を更新する。"""

    parameters: list[Parameter]  # 新しい定義
    parameter_map: dict[str, str | None]  # 旧パラメータ名 → 新しい名前(削除は None)
    level_map: dict[str, dict[str, str | None]]  # 旧パラメータ名 → {旧段階名: 新しい段階名(削除は None)}

    def changes(self, current: list[Parameter]) -> bool:
        """定義が変わる、または改名・削除がある。"""
        if self.parameters != current:
            return True
        if any(old != new for old, new in self.parameter_map.items()):
            return True
        return any(old != new for levels in self.level_map.values() for old, new in levels.items())


def validate_parameters(parameters: list[Parameter]) -> None:
    """名前の空・重複、判定値の範囲外・非有限は ValueError。段階が 0 件のパラメータは許す。"""
    names: set[str] = set()
    for parameter in parameters:
        name = parameter.name.strip()
        if not name:
            raise ValueError("パラメータの名前を入力してください")
        if name in names:
            raise ValueError(f"パラメータ名が重複しています: {name}")
        names.add(name)
        level_names: set[str] = set()
        for level in parameter.levels:
            level_name = level.name.strip()
            if not level_name:
                raise ValueError(f"{name} の段階の名前を入力してください")
            if level_name in level_names:
                raise ValueError(f"{name} の段階名が重複しています: {level_name}")
            level_names.add(level_name)
            if not isfinite(level.value) or not MIN_LEVEL_VALUE - 1e-9 <= level.value <= MAX_LEVEL_VALUE + 1e-9:
                raise ValueError(
                    f"判定値は{MIN_LEVEL_VALUE * 100:g}〜+{MAX_LEVEL_VALUE * 100:g}%で入力してください"
                )


def remap_levels(levels: dict[str, str], edit: ParameterEdit) -> dict[str, str]:
    """段階の選択(パラメータ名 → 段階名)を、新しい定義へ写す。削除された参照と、存在しない参照は外す。
    対応は旧い名前で引くので、入れ替えや、削除と改名の組み合わせでも、選択が取り違えられない。"""
    updated: dict[str, str] = {}
    for old_parameter, old_level in levels.items():
        new_parameter = edit.parameter_map.get(old_parameter)
        if new_parameter is None:
            continue
        new_level = edit.level_map.get(old_parameter, {}).get(old_level)
        if new_level is None:
            continue
        updated[new_parameter] = new_level
    return updated


def apply_parameter_edit(project: Project, edit: ParameterEdit) -> None:
    """定義を置き換え、全メンバーの選択とタスクに付けたパラメータを更新する。"""
    for member in project.members:
        member.levels = remap_levels(member.levels, edit)
    for task in project.all_tasks():
        # 対応表にない名前(登録外)は触らない。改名は新しい名前に、削除(None)は外す
        renamed = (edit.parameter_map.get(name, name) for name in task.parameters)
        task.parameters = list(dict.fromkeys(name for name in renamed if name is not None))
    project.parameters = edit.parameters


def deletion_impacts(project: Project, edit: ParameterEdit) -> list[tuple[str, int]]:
    """削除で選択が外れるメンバーの数(パラメータの削除 → 段階の削除の順)。数が 0 のものは含めない。"""
    impacts: list[tuple[str, int]] = []
    for old_parameter, new_parameter in edit.parameter_map.items():
        if new_parameter is None:
            count = sum(1 for m in project.members if old_parameter in m.levels)
            if count:
                impacts.append((f"「{old_parameter}」", count))
            continue
        for old_level, new_level in edit.level_map.get(old_parameter, {}).items():
            if new_level is None:
                count = sum(1 for m in project.members if m.levels.get(old_parameter) == old_level)
                if count:
                    impacts.append((f"「{old_parameter}」の「{old_level}」", count))
    return impacts


def task_deletion_impacts(project: Project, edit: ParameterEdit) -> list[tuple[str, int]]:
    """パラメータの削除で外れるタスクの数(パラメータの定義の順)。数が 0 のものは含めない。"""
    impacts: list[tuple[str, int]] = []
    for old_parameter, new_parameter in edit.parameter_map.items():
        if new_parameter is None:
            count = sum(1 for t in project.all_tasks() if old_parameter in t.parameters)
            if count:
                impacts.append((f"「{old_parameter}」", count))
    return impacts


def impact_lines(project: Project, edit: ParameterEdit) -> list[str]:
    """削除の確認ダイアログに出す行。メンバーの選択、続いてタスクに付けたもの。"""
    members = [f"{label}を選んでいるメンバーが{count}人います" for label, count in deletion_impacts(project, edit)]
    tasks = [f"{label}を付けているタスクが{count}件あります" for label, count in task_deletion_impacts(project, edit)]
    return members + tasks
