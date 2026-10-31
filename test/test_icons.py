import base64
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from projectapp.icons import (
    DATA_PREFIX,
    ICON_SIZE,
    MAX_ICON_BYTES,
    MAX_SOURCE_BYTES,
    IconError,
    is_valid_icon,
    load_icon,
    make_icon,
)


def decode(uri: str) -> Image.Image:
    assert uri.startswith(DATA_PREFIX)
    return Image.open(io.BytesIO(base64.b64decode(uri[len(DATA_PREFIX) :])))


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "GIF", "WEBP"])
def test_make_icon_accepts_each_format_and_returns_a_128_square_png(
    make_png, fmt: str
) -> None:
    image = decode(make_icon(make_png((300, 200), fmt=fmt)))
    assert image.format == "PNG" and image.size == (ICON_SIZE, ICON_SIZE)


def test_make_icon_crops_the_center_of_a_wide_image() -> None:
    wide = Image.new("RGBA", (300, 100), (255, 0, 0, 255))
    wide.paste(
        (0, 0, 255, 255), (250, 0, 300, 100)
    )  # 右端だけ青。中央の切り抜き(100〜200)には入らない
    buffer = io.BytesIO()
    wide.save(buffer, "PNG")
    image = decode(make_icon(buffer.getvalue())).convert("RGBA")
    assert image.getpixel((2, 64))[:3] == (255, 0, 0) and image.getpixel((125, 64))[
        :3
    ] == (255, 0, 0)


def test_make_icon_keeps_transparency(make_png) -> None:
    image = decode(make_icon(make_png((50, 50), (0, 0, 0, 0)))).convert("RGBA")
    assert image.getpixel((0, 0))[3] == 0


def test_make_icon_applies_the_exif_orientation() -> None:
    source = Image.new("RGB", (100, 50), (255, 0, 0))
    source.paste((0, 0, 255), (50, 0, 100, 50))  # 左が赤・右が青
    exif = Image.Exif()
    exif[0x0112] = 6  # 時計回りに 90 度回して表示する
    buffer = io.BytesIO()
    source.save(buffer, "JPEG", quality=95, exif=exif)
    image = decode(make_icon(buffer.getvalue())).convert("RGB")
    top, bottom = image.getpixel((64, 8)), image.getpixel((64, 119))
    left, right = image.getpixel((8, 64)), image.getpixel((119, 64))
    assert abs(top[0] - bottom[0]) > 100  # 回したので、赤と青は上下に分かれる
    assert abs(left[0] - right[0]) < 40


def test_make_icon_converts_a_palette_gif_and_a_cmyk_jpeg() -> None:
    buffer = io.BytesIO()
    Image.new("P", (40, 40), 3).save(buffer, "GIF")
    assert decode(make_icon(buffer.getvalue())).size == (ICON_SIZE, ICON_SIZE)
    buffer = io.BytesIO()
    Image.new("CMYK", (40, 40), (0, 255, 255, 0)).save(buffer, "JPEG")
    assert decode(make_icon(buffer.getvalue())).size == (ICON_SIZE, ICON_SIZE)


def test_make_icon_uses_the_first_frame_of_an_animation() -> None:
    frames = [Image.new("RGB", (30, 30), color) for color in ((255, 0, 0), (0, 0, 255))]
    buffer = io.BytesIO()
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:])
    assert (
        decode(make_icon(buffer.getvalue())).convert("RGB").getpixel((64, 64))[0] > 200
    )


def test_make_icon_scales_up_a_tiny_image(make_png) -> None:
    assert decode(make_icon(make_png((1, 1)))).size == (ICON_SIZE, ICON_SIZE)
    assert decode(make_icon(make_png((10, 400)))).size == (ICON_SIZE, ICON_SIZE)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"\x89PNG\r\n\x1a\nbroken",
    ],
)
def test_make_icon_rejects_what_is_not_a_supported_image(data: bytes) -> None:
    with pytest.raises(IconError):
        make_icon(data)


def test_make_icon_rejects_a_bmp() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, "BMP")
    with pytest.raises(IconError, match="形式"):
        make_icon(buffer.getvalue())


