import os
import shutil
import subprocess
from datetime import date, datetime, time
from pathlib import Path

import pytest

from projectapp.filtering import TaskFilter
from projectapp.gantt import STATUS_COLORS as GANTT_STATUS_COLORS
from projectapp.models import (
    Actual,
    Assignee,
    Event,
    Member,
    Project,
    ReferenceValue,
    Section,
    Status,
    Task,
    TaskKind,
    WorkDay,
)
from projectapp.plantuml import (
    OVERDUE_COLOR,
    PLANTUML_FILE_TYPES,
    STATUS_COLORS,
    build_plantuml,
    default_filename,
    weekly_crew_notice,
    write_text,
)
from projectapp.timeline import Scale

PERIOD = (date(2026, 10, 12), date(2026, 10, 30))
NOW = datetime(2026, 10, 1)


def task(name: str, start: str, end: str, **kw) -> Task:
    return Task(
        name,
        planned_start=datetime.fromisoformat(start),
        planned_end=datetime.fromisoformat(end),
        **kw,
    )


def build(project: Project, holidays: dict[date, str] | None = None, **kw):
    options = {
        "period": PERIOD,
        "scale": Scale.DAY,
        "task_filter": TaskFilter(),
        "now": NOW,
    }
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


@pytest.mark.parametrize(
    ("scale", "word"),
    [(Scale.DAY, "daily"), (Scale.WEEK, "weekly"), (Scale.MONTH, "monthly")],
)
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


def test_root_tasks_come_first_without_a_header_then_sections_with_nested_paths() -> (
    None
):
    inner = Section("設計", [task("b", "2026-10-14T09:00", "2026-10-14T18:00")])
    project = Project(
        "p",
        tasks=[task("a", "2026-10-13T09:00", "2026-10-13T18:00")],
        sections=[
            Section("開発", [], [inner]),
            Section("空", [task("外", "2026-12-01T09:00", "2026-12-02T09:00")]),
        ],
    )
    out = lines(project)
    assert out.index("[a] as [T1] starts 2026-10-13 and ends 2026-10-13") < out.index(
        "-- 開発 / 設計 --"
    )
    assert "-- イベント --" not in out  # イベントがなければ、区切りも出さない
    assert out.index("-- 開発 / 設計 --") < out.index(
        "[b] as [T2] starts 2026-10-14 and ends 2026-10-14"
    )
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
    project = Project(
        "p", tasks=[task("[重要] 設計", "2026-10-13T09:00", "2026-10-13T18:00")]
    )
    out = lines(project)
    assert "[(重要) 設計] as [T1] starts 2026-10-13 and ends 2026-10-13" in out


def test_chips_add_progress_and_assignees_when_enabled() -> None:
    t = task(
        "設計",
        "2026-10-13T09:00",
        "2026-10-14T18:00",
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 1.0)],
        actuals=[Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 12))],
        progress=40,
    )
    out = lines(Project("p", tasks=[t]))
    assert (
        "[設計] as [T1] on {田中:60%} {鈴木} starts 2026-10-13 and ends 2026-10-14"
        in out
    )
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
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in lines(
        project, now=late, show_alerts=False
    )
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in lines(
        project, now=NOW
    )


def test_predecessors_become_arrows_only_between_emitted_tasks() -> None:
    first = task("a", "2026-10-13T09:00", "2026-10-13T18:00", id="t1")
    second = task(
        "b", "2026-10-14T09:00", "2026-10-14T18:00", id="t2", predecessors=["t1"]
    )
    third = task(
        "c",
        "2026-10-15T09:00",
        "2026-10-15T18:00",
        id="t3",
        predecessors=["t2", "gone"],
    )
    out = lines(Project("p", tasks=[first, second, third]))
    assert "[T1] -> [T2]" in out and "[T2] -> [T3]" in out
    assert out.index("[T1] -> [T2]") > out.index(
        "[c] as [T3] starts 2026-10-15 and ends 2026-10-15"
    )  # 矢印は、すべての定義のあと
    hidden = lines(
        Project("p", tasks=[first, second, third]), task_filter=TaskFilter(query="b")
    )
    assert not any("->" in line for line in hidden)
    assert (
        "[b] as [T1] starts 2026-10-14 and ends 2026-10-14" in hidden
    )  # 後続は、先行が消えても出る


