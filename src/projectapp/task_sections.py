"""タスクのダイアログの節(基本・担当とパラメータ・実績と進捗・関連)の決まりごと。NiceGUI に依存しない。"""

from projectapp.models import DEFAULT_COLOR, Priority, Task

FOLDABLE = ("assignees", "actuals", "related")  # 折りたためる節。基本は常に開く
TITLES = {"basic": "基本", "assignees": "担当・パラメータ", "actuals": "実績・進捗", "related": "関連"}
MAX_SUMMARY_PEOPLE = 3
ERROR_PREFIXES = {
    "actuals": ("実績", "区間", "進捗度"),
    "assignees": ("担当",),
    "related": ("先行", "色は", "URL", "ID", "テンプレート"),
}


def has_values(section: str, task: Task) -> bool:
    """節に、既定でない値が入っているか(編集で開く節を決める)。"""
    if section == "assignees":
        return bool(task.assignees or task.weekly_crew or task.parameters)
    if section == "actuals":
        return bool(task.actuals or task.progress is not None)
    if section == "related":
        return bool(
            task.predecessors or task.urls or task.priority is not Priority.MEDIUM or task.color != DEFAULT_COLOR
        )
    return False


def initial_open(task: Task | None, saved: list[str] | None) -> list[str]:
    """開いて始める節。保存した開閉を使い、なければ新規は閉じ、編集は値のある節を開く。編集で値のある節は必ず開く。"""
    valued = set() if task is None else {key for key in FOLDABLE if has_values(key, task)}
    base = set(saved) if saved is not None else valued
    return [key for key in FOLDABLE if key in base | valued]


def assignees_summary(crew: list[tuple[str, float]], parameters: int) -> str:
    parts = [f"{name} {allocation * 100:g}%" for name, allocation in crew[:MAX_SUMMARY_PEOPLE]]
    if len(crew) > MAX_SUMMARY_PEOPLE:
        parts.append(f"ほか {len(crew) - MAX_SUMMARY_PEOPLE} 人")
    if parameters:
        parts.append(f"パラメータ {parameters}")
    return "・".join(parts)


def actuals_summary(count: int, interval_mode: bool, progress: int | None) -> str:
    parts = []
    if count:
        parts.append(f"{count}区間" if interval_mode else "実績あり")
    if progress is not None:
        parts.append(f"進捗 {progress}%")
    return "・".join(parts)


def related_summary(predecessors: int, links: int, priority: Priority, has_color: bool) -> str:
    parts = []
    if predecessors:
        parts.append(f"先行 {predecessors}")
    if links:
        parts.append(f"リンク {links}")
    if priority is not Priority.MEDIUM:
        parts.append(f"優先度 {priority.value}")
    if has_color:
        parts.append("色")
    return "・".join(parts)


def section_of_error(message: str) -> str | None:
    """検証エラーの文言から、エラーの項目がある節を決める(基本の項目と分からないものは None)。"""
    for key, prefixes in ERROR_PREFIXES.items():
        if message.startswith(prefixes):
            return key
    return None
