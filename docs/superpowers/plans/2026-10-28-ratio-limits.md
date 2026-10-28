# 相対比率の加算分の上限・下限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** パラメータによる相対比率の加算分に、プロジェクトごとの上限・下限を設けられるようにする(要望 73)。

**Architecture:** `ratios.py` の `ratio_detail` / `effective_ratio` に `limits: RatioLimits | None` を足し、判定値の合計を `[下限, 上限]` に収めてから基本比率に足す(10〜300% の丸めは従来どおり、そのあと)。設定は `Project.ratio_limit_upper` / `ratio_limit_lower`(`None` は制限なし)として保存(version 13)。計算の呼び出し元(`timeline.py`・`decompose.py`・`task_dialog.py`・`forms.py`)へ `project.ratio_limits` を渡す。設定ダイアログに欄を足し、変更時に実績・進捗のあるタスクの完了予定の見直し確認を出す(`reassign.py` に純粋関数を足す)。

**Tech Stack:** Python 3.13、NiceGUI、pytest、`ty`、`uv`

**Spec:** `docs/superpowers/specs/2026-10-28-ratio-limits-design.md`

## Global Constraints

- 言語は日本語(UI 文言・コメント・テスト名の説明)。コメントは多くても 3 行以内。
- すべての関数に型ヒント(引数・戻り値)を付ける。`uv run ty check` を通す。
- 実行は `uv run pytest`、型は `uv run ty check`(リポジトリ直下 `/Users/jun/Documents/opt/work/projectapp` で)。
- 上限の範囲は 0〜+290%(`MAX_LEVEL_VALUE`)、下限は -90%〜0(`MIN_LEVEL_VALUE`)。保存は割合の小数(+50% は `0.5`)で、小数点以下 4 桁に丸める。
- 相対比率の丸めは `MIN_RATIO`(0.1)〜`MAX_RATIO`(3.0)のまま変えない。判定値の範囲も変えない。
- 既定(`None`・`None`)では、完了予定・換算率・見積もりが従来と 1 ビットも変わらない。
- `FORMAT_VERSION` は 12 → 13。キーのない古いファイル(version 12 以下)は制限なしとして読む。
- 3 者マージは、2 つの値をそれぞれ設定の 1 項目として比べる。
- コミットメッセージは日本語、末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。

## Review Focus

- 上限 0%(加点なし)・下限 0%(減点なし)の境界: 上限 0 のとき、プラスの判定値は効かないが、マイナスは効く。→ Task 1
- 基本比率が低く(例 30%)、下限 -50% を足すと負になる: 制限のあとの 10% の丸めが効き、負にならない。→ Task 1
- 手編集のファイルの不正値(文字列・真偽値・NaN・範囲外・上限にマイナス): 読込を拒否する。→ Task 2
- 制限の変更で、週ごとのタスク・担当者のいないタスク・メンバーにいない担当者のタスクは、見直し確認の対象にならない。→ Task 4
- 制限を変えたあとの元に戻す(Undo)で、設定も完了予定の見直しも一緒に戻る。→ Task 5

---

## File Structure

| ファイル | 役割 |
| --- | --- |
| `src/projectapp/models.py` | `RatioLimits`・`Project.ratio_limit_upper/lower`・`Project.ratio_limits`・`FORMAT_VERSION` 13 |
| `src/projectapp/ratios.py` | 制限の計算(`limit_adjustment`)・`ratio_detail`/`effective_ratio` の `limits`・内訳の注記(`limit_note`) |
| `src/projectapp/storage.py` | 読込の検証(`_ratio_limit`)。書き出しは `asdict(project)` で自動 |
| `src/projectapp/merge.py` | `SETTING_LABELS` とマージ後の `Project` 構築 |
| `src/projectapp/timeline.py` | `crew_of`・`assignees_rate` の `limits`、`conversion_rate`・`weekly_crews`・`Schedule` の呼び出し |
| `src/projectapp/decompose.py` | `assignees_rate` の呼び出し 2 か所 |
| `src/projectapp/task_dialog.py` | `ratio_limits` 引数。メンバーの実効比率・内訳の注記 |
| `src/projectapp/forms.py` | `build_ratio_limits`・設定ダイアログの欄・メンバー画面の `effective_ratio_text` |
| `src/projectapp/reassign.py` | `limit_reviews`(制限の変更で見直しが要るタスクと新しい完了予定) |
| `src/projectapp/views.py` | `apply_ratio_limits`(確認つき)・各ダイアログへの受け渡し |
| `test/test_ratios.py`・`test_storage.py`・`test_merge.py`・`test_reassign.py`・`test_forms.py`・`test_views.py`・`test_timeline.py` | テスト |
| `CLAUDE.md`・`docs/development.md`・`docs/requests.md`・`.claude/MEMORY.md` | 仕様と記録 |

---

### Task 0: ブランチの準備

**Files:** なし(git のみ)

- [ ] **Step 1: 要望 74 の記録を、ドキュメント用ブランチにコミットする**

```bash
cd /Users/jun/Documents/opt/work/projectapp
git branch --show-current   # docs/request-74 であること
git add docs/requests.md
git commit -m "docs: 要望 74(未着手の工数の合計と必要人数の可視化)を記録する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: `develop` から機能ブランチを切り、設計書と計画書をコミットする**

```bash
git checkout develop
git checkout -b feature/ratio-limits
git add docs/superpowers/specs/2026-10-28-ratio-limits-design.md docs/superpowers/plans/2026-10-28-ratio-limits.md
git commit -m "docs: 要望 73(相対比率の加算分の上限・下限)の設計書と実装計画" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Expected: `git status` がクリーン。`git branch --show-current` が `feature/ratio-limits`。

---

### Task 1: 計算(`models.py` の型と `ratios.py`)

**Files:**
- Modify: `src/projectapp/models.py`(`MAX_LEVEL_VALUE` の近く、`Project` の直前)
- Modify: `src/projectapp/ratios.py`(`RatioDetail`・`ratio_detail`・`effective_ratio`・新規 `limit_adjustment`・`limit_note`)
- Test: `test/test_ratios.py`

**Interfaces:**
- Produces:
  - `models.RatioLimits(upper: float | None = None, lower: float | None = None)`(凍結データクラス)
  - `ratios.limit_adjustment(adjustment: float, limits: RatioLimits | None) -> float`
  - `ratios.ratio_detail(member, parameters, only=None, limits=None) -> RatioDetail`。`RatioDetail` に `adjustment: float = 0.0`(制限前の加算分)と `limited: bool = False` を末尾に足す
  - `ratios.effective_ratio(member, parameters, only=None, limits=None) -> float`
  - `ratios.limit_note(detail: RatioDetail, limits: RatioLimits | None) -> str`(制限していなければ空文字)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_ratios.py` の import に `RatioLimits`(`projectapp.models` から)と `limit_adjustment`・`limit_note`(`projectapp.ratios` から)を足し、末尾に追加する。

```python
BIG = Parameter("大", [Level("高", 0.5), Level("低", -0.5)])
BIG2 = Parameter("大2", [Level("高", 0.5)])
BIG3 = Parameter("大3", [Level("高", 0.5)])
PILE = [BIG, BIG2, BIG3]


