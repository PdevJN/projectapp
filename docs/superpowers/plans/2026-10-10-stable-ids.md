# メンバーとセクションの安定 id Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メンバーとセクションに安定した `id` を付け、ファイル(version 2)では担当者がメンバー `id` を指すようにする。実行時の担当者は名前参照のまま。

**Architecture:** `models.py` に `id` と `new_id(taken)`・`Project.used_ids()` を足す。`storage.py` は、保存で `asdict` の結果の担当者だけを「名前 → メンバー id」に置き換え、読込は `_Context`(版・メンバー id → 名前・セクション id・id のないタスク)を通して version 1/2 を読み分ける。画面側は、メンバーのダイアログの行に `id` を持たせて引き継ぎ、新しく作る箇所は既存の id を避けて振る。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -q -n auto`)、`uvx ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-10-stable-ids-design.md`

## Global Constraints

- `FORMAT_VERSION` を 2 にする。キーのない・1 のファイルは version 1 として読み、保存し直すと version 2 になる。
- id は `new_id()` の 8 桁の 16 進。`Member.id`・`Section.id` は `compare=False`。`Assignee` は変えない(`name` のまま)。
- 実行時の担当者の参照(約 30 箇所の名前参照)・`handoff.py`・パラメータ/段階/テンプレートの id は変えない(範囲外)。
- 保存の直前に、タスク同士・メンバー同士・セクション同士の id の重複があれば `save_project` は `ValueError`(ファイルを書き換えない)。
- 読込は、version 2 の `id` の欠落・`null`・空・文字列以外・重複(メンバー同士・セクション同士)、存在しない/文字列でない担当者の `member`、担当者の旧キー `name` を `ValueError` で拒否する。
- 重複名・空名のメンバーは、今までどおり最初の 1 件を残して捨てる。捨てた同名メンバーの id を指す担当者は、残ったメンバーへ読む。名前が空のメンバーの id を指す担当者は、存在しない `member` として拒否する。
- コメントの密度・命名・日本語の文体は、周囲のコードに合わせる。コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. version 1 のファイルで、id のないタスク・メンバー・セクションに振る id が、ファイルにある他の id と重ならない(Task 2)。
2. 保存時、担当者の名前がメンバーにいない(古い画面や手で作ったデータ)とき、メンバーを補って保存し、読み直すと担当者が残る(Task 2)。
3. 同名のメンバーが 2 人いるプロジェクトを保存して読むと、担当者は残った 1 人に付く。ファイルを手で書き換えて、捨てられた側の id を指しても開ける(Task 2)。
4. 重複した id のまま保存しようとすると、ファイルが壊れず(既存のファイルは残り)エラーになる(Task 2)。
5. メンバーのダイアログで名前を入れ替えても、各行の id は行について回る。行を消して同じ名前で足し直すと、新しい id になる(Task 3)。

---

### Task 1: モデル(`new_id(taken)`・`Member.id`・`Section.id`・`Project.used_ids`)

**Files:**
- Modify: `src/projectapp/models.py`(`new_id`、`Member`、`Section`、`Project`)
- Test: `test/test_models.py`

**Interfaces:**
- Produces: `new_id(taken: Collection[str] = ()) -> str`(`taken` にない 8 桁の 16 進)、`Member.id: str`・`Section.id: str`(各クラスの最後のフィールド。位置引数の既存の呼び出しは変わらない。`compare=False`)、`Project.used_ids() -> set[str]`(タスク・メンバー・セクションの id)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_models.py` の import を次に直し、末尾にテストを足す。

```python
import projectapp.models as models
from projectapp.models import Member, Project, Section, Task, new_id, walk_sections
```

```python
def test_new_id_is_8_hex_digits() -> None:
    value = new_id()
    assert len(value) == 8 and int(value, 16) >= 0


def test_new_id_does_not_return_a_taken_id(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter(["aaaaaaaa", "aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr(models.secrets, "token_hex", lambda nbytes: next(values))
    assert new_id({"aaaaaaaa"}) == "bbbbbbbb"


def test_member_and_section_get_ids_that_do_not_affect_equality() -> None:
    assert len(Member("田中").id) == 8 and len(Section("s").id) == 8
    assert Member("田中", 1.2) == Member("田中", 1.2)
    assert Section("s", [Task("a")]) == Section("s", [Task("a")])
    assert Member("田中").id != Member("田中").id


def test_used_ids_collects_tasks_members_and_nested_sections() -> None:
    project = tree()
    project.members = [Member("田中"), Member("鈴木")]
    expected = (
        {t.id for t in project.all_tasks()}
        | {m.id for m in project.members}
        | {s.id for _, s in walk_sections(project.sections)}
    )
    assert project.used_ids() == expected
    assert len(expected) == 6 + 2 + 5
```

