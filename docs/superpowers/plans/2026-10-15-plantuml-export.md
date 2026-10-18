# PlantUML 出力 Implementation Plan

> **状態**: 実装済み — マージ PR #19(05c601a。2026-10-15)。設計書は [`2026-10-15-plantuml-export-design.md`](../specs/2026-10-15-plantuml-export-design.md)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プレビューで見ているガントチャートを、PlantUML のガント(`@startgantt`)のテキストとして保存できるようにする。

**Architecture:** 変換は、NiceGUI に依存しない純粋関数 `plantuml.py`(`handoff.py` と同じ作り)。入口は、プレビューのバーに足すボタン「PlantUML として保存」。プレビューの期間・スケール・表示項目・絞り込みを使い、保存は既存の保存ダイアログ(`exporter.ask_path`)と、一時ファイル経由の書き込みで行う。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)。描画の確認に、`java` と `/usr/local/lib/plantuml.jar`(1.2021.15)。

**Spec:** `docs/superpowers/specs/2026-10-15-plantuml-export-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。コードの識別子は英語。
- 入口はプレビューのボタンだけ(メニュー・ショートカットは足さない)。
- 日付は日単位。開始は実効の開始(`Schedule.start`)の日付、終了は実効の完了(`Schedule.end`)の日付で、0 時ちょうどなら前日(終了が開始より前なら開始日)。
- 先行の連結は、日付を固定し、矢印 `[Tm] -> [Tn]` だけ添える(両方が出力されるときだけ)。
- 同じ表示名は、イベント・タスク・チェックポイントを通した 1 つの集合で重複を避ける(2 件目以降を `名前#2`)。PlantUML は、別名を付けても、同じ表示名を 1 件にまとめるため。
- 表示名の `[` と `]` は `(` と `)` に替える。
- 色は `#rrggbb`。状態の色は `gantt.STATUS_COLORS`(`plantuml.py` は NiceGUI に依存しないので、同じ値を持ち、テストで一致を確かめる)。予定超過で `show_alerts` なら `#e53935`。イベントは `events.color_hex`。
- プレビューは折りたたみを無視する(読み取り専用の描画)ので、出力も折りたたみによらない。絞り込み中は、一致したタスクだけで、一致のないセクションは出さない。
- 保存は、プロジェクトを変更扱いにしない。拡張子は `.puml`、UTF-8、LF。既定のファイル名は `<プロジェクト名>_<YYYYMMDD>.puml`(ファイル名に使えない文字は `_`)。
- 出力しないもの: 優先度、実績、リンク、添付、カテゴリ、割り当て率、通常タスクの締切、時刻。
- 完了の確認は `uv run pytest -n auto` と `uv run ty check src`。コミットメッセージは日本語で、末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

- 期間の外・日程のないタスクだけのプロジェクト: 出力が 0 件になり、ファイルを作らず、理由を通知する(Task 1・Task 2)。
- 同名のタスクと、イベントやチェックポイントとの同名: 別々に描かれる(`#2`)(Task 1)。
- 名前に `[` `]` や日本語・記号を含む: 構文エラーにならない(Task 1。描画テストで確認)。
- 0 時ちょうどに終わるタスク、開始と同じ瞬間に終わるタスク、期間の端をまたぐタスク: 日付が 1 日ずれず、終了が開始より前にならない(Task 1)。
- 先行だけが期間の外・絞り込みで消えたとき: 矢印は出さず、後続は出る(Task 1)。
- 保存先を選ばずに閉じる・書き込みに失敗する: ファイルが残らず、プレビューに留まる(Task 2)。

---

### Task 1: 変換 `plantuml.py`

**Files:**
- Create: `src/projectapp/plantuml.py`
- Create: `test/test_plantuml.py`

**Interfaces:**
- Consumes: `filtering.TaskFilter`・`matches`・`section_has_match`、`models.Project`・`Section`・`Status`・`Task`・`TaskKind`、`timeline.Scale`・`Schedule`・`current_progress`・`effective_end`・`effective_start`・`is_overdue`、`events.color_hex`。
- Produces:
  - `PLANTUML_FILE_TYPES = ("PlantUML ファイル (*.puml)",)`。
  - `default_filename(project_name: str, today: date) -> str`。
  - `write_text(path: Path, text: str) -> Path`(拡張子がなければ `.puml`。一時ファイル経由。失敗したら何も残さず例外)。
  - `PlantUml(text: str, task_count: int, skipped: int)`(`@dataclass(frozen=True)`)。
  - `build_plantuml(project: Project, holidays: dict[date, str], period: tuple[date, date], scale: Scale, task_filter: TaskFilter, now: datetime, *, show_chips: bool = True, show_alerts: bool = True, show_events: bool = True) -> PlantUml`。`task_count` は出したタスク(チェックポイントを含む)の数、`skipped` は期間の外・日程なしで出さなかったタスクの数(絞り込みで除いたものは数えない)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_plantuml.py`:

```python
import os
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest

