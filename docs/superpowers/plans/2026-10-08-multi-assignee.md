# タスクへの複数アサイン Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1 つのタスクに複数のメンバーを割り当て、メンバーごとに割り当て率を設定できるようにする。工数は 1 つのまま、担当者全員の換算率の合計で完了予定を出す。

**Architecture:** `Task.assignee` と `Task.allocation` をやめ、`Task.assignees: list[Assignee]` に一本化する。まず、読み取り専用の別名(`Task.assignee`・`Task.allocation`)を置いて、全体が動いたままデータの形を切り替える(Task 1)。そのあと、モジュールごとに、テストを先に書いて複数の担当者に対応させ(Task 2〜6)、最後に別名を消す(Task 7)。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -q -n auto`)、`uvx ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-08-multi-assignee-design.md`

## Global Constraints

- 言語は日本語。コメント・テスト名・コミットメッセージも日本語(識別子は英語)。コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- Python 3.13 以上、NiceGUI。外部のガントライブラリは使わない。
- 日時・日程の計算は、NiceGUI から切り離した純粋関数(`timeline.py`)に置く。
- ファイル形式を変えるときは、キーのない古いファイルを既定値で読み(移行を要らなくする)、不正な値は読込を拒否する。
- 割り当て率は 0.01〜1.0(`MIN_ALLOCATION`〜`MAX_ALLOCATION`)。同じタスクに同じメンバーを 2 回入れない。
- チェックポイントは担当を持たない(`assignees` は常に空)。
- 描画の要素数を増やさない(要望 24)。チップは担当者が 2 人以上のときだけ増える。
- テストは `uv run pytest -q -n auto`(全体で約 15 秒)。型は `uvx ty check src`。各タスクの最後に、全体のテストが通ることを確かめる。
- 実機確認(ネイティブ: `uv run projectapp`)の前に、PR・マージはしない。`develop` へのプッシュは、許可を得てから行う。

## Review Focus

- 古いファイル(`assignee`・`allocation` のキー)の読み込み。担当者なしで `allocation` が不正な値でも、今と同じく拒否する。→ Task 1 のテスト。
- 同じメンバーを 1 つのタスクに 2 回入れる(ダイアログの入力と、手編集したファイル)。→ Task 1(ファイル)と Task 3(ダイアログ)のテスト。
- メンバーの一覧にいない担当者が混ざる(換算率に数えない。保存で失わない。割り当て超過に数えない)。→ Task 2・3 のテスト。
- 5 人以上の担当者(チップが `+n` にまとまる)と、担当者全員が一覧にいない場合の換算率(1.0)。→ Task 2・5 のテスト。
- メンバー名の入れ替え(A↔B)での改名、担当の一部だけが削除されるメンバーの削除制限。→ Task 4 のテスト。

---

## File Structure

| ファイル | 役割 | 変更 |
|---|---|---|
| `src/projectapp/models.py` | `Assignee` を足し、`Task.assignees` に一本化 | Task 1 |
| `src/projectapp/storage.py` | `assignees` の保存・読込、古いキーの移行、メンバーの補い | Task 1 |
| `src/projectapp/arrange.py` | タスクの複製で `assignees` を引き継ぐ(別のオブジェクトにする) | Task 1 |
| `src/projectapp/timeline.py` | 換算率の合算、担当者ごとの割り当て超過 | Task 2 |
| `src/projectapp/forms.py` | `build_task` が担当者の行のリストを受ける | Task 3 |
| `src/projectapp/task_dialog.py` | 担当者の行のリスト(`AssigneeFields`)、換算の説明 | Task 3 |
| `src/projectapp/views.py` | 改名・削除制限・保存時の超過の通知 | Task 1・4 |
| `src/projectapp/filtering.py`・`gantt.py` | 担当者の絞り込み、複数のチップ | Task 5 |
| `src/projectapp/dashboard.py`・`handoff.py` | 担当者ごとの集計、書き出しの見積もり | Task 6 |
| `CLAUDE.md`・`docs/development.md`・`.claude/MEMORY.md` | 文書 | Task 7 |

---

### Task 1: データの形を `assignees` に切り替える(動作は変えない)

**Files:**
- Modify: `src/projectapp/models.py`(`Task` の担当・割り当て率の欄)
- Modify: `src/projectapp/storage.py`(`_task`・`_assignee`・`_checkpoint`・メンバーの補い)
- Modify: `src/projectapp/arrange.py:48-54`(複製)
- Modify: `src/projectapp/forms.py`(`build_task`・`_build_checkpoint` の `replace(...)`)
- Modify: `src/projectapp/views.py`(`apply_members` の改名)
- Test: `test/test_storage.py`、ほかのテストの機械的な移行

**Interfaces:**
- Produces: `Assignee(name: str, allocation: float = 1.0)`、`Task.assignees: list[Assignee]`、`Task.assignee_names -> list[str]`、移行用の読み取り専用の別名 `Task.assignee -> str | None`(先頭の名前)と `Task.allocation -> float`(先頭の割り当て率。担当なしは 1.0)。別名は Task 7 で消す。

- [ ] **Step 1: 保存・読込の失敗するテストを書く**

`test/test_storage.py` の末尾に足す(`Assignee` を `from projectapp.models import (...)` に足す。`_rewrite`・`save_project`・`load_project` は、このファイルに既にある)。

```python
def test_assignees_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    project = Project(
        "p",
        members=[Member("田中"), Member("鈴木")],
        tasks=[Task("a", assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.5)]), Task("b")],
    )
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.tasks[0].assignees == [Assignee("田中", 0.6), Assignee("鈴木", 0.5)]
    assert loaded.tasks[1].assignees == []
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["tasks"][0]["assignees"] == [
        {"name": "田中", "allocation": 0.6},
        {"name": "鈴木", "allocation": 0.5},
    ]
    assert "assignee" not in raw["tasks"][0] and "allocation" not in raw["tasks"][0]


