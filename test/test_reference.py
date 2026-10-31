from datetime import date, datetime

import pytest

from projectapp.models import Actual, Assignee, Event, Member, Project, Section, Status, Task, TaskKind
from projectapp.reference import compute_reference

NOW = datetime(2026, 10, 8, 10)


def D(month: int, day: int, hour: int = 9) -> datetime:
    return datetime(2026, month, day, hour)


def source() -> Project:
    return Project(
        "基盤",
        daily_hours=8.0,
        members=[Member("田中", 1.0)],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a", planned_start=D(10, 5), effort_hours=8.0, assignees=[Assignee("田中")],
                         status=Status.DONE, actuals=[Actual(D(10, 5), D(10, 5, 17))]),
                    Task("b", id="b", planned_start=D(10, 6), effort_hours=16.0, assignees=[Assignee("田中")],
                         progress=50, actuals=[Actual(D(10, 6), None)]),
                ],
            )
        ],
        tasks=[Task("c", id="c", planned_start=D(10, 20), effort_hours=8.0)],
    )


def test_the_span_progress_and_actuals_cover_the_whole_project() -> None:
    value = compute_reference(source(), {}, NOW)
    assert value.planned_start == D(10, 5)
    assert value.planned_end is not None and value.planned_end > D(10, 20)
    assert value.actual_start == D(10, 5)
    assert value.actual_end is None  # 実行中の区間がある
    assert value.finished is False
    # 工数の重み: a=8h で 100%、b=16h で 50%、c=8h で 0% → (800 + 800 + 0) / 32 = 50
    assert value.progress == 50


def test_delay_counts_unfinished_tasks_past_their_end() -> None:
    value = compute_reference(source(), {}, NOW)
    assert value.delayed == 1  # b は完了予定(10/7)を過ぎて終了していない。a は終了、c は先


def test_overlapping_assignments_become_a_peak_and_spans() -> None:
    project = Project(
        "基盤",
        members=[Member("田中", 1.0)],
        tasks=[
            Task("a", planned_start=D(10, 5), effort_hours=16.0, assignees=[Assignee("田中", 0.8)]),
            Task("b", planned_start=D(10, 5), effort_hours=16.0, assignees=[Assignee("田中", 0.5)]),
        ],
    )
    value = compute_reference(project, {}, NOW)
    assert value.peak_member == "田中" and round(value.peak_load, 2) == 1.3
    assert value.overloads and value.overloads[0].member == "田中"


def test_reference_rows_and_summaries_are_not_counted_and_an_empty_project_has_no_span() -> None:
    project = Project("基盤", tasks=[Task("ref", kind=TaskKind.REFERENCE, ref_project="x")])
    value = compute_reference(project, {}, NOW)
    assert (value.planned_start, value.planned_end, value.progress, value.finished) == (None, None, None, False)
    assert (value.delayed, value.peak_load, value.overloads) == (0, 0.0, ())


def test_a_finished_project_reports_its_last_actual_end() -> None:
    project = Project(
        "基盤",
        tasks=[Task("a", planned_start=D(10, 5), effort_hours=8.0, status=Status.DONE, actuals=[Actual(D(10, 5), D(10, 6))])],
    )
    value = compute_reference(project, {}, NOW)
    assert value.finished is True and value.actual_end == D(10, 6) and value.progress == 100


from projectapp.models import ReferenceValue
from projectapp.timeline import Schedule, effective_end, effective_start, is_overdue, progress_state


def ref_project(**kwargs: object) -> tuple[Project, Task]:
    ref = Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤", **kwargs)  # type: ignore[arg-type]
    after = Task("後続", id="after", planned_start=D(10, 1), effort_hours=8.0, predecessors=["ref"])
    return Project("p", daily_hours=8.0, tasks=[ref, after]), ref


def test_a_reference_row_takes_its_span_from_the_reference_value() -> None:
    project, ref = ref_project()
    value = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17))
    schedule = Schedule(project, {}, {"ref": value})
    assert (schedule.start(ref), schedule.end(ref)) == (D(10, 5), D(10, 20, 17))
    assert effective_start(ref, project, {}, schedule) == D(10, 5)
    assert effective_end(ref, project, {}, schedule) == D(10, 20, 17)
    assert Schedule(project, {}).start(ref) is None  # 参照値がなければ日程なし


