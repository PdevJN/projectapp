# 負荷の日ごとのヒートマップ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `全プロジェクト` がオンのとき、人×稼働日の表で日ごとの割り当て率の合計を色で示し、100% 超の日を一目で見つけられるようにする。

**Architecture:** 集計(`dashboard.py`)の `CrossLoad` に日ごとの値(`DayLoad`)を足す。描画は `dashboard_view.py` の純粋関数 `heatmap_html` が 1 つの HTML の塊を作り、全幅のカードに `ui.html` で出す。`views.py`・`portfolio.py` は変えない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、ty

**Spec:** `docs/superpowers/specs/2026-10-22-load-heatmap-design.md`

## Global Constraints

- 型ヒント: すべての関数に引数と戻り値の型を書く(`.claude/RULE.md`)。型チェックは `uv run ty check src`
- コメントは多くても 3 行以内。言語は日本語
- セルの値は「その日の同時刻の割り当て率の合計の最大」(要望 31 と同じ)
- 100% 超は `total > 1.0 + OVERLOAD_EPSILON`(`timeline.OVERLOAD_EPSILON`)
- 色は既存の `LOAD_COLOR`(1〜100%)と `OVER_COLOR`(100% 超)。濃さは透明度で表す。100% 超は太い枠線も付ける
- HTML に入れる名前・プロジェクト名・日付は `html.escape` する
- ファイル形式(`version` 7)は変えない。`views.py`・`portfolio.py` は変えない
- 実行: `uv run pytest -n auto -q`。ブランチは `feature/load-heatmap`(作成済み)

## Review Focus

- 名前やプロジェクト名に `<`・`"`・`&` が入る(HTML の崩れ・注入) → Task 2
- 稼働日が 0 日の期間(祝日だけの週など) → Task 2
- 同じ日に複数のプロジェクトで重なる日と、片方だけの日、0% の日の内訳 → Task 1
- 平均・最大・超過日数が、日ごとの値から求めた値と食い違わない → Task 1
- `全プロジェクト` をオフに戻すと、表が消える → Task 2

---

### Task 1: 集計に日ごとの値を足す

**Files:**
- Modify: `src/projectapp/dashboard.py`(`ProjectLoad`・`CrossLoad` の近く、`_load_stats`・`summarize_cross_loads`)
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: 既存の `_day_peak`、`_workdays`、`_member_spans`、`LoadStats`、`OVERLOAD_EPSILON`
- Produces:
  - `ProjectPeak(project: str, peak: float)`、`DayLoad(day: date, total: float, by_project: list[ProjectPeak])`(frozen dataclass)
  - `CrossLoad.days: list[DayLoad]`(既定は空のリスト)。稼働日の昇順。`by_project` は `peak > 0` のプロジェクトだけ(プロジェクトの並び順)
  - `_day_totals(items, days) -> list[float]`、`_stats_of(totals) -> LoadStats`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の `test_cross_load_without_projects_is_empty` の後ろに追記する。

```python
def test_cross_days_reproduce_the_load_stats() -> None:
    first = named("A", span_task("a", 5, 6, 0.6))
    second = named("B", span_task("b", 5, 6, 0.6), span_task("c", 8, 8, 0.3))
    cross = summarize_cross_loads([first, second], WEEK, {})["田中"]
    totals = [day.total for day in cross.days]
    assert cross.total.average == pytest.approx(sum(totals) / len(totals))
    assert cross.total.peak == max(totals)
    assert cross.total.overload_days == sum(1 for total in totals if total > 1.0 + 1e-9)


def test_cross_days_list_the_workdays_only() -> None:
    project = named("A", span_task("a", 5, 12, 0.5))
    cross = summarize_cross_loads([project], WEEK, {date(2026, 10, 6): "祝"})["田中"]
    assert [day.day for day in cross.days] == [date(2026, 10, d) for d in (5, 7, 8, 9)]


def test_cross_days_add_projects_on_the_same_day_and_break_them_down() -> None:
    first = named("A", span_task("a", 5, 6, 0.6))
    second = named("B", span_task("b", 6, 7, 0.6))
    days = {day.day: day for day in summarize_cross_loads([first, second], WEEK, {})["田中"].days}
    only_a = days[date(2026, 10, 5)]
    assert only_a.total == 0.6
    assert [(p.project, p.peak) for p in only_a.by_project] == [("A", 0.6)]
    both = days[date(2026, 10, 6)]
    assert both.total == pytest.approx(1.2)
    assert [(p.project, p.peak) for p in both.by_project] == [("A", 0.6), ("B", 0.6)]
    nobody = days[date(2026, 10, 8)]
    assert (nobody.total, nobody.by_project) == (0.0, [])


def test_cross_days_are_filled_for_a_single_project_too() -> None:
    cross = summarize_cross_loads([named("A", span_task("a", 5, 6, 0.5))], WEEK, {})["田中"]
    assert len(cross.days) == 5
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard.py -q -k cross_days`
Expected: FAIL(`AttributeError: 'CrossLoad' object has no attribute 'days'`)

