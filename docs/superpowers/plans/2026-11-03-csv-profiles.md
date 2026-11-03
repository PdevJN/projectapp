# CSV プロファイル(要望 101) 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CSV・TSV の取り込み・書き出しに、列の対応をまとめた「プロファイル」を導入し、汎用の CSV を読み書きできるようにする(Smartsheet 形式は組み込みのプロファイルとして、いまの動作を保つ)。

**Architecture:** 純粋なモジュール`csv_profile.py`(プロファイルの型・別名・推測・検証・config の変換)を新設し、`csv_import.py`・`csv_export.py`を「プロファイルで列を決める」形に一般化する。画面は`csv_dialog.py`(取り込みと書き出しのダイアログ)を新設し、`views.py`のハンドラーから開く。プロファイルは`~/.projectapp/config.json`の`csv_profiles`に保存する(プロジェクトのファイル形式は変えない)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -m smoke`・全テストは`-n auto`)、ruff、ty。

**Spec:** [`docs/superpowers/specs/2026-11-03-csv-profiles-design.md`](../specs/2026-11-03-csv-profiles-design.md)

## Global Constraints

- 言語は日本語(UI・通知・コメント・docstring)。Python 3.13 以上。ライブラリは NiceGUI。
- `csv_profile.py`・`csv_import.py`・`csv_export.py`は NiceGUI に依存しない。
- プロジェクトのファイル形式は変えない(`version` 20 のまま)。保存は`config.json`の`csv_profiles`・`csv_profile_last`のみ。
- 組み込みの`Smartsheet`で取り込む・書き出す結果は、いまと同じ(既存の`test/test_csv_import.py`・`test/test_csv_export.py`を、変えずに通す)。
- プロファイル名は 1〜30 文字、`Smartsheet`は予約。最大 20 件。見出しは 1〜40 文字。区切りは`,`・`\t`・`;`。文字コードは`utf-8`・`utf-8-sig`・`cp932`。日付の書式は`ja`・`ymd-dash`・`ymd-slash`。担当の区切りは 0〜3 文字。
- ネイティブ専用(ファイルのダイアログ)。Web モードでは従来どおり通知で断る(`IMPORT_NOT_NATIVE_MESSAGE`・`HANDOFF_NOT_NATIVE_MESSAGE`)。
- 実装の完了時: `uv run pytest -m smoke` →(広い範囲に触れるので)`uv run pytest -n auto` → `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`(既存の`days_text`の指摘 1 件のみが残る)。
- コミットメッセージの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。マージは利用者の指示を待つ(PR を作って止まる)。

## Review Focus

1. **Shift_JIS にできない文字を書き出す**(絵文字など): 黙って`?`にせず、書き出しを止めて、どの文字かを通知する(Task 5)。
2. **同じ見出しが 2 列ある CSV**: 先の列を使い、もう一方は`割り当てなし`にする。落ちない(Task 1・2)。
3. **ヘッダー行しかない・タイトル列が空の行だけ**の CSV: 「取り込める行がありません」。落ちない(Task 2)。
4. **壊れた`csv_profiles`**(config の手編集): 壊れた 1 件だけ捨て、アプリは起動する(Task 1)。
5. **日付だけの実績・終了が開始より前の実績**: 入れず件数を通知する。落ちない(Task 3)。

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `src/projectapp/csv_profile.py`(新) | `CsvField`・`CsvColumn`・`CsvProfile`・`SMARTSHEET`、別名・推測・検証・config の変換 |
| `src/projectapp/csv_import.py` | プロファイルで読む`parse_csv`、`sniff_table`、新しい項目、`cell_ok` |
| `src/projectapp/csv_export.py` | プロファイルで書く`build_table`、`encode_table`、`write_table`(`build_tsv`・`write_tsv`は互換のために残す) |
| `src/projectapp/csv_dialog.py`(新) | 取り込みのダイアログ・書き出しのダイアログ |
| `src/projectapp/config.py` | `load_csv_profiles`・`save_csv_profiles`・`load_csv_profile_last`・`save_csv_profile_last` |
| `src/projectapp/views.py` | `import_csv`・`export_tsv`をダイアログ経由にする。メニューの文言 |
| `test/test_csv_profile.py`(新)・`test_csv_import.py`・`test_csv_export.py`・`test_csv_dialog.py`(新)・`test_views.py`・`test_config.py` | テスト |
| `.claude/spec/import-export.md`・`docs/requests.md`・`.claude/MEMORY.md` | 仕様・状態・作業記録 |

---

### Task 1: プロファイルの型・別名・推測・検証・config

**Files:**
- Create: `src/projectapp/csv_profile.py`
- Modify: `src/projectapp/config.py`(末尾に追加)
- Test: `test/test_csv_profile.py`(新)、`test/test_config.py`(追加)

**Interfaces:**
- Produces(後の Task が使う。名前・型はこのとおり):
  - `class CsvField(StrEnum)`: `WBS="wbs"`・`TITLE="title"`・`OWNER="owner"`・`START="start"`・`END="end"`・`DURATION="duration"`・`PROGRESS="progress"`・`EFFORT="effort"`・`STATUS="status"`・`ACTUAL_START="actual_start"`・`ACTUAL_END="actual_end"`・`CATEGORY="category"`
  - `FIELD_LABELS: dict[CsvField, str]`(ダイアログの表示名)、`IMPORT_FIELDS: tuple[CsvField, ...]`(`DURATION`を除く、表示順)、`EXPORT_FIELDS: tuple[CsvField, ...]`(全項目、表示順)
  - `@dataclass(frozen=True) CsvColumn(field: CsvField, header: str)`
  - `@dataclass(frozen=True) CsvProfile(name: str, columns: tuple[CsvColumn, ...], delimiter: str = ",", encoding: str = "utf-8", date_format: str = "ymd-dash", owner_separator: str = ";", blank_rows: int = 0)`、プロパティ`headers: dict[CsvField, str]`
  - `SMARTSHEET: CsvProfile`、`SMARTSHEET_NAME = "Smartsheet"`
  - 定数`DELIMITERS`・`ENCODINGS`・`DATE_FORMATS`・`MAX_PROFILES = 20`・`MAX_PROFILE_NAME = 30`・`MAX_HEADER = 40`・`MAX_SEPARATOR = 3`
  - `header_key(text: str) -> str`(NFKC・空白除去・小文字)
  - `guess_columns(header: list[str]) -> tuple[CsvColumn, ...]`(別名の表で推測。見出しの文字をそのまま`header`にする)
  - `resolve_columns(profile: CsvProfile, header: list[str]) -> dict[CsvField, int]`(項目 → 列の位置。プロファイルの見出しで探し、なければ別名。同じ見出しが複数なら先の列)
  - `best_profile(header: list[str], profiles: list[CsvProfile]) -> CsvProfile | None`
  - `validate_profile(profile: CsvProfile) -> str | None`(問題の文言。なければ None)
  - `profile_to_config(profile) -> dict`、`profile_from_config(raw: object) -> CsvProfile | None`、`profiles_from_config(raw: object) -> list[CsvProfile]`
  - config: `load_csv_profiles(base_dir=BASE_DIR) -> list[CsvProfile]`、`save_csv_profiles(profiles, base_dir=BASE_DIR) -> None`、`load_csv_profile_last(base_dir=BASE_DIR) -> str | None`、`save_csv_profile_last(name: str | None, base_dir=BASE_DIR) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_csv_profile.py`:

```python
import pytest

from projectapp.csv_profile import (
    SMARTSHEET,
    CsvColumn,
    CsvField,
    CsvProfile,
    best_profile,
    guess_columns,
    header_key,
    profile_from_config,
    profile_to_config,
    profiles_from_config,
    resolve_columns,
    validate_profile,
)


def profile(*pairs: tuple[CsvField, str], name: str = "自作", **kw: object) -> CsvProfile:
    return CsvProfile(name, tuple(CsvColumn(f, h) for f, h in pairs), **kw)  # type: ignore[arg-type]


def test_header_key_ignores_width_case_and_spaces() -> None:
    assert header_key(" Ｔask  Name ") == "taskname"


def test_smartsheet_has_the_template_columns_in_order() -> None:
    assert [c.header for c in SMARTSHEET.columns] == [
        "WBS 番号", "タスクのタイトル", "タスクオーナー", "開始日", "期限", "期間", "タスク完了率",
    ]
    assert SMARTSHEET.delimiter == "\t" and SMARTSHEET.blank_rows == 2
    assert SMARTSHEET.owner_separator == "" and SMARTSHEET.date_format == "ja"


def test_guess_columns_uses_aliases_and_keeps_the_original_header() -> None:
    cols = guess_columns(["No", "Task Name", "Assignee", "Start Date", "Due", "% Complete", "Hours", "メモ"])
    assert {c.field: c.header for c in cols} == {
        CsvField.TITLE: "Task Name",
        CsvField.OWNER: "Assignee",
        CsvField.START: "Start Date",
        CsvField.END: "Due",
        CsvField.PROGRESS: "% Complete",
        CsvField.EFFORT: "Hours",
    }


def test_guess_columns_uses_a_field_once_even_with_duplicate_headers() -> None:
    cols = guess_columns(["名前", "名前", "担当"])
    assert [c.field for c in cols].count(CsvField.TITLE) == 1