def test_a_successor_is_pushed_by_the_reference_end_or_the_actual_end_when_finished() -> None:
    project, _ = ref_project()
    after = project.tasks[1]
    open_value = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17), actual_end=D(10, 19, 17))
    assert Schedule(project, {}, {"ref": open_value}).start(after) == D(10, 20, 17)
    done_value = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17), actual_end=D(10, 19, 17), finished=True)
    assert Schedule(project, {}, {"ref": done_value}).start(after) == D(10, 19, 17)


def test_a_reference_row_is_red_only_when_the_reference_end_passes_its_deadline() -> None:
    project, ref = ref_project(deadline=D(10, 15, 17))
    late = Schedule(project, {}, {"ref": ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20, 17))})
    assert is_overdue(ref, project, {}, NOW, late)
    ontime = Schedule(project, {}, {"ref": ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 14, 17))})
    assert not is_overdue(ref, project, {}, NOW, ontime)
    assert progress_state(ref, project, {}, NOW, ontime) is None


def test_reference_rows_are_left_out_of_the_dashboard_counts() -> None:
    from projectapp.dashboard import _tasks

    project, _ = ref_project()
    assert [t.id for t in _tasks(project)] == ["after"]


from pathlib import Path

from projectapp.models import ReferenceMode
from projectapp.reference import ReferenceResolver, build_references, load_children, missing_references, take_snapshot
from projectapp.storage import save_project


def resolver_for(folder: Path) -> ReferenceResolver:
    return ReferenceResolver(lambda: folder, lambda: {})


def referencing(mode: ReferenceMode = ReferenceMode.LIVE, **kwargs: object) -> Project:
    ref = Task("基盤", id="ref", kind=TaskKind.REFERENCE, ref_project="基盤", **kwargs)  # type: ignore[arg-type]
    return Project("p", reference_mode=mode, tasks=[ref])