from projectapp.filtering import TaskFilter
from projectapp.gantt import STATUS_COLORS as GANTT_STATUS_COLORS
from projectapp.models import Actual, Assignee, Event, Project, Section, Status, Task, TaskKind
from projectapp.plantuml import (
    OVERDUE_COLOR,
    PLANTUML_FILE_TYPES,
    STATUS_COLORS,
    build_plantuml,
    default_filename,
    write_text,
)
from projectapp.timeline import Scale

PERIOD = (date(2026, 10, 12), date(2026, 10, 30))
NOW = datetime(2026, 10, 1)


def task(name: str, start: str, end: str, **kw) -> Task:
    return Task(name, planned_start=datetime.fromisoformat(start), planned_end=datetime.fromisoformat(end), **kw)


def build(project: Project, holidays: dict[date, str] | None = None, **kw):
    options = {"period": PERIOD, "scale": Scale.DAY, "task_filter": TaskFilter(), "now": NOW}
    options.update(kw)
    return build_plantuml(project, holidays or {}, **options)


def lines(project: Project, **kw) -> list[str]:
    return build(project, **kw).text.splitlines()


def test_header_and_footer() -> None:
    out = lines(Project("デモ"))
    assert out[0] == "@startgantt" and out[-1] == "@endgantt"
    assert "title デモ" in out
    assert "Project starts 2026-10-12" in out
    assert "saturday are closed" in out and "sunday are closed" in out


@pytest.mark.parametrize(("scale", "word"), [(Scale.DAY, "daily"), (Scale.WEEK, "weekly"), (Scale.MONTH, "monthly")])
def test_print_scale(scale: Scale, word: str) -> None:
    assert f"printscale {word}" in lines(Project("p"), scale=scale)


def test_text_ends_with_a_newline_and_uses_lf() -> None:
    text = build(Project("p")).text
    assert text.endswith("@endgantt\n") and "\r" not in text


def test_a_task_is_emitted_with_inclusive_dates_and_its_status_color() -> None:
    project = Project("p", tasks=[task("設計", "2026-10-13T09:00", "2026-10-14T18:00")])
    result = build(project)
    out = result.text.splitlines()
    assert "[設計] as [T1] starts 2026-10-13 and ends 2026-10-14" in out
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in out
    assert (result.task_count, result.skipped) == (1, 0)


def test_status_colors_match_the_chart() -> None:
    assert STATUS_COLORS == GANTT_STATUS_COLORS


def test_an_end_at_midnight_means_the_previous_day() -> None:
    project = Project("p", tasks=[task("a", "2026-10-13T09:00", "2026-10-15T00:00")])
    assert "[a] as [T1] starts 2026-10-13 and ends 2026-10-14" in lines(project)


def test_an_end_not_after_the_start_becomes_a_single_day() -> None:
    project = Project("p", tasks=[task("a", "2026-10-13T00:00", "2026-10-13T00:00")])
    assert "[a] as [T1] starts 2026-10-13 and ends 2026-10-13" in lines(project)


def test_a_task_crossing_the_period_edge_is_clipped() -> None:
    project = Project("p", tasks=[task("a", "2026-10-01T09:00", "2026-11-10T18:00")])
    assert "[a] as [T1] starts 2026-10-12 and ends 2026-10-30" in lines(project)


def test_tasks_outside_the_period_or_without_dates_are_skipped_and_counted() -> None:
    project = Project(
        "p",
        tasks=[
            task("前", "2026-10-01T09:00", "2026-10-11T18:00"),
            task("後", "2026-10-31T09:00", "2026-11-02T18:00"),
            Task("日程なし"),
            task("中", "2026-10-13T09:00", "2026-10-13T18:00"),
        ],
    )
    result = build(project)
    assert (result.task_count, result.skipped) == (1, 3)
    assert "[前]" not in result.text and "[日程なし]" not in result.text


def test_no_tasks_means_a_valid_empty_chart() -> None:
    result = build(Project("p"))
    assert result.task_count == 0 and result.text.splitlines()[0] == "@startgantt"


def test_root_tasks_come_first_without_a_header_then_sections_with_nested_paths() -> None:
    inner = Section("設計", [task("b", "2026-10-14T09:00", "2026-10-14T18:00")])
    project = Project(
        "p",
        tasks=[task("a", "2026-10-13T09:00", "2026-10-13T18:00")],
        sections=[Section("開発", [], [inner]), Section("空", [task("外", "2026-12-01T09:00", "2026-12-02T09:00")])],
    )
    out = lines(project)
    assert out.index("[a] as [T1] starts 2026-10-13 and ends 2026-10-13") < out.index("-- 開発 / 設計 --")
    assert "-- イベント --" not in out  # イベントがなければ、区切りも出さない
    assert out.index("-- 開発 / 設計 --") < out.index("[b] as [T2] starts 2026-10-14 and ends 2026-10-14")
    assert "-- 開発 --" not in out  # 自分のタスクがないセクションは、見出しを出さない
    assert "-- 空 --" not in out  # 出すタスクがない