ファイル先頭の `from projectapp.models import Project, Section, Task, walk_sections` は、上の 2 行の import に置き換える。`import pytest` を足す。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_models.py`
Expected: FAIL(`new_id` が `taken` を受け取らない・`Member.id` がない)。

- [ ] **Step 3: 実装する**

`src/projectapp/models.py`:

1. `from collections.abc import Iterator` → `from collections.abc import Collection, Iterator`
2. `new_id` を置き換える。

```python
def new_id(taken: Collection[str] = ()) -> str:
    """id。8 桁の 16 進。`taken` にある id は返さない(プロジェクト内で重複しないように、振る側が既存の id を渡す)。"""
    while True:
        candidate = secrets.token_hex(4)
        if candidate not in taken:
            return candidate
```

3. `Member` の最後(`levels` の下)に足す。

```python
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する(担当者はこの id で指す)
```

4. `Section` の最後(`sections` の下)に足す。

```python
    id: str = field(default_factory=new_id, compare=False)  # 安定した識別子。ファイルに保存する
```

5. `Project` の `all_tasks` の下に足す。

```python
    def used_ids(self) -> set[str]:
        """タスク・メンバー・セクションの id。新しい id が既存と重ならないように、振る側が渡す。"""
        return (
            {t.id for t in self.all_tasks()}
            | {m.id for m in self.members}
            | {s.id for _, s in walk_sections(self.sections)}
        )
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q test/test_models.py`
Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/models.py test/test_models.py
git commit -m "feat: メンバーとセクションに id を持たせ、new_id が既存の id を避けられるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ファイル形式 version 2(保存と読込)

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION = 2`)
- Modify: `src/projectapp/storage.py`
- Test: `test/test_storage.py`

**Interfaces:**
- Consumes: Task 1 の `new_id(taken)`、`Member.id`、`Section.id`、`Project.used_ids()`、`walk_sections`。
- Produces: version 2 のファイル。`save_project` は重複 id で `ValueError`。`load_project` は version 1/2 を読む。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の末尾に足す。先頭の import に `from projectapp.models import ...` へ `walk_sections` を足す(`Assignee` などは既にある)。

