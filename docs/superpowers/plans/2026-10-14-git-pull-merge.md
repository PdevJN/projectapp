# git のプルとマージ Implementation Plan

> **状態**: 実装済み — 要望 10 の 5 — マージ PR #16(2026-10-14)。設計書は [`2026-10-14-git-pull-merge-design.md`](../specs/2026-10-14-git-pull-merge-design.md)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Git メニューの「プル」で、相手の変更を fetch し、プロジェクトファイルを`id`によるタスク単位の 3 者マージで統合して、マージコミットまで作る。

**Architecture:** `merge.py`(Project の 3 者マージ。純粋関数)、`storage.py`(文字列からの読み書きを足す)、`gitops.py`(`fetch`・分岐の判定・`git merge --no-commit --no-ff`・上書き・コミット・中止)、`forms.py`(衝突ダイアログ)、`views.py`(メニュー・手順)。両側が変えたプロジェクトファイルだけをアプリが統合し、それ以外は git に任せる。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`asyncio_mode = "auto"`)、実際の`git`(テストは`tmp_path`の bare リモート)。

**Spec:** `docs/superpowers/specs/2026-10-14-git-pull-merge-design.md`

## Global Constraints

- 言語は日本語。UI の文言・コメント・コミットメッセージ・ドキュメントは日本語(識別子は英語)。
- Python 3.13 以上。描画は NiceGUI と CSS による自前描画。
- `merge.py`は NiceGUI にも git にも依存しない(`models`・`storage`だけに依存する)。
- ファイル形式(`version: 3`)は変えない。保存は一時ファイル経由。
- 例外は`gitops`の外へ出さず、`GitResult`の`message`に理由を入れる。マージ中の失敗は`git merge --abort`で戻す。
- テストの実行は`uv run pytest -n auto`、型は`uv run ty check src`。テストは`test/`にあり、同じフォルダの別のテストを`from test_storage import ...`の形で読み込む。
- コミットメッセージは`feat:`・`test:`・`docs:`・`fix:`で始め、末尾に次の行を付ける:
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- 実装は`develop`から切った作業ブランチ`feature/git-pull-merge`で行う(`git switch -c feature/git-pull-merge`)。

## 設計書からの調整(この計画で決めたこと)

設計書を次のとおり読み替える(Task 9 で設計書も直す):

- `apply_choices`は作らず、`merge_projects(base, ours, theirs, choices=None)`に選択を渡して、もう一度マージする(純粋関数なので安い)。選択がない衝突は「自分」になる。
- 衝突の選択の鍵は`Conflict.id = (kind, key, field)`。ファイルをまたぐ衝突の混同を避けるため、衝突はファイルごとに順に出して選ばせる。
- 削除と変更の衝突の選択は、「自分」「相手」のどちらの版を採るか(削除した側を選べば削除)。画面では「削除する」「残す」の文言を添える。
- 並びの追加分は、「相手」側の直前の兄弟(結果にすでにあるもの)のあとに入れる。片側だけが並べ替えたときは、その並べ替えを採る。
- 完了通知は「取り込みました」に、選んだ衝突の件数だけ添える(自動で統合した項目の件数は数えない)。
- ファイル単位の衝突(片側が削除・両側が新規作成)は、自動では統合せず、中止して理由を出す。

## Review Focus

- 担当者のメンバーを片側が改名し、もう片側が別のタスクの担当に使っている: 名前が新しい名前にそろう(Task 3)
- 片側が削除したセクションに、もう片側がタスクを足している: タスクは消えず、ルートへ移り、通知に出る(Task 3)
- 同じ名前のメンバーを両側が別々に追加した: 落ちずに、両方が残る(Task 3)
- 相手がファイルを削除・新規作成している(ファイル単位の衝突)/プロジェクトファイル以外に衝突がある: 中止して元に戻り、`MERGE_HEAD`が残らない(Task 4)
- 認証や`user.name`の不足でマージコミットが失敗する: 中止して元に戻り、理由が出る(Task 4)
- ダイアログを ESC で閉じる: 中止と同じ(取り込まれず、`merge --abort`される)(Task 5・6)

---

### Task 1: storage に、文字列からの読み書きを足す

**Files:**
- Modify: `src/projectapp/storage.py`(`save_project`・`load_project`)
- Test: `test/test_storage.py`

**Interfaces:**
- Produces: `dumps_project(project: Project) -> str`(ファイルに書く JSON 文字列。id の重複は`ValueError`)、`parse_project(text: str, name: str) -> Project`(`load_project`と同じ検証。不正は`ValueError`・`KeyError`・`json.JSONDecodeError`)。`save_project`・`load_project`の挙動は変えない。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_storage.py`の末尾に足す。`Project`・`Task`・`Member`・`Assignee`・`Section`・`date`は、このファイルの先頭ですでに import されているか、必要なものを足す)

```python
def test_dumps_and_parse_round_trip(tmp_path: Path) -> None:
    from projectapp.storage import dumps_project, parse_project

    alice = Member("甲", 1.0)
    task = Task("調査", assignees=[Assignee("甲", 0.5)])
    project = Project("文字列", date(2026, 10, 1), members=[alice], sections=[Section("A", tasks=[task])])
    text = dumps_project(project)
    loaded = parse_project(text, "文字列")
    assert loaded == project
    assert loaded.sections[0].tasks[0].id == task.id
    save_project(project, tmp_path)
    assert (tmp_path / "文字列.json").read_text(encoding="utf-8") == text


def test_dumps_rejects_duplicate_ids() -> None:
    from projectapp.storage import dumps_project

    one = Task("a", id="same")
    two = Task("b", id="same")
    with pytest.raises(ValueError):
        dumps_project(Project("p", date(2026, 10, 1), tasks=[one, two]))
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `uv run pytest test/test_storage.py -k "dumps" -v`
Expected: FAIL(`ImportError: cannot import name 'dumps_project'`)

- [ ] **Step 3: 実装する**(`src/projectapp/storage.py`)

`save_project`の中の 2 行
```python
    _check_unique_ids(project)
    data = json.dumps(_dump(project), ensure_ascii=False, indent=2, default=_encode)
```
を、次の関数に切り出し、`save_project`では`data = dumps_project(project)`にする(`validate_name`の検査は、`save_project`に残す)。

```python
def dumps_project(project: Project) -> str:
    """ファイルに書く JSON 文字列。id が重複していれば`ValueError`(読めないファイルを作らない)。"""
    _check_unique_ids(project)
    return json.dumps(_dump(project), ensure_ascii=False, indent=2, default=_encode)
```

`load_project`を、文字列を受ける`parse_project`と、ファイルを読む薄い関数に分ける。`load_project`の本体(`raw = json.loads(...)`から`return project`まで)を`parse_project(text: str, name: str)`に移し、`json.loads(path.read_text(...))`を`json.loads(text)`に、`name=path.stem`を`name=name`にする。

```python
def load_project(path: Path) -> Project:
    return parse_project(path.read_text(encoding="utf-8"), path.stem)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_storage.py -v`
Expected: すべて PASS

- [ ] **Step 5: コミット**

```bash
git switch -c feature/git-pull-merge
git add src/projectapp/storage.py test/test_storage.py
git commit -m "feat: プロジェクトを文字列で読み書きできるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: merge.py の土台 — 記録のマージと、メンバー・カテゴリ・パラメータ・テンプレート・設定

**Files:**
- Create: `src/projectapp/merge.py`
- Test: `test/test_merge.py`

**Interfaces:**
- Produces(この Task で作り、Task 3 が広げる):
  - `OURS = "ours"`、`THEIRS = "theirs"`、`DELETED = "(削除)"`(削除と変更の衝突の`field`)
  - `Choices = dict[tuple[str, str, str], str]`(`Conflict.id` → `OURS`/`THEIRS`)
  - `Conflict`(`kind: str`・`key: str`・`label: str`・`field: str`・`ours: Any`・`theirs: Any`、プロパティ`id -> tuple[str, str, str]`)。`kind`は`task`・`section`・`member`・`category`・`parameter`・`url_template`・`setting`
  - `MergeResult(project: Project, conflicts: list[Conflict], notes: list[str])`
  - `merge_projects(base: Project, ours: Project, theirs: Project, choices: Choices | None = None) -> MergeResult`
  - `format_value(value: object) -> str`
  - 内部: `_Merger.record(...)`・`_Merger.collection(...)`・`_order(base, ours, theirs)`

- [ ] **Step 1: 失敗するテストを書く**(`test/test_merge.py`を新規作成)

```python
from datetime import date, time

import pytest

from projectapp.merge import DELETED, OURS, THEIRS, Conflict, merge_projects
from projectapp.models import ActualMode, Category, Level, Member, Parameter, Project, UrlTemplate


def proj(**kw) -> Project:
    return Project(name="p", base_date=date(2026, 10, 1), **kw)


def test_unchanged_projects_merge_to_the_same() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    result = merge_projects(base, base, base)
    assert result.conflicts == [] and result.notes == []
    assert result.project == base


def test_settings_take_each_sides_change() -> None:
    base = proj()
    ours = proj(daily_hours=7.0)
    theirs = proj(work_start=time(10, 0))
    merged = merge_projects(base, ours, theirs).project
    assert merged.daily_hours == 7.0 and merged.work_start == time(10, 0)


def test_settings_conflict_defaults_to_ours_and_follows_choices() -> None:
    base, ours, theirs = proj(), proj(daily_hours=7.0), proj(daily_hours=5.0)
    result = merge_projects(base, ours, theirs)
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.kind == "setting" and conflict.ours == 7.0 and conflict.theirs == 5.0
    assert result.project.daily_hours == 7.0
    chosen = merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project
    assert chosen.daily_hours == 5.0


def test_same_value_on_both_sides_is_not_a_conflict() -> None:
    base, ours, theirs = proj(), proj(daily_hours=7.0), proj(daily_hours=7.0)
    assert merge_projects(base, ours, theirs).conflicts == []


def test_actual_mode_merges() -> None:
    merged = merge_projects(proj(), proj(actual_mode=ActualMode.INTERVALS), proj()).project
    assert merged.actual_mode is ActualMode.INTERVALS


