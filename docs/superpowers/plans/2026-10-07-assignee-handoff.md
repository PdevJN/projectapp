# 担当者向けファイルの書き出し 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メイン画面から担当者を 1 人選び、その担当の未終了タスクを todoapp 形式(`todos.json`)で書き出せるようにする(要望 4)。

**Architecture:** 変換とファイルの書き込みを、NiceGUI に依存しない `handoff.py` にまとめる(`build_todos` / `write_json`)。画面は、ヘッダーのボタンと、担当者を選ぶダイアログ(`forms.open_handoff_dialog`)、保存先の選択(既存の `ImageExporter.ask_path` に `file_types` を足して共用)だけを持つ。プロジェクトは保存せず、変更扱いにもしない。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-10-07-assignee-handoff-design.md`(todoapp の形式は、`file-format.md`。git 管理外)

## Global Constraints

- Python 3.13 以上。NiceGUI。画面の文言は日本語。
- 出力は、todoapp 形式の `version: 1`、UTF-8、インデント 2 の整形 JSON(`ensure_ascii=False`)。独自のキーは足さない。
- 書き込みは一時ファイル経由で、失敗したら何も残さない。
- 書き出しは、プロジェクトを変更しない(保存しない・`is_dirty()` を変えない)。
- 対象は、選んだ担当のタスクのうち、状態が「終了」以外。
- 工数は `工数 ÷ メンバーの相対比率`(割り当て率では割らない。メンバーが見つからなければ 100%)。
- テストは、実際のホーム(`~/.projectapp`・`~/.todoapp`)を読み書きしない(`tmp_path` を使う)。
- 検証: `uv run pytest -n auto -q` と `uvx ty check src`(どちらもサンドボックスの外で動かす必要がある)。

## Review Focus

- 実行中(`end` なし)の区間が、複数のタスクにまたがってあるとき: todoapp は同時に 1 件までなので、開始が最も新しい 1 件だけを残し、ほかは書き出さずに件数を通知する(Task 2)。
- 同名のタスクがあるとき、ほかのタスクが終了して対象から外れても、残るタスクの id が変わらない(書き出し直しても同じ id になる)(Task 2)。
- 担当者名がメンバーにいない・工数がない・開始予定がないタスクでも、書き出しが落ちない(Task 2)。
- ProjectCode が 10 種類を超えても、カテゴリの色が巡回して落ちない(Task 2)。
- 保存ダイアログのキャンセル・書き込み失敗のあとで、ダイアログが開いたままで、もう一度書き出せる(Task 3)。

---

## ファイル構成

| ファイル | 変更 |
|---|---|
| `src/projectapp/export.py` | `ask_path` に `file_types` を足す(`PNG_FILE_TYPES` を定義) |
| `src/projectapp/handoff.py` | 新規。`tasks_for`・`build_todos`・`summary`・`default_filename`・`write_json`(NiceGUI に依存しない) |
| `src/projectapp/forms.py` | `open_handoff_dialog` を足す |
| `src/projectapp/views.py` | ヘッダーのボタン、`open_handoff`、`export_handoff` |
| `test/test_handoff.py` | 新規。変換・書き込みのテスト |
| `test/test_views.py` | `FakeExporter` の更新、画面のテスト |
| `CLAUDE.md`・`docs/development.md`・`.claude/MEMORY.md` | 仕様・モジュール構成・作業記録 |

---

### Task 1: 保存ダイアログの種類を引数にする

**Files:**
- Modify: `src/projectapp/export.py`(定数、`ImageExporter.ask_path`、`NativeImageExporter.ask_path`)
- Modify: `src/projectapp/views.py:270`(`save_image`の呼び出し)
- Modify: `test/test_views.py`(`FakeExporter`、`test_save_writes_the_png_and_notifies`)

**Interfaces:**
- Produces: `export.PNG_FILE_TYPES: tuple[str, ...]`、`ImageExporter.ask_path(filename: str, file_types: tuple[str, ...]) -> Path | None`

- [ ] **Step 1: ブランチを切る**

```bash
git switch -c feature/assignee-handoff develop
```

- [ ] **Step 2: 失敗するテストを書く**

`test/test_views.py` の `FakeExporter` を、種類を記録する形にする。

```python
class FakeExporter:
    """画像化と保存先の選択の偽物。呼ばれた内容を記録する。"""

    def __init__(self, path: Path | None = None, error: Exception | None = None, available: bool = True) -> None:
        self.path, self.error, self._available = path, error, available
        self.captured: list[float] = []
        self.asked: list[str] = []
        self.asked_types: list[tuple[str, ...]] = []

    @property
    def available(self) -> bool:
        return self._available

    async def capture(self, pixel_ratio: float) -> bytes:
        self.captured.append(pixel_ratio)
        if self.error is not None:
            raise self.error
        return PNG_BYTES

    async def ask_path(self, filename: str, file_types: tuple[str, ...] = ()) -> Path | None:
        self.asked.append(filename)
        self.asked_types.append(file_types)
        return self.path