def test_same_names_get_a_suffix_across_tasks_events_and_checkpoints() -> None:
    event = Event(date(2026, 10, 14), date(2026, 10, 15), "実装", "red", id="e1")
    project = Project(
        "p",
        tasks=[
            task("実装", "2026-10-13T09:00", "2026-10-13T18:00"),
            task("実装", "2026-10-14T09:00", "2026-10-14T18:00"),
            Task("実装", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 16, 18)),
        ],
        events=[event],
    )
    out = lines(project)
    labels = [line.split("]")[0][1:] for line in out if " as [" in line]
    assert sorted(labels) == ["実装", "実装#2", "実装#3", "実装#4"]
    assert len(set(labels)) == 4


def test_brackets_in_names_are_replaced() -> None:
    project = Project("p", tasks=[task("[重要] 設計", "2026-10-13T09:00", "2026-10-13T18:00")])
    out = lines(project)
    assert "[(重要) 設計] as [T1] starts 2026-10-13 and ends 2026-10-13" in out


def test_chips_add_progress_and_assignees_when_enabled() -> None:
    t = task(
        "設計",
        "2026-10-13T09:00",
        "2026-10-14T18:00",
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.4), Assignee("佐藤", 0.2), Assignee("高橋", 0.2), Assignee("伊藤", 0.2)],
        actuals=[Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 12), 40)],
    )
    out = lines(Project("p", tasks=[t]))
    assert "[設計 (田中・鈴木・佐藤ほか2名)] as [T1] starts 2026-10-13 and ends 2026-10-14" in out
    assert "[T1] is 40% completed" in out
    off = lines(Project("p", tasks=[t]), show_chips=False)
    assert "[設計] as [T1] starts 2026-10-13 and ends 2026-10-14" in off
    assert not any("completed" in line for line in off)


def test_no_progress_line_without_progress() -> None:
    out = lines(Project("p", tasks=[task("a", "2026-10-13T09:00", "2026-10-13T18:00")]))
    assert not any("completed" in line for line in out)


def test_overdue_tasks_are_red_only_when_alerts_are_on() -> None:
    project = Project("p", tasks=[task("a", "2026-10-13T09:00", "2026-10-14T18:00")])
    late = datetime(2026, 10, 20)
    assert f"[T1] is colored in {OVERDUE_COLOR}" in lines(project, now=late)
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in lines(project, now=late, show_alerts=False)
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in lines(project, now=NOW)


def test_predecessors_become_arrows_only_between_emitted_tasks() -> None:
    first = task("a", "2026-10-13T09:00", "2026-10-13T18:00", id="t1")
    second = task("b", "2026-10-14T09:00", "2026-10-14T18:00", id="t2", predecessors=["t1"])
    third = task("c", "2026-10-15T09:00", "2026-10-15T18:00", id="t3", predecessors=["t2", "gone"])
    out = lines(Project("p", tasks=[first, second, third]))
    assert "[T1] -> [T2]" in out and "[T2] -> [T3]" in out
    assert out.index("[T1] -> [T2]") > out.index("[c] as [T3] starts 2026-10-15 and ends 2026-10-15")  # 矢印は、すべての定義のあと
    hidden = lines(Project("p", tasks=[first, second, third]), task_filter=TaskFilter(query="b"))
    assert not any("->" in line for line in hidden)
    assert "[b] as [T1] starts 2026-10-14 and ends 2026-10-14" in hidden  # 後続は、先行が消えても出る


def test_a_pushed_start_follows_the_predecessor() -> None:
    first = task("a", "2026-10-13T09:00", "2026-10-16T18:00", id="t1")
    second = task("b", "2026-10-14T09:00", "2026-10-17T18:00", id="t2", predecessors=["t1"])
    out = lines(Project("p", tasks=[first, second]))
    start = next(line for line in out if line.startswith("[b]"))
    assert " starts 2026-10-16 " in start  # 先行の完了まで押し出された日付(画面と同じ)


def test_checkpoints_are_milestones_on_their_deadline() -> None:
    inside = Task("リリース", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 18))
    outside = Task("遠い節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 12, 1, 18))
    result = build(Project("p", tasks=[inside, outside]))
    out = result.text.splitlines()
    assert "[リリース] as [T1] happens on 2026-10-23" in out
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in out
    assert (result.task_count, result.skipped) == (1, 1)


def test_a_midnight_checkpoint_stays_on_its_day() -> None:
    cp = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 0, 0))
    assert "[節目] as [T1] happens on 2026-10-23" in lines(Project("p", tasks=[cp]))


