from datetime import datetime
from pathlib import Path

import pytest

from projectapp.models import Status
from projectapp.overview import NodeKind, OverviewNode, layout_overview
from projectapp.overview_pdf import OverviewPdfError, find_font, render_pdf


def small_layout():
    root = OverviewNode(
        "r",
        "とても長い名前のセクション" * 5 + "😀",
        NodeKind.SECTION,
        Status.NOT_STARTED,
        progress=40,
        effort_hours=12.0,
        due=datetime(2026, 11, 20),
    )
    root.children = [OverviewNode("a", "設計", NodeKind.TASK, Status.DONE, late=True)]
    return layout_overview(root, True, True)


needs_font = pytest.mark.skipif(find_font() is None, reason="日本語フォントがない環境")


def test_find_font_skips_missing_files(tmp_path: Path) -> None:
    real = tmp_path / "f.ttf"
    real.write_bytes(b"x")
    assert find_font([str(tmp_path / "none.ttf"), str(real)]) == real
    assert find_font([str(tmp_path / "none.ttf")]) is None


def test_missing_font_is_refused_and_no_file_is_made(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    with pytest.raises(OverviewPdfError):
        render_pdf(small_layout(), out, font_path=tmp_path / "none.ttf")
    assert not out.exists()


@needs_font
def test_pdf_starts_with_the_pdf_header(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    assert render_pdf(small_layout(), out) == out
    assert out.read_bytes().startswith(b"%PDF")


@needs_font
def test_an_existing_file_is_replaced_and_no_temp_file_remains(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    out.write_bytes(b"old")
    render_pdf(small_layout(), out)
    assert out.read_bytes().startswith(b"%PDF")
    assert [p.name for p in tmp_path.iterdir()] == ["out.pdf"]