- [ ] **Step 3: 実装する**

`dashboard.py`:

`ProjectLoad` と `CrossLoad` の定義を次のようにする。

```python
@dataclass(frozen=True)
class ProjectPeak:
    project: str
    peak: float  # その日、そのプロジェクトだけで見た割り当て率の合計の最大


@dataclass(frozen=True)
class DayLoad:
    day: date
    total: float  # 全プロジェクトを重ねた、その日の負荷(1.0 = 100%)
    by_project: list[ProjectPeak]  # 0 より大きいプロジェクトだけ


@dataclass(frozen=True)
class CrossLoad:
    total: LoadStats  # 全プロジェクトを重ねた負荷
    by_project: list[ProjectLoad]  # その人がメンバーのプロジェクトごと
    days: list[DayLoad] = field(default_factory=list)  # 稼働日ごと
```

`_load_stats` を次の 3 つにする。

```python
def _day_totals(items: list[Span], days: list[date]) -> list[float]:
    return [_day_peak(items, day) for day in days]


def _stats_of(totals: list[float]) -> LoadStats:
    return LoadStats(
        sum(totals) / len(totals) if totals else 0.0,
        max(totals, default=0.0),
        sum(1 for total in totals if total > 1.0 + OVERLOAD_EPSILON),
    )


def _load_stats(items: list[Span], days: list[date]) -> LoadStats:
    return _stats_of(_day_totals(items, days))
```

`summarize_cross_loads` の `for name in names:` の中身を次にする。

```python
        rows: list[ProjectLoad] = []
        everything: list[Span] = []
        per_day: list[tuple[str, list[float]]] = []
        for project, spans in per_project:
            if name not in {m.name for m in project.members}:
                continue
            items = spans.get(name, [])
            everything += items
            totals = _day_totals(items, days)
            stats = _stats_of(totals)
            rows.append(ProjectLoad(project.name, stats.average, stats.peak))
            per_day.append((project.name, totals))
        overall = _day_totals(everything, days)
        day_rows = [
            DayLoad(day, overall[i], [ProjectPeak(title, totals[i]) for title, totals in per_day if totals[i] > 0])
            for i, day in enumerate(days)
        ]
        loads[name] = CrossLoad(_stats_of(overall), rows, day_rows)
```

- [ ] **Step 4: 通ることを確認する(要望 31 のテストを含む)**

Run: `uv run pytest test/test_dashboard.py -q`
Expected: PASS(全件)

- [ ] **Step 5: 型チェックとコミット**

```bash
uv run ty check src
git add src/projectapp/dashboard.py test/test_dashboard.py
git commit -m "feat: 横断の負荷に、稼働日ごとの値を足す(要望47)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ヒートマップのカード

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(定数・純粋関数・`build`・`cards`・新しい `heatmap_card`)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: Task 1 の `DayLoad`・`ProjectPeak`・`CrossLoad.days`、`CrossSummary`、`gantt.WEEKDAYS`、`timeline.OVERLOAD_EPSILON`、既存の `LOAD_COLOR`・`OVER_COLOR`・`card`・`empty_message`
- Produces:
  - `heatmap_html(cross: CrossSummary) -> str`(人×稼働日の表。各セルは `data-cell="{名前}|{YYYY-MM-DD}"` と `title` を持つ)
  - `legend_html() -> str`
  - マーカー: カード `dashboard-heatmap`、表 `dashboard-heatmap-table`、空のとき `dashboard-heatmap-empty`(`稼働日がありません`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` の import に `DayLoad`・`ProjectPeak` を、`projectapp.dashboard_view` の import に `heatmap_html` を足し、末尾に追記する(`import re` を先頭に足す)。

