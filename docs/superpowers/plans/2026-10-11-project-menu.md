# プロジェクトメニューの見直し Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ヘッダーのメニューを整理する(新規作成をファイルメニューへ、メンバーとパラメータを 1 つのタブ付きダイアログへ、ダッシュボードの項目を足す、全項目にアイコン)。

**Architecture:** `forms.py` の 2 つのダイアログ(`open_members_dialog`・`open_parameters_dialog`)を、タブの中身を作る `members_panel`・`parameters_panel` に分け、`open_members_parameters_dialog` が `ui.tab_panels` に並べる。適用してもダイアログは閉じず、適用のたびにプロジェクトから行を作り直す。メニューは `MenuItem`(文言・アイコン・操作・マーカー・キー)で組み立てる。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、型検査は `ty`。

**Spec:** `docs/superpowers/specs/2026-10-11-project-menu-design.md`

## Global Constraints

- コード規約(`.claude/RULE.md`): すべての関数に型引数と戻り値の型を書く。コメントは多くても 3 行以内。`uv run ty check` を通す
- 言語は日本語(画面の文言・コメント・コミットメッセージ)
- 保存形式(`version`)・`Ctrl/Cmd+N`・`Ctrl/Cmd+,`・設定ダイアログは変えない
- ショートカットは `Ctrl/Cmd+Shift+M`(`Ctrl/Cmd+M` は使わない。macOS の最小化)
- マーカー: `file-new`・`open-settings` は変えない。`open-members`・`open-parameters` は無くし、`open-members-parameters` にする。メニューのダッシュボードは `menu-open-dashboard`(ヘッダーのアイコンの `open-dashboard` は変えない)
- コミットメッセージの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- テストの実行: `cd /Users/jun/Documents/opt/work/projectapp && uv run pytest -n auto -q`

## Review Focus

- 未適用のパラメータの編集があるまま、メンバーのタブで適用する(メンバーの検証は、適用済みのパラメータに対して行う)
- パラメータの適用でメンバーが選んでいた段階が消える・改名される(メンバーの未適用の行も追従し、`●` が出ない)
- メンバーを適用したあと、もう一度適用する(改名の対応が二重にならない。新しい行の id が重ならない)
- パラメータを 1 つも持たないプロジェクトで、パラメータを追加して適用する(メンバーの表に、列と相対比率が現れる)
- 「メンバーとパラメータ」を開いたまま `d`・`Ctrl/Cmd+Shift+M` を押す(ダイアログが開いているあいだは効かない・二重に開かない)

---

### Task 1: 段階の選択を新しい定義へ写す純粋関数

**Files:**
- Modify: `src/projectapp/ratios.py:81-95`
- Test: `test/test_ratios.py`

**Interfaces:**
- Consumes: `ParameterEdit`(`parameter_map: dict[str, str | None]`、`level_map: dict[str, dict[str, str | None]]`)
- Produces: `remap_levels(levels: dict[str, str], edit: ParameterEdit) -> dict[str, str]`(旧い名前で引く。削除・存在しない参照は外す)。`apply_parameter_edit` がこれを使う

- [ ] **Step 1: 失敗するテストを書く**

`test/test_ratios.py` の末尾に足す(ファイル冒頭の import に `remap_levels` を足す。`ParameterEdit` の import は既存のものを使う)。

```python
def test_remap_levels_follows_renames_and_drops_deleted():
    edit = ParameterEdit(
        [Parameter("経験値", [Level("上", 0.2)])],
        {"経験": "経験値", "言語": None},
        {"経験": {"上級": "上", "初級": None}, "言語": {"日本語": None}},
    )
    levels = {"経験": "上級", "言語": "日本語", "不明": "x"}
    assert remap_levels(levels, edit) == {"経験値": "上"}
    assert remap_levels({"経験": "初級"}, edit) == {}


def test_remap_levels_does_not_change_its_argument():
    edit = ParameterEdit([Parameter("a", [])], {"a": "a"}, {"a": {}})
    levels = {"a": "x"}
    remap_levels(levels, edit)
    assert levels == {"a": "x"}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_ratios.py -q`
Expected: FAIL(`ImportError: cannot import name 'remap_levels'`)

- [ ] **Step 3: 実装する**

`src/projectapp/ratios.py` の `apply_parameter_edit` を次に置き換える。