def test_make_icon_rejects_an_oversized_source() -> None:
    with pytest.raises(IconError, match="10MB"):
        make_icon(b"\0" * (MAX_SOURCE_BYTES + 1))


def test_make_icon_rejects_a_huge_pixel_count_without_loading_it() -> None:
    bomb = io.BytesIO()
    Image.new("1", (20000, 20000)).save(bomb, "PNG")  # 小さなファイルで 4 億画素
    assert len(bomb.getvalue()) < MAX_SOURCE_BYTES
    with pytest.raises(IconError):
        make_icon(bomb.getvalue())


def test_the_icon_stays_within_the_size_limit_even_for_noise() -> None:
    noise = Image.frombytes("RGBA", (400, 400), os.urandom(400 * 400 * 4))
    buffer = io.BytesIO()
    noise.save(buffer, "PNG")
    try:
        uri = make_icon(buffer.getvalue())
    except IconError:
        return  # 64KB を超えるときは、拒否でよい
    assert len(base64.b64decode(uri[len(DATA_PREFIX) :])) <= MAX_ICON_BYTES


def test_load_icon_reads_a_file_and_reports_a_missing_one(
    tmp_path: Path, make_png
) -> None:
    path = tmp_path / "a.png"
    path.write_bytes(make_png())
    assert is_valid_icon(load_icon(path))
    with pytest.raises(OSError):
        load_icon(tmp_path / "missing.png")


def test_load_icon_rejects_a_big_file_before_reading_it(tmp_path: Path) -> None:
    path = tmp_path / "big.png"
    with path.open("wb") as file:
        file.truncate(MAX_SOURCE_BYTES + 1)
    with pytest.raises(IconError, match="10MB"):
        load_icon(path)


def test_is_valid_icon(icon: str) -> None:
    assert is_valid_icon(icon)
    body = icon[len(DATA_PREFIX) :]
    assert not is_valid_icon("")
    assert not is_valid_icon("https://example.com/a.png")
    assert not is_valid_icon("data:image/jpeg;base64," + body)
    assert not is_valid_icon(DATA_PREFIX + "!!!not base64!!!")
    assert not is_valid_icon(DATA_PREFIX + base64.b64encode(b"not a png").decode())
    assert not is_valid_icon(
        DATA_PREFIX + base64.b64encode(b"\0" * (MAX_ICON_BYTES + 1)).decode()
    )
    assert not is_valid_icon(DATA_PREFIX + body[: len(body) // 2])  # 途中で切れた PNG


def crafted_png(width: int, height: int, idat: bytes) -> bytes:
    """画素数を偽った PNG(IHDR の大きさだけ大きい。CRC は合っている)。"""
    import struct
    import zlib

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + tag
            + body
            + struct.pack(">I", zlib.crc32(tag + body))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def as_icon(raw: bytes) -> str:
    return DATA_PREFIX + base64.b64encode(raw).decode()


@pytest.mark.parametrize("size", [(20000, 20000), (60000, 60000)])
def test_is_valid_icon_rejects_a_huge_declared_size_without_raising(
    size: tuple[int, int],
) -> None:
    import zlib

    assert (
        is_valid_icon(as_icon(crafted_png(*size, zlib.compress(b"\0" * 100)))) is False
    )


def test_is_valid_icon_rejects_a_png_that_is_not_128_square(make_png) -> None:
    assert is_valid_icon(as_icon(make_png((64, 64)))) is False


def test_is_valid_icon_rejects_a_png_whose_pixels_cannot_be_decoded(icon: str) -> None:
    import struct
    import zlib

    raw = bytearray(base64.b64decode(icon[len(DATA_PREFIX) :]))
    start = raw.index(b"IDAT") + 4
    length = struct.unpack(">I", raw[start - 8 : start - 4])[0]
    body = bytes(
        b ^ 0xFF for b in raw[start : start + length]
    )  # 中身を壊し、CRC は合わせ直す
    raw[start : start + length] = body
    raw[start + length : start + length + 4] = struct.pack(
        ">I", zlib.crc32(b"IDAT" + body)
    )
    assert is_valid_icon(as_icon(bytes(raw))) is False
