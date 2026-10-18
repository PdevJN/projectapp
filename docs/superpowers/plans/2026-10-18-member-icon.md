# メンバーのアイコン 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メンバーに画像のアイコンを設定でき、設定されていればガントチャートの担当者チップ・ダッシュボードの人ごとの負荷・プレビュー・PNG に出す。

**Architecture:** 画像の縮小と検証は、UI から切り離した純粋関数 `icons.py`(Pillow)に置く。アイコンは `Member.icon` に 128×128 PNG の data URI で持ち、プロジェクトのファイル(`version` 7)に埋め込む。表示は小さな部品 `avatar.py` の `avatar()` に集め、アイコンがなければ今の頭文字のチップを出す。

**Tech Stack:** Python 3.13、NiceGUI 3.17、Pillow(新規の依存)、pytest、ty。

**Spec:** `docs/superpowers/specs/2026-10-18-member-icon-design.md`

## Global Constraints

- 取り込む形式は PNG・JPEG・GIF・WebP。SVG は取り込まない。
- 取り込むと、中央を正方形に切り抜き、128×128 の PNG にする(透過は保つ)。
- 元ファイルは 10MB まで。保存するアイコンのデコード後の大きさは 64KB 以下。
- 値は `data:image/png;base64,<base64>` の形に限る。不正な値は読込を拒否する(ファイル形式の方針)。
- `FORMAT_VERSION` は 7。キーのない古いファイル(`version` 6 以下)は、アイコンなしとして読む。このアプリより新しい `version` は拒否したまま。
- `選ぶ`はネイティブウィンドウのときだけ出す(`MainView.exporter.available`)。
- 担当者向けファイル(`todos.json`)と PlantUML の出力、タスクの編集ダイアログの担当者の選択、担当者フィルタには出さない。
- すべての関数に型ヒント(引数と戻り値)。コメントは3行以内。`ty check` を通す。
- 日本語の文面・コメントで書く。既存のコードの密度・命名に合わせる。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- 作業ブランチは `feature/member-icon`(設計書のコミット済み)。

## Review Focus

- 画素数が巨大な画像(decompression bomb): 固まらず、理由つきで拒否する(Task 1)。
- EXIF の向きつきの JPEG・パレット GIF・CMYK JPEG・透過 PNG: 向きを直し、RGBA の PNG にして、透過を保つ(Task 1)。
- 名前が空の行・1 文字目が絵文字の名前: アイコンなしのとき、例外なく頭文字(または `?`)を出す(Task 3)。
- 壊れたアイコン値(手で書き換えたファイルを除き、読込で拒否済みのはずの値)がメモリ上にあっても、表示は頭文字に戻る(Task 3)。
- アイコンを設定したメンバーの改名・削除・元に戻す・キャンセル: 改名で残り、キャンセルで破棄され、`●` が出て、Undo で戻る(Task 4)。
- 同名メンバーの統合(`名前 (2)` への改名)でも、アイコンが落ちない(Task 2)。

---

## File Structure

| ファイル | 責務 |
| --- | --- |
| `src/projectapp/icons.py`(新規) | 画像のバイト列 → data URI(縮小・検証)、data URI の検証。UI に依存しない |
| `src/projectapp/avatar.py`(新規) | 丸いアイコン(なければ頭文字)を出す NiceGUI の部品 |
| `src/projectapp/models.py` | `Member.icon`、`FORMAT_VERSION = 7` |
| `src/projectapp/storage.py` | `icon` の読込の検証(`version` 7 以上)。書出しは `asdict` で入る |
| `src/projectapp/merge.py` | メンバーの項目に `icon` を足す |
| `src/projectapp/gantt.py` | 担当者チップを `avatar()` に置き換える |
| `src/projectapp/dashboard_view.py` | 人ごとの負荷の行に `avatar()` を出す |
| `src/projectapp/forms.py` | `MemberRow.icon`、`build_members`、メンバーの表のアイコン列 |
| `src/projectapp/views.py` | `pick_member_icon`、ダイアログへの配線、ガント・ダッシュボードへのアイコンの受け渡し |
| `test/conftest.py` | `png_bytes`(画像のバイト列を作る)、`icon`(有効な data URI)のフィクスチャ |

---

### Task 1: 依存と `icons.py`(縮小・検証)

**Files:**
- Modify: `pyproject.toml`(`uv add pillow`)
- Create: `src/projectapp/icons.py`
- Modify: `test/conftest.py`
- Test: `test/test_icons.py`(新規)

**Interfaces:**
- Produces:
  - `ICON_SIZE: int = 128`、`MAX_SOURCE_BYTES: int = 10 * 1024 * 1024`、`MAX_ICON_BYTES: int = 64 * 1024`、`DATA_PREFIX: str = "data:image/png;base64,"`
  - `ICON_FILE_TYPES: tuple[str, ...]`(ファイル選択の絞り込み)
  - `class IconError(ValueError)`
  - `make_icon(data: bytes) -> str`(取り込めなければ `IconError`)
  - `load_icon(path: Path) -> str`(`OSError` と `IconError`)
  - `is_valid_icon(value: str) -> bool`
  - フィクスチャ `png_bytes(size=(64, 64), color=(200, 30, 30, 255), fmt="PNG") -> bytes` を返す関数 `make_png`、`icon: str`

- [ ] **Step 1: Pillow を依存に足す**

Run: `uv add pillow`
Expected: `pyproject.toml` の `dependencies` に `pillow` が入り、`uv.lock` が更新される。

