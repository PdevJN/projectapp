from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.decompose import Part
from projectapp.decompose_dialog import open_decompose_dialog

from projectapp.filtering import TaskFilter
from projectapp.gantt import SUMMARY_BAND_HEIGHT_PX
from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from test_gantt import mount_chart


def summary_project() -> Project:
    def kid(name: str, day: int, status: Status = Status.NOT_STARTED) -> Task:
        return Task(
            name, id=name, planned_start=datetime(2026, 10, day, 9), planned_end=datetime(2026, 10, day + 1, 17),
            status=status, effort_hours=4.0, assignees=[Assignee("田中")],
        )

    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        members=[Member("田中")],
        sections=[
            Section("開発", [
                Task("実装", id="m", kind=TaskKind.SUMMARY, children=["a", "b"]),
                kid("a", 6, Status.RUNNING),
                kid("b", 9),
                Task("後続", id="z", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 9)),
            ])
        ],
    )


async def test_a_summary_draws_a_thin_band_over_its_children(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    band = user.find(marker="summary-band-0-0").elements.pop()
    assert band._style["height"] == f"{SUMMARY_BAND_HEIGHT_PX}px"
    await user.should_not_see(marker="bar-0-0")  # 通常の棒は出さない
    await user.should_see(marker="bar-0-1")


async def test_a_summary_name_is_bold_and_has_no_assignee_chip(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    name = user.find(marker="task-name-0-0").elements.pop()
    assert name._style["font-weight"] == "700"
    await user.should_not_see(marker="task-assignee-0-0")
    await user.should_see(marker="task-assignee-0-1")


async def test_children_are_indented_one_level_more_than_other_tasks(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    child_cell = user.find(marker="task-0-1").elements.pop()
    other_cell = user.find(marker="task-0-3").elements.pop()
    assert child_cell._style["padding-left"] != other_cell._style["padding-left"]


async def test_the_arrow_collapses_and_expands_the_children(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    await user.should_not_see(marker="task-0-1")
    await user.should_not_see(marker="task-0-2")
    await user.should_see(marker="task-0-3")
    assert charts[0].collapsed_summaries == {"m"}
    await user.should_see(marker="summary-count-0-0")
    user.find(marker="summary-toggle-0-0").click()
    await user.should_see(marker="task-0-1")
    assert charts[0].collapsed_summaries == set()


async def test_clicking_the_summary_name_toggles_it_too(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="task-name-0-0").click()
    assert charts[0].collapsed_summaries == {"m"}


async def test_a_collapsed_summary_shows_the_child_count(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    await user.should_not_see(marker="summary-count-0-0")
    user.find(marker="summary-toggle-0-0").click()
    assert user.find(marker="summary-count-0-0").elements.pop().text == "2件"


async def test_the_section_toggle_does_not_reopen_the_children_of_a_collapsed_summary(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    user.find(marker="section-toggle-0").click()
    user.find(marker="section-toggle-0").click()
    await user.should_not_see(marker="task-0-1")
    await user.should_see(marker="task-0-0")


async def test_filtering_ignores_the_summary_collapse(user: User) -> None:
    charts, _ = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    charts[0].set_filter(TaskFilter(query="b"))
    await user.should_see(marker="task-0-2")  # 子 b
    await user.should_see(marker="task-0-0")  # b を子に持つまとめ


async def test_a_summary_row_is_never_drawn_red_even_when_its_end_has_passed(user: User) -> None:
    mount_chart(summary_project(), now=datetime(2027, 1, 1))
    await user.open("/")
    row = user.find(marker="row-0-0").elements.pop()
    assert "239, 83, 80" not in row._style.get("background", "")
    child_row = user.find(marker="row-0-2").elements.pop()
    assert "239, 83, 80" in child_row._style.get("background", "")  # 子は赤くなる(テスト自体が効いている確認)


async def test_links_from_a_hidden_child_disappear_while_the_summary_is_collapsed(user: User) -> None:
    project = summary_project()
    project.sections[0].tasks[3].predecessors = ["a", "m"]
    mount_chart(project)
    await user.open("/")
    html = user.find(marker="links").elements.pop().content
    assert 'data-link="a-z"' in html and 'data-link="m-z"' in html
    user.find(marker="summary-toggle-0-0").click()
    html = user.find(marker="links").elements.pop().content
    assert 'data-link="a-z"' not in html and 'data-link="m-z"' in html


def mount_decompose(task: Task, calls: list[tuple[list[Part], bool, bool]], reason: str | None = None, fail: str | None = None) -> None:
    @ui.page("/")
    def index() -> None:
        def on_apply(parts: list[Part], chain: bool, new_section: bool) -> None:
            if fail:
                raise ValueError(fail)
            calls.append((parts, chain, new_section))

        ui.button("開く", on_click=lambda: open_decompose_dialog(task, reason, on_apply))


async def test_the_dialog_starts_with_two_even_rows(user: User) -> None:
    mount_decompose(Task("実装", effort_hours=5.0), [])
    await user.open("/")
    user.find("開く").click()
    assert user.find(marker="decompose-name-0").elements.pop().value == "実装 1"
    assert user.find(marker="decompose-effort-0").elements.pop().value == 2.5
    assert user.find(marker="decompose-effort-1").elements.pop().value == 2.5


async def test_apply_passes_the_rows_and_the_options(user: User) -> None:
    calls: list[tuple[list[Part], bool, bool]] = []
    mount_decompose(Task("実装", effort_hours=4.0), calls)
    await user.open("/")
    user.find("開く").click()
    user.find(marker="decompose-apply").click()
    assert calls == [([Part("実装 1", 2.0), Part("実装 2", 2.0)], True, False)]


async def test_edited_rows_and_options_are_passed(user: User) -> None:
    calls: list[tuple[list[Part], bool, bool]] = []
    mount_decompose(Task("実装", effort_hours=4.0), calls)
    await user.open("/")
    user.find("開く").click()
    user.find(marker="decompose-name-1").elements.pop().set_value("後半")
    user.find(marker="decompose-effort-0").elements.pop().set_value(3.0)
    user.find(marker="decompose-chain").elements.pop().set_value(False)
    user.find(marker="decompose-section").elements.pop().set_value(True)
    user.find(marker="decompose-apply").click()
    assert calls == [([Part("実装 1", 3.0), Part("後半", 2.0)], False, True)]


async def test_rows_can_be_added_and_removed_but_not_below_two(user: User) -> None:
    mount_decompose(Task("実装", effort_hours=3.0), [])
    await user.open("/")
    user.find("開く").click()
    await user.should_not_see(marker="decompose-remove-1")  # 2 行のときは削除を出さない
    user.find(marker="decompose-add").click()
    await user.should_see(marker="decompose-name-2")
    user.find(marker="decompose-remove-2").click()
    await user.should_not_see(marker="decompose-name-2")
    await user.should_not_see(marker="decompose-remove-1")


async def test_the_total_warns_when_it_differs_from_the_original(user: User) -> None:
    mount_decompose(Task("実装", effort_hours=4.0), [])
    await user.open("/")
    user.find("開く").click()
    assert "一致" in user.find(marker="decompose-total").elements.pop().text
    user.find(marker="decompose-effort-0").elements.pop().set_value(9.0)
    assert "違います" in user.find(marker="decompose-total").elements.pop().text


async def test_the_section_option_is_disabled_with_the_reason(user: User) -> None:
    calls: list[tuple[list[Part], bool, bool]] = []
    mount_decompose(Task("実装"), calls, reason="セクションは 3 階層までです")
    await user.open("/")
    user.find("開く").click()
    box = user.find(marker="decompose-section").elements.pop()
    assert not box.enabled
    await user.should_see("セクションは 3 階層までです")
    user.find(marker="decompose-apply").click()
    assert calls[0][2] is False


async def test_an_error_from_the_callback_keeps_the_dialog_open(user: User) -> None:
    mount_decompose(Task("実装"), [], fail="実績のあるタスクは分解できません")
    await user.open("/")
    user.find("開く").click()
    user.find(marker="decompose-apply").click()
    await user.should_see("実績のあるタスクは分解できません")
    await user.should_see(marker="decompose-apply")


async def test_the_arrow_stops_the_click_from_reaching_the_row_editor(user: User) -> None:
    mount_chart(summary_project())
    await user.open("/")
    arrow = user.find(marker="summary-toggle-0-0").elements.pop()
    clicks = [l for l in arrow._event_listeners.values() if l.type == "click"]
    assert clicks and all("stopPropagation" in (l.js_handler or "") for l in clicks)


async def test_a_summary_of_done_children_is_struck_through(user: User) -> None:
    project = summary_project()
    for task in project.sections[0].tasks[1:3]:
        task.status = Status.DONE
    mount_chart(project)
    await user.open("/")
    assert user.find(marker="task-name-0-0").elements.pop()._style.get("text-decoration") == "line-through"


async def test_the_section_count_does_not_count_summaries(user: User) -> None:
    mount_chart(summary_project())  # まとめ 1 + 子 2 + 後続 1
    await user.open("/")
    assert user.find(marker="section-count-0").elements.pop().text == "(3)"


async def test_a_link_from_a_hidden_child_is_redrawn_from_the_collapsed_summary(user: User) -> None:
    project = summary_project()
    project.sections[0].tasks[3].predecessors = ["a"]  # 子 a → 後続 z
    mount_chart(project)
    await user.open("/")
    assert 'data-link="a-z"' in user.find(marker="links").elements.pop().content
    user.find(marker="summary-toggle-0-0").click()
    html = user.find(marker="links").elements.pop().content
    assert 'data-link="a-z"' not in html and 'data-link="m-z"' in html
    user.find(marker="summary-toggle-0-0").click()
    assert 'data-link="a-z"' in user.find(marker="links").elements.pop().content


async def test_dropping_below_a_collapsed_summary_lands_after_its_hidden_children(user: User) -> None:
    charts, recorder = mount_chart(summary_project())
    await user.open("/")
    user.find(marker="summary-toggle-0-0").click()
    charts[0].handle_move({"src": ["top", 0], "dst": ["0", 1], "copy": False})  # まとめの直後 = 隠れた子の手前
    assert recorder.events == [("move_task", (((), 0), ((0,), 3), False))]
    recorder.events.clear()
    user.find(marker="summary-toggle-0-0").click()  # 開いていれば、そのまま
    charts[0].handle_move({"src": ["top", 0], "dst": ["0", 1], "copy": False})
    assert recorder.events == [("move_task", (((), 0), ((0,), 1), False))]


def mount_settled(task: Task, calls: list[tuple[list[Part], bool, bool]]) -> None:
    from projectapp.decompose import Settled

    @ui.page("/")
    def page() -> None:
        def apply(parts: list[Part], chain: bool, new_section: bool) -> None:
            calls.append((parts, chain, new_section))

        open_decompose_dialog(task, None, apply, Settled(3.0, []))


async def test_the_settled_dialog_fixes_the_first_row_and_splits_the_rest(user: User) -> None:
    calls: list[tuple[list[Part], bool, bool]] = []
    mount_settled(Task("実装", effort_hours=10.0, weekly_crew=[[Assignee("田中")]]), calls)
    await user.open("/")
    await user.should_see(marker="decompose-settled-note")
    await user.should_see(marker="decompose-weekly-note")
    assert not user.find(marker="decompose-effort-0").elements.pop().enabled
    assert [user.find(marker=f"decompose-effort-{n}").elements.pop().value for n in range(3)] == [3.0, 3.5, 3.5]
    await user.should_not_see(marker="decompose-remove-1")  # 3 行より減らせない
    user.find(marker="decompose-apply").click()
    assert [(p.name, p.effort_hours) for p in calls[0][0]] == [("実装 1", 3.0), ("実装 2", 3.5), ("実装 3", 3.5)]