def test_old_keys_load_as_one_assignee(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save_project(Project("p", members=[Member("田中")], tasks=[Task("a"), Task("b")]), path)

    def legacy(data: dict) -> None:
        for task in data["tasks"]:
            task.pop("assignees")
        data["tasks"][0].update(assignee=" 田中 ", allocation=0.4)
        data["tasks"][1].update(assignee="", allocation=1.0)

    _rewrite(path, legacy)
    loaded = load_project(path)
    assert loaded.tasks[0].assignees == [Assignee("田中", 0.4)]
    assert loaded.tasks[1].assignees == []


@pytest.mark.parametrize("value", [0.0, 1.5, "x", True, float("nan")])
def test_old_keys_with_a_bad_allocation_are_rejected_even_without_an_assignee(value: object, tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save_project(Project("p", tasks=[Task("a")]), path)

    def legacy(data: dict) -> None:
        data["tasks"][0].pop("assignees")
        data["tasks"][0].update(assignee=None, allocation=value)

    _rewrite(path, legacy)
    with pytest.raises(ValueError):
        load_project(path)


def test_assignees_win_over_the_old_keys(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save_project(Project("p", members=[Member("田中"), Member("鈴木")], tasks=[Task("a", assignees=[Assignee("鈴木")])]), path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignee="田中", allocation=0.2))
    assert load_project(path).tasks[0].assignees == [Assignee("鈴木", 1.0)]


@pytest.mark.parametrize(
    "bad",
    [
        "田中",  # リストでない
        ["田中"],  # 辞書でない
        [{"name": "", "allocation": 1.0}],
        [{"name": 3, "allocation": 1.0}],
        [{"name": "田中", "allocation": 0.0}],
        [{"name": "田中", "allocation": 1.01}],
        [{"name": "田中", "allocation": "x"}],
        [{"name": "田中", "allocation": 1.0}, {"name": " 田中 ", "allocation": 0.5}],  # 重複
    ],
)
def test_bad_assignees_are_rejected(bad: object, tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save_project(Project("p", members=[Member("田中")], tasks=[Task("a")]), path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignees=bad))
    with pytest.raises(ValueError):
        load_project(path)


def test_missing_allocation_in_an_assignee_means_one(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save_project(Project("p", members=[Member("田中")], tasks=[Task("a")]), path)
    _rewrite(path, lambda d: d["tasks"][0].update(assignees=[{"name": "田中"}]))
    assert load_project(path).tasks[0].assignees == [Assignee("田中", 1.0)]


def test_every_assignee_missing_from_the_members_is_added_as_a_member(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    project = Project(
        "p",
        members=[Member("田中", 1.2)],
        tasks=[Task("a", assignees=[Assignee("佐藤"), Assignee("鈴木")]), Task("b", assignees=[Assignee("佐藤")])],
    )
    save_project(project, path)
    loaded = load_project(path)
    assert [(m.name, m.ratio) for m in loaded.members] == [("田中", 1.2), ("佐藤", 1.0), ("鈴木", 1.0)]


def test_a_checkpoint_has_no_assignees(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    checkpoint = Task("c", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), assignees=[Assignee("田中")])
    save_project(Project("p", members=[Member("田中")], tasks=[checkpoint]), path)
    assert load_project(path).tasks[0].assignees == []
```

(`json`・`datetime`・`TaskKind` が import されていなければ足す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_storage.py -q -k "assignees or old_keys or bad_assignees or missing_allocation or every_assignee or checkpoint_has_no" 2>&1 | tail -15`
Expected: `ImportError: cannot import name 'Assignee'`(まだ作っていないため)。

- [ ] **Step 3: `models.py` を直す**

`Task` の前に `Assignee` を足し、`Task` の欄を直す。

```python
@dataclass
class Assignee:
    name: str
    allocation: float = 1.0  # 担当者の時間のうち、このタスクに使う割合(1.0 = 100%)
```

`Task` の中で、`assignee: str | None = None` の行を `assignees: list[Assignee] = field(default_factory=list)` に、`allocation: float = 1.0  # …` の行を削除する。`urls` の欄の下に、次の 3 つの property を足す。

```python
    @property
    def assignee_names(self) -> list[str]:
        return [a.name for a in self.assignees]

    # --- 移行用の読み取り専用の別名(Task 7 で消す) ---
    @property
    def assignee(self) -> str | None:
        return self.assignees[0].name if self.assignees else None

    @property
    def allocation(self) -> float:
        return self.assignees[0].allocation if self.assignees else 1.0
```

- [ ] **Step 4: `storage.py` を直す**

`from projectapp.models import (...)` に `Assignee` を足す。`_task` の `assignee=_assignee(raw.get("assignee")),` と `allocation=_allocation(raw.get("allocation", 1.0)),` の 2 行を `assignees=_assignees(raw),` の 1 行にする。`_assignee` の下に足す:

```python
def _assignees(raw: dict[str, Any]) -> list[Assignee]:
    """担当者のリスト。`assignees` を使う。なければ、古いキー(assignee・allocation)を 1 人にする。"""
    value = raw.get("assignees")
    if value is None:
        allocation = _allocation(raw.get("allocation", 1.0))  # 古いファイルも、不正な値は拒否する
        name = _assignee(raw.get("assignee"))
        return [Assignee(name, allocation)] if name else []
    if not isinstance(value, list):
        raise ValueError("担当者が配列ではありません")
    assignees: list[Assignee] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("担当者の形式が正しくありません")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("担当者の名前が正しくありません")
        name = name.strip()
        if name in seen:
            raise ValueError(f"担当者が重複しています: {name}")
        seen.add(name)
        assignees.append(Assignee(name, _allocation(item.get("allocation", 1.0))))
    return assignees
```

`_checkpoint` の `replace(...)` の `assignee=None,` と `allocation=1.0,` の 2 行を `assignees=[],` の 1 行にする。プロジェクトを組み立てる末尾の、メンバーの補いを直す:

```python
    known = {m.name for m in project.members}
    for task in project.all_tasks():  # 古いファイルの自由入力の担当者を、メンバーとして補う
        for assignee in task.assignees:
            if assignee.name not in known:
                known.add(assignee.name)
                project.members.append(Member(assignee.name, 1.0))
```

- [ ] **Step 5: 書き込む側の 3 か所を直す**

`src/projectapp/arrange.py` の `replace(` の引数で `urls=[...]` の行の上に足す(`Assignee` は import しない。`replace` は `dataclasses.replace` が既に import されている):

```python
        assignees=[replace(a) for a in original.assignees],
```

`src/projectapp/forms.py`:
- `_build_checkpoint` の `replace(...)` の `assignee=None,` と `allocation=1.0,` を `assignees=[],` にする。
- `build_task` の末尾の `replace(base, ...)` の `assignee=assignee_name or None,` と `allocation=allocation,` を `assignees=[Assignee(assignee_name, allocation)] if assignee_name else [],` にする。`from projectapp.models import` に `Assignee` を足す。(引数の `assignee`・`allocation_percent` は、Task 3 まで今のまま。)

`src/projectapp/views.py` の `apply_members` の改名を直す:

```python
        if renames:
            for task in self.project.all_tasks():
                for assignee in task.assignees:
                    if assignee.name in renames:
                        assignee.name = renames[assignee.name]
```

- [ ] **Step 6: 既存のテストを機械的に移行する**

使い捨てのスクリプトを、作業用ディレクトリ(`/private/tmp/claude-501/-Users-jun-Documents-opt-work-projectapp/8d3b9a46-ae45-4e7b-84ed-541906ce9bc4/scratchpad/migrate_tests.py`)に書いて実行する(リポジトリには入れない)。

```python
"""Task(...) の assignee=/allocation= を assignees=[Assignee(...)] に置き換える(テストの移行用。使い捨て)。"""
import re
import sys
from pathlib import Path

COMBINED = re.compile(r'assignee=("[^"]*"|[A-Za-z_]\w*),(\s*)allocation=([0-9.]+|[A-Za-z_]\w*)')
SINGLE = re.compile(r'(?<![\w"])assignee=("[^"]*")')

for name in sys.argv[1:]:
    path = Path(name)
    text = COMBINED.sub(lambda m: f"assignees=[Assignee({m.group(1)}, {m.group(3)})]", path.read_text(encoding="utf-8"))
    lines = []
    for line in text.splitlines(keepends=True):
        if "TaskFilter" not in line:
            line = SINGLE.sub(lambda m: f"assignees=[Assignee({m.group(1)})]", line)
        lines.append(line)
    text = "".join(lines)
    if "Assignee(" in text and not re.search(r"^from projectapp\.models import .*\bAssignee\b", text, re.M):
        if re.search(r"^from projectapp\.models import \($", text, re.M):
            text = re.sub(r"^(from projectapp\.models import \()$", r"\1\n    Assignee,", text, count=1, flags=re.M)
        else:
            text = re.sub(r"^(from projectapp\.models import )", r"\1Assignee, ", text, count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")
```

Run:
```bash
S=/private/tmp/claude-501/-Users-jun-Documents-opt-work-projectapp/8d3b9a46-ae45-4e7b-84ed-541906ce9bc4/scratchpad
uv run python $S/migrate_tests.py test/test_dashboard.py test/test_filtering.py test/test_timeline.py test/test_schedule.py test/test_gantt.py test/test_views.py test/test_storage.py test/test_handoff.py test/test_task_dialog.py
git diff --stat
```
Expected: 上のファイルだけが変わる。`test_forms.py`・`test_checkpoint.py`・`test_arrange.py` は、`build_task` の引数や属性への代入が混ざるので、手で直す(Step 7)。

- [ ] **Step 7: 残りを手で直す**

`uv run pytest -q -n auto 2>&1 | tail -30` を実行し、落ちたものを次の規則で直す。**期待される落ち方と直し方**:

- `test/test_arrange.py:96-97`: `original.assignee = "田中"` と `original.allocation = 0.5` を `original.assignees = [Assignee("田中", 0.5)]` の 1 行にし、`Assignee` を import する。さらに、次のテストを足す:
  ```python
  def test_copy_does_not_share_the_assignees() -> None:
      project = sample()
      original = project.sections[0].tasks[1]
      original.assignees = [Assignee("田中", 0.5)]
      copy = arrange.copy_task(project, (0, 1), (1, 0))
      copy.assignees[0].allocation = 0.9
      assert original.assignees == [Assignee("田中", 0.5)]
  ```
- `test/test_dashboard.py` の `stranger.assignee = "鈴木"` は `stranger.assignees = [Assignee("鈴木")]`。
- `test/test_gantt.py:586` の `project.tasks[1].allocation = 0.4` は `project.tasks[1].assignees[0].allocation = 0.4`。`test_gantt.py:642-647` の `assignee=assignee` は `assignees=[Assignee(assignee)]`。
- `test/test_timeline.py:553` の、担当のないタスクの `allocation=0.6` は削除する(担当がなければ意味がない)。
- `test/test_handoff.py:28` の `kwargs.setdefault("assignee", "田中")` は `kwargs.setdefault("assignees", [Assignee("田中")])`。`:65-66` の `assignee="鈴木"` は `assignees=[Assignee("鈴木")]`、`assignee=None` は `assignees=[]`。`:110` の `allocation=0.25` を含むタスクは `assignees=[Assignee("田中", 0.25)]` にする(その行の `task(...)` が既定の担当者を持つので、`assignees=` を明示して上書きする)。
- `test/test_storage.py` の `test_allocation_roundtrip_and_default`・`test_file_without_allocation_loads_as_one`・`test_load_rejects_an_invalid_allocation`・`test_load_accepts_the_ratio_and_allocation_boundaries` のうち、古いキー(`allocation`)を `pop`・`update` しているもの(`_rewrite(... pop("allocation"))`、`update(allocation=value)`)は、Step 1 の `test_old_keys_*` に置き換えられたので削除する。往復と境界のテストは、`assignees=[Assignee(...)]` に移行済みのものを残す。
- `test/test_checkpoint.py:70-79` は、保存済みの辞書に `"assignee"`・`"allocation"`(古いキー)を入れて読む検証なので、そのまま残す(読み取りは別名で通る)。

規則: **読み取りの `task.assignee`・`task.allocation` は、別名があるので、この Task では直さない**。`replace(...)`・コンストラクタ・属性への代入だけを直す。

- [ ] **Step 8: 全体が通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -5 && uvx ty check src | tail -2`
Expected: 全件 PASS(件数は 1,592 から増える)、`ty` の指摘なし。

- [ ] **Step 9: コミット**

```bash
git add -A
git commit -m "refactor: タスクの担当を assignees に一本化し、古い形式を読み込みで移行する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 換算率の合算と、担当者ごとの割り当て超過(`timeline.py`)

**Files:**
- Modify: `src/projectapp/timeline.py`(`counted_span`・`overallocations`・`clip_overloads`・`conversion_rate`)
- Test: `test/test_timeline.py`

**Interfaces:**
- Consumes: `Assignee`、`Task.assignees`、`Task.assignee_names`(Task 1)。
- Produces:
  - `counted_assignees(task: Task, project: Project) -> list[Assignee]`(メンバーにいる担当者だけ)
  - `assignees_rate(assignees: list[Assignee], members: list[Member]) -> float`(担当者全員の換算率の合計。誰も数えられなければ 1.0)
  - `conversion_rate(task, project) -> float`(上を使う。シグネチャは今のまま)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py` の `test_conversion_rate_uses_the_member_ratio_and_the_task_allocation` の下に足す(`Assignee`・`assignees_rate`・`counted_assignees` を import する)。

```python
def test_conversion_rate_adds_up_every_assignee() -> None:
    project = member_project(Member("田中", 1.2), Member("鈴木", 1.0))
    task = Task("t", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)])
    assert conversion_rate(task, project) == pytest.approx(1.2 + 0.5)


def test_conversion_rate_skips_assignees_who_are_not_members() -> None:
    project = member_project(Member("田中", 1.2))
    task = Task("t", assignees=[Assignee("田中", 0.5), Assignee("不明", 1.0)])
    assert conversion_rate(task, project) == pytest.approx(0.6)  # 不明は数えない
    nobody = Task("t", assignees=[Assignee("不明", 1.0), Assignee("他", 0.5)])
    assert conversion_rate(nobody, project) == 1.0  # 誰も数えられなければ換算しない


def test_assignees_rate_works_on_a_member_list() -> None:
    members = [Member("A", 1.0), Member("B", 2.0)]
    assert assignees_rate([Assignee("A", 1.0), Assignee("B", 0.25)], members) == pytest.approx(1.5)
    assert assignees_rate([], members) == 1.0


def test_two_assignees_finish_earlier_than_one() -> None:
    project = member_project(Member("田中", 1.0), Member("鈴木", 1.0))
    alone = Task("t", planned_start=FRI_START, effort_hours=13.0, assignees=[Assignee("田中")])
    pair = Task("t", planned_start=FRI_START, effort_hours=13.0, assignees=[Assignee("田中"), Assignee("鈴木")])
    # 13h / 1.0 = 13h → 金6.5h + 月6.5h
    assert effective_end(alone, project, {}) == datetime(2026, 10, 12, 15, 30)
    # 13h / 2.0 = 6.5h → 金のうちに終わる
    assert effective_end(pair, project, {}) == datetime(2026, 10, 9, 15, 30)


def test_counted_assignees_keeps_only_members_in_order() -> None:
    project = member_project(Member("田中"), Member("鈴木"))
    task = Task("t", assignees=[Assignee("不明"), Assignee("鈴木"), Assignee("田中")])
    assert [a.name for a in counted_assignees(task, project)] == ["鈴木", "田中"]


def test_each_assignee_counts_against_his_own_total() -> None:
    a = Task(
        "a", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9),
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.3)],
    )
    b = Task("b", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9), assignees=[Assignee("田中", 0.6)])
    project = member_project(Member("田中"), Member("鈴木"), tasks=[a, b])
    result = overallocations(project, {})
    assert [(o.member, round(o.total, 2)) for o in result] == [("田中", 1.2)]  # 鈴木は 30% だけ