```python
def _task_dicts(tasks: list[dict], sections: list[dict]):
    yield from tasks
    for section in sections:
        yield from _task_dicts(section["tasks"], section["sections"])


def _to_v1(data: dict) -> None:
    """version 2 のファイルの辞書を、version 1 の形(id なし・担当者は名前)にする。"""
    names = {m["id"]: m["name"] for m in data["members"]}
    del data["version"]
    for member in data["members"]:
        del member["id"]

    def strip(sections: list[dict]) -> None:
        for section in sections:
            del section["id"]
            strip(section["sections"])

    strip(data["sections"])
    for task in _task_dicts(data["tasks"], data["sections"]):
        task["assignees"] = [{"name": names[a["member"]], "allocation": a["allocation"]} for a in task["assignees"]]


def ids_project() -> Project:
    return Project(
        "p",
        members=[Member("田中"), Member("鈴木")],
        tasks=[Task("r", assignees=[Assignee("鈴木", 0.5)])],
        sections=[
            Section("s", [Task("a", assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.4)])], [Section("sub", [Task("b")])])
        ],
    )


def test_saved_file_is_version_2_and_refers_to_members_by_id(tmp_path: Path) -> None:
    project = ids_project()
    raw = json.loads(save_project(project, tmp_path).read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION == 2
    tanaka, suzuki = project.members
    assert [m["id"] for m in raw["members"]] == [tanaka.id, suzuki.id]
    assert raw["sections"][0]["id"] == project.sections[0].id
    assert raw["sections"][0]["sections"][0]["id"] == project.sections[0].sections[0].id
    assert raw["sections"][0]["tasks"][0]["assignees"] == [
        {"member": tanaka.id, "allocation": 0.6},
        {"member": suzuki.id, "allocation": 0.4},
    ]
    assert raw["tasks"][0]["assignees"] == [{"member": suzuki.id, "allocation": 0.5}]


def test_ids_survive_save_load_save(tmp_path: Path) -> None:
    project = ids_project()
    loaded = load_project(save_project(project, tmp_path))
    assert [m.id for m in loaded.members] == [m.id for m in project.members]
    assert [s.id for _, s in walk_sections(loaded.sections)] == [s.id for _, s in walk_sections(project.sections)]
    assert loaded.sections[0].tasks[0].assignees == [Assignee("田中", 0.6), Assignee("鈴木", 0.4)]
    again = load_project(save_project(loaded, tmp_path))
    assert again.used_ids() == project.used_ids()


def test_a_renamed_member_keeps_the_id_and_the_assignment(tmp_path: Path) -> None:
    project = ids_project()
    path = save_project(project, tmp_path)
    _rewrite(path, lambda d: d["members"][0].update(name="田中二郎"))
    loaded = load_project(path)
    assert loaded.members[0].id == project.members[0].id
    assert loaded.sections[0].tasks[0].assignee_names == ["田中二郎", "鈴木"]


def test_a_version_1_file_gets_unique_ids(tmp_path: Path) -> None:
    path = save_project(ids_project(), tmp_path)
    _rewrite(path, lambda d: (_to_v1(d), [t.pop("id") for t in _task_dicts(d["tasks"], d["sections"]) if t["name"] == "b"]))
    loaded = load_project(path)
    ids = [t.id for t in loaded.all_tasks()] + [m.id for m in loaded.members] + [s.id for _, s in walk_sections(loaded.sections)]
    assert len(ids) == 3 + 2 + 2 and len(set(ids)) == len(ids)
    assert all(len(i) == 8 for i in ids)
    assert loaded.sections[0].tasks[0].assignees == [Assignee("田中", 0.6), Assignee("鈴木", 0.4)]
    raw = json.loads(save_project(loaded, tmp_path, overwrite=True).read_text(encoding="utf-8"))
    assert raw["version"] == 2


def test_version_1_ids_avoid_the_ids_in_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project("p", members=[Member("田中")], sections=[Section("s", [Task("a", id="aaaaaaaa")])])
    path = save_project(project, tmp_path)
    _rewrite(path, _to_v1)
    values = iter(["aaaaaaaa", "bbbbbbbb", "cccccccc"])
    monkeypatch.setattr("projectapp.models.secrets.token_hex", lambda nbytes: next(values))
    loaded = load_project(path)
    assert loaded.sections[0].tasks[0].id == "aaaaaaaa"
    assert {loaded.members[0].id, loaded.sections[0].id} == {"bbbbbbbb", "cccccccc"}


def test_save_adds_a_member_for_an_unknown_assignee(tmp_path: Path) -> None:
    project = Project("p", tasks=[Task("a", assignees=[Assignee("佐藤", 0.5)])])
    path = save_project(project, tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert [m["name"] for m in raw["members"]] == ["佐藤"]
    assert raw["tasks"][0]["assignees"] == [{"member": raw["members"][0]["id"], "allocation": 0.5}]
    assert project.members == []  # 保存は実行時のプロジェクトを変えない
    loaded = load_project(path)
    assert loaded.tasks[0].assignees == [Assignee("佐藤", 0.5)]
    assert [m.name for m in loaded.members] == ["佐藤"]


def test_save_points_a_duplicate_named_member_at_the_first(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中", 1.2), Member("田中", 0.5)], tasks=[Task("a", assignees=[Assignee("田中")])])
    path = save_project(project, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["assignees"][0]["member"] == project.members[0].id
    loaded = load_project(path)
    assert loaded.members == [Member("田中", 1.2)]
    assert loaded.tasks[0].assignee_names == ["田中"]


def test_an_assignee_pointing_at_a_dropped_duplicate_reads_as_the_kept_member(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中", 1.2), Member("田中", 0.5)], tasks=[Task("a", assignees=[Assignee("田中")])])
    path = save_project(project, tmp_path)
    second = project.members[1].id
    _rewrite(path, lambda d: d["tasks"][0]["assignees"][0].update(member=second))
    assert load_project(path).tasks[0].assignee_names == ["田中"]


def test_an_assignee_pointing_at_a_blank_named_member_is_rejected(tmp_path: Path) -> None:
    project = Project("p", members=[Member("田中"), Member("鈴木")], tasks=[Task("a", assignees=[Assignee("鈴木")])])
    path = save_project(project, tmp_path)
    _rewrite(path, lambda d: d["members"][1].update(name="  "))
    with pytest.raises(ValueError, match="メンバーが見つかりません"):
        load_project(path)


def _bad_id_cases() -> list[tuple[str, Callable[[dict], None]]]:
    return [
        ("メンバー id なし", lambda d: d["members"][0].pop("id")),
        ("メンバー id 空", lambda d: d["members"][0].update(id="")),
        ("メンバー id null", lambda d: d["members"][0].update(id=None)),
        ("メンバー id 数値", lambda d: d["members"][0].update(id=5)),
        ("メンバー id 重複", lambda d: d["members"][1].update(id=d["members"][0]["id"])),
        ("セクション id なし", lambda d: d["sections"][0].pop("id")),
        ("セクション id 空", lambda d: d["sections"][0].update(id="")),
        ("セクション id 数値", lambda d: d["sections"][0].update(id=5)),
        ("入れ子のセクション id 重複", lambda d: d["sections"][0]["sections"][0].update(id=d["sections"][0]["id"])),
        ("担当者の member が存在しない", lambda d: d["tasks"][0]["assignees"][0].update(member="zzzzzzzz")),
        ("担当者の member が文字列でない", lambda d: d["tasks"][0]["assignees"][0].update(member=5)),
        ("担当者の member がない", lambda d: d["tasks"][0]["assignees"][0].pop("member")),
        ("担当者に旧キー name", lambda d: d["tasks"][0]["assignees"][0].update(name="鈴木")),
    ]


@pytest.mark.parametrize(("label", "edit"), _bad_id_cases(), ids=[c[0] for c in _bad_id_cases()])
def test_version_2_rejects_bad_ids_and_references(label: str, edit: Callable[[dict], None], tmp_path: Path) -> None:
    path = save_project(ids_project(), tmp_path)
    _rewrite(path, edit)
    with pytest.raises(ValueError):
        load_project(path)


def test_version_2_ignores_the_old_assignee_keys(tmp_path: Path) -> None:
    path = save_project(ids_project(), tmp_path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignee="田中", allocation=0.2))
    assert load_project(path).tasks[0].assignees == [Assignee("鈴木", 0.5)]


@pytest.mark.parametrize("kind", ["task", "member", "section"])
def test_save_rejects_duplicate_ids_and_leaves_the_file(kind: str, tmp_path: Path) -> None:
    good = save_project(Project("p"), tmp_path)
    before = good.read_text(encoding="utf-8")
    project = Project("p")
    if kind == "task":
        project.tasks = [Task("a", id="same"), Task("b", id="same")]
    elif kind == "member":
        project.members = [Member("田中", id="same"), Member("鈴木", id="same")]
    else:
        project.sections = [Section("a", id="same"), Section("b", sections=[Section("c", id="same")], id="other")]
    with pytest.raises(ValueError, match="重複"):
        save_project(project, tmp_path)
    assert good.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["p.json"]  # 一時ファイルも残さない
```