```python
def heat_summary(name: str = "田中", project: str = "A") -> CrossSummary:
    days = [
        DayLoad(date(2026, 10, 5), 0.0, []),
        DayLoad(date(2026, 10, 6), 0.6, [ProjectPeak(project, 0.6)]),
        DayLoad(date(2026, 10, 7), 1.2, [ProjectPeak(project, 0.6), ProjectPeak("B", 0.6)]),
    ]
    loads = {name: CrossLoad(LoadStats(0.6, 1.2, 1), [], days)}
    return CrossSummary(loads, [project, "B"], set(), [])


def cell_of(markup: str, key: str) -> str:
    match = re.search(rf'<td[^>]*data-cell="{re.escape(key)}"[^>]*>', markup)
    assert match is not None, key
    return match.group(0)


def test_the_heatmap_has_a_cell_per_person_and_day_and_marks_overload() -> None:
    markup = heatmap_html(heat_summary())
    assert markup.count("data-cell=") == 3
    assert "outline" in cell_of(markup, "田中|2026-10-07")  # 120% は枠線つき
    assert "outline" not in cell_of(markup, "田中|2026-10-06")
    assert "transparent" in cell_of(markup, "田中|2026-10-05")  # 0% は塗りなし


def test_the_heatmap_cells_show_the_total_and_the_breakdown_on_hover() -> None:
    markup = heatmap_html(heat_summary())
    assert "田中 10/07(水) 120%&#10;A 60% / B 60%" in cell_of(markup, "田中|2026-10-07")
    assert "田中 10/05(月) 0%" in cell_of(markup, "田中|2026-10-05")


def test_the_heatmap_escapes_names() -> None:
    markup = heatmap_html(heat_summary(name='<b>"田&中', project="<i>"))
    assert "<b>" not in markup and "<i>" not in markup
    assert "&lt;b&gt;" in markup and "&lt;i&gt;" in markup


async def test_the_heatmap_card_is_shown_only_with_cross(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-load-田中")
    await user.should_not_see(marker="dashboard-heatmap")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = heat_summary().loads["田中"]
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-table")
    assert "data-cell" in user.find(marker="dashboard-heatmap-table").elements.pop().content


async def test_the_heatmap_card_says_so_when_there_are_no_workdays(user: User) -> None:
    views, _, _ = mount_cross()
    await user.open("/")
    data = cross_sample()
    assert data.cross is not None
    data.cross.loads["田中"] = CrossLoad(LoadStats(0.0, 0.0, 0), [], [])
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker="dashboard-heatmap-empty")
    assert text(user, "dashboard-heatmap-empty") == "稼働日がありません"
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_dashboard_view.py -q -k heatmap`
Expected: FAIL(`ImportError: cannot import name 'heatmap_html'`)

- [ ] **Step 3: 実装する**

`dashboard_view.py`:

import を整える。

```python
import html
from collections.abc import Callable
from datetime import datetime

from projectapp.dashboard import CrossSummary, DayLoad, Dashboard, LoadStats, MemberProgress, PeriodKind, TeamProgress
from projectapp.gantt import STATUS_COLORS, STATUS_DARK_COLORS, WEEKDAYS
from projectapp.timeline import OVERLOAD_EPSILON
```

定数と純粋関数を、`percent_width` の近くに足す。

