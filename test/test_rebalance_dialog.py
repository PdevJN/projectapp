"""負荷の調整ダイアログの確認。"""

from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.dashboard import Period, PeriodKind
from projectapp.models import Assignee, Member, Project, Task, union_assignees
from projectapp.rebalance import Edit
from projectapp.rebalance_dialog import open_rebalance_dialog

NOW = datetime(2026, 10, 5, 8)
PERIOD = Period(date(2026, 10, 5), date(2026, 10, 11))


def make(task_id: str, owner: str = "田中", rate: float = 0.6) -> Task:
    return Task(
        task_id.upper(),
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=13,
        assignees=[Assignee(owner, rate)],
        id=task_id,
    )


def sample() -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=[make("a"), make("b"), make("c", "鈴木", 0.5)],
    )


def mount(project: Project, applied: list[list[Edit]]) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_rebalance_dialog(
                "田中", project, PERIOD, PeriodKind.WEEK, NOW, {}, applied.append
            ),
        ).mark("open")


async def open_dialog(user: User) -> None:
    await user.open("/")
    user.find("open").click()


def element(user: User, marker: str):  # noqa: ANN202
    return user.find(marker=marker).elements.pop()


async def test_the_dialog_lists_the_owners_tasks_and_the_current_load(
    user: User,
) -> None:
    mount(sample(), [])
    await open_dialog(user)
    assert element(user, "rebalance-title").text == "負荷の調整: 田中"
    await user.should_see(marker="rebalance-row-a")
    await user.should_see(marker="rebalance-row-b")
    await user.should_not_see(marker="rebalance-row-c")  # 他の人のタスク
    assert element(user, "rebalance-load-田中").text == (
        "田中: 平均 96% / 最大 120% / 割り当て超過 4 日"
    )
    assert not element(user, "rebalance-apply").enabled  # 変更がないうちは押せない


async def test_a_rate_change_shows_the_result_and_applies(user: User) -> None:
    applied: list[list[Edit]] = []
    mount(sample(), applied)
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("rate")
        element(user, "rebalance-rate-b").set_value(40)
    assert "割り当て超過 4 日 → 0 日" in element(user, "rebalance-load-田中").text
    assert "完了予定" in element(user, "rebalance-task-b").text
    assert element(user, "rebalance-apply").enabled
    user.find(marker="rebalance-apply").click()
    assert applied == [[Edit("b", "rate", rate=0.4)]]


async def test_a_move_lists_candidates_with_spare_hours_and_shows_both_loads(
    user: User,
) -> None:
    applied: list[list[Edit]] = []
    mount(sample(), applied)
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("move")
    options = element(user, "rebalance-target-b").options
    assert options["鈴木"].startswith("鈴木(余力 ")
    assert "田中" not in options  # 自分には移せない
    with user.client:
        element(user, "rebalance-target-b").set_value("鈴木")
    assert "→" in element(user, "rebalance-load-鈴木").text
    user.find(marker="rebalance-apply").click()
    (edits,) = applied
    assert [(e.task_id, e.kind, e.name) for e in edits] == [("b", "move", "鈴木")]


async def test_a_move_without_a_target_is_not_a_change(user: User) -> None:
    mount(sample(), [])
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("move")
    assert not element(user, "rebalance-apply").enabled


async def test_reset_puts_a_row_back_and_disables_apply(user: User) -> None:
    mount(sample(), [])
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("rate")
        element(user, "rebalance-rate-b").set_value(40)
    assert element(user, "rebalance-apply").enabled
    user.find(marker="rebalance-reset-b").click()
    assert element(user, "rebalance-mode-b").value == "none"
    assert not element(user, "rebalance-apply").enabled


async def test_an_out_of_range_rate_shows_an_error_and_cannot_be_applied(
    user: User,
) -> None:
    mount(sample(), [])
    await open_dialog(user)
    with user.client:
        element(user, "rebalance-mode-b").set_value("rate")
        element(user, "rebalance-rate-b").set_value(150)
    assert "割り当て率は" in element(user, "rebalance-error").text
    assert not element(user, "rebalance-apply").enabled
    with user.client:
        element(user, "rebalance-rate-b").set_value(0)
    assert "割り当て率は" in element(user, "rebalance-error").text


async def test_the_dialog_says_when_there_is_nothing_to_adjust(user: User) -> None:
    project = Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=[make("c", "鈴木", 0.5)],
    )
    mount(project, [])
    await open_dialog(user)
    await user.should_see(marker="rebalance-empty")


async def test_a_weekly_task_is_marked_as_applying_to_every_week(user: User) -> None:
    weekly = [
        [Assignee("田中", 1.0)],
        [Assignee("田中", 0.5), Assignee("鈴木", 1.0)],
    ]
    varying = Task(
        "W",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=40,
        weekly_crew=weekly,
        assignees=union_assignees(weekly),
        id="w",
    )
    project = Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=[varying],
    )
    mount(project, [])
    await open_dialog(user)
    note = element(user, "rebalance-note-w").text
    assert "全週に適用" in note and "50〜100%" in note and "上書き" in note
