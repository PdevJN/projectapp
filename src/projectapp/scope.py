"""メンバー・チームの絞り込みの選択肢。ガントチャートとダッシュボードのプルダウンが共有する。NiceGUI に依存しない。"""

from collections.abc import Sequence

ALL = ""  # `全員`・`すべての担当者`の値。メンバー名は空にできない
TEAM_KEY = "\x1fteam:"  # チームの値の接頭辞。制御文字なので、メンバー名とぶつからない


def team_key(name: str) -> str:
    return f"{TEAM_KEY}{name}"


def read_scope(value: str | None) -> tuple[str | None, str | None]:
    """プルダウンの値 → (メンバー名, チーム名)。どちらか一方だけ入る。`全員`・空は (None, None)。"""
    if not value:
        return None, None
    if value.startswith(TEAM_KEY):
        return None, value[len(TEAM_KEY) :] or None
    return value, None


def scope_value(member: str | None, team: str | None) -> str:
    """(メンバー名, チーム名) → プルダウンの値。両方あるときはチーム。"""
    if team:
        return team_key(team)
    return member or ALL


def scope_options(all_label: str, members: Sequence[str], teams: Sequence[str]) -> dict[str, str]:
    """プルダウンの選択肢。`全員`、メンバー、`チーム: 名前` の順。"""
    options = {ALL: all_label}
    options.update({name: name for name in members})
    options.update({team_key(name): f"チーム: {name}" for name in teams})
    return options
