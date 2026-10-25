"""名前欄・見出し・末尾の追加行のダブルクリックで、名前だけのタスクを作る入力行。"""

from datetime import date

from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import TaskFilter, ViewOptions
from projectapp.models import Project, Section, Task, TaskKind
from test_gantt import mount_chart, mount_with

INPUT = "quick-add-input"


async def double_click(user: User, marker: str) -> None:
    """ダブルクリックして、入力行が出るのを待つ。"""
    user.find(marker=marker).trigger("dblclick")
    await user.should_see(marker=INPUT)


def quick_project() -> Project:
    kids = [Task("子0", id="c0"), Task("子1", id="c1")]
    summary = Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["c0", "c1"])
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        sections=[Section("開発", [Task("設計", id="a"), Task("実装", id="b")]), Section("空", []), Section("束", [summary, *kids, Task("末", id="z")])],
        tasks=[Task("直下", id="t")],
    )


async def test_double_clicking_a_task_name_opens_the_input_right_below_it(user: User) -> None:
    mount_chart(quick_project())
    await user.open("/")
    await user.should_not_see(marker=INPUT)
    user.find(marker="task-0-0").trigger("dblclick")
    await user.should_see(marker=INPUT)


async def test_enter_creates_the_task_below_the_clicked_one_and_closes_the_input(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-0-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="新規")
    assert recorder.events == [("add_named_task", ((0,), 1, "新規"))]
    await user.should_not_see(marker=INPUT)


async def test_a_root_task_adds_below_it_in_the_root(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-top-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="新規")
    assert recorder.events == [("add_named_task", ((), 1, "新規"))]


async def test_a_summary_row_adds_behind_its_children(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-2-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="新規")
    assert recorder.events == [("add_named_task", ((2,), 3, "新規"))]


