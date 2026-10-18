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
        actuals=[Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 12))],
        progress=40,
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
