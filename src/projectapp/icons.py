"""メンバーのアイコン。画像のバイト列を 128×128 の PNG の data URI にする(UI に依存しない)。"""

import base64
import binascii
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ICON_SIZE = 128
MAX_SOURCE_BYTES = 10 * 1024 * 1024  # 取り込む元ファイルの上限
MAX_ICON_BYTES = 64 * 1024  # 保存するアイコン(デコード後)の上限
MAX_PIXELS = 40_000_000  # 元画像の画素数の上限(小さなファイルで巨大な画像を作る攻撃を避ける)
DATA_PREFIX = "data:image/png;base64,"
ICON_FILE_TYPES = ("画像ファイル (*.png;*.jpg;*.jpeg;*.gif;*.webp)",)
SOURCE_FORMATS = {"PNG", "JPEG", "GIF", "WEBP"}  # SVG は取り込まない


class IconError(ValueError):
    """アイコンにできない画像。文面は、そのまま通知に出せる。"""


def make_icon(data: bytes) -> str:
    """画像のバイト列を、中央を正方形に切り抜いて 128×128 にした PNG の data URI にする。"""
    if not data:
        raise IconError("画像が空です")
    if len(data) > MAX_SOURCE_BYTES:
        raise IconError("画像が大きすぎます(10MBまで)")
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in SOURCE_FORMATS:
            raise IconError("PNG・JPEG・GIF・WebP の画像を選んでください(対応しない形式です)")
        if image.width * image.height > MAX_PIXELS:
            raise IconError("画像の画素数が多すぎます")
        image.load()  # 最初のフレームだけ読む(アニメーションでも)
        square = ImageOps.fit(
            ImageOps.exif_transpose(image).convert("RGBA"), (ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS
        )
    except IconError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise IconError("画像として読めません") from exc
    buffer = io.BytesIO()
    square.save(buffer, "PNG", optimize=True)
    raw = buffer.getvalue()
    if len(raw) > MAX_ICON_BYTES:
        raise IconError("アイコンの画像が複雑すぎます(縮小しても64KBを超えます)")
    return DATA_PREFIX + base64.b64encode(raw).decode("ascii")


def load_icon(path: Path) -> str:
    """ファイルからアイコンを作る。読めなければ OSError、画像にできなければ IconError。"""
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise IconError("画像が大きすぎます(10MBまで)")
    return make_icon(path.read_bytes())


@lru_cache(maxsize=256)
def is_valid_icon(value: str) -> bool:
    """保存してよいアイコンか(PNG の data URI で、64KB 以下で、PNG として読める)。表示のたびに呼ぶので、結果を覚える。"""
    if not value.startswith(DATA_PREFIX) or len(value) > len(DATA_PREFIX) + MAX_ICON_BYTES * 4 // 3 + 4:
        return False
    try:
        raw = base64.b64decode(value[len(DATA_PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        return False
    if not raw or len(raw) > MAX_ICON_BYTES:
        return False
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
            return image.format == "PNG"
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return False
