"""タスクのメモ(要望 150)の保存。`~/.projectapp/notes/<プロジェクト名>/<タスクid>.html`で、git 管理の外。NiceGUI に依存しない。"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from projectapp.storage import BASE_DIR, INVALID_NAME_CHARS

NOTES_ROOT = BASE_DIR / "notes"
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_TAGS = re.compile(r"<[^>]*>")


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


def load(name: str, task_id: str) -> str | None:
    path = _file(name, task_id)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None  # 読めないメモは、メモなしとして扱う


def save(name: str, task_id: str, html: str) -> None:
    """保存する。中身が空なら、ファイルを消す。書けないとき(OSError)は、何もしない。"""
    path = _file(name, task_id)
    if path is None:
        return
    if is_blank(html):
        delete(name, task_id)
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(html)
        os.replace(tmp.name, path)
    except OSError:
        return


def delete(name: str, task_id: str) -> str | None:
    """消して、消した中身を返す(なければ None)。"""
    html = load(name, task_id)
    path = _file(name, task_id)
    if path is not None:
        path.unlink(missing_ok=True)
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