def test_without_limits_the_adjustments_are_added_as_before() -> None:
    member = Member("a", 1.0, {"大": "高", "大2": "高", "大3": "高"})
    assert effective_ratio(member, PILE) == pytest.approx(2.5)
    assert effective_ratio(member, PILE, limits=RatioLimits()) == pytest.approx(2.5)
    assert effective_ratio(member, PILE, limits=None) == pytest.approx(2.5)


def test_the_upper_limit_caps_the_sum_of_the_adjustments() -> None:
    member = Member("a", 1.0, {"大": "高", "大2": "高", "大3": "高"})
    detail = ratio_detail(member, PILE, limits=RatioLimits(upper=0.5))
    assert detail.adjustment == pytest.approx(1.5)
    assert detail.limited is True
    assert detail.raw == pytest.approx(1.5)
    assert detail.ratio == pytest.approx(1.5)


def test_the_lower_limit_floors_the_sum_of_the_adjustments() -> None:
    member = Member("a", 1.0, {"大": "低"})
    detail = ratio_detail(member, PILE, limits=RatioLimits(lower=-0.3))
    assert detail.adjustment == pytest.approx(-0.5)
    assert detail.ratio == pytest.approx(0.7)
    assert detail.limited is True


def test_a_sum_inside_the_limits_is_not_limited() -> None:
    member = Member("a", 1.0, {"経験": "上級"})
    detail = ratio_detail(member, PARAMETERS, limits=RatioLimits(upper=0.5, lower=-0.5))
    assert detail.limited is False
    assert detail.ratio == pytest.approx(1.2)


def test_a_sum_exactly_on_a_limit_is_not_reported_as_limited() -> None:
    member = Member("a", 1.0, {"大": "高"})
    detail = ratio_detail(member, PILE, limits=RatioLimits(upper=0.5))
    assert detail.limited is False
    assert detail.ratio == pytest.approx(1.5)


def test_an_upper_limit_of_zero_blocks_additions_but_not_reductions() -> None:
    plus = Member("a", 1.0, {"大": "高"})
    minus = Member("b", 1.0, {"大": "低"})
    zero_up = RatioLimits(upper=0.0)
    assert effective_ratio(plus, PILE, limits=zero_up) == pytest.approx(1.0)
    assert effective_ratio(minus, PILE, limits=zero_up) == pytest.approx(0.5)


def test_a_lower_limit_of_zero_blocks_reductions_but_not_additions() -> None:
    plus = Member("a", 1.0, {"大": "高"})
    minus = Member("b", 1.0, {"大": "低"})
    zero_down = RatioLimits(lower=0.0)
    assert effective_ratio(plus, PILE, limits=zero_down) == pytest.approx(1.5)
    assert effective_ratio(minus, PILE, limits=zero_down) == pytest.approx(1.0)


def test_the_limits_never_pull_a_high_base_ratio_below_the_base() -> None:
    fast = Member("a", 2.0, {"大": "高", "大2": "高"})
    assert effective_ratio(fast, PILE, limits=RatioLimits(upper=0.5)) == pytest.approx(2.5)


def test_the_limits_apply_to_the_tagged_parameters_only() -> None:
    member = Member("a", 1.0, {"大": "高", "大2": "高", "大3": "高"})
    assert effective_ratio(member, PILE, ["大", "大2"], RatioLimits(upper=0.5)) == pytest.approx(1.5)
    assert effective_ratio(member, PILE, ["大"], RatioLimits(upper=0.5)) == pytest.approx(1.5)  # 制限内


def test_the_rounding_to_the_ratio_range_still_applies_after_the_limits() -> None:
    slow = Member("a", 0.3, {"大": "低"})
    detail = ratio_detail(slow, PILE, limits=RatioLimits(lower=-0.5))
    assert detail.raw == pytest.approx(-0.2)
    assert detail.ratio == pytest.approx(0.1)
    assert detail.clamped is True and detail.limited is False


def test_limit_adjustment_handles_one_sided_and_missing_limits() -> None:
    assert limit_adjustment(0.8, None) == 0.8
    assert limit_adjustment(0.8, RatioLimits(upper=0.5)) == 0.5
    assert limit_adjustment(-0.8, RatioLimits(upper=0.5)) == -0.8
    assert limit_adjustment(-0.8, RatioLimits(lower=-0.5)) == -0.5
    assert limit_adjustment(0.8, RatioLimits(lower=-0.5)) == 0.8


def test_limit_note_names_the_limit_only_when_it_was_applied() -> None:
    member = Member("a", 1.0, {"大": "高", "大2": "高", "大3": "高"})
    up = RatioLimits(upper=0.5)
    assert limit_note(ratio_detail(member, PILE, limits=up), up) == "加算分 +150% → 上限 +50% に制限"
    down = RatioLimits(lower=-0.3)
    low = Member("b", 1.0, {"大": "低"})
    assert limit_note(ratio_detail(low, PILE, limits=down), down) == "加算分 -50% → 下限 -30% に制限"
    assert limit_note(ratio_detail(member, PILE), None) == ""
    assert limit_note(ratio_detail(member, PILE, limits=RatioLimits(upper=2.9)), RatioLimits(upper=2.9)) == ""
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest test/test_ratios.py -q`
Expected: FAIL(`ImportError: cannot import name 'RatioLimits'`)

- [ ] **Step 3: `models.py` に型と定数を足す**

`MIN_LEVEL_VALUE, MAX_LEVEL_VALUE = -0.9, 2.9` の行のあとに追加(`Project` の定義より前に `RatioLimits` を置く。`dataclass` は import 済み):

```python
@dataclass(frozen=True)
class RatioLimits:
    """相対比率の加算分(判定値の合計)の上限・下限。None の側は制限しない。"""

    upper: float | None = None
    lower: float | None = None
```

`Project` に、`plantuml_overload_notice` の次の行へフィールドを、`task_map` の前にプロパティを足す:

```python
    ratio_limit_upper: float | None = None  # 相対比率の加算分の上限(+50% は 0.5)。None は制限なし
    ratio_limit_lower: float | None = None  # 同じく下限(-50% は -0.5)
```

```python
    @property
    def ratio_limits(self) -> RatioLimits:
        return RatioLimits(self.ratio_limit_upper, self.ratio_limit_lower)
```

- [ ] **Step 4: `ratios.py` を実装する**

import に `RatioLimits` を足す(`from projectapp.models import ... RatioLimits ...`)。`RatioDetail` の末尾にフィールドを足す:

```python
    adjustment: float = 0.0  # 制限する前の加算分(判定値の合計)
    limited: bool = False  # 上限か下限で加算分を収めたか
