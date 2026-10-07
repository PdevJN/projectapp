"""矢印の連結の計算(行の並び・縦位置・折れ線)。NiceGUI には依存しない純粋関数。"""

from dataclasses import dataclass
from typing import Literal

from projectapp.filtering import TaskFilter, matches, visible_task_indexes
from projectapp.models import Project

STUB_PX = 6  # 先行の棒の右端から出る長さ。後続の棒の左端へ入る手前も同じ長さ
MIN_GAP_PX = 2 * STUB_PX  # 後続の左端がこれ未満のときは、行の間を通る経路にする


@dataclass(frozen=True)
class RowSlot:
    """描く行 1 つ。折りたたみで隠れる行は、作るが shown=False(高さを持たない)。"""

    kind: Literal["task", "section", "top-add"]
    si: int | None
    ti: int | None
    task_id: str | None
    shown: bool
    height: int


def row_slots(
    project: Project,
    task_filter: TaskFilter,
    collapsed: set[int],
    read_only: bool,
    row_height: int,
    add_height: int,
) -> list[RowSlot]:
    """gantt.render が描く行の並び。描画と矢印の計算の、両方がこの並びを使う。"""
    slots: list[RowSlot] = []
    for ti, task in enumerate(project.tasks):
        if matches(task, task_filter):
            slots.append(RowSlot("task", None, ti, task.id, True, row_height))
    if not read_only:
        slots.append(RowSlot("top-add", None, None, None, True, add_height))
    for si, section in enumerate(project.sections):
        is_collapsed = si in collapsed and not read_only
        shown = visible_task_indexes(section, task_filter, is_collapsed)
        if task_filter.active and not shown:
            continue
        slots.append(RowSlot("section", si, None, None, True, row_height))
        visible = set(shown)
        for ti, task in enumerate(section.tasks):
            if task_filter.active and ti not in visible:
                continue
            slots.append(RowSlot("task", si, ti, task.id, ti in visible, row_height))
    return slots


def row_centers(slots: list[RowSlot], top: float) -> dict[str, float]:
    """表示中のタスクの id から、行の中央の縦位置。top は、行の並びの上端(見出しの高さ)。"""
    centers: dict[str, float] = {}
    y = top
    for slot in slots:
        if not slot.shown:
            continue
        if slot.task_id is not None:
            centers[slot.task_id] = y + slot.height / 2
        y += slot.height
    return centers


def total_height(slots: list[RowSlot], top: float) -> float:
    return top + sum(slot.height for slot in slots if slot.shown)


@dataclass(frozen=True)
class Bar:
    """棒の左端と右端。名前の欄の右端(境界)からの距離(px)。"""

    left: float
    right: float


def link_points(
    pred: Bar, pred_y: float, succ: Bar, succ_y: float, row_height: int
) -> list[tuple[float, float]]:
    """先行の棒の右端から、後続の棒の左端までの折れ線(直角)。"""
    out = (pred.right, pred_y)
    if succ.left - pred.right >= MIN_GAP_PX:
        elbow = pred.right + STUB_PX
        return [out, (elbow, pred_y), (elbow, succ_y), (succ.left, succ_y)]
    between = pred_y + row_height / 2 if succ_y > pred_y else pred_y - row_height / 2
    right, left = pred.right + STUB_PX, succ.left - STUB_PX
    return [out, (right, pred_y), (right, between), (left, between), (left, succ_y), (succ.left, succ_y)]


def path_data(points: list[tuple[float, float]]) -> str:
    """SVG の path の d 属性。"""
    (x0, y0), *rest = points
    return f"M{x0:g},{y0:g} " + " ".join(f"L{x:g},{y:g}" for x, y in rest)