- [ ] **Step 2: テスト用のフィクスチャを足す**

`test/conftest.py` の末尾に足す(先頭の import に `io` を足す):

```python
@pytest.fixture
def make_png():
    """画像のバイト列を作る関数。fmt は Pillow の形式名(PNG・JPEG・GIF・WEBP)。"""
    from PIL import Image

    def build(size: tuple[int, int] = (64, 64), color: tuple[int, ...] = (200, 30, 30, 255), fmt: str = "PNG") -> bytes:
        mode = "RGBA" if fmt in ("PNG", "WEBP") else "RGB"
        image = Image.new(mode, size, color[: len(mode)] if mode == "RGB" else color)
        buffer = io.BytesIO()
        image.save(buffer, fmt)
        return buffer.getvalue()

    return build


@pytest.fixture
def icon(make_png) -> str:
    """有効なアイコン(data URI)。"""
    from projectapp.icons import make_icon

    return make_icon(make_png())
```

- [ ] **Step 3: 失敗するテストを書く**

`test/test_icons.py`:

```python
import base64
import io
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
def test_make_icon_accepts_each_format_and_returns_a_128_square_png(make_png, fmt: str) -> None:
    image = decode(make_icon(make_png((300, 200), fmt=fmt)))
    assert image.format == "PNG" and image.size == (ICON_SIZE, ICON_SIZE)


def test_make_icon_crops_the_center_of_a_wide_image(make_png) -> None:
    left_right = Image.new("RGBA", (300, 100), (255, 0, 0, 255))
    left_right.paste((0, 0, 255, 255), (200, 0, 300, 100))  # 右の 1/3 だけ青。中央の切り抜きには入らない
    buffer = io.BytesIO()
    left_right.save(buffer, "PNG")
    image = decode(make_icon(buffer.getvalue())).convert("RGBA")
    assert image.getpixel((2, 64))[:3] == (255, 0, 0) and image.getpixel((125, 64))[:3] == (255, 0, 0)


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
    top, bottom, left, right = image.getpixel((64, 8)), image.getpixel((64, 119)), image.getpixel((8, 64)), image.getpixel((119, 64))
    assert abs(top[0] - bottom[0]) > 100  # 回したので、赤と青は上下に分かれる
    assert abs(left[0] - right[0]) < 40


def test_make_icon_converts_a_palette_gif_and_a_cmyk_jpeg() -> None:
    palette = Image.new("P", (40, 40), 3)
    buffer = io.BytesIO()
    palette.save(buffer, "GIF")
    assert decode(make_icon(buffer.getvalue())).size == (ICON_SIZE, ICON_SIZE)
    cmyk = Image.new("CMYK", (40, 40), (0, 255, 255, 0))
    buffer = io.BytesIO()
    cmyk.save(buffer, "JPEG")
    assert decode(make_icon(buffer.getvalue())).size == (ICON_SIZE, ICON_SIZE)


def test_make_icon_uses_the_first_frame_of_an_animation() -> None:
    frames = [Image.new("RGB", (30, 30), color) for color in ((255, 0, 0), (0, 0, 255))]
    buffer = io.BytesIO()
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:])
    assert decode(make_icon(buffer.getvalue())).convert("RGB").getpixel((64, 64))[0] > 200


def test_make_icon_scales_up_a_tiny_image(make_png) -> None:
    assert decode(make_icon(make_png((1, 1)))).size == (ICON_SIZE, ICON_SIZE)
    assert decode(make_icon(make_png((10, 400)))).size == (ICON_SIZE, ICON_SIZE)


@pytest.mark.parametrize(
    "data",
    [b"", b"not an image", b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"\x89PNG\r\n\x1a\nbroken"],
)
def test_make_icon_rejects_what_is_not_a_supported_image(data: bytes) -> None:
    with pytest.raises(IconError):
        make_icon(data)


def test_make_icon_rejects_a_bmp(tmp_path: Path) -> None:
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
    noise = Image.frombytes("RGBA", (400, 400), __import__("os").urandom(400 * 400 * 4))
    buffer = io.BytesIO()
    noise.save(buffer, "PNG")
    try:
        uri = make_icon(buffer.getvalue())
    except IconError:
        return  # 64KB を超えるときは、拒否でよい
    assert len(base64.b64decode(uri[len(DATA_PREFIX) :])) <= MAX_ICON_BYTES


def test_load_icon_reads_a_file_and_reports_a_missing_one(tmp_path: Path, make_png) -> None:
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
    assert not is_valid_icon(DATA_PREFIX + base64.b64encode(b"\0" * (MAX_ICON_BYTES + 1)).decode())
    assert not is_valid_icon(DATA_PREFIX + body[: len(body) // 2])  # 途中で切れた PNG
```

- [ ] **Step 4: 失敗を確認する**

Run: `uv run pytest test/test_icons.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.icons`)

- [ ] **Step 5: `icons.py` を書く**

```python
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
```

- [ ] **Step 6: 通ることを確認する**

Run: `uv run pytest test/test_icons.py -q && uv run ty check src/projectapp/icons.py`
Expected: PASS、ty のエラーなし。落ちるテストがあれば、テストの前提(Pillow の挙動)を実際の出力で確かめ、実装かテストのどちらが間違いかを見極めて直す(例: ノイズ画像のテストは、拒否でも合格にしてある)。

- [ ] **Step 7: コミット**

