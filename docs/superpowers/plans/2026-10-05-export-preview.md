# エクスポートとプレビュー Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メイン画面をプレビューモード(読み取り専用。期間・スケール・表示項目を選べる)に切り替えられ、プレビューの内容を PNG 画像として保存できる。

**Architecture:** 同じ `GanttChart` を、表示の設定 `ViewOptions`(期間・スケール・チップ・赤みと縞・読み取り専用)で描き直す(別インスタンスは作らない。マーカーとスクロール枠が重複せず、スクロール位置と絞り込みが保たれる)。画像化は、同梱した html-to-image を WKWebView 内で動かし、PNG の base64 を Python に返す。画像化と保存先の選択は、差し替えられる部品 `ImageExporter` に切り出す。純粋な部分(倍率、ファイル名、デコード、書き込み、期間の検証)は `export.py`、プレビューのバーの UI は `preview.py`、切り替えと保存の流れは `MainView` に置く。

**Tech Stack:** Python 3.13、NiceGUI(native)、pywebview、html-to-image 1.11.11(MIT)、pytest(`nicegui.testing.User`)、`uvx ty check src`

**Spec:** `docs/superpowers/specs/2026-10-05-export-preview-design.md`

## Global Constraints

- 言語は日本語。画面の文言・エラーは日本語。
- プロジェクトファイルの保存形式は変えない。プレビューの設定は保存しない(プレビューを開くたびに初期値)。
- 通常の画面の描画は変えない(`ViewOptions()` の既定値が、今までと同じ描画になる)。
- Safari 系のキャンバスは幅 16,384px まで: 倍率は `min(2, 16384 / 幅)`。倍率 1 でも超えるときは、保存はできるようにして、警告を出す。
- プレビューで隠す編集用の部品は、アイコン付きのもの(アイコンのフォントは画像に埋め込まれない)をすべて含む。
- 期間は、開始日・終了日を含む(`[開始日, 終了日 + 1 日)`)。列の数の下限(`MIN_COLUMNS`)は守る。期間と重ならない棒(予定・実績・区間の点線・進捗の塗り)は描かない(期間を指定したときだけ)。行(タスク名)は残す。
- 年は `MIN_YEAR`〜`MAX_YEAR`(2000〜2100)。
- テストは `uv run pytest -q`(全体は約4分。タスク中は対象のファイルだけ)、型は `uvx ty check src`。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- 作業ブランチは `feature/export-preview`(`develop` から切ってある)。マージとプッシュは、ユーザーの許可を得てから。

## 設計書からの変更(計画時の判断)

- `ViewOptions` に `scale: Scale | None = None` を足す(`None` はツールバーのスケール)。プレビューのスケールを、メイン画面のスケール(`GanttChart.scale`、ツールバーのトグル)と分けて持つためで、プレビューを出ても、ツールバーのトグルと値がずれない。設計書の「プレビューで変えても、メイン画面には戻さない」を、そのまま満たす。
- 戻るとき、プレビューのスケールがメイン画面のスケールと違っていたら、横のスクロール位置は先頭に戻る(スケールを変えると列の幅が変わるため。`set_scale` と同じ扱い)。同じなら、横も縦も保たれる。設計書の「スクロール位置はそのまま」は、同じスケールのときに成り立つ。
- 静的ファイル(html-to-image)の登録は、テストごとにアプリが作り直されるため、`main()` から一度だけ行う(`export.register_static_files`)。

## Review Focus

- 期間の指定で、期間の端をまたぐ棒は、端で切って描く。期間の外にある棒は、端に細い棒を出さない(予定・実績・点線)。→ Task 2
- 通常の描画(`ViewOptions()` 既定)は、今までと同じ(既存のテストが、そのまま通る)。→ Task 2, 3
- 読み取り専用のとき、編集の部品がなく、クリックもドラッグもできない。→ Task 3
- 開始日が終了日より後、日付の形式の誤り、年の範囲外のとき、保存できず、理由が出る。→ Task 4, 5
- 保存の途中で失敗(画像化の失敗、書き込みの失敗)しても、プレビューに留まり、書きかけのファイルが残らない。二重に押せない。→ Task 4, 5
- プレビューから戻ったとき、通常のヘッダー・ツールバーが戻り、絞り込みが保たれる。ESC で戻る。→ Task 5
- ネイティブウィンドウでない環境では、保存ボタンが無効で理由が出る。→ Task 5

---

### Task 1: 期間つきの列の計算(`timeline.py`)

**Files:**
- Modify: `src/projectapp/timeline.py`(`build_columns` の `period` 引数、重なりの判定 `in_range`)
- Test: `test/test_timeline.py`

**Interfaces:**
- Produces:
  - `build_columns(project, scale, holidays=None, period: tuple[date, date] | None = None) -> list[Column]`(`period` は、開始日・終了日を含む。`period[0] > period[1]` は `ValueError`)
  - `in_range(start: datetime, end: datetime, columns: list[Column]) -> bool`(棒が、列の範囲と重なるか。幅 0 は、位置が範囲内のときだけ。逆順でも落ちない)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py` のインポートに `in_range` を足し(`from projectapp.timeline import (...)`)、末尾に追加する(`date`、`datetime`、`Project`、`Scale`、`build_columns`、`pytest` は既存。なければ足す)。

```python
def test_period_sets_the_first_and_last_columns() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 5)), Scale.DAY, period=(date(2026, 10, 6), date(2026, 10, 8)))
    assert columns[0].start == date(2026, 10, 6)
    assert len(columns) == 42  # 下限(MIN_COLUMNS)は守る


def test_period_includes_the_end_date_beyond_the_minimum() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 5)), Scale.DAY, period=(date(2026, 10, 1), date(2026, 12, 31)))
    assert columns[0].start == date(2026, 10, 1)
    assert columns[-1].start == date(2026, 12, 31)  # 終了日の列まで含む
    assert columns[-1].end == date(2027, 1, 1)


def test_period_for_week_and_month_scales() -> None:
    project = Project("p", base_date=date(2026, 10, 5))
    weeks = build_columns(project, Scale.WEEK, period=(date(2026, 10, 7), date(2026, 12, 31)))
    assert weeks[0].start == date(2026, 10, 5)  # 月曜に合わせる
    assert weeks[-1].end >= date(2027, 1, 1)
    months = build_columns(project, Scale.MONTH, period=(date(2026, 10, 7), date(2027, 3, 1)))
    assert months[0].start == date(2026, 10, 1)
    assert months[-1].start >= date(2027, 3, 1)


def test_without_a_period_the_columns_are_unchanged() -> None:
    project = Project("p", base_date=date(2026, 10, 5))
    assert build_columns(project, Scale.DAY) == build_columns(project, Scale.DAY, None)


def test_a_reversed_period_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_columns(Project("p", base_date=date(2026, 10, 5)), Scale.DAY, period=(date(2026, 10, 9), date(2026, 10, 8)))


def test_a_one_day_period_is_allowed() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 5)), Scale.DAY, period=(date(2026, 10, 8), date(2026, 10, 8)))
    assert columns[0].start == date(2026, 10, 8)


def _columns() -> list:  # 10/6 から 42 日
    return build_columns(Project("p", base_date=date(2026, 10, 5)), Scale.DAY, period=(date(2026, 10, 6), date(2026, 10, 8)))


def test_in_range_for_bars_inside_overlapping_and_outside() -> None:
    cols = _columns()  # [10/6 0:00, 11/17 0:00)
    assert in_range(datetime(2026, 10, 7), datetime(2026, 10, 8), cols)
    assert in_range(datetime(2026, 10, 5, 12), datetime(2026, 10, 6, 12), cols)  # 左端をまたぐ
    assert in_range(datetime(2026, 11, 16, 12), datetime(2026, 11, 18), cols)  # 右端をまたぐ
    assert not in_range(datetime(2026, 10, 1), datetime(2026, 10, 6), cols)  # 終了がちょうど左端
    assert not in_range(datetime(2026, 11, 17), datetime(2026, 11, 20), cols)  # 開始がちょうど右端
    assert not in_range(datetime(2026, 9, 1), datetime(2026, 9, 5), cols)


