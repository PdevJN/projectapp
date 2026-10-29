# チーム 段階 1(データ・管理画面・担当への展開) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プロジェクトに「チーム」を登録し、メンバーを複数のチームへ割合つきで所属させ、タスクの担当にチームのメンバーをまとめて入れられるようにする(要望 85 の段階 1)。

**Architecture:** `Team`(id・名前)を `Project.teams` に、所属を `Member.teams: list[Membership]`(チームの id と整数 1〜100 の割合。合計 100)に持つ。検証・正規化・削除の反映・担当への展開は NiceGUI に依存しない `teams.py` にまとめる。保存は `version` 17、3 者マージはチームを id で、所属をリスト全体で 1 項目として比べる。画面は `メンバーとパラメータ`に`チーム`タブを足し、メンバーの表に`チーム`列を足し、タスクの担当欄に`チームから追加`を足す。タスクにチームの記録は残さない(展開方式)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)。型は `uv run ty check src`。

**Spec:** [`docs/superpowers/specs/2026-10-30-teams-design.md`](../specs/2026-10-30-teams-design.md)(段階 1 の節)

## Global Constraints

- チーム名は 30 文字以内(`MAX_TEAM_NAME_LENGTH`)。制御文字・ゼロ幅文字(`Cc`・`Cf`・`Zl`・`Zp`。`models.has_control_char`)は不可。同じ名前は不可。空は不可。
- 所属の割合は整数 1〜100%。チームに入っているメンバーは、割合の合計をちょうど 100% にする。1 つのチームだけなら 100%。チームなし(`teams` が空)も可。
- チームの削除は、所属するメンバーがいるとき確認を出し、その所属を外す。残る割合は比を保って 100% に正規化し、端数は最大の所属(同じなら先頭)に寄せる。
- プロジェクトファイルの `version` は 17。キーのない古いファイルは「チームなし」で読む。`version` 16 以下のファイルにある `teams` は無視する。存在しないチーム `id`・同じチームの重複した所属・合計が 100% でない所属・重複したチーム名や `id` は読込を拒否する。
- 3 者マージはチームを `id` で、メンバーの所属(`teams`)をリスト全体で 1 項目として比べる。
- 設定ファイル(`settings.json`)にはチームを含めない(メンバーの所属も書き出さない)。
- 担当への展開では、チームに入っているメンバーを担当者として加える。すでにいる人は割り当て率だけ更新する。所属するメンバーがいないチームは選べない。
- 週ごとの担当のタスクでは、担当欄を隠すので、`チームから追加`も隠す。
- 元に戻す・やり直しの対象に含める(`MainView.after_edit` を通す)。
- コミット末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- 実装の経緯は仕様書へ、モジュール構成は `docs/development.md` へ書く。

## Review Focus

1. 兼務の所属で、チームを削除したあとの割合が合計 100% に揃うこと(60/30/10 から 10 を削除 → 67/33、1 人だけ残れば 100%、全部消えれば所属なし)。Task 1 の `test_drop_teams_*` と Task 4 の画面テストで確かめる。
2. チームタブで削除を適用する前に、メンバーのタブに未適用の編集(所属を含む)があっても、削除したチームへの所属が未適用の行からも外れ、メンバーのタブの `●` が出ないこと。Task 4 の `test_team_delete_*`。
3. 3 者マージで、片側がチームを削除し、もう片側がそのチームへ所属を足したとき、所属が外れて割合が 100% に揃い、通知が出ること。同名のチームを両側が足したときは名前を変えて両方残すこと。Task 3。
4. 古いファイル(version 16 以下)と、不正な `teams`(未知のチーム id・合計が 100% でない・真偽値や小数の割合)の読込。Task 2。
5. 設定ファイルの書き出し・取り込みが、チームのあるプロジェクトで壊れないこと(メンバーの所属が設定ファイルに出ない)。Task 2。

---

## File Structure

- Create: `src/projectapp/teams.py` — 名前・所属の検証、正規化、削除の反映、担当への展開(純粋関数と `TeamRow`)
- Create: `src/projectapp/teams_dialog.py` — `チーム`タブ(`teams_panel`)とメンバーの所属ダイアログ(`open_member_teams_dialog`)
- Create: `test/test_teams.py` — `teams.py` のテスト
- Modify: `src/projectapp/models.py` — `Team`・`Membership`・`Member.teams`・`Project.teams`・`used_ids`・`FORMAT_VERSION`
- Modify: `src/projectapp/storage.py` — 保存・読込・検証
- Modify: `src/projectapp/settings_io.py` — 書き出しからチームを除く
- Modify: `src/projectapp/merge.py` — チームと所属のマージ
- Modify: `src/projectapp/forms.py` — `MemberRow.teams`・`build_members`・メンバーの表の列・ダイアログのタブ
- Modify: `src/projectapp/views.py` — `apply_teams`・ダイアログへの配線・タスクダイアログへ `teams` を渡す
- Modify: `src/projectapp/task_dialog.py` — `チームから追加`
- Modify: `test/test_storage.py`・`test/test_merge.py`・`test/test_views.py`・`test/test_task_dialog.py`・`test/test_settings_io.py`、`FORMAT_VERSION == 16` を書いたテスト
- Modify: `CLAUDE.md`・`docs/development.md`・`docs/request-history.md`・`docs/hidden-requests.md`(git 管理外)・`file-format.md` は触らない(todoapp 用)

---

### Task 1: モデルと `teams.py`

**Files:**
- Modify: `src/projectapp/models.py`
- Create: `src/projectapp/teams.py`
- Test: `test/test_teams.py`

**Interfaces:**
- Produces(models): `MAX_TEAM_NAME_LENGTH = 30`、`Team(name: str, id: str)`(`id` は `compare=False`)、`Membership(team_id: str, percent: int = 100)`、`Member.teams: list[Membership]`(末尾のフィールド)、`Project.teams: list[Team]`、`Project.used_ids()` にチームの id を含める、`FORMAT_VERSION = 17`。
- Produces(`teams.py`):
  - `PERCENT_ERROR: str`
  - `team_name_error(name: str, others: Collection[str] = ()) -> str | None`
  - `membership_error(teams: Sequence[Membership], team_ids: Collection[str]) -> str | None`
  - `normalize(teams: Sequence[Membership]) -> list[Membership]`
  - `even_split(count: int) -> list[int]`
  - `settle_memberships(rows: Sequence[tuple[str, float | None]], team_ids: Collection[str]) -> list[Membership]`(`ValueError`)
  - `membership_summary(memberships: Sequence[Membership], teams: Sequence[Team]) -> str`
  - `team_member_names(members: Sequence[Member], team_id: str) -> list[str]`
  - `drop_teams(project: Project, removed: Collection[str]) -> int`
  - `TeamRow(id: str | None, name: str)`、`build_teams(rows: Sequence[TeamRow], taken: Collection[str]) -> list[Team]`(`ValueError`)
  - `replace_teams(project: Project, teams: list[Team]) -> int`
  - `removal_impacts(project: Project, teams: Sequence[Team]) -> list[str]`
  - `add_team_members(current: Sequence[Assignee], names: Sequence[str], allocation: float) -> list[Assignee]`

- [ ] **Step 1: モデルのテストと `teams.py` のテストを書く**

`test/test_teams.py` を作る。

