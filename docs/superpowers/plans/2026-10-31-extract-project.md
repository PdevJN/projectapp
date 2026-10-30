# タスクの子プロジェクトへの切り出し 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ガントチャートで選んだ複数のタスクを、新しいプロジェクトファイル(子)に切り出し、親では 1 行の`プロジェクト参照`に置き換える(要望 89)。

**Architecture:** 純関数モジュール`extract.py`(`decompose.py`と同じ作り)が、子の`Project`と、参照行に置き換えた親の複製を返す。画面(`views.py`・`gantt.py`)は、入口・名前入力・保存・通知だけを持つ。参照行をまとめの子にできるよう、`summary.py`の状態・進捗に参照値を渡す。TSV の書き出しは参照行を出す。

**Tech Stack:** Python 3.13・NiceGUI・pytest(`uv run pytest`)・`ty`(`uv run ty check src`)

**Spec:** [`docs/superpowers/specs/2026-10-31-extract-project-design.md`](../specs/2026-10-31-extract-project-design.md)

## Global Constraints

- 言語は日本語。UI の文言・コメント・docstring・テスト名・コミットメッセージも日本語。識別子は英語。
- 周りのコードに合わせる(コメントの量・命名・書き方)。`extract.py`は NiceGUI に依存しない。
- ファイル形式は変えない(`FORMAT_VERSION` は 17 のまま)。
- タスク名は 50 文字以内で、制御文字・改行は不可(`MAX_TASK_NAME_LENGTH`・`has_control_char`)。
- 新規保存は同名のファイルを上書きしない(`save_project(..., overwrite=False)`)。
- 切り出しは元に戻す 1 ステップ(`after_edit` が積む)。子のファイルは元に戻さない。
- プレビュー(読み取り専用)では入口を出さない。Web モードでも使える。
- コミットメッセージの末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- 設計書からの修正(Task 1 で設計書にも反映する): ① 引き継ぐ稼働設定に`実績の記録方式`(`actual_mode`)を加える(2 区間のタスクを簡易方式の子に入れると読めなくなる)。② パラメータは、切り出すタスクに担当者がいて`parameters`が空のものが 1 つでもあれば全部、なければ付けたものだけを持ち越す(`parameters`が空のタスクの相対比率は全パラメータの合計なので、削ると換算率が変わる)。③ 純関数の名前は`selection_error`・`name_error`・`expand_ids`・`extract`・`check`。

## Review Focus

1. 同じまとめの子を全部切り出す → そのまとめは通常タスクに戻る(別のまとめに参照行が入るとき)。Task 1 の`test_summary_left_without_children_becomes_normal`。
2. 切り出すタスクに`parameters`が空で担当者のいるものがある → 全パラメータを持ち越し、換算率が変わらない。Task 1 の`test_all_parameters_are_carried_when_a_task_uses_them_all`。
3. 子の保存に失敗(同名のファイルが先にできた)→ 親は 1 文字も変わらず、ダイアログは開いたまま。Task 4 の`test_extract_leaves_the_parent_untouched_when_the_child_cannot_be_saved`。
4. 参照先が見つからない参照行を子に持つまとめ → 状態は未着手、進捗は None で、落ちない。Task 2 の`test_reference_child_without_a_value_counts_as_not_started`。
5. 切り出し内から外へ、外から切り出し内への先行 → 前者は外して件数を数え、後者は参照行へ付け替える。Task 1 の`test_predecessors_across_the_boundary`。

---

## File Structure

| 区分 | ファイル | 責任 |
|---|---|---|
| 新規 | `src/projectapp/extract.py` | 切り出しの純関数(選択の検証・名前の検証・子と親の組み立て・検証) |
| 新規 | `test/test_extract.py` | `extract.py`の単体テスト |
| 新規 | `test/test_extract_view.py` | 画面(確定の流れ・元に戻す・保存失敗) |
| 変更 | `src/projectapp/summary.py` | `summary_status`・`summary_progress`に参照値を渡す |
| 変更 | `src/projectapp/gantt.py` | まとめの状態・進捗に参照値を渡す。選択バーと右クリックメニューに入口 |
| 変更 | `src/projectapp/csv_export.py` | 参照行を書く |
| 変更 | `src/projectapp/forms.py` | `open_name_dialog`の確定ボタンの文言を指定できるようにする |
| 変更 | `src/projectapp/views.py` | 入口・確定の流れ・TSV の参照値の受け渡し |
| 変更 | `test/test_summary.py`・`test/test_csv_export.py` | 参照行の追加テスト |
| 変更 | `CLAUDE.md`・`docs/development.md`・`docs/requests.md`・`docs/work-log.md`・設計書 | 仕様と記録 |

---

### Task 1: `extract.py`(選択・名前の検証と、子と親の組み立て)

**Files:**
- Create: `src/projectapp/extract.py`
- Create: `test/test_extract.py`
- Modify: `docs/superpowers/specs/2026-10-31-extract-project-design.md`(設計からの修正の反映)

