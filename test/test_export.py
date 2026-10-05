import base64
import json
import os
from datetime import date
from pathlib import Path

import pytest

from projectapp.export import (
    MAX_CANVAS_PX,
    ExportError,
    NativeImageExporter,
    default_filename,
    exceeds_canvas,
    export_pixel_ratio,
    parse_capture_result,
    png_from_data_url,
    write_png,
)

PNG = b"\x89PNG\r\n\x1a\nbody"


def data_url(data: bytes = PNG) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


@pytest.mark.parametrize(
    ("width", "ratio"),
    [(0, 2.0), (-5, 2.0), (1880, 2.0), (8192, 2.0), (8193, 16384 / 8193), (15240, 16384 / 15240), (30480, 16384 / 30480)],
)
def test_pixel_ratio_never_exceeds_the_canvas(width: float, ratio: float) -> None:
    assert export_pixel_ratio(width) == pytest.approx(ratio)
    if width > 0:
        assert width * export_pixel_ratio(width) <= MAX_CANVAS_PX + 1e-6


def test_exceeds_canvas_at_ratio_one() -> None:
    assert not exceeds_canvas(16384)
    assert exceeds_canvas(16385)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("デモ", "デモ_20261005.png"),
        ("a/b\\c:d*e?f\"g<h>i|j", "a_b_c_d_e_f_g_h_i_j_20261005.png"),
        (".hidden", "hidden_20261005.png"),
        ("  ", "gantt_20261005.png"),
        ("", "gantt_20261005.png"),
        ("制御\x07文字", "制御_文字_20261005.png"),
    ],
)
def test_default_filename(name: str, expected: str) -> None:
    assert default_filename(name, date(2026, 10, 5)) == expected


def test_png_from_data_url() -> None:
    assert png_from_data_url(data_url()) == PNG


@pytest.mark.parametrize("bad", ["", "data:image/jpeg;base64,AAAA", "data:image/png;base64,***", "hello"])
def test_png_from_data_url_rejects_bad_input(bad: str) -> None:
    with pytest.raises(ExportError):
        png_from_data_url(bad)


def test_parse_capture_result() -> None:
    assert parse_capture_result(json.dumps({"url": data_url()})) == PNG


def test_parse_capture_result_reports_a_js_error() -> None:
    with pytest.raises(ExportError, match="boom"):
        parse_capture_result(json.dumps({"error": "boom"}))


@pytest.mark.parametrize("bad", ["", "not json", "null", "[]", "{}"])
def test_parse_capture_result_rejects_unexpected_values(bad: str) -> None:
    with pytest.raises(ExportError):
        parse_capture_result(bad)


def test_write_png_adds_the_extension_and_returns_the_path(tmp_path: Path) -> None:
    written = write_png(tmp_path / "chart", PNG)
    assert written == tmp_path / "chart.png"
    assert written.read_bytes() == PNG
    assert write_png(tmp_path / "other.PNG", PNG).name == "other.PNG"  # 大文字の拡張子はそのまま


def test_write_png_overwrites_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "chart.png"
    target.write_bytes(b"old")
    write_png(target, PNG)
    assert target.read_bytes() == PNG


def test_write_png_leaves_no_partial_file_when_the_directory_is_missing(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        write_png(tmp_path / "missing" / "chart.png", PNG)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root は書き込み禁止を無視する")
def test_write_png_leaves_nothing_when_the_directory_is_read_only(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(OSError):
            write_png(locked / "chart.png", PNG)
    finally:
        locked.chmod(0o700)
    assert list(locked.iterdir()) == []


def test_the_native_exporter_is_unavailable_outside_the_native_window() -> None:
    assert NativeImageExporter().available is False