```python
import pytest

from projectapp.models import Assignee, Member, Membership, Project, Team
from projectapp.teams import (
    TeamRow,
    add_team_members,
    build_teams,
    drop_teams,
    even_split,
    membership_error,
    membership_summary,
    normalize,
    removal_impacts,
    replace_teams,
    settle_memberships,
    team_member_names,
    team_name_error,
)


def ms(*pairs: tuple[str, int]) -> list[Membership]:
    return [Membership(team_id, percent) for team_id, percent in pairs]


def test_team_ids_are_part_of_used_ids_and_not_of_equality() -> None:
    project = Project("p", teams=[Team("開発", id="t1")])
    assert "t1" in project.used_ids()
    assert Team("開発", id="a") == Team("開発", id="b")


def test_a_member_has_no_teams_by_default() -> None:
    assert Member("田中").teams == []


@pytest.mark.parametrize(
    ("name", "others", "expected"),
    [
        ("開発", (), None),
        ("  開発  ", (), None),
        ("", (), "チームの名前を入力してください"),
        ("   ", (), "チームの名前を入力してください"),
        ("開\n発", (), "チームの名前に使えない文字が含まれています"),
        ("開​発", (), "チームの名前に使えない文字が含まれています"),
        ("あ" * 31, (), "チームの名前は30文字以内で入力してください"),
        ("開発", ("開発",), "チームの名前が重複しています: 開発"),
    ],
)
def test_team_name_error(name: str, others: tuple[str, ...], expected: str | None) -> None:
    assert team_name_error(name, others) == expected


def test_a_30_character_team_name_is_accepted() -> None:
    assert team_name_error("あ" * 30) is None


def test_membership_error_accepts_none_one_and_several_summing_to_100() -> None:
    ids = {"a", "b", "c"}
    assert membership_error([], ids) is None
    assert membership_error(ms(("a", 100)), ids) is None
    assert membership_error(ms(("a", 60), ("b", 40)), ids) is None


@pytest.mark.parametrize(
    "teams",
    [
        ms(("zzz", 100)),  # 存在しないチーム
        ms(("a", 50), ("a", 50)),  # 同じチームの重複
        ms(("a", 60), ("b", 30)),  # 合計が 100 でない
        ms(("a", 60), ("b", 50)),
        ms(("a", 0), ("b", 100)),  # 0%
        ms(("a", 101)),
    ],
)
def test_membership_error_rejects_bad_memberships(teams: list[Membership]) -> None:
    assert membership_error(teams, {"a", "b"}) is not None


def test_membership_error_rejects_non_integer_percents() -> None:
    assert membership_error([Membership("a", 60.5)], {"a"}) is not None  # type: ignore[arg-type]
    assert membership_error([Membership("a", True)], {"a"}) is not None  # type: ignore[arg-type]
    assert membership_error([Membership("a", None)], {"a"}) is not None  # type: ignore[arg-type]


def test_normalize_keeps_the_ratio_and_gives_the_remainder_to_the_largest() -> None:
    assert normalize(ms(("a", 60), ("b", 30))) == ms(("a", 67), ("b", 33))
    assert normalize(ms(("a", 50), ("b", 50))) == ms(("a", 50), ("b", 50))
    assert normalize(ms(("a", 30))) == ms(("a", 100))
    assert normalize([]) == []


def test_normalize_gives_a_tie_remainder_to_the_first() -> None:
    assert normalize(ms(("a", 1), ("b", 1), ("c", 1))) == ms(("a", 34), ("b", 33), ("c", 33))


def test_even_split_sums_to_100() -> None:
    assert even_split(1) == [100]
    assert even_split(2) == [50, 50]
    assert even_split(3) == [34, 33, 33]
    assert sum(even_split(7)) == 100


def test_settle_memberships_gives_a_single_team_100_percent_whatever_the_input() -> None:
    assert settle_memberships([("a", None)], {"a"}) == ms(("a", 100))


def test_settle_memberships_reads_whole_percents() -> None:
    assert settle_memberships([("a", 60.0), ("b", 40.0)], {"a", "b"}) == ms(("a", 60), ("b", 40))


def test_settle_memberships_of_nothing_is_nothing() -> None:
    assert settle_memberships([], {"a"}) == []


@pytest.mark.parametrize("rows", [[("a", 60.5), ("b", 39.5)], [("a", None), ("b", 100.0)], [("a", float("nan")), ("b", 50.0)]])
def test_settle_memberships_rejects_fractions_and_blanks(rows: list[tuple[str, float | None]]) -> None:
    with pytest.raises(ValueError, match="1〜100 の整数"):
        settle_memberships(rows, {"a", "b"})


def test_settle_memberships_rejects_a_total_other_than_100() -> None:
    with pytest.raises(ValueError, match="合計を 100%"):
        settle_memberships([("a", 60.0), ("b", 30.0)], {"a", "b"})


def test_membership_summary() -> None:
    teams = [Team("開発", id="a"), Team("QA", id="b")]
    assert membership_summary([], teams) == "チーム"
    assert membership_summary(ms(("a", 100)), teams) == "開発"
    assert membership_summary(ms(("a", 60), ("b", 40)), teams) == "開発 60%・QA 40%"


def test_team_member_names_keeps_member_order() -> None:
    members = [Member("甲", teams=ms(("a", 100))), Member("乙"), Member("丙", teams=ms(("a", 50), ("b", 50)))]
    assert team_member_names(members, "a") == ["甲", "丙"]
    assert team_member_names(members, "b") == ["丙"]
    assert team_member_names(members, "zzz") == []


def test_drop_teams_renormalizes_what_is_left() -> None:
    project = Project(
        "p",
        members=[
            Member("甲", teams=ms(("a", 60), ("b", 30), ("c", 10))),
            Member("乙", teams=ms(("c", 100))),
            Member("丙", teams=ms(("a", 100))),
        ],
    )
    assert drop_teams(project, {"c"}) == 2
    assert project.members[0].teams == ms(("a", 67), ("b", 33))
    assert project.members[1].teams == []
    assert project.members[2].teams == ms(("a", 100))


def test_drop_teams_with_one_left_gives_100() -> None:
    project = Project("p", members=[Member("甲", teams=ms(("a", 60), ("b", 40)))])
    drop_teams(project, {"b"})
    assert project.members[0].teams == ms(("a", 100))


def test_build_teams_keeps_existing_ids_and_gives_new_ones() -> None:
    rows = [TeamRow("t1", " 開発 "), TeamRow(None, "QA")]
    teams = build_teams(rows, {"t1", "x"})
    assert [t.name for t in teams] == ["開発", "QA"]
    assert teams[0].id == "t1"
    assert teams[1].id not in {"t1", "x"}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([TeamRow(None, "")], "名前を入力"),
        ([TeamRow(None, "A"), TeamRow(None, "A")], "重複"),
        ([TeamRow(None, "あ" * 31)], "30文字以内"),
    ],
)
def test_build_teams_rejects_bad_rows(rows: list[TeamRow], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_teams(rows, set())


def test_replace_teams_drops_memberships_of_removed_teams() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="a"), Team("QA", id="b")],
        members=[Member("甲", teams=ms(("a", 60), ("b", 40)))],
    )
    changed = replace_teams(project, [Team("開発", id="a")])
    assert changed == 1
    assert [t.id for t in project.teams] == ["a"]
    assert project.members[0].teams == ms(("a", 100))


def test_removal_impacts_lists_only_removed_teams_that_have_members() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="a"), Team("QA", id="b"), Team("空", id="c")],
        members=[Member("甲", teams=ms(("a", 100))), Member("乙", teams=ms(("a", 50), ("b", 50)))],
    )
    assert removal_impacts(project, [Team("QA", id="b"), Team("空", id="c")]) == ["チーム「開発」: 所属 2 人"]
    assert removal_impacts(project, project.teams) == []


def test_add_team_members_adds_and_updates() -> None:
    current = [Assignee("甲", 0.5), Assignee("丙", 1.0)]
    result = add_team_members(current, ["甲", "乙"], 0.8)
    assert result == [Assignee("甲", 0.8), Assignee("丙", 1.0), Assignee("乙", 0.8)]
    assert current == [Assignee("甲", 0.5), Assignee("丙", 1.0)]  # 元は変えない
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest test/test_teams.py -q`
Expected: FAIL(`ImportError: cannot import name 'Team'` など)。

- [ ] **Step 3: `models.py` にモデルを足す**

`src/projectapp/models.py`:

1. `FORMAT_VERSION = 16` を `17` にし、末尾のコメントの括弧に `17: チーム〔teams・members[].teams〕` を足す(`16: メンバーの丸め対象外〔members[].ratio_unclamped〕` のあと)。
2. `MAX_EVENT_TEXT_LENGTH = 30 ...` の次の行に足す。

```python
MAX_TEAM_NAME_LENGTH = 30  # チームの名前の最大文字数
```

3. `Member` の前に `Membership` を、`Category` の前に `Team` を足し、`Member` の末尾にフィールドを足す。`Member` は `Membership` を参照するので、`Membership` を `Member` より前に置く。

```python
@dataclass
class Membership:
    """メンバーのチームへの所属。`percent` は、そのメンバーの時間のうちこのチームに数える割合(整数 1〜100)。"""

    team_id: str
    percent: int = 100


@dataclass
class Team:
    """プロジェクト共通のチーム。所属は `Member.teams` が持つ(タスクにチームの記録は残さない)。"""

    name: str
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する
```

`Member` の最後のフィールド `ratio_unclamped` の次の行に足す。

```python
    teams: list[Membership] = field(default_factory=list)  # 所属するチーム。空はチームなし。あれば割合の合計が 100
```

4. `Project` の `events` の次の行に足す。

```python
    teams: list[Team] = field(default_factory=list)  # チーム(プロジェクト共通)
```

5. `used_ids` の docstring を「タスク・メンバー・セクション・カテゴリ・イベント・チームの id」にし、`| {e.id for e in self.events}` の次に `| {t.id for t in self.teams}` を足す。

- [ ] **Step 4: `teams.py` を書く**

`src/projectapp/teams.py`:

```python
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


def membership_error(teams: Sequence[Membership], team_ids: Collection[str]) -> str | None:
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
        if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
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


def settle_memberships(rows: Sequence[tuple[str, float | None]], team_ids: Collection[str]) -> list[Membership]:
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


def add_team_members(current: Sequence[Assignee], names: Sequence[str], allocation: float) -> list[Assignee]:
    """担当者にチームのメンバーを加える。すでにいる人は割り当て率だけ更新する(元のリストは変えない)。"""
    result = [Assignee(a.name, allocation if a.name in names else a.allocation) for a in current]
    have = {a.name for a in result}
    result += [Assignee(name, allocation) for name in names if name not in have]
    return result
```

- [ ] **Step 5: テストが通ることを確かめる**

Run: `uv run pytest test/test_teams.py -q`
Expected: すべて PASS。

- [ ] **Step 6: 既存の `FORMAT_VERSION == 16` の断定を 17 に直す**

`test/test_reference_storage.py:39`・`test/test_summary.py:72`・`test/test_storage.py` の `FORMAT_VERSION == 16`(1311・1379・1905・1947 行)と `raw["version"] == 16`(2112・2176 行)を調べる。`FORMAT_VERSION == 16` は `== 17` に、`raw["version"] == 16` は、保存した直後の値を見るものなら `17` に直す(古い形式のファイルを読む試験で `16` を書いているものは直さない)。

Run: `uv run pytest test/test_storage.py test/test_reference_storage.py test/test_summary.py -q`
Expected: PASS。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/models.py src/projectapp/teams.py test/test_teams.py test/test_storage.py test/test_reference_storage.py test/test_summary.py
git commit -m "feat: チームのモデルと検証・正規化・削除の反映(要望 85 段階 1)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 保存・読込と設定ファイル

**Files:**
- Modify: `src/projectapp/storage.py`
- Modify: `src/projectapp/settings_io.py`
- Test: `test/test_storage.py`、`test/test_settings_io.py`