def test_a_pushed_start_follows_the_predecessor() -> None:
    first = task("a", "2026-10-13T09:00", "2026-10-16T18:00", id="t1")
    second = task(
        "b", "2026-10-14T09:00", "2026-10-17T18:00", id="t2", predecessors=["t1"]
    )
    out = lines(Project("p", tasks=[first, second]))
    start = next(line for line in out if line.startswith("[b]"))
    assert " starts 2026-10-16 " in start  # 先行の完了まで押し出された日付(画面と同じ)


def test_checkpoints_are_milestones_on_their_deadline() -> None:
    inside = Task(
        "リリース", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 18)
    )
    outside = Task(
        "遠い節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 12, 1, 18)
    )
    result = build(Project("p", tasks=[inside, outside]))
    out = result.text.splitlines()
    assert "[リリース] as [T1] happens on 2026-10-23" in out
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in out
    assert (result.task_count, result.skipped) == (1, 1)


def test_a_midnight_checkpoint_stays_on_its_day() -> None:
    cp = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 0, 0))
    assert "[節目] as [T1] happens on 2026-10-23" in lines(Project("p", tasks=[cp]))


def test_holidays_in_the_period_are_closed_but_weekends_and_outsiders_are_not_repeated() -> (
    None
):
    holidays = {
        date(2026, 10, 12): "スポーツの日",
        date(2026, 10, 17): "土曜の祝日",
        date(2026, 11, 3): "文化の日",
    }
    out = lines(Project("p"), holidays=holidays)
    assert "2026-10-12 is closed" in out
    assert "2026-10-17 is closed" not in out and "2026-11-03 is closed" not in out


def test_events_are_colored_cells_and_bars_clipped_to_the_period() -> None:
    inside = Event(
        date(2026, 10, 19), date(2026, 11, 5), "繁忙期", "lightpink", id="e1"
    )
    before = Event(date(2026, 9, 1), date(2026, 10, 1), "過去", "red", id="e2")
    out = lines(Project("p", events=[inside, before]))
    assert "2026-10-19 to 2026-10-30 are colored in #ffb6c1" in out
    assert "-- イベント --" in out
    assert "[繁忙期] as [E1] starts 2026-10-19 and ends 2026-10-30" in out
    assert "[E1] is colored in #ffb6c1" in out
    assert not any("過去" in line for line in out)
    off = lines(Project("p", events=[inside]), show_events=False)
    assert not any(
        "繁忙期" in line or "イベント" in line or "are colored" in line for line in off
    )


TODAY = datetime(2026, 10, 14, 9)  # PERIOD(10/12〜10/30)の中


def test_today_is_a_red_colored_day() -> None:
    assert "2026-10-14 is colored in red" in lines(Project("p"), now=TODAY)


def test_today_line_is_omitted_when_off_or_outside_the_period() -> None:
    assert not any(
        "is colored in red" in line
        for line in lines(Project("p"), now=TODAY, show_today=False)
    )
    assert not any(
        "is colored in red" in line
        for line in lines(Project("p"), now=datetime(2026, 10, 1))
    )
    assert not any(
        "is colored in red" in line
        for line in lines(Project("p"), now=datetime(2026, 10, 31))
    )


def test_today_is_inclusive_at_both_ends_of_the_period() -> None:
    assert "2026-10-12 is colored in red" in lines(
        Project("p"), now=datetime(2026, 10, 12, 0, 0)
    )
    assert "2026-10-30 is colored in red" in lines(
        Project("p"), now=datetime(2026, 10, 30, 23, 59)
    )


def test_today_comes_after_the_event_colors_and_is_independent_of_show_events() -> None:
    event = Event(
        date(2026, 10, 13), date(2026, 10, 16), "繁忙期", "lightpink", id="e1"
    )
    out = lines(Project("p", events=[event]), now=TODAY)
    assert out.index("2026-10-14 is colored in red") > out.index(
        "2026-10-13 to 2026-10-16 are colored in #ffb6c1"
    )
    off = lines(Project("p", events=[event]), now=TODAY, show_events=False)
    assert "2026-10-14 is colored in red" in off


