# 名前の欄の幅をドラッグで調整する 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートの、タスクの名前の欄とチャートの境目をドラッグして、名前の欄の幅(120〜480px。既定 200px)を変えられるようにし、アプリ全体の設定として保存する(要望 23)。

**Architecture:** 幅を CSS 変数 `--name-w`(`chart-content` に設定)に持たせ、名前の欄の幅と、棒・印・◆・格子線・縞の位置を `calc(var(--name-w) + Npx)` で書く。ドラッグ中は JS が変数を書き換えるだけ(再描画なし)で、離したときに `chart_name_width` を送り、Python が検証・保存する。掴み場所は名前の欄の右端 6px の CSS 疑似要素(要素数は増えない)。保存は `config.json`(テーマと同じファイル。読んで更新して書く形に直す)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)、Node(JS の状態機械を偽の `document` で動かす既存のハーネス)

**Spec:** `docs/superpowers/specs/2026-10-06-name-width-design.md`

## Global Constraints

- 言語は日本語(画面の文言・コメント・コミットメッセージ)。識別子は英語。
- Python 3.13 以上。外部ライブラリは足さない。NiceGUI の内部関数の差し替え(モンキーパッチ)と、Tooltip の `title` 属性への置換はしない(`docs/development.md` の「描画速度の設計制約」)。
- 要素数を増やさない(掴み場所は疑似要素)。幅の変更で `render` を呼ばない。
- 幅の範囲は 120〜480px、既定は 200px(`config.py` の定数が唯一の定義元。JS には `chart-content` の `data-*` 属性で渡す)。
- 幅は `~/.projectapp/config.json` のキー `name_width`(整数)に保存する。プロジェクトのファイルには入れない。`theme` と互いに消さない。
- 既定の 200px のとき、表示は今と同じ。`timeline.py` の純粋関数は変えない。
- 日付に依存するテストは `base_date` を固定する(`BASE = date(2026, 10, 5)`)。
- 全体テストは `uv run pytest -n auto -q`(約 10 秒)。型チェックは `uvx ty check src`。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- ブランチは `feature/name-width`(作成済み)。マージとプッシュは、許可を得てから行う。

## Review Focus

仕様が暗に求めるが、各タスクの主なテストが扱わない入力・状態。それぞれ、担当のタスクにテストを足してある。

1. **範囲外・不正な保存値**: `config.json` の `name_width` が `9999`・`-5`・`"abc"`・`true`・`null`・`1e999`・`10**400` でも、起動でき、範囲内の幅(または既定)になる(Task 1)。
2. **テーマと幅が互いを消さない**: テーマを保存しても幅が、幅を保存してもテーマが、残る。ほかのキーも残る(Task 1)。
3. **幅が 200px 以外でも、位置が崩れない**: 幅 300px で、棒・印・◆の位置の式が同じ(境界からの相対値)で、期間指定の右端の判定(`MARK_WIDTH_PX`)も同じ結果になる(Task 2)。
4. **再描画で幅が戻らない**: 幅を変えたあと、スケールの切り替え・絞り込み・折りたたみで `render` が走っても、`--name-w` が保存した幅のまま(Task 3)。
5. **ドラッグ直後に、編集ダイアログが開かない・行の移動が始まらない**: 右端を掴んで離す(動かさなくても)と、`click` は打ち消され、`dragstart` は止められる。右端の外では何も起きない(Task 4)。

---

## ファイル構成

| ファイル | 責務 |
|---|---|
| `src/projectapp/config.py` | 幅の定数・`parse_name_width`・`load_name_width`・`save_name_width`。設定ファイルの「読んで更新して書く」 |
| `src/projectapp/gantt.py` | `name_width`・`from_name`・位置の式・`handle_name_width`・`GanttActions.set_name_width`・掴み場所のクラス |
| `src/projectapp/gantt_drag.py` | `RESIZE_EDGE_PX`・疑似要素の CSS・ドラッグとダブルクリックの JS |
| `src/projectapp/views.py` | 起動時の読み込み・保存・`fit_scale` への幅の受け渡し |
| `src/projectapp/preview.py` | `fit_scale` が幅を引数で受け取る |
| `test/test_config.py`(新規) | 設定の検証・読み書き |
| `test/test_gantt.py`・`test_gantt_drag.py`・`test_preview.py`・`test_views.py`・`test_leak_cleanup.py` | 上のとおり |
| `CLAUDE.md`・`docs/development.md`・`.claude/MEMORY.md`・設計書 | 仕様・構成の追記 |

---

### Task 1: 設定の幅(検証・読み書き)

**Files:**
- Modify: `src/projectapp/config.py`
- Create: `test/test_config.py`

**Interfaces:**
- Produces(後続のタスクが使う):
  - `DEFAULT_NAME_WIDTH_PX: int`(200)、`MIN_NAME_WIDTH_PX: int`(120)、`MAX_NAME_WIDTH_PX: int`(480)
  - `parse_name_width(value: object) -> int | None`
  - `load_name_width(base_dir: Path = BASE_DIR) -> int`
  - `save_name_width(width: int, base_dir: Path = BASE_DIR) -> None`
  - 既存の `load_theme` / `save_theme` の署名は変えない。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_config.py` を新規作成する。

```python
import json
from pathlib import Path

import pytest

from projectapp.config import (
    DEFAULT_NAME_WIDTH_PX,
    MAX_NAME_WIDTH_PX,
    MIN_NAME_WIDTH_PX,
    load_name_width,
    load_theme,
    parse_name_width,
    save_name_width,
    save_theme,
)


def test_the_width_constants() -> None:
    assert (MIN_NAME_WIDTH_PX, DEFAULT_NAME_WIDTH_PX, MAX_NAME_WIDTH_PX) == (120, 200, 480)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (200, 200),
        (120, 120),
        (480, 480),
        (119, 120),  # 範囲外は、範囲に収める
        (481, 480),
        (-5, 120),
        (10**400, 480),  # float に直せない大きさでも、落ちない
        (250.4, 250),  # 小数は、丸める
        (250.6, 251),
    ],
)
def test_parse_name_width_accepts_numbers_and_clamps(value: object, expected: int) -> None:
    assert parse_name_width(value) == expected


@pytest.mark.parametrize("value", [True, False, None, "200", "abc", [], {}, float("nan"), float("inf"), -float("inf")])
def test_parse_name_width_rejects_other_values(value: object) -> None:
    assert parse_name_width(value) is None


def test_load_name_width_defaults_without_a_file(tmp_path: Path) -> None:
    assert load_name_width(tmp_path) == DEFAULT_NAME_WIDTH_PX


def test_load_name_width_defaults_without_the_key(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    assert load_name_width(tmp_path) == DEFAULT_NAME_WIDTH_PX


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(300, 300), (9999, 480), (-5, 120), ("abc", 200), (True, 200), (None, 200), (1e999, 200), (10**400, 480)],
)
def test_load_name_width_reads_the_stored_value_safely(tmp_path: Path, stored: object, expected: int) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"name_width": stored}), encoding="utf-8")
    assert load_name_width(tmp_path) == expected


def test_save_name_width_creates_the_file_and_round_trips(tmp_path: Path) -> None:
    base = tmp_path / "new"  # まだ存在しない
    save_name_width(260, base)
    assert load_name_width(base) == 260
    assert json.loads((base / "config.json").read_text(encoding="utf-8")) == {"name_width": 260}


def test_saving_the_width_keeps_the_theme_and_other_keys(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "other": 1}), encoding="utf-8")
    save_name_width(300, tmp_path)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {
        "theme": "dark",
        "other": 1,
        "name_width": 300,
    }
    assert load_theme(tmp_path) == "dark"


def test_saving_the_theme_keeps_the_width(tmp_path: Path) -> None:
    save_name_width(300, tmp_path)
    save_theme("light", tmp_path)
    assert load_name_width(tmp_path) == 300
    assert load_theme(tmp_path) == "light"


