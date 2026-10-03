# ガントチャート基本表示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **コミットについて:** ユーザー指示により、許可が出るまでコミットしない。各タスク末尾の Commit ステップは、許可が出てから実施する(許可前は `git status` で変更を確認するだけにする)。

**Goal:** メイン画面のチャート領域に、セクションとタスクのバーを日・週・月のスケールで表示し、土日祝の背景色とタスク・セクションの追加・編集を提供する。

**Architecture:** 日時から列・位置への変換は NiceGUI に依存しない純粋関数(`timeline.py`)にし、描画(`gantt.py`)とダイアログ(`forms.py`)は NiceGUI 要素で作る。祝日は内閣府 CSV を `httpx` で取得して `holidays.json` にキャッシュする(`calendar.py`)。`MainView` が各部品を束ね、チャート領域だけを `refreshable` で再描画する。

**Tech Stack:** Python 3.13、NiceGUI 3.17、httpx、pytest / pytest-asyncio / pytest-cov、ty、uv

**Spec:** `docs/superpowers/specs/2026-10-02-gantt-basic-design.md`

## Global Constraints

- Python 3.13 以上。パッケージャーは uv。ライブラリは NiceGUI(UI 言語は日本語)。
- すべての関数に型引数と戻り値の型ヒントを付ける。型チェックは `uvx ty check src`。
- コメントの説明は多くても3行以内。コードは PEP8 と The Zen of Python に従う。
- テストは pytest、カバレッジは pytest-cov。テストは `test/` に置く。
- 祝日データは内閣府の CSV を `httpx` で取得し、`~/.projectapp/holidays.json` に保存する。`holidays.json` がない初回のみ起動時に自動取得し、以降は更新ボタンのときだけ再取得する。
- スケールの1列と最小表示幅: 日次=1日・42日、週次=1週間(月曜始まり)・26週、月次=1か月・12か月。
- 土日祝の背景は日次スケールのみ。土曜=薄い青、日曜=薄いピンク、祝日=薄い緑(土日と重なる場合は祝日を優先)。半透明色でライト・ダークの両テーマに対応する。
- バーは開始・終了が両方設定されたタスクのみ描画する。未設定のタスクは名前の行だけ表示する。
- 入力検証: 名前は必須。終了が開始より前なら保存せずエラーを表示する。
- 範囲外(作らない): 工数からの終了日時の自動算出、予定超過の赤表示、ドラッグ&ドロップ、検索・絞り込み、矢印連結、添付ファイル、リソース割り当て比率、プロジェクトの保存。

## Review Focus

仕様が黙っているが、利用者が踏みやすい入力・状態。各行は、担当タスクのテストで固定する。

1. 終了が開始より前のタスクが読み込まれた(不正データ): バーの幅を 0 にして、クラッシュしない(Task 2)。
2. `holidays.json` が壊れている・形式が違う: 初回扱いにして再取得する(Task 1)。
3. 祝日 CSV の取得は成功したが中身が CSV でない(HTML のエラーページなど): 保存せず、失敗として扱う(Task 1)。
4. 名前が空白だけ、タイムゾーン付きの日時、負の工数: 保存せずエラーを表示する(Task 4)。
5. セクション名・タスク名に `<b>` など HTML を含む: 文字列としてそのまま表示する(Task 3)。

---

## File Structure

| ファイル | 操作 | 責務 |
|---|---|---|
| `src/projectapp/calendar.py` | 新規 | 祝日の解析・取得・キャッシュ、日付種別の判定 |
| `src/projectapp/timeline.py` | 新規 | スケール、列の生成、日時から位置・幅への変換(純粋関数) |
| `src/projectapp/gantt.py` | 新規 | チャートの描画、スケール切替トグル、操作のコールバック |
| `src/projectapp/forms.py` | 新規 | 入力検証(純粋関数)とタスク・セクションのダイアログ |
| `src/projectapp/views.py` | 変更 | チャート組み込み、祝日の初回取得・更新、追加・編集の接続 |
| `test/test_calendar.py` | 新規 | 祝日のテスト |
| `test/test_timeline.py` | 新規 | 列・位置のテスト |
| `test/test_gantt.py` | 新規 | 描画のテスト |
| `test/test_forms.py` | 新規 | 入力検証とダイアログのテスト |
| `test/test_views.py` | 変更 | 画面全体のテスト(ネットワークを使わない) |
| `docs/development.md` | 変更 | モジュール構成の追記 |

---

### Task 1: 祝日データ(calendar.py)

**Files:**
- Create: `src/projectapp/calendar.py`
- Test: `test/test_calendar.py`

**Interfaces:**
- Consumes: `projectapp.storage.BASE_DIR`
- Produces:
  - `class DayKind(StrEnum)`: `WEEKDAY`, `SATURDAY`, `SUNDAY`, `HOLIDAY`
  - `parse_holidays_csv(raw: bytes) -> dict[date, str]`(読み取れた行がなければ `ValueError`)
  - `day_kind(day: date, holidays: dict[date, str]) -> DayKind`
  - `load_cache(base_dir: Path = BASE_DIR) -> dict[date, str] | None`(なし・壊れている場合は `None`)
  - `save_cache(holidays: dict[date, str], base_dir: Path = BASE_DIR) -> None`
  - `async refresh_holidays(base_dir: Path = BASE_DIR, transport: httpx.AsyncBaseTransport | None = None) -> dict[date, str]`(失敗は `httpx.HTTPError` または `ValueError`)

- [ ] **Step 1: Write the failing test**

`test/test_calendar.py`:

```python
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from projectapp.calendar import (
    DayKind,
    day_kind,
    load_cache,
    parse_holidays_csv,
    refresh_holidays,
    save_cache,
)

HEADER = "国民の祝日・休日月日,国民の祝日・休日名称\n"
CSV = (HEADER + "2026/1/1,元日\n2026/1/12,成人の日\n").encode("cp932")


def transport_returning(status: int, content: bytes) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, content=content))


def test_parse_holidays_csv() -> None:
    assert parse_holidays_csv(CSV) == {
        date(2026, 1, 1): "元日",
        date(2026, 1, 12): "成人の日",
    }


def test_parse_skips_broken_rows() -> None:
    raw = (HEADER + "abc,x\n2026/2/30,存在しない日\n2026/2/11,建国記念の日\n").encode("cp932")
    assert parse_holidays_csv(raw) == {date(2026, 2, 11): "建国記念の日"}


def test_parse_rejects_non_csv() -> None:
    with pytest.raises(ValueError):
        parse_holidays_csv(b"<html>error</html>")


def test_day_kind() -> None:
    holidays = {date(2026, 10, 4): "テスト祝日"}  # 日曜
    assert day_kind(date(2026, 10, 3), holidays) is DayKind.SATURDAY
    assert day_kind(date(2026, 10, 4), holidays) is DayKind.HOLIDAY
    assert day_kind(date(2026, 10, 11), holidays) is DayKind.SUNDAY
    assert day_kind(date(2026, 10, 5), holidays) is DayKind.WEEKDAY


def test_cache_roundtrip(tmp_path: Path) -> None:
    assert load_cache(tmp_path) is None
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    assert load_cache(tmp_path) == {date(2026, 1, 1): "元日"}


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"2026-13-45": "x"}'])
def test_broken_cache_is_treated_as_missing(tmp_path: Path, content: str) -> None:
    (tmp_path / "holidays.json").write_text(content, encoding="utf-8")
    assert load_cache(tmp_path) is None


async def test_refresh_fetches_and_saves(tmp_path: Path) -> None:
    result = await refresh_holidays(tmp_path, transport_returning(200, CSV))
    assert result[date(2026, 1, 1)] == "元日"
    saved = json.loads((tmp_path / "holidays.json").read_text(encoding="utf-8"))
    assert saved["2026-01-12"] == "成人の日"


async def test_refresh_http_error_keeps_cache(tmp_path: Path) -> None:
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    with pytest.raises(httpx.HTTPError):
        await refresh_holidays(tmp_path, transport_returning(500, b""))
    assert load_cache(tmp_path) == {date(2026, 1, 1): "元日"}


async def test_refresh_non_csv_is_not_saved(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await refresh_holidays(tmp_path, transport_returning(200, b"<html>oops</html>"))
    assert not (tmp_path / "holidays.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_calendar.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.calendar'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/calendar.py`:

```python
"""祝日データの取得・キャッシュと日付種別の判定。"""

import csv
import io
import json
from datetime import date
from enum import StrEnum
from pathlib import Path

import httpx

from projectapp.storage import BASE_DIR

HOLIDAYS_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
CACHE_NAME = "holidays.json"
TIMEOUT_SECONDS = 10.0


class DayKind(StrEnum):
    WEEKDAY = "平日"
    SATURDAY = "土曜"
    SUNDAY = "日曜"
    HOLIDAY = "祝日"


def parse_holidays_csv(raw: bytes) -> dict[date, str]:
    """内閣府CSV(cp932)を解析する。読み取れた行がなければValueError。"""
    rows = csv.reader(io.StringIO(raw.decode("cp932")))
    next(rows, None)  # ヘッダー行
    holidays: dict[date, str] = {}
    for row in rows:
        try:
            year, month, day = (int(v) for v in row[0].split("/"))
            holidays[date(year, month, day)] = row[1].strip()
        except (ValueError, IndexError):
            continue
    if not holidays:
        raise ValueError("祝日データを解析できません")
    return holidays


def day_kind(day: date, holidays: dict[date, str]) -> DayKind:
    if day in holidays:
        return DayKind.HOLIDAY
    if day.weekday() == 5:
        return DayKind.SATURDAY
    if day.weekday() == 6:
        return DayKind.SUNDAY
    return DayKind.WEEKDAY


def load_cache(base_dir: Path = BASE_DIR) -> dict[date, str] | None:
    """キャッシュを読む。ファイルがない・壊れている場合はNone。"""
    try:
        raw = json.loads((base_dir / CACHE_NAME).read_text(encoding="utf-8"))
        return {date.fromisoformat(key): str(name) for key, name in raw.items()}
    except (OSError, ValueError, AttributeError):
        return None


def save_cache(holidays: dict[date, str], base_dir: Path = BASE_DIR) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    data = {day.isoformat(): name for day, name in holidays.items()}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    (base_dir / CACHE_NAME).write_text(text, encoding="utf-8")


async def refresh_holidays(
    base_dir: Path = BASE_DIR,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[date, str]:
    """祝日を取得してキャッシュに保存する。失敗時は何も保存せず例外を送出する。"""
    async with httpx.AsyncClient(
        transport=transport, timeout=TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        response = await client.get(HOLIDAYS_URL)
    response.raise_for_status()
    holidays = parse_holidays_csv(response.content)
    save_cache(holidays, base_dir)
    return holidays
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_calendar.py -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/calendar.py test/test_calendar.py
git commit -m "feat: 祝日データの取得・キャッシュと日付種別判定を追加"
```

---

### Task 2: 列と位置の計算(timeline.py)

**Files:**
- Create: `src/projectapp/timeline.py`
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: `projectapp.models.Project`, `Task`, `Section`
- Produces:
  - `class Scale(StrEnum)`: `DAY="日次"`, `WEEK="週次"`, `MONTH="月次"`
  - `MIN_COLUMNS: dict[Scale, int]`
  - `@dataclass(frozen=True) class Column`: `start: date`, `end: date`(終端を含まない)、`label: str`
  - `visible_range(project: Project) -> tuple[date, date]`(`[開始日, 終了日)`)
  - `build_columns(project: Project, scale: Scale) -> list[Column]`
  - `bar_span(task: Task, columns: list[Column]) -> tuple[float, float] | None`(列の単位での `(left, width)`。開始・終了が未設定なら `None`)

- [ ] **Step 1: Write the failing test**

`test/test_timeline.py`:

```python
from datetime import date, datetime

import pytest

from projectapp.models import Project, Section, Task
from projectapp.timeline import Scale, bar_span, build_columns

BASE = date(2026, 10, 5)  # 月曜


def project_with(*tasks: Task, base: date = BASE) -> Project:
    return Project("p", base_date=base, sections=[Section("s", list(tasks))])


def test_empty_project_uses_min_columns() -> None:
    project = Project("p", base_date=BASE)
    assert len(build_columns(project, Scale.DAY)) == 42
    assert len(build_columns(project, Scale.WEEK)) == 26
    assert len(build_columns(project, Scale.MONTH)) == 12


def test_day_columns_start_at_base_and_are_contiguous() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert columns[0].start == BASE
    assert columns[0].label == "10/5"
    assert all(a.end == b.start for a, b in zip(columns, columns[1:]))


def test_range_extends_to_the_day_after_last_end() -> None:
    task = Task("t", start=datetime(2026, 10, 5, 9), end=datetime(2026, 12, 31, 18))
    columns = build_columns(project_with(task), Scale.DAY)
    assert len(columns) == 88
    assert columns[-1].end == date(2027, 1, 1)


def test_range_extends_before_base_date() -> None:
    task = Task("t", start=datetime(2026, 9, 20, 9), end=datetime(2026, 9, 22, 9))
    assert build_columns(project_with(task), Scale.DAY)[0].start == date(2026, 9, 20)


def test_week_columns_start_on_monday() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 7)), Scale.WEEK)
    assert columns[0].start == date(2026, 10, 5)
    assert columns[0].end == date(2026, 10, 12)
    assert columns[0].label == "10/5~"


def test_month_columns_cross_the_year() -> None:
    task = Task("t", start=datetime(2026, 11, 15), end=datetime(2027, 2, 10))
    columns = build_columns(project_with(task, base=date(2026, 11, 15)), Scale.MONTH)
    assert [c.label for c in columns[:4]] == ["2026/11", "2026/12", "2027/1", "2027/2"]
    assert (columns[2].start, columns[2].end) == (date(2027, 1, 1), date(2027, 2, 1))
    assert all(a.end == b.start for a, b in zip(columns, columns[1:]))


def test_bar_span_in_day_scale() -> None:
    task = Task("t", start=datetime(2026, 10, 5, 12), end=datetime(2026, 10, 7, 12))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task, columns) == (0.5, 2.0)


def test_bar_span_in_week_scale() -> None:
    task = Task("t", start=datetime(2026, 10, 5), end=datetime(2026, 10, 12))
    columns = build_columns(project_with(task), Scale.WEEK)
    assert bar_span(task, columns) == (0.0, 1.0)


def test_bar_span_in_month_scale_is_proportional() -> None:
    task = Task("t", start=datetime(2026, 1, 16), end=datetime(2026, 2, 1))
    columns = build_columns(project_with(task, base=date(2026, 1, 1)), Scale.MONTH)
    left, width = bar_span(task, columns) or (-1.0, -1.0)
    assert left == pytest.approx(15 / 31)
    assert width == pytest.approx(16 / 31)


def test_bar_span_is_none_without_start_or_end() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert bar_span(Task("a"), columns) is None
    assert bar_span(Task("b", start=datetime(2026, 10, 5)), columns) is None
    assert bar_span(Task("c", end=datetime(2026, 10, 5)), columns) is None


def test_end_before_start_gives_zero_width_without_error() -> None:
    task = Task("bad", start=datetime(2026, 10, 8), end=datetime(2026, 10, 6))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task, columns) == (3.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_timeline.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.timeline'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/timeline.py`:

```python
"""スケールごとの列生成と、日時から位置・幅への変換(純粋関数)。"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from math import ceil

from projectapp.models import Project, Task


class Scale(StrEnum):
    DAY = "日次"
    WEEK = "週次"
    MONTH = "月次"


MIN_COLUMNS = {Scale.DAY: 42, Scale.WEEK: 26, Scale.MONTH: 12}


@dataclass(frozen=True)
class Column:
    start: date
    end: date  # 終端を含まない
    label: str


def visible_range(project: Project) -> tuple[date, date]:
    """基準日とバーを持つタスクから、表示範囲[開始日, 終了日)を返す。"""
    start = end = project.base_date
    for section in project.sections:
        for task in section.tasks:
            if task.start is None or task.end is None:
                continue
            first, last = sorted((task.start.date(), task.end.date()))
            start = min(start, first)
            end = max(end, last + timedelta(days=1))
    return start, end


def build_columns(project: Project, scale: Scale) -> list[Column]:
    start, end = visible_range(project)
    if scale is Scale.WEEK:
        return _week_columns(start, end)
    if scale is Scale.MONTH:
        return _month_columns(start, end)
    return _day_columns(start, end)


def _day_columns(start: date, end: date) -> list[Column]:
    count = max((end - start).days, MIN_COLUMNS[Scale.DAY])
    days = (start + timedelta(days=i) for i in range(count))
    return [Column(d, d + timedelta(days=1), f"{d.month}/{d.day}") for d in days]


def _week_columns(start: date, end: date) -> list[Column]:
    monday = start - timedelta(days=start.weekday())
    count = max(ceil((end - monday).days / 7), MIN_COLUMNS[Scale.WEEK])
    weeks = (monday + timedelta(weeks=i) for i in range(count))
    return [Column(d, d + timedelta(days=7), f"{d.month}/{d.day}~") for d in weeks]


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _month_columns(start: date, end: date) -> list[Column]:
    first = start.replace(day=1)
    last = max(end - timedelta(days=1), first)
    count = (last.year - first.year) * 12 + last.month - first.month + 1
    columns: list[Column] = []
    for i in range(max(count, MIN_COLUMNS[Scale.MONTH])):
        month = _add_months(first, i)
        columns.append(Column(month, _add_months(first, i + 1), f"{month.year}/{month.month}"))
    return columns


def _position(moment: datetime, columns: list[Column]) -> float:
    """日時を、列の単位(0〜列数)の連続値に変換する。"""
    if moment <= datetime.combine(columns[0].start, time.min):
        return 0.0
    for index, column in enumerate(columns):
        begin = datetime.combine(column.start, time.min)
        finish = datetime.combine(column.end, time.min)
        if begin <= moment < finish:
            return index + (moment - begin) / (finish - begin)
    return float(len(columns))


def bar_span(task: Task, columns: list[Column]) -> tuple[float, float] | None:
    """バーの(左端, 幅)を列の単位で返す。開始・終了が未設定ならNone。"""
    if task.start is None or task.end is None:
        return None
    left = _position(task.start, columns)
    right = _position(task.end, columns)
    return left, max(right - left, 0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_timeline.py -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/timeline.py test/test_timeline.py
git commit -m "feat: スケール別の列生成とバー位置の計算を追加"
```

