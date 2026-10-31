"""チーム(要望 85)。名前の検証、所属の検証と正規化、削除の反映、担当への展開。NiceGUI に依存しない。"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from math import isfinite

from projectapp.models import (
    MAX_TEAM_NAME_LENGTH,
    Assignee,
    Member,
    Membership,
    Project,
    Team,
    has_control_char,
    new_id,
)

PERCENT_ERROR = "所属の割合は 1〜100 の整数で入力してください"


def team_name_error(name: str, others: Collection[str] = ()) -> str | None:
    """チーム名の検証。`others` は、すでにある(整えた)名前。問題がなければ None。"""
    clean = name.strip()
    if not clean:
        return "チームの名前を入力してください"
    if has_control_char(clean):
        return "チームの名前に使えない文字が含まれています"
    if len(clean) > MAX_TEAM_NAME_LENGTH:
        return f"チームの名前は{MAX_TEAM_NAME_LENGTH}文字以内で入力してください"
    if clean in others:
        return f"チームの名前が重複しています: {clean}"
    return None


def membership_error(
    teams: Sequence[Membership], team_ids: Collection[str]
) -> str | None:
    """メンバーの所属の検証。空は可。チームが存在し、重複せず、割合が整数 1〜100 で、合計が 100。"""
    if not teams:
        return None
    seen: set[str] = set()
    for membership in teams:
        if membership.team_id not in team_ids:
            return "存在しないチームへの所属があります"
        if membership.team_id in seen:
            return "同じチームには 1 回までしか所属できません"
        seen.add(membership.team_id)
        percent = membership.percent
        if (
            isinstance(percent, bool)
            or not isinstance(percent, int)
            or not 1 <= percent <= 100
        ):
            return PERCENT_ERROR
    total = sum(m.percent for m in teams)
    if total != 100:
        return f"所属の割合の合計を 100% にしてください(今は {total}%)"
    return None


def normalize(teams: Sequence[Membership]) -> list[Membership]:
    """割合の比を保って合計を 100 に揃える。端数は割合が最大の所属(同じなら先頭)に寄せる。合計が 100 以下の所属を渡す。"""
    if not teams:
        return []
    if len(teams) == 1:
        return [Membership(teams[0].team_id, 100)]
    total = sum(m.percent for m in teams)
    shares = [m.percent * 100 // total for m in teams]
    largest = max(range(len(teams)), key=lambda i: (teams[i].percent, -i))
    shares[largest] += 100 - sum(shares)
    return [Membership(m.team_id, share) for m, share in zip(teams, shares)]


def even_split(count: int) -> list[int]:
    """合計 100 の均等割り(端数は先頭から 1 ずつ)。"""
    return [100 // count + (1 if i < 100 % count else 0) for i in range(count)]


def settle_memberships(
    rows: Sequence[tuple[str, float | None]], team_ids: Collection[str]
) -> list[Membership]:
    """チェックを入れた(チームの id, 割合)から所属を作る。1 つだけなら割合に関わらず 100%。問題があれば ValueError。"""
    if len(rows) == 1:
        result = [Membership(rows[0][0], 100)]
    else:
        result = []
        for team_id, percent in rows:
            if percent is None or not isfinite(percent) or percent != int(percent):
                raise ValueError(PERCENT_ERROR)
            result.append(Membership(team_id, int(percent)))
    error = membership_error(result, team_ids)
    if error is not None:
        raise ValueError(error)
    return result


def membership_summary(memberships: Sequence[Membership], teams: Sequence[Team]) -> str:
    """メンバーの表のボタンの文言。所属なしは「チーム」、1 つはチーム名、兼務は「開発 60%・QA 40%」。"""
    names = {t.id: t.name for t in teams}
    rows = [(names[m.team_id], m.percent) for m in memberships if m.team_id in names]
    if not rows:
        return "チーム"
    if len(rows) == 1:
        return rows[0][0]
    return "・".join(f"{name} {percent}%" for name, percent in rows)


def team_member_names(members: Sequence[Member], team_id: str) -> list[str]:
    """チームに所属するメンバーの名前(メンバーの並び順)。"""
    return [m.name for m in members if any(s.team_id == team_id for s in m.teams)]


def teams_with_members(project: Project) -> list[str]:
    """メンバーがいるチームの名前(チームの並び順)。絞り込みの選択肢に出す。"""
    return [t.name for t in project.teams if team_member_names(project.members, t.id)]


def team_scope(project: Project, team: str | None) -> frozenset[str] | None:
    """チーム名 → 所属するメンバー名の集合。None・存在しない・メンバーがいないチームは None(絞り込まない)。"""
    if team is None:
        return None
    for entry in project.teams:
        if entry.name == team:
            names = team_member_names(project.members, entry.id)
            return frozenset(names) if names else None
    return None


def team_weights(project: Project, team: str | None) -> dict[str, float] | None:
    """チーム名 → {メンバー名: そのチームの所属の割合(1.0 = 100%)}(メンバーの並び順)。None・存在しない・メンバーがいないチームは None。"""
    if team is None:
        return None
    for entry in project.teams:
        if entry.name == team:
            weights = {
                m.name: s.percent / 100
                for m in project.members
                for s in m.teams
                if s.team_id == entry.id
            }
            return weights or None
    return None


def drop_teams(project: Project, removed: Collection[str]) -> int:
    """削除したチームへの所属を外し、残りの割合を 100% に揃える。所属が変わったメンバーの数を返す。"""
    changed = 0
    for member in project.members:
        kept = [s for s in member.teams if s.team_id not in removed]
        if len(kept) != len(member.teams):
            member.teams = normalize(kept)
            changed += 1
    return changed


@dataclass
class TeamRow:
    """チームのタブの 1 行。`id` は開いた時点のチームの id(新しい行は None)。"""

    id: str | None
    name: str


def build_teams(rows: Sequence[TeamRow], taken: Collection[str]) -> list[Team]:
    """タブの行を検証してチームの一覧にする。`taken` は、すでにある id(新しい行の id がこれと重ならない)。"""
    teams: list[Team] = []
    names: set[str] = set()
    used = set(taken)
    for row in rows:
        error = team_name_error(row.name, names)
        if error is not None:
            raise ValueError(error)
        team_id = row.id or new_id(used)
        used.add(team_id)
        names.add(row.name.strip())
        teams.append(Team(row.name.strip(), team_id))
    return teams


def replace_teams(project: Project, teams: list[Team]) -> int:
    """チームの一覧を置き換え、消えたチームへの所属を外す。所属が変わったメンバーの数を返す。"""
    removed = {t.id for t in project.teams} - {t.id for t in teams}
    project.teams = teams
    return drop_teams(project, removed)


def removal_impacts(project: Project, teams: Sequence[Team]) -> list[str]:
    """`teams` に置き換えたとき、所属が外れるメンバーがいる削除チームの説明(確認ダイアログに出す)。"""
    kept = {t.id for t in teams}
    lines = []
    for team in project.teams:
        if team.id in kept:
            continue
        count = len(team_member_names(project.members, team.id))
        if count:
            lines.append(f"チーム「{team.name}」: 所属 {count} 人")
    return lines


def add_team_members(
    current: Sequence[Assignee], names: Sequence[str], allocation: float
) -> list[Assignee]:
    """担当者にチームのメンバーを加える。すでにいる人は割り当て率だけ更新する(元のリストは変えない)。"""
    result = [
        Assignee(a.name, allocation if a.name in names else a.allocation)
        for a in current
    ]
    have = {a.name for a in result}
    result += [Assignee(name, allocation) for name in names if name not in have]
    return result
