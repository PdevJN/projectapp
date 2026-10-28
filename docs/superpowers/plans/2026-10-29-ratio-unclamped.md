# 相対比率の丸めの対象外メンバー Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メンバーごとに`丸めない`を設定でき、その人の相対比率を既定の 50〜150% や設定の上限・下限で丸めず、固定の 10〜300% だけで止める(要望 76)。

**Architecture:** `Member.ratio_unclamped`(既定 False)を足し、`FORMAT_VERSION` を 16 にする。計算は`ratios.ratio_detail`の 1 か所だけを分岐させる(全呼び出し元がここを通る)。画面はメンバー表に列を 1 つ足し、3 者マージと設定の取り込みのメンバー項目に載せる。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)。

**Spec:** [`docs/superpowers/specs/2026-10-29-ratio-unclamped-design.md`](../specs/2026-10-29-ratio-unclamped-design.md)

## Global Constraints

- 丸めを外したメンバーも、固定の安全範囲 `MIN_RATIO`〜`MAX_RATIO`(10〜300%。`models.py`)だけは常に掛ける。変更不可。
- 既定は「丸める」(`ratio_unclamped=False`)。キーのない古いファイル(version 15 以下)は False で読む。
- `FORMAT_VERSION` は 15 → 16。
- 見直し確認は出さない(メンバー表の基本比率の編集と同じ扱い)。
- 画面の文言は日本語。コードの識別子は英語。コメントは周囲に合わせて日本語。
- 作業ブランチは `feature/ratio-unclamped`(作成済み)。

## Review Focus

- 基本 200% で何も選ばない対象外メンバー → 200% のまま(Task 2 のテスト)。
- 判定値の合計で 0 以下や 300% 超になる対象外メンバー → 10% / 300% で止まり、割り算が壊れない(Task 2)。
- 設定の上限・下限を狭めても、対象外メンバーには効かない。対象のメンバーは従来どおり(Task 2)。
- 古い(version 15 以下)ファイルを読むと対象外はなし。version 16 で真偽値以外のキーは読込拒否(Task 1)。
- 上限・下限の変更時の見直し(`limit_reviews`)が、対象外メンバーだけのタスクを対象にしない(Task 2)。
- メンバー表の適用で、チェックが保存され、変更なしの行は未適用扱いにならない(Task 4)。

---

### Task 1: モデル・保存・読込・バージョン

**Files:**
- Modify: `src/projectapp/models.py:15`(バージョン)・`models.py:98-104`(Member)
- Modify: `src/projectapp/storage.py:946-960`(メンバーの読込)
- Modify: `test/test_storage.py:1311, 1379, 1905, 1947, 2112`、`test/test_reference_storage.py:39`、`test/test_summary.py:72`(`15` → `16`)
- Test: `test/test_storage.py`

**Interfaces:**
- Produces: `Member.ratio_unclamped: bool = False`(最後のフィールド。位置引数の既存の呼び出しは壊れない)。`FORMAT_VERSION == 16`。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_storage.py` の末尾に追加)

```python
def test_ratio_unclamped_round_trips() -> None:
    members = [Member("甲", 2.0, id="m1", ratio_unclamped=True), Member("乙", 1.0, id="m2")]
    text = dumps_project(Project("p", members=members))
    raw = json.loads(text)
    assert raw["version"] == 16
    assert [m["ratio_unclamped"] for m in raw["members"]] == [True, False]
    assert [m.ratio_unclamped for m in parse_project(text, "p").members] == [True, False]


def test_a_file_without_the_ratio_unclamped_key_loads_as_clamped() -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", 1.0, id="m1", ratio_unclamped=True)])))
    del raw["members"][0]["ratio_unclamped"]
    assert parse_project(json.dumps(raw), "p").members[0].ratio_unclamped is False


def test_ratio_unclamped_in_a_version_15_file_is_ignored() -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", 1.0, id="m1", ratio_unclamped=True)])))
    raw["version"] = 15
    assert parse_project(json.dumps(raw), "p").members[0].ratio_unclamped is False