**Interfaces:**
- Consumes: Task 1 の `Team`・`Membership`・`team_name_error`・`membership_error`。
- Produces: `dumps_project` / `parse_project` がチームと所属を往復する。`_check_unique_ids` が重複したチーム id と、読めない所属を拒否する。`settings_io.build_settings` は `teams` を含めず、メンバーの `teams` を空にする。

- [ ] **Step 1: 失敗するテストを書く(storage)**

`test/test_storage.py` の末尾に足す。`Team`・`Membership` を `projectapp.models` の import に足し、ファイルに `import json` がなければ足す(すでにある)。

```python
def team_project() -> Project:
    return Project(
        "p",
        base_date=date(2026, 10, 5),
        teams=[Team("開発", id="t1"), Team("QA", id="t2")],
        members=[
            Member("甲", id="m1", teams=[Membership("t1", 60), Membership("t2", 40)]),
            Member("乙", id="m2", teams=[Membership("t2", 100)]),
            Member("丙", id="m3"),
        ],
    )


def team_dict() -> dict:
    return json.loads(dumps_project(team_project()))


def test_teams_and_memberships_round_trip() -> None:
    loaded = parse_project(dumps_project(team_project()), "p")
    assert [(t.id, t.name) for t in loaded.teams] == [("t1", "開発"), ("t2", "QA")]
    assert loaded.members[0].teams == [Membership("t1", 60), Membership("t2", 40)]
    assert loaded.members[2].teams == []


def test_a_file_without_team_keys_loads_as_no_teams() -> None:
    raw = team_dict()
    raw["version"] = 16
    del raw["teams"]
    for member in raw["members"]:
        del member["teams"]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.teams == [] and all(m.teams == [] for m in loaded.members)


def test_teams_in_a_version_16_file_are_ignored() -> None:
    raw = team_dict()
    raw["version"] = 16
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.teams == [] and all(m.teams == [] for m in loaded.members)


@pytest.mark.parametrize(
    "edit",
    [
        lambda raw: raw["members"][0]["teams"].append({"team_id": "zzz", "percent": 0}),  # 未知のチーム
        lambda raw: raw["members"][0].update(teams=[{"team_id": "t1", "percent": 50}, {"team_id": "t1", "percent": 50}]),
        lambda raw: raw["members"][0].update(teams=[{"team_id": "t1", "percent": 60}, {"team_id": "t2", "percent": 30}]),
        lambda raw: raw["members"][0].update(teams=[{"team_id": "t1", "percent": 60.5}, {"team_id": "t2", "percent": 39.5}]),
        lambda raw: raw["members"][0].update(teams=[{"team_id": "t1", "percent": True}]),
        lambda raw: raw["members"][0].update(teams=[{"team_id": "t1", "percent": 0}, {"team_id": "t2", "percent": 100}]),
        lambda raw: raw["members"][0].update(teams=[{"team_id": 1, "percent": 100}]),
        lambda raw: raw["members"][0].update(teams="x"),
        lambda raw: raw.update(teams="x"),
        lambda raw: raw["teams"].append({"name": "開発", "id": "t3"}),  # 名前の重複
        lambda raw: raw["teams"].append({"name": "別", "id": "t1"}),  # id の重複
        lambda raw: raw["teams"].append({"name": "", "id": "t3"}),
        lambda raw: raw["teams"].append({"name": "あ" * 31, "id": "t3"}),
        lambda raw: raw["teams"].append({"name": "別", "id": ""}),
        lambda raw: raw["teams"].append("x"),
    ],
)
def test_bad_teams_are_rejected_on_load(edit) -> None:
    raw = team_dict()
    edit(raw)
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_dumping_refuses_a_membership_of_an_unknown_team() -> None:
    project = team_project()
    project.members[2].teams = [Membership("zzz", 100)]
    with pytest.raises(ValueError):
        dumps_project(project)


def test_dumping_refuses_duplicate_team_ids() -> None:
    project = team_project()
    project.teams[1].id = "t1"
    with pytest.raises(ValueError, match="チーム"):
        dumps_project(project)


def test_members_added_for_unknown_assignees_are_saved_without_teams() -> None:
    project = team_project()
    project.tasks = [Task("a", id="a", assignees=[Assignee("新人", 1.0)])]
    loaded = parse_project(dumps_project(project), "p")
    assert next(m for m in loaded.members if m.name == "新人").teams == []
```

- [ ] **Step 2: 失敗するテストを書く(settings_io)**

`test/test_settings_io.py` の末尾に足す(`Team`・`Membership`・`Member`・`Project` を import に足す)。既存のテストが使う `build_settings`・`parse_settings` の呼び方に合わせる。

```python
def test_the_settings_file_has_no_teams_and_members_have_no_memberships() -> None:
    project = Project(
        "p",
        teams=[Team("開発", id="t1")],
        members=[Member("甲", id="m1", teams=[Membership("t1", 100)])],
    )
    data = build_settings(project)
    assert "teams" not in data
    assert data["members"][0]["teams"] == []
    imported = parse_settings(json.dumps(data))  # 読める(未知のチームを指す所属が残っていない)
    assert imported.project.members[0].teams == []
```

`parse_settings` の戻り値(`ImportFile`)のフィールド名は、既存のテストの使い方に合わせて直す(`ImportFile` の定義は `settings_io.py` 76 行付近)。

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_storage.py -k "team or membership" test/test_settings_io.py -q`
Expected: FAIL。

- [ ] **Step 4: `storage.py` を実装する**

1. import に `Membership`・`Team` を足し、`from projectapp.teams import membership_error, team_name_error` を足す(`teams.py` は `models` だけに依存するので循環しない)。
2. `_check_unique_ids` の `groups` に `"チーム": [t.id for t in project.teams],` を足し、`for label, ids in groups.items():` のループのあとに足す。

```python
    team_ids = {t.id for t in project.teams}
    for member in project.members:
        error = membership_error(member.teams, team_ids)
        if error is not None:
            raise ValueError(f"{member.name}: {error}")
```

   docstring は「…id の重複と、読めないチームの所属があれば ValueError」に直す。
3. `_dump` の、メンバーを補う辞書に `"teams": []` を足す: `data["members"].append({"name": name, "ratio": 1.0, "levels": {}, "id": ids[name], "icon": "", "work_days": [], "teams": []})`。
4. `_Context` に足す。

```python
    team_ids: set[str] = field(default_factory=set)  # version 17: 読んだチームの id(メンバーの所属の検証に使う)
```

5. `_events` の近くに足す。

```python
def _teams(value: Any) -> list[Team]:
    """チーム(version 17)。キーがない・null は空。名前の空・重複・長さ・制御文字、id の不正・重複は ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("チームがリストではありません")
    teams: list[Team] = []
    names: set[str] = set()
    ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("チームの形式が正しくありません")
        name = raw.get("name")
        if not isinstance(name, str):
            raise ValueError("チームの名前が文字列ではありません")
        error = team_name_error(name, names)
        if error is not None:
            raise ValueError(error)
        team_id = _entity_id(raw.get("id"), "チーム")
        if team_id in ids:
            raise ValueError(f"チームの id が重複しています: {team_id}")
        names.add(name.strip())
        ids.add(team_id)
        teams.append(Team(name.strip(), team_id))
    return teams


def _memberships(value: Any, team_ids: set[str]) -> list[Membership]:
    """メンバーの所属(version 17)。キーがない・null は空。存在しないチーム・重複・割合の不正・合計が 100 でないものは ValueError。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("メンバーの所属がリストではありません")
    rows: list[Membership] = []
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("team_id"), str):
            raise ValueError("メンバーの所属の形式が正しくありません")
        rows.append(Membership(raw["team_id"], raw.get("percent")))  # type: ignore[arg-type]  # 割合の型は membership_error が見る
    error = membership_error(rows, team_ids)
    if error is not None:
        raise ValueError(error)
    return rows
```

6. `_members` の `unclamped = ...` 検証の直後に足し、`Member(...)` の呼び出しに `teams=teams` を足す。

```python
        teams = _memberships(raw.get("teams"), ctx.team_ids) if ctx.version >= 17 else []
```

7. `parse_project` の `members = _members(...)` の前に足し、`Project(...)` に `teams=teams,` を足す。

```python
    teams = _teams(raw.get("teams")) if ctx.version >= 17 else []
    ctx.team_ids = {t.id for t in teams}
```

- [ ] **Step 5: `settings_io.build_settings` を直す**

`data.update(...)` のあとに足す。

```python
    data["members"] = [{**member, "teams": []} for member in data["members"]]  # チームと所属は設定ファイルに含めない
```

   docstring に「チームと所属は含めない」を足す。

- [ ] **Step 6: テストが通ることを確かめる**

Run: `uv run pytest test/test_storage.py test/test_settings_io.py test/test_teams.py -q`
Expected: PASS。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/storage.py src/projectapp/settings_io.py test/test_storage.py test/test_settings_io.py
git commit -m "feat: チームの保存・読込(version 17)と設定ファイルからの除外

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 3 者マージ

**Files:**
- Modify: `src/projectapp/merge.py`
- Test: `test/test_merge.py`

**Interfaces:**
- Consumes: Task 1 の `Team`・`Membership`・`normalize`。
- Produces: `merge_projects` がチーム(kind `"team"`、鍵は id)と、メンバーの `teams` を扱う。削除されたチームへの所属は外して割合を揃え、通知を出す。同名で id の違うチームは、名前を変えて両方残し、通知を出す。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_merge.py` の末尾に足す(`Team`・`Membership` を import に足す)。

