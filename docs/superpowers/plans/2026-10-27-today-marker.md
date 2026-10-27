# ガントチャートの今日の線 実装計画(要望 71)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートに今日の位置を示す赤い縦線と、今日へ戻る`当日`ボタンを出し、プレビュー・画像・PlantUML にも反映する。

**Architecture:** 位置の計算は`timeline.today_position`(純粋関数。`deadline_position`と同じ範囲判定)。描画は`GanttChart.render`が、格子線と同じ「絶対配置の重ね要素」として 1 本描く。プレビューは`ViewOptions.show_today`・`PreviewSettings.show_today`・表示項目のチェックボックス`今日`で切り替え、PlantUML は`build_plantuml(show_today=)`が今日の日付の列を赤く塗る。

**Tech Stack:** Python 3.13・NiceGUI・pytest(`nicegui.testing.User`)・`ty`

**Spec:** `docs/superpowers/specs/2026-10-27-today-marker-design.md`

## Global Constraints

- 日次の線は今この時刻の位置、週次は今日の日の真ん中(12:00)、月次は今日を含む月の列の真ん中(月内の位置は計算しない)
- 今日が表示範囲の外なら線は出さず、`当日`ボタンは押せない(ホバー`今日は表示期間の外です`)
- 線の色はライト`#e53935`・ダーク`#ff5252`、幅 2px。クリックは通す(`pointer-events: none`)
- `当日`ボタンはプレビュー(読み取り専用)に出さない
- スクロールは、プロジェクトを開いた直後だけ、線がチャート領域の左から 1/4 の位置になるようにする。期間・スケールの変更は今までどおり左端へ戻す
- PlantUML は`YYYY-MM-DD is colored in red`を 1 行足す。イベントの色の行より後ろに置き、期間の外なら足さない
- すべての関数に型ヒント(引数・戻り値)を付ける。コメントは多くても 3 行(`.claude/RULE.md`)
- 検証は`uv run pytest -n auto`と`uv run ty check src`
- ブランチは git-flow に従い`feature/today-marker`(設計書のある`docs/record-request-71`から作る。そのブランチが`develop`へマージ済みなら`develop`から)

## Review Focus

- 範囲の端: `now`が最初の列の 0 時ちょうど(位置 0.0)なら線を出し、最後の列の終端ちょうどなら出さない(例外にしない)
- 日付をまたいで開きっぱなし: 線は描き直すまで古いが、`当日`ボタンは押した時点の`now`で位置を求める
- 期間欄・スケールの変更で今日が範囲の外に出た/戻ったとき、`当日`ボタンの押せる・押せないが追従する
- タスクが 0 件のプロジェクトでも線は出る(行がなくても例外にならない)
- PlantUML で、今日が期間の最終日(含む)・初日のとき行が出る。`show_today`オフ・`show_events`オフの組み合わせでも今日の行は独立に出入りする

---

## File Structure

- `src/projectapp/timeline.py`: `today_position`(純粋関数)を追加
- `src/projectapp/gantt.py`: 色の定数と CSS、`ViewOptions.show_today`、`today_line`、`当日`ボタン、`today_x`・`scroll_to_today`・`scroll_on_open`、`today_scroll_js`
- `src/projectapp/preview.py`: `PreviewSettings.show_today`、`PreviewBar`の`今日`チェックボックス(`read()`の戻り値を 7 要素にする)
- `src/projectapp/plantuml.py`: `build_plantuml(show_today=)`
- `src/projectapp/views.py`: `on_preview_change`・`save_plantuml`・`show_project`の配線
- `test/test_timeline.py`・`test/test_gantt.py`・`test/test_preview.py`・`test/test_views.py`・`test/test_plantuml.py`
- `CLAUDE.md`・`docs/requests.md`・`docs/superpowers/specs/2026-10-27-today-marker-design.md`・`.claude/MEMORY.md`

---