@pytest.mark.parametrize("value", [1, "true", None, [True]])
def test_a_non_boolean_ratio_unclamped_is_rejected_on_load(value: object) -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", 1.0, id="m1")])))
    raw["members"][0]["ratio_unclamped"] = value
    with pytest.raises(ValueError, match="丸め"):
        parse_project(json.dumps(raw), "p")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_storage.py -q -k ratio_unclamped`
Expected: FAIL(`Member` に `ratio_unclamped` がない)

- [ ] **Step 3: 実装する**

`models.py` のバージョン行の説明末尾の `15: イベントの休み〔events[].closed〕)` を `15: イベントの休み〔events[].closed〕。16: メンバーの丸め対象外〔members[].ratio_unclamped〕)` にし、`FORMAT_VERSION = 15` を `16` にする。`Member` の最後に足す:

```python
    ratio_unclamped: bool = False  # 真なら、相対比率を 50〜150%(設定の上限・下限)に丸めない(10〜300% の安全範囲だけ守る)
```

`storage.py` のメンバー読込(`work_days = ...` の次の行)に足し、`Member(...)` に渡す。真偽値以外(`1`・`None` を含む)は拒否:

```python
        unclamped = raw.get("ratio_unclamped", False) if ctx.version >= 16 else False
        if not isinstance(unclamped, bool):
            raise ValueError(f"メンバーの丸め対象外の設定が真偽値ではありません: {unclamped!r}")
```
```python
        member = Member(name, ratio, levels, icon=icon, work_days=work_days, ratio_unclamped=unclamped)
```

`_dump` は`asdict(project)`なので書き出しは変更不要。

- [ ] **Step 4: 既存のバージョン固定テストを更新する**

`test/test_storage.py` の 1311・1379・1905・1947・2112 行目、`test/test_reference_storage.py:39`、`test/test_summary.py:72` の `15` を `16` に変える。

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest test/test_storage.py test/test_reference_storage.py test/test_summary.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_storage.py test/test_reference_storage.py test/test_summary.py
git commit -m "feat: メンバーに丸め対象外の設定を足す(version 16)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 計算(`ratios.py`)

**Files:**
- Modify: `src/projectapp/ratios.py:24-80`
- Test: `test/test_ratios.py`

**Interfaces:**
- Consumes: `Member.ratio_unclamped`、`MIN_RATIO`・`MAX_RATIO`(`models`)。
- Produces: `RatioDetail.unclamped: bool`(末尾のフィールド、既定 False)。対象外で安全範囲に掛かったとき `limited=True`・`clamped=True`。`limit_note(detail, limits)` は対象外で掛かったとき、`limits` が None でも注記を返す。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_ratios.py` の末尾に追加。`MIN_RATIO`・`MAX_RATIO` を `projectapp.models` の import に足す。`reassign` の import も足す)

