"""タスクの連結(先行 → 後続)のグラフ操作。NiceGUI には依存しない純粋関数。"""

from projectapp.models import Project, Task, walk_sections


def downstream_ids(project: Project, task_id: str) -> set[str]:
    """そのタスクを、直接・間接に先行にしているタスクの id。循環があっても止まる。"""
    tasks = project.all_tasks()
    found: set[str] = set()
    frontier = [task_id]
    while frontier:
        current = frontier.pop()
        for task in tasks:
            if current in task.predecessors and task.id not in found:
                found.add(task.id)
                frontier.append(task.id)
    return found


def validate_links(tasks: list[Task]) -> None:
    """id の重複、不正な先行(存在しない・自分自身・重複)、循環があれば ValueError。"""
    ids = [task.id for task in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("タスクの id が重複しています")
    known = set(ids)
    for task in tasks:
        if len(set(task.predecessors)) != len(task.predecessors):
            raise ValueError(f"先行タスクが重複しています: {task.name}")
        for pid in task.predecessors:
            if pid == task.id:
                raise ValueError(f"タスクが自分自身を先行にしています: {task.name}")
            if pid not in known:
                raise ValueError(f"存在しない先行タスクを指しています: {task.name}")
    _reject_cycle(tasks)


def _reject_cycle(tasks: list[Task]) -> None:
    by_id = {task.id: task for task in tasks}
    state: dict[str, int] = {}  # 1 = 探索中、2 = 済み

    def visit(task_id: str) -> None:
        if state.get(task_id) == 2:
            return
        if state.get(task_id) == 1:
            raise ValueError("先行タスクが循環しています")
        state[task_id] = 1
        for pid in by_id[task_id].predecessors:
            visit(pid)
        state[task_id] = 2

    for task_id in by_id:
        visit(task_id)


def drop_task_links(project: Project, task_id: str) -> None:
    """全タスクの先行から、その id を取り除く(タスクの削除のとき)。"""
    for task in project.all_tasks():
        if task_id in task.predecessors:
            task.predecessors = [pid for pid in task.predecessors if pid != task_id]


def link_options(project: Project, task: Task | None) -> dict[str, str]:
    """先行にできるタスクの候補(id → 「セクション名 / タスク名」)。

    自分と、自分を(直接・間接に)先行にしているタスクは除く(循環を防ぐ)。
    同じ表示が複数あるときは、2 件目以降に「 (2)」などを添える。
    """
    excluded: set[str] = set()
    if task is not None:
        excluded = {task.id, *downstream_ids(project, task.id)}
    labelled: list[tuple[str, str]] = [(t.id, t.name) for t in project.tasks]
    names: dict[tuple[int, ...], str] = {}
    for path, section in walk_sections(project.sections):
        names[path] = f"{names[path[:-1]]} / {section.name}" if path[:-1] else section.name
        labelled += [(t.id, f"{names[path]} / {t.name}") for t in section.tasks]
    seen: dict[str, int] = {}
    options: dict[str, str] = {}
    for task_id, label in labelled:
        seen[label] = seen.get(label, 0) + 1
        if task_id not in excluded:
            options[task_id] = label if seen[label] == 1 else f"{label} ({seen[label]})"
    return options