def test_a_task_with_two_overloaded_assignees_is_reported_for_both() -> None:
    a = Task(
        "a", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9),
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.6)],
    )
    b = Task(
        "b", planned_start=datetime(2026, 10, 7), planned_end=datetime(2026, 10, 12),
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.6)],
    )
    project = member_project(Member("田中"), Member("鈴木"), tasks=[a, b])
    overloads = overallocations(project, {})
    assert sorted(o.member for o in overloads) == ["田中", "鈴木"]
    assert sorted(o.member for o in clip_overloads(a, project, {}, overloads)) == ["田中", "鈴木"]


def test_clip_overloads_ignores_members_who_are_not_on_the_task() -> None:
    a = alloc_task("a", 5, 9, 0.6)
    b = alloc_task("b", 7, 12, 0.6)
    other = Task("o", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 12), assignees=[Assignee("鈴木", 0.5)])
    project = member_project(Member("田中"), Member("鈴木"), tasks=[a, b, other])
    overloads = overallocations(project, {})
    assert clip_overloads(other, project, {}, overloads) == []


def test_an_assignee_who_is_not_a_member_is_not_counted_for_overload() -> None:
    a = Task("a", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9), assignees=[Assignee("不明", 0.7)])
    b = Task("b", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9), assignees=[Assignee("不明", 0.7)])
    project = member_project(Member("田中"), tasks=[a, b])
    assert overallocations(project, {}) == []
    assert counted_span(a, project, {}) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_timeline.py -q 2>&1 | tail -8`
Expected: `ImportError: cannot import name 'assignees_rate'`(または `counted_assignees`)。

- [ ] **Step 3: 実装する**

`src/projectapp/timeline.py`:

- `from projectapp.models import (...)` に `Assignee`・`Member` を足す(既に import されていれば足さない)。
- `counted_span` の前に足す:

```python
def counted_assignees(task: Task, project: Project) -> list[Assignee]:
    """換算率と割り当ての合計に数える担当者(メンバーにいる人だけ。タスクの並び順)。"""
    names = {m.name for m in project.members}
    return [a for a in task.assignees if a.name in names]
```

- `counted_span` の先頭の判定を直す(`if not task.assignee or task.status is Status.DONE:` と、`if all(m.name != task.assignee for m in project.members): return None` の 2 か所):

```python
    if task.status is Status.DONE or not counted_assignees(task, project):
        return None
    start = effective_start(task, project, holidays, schedule)
    if start is None:
        return None
    end = effective_end(task, project, holidays, schedule)
```
(`if all(m.name != task.assignee …)` の 2 行は削除する。`end <= start` の判定は今のまま。)

- `overallocations` のループを直す:

```python
    for task in project.all_tasks():
        counted = counted_span(task, project, holidays, schedule)
        if counted is not None:
            for assignee in counted_assignees(task, project):
                spans.setdefault(assignee.name, []).append((*counted, assignee.allocation))
```

- `clip_overloads` の `if overload.member != task.assignee:` を `if overload.member not in task.assignee_names:` にする。
- `conversion_rate` を置き換え、`assignees_rate` を足す:

```python
def assignees_rate(assignees: list[Assignee], members: list[Member]) -> float:
    """担当者全員の換算率(相対比率 × 割り当て率)の合計。メンバーにいない担当者は数えない。
    誰も数えられなければ 1.0(換算しない)。"""
    by_name = {m.name: m for m in members}
    rates = [combine_rate(by_name[a.name].ratio, a.allocation) for a in assignees if a.name in by_name]
    return sum(rates) if rates else 1.0


def conversion_rate(task: Task, project: Project) -> float:
    return assignees_rate(task.assignees, project.members)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: 複数の担当者の換算率を合算し、割り当て超過を担当者ごとに数える

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 編集ダイアログの担当者の行(`forms.py`・`task_dialog.py`)