```python
def test_an_unclamped_member_keeps_a_base_ratio_outside_the_default_range() -> None:
    assert effective_ratio(Member("a", 2.0, ratio_unclamped=True), []) == pytest.approx(2.0)
    assert effective_ratio(Member("a", 0.3, ratio_unclamped=True), []) == pytest.approx(0.3)
    assert effective_ratio(Member("a", 2.0), []) == pytest.approx(1.5)  # 対象のメンバーは従来どおり


def test_an_unclamped_member_adds_the_levels_without_the_default_range() -> None:
    member = Member("a", 2.0, {"経験": "上級"}, ratio_unclamped=True)
    detail = ratio_detail(member, PARAMETERS)
    assert detail.raw == pytest.approx(2.2) and detail.ratio == pytest.approx(2.2)
    assert detail.unclamped is True and detail.clamped is False and detail.limited is False


def test_the_limits_do_not_apply_to_an_unclamped_member() -> None:
    limits = RatioLimits(upper=1.2, lower=0.8)
    assert effective_ratio(Member("a", 2.0, ratio_unclamped=True), [], limits=limits) == pytest.approx(2.0)
    assert effective_ratio(Member("a", 2.0), [], limits=limits) == pytest.approx(1.2)


def test_an_unclamped_member_is_still_held_to_the_safe_range() -> None:
    low = ratio_detail(Member("a", 1.0, {"大": "低"}, ratio_unclamped=True), [Parameter("大", [Level("低", -2.5)])])
    assert low.raw == pytest.approx(-1.5) and low.ratio == pytest.approx(MIN_RATIO)  # 0 以下で割り算が壊れない
    assert low.clamped is True and low.limited is True
    high = ratio_detail(Member("a", 2.5, {"大": "高"}, ratio_unclamped=True), [Parameter("大", [Level("高", 1.0)])])
    assert high.raw == pytest.approx(3.5) and high.ratio == pytest.approx(MAX_RATIO)
    assert high.limited is True


def test_a_ratio_exactly_on_the_safe_range_is_not_limited() -> None:
    detail = ratio_detail(Member("a", 3.0, ratio_unclamped=True), [])
    assert detail.ratio == pytest.approx(3.0) and detail.limited is False and detail.clamped is False


def test_limit_note_for_an_unclamped_member_names_the_safe_range_even_without_limits() -> None:
    upper = ratio_detail(Member("a", 2.5, {"大": "高"}, ratio_unclamped=True), [Parameter("大", [Level("高", 1.0)])])
    assert limit_note(upper, None) == "相対比率 350% → 安全範囲の上限 300% に制限"
    lower = ratio_detail(Member("a", 1.0, {"大": "低"}, ratio_unclamped=True), [Parameter("大", [Level("低", -0.95)])])
    assert limit_note(lower, RatioLimits(lower=0.8)) == "相対比率 5% → 安全範囲の下限 10% に制限"
    inside = ratio_detail(Member("a", 2.0, ratio_unclamped=True), [])
    assert limit_note(inside, None) == ""


def test_limit_reviews_ignore_a_task_whose_crew_is_unclamped() -> None:
    from datetime import datetime

    from projectapp.models import Assignee
    from projectapp.reassign import limit_reviews

    task = Task("x", assignees=[Assignee("a", 1.0)], effort=8.0, actual=[])
    for unclamped, expected in ((True, 0), (False, 1)):
        project = Project("p", members=[Member("a", 2.0, ratio_unclamped=unclamped)], tasks=[task])
        reviews = limit_reviews(project, RatioLimits(upper=1.2), {}, datetime(2026, 10, 29, 9, 0))
        assert len(reviews) == expected
```

