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
    RATIO = "ratio"
    START = "start"
    END = "end"
    DEADLINE = "deadline"
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
    CsvField.RATIO: "担当の割合",
    CsvField.START: "開始日",
    CsvField.END: "期限",
    CsvField.DEADLINE: "締切",
    CsvField.DURATION: "期間",
    CsvField.PROGRESS: "進捗率",
    CsvField.EFFORT: "工数",
    CsvField.STATUS: "状態",
    CsvField.ACTUAL_START: "開始実績",
    CsvField.ACTUAL_END: "終了実績",
    CsvField.CATEGORY: "カテゴリ",
}
EXPORT_FIELDS = tuple(CsvField)  # ダイアログの表示順
IMPORT_FIELDS = tuple(
    f for f in CsvField if f is not CsvField.DURATION
)  # 期間は読まない

ALIASES: dict[CsvField, tuple[str, ...]] = {  # 見出しの別名(header_key にそろえた形)
    CsvField.WBS: ("wbs番号", "wbs", "wbsno", "no", "番号"),
    CsvField.TITLE: (
        "タスクのタイトル",
        "タスク名",
        "タスク",
        "名前",
        "件名",
        "タイトル",
        "task",
        "taskname",
        "title",
        "name",
        "subject",
    ),
    CsvField.OWNER: (
        "タスクオーナー",
        "タスクのオーナー",
        "担当",
        "担当者",
        "オーナー",
        "assignee",
        "owner",
        "assignedto",
        "resource",
    ),
    CsvField.START: ("開始日", "開始", "着手日", "start", "startdate", "begin"),
    CsvField.END: (
        "期限",
        "終了日",
        "終了",
        "完了日",
        "due",
        "duedate",
        "end",
        "enddate",
        "finish",
    ),
    CsvField.DEADLINE: ("締切", "締切日", "納期", "deadline"),
    CsvField.RATIO: (
        "担当の割合",
        "担当割合",
        "割合",
        "割当率",
        "割り当て率",
        "allocation",
    ),
    CsvField.DURATION: ("期間", "duration", "days"),
    CsvField.PROGRESS: (
        "タスク完了率",
        "完了率",
        "進捗",
        "進捗率",
        "%complete",
        "progress",
        "complete",
    ),
    CsvField.EFFORT: (
        "工数",
        "見積",
        "見積もり",
        "予定工数",
        "effort",
        "hours",
        "estimate",
    ),
    CsvField.STATUS: ("状態", "ステータス", "status", "state"),
    CsvField.ACTUAL_START: ("開始実績", "実績開始", "actualstart"),
    CsvField.ACTUAL_END: ("終了実績", "実績終了", "actualend", "actualfinish"),
    CsvField.CATEGORY: (
        "カテゴリ",
        "カテゴリー",
        "プロジェクトコード",
        "category",
        "projectcode",
    ),
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
    owner_separator: str = (
        ";"  # 複数の担当の区切り。空は 1 人だけ(取り込みは分けず、書き出しは筆頭のみ)
    )
    progress_percent: bool = (
        True  # 進捗率の書き出しに % を付ける(取り込みはどちらも読む)
    )
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
        for name in (header_key(column.header), *ALIASES[column.field]):
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
        title_hit = any(
            c.field is CsvField.TITLE and header_key(c.header) in keys for c in cols
        )
        if (
            title_hit
            and cols
            and hits * 2 >= len(cols)
            and (best is None or hits > best[0])
        ):
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
        "columns": [
            {"field": c.field.value, "header": c.header} for c in profile.columns
        ],
        "delimiter": profile.delimiter,
        "encoding": profile.encoding,
        "date_format": profile.date_format,
        "owner_separator": profile.owner_separator,
        "progress_percent": profile.progress_percent,
    }


def profile_from_config(raw: object) -> CsvProfile | None:
    """config の 1 件を読む。形が違う・検証に通らないときは None。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("columns"), list):
        return None
    try:
        columns = tuple(
            CsvColumn(CsvField(c["field"]), str(c["header"]).strip())
            for c in raw["columns"]
        )
        profile = CsvProfile(
            str(raw["name"]).strip(),
            columns,
            str(raw.get("delimiter", ",")),
            str(raw.get("encoding", "utf-8")),
            str(raw.get("date_format", "ymd-dash")),
            str(raw.get("owner_separator", ";")),
            progress_percent=raw.get("progress_percent", True) is not False,
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