**Interfaces:**
- Consumes: `models.Project`・`Section`・`Task`・`TaskKind`・`Parameter`・`new_id`・`walk_sections`・`has_control_char`・`MAX_TASK_NAME_LENGTH`、`summary.parent_map`・`revert_empty`、`storage.dumps_project`・`parse_project`
- Produces:
  - `expand_ids(project: Project, ids: Collection[str]) -> list[str]`: 選んだ id に、まとめの子を足し、表示順(`Project.all_tasks` の順)に並べたもの
  - `selection_error(project: Project, ids: Collection[str]) -> str | None`
  - `name_error(project: Project, name: str, existing: Collection[str]) -> str | None`
  - `Extraction`(frozen dataclass): `child: Project`・`parent: Project`・`reference_id: str`・`moved: int`・`dropped: int`
  - `extract(project: Project, ids: Collection[str], name: str) -> Extraction`(`selection_error` があれば`ValueError`。`project`は変えない)
  - `check(extraction: Extraction) -> None`(保存・読込の検証を通らなければ`ValueError`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_extract.py` を新規作成する。

```python
from datetime import date

import pytest

from projectapp.extract import check, expand_ids, extract, name_error, selection_error
from projectapp.models import (
    Assignee,
    Category,
    Event,
    Level,
    Member,
    Membership,
    Parameter,
    Project,
    Section,
    Task,
    TaskKind,
    TaskUrl,
    UrlTemplate,
    ActualMode,
)


def make() -> Project:
    return Project(
        "親",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        members=[Member("田中", id="m1"), Member("鈴木", id="m2"), Member("佐藤", id="m3")],
        tasks=[Task("root", id="r")],
        sections=[
            Section(
                "開発",
                [
                    Task("a", id="a", effort_hours=8, assignees=[Assignee("田中", 1.0)]),
                    Task("b", id="b", effort_hours=4, predecessors=["a"], assignees=[Assignee("鈴木", 1.0)]),
                    Task("c", id="c", predecessors=["b"]),
                ],
                id="s1",
            )
        ],
    )


def summary_project() -> Project:
    """まとめ S1(子 k1・k2)と、まとめ S2(子 k3)。"""
    return Project(
        "親",
        sections=[
            Section(
                "開発",
                [
                    Task("S1", id="S1", kind=TaskKind.SUMMARY, children=["k1", "k2"]),
                    Task("k1", id="k1"),
                    Task("k2", id="k2"),
                    Task("S2", id="S2", kind=TaskKind.SUMMARY, children=["k3"]),
                    Task("k3", id="k3"),
                ],
                id="s1",
            )
        ],
    )


def ids_of(tasks: list[Task]) -> list[str]:
    return [t.id for t in tasks]


def test_selected_tasks_move_with_ids_and_sections_and_leave_a_reference() -> None:
    project = make()
    result = extract(project, ["a", "b"], "子")
    child, parent = result.child, result.parent
    assert child.name == "子" and child.tasks == []
    assert [s.name for s in child.sections] == ["開発"] and child.sections[0].id == "s1"
    assert ids_of(child.sections[0].tasks) == ["a", "b"]
    kept = parent.sections[0].tasks
    assert [t.kind for t in kept] == [TaskKind.REFERENCE, TaskKind.NORMAL]
    assert kept[0].id == result.reference_id and kept[0].name == "子" and kept[0].ref_project == "子"
    assert kept[0].ref_snapshot is None
    assert result.moved == 2
    assert ids_of(parent.tasks) == ["r"]
    assert ids_of(project.sections[0].tasks) == ["a", "b", "c"]  # 元の project は変えない


def test_root_tasks_stay_at_the_root_of_the_child() -> None:
    result = extract(make(), ["r"], "子")
    assert ids_of(result.child.tasks) == ["r"] and result.child.sections == []
    assert result.parent.tasks[0].kind is TaskKind.REFERENCE


def test_predecessors_across_the_boundary() -> None:
    result = extract(make(), ["b"], "子")
    assert result.child.sections[0].tasks[0].predecessors == []  # b は外の a を先行にしていた
    assert result.dropped == 1
    c = result.parent.sections[0].tasks[-1]
    assert c.id == "c" and c.predecessors == [result.reference_id]  # c は b を先行にしていた
    assert "a" in ids_of(result.parent.sections[0].tasks)


def test_predecessors_inside_the_selection_are_kept() -> None:
    result = extract(make(), ["a", "b"], "子")
    assert result.child.sections[0].tasks[1].predecessors == ["a"] and result.dropped == 0


def test_the_reference_goes_where_the_first_selected_task_was() -> None:
    result = extract(make(), ["b", "c"], "子")
    assert [t.kind for t in result.parent.sections[0].tasks] == [TaskKind.NORMAL, TaskKind.REFERENCE]


def test_only_the_members_in_the_selected_tasks_are_carried() -> None:
    project = make()
    project.members[0].teams = [Membership("t1", 100)]
    result = extract(project, ["a", "b"], "子")
    assert [m.name for m in result.child.members] == ["田中", "鈴木"]
    assert all(m.teams == [] for m in result.child.members)
    assert result.child.teams == []
    assert [m.name for m in result.parent.members] == ["田中", "鈴木", "佐藤"]  # 親の名簿は変えない


def test_members_in_weekly_crew_are_carried() -> None:
    project = make()
    task = project.sections[0].tasks[0]
    task.weekly_crew = [[Assignee("田中", 1.0)], [Assignee("佐藤", 0.5)]]
    task.assignees = [Assignee("田中", 1.0), Assignee("佐藤", 0.5)]
    result = extract(project, ["a"], "子")
    assert [m.name for m in result.child.members] == ["田中", "佐藤"]


def test_only_used_parameters_are_carried_when_every_task_picks_its_own() -> None:
    project = make()
    project.parameters = [Parameter("経験", [Level("高", 0.2)]), Parameter("慣れ", [Level("低", -0.1)])]
    project.members[0].levels = {"経験": "高", "慣れ": "低"}
    for task in project.sections[0].tasks[:2]:
        task.parameters = ["経験"]
    result = extract(project, ["a", "b"], "子")
    assert [p.name for p in result.child.parameters] == ["経験"]
    assert result.child.members[0].levels == {"経験": "高"}


def test_all_parameters_are_carried_when_a_task_uses_them_all() -> None:
    project = make()
    project.parameters = [Parameter("経験", [Level("高", 0.2)]), Parameter("慣れ", [Level("低", -0.1)])]
    project.sections[0].tasks[0].parameters = ["経験"]  # b は parameters が空 = 全パラメータの合計
    result = extract(project, ["a", "b"], "子")
    assert [p.name for p in result.child.parameters] == ["経験", "慣れ"]


def test_only_used_categories_and_url_templates_are_carried() -> None:
    project = make()
    project.categories = [Category("開発", id="c1"), Category("運用", id="c2")]
    project.url_templates = [UrlTemplate("チケット", "https://e/{ID}"), UrlTemplate("文書", "https://d/{ID}")]
    task = project.sections[0].tasks[0]
    task.category_id = "c1"
    task.urls = [TaskUrl(template="チケット", values={"ID": "1"})]
    result = extract(project, ["a"], "子")
    assert [c.id for c in result.child.categories] == ["c1"]
    assert [u.name for u in result.child.url_templates] == ["チケット"]


def test_settings_and_events_are_carried_but_not_teams() -> None:
    project = make()
    project.actual_mode = ActualMode.INTERVALS
    project.ratio_limit_upper = 1.2
    project.events = [Event(date(2026, 10, 7), date(2026, 10, 8), "休み", id="e1")]
    child = extract(project, ["a"], "子").child
    assert (child.base_date, child.daily_hours, child.work_start) == (project.base_date, 7.0, project.work_start)
    assert child.actual_mode is ActualMode.INTERVALS and child.ratio_limit_upper == 1.2
    assert [e.id for e in child.events] == ["e1"]


def test_selecting_a_summary_moves_its_children_too() -> None:
    result = extract(summary_project(), ["S1"], "子")
    assert ids_of(result.child.sections[0].tasks) == ["S1", "k1", "k2"]
    assert result.child.sections[0].tasks[0].kind is TaskKind.SUMMARY
    assert ids_of(result.parent.sections[0].tasks) == [result.reference_id, "S2", "k3"]
    assert result.moved == 3


def test_a_child_alone_becomes_a_reference_inside_its_summary() -> None:
    result = extract(summary_project(), ["k1"], "子")
    tasks = result.parent.sections[0].tasks
    assert ids_of(tasks) == ["S1", result.reference_id, "k2", "S2", "k3"]
    assert tasks[0].children == [result.reference_id, "k2"]
    assert tasks[1].kind is TaskKind.REFERENCE
    assert ids_of(result.child.sections[0].tasks) == ["k1"]
    assert result.child.sections[0].tasks[0].kind is TaskKind.NORMAL  # まとめは持ち越さない


def test_summary_left_without_children_becomes_normal() -> None:
    result = extract(summary_project(), ["k1", "k3"], "子")  # 参照行は S1 の中。S2 は子を全部失う
    by_id = {t.id: t for t in result.parent.all_tasks()}
    assert by_id["S2"].kind is TaskKind.NORMAL and by_id["S2"].children == []
    assert by_id["S1"].kind is TaskKind.SUMMARY and by_id["S1"].children == [result.reference_id, "k2"]


def test_expand_ids_adds_summary_children_in_display_order() -> None:
    assert expand_ids(summary_project(), ["S2", "k1"]) == ["k1", "S2", "k3"]
    assert expand_ids(summary_project(), ["missing"]) == []


def test_selection_errors() -> None:
    assert selection_error(make(), []) == "切り出すタスクがありません"
    project = make()
    project.tasks.append(Task("参照", id="ref", kind=TaskKind.REFERENCE, ref_project="x"))
    assert selection_error(project, ["a", "ref"]) == "プロジェクト参照の行は切り出せません"
    assert selection_error(project, ["a"]) is None
    with pytest.raises(ValueError):
        extract(project, ["ref"], "子")


def test_name_errors() -> None:
    project = make()
    assert name_error(project, "  ", []) == "名前を入力してください"
    assert "50文字以内" in (name_error(project, "あ" * 51, []) or "")
    assert name_error(project, "あ" * 50, []) is None
    assert name_error(project, "a\nb", []) == "名前に改行・制御文字は使えません"
    assert name_error(project, "親", []) == "今のプロジェクトと同じ名前にはできません"
    assert name_error(project, "子", ["子"]) == "同じ名前のプロジェクトがすでにあります"
    assert name_error(project, "子", ["孫"]) is None


def test_both_results_pass_the_load_validation() -> None:
    for ids in (["a", "b"], ["r"], ["b"]):
        check(extract(make(), ids, "子"))
    check(extract(summary_project(), ["k1"], "子"))
    check(extract(summary_project(), ["S1"], "子"))
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_extract.py -q 2>&1 | tail -5`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.extract'`)

