import asyncio
from datetime import datetime, time

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.forms import (
    LevelRow,
    MemberRow,
    ParameterRow,
    build_actual_intervals,
    build_members,
    build_parameter_edit,
    build_section_name,
    build_task,
    build_urls,
    build_work_settings,
    compose_actual,
    compose_datetime,
    default_times,
    effective_ratio_text,
    exceeds_decimals,
    in_hours_range,
    needs_end_time,
    needs_start_time,
    open_file_dialog,
    open_name_dialog,
    open_section_dialog,
    open_settings_dialog,
    open_unsaved_dialog,
    parse_datetime,
    push_hint,
    suggest_status,
)
from projectapp.models import (
    Actual,
    ActualMode,
    Assignee,
    Level,
    Member,
    Parameter,
    Priority,
    Status,
    Task,
    TaskUrl,
    UrlTemplate,
)
from projectapp.urls import TemplateEdit
from projectapp.task_dialog import open_task_dialog


def make(existing: Task | None = None, **overrides: object) -> Task:
    values: dict[str, object] = {
        "name": "設計",
        "planned_start": "2026-10-05T09:00",
        "planned_end": "2026-10-07T18:00",
        "planned_end_manual": False,
        "deadline": "",
        "effort_hours": 8.0,
        "priority": Priority.HIGH,
        "status": Status.RUNNING,
        "color": "#112233",
        "assignees": [],
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]


def test_build_task_normalizes_input() -> None:
    task = make(name="  設計  ", assignees=[(" 佐藤 ", 100.0)])
    assert task.name == "設計"
    assert task.planned_start == datetime(2026, 10, 5, 9, 0)
    assert task.planned_end == datetime(2026, 10, 7, 18, 0)
    assert task.effort_hours == 8.0
    assert task.assignee_names == ["佐藤"]


def test_blank_assignee_and_dates_become_none() -> None:
    task = make(planned_start="", planned_end="", assignees=[("  ", None)], effort_hours=None)
    assert (task.planned_start, task.planned_end, task.assignees, task.effort_hours) == (None, None, [], 0.0)


@pytest.mark.parametrize("name", ["", "   ", "　"])
def test_blank_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="名前"):
        make(name=name)


def test_end_before_start_is_rejected_but_equal_is_allowed() -> None:
    with pytest.raises(ValueError, match="完了予定は開始予定以降"):
        make(effort_hours=0.0, planned_start="2026-10-07T09:00", planned_end="2026-10-05T09:00")
    same = make(effort_hours=0.0, planned_start="2026-10-05T09:00", planned_end="2026-10-05T09:00")
    assert same.name == "設計"


@pytest.mark.parametrize(
    "text", ["abc", "2026-13-01T00:00", "2026-10-05T09:00+09:00", "2026-10-05T09:00Z"]
)
def test_bad_or_timezone_aware_datetime_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="形式"):
        make(planned_start=text)


@pytest.mark.parametrize("text", ["0026-10-05T09:00", "1999-12-31T23:59", "2101-01-01T00:00", "2926-10-05T09:00"])
def test_year_outside_range_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="年"):
        make(planned_start=text, planned_end="")
    with pytest.raises(ValueError, match="年"):
        make(planned_start="", planned_end=text, effort_hours=0.0)


def test_year_boundaries_are_accepted() -> None:
    task = make(planned_start="2000-01-01T00:00", planned_end="2100-12-31T23:59")
    assert task.planned_start == datetime(2000, 1, 1)
    assert task.planned_end == datetime(2100, 12, 31, 23, 59)


def test_negative_effort_is_rejected() -> None:
    with pytest.raises(ValueError, match="工数"):
        make(effort_hours=-1.0)


def test_editing_keeps_fields_not_in_the_form() -> None:
    existing = Task("旧", predecessors=["x"])
    edited = make(existing)
    assert edited.predecessors == ["x"]
    assert existing.name == "旧"


def test_parse_datetime_accepts_date_only() -> None:
    assert parse_datetime("2026-10-05") == datetime(2026, 10, 5)


def test_build_section_name() -> None:
    assert build_section_name(" 開発 ") == "開発"
    with pytest.raises(ValueError, match="名前"):
        build_section_name("  ")


async def test_task_dialog_saves_a_valid_task(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert [t.name for t in saved] == ["設計"]
    assert saved[0].planned_start == datetime(2026, 10, 5, 9, 0)
    assert saved[0].planned_end == datetime(2026, 10, 7, 18, 0)


async def test_task_dialog_shows_error_and_does_not_save(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-save").click()
    await user.should_see("名前を入力してください")
    assert saved == []


async def test_task_dialog_prefills_when_editing(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        task = Task("既存", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 9))
        ui.button("open", on_click=lambda: open_task_dialog(task, lambda t: None))

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="task-name").elements.pop().value == "既存"
    assert user.find(marker="task-start-date").elements.pop().value == "2026-10-05"


async def test_task_dialog_color_shows_a_preview(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, lambda t: None))

    await user.open("/")
    user.find("open").click()
    color = user.find(marker="task-color").elements.pop()
    assert color.preview is True


async def test_task_dialog_status_select_uses_full_width(user: User) -> None:
    # 幅が内容に縮むと、浮いたラベルが「優.」のように省略される
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, lambda t: None))

    await user.open("/")
    user.find("open").click()
    select = user.find(marker="task-status").elements.pop()
    assert "w-full" in select.classes


def _selected_priorities(user: User) -> list[str]:
    chips = {p: user.find(marker=f"priority-{p.name}").elements.pop() for p in Priority}
    return [p.value for p, chip in chips.items() if "outline" not in chip.props]


async def test_task_dialog_priority_defaults_to_medium(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, lambda t: None))

    await user.open("/")
    user.find("open").click()
    assert _selected_priorities(user) == ["中"]