**Files:**
- Modify: `src/projectapp/forms.py`(`build_task` の引数と検証)
- Modify: `src/projectapp/task_dialog.py`(`AssigneeFields`、換算の説明、`current()`・`save()`・`apply_kind`)
- Test: `test/test_forms.py`、`test/test_checkpoint.py`、`test/test_task_dialog.py`

**Interfaces:**
- Consumes: `Assignee`(Task 1)、`assignees_rate`(Task 2)。
- Produces:
  - `build_task(..., assignees: list[tuple[str, float | None]] | None = None, ...)`。各行は `(メンバー名, 割り当て率の%)`。`assignee`・`allocation_percent` の引数はなくなる。
  - ダイアログのマーカー: 1 行目は `task-assignee`(メンバー)・`task-allocation`(割り当て率)。n 行目(n≥2)は `task-assignee-{n}`・`task-allocation-{n}`。削除は `task-assignee-remove`(1 行目)・`task-assignee-remove-{n}`。追加は `task-assignee-add`。

- [ ] **Step 1: `build_task` の失敗するテストを書く**

`test/test_forms.py`:

- `make` の既定の辞書(`"assignee": "",` と `"allocation_percent": 100.0,` の 2 行、48〜49 行目付近)を `"assignees": [],` の 1 行にする。
- `:56` の `make(name="  設計  ", assignee=" 佐藤 ")` を `make(name="  設計  ", assignees=[(" 佐藤 ", 100.0)])` に、`:61` の `task.assignee == "佐藤"` を `task.assignee_names == ["佐藤"]` にする。
- `:64-66` の `make(planned_start="", planned_end="", assignee="  ", effort_hours=None)` を `assignees=[("  ", None)]` にし、検証を `(task.planned_start, task.planned_end, task.assignees, task.effort_hours) == (None, None, [], 0.0)` にする。
- `:645` 付近の `assignee="",` の行を `assignees=[],` にする。
- `:730-748` の 5 つのテスト(`test_allocation_*`、`test_a_bad_allocation_*`)を、次の内容に置き換える:

```python
def test_allocation_is_stored_as_a_fraction() -> None:
    task = make(assignees=[("田中", 60.0)])
    assert task.assignees == [Assignee("田中", pytest.approx(0.6))]


def test_blank_rows_are_dropped() -> None:
    assert make(assignees=[("", 60.0), ("  ", None)]).assignees == []


@pytest.mark.parametrize("percent", [None, 0.0, 0.5, 100.5, float("nan"), float("inf")])
def test_a_bad_allocation_is_rejected_for_a_chosen_member(percent: float | None) -> None:
    with pytest.raises(ValueError, match="割り当て率"):
        make(assignees=[("田中", percent)])


@pytest.mark.parametrize("percent", [1.0, 100.0])
def test_allocation_boundaries_are_accepted(percent: float) -> None:
    assert make(assignees=[("田中", percent)]).assignees[0].allocation == pytest.approx(percent / 100)


def test_several_assignees_keep_their_order_and_allocations() -> None:
    task = make(assignees=[("田中", 100.0), ("鈴木", 50.0)])
    assert task.assignees == [Assignee("田中", 1.0), Assignee("鈴木", 0.5)]


def test_the_same_member_twice_is_rejected() -> None:
    with pytest.raises(ValueError, match="重複"):
        make(assignees=[("田中", 100.0), (" 田中 ", 50.0)])
```
(`Assignee` を import する。)

`test/test_checkpoint.py`: `:173-174` の `"assignee": "",` と `"allocation_percent": None,` を `"assignees": [],` に、`:186-187` の `assignee="佐藤", allocation_percent=500.0,` を `assignees=[("佐藤", 500.0)],` に、`:217` の `allocation_percent=100.0,` を削除する。`:79` と `:193` の `task.assignee, task.allocation` の組は `task.assignees` に直し、期待値の `None, 1.0` を `[]` 1 つにする(たとえば `(task.effort_hours, task.assignees, task.actuals) == (0.0, [], [])`)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py test/test_checkpoint.py -q 2>&1 | tail -8`
Expected: `TypeError: build_task() got an unexpected keyword argument 'assignees'`。

- [ ] **Step 3: `forms.build_task` を直す**

引数の `assignee: str,` と `allocation_percent: float | None,` の 2 行を、キーワード引数の並びの最後(`urls` の下)の `assignees: list[tuple[str, float | None]] | None = None,` 1 行にする。`assignee_name = assignee.strip()` から `allocation = round(...)` までの検証ブロックを削除し、次を同じ位置に置く:

```python
    assignee_list = _build_assignees(assignees or [])
```
`replace(base, ...)` の `assignees=[Assignee(assignee_name, allocation)] if assignee_name else [],` を `assignees=assignee_list,` にする。ファイルの `build_task` の上に足す:

```python
def _build_assignees(rows: list[tuple[str, float | None]]) -> list[Assignee]:
    """担当者の行を検証して Assignee にする。メンバーを選んでいない行は捨てる。"""
    result: list[Assignee] = []
    seen: set[str] = set()
    for raw_name, percent in rows:
        name = raw_name.strip()
        if not name:
            continue
        if name in seen:
            raise ValueError(f"担当者が重複しています: {name}")
        seen.add(name)
        if (
            percent is None
            or not isfinite(percent)
            or not MIN_ALLOCATION * 100 <= percent <= MAX_ALLOCATION * 100
        ):
            raise ValueError(
                f"割り当て率は{MIN_ALLOCATION * 100:g}〜{MAX_ALLOCATION * 100:g}%で入力してください"
            )
        result.append(Assignee(name, round(percent / 100, 4)))
    return result
```

- [ ] **Step 4: フォームのテストが通ることを確かめる**

Run: `uv run pytest test/test_forms.py test/test_checkpoint.py -q 2>&1 | tail -4`
Expected: PASS。(`task_dialog.py` はまだ古い引数で `build_task` を呼ぶので、`test_task_dialog.py` は落ちる。次の Step で直す。)

- [ ] **Step 5: ダイアログの失敗するテストを書く**

`test/test_task_dialog.py` の、`assignee`・`allocation` を扱う既存のテスト(`test_the_assignee_is_chosen_from_the_members` から `test_an_assignee_missing_from_the_members_is_kept_when_saving` まで、789〜898 行目付近)を、次のとおり直す。1 行目のマーカー(`task-assignee`・`task-allocation`)は変わらないので、そのまま使える。

- `test_the_assignee_is_chosen_from_the_members`: 最後の検証を `assert saved[0].assignees == [Assignee("田中", 1.0)]` にする。
- `test_without_an_assignee_the_allocation_is_disabled_and_saved_as_one`: 最後の検証を `assert saved[0].assignees == []` にする。(テスト名は `..._and_nobody_is_saved` に直す。)
- `test_the_allocation_is_enabled_with_an_assignee_and_saved`: 最後の検証を `assert saved[0].assignees[0].allocation == pytest.approx(0.6)` にする。
- `test_returning_the_assignee_to_none_saves_an_allocation_of_one`: タスクを `Task("旧", assignees=[Assignee("田中", 0.5)])` にし、最後の検証を `assert saved[0].assignees == []` にする。(名前は `test_returning_the_assignee_to_none_saves_nobody`。)
- `test_the_conversion_is_shown_with_an_assignee_and_effort`: 期待する文字列を `"換算率 96%(田中 120%×80%)→ 15h は約 2.4日分"` にする。
- `test_an_assignee_missing_from_the_members_is_kept_when_saving`: タスクを `Task("旧", assignees=[Assignee("不明", 0.5)])` にし、最後の 2 つの検証を `assert saved[0].assignees == [Assignee("不明", pytest.approx(0.5))]` にする。
- `:1463` 付近の `assignee="佐藤",`(チェックポイントのテスト)を `assignees=[Assignee("佐藤")],` にし、`:1473` の `result.assignee` を `result.assignees` にして、期待値の `None` を `[]` にする。

そのうえで、末尾に新しいテストを足す:

```python
SATO = Member("佐藤", 1.0)


async def test_a_second_assignee_row_can_be_added_and_saved(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
        user.find(marker="task-allocation-2").elements.pop().set_value(50)
    user.find(marker="task-save").click()
    assert saved[0].assignees == [Assignee("田中", 1.0), Assignee("鈴木", pytest.approx(0.5))]


async def test_a_member_chosen_in_one_row_is_not_offered_in_the_others(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA, SUZUKI, SATO])
    await open_dialog(user)
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    second = user.find(marker="task-assignee-2").elements.pop()
    assert second.options == {"": "(なし)", "鈴木": "鈴木", "佐藤": "佐藤"}
    first = user.find(marker="task-assignee").elements.pop()
    assert first.options == {"": "(なし)", "田中": "田中", "鈴木": "鈴木", "佐藤": "佐藤"}