def test_filter_keeps_matching_tasks_and_drops_sections_without_a_match() -> None:
    project = Project(
        "p",
        tasks=[
            task("設計 a", "2026-10-13T09:00", "2026-10-13T18:00"),
            task("実装 b", "2026-10-13T09:00", "2026-10-13T18:00"),
        ],
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
    mine = task(
        "a", "2026-10-13T09:00", "2026-10-13T18:00", assignees=[Assignee("田中", 1.0)]
    )
    other = task(
        "b", "2026-10-13T09:00", "2026-10-13T18:00", assignees=[Assignee("鈴木", 1.0)]
    )
    result = build(
        Project("p", tasks=[mine, other]), task_filter=TaskFilter(assignee="田中")
    )
    assert result.task_count == 1 and "[a" in result.text and "[b" not in result.text


def test_default_filename_replaces_unsafe_characters() -> None:
    assert default_filename("デモ", date(2026, 10, 15)) == "デモ_20261015.puml"
    assert default_filename("a/b:c", date(2026, 10, 15)) == "a_b_c_20261015.puml"
    assert default_filename("  ", date(2026, 10, 15)) == "gantt_20261015.puml"
    assert PLANTUML_FILE_TYPES == ("PlantUML ファイル (*.puml)",)


def test_write_text_writes_utf8_adds_the_extension_and_leaves_no_temp_file(
    tmp_path: Path,
) -> None:
    path = write_text(tmp_path / "chart", "@startgantt\n日本語\n@endgantt\n")
    assert path == tmp_path / "chart.puml"
    assert path.read_bytes() == "@startgantt\n日本語\n@endgantt\n".encode()
    assert not list(tmp_path.glob("*.tmp"))


def test_write_text_failure_leaves_nothing(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        write_text(tmp_path / "missing" / "chart.puml", "x")
    assert not list(tmp_path.rglob("*.tmp"))


PLANTUML_JAR = Path(os.environ.get("PLANTUML_JAR", "/usr/local/lib/plantuml.jar"))


JAVA_FAST = ["java", "-Djava.awt.headless=true", "-XX:TieredStopAtLevel=1", "-jar"]


@pytest.fixture(scope="module")
def rendered_svgs() -> dict[Scale, str]:
    """3 つのスケールを 1 回の JVM 起動でまとめて描く(起動が支配的なので、スケールごとに起動しない)。"""
    first = task(
        "[重要] 設計",
        "2026-10-13T09:00",
        "2026-10-14T18:00",
        id="t1",
        status=Status.RUNNING,
        assignees=[Assignee("田中", 1.0)],
        actuals=[Actual(datetime(2026, 10, 13, 9), None, 40)],
    )
    second = task(
        "実装",
        "2026-10-15T09:00",
        "2026-10-20T18:00",
        id="t2",
        predecessors=["t1"],
        assignees=[Assignee("田中", 0.5), Assignee("鈴木:{特}", 1.0)],
    )  # 担当構文と、記号の置き換え
    dup = task("実装", "2026-10-16T09:00", "2026-10-21T18:00", id="t3")
    cp = Task(
        "リリース",
        kind=TaskKind.CHECKPOINT,
        deadline=datetime(2026, 10, 23, 18),
        id="t4",
        predecessors=["t2"],
    )
    project = Project(
        "検証",
        tasks=[first],
        sections=[Section("開発", [second, dup], [Section("運用", [cp])])],
        events=[
            Event(
                date(2026, 10, 19), date(2026, 10, 30), "繁忙期", "lightpink", id="e1"
            ),
            Event(date(2026, 10, 23), date(2026, 10, 23), "本番", "red", id="e2"),
        ],
        members=[
            Member(
                "甲",
                work_days=[
                    WorkDay(date(2026, 10, 17), time(13), time(16)),
                    WorkDay(date(2026, 10, 14)),
                ],
            )
        ],
    )
    scales = [Scale.DAY, Scale.WEEK, Scale.MONTH]
    texts = [
        build(
            project,
            holidays={date(2026, 10, 12): "祝日"},
            scale=s,
            now=datetime(2026, 10, 20),
        ).text
        for s in scales
    ]
    done = subprocess.run(
        [*JAVA_FAST, str(PLANTUML_JAR), "-pipe", "-tsvg"],
        input="\n".join(texts).encode(),
        capture_output=True,
        timeout=120,
    )
    assert done.returncode == 0
    svgs = [
        chunk + "</svg>"
        for chunk in done.stdout.decode(errors="replace").split("</svg>")[:-1]
    ]
    assert len(svgs) == len(scales)  # 構文エラーでも、エラーの図が 1 枚出る
    return dict(zip(scales, svgs))


@pytest.mark.skipif(
    shutil.which("java") is None or not PLANTUML_JAR.exists(),
    reason="java と plantuml.jar が要る",
)
@pytest.mark.parametrize("scale", [Scale.DAY, Scale.WEEK, Scale.MONTH])
def test_the_output_renders_without_syntax_errors(
    scale: Scale, rendered_svgs: dict[Scale, str]
) -> None:
    svg = rendered_svgs[scale]
    assert "<svg" in svg and "Syntax Error" not in svg


def test_every_assignee_is_listed_without_a_limit() -> None:
    names = ["田中", "鈴木", "佐藤", "高橋", "伊藤"]
    t = task(
        "設計",
        "2026-10-13T09:00",
        "2026-10-13T18:00",
        assignees=[Assignee(n, 1.0) for n in names],
    )
    out = lines(Project("p", tasks=[t]))
    assert (
        "[設計] as [T1] on {田中} {鈴木} {佐藤} {高橋} {伊藤} starts 2026-10-13 and ends 2026-10-13"
        in out
    )


def test_allocation_is_omitted_at_one_hundred_percent_and_rounded_otherwise() -> None:
    t = task(
        "設計",
        "2026-10-13T09:00",
        "2026-10-13T18:00",
        assignees=[
            Assignee("田中", 1.0),
            Assignee("鈴木", 1 / 3),
            Assignee("佐藤", 0.005),
        ],
    )
    out = lines(Project("p", tasks=[t]))
    assert any("on {田中} {鈴木:33%} {佐藤:1%} starts" in line for line in out)


def test_assignee_names_cannot_break_the_resource_syntax() -> None:
    t = task(
        "設計",
        "2026-10-13T09:00",
        "2026-10-13T18:00",
        assignees=[Assignee("田{中}:A", 0.5)],
    )
    out = lines(Project("p", tasks=[t]))
    assert any("on {田(中)：A:50%} starts" in line for line in out)


def test_no_resource_clause_without_assignees_or_with_chips_off() -> None:
    plain = task("a", "2026-10-13T09:00", "2026-10-13T18:00")
    assigned = task(
        "b", "2026-10-14T09:00", "2026-10-14T18:00", assignees=[Assignee("田中", 1.0)]
    )
    project = Project("p", tasks=[plain, assigned])
    assert not any(" on {" in line for line in lines(project, show_chips=False))
    assert [line for line in lines(project) if " on {" in line] == [
        "[b] as [T2] on {田中} starts 2026-10-14 and ends 2026-10-14"
    ]


def test_checkpoints_never_get_a_resource_clause() -> None:
    t = Task(
        "節目",
        kind=TaskKind.CHECKPOINT,
        deadline=datetime(2026, 10, 14, 17),
        assignees=[Assignee("田中", 1.0)],
    )
    assert not any(" on {" in line for line in lines(Project("p", tasks=[t])))


def test_exported_assignees_read_back_through_the_importer() -> None:
    from projectapp.puml_import import parse_plantuml

    t = task(
        "設計",
        "2026-10-13T09:00",
        "2026-10-14T18:00",
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 1.0)],
    )
    text = build(Project("p", tasks=[t])).text
    back = parse_plantuml(text, "戻し").project.all_tasks()[0]
    assert [(a.name, round(a.allocation, 2)) for a in back.assignees] == [
        ("田中", 0.6),
        ("鈴木", 1.0),
    ]