def test_holidays_in_the_period_are_closed_but_weekends_and_outsiders_are_not_repeated() -> None:
    holidays = {date(2026, 10, 12): "スポーツの日", date(2026, 10, 17): "土曜の祝日", date(2026, 11, 3): "文化の日"}
    out = lines(Project("p"), holidays=holidays)
    assert "2026-10-12 is closed" in out
    assert "2026-10-17 is closed" not in out and "2026-11-03 is closed" not in out


def test_events_are_colored_cells_and_bars_clipped_to_the_period() -> None:
    inside = Event(date(2026, 10, 19), date(2026, 11, 5), "繁忙期", "lightpink", id="e1")
    before = Event(date(2026, 9, 1), date(2026, 10, 1), "過去", "red", id="e2")
    out = lines(Project("p", events=[inside, before]))
    assert "2026-10-19 to 2026-10-30 are colored in #ffb6c1" in out
    assert "-- イベント --" in out
    assert "[繁忙期] as [E1] starts 2026-10-19 and ends 2026-10-30" in out
    assert "[E1] is colored in #ffb6c1" in out
    assert not any("過去" in line for line in out)
    off = lines(Project("p", events=[inside]), show_events=False)
    assert not any("繁忙期" in line or "イベント" in line or "are colored" in line for line in off)


def test_filter_keeps_matching_tasks_and_drops_sections_without_a_match() -> None:
    project = Project(
        "p",
        tasks=[task("設計 a", "2026-10-13T09:00", "2026-10-13T18:00"), task("実装 b", "2026-10-13T09:00", "2026-10-13T18:00")],
        sections=[
            Section("開発", [task("実装 c", "2026-10-14T09:00", "2026-10-14T18:00")]),
            Section("設計部", [task("設計 d", "2026-10-14T09:00", "2026-10-14T18:00")]),
        ],
    )
    result = build(project, task_filter=TaskFilter(query="設計"))
    out = result.text.splitlines()
    assert result.task_count == 2 and result.skipped == 0
    assert "-- 設計部 --" in out and "-- 開発 --" not in out
    assert not any("実装" in line for line in out)


def test_the_filter_by_assignee() -> None:
    mine = task("a", "2026-10-13T09:00", "2026-10-13T18:00", assignees=[Assignee("田中", 1.0)])
    other = task("b", "2026-10-13T09:00", "2026-10-13T18:00", assignees=[Assignee("鈴木", 1.0)])
    result = build(Project("p", tasks=[mine, other]), task_filter=TaskFilter(assignee="田中"))
    assert result.task_count == 1 and "[a" in result.text and "[b" not in result.text


def test_default_filename_replaces_unsafe_characters() -> None:
    assert default_filename("デモ", date(2026, 10, 15)) == "デモ_20261015.puml"
    assert default_filename("a/b:c", date(2026, 10, 15)) == "a_b_c_20261015.puml"
    assert default_filename("  ", date(2026, 10, 15)) == "gantt_20261015.puml"
    assert PLANTUML_FILE_TYPES == ("PlantUML ファイル (*.puml)",)


def test_write_text_writes_utf8_adds_the_extension_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = write_text(tmp_path / "chart", "@startgantt\n日本語\n@endgantt\n")
    assert path == tmp_path / "chart.puml"
    assert path.read_bytes() == "@startgantt\n日本語\n@endgantt\n".encode()
    assert not list(tmp_path.glob("*.tmp"))


def test_write_text_failure_leaves_nothing(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        write_text(tmp_path / "missing" / "chart.puml", "x")
    assert not list(tmp_path.rglob("*.tmp"))


PLANTUML_JAR = Path(os.environ.get("PLANTUML_JAR", "/usr/local/lib/plantuml.jar"))


@pytest.mark.skipif(shutil.which("java") is None or not PLANTUML_JAR.exists(), reason="java と plantuml.jar が要る")
@pytest.mark.parametrize("scale", [Scale.DAY, Scale.WEEK, Scale.MONTH])
def test_the_output_renders_without_syntax_errors(scale: Scale) -> None:
    first = task("[重要] 設計", "2026-10-13T09:00", "2026-10-14T18:00", id="t1", status=Status.RUNNING,
                 assignees=[Assignee("田中", 1.0)], actuals=[Actual(datetime(2026, 10, 13, 9), None, 40)])
    second = task("実装", "2026-10-15T09:00", "2026-10-20T18:00", id="t2", predecessors=["t1"])
    dup = task("実装", "2026-10-16T09:00", "2026-10-21T18:00", id="t3")
    cp = Task("リリース", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 18), id="t4", predecessors=["t2"])
    project = Project(
        "検証",
        tasks=[first],
        sections=[Section("開発", [second, dup], [Section("運用", [cp])])],
        events=[Event(date(2026, 10, 19), date(2026, 10, 30), "繁忙期", "lightpink", id="e1"),
                Event(date(2026, 10, 23), date(2026, 10, 23), "本番", "red", id="e2")],
    )
    text = build(project, holidays={date(2026, 10, 12): "祝日"}, scale=scale, now=datetime(2026, 10, 20)).text
    done = subprocess.run(
        ["java", "-jar", str(PLANTUML_JAR), "-pipe", "-tsvg"], input=text.encode(), capture_output=True, timeout=60
    )
    svg = done.stdout.decode(errors="replace")
    assert done.returncode == 0 and "<svg" in svg and "Syntax Error" not in svg
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_plantuml.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.plantuml'`)。