```python
CELL_PX = 26  # 見出しの `10/22` が収まる幅
HEAT_OVER_OUTLINE = "#b71c1c"
HEATMAP_CSS = (
    ".heatmap-name { position: sticky; left: 0; background: #fff; padding-right: 8px; white-space: nowrap }\n"
    "body.body--dark .heatmap-name { background: #1d1d1d }"
)


def rgba(color: str, alpha: float) -> str:
    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha:.2f})"


def cell_style(total: float) -> str:
    """セルの塗り。0% は塗りなし、100% 以下は青、100% 超は赤と太い枠線(濃さは値に比例)。"""
    if total <= 0:
        return "background: transparent"
    if total <= 1.0 + OVERLOAD_EPSILON:
        return f"background: {rgba(LOAD_COLOR, 0.15 + 0.65 * min(total, 1.0))}"
    alpha = 0.55 + 0.45 * min(total - 1.0, 1.0)
    return f"background: {rgba(OVER_COLOR, alpha)}; outline: 2px solid {HEAT_OVER_OUTLINE}; outline-offset: -2px"


def cell_title(name: str, load: DayLoad) -> str:
    head = f"{name} {load.day:%m/%d}({WEEKDAYS[load.day.weekday()]}) {load.total * 100:.0f}%"
    lines = [html.escape(head)]
    if load.by_project:
        lines.append(html.escape(" / ".join(f"{p.project} {p.peak * 100:.0f}%" for p in load.by_project)))
    return "&#10;".join(lines)


def heatmap_html(cross: CrossSummary) -> str:
    """人×稼働日の表。名前・プロジェクト名はエスケープする。"""
    first = next(iter(cross.loads.values()), None)
    days = first.days if first is not None else []
    head = "".join(
        f'<th class="text-caption" style="font-weight: normal; font-size: 10px; min-width: {CELL_PX}px">'
        f"<div>{day.day:%m/%d}</div><div>{WEEKDAYS[day.day.weekday()]}</div></th>"
        for day in days
    )
    rows = []
    for name, entry in cross.loads.items():
        cells = "".join(
            f'<td data-cell="{html.escape(name)}|{day.day.isoformat()}" title="{cell_title(name, day)}"'
            f' style="width: {CELL_PX}px; height: {CELL_PX}px; border: 1px solid rgba(128, 128, 128, 0.25);'
            f' {cell_style(day.total)}"></td>'
            for day in entry.days
        )
        rows.append(f'<tr><th class="heatmap-name text-body2" style="text-align: left">{html.escape(name)}</th>{cells}</tr>')
    return (
        '<div style="overflow-x: auto; max-width: 100%">'
        '<table style="border-collapse: separate; border-spacing: 2px">'
        f'<tr><th class="heatmap-name"></th>{head}</tr>{"".join(rows)}</table></div>'
    )


def legend_html() -> str:
    swatches = [(0.0, "0%"), (0.5, "50%"), (1.0, "100%"), (1.5, "超過")]
    items = "".join(
        f'<span style="display: inline-flex; align-items: center; gap: 4px; margin-right: 12px">'
        f'<span style="display: inline-block; width: 14px; height: 14px; {cell_style(value)};'
        f' border: 1px solid rgba(128, 128, 128, 0.25)"></span>{label}</span>'
        for value, label in swatches
    )
    return f'<div class="text-caption">{items}</div>'
```

(`cell_style` を凡例にも使うので、`0.0` は塗りなし、`1.5` は赤と枠線になる。凡例の 100% は `1.0` で青の最も濃い色。)

`build()` の先頭の `ui.add_css(PIE_CSS)` の次の行に `ui.add_css(HEATMAP_CSS)` を足す。`cards()` の `self.load_card(data)` の次の行に `self.heatmap_card(data)` を足す。`load_card` の後ろにメソッドを足す。

```python
    def heatmap_card(self, data: Dashboard) -> None:
        cross = data.cross
        if cross is None or not cross.loads:
            return
        box = card("負荷の日ごとの推移", "dashboard-heatmap")
        box.style("grid-column: 1 / -1")
        with box:
            if not any(entry.days for entry in cross.loads.values()):
                ui.label("稼働日がありません").classes("text-grey").mark("dashboard-heatmap-empty")
                return
            ui.html(legend_html(), sanitize=False)
            ui.html(heatmap_html(cross), sanitize=False).mark("dashboard-heatmap-table")
```