def test_members_merge_by_id_field_by_field() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2")])
    ours = proj(members=[Member("甲", 1.2, id="m1"), Member("乙", 1.0, id="m2")])  # 比率を変えた
    theirs = proj(members=[Member("甲改", 1.0, id="m1"), Member("乙", 1.0, id="m2"), Member("丙", 0.8, id="m3")])
    merged = merge_projects(base, ours, theirs).project
    assert [(m.id, m.name, m.ratio) for m in merged.members] == [("m1", "甲改", 1.2), ("m2", "乙", 1.0), ("m3", "丙", 0.8)]


def test_member_deleted_on_one_side_and_unchanged_on_the_other_is_deleted() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1"), Member("乙", 1.0, id="m2")])
    theirs = proj(members=[Member("甲", 1.0, id="m1")])
    merged = merge_projects(base, base, theirs)
    assert [m.id for m in merged.project.members] == ["m1"] and merged.conflicts == []


def test_delete_versus_change_is_a_conflict_with_both_choices() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")])
    ours = proj(members=[])  # 自分が削除
    theirs = proj(members=[Member("甲", 0.5, id="m1")])  # 相手が変更
    result = merge_projects(base, ours, theirs)
    (conflict,) = result.conflicts
    assert conflict.field == DELETED and conflict.ours is None and conflict.theirs is not None
    assert result.project.members == []  # 既定は自分
    kept = merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project
    assert [(m.id, m.ratio) for m in kept.members] == [("m1", 0.5)]


def test_same_name_members_added_on_both_sides_both_stay() -> None:
    base = proj()
    ours = proj(members=[Member("丁", 1.0, id="a1")])
    theirs = proj(members=[Member("丁", 1.0, id="b1")])
    merged = merge_projects(base, ours, theirs).project
    assert {m.id for m in merged.members} == {"a1", "b1"}


def test_categories_merge_by_id() -> None:
    base = proj(categories=[Category("開発", id="c1")])
    ours = proj(categories=[Category("開発", color="red", id="c1")])
    theirs = proj(categories=[Category("開発", prj_code="PRJ-1", id="c1"), Category("保守", id="c2")])
    merged = merge_projects(base, ours, theirs).project
    assert [(c.id, c.color, c.prj_code) for c in merged.categories] == [("c1", "red", "PRJ-1"), ("c2", "blue", "")]


def test_parameters_and_url_templates_merge_by_name() -> None:
    p1 = Parameter("経験", [Level("低", -0.1), Level("高", 0.2)])
    base = proj(parameters=[p1], url_templates=[UrlTemplate("チケット", "https://e.com/{ID}")])
    ours = proj(parameters=[Parameter("経験", [Level("低", -0.1), Level("高", 0.3)])], url_templates=base.url_templates)
    theirs = proj(parameters=[p1, Parameter("言語", [Level("日", 0.0)])], url_templates=[UrlTemplate("チケット", "https://e.com/t/{ID}")])
    merged = merge_projects(base, ours, theirs).project
    assert [p.name for p in merged.parameters] == ["経験", "言語"]
    assert merged.parameters[0].levels[1].value == 0.3
    assert merged.url_templates[0].pattern == "https://e.com/t/{ID}"


def test_added_items_follow_the_theirs_predecessor_and_one_sided_reorders_win() -> None:
    a, b, c = (Member(n, 1.0, id=n) for n in "abc")
    base = proj(members=[a, b, c])
    theirs = proj(members=[c, a, b])  # 相手だけが並べ替えた
    assert [m.id for m in merge_projects(base, base, theirs).project.members] == ["c", "a", "b"]
    d = Member("d", 1.0, id="d")
    theirs = proj(members=[a, d, b, c])  # 相手が a の次に追加
    ours = proj(members=[b, a, c])  # 自分が並べ替えた
    assert [m.id for m in merge_projects(base, ours, theirs).project.members] == ["b", "a", "d", "c"]


@pytest.mark.parametrize(
    ("value", "text"),
    [(None, "(削除)"), (True, "はい"), (3, "3"), ([], "(なし)"), (["a", "b"], "a, b")],
)
def test_format_value(value: object, text: str) -> None:
    from projectapp.merge import format_value

    assert format_value(value) == text
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `uv run pytest test/test_merge.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.merge`)

- [ ] **Step 3: 実装する**(`src/projectapp/merge.py`を新規作成)

```python
"""プロジェクトの 3 者マージ(共通祖先・自分・相手)。NiceGUI にも git にも依存しない。

タスク・メンバー・セクション・カテゴリは`id`で、パラメータ・URL テンプレートは名前で突き合わせる。
項目ごとに、片側だけが変えた値を採り、両側が違う値に変えた項目だけを衝突にする。
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from projectapp.models import (
    Category,
    Level,
    Member,
    Parameter,
    Project,
    UrlTemplate,
)

OURS = "ours"
THEIRS = "theirs"
DELETED = "(削除)"  # 削除と変更の衝突の項目名
Choices = dict[tuple[str, str, str], str]
Record = dict[str, Any]
_MISSING = object()


@dataclass(frozen=True, eq=False)
class Conflict:
    kind: str  # task・section・member・category・parameter・url_template・setting
    key: str  # id(パラメータ・テンプレートは名前)
    label: str  # 画面に出す名前
    field: str  # 画面に出す項目名。削除と変更の衝突は`DELETED`
    ours: Any  # 自分の値。自分が削除したときは None
    theirs: Any  # 相手の値。相手が削除したときは None

    @property
    def id(self) -> tuple[str, str, str]:
        return (self.kind, self.key, self.field)


@dataclass
class MergeResult:
    project: Project
    conflicts: list[Conflict]  # 選択がなかった衝突も含む(結果は「自分」になっている)
    notes: list[str]  # 利用者に知らせる整理(外した担当者など)


def format_value(value: object) -> str:
    """衝突ダイアログに出す値の文言。"""
    if value is None:
        return DELETED
    if isinstance(value, bool):
        return "はい" if value else "いいえ"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(v) for v in value) or "(なし)"
    if isinstance(value, dict):
        return ", ".join(f"{k}={format_value(v)}" for k, v in value.items()) or "(なし)"
    if value == "":
        return "(空)"
    return str(value)


def _order(base: list[str], ours: list[str], theirs: list[str]) -> list[str]:
    """3 者の並びを合わせる。自分の並びが土台。相手だけが並べ替えたときは相手の並びが土台。
    土台にないもの(相手の追加・移動)は、相手の並びでの直前の兄弟(結果にすでにあるもの)のあとに入れる。"""
    members = set(ours) | set(theirs)
    common = set(base) & set(ours) & set(theirs)

    def restrict(seq: list[str]) -> list[str]:
        return [x for x in seq if x in common]

    primary, secondary = ours, theirs
    if restrict(ours) == restrict(base) and restrict(theirs) != restrict(base):
        primary, secondary = theirs, ours
    result = [x for x in primary if x in members]
    for index, item in enumerate(secondary):
        if item in result:
            continue
        position = 0
        for earlier in reversed(secondary[:index]):
            if earlier in result:
                position = result.index(earlier) + 1
                break
        result.insert(position, item)
    return result


class _Merger:
    def __init__(self, choices: Choices | None) -> None:
        self.choices = choices or {}
        self.conflicts: list[Conflict] = []

    def pick(self, conflict: Conflict) -> str:
        self.conflicts.append(conflict)
        return self.choices.get(conflict.id, OURS)

    def record(
        self,
        kind: str,
        key: str,
        labels: dict[str, str],
        base: Record | None,
        ours: Record | None,
        theirs: Record | None,
        display: Callable[[str, Any], Any] = lambda name, value: value,
    ) -> Record | None:
        """1 件の記録を 3 者マージする。`None`は存在しないこと。結果が`None`なら削除。"""
        if ours is None and theirs is None:
            return None
        label = str((ours or theirs or base or {}).get("name", key))
        if base is None:
            if ours is None:
                return theirs
            if theirs is None:
                return ours
            base = {}  # 両側が追加した: 値の違う項目だけが衝突になる
        elif ours is None or theirs is None:
            kept = theirs if ours is None else ours
            if kept == base:
                return None  # 片側が削除し、もう片側は変えていない
            conflict = Conflict(kind, key, label, DELETED, ours, theirs)
            return ours if self.pick(conflict) == OURS else theirs
        assert ours is not None and theirs is not None
        merged: Record = {}
        for name in ours:
            b, o, t = base.get(name, _MISSING), ours[name], theirs[name]
            if o == t:
                merged[name] = o
            elif b == o:
                merged[name] = t
            elif b == t:
                merged[name] = o
            else:
                conflict = Conflict(kind, key, label, labels.get(name, name), display(name, o), display(name, t))
                merged[name] = o if self.pick(conflict) == OURS else t
        return merged

    def collection(
        self,
        kind: str,
        labels: dict[str, str],
        base: dict[str, Record],
        ours: dict[str, Record],
        theirs: dict[str, Record],
        display: Callable[[str, Any], Any] = lambda name, value: value,
    ) -> dict[str, Record]:
        """キーごとに記録をマージする。並びは`_order`。"""
        result: dict[str, Record] = {}
        for key in _order(list(base), list(ours), list(theirs)):
            merged = self.record(kind, key, labels, base.get(key), ours.get(key), theirs.get(key), display)
            if merged is not None:
                result[key] = merged
        return result


MEMBER_LABELS = {"name": "名前", "ratio": "基本比率", "levels": "段階の選択"}
CATEGORY_LABELS = {"name": "名前", "kind": "種別", "expiry_date": "有効期限", "color": "色", "prj_code": "PRJコード"}
PARAMETER_LABELS = {"levels": "段階"}
TEMPLATE_LABELS = {"pattern": "URLの型"}
SETTING_LABELS = {"base_date": "基準日", "daily_hours": "稼働可能時間", "work_start": "始業時刻", "actual_mode": "実績の記録方式"}


def _members(project: Project) -> dict[str, Record]:
    return {m.id: {"name": m.name, "ratio": m.ratio, "levels": dict(m.levels)} for m in project.members}


def _categories(project: Project) -> dict[str, Record]:
    return {
        c.id: {"name": c.name, "kind": c.kind, "expiry_date": c.expiry_date, "color": c.color, "prj_code": c.prj_code}
        for c in project.categories
    }


def _parameters(project: Project) -> dict[str, Record]:
    return {p.name: {"levels": [(lv.name, lv.value) for lv in p.levels]} for p in project.parameters}


def _templates(project: Project) -> dict[str, Record]:
    return {t.name: {"pattern": t.pattern} for t in project.url_templates}


def _settings(project: Project) -> Record:
    return {name: getattr(project, name) for name in SETTING_LABELS}


def merge_projects(base: Project, ours: Project, theirs: Project, choices: Choices | None = None) -> MergeResult:
    """共通祖先`base`・自分`ours`・相手`theirs`を統合する。選択のない衝突は「自分」になり、`conflicts`に残る。"""
    merger = _Merger(choices)
    notes: list[str] = []
    settings = merger.record(
        "setting", "設定", SETTING_LABELS, _settings(base), _settings(ours), _settings(theirs)
    )
    assert settings is not None
    members = merger.collection("member", MEMBER_LABELS, _members(base), _members(ours), _members(theirs))
    categories = merger.collection("category", CATEGORY_LABELS, _categories(base), _categories(ours), _categories(theirs))
    parameters = merger.collection("parameter", PARAMETER_LABELS, _parameters(base), _parameters(ours), _parameters(theirs))
    templates = merger.collection("url_template", TEMPLATE_LABELS, _templates(base), _templates(ours), _templates(theirs))
    project = Project(
        name=ours.name,
        base_date=settings["base_date"],
        daily_hours=settings["daily_hours"],
        work_start=settings["work_start"],
        actual_mode=settings["actual_mode"],
        members=[Member(r["name"], r["ratio"], dict(r["levels"]), id=key) for key, r in members.items()],
        categories=[
            Category(r["name"], r["kind"], r["expiry_date"], r["color"], r["prj_code"], id=key)
            for key, r in categories.items()
        ],
        parameters=[Parameter(key, [Level(n, v) for n, v in r["levels"]]) for key, r in parameters.items()],
        url_templates=[UrlTemplate(key, r["pattern"]) for key, r in templates.items()],
    )
    return MergeResult(copy.deepcopy(project), merger.conflicts, notes)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_merge.py -v`
