import asyncio
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.models import Project, Section, Task, TaskKind
from projectapp.overview import build_overview
from projectapp.overview_dialog import open_overview_dialog
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


def mount_dialog(jumps: list[str], pdfs: list) -> None:
    root = build_overview(project(), {}, datetime(2026, 10, 1), section_path=(0,))

    @ui.page("/")
    def index() -> None:
        async def on_pdf(layout) -> None:
            pdfs.append(layout)

        ui.button(
            "開く", on_click=lambda: open_overview_dialog(root, jumps.append, on_pdf)
        ).mark("open")


async def test_dialog_shows_nodes_and_hides_items_with_the_checkboxes(
    user: User,
) -> None:
    mount_dialog([], [])
    await user.open("/")
    user.find(marker="open").click()
    await user.should_see("開発")
    await user.should_see("進捗 ")
    user.find(marker="overview-progress").click()
    await user.should_not_see("進捗 ")


async def test_clicking_a_node_jumps_to_its_task_and_closes(user: User) -> None:
    jumps: list[str] = []
    mount_dialog(jumps, [])
    await user.open("/")
    user.find(marker="open").click()
    user.find(marker="overview-node-a").click()
    assert jumps == ["a"]


async def test_pdf_button_hands_the_current_layout_to_the_callback(user: User) -> None:
    pdfs: list = []
    mount_dialog([], pdfs)
    await user.open("/")
    user.find(marker="open").click()
    user.find(marker="overview-effort").click()  # 工数を隠した状態の座標が渡る
    user.find(marker="overview-pdf").click()
    for _ in range(50):  # 非同期のボタンの処理が終わるのを待つ
        if pdfs:
            break
        await asyncio.sleep(0.02)
    assert len(pdfs) == 1
    assert all("工数" not in line for p in pdfs[0].placed for line in p.lines)
