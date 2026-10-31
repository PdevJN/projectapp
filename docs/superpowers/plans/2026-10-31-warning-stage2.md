# 警告の状態 段階 2(ダッシュボード・メンバーの閾値)実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 警告のタスクを、ダッシュボードの `進捗と遅れ`(全体・メンバー別・チーム別の件数)と `期限とマイルストーン`(行の印)に出し、メンバーごとの警告の件数の閾値(`warning_limit`)で、抱えすぎのメンバーを強調する。あわせて、プロジェクト参照行の名前の欄に `警告 n件` のチップを出す。

**Architecture:** 段階 1 の `pace.warning_pace` を、ダッシュボードの集計(`dashboard.py`)から呼ぶ。件数は、集計の対象の各 `Entry`(参照先のタスクを含む)で 1 回ずつ判定して `id(task)` の集合にし、全体・メンバー別・チーム別の行が同じ集合から数える。`Member` に整数の `warning_limit`(1〜999 または `None`)を足し、ファイル形式を version 19 に上げる(`ratio_unclamped` を足した version 16 と同じ経路: モデル・読込・3 者マージ・設定のインポート・メンバーの表)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、`ty`

**Spec:** [`docs/superpowers/specs/2026-10-31-warning-status-design.md`](../specs/2026-10-31-warning-status-design.md)(要望 103 の段階 2。段階 1: `2026-10-31-warning-stage1.md` はマージ済み。段階 3: 要望 98 のボタンは続く)

## Global Constraints

- 警告の判定は段階 1 の `pace.warning_pace` をそのまま使う(110% 以上、予定超過・終了・まとめ・節目・参照行・工数なしは警告にしない)。ここで判定を変えない。
- 件数は、`進捗と遅れ` の他の件数と同じ数え方。共同タスクは担当者それぞれの行に 1 件ずつ、担当がメンバーでないタスク・担当なしは `未割り当て` 行に数える。期間には影響されない。メンバー・チームの絞り込みに従う(共同タスクは丸ごと)。
- 参照行の参照先の通常タスクも、開いているプロジェクトのタスクと同列に数える。判定は、参照先自身の稼働設定・祝日・イベントで行う(`Entry.project`・`Entry.schedule` を使う)。
- 強調するのはメンバー別の行だけ。そのメンバーの閾値(`warning_limit`)があり、警告の件数が閾値以上のとき。閾値がないメンバー、チーム別、`未割り当て` の行は強調しない。
- `warning_limit` は整数 1〜999 または `null`。`bool`・小数・範囲外・文字列は読込を拒否する。キーのない古いファイルは `null`。`FORMAT_VERSION` は 18 → 19。
- 警告の色は `var(--warning)`(段階 1)。強調はアイコンと太字で示し、文字そのものを黄色にしない(白地で読めないため)。
- 集計は保存しない。ダッシュボードのビューには入れない。ただし参照行のスナップショット(`ReferenceValue`)は保存する値なので、`warned`(警告のタスクの数)を足す。キーのない古いスナップショットは 0 で読む。`same_as` は `warned` も比べる(古いスナップショットは、警告があれば「古い」と判定され、`更新して続ける` などの確認が出る。許容する)。
- 参照行の `警告 n件` は、遅延のチップと同じ表示項目(予定超過の赤みと割り当て超過の縞)に従う。PlantUML には出さない。帯は赤のまま変えない。
- 画面の文言に「要望 N」は書かない。コメントには書いてよい。
- 実装のたびに `uv run pytest -m smoke`。PR の前は `uv run pytest -n auto` と `uv run ty check src`(診断は変更前と同じ 1 件)。

## Review Focus

- 共同タスクが担当者それぞれの行に 1 件ずつ数えられ、全体の `警告 n` は 1 件のままであること(行の合計と全体が一致しないのは仕様。テストで明示する)。
- 参照先のタスクの警告が、参照先自身の稼働設定で判定されること(開いているプロジェクトの設定で判定しない)。
- 古いファイル(version 18 以下)で `warning_limit` が `None` になり、保存し直すと version 19 で書かれること。不正値(`true`・`1.5`・`0`・`1000`・`"3"`)で読込が拒否されること。
- メンバーの表で、閾値を空にして適用すると `None` に戻ること。`0`・負・小数・1000 以上は適用できないこと。
- 3 者マージで、片側だけ閾値を変えたときは取り込まれ、両側が別の値に変えたときだけ衝突になること。
- 閾値ちょうど(件数 = 閾値)で強調され、閾値 − 1 では強調されないこと。
- 参照行のチップが、`常に最新` では参照先自身の設定で数えた件数、`スナップショット` では保存した件数を出すこと。0 件では出さないこと。古いスナップショット(`warned` のキーなし)が 0 で読め、不正値は拒否されること。

## ファイル構成

| ファイル | 内容 |
|---|---|
| `src/projectapp/models.py` | `Member.warning_limit`、`FORMAT_VERSION = 19`、定数 `MIN_WARNING_LIMIT`・`MAX_WARNING_LIMIT` |
| `src/projectapp/storage.py` | `_warning_limit`(読込の検証)、`_members` で読む |
| `src/projectapp/merge.py` | `MEMBER_LABELS`・`_members`・メンバーの組み立て |
| `src/projectapp/settings_io.py` | `_overwrite` に `warning_limit` |
| `src/projectapp/forms.py` | `MemberRow.warning_limit`・`build_members` の検証・メンバーの表の列 |
| `src/projectapp/dashboard.py` | `warning_tasks`、`Progress.warnings`、`MemberProgress.warnings`・`limit`、`DueRow.warning` |
| `src/projectapp/dashboard_view.py` | `警告 n` の表示、メンバー行の強調、期限の行の印 |
| `src/projectapp/models.py`・`reference.py`・`storage.py`・`gantt.py` | 参照行: `ReferenceValue.warned`・`compute_reference`・スナップショットの読込・`警告 n件` のチップと帯のホバー(Task 6) |
| `test/test_reference.py`・`test_reference_storage.py`・`test_gantt.py` | 参照行(Task 6) |
| `test/test_storage.py`・`test_merge.py`・`test_settings_io.py`・`test_forms.py`・`test_dashboard.py`・`test_dashboard_view.py`・`test_summary.py`・`test_reference_storage.py` | テスト |
| `CLAUDE.md`・`docs/development.md`・`docs/work-log.md`・`docs/requests.md`・`docs/request-history.md` | 仕様と記録 |

---