async def test_removing_a_row_returns_the_member_to_the_others(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, members=[TANAKA, SUZUKI])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
    user.find(marker="task-assignee-remove-2").click()
    user.find(marker="task-save").click()
    assert saved[0].assignees == []


async def test_existing_assignees_open_as_rows(user: User) -> None:
    task = Task("旧", assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.25)])
    mount_dialog(task, [], members=[TANAKA, SUZUKI])
    await open_dialog(user)
    assert user.find(marker="task-assignee").elements.pop().value == "田中"
    assert user.find(marker="task-allocation").elements.pop().value == 50
    assert user.find(marker="task-assignee-2").elements.pop().value == "鈴木"
    assert user.find(marker="task-allocation-2").elements.pop().value == 25


async def test_the_conversion_adds_up_every_assignee(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    await open_dialog(user)
    conversion = user.find(marker="task-conversion").elements.pop()
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
        user.find(marker="task-allocation-2").elements.pop().set_value(50)
    user.find(marker="task-effort").clear().type("19.5")
    # 換算率 1.0×100% + 1.0×50% = 150% → 19.5h / 1.5 / 6.5h = 2.0日
    assert conversion.text == "換算率 150%(田中 100%×100% + 鈴木 100%×50%)→ 19.5h は約 2.0日分"


async def test_two_assignees_shorten_the_computed_end(user: User) -> None:
    mount_dialog(None, [], members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    await open_dialog(user)
    user.find(marker="task-start-date").type("2026-10-09")
    with user.client:
        user.find(marker="task-assignee").elements.pop().set_value("田中")
    user.find(marker="task-assignee-add").click()
    with user.client:
        user.find(marker="task-assignee-2").elements.pop().set_value("鈴木")
    user.find(marker="task-effort").clear().type("13")
    # 13h / 2.0 = 6.5h → 金のうちに終わる
    assert user.find(marker="task-end-computed").elements.pop().value == "2026-10-09 15:30"


async def test_adding_a_row_counts_as_a_change_on_close(user: User) -> None:
    mount_dialog(Task("旧"), [], members=[TANAKA])
    await open_dialog(user)
    user.find(marker="task-assignee-add").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_the_assignee_rows_are_hidden_for_a_checkpoint(user: User) -> None:
    mount_dialog(None, [], members=[TANAKA])
    await open_dialog(user)
    await user.should_see(marker="task-assignee-add")
    with user.client:
        user.find(marker="task-kind").elements.pop().set_value(TaskKind.CHECKPOINT)
    await user.should_not_see(marker="task-assignee-add")
```

- [ ] **Step 6: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q 2>&1 | tail -8`
Expected: `build_task` に古い引数 `assignee` が渡されて `TypeError`(まだ `task_dialog.py` が古いため)。

- [ ] **Step 7: `task_dialog.py` を実装する**

1. import: `from projectapp.models import (...)` に `Assignee` を足す。`from projectapp.timeline import combine_rate, computed_end, effort_days` を `from projectapp.timeline import assignees_rate, combine_rate, computed_end, effort_days` にする。`dataclass` が未 import なら `from dataclasses import dataclass` を足す。

2. `UrlFields` の下(`open_task_dialog` の上)に足す:

```python
NO_MEMBER = ""
AssigneeRow = tuple[str, float | None]  # (メンバー名, 割り当て率の%)


@dataclass
class AssigneeItem:
    row: ui.row
    member: ui.select
    allocation: ui.number


class AssigneeFields:
    """タスクの担当者の節。1 行が メンバー・割り当て率(%)・削除。メンバーは行をまたいで重ならない。"""

    def __init__(self, assignees: list[Assignee], members: list[Member], on_change: Callable[[], object]) -> None:
        self.members = members
        self.on_change = on_change
        self.items: list[AssigneeItem] = []
        self.counter = 0
        self.container = ui.column().classes("w-full gap-1")
        with self.container:
            ui.label("担当者").classes("text-caption text-grey")
            self.box = ui.column().classes("w-full gap-1")
            for assignee in assignees or [None]:
                self._add_row(assignee)
            ui.button("担当者を追加", icon="add", on_click=self._add_blank).props("flat dense").mark(
                "task-assignee-add"
            )
        self._sync()

    def _add_blank(self) -> None:
        self._add_row(None)
        self._sync()
        self.on_change()

    def _add_row(self, assignee: Assignee | None) -> None:
        self.counter += 1
        suffix = "" if self.counter == 1 else f"-{self.counter}"
        name = NO_MEMBER if assignee is None else assignee.name
        fraction = 1.0 if assignee is None else assignee.allocation
        with self.box:
            with ui.row().classes("w-full items-center no-wrap gap-4") as row:
                member = ui.select({NO_MEMBER: "(なし)", **({name: name} if name else {})}, label="担当者", value=name)
                member.classes("flex-1").mark(f"task-assignee{suffix}")
                allocation = ui.number(
                    "割り当て率(%)",
                    value=round(fraction * 100, 2),
                    min=MIN_ALLOCATION * 100,
                    max=MAX_ALLOCATION * 100,
                    step=5,
                )
                allocation.classes("flex-1").mark(f"task-allocation{suffix}")
                item = AssigneeItem(row, member, allocation)
                ui.button(icon="delete", on_click=lambda: self._remove(item)).props(
                    "flat dense color=negative"
                ).mark(f"task-assignee-remove{suffix}")
        member.on_value_change(lambda _e: self._changed())
        allocation.on_value_change(lambda _e: self.on_change())
        self.items.append(item)

    def _remove(self, item: AssigneeItem) -> None:
        self.items.remove(item)
        item.row.delete()
        self._sync()
        self.on_change()

    def _changed(self) -> None:
        self._sync()
        self.on_change()

    def _options(self, item: AssigneeItem) -> dict[str, str]:
        taken = {other.member.value for other in self.items if other is not item}
        own = item.member.value
        names = [m.name for m in self.members if m.name == own or m.name not in taken]
        return {NO_MEMBER: "(なし)", **{n: n for n in names}}

    def _sync(self) -> None:
        for item in self.items:
            item.member.set_options(self._options(item), value=item.member.value)
            item.allocation.set_enabled(bool(item.member.value))

    def rows(self) -> list[AssigneeRow]:
        return [(item.member.value or "", item.allocation.value) for item in self.items]

    def state(self) -> tuple[AssigneeRow, ...]:
        return tuple(self.rows())

    def chosen(self) -> list[tuple[Member, float]]:
        """メンバーを選んだ行の、(メンバー, 割り当ての割合)。"""
        by_name = {m.name: m for m in self.members}
        return [(by_name[name], (percent or 100) / 100) for name, percent in self.rows() if name in by_name]
```

3. `open_task_dialog` の冒頭(`member_list = ...` から `initial_rate = ...` まで、604〜610 行目付近)を置き換える:

```python
    member_list = list(members or [])
    for assignee in initial.assignees:  # 一覧にいない担当者も、保存で失わない(相対比率は 100% とみなす)
        if all(m.name != assignee.name for m in member_list):
            member_list.append(Member(assignee.name, 1.0))
    initial_rate = assignees_rate(initial.assignees, member_list)
```
(`initial_member` は、この後の `value=initial.assignee if initial_member else ""` でしか使っていなかった。次の 4. で消える。)

4. `assignee_row = ui.row()…` から `refresh_conversion()` の呼び出しまで(632〜681 行目付近。`conversion = ui.label(…)`・`current_member`・`refresh_conversion`・`on_effort_change`・`effort.on_value_change(…)`・`assignee.on_value_change(…)`・`allocation.on_value_change(…)`・`refresh_conversion()` を含む)を、次の全体で置き換える。画面の順は「担当者の行 → 換算の説明」。`AssigneeFields` のコールバックは、あとで定義する `refresh_conversion` を呼ぶ(呼ばれるのは作成後なので、問題ない):

```python
        assignee_fields = AssigneeFields(initial.assignees, member_list, lambda: refresh_conversion())
        conversion = ui.label("").classes("text-caption text-grey").mark("task-conversion")

        def refresh_conversion(_event: object = None) -> None:
            chosen = assignee_fields.chosen()
            rate = sum(combine_rate(m.ratio, f) for m, f in chosen) if chosen else 1.0
            fields.set_rate(rate)
            days = effort_days(effort.value or 0.0, rate, daily_hours) if chosen else None
            if not chosen or days is None:
                conversion.set_text("")
                return
            detail = " + ".join(f"{m.name} {m.ratio * 100:g}%×{f * 100:g}%" for m, f in chosen)
            conversion.set_text(f"換算率 {rate * 100:g}%({detail})→ {effort.value:g}h は約 {days:.1f}日分")

        def on_effort_change(e: object) -> None:
            fields.set_effort(getattr(e, "value", None))
            refresh_conversion()

        effort.on_value_change(on_effort_change)
        refresh_conversion()
```

5. `has_normal_data` の `or initial.assignee` を `or initial.assignees` にする。`apply_kind` の `for widget in (fields.first_row, effort, assignee_row, conversion, actual_box):` の `assignee_row` を `assignee_fields.container` にする。

6. `current()` の `assignee.value,` と `allocation.value,` の 2 行を `assignee_fields.state(),` 1 行にする。

7. `save()` の `build_task(...)` の `assignee=assignee.value or "",` と `allocation_percent=allocation.value,` の 2 行を `assignees=assignee_fields.rows(),` 1 行にする。

- [ ] **Step 8: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -6 && uvx ty check src | tail -2`
Expected: 全件 PASS、`ty` の指摘なし。落ちるテストがあれば、マーカーの付け方(1 行目に接尾辞がないこと)と、`_sync` が値を保つことを確かめる。

- [ ] **Step 9: コミット**

```bash
git add -A
git commit -m "feat: 編集ダイアログで複数の担当者を行で追加・削除できるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: メンバーの削除制限と、保存時の超過の通知(`views.py`)

**Files:**
- Modify: `src/projectapp/views.py`(`assigned_count`・`warn_overallocation`)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: `Task.assignee_names`(Task 1)、`overallocations`・`clip_overloads`(Task 2)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の、メンバーの改名のテスト(`test_renaming_a_member_renames_the_assignee_of_its_tasks`)の近くに足す。ファイルにある `make_view`・`wait_until`・`user.open("/")` の流れで、既存のテストと同じ書き方にそろえる(下は、そのテストが使っている形)。

```python
async def test_assigned_count_counts_tasks_where_the_member_is_one_of_the_assignees(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.tasks = [
        Task("a", assignees=[Assignee("田中"), Assignee("鈴木")]),
        Task("b", assignees=[Assignee("鈴木")]),
        Task("c"),
    ]
    assert view.assigned_count("田中") == 1
    assert view.assigned_count("鈴木") == 2
    assert view.assigned_count("佐藤") == 0


async def test_renaming_a_member_renames_every_assignee_entry(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("A"), Member("B")]
    view.project.tasks = [Task("t", assignees=[Assignee("A", 0.5), Assignee("B", 0.25)])]
    view.apply_members([Member("B"), Member("A")], {"A": "B", "B": "A"})  # 入れ替え
    assert view.project.tasks[0].assignees == [Assignee("B", 0.5), Assignee("A", 0.25)]


async def test_saving_a_task_warns_for_each_overloaded_assignee(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    make_view(tmp_path, views)
    await user.open("/")
    view = views[0]
    view.project.members = [Member("田中"), Member("鈴木")]

    def task(name: str, start: int, end: int) -> Task:
        return Task(
            name,
            planned_start=datetime(2026, 10, start),
            planned_end=datetime(2026, 10, end),
            assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.6)],
        )

    view.save_task(None, None, task("a", 5, 9))
    view.save_task(None, None, task("b", 7, 12))
    await user.should_see("田中 の割り当てが最大120%になる期間があります")
    await user.should_see("鈴木 の割り当てが最大120%になる期間があります")
```
(`Assignee` を import する。`datetime`・`Member`・`MainView`・`save_cache` は、このファイルに既にある。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "assigned_count_counts or renaming_a_member_renames_every or warns_for_each" 2>&1 | tail -8`
Expected: 1 つ目は `assert 1 == 2`(鈴木の件数が 1 になる)、3 つ目は「鈴木 の割り当て…」が見つからずに失敗する。2 つ目は Task 1 で直した改名の処理を検証するので、すぐ通る(挙動を固定するためのテスト)。

- [ ] **Step 3: 実装する**

`assigned_count`:

```python
    def assigned_count(self, name: str) -> int:
        return sum(1 for task in self.project.all_tasks() if name in task.assignee_names)
```

`warn_overallocation`:

```python
    def warn_overallocation(self, task: Task) -> None:
        """保存したタスクが担当者の割り当て合計の超過に関わるなら、担当者ごとに通知する(保存は妨げない)。"""
        if not task.assignees:
            return
        overloads = overallocations(self.project, self.holidays)
        mine = clip_overloads(task, self.project, self.holidays, overloads)
        for name in task.assignee_names:
            peaks = [o.total for o in mine if o.member == name]
            if peaks:
                ui.notify(
                    f"{name} の割り当てが最大{round(max(peaks) * 100)}%になる期間があります",
                    type="warning",
                )
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: メンバーの削除制限と超過の通知を、複数の担当者に対応させる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 絞り込みと、複数のチップ(`filtering.py`・`gantt.py`)

**Files:**
- Modify: `src/projectapp/filtering.py`
- Modify: `src/projectapp/gantt.py`(`task_chips`)
- Test: `test/test_filtering.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: `Task.assignees`・`Task.assignee_names`。
- Produces: マーカー `task-assignee-{key}-{ti}`(先頭のチップ)、`task-assignee-{key}-{ti}-{n}`(2 人目以降。n は 1 から)、`task-assignee-more-{key}-{ti}`(`+n`)。定数 `MAX_ASSIGNEE_CHIPS = 3`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_filtering.py` に足す(`Assignee` を import する):

```python
def test_a_task_matches_when_the_member_is_any_of_its_assignees() -> None:
    task = Task("設計", assignees=[Assignee("鈴木"), Assignee("田中")])
    assert matches(task, TaskFilter(assignee="田中"))
    assert matches(task, TaskFilter(assignee="鈴木"))
    assert not matches(task, TaskFilter(assignee="佐藤"))
```

`test/test_gantt.py`: 既存の `test_assignee_chip_shows_the_first_character_and_the_name_on_hover`(1912 行目付近。Task 1 の移行で `assignees=[Assignee("山田太郎")]` になっている)は、ツールチップが名前と割り当て率になるので、`assert tooltips_targeting(who) == ["山田太郎"]` を `["山田太郎 100%"]` に直す。そのうえで、すぐ下に足す(`mount`・`project_with`・`chip`・`tooltips_targeting` は、このファイルのもの。セクション 0 のタスク 0 のマーカーは `…-0-0`):

```python
async def test_several_assignees_get_one_chip_each(user: User) -> None:
    mount(project_with(Task("設計", assignees=[Assignee("山田", 1.0), Assignee("鈴木", 0.5)])))
    await user.open("/")
    first, second = chip(user, "task-assignee-0-0"), chip(user, "task-assignee-0-0-1")
    assert (first.text, second.text) == ("山", "鈴")
    assert tooltips_targeting(first) == ["山田 100%"]
    assert tooltips_targeting(second) == ["鈴木 50%"]


async def test_more_than_three_assignees_are_summarized_in_a_plus_chip(user: User) -> None:
    names = ["山田", "鈴木", "佐藤", "高橋", "伊藤"]
    mount(project_with(Task("設計", assignees=[Assignee(n, 0.5) for n in names])))
    await user.open("/")
    assert chip(user, "task-assignee-0-0-2").text == "佐"  # 3 人目まで
    await user.should_not_see(marker="task-assignee-0-0-3")
    more = chip(user, "task-assignee-more-0-0")
    assert more.text == "+2"
    assert tooltips_targeting(more) == ["高橋 50%\n伊藤 50%"]


async def test_exactly_three_assignees_have_no_plus_chip(user: User) -> None:
    mount(project_with(Task("設計", assignees=[Assignee(n) for n in ("山田", "鈴木", "佐藤")])))
    await user.open("/")
    await user.should_see(marker="task-assignee-0-0-2")
    await user.should_not_see(marker="task-assignee-more-0-0")


async def test_a_task_without_assignees_has_no_chip(user: User) -> None:
    mount(project_with(Task("設計")))
    await user.open("/")
    await user.should_not_see(marker="task-assignee-0-0")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_filtering.py test/test_gantt.py -q -k "several_assignees or three_assignees or any_of_its or chip_shows or without_assignees_has_no" 2>&1 | tail -8`
Expected: 絞り込みは `assert not matches(...)`(2 人目で一致しない)、チップはマーカーが見つからない、で失敗する。

- [ ] **Step 3: 実装する**

`src/projectapp/filtering.py` の `matches`:

```python
    if task_filter.assignee is not None and task_filter.assignee not in task.assignee_names:
        return False
```

`src/projectapp/gantt.py`: 定数を `ASSIGNEE_CHIP_STYLE` の近くに足す。

```python
MAX_ASSIGNEE_CHIPS = 3  # これを超える担当者は、「+n」のチップ 1 つにまとめる
```

`task_chips` の `if task.assignee:` のブロックを置き換える:

```python
        for n, assignee in enumerate(task.assignees[:MAX_ASSIGNEE_CHIPS]):
            suffix = "" if n == 0 else f"-{n}"
            ui.label(assignee.name[0]).style(ASSIGNEE_CHIP_STYLE).tooltip(
                f"{assignee.name} {round(assignee.allocation * 100)}%"
            ).mark(f"task-assignee-{key}-{ti}{suffix}")
        rest = task.assignees[MAX_ASSIGNEE_CHIPS:]
        if rest:
            ui.label(f"+{len(rest)}").style(ASSIGNEE_CHIP_STYLE).tooltip(
                "\n".join(f"{a.name} {round(a.allocation * 100)}%" for a in rest)
            ).mark(f"task-assignee-more-{key}-{ti}")
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -3 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "feat: 絞り込みを複数の担当者に対応させ、担当者ごとのチップを出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ダッシュボードと担当者向けの書き出し(`dashboard.py`・`handoff.py`)

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_progress` の `OverdueRow`、`summarize_loads`、`summarize_workload`、`summarize_due`)
- Modify: `src/projectapp/handoff.py`(`tasks_for`・`_estimate_hours`・呼び出し)
- Test: `test/test_dashboard.py`、`test/test_handoff.py`

**Interfaces:**
- Consumes: `counted_assignees`・`assignees_rate`・`conversion_rate`(Task 2)。
- Produces: `dashboard.assignee_label(task) -> str | None`(名前を「、」でつなぐ。担当なしは None)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` に足す(`Assignee`・必要なら `assignee_label` を import する。`project_of`・`span_task` などの補助関数は、このファイルのものを使う。期間・`NOW`・`summarize_*` の呼び方は、周りのテストと同じにする):

```python
def test_assignee_label_joins_the_names() -> None:
    from projectapp.dashboard import assignee_label

    assert assignee_label(Task("t")) is None
    assert assignee_label(Task("t", assignees=[Assignee("田中")])) == "田中"
    assert assignee_label(Task("t", assignees=[Assignee("田中"), Assignee("鈴木")])) == "田中、鈴木"


def test_load_counts_each_assignee_with_his_own_allocation() -> None:
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 6, 9),
        planned_end=datetime(2026, 10, 6, 17),
        assignees=[Assignee("田中", 0.6), Assignee("鈴木", 0.3)],
    )
    other = Task("b", planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 6, 17), assignees=[Assignee("田中", 0.6)])
    project = Project("p", members=[Member("田中"), Member("鈴木")], tasks=[task, other])
    loads = summarize_loads(project, Period(date(2026, 10, 6), date(2026, 10, 6)), {})
    assert loads["田中"].peak == pytest.approx(1.2) and loads["田中"].overloaded_days == 1
    assert loads["鈴木"].peak == pytest.approx(0.3) and loads["鈴木"].overloaded_days == 0