### Task 1: 今日の位置の純粋関数

**Files:**
- Modify: `src/projectapp/timeline.py`(`deadline_position`の直後)
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: `Column`・`_position(moment, columns)`・`Scale`(同ファイル)
- Produces: `today_position(now: datetime, columns: list[Column], scale: Scale) -> float | None`(列の単位の連続値。範囲外は`None`)

- [ ] **Step 1: Write the failing tests**

`test/test_timeline.py`の import に`today_position`を足し(`from projectapp.timeline import (...)`の並びに)、`test_deadline_position_at_the_boundaries`の後ろへ追加する。

```python
def test_today_position_day_follows_the_time_of_day() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert today_position(datetime(2026, 10, 7, 12), columns, Scale.DAY) == 2.5
    assert today_position(datetime(2026, 10, 7, 6), columns, Scale.DAY) == 2.25


def test_today_position_week_is_the_middle_of_the_day() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.WEEK)
    morning = today_position(datetime(2026, 10, 7, 1), columns, Scale.WEEK)
    evening = today_position(datetime(2026, 10, 7, 23), columns, Scale.WEEK)
    assert morning == evening == pytest.approx(2.5 / 7)  # 月曜始まりの水曜の 12:00


def test_today_position_month_is_the_middle_of_the_column() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.MONTH)
    index = next(i for i, c in enumerate(columns) if c.start <= date(2026, 10, 20) < c.end)
    assert today_position(datetime(2026, 10, 2, 9), columns, Scale.MONTH) == index + 0.5
    assert today_position(datetime(2026, 10, 31, 23), columns, Scale.MONTH) == index + 0.5


@pytest.mark.parametrize("scale", [Scale.DAY, Scale.WEEK, Scale.MONTH])
def test_today_position_outside_the_range_is_none(scale: Scale) -> None:
    columns = build_columns(Project("p", base_date=BASE), scale)
    assert today_position(datetime.combine(columns[0].start, time.min) - timedelta(minutes=1), columns, scale) is None
    assert today_position(datetime.combine(columns[-1].end, time.min), columns, scale) is None


def test_today_position_at_the_first_instant_is_zero() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert today_position(datetime.combine(columns[0].start, time.min), columns, Scale.DAY) == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_timeline.py -k today_position -v`
Expected: FAIL(`ImportError: cannot import name 'today_position'`)

- [ ] **Step 3: Implement**

`src/projectapp/timeline.py`の`deadline_position`の直後に追加する。

```python
def today_position(now: datetime, columns: list[Column], scale: Scale) -> float | None:
    """今日の線の位置(列の単位)。範囲の外ならNone。日次は時刻、週次は日の真ん中、月次は列の真ん中。"""
    begin = datetime.combine(columns[0].start, time.min)
    finish = datetime.combine(columns[-1].end, time.min)
    if not begin <= now < finish:
        return None
    if scale is Scale.DAY:
        return _position(now, columns)
    if scale is Scale.WEEK:
        return _position(datetime.combine(now.date(), time(12)), columns)
    for index, column in enumerate(columns):
        if column.start <= now.date() < column.end:
            return index + 0.5
    return None
```