```

`ratio_detail` を次の形に置き換える(シグネチャと末尾の計算。ループは今のまま):

```python
def limit_adjustment(adjustment: float, limits: RatioLimits | None) -> float:
    """加算分を [下限, 上限] に収める。None の側は収めない。"""
    if limits is None:
        return adjustment
    if limits.upper is not None and adjustment > limits.upper:
        return limits.upper
    if limits.lower is not None and adjustment < limits.lower:
        return limits.lower
    return adjustment


def ratio_detail(
    member: Member,
    parameters: list[Parameter],
    only: Collection[str] | None = None,
    limits: RatioLimits | None = None,
) -> RatioDetail:
    """(docstring は今のまま。末尾に追記)limits があれば、判定値の合計をその範囲に収めてから基本比率に足す。"""
    counted = set(only) if only else None
    adjustments: list[tuple[str, str, float]] = []
    for parameter in parameters:
        ...  # 今のループのまま
    total = sum(value for _, _, value in adjustments)
    adjustment = round(total, 4)
    bounded = limit_adjustment(adjustment, limits)
    limited = bounded != adjustment
    # 保存する値は小数点以下 4 桁までなので、足し算の誤差(0.3 - 0.2 = 0.0999…)で境界を外さないよう丸める
    raw = round(member.ratio + (bounded if limited else total), 4)
    ratio = min(max(raw, MIN_RATIO), MAX_RATIO) if isfinite(raw) else member.ratio
    return RatioDetail(member.ratio, adjustments, raw, ratio, ratio != raw, adjustment, limited)


def effective_ratio(
    member: Member,
    parameters: list[Parameter],
    only: Collection[str] | None = None,
    limits: RatioLimits | None = None,
) -> float:
    """計算に使う相対比率。"""
    return ratio_detail(member, parameters, only, limits).ratio


def limit_note(detail: RatioDetail, limits: RatioLimits | None) -> str:
    """内訳に添える注記。加算分を制限したときだけ。例: 加算分 +150% → 上限 +50% に制限。"""
    if limits is None or not detail.limited:
        return ""
    if limits.upper is not None and detail.adjustment > limits.upper:
        return f"加算分 {detail.adjustment * 100:+g}% → 上限 {limits.upper * 100:+g}% に制限"
    assert limits.lower is not None
    return f"加算分 {detail.adjustment * 100:+g}% → 下限 {limits.lower * 100:+g}% に制限"
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest test/test_ratios.py -q && uv run ty check`
Expected: すべて PASS、ty はエラーなし

- [ ] **Step 6: コミットする**

```bash
git add src/projectapp/models.py src/projectapp/ratios.py test/test_ratios.py
git commit -m "feat: 相対比率の加算分に上限・下限を設けられる計算を足す(要望 73)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ファイル形式(version 13)と 3 者マージ

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION`)
- Modify: `src/projectapp/storage.py`(`_ratio_limit` と `parse_project`)
- Modify: `src/projectapp/merge.py`(`SETTING_LABELS` と `Project(...)` の構築)
- Test: `test/test_storage.py`、`test/test_merge.py`、`test/test_reference_storage.py:39`、`test/test_summary.py:72`

**Interfaces:**
- Consumes: Task 1 の `Project.ratio_limit_upper/lower`
- Produces: `storage._ratio_limit(value: Any, name: str, low: float, high: float) -> float | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の末尾に追加する(同ファイルの既存テストの import と書き方に合わせる。`dumps_project`・`parse_project`・`save_project`・`load_project`・`Project` は既に import 済みのはず。なければ足す)。

```python
def test_the_ratio_limits_round_trip_and_default_to_none() -> None:
    project = Project("p", ratio_limit_upper=0.5, ratio_limit_lower=-0.5)
    loaded = parse_project(dumps_project(project), "p")
    assert (loaded.ratio_limit_upper, loaded.ratio_limit_lower) == (0.5, -0.5)
    plain = parse_project(dumps_project(Project("p")), "p")
    assert (plain.ratio_limit_upper, plain.ratio_limit_lower) == (None, None)


def test_a_file_without_the_ratio_limit_keys_reads_as_no_limits() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw.pop("ratio_limit_upper")
    raw.pop("ratio_limit_lower")
    raw["version"] = 12
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.ratio_limits.upper is None and loaded.ratio_limits.lower is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ratio_limit_upper", "0.5"),
        ("ratio_limit_upper", True),
        ("ratio_limit_upper", float("nan")),
        ("ratio_limit_upper", -0.1),
        ("ratio_limit_upper", 3.0),
        ("ratio_limit_lower", 0.1),
        ("ratio_limit_lower", -0.95),
        ("ratio_limit_lower", [0]),
    ],
)
def test_an_invalid_ratio_limit_is_rejected(key: str, value: object) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw[key] = value
    with pytest.raises(ValueError, match="相対比率の"):
        parse_project(json.dumps(raw), "p")


def test_the_ratio_limits_are_rounded_to_four_decimals() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["ratio_limit_upper"] = 0.123456
    assert parse_project(json.dumps(raw), "p").ratio_limit_upper == 0.1235
```

`json.dumps` が NaN を `NaN` と書き、`json.loads` が読める(Python 標準)ので、このテストは成り立つ。

`test/test_merge.py` の末尾に追加(`proj()` は既存のヘルパー。`reference_mode` の既存テストと同じ形):

```python
def test_the_ratio_limits_merge_as_settings() -> None:
    merged = merge_projects(proj(), proj(ratio_limit_upper=0.5), proj(ratio_limit_lower=-0.5))
    assert merged.project.ratio_limit_upper == 0.5
    assert merged.project.ratio_limit_lower == -0.5 and merged.conflicts == []


def test_different_limits_on_both_sides_are_a_conflict_with_a_readable_label() -> None:
    merged = merge_projects(proj(), proj(ratio_limit_upper=0.5), proj(ratio_limit_upper=0.3))
    assert [c.label for c in merged.conflicts] == ["相対比率の上限"]
```

`merged.conflicts` の要素の属性名は、同ファイルの既存の衝突テスト(`test_a_snapshot_changed_on_both_sides_is_a_conflict_with_a_readable_label`)を見て合わせる。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest test/test_storage.py test/test_merge.py -q -k "ratio_limit or limits"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`models.py`: `FORMAT_VERSION = 12` を `13` に変え、コメントの末尾の `12: PlantUML の通知の設定〔plantuml_overload_notice〕)` を `12: PlantUML の通知の設定〔plantuml_overload_notice〕。13: 相対比率の加算分の上限・下限〔ratio_limit_upper・ratio_limit_lower〕)` にする。

`storage.py`: `_plantuml_overload_notice` の次に追加する(`isfinite` と `MAX_LEVEL_VALUE`・`MIN_LEVEL_VALUE` が未 import なら足す):

