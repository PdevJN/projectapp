# インラインセクション(セクションの入れ子) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** セクションの中にサブセクションを置けるようにする(セクションを最大 3 階層。root は数えない)。タスクは root と、どの階層のセクションにも置ける。インデントして同じ画面に並べる。

**Architecture:** `Section.sections`(入れ子)を足し、セクションの位置を番号のパス(`SectionPath = tuple[int, ...]`。root は `()`)で表す。マーカーのキーは、パスを「.」でつないだ文字列(`top`・`0`・`0.1`)で、1 階層目は今のまま。まず、データと保存、位置の純粋関数、行の並びの純粋関数を作り、そのあとガントチャートと画面を再帰に直す。パスへの移行は、移行用の変換 `as_path`(`None`・整数・タプル → パス)を置いて、全体が動いたまま進め、最後に消す。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -q -n auto`)、`uvx ty check src`、node(JS の動作テスト)。

**Spec:** `docs/superpowers/specs/2026-10-09-nested-sections-design.md`

## Global Constraints

- 言語は日本語。コメント・テスト名・コミットメッセージも日本語(識別子は英語)。コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- Python 3.13 以上、NiceGUI。描画は NiceGUI の要素と CSS による自前描画(外部のガントライブラリは使わない)。
- 位置や行の並びの計算は、NiceGUI から切り離した純粋関数にする(`arrange.py`・`links.py`・`filtering.py`)。
- ファイル形式を変えるときは、キーのない古いファイルを既定値で読み(移行を要らなくする)、不正な値は読込を拒否する。
- セクションは最大 3 階層(`MAX_SECTION_DEPTH = 3`。root 直下が 1 階層目)。セクション自体の改名・削除・移動、タスクとサブセクションの混在、4 階層目以降は作らない。
- 1 階層目のセクションと root のマーカー(`task-0-0`・`section-0`・`task-top-0` など)は、今のまま変えない。
- 描画の要素数を増やさない(要望 24)。増えるのは、サブセクションの見出しと、その追加ボタンだけ。
- テストは `uv run pytest -q -n auto`(全体で約 15 秒)。型は `uvx ty check src`。各タスクの最後に、全体のテストが通ることを確かめる。
- 実機確認(ネイティブ: `uv run projectapp`)の前に、PR・マージはしない。`develop` へのプッシュは、許可を得てから行う。

## Review Focus

- 深さの上限: 4 階層目は、読込で拒否する。画面では 3 階層目のセクションに「サブセクション追加」を出さない。`save_subsection` は 3 階層目の親を拒否する。→ Task 1・5 のテスト。
- 折りたたみ: 親を閉じると子孫がすべて隠れ、親を開いても子の閉じた状態が保たれる。タスクやサブセクションを足すと、そのセクションと親すべてが開く。絞り込み中は、閉じていても一致するものが出る。→ Task 3・4・5 のテスト。
- キーの形式: `parse_section_key` が、空・`0.`・`.0`・`-1`・`01`・`0.0.0.0`・`top.1`・空白つき・全角数字を拒否する。→ Task 2 のテスト。
- ドラッグの移動・コピー: 見出しに落とすと、そのセクション自身のタスクの末尾(サブセクションの前)に入る。同じ一覧での位置の補正。入れ子のセクションへの移動と、親から子への移動。→ Task 2・4 のテスト。
- 古いファイル(`sections` のキーがないセクション)と、見出しのタスク数(サブセクションなしは今のまま)、先行タスクの候補の表示(`親 / 子 / タスク`)。→ Task 1・3 のテスト。

---

## File Structure

| ファイル | 役割 | 変更 |
|---|---|---|
| `src/projectapp/models.py` | `Section.sections`、`SectionPath`、`MAX_SECTION_DEPTH`、`walk_sections`、`all_tasks` の再帰 | Task 1 |
| `src/projectapp/storage.py` | 入れ子の保存・読込、深さの拒否 | Task 1 |
| `src/projectapp/arrange.py` | パスの関数(`section_at`・`tasks_at`・`section_key`・`parse_section_key`・`as_path`)、移動・コピー・パース | Task 2 |
| `src/projectapp/filtering.py`・`links.py`・`linkgraph.py`・`timeline.py` | 入れ子の行の並び、絞り込み、先行タスクの候補、表示範囲 | Task 3 |
| `src/projectapp/gantt.py` | 入れ子の描画、インデント、折りたたみ、タスク数、サブセクション追加のボタン | Task 4・5 |
| `src/projectapp/views.py` | パスで動く操作、サブセクションの追加 | Task 4・5 |
| `src/projectapp/gantt_drag.py` | ドラッグの JS がセクションのキーを文字列で送る | Task 5 |
| `src/projectapp/forms.py` | `open_section_dialog` のタイトル | Task 5 |
| `CLAUDE.md`・`docs/development.md`・`.claude/MEMORY.md` | 文書 | Task 6 |

---

### Task 1: 入れ子のデータと保存・読込(`models.py`・`storage.py`)

**Files:**
- Modify: `src/projectapp/models.py`(`Section`・`Project.all_tasks`・`SectionPath`・`MAX_SECTION_DEPTH`・`walk_sections`)
- Modify: `src/projectapp/storage.py`(`load_project` の `sections`)
- Test: `test/test_storage.py`、`test/test_models.py`(なければ新規)

**Interfaces:**
- Produces:
  - `SectionPath = tuple[int, ...]`(root は `()`)
  - `MAX_SECTION_DEPTH = 3`
  - `Section.sections: list[Section]`、`Section.all_tasks() -> list[Task]`(自分のタスク → サブセクション)
  - `walk_sections(sections: list[Section], prefix: SectionPath = ()) -> Iterator[tuple[SectionPath, Section]]`(深さ優先)
  - `Project.all_tasks()`: root のタスク → 各セクションを深さ優先

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の `from projectapp.models import (...)` に何も足さずに済む(`Section`・`Task` は import 済み)。末尾に足す:

```python
def nested_sections() -> list[Section]:
    deep = Section("孫", [Task("孫タスク")])
    child = Section("子", [Task("子タスク")], [deep])
    return [Section("親", [Task("親タスク")], [child, Section("子2", [Task("子2タスク")])]), Section("別", [Task("別タスク")])]