def test_member_work_days_do_not_change_the_closed_lines() -> None:
    days = [
        WorkDay(date(2026, 10, 17), time(13), time(16)),
        WorkDay(date(2026, 10, 14)),
    ]
    out = lines(
        Project("p", members=[Member("甲", work_days=days)]),
        holidays={date(2026, 10, 13): "祝"},
    )
    assert [line for line in out if "is closed" in line or "is open" in line] == [
        "2026-10-13 is closed"
    ]


def test_no_overrides_leave_the_closed_lines_unchanged() -> None:
    out = lines(Project("p"), holidays={date(2026, 10, 13): "祝"})
    assert [line for line in out if "is closed" in line or "is open" in line] == [
        "2026-10-13 is closed"
    ]


def test_unselected_tasks_are_not_emitted_and_not_counted_as_skipped() -> None:
    a = task("残す", "2026-10-13T09:00", "2026-10-14T18:00")
    b = task("外す", "2026-10-15T09:00", "2026-10-16T18:00")
    result = build(Project("p", tasks=[a, b]), excluded=frozenset({b.id}))
    assert "[外す]" not in result.text
    assert "[残す] as [T1] starts 2026-10-13 and ends 2026-10-14" in result.text
    assert (result.task_count, result.skipped) == (1, 0)