```python
def _ratio_limit(value: Any, name: str, low: float, high: float) -> float | None:
    """相対比率の加算分の上限・下限。null は制限なし。数値以外・非有限・範囲外は ValueError。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise ValueError(f"{name}が正しくありません: {value!r}")
    if not low - 1e-9 <= value <= high + 1e-9:
        raise ValueError(f"{name}は{low * 100:+g}〜{high * 100:+g}%で指定してください: {value!r}")
    return round(float(value), 4)
```

`parse_project` の `plantuml_overload_notice=(...)` の次に足す:

```python
        ratio_limit_upper=(
            _ratio_limit(raw.get("ratio_limit_upper"), "相対比率の上限", 0.0, MAX_LEVEL_VALUE) if ctx.version >= 13 else None
        ),
        ratio_limit_lower=(
            _ratio_limit(raw.get("ratio_limit_lower"), "相対比率の下限", MIN_LEVEL_VALUE, 0.0) if ctx.version >= 13 else None
        ),
```

`merge.py`: `SETTING_LABELS` の辞書の末尾に `"ratio_limit_upper": "相対比率の上限", "ratio_limit_lower": "相対比率の下限"` を足し、`Project(...)` の構築の `plantuml_overload_notice=settings["plantuml_overload_notice"],` の次に足す:

```python
        ratio_limit_upper=settings["ratio_limit_upper"],
        ratio_limit_lower=settings["ratio_limit_lower"],
```

`test/test_storage.py` の `== 12`(1311・1379・1903・1945 行)、`test/test_reference_storage.py:39`、`test/test_summary.py:72` の `12` を `13` に直す。

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest test/test_storage.py test/test_merge.py test/test_reference_storage.py test/test_summary.py -q && uv run ty check`
Expected: すべて PASS

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/models.py src/projectapp/storage.py src/projectapp/merge.py test/
git commit -m "feat: 相対比率の上限・下限をファイル(version 13)に保存し、3 者マージで比べる(要望 73)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 計算の呼び出し元へ制限を渡す(`timeline`・`decompose`・`task_dialog`・`forms` の内訳)

**Files:**
- Modify: `src/projectapp/timeline.py`(`crew_of`・`assignees_rate`・`conversion_rate`・`weekly_crews`・`Schedule` 内の `crew_of` 呼び出し〔594 行付近〕)
- Modify: `src/projectapp/decompose.py`(`assignees_rate` の 2 か所〔90・109 行付近〕)
- Modify: `src/projectapp/task_dialog.py`(`open_task_dialog` の `ratio_limits` 引数、メンバーの実効比率、内訳の注記)
- Modify: `src/projectapp/forms.py`(`effective_ratio_text`・`members_panel`・`open_members_parameters_dialog`)
- Modify: `src/projectapp/views.py`(`link_args`・`open_members_parameters`)
- Test: `test/test_timeline.py`、`test/test_schedule.py`、`test/test_forms.py`、`test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 の `RatioLimits`・`effective_ratio(..., limits)`・`limit_note`
- Produces:
  - `timeline.crew_of(assignees, members, parameters=None, only=None, limits=None)`
  - `timeline.assignees_rate(assignees, members, parameters=None, only=None, limits=None)`
  - `forms.effective_ratio_text(row, parameters, limits=None) -> str`
  - `open_task_dialog(..., ratio_limits: RatioLimits | None = None)`
  - `open_members_parameters_dialog(..., get_limits: Callable[[], RatioLimits] = RatioLimits)`、`members_panel(..., get_limits=RatioLimits)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py` の末尾に追加(`Project`・`Member`・`Parameter`・`Level`・`Task`・`Assignee` の import は同ファイルの既存を使う。足りなければ足す):

```python
def _limited_project(**limits: float) -> tuple[Project, Task]:
    parameters = [Parameter("a", [Level("高", 0.5)]), Parameter("b", [Level("高", 0.5)]), Parameter("c", [Level("高", 0.5)])]
    member = Member("田中", 1.0, {"a": "高", "b": "高", "c": "高"})
    task = Task("t", assignees=[Assignee("田中", 1.0)], effort_hours=10.0)
    return Project("p", members=[member], parameters=parameters, tasks=[task], **limits), task


def test_conversion_rate_uses_the_project_ratio_limits() -> None:
    free, task = _limited_project()
    assert conversion_rate(task, free) == pytest.approx(2.5)
    capped, task = _limited_project(ratio_limit_upper=0.5)
    assert conversion_rate(task, capped) == pytest.approx(1.5)


def test_the_planned_end_follows_the_ratio_limits() -> None:
    free, task = _limited_project()
    capped, capped_task = _limited_project(ratio_limit_upper=0.5)
    capped_task.planned_start = task.planned_start = datetime(2026, 10, 5, 9)
    free_end = Schedule(free, {}).finish(task)
    capped_end = Schedule(capped, {}).finish(capped_task)
    assert free_end is not None and capped_end is not None and capped_end > free_end
```

`conversion_rate`・`Schedule` は既存の import を確認する。`Schedule.finish` は `views.link_args` で使われているのと同じ呼び出し。

`test/test_forms.py` の末尾に追加(`MemberRow` の引数は既存テストの書き方に合わせる):

```python
def test_effective_ratio_text_reports_a_limited_sum() -> None:
    params = [Parameter("a", [Level("高", 0.5)]), Parameter("b", [Level("高", 0.5)]), Parameter("c", [Level("高", 0.5)])]
    row = MemberRow("田中", "田中", 100.0, {"a": "高", "b": "高", "c": "高"})
    assert effective_ratio_text(row, params) == "相対比率 250%"
    text = effective_ratio_text(row, params, RatioLimits(upper=0.5))
    assert text == "相対比率 150%(加算分 +150% → 上限 +50% に制限)"
```

`MemberRow` の位置引数が合わなければ、同ファイルの既存の `effective_ratio_text` のテストの組み立てをそのまま真似る。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest test/test_timeline.py test/test_forms.py -q -k "limit"`
Expected: FAIL

- [ ] **Step 3: `timeline.py` を直す**

`from projectapp.models import ...` に `RatioLimits` を足す。`crew_of` と `assignees_rate` に `limits: RatioLimits | None = None` を足し、`effective_ratio(by_name[a.name], chosen, only, limits)`、`crew_of(assignees, members, parameters, only, limits)` と渡す。`conversion_rate`・`weekly_crews` と、`Schedule` 内の `crew_of(task.assignees, project.members, project.parameters, task.parameters)`(594 行付近)に、末尾の引数として `project.ratio_limits` を足す:

```python
def conversion_rate(task: Task, project: Project) -> float:
    return assignees_rate(task.assignees, project.members, project.parameters, task.parameters, project.ratio_limits)


def weekly_crews(task: Task, project: Project) -> list[list[Worker]]:
    return [crew_of(week, project.members, project.parameters, task.parameters, project.ratio_limits) for week in task.weekly_crew]