def test_in_range_for_zero_length_and_reversed_bars() -> None:
    cols = _columns()
    assert in_range(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 9), cols)
    assert not in_range(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 9), cols)
    assert in_range(datetime(2026, 10, 8), datetime(2026, 10, 7), cols)  # 逆順(手編集)でも落ちない
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_timeline.py -q -k "period or in_range"`
Expected: FAIL(`ImportError: cannot import name 'in_range'`)

- [ ] **Step 3: 実装する**

`timeline.py`: `build_columns` を次に置き換える。

```python
def build_columns(
    project: Project,
    scale: Scale,
    holidays: dict[date, str] | None = None,
    period: tuple[date, date] | None = None,
) -> list[Column]:
    """列を作る。period は [開始日, 終了日](終了日を含む)。None は、基準日とバーから決めた表示範囲。"""
    if period is None:
        start, end = visible_range(project, holidays)
    else:
        if period[0] > period[1]:
            raise ValueError("期間の開始日が終了日より後です")
        start, end = period[0], period[1] + timedelta(days=1)
    if scale is Scale.WEEK:
        return _week_columns(start, end)
    if scale is Scale.MONTH:
        return _month_columns(start, end)
    return _day_columns(start, end)
```

`bar_span` の下に追加する。

```python
def in_range(start: datetime, end: datetime, columns: list[Column]) -> bool:
    """棒が、列の範囲と重なるか。幅 0 の棒は、位置が範囲内のときだけ。逆順(手編集)でも落ちない。"""
    begin = datetime.combine(columns[0].start, time.min)
    finish = datetime.combine(columns[-1].end, time.min)
    first, last = sorted((start, end))
    if first == last:
        return begin <= first < finish
    return first < finish and last > begin
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_timeline.py -q`
Expected: PASS

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "期間を指定して列を作れるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 表示の設定 `ViewOptions`(期間・スケール・チップ・赤みと縞)(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`ViewOptions`、`GanttChart.options`、`view_scale`、`set_options`、`render`、`task_row`、`actual_bars`、`overload_stripes`、`stripes`、`header`、`label_row`)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `build_columns(..., period)`、`in_range`(Task 1)
- Produces:
  - `ViewOptions(period: tuple[date, date] | None = None, scale: Scale | None = None, show_chips: bool = True, show_alerts: bool = True, read_only: bool = False)`(`frozen` の `dataclass`)。`read_only` の挙動は Task 3
  - `GanttChart.options: ViewOptions`、`GanttChart.view_scale -> Scale`(`options.scale or self.scale`)、`GanttChart.set_options(options: ViewOptions) -> None`(再描画。スケールが変わったら、横のスクロールを先頭へ)
  - 描画の変更: 期間があるとき、期間と重ならない予定の棒・実績・区間の点線・進捗の塗り・状態の印を描かない

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` のインポートに `ViewOptions`(`from projectapp.gantt import (...)`)、`date` を確認して、末尾に追加する(`mount`、`sample_project`、`BASE`、`Project`、`Section`、`Task`、`Actual`、`Member`、`OVERDUE_COLOR`、`overloaded_project` は既存)。

```python
def mount_with(project: Project, options: ViewOptions, now: datetime = datetime(2026, 10, 1)) -> None:
    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, Recorder().actions, now=lambda: now)
        chart.options = options
        chart.build()


def test_view_options_defaults_mean_today_s_chart() -> None:
    options = ViewOptions()
    assert (options.period, options.scale, options.show_chips, options.show_alerts, options.read_only) == (
        None, None, True, True, False,
    )


async def test_period_sets_the_first_column_and_clips_bars_at_the_edge(user: User) -> None:
    mount_with(sample_project(), ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 8))))
    await user.open("/")
    await user.should_see(marker="col-2026-10-06")
    await user.should_not_see(marker="col-2026-10-05")
    bar = user.find(marker="bar-0-0").elements.pop()  # 10/5 12:00 → 10/7 12:00。左は端で切る
    assert bar._style["left"] == "200.0px"
    assert bar._style["width"] == "60.0px"  # 10/6 0:00 から 10/7 12:00 = 1.5 日 * 40


async def test_bars_outside_the_period_are_not_drawn_but_the_rows_stay(user: User) -> None:
    outside = Task(
        "範囲外",
        planned_start=datetime(2026, 9, 20),
        planned_end=datetime(2026, 9, 22),
        deadline=datetime(2026, 9, 25),
        actuals=[
            Actual(datetime(2026, 9, 20, 9), datetime(2026, 9, 20, 12)),
            Actual(datetime(2026, 9, 21, 9), datetime(2026, 9, 21, 12)),
        ],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [outside])])
    mount_with(project, ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 8))))
    await user.open("/")
    await user.should_see(marker="task-0-0")  # 行は残る
    for marker in ("bar-0-0", "actual-0-0-0", "actual-0-0-1", "actual-gap-0-0-0", "deadline-0-0", "progress-state-0-0"):
        await user.should_not_see(marker=marker)


async def test_actual_bars_and_gap_lines_inside_the_period_are_kept(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 6),
        planned_end=datetime(2026, 10, 9),
        actuals=[
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12)),
            Actual(datetime(2026, 10, 8, 9), datetime(2026, 10, 8, 12)),
        ],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [task])])
    mount_with(project, ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 10))))
    await user.open("/")
    for marker in ("bar-0-0", "actual-0-0-0", "actual-0-0-1", "actual-gap-0-0-0"):
        await user.should_see(marker=marker)


async def test_preview_scale_is_separate_from_the_toolbar_scale(user: User) -> None:
    mount_with(sample_project(), ViewOptions(scale=Scale.WEEK))
    await user.open("/")
    assert user.find(kind=ui.toggle).elements.pop().value == Scale.DAY  # ツールバーは変わらない
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["width"] != "80.0px"  # 週次の幅で描かれる(日次なら 2.0 日 * 40 = 80px)
    await user.should_not_see(marker="stripes")  # 土日の背景は日次だけ


async def test_show_chips_false_hides_the_chips_and_progress(user: User) -> None:
    task = Task("設計", project_code="PRJ-1", assignee="山", status=Status.DONE)
    project = Project("demo", base_date=BASE, sections=[Section("開発", [task])])
    mount_with(project, ViewOptions(show_chips=False))
    await user.open("/")
    await user.should_see(marker="task-name-0-0")
    for marker in ("task-code-0-0", "task-assignee-0-0", "task-progress-0-0"):
        await user.should_not_see(marker=marker)


async def test_show_alerts_false_hides_the_overdue_tint(user: User) -> None:
    mount_with(sample_project(), ViewOptions(show_alerts=False), now=datetime(2026, 10, 8))
    await user.open("/")
    cell = user.find(marker="task-0-0").elements.pop()
    assert "background-image" not in cell._style
    assert user.find(marker="row-0-0").elements.pop()._style.get("background") is None


async def test_show_alerts_false_hides_the_overload_stripes(user: User) -> None:
    mount_with(overloaded_project(), ViewOptions(show_alerts=False))
    await user.open("/")
    await user.should_see(marker="bar-top-0")
    await user.should_not_see(marker="overload-top-0-0")


async def test_alerts_are_shown_by_default(user: User) -> None:
    mount_with(overloaded_project(), ViewOptions())
    await user.open("/")
    await user.should_see(marker="overload-top-0-0")


async def test_set_options_rerenders_and_scrolls_left_only_when_the_scale_changes(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    await user.open("/")
    chart = charts[0]
    chart.set_options(ViewOptions(period=(date(2026, 10, 6), date(2026, 10, 8))))
    await user.should_not_see(marker="col-2026-10-05")
    assert chart.view_scale is Scale.DAY
    chart.set_options(ViewOptions(scale=Scale.MONTH))
    assert chart.view_scale is Scale.MONTH
    assert chart.scale is Scale.DAY
    chart.set_options(ViewOptions())
    await user.should_see(marker="col-2026-10-05")
```