def test_resolve_columns_prefers_the_profile_header_then_aliases() -> None:
    p = profile((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"))
    assert resolve_columns(p, ["x", "件名", "担当者"]) == {CsvField.TITLE: 1, CsvField.OWNER: 2}


def test_resolve_columns_takes_the_first_of_duplicate_headers() -> None:
    p = profile((CsvField.TITLE, "名前"))
    assert resolve_columns(p, ["名前", "名前"]) == {CsvField.TITLE: 0}


def test_smartsheet_accepts_the_other_owner_spelling() -> None:
    header = ["WBS 番号", "タスクのタイトル", "タスクのオーナー"]
    assert resolve_columns(SMARTSHEET, header)[CsvField.OWNER] == 2


def test_best_profile_needs_half_of_the_columns_to_match() -> None:
    a = profile((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), name="A")
    b = profile((CsvField.TITLE, "Subject"), (CsvField.OWNER, "Who"), name="B")
    assert best_profile(["件名", "担当", "開始"], [a, b]) is a
    assert best_profile(["x", "y"], [a, b]) is None


@pytest.mark.parametrize(
    ("bad", "word"),
    [
        (profile((CsvField.OWNER, "担当")), "タスク名"),
        (profile((CsvField.TITLE, "a"), (CsvField.TITLE, "b")), "重複"),
        (profile((CsvField.TITLE, "")), "見出し"),
        (profile((CsvField.TITLE, "a"), name=""), "名前"),
        (profile((CsvField.TITLE, "a"), name="Smartsheet"), "予約"),
        (profile((CsvField.TITLE, "a"), delimiter="|"), "区切り"),
        (profile((CsvField.TITLE, "a"), encoding="latin-1"), "文字コード"),
        (profile((CsvField.TITLE, "a"), owner_separator="abcd"), "担当の区切り"),
    ],
)
def test_validate_profile_rejects(bad: CsvProfile, word: str) -> None:
    assert word in (validate_profile(bad) or "")


def test_validate_profile_accepts_a_good_one() -> None:
    assert validate_profile(profile((CsvField.TITLE, "件名"), delimiter=";", encoding="cp932")) is None


def test_config_round_trip() -> None:
    p = profile((CsvField.TITLE, "件名"), (CsvField.EFFORT, "工数"), delimiter=";", encoding="utf-8-sig", date_format="ymd-slash", owner_separator="/")
    assert profile_from_config(profile_to_config(p)) == p


def test_profiles_from_config_drops_only_the_broken_ones() -> None:
    good = profile_to_config(profile((CsvField.TITLE, "件名"), name="良"))
    dup = profile_to_config(profile((CsvField.TITLE, "別"), name="良"))
    raw = [good, {"name": "壊", "columns": "x"}, 5, dup, {"name": "無題"}]
    assert [p.name for p in profiles_from_config(raw)] == ["良"]
    assert profiles_from_config("x") == [] and profiles_from_config(None) == []
```

`test/test_config.py`の末尾に追加(`tmp_path`を使う既存のテストの流儀に合わせる):

```python
def test_csv_profiles_round_trip_and_survive_a_broken_file(tmp_path) -> None:
    from projectapp.config import (
        load_csv_profile_last, load_csv_profiles, save_csv_profile_last, save_csv_profiles,
    )
    from projectapp.csv_profile import CsvColumn, CsvField, CsvProfile

    p = CsvProfile("自作", (CsvColumn(CsvField.TITLE, "件名"),))
    assert load_csv_profiles(tmp_path) == []
    save_csv_profiles([p], tmp_path)
    assert load_csv_profiles(tmp_path) == [p]
    save_csv_profile_last("自作", tmp_path)
    assert load_csv_profile_last(tmp_path) == "自作"
    (tmp_path / "config.json").write_text("{broken", encoding="utf-8")
    assert load_csv_profiles(tmp_path) == [] and load_csv_profile_last(tmp_path) is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_profile.py test/test_config.py -q`
Expected: FAIL(`projectapp.csv_profile`がない)

- [ ] **Step 3: 実装する**

`src/projectapp/csv_profile.py`:

```python
"""CSV・TSV の列の対応(プロファイル)。項目・別名・推測・検証・config の変換。NiceGUI には依存しない。"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

SMARTSHEET_NAME = "Smartsheet"
DELIMITERS = (",", "\t", ";")
ENCODINGS = ("utf-8", "utf-8-sig", "cp932")
DATE_FORMATS = ("ja", "ymd-dash", "ymd-slash")
MAX_PROFILES = 20
MAX_PROFILE_NAME = 30
MAX_HEADER = 40
MAX_SEPARATOR = 3


class CsvField(StrEnum):
    WBS = "wbs"
    TITLE = "title"
    OWNER = "owner"
    START = "start"
    END = "end"
    DURATION = "duration"
    PROGRESS = "progress"
    EFFORT = "effort"
    STATUS = "status"
    ACTUAL_START = "actual_start"
    ACTUAL_END = "actual_end"
    CATEGORY = "category"


FIELD_LABELS = {
    CsvField.WBS: "WBS 番号",
    CsvField.TITLE: "タスク名",
    CsvField.OWNER: "担当",
    CsvField.START: "開始日",
    CsvField.END: "期限",
    CsvField.DURATION: "期間",
    CsvField.PROGRESS: "完了率",
    CsvField.EFFORT: "工数",
    CsvField.STATUS: "状態",
    CsvField.ACTUAL_START: "開始実績",
    CsvField.ACTUAL_END: "終了実績",
    CsvField.CATEGORY: "カテゴリ",
}
EXPORT_FIELDS = tuple(CsvField)  # ダイアログの表示順
IMPORT_FIELDS = tuple(f for f in CsvField if f is not CsvField.DURATION)  # 期間は読まない

ALIASES: dict[CsvField, tuple[str, ...]] = {  # 見出しの別名(header_key にそろえた形)
    CsvField.WBS: ("wbs番号", "wbs", "wbsno", "no", "番号"),
    CsvField.TITLE: ("タスクのタイトル", "タスク名", "タスク", "名前", "件名", "タイトル", "task", "taskname", "title", "name", "subject"),
    CsvField.OWNER: ("タスクオーナー", "タスクのオーナー", "担当", "担当者", "オーナー", "assignee", "owner", "assignedto", "resource"),
    CsvField.START: ("開始日", "開始", "着手日", "start", "startdate", "begin"),
    CsvField.END: ("期限", "終了日", "終了", "完了日", "納期", "due", "duedate", "end", "enddate", "finish"),
    CsvField.DURATION: ("期間", "duration", "days"),
    CsvField.PROGRESS: ("タスク完了率", "完了率", "進捗", "進捗率", "%complete", "progress", "complete"),
    CsvField.EFFORT: ("工数", "見積", "見積もり", "予定工数", "effort", "hours", "estimate"),
    CsvField.STATUS: ("状態", "ステータス", "status", "state"),
    CsvField.ACTUAL_START: ("開始実績", "実績開始", "actualstart"),
    CsvField.ACTUAL_END: ("終了実績", "実績終了", "actualend", "actualfinish"),
    CsvField.CATEGORY: ("カテゴリ", "カテゴリー", "プロジェクトコード", "category", "projectcode"),
}


@dataclass(frozen=True)
class CsvColumn:
    field: CsvField
    header: str


@dataclass(frozen=True)
class CsvProfile:
    name: str
    columns: tuple[CsvColumn, ...]
    delimiter: str = ","
    encoding: str = "utf-8"
    date_format: str = "ymd-dash"
    owner_separator: str = ";"  # 複数の担当の区切り。空は 1 人だけ(取り込みは分けず、書き出しは筆頭のみ)
    blank_rows: int = 0  # 見出しの次に入れる空行の数(Smartsheet のテンプレートだけ)

    @property
    def headers(self) -> dict[CsvField, str]:
        return {c.field: c.header for c in self.columns}


SMARTSHEET = CsvProfile(
    SMARTSHEET_NAME,
    (
        CsvColumn(CsvField.WBS, "WBS 番号"),
        CsvColumn(CsvField.TITLE, "タスクのタイトル"),
        CsvColumn(CsvField.OWNER, "タスクオーナー"),
        CsvColumn(CsvField.START, "開始日"),
        CsvColumn(CsvField.END, "期限"),
        CsvColumn(CsvField.DURATION, "期間"),
        CsvColumn(CsvField.PROGRESS, "タスク完了率"),
    ),
    delimiter="\t",
    encoding="utf-8",
    date_format="ja",
    owner_separator="",
    blank_rows=2,
)


def header_key(text: str) -> str:
    """見出しの比較用。全角を半角に、空白を除き、小文字にする。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def guess_columns(header: list[str]) -> tuple[CsvColumn, ...]:
    """見出しから、別名の表で項目を推測する。同じ項目は先に見つかった列だけ。見出しは元の文字のまま。"""
    found: dict[CsvField, str] = {}
    for cell in header:
        key = header_key(cell)
        if not key:
            continue
        for field_, names in ALIASES.items():
            if field_ not in found and field_ is not CsvField.DURATION and key in names:
                found[field_] = cell.strip()
                break
    return tuple(CsvColumn(f, found[f]) for f in IMPORT_FIELDS if f in found)


def resolve_columns(profile: CsvProfile, header: list[str]) -> dict[CsvField, int]:
    """プロファイルの各項目が、見出しのどの列(0 始まり)か。プロファイルの見出し、なければ別名で探す。同じ見出しは先の列。"""
    keys = [header_key(cell) for cell in header]
    result: dict[CsvField, int] = {}
    for column in profile.columns:
        if column.field is CsvField.DURATION:
            continue
        wanted = header_key(column.header)
        names = (wanted, *ALIASES[column.field])
        for name in names:
            if name and name in keys:
                result[column.field] = keys.index(name)
                break
    return result


def best_profile(header: list[str], profiles: list[CsvProfile]) -> CsvProfile | None:
    """見出しに最もよく合うプロファイル。列の半分以上が一致し、タスク名の列があるものだけ。"""
    keys = {header_key(cell) for cell in header}
    best: tuple[int, CsvProfile] | None = None
    for p in profiles:
        cols = [c for c in p.columns if c.field is not CsvField.DURATION]
        hits = sum(header_key(c.header) in keys for c in cols)
        title_hit = any(c.field is CsvField.TITLE and header_key(c.header) in keys for c in cols)
        if title_hit and cols and hits * 2 >= len(cols) and (best is None or hits > best[0]):
            best = (hits, p)
    return best[1] if best else None


def validate_profile(profile: CsvProfile) -> str | None:
    """問題の文言(なければ None)。"""
    name = profile.name.strip()
    if not 1 <= len(name) <= MAX_PROFILE_NAME:
        return f"プロファイルの名前は 1〜{MAX_PROFILE_NAME} 文字にしてください"
    if name == SMARTSHEET_NAME:
        return f"「{SMARTSHEET_NAME}」は予約された名前です"
    if profile.delimiter not in DELIMITERS:
        return "区切りはカンマ・タブ・セミコロンから選んでください"
    if profile.encoding not in ENCODINGS:
        return "文字コードは UTF-8・UTF-8(BOM 付き)・Shift_JIS から選んでください"
    if profile.date_format not in DATE_FORMATS:
        return "日付の書式を選んでください"
    if len(profile.owner_separator) > MAX_SEPARATOR:
        return f"担当の区切りは {MAX_SEPARATOR} 文字までです"
    fields = [c.field for c in profile.columns]
    if len(fields) != len(set(fields)):
        return "同じ項目が重複しています"
    if CsvField.TITLE not in fields:
        return "タスク名の列が必要です"
    for column in profile.columns:
        if not 1 <= len(column.header.strip()) <= MAX_HEADER:
            return f"見出しは 1〜{MAX_HEADER} 文字にしてください"
    return None


def profile_to_config(profile: CsvProfile) -> dict:
    return {
        "name": profile.name,
        "columns": [{"field": c.field.value, "header": c.header} for c in profile.columns],
        "delimiter": profile.delimiter,
        "encoding": profile.encoding,
        "date_format": profile.date_format,
        "owner_separator": profile.owner_separator,
    }


def profile_from_config(raw: object) -> CsvProfile | None:
    """config の 1 件を読む。形が違う・検証に通らないときは None。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("columns"), list):
        return None
    try:
        columns = tuple(
            CsvColumn(CsvField(c["field"]), str(c["header"]).strip()) for c in raw["columns"]
        )
        profile = CsvProfile(
            str(raw["name"]).strip(),
            columns,
            str(raw.get("delimiter", ",")),
            str(raw.get("encoding", "utf-8")),
            str(raw.get("date_format", "ymd-dash")),
            str(raw.get("owner_separator", ";")),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return profile if validate_profile(profile) is None else None


def profiles_from_config(raw: object) -> list[CsvProfile]:
    """config の配列を読む。壊れた 1 件と、名前が重複する後の 1 件は捨てる。上限を超えた分も捨てる。"""
    if not isinstance(raw, list):
        return []
    result: list[CsvProfile] = []
    for item in raw:
        found = profile_from_config(item)
        if found is not None and all(p.name != found.name for p in result):
            result.append(found)
    return result[:MAX_PROFILES]
```

`src/projectapp/config.py`の末尾に追加(先頭の import に`from projectapp.csv_profile import CsvProfile, profile_to_config, profiles_from_config`を足す。循環しないこと: `csv_profile`は`config`を import しない):

```python
def load_csv_profiles(base_dir: Path = BASE_DIR) -> list[CsvProfile]:
    """保存した CSV のプロファイル(`Smartsheet`を含まない)。読めないときは空。"""
    try:
        return profiles_from_config(read_config(base_dir).get("csv_profiles"))
    except (OSError, ValueError):
        return []


def save_csv_profiles(profiles: list[CsvProfile], base_dir: Path = BASE_DIR) -> None:
    update_config({"csv_profiles": [profile_to_config(p) for p in profiles]}, base_dir)


def load_csv_profile_last(base_dir: Path = BASE_DIR) -> str | None:
    """直近に使ったプロファイル名。読めない・文字列でないときは None。"""
    try:
        value = read_config(base_dir).get("csv_profile_last")
    except (OSError, ValueError):
        return None
    return value if isinstance(value, str) and value else None


def save_csv_profile_last(name: str | None, base_dir: Path = BASE_DIR) -> None:
    update_config({"csv_profile_last": name or ""}, base_dir)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_profile.py test/test_config.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test && uvx ruff check src test
git add src/projectapp/csv_profile.py src/projectapp/config.py test/test_csv_profile.py test/test_config.py
git commit -m "feat: CSV のプロファイル(列の対応)の型・推測・検証・config を足す"
```

---

### Task 2: 取り込みをプロファイルで読む形に一般化する(Smartsheet の回帰を保つ)

**Files:**
- Modify: `src/projectapp/csv_import.py`
- Test: `test/test_csv_import.py`(既存はそのまま通す。追加する)

**Interfaces:**
- Consumes: Task 1 の`CsvField`・`CsvProfile`・`SMARTSHEET`・`resolve_columns`・`header_key`・`ALIASES`
- Produces:
  - `parse_csv(text: str, name: str, holidays: dict[date, str], today: date | None = None, profile: CsvProfile = SMARTSHEET, delimiter: str | None = None, header_row: int | None = None) -> CsvImport`(`delimiter`が None なら、ヘッダー行からタブかカンマを自動判定〔従来どおり〕。`header_row`が None なら、プロファイルのタスク名の見出しを含む最初の行〔従来どおり〕。`CsvImportError`は従来と同じ)
  - `@dataclass(frozen=True) TableSniff(text: str, encoding: str, delimiter: str, header_row: int, header: list[str], rows: list[list[str]])`(`rows`はヘッダーの次からの空でない先頭 5 行)
  - `sniff_table(data: bytes, encoding: str | None = None, delimiter: str | None = None, header_row: int | None = None) -> TableSniff`(エンコーディング None は`utf-8-sig`→`cp932`。区切り None は自動。ヘッダー行 None は、タスク名の別名を含む最初の行、なければ最初の空でない行。読めなければ`CsvImportError`)
  - `read_table(path)`は従来のまま(テキストを返す)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_csv_import.py`に追加)

```python
from projectapp.csv_profile import CsvColumn, CsvField, CsvProfile
from projectapp.csv_import import sniff_table


def custom(*pairs: tuple[CsvField, str], **kw: object) -> CsvProfile:
    return CsvProfile("自作", tuple(CsvColumn(f, h) for f, h in pairs), **kw)  # type: ignore[arg-type]


def test_a_custom_profile_reads_its_own_headers_and_delimiter() -> None:
    text = "件名;担当;開始\n設計;田中;2026-10-05\n"
    p = custom((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), (CsvField.START, "開始"), delimiter=";")
    result = parse_csv(text, "x", {}, profile=p, delimiter=";")
    task = result.project.all_tasks()[0]
    assert task.name == "設計" and task.assignee_names == ["田中"]
    assert task.planned_start is not None and task.planned_start.date() == date(2026, 10, 5)


def test_without_a_wbs_column_rows_with_only_a_title_become_sections() -> None:
    text = "件名,担当\n設計フェーズ,\nやること,田中\n"
    p = custom((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"))
    result = parse_csv(text, "x", {}, profile=p, delimiter=",")
    assert [s.name for s in result.project.sections] == ["設計フェーズ"]
    assert [t.name for t in result.project.sections[0].tasks] == ["やること"]


def test_header_row_can_be_chosen() -> None:
    text = "メモ\n\n件名,担当\n設計,田中\n"
    p = custom((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"))
    result = parse_csv(text, "x", {}, profile=p, delimiter=",", header_row=2)
    assert [t.name for t in result.project.all_tasks()] == ["設計"]


def test_only_a_header_row_has_nothing_to_import() -> None:
    p = custom((CsvField.TITLE, "件名"))
    with pytest.raises(CsvImportError):
        parse_csv("件名\n", "x", {}, profile=p, delimiter=",")


def test_duplicate_headers_use_the_first_column() -> None:
    p = custom((CsvField.TITLE, "名前"))
    result = parse_csv("名前,名前\nA,B\n", "x", {}, profile=p, delimiter=",")
    assert [t.name for t in result.project.all_tasks()] == ["A"]


def test_sniff_table_detects_encoding_delimiter_and_header() -> None:
    data = "メモ\n件名;担当\n設計;田中\n実装;鈴木\n".encode("cp932")
    s = sniff_table(data)
    assert (s.encoding, s.delimiter, s.header_row) == ("cp932", ";", 1)
    assert s.header == ["件名", "担当"] and s.rows == [["設計", "田中"], ["実装", "鈴木"]]


def test_sniff_table_falls_back_to_the_first_nonblank_line() -> None:
    s = sniff_table("\n\nA,B\n1,2\n".encode("utf-8"))
    assert s.header_row == 2 and s.header == ["A", "B"]


def test_sniff_table_honours_explicit_choices() -> None:
    data = "a;b,c\n1;2,3\n".encode("utf-8")
    assert sniff_table(data, delimiter=",").header == ["a;b", "c"]


def test_sniff_table_rejects_undecodable_data() -> None:
    with pytest.raises(CsvImportError):
        sniff_table(b"\xff\xfe\x00\x81")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_import.py -q`
Expected: 追加分が FAIL(`sniff_table`・`profile=`がない)。既存は PASS のまま。

- [ ] **Step 3: 実装する**

`csv_import.py`を次のとおり変える。

1. import に追加: `from projectapp.csv_profile import ALIASES, SMARTSHEET, CsvField, CsvProfile, header_key, resolve_columns`。`TITLE_COLUMN`・`COLUMN_NAMES`は残す(`csv_export`が`WBS_NUMBER`・`WBS_SEPARATOR`を使う。ほかの参照は`grep -rn "TITLE_COLUMN\|COLUMN_NAMES" src test`で確認して、使われていなければ削除してよい)。

2. `_rows`を置き換える:

```python
def detect_delimiter(line: str) -> str:
    """ヘッダー行で最も多い区切り(タブ・カンマ・セミコロン)。同数ならタブ、次にカンマ。"""
    counts = {d: line.count(d) for d in ("\t", ",", ";")}
    return max(counts, key=lambda d: (counts[d], d == "\t", d == ","))


def _find_header(lines: list[str], profile: CsvProfile) -> int | None:
    """プロファイルのタスク名の見出しを含む最初の行(従来どおり、行全体の部分一致)。"""
    wanted = header_key(profile.headers.get(CsvField.TITLE, ""))
    if not wanted:
        return None
    return next((i for i, line in enumerate(lines) if wanted in header_key(line)), None)


def _rows(
    text: str,
    profile: CsvProfile,
    delimiter: str | None,
    header_row: int | None,
) -> list["_Row | None"]:
    """ヘッダー行を探し、そのあとの行を読む。空行は読み飛ばし、タイトルのない行は None で返す。"""
    lines = text.splitlines()
    header_at = header_row if header_row is not None else _find_header(lines, profile)
    title_header = profile.headers.get(CsvField.TITLE, "タスク名")
    if header_at is None or not 0 <= header_at < len(lines):
        raise CsvImportError(f"「{title_header}」の列が見つかりません")
    sep = delimiter or detect_delimiter(lines[header_at])
    table = csv.reader(io.StringIO("\n".join(lines[header_at:])), delimiter=sep)
    header = next(table)
    columns = resolve_columns(profile, header)
    if CsvField.TITLE not in columns:
        raise CsvImportError(f"「{title_header}」の列が見つかりません")
    rows: list[_Row | None] = []
    for cells in table:
        if not any(cell.strip() for cell in cells):
            continue

        def cell(field_: CsvField) -> str:
            index = columns.get(field_)
            return cells[index].strip() if index is not None and index < len(cells) else ""

        row = _Row(
            _plain(cell(CsvField.WBS)),
            cell(CsvField.TITLE),
            cell(CsvField.OWNER),
            cell(CsvField.START),
            cell(CsvField.END),
            cell(CsvField.PROGRESS),
        )
        rows.append(row if tidy_task_name(row.title) else None)
    return rows
```

3. `parse_csv`のシグネチャを`(text, name, holidays, today=None, profile=SMARTSHEET, delimiter=None, header_row=None)`にし、`for row in _rows(text)`を`_rows(text, profile, delimiter, header_row)`に替える。`_Builder`には`profile`を渡さない(Task 3 で`owner_separator`などを渡す)。

4. `TableSniff`と`sniff_table`を足す:

```python
@dataclass(frozen=True)
class TableSniff:
    text: str
    encoding: str
    delimiter: str
    header_row: int
    header: list[str]
    rows: list[list[str]]  # ヘッダーの次からの、空でない先頭 5 行


PREVIEW_ROWS = 5


def decode_table(data: bytes, encoding: str | None = None) -> tuple[str, str]:
    """(テキスト, 文字コード)。`encoding`が None なら UTF-8(BOM 可)を先に試し、読めなければ Shift_JIS。"""
    for name in (encoding,) if encoding else ("utf-8-sig", "cp932"):
        try:
            return data.decode(name), name
        except UnicodeDecodeError:
            continue
    raise CsvImportError("文字コードを判定できません(UTF-8 か Shift_JIS にしてください)")


def sniff_table(
    data: bytes,
    encoding: str | None = None,
    delimiter: str | None = None,
    header_row: int | None = None,
) -> TableSniff:
    """文字コード・区切り・ヘッダー行を判定し、見出しと先頭の数行を返す(取り込みのダイアログ用)。"""
    text, used = decode_table(data, encoding)
    lines = text.splitlines()
    if header_row is None:
        wanted = {n for n in ALIASES[CsvField.TITLE]}
        header_row = next(
            (i for i, line in enumerate(lines) if any(header_key(c) in wanted for c in re.split(r"[\t,;]", line))),
            next((i for i, line in enumerate(lines) if line.strip()), 0),
        )
    if not lines or not 0 <= header_row < len(lines):
        raise CsvImportError("取り込める行がありません")
    sep = delimiter or detect_delimiter(lines[header_row])
    table = csv.reader(io.StringIO("\n".join(lines[header_row:])), delimiter=sep)
    header = [c.strip() for c in next(table, [])]
    rows = [r for r in table if any(c.strip() for c in r)][:PREVIEW_ROWS]
    return TableSniff(text, used, sep, header_row, header, rows)
```

`read_table`は、`decode_table(data)[0]`を返す形に直して重複を減らす(エラー文言は同じ)。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_import.py -q`
Expected: すべて PASS(既存の Smartsheet のテストも変更なしで通る)

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test && uvx ruff check src test
git add src/projectapp/csv_import.py test/test_csv_import.py
git commit -m "feat: CSV の取り込みを、プロファイル・区切り・ヘッダー行で読む形に一般化する"
```

---

### Task 3: 取り込みの新しい項目(工数・状態・実績・カテゴリ・複数の担当)と、プレビューの検査

**Files:**
- Modify: `src/projectapp/csv_import.py`
- Test: `test/test_csv_import.py`

**Interfaces:**
- Consumes: Task 2 の`parse_csv(..., profile=)`、`_Row`、`_Builder`
- Produces:
  - `CsvImport`に`invalid_values: int = 0`(読めない工数・状態・実績・入れなかった実績の数)を追加(既存の位置引数の呼び出しを壊さないよう、末尾にデフォルトつき)
  - `parse_effort(text) -> float | None`、`parse_status(text) -> Status | None`、`parse_datetime(text) -> datetime | None`(日付だけは 00:00。`date_only(text) -> bool`)
  - `cell_ok(field: CsvField, text: str) -> bool`(空は True。プレビューで読めない値を赤くするために使う)
  - `summary`が`読めない値 n 件`を足す

- [ ] **Step 1: 失敗するテストを書く**(`test/test_csv_import.py`に追加。`custom`は Task 2 で定義済み)

```python
from projectapp.csv_import import cell_ok, parse_datetime, parse_effort, parse_status
from projectapp.models import Status


@pytest.mark.parametrize(
    ("text", "want"),
    [("8", 8.0), ("8.5", 8.5), ("8h", 8.0), ("8.5時間", 8.5), (" 12 ", 12.0), ("０", None), ("-1", None), ("abc", None), ("10001", None), ("", None)],
)
def test_parse_effort(text: str, want: float | None) -> None:
    assert parse_effort(text) == want


@pytest.mark.parametrize(
    ("text", "want"),
    [("未着手", Status.NOT_STARTED), ("実行中", Status.RUNNING), ("一時停止", Status.PAUSED), ("終了", Status.DONE),
     ("Done", Status.DONE), ("in progress", Status.RUNNING), ("on hold", Status.PAUSED), ("Not Started", Status.NOT_STARTED), ("???", None)],
)
def test_parse_status(text: str, want: Status | None) -> None:
    assert parse_status(text) == want


def test_parse_datetime_accepts_date_and_time() -> None:
    assert parse_datetime("2026-10-05 09:30") == datetime(2026, 10, 5, 9, 30)
    assert parse_datetime("2026/10/5T9:05") == datetime(2026, 10, 5, 9, 5)
    assert parse_datetime("2026-10-05") == datetime(2026, 10, 5)
    assert parse_datetime("きのう") is None


def test_cell_ok_flags_unreadable_values_only() -> None:
    assert cell_ok(CsvField.START, "") and cell_ok(CsvField.START, "2026-10-05")
    assert not cell_ok(CsvField.START, "あした")
    assert not cell_ok(CsvField.EFFORT, "x") and not cell_ok(CsvField.STATUS, "x")
    assert cell_ok(CsvField.TITLE, "なんでも")


FULL = custom(
    (CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), (CsvField.START, "開始"), (CsvField.END, "期限"),
    (CsvField.EFFORT, "工数"), (CsvField.STATUS, "状態"), (CsvField.ACTUAL_START, "実績開始"),
    (CsvField.ACTUAL_END, "実績終了"), (CsvField.CATEGORY, "区分"),
    delimiter=",", owner_separator=";",
)
FULL_HEADER = "件名,担当,開始,期限,工数,状態,実績開始,実績終了,区分"


def run(*lines: str) -> CsvImport:
    return parse_csv("\n".join([FULL_HEADER, *lines]), "x", {}, profile=FULL, delimiter=",")


def test_multiple_owners_are_split_by_the_profile_separator() -> None:
    result = run("A,田中; 鈴木 ;,,,,,,,")
    task = result.project.all_tasks()[0]
    assert task.assignee_names == ["田中", "鈴木"] and all(a.allocation == 1.0 for a in task.assignees)
    assert [m.name for m in result.project.members] == ["田中", "鈴木"]


def test_an_empty_separator_keeps_the_whole_value_as_one_name() -> None:
    p = custom((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), delimiter=",", owner_separator="")
    result = parse_csv("件名,担当\nA,田中;鈴木\n", "x", {}, profile=p, delimiter=",")
    assert result.project.all_tasks()[0].assignee_names == ["田中;鈴木"]


def test_effort_wins_over_the_period_and_keeps_the_deadline() -> None:
    result = run("A,,2026-10-05,2026-10-09,3,,,,")
    task = result.project.all_tasks()[0]
    assert task.effort_hours == 3.0 and task.planned_end_manual
    assert task.planned_end is not None and task.planned_end.date() == date(2026, 10, 9)


def test_status_wins_over_progress_and_done_sets_full_progress() -> None:
    p = custom((CsvField.TITLE, "件名"), (CsvField.PROGRESS, "率"), (CsvField.STATUS, "状態"), delimiter=",")
    result = parse_csv("件名,率,状態\nA,10%,終了\nB,,未着手\nC,50,実行中\n", "x", {}, profile=p, delimiter=",")
    a, b, c = result.project.all_tasks()
    assert (a.status, a.progress) == (Status.DONE, 100)
    assert (b.status, b.progress) == (Status.NOT_STARTED, None)
    assert (c.status, c.progress) == (Status.RUNNING, 50)


def test_actuals_make_one_interval_and_date_only_uses_work_hours() -> None:
    result = run("A,,,,,,2026-10-05,2026-10-06,", "B,,,,,,2026-10-05 10:00,2026-10-05 12:30,")
    a, b = result.project.all_tasks()
    assert len(a.actuals) == 1 and a.actuals[0].start == datetime(2026, 10, 5, 9, 0)
    assert a.actuals[0].end is not None and a.actuals[0].end.date() == date(2026, 10, 6)
    assert b.actuals[0].start == datetime(2026, 10, 5, 10, 0) and b.actuals[0].end == datetime(2026, 10, 5, 12, 30)


def test_bad_actuals_are_skipped_and_counted() -> None:
    result = run("A,,,,,,,2026-10-06,", "B,,,,,,2026-10-06,2026-10-05,", "C,,,,x,ぶ,,,")
    assert all(not t.actuals for t in result.project.all_tasks())
    assert result.invalid_values == 4  # 終了だけ・終了が開始より前・読めない工数・読めない状態


def test_an_open_actual_marks_the_task_running() -> None:
    result = run("A,,,,,,2026-10-05 10:00,,")
    task = result.project.all_tasks()[0]
    assert task.status is Status.RUNNING and task.actuals[0].end is None


def test_categories_are_created_once_by_name() -> None:
    result = run("A,,,,,,,,開発", "B,,,,,,,,開発", "C,,,,,,,,運用", "D,,,,,,,,")
    cats = result.project.categories
    assert [c.name for c in cats] == ["開発", "運用"]
    a, b, c, d = result.project.all_tasks()
    assert a.category_id == b.category_id == cats[0].id and c.category_id == cats[1].id and d.category_id is None


def test_summary_mentions_unreadable_values() -> None:
    result = run("C,,,,x,,,,")
    assert "読めない値 1 件" in summary(result)
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_import.py -q`
Expected: 追加分が FAIL

- [ ] **Step 3: 実装する**

1. import に`Actual`・`Category`・`Status`・`MAX_CATEGORY_NAME_LENGTH`を足す(`models`から)。

2. 読み取りの関数:

```python
MAX_EFFORT_HOURS = 10000
_EFFORT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h|時間)?", re.IGNORECASE)
_DATETIME = re.compile(r"(.+?)(?:[T\s]+(\d{1,2}):(\d{2}))?")
STATUS_WORDS = {
    "未着手": Status.NOT_STARTED, "notstarted": Status.NOT_STARTED, "todo": Status.NOT_STARTED,
    "実行中": Status.RUNNING, "inprogress": Status.RUNNING, "running": Status.RUNNING,
    "一時停止": Status.PAUSED, "onhold": Status.PAUSED, "paused": Status.PAUSED,
    "終了": Status.DONE, "完了": Status.DONE, "done": Status.DONE, "complete": Status.DONE, "completed": Status.DONE,
}


def parse_effort(text: str) -> float | None:
    """`8`・`8.5`・`8h`・`8.5時間` を時間で読む。0 以下・1 万時間超・読めない値は None。"""
    found = _EFFORT.fullmatch(_plain(text))
    if found is None:
        return None
    value = float(found.group(1))
    return value if 0 < value <= MAX_EFFORT_HOURS else None


def parse_status(text: str) -> Status | None:
    return STATUS_WORDS.get(header_key(text))


def date_only(text: str) -> bool:
    return not re.search(r"\d{1,2}:\d{2}", _plain(text))


def parse_datetime(text: str) -> datetime | None:
    """`2026-10-05`・`2026-10-05 09:30`・`2026/10/5T9:05` を読む。日付だけは 0 時。読めなければ None。"""
    found = _DATETIME.fullmatch(_plain(text))
    if found is None:
        return None
    day = parse_date(found.group(1))
    if day is None:
        return None
    if found.group(2) is None:
        return datetime.combine(day, time(0))
    hour, minute = int(found.group(2)), int(found.group(3))
    return datetime.combine(day, time(hour, minute)) if hour < 24 and minute < 60 else None


def cell_ok(field_: CsvField, text: str) -> bool:
    """プレビューで読めない値を示すための検査。空は読める。"""
    if not text.strip():
        return True
    if field_ in (CsvField.START, CsvField.END):
        return parse_date(text) is not None
    if field_ is CsvField.PROGRESS:
        return parse_percent(text) is not None
    if field_ is CsvField.EFFORT:
        return parse_effort(text) is not None
    if field_ is CsvField.STATUS:
        return parse_status(text) is not None
    if field_ in (CsvField.ACTUAL_START, CsvField.ACTUAL_END):
        return parse_datetime(text) is not None
    return True
```

`from datetime import date, datetime, time, timedelta`に`time`を足す。

3. `_Row`に`effort: str = ""`・`status: str = ""`・`actual_start: str = ""`・`actual_end: str = ""`・`category: str = ""`を足す。`blank_fields`は`not (self.owner or self.start or self.end or self.progress or self.effort or self.status or self.actual_start or self.actual_end or self.category)`にする。`_rows`の`_Row(...)`にキーワードで新しい項目を渡す(`cell(CsvField.EFFORT)`など)。

4. `_Builder.__init__(self, name, holidays, today, profile=SMARTSHEET)`に変え、`self.profile = profile`、`self.categories: dict[str, Category] = {}`、`self.invalid_values = 0`を持つ。`parse_csv`は`_Builder(name, holidays, today or clock.today(), profile)`。

5. `add_task`を次のとおりにする(担当・工数・状態・実績・カテゴリ):

```python
    def add_task(self, row: _Row) -> None:
        task = Task(row.name, id=self.fresh())
        if row.progress:
            value = parse_percent(row.progress)
            if value is None:
                self.invalid_progress += 1
            else:
                task.status, task.progress = _status(value), value or None
        for owner in self.owners(row.owner):
            task.assignees.append(Assignee(owner, 1.0))
            self.member(owner)
        self.schedule(task, row)
        self.apply_effort(task, row)
        self.apply_status(task, row)
        self.apply_actuals(task, row)
        self.apply_category(task, row)
        (self.stack[-1].tasks if self.stack else self.project.tasks).append(task)

    def owners(self, text: str) -> list[str]:
        sep = self.profile.owner_separator
        names = text.split(sep) if sep else [text]
        found: list[str] = []
        for name in (tidy_task_name(n) for n in names):
            if name and name not in found:
                found.append(name)
        return found

    def apply_effort(self, task: Task, row: _Row) -> None:
        if not row.effort:
            return
        hours = parse_effort(row.effort)
        if hours is None:
            self.invalid_values += 1
            return
        task.effort_hours = hours
        end = parse_date(row.end) if row.end else None
        if end is not None:  # 期限は守る: 完了予定を手で指定する
            task.planned_end_manual = True
            task.planned_end = datetime.combine(end, self.project.work_start) + timedelta(
                hours=self.project.daily_hours
            )

    def apply_status(self, task: Task, row: _Row) -> None:
        if not row.status:
            return
        status = parse_status(row.status)
        if status is None:
            self.invalid_values += 1
            return
        task.status = status
        if status is Status.DONE:
            task.progress = 100
        elif status is Status.NOT_STARTED:
            task.progress = None

    def apply_actuals(self, task: Task, row: _Row) -> None:
        if not (row.actual_start or row.actual_end):
            return
        start = parse_datetime(row.actual_start) if row.actual_start else None
        end = parse_datetime(row.actual_end) if row.actual_end else None
        bad = (
            (row.actual_start and start is None)
            or (row.actual_end and end is None)
            or (end is not None and start is None)
            or (start is not None and end is not None and end < start)
        )
        if bad:
            self.invalid_values += 1
            return
        project = self.project
        if start is not None and date_only(row.actual_start):
            start = datetime.combine(start.date(), project.work_start)
        if end is not None and date_only(row.actual_end):
            end = datetime.combine(end.date(), project.work_start) + timedelta(hours=project.daily_hours)
            if start is not None and end < start:
                end = start
        if start is None:
            return
        task.actuals = [Actual(start, end)]
        if end is None and task.status in (Status.NOT_STARTED, Status.DONE):
            task.status = Status.RUNNING  # 進行中の区間があるのに未着手・終了は食い違う

    def apply_category(self, task: Task, row: _Row) -> None:
        name = tidy_task_name(row.category)[:MAX_CATEGORY_NAME_LENGTH]
        if not name:
            return
        if name not in self.categories:
            category = Category(name, id=self.fresh())
            self.categories[name] = category
            self.project.categories.append(category)
        task.category_id = self.categories[name].id
```

(`tidy_task_name`は 50 文字までに整える。カテゴリは 30 文字に切る。)

6. `CsvImport`に`invalid_values: int = 0`を末尾に足し、`parse_csv`の戻りで`builder.invalid_values`を渡す。`summary`の`notes`に`f"読めない値 {result.invalid_values} 件" if result.invalid_values else ""`を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_import.py -q`
Expected: PASS。`parse_project`の検証で落ちるテスト(`planned_end_manual`・`DONE`と進捗・進行中の実績と状態)があれば、検証の文言を読んで、設定の組み合わせを直す(モデルの検証が正)。

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test && uvx ruff check src test
git add src/projectapp/csv_import.py test/test_csv_import.py
git commit -m "feat: CSV の取り込みで、工数・状態・実績・カテゴリ・複数の担当を読む"
```

---

### Task 4: 取り込みのダイアログと画面への組み込み

**Files:**
- Create: `src/projectapp/csv_dialog.py`(取り込みのダイアログ。書き出しは Task 6 で足す)
- Modify: `src/projectapp/views.py`(`import_csv`、`MainView.__init__`にプロファイルの保持)
- Test: `test/test_csv_dialog.py`(新)、`test/test_views.py`(既存の CSV 取り込みのテストを、ダイアログの`取り込む`を押す形に直す)

**Interfaces:**
- Consumes: Task 1〜3(`sniff_table`・`TableSniff`・`parse_csv`・`cell_ok`・`best_profile`・`guess_columns`・`resolve_columns`・`validate_profile`・`SMARTSHEET`・config の読み書き)
- Produces(`csv_dialog.py`):
  - `@dataclass(frozen=True) ImportChoice(profile: CsvProfile, delimiter: str, header_row: int, encoding: str)`
  - `open_csv_import_dialog(data: bytes, profiles: list[CsvProfile], last: str | None, on_import: Callable[[ImportChoice, str], None], on_save: Callable[[CsvProfile], str | None]) -> None`(`on_import(choice, text)`の`text`は選んだ文字コードで読んだテキスト。`on_save`は保存の失敗の文言か None を返す)
  - マーカー: `csv-import-dialog`・`csv-profile`・`csv-delimiter`・`csv-encoding`・`csv-header-row`・`csv-owner-sep`・`csv-map-<field>`(例`csv-map-title`)・`csv-preview`・`csv-import-confirm`・`csv-save-profile`・`csv-save-name`・`csv-save-ok`・`csv-cancel`

**ダイアログの振る舞い**:
- 開いたとき: `sniff_table(data)`で判定。プロファイルのコンボは`推測`(既定)・`Smartsheet`・保存済み。初期選択は、`best_profile(header, [SMARTSHEET, *profiles])`があればそれ、なければ`last`が保存済みにあればそれ、なければ`推測`。`推測`の中身は`CsvProfile("推測", guess_columns(header), delimiter, encoding, "ymd-dash", ";")`(その場限り。保存できない名前`推測`は`validate_profile`で通るが、保存時に名前を入力させる)。
- 区切り・文字コード・ヘッダー行を変えたら`sniff_table(data, encoding, delimiter, header_row)`で見出し・プレビューを作り直し、列のコンボの選択肢も作り直す(`resolve_columns`で現在の対応を引き継ぐ)。
- 項目ごとのコンボ: 選択肢は`割り当てなし`と、見出しの文字(位置の番号を前に付ける: `1: 件名`)。同じ列を 2 項目に選んだら、後から選んだ側を優先し、先の項目を`割り当てなし`に戻す。`title`が`割り当てなし`のあいだは`csv-import-confirm`を無効にし、注意書きを出す。
- プレビュー: 先頭 5 行を、割り当てた項目だけの表で出す。`cell_ok`が偽のセルは赤(`text-negative`)。
- `プロファイルとして保存…`: 名前の入力(`csv-save-name`)と`保存`(`csv-save-ok`)の小さなダイアログ。同名は上書き(組み込みの名前は`validate_profile`の文言で断る)。保存したらプロファイルのコンボをそのプロファイルに切り替える。
- `取り込む`: 現在の対応から`CsvProfile`を作り(`name`は選択中のプロファイル名、`columns`は割り当てた項目〔見出しは元の見出しの文字〕、`owner_separator`は入力欄の値)、`on_import(ImportChoice(...), text)`を呼んで閉じる。`キャンセル`・ESC は何も呼ばない。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_csv_dialog.py`(`test_git_ops_view.py`などの`User`の流儀に合わせる: `from nicegui.testing import User`、`@ui.page("/")`でダイアログを開く関数を呼ぶ):

```python
from pathlib import Path

from nicegui import ui
from nicegui.testing import User

from projectapp.csv_dialog import ImportChoice, open_csv_import_dialog
from projectapp.csv_profile import SMARTSHEET, CsvColumn, CsvField, CsvProfile

DATA = "件名,担当,開始\n設計,田中,2026-10-05\n実装,鈴木,あした\n".encode("utf-8")


async def open_dialog(user: User, profiles=(), last=None):
    chosen: list[tuple[ImportChoice, str]] = []
    saved: list[CsvProfile] = []

    @ui.page("/")
    def index() -> None:
        ui.button("開く", on_click=lambda: open_csv_import_dialog(
            DATA, list(profiles), last,
            lambda choice, text: chosen.append((choice, text)),
            lambda p: saved.append(p) or None,
        )).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="csv-import-dialog")
    return chosen, saved


async def test_the_guess_fills_the_mapping_and_import_returns_it(user: User) -> None:
    chosen, _ = await open_dialog(user)
    user.find(marker="csv-import-confirm").click()
    choice, text = chosen[0]
    assert {c.field: c.header for c in choice.profile.columns} == {
        CsvField.TITLE: "件名", CsvField.OWNER: "担当", CsvField.START: "開始",
    }
    assert choice.delimiter == "," and text.startswith("件名")


async def test_import_is_disabled_without_a_title_column(user: User) -> None:
    chosen, _ = await open_dialog(user)
    select = user.find(marker="csv-map-title").elements.pop()
    select.set_value(None)
    confirm = user.find(marker="csv-import-confirm").elements.pop()
    assert not confirm.enabled


async def test_choosing_the_same_column_twice_clears_the_earlier_field(user: User) -> None:
    await open_dialog(user)
    owner = user.find(marker="csv-map-owner").elements.pop()
    title = user.find(marker="csv-map-title").elements.pop()
    owner.set_value(title.value)  # 担当にも「件名」の列を選ぶ
    assert title.value is None


async def test_the_preview_marks_unreadable_cells(user: User) -> None:
    await open_dialog(user)
    preview = user.find(marker="csv-preview").elements.pop()
    reds = [e for e in preview.descendants() if "text-negative" in e.classes]
    assert [e.text for e in reds] == ["あした"]


async def test_a_matching_saved_profile_is_preselected(user: User) -> None:
    p = CsvProfile("自作", (CsvColumn(CsvField.TITLE, "件名"), CsvColumn(CsvField.OWNER, "担当")))
    await open_dialog(user, profiles=[p])
    assert user.find(marker="csv-profile").elements.pop().value == "自作"


async def test_smartsheet_files_select_the_builtin_profile(user: User) -> None:
    sheet = "WBS 番号\tタスクのタイトル\tタスクオーナー\t開始日\t期限\t期間\tタスク完了率\n1\tA\t\t\t\t\t\n".encode()
    chosen: list = []

    @ui.page("/")
    def index() -> None:
        ui.button("開く", on_click=lambda: open_csv_import_dialog(
            sheet, [], None, lambda c, t: chosen.append(c), lambda p: None)).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="csv-import-dialog")
    assert user.find(marker="csv-profile").elements.pop().value == SMARTSHEET.name


async def test_cancel_returns_nothing(user: User) -> None:
    chosen, _ = await open_dialog(user)
    user.find(marker="csv-cancel").click()
    assert chosen == []
```

`test/test_views.py`の既存テスト(`test_import_csv_opens_an_unsaved_project`・`..._refuses_a_file_without_the_title_column`・`..._asks_before_dropping_unsaved_edits`・`test_export_tsv_writes_the_file_without_touching_the_project`の取り込み部分、ほか`file-import-csv`を押すもの)は、`user.find(marker="file-import-csv").click()`のあとに`user.find(marker="csv-import-confirm").click()`を足す形に直す。「タイトルの列がない」テストは、ダイアログが出るので、`csv-import-confirm`が無効(押せない)であることを確認する形に変える。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_dialog.py -q`
Expected: FAIL(`csv_dialog`がない)

- [ ] **Step 3: 実装する**

`src/projectapp/csv_dialog.py`に、上の振る舞いのとおり`open_csv_import_dialog`を書く。構成の指針:

- 状態は関数内の変数(`sniff`・`mapping: dict[CsvField, int | None]`・`name`)に持つ。`ui.dialog()`の中に`ui.card()`。
- 列のコンボは`ui.select({None: "割り当てなし", 0: "1: 件名", ...}, value=..., on_change=...)`を、`IMPORT_FIELDS`の順に作り、`mark(f"csv-map-{field.value}")`。見出しの作り直しは`@ui.refreshable`の関数にまとめて、`refresh()`する。
- 重複の解消は、`on_change`で「いま選んだ項目以外で同じ位置を持つ項目を None にする」。
- プレビューは`ui.element("div").mark("csv-preview")`の中に`ui.grid`か`ui.html`ではなく、`ui.label`の表(`ui.row`と`ui.label`)で作り、読めないセルに`.classes("text-negative")`。
- `取り込む`は`ui.button(...).mark("csv-import-confirm")`。無効化は`set_enabled`。
- 閉じるのは`dialog.close()`、ESC・外側クリックは`ui.dialog`の既定。`dialog.mark("csv-import-dialog")`。

`views.py`:
- 先頭で`from projectapp.csv_dialog import ImportChoice, open_csv_import_dialog`、`from projectapp.csv_import import sniff_table`(不要になった`read_table`は、他で使っていなければ import を外す)、`from projectapp.config import load_csv_profile_last, load_csv_profiles, save_csv_profile_last, save_csv_profiles`、`from projectapp.csv_profile import CsvProfile`。
- `import_csv`を置き換える:

```python
    async def import_csv(self) -> None:
        """選んだ CSV・TSV を読み、列の対応のダイアログを開く。確定すると、保存前の新規プロジェクトを作る。"""
        path = await self.exporter.ask_open_path(CSV_OPEN_FILE_TYPES)
        if path is None:
            return
        try:
            data = path.read_bytes()
            sniff_table(data)  # 読めるかだけ先に確かめる
        except (OSError, CsvImportError) as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        with self.client:
            open_csv_import_dialog(
                data,
                load_csv_profiles(self.base_dir),
                load_csv_profile_last(self.base_dir),
                lambda choice, text: self.apply_csv_import(choice, text, path.stem),
                self.save_csv_profile,
            )

    def save_csv_profile(self, profile: CsvProfile) -> str | None:
        """プロファイルを保存する(同名は上書き)。失敗の文言か None。"""
        profiles = [p for p in load_csv_profiles(self.base_dir) if p.name != profile.name]
        if len(profiles) >= MAX_PROFILES:
            return f"プロファイルは {MAX_PROFILES} 件までです"
        try:
            save_csv_profiles([*profiles, profile], self.base_dir)
        except OSError as exc:
            return f"保存できませんでした: {exc}"
        return None

    def apply_csv_import(self, choice: ImportChoice, text: str, stem: str) -> None:
        try:
            result = parse_csv(
                text, stem, self.holidays, profile=choice.profile,
                delimiter=choice.delimiter, header_row=choice.header_row,
            )
        except CsvImportError as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        try:
            save_csv_profile_last(choice.profile.name, self.base_dir)
        except OSError:
            pass  # 覚えられなくても、取り込みは続ける
        self.show_project(result.project, None)
        self.snapshot = asdict(Project(NEW_PROJECT_NAME))
        ui.notify(csv_import_summary(result))
```

(`self.base_dir`が`MainView`にあることを`grep -n "base_dir" src/projectapp/views.py`で確認し、なければ config の読み書きで使っている名前に合わせる。`MAX_PROFILES`は`csv_profile`から import。)

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_dialog.py test/test_views.py -q -k "csv or Csv"` → PASS。続けて`uv run pytest -m smoke -q`。

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test && uvx ruff check src test
git add src/projectapp/csv_dialog.py src/projectapp/views.py test/test_csv_dialog.py test/test_views.py
git commit -m "feat: CSV の取り込みに、列の対応のダイアログを足す"
```

---

### Task 5: 書き出しをプロファイルで書く形に一般化する

**Files:**
- Modify: `src/projectapp/csv_export.py`
- Test: `test/test_csv_export.py`(既存はそのまま通す。追加する)

**Interfaces:**
- Consumes: Task 1 の`CsvProfile`・`CsvField`・`SMARTSHEET`
- Produces:
  - `TableExport`(旧`TsvExport`。`TsvExport = TableExport`の別名を残す。フィールドは従来どおり)
  - `build_table(project, holidays, profile: CsvProfile, references=None) -> TableExport`
  - `build_tsv(project, holidays, references=None)`は`build_table(..., SMARTSHEET, ...)`を返す(出力は従来と一致)
  - `format_date(day: date, style: str = "ja") -> str`(`ja`は従来の`26年 10月 5日`、`ymd-dash`は`2026-10-05`、`ymd-slash`は`2026/10/05`)
  - `format_datetime(moment: datetime, style: str) -> str`(日付の書式 + ` HH:MM`)
  - `encode_table(text: str, encoding: str) -> bytes`(`cp932`にできない文字があれば`ValueError("Shift_JIS にできない文字があります: …")`、最初の 5 文字まで列挙)
  - `write_table(path: Path, data: bytes, delimiter: str) -> Path`(拡張子がなければ、タブは`.tsv`、それ以外は`.csv`を付ける。一時ファイル経由)
  - `default_filename(delimiter: str) -> str`(タブ`out.tsv`、それ以外`out.csv`)
  - `write_tsv(path, text)`は従来のまま(`write_table(path, text.encode("utf-8"), "\t")`でもよい。出力は同じ)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_csv_export.py`に追加。既存のテストが使っているプロジェクトの作り方に合わせる)

```python
from projectapp.csv_export import (
    build_table, default_filename, encode_table, format_date, format_datetime, write_table,
)
from projectapp.csv_profile import CsvColumn, CsvField, CsvProfile
from projectapp.models import Actual, Assignee, Category, Project, Section, Status, Task


def prof(*pairs: tuple[CsvField, str], **kw: object) -> CsvProfile:
    return CsvProfile("自作", tuple(CsvColumn(f, h) for f, h in pairs), **kw)  # type: ignore[arg-type]


def test_build_tsv_equals_build_table_with_smartsheet() -> None:
    from projectapp.csv_profile import SMARTSHEET

    p = Project("x")
    p.tasks.append(Task("1.1#設計", assignees=[Assignee("田中", 1.0)], progress=50))
    assert build_tsv(p, {}).text == build_table(p, {}, SMARTSHEET).text


def test_date_styles() -> None:
    d = date(2026, 10, 5)
    assert (format_date(d, "ja"), format_date(d, "ymd-dash"), format_date(d, "ymd-slash")) == (
        "26年 10月 5日", "2026-10-05", "2026/10/05",
    )
    assert format_datetime(datetime(2026, 10, 5, 9, 5), "ymd-dash") == "2026-10-05 09:05"


def test_columns_follow_the_profile_order_headers_and_delimiter() -> None:
    p = Project("x")
    p.tasks.append(Task("設計", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)], effort_hours=8, status=Status.RUNNING))
    profile = prof((CsvField.STATUS, "状態"), (CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), (CsvField.EFFORT, "工数"), delimiter=";", owner_separator="/")
    lines = build_table(p, {}, profile).text.splitlines()
    assert lines == ["状態;件名;担当;工数", "実行中;設計;田中/鈴木;8"]


def test_an_empty_separator_writes_only_the_first_owner_and_counts_it() -> None:
    p = Project("x")
    p.tasks.append(Task("設計", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)]))
    result = build_table(p, {}, prof((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), owner_separator=""))
    assert result.multiple_owners == 1 and result.text.splitlines()[1] == "設計,田中"


def test_values_with_the_delimiter_or_quotes_are_quoted() -> None:
    p = Project("x")
    p.tasks.append(Task('A,"B"'))
    assert build_table(p, {}, prof((CsvField.TITLE, "件名"))).text.splitlines()[1] == '"A,""B"""'


def test_actuals_category_and_effort_are_written() -> None:
    p = Project("x")
    cat = Category("開発")
    p.categories.append(cat)
    task = Task("A", effort_hours=2.5, category_id=cat.id, actuals=[Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 6, 17, 30))])
    p.tasks.append(task)
    profile = prof((CsvField.TITLE, "件名"), (CsvField.ACTUAL_START, "開始実績"), (CsvField.ACTUAL_END, "終了実績"), (CsvField.CATEGORY, "区分"), (CsvField.EFFORT, "工数"))
    assert build_table(p, {}, profile).text.splitlines()[1] == "A,2026-10-05 09:00,2026-10-06 17:30,開発,2.5"