---

### Task 3: チャートの描画(gantt.py)

**Files:**
- Create: `src/projectapp/gantt.py`
- Test: `test/test_gantt.py`

**Interfaces:**
- Consumes:
  - `projectapp.calendar.DayKind`, `day_kind(day, holidays) -> DayKind`
  - `projectapp.timeline.Scale`, `Column`, `build_columns(project, scale) -> list[Column]`, `bar_span(task, columns) -> tuple[float, float] | None`
  - `projectapp.models.Project`, `Section`, `Task`
- Produces:
  - 定数 `NAME_WIDTH_PX = 200`、`ROW_HEIGHT_PX = 32`、`COLUMN_WIDTH_PX = {DAY: 40, WEEK: 56, MONTH: 80}`、`KIND_COLORS: dict[DayKind, str]`(SATURDAY / SUNDAY / HOLIDAY)
  - `@dataclass class GanttActions`: `add_section: Callable[[], object]`、`add_task: Callable[[int], object]`(引数はセクション番号)、`edit_task: Callable[[int, int], object]`(セクション番号, タスク番号)、`refresh_holidays: Callable[[], object]`
  - `class GanttChart(project: Project, holidays: dict[date, str], actions: GanttActions)` のメソッド: `build() -> None`、`set_project(project) -> None`、`set_holidays(holidays) -> None`、`set_scale(scale) -> None`
  - テスト用マーカー: `scale-toggle`、`add-section`、`refresh-holidays`、`stripes`、`add-task-{si}`、`task-{si}-{ti}`(名前の行)、`bar-{si}-{ti}`(バー)

- [ ] **Step 1: Write the failing test**

`test/test_gantt.py`:

```python
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import DayKind
from projectapp.gantt import KIND_COLORS, GanttActions, GanttChart
from projectapp.models import Project, Section, Task
from projectapp.timeline import Scale

BASE = date(2026, 10, 5)  # 月曜


class Recorder:
    """操作のコールバックを記録する。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[int, ...]]] = []
        self.actions = GanttActions(
            add_section=lambda: self.events.append(("add_section", ())),
            add_task=lambda si: self.events.append(("add_task", (si,))),
            edit_task=lambda si, ti: self.events.append(("edit_task", (si, ti))),
            refresh_holidays=lambda: self.events.append(("refresh_holidays", ())),
        )


def sample_project() -> Project:
    task = Task(
        "設計",
        start=datetime(2026, 10, 5, 12),
        end=datetime(2026, 10, 7, 12),
        color="#ff0000",
    )
    return Project("demo", base_date=BASE, sections=[Section("開発", [task, Task("未設定")])])


def mount(project: Project, holidays: dict[date, str] | None = None) -> Recorder:
    recorder = Recorder()

    @ui.page("/")
    def index() -> None:
        GanttChart(project, holidays or {}, recorder.actions).build()

    return recorder


async def test_renders_sections_tasks_and_bars(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    await user.should_see("開発")
    await user.should_see("設計")
    await user.should_see("未設定")
    await user.should_see(marker="bar-0-0")
    await user.should_not_see(marker="bar-0-1")


async def test_bar_geometry_and_color(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["left"] == "220.0px"  # 200 + 0.5 * 40
    assert bar._style["width"] == "80.0px"  # 2.0 * 40
    assert bar._style["background"] == "#ff0000"


async def test_day_scale_colors_weekends_and_holidays(user: User) -> None:
    mount(sample_project(), {date(2026, 10, 7): "テスト祝日"})
    await user.open("/")
    html = user.find(marker="stripes").elements.pop().content
    assert html.count(KIND_COLORS[DayKind.HOLIDAY]) == 1
    assert html.count(KIND_COLORS[DayKind.SATURDAY]) == 6
    assert html.count(KIND_COLORS[DayKind.SUNDAY]) == 6


async def test_holiday_wins_over_sunday(user: User) -> None:
    mount(sample_project(), {date(2026, 10, 11): "日曜の祝日"})
    await user.open("/")
    html = user.find(marker="stripes").elements.pop().content
    assert html.count(KIND_COLORS[DayKind.HOLIDAY]) == 1
    assert html.count(KIND_COLORS[DayKind.SUNDAY]) == 5


async def test_week_scale_has_no_stripes_and_scales_bars(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.WEEK)
    await user.should_not_see(marker="stripes")
    await user.should_see("10/5~")
    bar = user.find(marker="bar-0-0").elements.pop()
    assert bar._style["left"] == "204.0px"  # 200 + 0.5 / 7 * 56
    assert bar._style["width"] == "16.0px"  # 2 / 7 * 56


async def test_month_scale_labels(user: User) -> None:
    mount(sample_project())
    await user.open("/")
    user.find(kind=ui.toggle).elements.pop().set_value(Scale.MONTH)
    await user.should_see("2026/10")


async def test_clicks_call_the_actions(user: User) -> None:
    recorder = mount(sample_project())
    await user.open("/")
    user.find(marker="bar-0-0").click()
    user.find(marker="task-0-1").click()
    user.find(marker="add-task-0").click()
    user.find(marker="add-section").click()
    user.find(marker="refresh-holidays").click()
    assert recorder.events == [
        ("edit_task", (0, 0)),
        ("edit_task", (0, 1)),
        ("add_task", (0,)),
        ("add_section", ()),
        ("refresh_holidays", ()),
    ]


async def test_empty_section_and_html_like_names_are_shown_literally(user: User) -> None:
    project = Project("p", base_date=BASE, sections=[Section("<b>空</b>")])
    mount(project)
    await user.open("/")
    await user.should_see("<b>空</b>")
    await user.should_see(marker="add-task-0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_gantt.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.gantt'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/gantt.py`:

```python
"""ガントチャートの描画(NiceGUI要素とCSS)。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from nicegui import ui

from projectapp.calendar import DayKind, day_kind
from projectapp.models import Project, Section, Task
from projectapp.timeline import Column, Scale, bar_span, build_columns

NAME_WIDTH_PX = 200
ROW_HEIGHT_PX = 32
COLUMN_WIDTH_PX = {Scale.DAY: 40, Scale.WEEK: 56, Scale.MONTH: 80}
KIND_COLORS = {
    DayKind.SATURDAY: "rgba(66, 165, 245, 0.18)",
    DayKind.SUNDAY: "rgba(244, 143, 177, 0.22)",
    DayKind.HOLIDAY: "rgba(129, 199, 132, 0.28)",
}
ROW_STYLE = f"height: {ROW_HEIGHT_PX}px; position: relative"


@dataclass
class GanttActions:
    """チャートからの操作要求を受け取るコールバック。"""

    add_section: Callable[[], object]
    add_task: Callable[[int], object]
    edit_task: Callable[[int, int], object]
    refresh_holidays: Callable[[], object]


class GanttChart:
    def __init__(
        self, project: Project, holidays: dict[date, str], actions: GanttActions
    ) -> None:
        self.project = project
        self.holidays = holidays
        self.actions = actions
        self.scale = Scale.DAY

    def set_project(self, project: Project) -> None:
        self.project = project
        self.render.refresh()

    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.holidays = holidays
        self.render.refresh()

    def set_scale(self, scale: Scale) -> None:
        self.scale = scale
        self.render.refresh()

    def build(self) -> None:
        with ui.row().classes("w-full items-center gap-4"):
            ui.toggle(
                {scale: scale.value for scale in Scale},
                value=self.scale,
                on_change=lambda e: self.set_scale(Scale(e.value)),
            ).mark("scale-toggle")
            ui.button("セクション追加", icon="add", on_click=self.actions.add_section).props(
                "flat"
            ).mark("add-section")
            ui.button(
                "祝日を更新", icon="refresh", on_click=self.actions.refresh_holidays
            ).props("flat").mark("refresh-holidays")
        self.render()

    @ui.refreshable_method
    def render(self) -> None:
        columns = build_columns(self.project, self.scale)
        width = COLUMN_WIDTH_PX[self.scale]
        total = NAME_WIDTH_PX + width * len(columns)
        with ui.element("div").classes("w-full").style("overflow-x: auto"):
            with ui.element("div").style(f"position: relative; width: {total}px"):
                if self.scale is Scale.DAY:
                    self.stripes(columns, width)
                self.header(columns, width)
                for si, section in enumerate(self.project.sections):
                    self.section_rows(si, section, columns, width)

    def stripes(self, columns: list[Column], width: int) -> None:
        """日次スケールの土日祝の背景。内容は定数と日付のみで利用者の入力を含まない。"""
        cells = "".join(
            f'<div style="width:{width}px;background:'
            f'{KIND_COLORS.get(day_kind(column.start, self.holidays), "transparent")}">'
            "</div>"
            for column in columns
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; top: 0; bottom: 0; left: {NAME_WIDTH_PX}px;"
            " pointer-events: none"
        ).mark("stripes")

    def header(self, columns: list[Column], width: int) -> None:
        with ui.row().classes("items-center no-wrap gap-0").style(ROW_STYLE):
            ui.element("div").style(f"width: {NAME_WIDTH_PX}px")
            for column in columns:
                ui.label(column.label).classes("text-caption text-center").style(
                    f"width: {width}px"
                )

    def section_rows(
        self, si: int, section: Section, columns: list[Column], width: int
    ) -> None:
        with ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE):
            ui.label(section.name).classes("text-subtitle2")
            ui.button(
                icon="add", on_click=lambda si=si: self.actions.add_task(si)
            ).props("flat dense round size=sm").tooltip("タスク追加").mark(f"add-task-{si}")
        for ti, task in enumerate(section.tasks):
            self.task_row(si, ti, task, columns, width)

    def task_row(
        self, si: int, ti: int, task: Task, columns: list[Column], width: int
    ) -> None:
        with ui.row().classes("items-center no-wrap gap-0").style(ROW_STYLE):
            ui.label(task.name).classes("ellipsis cursor-pointer").style(
                f"width: {NAME_WIDTH_PX}px; padding-left: 16px"
            ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                f"task-{si}-{ti}"
            )
            span = bar_span(task, columns)
            if span is None:
                return
            left, length = span
            ui.element("div").style(
                f"position: absolute; left: {NAME_WIDTH_PX + left * width:.1f}px;"
                f" width: {length * width:.1f}px; top: 6px;"
                f" height: {ROW_HEIGHT_PX - 12}px; background: {task.color};"
                " border-radius: 4px; cursor: pointer"
            ).on("click", lambda si=si, ti=ti: self.actions.edit_task(si, ti)).mark(
                f"bar-{si}-{ti}"
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_gantt.py -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`
(`_style` の値の書式が異なって失敗した場合は、`print(bar._style)` で実際の値を見て、テストの期待値の書式を合わせる。計算結果自体は変えない。)

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/gantt.py test/test_gantt.py
git commit -m "feat: ガントチャートの描画とスケール切替を追加"
```

---

### Task 4: 追加・編集ダイアログ(forms.py)

**Files:**
- Create: `src/projectapp/forms.py`
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: `projectapp.models.Task`, `Priority`, `Status`
- Produces:
  - `parse_datetime(text: str) -> datetime | None`(空は `None`、不正・タイムゾーン付きは `ValueError`)
  - `build_task(existing: Task | None, *, name: str, start: str, end: str, effort_hours: float | None, priority: Priority, status: Status, color: str, assignee: str) -> Task`(検証エラーは `ValueError(日本語メッセージ)`)
  - `build_section_name(text: str) -> str`(空白のみは `ValueError`)
  - `open_task_dialog(task: Task | None, on_save: Callable[[Task], object]) -> None`
  - `open_section_dialog(on_save: Callable[[str], object]) -> None`
  - テスト用マーカー: `task-name`、`task-start`、`task-end`、`task-save`、`section-name`、`section-save`、`form-error`

- [ ] **Step 1: Write the failing test**

`test/test_forms.py`:

```python
from datetime import datetime

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.forms import (
    build_section_name,
    build_task,
    open_section_dialog,
    open_task_dialog,
    parse_datetime,
)
from projectapp.models import Priority, Status, Task