def test_nested_sections_roundtrip(tmp_path: Path) -> None:
    project = Project("p", tasks=[Task("root")], sections=nested_sections())
    path = save_project(project, tmp_path)
    loaded = load_project(path)
    assert loaded.sections == project.sections
    assert [t.name for t in loaded.all_tasks()] == ["root", "親タスク", "子タスク", "孫タスク", "子2タスク", "別タスク"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["sections"][0]["sections"][0]["sections"][0]["name"] == "孫"


def test_a_file_without_nested_sections_loads_as_flat(tmp_path: Path) -> None:
    path = save_project(Project("p", sections=[Section("A", [Task("a")])]), tmp_path)

    def legacy(data: dict) -> None:
        data["sections"][0].pop("sections")

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert loaded.sections == [Section("A", [Task("a")])]
    _rewrite(path, lambda d: d["sections"][0].update(sections=None))
    assert load_project(path).sections[0].sections == []


def test_four_levels_of_sections_are_rejected(tmp_path: Path) -> None:
    four = Section("1", sections=[Section("2", sections=[Section("3", sections=[Section("4")])])])
    path = save_project(Project("p", sections=[four]), tmp_path)
    with pytest.raises(ValueError, match="3階層"):
        load_project(path)


def test_three_levels_of_sections_are_accepted(tmp_path: Path) -> None:
    three = Section("1", sections=[Section("2", sections=[Section("3")])])
    loaded = load_project(save_project(Project("p", sections=[three]), tmp_path))
    assert loaded.sections[0].sections[0].sections[0].name == "3"


@pytest.mark.parametrize("bad", ["子", ["子"], [3], [None]])
def test_bad_nested_sections_are_rejected(bad: object, tmp_path: Path) -> None:
    path = save_project(Project("p", sections=[Section("A")]), tmp_path)
    _rewrite(path, lambda d: d["sections"][0].update(sections=bad))
    with pytest.raises(ValueError):
        load_project(path)
```

`test/test_models.py`(新規。すでにあれば末尾に足す):

```python
"""モデルの小さな規則(セクションの入れ子)。"""

from projectapp.models import Project, Section, Task, walk_sections


def tree() -> Project:
    deep = Section("孫", [Task("g")])
    child = Section("子", [Task("c")], [deep])
    return Project("p", tasks=[Task("r")], sections=[Section("親", [Task("p1")], [child, Section("子2", [Task("c2")])]), Section("別", [Task("o")])])


def test_all_tasks_runs_depth_first_after_the_root_tasks() -> None:
    assert [t.name for t in tree().all_tasks()] == ["r", "p1", "c", "g", "c2", "o"]


def test_a_section_lists_its_own_and_its_descendants_tasks() -> None:
    parent = tree().sections[0]
    assert [t.name for t in parent.all_tasks()] == ["p1", "c", "g", "c2"]
    assert [t.name for t in parent.sections[0].all_tasks()] == ["c", "g"]


def test_walk_sections_yields_paths_depth_first() -> None:
    paths = [(path, section.name) for path, section in walk_sections(tree().sections)]
    assert paths == [((0,), "親"), ((0, 0), "子"), ((0, 0, 0), "孫"), ((0, 1), "子2"), ((1,), "別")]


def test_a_flat_project_is_unchanged() -> None:
    project = Project("p", tasks=[Task("r")], sections=[Section("A", [Task("a")])])
    assert [t.name for t in project.all_tasks()] == ["r", "a"]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_models.py test/test_storage.py -q -k "nested or section or all_tasks or walk or flat or levels" 2>&1 | tail -6`
Expected: `ImportError: cannot import name 'walk_sections'`(と、`Section()` が `sections` を受けない `TypeError`)。

- [ ] **Step 3: `models.py` を直す**

`MIN_RATIO, MAX_RATIO = …` の定数の並びに足す:

```python
MAX_SECTION_DEPTH = 3  # セクションの入れ子の上限(root 直下が 1 階層目。root は数えない)
SectionPath = tuple[int, ...]  # セクションの位置。root は ()、1 番目のセクションは (0,)、その 2 番目のサブセクションは (0, 1)
```
(`from collections.abc import Iterator` を import に足す。)`Section` を置き換え、その下に `walk_sections` を足す:

```python
@dataclass
class Section:
    name: str
    tasks: list[Task] = field(default_factory=list)
    sections: list["Section"] = field(default_factory=list)  # サブセクション(タスクの後ろに並ぶ)

    def all_tasks(self) -> list[Task]:
        """このセクションのタスク、続いてサブセクションのタスク(深さ優先)。"""
        tasks = list(self.tasks)
        for child in self.sections:
            tasks += child.all_tasks()
        return tasks


def walk_sections(sections: list[Section], prefix: SectionPath = ()) -> Iterator[tuple[SectionPath, Section]]:
    """セクションを深さ優先でたどる(親 → その子孫 → 次の兄弟)。パスは root からの番号の並び。"""
    for index, section in enumerate(sections):
        path = (*prefix, index)
        yield path, section
        yield from walk_sections(section.sections, path)
```
`Project.all_tasks` を置き換える:

```python
    def all_tasks(self) -> list[Task]:
        """セクションなしのタスク、続いて各セクションを深さ優先で(そのタスク → そのサブセクション)。"""
        tasks = list(self.tasks)
        for section in self.sections:
            tasks += section.all_tasks()
        return tasks
```

- [ ] **Step 4: `storage.py` を直す**

`from projectapp.models import (...)` に `MAX_SECTION_DEPTH` を足す。`_members` の上(または `_task` の近く)に足す:

```python
def _section(raw: Any, depth: int) -> Section:
    """セクションを読む(入れ子)。depth は 1 階層目が 1。上限を超えたら ValueError。"""
    if depth > MAX_SECTION_DEPTH:
        raise ValueError(f"セクションは{MAX_SECTION_DEPTH}階層までです")
    if not isinstance(raw, dict):
        raise ValueError("セクションの形式が正しくありません")
    children = raw.get("sections")
    if children is None:
        children = []
    if not isinstance(children, list):
        raise ValueError("サブセクションがリストではありません")
    return Section(raw["name"], [_task(t) for t in raw["tasks"]], [_section(c, depth + 1) for c in children])
```
`load_project` の `sections = [Section(s["name"], [_task(t) for t in s["tasks"]]) for s in raw["sections"]]` を `sections = [_section(s, 1) for s in raw["sections"]]` にする。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: セクションの入れ子のデータを、保存・読込できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: セクションのパスの関数と、移動・コピー・パース(`arrange.py`)

**Files:**
- Modify: `src/projectapp/arrange.py`
- Test: `test/test_arrange.py`、`test/test_gantt_drag.py`(パース関係の期待値の更新)

**Interfaces:**
- Consumes: `SectionPath`・`MAX_SECTION_DEPTH`(Task 1)。
- Produces:
  - `Position = tuple[SectionPath, int]`
  - `as_path(section: object) -> SectionPath`(移行用。`None` → `()`、整数 → `(n,)`、タプル → そのまま。Task 6 で消す)
  - `section_at(project, path) -> Section | None`(`path == ()` と範囲外は None)
  - `section_key(path) -> str`、`parse_section_key(text) -> SectionPath | None`
  - `tasks_at(project, section) -> list[Task]`・`valid_section`・`has_task`・`has_list`・`move_task`・`copy_task`: セクションの引数は `as_path` を通す。
  - `parse_position`・`parse_move`・`parse_shift`: セクションの指定に、`None`(root)・整数・キーの文字列(`top`・`0`・`0.1`)を受け、`SectionPath` を返す。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_arrange.py` の末尾に足す(`Project`・`Section`・`Task`・`arrange` は import 済み。`pytest` が未 import なら足す):

```python
def tree() -> Project:
    deep = Section("孫", [Task("g")])
    child = Section("子", [Task("c1"), Task("c2")], [deep])
    return Project("p", tasks=[Task("r0"), Task("r1")], sections=[Section("親", [Task("p0")], [child]), Section("別", [Task("o0")])])


@pytest.mark.parametrize(
    ("path", "found"),
    [((), None), ((0,), "親"), ((0, 0), "子"), ((0, 0, 0), "孫"), ((1,), "別"), ((2,), None), ((0, 1), None), ((-1,), None), ((0, 0, 0, 0), None)],
)
def test_section_at(path: tuple[int, ...], found: str | None) -> None:
    section = arrange.section_at(tree(), path)
    assert (section.name if section else None) == found


def test_tasks_at_returns_the_list_of_the_section() -> None:
    project = tree()
    assert [t.name for t in arrange.tasks_at(project, ())] == ["r0", "r1"]
    assert [t.name for t in arrange.tasks_at(project, (0, 0))] == ["c1", "c2"]
    assert arrange.tasks_at(project, (0, 0, 0)) is project.sections[0].sections[0].sections[0].tasks
    with pytest.raises(IndexError):
        arrange.tasks_at(project, (5,))


@pytest.mark.parametrize(
    ("path", "valid"),
    [((), True), ((0,), True), ((0, 0, 0), True), ((0, 0, 1), False), ((3,), False), ((0, 0, 0, 0), False), ((-1,), False)],
)
def test_valid_section(path: tuple[int, ...], valid: bool) -> None:
    assert arrange.valid_section(tree(), path) is valid


@pytest.mark.parametrize(
    ("path", "key"),
    [((), "top"), ((0,), "0"), ((12,), "12"), ((0, 1), "0.1"), ((3, 0, 2), "3.0.2")],
)
def test_section_key_and_parse_are_inverse(path: tuple[int, ...], key: str) -> None:
    assert arrange.section_key(path) == key
    assert arrange.parse_section_key(key) == path


@pytest.mark.parametrize(
    "bad",
    ["", " ", "0.", ".0", "-1", "01", "0.01", "0.0.0.0", "top.1", "x", "0,1", " 0", "0 ", "１", "0..1", "1e3", "+1"],
)
def test_parse_section_key_rejects_malformed_keys(bad: str) -> None:
    assert arrange.parse_section_key(bad) is None


def test_move_task_into_a_nested_section() -> None:
    project = tree()
    assert arrange.move_task(project, ((), 1), ((0, 0), 1)) is True
    assert [t.name for t in project.tasks] == ["r0"]
    assert [t.name for t in project.sections[0].sections[0].tasks] == ["c1", "r1", "c2"]


def test_move_task_from_a_parent_to_its_child_end() -> None:
    project = tree()
    child_tasks = project.sections[0].sections[0].tasks
    arrange.move_task(project, ((0,), 0), ((0, 0), len(child_tasks)))
    assert [t.name for t in child_tasks] == ["c1", "c2", "p0"]
    assert project.sections[0].tasks == []


def test_moving_inside_one_nested_list_adjusts_the_position() -> None:
    project = tree()
    assert arrange.move_task(project, ((0, 0), 0), ((0, 0), 2)) is True
    assert [t.name for t in project.sections[0].sections[0].tasks] == ["c2", "c1"]
    assert arrange.move_task(project, ((0, 0), 0), ((0, 0), 1)) is False  # 位置が変わらない


def test_copy_task_into_a_deep_section() -> None:
    project = tree()
    copy = arrange.copy_task(project, ((0, 0), 0), ((0, 0, 0), 0))
    assert copy.name == "c1(コピー)"
    assert [t.name for t in project.sections[0].sections[0].sections[0].tasks] == ["c1(コピー)", "g"]
    assert [t.name for t in project.sections[0].sections[0].tasks] == ["c1", "c2"]


def test_has_task_and_has_list_follow_the_path() -> None:
    project = tree()
    assert arrange.has_task(project, ((0, 0), 1)) and not arrange.has_task(project, ((0, 0), 2))
    assert arrange.has_list(project, ((0, 0, 0), 5)) and not arrange.has_list(project, ((0, 0, 1), 0))


def test_parse_position_accepts_keys_integers_and_none() -> None:
    assert arrange.parse_position(["top", 0]) == ((), 0)
    assert arrange.parse_position(["0.1", 5]) == ((0, 1), 5)
    assert arrange.parse_position(["2", 1]) == ((2,), 1)
    assert arrange.parse_position([None, 0]) == ((), 0)
    assert arrange.parse_position([2, 5]) == ((2,), 5)
    for bad in (["0.", 1], ["x", 1], [[0], 1], ["0", "1"], ["0", True], "ab", None):
        assert arrange.parse_position(bad) is None
```

`test/test_arrange.py` の既存の期待値を、新しい形に直す(`parse_position` と `parse_move`・`parse_shift` の返す位置がパスになるため):
- `test_parse_position`(168〜173 行目付近): 1 行目 `== (None, 0)` を `== ((), 0)`、2 行目 `== (2, 5)` を `== ((2,), 5)`、3 行目 `== (1, 0)` を `== ((1,), 0)` にする。
- `test_parse_move`(176〜184 行目付近): `== ((0, 1), (None, 2), True)` を `== (((0,), 1), ((), 2), True)`、`== ((0, 1), (None, 2), False)` を `== (((0,), 1), ((), 2), False)` にする。
- `test_parse_shift_accepts_integers_within_the_limit_only`(187 行目付近): `== ((None, 0), -3)` を `== (((), 0), -3)`、`== ((1, 2), 3650)` を `== (((1,), 2), 3650)` にする。
- `test/test_gantt_drag.py` の 93 行目付近 `assert recorder.events == [("move_task", ((None, 0), (0, 1), True))]` を `[("move_task", (((), 0), ((0,), 1), True))]` に、175 行目付近 `assert recorder.events == [("shift_task", (0, 0, -2)), ("shift_task", (None, 1, 5))]` を `[("shift_task", ((0,), 0, -2)), ("shift_task", ((), 1, 5))]` に直す(`handle_move`・`handle_shift` が、パースしたパスをコールバックへ渡すため)。
- `test/test_gantt_drag.py` の 182 行目付近 `charts[0].handle_shift({"si": "0", "ti": 0, "days": 1})`(「文字列は無視する」という検証)は、`"0"` が正しいキーになるので、不正なキー `{"si": "0.", "ti": 0, "days": 1}` に直す。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_arrange.py -q 2>&1 | tail -6`
Expected: `AttributeError: module 'projectapp.arrange' has no attribute 'section_at'` などで失敗する。

- [ ] **Step 3: `arrange.py` を実装する**

`Position = …` の行を置き換え、その下の `tasks_at`・`valid_section` を置き換える。import に `import re` と、`from projectapp.models import (MAX_SECTION_DEPTH, MAX_YEAR, MIN_YEAR, Project, Section, SectionPath, Task, new_id)` を整える。

```python
Position = tuple[SectionPath, int]  # (セクションのパス。root は (), 番号)
COPY_SUFFIX = "(コピー)"
MAX_SHIFT_DAYS = 3650
_KEY = re.compile(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){0,%d}" % (MAX_SECTION_DEPTH - 1))


def as_path(section: object) -> SectionPath:
    """移行用: None(root)・整数(1 階層目)・タプルを、セクションのパスにそろえる(Task 6 で消す)。"""
    if section is None:
        return ()
    if isinstance(section, int) and not isinstance(section, bool):
        return (section,)
    return tuple(section)  # type: ignore[arg-type]


def section_key(path: SectionPath) -> str:
    """マーカーと `data-si` に使うキー。root は `top`、それ以外は番号を「.」でつなぐ(`0`・`0.1`)。"""
    return ".".join(str(n) for n in path) if path else "top"


def parse_section_key(text: str) -> SectionPath | None:
    """`section_key` の逆。不正(空・先頭の 0・空白・全角・4 階層以上など)は None。"""
    if text == "top":
        return ()
    if not text.isascii() or _KEY.fullmatch(text) is None:
        return None
    return tuple(int(part) for part in text.split("."))


def section_at(project: Project, path: SectionPath) -> Section | None:
    """パスのセクション。root(`()`)と、存在しないパスは None。"""
    sections = project.sections
    found: Section | None = None
    for index in path:
        if not 0 <= index < len(sections):
            return None
        found = sections[index]
        sections = found.sections
    return found


def tasks_at(project: Project, section: object) -> list[Task]:
    path = as_path(section)
    if not path:
        return project.tasks
    found = section_at(project, path)
    if found is None:
        raise IndexError(path)
    return found.tasks


def valid_section(project: Project, section: object) -> bool:
    path = as_path(section)
    return not path or (len(path) <= MAX_SECTION_DEPTH and section_at(project, path) is not None)
```

(`has_task`・`has_list`・`move_task`・`copy_task` は、`tasks_at`・`valid_section` を通すので、本体は変えない。ただし `has_task` の `section, index = position` の `section` は `valid_section(project, section)` と `tasks_at(project, section)` に渡るだけでよい。)

`parse_position` を置き換える:

```python
def parse_section(value: object) -> SectionPath | None:
    """画面から届くセクションの指定。キーの文字列(`top`・`0`・`0.1`)、または None(root)・整数(移行用)。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return parse_section_key(value)
    number = as_int(value)
    return None if number is None else (number,)


def parse_position(value: object) -> Position | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    section, raw_index = value
    index = as_int(raw_index)
    path = parse_section(section)
    if index is None or path is None:
        return None
    return path, index
```
`parse_shift` の `position = parse_position([args.get("si"), args.get("ti")])` は、そのままでよい。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: セクションを番号のパスで表し、入れ子のセクションへの移動・コピーに対応させる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 行の並び・絞り込み・先行タスクの候補・表示範囲(`links.py`・`filtering.py`・`linkgraph.py`・`timeline.py`)

**Files:**
- Modify: `src/projectapp/filtering.py`(`section_has_match`)
- Modify: `src/projectapp/links.py`(`RowSlot`・`row_slots`)
- Modify: `src/projectapp/linkgraph.py`(`link_options`)
- Modify: `src/projectapp/timeline.py`(`visible_range`)
- Test: `test/test_filtering.py`、`test/test_links.py`、`test/test_linkgraph.py`(なければ `test_links.py`)、`test/test_timeline.py`、`test/test_gantt.py`(`slot.si` の参照)

**Interfaces:**
- Consumes: `Section.sections`・`Section.all_tasks`(Task 1)、`as_path`(Task 2)。
- Produces:
  - `filtering.section_has_match(section: Section, task_filter: TaskFilter) -> bool`
  - `RowSlot(kind, path: SectionPath, ti, task_id, shown, height)`(`si` を `path` に改名。root と "top-add" は `()`)
  - `row_slots(project, task_filter, collapsed: set[SectionPath], read_only, row_height, add_height)`
  - `link_options` のラベル: `親 / 子 / タスク`(セクションの名前をすべてつなぐ)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_filtering.py` に足す(`Section`・`Task`・`TaskFilter` は import 済み。`section_has_match` を import する):

```python
def tree_section() -> Section:
    grandchild = Section("孫", [Task("深い")])
    return Section("親", [Task("上")], [Section("子", [Task("中")], [grandchild]), Section("子2", [Task("横")])])


def test_section_has_match_looks_at_the_whole_subtree() -> None:
    parent = tree_section()
    assert section_has_match(parent, TaskFilter(query="深"))  # 孫のタスクで、親も一致
    assert section_has_match(parent.sections[0], TaskFilter(query="深"))
    assert not section_has_match(parent.sections[1], TaskFilter(query="深"))
    assert section_has_match(parent, TaskFilter(query="上"))
    assert not section_has_match(parent, TaskFilter(query="存在しない"))


def test_section_has_match_with_an_inactive_filter_is_true() -> None:
    assert section_has_match(tree_section(), TaskFilter())
    assert section_has_match(Section("空"), TaskFilter())  # 条件がなければ、空のセクションも出す
```

`test/test_links.py`(`row_slots`・`RowSlot` の既存のテストがあるファイル。なければ新規)に足す:

```python
def nested_project() -> Project:
    deep = Section("孫", [Task("g", id="g")])
    child = Section("子", [Task("c", id="c")], [deep])
    return Project("p", tasks=[Task("r", id="r")], sections=[Section("親", [Task("p", id="p")], [child, Section("子2", [Task("c2", id="c2")])]), Section("別", [Task("o", id="o")])])


def summary(slots: list[RowSlot]) -> list[tuple[str, tuple[int, ...], int | None, bool]]:
    return [(slot.kind, slot.path, slot.ti, slot.shown) for slot in slots]


def test_nested_sections_make_slots_depth_first() -> None:
    slots = row_slots(nested_project(), TaskFilter(), set(), False, 32, 24)
    assert summary(slots) == [
        ("task", (), 0, True),
        ("top-add", (), None, True),
        ("section", (0,), None, True),
        ("task", (0,), 0, True),
        ("section", (0, 0), None, True),
        ("task", (0, 0), 0, True),
        ("section", (0, 0, 0), None, True),
        ("task", (0, 0, 0), 0, True),
        ("section", (0, 1), None, True),
        ("task", (0, 1), 0, True),
        ("section", (1,), None, True),
        ("task", (1,), 0, True),
    ]


def test_collapsing_a_parent_hides_its_descendants_but_keeps_the_childs_own_state() -> None:
    shown = lambda collapsed: {  # noqa: E731
        (s.kind, s.path, s.ti): s.shown for s in row_slots(nested_project(), TaskFilter(), collapsed, False, 32, 24)
    }
    parent_closed = shown({(0,)})
    assert parent_closed[("section", (0,), None)] is True  # 閉じた親の見出し自身は見える
    assert parent_closed[("task", (0,), 0)] is False
    assert parent_closed[("section", (0, 0), None)] is False
    assert parent_closed[("task", (0, 0, 0), 0)] is False
    assert parent_closed[("section", (1,), None)] is True and parent_closed[("task", (1,), 0)] is True
    both = shown({(0,), (0, 0)})
    reopened = shown({(0, 0)})  # 親を開いても、子は閉じたまま
    assert reopened[("section", (0, 0), None)] is True
    assert reopened[("task", (0, 0), 0)] is False
    assert reopened[("section", (0, 0, 0), None)] is False
    assert reopened[("task", (0, 1), 0)] is True
    assert both[("section", (0, 1), None)] is False


def test_a_filter_ignores_collapse_and_keeps_the_parents_of_matches() -> None:
    slots = row_slots(nested_project(), TaskFilter(query="g"), {(0,), (0, 0)}, False, 32, 24)
    assert [(s.kind, s.path, s.ti) for s in slots if s.kind != "top-add"] == [
        ("section", (0,), None),
        ("section", (0, 0), None),
        ("section", (0, 0, 0), None),
        ("task", (0, 0, 0), 0),
    ]
    assert all(s.shown for s in slots)


def test_read_only_ignores_collapse_and_has_no_add_row() -> None:
    slots = row_slots(nested_project(), TaskFilter(), {(0,)}, True, 32, 24)
    assert all(s.shown for s in slots) and not any(s.kind == "top-add" for s in slots)


def test_row_centers_skip_hidden_nested_rows() -> None:
    slots = row_slots(nested_project(), TaskFilter(), {(0,)}, False, 32, 24)
    centers = row_centers(slots, 0)
    assert "p" not in centers and "c" not in centers and "g" not in centers
    assert "r" in centers and "o" in centers
```
(`row_slots`・`RowSlot`・`row_centers`・`Project`・`Section`・`Task`・`TaskFilter` を import する。)

`test/test_links.py` かリンクの候補のテスト(`link_options` を試験しているファイル。`grep -rn link_options test`)に足す:

```python
def test_link_options_label_nested_tasks_with_every_section_name() -> None:
    deep = Section("孫", [Task("深い", id="g")])
    project = Project("p", tasks=[Task("根", id="r")], sections=[Section("親", [Task("上", id="u")], [Section("子", [Task("中", id="m")], [deep])])])
    options = link_options(project, None)
    assert options == {"r": "根", "u": "親 / 上", "m": "親 / 子 / 中", "g": "親 / 子 / 孫 / 深い"}
```

`test/test_timeline.py` に足す:

```python
def test_visible_range_includes_tasks_in_nested_sections() -> None:
    far = Task("遠い", planned_start=datetime(2026, 12, 1, 9), planned_end=datetime(2026, 12, 3, 9))
    project = Project("p", base_date=date(2026, 10, 5), sections=[Section("親", sections=[Section("子", [far])])])
    start, end = visible_range(project)
    assert start == date(2026, 10, 5)
    assert end >= date(2026, 12, 4)  # 入れ子のタスクのバーまで、範囲が広がる
```

`test/test_gantt.py`:
- `test_the_slots_match_the_rendered_rows`(2760 行目付近)の中の `slot.si` を `slot.path` を使う形に直す:

```python
        marker = (
            f"row-{section_key(slot.path)}-{slot.ti}"
            if slot.kind == "task"
            else {"top-add": "top-end", "section": f"section-{section_key(slot.path)}"}[slot.kind]
        )
```
(`from projectapp.arrange import section_key` を import する。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_filtering.py test/test_links.py test/test_timeline.py -q 2>&1 | tail -6`
Expected: `ImportError: cannot import name 'section_has_match'`(`RowSlot` の `path` もまだない)。

- [ ] **Step 3: 実装する**

`src/projectapp/filtering.py`: import に `Section` はあるので、`visible_task_indexes` の下に足す:

```python
def section_has_match(section: Section, task_filter: TaskFilter) -> bool:
    """セクション自身か、子孫のどれかのタスクが条件に合うか。条件が空なら常に True。"""
    if not task_filter.active:
        return True
    return any(matches(task, task_filter) for task in section.tasks) or any(
        section_has_match(child, task_filter) for child in section.sections
    )
```

`src/projectapp/links.py`: import を `from projectapp.filtering import TaskFilter, matches, section_has_match, visible_task_indexes` と `from projectapp.models import Project, Section, SectionPath` にし、`RowSlot` と `row_slots` を置き換える:

```python
@dataclass(frozen=True)
class RowSlot:
    """描く行 1 つ。折りたたみで隠れる行は、作るが shown=False(高さを持たない)。"""

    kind: Literal["task", "section", "top-add"]
    path: SectionPath  # 行が属するセクションのパス(root と追加行は ())
    ti: int | None
    task_id: str | None
    shown: bool
    height: int


def row_slots(
    project: Project,
    task_filter: TaskFilter,
    collapsed: set[SectionPath],
    read_only: bool,
    row_height: int,
    add_height: int,
) -> list[RowSlot]:
    """gantt.render が描く行の並び。描画と矢印の計算の、両方がこの並びを使う。"""
    slots: list[RowSlot] = []
    for ti, task in enumerate(project.tasks):
        if matches(task, task_filter):
            slots.append(RowSlot("task", (), ti, task.id, True, row_height))
    if not read_only:
        slots.append(RowSlot("top-add", (), None, None, True, add_height))
    for index, section in enumerate(project.sections):
        _section_slots(slots, section, (index,), task_filter, collapsed, read_only, False, row_height)
    return slots


def _section_slots(
    slots: list[RowSlot],
    section: Section,
    path: SectionPath,
    task_filter: TaskFilter,
    collapsed: set[SectionPath],
    read_only: bool,
    hidden: bool,
    row_height: int,
) -> None:
    """セクションの見出し・タスク・サブセクションの行を足す。hidden は、親のどれかが折りたたまれている。"""
    if task_filter.active and not section_has_match(section, task_filter):
        return
    own_collapsed = path in collapsed and not read_only and not task_filter.active
    slots.append(RowSlot("section", path, None, None, not hidden, row_height))
    visible = set(visible_task_indexes(section, task_filter, own_collapsed))
    for ti, task in enumerate(section.tasks):
        if task_filter.active and ti not in visible:
            continue
        slots.append(RowSlot("task", path, ti, task.id, not hidden and ti in visible, row_height))
    for index, child in enumerate(section.sections):
        _section_slots(
            slots, child, (*path, index), task_filter, collapsed, read_only, hidden or own_collapsed, row_height
        )
```
(`links.py` の 40〜51 行目の古いループは削除。`row_centers`・`total_height` は変えない。)

`src/projectapp/linkgraph.py`: `link_options` の `labelled` の組み立てを置き換える(`walk_sections` を `projectapp.models` から import):

```python
    labelled: list[tuple[str, str]] = [(t.id, t.name) for t in project.tasks]
    names: dict[tuple[int, ...], str] = {}
    for path, section in walk_sections(project.sections):
        names[path] = f"{names[path[:-1]]} / {section.name}" if path[:-1] else section.name
        labelled += [(t.id, f"{names[path]} / {t.name}") for t in section.tasks]
```

`src/projectapp/timeline.py` の `visible_range`: `tasks = [*project.tasks, *(t for section in project.sections for t in section.tasks)]` を `tasks = project.all_tasks()` にする。

- [ ] **Step 4: 呼び出し側を合わせる**

`src/projectapp/gantt.py` の `self.collapsed` を使う箇所の型は Task 4 で直すが、`slots()` は `row_slots(…, self.collapsed, …)` を呼ぶ。この Task では `self.collapsed` が `set[int]` のままなので、`row_slots` に渡す前に変換する(Task 4 で外す):

```python
    def slots(self) -> list[RowSlot]:
        return row_slots(
            self.project,
            self.task_filter,
            {as_path(si) for si in self.collapsed},  # Task 4 で、collapsed 自体をパスの集合にする
            self.options.read_only,
            ROW_HEIGHT_PX,
            ADD_ROW_HEIGHT_PX,
        )
```
(`from projectapp.arrange import as_path` を import する。)

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -4 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: 入れ子のセクションの行の並び・絞り込み・先行タスクの候補・表示範囲を計算する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 入れ子の描画と、パスで動く操作(`gantt.py`・`views.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`SectionView`・`GanttActions`・`GanttChart`)
- Modify: `src/projectapp/views.py`(`tasks_in`・`save_task`・`add_task`・`edit_task`・`delete_task`・`shift_task`)
- Test: `test/test_gantt.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `section_key`・`as_path`・`parse_move` が返すパス(Task 2)、`row_slots`・`section_has_match`(Task 3)、`Section.all_tasks`(Task 1)。
- Produces:
  - `GanttChart.collapsed: set[SectionPath]`
  - `GanttChart.toggle_section(path)`・`expand_section(path)`(親もすべて展開)
  - 描画のマーカー: `section-<key>`・`section-name-<key>`・`section-toggle-<key>`・`section-label-<key>`・`section-count-<key>`・`add-task-<key>`・`task-<key>-<ti>`・`row-<key>-<ti>`・`bar-<key>-<ti>` ほか(`<key>` は `top`・`0`・`0.1`)
  - `GanttActions` の `add_task`・`edit_task`・`shift_task` はパス(`SectionPath`)を受ける。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py` に、入れ子のプロジェクトとテストを足す(`mount`(`Recorder` を返す)・`mount_chart`(`(charts, recorder)` を返す)・`chip`・`Project`・`Section`・`Task`・`BASE`・`TaskFilter`・`ViewOptions` は、このファイルのもの):

```python
def nested_chart_project() -> Project:
    def task(name: str) -> Task:
        return Task(name, planned_start=datetime(2026, 10, 5, 9), effort_hours=6.5)

    grandchild = Section("孫", [task("孫タスク")])
    child = Section("子", [task("子タスク")], [grandchild])
    parent = Section("親", [task("親タスク")], [child, Section("子2", [task("子2タスク")])])
    return Project("demo", base_date=BASE, tasks=[task("根タスク")], sections=[parent, Section("別", [task("別タスク")])])


NESTED_MARKERS = [
    "task-top-0", "section-0", "task-0-0", "section-0.0", "task-0.0-0", "section-0.0.0",
    "task-0.0.0-0", "section-0.1", "task-0.1-0", "section-1", "task-1-0",
]


async def test_nested_sections_render_depth_first_with_their_keys(user: User) -> None:
    mount(nested_chart_project())
    await user.open("/")
    for marker in NESTED_MARKERS:
        await user.should_see(marker=marker)


async def test_a_section_header_counts_every_task_below_it(user: User) -> None:
    mount(nested_chart_project())
    await user.open("/")
    counts = {key: chip(user, f"section-count-{key}").text for key in ("0", "0.0", "0.0.0", "0.1", "1")}
    assert counts == {"0": "(4)", "0.0": "(2)", "0.0.0": "(1)", "0.1": "(1)", "1": "(1)"}


async def test_each_level_is_indented_by_12px(user: User) -> None:
    mount(nested_chart_project())
    await user.open("/")
    assert chip(user, "task-top-0")._style["padding-left"] == "16px"  # root は今のまま
    assert chip(user, "task-0-0")._style["padding-left"] == "16px"  # 1 階層目も今のまま
    assert chip(user, "task-0.0-0")._style["padding-left"] == "28px"
    assert chip(user, "task-0.0.0-0")._style["padding-left"] == "40px"
    assert chip(user, "section-name-0")._style["padding-left"] == "0px"
    assert chip(user, "section-name-0.0")._style["padding-left"] == "12px"
    assert chip(user, "section-name-0.0.0")._style["padding-left"] == "24px"


async def test_collapsing_a_parent_hides_every_descendant(user: User) -> None:
    charts, _ = mount_chart(nested_chart_project())
    await user.open("/")
    charts[0].toggle_section((0,))
    await user.should_see(marker="section-0")
    for marker in ("task-0-0", "section-0.0", "task-0.0-0", "section-0.0.0", "task-0.0.0-0", "section-0.1", "task-0.1-0"):
        await user.should_not_see(marker=marker)
    await user.should_see(marker="section-1")
    await user.should_see(marker="task-1-0")


async def test_reopening_a_parent_keeps_the_childs_own_collapsed_state(user: User) -> None:
    charts, _ = mount_chart(nested_chart_project())
    await user.open("/")
    charts[0].toggle_section((0, 0))  # 子を閉じる
    charts[0].toggle_section((0,))  # 親を閉じる
    charts[0].toggle_section((0,))  # 親を開く
    await user.should_see(marker="section-0.0")  # 子の見出しは見える
    await user.should_not_see(marker="task-0.0-0")  # 子は閉じたまま
    await user.should_not_see(marker="section-0.0.0")
    await user.should_see(marker="task-0.1-0")  # 兄弟は開いている


async def test_expand_section_opens_every_ancestor(user: User) -> None:
    charts, _ = mount_chart(nested_chart_project())
    await user.open("/")
    chart = charts[0]
    chart.collapsed.update({(0,), (0, 0), (0, 0, 0), (1,)})
    chart.expand_section((0, 0, 0))
    assert chart.collapsed == {(1,)}  # 親すべてと自分を開き、無関係なセクションは閉じたまま


async def test_a_filter_shows_the_parents_of_a_match_and_ignores_collapse(user: User) -> None:
    charts, _ = mount_chart(nested_chart_project())
    await user.open("/")
    charts[0].collapsed.update({(0,), (0, 0)})
    charts[0].set_filter(TaskFilter(query="孫"))
    for marker in ("section-0", "section-0.0", "section-0.0.0", "task-0.0.0-0"):
        await user.should_see(marker=marker)
    for marker in ("task-top-0", "task-0-0", "task-0.0-0", "section-0.1", "section-1"):
        await user.should_not_see(marker=marker)


async def test_clicking_a_nested_task_reports_its_path(user: User) -> None:
    recorder = mount(nested_chart_project())
    await user.open("/")
    user.find(marker="task-0.0-0").click()
    assert recorder.events == [("edit_task", ((0, 0), 0))]


async def test_the_add_task_button_of_a_nested_section_reports_its_path(user: User) -> None:
    recorder = mount(nested_chart_project())
    await user.open("/")
    user.find(marker="add-task-0.0.0").click()
    assert recorder.events == [("add_task", ((0, 0, 0),))]


async def test_read_only_shows_every_nested_row_ignoring_collapse(user: User) -> None:
    charts, _ = mount_chart(nested_chart_project())
    await user.open("/")
    charts[0].collapsed.add((0,))
    charts[0].set_options(ViewOptions(read_only=True))
    for marker in ("section-0.0.0", "task-0.0.0-0"):
        await user.should_see(marker=marker)
```
(`ViewOptions`・`GanttChart`・`ui` は import 済み。`GanttChart(...)` のキーワード引数名は、既存の `mount` の書き方に合わせる。)

そのうえで、既存の `test_gantt.py` の `recorder.events` の期待値を、パスの形に直す(`edit_task` の第 1 引数が `None`/整数から、パスになるため):
- `("edit_task", (None, N))` → `("edit_task", ((), N))`
- `("edit_task", (K, N))` → `("edit_task", ((K,), N))`(K は整数)
- `test_the_add_task_button…` のような `("add_task", (K,))` → `("add_task", ((K,),))`

(該当箇所は 187・287・516・570・895・1549・2051・2232・2809 行目付近。`uv run pytest test/test_gantt.py -q` で落ちたものを直す。)

`test/test_views.py` に足す:

```python
async def open_nested_view(user: User, tmp_path: Path) -> MainView:
    view = await open_members_view(user, tmp_path)
    view.project.sections = [Section("親", [Task("p0")], [Section("子", [Task("c0")])])]
    view.project.tasks = [Task("r0")]
    view.gantt.set_project(view.project)
    return view


async def test_a_task_is_saved_into_a_nested_section(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.save_task((0, 0), None, Task("新しい"))
    assert [t.name for t in view.project.sections[0].sections[0].tasks] == ["c0", "新しい"]
    await user.should_see(marker="task-0.0-1")


async def test_saving_into_a_nested_section_opens_it_and_its_parents(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})
    view.save_task((0, 0), None, Task("新しい"))
    assert view.gantt.collapsed == set()


async def test_a_nested_task_can_be_edited_deleted_and_shifted(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.project.sections[0].sections[0].tasks[0].planned_start = datetime(2026, 10, 7, 9)
    view.shift_task((0, 0), 0, 2)
    assert view.project.sections[0].sections[0].tasks[0].planned_start == datetime(2026, 10, 9, 9)
    view.delete_task((0, 0), 0)
    assert view.project.sections[0].sections[0].tasks == []
    assert view.tasks_in((0,))[0].name == "p0"


async def test_shift_ignores_a_path_that_does_not_exist(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.shift_task((0, 5), 0, 1)  # 存在しない。落ちない
    view.shift_task((9,), 0, 1)
```
(`Section`・`datetime` は import 済み。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py test/test_views.py -q -k "nested or indented or counts or parent or expand_section or ancestors" 2>&1 | tail -8`
Expected: 入れ子のセクションの見出し(`section-0.0` など)が描かれない、`toggle_section((0,))` が `unhashable`/型エラーなどで失敗する。

- [ ] **Step 3: `gantt.py` を直す**

1. import: `from projectapp.arrange import …` に `section_key`・`as_path` を足し、`from projectapp.filtering import …` に `section_has_match` を、`from projectapp.models import …` に `SectionPath` を足す。
2. `SectionView` を置き換える:

```python
@dataclass
class SectionView:
    """描画したセクションの、折りたたみで切り替える部品。描き直すたびに作り直す。"""

    arrow: ui.button | None = None  # 開閉の矢印(読み取り専用では出さない)
    header: ui.element | None = None  # 見出しの行(親が折りたたまれると隠す)
    rows: list[ui.element] = field(default_factory=list)  # このセクション自身のタスクの行
    children: list[SectionPath] = field(default_factory=list)  # 描いたサブセクション
```
3. `GanttActions` のコメントと型を直す: `add_task: Callable[[SectionPath], object]`、`edit_task: Callable[[SectionPath, int], object]  # セクションのパス(root は ()), タスク番号`、`shift_task: Callable[[SectionPath, int, int], object]  # パス, タスク番号, 日数`。(`move_task` は `Position` を使うので、そのまま。)
4. `GanttChart.__init__`: `self.collapsed: set[SectionPath] = set()  # 折りたたんだセクションのパス。保存しない`、`self.section_views: dict[SectionPath, SectionView] = {}`。
5. `toggle_section`・`expand_section`・`reset_collapsed` を置き換える:

```python
    def hidden_by_ancestor(self, path: SectionPath) -> bool:
        """親のどれかが折りたたまれているか。"""
        return any(path[:n] in self.collapsed for n in range(1, len(path)))

    def toggle_section(self, section: object) -> None:
        """セクションの折りたたみを切り替える。描き直さず、行の表示と矢印だけを変える。"""
        path = as_path(section)
        self.collapsed.symmetric_difference_update({path})
        view = self.section_views.get(path)
        if view is None or self.options.read_only:
            return
        self.update_links()
        if view.arrow is not None:
            view.arrow.props(f"icon={ARROW_COLLAPSED if path in self.collapsed else ARROW_EXPANDED}")
        if not self.task_filter.active:  # 絞り込み中は、折りたたみを無視する(表示は変えない)
            self.apply_visibility(path, self.hidden_by_ancestor(path))

    def apply_visibility(self, path: SectionPath, hidden: bool) -> None:
        """セクションの見出し・タスク・サブセクションの表示を、折りたたみの状態に合わせる。"""
        view = self.section_views.get(path)
        if view is None:
            return
        collapsed = path in self.collapsed
        if view.header is not None:
            view.header.set_visibility(not hidden)
        for row in view.rows:
            row.set_visibility(not hidden and not collapsed)
        for child in view.children:
            self.apply_visibility(child, hidden or collapsed)

    def expand_section(self, section: object) -> None:
        """セクションと、その親をすべて展開する(描き直しは、呼び出し側のあとの処理に任せる)。"""
        path = as_path(section)
        for n in range(1, len(path) + 1):
            self.collapsed.discard(path[:n])
```
6. `drag_props(self, kind: str, key: str, **extra)` の型を `key: str` にする(中身は変えない。`data-si={key}`)。
7. `edit_on_click` を置き換える:

```python
    def edit_on_click(self, element: ui.element, path: SectionPath, ti: int) -> ui.element:
        """クリックでタスクの編集を開く。読み取り専用では何も付けない。"""
        if not self.options.read_only:
            element.on("click", lambda path=path, ti=ti: self.actions.edit_task(path, ti))
        return element
```
8. `slots()` を、Task 3 の一時的な変換をやめる形に直す: `row_slots(self.project, self.task_filter, self.collapsed, …)`(`{as_path(si) for si in self.collapsed}` を `self.collapsed` に戻す)。
9. `render()` の本体を置き換える:

```python
            for ti, task in enumerate(self.project.tasks):
                if matches(task, self.task_filter):
                    self.task_row((), ti, task, columns, width)
            self.top_add_row()
            for index, section in enumerate(self.project.sections):
                self.section_rows((index,), section, columns, width)
```
10. `section_rows` を、再帰に置き換える(`ARROW_*`・`ROW_STYLE`・`STICKY_Z_NAME` などは既存のもの):

```python
    def section_rows(
        self, path: SectionPath, section: Section, columns: list[Column], width: int, hidden: bool = False
    ) -> None:
        """セクションの見出し・タスク・サブセクション(再帰)を描く。hidden は、親のどれかが折りたたまれている。"""
        if self.task_filter.active and not section_has_match(section, self.task_filter):
            return
        key = section_key(path)
        collapsed = path in self.collapsed and not self.options.read_only
        effective = collapsed and not self.task_filter.active
        visible = visible_task_indexes(section, self.task_filter, collapsed)
        view = self.section_views[path] = SectionView()
        indent = 12 * (len(path) - 1)
        header = ui.row().classes("items-center no-wrap gap-2").style(ROW_STYLE)
        header.props(self.drag_props("section", key, count=len(section.tasks)))
        header.mark(f"section-{key}")
        header.set_visibility(not hidden)
        view.header = header
        with header:
            name = ui.row().classes("items-center no-wrap gap-2 gantt-sticky" + self.resize_classes())
            name.style(  # 名前の列にちょうど収める(狭いと縞や格子線が見え、広いと棒を隠す)
                f"width: var(--name-w); overflow: hidden; align-self: stretch;"
                f" padding-left: {indent}px; {sticky_left(STICKY_Z_NAME)}"
            )
            with name.mark(f"section-name-{key}"):
                if not self.options.read_only:
                    arrow = ARROW_COLLAPSED if collapsed else ARROW_EXPANDED
                    view.arrow = ui.button(
                        icon=arrow, on_click=lambda path=path: self.toggle_section(path)
                    ).props("flat dense round size=sm").classes("shrink-0").mark(f"section-toggle-{key}")
                label = ui.label(section.name).classes("text-subtitle2 ellipsis")
                label.style("min-width: 0; padding-left: 4px")  # 長い名前は縮めて、ボタンを残す
                label.tooltip(section.name).mark(f"section-label-{key}")
                if not self.options.read_only:
                    label.classes("cursor-pointer").on("click", lambda path=path: self.toggle_section(path))
                ui.label(f"({len(section.all_tasks())})").classes("text-caption shrink-0").mark(
                    f"section-count-{key}"
                )
                if not self.options.read_only:
                    ui.button(
                        icon="add", on_click=lambda path=path: self.actions.add_task(path)
                    ).props("flat dense round size=sm").classes("shrink-0").tooltip("タスク追加").mark(
                        f"add-task-{key}"
                    )
        shown = set(visible)
        for ti, task in enumerate(section.tasks):
            if self.task_filter.active and ti not in shown:
                continue  # 絞り込みで外れたタスクは、描かない
            row = self.task_row(path, ti, task, columns, width)
            row.set_visibility(not hidden and ti in shown)  # 折りたたみ中は、行を作って隠しておく(開くとき作り直さない)
            view.rows.append(row)
        for index, child in enumerate(section.sections):
            child_path = (*path, index)
            self.section_rows(child_path, child, columns, width, hidden or effective)
            if child_path in self.section_views:
                view.children.append(child_path)
```
11. `task_row` と、`actual_bars`・`checkpoint_marker`・`deadline_marker` を、パスに直す。次の使い捨てのスクリプトで、機械的に置き換える(スクリプトは作業用ディレクトリに書き、リポジトリには入れない):

```python
import re
from pathlib import Path

p = Path("src/projectapp/gantt.py")
s = p.read_text(encoding="utf-8")
s = s.replace("si: int | None", "path: SectionPath")
s = s.replace('key = "top" if si is None else si', "key = section_key(path)")
s = re.sub(r"(?<![-\w])si\b", "path", s)  # `data-si` は残す(直前が「-」)
p.write_text(s, encoding="utf-8")
```
実行後に `grep -n "\bsi\b" src/projectapp/gantt.py | grep -v "data-si"` が何も返さないこと、`uv run ruff` 相当の確認として `uvx ty check src` が通ることを確かめる。さらに `task_row` の名前の欄の左の余白を、階層に合わせる(`cell_style` の `padding-left: 16px` を、`padding-left: {16 + 12 * max(len(path) - 1, 0)}px` にする)。

- [ ] **Step 4: `views.py` を直す**

`tasks_in`・`add_task`・`edit_task`・`delete_task`・`shift_task`・`save_task` の引数名 `section_index` を `path` にし、型を `SectionPath` にする。`tasks_in` は `arrange.tasks_at` を使う:

```python
    def tasks_in(self, path: SectionPath) -> list[Task]:
        """セクション(root は ())のタスクの一覧。"""
        return arrange.tasks_at(self.project, path)
```
`save_task` の末尾の展開は `if task_index is None and path: self.gantt.expand_section(path)`(root `()` は展開しない)に直す。`shift_task` の `arrange.has_task(self.project, (path, task_index))` は変えない。`add_task` が開くダイアログの保存コールバック `lambda task: self.save_task(path, None, task)` に直す。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -6 && uvx ty check src | tail -2`
Expected: 全件 PASS、`ty` の指摘なし。落ちた場合は、マーカーのインデント(`padding-left`)、見出しの `set_visibility`、`SectionView.children` を確かめる。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: 入れ子のセクションを、インデントして再帰で描き、パスで操作する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: サブセクションの追加と、ドラッグのキー(`gantt.py`・`views.py`・`forms.py`・`gantt_drag.py`)

**Files:**
- Modify: `src/projectapp/gantt.py`(`GanttActions.add_subsection`・見出しのボタン)
- Modify: `src/projectapp/views.py`(`add_subsection`・`save_subsection`)
- Modify: `src/projectapp/forms.py`(`open_section_dialog` のタイトル)
- Modify: `src/projectapp/gantt_drag.py`(`section()` がキーの文字列を送る)
- Test: `test/test_gantt.py`、`test/test_views.py`、`test/test_gantt_drag.py`

**Interfaces:**
- Consumes: `section_at`・`MAX_SECTION_DEPTH`(Task 1・2)、`SectionView`・`expand_section`(Task 4)。
- Produces:
  - `GanttActions.add_subsection: Callable[[SectionPath], object]`(既定は何もしない)
  - マーカー `add-subsection-<key>`(1・2 階層目の見出しだけ。読み取り専用では出さない)
  - `MainView.add_subsection(path)`・`MainView.save_subsection(path, name)`(存在しない親と、3 階層目の親は何もしない)
  - `open_section_dialog(on_save, title: str = "セクションの追加")`
  - ブラウザ側の JS は、セクションを `data-si` の文字列(`top`・`0`・`0.1`)のまま `chart_move`・`chart_shift` で送る。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_gantt.py`: `Recorder` の `GanttActions(...)` に `add_subsection=lambda path: self.events.append(("add_subsection", (path,))),` を足す。そのうえで足す:

```python
async def test_subsection_buttons_appear_on_levels_one_and_two_only(user: User) -> None:
    mount(nested_chart_project())
    await user.open("/")
    await user.should_see(marker="add-subsection-0")
    await user.should_see(marker="add-subsection-0.0")
    await user.should_see(marker="add-subsection-1")
    await user.should_not_see(marker="add-subsection-0.0.0")  # 3 階層目には出さない


async def test_the_subsection_button_reports_its_path(user: User) -> None:
    recorder = mount(nested_chart_project())
    await user.open("/")
    user.find(marker="add-subsection-0.0").click()
    assert recorder.events == [("add_subsection", ((0, 0),))]


async def test_read_only_has_no_subsection_buttons(user: User) -> None:
    charts, _ = mount_chart(nested_chart_project())
    await user.open("/")
    charts[0].set_options(ViewOptions(read_only=True))
    await user.should_see(marker="section-0")
    await user.should_not_see(marker="add-subsection-0")
```

`test/test_views.py`:

```python
async def test_adding_a_subsection_through_the_dialog(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    user.find(marker="add-subsection-0").click()
    user.find(marker="section-name").type("新しい子")
    user.find(marker="section-save").click()
    assert [s.name for s in view.project.sections[0].sections] == ["子", "新しい子"]
    await user.should_see(marker="section-0.1")
    assert view.is_dirty()


async def test_a_subsection_can_be_added_to_a_subsection_but_not_below_level_three(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.save_subsection((0, 0), "孫")
    assert view.project.sections[0].sections[0].sections[0].name == "孫"
    view.save_subsection((0, 0, 0), "ひ孫")  # 3 階層目の親には足せない
    assert view.project.sections[0].sections[0].sections[0].sections == []


async def test_save_subsection_ignores_a_missing_parent(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.save_subsection((7,), "どこにも")
    view.save_subsection((), "root は別の操作")
    assert [s.name for s in view.project.sections] == ["親"]


async def test_adding_a_subsection_opens_the_parent_chain(user: User, tmp_path: Path) -> None:
    view = await open_nested_view(user, tmp_path)
    view.gantt.collapsed.update({(0,), (0, 0)})
    view.save_subsection((0, 0), "孫")
    assert view.gantt.collapsed == set()


async def test_the_subsection_dialog_has_its_own_title(user: User, tmp_path: Path) -> None:
    await open_nested_view(user, tmp_path)
    user.find(marker="add-subsection-0").click()
    await user.should_see("サブセクションの追加")
```

`test/test_gantt_drag.py`: ブラウザ側が文字列のキーを送るので、次を直す。
- 440 行目付近 `assert normal["emitted"] == [["chart_shift", {"si": 0, "ti": 0, "days": 3}]]` を `{"si": "0", "ti": 0, "days": 3}` に、600 行目付近の `{"si": 0, "ti": 0, "days": 2}` を `{"si": "0", "ti": 0, "days": 2}` に直す。
- 475 行目付近 `["chart_move", {"src": [None, 1], "dst": [0, 0], "copy": True}]` を `["chart_move", {"src": ["top", 1], "dst": ["0", 0], "copy": True}]` に直す。
- `test_a_nested_section_key_survives_the_roundtrip_to_the_server` を足す:

```python
def test_a_nested_section_key_survives_the_roundtrip_to_the_server() -> None:
    from projectapp.arrange import parse_move, parse_shift

    assert parse_move({"src": ["0.1", 2], "dst": ["0.1.0", 0], "copy": False}) == (((0, 1), 2), ((0, 1, 0), 0), False)
    assert parse_shift({"si": "0.1", "ti": 0, "days": 1}) == (((0, 1), 0), 1)
    assert parse_move({"src": ["top", 0], "dst": ["1", 3], "copy": True}) == (((), 0), ((1,), 3), True)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_gantt.py test/test_views.py test/test_gantt_drag.py -q -k "subsection or nested_section_key or chart_move or normal or zoom" 2>&1 | tail -8`
Expected: `add_subsection` が `GanttActions` にない、`add-subsection-0` が見つからない、JS のキーが数値・`null` のまま、などで失敗する。

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py`:
- `GanttActions` に、`set_name_width` の前に追加する(既定は何もしない):

```python
    add_subsection: Callable[[SectionPath], object] = lambda path: None  # サブセクションの追加(セクションのパス)
```
(dataclass の既定値つきフィールドは、既定値のないフィールドより後ろに置く。`set_name_width` が既定値なしで最後にあるので、順序の都合で、`add_subsection` を `set_name_width` の**後ろ**(最後)に置く。)
- `section_rows` の `add-task-{key}` のボタンの前に、サブセクションの追加ボタンを足す:

```python
                if not self.options.read_only and len(path) < MAX_SECTION_DEPTH:
                    ui.button(
                        icon="create_new_folder", on_click=lambda path=path: self.actions.add_subsection(path)
                    ).props("flat dense round size=sm").classes("shrink-0").tooltip("サブセクション追加").mark(
                        f"add-subsection-{key}"
                    )
```
(`MAX_SECTION_DEPTH` を `projectapp.models` から import する。)

`src/projectapp/forms.py`: `open_section_dialog` を次にする:

```python
def open_section_dialog(on_save: Callable[[str], object], title: str = "セクションの追加") -> None:
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-80"):
        ui.label(title).classes("text-h6")
        name = ui.input("セクション名").mark("section-name")
        # (以下は今のまま)
```

`src/projectapp/views.py`:
- `GanttActions(...)` の組み立てに `add_subsection=self.add_subsection,` を足す。
- `save_section` の下に足す:

```python
    def add_subsection(self, path: SectionPath) -> None:
        open_section_dialog(lambda name: self.save_subsection(path, name), title="サブセクションの追加")

    def save_subsection(self, path: SectionPath, name: str) -> None:
        """セクションの末尾にサブセクションを足す。親がない・root・3 階層目の親は何もしない。"""
        parent = arrange.section_at(self.project, path)
        if parent is None or len(path) >= MAX_SECTION_DEPTH:
            return
        parent.sections.append(Section(name))
        self.gantt.expand_section(path)
        self.gantt.set_project(self.project)
```
(`MAX_SECTION_DEPTH`・`SectionPath` を `projectapp.models` から import する。)

`src/projectapp/gantt_drag.py`: 先頭付近の `const section = (value) => (value === "top" ? null : Number(value));` を `const section = (value) => value;  // data-si のキー(top・0・0.1)をそのまま送る` に直す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -6 && uvx ty check src | tail -2`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: サブセクションを追加でき、ドラッグがセクションのキーを送る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 移行用の変換を消し、文書を直す

**Files:**
- Modify: `src/projectapp/arrange.py`(`as_path` を削除)、`gantt.py`・`views.py`(`as_path` の呼び出しを削除)
- Modify: パスに直っていないテスト(`test_views.py`・`test_gantt.py`・`test_arrange.py` など)
- Modify: `CLAUDE.md`、`docs/development.md`、`.claude/MEMORY.md`

- [ ] **Step 1: 残りの `as_path` を洗い出す**

Run: `grep -rn "as_path" src test`
Expected: `arrange.py`(定義と `tasks_at`・`valid_section`)、`gantt.py`(`toggle_section`・`expand_section`)。

- [ ] **Step 2: 変換を消す**

- `arrange.py`: `as_path` の関数を削除し、`tasks_at(project, path: SectionPath)`・`valid_section(project, path: SectionPath)` の引数名と型を `path: SectionPath` にして、`path = as_path(section)` の行を削除する。`parse_section` の整数・`None` の分岐は、画面(JS)がキーの文字列だけを送るので、`None`・整数を `None`(不正)にする: 

```python
def parse_section(value: object) -> SectionPath | None:
    """画面から届くセクションの指定(キーの文字列 `top`・`0`・`0.1`)。不正は None。"""
    return parse_section_key(value) if isinstance(value, str) else None
```
- `gantt.py`: `toggle_section(self, path: SectionPath)`・`expand_section(self, path: SectionPath)` から `as_path` を外す。`from projectapp.arrange import as_path` の import を消す。
- `views.py`: `as_path` を使っている箇所があれば外す。

- [ ] **Step 3: 落ちるテストをパスに直す**

Run: `uv run pytest -q -n auto 2>&1 | tail -40`。`TypeError`・`IndexError`・`AssertionError` で落ちたものを、次の規則で直す(セクションの引数だけ):
- `None`(root) → `()`、整数 `N` → `(N,)`。
- 対象の呼び出し: `view.save_task(`・`view.add_task(`・`view.edit_task(`・`view.delete_task(`・`view.shift_task(`・`view.tasks_in(`・`chart.toggle_section(`・`chart.expand_section(`・`charts[0].toggle_section(`・`charts[0].expand_section(`、`arrange.*(project, (section, index), …)` の位置、`GanttChart.collapsed` との比較(`{0}` → `{(0,)}`)、`parse_position`/`parse_move`/`parse_shift` に渡す `None`・整数(これらは JS が文字列のキーを送るので、`"top"`・`"0"` に直す)。
- 例: `view.save_task(0, None, task)` → `view.save_task((0,), None, task)`、`view.save_task(None, None, task)` → `view.save_task((), None, task)`、`arrange.move_task(project, (0, 1), (None, 0))` → `arrange.move_task(project, ((0,), 1), ((), 0))`、`chart.collapsed == {0}` → `{(0,)}`。
- 迷ったら、失敗の出力の `section`/`path` の型の不一致を見る。

- [ ] **Step 4: 文書を直す**

`CLAUDE.md`(`projectapp/CLAUDE.md`)の「ガントチャート」の節に足す: 「`ガントチャート`の`セクション`は、サブセクションを持てる（セクションを最大3階層まで。タスクは`root`と、どの階層のセクションにも置ける）。サブセクションは、1・2階層目のセクションの見出しのボタンで追加する（改名・削除・移動はできない）。セクションの中は、タスクが先、サブセクションが後。インデントして並べ、見出しのタスク数はサブセクションの分も含めた合計。折りたたみは、サブセクションもまとめて隠し、親を開いても子の折りたたみの状態を保つ。絞り込み中は、一致したタスクの親のセクションも出す」。既存の「`ガントチャート`の`セクション`は、見出しの矢印か名前のクリックで折りたためる。…」の項目は、そのまま残す。

`docs/development.md`: 「ファイル形式の注意」に足す: 「セクションは `Section.sections`(入れ子。`[{"name", "tasks", "sections"}]`)。キーがない・`null` は空。4 階層以上と、`sections` の型の違いは読込を拒否する(`storage._section`)。セクションの位置は `SectionPath`(番号のパス。root は `()`)で、マーカーのキーは `arrange.section_key`(`top`・`0`・`0.1`)。1 階層目は入れ子の前と同じ。ブラウザ側の JS は、`data-si` のキー(文字列)をそのまま送り、サーバーが `parse_section_key` で戻す。折りたたみは `GanttChart.collapsed`(パスの集合)で、親を閉じると子孫が隠れ、親を開いても子の状態は保たれる(`row_slots` と `apply_visibility` が同じ規則)」。設計書の一覧の表に `| セクションの入れ子 | `2026-10-09-nested-sections-design.md` |` を足す。

`.claude/MEMORY.md`: 要望 7 を「実装済み・実機確認待ち。ブランチ `feature/nested-sections`。設計書 `2026-10-09-nested-sections-design.md`、実装計画 `2026-10-09-nested-sections.md`。テスト N 件と `ty` が通る」に書き換える(決定の要約は残す)。「最終更新」の行と、未着手の要望の番号の列から 7 を外す。

- [ ] **Step 5: 全体を確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -4 && uvx ty check src | tail -2 && grep -rn "as_path\|\bsi: int" src | head`
Expected: 全件 PASS、`ty` の指摘なし、`grep` が何も返さない。結果の件数を `.claude/MEMORY.md` に書く。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "refactor: 移行用の変換を消し、セクションの入れ子の文書を直す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: 実機確認をユーザーに依頼する**

ネイティブウィンドウ(`uv run projectapp`)で、次を確認してもらう。結果が届くまで、PR とマージはしない。
1. 1・2 階層目のセクションの見出しに「サブセクション追加」のボタンが出て、押すと名前の入力のダイアログ(「サブセクションの追加」)が開き、追加すると親の下にインデントして出る。3 階層目の見出しにはボタンが出ない。
2. インデント: 1 階層目は今のまま、2・3 階層目が 12px ずつ右にずれる(ライト・ダーク、拡大・縮小、名前の欄の幅の調整でも崩れない)。
3. 見出しのタスク数が、サブセクションの分も含めた合計になる。サブセクションのないセクションは、今と同じ。
4. 親を閉じると、中のタスクとサブセクションがすべて隠れる。親を開き直しても、子の閉じた状態が保たれる。タスクやサブセクションを足すと、そのセクションと親がすべて開く。
5. 絞り込みで、一致するタスクの親のセクションも出る。折りたたんでいても出る。
6. ドラッグ: タスクを、サブセクションの見出しやタスクの間に、移動・コピーできる。見出しに落とすと、そのセクション自身のタスクの末尾(サブセクションの前)に入る。
7. 古いファイル(入れ子のないプロジェクト)が、これまでと同じに見える。入れ子のプロジェクトを保存して開き直しても、残る。
8. 先行タスクの連結の矢印と、先行タスクの候補(`親 / 子 / タスク`)が、入れ子でも動く。プレビュー(画像の保存)とダッシュボードが、入れ子のタスクを含めて動く。
