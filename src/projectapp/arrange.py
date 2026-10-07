"""タスクの移動・コピー・日程のずらし(純粋関数)と、画面から届く値の検証。"""

from dataclasses import replace
from datetime import date, timedelta

from projectapp.models import MAX_YEAR, MIN_YEAR, Project, Task, new_id

Position = tuple[int | None, int]  # (セクション番号。Noneはセクションなし, 番号)
COPY_SUFFIX = "(コピー)"
MAX_SHIFT_DAYS = 3650


def tasks_at(project: Project, section: int | None) -> list[Task]:
    return project.tasks if section is None else project.sections[section].tasks


def valid_section(project: Project, section: int | None) -> bool:
    return section is None or 0 <= section < len(project.sections)


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
    index = min(dst[1], len(target))
    if source is target:
        if index in (src[1], src[1] + 1):
            return False
        if index > src[1]:
            index -= 1
    target.insert(index, source.pop(src[1]))
    return True


def copy_task(project: Project, src: Position, dst: Position) -> Task:
    original = tasks_at(project, src[0])[src[1]]
    copy = replace(
        original, name=f"{original.name}{COPY_SUFFIX}", id=new_id(), predecessors=[], actuals=[]
    )
    target = tasks_at(project, dst[0])
    target.insert(min(dst[1], len(target)), copy)
    return copy


def shift_task(task: Task, days: int) -> bool:
    """開始予定と、入っていれば完了予定を同じ日数ずらす(締切は動かさない)。範囲外なら何も書き換えない。"""
    if task.planned_start is None:
        return False
    try:
        delta = timedelta(days=days)
        start = task.planned_start + delta
        end = None if task.planned_end is None else task.planned_end + delta
    except OverflowError:
        return False
    for moment in (start, end):
        if moment is not None and not MIN_YEAR <= moment.year <= MAX_YEAR:
            return False
    task.planned_start, task.planned_end = start, end
    return True


def min_shift_days(task: Task, base_date: date) -> int:
    """左へずらせる限度(0 以下の日数)。開始予定は基準日より前へは動かさない。"""
    if task.planned_start is None:
        return 0
    start = task.planned_start.date()
    return (min(base_date, start) - start).days


def as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_position(value: object) -> Position | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    section, raw_index = value
    index = as_int(raw_index)
    if index is None:
        return None
    if section is None:
        return None, index
    number = as_int(section)
    return None if number is None else (number, index)


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
