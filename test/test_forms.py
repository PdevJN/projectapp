import asyncio
from datetime import date, datetime, time

import pytest

import projectapp.models as models
from nicegui import ui
from nicegui.testing import User

from projectapp.models import Event, Membership, WorkDay
from projectapp.categories import COLOR_HEX, COLOR_LABELS, COLORS, CategoryEdit
from projectapp.forms import (
    MEMBER_ICON_COLUMN_REM,
    MEMBER_NAME_COLUMN_REM,
    MEMBER_RATIO_COLUMN_REM,
    member_columns,
    member_table_min_rem,
    CategoryRow,
    EventRow,
    RangeAdd,
    WorkDayRow,
    build_work_day_list,
    plan_work_day_range,
    work_day_range_summary,
    build_category_edit,
    LevelRow,
    MemberRow,
    ParameterRow,
    build_actual_intervals,
    build_members,
    build_parameter_edit,
    build_section_name,
    build_task,
    build_urls,
    build_base_date,
    build_work_settings,
    compose_actual,
    compose_datetime,
    default_times,
    build_ratio_limits,
    ratio_range_text,
    effective_ratio_text,
    exceeds_decimals,
    in_hours_range,
    needs_end_time,
    needs_start_time,
    open_file_dialog,
    open_name_dialog,
    open_section_dialog,
    build_event_list,
    open_settings_dialog,
    open_stale_reference_dialog,
    open_stale_snapshot_dialog,
    open_unsaved_dialog,
    parse_datetime,
    end_gap_hint,
    push_hint,
    suggest_status,
)
from projectapp.models import (
    Actual,
    ActualMode,
    ReferenceMode,
    Assignee,
    Category,
    Level,
    Member,
    Parameter,
    Priority,
    RatioLimits,
    Status,
    Task,
    TaskKind,
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


@pytest.mark.parametrize("hours", [0.0, 1.0, 1.5, 1.25, 0.01, 130.0])
def test_effort_up_to_two_decimals_is_accepted(hours: float) -> None:
    assert make(effort_hours=hours).effort_hours == hours


@pytest.mark.parametrize("hours", [1.234, 0.001, 2.505])
def test_effort_with_more_than_two_decimals_is_rejected(hours: float) -> None:
    with pytest.raises(ValueError, match="工数は小数点以下2桁"):
        make(effort_hours=hours)


def test_an_existing_effort_with_three_decimals_is_kept_when_unchanged() -> None:
    existing = Task("旧", effort_hours=1.234)  # 古いファイルの値は、触らなければ保存できる
    assert make(existing, effort_hours=1.234).effort_hours == 1.234


def test_changing_an_existing_effort_to_three_decimals_is_rejected() -> None:
    existing = Task("旧", effort_hours=1.234)
    with pytest.raises(ValueError, match="工数は小数点以下2桁"):
        make(existing, effort_hours=1.2345)


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


def test_build_members_carries_the_icon(icon: str) -> None:
    rows = [MemberRow("甲", "甲", 100.0, icon=icon), MemberRow(None, "乙", 100.0)]
    members, _ = build_members(rows, ["甲"], lambda _: 0)
    assert [m.icon for m in members] == [icon, ""]


def test_build_members_rejects_a_broken_icon() -> None:
    with pytest.raises(ValueError, match="アイコン"):
        build_members([MemberRow(None, "甲", 100.0, icon="data:image/png;base64,AAAA")], [], lambda _: 0)


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


def test_the_task_progress_is_saved_apart_from_the_actuals() -> None:
    task = make(progress=40)
    assert task.progress == 40 and task.actuals == []


def test_the_task_progress_accepts_zero_hundred_and_empty() -> None:
    assert make(progress=0).progress == 0
    assert make(progress=100.0).progress == 100
    assert make(Task("t", progress=40), progress=None).progress is None


@pytest.mark.parametrize("bad", [-1, 101, 40.5, float("nan"), float("inf")])
def test_a_bad_task_progress_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="進捗度"):
        make(progress=bad)


def test_a_checkpoint_drops_the_task_progress() -> None:
    task = make(
        Task("t", progress=40),
        kind=TaskKind.CHECKPOINT,
        deadline="2026-10-09T17:00",
        status=Status.NOT_STARTED,
        progress=40,
    )
    assert task.progress is None


def test_two_or_more_actuals_are_kept_when_saved_with_the_simple_input() -> None:
    kept = [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 12, 0)),
        Actual(datetime(2026, 10, 6, 9, 0), None),
    ]
    existing = Task("t", actuals=list(kept))
    assert make(existing).actuals == kept


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
    result = build_actual_intervals([(S1, E1), (S2, "")])
    assert result == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 6, 9)),
    ]


def test_empty_rows_are_ignored() -> None:
    assert build_actual_intervals([("", ""), (S1, E1), ("", "")]) == [
        Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12))
    ]
    assert build_actual_intervals([("", "")]) == []
    assert build_actual_intervals([]) == []


def test_interval_errors_name_the_row() -> None:
    with pytest.raises(ValueError, match="区間 2: 実績の終了"):
        build_actual_intervals([(S1, E1), (S2, "2026-10-06T08:00")])
    with pytest.raises(ValueError, match="区間 1: 実績の開始"):
        build_actual_intervals([("", E1)])
    with pytest.raises(ValueError, match="区間 1: .*形式"):
        build_actual_intervals([("abc", "")])


def test_the_row_number_counts_the_ignored_empty_rows() -> None:
    with pytest.raises(ValueError, match="区間 3: 前の区間と重なっています"):
        build_actual_intervals(
            [(S1, "2026-10-05T12:00"), ("", ""), ("2026-10-05T11:00", E2)]
        )


def test_overlapping_intervals_are_rejected_but_touching_ones_are_not() -> None:
    with pytest.raises(ValueError, match="区間 2: 前の区間と重なっています"):
        build_actual_intervals([(S1, E1), ("2026-10-05T11:59", E2)])
    assert len(build_actual_intervals([(S1, E1), (E1, E2)])) == 2