def test_sections_write_only_the_title_and_wbs() -> None:
    p = Project("x")
    p.sections.append(Section("1#計画", tasks=[Task("1.1#設計")]))
    profile = prof((CsvField.WBS, "WBS"), (CsvField.TITLE, "件名"))
    assert build_table(p, {}, profile).text.splitlines()[1:] == ["1,計画", "1.1,設計"]


def test_encode_table_variants() -> None:
    assert encode_table("あ", "utf-8") == "あ".encode("utf-8")
    assert encode_table("あ", "utf-8-sig") == b"\xef\xbb\xbf" + "あ".encode("utf-8")
    assert encode_table("あ", "cp932") == "あ".encode("cp932")


def test_encode_table_refuses_characters_shift_jis_cannot_hold() -> None:
    with pytest.raises(ValueError, match="Shift_JIS にできない文字"):
        encode_table("🙂とA", "cp932")


def test_write_table_adds_an_extension_by_delimiter(tmp_path) -> None:
    assert write_table(tmp_path / "a", b"x", "\t").name == "a.tsv"
    assert write_table(tmp_path / "b", b"x", ",").name == "b.csv"
    assert default_filename("\t") == "out.tsv" and default_filename(";") == "out.csv"


def test_a_roundtrip_through_a_custom_profile_keeps_the_content() -> None:
    from projectapp.csv_import import parse_csv

    p = Project("x")
    p.tasks.append(Task("設計", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)], effort_hours=3, status=Status.RUNNING))
    profile = prof((CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), (CsvField.EFFORT, "工数"), (CsvField.STATUS, "状態"), delimiter=",", owner_separator=";")
    text = build_table(p, {}, profile).text
    back = parse_csv(text, "y", {}, profile=profile, delimiter=",").project.all_tasks()[0]
    assert (back.name, back.assignee_names, back.effort_hours, back.status) == ("設計", ["田中", "鈴木"], 3.0, Status.RUNNING)