```

`decompose.py` の `assignees_rate(...)` 2 か所にも `project.ratio_limits` を末尾の引数として足す(`_worked_rate` の 90 行付近と、`settle` の 109 行付近)。

- [ ] **Step 4: `forms.py`・`task_dialog.py`・`views.py` を直す**

`forms.py`:

```python
def effective_ratio_text(row: MemberRow, parameters: list[Parameter], limits: RatioLimits | None = None) -> str:
    """(docstring は今のまま)制限したときは、その注記を添える。"""
    percent = row.ratio_percent
    if percent is None or not isfinite(percent):
        return ""
    detail = ratio_detail(Member(row.name, percent / 100, row.levels), parameters, limits=limits)
    notes = ["範囲に丸めました"] if detail.clamped else []
    if note := limit_note(detail, limits):
        notes.append(note)
    suffix = f"({'・'.join(notes)})" if notes else ""
    return f"相対比率 {detail.ratio * 100:g}%{suffix}"
```

既存の `(範囲に丸めました)` の表示(`note = "(範囲に丸めました)"`)は、`notes` が 1 件のときに同じ文字列になるので、既存テストの期待は変わらない(`"相対比率 120%(範囲に丸めました)"` など)。`members_panel` に `get_limits: Callable[[], RatioLimits] = RatioLimits` を足し(`pick_icon` の後ろ)、1813・1865 行付近の `effective_ratio_text(r, chosen_parameters)` を `effective_ratio_text(r, chosen_parameters, get_limits())` にする。`open_members_parameters_dialog` にも同じ引数を足して `members_panel(..., get_limits)` へ渡す。import に `RatioLimits`(models)と `limit_note`(ratios)を足す。

`views.py`: `open_members_parameters` の `open_members_parameters_dialog(...)` に `get_limits=lambda: self.project.ratio_limits,` を足す。`link_args` の辞書に `"ratio_limits": self.project.ratio_limits,` を足す。

`task_dialog.py`: `open_task_dialog` の引数に `ratio_limits: RatioLimits | None = None` を足す(`parameters` の近く)。メンバーの実効比率の 2 か所を直す:

```python
    member_list = [
        Member(m.name, effective_ratio(m, parameters or [], chosen_parameters, ratio_limits), work_days=list(m.work_days))
        for m in raw_members
    ]
```

```python
                member.ratio = effective_ratio(by_name[member.name], parameters or [], chosen_parameters, ratio_limits)
```

内訳の注記: `refresh_conversion` の通常の分岐(1066 行付近)で、`detail` のあとに制限の注記を足す。担当者の元メンバー(`raw_members`)から `ratio_detail` を引き直して、制限した人だけ並べる:

```python
        def limit_notes(names: list[str]) -> str:
            """制限した担当者の注記(例: 田中 加算分 +150% → 上限 +50% に制限)。"""
            by_name = {m.name: m for m in raw_members}
            notes = []
            for name in names:
                if name in by_name and (
                    note := limit_note(ratio_detail(by_name[name], parameters or [], chosen_parameters, ratio_limits), ratio_limits)
                ):
                    notes.append(f"{name} {note}")
            return f"・{'・'.join(notes)}" if notes else ""
```

通常の分岐の `conversion.set_text(...)` の `tagged` の後ろに `{limit_notes([m.name for m, _ in chosen])}` を足す(`f"換算率 {rate * 100:g}%({detail}{tagged}{limit_notes(...)})→ ..."`)。週ごとの分岐も、`tagged` の後ろに `limit_notes([m.name for week in weeks for m, _ in week])` を足す。import に `ratio_detail`・`limit_note`・`RatioLimits` を足す。

- [ ] **Step 5: ダイアログのテストを書く**

`test/test_task_dialog.py` に追加する。同ファイルの既存の換算率のテスト(`task-conversion` のマーカーを読むもの)の組み立てを真似る:

```python
async def test_the_conversion_text_names_a_limited_assignee(user: User) -> None:
    params = [Parameter("a", [Level("高", 0.5)]), Parameter("b", [Level("高", 0.5)]), Parameter("c", [Level("高", 0.5)])]
    member = Member("田中", 1.0, {"a": "高", "b": "高", "c": "高"})
    task = Task("t", assignees=[Assignee("田中", 1.0)], effort_hours=10.0, parameters=["a", "b", "c"])

    @ui.page("/")
    def index() -> None:
        open_task_dialog(
            task, lambda t: None, members=[member], parameters=params,
            ratio_limits=RatioLimits(upper=0.5), daily_hours=6.5,
        )

    await user.open("/")
    text = user.find(marker="task-conversion").elements.pop().text
    assert "換算率 150%" in text and "田中 加算分 +150% → 上限 +50% に制限" in text
```

`open_task_dialog` の他の必須引数が足りないときは、既存テストの呼び出しに合わせる。

- [ ] **Step 6: テストが通ることを確認する**

Run: `uv run pytest test/test_timeline.py test/test_schedule.py test/test_forms.py test/test_task_dialog.py test/test_decompose_ui.py test/test_handoff.py -q && uv run ty check`
Expected: すべて PASS(既存の期待は、制限なしで変わらない)

- [ ] **Step 7: 他に判定値を直接足している箇所がないか確認する**

Run: `grep -rn "\.levels\|level\.value\|\.value for .* in .*levels" src/projectapp | grep -v "^src/projectapp/ratios.py"`
Expected: メンバー画面の段階の選択・パラメータ編集の行のみ(計算には使っていない)。計算に使っている箇所が見つかったら、`limits` を通す。

- [ ] **Step 8: コミットする**

```bash
git add src/projectapp test
git commit -m "feat: 完了予定・換算率・内訳に、相対比率の上限・下限を反映する(要望 73)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 制限の変更で見直しが要るタスクの算出(`reassign.py`)

**Files:**
- Modify: `src/projectapp/reassign.py`
- Test: `test/test_reassign.py`

**Interfaces:**
- Consumes: Task 3 の `assignees_rate(..., limits)`・`crew_of(..., limits)`、既存の `needs_review`・`reviewed_end`
- Produces: `reassign.limit_reviews(project: Project, new_limits: RatioLimits, holidays: dict[date, str], now: datetime) -> list[tuple[Task, datetime]]`(見直しが要るタスクと、新しい完了予定。`project` は変えない)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_reassign.py` の末尾に追加する(import に `limit_reviews`、`RatioLimits`・`Project`・`Member`・`Parameter`・`Level`・`Task`・`Assignee`・`Actual`〔実績の型。名前は `models.py` で確認〕を足す):

```python
NOW = datetime(2026, 10, 12, 10)


def _project_with(*tasks: Task) -> Project:
    parameters = [Parameter("a", [Level("高", 0.5)]), Parameter("b", [Level("高", 0.5)]), Parameter("c", [Level("高", 0.5)])]
    member = Member("田中", 1.0, {"a": "高", "b": "高", "c": "高"})
    return Project("p", members=[member], parameters=parameters, tasks=list(tasks), daily_hours=8.0)