```python
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
    """定義を置き換え、全メンバーの選択を更新する。"""
    for member in project.members:
        member.levels = remap_levels(member.levels, edit)
    project.parameters = edit.parameters
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_ratios.py test/test_views.py -q -k "ratio or parameter"`
Expected: PASS(既存の `apply_parameter_edit` のテストも通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/ratios.py test/test_ratios.py
git commit -m "refactor: 段階の選択を新しい定義へ写す処理を remap_levels に分ける

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: メンバーとパラメータのタブ付きダイアログ

**Files:**
- Modify: `src/projectapp/forms.py`(`open_parameters_dialog`:981 付近、`open_members_dialog`:1145 付近を置き換える。import に `deepcopy` と `remap_levels` を足す)
- Modify: `src/projectapp/views.py`(import:33-35、`open_members`:520、`open_parameters`:540、`apply_members`、`apply_parameters`、ヘッダーのメニュー項目)
- Test: `test/test_views.py`(既存の `open-members`・`open-parameters` を使うテストを移し、新しいテストを足す)

**Interfaces:**
- Consumes: `build_members`・`build_parameter_edit`・`member_columns`・`member_table_min_rem`・`effective_ratio_text`(既存)、`remap_levels`(Task 1)、`disposable`
- Produces:
  - `members_panel(get_members, assigned, on_apply, get_parameters, get_taken) -> MembersPanel`
  - `parameters_panel(get_parameters, impacts, on_apply, on_applied) -> ParametersPanel`
  - `open_members_parameters_dialog(...) -> None`
  - `MainView.open_members_parameters(self) -> None`
  - マーカー: ダイアログの `members-parameters-tabs`(`ui.tabs`)・`members-parameters-panels`(`ui.tab_panels`)・`tab-members`・`tab-parameters`・`members-dirty`・`parameters-dirty`(`●`。未適用の編集があるときだけ表示)・`members-parameters-cancel`。既存の `member-*`・`parameter-*`・`level-*` は変えない

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `open_members_view` の下に足す。

```python
async def open_members_parameters(user: User) -> None:
    user.find(marker="open-members-parameters").click()
    await user.should_see(marker="members-parameters-panels")


async def test_the_members_parameters_dialog_opens_on_the_members_tab(user: User, tmp_path: Path) -> None:
    await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    panels = user.find(marker="members-parameters-panels").elements.pop()
    assert panels.value == "members"
    await user.should_see(marker="tab-members")
    await user.should_see(marker="tab-parameters")


async def test_applying_the_members_tab_keeps_the_dialog_open(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["田中"])
    await user.should_see(marker="members-parameters-panels")  # 閉じない
    user.find(marker="member-name-0").clear().type("田中太郎")  # 続けて適用できる(改名は 1 回分)
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["田中太郎"])


async def test_applying_parameters_rebuilds_the_member_columns_and_keeps_unapplied_member_edits(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")  # 未適用
    user.find(marker="parameter-add").click()
    await user.should_see(marker="parameter-name-0")
    user.find(marker="parameter-name-0").type("経験")
    user.find(marker="level-add-0").click()
    await user.should_see(marker="level-name-0-0")
    user.find(marker="level-name-0-0").type("上級")
    user.find(marker="level-value-0-0").clear().type("20")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: [p.name for p in view.project.parameters] == ["経験"])
    await user.should_see(marker="member-level-0-0")  # メンバーの表に、パラメータの列ができる
    await user.should_see(marker="member-effective-0")
    assert view.project.members == []  # メンバーは、まだ適用していない
    assert user.find(marker="member-name-0").elements.pop().value == "田中"


async def test_a_parameter_rename_and_delete_carry_over_to_unapplied_member_rows(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.parameters = [Parameter("経験", [Level("上級", 0.2), Level("初級", -0.1)])]
    view.project.members = [Member("田中", 1.0, {"経験": "上級"}, "m1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-name-0").clear().type("田中A")  # 未適用の編集
    user.find(marker="parameter-name-0").clear().type("経験値")
    user.find(marker="level-delete-0-1").click()  # 「初級」を削除(選んでいるメンバーはいない)
    await user.should_see(marker="level-add-0")
    user.find(marker="parameter-apply").click()
    assert await wait_until(lambda: view.project.parameters[0].name == "経験値")
    assert view.project.members[0].levels == {"経験値": "上級"}
    member_row_level = user.find(marker="member-level-0-0").elements.pop()
    assert member_row_level.value == "上級"  # 未適用の行も、改名に追従する
    assert user.find(marker="member-name-0").elements.pop().value == "田中A"


async def test_the_tabs_show_a_mark_while_they_have_unapplied_edits(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    members_mark = user.find(marker="members-dirty").elements.pop()
    parameters_mark = user.find(marker="parameters-dirty").elements.pop()
    assert not members_mark.visible and not parameters_mark.visible
    user.find(marker="member-add").click()
    assert await wait_until(lambda: members_mark.visible)
    assert not parameters_mark.visible
    user.find(marker="member-name-0").type("田中")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: not members_mark.visible)
    assert view.project.members[0].name == "田中"
    user.find(marker="parameter-add").click()
    assert await wait_until(lambda: parameters_mark.visible)


async def test_cancel_closes_the_dialog_and_discards_unapplied_edits(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="member-add").click()
    await user.should_see(marker="member-name-0")
    user.find(marker="member-name-0").type("田中")
    user.find(marker="members-parameters-cancel").click()
    await user.should_not_see(marker="members-parameters-panels")
    assert view.project.members == []
    assert not view.is_dirty()
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "members_parameters or unapplied or the_tabs_show or cancel_closes"`
Expected: FAIL(`open-members-parameters` が見つからない)

- [ ] **Step 3: forms.py を置き換える**

`forms.py` の import に `from copy import deepcopy` を足し、`from projectapp.ratios import ParameterEdit, ratio_detail, remap_levels, validate_parameters` にする。

`open_parameters_dialog`(981 行〜、`dialog.open()` まで)を、次の `ParametersPanel` と `parameters_panel` に置き換える。表の描画(`table`)・`add_parameter`・`remove_parameter`・`add_level`・`remove_level`・削除確認のダイアログの中身は、**既存のコードをそのまま**使う。変えるのは、冒頭、`commit`・`apply`、末尾だけ。

```python
@dataclass
class ParametersPanel:
    """パラメータのタブの操作。dirty は、未適用の編集があるか。"""

    dirty: Callable[[], bool]


def parameters_panel(
    get_parameters: Callable[[], list[Parameter]],
    impacts: Callable[[ParameterEdit], list[tuple[str, int]]],
    on_apply: Callable[[ParameterEdit], object],
    on_applied: Callable[[ParameterEdit], object],
) -> ParametersPanel:
    """パラメータの定義の編集(タブの中身)。削除でメンバーの選択が外れるときは、適用の前に確認する。
    適用してもダイアログは閉じず、プロジェクトの今の定義から行を作り直す。"""

    def to_rows() -> list[ParameterRow]:
        return [
            ParameterRow(p.name, p.name, [LevelRow(lv.name, lv.name, round(lv.value * 100, 2)) for lv in p.levels])
            for p in get_parameters()
        ]

    rows = to_rows()
    baseline = deepcopy(rows)
    ui.label("相対比率 = 基本比率 + 選んだ段階の判定値の合計(10〜300% に丸めます)").classes("text-caption text-grey")

    # ここに、既存の `table`(@ui.refreshable)・add_parameter・remove_parameter・add_level・remove_level を、そのまま置く

    table()
    ui.button("パラメータを追加", icon="add", on_click=add_parameter).props("flat").mark("parameter-add")
    error = ui.label("").classes("text-negative").mark("parameter-error")
    pending: dict[str, ParameterEdit] = {}
    # ここに、既存の削除確認の `with ui.dialog() as confirm, ui.card():` ブロックを、そのまま置く

    def commit(edit: ParameterEdit) -> None:
        on_apply(edit)
        on_applied(edit)
        rows[:] = to_rows()
        baseline[:] = deepcopy(rows)
        table.refresh()

    def confirm_apply() -> None:
        confirm.close()
        commit(pending["edit"])

    def apply() -> None:
        error.set_text("")
        try:
            edit = build_parameter_edit(rows, get_parameters())
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

    ui.button("適用", on_click=apply).mark("parameter-apply")
    return ParametersPanel(dirty=lambda: rows != baseline)
```

`open_members_dialog`(1145 行〜、`dialog.open()` まで)を、次の `MembersPanel` と `members_panel` に置き換える。`table` の中身は既存のままで、**冒頭の 1 行だけ**足し、`chosen_parameters`・`with_effective`・`columns`・`min_rem` を `layout()` から読む(下のコードの `table` の先頭を参照)。`remove`・`add` も既存のまま。

```python
@dataclass
class MembersPanel:
    """メンバーのタブの操作。dirty は未適用の編集があるか、min_rem は今の表の幅(rem)、
    parameters_changed は、パラメータの適用を、未適用の行へ伝える。"""

    dirty: Callable[[], bool]
    min_rem: Callable[[], int]
    parameters_changed: Callable[[ParameterEdit], None]


def members_panel(
    get_members: Callable[[], list[Member]],
    assigned: Callable[[str], int],
    on_apply: Callable[[list[Member], dict[str, str]], object],
    get_parameters: Callable[[], list[Parameter]],
    get_taken: Callable[[], Collection[str]],
) -> MembersPanel:
    """メンバーの編集(タブの中身)。1 行が 1 人の表(名前・基本比率・パラメータごとの段階・実効比率・削除)。
    適用してもダイアログは閉じず、プロジェクトの今のメンバーから行を作り直す。"""

    def to_rows() -> list[MemberRow]:
        return [MemberRow(m.name, m.name, round(m.ratio * 100, 2), dict(m.levels), m.id) for m in get_members()]

    rows = to_rows()
    baseline = deepcopy(rows)
    originals = [r.name for r in rows]
    current = {"parameters": list(get_parameters())}

    def layout() -> tuple[list[Parameter], bool, list[str], int]:
        parameters = current["parameters"]
        with_effective = bool(parameters)
        return (
            parameters,
            with_effective,
            member_columns(len(parameters), with_effective),
            member_table_min_rem(len(parameters), with_effective),
        )

    @ui.refreshable
    def table() -> None:
        chosen_parameters, with_effective, columns, min_rem = layout()
        # ここから下は、既存の `table` の本体(`if not rows:` 以降)をそのまま置く

    # ここに、既存の remove・add を、そのまま置く

    table()
    ui.button("メンバーを追加", icon="add", on_click=add).props("flat").mark("member-add")
    error = ui.label("").classes("text-negative").mark("member-error")

    def apply() -> None:
        try:
            result = build_members(rows, originals, assigned, current["parameters"], get_taken())
        except ValueError as exc:
            error.set_text(str(exc))
            return
        error.set_text("")
        on_apply(*result)
        rows[:] = to_rows()
        baseline[:] = deepcopy(rows)
        originals[:] = [r.name for r in rows]
        table.refresh()

    def parameters_changed(edit: ParameterEdit) -> None:
        for row in (*rows, *baseline):  # 未適用の行も、適用済みの基準も、同じように写す(印が出ない)
            row.levels = remap_levels(row.levels, edit)
        current["parameters"] = list(get_parameters())
        table.refresh()

    ui.button("適用", on_click=apply).mark("member-apply")
    return MembersPanel(
        dirty=lambda: rows != baseline, min_rem=lambda: layout()[3], parameters_changed=parameters_changed
    )


def open_members_parameters_dialog(
    *,
    get_members: Callable[[], list[Member]],
    assigned: Callable[[str], int],
    on_apply_members: Callable[[list[Member], dict[str, str]], object],
    get_parameters: Callable[[], list[Parameter]],
    impacts: Callable[[ParameterEdit], list[tuple[str, int]]],
    on_apply_parameters: Callable[[ParameterEdit], object],
    get_taken: Callable[[], Collection[str]],
) -> None:
    """メンバーとパラメータのダイアログ。タブごとに適用し、適用しても閉じない(キャンセルで閉じる)。"""
    with disposable(ui.dialog()) as dialog, ui.card() as card:
        ui.label("メンバーとパラメータ").classes("text-h6")
        with ui.tabs().mark("members-parameters-tabs") as tabs:
            with ui.tab("members", label="メンバー").mark("tab-members"):
                members_mark = ui.label("●").classes("text-orange q-ml-xs").mark("members-dirty")
            with ui.tab("parameters", label="パラメータ").mark("tab-parameters"):
                parameters_mark = ui.label("●").classes("text-orange q-ml-xs").mark("parameters-dirty")
        members_mark.set_visibility(False)
        parameters_mark.set_visibility(False)
        with ui.tab_panels(tabs, value="members").props("keep-alive").classes("w-full").mark(
            "members-parameters-panels"
        ):
            with ui.tab_panel("members"):
                members = members_panel(get_members, assigned, on_apply_members, get_parameters, get_taken)
            with ui.tab_panel("parameters"):

                def parameters_applied(edit: ParameterEdit) -> None:
                    members.parameters_changed(edit)
                    fit_width()

                parameters = parameters_panel(get_parameters, impacts, on_apply_parameters, parameters_applied)

        def fit_width() -> None:
            card.style(replace=f"width: {max(36, members.min_rem() + 3)}rem; max-width: 96vw")

        def update_marks() -> None:
            members_mark.set_visibility(members.dirty())
            parameters_mark.set_visibility(parameters.dirty())

        fit_width()
        ui.timer(0.3, update_marks)
        ui.button("キャンセル", on_click=dialog.close).props("flat").mark("members-parameters-cancel")
    dialog.open()
```

メンバーの表の中の `chosen_parameters` を使う箇所(列の見出し・段階の選択・実効比率)は、`table` の先頭の `layout()` の戻り値をそのまま使う。`refresh_effective` が `chosen_parameters` を読む箇所は、`table` の内側の定義のままなので変更不要。

- [ ] **Step 4: views.py をつなぐ**

import の `open_members_dialog`・`open_parameters_dialog` を `open_members_parameters_dialog` に置き換える(アルファベット順の位置に)。`open_members`(520 行)と `open_parameters`(540 行)を、次の 1 つに置き換える。`assigned_count`・`apply_members`・`apply_parameters` は変えない。

```python
    def open_members_parameters(self) -> None:
        open_members_parameters_dialog(
            get_members=lambda: self.project.members,
            assigned=self.assigned_count,
            on_apply_members=self.apply_members,
            get_parameters=lambda: self.project.parameters,
            impacts=lambda edit: deletion_impacts(self.project, edit),
            on_apply_parameters=self.apply_parameters,
            get_taken=self.project.used_ids,
        )
```

ヘッダーのプロジェクトメニュー(`header` 内)の `メンバー`・`パラメータ` の 2 行を、次の 1 行に置き換える。

```python
                    ("メンバーとパラメータ", self.open_members_parameters, "open-members-parameters"),
```

- [ ] **Step 5: 既存のテストを移す**

`test/test_views.py` の `user.find(marker="open-members").click()` と `user.find(marker="open-parameters").click()` を、すべて `await open_members_parameters(user)` に置き換える(`sed -i '' 's/user.find(marker="open-members").click()/await open_members_parameters(user)/; s/user.find(marker="open-parameters").click()/await open_members_parameters(user)/' test/test_views.py`)。`test_the_menus_list_their_items_in_order` の期待値は Task 3 で直すので、ここでは触らない。適用後に「ダイアログが閉じる」ことを確かめている既存のテストがあれば、閉じない動きに合わせて直す(閉じる確認は、`members-parameters-cancel` で行う)。

- [ ] **Step 6: 通ることを確かめる**

Run: `uv run pytest test/test_views.py test/test_forms.py -q -x`
Expected: PASS(`test_the_menus_list_their_items_in_order` だけは失敗してよい。Task 3 で直す)

- [ ] **Step 7: 型検査**

Run: `uv run ty check src`
Expected: エラーなし

- [ ] **Step 8: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_views.py
git commit -m "feat: メンバーとパラメータを、タブ付きの 1 つのダイアログにまとめる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: メニューの構成・アイコン・ダッシュボードの項目

**Files:**
- Modify: `src/projectapp/views.py`(`header`:790 付近、`header_menu`、`theme_menu`:860 付近)
- Test: `test/test_views.py`(`menu_items`:1910、`test_the_menus_list_their_items_in_order`:1925)

**Interfaces:**
- Consumes: `MainView.request_new`・`open_settings`・`open_members_parameters`・`open_dashboard`・`show_file_list`・`save_project_clicked`・`save_as`・`refresh_holidays`・`enter_preview`・`open_handoff`・`help_dialog.open`
- Produces: `MenuItem(text, icon, handler, marker, key="")`(`views.py` 内の dataclass)、`header_menu(label, marker, items: list[MenuItem | None])`

- [ ] **Step 1: 失敗するテストを書く**

`menu_items` を、アイコンの区間も持つ項目に対応させ、期待値を新しい構成にする。

```python
def menu_items(user: User, menu_marker: str) -> list[tuple[str, str]]:
    """メニューの項目(文言, マーカー)を、並んだ順に返す。文言は、項目の中の、アイコンでも右端のキーでもない ItemSection。"""
    menu = user.find(marker=menu_marker).elements.pop()
    return [
        (label_section(child).text, next(iter(child._markers)))
        for child in menu.default_slot.children
        if isinstance(child, ui.menu_item)
    ]


def label_section(item: ui.menu_item) -> ui.item_section:
    return next(c for c in item.default_slot.children if c.text and "side" not in c._props)


def menu_icons(user: User, menu_marker: str) -> list[str]:
    menu = user.find(marker=menu_marker).elements.pop()
    return [
        next(c for c in child.default_slot.children if "avatar" in c._props).default_slot.children[0]._props["name"]
        for child in menu.default_slot.children
        if isinstance(child, ui.menu_item)
    ]
```

`test_the_menus_list_their_items_in_order` の `menu-file-items`・`menu-project-items` の期待値と、アイコンの確認を次にする。

```python
    assert menu_items(user, "menu-file-items") == [
        ("開く", "file-open"),
        ("新規プロジェクト作成", "file-new"),
        ("上書き保存", "save-project"),
        ("名前をつけて保存", "file-save-as"),
        ("祝日を更新", "refresh-holidays"),
    ]
    assert menu_items(user, "menu-project-items") == [
        ("設定", "open-settings"),
        ("メンバーとパラメータ", "open-members-parameters"),
        ("ダッシュボード", "menu-open-dashboard"),
    ]
    assert menu_icons(user, "menu-file-items") == ["folder_open", "note_add", "save", "save_as", "event_repeat"]
    assert menu_icons(user, "menu-project-items") == ["settings", "groups", "dashboard"]
    assert menu_icons(user, "menu-export-items") == ["visibility", "ios_share"]
    assert menu_icons(user, "menu-help-items") == ["keyboard"]
    assert menu_icons(user, "menu-theme-items") == ["brightness_auto", "light_mode", "dark_mode"]
```

水平線の位置と、新規作成・ダッシュボードの動きのテストを足す。

```python
async def test_the_file_menu_separates_open_save_and_update(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    menu = user.find(marker="menu-file-items").elements.pop()
    kinds = ["sep" if isinstance(c, ui.separator) else "item" for c in menu.default_slot.children]
    assert kinds == ["item", "item", "sep", "item", "item", "sep", "item"]


async def test_the_project_menu_dashboard_item_opens_the_dashboard(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    save_cache({}, tmp_path)
    mount_capturing(tmp_path, views)
    await user.open("/")
    user.find(marker="menu-open-dashboard").click()
    assert await wait_until(lambda: views[0].dashboard_kind is not None)


async def test_the_dashboard_menu_item_shows_the_key_hint(user: User, tmp_path: Path) -> None:
    await open_header_view(user, tmp_path)
    menu = user.find(marker="menu-project-items").elements.pop()
    item = next(c for c in menu.default_slot.children if isinstance(c, ui.menu_item) and "menu-open-dashboard" in c._markers)
    assert [c.text for c in item.default_slot.children if "side" in c._props] == ["D"]
```

既存の「新規プロジェクト作成」のテスト(`file-new` を押す)は、メニューの位置に依存しないので、そのまま通る。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "menu"`
Expected: FAIL

- [ ] **Step 3: views.py のメニューを組み替える**

`views.py` の `header_menu` の前(クラスの外、`THEME_ICONS` の近く)に足す。

```python
@dataclass(frozen=True)
class MenuItem:
    """ヘッダーのメニューの 1 項目。keyは、割り当てたショートカットのキー(右端に薄く添える。なければ空)。"""

    text: str
    icon: str
    handler: Callable[[], object]
    marker: str
    key: str = ""
```

(`dataclass` の import がなければ `from dataclasses import dataclass` を足す。)`header` のメニュー定義を次にする。

```python
            self.header_menu(
                "ファイル",
                "menu-file",
                [
                    MenuItem("開く", "folder_open", self.show_file_list, "file-open"),
                    MenuItem("新規プロジェクト作成", "note_add", self.request_new, "file-new"),
                    None,  # 水平線(開く・作る / 保存 / データの更新)
                    MenuItem("上書き保存", "save", self.save_project_clicked, "save-project"),
                    MenuItem("名前をつけて保存", "save_as", self.save_as, "file-save-as"),
                    None,
                    MenuItem("祝日を更新", "event_repeat", self.refresh_holidays, "refresh-holidays"),
                ],
            )
            self.header_menu(
                "プロジェクト",
                "menu-project",
                [
                    MenuItem("設定", "settings", self.open_settings, "open-settings"),
                    MenuItem(
                        "メンバーとパラメータ", "groups", self.open_members_parameters, "open-members-parameters"
                    ),
                    MenuItem("ダッシュボード", "dashboard", self.open_dashboard, "menu-open-dashboard", "D"),
                ],
            )
            self.header_menu(
                "エクスポート",
                "menu-export",
                [
                    MenuItem("チャートプレビュー", "visibility", self.enter_preview, "export-preview"),
                    MenuItem("担当者へ書き出し", "ios_share", self.open_handoff, "export-handoff"),
                ],
            )
            self.header_menu(
                "ヘルプ", "menu-help", [MenuItem("ショートカットヘルプ", "keyboard", self.help_dialog.open, "help-shortcuts")]
            )
```

キーの表示は、spec どおりダッシュボードの `D` だけに添える(ほかの項目は空)。

`header_menu` を次にする。

```python
    def header_menu(self, label: str, marker: str, items: list[MenuItem | None]) -> None:
        """ヘッダーのメニュー。項目のマーカーは、押す操作を指す(None は水平線)。"""
        with ui.button(label, color=None).props("unelevated rounded no-caps").classes("app-menu-btn").mark(marker):
            with ui.menu().props("content-class=app-menu").mark(f"{marker}-items"):
                for item in items:
                    if item is None:
                        ui.separator().mark(f"{marker}-separator")
                        continue
                    self.menu_entry(item.text, item.icon, item.handler, item.marker, item.key)

    @staticmethod
    def menu_entry(text: str, icon: str, handler: Callable[[], object], marker: str, key: str = "") -> ui.menu_item:
        """メニューの 1 項目(左にアイコン、右端にキー)。文言の ItemSection は、menu_item が作る。"""
        with ui.menu_item(text, on_click=handler).mark(marker) as entry:
            with ui.item_section().props("avatar") as avatar:
                ui.icon(icon)
            avatar.move(entry, target_index=0)
            if key:
                ui.item_section(key).props("side").classes("text-caption text-grey")
        return entry
```

`theme_menu` の項目を、`self.menu_entry` で作る(絵は `brightness_auto`・`light_mode`・`dark_mode`)。

```python
                THEME_MENU_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode"}
                for theme in THEMES:
                    item = self.menu_entry(
                        THEME_LABELS[theme], THEME_MENU_ICONS[theme], lambda t=theme: self.set_theme(t), f"theme-{theme}"
                    )
                    if theme == self.theme:
                        item.props("active")
```

(`THEME_MENU_ICONS` は、`THEME_ICONS` の隣に、モジュールの定数として置く。キーが `THEMES` の値と違うなら、`THEMES` に合わせる。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_views.py -q`
Expected: PASS。アイコンの取り出しで落ちたら、`ui.item_section` の `_props` に `avatar` が入るか、`ui.icon` の `_props["name"]` を、小さなスクリプトで確かめてテストを直す。

- [ ] **Step 5: 型検査とコミット**

Run: `uv run ty check src`
Expected: エラーなし

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: メニューを整理し、新規作成をファイルへ、ダッシュボードの項目とアイコンを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ショートカット・ヘルプ・ドキュメント

**Files:**
- Modify: `src/projectapp/shortcuts.py:34-49`(`SHORTCUTS`)
- Modify: `src/projectapp/views.py`(`SHORTCUT_METHODS`:315)
- Test: `test/test_shortcuts.py`、`test/test_views.py`
- Modify: `CLAUDE.md`(`projectapp/`。ヘッダー節)、`docs/development.md`(`forms.py` の行、メニュー)

**Interfaces:**
- Consumes: `MainView.open_members_parameters`(Task 2)
- Produces: `Shortcut("m", "members_parameters", "メンバーとパラメータ", ctrl=True, shift=True)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_shortcuts.py` に足し、`ctrl_keys` の期待値に `"m"` を加える。

```python
def test_members_parameters_shortcut_needs_ctrl_and_shift():
    assert resolve("m", ctrl=True, shift=True, modal=False, screen=Screen.MAIN) == "members_parameters"
    assert resolve("m", ctrl=True, shift=False, modal=False, screen=Screen.MAIN) is None  # Ctrl/Cmd+M は割り当てない
    assert resolve("m", ctrl=True, shift=True, modal=True, screen=Screen.MAIN) is None  # ダイアログが開いているあいだは効かない
    assert resolve("m", ctrl=True, shift=True, modal=False, screen=Screen.DASHBOARD) is None


def test_help_lists_the_members_parameters_shortcut():
    assert ("Ctrl/Cmd+Shift+M", "メンバーとパラメータ") in help_entries()
```

`test/test_views.py` に足す。

```python
async def test_the_shortcut_opens_the_members_parameters_dialog_once(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    save_cache({}, tmp_path)
    mount_capturing(tmp_path, views)
    await user.open("/")
    user.trigger("m", modifiers={"ctrl", "shift"})
    await user.should_see(marker="members-parameters-panels")
    user.trigger("m", modifiers={"ctrl", "shift"})  # 開いているあいだは、二重に開かない
    assert len(user.find(marker="members-parameters-panels").elements) == 1
```

(`user.trigger` の使い方は、既存の `Ctrl+S` などのテストに合わせる。`grep -n "user.trigger" test/test_views.py` で書き方を確かめる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_shortcuts.py test/test_views.py -q -k "members_parameters"`
Expected: FAIL

- [ ] **Step 3: 実装する**

`shortcuts.py` の `SHORTCUTS` の、`settings` の次に足す。

```python
    Shortcut("m", "members_parameters", "メンバーとパラメータ", ctrl=True, shift=True),
```

`views.py` の `SHORTCUT_METHODS` に足す。

```python
        "members_parameters": "open_members_parameters",
```

- [ ] **Step 4: ドキュメントを直す**

`CLAUDE.md`(`projectapp/`)のヘッダー節を直す。

- `ファイル`メニュー: `開く`(ファイル一覧のダイアログ)・`新規プロジェクト作成`・(水平線)・`上書き保存`・`名前をつけて保存`・(水平線)・`祝日を更新`
- `プロジェクト`メニュー: `設定`・`メンバーとパラメータ`・`ダッシュボード`。「メンバーとパラメータ」は 1 つのダイアログのタブで、適用はタブごと(適用しても閉じない。未適用の編集があるタブには`●`)
- 各メニューの項目にアイコンを添える。ダッシュボードの項目には、キー`D`も添える
- キーボードショートカットに`Ctrl/Cmd+Shift+M` メンバーとパラメータ を足す
- 「メイン画面の上部に、1 行のヘッダーを置く(左から、メニュー 4 つ。…)」の記述は、変えない

`docs/development.md` の `forms.py` の行を「メンバーとパラメータのダイアログ(`members_panel`・`parameters_panel`・`open_members_parameters_dialog`。適用後は、プロジェクトから行を作り直す)と検証(`build_members`)」に直し、`views.py` の行に `MenuItem` と `menu_entry` を足す。`ratios.py` の説明に `remap_levels` を足す。

- [ ] **Step 5: 全体の確認**

Run: `uv run pytest -n auto -q && uv run ty check src`
Expected: すべて PASS、型エラーなし

- [ ] **Step 6: 実機の確認**

`run` スキルでアプリを起動して確かめる: ① ファイルメニューの順序・水平線・アイコン・キー表示、② プロジェクトメニューの 3 項目、③ メンバーとパラメータのダイアログでパラメータを足して適用すると、メンバーのタブに列が出る、④ 未適用の編集で`●`が出る、⑤ `Ctrl/Cmd+Shift+M` で開く、⑥ ダイアログの幅が、パラメータの数に応じて変わる。見つけた不具合は、その場で直し、`docs/` の作業記録に残す。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/shortcuts.py src/projectapp/views.py test CLAUDE.md docs/development.md
git commit -m "feat: メンバーとパラメータのショートカットを足し、ドキュメントを直す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
