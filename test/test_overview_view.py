from datetime import date

from nicegui.testing import User

from projectapp.models import Project, Section, Task, TaskKind
from test_gantt import mount_chart


def project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        sections=[
            Section(
                "開発",
                [
                    Task("通常", id="a", effort_hours=4.0),
                    Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["c"]),
                    Task("子", id="c", effort_hours=2.0),
                ],
            )
        ],
    )


async def test_section_menu_opens_the_overview_of_that_section(user: User) -> None:
    charts, recorder = mount_chart(project())
    await user.open("/")
    charts[0].open_section_menu((0,))
    user.find(marker="section-context-overview").click()
    assert recorder.events == [("overview_section", ((0,),))]


async def test_summary_row_menu_opens_the_overview_of_that_summary(user: User) -> None:
    charts, recorder = mount_chart(project())
    await user.open("/")
    charts[0].open_menu((0,), 1)
    user.find(marker="context-overview").click()
    assert recorder.events == [("overview_summary", ("s",))]


async def test_overview_is_not_offered_on_a_plain_task(user: User) -> None:
    charts, _ = mount_chart(project())
    await user.open("/")
    charts[0].open_menu((0,), 0)
    assert charts[0].overview_item is not None
    assert not charts[0].overview_item.visible


async def test_reveal_task_unfolds_the_section_and_the_summary(user: User) -> None:
    charts, _ = mount_chart(project())
    await user.open("/")
    chart = charts[0]
    chart.collapsed.add((0,))
    chart.collapsed_summaries.add("s")
    chart.reveal_task("c")
    assert (0,) not in chart.collapsed
    assert "s" not in chart.collapsed_summaries