def test_intervals_must_be_in_start_order() -> None:
    with pytest.raises(ValueError, match="開始の早い順"):
        build_actual_intervals([(S2, E2), (S1, E1)])


def test_only_the_last_interval_may_be_open() -> None:
    with pytest.raises(ValueError, match="区間 1: 終了のない区間は最後の1つだけ"):
        build_actual_intervals([(S1, ""), (S2, E2)])
    assert len(build_actual_intervals([(S1, E1), (S2, "")])) == 2


def test_build_task_uses_the_rows_when_given() -> None:
    existing = Task("t", actuals=[Actual(datetime(2026, 1, 1, 9))])
    task = make(existing, actual_rows=[(S1, E1), (S2, "")], actual_start="2030-01-01T09:00")
    assert [a.start for a in task.actuals] == [datetime(2026, 10, 5, 9), datetime(2026, 10, 6, 9)]
    assert make(existing, actual_rows=[]).actuals == []
    assert make(existing, actual_rows=[("", "")]).actuals == []


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


def test_category_id_is_saved() -> None:
    assert make(category_id="abcd1234").category_id == "abcd1234"


def test_category_defaults_to_undecided_and_can_be_cleared() -> None:
    assert make().category_id is None
    assert make(Task("t", category_id="abcd1234")).category_id is None  # 入力が未定なら未定にできる


def test_checkpoint_keeps_the_category() -> None:
    task = make(kind=TaskKind.CHECKPOINT, deadline="2026-10-09T17:00", status=Status.NOT_STARTED, category_id="abcd1234")
    assert task.category_id == "abcd1234"


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
        (140.0, {"経験": "上級"}, "相対比率 150%(範囲に丸めました)"),
        (40.0, {"経験": "初級"}, "相対比率 50%(範囲に丸めました)"),
        (70.0, {"経験": "初級"}, "相対比率 50%"),  # ちょうど下限は、丸めたことにしない
        (130.0, {"経験": "上級"}, "相対比率 150%"),  # ちょうど上限も同じ
        (None, {}, ""),
        (float("nan"), {}, ""),
    ],
)
def test_effective_ratio_text(percent: float | None, levels: dict[str, str], text: str) -> None:
    assert effective_ratio_text(MemberRow(None, "a", percent, levels), [EXPERIENCE]) == text


def test_build_members_carries_ratio_unclamped() -> None:
    rows = [MemberRow(None, "田中", 200.0, ratio_unclamped=True), MemberRow(None, "鈴木", 100.0)]
    members, _ = build_members(rows, [], lambda _: 0)
    assert [m.ratio_unclamped for m in members] == [True, False]


def test_effective_ratio_text_for_an_unclamped_member() -> None:
    row = MemberRow(None, "a", 200.0, ratio_unclamped=True)
    assert effective_ratio_text(row, [EXPERIENCE]) == "相対比率 200%(丸め対象外)"
    over = MemberRow(None, "a", 290.0, {"経験": "上級"}, ratio_unclamped=True)
    assert effective_ratio_text(over, [EXPERIENCE]) == "相対比率 300%(丸め対象外・相対比率 310% → 安全範囲の上限 300% に制限)"
    assert effective_ratio_text(MemberRow(None, "a", 200.0), [EXPERIENCE]) == "相対比率 150%(範囲に丸めました)"


def test_build_members_keeps_the_id_of_a_renamed_row() -> None:
    members, renames = build_members([MemberRow("田中", "田中二郎", 100.0, id="m1")], ["田中"], lambda name: 0)
    assert [(m.name, m.id) for m in members] == [("田中二郎", "m1")]
    assert renames == {"田中": "田中二郎"}


def test_build_members_keeps_each_rows_id_when_names_are_swapped() -> None:
    rows = [MemberRow("A", "B", 100.0, id="ida"), MemberRow("B", "A", 100.0, id="idb")]
    members, _ = build_members(rows, ["A", "B"], lambda name: 0)
    assert [(m.name, m.id) for m in members] == [("B", "ida"), ("A", "idb")]


def test_build_members_gives_a_new_row_an_id_that_is_not_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter(["aaaaaaaa", "bbbbbbbb", "cccccccc"])
    monkeypatch.setattr(models.secrets, "token_hex", lambda nbytes: next(values))
    rows = [MemberRow(None, "田中", 100.0), MemberRow(None, "鈴木", 100.0)]
    members, _ = build_members(rows, [], lambda name: 0, taken={"aaaaaaaa"})
    assert [m.id for m in members] == ["bbbbbbbb", "cccccccc"]


def test_a_deleted_and_re_added_member_gets_a_new_id() -> None:
    members, _ = build_members([MemberRow(None, "田中", 100.0)], ["田中"], lambda name: 0, taken={"old"})
    assert members[0].id != "old"


def row(name: str = "開発", **kwargs: object) -> CategoryRow:
    values: dict[str, object] = {"original": None, "name": name, "kind": "", "expiry": "", "color": "blue", "prj_code": ""}
    values.update(kwargs)
    return CategoryRow(**values)  # type: ignore[arg-type]


def test_build_category_edit_makes_categories_with_new_ids() -> None:
    edit = build_category_edit(
        [row(" 開発 ", kind=" 業務 ", expiry="2026-12-31", color="red", prj_code=" P ")], [], {"aaaaaaaa"}
    )
    (category,) = edit.categories
    assert (category.name, category.kind, category.expiry_date, category.color, category.prj_code) == (
        "開発", "業務", date(2026, 12, 31), "red", "P",
    )
    assert category.id != "aaaaaaaa" and len(category.id) == 8
    assert edit.removed_ids == []


def test_build_category_edit_keeps_ids_and_reports_removals() -> None:
    keep, drop = Category("keep"), Category("drop")
    edit = build_category_edit([row("keep2", original=keep.id)], [keep, drop], set())
    assert [c.id for c in edit.categories] == [keep.id]
    assert edit.categories[0].name == "keep2"
    assert edit.removed_ids == [drop.id]


