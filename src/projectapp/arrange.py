"""タスクの移動・コピー・日程のずらし(純粋関数)と、画面から届く値の検証。"""

import re
from dataclasses import replace
from datetime import date, datetime, timedelta


from projectapp.models import (
    MAX_SECTION_DEPTH,
    MAX_TASK_NAME_LENGTH,
    MAX_YEAR,
    MIN_YEAR,
    Project,
    Section,
    SectionPath,
    Task,
    TaskKind,
    new_id,
    walk_sections,
)
from projectapp.summary import children_of

Position = tuple[SectionPath, int]  # (セクションのパス。root は (), 番号)
COPY_SUFFIX = "(コピー)"
FIRST_CHILD_NAME = "子 1"  # まとめと一緒に作る、最初の子の名前
MAX_SHIFT_DAYS = 3650
_KEY = re.compile(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){0,%d}" % (MAX_SECTION_DEPTH - 1))


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


def tasks_at(project: Project, path: SectionPath) -> list[Task]:
    if not path:
        return project.tasks
    found = section_at(project, path)
    if found is None:
        raise IndexError(path)
    return found.tasks


def valid_section(project: Project, path: SectionPath) -> bool:
    return not path or (len(path) <= MAX_SECTION_DEPTH and section_at(project, path) is not None)


def has_task(project: Project, position: Position) -> bool:
    section, index = position
    return valid_section(project, section) and 0 <= index < len(tasks_at(project, section))


def has_list(project: Project, position: Position) -> bool:
    """挿入先として使えるか。番号は末尾に丸めるので、0 以上ならよい。"""
    section, index = position
    return valid_section(project, section) and index >= 0


def move_task(project: Project, src: Position, dst: Position) -> bool:
    """`dst` の番号は、取り除く前の一覧での挿入位置。位置が変わらないときは False。"""
    source = tasks_at(project, src[0])
    target = tasks_at(project, dst[0])
    index = _outside_blocks(target, min(dst[1], len(target)), source[src[1]])
    size = _block_size(source, src[1])
    if source is target:
        if src[1] <= index <= src[1] + size:
            return False
        if index > src[1]:
            index -= size
    block = source[src[1] : src[1] + size]
    del source[src[1] : src[1] + size]
    target[index:index] = block
    return True


def _outside_blocks(tasks: list[Task], index: int, moving: Task) -> int:
    """まとめと子のあいだ(かたまりの内側)への挿入は、かたまりの後ろへ送る。同じまとめの子の並べ替えは除く。"""
    for start, task in enumerate(tasks):
        if task.kind is not TaskKind.SUMMARY or moving.id in task.children or moving is task:
            continue
        end = start + _block_size(tasks, start)
        if start < index < end:
            return end
    return index


def _block_size(tasks: list[Task], index: int) -> int:
    """タスクと一緒に動かす行数。まとめは、直後に続く子を含める(それ以外は 1)。"""
    task = tasks[index]
    end = index + 1
    if task.kind is TaskKind.SUMMARY:
        while end < len(tasks) and tasks[end].id in task.children:
            end += 1
    return end - index


def _plain_copy(original: Task, task_id: str, name: str) -> Task:
    """連結・実績を持たない複製。担当とリンクは独立した複製にする。"""
    return replace(
        original,
        name=name,
        id=task_id,
        predecessors=[],
        actuals=[],
        assignees=[replace(a) for a in original.assignees],
        weekly_crew=[[replace(a) for a in week] for week in original.weekly_crew],
        parameters=list(original.parameters),
        urls=[replace(u, values=dict(u.values)) for u in original.urls],
    )


def after_task(project: Project, src: Position) -> Position:
    """タスクの直後の挿入位置。まとめは、続く子の後ろ。"""
    path, index = src
    tasks = tasks_at(project, path)
    task = tasks[index]
    after = index + 1
    if task.kind is TaskKind.SUMMARY:
        while after < len(tasks) and tasks[after].id in task.children:
            after += 1
    return path, after


def insert_named_task(project: Project, dst: Position, name: str) -> Task:
    """名前だけの通常タスクを dst に挿入して返す(名前の検証は呼び出し側)。番号は末尾に丸める。"""
    path, index = dst
    task = Task(name, id=new_id(project.used_ids()))
    tasks_at(project, path).insert(index, task)
    return task


def parent_of(project: Project, src: Position) -> Task | None:
    """タスクが、まとめの子なら、そのまとめ(同じ一覧にいる)。子でなければ None。"""
    path, index = src
    tasks = tasks_at(project, path)
    task = tasks[index]
    return next((t for t in tasks if t.kind is TaskKind.SUMMARY and task.id in t.children), None)