- [ ] **Step 4: 通ることを確認する(既存のビューのテストを含む)**

Run: `uv run pytest test/test_dashboard_view.py -q`
Expected: PASS(全件)

- [ ] **Step 5: 型チェックとコミット**

```bash
uv run ty check src
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: 負荷の日ごとのヒートマップを出す(要望47)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面までの確認と文書

**Files:**
- Test: `test/test_views.py`(`test_excluding_a_project_removes_it_from_the_total` の近く)
- Modify: `CLAUDE.md`、`.claude/MEMORY.md`、`docs/requests.md`、`docs/superpowers/specs/2026-10-22-load-heatmap-design.md`

**Interfaces:**
- Consumes: Task 1・2 の成果と、要望 31 の `change_dashboard_cross`・`change_dashboard_project`、`other_project`、`open_dashboard_view`

- [ ] **Step 1: 画面までの確認のテストを書く(Task 1・2 の結果をつなぐ確認なので、書いてすぐ通ってよい)**

```python
async def test_the_heatmap_follows_the_cross_switch_and_the_excluded_projects(user: User, tmp_path: Path) -> None:
    save_project(other_project("別", 6, 7, 1.0), tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-load-田中")
    await user.should_not_see(marker="dashboard-heatmap")  # 横断オフでは出ない
    view.change_dashboard_cross(True)
    await user.should_see(marker="dashboard-heatmap-table")
    both = user.find(marker="dashboard-heatmap-table").elements.pop().content
    assert "別 100%" in both
    view.change_dashboard_project("別", False)
    await asyncio.sleep(0.3)  # refresh は遅延実行なので、描き直されるのを待つ
    assert "別 100%" not in user.find(marker="dashboard-heatmap-table").elements.pop().content
    view.change_dashboard_cross(False)
    await asyncio.sleep(0.3)
    await user.should_not_see(marker="dashboard-heatmap")
```

- [ ] **Step 2: 実行する**

Run: `uv run pytest test/test_views.py -q -k heatmap`
Expected: PASS

- [ ] **Step 3: 文書を更新する**

`CLAUDE.md` のダッシュボードの節、`全プロジェクト` の項目の末尾に、次を足す。

```
 。オンのときは、その下に`負荷の日ごとの推移`のカード(全幅)を出す。人を行、稼働日(土日・祝日を除く)を列にした表で、セルの色が、その日の同時刻の割り当て率の合計の最大を示す(0% は塗りなし、1〜100% は青、100% 超は赤と太い枠線。濃さは値に比例)。横スクロールで、名前の列は固定。セルのマウスオーバーに、合計とプロジェクト別の内訳が出る
```

(既存の文末に続けて書く。`ほかのカードは、開いているプロジェクトのまま` の後ろに、句点なしで足す。)

設計書のセルの幅の記述 `幅 22px` を `幅 26px(見出しの 10/22 が収まる幅)` に直し、状態行を `実装済み(2026-10-22)` にする。`.claude/MEMORY.md` の 47 を `(完了。<PR は未>。実機確認は未。…)` の形にし、冒頭の `未着手は …・44〜47` から 47 を外す。`docs/requests.md` の要望 47 の見出しの下に状態の行(設計書・実装計画・決定)を足す。

- [ ] **Step 4: 全体のテストと型チェック、コミット**

```bash
uv run pytest -n auto -q
uv run ty check src
git add -A
git commit -m "docs: 要望47の仕様と記録を反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** 集計(Task 1)、置き場所・全幅・オンのときだけ・色・枠線・凡例・マウスオーバー・稼働日 0 日・エスケープ(Task 2)、画面までの確認と文書(Task 3)。`views.py`・`portfolio.py` は変えないことも守っている。
- **Placeholder scan:** なし。
- **Type consistency:** `ProjectPeak`・`DayLoad`・`CrossLoad.days`・`_day_totals`・`_stats_of`・`heatmap_html`・`legend_html`・`cell_style`・`cell_title`・マーカー名は各 Task で一致している。
- **設計書との差:** セルの幅を 22px から 26px にした(見出しの `10/22` を収めるため)。Task 3 で設計書を直す。