(`Status`、`ui`、`GanttChart`、`Recorder`、`Scale` が未インポートなら足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "view_options or period or outside_the_period or preview_scale or show_chips or show_alerts or alerts_are_shown or set_options"`
Expected: FAIL(`ImportError: cannot import name 'ViewOptions'`)

- [ ] **Step 3: 実装する**

`gantt.py`: `from projectapp.timeline import (...)` に `in_range` を足す。定数の並び(`PRIORITY_CSS` の下)に追加する。

```python
@dataclass(frozen=True)
class ViewOptions:
    """ガントチャートの表示の設定。既定値が、通常の画面と同じ描画になる。"""

    period: tuple[date, date] | None = None  # 表示する期間 [開始日, 終了日]。None は、基準日とバーから決める
    scale: Scale | None = None  # None は、ツールバーのスケール
    show_chips: bool = True  # 名前欄のチップと進捗
    show_alerts: bool = True  # 予定超過の赤みと、割り当て超過の縞
    read_only: bool = False  # 編集の部品・クリック・ドラッグをなくす(Task 3)
```

`GanttChart.__init__` に `self.options = ViewOptions()` を足す。`set_scale` の下に追加する。

```python
    @property
    def view_scale(self) -> Scale:
        """描画に使うスケール。プレビューで指定されていればそれ、なければツールバーのスケール。"""
        return self.options.scale or self.scale

    def set_options(self, options: ViewOptions) -> None:
        """表示の設定を変えて、描き直す。描画のスケールが変わるときは、横のスクロールを先頭へ戻す。"""
        before = self.view_scale
        self.options = options
        self.render.refresh()
        if self.view_scale != before:
            self.scroll_to_left()  # 列の幅が変わるので、横の位置は意味を持たない(縦は保つ)
```

描画の中の `self.scale` を、`self.view_scale` に置き換える。対象は次のとおり(`grep -n "self.scale" src/projectapp/gantt.py` で見つける)。`handle_shift` の `self.scale is not Scale.DAY`(行 289 付近)、`set_scale`、`build` のトグルの `value=self.scale` は**置き換えない**(ツールバーのスケール)。置き換えるのは、`render`(`build_columns`、`COLUMN_WIDTH_PX`、`top`、`stripes` の判定)、`header`(`Scale.MONTH` の判定)、`label_row`(`Scale.DAY` の判定、2 か所)、`task_row` の `draggable = self.scale is Scale.DAY`。`handle_shift` は、`self.view_scale is not Scale.DAY` に直す(プレビューの日次以外では移動を無視する)。

`render` の `columns = build_columns(self.project, self.scale, self.holidays)` を、`columns = build_columns(self.project, self.view_scale, self.holidays, self.options.period)` にする。

`task_row` を次のように変える。

- `overdue = is_overdue(...)` の直後に `overdue = overdue and self.options.show_alerts`。
- `self.task_chips(key, ti, task)` を、`if self.options.show_chips:` の中にする。
- 予定の棒(`span = bar_span(...)` から `self.progress_marker(...)` まで)を、`if span is not None and self.bar_visible(task.planned_start, end, columns):` の中にする(`span` の判定を置き換える)。
- `self.overload_stripes(...)` の呼び出しを、`if self.options.show_alerts:` の中にする。

`GanttChart` に追加する。

```python
    def bar_visible(
        self, start: datetime | None, end: datetime | None, columns: list[Column]
    ) -> bool:
        """棒を描くか。期間を指定したときだけ、期間と重ならない棒を描かない(端に細い棒を出さない)。"""
        if self.options.period is None or start is None or end is None:
            return True
        return in_range(start, end, columns)
```

`actual_bars` を変える。区間の棒のループで、`finish` を決めたあとに `if not self.bar_visible(actual.start, finish, columns): continue` を足す(`n` の番号は、`enumerate` のまま保つ)。点線のループで、`before.end is None or after.start <= before.end` の判定の直後に `if not self.bar_visible(before.end, after.start, columns): continue` を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py test/test_gantt_drag.py -q`
Expected: PASS(新しいテストと、既存の描画のテストの両方)

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "ガントチャートに、期間・スケール・チップ・赤みと縞の表示の設定を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 読み取り専用と、ツールバーの切り替え(`gantt.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`edit_on_click`、`drag_props`、`task_row`、`top_add_row`、`section_rows`、`build`、`set_options`、`content_width`、`render` の `data-chart-content`)
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes: `ViewOptions.read_only`(Task 2)
- Produces:
  - `GanttChart.edit_on_click(element, si, ti)`(`read_only` でなければ、クリックで編集を呼ぶ)
  - `GanttChart.toolbar: ui.row | None`(`set_options` が、`read_only` のとき隠す)
  - `GanttChart.content_width() -> int`(描画の全体の幅 px。`NAME_WIDTH_PX + 列の幅 × 列の数`)
  - 描画の中身の要素に、属性 `data-chart-content`(画像化の対象)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の末尾に追加する(`mount_with`、`click_listeners` は Task 2・既存。`sample_project`、`Recorder` 既存)。

```python
async def test_read_only_removes_the_edit_parts(user: User) -> None:
    mount_with(sample_project(), ViewOptions(read_only=True))
    await user.open("/")
    for marker in ("add-task-top", "add-task-0", "top-end"):
        await user.should_not_see(marker=marker)
    await user.should_see(marker="section-name-0")  # セクションの見出しは残る
    await user.should_see(marker="task-0-0")


async def test_read_only_hides_the_toolbar_and_set_options_restores_it(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    await user.open("/")
    chart = charts[0]
    assert chart.toolbar is not None and chart.toolbar.visible
    chart.set_options(ViewOptions(read_only=True))
    assert not chart.toolbar.visible
    chart.set_options(ViewOptions())
    assert chart.toolbar.visible


async def test_read_only_has_no_click_handlers_and_no_drag_attributes(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 7, 12),
        deadline=datetime(2026, 10, 9),
        actuals=[
            Actual(datetime(2026, 10, 5, 12), datetime(2026, 10, 6, 12)),
            Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
        ],
    )
    project = Project("demo", base_date=BASE, sections=[Section("開発", [task])])
    mount_with(project, ViewOptions(read_only=True))
    await user.open("/")
    for marker in ("task-0-0", "bar-0-0", "actual-0-0-0", "actual-gap-0-0-0", "deadline-0-0"):
        assert click_listeners(user.find(marker=marker).elements.pop()) == [], marker
    cell = user.find(marker="task-0-0").elements.pop()
    assert "draggable" not in cell.props and "data-drag-handle" not in cell.props
    bar = user.find(marker="bar-0-0").elements.pop()
    assert "data-bar" not in bar.props
    assert "data-drop" not in user.find(marker="row-0-0").elements.pop().props
    assert "data-drop" not in user.find(marker="section-0").elements.pop().props


async def test_the_edit_handlers_are_kept_when_not_read_only(user: User) -> None:
    recorder = mount(sample_project())
    await user.open("/")
    user.find(marker="bar-0-0").click()
    user.find(marker="task-0-1").click()
    assert recorder.events == [("edit_task", (0, 0)), ("edit_task", (0, 1))]


async def test_content_width_and_the_content_attribute(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(sample_project(), {}, Recorder().actions, now=lambda: datetime(2026, 10, 1))
        charts.append(chart)
        chart.build()

    await user.open("/")
    chart = charts[0]
    columns = build_columns(chart.project, Scale.DAY, {})
    assert chart.content_width() == NAME_WIDTH_PX + COLUMN_WIDTH_PX[Scale.DAY] * len(columns)
    content = user.find(marker="chart-content").elements.pop()
    assert "data-chart-content" in content.props
    assert content._style["width"] == f"{chart.content_width()}px"
    chart.set_options(ViewOptions(scale=Scale.WEEK))
    weeks = build_columns(chart.project, Scale.WEEK, {})
    assert chart.content_width() == NAME_WIDTH_PX + COLUMN_WIDTH_PX[Scale.WEEK] * len(weeks)
```

(`click_listeners` は、同じファイルに既にある。`build_columns`、`NAME_WIDTH_PX`、`COLUMN_WIDTH_PX` が未インポートなら足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_gantt.py -q -k "read_only or edit_handlers_are_kept or content_width"`
Expected: FAIL(`add-task-top` がまだ見える、`toolbar` 属性がない、など)

- [ ] **Step 3: 実装する**

`gantt.py`:

(a) `GanttChart.__init__` に `self.toolbar: ui.row | None = None` を足す。`build` のツールバーの `with ui.row()...mark("chart-toolbar"):` を、`self.toolbar = ui.row()...` と `with self.toolbar.mark("chart-toolbar"):` の 2 行に分ける(中身は変えない)。

(b) `set_options` の `self.options = options` の直後に、次を足す。

```python
        if self.toolbar is not None:
            self.toolbar.set_visibility(not options.read_only)
```

(c) クリックの付け方を 1 か所にまとめる。`GanttChart` に追加する。

```python
    def edit_on_click(self, element: ui.element, si: int | None, ti: int) -> ui.element:
        """クリックでタスクの編集を開く。読み取り専用では何も付けない。"""
        if not self.options.read_only:
            element.on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti))
        return element