def insert_named_child(project: Project, dst: Position, name: str, parent_id: str) -> Task:
    """名前だけの通常タスクを dst に挿入し、まとめ parent_id の子にする。直前が子ならその子の後ろ、そうでなければ子の末尾に入る。"""
    path, index = dst
    tasks = tasks_at(project, path)
    parent = next((t for t in tasks if t.id == parent_id and t.kind is TaskKind.SUMMARY), None)
    if parent is None:
        raise ValueError("まとめが見つかりません")
    before = tasks[index - 1].id if 0 < index <= len(tasks) else None
    task = insert_named_task(project, dst, name)
    at = parent.children.index(before) + 1 if before in parent.children else len(parent.children)
    parent.children.insert(at, task.id)
    return task


def insert_named_summary(project: Project, dst: Position, name: str) -> Task:
    """まとめを dst に挿入して返す。子のないまとめは通常タスクに戻るので、最初の子(「子 1」)を直後に一緒に作る。"""
    path, index = dst
    taken = project.used_ids()
    child = Task(FIRST_CHILD_NAME, id=new_id(taken))
    taken.add(child.id)
    summary = Task(name, id=new_id(taken), kind=TaskKind.SUMMARY, children=[child.id])
    tasks = tasks_at(project, path)
    at = min(index, len(tasks))
    tasks[at:at] = [summary, child]
    return summary


def copy_task(project: Project, src: Position, dst: Position) -> Task:
    """タスクを dst に複製する。まとめは、子も複製して直後に並べる(子同士の先行は複製へ付け替え、外への先行は外す)。"""
    original = tasks_at(project, src[0])[src[1]]
    taken = project.used_ids()
    copy_id = new_id(taken)
    taken.add(copy_id)
    copy = _plain_copy(original, copy_id, original.name[: MAX_TASK_NAME_LENGTH - len(COPY_SUFFIX)] + COPY_SUFFIX)  # 上限を超えないよう、元の名前を切り詰める
    copies = [copy]
    if original.kind is TaskKind.SUMMARY:
        kids = children_of(original, project.task_map())
        renamed: dict[str, str] = {}
        for kid in kids:
            renamed[kid.id] = new_id(taken)
            taken.add(renamed[kid.id])
        for kid in kids:
            kid_copy = _plain_copy(kid, renamed[kid.id], kid.name)
            kid_copy.predecessors = [renamed[pid] for pid in kid.predecessors if pid in renamed]
            copies.append(kid_copy)
        copy.children = [renamed[kid.id] for kid in kids]
    else:
        copy.children = []
    target = tasks_at(project, dst[0])
    at = min(dst[1], len(target))
    target[at:at] = copies
    return copy


def _sections_list(project: Project, path: SectionPath) -> list[Section]:
    """そのセクションが入っている一覧(root か、親のサブセクション)。"""
    if len(path) == 1:
        return project.sections
    parent = section_at(project, path[:-1])
    if parent is None:
        raise IndexError(path)
    return parent.sections


def _copy_sections(section: Section, task_ids: dict[str, str], taken: set[str]) -> Section:
    """セクションの木を、新しい id で複製する(タスクの連結・まとめの子は、あとで付け替える)。"""
    tasks = []
    for task in section.tasks:
        copy = _plain_copy(task, task_ids[task.id], task.name)
        tasks.append(copy)
    children = [_copy_sections(child, task_ids, taken) for child in section.sections]
    section_id = new_id(taken)
    taken.add(section_id)
    return Section(section.name, tasks, children, id=section_id)


def copy_section(project: Project, path: SectionPath) -> Section:
    """セクションを、中のタスク・サブセクションごと複製して、直後に置く(名前に`(コピー)`を付ける)。

    中のタスク同士の先行・まとめの子は複製へ付け替え、外への先行と実績は引き継がない。
    外のタスクを子に持つまとめは、その子を外し、0 件になれば通常タスクに戻す。
    """
    siblings = _sections_list(project, path)
    original = siblings[path[-1]]
    taken = project.used_ids()
    task_ids: dict[str, str] = {}
    for task in original.all_tasks():
        task_ids[task.id] = new_id(taken)
        taken.add(task_ids[task.id])
    copy = _copy_sections(original, task_ids, taken)
    copy.name = original.name + COPY_SUFFIX
    old_by_new = {new: old for old, new in task_ids.items()}
    old_tasks = {task.id: task for task in original.all_tasks()}
    for task in copy.all_tasks():
        source = old_tasks[old_by_new[task.id]]
        task.predecessors = [task_ids[pid] for pid in source.predecessors if pid in task_ids]
        task.children = [task_ids[cid] for cid in source.children if cid in task_ids]
        if task.kind is TaskKind.SUMMARY and not task.children:
            task.kind = TaskKind.NORMAL
    siblings.insert(path[-1] + 1, copy)
    return copy


def delete_section(project: Project, path: SectionPath) -> list[Task]:
    """セクションを取り除く。中のタスク(サブセクションのも含む)は、root の末尾へ順に移し、移したタスクを返す。"""
    removed = _sections_list(project, path).pop(path[-1])
    moved = removed.all_tasks()
    project.tasks.extend(moved)
    return moved