- [ ] **Step 3: `plantuml.py` を書く**

```python
"""プレビューのガントチャートを、PlantUML のガント(`@startgantt`)のテキストにする。NiceGUI には依存しない。"""

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from projectapp.events import color_hex
from projectapp.filtering import TaskFilter, matches, section_has_match
from projectapp.models import Project, Section, Status, Task, TaskKind
from projectapp.timeline import Scale, Schedule, current_progress, effective_end, effective_start, is_overdue

PLANTUML_FILE_TYPES = ("PlantUML ファイル (*.puml)",)
UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
SCALE_NAMES = {Scale.DAY: "daily", Scale.WEEK: "weekly", Scale.MONTH: "monthly"}
STATUS_COLORS = {  # gantt.STATUS_COLORS と同じ(あちらは NiceGUI に依存するので、写して持つ。テストで一致を確かめる)
    Status.NOT_STARTED: "#78909c",
    Status.RUNNING: "#1e88e5",
    Status.PAUSED: "#fb8c00",
    Status.DONE: "#9e9e9e",
}
OVERDUE_COLOR = "#e53935"
MAX_ASSIGNEE_NAMES = 3  # これを超える担当者は「ほか n 名」にまとめる
EVENT_SECTION = "イベント"


@dataclass(frozen=True)
class PlantUml:
    text: str
    task_count: int  # 出したタスク(チェックポイントを含む)の数
    skipped: int  # 期間の外・日程なしで出さなかったタスクの数(絞り込みで除いたものは数えない)


def default_filename(project_name: str, today: date) -> str:
    """既定のファイル名 `<名前>_<YYYYMMDD>.puml`。ファイル名に使えない文字は `_` にする。"""
    name = UNSAFE_NAME_CHARS.sub("_", project_name.strip()).lstrip(".")
    return f"{name or 'gantt'}_{today:%Y%m%d}.puml"


def write_text(path: Path, text: str) -> Path:
    """テキストを書く。拡張子がなければ .puml を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    if not path.suffix:
        path = path.with_name(path.name + ".puml")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".plantuml-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def _safe(text: str) -> str:
    """PlantUML の `[ ]` の中に置けるよう、角括弧を丸括弧に替える。"""
    return text.replace("[", "(").replace("]", ")")


def _days(start: datetime, end: datetime | None) -> tuple[date, date]:
    """開始日と、終了日(含む)。終了が 0 時ちょうどなら前日。終了が開始日より前なら開始日。"""
    first = start.date()
    if end is None:
        return first, first
    last = (end - timedelta(seconds=1) if end.time() == time(0, 0) else end).date()
    return first, max(first, last)


def _assignees(task: Task) -> str:
    names = task.assignee_names
    if not names:
        return ""
    shown = "・".join(names[:MAX_ASSIGNEE_NAMES])
    more = len(names) - MAX_ASSIGNEE_NAMES
    return f" ({shown}ほか{more}名)" if more > 0 else f" ({shown})"


def build_plantuml(
    project: Project,
    holidays: dict[date, str],
    period: tuple[date, date],
    scale: Scale,
    task_filter: TaskFilter,
    now: datetime,
    *,
    show_chips: bool = True,
    show_alerts: bool = True,
    show_events: bool = True,
) -> PlantUml:
    """プレビューの設定で見えるガントチャートを、PlantUML のテキストにする。プロジェクトは変えない。"""
    p_start, p_end = period
    schedule = Schedule(project, holidays)
    used: set[str] = set()
    aliases: dict[str, str] = {}  # タスクの id → 別名(T1, T2, ...)。出したものだけ
    order: list[Task] = []
    skipped = 0

    def unique(label: str) -> str:
        candidate, n = label, 1
        while candidate in used:
            n += 1
            candidate = f"{label}#{n}"
        used.add(candidate)
        return candidate

    head = [
        "@startgantt",
        f"title {project.name}",
        f"printscale {SCALE_NAMES[scale]}",
        f"Project starts {p_start.isoformat()}",
        "saturday are closed",
        "sunday are closed",
    ]
    head += [
        f"{day.isoformat()} is closed"
        for day in sorted(holidays)
        if p_start <= day <= p_end and day.weekday() < 5
    ]

    event_lines: list[str] = []
    if show_events:
        shown = [e for e in project.events if e.start <= p_end and e.end >= p_start]
        for e in shown:
            head.append(
                f"{max(e.start, p_start).isoformat()} to {min(e.end, p_end).isoformat()}"
                f" are colored in {color_hex(e.color)}"
            )
        for n, e in enumerate(shown, 1):
            label = unique(_safe(e.text))
            event_lines.append(
                f"[{label}] as [E{n}] starts {max(e.start, p_start).isoformat()}"
                f" and ends {min(e.end, p_end).isoformat()}"
            )
            event_lines.append(f"[E{n}] is colored in {color_hex(e.color)}")

    def emit(task: Task, target: list[str]) -> None:
        nonlocal skipped
        start = effective_start(task, project, holidays, schedule)
        if start is None:
            skipped += 1
            return
        first, last = _days(start, effective_end(task, project, holidays, schedule))
        if last < p_start or first > p_end:
            skipped += 1
            return
        first, last = max(first, p_start), min(last, p_end)
        alias = f"T{len(aliases) + 1}"
        label = unique(_safe(task.name) + (_assignees(task) if show_chips else ""))
        aliases[task.id] = alias
        order.append(task)
        if task.kind is TaskKind.CHECKPOINT:
            target.append(f"[{label}] as [{alias}] happens on {first.isoformat()}")
        else:
            target.append(f"[{label}] as [{alias}] starts {first.isoformat()} and ends {last.isoformat()}")
            progress = current_progress(task)
            if show_chips and progress is not None:
                target.append(f"[{alias}] is {progress}% completed")
        overdue = show_alerts and is_overdue(task, project, holidays, now, schedule)
        target.append(f"[{alias}] is colored in {OVERDUE_COLOR if overdue else STATUS_COLORS[task.status]}")

    root_body: list[str] = []  # セクションに属さないタスク(区切りなし)。イベントの区切りより前に置く
    for task in project.tasks:
        if matches(task, task_filter):
            emit(task, root_body)
    section_body: list[str] = []

    def visit(section: Section, names: list[str]) -> None:
        if task_filter.active and not section_has_match(section, task_filter):
            return
        path = [*names, section.name]
        block: list[str] = []
        for task in section.tasks:
            if matches(task, task_filter):
                emit(task, block)
        if block:
            section_body.append(f"-- {' / '.join(path)} --")
            section_body.extend(block)
        for child in section.sections:
            visit(child, path)

    for section in project.sections:
        visit(section, [])

    arrows = [
        f"[{aliases[pid]}] -> [{aliases[task.id]}]"
        for task in order
        for pid in task.predecessors
        if pid in aliases and pid != task.id
    ]
    lines = [*head, *root_body]
    if event_lines:
        lines += [f"-- {EVENT_SECTION} --", *event_lines]
    lines += [*section_body, *arrows, "@endgantt"]
    return PlantUml("\n".join(lines) + "\n", len(aliases), skipped)
```