Expected: すべて PASS(`Conflict.field`は日本語の項目名なので、設定の衝突の`id`は`("setting", "設定", "稼働可能時間")`になる)。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/merge.py test/test_merge.py
git commit -m "feat: プロジェクトの設定・メンバー・カテゴリなどを 3 者マージする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: merge.py — セクションとタスクのマージ、整合、ファイルの文字列のマージ

**Files:**
- Modify: `src/projectapp/merge.py`
- Test: `test/test_merge.py`

**Interfaces:**
- Consumes: Task 2 の`_Merger`・`_order`・`merge_projects`、Task 1 の`dumps_project`・`parse_project`。
- Produces:
  - `merge_projects`が、`sections`・`tasks`もマージする(下記の規則)。
  - `FileMerge(text: str, conflicts: list[Conflict], notes: list[str])`
  - `merge_files(name: str, base: str, ours: str, theirs: str, choices: Choices | None = None) -> FileMerge`(`name`は`甲.json`。`parse_project`で読み、`merge_projects`のあと、`dumps_project`で書き、`parse_project`で読み直して検証する。不正は`ValueError`)

規則(設計書の再掲と、この計画での具体化):
- タスクの記録: `Task`の`id`以外のすべての項目、`assignees`は`[(メンバーid, 割り当て率)]`、`parent`はセクション`id`か`None`(ルート)。
- セクションの記録: `name`と`parent`。
- 担当者は、各プロジェクトの`members`で名前→`id`にして比べ、結果は結果のメンバーの名前に戻す。結果のメンバーにいない`id`は外し、`notes`に`担当者を外しました: 〈タスク名〉の〈id〉`の形で残す。
- 結果のセクションにない親を持つタスク・セクションは、ルートへ移し、`notes`に`削除されたセクションにあった〈名前〉をルートへ移しました`を残す。
- 先行は、結果にないタスクの`id`を外す(通知しない)。カテゴリは、結果にないカテゴリ`id`を`None`にし、`notes`に`カテゴリを外しました: 〈タスク名〉`を残す。
- 各入れ物(ルート・セクション)のタスクとセクションの並びは`_order`。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_merge.py`に足す。先頭の import に`Assignee, Priority, Section, Task`を足す。`merge_files`・`dumps_project`・`parse_project`は各テストの中で import している)

```python
def task(name: str, id: str, **kw) -> Task:
    return Task(name, id=id, **kw)


def names_of(project: Project) -> list[str]:
    return [t.name for t in project.all_tasks()]


def test_tasks_merge_field_by_field() -> None:
    base = proj(tasks=[task("調査", "t1", effort_hours=4.0)])
    ours = proj(tasks=[task("調査", "t1", effort_hours=8.0)])
    theirs = proj(tasks=[task("調査(改)", "t1", effort_hours=4.0)])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert (merged.project.tasks[0].name, merged.project.tasks[0].effort_hours) == ("調査(改)", 8.0)
    assert merged.project.tasks[0].id == "t1"


def test_same_field_changed_differently_is_a_conflict() -> None:
    base = proj(tasks=[task("a", "t1", effort_hours=4.0)])
    ours = proj(tasks=[task("a", "t1", effort_hours=8.0)])
    theirs = proj(tasks=[task("a", "t1", effort_hours=2.0)])
    result = merge_projects(base, ours, theirs)
    (conflict,) = result.conflicts
    assert (conflict.kind, conflict.key, conflict.field, conflict.ours, conflict.theirs) == ("task", "t1", "工数", 8.0, 2.0)
    assert result.project.tasks[0].effort_hours == 8.0
    assert merge_projects(base, ours, theirs, {conflict.id: THEIRS}).project.tasks[0].effort_hours == 2.0


def test_added_task_goes_after_its_predecessor_sibling() -> None:
    base = proj(tasks=[task("a", "t1"), task("b", "t2")])
    theirs = proj(tasks=[task("a", "t1"), task("new", "t3"), task("b", "t2")])
    ours = proj(tasks=[task("a", "t1", effort_hours=1.0), task("b", "t2")])
    assert names_of(merge_projects(base, ours, theirs).project) == ["a", "new", "b"]


def test_task_deleted_by_one_side_and_unchanged_by_the_other() -> None:
    base = proj(tasks=[task("a", "t1"), task("b", "t2")])
    theirs = proj(tasks=[task("b", "t2")])
    merged = merge_projects(base, base, theirs)
    assert names_of(merged.project) == ["b"] and merged.conflicts == []


def test_task_deleted_by_theirs_and_changed_by_ours_is_a_conflict() -> None:
    base = proj(tasks=[task("a", "t1")])
    ours = proj(tasks=[task("a", "t1", effort_hours=3.0)])
    result = merge_projects(base, ours, proj())
    (conflict,) = result.conflicts
    assert conflict.field == DELETED and conflict.theirs is None
    assert names_of(result.project) == ["a"]  # 既定は自分
    assert names_of(merge_projects(base, ours, proj(), {conflict.id: THEIRS}).project) == []


def test_task_moved_into_a_section_by_theirs() -> None:
    base = proj(sections=[Section("S", id="s1")], tasks=[task("a", "t1")])
    ours = proj(sections=[Section("S", id="s1")], tasks=[task("a", "t1", effort_hours=2.0)])
    theirs = proj(sections=[Section("S", tasks=[task("a", "t1")], id="s1")])
    merged = merge_projects(base, ours, theirs).project
    assert merged.tasks == [] and [t.name for t in merged.sections[0].tasks] == ["a"]
    assert merged.sections[0].tasks[0].effort_hours == 2.0


def test_sections_merge_and_keep_subsections() -> None:
    sub = Section("子", tasks=[task("x", "t9")], id="s2")
    base = proj(sections=[Section("親", sections=[sub], id="s1")])
    theirs = proj(sections=[Section("親改", sections=[sub], id="s1")])
    ours = proj(sections=[Section("親", sections=[Section("子", tasks=[task("x", "t9"), task("y", "t10")], id="s2")], id="s1")])
    merged = merge_projects(base, ours, theirs).project
    assert merged.sections[0].name == "親改"
    assert [t.name for t in merged.sections[0].sections[0].tasks] == ["x", "y"]


def test_predecessors_pointing_to_deleted_tasks_are_dropped() -> None:
    base = proj(tasks=[task("a", "t1"), task("b", "t2", predecessors=["t1"])])
    theirs = proj(tasks=[task("b", "t2", predecessors=["t1"])])
    merged = merge_projects(base, base, theirs).project
    assert merged.tasks[0].predecessors == []


def test_member_renamed_by_theirs_renames_the_assignees_of_ours_tasks() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 0.5)])])
    ours = proj(
        members=[Member("甲", 1.0, id="m1")],
        tasks=[task("a", "t1", assignees=[Assignee("甲", 0.5)]), task("b", "t2", assignees=[Assignee("甲", 1.0)])],
    )
    theirs = proj(members=[Member("甲改", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲改", 0.5)])])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == []
    assert [(t.name, [a.name for a in t.assignees]) for t in merged.project.tasks] == [("a", ["甲改"]), ("b", ["甲改"])]


def test_assignee_of_a_deleted_member_is_dropped_with_a_note() -> None:
    base = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1")])
    ours = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)])])
    theirs = proj(members=[], tasks=[task("a", "t1")])  # メンバーの記録は自分が変えていないので、衝突なしで削除される
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == [] and merged.project.members == []
    assert merged.project.tasks[0].assignees == []
    assert any("担当者を外しました" in n and "a" in n for n in merged.notes)


def test_tasks_of_a_deleted_section_move_to_the_root_with_a_note() -> None:
    base = proj(sections=[Section("S", id="s1")])
    ours = proj(sections=[])  # 自分が(変更のない)セクションを削除
    theirs = proj(sections=[Section("S", tasks=[task("new", "t1")], id="s1")])
    merged = merge_projects(base, ours, theirs)
    assert [t.name for t in merged.project.tasks] == ["new"] and merged.project.sections == []
    assert any("ルートへ移しました" in n for n in merged.notes)


def test_category_removed_by_theirs_unsets_ours_tasks() -> None:
    base = proj(categories=[Category("開発", id="c1")], tasks=[task("a", "t1")])
    ours = proj(categories=[Category("開発", id="c1")], tasks=[task("a", "t1", category_id="c1")])
    theirs = proj(categories=[], tasks=[task("a", "t1")])
    merged = merge_projects(base, ours, theirs)
    assert merged.conflicts == [] and merged.project.categories == []
    assert merged.project.tasks[0].category_id is None
    assert any("カテゴリを外しました" in n for n in merged.notes)


