"""タスクのメモ(要望 150)の保存。`~/.projectapp/notes/<プロジェクト名>/<タスクid>.html`で、git 管理の外。NiceGUI に依存しない。"""

import os
import re
import shutil
import tempfile
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from projectapp.storage import BASE_DIR, INVALID_NAME_CHARS

NOTES_ROOT = BASE_DIR / "notes"
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_TAGS = re.compile(r"<[^>]*>")


# メモに残してよいタグ(`ui.editor`が出すもの)。ほかは、タグだけ外して中の文字は残す。属性は、リンクの href だけ
_ALLOWED = frozenset(
    "p br div span b strong i em u s strike del ul ol li a h1 h2 h3 h4 h5 h6 "
    "blockquote pre code hr sub sup".split()
)
_VOID = frozenset({"br", "hr"})
# タグごと、中身も捨てるもの(スクリプト・埋め込み・図・書式など)
_DROP = frozenset(
    "script style iframe frame frameset object embed applet template noscript "
    "svg math head title form textarea select option button audio video canvas".split()
)
_SAFE_SCHEMES = ("http:", "https:", "mailto:")
_CONTROL = re.compile(r"[\x00-\x20\x7f-\x9f\u200b-\u200f\u2028-\u202e\ufeff]")


class _Cleaner(HTMLParser):
    """許可したタグだけを残して書き直す(許可リスト方式)。イベント属性・style・javascript: は残さない。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self._skip = 0
        self._open: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP:
            self._skip += 1
        elif not self._skip and tag in _ALLOWED:
            self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")
            if tag not in _VOID:
                self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP or self._skip or tag not in _ALLOWED:
            return  # 自己終了の`<script/>`は中身がないので、深さを変えない
        self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")
        if tag not in _VOID:
            self.out.append(f"</{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP:
            self._skip = max(0, self._skip - 1)
        elif not self._skip and tag in self._open:
            while self._open:
                last = self._open.pop()
                self.out.append(f"</{last}>")
                if last == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.out.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if not self._skip and re.fullmatch(r"[A-Za-z0-9]{1,32}", name):
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip and re.fullmatch(r"[xX][0-9a-fA-F]{1,6}|[0-9]{1,7}", name):
            self.out.append(f"&#{name};")

    @staticmethod
    def _attrs(tag: str, attrs: list[tuple[str, str | None]]) -> str:
        if tag != "a":
            return ""
        for key, value in attrs:
            if key == "href" and value is not None:
                scheme = _CONTROL.sub("", value).lower()
                if scheme.startswith(_SAFE_SCHEMES):
                    return f' href="{escape(value.strip(), quote=True)}" rel="noopener noreferrer"'
        return ""

    def finish(self) -> str:
        self.close()
        while self._open:
            self.out.append(f"</{self._open.pop()}>")
        return "".join(self.out)


def sanitize(html: str) -> str:
    """メモの HTML を、許可したタグだけにする。読み込み・保存のたびに通し、他の端末のファイルの JavaScript を実行させない。"""
    cleaner = _Cleaner()
    cleaner.feed(html)
    return cleaner.finish()


def _folder(name: str) -> Path | None:
    """プロジェクトのメモのフォルダ。名前がフォルダ名に使えなければ None。"""
    if (
        not name
        or name in {".", ".."}
        or any(c in INVALID_NAME_CHARS or ord(c) < 32 or ord(c) == 127 for c in name)
    ):
        return None
    return NOTES_ROOT / name


def _file(name: str, task_id: str) -> Path | None:
    folder = _folder(name)
    if folder is None or not _ID.fullmatch(task_id):
        return None
    return folder / f"{task_id}.html"


def is_blank(html: str) -> bool:
    """タグと空白だけで、書いた中身がないか。"""
    return not _TAGS.sub("", html).replace("&nbsp;", " ").strip()


MAX_NOTE_TEXT = 10000  # 取り込む 1 件のメモの文字数の上限
_BLOCKS = frozenset(
    "p div ul ol li h1 h2 h3 h4 h5 h6 blockquote pre hr br".split()
)  # 前後で改行にするタグ
_ESCAPED = re.compile(r"\\([\\n])")


class _Plain(HTMLParser):
    """メモの HTML を、タグを落としたテキストにする(ブロックの境目は改行、リストの項目は`- `)。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def to_cell(html: str) -> str:
    """CSV のセルに入れる 1 行のテキスト。タグを落とし、`\\`を`\\\\`に、改行を文字の`\\n`にする。空のメモは空文字。"""
    if is_blank(html):
        return ""
    parser = _Plain()
    parser.feed(sanitize(html))
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ").replace("\r", "")
    lines = [line.rstrip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines).replace("\\", "\\\\").replace("\n", "\\n")