def test_a_section_with_every_task_unselected_has_no_divider() -> None:
    a = task("甲", "2026-10-13T09:00", "2026-10-14T18:00")
    b = task("乙", "2026-10-15T09:00", "2026-10-16T18:00")
    project = Project("p", sections=[Section("A", tasks=[a]), Section("B", tasks=[b])])
    out = lines(project, excluded=frozenset({a.id}))
    assert "-- A --" not in out and "-- B --" in out


def test_arrows_to_or_from_an_unselected_task_are_dropped() -> None:
    a = task("先", "2026-10-13T09:00", "2026-10-14T18:00")
    b = task("後", "2026-10-15T09:00", "2026-10-16T18:00", predecessors=[a.id])
    out = lines(Project("p", tasks=[a, b]), excluded=frozenset({a.id}))
    assert not any("->" in line for line in out)


def test_nothing_is_excluded_by_default() -> None:
    a = task("甲", "2026-10-13T09:00", "2026-10-14T18:00")
    assert build(Project("p", tasks=[a])).task_count == 1


def two_tasks_for(
    name: str, first: tuple[str, str], second: tuple[str, str], allocation: float = 0.6
) -> Project:
    def make(label: str, span: tuple[str, str]) -> Task:
        return task(label, span[0], span[1], assignees=[Assignee(name, allocation)])

    return Project(
        "p", members=[Member(name)], tasks=[make("前", first), make("後", second)]
    )


def test_a_same_day_handover_is_reported_because_plantuml_counts_whole_days() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-13T09:00", "2026-10-14T12:00"),
        ("2026-10-14T13:00", "2026-10-15T18:00"),
    )
    assert build(project).day_overloads == (("田中", date(2026, 10, 14)),)


def test_a_real_overlap_is_not_reported_because_the_app_already_flags_it() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-13T09:00", "2026-10-15T18:00"),
        ("2026-10-14T09:00", "2026-10-16T18:00"),
    )
    assert build(project).day_overloads == ()


def test_a_finished_task_that_overlaps_counts_in_plantuml_but_not_in_the_app() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-13T09:00", "2026-10-15T18:00"),
        ("2026-10-14T09:00", "2026-10-16T18:00"),
    )
    project.tasks[
        0
    ].status = Status.DONE  # アプリは終了したタスクを数えない。PlantUML は描く
    days = {d for _, d in build(project).day_overloads}
    assert days == {date(2026, 10, 14), date(2026, 10, 15)}


def test_nothing_is_reported_when_the_day_total_stays_within_100_percent() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-13T09:00", "2026-10-14T12:00"),
        ("2026-10-14T13:00", "2026-10-15T18:00"),
        allocation=0.5,
    )
    assert build(project).day_overloads == ()


def test_nothing_is_reported_without_the_chips_because_no_assignee_is_emitted() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-13T09:00", "2026-10-14T12:00"),
        ("2026-10-14T13:00", "2026-10-15T18:00"),
    )
    assert build(project, show_chips=False).day_overloads == ()