既存の `test_saved_file_starts_with_the_format_version` の `assert raw["version"] == FORMAT_VERSION == 1` を `== FORMAT_VERSION == 2` に直す。

`pytest.MonkeyPatch` を使うので、`test_storage.py` の先頭に `import pytest` があることを確かめる(既にある)。`Callable` は `from collections.abc import Callable` で import 済み。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_storage.py -k "version_2 or ids or id_ or save_adds or duplicate_named or dropped or blank_named or renamed_member or format_version"`
Expected: FAIL(`version` が 1 のまま・メンバーに id が保存されない・重複 id を保存できる、など)。

- [ ] **Step 3: モデルの版を上げる**

`src/projectapp/models.py`: `FORMAT_VERSION = 1  # …` を次に置き換える。

```python
FORMAT_VERSION = 2  # プロジェクトファイルの形式のバージョン。キーのない古いファイルは 1 として読む(2: メンバーとセクションの id、担当者はメンバー id で指す)
```

- [ ] **Step 4: 保存を実装する**

`src/projectapp/storage.py`:

import を直す。`from dataclasses import asdict, replace` → `from dataclasses import asdict, dataclass, field, replace`。`from collections.abc import Iterator` を足す(標準ライブラリの import の並びに合わせる)。`from projectapp.models import (` の中に `walk_sections,` を足す(`new_id` は既にある)。

`_encode` の下に足す。

```python
def _task_dicts(tasks: list[dict[str, Any]], sections: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    yield from tasks
    for section in sections:
        yield from _task_dicts(section["tasks"], section["sections"])


def _check_unique_ids(project: Project) -> None:
    """タスク同士・メンバー同士・セクション同士の id の重複があれば ValueError(読めないファイルを書かない)。"""
    groups = {
        "タスク": [t.id for t in project.all_tasks()],
        "メンバー": [m.id for m in project.members],
        "セクション": [s.id for _, s in walk_sections(project.sections)],
    }
    for label, ids in groups.items():
        if len(set(ids)) != len(ids):
            raise ValueError(f"{label}の id が重複しています")


def _dump(project: Project) -> dict[str, Any]:
    """ファイルに書く辞書。担当者は名前ではなくメンバー id で指す。メンバーにいない名前は、メンバーを補う(実行時のプロジェクトは変えない)。"""
    data: dict[str, Any] = {"version": FORMAT_VERSION, **asdict(project)}
    ids: dict[str, str] = {}
    for member in data["members"]:
        ids.setdefault(member["name"], member["id"])  # 同名は最初の 1 件を指す(読込が残すのも最初の 1 件)
    taken = project.used_ids()
    for task in _task_dicts(data["tasks"], data["sections"]):
        refs = []
        for assignee in task["assignees"]:
            name = assignee["name"]
            if name not in ids:
                ids[name] = new_id(taken)
                taken.add(ids[name])
                data["members"].append({"name": name, "ratio": 1.0, "levels": {}, "id": ids[name]})
            refs.append({"member": ids[name], "allocation": assignee["allocation"]})
        task["assignees"] = refs
    return data
```

`save_project` の `data = json.dumps({"version": FORMAT_VERSION, **asdict(project)}, ensure_ascii=False, indent=2, default=_encode)` を置き換え、`validate_name` の検査の後に重複の検査を足す。

```python
    if error := validate_name(name, base_dir, new=False):
        raise ValueError(error)
    _check_unique_ids(project)
    data = json.dumps(_dump(project), ensure_ascii=False, indent=2, default=_encode)
```

- [ ] **Step 5: 読込を実装する**

`src/projectapp/storage.py`:

(a) `_check_version` が版を返すようにする(`-> int`、`"version" not in raw` のとき `return 1`、末尾で `return version`)。