async def test_task_dialog_priority_prefills_when_editing(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        task = Task("既存", priority=Priority.LOW)
        ui.button("open", on_click=lambda: open_task_dialog(task, lambda t: None))

    await user.open("/")
    user.find("open").click()
    assert _selected_priorities(user) == ["低"]


async def test_task_dialog_priority_chip_click_selects_only_that_chip(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="priority-HIGH").click()
    assert _selected_priorities(user) == ["高"]
    user.find(marker="priority-LOW").click()
    assert _selected_priorities(user) == ["低"]
    user.find(marker="task-save").click()
    assert saved[0].priority == Priority.LOW


async def test_section_dialog(user: User) -> None:
    saved: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_section_dialog(saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="section-save").click()
    await user.should_see("名前を入力してください")
    user.find(marker="section-name").type("開発")
    user.find(marker="section-save").click()
    assert saved == ["開発"]


async def test_name_dialog_rejects_then_accepts_a_stripped_name(user: User) -> None:
    saved: list[str] = []
    seen: list[str] = []

    def validate(name: str) -> str | None:
        seen.append(name)
        return "使えない名前です" if name == "bad" else None

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_name_dialog(saved.append, validate))

    await user.open("/")
    user.find("open").click()
    user.find(marker="project-name").type("bad")
    user.find(marker="name-save").click()
    await user.should_see("使えない名前です")
    assert saved == []
    user.find(marker="project-name").clear().type("\u3000デモ ")
    user.find(marker="name-save").click()
    assert saved == ["デモ"]
    assert seen == ["bad", "デモ"]


async def test_file_dialog_lists_names_and_selects_one(user: User) -> None:
    chosen: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_file_dialog(["甲", "乙"], chosen.append))

    await user.open("/")
    user.find("open").click()
    await user.should_see(marker="file-0")
    await user.should_see("乙")
    user.find(marker="file-1").click()
    assert chosen == ["乙"]


async def test_file_dialog_shows_a_message_when_empty(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_file_dialog([], lambda name: None))

    await user.open("/")
    user.find("open").click()
    await user.should_see("プロジェクトファイルがありません")


@pytest.mark.parametrize("marker", ["unsaved-save", "unsaved-discard", "unsaved-cancel"])
async def test_unsaved_dialog_calls_the_matching_action(user: User, marker: str) -> None:
    calls: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_unsaved_dialog(
                lambda: calls.append("unsaved-save"),
                lambda: calls.append("unsaved-discard"),
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker=marker).click()
    assert calls == ([] if marker == "unsaved-cancel" else [marker])


@pytest.mark.parametrize(
    ("hours", "start"),
    [(6.5, "09:00"), (1.0, "09:00"), (8.0, "16:00"), (1.0, "23:00"), (6.5, "17:30"), (8.0, "9:00")],
)
def test_build_work_settings_accepts_valid_values(hours: float, start: str) -> None:
    assert build_work_settings(hours, start)[0] == hours


def test_build_work_settings_returns_hours_and_time() -> None:
    assert build_work_settings(6.5, " 9:05 ") == (6.5, time(9, 5))


@pytest.mark.parametrize(
    ("hours", "start"),
    [
        (None, "09:00"),
        (0.0, "09:00"),
        (-1.0, "09:00"),
        (8.01, "09:00"),
        (8.5, "09:00"),
        (24.0, "00:00"),
        (0.99, "09:00"),
        (float("nan"), "09:00"),
        (float("inf"), "09:00"),
        (6.5, ""),
        (6.5, "25:00"),
        (6.5, "abc"),
        (6.5, "09:00:30"),
        (6.5, "17:31"),
        (8.0, "16:01"),
        (1.0, "23:01"),
    ],
)
def test_build_work_settings_rejects_invalid_values(hours: float | None, start: str) -> None:
    with pytest.raises(ValueError):
        build_work_settings(hours, start)


async def test_settings_dialog_prefills_rejects_then_applies(user: User) -> None:
    applied: list[tuple[float, time, ActualMode]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: applied.append((h, s, m))
            ),
        )

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="settings-hours").elements.pop().value == 6.5
    assert user.find(marker="settings-start").elements.pop().value == "09:00"
    user.find(marker="settings-hours").clear().type("25")
    user.find(marker="settings-apply").click()
    await user.should_see("1以上8以下")
    assert applied == []
    user.find(marker="settings-hours").clear().type("8")
    user.find(marker="settings-start").clear().type("10:00")
    user.find(marker="settings-apply").click()
    assert applied == [(8.0, time(10, 0), ActualMode.SIMPLE)]


async def test_settings_dialog_time_picker_and_field_stay_in_sync(user: User) -> None:
    applied: list[tuple[float, time, ActualMode]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: applied.append((h, s, m))
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="open-time-picker").click()
    picker = user.find(marker="settings-time-picker").elements.pop()
    start = user.find(marker="settings-start").elements.pop()
    assert picker.value == "09:00"
    with user.client:
        picker.set_value("14:30")
    assert start.value == "14:30"
    user.find(marker="settings-start").clear().type("10:15")
    assert picker.value == "10:15"
    user.find(marker="settings-apply").click()
    assert applied == [(6.5, time(10, 15), ActualMode.SIMPLE)]


async def test_clock_icon_opens_a_picker_dialog_and_ok_closes_it(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s, m: None))

    await user.open("/")
    user.find("open").click()
    ok = user.find(marker="time-picker-ok").elements.pop()
    picker = ok.parent_slot.parent.parent_slot.parent  # ボタン → カード → ダイアログ
    assert isinstance(picker, ui.dialog)
    assert picker.value is False
    user.find(marker="open-time-picker").click()
    assert picker.value is True
    user.find(marker="time-picker-ok").click()
    assert picker.value is False


@pytest.mark.parametrize("hours", [6.25, 6.17, 1.01, 7.0, 6.5])
def test_build_work_settings_accepts_up_to_two_decimal_places(hours: float) -> None:
    assert build_work_settings(hours, "09:00")[0] == hours