def test_a_live_reference_reads_the_file_and_caches_by_content(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    value, problem = resolver.live("基盤", NOW)
    assert problem == "" and value is not None and value.planned_start == D(10, 5)
    again, _ = resolver.live("基盤", NOW)
    assert again is value  # 内容が同じ間は、同じ値を返す
    changed = source()
    changed.tasks.append(Task("d", id="d", planned_start=D(12, 1), effort_hours=8.0))
    save_project(changed, tmp_path)
    after, _ = resolver.live("基盤", NOW)
    assert after is not value and after is not None and after.planned_end != value.planned_end


def test_a_missing_or_broken_file_gives_a_reason_not_an_error(tmp_path: Path) -> None:
    resolver = resolver_for(tmp_path)
    assert resolver.live("基盤", NOW) == (None, "「基盤.json」が格納先にありません")
    (tmp_path / "基盤.json").write_text("{ not json", encoding="utf-8")
    value, problem = resolver.live("基盤", NOW)
    assert value is None and problem.startswith("「基盤.json」を読めません")


def test_build_references_in_live_mode_uses_the_file(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    refs = build_references(referencing(), resolver_for(tmp_path), NOW)
    assert refs["ref"].value is not None and refs["ref"].stale is False and refs["ref"].source is ReferenceMode.LIVE


def test_build_references_in_snapshot_mode_uses_the_saved_value_and_flags_stale(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    taken = take_snapshot(resolver, "基盤", NOW)
    assert taken is not None and taken.taken_at == NOW
    project = referencing(ReferenceMode.SNAPSHOT, ref_snapshot=taken)
    fresh = build_references(project, resolver, NOW)["ref"]
    assert fresh.value == taken and fresh.stale is False
    project.tasks[0].ref_snapshot = ReferenceValue(planned_start=D(1, 1), planned_end=D(1, 2))
    old = build_references(project, resolver, NOW)["ref"]
    assert old.stale is True and old.value == project.tasks[0].ref_snapshot  # 保存した値のまま出す
    empty = referencing(ReferenceMode.SNAPSHOT)
    assert build_references(empty, resolver, NOW)["ref"].value is None  # スナップショットがなければ帯なし


def test_snapshot_mode_keeps_the_saved_value_when_the_file_is_missing(tmp_path: Path) -> None:
    saved = ReferenceValue(planned_start=D(10, 5), planned_end=D(10, 20), taken_at=NOW)
    project = referencing(ReferenceMode.SNAPSHOT, ref_snapshot=saved)
    ref = build_references(project, resolver_for(tmp_path), NOW)["ref"]
    assert ref.value == saved and "格納先にありません" in ref.problem and ref.stale is False


def test_missing_references_lists_each_file_once(tmp_path: Path) -> None:
    project = Project("p", tasks=[
        Task("a", id="a", kind=TaskKind.REFERENCE, ref_project="ない"),
        Task("b", id="b", kind=TaskKind.REFERENCE, ref_project="ない"),
        Task("c", id="c", kind=TaskKind.REFERENCE, ref_project="基盤"),
    ])
    save_project(source(), tmp_path)
    assert missing_references(project, resolver_for(tmp_path), NOW) == ["ない"]


def test_reference_passes_the_event_closed_days_to_the_computation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project("基盤", events=[Event(date(2026, 10, 12), date(2026, 10, 12), "休業", closed=True)])
    save_project(project, tmp_path)
    seen: list[dict[date, str]] = []
    real = compute_reference

    def spy(p: Project, holidays: dict[date, str], now: datetime) -> ReferenceValue:
        seen.append(holidays)
        return real(p, holidays, now)

    monkeypatch.setattr("projectapp.reference.compute_reference", spy)
    ReferenceResolver(lambda: tmp_path, lambda: {date(2026, 10, 1): "祝"}).live("基盤", datetime(2026, 10, 14))
    assert seen == [{date(2026, 10, 1): "祝", date(2026, 10, 12): "休業"}]


def parent_with_references(*names: str) -> Project:
    return Project(
        "親",
        tasks=[Task(n, id=f"r{i}", kind=TaskKind.REFERENCE, ref_project=n) for i, n in enumerate(names)],
    )


def test_project_returns_the_referenced_project_and_caches_by_content(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    resolver = resolver_for(tmp_path)
    first, problem = resolver.project("基盤")
    assert problem == "" and first is not None and first.name == "基盤"
    assert resolver.project("基盤")[0] is first  # ファイルが同じ間は同じ物を返す
    changed = source()
    changed.tasks.append(Task("d", id="d"))
    save_project(changed, tmp_path)
    assert resolver.project("基盤")[0] is not first


def test_project_gives_a_reason_for_a_missing_or_broken_file(tmp_path: Path) -> None:
    resolver = resolver_for(tmp_path)
    assert resolver.project("無い")[0] is None
    (tmp_path / "壊れ.json").write_text("{", encoding="utf-8")
    value, problem = resolver.project("壊れ")
    assert value is None and "壊れ" in problem


def test_load_children_reads_each_referenced_project_once_and_skips_unreadable_ones(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    children = load_children(parent_with_references("基盤", "基盤", "無い"), resolver_for(tmp_path), {})
    assert list(children) == ["基盤"]  # 重複は 1 回、読めないものは外す
    assert children["基盤"].project.name == "基盤"


def test_load_children_gives_the_child_its_own_closed_event_holidays(tmp_path: Path) -> None:
    inner = source()
    inner.events = [Event(date(2026, 10, 12), date(2026, 10, 12), "休業", "gray", closed=True)]
    save_project(inner, tmp_path)
    children = load_children(parent_with_references("基盤"), resolver_for(tmp_path), {})
    assert date(2026, 10, 12) in children["基盤"].holidays


def test_load_children_skips_a_reference_to_the_project_itself(tmp_path: Path) -> None:
    save_project(source(), tmp_path)
    own = parent_with_references("基盤")
    own.name = "基盤"
    assert load_children(own, resolver_for(tmp_path), {}) == {}