- [ ] **Step 3: 実装する**

`src/projectapp/extract.py` を新規作成する。

```python
"""タスクの子プロジェクトへの切り出し(要望 89)。NiceGUI には依存しない純粋関数。"""

from collections.abc import Collection, Iterator
from copy import deepcopy
from dataclasses import dataclass

from projectapp.models import (
    MAX_TASK_NAME_LENGTH,
    Project,
    Section,
    Task,
    TaskKind,
    has_control_char,
    new_id,
    walk_sections,
)
from projectapp.storage import dumps_project, parse_project
from projectapp.summary import parent_map, revert_empty

CHECK_NAME = "_check"  # 検証で読み直すときの名前(参照先が自分自身かの判定に、実際の名前を使わないため)


@dataclass(frozen=True)
class Extraction:
    child: Project  # 子のプロジェクト(まだ保存していない)
    parent: Project  # 参照行に置き換えた親の複製
    reference_id: str  # 親に置いた参照行のタスクの id
    moved: int  # 子へ移したタスクの件数(まとめの子を含む)
    dropped: int  # 外のタスクを先行にしていたため、外した先行の数


def expand_ids(project: Project, ids: Collection[str]) -> list[str]:
    """選んだ id に、まとめの子を足し、表示順(`Project.all_tasks` の順)に並べる。プロジェクトにない id は捨てる。"""
    by_id = project.task_map()
    chosen = {i for i in ids if i in by_id}
    for task_id in list(chosen):
        if by_id[task_id].kind is TaskKind.SUMMARY:
            chosen.update(c for c in by_id[task_id].children if c in by_id)
    return [t.id for t in project.all_tasks() if t.id in chosen]


def selection_error(project: Project, ids: Collection[str]) -> str | None:
    """選択が切り出せない理由。切り出せるなら None。"""
    moved = expand_ids(project, ids)
    if not moved:
        return "切り出すタスクがありません"
    by_id = project.task_map()
    if any(by_id[i].kind is TaskKind.REFERENCE for i in moved):
        return "プロジェクト参照の行は切り出せません"
    return None


def name_error(project: Project, name: str, existing: Collection[str]) -> str | None:
    """子のプロジェクト名(参照行の名前にもなる)の不正な理由。existing は格納先にあるプロジェクト名。"""
    clean = name.strip()
    if not clean:
        return "名前を入力してください"
    if len(clean) > MAX_TASK_NAME_LENGTH:
        return f"名前は{MAX_TASK_NAME_LENGTH}文字以内で入力してください"
    if has_control_char(clean):
        return "名前に改行・制御文字は使えません"
    if clean == project.name:
        return "今のプロジェクトと同じ名前にはできません"
    if clean in existing:
        return "同じ名前のプロジェクトがすでにあります"
    return None


def _crew_names(task: Task) -> Iterator[str]:
    yield from task.assignee_names
    for week in task.weekly_crew:
        yield from (a.name for a in week)


def _task_lists(project: Project) -> list[list[Task]]:
    return [project.tasks, *(section.tasks for _, section in walk_sections(project.sections))]


def extract(project: Project, ids: Collection[str], name: str) -> Extraction:
    """選んだタスクを子のプロジェクトに移し、親は参照行に置き換えた複製にする。project は変えない。"""
    if (reason := selection_error(project, ids)) is not None:
        raise ValueError(reason)
    name = name.strip()
    moved_ids = expand_ids(project, ids)
    moved = set(moved_ids)
    used = [t for t in project.all_tasks() if t.id in moved]
    dropped = 0

    def moved_copy(task: Task) -> Task:
        nonlocal dropped
        copy = deepcopy(task)
        kept = [p for p in copy.predecessors if p in moved]
        dropped += len(copy.predecessors) - len(kept)
        copy.predecessors = kept  # 外のタスクを先行にしていたものは外す
        return copy

    def pick(section: Section) -> Section | None:
        tasks = [moved_copy(t) for t in section.tasks if t.id in moved]
        children = [s for s in map(pick, section.sections) if s is not None]
        return Section(section.name, tasks, children, id=section.id) if tasks or children else None

    child_tasks = [moved_copy(t) for t in project.tasks if t.id in moved]
    child_sections = [s for s in map(pick, project.sections) if s is not None]

    crew = {n for t in used for n in _crew_names(t)}
    # 付けたパラメータがなく担当のいるタスクの相対比率は全パラメータの合計なので、1 つでもあれば全パラメータを持ち越す
    needs_all = any(t.kind is TaskKind.NORMAL and t.assignees and not t.parameters for t in used)
    picked = {p for t in used for p in t.parameters}
    parameters = [deepcopy(p) for p in project.parameters if needs_all or p.name in picked]
    kept_levels = {p.name for p in parameters}
    members = []
    for member in project.members:
        if member.name in crew:
            copy = deepcopy(member)
            copy.teams = []
            copy.levels = {k: v for k, v in member.levels.items() if k in kept_levels}
            members.append(copy)
    category_ids = {t.category_id for t in used if t.category_id is not None}
    template_names = {u.template for t in used for u in t.urls if u.template is not None}
    child = Project(
        name,
        base_date=project.base_date,
        daily_hours=project.daily_hours,
        work_start=project.work_start,
        members=members,
        sections=child_sections,
        tasks=child_tasks,
        actual_mode=project.actual_mode,
        url_templates=[deepcopy(u) for u in project.url_templates if u.name in template_names],
        parameters=parameters,
        categories=[deepcopy(c) for c in project.categories if c.id in category_ids],
        events=deepcopy(project.events),
        reference_mode=project.reference_mode,
        plantuml_overload_notice=project.plantuml_overload_notice,
        ratio_limit_upper=project.ratio_limit_upper,
        ratio_limit_lower=project.ratio_limit_lower,
    )

    parent = deepcopy(project)
    owner = parent_map(project).get(moved_ids[0])  # 最初のタスクがまとめの子なら、参照行はそのまとめの子になる
    reference = Task(name, id=new_id(parent.used_ids()), kind=TaskKind.REFERENCE, ref_project=name)
    target: list[Task] = parent.tasks
    index = 0
    for tasks in _task_lists(parent):
        at = next((i for i, t in enumerate(tasks) if t.id == moved_ids[0]), None)
        if at is not None:
            target, index = tasks, at - sum(1 for t in tasks[:at] if t.id in moved)
            break
    for task in parent.all_tasks():
        if task.kind is not TaskKind.SUMMARY or task.id in moved:
            continue
        kids = [c for c in task.children if c not in moved]
        if task.id == owner:
            before = task.children[: task.children.index(moved_ids[0])]
            kids.insert(len([c for c in before if c not in moved]), reference.id)
        task.children = kids
    for tasks in _task_lists(parent):
        tasks[:] = [t for t in tasks if t.id not in moved]
    target.insert(index, reference)
    for task in parent.all_tasks():
        if any(p in moved for p in task.predecessors):
            ordered = [reference.id if p in moved else p for p in task.predecessors]
            task.predecessors = list(dict.fromkeys(ordered))
    revert_empty(parent)
    return Extraction(child, parent, reference.id, len(moved_ids), dropped)


def check(extraction: Extraction) -> None:
    """子と親を、保存・読込と同じ検証に通す。通らなければ ValueError。"""
    for project in (extraction.child, extraction.parent):
        parse_project(dumps_project(project), CHECK_NAME)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_extract.py -q 2>&1 | tail -8`
Expected: 全件 PASS