def move_section(project: Project, path: SectionPath, to_index: int) -> bool:
    """セクションを、同じ親の一覧の to_index の位置へ移す。範囲外・同じ位置なら何もせず False。"""
    if not path or (len(path) > 1 and section_at(project, path[:-1]) is None):
        return False
    siblings = _sections_list(project, path)
    index = path[-1]
    if not (0 <= index < len(siblings) and 0 <= to_index < len(siblings)) or index == to_index:
        return False
    siblings.insert(to_index, siblings.pop(index))
    return True


def reorder_collapsed(
    collapsed: set[SectionPath], parent: SectionPath, src: int, dst: int
) -> set[SectionPath]:
    """兄弟の src を dst へ移したぶん、折りたたみのパスを付け替える(子孫は動かしたセクションに付く)。"""
    result: set[SectionPath] = set()
    depth = len(parent)
    for path in collapsed:
        if len(path) <= depth or path[:depth] != parent:
            result.add(path)
            continue
        number = path[depth]
        if number == src:
            number = dst
        elif src < number <= dst:
            number -= 1
        elif dst <= number < src:
            number += 1
        result.add((*parent, number, *path[depth + 1 :]))
    return result


def collapsed_ids(project: Project, collapsed: set[SectionPath]) -> set[str]:
    """折りたたんだセクションの id(存在しないパスは無視する)。元に戻す・やり直しで状態を引き継ぐのに使う。"""
    return {section.id for path, section in walk_sections(project.sections) if path in collapsed}


def collapsed_paths(project: Project, ids: set[str]) -> set[SectionPath]:
    """id のセクションのパス(いまのプロジェクトにないものは落とす)。"""
    return {path for path, section in walk_sections(project.sections) if section.id in ids}


def remap_collapsed(
    collapsed: set[SectionPath], parent: SectionPath, index: int, delta: int
) -> set[SectionPath]:
    """セクションの挿入(delta=1)・削除(delta=-1)で番号がずれたぶん、折りたたみのパスを付け替える。
    削除のときは、そのセクションと子孫のパスを消す。"""
    result: set[SectionPath] = set()
    depth = len(parent)
    for path in collapsed:
        if len(path) <= depth or path[:depth] != parent:
            result.add(path)
            continue
        number = path[depth]
        if delta < 0 and number == index:
            continue
        if number >= index:
            number += delta if delta > 0 or number > index else 0
        result.add((*parent, number, *path[depth + 1 :]))
    return result


def shift_task(task: Task, days: int, shown_start: datetime | None = None) -> bool:
    """開始予定と、入っていれば完了予定を同じ日数ずらす(締切は動かさない)。範囲外なら何も書き換えない。

    押し出されているタスクは、見えている開始(shown_start)を基準にずらす。完了予定は押し出し分も含める。
    """
    if task.planned_start is None:
        return False
    shown = task.planned_start if shown_start is None else max(shown_start, task.planned_start)
    try:
        delta = timedelta(days=days)
        pushed = shown - task.planned_start
        start = shown + delta
        end = None if task.planned_end is None else task.planned_end + pushed + delta
    except OverflowError:
        return False
    for moment in (start, end):
        if moment is not None and not MIN_YEAR <= moment.year <= MAX_YEAR:
            return False
    task.planned_start, task.planned_end = start, end
    return True


def min_shift_days(
    task: Task,
    base_date: date,
    shown_start: datetime | None = None,
    floor: datetime | None = None,
) -> int:
    """左へずらせる限度(0 以下の日数)。見えている開始は、基準日と先行の完了の日より前へは動かさない。"""
    shown = task.planned_start if shown_start is None else shown_start
    if shown is None:
        return 0
    limit = base_date if floor is None else max(base_date, floor.date())
    start = shown.date()
    return (min(limit, start) - start).days


def as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_section(value: object) -> SectionPath | None:
    """画面から届くセクションの指定(キーの文字列 `top`・`0`・`0.1`)。不正は None。"""
    return parse_section_key(value) if isinstance(value, str) else None


def parse_position(value: object) -> Position | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    section, raw_index = value
    index = as_int(raw_index)
    path = parse_section(section)
    if index is None or path is None:
        return None
    return path, index


def parse_move(args: object) -> tuple[Position, Position, bool] | None:
    if not isinstance(args, dict):
        return None
    src = parse_position(args.get("src"))
    dst = parse_position(args.get("dst"))
    copy = args.get("copy")
    if src is None or dst is None or not isinstance(copy, bool):
        return None
    return src, dst, copy


def parse_shift(args: object) -> tuple[Position, int] | None:
    if not isinstance(args, dict):
        return None
    position = parse_position([args.get("si"), args.get("ti")])
    days = as_int(args.get("days"))
    if position is None or days is None or abs(days) > MAX_SHIFT_DAYS:
        return None
    return position, days


def parse_section_move(args: object) -> tuple[SectionPath, SectionPath] | None:
    """セクションのドロップ。両方がセクションのパスで、同じ親の兄弟のときだけ通す。"""
    if not isinstance(args, dict):
        return None
    src = parse_section(args.get("src"))
    dst = parse_section(args.get("dst"))
    if not src or not dst or src[:-1] != dst[:-1]:
        return None
    return src, dst