`time`が`datetime.time`クラスとして import されていることを確認する(`time.min`を既に使っている)。`pytest`が`test/test_timeline.py`で import されていなければ足す。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_timeline.py -k today_position -v && uv run ty check src`
Expected: PASS・ty 通過

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "feat: 今日の線の位置を求める純粋関数を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ガントチャートに今日の線を描く

**Files:**
- Modify: `src/projectapp/gantt.py`(定数は`DEADLINE_COLOR`付近、`ViewOptions`、`build`の`ui.add_css`、`render`、`gridlines`の直後にメソッド)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `today_position`(Task 1)、`from_name(px: float) -> str`、`GanttChart.now`・`view_scale`・`options`
- Produces: `ViewOptions.show_today: bool = True`、定数`TODAY_COLOR`・`TODAY_DARK_COLOR`・`TODAY_LINE_WIDTH_PX`・`TODAY_CSS`、マーカー`today-line`の要素

- [ ] **Step 1: Write the failing tests**

`test/test_gantt.py`の import(`from projectapp.gantt import (...)`)に`TODAY_COLOR`・`TODAY_CSS`・`TODAY_DARK_COLOR`・`TODAY_LINE_WIDTH_PX`を、`from projectapp.timeline import`に`today_position`を足す(既にあれば重複させない)。`test_week_scale_has_no_stripes_and_scales_bars`の前に追加する。

```python
NOON = datetime(2026, 10, 7, 12)  # sample_project の開始(10/5)から 2.5 列目


async def test_day_scale_draws_the_today_line_at_the_current_time(user: User) -> None:
    mount(sample_project(), now=NOON)
    await user.open("/")
    line = user.find(marker="today-line").elements.pop()
    assert line._style["left"] == from_name(2.5 * COLUMN_WIDTH_PX[Scale.DAY] - TODAY_LINE_WIDTH_PX / 2)
    assert line._style["width"] == f"{TODAY_LINE_WIDTH_PX}px"
    assert line._style["pointer-events"] == "none"


async def test_week_and_month_scales_draw_the_today_line_in_the_middle(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=NOON)
    await user.open("/")
    for scale in (Scale.WEEK, Scale.MONTH):
        charts[0].set_scale(scale)
        columns = build_columns(charts[0].project, scale, {}, None)
        expected = today_position(NOON, columns, scale) * COLUMN_WIDTH_PX[scale]
        line = user.find(marker="today-line").elements.pop()
        assert line._style["left"] == from_name(expected - TODAY_LINE_WIDTH_PX / 2)


async def test_no_today_line_when_today_is_outside_the_range(user: User) -> None:
    mount(sample_project(), now=datetime(2026, 10, 1))  # 範囲(10/5〜)の前
    await user.open("/")
    await user.should_not_see(marker="today-line")


async def test_no_today_line_when_show_today_is_off(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=NOON)
    await user.open("/")
    await user.should_see(marker="today-line")
    charts[0].set_options(ViewOptions(show_today=False))
    await user.should_not_see(marker="today-line")


async def test_today_line_is_drawn_without_tasks(user: User) -> None:
    mount(Project("empty", base_date=BASE), now=NOON)
    await user.open("/")
    await user.should_see(marker="today-line")


def test_today_line_colors_are_red_in_both_themes() -> None:
    assert TODAY_COLOR in TODAY_CSS and TODAY_DARK_COLOR in TODAY_CSS
    assert "body.body--dark" in TODAY_CSS
```

`Project`・`BASE`・`build_columns`・`Scale`が`test_gantt.py`で import 済みか確認し、なければ足す。

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_gantt.py -k today_line -v`
Expected: FAIL(`ImportError: cannot import name 'TODAY_COLOR'`)

- [ ] **Step 3: Implement**

`src/projectapp/gantt.py`:

(a) `DEADLINE_COLOR`の定義の下に定数を追加し、`from projectapp.timeline import`に`today_position`を足す。

```python
TODAY_COLOR = "#e53935"  # 今日の線。ダークでは明るい赤に替える
TODAY_DARK_COLOR = "#ff5252"
TODAY_COLOR_VAR = "var(--today)"
TODAY_LINE_WIDTH_PX = 2
TODAY_CSS = f":root {{ --today: {TODAY_COLOR}; }}\nbody.body--dark {{ --today: {TODAY_DARK_COLOR}; }}"
```

(b) `ViewOptions`に`show_events`の直後で追加する。

```python
    show_today: bool = True  # 今日の赤い縦線
```

(c) `build`の`ui.add_css(STATUS_CSS)`の下に`ui.add_css(TODAY_CSS)`を足す。