def from_cell(text: str) -> str:
    """`to_cell`の逆。`\\n`を改行に、`\\\\`を`\\`に戻し、1 行ごとの段落にする。タグとしては読まない。空なら空文字。"""
    text = text.strip()
    if not text:
        return ""
    plain = _ESCAPED.sub(lambda m: "\n" if m.group(1) == "n" else "\\", text)
    lines = plain[:MAX_NOTE_TEXT].split("\n")
    body = "".join(
        f"<p>{escape(line)}</p>" if line.strip() else "<p><br></p>" for line in lines
    )
    return sanitize(body)


def load(name: str, task_id: str) -> str | None:
    path = _file(name, task_id)
    if path is None:
        return None
    try:
        return sanitize(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None  # 読めないメモは、メモなしとして扱う


def save(name: str, task_id: str, html: str) -> bool:
    """保存する。中身が空なら、ファイルを消す。書けなかったら False(例外は出さない)。"""
    path = _file(name, task_id)
    if path is None:
        return False
    html = sanitize(html)
    if is_blank(html):
        delete(name, task_id)
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(html)
        os.replace(tmp.name, path)
    except OSError:
        return False
    return True


def exists(name: str) -> bool:
    """そのプロジェクトのメモのフォルダがあるか。"""
    folder = _folder(name)
    return folder is not None and folder.exists()


def remove_project(name: str) -> None:
    """プロジェクトのメモのフォルダを、中身ごと消す。使えない名前・消せないときは何もしない。"""
    folder = _folder(name)
    if folder is not None and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def delete(name: str, task_id: str) -> str | None:
    """消して、消した中身を返す(なければ None)。"""
    html = load(name, task_id)
    path = _file(name, task_id)
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass  # 消せないときも、画面へ例外を出さない
    return html


def note_ids(name: str) -> frozenset[str]:
    """メモのあるタスク id。"""
    folder = _folder(name)
    if folder is None or not folder.is_dir():
        return frozenset()
    return frozenset(p.stem for p in folder.glob("*.html") if _ID.fullmatch(p.stem))


def copy(name: str, src_id: str, dst_id: str) -> None:
    html = load(name, src_id)
    if html is not None:
        save(name, dst_id, html)


def copy_between(src_name: str, dst_name: str, task_ids: list[str]) -> None:
    """別のプロジェクトへ、指定したタスクのメモをコピーする(切り出し)。元にないものは作らない。"""
    for task_id in task_ids:
        html = load(src_name, task_id)
        if html is not None:
            save(dst_name, task_id, html)


def copy_many(name: str, pairs: list[tuple[str, str]]) -> None:
    for src_id, dst_id in pairs:
        copy(name, src_id, dst_id)


def copy_project(src_name: str, dst_name: str) -> None:
    """名前をつけて保存のとき、メモのフォルダを新しい名前へコピーする(元は残す)。"""
    src, dst = _folder(src_name), _folder(dst_name)
    if src is None or dst is None or src == dst or not src.is_dir():
        return
    try:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    except OSError:
        return


def rename_project(src_name: str, dst_name: str) -> None:
    """プロジェクト名の変更のとき、メモのフォルダを新しい名前へ移す。先に同名のフォルダがあれば`FileExistsError`。"""
    src, dst = _folder(src_name), _folder(dst_name)
    if src is None or dst is None or src == dst or not src.is_dir():
        return
    if dst.exists():
        raise FileExistsError(dst_name)
    src.rename(dst)


def sync(
    name: str, before: set[str], after: set[str], trash: dict[str, str]
) -> set[str]:
    """タスク id の増減に、メモを合わせる。消えた id のメモはごみ箱へ(元に戻すで書き戻す)。消えた id を返す。"""
    gone = before - after
    for task_id in gone:
        html = delete(name, task_id)
        if html is not None:
            trash[task_id] = html
    for task_id in after - before:
        html = trash.pop(task_id, None)
        if html is not None:
            save(name, task_id, html)
    return gone