@pytest.mark.parametrize("hours", [6.123, 6.005, 1.001, 6.123456789, 7.999999999999])
def test_build_work_settings_rejects_more_than_two_decimal_places(hours: float) -> None:
    with pytest.raises(ValueError, match="小数点以下2桁"):
        build_work_settings(hours, "09:00")


@pytest.mark.parametrize(("hours", "expected"), [(6.25, False), (6.17, False), (7.0, False), (6.123, True), (6.005, True), (1.001, True)])
def test_exceeds_decimals(hours: float, expected: bool) -> None:
    assert exceeds_decimals(hours) is expected


async def test_settings_dialog_hours_field_warns_instead_of_rounding(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s, m: None))

    await user.open("/")
    user.find("open").click()
    hours = user.find(marker="settings-hours").elements.pop()
    assert isinstance(hours, ui.number)
    assert hours.precision is None  # 丸めない
    with user.client:
        hours.set_value(6.123)
        assert hours.validate() is False
        assert hours.error == "小数点以下2桁までで入力してください"
        assert hours.value == 6.123
        hours.set_value(6.25)
        assert hours.validate() is True
        assert hours.error is None


@pytest.mark.parametrize(("hours", "ok"), [(1.0, True), (8.0, True), (0.99, False), (8.01, False), (0.0, False), (-1.0, False), (24.0, False)])
def test_in_hours_range(hours: float, ok: bool) -> None:
    assert in_hours_range(hours) is ok


async def test_settings_dialog_hours_field_warns_when_out_of_range(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s, m: None))

    await user.open("/")
    user.find("open").click()
    hours = user.find(marker="settings-hours").elements.pop()
    assert isinstance(hours, ui.number)
    assert hours.props["min"] == 1 and hours.props["max"] == 8
    with user.client:
        for bad in (9.0, 0.5):
            hours.set_value(bad)
            assert hours.validate() is False
            assert hours.error == "稼働可能時間は1以上8以下で入力してください"
        for good in (1.0, 8.0):
            hours.set_value(good)
            assert hours.validate() is True


def test_default_times_adds_the_standard_day_and_lunch() -> None:
    assert default_times(time(9, 0)) == (time(9, 0), time(18, 0))
    assert default_times(time(8, 30)) == (time(8, 30), time(17, 30))


def test_default_times_caps_the_end_at_2359() -> None:
    # 暫定: 始業が15:00以降だと始業+9hが24時以上になり、表せない(保留事項)
    assert default_times(time(14, 59)) == (time(14, 59), time(23, 59))
    assert default_times(time(15, 0)) == (time(15, 0), time(23, 59))
    assert default_times(time(17, 0)) == (time(17, 0), time(23, 59))


def test_compose_datetime_joins_day_and_clock() -> None:
    assert compose_datetime("2026-10-05", "09:00") == "2026-10-05T09:00"
    assert compose_datetime(" 2026-10-05 ", " 09:00 ") == "2026-10-05T09:00"


def test_compose_datetime_zero_pads_the_day() -> None:
    assert compose_datetime("2026-10-5", "09:00") == "2026-10-05T09:00"
    assert compose_datetime("2026-1-05", "09:00") == "2026-01-05T09:00"


def test_compose_datetime_keeps_an_unparsable_day_for_build_task_to_report() -> None:
    assert compose_datetime("abc", "09:00") == "abcT09:00"


def test_compose_datetime_ignores_the_clock_when_the_day_is_empty() -> None:
    assert compose_datetime("", "09:00") == ""
    assert compose_datetime("  ", "") == ""
    assert compose_datetime("", "xx") == ""


@pytest.mark.parametrize("clock", ["", "25:00", "9am", "09:60", "09"])
def test_compose_datetime_rejects_a_bad_clock_when_the_day_is_given(clock: str) -> None:
    with pytest.raises(ValueError, match="時刻の形式"):
        compose_datetime("2026-10-05", clock)


def test_needs_start_time_is_false_for_the_work_start_or_empty() -> None:
    nine = time(9, 0)
    assert needs_start_time(None, nine) is False
    assert needs_start_time(datetime(2026, 10, 5, 9, 0), nine) is False


def test_needs_start_time_is_true_for_another_time() -> None:
    assert needs_start_time(datetime(2026, 10, 5, 9, 30), time(9, 0)) is True


def test_needs_start_time_follows_the_work_start() -> None:
    moment = datetime(2026, 10, 5, 8, 30)
    assert needs_start_time(moment, time(8, 30)) is False
    assert needs_start_time(moment, time(9, 0)) is True


def test_needs_end_time_is_false_for_the_default_end_or_empty() -> None:
    nine = time(9, 0)
    assert needs_end_time(None, nine) is False
    assert needs_end_time(datetime(2026, 10, 7, 18, 0), nine) is False


def test_needs_end_time_is_true_for_another_time() -> None:
    assert needs_end_time(datetime(2026, 10, 7, 15, 30), time(9, 0)) is True


def test_needs_end_time_compares_in_minutes() -> None:
    # 秒を持つ終了(自動算出)でも、同じ分なら補う時刻と同じとみなす
    assert needs_end_time(datetime(2026, 10, 7, 18, 0, 30), time(9, 0)) is False


def test_needs_end_time_follows_the_work_start() -> None:
    moment = datetime(2026, 10, 7, 17, 30)
    assert needs_end_time(moment, time(8, 30)) is False
    assert needs_end_time(moment, time(9, 0)) is True