def _worked(**extra: object) -> Task:
    return Task(
        "t", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50,
        planned_start=datetime(2026, 10, 5, 9), **extra,
    )


def test_a_task_with_progress_needs_a_review_when_the_limit_changes_its_rate() -> None:
    task = _worked()
    result = limit_reviews(_project_with(task), RatioLimits(upper=0.5), {}, NOW)
    assert [t is task for t, _ in result] == [True]
    assert result[0][1] > NOW


def test_nothing_needs_a_review_when_the_limits_do_not_change_the_rate() -> None:
    assert limit_reviews(_project_with(_worked()), RatioLimits(), {}, NOW) == []
    assert limit_reviews(_project_with(_worked()), RatioLimits(upper=2.9), {}, NOW) == []


@pytest.mark.parametrize(
    "task",
    [
        Task("未着手", assignees=[Assignee("田中", 1.0)], effort_hours=20.0),  # 実績も進捗度もない
        Task("終了", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.DONE, progress=50),
        Task("担当なし", effort_hours=20.0, status=Status.RUNNING, progress=50),
        Task("工数なし", assignees=[Assignee("田中", 1.0)], status=Status.RUNNING, progress=50),
        Task("メンバー外", assignees=[Assignee("鈴木", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50),
        Task("週ごと", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50,
             weekly_crew=[[Assignee("田中", 1.0)]]),
    ],
    ids=lambda t: t.name,
)
def test_tasks_outside_the_review_conditions_are_skipped(task: Task) -> None:
    assert limit_reviews(_project_with(task), RatioLimits(upper=0.5), {}, NOW) == []


def test_limit_reviews_does_not_change_the_project() -> None:
    task = _worked()
    project = _project_with(task)
    before = deepcopy(project)
    limit_reviews(project, RatioLimits(upper=0.5), {}, NOW)
    assert project == before
```

`Status` の値名(`RUNNING` など)と `deepcopy` の import は、同ファイル・`models.py` の実名に合わせる。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest test/test_reassign.py -q -k "limit"`
Expected: FAIL(`ImportError: cannot import name 'limit_reviews'`)

- [ ] **Step 3: 実装する**

`reassign.py` の import を `from projectapp.models import Project, RatioLimits, Status, Task, TaskKind` と `from projectapp.timeline import Worker, assignees_rate, calc_end, combine_rate, crew_of` にして、末尾に追加する:

```python
def limit_reviews(
    project: Project, new_limits: RatioLimits, holidays: dict[date, str], now: datetime
) -> list[tuple[Task, datetime]]:
    """上限・下限を new_limits に変えたとき、完了予定の見直しが要るタスクと、見直した完了予定。project は変えない。"""
    result: list[tuple[Task, datetime]] = []
    for task in project.all_tasks():
        args = (task.assignees, project.members, project.parameters, task.parameters)
        old_rate = assignees_rate(*args, project.ratio_limits)
        new_rate = assignees_rate(*args, new_limits)
        if not needs_review(task, old_rate, new_rate):
            continue
        crew = crew_of(*args, new_limits)
        end = reviewed_end(task, old_rate, new_rate, project.daily_hours, project.work_start, holidays, now, crew)
        if end is not None:
            result.append((task, end))
    return result
```

`timeline.py` が `reassign.py` を import していないこと(循環しないこと)を確認する: `grep -n "reassign" src/projectapp/timeline.py` が空であること。

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest test/test_reassign.py -q && uv run ty check`
Expected: すべて PASS

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/reassign.py test/test_reassign.py
git commit -m "feat: 上限・下限の変更で完了予定の見直しが要るタスクを算出する(要望 73)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 設定ダイアログと適用(確認つき・Undo)

**Files:**
- Modify: `src/projectapp/forms.py`(`build_ratio_limits`・`open_settings_dialog`)
- Modify: `src/projectapp/views.py`(`apply_ratio_limits`・`open_settings_dialog` の呼び出し)
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 4 の `limit_reviews`、Task 1 の `RatioLimits`
- Produces:
  - `forms.build_ratio_limits(upper_text: str, lower_text: str) -> RatioLimits`(空欄は `None`。範囲外・数値でない・非有限は `ValueError`)
  - `open_settings_dialog(..., ratio_limits: RatioLimits = RatioLimits(), on_ratio_limits: Callable[[RatioLimits], object] | None = None)`
  - `MainView.apply_ratio_limits(limits: RatioLimits) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の末尾に追加する(import に `build_ratio_limits`・`RatioLimits`):

```python
def test_build_ratio_limits_reads_percent_text() -> None:
    assert build_ratio_limits("50", "-50") == RatioLimits(0.5, -0.5)
    assert build_ratio_limits("", "") == RatioLimits(None, None)
    assert build_ratio_limits(" 0 ", "0") == RatioLimits(0.0, 0.0)
    assert build_ratio_limits("12.34567", "") == RatioLimits(0.1235, None)


@pytest.mark.parametrize(
    ("upper", "lower"),
    [("abc", ""), ("", "x"), ("-1", ""), ("291", ""), ("", "1"), ("", "-91"), ("nan", ""), ("inf", ""), ("", "-inf")],
)
def test_build_ratio_limits_rejects_invalid_input(upper: str, lower: str) -> None:
    with pytest.raises(ValueError, match="上限|下限"):
        build_ratio_limits(upper, lower)


async def test_the_settings_dialog_reports_changed_ratio_limits(user: User) -> None:
    applied: list[RatioLimits] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(
            6.5, time(9, 0), lambda *a: None, ratio_limits=RatioLimits(), on_ratio_limits=applied.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-limit-upper").elements.pop().set_value("50")
    user.find(marker="settings-limit-lower").elements.pop().set_value("-50")
    user.find(marker="settings-apply").click()
    assert applied == [RatioLimits(0.5, -0.5)]


async def test_the_preset_button_fills_plus_and_minus_fifty(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(
            6.5, time(9, 0), lambda *a: None, ratio_limits=RatioLimits(), on_ratio_limits=lambda limits: None))

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-limit-preset").click()
    assert user.find(marker="settings-limit-upper").elements.pop().value == "50"
    assert user.find(marker="settings-limit-lower").elements.pop().value == "-50"


async def test_the_settings_dialog_does_not_report_unchanged_ratio_limits(user: User) -> None:
    applied: list[RatioLimits] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(
            6.5, time(9, 0), lambda *a: None, ratio_limits=RatioLimits(0.5, None), on_ratio_limits=applied.append))

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="settings-limit-upper").elements.pop().value == "50"
    user.find(marker="settings-apply").click()
    assert applied == []


async def test_an_invalid_ratio_limit_shows_an_error_and_keeps_the_dialog(user: User) -> None:
    applied: list[RatioLimits] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(
            6.5, time(9, 0), lambda *a: None, ratio_limits=RatioLimits(), on_ratio_limits=applied.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-limit-upper").elements.pop().set_value("500")
    user.find(marker="settings-apply").click()
    assert applied == []
    await user.should_see("上限")
```

`test/test_views.py` の末尾に追加する(`test_apply_plantuml_notice_is_an_undoable_unsaved_edit` と同じ組み立て):

```python
def _progress_project() -> Project:
    parameters = [Parameter("a", [Level("高", 0.5)]), Parameter("b", [Level("高", 0.5)]), Parameter("c", [Level("高", 0.5)])]
    member = Member("田中", 1.0, {"a": "高", "b": "高", "c": "高"})
    task = Task("実装", assignees=[Assignee("田中", 1.0)], effort_hours=20.0, status=Status.RUNNING, progress=50,
                planned_start=datetime(2026, 10, 5, 9))
    return Project("既存", members=[member], parameters=parameters, sections=[Section("開発", [task])])


async def test_apply_ratio_limits_without_affected_tasks_is_an_undoable_unsaved_edit(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(Project("既存", sections=[Section("開発", [Task("実装")])]), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.apply_ratio_limits(RatioLimits(0.5, -0.5))
    assert (view.project.ratio_limit_upper, view.project.ratio_limit_lower) == (0.5, -0.5) and view.is_dirty()
    view.undo()
    assert view.project.ratio_limits == RatioLimits() and not view.is_dirty()


async def test_apply_ratio_limits_asks_before_changing_a_task_with_progress(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(_progress_project(), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.apply_ratio_limits(RatioLimits(0.5, None))
    await user.should_see("見直して適用")
    assert view.project.ratio_limit_upper is None  # 確認の前は変わらない
    user.find(marker="limit-review-cancel").click()
    assert view.project.ratio_limit_upper is None and not view.is_dirty()


async def test_apply_ratio_limits_with_review_sets_the_manual_planned_end_in_one_undo_step(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(_progress_project(), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.apply_ratio_limits(RatioLimits(0.5, None))
    user.find(marker="limit-review-apply").click()
    task = view.project.all_tasks()[0]
    assert view.project.ratio_limit_upper == 0.5
    assert task.planned_end_manual is True and task.planned_end is not None
    view.undo()
    task = view.project.all_tasks()[0]
    assert view.project.ratio_limit_upper is None and task.planned_end_manual is False and not view.is_dirty()


async def test_apply_ratio_limits_without_review_keeps_the_planned_end(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    save_project(_progress_project(), tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    view.apply_ratio_limits(RatioLimits(0.5, None))
    user.find(marker="limit-review-skip").click()
    task = view.project.all_tasks()[0]
    assert view.project.ratio_limit_upper == 0.5 and task.planned_end_manual is False
```

(`Status`・`Level`・`Parameter`・`Member`・`Assignee`・`Section` などの import は同ファイルの既存を確認して足す。`planned_end_manual` の既定は `False`。)

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -k "ratio_limit or preset"`
Expected: FAIL

- [ ] **Step 3: `forms.py` を実装する**

`build_work_settings` の近くに追加する:

```python
def build_ratio_limits(upper_text: str, lower_text: str) -> RatioLimits:
    """相対比率の加算分の上限・下限(%)の入力を検証する。空欄は制限なし。"""

    def read(text: str, name: str, low: float, high: float) -> float | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = float(text) / 100
        except ValueError:
            raise ValueError(f"{name}は数値で入力してください") from None
        if not isfinite(value) or not low - 1e-9 <= value <= high + 1e-9:
            raise ValueError(f"{name}は{low * 100:+g}〜{high * 100:+g}%で入力してください")
        return round(value, 4)

    return RatioLimits(
        read(upper_text, "相対比率の上限", 0.0, MAX_LEVEL_VALUE),
        read(lower_text, "相対比率の下限", MIN_LEVEL_VALUE, 0.0),
    )
```

`open_settings_dialog` のシグネチャ末尾に `ratio_limits: RatioLimits = RatioLimits(),` と `on_ratio_limits: Callable[[RatioLimits], object] | None = None,` を足す。`notice` のチェックボックスの次(`rows = [TemplateRow(...)` の前)に節を足す:

```python
        limit_upper = limit_lower = None
        if on_ratio_limits is not None:
            ui.label("相対比率の加算分の制限").classes("text-caption text-grey")
            ui.label(
                "パラメータの判定値の合計に上限・下限を設けます(空欄は制限なし)。基本比率 100% で +50% なら最大 150%"
            ).classes("text-caption text-grey")
            with ui.row().classes("items-center"):
                limit_upper = ui.input(
                    "上限(%)", value="" if ratio_limits.upper is None else f"{ratio_limits.upper * 100:g}"
                ).props("dense").classes("w-28").mark("settings-limit-upper")
                limit_lower = ui.input(
                    "下限(%)", value="" if ratio_limits.lower is None else f"{ratio_limits.lower * 100:g}"
                ).props("dense").classes("w-28").mark("settings-limit-lower")

                def fill_preset() -> None:
                    limit_upper.set_value("50")
                    limit_lower.set_value("-50")

                ui.button("+50% / -50%", on_click=fill_preset).props("flat dense").mark("settings-limit-preset")
```

`commit` の引数に `limits: RatioLimits | None` を足し、`notice` の処理の次に:

```python
            if limits is not None and on_ratio_limits is not None and limits != ratio_limits:
                on_ratio_limits(limits)
```

`apply` の `try` に `limits = build_ratio_limits(limit_upper.value or "", limit_lower.value or "") if limit_upper and limit_lower else None` を足し、`pending.update(...)` と `commit(...)`・`confirm_delete` の呼び出しに `limits` を通す(`pending["limits"]`)。`commit` の引数の並びを変えるときは、`commit(` の呼び出し 2 か所(`confirm_delete` と `apply`)を両方直す。import に `RatioLimits`・`MAX_LEVEL_VALUE`・`MIN_LEVEL_VALUE` を足す。

- [ ] **Step 4: `views.py` を実装する**

`open_settings_dialog(...)` の呼び出しに足す:

```python
            ratio_limits=self.project.ratio_limits,
            on_ratio_limits=self.apply_ratio_limits,
```

`apply_plantuml_notice` の次にメソッドを足す(`reassign` から `limit_reviews` を import する):

```python
    def apply_ratio_limits(self, limits: RatioLimits) -> None:
        """相対比率の加算分の上限・下限を変える。実績か進捗のあるタスクの完了予定が変わるときは、見直しを選ばせる。"""
        if limits == self.project.ratio_limits:
            return
        reviews = limit_reviews(self.project, limits, self.holidays, datetime.now())

        def commit(review: bool) -> None:
            if review:
                for task, end in reviews:
                    task.planned_end, task.planned_end_manual = end, True
            self.project.ratio_limit_upper, self.project.ratio_limit_lower = limits.upper, limits.lower
            self.after_edit()

        if not reviews:
            commit(False)
            return
        with ui.dialog() as dialog, ui.card():
            ui.label(
                f"上限・下限の変更で、実績か進捗のある {len(reviews)} 件のタスクの換算率が変わります。\n"
                "残りの作業を新しい条件で見直して、完了予定を手で指定の値にしますか。"
            ).classes("whitespace-pre-line")

            def choose(review: bool) -> None:
                dialog.close()
                commit(review)

            with ui.row():
                ui.button("見直して適用", on_click=lambda: choose(True)).mark("limit-review-apply")
                ui.button("見直さずに適用", on_click=lambda: choose(False)).props("flat").mark("limit-review-skip")
                ui.button("キャンセル", on_click=dialog.close).props("flat").mark("limit-review-cancel")
        dialog.open()
```

見直しの対象タスクは `project.all_tasks()` が返す実体なので、`commit` で書き換えれば `after_edit` が差分を 1 件の履歴にする。`datetime`・`RatioLimits` の import を確認する。

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q && uv run ty check`
Expected: すべて PASS

- [ ] **Step 6: コミットする**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_forms.py test/test_views.py
git commit -m "feat: 設定ダイアログで相対比率の上限・下限を設定できるようにする(要望 73)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 回帰・仕様と記録の更新・全体の確認

**Files:**
- Modify: `CLAUDE.md`(リポジトリ直下の仕様)
- Modify: `docs/development.md`、`docs/requests.md`、`.claude/MEMORY.md`、`docs/superpowers/specs/2026-10-28-ratio-limits-design.md`(状態行)

- [ ] **Step 1: 回帰テストを足す(制限なしで従来と一致)**

`test/test_ratios.py` に追加する。既存の PARAMETERS で、制限なし(`None`・`RatioLimits()`)の `ratio_detail` が、`limits` を渡さない呼び出しと全フィールドで一致することを確かめる:

```python
@pytest.mark.parametrize("levels", [{}, {"経験": "上級"}, {"経験": "初級", "専門": "高"}, {"専門": "低"}])
@pytest.mark.parametrize("only", [None, ["経験"], ["専門"]])
def test_no_limits_gives_the_same_detail_as_before(levels: dict[str, str], only: list[str] | None) -> None:
    member = Member("a", 1.0, levels)
    plain = ratio_detail(member, PARAMETERS, only)
    for limits in (None, RatioLimits(), RatioLimits(None, None)):
        detail = ratio_detail(member, PARAMETERS, only, limits)
        assert (detail.base, detail.adjustments, detail.raw, detail.ratio, detail.clamped) == (
            plain.base, plain.adjustments, plain.raw, plain.ratio, plain.clamped,
        )
        assert detail.limited is False
```

- [ ] **Step 2: 全体のテストと型を通す**

Run: `uv run pytest -q && uv run ty check`
Expected: すべて PASS(テスト数が増えている。失敗があれば原因を直す)

- [ ] **Step 3: 仕様書(`CLAUDE.md`)を更新する**

次の 3 か所を直す(文言は既存の文体に合わせる)。

1. 「`パラメータ`は、プロジェクト共通で…」の項目の末尾に追記する: `加算分(判定値の合計)には、プロジェクトの設定の上限・下限を設けられる(上限は 0〜+290%、下限は -90〜0%。空欄は制限なしで既定。基本比率 100% で +50% なら最大 150%)。制限は、基本比率に足す前の加算分に掛け、基本比率そのものは下げない。そのあとの 10〜300% の丸めは従来どおり。付けたパラメータだけを数えるタスクにも同じ制限が掛かる。換算率の内訳に、制限したときだけ注記を出す(例: 加算分 +150% → 上限 +50% に制限)`
2. 「設定ダイアログで、プロジェクトごとに…」の項目に追記する: `と`相対比率の加算分の上限・下限`(+50% / -50% のプリセットつき。変えると、実績か進捗のあるタスクの換算率が変わる場合は、件数を出して`見直して適用`・`見直さずに適用`・`キャンセル`を選ばせる。見直しは担当の付け替え時と同じ規則で、手で指定の完了予定にする。元に戻す対象)`
3. 「実装上の注意」のプロジェクトファイルの `version` の説明を `現在 13` にし、`12 でプロジェクトの plantuml_overload_notice を足した` のあとに `13 でプロジェクトの ratio_limit_upper・ratio_limit_lower を足した` を足す。3 者マージの項に `ratio_limit_upper`・`ratio_limit_lower` を設定として 1 項目ずつ比べることを足す。

- [ ] **Step 4: 開発者向け・記録を更新する**

- `docs/development.md`: ファイル形式の注意に version 13(`ratio_limit_upper`・`ratio_limit_lower`、キーなしは `null` 相当)と、`ratios.limit_adjustment`・`reassign.limit_reviews` の役割を、既存の version 12 の記述の隣に書く。
- `docs/requests.md`: 要望 73 の状態行を `実装済み(2026-10-28。ブランチ feature/ratio-limits。PR 番号はマージ後に記録。実機確認待ち)。決定: 足しこみのまま加算分に上限・下限(プロジェクトの設定・既定は制限なし)、乗算・平均・逓減は入れない。設計書 docs/superpowers/specs/2026-10-28-ratio-limits-design.md、計画 docs/superpowers/plans/2026-10-28-ratio-limits.md` に直す。
- 設計書の状態行(`> **状態**:`)を `実装済み・実機確認待ち(2026-10-28)— 要望 73 — feature/ratio-limits。現在の仕様は CLAUDE.md に反映済み。` に直す。
- `.claude/MEMORY.md`: 先頭の最終更新と「現在の状況」に、要望 73 の実装(ブランチ・テスト件数・仕様の要点・未確認の実機項目)を 1 段落で足し、「次の作業の候補」から 73 を外して 74 を足す。

- [ ] **Step 5: ドキュメントの変更をコミットする**

```bash
git add CLAUDE.md docs .claude/MEMORY.md test/test_ratios.py
git commit -m "docs: 要望 73 の仕様と記録を更新し、制限なしの回帰テストを足す" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 実機(ネイティブ)で確認してもらう項目を、ユーザーに渡す**

確認項目(実行は `uv run projectapp`):
1. 設定ダイアログ → 相対比率の加算分の制限 → `+50% / -50%` を押して適用。上限を超える組み合わせのタスクの換算率・完了予定が変わる。
2. 実績か進捗のあるタスクがあるとき、確認ダイアログが出て、3 つの選択肢がそれぞれ動く。
3. タスクの編集ダイアログの換算率とメンバー画面の実効比率に、制限の注記が出る。
4. `Cmd+Z` で設定と見直しが一緒に戻る。保存して開き直しても値が残る。
5. 空欄にして適用すると、制限なしに戻る。範囲外(例: 上限 500)でエラーが出る。

実機確認が済むまで、PR とマージはしない。