`emit` が `skipped` を数えるのは、絞り込みを通ったタスクだけ(呼び出し側が `matches` を先に確かめる)。ルートのタスクをイベントの区切りより前に置くのは、後ろに置くと、PlantUML では「イベント」セクションに属して見えるため。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_plantuml.py -q` と `uv run ty check src`
Expected: PASS(`java` と jar があれば描画のテスト 3 件も通る。なければ skip)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/plantuml.py test/test_plantuml.py
git commit -m "feat: ガントチャートを PlantUML のテキストにする変換を追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: プレビューのボタンと保存

**Files:**
- Modify: `src/projectapp/preview.py`(`PreviewBar` のボタン・`set_save_enabled`)
- Modify: `src/projectapp/views.py`(`PreviewBar(...)` の引数・`save_plantuml`・import)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `build_plantuml`・`default_filename`(`plantuml_filename` の別名で import)・`write_text`・`PLANTUML_FILE_TYPES`、`MainView.preview`(`PreviewSettings`)・`self.gantt.task_filter`・`self.holidays`・`self.exporter`。
- Produces: `PreviewBar(on_change, on_back, on_save, on_save_plantuml)`。マーカー `preview-plantuml`。`PreviewBar.set_save_enabled(enabled)` が、2 つのボタンを同時に切り替える。`MainView.save_plantuml()`(`async`)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `test_save_writes_the_png_and_notifies` の近くに足す(`from projectapp.plantuml import PLANTUML_FILE_TYPES` を import に足す)。`planned_task()` は 2026-10-05 12:00〜2026-10-07 12:00、`open_preview` は基準日を 2026-10-05 にして、既定の期間がそれを含む。

```python
async def test_save_plantuml_writes_the_text_and_notifies(user: User, tmp_path: Path) -> None:
    target = tmp_path / "out" / "chart"
    target.parent.mkdir()
    exporter = FakeExporter(path=target)
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: (tmp_path / "out" / "chart.puml").exists())
    text = (tmp_path / "out" / "chart.puml").read_text(encoding="utf-8")
    assert text.startswith("@startgantt") and "[設計] as [T1] starts 2026-10-05 and ends 2026-10-07" in text
    assert "title 新規プロジェクト" in text
    assert exporter.asked == [f"新規プロジェクト_{date.today():%Y%m%d}.puml"]
    assert exporter.asked_types == [PLANTUML_FILE_TYPES]
    assert exporter.captured == []  # 画像化はしない
    await user.should_see("保存しました")
    assert view.preview is not None and not view.is_dirty()  # プロジェクトは変更扱いにならない