```python
def _check_version(raw: dict[str, Any]) -> int:
    """形式のバージョンを確かめて返す。キーがない古いファイルは 1。整数でない・1 未満・このアプリより新しいものは ValueError。"""
    if "version" not in raw:
        return 1
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError(f"version が正しくありません: {version!r}")
    if version > FORMAT_VERSION:
        raise ValueError(f"このアプリより新しい形式です(version {version})。アプリを更新してください")
    return version
```

(b) `_check_version` の上に文脈を足す。

```python
@dataclass
class _Context:
    """読込の途中で持ち回るもの。version 2 の担当者の解決と、id の重複・振り直しに使う。"""

    version: int
    member_names: dict[str, str] = field(default_factory=dict)  # version 2: メンバー id → 名前(名前が空のメンバーは入れない)
    section_ids: set[str] = field(default_factory=set)
    pending: list[Task] = field(default_factory=list)  # id のないタスク(古いファイル)。読込の最後に id を振る


def _entity_id(value: Any, label: str) -> str:
    """version 2 のメンバー・セクションの id。空・文字列以外は ValueError。"""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}の id が正しくありません: {value!r}")
    return value
```

(c) `_task(raw)` を `_task(raw: dict[str, Any], ctx: _Context)` にし、`assignees=_assignees(raw)` を `assignees=_assignees(raw, ctx)` にし、末尾の `return _checkpoint(task) if kind is TaskKind.CHECKPOINT else task` を置き換える。

```python
    result = _checkpoint(task) if kind is TaskKind.CHECKPOINT else task
    if raw.get("id") is None:
        ctx.pending.append(result)  # 読込の最後に、ファイルの他の id と重ならない id を振る
    return result
```

(d) `_assignees(raw)` を `_assignees(raw: dict[str, Any], ctx: _Context)` にし、先頭(docstring の下)に version 2 の分岐を足す。

```python
    if ctx.version >= 2:
        return _member_assignees(raw.get("assignees"), ctx.member_names)
```

`_assignees` の上に足す。

```python
def _member_assignees(value: Any, names: dict[str, str]) -> list[Assignee]:
    """version 2 の担当者。`member` はメンバーの id。名前の取り違えを避けるため、旧キー `name` は拒否する。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("担当者が配列ではありません")
    assignees: list[Assignee] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or "name" in item:
            raise ValueError("担当者の形式が正しくありません")
        member = item.get("member")
        if not isinstance(member, str) or member not in names:
            raise ValueError(f"担当者のメンバーが見つかりません: {member!r}")
        name = names[member]
        if name in seen:
            raise ValueError(f"担当者が重複しています: {name}")
        seen.add(name)
        assignees.append(Assignee(name, _allocation(item.get("allocation", 1.0))))
    return assignees
```

(e) `_section(raw, depth)` を `_section(raw, depth, ctx)` にし、再帰の呼び出しにも `ctx` を渡す。末尾の `return Section(...)` を置き換える。

```python
    section_id = None
    if ctx.version >= 2:
        section_id = _entity_id(raw.get("id"), "セクション")
        if section_id in ctx.section_ids:
            raise ValueError(f"セクションの id が重複しています: {section_id}")
        ctx.section_ids.add(section_id)
    section = Section(
        raw["name"], [_task(t, ctx) for t in raw["tasks"]], [_section(c, depth + 1, ctx) for c in children]
    )
    if section_id is not None:
        section.id = section_id
    return section
```

(f) `_members(raw_members)` を `_members(raw_members, ctx)` にする。ループを置き換える。

```python
    members: list[Member] = []
    seen: set[str] = set()
    ids: set[str] = set()
    for raw in raw_members:
        name = str(raw["name"]).strip()
        ratio = _number_in_range(raw.get("ratio", 1.0), MIN_RATIO, MAX_RATIO, "相対比率")
        levels = _member_levels(raw.get("levels"))
        member_id = None
        if ctx.version >= 2:
            member_id = _entity_id(raw.get("id"), "メンバー")
            if member_id in ids:
                raise ValueError(f"メンバーの id が重複しています: {member_id}")
            ids.add(member_id)
            if name:
                ctx.member_names[member_id] = name  # 捨てる同名のメンバーを指す担当者も、名前で残ったメンバーへ読める
        if not name or name in seen:
            continue
        seen.add(name)
        member = Member(name, ratio, levels)
        if member_id is not None:
            member.id = member_id
        members.append(member)
    return members
```

(g) `_members` の下に、id の振り直しを足す。

```python
def _assign_ids(project: Project, ctx: _Context) -> None:
    """古いファイルに id を振る。version 1 のメンバー・セクションと、id のないタスク。ファイルにある他の id と重ならないようにする。"""
    pending = {id(task) for task in ctx.pending}
    taken = {t.id for t in project.all_tasks() if id(t) not in pending}
    targets: list[Task | Member | Section] = list(ctx.pending)
    sections = [s for _, s in walk_sections(project.sections)]
    if ctx.version < 2:
        targets += [*project.members, *sections]
    else:
        taken |= {m.id for m in project.members} | {s.id for s in sections}
    for target in targets:
        target.id = new_id(taken)
        taken.add(target.id)
```

