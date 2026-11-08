from datetime import date
from pathlib import Path

from nicegui.testing import User

from projectapp.delay_response import DELAY_RESPONSE_CSS
from projectapp.models import Assignee
from test_delay_response import opened


def test_the_band_css_uses_a_thick_dotted_border_and_its_own_colours() -> None:
    assert "3px dotted" in DELAY_RESPONSE_CSS
    assert "--delay-accent" in DELAY_RESPONSE_CSS
    assert "body.body--dark" in DELAY_RESPONSE_CSS  # ダークの値がある
    for banned in ("red", "#f44336", "#ffc107", "green"):
        assert banned not in DELAY_RESPONSE_CSS  # 遅れ・警告・取り戻せたの色は使わない


async def test_no_band_without_trials_and_a_band_with_them(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    await user.should_not_see(marker="delay-band")
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    await user.should_see(marker="delay-band")
    await user.should_see(marker="trial-ghost-top-0")
    await user.should_see(marker="trial-origin-top-0")
    await user.should_see(marker="trial-chip-top-0")
    await user.should_see(marker="trial-label-top-0")


async def test_the_band_shows_the_title_and_counts(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    await user.should_see("遅延対応")
    await user.should_see("試算中: 1 件の増員")


async def test_clear_button_removes_the_band(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    await user.should_see(marker="delay-band-clear")
    user.find(marker="delay-band-clear").click()
    await user.should_not_see(marker="delay-band")
    assert view.trials == {}


async def test_confirm_button_writes_weekly_crew(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    await user.should_see(marker="delay-band-confirm")
    user.find(marker="delay-band-confirm").click()
    await user.should_not_see(marker="delay-band")
    assert view.project.tasks[0].weekly_crew != []
    assert view.is_dirty()


async def test_context_menu_has_try_crew_and_drop(user: User, tmp_path: Path) -> None:
    await opened(user, tmp_path)
    await user.should_see(marker="context-try-crew")
    await user.should_see(marker="context-drop-trial")


async def test_week_chips_are_unchanged_when_there_are_no_trials(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.toggle_weeks((), 0)
    await user.should_see(marker="week-chip-top-0-0")
    await user.should_not_see(marker="delay-band")
    assert view.trial_results() == {}


async def test_the_drop_action_removes_the_trial(user: User, tmp_path: Path) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    view.drop_trial_at((), 0)
    assert view.trials == {}
    await user.should_not_see(marker="delay-band")


async def test_overlay_positions_follow_the_name_column_width(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    for marker in ("ghost", "origin", "chip", "label"):
        await user.should_see(marker=f"trial-{marker}-top-0")
        style = user.find(marker=f"trial-{marker}-top-0").elements.pop()._style
        assert "var(--name-w)" in style["left"], marker  # 棒と同じ基準


async def test_switching_project_clears_the_band_and_the_overlay(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    view.try_crew("ta", ["鈴木"], date(2099, 1, 12))
    await user.should_see(marker="delay-band")
    view.reset_history()  # プロジェクトの切り替え・名前をつけて保存の入口
    assert view.gantt.trial_results == {}
    await user.should_not_see(marker="delay-band")


async def test_a_week_that_adds_a_member_is_marked_as_an_increase(
    user: User, tmp_path: Path
) -> None:
    view = await opened(user, tmp_path)
    task = view.project.tasks[0]
    task.weekly_crew = [
        [Assignee("田中")],
        [Assignee("田中"), Assignee("鈴木")],
        [Assignee("田中"), Assignee("鈴木")],
    ]
    view.after_edit()
    await user.should_see(marker="week-chip-top-0-1")
    await user.should_see(marker="week-added-top-0-1")  # 鈴木が増えた週
    await user.should_not_see(marker="week-added-top-0-0")  # 第 1 週は最初の担当
    await user.should_not_see(marker="week-added-top-0-2")  # 人が増えていない週
    chip = user.find(marker="week-added-top-0-1").elements.pop()
    assert "week-added" in chip.classes  # 紫の実線の縁で示す


def left_px(style: dict[str, str]) -> float:
    return float(style["left"].split("+")[1].strip().removesuffix("px)"))


async def test_the_ghost_of_an_overdue_task_starts_today_not_at_the_task_start(
    user: User, tmp_path: Path
) -> None:
    from datetime import datetime

    from projectapp import clock
    from projectapp.models import Task

    view = await opened(user, tmp_path)
    today = clock.now()
    view.project.tasks.clear()
    view.project.tasks.append(
        Task(
            "late",
            id="tl",
            planned_start=datetime.combine(today.date(), today.time().min).replace(
                hour=9
            )
            - __import__("datetime").timedelta(days=6),
            effort_hours=20.0,
            assignees=[Assignee("田中")],
        )
    )
    view.after_edit()
    view.try_crew("tl", ["鈴木"], today.date())
    assert view.trial_results()["tl"].from_now
    await user.should_see(marker="trial-ghost-top-0")
    bar = user.find(marker="bar-top-0").elements.pop()._style
    ghost = user.find(marker="trial-ghost-top-0").elements.pop()._style
    assert left_px(ghost) > left_px(bar)  # 棒の開始ではなく、今日から


def test_the_trial_ghost_is_a_filled_band_in_front_of_the_bar() -> None:
    rule = DELAY_RESPONSE_CSS.split(".trial-ghost {")[1].split("}")[0]
    assert "color-mix" in rule and "--delay-accent" in rule  # 薄い紫の塗り
    assert "z-index" in rule  # 実績・進捗の印に隠れない
    assert "dashed" in rule  # 試算の点線の縁は残す