@pytest.mark.parametrize("hours", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_effort_is_rejected(hours: float) -> None:
    with pytest.raises(ValueError, match="工数"):
        make(effort_hours=hours)


@pytest.mark.parametrize("color", ["#abc", "#AABBCC", "#aabbccdd"])
def test_hex_colors_are_accepted(color: str) -> None:
    assert make(color=color).color == color


@pytest.mark.parametrize(
    "color", ["", "red", "#12", "#12345", "#gggggg", "red; background:url(x)", "#fff;x"]
)
def test_non_hex_colors_are_rejected(color: str) -> None:
    with pytest.raises(ValueError, match="色"):
        make(color=color)


def test_deadline_is_parsed_and_may_precede_the_start() -> None:
    task = make(deadline="2026-10-01T18:00")
    assert task.deadline == datetime(2026, 10, 1, 18, 0)  # 開始予定(10/5)より前でもよい


def test_blank_deadline_clears_it() -> None:
    existing = Task("旧", deadline=datetime(2026, 10, 9, 18))
    assert make(existing, deadline="").deadline is None


@pytest.mark.parametrize("deadline", ["1999-12-31T18:00", "2101-01-01T00:00"])
def test_deadline_year_is_limited(deadline: str) -> None:
    with pytest.raises(ValueError, match="年は"):
        make(deadline=deadline)


@pytest.mark.parametrize("bad", ["abc", "2026-10-05T18:00+09:00"])
def test_deadline_rejects_a_bad_format_and_a_timezone(bad: str) -> None:
    with pytest.raises(ValueError, match="日時"):
        make(deadline=bad)


def test_planned_end_before_the_start_is_rejected_without_effort() -> None:
    with pytest.raises(ValueError, match="完了予定は開始予定以降"):
        make(effort_hours=0.0, planned_end="2026-10-04T09:00")


def test_planned_end_before_the_start_is_rejected_when_manual() -> None:
    with pytest.raises(ValueError, match="完了予定は開始予定以降"):
        make(effort_hours=8.0, planned_end_manual=True, planned_end="2026-10-04T09:00")


def test_a_hidden_planned_end_is_not_validated() -> None:
    task = make(effort_hours=8.0, planned_end_manual=False, planned_end="2026-10-04T09:00")
    assert task.planned_end == datetime(2026, 10, 4, 9)  # 工数あり・手で指定なしなので無視される値
    assert task.planned_end_manual is False


def test_planned_end_manual_is_saved_only_with_effort() -> None:
    assert make(effort_hours=8.0, planned_end_manual=True).planned_end_manual is True
    assert make(effort_hours=0.0, planned_end_manual=True).planned_end_manual is False
    assert make(effort_hours=None, planned_end_manual=True).planned_end_manual is False


def test_planned_end_year_is_limited() -> None:
    with pytest.raises(ValueError, match="年は"):
        make(planned_end="2101-01-01T00:00", effort_hours=0.0)


def test_build_task_requires_the_deadline_text() -> None:
    with pytest.raises(TypeError):
        build_task(  # type: ignore[call-arg]
            None,
            name="a",
            planned_start="",
            planned_end="",
            effort_hours=0.0,
            priority=Priority.HIGH,
            status=Status.RUNNING,
            color="#112233",
        )


def test_a_hidden_planned_end_with_a_bad_format_does_not_block_saving() -> None:
    existing = Task("旧", planned_end=datetime(2026, 10, 9, 18), effort_hours=8.0)
    task = make(existing, effort_hours=8.0, planned_end_manual=False, planned_end="abc")
    assert task.planned_end == datetime(2026, 10, 9, 18)  # 使われない値は、前の値を保つ


def test_a_hidden_planned_end_outside_the_year_range_does_not_block_saving() -> None:
    task = make(effort_hours=8.0, planned_end_manual=False, planned_end="9999-01-01T00:00")
    assert task.planned_end is None


def test_a_used_planned_end_with_a_bad_format_is_still_rejected() -> None:
    with pytest.raises(ValueError, match="日時"):
        make(effort_hours=0.0, planned_end="abc")
    with pytest.raises(ValueError, match="日時"):
        make(effort_hours=8.0, planned_end_manual=True, planned_end="abc")


def rows(*pairs: tuple[str | None, str, float | None]) -> list[MemberRow]:
    return [MemberRow(o, n, r) for o, n, r in pairs]


def no_tasks(_name: str) -> int:
    return 0


def test_build_members_converts_percent_to_ratio_and_trims_names() -> None:
    members, renames = build_members(rows((None, " 田中 ", 120.0)), [], no_tasks)
    assert members == [Member("田中", 1.2)]
    assert renames == {}


def test_build_members_rejects_a_blank_name() -> None:
    with pytest.raises(ValueError, match="名前"):
        build_members(rows((None, "  ", 100.0)), [], no_tasks)


def test_build_members_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="重複"):
        build_members(rows((None, "田中", 100.0), (None, "田中 ", 80.0)), [], no_tasks)


@pytest.mark.parametrize("ratio", [None, 9.99, 300.01, 0.0, -10.0, float("nan"), float("inf"), 100.123])
def test_build_members_rejects_a_bad_ratio(ratio: float | None) -> None:
    with pytest.raises(ValueError, match="相対比率"):
        build_members(rows((None, "田中", ratio)), [], no_tasks)


@pytest.mark.parametrize("ratio", [10.0, 300.0, 100.25])
def test_build_members_accepts_the_boundaries(ratio: float) -> None:
    members, _ = build_members(rows((None, "田中", ratio)), [], no_tasks)
    assert members[0].ratio == pytest.approx(ratio / 100)


def test_build_members_reports_renames() -> None:
    _, renames = build_members(rows(("田中", "田中太郎", 100.0)), ["田中"], no_tasks)
    assert renames == {"田中": "田中太郎"}


def test_build_members_allows_swapping_two_names() -> None:
    _, renames = build_members(rows(("A", "B", 100.0), ("B", "A", 100.0)), ["A", "B"], no_tasks)
    assert renames == {"A": "B", "B": "A"}


def test_build_members_rejects_deleting_a_member_with_tasks() -> None:
    counts = {"田中": 2}
    with pytest.raises(ValueError, match="田中.*2件"):
        build_members([], ["田中"], lambda name: counts.get(name, 0))


def test_build_members_allows_deleting_a_member_without_tasks() -> None:
    members, _ = build_members([], ["田中"], no_tasks)
    assert members == []


