from datetime import datetime, timedelta
from pathlib import Path

from nicegui.testing import User

from projectapp import clock
from projectapp.gantt import FORECAST_CSS, forecast_text
from projectapp.forecast import Forecast
from projectapp.models import Assignee, Status, Task
from test_delay_response import opened


def test_forecast_text_shows_the_signed_days() -> None:
    end = datetime(2026, 11, 16, 18)
    assert (
        forecast_text(Forecast(end, end - timedelta(days=3))) == "見込み 11/16(+3 日)"
    )
    assert (
        forecast_text(Forecast(end, end + timedelta(days=2))) == "見込み 11/16(−2 日)"
    )


def test_forecast_colour_has_light_and_dark_values() -> None:
    assert "--forecast" in FORECAST_CSS and "body.body--dark" in FORECAST_CSS
    assert "dotted" in FORECAST_CSS


def late_task(**changes: object) -> Task:
    today = clock.now()
    task = Task(
        "late",
        id="tl",
        planned_start=today.replace(hour=9, minute=0, second=0, microsecond=0)
        - timedelta(days=6),
        effort_hours=20.0,
        assignees=[Assignee("田中")],
    )
    for key, value in changes.items():
        setattr(task, key, value)
    return task


async def put(user: User, tmp_path: Path, task: Task):
    view = await opened(user, tmp_path)
    view.project.tasks.clear()
    view.project.tasks.append(task)
    view.after_edit()
    return view


async def test_a_late_task_shows_the_forecast_line_and_label(
    user: User, tmp_path: Path
) -> None:
    await put(user, tmp_path, late_task())
    await user.should_see(marker="forecast-line-top-0")
    await user.should_see(marker="forecast-label-top-0")


async def test_no_forecast_for_a_task_that_is_not_late_and_has_no_progress(
    user: User, tmp_path: Path
) -> None:
    await put(user, tmp_path, late_task(effort_hours=20.0, planned_start=clock.now()))
    await user.should_not_see(marker="forecast-label-top-0")


async def test_no_forecast_when_done_or_alerts_off_or_trial_active(
    user: User, tmp_path: Path
) -> None:
    view = await put(user, tmp_path, late_task())
    await user.should_see(marker="forecast-label-top-0")
    view.try_crew("tl", ["鈴木"], clock.now().date())
    await user.should_not_see(marker="forecast-label-top-0")  # 試算中は試算を優先
    view.trials.clear()
    view.after_edit()
    view.project.tasks[0].status = Status.DONE
    view.after_edit()
    await user.should_not_see(marker="forecast-label-top-0")


async def test_forecast_is_computed_once_per_task_per_render(
    user: User, tmp_path: Path, monkeypatch
) -> None:
    import projectapp.gantt as gantt

    calls: list[str] = []
    real = gantt.forecast_end

    def counting(task, *args, **kwargs):
        calls.append(task.id)
        return real(task, *args, **kwargs)

    monkeypatch.setattr(gantt, "forecast_end", counting)
    await put(user, tmp_path, late_task())
    await user.should_see(marker="forecast-label-top-0")
    assert calls.count("tl") <= 2  # 行の描画と警告ホバーで使い回す(描画ごとに 1 回)