```

(`pytest`・`date`・`datetime`・`build_tsv`は同ファイルの既存の import を使う。足りなければ足す。)

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_export.py -q`
Expected: 追加分が FAIL

- [ ] **Step 3: 実装する**

`csv_export.py`を次の方針で書き換える。

- `HEADER`・`BLANK_ROWS`は`SMARTSHEET`に統合する(`HEADER`・`BLANK_ROWS`を参照する既存のテストがあれば、`grep -n "HEADER\|BLANK_ROWS" test/test_csv_export.py`で確認し、定数を残して`SMARTSHEET`から作る: `HEADER = tuple(c.header for c in SMARTSHEET.columns)`、`BLANK_ROWS = SMARTSHEET.blank_rows`)。
- `format_date(day, style="ja")`・`format_datetime`を足す。
- `build_table`は、`build_tsv`の本体を、「行を`dict[CsvField, str]`で作り、`[values.get(c.field, "") for c in profile.columns]`で書く」形にする。区切りは`profile.delimiter`、`csv.writer(out, delimiter=profile.delimiter, lineterminator="\n")`。見出しは`[c.header for c in profile.columns]`。見出しの次に`profile.blank_rows`行の空行(`[""] * len(columns)`)。
- 行の値(`task_row`):
  - `WBS`・`TITLE`: `split_name(task.name)`
  - `OWNER`: `separator`が空なら筆頭の名前(複数なら`counts["multiple"] += 1`)、空でなければ`separator.join(names)`(`counts["multiple"]`は増やさない)
  - `START`・`END`: `format_date(first/last, profile.date_format)`(日付がなければ空)
  - `DURATION`: 従来と同じ(`(last - first).days` か 0)
  - `PROGRESS`: `f"{progress}%"`
  - `EFFORT`: `f"{task.total_effort:g}"`(0 のときは空)
  - `STATUS`: `task.status.value`
  - `ACTUAL_START`: `task.actuals[0].start`を`format_datetime`(なければ空)
  - `ACTUAL_END`: `task.actuals[-1].end`があれば`format_datetime`
  - `CATEGORY`: `{c.id: c.name for c in project.categories}`で引く(なければ空)
