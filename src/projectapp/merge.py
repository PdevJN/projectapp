"""プロジェクトの 3 者マージ(共通祖先・自分・相手)。NiceGUI にも git にも依存しない。

タスク・メンバー・セクション・カテゴリは`id`で、パラメータ・URL テンプレートは名前で突き合わせる。
項目ごとに、片側だけが変えた値を採り、両側が違う値に変えた項目だけを衝突にする。
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from projectapp.events import sort_events
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
    Team,
    UrlTemplate,
    WorkDay,
    union_assignees,
)
from projectapp.storage import dumps_project, parse_project
from projectapp.teams import normalize
from projectapp.workdays import sort_work_days

OURS = "ours"
THEIRS = "theirs"
DELETED = "(削除)"  # 削除と変更の衝突の項目名
Choices = dict[tuple[str, str, str], str]
Record = dict[str, Any]
_MISSING = object()


@dataclass(frozen=True, eq=False)
class Conflict:
    kind: str  # task・section・member・category・event・work_day・parameter・url_template・setting
    key: str  # id(パラメータ・テンプレートは名前)
    label: str  # 画面に出す名前
    field: str  # 画面に出す項目名。削除と変更の衝突は`DELETED`
    ours: Any  # 自分の値。自分が削除したときは None
    theirs: Any  # 相手の値。相手が削除したときは None

    @property
    def id(self) -> tuple[str, str, str]:
        return (self.kind, self.key, self.field)


@dataclass
class MergeResult:
    project: Project
    conflicts: list[Conflict]  # 選択がなかった衝突も含む(結果は「自分」になっている)
    notes: list[str]  # 利用者に知らせる整理(外した担当者など)


def format_value(value: object) -> str:
    """衝突ダイアログに出す値の文言。"""
    if value is None:
        return DELETED
    if isinstance(value, bool):
        return "はい" if value else "いいえ"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(v) for v in value) or "(なし)"
    if isinstance(value, dict):
        return ", ".join(f"{k}={format_value(v)}" for k, v in value.items()) or "(なし)"
    if value == "":
        return "(空)"
    if isinstance(value, str) and value.startswith("data:image/"):
        return f"画像({len(value) // 1024 + 1}KB)"  # アイコンの base64 全文は出さない
    return str(value)


def _order(base: list[str], ours: list[str], theirs: list[str]) -> list[str]:
    """3 者の並びを合わせる。自分の並びが土台。相手だけが並べ替えたときは相手の並びが土台。
    土台にないもの(相手の追加・移動)は、相手の並びでの直前の兄弟(結果にすでにあるもの)のあとに入れる。"""
    members = set(ours) | set(theirs)
    common = set(base) & set(ours) & set(theirs)

    def restrict(seq: list[str]) -> list[str]:
        return [x for x in seq if x in common]

    primary, secondary = ours, theirs
    if restrict(ours) == restrict(base) and restrict(theirs) != restrict(base):
        primary, secondary = theirs, ours
    result = [x for x in primary if x in members]
    for index, item in enumerate(secondary):
        if item in result:
            continue
        position = 0
        for earlier in reversed(secondary[:index]):
            if earlier in result:
                position = result.index(earlier) + 1
                break
        result.insert(position, item)
    return result


class _Merger:
    def __init__(self, choices: Choices | None) -> None:
        self.choices = choices or {}
        self.conflicts: list[Conflict] = []
        self.titles: dict[str, str] = {}  # 記録の鍵 → 画面に出す名前(名前の項目がない記録用)

    def pick(self, conflict: Conflict) -> str:
        self.conflicts.append(conflict)
        return self.choices.get(conflict.id, OURS)

    def record(
        self,
        kind: str,
        key: str,
        labels: dict[str, str],
        base: Record | None,
        ours: Record | None,
        theirs: Record | None,
        display: Callable[[str, Any], Any] = lambda name, value: value,
    ) -> Record | None:
        """1 件の記録を 3 者マージする。`None`は存在しないこと。結果が`None`なら削除。"""
        if ours is None and theirs is None:
            return None
        shown = ours or theirs or base or {}
        label = str(shown.get("name") or shown.get("text") or self.titles.get(key) or key)
        if base is None:
            if ours is None:
                return theirs
            if theirs is None:
                return ours
            base = {}  # 両側が追加した: 値の違う項目だけが衝突になる
        elif ours is None or theirs is None:
            kept = theirs if ours is None else ours
            if kept == base:
                return None  # 片側が削除し、もう片側は変えていない
            conflict = Conflict(kind, key, label, DELETED, ours, theirs)
            return ours if self.pick(conflict) == OURS else theirs
        assert ours is not None and theirs is not None
        merged: Record = {}
        for name in ours:
            b, o, t = base.get(name, _MISSING), ours[name], theirs[name]
            if o == t:
                merged[name] = o
            elif b == o:
                merged[name] = t
            elif b == t:
                merged[name] = o
            else:
                conflict = Conflict(kind, key, label, labels.get(name, name), display(name, o), display(name, t))
                merged[name] = o if self.pick(conflict) == OURS else t
        return merged

    def collection(
        self,
        kind: str,
        labels: dict[str, str],
        base: dict[str, Record],
        ours: dict[str, Record],
        theirs: dict[str, Record],
        display: Callable[[str, Any], Any] = lambda name, value: value,
    ) -> dict[str, Record]:
        """キーごとに記録をマージする。並びは`_order`。"""
        result: dict[str, Record] = {}
        for key in _order(list(base), list(ours), list(theirs)):
            merged = self.record(kind, key, labels, base.get(key), ours.get(key), theirs.get(key), display)
            if merged is not None:
                result[key] = merged
        return result


MEMBER_LABELS = {"name": "名前", "ratio": "基本比率", "levels": "段階の選択", "icon": "アイコン", "ratio_unclamped": "丸め対象外", "teams": "所属チーム"}
TEAM_LABELS = {"name": "名前"}
CATEGORY_LABELS = {"name": "名前", "kind": "種別", "expiry_date": "有効期限", "color": "色", "prj_code": "PRJコード"}
PARAMETER_LABELS = {"levels": "段階"}
TEMPLATE_LABELS = {"pattern": "URLの型"}
EVENT_LABELS = {"start": "開始日", "end": "終了日", "text": "文字列", "color": "色", "closed": "休み"}
WORK_DAY_LABELS = {"window": "時間帯", "note": "メモ"}
SETTING_LABELS = {"base_date": "基準日", "daily_hours": "稼働可能時間", "work_start": "始業時刻", "actual_mode": "実績の記録方式", "reference_mode": "参照の方式", "plantuml_overload_notice": "PlantUML の通知", "ratio_limit_upper": "相対比率の上限", "ratio_limit_lower": "相対比率の下限"}


def _members(project: Project) -> dict[str, Record]:
    return {
        m.id: {
            "name": m.name,
            "ratio": m.ratio,
            "levels": dict(m.levels),
            "icon": m.icon,
            "ratio_unclamped": m.ratio_unclamped,
            "teams": [(s.team_id, s.percent) for s in m.teams],
        }
        for m in project.members
    }


def _teams(project: Project) -> dict[str, Record]:
    return {t.id: {"name": t.name} for t in project.teams}


def _categories(project: Project) -> dict[str, Record]:
    return {
        c.id: {"name": c.name, "kind": c.kind, "expiry_date": c.expiry_date, "color": c.color, "prj_code": c.prj_code}
        for c in project.categories
    }


def _show_work_day(name: str, value: Any) -> str:
    if name == "note":
        return value or "(なし)"
    start, end = value
    return "休み" if start is None else f"{start:%H:%M}〜{end:%H:%M}"


def _member_work_days(project: Project) -> dict[str, Record]:
    # 開始と終了は組で意味を持つ(両方 None=休み)ので、1 項目として比べる
    return {
        f"{m.id}:{w.day.isoformat()}": {"window": (w.start, w.end), "note": w.note}
        for m in project.members
        for w in m.work_days
    }


def _events(project: Project) -> dict[str, Record]:
    return {e.id: {"start": e.start, "end": e.end, "text": e.text, "color": e.color, "closed": e.closed} for e in project.events}


def _parameters(project: Project) -> dict[str, Record]:
    return {p.name: {"levels": [(lv.name, lv.value) for lv in p.levels]} for p in project.parameters}


def _templates(project: Project) -> dict[str, Record]:
    return {t.name: {"pattern": t.pattern} for t in project.url_templates}


def _settings(project: Project) -> Record:
    return {name: getattr(project, name) for name in SETTING_LABELS}


TASK_LABELS = {
    "name": "名前", "planned_start": "開始予定", "effort_hours": "工数", "priority": "優先度", "status": "状態",
    "color": "色", "assignees": "担当", "predecessors": "先行", "deadline": "締切", "planned_end": "完了予定",
    "planned_end_manual": "完了予定を手で指定", "actuals": "実績", "progress": "進捗度", "category_id": "カテゴリ", "kind": "種別",
    "urls": "リンク", "children": "子", "parameters": "パラメータ", "weekly_crew": "週ごとの担当", "parent": "所属",
    "ref_project": "参照先", "ref_snapshot": "スナップショット",
}
SECTION_LABELS = {"name": "名前", "parent": "所属"}


@dataclass
class _Flat:
    """プロジェクトのタスクとセクションを、id ごとの記録と、入れ物(ルート = None)ごとの並びにほどいたもの。"""

    tasks: dict[str, Record]
    sections: dict[str, Record]
    task_order: dict[str | None, list[str]]
    section_order: dict[str | None, list[str]]


def _flatten(project: Project) -> _Flat:
    ids = {}
    for member in project.members:
        ids.setdefault(member.name, member.id)  # 同名は最初の 1 件(保存・読込と同じ)
    flat = _Flat({}, {}, {}, {})

    def visit(container: str | None, tasks: list[Task], sections: list[Section]) -> None:
        flat.task_order[container] = [t.id for t in tasks]
        flat.section_order[container] = [s.id for s in sections]
        for t in tasks:
            record: Record = {
                f.name: getattr(t, f.name) for f in fields(Task) if f.name not in ("id", "assignees", "weekly_crew")
            }
            # 週ごとのタスクの担当は週の表が正(和集合は持たない)なので、「担当」は空にして衝突させない
            record["assignees"] = [] if t.weekly_crew else [(ids.get(a.name, a.name), a.allocation) for a in t.assignees]
            record["weekly_crew"] = [[(ids.get(a.name, a.name), a.allocation) for a in week] for week in t.weekly_crew]
            record["parent"] = container
            flat.tasks[t.id] = record
        for s in sections:
            flat.sections[s.id] = {"name": s.name, "parent": container}
            visit(s.id, s.tasks, s.sections)

    visit(None, project.tasks, project.sections)
    return flat


def _member_names(*projects: Project) -> dict[str, str]:
    names: dict[str, str] = {}
    for project in projects:  # 先のものを優先する
        for member in project.members:
            names.setdefault(member.id, member.name)
    return names


def fill_empty_weeks(weeks: list[list[Assignee]]) -> tuple[list[list[Assignee]], list[int]]:
    """担当者のいなくなった週を、前の週(なければ次の週)の担当にする。埋めた週の番号(1 始まり)も返す。
    すべての週が空なら空のリスト(週ごとに分けない)。"""
    if not any(weeks):
        return [], []
    result = [list(week) for week in weeks]
    filled: list[int] = []
    for index, week in enumerate(result):
        if week:
            continue
        source = next((result[i] for i in range(index - 1, -1, -1) if result[i]), None) or next(w for w in result if w)
        result[index] = [Assignee(a.name, a.allocation) for a in source]
        filled.append(index + 1)
    return result, filled


def merge_projects(base: Project, ours: Project, theirs: Project, choices: Choices | None = None) -> MergeResult:
    """共通祖先`base`・自分`ours`・相手`theirs`を統合する。選択のない衝突は「自分」になり、`conflicts`に残る。"""
    merger = _Merger(choices)
    notes: list[str] = []
    settings = merger.record(
        "setting", "設定", SETTING_LABELS, _settings(base), _settings(ours), _settings(theirs)
    )
    assert settings is not None
    teams = merger.collection("team", TEAM_LABELS, _teams(base), _teams(ours), _teams(theirs))
    team_names = {t.id: t.name for source in (base, theirs, ours) for t in source.teams}  # 自分の名前を優先

    def show_member(name: str, value: Any) -> Any:
        if name == "teams":
            return [f"{team_names.get(team_id, team_id)} {percent}%" for team_id, percent in value]
        return value

    members = merger.collection("member", MEMBER_LABELS, _members(base), _members(ours), _members(theirs), show_member)
    categories = merger.collection("category", CATEGORY_LABELS, _categories(base), _categories(ours), _categories(theirs))
    events = merger.collection("event", EVENT_LABELS, _events(base), _events(ours), _events(theirs))
    for source in (theirs, ours):  # 自分の名前を優先する
        for member in source.members:
            for row in member.work_days:
                merger.titles[f"{member.id}:{row.day.isoformat()}"] = f"{member.name}: {row.day.isoformat()}"
    member_days = merger.collection(
        "work_day",
        WORK_DAY_LABELS,
        _member_work_days(base),
        _member_work_days(ours),
        _member_work_days(theirs),
        _show_work_day,
    )
    parameters = merger.collection("parameter", PARAMETER_LABELS, _parameters(base), _parameters(ours), _parameters(theirs))
    templates = merger.collection("url_template", TEMPLATE_LABELS, _templates(base), _templates(ours), _templates(theirs))
    team_seen: set[str] = set()  # 同名で id の違うチームも、読み直すと拒否されるので、名前を変えて両方残す
    team_taken = {record["name"] for record in teams.values()}
    for record in teams.values():
        name = record["name"]
        if name in team_seen:
            number = 2
            while f"{name} ({number})" in team_taken | team_seen:
                number += 1
            renamed = f"{name} ({number})"
            notes.append(f"同名のチームがいたため、名前を変えました: {name} → {renamed}")
            record["name"] = name = renamed
        team_seen.add(name)
    seen: set[str] = set()  # 同名で id の違うメンバーは、読み直すと片方が捨てられるので、名前を変えて両方残す
    taken = {record["name"] for record in members.values()}
    for record in members.values():
        name = record["name"]
        if name in seen:
            number = 2
            while f"{name} ({number})" in taken | seen:
                number += 1
            renamed = f"{name} ({number})"
            notes.append(f"同名のメンバーがいたため、名前を変えました: {name} → {renamed}")
            record["name"] = name = renamed
        seen.add(name)
    flats = [_flatten(p) for p in (base, ours, theirs)]
    shown = _member_names(ours, theirs, base)

    def display(name: str, value: Any) -> Any:
        if name == "assignees":
            return [f"{shown.get(i, i)} {a:.0%}" for i, a in value]
        if name == "weekly_crew":
            return [
                f"第{n}週: " + "、".join(f"{shown.get(i, i)} {a:.0%}" for i, a in week)
                for n, week in enumerate(value, start=1)
            ]
        return value

    sections = merger.collection("section", SECTION_LABELS, flats[0].sections, flats[1].sections, flats[2].sections)
    tasks = merger.collection("task", TASK_LABELS, flats[0].tasks, flats[1].tasks, flats[2].tasks, display=display)
    names = {key: r["name"] for key, r in members.items()}

    for key, record in sections.items():  # 親が消えたセクションは、ルートへ移す
        if record["parent"] is not None and record["parent"] not in sections:
            notes.append(f"削除されたセクションにあった「{record['name']}」をルートへ移しました")
            record["parent"] = None
    for key, record in tasks.items():
        if record["parent"] is not None and record["parent"] not in sections:
            notes.append(f"削除されたセクションにあった「{record['name']}」をルートへ移しました")
            record["parent"] = None

    def make_task(key: str, record: Record) -> Task:
        assignees = []
        for member_id, allocation in record["assignees"]:
            if member_id in names:
                assignees.append(Assignee(names[member_id], allocation))
            else:
                notes.append(f"担当者を外しました: 「{record['name']}」の{shown.get(member_id, member_id)}")
        weeks: list[list[Assignee]] = []
        for number, week in enumerate(record["weekly_crew"], start=1):
            crew = []
            for member_id, allocation in week:
                if member_id in names:
                    crew.append(Assignee(names[member_id], allocation))
                else:
                    notes.append(f"担当者を外しました: 「{record['name']}」の第{number}週の{shown.get(member_id, member_id)}")
            weeks.append(crew)
        weeks, filled = fill_empty_weeks(weeks)
        for number in filled:
            notes.append(f"担当者がいなくなった週を、隣の週と同じにしました: 「{record['name']}」の第{number}週")
        if record["weekly_crew"] and not weeks:
            notes.append(f"週ごとの担当をすべて外しました: 「{record['name']}」")
        data = {
            k: v
            for k, v in record.items()
            if k not in ("assignees", "weekly_crew", "parent", "predecessors", "category_id", "children")
        }
        category = record["category_id"]
        if category is not None and category not in categories:
            notes.append(f"カテゴリを外しました: 「{record['name']}」")
            category = None
        predecessors = [p for p in record["predecessors"] if p in tasks]
        children = [c for c in record["children"] if c in tasks]
        if data["kind"] is TaskKind.SUMMARY and not children:
            data["kind"] = TaskKind.NORMAL  # 子がいなくなったまとめは、通常タスクに戻す
        return Task(
            id=key,
            assignees=union_assignees(weeks) if weeks else assignees,
            weekly_crew=weeks,
            predecessors=predecessors,
            category_id=category,
            children=children,
            **data,
        )

    task_objects = {key: make_task(key, record) for key, record in tasks.items()}

    task_orders = [f.task_order for f in flats]  # base, ours, theirs の順
    section_orders = [f.section_order for f in flats]

    def children(orders: list[dict[str | None, list[str]]], records: dict[str, Record], container: str | None) -> list[str]:
        wanted = [k for k, r in records.items() if r["parent"] == container]
        base_o, ours_o, theirs_o = (o.get(container, []) for o in orders)
        ordered = [k for k in _order(base_o, ours_o, theirs_o) if k in wanted]
        return ordered + [k for k in wanted if k not in ordered]

    def build(container: str | None) -> tuple[list[Task], list[Section]]:
        built = []
        for sid in children(section_orders, sections, container):
            section = Section(sections[sid]["name"], id=sid)
            section.tasks, section.sections = build(sid)
            built.append(section)
        return [task_objects[k] for k in children(task_orders, tasks, container)], built

    root_tasks, root_sections = build(None)

    team_ids = set(teams)

    def settle_teams(record: Record) -> list[Membership]:
        rows = [Membership(team_id, percent) for team_id, percent in record["teams"]]
        kept = [s for s in rows if s.team_id in team_ids]
        if len(kept) != len(rows):
            notes.append(f"削除されたチームへの所属を外しました: {record['name']}")
            return normalize(kept)
        return rows

    built_members = [
        Member(
            r["name"],
            r["ratio"],
            dict(r["levels"]),
            id=key,
            icon=r["icon"],
            ratio_unclamped=r["ratio_unclamped"],
            teams=settle_teams(r),
        )
        for key, r in members.items()
    ]
    by_id = {m.id: m for m in built_members}
    for key, r in member_days.items():
        member_id, day = key.split(":", 1)
        if member_id in by_id:  # 削除されたメンバーの上書きは捨てる
            start, end = r["window"]
            by_id[member_id].work_days.append(WorkDay(date.fromisoformat(day), start, end, r["note"]))
    for member in built_members:
        member.work_days = sort_work_days(member.work_days)

    project = Project(
        name=ours.name,
        tasks=root_tasks,
        sections=root_sections,
        base_date=settings["base_date"],
        daily_hours=settings["daily_hours"],
        work_start=settings["work_start"],
        actual_mode=settings["actual_mode"],
        reference_mode=settings["reference_mode"],
        plantuml_overload_notice=settings["plantuml_overload_notice"],
        ratio_limit_upper=settings["ratio_limit_upper"],
        ratio_limit_lower=settings["ratio_limit_lower"],
        members=built_members,
        teams=[Team(r["name"], id=key) for key, r in teams.items()],
        categories=[
            Category(r["name"], r["kind"], r["expiry_date"], r["color"], r["prj_code"], id=key)
            for key, r in categories.items()
        ],
        events=sort_events([Event(r["start"], r["end"], r["text"], r["color"], id=key, closed=r["closed"]) for key, r in events.items()]),
        parameters=[Parameter(key, [Level(n, v) for n, v in r["levels"]]) for key, r in parameters.items()],
        url_templates=[UrlTemplate(key, r["pattern"]) for key, r in templates.items()],
    )
    return MergeResult(copy.deepcopy(project), merger.conflicts, notes)


@dataclass(frozen=True)
class FileMerge:
    text: str
    conflicts: list[Conflict]
    notes: list[str]


def merge_files(name: str, base: str, ours: str, theirs: str, choices: Choices | None = None) -> FileMerge:
    """プロジェクトファイル 1 つの、3 者の本文を統合する。読めない・統合結果が検証を通らないときは`ValueError`。"""
    stem = name.removesuffix(".json")
    try:
        base_p, ours_p, theirs_p = (parse_project(text, stem) for text in (base, ours, theirs))
    except KeyError as exc:  # 読込は、キーの欠けを KeyError で知らせる
        raise ValueError(f"キーがありません: {exc}") from exc
    result = merge_projects(base_p, ours_p, theirs_p, choices)
    text = dumps_project(result.project)
    parse_project(text, stem)  # 書いたものを読み直せること
    return FileMerge(text, result.conflicts, result.notes)
