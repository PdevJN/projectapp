# プレビューの操作部の見直し Implementation Plan

> **実装後の変更**: 開始日・終了日の 2 欄は 1 つの期間欄(`preview-period`)に統一し、最終レビューの指摘で範囲カレンダーの `OK` の制御を `rangeStart`/`rangeEnd` に変えた。以下のタスクの `add_range_picker(start, end)`・`preview-start`・`preview-end` は当初の案。現在の仕様は設計書を正とする。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プレビューの上部のバーを「表示の設定」と「出力・戻る・保存」の 2 段に分け、期間を範囲カレンダー(ドラッグ)で選べるようにする。

**Architecture:** `preview.py` の `PreviewBar.build` を 2 段の構成に組み替える。範囲の値の解釈は NiceGUI に依存しない純粋関数 `parse_range_value` に切り出し、ダイアログの組み立ては `add_range_picker` に置く。`read()` の戻り値と `MainView` 側(`views.py`)は変えない。

**Tech Stack:** Python 3.13、NiceGUI 3.18(`ui.date` の `range` プロップ)、pytest(`nicegui.testing.user_plugin`)、`ty`。

**Spec:** `docs/superpowers/specs/2026-10-25-preview-bar-design.md`(要望 63・64)

## Global Constraints

- 言語は日本語。画面の文言・コメント・docstring は日本語で、既存の文体に合わせる。
- 期間の検証は変えない: 開始日 ≤ 終了日、年は 2000〜2100(`validate_period`)、列数の上限(`check_column_count`)。範囲外のタスクを期間の端で切る扱いも変えない。
- プレビューの設定は保存しない。`read()` の戻り値は `tuple[str, str, Scale, bool, bool, bool]` のまま。
- 維持するマーカー: `preview-bar`・`preview-start`・`preview-end`・`preview-scale`・`preview-chips`・`preview-alerts`・`preview-events`・`preview-select-all`・`preview-select-count`・`preview-back`・`preview-save`・`preview-plantuml`・`preview-error`・`preview-warning`。
- 足すマーカー: `open-preview-range-picker`・`preview-range-picker`・`preview-range-picker-ok`。廃止するマーカー: `open-preview-start-picker`・`open-preview-end-picker`・`preview-start-picker`・`preview-end-picker`・`preview-start-picker-ok`・`preview-end-picker-ok`(`test/` で使われていないことを確認済み)。
- `task_dialog.add_picker` と `forms.bind_picker` は他の画面が使うので変えない。
- 省略形(`10/15`・`1015`・`20261015`)の整形は `dateinput.parse_date_input` を使い、`roll_forward=False`(過ぎた日でも翌年にしない。表示期間は過去を見るため)。
- テストは `uv run pytest`、型は `uv run ty check`。

## Review Focus

- 範囲カレンダーで 1 日だけ選んだ(`to` がない)状態: `OK` を押せない。押せてしまうと終了日が空になりエラーになる。
- 開始日・終了日の欄が空・不正なときにカレンダーを開く: 例外にせず、選択なしで開く。
- 範囲を選んでキャンセル(`OK` を押さずに閉じる)したとき: 欄の値は変わらない。
- 同じ日を範囲にした(`from` = `to`)とき: 1 日の期間として反映できる。
- 欄を離れたとき、整えられない文字(`abc`)は書き換えず、検証でエラーにする。
- 保存中・保存ボタン無効の状態(`set_save_enabled`)が、2 段目に移したあとも効く。

---

### Task 1: 範囲の値を読む純粋関数

**Files:**
- Modify: `src/projectapp/preview.py`(`validate_period` の後ろに足す)
- Test: `test/test_preview.py`

**Interfaces:**
- Consumes: なし
- Produces: `parse_range_value(value: object) -> tuple[str, str] | None` — `ui.date` の `range` の値(`{'from': 'YYYY-MM-DD', 'to': 'YYYY-MM-DD'}`、1 日だけのときは文字列、未選択は `None`)から `(開始, 終了)` を返す。両端がそろわないものは `None`(OK を押せない状態)。

- [ ] **Step 1: Write the failing test**

`test/test_preview.py` の import に `parse_range_value` を足し、末尾に追加する。

