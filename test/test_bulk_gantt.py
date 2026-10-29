import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.filtering import TaskFilter
from projectapp.gantt import SELECT_CLICK_JS
from projectapp.models import Project, Section, Task, TaskKind
from test_gantt import mount_chart


def bulk_project() -> Project:
    kids = [Task("子0", id="c0"), Task("子1", id="c1")]
    summary = Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["c0", "c1"])
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        tasks=[Task("上", id="top")],
        sections=[Section("開発", [summary, *kids, Task("下", id="low")])],
    )


def rows(chart) -> list[str]:
    return chart.visible_task_ids()


async def test_visible_task_ids_follow_render_order_and_skip_collapsed_children(user: User) -> None:
    charts, _ = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    assert rows(chart) == ["top", "s", "c0", "c1", "low"]
    chart.toggle_summary("s")
    assert rows(chart) == ["top", "s", "low"]
    chart.toggle_summary("s")
    chart.set_filter(TaskFilter(query="子"))
    assert rows(chart) == ["s", "c0", "c1"]  # 子が一致するまとめも出す


async def test_ctrl_click_selects_and_marks_rows_without_re_rendering(user: User) -> None:
    charts, _ = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    before = chart.render_count if hasattr(chart, "render_count") else None
    chart.clicked_task("top", {"ctrl": True})
    assert chart.bulk.ids == {"top"}
    await user.should_see(marker="bulk-bar")
    assert user.find(marker="bulk-count").elements.pop().text == "1 件選択中"
    if before is not None:
        assert chart.render_count == before  # 描き直さない


async def test_plain_click_does_nothing_and_shift_click_selects_a_range(user: User) -> None:
    charts, _ = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    chart.clicked_task("top", {})
    assert chart.bulk.ids == set()
    chart.clicked_task("top", {"ctrl": True})
    chart.clicked_task("c1", {"shift": True})
    assert chart.bulk.ids == {"top", "s", "c0", "c1"}


async def test_the_bar_actions_pass_visible_selected_ids_in_render_order(user: User) -> None:
    charts, recorder = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    chart.clicked_task("low", {"ctrl": True})
    chart.clicked_task("top", {"ctrl": True})
    user.find(marker="bulk-edit").click()
    user.find(marker="bulk-delete").click()
    assert recorder.events == [("bulk_edit", (["top", "low"],)), ("bulk_delete", (["top", "low"],))]


async def test_rows_hidden_by_a_filter_are_not_targets_but_stay_selected(user: User) -> None:
    charts, recorder = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    chart.clicked_task("top", {"ctrl": True})
    chart.clicked_task("low", {"ctrl": True})
    chart.set_filter(TaskFilter(query="下"))
    user.find(marker="bulk-edit").click()
    assert recorder.events == [("bulk_edit", (["low"],))]
    assert chart.bulk.ids == {"top", "low"}
    assert user.find(marker="bulk-count").elements.pop().text == "1 件選択中"


async def test_clear_selection_hides_the_bar_and_set_project_prunes_gone_ids(user: User) -> None:
    charts, _ = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    chart.clicked_task("top", {"ctrl": True})
    chart.clicked_task("low", {"ctrl": True})
    project = chart.project
    project.tasks.clear()
    chart.set_project(project)
    assert chart.bulk.ids == {"low"}
    chart.clear_selection()
    assert not chart.has_selection()
    await user.should_not_see(marker="bulk-bar")


async def test_the_context_menu_offers_bulk_items_only_on_a_selected_row(user: User) -> None:
    charts, recorder = mount_chart(bulk_project())
    await user.open("/")
    chart = charts[0]
    chart.clicked_task("top", {"ctrl": True})
    chart.open_menu((), 0)
    assert chart.bulk_edit_item.visible and chart.bulk_delete_item.visible
    chart.open_menu((0,), 3)  # 選択に含まれない行
    assert not chart.bulk_edit_item.visible and not chart.bulk_delete_item.visible
    assert chart.bulk.ids == {"top"}  # 選択はそのまま
    chart.open_menu((), 0)
    user.find(marker="context-bulk-edit").click()
    assert recorder.events == [("bulk_edit", (["top"],))]


async def test_read_only_charts_ignore_selection(user: User) -> None:
    from projectapp.gantt import ViewOptions
    from test_gantt import mount_with

    mount_with(bulk_project(), ViewOptions(read_only=True))
    await user.open("/")
    await user.should_not_see(marker="bulk-bar")


def test_the_click_script_filters_modifiers_and_excluded_targets(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node がないので動きを確かめない")
    sim = tmp_path / "sim.js"
    sim.write_text(
        "const fn = eval(process.argv[2]);\n"
        "const run = (mods, excluded) => { const out = []; let prevented = false;\n"
        "  const e = { shiftKey: !!mods.shift, ctrlKey: !!mods.ctrl, metaKey: !!mods.meta,\n"
        "    target: { closest: () => (excluded ? {} : null) }, preventDefault: () => { prevented = true; } };\n"
        "  global.emit = (v) => out.push(v); fn(e); return { out, prevented }; };\n"
        "console.log(JSON.stringify({ plain: run({}, false), ctrl: run({ ctrl: true }, false),\n"
        "  meta: run({ meta: true }, false), shift: run({ shift: true }, false), button: run({ ctrl: true }, true) }));\n",
        encoding="utf-8",
    )
    result = subprocess.run([node, str(sim), SELECT_CLICK_JS], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["plain"]["out"] == []  # 修飾なしは何も送らない
    assert out["ctrl"]["out"] == [{"shift": False, "ctrl": True}]
    assert out["meta"]["out"] == [{"shift": False, "ctrl": True}]  # Cmd も ctrl 扱い
    assert out["shift"]["out"] == [{"shift": True, "ctrl": False}]
    assert out["button"]["out"] == []  # ボタン・リンク・入力欄の上は選択にしない