```python
def ms(*pairs: tuple[str, int]) -> list[Membership]:
    return [Membership(team_id, percent) for team_id, percent in pairs]


def team_base() -> Project:
    return proj(
        teams=[Team("開発", id="a"), Team("QA", id="b")],
        members=[Member("甲", 1.0, id="m1", teams=ms(("a", 60), ("b", 40)))],
    )


def test_team_added_on_one_side_is_taken() -> None:
    base = team_base()
    theirs = replace(base, teams=[*base.teams, Team("運用", id="c")])
    result = merge_projects(base, base, theirs)
    assert [t.id for t in result.project.teams] == ["a", "b", "c"]
    assert result.conflicts == []


def test_team_rename_on_both_sides_is_a_conflict() -> None:
    base = team_base()
    ours = replace(base, teams=[Team("開発1", id="a"), base.teams[1]])
    theirs = replace(base, teams=[Team("開発2", id="a"), base.teams[1]])
    result = merge_projects(base, ours, theirs)
    assert [(c.kind, c.key, c.field) for c in result.conflicts] == [("team", "a", "名前")]
    assert result.project.teams[0].name == "開発1"
    chosen = merge_projects(base, ours, theirs, {("team", "a", "名前"): THEIRS})
    assert chosen.project.teams[0].name == "開発2"


def test_membership_change_on_one_side_is_taken_as_a_whole_list() -> None:
    base = team_base()
    theirs = replace(base, members=[Member("甲", 1.0, id="m1", teams=ms(("a", 100)))])
    result = merge_projects(base, base, theirs)
    assert result.project.members[0].teams == ms(("a", 100))
    assert result.conflicts == []


def test_membership_change_on_both_sides_is_one_conflict_shown_with_team_names() -> None:
    base = team_base()
    ours = replace(base, members=[Member("甲", 1.0, id="m1", teams=ms(("a", 100)))])
    theirs = replace(base, members=[Member("甲", 1.0, id="m1", teams=ms(("b", 100)))])
    result = merge_projects(base, ours, theirs)
    [conflict] = result.conflicts
    assert (conflict.kind, conflict.field) == ("member", "所属チーム")
    assert conflict.ours == ["開発 100%"] and conflict.theirs == ["QA 100%"]


def test_a_team_deleted_on_one_side_is_removed_from_memberships_and_the_rest_is_renormalized() -> None:
    base = team_base()
    ours = replace(base, teams=[base.teams[0]])  # 自分は QA を削除(所属は触らない = base のまま)
    result = merge_projects(base, ours, base)
    assert [t.id for t in result.project.teams] == ["a"]
    assert result.project.members[0].teams == ms(("a", 100))
    assert any("甲" in note and "チーム" in note for note in result.notes)


def test_a_membership_added_to_a_team_the_other_side_deleted_is_dropped_with_a_note() -> None:
    base = proj(teams=[Team("開発", id="a")], members=[Member("甲", 1.0, id="m1")])
    ours = replace(base, teams=[])
    theirs = replace(base, members=[Member("甲", 1.0, id="m1", teams=ms(("a", 100)))])
    result = merge_projects(base, ours, theirs)
    assert result.project.teams == []
    assert result.project.members[0].teams == []
    assert result.notes


def test_same_named_teams_added_on_both_sides_both_stay_with_a_rename_note() -> None:
    base = proj()
    ours = replace(base, teams=[Team("開発", id="x")])
    theirs = replace(base, teams=[Team("開発", id="y")])
    result = merge_projects(base, ours, theirs)
    assert sorted(t.name for t in result.project.teams) == ["開発", "開発 (2)"]
    assert any("同名のチーム" in note for note in result.notes)


def test_merged_files_with_teams_load_again() -> None:
    from projectapp.storage import dumps_project

    base = team_base()
    theirs = replace(base, teams=[*base.teams, Team("運用", id="c")])
    merged = merge_projects(base, base, theirs).project
    dumps_project(merged)  # 例外にならない(読み直せる形)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_merge.py -k "team or membership" -q`
Expected: FAIL。

- [ ] **Step 3: 実装する**

`src/projectapp/merge.py`:

1. import に `Membership`・`Team` を足し、`from projectapp.teams import normalize` を足す。
2. ラベルと記録を足す。`MEMBER_LABELS` に `"teams": "所属チーム"` を足し、`CATEGORY_LABELS` の前に足す。

```python
TEAM_LABELS = {"name": "名前"}
```

   `_members` の辞書に `"teams": [(s.team_id, s.percent) for s in m.teams]` を足す。`_categories` の前に足す。

```python
def _teams(project: Project) -> dict[str, Record]:
    return {t.id: {"name": t.name} for t in project.teams}
```

3. `merge_projects` で、`assert settings is not None` の次に足す。

```python
    teams = merger.collection("team", TEAM_LABELS, _teams(base), _teams(ours), _teams(theirs))
    team_names = {t.id: t.name for source in (base, theirs, ours) for t in source.teams}  # 自分の名前を優先
```

   `members = merger.collection("member", MEMBER_LABELS, ...)` に表示関数を足す。

```python
    def show_member(name: str, value: Any) -> Any:
        if name == "teams":
            return [f"{team_names.get(team_id, team_id)} {percent}%" for team_id, percent in value]
        return value

    members = merger.collection(
        "member", MEMBER_LABELS, _members(base), _members(ours), _members(theirs), show_member
    )
```

4. 同名メンバーの名前を変える処理の直前(`seen: set[str] = set()` の前)に、同名のチームの名前を変える処理を足す。

```python
    team_seen: set[str] = set()  # 同名で id の違うチームも、読み直すと拒否されるので、名前を変えて両方残す
    team_taken = {record["name"] for record in teams.values()}
    for record in teams.values():
        name = record["name"]
        if name in team_seen:
            number = 2
            while f"{name} ({number})" in team_taken | team_seen:
                number += 1
            renamed = f"{name} ({number})"
            notes.append(f"同名のチームがいたため、名前を変えました: {name} → {renamed}")
            record["name"] = name = renamed
        team_seen.add(name)
```

   `record()` は、片側だけが追加した記録を `theirs`/`ours` そのままで返すので、`record["name"] = ...` がもとのプロジェクトの記録辞書を書き換えうる。`_teams()` が呼び出しごとに新しい辞書を作るので、プロジェクト自体は変わらない。
5. メンバーを組み立てる箇所(`built_members = [...]`)を、所属を整える形に直す。

```python
    team_ids = set(teams)

    def settle_teams(record: Record) -> list[Membership]:
        rows = [Membership(team_id, percent) for team_id, percent in record["teams"]]
        kept = [s for s in rows if s.team_id in team_ids]
        if len(kept) != len(rows):
            notes.append(f"削除されたチームへの所属を外しました: {record['name']}")
            return normalize(kept)
        return rows

    built_members = [
        Member(
            r["name"], r["ratio"], dict(r["levels"]), id=key, icon=r["icon"], ratio_unclamped=r["ratio_unclamped"],
            teams=settle_teams(r),
        )
        for key, r in members.items()
    ]
```

6. `Project(...)` に `teams=[Team(r["name"], id=key) for key, r in teams.items()],` を足す。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest test/test_merge.py test/test_teams.py -q`
Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/merge.py test/test_merge.py
git commit -m "feat: チームと所属の 3 者マージ

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `チーム`タブと管理画面の配線

**Files:**
- Create: `src/projectapp/teams_dialog.py`(`teams_panel`)
- Modify: `src/projectapp/forms.py`(`MemberRow.teams`・`build_members`・`members_panel` の追従・ダイアログのタブ)
- Modify: `src/projectapp/views.py`(`apply_teams`・配線)
- Test: `test/test_views.py`、`test/test_forms.py`

**Interfaces:**
- Consumes: Task 1 の `TeamRow`・`build_teams`・`replace_teams`・`removal_impacts`・`normalize`・`membership_error`。
- Produces:
  - `teams_dialog.teams_panel(get_teams: Callable[[], list[Team]], impacts: Callable[[list[Team]], list[str]], on_apply: Callable[[list[Team]], object], on_applied: Callable[[set[str]], object], get_taken: Callable[[], Collection[str]]) -> TeamsPanel`。`TeamsPanel(dirty: Callable[[], bool], apply: Callable[[Callable[[], None] | None], None])`。マーカー: `team-name-{i}`・`team-delete-{i}`・`team-add`・`team-apply`・`team-error`・`team-delete-confirm`・`team-delete-cancel`。
  - `forms.MemberRow.teams: list[Membership]`(末尾のフィールド)。`forms.build_members(..., team_ids: Collection[str] = ())`。
  - `forms.members_panel(..., get_teams: Callable[[], list[Team]] = list)` が返す `MembersPanel` に `teams_changed: Callable[[set[str]], None]` を足す(削除したチームの id の集合を受け、未適用の行と基準から所属を外して正規化する)。
  - `forms.open_members_parameters_dialog(..., get_teams=list, team_impacts=lambda teams: [], on_apply_teams=lambda teams: None)`。タブのキーは `"teams"`、見出しのマーカーは `tab-teams`、未適用の印は `teams-dirty`。`閉じる`の確定順は パラメータ → チーム → メンバー。
  - `views.MainView.apply_teams(teams: list[Team]) -> None`。

- [ ] **Step 1: 失敗するテストを書く(forms)**

`test/test_forms.py` に、既存の `build_members` のテストの近くへ足す(`Membership`・`MemberRow` を import に足す)。

```python
def test_build_members_carries_memberships_and_checks_them() -> None:
    rows = [MemberRow(None, "甲", 100.0, teams=[Membership("a", 60), Membership("b", 40)])]
    members, _ = build_members(rows, [], lambda name: 0, team_ids={"a", "b"})
    assert members[0].teams == [Membership("a", 60), Membership("b", 40)]


