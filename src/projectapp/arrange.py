"""タスクの移動・コピー・日程のずらし(純粋関数)と、画面から届く値の検証。"""

import re
from dataclasses import replace
from datetime import date, datetime, timedelta


from projectapp.models import MAX_SECTION_DEPTH, MAX_YEAR, MIN_YEAR, Project, Section, SectionPath, Task, new_id

Position = tuple[SectionPath, int]  # (セクションのパス。root は (), 番号)
COPY_SUFFIX = "(コピー)"
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
        original,
        name=f"{original.name}{COPY_SUFFIX}",
        id=new_id(),
        predecessors=[],
        actuals=[],
        assignees=[replace(a) for a in original.assignees],
        urls=[replace(u, values=dict(u.values)) for u in original.urls],
    )
    target = tasks_at(project, dst[0])
    target.insert(min(dst[1], len(target)), copy)
    return copy


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