async def test_save_plantuml_uses_the_preview_settings(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    exporter = FakeExporter(path=target)
    await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-scale").elements.pop().set_value("週次")
    user.find(marker="preview-chips").elements.pop().set_value(False)
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    text = target.read_text(encoding="utf-8")
    assert "printscale weekly" in text and "completed" not in text


async def test_save_plantuml_with_no_tasks_notifies_and_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "chart.puml")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-start").clear().type("2030-01-01")
    user.find(marker="preview-end").clear().type("2030-01-31")  # 期間の外
    user.find(marker="preview-plantuml").click()
    await user.should_see("出力できるタスクがありません")
    assert exporter.asked == [] and not list(tmp_path.glob("*.puml"))
    assert view.preview is not None


async def test_save_plantuml_notes_skipped_tasks(user: User, tmp_path: Path) -> None:
    target = tmp_path / "chart.puml"
    far = Task("遠い", planned_start=datetime(2027, 6, 1, 9), planned_end=datetime(2027, 6, 2, 18))
    exporter = FakeExporter(path=target)
    await open_preview(user, tmp_path, exporter, extra=far)
    user.find(marker="preview-end").clear().type("2026-12-31")
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: target.exists())
    await user.should_see("1 件を省きました")


async def test_cancelling_the_plantuml_dialog_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-plantuml").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.glob("*.puml")) and view.preview is not None


async def test_a_plantuml_write_failure_is_reported_and_leaves_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "missing" / "chart.puml")
    view = await open_preview(user, tmp_path, exporter)
    user.find(marker="preview-plantuml").click()
    await user.should_see("保存できませんでした")
    assert view.preview is not None and not list(tmp_path.rglob("*.tmp"))
    assert user.find(marker="preview-plantuml").elements.pop().enabled  # もう一度押せる


async def test_the_plantuml_button_is_disabled_when_not_native(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter(available=False))
    assert not user.find(marker="preview-plantuml").elements.pop().enabled


async def test_the_plantuml_button_is_disabled_for_a_bad_period_and_back_on_when_fixed(user: User, tmp_path: Path) -> None:
    await open_preview(user, tmp_path, FakeExporter())
    assert user.find(marker="preview-plantuml").elements.pop().enabled
    user.find(marker="preview-start").clear().type("2026-12-31")
    user.find(marker="preview-end").clear().type("2026-10-01")
    await user.should_see("開始日が終了日以前")
    assert not user.find(marker="preview-plantuml").elements.pop().enabled
    user.find(marker="preview-end").clear().type("2027-01-31")
    assert user.find(marker="preview-plantuml").elements.pop().enabled
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k plantuml`
Expected: FAIL(`preview-plantuml` が見つからない)。

- [ ] **Step 3: 実装する**

`preview.py`: `PreviewBar.__init__` に `on_save_plantuml: Callable[[], object]` を足し(`on_save` の次)、`self.on_save_plantuml = on_save_plantuml` を持つ。`build` の `preview-save` のボタンの次に足す:

```python
                self.plantuml_button = ui.button(
                    "PlantUML として保存", icon="code", on_click=lambda: self.on_save_plantuml()
                ).mark("preview-plantuml")
```

`set_save_enabled` を次にする:

```python
    def set_save_enabled(self, enabled: bool) -> None:
        self.save_button.set_enabled(enabled)
        self.plantuml_button.set_enabled(enabled)
```

`views.py`: import に `from projectapp.plantuml import PLANTUML_FILE_TYPES, build_plantuml, write_text` と `from projectapp.plantuml import default_filename as plantuml_filename` を足し、`datetime` が未 import なら足す(`from datetime import date, datetime, timedelta` の形に合わせる)。`PreviewBar(...)` の呼び出しを `PreviewBar(self.on_preview_change, self.exit_preview, self.save_image, self.save_plantuml)` にする。`save_image` の次にメソッドを足す:

```python
    async def save_plantuml(self) -> None:
        """プレビューの設定で、ガントチャートを PlantUML のテキストにして、選んだ場所へ保存する。失敗しても、プレビューに留まる。"""
        if self.preview is None or self.saving or not self.exporter.available:
            return
        settings = self.preview
        result = build_plantuml(
            self.project,
            self.holidays,
            (settings.start, settings.end),
            settings.scale,
            self.gantt.task_filter,
            datetime.now(),
            show_chips=settings.show_chips,
            show_alerts=settings.show_alerts,
            show_events=settings.show_events,
        )
        if result.task_count == 0:
            ui.notify("出力できるタスクがありません", type="warning")
            return
        self.saving = True
        self.preview_bar.set_save_enabled(False)
        try:
            path = await self.exporter.ask_path(plantuml_filename(self.project.name, date.today()), PLANTUML_FILE_TYPES)
            if path is None:
                return
            try:
                write_text(path, result.text)
            except OSError as exc:
                ui.notify(f"保存できませんでした: {exc}", type="negative")
                return
            note = f"(期間の外などで {result.skipped} 件を省きました)" if result.skipped else ""
            ui.notify(f"保存しました{note}")
        finally:
            self.saving = False
            if self.preview is not None:
                self.preview_bar.set_save_enabled(self.exporter.available)
