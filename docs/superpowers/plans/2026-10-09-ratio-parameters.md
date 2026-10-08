# メンバーの相対比率のパラメータ化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メンバーの相対比率を、プロジェクト共通のパラメータ(名前 + 段階)と、メンバーごとの段階の選択で調整できるようにする。`相対比率 = 基本比率 + 選んだ段階の判定値の合計`(10〜300% に丸める)。

**Architecture:** `Member.ratio` は「基本比率」の意味で残し(ファイルの形式は変わらない)、`Member.levels`(パラメータ名 → 段階名)と `Project.parameters`(定義)を足す。実効比率は純粋関数(`ratios.py`)で求め、換算(`timeline.assignees_rate`・編集ダイアログ)だけがこれを使う。定義の編集(改名・削除)は `ParameterEdit`(旧名 → 新名の対応)で全メンバーの選択に伝える。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -q -n auto`)、`uvx ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-09-ratio-parameters-design.md`

## Global Constraints

- 言語は日本語。コメント・テスト名・コミットメッセージも日本語(識別子は英語)。コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- Python 3.13 以上、NiceGUI。外部のガントライブラリは使わない。
- 日程・比率の計算は、NiceGUI から切り離した純粋関数に置く(`ratios.py`・`timeline.py`)。
- ファイル形式を変えるときは、キーのない古いファイルを既定値で読み(移行を要らなくする)、不正な値は読込を拒否する。
- 相対比率の範囲は 10〜300%(`MIN_RATIO`〜`MAX_RATIO`)。判定値は -0.9〜+2.9(-90〜+290%)、小数点以下 2 桁の%まで。
- パラメータのないプロジェクトと古いファイルは、これまでと同じ値・同じ見た目になる。
- 割り当て超過とダッシュボードの負荷は割り当て率だけを使うので、変えない。
- 描画の要素数を増やさない(要望 24)。ガントチャートの描画は変えない。
- テストは `uv run pytest -q -n auto`(全体で約 15 秒)。型は `uvx ty check src`。各タスクの最後に、全体のテストが通ることを確かめる。
- 実機確認(ネイティブ: `uv run projectapp`)の前に、PR・マージはしない。`develop` へのプッシュは、許可を得てから行う。

## Review Focus

- 定義の削除と改名の組み合わせ: 削除した「A」と、「B」から改名した新しい「A」が同居するとき、古い「A」の選択が新しい「A」に化けない。入れ替え(A↔B)でも、各メンバーの選択が 1 回だけ更新される。→ Task 3 のテスト。
- 合計が範囲外(下限・上限・ちょうど境界)のときの丸めと、丸めた旨の表示。判定値の境界(-90%・+290%・小数点以下 3 桁)。→ Task 2・4・5 のテスト。
- 手で編集したファイルの参照切れ(存在しないパラメータ・段階を選んでいるメンバー): 読込は拒否せず、計算では 0%、メンバーのダイアログの適用で捨てる。→ Task 1・2・5 のテスト。
- パラメータのないプロジェクト・古いファイル: 値も見た目(ラベル「相対比率(%)」、実効比率の行なし)も変わらない。→ Task 1・2・5 のテスト。
- 名前の空・重複(パラメータ・段階。ダイアログとファイル)と、メンバーの改名で選択が引き継がれること。→ Task 1・4・5 のテスト。

---

## File Structure

| ファイル | 役割 | 変更 |
|---|---|---|
| `src/projectapp/models.py` | `Level`・`Parameter`、`Project.parameters`、`Member.levels`、判定値の範囲 | Task 1 |
| `src/projectapp/storage.py` | `parameters`・メンバーの `levels` の保存・読込 | Task 1 |
| `src/projectapp/ratios.py`(新規) | 実効比率、`ParameterEdit`、検証、適用、削除の影響 | Task 2・3 |
| `src/projectapp/timeline.py` | `assignees_rate` が実効比率を使う | Task 2 |
| `src/projectapp/task_dialog.py` | 編集ダイアログの換算が実効比率を使う | Task 2 |
| `src/projectapp/forms.py` | パラメータのダイアログ、メンバーのダイアログの拡張 | Task 4・5 |
| `src/projectapp/views.py` | メニュー、`apply_parameters`、引数の受け渡し | Task 2・4・5 |
| `CLAUDE.md`・`docs/development.md`・`.claude/MEMORY.md` | 文書 | Task 6 |

---

### Task 1: データの形と保存・読込

**Files:**
- Modify: `src/projectapp/models.py`(`Level`・`Parameter` を足し、`Member`・`Project` に欄を足す)
- Modify: `src/projectapp/storage.py`(`_parameters`・`_member_levels`、`_members`、`load_project`)
- Test: `test/test_storage.py`

**Interfaces:**
- Produces:
  - `Level(name: str, value: float)`(`value` は割合。+0.2 が +20%)
  - `Parameter(name: str, levels: list[Level] = [])`
  - `Member.levels: dict[str, str]`(既定は空。パラメータ名 → 段階名)
  - `Project.parameters: list[Parameter]`(既定は空)
  - 定数 `MIN_LEVEL_VALUE = -0.9`・`MAX_LEVEL_VALUE = 2.9`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の `from projectapp.models import (...)` に `Level`・`Parameter` を足し、末尾に足す:

```python
def test_parameters_and_levels_roundtrip(tmp_path: Path) -> None:
    project = Project(
        "p",
        members=[Member("田中", 1.0, {"経験": "上級", "専門": "高"}), Member("鈴木")],
        parameters=[
            Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)]),
            Parameter("専門", [Level("高", 0.1)]),
            Parameter("空", []),
        ],
    )
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.parameters == project.parameters
    assert loaded.members[0].levels == {"経験": "上級", "専門": "高"}
    assert loaded.members[1].levels == {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["parameters"][0] == {"name": "経験", "levels": [{"name": "初級", "value": -0.2}, {"name": "上級", "value": 0.2}]}
    assert raw["members"][0]["levels"] == {"経験": "上級", "専門": "高"}


def test_a_file_without_parameters_or_levels_loads_as_empty(tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中", 1.2)]), tmp_path)

    def legacy(data: dict) -> None:
        data.pop("parameters")
        data["members"][0].pop("levels")

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert loaded.parameters == []
    assert loaded.members == [Member("田中", 1.2)]
    _rewrite(path, lambda d: d.update(parameters=None))
    assert load_project(path).parameters == []


@pytest.mark.parametrize(
    "bad",
    [
        "経験",  # リストでない
        ["経験"],  # 辞書でない
        [{"name": "", "levels": []}],
        [{"name": "  ", "levels": []}],
        [{"name": 3, "levels": []}],
        [{"name": "経験", "levels": []}, {"name": " 経験 ", "levels": []}],  # 重複
        [{"name": "経験", "levels": "上級"}],  # levels がリストでない
        [{"name": "経験", "levels": ["上級"]}],  # 段階が辞書でない
        [{"name": "経験", "levels": [{"name": "", "value": 0.1}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": 0.1}, {"name": "上級", "value": 0.2}]}],  # 段階名の重複
        [{"name": "経験", "levels": [{"name": "上級"}]}],  # 値がない
        [{"name": "経験", "levels": [{"name": "上級", "value": "x"}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": True}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": -0.91}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": 2.91}]}],
        [{"name": "経験", "levels": [{"name": "上級", "value": float("nan")}]}],
    ],
)
def test_bad_parameters_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")]), tmp_path)
    _rewrite(path, lambda d: d.update(parameters=bad))
    with pytest.raises(ValueError):
        load_project(path)


@pytest.mark.parametrize("value", [-0.9, 2.9, 0.0])
def test_the_level_value_boundaries_are_accepted(value: float, tmp_path: Path) -> None:
    project = Project("p", parameters=[Parameter("経験", [Level("a", value)])])
    assert load_project(save_project(project, tmp_path)).parameters[0].levels[0].value == pytest.approx(value)


@pytest.mark.parametrize("bad", ["上級", ["経験"], {"経験": 3}, {3: "上級"}])
def test_bad_member_levels_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", members=[Member("田中")]), tmp_path)
    _rewrite(path, lambda d: d["members"][0].update(levels=bad))
    with pytest.raises(ValueError):
        load_project(path)


def test_a_member_selection_that_points_nowhere_is_kept(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中", 1.0, {"消えた": "上級"})], parameters=[Parameter("経験", [Level("初級", -0.2)])])
    loaded = load_project(save_project(project, tmp_path))
    assert loaded.members[0].levels == {"消えた": "上級"}  # 読込は拒否しない。計算では 0% として扱う(Task 2)
```
(`json`・`pytest`・`_rewrite` は、このファイルにある。JSON の `NaN` は Python の `json` が読み書きできる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_storage.py -q -k "parameters or levels or boundaries" 2>&1 | tail -6`
Expected: `ImportError: cannot import name 'Level'`。

- [ ] **Step 3: `models.py` を直す**

`MIN_RATIO, MAX_RATIO = 0.1, 3.0  # 相対比率(10%〜300%)` の下に足す:

```python
MIN_LEVEL_VALUE, MAX_LEVEL_VALUE = -0.9, 2.9  # パラメータの段階の判定値(-90%〜+290%)
```

`Member` を次にし、その下に `Level`・`Parameter` を足す(`Member` の前後の他のクラスは変えない):

```python
@dataclass
class Member:
    name: str
    ratio: float = 1.0  # 基本比率(1.0 = 100%)。相対比率 = 基本比率 + 選んだ段階の判定値の合計
    levels: dict[str, str] = field(default_factory=dict)  # パラメータ名 → 選んだ段階名


@dataclass
class Level:
    name: str
    value: float  # 判定値。割合(+0.2 = +20%)


@dataclass
class Parameter:
    name: str
    levels: list[Level] = field(default_factory=list)
```
`Project` の `url_templates` の下に足す:

```python
    parameters: list[Parameter] = field(default_factory=list)  # 相対比率のパラメータ(プロジェクト共通)
```

- [ ] **Step 4: `storage.py` を直す**

`from projectapp.models import (...)` に `MAX_LEVEL_VALUE`・`MIN_LEVEL_VALUE`・`Level`・`Parameter` を足す。`_members` の上に足す:

```python
def _label_name(value: Any, label: str) -> str:
    """パラメータ・段階の名前。前後の空白を除く。空・文字列以外は ValueError。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}の名前が正しくありません")
    return value.strip()


def _parameters(value: Any) -> list[Parameter]:
    """パラメータの定義。キーがない・null は空。名前の空・重複、判定値の範囲外・非有限は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("パラメータがリストではありません")
    parameters: list[Parameter] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("パラメータの形式が正しくありません")
        name = _label_name(raw.get("name"), "パラメータ")
        if name in seen:
            raise ValueError(f"パラメータ名が重複しています: {name}")
        seen.add(name)
        raw_levels = raw.get("levels")
        if raw_levels is None:
            raw_levels = []
        if not isinstance(raw_levels, list):
            raise ValueError("段階がリストではありません")
        levels: list[Level] = []
        level_names: set[str] = set()
        for item in raw_levels:
            if not isinstance(item, dict):
                raise ValueError("段階の形式が正しくありません")
            level_name = _label_name(item.get("name"), "段階")
            if level_name in level_names:
                raise ValueError(f"段階名が重複しています: {name} の {level_name}")
            level_names.add(level_name)
            levels.append(Level(level_name, _number_in_range(item.get("value"), MIN_LEVEL_VALUE, MAX_LEVEL_VALUE, "判定値")))
        parameters.append(Parameter(name, levels))
    return parameters


def _member_levels(value: Any) -> dict[str, str]:
    """メンバーが選んだ段階(パラメータ名 → 段階名)。キーがない・null は空。存在しない参照は拒否しない。"""
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError("メンバーの段階の選択が正しくありません")
    return dict(value)
```

`_members` の本体を直す(`ratio = ...` の下で `levels` を読み、`Member(name, ratio, levels)` を作る):

```python
        ratio = _number_in_range(raw.get("ratio", 1.0), MIN_RATIO, MAX_RATIO, "相対比率")
        levels = _member_levels(raw.get("levels"))
        if not name or name in seen:
            continue
        seen.add(name)
        members.append(Member(name, ratio, levels))
```
`load_project` の `Project(...)` に `parameters=_parameters(raw.get("parameters")),` を足す(`url_templates=` の下)。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: 相対比率のパラメータの定義とメンバーの段階の選択を、保存・読込できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 実効比率の計算と、換算への反映(`ratios.py`・`timeline.py`・`task_dialog.py`)

**Files:**
- Create: `src/projectapp/ratios.py`
- Modify: `src/projectapp/timeline.py`(`assignees_rate`・`conversion_rate`)
- Modify: `src/projectapp/task_dialog.py`(`open_task_dialog` の `parameters`)
- Modify: `src/projectapp/views.py`(`link_args`)
- Test: `test/test_ratios.py`(新規)、`test/test_timeline.py`、`test/test_task_dialog.py`、`test/test_handoff.py`

**Interfaces:**
- Consumes: `Level`・`Parameter`・`Member.levels`(Task 1)。
- Produces:
  - `RatioDetail(base: float, adjustments: list[tuple[str, str, float]], raw: float, ratio: float, clamped: bool)`(`adjustments` は(パラメータ名, 段階名, 判定値)で、パラメータの定義の順)
  - `ratio_detail(member: Member, parameters: list[Parameter]) -> RatioDetail`
  - `effective_ratio(member: Member, parameters: list[Parameter]) -> float`
  - `timeline.assignees_rate(assignees, members, parameters: list[Parameter] | None = None) -> float`
  - `open_task_dialog(..., parameters: list[Parameter] | None = None)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_ratios.py`(新規):

```python
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
```

`test/test_timeline.py` の `test_assignees_rate_works_on_a_member_list` の下に足す(`Level`・`Parameter` を import する):

```python
def test_assignees_rate_uses_the_effective_ratio() -> None:
    parameters = [Parameter("経験", [Level("上級", 0.2)])]
    members = [Member("A", 1.0, {"経験": "上級"}), Member("B", 1.0)]
    assignees = [Assignee("A", 1.0), Assignee("B", 0.5)]
    assert assignees_rate(assignees, members, parameters) == pytest.approx(1.2 + 0.5)
    assert assignees_rate(assignees, members) == pytest.approx(1.0 + 0.5)  # パラメータなしは基本比率


def test_the_computed_end_follows_the_parameters() -> None:
    project = member_project(Member("田中", 1.0, {"経験": "上級"}))
    project.parameters = [Parameter("経験", [Level("上級", 0.5)])]
    task = Task("t", planned_start=FRI_START, effort_hours=15.0, assignees=[Assignee("田中")])
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert effective_end(task, project, {}) == datetime(2026, 10, 12, 12, 30)
    assert conversion_rate(task, project) == pytest.approx(1.5)
```

`test/test_handoff.py` に足す(`Level`・`Parameter` を import):

```python
def test_the_estimate_follows_the_parameters() -> None:
    solo = task("単独", effort_hours=15.0, assignees=[Assignee("田中", 1.0)])
    project = make_project(solo, members=[Member("田中", 1.0, {"経験": "上級"})])
    project.parameters = [Parameter("経験", [Level("上級", 0.5)])]
    assert build(project, "田中").data["items"][0]["estimate_hours"] == pytest.approx(10.0)  # 15 / 1.5
```

`test/test_task_dialog.py`: `mount_dialog` の引数に `parameters: list[Parameter] | None = None` を足し、`open_task_dialog(...)` の呼び出しに `parameters=parameters,` を渡す(`Parameter`・`Level` を import)。末尾に足す:

```python
async def test_the_conversion_uses_the_effective_ratio(user: User) -> None:
    members = [Member("田中", 1.0, {"経験": "上級"})]
    mount_dialog(None, [], members=members, parameters=[Parameter("経験", [Level("上級", 0.2)])])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    # 実効比率 120%。15h / 1.2 / 6.5h = 1.92日
    assert conversion.text == "換算率 120%(田中 120%×100%)→ 15h は約 1.9日分"


async def test_the_computed_end_follows_the_parameters_in_the_dialog(user: User) -> None:
    members = [Member("田中", 1.0, {"経験": "上級"})]
    mount_dialog(None, [], members=members, parameters=[Parameter("経験", [Level("上級", 0.5)])])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-effort").clear().type("15")
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-12 12:30"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_ratios.py test/test_timeline.py test/test_handoff.py test/test_task_dialog.py -q 2>&1 | tail -8`
Expected: `ModuleNotFoundError: No module named 'projectapp.ratios'` と、`assignees_rate() takes 2 positional arguments`、`mount_dialog() got an unexpected keyword argument` などで失敗する。

- [ ] **Step 3: `ratios.py` を作る**

```python
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
    raw = member.ratio + sum(value for _, _, value in adjustments)
    ratio = min(max(raw, MIN_RATIO), MAX_RATIO) if isfinite(raw) else member.ratio
    return RatioDetail(member.ratio, adjustments, raw, ratio, ratio != raw)


def effective_ratio(member: Member, parameters: list[Parameter]) -> float:
    """計算に使う相対比率。"""
    return ratio_detail(member, parameters).ratio
```

- [ ] **Step 4: `timeline.py`・`task_dialog.py`・`views.py` を直す**

`src/projectapp/timeline.py`: `from projectapp.models import (...)` に `Parameter` を足し、`from projectapp.ratios import effective_ratio` を足す。`assignees_rate` と `conversion_rate` を置き換える:

```python
def assignees_rate(
    assignees: list[Assignee], members: list[Member], parameters: list[Parameter] | None = None
) -> float:
    """担当者全員の換算率(相対比率 × 割り当て率)の合計。相対比率は、パラメータを反映した実効比率。
    メンバーにいない担当者は数えない。誰も数えられなければ 1.0(換算しない)。"""
    by_name = {m.name: m for m in members}
    chosen = parameters or []
    rates = [
        combine_rate(effective_ratio(by_name[a.name], chosen), a.allocation)
        for a in assignees
        if a.name in by_name
    ]
    return sum(rates) if rates else 1.0


def conversion_rate(task: Task, project: Project) -> float:
    return assignees_rate(task.assignees, project.members, project.parameters)
```

`src/projectapp/task_dialog.py`: `from projectapp.models import (...)` に `Parameter` を足し、`from projectapp.ratios import effective_ratio` を足す。`open_task_dialog` の引数の最後(`open_url` の下)に `parameters: list[Parameter] | None = None,` を足し、`member_list = list(members or [])` を置き換える:

```python
    # 換算には、パラメータを反映した実効比率を使う(以降は、このコピーだけを見る)
    member_list = [Member(m.name, effective_ratio(m, parameters or [])) for m in members or []]
```

`src/projectapp/views.py` の `link_args` が返す辞書に `"parameters": self.project.parameters,` を足す(`"url_templates": …` の下)。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: 相対比率にパラメータの判定値を足した実効比率で、換算する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 定義の編集の純粋ロジック(`ratios.py`)

**Files:**
- Modify: `src/projectapp/ratios.py`
- Test: `test/test_ratios.py`

**Interfaces:**
- Consumes: `Level`・`Parameter`・`Project`(Task 1)。
- Produces:
  - `ParameterEdit(parameters: list[Parameter], parameter_map: dict[str, str | None], level_map: dict[str, dict[str, str | None]])`。`parameter_map` は、旧パラメータ名 → 新しい名前(削除は None)。`level_map` は、旧パラメータ名 → {旧段階名: 新しい段階名(削除は None)}(削除されたパラメータの項目はない)。メソッド `changes(current: list[Parameter]) -> bool`(定義または対応が変わるか)。
  - `validate_parameters(parameters: list[Parameter]) -> None`(不正なら `ValueError`)
  - `apply_parameter_edit(project: Project, edit: ParameterEdit) -> None`
  - `deletion_impacts(project: Project, edit: ParameterEdit) -> list[tuple[str, int]]`(選択が外れる影響。(ラベル, メンバー数))

- [ ] **Step 1: 失敗するテストを書く**

`test/test_ratios.py` の末尾に足す(`Project`・`ParameterEdit`・`apply_parameter_edit`・`deletion_impacts`・`validate_parameters` を import する):

```python
def edit_of(parameters: list[Parameter], parameter_map: dict, level_map: dict | None = None) -> ParameterEdit:
    return ParameterEdit(parameters, parameter_map, level_map or {})


def project_with(*members: Member, parameters: list[Parameter]) -> Project:
    return Project("p", members=list(members), parameters=parameters)


def test_an_unchanged_edit_changes_nothing() -> None:
    edit = edit_of(PARAMETERS, {"経験": "経験", "専門": "専門"}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}, "専門": {"低": "低", "高": "高"}})
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
    apply_parameter_edit(project, edit_of([EXPERIENCE], {"経験": "経験"}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}}))
    assert project.members[0].levels == {"経験": "上級"}


def test_changing_a_level_value_changes_the_effective_ratio_at_once() -> None:
    project = project_with(Member("a", 1.0, {"経験": "上級"}), parameters=[EXPERIENCE])
    new = [Parameter("経験", [Level("初級", -0.2), Level("中級", 0.0), Level("上級", 0.5)])]
    apply_parameter_edit(project, edit_of(new, {"経験": "経験"}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}}))
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
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_ratios.py -q 2>&1 | tail -4`
Expected: `ImportError: cannot import name 'ParameterEdit'`。

- [ ] **Step 3: 実装する**

`src/projectapp/ratios.py` の import を `from projectapp.models import MAX_LEVEL_VALUE, MAX_RATIO, MIN_LEVEL_VALUE, MIN_RATIO, Member, Parameter, Project` にし、末尾に足す:

```python
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


def apply_parameter_edit(project: Project, edit: ParameterEdit) -> None:
    """定義を置き換え、全メンバーの選択を更新する。削除された参照と、存在しない参照は外す。
    対応は旧い名前で引くので、入れ替えや、削除と改名の組み合わせでも、選択が取り違えられない。"""
    for member in project.members:
        updated: dict[str, str] = {}
        for old_parameter, old_level in member.levels.items():
            new_parameter = edit.parameter_map.get(old_parameter)
            if new_parameter is None:
                continue
            new_level = edit.level_map.get(old_parameter, {}).get(old_level)
            if new_level is None:
                continue
            updated[new_parameter] = new_level
        member.levels = updated
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
```

(注: `deletion_impacts` の並びは、`parameter_map` の挿入順に従う。テストの期待 `[("「経験」の「上級」", 2), ("「専門」", 1)]` は、`parameter_map = {"経験": …, "専門": None}` の順で出る。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: パラメータの定義の編集(改名・削除)をメンバーの選択に伝える

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: パラメータのダイアログとメニュー(`forms.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`LevelRow`・`ParameterRow`・`build_parameter_edit`・`open_parameters_dialog`)
- Modify: `src/projectapp/views.py`(メニュー、`open_parameters`、`apply_parameters`)
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `ParameterEdit`・`validate_parameters`・`apply_parameter_edit`・`deletion_impacts`(Task 3)。
- Produces:
  - `LevelRow(original: str | None, name: str, value_percent: float | None)`、`ParameterRow(original: str | None, name: str, levels: list[LevelRow])`
  - `build_parameter_edit(rows: list[ParameterRow], before: list[Parameter]) -> ParameterEdit`(不正なら `ValueError`)
  - `open_parameters_dialog(parameters: list[Parameter], impacts: Callable[[ParameterEdit], list[tuple[str, int]]], on_apply: Callable[[ParameterEdit], object]) -> None`
  - マーカー: メニュー `open-parameters`。ダイアログ `parameter-name-<p>`・`parameter-delete-<p>`・`parameter-add`・`level-name-<p>-<l>`・`level-value-<p>-<l>`・`level-delete-<p>-<l>`・`level-add-<p>`・`parameter-apply`・`parameter-error`・確認の `parameter-delete-confirm`・`parameter-delete-cancel`

- [ ] **Step 1: `build_parameter_edit` の失敗するテストを書く**

`test/test_forms.py` に足す(`Level`・`Parameter`・`LevelRow`・`ParameterRow`・`build_parameter_edit` を import する):

```python
def prow(original: str | None, name: str, *levels: tuple[str | None, str, float | None]) -> ParameterRow:
    return ParameterRow(original, name, [LevelRow(o, n, v) for o, n, v in levels])


BEFORE = [Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)]), Parameter("専門", [Level("高", 0.1)])]


def test_build_parameter_edit_converts_percent_to_a_fraction_and_trims_names() -> None:
    edit = build_parameter_edit([prow(None, " 経験 ", (None, " 上級 ", 20.0), (None, "初級", -20.0))], [])
    assert edit.parameters == [Parameter("経験", [Level("上級", 0.2), Level("初級", -0.2)])]
    assert edit.parameter_map == {} and edit.level_map == {}


def test_build_parameter_edit_maps_renames_and_deletions_by_the_old_names() -> None:
    rows = [
        prow("経験", "スキル", ("初級", "初級", -20.0), (None, "中級", 0.0)),  # 上級を削除、中級を追加
    ]
    edit = build_parameter_edit(rows, BEFORE)
    assert edit.parameter_map == {"経験": "スキル", "専門": None}
    assert edit.level_map == {"経験": {"初級": "初級", "上級": None}}


def test_build_parameter_edit_keeps_swapped_names_apart() -> None:
    before = [Parameter("A", [Level("x", 0.1)]), Parameter("B", [Level("y", 0.2)])]
    rows = [prow("B", "A", ("y", "y", 20.0)), prow("A", "B", ("x", "x", 10.0))]
    edit = build_parameter_edit(rows, before)
    assert edit.parameter_map == {"A": "B", "B": "A"}
    assert edit.level_map == {"A": {"x": "x"}, "B": {"y": "y"}}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([prow(None, "")], "名前"),
        ([prow(None, "A"), prow(None, "A")], "重複"),
        ([prow(None, "A", (None, "", 10.0))], "名前"),
        ([prow(None, "A", (None, "x", 10.0), (None, "x", 20.0))], "重複"),
        ([prow(None, "A", (None, "x", None))], "判定値"),
        ([prow(None, "A", (None, "x", float("nan")))], "判定値"),
        ([prow(None, "A", (None, "x", -90.01))], "判定値"),
        ([prow(None, "A", (None, "x", 290.01))], "判定値"),
        ([prow(None, "A", (None, "x", 10.005))], "小数点"),
    ],
)
def test_build_parameter_edit_rejects_bad_rows(rows: list[ParameterRow], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_parameter_edit(rows, [])


def test_build_parameter_edit_accepts_the_boundaries() -> None:
    edit = build_parameter_edit([prow(None, "A", (None, "lo", -90.0), (None, "hi", 290.0), (None, "z", 12.5))], [])
    assert [lv.value for lv in edit.parameters[0].levels] == [-0.9, 2.9, 0.125]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py -q -k "parameter_edit" 2>&1 | tail -4`
Expected: `ImportError: cannot import name 'ParameterRow'`。

- [ ] **Step 3: `forms.py` に行と `build_parameter_edit` を足す**

import に `Level`・`Parameter` と、`from projectapp.ratios import ParameterEdit, validate_parameters` を足す。`MemberRow` の上に足す:

```python
@dataclass
class LevelRow:
    """パラメータのダイアログの段階の 1 行。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    value_percent: float | None


@dataclass
class ParameterRow:
    """パラメータのダイアログの 1 行(下に段階の行を持つ)。originalは、開いた時点の名前(新しい行はNone)。"""

    original: str | None
    name: str
    levels: list[LevelRow]


def build_parameter_edit(rows: list[ParameterRow], before: list[Parameter]) -> ParameterEdit:
    """ダイアログの行を検証して、新しい定義と、旧い名前からの対応を返す。不正なら ValueError。"""
    parameters: list[Parameter] = []
    for row in rows:
        levels: list[Level] = []
        for level_row in row.levels:
            value = level_row.value_percent
            if value is None or not isfinite(value):
                raise ValueError("判定値を入力してください")
            if exceeds_decimals(value):
                raise ValueError(f"判定値は小数点以下{HOURS_DECIMALS}桁までで入力してください")
            levels.append(Level(level_row.name.strip(), round(value / 100, 4)))
        parameters.append(Parameter(row.name.strip(), levels))
    validate_parameters(parameters)
    by_name = {p.name: p for p in before}
    parameter_map: dict[str, str | None] = {p.name: None for p in before}
    level_map: dict[str, dict[str, str | None]] = {}
    for row, built in zip(rows, parameters):
        if row.original is None or row.original not in by_name:
            continue
        parameter_map[row.original] = built.name
        mapping: dict[str, str | None] = {lv.name: None for lv in by_name[row.original].levels}
        for level_row, level in zip(row.levels, built.levels):
            if level_row.original is not None and level_row.original in mapping:
                mapping[level_row.original] = level.name
        level_map[row.original] = mapping
    return ParameterEdit(parameters, parameter_map, level_map)
```
(`isfinite`・`exceeds_decimals`・`HOURS_DECIMALS` は、`forms.py` に既にある。新しい行のとき `parameter_map` には何も足さない。)

- [ ] **Step 4: `build_parameter_edit` のテストが通ることを確かめる**

Run: `uv run pytest test/test_forms.py -q -k "parameter_edit" 2>&1 | tail -3`
Expected: PASS。

- [ ] **Step 5: ダイアログとメニューの失敗するテストを書く**

`test/test_views.py` の末尾に足す(`Level`・`Parameter` を import する。補助は、このファイルの `open_members_view`・`wait_until`・`menu_items` を使う):

```python
async def test_the_project_menu_has_the_parameters_item(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    assert ("パラメータ", "open-parameters") in menu_items(user, "menu-project-items")


async def test_the_parameters_dialog_adds_a_parameter_with_levels(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    user.find(marker="open-parameters").click()
    user.find(marker="parameter-add").click()
    await user.should_see(marker="parameter-name-0")
    user.find(marker="parameter-name-0").type("経験")
    user.find(marker="level-add-0").click()
    await user.should_see(marker="level-name-0-0")
    user.find(marker="level-name-0-0").type("上級")
    user.find(marker="level-value-0-0").clear().type("20")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters == [Parameter("経験", [Level("上級", 0.2)])])
    assert view.is_dirty()


async def test_the_parameters_dialog_shows_the_error_and_does_not_apply(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    user.find(marker="open-parameters").click()
    user.find(marker="parameter-add").click()
    await user.should_see(marker="parameter-name-0")
    user.find(marker="parameter-apply").click()  # 名前が空
    await user.should_see("名前")
    assert view.project.parameters == []


async def test_applying_the_same_parameters_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.mark_clean()
    user.find(marker="open-parameters").click()
    user.find(marker="parameter-apply").click()
    await wait_until(lambda: True)
    assert not view.is_dirty()


async def test_renaming_a_parameter_renames_the_selection_of_members(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"})]
    view.mark_clean()
    user.find(marker="open-parameters").click()
    user.find(marker="parameter-name-0").clear().type("スキル")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.members[0].levels == {"スキル": "上級"})
    assert view.project.parameters[0].name == "スキル"


async def test_deleting_a_used_level_asks_first_and_clears_the_selection(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"}), Member("鈴木", 1.0, {"経験": "上級"})]
    view.mark_clean()
    user.find(marker="open-parameters").click()
    user.find(marker="level-delete-0-1").click()
    user.find(marker="parameter-apply").click()
    await user.should_see("「経験」の「上級」を選んでいるメンバーが2人います")
    assert view.project.members[0].levels == {"経験": "上級"}  # まだ変わらない
    user.find(marker="parameter-delete-confirm").click()
    assert await wait_until(lambda: view.project.members[0].levels == {})
    assert [lv.name for lv in view.project.parameters[0].levels] == ["初級"]


async def test_cancelling_the_delete_confirmation_keeps_everything(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"})]
    user.find(marker="open-parameters").click()
    user.find(marker="parameter-delete-0").click()
    user.find(marker="parameter-apply").click()
    await user.should_see("「経験」を選んでいるメンバーが1人います")
    user.find(marker="parameter-delete-cancel").click()
    assert view.project.parameters != []
    assert view.project.members[0].levels == {"経験": "上級"}


async def test_deleting_an_unused_parameter_needs_no_confirmation(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    user.find(marker="open-parameters").click()
    user.find(marker="parameter-delete-0").click()
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters == [])


async def test_a_parameter_edit_changes_the_computed_end(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"})]
    task = Task("t", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0, assignees=[Assignee("田中")])
    view.project.tasks = [task]
    view.gantt.set_project(view.project)
    # 15h / 1.2 = 12.5h → 金6.5h + 月6.0h
    assert effective_end(task, view.project, {}) == datetime(2026, 10, 12, 15, 0)
    user.find(marker="open-parameters").click()
    user.find(marker="level-value-0-0").clear().type("50")
    user.find(marker="parameter-apply").click()
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert await wait_until(lambda: effective_end(task, view.project, {}) == datetime(2026, 10, 12, 12, 30))
```
(`open_header_view`・`menu_items` は、既存のヘッダーのテストが使っているもの。`effective_end` は `projectapp.timeline` から import する。)

- [ ] **Step 6: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "parameters or parameter_edit or unused_parameter or delete_confirmation or used_level" 2>&1 | tail -6`
Expected: `open-parameters` のマーカーが見つからないなどで失敗する。

- [ ] **Step 7: ダイアログを実装する**

`src/projectapp/forms.py` の `open_members_dialog` の上に足す:

```python
def open_parameters_dialog(
    parameters: list[Parameter],
    impacts: Callable[[ParameterEdit], list[tuple[str, int]]],
    on_apply: Callable[[ParameterEdit], object],
) -> None:
    """パラメータの定義の編集。削除でメンバーの選択が外れるときは、適用の前に確認する。"""
    rows = [
        ParameterRow(p.name, p.name, [LevelRow(lv.name, lv.name, round(lv.value * 100, 2)) for lv in p.levels])
        for p in parameters
    ]
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[36rem] max-w-full"):
        ui.label("パラメータ").classes("text-h6")
        ui.label("相対比率 = 基本比率 + 選んだ段階の判定値の合計(10〜300% に丸めます)").classes("text-caption text-grey")

        @ui.refreshable
        def table() -> None:
            with ui.column().classes("w-full gap-2"):
                if not rows:
                    ui.label("パラメータがありません").classes("text-grey")
                for p, row in enumerate(rows):
                    with ui.column().classes("w-full gap-1 q-pa-sm").style("border: 1px solid rgba(128,128,128,0.4)"):
                        with ui.row().classes("w-full items-center no-wrap gap-2"):
                            ui.input(
                                "パラメータ名",
                                value=row.name,
                                on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                            ).classes("flex-1").mark(f"parameter-name-{p}")
                            ui.button(icon="delete", on_click=lambda _e, r=row: remove_parameter(r)).props(
                                "flat dense round color=negative"
                            ).mark(f"parameter-delete-{p}")
                        for n, level in enumerate(row.levels):
                            with ui.row().classes("w-full items-center no-wrap gap-2 q-pl-md"):
                                ui.input(
                                    "段階",
                                    value=level.name,
                                    on_change=lambda e, lv=level: setattr(lv, "name", e.value or ""),
                                ).classes("flex-1").mark(f"level-name-{p}-{n}")
                                ui.number(
                                    "判定値(%)",
                                    value=level.value_percent,
                                    min=MIN_LEVEL_VALUE * 100,
                                    max=MAX_LEVEL_VALUE * 100,
                                    step=5,
                                    on_change=lambda e, lv=level: setattr(lv, "value_percent", e.value),
                                ).classes("w-32").mark(f"level-value-{p}-{n}")
                                ui.button(
                                    icon="delete", on_click=lambda _e, r=row, lv=level: remove_level(r, lv)
                                ).props("flat dense round").mark(f"level-delete-{p}-{n}")
                        ui.button("段階を追加", icon="add", on_click=lambda _e, r=row: add_level(r)).props(
                            "flat dense"
                        ).classes("q-ml-md").mark(f"level-add-{p}")

        def add_parameter() -> None:
            rows.append(ParameterRow(None, "", []))
            table.refresh()

        def remove_parameter(row: ParameterRow) -> None:
            rows.remove(row)
            table.refresh()

        def add_level(row: ParameterRow) -> None:
            row.levels.append(LevelRow(None, "", 0.0))
            table.refresh()

        def remove_level(row: ParameterRow, level: LevelRow) -> None:
            row.levels.remove(level)
            table.refresh()

        table()
        ui.button("パラメータを追加", icon="add", on_click=add_parameter).props("flat").mark("parameter-add")
        error = ui.label("").classes("text-negative").mark("parameter-error")
        pending: dict[str, ParameterEdit] = {}
        with ui.dialog() as confirm, ui.card():
            confirm_text = ui.label("").style("white-space: pre-line")
            with ui.row():
                ui.button("キャンセル", on_click=confirm.close).props("flat").mark("parameter-delete-cancel")
                ui.button("削除する", on_click=lambda: confirm_apply()).props("color=negative").mark(
                    "parameter-delete-confirm"
                )

        def commit(edit: ParameterEdit) -> None:
            on_apply(edit)
            dialog.close()

        def confirm_apply() -> None:
            confirm.close()
            commit(pending["edit"])

        def apply() -> None:
            error.set_text("")
            try:
                edit = build_parameter_edit(rows, parameters)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            affected = impacts(edit)
            if affected:
                pending["edit"] = edit
                confirm_text.set_text(
                    "\n".join(f"{label}を選んでいるメンバーが{count}人います" for label, count in affected)
                    + "\n削除すると、その選択は外れて判定値 0% になります"
                )
                confirm.open()
                return
            commit(edit)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("parameter-apply")
    dialog.open()
```
(import に `MAX_LEVEL_VALUE`・`MIN_LEVEL_VALUE` を `projectapp.models` から足す。確認の文面は、複数行を `\n` でつなぐ。)

`src/projectapp/views.py`:
- import: `from projectapp.forms import (...)` に `open_parameters_dialog` を足し、`from projectapp.ratios import ParameterEdit, apply_parameter_edit, deletion_impacts` を足す。
- `プロジェクト`メニューの項目を `("メンバー", …)` の下に `("パラメータ", self.open_parameters, "open-parameters"),` で足す。
- `apply_members` の下に足す:

```python
    def open_parameters(self) -> None:
        open_parameters_dialog(
            self.project.parameters,
            lambda edit: deletion_impacts(self.project, edit),
            self.apply_parameters,
        )

    def apply_parameters(self, edit: ParameterEdit) -> None:
        """パラメータの定義を更新し、メンバーの選択に改名・削除を伝える。保存はしない(編集中の判定に入る)。"""
        if not edit.changes(self.project.parameters):
            return
        apply_parameter_edit(self.project, edit)
        self.gantt.set_project(self.project)
```

既存のテスト `test_the_header_has_the_four_menus…`(`menu-project-items` の項目の一覧を検証している箇所、`test/test_views.py` の 1933 行目付近)の期待値に `("パラメータ", "open-parameters"),` を足す(`("メンバー", "open-members"),` の下)。

- [ ] **Step 8: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -5 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 9: コミット**

```bash
git add -A
git commit -m "feat: パラメータの定義をダイアログで編集できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: メンバーのダイアログの拡張(`forms.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`MemberRow`・`build_members`・`open_members_dialog`)
- Modify: `src/projectapp/views.py`(`open_members`)
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `ratio_detail`(Task 2)、`Parameter`(Task 1)。
- Produces:
  - `MemberRow.levels: dict[str, str]`(既定は空)
  - `build_members(rows, originals, assigned, parameters: list[Parameter] | None = None)`: `levels` は、存在するパラメータ・段階だけに絞る。
  - `open_members_dialog(members, assigned, on_apply, parameters: list[Parameter] | None = None)`
  - `effective_ratio_text(row: MemberRow, parameters: list[Parameter]) -> str`
  - マーカー: 選択 `member-level-<i>-<p>`、実効比率 `member-effective-<i>`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py`(`effective_ratio_text`・`Level`・`Parameter` を import):

```python
EXPERIENCE = Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])


def test_build_members_keeps_the_levels_that_exist() -> None:
    row = MemberRow(None, "田中", 100.0, {"経験": "上級", "消えた": "x", "経験2": "y"})
    members, _ = build_members([row], [], no_tasks, [EXPERIENCE])
    assert members == [Member("田中", 1.0, {"経験": "上級"})]


def test_build_members_drops_a_level_that_no_longer_exists() -> None:
    row = MemberRow(None, "田中", 100.0, {"経験": "存在しない"})
    members, _ = build_members([row], [], no_tasks, [EXPERIENCE])
    assert members[0].levels == {}


def test_build_members_without_parameters_has_no_levels() -> None:
    members, _ = build_members([MemberRow(None, "田中", 100.0, {"経験": "上級"})], [], no_tasks)
    assert members[0].levels == {}


def test_a_renamed_member_keeps_the_levels() -> None:
    row = MemberRow("田中", "田中太郎", 100.0, {"経験": "上級"})
    members, renames = build_members([row], ["田中"], no_tasks, [EXPERIENCE])
    assert members == [Member("田中太郎", 1.0, {"経験": "上級"})]
    assert renames == {"田中": "田中太郎"}


@pytest.mark.parametrize(
    ("percent", "levels", "text"),
    [
        (100.0, {}, "相対比率 100%"),
        (100.0, {"経験": "上級"}, "相対比率 120%"),
        (100.0, {"経験": "初級"}, "相対比率 80%"),
        (290.0, {"経験": "上級"}, "相対比率 300%(範囲に丸めました)"),
        (10.0, {"経験": "初級"}, "相対比率 10%(範囲に丸めました)"),
        (None, {}, ""),
        (float("nan"), {}, ""),
    ],
)
def test_effective_ratio_text(percent: float | None, levels: dict[str, str], text: str) -> None:
    assert effective_ratio_text(MemberRow(None, "a", percent, levels), [EXPERIENCE]) == text
```

`test/test_views.py` に足す:

```python
def params_view_setup(view: MainView) -> None:
    view.project.parameters = [Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])]
    view.project.members = [Member("田中", 1.0)]
    view.mark_clean()


async def test_the_members_dialog_without_parameters_looks_as_before(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("田中", 1.0)]
    user.find(marker="open-members").click()
    await user.should_see(marker="member-ratio-0")
    ratio = user.find(marker="member-ratio-0").elements.pop()
    assert ratio.props["label"] == "相対比率(%)"
    await user.should_not_see(marker="member-effective-0")
    await user.should_not_see(marker="member-level-0-0")


async def test_the_members_dialog_with_parameters_shows_selects_and_the_effective_ratio(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    user.find(marker="open-members").click()
    await user.should_see(marker="member-level-0-0")
    assert user.find(marker="member-ratio-0").elements.pop().props["label"] == "基本比率(%)"
    select = user.find(marker="member-level-0-0").elements.pop()
    assert select.options == {"": "(なし)", "初級": "初級 -20%", "上級": "上級 +20%"}
    assert user.find(marker="member-effective-0").elements.pop().text == "相対比率 100%"
    with user.client:
        select.set_value("上級")
    assert user.find(marker="member-effective-0").elements.pop().text == "相対比率 120%"
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members == [Member("田中", 1.0, {"経験": "上級"})])
    assert view.is_dirty()


async def test_the_effective_ratio_follows_the_base_ratio_and_shows_the_rounding(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    user.find(marker="open-members").click()
    await user.should_see(marker="member-level-0-0")
    with user.client:
        user.find(marker="member-level-0-0").elements.pop().set_value("上級")
    user.find(marker="member-ratio-0").clear().type("290")
    assert user.find(marker="member-effective-0").elements.pop().text == "相対比率 300%(範囲に丸めました)"


async def test_applying_members_drops_selections_that_point_nowhere(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    view.project.members = [Member("田中", 1.0, {"経験": "存在しない", "消えた": "x"})]
    view.mark_clean()
    user.find(marker="open-members").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].levels == {})


async def test_a_new_member_row_has_no_selection_and_is_saved(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    params_view_setup(view)
    user.find(marker="open-members").click()
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-1")
    user.find(marker="member-name-1").type("鈴木")
    with user.client:
        user.find(marker="member-level-1-0").elements.pop().set_value("初級")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: len(view.project.members) == 2)
    assert view.project.members[1] == Member("鈴木", 1.0, {"経験": "初級"})
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -k "levels or effective or members_dialog or new_member_row or drops_selections" 2>&1 | tail -6`
Expected: `ImportError: cannot import name 'effective_ratio_text'` などで失敗する。

- [ ] **Step 3: `forms.py` を実装する**

`from projectapp.ratios import ParameterEdit, ratio_detail, validate_parameters` に直す。`MemberRow` に欄を足す:

```python
    levels: dict[str, str] = field(default_factory=dict)  # パラメータ名 → 選んだ段階名
```
(`field` を `dataclasses` から import する。)`build_members` の引数に `parameters: list[Parameter] | None = None` を足し、`members.append(...)` の直前で `levels` を絞って渡す:

```python
        existing = {p.name: {lv.name for lv in p.levels} for p in parameters or []}
        levels = {p: lv for p, lv in row.levels.items() if lv in existing.get(p, set())}
        members.append(Member(name, round(ratio / 100, 4), levels))
```
(`members.append(Member(name, round(ratio / 100, 4)))` の 1 行を置き換える。)`open_members_dialog` の上に足す:

```python
def effective_ratio_text(row: MemberRow, parameters: list[Parameter]) -> str:
    """メンバーの行の、実効比率の表示。基本比率が空・非有限のときは空。範囲に丸めたときは、その旨を足す。"""
    percent = row.ratio_percent
    if percent is None or not isfinite(percent):
        return ""
    detail = ratio_detail(Member(row.name, percent / 100, row.levels), parameters)
    note = "(範囲に丸めました)" if detail.clamped else ""
    return f"相対比率 {detail.ratio * 100:g}%{note}"


def _signed_percent(value: float) -> str:
    return f"{value * 100:+g}%" if value else "0%"
```

`open_members_dialog` を置き換える(引数の `parameters` を足し、行・見た目を拡張。パラメータがないときは今と同じ):

```python
def open_members_dialog(
    members: list[Member],
    assigned: Callable[[str], int],
    on_apply: Callable[[list[Member], dict[str, str]], object],
    parameters: list[Parameter] | None = None,
) -> None:
    chosen_parameters = parameters or []
    rows = [MemberRow(m.name, m.name, round(m.ratio * 100, 2), dict(m.levels)) for m in members]
    originals = [m.name for m in members]
    width = "w-[28rem]" if not chosen_parameters else "w-[48rem]"
    with disposable(ui.dialog()) as dialog, ui.card().classes(f"{width} max-w-full"):
        ui.label("メンバー").classes("text-h6")

        @ui.refreshable
        def table() -> None:
            with ui.column().classes("w-full gap-1"):
                if not rows:
                    ui.label("メンバーがいません").classes("text-grey")
                for index, row in enumerate(rows):
                    with ui.row().classes("w-full items-center gap-2"):
                        effective = (
                            ui.label(effective_ratio_text(row, chosen_parameters))
                            .classes("text-caption text-grey")
                            .mark(f"member-effective-{index}")
                            if chosen_parameters
                            else None
                        )

                        def on_ratio(e, r=row, label=effective) -> None:  # noqa: ANN001
                            r.ratio_percent = e.value
                            if label is not None:
                                label.set_text(effective_ratio_text(r, chosen_parameters))

                        ui.input(
                            "名前",
                            value=row.name,
                            on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                        ).classes("flex-1").mark(f"member-name-{index}")
                        ui.number(
                            "基本比率(%)" if chosen_parameters else "相対比率(%)",
                            value=row.ratio_percent,
                            min=MIN_RATIO * 100,
                            max=MAX_RATIO * 100,
                            step=5,
                            on_change=on_ratio,
                        ).classes("w-32").mark(f"member-ratio-{index}")
                        for p, parameter in enumerate(chosen_parameters):

                            def on_level(e, r=row, name=parameter.name, label=effective) -> None:  # noqa: ANN001
                                if e.value:
                                    r.levels[name] = e.value
                                else:
                                    r.levels.pop(name, None)
                                if label is not None:
                                    label.set_text(effective_ratio_text(r, chosen_parameters))

                            options = {"": "(なし)", **{lv.name: f"{lv.name} {_signed_percent(lv.value)}" for lv in parameter.levels}}
                            current = row.levels.get(parameter.name, "")
                            ui.select(
                                options,
                                label=parameter.name,
                                value=current if current in options else "",
                                on_change=on_level,
                            ).classes("w-36").mark(f"member-level-{index}-{p}")
                        ui.button(icon="delete", on_click=lambda r=row: remove(r)).props(
                            "flat dense round"
                        ).mark(f"member-delete-{index}")

        def remove(row: MemberRow) -> None:
            rows.remove(row)
            table.refresh()

        def add() -> None:
            rows.append(MemberRow(None, "", 100.0))
            table.refresh()

        table()
        ui.button("メンバーを追加", icon="add", on_click=add).props("flat").mark("member-add")
        error = ui.label("").classes("text-negative").mark("member-error")

        def apply() -> None:
            try:
                result = build_members(rows, originals, assigned, chosen_parameters)
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_apply(*result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("適用", on_click=apply).mark("member-apply")
    dialog.open()
```
(元の `open_members_dialog` の内容と見比べ、実効比率のラベルの配置だけが違うことを確かめる。選択の値が `options` にない(参照切れ)ときは「(なし)」を出し、適用で捨てる。)

`src/projectapp/views.py` の `open_members` を直す:

```python
    def open_members(self) -> None:
        open_members_dialog(
            self.project.members, self.assigned_count, self.apply_members, self.project.parameters
        )
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -5 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。既存のメンバーのダイアログのテスト(`member-name-<i>`・`member-ratio-<i>` の操作)も通ること(パラメータなしの見た目が変わっていない確認)。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: メンバーのダイアログで段階を選べるようにし、実効比率を示す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 文書を直し、全体を確かめる

**Files:**
- Modify: `CLAUDE.md`(`projectapp/CLAUDE.md`)、`docs/development.md`、`.claude/MEMORY.md`

- [ ] **Step 1: `CLAUDE.md` を直す**

- 「`メンバー`（担当者）は、プロジェクトごとに名前と`相対比率`（基準の人を100%とした作業速度。10〜300%）で管理する」の項目を、次に置き換える: 「`メンバー`（担当者）は、プロジェクトごとに名前と`基本比率`（基準の人を100%とした作業速度の基本値）で管理する。`相対比率`は、`基本比率 + 選んだ段階の判定値の合計`で決まり、10〜300%に丸めて使う（丸めたときは、メンバーの画面に示す）」。
- その下に足す: 「`パラメータ`は、プロジェクト共通で、`プロジェクト`メニューの`パラメータ`で、名前と段階（名前と判定値-90〜+290%）を登録する。メンバーは、パラメータごとに段階を選ぶ（選ばなければ判定値0%）。パラメータ・段階の改名は、メンバーの選択に引き継ぐ。削除は、その段階を選んでいるメンバーがいるときに確認を出し、選択を外す（判定値0%になる）」。
- 「ヘッダー」の節の `プロジェクト`メニューを `新規プロジェクト作成`・`設定`・`メンバー`・`パラメータ` に直す。
- 「工数（時間）は…`工数 ÷ 担当者全員の（相対比率 × 割り当て率）の合計`」の項目に、「相対比率は、パラメータを反映した値」を足す。
- 「データの保存先」の節のプロジェクトの項目に、「パラメータ」を足す。

- [ ] **Step 2: `docs/development.md` を直す**

- 「ファイル形式の注意」に足す: 「パラメータは `Project.parameters`(`[{"name", "levels": [{"name", "value"}]}]`。`value` は割合で -0.9〜+2.9)、メンバーの選択は `Member.levels`(`{"パラメータ名": "段階名"}`)。キーがない・`null` は空。名前の空・重複、`value` の範囲外・非有限・型の違いは読込を拒否する。メンバーの選択が存在しないパラメータ・段階を指していても、読込は拒否せず、`ratios.ratio_detail` が判定値 0% として扱い、メンバーのダイアログの適用で捨てる。`Member.ratio` は基本比率」。
- モジュール構成の表に足す: `| `ratios.py` | 相対比率のパラメータ。`ratio_detail`・`effective_ratio`(基本比率 + 選んだ段階の判定値の合計。10〜300% に丸める)、`ParameterEdit`(旧い名前からの対応。削除は None)、`validate_parameters`、`apply_parameter_edit`(入れ替えや、削除と改名の組み合わせでも取り違えない)、`deletion_impacts`。純粋関数(NiceGUI に依存しない) |`。
- 設計書の一覧の表に `| メンバーの相対比率のパラメータ化 | `2026-10-09-ratio-parameters-design.md` |` を足す。

- [ ] **Step 3: `.claude/MEMORY.md` を直す**

要望 20 を「実装済み・実機確認待ち。ブランチ `feature/ratio-parameters`。設計書 `2026-10-09-ratio-parameters-design.md`、実装計画 `2026-10-09-ratio-parameters.md`。テスト N 件と `ty` が通る」に書き換える(決定の要約は残す)。「最終更新」の行と、未着手の要望の番号の列を直す。

- [ ] **Step 4: 全体を確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -4 && uvx ty check src | tail -2 && grep -rn "m\.ratio\|\.ratio\b" src | grep -v "ratios.py\|ratio_percent\|pixel_ratio\|member.ratio"`
Expected: 全件 PASS、`ty` の指摘なし。`grep` の結果は、`forms.py`(基本比率の検証と表示)と `storage.py`(読込)と `task_dialog.py` の `m.ratio`(実効比率のコピーを見る箇所)だけ。換算で `Member.ratio` を直接使う箇所が残っていないこと。結果の件数を `.claude/MEMORY.md` に書く。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "docs: 相対比率のパラメータ化の文書を直す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 実機確認をユーザーに依頼する**

ネイティブウィンドウ(`uv run projectapp`)で、次を確認してもらう。結果が届くまで、PR とマージはしない。
1. `プロジェクト > パラメータ` で、パラメータ「経験」と段階(初級 -20%・中級 0%・上級 +20%)を登録できる。名前が空・重複、判定値が範囲外のときは、エラーが出て適用されない。
2. `プロジェクト > メンバー` で、パラメータごとの選択が出る。段階を選ぶと、その行の「相対比率」がその場で変わる。基本比率 290% に上級(+20%)を選ぶと「300%(範囲に丸めました)」と出る。
3. 段階を選んだメンバーを担当にしたタスクの完了予定が、実効比率で変わる(上級を選ぶと早まる)。編集ダイアログの換算の説明も、実効比率で出る。
4. パラメータの段階の判定値を変えると、そのメンバーが担当するタスクの完了予定がすぐ変わる。
5. 使われている段階を削除しようとすると、確認が出る。削除すると、メンバーの選択が外れる。名前を変えると、選択が引き継がれる。
6. パラメータのないプロジェクト(古いファイル)で、メンバーのダイアログの見た目が変わっていない。保存して開き直しても、パラメータと選択が残る。
7. 担当者向けの書き出しの見積もりが、実効比率で出る。
8. ライト・ダーク両方、拡大・縮小しても、ダイアログの表示が崩れない。メンバーのダイアログが、パラメータが多いときも折り返して使える。
