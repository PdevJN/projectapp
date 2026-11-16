import json
from datetime import time

import pytest

from projectapp.forms import ActualTimePolicy, build_actuals, fill_actual_times
from projectapp.merge import SETTING_LABELS
from projectapp.models import FORMAT_VERSION, Project
from projectapp.storage import dumps_project, parse_project

START = time(9, 0)


def fill(sd="", sc="", ed="", ec="", *, optional=True, work_start=START, hours=6.5):
    return fill_actual_times(
        sd, sc, ed, ec, optional=optional, work_start=work_start, daily_hours=hours
    )


def test_both_empty_means_no_actual() -> None:
    assert fill() == ("", "")


def test_a_date_and_a_time_are_kept_as_typed() -> None:
    assert fill("2026-10-05", "09:15", "2026-10-05", "17:45") == (
        "2026-10-05T09:15",
        "2026-10-05T17:45",
    )


def test_a_date_only_start_gets_the_start_of_the_day() -> None:
    assert fill("2026-10-05") == ("2026-10-05T09:00", "")


def test_a_date_only_end_gets_the_start_of_the_day_plus_the_daily_hours() -> None:
    assert fill("2026-10-05", "", "2026-10-06") == (
        "2026-10-05T09:00",
        "2026-10-06T15:30",
    )


def test_the_date_is_normalized_like_the_typed_one() -> None:
    assert fill("2026-10-5", "", "2026-10-6")[0] == "2026-10-05T09:00"


def test_an_end_that_crosses_midnight_moves_to_the_next_day() -> None:
    assert fill("2026-10-05", "", "2026-10-05", work_start=time(22, 0), hours=8.0) == (
        "2026-10-05T22:00",
        "2026-10-06T06:00",
    )


def test_a_filled_end_before_an_explicit_start_is_raised_to_the_start() -> None:
    # 開始 18:00 を明示、終了は日付だけ(補うと 15:30)→ 開始に揃える
    assert fill("2026-10-05", "18:00", "2026-10-05") == (
        "2026-10-05T18:00",
        "2026-10-05T18:00",
    )


def test_a_filled_end_on_an_earlier_date_than_the_start_is_left_for_build_actuals_to_refuse() -> (
    None
):
    start, end = fill("2026-10-05", "", "2026-10-04")
    assert (start, end) == ("2026-10-05T09:00", "2026-10-04T15:30")
    with pytest.raises(ValueError):
        build_actuals(start, end)


def test_an_explicit_end_before_the_start_is_left_for_build_actuals_to_refuse() -> None:
    start, end = fill("2026-10-05", "18:00", "2026-10-05", "17:00")
    assert (start, end) == ("2026-10-05T18:00", "2026-10-05T17:00")
    with pytest.raises(ValueError):
        build_actuals(start, end)


def test_a_filled_start_after_an_explicit_end_is_lowered_to_the_end() -> None:
    # 開始は日付だけ(補うと 09:00)、終了に 08:00 を明示 → 開始を終了に揃える
    assert fill("2026-10-05", "", "2026-10-05", "08:00") == (
        "2026-10-05T08:00",
        "2026-10-05T08:00",
    )


def test_a_time_without_a_date_is_an_error_even_when_optional() -> None:
    with pytest.raises(ValueError, match="日付を入れてください"):
        fill("", "09:00")
    with pytest.raises(ValueError, match="日付を入れてください"):
        fill("2026-10-05", "", "", "17:00")


def test_required_keeps_the_old_rule() -> None:
    assert fill("2026-10-05", "09:00", optional=False) == ("2026-10-05T09:00", "")
    for args in (("2026-10-05",), ("", "09:00"), ("2026-10-05", "09:00", "2026-10-06")):
        with pytest.raises(ValueError, match="日付と時刻を両方入れてください"):
            fill(*args, optional=False)


def test_a_bad_date_is_reported_by_build_actuals_not_by_the_filler() -> None:
    start, end = fill("2026-13-45")
    with pytest.raises(ValueError, match="形式"):
        build_actuals(start, end)


def test_a_bad_time_is_reported() -> None:
    with pytest.raises(ValueError, match="時刻の形式"):
        fill("2026-10-05", "9時")


def test_the_policy_delegates_and_makes_hints() -> None:
    policy = ActualTimePolicy(True, time(9, 0), 6.5)
    assert policy.fill("2026-10-05", "", "", "") == ("2026-10-05T09:00", "")
    assert policy.start_hint() == "省略: 始業 09:00"
    assert policy.end_hint() == "省略: 終業 15:30"


def test_the_end_hint_names_the_next_day_when_it_crosses_midnight() -> None:
    assert ActualTimePolicy(True, time(22, 0), 8.0).end_hint() == "省略: 終業 翌 06:00"


def test_a_required_policy_has_no_hints() -> None:
    policy = ActualTimePolicy(False)
    assert policy.start_hint() == "" and policy.end_hint() == ""
    with pytest.raises(ValueError):
        policy.fill("2026-10-05", "", "", "")


def test_the_option_defaults_to_optional_and_the_version_is_23() -> None:
    assert Project("p").actual_time_optional is True
    assert FORMAT_VERSION == 23


def test_the_option_is_saved_and_read_back() -> None:
    for value in (True, False):
        project = Project("p", actual_time_optional=value)
        text = dumps_project(project)
        assert json.loads(text)["actual_time_optional"] is value
        assert parse_project(text, "p").actual_time_optional is value


def test_a_file_without_the_key_reads_as_optional() -> None:
    raw = json.loads(dumps_project(Project("p", actual_time_optional=False)))
    del raw["actual_time_optional"]
    raw["version"] = 22
    assert parse_project(json.dumps(raw), "p").actual_time_optional is True


@pytest.mark.parametrize("bad", [None, "yes", 1])
def test_a_non_boolean_value_is_refused(bad) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["actual_time_optional"] = bad
    with pytest.raises(ValueError, match="実績の時刻の省略"):
        parse_project(json.dumps(raw), "p")


def test_a_newer_version_is_still_refused() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = FORMAT_VERSION + 1
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_the_option_is_one_of_the_three_way_merge_settings() -> None:
    assert SETTING_LABELS["actual_time_optional"] == "実績の時刻の省略"


def test_the_end_hint_counts_days_when_it_is_two_or_more_days_ahead() -> None:
    assert ActualTimePolicy(True, time(9, 0), 30.0).end_hint() == "省略: 終業 翌 15:00"
    assert (
        ActualTimePolicy(True, time(9, 0), 60.0).end_hint() == "省略: 終業 2日後 21:00"
    )