def test_build_category_edit_ignores_a_blank_new_row() -> None:
    assert build_category_edit([row("")], [], set()) == CategoryEdit([], [])


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([row("")], None),
        ([row("", kind="x")], "名前"),
        ([row("未定")], "未定"),
        ([row("a"), row("a")], "重複"),
        ([row("a", expiry="2026-13-40")], "有効期限"),
        ([row("a", color="gold")], "色"),
        ([row("a", prj_code="A" * 21)], "PRJ"),
        ([row("あ" * 31)], "名前"),
        ([row("a\nb")], "名前"),
        ([row("a", prj_code="P\nQ")], "PRJ"),
        ([row("a", prj_code="日本語")], "PRJ"),
        ([row("a", prj_code="PRJ 1")], "PRJ"),
        ([row("a", kind="あ" * 21)], "種別"),
        ([row("a", kind="業務\n開発")], "種別"),
    ],
)
def test_build_category_edit_rejects_bad_input(rows: list[CategoryRow], message: str | None) -> None:
    if message is None:  # 完全に空の新しい行は無視する
        assert build_category_edit(rows, [], set()).categories == []
        return
    with pytest.raises(ValueError, match=message):
        build_category_edit(rows, [], set())


def mount_category_settings(
    categories: list[Category],
    usage: dict[str, int],
    applied: list[int],
    edits: list[CategoryEdit],
    templates: list[UrlTemplate] | None = None,
    template_usage: dict[str, int] | None = None,
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
                template_usage=lambda name: (template_usage or {}).get(name, 0),
                on_templates=lambda e: None,
                categories=categories,
                category_usage=lambda cid: usage.get(cid, 0),
                on_categories=edits.append,
                used_ids={c.id for c in categories},
            ),
        )


async def test_undecided_row_is_shown_and_cannot_be_edited(user: User) -> None:
    mount_category_settings([], {}, [], [])
    await user.open("/")
    user.find("open").click()
    await user.should_see(marker="settings-category-undecided")
    for part in ("name", "remove"):
        await user.should_not_see(marker=f"settings-category-undecided-{part}")


async def test_adding_a_category_applies_it(user: User) -> None:
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-add").click()
    await asyncio.sleep(0.2)  # 行の描き直しを待つ
    user.find(marker="settings-category-0-name").type("開発")
    user.find(marker="settings-category-0-kind").type("業務")
    user.find(marker="settings-category-0-expiry").type("2026-12-31")
    user.find(marker="settings-category-0-prj").type("PRJ-1")
    user.find(marker="settings-category-0-color").elements.pop().set_value("red")
    user.find(marker="settings-apply").click()
    assert applied == [1]
    (edit,) = edits
    (category,) = edit.categories
    assert (category.name, category.kind, category.expiry_date, category.color, category.prj_code) == (
        "開発", "業務", date(2026, 12, 31), "red", "PRJ-1",
    )
    assert edit.removed_ids == []


async def test_a_new_row_gets_the_first_unused_color(user: User) -> None:
    mount_category_settings([Category("a", color="blue")], {}, [], [])
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-add").click()
    await asyncio.sleep(0.2)
    assert user.find(marker="settings-category-1-color").elements.pop().value == "indigo"


async def test_the_color_select_shows_a_colored_dot_with_the_name(user: User) -> None:
    mount_category_settings([Category("a", color="blue")], {}, [], [])
    await user.open("/")
    user.find("open").click()
    select = user.find(marker="settings-category-0-color").elements.pop()
    assert list(select.options.values()) == [COLOR_LABELS[c] for c in COLORS]  # 名前が選択肢の文字
    for slot in ("option", "selected-item"):  # 選択肢も、選んだあとの表示も、丸 + 名前
        template = select.slots[slot].template
        assert 'name="circle"' in template and "props.opt.label" in template
        # NiceGUI の select は、選択肢の value に色名ではなく番号(0〜9)を渡す。色は、一意なラベル(名前)で引く
        assert "[props.opt.label]" in template and "[props.opt.value]" not in template
        for color in COLORS:
            assert f"'{COLOR_LABELS[color]}':'{COLOR_HEX[color]}'" in template  # 名前 → 色コード、10 色すべて
    await user.should_not_see(marker="settings-category-0-swatch")  # 別の色見本は置かない


