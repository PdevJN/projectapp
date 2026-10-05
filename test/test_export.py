import asyncio
import base64
import json
import os
from datetime import date
from pathlib import Path

import pytest

from projectapp.export import (
    MAX_CANVAS_PX,
    ExportError,
    CAPTURE_CHUNK_CHARS,
    NativeImageExporter,
    default_filename,
    exceeds_canvas,
    export_pixel_ratio,
    parse_capture_meta,
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


def test_parse_capture_meta() -> None:
    assert parse_capture_meta(json.dumps({"length": 123})) == 123


def test_parse_capture_meta_reports_a_js_error() -> None:
    with pytest.raises(ExportError, match="boom"):
        parse_capture_meta(json.dumps({"error": "boom"}))


@pytest.mark.parametrize("bad", ["", "not json", "null", "[]", "{}", '{"length": 0}', '{"length": "9"}', '{"length": true}', '{"length": -3}'])
def test_parse_capture_meta_rejects_unexpected_values(bad: str) -> None:
    with pytest.raises(ExportError):
        parse_capture_meta(bad)


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


class FakeBrowser:
    """ui.run_javascript の偽物。window.__exportPng の保存と、slice による分割の取り出しを再現する。"""

    def __init__(self, data_url_text: str | None = None, error: str | None = None) -> None:
        self.data_url_text, self.error = data_url_text, error
        self.stored: str | None = None
        self.replies: list[int] = []
        self.scripts: list[str] = []

    async def __call__(self, script: str, timeout: float = 1.0) -> str | None:
        self.scripts.append(script)
        if "toPng" in script:
            if self.error is not None:
                return json.dumps({"error": self.error})
            self.stored = self.data_url_text
            return json.dumps({"length": len(self.stored or "")})
        if ".slice(" in script:
            start, end = script.split(".slice(")[1].rstrip(")").split(",")
            reply = (self.stored or "")[int(start) : int(end)]
            self.replies.append(len(reply))
            return reply
        if script.startswith("delete"):
            self.stored = None
            return None
        raise AssertionError(script)


def test_the_chunk_size_keeps_each_reply_under_the_websocket_limit() -> None:
    assert CAPTURE_CHUNK_CHARS * 4 < 1_000_000  # 日本語を含まない ASCII だが、余裕を見て上限の 1/4 以下にする


def test_a_large_image_is_received_in_chunks() -> None:
    big = b"\x89PNG" + os.urandom(3_000_000)  # 約 4MB の base64 = 上限(約 1MB)を大きく超える
    browser = FakeBrowser(data_url(big))
    result = asyncio.run(NativeImageExporter(run_js=browser).capture(2.0))
    assert result == big
    assert len(browser.replies) > 3
    assert max(browser.replies) <= CAPTURE_CHUNK_CHARS
    assert max(browser.replies) < 1_000_000  # どの応答も、websocket の上限の内側
    assert browser.stored is None  # 受け取ったあとは、ブラウザ側の保存を消す


def test_a_small_image_needs_one_chunk() -> None:
    browser = FakeBrowser(data_url())
    assert asyncio.run(NativeImageExporter(run_js=browser).capture(1.0)) == PNG
    assert len(browser.replies) == 1


def test_the_capture_script_gets_the_ratio_and_stores_the_result_instead_of_returning_it() -> None:
    browser = FakeBrowser(data_url())
    asyncio.run(NativeImageExporter(run_js=browser).capture(1.2345))
    script = browser.scripts[0]
    assert "pixelRatio: 1.2345" in script
    assert "window.__exportPng" in script
    assert "__RATIO__" not in script


def test_a_js_error_is_reported_and_nothing_is_fetched() -> None:
    browser = FakeBrowser(error="boom")
    with pytest.raises(ExportError, match="boom"):
        asyncio.run(NativeImageExporter(run_js=browser).capture(2.0))
    assert browser.replies == []


def test_a_truncated_transfer_is_rejected_and_the_browser_copy_is_deleted() -> None:
    class Truncating(FakeBrowser):
        async def __call__(self, script: str, timeout: float = 1.0) -> str | None:
            reply = await super().__call__(script, timeout)
            return reply[:-1] if ".slice(" in script and reply else reply  # 最後の 1 文字が欠ける

    browser = Truncating(data_url(b"\x89PNG" + os.urandom(2000)))
    with pytest.raises(ExportError):
        asyncio.run(NativeImageExporter(run_js=browser).capture(2.0))
    assert browser.stored is None


def test_a_timeout_in_a_chunk_is_reported_and_the_browser_copy_is_deleted() -> None:
    class Slow(FakeBrowser):
        async def __call__(self, script: str, timeout: float = 1.0) -> str | None:
            if ".slice(" in script:
                raise TimeoutError
            return await super().__call__(script, timeout)

    browser = Slow(data_url())
    with pytest.raises(ExportError, match="時間内"):
        asyncio.run(NativeImageExporter(run_js=browser).capture(2.0))
    assert browser.stored is None