```python
def test_parse_range_value_reads_a_complete_range() -> None:
    assert parse_range_value({"from": "2026-10-01", "to": "2026-10-31"}) == ("2026-10-01", "2026-10-31")


def test_parse_range_value_accepts_the_same_day_as_a_range() -> None:
    assert parse_range_value({"from": "2026-10-05", "to": "2026-10-05"}) == ("2026-10-05", "2026-10-05")


@pytest.mark.parametrize(
    "value",
    [None, "", "2026-10-05", {}, {"from": "2026-10-05"}, {"from": "2026-10-05", "to": ""}, {"to": "2026-10-05"}, 5],
)
def test_parse_range_value_rejects_an_incomplete_selection(value: object) -> None:
    assert parse_range_value(value) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_preview.py -k parse_range_value -v`
Expected: FAIL(`ImportError: cannot import name 'parse_range_value'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/preview.py` の `validate_period` の直後に追加する。

```python
def parse_range_value(value: object) -> tuple[str, str] | None:
    """範囲カレンダーの値を (開始, 終了) にする。1 日だけ選んだとき・未選択のときは None(確定できない)。"""
    if not isinstance(value, dict):
        return None
    start, end = value.get("from"), value.get("to")
    if isinstance(start, str) and isinstance(end, str) and start and end:
        return start, end
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_preview.py -k parse_range_value -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/preview.py test/test_preview.py
git commit -m "feat: 範囲カレンダーの値を読む関数を足す"
```

---

### Task 2: バーを 2 段にし、範囲カレンダーを置く

**Files:**
- Modify: `src/projectapp/preview.py`(`PreviewBar.build`、`add_range_picker` を追加、import)
- Test: `test/test_views.py`(`test_the_preview_starts_with_the_visible_range_and_the_current_scale` の近くに追加)

**Interfaces:**
- Consumes: `parse_range_value`(Task 1)、`forms.bind_picker` は使わない。
- Produces: `add_range_picker(start: ui.input, end: ui.input) -> None` — 2 つの欄の右(`start` の append スロットではなく、`end` の append スロット)に範囲選択のアイコン(マーカー `open-preview-range-picker`)を足す。ダイアログ内の `ui.date`(`range`)のマーカーは `preview-range-picker`、`OK` は `preview-range-picker-ok`。`OK` で 2 つの欄に値を入れ(欄の `on_value_change` が走ってプレビューが描き直される)、閉じる。

- [ ] **Step 1: ui.date の range の値を確かめる(spec の未決事項)**

`test/test_views.py` に、確認用のテストとして次を追加し、実行して `from`/`to` の形を確かめる(形が違えば Task 1 の関数とこの計画を直してから進む)。

```python
async def test_the_range_picker_applies_the_chosen_range_to_the_fields(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="open-preview-range-picker").click()
    picker = user.find(marker="preview-range-picker").elements.pop()
    assert picker.props.get("range") is not None  # 範囲選択のプロップ(値がなくても付く)
    picker.set_value({"from": "2026-10-01", "to": "2026-10-20"})
    user.find(marker="preview-range-picker-ok").click()
    assert user.find(marker="preview-start").elements.pop().value == "2026-10-01"
    assert user.find(marker="preview-end").elements.pop().value == "2026-10-20"
    assert view.preview is not None
    assert (view.preview.start, view.preview.end) == (date(2026, 10, 1), date(2026, 10, 20))
```

Run: `uv run pytest test/test_views.py -k range_picker -v`
Expected: FAIL(マーカー `open-preview-range-picker` が見つからない)。`range` プロップが `props` でどう見えるか(`True` か空文字か)で `assert` を調整してよい。

- [ ] **Step 2: 追加のテストを書く(失敗させる)**

同じ場所に追加する。

```python
async def test_the_range_picker_does_not_apply_a_single_day_and_ok_is_disabled(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    before = (user.find(marker="preview-start").elements.pop().value, user.find(marker="preview-end").elements.pop().value)
    user.find(marker="open-preview-range-picker").click()
    picker = user.find(marker="preview-range-picker").elements.pop()
    picker.set_value("2026-10-09")  # 1 日だけ選んだ状態(to がない)
    assert not user.find(marker="preview-range-picker-ok").elements.pop().enabled
    picker.set_value({"from": "2026-10-09", "to": "2026-10-09"})  # 同じ日を 2 回押した 1 日の範囲
    assert user.find(marker="preview-range-picker-ok").elements.pop().enabled
    user.find(marker="preview-range-picker-ok").click()
    assert view.preview is not None
    assert (view.preview.start, view.preview.end) == (date(2026, 10, 9), date(2026, 10, 9))
    assert before != ("2026-10-09", "2026-10-09")


async def test_closing_the_range_picker_without_ok_keeps_the_fields(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    before = (user.find(marker="preview-start").elements.pop().value, user.find(marker="preview-end").elements.pop().value)
    user.find(marker="open-preview-range-picker").click()
    user.find(marker="preview-range-picker").elements.pop().set_value({"from": "2026-11-01", "to": "2026-11-30"})
    ok = user.find(marker="preview-range-picker-ok").elements.pop()
    dialog = ok.parent_slot.parent.parent_slot.parent  # ボタン → カード → ダイアログ
    assert isinstance(dialog, ui.dialog)
    dialog.close()  # OK を押さずに閉じる(外側のクリックや ESC と同じ)
    assert (user.find(marker="preview-start").elements.pop().value, user.find(marker="preview-end").elements.pop().value) == before
    assert view.preview is not None


async def test_the_range_picker_opens_with_blank_or_invalid_fields(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-start").clear().type("abc")
    user.find(marker="preview-end").clear()
    user.find(marker="open-preview-range-picker").click()
    picker = user.find(marker="preview-range-picker").elements.pop()
    assert picker.value is None
    assert not user.find(marker="preview-range-picker-ok").elements.pop().enabled


async def test_the_preview_bar_has_a_view_row_and_an_output_row(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter())

    def markers_under(marker: str) -> set[str]:
        row = user.find(marker=marker).elements.pop()
        return {m for child in row.descendants() for m in child._markers}

    view_row = markers_under("preview-bar")
    output_row = markers_under("preview-output")
    # 1 段目: 期間・スケール・表示項目。保存・戻る・すべて選択は含まない
    assert {"preview-start", "preview-end", "preview-scale", "preview-chips", "preview-alerts", "preview-events"} <= view_row
    assert not {"preview-back", "preview-save", "preview-plantuml", "preview-select-all"} & view_row
    # 2 段目: 出力の選択と、戻る・保存
    assert {"preview-select-all", "preview-select-count", "preview-back", "preview-save", "preview-plantuml"} <= output_row
    assert not {"preview-start", "preview-end", "preview-scale"} & output_row
```

Run: `uv run pytest test/test_views.py -k "range_picker or view_row" -v`
Expected: すべて FAIL(マーカーがない)

- [ ] **Step 3: Write the implementation**

`src/projectapp/preview.py` の import に `from projectapp.dateinput import parse_date_input` を足す(`task_dialog` から `date_normalizer` は import しない。Task 3 で使う)。`add_picker` の import は不要になるので外す。`PreviewBar` の前に追加:

```python
def add_range_picker(start: ui.input, end: ui.input) -> None:
    """期間の欄の右に、範囲カレンダーを開くアイコンを足す。OK で 2 つの欄に反映する。1 日だけ選んだ間は OK を押せない。"""
    with ui.dialog() as dialog, ui.card():
        picker = ui.date().props("range").mark("preview-range-picker")
        ok = ui.button("OK").mark("preview-range-picker-ok")

    def on_pick(event: object) -> None:
        ok.set_enabled(parse_range_value(picker.value) is not None)

    def open_picker() -> None:
        try:
            current = validate_period(start.value or "", end.value or "")
        except ValueError:
            picker.set_value(None)  # 空・不正・開始が終了より後のときは、選択なしで開く
        else:
            picker.set_value({"from": current[0].isoformat(), "to": current[1].isoformat()})
        on_pick(None)
        dialog.open()

    def apply() -> None:
        chosen = parse_range_value(picker.value)
        if chosen is None:
            return
        start.set_value(chosen[0])
        end.set_value(chosen[1])
        dialog.close()

    picker.on_value_change(on_pick)
    ok.on_click(apply)
    with end.add_slot("append"):
        ui.icon("date_range").classes("cursor-pointer").on("click", open_picker).mark("open-preview-range-picker")
```

`PreviewBar.build` の本体(`with ui.column()...` から `self.warning` まで)を次に置き換える。

```python
        with ui.column().classes("w-full gap-1") as box:
            with ui.row().classes("w-full items-center gap-4").mark("preview-bar"):
                self.start = ui.input("開始日").classes("w-40").mark("preview-start")
                self.end = ui.input("終了日").classes("w-40").mark("preview-end")
                add_range_picker(self.start, self.end)
                self.scale = ui.toggle({s.value: s.value for s in Scale}).mark("preview-scale")
                self.chips = ui.checkbox("チップと進捗", value=True).mark("preview-chips")
                self.alerts = ui.checkbox("予定超過の赤みと割り当て超過の縞", value=True).mark(
                    "preview-alerts"
                )
                self.events = ui.checkbox("イベント", value=True).mark("preview-events")
            with ui.row().classes("w-full items-center gap-4").mark("preview-output"):
                self.select_all = ui.checkbox("すべて選択", value=True).mark("preview-select-all")
                self.select_count = ui.label("").classes("text-caption").mark("preview-select-count")
                ui.space()
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props(
                    "flat"
                ).mark("preview-back")
                self.save_button = ui.button(
                    "画像として保存", icon="image", on_click=lambda: self.on_save()
                ).mark("preview-save")
                self.plantuml_button = ui.button(
                    "PlantUML として保存", icon="code", on_click=lambda: self.on_save_plantuml()
                ).mark("preview-plantuml")
            self.error = ui.label("").classes("text-negative text-caption").mark("preview-error")
            self.warning = ui.label("").classes("text-caption text-grey").mark("preview-warning")
```

`ui.row` は既定で折り返す(`flex-wrap`)ので、狭い画面でも段の中で折り返す。docstring を `"""プレビューの上部のバー。1 段目に期間・スケール・表示項目、2 段目に出力の選択と戻る・保存。"""` に直す。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/test_views.py -k "preview or range_picker or view_row" -v`
Expected: PASS(既存のプレビューのテスト〔期間・スケール・チェック・すべて選択・保存の有効無効〕も通る)

- [ ] **Step 5: 全体の確認**

Run: `uv run pytest -q && uv run ty check`
Expected: すべて PASS、型エラーなし

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/preview.py test/test_views.py
git commit -m "feat: プレビューのバーを2段にして、期間を範囲カレンダーで選べるようにする"
```

---

### Task 3: 期間の欄の省略形を整える

**Files:**
- Modify: `src/projectapp/preview.py`(`PreviewBar.build`)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `dateinput.parse_date_input(text, today, roll_forward)`、`task_dialog.normalize_field(field, normalize)`、`task_dialog.date_normalizer(roll_forward)`。
- Produces: 開始日・終了日の欄を離れたとき、`10/15`・`1015`・`20261015`(全角も)を `YYYY-MM-DD` に整える。年がないときは今年。整えられない文字はそのまま残す。

- [ ] **Step 1: Write the failing test**

`test/test_views.py` の import に `from nicegui import events` を足し(`from nicegui import ui` の行を `from nicegui import events, ui` にする)、次を追加する。`blur` は `test/test_task_dialog.py:2027` と同じ作りで、User のシミュレーションにはフォーカス移動がないため、blur のハンドラを直接呼ぶ。

```python
def blur(user: User, marker: str) -> None:
    """入力欄を離れたときの処理(blur)を呼ぶ。User のシミュレーションには、フォーカスの移動がないため。"""
    element = user.find(marker=marker).elements.pop()
    for listener in element._event_listeners.values():
        if listener.type == "blur":
            events.handle_event(
                listener.handler, events.GenericEventArguments(sender=element, client=element.client, args={})
            )


async def test_the_preview_period_fields_normalize_abbreviated_dates_on_blur(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("projectapp.task_dialog.today", lambda: date(2026, 10, 12))
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-start").clear().type("10/08")  # 過ぎた日でも翌年にしない
    blur(user, "preview-start")
    assert user.find(marker="preview-start").elements.pop().value == "2026-10-08"
    user.find(marker="preview-end").clear().type("２０２６１２３１")  # 全角
    blur(user, "preview-end")
    assert user.find(marker="preview-end").elements.pop().value == "2026-12-31"
    assert view.preview is not None
    assert (view.preview.start, view.preview.end) == (date(2026, 10, 8), date(2026, 12, 31))


async def test_the_preview_period_field_keeps_text_it_cannot_normalize(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-start").clear().type("abc")
    blur(user, "preview-start")
    assert user.find(marker="preview-start").elements.pop().value == "abc"
    assert "日付の形式が正しくありません" in user.find(marker="preview-error").elements.pop().text
    assert view.preview is not None
```

Run: `uv run pytest test/test_views.py -k "normalize_abbreviated or cannot_normalize" -v`
Expected: FAIL(blur しても整形されない)

- [ ] **Step 2: Write minimal implementation**

`preview.py` の import に `from projectapp.task_dialog import date_normalizer, normalize_field` を足し(既存の `add_picker` の import を置き換える)、`build` の `add_range_picker(...)` の直後に追加:

```python
                for field in (self.start, self.end):
                    field.on("blur", lambda _e, field=field: normalize_field(field, date_normalizer(False)))
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest test/test_views.py -k "preview" -v && uv run pytest -q && uv run ty check`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/projectapp/preview.py test/test_views.py
git commit -m "feat: プレビューの期間の欄で、日付の省略形を整える"
```

---

### Task 4: 仕様と記録の更新

**Files:**
- Modify: `CLAUDE.md`(プロジェクト直下。「ガントチャート」節のプレビューの項目)
- Modify: `docs/requests.md`(要望 63・64 の状態)
- Modify: `docs/request-history.md`(要望 63・64 の行。末尾の表の形式に合わせる)
- Modify: `docs/superpowers/README.md`(表に行を足す)
- Modify: `docs/superpowers/specs/2026-10-25-preview-bar-design.md`(状態を「実装済み(実機確認待ち)」に)
- Modify: `docs/work-log.md`(末尾に項目を足す。書式は既存の項目に合わせる)

**Interfaces:** なし(文書のみ)。

- [ ] **Step 1: CLAUDE.md を更新する**

「ヘッダーの`エクスポート`メニューの「チャートプレビュー」で、プレビューモード…」の項目に、次を足す。「プレビューの上部のバーは 2 段で、1 段目に期間・スケール・表示項目、2 段目に出力の選択(すべて選択と件数)と戻る・保存を置く。期間は開始日・終了日の入力欄(`10/15`・`1015`・`20261015` でも書け、欄を離れたときに`YYYY-MM-DD`に整える。過ぎた日でも翌年にしない)と、欄の右の範囲カレンダー(ドラッグまたは 2 回クリックで開始日と終了日をまとめて決め、`OK`で反映する。1 日だけ選んだ間は`OK`を押せない)で決める」。

- [ ] **Step 2: 記録を更新する**

- `docs/requests.md`: 63・64 の「状態」を「実装済み(実機確認待ち)」にする。
- `docs/request-history.md`: 63・64 の行を、既存の行の列(要望・内容・状態・期間・ブランチ名・マージ・メモ)に合わせて足す。マージの欄は `未マージ(feature/preview-bar)`。
- `docs/superpowers/README.md`: 表に `| 2026-10-25 | プレビューの操作部の見直し | [設計](specs/2026-10-25-preview-bar-design.md) | [計画](plans/2026-10-25-preview-bar.md) | 要望 63・64 | 未マージ(`feature/preview-bar`) | — |` を足す。
- 設計書の先頭の状態行を `> **状態**: 実装済み(実機確認待ち)— 要望 63・64。現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) に反映済み。` にする。
- `docs/work-log.md`: 末尾に、日付・ブランチ・変更の要約・テスト件数(`uv run pytest -q` の件数)・実機確認が必要な点(範囲カレンダーのドラッグ操作、2 段のバーの折り返し)を、既存の項目の書式で足す。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs
git commit -m "docs: プレビューの操作部の見直し(要望63・64)を記録する"
```

---

## Self-Review

- **Spec coverage:** 2 段のバー(Task 2)、範囲カレンダー・OK の無効化・初期選択・空/不正での開き方(Task 2)、省略形の整形(Task 3)、検証と範囲外の扱いは変更なし(Global Constraints)、マーカーの増減(Global Constraints と Task 2)、文書(Task 4)。見送り項目は実装しない。
- **Placeholder scan:** TBD・未確定の雛形なし。マーカーの列挙は `element._markers`(`test/test_gantt.py:1361` と同じ)、blur の発火は `test/test_task_dialog.py:2027` と同じ作り。
- **Type consistency:** `parse_range_value(value: object) -> tuple[str, str] | None`(Task 1)を `add_range_picker`(Task 2)が使う。`add_range_picker(start: ui.input, end: ui.input) -> None`。`read()` の戻り値は不変。
- **Review Focus:** 1 日だけ選んだ状態(Task 2 の 2 つ目のテスト)、空・不正な欄で開く(同 4 つ目)、OK なしで閉じる(同 3 つ目)、同じ日の範囲(同 2 つ目)、整えられない文字(Task 3)、保存ボタンの無効化(既存のテストが 2 段目でも通ることで確認。Task 2 Step 4)。