def test_planned_hours_use_each_assignees_allocation() -> None:
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 6, 9),
        planned_end=datetime(2026, 10, 6, 17),
        assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)],
    )
    project = Project("p", daily_hours=6.5, members=[Member("田中"), Member("鈴木")], tasks=[task])
    rows = summarize_workload(project, Period(date(2026, 10, 6), date(2026, 10, 6)), datetime(2026, 10, 8), {})
    assert {r.name: r.planned for r in rows} == {"田中": pytest.approx(6.5), "鈴木": pytest.approx(3.25)}


def test_actual_hours_are_split_by_allocation() -> None:
    task = Task(
        "a",
        assignees=[Assignee("田中", 0.75), Assignee("鈴木", 0.25), Assignee("不明", 0.0 + 1.0)],
        actuals=[Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 11))],
    )
    project = Project("p", members=[Member("田中"), Member("鈴木")], tasks=[task])
    rows = summarize_workload(project, Period(date(2026, 10, 6), date(2026, 10, 6)), datetime(2026, 10, 8), {})
    by_name = {r.name: r.actual for r in rows}
    # 2h を 0.75 : 0.25 : 1.0 で按分(合計 2.0)。メンバーでない担当者の分は「未割当」
    assert by_name["田中"] == pytest.approx(0.75)
    assert by_name["鈴木"] == pytest.approx(0.25)
    assert by_name[UNASSIGNED] == pytest.approx(1.0)
    assert sum(by_name.values()) == pytest.approx(2.0)  # タスク全体の実績が変わらない


