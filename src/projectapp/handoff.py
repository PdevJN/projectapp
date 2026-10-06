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