(d) `render`で、`self.event_tints(columns, width, top)`の直後に`self.today_line(columns, width, top)`を足す。

(e) `event_tints`の後ろにメソッドを追加する。

```python
    def today_line(self, columns: list[Column], width: int, top: int) -> None:
        """今日の赤い縦線。年・月の帯の下から最下行まで。クリックは通す。内容は定数と数値だけ。"""
        position = today_position(self.now(), columns, self.view_scale)
        if not self.options.show_today or position is None:
            return
        left = from_name(position * width - TODAY_LINE_WIDTH_PX / 2)
        ui.element("div").style(
            f"position: absolute; top: {top}px; bottom: 0; left: {left};"
            f" width: {TODAY_LINE_WIDTH_PX}px; background: {TODAY_COLOR_VAR};"
            " pointer-events: none; z-index: 1"
        ).mark("today-line")
```

`z-index: 1`は、棒(z-index 未指定)より前、名前の欄(2)・見出し(3)より後ろ、週ごとのチップ(1)とは同じで DOM の後に描かれるチップが前になる。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_gantt.py -k "today_line or today" -v && uv run ty check src`
Expected: PASS・ty 通過

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: ガントチャートに今日の赤い縦線を描く

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `当日`ボタンと、開いた直後のスクロール

**Files:**
- Modify: `src/projectapp/gantt.py`(定数、`__init__`、`build`のツールバー、`render`、スクロール系メソッド)、`src/projectapp/views.py:491`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `today_position`(Task 1)、`GanttChart.view_period`・`reference_values()`・`name_width`・`client`
- Produces: `today_scroll_js(x: float, name_width: int) -> str`、`GanttChart.today_x(columns: list[Column] | None = None) -> float | None`、`scroll_to_today() -> None`、`scroll_on_open() -> None`、マーカー`today-button`

- [ ] **Step 1: Write the failing tests**

`test/test_gantt.py`の import に`today_scroll_js`を足す。`test_set_project_does_not_touch_the_scroll_position`の前後に追加する。

```python
def test_today_scroll_js_puts_the_line_a_quarter_in_from_the_name_column() -> None:
    js = today_scroll_js(400.0, 200)
    assert "[data-chart-scroll]" in js
    assert "400.0 - (el.clientWidth - 200) / 4" in js
    assert "Math.max(0," in js


async def test_today_button_scrolls_to_the_line(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=NOON)
    await user.open("/")
    sent = record_javascript(charts[0])
    user.find(marker="today-button").click()
    assert sent == [today_scroll_js(2.5 * COLUMN_WIDTH_PX[Scale.DAY], charts[0].name_width)]


async def test_today_button_is_disabled_outside_the_range_and_follows_the_period(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=NOON)
    await user.open("/")
    button = user.find(marker="today-button").elements.pop()
    assert button.enabled
    charts[0].set_period((date(2026, 11, 1), date(2026, 11, 30)))
    assert not button.enabled
    charts[0].set_period(None)
    assert button.enabled


async def test_today_button_uses_the_time_of_the_click(user: User) -> None:
    clock = [datetime(2026, 10, 1)]  # 範囲の前から始める
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: clock[0])
        charts.append(chart)
        chart.build()

    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].scroll_to_today()
    assert sent == []  # 範囲の外では何も送らない
    clock[0] = NOON  # 日付をまたいで開きっぱなし
    charts[0].scroll_to_today()
    assert len(sent) == 1


async def test_scroll_on_open_resets_then_goes_to_today(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=NOON)
    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].scroll_on_open()
    assert sent == [SCROLL_RESET_JS, today_scroll_js(2.5 * COLUMN_WIDTH_PX[Scale.DAY], charts[0].name_width)]


async def test_scroll_on_open_stays_at_the_left_when_today_is_outside(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=datetime(2026, 10, 1))
    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].scroll_on_open()
    assert sent == [SCROLL_RESET_JS]