- 参照行(`reference_row`): `TITLE`に`REFERENCE_PREFIX + task.name`、`START`・`END`・`DURATION`・`PROGRESS`だけ値を入れる(従来と同じ)。セクション行: `WBS`・`TITLE`だけ。
- `encode_table`:

```python
def encode_table(text: str, encoding: str) -> bytes:
    """指定の文字コードにする。Shift_JIS にできない文字があれば、黙って置き換えず `ValueError`。"""
    if encoding == "utf-8":
        return text.encode("utf-8")
    if encoding == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    try:
        return text.encode("cp932")
    except UnicodeEncodeError:
        bad: list[str] = []
        for ch in text:
            try:
                ch.encode("cp932")
            except UnicodeEncodeError:
                if ch not in bad:
                    bad.append(ch)
        raise ValueError(f"Shift_JIS にできない文字があります: {''.join(bad[:5])}") from None
```

- `write_table`は`write_text`と同じ手順(`tempfile.mkstemp(dir=path.parent, ...)`、`os.fdopen(fd, "wb")`、`fsync`、`os.replace`、失敗で一時ファイルを消す)でバイト列を書く。拡張子がなければ`.tsv`(タブ)か`.csv`を付ける。`import os, tempfile`を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_export.py test/test_csv_import.py -q`
Expected: PASS(既存の Smartsheet の書き出しテストも変更なしで通る)

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test && uvx ruff check src test
git add src/projectapp/csv_export.py test/test_csv_export.py
git commit -m "feat: CSV の書き出しを、プロファイルの列・区切り・文字コードで書く形に一般化する"
```