async def test_choosing_a_color_changes_the_category_color(user: User) -> None:
    edits: list[CategoryEdit] = []
    mount_category_settings([Category("a", color="blue")], {}, [], edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-color").elements.pop().set_value("red")
    user.find(marker="settings-apply").click()
    assert edits[0].categories[0].color == "red"


async def test_unchanged_categories_do_not_call_on_categories(user: User) -> None:
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([Category("開発")], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert applied == [1] and edits == []


async def test_a_blank_added_category_row_is_ignored(user: User) -> None:
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-apply").click()
    assert applied == [1] and edits == []


@pytest.mark.parametrize(
    ("name", "message"),
    [("", "名前"), ("未定", "未定"), ("開発", "重複")],
)
async def test_invalid_categories_keep_the_dialog_and_call_nothing(user: User, name: str, message: str) -> None:
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([Category("開発")], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-category-1-name").type(name)
    user.find(marker="settings-category-1-prj").type("X")  # 名前が空でも、行を無視しない
    user.find(marker="settings-apply").click()
    await user.should_see(message)
    assert applied == [] and edits == []


async def test_renaming_a_category_keeps_its_id(user: User) -> None:
    category = Category("開発")
    edits: list[CategoryEdit] = []
    mount_category_settings([category], {}, [], edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-name").clear().type("開発(改)")
    user.find(marker="settings-apply").click()
    assert [(c.name, c.id) for c in edits[0].categories] == [("開発(改)", category.id)]
    assert edits[0].removed_ids == []


async def test_deleting_an_unused_category_needs_no_confirmation(user: User) -> None:
    category = Category("開発")
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([category], {}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-remove").click()
    user.find(marker="settings-apply").click()
    assert applied == [1]
    assert edits == [CategoryEdit([], [category.id])]


async def test_deleting_a_used_category_asks_first(user: User) -> None:
    category = Category("開発")
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([category], {category.id: 3}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-remove").click()
    user.find(marker="settings-apply").click()
    await user.should_see("削除するカテゴリを使っているタスクが3件あります。未定に戻ります。")
    assert applied == [] and edits == []
    user.find(marker="settings-confirm-delete").click()
    assert applied == [1]
    assert edits == [CategoryEdit([], [category.id])]


async def test_cancelling_the_confirmation_changes_nothing(user: User) -> None:
    category = Category("開発")
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([category], {category.id: 3}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-remove").click()
    user.find(marker="settings-apply").click()
    user.find(marker="settings-confirm-cancel").click()
    assert applied == [] and edits == []


async def test_template_and_category_deletions_are_confirmed_together(user: User) -> None:
    category = Category("開発")
    template = UrlTemplate("チケット", "https://example.com/{ID}")
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings(
        [category], {category.id: 2}, applied, edits, templates=[template], template_usage={"チケット": 4}
    )
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-remove").click()
    user.find(marker="settings-template-0-remove").click()
    user.find(marker="settings-apply").click()
    await user.should_see("削除するテンプレートを使っているリンクが4件あります。URL としてそのまま残ります。")
    await user.should_see("削除するカテゴリを使っているタスクが2件あります。未定に戻ります。")
    user.find(marker="settings-confirm-delete").click()
    assert applied == [1] and len(edits) == 1


def test_task_name_may_be_fifty_characters() -> None:
    assert make(name="あ" * 50).name == "あ" * 50


def test_task_name_over_fifty_characters_is_rejected() -> None:
    with pytest.raises(ValueError, match="50文字"):
        make(name="あ" * 51)


def test_task_name_length_is_checked_after_trimming() -> None:
    assert make(name=" " + "あ" * 50 + " ").name == "あ" * 50


@pytest.mark.parametrize("name", ["a\nb", "a\tb", "a\x00b", "a\x7fb", "a\u200bb", "a\ufeffb", "a\u2028b"])
def test_task_name_with_control_characters_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="制御文字"):
        make(name=name)


def test_a_trailing_newline_is_trimmed_not_rejected() -> None:
    assert make(name="設計\n").name == "設計"


def test_the_name_rules_apply_to_a_checkpoint_too() -> None:
    kwargs = {"kind": TaskKind.CHECKPOINT, "deadline": "2026-10-09T17:00", "status": Status.NOT_STARTED}
    with pytest.raises(ValueError, match="50文字"):
        make(name="あ" * 51, **kwargs)
    with pytest.raises(ValueError, match="制御文字"):
        make(name="a\nb", **kwargs)


async def test_deleting_a_used_category_and_adding_an_identical_row_still_applies(user: User) -> None:
    category = Category("開発", "業務", date(2026, 12, 31), "indigo", "P1")
    applied: list[int] = []
    edits: list[CategoryEdit] = []
    mount_category_settings([category], {category.id: 3}, applied, edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-0-remove").click()
    user.find(marker="settings-category-add").click()
    await asyncio.sleep(0.2)  # 行の描き直しを待つ
    user.find(marker="settings-category-0-name").type("開発")
    user.find(marker="settings-category-0-kind").type("業務")
    user.find(marker="settings-category-0-expiry").type("2026-12-31")
    user.find(marker="settings-category-0-color").elements.pop().set_value("indigo")
    user.find(marker="settings-category-0-prj").type("P1")
    user.find(marker="settings-apply").click()
    await user.should_see("削除するカテゴリを使っているタスクが3件あります。未定に戻ります。")
    user.find(marker="settings-confirm-delete").click()
    assert applied == [1]
    (edit,) = edits  # 確認の文言どおり、削除が適用される(内容が同じでも、別の id の新しいカテゴリ)
    assert edit.removed_ids == [category.id]
    assert edit.categories == [category] and edit.categories[0].id != category.id


@pytest.mark.parametrize(("part", "limit"), [("name", 30), ("kind", 20), ("prj", 20)])
async def test_category_inputs_are_cut_to_the_limit_in_characters(user: User, part: str, limit: int) -> None:
    mount_category_settings([Category("a")], {}, [], [])
    await user.open("/")
    user.find("open").click()
    field = user.find(marker=f"settings-category-0-{part}").elements.pop()
    assert field._props.get("maxlength") is None  # ブラウザの maxlength は UTF-16 単位で、文字数とずれる
    field.set_value("A" * (limit + 5))
    assert field.value == "A" * limit
    field.set_value("😀" * limit)  # 絵文字は 1 文字と数える(UTF-16 では 2 単位)
    assert field.value == "😀" * limit


async def test_a_cut_category_name_is_what_gets_applied(user: User) -> None:
    edits: list[CategoryEdit] = []
    mount_category_settings([], {}, [], edits)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-category-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-category-0-name").elements.pop().set_value("あ" * 40)
    user.find(marker="settings-apply").click()
    assert edits[0].categories[0].name == "あ" * 30


async def test_a_category_is_laid_out_in_two_rows_so_long_text_fits(user: User) -> None:
    mount_category_settings([Category("a")], {}, [], [])
    await user.open("/")
    user.find("open").click()

    def element(part: str):  # noqa: ANN202
        return user.find(marker=f"settings-category-0-{part}").elements.pop()

    first, second = element("name").parent_slot.parent, element("kind").parent_slot.parent
    assert first is not second
    assert element("color").parent_slot.parent is first and element("remove").parent_slot.parent is first
    assert element("expiry").parent_slot.parent is second and element("prj").parent_slot.parent is second
    assert first.parent_slot.parent is second.parent_slot.parent  # 1 つのカテゴリは、1 つのブロックにまとまる
    assert "grow" in element("name").classes  # 名前は、1 段目の残りの幅を使う(全角 30 文字)
    assert "grow" in element("kind").classes  # 種別は、2 段目の残りの幅を使う(全角 20 文字)
    assert "w-48" in element("prj").classes  # PRJコードは、半角 20 文字が収まる幅


TODAY = date(2026, 10, 15)


def test_build_event_list_normalizes_dates_and_color_and_sorts() -> None:
    rows = [
        EventRow(None, "10/20", "10/24", " リリース ", " Red "),
        EventRow("e1", "2026-10-01", "20261003", "休み", "gray"),
    ]
    built = build_event_list(rows, {"e1"}, TODAY)
    assert [(e.start, e.end, e.text, e.color) for e in built] == [
        (date(2026, 10, 1), date(2026, 10, 3), "休み", "gray"),
        (date(2026, 10, 20), date(2026, 10, 24), "リリース", "red"),
    ]
    assert built[0].id == "e1" and built[1].id not in {"e1", ""}


def test_event_row_is_open_by_default() -> None:
    assert EventRow(None, "10/20", "10/24", "x", "gray").closed is False


def test_build_event_list_carries_closed() -> None:
    rows = [EventRow(None, "10/26", "10/28", "夏季休業", "gray", True), EventRow(None, "10/1", "10/1", "x", "gray")]
    built = build_event_list(rows, set(), TODAY)
    assert [(e.text, e.closed) for e in built] == [("x", False), ("夏季休業", True)]


def test_build_event_list_does_not_roll_dates_into_next_year() -> None:
    (built,) = build_event_list([EventRow(None, "10/1", "10/2", "x", "red")], set(), TODAY)  # 10/1 は過ぎた日
    assert built.start == date(2026, 10, 1)


def test_build_event_list_ignores_a_blank_new_row_but_not_a_blank_existing_one() -> None:
    assert build_event_list([EventRow(None, "", "", "", "gray")], set(), TODAY) == []
    with pytest.raises(ValueError):
        build_event_list([EventRow("e1", "", "", "", "gray")], {"e1"}, TODAY)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (EventRow(None, "", "10/2", "x", "red"), "開始日"),
        (EventRow(None, "10/1", "", "x", "red"), "終了日"),
        (EventRow(None, "あした", "10/2", "x", "red"), "開始日"),
        (EventRow(None, "10/3", "10/2", "x", "red"), "終了日は開始日以降"),
        (EventRow(None, "10/1", "10/2", "", "red"), "文字列"),
        (EventRow(None, "10/1", "10/2", "あ" * 31, "red"), "30"),
        (EventRow(None, "10/1", "10/2", "x", "#ff00"), "色"),
        (EventRow(None, "10/1", "10/2", "x", "#ff0000ff"), "色"),
        (EventRow(None, "10/1", "10/2", "x", "transparent"), "色"),
        (EventRow(None, "10/1", "10/2", "x", ""), "色"),
    ],
)
def test_build_event_list_rejects_invalid_rows(row: EventRow, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_event_list([row], set(), TODAY)


def mount_event_settings(events: list[Event], applied: list[int], received: list[list[Event]]) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda h, s, m: applied.append(1),
                events=events,
                on_events=received.append,
                used_ids={e.id for e in events},
            ),
        )


async def test_adding_an_event_applies_it(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    mount_event_settings([], applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-event-0-start").type("2026-10-20")
    user.find(marker="settings-event-0-end").type("2026-10-24")
    user.find(marker="settings-event-0-text").type("リリース")
    user.find(marker="settings-event-0-color").elements.pop().set_value("Orange")
    user.find(marker="settings-apply").click()
    assert applied == [1]
    ((event,),) = received
    assert (event.start, event.end, event.text, event.color) == (date(2026, 10, 20), date(2026, 10, 24), "リリース", "orange")


async def test_closing_an_event_applies_it(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    mount_event_settings([], applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-event-0-start").type("2026-10-26")
    user.find(marker="settings-event-0-end").type("2026-10-28")
    user.find(marker="settings-event-0-text").type("夏季休業")
    user.find(marker="settings-event-0-closed").click()
    user.find(marker="settings-apply").click()
    assert applied == [1]
    ((event,),) = received
    assert event.closed is True


async def test_changing_only_closed_counts_as_an_event_change(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    existing = [Event(date(2026, 10, 26), date(2026, 10, 28), "夏季休業", "gray", id="e1")]
    mount_event_settings(existing, applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-0-closed").click()
    user.find(marker="settings-apply").click()
    assert [e.closed for e in received[0]] == [True]


async def test_event_color_field_is_a_color_input_that_takes_a_code(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    mount_event_settings([], applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-add").click()
    await asyncio.sleep(0.2)
    field = user.find(marker="settings-event-0-color").elements.pop()
    assert isinstance(field, ui.color_input)  # タスクの`色`と同じ、コードの入力と色の選択
    user.find(marker="settings-event-0-start").type("2026-10-20")
    user.find(marker="settings-event-0-end").type("2026-10-24")
    user.find(marker="settings-event-0-text").type("リリース")
    field.set_value("#FFAA00")
    user.find(marker="settings-apply").click()
    assert applied == [1]
    ((event,),) = received
    assert event.color == "#ffaa00"


async def test_event_swatch_follows_a_color_code_too(user: User) -> None:
    mount_event_settings([Event(date(2026, 10, 1), date(2026, 10, 2), "x", "red", id="e1")], [], [])
    await user.open("/")
    user.find("open").click()
    swatch = user.find(marker="settings-event-0-swatch").elements.pop()
    user.find(marker="settings-event-0-color").elements.pop().set_value("#12ab34")
    assert "#12ab34" in swatch._style["color"]


async def test_event_swatch_follows_the_color_text(user: User) -> None:
    mount_event_settings([Event(date(2026, 10, 1), date(2026, 10, 2), "x", "red", id="e1")], [], [])
    await user.open("/")
    user.find("open").click()
    swatch = user.find(marker="settings-event-0-swatch").elements.pop()
    assert "#ff0000" in swatch._style["color"]
    user.find(marker="settings-event-0-color").elements.pop().set_value("nonsense")
    assert swatch._style["color"] != "#ff0000"  # 不正な名前では、色を出さない(灰色)


async def test_removing_an_event_applies_the_rest(user: User) -> None:
    a = Event(date(2026, 10, 1), date(2026, 10, 2), "a", "red", id="e1")
    b = Event(date(2026, 10, 5), date(2026, 10, 6), "b", "blue", id="e2")
    received: list[list[Event]] = []
    mount_event_settings([a, b], [], received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-0-remove").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-apply").click()
    assert [e.id for e in received[0]] == ["e2"]


async def test_invalid_event_keeps_the_dialog_and_calls_nothing(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    mount_event_settings([], applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-event-0-start").type("10/20")
    user.find(marker="settings-event-0-end").type("10/10")
    user.find(marker="settings-event-0-text").type("x")
    user.find(marker="settings-apply").click()
    await user.should_see("終了日は開始日以降")
    assert applied == [] and received == []


async def test_unchanged_events_are_not_reapplied(user: User) -> None:
    received: list[list[Event]] = []
    mount_event_settings([Event(date(2026, 10, 1), date(2026, 10, 2), "a", "red", id="e1")], [], received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert received == []


def test_end_gap_hint_compares_calendar_days() -> None:
    computed = datetime(2026, 10, 13, 11, 0)
    assert end_gap_hint(datetime(2026, 10, 20, 9, 0), computed) == "算出値より 7 日遅い"
    assert end_gap_hint(datetime(2026, 10, 12, 18, 0), computed) == "算出値より 1 日前倒し"
    assert end_gap_hint(datetime(2026, 10, 13, 18, 0), computed) == "算出値と同じ日"
    assert end_gap_hint(None, computed) == ""
    assert end_gap_hint(computed, None) == ""


TODAY = date(2026, 10, 18)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-05", date(2026, 10, 5)),
        ("20261005", date(2026, 10, 5)),
        ("２０２６１００５", date(2026, 10, 5)),
        ("10/05", date(2026, 10, 5)),  # 年を省くと今年。過ぎた日でも翌年にしない
        ("2020-01-01", date(2020, 1, 1)),  # 過去の基準日も許可する
    ],
)
def test_build_base_date_reads_shortened_forms_and_keeps_past_days(text: str, expected: date) -> None:
    assert build_base_date(text, TODAY) == expected


@pytest.mark.parametrize("text", ["", "   ", "あした", "2026-02-30", "1999-12-31", "2101-01-01"])
def test_build_base_date_rejects_unreadable_or_out_of_range_days(text: str) -> None:
    with pytest.raises(ValueError, match="基準日"):
        build_base_date(text, TODAY)


async def test_settings_dialog_applies_the_base_date_only_when_given(user: User) -> None:
    bases: list[date] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: None, base_date=date(2026, 10, 5), on_base_date=bases.append
            ),
        )

    await user.open("/")
    user.find("open").click()
    assert user.find(marker="settings-base-date").elements.pop().value == "2026-10-05"
    user.find(marker="settings-base-date").clear().type("1020")
    user.find(marker="settings-apply").click()
    assert bases == [date(date.today().year, 10, 20)]  # 年を省くと今年


async def test_settings_dialog_rejects_a_bad_base_date_and_keeps_the_dialog(user: User) -> None:
    bases: list[date] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s, m: None, base_date=date(2026, 10, 5), on_base_date=bases.append
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-base-date").clear().type("あした")
    user.find(marker="settings-apply").click()
    await user.should_see("基準日")
    assert bases == []


async def test_settings_dialog_has_no_base_date_field_without_one(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s, m: None))

    await user.open("/")
    user.find("open").click()
    await user.should_not_see(marker="settings-base-date")


def test_build_task_for_a_summary_updates_only_the_shared_fields() -> None:
    existing = Task("m", id="m", kind=TaskKind.SUMMARY, children=["a"], color="#112233")
    built = make(existing, name=" 新 ", priority=Priority.HIGH, category_id="c", kind=TaskKind.SUMMARY, effort_hours=5.0,
                 status=Status.RUNNING, color="#ffffff")
    assert (built.kind, built.children, built.name, built.priority, built.category_id) == (
        TaskKind.SUMMARY, ["a"], "新", Priority.HIGH, "c",
    )
    assert (built.effort_hours, built.status, built.color, built.predecessors) == (0.0, Status.NOT_STARTED, "#112233", [])


def test_a_summary_cannot_be_made_from_a_form() -> None:
    with pytest.raises(ValueError, match="まとめ"):
        make(None, kind=TaskKind.SUMMARY)
    with pytest.raises(ValueError, match="まとめ"):
        make(Task("x"), kind=TaskKind.SUMMARY)


WORK_TODAY = date(2026, 10, 1)


def test_build_work_day_list_parses_shortcuts_sorts_and_skips_empty_rows() -> None:
    rows = [
        WorkDayRow("10/18", "930", "12", False),
        WorkDayRow("2026-10-17", "13:00", "16:00", False),
        WorkDayRow("", "", "", False),  # 完全に空の行は無視
        WorkDayRow("10/12", "", "", True),  # 休みは時刻を見ない
    ]
    built = build_work_day_list(rows, WORK_TODAY)
    assert [w.day for w in built] == [date(2026, 10, 12), date(2026, 10, 17), date(2026, 10, 18)]
    assert built[0].start is None and built[0].end is None
    assert (built[1].start, built[1].end) == (time(13), time(16))
    assert (built[2].start, built[2].end) == (time(9, 30), time(12))


@pytest.mark.parametrize(
    "row",
    [
        WorkDayRow("abc", "9", "10", False),  # 日付が読めない
        WorkDayRow("10/17", "", "10", False),  # 開始が空
        WorkDayRow("10/17", "9", "", False),  # 終了が空
        WorkDayRow("10/17", "25", "10", False),  # 時刻が範囲外
        WorkDayRow("10/17", "12", "9", False),  # 開始 > 終了
        WorkDayRow("10/17", "9", "9", False),  # 開始 = 終了
    ],
)
def test_build_work_day_list_rejects_bad_rows(row: WorkDayRow) -> None:
    with pytest.raises(ValueError):
        build_work_day_list([row], WORK_TODAY)


def test_build_work_day_list_rejects_a_duplicate_date() -> None:
    with pytest.raises(ValueError, match="重複"):
        build_work_day_list([WorkDayRow("10/17", "9", "10", False), WorkDayRow("2026-10-17", "", "", True)], WORK_TODAY)


def test_build_members_carries_work_day_rows_and_prefixes_errors_with_the_name() -> None:
    row = MemberRow("甲", "甲", 100.0, work_days=[WorkDayRow("10/17", "13", "16", False), WorkDayRow("10/18", "", "", True)])
    members, _ = build_members([row], ["甲"], lambda name: 0, today=WORK_TODAY)
    assert members[0].work_days == [WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 18))]
    bad = MemberRow("甲", "甲", 100.0, work_days=[WorkDayRow("10/17", "16", "13", False)])
    with pytest.raises(ValueError, match="甲"):
        build_members([bad], ["甲"], lambda name: 0, today=WORK_TODAY)


def test_member_columns_include_the_work_days_column() -> None:
    assert len(member_columns(0, False)) == 6  # アイコン・名前・比率・丸めない・稼働日・削除
    assert member_table_min_rem(0, False) > MEMBER_ICON_COLUMN_REM + MEMBER_NAME_COLUMN_REM + MEMBER_RATIO_COLUMN_REM


def test_build_task_takes_the_parameters_and_keeps_them_when_omitted() -> None:
    made = make(parameters=["P", "P", "Q"])
    assert made.parameters == ["P", "Q"]
    assert make(made).parameters == ["P", "Q"]  # 引数がなければ引き継ぐ
    assert make(made, parameters=[]).parameters == []  # 空を渡せば外す


def test_build_task_clears_the_parameters_of_a_checkpoint() -> None:
    made = make(kind=TaskKind.CHECKPOINT, deadline="2026-10-09T17:00", status=Status.NOT_STARTED, parameters=["P"])
    assert made.parameters == []


async def test_the_settings_dialog_reports_a_changed_reference_mode(user: User) -> None:
    applied: list[ReferenceMode] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda *a: None, reference_mode=ReferenceMode.LIVE, on_reference_mode=applied.append
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-reference-mode").elements.pop().set_value(ReferenceMode.SNAPSHOT.value)
    user.find(marker="settings-apply").click()
    assert applied == [ReferenceMode.SNAPSHOT]


async def test_the_stale_reference_dialog_offers_update_skip_and_cancel(user: User) -> None:
    done: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_stale_reference_dialog("基盤", lambda: done.append("update"), lambda: done.append("skip")))

    await user.open("/")
    for marker, expected in (("stale-update", ["update"]), ("stale-skip", ["update", "skip"]), ("stale-cancel", ["update", "skip"])):
        user.find("open").click()
        user.find(marker=marker).click()
        assert done == expected


async def test_the_settings_dialog_does_not_report_an_unchanged_reference_mode(user: User) -> None:
    applied: list[ReferenceMode] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda *a: None, reference_mode=ReferenceMode.LIVE, on_reference_mode=applied.append
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert applied == []


async def test_the_stale_snapshot_dialog_names_the_targets_and_offers_three_choices(user: User) -> None:
    done: list[str] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_stale_snapshot_dialog(
                ["基盤", "共通"], "保存", lambda: done.append("update"), lambda: done.append("skip")
            ),
        )

    await user.open("/")
    user.find("open").click()
    await user.should_see("「基盤」「共通」")
    await user.should_see("更新して保存")
    user.find(marker="snapshot-skip").click()
    assert done == ["skip"]


async def test_the_settings_dialog_reports_a_changed_plantuml_notice(user: User) -> None:
    applied: list[bool] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda *a: None, plantuml_notice=True, on_plantuml_notice=applied.append
            ),
        )

    await user.open("/")
    user.find("open").click()
    box = user.find(marker="settings-plantuml-notice").elements.pop()
    assert box.value is True
    box.set_value(False)
    user.find(marker="settings-apply").click()
    assert applied == [False]


async def test_the_settings_dialog_does_not_report_an_unchanged_plantuml_notice(user: User) -> None:
    applied: list[bool] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda *a: None, plantuml_notice=False, on_plantuml_notice=applied.append
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert applied == []


def test_effective_ratio_text_reports_a_limited_ratio() -> None:
    params = [Parameter(n, [Level("高", 0.5)]) for n in ("a", "b", "c")]
    row = MemberRow(None, "田中", 100.0, {"a": "高", "b": "高", "c": "高"})
    assert effective_ratio_text(row, params) == "相対比率 150%(範囲に丸めました)"
    text = effective_ratio_text(row, params, RatioLimits(upper=1.5))
    assert text == "相対比率 150%(相対比率 250% → 上限 150% に制限)"


def test_build_ratio_limits_reads_percent_text() -> None:
    assert build_ratio_limits("150", "50") == RatioLimits(upper=1.5, lower=0.5)
    assert build_ratio_limits("", "") == RatioLimits(None, None)
    assert build_ratio_limits(" 120 ", "80") == RatioLimits(upper=1.2, lower=0.8)
    assert build_ratio_limits("149.12345", "") == RatioLimits(upper=1.4912, lower=None)
    assert build_ratio_limits("100", "100") == RatioLimits(upper=1.0, lower=1.0)


@pytest.mark.parametrize(
    ("upper", "lower"),
    [
        ("abc", ""), ("", "x"), ("49", ""), ("151", ""), ("", "49"), ("", "151"), ("nan", ""), ("inf", ""),
        ("", "-inf"), ("", "-50"), ("100", "120"),
    ],
)
def test_build_ratio_limits_rejects_invalid_input(upper: str, lower: str) -> None:
    with pytest.raises(ValueError, match="上限|下限"):
        build_ratio_limits(upper, lower)


def _open_limits_dialog(limits: RatioLimits, applied: list[RatioLimits]) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda *a: None, ratio_limits=limits, on_ratio_limits=applied.append
            ),
        )


async def test_the_settings_dialog_reports_changed_ratio_limits(user: User) -> None:
    applied: list[RatioLimits] = []
    _open_limits_dialog(RatioLimits(), applied)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-limit-upper").elements.pop().set_value("150")
    user.find(marker="settings-limit-lower").elements.pop().set_value("50")
    user.find(marker="settings-apply").click()
    assert applied == [RatioLimits(upper=1.5, lower=0.5)]


async def test_the_preset_button_fills_fifty_to_one_fifty(user: User) -> None:
    _open_limits_dialog(RatioLimits(), [])
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-limit-preset").click()
    assert user.find(marker="settings-limit-upper").elements.pop().value == "150"
    assert user.find(marker="settings-limit-lower").elements.pop().value == "50"


async def test_the_settings_dialog_does_not_report_unchanged_ratio_limits(user: User) -> None:
    applied: list[RatioLimits] = []
    _open_limits_dialog(RatioLimits(upper=1.5), applied)
    await user.open("/")
    user.find("open").click()
    assert user.find(marker="settings-limit-upper").elements.pop().value == "150"
    user.find(marker="settings-apply").click()
    assert applied == []


async def test_an_invalid_ratio_limit_shows_an_error_and_keeps_the_dialog(user: User) -> None:
    applied: list[RatioLimits] = []
    _open_limits_dialog(RatioLimits(), applied)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-limit-upper").elements.pop().set_value("500")
    user.find(marker="settings-apply").click()
    assert applied == []
    await user.should_see("相対比率の上限")


def test_ratio_range_text_shows_the_configured_range_or_the_default() -> None:
    assert ratio_range_text(None) == "50〜150%"
    assert ratio_range_text(RatioLimits()) == "50〜150%"
    assert ratio_range_text(RatioLimits(upper=1.2, lower=0.8)) == "80〜120%"
    assert ratio_range_text(RatioLimits(upper=1.2)) == "50〜120%"
    assert ratio_range_text(RatioLimits(lower=0.8)) == "80〜150%"


def test_work_day_row_has_an_empty_note_by_default() -> None:
    assert WorkDayRow("10/17", "", "", True).note == ""


def test_build_work_day_list_carries_the_note_and_strips_it() -> None:
    rows = [WorkDayRow("10/17", "13", "16", False, " 通院 "), WorkDayRow("10/18", "", "", True, "夏季休暇")]
    built = build_work_day_list(rows, WORK_TODAY)
    assert [w.note for w in built] == ["通院", "夏季休暇"]


def test_a_row_with_only_a_note_is_not_ignored() -> None:
    with pytest.raises(ValueError, match="日付"):
        build_work_day_list([WorkDayRow("", "", "", False, "メモだけ")], WORK_TODAY)


def test_build_work_day_list_rejects_a_long_note() -> None:
    with pytest.raises(ValueError, match="メモ"):
        build_work_day_list([WorkDayRow("10/17", "", "", True, "あ" * 31)], WORK_TODAY)


def test_plan_work_day_range_adds_rest_rows_and_skips_registered_days() -> None:
    existing = [WorkDayRow("10/27", "", "", True)]
    plan = plan_work_day_range("10/26 〜 10/30", True, "", "", "夏季休暇", True, existing, {}, WORK_TODAY)
    assert [r.day for r in plan.rows] == ["2026-10-26", "2026-10-28", "2026-10-29", "2026-10-30"]
    assert all(r.rest and r.note == "夏季休暇" and r.start == "" and r.end == "" for r in plan.rows)
    assert (plan.registered, plan.off) == (1, 0)


def test_plan_work_day_range_with_a_window_formats_the_times() -> None:
    plan = plan_work_day_range("2026-10-26 〜 2026-10-26", False, "9", "1230", "", True, [], {}, WORK_TODAY)
    assert [(r.start, r.end, r.rest) for r in plan.rows] == [("09:00", "12:30", False)]


@pytest.mark.parametrize(
    ("period", "rest", "start", "end", "message"),
    [
        ("", True, "", "", "期間"),  # 空
        ("abc", True, "", "", "期間"),
        ("10/30 〜 10/26", True, "", "", "開始日"),  # 逆
        ("10/26 〜 10/30", False, "", "", "時刻"),  # 時間帯なのに時刻が空
        ("10/26 〜 10/30", False, "12", "9", "開始"),  # 逆
    ],
)
def test_plan_work_day_range_rejects_bad_input(period: str, rest: bool, start: str, end: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        plan_work_day_range(period, rest, start, end, "", True, [], {}, WORK_TODAY)


def test_plan_work_day_range_with_nothing_to_add_returns_no_rows() -> None:
    plan = plan_work_day_range("10/31 〜 11/1", True, "", "", "", True, [], {}, WORK_TODAY)  # 土日だけ
    assert plan.rows == [] and plan.off == 2


def test_work_day_range_summary() -> None:
    row = WorkDayRow("2026-10-26", "", "", True)
    assert work_day_range_summary(RangeAdd([row] * 3, 1, 2)) == "3 日を追加しました(1 日は登録済みのため飛ばしました。土日祝 2 日を除きました)"
    assert work_day_range_summary(RangeAdd([row], 0, 0)) == "1 日を追加しました"
    assert work_day_range_summary(RangeAdd([], 2, 0)) == "追加する日がありません(2 日は登録済みのため飛ばしました)"


def test_build_members_carries_memberships_and_checks_them() -> None:
    rows_ = [MemberRow(None, "甲", 100.0, teams=[Membership("a", 60), Membership("b", 40)])]
    members, _ = build_members(rows_, [], no_tasks, team_ids={"a", "b"})
    assert members[0].teams == [Membership("a", 60), Membership("b", 40)]


def test_build_members_rejects_a_bad_membership_with_the_member_name() -> None:
    rows_ = [MemberRow(None, "甲", 100.0, teams=[Membership("a", 60), Membership("b", 30)])]
    with pytest.raises(ValueError, match="甲: 所属の割合の合計を 100%"):
        build_members(rows_, [], no_tasks, team_ids={"a", "b"})


def test_build_members_rejects_a_membership_of_an_unknown_team() -> None:
    rows_ = [MemberRow(None, "甲", 100.0, teams=[Membership("zzz", 100)])]
    with pytest.raises(ValueError, match="存在しないチーム"):
        build_members(rows_, [], no_tasks, team_ids={"a"})


def test_member_columns_add_a_teams_column_only_when_asked() -> None:
    assert len(member_columns(0, False, True)) == len(member_columns(0, False)) + 1
    assert member_table_min_rem(0, False, True) > member_table_min_rem(0, False)