async def test_changing_the_scale_still_resets_to_the_left_not_today(user: User) -> None:
    charts, _ = mount_chart(sample_project(), now=NOON)
    await user.open("/")
    sent = record_javascript(charts[0])
    charts[0].set_scale(Scale.WEEK)
    assert sent == [SCROLL_TO_LEFT_JS]
```

`set_period`が`(date, date) | None`を受けること、`GanttChart`・`Recorder`が import 済みであることを確認する(`set_period`のシグネチャが違えば、テストの呼び出しを実装に合わせる)。

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_gantt.py -k "today_button or today_scroll or scroll_on_open" -v`
Expected: FAIL(`ImportError: cannot import name 'today_scroll_js'`)

- [ ] **Step 3: Implement**

`src/projectapp/gantt.py`:

(a) `SCROLL_RESET_JS`の定義の下に追加する。

```python
def today_scroll_js(x: float, name_width: int) -> str:
    """今日の線が、名前の欄を除いたチャート領域の左から 1/4 の位置に来るよう、横にスクロールする。"""
    return (
        "requestAnimationFrame(() => { const el = document.querySelector('[data-chart-scroll]');"
        f" if (el) el.scrollTo({{left: Math.max(0, {x:.1f} - (el.clientWidth - {name_width}) / 4)}}) })"
    )
```

テストの文字列(`400.0 - (el.clientWidth - 200) / 4`)と一致させる。

(b) `__init__`に`self.today_button: ui.button | None = None`と`self.today_tooltip: ui.tooltip | None = None`を足す(`self.scroll_box`の隣)。

(c) `build`のツールバーで、スケールのトグルの直後(`with ui.column().classes("gap-0 shrink-0"):`の前)にボタンを置く。

```python
            self.today_button = (
                ui.button("当日", icon="today", on_click=self.scroll_to_today)
                .props("flat dense")
                .classes("shrink-0")
                .mark("today-button")
            )
            with self.today_button:
                self.today_tooltip = ui.tooltip("今日の位置へ移ります")
```

(d) スクロール系メソッド(`scroll_to_top`の近く)を追加する。

```python
    def today_x(self, columns: list[Column] | None = None) -> float | None:
        """今日の線のチャート内の横位置(px)。表示範囲の外なら None。"""
        if columns is None:
            columns = build_columns(
                self.project, self.view_scale, self.holidays, self.view_period, self.reference_values()
            )
        position = today_position(self.now(), columns, self.view_scale)
        return None if position is None else position * COLUMN_WIDTH_PX[self.view_scale]

    def scroll_to_today(self) -> None:
        x = self.today_x()
        if self.client is not None and x is not None:
            self.client.run_javascript(today_scroll_js(x, self.name_width))

    def scroll_on_open(self) -> None:
        """別のプロジェクトを開いた直後だけ、先頭に戻してから今日の位置へ移る(範囲の外なら先頭のまま)。"""
        self.reset_scroll()
        self.scroll_to_today()

    def sync_today_button(self, x: float | None) -> None:
        """`当日`ボタンの押せる・押せないと、ホバーの文言を、今日が表示範囲の中かに合わせる。"""
        if self.today_button is None or self.today_tooltip is None:
            return
        self.today_button.set_enabled(x is not None)
        self.today_tooltip.set_text("今日の位置へ移ります" if x is not None else "今日は表示期間の外です")
```

(e) `render`で`columns`を作った直後に`self.sync_today_button(self.today_x(columns))`を足す。

(f) `src/projectapp/views.py`の`show_project`で、`self.gantt.reset_scroll()  # 別のプロジェクトは…`の行を次に置き換える。

```python
        self.gantt.scroll_on_open()  # 別のプロジェクトは、先頭に戻してから今日の位置へ(編集後の再描画では動かさない)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_gantt.py -k "today or scroll" -v && uv run ty check src`
