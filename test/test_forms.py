from datetime import datetime, time

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.forms import (
    build_section_name,
    build_task,
    build_work_settings,
    compose_datetime,
    default_times,
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
)
from projectapp.models import Priority, Status, Task
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
        "assignee": "",
    }
    values.update(overrides)
    return build_task(existing, **values)  # type: ignore[arg-type]


def test_build_task_normalizes_input() -> None:
    task = make(name="  設計  ", assignee=" 佐藤 ")
    assert task.name == "設計"
    assert task.planned_start == datetime(2026, 10, 5, 9, 0)
    assert task.planned_end == datetime(2026, 10, 7, 18, 0)
    assert task.effort_hours == 8.0
    assert task.assignee == "佐藤"


def test_blank_assignee_and_dates_become_none() -> None:
    task = make(planned_start="", planned_end="", assignee="  ", effort_hours=None)
    assert (task.planned_start, task.planned_end, task.assignee, task.effort_hours) == (None, None, None, 0.0)


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
        make(planned_start="", planned_end=text)


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
    applied: list[tuple[float, time]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s: applied.append((h, s))
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
    assert applied == [(8.0, time(10, 0))]


async def test_settings_dialog_time_picker_and_field_stay_in_sync(user: User) -> None:
    applied: list[tuple[float, time]] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5, time(9, 0), lambda h, s: applied.append((h, s))
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
    assert applied == [(6.5, time(10, 15))]


async def test_clock_icon_opens_a_picker_dialog_and_ok_closes_it(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s: None))

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
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s: None))

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
        ui.button("open", on_click=lambda: open_settings_dialog(6.5, time(9, 0), lambda h, s: None))

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
        make(planned_end="2101-01-01T00:00")


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
            assignee="",
        )