### Task 1: `Member.warning_limit` と version 19(モデル・読込)

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION`、`Member`)
- Modify: `src/projectapp/storage.py`(`_members` の近く)
- Modify: `test/test_summary.py:72`・`test/test_reference_storage.py:39`(`FORMAT_VERSION == 18` → `19`)
- Test: `test/test_storage.py`

**Interfaces:**
- Produces:
  - `models.MIN_WARNING_LIMIT = 1`、`models.MAX_WARNING_LIMIT = 999`
  - `Member.warning_limit: int | None = None`(`teams` の後ろ。位置引数の既存の呼び出しを壊さない)
  - `storage._warning_limit(value: Any) -> int | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の末尾に足す(ファイルの先頭で `dumps_project`・`loads_project` などの読み書きの関数名を確認し、既存の `ratio_unclamped` のテストと同じ関数を使う。下のコードは名前が `dumps_project` / `loads_project` / `load_project_text` のどれかを確かめて合わせる):

```python
def member_json(**extra: object) -> str:
    base = {"version": 19, "name": "p", "members": [{"name": "田中", "ratio": 1.0, "id": "m1", **extra}]}
    return json.dumps(base, ensure_ascii=False)


def test_the_warning_limit_round_trips_and_defaults_to_none() -> None:
    project = Project("p", members=[Member("田中", 1.0, warning_limit=3), Member("鈴木", 1.0)])
    again = loads_project(dumps_project(project))
    assert [m.warning_limit for m in again.members] == [3, None]
    assert json.loads(dumps_project(project))["version"] == 19


@pytest.mark.parametrize("version", [1, 8, 16, 18])
def test_an_older_file_reads_the_warning_limit_as_none(version: int) -> None:
    text = json.dumps({"version": version, "name": "p", "members": [{"name": "田中", "ratio": 1.0, "id": "m1"}]})
    assert loads_project(text).members[0].warning_limit is None


@pytest.mark.parametrize("bad", [True, 0, -1, 1000, 1.5, "3", [], {}])
def test_an_invalid_warning_limit_is_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="警告の件数"):
        loads_project(member_json(warning_limit=bad))


@pytest.mark.parametrize("good", [1, 3, 999, None])
def test_a_valid_warning_limit_is_read(good: int | None) -> None:
    assert loads_project(member_json(warning_limit=good)).members[0].warning_limit == good
```

`test/test_summary.py:72` と `test/test_reference_storage.py:39` の `assert FORMAT_VERSION == 18` を `19` に直す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_storage.py test/test_summary.py test/test_reference_storage.py -q -n 0 -k "warning_limit or FORMAT or format_version"`
Expected: FAIL(`TypeError: Member.__init__() got an unexpected keyword argument 'warning_limit'`、`FORMAT_VERSION == 19` の失敗)

- [ ] **Step 3: 実装する**

`models.py`: `FORMAT_VERSION = 18  # ...` を 19 に上げ、コメントの末尾の `18:` の説明の後ろに `。19: メンバーの警告の件数の閾値 warning_limit` を足す(長い 1 行コメントなので、末尾に追記するだけにする)。`Member` の `teams` の次の行に:

```python
    warning_limit: int | None = None  # 警告のタスクの件数がこの数以上のとき、ダッシュボードで強調する(1〜999。None は強調しない)
```

`Member` の定義の前に:

```python
MIN_WARNING_LIMIT = 1
MAX_WARNING_LIMIT = 999
```

`storage.py`: 先頭の `from projectapp.models import (...)` に `MAX_WARNING_LIMIT`・`MIN_WARNING_LIMIT` を足す。`_icon` の定義の近くに:

```python
def _warning_limit(value: Any) -> int | None:
    """メンバーの警告の件数の閾値。null・キーなしは閾値なし。整数(boolは不可)で 1〜999。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"メンバーの警告の件数が整数ではありません: {value!r}")
    if not MIN_WARNING_LIMIT <= value <= MAX_WARNING_LIMIT:
        raise ValueError(f"メンバーの警告の件数は{MIN_WARNING_LIMIT}〜{MAX_WARNING_LIMIT}で指定してください: {value}")
    return value
```

`_members` の `teams = _memberships(...)` の次の行に `warning_limit = _warning_limit(raw.get("warning_limit")) if ctx.version >= 19 else None`、`member = Member(...)` の引数に `warning_limit=warning_limit` を足す。書き込みは `asdict(project)` なので変更不要(`save_project` が `members` を `asdict` で書く行〔`storage.py:124` 付近〕に `warning_limit` が含まれることをテストで確かめる)。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_storage.py test/test_summary.py test/test_reference_storage.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_storage.py test/test_summary.py test/test_reference_storage.py
git commit -m "feat: メンバーに警告の件数の閾値(warning_limit)を足す(version 19)"
```

---

### Task 2: 3 者マージ・設定のインポート・子プロジェクトへの引き継ぎ

**Files:**
- Modify: `src/projectapp/merge.py`(`MEMBER_LABELS`・`_members`・メンバーの組み立て〔`built_members`〕)
- Modify: `src/projectapp/settings_io.py`(`_overwrite`)
- Test: `test/test_merge.py`・`test/test_settings_io.py`・`test/test_extract.py`

**Interfaces:**
- Consumes: `Member.warning_limit`(Task 1)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_merge.py` の `test_ratio_unclamped_and_ratio_changed_on_different_sides_merge_without_conflict` の後に、同じ組み立て(`proj`・`merge_projects` 相当の呼び出し)で足す。既存の `ratio_unclamped` のテスト(`test_merge.py:617-630`)をそのまま写して、`ratio_unclamped=True` を `warning_limit=3` に、`.ratio_unclamped is True` を `.warning_limit == 3` に直す:

```python
def test_a_member_warning_limit_changed_on_one_side_is_taken() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[Member("甲", 1.0, id="m1", warning_limit=3)])
    theirs = proj(members=[Member("甲", 1.0, id="m1")])
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == [] and result.project.members[0].warning_limit == 3


def test_a_warning_limit_changed_to_different_values_on_both_sides_conflicts() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[Member("甲", 1.0, id="m1", warning_limit=3)])
    theirs = proj(members=[Member("甲", 1.0, id="m1", warning_limit=5)])
    result = merge_projects(base, ours, theirs)
    assert [c.label for c in result.conflicts if "警告" in c.label]
```

(`merge_projects` と `proj` と衝突のラベルの取り方は、`test_merge.py:617` の隣のテストに合わせて直す。)

`test/test_settings_io.py` の `test_settings_file_round_trips_ratio_unclamped` の後に:

```python
def test_apply_overwrite_also_replaces_warning_limit() -> None:
    work = Project("現", members=[Member("田中", 1.0, warning_limit=2)])
    source = Project("入", members=[Member("田中", 1.0, warning_limit=7)])
    result = <既存の ratio_unclamped の上書きテストと同じ呼び出し>(work, source, ...)
    assert result.project.members[0].warning_limit == 7


def test_settings_file_round_trips_warning_limit() -> None:
    incoming = incoming_of(Project("p", members=[Member("田中", 1.0, warning_limit=4)]))
    assert incoming.project.members[0].warning_limit == 4
```

(上書きの呼び出しは `test_apply_overwrite_also_replaces_ratio_unclamped`〔`test_settings_io.py:291`〕の行をそのまま写す。)

`test/test_extract.py` の末尾に、既存のメンバー引き継ぎのテストの形で:

```python
def test_extract_keeps_the_warning_limit_of_the_members_who_move() -> None:
    <既存のテストと同じ組み立て: 担当者「田中」を持つタスクを切り出す>
    assert child.members[0].warning_limit == 3
```

(`extract.py` は `deepcopy(member)` なので、`Member("田中", 1.0, warning_limit=3)` を持つ親から切り出すだけで通る。既存の切り出しのテストのヘルパーを使う。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_merge.py test/test_settings_io.py test/test_extract.py -q -n 0 -k warning_limit`
Expected: merge・settings_io の 3 件が FAIL(extract は通る場合がある。通るなら「`deepcopy` で既に通る」ことの確認として残す)

- [ ] **Step 3: 実装する**

`merge.py`:
- `MEMBER_LABELS` に `"warning_limit": "警告の件数"` を足す。
- `_members` の辞書に `"warning_limit": m.warning_limit,` を足す。
- 組み立て(`built_members` の `Member(...)`)に `warning_limit=r["warning_limit"],` を足す。

`settings_io.py` の `_overwrite`: `target.ratio_unclamped = item.ratio_unclamped` の次の行に `target.warning_limit = item.warning_limit`。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_merge.py test/test_settings_io.py test/test_extract.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/merge.py src/projectapp/settings_io.py test/test_merge.py test/test_settings_io.py test/test_extract.py
git commit -m "feat: 警告の件数の閾値を、3 者マージと設定のインポートの対象にする"
```

---

### Task 3: メンバーの表に `警告の件数` の列

**Files:**
- Modify: `src/projectapp/forms.py`(`MemberRow`・`build_members`・列の幅・`to_rows`・表)
- Test: `test/test_forms.py`・`test/test_views.py`

**Interfaces:**
- Consumes: `Member.warning_limit`・`MIN_WARNING_LIMIT`・`MAX_WARNING_LIMIT`(Task 1)
- Produces:
  - `MemberRow.warning_limit: float | None = None`(`teams` の後ろ。入力欄は数値なので float)
  - `build_members` が `warning_limit` を検証して `int | None` で `Member` に入れる
  - `MEMBER_WARNING_COLUMN_REM = 6`、列は `丸めない` の次(マーカー: 見出し `member-header-warning-limit`、入力 `member-warning-limit-{index}`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の `test_build_members_carries_ratio_unclamped` の後に:

```python
def test_build_members_carries_the_warning_limit_as_an_int() -> None:
    rows = [MemberRow(None, "田中", 100.0, warning_limit=3.0), MemberRow(None, "鈴木", 100.0)]
    members, _ = build_members(rows, [], lambda name: 0)
    assert [m.warning_limit for m in members] == [3, None]
    assert isinstance(members[0].warning_limit, int)


@pytest.mark.parametrize("bad", [0.0, -1.0, 1000.0, 1.5, float("nan"), float("inf")])
def test_build_members_rejects_a_bad_warning_limit(bad: float) -> None:
    with pytest.raises(ValueError, match="警告の件数は1〜999の整数"):
        build_members([MemberRow(None, "田中", 100.0, warning_limit=bad)], [], lambda name: 0)


@pytest.mark.parametrize("good", [1.0, 999.0])
def test_build_members_accepts_the_edges_of_the_warning_limit(good: float) -> None:
    members, _ = build_members([MemberRow(None, "田中", 100.0, warning_limit=good)], [], lambda name: 0)
    assert members[0].warning_limit == int(good)
```

(`build_members` の第 2・3 引数は、`test_build_members_carries_ratio_unclamped`〔`test_forms.py:1440`〕と同じにする。)

既存の列の数のテストを直す: `test_member_columns_include_the_work_days_column`(`test_forms.py:2200`)の `== 6` を `== 7`(アイコン・名前・比率・丸めない・警告の件数・稼働日・削除)に、コメントも合わせる。

`test/test_views.py` に、メンバーの表の既存のテスト(`member-unclamped-` を操作しているもの。`grep -n "member-unclamped" test/test_views.py` で探す)と同じ組み立てで:

```python
async def test_the_member_table_edits_the_warning_limit(user: User, tmp_path: Path) -> None:
    <メンバーのダイアログを開く既存の手順>
    await user.should_see(marker="member-header-warning-limit")
    user.find(marker="member-warning-limit-0").elements.pop().set_value(3)
    <適用する既存の手順>
    assert <現在のプロジェクト>.members[0].warning_limit == 3
    user.find(marker="member-warning-limit-0").elements.pop().set_value(None)
    <適用する既存の手順>
    assert <現在のプロジェクト>.members[0].warning_limit is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -n 0 -k "warning_limit or work_days_column"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`forms.py`:
1. `from projectapp.models import (...)` に `MAX_WARNING_LIMIT`・`MIN_WARNING_LIMIT` を足す。
2. `MemberRow` の `teams` の次に `warning_limit: float | None = None  # 警告の件数の閾値(1〜999 の整数。空は閾値なし)`。
3. `build_members` の、`team_error` の検査の後ろに:

```python
        limit = row.warning_limit
        if limit is not None and not (
            isfinite(limit) and limit == int(limit) and MIN_WARNING_LIMIT <= limit <= MAX_WARNING_LIMIT
        ):
            raise ValueError(f"{name}: 警告の件数は{MIN_WARNING_LIMIT}〜{MAX_WARNING_LIMIT}の整数で入力してください")
```

   `Member(...)` の呼び出しの引数の最後に `warning_limit=None if limit is None else int(limit)` を足す(位置引数の並びは変えない)。
4. `to_rows`(`forms.py:2015` 付近)の `MemberRow(...)` の最後の引数に `m.warning_limit` を足す。
5. 列: `MEMBER_UNCLAMPED_COLUMN_REM = 5` の次に `MEMBER_WARNING_COLUMN_REM = 6  # 警告の件数の列`。`member_columns` の `MEMBER_UNCLAMPED_COLUMN_REM` の行の次に `f"{MEMBER_WARNING_COLUMN_REM}rem",` を足し、docstring に `警告の件数` を足す。`member_table_min_rem` の合計に `+ MEMBER_WARNING_COLUMN_REM` を足し、列の間隔の概算の `6 + level_count` を `7 + level_count` にする。
6. 見出し: `ui.label("丸めない")...mark("member-header-unclamped")` の次に `ui.label("警告の件数").classes(header).mark("member-header-warning-limit")`。
7. 行: `member-unclamped-{index}` の `ui.checkbox(...)` の直後(パラメータの `for p, parameter in ...` の前)に:

```python
                    def on_warning_limit(e, r=row) -> None:  # noqa: ANN001
                        r.warning_limit = e.value

                    ui.number(
                        value=row.warning_limit,
                        min=MIN_WARNING_LIMIT,
                        max=MAX_WARNING_LIMIT,
                        step=1,
                        precision=0,
                        on_change=on_warning_limit,
                    ).props("dense outlined clearable aria-label=警告の件数").classes("w-full").tooltip(
                        "警告のタスクの件数がこの数以上になったら、ダッシュボードで強調します。空は強調しません"
                    ).mark(f"member-warning-limit-{index}")
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS(他のメンバーの表のテストで列の数・順に依存するものが落ちたら、`警告の件数` の列を足した分だけ期待値を直す)

- [ ] **Step 5: 見た目を確かめる(目視)**

`uv run projectapp` で `プロジェクト` → `メンバーとパラメータ`。`丸めない` の右に `警告の件数` の列が出ること、数字を入れて `適用` → 開き直して値が残ること、空にして適用すると空に戻ること、`0` や `1.5` で適用するとエラーが出ることを確かめる。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/forms.py test/test_forms.py test/test_views.py
git commit -m "feat: メンバーの表に警告の件数の閾値の列を足す"
```

---

### Task 4: ダッシュボードの集計に警告を足す

**Files:**
- Modify: `src/projectapp/dashboard.py`
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: `pace.warning_pace`(段階 1)、`Member.warning_limit`(Task 1)
- Produces:
  - `dashboard.warning_tasks(entries: Sequence[Entry], now: datetime) -> frozenset[int]`(`id(task)` の集合)
  - `MemberProgress.warnings: int = 0`、`MemberProgress.limit: int | None = None`(いずれも末尾)
  - `MemberProgress.over_limit -> bool`(`limit is not None and warnings >= limit`)
  - `Progress.warnings: int = 0`(末尾)
  - `DueRow.warning: bool = False`(末尾)
  - `summarize_member_progress(project, children=None, warned: Collection[int] = ())`・`summarize_team_rows(project, children=None, warned: Collection[int] = ())`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の末尾に足す(`from projectapp.dashboard import (...)` に `summarize_due`・`summarize_progress`・`warning_tasks` 等、使うものを足す。`NOW`・`project_of` は既にある。`NOW` = 2026-10-07 水曜 12:00、月曜 9:00 開始の 19.5h で進捗 50% が警告、進捗 82% が予定どおり):

```python
MON = datetime(2026, 10, 5, 9)


def warned_task(name: str, *assignees: str, progress: int = 50) -> Task:
    return Task(name, planned_start=MON, effort_hours=19.5, progress=progress, status=Status.RUNNING, assignees=[Assignee(a) for a in assignees])


def test_progress_counts_the_warning_tasks_once() -> None:
    project = project_of(warned_task("a", "田中"), warned_task("b", "田中", "鈴木"), warned_task("c", "田中", progress=82))
    progress = summarize_progress(project, {}, NOW)
    assert progress.warnings == 2  # 共同タスクは 1 件のまま


def test_member_rows_count_a_shared_warning_task_for_each_assignee() -> None:
    project = project_of(
        warned_task("a", "田中"), warned_task("b", "田中", "鈴木"), warned_task("c", "田中", progress=82),
        members=[Member("田中", 1.0, warning_limit=2), Member("鈴木", 1.0)],
    )
    rows = {row.name: row for row in summarize_progress(project, {}, NOW).by_member}
    assert (rows["田中"].warnings, rows["鈴木"].warnings) == (2, 1)
    assert (rows["田中"].limit, rows["鈴木"].limit) == (2, None)
    assert rows["田中"].over_limit and not rows["鈴木"].over_limit


def test_the_limit_is_reached_exactly_at_the_limit() -> None:
    project = project_of(warned_task("a", "田中"), members=[Member("田中", 1.0, warning_limit=1)])
    assert summarize_progress(project, {}, NOW).by_member[0].over_limit
    project = project_of(warned_task("a", "田中"), members=[Member("田中", 1.0, warning_limit=2)])
    assert not summarize_progress(project, {}, NOW).by_member[0].over_limit


def test_a_warning_task_without_a_member_assignee_counts_for_the_unassigned_row() -> None:
    project = project_of(warned_task("a"), warned_task("b", "外部の人"))
    rows = {row.name: row for row in summarize_progress(project, {}, NOW).by_member}
    assert rows[UNASSIGNED].warnings == 2 and rows[UNASSIGNED].limit is None


def test_team_rows_count_warnings_per_team() -> None:
    <チームのあるプロジェクトを、既存のチーム別のテスト〔`grep -n "summarize_team_rows" test/test_dashboard.py`〕と同じ組み立てで作る。
     甲チーム = 田中、乙チーム = 鈴木。田中のタスクと、田中・鈴木の共同タスクが警告>
    rows = {row.name: row for row in summarize_progress(project, {}, NOW).by_team}
    assert (rows["甲"].warnings, rows["乙"].warnings) == (2, 1)
    assert rows["甲"].limit is None  # チーム別は強調しない


def test_warnings_follow_the_member_filter_and_the_whole_count_is_scoped() -> None:
    project = project_of(warned_task("a", "田中"), warned_task("b", "鈴木"), members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    progress = summarize_progress(project, {}, NOW, "田中")
    assert progress.warnings == 1 and progress.by_member == []


def test_warnings_in_a_referenced_project_use_that_projects_own_settings() -> None:
    # 参照先は稼働可能時間が 3.25h(開いているプロジェクトは 6.5h)。同じタスクでも、参照先の稼働量で判定する
    child = Project("子", base_date=date(2026, 10, 5), daily_hours=3.25, members=[Member("田中", 1.0)], tasks=[warned_task("子の作業", "田中", progress=82)])
    own = project_of()
    progress = summarize_progress(own, {}, NOW, children={"子": ChildProject(child, {})})
    assert progress.warnings == <期待値: 参照先の 3.25h の枠で数え直した判定。実装時に warning_pace(child の task, child, {}, NOW) を直接呼んで期待値を決める>


def test_due_rows_mark_the_warning_tasks_and_not_the_overdue_ones() -> None:
    warned = warned_task("警告", "田中")
    warned.deadline = datetime(2026, 10, 9, 17)
    late = Task("超過", planned_start=MON, effort_hours=6.5, assignees=[Assignee("田中")])
    rows = summarize_due(project_of(warned, late), Period(date(2026, 10, 5), date(2026, 10, 11)), NOW, {})
    by_name = {(row.name, row.kind): row for row in rows}
    assert by_name[("警告", "締切")].warning and not by_name[("警告", "締切")].overdue
    assert not by_name[("超過", "完了予定")].warning and by_name[("超過", "完了予定")].overdue
```

(`project_of` は `tasks=` を取るので `project_of(*tasks, members=...)` の形で呼ぶ。`Assignee`・`Status`・`ChildProject`・`UNASSIGNED` は import に足す。参照先のテストの期待値は、実装後に `pace.warning_pace(参照先のタスク, child, {}, NOW)` の結果から決めて数字を固定する。計算の根拠: 参照先の 19.5h は稼働可能時間 3.25h で 6 日かかり、完了予定が 10/12 になる。進捗 82% の残り 3.51h は、今から完了予定までの稼働量 (水曜の昼から 15:30 の枠がなく、木・金・月の 3.25h × 3 = 9.75h 程度) に収まるので警告にならない。開いているプロジェクトの設定で判定すると警告になる、という差が出ることを確かめる。差が出ないときは、`daily_hours` かタスクの数字を調整して、2 つの設定で結果が分かれる組み合わせにする。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -q -n 0 -k "warning or limit"`
Expected: FAIL(`AttributeError: 'Progress' object has no attribute 'warnings'` など)

- [ ] **Step 3: 実装する**

`dashboard.py`:

1. import に `from collections.abc import Collection, Mapping, Sequence`(`Mapping` は既存。足りないものだけ)、`from projectapp.pace import warning_pace`。
2. `OverdueRow` の後ろの `MemberProgress` を:

```python
@dataclass(frozen=True)
class MemberProgress:
    name: str
    percent: float | None  # 工数で重みづけした進捗率(0〜100)。担当のタスクがなければ None
    counts: dict[Status, int]
    warnings: int = 0  # 警告のタスクの数(共同タスクは担当者それぞれの行に数える)
    limit: int | None = None  # そのメンバーの警告の件数の閾値(メンバー別の行だけ)

    @property
    def over_limit(self) -> bool:
        return self.limit is not None and self.warnings >= self.limit
```

3. `Progress` の `by_team` の次に `warnings: int = 0  # 警告のタスクの数(絞り込みに従う。共同タスクも 1 件)`。
4. `DueRow` の `overdue: bool` の次に `warning: bool = False`。
5. `_entries` の後ろに:

```python
def warning_tasks(entries: Sequence[Entry], now: datetime) -> frozenset[int]:
    """警告のタスクの `id(task)`。判定は、各タスクが属するプロジェクト自身の稼働設定・祝日・イベントで行う(参照先も同じ)。"""
    return frozenset(
        id(entry.task)
        for entry in entries
        if warning_pace(entry.task, entry.project, entry.schedule.holidays, now, entry.schedule) is not None
    )
```

6. `_member_row` を:

```python
def _member_row(name: str, tasks: list[Task], warned: Collection[int] = (), limit: int | None = None) -> MemberProgress:
    counts = {status: 0 for status in Status}
    weighted = total = 0.0
    for task in tasks:
        counts[task.status] += 1
        if (weight_and_percent := _progress_weight(task)) is not None:  # 節目は重みに入れない
            weight, percent = weight_and_percent
            weighted += weight * percent
            total += weight
    return MemberProgress(name, weighted / total if total else None, counts, sum(1 for t in tasks if id(t) in warned), limit)
```

7. `summarize_member_progress(project, children=None, warned: Collection[int] = ())`: メンバーの行は `_member_row(m.name, [...], warned, m.warning_limit)`、`未割り当て` の行は `_member_row(UNASSIGNED, nobody, warned)`。`summarize_team_rows(project, children=None, warned=())`: `_member_row(name, [...], warned)`。
8. `summarize_progress`: ループの前に `entries = _entries(project, holidays, member, children)`、`warned = warning_tasks(entries, now)` を作り、ループは `for entry in entries:`。末尾で `summarize_member_progress(project, children, warned)`・`summarize_team_rows(project, children, warned)`、`Progress(..., by_member, by_team, sum(1 for e in entries if id(e.task) in warned))`。
9. `summarize_due`: `late = is_overdue(...)` の次に `warning = not late and warning_pace(task, project, holidays, now, schedule) is not None`、`DueRow(moment, kind, task.name, assignee_label(task), late, warning)`。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard.py test/test_dashboard_backlog.py test/test_dashboard_view.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: ダッシュボードの集計に、警告のタスクの件数と閾値を足す"
```

---

### Task 5: ダッシュボードの表示(`進捗と遅れ`・`期限とマイルストーン`)

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`progress_card`・`member_progress_row`・`due_card`)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `Progress.warnings`・`MemberProgress.warnings`・`.limit`・`.over_limit`・`DueRow.warning`(Task 4)、`gantt.WARNING_BACKGROUND`(段階 1)
- Produces(マーカー):
  - `dashboard-count-warning`(状態別の件数の行の `警告 n`)
  - `{marker}-warning-{name}`(メンバー別・チーム別の行の `警告 n 件`。`marker` は `dashboard-member` か `dashboard-team-row`。0 件は出さない)
  - `dashboard-member-limit-{name}`(閾値に達した行のアイコン)
  - `dashboard-due-warning-{index}`(期限の行の `警告`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` の `sample()` は変えない(位置引数の既存の構築は、新しい引数が末尾で既定値つきなので通る)。専用のデータを足す:

```python
def warned_sample() -> Dashboard:
    counts = {Status.NOT_STARTED: 0, Status.RUNNING: 2, Status.PAUSED: 0, Status.DONE: 0}
    base = sample()
    base.progress = Progress(
        40.0,
        counts,
        [],
        [
            MemberProgress("田中", 40.0, counts, warnings=3, limit=3),  # 閾値ちょうど
            MemberProgress("鈴木", 40.0, counts, warnings=2, limit=3),  # 閾値の手前
            MemberProgress("佐藤", 40.0, counts, warnings=4, limit=None),  # 閾値なし
            MemberProgress("高橋", 40.0, counts, warnings=0, limit=1),  # 0 件
        ],
        [MemberProgress("甲", 40.0, counts, warnings=5)],
        warnings=5,
    )
    base.due = [
        DueRow(datetime(2026, 10, 8, 17), "締切", "警告の作業", "田中", False, True),
        DueRow(datetime(2026, 10, 9, 12), "完了予定", "遅れ", None, True, False),
        DueRow(datetime(2026, 10, 9, 17), "締切", "ふつう", None, False, False),
    ]
    return base


async def test_the_progress_card_shows_the_warning_count(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-count-warning")
    assert text(user, "dashboard-count-warning") == "警告 5"


async def test_member_and_team_rows_show_the_warning_count_only_when_there_is_one(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-warning-田中")
    assert text(user, "dashboard-member-warning-田中") == "警告 3 件"
    assert text(user, "dashboard-team-row-warning-甲") == "警告 5 件"
    await user.should_not_see(marker="dashboard-member-warning-高橋")


async def test_a_member_at_the_limit_is_highlighted_and_others_are_not(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-member-limit-田中")  # 3 件 / 閾値 3
    await user.should_not_see(marker="dashboard-member-limit-鈴木")  # 2 件 / 閾値 3
    await user.should_not_see(marker="dashboard-member-limit-佐藤")  # 閾値なし
    await user.should_not_see(marker="dashboard-member-limit-高橋")  # 0 件


async def test_the_team_row_is_never_highlighted(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-team-row-warning-甲")
    await user.should_not_see(marker="dashboard-team-row-limit-甲")


async def test_the_due_card_marks_the_warning_rows_only(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(warned_sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-due-warning-0")
    assert text(user, "dashboard-due-warning-0") == "警告"
    await user.should_not_see(marker="dashboard-due-warning-1")  # 予定超過の行は赤のまま
    await user.should_not_see(marker="dashboard-due-warning-2")
    assert "text-negative" in user.find(marker="dashboard-due-1").elements.pop().classes
```

(`Progress`・`MemberProgress`・`DueRow`・`Dashboard` は `test_dashboard_view.py` の import に既にある。足りなければ足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -n 0 -k "warning or highlighted"`
Expected: FAIL(`dashboard-count-warning` が見つからない)

- [ ] **Step 3: 実装する**

`dashboard_view.py`:

1. `from projectapp.gantt import STATUS_COLORS, STATUS_DARK_COLORS, WEEKDAYS` に `WARNING_BACKGROUND` を足す。
2. モジュールに共通の印を足す(`card` などのヘルパーの近く):

```python
def warning_icon(marker: str) -> ui.icon:
    """警告の印。警告の色(`--warning`)のアイコン。文字そのものは色づけしない(白地で読めないため)。"""
    return ui.icon("warning_amber", size="xs").style("color: var(--warning)").mark(marker)
```

3. `progress_card` の状態別の件数の行の末尾(`for status in Status:` のループの後)に:

```python
                with ui.row().classes("items-center no-wrap gap-1"):
                    if progress.warnings:
                        warning_icon("dashboard-count-warning-icon")
                    ui.label(f"警告 {progress.warnings}").mark("dashboard-count-warning")
```

   (この `with ui.row().classes("gap-4"):` の中に入れる。)
4. `member_progress_row` の、`ui.label(row.name)` の行の後ろ(アイコンと名前の行の中)に:

```python
                if row.over_limit:
                    warning_icon(f"{marker}-limit-{row.name}").tooltip(
                        f"警告が閾値({row.limit} 件)に達しています"
                    )
```

   進捗率の行の前に、警告の件数を出す(`row.percent is None` の早期 return より前に置く。タスクなしの行には警告も 0 件なので出ない):

```python
            if row.warnings:
                ui.label(f"警告 {row.warnings} 件").classes(
                    "text-caption" + (" text-weight-bold" if row.over_limit else "")
                ).mark(f"{marker}-warning-{row.name}")
```

5. `due_card` の行: `row.warning` のとき、行に `.style(f"background: {WARNING_BACKGROUND}")` を付け、名前の後ろに `warning_icon` と `ui.label("警告").classes("text-caption").mark(f"dashboard-due-warning-{index}")` を足す。`ui.row()` の作成を `line = ui.row().classes("w-full items-center no-wrap gap-2")`、`if row.warning: line.style(f"background: {WARNING_BACKGROUND}")`、`with line:` の形に直す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS

- [ ] **Step 5: 確認用データを作る**

`docs/samples/警告の確認.json` に追記する形で、ダッシュボードの確認用データを作る(閾値を持つメンバーと、共同タスク、チーム):

```bash
uv run python - <<'EOF'
import json
from pathlib import Path
for path in (Path("docs/samples/警告の確認.json"), Path.home() / ".projectapp/警告の確認.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = 19
    for member in data["members"]:
        member["warning_limit"] = 2 if member["name"] == "田中" else None
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
EOF
```

(「今」= 2026-11-04 12:00 で、田中が警告 2 件〔`進捗が遅れている`・`計画が短すぎる`〕= 閾値 2 に達して強調、鈴木は閾値なしで 1 件〔`着手が遅れている`〕になる。)

- [ ] **Step 6: 見た目を確かめる(目視)**

`FAKE_NOW=2026-11-04T12:00` で起動し、`D` でダッシュボード。`進捗と遅れ` の件数の行に `警告 3`、メンバー別の田中に `警告 2 件`(太字・アイコン)と、鈴木に `警告 1 件`(強調なし)、`期限とマイルストーン`(期間を `全期間` にする)で警告のタスクの行に黄色の背景と `警告` が出ることを確かめる。`メンバーとパラメータ` で田中の閾値を 3 にして適用 → 強調が消えること。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py docs/samples
git commit -m "feat: ダッシュボードに警告の件数と閾値の強調を出す"
```

---

### Task 6: プロジェクト参照行に `警告 n件` のチップを出す

**Files:**
- Modify: `src/projectapp/models.py`(`ReferenceValue`)
- Modify: `src/projectapp/reference.py`(`compute_reference`)
- Modify: `src/projectapp/storage.py`(`_reference_value`)
- Modify: `src/projectapp/gantt.py`(`reference_chips`・`reference_text`)
- Test: `test/test_reference.py`・`test/test_reference_storage.py`・`test/test_gantt.py`

**Interfaces:**
- Consumes: `pace.warning_pace`(段階 1)
- Produces:
  - `ReferenceValue.warned: int = 0`(**末尾の `taken_at` の後ろ**に足し、既存の位置引数・キーワード引数の構築を壊さない)
  - マーカー `ref-warning-{key}-{ti}`(チップ)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_reference.py` の `test_delay_counts_unfinished_tasks_past_their_end` の後に(`compute_reference`・`source` はそのファイルの既存のもの。`WARN_NOW` は専用に置く):

```python
WARN_NOW = datetime(2026, 10, 7, 12)  # 水曜の昼。月曜 9:00 開始の 19.5h・進捗 50% は警告、進捗 82% は予定どおり


def warn_task(name: str, progress: int) -> Task:
    return Task(name, planned_start=datetime(2026, 10, 5, 9), effort_hours=19.5, progress=progress, status=Status.RUNNING)


def test_warned_counts_the_warning_tasks_only() -> None:
    project = Project("基盤", members=[Member("田中", 1.0)], tasks=[warn_task("a", 50), warn_task("b", 50), warn_task("c", 82)])
    assert compute_reference(project, {}, WARN_NOW).warned == 2


def test_warned_uses_the_referenced_projects_own_settings() -> None:
    # 同じタスクでも、参照先の稼働可能時間で判定が分かれる
    normal = Project("基盤", members=[Member("田中", 1.0)], tasks=[warn_task("a", 82)])
    short = Project("基盤", daily_hours=3.25, members=[Member("田中", 1.0)], tasks=[warn_task("a", 82)])
    assert compute_reference(normal, {}, WARN_NOW).warned == 0
    assert compute_reference(short, {}, WARN_NOW).warned == <実装後に warning_pace を直接呼んで決める。分かれない場合は、タスクの数字を調整して 2 つの設定で結果が分かれる組み合わせにする>


def test_overdue_and_done_tasks_are_not_counted_as_warned() -> None:
    late = Task("超過", planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5)
    done = Task("終了", planned_start=datetime(2026, 10, 5, 9), effort_hours=19.5, status=Status.DONE)
    project = Project("基盤", members=[Member("田中", 1.0)], tasks=[late, done])
    assert compute_reference(project, {}, WARN_NOW).warned == 0


def test_the_snapshot_differs_when_only_the_warned_count_differs() -> None:
    from dataclasses import replace

    value = compute_reference(source(), {}, NOW)
    assert not value.same_as(replace(value, warned=value.warned + 1))
```

`test/test_reference_storage.py`:
- 先頭の `VALUE` に `warned=2,` を足す(`delayed=3,` の次)。
- 末尾に(`json`・`pytest` の import がなければ足す):

```python
def test_a_snapshot_without_warned_is_read_as_zero_and_a_bad_one_is_rejected() -> None:
    project = Project("p", reference_mode=ReferenceMode.SNAPSHOT, sections=[Section("s", [reference_task(ref_snapshot=VALUE)])])
    data = json.loads(dumps_project(project))
    snapshot = data["sections"][0]["tasks"][0]["ref_snapshot"]
    assert snapshot["warned"] == 2
    del snapshot["warned"]
    loaded = parse_project(json.dumps(data), "p")
    assert loaded.sections[0].tasks[0].ref_snapshot.warned == 0  # type: ignore[union-attr]
    for bad in (True, -1, 1.5, "2"):
        snapshot["warned"] = bad
        with pytest.raises(ValueError, match="警告の件数"):
            parse_project(json.dumps(data), "p")
```

`test/test_gantt.py`: `SPAN`(3884 行付近)の `delayed=3,` の次に `warned=2,` を足す。`test_a_reference_row_draws_one_band_with_delay_and_load_chips` の後に(`replace` は `from dataclasses import replace` を足す):

```python
async def test_a_reference_row_shows_the_warning_chip(user: User) -> None:
    reference_chart(SPAN)
    await user.open("/")
    assert "警告 2件" in user.find(marker="ref-warning-top-0").elements.pop().text


async def test_no_warning_chip_without_warned_tasks(user: User) -> None:
    reference_chart(replace(SPAN, warned=0))
    await user.open("/")
    await user.should_see(marker="ref-delay-top-0")
    await user.should_not_see(marker="ref-warning-top-0")


async def test_the_reference_hover_lists_the_warning_count(user: User) -> None:
    <`test_the_reference_hover_says_it_opens_on_click_and_the_band_underlines` と同じ手順で帯のホバーの文字を取り出す>
    assert "警告 2 件" in <ホバーの文字>
```

「表示項目をオフにすると出ない」は、遅延のチップのオフのテスト(`grep -n "ref-delay" test/test_gantt.py` で、`show_alerts=False` を使うもの)に、`ref-warning-top-0` が出ない検査を 1 行足す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_reference.py test/test_reference_storage.py test/test_gantt.py -q -n 0 -k "warn"`
Expected: FAIL(`ReferenceValue` に `warned` がない)

- [ ] **Step 3: 実装する**

`models.py`: `ReferenceValue` の末尾 `taken_at: datetime | None = None` の次に `warned: int = 0  # 警告(完了予定を過ぎる見込み)のタスク数。参照先自身の設定で数える`。

`reference.py`: `from projectapp.pace import warning_pace` を足し、`compute_reference` の `delayed = ...` の次に:

```python
    warned = sum(1 for task in tasks if warning_pace(task, project, holidays, now, schedule) is not None)
```

`ReferenceValue(...)` に `warned=warned,` を足す。

`storage.py` の `_reference_value`: `delayed` の検査の次に:

```python
        warned = raw.get("warned", 0)
        if isinstance(warned, bool) or not isinstance(warned, int) or warned < 0:
            raise ValueError("スナップショットの警告の件数が正しくありません")
```

`ReferenceValue(...)` に `warned=warned,` を足す。書き込みは `asdict` なので変更不要。

`gantt.py`:
- `reference_chips` の `遅延` のチップの次、`負荷` のチップの前に:

```python
        if self.options.show_alerts and value.warned:
            ui.label(f"警告 {value.warned}件").style(
                REFERENCE_CHIP_STYLE + " background: var(--warning); color: #212121;"
            ).mark(f"ref-warning-{key}-{ti}")
```

  (黄色の背景に固定の黒系の文字。ダークテーマでも黄色なので、文字色は変えない。)
- `reference_text` の `lines.append(f"遅延 {value.delayed} 件")` の次に `lines.append(f"警告 {value.warned} 件")`。
- 帯の色(`late`)は変えない。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_reference.py test/test_reference_storage.py test/test_gantt.py test/test_dashboard_references.py -q -n auto && uv run pytest -m smoke -q -n auto`
Expected: すべて PASS(チップの数・順に依存する既存のテストが落ちたら、期待値を直す)

- [ ] **Step 5: 確認用データと見た目の確認(目視)**

`docs/samples/警告の確認.json` を参照先として、親のプロジェクトを作る。参照行のデータの書き方は、既存の確認用データ(`grep -l ref_project docs/samples/*.json`)に合わせる。`docs/samples/警告の確認(親).json` を作り、`~/.projectapp/` にもコピーする。

`FAKE_NOW=2026-11-04T12:00` で `警告の確認(親)` を開き、参照行の名前の右に `遅延 1件`・`警告 3件`(黄)が並ぶこと、帯のホバーに `警告 3 件` が出ること、`プロジェクト参照の方式` を `スナップショット` にして保存し、開き直しても件数が残ることを確かめる。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/models.py src/projectapp/reference.py src/projectapp/storage.py src/projectapp/gantt.py test/test_reference.py test/test_reference_storage.py test/test_gantt.py docs/samples
git commit -m "feat: プロジェクト参照行に、警告のタスクの件数のチップを出す"
```

---

### Task 7: 仕様と記録を更新する

**Files:**
- Modify: `CLAUDE.md`・`docs/development.md`・`docs/work-log.md`・`docs/requests.md`・`docs/request-history.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

1. 段階 1 で足した警告の項目の末尾 `ダッシュボードへの表示と、メンバーごとの件数の閾値は、続く段階で足す` を、`ダッシュボードとメンバーごとの件数の閾値は、下のとおり` に直す。
2. `## ダッシュボード` の、`進捗と遅れ` を説明している項(`4 つの柱: ...`)の近くに足す:

```markdown
- 警告のタスク(ガントチャートと同じ判定)を、`進捗と遅れ`の状態別の件数の行に`警告 n`(絞り込みに従う。共同タスクは 1 件)として出す。`メンバー別`・`チーム別`の各行には`警告 n 件`を出す(0 件は出さない。共同タスクは担当者それぞれの行に数える。担当がメンバーでないタスク・担当なしは`未割り当て`)。メンバー別の行は、そのメンバーの`警告の件数`(閾値)があり、件数が閾値以上のとき、警告のアイコンと太字で強調する(チーム別・`未割り当て`は強調しない)。参照先の通常タスクも、参照先自身の稼働設定・祝日・イベントで判定して同列に数える。`期限とマイルストーン`では、警告のタスクの行(締切・完了予定の両方)に警告の色の背景と`警告`を添える(予定超過の行は赤のまま)。集計は保存しない
```

3. プロジェクト参照の項の、遅延・負荷のチップを説明している箇所に、`警告 n件`のチップ(警告の色の背景。参照先自身の設定で数える。スナップショットは`warned`を保存し、キーのない古い値は 0 で読む)を足す。
4. メンバーの節(`メンバー`（担当者）は、プロジェクトごとに名前と`基本比率`... の項)の末尾に `。メンバーごとに`警告の件数`(閾値。整数 1〜999、空は閾値なし)を持てる(メンバーの表の列。ダッシュボードの強調に使う)` を足す。
5. 実装上の注意の version の説明: `現在 18` を `現在 19` に、括弧の中の `18 でイベントの色に`#rrggbb`を許した` の後ろに `、19 でメンバーの`warning_limit`〔警告の件数の閾値〕` を足す。設定のエクスポート・インポートの項(`メンバー(稼働日の上書き・アイコン・段階の選択を含む)`)に `・警告の件数` を足す。

- [ ] **Step 2: ほかの文書を更新する**

- `docs/development.md:112` の `現在 18` を `現在 19` に。
- `docs/requests.md` の要望 103 の状態の行を、`段階 2(ダッシュボード・メンバーの閾値。version 19)を実装済み(PR 作成中)` に更新(残りは段階 3)。`docs/request-history.md` の 103 の行も同様。
- `docs/work-log.md` の末尾に、段階 2 の記録(件数を `id(task)` の集合で数えて全体・メンバー・チームで共有したこと、共同タスクの行の合計が全体と一致しないのは仕様であること、強調にアイコンと太字を使い文字色を黄にしなかった理由〔白地のコントラスト〕、version 19、確認用データ、テスト件数)を足す。

- [ ] **Step 3: 全体の確認**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS。`ty` の診断は変更前と同じ 1 件。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs
git commit -m "docs: 要望 103 の段階 2 の仕様と記録を更新する"
```

---

## Self-Review

**Spec coverage**(設計書の段階 2):
- `進捗と遅れ`: 状態別の行の `警告 n`・メンバー別/チーム別の `警告 3 件`・閾値での強調・絞り込み・参照先 → Task 4(集計)・5(表示)
- `期限とマイルストーン` の警告の行 → Task 4(`DueRow.warning`)・5
- メンバーの閾値の設定(メンバーの表の `警告の件数` の列、整数 1〜999、空は閾値なし) → Task 3
- version 19(読み書き・古いファイルの既定・不正値の拒否) → Task 1
- 3 者マージ・設定のエクスポート/インポート・子プロジェクトへの引き継ぎ・元に戻す → Task 2(元に戻すは `build_members` を通すメンバーの適用と同じ経路なので追加の作業なし。Task 3 のテストで適用を通す)
- 参照行の `警告 n件`(名前の欄のチップ・帯のホバー・スナップショットの `warned`) → Task 6
- 段階 3(98 のボタン)・追加工数 → 範囲外

**Placeholder scan:** テストの `<...>` は、既存テストの組み立て(チームのプロジェクト・メンバーのダイアログの手順・上書きの呼び出し)を写す指示で、写す元の場所(ファイル・行・テスト名)を書いている。参照先の期待値は、数字を実装時に `warning_pace` から決める手順と根拠を書いた。それ以外に TBD はない。

**Type consistency:** `ReferenceValue.warned` は Task 6 で定義し、`compute_reference`・`_reference_value`・`reference_chips`・`reference_text` が同じ名前で使う。 `MemberProgress(name, percent, counts, warnings, limit)`・`over_limit` は Task 4 で定義し、Task 5 のテスト・実装が同じ名前で使う。`DueRow(..., overdue, warning)` の位置は、Task 4 の定義と Task 5 のテストの構築で一致。`warning_tasks` は Task 4 内だけで使う。マーカー名は Task 5 の Interfaces とテストで一致(`{marker}-warning-{name}`・`{marker}-limit-{name}`)。`MemberRow.warning_limit: float | None` と `Member.warning_limit: int | None` の変換は `build_members` の 1 か所。

**Review Focus:** 共同タスクの数え方(Task 4 `test_member_rows_count_a_shared_warning_task_for_each_assignee`)、参照先の設定(`test_warnings_in_a_referenced_project_use_that_projects_own_settings`)、古いファイル・不正値(Task 1)、閾値の空・不正(Task 3)、マージ(Task 2)、閾値ちょうど(Task 4 `test_the_limit_is_reached_exactly_at_the_limit`・Task 5 `test_a_member_at_the_limit_is_highlighted_and_others_are_not`)をそれぞれ押さえている。