Expected: PASS・ty 通過(既存の`reset_scroll`のテストも通ること)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/gantt.py src/projectapp/views.py test/test_gantt.py
git commit -m "feat: 当日ボタンと、開いた直後に今日へスクロールする動作を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: プレビューの表示項目に`今日`を足す

**Files:**
- Modify: `src/projectapp/preview.py`(`PreviewSettings`、`PreviewBar.build`・`show`・`read`)、`src/projectapp/views.py`(`on_preview_change`)
- Test: `test/test_preview.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `ViewOptions.show_today`(Task 2)
- Produces: `PreviewSettings.show_today: bool = True`(`excluded`の後ろ。位置引数の順を変えない)、`PreviewBar.read() -> tuple[str, str, Scale, bool, bool, bool, bool]`(末尾が`today`)、マーカー`preview-today`

- [ ] **Step 1: Write the failing tests**

`test/test_preview.py`の`test_preview_settings_pass_show_events_to_the_options`の後ろへ。

```python
def test_preview_settings_pass_show_today_to_the_options() -> None:
    settings = PreviewSettings(date(2026, 10, 1), date(2026, 10, 31), Scale.WEEK, show_today=False)
    assert settings.to_options().show_today is False
    assert PreviewSettings(date(2026, 10, 1), date(2026, 10, 31), Scale.WEEK).to_options().show_today is True
