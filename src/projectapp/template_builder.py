"""CSV の書式(`{開始日}/{期限}: {タスク名}`)を、項目と区切りの文字のチップの並びとして扱う純粋関数(要望 119)。

画面は`template_builder_view.py`。ここは NiceGUI を使わない。文字列の書式は`csv_profile.parse_template`で読む。
"""

from projectapp.csv_profile import (
    FIELD_LABELS,
    MAX_TEMPLATE_FIELDS,
    CsvField,
    parse_template,
)

SEPARATORS = (";", ":", ",", "-", "_", "+", "|", "\\", "/", " ")  # 区切りのパレット
SPACE_MARK = "␣"  # 半角空白のチップの表示

Token = str | CsvField


def tokens_of(template: str) -> list[Token] | None:
    """文字列の書式を、チップの並びにする。読めない書式(波括弧の崩れ・知らない項目名)は None。"""
    parsed = parse_template(template)
    return None if parsed is None else list(parsed)


def template_of(tokens: list[Token]) -> str:
    return "".join(
        f"{{{FIELD_LABELS[t]}}}" if isinstance(t, CsvField) else t for t in tokens
    )


def token_label(token: Token) -> str:
    """チップに出す文字。空白だけの区切りは、見えるように記号にする。"""
    if isinstance(token, CsvField):
        return FIELD_LABELS[token]
    return token.replace(" ", SPACE_MARK)


def insert_token(tokens: list[Token], token: Token, index: int | None) -> list[Token]:
    """`index`の位置にチップを入れる(None は末尾)。同じ項目がすでにあれば、そこから移す。"""
    rest = list(tokens)
    at = len(rest) if index is None else max(0, min(index, len(rest)))
    if isinstance(token, CsvField) and token in rest:
        old = rest.index(token)
        rest.pop(old)
        if old < at:
            at -= 1
    elif isinstance(token, CsvField):
        if sum(isinstance(t, CsvField) for t in rest) >= MAX_TEMPLATE_FIELDS:
            return list(tokens)
    rest.insert(at, token)
    return rest


def move_token(tokens: list[Token], source: int, target: int) -> list[Token]:
    """`source`のチップを、取り除いたあとの並びの`target`番目へ移す。"""
    if not 0 <= source < len(tokens):
        return list(tokens)
    rest = list(tokens)
    token = rest.pop(source)
    rest.insert(max(0, min(target, len(rest))), token)
    return rest


def remove_token(tokens: list[Token], index: int) -> list[Token]:
    if not 0 <= index < len(tokens):
        return list(tokens)
    return tokens[:index] + tokens[index + 1 :]
