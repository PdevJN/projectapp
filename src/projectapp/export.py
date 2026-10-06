"""ガントチャートの PNG 出力。倍率・ファイル名・デコード・書き込みは、画面に依存しない関数にする。"""

import base64
import binascii
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from nicegui import app, ui

MAX_CANVAS_PX = 16384  # Safari 系のキャンバスの、1辺の上限
MAX_PIXEL_RATIO = 2.0
HTML_TO_IMAGE_URL = "/static/html-to-image.js"
STATIC_DIR = Path(__file__).parent / "static"
PNG_PREFIX = "data:image/png;base64,"
UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
CAPTURE_TIMEOUT_S = 90
# NiceGUI の websocket は、1 メッセージ約 1MB まで(engineio の既定)。画像は分けて受け取る
CAPTURE_CHUNK_CHARS = 200_000

# 画像化の間だけ当てる CSS。html-to-image は、各要素の計算済みの幅を px で複製に固定する(月の見出しは 26.7031px など)。
# 書き出しの文字の測り方が、画面とわずかに違うと、固定された幅に収まらず、月の見出しが折り返され(9月 → 9 / 月)、
# ProjectCode が省略される。折り返しを禁じ、チップは省略せずに、余白(左右 6px)へはみ出させる。
EXPORT_CSS = (
    "[data-chart-content] * { white-space: nowrap !important; } "
    "[data-chart-content] .code-chip { text-overflow: clip !important; overflow: visible !important; }"
)

# 画像化する。対象は data-chart-content の要素の全体(スクロールの外へはみ出す分を含む)。
# ライトは白、ダークは body の背景色。結果は window.__exportPng に置き、長さだけを返す(分けて取り出す)。
# 失敗は、例外にせず error の文字列で返す。
CAPTURE_JS = """
async () => {
  const root = document.querySelector('[data-chart-content]');
  if (!root) return JSON.stringify({error: '描画の対象が見つかりません'});
  if (typeof htmlToImage === 'undefined') return JSON.stringify({error: '画像化の部品を読み込めていません'});
  const dark = document.body.classList.contains('body--dark');
  const bg = dark ? getComputedStyle(document.body).backgroundColor : '#ffffff';
  const style = document.createElement('style');
  style.textContent = __CSS__;
  document.head.appendChild(style);
  try {
    window.__exportPng = await htmlToImage.toPng(root, {
      width: root.scrollWidth, height: root.scrollHeight,
      pixelRatio: __RATIO__, backgroundColor: bg, cacheBust: false,
    });
    return JSON.stringify({length: window.__exportPng.length});
  } catch (e) { return JSON.stringify({error: String(e)}); }
  finally { style.remove(); }
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


def parse_capture_meta(raw: str) -> int:
    """CAPTURE_JS の戻り値(JSON)から、画像のデータ URL の長さを取り出す。"""
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        raise ExportError("画像化の結果を読めません") from None
    if not isinstance(result, dict):
        raise ExportError("画像化の結果が正しくありません")
    if "error" in result:
        raise ExportError(str(result["error"]))
    length = result.get("length")
    if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
        raise ExportError("画像化の結果が正しくありません")
    return length


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


RunJs = Callable[..., Awaitable[Any]]


class NativeImageExporter:
    """ネイティブウィンドウ(pywebview)で、画面内の画像化と、保存ダイアログを使う。"""

    def __init__(self, run_js: RunJs | None = None) -> None:
        self.run_js: RunJs = run_js or ui.run_javascript  # テストでは、ブラウザの偽物に差し替える

    @property
    def available(self) -> bool:
        return app.native.main_window is not None

    async def capture(self, pixel_ratio: float) -> bytes:
        """画像化して、PNG のバイト列を返す。データ URL は、websocket の上限に収まる大きさに分けて受け取る。"""
        body = CAPTURE_JS.replace("__RATIO__", repr(float(pixel_ratio))).replace("__CSS__", json.dumps(EXPORT_CSS))
        script = f"({body})()"
        try:
            length = parse_capture_meta(await self.run_js(script, timeout=CAPTURE_TIMEOUT_S))
            parts: list[str] = []
            for start in range(0, length, CAPTURE_CHUNK_CHARS):
                end = start + CAPTURE_CHUNK_CHARS
                part = await self.run_js(
                    f"window.__exportPng.slice({start}, {end})", timeout=CAPTURE_TIMEOUT_S
                )
                if not isinstance(part, str):
                    raise ExportError("画像のデータを受け取れませんでした")
                parts.append(part)
            text = "".join(parts)
            if len(text) != length:
                raise ExportError("画像のデータが欠けています")
            return png_from_data_url(text)
        except TimeoutError:
            raise ExportError("画像化が時間内に終わりませんでした") from None
        finally:
            try:
                await self.run_js("delete window.__exportPng", timeout=5)
            except Exception:  # noqa: BLE001 後始末の失敗は、画像の結果に影響させない
                pass

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