def test_overdue_and_due_rows_show_every_assignee() -> None:
    late = Task("late", status=Status.RUNNING, deadline=datetime(2026, 10, 6, 17), assignees=[Assignee("田中"), Assignee("鈴木")])
    project = project_of(late)
    now = datetime(2026, 10, 8, 9)
    assert summarize_progress(project, now, {}).overdue[0].assignee == "田中、鈴木"
```
(`summarize_progress` の名前・引数は、このファイルの既存のテストで使われているものに合わせる。`Period`・`UNASSIGNED`・`Actual`・`date` も import されているものを使う。)

`test/test_handoff.py` に足す:

```python
def test_a_task_is_exported_for_every_assignee() -> None:
    shared = task("共同", assignees=[Assignee("田中"), Assignee("鈴木")])
    project = make_project(shared, members=[Member("田中", 1.0), Member("鈴木", 1.0)])
    assert [t.name for t in tasks_for(project, "田中")] == ["共同"]
    assert [t.name for t in tasks_for(project, "鈴木")] == ["共同"]


def test_the_estimate_is_the_assignees_own_share_of_the_effort() -> None:
    shared = task("共同", effort_hours=15.0, assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)])
    members = [Member("田中", 1.0), Member("鈴木", 1.0)]
    project = make_project(shared, members=members)
    # 換算率は 1.0 + 0.5 = 1.5。田中は 15 × 1.0 / 1.5 = 10h、鈴木は 15 × 0.5 / 1.5 = 5h
    assert build_todos(project, "田中", {}).data["items"][0]["estimate_hours"] == pytest.approx(10.0)
    assert build_todos(project, "鈴木", {}).data["items"][0]["estimate_hours"] == pytest.approx(5.0)


def test_a_single_assignee_keeps_the_old_estimate() -> None:
    solo = task("単独", effort_hours=13.0, assignees=[Assignee("田中", 0.25)])
    project = make_project(solo, members=[Member("田中", 0.5)])
    assert build_todos(project, "田中", {}).data["items"][0]["estimate_hours"] == pytest.approx(26.0)  # 13 / 0.5
```
(`task(...)`・`make_project(...)`・`build(...)` は、このファイルの補助関数。`build_todos` の呼び方・戻り値の取り出し方は、既存のテストに合わせる。`make_project` が `members=` を受けない場合は、受けるように足す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard.py test/test_handoff.py -q 2>&1 | tail -10`
Expected: `ImportError: cannot import name 'assignee_label'` と、書き出しの見積もりの不一致で失敗する。

- [ ] **Step 3: `dashboard.py` を実装する**

import に `counted_assignees` を足す(`from projectapp.timeline import (...)`)。モジュールの先頭付近(`OverdueRow` の上)に足す:

```python
def assignee_label(task: Task) -> str | None:
    """担当者の名前を「、」でつなぐ。担当なしは None。"""
    return "、".join(task.assignee_names) or None
```
(`Task` を `from projectapp.models import` に足す。)

- `OverdueRow(task.name, task.assignee, limit)` を `OverdueRow(task.name, assignee_label(task), limit)` に、`DueRow(moment, kind, task.name, task.assignee, late)` を `DueRow(moment, kind, task.name, assignee_label(task), late)` にする。
- `summarize_loads` の、`if counted is not None and task.assignee is not None:` のブロックを置き換える:

```python
        if counted is not None:
            for assignee in counted_assignees(task, project):
                spans.setdefault(assignee.name, []).append((*counted, assignee.allocation))
```

- `summarize_workload` のタスクのループを置き換える(`key = …` から `actual[key] += …` まで):

```python
    for task in project.all_tasks():
        start, end = schedule.start(task), schedule.end(task)
        count = (
            sum(1 for day in days if _covers(start, end, day))
            if start is not None and end is not None and end > start
            else 0
        )
        for key, allocation, share in _shares(task, names):
            if count and isfinite(allocation):
                planned[key] += allocation * project.daily_hours * count
            for interval in task.actuals:
                seconds = (min(interval.end or now, high) - max(interval.start, low)).total_seconds()
                if seconds > 0:
                    actual[key] += seconds / 3600 * share
```
`summarize_workload` の上に足す:

```python
def _shares(task: Task, names: list[str]) -> list[tuple[str, float, float]]:
    """(集計先, 割り当て率, 実績の按分の比)。メンバーでない担当者と担当なしは「未割当」。"""
    if not task.assignees:
        return [(UNASSIGNED, 1.0, 1.0)]
    total = sum(a.allocation for a in task.assignees)
    usable = isfinite(total) and total > 0
    return [
        (a.name if a.name in names else UNASSIGNED, a.allocation, a.allocation / total if usable else 1 / len(task.assignees))
        for a in task.assignees
    ]
```

- [ ] **Step 4: `handoff.py` を実装する**

import を `from projectapp.timeline import conversion_rate, effective_end, effective_start` にする(`combine_rate` が他で使われていなければ外す)。

```python
def tasks_for(project: Project, member_name: str) -> list[Task]:
    """選んだ担当の、終了していないタスク(`all_tasks()` の順)。担当者のどれかが、そのメンバーなら対象。"""
    return [t for t in project.all_tasks() if member_name in t.assignee_names and t.status != Status.DONE]
```

```python
def _estimate_hours(task: Task, project: Project, member_name: str) -> float:
    """担当者自身の時間での見積もり = 工数 × そのメンバーの割り当て率 ÷ 担当者全員の換算率の合計。
    担当が 1 人なら 工数 ÷ 相対比率 と同じ。"""
    if not isfinite(task.effort_hours) or task.effort_hours <= 0:
        return 0.0
    mine = next((a for a in task.assignees if a.name == member_name), None)
    allocation = mine.allocation if mine is not None else 1.0
    return round(task.effort_hours * allocation / conversion_rate(task, project), 2)
```
呼び出し側(`"estimate_hours": _estimate_hours(task, project),`)を `_estimate_hours(task, project, member_name)` にする。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -4 && uvx ty check src | tail -1`
Expected: 全件 PASS、`ty` の指摘なし。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "feat: ダッシュボードと担当者向けの書き出しを、複数の担当者に対応させる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 別名を消し、文書を直す

**Files:**
- Modify: `src/projectapp/models.py`(別名 `assignee`・`allocation` を削除)
- Modify: 残っている `task.assignee`・`task.allocation` の読み取り(src とテスト)
- Modify: `CLAUDE.md`、`docs/development.md`、`.claude/MEMORY.md`

- [ ] **Step 1: 残りの参照を洗い出す**

Run:
```bash
grep -rn "\.assignee\b\|\.allocation\b" src | grep -v "assignee_names\|\.assignees\|self.task_filter.assignee\|task_filter.assignee\|row.assignee\|a.allocation\|assignee.allocation\|mine.allocation"
grep -rn "\.assignee\b\|\.allocation\b" test | grep -v "task_filter\|TaskFilter\|row.assignee\|rows\[.\].assignee"
```
Expected: `src` は、`TaskFilter.assignee` と、ダッシュボードの行(`OverdueRow.assignee`・`DueRow.assignee`)だけ。テストには、`task.assignee`・`task.allocation` の読み取りが残っている。

- [ ] **Step 2: 別名を消す**

`src/projectapp/models.py` の「移行用の読み取り専用の別名」のコメントと、`assignee`・`allocation` の 2 つの property を削除する。

- [ ] **Step 3: 落ちるテストを直す**

Run: `uv run pytest -q -n auto 2>&1 | tail -30`。`AttributeError: 'Task' object has no attribute 'assignee'`(または `allocation`)で落ちた箇所を、次の規則で直す:
- `x.assignee == "名前"` → `x.assignee_names == ["名前"]`
- `x.assignee is None` → `x.assignees == []`
- `[t.assignee for t in tasks]` → `[t.assignee_names for t in tasks]`(期待値も、各要素を `["名前"]` か `[]` に)
- `x.allocation == 値` → `x.assignees[0].allocation == 値`
`TaskFilter.assignee` と、ダッシュボードの行の `assignee` は、そのまま。

- [ ] **Step 4: 文書を直す**

`CLAUDE.md`(`projectapp/CLAUDE.md`):
- 「タスクの担当者は`メンバー`から選び、そのタスクに使う`割り当て率`(担当者の時間の1〜100%)を設定できる」の項目を、「タスクには複数の担当者を割り当てられる。担当者ごとに、メンバーから選び、そのタスクに使う`割り当て率`(担当者の時間の1〜100%)を設定する。同じメンバーは 1 つのタスクに 1 回まで」に直す。
- 「工数(時間)は、基準の人が全時間をかけた場合の時間とし、`工数 ÷（相対比率 × 割り当て率）`…」の項目を、「`工数 ÷ 担当者全員の（相対比率 × 割り当て率）の合計`を稼働可能時間（バッファ）の枠に割り当てて`完了予定`を算出する。ダイアログには日数に換算した値と、内訳を表示する」に直す。
- 「同じ担当者の、期間が重なるタスクの`割り当て率`の合計が100%を超える期間」の項目は、「担当者ごとに」であることを明記する(複数の担当者がいるタスクは、それぞれの担当者の合計に数える)。
- 「ダッシュボード」の節: 人ごとの負荷・工数の予定と実績の説明に、「複数の担当者のタスクは、担当者ごとの割り当て率で数え、実績は割り当て率の比で按分する」を足す。
- 「担当者向けファイル」の節: 「見積もりは`工数 ÷ メンバーの相対比率`」を、「見積もりは`工数 × そのメンバーの割り当て率 ÷ 担当者全員の換算率の合計`(担当が 1 人なら`工数 ÷ メンバーの相対比率`)」に直す。「その担当の状態が`終了`以外のタスク」は「担当者のどれかが、そのメンバーの…」に直す。
- ガントチャートの名前の欄のチップの項目: 「担当者(頭1文字…)」を「担当者(頭1文字を担当者の数だけ。4 人目以降は`+n`にまとめる。マウスオーバーで名前と割り当て率)」に直す。

`docs/development.md`: ファイル形式の注意に、「タスクの `assignees`(`name`・`allocation` の配列)。古いキー `assignee`・`allocation` は、`assignees` がないときだけ 1 人のリストとして読む(不正な割り当て率は、担当者がなくても拒否する)。名前が空・重複、割り当て率が範囲外・非有限は読込を拒否する。保存は `assignees` だけ」を足す。モジュール構成の `timeline.py` の行に、`counted_assignees`・`assignees_rate` を足す。

`.claude/MEMORY.md`: 要望 22 を「(完了待ち)実装済み・実機確認待ち。ブランチ `feature/multi-assignee`。設計書 `2026-10-08-multi-assignee-design.md`、実装計画 `2026-10-08-multi-assignee.md`。テスト N 件と `ty` が通る」に書き換える。「最終更新」の行も直す。「ブランチ」の表があれば、`feature/multi-assignee` の行を足す。

- [ ] **Step 5: 全体を確かめる**

Run: `uv run pytest -q -n auto 2>&1 | tail -4 && uvx ty check src | tail -2 && grep -rn "assignee=" src | grep -v "TaskFilter\|task_filter" | head`
Expected: 全件 PASS、`ty` の指摘なし。`grep` が何も出さない(コンストラクタに古い `assignee=` が残っていない)。結果の件数を `.claude/MEMORY.md` に書く。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "refactor: 移行用の別名を消し、複数アサインの文書を直す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: 実機確認をユーザーに依頼する**

ネイティブウィンドウ(`uv run projectapp`)で、次を確認してもらう。結果が届くまで、PR とマージはしない。
1. 編集ダイアログで、担当者の行を追加・削除できる。同じメンバーは 2 行に選べない。換算の説明に、合算の換算率と内訳が出る。
2. 2 人を割り当てると、完了予定が 1 人のときより早くなる。
3. ガントチャートの名前の欄に、担当者の頭文字のチップが並ぶ(4 人目以降は `+n`)。マウスオーバーで名前と割り当て率が出る。
4. 担当者の絞り込みで、担当者のどれかに含まれるタスクが出る。
5. 同じメンバーの割り当て率の合計が 100% を超えると、縞が出て、保存時に担当者ごとに通知が出る。
6. 古いファイル(1 人担当のプロジェクト)を開いて、担当が残る。保存して開き直しても、担当者と割り当て率が残る。
7. ダッシュボードの「人ごとの負荷」「工数の予定と実績」、「担当者へ書き出し」(共同のタスクが両方のメンバーに出る)が、期待どおり。
8. ライト・ダーク両方で、ダイアログの表示が崩れない。拡大・縮小しても崩れない。