```bash
git add pyproject.toml uv.lock src/projectapp/icons.py test/conftest.py test/test_icons.py
git commit -m "feat: メンバーのアイコンを作る・検証する関数を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `Member.icon` とファイル形式(`version` 7)・マージ

**Files:**
- Modify: `src/projectapp/models.py:11`(`FORMAT_VERSION`)、`src/projectapp/models.py:85-89`(`Member`)
- Modify: `src/projectapp/storage.py`(`_members`、`_dump`、新規 `_icon`)
- Modify: `src/projectapp/merge.py:174`(`MEMBER_LABELS`)、`merge.py:182-183`(`_members`)、`merge.py:355`
- Test: `test/test_storage.py`、`test/test_merge.py`、`test/test_summary.py:61`(`test_version_is_6`)、`test/test_storage.py:1307`・`:1375`

**Interfaces:**
- Consumes: `projectapp.icons.is_valid_icon(value: str) -> bool`(Task 1)
- Produces: `Member.icon: str = ""`(`id` の次のフィールド)、`FORMAT_VERSION == 7`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の末尾に足す(`json`・`Path`・`save_project`・`load_project`・`Member`・`Project` は既に import 済み):

```python
def write_member_icon(path: Path, value: object, version: int = 7) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = version
    raw["members"][0]["icon"] = value
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_member_icon_roundtrips(tmp_path: Path, icon: str) -> None:
    project = Project("demo", members=[Member("甲", 1.0, icon=icon), Member("乙", 1.0)])
    loaded = load_project(save_project(project, tmp_path))
    assert [m.icon for m in loaded.members] == [icon, ""]


def test_a_file_without_the_icon_key_loads_with_no_icon(tmp_path: Path) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 6
    del raw["members"][0]["icon"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_project(path).members[0].icon == ""


def test_a_version_6_file_ignores_an_icon_key(tmp_path: Path, icon: str) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, icon, version=6)
    assert load_project(path).members[0].icon == ""


@pytest.mark.parametrize("value", [None, ""])
def test_a_null_or_empty_icon_means_no_icon(tmp_path: Path, value: object) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, value)
    assert load_project(path).members[0].icon == ""


@pytest.mark.parametrize(
    "value",
    ["https://example.com/a.png", "data:image/png;base64,!!!", "data:image/png;base64,AAAA", 123, ["x"]],
)
def test_an_invalid_icon_is_rejected_on_load(tmp_path: Path, value: object) -> None:
    path = save_project(Project("demo", members=[Member("甲", 1.0)]), tmp_path)
    write_member_icon(path, value)
    with pytest.raises(ValueError, match="アイコン"):
        load_project(path)


def test_a_member_added_for_an_unknown_assignee_is_saved_with_an_empty_icon(tmp_path: Path) -> None:
    project = Project("demo", sections=[Section("s", [Task("t", assignees=[Assignee("丙", 1.0)])])])
    raw = json.loads(save_project(project, tmp_path).read_text(encoding="utf-8"))
    assert raw["members"] == [{"name": "丙", "ratio": 1.0, "levels": {}, "id": raw["members"][0]["id"], "icon": ""}]
```

`test/test_merge.py` の末尾に足す(`ICON_B` は `icon` フィクスチャと別の有効な値が要る。2 つ目の値は、`make_png` で色違いを作る):

```python
def test_a_member_icon_changed_on_one_side_is_taken(icon: str) -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[Member("甲", 1.0, id="m1", icon=icon)])
    result = merge_projects(base, ours, base)
    assert result.conflicts == [] and result.project.members[0].icon == icon


def test_different_member_icons_on_both_sides_conflict(make_png) -> None:
    from projectapp.icons import make_icon

    one, two = make_icon(make_png(color=(255, 0, 0, 255))), make_icon(make_png(color=(0, 0, 255, 255)))
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[Member("甲", 1.0, id="m1", icon=one)])
    theirs = proj(members=[Member("甲", 1.0, id="m1", icon=two)])
    result = merge_projects(base, ours, theirs)
    assert [(c.kind, c.field) for c in result.conflicts] == [("member", "icon")]
    assert merge_projects(base, ours, theirs, {result.conflicts[0].key: THEIRS}).project.members[0].icon == two


def test_the_icon_survives_the_rename_of_a_same_name_member(icon: str) -> None:
    base = proj()
    ours = proj(members=[Member("甲", 1.0, id="m1", icon=icon)])
    theirs = proj(members=[Member("甲", 1.0, id="m2")])
    merged = merge_projects(base, ours, theirs).project
    assert sorted((m.name, bool(m.icon)) for m in merged.members) == [("甲", True), ("甲 (2)", False)]
```

注意: `Conflict` のフィールド名(`kind`・`field`・`key`)と `choices` の渡し方は、`test/test_merge.py` の既存の衝突テスト(`THEIRS` を使うもの)をそのまま真似て合わせる。名前が違えば、このテストを既存の形に直す(期待する中身は変えない)。

また、既存の `test_version_is_6`(`test/test_summary.py:61`)と `FORMAT_VERSION == 6`(`test/test_storage.py:1307`・`:1375`)を `7` に直す。`test_summary.py:38` の `"version": 6` は、旧形式のサンプルなので、そのまま残す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_storage.py test/test_merge.py test/test_summary.py -q -x`
Expected: FAIL(`Member` に `icon` がない)

- [ ] **Step 3: モデルを直す**

`src/projectapp/models.py:11`:

```python
FORMAT_VERSION = 7  # プロジェクトファイルの形式のバージョン。キーのない古いファイルは 1 として読む(2: メンバーとセクションの id、担当者はメンバー id で指す。3: カテゴリ、タスクは category_id で指す。4: イベント。5: タスクの進捗度。6: まとめ〔種別と子の id〕。7: メンバーのアイコン)
```

`Member` の `id` の次に足す:

```python
    icon: str = ""  # アイコン(128×128 の PNG の data URI)。空はアイコンなし
```

- [ ] **Step 4: 保存・読込を直す**

`storage.py` の import に `from projectapp.icons import is_valid_icon` を足し、`_members` の前に:

```python
def _icon(value: Any) -> str:
    """メンバーのアイコン(version 7)。キーがない・null・空は、アイコンなし。形・大きさ・中身が不正なら ValueError。"""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not is_valid_icon(value):
        raise ValueError("メンバーのアイコンが正しくありません")
    return value
```

`_members` の `member = Member(name, ratio, levels)` を差し替える(`icon` の検証は、同名で捨てるメンバーにも効くよう、`if not name or name in seen:` より前に置く):

```python
        icon = _icon(raw.get("icon")) if ctx.version >= 7 else ""
        ...
        member = Member(name, ratio, levels, icon=icon)
```

`_dump` の補うメンバーの辞書に `"icon": ""` を足す:

```python
                data["members"].append({"name": name, "ratio": 1.0, "levels": {}, "id": ids[name], "icon": ""})
```

- [ ] **Step 5: マージを直す**

`merge.py`:

```python
MEMBER_LABELS = {"name": "名前", "ratio": "基本比率", "levels": "段階の選択", "icon": "アイコン"}
```

```python
def _members(project: Project) -> dict[str, Record]:
    return {
        m.id: {"name": m.name, "ratio": m.ratio, "levels": dict(m.levels), "icon": m.icon} for m in project.members
    }
```

`merge.py:355` の `Member(...)` に `icon=r["icon"]` を足す:

```python
        members=[
            Member(r["name"], r["ratio"], dict(r["levels"]), id=key, icon=r["icon"]) for key, r in members.items()
        ],
```

- [ ] **Step 6: 通ることと全体への影響を確認する**

Run: `uv run pytest test/test_storage.py test/test_merge.py test/test_summary.py test/test_models.py test/test_handoff.py test/test_puml_import.py -q`
Expected: PASS。`Member` の等しさを使う既存のテストが落ちたら、`icon` の既定が空なので、通常は影響しない。落ちた理由を確かめて直す。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py src/projectapp/merge.py test/
git commit -m "feat: メンバーのアイコンをファイル(version 7)とマージに足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `avatar()` と、ガントチャート・ダッシュボードへの表示

**Files:**
- Create: `src/projectapp/avatar.py`
- Modify: `src/projectapp/gantt.py:370`(`__init__`)、`:867`(`category_lookup` の隣)、`:1246-1250`(担当者チップ)
- Modify: `src/projectapp/dashboard_view.py`(`show`、`cards`、`load_card`)
- Modify: `src/projectapp/views.py:681`(`show` の呼び出し)
- Test: `test/test_avatar.py`(新規)、`test/test_gantt.py`、`test/test_dashboard_view.py`

**Interfaces:**
- Consumes: `projectapp.icons.is_valid_icon(value: str) -> bool`、`Member.icon`
- Produces:
  - `avatar(name: str, icon: str, size: int) -> ui.element`(アイコンが有効なら `<img>`、そうでなければ頭文字の `ui.label`。どちらも丸で `size`px 四方。`.tooltip()`・`.mark()` が使える)
  - `GanttChart.icon_lookup: dict[str, str]`(メンバー名 → アイコン。`set_project` のたびに作り直す)
  - `DashboardView.show(data: Dashboard, kind: PeriodKind, icons: dict[str, str] | None = None) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_avatar.py`:

```python
from nicegui import ui
from nicegui.testing import User

from projectapp.avatar import avatar


def mount_avatars(*specs: tuple[str, str, int]) -> None:
    @ui.page("/")
    def index() -> None:
        for number, (name, icon, size) in enumerate(specs):
            avatar(name, icon, size).mark(f"a{number}")


async def test_an_avatar_without_an_icon_shows_the_first_character(user: User) -> None:
    mount_avatars(("山田太郎", "", 16))
    await user.open("/")
    element = user.find(marker="a0").elements.pop()
    assert element.text == "山" and element._style["width"] == element._style["height"] == "16px"
    assert element._style["border-radius"] == "50%"


async def test_an_avatar_with_an_icon_is_a_round_image(user: User, icon: str) -> None:
    mount_avatars(("山田", icon, 28))
    await user.open("/")
    element = user.find(marker="a0").elements.pop()
    assert element.tag == "img" and element._props["src"] == icon
    assert element._style["width"] == "28px" and element._style["border-radius"] == "50%"


async def test_an_avatar_with_a_broken_icon_falls_back_to_the_first_character(user: User) -> None:
    mount_avatars(("山田", "data:image/png;base64,AAAA", 16), ("", "", 16), ("😀太郎", "", 16))
    await user.open("/")
    assert user.find(marker="a0").elements.pop().text == "山"
    assert user.find(marker="a1").elements.pop().text == "?"  # 名前が空でも落ちない
    assert user.find(marker="a2").elements.pop().text == "😀"
```

`test/test_gantt.py` の `test_assignee_chip_shows_the_first_character_and_the_name_on_hover`(2016 行付近)の下に足す(`mount`・`chip`・`tooltips_targeting`・`project_with` は同じファイルの既存):