失敗したときは、期待値ではなく実装を直す。`test_a_child_alone_becomes_a_reference_inside_its_summary` が落ちるときは、`owner` の判定(最初のタスクの親のまとめが、移さない側か)と、`target.insert` の位置を見る。

- [ ] **Step 5: 設計書に設計からの修正を反映する**

`docs/superpowers/specs/2026-10-31-extract-project-design.md` を編集する。

「子プロジェクトの中身」の`稼働設定`の行を、次に置き換える。

```
  - 稼働設定: 稼働可能時間・始業時刻・基準日・実績の記録方式・参照の方式・相対比率の上限と下限・PlantUML の通知。
```

同じ節の`パラメータ`の行を、次に置き換える。

```
  - パラメータ: 切り出すタスクに、担当者がいて`parameters`が空のもの(相対比率が全パラメータの合計になる)が 1 つでもあれば、全パラメータ。なければ、タスクに付けたものだけ。メンバーの段階の選択も、持ち越したパラメータ分だけ残す。
```

「`extract_block_reason(project, ids, name)`」の箇条書き全体(`### extract.py`の最初の項目と、その下の理由の一覧)を、次に置き換える。

```
- `selection_error(project, ids)`: 選択が切り出せない理由を返す(なければ`None`)。プロジェクト参照行を含む、タスクが 0 件。
- `name_error(project, name, existing)`: 子のプロジェクト名の不正な理由。空、50 文字超、制御文字、親と同じ名前(自己参照になる)、格納先に同名のファイルがある(`existing`に格納先のプロジェクト名を渡す)。
- `expand_ids(project, ids)`: まとめの子を足して表示順に並べる。
- `check(extraction)`: 子と親を保存・読込と同じ検証に通す。
```

- [ ] **Step 6: 型を確認してコミットする**

```bash
uv run ty check src 2>&1 | tail -3
git add src/projectapp/extract.py test/test_extract.py docs/superpowers/specs/2026-10-31-extract-project-design.md docs/superpowers/plans/2026-10-31-extract-project.md
git commit -m "feat: タスクを子プロジェクトに切り出す純関数を足す(要望 89)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 参照行を子に持つまとめの状態・進捗

**Files:**
- Modify: `src/projectapp/summary.py:22-47`(`summary_status`・`summary_progress`)
- Modify: `src/projectapp/gantt.py`(`summary_status`・`summary_progress`を呼ぶ 4 か所)
- Test: `test/test_summary.py`

**Interfaces:**
- Consumes: `models.ReferenceValue`(`finished`・`actual_start`・`progress`)、`gantt.GanttChart.reference_values() -> dict[str, ReferenceValue]`
- Produces: `summary_status(children: Sequence[Task], references: Mapping[str, ReferenceValue] | None = None) -> Status`、`summary_progress(children: Sequence[Task], references: Mapping[str, ReferenceValue] | None = None) -> int | None`。参照行は`references[task.id]`の値で数える。`references`を渡さない従来の呼び出しは、結果が変わらない。

日程(開始・完了)は、`timeline.Schedule._resolve`が子を再帰的に解決し、参照行は`references`を見るので、変更は要らない(Step 1 のテストで確かめる)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_summary.py` の末尾に追加する(import に`Mapping`は要らない。`ReferenceValue`・`Schedule`は既存の import になければ足す)。

```python
from projectapp.models import ReferenceValue
from projectapp.summary import summary_progress, summary_status
from projectapp.timeline import Schedule


def reference_task() -> Task:
    return Task("参照", id="ref", kind=TaskKind.REFERENCE, ref_project="x")


def test_reference_child_finished_counts_as_done() -> None:
    refs = {"ref": ReferenceValue(finished=True, progress=100)}
    assert summary_status([reference_task()], refs) is Status.DONE


def test_reference_child_with_actuals_counts_as_running() -> None:
    refs = {"ref": ReferenceValue(actual_start=datetime(2026, 10, 5, 9), progress=30)}
    assert summary_status([reference_task()], refs) is Status.RUNNING


def test_reference_child_without_actuals_counts_as_not_started() -> None:
    refs = {"ref": ReferenceValue(planned_start=datetime(2026, 10, 5, 9))}
    assert summary_status([reference_task()], refs) is Status.NOT_STARTED


def test_reference_child_without_a_value_counts_as_not_started() -> None:
    assert summary_status([reference_task()], {}) is Status.NOT_STARTED
    assert summary_status([reference_task()]) is Status.NOT_STARTED
    assert summary_progress([reference_task()], {}) is None  # 参照先が見つからなくても落ちない


def test_reference_progress_is_averaged_with_weight_one() -> None:
    refs = {"ref": ReferenceValue(progress=100)}
    assert summary_progress([Task("a", progress=50), reference_task()], refs) == 75


def test_finished_reference_counts_as_100_percent() -> None:
    refs = {"ref": ReferenceValue(finished=True)}
    assert summary_progress([Task("a", progress=50), reference_task()], refs) == 75


def test_reference_without_progress_does_not_make_a_progress() -> None:
    refs = {"ref": ReferenceValue()}
    assert summary_progress([reference_task()], refs) is None


def test_summary_span_covers_a_reference_child() -> None:
    value = ReferenceValue(planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 9, 18))
    project = Project(
        "p",
        tasks=[Task("まとめ", id="s", kind=TaskKind.SUMMARY, children=["ref"]), reference_task()],
    )
    schedule = Schedule(project, {}, {"ref": value})
    assert schedule.start(project.tasks[0]) == value.planned_start
    assert schedule.end(project.tasks[0]) == value.planned_end
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_summary.py -q -k "reference" 2>&1 | tail -8`
Expected: FAIL(`summary_status() takes 1 positional argument but 2 were given`)。`test_summary_span_covers_a_reference_child`は通ってよい(日程は既に対応している)。

- [ ] **Step 3: 実装する**

`src/projectapp/summary.py` の import を直す。

```python
from collections.abc import Mapping, Sequence
from math import isfinite

from projectapp.models import Project, ReferenceValue, Status, Task, TaskKind
```

`summary_status`・`summary_progress` を次に置き換える(`_weight` は残す)。

```python
def _status_of(child: Task, references: Mapping[str, ReferenceValue] | None) -> Status:
    """子の状態。参照行は、状態を持たないので、参照先の値から出す(値がなければ未着手)。"""
    if child.kind is not TaskKind.REFERENCE:
        return child.status
    value = (references or {}).get(child.id)
    if value is None:
        return Status.NOT_STARTED
    if value.finished:
        return Status.DONE
    return Status.RUNNING if value.actual_start is not None else Status.NOT_STARTED


def summary_status(children: Sequence[Task], references: Mapping[str, ReferenceValue] | None = None) -> Status:
    """全員が終了なら終了、1 つでも着手済み(実行中・一時停止・終了)なら実行中、それ以外は未着手。
    参照行は参照先の値(全部終了なら終了、実績があれば実行中)で数える。"""
    states = [_status_of(c, references) for c in children]
    if states and all(s is Status.DONE for s in states):
        return Status.DONE
    if any(s is not Status.NOT_STARTED for s in states):
        return Status.RUNNING
    return Status.NOT_STARTED


def _weight(effort_hours: float) -> float:
    return effort_hours if isfinite(effort_hours) and effort_hours > 0 else 1.0


def _percent_of(child: Task, references: Mapping[str, ReferenceValue] | None) -> tuple[int | None, float]:
    """(進捗度, 重み)。参照行は参照先の進捗(全部終了なら 100)で、重みは 1。進捗度がないものは None。"""
    if child.kind is TaskKind.REFERENCE:
        value = (references or {}).get(child.id)
        if value is None:
            return None, 1.0
        return (100 if value.finished else value.progress), 1.0
    return (100 if child.status is Status.DONE else child.progress), _weight(child.effort_hours)


def summary_progress(children: Sequence[Task], references: Mapping[str, ReferenceValue] | None = None) -> int | None:
    """子の進捗度を、工数(なければ 1)で重みづけした平均(四捨五入)。終了は 100、進捗度がないものは 0。
    どの子にも進捗度がなく、終了もないときは None。参照行は参照先の進捗で、重みは 1。"""
    parts = [_percent_of(c, references) for c in children]
    if all(percent is None for percent, _ in parts):
        return None
    weighted = sum(weight * (percent or 0) for percent, weight in parts)
    total = sum(weight for _, weight in parts)
    return int(weighted / total + 0.5)  # 四捨五入(round は銀行丸めで、62.5 が 62 になる)
```

