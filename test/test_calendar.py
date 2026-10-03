import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from projectapp.calendar import (
    DayKind,
    day_kind,
    load_cache,
    parse_holidays_csv,
    refresh_holidays,
    save_cache,
)

HEADER = "国民の祝日・休日月日,国民の祝日・休日名称\n"
CSV = (HEADER + "2026/1/1,元日\n2026/1/12,成人の日\n").encode("cp932")


def transport_returning(status: int, content: bytes) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, content=content))


def test_parse_holidays_csv() -> None:
    assert parse_holidays_csv(CSV) == {
        date(2026, 1, 1): "元日",
        date(2026, 1, 12): "成人の日",
    }


def test_parse_skips_broken_rows() -> None:
    raw = (HEADER + "abc,x\n2026/2/30,存在しない日\n2026/2/11,建国記念の日\n").encode("cp932")
    assert parse_holidays_csv(raw) == {date(2026, 2, 11): "建国記念の日"}


def test_parse_rejects_non_csv() -> None:
    with pytest.raises(ValueError):
        parse_holidays_csv(b"<html>error</html>")


def test_day_kind() -> None:
    holidays = {date(2026, 10, 4): "テスト祝日"}  # 日曜
    assert day_kind(date(2026, 10, 3), holidays) is DayKind.SATURDAY
    assert day_kind(date(2026, 10, 4), holidays) is DayKind.HOLIDAY
    assert day_kind(date(2026, 10, 11), holidays) is DayKind.SUNDAY
    assert day_kind(date(2026, 10, 5), holidays) is DayKind.WEEKDAY


def test_cache_roundtrip(tmp_path: Path) -> None:
    assert load_cache(tmp_path) is None
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    assert load_cache(tmp_path) == {date(2026, 1, 1): "元日"}


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"2026-13-45": "x"}'])
def test_broken_cache_is_treated_as_missing(tmp_path: Path, content: str) -> None:
    (tmp_path / "holidays.json").write_text(content, encoding="utf-8")
    assert load_cache(tmp_path) is None


async def test_refresh_fetches_and_saves(tmp_path: Path) -> None:
    result = await refresh_holidays(tmp_path, transport_returning(200, CSV))
    assert result[date(2026, 1, 1)] == "元日"
    saved = json.loads((tmp_path / "holidays.json").read_text(encoding="utf-8"))
    assert saved["2026-01-12"] == "成人の日"


async def test_refresh_http_error_keeps_cache(tmp_path: Path) -> None:
    save_cache({date(2026, 1, 1): "元日"}, tmp_path)
    with pytest.raises(httpx.HTTPError):
        await refresh_holidays(tmp_path, transport_returning(500, b""))
    assert load_cache(tmp_path) == {date(2026, 1, 1): "元日"}


async def test_refresh_non_csv_is_not_saved(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await refresh_holidays(tmp_path, transport_returning(200, b"<html>oops</html>"))
    assert not (tmp_path / "holidays.json").exists()