```

`test/test_views.py`の`test_unchecking_preview_events_turns_off_the_event_options`の後ろへ。`view_row`を検査しているテスト(1822 行付近)の集合にも`"preview-today"`を足す。

```python
async def test_unchecking_preview_today_turns_off_the_today_line(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    assert view.gantt.options.show_today is True
    user.find(marker="preview-today").elements.pop().set_value(False)
    assert view.gantt.options.show_today is False
    assert view.preview is not None and view.preview.show_today is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_preview.py test/test_views.py -k "show_today or preview_today" -v`
Expected: FAIL(`unexpected keyword argument 'show_today'` など)

- [ ] **Step 3: Implement**

`src/projectapp/preview.py`:

- `PreviewSettings`の`excluded`の後ろに`show_today: bool = True`を足す。
- `to_options`に`show_today=self.show_today,`を足す。
- `PreviewBar.build`で、`self.events = ...`の次の行に`self.today = ui.checkbox("今日", value=True).mark("preview-today")`を足し、`for widget in (...)`の並びに`self.today`を足す。
- `show`で`self.events.set_value(settings.show_events)`の次に`self.today.set_value(settings.show_today)`を足す。
- `read`の戻り値の型を`tuple[str, str, Scale, bool, bool, bool, bool]`にし、末尾に`bool(self.today.value),`を足す。

`src/projectapp/views.py`の`on_preview_change`:

```python
        start_text, end_text, scale, chips, alerts, events, today = self.preview_bar.read()
```

と、`self.preview = PreviewSettings(...)`を次に置き換える。

```python
        self.preview = PreviewSettings(
            start, end, scale, chips, alerts, events, self.preview.excluded, today
        )
```

`self.preview_bar.read()`を呼ぶほかの箇所・テストがあれば、7 要素に合わせる(`grep -rn "\.read()" src test`)。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_preview.py test/test_views.py -v && uv run ty check src`
Expected: PASS・ty 通過

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/preview.py src/projectapp/views.py test/test_preview.py test/test_views.py
git commit -m "feat: プレビューの表示項目に今日の線の切り替えを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: PlantUML に今日の列の色を出す

**Files:**
- Modify: `src/projectapp/plantuml.py:143-200`、`src/projectapp/views.py`(`save_plantuml`)
- Test: `test/test_plantuml.py`

**Interfaces:**
- Consumes: `PreviewSettings.show_today`(Task 4)
- Produces: `build_plantuml(..., show_today: bool = True, ...)`

- [ ] **Step 1: Write the failing tests**

`test/test_plantuml.py`の`test_events_are_colored_cells_and_bars_clipped_to_the_period`の後ろへ。

```python
TODAY = datetime(2026, 10, 14, 9)  # PERIOD(10/12〜10/30)の中


def test_today_is_a_red_colored_day() -> None:
    assert "2026-10-14 is colored in red" in lines(Project("p"), now=TODAY)


def test_today_line_is_omitted_when_off_or_outside_the_period() -> None:
    assert not any("is colored in red" in line for line in lines(Project("p"), now=TODAY, show_today=False))
    assert not any("is colored in red" in line for line in lines(Project("p"), now=datetime(2026, 10, 1)))
    assert not any("is colored in red" in line for line in lines(Project("p"), now=datetime(2026, 10, 31)))


def test_today_is_inclusive_at_both_ends_of_the_period() -> None:
    assert "2026-10-12 is colored in red" in lines(Project("p"), now=datetime(2026, 10, 12, 0, 0))
    assert "2026-10-30 is colored in red" in lines(Project("p"), now=datetime(2026, 10, 30, 23, 59))


def test_today_comes_after_the_event_colors_and_is_independent_of_show_events() -> None:
    event = Event(date(2026, 10, 13), date(2026, 10, 16), "繁忙期", "lightpink", id="e1")
    out = lines(Project("p", events=[event]), now=TODAY)
    assert out.index("2026-10-14 is colored in red") > out.index("2026-10-13 to 2026-10-16 are colored in #ffb6c1")
    off = lines(Project("p", events=[event]), now=TODAY, show_events=False)
    assert "2026-10-14 is colored in red" in off
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_plantuml.py -k today -v`
Expected: FAIL(`unexpected keyword argument 'show_today'`)

- [ ] **Step 3: Implement**

`src/projectapp/plantuml.py`: `build_plantuml`の引数に`show_events`の次で`show_today: bool = True,`を足し、イベントの `if show_events:` ブロックの直前(`event_lines: list[str] = []`の前)ではなく、**ブロックの後ろ**(`def emit`の前)に追加する。

```python
    if show_today and p_start <= now.date() <= p_end:
        head.append(f"{now.date().isoformat()} is colored in red")  # PlantUML は線を引けないので、列を塗る
```

`src/projectapp/views.py`の`save_plantuml`で、`show_events=settings.show_events,`の次に`show_today=settings.show_today,`を足す。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest -n auto && uv run ty check src`
Expected: 全テスト PASS・ty 通過(既存の PlantUML テストが`now`を期間の中にしていて、赤い行が増えて失敗するものがあれば、その`now`を期間の外にするか期待値に行を足す)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/plantuml.py src/projectapp/views.py test/test_plantuml.py
git commit -m "feat: PlantUML に今日の列の色を出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 文書を更新し、実機で確認する

**Files:**
- Modify: `CLAUDE.md`、`docs/requests.md`、`docs/superpowers/specs/2026-10-27-today-marker-design.md`、`.claude/MEMORY.md`

**Interfaces:**
- Consumes: Task 1〜5 の実装

- [ ] **Step 1: CLAUDE.md に仕様を追記する**

「ガントチャート」の節(`ガントチャートは、土日…`の項目の後ろ)に 1 項目を足す。

```markdown
- ガントチャートに、`今日の線`(赤い縦線。ライト`#e53935`・ダーク`#ff5252`・幅 2px)を出す。位置は、日次=今この時刻、週次=今日の日の真ん中、月次=今日を含む月の列の真ん中(月内の位置は計算しない)。年・月の帯の下から最下行まで引き、棒より前・名前の欄より後ろに置く。クリックは通す。今日が表示期間の外なら出さない。描き直すまで動かない(日付をまたぐと古くなる)。ツールバーのスケールの右の`当日`ボタンで、線がチャート領域の左から 1/4 の位置になるまで横にスクロールする(今日が期間の外のときは押せず、ホバーに`今日は表示期間の外です`)。プロジェクトを開いた直後だけ、同じ位置へ自動でスクロールする(期間・スケールの変更は左端へ戻す)。プレビューの表示項目`今日`(既定オン。保存しない)で切り替え、画像にも写る。プレビューに`当日`ボタンはない
```

「PlantUML の出力」の節の末尾の項目の中、イベントの記述の後ろに次を足す。

```markdown
今日が出力の期間の中にあるとき(プレビューの`今日`がオン)、今日の日付を`YYYY-MM-DD is colored in red`で赤く塗る(PlantUML は線を引けないので列の色になる。イベントの色の行より後ろに置く)。
```

- [ ] **Step 2: 設計書の差分を直す**

`docs/superpowers/specs/2026-10-27-today-marker-design.md`の次を直す。
- 状態を`実装済み(実機確認待ち)— 要望 71。`にする。
- 「見出しから最下行まで 1 本描く」を「年・月の帯の下(格子線と同じ位置)から最下行まで 1 本描く」にする。
- 「チップの上には出さない」を「週ごとのチップより後ろ(同じ z-index で、DOM の順でチップが前になる)」にする。

- [ ] **Step 3: 実機(ネイティブ)で確認する**

Run: `uv run projectapp`

- 日次・週次・月次で、赤い線が今日の位置にある(日次は時刻、週次・月次は真ん中)。土日祝・イベントの色の上でも見える。ダークテーマで明るい赤になる。
- `当日`で今日へ移る。期間欄で今日を外すと押せなくなり、ホバーに理由が出る。
- プロジェクトを開いた直後に、線が左から 1/4 の位置に見える。スケール変更では左端へ戻る。
- プレビューで`今日`のオン・オフが効き、画像に線が写り、PlantUML に赤い行が出る(`java`と`/usr/local/lib/plantuml.jar`で描画して今日の列が赤いことを確かめる)。
- 行・棒のドラッグ、セクションのドラッグが従来どおり動く(線が掴めないこと)。

確認できない項目があれば、`docs/requests.md`の要望 71 に「未確認」として書く。

- [ ] **Step 4: 要望と記録を更新する**

`docs/requests.md`の要望 71 の状態を、実装した内容・PR 番号(マージ後)・テスト件数・実機確認の結果に更新する。`.claude/MEMORY.md`の先頭に今回の状況(ブランチ・設計書・計画・未確認の項目)を足す。

- [ ] **Step 5: 全体を検証してコミットする**

Run: `uv run pytest -n auto && uv run ty check src`
Expected: 全テスト PASS・ty 通過

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "docs: 今日の線の仕様と記録を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage**: 位置(Task 1)・描画/`show_today`/色(Task 2)・`当日`/範囲外/開いた直後(Task 3)・プレビュー/画像(Task 4。画像は DOM 撮影なので追加実装なし。Task 6 の実機で確認)・PlantUML(Task 5)・文書(Task 6)。「期間・スケール変更は左端」は Task 3 のテストで固定。
- **Placeholders**: なし。ただし Task 3 の`set_period`の引数形、Task 5 の既存テストへの影響、Task 4 の`read()`の他の呼び出しは、実装時に現物へ合わせる旨を各ステップに書いた。
- **Type consistency**: `today_position(now, columns, scale)`、`today_x(columns=None)`、`today_scroll_js(x, name_width)`、`scroll_on_open`・`scroll_to_today`、`PreviewSettings.show_today`、`read()`の 7 要素、`build_plantuml(show_today=)`は全タスクで一致。
- **Review Focus**: 範囲の端(Task 1・5)、日付またぎ(Task 3)、期間変更への追従(Task 3)、タスク 0 件(Task 2)、PlantUML の端と独立性(Task 5)にそれぞれテストがある。