`summary_progress` の従来の挙動(`status is DONE` か`progress is not None`のどれかがあれば算出)は、`_percent_of`が`DONE`なら 100 を返すので変わらない。

`src/projectapp/gantt.py` の 4 か所に、`self.reference_values()` を渡す。

- `finished = summary_status(children_of(task, self.tasks_by_id)) is Status.DONE` → `finished = summary_status(children_of(task, self.tasks_by_id), self.reference_values()) is Status.DONE`
- `percent = summary_progress(children_of(task, self.tasks_by_id))` → `percent = summary_progress(children_of(task, self.tasks_by_id), self.reference_values())`
- `percent = summary_progress(kids)` → `percent = summary_progress(kids, self.reference_values())`
- `band.classes(STATUS_CLASSES[summary_status(kids)])` → `band.classes(STATUS_CLASSES[summary_status(kids, self.reference_values())])`

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_summary.py test/test_gantt.py test/test_reference.py -q 2>&1 | tail -5`
Expected: 全件 PASS(既存のまとめのテストが変わらず通ること)

- [ ] **Step 5: コミット**

```bash
uv run ty check src 2>&1 | tail -3
git add src/projectapp/summary.py src/projectapp/gantt.py test/test_summary.py
git commit -m "feat: 参照行を子に持つまとめの状態と進捗を、参照先の値から出す(要望 89)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: TSV の書き出しに参照行を足す

**Files:**
- Modify: `src/projectapp/csv_export.py`(`TsvExport`・`build_tsv`)
- Modify: `src/projectapp/views.py:675-698`(`export_tsv`)
- Test: `test/test_csv_export.py`

**Interfaces:**
- Consumes: `models.ReferenceValue`(`planned_start`・`planned_end`・`progress`・`finished`)、`reference.build_references(project, resolver, now) -> dict[str, Reference]`
- Produces: `build_tsv(project, holidays, references: Mapping[str, ReferenceValue] | None = None) -> TsvExport`。`TsvExport`に`references: int`(書いた参照行の数)と`unresolved: int`(値がなく、日付と完了率を空にした参照行の数)を足す。`skipped`は、まとめとチェックポイントだけを数える。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_csv_export.py` の import に`ReferenceValue`を足し、末尾に追加する。

```python
from projectapp.models import ReferenceValue


def reference_project() -> Project:
    return Project("p", tasks=[Task("基盤", id="r", kind=TaskKind.REFERENCE, ref_project="基盤")])


def test_a_reference_row_is_written_with_the_dates_and_progress_of_its_target() -> None:
    value = ReferenceValue(planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 9, 18), progress=40)
    out = build_tsv(reference_project(), {}, {"r": value})
    assert rows(out.text)[3] == ["", "(参照) 基盤", "", "26年 10月 5日", "26年 10月 9日", "4", "40%"]
    assert (out.task_count, out.references, out.unresolved, out.skipped) == (0, 1, 0, 0)


def test_a_finished_reference_without_progress_is_written_as_100_percent() -> None:
    value = ReferenceValue(planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 5, 18), finished=True)
    assert rows(build_tsv(reference_project(), {}, {"r": value}).text)[3][-1] == "100%"


def test_a_reference_without_progress_is_written_as_0_percent() -> None:
    value = ReferenceValue(planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 5, 18))
    assert rows(build_tsv(reference_project(), {}, {"r": value}).text)[3][-1] == "0%"


def test_a_reference_that_cannot_be_read_is_written_with_blank_dates_and_progress() -> None:
    out = build_tsv(reference_project(), {}, {})
    assert rows(out.text)[3] == ["", "(参照) 基盤", "", "", "", "0", ""]
    assert (out.references, out.unresolved) == (1, 1)


def test_references_default_to_unresolved_when_no_values_are_given() -> None:
    assert build_tsv(reference_project(), {}).unresolved == 1
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_csv_export.py -q -k "reference" 2>&1 | tail -8`
Expected: FAIL(`build_tsv() takes 2 positional arguments but 3 were given`)

- [ ] **Step 3: 実装する**

`src/projectapp/csv_export.py` を編集する。

import に`Mapping`と`ReferenceValue`を足す。

```python
from collections.abc import Mapping
...
from projectapp.models import Project, ReferenceValue, Section, Status, Task, TaskKind
```

定数と`TsvExport`を直す。

```python
REFERENCE_PREFIX = "(参照) "  # 参照行のタイトルの頭。取り込みは通常タスクとして読む(往復で参照行には戻らない)
```

```python
@dataclass(frozen=True)
class TsvExport:
    text: str
    task_count: int
    section_count: int
    skipped: int  # 書き出さなかったタスク(まとめ・チェックポイント)の数
    multiple_owners: int  # 担当者が複数で、筆頭だけを書いたタスクの数
    references: int = 0  # 書いたプロジェクト参照の行の数
    unresolved: int = 0  # うち、参照先の値がなく、日付と完了率を空にした行の数
```

`build_tsv` の署名と、`counts`・`task_row` を直す。

```python
def build_tsv(
    project: Project, holidays: dict[date, str], references: Mapping[str, ReferenceValue] | None = None
) -> TsvExport:
    """通常タスクとプロジェクト参照とセクションを、`Project.all_tasks` と同じ順(セクションなしが先、続いてセクションを深さ優先)で書く。
    references は参照行(タスクの id)ごとの参照先の値。なければ日付と完了率を空にする。"""
    schedule = Schedule(project, holidays)
    out = io.StringIO()
    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
    writer.writerow(HEADER)
    for _ in range(BLANK_ROWS):
        writer.writerow([""] * len(HEADER))
    counts = {"tasks": 0, "sections": 0, "skipped": 0, "multiple": 0, "references": 0, "unresolved": 0}

    def reference_row(task: Task) -> None:
        value = (references or {}).get(task.id)
        counts["references"] += 1
        start = value.planned_start if value is not None else None
        end = value.planned_end if value is not None else None
        first, last = (start.date() if start else None), (_last_day(end) if end else None)
        if value is None:
            counts["unresolved"] += 1
            percent = ""
        else:
            percent = f"{value.progress if value.progress is not None else (100 if value.finished else 0)}%"
        writer.writerow(
            (
                "",
                REFERENCE_PREFIX + task.name,
                "",
                format_date(first) if first else "",
                format_date(last) if last else "",
                (last - first).days if first and last else 0,
                percent,
            )
        )

    def task_row(task: Task) -> None:
        if task.kind is TaskKind.REFERENCE:
            reference_row(task)
            return
        if task.kind is not TaskKind.NORMAL:
            counts["skipped"] += 1
            return
```

(`task_row` の残り — `wbs, title = split_name(task.name)` 以降 — は変えない。)

末尾の`return TsvExport(...)`を直す。

```python
    return TsvExport(
        out.getvalue(),
        counts["tasks"],
        counts["sections"],
        counts["skipped"],
        counts["multiple"],
        counts["references"],
        counts["unresolved"],
    )