def test_build_members_rejects_a_bad_membership_with_the_member_name() -> None:
    rows = [MemberRow(None, "甲", 100.0, teams=[Membership("a", 60), Membership("b", 30)])]
    with pytest.raises(ValueError, match="甲: 所属の割合の合計を 100%"):
        build_members(rows, [], lambda name: 0, team_ids={"a", "b"})


def test_build_members_rejects_a_membership_of_an_unknown_team() -> None:
    rows = [MemberRow(None, "甲", 100.0, teams=[Membership("zzz", 100)])]
    with pytest.raises(ValueError, match="存在しないチーム"):
        build_members(rows, [], lambda name: 0, team_ids={"a"})
```

- [ ] **Step 2: 失敗するテストを書く(画面)**

`test/test_views.py` の末尾に足す(`Team`・`Membership` を import に足す)。

```python
async def test_the_teams_tab_adds_renames_and_applies_without_closing(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    await user.should_see(marker="tab-teams")
    user.find(marker="tab-teams").click()
    user.find(marker="team-add").click()
    await user.should_see(marker="team-name-0")
    user.find(marker="team-name-0").type("開発")
    user.find(marker="team-apply").click()
    assert await wait_until(lambda: [t.name for t in view.project.teams] == ["開発"])
    await user.should_see(marker="members-parameters-panels")  # 閉じない


async def test_the_teams_tab_shows_errors_and_changes_nothing(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="tab-teams").click()
    user.find(marker="team-add").click()
    await user.should_see(marker="team-name-0")
    user.find(marker="team-apply").click()  # 名前が空
    assert await wait_until(lambda: "名前を入力" in user.find(marker="team-error").elements.pop().text)
    assert view.project.teams == []


async def test_team_delete_without_members_applies_without_a_confirmation(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.teams = [Team("開発", id="t1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="tab-teams").click()
    user.find(marker="team-delete-0").click()
    user.find(marker="team-apply").click()
    assert await wait_until(lambda: view.project.teams == [])


async def test_team_delete_with_members_asks_then_drops_memberships_and_renormalizes(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.teams = [Team("開発", id="t1"), Team("QA", id="t2"), Team("運用", id="t3")]
    view.project.members = [Member("甲", 1.0, id="m1", teams=[Membership("t1", 60), Membership("t2", 30), Membership("t3", 10)])]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="tab-teams").click()
    user.find(marker="team-delete-2").click()  # 運用を削除
    user.find(marker="team-apply").click()
    await user.should_see(marker="team-delete-confirm")
    assert view.project.teams[2].name == "運用"  # 確認の前は変わらない
    user.find(marker="team-delete-confirm").click()
    assert await wait_until(lambda: [t.name for t in view.project.teams] == ["開発", "QA"])
    assert view.project.members[0].teams == [Membership("t1", 67), Membership("t2", 33)]


async def test_team_delete_also_fixes_unapplied_member_rows_without_marking_the_members_tab(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.teams = [Team("開発", id="t1"), Team("QA", id="t2")]
    view.project.members = [Member("甲", 1.0, id="m1", teams=[Membership("t1", 60), Membership("t2", 40)])]
    view.mark_clean()
    await open_members_parameters(user)
    members_mark = user.find(marker="members-dirty").elements.pop()
    user.find(marker="member-name-0").clear().type("甲田")  # 未適用の編集
    user.find(marker="tab-teams").click()
    user.find(marker="team-delete-1").click()  # QA を削除
    user.find(marker="team-apply").click()
    await user.should_see(marker="team-delete-confirm")
    user.find(marker="team-delete-confirm").click()
    assert await wait_until(lambda: [t.name for t in view.project.teams] == ["開発"])
    user.find(marker="tab-members").click()
    user.find(marker="member-apply").click()  # 未適用の行の所属が正規化されているので、検証を通る
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["甲田"])
    assert view.project.members[0].teams == [Membership("t1", 100)]
    assert members_mark.text == ""


async def test_closing_applies_teams_before_members(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    user.find(marker="tab-teams").click()
    user.find(marker="team-add").click()
    await user.should_see(marker="team-name-0")
    user.find(marker="team-name-0").type("開発")
    user.find(marker="members-parameters-close").click()
    assert await wait_until(lambda: [t.name for t in view.project.teams] == ["開発"])


async def test_the_teams_tab_shows_a_mark_while_it_has_unapplied_edits(user: User, tmp_path: Path) -> None:
    await open_members_view(user, tmp_path)
    await open_members_parameters(user)
    teams_mark = user.find(marker="teams-dirty").elements.pop()
    assert teams_mark.text == ""
    user.find(marker="tab-teams").click()
    user.find(marker="team-add").click()
    assert await wait_until(lambda: teams_mark.text == "●")
```


- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py -k "memberships or membership" test/test_views.py -k "team" -q`
Expected: FAIL。

- [ ] **Step 4: `forms.py` を直す(メンバーの行と検証)**

1. import に `Membership`・`Team` を足し(`from projectapp.models import (...)` の中)、`from projectapp.teams import membership_error, normalize` を足す。
2. `MemberRow` の末尾に足す。

```python
    teams: list[Membership] = field(default_factory=list)  # 所属するチーム(割合の合計 100。空はチームなし)
```

3. `build_members` の引数に `team_ids: Collection[str] = ()` を足し(`today` のあと)、docstring に「`team_ids` は、所属を検証する、今あるチームの id」を足す。行のループの `member_id = row.id or new_id(used)` の前に足す。

```python
        team_error = membership_error(row.teams, team_ids)
        if team_error is not None:
            raise ValueError(f"{name}: {team_error}")
```

   `members.append(Member(...))` を、最後の引数に `teams=[Membership(s.team_id, s.percent) for s in row.teams]` を足した形に直す。

- [ ] **Step 5: `teams_dialog.py` を書く(`チーム`タブ)**

`src/projectapp/teams_dialog.py`:

```python
"""チームのタブ(`メンバーとパラメータ`のダイアログの 3 つ目)。"""

from collections.abc import Callable, Collection
from copy import deepcopy
from dataclasses import dataclass

from nicegui import ui

from projectapp.models import Team
from projectapp.teams import TeamRow, build_teams


@dataclass
class TeamsPanel:
    """チームのタブの操作。dirty は未適用の編集があるか、apply は適用(続きの処理は、適用できたときだけ呼ぶ)。"""

    dirty: Callable[[], bool]
    apply: Callable[[Callable[[], None] | None], None]


def teams_panel(
    get_teams: Callable[[], list[Team]],
    impacts: Callable[[list[Team]], list[str]],
    on_apply: Callable[[list[Team]], object],
    on_applied: Callable[[set[str]], object],
    get_taken: Callable[[], Collection[str]],
) -> TeamsPanel:
    """チームの登録(タブの中身)。削除で所属が外れるメンバーがいるときは、適用の前に確認する。
    適用してもダイアログは閉じず、プロジェクトの今のチームから行を作り直す。`on_applied` には、削除したチームの id を渡す。"""

    def to_rows() -> list[TeamRow]:
        return [TeamRow(t.id, t.name) for t in get_teams()]

    rows = to_rows()
    baseline = deepcopy(rows)
    ui.label("メンバーを所属させて、担当の割り当てと絞り込み・集計に使います").classes("text-caption text-grey")

    @ui.refreshable
    def table() -> None:
        with ui.column().classes("w-full gap-1"):
            if not rows:
                ui.label("チームがありません").classes("text-grey")
            for index, row in enumerate(rows):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.input(
                        "チーム名",
                        value=row.name,
                        on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                    ).classes("flex-1").mark(f"team-name-{index}")
                    ui.button(icon="delete", on_click=lambda _e, r=row: remove(r)).props(
                        "flat dense round color=negative"
                    ).mark(f"team-delete-{index}")

    def add() -> None:
        rows.append(TeamRow(None, ""))
        table.refresh()

    def remove(row: TeamRow) -> None:
        rows.remove(row)
        table.refresh()

    table()
    ui.button("チームを追加", icon="add", on_click=add).props("flat").mark("team-add")
    error = ui.label("").classes("text-negative").mark("team-error")
    pending: dict[str, list[Team]] = {}
    after: dict[str, Callable[[], None] | None] = {"then": None}
    with ui.dialog() as confirm, ui.card():
        confirm_text = ui.label("").style("white-space: pre-line")
        with ui.row():
            ui.button("キャンセル", on_click=confirm.close).props("flat").mark("team-delete-cancel")
            ui.button("削除する", on_click=lambda: confirm_apply()).props("color=negative").mark("team-delete-confirm")

    def commit(teams: list[Team], then: Callable[[], None] | None) -> None:
        removed = {t.id for t in get_teams()} - {t.id for t in teams}
        on_apply(teams)
        on_applied(removed)
        rows[:] = to_rows()
        baseline[:] = deepcopy(rows)
        table.refresh()
        if then is not None:
            then()

    def confirm_apply() -> None:
        confirm.close()
        commit(pending["teams"], after["then"])

    def apply(then: Callable[[], None] | None = None) -> None:
        error.set_text("")
        try:
            teams = build_teams(rows, get_taken())
        except ValueError as exc:
            error.set_text(str(exc))
            return
        affected = impacts(teams)
        if affected:
            pending["teams"] = teams
            after["then"] = then
            confirm_text.set_text("\n".join(affected) + "\n削除すると、その所属は外れます(残りの割合は 100% に揃えます)")
            confirm.open()
            return
        commit(teams, then)

    ui.button("適用", on_click=lambda: apply()).mark("team-apply")
    return TeamsPanel(dirty=lambda: rows != baseline, apply=apply)
```

- [ ] **Step 6: `forms.py` にタブと追従を配線する**

1. `members_panel` の引数に `get_teams: Callable[[], list[Team]] = list` を足す(`get_holidays` のあと)。`to_rows` の `MemberRow(...)` の最後の引数に `[Membership(s.team_id, s.percent) for s in m.teams]` を足す。`apply` の `build_members(...)` の呼び出しに `team_ids={t.id for t in get_teams()}` を足す(`build_members(rows, originals, assigned, current["parameters"], get_taken(), team_ids=...)`)。
2. `MembersPanel` に `teams_changed: Callable[[set[str]], None]` を足す(docstring に「teams_changed は、チームの削除を、未適用の行へ伝える」)。`parameters_changed` の次に足す。

```python
    def teams_changed(removed: set[str]) -> None:
        for row in (*rows, *baseline):  # 未適用の行も、適用済みの基準も、同じように写す(印が出ない)
            row.teams = normalize([s for s in row.teams if s.team_id not in removed])
        table.refresh()
```

   `return MembersPanel(...)` に `teams_changed=teams_changed,` を足す。
3. `open_members_parameters_dialog` の引数に足す。

```python
    get_teams: Callable[[], list[Team]] = list,
    team_impacts: Callable[[list[Team]], list[str]] = lambda teams: [],
    on_apply_teams: Callable[[list[Team]], object] = lambda teams: None,
```

   `members_panel(...)` の呼び出しに `get_teams` を足す。タブの見出しに、`parameters` の次の行として足す。

```python
            with ui.tab("teams", label="").mark("tab-teams"), ui.row().classes("items-center no-wrap gap-1"):
                ui.label("チーム")
                teams_mark = ui.label("").classes("text-orange").mark("teams-dirty")
```

   パネルに、`parameters` のパネルの次に足す。

```python
            with ui.tab_panel("teams"):
                teams = teams_panel(
                    get_teams, team_impacts, on_apply_teams, lambda removed: members.teams_changed(removed), get_taken
                )
```

   `update_marks` に `teams_mark.set_text("●" if teams.dirty() else "")` を足す。`close_after_apply` を、パラメータ → チーム → メンバーの順に直す。

```python
            def apply_members() -> None:
                if members.dirty():
                    tabs.set_value("members")
                    members.apply(close_dialog)
                else:
                    close_dialog()

            def apply_teams() -> None:
                if teams.dirty():
                    tabs.set_value("teams")
                    teams.apply(apply_members)
                else:
                    apply_members()

            if parameters.dirty():
                tabs.set_value("parameters")
                parameters.apply(apply_teams)
            else:
                apply_teams()
```

   ファイル先頭の import に `from projectapp.teams_dialog import teams_panel` を足す。`teams_dialog` は `forms` を import しないので、循環しない。
4. `views.py`: import に `Team` を足し、`from projectapp.teams import removal_impacts, replace_teams` を足す。`apply_members` の次に足す。

```python
    def apply_teams(self, teams: list[Team]) -> None:
        """チームを更新し、消えたチームへの所属をメンバーから外す。保存はしない(編集中の判定に入る)。"""
        if [(t.id, t.name) for t in teams] == [(t.id, t.name) for t in self.project.teams]:
            return
        replace_teams(self.project, teams)
        self.after_edit()
```

   `open_members_parameters_dialog(...)` の呼び出しに足す。

```python
            get_teams=lambda: self.project.teams,
            team_impacts=lambda teams: removal_impacts(self.project, teams),
            on_apply_teams=self.apply_teams,
```

- [ ] **Step 7: テストが通ることを確かめる**

Run: `uv run pytest test/test_forms.py test/test_views.py -k "team or member or parameter" -q`
Expected: PASS。

- [ ] **Step 8: コミット**

```bash
git add src/projectapp/teams_dialog.py src/projectapp/forms.py src/projectapp/views.py test/test_forms.py test/test_views.py
git commit -m "feat: メンバーとパラメータのダイアログにチームのタブを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: メンバーの表の`チーム`列と所属ダイアログ

**Files:**
- Modify: `src/projectapp/teams_dialog.py`(`open_member_teams_dialog`)
- Modify: `src/projectapp/forms.py`(列・見出し・ボタン)
- Test: `test/test_views.py`、`test/test_forms.py`

**Interfaces:**
- Consumes: Task 1 の `settle_memberships`・`even_split`・`membership_summary`。Task 4 の `MemberRow.teams`・`get_teams`。
- Produces:
  - `teams_dialog.open_member_teams_dialog(name: str, teams: list[Team], current: list[Membership], on_save: Callable[[list[Membership]], object]) -> None`。マーカー: `mteam-check-{i}`・`mteam-percent-{i}`・`mteam-save`・`mteam-cancel`・`mteam-error`。
  - `forms.member_columns(level_count, with_effective, with_teams=False)`・`forms.member_table_min_rem(level_count, with_effective, with_teams=False)`。定数 `MEMBER_TEAMS_COLUMN_REM = 10`。
  - メンバーの表の`チーム`列(チームが 1 つ以上あるときだけ)。ボタンのマーカーは `member-teams-open-{i}`、見出しは `member-header-teams`。

- [ ] **Step 1: 失敗するテストを書く(forms)**

`test/test_forms.py` に足す(`member_columns`・`member_table_min_rem` が import 済みでなければ足す)。

```python
def test_member_columns_add_a_teams_column_only_when_asked() -> None:
    assert len(member_columns(0, False, True)) == len(member_columns(0, False)) + 1
    assert member_table_min_rem(0, False, True) > member_table_min_rem(0, False)
```

- [ ] **Step 2: 失敗するテストを書く(画面)**

`test/test_views.py` に足す。

```python
def team_members_view_setup(view: MainView) -> None:
    view.project.teams = [Team("開発", id="t1"), Team("QA", id="t2")]
    view.project.members = [Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2", teams=[Membership("t1", 100)])]
    view.mark_clean()


async def test_the_members_table_has_a_teams_column_only_when_teams_exist(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("甲", 1.0, id="m1")]
    view.mark_clean()
    await open_members_parameters(user)
    assert not user.find(marker="member-header-teams").elements


async def test_the_teams_button_shows_the_summary(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    team_members_view_setup(view)
    await open_members_parameters(user)
    await user.should_see(marker="member-header-teams")
    assert user.find(marker="member-teams-open-0").elements.pop().text == "チーム"
    assert user.find(marker="member-teams-open-1").elements.pop().text == "開発"


async def test_choosing_two_teams_splits_evenly_and_saves_on_apply(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    team_members_view_setup(view)
    await open_members_parameters(user)
    user.find(marker="member-teams-open-0").click()
    await user.should_see(marker="mteam-save")
    user.find(marker="mteam-check-0").elements.pop().set_value(True)
    user.find(marker="mteam-check-1").elements.pop().set_value(True)
    assert user.find(marker="mteam-percent-0").elements.pop().value == 50
    user.find(marker="mteam-percent-0").elements.pop().set_value(70)
    user.find(marker="mteam-percent-1").elements.pop().set_value(30)
    user.find(marker="mteam-save").click()
    assert await wait_until(lambda: user.find(marker="member-teams-open-0").elements.pop().text == "開発 70%・QA 30%")
    assert view.project.members[0].teams == []  # 適用するまでは変わらない
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].teams == [Membership("t1", 70), Membership("t2", 30)])


async def test_choosing_one_team_hides_the_percent_and_saves_100(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    team_members_view_setup(view)
    await open_members_parameters(user)
    user.find(marker="member-teams-open-0").click()
    await user.should_see(marker="mteam-save")
    user.find(marker="mteam-check-1").elements.pop().set_value(True)
    assert not user.find(marker="mteam-percent-1").elements.pop().visible
    user.find(marker="mteam-save").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].teams == [Membership("t2", 100)])


async def test_a_bad_total_shows_an_error_and_keeps_the_dialog_open(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    team_members_view_setup(view)
    await open_members_parameters(user)
    user.find(marker="member-teams-open-0").click()
    await user.should_see(marker="mteam-save")
    user.find(marker="mteam-check-0").elements.pop().set_value(True)
    user.find(marker="mteam-check-1").elements.pop().set_value(True)
    user.find(marker="mteam-percent-0").elements.pop().set_value(70)
    user.find(marker="mteam-percent-1").elements.pop().set_value(40)
    user.find(marker="mteam-save").click()
    assert await wait_until(lambda: "合計を 100%" in user.find(marker="mteam-error").elements.pop().text)
    await user.should_see(marker="mteam-save")  # 閉じない


async def test_unchecking_every_team_clears_the_membership(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    team_members_view_setup(view)
    await open_members_parameters(user)
    user.find(marker="member-teams-open-1").click()
    await user.should_see(marker="mteam-save")
    assert user.find(marker="mteam-check-0").elements.pop().value is True  # 今の所属が入っている
    user.find(marker="mteam-check-0").elements.pop().set_value(False)
    user.find(marker="mteam-save").click()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[1].teams == [])
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py -k teams_column test/test_views.py -k "teams_button or teams_column or choosing or bad_total or unchecking" -q`
Expected: FAIL。

- [ ] **Step 4: `open_member_teams_dialog` を書く**

`src/projectapp/teams_dialog.py` の import を、次の 2 行に置き換える(既存の `from projectapp.models import Team` と `from projectapp.teams import TeamRow, build_teams` の代わり)。`forms.py` が `teams_dialog` を import するので、`teams_dialog` は `forms` を import しない(循環を避ける)。

```python
from projectapp.models import Membership, Team
from projectapp.teams import TeamRow, build_teams, even_split, settle_memberships
```

ファイルの末尾に足す。

```python
def open_member_teams_dialog(
    name: str,
    teams: list[Team],
    current: list[Membership],
    on_save: Callable[[list[Membership]], object],
) -> None:
    """メンバー 1 人の所属を決める小さなダイアログ。チームごとにチェックを入れ、2 つ以上のときだけ割合(合計 100)を入れる。"""
    percents = {m.team_id: m.percent for m in current}
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"{name or '(名前なし)'} の所属チーム").classes("text-subtitle1")
        ui.label("兼務のときは、割合の合計を 100% にします").classes("text-caption text-grey")
        checks: list[ui.checkbox] = []
        inputs: list[ui.number] = []
        for index, team in enumerate(teams):
            with ui.row().classes("w-full items-center no-wrap gap-3"):
                check = ui.checkbox(team.name, value=team.id in percents).classes("flex-1").mark(f"mteam-check-{index}")
                number = ui.number("割合(%)", value=percents.get(team.id), min=1, max=100, step=5).classes("w-28")
                number.mark(f"mteam-percent-{index}")
            checks.append(check)
            inputs.append(number)
        error = ui.label("").classes("text-negative").mark("mteam-error")

        def checked() -> list[int]:
            return [i for i, check in enumerate(checks) if check.value]

        def show() -> None:
            picked = checked()
            for i, number in enumerate(inputs):
                number.set_visibility(i in picked and len(picked) >= 2)

        def on_check() -> None:
            picked = checked()
            if len(picked) >= 2:  # 選び直したら、均等割りから始める
                for i, share in zip(picked, even_split(len(picked))):
                    inputs[i].set_value(share)
            show()

        for check in checks:
            check.on_value_change(lambda _e: on_check())
        show()

        def save() -> None:
            rows = [(teams[i].id, inputs[i].value) for i in checked()]
            try:
                chosen = settle_memberships(rows, {t.id for t in teams})
            except ValueError as exc:
                error.set_text(str(exc))
                return
            dialog.close()
            on_save(chosen)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("mteam-cancel")
            ui.button("決定", on_click=save).mark("mteam-save")
    dialog.on("hide", dialog.delete)
    dialog.open()
```

   注意: 開いた時点で 2 つ以上チェック済み(兼務)のとき、`on_check` は呼ばれないので、保存済みの割合がそのまま入る(`value=percents.get(...)`)。チェックを足し引きしたときだけ、均等割りに直す。

- [ ] **Step 5: `forms.py` の表に列を足す**

1. 定数を `MEMBER_WORK_DAYS_COLUMN_REM = 7` の次に足す。

```python
MEMBER_TEAMS_COLUMN_REM = 10  # チームの列(所属の要約のボタン)
```

2. `member_columns` と `member_table_min_rem` を直す。

```python
def member_columns(level_count: int, with_effective: bool, with_teams: bool = False) -> list[str]:
```

   `columns.append(f"{MEMBER_WORK_DAYS_COLUMN_REM}rem")` の前に `if with_teams: columns.append(f"{MEMBER_TEAMS_COLUMN_REM}rem")` を足す(docstring の列の並びに`チーム`を足す)。

```python
def member_table_min_rem(level_count: int, with_effective: bool, with_teams: bool = False) -> int:
```

   戻り値の式の `+ MEMBER_WORK_DAYS_COLUMN_REM` の前に `+ (MEMBER_TEAMS_COLUMN_REM if with_teams else 0)` を足し、間隔の概算 `2 * (6 + level_count + (1 if with_effective else 0))` に `+ (1 if with_teams else 0)` を足す。
3. `members_panel` の `layout()` を、チームの有無も返す形に直す。

```python
    def layout() -> tuple[list[Parameter], bool, list[str], int, bool]:
        parameters = current["parameters"]
        with_effective = bool(parameters)
        with_teams = bool(get_teams())
        return (
            parameters,
            with_effective,
            member_columns(len(parameters), with_effective, with_teams),
            member_table_min_rem(len(parameters), with_effective, with_teams),
            with_teams,
        )
```

   `layout()` の戻り値を使う箇所を直す: `table()` の先頭を `chosen_parameters, with_effective, columns, min_rem, with_teams = layout()` に、`MembersPanel(min_rem=lambda: layout()[3])` はそのまま(添字 3 が `min_rem` のまま)。
4. 見出しに足す。`ui.label("稼働日")...mark("member-header-workdays")` の前に足す。

```python
                if with_teams:
                    ui.label("チーム").classes(header).mark("member-header-teams")
```

   行のボタンに足す。`ui.button(f"稼働日({len(row.work_days)})" ...` の前に足す。

```python
                    if with_teams:
                        ui.button(
                            membership_summary(row.teams, get_teams()),
                            on_click=lambda r=row: open_teams(r),
                        ).props("flat dense no-caps").classes("ellipsis").mark(f"member-teams-open-{index}")
```

5. `open_work_days` の次に足す。

```python
    def open_teams(row: MemberRow) -> None:
        def save(chosen: list[Membership]) -> None:
            row.teams = chosen
            table.refresh()

        open_member_teams_dialog(row.name, get_teams(), list(row.teams), save)
```

   import に `from projectapp.teams import membership_error, membership_summary, normalize` と、`from projectapp.teams_dialog import open_member_teams_dialog, teams_panel` を揃える。

- [ ] **Step 6: テストが通ることを確かめる**

Run: `uv run pytest test/test_forms.py test/test_views.py -k "team or member" -q`
Expected: PASS。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/teams_dialog.py src/projectapp/forms.py test/test_forms.py test/test_views.py
git commit -m "feat: メンバーの表にチームの列と所属のダイアログを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: タスクの担当欄に`チームから追加`

**Files:**
- Modify: `src/projectapp/task_dialog.py`
- Modify: `src/projectapp/views.py`(3 か所の `open_task_dialog` 呼び出し)
- Test: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 の `team_member_names`・`add_team_members`。
- Produces: `open_task_dialog(..., teams: list[Team] | None = None)`。担当欄の下に、メンバーのいるチームがあるときだけ、行(`task-team` の選択・`task-team-rate` の割り当て率・`task-team-add` のボタン)を出す。週ごとのタスクでは、担当欄と一緒に隠す。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` の既存のテストの書き方(ダイアログを開く helper、`user.find(marker="task-assignee")` の扱い)に合わせて、次の 5 件を足す。`Team`・`Membership` を import に足す。ここでは `open_task_dialog` を直接開く既存の `mount` helper の名前を `mount_dialog` と書いたので、実際の名前に直す(`grep -n "def mount\|def open_dialog" test/test_task_dialog.py` で確かめる)。

```python
def teamed_members() -> list[Member]:
    return [
        Member("甲", 1.0, id="m1", teams=[Membership("t1", 100)]),
        Member("乙", 1.0, id="m2", teams=[Membership("t1", 50), Membership("t2", 50)]),
        Member("丙", 1.0, id="m3"),
    ]


async def test_the_team_row_is_hidden_when_no_team_has_members(user: User) -> None:
    mount_dialog(None, members=teamed_members(), teams=[Team("空", id="t9")])
    await user.open("/")
    assert not user.find(marker="task-team-add").elements


async def test_adding_a_team_puts_its_members_in_the_crew_at_the_given_rate(user: User) -> None:
    mount_dialog(None, members=teamed_members(), teams=[Team("開発", id="t1"), Team("QA", id="t2")])
    await user.open("/")
    user.find(marker="task-team-rate").elements.pop().set_value(80)
    user.find(marker="task-team-add").click()
    assert await wait_until(lambda: user.find(marker="task-assignee-2").elements)  # 2 人ぶんの行ができる
    assert user.find(marker="task-assignee").elements.pop().value == "甲"
    assert user.find(marker="task-allocation").elements.pop().value == 80
    assert user.find(marker="task-assignee-2").elements.pop().value == "乙"


async def test_adding_a_team_updates_the_rate_of_people_already_in_the_crew(user: User) -> None:
    mount_dialog(Task("a", assignees=[Assignee("甲", 0.5), Assignee("丙", 1.0)]), members=teamed_members(), teams=[Team("開発", id="t1")])
    await user.open("/")
    user.find(marker="task-team-rate").elements.pop().set_value(100)
    user.find(marker="task-team-add").click()
    assert await wait_until(lambda: user.find(marker="task-allocation").elements.pop().value == 100)  # 甲 50 → 100
    assert user.find(marker="task-assignee-2").elements.pop().value == "丙"  # 既存の担当は残る
    assert user.find(marker="task-assignee-3").elements.pop().value == "乙"


async def test_a_bad_team_rate_notifies_and_changes_nothing(user: User) -> None:
    mount_dialog(None, members=teamed_members(), teams=[Team("開発", id="t1")])
    await user.open("/")
    user.find(marker="task-team-rate").elements.pop().set_value(0)
    user.find(marker="task-team-add").click()
    await user.should_see("割り当て率は 1〜100% で入力してください")
    assert user.find(marker="task-assignee").elements.pop().value in ("", None) or not user.find(marker="task-assignee").elements.pop().value


async def test_the_team_row_follows_the_assignee_fields_when_the_task_is_weekly(user: User) -> None:
    task = Task("a", assignees=[Assignee("甲", 1.0)], weekly_crew=[[Assignee("甲", 1.0)]])
    mount_dialog(task, members=teamed_members(), teams=[Team("開発", id="t1")])
    await user.open("/")
    assert not user.find(marker="task-team-add").elements.pop().visible
```

   担当の行のマーカーが `task-assignee`・`task-assignee-2`…、割り当て率が `task-allocation`・`task-allocation-2`… になることは `AssigneeFields._add_row`(`marker="task"` で `task-assignee{suffix}`・`task-allocation{suffix}`)から分かる。`task-assignee-remove` と取り違えないこと。

   `test_a_bad_team_rate_notifies_and_changes_nothing` の最後の `assert` は、ダイアログの空の担当行(値が空または `"__none__"` に当たる `NO_MEMBER`)に合わせて、実際の値の比較に直す(`NO_MEMBER` は `task_dialog.py` の定数)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -k "team" -q`
Expected: FAIL(`open_task_dialog() got an unexpected keyword argument 'teams'`)。

- [ ] **Step 3: `task_dialog.py` を実装する**

1. import に `Team` を足し(`from projectapp.models import (...)`)、`from projectapp.teams import add_team_members, team_member_names` を足す。
2. `open_task_dialog` の引数の `reference_choices: list[str] | None = None,` の次に `teams: list[Team] | None = None,` を足す。
3. `assignee_fields = AssigneeFields(...)` の直後(`weekly_note = ui.label(...)` の前)に足す。

```python
            team_choices = {t.id: t.name for t in teams or [] if team_member_names(raw_members, t.id)}
            with ui.row().classes("w-full items-center no-wrap gap-4") as team_box:
                team_select = ui.select(
                    team_choices, label="チームから追加", value=next(iter(team_choices), None)
                ).classes("flex-1").mark("task-team")
                team_rate = ui.number("割り当て率(%)", value=100, min=1, max=100, step=5).classes("flex-1")
                team_rate.mark("task-team-rate")

                def add_team() -> None:
                    rate = team_rate.value
                    if rate is None or not isfinite(rate) or not 1 <= rate <= 100:
                        ui.notify("割り当て率は 1〜100% で入力してください")
                        return
                    names = team_member_names(raw_members, team_select.value)
                    assignee_fields.set_assignees(add_team_members(assignee_fields.assignee_list(), names, rate / 100))

                ui.button("追加", icon="group_add", on_click=add_team).props("flat dense").mark("task-team-add")
            team_box.set_visibility(bool(team_choices))
```

   `isfinite` を `from math import isfinite` で import する(`task_dialog.py` に未 import なら足す)。
4. 1240 行付近の `assignee_fields.container.set_visibility(normal and not weekly)` の次に足す。

```python
            team_box.set_visibility(normal and not weekly and bool(team_choices))
```

   `team_choices` と `team_box` は、このダイアログ関数のスコープで定義されている(担当欄の節の中)。1240 行の処理が同じ関数の中にあることを確かめる。
5. `views.py` の `add_task`・`add_top_task`・`edit_task` の 3 つの `open_task_dialog(...)` 呼び出しに、`members=self.project.members,` の次の行として `teams=self.project.teams,` を足す。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py -q`
Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/task_dialog.py src/projectapp/views.py test/test_task_dialog.py
git commit -m "feat: タスクの担当欄に、チームのメンバーをまとめて加える行を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 仕様書・記録・全体の確認

**Files:**
- Modify: `CLAUDE.md`、`docs/development.md`、`docs/request-history.md`、`docs/superpowers/specs/2026-10-30-teams-design.md`
- Modify(git 管理外): `docs/hidden-requests.md`

- [ ] **Step 1: `CLAUDE.md` に段階 1 の仕様を足す**

次を入れる(既存の書き方に合わせて 1 項目 1 行)。

1. 「機能の詳細」の「ガントチャート」の、`メンバー`の項目(`メンバー`には`稼働日の上書き`…)の次に足す。

```
- `チーム`は、プロジェクトごとに名前(30 文字以内。タスク名と同じ文字の制限。同じ名前・空は不可)で登録する(`プロジェクト`メニューの`メンバーとパラメータ`の`チーム`タブ)。メンバーは複数のチームに所属でき(兼務)、チームごとに所属の割合(整数 1〜100%)を持つ。チームに入っているメンバーは、割合の合計をちょうど 100% にする(1 つだけなら 100%。チームなしも可)。メンバーの表の`チーム`列(チームが 1 つ以上あるときだけ)のボタンで、チェックと割合を入れる(2 つ以上のときだけ割合を出し、チェックを足し引きすると均等割りから始める)。チームの削除は、所属するメンバーがいるとき確認(人数)を出し、その所属を外して残りの割合を比を保って 100% に揃える(端数は最大の所属、同じなら先頭)。タスクにチームは記録しない。絞り込みと集計への利用は後続機能(要望 85 の段階 2・3)
- タスクの編集ダイアログの`担当`の節に、所属するメンバーがいるチームがあるときだけ`チームから追加`(チームの選択・割り当て率・`追加`)を出す。押すと、そのチームのメンバーを担当者として加える(いる人は割り当て率だけ更新する。その時点のメンバーを展開するだけで、あとでチームの名簿が変わってもタスクは変わらない)。週ごとの担当のタスクでは、担当の欄と一緒に隠す
```

2. 「ヘッダー」の`プロジェクト`メニューの記述にある「`閉じる`は変更のあるタブをパラメータ→メンバーの順に確定して閉じる」を「パラメータ→チーム→メンバーの順」に直し、「パラメータを適用すると、メンバーのタブの表の列を作り直す…」の文のあとに「チームを適用すると、メンバーのタブの未適用の行から、削除したチームへの所属を外す」を足し、「未適用の編集があるタブの見出しには`●`を出す」はそのまま。
3. 「データの保存先」の最初の項目の括弧に`チーム`を足す。
4. 「実装上の注意」の `version` の記述を「現在 17」にし、括弧の列挙の最後に「17 でプロジェクトの`teams`とメンバーの`teams`〔チームと所属〕を足した」を足す。
5. 「git のプルとマージ」の「3 者マージは項目ごとに行う」の文の、`タスク・メンバー・セクション・カテゴリ・イベントは`id`で` に`チーム`を足し、「メンバーの稼働日の上書きは…」の文のあとに「メンバーの所属(`teams`)はリスト全体を 1 項目として比べ、消えたチームへの所属は外して割合を 100% に揃えて通知する。同名で id の違うチームは、名前を変えて両方残す」を足す。
6. 「設定値のエクスポート・インポート」の先頭の項目の末尾に「チームとメンバーの所属は含めない」を足す。

- [ ] **Step 2: `docs/development.md` を直す**

モジュール表(`settings_io.py` の行の近く)に 2 行足す。

```
| `teams.py` | チーム(要望 85)。`team_name_error`・`membership_error`(整数 1〜100・合計 100)・`normalize`(比を保って 100 に揃える。端数は最大の所属)・`even_split`・`settle_memberships`・`membership_summary`・`team_member_names`・`drop_teams`・`TeamRow`/`build_teams`・`replace_teams`・`removal_impacts`・`add_team_members`。NiceGUI に依存しない |
| `teams_dialog.py` | `チーム`タブ(`teams_panel`)とメンバーの所属ダイアログ(`open_member_teams_dialog`)。`forms.py` から import されるので、`forms` を import しない |
```

ファイル形式の注意の節に足す。

```
- チーム(version 17、2026-10-30)は `Project.teams: list[Team]`(`id`・`name`)と `Member.teams: list[Membership]`(`team_id`・`percent`)。保存は `teams`(`id`・`name`)と `members[].teams`(`team_id`・`percent`)。読込(`storage._teams`・`_memberships`)は、チーム名の空・重複・長さ・制御文字、`id` の不正・重複、存在しないチーム・同じチームの重複・割合が整数 1〜100 でない(bool・小数も不可)・合計が 100 でない所属を拒否する。version 16 以下のファイルにある `teams` は無視する。`Team.id` は `compare=False`。マージは `kind="team"`(鍵は id)とメンバーの `teams`(リスト全体を 1 項目)。設定ファイルには出さない(`settings_io.build_settings` が所属を空にする)。段階 2・3(絞り込み・集計)は未実装。
```

- [ ] **Step 3: 記録を直す**

`docs/superpowers/specs/2026-10-30-teams-design.md` の状態を「**状態**: 設計(2026-10-30 に承認済み)。段階 1 の実装計画 [`plans/2026-10-30-teams-stage1.md`](../plans/2026-10-30-teams-stage1.md)。段階 2・3 の計画は未作成。」に直す。

`docs/request-history.md` の一覧に要望 85 の行を足す(完了は PR を作ってから直す)。80・81 の行の書式に合わせ、状態は「段階 1 実装中」、設計は`superpowers/specs/2026-10-30-teams-design.md`、計画は`superpowers/plans/2026-10-30-teams-stage1.md`、備考は「チーム。段階 2(絞り込み)・3(集計)は未着手。メンバーは兼務でき、所属の割合で按分する」とする。

`docs/hidden-requests.md`(git に入れない)に、要望 85 の行を足す(未着手の表の末尾)。

- [ ] **Step 4: 全体のテストと型を通す**

Run: `uv run pytest -q -x -n auto 2>&1 | tail -15`(約 4 分)
Expected: すべて PASS。失敗があれば、報告に名前を出して直す。

Run: `uv run ty check src`
Expected: エラーなし(既存の警告以外が出ないこと)。

- [ ] **Step 5: 実機で確かめる項目を整理する(コミットはしない)**

`uv run projectapp` で、次を手で確かめる。結果は報告に書く。

1. `プロジェクト`→`メンバーとパラメータ`→`チーム`タブでチームを 3 つ作り、適用しても閉じない。
2. メンバーの表の`チーム`列で、兼務(60/40)を入れて適用し、保存して開き直しても残る。
3. 兼務のメンバーが入ったチームを削除すると確認が出て、残りの割合が 100% に揃う。
4. タスクの編集ダイアログで`チームから追加`を押すと、メンバーが担当に入り、割り当て率が反映される。
5. `Ctrl/Cmd+Z` で、チームの追加・削除が元に戻る。

- [ ] **Step 6: コミット**

```bash
git add CLAUDE.md docs/development.md docs/request-history.md docs/superpowers/specs/2026-10-30-teams-design.md
git commit -m "docs: チーム(要望 85 段階 1)の仕様と開発者向けの記録を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