```

`task_row` の `cell.on("click", ...)`、`bar.on("click", ...)、`actual_bars` の `bar.on("click", ...)` と `gap.on("click", ...)`、`deadline_marker` の `.on("click", ...)` を、それぞれ `self.edit_on_click(<要素>, si, ti)` に置き換える(`deadline_marker` は、`ui.label("◆").style(...)` を変数に取り、`.on(...)` を外して `self.edit_on_click(label, si, ti)` を呼んでから、`.tooltip(...).mark(...)` を続ける)。

(d) ドラッグ属性を、読み取り専用で付けない。`drag_props` の先頭の条件を `if self.task_filter.active or self.options.read_only:` にする。`task_row` の `if not self.task_filter.active: cell.props(...)` を `if not self.task_filter.active and not self.options.read_only:` にする。`draggable = self.view_scale is Scale.DAY` を `draggable = self.view_scale is Scale.DAY and not self.options.read_only` にする。

(e) 追加の部品を、読み取り専用で出さない。`top_add_row` の先頭に `if self.options.read_only: return` を足す。`section_rows` の `ui.button(icon="add", on_click=...)...mark(f"add-task-{si}")` を、`if not self.options.read_only:` の中にする。

(f) 描画の幅と、画像化の対象。`GanttChart` に追加する。

```python
    def content_width(self) -> int:
        """描画の全体の幅(px)。名前の列と、すべての列。画像の幅になる。"""
        columns = build_columns(self.project, self.view_scale, self.holidays, self.options.period)
        return NAME_WIDTH_PX + COLUMN_WIDTH_PX[self.view_scale] * len(columns)
```

`render` の `total = NAME_WIDTH_PX + width * len(columns)` はそのままにし、`with ui.element("div").style(f"position: relative; width: {total}px"):` を、`with ui.element("div").style(...).props("data-chart-content").mark("chart-content"):` にする。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_gantt.py test/test_gantt_drag.py test/test_views.py -q`
Expected: PASS(既存のクリック・ドラッグ・固定表示のテストも)

- [ ] **Step 5: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "ガントチャートを読み取り専用にでき、描画の幅と画像化の対象を持たせる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 画像の出力(`export.py`、同梱ファイル、`main.py`)

**Files:**
- Create: `src/projectapp/export.py`
- Create: `src/projectapp/static/html-to-image.js`、`src/projectapp/static/html-to-image.LICENSE`
- Modify: `src/projectapp/main.py`(`register_static_files()` の呼び出し)
- Test: `test/test_export.py`(新規)

**Interfaces:**
- Produces(`projectapp.export`):
  - 定数 `MAX_CANVAS_PX = 16384`、`MAX_PIXEL_RATIO = 2.0`
  - `export_pixel_ratio(width: float) -> float`(`min(2.0, 16384 / 幅)`。幅 ≤ 0 は 2.0)、`exceeds_canvas(width: float) -> bool`(幅 > 16384)
  - `default_filename(project_name: str, today: date) -> str`(`<名前>_<YYYYMMDD>.png`。使えない文字は `_` に、先頭の `.` は除く、空なら `gantt`)
  - `class ExportError(Exception)`
  - `png_from_data_url(url: str) -> bytes`(`data:image/png;base64,` 以外・不正な base64 は `ExportError`)
  - `parse_capture_result(raw: str) -> bytes`(JS の戻り値の JSON から PNG を取り出す。`error` があれば `ExportError`)
  - `write_png(path: Path, data: bytes) -> Path`(拡張子がなければ `.png` を付ける。一時ファイル経由で書く。失敗したら一時ファイルを残さず、`OSError` を投げる。書いたパスを返す)
  - `class ImageExporter(Protocol)`: `available: bool`(プロパティ)、`async capture(pixel_ratio: float) -> bytes`(`ExportError`)、`async ask_path(filename: str) -> Path | None`
  - `class NativeImageExporter`(上の実装)、`CAPTURE_JS`(`__RATIO__` を倍率に置き換えて使う)
  - `register_static_files() -> None`、`HTML_TO_IMAGE_URL = "/static/html-to-image.js"`

- [ ] **Step 1: 同梱ファイルを取得する**

```bash
mkdir -p src/projectapp/static
curl -sL https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.js -o src/projectapp/static/html-to-image.js
curl -sL https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/LICENSE -o src/projectapp/static/html-to-image.LICENSE
head -c 80 src/projectapp/static/html-to-image.js; echo; head -3 src/projectapp/static/html-to-image.LICENSE; wc -c src/projectapp/static/html-to-image.js
```

Expected: JS が `!function(t,e){"object"==typeof exports...` で始まり、約 19,000 バイト。LICENSE が `MIT License` で始まる。

- [ ] **Step 2: 失敗するテストを書く**

`test/test_export.py` を作る。

```python
import base64
import json
import os
from datetime import date
from pathlib import Path

import pytest

from projectapp.export import (
    MAX_CANVAS_PX,
    ExportError,
    NativeImageExporter,
    default_filename,
    exceeds_canvas,
    export_pixel_ratio,
    parse_capture_result,
    png_from_data_url,
    write_png,
)

PNG = b"\x89PNG\r\n\x1a\nbody"


def data_url(data: bytes = PNG) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


@pytest.mark.parametrize(
    ("width", "ratio"),
    [(0, 2.0), (-5, 2.0), (1880, 2.0), (8192, 2.0), (8193, 16384 / 8193), (15240, 16384 / 15240), (30480, 16384 / 30480)],
)
def test_pixel_ratio_never_exceeds_the_canvas(width: float, ratio: float) -> None:
    assert export_pixel_ratio(width) == pytest.approx(ratio)
    if width > 0:
        assert width * export_pixel_ratio(width) <= MAX_CANVAS_PX + 1e-6


def test_exceeds_canvas_at_ratio_one() -> None:
    assert not exceeds_canvas(16384)
    assert exceeds_canvas(16385)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("デモ", "デモ_20261005.png"),
        ("a/b\\c:d*e?f\"g<h>i|j", "a_b_c_d_e_f_g_h_i_j_20261005.png"),
        (".hidden", "hidden_20261005.png"),
        ("  ", "gantt_20261005.png"),
        ("", "gantt_20261005.png"),
        ("制御\x07文字", "制御_文字_20261005.png"),
    ],
)
def test_default_filename(name: str, expected: str) -> None:
    assert default_filename(name, date(2026, 10, 5)) == expected


def test_png_from_data_url() -> None:
    assert png_from_data_url(data_url()) == PNG


@pytest.mark.parametrize("bad", ["", "data:image/jpeg;base64,AAAA", "data:image/png;base64,***", "hello"])
def test_png_from_data_url_rejects_bad_input(bad: str) -> None:
    with pytest.raises(ExportError):
        png_from_data_url(bad)


def test_parse_capture_result() -> None:
    assert parse_capture_result(json.dumps({"url": data_url()})) == PNG


def test_parse_capture_result_reports_a_js_error() -> None:
    with pytest.raises(ExportError, match="boom"):
        parse_capture_result(json.dumps({"error": "boom"}))


@pytest.mark.parametrize("bad", ["", "not json", "null", "[]", "{}"])
def test_parse_capture_result_rejects_unexpected_values(bad: str) -> None:
    with pytest.raises(ExportError):
        parse_capture_result(bad)


def test_write_png_adds_the_extension_and_returns_the_path(tmp_path: Path) -> None:
    written = write_png(tmp_path / "chart", PNG)
    assert written == tmp_path / "chart.png"
    assert written.read_bytes() == PNG
    assert write_png(tmp_path / "other.PNG", PNG).name == "other.PNG"  # 大文字の拡張子はそのまま


def test_write_png_overwrites_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "chart.png"
    target.write_bytes(b"old")
    write_png(target, PNG)
    assert target.read_bytes() == PNG