```

`src/projectapp/views.py` の`export_tsv`を直す(import に`build_references`は既にある)。

```python
        now = datetime.now()
        values = {tid: ref.value for tid, ref in build_references(self.project, self.reference_resolver, now).items() if ref.value is not None}
        result = build_tsv(self.project, self.holidays, values)
        if result.task_count == 0 and result.section_count == 0 and result.references == 0:
            ui.notify("書き出せるタスクがありません", type="warning")
            return
```

通知の`notes`を直す。

```python
        notes = [
            f"{result.skipped} 件(まとめ・節目)は書き出していません" if result.skipped else "",
            f"担当者が複数の {result.multiple_owners} 件は筆頭だけを書きました" if result.multiple_owners else "",
            f"参照先が読めない {result.unresolved} 件は、日付と完了率を空にしました" if result.unresolved else "",
        ]
        detail = "、".join(note for note in notes if note)
        head = f"書き出しました(タスク {result.task_count} 件、参照 {result.references} 件、セクション {result.section_count} 件)"
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_csv_export.py test/test_csv_import.py -q 2>&1 | tail -5`
Expected: 全件 PASS。既存の`test_only_normal_tasks_are_written`(まとめと節目で`skipped == 2`)は変わらず通る。

`views.py` の通知の文言を直したので、`grep -rn "まとめ・節目・参照" test src` で古い文言を参照するテストがないか確かめ、あれば新しい文言に合わせる。

- [ ] **Step 5: コミット**

```bash
uv run ty check src 2>&1 | tail -3
git add src/projectapp/csv_export.py src/projectapp/views.py test/test_csv_export.py
git commit -m "feat: TSV の書き出しに、プロジェクト参照の行を足す(要望 89)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 画面の入口と確定の流れ

**Files:**
- Modify: `src/projectapp/forms.py:1055-1081`(`open_name_dialog`)
- Modify: `src/projectapp/gantt.py`(`GanttActions`・選択バー・右クリックメニュー)
- Modify: `src/projectapp/views.py`(`GanttActions` の組み立て・`extract_tasks`・`apply_extract`)
- Create: `test/test_extract_view.py`

**Interfaces:**
- Consumes: Task 1 の`selection_error`・`name_error`・`extract`・`check`・`Extraction`、`storage.save_project(project, base_dir, overwrite=False)`・`validate_name`、`reference.compute_reference`、`events.effective_holidays`、`views.MainView.after_edit`・`gantt.clear_selection`
- Produces: `GanttActions.extract_tasks: Callable[[list[str]], object]`、`MainView.extract_tasks(ids: list[str]) -> None`(名前の入力ダイアログを開く)、`MainView.apply_extract(ids: list[str], name: str) -> bool`(確定。失敗は`False`)、`open_name_dialog(..., submit: str = "保存")`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_extract_view.py` を新規作成する(`test/test_bulk_view.py` の`mount`・`open_view`と同じ作り)。

```python
from datetime import date
from pathlib import Path

import httpx
from nicegui import ui
from nicegui.testing import User

from projectapp.models import Assignee, Member, Project, Section, Task, TaskKind
from projectapp.storage import load_project
from projectapp.views import MainView


def make_project() -> Project:
    return Project(
        "親",
        base_date=date(2026, 10, 5),
        members=[Member("田中", id="m1")],
        tasks=[Task("a", id="a", effort_hours=8), Task("b", id="b", effort_hours=4)],
        sections=[Section("開発", [Task("c", id="c", effort_hours=2, assignees=[Assignee("田中", 1.0)])], id="s1")],
    )


def mount(tmp_path: Path, views: list[MainView]) -> None:
    @ui.page("/")
    def index() -> None:
        view = MainView(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200)))
        views.append(view)
        view.build()
        view.project = make_project()
        view.mark_clean()
        view.reset_history()
        view.gantt.set_project(view.project)


async def open_view(user: User, tmp_path: Path) -> MainView:
    views: list[MainView] = []
    mount(tmp_path, views)
    await user.open("/")
    return views[0]