(h) `load_project` を置き換える。

```python
def load_project(path: Path) -> Project:
    raw = json.loads(path.read_text(encoding="utf-8"))
    ctx = _Context(_check_version(raw))
    members = _members(raw["members"], ctx)  # version 2 の担当者の解決に要るので、タスクより先に読む
    sections = [_section(s, 1, ctx) for s in raw["sections"]]
    project = Project(
        name=path.stem,
        base_date=date.fromisoformat(raw["base_date"]),
        daily_hours=_daily_hours(raw["daily_hours"]),
        work_start=_work_start(raw.get("work_start", "09:00:00")),
        members=members,
        sections=sections,
        tasks=[_task(t, ctx) for t in raw.get("tasks", [])],
        actual_mode=_actual_mode(raw.get("actual_mode", "simple")),
        url_templates=_url_templates(raw.get("url_templates")),
        parameters=_parameters(raw.get("parameters")),
    )
    known = {m.name for m in project.members}
    for task in project.all_tasks():  # 古いファイルの自由入力の担当者を、メンバーとして補う
        for assignee in task.assignees:
            if assignee.name not in known:
                known.add(assignee.name)
                project.members.append(Member(assignee.name, 1.0))
    _assign_ids(project, ctx)
    validate_links(project.all_tasks())
    for task in project.all_tasks():
        validate_urls(task.urls, project.url_templates)
    return project
```

- [ ] **Step 6: 通ることを確かめる**

Run: `uv run pytest -q test/test_storage.py`
Expected: 追加したテストは PASS。**既存のテストのうち失敗するものは、次の 2 種類だけのはず**。失敗が出たら、原因で直す。

- A. version 1 のファイルを真似るために、保存した version 2 のファイルから担当者のキーを `assignee`/`allocation` に書き換えているテスト(`test_assignee_whitespace_is_trimmed_and_blank_becomes_none`、`test_old_keys_load_as_one_assignee`、`test_old_keys_with_a_bad_allocation_are_rejected_even_without_an_assignee` など): 書き換える関数の先頭で `data.pop("version")` を足し、version 1 として読ませる。
- B. 保存した担当者の形を `{"name": …}` で検査しているテスト(`test_assignees_roundtrip` の `raw["tasks"][0]["assignees"] == [{"name": …}]`): `{"member": <メンバーid>, "allocation": …}` の形に直す(メンバー id は `project.members[i].id`)。

`test_assignees_win_over_the_old_keys` と、`assignees` の不正な形を検査するテスト(`d["tasks"][0].update(assignees=bad)` など)は、version 2 でも `ValueError` になるので、そのまま通るはず。通らなければ原因を調べる。

Run: `uv run pytest -q -n auto && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`(他のテストファイルが担当者の保存形式を直接見ていれば、同じ A/B で直す)。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test/test_storage.py
git commit -m "feat: ファイル形式を version 2 にし、メンバーとセクションの id と、担当者のメンバー id 参照を保存する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面側(メンバーのダイアログ・セクション追加・新規タスク・行のコピー)

**Files:**
- Modify: `src/projectapp/forms.py`(`MemberRow`、`build_members`、`open_members_dialog`、import)
- Modify: `src/projectapp/views.py`(`open_members`、`save_section`、`save_subsection`、`save_task`、import)
- Modify: `src/projectapp/arrange.py`(`copy_task`)
- Test: `test/test_forms.py`、`test/test_arrange.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `new_id(taken)`、`Member.id`、`Section.id`、`Project.used_ids()`。
- Produces: `MemberRow.id: str | None = None`(最後のフィールド)、`build_members(rows, originals, assigned, parameters=None, taken=())`、`open_members_dialog(members, assigned, on_apply, parameters=None, taken=())`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の末尾に足す(import: `import projectapp.models as models` を足す。`MemberRow`・`build_members` は import 済み)。

```python
def test_build_members_keeps_the_id_of_a_renamed_row() -> None:
    members, renames = build_members([MemberRow("田中", "田中二郎", 100.0, id="m1")], ["田中"], lambda name: 0)
    assert [(m.name, m.id) for m in members] == [("田中二郎", "m1")]
    assert renames == {"田中": "田中二郎"}


def test_build_members_keeps_each_rows_id_when_names_are_swapped() -> None:
    rows = [MemberRow("A", "B", 100.0, id="ida"), MemberRow("B", "A", 100.0, id="idb")]
    members, _ = build_members(rows, ["A", "B"], lambda name: 0)
    assert [(m.name, m.id) for m in members] == [("B", "ida"), ("A", "idb")]


def test_build_members_gives_a_new_row_an_id_that_is_not_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter(["aaaaaaaa", "bbbbbbbb", "cccccccc"])
    monkeypatch.setattr(models.secrets, "token_hex", lambda nbytes: next(values))
    rows = [MemberRow(None, "田中", 100.0), MemberRow(None, "鈴木", 100.0)]
    members, _ = build_members(rows, [], lambda name: 0, taken={"aaaaaaaa"})
    assert [m.id for m in members] == ["bbbbbbbb", "cccccccc"]