def test_write_png_leaves_no_partial_file_when_the_directory_is_missing(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        write_png(tmp_path / "missing" / "chart.png", PNG)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root は書き込み禁止を無視する")
def test_write_png_leaves_nothing_when_the_directory_is_read_only(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(OSError):
            write_png(locked / "chart.png", PNG)
    finally:
        locked.chmod(0o700)
    assert list(locked.iterdir()) == []


def test_the_native_exporter_is_unavailable_outside_the_native_window() -> None:
    assert NativeImageExporter().available is False
```

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_export.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.export'`)

- [ ] **Step 4: 実装する**

`src/projectapp/export.py` を作る。

```python
"""ガントチャートの PNG 出力。倍率・ファイル名・デコード・書き込みは、画面に依存しない関数にする。"""

import base64
import binascii
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Protocol

from nicegui import app, ui

MAX_CANVAS_PX = 16384  # Safari 系のキャンバスの、1辺の上限
MAX_PIXEL_RATIO = 2.0
HTML_TO_IMAGE_URL = "/static/html-to-image.js"
STATIC_DIR = Path(__file__).parent / "static"
PNG_PREFIX = "data:image/png;base64,"
UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
CAPTURE_TIMEOUT_S = 90

# 画像化する。対象は data-chart-content の要素の全体(スクロールの外へはみ出す分を含む)。
# ライトは白、ダークは body の背景色。失敗は、例外にせず error の文字列で返す。
CAPTURE_JS = """
async () => {
  const root = document.querySelector('[data-chart-content]');
  if (!root) return JSON.stringify({error: '描画の対象が見つかりません'});
  if (typeof htmlToImage === 'undefined') return JSON.stringify({error: '画像化の部品を読み込めていません'});
  const dark = document.body.classList.contains('body--dark');
  const bg = dark ? getComputedStyle(document.body).backgroundColor : '#ffffff';
  try {
    const url = await htmlToImage.toPng(root, {
      width: root.scrollWidth, height: root.scrollHeight,
      pixelRatio: __RATIO__, backgroundColor: bg, cacheBust: false,
    });
    return JSON.stringify({url});
  } catch (e) { return JSON.stringify({error: String(e)}); }
}
"""


class ExportError(Exception):
    """画像を作れなかった(画像化の失敗、不正な結果)。"""


def export_pixel_ratio(width: float) -> float:
    """倍率。画像の幅がキャンバスの上限を超えないようにする(最大 2)。"""
    if width <= 0:
        return MAX_PIXEL_RATIO
    return min(MAX_PIXEL_RATIO, MAX_CANVAS_PX / width)


def exceeds_canvas(width: float) -> bool:
    """倍率 1 でも、上限を超えるか(縮小して保存される)。"""
    return width > MAX_CANVAS_PX


def default_filename(project_name: str, today: date) -> str:
    """既定のファイル名 `<名前>_<YYYYMMDD>.png`。ファイル名に使えない文字は `_` にする。"""
    name = UNSAFE_NAME_CHARS.sub("_", project_name.strip()).lstrip(".")
    return f"{name or 'gantt'}_{today:%Y%m%d}.png"


def png_from_data_url(url: str) -> bytes:
    if not isinstance(url, str) or not url.startswith(PNG_PREFIX):
        raise ExportError("画像の形式が正しくありません")
    try:
        return base64.b64decode(url[len(PNG_PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        raise ExportError("画像のデータが正しくありません") from None


def parse_capture_result(raw: str) -> bytes:
    """CAPTURE_JS の戻り値(JSON)から、PNG のバイト列を取り出す。"""
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        raise ExportError("画像化の結果を読めません") from None
    if not isinstance(result, dict):
        raise ExportError("画像化の結果が正しくありません")
    if "error" in result:
        raise ExportError(str(result["error"]))
    if "url" not in result:
        raise ExportError("画像化の結果が正しくありません")
    return png_from_data_url(result["url"])


def write_png(path: Path, data: bytes) -> Path:
    """PNG を書く。拡張子がなければ .png を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    if not path.suffix:
        path = path.with_name(path.name + ".png")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".export-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


class ImageExporter(Protocol):
    """画像化と、保存先の選択。テストでは、偽物に差し替える。"""

    @property
    def available(self) -> bool: ...

    async def capture(self, pixel_ratio: float) -> bytes: ...

    async def ask_path(self, filename: str) -> Path | None: ...


class NativeImageExporter:
    """ネイティブウィンドウ(pywebview)で、画面内の画像化と、保存ダイアログを使う。"""

    @property
    def available(self) -> bool:
        return app.native.main_window is not None

    async def capture(self, pixel_ratio: float) -> bytes:
        script = f"({CAPTURE_JS.replace('__RATIO__', repr(float(pixel_ratio)))})()"
        try:
            raw = await ui.run_javascript(script, timeout=CAPTURE_TIMEOUT_S)
        except TimeoutError:
            raise ExportError("画像化が時間内に終わりませんでした") from None
        return parse_capture_result(raw)

    async def ask_path(self, filename: str) -> Path | None:
        import webview  # ネイティブのときだけ使う

        window = app.native.main_window
        if window is None:
            return None
        result = await window.create_file_dialog(
            dialog_type=webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=("PNG 画像 (*.png)",),
        )
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])


def register_static_files() -> None:
    """同梱の JS を配る。アプリの起動時に一度だけ呼ぶ。"""
    app.add_static_file(local_file=STATIC_DIR / "html-to-image.js", url_path=HTML_TO_IMAGE_URL)
```

`main.py` の `main()` の、`ui.run(...)` の前に `register_static_files()` を呼ぶ(`from projectapp.export import register_static_files` を足す)。

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest test/test_export.py -q`
Expected: PASS

Run: `uvx ty check src` → `All checks passed!`

(`ui.run_javascript` の `TimeoutError` の型は、`ty` が指摘したら、NiceGUI の実際の例外型に合わせて `except` を直し、ledger に Ruling を残す。)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/export.py src/projectapp/static src/projectapp/main.py test/test_export.py
git commit -m "ガントチャートの PNG 出力の部品(倍率・ファイル名・デコード・書き込み・保存先)を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: プレビューの画面と保存の流れ(`preview.py`、`views.py`)

**Files:**
- Create: `src/projectapp/preview.py`
- Modify: `src/projectapp/views.py`(`exporter` 引数、ヘッダーの「エクスポート」と `header_box`、`build`、`enter_preview` / `exit_preview` / `on_preview_change` / `save_image`、ESC)
- Test: `test/test_preview.py`(新規)、`test/test_views.py`

**Interfaces:**
- Consumes: `ViewOptions`・`set_options`・`content_width`・`toolbar`(Task 2・3)、`export_pixel_ratio`・`exceeds_canvas`・`default_filename`・`write_png`・`ImageExporter`・`NativeImageExporter`・`ExportError`・`HTML_TO_IMAGE_URL`(Task 4)、`visible_range`(既存)
- Produces(`projectapp.preview`):
  - `PreviewSettings`(`frozen` の `dataclass`): `start: date`、`end: date`、`scale: Scale`、`show_chips: bool = True`、`show_alerts: bool = True`。`to_options() -> ViewOptions`(`read_only=True`)
  - `validate_period(start_text: str, end_text: str) -> tuple[date, date]`(`ValueError` の文: 「日付の形式が正しくありません(YYYY-MM-DD)」「年は2000〜2100の範囲で入力してください」「期間は、開始日が終了日以前になるように入れてください」)
  - `PreviewBar(on_change, on_back, on_save)`: `build()`、`show(settings, available)`、`hide()`、`read() -> tuple[str, str, Scale, bool, bool]`、`set_error(text | None)`、`set_warning(text | None)`、`set_saving(bool)`。マーカー: `preview-bar`、`preview-start`、`preview-end`、`preview-scale`、`preview-chips`、`preview-alerts`、`preview-back`、`preview-save`、`preview-error`、`preview-warning`
  - `MainView(base_dir, transport, exporter: ImageExporter | None = None)`、`MainView.preview: PreviewSettings | None`、`enter_preview()`、`exit_preview()`、`async save_image()`、マーカー `export-preview`(ヘッダーのボタン)、`header-box`

- [ ] **Step 1: 失敗するテストを書く(純粋な部分)**

`test/test_preview.py` を作る。

```python
from datetime import date

import pytest

from projectapp.gantt import ViewOptions
from projectapp.preview import PreviewSettings, validate_period
from projectapp.timeline import Scale


def test_settings_become_read_only_view_options() -> None:
    settings = PreviewSettings(date(2026, 10, 1), date(2026, 10, 31), Scale.WEEK, show_chips=False, show_alerts=True)
    assert settings.to_options() == ViewOptions(
        period=(date(2026, 10, 1), date(2026, 10, 31)), scale=Scale.WEEK, show_chips=False, show_alerts=True, read_only=True
    )


def test_validate_period_accepts_a_period_and_one_day() -> None:
    assert validate_period("2026-10-01", "2026-10-31") == (date(2026, 10, 1), date(2026, 10, 31))
    assert validate_period(" 2026-10-05 ", "2026-10-05") == (date(2026, 10, 5), date(2026, 10, 5))


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2026-10-09", "2026-10-08", "開始日が終了日以前"),
        ("", "2026-10-08", "形式"),
        ("2026-10-01", "abc", "形式"),
        ("2026/10/01", "2026-10-08", "形式"),
        ("2026-13-01", "2026-12-31", "形式"),
        ("1999-12-31", "2026-10-08", "2000〜2100"),
        ("2026-10-01", "2101-01-01", "2000〜2100"),
    ],
)
def test_validate_period_rejects_bad_input(start: str, end: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_period(start, end)
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_preview.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.preview'`)

- [ ] **Step 3: `preview.py` を実装する**

```python
"""プレビューモードの設定と、上部のバー。切り替えと保存の流れは MainView が持つ。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from nicegui import ui

from projectapp.gantt import ViewOptions
from projectapp.models import MAX_YEAR, MIN_YEAR
from projectapp.task_dialog import add_picker
from projectapp.timeline import Scale

PERIOD_ORDER_MESSAGE = "期間は、開始日が終了日以前になるように入れてください"
LARGE_IMAGE_MESSAGE = "画像が大きいため、縮小して保存されます(期間かスケールを変えると小さくできます)"
NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、画像として保存できます"


@dataclass(frozen=True)
class PreviewSettings:
    start: date
    end: date
    scale: Scale
    show_chips: bool = True
    show_alerts: bool = True

    def to_options(self) -> ViewOptions:
        return ViewOptions(
            period=(self.start, self.end),
            scale=self.scale,
            show_chips=self.show_chips,
            show_alerts=self.show_alerts,
            read_only=True,
        )


def validate_period(start_text: str, end_text: str) -> tuple[date, date]:
    """期間の入力(YYYY-MM-DD)を検証する。開始日は終了日以前。"""
    try:
        start = datetime.strptime((start_text or "").strip(), "%Y-%m-%d").date()
        end = datetime.strptime((end_text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("日付の形式が正しくありません(YYYY-MM-DD)") from None
    if not (MIN_YEAR <= start.year <= MAX_YEAR and MIN_YEAR <= end.year <= MAX_YEAR):
        raise ValueError(f"年は{MIN_YEAR}〜{MAX_YEAR}の範囲で入力してください")
    if start > end:
        raise ValueError(PERIOD_ORDER_MESSAGE)
    return start, end


class PreviewBar:
    """プレビューの上部のバー。期間・スケール・表示項目と、戻る・保存のボタン。"""

    def __init__(
        self,
        on_change: Callable[[], object],
        on_back: Callable[[], object],
        on_save: Callable[[], object],
    ) -> None:
        self.on_change, self.on_back, self.on_save = on_change, on_back, on_save
        self.box: ui.column | None = None

    def build(self) -> None:
        with ui.column().classes("w-full gap-1") as box:
            with ui.row().classes("w-full items-center gap-4").mark("preview-bar"):
                self.start = ui.input("開始日").classes("w-40").mark("preview-start")
                add_picker(self.start, ui.date, "event", "preview-start", "%Y-%m-%d")
                self.end = ui.input("終了日").classes("w-40").mark("preview-end")
                add_picker(self.end, ui.date, "event", "preview-end", "%Y-%m-%d")
                self.scale = ui.toggle({s.value: s.value for s in Scale}).mark("preview-scale")
                self.chips = ui.checkbox("チップと進捗", value=True).mark("preview-chips")
                self.alerts = ui.checkbox("予定超過の赤みと割り当て超過の縞", value=True).mark(
                    "preview-alerts"
                )
                ui.button("戻る", icon="arrow_back", on_click=lambda: self.on_back()).props(
                    "flat"
                ).mark("preview-back")
                self.save_button = ui.button(
                    "画像として保存", icon="image", on_click=lambda: self.on_save()
                ).mark("preview-save")
            self.error = ui.label("").classes("text-negative text-caption").mark("preview-error")
            self.warning = ui.label("").classes("text-caption text-grey").mark("preview-warning")
        box.set_visibility(False)
        self.box = box
        for widget in (self.start, self.end, self.scale, self.chips, self.alerts):
            widget.on_value_change(lambda _event: self.on_change())

    def show(self, settings: PreviewSettings) -> None:
        """初期値を入れて出す。値を入れる間は、変更の通知を出さない。"""
        callback, self.on_change = self.on_change, lambda: None
        try:
            self.start.set_value(settings.start.isoformat())
            self.end.set_value(settings.end.isoformat())
            self.scale.set_value(settings.scale.value)
            self.chips.set_value(settings.show_chips)
            self.alerts.set_value(settings.show_alerts)
        finally:
            self.on_change = callback
        self.set_error(None)
        self.set_warning(None)
        if self.box is not None:
            self.box.set_visibility(True)

    def hide(self) -> None:
        if self.box is not None:
            self.box.set_visibility(False)

    def read(self) -> tuple[str, str, Scale, bool, bool]:
        return (
            self.start.value or "",
            self.end.value or "",
            Scale(self.scale.value),
            bool(self.chips.value),
            bool(self.alerts.value),
        )

    def set_error(self, text: str | None) -> None:
        self.error.set_text(text or "")

    def set_warning(self, text: str | None) -> None:
        self.warning.set_text(text or "")

    def set_save_enabled(self, enabled: bool) -> None:
        self.save_button.set_enabled(enabled)
```

- [ ] **Step 4: `views.py` の統合のテストを書く**

`test/test_views.py` の末尾に追加する(`mount_capturing`、`wait_until`、`save_cache`、`make_transport`、`Project`、`Section`、`Task`、`Path`、`datetime`、`date` は既存。インポートに `ExportError`、`PNG`(下で定義)を足す)。

```python
PNG_BYTES = b"\x89PNG\r\n\x1a\nbody"


class FakeExporter:
    """画像化と保存先の選択の偽物。呼ばれた内容を記録する。"""

    def __init__(self, path: Path | None = None, error: Exception | None = None, available: bool = True) -> None:
        self.path, self.error, self._available = path, error, available
        self.captured: list[float] = []
        self.asked: list[str] = []

    @property
    def available(self) -> bool:
        return self._available

    async def capture(self, pixel_ratio: float) -> bytes:
        self.captured.append(pixel_ratio)
        if self.error is not None:
            raise self.error
        return PNG_BYTES

    async def ask_path(self, filename: str) -> Path | None:
        self.asked.append(filename)
        return self.path


def mount_preview(base_dir: Path, views: list[MainView], exporter: FakeExporter) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(base_dir, make_transport(200, []), exporter)
        views.append(view)
        view.build()


def planned_task() -> Task:
    return Task("設計", planned_start=datetime(2026, 10, 5, 12), planned_end=datetime(2026, 10, 7, 12), project_code="P")


async def open_preview(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    view.save_task(None, None, planned_task())
    user.find(marker="export-preview").click()
    return view


async def test_the_preview_replaces_the_header_and_toolbar(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    assert view.preview is not None
    assert not user.find(marker="header-box").elements.pop().visible
    assert not view.gantt.toolbar.visible
    assert user.find(marker="preview-bar").elements.pop().parent_slot.parent.visible
    assert view.gantt.options.read_only
    await user.should_not_see(marker="add-task-top")


async def test_the_preview_starts_with_the_visible_range_and_the_current_scale(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    settings = view.preview
    assert settings is not None
    assert settings.start == date(2026, 10, 5)
    assert settings.end >= date(2026, 10, 7)
    assert settings.scale is view.gantt.scale
    assert user.find(marker="preview-start").elements.pop().value == "2026-10-05"
    assert user.find(marker="preview-scale").elements.pop().value == view.gantt.scale.value


async def test_back_restores_the_header_toolbar_and_default_options(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-back").click()
    assert view.preview is None
    assert user.find(marker="header-box").elements.pop().visible
    assert view.gantt.toolbar.visible
    assert view.gantt.options == ViewOptions()


def key_event(name: str, keydown: bool = True) -> KeyEventArguments:
    return KeyEventArguments(
        sender=None,  # type: ignore[arg-type]
        client=None,  # type: ignore[arg-type]
        action=KeyboardAction(keydown=keydown, keyup=not keydown, repeat=False),
        key=KeyboardKey(name=name, code=name, location=0),
        modifiers=KeyboardModifiers(alt=False, ctrl=False, meta=False, shift=False),
    )


async def test_escape_goes_back(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    view.on_key(key_event("Escape"))
    assert view.preview is None
    assert user.find(marker="header-box").elements.pop().visible


async def test_other_keys_and_key_releases_do_not_go_back(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    view.on_key(key_event("Enter"))
    view.on_key(key_event("Escape", keydown=False))
    assert view.preview is not None


async def test_escape_does_nothing_outside_the_preview(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, FakeExporter())
    await user.open("/")
    views[0].on_key(key_event("Escape"))
    assert views[0].preview is None
    assert user.find(marker="header-box").elements.pop().visible


async def test_the_filter_survives_the_preview_round_trip(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    view.gantt.set_filter(replace(view.gantt.task_filter, query="設計"))
    user.find(marker="preview-back").click()
    assert view.gantt.task_filter.query == "設計"


async def test_changing_the_settings_updates_the_chart(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-start").clear().type("2026-10-06")
    assert view.gantt.options.period[0] == date(2026, 10, 6)
    user.find(marker="preview-chips").elements.pop().set_value(False)
    assert view.gantt.options.show_chips is False
    user.find(marker="preview-scale").elements.pop().set_value("週次")
    assert view.gantt.options.scale.value == "週次"
    assert view.gantt.scale.value == "日次"  # ツールバーのスケールは変わらない


async def test_a_bad_period_disables_saving_and_shows_the_reason(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter()
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-start").clear().type("2026-12-31")
    user.find(marker="preview-end").clear().type("2026-10-01")
    await user.should_see("開始日が終了日以前")
    assert not user.find(marker="preview-save").elements.pop().enabled
    user.find(marker="preview-end").clear().type("2027-01-31")
    assert user.find(marker="preview-save").elements.pop().enabled
    assert exporter.captured == []


async def test_a_large_image_shows_a_warning_but_can_still_be_saved(user: User, tmp_path: Path) -> None:
    view = await open_preview(user, tmp_path, FakeExporter())
    user.find(marker="preview-end").clear().type("2028-12-31")  # 日次で約 3 年 → 16,384px 超
    await user.should_see("縮小して保存されます")
    assert user.find(marker="preview-save").elements.pop().enabled
    user.find(marker="preview-end").clear().type("2026-12-31")
    await user.should_not_see("縮小して保存されます")


async def test_save_writes_the_png_and_notifies(user: User, tmp_path: Path) -> None:
    target = tmp_path / "out" / "chart"
    target.parent.mkdir()
    exporter = FakeExporter(path=target)
    await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: (tmp_path / "out" / "chart.png").exists())
    assert (tmp_path / "out" / "chart.png").read_bytes() == PNG_BYTES
    assert exporter.asked == [f"新規プロジェクト_{date.today():%Y%m%d}.png"]
    assert 0 < exporter.captured[0] <= 2.0
    await user.should_see("保存しました")


async def test_cancelling_the_save_dialog_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.glob("*.png"))
    assert view.preview is not None  # プレビューに留まる


async def test_a_capture_failure_is_reported_and_the_preview_stays(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(error=ExportError("boom"))
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    await user.should_see("画像を作れませんでした: boom")
    assert exporter.asked == []  # 保存先は聞かない
    assert view.preview is not None
    assert user.find(marker="preview-save").elements.pop().enabled  # もう一度押せる


async def test_a_write_failure_is_reported_and_leaves_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "missing" / "chart.png")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    await user.should_see("保存できませんでした")
    assert view.preview is not None
    assert not list(tmp_path.rglob("*.tmp"))


async def test_saving_cannot_be_started_twice(user: User, tmp_path: Path) -> None:
    gate = asyncio.Event()

    class SlowExporter(FakeExporter):
        async def capture(self, pixel_ratio: float) -> bytes:
            self.captured.append(pixel_ratio)
            await gate.wait()
            return PNG_BYTES

    exporter = SlowExporter(path=tmp_path / "chart.png")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-save").click()
    assert await wait_until(lambda: exporter.captured != [])
    assert not user.find(marker="preview-save").elements.pop().enabled  # 保存中は押せない
    await view.save_image()  # 直接呼んでも、二重には始まらない
    assert len(exporter.captured) == 1
    gate.set()
    assert await wait_until(lambda: (tmp_path / "chart.png").exists())
    assert user.find(marker="preview-save").elements.pop().enabled


async def test_saving_is_disabled_outside_the_native_window(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter(available=False))
    assert not user.find(marker="preview-save").elements.pop().enabled
    await user.should_see("ネイティブウィンドウでのみ")


async def test_the_default_exporter_is_unavailable_in_tests(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_capturing(tmp_path, views)  # exporter を渡さない = NativeImageExporter
    await user.open("/")
    user.find(marker="export-preview").click()
    assert not user.find(marker="preview-save").elements.pop().enabled
```

(`asyncio`、`replace`(`dataclasses`)、`ViewOptions`、`ExportError`、`ui`、`KeyEventArguments`・`KeyboardAction`・`KeyboardKey`・`KeyboardModifiers`(`nicegui.events`)が未インポートなら足す。NiceGUI の `User` には、キー入力のシミュレーションがないので、`on_key` にイベントを直接渡す。)

- [ ] **Step 5: 失敗を確認する**

Run: `uv run pytest test/test_preview.py test/test_views.py -q -k "preview or escape or large_image or save_ or capture_failure or write_failure or default_exporter or cancelling or twice"`
Expected: FAIL(`export-preview` が見つからない、`MainView() takes ... exporter` など)

- [ ] **Step 6: `views.py` を実装する**

インポートを足す。

```python
from datetime import date

from projectapp.export import (
    HTML_TO_IMAGE_URL,
    ExportError,
    ImageExporter,
    NativeImageExporter,
    default_filename,
    exceeds_canvas,
    export_pixel_ratio,
    write_png,
)
from projectapp.gantt import GanttActions, GanttChart, ViewOptions
from projectapp.preview import (
    LARGE_IMAGE_MESSAGE,
    NOT_NATIVE_MESSAGE,
    PreviewBar,
    PreviewSettings,
    validate_period,
)
from projectapp.timeline import visible_range
from nicegui.events import KeyEventArguments
```

(`date` と `GanttActions`/`GanttChart` は既にあれば重複させない。)

`MainView.__init__` のシグネチャに `exporter: ImageExporter | None = None` を足し、本体に次を足す。

```python
        self.exporter: ImageExporter = exporter or NativeImageExporter()
        self.preview: PreviewSettings | None = None
        self.saving = False
        self.preview_bar = PreviewBar(self.on_preview_change, self.exit_preview, self.save_image)
```

`build` を次にする。

```python
    def build(self) -> None:
        ui.add_head_html(f'<script src="{HTML_TO_IMAGE_URL}"></script>')
        self.header()
        self.preview_bar.build()
        self.gantt.build()
        self.theme_fab()
        self.help_button()
        ui.keyboard(on_key=self.on_key)
        if self.needs_first_fetch:
            ui.timer(0.1, self.first_fetch, once=True)
```

`header` の `with ui.column().classes("w-full gap-2"):` を `with ui.column().classes("w-full gap-2") as box:` にして、`self.header_box = box`、`box.mark("header-box")` とする(中身は変えない)。「メンバー」ボタンの後ろに足す。

```python
                ui.button("エクスポート", icon="image", on_click=self.enter_preview).mark(
                    "export-preview"
                )
```

メソッドを追加する(`open_members` の近くなど)。

```python
    def on_key(self, event: KeyEventArguments) -> None:
        """ESC で、プレビューから戻る。"""
        if self.preview is not None and event.action.keydown and event.key == "Escape":
            self.exit_preview()

    def enter_preview(self) -> None:
        """メイン画面を、プレビューモードに切り替える。初期値は、今の表示範囲と、今のスケール。"""
        if self.preview is not None:
            return
        start, end = visible_range(self.project, self.holidays)
        self.preview = PreviewSettings(start, end - timedelta(days=1), self.gantt.scale)
        self.header_box.set_visibility(False)
        self.preview_bar.show(self.preview)
        self.apply_preview(self.preview)

    def exit_preview(self) -> None:
        """プレビューから戻る。通常のヘッダー・ツールバー・描画に戻す(絞り込みは変えない)。"""
        if self.preview is None:
            return
        self.preview = None
        self.preview_bar.hide()
        self.header_box.set_visibility(True)
        self.gantt.set_options(ViewOptions())

    def on_preview_change(self) -> None:
        """バーの入力が変わったとき。期間が正しければ描き直し、誤りなら理由を出して保存を止める。"""
        if self.preview is None:
            return
        start_text, end_text, scale, chips, alerts = self.preview_bar.read()
        try:
            start, end = validate_period(start_text, end_text)
        except ValueError as exc:
            self.preview_bar.set_error(str(exc))
            self.preview_bar.set_warning(None)
            self.preview_bar.set_save_enabled(False)
            return
        self.preview = PreviewSettings(start, end, scale, chips, alerts)
        self.apply_preview(self.preview)

    def apply_preview(self, settings: PreviewSettings) -> None:
        self.gantt.set_options(settings.to_options())
        self.preview_bar.set_error(None)
        available = self.exporter.available
        self.preview_bar.set_save_enabled(available and not self.saving)
        if not available:
            self.preview_bar.set_warning(NOT_NATIVE_MESSAGE)
        elif exceeds_canvas(self.gantt.content_width()):
            self.preview_bar.set_warning(LARGE_IMAGE_MESSAGE)
        else:
            self.preview_bar.set_warning(None)

    async def save_image(self) -> None:
        """プレビューを画像にして、選んだ場所へ保存する。失敗しても、プレビューに留まる。"""
        if self.preview is None or self.saving or not self.exporter.available:
            return
        self.saving = True
        self.preview_bar.set_save_enabled(False)
        try:
            ratio = export_pixel_ratio(self.gantt.content_width())
            try:
                data = await self.exporter.capture(ratio)
            except ExportError as exc:
                ui.notify(f"画像を作れませんでした: {exc}", type="negative")
                return
            path = await self.exporter.ask_path(default_filename(self.project.name, date.today()))
            if path is None:
                return
            try:
                write_png(path, data)
            except OSError as exc:
                ui.notify(f"保存できませんでした: {exc}", type="negative")
                return
            ui.notify("保存しました")
        finally:
            self.saving = False
            if self.preview is not None:
                self.preview_bar.set_save_enabled(self.exporter.available)
```

(`timedelta` を `from datetime import date, timedelta` に。プレビューのバーの `on_change` は、`PreviewBar.show` の間は何もしないため、`show` のあとに `apply_preview` を呼ぶ。`on_preview_change` が `self.preview` を上書きするので、`exit_preview` を呼んだあとの遅れた通知は、`self.preview is None` で無視される。)

- [ ] **Step 7: 通ることを確認する**

Run: `uv run pytest test/test_preview.py test/test_views.py test/test_gantt.py -q`
Expected: PASS(既存の画面のテストも)

- [ ] **Step 8: 型チェックとコミット**

Run: `uvx ty check src` → `All checks passed!`

```bash
git add src/projectapp/preview.py src/projectapp/views.py test/test_preview.py test/test_views.py
git commit -m "メイン画面をプレビューモードに切り替え、画像として保存できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ドキュメントと作業記録、全体の確認

**Files:**
- Modify: `CLAUDE.md`(projectapp。「ガントチャート」の節)
- Modify: `docs/development.md`
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: `CLAUDE.md` に 2 行を足す**

「タスクの優先度(`高`・`中`・`低`)は、…」の行の下に追加する。

```markdown
- メイン画面の「エクスポート」で、プレビューモード(読み取り専用)に切り替わる。プレビューで、期間・スケール・表示項目(名前欄のチップと進捗、予定超過の赤みと割り当て超過の縞)を選べる。ESC か「戻る」で戻る
- プレビューの「画像として保存」で、ガントチャートを PNG 画像として保存できる(保存先は、ファイル保存ダイアログで選ぶ。ネイティブウィンドウのみ)
```

- [ ] **Step 2: `docs/development.md` に説明を足す**

ガントチャートの表示に関する既存の記述の近くに、次の内容を足す(既存の文体にそろえる)。

- `gantt.ViewOptions`(`period`、`scale`、`show_chips`、`show_alerts`、`read_only`。既定値が通常の画面と同じ)。`GanttChart.options` と `view_scale`(`options.scale or scale`)で描く。ツールバーのトグルは `scale` を持ち、プレビューのスケールとは別。`set_options` は、描き直し、描画のスケールが変わるときだけ横のスクロールを先頭へ戻し、読み取り専用のときツールバーを隠す。
- 期間は `timeline.build_columns(..., period)`(開始日・終了日を含む。下限 `MIN_COLUMNS` は守る)。期間を指定したときだけ、期間と重ならない棒(予定・実績・点線・進捗の塗り・状態の印)を `bar_visible`(`timeline.in_range`)で描かない。行は残す。
- 読み取り専用: `edit_on_click` がクリックを付けず、`drag_props` とドラッグ属性を付けず、`top_add_row` とセクションの追加ボタンを出さない。
- 画像化は `export.py`: 同梱の html-to-image(`src/projectapp/static/`、MIT)で、`data-chart-content` の要素(スクロールの外へはみ出す分を含む全体)を PNG にし、base64 を Python に返す(`CAPTURE_JS`)。倍率は `export_pixel_ratio(幅) = min(2, 16384 / 幅)`(Safari 系のキャンバスの上限)。倍率 1 でも超えるとき(`exceeds_canvas`)は、警告を出して縮小して保存する。アイコンのフォントは画像に埋め込まれないので、プレビューは、アイコン付きの編集の部品をすべて隠す。
- 保存の流れ(`MainView.save_image`): 画像化 → 保存先の選択(pywebview のファイル保存ダイアログ) → `write_png`(一時ファイル経由。拡張子がなければ `.png`)。画像化と保存先の選択は `ImageExporter`(テストでは偽物)。ネイティブウィンドウでないときは、保存を無効にする。静的ファイルの登録(`register_static_files`)は、`main()` から一度だけ。
- 実際の画像化は、自動テストでは確かめられない(WKWebView が要る)。実機で、ライト・ダーク、日次・週次・月次、長い期間を確認する。

- [ ] **Step 3: 全体のテストと型チェック**

Run: `uv run pytest -q`(約4分。バックグラウンドで実行して、終わりを待つ)
Expected: すべて PASS(911 件 + 新しいテスト)

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 4: `.claude/MEMORY.md` を更新する**

- 先頭の「最終更新」を、要望 2 の実装(`feature/export-preview`、未マージ)に直す。
- 「現在の状況」の先頭に、要望 2 の実装の記録を足す: ブランチ、設計書 `2026-10-05-export-preview-design.md`、実装計画 `2026-10-05-export-preview.md`、テストの件数、方式(`ViewOptions`、`export.py`、`preview.py`、同梱の html-to-image)、`develop` へは未マージ・未プッシュ、実機での確認はこれから(画像化の見た目、ライト・ダーク、日次・週次・月次、1 年以上の日次、保存ダイアログ、ESC)、保留(期間にタスクがない行を隠すか、画像の見出し、分割保存)。
- 「今後の要望」の 2 の行に `(完了)` を付ける。
- 「参照先」に、設計書と実装計画を足す。

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md
git commit -m "作業記録: エクスポートとプレビューの実装を反映

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

実機での確認用のデータは、`~/.projectapp/` の既存の `チップテスト.json` を使える(新しいファイルは不要)。長い期間の確認には、遠い先のタスクを持つプロジェクトを、新しいファイルとして作る(既存のファイルを上書きしない)。