async def test_extract_saves_the_child_and_replaces_the_tasks_with_a_reference(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    assert view.apply_extract(["a", "c"], "子") is not False
    child = load_project(view.project_dir / "子.json")
    assert {t.id for t in child.all_tasks()} == {"a", "c"}
    kinds = [t.kind for t in view.project.all_tasks()]
    assert kinds.count(TaskKind.REFERENCE) == 1 and "a" not in view.project.task_map()
    assert view.is_dirty()


async def test_extract_is_one_undo_step_and_keeps_the_child_file(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.apply_extract(["a", "c"], "子")
    view.undo()
    assert set(view.project.task_map()) == {"a", "b", "c"}
    assert (view.project_dir / "子.json").exists()  # 元に戻しても、保存した子のファイルは残る


async def test_extract_leaves_the_parent_untouched_when_the_child_cannot_be_saved(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    (view.project_dir / "子.json").write_text("{}", encoding="utf-8")  # ダイアログの検証のあとに、同名のファイルができた
    before = view.project.task_map().keys()
    assert view.apply_extract(["a"], "子") is False
    assert set(view.project.task_map()) == set(before) and not view.is_dirty()
    assert (view.project_dir / "子.json").read_text(encoding="utf-8") == "{}"  # 上書きしない


async def test_extract_clears_the_selection(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.bulk.ids.update({"a", "b"})
    view.apply_extract(["a", "b"], "子")
    assert not view.gantt.has_selection()


async def test_extract_takes_a_snapshot_when_the_reference_mode_is_snapshot(user: User, tmp_path: Path) -> None:
    from projectapp.models import ReferenceMode

    view = await open_view(user, tmp_path)
    view.project.reference_mode = ReferenceMode.SNAPSHOT
    view.apply_extract(["a"], "子")
    reference = next(t for t in view.project.all_tasks() if t.kind is TaskKind.REFERENCE)
    assert reference.ref_snapshot is not None and reference.ref_snapshot.taken_at is not None


async def test_extract_notifies_the_count_and_dropped_predecessors(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.project.tasks[1].predecessors = ["a"]  # b は外の a を先行にしている
    view.apply_extract(["b"], "子")
    await user.should_see("「子」に 1 件を切り出しました")
    await user.should_see("先行 1 件を外しました")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_extract_view.py -q 2>&1 | tail -8`
Expected: FAIL(`AttributeError: 'MainView' object has no attribute 'apply_extract'`)

- [ ] **Step 3: 実装する(forms・gantt)**

`src/projectapp/forms.py` の`open_name_dialog`に`submit`を足す。

```python
def open_name_dialog(
    on_submit: Callable[[str], object],
    validate: Callable[[str], str | None],
    *,
    title: str = "プロジェクトの保存",
    initial: str = "",
    label: str = "プロジェクト名",
    submit: str = "保存",
) -> None:
```
```python
            ui.button(submit, on_click=save).mark("name-save")
```

`src/projectapp/gantt.py` を編集する。

1. `GanttActions`(`bulk_delete` の次の行)に追加する。

```python
    extract_tasks: Callable[[list[str]], object] = lambda ids: None
```

2. 選択バー(`bulk-delete` のボタンの次、`bulk-clear` の前)にボタンを足す。

```python
                ui.button(
                    "子プロジェクトに切り出し…", icon="call_split", on_click=lambda: self.actions.extract_tasks(self.selected_ids())
                ).props("flat dense size=sm").mark("bulk-extract")
```

3. `build_menu` の、`bulk_delete_item` を作った直後(`self.bulk_delete_item = item` の次)に追加する。

```python
            with ui.menu_item(on_click=lambda: self.actions.extract_tasks(self.selected_ids())).mark("context-extract") as item:
                with ui.item_section():
                    self.extract_label = ui.label("選択中を子プロジェクトに切り出し…")
            self.extract_item = item
```
そして、直後の`for part in (self.bulk_edit_item, self.bulk_delete_item, self.bulk_separator):`を`for part in (self.bulk_edit_item, self.bulk_delete_item, self.extract_item, self.bulk_separator):`に直す。

4. `GanttChart.__init__` で、`bulk_delete_label` を初期化している箇所の近くに、`self.extract_item: ui.menu_item | None = None` と `self.extract_label: ui.label | None = None` を足す(`grep -n "bulk_delete_label" src/projectapp/gantt.py` で場所を見つけ、同じ書き方に合わせる)。

5. `open_menu` の`for item, label, text in (...)`のタプルに 1 行足す。

```python
            (self.extract_item, self.extract_label, "子プロジェクトに切り出し…"),
```
(`label.set_text(f"選択中 {len(chosen)} 件を{text}")` が、`選択中 3 件を子プロジェクトに切り出し…` になる。)

- [ ] **Step 4: 実装する(views)**

`src/projectapp/views.py` の import に追加する。

```python
from projectapp.extract import check as check_extraction, extract, name_error as extract_name_error, selection_error
from projectapp.reference import compute_reference
from projectapp.storage import save_project, validate_name
```
(`save_project`・`validate_name`・`compute_reference`・`replace` が既に import されていれば足さない。`grep -n "^from projectapp.storage\|^from projectapp.reference\|^from dataclasses" src/projectapp/views.py` で確かめる。)

`GanttActions(...)` の`bulk_delete=self.confirm_bulk_delete,` の次に、`extract_tasks=self.extract_tasks,` を足す。

`confirm_bulk_delete` の前に、次の 2 つのメソッドを足す。

```python
    def extract_tasks(self, ids: list[str]) -> None:
        """選択中のタスクを子プロジェクトに切り出す(名前の入力ダイアログを開く)。"""
        if self.preview is not None or not ids:
            return
        if (reason := selection_error(self.project, ids)) is not None:
            ui.notify(reason, type="warning")
            return

        def validate(name: str) -> str | None:
            existing = {p.stem for p in self.project_dir.glob("*.json")}
            return extract_name_error(self.project, name, existing) or validate_name(name, self.project_dir, new=True)

        open_name_dialog(
            lambda name: self.apply_extract(ids, name),
            validate,
            title="子プロジェクトに切り出し",
            label="子プロジェクト名",
            submit="切り出す",
        )

    def apply_extract(self, ids: list[str], name: str) -> bool:
        """子を新規保存し、親を参照行に置き換える(元に戻す 1 ステップ)。失敗は False(親は変えない)。"""
        try:
            result = extract(self.project, ids, name)
            now = self.now()
            if self.project.reference_mode is ReferenceMode.SNAPSHOT:
                value = compute_reference(result.child, effective_holidays(result.child, self.base_holidays), now)
                reference = next(t for t in result.parent.all_tasks() if t.id == result.reference_id)
                reference.ref_snapshot = replace(value, taken_at=now)
            check_extraction(result)
            save_project(result.child, self.project_dir, overwrite=False)  # 子を先に保存する。失敗したら親は変えない
        except (OSError, ValueError) as exc:
            ui.notify(f"切り出せませんでした: {exc}", type="negative")
            return False
        self.project = result.parent
        self.gantt.clear_selection()
        self.after_edit()
        notes = [f"先行 {result.dropped} 件を外しました" if result.dropped else "", "親を保存してください"]
        ui.notify(f"「{name.strip()}」に {result.moved} 件を切り出しました。" + "。".join(n for n in notes if n))
        return True
```

(`ReferenceMode`・`effective_holidays`・`replace`・`open_name_dialog` が views.py で既に import されているか確かめ、なければ足す: `grep -n "ReferenceMode\|effective_holidays\|open_name_dialog" src/projectapp/views.py | head`。`effective_holidays` は`projectapp.events`にある。)

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest test/test_extract_view.py test/test_extract.py test/test_bulk_view.py test/test_context_menu.py -q 2>&1 | tail -8`
Expected: 全件 PASS

`test_extract_notifies_the_count_and_dropped_predecessors` は、通知文の一部を`user.should_see`で見る。通知が連結された 1 つの文のため、見つからないときは `should_see("先行 1 件を外しました")` を、実際の通知の全文の一部に合わせて直す(実装の文言は変えない)。

- [ ] **Step 6: 選択バーと右クリックメニューのテストを足す**

`test/test_extract_view.py` の末尾に追加する。

```python
async def test_the_selection_bar_and_the_context_menu_have_the_entry(user: User, tmp_path: Path) -> None:
    view = await open_view(user, tmp_path)
    view.gantt.bulk.ids.update({"a", "b"})
    view.gantt.sync_bulk()
    await user.should_see(marker="bulk-extract")
    view.gantt.open_menu((), 0)
    assert view.gantt.extract_label is not None
    assert view.gantt.extract_label.text == "選択中 2 件を子プロジェクトに切り出し…"
```

Run: `uv run pytest test/test_extract_view.py -q 2>&1 | tail -5`
Expected: 全件 PASS

- [ ] **Step 7: コミット**

```bash
uv run ty check src 2>&1 | tail -3
git add src/projectapp/forms.py src/projectapp/gantt.py src/projectapp/views.py test/test_extract_view.py
git commit -m "feat: 選択したタスクを子プロジェクトに切り出す入口と流れを足す(要望 89)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 仕様書・記録・全体の確認

**Files:**
- Modify: `CLAUDE.md`(projectapp/CLAUDE.md)、`docs/development.md`、`docs/requests.md`、`docs/work-log.md`、`docs/hidden-requests.md`(git 管理外)、設計書の状態

- [ ] **Step 1: 失敗するテストを書く(仕様の記述の確認はテストにならないので省く)**

このタスクにコードの変更はない。

- [ ] **Step 2: `CLAUDE.md`(projectapp 側)に仕様を足す**

`## ガントチャート`の、`種別`プロジェクト参照`の項目の次に、次の項目を足す。

```
- 選択したタスクを、新しい子プロジェクトに切り出せる(要望 89)。選択バーの`子プロジェクトに切り出し…`と、選択した行の右クリックメニューの`選択中 n 件を子プロジェクトに切り出し…`で、プロジェクト名(タスク名と同じ文字の制限。親と同じ名前・格納先の同名のファイルは不可)を入れる。まとめを選ぶと子も一緒に移し、まとめの子だけを選んでもよい(まとめは持ち越さない)。プロジェクト参照の行は切り出せない。確定すると、子のファイルを格納先にすぐ新規保存し(同名は上書きしない。失敗したら親は変えない)、親は、切り出したタスクを取り除いて、子を指す`プロジェクト参照`の行を 1 つ置いた未保存の編集になる(元に戻す 1 ステップ。保存済みの子のファイルは戻さない)。参照行の位置は、選択の中で表示順が最初のタスクの位置で、それがまとめの子ならそのまとめの子になる。
- 子には、タスクを`id`のまま移し(セクションは、選んだタスクを含むものを同じ階層・順で作る)、関わる分だけを引き継ぐ: 担当(週ごとの担当を含む)に入っているメンバー(所属は持ち越さない)、タスクに付けたパラメータ(担当がいて`parameters`が空のタスクがあれば全パラメータ)、使っているカテゴリ・URL テンプレート、稼働設定(稼働可能時間・始業時刻・基準日・実績の記録方式・参照の方式・相対比率の上限と下限・PlantUML の通知)、イベント。先行は、切り出し内どうしは維持し、外を先行にしていたものは外して件数を通知する。切り出したタスクを先行にしていた外のタスクは、参照行を先行にする。参照の方式がスナップショットなら、参照行のスナップショットをその場で取る。
- 参照行はまとめの子にできる。まとめの状態・進捗は、参照行を参照先の値で数える(状態: 全部終了なら終了、実績があれば実行中、なければ未着手。進捗: 参照先の進捗、重みは 1)。開始・完了は、これまでどおり子の最小と最大。
```

`## CSV の取り込みと TSV の書き出し`の、`書き出す行は…`の項目を、次に置き換える(`通常タスクとセクション`の後ろに`プロジェクト参照`を足し、`まとめ・チェックポイント・プロジェクト参照は書かず`を`まとめ・チェックポイントは書かず`にし、参照行の規則を足す)。

```
- 書き出す行は、通常タスクとプロジェクト参照とセクション(セクションなしのタスクが先、続いてセクションを深さ優先)。まとめ・チェックポイントは書かず、件数を通知する。プロジェクト参照は、`タスクのタイトル`を`(参照) 名前`とし、`開始日`・`期限`は参照先の予定の開始・完了(日付がなければ空。期限は完了予定の日。0 時ちょうどは前日)、`期間`は期限 − 開始日の暦日数、`タスク完了率`は参照先の進捗(なければ、全部終了なら 100、それ以外は 0)に`%`を付ける。参照先が見つからない・読めないときは、日付と完了率を空にして件数を通知する。取り込みは`(参照)`付きの行を通常タスクとして読む(往復で参照行には戻らない)。(以下、名前の分け方・セクション・`開始日`などの規則は、これまでどおり。)
```
※ 置き換えるときは、元の項目の後半(名前の最初の`#`で…から完了率まで)を削らずに残す。

- [ ] **Step 3: `docs/development.md` に追記する**

モジュール表(`teams.py` の行の近く)に追加する。

```
| `extract.py` | タスクの子プロジェクトへの切り出し(要望 89)。`expand_ids`・`selection_error`・`name_error`・`extract`(子の`Project`と、参照行に置き換えた親の複製を返す。元は変えない)・`check`(保存・読込の検証)。NiceGUI に依存しない。画面は`views.extract_tasks`(名前の入力)・`apply_extract`(子を先に新規保存し、親を置き換える) |
```

ファイル形式の注意の節に追記する。

```
- 参照行をまとめの子にできる(要望 89)。ファイル形式は変えない(`children`は id のリストで、種別は検証しない)。`summary.summary_status`・`summary_progress`は、参照行を`references`(参照行の id → `ReferenceValue`)から数える。日程は`timeline.Schedule`が子を再帰的に解決するので、`references`を渡すだけでよい。
```

- [ ] **Step 4: `docs/requests.md` と `docs/work-log.md` に記録する**

`docs/requests.md` の末尾に、要望 89 の節を足す(`## 要望 82` の書式に合わせる)。

```
## 要望 89: プロジェクトのタスクを起点に、子プロジェクトのファイルを作成する(2026-10-30 に受領)

> **状態**: 実装済み(PR 番号はマージ後に記入)。[設計書](superpowers/specs/2026-10-31-extract-project-design.md)・[計画](superpowers/plans/2026-10-31-extract-project.md)。

### 要望
大きなタスクを、独立したプロジェクトファイル(子プロジェクト)に切り出して管理したい。元のタスクは`プロジェクト参照`の行に置き換わり、親から子の進捗が見える。

### 決めた点
- 複数選択したタスク(まとめの子だけも可)を、まとめて 1 つの子にする。引き継ぎは、タスクに関わる分だけ。境界の先行は、参照行へ付け替え(外を先行にしていたものは外す)。子のファイルは確定時にすぐ新規保存し、親は未保存の編集のまま。
- 参照行をまとめの子にできるよう、まとめの状態・進捗を参照先の値から出す。TSV の書き出しは参照行を`(参照) 名前`の行として書く。
- ダッシュボードは変えない(参照行は数えない)。参照行の進捗・工数をダッシュボードに載せることは要望 90。

### 関連
- 要望 77(既存プロジェクトからの引き継ぎ)・要望 78・要望 35・要望 90。
```

`docs/work-log.md` の末尾に足す(`要望 85 チーム 段階 3` の項の書式に合わせる)。

```
- 要望 89 タスクの子プロジェクトへの切り出し(2026-10-31): brainstorming(architectural)で設計を確定(目的・複数選択・タスクに関わる分だけ引き継ぎ・境界の先行は参照行へ・子を即保存・TSV に参照行・ダッシュボードは変えない)。設計書 `2026-10-31-extract-project-design.md`、計画 `plans/2026-10-31-extract-project.md`。`extract.py`(純関数)、まとめの状態・進捗の参照行対応、TSV の参照行、選択バーと右クリックの入口を実装。設計からの修正: 引き継ぐ稼働設定に実績の記録方式を加え、パラメータは`parameters`が空で担当のいるタスクがあれば全部持ち越す。
```

`docs/hidden-requests.md`(git 管理外)の要望 89 の行の状態を`実装済み`にする。

- [ ] **Step 5: 設計書の状態を更新する**

`docs/superpowers/specs/2026-10-31-extract-project-design.md` の状態の行を、次に置き換える。

```
> **状態**: 設計(2026-10-31 に承認済み)。実装済み(計画 [`plans/2026-10-31-extract-project.md`](../plans/2026-10-31-extract-project.md))。要望 89。
```

- [ ] **Step 6: 全体を確認する**

Run: `uv run pytest -q 2>&1 | tail -5` と `uv run ty check src`
Expected: 全テスト PASS・`ty` 通過(約 4 分かかる。タイムアウトを長くするか、バックグラウンドで実行する)

- [ ] **Step 7: 実機で確認する**(`uv run projectapp`)

`~/.projectapp/チーム按分確認.json` を開き、①タスクを `Cmd/Ctrl+クリック` で 2〜3 件選び、選択バーの`子プロジェクトに切り出し…`で名前を入れて確定する → 親に参照行(📅)が出て、`未保存`になる ②`Cmd/Ctrl+Z`で元に戻る(子のファイルは残る) ③右クリックメニューでも同じ入口が出る ④まとめの子だけを選んで切り出すと、参照行がそのまとめの子になり、まとめの帯と進捗が参照先を含んで出る ⑤`エクスポート > TSV として書き出す`で`(参照) 名前`の行が出る ⑥親を保存して、参照行をクリックすると子が開く、を確かめる。確認用に作った子のファイルは、確認後に削除する。

- [ ] **Step 8: コミット**

```bash
git add CLAUDE.md docs/development.md docs/requests.md docs/work-log.md docs/superpowers/specs/2026-10-31-extract-project-design.md
git commit -m "docs: タスクの子プロジェクトへの切り出し(要望 89)の仕様と記録を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**1. 設計書との対応**
- 子の中身(タスク・`id`・セクション・名簿と設定・先行): Task 1。
- 親の置き換え(位置・まとめの子・先行の付け替え・`revert_empty`・スナップショット): Task 1(純関数)と Task 4(スナップショット)。
- 参照行をまとめの子にする: Task 2。
- TSV の書き出し: Task 3。
- 入口・名前の検証・保存の順序・通知・元に戻す: Task 4。
- 断る条件(参照行・0 件・名前・自己参照・同名ファイル): Task 1 の`selection_error`・`name_error`と、Task 4 の`validate`。
- ダッシュボードは変えない・要望 90 は別: 実装なし(設計書と記録だけ。Task 5)。
- 仕様書・記録: Task 5。

**2. プレースホルダ**: なし。`views.py`・`gantt.py` の編集箇所は、既存コードの引用で位置を示した。

**3. 型の整合**: `Extraction(child, parent, reference_id, moved, dropped)`(Task 1)を Task 4 の`apply_extract`が同じ名前で使う。`summary_status`・`summary_progress`の`references`引数(Task 2)を、`gantt.py`が`self.reference_values()`で渡す。`build_tsv`の`references`・`TsvExport.references`・`unresolved`(Task 3)を`views.export_tsv`が使う。`open_name_dialog`の`submit`(Task 4)。

**4. Review Focus**: 5 項目すべてに、所有するタスクのテストがある(冒頭の対応表)。