def test_merge_files_round_trips_through_text() -> None:
    from projectapp.merge import merge_files
    from projectapp.storage import dumps_project, parse_project

    base = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)], effort_hours=4.0)])
    ours = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)], effort_hours=8.0)])
    theirs = proj(members=[Member("甲", 1.0, id="m1")], tasks=[task("a", "t1", assignees=[Assignee("甲", 1.0)], priority=Priority.HIGH)])
    result = merge_files("p.json", dumps_project(base), dumps_project(ours), dumps_project(theirs))
    assert result.conflicts == []
    merged = parse_project(result.text, "p")
    assert merged.tasks[0].effort_hours == 8.0 and merged.tasks[0].priority.value == "高"


def test_merge_files_rejects_unreadable_text() -> None:
    from projectapp.merge import merge_files

    with pytest.raises(ValueError):
        merge_files("p.json", "{", "{", "{")
```


- [ ] **Step 2: 落ちることを確かめる**

Run: `uv run pytest test/test_merge.py -v`
Expected: 新しいテストが FAIL

- [ ] **Step 3: 実装する**(`src/projectapp/merge.py`)

import に`Assignee, Section, Task`と、`from dataclasses import fields`、`from projectapp.storage import dumps_project, parse_project`を足す。

```python
TASK_LABELS = {
    "name": "名前", "planned_start": "開始予定", "effort_hours": "工数", "priority": "優先度", "status": "状態",
    "color": "色", "assignees": "担当", "predecessors": "先行", "deadline": "締切", "planned_end": "完了予定",
    "planned_end_manual": "完了予定を手で指定", "actuals": "実績", "category_id": "カテゴリ", "kind": "種別",
    "urls": "リンク", "parent": "所属",
}
SECTION_LABELS = {"name": "名前", "parent": "所属"}


@dataclass
class _Flat:
    """プロジェクトのタスクとセクションを、id ごとの記録と、入れ物(ルート = None)ごとの並びにほどいたもの。"""

    tasks: dict[str, Record]
    sections: dict[str, Record]
    task_order: dict[str | None, list[str]]
    section_order: dict[str | None, list[str]]


def _flatten(project: Project) -> _Flat:
    ids = {}
    for member in project.members:
        ids.setdefault(member.name, member.id)  # 同名は最初の 1 件(保存・読込と同じ)
    flat = _Flat({}, {}, {}, {})

    def visit(container: str | None, tasks: list[Task], sections: list[Section]) -> None:
        flat.task_order[container] = [t.id for t in tasks]
        flat.section_order[container] = [s.id for s in sections]
        for t in tasks:
            record: Record = {f.name: getattr(t, f.name) for f in fields(Task) if f.name not in ("id", "assignees")}
            record["assignees"] = [(ids.get(a.name, a.name), a.allocation) for a in t.assignees]
            record["parent"] = container
            flat.tasks[t.id] = record
        for s in sections:
            flat.sections[s.id] = {"name": s.name, "parent": container}
            visit(s.id, s.tasks, s.sections)

    visit(None, project.tasks, project.sections)
    return flat


def _member_names(*projects: Project) -> dict[str, str]:
    names: dict[str, str] = {}
    for project in projects:  # 先のものを優先する
        for member in project.members:
            names.setdefault(member.id, member.name)
    return names
```

`merge_projects`の末尾(`project = Project(...)`の前)に、セクションとタスクのマージを足し、`Project`に`tasks`・`sections`を渡す。

```python
    flats = [_flatten(p) for p in (base, ours, theirs)]
    shown = _member_names(ours, theirs, base)

    def display(name: str, value: Any) -> Any:
        if name == "assignees":
            return [f"{shown.get(i, i)} {a:.0%}" for i, a in value]
        return value

    sections = merger.collection("section", SECTION_LABELS, *(f.sections for f in flats))
    tasks = merger.collection("task", TASK_LABELS, *(f.tasks for f in flats), display=display)
    names = {key: r["name"] for key, r in members.items()}

    for key, record in sections.items():  # 親が消えたセクションは、ルートへ移す
        if record["parent"] is not None and record["parent"] not in sections:
            notes.append(f"削除されたセクションにあった「{record['name']}」をルートへ移しました")
            record["parent"] = None
    for key, record in tasks.items():
        if record["parent"] is not None and record["parent"] not in sections:
            notes.append(f"削除されたセクションにあった「{record['name']}」をルートへ移しました")
            record["parent"] = None

    def make_task(key: str, record: Record) -> Task:
        assignees = []
        for member_id, allocation in record["assignees"]:
            if member_id in names:
                assignees.append(Assignee(names[member_id], allocation))
            else:
                notes.append(f"担当者を外しました: 「{record['name']}」の{shown.get(member_id, member_id)}")
        data = {k: v for k, v in record.items() if k not in ("assignees", "parent", "predecessors", "category_id")}
        category = record["category_id"]
        if category is not None and category not in categories:
            notes.append(f"カテゴリを外しました: 「{record['name']}」")
            category = None
        predecessors = [p for p in record["predecessors"] if p in tasks]
        return Task(id=key, assignees=assignees, predecessors=predecessors, category_id=category, **data)

    task_objects = {key: make_task(key, record) for key, record in tasks.items()}

    task_orders = [f.task_order for f in flats]  # base, ours, theirs の順
    section_orders = [f.section_order for f in flats]

    def children(orders: list[dict[str | None, list[str]]], records: dict[str, Record], container: str | None) -> list[str]:
        wanted = [k for k, r in records.items() if r["parent"] == container]
        base_o, ours_o, theirs_o = (o.get(container, []) for o in orders)
        ordered = [k for k in _order(base_o, ours_o, theirs_o) if k in wanted]
        return ordered + [k for k in wanted if k not in ordered]

    def build(container: str | None) -> tuple[list[Task], list[Section]]:
        built = []
        for sid in children(section_orders, sections, container):
            section = Section(sections[sid]["name"], id=sid)
            section.tasks, section.sections = build(sid)
            built.append(section)
        return [task_objects[k] for k in children(task_orders, tasks, container)], built

    root_tasks, root_sections = build(None)
```

`Project(...)`の組み立てに`tasks=root_tasks, sections=root_sections`を足す。ただし`Project(...)`は、上の`make_task`・`build`より後(`categories`・`members`の辞書が出そろったあと)で作る。`make_task`が参照する`categories`は、Task 2 の`categories = merger.collection(...)`(カテゴリ id → 記録の辞書)である。

ファイル全体の最後に`merge_files`を足す。

```python
@dataclass(frozen=True)
class FileMerge:
    text: str
    conflicts: list[Conflict]
    notes: list[str]


def merge_files(name: str, base: str, ours: str, theirs: str, choices: Choices | None = None) -> FileMerge:
    """プロジェクトファイル 1 つの、3 者の本文を統合する。読めない・統合結果が検証を通らないときは`ValueError`。"""
    stem = name.removesuffix(".json")
    try:
        projects = [parse_project(text, stem) for text in (base, ours, theirs)]
    except KeyError as exc:  # 読込は、キーの欠けを KeyError で知らせる
        raise ValueError(f"キーがありません: {exc}") from exc
    result = merge_projects(*projects, choices)
    text = dumps_project(result.project)
    parse_project(text, stem)  # 書いたものを読み直せること
    return FileMerge(text, result.conflicts, result.notes)
```

`json.JSONDecodeError`は`ValueError`の子なので、そのまま`ValueError`として出る。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_merge.py -v` と `uv run ty check src`
Expected: すべて PASS、型エラーなし。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/merge.py test/test_merge.py
git commit -m "feat: セクションとタスクを id で 3 者マージし、整合を取る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: gitops にプルの段階を足す

**Files:**
- Modify: `src/projectapp/gitops.py`
- Create: `test/test_gitpull.py`

**Interfaces:**
- Consumes: 既存の`_call`・`_failed`・`list_changes`・`valid_name`・`PUSH_TIMEOUT`・`COMMIT_TIMEOUT`、`gitstate.PATHSPEC`・`failure_reason`・`run_git`・`Runner`。
- Produces:
  - `PullKind`(`UP_TO_DATE`・`FAST_FORWARD`・`MERGE`)、`PullPlan(kind: PullKind, upstream: str)`
  - `MergeFile(name: str, base: str, ours: str, theirs: str)`、`MergeSession(upstream: str, files: list[MergeFile])`
  - `pull_prepare(project_dir: Path, run: Runner = run_git) -> PullPlan | GitResult`
  - `pull_fast_forward(project_dir: Path, run: Runner = run_git) -> GitResult`
  - `pull_start_merge(project_dir: Path, upstream: str, run: Runner = run_git) -> MergeSession | GitResult`
  - `pull_finish_merge(project_dir: Path, session: MergeSession, merged: dict[str, str], run: Runner = run_git) -> GitResult`(成功時`detail`が短いハッシュ。失敗時は中止して戻す)
  - `pull_abort(project_dir: Path, run: Runner = run_git) -> GitResult`
  - `PullOps`(上の 5 つを`prepare`・`fast_forward`・`start_merge`・`finish_merge`・`abort`のメソッドにしたクラス。引数は`project_dir`のあとに同じもの。テストで差し替える)

- [ ] **Step 1: 失敗するテストを書く**(`test/test_gitpull.py`を新規作成)