def test_a_deleted_and_re_added_member_gets_a_new_id() -> None:
    old = MemberRow("田中", "田中", 100.0, id="old")
    members, _ = build_members([MemberRow(None, "田中", 100.0)], ["田中"], lambda name: 0, taken={"old"})
    assert members[0].id != "old"
    assert old.id == "old"
```

`test_a_deleted_and_re_added_member_gets_a_new_id` は、`assigned` が 0 を返すので削除が許される。`import pytest` が `test_forms.py` にあることを確かめる(なければ足す)。

`test/test_arrange.py` の末尾に足す。

```python
def test_copy_gets_an_id_that_is_not_used_in_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    import projectapp.models as models

    project = sample()
    taken = project.used_ids()
    clash = next(iter(taken))
    values = iter([clash, "zzzzzzzz"])
    monkeypatch.setattr(models.secrets, "token_hex", lambda nbytes: next(values))
    copy = arrange.copy_task(project, ((), 0), ((), 1))
    assert copy.id == "zzzzzzzz"
```

`test/test_views.py` の末尾に足す(`test_save_task_adds_then_replaces` と同じ作り方)。

```python
async def test_new_sections_and_tasks_get_ids_that_are_not_used(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []

    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, make_transport(200, []))
        views.append(view)
        view.build()

    await user.open("/")
    view = views[0]
    view.save_section("A")
    view.save_subsection((0,), "A-1")
    clash = Task("x", id=view.project.sections[0].id)  # セクションと同じ id のタスク
    view.save_task((0,), None, clash)
    assert clash.id != view.project.sections[0].id
    ids = view.project.used_ids()
    assert len(ids) == 3
    assert len(view.project.sections[0].id) == 8 and len(view.project.sections[0].sections[0].id) == 8
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_forms.py test/test_arrange.py test/test_views.py -k "build_members or copy_gets or new_sections"`
Expected: FAIL(`MemberRow` に `id` がない、`build_members` に `taken` がない、など)。

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py`:

1. `from collections.abc import Awaitable, Callable` → `from collections.abc import Awaitable, Callable, Collection`
2. `from projectapp.models import (` の中に `new_id,` を足す(`is_hex_color,` の下)。
3. `MemberRow` の最後のフィールドの下に足し、docstring の「originalは…」の後に id の説明を足す。

```python
    id: str | None = None  # 開いた時点のメンバーの id。新しい行は None(適用で新しい id を振る)
```

4. `build_members` の引数に `taken: Collection[str] = ()` を足す(`parameters` の下)。`seen: set[str] = set()` の下に `used = set(taken)` を足し、`members.append(Member(name, round(ratio / 100, 4), levels))` を置き換える。

```python
        member_id = row.id or new_id(used)
        used.add(member_id)
        members.append(Member(name, round(ratio / 100, 4), levels, member_id))
```

docstring に「`taken` は、プロジェクトにある id(新しい行の id がこれと重ならない)」を足す。

5. `open_members_dialog` の引数に `taken: Collection[str] = ()` を足す(`parameters` の下)。`rows = [...]` を置き換える。

```python
    rows = [MemberRow(m.name, m.name, round(m.ratio * 100, 2), dict(m.levels), m.id) for m in members]
```

`apply` の中の `build_members(rows, originals, assigned, chosen_parameters)` を `build_members(rows, originals, assigned, chosen_parameters, taken)` にする。

`src/projectapp/views.py`:

1. `from projectapp.models import MAX_SECTION_DEPTH, ActualMode, Member, Project, Section, SectionPath, Task` に `new_id` を足す。
2. `open_members` の `open_members_dialog(...)` の最後の引数に `self.project.used_ids()` を足す(`self.project.parameters` の次)。
3. `save_section`: `self.project.sections.append(Section(name))` → `self.project.sections.append(Section(name, id=new_id(self.project.used_ids())))`
4. `save_subsection`: `parent.sections.append(Section(name))` → `parent.sections.append(Section(name, id=new_id(self.project.used_ids())))`
5. `save_task` の `if task_index is None: tasks.append(task)` を置き換える。

```python
        if task_index is None:
            if task.id in self.project.used_ids():
                task.id = new_id(self.project.used_ids())  # 他のタスク・メンバー・セクションと同じ id にならないように
            tasks.append(task)
```

`src/projectapp/arrange.py`:

`copy_task` の `id=new_id(),` を `id=new_id(project.used_ids()),` にする。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py src/projectapp/arrange.py test/test_forms.py test/test_arrange.py test/test_views.py
git commit -m "feat: メンバーのダイアログが id を引き継ぎ、新しいセクション・タスク・コピーに既存と重ならない id を振る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ドキュメントと実機確認

**Files:**
- Modify: `docs/development.md`(「ファイル形式の注意」)
- Modify: `CLAUDE.md`(projectapp のもの。「実装上の注意」の `version` の行)
- Modify: `.claude/MEMORY.md`(提案2の記録。git 管理外なら省く)