---

### Task 6: 書き出しのダイアログと画面への組み込み

**Files:**
- Modify: `src/projectapp/csv_dialog.py`、`src/projectapp/views.py`
- Test: `test/test_csv_dialog.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1・5(`CsvProfile`・`EXPORT_FIELDS`・`FIELD_LABELS`・`validate_profile`・`build_table`・`encode_table`・`write_table`・`default_filename`)
- Produces(`csv_dialog.py`):
  - `open_csv_export_dialog(profiles: list[CsvProfile], last: str | None, on_export: Callable[[CsvProfile], None], on_save: Callable[[CsvProfile], str | None]) -> None`
  - マーカー: `csv-export-dialog`・`csv-ex-profile`・`csv-ex-delimiter`・`csv-ex-encoding`・`csv-ex-date`・`csv-ex-owner-sep`・`csv-ex-use-<field>`(含める。チェックボックス)・`csv-ex-header-<field>`(見出し名の入力)・`csv-ex-up-<field>`・`csv-ex-down-<field>`(並べ替え)・`csv-ex-save`・`csv-ex-save-name`・`csv-ex-save-ok`・`csv-export-confirm`・`csv-ex-cancel`

**ダイアログの振る舞い**:
- プロファイルのコンボは`Smartsheet`・保存済み。初期値は`last`が候補にあればそれ、なければ`Smartsheet`。選び直すと、列・区切り・文字コード・日付・担当の区切りがそのプロファイルの値に入れ替わる。
- 列の表は`EXPORT_FIELDS`の全項目を並べる。プロファイルに含まれる項目は、その順で先に、含まれない項目は後ろ。各行: 含める(チェック)・項目名(`FIELD_LABELS`)・見出し名(入力。既定は`FIELD_LABELS`の名前〔Smartsheet の列はその見出し〕)・上へ・下へ。
- `書き出す`は、含める項目が 1 つ以上で`title`を含み、見出しが 1〜40 文字で、`validate_profile`が通るときだけ有効(通らない理由は注意書きに出す)。押すと、現在の状態から作った`CsvProfile`(名前はコンボの名前、組み込みを編集した場合も`Smartsheet`のまま渡してよいが、`blank_rows`は元が`Smartsheet`で列・区切りが変わっていなければ 2、そうでなければ 0)で`on_export`を呼んで閉じる。
- `プロファイルとして保存…`は取り込みと同じ小さなダイアログ。

`views.py`の`export_tsv`を置き換える(メソッド名・マーカー`export-tsv`は変えない。メニューの文言だけ`CSV・TSV として書き出す…`にする。`test_views.py`の`("TSV として書き出す", "export-tsv")`の期待値も合わせる):

```python
    async def export_tsv(self) -> None:
        """書き出しのダイアログを開く。確定すると、通常タスクとセクションを CSV・TSV に書く。プロジェクトは変えない。"""
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not (self.project.all_tasks() or self.project.sections):
            ui.notify("書き出せるタスクがありません", type="warning")
            return
        with self.client:
            open_csv_export_dialog(
                load_csv_profiles(self.base_dir),
                load_csv_profile_last(self.base_dir),
                lambda profile: self.later(lambda: self.run_csv_export(profile)),
                self.save_csv_profile,
            )

    async def run_csv_export(self, profile: CsvProfile) -> None:
        values = {
            tid: ref.value
            for tid, ref in build_references(self.project, self.reference_resolver, clock.now()).items()
            if ref.value is not None
        }
        result = build_table(self.project, self.holidays, profile, values)
        if result.task_count == 0 and result.section_count == 0 and result.references == 0:
            ui.notify("書き出せるタスクがありません", type="warning")
            return
        try:
            data = encode_table(result.text, profile.encoding)
        except ValueError as exc:
            ui.notify(f"書き出せませんでした: {exc}", type="negative")
            return
        types = TSV_FILE_TYPES if profile.delimiter == "\t" else CSV_SAVE_FILE_TYPES
        path = await self.exporter.ask_path(default_filename(profile.delimiter), types)
        if path is None:
            return
        try:
            write_table(path, data, profile.delimiter)
        except OSError as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        try:
            save_csv_profile_last(profile.name, self.base_dir)
        except OSError:
            pass  # 覚えられなくても、書き出しは済んでいる
        notes = [
            f"{result.skipped} 件(まとめ・節目)は書き出していません"
            if result.skipped
            else "",
            f"担当者が複数の {result.multiple_owners} 件は筆頭だけを書きました"
            if result.multiple_owners
            else "",
            f"参照先が読めない {result.unresolved} 件は、日付と完了率を空にしました"
            if result.unresolved
            else "",
        ]
        detail = "、".join(note for note in notes if note)
        head = f"書き出しました(タスク {result.task_count} 件、参照 {result.references} 件、セクション {result.section_count} 件)"
        ui.notify(head + (f"。{detail}" if detail else ""))
