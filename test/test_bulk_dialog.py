from datetime import date

from nicegui import ui
from nicegui.testing import User

from projectapp.bulk_dialog import open_bulk_dialog
from projectapp.bulk_edit import BulkChanges, CategoryChange, EffortMode
from projectapp.models import Category, Member, Project, Task


def dialog_project() -> Project:
    return Project(
        "p",
        base_date=date(2026, 10, 5),
        tasks=[Task("a", id="a", effort_hours=8), Task("b", id="b")],
        members=[Member("田中", id="m1")],
        categories=[Category("開発", id="cat")],
    )


def mount(applied: list[BulkChanges]) -> Project:
    project = dialog_project()

    @ui.page("/")
    def index() -> None:
        open_bulk_dialog(project, ["a", "b"], {}, applied.append)

    return project


def button_disabled(user: User, marker: str) -> bool:
    return not user.find(marker=marker).elements.pop().enabled


async def test_the_dialog_starts_with_nothing_to_change_and_apply_disabled(
    user: User,
) -> None:
    mount([])
    await user.open("/")
    await user.should_see(marker="bulk-dialog")
    assert button_disabled(user, "bulk-apply")
    assert "対象 2 件" in user.find(marker="bulk-forecast").elements.pop().text


async def test_turning_on_the_category_section_enables_apply_and_passes_the_change(
    user: User,
) -> None:
    applied: list[BulkChanges] = []
    mount(applied)
    await user.open("/")
    user.find(marker="bulk-category-on").click()
    assert not button_disabled(user, "bulk-apply")
    user.find(marker="bulk-apply").click()
    assert applied == [
        BulkChanges(category=CategoryChange(None))
    ]  # 選択の既定は「未定」


async def test_effort_adjust_forecast_reports_skipped_tasks_without_changing_the_project(
    user: User,
) -> None:
    applied: list[BulkChanges] = []
    project = mount(applied)
    await user.open("/")
    user.find(marker="bulk-effort-on").click()
    user.find(marker="bulk-effort-mode").elements.pop().set_value(
        EffortMode.ADJUST.value
    )
    user.find(marker="bulk-effort-value").type("2")
    forecast = user.find(marker="bulk-forecast").elements.pop().text
    assert "変更 1 件" in forecast and "工数なし" in forecast
    assert [t.effort_hours for t in project.all_tasks()] == [8, 0]  # ドライラン


async def test_invalid_input_shows_an_error_and_disables_apply(user: User) -> None:
    mount([])
    await user.open("/")
    user.find(marker="bulk-effort-on").click()
    user.find(marker="bulk-effort-value").type("-3")
    assert button_disabled(user, "bulk-apply")
    assert "0 以上" in user.find(marker="bulk-error").elements.pop().text


async def test_crew_add_needs_a_member_then_passes_the_change(user: User) -> None:
    from projectapp.bulk_edit import CrewChange, CrewMode
    from projectapp.models import Assignee

    applied: list[BulkChanges] = []
    mount(applied)
    await user.open("/")
    user.find(marker="bulk-crew-on").click()
    assert button_disabled(user, "bulk-apply")
    assert "メンバー" in user.find(marker="bulk-error").elements.pop().text
    user.find(marker="bulk-crew-member").elements.pop().set_value("田中")
    assert not button_disabled(user, "bulk-apply")
    user.find(marker="bulk-apply").click()
    assert applied == [
        BulkChanges(crew=CrewChange(CrewMode.ADD, (Assignee("田中", 1.0),)))
    ]


async def test_end_date_must_be_readable_and_shift_is_signed(user: User) -> None:
    from projectapp.bulk_edit import EndChange, EndMode

    applied: list[BulkChanges] = []
    mount(applied)
    await user.open("/")
    user.find(marker="bulk-end-on").click()
    assert button_disabled(user, "bulk-apply")
    assert "YYYY-MM-DD" in user.find(marker="bulk-error").elements.pop().text
    user.find(marker="bulk-end-mode").elements.pop().set_value(EndMode.SHIFT.value)
    user.find(marker="bulk-apply").click()
    assert applied == [BulkChanges(end=EndChange(EndMode.SHIFT, days=1))]