def test_build_members_rejects_taking_the_name_of_a_member_that_is_deleted_with_tasks() -> None:
    counts = {"B": 1}
    with pytest.raises(ValueError, match="B.*1件"):
        build_members(rows(("A", "B", 100.0)), ["A", "B"], lambda name: counts.get(name, 0))


def test_allocation_is_stored_as_a_fraction() -> None:
    task = make(assignees=[("田中", 60.0)])
    assert task.assignees == [Assignee("田中", pytest.approx(0.6))]


def test_blank_rows_are_dropped() -> None:
    assert make(assignees=[("", 60.0), ("  ", None)]).assignees == []


@pytest.mark.parametrize("percent", [None, 0.0, 0.5, 100.5, float("nan"), float("inf")])
def test_a_bad_allocation_is_rejected_for_a_chosen_member(percent: float | None) -> None:
    with pytest.raises(ValueError, match="割り当て率"):
        make(assignees=[("田中", percent)])


@pytest.mark.parametrize("percent", [1.0, 100.0, 33.33])
def test_allocation_boundaries_are_accepted(percent: float) -> None:
    assert make(assignees=[("田中", percent)]).assignees[0].allocation == pytest.approx(percent / 100)


def test_several_assignees_keep_their_order_and_allocations() -> None:
    task = make(assignees=[("田中", 100.0), ("鈴木", 50.0)])
    assert task.assignees == [Assignee("田中", 1.0), Assignee("鈴木", 0.5)]


def test_the_same_member_twice_is_rejected() -> None:
    with pytest.raises(ValueError, match="重複"):
        make(assignees=[("田中", 100.0), (" 田中 ", 50.0)])


def test_actuals_default_to_none() -> None:
    assert make().actuals == []


def test_start_and_end_make_one_actual() -> None:
    task = make(actual_start="2026-10-05T09:00", actual_end="2026-10-05T17:30")
    assert task.actuals == [Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 17, 30))]


def test_start_only_is_in_progress() -> None:
    assert make(actual_start="2026-10-05T09:00").actuals == [Actual(datetime(2026, 10, 5, 9, 0), None)]


def test_end_without_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="実績の開始"):
        make(actual_end="2026-10-05T17:30")


def test_actual_end_before_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="実績の終了"):
        make(actual_start="2026-10-05T09:00", actual_end="2026-10-05T08:59")


@pytest.mark.parametrize("bad", ["2026-10-05T09:00+09:00", "abc", "1999-10-05T09:00", "2101-01-01T09:00"])
def test_bad_actual_start_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        make(actual_start=bad)


def test_clearing_the_inputs_removes_the_actual() -> None:
    existing = Task("t", actuals=[Actual(datetime(2026, 10, 5, 9, 0), None)])
    assert make(existing).actuals == []


def test_two_or_more_actuals_are_kept_and_the_inputs_are_ignored() -> None:
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    ]
    existing = Task("t", actuals=list(kept))
    assert make(existing, actual_start="", actual_end="").actuals == kept
    assert make(existing, actual_start="2030-01-01T09:00").actuals == kept


def test_progress_is_saved_in_the_actual() -> None:
    task = make(actual_start="2026-10-05T09:00", actual_progress=40)
    assert task.actuals == [Actual(datetime(2026, 10, 5, 9, 0), None, 40)]


def test_progress_zero_and_hundred_are_accepted() -> None:
    assert make(actual_start="2026-10-05T09:00", actual_progress=0).actuals[0].progress == 0
    assert make(actual_start="2026-10-05T09:00", actual_progress=100.0).actuals[0].progress == 100


def test_empty_progress_is_none() -> None:
    assert make(actual_start="2026-10-05T09:00", actual_progress=None).actuals[0].progress is None


@pytest.mark.parametrize("bad", [-1, 101, 40.5, float("nan"), float("inf")])
def test_bad_progress_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="進捗度"):
        make(actual_start="2026-10-05T09:00", actual_progress=bad)


def test_progress_without_a_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="実績の開始"):
        make(actual_progress=40)


def test_two_or_more_actuals_keep_their_progress_and_ignore_the_input() -> None:
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0), 30),
        Actual(datetime(2026, 10, 6, 9, 0), None, 60),
    ]
    existing = Task("t", actuals=list(kept))
    assert make(existing, actual_progress=None).actuals == kept
    assert make(existing, actual_progress=90).actuals == kept


@pytest.mark.parametrize(
    ("has_start", "has_end", "progress", "expected"),
    [
        (True, False, 100, None),
        (True, False, 100.0, None),
        (True, False, 99, Status.RUNNING),
        (True, False, 0, Status.RUNNING),
        (True, False, None, Status.RUNNING),
        (True, True, 100, Status.DONE),
        (True, True, None, Status.DONE),
        (False, False, 100, None),
    ],
)
def test_suggest_status_with_progress(
    has_start: bool, has_end: bool, progress: float | None, expected: Status | None
) -> None:
    assert suggest_status(has_start, has_end, progress) is expected


def test_compose_actual() -> None:
    assert compose_actual("", "") == ""
    assert compose_actual(" 2026-10-5 ", "09:00") == "2026-10-05T09:00"
    for day, clock in (("2026-10-05", ""), ("", "09:00")):
        with pytest.raises(ValueError, match="両方"):
            compose_actual(day, clock)
    with pytest.raises(ValueError):
        compose_actual("2026-10-05", "9時")


@pytest.mark.parametrize(
    ("has_start", "has_end", "expected"),
    [(False, False, None), (True, False, Status.RUNNING), (True, True, Status.DONE), (False, True, None)],
)
def test_suggest_status(has_start: bool, has_end: bool, expected: Status | None) -> None:
    assert suggest_status(has_start, has_end) is expected


S1, E1 = "2026-10-05T09:00", "2026-10-05T12:00"
S2, E2 = "2026-10-06T09:00", "2026-10-06T12:00"