def test_a_config_that_is_not_an_object_reads_as_empty_and_is_replaced_on_save(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("[1, 2]", encoding="utf-8")
    assert load_name_width(tmp_path) == DEFAULT_NAME_WIDTH_PX
    assert load_theme(tmp_path) == "auto"
    save_name_width(250, tmp_path)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {"name_width": 250}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: FAIL(`ImportError: cannot import name 'DEFAULT_NAME_WIDTH_PX'`)

- [ ] **Step 3: 最小の実装を書く**

`src/projectapp/config.py` 全体を次にする(テーマの読み書きの挙動は変えず、ファイルの読み書きを共通の関数にする)。

```python
"""アプリ設定(~/.projectapp/config.json)。"""

import json
from math import isfinite
from pathlib import Path

from projectapp.storage import BASE_DIR

THEMES = ("auto", "light", "dark")
DEFAULT_NAME_WIDTH_PX = 200  # ガントチャートの名前の欄の幅
MIN_NAME_WIDTH_PX = 120
MAX_NAME_WIDTH_PX = 480


def parse_name_width(value: object) -> int | None:
    """名前の欄の幅(px)の検証。有限の数(真偽値でない)を、丸めて、範囲に収める。それ以外は None。"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    return min(max(round(value), MIN_NAME_WIDTH_PX), MAX_NAME_WIDTH_PX)


def read_config(base_dir: Path) -> dict:
    """設定ファイルの中身。ファイルがないか、オブジェクトでなければ、空。"""
    path = base_dir / "config.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def update_config(updates: dict, base_dir: Path) -> None:
    """指定のキーだけを更新して書く(ほかのキーは残す)。"""
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / "config.json"
    path.write_text(json.dumps({**read_config(base_dir), **updates}), encoding="utf-8")


def load_theme(base_dir: Path = BASE_DIR) -> str:
    theme = read_config(base_dir).get("theme", "auto")
    return theme if theme in THEMES else "auto"


def save_theme(theme: str, base_dir: Path = BASE_DIR) -> None:
    update_config({"theme": theme}, base_dir)


def load_name_width(base_dir: Path = BASE_DIR) -> int:
    width = parse_name_width(read_config(base_dir).get("name_width"))
    return DEFAULT_NAME_WIDTH_PX if width is None else width


def save_name_width(width: int, base_dir: Path = BASE_DIR) -> None:
    update_config({"name_width": width}, base_dir)
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: PASS(全件)

Run: `uv run pytest test/test_views.py -q -k theme`
Expected: PASS(既存のテーマのテストが、そのまま通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/config.py test/test_config.py
git commit -m "$(cat <<'EOF'
設定: 名前の欄の幅の検証と読み書きを足し、設定ファイルを読んで更新して書く形にする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 描画の位置を `--name-w` に追従させる

**Files:**
- Modify: `src/projectapp/gantt.py`(定数・`GanttChart.__init__`・`content_width`・`render`・各描画関数・`marker_left`・`progress_marker`)
- Modify: `src/projectapp/preview.py:9,63`(`fit_scale`)
- Modify: `test/test_gantt.py`(新しいテストと、既存テストの位置の期待値)
- Modify: `test/test_preview.py:79-82`

**Interfaces:**
- Consumes: Task 1 の `DEFAULT_NAME_WIDTH_PX` / `MIN_NAME_WIDTH_PX` / `MAX_NAME_WIDTH_PX`。
- Produces(後続のタスクが使う):
  - `gantt.RESIZE_EDGE_PX` は Task 4 で `gantt_drag.py` に置く。この Task では、`data-name-edge` に使う値を、`gantt.py` に仮の定数 `RESIZE_EDGE_PX = 6` として置き、Task 4 で `gantt_drag` からの import に置き換える。
  - `GanttChart(project, holidays, actions, now=..., name_width: int = DEFAULT_NAME_WIDTH_PX)` と、属性 `GanttChart.name_width: int`
  - `from_name(px: float) -> str`(`gantt.py` のモジュール関数): `calc(var(--name-w) + {px:.1f}px)`
  - `chart-content` の要素: スタイル `--name-w: {name_width}px`、`props` に `data-name-min`・`data-name-max`・`data-name-default`・`data-name-edge`
  - `marker_left(...)` と `progress_marker(mark_left, ...)` の位置は、**境界(名前の欄の右端)からの距離**(名前の幅を含まない)
  - `preview.fit_scale(project, holidays, period, scale, name_width: int = DEFAULT_NAME_WIDTH_PX) -> Scale`
  - 定数 `NAME_WIDTH_PX` は、なくなる(`gantt.py`・テストとも)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の import を直す。`NAME_WIDTH_PX,`(48 行目付近)を削除し、`from_name` と `DEFAULT_NAME_WIDTH_PX` を足す。ファイルの先頭の import に `import re` を足し、`from projectapp.gantt import (...)` のリストに `from_name,` を、`from projectapp.config import DEFAULT_NAME_WIDTH_PX, MAX_NAME_WIDTH_PX, MIN_NAME_WIDTH_PX` の行を足す。

`test/test_gantt.py` の末尾に、次を追加する。

```python
def offset(left: str) -> float:
    """`from_name` の式から、境界(名前の欄の右端)からの距離(px)を取り出す。"""
    match = re.fullmatch(r"calc\(var\(--name-w\) \+ (-?[\d.]+)px\)", left)
    assert match, left
    return float(match.group(1))


def test_from_name_builds_a_calc_expression() -> None:
    assert from_name(20) == "calc(var(--name-w) + 20.0px)"
    assert from_name(-6) == "calc(var(--name-w) + -6.0px)"
    assert offset(from_name(104.5)) == 104.5


def test_the_chart_defaults_to_the_default_name_width() -> None:
    chart = GanttChart(sample_project(), {}, Recorder().actions)
    assert chart.name_width == DEFAULT_NAME_WIDTH_PX == 200


async def test_the_content_carries_the_name_width_variable_and_its_range(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    content = user.find(marker="chart-content").elements.pop()
    assert content._style["--name-w"] == "200px"
    props = content.props
    assert props["data-name-min"] == str(MIN_NAME_WIDTH_PX)
    assert props["data-name-max"] == str(MAX_NAME_WIDTH_PX)
    assert props["data-name-default"] == str(DEFAULT_NAME_WIDTH_PX)
    assert props["data-name-edge"] == "6"


async def test_the_variable_follows_the_chart_name_width(user: User) -> None:
    charts, _ = mount_chart(sample_project())
    await user.open("/")
    charts[0].name_width = 300
    charts[0].render.refresh()
    await settles(lambda: user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px")


def mount_with_width(project: Project, name_width: int, now: datetime = datetime(2026, 10, 1)) -> None:
    @ui.page("/")
    def index() -> None:
        GanttChart(project, {}, Recorder().actions, now=lambda: now, name_width=name_width).build()


async def test_positions_do_not_depend_on_the_name_width(user: User) -> None:
    # 位置は「境界からの距離」。幅が変わっても、棒・◆・印の式は同じで、変数だけが変わる
    project = sample_project()
    project.sections[0].tasks[0].deadline = datetime(2026, 10, 8, 12)
    mount_with_width(project, 300)
    await user.open("/")
    assert user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px"
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["left"] == from_name(20.0)
    marker = user.find(marker="deadline-0-0").elements.pop()
    assert marker._style["left"] == from_name(3.5 * 40 - DEADLINE_MARKER_HALF_PX)


async def test_the_name_columns_and_the_chart_edges_use_the_variable(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    assert user.find(marker="task-0-0").elements.pop()._style["width"] == "var(--name-w)"
    assert user.find(marker="section-name-0").elements.pop()._style["width"] == "var(--name-w)"
    for marker in ("label-row-spacer", "month-band-spacer", "year-band-spacer"):
        assert user.find(marker=marker).elements.pop()._style["width"] == "var(--name-w)", marker
    for marker in ("gridlines", "stripes"):
        assert user.find(marker=marker).elements.pop()._style["left"] == "var(--name-w)", marker


async def test_the_content_width_is_the_name_width_plus_the_columns(user: User) -> None:
    charts, _ = mount_chart(sample_project())
    await user.open("/")
    columns = build_columns(charts[0].project, Scale.DAY, {})
    content = user.find(marker="chart-content").elements.pop()
    assert content._style["width"] == from_name(COLUMN_WIDTH_PX[Scale.DAY] * len(columns))
    charts[0].name_width = 300
    assert charts[0].content_width() == 300 + COLUMN_WIDTH_PX[Scale.DAY] * len(columns)


@pytest.mark.parametrize("name_width", [120, 480])
async def test_the_late_done_mark_position_does_not_depend_on_the_name_width(user: User, name_width: int) -> None:
    # 印の位置は、境界からの距離。幅によらない
    mount_with_width(finished_project(datetime(2026, 10, 8, 12)), name_width, now=datetime(2026, 10, 20))
    await user.open("/")
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert mark._style["left"] == from_name(144.0)  # 実績の棒の右端 140 + 4


@pytest.mark.parametrize("name_width", [120, 480])
async def test_the_period_edge_check_for_the_state_mark_does_not_depend_on_the_name_width(
    user: User, name_width: int
) -> None:
    # 期間の右端の外へ、印を出さない判定は、境界からの距離で比べるので、幅によらない
    @ui.page("/")
    def index() -> None:
        chart = GanttChart(
            project_with(long_running_task(0)),
            {},
            Recorder().actions,
            now=lambda: datetime(2026, 10, 20),
            name_width=name_width,
        )
        chart.options = ViewOptions(period=(date(2026, 10, 1), date(2026, 10, 10)))
        chart.build()

    await user.open("/")
    await user.should_see(marker="bar-0-0")
    await user.should_not_see(marker="progress-state-0-0")  # 既存の、幅 200px での結果と同じ

- [ ] **Step 2: 新しいテストが失敗することを確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "from_name or name_width or variable or name_columns or content_width_is" -x`
Expected: FAIL(`ImportError: cannot import name 'from_name'` など)

- [ ] **Step 3: `gantt.py` を直す**

**3-1. import と定数**

`from projectapp.calendar import DayKind, day_kind` の次の行に足す。

```python
from projectapp.config import DEFAULT_NAME_WIDTH_PX, MAX_NAME_WIDTH_PX, MIN_NAME_WIDTH_PX
```

`NAME_WIDTH_PX = 200` の 1 行を、次に置き換える。

```python
RESIZE_EDGE_PX = 6  # 名前の欄の右端の、幅の調整の掴み場所の幅(Task 4 で gantt_drag へ移す)
NAME_WIDTH_PROPS = (  # JS が範囲と掴み場所の幅を読む。定義元は Python の定数
    f"data-chart-content data-name-min={MIN_NAME_WIDTH_PX} data-name-max={MAX_NAME_WIDTH_PX}"
    f" data-name-default={DEFAULT_NAME_WIDTH_PX} data-name-edge={RESIZE_EDGE_PX}"
)
```

`sticky_left` の定義の前(`def planned_background` の近く)に、モジュール関数を足す。

```python
def from_name(px: float) -> str:
    """名前の欄の右端(境界)からの距離を、CSS 変数 --name-w に追従する位置の式にする。"""
    return f"calc(var(--name-w) + {px:.1f}px)"
```

**3-2. `GanttChart.__init__`**

引数に `name_width: int = DEFAULT_NAME_WIDTH_PX,` を `now` の次に足し、本体に `self.name_width = name_width` を足す。

```python
        now: Callable[[], datetime] = datetime.now,
        name_width: int = DEFAULT_NAME_WIDTH_PX,
    ) -> None:
        ...
        self.now = now
        self.name_width = name_width  # 名前の欄の幅(px)。ドラッグで変わり、保存は呼び出し側
```

**3-3. `content_width`**

```python
        return self.name_width + COLUMN_WIDTH_PX[self.view_scale] * len(columns)
```

**3-4. `render`**

```python
        width = COLUMN_WIDTH_PX[self.view_scale]
        content = ui.element("div").style(
            f"position: relative; width: {from_name(width * len(columns))};"
            f" --name-w: {self.name_width}px"
        )
        with content.props(NAME_WIDTH_PROPS).mark("chart-content"):
```
(元の `total = NAME_WIDTH_PX + width * len(columns)` と `content = ...style(f"position: relative; width: {total}px")`、`content.props("data-chart-content")` を置き換える。)

**3-5. 名前の欄の幅(4 か所)を `var(--name-w)` に**

- `top_add_row`: `f"width: {NAME_WIDTH_PX}px; padding-right: 8px; align-self: stretch;"` → `f"width: var(--name-w); padding-right: 8px; align-self: stretch;"`
- `header_spacer`: `f"width: {NAME_WIDTH_PX}px; align-self: stretch; {sticky_left(STICKY_Z_SPACER)}"` → `f"width: var(--name-w); align-self: stretch; {sticky_left(STICKY_Z_SPACER)}"`
- `section_rows`: `f"width: {NAME_WIDTH_PX}px; overflow: hidden; align-self: stretch;"` → `f"width: var(--name-w); overflow: hidden; align-self: stretch;"`
- `task_row` の `cell_style`: `f"width: {NAME_WIDTH_PX}px; padding-left: 16px; padding-right: 4px;"` → `f"width: var(--name-w); padding-left: 16px; padding-right: 4px;"`

**3-6. 格子線・縞・帯のラベル(固定位置)**

- `gridlines` と `stripes`(同じ行が 2 つ): `f"position: absolute; top: {top}px; bottom: 0; left: {NAME_WIDTH_PX}px;"` → `f"position: absolute; top: {top}px; bottom: 0; left: var(--name-w);"`(2 か所とも)
- `band_row` のラベル: `f"position: sticky; left: {NAME_WIDTH_PX}px; display: inline-block;"` → `f"position: sticky; left: var(--name-w); display: inline-block;"`

**3-7. 棒・実績の棒・点線の `left`**

次の行は、3 か所(`task_row` の予定の棒・`actual_bars` の実績の棒・同じく間の点線)にある。3 か所とも置き換える。

```python
f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
```
→
```python
f"position: absolute; left: {from_name(left * width)};"
```

**3-8. 印の位置を、境界からの距離にする**

`task_row` の印の箇所(元は `NAME_WIDTH_PX + left * width + bar_width` を渡し、`total = NAME_WIDTH_PX + width * len(columns)` と比べている)を直す。

```python
                mark_left = self.marker_left(task, columns, width, left * width + bar_width)
                total = width * len(columns)
                if self.options.period is None or mark_left <= total - MARK_WIDTH_PX:
                    self.progress_marker(key, ti, task, state, mark_left, end)  # 期間の右端の外へは出さない
```

`marker_left` の本体の 2 か所(と docstring)を直す。

```python
    def marker_left(
        self, task: Task, columns: list[Column], width: int, bar_right: float
    ) -> float:
        """印の左端(境界からの距離)。予定の棒と、それより右へ伸びる実績の棒(完了の遅れや進行中)の右に置き、
        締切の◆と重なるときは◆の右へずらす。bar_right も、境界からの距離。"""
        right = bar_right
        for actual in task.actuals:
            ...
            right = max(right, start * width + max(length * width, MIN_BAR_PX))
        left = right + MARK_GAP_PX
        position = None if task.deadline is None else deadline_position(task.deadline, columns)
        if position is not None:
            center = position * width
            ...
```
(`NAME_WIDTH_PX + ` を、2 か所から取り除く。ほかの行は変えない。)

`progress_marker` の `left` を直す。

```python
            f"position: absolute; left: {from_name(mark_left)}; top: {BAR_TOP_PX}px;"
```
(元は `left: {mark_left:.1f}px;`)

**3-9. 締切の ◆**

```python
        left = position * width - DEADLINE_MARKER_HALF_PX
        marker = ui.label("◆").style(
            f"position: absolute; left: {from_name(left)}; top: 4px; line-height: 1;"
```
(元は `left = NAME_WIDTH_PX + position * width - DEADLINE_MARKER_HALF_PX` と `left: {left:.1f}px;`)

**3-10. 取りこぼしの確認**

Run: `grep -n "NAME_WIDTH_PX" src/projectapp/*.py`
Expected: `preview.py` の 2 行(次のステップで直す)以外に、出力がない。

- [ ] **Step 4: `preview.py` を直す**

```python
from projectapp.config import DEFAULT_NAME_WIDTH_PX
from projectapp.gantt import COLUMN_WIDTH_PX, ViewOptions
```
(元は `from projectapp.gantt import COLUMN_WIDTH_PX, NAME_WIDTH_PX, ViewOptions`)

```python
def fit_scale(
    project: Project,
    holidays: dict[date, str],
    period: tuple[date, date] | None,
    scale: Scale,
    name_width: int = DEFAULT_NAME_WIDTH_PX,
) -> Scale:
    """全期間の画像の幅が快適な幅に収まるまで、スケールを 1 段ずつ粗くする。細かくはしない。月次は、広くても月次。"""
    for candidate in COARSER[COARSER.index(scale) :]:
        columns = build_columns(project, candidate, holidays, period)
        if name_width + COLUMN_WIDTH_PX[candidate] * len(columns) <= PREVIEW_COMFORT_WIDTH_PX:
            return candidate
    return Scale.MONTH
```

- [ ] **Step 5: 新しいテストが通ることを確かめる**

Run: `uv run pytest test/test_gantt.py -q -k "from_name or name_width or variable or name_columns or content_width_is or late_done_mark_is_inside"`
Expected: PASS(全件)

- [ ] **Step 6: 既存テストの期待値を、新しい式に直す**

Run: `uv run pytest test/test_gantt.py test/test_preview.py -q 2>&1 | tail -40`
Expected: 位置と幅の期待値が古い、次の失敗が出る。次の対応で直す(確かめる内容は変えない。値を `from_name(...)` と `"var(--name-w)"` に置き換えるだけ)。

`test/test_gantt.py`(行番号は目安。関数名で探す):

| テスト(関数名) | 変更前 | 変更後 |
|---|---|---|
| `test_bar_geometry_and_color` | `bar._style["left"] == "220.0px"` | `== from_name(20.0)` |
| 日次以外のスケールの棒(`"204.0px"` のテスト) | `== "204.0px"` | `== from_name(4.0)` |
| セクションなしのタスクの棒(`bar-top-0`) | `== "220.0px"` | `== from_name(20.0)` |
| `test_band_labels_stay_visible_when_scrolled_horizontally` | `== f"{NAME_WIDTH_PX}px"` | `== "var(--name-w)"` |
| `test_add_row_is_right_aligned_in_the_name_column` | `cell._style["width"] == "200px"` | `== "var(--name-w)"` |
| `test_the_deadline_marker_is_placed_at_the_deadline` | `f"{200 + 3.5 * 40 - DEADLINE_MARKER_HALF_PX:.1f}px"` | `from_name(3.5 * 40 - DEADLINE_MARKER_HALF_PX)` |
| `test_actual_bar_is_drawn_in_the_lower_half_with_the_task_color` | `== "260.0px"` | `== from_name(60.0)` |
| 進捗の状態の印(`mark._style["left"] == "304.0px"`) | `"304.0px"` | `from_name(104.0)` |
| `test_late_done_mark_does_not_overlap_the_longer_actual_bar` | 下の置き換え | |
| `test_mark_stays_next_to_the_planned_bar_when_the_actual_is_shorter` | `== "304.0px"` | `== from_name(104.0)` |
| `test_delayed_mark_clears_an_in_progress_actual_bar_that_runs_past_the_plan` | 下の置き換え | |
| `test_mark_does_not_overlap_the_deadline_diamond` | `== "310.0px"  # ◆の右端 306 + 4` | `== from_name(110.0)  # ◆の右端 106 + 4` |
| `test_mark_ignores_a_far_away_deadline` | `== "304.0px"` | `== from_name(104.0)` |
| 実績の間の点線(`gap._style["left"] == "220.0px"`) | `"220.0px"` | `from_name(20.0)` |
| 名前の欄の幅(`cell._style["width"] == "200px"`、タスクの名前の欄の構造のテスト) | `"200px"` | `"var(--name-w)"` |
| 名前の欄の幅(`name._style["width"] == f"{NAME_WIDTH_PX}px"`、固定表示のテスト) | `f"{NAME_WIDTH_PX}px"` | `"var(--name-w)"` |
| `pinned(user, "section-name-0")._style["width"]` | `== f"{NAME_WIDTH_PX}px"` | `== "var(--name-w)"` |
| `test_period_sets_the_first_column_and_clips_bars_at_the_edge` | `bar._style["left"] == "200.0px"` | `== from_name(0.0)` |
| `content_width` のテスト | 下の置き換え | |

次の 3 つは、式の置き換えが 1 行では足りないので、本体を書き換える。

`test_late_done_mark_does_not_overlap_the_longer_actual_bar`:

```python
    actual = user.find(marker="actual-0-0-0").elements.pop()
    actual_right = offset(actual._style["left"]) + float(actual._style["width"][:-2])
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert actual_right == 140.0  # 3.5 * 40
    assert mark._style["left"] == from_name(144.0)  # 実績の棒の右端 + 4
```

`test_delayed_mark_clears_an_in_progress_actual_bar_that_runs_past_the_plan`:

```python
    actual = user.find(marker="actual-0-0-0").elements.pop()
    actual_right = offset(actual._style["left"]) + float(actual._style["width"][:-2])
    mark = user.find(marker="progress-state-0-0").elements.pop()
    assert offset(mark._style["left"]) >= actual_right + 4
```

`content_width` のテスト(`chart.content_width() == NAME_WIDTH_PX + ...` の 2 か所と、`content._style["width"] == f"{chart.content_width()}px"`):

```python
    assert chart.content_width() == DEFAULT_NAME_WIDTH_PX + COLUMN_WIDTH_PX[Scale.DAY] * len(columns)
    content = user.find(marker="chart-content").elements.pop()
    assert "data-chart-content" in content.props
    assert content._style["width"] == from_name(COLUMN_WIDTH_PX[Scale.DAY] * len(columns))
    chart.set_options(ViewOptions(scale=Scale.WEEK))
    weeks = build_columns(chart.project, Scale.WEEK, {})
    assert chart.content_width() == DEFAULT_NAME_WIDTH_PX + COLUMN_WIDTH_PX[Scale.WEEK] * len(weeks)
```

棒の内側の縞の `left`(`"80.0px"`・`"0.0px"`・`stripe._style["left"]`)は、棒の左端からの距離なので、**変えない**。

`test/test_preview.py` の `width_of`:

```python
def width_of(project: Project, scale: Scale) -> int:
    from projectapp.config import DEFAULT_NAME_WIDTH_PX
    from projectapp.gantt import COLUMN_WIDTH_PX
    from projectapp.timeline import build_columns

    return DEFAULT_NAME_WIDTH_PX + COLUMN_WIDTH_PX[scale] * len(build_columns(project, scale, {}))
```

`fit_scale` が幅を使うことの確認を、`test/test_preview.py` の末尾に足す。

```python
def test_fit_scale_uses_the_name_width() -> None:
    from projectapp.gantt import COLUMN_WIDTH_PX
    from projectapp.timeline import build_columns

    project = project_of_days(100)
    day_columns = len(build_columns(project, Scale.DAY, {}))
    exact = PREVIEW_COMFORT_WIDTH_PX - COLUMN_WIDTH_PX[Scale.DAY] * day_columns  # 日次が、ちょうど収まる幅
    assert fit_scale(project, {}, None, Scale.DAY, exact) is Scale.DAY
    assert fit_scale(project, {}, None, Scale.DAY, exact + 1) is Scale.WEEK  # 1px 広いと、収まらず週次
```

- [ ] **Step 7: ファイル全体が通ることを確かめる**

Run: `uv run pytest test/test_gantt.py test/test_preview.py test/test_gantt_drag.py test/test_views.py -n auto -q 2>&1 | tail -15`
Expected: PASS。残った失敗は、上の対応表と同じ規則(位置は `from_name`、幅は `"var(--name-w)"`)で直す。

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 8: コミット**

```bash
git add src/projectapp/gantt.py src/projectapp/preview.py test/test_gantt.py test/test_preview.py
git commit -m "$(cat <<'EOF'
ガントチャートの位置を CSS 変数 --name-w に追従させる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 幅の受け取り・保存・読み込み(Python 側の配線)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions`・`build`・`handle_name_width`)
- Modify: `src/projectapp/views.py`
- Modify: `test/test_gantt.py`(`Recorder`・テスト)、`test/test_leak_cleanup.py:27`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `parse_name_width` / `load_name_width` / `save_name_width`、Task 2 の `GanttChart.name_width` と `fit_scale(..., name_width)`。
- Produces:
  - `GanttActions.set_name_width: Callable[[int], object]`(最後のフィールド)
  - `GanttChart.handle_name_width(args: object) -> None`(イベント名 `chart_name_width`、`args = {"width": number}`)
  - `MainView.set_name_width(width: int) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` の `Recorder.__init__` の `GanttActions(...)` に、最後の引数を足す。

```python
            shift_task=lambda si, ti, days: self.events.append(("shift_task", (si, ti, days))),
            set_name_width=lambda width: self.events.append(("set_name_width", (width,))),
```

`test/test_leak_cleanup.py:27` を直す。

```python
NOOP = GanttActions(*([lambda *args, **kwargs: None] * 7))
```

`test/test_gantt.py` の末尾に足す。

```python
async def test_handle_name_width_updates_the_width_and_reports_it(user: User) -> None:
    charts, recorder = mount_chart(sample_project())
    await user.open("/")
    charts[0].handle_name_width({"width": 300})
    assert charts[0].name_width == 300
    assert recorder.events == [("set_name_width", (300,))]


async def test_handle_name_width_clamps_out_of_range_values(user: User) -> None:
    charts, recorder = mount_chart(sample_project())
    await user.open("/")
    charts[0].handle_name_width({"width": 9999})
    charts[0].handle_name_width({"width": 1})
    assert [event[1] for event in recorder.events] == [(480,), (120,)]
    assert charts[0].name_width == 120


@pytest.mark.parametrize(
    "args",
    [None, 300, "300", [300], {}, {"width": None}, {"width": "300"}, {"width": True}, {"width": float("nan")}],
)
async def test_handle_name_width_ignores_bad_events(user: User, args: object) -> None:
    charts, recorder = mount_chart(sample_project())
    await user.open("/")
    charts[0].handle_name_width(args)
    assert recorder.events == []
    assert charts[0].name_width == DEFAULT_NAME_WIDTH_PX


async def test_handle_name_width_does_not_redraw(user: User) -> None:
    charts, _ = mount_chart(sample_project())
    await user.open("/")
    before = user.find(marker="chart-content").elements.pop()
    charts[0].handle_name_width({"width": 300})
    await asyncio.sleep(0.05)
    assert user.find(marker="chart-content").elements.pop() is before  # 描き直されていない


async def test_the_saved_width_survives_a_redraw(user: User) -> None:
    # 幅を変えたあと、スケールの切り替え・絞り込み・折りたたみで描き直しても、幅が戻らない
    charts, _ = mount_chart(sample_project())
    await user.open("/")
    charts[0].handle_name_width({"width": 300})
    charts[0].set_scale(Scale.WEEK)
    await settles(lambda: user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px")
    charts[0].set_filter(TaskFilter(query="設計"))
    await settles(lambda: user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px")
    charts[0].toggle_section(0)
    await settles(lambda: user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px")
```

`test/test_views.py` の末尾に足す。

```python
async def test_the_saved_name_width_is_restored_on_startup(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"theme": "dark", "name_width": 300}), encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].gantt.name_width == 300
    assert user.find(marker="chart-content").elements.pop()._style["--name-w"] == "300px"


async def test_a_bad_saved_name_width_falls_back_to_the_default(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"name_width": "abc"}), encoding="utf-8")
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    assert views[0].gantt.name_width == 200


async def test_changing_the_name_width_saves_it_without_losing_the_theme(user: User, tmp_path: Path) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    views[0].set_theme("dark")
    views[0].gantt.handle_name_width({"width": 260})
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved == {"theme": "dark", "name_width": 260}


async def test_the_preview_fits_the_scale_with_the_current_name_width(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    views[0].gantt.handle_name_width({"width": 333})
    seen: list[int] = []
    import projectapp.views as views_module

    original = views_module.fit_scale
    monkeypatch.setattr(
        views_module,
        "fit_scale",
        lambda *args, **kwargs: seen.append(args[4] if len(args) > 4 else kwargs["name_width"]) or original(*args, **kwargs),
    )
    views[0].enter_preview()
    assert seen == [333]
```

(`test_views.py` の先頭に `import json` と `import pytest` がなければ足す。`Path` は既存。)

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest test/test_gantt.py test/test_views.py test/test_leak_cleanup.py -q -k "name_width or saved_width or leak" -x`
Expected: FAIL(`TypeError: GanttActions.__init__() got an unexpected keyword argument 'set_name_width'` など)

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py`:

`GanttActions` の最後に足す。

```python
    shift_task: Callable[[int | None, int, int], object]  # セクション番号, タスク番号, 日数
    set_name_width: Callable[[int], object]  # 名前の欄の幅(px)。範囲に収めた整数。保存は受け取り側
```

import に `parse_name_width` を足す(`from projectapp.config import DEFAULT_NAME_WIDTH_PX, MAX_NAME_WIDTH_PX, MIN_NAME_WIDTH_PX, parse_name_width`)。

`handle_shift` の次に足す。

```python
    def handle_name_width(self, args: object) -> None:
        """名前の欄の幅の変更を受ける。不正な値は無視し、範囲外は範囲に収める。
        描き直さない(ブラウザ側の --name-w が、すでに同じ値)。以降の描画は、この値を使う。"""
        width = parse_name_width(args.get("width") if isinstance(args, dict) else None)
        if width is None:
            return
        self.name_width = width
        self.actions.set_name_width(width)
```

`build` の `ui.on("chart_shift", ...)` の次に足す。

```python
        ui.on("chart_name_width", lambda e: self.handle_name_width(e.args))
```

`src/projectapp/views.py`:

import を直す。

```python
from projectapp.config import THEMES, load_name_width, load_theme, save_name_width, save_theme
```

`GanttChart(...)` の生成を直す。

```python
        self.gantt = GanttChart(
            self.project,
            self.holidays,
            GanttActions(
                add_section=self.add_section,
                add_task=self.add_task,
                add_top_task=self.add_top_task,
                edit_task=self.edit_task,
                move_task=self.move_task,
                shift_task=self.shift_task,
                set_name_width=self.set_name_width,
            ),
            name_width=load_name_width(base_dir),
        )
```

`set_theme` の次にメソッドを足す。

```python
    def set_name_width(self, width: int) -> None:
        """名前の欄の幅を、アプリ全体の設定として保存する。プロジェクトのデータには入れない。"""
        save_name_width(width, self.base_dir)
```

`enter_preview` の `fit_scale` の呼び出しを直す。

```python
        scale = fit_scale(self.project, self.holidays, period, self.gantt.scale, self.gantt.name_width)
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -8`
Expected: PASS(全件)

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gantt.py src/projectapp/views.py test/test_gantt.py test/test_views.py test/test_leak_cleanup.py
git commit -m "$(cat <<'EOF'
名前の欄の幅: イベントの受け取りと、アプリ設定への保存・復元を配線する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 境界のドラッグ操作(掴み場所と JS)

**Files:**
- Modify: `src/projectapp/gantt_drag.py`(`RESIZE_EDGE_PX`・`NAME_RESIZE_CSS`・`CHART_DRAG_JS`)
- Modify: `src/projectapp/gantt.py`(掴み場所のクラス・`RESIZE_EDGE_PX` の import・CSS の登録)
- Modify: `test/test_gantt_drag.py`(静的な確認・ハーネス)、`test/test_gantt.py`(クラスの確認)

**Interfaces:**
- Consumes: Task 2 の `NAME_WIDTH_PROPS`(`data-name-min` / `-max` / `-default` / `-edge`)、Task 3 の `chart_name_width` イベント。
- Produces:
  - `gantt_drag.RESIZE_EDGE_PX = 6`、`gantt_drag.NAME_RESIZE_CSS`(`.gantt-name-resizable::after`)
  - 名前の欄(タスクの行・セクション見出し・見出しの空白 3 つ・タスク追加の行)のクラス `gantt-name-resizable`(読み取り専用では付かない)
  - JS: `emitEvent("chart_name_width", {width})`

- [ ] **Step 1: 失敗するテストを書く(Python 側)**

`test/test_gantt.py` の末尾に足す。

```python
RESIZABLE = "gantt-name-resizable"


async def test_the_name_columns_are_resizable_at_the_right_edge(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    for marker in (
        "task-0-0",
        "section-name-0",
        "year-band-spacer",
        "month-band-spacer",
        "label-row-spacer",
        "add-task-top",  # ボタンの親(名前の欄)を、下で確かめる
    ):
        element = user.find(marker=marker).elements.pop()
        if marker == "add-task-top":
            element = element.parent_slot.parent
        assert RESIZABLE in element.classes, marker


async def test_the_read_only_chart_has_no_resize_handle(user: User) -> None:
    mount_with(sample_project(), ViewOptions(read_only=True))
    await user.open("/")
    for marker in ("task-0-0", "section-name-0", "label-row-spacer"):
        assert RESIZABLE not in user.find(marker=marker).elements.pop().classes, marker
```

(`add-task-top` は読み取り専用では出ない。`top_add_row` は読み取り専用で何も描かない。)

`test/test_gantt_drag.py` に、静的な確認を足す(`test_the_script_emits_the_events_the_python_side_listens_to` の次)。

```python
def test_the_script_has_the_name_width_pieces() -> None:
    assert 'emitEvent("chart_name_width"' in CHART_DRAG_JS
    assert "gantt-name-resizable" in CHART_DRAG_JS
    for name in ("nameMin", "nameMax", "nameDefault", "nameEdge"):
        assert name in CHART_DRAG_JS
    assert "dblclick" in CHART_DRAG_JS


def test_the_resize_css_draws_a_column_resize_handle_of_the_edge_width() -> None:
    from projectapp.gantt_drag import NAME_RESIZE_CSS, RESIZE_EDGE_PX

    assert ".gantt-name-resizable::after" in NAME_RESIZE_CSS
    assert "cursor: col-resize" in NAME_RESIZE_CSS
    assert f"width: {RESIZE_EDGE_PX}px" in NAME_RESIZE_CSS
```

- [ ] **Step 2: ハーネスのテストを書く**

`test/test_gantt_drag.py` の `HARNESS` を直す。

(a) `global.window = {};` から `global.document = {...};` までを、次に置き換える。

```js
global.window = {};
const area = {  // chart-content。範囲と掴み場所の幅は、data-* 属性で渡される
  dataset: { nameMin: "120", nameMax: "480", nameDefault: "200", nameEdge: "6" },
  vars: { "--name-w": "200px" },
  style: { setProperty(name, value) { area.vars[name] = value; } },
};
global.getComputedStyle = (el) => ({ getPropertyValue: (name) => el.vars[name] });
global.document = {
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  querySelectorAll: () => [],
  querySelector: (selector) => (selector === "[data-chart-content]" ? area : null),
  body: { style: {} },
};
```

(b) `console.log(JSON.stringify(scenarios));` の直前に、次を足す。

```js
// 名前の欄の幅の調整(右端 6px を掴む)。欄の右端は x=200
const cell = {
  draggable: true,
  closest(selector) { return selector === ".gantt-name-resizable" ? this : null; },
  getBoundingClientRect: () => ({ right: 200 }),
  setPointerCapture() {},
};
const edge = (x) => ({ target: cell, button: 0, pointerId: 1, clientX: x, buttons: 1, preventDefault() {} });
const width = () => area.vars["--name-w"];

// 通常: 右端を掴んで 100px 動かす
fire("pointerdown", edge(197)); fire("pointermove", edge(297));
const during = { width: width(), draggable: cell.draggable, cursor: document.body.style.cursor };
fire("pointerup", edge(297));
scenarios.resize = {
  during, emitted: emitted.splice(0), width: width(), draggable: cell.draggable,
  cursor: document.body.style.cursor, suppressed: click(),
};
flush();

// 範囲: 上限と下限で止まる(開始の幅 300 から)
fire("pointerdown", edge(197)); fire("pointermove", edge(1197));
const max = width();
fire("pointermove", edge(-1803));
const min = width();
fire("pointerup", edge(-1803));
scenarios.clamp = { max, min, emitted: emitted.splice(0) };
click(); flush();

// 動かさずに離す: 送らないが、click は打ち消す(編集ダイアログを開かない)
fire("pointerdown", edge(197)); fire("pointerup", edge(197));
scenarios.noMove = { emitted: emitted.splice(0), width: width(), suppressed: click() };
flush();

// 右端の外: 何も始めない(click も打ち消さない)
fire("pointerdown", edge(100)); fire("pointermove", edge(150)); fire("pointerup", edge(150));
scenarios.outside = { emitted: emitted.splice(0), width: width(), suppressed: click() };
flush();

// ダブルクリック: 既定の幅に戻して送る(2 回の click は、どちらも打ち消す)
fire("pointerdown", edge(197)); fire("pointerup", edge(197)); const firstClick = click();
fire("pointerdown", edge(197)); fire("pointerup", edge(197)); const secondClick = click();
fire("dblclick", edge(197));
scenarios.reset = { emitted: emitted.splice(0), width: width(), clicks: [firstClick, secondClick] };
flush();

// pointercancel: 元の幅に戻し、何も送らない
fire("pointerdown", edge(197)); fire("pointermove", edge(297)); fire("pointercancel", edge(297));
fire("pointermove", edge(397)); fire("pointerup", edge(397));
scenarios.cancel = { emitted: emitted.splice(0), width: width(), draggable: cell.draggable };
flush();

// ボタンが離れているのに pointermove が来たら、掴んだ状態を捨てる
fire("pointerdown", edge(197)); fire("pointermove", edge(297));
fire("pointermove", { ...edge(397), buttons: 0 });
fire("pointermove", edge(497)); fire("pointerup", edge(497));
scenarios.released = { emitted: emitted.splice(0), width: width() };
flush();

// Esc: 元の幅に戻し、送らない。離したあとの click は打ち消す
fire("pointerdown", edge(197)); fire("pointermove", edge(297)); fire("keydown", { key: "Escape" });
const afterEscape = width();
fire("pointermove", edge(397)); fire("pointerup", edge(397));
scenarios.escape = { afterEscape, emitted: emitted.splice(0), width: width(), suppressed: click() };
flush();

// 掴んでいる間は、行の移動(HTML5 の drag)を始めない
fire("pointerdown", edge(197));
const dragEvent = { target: cell, prevented: false, preventDefault() { this.prevented = true; } };
fire("dragstart", dragEvent);
scenarios.dragstart = dragEvent.prevented;
fire("pointerup", edge(197)); click(); flush();
```

`test/test_gantt_drag.py` の末尾(`test_js_a_drop_that_did_not_start_from_a_row_is_ignored` の次)に足す。

```python
def test_js_resizing_the_name_column_follows_the_pointer_and_sends_the_width(js_scenarios: dict) -> None:
    resize = js_scenarios["resize"]
    assert resize["during"] == {"width": "300px", "draggable": False, "cursor": "col-resize"}  # 動かすだけ。欄の drag は止める
    assert resize["emitted"] == [["chart_name_width", {"width": 300}]]
    assert resize["width"] == "300px"
    assert resize["draggable"] is True  # 離したら、欄の drag を戻す
    assert resize["cursor"] == ""
    assert resize["suppressed"] is True  # 離したあとの click で、編集ダイアログを開かない


def test_js_the_width_stops_at_the_range_limits(js_scenarios: dict) -> None:
    clamp = js_scenarios["clamp"]
    assert (clamp["max"], clamp["min"]) == ("480px", "120px")
    assert clamp["emitted"] == [["chart_name_width", {"width": 120}]]


def test_js_releasing_without_moving_sends_nothing_but_swallows_the_click(js_scenarios: dict) -> None:
    assert js_scenarios["noMove"] == {"emitted": [], "width": "120px", "suppressed": True}


def test_js_outside_the_right_edge_nothing_starts(js_scenarios: dict) -> None:
    assert js_scenarios["outside"] == {"emitted": [], "width": "120px", "suppressed": False}


def test_js_double_clicking_the_edge_resets_to_the_default_width(js_scenarios: dict) -> None:
    reset = js_scenarios["reset"]
    assert reset["emitted"] == [["chart_name_width", {"width": 200}]]
    assert reset["width"] == "200px"
    assert reset["clicks"] == [True, True]  # 2 回の click は、どちらも編集を開かない


def test_js_pointercancel_restores_the_width_without_sending(js_scenarios: dict) -> None:
    assert js_scenarios["cancel"] == {"emitted": [], "width": "200px", "draggable": True}


def test_js_a_pointermove_without_buttons_drops_the_resize(js_scenarios: dict) -> None:
    assert js_scenarios["released"] == {"emitted": [], "width": "200px"}


def test_js_escape_restores_the_width_and_still_swallows_the_click(js_scenarios: dict) -> None:
    assert js_scenarios["escape"] == {
        "afterEscape": "200px",
        "emitted": [],
        "width": "200px",
        "suppressed": True,
    }


def test_js_the_row_drag_does_not_start_while_resizing(js_scenarios: dict) -> None:
    assert js_scenarios["dragstart"] is True
```

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `uv run pytest test/test_gantt_drag.py test/test_gantt.py -q -k "resiz or name_width_pieces or resize_css or js_" 2>&1 | tail -20`
Expected: FAIL(`cannot import name 'NAME_RESIZE_CSS'`、ハーネスの `resize` の値が `undefined` など)

- [ ] **Step 4: `gantt_drag.py` を実装する**

ファイルの先頭の docstring の次(`CHART_DRAG_CSS` の前)に足す。

```python
RESIZE_EDGE_PX = 6  # 名前の欄の右端の、幅の調整の掴み場所の幅
# 名前の欄の右端の掴み場所。疑似要素なので、要素は増えない(欄は position: sticky なので、基準になる)
NAME_RESIZE_CSS = f"""
.gantt-name-resizable::after {{
  content: ""; position: absolute; top: 0; right: 0; bottom: 0;
  width: {RESIZE_EDGE_PX}px; cursor: col-resize;
}}
"""
```

`CHART_DRAG_JS` を直す。

(1) 冒頭の `let source = null;` の次に足す。

```js
  let resize = null;  // 名前の欄の幅の調整中の状態
```

(2) 既存の `dragstart` のリスナーの先頭(`const handle = ...` の前)に足す。

```js
    if (resize) {  // 幅の調整中は、欄の drag(行の移動)を始めない
      event.preventDefault();
      return;
    }
```

(3) ファイル末尾の `document.addEventListener("click", ..., true);` の次、`})();` の前に足す。

```js

  // 名前の欄の幅の調整。右端を掴み、--name-w を書き換えるだけにする(再描画しない)。離したときだけ幅を送る
  const content = () => document.querySelector("[data-chart-content]");
  const edgeCell = (event) => {  // ポインタが、名前の欄の右端にあれば、その欄を返す
    const cell = event.target.closest ? event.target.closest(".gantt-name-resizable") : null;
    const area = content();
    if (!cell || !area) return null;
    const right = cell.getBoundingClientRect().right;
    return event.clientX <= right && event.clientX >= right - Number(area.dataset.nameEdge) ? cell : null;
  };
  const setWidth = (area, value) => area.style.setProperty("--name-w", `${value}px`);
  const endResize = (restore) => {  // 掴んだ状態を捨てる。restore なら、掴む前の幅に戻す
    if (!resize) return null;
    const done = resize;
    resize = null;
    if (restore) setWidth(done.area, done.start);
    done.cell.draggable = done.draggable;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    return done;
  };

  document.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const cell = edgeCell(event);
    if (!cell) return;
    event.preventDefault();
    const area = content();
    const start = parseFloat(getComputedStyle(area).getPropertyValue("--name-w"));
    resize = { cell, area, x0: event.clientX, start, width: start, draggable: cell.draggable, cancelled: false };
    cell.draggable = false;  // 欄は行の移動の掴み場所でもあるので、幅の調整中は止める
    cell.setPointerCapture(event.pointerId);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("pointermove", (event) => {
    if (!resize) return;
    if (event.buttons === 0) {  // 放したのに pointerup が届かなかった
      endResize(true);
      return;
    }
    if (resize.cancelled) return;
    const min = Number(resize.area.dataset.nameMin);
    const max = Number(resize.area.dataset.nameMax);
    resize.width = Math.round(Math.min(Math.max(resize.start + event.clientX - resize.x0, min), max));
    setWidth(resize.area, resize.width);
  });

  document.addEventListener("pointerup", () => {
    const done = endResize(false);
    if (!done) return;
    suppressClick = true;  // 離したあとの click で、編集ダイアログが開かないようにする(動かさなくても)
    setTimeout(() => { suppressClick = false; }, 0);
    if (!done.cancelled && done.width !== done.start) {
      emitEvent("chart_name_width", { width: done.width });
    }
  });

  document.addEventListener("pointercancel", () => endResize(true));
  document.addEventListener("lostpointercapture", () => endResize(true));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !resize || resize.cancelled) return;
    resize.cancelled = true;  // 離すまで掴んだままにし、離したあとの click だけ打ち消す
    setWidth(resize.area, resize.start);
  });

  document.addEventListener("dblclick", (event) => {  // 右端のダブルクリックで、既定の幅へ戻す
    if (!edgeCell(event)) return;
    const area = content();
    const width = Number(area.dataset.nameDefault);
    setWidth(area, width);
    emitEvent("chart_name_width", { width });
  });
```

- [ ] **Step 5: `gantt.py` を実装する**

import を直す(Task 2 の仮の定数をなくし、`gantt_drag` から取る)。

```python
from projectapp.gantt_drag import CHART_DRAG_CSS, CHART_DRAG_JS, NAME_RESIZE_CSS, RESIZE_EDGE_PX
```
`RESIZE_EDGE_PX = 6  # ...(Task 4 で gantt_drag へ移す)` の 1 行を削除する(`NAME_WIDTH_PROPS` は、そのまま `RESIZE_EDGE_PX` を使う)。

`build` の `ui.add_css(CHART_DRAG_CSS)` の次に足す。

```python
        ui.add_css(NAME_RESIZE_CSS)
```

`GanttChart` に、メソッドを足す(`edit_on_click` の前)。

```python
    def resize_classes(self) -> str:
        """名前の欄の右端を、幅の調整の掴み場所にするクラス(先頭に空白)。読み取り専用では付けない。"""
        return "" if self.options.read_only else " gantt-name-resizable"
```

4 か所のクラスに足す。

- `top_add_row`: `cell = ui.row().classes("items-center justify-end no-wrap gantt-sticky")` → `cell = ui.row().classes("items-center justify-end no-wrap gantt-sticky" + self.resize_classes())`
- `header_spacer`: `spacer = ui.element("div").classes("gantt-sticky")` → `spacer = ui.element("div").classes("gantt-sticky" + self.resize_classes())`
- `section_rows`: `name = ui.row().classes("items-center no-wrap gap-2 gantt-sticky")` → `name = ui.row().classes("items-center no-wrap gap-2 gantt-sticky" + self.resize_classes())`
- `task_row`: `cell = ui.row().classes("items-center no-wrap gap-1 cursor-pointer gantt-sticky" f" {PRIORITY_CLASSES[task.priority]}")` → 末尾に `+ self.resize_classes()` を足す。

```python
            cell = ui.row().classes(
                "items-center no-wrap gap-1 cursor-pointer gantt-sticky"
                f" {PRIORITY_CLASSES[task.priority]}" + self.resize_classes()
            )
```

- [ ] **Step 6: テストが通ることを確かめる**

Run: `uv run pytest test/test_gantt_drag.py test/test_gantt.py -q 2>&1 | tail -10`
Expected: PASS(Node がない環境では、JS の動作のテストは skip)

Run: `uv run pytest -n auto -q 2>&1 | tail -5`
Expected: PASS(全件)

Run: `uvx ty check src`
Expected: `All checks passed!`

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/gantt_drag.py src/projectapp/gantt.py test/test_gantt_drag.py test/test_gantt.py
git commit -m "$(cat <<'EOF'
名前の欄の右端をドラッグして、幅を調整できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 仕様・開発メモの更新と、全体の確認

**Files:**
- Modify: `CLAUDE.md`(プロジェクト直下)、`docs/development.md`、`docs/superpowers/specs/2026-10-06-name-width-design.md`、`.claude/MEMORY.md`

- [ ] **Step 1: `CLAUDE.md`(`projectapp/CLAUDE.md`)の仕様を足す**

「## テーマ・ヘルプ」の節の末尾に足す。

```markdown
- ガントチャートの名前の欄(左の列)の幅は、名前の欄の右端(チャートとの境目)をドラッグして、120〜480px の範囲で変えられる(既定は 200px)。右端のダブルクリックで既定へ戻る。選んだ幅は`~/.projectapp/config.json`に保存し、次回起動時に復元する(全プロジェクト共通)。プレビューでは変えられず、保存した幅で表示する
```

「## データの保存先」の `テーマは~/.projectapp/config.json、…` の行を直す。

```markdown
- テーマと名前の欄の幅は`~/.projectapp/config.json`、祝日データのキャッシュは`~/.projectapp/holidays.json`に保存する
```

- [ ] **Step 2: `docs/development.md` を直す**

モジュール表の次の行を直す。

- `gantt.py`: 説明の末尾に「、名前の欄の幅(CSS 変数 `--name-w`。位置は `from_name` で式にする)」を足す。
- `gantt_drag.py`: 「(定数のみ。行は HTML5 の drag、バーは pointer イベント)」を「(定数のみ。行は HTML5 の drag、バーと名前の欄の右端は pointer イベント)」にする。
- `config.py`: 「テーマ設定(`config.json`)」を「テーマと名前の欄の幅の設定(`config.json`。読んで更新して書く)」にする。

設計書の表に行を足す。

```markdown
| 名前の欄の幅 | `2026-10-06-name-width-design.md` |
```

「## 描画速度の設計制約」の節に、一文を足す。

```markdown
- 名前の欄の幅の変更(要望 23)は、CSS 変数 `--name-w` で行い、再描画しない。掴み場所は疑似要素で、要素数は増えない。
```

- [ ] **Step 3: 設計書の見積りを直す**

`docs/superpowers/specs/2026-10-06-name-width-design.md` の次の箇所を直す。

「既存テストのうち、`NAME_WIDTH_PX` に依存する約 8 か所(`test_gantt.py` 5 か所、`test_preview.py` 2 か所ほか)」→「既存テストのうち、名前の幅や位置の文字列(`200`・`220.0px` など)に依存する約 25 か所(`test_gantt.py` 約 23 か所、`test_preview.py` 2 か所)」

- [ ] **Step 4: `.claude/MEMORY.md` を直す**

- 「今後の要望」の見出しの「未着手は 4・5・6・7・8・10・11・20〜24」から、23 を除く。
- 要望 23 の行の先頭に「(完了)」を付け、末尾に「対応: CSS 変数 `--name-w`、右端 6px の疑似要素の掴み場所、`config.json` の `name_width`(120〜480、既定 200)。設計書 `2026-10-06-name-width-design.md`、実装計画 `2026-10-06-name-width.md`。」を足す。
- 「## ブランチ」の表に、`feature/name-width`(要望 23 の実装中。マージ前)を足す。
- 「## 参照先」の設計書・実装計画の一覧に、`2026-10-06-name-width-design.md` と `2026-10-06-name-width.md` を足す。
- 「次にやること(候補)」の 0 に、要望 23 の実機確認(下の Step 6 の項目)を足す。

- [ ] **Step 5: 全体を確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -5`
Expected: PASS(全件。件数は、実装前の 1,075 件より増える)

Run: `uv run pytest --cov=projectapp -n auto -q 2>&1 | tail -20`
Expected: PASS。`config.py`・`gantt.py`・`gantt_drag.py` の網羅率が下がっていない。

Run: `uvx ty check src`
Expected: `All checks passed!`

Run: `grep -rn "NAME_WIDTH_PX" src test | grep -v "DEFAULT_NAME_WIDTH_PX\|MIN_NAME_WIDTH_PX\|MAX_NAME_WIDTH_PX"`
Expected: 出力なし。

- [ ] **Step 6: コミットし、実機の確認項目をユーザーへ渡す**

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "$(cat <<'EOF'
名前の欄の幅: 仕様と開発メモを更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

自動テストで扱えないので、`uv run projectapp`(ネイティブウィンドウ)での確認を、ユーザーへ依頼する。確認項目(設計書の「実機で確認する項目」と同じ):

- 名前の欄の右端でカーソルが `col-resize` になり、ドラッグで幅が追従する(棒・格子線・帯・ヘッダー・◆・印が一緒に動く)。ヘッダーの欄(年・月・日)でも掴める。
- 120px・480px で止まる。右端のダブルクリックで 200px に戻る。
- ドラッグしたあと、編集ダイアログが開かない。行の移動(drag)が始まらない。通常のクリックと行のドラッグは、これまでどおり動く。
- 横にスクロールしても、右端の掴み場所が名前の欄に付いてくる。
- 離したあとと、アプリの再起動後に、幅が保たれる。テーマの設定も保たれる。
- 120px で、長い名前が省略表示され、チップが隠れない。
- プレビューで掴めない。幅が反映される。画像で保存したとき、見た目と同じ幅になる(`calc(var())` が画像化でも解決される。ダークテーマを含む)。

問題が出たら、`feature/name-width` に修正を足す。実機の確認が済んだら、`develop` へのマージ(ユーザーの許可を得てから)に進む。