async def test_the_section_header_adds_at_the_end_of_its_tasks_even_when_empty(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "section-1")  # 空のセクション
    user.find(marker=INPUT).trigger("keydown.enter", args="最初")
    await user.should_not_see(marker=INPUT)
    await double_click(user, "section-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="末尾")
    assert recorder.events == [("add_named_task", ((1,), 0, "最初")), ("add_named_task", ((0,), 2, "末尾"))]


async def test_double_clicking_the_header_of_a_collapsed_section_opens_it_and_shows_the_input(user: User) -> None:
    charts, _ = mount_chart(quick_project())
    await user.open("/")
    charts[0].toggle_section((0,))
    user.find(marker="section-0").trigger("dblclick")
    assert (0,) not in charts[0].collapsed
    await user.should_see(marker=INPUT)


async def test_the_end_row_of_the_root_adds_at_the_end_of_the_root(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "top-end")
    user.find(marker=INPUT).trigger("keydown.enter", args="末")
    assert recorder.events == [("add_named_task", ((), 1, "末"))]


async def test_an_invalid_name_shows_the_error_and_keeps_the_input(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-0-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="   ")
    user.find(marker=INPUT).trigger("keydown.enter", args="あ" * 51)
    assert recorder.events == []
    await user.should_see(marker=INPUT)
    await user.should_see(marker="quick-add-error")


async def test_escape_and_blur_cancel_without_creating(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-0-0")
    user.find(marker=INPUT).trigger("keydown.escape")
    await user.should_not_see(marker=INPUT)
    await double_click(user, "task-0-0")
    user.find(marker=INPUT).trigger("blur")
    await user.should_not_see(marker=INPUT)
    assert recorder.events == []


async def test_only_one_input_is_open_at_a_time(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-0-0")
    user.find(marker="task-0-1").trigger("dblclick")
    await user.should_see(marker=INPUT)
    assert len(user.find(marker=INPUT).elements) == 1
    user.find(marker=INPUT).trigger("keydown.enter", args="新規")
    assert recorder.events == [("add_named_task", ((0,), 2, "新規"))]


async def test_an_active_filter_refuses_with_a_notice(user: User) -> None:
    charts, recorder = mount_chart(quick_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="設"))
    user.find(marker="task-0-0").trigger("dblclick")
    await user.should_see("絞り込みを解除してください")
    await user.should_not_see(marker=INPUT)
    assert recorder.events == []


async def test_the_read_only_chart_has_no_double_click(user: User) -> None:
    mount_with(quick_project(), ViewOptions(read_only=True))
    await user.open("/")
    for marker in ("task-0-0", "task-top-0", "section-0"):
        element = user.find(marker=marker).elements.pop()
        assert not any(listener.type == "dblclick" for listener in element._event_listeners.values())
    await user.should_not_see(marker="top-end")


# Shift + ダブルクリックは、タスクの代わりにセクション(親のセクションの子の末尾)の入力行を出す

def nested_project() -> Project:
    deep = Section("深", [Task("底", id="d")])
    mid = Section("中", [Task("中身", id="m")], sections=[deep])
    return Project("demo", base_date=date(2026, 10, 5), sections=[Section("上", [Task("上身", id="u")], sections=[mid])], tasks=[Task("直下", id="t")])


async def shift_double_click(user: User, marker: str) -> None:
    user.find(marker=marker).trigger("dblclick", args={"shift": True})  # args は {shift, ctrl}
    await user.should_see(marker=INPUT)


async def test_shift_double_click_on_a_section_header_adds_a_subsection_at_its_end(user: User) -> None:
    _, recorder = mount_chart(nested_project())
    await user.open("/")
    await shift_double_click(user, "section-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="新")
    assert recorder.events == [("add_named_section", ((0,), "新"))]
    await user.should_not_see(marker=INPUT)


async def test_shift_double_click_on_a_task_adds_a_subsection_to_its_section(user: User) -> None:
    _, recorder = mount_chart(nested_project())
    await user.open("/")
    await shift_double_click(user, "task-0.0-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="新")
    assert recorder.events == [("add_named_section", ((0, 0), "新"))]


async def test_shift_double_click_on_a_root_task_or_the_end_row_adds_a_top_level_section(user: User) -> None:
    _, recorder = mount_chart(nested_project())
    await user.open("/")
    await shift_double_click(user, "task-top-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="一")
    await user.should_not_see(marker=INPUT)
    await shift_double_click(user, "top-end")
    user.find(marker=INPUT).trigger("keydown.enter", args="二")
    assert recorder.events == [("add_named_section", ((), "一")), ("add_named_section", ((), "二"))]


async def test_shift_double_click_in_a_third_level_section_is_refused_with_a_notice(user: User) -> None:
    _, recorder = mount_chart(nested_project())
    await user.open("/")
    for marker in ("section-0.0.0", "task-0.0.0-0"):
        user.find(marker=marker).trigger("dblclick", args={"shift": True})
        await user.should_see("サブセクションは 3 階層までです")
    await user.should_not_see(marker=INPUT)
    assert recorder.events == []


async def test_a_section_input_rejects_invalid_names_and_cancels_with_escape(user: User) -> None:
    _, recorder = mount_chart(nested_project())
    await user.open("/")
    await shift_double_click(user, "section-0")
    user.find(marker=INPUT).trigger("keydown.enter", args="   ")
    await user.should_see(marker="quick-add-error")
    assert recorder.events == []
    user.find(marker=INPUT).trigger("keydown.escape")
    await user.should_not_see(marker=INPUT)
    assert recorder.events == []


async def test_the_section_input_and_the_task_input_are_never_open_together(user: User) -> None:
    _, recorder = mount_chart(nested_project())
    await user.open("/")
    await shift_double_click(user, "section-0")
    user.find(marker="task-top-0").trigger("dblclick")
    await user.should_see(marker=INPUT)
    assert len(user.find(marker=INPUT).elements) == 1
    user.find(marker=INPUT).trigger("keydown.enter", args="タスク")
    assert recorder.events == [("add_named_task", ((), 1, "タスク"))]


async def test_shift_double_click_with_an_active_filter_refuses_with_a_notice(user: User) -> None:
    charts, recorder = mount_chart(nested_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="上"))
    user.find(marker="section-0").trigger("dblclick", args={"shift": True})
    await user.should_see("絞り込みを解除してください")
    await user.should_not_see(marker=INPUT)


async def test_shift_double_click_on_a_collapsed_section_opens_it(user: User) -> None:
    charts, _ = mount_chart(nested_project())
    await user.open("/")
    charts[0].toggle_section((0,))
    await shift_double_click(user, "section-0")
    assert (0,) not in charts[0].collapsed


CTRL = {"ctrl": True}
SHIFT_CTRL = {"shift": True, "ctrl": True}


async def test_shift_ctrl_double_click_on_a_summary_adds_a_child_at_the_end_of_its_children(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    user.find(marker="task-2-0").trigger("dblclick", args=SHIFT_CTRL)
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="新")
    assert recorder.events == [("add_named_child", ((2,), 3, "新", "s"))]
    await user.should_not_see(marker=INPUT)


async def test_double_click_on_a_child_adds_a_sibling_child_right_below_it(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    await double_click(user, "task-2-1")  # Ctrl なし
    user.find(marker=INPUT).trigger("keydown.enter", args="新")
    assert recorder.events == [("add_named_child", ((2,), 2, "新", "s"))]


async def test_ctrl_double_click_on_a_plain_task_or_a_summary_adds_a_plain_task(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    user.find(marker="task-0-0").trigger("dblclick", args=CTRL)
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="一")
    user.find(marker="task-2-0").trigger("dblclick", args=CTRL)  # Ctrl だけでは、まとめの子にならない
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="二")
    assert recorder.events == [("add_named_task", ((0,), 1, "一")), ("add_named_task", ((2,), 3, "二"))]


async def test_shift_ctrl_double_click_on_a_child_adds_a_sibling_child(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    user.find(marker="task-2-1").trigger("dblclick", args=SHIFT_CTRL)
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="新")
    assert recorder.events == [("add_named_child", ((2,), 2, "新", "s"))]


async def test_shift_on_a_child_still_adds_a_section(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    user.find(marker="task-2-1").trigger("dblclick", args={"shift": True})
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="節")
    assert recorder.events == [("add_named_section", ((2,), "節"))]


async def test_shift_ctrl_on_a_plain_task_adds_a_section_like_shift(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    user.find(marker="task-0-0").trigger("dblclick", args=SHIFT_CTRL)
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="節")
    assert recorder.events == [("add_named_section", ((0,), "節"))]


async def test_shift_on_a_summary_still_adds_a_section(user: User) -> None:
    _, recorder = mount_chart(quick_project())
    await user.open("/")
    user.find(marker="task-2-0").trigger("dblclick", args={"shift": True})
    await user.should_see(marker=INPUT)
    user.find(marker=INPUT).trigger("keydown.enter", args="束2")
    assert recorder.events == [("add_named_section", ((2,), "束2"))]


async def test_adding_a_child_to_a_folded_summary_opens_it(user: User) -> None:
    charts, _ = mount_chart(quick_project())
    await user.open("/")
    charts[0].collapsed_summaries.add("s")
    charts[0].render.refresh()
    user.find(marker="task-2-0").trigger("dblclick", args=SHIFT_CTRL)
    await user.should_see(marker=INPUT)
    assert "s" not in charts[0].collapsed_summaries


async def test_the_child_input_is_refused_while_filtering(user: User) -> None:
    charts, recorder = mount_chart(quick_project())
    await user.open("/")
    charts[0].set_filter(TaskFilter(query="子"))
    charts[0].double_clicked_task((2,), 1, {})
    await user.should_see("絞り込みを解除してください")
    assert recorder.events == []