def test_intervals_build_in_order() -> None:
    result = build_actual_intervals([(S1, E1, 30), (S2, "", 60)])
    assert result == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), 30),
        Actual(datetime(2026, 10, 6, 9), None, 60),
    ]


def test_empty_rows_are_ignored() -> None:
    assert build_actual_intervals([("", "", None), (S1, E1, None), ("", "", None)]) == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), None)
    ]
    assert build_actual_intervals([("", "", None)]) == []
    assert build_actual_intervals([]) == []


def test_interval_errors_name_the_row() -> None:
    with pytest.raises(ValueError, match="区間 2: 実績の終了"):
        build_actual_intervals([(S1, E1, None), (S2, "2026-10-06T08:00", None)])
    with pytest.raises(ValueError, match="区間 1: 実績の開始"):
        build_actual_intervals([("", E1, None)])
    with pytest.raises(ValueError, match="区間 1: .*形式"):
        build_actual_intervals([("abc", "", None)])


def test_the_row_number_counts_the_ignored_empty_rows() -> None:
    with pytest.raises(ValueError, match="区間 3: 前の区間と重なっています"):
        build_actual_intervals(
            [(S1, "2026-10-05T12:00", None), ("", "", None), ("2026-10-05T11:00", E2, None)]
        )


def test_overlapping_intervals_are_rejected_but_touching_ones_are_not() -> None:
    with pytest.raises(ValueError, match="区間 2: 前の区間と重なっています"):
        build_actual_intervals([(S1, E1, None), ("2026-10-05T11:59", E2, None)])
    assert len(build_actual_intervals([(S1, E1, None), (E1, E2, None)])) == 2


def test_intervals_must_be_in_start_order() -> None:
    with pytest.raises(ValueError, match="開始の早い順"):
        build_actual_intervals([(S2, E2, None), (S1, E1, None)])


def test_only_the_last_interval_may_be_open() -> None:
    with pytest.raises(ValueError, match="区間 1: 終了のない区間は最後の1つだけ"):
        build_actual_intervals([(S1, "", None), (S2, E2, None)])
    assert len(build_actual_intervals([(S1, E1, None), (S2, "", None)])) == 2


def test_progress_must_not_decrease_across_intervals() -> None:
    with pytest.raises(ValueError, match="区間 3: 進捗度は前の区間以上"):
        build_actual_intervals(
            [(S1, E1, 50), (S2, E2, None), ("2026-10-07T09:00", "", 40)]
        )
    assert len(build_actual_intervals([(S1, E1, 50), (S2, E2, 50)])) == 2


def test_build_task_uses_the_rows_when_given() -> None:
    existing = Task("t", actuals=[Actual(datetime(2026, 1, 1, 9), None)])
    task = make(existing, actual_rows=[(S1, E1, None), (S2, "", None)], actual_start="2030-01-01T09:00")
    assert [a.start for a in task.actuals] == [datetime(2026, 10, 5, 9), datetime(2026, 10, 6, 9)]
    assert make(existing, actual_rows=[]).actuals == []
    assert make(existing, actual_rows=[("", "", None)]).actuals == []


def test_build_task_without_rows_keeps_the_simple_behaviour() -> None:
    kept = [Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)), Actual(datetime(2026, 10, 6, 9), None)]
    assert make(Task("t", actuals=list(kept)), actual_start="").actuals == kept


@pytest.mark.parametrize(
    ("has_start", "has_end", "progress", "expected"),
    [
        (False, False, None, None),
        (False, True, None, None),
        (True, False, None, Status.RUNNING),
        (True, False, 100, None),
        (True, True, None, Status.PAUSED),
        (True, True, 50, Status.PAUSED),
        (True, True, 99, Status.PAUSED),
        (True, True, 100, Status.DONE),
    ],
)
def test_suggest_status_for_intervals(
    has_start: bool, has_end: bool, progress: float | None, expected: Status | None
) -> None:
    assert suggest_status(has_start, has_end, progress, intervals=True) is expected


def test_suggest_status_for_simple_is_unchanged_by_the_intervals_flag_default() -> None:
    assert suggest_status(True, True, 50) is Status.DONE


async def test_settings_dialog_applies_the_actual_mode(user: User) -> None:
    applied: list[tuple[float, time, ActualMode]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: applied.append((h, s, m))
            ),
        )

    await user.open("/")
    user.find("open").click()
    mode = user.find(marker="settings-actual-mode").elements.pop()
    assert mode.value == "simple"
    mode.set_value("intervals")
    user.find(marker="settings-apply").click()
    assert applied == [(6.5, time(9, 0), ActualMode.INTERVALS)]