```python
import subprocess
from pathlib import Path

import pytest

from projectapp.gitops import (
    GitResult,
    MergeSession,
    PullKind,
    PullPlan,
    pull_abort,
    pull_fast_forward,
    pull_finish_merge,
    pull_prepare,
    pull_start_merge,
)


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout


def configure(path: Path) -> None:
    git(path, "config", "user.name", "tester")
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "commit.gpgsign", "false")


def write(path: Path, name: str, text: str) -> None:
    (path / name).write_text(text, encoding="utf-8")


def commit_all(path: Path, message: str) -> None:
    git(path, "add", "-A")
    git(path, "commit", "-m", message)


BASE_TEXT = "1\n2\n3\n4\n5\n6\n7\n8\n9\n"


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """bare のリモートと、同じ内容から始まる 2 つのクローン(a・b)。甲.json と README.md がある。"""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    a = tmp_path / "a"
    a.mkdir()
    git(a, "init", "-b", "main")
    configure(a)
    write(a, "甲.json", BASE_TEXT)
    write(a, "README.md", "r\n")
    commit_all(a, "init")
    git(a, "remote", "add", "origin", str(remote))
    git(a, "push", "-u", "origin", "main")
    b = tmp_path / "b"
    git(tmp_path, "clone", str(remote), str(b))
    configure(b)
    return a, b


def push_change(clone: Path, name: str, text: str, message: str = "change") -> None:
    write(clone, name, text)
    commit_all(clone, message)
    git(clone, "push")


def parents(path: Path) -> list[str]:
    return git(path, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]


def test_up_to_date(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    assert pull_prepare(a) == PullPlan(PullKind.UP_TO_DATE, "origin/main")


def test_fast_forward(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("2", "二"))
    plan = pull_prepare(a)
    assert isinstance(plan, PullPlan) and plan.kind is PullKind.FAST_FORWARD
    assert pull_fast_forward(a).ok
    assert (a / "甲.json").read_text(encoding="utf-8").splitlines()[1] == "二"


def test_diverged_is_merge(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("2", "二"))
    write(a, "甲.json", BASE_TEXT.replace("8", "八"))
    commit_all(a, "mine")
    plan = pull_prepare(a)
    assert isinstance(plan, PullPlan) and plan.kind is PullKind.MERGE and plan.upstream == "origin/main"


def test_uncommitted_project_changes_refuse_the_pull(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    write(a, "甲.json", BASE_TEXT + "x\n")
    result = pull_prepare(a)
    assert isinstance(result, GitResult) and not result.ok and "甲.json" in result.message


def test_no_upstream_refuses(tmp_path: Path) -> None:
    repo = tmp_path / "solo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    configure(repo)
    write(repo, "甲.json", "x\n")
    commit_all(repo, "c")
    result = pull_prepare(repo)
    assert isinstance(result, GitResult) and result.message == "上流がありません"


def test_merge_with_a_textual_conflict_is_finished_with_the_apps_text(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("5", "B"))
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    session = pull_start_merge(a, "origin/main")
    assert isinstance(session, MergeSession)
    (file,) = session.files
    assert file.name == "甲.json" and file.base == BASE_TEXT
    assert "A" in file.ours and "B" in file.theirs
    done = pull_finish_merge(a, session, {"甲.json": BASE_TEXT.replace("5", "AB")})
    assert done.ok and done.detail
    assert len(parents(a)) == 2
    assert (a / "甲.json").read_text(encoding="utf-8") == BASE_TEXT.replace("5", "AB")
    assert git(a, "status", "--porcelain") == ""
    assert git(a, "log", "-1", "--format=%s").strip() == "マージ: origin/main"


def test_merge_without_overlap_in_project_files_needs_no_app_merge(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "README.md", "r2\n")
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    session = pull_start_merge(a, "origin/main")
    assert isinstance(session, MergeSession) and session.files == []
    assert pull_finish_merge(a, session, {}).ok
    assert len(parents(a)) == 2 and (a / "README.md").read_text() == "r2\n"


def test_conflict_outside_project_files_aborts_and_restores(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "README.md", "b\n")
    write(a, "README.md", "a\n")
    commit_all(a, "mine")
    git(a, "fetch")
    result = pull_start_merge(a, "origin/main")
    assert isinstance(result, GitResult) and not result.ok and "README.md" in result.message
    assert not (a / ".git" / "MERGE_HEAD").exists()
    assert (a / "README.md").read_text() == "a\n"


def test_file_level_conflict_aborts(pair: tuple[Path, Path]) -> None:
    a, b = pair
    git(b, "rm", "甲.json")
    commit_all(b, "delete")
    git(b, "push")
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    result = pull_start_merge(a, "origin/main")
    assert isinstance(result, GitResult) and not result.ok
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_failed_merge_commit_aborts_and_restores(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("5", "B"))
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    session = pull_start_merge(a, "origin/main")
    assert isinstance(session, MergeSession)
    git(a, "config", "user.useConfigOnly", "true")
    git(a, "config", "--unset", "user.name")
    git(a, "config", "--unset", "user.email")
    done = pull_finish_merge(a, session, {"甲.json": BASE_TEXT})
    assert not done.ok
    assert not (a / ".git" / "MERGE_HEAD").exists()
    assert (a / "甲.json").read_text(encoding="utf-8") == BASE_TEXT.replace("5", "A")


def test_abort_restores(pair: tuple[Path, Path]) -> None:
    a, b = pair
    push_change(b, "甲.json", BASE_TEXT.replace("5", "B"))
    write(a, "甲.json", BASE_TEXT.replace("5", "A"))
    commit_all(a, "mine")
    git(a, "fetch")
    assert isinstance(pull_start_merge(a, "origin/main"), MergeSession)
    assert pull_abort(a).ok
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_a_missing_git_does_not_raise(tmp_path: Path) -> None:
    def missing(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    result = pull_prepare(tmp_path, missing)
    assert isinstance(result, GitResult) and not result.ok
    assert not pull_fast_forward(tmp_path, missing).ok
    assert not pull_abort(tmp_path, missing).ok
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `uv run pytest test/test_gitpull.py -v`
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 実装する**(`src/projectapp/gitops.py`の末尾に足す。import に`os`・`tempfile`を足す)

```python
class PullKind(Enum):
    UP_TO_DATE = "最新"
    FAST_FORWARD = "早送り"
    MERGE = "マージ"


@dataclass(frozen=True)
class PullPlan:
    kind: PullKind
    upstream: str  # 例: origin/main


@dataclass(frozen=True)
class MergeFile:
    """両側が変えたプロジェクトファイル 1 つの、共通祖先・自分・相手の本文。"""

    name: str
    base: str
    ours: str
    theirs: str


@dataclass(frozen=True)
class MergeSession:
    upstream: str
    files: list[MergeFile]


def _git(run: Runner, project_dir: Path, args: list[str], timeout: float = COMMIT_TIMEOUT):
    return _call(run, ["-C", str(project_dir), *args], timeout)


def _out(done: subprocess.CompletedProcess[str] | GitResult) -> str | GitResult:
    """成功した出力の本文(前後の空白を除く)。失敗は`GitResult`。"""
    if isinstance(done, GitResult):
        return done
    if done.returncode != 0:
        return _failed(failure_reason(done))
    return done.stdout.strip()


