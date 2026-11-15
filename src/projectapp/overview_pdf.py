"""俯瞰図を PDF に書き出す。Pillow で画像に描き、PDF に包む。NiceGUI には依存しない。"""

import os
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from projectapp.gantt import STATUS_COLORS
from projectapp.overview import LINE_HEIGHT, PADDING, Layout

SCALE = 2  # 画面の 1 に対する、画像の倍率
MARGIN = 24
RESOLUTION = 72.0 * SCALE  # 1 単位が 1pt になる
LATE_COLOR = "#ef5350"  # 予定超過・期限超過の枠(gantt の行の背景は半透明なので使えない)
EDGE_COLOR = "#90a4ae"
BORDER_COLOR = "#b0bec5"

FONT_CANDIDATES = (
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothR.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
)


class OverviewPdfError(Exception):
    """PDF を作れない(フォントがない・書き込みに失敗など)。"""


def find_font(candidates: Sequence[str] = FONT_CANDIDATES) -> Path | None:
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _fit(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float
) -> str:
    """幅に収まるように、末尾を…で切る。"""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def render_pdf(layout: Layout, path: Path, font_path: Path | None = None) -> Path:
    font_file = font_path if font_path is not None else find_font()
    if font_file is None or not font_file.is_file():
        raise OverviewPdfError("日本語のフォントが見つからないため、PDF を作れません")
    try:
        font = ImageFont.truetype(str(font_file), 12 * SCALE)
    except OSError as exc:
        raise OverviewPdfError(f"フォントを読めません: {exc}") from exc
    size = (
        (layout.width + MARGIN * 2) * SCALE,
        (layout.height + MARGIN * 2) * SCALE,
    )
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)

    def at(value: float) -> float:
        return (value + MARGIN) * SCALE

    for edge in layout.edges:
        mid = (edge.x1 + edge.x2) / 2
        points = [
            (at(edge.x1), at(edge.y1)),
            (at(mid), at(edge.y1)),
            (at(mid), at(edge.y2)),
            (at(edge.x2), at(edge.y2)),
        ]
        draw.line(points, fill=EDGE_COLOR, width=SCALE)
    for item in layout.placed:
        node = item.node
        left, top = at(item.x), at(item.y)
        right, bottom = at(item.x + item.width), at(item.y + item.height)
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=4 * SCALE,
            fill="#ffffff",
            outline=LATE_COLOR if node.late else BORDER_COLOR,
            width=(2 if node.late else 1) * SCALE,
        )
        draw.rectangle(
            (left, top, left + 5 * SCALE, bottom), fill=STATUS_COLORS[node.status]
        )
        text_x = left + (PADDING + 4) * SCALE
        room = right - text_x - PADDING * SCALE
        for number, line in enumerate(item.lines):
            draw.text(
                (text_x, top + (PADDING + number * LINE_HEIGHT) * SCALE),
                _fit(draw, line, font, room),
                fill="#263238" if number == 0 else "#546e7a",
                font=font,
            )
    temp = path.with_name(f".{path.name}.tmp")
    try:
        image.save(temp, "PDF", resolution=RESOLUTION)
        os.replace(temp, path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise OverviewPdfError(f"保存できませんでした: {exc}") from exc
    return path