```

`test_save_writes_the_png_and_notifies` の、`assert exporter.asked == [...]` の次の行に足す。`PNG_FILE_TYPES` は `from projectapp.export import ExportError, PNG_FILE_TYPES` で読み込む。

```python
    assert exporter.asked_types == [PNG_FILE_TYPES]
```

- [ ] **Step 3: 失敗を確かめる**

Run: `uv run pytest test/test_views.py::test_save_writes_the_png_and_notifies -q`
Expected: FAIL(`ImportError: cannot import name 'PNG_FILE_TYPES'`)

- [ ] **Step 4: 実装する**

`src/projectapp/export.py`: 定数を `PNG_PREFIX` の下に足す。

```python
PNG_FILE_TYPES = ("PNG 画像 (*.png)",)
```

`ImageExporter` の宣言と、`NativeImageExporter.ask_path` を、次のようにする。

```python
    async def ask_path(self, filename: str, file_types: tuple[str, ...]) -> Path | None: ...
```

```python
    async def ask_path(self, filename: str, file_types: tuple[str, ...]) -> Path | None:
        import webview  # ネイティブのときだけ使う

        window = app.native.main_window
        if window is None:
            return None
        # WindowProxy のメソッドは、実行時に pywebview の Window から作られる(型の定義が静的に見えない)
        result = await window.create_file_dialog(  # ty: ignore[unresolved-attribute]
            dialog_type=webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=file_types,
        )
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])
```

`src/projectapp/views.py` の `save_image` の呼び出しと import を直す。

```python
            path = await self.exporter.ask_path(default_filename(self.project.name, date.today()), PNG_FILE_TYPES)