def pull_prepare(project_dir: Path, run: Runner = run_git) -> PullPlan | GitResult:
    """プルの前提を確かめて`fetch`し、何をするか(最新・早送り・マージ)を決める。"""
    upstream = _git(run, project_dir, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if isinstance(upstream, GitResult):
        return upstream
    if upstream.returncode != 0:
        return _failed("上流がありません")
    changes = list_changes(project_dir, run)
    if isinstance(changes, GitResult):
        return changes
    if changes:
        return _failed("先に保存・コミットしてください: " + ", ".join(change.name for change in changes))
    fetched = _out(_git(run, project_dir, ["fetch"], PUSH_TIMEOUT))
    if isinstance(fetched, GitResult):
        return fetched
    counts = _out(_git(run, project_dir, ["rev-list", "--left-right", "--count", "HEAD...@{u}"]))
    if isinstance(counts, GitResult):
        return counts
    try:
        ahead, behind = (int(part) for part in counts.split())
    except ValueError:
        return _failed(f"想定外の出力です: {counts}")
    name = upstream.stdout.strip()
    if behind == 0:
        return PullPlan(PullKind.UP_TO_DATE, name)
    return PullPlan(PullKind.FAST_FORWARD if ahead == 0 else PullKind.MERGE, name)


def pull_fast_forward(project_dir: Path, run: Runner = run_git) -> GitResult:
    out = _out(_git(run, project_dir, ["merge", "--ff-only", "@{u}"]))
    return out if isinstance(out, GitResult) else GitResult(True, "取り込みました")


def pull_abort(project_dir: Path, run: Runner = run_git) -> GitResult:
    out = _out(_git(run, project_dir, ["merge", "--abort"]))
    return out if isinstance(out, GitResult) else GitResult(True, "取り込みを中止しました")


def _abort_with(project_dir: Path, run: Runner, message: str) -> GitResult:
    pull_abort(project_dir, run)  # 戻せなくても、元の失敗の理由を返す
    return _failed(message)


def _paths(run: Runner, project_dir: Path, args: list[str]) -> list[str] | GitResult:
    out = _git(run, project_dir, args)
    if isinstance(out, GitResult):
        return out
    if out.returncode != 0:
        return _failed(failure_reason(out))
    return [path for path in out.stdout.split("\0") if path]


def _show(run: Runner, project_dir: Path, rev: str, name: str) -> str | None:
    done = _git(run, project_dir, ["show", f"{rev}:./{name}"])
    if isinstance(done, GitResult) or done.returncode != 0:
        return None
    return done.stdout


def pull_start_merge(project_dir: Path, upstream: str, run: Runner = run_git) -> MergeSession | GitResult:
    """`git merge --no-commit --no-ff`を始め、両側が変えたプロジェクトファイルの 3 版を取り出す。
    アプリが統合できないとき(プロジェクトファイル以外の衝突・ファイル単位の衝突)は、中止して元に戻す。"""
    merged = _git(run, project_dir, ["merge", "--no-commit", "--no-ff", "@{u}"])
    if isinstance(merged, GitResult):
        return merged
    unmerged = _paths(run, project_dir, ["diff", "--name-only", "--diff-filter=U", "-z"])
    if isinstance(unmerged, GitResult):
        return _abort_with(project_dir, run, unmerged.message)
    if merged.returncode != 0 and not unmerged:
        return _abort_with(project_dir, run, failure_reason(merged))  # 衝突ではない失敗(未コミットの変更など)
    prefix = _out(_git(run, project_dir, ["rev-parse", "--show-prefix"]))
    base = _out(_git(run, project_dir, ["merge-base", "HEAD", "@{u}"]))
    for item in (prefix, base):
        if isinstance(item, GitResult):
            return _abort_with(project_dir, run, item.message)
    assert isinstance(prefix, str) and isinstance(base, str)
    tail = ["--name-only", "--relative", "--no-renames", "-z"]
    ours_changed = _paths(run, project_dir, ["diff", *tail, base, "HEAD", "--", *PATHSPEC])
    theirs_changed = _paths(run, project_dir, ["diff", *tail, base, "@{u}", "--", *PATHSPEC])
    for item in (ours_changed, theirs_changed):
        if isinstance(item, GitResult):
            return _abort_with(project_dir, run, item.message)
    assert isinstance(ours_changed, list) and isinstance(theirs_changed, list)
    both = sorted(name for name in set(ours_changed) & set(theirs_changed) if valid_name(name))
    stray = sorted(set(unmerged) - {prefix + name for name in both})
    if stray:
        return _abort_with(project_dir, run, "プロジェクトファイル以外に衝突があります: " + ", ".join(stray))
    files = []
    for name in both:
        texts = [_show(run, project_dir, rev, name) for rev in (base, "HEAD", "@{u}")]
        if any(text is None for text in texts):
            return _abort_with(project_dir, run, f"ファイル単位の衝突(追加・削除)のため、自動で取り込めません: {name}")
        files.append(MergeFile(name, *texts))  # type: ignore[arg-type]
    return MergeSession(upstream, files)


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pull-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def pull_finish_merge(
    project_dir: Path, session: MergeSession, merged: dict[str, str], run: Runner = run_git
) -> GitResult:
    """統合したファイルを書いて stage し、マージコミットを作る。どこで失敗しても、中止して元に戻す。"""
    names = sorted(merged)
    for name in names:
        if not valid_name(name):
            return _abort_with(project_dir, run, f"書けないファイル名です: {name}")
    try:
        for name in names:
            _write_atomic(project_dir / name, merged[name])
    except OSError as exc:
        return _abort_with(project_dir, run, str(exc))
    steps = []
    if names:
        steps.append(["--literal-pathspecs", "add", "--", *names])
    steps.append(["commit", "-m", f"マージ: {session.upstream}"])
    for args in steps:
        out = _out(_git(run, project_dir, args))
        if isinstance(out, GitResult):
            return _abort_with(project_dir, run, out.message)
    head = _out(_git(run, project_dir, ["rev-parse", "--short", "HEAD"]))
    return GitResult(True, "取り込みました", head if isinstance(head, str) else "")


class PullOps:
    """プルの各段階(`MainView`が持ち、テストで差し替える)。"""

    def prepare(self, project_dir: Path) -> PullPlan | GitResult:
        return pull_prepare(project_dir)

    def fast_forward(self, project_dir: Path) -> GitResult:
        return pull_fast_forward(project_dir)

    def start_merge(self, project_dir: Path, upstream: str) -> MergeSession | GitResult:
        return pull_start_merge(project_dir, upstream)

    def finish_merge(self, project_dir: Path, session: MergeSession, merged: dict[str, str]) -> GitResult:
        return pull_finish_merge(project_dir, session, merged)

    def abort(self, project_dir: Path) -> GitResult:
        return pull_abort(project_dir)
```

`PATHSPEC`は`from projectapp.gitstate import ...`に足す。`--literal-pathspecs`はコマンドの前(グローバル)オプションなので、`pull_finish_merge`の`add`の呼び出しでは、`_git`が`-C`の後ろに`args`を並べることに合わせ、`["--literal-pathspecs", "add", ...]`のままでよい(`git -C dir --literal-pathspecs add -- ...`)。`pull_start_merge`の`git show <rev>:./name`は、`-C`の作業フォルダ基準で解かれる。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_gitpull.py -v` と `uv run ty check src`
Expected: すべて PASS。実機の git の出力の違いで落ちるテストは、実際の出力を見て、実装(特に`--relative`・`--show-prefix`・`@{u}`の扱い)を直す。テストの期待を弱めて通さない。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/gitops.py test/test_gitpull.py
git commit -m "feat: git のプルの段階(fetch・マージの開始・確定・中止)を gitops に足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 衝突ダイアログ

**Files:**
- Modify: `src/projectapp/forms.py`(`open_commit_dialog`の後ろに足す)
- Test: `test/test_conflict_dialog.py`

**Interfaces:**
- Consumes: `merge.Conflict`・`merge.OURS`・`merge.THEIRS`・`merge.DELETED`・`merge.format_value`・`merge.Choices`。
- Produces: `open_conflict_dialog(file_name: str, conflicts: list[Conflict], on_apply: Callable[[Choices], object], on_cancel: Callable[[], object]) -> None`。マーカー: ラジオ`conflict-choice-{番号}`(番号は`conflicts`の添字。値は`ours`/`theirs`)、ボタン`conflict-apply`・`conflict-abort`。既定の選択は「相手」。「取り込む」で`on_apply`、「中止」・ESC・閉じるで`on_cancel`(どちらか一度だけ)。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_conflict_dialog.py`を新規作成。ダイアログのテストの書き方は、既存の`test/test_commit_dialog.py`に合わせる。以下は骨子で、`User`・`ui.page`の構成は同ファイルの冒頭をそのまま使う)

```python
from nicegui import ui
from nicegui.testing import User

from projectapp.forms import open_conflict_dialog
from projectapp.merge import DELETED, OURS, THEIRS, Conflict

CONFLICTS = [
    Conflict("task", "t1", "調査", "工数", 8.0, 2.0),
    Conflict("task", "t2", "設計", DELETED, None, {"name": "設計"}),
]


async def test_defaults_to_theirs_and_applies_the_choices(user: User) -> None:
    applied: list[dict] = []
    cancelled: list[bool] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_conflict_dialog("甲.json", CONFLICTS, applied.append, lambda: cancelled.append(True))).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="conflict-apply")
    radios = [next(iter(user.find(marker=f"conflict-choice-{i}").elements)) for i in range(2)]
    assert [r.value for r in radios] == [THEIRS, THEIRS]
    radios[0].set_value(OURS)
    user.find(marker="conflict-apply").click()
    assert applied == [{("task", "t1", "工数"): OURS, ("task", "t2", DELETED): THEIRS}]
    assert cancelled == []


async def test_abort_and_closing_cancel_once(user: User) -> None:
    applied: list[dict] = []
    cancelled: list[bool] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_conflict_dialog("甲.json", CONFLICTS, applied.append, lambda: cancelled.append(True))).mark("open")

    await user.open("/")
    user.find(marker="open").click()
    await user.should_see(marker="conflict-abort")
    user.find(marker="conflict-abort").click()
    assert cancelled == [True] and applied == []
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `uv run pytest test/test_conflict_dialog.py -v`
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 実装する**(`src/projectapp/forms.py`。`from projectapp.merge import ...`を import に足す)

```python
def open_conflict_dialog(
    file_name: str,
    conflicts: list[Conflict],
    on_apply: Callable[[Choices], object],
    on_cancel: Callable[[], object],
) -> None:
    """両側が違う値に変えた項目を、1 つずつ「自分」か「相手」で選ぶ(既定は相手)。
    「取り込む」で`on_apply`、「中止」・ESC・閉じるで`on_cancel`を、どちらか一度だけ呼ぶ。"""
    decided = {"done": False}

    def finish(action: Callable[[], object]) -> None:
        if decided["done"]:
            return
        decided["done"] = True
        action()

    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[40rem] max-w-full"):
        ui.label(f"{file_name} の衝突").classes("text-h6")
        ui.label("自分と相手が、同じ項目を違う値に変えています。採る値を選んでください。").classes("text-caption text-grey")
        radios: list[ui.radio] = []
        shown_label = None
        with ui.scroll_area().classes("w-full max-h-[60vh]"):
            for index, conflict in enumerate(conflicts):
                if (conflict.kind, conflict.key) != shown_label:
                    shown_label = (conflict.kind, conflict.key)
                    ui.label(conflict.label).classes("text-subtitle2 q-mt-sm")
                ui.label(conflict.field).classes("text-caption text-grey")
                if conflict.field == DELETED:
                    options = {
                        OURS: "自分: " + ("削除する" if conflict.ours is None else "残す"),
                        THEIRS: "相手: " + ("削除する" if conflict.theirs is None else "残す"),
                    }
                else:
                    options = {
                        OURS: f"自分: {format_value(conflict.ours)}",
                        THEIRS: f"相手: {format_value(conflict.theirs)}",
                    }
                radios.append(ui.radio(options, value=THEIRS).props("dense").mark(f"conflict-choice-{index}"))

        def apply() -> None:
            choices = {conflict.id: str(radio.value) for conflict, radio in zip(conflicts, radios, strict=True)}
            finish(lambda: on_apply(choices))
            dialog.close()

        def cancel() -> None:
            finish(on_cancel)
            dialog.close()

        with ui.row().classes("justify-end w-full"):
            ui.button("中止", on_click=cancel).props("flat").mark("conflict-abort")
            ui.button("取り込む", on_click=apply).mark("conflict-apply")
        dialog.on("hide", lambda: finish(on_cancel))  # ESC・外側のクリックも中止
    dialog.open()
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_conflict_dialog.py -v`
Expected: PASS(ESC のケースは、`user.keyboard`で`Escape`を送るテストを 1 つ足して確かめる。既存の`test_commit_dialog.py`に ESC のテストがあれば、同じ書き方にする)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py test/test_conflict_dialog.py
git commit -m "feat: プルの衝突を選ぶダイアログを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Git メニューの「プル」とショートカット、手順

**Files:**
- Modify: `src/projectapp/shortcuts.py`、`src/projectapp/views.py`
- Modify: `test/test_shortcuts.py`
- Create: `test/test_git_pull_view.py`

**Interfaces:**
- Consumes: Task 4 の`PullOps`・`PullKind`・`PullPlan`・`MergeSession`・`MergeFile`・`GitResult`、Task 3 の`merge_files`・`FileMerge`、Task 5 の`open_conflict_dialog`。
- Produces: `Shortcut("l", "git_pull", "プル", ctrl=True, shift=True)`、`MainView.pull_ops: PullOps`(差し替え可)、`MainView.start_git_pull()`、`MainView.run_pull()`、`git_reason("pull")`、メニュー項目(`プル`・`cloud_download`・マーカー`git-pull`)。