```

(`CSV_SAVE_FILE_TYPES = ("CSV TSV ファイル (*.csv;*.tsv)",)`を`csv_export.py`に足す。`TSV_FILE_TYPES`・`TSV_DEFAULT_FILENAME`は`test_views.py`の既存テストが参照しているので残す。Smartsheet の既定(タブ)では`out.tsv`・`TSV_FILE_TYPES`になり、既存テストの期待〔`exporter.asked == ["out.tsv"]`・`asked_types == [TSV_FILE_TYPES]`〕は変わらない。)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_csv_dialog.py`に追加:

```python
from projectapp.csv_dialog import open_csv_export_dialog


async def open_export(user: User, profiles=(), last=None):
    exported: list[CsvProfile] = []
    saved: list[CsvProfile] = []

    @ui.page("/")
    def index() -> None:
        ui.button("開く", on_click=lambda: open_csv_export_dialog(
            list(profiles), last, exported.append, lambda p: saved.append(p) or None)).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="csv-export-dialog")
    return exported, saved


async def test_export_dialog_starts_with_smartsheet_and_exports_it(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-export-confirm").click()
    p = exported[0]
    assert p.name == "Smartsheet" and p.delimiter == "\t" and p.blank_rows == 2
    assert [c.header for c in p.columns][:2] == ["WBS 番号", "タスクのタイトル"]


async def test_unchecking_a_column_and_moving_another_changes_the_profile(user: User) -> None:
    exported, _ = await open_export(user)
    user.find(marker="csv-ex-use-duration").elements.pop().set_value(False)
    user.find(marker="csv-ex-down-wbs").click()
    user.find(marker="csv-export-confirm").click()
    p = exported[0]
    fields = [c.field.value for c in p.columns]
    assert "duration" not in fields and fields[:2] == ["title", "wbs"]
    assert p.blank_rows == 0  # 組み込みの形から外れたら、テンプレートの空行は入れない


async def test_export_is_disabled_without_the_title_column(user: User) -> None:
    await open_export(user)
    user.find(marker="csv-ex-use-title").elements.pop().set_value(False)
    assert not user.find(marker="csv-export-confirm").elements.pop().enabled


async def test_choosing_a_saved_profile_loads_its_settings(user: User) -> None:
    p = CsvProfile("自作", (CsvColumn(CsvField.TITLE, "件名"), CsvColumn(CsvField.EFFORT, "工数")), delimiter=";", encoding="cp932", date_format="ymd-slash", owner_separator="/")
    exported, _ = await open_export(user, profiles=[p], last="自作")
    user.find(marker="csv-export-confirm").click()
    q = exported[0]
    assert (q.name, q.delimiter, q.encoding, q.date_format, q.owner_separator) == ("自作", ";", "cp932", "ymd-slash", "/")
    assert [(c.field, c.header) for c in q.columns] == [(CsvField.TITLE, "件名"), (CsvField.EFFORT, "工数")]
```