async def test_settings_dialog_cannot_go_back_to_simple_with_multi_interval_tasks(
    user: User,
) -> None:
    applied: list[tuple[float, time, ActualMode]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda h, s, m: applied.append((h, s, m)),
                ActualMode.INTERVALS,
                multi_interval_tasks=2,
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_see("2件のタスクに複数の区間があるため、簡易には戻せません")
    mode = user.find(marker="settings-actual-mode").elements.pop()
    mode.set_value("simple")
    assert mode.value == "intervals"  # 選んでも、区間に戻る
    user.find(marker="settings-apply").click()
    assert applied == [(6.5, time(9, 0), ActualMode.INTERVALS)]


async def test_settings_dialog_hides_the_lock_message_without_multi_interval_tasks(
    user: User,
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: None, ActualMode.INTERVALS
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_not_see(marker="settings-mode-locked")
    user.find(marker="settings-actual-mode").elements.pop().set_value("simple")
    assert user.find(marker="settings-actual-mode").elements.pop().value == "simple"


async def test_settings_dialog_has_no_lock_when_it_was_simple(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: None, ActualMode.SIMPLE, multi_interval_tasks=1
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_not_see(marker="settings-mode-locked")  # 簡易のままなら、制限はない


def test_project_code_is_trimmed_and_saved() -> None:
    assert make(project_code="  PRJ-001 ").project_code == "PRJ-001"


def test_project_code_defaults_to_empty_and_can_be_cleared() -> None:
    assert make().project_code == ""
    assert make(Task("t", project_code="OLD")).project_code == ""  # 入力が空なら空にできる


def test_project_code_length_is_checked_after_trimming() -> None:
    assert make(project_code="A" * 20).project_code == "A" * 20
    assert make(project_code=" " + "A" * 20 + " ").project_code == "A" * 20
    with pytest.raises(ValueError, match="20文字以内"):
        make(project_code="A" * 21)


def test_a_blank_project_code_becomes_empty() -> None:
    assert make(project_code="   ").project_code == ""


def test_build_task_sets_and_dedupes_predecessors() -> None:
    task = make(predecessors=["a", "b", "a"], linkable_ids=frozenset({"a", "b"}))
    assert task.predecessors == ["a", "b"]


def test_build_task_keeps_existing_predecessors_when_not_given() -> None:
    existing = Task("x", id="xxxxxxxx", predecessors=["a"])
    task = make(existing)
    assert task.predecessors == ["a"] and task.id == "xxxxxxxx"


@pytest.mark.parametrize("bad", [["zz"], ["xxxxxxxx"]])
def test_build_task_rejects_unlinkable_predecessors(bad: list[str]) -> None:
    existing = Task("x", id="xxxxxxxx")
    with pytest.raises(ValueError, match="先行タスク"):
        make(existing, predecessors=bad, linkable_ids=frozenset({"a"}))


def test_push_hint_only_when_the_start_is_pushed() -> None:
    start = datetime(2026, 10, 5, 9, 0)
    assert push_hint(start, []) == ""
    assert push_hint(start, [datetime(2026, 10, 5, 8, 0)]) == ""
    assert push_hint(start, [datetime(2026, 10, 12, 9, 0)]) == (
        "先行の完了により、実際の開始は 10/12 09:00 です"
    )
    assert push_hint(None, [datetime(2026, 10, 12, 9, 0)]).endswith("10/12 09:00 です")


TICKET = UrlTemplate("チケット", "https://example.com/{ID}")


def test_build_urls_builds_links_and_ignores_empty_rows() -> None:
    rows = [("メモ", "チケット", " 231 "), ("", None, ""), ("", None, " https://example.com/a ")]
    assert build_urls(rows, [TICKET]) == [
        TaskUrl("メモ", "チケット", {"ID": "231"}),
        TaskUrl("", None, {"URL": "https://example.com/a"}),
    ]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("", "チケット", ""), "1行目.*ID"),
        (("名前だけ", None, ""), "1行目.*URL"),
        (("", None, "javascript:alert(1)"), "1行目.*http"),
        (("", "なし", "1"), "1行目.*見つかりません"),
    ],
)
def test_build_urls_rejects_incomplete_rows_with_the_row_number(
    row: tuple[str, str | None, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_urls([row], [TICKET])


def test_build_task_keeps_the_existing_links_unless_given_new_ones() -> None:
    existing = Task("設計", urls=[TaskUrl("", None, {"URL": "https://example.com/a"})])
    assert make(existing).urls == existing.urls
    replaced = [TaskUrl("", None, {"URL": "https://example.com/b"})]
    assert make(existing, urls=replaced).urls == replaced
    assert make(existing, urls=[]).urls == []


def mount_settings(
    templates: list[UrlTemplate],
    usage: dict[str, int],
    applied: list[int],
    edits: list[TemplateEdit],
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda h, s, m: applied.append(1),
                templates=templates,
                template_usage=lambda name: usage.get(name, 0),
                on_templates=edits.append,
            ),
        )


async def test_adding_a_template_applies_it(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings([], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-add").click()
    await asyncio.sleep(0.2)  # 行の描き直しを待つ
    user.find(marker="settings-template-0-name").type("チケット")
    user.find(marker="settings-template-0-pattern").type("https://example.com/{ID}")
    user.find(marker="settings-apply").click()
    assert applied == [1]
    assert edits == [TemplateEdit([UrlTemplate("チケット", "https://example.com/{ID}")], {}, [])]


async def test_unchanged_templates_do_not_call_on_templates(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings([UrlTemplate("チケット", "https://example.com/{ID}")], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert applied == [1] and edits == []


async def test_a_blank_added_row_is_ignored(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings([], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-add").click()
    await asyncio.sleep(0.2)  # 行の描き直しを待つ
    user.find(marker="settings-apply").click()
    assert applied == [1] and edits == []


@pytest.mark.parametrize(
    ("name", "pattern", "message"),
    [
        ("", "https://x.test/{ID}", "名前を入力"),
        ("a", "javascript:{ID}", "http://"),
        ("チケット", "https://y.test/{ID}", "重複"),
    ],
)
async def test_invalid_templates_keep_the_dialog_and_call_nothing(
    user: User, name: str, pattern: str, message: str
) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings([UrlTemplate("チケット", "https://example.com/{ID}")], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-add").click()
    await asyncio.sleep(0.2)  # 行の描き直しを待つ
    user.find(marker="settings-template-1-name").type(name)
    user.find(marker="settings-template-1-pattern").type(pattern)
    user.find(marker="settings-apply").click()
    await user.should_see(message)
    assert applied == [] and edits == []


async def test_renaming_a_template_is_reported_as_a_rename(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings(
        [UrlTemplate("チケット", "https://example.com/{ID}")], {"チケット": 3}, applied, edits
    )
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-0-name").clear().type("課題")
    user.find(marker="settings-apply").click()
    assert edits == [
        TemplateEdit([UrlTemplate("課題", "https://example.com/{ID}")], {"チケット": "課題"}, [])
    ]


async def test_deleting_an_unused_template_needs_no_confirmation(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings([UrlTemplate("チケット", "https://example.com/{ID}")], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-0-remove").click()
    user.find(marker="settings-apply").click()
    assert edits == [TemplateEdit([], {}, ["チケット"])]


async def test_deleting_a_used_template_asks_with_the_count(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings(
        [UrlTemplate("チケット", "https://example.com/{ID}")], {"チケット": 3}, applied, edits
    )
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-0-remove").click()
    user.find(marker="settings-apply").click()
    await user.should_see("3件")
    assert applied == [] and edits == []
    user.find(marker="settings-confirm-delete").click()
    assert applied == [1]
    assert edits == [TemplateEdit([], {}, ["チケット"])]


async def test_cancelling_the_delete_confirmation_changes_nothing(user: User) -> None:
    applied: list[int] = []
    edits: list[TemplateEdit] = []
    mount_settings(
        [UrlTemplate("チケット", "https://example.com/{ID}")], {"チケット": 3}, applied, edits
    )
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-template-0-remove").click()
    user.find(marker="settings-apply").click()
    user.find(marker="settings-confirm-cancel").click()
    assert applied == [] and edits == []
    await user.should_see(marker="settings-apply")  # 設定ダイアログは開いたまま


def prow(original: str | None, name: str, *levels: tuple[str | None, str, float | None]) -> ParameterRow:
    return ParameterRow(original, name, [LevelRow(o, n, v) for o, n, v in levels])


BEFORE = [Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)]), Parameter("専門", [Level("高", 0.1)])]


def test_build_parameter_edit_converts_percent_to_a_fraction_and_trims_names() -> None:
    edit = build_parameter_edit([prow(None, " 経験 ", (None, " 上級 ", 20.0), (None, "初級", -20.0))], [])
    assert edit.parameters == [Parameter("経験", [Level("上級", 0.2), Level("初級", -0.2)])]
    assert edit.parameter_map == {} and edit.level_map == {}


def test_build_parameter_edit_maps_renames_and_deletions_by_the_old_names() -> None:
    rows = [prow("経験", "スキル", ("初級", "初級", -20.0), (None, "中級", 0.0))]  # 上級を削除、中級を追加
    edit = build_parameter_edit(rows, BEFORE)
    assert edit.parameter_map == {"経験": "スキル", "専門": None}
    assert edit.level_map == {"経験": {"初級": "初級", "上級": None}}


def test_build_parameter_edit_keeps_swapped_names_apart() -> None:
    before = [Parameter("A", [Level("x", 0.1)]), Parameter("B", [Level("y", 0.2)])]
    rows = [prow("B", "A", ("y", "y", 20.0)), prow("A", "B", ("x", "x", 10.0))]
    edit = build_parameter_edit(rows, before)
    assert edit.parameter_map == {"A": "B", "B": "A"}
    assert edit.level_map == {"A": {"x": "x"}, "B": {"y": "y"}}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([prow(None, "")], "名前"),
        ([prow(None, "A"), prow(None, "A")], "重複"),
        ([prow(None, "A", (None, "", 10.0))], "名前"),
        ([prow(None, "A", (None, "x", 10.0), (None, "x", 20.0))], "重複"),
        ([prow(None, "A", (None, "x", None))], "判定値"),
        ([prow(None, "A", (None, "x", float("nan")))], "判定値"),
        ([prow(None, "A", (None, "x", -90.01))], "判定値"),
        ([prow(None, "A", (None, "x", 290.01))], "判定値"),
        ([prow(None, "A", (None, "x", 10.005))], "小数点"),
    ],
)
def test_build_parameter_edit_rejects_bad_rows(rows: list[ParameterRow], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_parameter_edit(rows, [])


def test_build_parameter_edit_accepts_the_boundaries() -> None:
    edit = build_parameter_edit([prow(None, "A", (None, "lo", -90.0), (None, "hi", 290.0), (None, "z", 12.5))], [])
    assert [lv.value for lv in edit.parameters[0].levels] == [-0.9, 2.9, 0.125]


EXPERIENCE = Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])


def test_build_members_keeps_the_levels_that_exist() -> None:
    row = MemberRow(None, "田中", 100.0, {"経験": "上級", "消えた": "x", "経験2": "y"})
    members, _ = build_members([row], [], no_tasks, [EXPERIENCE])
    assert members == [Member("田中", 1.0, {"経験": "上級"})]


def test_build_members_drops_a_level_that_no_longer_exists() -> None:
    row = MemberRow(None, "田中", 100.0, {"経験": "存在しない"})
    members, _ = build_members([row], [], no_tasks, [EXPERIENCE])
    assert members[0].levels == {}


def test_build_members_without_parameters_has_no_levels() -> None:
    members, _ = build_members([MemberRow(None, "田中", 100.0, {"経験": "上級"})], [], no_tasks)
    assert members[0].levels == {}


def test_a_renamed_member_keeps_the_levels() -> None:
    row = MemberRow("田中", "田中太郎", 100.0, {"経験": "上級"})
    members, renames = build_members([row], ["田中"], no_tasks, [EXPERIENCE])
    assert members == [Member("田中太郎", 1.0, {"経験": "上級"})]
    assert renames == {"田中": "田中太郎"}


@pytest.mark.parametrize(
    ("percent", "levels", "text"),
    [
        (100.0, {}, "相対比率 100%"),
        (100.0, {"経験": "上級"}, "相対比率 120%"),
        (100.0, {"経験": "初級"}, "相対比率 80%"),
        (290.0, {"経験": "上級"}, "相対比率 300%(範囲に丸めました)"),
        (10.0, {"経験": "初級"}, "相対比率 10%(範囲に丸めました)"),
        (30.0, {"経験": "初級"}, "相対比率 10%"),  # ちょうど下限は、丸めたことにしない
        (None, {}, ""),
        (float("nan"), {}, ""),
    ],
)
def test_effective_ratio_text(percent: float | None, levels: dict[str, str], text: str) -> None:
    assert effective_ratio_text(MemberRow(None, "a", percent, levels), [EXPERIENCE]) == text