```python
async def test_assignee_chip_shows_the_member_icon_and_keeps_the_hover(user: User, icon: str) -> None:
    project = project_with(Task("設計", assignees=[Assignee("山田太郎", 0.5)]))
    project.members = [Member("山田太郎", 1.0, icon=icon)]
    mount(project)
    await user.open("/")
    who = chip(user, "task-assignee-0-0")
    assert who.tag == "img" and who._props["src"] == icon
    assert tooltips_targeting(who) == ["山田太郎 50%"]


async def test_assignee_chip_without_an_icon_keeps_the_first_character_for_other_members(user: User, icon: str) -> None:
    project = project_with(Task("設計", assignees=[Assignee("山田"), Assignee("佐藤")]))
    project.members = [Member("山田", 1.0, icon=icon), Member("佐藤", 1.0)]
    mount(project)
    await user.open("/")
    assert chip(user, "task-assignee-0-0").tag == "img"
    assert chip(user, "task-assignee-0-0-1").text == "佐"


async def test_the_icon_follows_a_changed_project(user: User, icon: str) -> None:
    project = project_with(Task("設計", assignees=[Assignee("山田")]))
    project.members = [Member("山田", 1.0)]
    charts, _ = mount_chart(project)
    await user.open("/")
    assert chip(user, "task-assignee-0-0").text == "山"
    project.members[0].icon = icon
    charts[0].set_project(project)
    await user.should_see(marker="task-assignee-0-0")
    assert chip(user, "task-assignee-0-0").tag == "img"
```

`test/test_dashboard_view.py` の末尾に足す(`mount`・`sample` は既存。`sample()` に `loads` の「甲」が入っているかを確かめ、なければ `sample()` が返す `Dashboard` の `loads` に合う名前を使う):

```python
async def test_the_load_card_shows_the_icon_of_a_member_who_has_one(user: User, icon: str) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    name = next(iter(data.loads))
    views[0].show(data, PeriodKind.WEEK, {name: icon})
    await user.should_see(marker=f"dashboard-load-icon-{name}")
    element = user.find(marker=f"dashboard-load-icon-{name}").elements.pop()
    assert element._props["src"] == icon


async def test_the_load_card_shows_no_icon_for_a_member_without_one(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    data = sample()
    name = next(iter(data.loads))
    views[0].show(data, PeriodKind.WEEK)
    await user.should_see(marker=f"dashboard-load-{name}")
    assert not user.find(marker=f"dashboard-load-icon-{name}").elements
```

`test/test_gantt.py` の、上の担当者チップのテストの下に、プレビュー(読み取り専用)でもアイコンが出ることを足す(`mount_with` は既存。`ViewOptions(read_only=True)` を渡す):

```python
async def test_the_read_only_chart_shows_the_member_icon(user: User, icon: str) -> None:
    project = project_with(Task("設計", assignees=[Assignee("山田")]))
    project.members = [Member("山田", 1.0, icon=icon)]
    mount_with(project, ViewOptions(read_only=True))
    await user.open("/")
    assert chip(user, "task-assignee-0-0").tag == "img"
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_avatar.py test/test_gantt.py test/test_dashboard_view.py -q -x`
Expected: FAIL(`projectapp.avatar` がない)

- [ ] **Step 3: `avatar.py` を書く**

```python
"""メンバーの丸いアイコン。アイコンがなければ(壊れていても)頭文字のチップを出す。"""

from nicegui import ui

from projectapp.icons import is_valid_icon

ICON_BORDER = "1px solid rgba(128, 128, 128, 0.6)"


def avatar(name: str, icon: str, size: int) -> ui.element:
    """`size`px 四方の丸。有効なアイコンがあれば画像、なければ名前の頭文字(名前が空なら `?`)。"""
    base = f"flex: none; width: {size}px; height: {size}px; border-radius: 50%;"
    if icon and is_valid_icon(icon):
        return ui.element("img").props(f'src="{icon}" alt=""').style(
            base + f" object-fit: cover; border: {ICON_BORDER}"
        )
    return ui.label(name[:1] or "?").style(
        base
        + f" line-height: {size}px; text-align: center; font-size: {max(8, size * 5 // 8)}px;"
        + " background: rgba(128, 128, 128, 0.3)"
    )
```

`ui.element("img").props('src="..."')` の値が `_props["src"]` に入らないとき(引用符つきの値の扱いが違うとき)は、`props` に渡す文字列を `f"src={icon}"`(引用符なし。base64 に空白がないので可)に変えて、`test_avatar` の `_props["src"] == icon` が通る形にする。

- [ ] **Step 4: ガントチャートのチップを置き換える**

`gantt.py` の import に `from projectapp.avatar import avatar` を足す。`__init__` の `self.category_lookup: dict[str, Category] = {}` の次に:

```python
        self.icon_lookup: dict[str, str] = {}
```

`self.category_lookup = by_id(self.project.categories)` の次に:

```python
        self.icon_lookup = {m.name: m.icon for m in self.project.members if m.icon}
```

`task_chips` の担当者のチップ(`ui.label(assignee.name[0])...` の 1 文)を差し替える:

```python
            avatar(assignee.name, self.icon_lookup.get(assignee.name, ""), 16).tooltip(
                f"{assignee.name} {round(assignee.allocation * 100)}%"
            ).mark(f"task-assignee-{key}-{ti}{suffix}")
```

`ASSIGNEE_CHIP_STYLE` は `+n` のチップでまだ使うので残す。