def make(existing: Task | None = None, **overrides: object) -> Task:
    values: dict[str, object] = {
        "name": "設計",
        "start": "2026-10-05T09:00",
        "end": "2026-10-07T18:00",
        "effort_hours": 8.0,
        "priority": Priority.HIGH,
        "status": Status.RUNNING,
        "color": "#112233",
        "assignee": "",
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]


def test_build_task_normalizes_input() -> None:
    task = make(name="  設計  ", assignee=" 佐藤 ")
    assert task.name == "設計"
    assert task.start == datetime(2026, 10, 5, 9, 0)
    assert task.end == datetime(2026, 10, 7, 18, 0)
    assert task.effort_hours == 8.0
    assert task.assignee == "佐藤"


def test_blank_assignee_and_dates_become_none() -> None:
    task = make(start="", end="", assignee="  ", effort_hours=None)
    assert (task.start, task.end, task.assignee, task.effort_hours) == (None, None, None, 0.0)


@pytest.mark.parametrize("name", ["", "   ", "　"])
def test_blank_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="名前"):
        make(name=name)


def test_end_before_start_is_rejected_but_equal_is_allowed() -> None:
    with pytest.raises(ValueError, match="終了"):
        make(start="2026-10-07T09:00", end="2026-10-05T09:00")
    assert make(start="2026-10-05T09:00", end="2026-10-05T09:00").name == "設計"


@pytest.mark.parametrize("text", ["abc", "2026-13-01T00:00", "2026-10-05T09:00+09:00", "2026-10-05T09:00Z"])
def test_bad_or_timezone_aware_datetime_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="形式"):
        make(start=text)


def test_negative_effort_is_rejected() -> None:
    with pytest.raises(ValueError, match="工数"):
        make(effort_hours=-1.0)


def test_editing_keeps_fields_not_in_the_form() -> None:
    existing = Task("旧", predecessors=["x"])
    edited = make(existing)
    assert edited.predecessors == ["x"]
    assert existing.name == "旧"


def test_parse_datetime_accepts_date_only() -> None:
    assert parse_datetime("2026-10-05") == datetime(2026, 10, 5)


def test_build_section_name() -> None:
    assert build_section_name(" 開発 ") == "開発"
    with pytest.raises(ValueError, match="名前"):
        build_section_name("  ")