(`limit_reviews` の戻り値の形と、`Task` の実績・進捗度の条件は、実装前に `src/projectapp/reassign.py:56-90` と `test/test_reassign.py` の既存テストを読み、見直し対象になるタスク〔工数あり・進捗度または実績あり・未終了〕を同じ作り方で組む。`expected` が 1 になるのは、対象のメンバーの換算率が 1.5 → 1.2 に変わるため。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_ratios.py -q`
Expected: FAIL(`Member` は通るが `unclamped` 属性・分岐がない)

- [ ] **Step 3: 実装する**

`ratios.py`: import に `MAX_RATIO`・`MIN_RATIO` を足す。`RatioDetail` の末尾に足す:

```python
    unclamped: bool = False  # 丸め対象外のメンバー(安全範囲 10〜300% だけで収めた)
```

`ratio_detail` の `lower`/`upper`〜`return` を置き換える:

```python
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
```

`limit_note` の先頭を置き換える(docstring に対象外の注記を足す):

```python
    if detail.unclamped:
        if not detail.limited:
            return ""
        edge = "上限 300%" if detail.raw > detail.ratio else "下限 10%"
        return f"相対比率 {detail.raw * 100:g}% → 安全範囲の{edge} に制限"
    if limits is None or not detail.limited:
        return ""
```

`ratio_detail` の docstring に「`member.ratio_unclamped` なら 10〜300% だけで収める」を 1 行足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_ratios.py test/test_reassign.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/ratios.py test/test_ratios.py
git commit -m "feat: 丸め対象外のメンバーの相対比率を安全範囲だけで収める

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 3 者マージと設定の取り込み

**Files:**
- Modify: `src/projectapp/merge.py:180, 190-192, 433-434`
- Modify: `src/projectapp/settings_io.py:187-188`
- Test: `test/test_merge.py`、`test/test_settings_io.py`

**Interfaces:**
- Consumes: `Member.ratio_unclamped`。
- Produces: マージのメンバー項目`ratio_unclamped`(表示名`丸め対象外`)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_merge.py`(末尾):

```python
def test_a_member_ratio_unclamped_changed_on_one_side_is_taken() -> None:
    base = proj(members=[Member("甲", 2.0, id="m1")])
    ours = proj(members=[Member("甲", 2.0, id="m1", ratio_unclamped=True)])
    result = merge_projects(base, ours, base)
    assert result.conflicts == [] and result.project.members[0].ratio_unclamped is True


def test_a_member_ratio_unclamped_changed_to_different_values_on_both_sides_conflicts() -> None:
    base = proj(members=[Member("甲", 2.0, id="m1")])
    ours = proj(members=[Member("甲", 2.0, id="m1", ratio_unclamped=True)])
    theirs = proj(members=[Member("甲", 2.0, id="m1", ratio_unclamped=False, ratio=1.0)])
    # ratio だけ相手が変えた: 衝突しない。丸め対象外は自分の変更を採る
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == [] and result.project.members[0].ratio_unclamped is True
```

`test/test_settings_io.py`(`test_apply_overwrites_...` の次):

```python
def test_apply_overwrite_also_replaces_ratio_unclamped() -> None:
    current = Project("現", members=[Member("田中", 1.0)])
    source = Project("入", members=[Member("田中", 2.0, ratio_unclamped=True)])
    result = apply_import(current, incoming_of(source), {"members"}, {("members", "田中")})
    assert result.project.members[0].ratio_unclamped is True
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_merge.py test/test_settings_io.py -q -k unclamped`
Expected: FAIL(マージが`ratio_unclamped`を落とす)

- [ ] **Step 3: 実装する**

`merge.py`: `MEMBER_LABELS` に `"ratio_unclamped": "丸め対象外"` を足す。`_members` の辞書に `"ratio_unclamped": m.ratio_unclamped` を足す(`"icon": m.icon,` の次)。再構築を:

```python
    built_members = [
        Member(r["name"], r["ratio"], dict(r["levels"]), id=key, icon=r["icon"], ratio_unclamped=r["ratio_unclamped"])
        for key, r in members.items()
    ]
```

`settings_io.py` の `_overwrite`:

```python
        target.ratio, target.levels, target.icon, target.work_days = item.ratio, item.levels, item.icon, item.work_days
        target.ratio_unclamped = item.ratio_unclamped
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_merge.py test/test_settings_io.py -q`
Expected: PASS(設定の書き出しは `storage` の関数でメンバーを変換しているので、往復のテストも通ることを確認する。落ちたら `settings_io.py` のメンバー変換に`ratio_unclamped`を足す)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/merge.py src/projectapp/settings_io.py test/test_merge.py test/test_settings_io.py
git commit -m "feat: 丸め対象外を3者マージと設定の取り込みに載せる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: メンバー表の画面と換算率の内訳

**Files:**
- Modify: `src/projectapp/forms.py`(`MemberRow` 885・`build_members` 928・`effective_ratio_text` 1856・`to_rows` 1963・表 1995 付近・`member_columns` 1895・`member_table_min_rem` 1911・定数 1876・説明文 1750・行の追加 2104)
- Modify: `src/projectapp/task_dialog.py:1046-1054`(`limit_notes`)
- Modify: `test/test_forms.py:2143`、`test/test_views.py:4211-4212`
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `Member.ratio_unclamped`、`RatioDetail.unclamped`、`limit_note`。
- Produces: `MemberRow.ratio_unclamped: bool = False`(`work_days` の次の最後のフィールド)。メンバー表の新しい列(チェック。mark `member-unclamped-{index}`、見出し mark `member-header-unclamped`)。定数 `MEMBER_UNCLAMPED_COLUMN_REM = 5`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py`(`test_effective_ratio_text` の近く):

```python
def test_build_members_carries_ratio_unclamped() -> None:
    rows = [MemberRow(None, "田中", 200.0, ratio_unclamped=True), MemberRow(None, "鈴木", 100.0)]
    members, _ = build_members(rows, [], lambda _: 0)
    assert [m.ratio_unclamped for m in members] == [True, False]


def test_effective_ratio_text_for_an_unclamped_member() -> None:
    row = MemberRow(None, "a", 200.0, ratio_unclamped=True)
    assert effective_ratio_text(row, [EXPERIENCE]) == "相対比率 200%(丸め対象外)"
    over = MemberRow(None, "a", 290.0, {"経験": "上級"}, ratio_unclamped=True)
    assert effective_ratio_text(over, [EXPERIENCE]) == "相対比率 300%(丸め対象外・相対比率 310% → 安全範囲の上限 300% に制限)"
    assert effective_ratio_text(MemberRow(None, "a", 200.0), [EXPERIENCE]) == "相対比率 150%(範囲に丸めました)"
```

`test/test_forms.py:2143` の列数テストを更新:

```python
    assert len(member_columns(0, False)) == 6  # アイコン・名前・比率・丸めない・稼働日・削除
```

`test/test_views.py`(既存の `test_applying_parameters_rebuilds_the_member_columns_and_keeps_unapplied_member_edits` の近く。メンバーダイアログを開いて適用する既存テストの作り方を読み、同じ流儀で書く):

```python
async def test_member_dialog_applies_ratio_unclamped(...)  # 既存のメンバーダイアログのテストと同じ fixture・開き方
    # member-unclamped-0 をオンにして適用 → project.members[0].ratio_unclamped is True、
    # 変更なしで適用した行は ratio_unclamped が変わらず、未適用の印(●)も出ない
```

(fixture 名・クリックのヘルパーは周囲のテストに合わせる。上の 2 つの確認を実際の assert にして書くこと。)

`test/test_views.py:4211-4212` の期待値を更新(列が 1 つ増え、列の間隔の概算が `2 * (6 + n + eff)` になる):

```python
    assert member_table_min_rem(0, False) == 6 + 7 + 7 + 5 + 7 + 3 + 2 * 6
    assert member_table_min_rem(2, True) == 6 + 7 + 7 + 5 + 9 * 2 + 11 + 7 + 3 + 2 * 9
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -k "unclamped or member_columns or min_rem"`
Expected: FAIL

- [ ] **Step 3: `forms.py` を実装する**

- 定数 `MEMBER_RATIO_COLUMN_REM = 7` の次に `MEMBER_UNCLAMPED_COLUMN_REM = 5  # 丸めないのチェックの列`。
- `MemberRow` の最後に `ratio_unclamped: bool = False  # 丸めない(相対比率を 50〜150% に丸めない)`。
- `build_members`: `Member(name, round(ratio / 100, 4), levels, member_id, row.icon, work_days, row.ratio_unclamped)`。
- `to_rows`: `MemberRow(m.name, m.name, round(m.ratio * 100, 2), dict(m.levels), m.id, m.icon, work_day_rows(m), m.ratio_unclamped)`。
- `member_columns`: 比率の次に `f"{MEMBER_UNCLAMPED_COLUMN_REM}rem"` を足す(docstring の列の並びも「…・基本比率・丸めない・…」に)。
- `member_table_min_rem`: `+ MEMBER_UNCLAMPED_COLUMN_REM` を足し、間隔の概算を `2 * (6 + level_count + (1 if with_effective else 0))` にする。
- `effective_ratio_text`: `Member(row.name, percent / 100, row.levels, ratio_unclamped=row.ratio_unclamped)` にし、注記を組み直す:

```python
    notes = ["丸め対象外"] if detail.unclamped else []
    if detail.clamped and not detail.limited:
        notes.append("範囲に丸めました")  # 制限したときは、その注記だけ
    if note := limit_note(detail, limits):
        notes.append(note)
```
  (`detail.unclamped` のときは `clamped and not limited` にならないので、順序・文言は上のテストどおり。)
- 表: 見出しの比率の次に `ui.label("丸めない").classes(header).mark("member-header-unclamped")`。各行の比率の `ui.number(...)` の次に:

```python
                    def on_unclamped(e, r=row) -> None:  # noqa: ANN001
                        r.ratio_unclamped = bool(e.value)
                        refresh_effective(r)

                    ui.checkbox(value=row.ratio_unclamped, on_change=on_unclamped).props(
                        "dense aria-label=丸めない"
                    ).tooltip(
                        "50〜150%(設定の上限・下限)に丸めず、基本比率 + 判定値をそのまま使います。"
                        "10〜300% は常に守ります"
                    ).mark(f"member-unclamped-{index}")
```
  (`on_unclamped` は `refresh_effective` より後に定義する。`effective` ラベルは`with_effective`のときだけ作られ、`refresh_effective` が空を許す。)
- パラメータタブの説明文(1750 付近)を `…に丸めます(メンバーの「丸めない」を除く))` にする。文言を assert している既存テストがあれば合わせる。
- 行の追加(2104)は `MemberRow(None, "", 100.0)` のまま(既定 False)。

- [ ] **Step 4: `task_dialog.py` の `limit_notes` を実装する**

```python
                    detail = ratio_detail(by_name[name], parameters or [], chosen_parameters, ratio_limits)
                    note = limit_note(detail, ratio_limits)
                    if detail.unclamped:
                        note = f"丸め対象外・{note}" if note else "丸め対象外"
                    if note:
                        notes.append(f"{name} {note}")
```

- [ ] **Step 5: 通ることを確認する(全体)**

Run: `uv run pytest -q`
Expected: PASS(落ちた場合は、列数・文言を固定している既存テストだけを新しい仕様に合わせて直し、それ以外は実装を疑う)

Run: `uv run ty check`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py test/test_forms.py test/test_views.py
git commit -m "feat: メンバー表に丸めないの列を足し、内訳に対象外を示す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ドキュメント

**Files:**
- Modify: `CLAUDE.md`(`projectapp/CLAUDE.md`。メンバー・相対比率・バージョンの行)
- Modify: `docs/development.md`(`ratios.py` の行・151 行目付近に version 16 の項を追記)
- Modify: `docs/requests.md`(要望 76 の状態)
- Modify: `docs/superpowers/specs/2026-10-29-ratio-unclamped-design.md`(状態を実装済みに)

- [ ] **Step 1: `CLAUDE.md` を更新する**
  - 「ファイルの先頭の`version`」の記述を `現在 16`、`15 でイベントの closed を足した` の後に `16 でメンバーの`ratio_unclamped`〔丸め対象外〕を足した` を追記。
  - 「`メンバー`（担当者）は…」の行の末尾(`基本比率の入力・読込の範囲は 10〜300% のまま）` の後)に追記: `メンバーごとの`丸めない`(`メンバーとパラメータ`のメンバーの表のチェック)をオンにすると、その人の相対比率は既定の 50〜150% や設定の上限・下限で丸めず、`基本比率 + 判定値の合計`を使う(固定の 10〜300% だけは常に守り、掛かったときは注記を出す)`。

- [ ] **Step 2: `docs/development.md` を更新する**
  - `ratios.py` の行に「`Member.ratio_unclamped` なら 10〜300%(`MIN_RATIO`〜`MAX_RATIO`)だけで収める。`RatioDetail.unclamped`」を足す。
  - 151 行目の相対比率の項の次に、version 16 の項を足す(読込は version 16 以上でだけ読み、真偽値以外を拒否、3 者マージ・設定の取り込みはメンバーの項目として扱う、見直し確認は出さない)。

- [ ] **Step 3: `docs/requests.md` の要望 76 を更新する**
  - 状態を `実装済み(実機確認前。2026-10-29。[設計書](superpowers/specs/2026-10-29-ratio-unclamped-design.md)・[計画](superpowers/plans/2026-10-29-ratio-unclamped.md))` にし、「決めたい点(未決)」を「決めたこと」に直す(メンバーごと・丸めを一切掛けない・10〜300% の安全範囲・見直し確認なし)。
  - spec の状態行も `実装済み(2026-10-29)` にする。

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs
git commit -m "docs: 要望 76(丸め対象外のメンバー)の実装を記録する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage**: データ・ファイル(Task 1)、計算・注記(Task 2)、画面の列・内訳(Task 4)、3 者マージ・設定の取り込み・元に戻す(メンバー編集で自動。Task 3/4)、`limit_reviews` が追従すること(Task 2 のテスト)、ドキュメント(Task 5)。範囲外(個別の上限・下限、切り替え時の見直し確認)は入れていない。
- **型の一貫性**: `ratio_unclamped`(Member・MemberRow・マージの辞書キー)、`RatioDetail.unclamped`、`MEMBER_UNCLAMPED_COLUMN_REM`、mark の名前を全タスクで統一した。
- **実機確認が必要**: メンバー表の列幅(チェックと見出し`丸めない`が 5rem に収まるか)、ツールチップの表示。ネイティブウィンドウで確認する。