仕様:
- `git_reason("pull")`: 既存の順に加えて、`state.kind is not OK` → 作業ツリーでない、`git_busy` → 実行中、`state.error` → 読めていない、`upstream is None` → 上流がありません、`state.ahead is None` → 上流が見つかりません、`state.dirty > 0` → 「未コミットの変更があります。先にコミットしてください」、`self.is_dirty()` → 「保存されていない編集があります。先に保存・コミットしてください」。
- Git メニューの順は「コミット…」「プッシュ」「プル」「状態を読み直す」。`GIT_MENU`に`("pull", "git-pull")`を足す。
- `start_git_pull`: 理由があれば通知して戻る。なければ`self.later(self.run_pull)`。
- `run_pull`: `git_busy`を立て、`finally`で下ろして`request_git_refresh()`。手順は下のコード。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_shortcuts.py`の`("K", True, True, "git_push"),`の下に`("l", True, True, "git_pull"), ("L", True, True, "git_pull"),`を足し、`label_for`のテストに`assert label_for("git_pull") == "Ctrl/Cmd+Shift+L"`を足す。

`test/test_git_pull_view.py`を新規作成(`test_git_ops_view.py`の`Fakes`・`open_with`・`wait_until`・`menu_entry`の書き方を踏襲し、`mount`でプルの差し替えを足す):

```python
import asyncio
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User
from test_git_ops_view import AHEAD, SYNCED, Fakes, menu_entry, wait_until

from projectapp.calendar import save_cache
from projectapp.gitops import GitResult, MergeFile, MergeSession, PullKind, PullPlan
from projectapp.gitstate import GitKind, GitState
from projectapp.models import Project, Task
from projectapp.storage import dumps_project
from projectapp.views import MainView

from datetime import date

BEHIND = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=0, behind=2)


class FakePullOps:
    def __init__(self) -> None:
        self.plan: PullPlan | GitResult = PullPlan(PullKind.UP_TO_DATE, "origin/main")
        self.session: MergeSession | GitResult = MergeSession("origin/main", [])
        self.ff_result = GitResult(True, "取り込みました")
        self.finish_result = GitResult(True, "取り込みました", "abc1234")
        self.calls: list[str] = []
        self.merged: dict[str, str] | None = None

    def prepare(self, d: Path):
        self.calls.append("prepare")
        return self.plan

    def fast_forward(self, d: Path):
        self.calls.append("ff")
        return self.ff_result

    def start_merge(self, d: Path, upstream: str):
        self.calls.append("start")
        return self.session

    def finish_merge(self, d: Path, session: MergeSession, merged: dict[str, str]):
        self.calls.append("finish")
        self.merged = merged
        return self.finish_result

    def abort(self, d: Path):
        self.calls.append("abort")
        return GitResult(True, "中止")


async def open_pull(user: User, tmp_path: Path, state: GitState = BEHIND) -> tuple[MainView, FakePullOps]:
    fakes, ops = Fakes(state), FakePullOps()
    save_cache({}, tmp_path)
    views: list[MainView] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200)))
        view.read_git = fakes.read_git
        view.pull_ops = ops
        views.append(view)
        view.build()

    await user.open("/")
    view = views[0]
    assert await wait_until(lambda: view.git_state is state)
    return view, ops


def project_text(effort: float) -> str:
    return dumps_project(Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=effort)]))


async def test_the_pull_menu_item_and_reasons(user: User, tmp_path: Path) -> None:
    view, _ = await open_pull(user, tmp_path)
    entry = menu_entry(view, "git-pull")
    assert entry.enabled and view.git_reason("pull") is None
    view.git_state = GitState(GitKind.OK, branch="main", upstream="origin/main", ahead=0, behind=0, dirty=1)
    assert "未コミット" in (view.git_reason("pull") or "")
    view.git_state = GitState(GitKind.OK, branch="main")
    assert view.git_reason("pull") == "上流がありません"
    view.git_state = GitState(GitKind.NOT_REPO)
    assert view.git_reason("pull") == "git の作業ツリーではありません"
    view.git_state = BEHIND
    view.git_busy = True
    assert view.git_reason("pull") == "実行中です"


async def test_unsaved_edits_refuse_the_pull(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    view.save_section("追加")
    assert "保存されていない編集" in (view.git_reason("pull") or "")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("保存されていない編集"))
    assert ops.calls == []


async def test_up_to_date_just_notifies(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("最新です"))
    assert ops.calls == ["prepare"] and not view.git_busy


async def test_prepare_failure_is_reported(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = GitResult(False, "上流がありません")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("上流がありません"))
    assert not view.git_busy


async def test_fast_forward(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.FAST_FORWARD, "origin/main")
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("取り込みました"))
    assert ops.calls == ["prepare", "ff"]


async def test_merge_without_conflicts_finishes_with_the_merged_text(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    base, ours = project_text(4.0), project_text(8.0)
    theirs = dumps_project(Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=4.0, name="a2")]))
    ops.session = MergeSession("origin/main", [MergeFile("甲.json", base, ours, theirs)])
    view.start_git_pull()
    assert await wait_until(lambda: user.notify.contains("取り込みました"))
    assert ops.calls == ["prepare", "start", "finish"] and set(ops.merged) == {"甲.json"}
    assert '"a2"' in ops.merged["甲.json"] and "8.0" in ops.merged["甲.json"]


async def test_merge_with_a_conflict_waits_for_the_choice(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession("origin/main", [MergeFile("甲.json", project_text(4.0), project_text(8.0), project_text(2.0))])
    view.start_git_pull()
    await user.should_see(marker="conflict-apply")
    assert ops.calls == ["prepare", "start"]
    user.find(marker="conflict-apply").click()  # 既定は相手
    assert await wait_until(lambda: "finish" in ops.calls)
    assert "2.0" in ops.merged["甲.json"]


async def test_cancelling_the_conflict_dialog_aborts(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession("origin/main", [MergeFile("甲.json", project_text(4.0), project_text(8.0), project_text(2.0))])
    view.start_git_pull()
    await user.should_see(marker="conflict-abort")
    user.find(marker="conflict-abort").click()
    assert await wait_until(lambda: "abort" in ops.calls)
    assert "finish" not in ops.calls and not view.git_busy


async def test_unreadable_files_abort_the_merge(user: User, tmp_path: Path) -> None:
    view, ops = await open_pull(user, tmp_path)
    ops.plan = PullPlan(PullKind.MERGE, "origin/main")
    ops.session = MergeSession("origin/main", [MergeFile("甲.json", "{", "{", "{")])
    view.start_git_pull()
    assert await wait_until(lambda: "abort" in ops.calls)
    assert "finish" not in ops.calls and not view.git_busy


async def test_pull_reloads_the_open_project_and_refreshes_git(user: User, tmp_path: Path) -> None:
    from projectapp.storage import save_project

    save_project(Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=4.0)]), tmp_path)
    view, ops = await open_pull(user, tmp_path)
    view.files = {"甲": tmp_path / "甲.json"}
    view.open_project("甲")
    save_project(Project("甲", date(2026, 10, 1), tasks=[Task("a", id="t1", effort_hours=9.0)]), tmp_path)  # プルで書き換わった想定
    ops.plan = PullPlan(PullKind.FAST_FORWARD, "origin/main")
    view.start_git_pull()
    assert await wait_until(lambda: view.project.tasks[0].effort_hours == 9.0)
    assert not view.is_dirty()
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `uv run pytest test/test_shortcuts.py test/test_git_pull_view.py -v`
Expected: FAIL

- [ ] **Step 3: 実装する**

`shortcuts.py`: `Shortcut("k", "git_push", ...)`の下に`Shortcut("l", "git_pull", "プル", ctrl=True, shift=True),`を足す。

`views.py`:
- import に`PullKind, PullOps`(`projectapp.gitops`)、`merge_files`(`projectapp.merge`)、`open_conflict_dialog`(`projectapp.forms`)を足す。
- `__init__`に`self.pull_ops: PullOps = PullOps()  # テストで差し替える`を足す。
- `SHORTCUT_METHODS`に`"git_pull": "start_git_pull",`、メニューの`MenuItem`を「プッシュ」の後ろに`MenuItem("プル", "cloud_download", self.start_git_pull, "git-pull", label_for("git_pull")),`、`GIT_MENU`に`("pull", "git-pull")`を足す(「プッシュ」と「状態を読み直す」の間)。
- `git_reason`に、`push`の分岐の後ろ(`return None`の前)へ次を足す。

```python
        if action == "pull":
            if state.error is not None:
                return "git の状態を読めていません"
            if state.upstream is None:
                return "上流がありません"
            if state.ahead is None:
                return "上流が見つかりません"
            if state.dirty:
                return "未コミットの変更があります。先にコミットしてください"
            if self.is_dirty():
                return "保存されていない編集があります。先に保存・コミットしてください"
```

- `start_git_push`の下に、次のメソッドを足す。

```python
    def start_git_pull(self) -> None:
        """プルを始める(メニューとショートカットの入口)。できないときは、理由を通知する。"""
        reason = self.git_reason("pull")
        if reason is not None:
            ui.notify(reason, type="warning")
            return
        self.later(self.run_pull)

    async def run_pull(self) -> None:
        """fetch して、最新・早送り・マージのどれかを行う。終わったら、開いているプロジェクトを読み直す。"""
        if self.git_busy:
            return
        self.set_git_busy(True)
        reload_needed = False
        try:
            ops = self.pull_ops
            plan = await run.io_bound(ops.prepare, self.project_dir)
            if plan is None:  # アプリの終了中
                return
            if isinstance(plan, GitResult):
                ui.notify(plan.message, type="negative")
                return
            if plan.kind is PullKind.UP_TO_DATE:
                ui.notify("最新です")
                return
            if plan.kind is PullKind.FAST_FORWARD:
                done = await run.io_bound(ops.fast_forward, self.project_dir)
                if done is None:
                    return
                ui.notify(done.message, type="positive" if done.ok else "negative")
                reload_needed = done.ok
                return
            reload_needed = await self.pull_merge(plan.upstream)
        finally:
            self.set_git_busy(False)
            if reload_needed:
                self.reload_after_pull()
            self.request_git_refresh()

    async def pull_merge(self, upstream: str) -> bool:
        """マージを始め、ファイルごとに統合する(衝突は選ばせる)。取り込めたら True。失敗・中止は元に戻す。"""
        ops = self.pull_ops
        session = await run.io_bound(ops.start_merge, self.project_dir, upstream)
        if session is None:
            return False
        if isinstance(session, GitResult):
            ui.notify(session.message, type="negative")
            return False
        merged: dict[str, str] = {}
        notes: list[str] = []
        picked = 0
        try:
            for file in session.files:
                outcome = merge_files(file.name, file.base, file.ours, file.theirs)
                if outcome.conflicts:
                    choices = await self.ask_conflicts(file.name, outcome.conflicts)
                    if choices is None:
                        await run.io_bound(ops.abort, self.project_dir)
                        ui.notify("取り込みを中止しました")
                        return False
                    picked += len(outcome.conflicts)
                    outcome = merge_files(file.name, file.base, file.ours, file.theirs, choices)
                merged[file.name] = outcome.text
                notes += outcome.notes
        except ValueError as exc:
            await run.io_bound(ops.abort, self.project_dir)
            ui.notify(f"統合できませんでした: {exc}", type="negative")
            return False
        done = await run.io_bound(ops.finish_merge, self.project_dir, session, merged)
        if done is None:
            return False
        if not done.ok:
            ui.notify(f"取り込めませんでした: {done.message}", type="negative")
            return False
        message = "取り込みました" + (f"(衝突 {picked} 件を選択)" if picked else "")
        ui.notify(message, type="positive")
        for note in notes:
            ui.notify(note, type="warning")
        return True

    async def ask_conflicts(self, name: str, conflicts):
        """衝突ダイアログを開き、選択(中止なら None)を待つ。"""
        future = asyncio.get_running_loop().create_future()
        open_conflict_dialog(
            name,
            conflicts,
            lambda choices: future.done() or future.set_result(choices),
            lambda: future.done() or future.set_result(None),
        )
        return await future

    def reload_after_pull(self) -> None:
        """プルで書き換わったかもしれないので、開いているプロジェクトを読み直す(未保存の編集はなかった)。"""
        self.files = {p.stem: p for p in list_project_files(self.project_dir)}
        self.file_select.set_options(sorted(self.files), value=self.current_name())
        name = self.current_name()
        if name is not None and name in self.files:
            self.open_project(name)
```