def test_an_unselected_task_is_not_counted_in_the_report() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-13T09:00", "2026-10-14T12:00"),
        ("2026-10-14T13:00", "2026-10-15T18:00"),
    )
    assert build(project, excluded=frozenset({project.tasks[1].id})).day_overloads == ()


def test_closed_days_are_not_counted() -> None:
    project = two_tasks_for(
        "田中",
        ("2026-10-16T09:00", "2026-10-17T12:00"),
        ("2026-10-17T13:00", "2026-10-19T18:00"),
    )
    assert build(project).day_overloads == ()  # 重なる 10/17 は土曜(休み)


def test_the_notice_lists_up_to_three_person_days_and_counts_the_rest() -> None:
    from projectapp.plantuml import day_overload_notice

    assert day_overload_notice(()) is None
    items = tuple(("田中", date(2026, 10, d)) for d in (14, 15, 16, 19, 20))
    text = day_overload_notice(items)
    assert text is not None
    assert (
        "日単位" in text
        and "田中 10/14、田中 10/15、田中 10/16" in text
        and "ほか 2 件" in text
    )
    assert "ほか" not in (day_overload_notice(items[:3]) or "")


def test_weekly_tasks_are_counted_for_the_approximation_notice() -> None:
    weeks = [[Assignee("田中")], [Assignee("鈴木")]]
    weekly = task(
        "a",
        "2026-10-12T09:00",
        "2026-10-20T17:00",
        assignees=[Assignee("田中"), Assignee("鈴木")],
        weekly_crew=weeks,
    )
    plain = task(
        "b", "2026-10-12T09:00", "2026-10-14T17:00", assignees=[Assignee("田中")]
    )
    project = Project(
        "p", members=[Member("田中"), Member("鈴木")], tasks=[weekly, plain]
    )
    assert build(project).weekly_tasks == 1
    assert (
        build(project, show_chips=False).weekly_tasks == 0
    )  # 担当者を出さないときは近似にならない
    assert (
        weekly_crew_notice(1)
        == "週ごとの担当は近似で出力しました(1 件。和集合の担当者を、各人の最大の割り当て率で出しています)"
    )
    assert weekly_crew_notice(0) is None


REF_VALUE = ReferenceValue(
    planned_start=datetime(2026, 10, 14, 9),
    planned_end=datetime(2026, 10, 20, 17),
    progress=45,
    delayed=2,
)


def reference_project() -> Project:
    ref = Task("基盤開発", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤")
    return Project("本体", base_date=date(2026, 10, 1), tasks=[ref])


def test_a_reference_row_is_one_band_named_with_the_reference_mark() -> None:
    result = build(reference_project(), references={"ref": REF_VALUE})
    assert (
        "[基盤開発(参照)] as [T1] starts 2026-10-14 and ends 2026-10-20" in result.text
    )
    assert f"[T1] is colored in {OVERDUE_COLOR}" in result.text  # 遅延があるので赤
    assert "completed" not in result.text  # 進捗は出さない
    assert result.task_count == 1


def test_a_reference_row_without_delay_uses_the_not_started_color() -> None:
    value = ReferenceValue(
        planned_start=REF_VALUE.planned_start, planned_end=REF_VALUE.planned_end
    )
    result = build(reference_project(), references={"ref": value})
    assert f"[T1] is colored in {STATUS_COLORS[Status.NOT_STARTED]}" in result.text


def test_a_reference_row_without_a_value_is_skipped_and_counted() -> None:
    result = build(reference_project())
    assert result.task_count == 0 and result.skipped == 1


def test_today_uses_the_configured_color_instead_of_red() -> None:
    out = lines(Project("p"), now=TODAY, today_color="#1e88e5")
    assert "2026-10-14 is colored in #1e88e5" in out
    assert not any("is colored in red" in line for line in out)


def test_the_configured_today_color_is_not_used_when_today_is_off() -> None:
    out = lines(Project("p"), now=TODAY, today_color="#1e88e5", show_today=False)
    assert not any("#1e88e5" in line for line in out)