```

```python
from projectapp.export import (
    HTML_TO_IMAGE_URL,
    PNG_FILE_TYPES,
    ExportError,
    ...
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_views.py test/test_export.py -q`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/export.py src/projectapp/views.py test/test_views.py
git commit -m "保存ダイアログのファイルの種類を引数にする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: todoapp 形式への変換と書き込み(`handoff.py`)

**Files:**
- Create: `src/projectapp/handoff.py`
- Create: `test/test_handoff.py`

**Interfaces:**
- Consumes: `timeline.effective_end(task, project, holidays) -> datetime | None`、`timeline.combine_rate(ratio, allocation) -> float`、`Project.all_tasks()`、`Status.DONE`
- Produces:
  - `handoff.JSON_FILE_TYPES: tuple[str, ...]`
  - `handoff.Handoff`(`data: dict[str, Any]`、`task_count: int`、`skipped_records: int`)
  - `handoff.tasks_for(project: Project, member_name: str) -> list[Task]`
  - `handoff.build_todos(project: Project, member_name: str, holidays: dict[date, str]) -> Handoff`
  - `handoff.summary(handoff: Handoff) -> str`
  - `handoff.default_filename(member_name: str) -> str`
  - `handoff.write_json(path: Path, data: dict[str, Any]) -> Path`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_handoff.py` を作る。

```python
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from projectapp.handoff import (
    CATEGORY_COLORS,
    JSON_FILE_TYPES,
    Handoff,
    build_todos,
    default_filename,
    summary,
    tasks_for,
    write_json,
)
from projectapp.models import Actual, Member, Project, Section, Status, Task

BASE = date(2026, 10, 5)  # 月曜


def make_project(*tasks: Task, members: list[Member] | None = None, sections: list[Section] | None = None) -> Project:
    chosen = [Member("田中", 0.5)] if members is None else members
    return Project("案件", base_date=BASE, members=chosen, tasks=list(tasks), sections=sections or [])


def task(name: str = "設計", **kwargs) -> Task:
    kwargs.setdefault("assignee", "田中")
    return Task(name, **kwargs)


def build(project: Project, member: str = "田中") -> Handoff:
    return build_todos(project, member, {})


def assert_todoapp_shape(data: dict) -> None:
    """`file-format.md` の必須キーと型。"""
    assert set(data) == {"version", "items", "records", "categories"}
    assert data["version"] == 1
    category_ids = {c["id"] for c in data["categories"]}
    item_ids = {i["id"] for i in data["items"]}
    for category in data["categories"]:
        assert set(category) == {"id", "name", "kind", "expiry_date", "color", "prj_code"}
        assert category["color"] in CATEGORY_COLORS
        assert category["expiry_date"] is None
    for item in data["items"]:
        assert set(item) == {"id", "name", "schedule_type", "anchor_date", "estimate_hours", "category_id", "done_date"}
        assert isinstance(item["id"], str) and len(item["id"]) == 32
        assert item["schedule_type"] in {"daily", "weekly", "monthly", "one_time"}
        date.fromisoformat(item["anchor_date"])
        assert isinstance(item["estimate_hours"], float)
        assert item["category_id"] is None or item["category_id"] in category_ids
        assert item["done_date"] is None
    for record in data["records"]:
        assert set(record) == {"id", "item_id", "item_name", "start_time", "end_time"}
        assert record["item_id"] in item_ids
        datetime.fromisoformat(record["start_time"])
        assert record["end_time"] is None or datetime.fromisoformat(record["end_time"])


def test_only_unfinished_tasks_of_the_member_are_exported_in_order() -> None:
    project = make_project(
        task("a"),
        task("done", status=Status.DONE),
        task("other", assignee="鈴木"),
        task("nobody", assignee=None),
        sections=[Section("S", [task("s1", status=Status.RUNNING)])],
    )
    result = build(project)
    assert [i["name"] for i in result.data["items"]] == ["a", "s1"]
    assert result.task_count == 2
    assert [t.name for t in tasks_for(project, "田中")] == ["a", "s1"]
    assert_todoapp_shape(result.data)


@pytest.mark.parametrize(
    ("kwargs", "schedule_type", "anchor"),
    [
        (dict(planned_start=datetime(2026, 10, 5, 9), effort_hours=3), "one_time", "2026-10-05"),  # 6h で 1 日に収まる
        (dict(planned_start=datetime(2026, 10, 5, 9), effort_hours=13), "daily", "2026-10-05"),  # 26h で 4 日
        ({}, "one_time", "2026-10-05"),  # 開始予定なし → 基準日
        (dict(planned_start=datetime(2026, 10, 6, 9)), "one_time", "2026-10-06"),  # 期間の情報がない
        (dict(planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 6, 17)), "one_time", "2026-10-06"),
        (dict(planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 7, 0, 0)), "one_time", "2026-10-06"),
        (dict(planned_start=datetime(2026, 10, 6, 9), planned_end=datetime(2026, 10, 8, 12)), "daily", "2026-10-06"),
        (dict(planned_start=datetime(2026, 10, 6, 9), deadline=datetime(2026, 10, 9, 17)), "daily", "2026-10-06"),
    ],
    ids=["one-day", "multi-day", "no-start", "no-span", "same-day-end", "midnight-end", "later-end", "deadline-only"],
)
def test_schedule_type_and_anchor_date(kwargs: dict, schedule_type: str, anchor: str) -> None:
    item = build(make_project(task(**kwargs))).data["items"][0]
    assert (item["schedule_type"], item["anchor_date"]) == (schedule_type, anchor)


@pytest.mark.parametrize(
    ("effort", "members", "expected"),
    [
        (13.0, [Member("田中", 0.5)], 26.0),  # 相対比率 50% → 担当者は 2 倍の時間
        (13.0, [], 13.0),  # メンバーにいない担当者は 100%
        (0.0, [Member("田中", 0.5)], 0.0),
        (1.0, [Member("田中", 0.3)], 3.33),  # 小数第 2 位に丸める
    ],
)
def test_estimate_hours_divides_by_the_relative_ratio(effort: float, members: list[Member], expected: float) -> None:
    item = build(make_project(task(effort_hours=effort), members=members)).data["items"][0]
    assert item["estimate_hours"] == expected


def test_the_allocation_does_not_change_the_estimate() -> None:
    item = build(make_project(task(effort_hours=13.0, allocation=0.25))).data["items"][0]
    assert item["estimate_hours"] == 26.0


def test_categories_follow_project_codes() -> None:
    project = make_project(
        task("A", project_code="PRJ-1"), task("B", project_code="PRJ-2"), task("C", project_code="PRJ-1"), task("D")
    )
    data = build(project).data
    first, second = data["categories"]
    assert [first["name"], second["name"]] == ["PRJ-1", "PRJ-2"]
    assert (first["prj_code"], first["kind"]) == ("PRJ-1", "")
    assert [first["color"], second["color"]] == ["blue", "indigo"]
    assert [i["category_id"] for i in data["items"]] == [first["id"], second["id"], first["id"], None]
    assert_todoapp_shape(data)


def test_category_colors_cycle_after_ten_codes() -> None:
    project = make_project(*(task(f"t{i}", project_code=f"C{i}") for i in range(11)))
    categories = build(project).data["categories"]
    assert len(categories) == 11
    assert categories[10]["color"] == categories[0]["color"] == "blue"


def test_actuals_become_records() -> None:
    work = task(actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 10, 30, 15)), Actual(datetime(2026, 10, 6, 9))])
    result = build(make_project(work))
    item = result.data["items"][0]
    first, second = result.data["records"]
    assert (first["start_time"], first["end_time"]) == ("2026-10-05T09:00:00", "2026-10-05T10:30:15")
    assert (second["start_time"], second["end_time"]) == ("2026-10-06T09:00:00", None)
    assert first["item_id"] == second["item_id"] == item["id"]
    assert first["item_name"] == "設計"
    assert first["id"] != second["id"]
    assert result.skipped_records == 0
    assert_todoapp_shape(result.data)


def test_only_the_latest_running_record_is_kept() -> None:
    a = task("a", actuals=[Actual(datetime(2026, 10, 4, 9), datetime(2026, 10, 4, 10)), Actual(datetime(2026, 10, 5, 9))])
    b = task("b", actuals=[Actual(datetime(2026, 10, 6, 9))])
    result = build(make_project(a, b))
    items = {i["name"]: i["id"] for i in result.data["items"]}
    running = [r for r in result.data["records"] if r["end_time"] is None]
    assert [r["item_id"] for r in running] == [items["b"]]
    assert len(result.data["records"]) == 2  # a の終了した区間と、b の実行中
    assert result.skipped_records == 1


def test_ids_are_stable_across_exports_and_task_changes() -> None:
    first, second = task("同名"), task("同名")
    before = build(make_project(first, second)).data
    assert before == build(make_project(first, second)).data
    ids = [i["id"] for i in before["items"]]
    assert ids[0] != ids[1]
    first.status = Status.DONE  # 対象から外れても、残るタスクの id は変わらない
    after = build(make_project(first, second)).data
    assert [i["id"] for i in after["items"]] == [ids[1]]


def test_nothing_about_other_people_is_exported() -> None:
    project = make_project(task("自分"), task("別件", assignee="鈴木"), members=[Member("田中", 0.5), Member("鈴木", 2.0)])
    text = json.dumps(build(project).data, ensure_ascii=False)
    assert "鈴木" not in text and "別件" not in text and "assignee" not in text


def test_an_empty_result_is_valid() -> None:
    result = build(make_project())
    assert result.task_count == 0
    assert result.data == {"version": 1, "items": [], "records": [], "categories": []}


def test_summary_mentions_skipped_records_only_when_there_are_some() -> None:
    assert summary(Handoff({}, 3, 0)) == "3 件を書き出しました"
    assert summary(Handoff({}, 3, 2)) == "3 件を書き出しました(実行中の記録が複数あったため、2 件は書き出していません)"


@pytest.mark.parametrize(
    ("member", "expected"),
    [("田中", "todos-田中.json"), ("a/b:c", "todos-a_b_c.json"), ("  ", "todos-member.json"), ("..x", "todos-x.json")],
)
def test_default_filename(member: str, expected: str) -> None:
    assert default_filename(member) == expected


def test_write_json_writes_pretty_utf8_and_adds_the_extension(tmp_path: Path) -> None:
    data = {"version": 1, "items": [{"name": "設計"}]}
    path = write_json(tmp_path / "todos", data)
    assert path == tmp_path / "todos.json"
    text = path.read_text(encoding="utf-8")
    assert "設計" in text and '\n  "version": 1' in text and text.endswith("\n")
    assert json.loads(text) == data
    assert [p.name for p in tmp_path.iterdir()] == ["todos.json"]


def test_write_json_leaves_nothing_on_failure(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_json(tmp_path / "todos.json", {"x": object()})
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(OSError):
        write_json(tmp_path / "missing" / "todos.json", {})


def test_json_file_types_name_the_extension() -> None:
    assert any("*.json" in t for t in JSON_FILE_TYPES)
```

注: `default_filename("..x")` は先頭の `.` を落として `todos-x.json`(`..x` → `lstrip(".")` → `x`)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_handoff.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.handoff'`)

- [ ] **Step 3: 実装する**

`src/projectapp/handoff.py` を作る。

```python
"""担当者向けファイルの書き出し。タスクを todoapp(`~/.todoapp/todos.json`)の形式へ変える。NiceGUI には依存しない。"""

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import date, time, timedelta
from math import isfinite
from pathlib import Path
from typing import Any

from projectapp.models import Project, Status, Task
from projectapp.timeline import combine_rate, effective_end

NAMESPACE = uuid.UUID("5b0f3c1e-8a42-4d6f-9e17-3c2a7d94b0e8")  # 決定的な id の元。変えると、書き出し直しの id が変わる
CATEGORY_COLORS = ("blue", "indigo", "purple", "pink", "red", "orange", "amber", "green", "teal", "brown")
JSON_FILE_TYPES = ("JSON ファイル (*.json)",)
UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


@dataclass
class Handoff:
    data: dict[str, Any]  # todoapp 形式
    task_count: int
    skipped_records: int  # 実行中の記録が複数あったため、書き出さなかった件数


def tasks_for(project: Project, member_name: str) -> list[Task]:
    """選んだ担当の、終了していないタスク(`all_tasks()` の順)。"""
    return [t for t in project.all_tasks() if t.assignee == member_name and t.status != Status.DONE]


def _uuid(*parts: str) -> str:
    return uuid.uuid5(NAMESPACE, "\n".join(parts)).hex


def _task_keys(project: Project) -> dict[int, str]:
    """タスクの識別名。同名の 2 件目以降は `名前#2`。対象かどうかによらず数えるので、ほかのタスクの状態で変わらない。"""
    seen: dict[str, int] = {}
    keys: dict[int, str] = {}
    for task in project.all_tasks():
        seen[task.name] = seen.get(task.name, 0) + 1
        keys[id(task)] = task.name if seen[task.name] == 1 else f"{task.name}#{seen[task.name]}"
    return keys


def _schedule(task: Task, project: Project, holidays: dict[date, str]) -> tuple[str, str]:
    """(schedule_type, anchor_date)。期間が複数日なら daily、それ以外は one_time。"""
    start = task.planned_start
    anchor = start.date() if start is not None else project.base_date
    no_span = task.effort_hours <= 0 and task.planned_end is None and task.deadline is None
    if start is None or no_span:
        return "one_time", anchor.isoformat()
    end = effective_end(task, project, holidays)
    if end is None:
        return "one_time", anchor.isoformat()
    last = end - timedelta(seconds=1) if end.time() == time(0, 0) else end  # 0 時ちょうどは、前日の終わり
    return ("daily" if last.date() > anchor else "one_time"), anchor.isoformat()


def _estimate_hours(task: Task, project: Project) -> float:
    if not isfinite(task.effort_hours) or task.effort_hours <= 0:
        return 0.0
    member = next((m for m in project.members if m.name == task.assignee), None)
    ratio = combine_rate(member.ratio, 1.0) if member is not None else 1.0
    return round(task.effort_hours / ratio, 2)


def build_todos(project: Project, member_name: str, holidays: dict[date, str]) -> Handoff:
    tasks = tasks_for(project, member_name)
    keys = _task_keys(project)
    categories: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    pairs: list[tuple[str, Task]] = []
    for task in tasks:
        item_id = _uuid(project.name, keys[id(task)])
        category_id = None
        if task.project_code:
            category = categories.get(task.project_code)
            if category is None:
                category = {
                    "id": _uuid(project.name, "category", task.project_code),
                    "name": task.project_code,
                    "kind": "",
                    "expiry_date": None,
                    "color": CATEGORY_COLORS[len(categories) % len(CATEGORY_COLORS)],
                    "prj_code": task.project_code,
                }
                categories[task.project_code] = category
            category_id = category["id"]
        schedule_type, anchor = _schedule(task, project, holidays)
        items.append(
            {
                "id": item_id,
                "name": task.name,
                "schedule_type": schedule_type,
                "anchor_date": anchor,
                "estimate_hours": _estimate_hours(task, project),
                "category_id": category_id,
                "done_date": None,
            }
        )
        pairs.append((item_id, task))
    records, skipped = _records(pairs)
    data = {"version": 1, "items": items, "records": records, "categories": list(categories.values())}
    return Handoff(data, len(tasks), skipped)


def _records(pairs: list[tuple[str, Task]]) -> tuple[list[dict[str, Any]], int]:
    """実績を記録にする。todoapp は実行中を同時に 1 件までとするので、開始が最も新しい 1 件だけを残す。"""
    running = [a for _, task in pairs for a in task.actuals if a.end is None]
    keep = max(running, key=lambda a: a.start, default=None)
    records: list[dict[str, Any]] = []
    skipped = 0
    for item_id, task in pairs:
        for actual in task.actuals:
            if actual.end is None and actual is not keep:
                skipped += 1
                continue
            start = actual.start.isoformat(timespec="seconds")
            records.append(
                {
                    "id": _uuid(item_id, start),
                    "item_id": item_id,
                    "item_name": task.name,
                    "start_time": start,
                    "end_time": actual.end.isoformat(timespec="seconds") if actual.end is not None else None,
                }
            )
    return records, skipped


def summary(handoff: Handoff) -> str:
    text = f"{handoff.task_count} 件を書き出しました"
    if handoff.skipped_records:
        text += f"(実行中の記録が複数あったため、{handoff.skipped_records} 件は書き出していません)"
    return text


def default_filename(member_name: str) -> str:
    """既定のファイル名 `todos-<メンバー名>.json`。ファイル名に使えない文字は `_` にする。"""
    name = UNSAFE_NAME_CHARS.sub("_", member_name.strip()).lstrip(".")
    return f"todos-{name or 'member'}.json"


def write_json(path: Path, data: dict[str, Any]) -> Path:
    """JSON を書く。拡張子がなければ .json を付ける。一時ファイル経由で、失敗したら何も残さない。"""
    if not path.suffix:
        path = path.with_name(path.name + ".json")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".handoff-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_handoff.py -q`
Expected: PASS(落ちるテストがあれば、期待値を先に疑わず、実装と設計書の対応を確かめる)

Run: `uvx ty check src`
Expected: All checks passed!

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/handoff.py test/test_handoff.py
git commit -m "担当者向けファイル: todoapp 形式への変換と書き込みを追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 画面(ボタン・ダイアログ・書き出し)

**Files:**
- Modify: `src/projectapp/forms.py`(`open_handoff_dialog`。`open_members_dialog` の後ろ)
- Modify: `src/projectapp/views.py`(import、ヘッダー、`open_handoff`、`export_handoff`)
- Modify: `test/test_views.py`(末尾にテストを足す。import に `JSON_FILE_TYPES` を足す)

**Interfaces:**
- Consumes: `handoff.tasks_for`・`build_todos`・`summary`・`default_filename`・`write_json`・`JSON_FILE_TYPES`、`ImageExporter.ask_path(filename, file_types)`、`ImageExporter.available`
- Produces: `forms.open_handoff_dialog(names: list[str], count_for: Callable[[str], int], on_export: Callable[[str], Awaitable[bool]]) -> None`(`on_export` が `True` を返したら閉じる)、`MainView.open_handoff()`、`MainView.export_handoff(member_name) -> bool`。マーカー: `export-handoff`(ヘッダーのボタン)、`handoff-member`(選択)、`handoff-count`(件数の文)、`handoff-export`(書き出すボタン)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の import に、`from projectapp.handoff import JSON_FILE_TYPES` を足す。ファイルの末尾に、次を足す。

```python
async def open_handoff_view(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    view = views[0]
    view.project.base_date = date(2026, 10, 5)
    return view


def assign(view: MainView) -> None:
    view.project.members = [Member("田中", 0.5)]
    view.save_task(None, None, Task("設計", assignee="田中", planned_start=datetime(2026, 10, 5, 9), effort_hours=3))
    view.mark_clean()


async def test_handoff_needs_members(user: User, tmp_path: Path) -> None:
    await open_handoff_view(user, tmp_path, FakeExporter())
    user.find(marker="export-handoff").click()
    await user.should_see("メンバーが登録されていません")
    await user.should_not_see(marker="handoff-member")


async def test_handoff_needs_the_native_window(user: User, tmp_path: Path) -> None:
    view = await open_handoff_view(user, tmp_path, FakeExporter(available=False))
    assign(view)
    user.find(marker="export-handoff").click()
    await user.should_see("ネイティブウィンドウでのみ、書き出せます")
    await user.should_not_see(marker="handoff-member")


async def test_handoff_disables_export_without_unfinished_tasks(user: User, tmp_path: Path) -> None:
    view = await open_handoff_view(user, tmp_path, FakeExporter())
    view.project.members = [Member("田中", 0.5)]
    user.find(marker="export-handoff").click()
    await user.should_see("終了以外のタスクがありません")
    assert not user.find(marker="handoff-export").elements.pop().enabled


async def test_handoff_writes_todoapp_json_and_keeps_the_project_clean(user: User, tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    exporter = FakeExporter(path=tmp_path / "out" / "todos")
    view = await open_handoff_view(user, tmp_path, exporter)
    assign(view)
    user.find(marker="export-handoff").click()
    await user.should_see("終了以外のタスク: 1 件")
    user.find(marker="handoff-export").click()
    target = tmp_path / "out" / "todos.json"
    assert await wait_until(target.exists)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert [(i["name"], i["schedule_type"], i["estimate_hours"]) for i in data["items"]] == [("設計", "one_time", 6.0)]
    assert exporter.asked == ["todos-田中.json"]
    assert exporter.asked_types == [JSON_FILE_TYPES]
    await user.should_see("1 件を書き出しました")
    assert not view.is_dirty()


async def test_cancelling_the_save_dialog_keeps_the_dialog_open(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    view = await open_handoff_view(user, tmp_path, exporter)
    assign(view)
    user.find(marker="export-handoff").click()
    user.find(marker="handoff-export").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.rglob("*.json"))
    await user.should_see(marker="handoff-member")
    assert await wait_until(lambda: user.find(marker="handoff-export").elements.pop().enabled)  # もう一度押せる


async def test_a_write_failure_is_reported_and_the_dialog_stays(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "missing" / "todos.json")
    view = await open_handoff_view(user, tmp_path, exporter)
    assign(view)
    user.find(marker="export-handoff").click()
    user.find(marker="handoff-export").click()
    await user.should_see("保存できませんでした")
    await user.should_see(marker="handoff-member")
    assert await wait_until(lambda: user.find(marker="handoff-export").elements.pop().enabled)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -k handoff -q`
Expected: FAIL(`export-handoff` が見つからない)

- [ ] **Step 3: ダイアログを実装する**

`src/projectapp/forms.py` の冒頭の import に `Awaitable` を足す(`from collections.abc import Awaitable, Callable`)。`open_members_dialog` の後ろに足す。

```python
def open_handoff_dialog(
    names: list[str],
    count_for: Callable[[str], int],
    on_export: Callable[[str], Awaitable[bool]],
) -> None:
    """担当者を選んで、その担当の書き出しを頼む。`on_export` が True を返したら閉じる(キャンセル・失敗は開いたまま)。"""
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[28rem] max-w-full"):
        ui.label("担当者へ書き出し").classes("text-h6")
        select = ui.select(
            names, value=names[0], label="担当者", on_change=lambda _: update()
        ).classes("w-full").mark("handoff-member")
        info = ui.label().mark("handoff-count")

        def update() -> None:
            count = count_for(select.value)
            info.set_text(f"終了以外のタスク: {count} 件" if count else "終了以外のタスクがありません")
            export.set_enabled(count > 0)

        async def run() -> None:
            export.disable()
            closing = False
            try:
                closing = await on_export(select.value)
            finally:
                if closing:
                    dialog.close()
                else:
                    update()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            export = ui.button("書き出す", on_click=run).mark("handoff-export")
        update()
    dialog.open()
```

- [ ] **Step 4: 画面を実装する**

`src/projectapp/views.py`:

import: `forms` の import に `open_handoff_dialog` を足し、新しく足す。

```python
from projectapp.handoff import (
    JSON_FILE_TYPES,
    build_todos,
    summary,
    tasks_for,
    write_json,
)
from projectapp.handoff import default_filename as handoff_filename
```

定数(`NEW_PROJECT_NAME` の下):

```python
HANDOFF_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、書き出せます"
```

`open_members` の前にメソッドを足す。

```python
    def open_handoff(self) -> None:
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not self.project.members:
            ui.notify("メンバーが登録されていません", type="warning")
            return
        open_handoff_dialog(
            [m.name for m in self.project.members],
            lambda name: len(tasks_for(self.project, name)),
            self.export_handoff,
        )

    async def export_handoff(self, member_name: str) -> bool:
        """選んだ担当の未終了タスクを、todoapp 形式で書き出す。閉じてよいとき(書き出せたとき)だけ True。プロジェクトは変えない。"""
        result = build_todos(self.project, member_name, self.holidays)
        if result.task_count == 0:
            return False
        path = await self.exporter.ask_path(handoff_filename(member_name), JSON_FILE_TYPES)
        if path is None:
            return False
        try:
            write_json(path, result.data)
        except OSError as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return False
        ui.notify(summary(result))
        return True
```

ヘッダーの「エクスポート」ボタンの後ろに足す。

```python
                ui.button("担当者へ書き出し", icon="upload_file", on_click=self.open_handoff).mark(
                    "export-handoff"
                )
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_views.py -k "handoff or save or cancelling" -q`
Expected: PASS

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて PASS / All checks passed!

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_views.py
git commit -m "担当者向けファイル: ヘッダーのボタンと書き出しのダイアログを追加する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ドキュメント

**Files:**
- Modify: `CLAUDE.md`(「プロジェクトファイル」の節の後ろ)
- Modify: `docs/development.md`(モジュール表・設計書表)
- Modify: `.claude/MEMORY.md`(要望 4 の状況・参照先・ブランチ)

- [ ] **Step 1: `CLAUDE.md` に仕様を足す**

「## プロジェクトファイル」の節の末尾に、新しい節を足す。

```markdown
## 担当者向けファイル

- メイン画面の「担当者へ書き出し」で、メンバーを 1 人選び、その担当の状態が`終了`以外のタスクを、todoapp(別アプリ)の形式の`todos.json`として書き出せる(保存先は、ファイル保存ダイアログで選ぶ。ネイティブウィンドウのみ)
- todoapp の形式(`version: 1`)のままで、独自のキーは足さない。状態・進捗度・優先度・締切・他の担当者のタスク・メンバーの比率・添付ファイルは書き出さない
- 期間が複数日のタスクは`daily`、1 日(または期間の情報がない)のタスクは`one_time`、基準日は開始予定の日。見積もりは`工数 ÷ メンバーの相対比率`(担当者自身の時間)。ProjectCode はカテゴリ(`prj_code`)にする。実績は`records`にする(実行中の記録は、開始が最も新しい 1 件だけ)
- 書き出しは、プロジェクトを保存せず、変更扱いにもしない。担当者からの返送の取り込みは後続機能
```

- [ ] **Step 2: `docs/development.md` を直す**

モジュール表の、`export.py` の行の後ろに足す。

```markdown
| `handoff.py` | 担当者向けファイルの書き出し。タスクを todoapp 形式(`items`・`records`・`categories`)へ変える(`build_todos`)、書き込み(`write_json`)。純粋関数(NiceGUI に依存しない)。id は`uuid5`で決まる(同名のタスクは`名前#2`)。todoapp の形式は`file-format.md`(git 管理外) |
```

`export.py` の行の「保存ダイアログ(`ImageExporter`)」の説明に「(`ask_path` は、ファイルの種類を引数に取る。担当者向けファイルでも使う)」を足す。設計書の表の末尾に足す。

```markdown
| 担当者向けファイルの書き出し | `2026-10-07-assignee-handoff-design.md` |
```

- [ ] **Step 3: `.claude/MEMORY.md` を直す**

次の 3 点を、実際の結果に合わせて直す(テスト件数・コミットは、`uv run pytest -n auto -q` と `git log` の結果を使う)。
- 「今後の要望」の 4 に `(完了)` を付け、「対応:」に、方式(todoapp 形式で書き出し、ブランチ `feature/assignee-handoff`、設計書・実装計画の名前)を 1〜2 文で足す。未着手の一覧から 4 を外す。
- 「現在の状況」の要約に、書き出しの項目を足す(マージ前は「ブランチで実装済み。実機の確認待ち」)。
- 「参照先」に、設計書 `2026-10-07-assignee-handoff-design.md` と実装計画 `2026-10-07-assignee-handoff.md` を足す。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs/development.md .claude/MEMORY.md
git commit -m "担当者向けファイル: 仕様・開発メモ・作業記録を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## 完了の条件

- `uv run pytest -n auto -q` と `uvx ty check src` が通る。
- 実機(ネイティブウィンドウ)で、次を確かめる(自動テストは偽の保存ダイアログを使う)。
  - 「担当者へ書き出し」→ 担当者を選ぶ → 保存ダイアログが開き、`todos-<名前>.json` が既定で入る。
  - 書き出したファイルを、todoapp の `~/.todoapp/todos.json` として置いて、アイテム・カテゴリ(ProjectCode)・実績が、todoapp で正しく見える。
  - キャンセルしたあと、ダイアログが開いたままで、もう一度書き出せる。
- マージ・プッシュは、ユーザーの許可を得てから行う。
