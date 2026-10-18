from datetime import date, datetime

from nicegui.testing import User

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