async def test_task_dialog_saves_a_valid_task(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start").type("2026-10-05T09:00")
    user.find(marker="task-end").type("2026-10-07T18:00")
    user.find(marker="task-save").click()
    assert [t.name for t in saved] == ["設計"]
    assert saved[0].end == datetime(2026, 10, 7, 18, 0)


async def test_task_dialog_shows_error_and_does_not_save(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-save").click()
    await user.should_see("名前を入力してください")
    assert saved == []


async def test_task_dialog_prefills_when_editing(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        task = Task("既存", start=datetime(2026, 10, 5, 9), end=datetime(2026, 10, 6, 9))
        ui.button("open", on_click=lambda: open_task_dialog(task, lambda t: None))

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="task-name").elements.pop().value == "既存"
    assert user.find(marker="task-start").elements.pop().value == "2026-10-05T09:00"


async def test_section_dialog(user: User) -> None:
    saved: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_section_dialog(saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="section-save").click()
    await user.should_see("名前を入力してください")
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    assert saved == ["開発"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_forms.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.forms'`)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/forms.py`:

```python
"""タスク・セクションの追加・編集ダイアログと入力検証。"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from nicegui import ui

from projectapp.models import Priority, Status, Task

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


def parse_datetime(text: str) -> datetime | None:
    """datetime-local形式を解析する。空はNone、不正・タイムゾーン付きはValueError。"""
    text = text.strip()
    if not text:
        return None
    value = datetime.fromisoformat(text)
    if value.tzinfo is not None:
        raise ValueError("タイムゾーン付きの日時は扱えません")
    return value


def build_task(
    existing: Task | None,
    *,
    name: str,
    start: str,
    end: str,
    effort_hours: float | None,
    priority: Priority,
    status: Status,
    color: str,
    assignee: str,
) -> Task:
    """入力値からTaskを作る。編集時はフォームにない項目を引き継ぐ。"""
    clean = name.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    try:
        start_at, end_at = parse_datetime(start), parse_datetime(end)
    except ValueError:
        raise ValueError("日時の形式が正しくありません") from None
    if start_at and end_at and end_at < start_at:
        raise ValueError("終了は開始以降の日時にしてください")
    hours = effort_hours or 0.0
    if hours < 0:
        raise ValueError("工数は0以上で入力してください")
    return replace(
        existing or Task(clean),
        name=clean,
        start=start_at,
        end=end_at,
        effort_hours=hours,
        priority=priority,
        status=status,
        color=color,
        assignee=assignee.strip() or None,
    )


def build_section_name(text: str) -> str:
    clean = text.strip()
    if not clean:
        raise ValueError("名前を入力してください")
    return clean


def _format(moment: datetime | None) -> str:
    return moment.strftime(DATETIME_FORMAT) if moment else ""


def open_task_dialog(task: Task | None, on_save: Callable[[Task], object]) -> None:
    initial = task or Task("")
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        name = ui.input("名前", value=initial.name).mark("task-name")
        start = ui.input("開始日時", value=_format(initial.start)).props(
            "type=datetime-local"
        ).mark("task-start")
        end = ui.input("終了日時", value=_format(initial.end)).props(
            "type=datetime-local"
        ).mark("task-end")
        effort = ui.number("工数(時間)", value=initial.effort_hours, min=0)
        priority = ui.select(
            {p: p.value for p in Priority}, label="優先度", value=initial.priority
        )
        status = ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
        color = ui.color_input("色", value=initial.color)
        assignee = ui.input("担当者", value=initial.assignee or "")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    start=start.value or "",
                    end=end.value or "",
                    effort_hours=effort.value,
                    priority=Priority(priority.value),
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("task-save")
    dialog.open()


def open_section_dialog(on_save: Callable[[str], object]) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-80"):
        ui.label("セクションの追加").classes("text-h6")
        name = ui.input("セクション名").mark("section-name")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_section_name(name.value or "")
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("section-save")
    dialog.open()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_forms.py -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: Commit(許可が出てから)**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "feat: タスク・セクションの追加編集ダイアログと入力検証を追加"
```

---

### Task 5: メイン画面への組み込み(views.py)

**Files:**
- Modify: `src/projectapp/views.py`(全体を下記の内容に置き換える)
- Modify: `test/test_views.py`(全体を下記の内容に置き換える)
- Modify: `docs/development.md`

**Interfaces:**
- Consumes: Task 1〜4 の `load_cache`、`refresh_holidays`、`GanttChart`、`GanttActions`、`open_task_dialog`、`open_section_dialog`
- Produces: `MainView(base_dir: Path = BASE_DIR, transport: httpx.AsyncBaseTransport | None = None)`。`base_dir` はテーマ・プロジェクトファイル・祝日キャッシュの保存先。`transport` はテストで祝日取得を差し替えるためのもの。

- [ ] **Step 1: Write the failing test**

`test/test_views.py` を次の内容に置き換える:

```python
import asyncio
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.calendar import DayKind, save_cache
from projectapp.gantt import KIND_COLORS
from projectapp.views import MainView


def holiday_csv() -> bytes:
    today = date.today()
    row = f"{today.year}/{today.month}/{today.day},テスト祝日\n"
    return ("国民の祝日・休日月日,国民の祝日・休日名称\n" + row).encode("cp932")


def make_transport(status: int, calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, content=holiday_csv())

    return httpx.MockTransport(handler)


def mount(base_dir: Path, transport: httpx.MockTransport) -> None:
    @ui.page("/")
    def index() -> None:
        MainView(base_dir, transport).build()


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return False


def stripes_have_holiday(user: User) -> bool:
    color = KIND_COLORS[DayKind.HOLIDAY]
    return any(color in e.content for e in user.find(marker="stripes").elements)


async def test_main_view(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    await user.should_see("新規プロジェクト")
    await user.should_see("開く")
    await user.should_see(marker="scale-toggle")


async def test_first_launch_fetches_holidays_once(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    mount(tmp_path, make_transport(200, calls))
    await user.open("/")
    assert await wait_until(lambda: stripes_have_holiday(user))
    assert (tmp_path / "holidays.json").exists()
    assert len(calls) == 1


async def test_cached_holidays_are_not_fetched_again(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    mount(tmp_path, make_transport(200, calls))
    await user.open("/")
    await asyncio.sleep(0.3)
    assert calls == []


async def test_first_fetch_failure_keeps_the_screen_and_retries_next_time(
    user: User, tmp_path: Path
) -> None:
    mount(tmp_path, make_transport(500, []))
    await user.open("/")
    assert await wait_until(lambda: user.notify.contains("祝日データを取得できませんでした"))
    await user.should_see("新規プロジェクト")
    assert not (tmp_path / "holidays.json").exists()


async def test_refresh_button_fetches_again(user: User, tmp_path: Path) -> None:
    calls: list[str] = []
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    mount(tmp_path, make_transport(200, calls))
    await user.open("/")
    user.find(marker="refresh-holidays").click()
    assert await wait_until(lambda: user.notify.contains("祝日データを更新しました"))
    assert len(calls) == 1
    assert await wait_until(lambda: stripes_have_holiday(user))


async def test_add_section_then_task_shows_a_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-section").click()
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    await user.should_see("開発")
    user.find(marker="add-task-0").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start").type("2026-10-05T09:00")
    user.find(marker="task-end").type("2026-10-07T18:00")
    user.find(marker="task-save").click()
    await user.should_see("設計")
    await user.should_see(marker="bar-0-0")


async def test_edit_task_updates_the_name(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-section").click()
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    user.find(marker="add-task-0").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see("設計")
    user.find(marker="task-0-0").click()
    name = user.find(marker="task-name").elements.pop()
    assert name.value == "設計"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_views.py -q`
Expected: FAIL(`TypeError: MainView() takes no arguments`、または `scale-toggle` が見つからない)

- [ ] **Step 3: Write minimal implementation**

`src/projectapp/views.py` を次の内容に置き換える:

```python
"""メイン画面。"""

from datetime import date
from pathlib import Path

import httpx
from nicegui import ui

from projectapp.calendar import load_cache
from projectapp.calendar import refresh_holidays as download_holidays
from projectapp.config import THEMES, load_theme, save_theme
from projectapp.forms import open_section_dialog, open_task_dialog
from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import Project, Section, Task
from projectapp.storage import BASE_DIR, list_project_files, load_project

THEME_LABELS = {"auto": "自動", "light": "ライト", "dark": "ダーク"}
THEME_ICONS = {"auto": "brightness_auto", "light": "light_mode", "dark": "dark_mode"}
NEW_PROJECT_NAME = "新規プロジェクト"
HELP_KEYS: list[tuple[str, str]] = []  # (キー, 機能) 機能追加時に登録する


class MainView:
    """メインパネル。現在のプロジェクトと画面部品を保持する。"""

    def __init__(
        self,
        base_dir: Path = BASE_DIR,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.transport = transport
        self.project = Project(NEW_PROJECT_NAME)
        self.files: dict[str, Path] = {p.stem: p for p in list_project_files(base_dir)}
        self.selected: str | None = None
        self.theme = load_theme(base_dir)
        self.dark = ui.dark_mode()
        self.apply_theme(self.theme)
        cached = load_cache(base_dir)
        self.holidays: dict[date, str] = cached or {}
        self.needs_first_fetch = cached is None
        self.gantt = GanttChart(
            self.project,
            self.holidays,
            GanttActions(
                add_section=self.add_section,
                add_task=self.add_task,
                edit_task=self.edit_task,
                refresh_holidays=self.refresh_holidays,
            ),
        )

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.dark.value = None if theme == "auto" else theme == "dark"

    def set_theme(self, theme: str) -> None:
        self.apply_theme(theme)
        save_theme(theme, self.base_dir)
        self.theme_buttons.refresh()

    def open_selected(self) -> None:
        if self.selected is None:
            return
        self.project = load_project(self.files[self.selected])
        self.title.refresh()
        self.gantt.set_project(self.project)

    def add_section(self) -> None:
        open_section_dialog(self.save_section)

    def save_section(self, name: str) -> None:
        self.project.sections.append(Section(name))
        self.gantt.set_project(self.project)

    def add_task(self, section_index: int) -> None:
        open_task_dialog(None, lambda task: self.save_task(section_index, None, task))

    def edit_task(self, section_index: int, task_index: int) -> None:
        task = self.project.sections[section_index].tasks[task_index]
        open_task_dialog(task, lambda t: self.save_task(section_index, task_index, t))

    def save_task(self, section_index: int, task_index: int | None, task: Task) -> None:
        tasks = self.project.sections[section_index].tasks
        if task_index is None:
            tasks.append(task)
        else:
            tasks[task_index] = task
        self.gantt.set_project(self.project)

    async def refresh_holidays(self, quiet: bool = False) -> None:
        """祝日を取得してチャートに反映する。失敗しても画面は変えず通知だけ出す。"""
        try:
            self.holidays = await download_holidays(self.base_dir, self.transport)
        except (httpx.HTTPError, ValueError):
            ui.notify("祝日データを取得できませんでした", type="warning")
            return
        self.gantt.set_holidays(self.holidays)
        if not quiet:
            ui.notify("祝日データを更新しました")

    async def first_fetch(self) -> None:
        await self.refresh_holidays(quiet=True)

    def build(self) -> None:
        self.header()
        self.gantt.build()
        self.theme_fab()
        self.help_button()
        if self.needs_first_fetch:
            ui.timer(0.1, self.first_fetch, once=True)

    def header(self) -> None:
        with ui.column().classes("w-full gap-2"):
            self.title()
            with ui.row().classes("w-full items-center justify-start gap-4"):
                ui.select(
                    list(self.files),
                    label="プロジェクトファイル",
                    on_change=lambda e: setattr(self, "selected", e.value),
                ).classes("w-64")
                ui.button("開く", icon="folder_open", on_click=self.open_selected)

    @ui.refreshable_method
    def title(self) -> None:
        ui.label(self.project.name).classes("text-h5")

    def theme_fab(self) -> None:
        with ui.page_sticky(position="top-right", x_offset=18, y_offset=18):
            with ui.fab("palette", direction="left"):
                self.theme_buttons()

    @ui.refreshable_method
    def theme_buttons(self) -> None:
        for theme in THEMES:
            color = "primary" if theme == self.theme else "grey"
            ui.fab_action(
                THEME_ICONS[theme],
                label=THEME_LABELS[theme],
                color=color,
                on_click=lambda t=theme: self.set_theme(t),
            )

    def help_button(self) -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("キー操作").classes("text-h6")
            if not HELP_KEYS:
                ui.label("登録されたキー操作はありません")
            for key, desc in HELP_KEYS:
                ui.label(f"{key}: {desc}")
            ui.button("閉じる", on_click=dialog.close)
        with ui.page_sticky(position="bottom-right", x_offset=18, y_offset=18):
            ui.button(icon="help_outline", on_click=dialog.open).props("fab")
```

`docs/development.md` のモジュール表に、次の3行を追加する(`views.py` の行の下):

```markdown
| `calendar.py` | 祝日の取得・キャッシュ(`holidays.json`)と日付種別の判定 |
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換(純粋関数) |
| `gantt.py` | ガントチャートの描画とスケール切替 |
| `forms.py` | タスク・セクションの追加・編集ダイアログと入力検証 |
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest --cov=projectapp -q && uvx ty check src`
Expected: 全テスト PASS、`All checks passed!`

- [ ] **Step 5: 手動確認(実機)**

Run: `uv run projectapp`
確認すること:
- 起動時に「新規プロジェクト」とツールバー(日次・週次・月次のトグル、セクション追加、祝日を更新)が出る。
- 初回は祝日が取得され、日次スケールの祝日・土日に背景色が付く(2回目以降の起動では取得されない)。
- セクションとタスクを追加するとバーが出て、バーまたは名前のクリックで編集できる。
- 週次・月次に切り替えると背景色が消え、バーの長さが列に合わせて変わる。
- ライト・ダークの両テーマで背景色とバーが読める。

- [ ] **Step 6: Commit(許可が出てから)**

```bash
git add src/projectapp/views.py test/test_views.py docs/development.md
git commit -m "feat: メイン画面にガントチャートを組み込み祝日の初回取得を追加"
```

---

## Self-Review(計画の作成者による確認)

**1. 設計書の網羅**
- 構成の4モジュール、データの流れ: Task 1〜5。
- スケールと最小表示幅、範囲の拡張、バーは両日時があるタスクのみ: Task 2、3。
- 土日祝の背景(日次のみ、祝日優先): Task 3(`test_day_scale_colors_weekends_and_holidays`、`test_holiday_wins_over_sunday`、`test_week_scale_has_no_stripes_and_scales_bars`)。
- 祝日の初回のみ自動取得、更新ボタン、失敗時の通知とフォールバック: Task 1、5。
- 追加・編集(セクション追加、タスク追加、バー・行のクリック、項目一覧、入力検証): Task 3、4、5。
- 抜けはなし。「担当者」は入力できるが、絞り込みは範囲外(後続)。

**2. プレースホルダーの確認:** TBD、TODO、「適切に処理する」などの記述はなし。すべてのコード手順にコードを載せた。

**3. 型・名前の整合**
- `GanttActions` の4フィールドは Task 3 の定義と Task 5 の `MainView` で一致する。
- マーカー名(`bar-{si}-{ti}`、`task-{si}-{ti}`、`add-task-{si}`、`refresh-holidays` など)は Task 3、4、5 のテストで一致する。
- `refresh_holidays` は `calendar.py` の関数と `MainView` のメソッドが同名のため、`views.py` では `download_holidays` として別名で取り込んでいる。

**4. Review Focus:** 5項目とも担当タスクのテストにある(1: Task 2 `test_end_before_start_gives_zero_width_without_error`、2: Task 1 `test_broken_cache_is_treated_as_missing`、3: Task 1 `test_refresh_non_csv_is_not_saved`、4: Task 4 の `test_blank_name_is_rejected` ほか、5: Task 3 `test_empty_section_and_html_like_names_are_shown_literally`)。
