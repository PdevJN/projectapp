"""ガントチャートの PNG 出力。倍率・ファイル名・デコード・書き込みは、画面に依存しない関数にする。"""

import base64
import binascii
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Protocol

from nicegui import app, ui

MAX_CANVAS_PX = 16384  # Safari 系のキャンバスの、1辺の上限
MAX_PIXEL_RATIO = 2.0
HTML_TO_IMAGE_URL = "/static/html-to-image.js"
STATIC_DIR = Path(__file__).parent / "static"
PNG_PREFIX = "data:image/png;base64,"
UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
CAPTURE_TIMEOUT_S = 90

# 画像化する。対象は data-chart-content の要素の全体(スクロールの外へはみ出す分を含む)。
# ライトは白、ダークは body の背景色。失敗は、例外にせず error の文字列で返す。
CAPTURE_JS = """
async () => {
  const root = document.querySelector('[data-chart-content]');
  if (!root) return JSON.stringify({error: '描画の対象が見つかりません'});
  if (typeof htmlToImage === 'undefined') return JSON.stringify({error: '画像化の部品を読み込めていません'});
  const dark = document.body.classList.contains('body--dark');
  const bg = dark ? getComputedStyle(document.body).backgroundColor : '#ffffff';
  try {
    const url = await htmlToImage.toPng(root, {
      width: root.scrollWidth, height: root.scrollHeight,
      pixelRatio: __RATIO__, backgroundColor: bg, cacheBust: false,
    });
    return JSON.stringify({url});
  } catch (e) { return JSON.stringify({error: String(e)}); }
}
"""


class ExportError(Exception):
    """画像を作れなかった(画像化の失敗、不正な結果)。"""


def export_pixel_ratio(width: float) -> float:
    """倍率。画像の幅がキャンバスの上限を超えないようにする(最大 2)。"""
    if width <= 0:
        return MAX_PIXEL_RATIO
    return min(MAX_PIXEL_RATIO, MAX_CANVAS_PX / width)


def exceeds_canvas(width: float) -> bool:
    """倍率 1 でも、上限を超えるか(縮小して保存される)。"""
    return width > MAX_CANVAS_PX


def default_filename(project_name: str, today: date) -> str:
    """既定のファイル名 `<名前>_<YYYYMMDD>.png`。ファイル名に使えない文字は `_` にする。"""
    name = UNSAFE_NAME_CHARS.sub("_", project_name.strip()).lstrip(".")
    return f"{name or 'gantt'}_{today:%Y%m%d}.png"


def png_from_data_url(url: str) -> bytes:
    if not isinstance(url, str) or not url.startswith(PNG_PREFIX):
        raise ExportError("画像の形式が正しくありません")
    try:
        return base64.b64decode(url[len(PNG_PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        raise ExportError("画像のデータが正しくありません") from None


def parse_capture_result(raw: str) -> bytes:
    """CAPTURE_JS の戻り値(JSON)から、PNG のバイト列を取り出す。"""
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        raise ExportError("画像化の結果を読めません") from None
    if not isinstance(result, dict):
        raise ExportError("画像化の結果が正しくありません")
    if "error" in result:
        raise ExportError(str(result["error"]))
    if "url" not in result:
        raise ExportError("画像化の結果が正しくありません")
    return png_from_data_url(result["url"])


def write_png(path: Path, data: bytes) -> Path:
    """PNG を書く。拡張子がなければ .png を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    if not path.suffix:
        path = path.with_name(path.name + ".png")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".export-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


class ImageExporter(Protocol):
    """画像化と、保存先の選択。テストでは、偽物に差し替える。"""

    @property
    def available(self) -> bool: ...

    async def capture(self, pixel_ratio: float) -> bytes: ...

    async def ask_path(self, filename: str) -> Path | None: ...


class NativeImageExporter:
    """ネイティブウィンドウ(pywebview)で、画面内の画像化と、保存ダイアログを使う。"""

    @property
    def available(self) -> bool:
        return app.native.main_window is not None

    async def capture(self, pixel_ratio: float) -> bytes:
        script = f"({CAPTURE_JS.replace('__RATIO__', repr(float(pixel_ratio)))})()"
        try:
            raw = await ui.run_javascript(script, timeout=CAPTURE_TIMEOUT_S)
        except TimeoutError:
            raise ExportError("画像化が時間内に終わりませんでした") from None
        return parse_capture_result(raw)

    async def ask_path(self, filename: str) -> Path | None:
        import webview  # ネイティブのときだけ使う

        window = app.native.main_window
        if window is None:
            return None
        # WindowProxy のメソッドは、実行時に pywebview の Window から作られる(型の定義が静的に見えない)
        result = await window.create_file_dialog(  # ty: ignore[unresolved-attribute]
            dialog_type=webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=("PNG 画像 (*.png)",),
        )
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])


def register_static_files() -> None:
    """同梱の JS を配る。アプリの起動時に一度だけ呼ぶ。"""
    app.add_static_file(local_file=STATIC_DIR / "html-to-image.js", url_path=HTML_TO_IMAGE_URL)