```

(`self.saving` は、画像保存の「保存中は画面を変えない」の印と共通。保存ダイアログを開いている間も、プレビューの設定を変えないための印で、`on_preview_change` と `exit_preview` が見る。)

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_views.py -q -k "plantuml or preview or save"` → PASS。続けて `uv run pytest -n auto -q` と `uv run ty check src`。
Expected: すべて PASS。`test_preview.py` などで `PreviewBar(...)` を直に作っているテストがあれば、4 つ目の引数を足す(`grep -rn "PreviewBar(" test`)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/preview.py src/projectapp/views.py test/test_views.py
git commit -m "feat: プレビューから PlantUML として保存できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 文書の更新と全体の確認

**Files:**
- Modify: `CLAUDE.md`(`projectapp/`)
- Modify: `docs/development.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

「ダッシュボード」の節の次に、節を足す:

```markdown
## PlantUML の出力

- プレビューの「PlantUML として保存」で、見ているガントチャートを PlantUML のガント(`@startgantt`〜`@endgantt`)のテキストとして保存できる(保存先は、ファイル保存ダイアログで選ぶ。ネイティブウィンドウのみ。拡張子は`.puml`、UTF-8)。プロジェクトは変えず、変更扱いにもしない
- プレビューの期間・スケール(`printscale daily`・`weekly`・`monthly`)・表示項目・絞り込みを使う。期間の外のタスクと、日程のないタスクは出さず、件数を通知する。一部だけ重なるタスクは、期間の端で切る。出力できるタスクがなければ、通知して保存しない
- 日付は日単位。開始は実効の開始(先行の押し出しを反映)、終了は完了予定の日まで含める(0 時ちょうどなら前日)。時刻は出さない
- セクションは区切り(`-- 親 / 子 --`)、チェックポイントはマイルストーン(`happens on 締切日`)。先行の連結は、日付を固定し、矢印(`[T1] -> [T2]`)だけ添える。色は状態の色(予定超過の赤みがオンなら、超過を赤)。土日と、期間内の祝日を休みにする。イベントは、期間のセルの色と、先頭の「イベント」セクションの帯で出す。同じ表示名は`名前#2`にする
- 表示項目のチップと進捗がオンなら、進捗(`is 40% completed`)と担当者名を添える。優先度・実績・リンク・添付・カテゴリ・割り当て率・通常タスクの締切は出さない
```

ヘッダーの `エクスポート` メニューの説明の末尾に「(プレビューからは、画像と PlantUML で保存できる)」を足す。

- [ ] **Step 2: `docs/development.md` を更新する**

モジュール構成の表の `handoff.py` の行の次に足す: `| \`plantuml.py\` | プレビューのガントチャートを PlantUML のテキストにする。\`build_plantuml\`(\`PlantUml\`: \`text\`・\`task_count\`・\`skipped\`)、\`default_filename\`、\`write_text\`(一時ファイル経由)。純粋関数(NiceGUI に依存しない)。状態の色は \`gantt.STATUS_COLORS\` の写し(テストで一致を確かめる)。表示名は、イベント・タスク・チェックポイントを通した 1 つの集合で重複を避ける(PlantUML は、別名を付けても、同じ表示名を 1 件にまとめるため)。描画のテストは、\`java\` と \`plantuml.jar\`(\`PLANTUML_JAR\` か \`/usr/local/lib/plantuml.jar\`)があるときだけ走る |`。設計書の表に `PlantUML 出力 | 2026-10-15-plantuml-export-design.md` を足す。

- [ ] **Step 3: 全体の確認**

Run: `uv run pytest -n auto -q` と `uv run ty check src`
Expected: すべて PASS、型エラーなし。

- [ ] **Step 4: 実機での確認(手動)**

`~/.projectapp/イベント確認.json` を開き、プレビューで「PlantUML として保存」を押して `.puml` を保存する。`java -jar /usr/local/lib/plantuml.jar -tpng <保存したファイル>` で描画し、次を目で確かめる。結果は PR の説明に書く:
  - タスクの帯・セクションの区切り・イベントの帯とセルの色・土日の休みが出る。
  - 日次・週次・月次のスケールで、描画できる。
  - 期間を狭めると、期間の外のタスクが消える。

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md docs/development.md
git commit -m "docs: PlantUML 出力を仕様と開発者向けメモに反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
