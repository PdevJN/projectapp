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
    return [
        project.tasks,
        *(section.tasks for _, section in walk_sections(project.sections)),
    ]


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
        return (
            Section(section.name, tasks, children, id=section.id)
            if tasks or children
            else None
        )

    child_tasks = [moved_copy(t) for t in project.tasks if t.id in moved]
    child_sections = [s for s in map(pick, project.sections) if s is not None]

    crew = {n for t in used for n in _crew_names(t)}
    # 付けたパラメータがなく担当のいるタスクの相対比率は全パラメータの合計なので、1 つでもあれば全パラメータを持ち越す
    needs_all = any(
        t.kind is TaskKind.NORMAL and t.assignees and not t.parameters for t in used
    )
    picked = {p for t in used for p in t.parameters}
    parameters = [
        deepcopy(p) for p in project.parameters if needs_all or p.name in picked
    ]
    kept_levels = {p.name for p in parameters}
    members = []
    for member in project.members:
        if member.name in crew:
            copy = deepcopy(member)
            copy.teams = []
            copy.levels = {k: v for k, v in member.levels.items() if k in kept_levels}
            members.append(copy)
    category_ids = {t.category_id for t in used if t.category_id is not None}
    template_names = {
        u.template for t in used for u in t.urls if u.template is not None
    }
    child = Project(
        name,
        base_date=project.base_date,
        daily_hours=project.daily_hours,
        work_start=project.work_start,
        members=members,
        sections=child_sections,
        tasks=child_tasks,
        actual_mode=project.actual_mode,
        url_templates=[
            deepcopy(u) for u in project.url_templates if u.name in template_names
        ],
        parameters=parameters,
        categories=[deepcopy(c) for c in project.categories if c.id in category_ids],
        events=deepcopy(project.events),
        reference_mode=project.reference_mode,
        plantuml_overload_notice=project.plantuml_overload_notice,
        ratio_limit_upper=project.ratio_limit_upper,
        ratio_limit_lower=project.ratio_limit_lower,
    )

    parent = deepcopy(project)
    owner = parent_map(project).get(
        moved_ids[0]
    )  # 最初のタスクがまとめの子なら、参照行はそのまとめの子になる
    reference = Task(
        name, id=new_id(parent.used_ids()), kind=TaskKind.REFERENCE, ref_project=name
    )
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