- [ ] **Step 5: ダッシュボードに出す**

`dashboard_view.py` の import に `from projectapp.avatar import avatar` を足す。`__init__` で `self.icons: dict[str, str] = {}`、`show` を:

```python
    def show(self, data: Dashboard, kind: PeriodKind, icons: dict[str, str] | None = None) -> None:
        self.icons = icons or {}
        ...  # 既存の本文はそのまま
```

(既存の本文の `self.data = data` の前に `self.icons = icons or {}` を置く。)

`load_card` の `ui.label(name)` を差し替える:

```python
                    with ui.row().classes("items-center no-wrap gap-2"):
                        if icon := self.icons.get(name):
                            avatar(name, icon, 20).mark(f"dashboard-load-icon-{name}")
                        ui.label(name)
```

`views.py:681`:

```python
        icons = {m.name: m.icon for m in self.project.members if m.icon}
        self.dashboard_view.show(summarize(self.project, period, now, self.holidays), self.dashboard_kind, icons)
```

- [ ] **Step 6: 通ることを確認する**

Run: `uv run pytest test/test_avatar.py test/test_gantt.py test/test_dashboard_view.py test/test_views.py -q -n auto && uv run ty check src/projectapp`
Expected: PASS、ty のエラーなし。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/avatar.py src/projectapp/gantt.py src/projectapp/dashboard_view.py src/projectapp/views.py test/
git commit -m "feat: 担当者チップとダッシュボードにメンバーのアイコンを出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: メンバーのダイアログでアイコンを選ぶ・外す

**Files:**
- Modify: `src/projectapp/forms.py`(`MemberRow`:596、`build_members`:606-640、`member_columns`:1482、`member_table_min_rem`:1491、`members_panel`:1514、`open_members_parameters_dialog`:1655)
- Modify: `src/projectapp/views.py`(`open_members_parameters`:852、新規 `pick_member_icon`)
- Test: `test/test_forms.py`、`test/test_views.py`(`:3320-3328` の既存の列の幅のテストも直す)

**Interfaces:**
- Consumes: `avatar(name, icon, size)`(Task 3)、`icons.load_icon`・`icons.IconError`・`icons.ICON_FILE_TYPES`・`icons.is_valid_icon`(Task 1)、`Member.icon`(Task 2)
- Produces:
  - `MemberRow.icon: str = ""`(`id` の次)
  - `members_panel(..., pick_icon: Callable[[], Awaitable[str | None]] | None = None)`、`open_members_parameters_dialog(..., pick_icon: ... = None)`
  - `MainView.pick_member_icon() -> str | None`(async。キャンセル・失敗は `None`)
  - 列: `MEMBER_ICON_COLUMN_REM = 6` を先頭に足す。マーカー `member-icon-{index}`・`member-icon-pick-{index}`・`member-icon-clear-{index}`、見出し `member-header-icon`

- [ ] **Step 1: 失敗するテストを書く(フォームの検証)**

`test/test_forms.py` の `test_build_members_*` の並びに足す(`MemberRow`・`build_members` は import 済み。`MemberRow(original, name, ratio_percent, levels, id)` の既存の呼び方に合わせる):

```python
def test_build_members_carries_the_icon(icon: str) -> None:
    members, _ = build_members([MemberRow("甲", "甲", 100.0, icon=icon), MemberRow(None, "乙", 100.0)], ["甲"], lambda _: 0)
    assert [m.icon for m in members] == [icon, ""]


def test_build_members_rejects_a_broken_icon() -> None:
    with pytest.raises(ValueError, match="アイコン"):
        build_members([MemberRow(None, "甲", 100.0, icon="data:image/png;base64,AAAA")], [], lambda _: 0)
```

- [ ] **Step 2: 失敗するテストを書く(ダイアログと配線)**

`test/test_views.py` の `FakeExporter` を使う。メンバーのダイアログのテストの近く(`test_applying_the_members_tab_keeps_the_dialog_open` の下)に足す。`mount_capturing` は既存のテスト用に `MainView` を作る関数なので、`exporter` を渡せる形かを確かめ、渡せなければ `mount_preview(base_dir, views, exporter)`(`FakeExporter` を受け取る、既存)を使う:

```python
async def open_members_view_with(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    return views[0]


def write_png(path: Path, make_png) -> Path:
    path.write_bytes(make_png())
    return path


async def test_choosing_an_icon_shows_it_and_applies_it(user: User, tmp_path: Path, make_png) -> None:
    exporter = FakeExporter(open_path=write_png(tmp_path / "a.png", make_png))
    view = await open_members_view_with(user, tmp_path, exporter)
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    user.find(marker="member-icon-pick-0").click()
    assert await wait_until(lambda: user.find(marker="member-icon-0").elements.pop().tag == "img")
    assert exporter.asked_open and "png" in exporter.asked_open[0][0]
    assert user.find(marker="members-dirty").elements.pop().text == "●"  # 未適用の編集
    assert view.project.members[0].icon == ""  # 適用までは変わらない
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].icon.startswith("data:image/png;base64,"))


async def test_clearing_an_icon_applies_the_removal(user: User, tmp_path: Path, icon: str) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter())
    view.project.members = [Member("田中", 1.0, icon=icon)]
    await open_members_parameters(user)
    user.find(marker="member-icon-clear-0").click()
    assert await wait_until(lambda: not user.find(marker="member-icon-clear-0").elements)
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].icon == "")


async def test_cancelling_the_file_choice_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter(open_path=None))
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    user.find(marker="member-icon-pick-0").click()
    assert await wait_until(lambda: bool(view.exporter.asked_open))
    assert user.find(marker="member-icon-0").elements.pop().tag != "img"
    assert user.find(marker="members-dirty").elements.pop().text == ""


async def test_an_unreadable_image_is_reported_and_changes_nothing(user: User, tmp_path: Path) -> None:
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    view = await open_members_view_with(user, tmp_path, FakeExporter(open_path=bad))
    view.project.members = [Member("田中", 1.0)]
    await open_members_parameters(user)
    user.find(marker="member-icon-pick-0").click()
    await user.should_see("アイコンにできませんでした")
    assert user.find(marker="member-icon-0").elements.pop().tag != "img"


async def test_the_pick_button_is_hidden_without_a_native_window(user: User, tmp_path: Path, icon: str) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter(available=False))
    view.project.members = [Member("田中", 1.0, icon=icon)]
    await open_members_parameters(user)
    await user.should_see(marker="member-icon-0")
    assert not user.find(marker="member-icon-pick-0").elements
    assert user.find(marker="member-icon-clear-0").elements  # 外すことはできる


async def test_the_icon_survives_a_rename_and_undo_restores_it(user: User, tmp_path: Path, icon: str) -> None:
    view = await open_members_view_with(user, tmp_path, FakeExporter())
    view.project.members = [Member("田中", 1.0, icon=icon)]
    await open_members_parameters(user)
    user.find(marker="member-name-0").clear().type("田中太郎")
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["田中太郎"])
    assert view.project.members[0].icon == icon
    user.find(marker="member-icon-clear-0").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].icon == "")
    with view.client:
        view.undo()
    assert view.project.members[0].icon == icon
```

`view.undo()` と `wait_until` の名前・渡し方は、`test_views.py` の元に戻すのテスト(`undo` で grep)に合わせる。違えば、既存の呼び方にそろえる。

既存の列の幅のテストは、アイコンの列(6rem)と間隔(`3` → `4`)を足した値に直す(`test/test_views.py:3320-3328`):

```python
    assert grid_columns(user) == ["6rem", "7rem", "7rem", "3rem"]  # アイコン・名前・相対比率・削除
```
```python
    # アイコン 6rem + 名前 7rem + 比率 7rem + 削除 3rem + 列の間隔
    assert member_table_min_rem(0, False) == 6 + 7 + 7 + 3 + 2 * 4
    assert member_table_min_rem(2, True) == 6 + 7 + 7 + 9 * 2 + 11 + 3 + 2 * 7
```

`grid_columns` を使うほかのテストや、列の数・位置に依存するテスト(`member-header-*`)が落ちたら、アイコン列が先頭に増えた分だけ期待値を直す。

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -x -k "member"`
Expected: FAIL

- [ ] **Step 4: フォームのデータを直す**

`MemberRow` に足す:

```python
    icon: str = ""  # アイコン(data URI)。空はアイコンなし
```

`build_members` で、`Member(name, ...)` の前に検証し、`icon` を渡す(`from projectapp.icons import is_valid_icon` を import):

```python
        if row.icon and not is_valid_icon(row.icon):
            raise ValueError(f"アイコンが正しくありません: {name}")
        ...
        members.append(Member(name, round(ratio / 100, 4), levels, member_id, row.icon))
```

`members_panel` の `to_rows` を:

```python
        return [
            MemberRow(m.name, m.name, round(m.ratio * 100, 2), dict(m.levels), m.id, m.icon)
            for m in get_members()
        ]
```

- [ ] **Step 5: 列と表を直す**

`MEMBER_ICON_COLUMN_REM = 6` を `MEMBER_NAME_COLUMN_REM` の定義の近くに足し、`member_columns` / `member_table_min_rem` を直す:

```python
    columns = [f"{MEMBER_ICON_COLUMN_REM}rem", f"{MEMBER_NAME_COLUMN_REM}rem", f"{MEMBER_RATIO_COLUMN_REM}rem"]
```
```python
    return (
        MEMBER_ICON_COLUMN_REM
        + MEMBER_NAME_COLUMN_REM
        + ...  # 以下は既存のまま
        + 2 * (4 + level_count + (1 if with_effective else 0))  # 列の間隔(gap 0.5rem)の概算
    )
```

docstring の列の説明を「アイコン・名前・基本比率…」に直す。

`members_panel` に引数 `pick_icon: Callable[[], Awaitable[str | None]] | None = None` を足し(`from collections.abc import Awaitable` を import)、`table()` の見出しとセルを直す:

```python
                ui.label("アイコン").classes(header).mark("member-header-icon")
                ui.label("名前").classes(header).mark("member-header-name")
```

行の先頭(名前の `ui.input` の前)に:

```python
                    with ui.row().classes("items-center no-wrap gap-1"):
                        avatar(row.name or "?", row.icon, MEMBER_ICON_SIZE_PX).mark(f"member-icon-{index}")
                        if pick_icon is not None:
                            ui.button(icon="image", on_click=lambda r=row: choose_icon(r)).props(
                                "flat dense round size=sm"
                            ).tooltip("アイコンを選ぶ").mark(f"member-icon-pick-{index}")
                        if row.icon:
                            ui.button(icon="close", on_click=lambda r=row: clear_icon(r)).props(
                                "flat dense round size=sm"
                            ).tooltip("アイコンを外す").mark(f"member-icon-clear-{index}")