`test/test_views.py`に追加(`open_for_import`・`write_csv`・`FakeExporter`を既存のテストのとおりに使う。取り込みで`view.project`を作ってから書き出す形):

```python
async def test_export_dialog_writes_a_custom_csv_in_shift_jis(user: User, tmp_path: Path) -> None:
    target = tmp_path / "out" / "plan"
    target.parent.mkdir()
    exporter = FakeExporter(path=target, open_path=write_csv(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-csv").click()
    user.find(marker="csv-import-confirm").click()
    assert await wait_until(lambda: view.project.name == "in")
    user.find(marker="export-tsv").click()
    await user.should_see(marker="csv-export-dialog")
    user.find(marker="csv-ex-delimiter").elements.pop().set_value(";")
    user.find(marker="csv-ex-encoding").elements.pop().set_value("cp932")
    user.find(marker="csv-export-confirm").click()
    assert await wait_until(lambda: (target.parent / "plan.csv").exists())
    assert "タスクのタイトル" in (target.parent / "plan.csv").read_bytes().decode("cp932")
    assert exporter.asked == ["out.csv"]


async def test_export_refuses_characters_shift_jis_cannot_hold(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "x", open_path=write_csv(tmp_path, "タスクのタイトル\n🙂\n"))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-csv").click()
    user.find(marker="csv-import-confirm").click()
    assert await wait_until(lambda: view.project.name == "in")
    user.find(marker="export-tsv").click()
    await user.should_see(marker="csv-export-dialog")
    user.find(marker="csv-ex-encoding").elements.pop().set_value("cp932")
    user.find(marker="csv-export-confirm").click()
    await user.should_see("Shift_JIS にできない文字があります")
    assert exporter.asked == []
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_dialog.py -q`
Expected: 追加分が FAIL

- [ ] **Step 3: 実装する**

`csv_dialog.py`に`open_csv_export_dialog`を足す(取り込みと同じ書き方。列の表は`@ui.refreshable`。状態は`rows: list[dict]`〔`field`・`use`・`header`〕と`settings`〔区切り・文字コード・日付・担当の区切り〕を関数内に持つ)。`views.py`は上のとおり。`csv_export.py`に`CSV_SAVE_FILE_TYPES`を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_dialog.py test/test_views.py test/test_csv_export.py -q -k "csv or Csv or tsv or export"` → PASS。続けて`uv run pytest -m smoke -q`。

- [ ] **Step 5: コミット**

```bash
uvx ruff format src test && uvx ruff check src test
git add src/projectapp/csv_dialog.py src/projectapp/csv_export.py src/projectapp/views.py test/test_csv_dialog.py test/test_views.py
git commit -m "feat: CSV の書き出しに、列・区切り・文字コードを選ぶダイアログを足す"
```

---

### Task 7: 仕様・状態・作業記録、全体の確認、PR

**Files:**
- Modify: `.claude/spec/import-export.md`(「CSV の取り込みと TSV の書き出し」の節)、`docs/requests.md`(要望 101 の状態と決定)、`.claude/MEMORY.md`(作業記録)

- [ ] **Step 1: 仕様を更新する**

`import-export.md`の該当節を、設計書の「取り込み」「書き出し」「データ」の内容で書き換える。要点: プロファイル(`Smartsheet`は組み込み・予約)、`config.json`の`csv_profiles`・`csv_profile_last`、取り込みのダイアログ(推測・対応・プレビュー・保存)、項目ごとの規則(工数・状態・実績・カテゴリ・複数の担当・WBS 列なしのセクション)、書き出しのダイアログ(列・区切り・文字コード・日付の書式・担当の区切り)、Shift_JIS にできない文字の扱い、`メモ`は範囲外。メニューの文言`CSV・TSV として書き出す…`。`header-git.md`にメニューの一覧があれば合わせる(`grep -n "TSV として書き出す" .claude/spec/*.md`)。

- [ ] **Step 2: 要望の状態を更新する**

`docs/requests.md`の要望 101 を、状態「実装済み・実機確認待ち(PR #…)」と、決定(汎用・ダイアログ・プロファイル保存・メモは範囲外・担当の区切りを設定可)に書き換える。設計書・計画へのリンクを足す。

- [ ] **Step 3: 全体を確認する**

```bash
uv run pytest -m smoke -q
uv run pytest -n auto -q
uvx ruff check && uvx ruff format src test
uvx ty check src
```
Expected: smoke・全テストが PASS。`ty`は既存の`days_text` 1 件のみ。

- [ ] **Step 4: 作業記録とコミット、PR**

`.claude/MEMORY.md`に 2026-11-03 の項目(要望 101: プロファイル・ダイアログ・新しい項目、`csv_profile.py`・`csv_dialog.py`、smoke と全テストの件数)を足す。

```bash
git add .claude docs
git commit -m "docs: 要望 101(CSV のプロファイル)の仕様・状態・作業記録を更新する"
GIT_TERMINAL_PROMPT=0 timeout 90 git push -q -u origin feature/csv-profiles
gh pr create --base develop --title "feat: CSV・TSV の取り込み・書き出しに列の対応(プロファイル)を足す(要望 101)" --body "<概要・テスト・実機確認の手順>"
```

PR の本文には、実機確認の手順(Smartsheet のサンプルを取り込んで従来と同じになること、任意の CSV の推測とプレビュー、プロファイルの保存と再利用、書き出しの列・区切り・文字コード、Shift_JIS にできない文字の通知)を書く。マージは利用者の指示を待つ。