(`asyncio`・`list_project_files`が`views.py`で未 import なら足す。型注釈の`conflicts`は`list[Conflict]`にする。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_shortcuts.py test/test_git_pull_view.py test/test_git_ops_view.py test/test_git_view.py -v` と `uv run ty check src`
Expected: すべて PASS。ショートカットヘルプの一覧を数えるテストがあれば、1 件増えた分を直す。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/shortcuts.py src/projectapp/views.py test/test_shortcuts.py test/test_git_pull_view.py
git commit -m "feat: Git メニューの「プル」で、相手の変更を取り込めるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 実際の git と実際のファイルでの通し検証

**Files:**
- Test: `test/test_gitpull.py`(通しのテストを足す)

`merge.py`・`gitops.py`・`storage.py`を、画面を介さずに本物の git とプロジェクトファイルでつなぎ、別々のタスクを別々のクローンで編集して、衝突なしで取り込めることを確かめる。

- [ ] **Step 1: テストを書く**(`test/test_gitpull.py`に足す。`pair`フィクスチャの`甲.json`は文字列のままなので、このテストでは自前で保存する)

```python
def test_end_to_end_two_people_edit_different_tasks(pair: tuple[Path, Path]) -> None:
    from datetime import date

    from projectapp.gitops import pull_finish_merge, pull_prepare, pull_start_merge
    from projectapp.merge import merge_files
    from projectapp.models import Project, Task
    from projectapp.storage import load_project, save_project

    a, b = pair
    base = Project("共有", date(2026, 10, 1), tasks=[Task(f"t{i}", id=f"id{i}", effort_hours=1.0) for i in range(1, 7)])
    save_project(base, a)
    commit_all(a, "共有を追加")
    git(a, "push")
    git(b, "pull")
    mine = load_project(a / "共有.json")
    mine.tasks[0].effort_hours = 5.0  # a は先頭を変える
    save_project(mine, a)
    commit_all(a, "a の変更")
    theirs = load_project(b / "共有.json")
    theirs.tasks[5].effort_hours = 7.0  # b は末尾を変える
    save_project(theirs, b)
    commit_all(b, "b の変更")
    git(b, "push")

    plan = pull_prepare(a)
    assert isinstance(plan, PullPlan) and plan.kind is PullKind.MERGE
    session = pull_start_merge(a, plan.upstream)
    assert isinstance(session, MergeSession)
    merged: dict[str, str] = {}
    for file in session.files:
        outcome = merge_files(file.name, file.base, file.ours, file.theirs)
        assert outcome.conflicts == []
        merged[file.name] = outcome.text
    assert pull_finish_merge(a, session, merged).ok
    result = load_project(a / "共有.json")
    assert [t.effort_hours for t in result.tasks] == [5.0, 1.0, 1.0, 1.0, 1.0, 7.0]
    assert len(parents(a)) == 2
```

- [ ] **Step 2: 実行する**

Run: `uv run pytest test/test_gitpull.py -v`
Expected: PASS

- [ ] **Step 3: 全体を通す**

Run: `uv run pytest -n auto` と `uv run ty check src`
Expected: すべて PASS、型エラーなし。テスト件数(現在 2,418 件)を控える。

- [ ] **Step 4: コミット**

```bash
git add test/test_gitpull.py
git commit -m "test: 2 人が別々のタスクを編集したプルの通しのテストを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: ネイティブウィンドウでの実機の確認

**Files:** なし(確認のみ。結果は Task 9 の文書に書く)

- [ ] **Step 1: 確認用のリポジトリを作る**

```bash
cd $TMPDIR && rm -rf pull-demo && mkdir pull-demo && cd pull-demo
git init --bare -b main remote.git
git clone remote.git a && git clone remote.git b
```

`a`で、アプリから「格納先を変更」→`a`を選び、プロジェクトを保存して、タスクを数件足してコミットし、プッシュする。`b`を別の格納先として、`git pull`し、アプリで別のタスクを編集してコミット・プッシュする。`a`に戻り、別のタスクを編集してコミットしたあと、「プル」を実行する。

- [ ] **Step 2: 次を確かめる**(`/run`スキルでアプリを起動する)
  - 別のタスクの編集は、衝突なしで取り込まれ、`git log --graph`で親が 2 つのマージコミットになる
  - 同じタスクの同じ項目を変えると、衝突ダイアログが出て、選んだ値になる
  - ダイアログを ESC で閉じると、`git status`がクリーンで、`.git/MERGE_HEAD`がない
  - 未保存の編集・未コミットの変更があると、メニューが押せず、理由がマウスオーバーに出る
  - 取り込み後、開いているプロジェクトが読み直され、ガントチャートが更新される
  - Ctrl/Cmd+Shift+L で動く。ショートカットヘルプに載っている

- [ ] **Step 3: 結果を Task 9 の文書に書く。** 確認できなかった項目は、そのまま「未確認」と書く。

---

### Task 9: ドキュメントの更新

**Files:**
- Modify: `CLAUDE.md`(`projectapp/CLAUDE.md`)、`docs/development.md`、`docs/request-history.md`、`docs/superpowers/specs/2026-10-14-git-pull-merge-design.md`

- [ ] **Step 1: `projectapp/CLAUDE.md`を更新する**
  - 「ヘッダー」の`Git`メニューの記述に`プル`を足す(項目の順、押せない条件: 作業ツリーでない・上流がない・未コミットの変更・未保存の編集・実行中)。キーボードショートカットの一覧に`Ctrl/Cmd+Shift+L` プルを足す。
  - 「git のコミットとプッシュ」の節のあとに、「git のプル」の節を足す: 手順(fetch → 最新・早送り・マージ)、マージの規則(項目単位・同じ項目だけ選ぶ・id で突き合わせる・削除と変更は選ぶ)、マージコミットを作ること、未コミット・未保存では拒否すること、ファイル単位の衝突とプロジェクトファイル以外の衝突は中止して戻すこと。「含まない」に、自動プル・名前の変更の追従を書く。
  - 「git のコミットとプッシュ」の「ブランチの切り替え・プル・`fetch`・マージは含まない」を、プルを含む形に直す(`fetch`はプルの中だけ)。プッシュの拒否の案内「先にプルが必要です(プルは後続機能)」を「先にプルが必要です」に直し、`gitops.PULL_HINT`とそのテストも直す。

- [ ] **Step 2: `docs/development.md`を更新する**
  - `merge.py`: 突き合わせの鍵(id・名前)、項目ごとの規則、`_order`、整合(先行・担当者・カテゴリ・消えたセクション)、`merge_files`の検証、既知の制限(パラメータ・テンプレートの名前変更は削除と追加に見える)を書く。
  - `gitops`のプル: 手順、`@{u}`、`--relative`・`--show-prefix`、ファイル単位の衝突の中止、`MERGE_HEAD`の戻し方、Task 8 で確かめた点。

- [ ] **Step 3: `docs/request-history.md`を更新する**
  - 要望 10 の行に、5 番目(`git-pull-merge`。PR 番号はマージ後に入れる。テスト件数)を足す。
  - 「要望 10 の分割」の表の 5 番目を「実装済み(マージ待ち)」にし、設計書名`git-pull-merge`を入れる。
  - 「未着手の整理」の要望 10 の「次の一歩」を、残る後続(merge driver、自動プル、名前の変更の追従)に直す。

- [ ] **Step 4: 設計書を計画の調整に合わせて直す**(「設計書からの調整」の 6 項目を、設計書の該当箇所に反映する)

- [ ] **Step 5: 全体の検証とコミット**

Run: `uv run pytest -n auto` と `uv run ty check src`
Expected: すべて PASS

```bash
git add CLAUDE.md docs src test
git commit -m "docs: git のプルとマージの仕様と開発メモを更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

(`CLAUDE.md`は`projectapp/CLAUDE.md`のこと。リポジトリのルートはこのフォルダ。)

---

## Self-Review(計画の作成者が実施)

- **Spec coverage:** merge.py の規則(Task 2・3)、gitops の段階(Task 4)、メニュー・ショートカット・手順(Task 6)、衝突ダイアログ(Task 5)、`git_busy`・読み直し・`digest`の更新(Task 6 の`reload_after_pull`が`open_project`を通るので、`digest`も更新される)、テスト(各 Task と Task 7)、ドキュメント(Task 9)。設計書との差分は冒頭の「設計書からの調整」に列挙した。
- **Placeholder scan:** 骨子のままのコードと、分岐つきのテストは残していない。
- **Type consistency:** `Conflict.id`は`(kind, key, field)`、`Choices`は`dict[tuple[str,str,str], str]`で、Task 2・3・5・6 で一致。`MergeSession.files: list[MergeFile]`、`PullOps`のメソッド名(`prepare`・`fast_forward`・`start_merge`・`finish_merge`・`abort`)は Task 4・6 で一致。