- [ ] **Step 1: `docs/development.md` を直す**

「ファイル形式の注意」の先頭の `version` の項目(`- 形式のバージョンは先頭の \`version\`…`)を次に置き換える。

```markdown
- 形式のバージョンは先頭の `version`(整数。`models.FORMAT_VERSION`、現在 2)。キーのない古いファイルは 1 として読む。整数でない値(`true`・小数・文字列・`null`)と 1 未満は読込を拒否し、このアプリより新しい値は「アプリを更新してください」で拒否する(`storage._check_version`)。形式を変える(キーの意味を変える・消す)ときは `FORMAT_VERSION` を上げ、旧形式の読み替えはバージョンで分ける。
- version 2(2026-10-10): `members[].id` と `sections[].id`(`new_id()` の 8 桁の 16 進。入れ子のセクションも)を保存し、担当者は `tasks[].assignees[]` の `{"member": <メンバーid>, "allocation": …}` で指す(`name` は書かない。`_dump`)。実行時の `Assignee` は名前のまま(読込が id から名前へ戻す。`_member_assignees`)。読込は、`id` の欠落・`null`・空・文字列以外・重複(メンバー同士・セクション同士)、存在しない/文字列でない `member`、担当者の旧キー `name` を拒否する。名前が空・重複のメンバーは最初の 1 件を残して捨てるが、捨てた同名のメンバーの id を指す担当者は、残ったメンバーへ読む(名前が空のメンバーの id を指すものは拒否)。version 1(キーなしを含む)は、メンバー・セクションと id のないタスクに読込の最後に新しい id を振る(`_assign_ids`。ファイルの他の id と重ならない)。保存し直すと version 2 になる。
- 保存(`save_project`)は、タスク同士・メンバー同士・セクション同士の id の重複を `ValueError` にして、ファイルを書かない(読めないファイルを作らない)。担当者の名前がメンバーにいなければ、保存するファイルにだけメンバー(比率 100%)を補う(読込の補完と同じ。実行時のプロジェクトは変えない)。新しい id は `new_id(project.used_ids())` で振る(セクションの追加・新規タスク・行のコピー・メンバーのダイアログの新しい行)。メンバーのダイアログは `MemberRow.id` で行の id を引き継ぐ(改名・並べ替えでは変わらない。行を消して足し直すと新しくなる)。
```

- [ ] **Step 2: `CLAUDE.md` を直す**

「実装上の注意」の `version` の行を次に置き換える。

```markdown
- プロジェクトファイルの先頭に`version`(整数。現在 2)を保存する。キーのない古いファイルは 1 として読み、このアプリより新しい`version`は読込を拒否する。メンバーとセクションは安定した`id`を持ち、担当者はファイルではメンバーの`id`で指す
```

- [ ] **Step 3: 全体を確かめて実機で確認する**

Run: `uv run pytest -q -n auto && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`。

実機(`uv run projectapp`)で次を確認する(ユーザーに依頼する。自動テストでは確かめられない)。
1. `~/.projectapp` の既存のファイル(version なし)を開き、保存して、ファイルの先頭が `"version": 2` で、メンバーとセクションに `id` があり、担当者が `member` になっていること。
2. メンバーのダイアログで名前を変えて適用し、保存し直しても、そのメンバーの `id` が同じこと。担当者のタスクの担当が変わらないこと。
3. 保存したファイルを開き直して、担当者のチップ・割り当て・書き出しが保存前と同じこと。

- [ ] **Step 4: コミット**

```bash
git add docs/development.md CLAUDE.md
git commit -m "docs: ファイル形式 version 2(メンバーとセクションの id)を書く

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** モデルの `id`・`new_id(taken)`・`used_ids` は Task 1。version 2 の形式・読込のルール(拒否、重複メンバー、version 1 の id 振り)・保存の重複検査は Task 2。メンバーのダイアログ、セクション追加、新規タスク、行のコピーの一意化は Task 3。ドキュメントは Task 4。範囲外の項目(実行時の id 化・`handoff.py`・パラメータ/段階/テンプレート・シリアライズ層の統合)は、どのタスクも触れない。

**設計書との差:** 設計書にない決定が 2 つある。(1) 保存時、担当者の名前がメンバーにいなければ、ファイルにだけメンバーを補う(`_dump`)。読込が同じ補完をしており、実行時のプロジェクトが保存で変わらず、既存の「名前だけの担当者を保存して読むとメンバーが増える」テストが成り立つため。(2) 名前が空のメンバーの id を指す担当者は拒否する(設計書は未定)。設計書にこの 2 点を後で追記する(Task 4 のドキュメントの記述に含めた)。

**型の一貫性:** `new_id(taken: Collection[str] = ())`、`MemberRow.id`、`build_members(..., taken)`、`open_members_dialog(..., taken)`、`_Context`(`version`・`member_names`・`section_ids`・`pending`)、`_assign_ids(project, ctx)`、`_dump`・`_check_unique_ids`・`_member_assignees` は、各タスクで同じ名前と引数で使っている。