```

`MEMBER_ICON_SIZE_PX = 28` を足し、`from projectapp.avatar import avatar` を import。`remove` の隣に:

```python
    async def choose_icon(row: MemberRow) -> None:
        assert pick_icon is not None
        chosen = await pick_icon()
        if chosen is not None:
            row.icon = chosen
            table.refresh()

    def clear_icon(row: MemberRow) -> None:
        row.icon = ""
        table.refresh()
```

(`table` は `remove` が使うのと同じ `@ui.refreshable`。`choose_icon` は `table()` の定義より後に置いて参照できる位置に置く。)

`open_members_parameters_dialog` に `pick_icon: Callable[[], Awaitable[str | None]] | None = None` を足し、`members_panel(get_members, assigned, on_apply_members, get_parameters, get_taken, pick_icon)` に渡す(`members_panel` の引数の末尾に `pick_icon` を足した順に合わせる)。

- [ ] **Step 6: `views.py` の配線**

import に `from projectapp.icons import ICON_FILE_TYPES, IconError, load_icon` を足す。`open_members_parameters` に:

```python
            pick_icon=self.pick_member_icon if self.exporter.available else None,
```

`assigned_count` の前に:

```python
    async def pick_member_icon(self) -> str | None:
        """メンバーのアイコンにする画像を選ばせる。キャンセルと、画像にできないとき(理由を通知)は None。"""
        path = await self.exporter.ask_open_path(ICON_FILE_TYPES)
        if path is None:
            return None
        try:
            return load_icon(path)
        except (IconError, OSError) as exc:
            ui.notify(f"アイコンにできませんでした: {exc}", type="negative")
            return None
```

- [ ] **Step 7: 通ることを確認する**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -n auto && uv run ty check src/projectapp`
Expected: PASS、ty のエラーなし。

- [ ] **Step 8: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/
git commit -m "feat: メンバーのダイアログで、アイコンを選ぶ・外す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 仕様の更新・全体の検証・実機の確認

**Files:**
- Modify: `CLAUDE.md`(プロジェクトの仕様。`メンバー`の節、`データの保存先`、`実装上の注意`の `version`)
- Modify: `docs/development.md`(モジュール構成に `icons.py`・`avatar.py`、ファイル形式に `version` 7)
- Modify: `docs/superpowers/specs/2026-10-18-member-icon-design.md`(状態を実装済みに)
- Modify: `.claude/MEMORY.md`(要望 41 を完了に、次は 42)、`docs/requests.md`・`docs/request-history.md`・`docs/work-log.md`(既存の記録の流儀に合わせる)

- [ ] **Step 1: 仕様を直す**

`CLAUDE.md` の次の箇所を直す(周りの文体に合わせて、1〜3 文):
- コンセプトの `メンバー` の項: 「`アイコン`(画像ファイル。Slack のアイコンなど)を設定でき、設定されていれば、ガントチャートの担当者チップ・ダッシュボードの人ごとの負荷・プレビュー・画像に出す。128×128 の PNG に縮小して、プロジェクトのファイルに埋め込む。PNG・JPEG・GIF・WebP(10MB まで)。選ぶのはネイティブウィンドウのみ。担当者向けファイル・PlantUML には出さない」を足す。
- `実装上の注意` の `version`(整数。現在 6)を 7 に。
- ヘッダー節の `メンバーとパラメータ` の説明に、メンバーのタブの表の「アイコン」の列を足す。

`docs/development.md` に、`icons.py`(縮小と検証の純粋関数)・`avatar.py`(表示の部品)と、ファイル形式の `version` 7(`members[].icon`)を足す。

- [ ] **Step 2: 全体のテストと型を通す**

Run: `uv run pytest -q -n auto && uv run ty check`
Expected: すべて PASS、ty のエラーなし。件数(約 1,800 件+新規)を記録に残す。

- [ ] **Step 3: 実機で確認する(ネイティブ)**

Run: `uv run projectapp`
確認する項目(結果は、作業記録に書く):
1. `プロジェクト` → `メンバーとパラメータ` で、メンバーのアイコンを `選ぶ`(Slack のアイコンの PNG・JPEG)。プレビューが丸く出る。`適用` までは `●` が出る。
2. 適用後、ガントチャートの担当者チップに出る。マウスオーバーの名前と割り当て率は今のまま。`+n` のまとめも崩れない。
3. ダッシュボードの人ごとの負荷の行に出る。
4. `エクスポート` → `チャートプレビュー` に出て、`画像として保存` の PNG にも出る。
5. 保存して開き直す。ダーク、画面の拡大 200% で見た目が崩れない。
6. `外す` で頭文字に戻る。画像でないファイル・大きすぎるファイルを選ぶと、理由が通知され、変わらない。
7. `Cmd+Z` で戻る。

- [ ] **Step 4: 記録を直してコミットする**

`.claude/MEMORY.md` の要望 41 を「(完了。PR #xx)」に直し、「次に着手する」を要望 42 に移す。設計書の状態を「実装済み」に。`docs/request-history.md` と `docs/work-log.md` に、決めたこと・見送ったこと・実機の結果を、既存の項目の流儀で足す。

```bash
git add -A
git commit -m "docs: メンバーのアイコン(要望41)の仕様と作業記録を直す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: PR を出す**

```bash
git push -u origin feature/member-icon
gh pr create --base develop --title "feat: メンバーのアイコン(要望41)" --body "<変更の要約、設計書へのリンク、テストの件数、実機の確認結果>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

マージは、実機の確認結果を見せて、承認をもらってから行う。
