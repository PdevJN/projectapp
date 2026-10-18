# PlantUML 取り込み Implementation Plan

> **状態**: 実装済み — 要望 37 — マージ PR #21(1a081c2。2026-10-16)。設計書は [`2026-10-16-plantuml-import-design.md`](../specs/2026-10-16-plantuml-import-design.md)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。
> **後の変更**: 日付がまったくないガントは取り込み日を開始にする(PR #33)、`requires`・`is N% complete`・`<style>` を読む(PR #34)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 他所で作られた PlantUML のガント(`@startgantt`〜`@endgantt`)から、`ファイル`メニューで新規プロジェクトを作れるようにする。

**Architecture:** 変換は、NiceGUI に依存しない純粋関数 `puml_import.py`(`plantuml.py` の対)。行ごとの正規表現で読み(`_Scanner`)、PlantUML のルールで日付に解決し(`_Resolver`)、`Project` を組み立てる(`_Builder`)。最後に `dumps_project` → `parse_project` で保存・読込と同じ検証を通す。入口は `ファイル`メニューの`PlantUML を取り込む`と、読み込み用のファイル選択(`exporter.ask_open_path`)。取り込んだプロジェクトは、保存前の新規として開き、未保存の扱いにする。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、ty。描画の確認に、`java` と `/usr/local/lib/plantuml.jar`(1.2021.15)。

**Spec:** `docs/superpowers/specs/2026-10-16-plantuml-import-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。コードの識別子は英語。
- コード規約(`.claude/RULE.md`): すべての関数に型引数と戻り値の型ヒントを付ける。コメントの説明は多くても 3 行以内。型の検証は `ty`。
- 取り込み先は、保存前の新規プロジェクト。ファイルは、保存するまで作らない。既存プロジェクトへの追加はしない。
- 入口は `ファイル`メニューの`PlantUML を取り込む`(マーカー `file-import-plantuml`、アイコン `upload_file`、`開く`の次)だけ。ショートカットは足さない。ネイティブウィンドウのみ。
- 日付は、取り込み時に PlantUML のルールで解決し、開始予定は開始日の始業時刻(`Project.work_start`)、完了予定・締切は終了日(締切日)の終業時刻(始業時刻 + `Project.daily_hours` 時間)にする。完了予定は工数が空なので直接入力の値(`planned_end_manual` は偽のまま)。
- 稼働日は、既定で土日が休み。`closed`・`open` は日付の計算にだけ使い、保存しない。日付の指定(`<日付> is closed`)は曜日の指定(`saturday are closed`)より優先し、同じ種類では後に書かれたものが勝つ。
- `lasts N days`・`lasts N weeks` は稼働日で数える(週は `5 × N` 日)。上限 3660 日。開始日が休みなら次の稼働日から数える。
- 進捗(`is N% completed`)からは状態だけを決める(0・未指定=`未着手`、1〜99=`実行中`、100=`終了`)。進捗度は保存しない。実績は作らない。
- 担当者(`{名前}`・`{名前:50%}`)は、名前ごとにメンバー(基本比率 100%)を 1 回だけ自動作成する。割り当て率は 1〜100%(範囲外は 100% にして数える)。
- タスク名・セクション名・メンバー名は `models.tidy_task_name` で整える(制御文字は空白、50 文字で切り詰め)。
- セクションは最大 3 階層(`models.MAX_SECTION_DEPTH`)。`-- 親 / 子 --` を `/` で分け、超える分は 3 階層目の名前に ` / ` でつなぐ。
- 色・`printscale`・コメントなど、仕様で読み飛ばすと決めた行は、読み飛ばし件数に数えない。解釈できない行だけ数える。
- 完了の確認は `uv run pytest -n auto` と `uv run ty check src`。コミットメッセージは日本語で、末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。ブランチは `feature/plantuml-import`。

## Review Focus

- 全曜日が休み・`lasts 99999 days` のような極端な指定: 止まらず、日程なしか読み飛ばしになる(Task 1)。
- 空のテキスト・囲みだけ・バイナリ・UTF-8 でないファイル: 通知して、何も変えない(Task 1・Task 3・Task 4)。
- 同名のタスク、同じ別名の再宣言、存在しない別名への参照: 落ちずに取り込み、参照先のない指定は日程なしになる(Task 1・Task 2)。
- 先行の循環(`A` は `B` の後、`B` は `A` の後): 止まらず、両方が日程なしになる(Task 2)。
- 取り込んだ直後に別のプロジェクトを開く・新規作成する: 未保存の確認が出る(Task 4)。
- 担当者名が空・全角・同じタスクで重複: 空は無視、重複は最初だけ(Task 3)。

---

### Task 1: 読み取りと日程の解決(絶対日付)・変換の土台

**Files:**
- Create: `src/projectapp/puml_import.py`
- Create: `test/test_puml_import.py`

**Interfaces:**
- Consumes: `models.Project`・`Section`・`Task`・`TaskKind`・`new_id`・`tidy_task_name`・`MAX_SECTION_DEPTH`・`MIN_YEAR`・`MAX_YEAR`、`storage.dumps_project`・`parse_project`。
- Produces:
  - `PlantUmlImportError(ValueError)`。
  - `PlantUmlImport`(`@dataclass(frozen=True)`): `project: Project`、`task_count: int`、`created_members: int`、`skipped_lines: int`、`unresolved: int`、`clamped_allocations: int`、`dropped_progress: int`。
  - `parse_plantuml(text: str, name: str) -> PlantUmlImport`(`name` は `title` がないときのプロジェクト名)。
  - 内部: `_Raw`・`_Scanner`・`_Calendar`・`_Resolver`・`_Builder`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_puml_import.py`:

```python
from datetime import date, datetime

import pytest

from projectapp.models import Status, Task, TaskKind
from projectapp.puml_import import PlantUmlImport, PlantUmlImportError, parse_plantuml


def parse(*lines: str, name: str = "取込") -> PlantUmlImport:
    return parse_plantuml("\n".join(["@startgantt", *lines, "@endgantt"]), name)


def task_named(result: PlantUmlImport, name: str) -> Task:
    return next(t for t in result.project.all_tasks() if t.name == name)


def span(result: PlantUmlImport, name: str) -> tuple[datetime | None, datetime | None]:
    task = task_named(result, name)
    return task.planned_start, task.planned_end


def at(day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute)


END = (15, 30)  # 終業時刻(9:00 + 6.5h)


def test_a_task_with_absolute_dates_becomes_a_planned_task() -> None:
    result = parse("[設計] starts 2026-10-13 and ends 2026-10-15")
    assert span(result, "設計") == (at(13), at(15, *END))
    task = task_named(result, "設計")
    assert (task.status, task.effort_hours, task.planned_end_manual) == (Status.NOT_STARTED, 0.0, False)
    assert (result.task_count, result.skipped_lines, result.unresolved) == (1, 0, 0)


def test_title_and_project_start_name_and_date_the_project() -> None:
    result = parse("title 取込元", "Project starts 2026-10-12", "[A] starts 2026-10-13")
    assert result.project.name == "取込元" and result.project.base_date == date(2026, 10, 12)


def test_the_given_name_is_used_without_a_title() -> None:
    assert parse("[A] starts 2026-10-13", name="ファイル名").project.name == "ファイル名"


def test_keywords_are_case_insensitive_and_slashed_dates_are_read() -> None:
    result = parse("PROJECT STARTS 2026/10/12", "[A] STARTS 2026/10/13 AND ENDS 2026/10/14")
    assert result.project.base_date == date(2026, 10, 12)
    assert span(result, "A") == (at(13), at(14, *END))


def test_lasts_counts_working_days_across_a_weekend() -> None:
    assert span(parse("[A] starts 2026-10-15 and lasts 3 days"), "A")[1] == at(19, *END)


def test_lasts_skips_closed_days() -> None:
    result = parse("2026-10-16 is closed", "[A] starts 2026-10-15 and lasts 2 days")
    assert span(result, "A")[1] == at(19, *END)


def test_a_date_marked_open_overrides_the_weekend() -> None:
    result = parse("2026-10-17 is open", "[A] starts 2026-10-16 and lasts 2 days")
    assert span(result, "A")[1] == at(17, *END)


def test_a_range_can_be_closed_and_reopened_later() -> None:
    result = parse("2026-10-19 to 2026-10-20 are closed", "[A] starts 2026-10-16 and lasts 2 days")
    assert span(result, "A")[1] == at(21, *END)
    reopened = parse(
        "2026-10-19 to 2026-10-20 are closed", "2026-10-19 is open", "[A] starts 2026-10-16 and lasts 2 days"
    )
    assert span(reopened, "A")[1] == at(19, *END)


def test_a_weekday_can_be_opened() -> None:
    result = parse("saturday are open", "[A] starts 2026-10-16 and lasts 2 days")
    assert span(result, "A")[1] == at(17, *END)


def test_lasts_in_weeks_is_five_working_days_per_week() -> None:
    assert span(parse("[A] starts 2026-10-12 and lasts 1 week"), "A")[1] == at(16, *END)


def test_a_task_without_a_period_lasts_one_working_day() -> None:
    assert span(parse("[A] starts 2026-10-13"), "A") == (at(13), at(13, *END))


def test_a_start_on_a_closed_day_ends_on_the_next_working_day() -> None:
    assert span(parse("[A] starts 2026-10-17"), "A") == (at(17), at(19, *END))


def test_an_end_before_the_start_is_pulled_to_the_start() -> None:
    assert span(parse("[A] starts 2026-10-15 and ends 2026-10-13"), "A") == (at(15), at(15, *END))


def test_a_task_without_a_start_begins_on_the_project_start() -> None:
    result = parse("Project starts 2026-10-13", "[A] lasts 1 day")
    assert span(result, "A") == (at(13), at(13, *END))


def test_without_a_project_start_the_first_date_seen_is_used() -> None:
    result = parse("[A] lasts 1 day", "[B] starts 2026-10-14")
    assert span(result, "A")[0] == at(14)


def test_a_task_with_no_date_anywhere_has_no_schedule() -> None:
    result = parse("[A]")
    assert span(result, "A") == (None, None) and result.unresolved == 1


def test_extreme_periods_do_not_hang() -> None:
    result = parse(
        "[A] lasts 99999 days",
        "monday are closed", "tuesday are closed", "wednesday are closed", "thursday are closed",
        "friday are closed", "saturday are closed", "sunday are closed",
        "[B] starts 2026-10-13 and lasts 2 days",
    )
    assert result.skipped_lines == 1  # lasts 99999 は読み飛ばす(A は宣言だけ残る)
    assert span(result, "A")[0] == at(13)  # 開始は最初に現れた日付
    assert span(result, "B")[0] == at(13)


def test_a_milestone_becomes_a_checkpoint_at_the_end_of_the_day() -> None:
    task = task_named(parse("[M] happens on 2026-10-23"), "M")
    assert task.kind is TaskKind.CHECKPOINT and task.deadline == at(23, *END)
    assert (task.planned_start, task.planned_end, task.status) == (None, None, Status.NOT_STARTED)


def test_sections_nest_up_to_three_levels() -> None:
    result = parse(
        "[R] starts 2026-10-13",
        "-- 開発 --", "[A] starts 2026-10-13",
        "-- 開発 / 設計 --", "[B] starts 2026-10-13",
        "-- 空 --",
        "-- P / Q / R / S --", "[C] starts 2026-10-13",
    )
    project = result.project
    assert [t.name for t in project.tasks] == ["R"]
    assert [s.name for s in project.sections] == ["開発", "空", "P"]
    dev = project.sections[0]
    assert [t.name for t in dev.tasks] == ["A"] and [s.name for s in dev.sections] == ["設計"]
    assert [t.name for t in dev.sections[0].tasks] == ["B"]
    deep = project.sections[2].sections[0].sections[0]
    assert deep.name == "R / S" and [t.name for t in deep.tasks] == ["C"]


def test_ignored_lines_are_not_counted_but_unknown_lines_are() -> None:
    result = parse(
        "' コメント", "", "printscale daily", "hide footbox",
        "2026-10-19 to 2026-10-30 are colored in lightpink",
        "[A] starts 2026-10-13", "[A] is colored in #4c8bf5",
        "saturday are closed",
    )
    assert result.skipped_lines == 0
    assert parse("[A] starts 2026-10-13", "foo bar baz").skipped_lines == 1


def test_an_invalid_date_skips_the_line_but_keeps_the_task() -> None:
    result = parse("[A] starts 2026-13-40")
    assert result.skipped_lines == 1 and result.unresolved == 1 and task_named(result, "A")


def test_task_names_are_tidied() -> None:
    result = parse("[a\tb] starts 2026-10-13", f"[{'あ' * 60}] starts 2026-10-13")
    names = [t.name for t in result.project.all_tasks()]
    assert names == ["a b", "あ" * 50]


def test_a_repeated_name_is_the_same_task() -> None:
    result = parse("[設計] as [T1] starts 2026-10-13", "[設計] as [T2] starts 2026-10-14")
    assert [t.name for t in result.project.all_tasks()] == ["設計"]  # 同じ名前は同じタスク。あとの指定が勝つ
    assert span(result, "設計")[0] == at(14)


@pytest.mark.parametrize(
    "text",
    ["", "[A] starts 2026-10-13", "@startgantt\n[A] starts 2026-10-13", "@startgantt\ntitle x\n@endgantt", "\x00\x01\x02"],
)
def test_text_without_a_diagram_or_tasks_is_refused(text: str) -> None:
    with pytest.raises(PlantUmlImportError):
        parse_plantuml(text, "x")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_puml_import.py -v`
Expected: FAIL(`ModuleNotFoundError: projectapp.puml_import`)

- [ ] **Step 3: 実装する**

`src/projectapp/puml_import.py`:

```python
"""PlantUML のガント(`@startgantt`)のテキストから、新規プロジェクトを作る。NiceGUI には依存しない。"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from projectapp.models import (
    MAX_SECTION_DEPTH,
    MAX_YEAR,
    MIN_YEAR,
    Project,
    Section,
    Task,
    TaskKind,
    new_id,
    tidy_task_name,
)
from projectapp.storage import dumps_project, parse_project

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
MAX_LASTS_DAYS = 3660  # 期間の上限(稼働日)。これを超える指定は読み飛ばす
MAX_SEARCH_DAYS = 3660  # 稼働日を探す日数の上限(全日が休みでも止まる)
WORKDAYS_PER_WEEK = 5
UNNAMED = "名称なし"

_D = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"
_START = re.compile(r"@startgantt\b", re.I)
_END = re.compile(r"@endgantt\b", re.I)
_TITLE = re.compile(r"title\s+(.+)$", re.I)
_PROJECT_STARTS = re.compile(rf"project\s+starts?\s+(?:on\s+)?{_D}$", re.I)
_WEEKDAY_RULE = re.compile(rf"({'|'.join(WEEKDAYS)})s?\s+(?:is|are)\s+(closed|open)$", re.I)
_RANGE_RULE = re.compile(rf"{_D}\s+to\s+{_D}\s+(?:is|are)\s+(closed|open)$", re.I)
_DAY_RULE = re.compile(rf"{_D}\s+(?:is|are)\s+(closed|open)$", re.I)
_SECTION = re.compile(r"--\s*(.+?)\s*--$")
_TASK = re.compile(r"\[([^\]]+)\](?:\s+as\s+\[([^\]]+)\])?(?:\s+(.*))?$", re.I)
_IGNORED = re.compile(r"(?:printscale|scale|hide|header|footer|caption|skinparam|language)\b|.*\bcolored\s+in\b", re.I)
_COLORED = re.compile(r"(?:\band\s+)?\b(?:is|are)\s+colored\s+in\s+\S+", re.I)
_HAPPENS_ON = re.compile(rf"\bhappens\s+on\s+{_D}", re.I)
_STARTS_DATE = re.compile(rf"\bstarts?\s+(?:on\s+)?{_D}", re.I)
_ENDS_DATE = re.compile(rf"\bends?\s+(?:on\s+)?{_D}", re.I)
_LASTS = re.compile(r"\blasts?\s+(\d+)\s+(day|week)s?\b", re.I)


class PlantUmlImportError(ValueError):
    """取り込めないテキスト(囲みがない・タスクがない・結果が不正)。"""


@dataclass(frozen=True)
class PlantUmlImport:
    project: Project
    task_count: int
    created_members: int  # 自動で作ったメンバーの数
    skipped_lines: int  # 解釈できず読み飛ばした行の数
    unresolved: int  # 日程が求まらなかったタスクの数
    clamped_allocations: int  # 範囲外で 100% にした割り当て率の数
    dropped_progress: int  # 進捗度(1〜100%)を取り込まなかったタスクの数


def _parse_date(text: str) -> date | None:
    try:
        year, month, day = (int(part) for part in re.split(r"[-/]", text))
        value = date(year, month, day)
    except ValueError:
        return None
    return value if MIN_YEAR <= year <= MAX_YEAR else None


def _section_path(text: str) -> tuple[str, ...]:
    """`親 / 子` を名前の並びにする。3 階層を超える分は、3 階層目の名前につなぐ。"""
    parts = [part for part in (tidy_task_name(p) for p in text.split("/")) if part]
    if len(parts) > MAX_SECTION_DEPTH:
        merged = tidy_task_name(" / ".join(parts[MAX_SECTION_DEPTH - 1 :]))
        parts = [*parts[: MAX_SECTION_DEPTH - 1], merged]
    return tuple(parts)


@dataclass
class _Raw:
    """読み取ったタスク 1 件(日付の解決の前)。"""

    name: str
    section: tuple[str, ...]
    milestone: bool = False
    day: date | None = None  # starts / happens on
    end_day: date | None = None
    lasts: int | None = None  # 稼働日数


class _Scanner:
    """行ごとに読む。解釈できない行は数える。"""

    def __init__(self) -> None:
        self.title = ""
        self.project_start: date | None = None
        self.first_date: date | None = None  # タスクの行で最初に現れた日付
        self.closed_weekdays = {5, 6}
        self.day_rules: dict[date, bool] = {}  # 日付 → 休みか
        self.tasks: list[_Raw] = []
        self.sections: list[tuple[str, ...]] = []
        self.skipped = 0
        self.complete = False
        self._started = False
        self._section: tuple[str, ...] = ()
        self._alias: dict[str, int] = {}
        self._names: dict[str, int] = {}

    def lookup(self, key: str) -> int | None:
        key = key.strip()
        return self._alias.get(key, self._names.get(key))

    def scan(self, text: str) -> None:
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("﻿")
            if not self._started:
                self._started = _START.match(line) is not None
                continue
            if _END.match(line):
                self.complete = True
                return
            if line and not line.startswith("'") and not self._line(line):
                self.skipped += 1

    def _line(self, line: str) -> bool:
        """行を解釈できたか。"""
        if m := _TITLE.match(line):
            self.title = m.group(1).strip()
            return True
        if m := _PROJECT_STARTS.match(line):
            day = _parse_date(m.group(1))
            if day is not None:
                self.project_start = day
            return day is not None
        if m := _WEEKDAY_RULE.match(line):
            index = WEEKDAYS[m.group(1).lower()]
            if m.group(2).lower() == "closed":
                self.closed_weekdays.add(index)
            else:
                self.closed_weekdays.discard(index)
            return True
        if m := _RANGE_RULE.match(line):
            return self._range(m.group(1), m.group(2), m.group(3).lower() == "closed")
        if m := _DAY_RULE.match(line):
            day = _parse_date(m.group(1))
            if day is not None:
                self.day_rules[day] = m.group(2).lower() == "closed"
            return day is not None
        if m := _SECTION.match(line):
            self._enter_section(_section_path(m.group(1)))
            return True
        if line.startswith("["):
            return self._task_line(line)
        return _IGNORED.match(line) is not None

    def _range(self, first: str, last: str, closed: bool) -> bool:
        start, end = _parse_date(first), _parse_date(last)
        if start is None or end is None or end < start or (end - start).days > MAX_SEARCH_DAYS:
            return False
        for offset in range((end - start).days + 1):
            self.day_rules[start + timedelta(days=offset)] = closed
        return True

    def _enter_section(self, path: tuple[str, ...]) -> None:
        self._section = path
        for depth in range(1, len(path) + 1):
            if path[:depth] not in self.sections:
                self.sections.append(path[:depth])

    def _declare(self, key: str, alias: str | None) -> int:
        """名前(または別名)のタスクの番号。なければ作る。`as` の別名は覚える。"""
        key = key.strip()
        index = self.lookup(key)
        if index is None:
            index = len(self.tasks)
            self.tasks.append(_Raw(key, self._section))
            self._names[key] = index
        if alias and alias.strip():
            self._alias[alias.strip()] = index
        return index

    def _task_line(self, line: str) -> bool:
        m = _TASK.match(line)
        if m is None or not m.group(1).strip():
            return False
        raw = self.tasks[self._declare(m.group(1), m.group(2))]
        rest = (m.group(3) or "").strip()
        return not rest or self._clauses(raw, rest)

    def _clauses(self, raw: _Raw, rest: str) -> bool:
        """タスクの行の続き。ひとつでも解釈できれば True。"""
        rest, colored = _COLORED.subn(" ", rest)
        return self._when(raw, rest) or colored > 0

    def _note(self, text: str) -> date | None:
        day = _parse_date(text)
        if day is not None and self.first_date is None:
            self.first_date = day
        return day

    def _when(self, raw: _Raw, rest: str) -> bool:
        matched = False
        if m := _HAPPENS_ON.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.milestone, raw.day, matched = True, day, True
        elif m := _STARTS_DATE.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.day, matched = day, True
        if m := _ENDS_DATE.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.end_day, matched = day, True
        if m := _LASTS.search(rest):
            count = int(m.group(1)) * (WORKDAYS_PER_WEEK if m.group(2).lower() == "week" else 1)
            if 1 <= count <= MAX_LASTS_DAYS:
                raw.lasts, matched = count, True
        return matched


@dataclass(frozen=True)
class _Calendar:
    closed_weekdays: frozenset[int]
    day_rules: dict[date, bool]

    def is_open(self, day: date) -> bool:
        closed = self.day_rules.get(day)
        return day.weekday() not in self.closed_weekdays if closed is None else not closed

    def next_open(self, day: date) -> date | None:
        """その日以降で最初の稼働日。見つからなければ None。"""
        for offset in range(MAX_SEARCH_DAYS):
            candidate = day + timedelta(days=offset)
            if self.is_open(candidate):
                return candidate
        return None


Span = tuple[date | None, date | None]


def _in_range(span: Span) -> bool:
    return all(day is not None and MIN_YEAR <= day.year <= MAX_YEAR for day in span)


class _Resolver:
    """PlantUML のルールで、タスクの開始日・終了日(含む)を求める。"""

    def __init__(self, scanner: _Scanner) -> None:
        self.scanner = scanner
        self.calendar = _Calendar(frozenset(scanner.closed_weekdays), dict(scanner.day_rules))
        self._memo: dict[int, Span] = {}
        self._active: set[int] = set()

    def span(self, index: int) -> Span:
        if index in self._memo:
            return self._memo[index]
        if index in self._active:  # 循環
            return None, None
        self._active.add(index)
        try:
            result = self._compute(self.scanner.tasks[index])
        finally:
            self._active.discard(index)
        self._memo[index] = result
        return result

    def _compute(self, raw: _Raw) -> Span:
        if raw.milestone:
            result: Span = (raw.day, raw.day)
        else:
            start = self._start(raw)
            result = (None, None) if start is None else (start, self._end(raw, start))
        return result if _in_range(result) else (None, None)

    def _start(self, raw: _Raw) -> date | None:
        if raw.day is not None:
            return raw.day
        return self.scanner.project_start or self.scanner.first_date

    def _end(self, raw: _Raw, start: date) -> date:
        if raw.end_day is not None:
            return max(raw.end_day, start)
        day = self.calendar.next_open(start)  # 開始日が休みなら、次の稼働日から数える
        if day is None:
            return start
        for _ in range((raw.lasts or 1) - 1):
            following = self.calendar.next_open(day + timedelta(days=1))
            if following is None:
                break
            day = following
        return day


@dataclass
class _Counts:
    unresolved: int = 0
    clamped: int = 0
    dropped_progress: int = 0
    created_members: int = 0


class _Builder:
    """読み取った結果と解決した日付から、`Project` を組み立てる。"""

    def __init__(self, scanner: _Scanner, name: str) -> None:
        self.scanner = scanner
        self.resolver = _Resolver(scanner)
        self.project = Project(tidy_task_name(scanner.title) or name, base_date=scanner.project_start or date.today())
        self.counts = _Counts()
        self._taken: set[str] = set()
        self._sections: dict[tuple[str, ...], Section] = {}

    def build(self) -> Project:
        for path in self.scanner.sections:
            self._section(path)
        tasks = [self._task(index, raw) for index, raw in enumerate(self.scanner.tasks)]
        for raw, task in zip(self.scanner.tasks, tasks):
            (self._section(raw.section).tasks if raw.section else self.project.tasks).append(task)
        return self.project

    def _fresh(self) -> str:
        value = new_id(self._taken)
        self._taken.add(value)
        return value

    def _end_of_day(self, day: date) -> datetime:
        return datetime.combine(day, self.project.work_start) + timedelta(hours=self.project.daily_hours)

    def _section(self, path: tuple[str, ...]) -> Section:
        if path not in self._sections:
            section = Section(path[-1], id=self._fresh())
            siblings = self.project.sections if len(path) == 1 else self._section(path[:-1]).sections
            siblings.append(section)
            self._sections[path] = section
        return self._sections[path]

    def _task(self, index: int, raw: _Raw) -> Task:
        start, end = self.resolver.span(index)
        task = Task(tidy_task_name(raw.name) or UNNAMED, id=self._fresh())
        if start is None or end is None:
            self.counts.unresolved += 1
        elif raw.milestone:
            task.kind = TaskKind.CHECKPOINT
            task.deadline = self._end_of_day(start)
        else:
            task.planned_start = datetime.combine(start, self.project.work_start)
            task.planned_end = self._end_of_day(end)
        return task


def parse_plantuml(text: str, name: str) -> PlantUmlImport:
    """PlantUML のガントのテキストから、新規プロジェクトを作る。取り込めなければ `PlantUmlImportError`。"""
    scanner = _Scanner()
    scanner.scan(text)
    if not scanner.complete:
        raise PlantUmlImportError("@startgantt から @endgantt までが見つかりません")
    if not scanner.tasks:
        raise PlantUmlImportError("取り込めるタスクがありません")
    builder = _Builder(scanner, name)
    project = builder.build()
    try:  # 保存・読込と同じ検証を通す
        project = parse_project(dumps_project(project), project.name)
    except (ValueError, KeyError, TypeError) as exc:
        raise PlantUmlImportError(f"取り込んだ結果が正しくありません: {exc}") from exc
    counts = builder.counts
    return PlantUmlImport(
        project,
        len(project.all_tasks()),
        counts.created_members,
        scanner.skipped,
        counts.unresolved,
        counts.clamped,
        counts.dropped_progress,
    )
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_puml_import.py -v && uv run ty check src`
Expected: PASS、ty はエラーなし

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/puml_import.py test/test_puml_import.py
git commit -m "$(cat <<'EOF'
feat: PlantUML のガントを読み、絶対日付のタスクを新規プロジェクトにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 相対指定と依存(先行タスク)

**Files:**
- Modify: `src/projectapp/puml_import.py`
- Modify: `test/test_puml_import.py`

**Interfaces:**
- Consumes: Task 1 の `_Raw`・`_Scanner._line`・`_Scanner._when`・`_Resolver._compute`・`_Resolver._start`・`_Builder.build`。
- Produces: `_Raw.after: tuple[str, str, int] | None`(参照するタスクの名前または別名、`"end"` か `"start"`、日数)、`_Raw.preds: list[str]`(`->` の先行の名前または別名)、`_Resolver._anchor(after)`、`_Builder._link(tasks)`(先行を `Task.predecessors` に入れる)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_puml_import.py` に足す:

```python
def test_starts_at_the_end_of_another_task_begins_on_the_next_working_day() -> None:
    result = parse("[A] starts 2026-10-15 and ends 2026-10-16", "[B] starts at [A]'s end and lasts 2 days")
    assert span(result, "B") == (at(19), at(20, *END))
    assert task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_starts_at_the_start_of_another_task_does_not_become_a_predecessor() -> None:
    result = parse("[A] starts 2026-10-15 and ends 2026-10-16", "[B] starts at [A]'s start and lasts 1 day")
    assert span(result, "B")[0] == at(15) and task_named(result, "B").predecessors == []


def test_days_after_the_end_counts_calendar_days_from_the_next_day() -> None:
    result = parse("[A] starts 2026-10-12", "[B] starts 3 days after [A]'s end")
    assert span(result, "B")[0] == at(16)  # 12 の終わりの 1 日後が 13、さらに 3 日後
    assert task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_an_arrow_makes_a_predecessor_and_starts_after_it() -> None:
    result = parse("[A] starts 2026-10-12 and ends 2026-10-13", "[B] lasts 2 days", "[A] -> [B]")
    assert span(result, "B") == (at(14), at(15, *END))
    assert task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_an_explicit_start_wins_over_an_arrow_but_the_link_is_kept() -> None:
    result = parse("[A] starts 2026-10-12", "[B] starts 2026-10-20", "[A] -> [B]")
    assert span(result, "B")[0] == at(20) and task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_references_by_alias_and_forward_references_resolve() -> None:
    result = parse(
        "[B] as [T2] starts at [T1]'s end and lasts 1 day",
        "[A] as [T1] starts 2026-10-12 and ends 2026-10-12",
    )
    assert span(result, "B")[0] == at(13)


def test_chains_resolve_through_several_tasks() -> None:
    result = parse(
        "[A] starts 2026-10-12", "[B] starts at [A]'s end and lasts 1 day", "[C] starts at [B]'s end and lasts 1 day"
    )
    assert span(result, "C")[0] == at(14)


def test_a_milestone_can_follow_the_end_of_a_task() -> None:
    result = parse("[A] starts 2026-10-12 and ends 2026-10-14", "[M] happens at [A]'s end")
    task = task_named(result, "M")
    assert task.kind is TaskKind.CHECKPOINT and task.deadline == at(14, *END)
    assert task.predecessors == [task_named(result, "A").id]


def test_a_cycle_leaves_both_tasks_without_a_schedule() -> None:
    result = parse("[A] starts at [B]'s end", "[B] starts at [A]'s end")
    assert span(result, "A") == (None, None) and span(result, "B") == (None, None)
    assert result.unresolved == 2


def test_a_reference_to_an_unknown_task_is_unresolved_and_creates_nothing() -> None:
    result = parse("[A] starts at [Z]'s end")
    assert span(result, "A") == (None, None) and task_named(result, "A").predecessors == []
    assert [t.name for t in result.project.all_tasks()] == ["A"]


def test_a_task_after_an_unresolved_task_is_unresolved() -> None:
    result = parse("[A]", "[B] lasts 1 day", "[A] -> [B]")
    assert span(result, "B") == (None, None)
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_puml_import.py -v`
Expected: 新しい 10 件が FAIL(`predecessors` が空、日付が違う)

- [ ] **Step 3: 実装する**

`src/projectapp/puml_import.py` を次のとおり直す。

(0) import を直す: `from dataclasses import dataclass, field` にする。

(1) 正規表現を足す(`_LASTS` の次):

```python
_REF = r"\[([^\]]+)\]'s\s+(end|start)"
_DEPENDENCY = re.compile(r"\[([^\]]+)\]\s*->\s*\[([^\]]+)\]$")
_HAPPENS_AT = re.compile(rf"\bhappens\s+at\s+{_REF}", re.I)
_STARTS_AT = re.compile(rf"\bstarts?\s+at\s+{_REF}", re.I)
_STARTS_AFTER = re.compile(r"\bstarts?\s+(\d+)\s+days?\s+after\s+\[([^\]]+)\]'s\s+end", re.I)
```

(2) `_Raw` に項目を足す:

```python
    after: tuple[str, str, int] | None = None  # (参照するタスク, "end" か "start", 日数)
    preds: list[str] = field(default_factory=list)  # `->` の先行(名前または別名)
```

(3) `_Scanner._line` の `_SECTION` の分岐の次に、依存を足す(`line.startswith("[")` の前):

```python
        if m := _DEPENDENCY.match(line):
            self._declare(m.group(1), None)
            self.tasks[self._declare(m.group(2), None)].preds.append(m.group(1).strip())
            return True
```

(4) `_Scanner._when` を差し替える:

```python
    def _when(self, raw: _Raw, rest: str) -> bool:
        matched = False
        if m := _HAPPENS_ON.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.milestone, raw.day, matched = True, day, True
        elif m := _HAPPENS_AT.search(rest):
            raw.milestone, raw.after, matched = True, (m.group(1).strip(), m.group(2).lower(), 0), True
        elif m := _STARTS_AT.search(rest):
            raw.after, matched = (m.group(1).strip(), m.group(2).lower(), 0), True
        elif m := _STARTS_AFTER.search(rest):
            raw.after, matched = (m.group(2).strip(), "end", int(m.group(1))), True
        elif m := _STARTS_DATE.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.day, matched = day, True
        if m := _ENDS_DATE.search(rest):
            if (day := self._note(m.group(1))) is not None:
                raw.end_day, matched = day, True
        if m := _LASTS.search(rest):
            count = int(m.group(1)) * (WORKDAYS_PER_WEEK if m.group(2).lower() == "week" else 1)
            if 1 <= count <= MAX_LASTS_DAYS:
                raw.lasts, matched = count, True
        return matched
```

(5) `_Resolver._compute` と `_start` を差し替え、`_anchor` を足す:

```python
    def _compute(self, raw: _Raw) -> Span:
        if raw.milestone:
            day = raw.day if raw.day is not None else self._anchor(raw.after)
            result: Span = (day, day)
        else:
            start = self._start(raw)
            result = (None, None) if start is None else (start, self._end(raw, start))
        return result if _in_range(result) else (None, None)

    def _anchor(self, after: tuple[str, str, int] | None) -> date | None:
        """参照するタスクの終了日(`end`)か開始日(`start`)。求まらなければ None。"""
        if after is None:
            return None
        index = self.scanner.lookup(after[0])
        if index is None:
            return None
        start, end = self.span(index)
        return start if after[1] == "start" else end

    def _start(self, raw: _Raw) -> date | None:
        if raw.day is not None:
            return raw.day
        if raw.after is not None:
            base = self._anchor(raw.after)
            if base is None:
                return None
            if raw.after[1] == "start":
                return base
            return self.calendar.next_open(base + timedelta(days=1 + raw.after[2]))
        if raw.preds:
            ends = [self._anchor((key, "end", 0)) for key in raw.preds]
            known = [end for end in ends if end is not None]
            if len(known) != len(ends):
                return None
            return self.calendar.next_open(max(known) + timedelta(days=1))
        return self.scanner.project_start or self.scanner.first_date
```

(6) `_Builder.build` の `return self.project` の前に `self._link(tasks)` を足し、メソッドを足す:

```python
    def _link(self, tasks: list[Task]) -> None:
        """`->` と、終わりからの指定(`'s end`)の参照先を、先行タスクにする(`'s start` は入れない)。"""
        for index, (raw, task) in enumerate(zip(self.scanner.tasks, tasks)):
            keys = list(raw.preds)
            if raw.after is not None and raw.after[1] == "end":
                keys.append(raw.after[0])
            for key in keys:
                found = self.scanner.lookup(key)
                if found is not None and found != index and tasks[found].id not in task.predecessors:
                    task.predecessors.append(tasks[found].id)
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_puml_import.py -v && uv run ty check src`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/puml_import.py test/test_puml_import.py
git commit -m "$(cat <<'EOF'
feat: PlantUML 取り込みで相対指定と依存を先行タスクにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 担当者・進捗・通知文・ファイル読み込み・往復

**Files:**
- Modify: `src/projectapp/puml_import.py`
- Modify: `test/test_puml_import.py`

**Interfaces:**
- Consumes: Task 1・2 の `_Raw`・`_Scanner._clauses`・`_Builder._task`・`_Builder.counts`。
- Produces:
  - `_Raw.assignees: list[tuple[str, float | None]]`(名前と、`:N%` の N。省略は None)、`_Raw.progress: int | None`。
  - `summary(result: PlantUmlImport) -> str`。
  - `read_plantuml(path: Path) -> str`(UTF-8。BOM があれば除く。読めなければ `PlantUmlImportError`)。
  - `PLANTUML_OPEN_FILE_TYPES = ("PlantUML ファイル (*.puml *.plantuml *.txt)",)`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_puml_import.py` の先頭の import に `from pathlib import Path`、`import os`、`import shutil`、`import subprocess` と、次を足す:

```python
from projectapp.filtering import TaskFilter
from projectapp.models import Assignee, Project, Section
from projectapp.plantuml import build_plantuml
from projectapp.puml_import import PLANTUML_OPEN_FILE_TYPES, read_plantuml, summary
from projectapp.timeline import Scale
```

テストを足す:

```python
def test_assignees_create_members_and_allocations() -> None:
    result = parse(
        "[A] on {田中:50%} {鈴木} starts 2026-10-13 and ends 2026-10-13",
        "[B] on {田中} starts 2026-10-14 and ends 2026-10-14",
    )
    assert [m.name for m in result.project.members] == ["田中", "鈴木"]
    assert all(m.ratio == 1.0 for m in result.project.members) and result.created_members == 2
    assert [(a.name, a.allocation) for a in task_named(result, "A").assignees] == [("田中", 0.5), ("鈴木", 1.0)]
    assert [(a.name, a.allocation) for a in task_named(result, "B").assignees] == [("田中", 1.0)]


@pytest.mark.parametrize("percent", ["0%", "101%", "150%"])
def test_an_allocation_out_of_range_becomes_100_percent_and_is_counted(percent: str) -> None:
    result = parse(f"[A] on {{田中:{percent}}} starts 2026-10-13")
    assert task_named(result, "A").assignees[0].allocation == 1.0 and result.clamped_allocations == 1


def test_empty_and_duplicate_assignees_are_ignored() -> None:
    result = parse("[A] on {} {田中:30%} {田中:80%} starts 2026-10-13")
    assert [(a.name, a.allocation) for a in task_named(result, "A").assignees] == [("田中", 0.3)]
    assert [m.name for m in result.project.members] == ["田中"]


def test_a_checkpoint_has_no_assignees() -> None:
    result = parse("[M] on {田中} happens on 2026-10-23")
    assert task_named(result, "M").assignees == [] and result.project.members == []


@pytest.mark.parametrize(
    ("line", "status"),
    [
        ("[A] starts 2026-10-13", Status.NOT_STARTED),
        ("[A] starts 2026-10-13 and is 0% completed", Status.NOT_STARTED),
        ("[A] starts 2026-10-13 and is 1% completed", Status.RUNNING),
        ("[A] starts 2026-10-13 and is 99% completed", Status.RUNNING),
        ("[A] starts 2026-10-13 and is 100% completed", Status.DONE),
    ],
)
def test_progress_decides_only_the_status(line: str, status: Status) -> None:
    result = parse(line)
    task = task_named(result, "A")
    assert task.status is status and task.actuals == []


def test_progress_on_a_separate_line_and_the_dropped_count() -> None:
    result = parse("[A] as [T1] starts 2026-10-13", "[T1] is 40% completed", "[B] starts 2026-10-13", "[C] is 0% completed")
    assert task_named(result, "A").status is Status.RUNNING
    assert result.dropped_progress == 1  # 0% と、進捗のないものは数えない


def test_progress_over_100_skips_the_line() -> None:
    result = parse("[A] starts 2026-10-13", "[A] is 150% completed")
    assert task_named(result, "A").status is Status.NOT_STARTED and result.skipped_lines == 1


def test_a_checkpoint_is_done_only_at_100_percent() -> None:
    assert task_named(parse("[M] happens on 2026-10-23 and is 100% completed"), "M").status is Status.DONE
    assert task_named(parse("[M] happens on 2026-10-23 and is 50% completed"), "M").status is Status.NOT_STARTED


def test_a_milestone_without_a_date_is_a_plain_unscheduled_task() -> None:
    result = parse("[M] happens at [Z]'s end")
    task = task_named(result, "M")
    assert task.kind is TaskKind.NORMAL and task.deadline is None and result.unresolved == 1


def test_the_summary_lists_counts_and_notes() -> None:
    result = parse(
        "[A] on {田中:0%} starts 2026-10-13 and is 50% completed", "[B] starts at [Z]'s end", "foo bar baz"
    )
    text = summary(result)
    assert text.startswith("取り込みました(タスク 2 件、メンバー 1 人を作成)")
    for note in ("読み飛ばした行 1 行", "日程が求まらないタスク 1 件", "割り当て率を 100% にした担当 1 件", "進捗度を取り込まなかったタスク 1 件"):
        assert note in text
    assert summary(parse("[A] starts 2026-10-13")) == "取り込みました(タスク 1 件)"


def test_read_plantuml_reads_utf8_with_or_without_a_bom(tmp_path: Path) -> None:
    plain, bom = tmp_path / "a.puml", tmp_path / "b.puml"
    plain.write_text("@startgantt\n[設計] starts 2026-10-13\n@endgantt\n", encoding="utf-8")
    bom.write_text("@startgantt\n[設計] starts 2026-10-13\n@endgantt\n", encoding="utf-8-sig")
    assert read_plantuml(plain) == read_plantuml(bom)
    assert "設計" in parse_plantuml(read_plantuml(bom), "x").project.all_tasks()[0].name


def test_read_plantuml_refuses_unreadable_files(tmp_path: Path) -> None:
    binary = tmp_path / "bin.puml"
    binary.write_bytes(b"\xff\xfe\x00\x81\x82")
    with pytest.raises(PlantUmlImportError):
        read_plantuml(binary)
    with pytest.raises(PlantUmlImportError):
        read_plantuml(tmp_path / "missing.puml")


def test_the_open_file_types_name_the_extensions() -> None:
    assert PLANTUML_OPEN_FILE_TYPES == ("PlantUML ファイル (*.puml *.plantuml *.txt)",)


def test_the_output_of_build_plantuml_comes_back() -> None:
    first = Task("設計", id="t1", planned_start=datetime(2026, 10, 13, 9), planned_end=datetime(2026, 10, 14, 15, 30),
                 assignees=[Assignee("田中", 1.0)])
    second = Task("実装", id="t2", planned_start=datetime(2026, 10, 15, 9), planned_end=datetime(2026, 10, 20, 15, 30),
                  predecessors=["t1"])
    release = Task("リリース", id="t3", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 15, 30))
    project = Project("検証", tasks=[first], sections=[Section("開発", [second], [Section("運用", [release])])])
    text = build_plantuml(
        project, {}, (date(2026, 10, 12), date(2026, 10, 30)), Scale.DAY, TaskFilter(), datetime(2026, 10, 1)
    ).text
    result = parse_plantuml(text, "代わり")
    back = result.project
    assert back.name == "検証" and result.created_members == 0 and result.skipped_lines == 0
    by_name = {t.name: t for t in back.all_tasks()}
    assert set(by_name) == {"設計 (田中)", "実装", "リリース"}  # 担当者名は表示名に残る
    assert (by_name["設計 (田中)"].planned_start, by_name["設計 (田中)"].planned_end) == (at(13), at(14, *END))
    assert (by_name["実装"].planned_start, by_name["実装"].planned_end) == (at(15), at(20, *END))
    assert by_name["実装"].predecessors == [by_name["設計 (田中)"].id]
    assert by_name["リリース"].kind is TaskKind.CHECKPOINT and by_name["リリース"].deadline == at(23, *END)
    assert [t.name for t in back.tasks] == ["設計 (田中)"]
    assert [s.name for s in back.sections] == ["開発"] and [s.name for s in back.sections[0].sections] == ["運用"]


PLANTUML_JAR = Path(os.environ.get("PLANTUML_JAR", "/usr/local/lib/plantuml.jar"))

SUPPORTED_SYNTAX = """@startgantt
Project starts 2026-10-12
saturday are closed
sunday are closed
2026-10-16 is closed
-- 開発 --
[設計] as [T1] starts 2026-10-13 and lasts 3 days
[T1] is 40% completed
[実装] as [T2] starts at [T1]'s end and lasts 5 days
[テスト] as [T3] starts 3 days after [T2]'s end and lasts 2 days
[準備] as [T4] starts at [T1]'s start and lasts 1 day
[T1] -> [T2]
[リリース] happens on 2026-10-30
[節目] happens at [T2]'s end
@endgantt
"""


@pytest.mark.skipif(shutil.which("java") is None or not PLANTUML_JAR.exists(), reason="java と plantuml.jar が要る")
def test_the_supported_syntax_is_accepted_by_plantuml_and_imported() -> None:
    done = subprocess.run(
        ["java", "-jar", str(PLANTUML_JAR), "-pipe", "-tsvg"], input=SUPPORTED_SYNTAX.encode(), capture_output=True, timeout=60
    )
    svg = done.stdout.decode(errors="replace")
    assert done.returncode == 0 and "<svg" in svg and "Syntax Error" not in svg
    result = parse_plantuml(SUPPORTED_SYNTAX, "検証")
    assert result.skipped_lines == 0 and result.unresolved == 0
    assert result.task_count == 6
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_puml_import.py -v`
Expected: 新しいテストが FAIL(`summary`・`read_plantuml` が未定義、担当者・状態が未実装)

- [ ] **Step 3: 実装する**

`src/projectapp/puml_import.py` を次のとおり直す。

(1) import を直す: `from pathlib import Path` を足し、`from projectapp.models import (...)` に `Assignee`・`Member`・`Status` を足す。

(2) 定数と正規表現を足す(`_LASTS` や `_REF` の並びに):

```python
PLANTUML_OPEN_FILE_TYPES = ("PlantUML ファイル (*.puml *.plantuml *.txt)",)
_ON = re.compile(r"\bon\s+((?:\{[^}]*\}\s*)+)", re.I)
_RESOURCE = re.compile(r"\{\s*([^}:]*?)\s*(?::\s*(\d+(?:\.\d+)?)\s*%)?\s*\}")
_PROGRESS = re.compile(r"\bis\s+(\d{1,3})%\s+completed\b", re.I)
```

(3) `_Raw` に項目を足す:

```python
    assignees: list[tuple[str, float | None]] = field(default_factory=list)  # (名前, `:N%` の N。省略は None)
    progress: int | None = None
```

(4) `_Scanner._clauses` を差し替える:

```python
    def _clauses(self, raw: _Raw, rest: str) -> bool:
        """タスクの行の続き。ひとつでも解釈できれば True。"""
        rest, colored = _COLORED.subn(" ", rest)
        matched = colored > 0
        if m := _ON.search(rest):
            raw.assignees += [(n, float(p) if p else None) for n, p in _RESOURCE.findall(m.group(1))]
            rest = f"{rest[: m.start()]} {rest[m.end() :]}"
            matched = True
        if (m := _PROGRESS.search(rest)) and int(m.group(1)) <= 100:
            raw.progress, matched = int(m.group(1)), True
        return self._when(raw, rest) or matched
```

(5) `_Builder` を直す。`__init__` に `self._members: dict[str, Member] = {}` を足し、`_task` を差し替え、メンバーの関数を足す:

```python
    def _task(self, index: int, raw: _Raw) -> Task:
        start, end = self.resolver.span(index)
        task = Task(tidy_task_name(raw.name) or UNNAMED, id=self._fresh())
        task.status = _status(raw.progress)
        if raw.progress:
            self.counts.dropped_progress += 1
        if start is None or end is None:
            self.counts.unresolved += 1
        elif raw.milestone:
            task.kind = TaskKind.CHECKPOINT
            task.deadline = self._end_of_day(start)
            task.status = Status.DONE if task.status is Status.DONE else Status.NOT_STARTED
            return task
        else:
            task.planned_start = datetime.combine(start, self.project.work_start)
            task.planned_end = self._end_of_day(end)
        task.assignees = self._assignees(raw)
        return task

    def _assignees(self, raw: _Raw) -> list[Assignee]:
        found: list[Assignee] = []
        for raw_name, percent in raw.assignees:
            name = tidy_task_name(raw_name)
            if not name or any(a.name == name for a in found):
                continue
            if name not in self._members:
                member = Member(name, id=self._fresh())
                self._members[name] = member
                self.project.members.append(member)
                self.counts.created_members += 1
            allocation = 1.0 if percent is None else percent / 100
            if percent is not None and not 1 <= percent <= 100:
                allocation = 1.0
                self.counts.clamped += 1
            found.append(Assignee(name, allocation))
        return found
```

> 注意: 未解決で日程なしのタスク(`start is None`)にも担当者を付けるため、`if start is None ...` の分岐のあとに `task.assignees = ...` を置く(チェックポイントだけが早期 return)。日程なしに降格したマイルストーン(`raw.milestone` だが `start is None`)は通常タスクとして扱い、担当者も付く。

(6) 状態の関数を足す(`_in_range` の近く):

```python
def _status(progress: int | None) -> Status:
    if not progress:
        return Status.NOT_STARTED
    return Status.DONE if progress == 100 else Status.RUNNING
```

(7) 通知文とファイル読み込みを足す(ファイルの末尾):

```python
def summary(result: PlantUmlImport) -> str:
    """取り込み後の通知。件数と、取り込めなかったものの内訳。"""
    head = f"タスク {result.task_count} 件"
    if result.created_members:
        head += f"、メンバー {result.created_members} 人を作成"
    notes = [
        f"読み飛ばした行 {result.skipped_lines} 行" if result.skipped_lines else "",
        f"日程が求まらないタスク {result.unresolved} 件" if result.unresolved else "",
        f"割り当て率を 100% にした担当 {result.clamped_allocations} 件" if result.clamped_allocations else "",
        f"進捗度を取り込まなかったタスク {result.dropped_progress} 件" if result.dropped_progress else "",
    ]
    detail = "、".join(note for note in notes if note)
    return f"取り込みました({head})" + (f"。{detail}" if detail else "")


def read_plantuml(path: Path) -> str:
    """UTF-8 のテキストを読む(BOM は除く)。読めなければ `PlantUmlImportError`。"""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise PlantUmlImportError(f"ファイルを読めません: {exc}") from exc
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_puml_import.py -v && uv run ty check src`
Expected: すべて PASS(`java` と `plantuml.jar` があれば、描画のテストも走る)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/puml_import.py test/test_puml_import.py
git commit -m "$(cat <<'EOF'
feat: PlantUML 取り込みで担当者と進捗の状態を読み、通知文を作る

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: メニューとファイル選択(画面)

**Files:**
- Modify: `src/projectapp/export.py`(`ImageExporter` の Protocol と `NativeImageExporter`)
- Modify: `src/projectapp/views.py`(import・メッセージ・メニュー項目・フロー)
- Modify: `test/test_views.py`(`FakeExporter`・メニューの既存テスト・新しいテスト)

**Interfaces:**
- Consumes: Task 3 の `PLANTUML_OPEN_FILE_TYPES`・`parse_plantuml`・`read_plantuml`・`summary`・`PlantUmlImportError`。既存の `MainView.is_dirty`・`save_then`・`show_project`・`forms.open_unsaved_dialog(on_save, on_discard, purpose=...)`。
- Produces:
  - `ImageExporter.ask_open_path(self, file_types: tuple[str, ...]) -> Path | None`(読み込み用のファイル選択。選ばなければ None)。
  - `MainView.request_import_plantuml()`、`MainView.import_plantuml()`(async)、`MainView.pick_plantuml()`。
  - 定数 `IMPORT_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、取り込めます"`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py`:

(1) `FakeExporter` に、読み込み用の選択を足す。`__init__` の引数に `open_path: Path | None = None` を末尾に足し、次を足す:

```python
        self.open_path = open_path
        self.asked_open: list[tuple[str, ...]] = []
```

メソッド:

```python
    async def ask_open_path(self, file_types: tuple[str, ...] = ()) -> Path | None:
        self.asked_open.append(file_types)
        return self.open_path
```

(2) 既存のメニューのテストを直す(`ファイル`メニューは、`開く`の次に取り込みが入る):

```python
    assert menu_items(user, "menu-file-items") == [
        ("開く", "file-open"),
        ("PlantUML を取り込む", "file-import-plantuml"),
        ("新規プロジェクト作成", "file-new"),
        ("上書き保存", "save-project"),
        ("名前をつけて保存", "file-save-as"),
        ("格納先を変更", "file-change-dir"),
        ("祝日を更新", "refresh-holidays"),
    ]
```

アイコン: `["folder_open", "upload_file", "note_add", "save", "save_as", "drive_file_move", "event_repeat"]`。水平線: `kinds == ["item", "item", "item", "sep", "item", "item", "sep", "item", "item"]`。

(3) 新しいテストを足す:

```python
IMPORT_SAMPLE = """@startgantt
title 取込元
Project starts 2026-10-12
-- 開発 --
[設計] on {田中} starts 2026-10-13 and ends 2026-10-14
@endgantt
"""


def write_puml(tmp_path: Path, text: str = IMPORT_SAMPLE) -> Path:
    folder = tmp_path / "other"
    folder.mkdir(exist_ok=True)
    source = folder / "in.puml"
    source.write_text(text, encoding="utf-8")
    return source


async def open_for_import(user: User, tmp_path: Path, exporter: FakeExporter) -> MainView:
    save_cache({}, tmp_path)
    views: list[MainView] = []
    mount_preview(tmp_path, views, exporter)
    await user.open("/")
    return views[0]


async def test_import_plantuml_opens_an_unsaved_project(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    assert await wait_until(lambda: view.project.name == "取込元")
    assert view.path is None and view.is_dirty()  # 保存前の新規。ファイルは作らない
    assert [t.name for t in view.project.sections[0].tasks] == ["設計"]
    assert [m.name for m in view.project.members] == ["田中"]
    assert exporter.asked_open == [PLANTUML_OPEN_FILE_TYPES]
    await user.should_see("取り込みました(タスク 1 件、メンバー 1 人を作成)")
    assert not list(tmp_path.glob("*.json"))


async def test_cancelling_the_import_dialog_changes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=None)
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    assert await wait_until(lambda: exporter.asked_open != [])
    assert view.project.name == "新規プロジェクト" and not view.is_dirty()


async def test_import_plantuml_refuses_a_text_without_a_diagram(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path, "hello"))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    await user.should_see("取り込めませんでした")
    assert view.project.name == "新規プロジェクト" and not view.is_dirty()


async def test_import_plantuml_needs_the_native_window(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path), available=False)
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    await user.should_see("ネイティブウィンドウでのみ、取り込めます")
    assert exporter.asked_open == [] and view.project.name == "新規プロジェクト"


async def test_import_plantuml_asks_before_dropping_unsaved_edits(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    view.save_section("追加")
    user.find(marker="file-import-plantuml").click()
    await user.should_see(marker="unsaved-discard")
    assert exporter.asked_open == []
    user.find(marker="unsaved-discard").click()
    assert await wait_until(lambda: view.project.name == "取込元")
    assert [s.name for s in view.project.sections] == ["開発"]


async def test_cancelling_the_unsaved_dialog_does_not_start_the_import(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    view.save_section("追加")
    user.find(marker="file-import-plantuml").click()
    await user.should_see(marker="unsaved-cancel")
    user.find(marker="unsaved-cancel").click()
    assert exporter.asked_open == [] and [s.name for s in view.project.sections] == ["追加"]


async def test_an_imported_project_asks_before_another_project_is_opened(user: User, tmp_path: Path) -> None:
    save_project(Project("既存"), tmp_path)
    exporter = FakeExporter(open_path=write_puml(tmp_path))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-plantuml").click()
    assert await wait_until(lambda: view.project.name == "取込元")
    await choose_in_combo(user, "既存")
    await user.should_see(marker="unsaved-save")
```

テストファイルの import に `from projectapp.puml_import import PLANTUML_OPEN_FILE_TYPES` を足す。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -k "import or menus_list or file_menu" -v`
Expected: FAIL(メニュー項目がない、`ask_open_path` が Protocol にない)

- [ ] **Step 3: 実装する**

`src/projectapp/export.py`:

`ImageExporter`(Protocol)に、`ask_path` の次に足す:

```python
    async def ask_open_path(self, file_types: tuple[str, ...]) -> Path | None: ...
```

`NativeImageExporter` に、`ask_path` の次に足す:

```python
    async def ask_open_path(self, file_types: tuple[str, ...]) -> Path | None:
        import webview  # ネイティブのときだけ使う

        window = app.native.main_window
        if window is None:
            return None
        result = await window.create_file_dialog(  # ty: ignore[unresolved-attribute]
            dialog_type=webview.FileDialog.OPEN,
            file_types=file_types,
        )
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])
```

`src/projectapp/views.py`:

(1) import に足す(`from projectapp.plantuml import ...` の並びに):

```python
from projectapp.puml_import import (
    PLANTUML_OPEN_FILE_TYPES,
    PlantUmlImportError,
    parse_plantuml,
    read_plantuml,
)
from projectapp.puml_import import summary as import_summary
```

(2) 定数を、`CHANGE_DIR_NOT_NATIVE_MESSAGE` の次に足す:

```python
IMPORT_NOT_NATIVE_MESSAGE = "ネイティブウィンドウでのみ、取り込めます"
```

(3) `ファイル`メニューの `開く` の次に足す:

```python
                    MenuItem("PlantUML を取り込む", "upload_file", self.request_import_plantuml, "file-import-plantuml"),
```

(4) `request_new` の次に、フローを足す:

```python
    def request_import_plantuml(self) -> None:
        """PlantUML の取り込みを始める(ネイティブのみ)。編集中は、確認してからファイルを選ばせる。"""
        if not self.exporter.available:
            ui.notify(IMPORT_NOT_NATIVE_MESSAGE, type="warning")
            return
        if not self.is_dirty():
            self.pick_plantuml()
            return
        open_unsaved_dialog(
            on_save=lambda: self.save_then(self.pick_plantuml),
            on_discard=self.pick_plantuml,
            purpose="取り込み",
        )

    def pick_plantuml(self) -> None:
        """ファイル選択を始める。確認ダイアログは閉じると消えるので、タイマーは画面の直下に置く。"""
        with self.client:
            ui.timer(0, self.import_plantuml, once=True)

    async def import_plantuml(self) -> None:
        """選んだ PlantUML から、保存前の新規プロジェクトを作る。失敗したら、通知だけして何も変えない。"""
        path = await self.exporter.ask_open_path(PLANTUML_OPEN_FILE_TYPES)
        if path is None:
            return
        try:
            result = parse_plantuml(read_plantuml(path), path.stem)
        except PlantUmlImportError as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        self.show_project(result.project, None)
        self.snapshot = asdict(Project(NEW_PROJECT_NAME))  # 空の新規とは別物なので、未保存の扱いにする
        ui.notify(import_summary(result))
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_views.py test/test_export.py -v -n auto && uv run ty check src`
Expected: PASS(既存のメニューのテストを直した分も含む)

- [ ] **Step 5: 全体を確認して Commit**

Run: `uv run pytest -n auto`
Expected: すべて PASS

```bash
git add src/projectapp/export.py src/projectapp/views.py test/test_views.py
git commit -m "$(cat <<'EOF'
feat: ファイルメニューから PlantUML を取り込めるようにする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 文書の更新と最終確認

**Files:**
- Modify: `CLAUDE.md`(`projectapp/` 直下)
- Modify: `docs/development.md`
- Modify: `docs/superpowers/specs/2026-10-16-plantuml-import-design.md`

**Interfaces:**
- Consumes: Task 1〜4 の実装。
- Produces: 仕様書・開発者向けメモ・設計書が実装と一致する。

- [ ] **Step 1: 設計書を実装に合わせて直す**

`docs/superpowers/specs/2026-10-16-plantuml-import-design.md` に、実装で決めた次の点を反映する:

- 日付の指定(`<日付> is closed`)は曜日の指定より優先し、同じ種類では後に書かれたものが勝つ(「対応する構文」の休みの項)。
- `starts at [X]'s start` の参照先は先行タスクにしない(終わりからの指定と `->` だけ)(「プロジェクトへの変換」の先行の項)。
- 日程が求まらないマイルストーンは、チェックポイントにせず、日程なしの通常タスクにする(締切が必須のため)。
- 取り込んだプロジェクトは未保存の扱い(`is_dirty` が真)で開く。
- ネイティブウィンドウでないときは、メニュー項目は押せて、押すと通知する(`担当者へ書き出し`・`格納先を変更`と同じ)。
- 成功の通知は `取り込みました(タスク n 件、メンバー m 人を作成)` のあとに、`。` で続けて内訳を足す。
- 描画のテストは、対応する構文が `plantuml.jar` で構文エラーにならないことと、それが取り込めることを確かめる(日程の照合はしない)。

- [ ] **Step 2: 仕様書(`CLAUDE.md`)を更新する**

`projectapp/CLAUDE.md`:

- 「PlantUML の出力」の節の次に、「PlantUML の取り込み」の節を足す。内容は設計書の「決定事項」「対応する構文」「プロジェクトへの変換」「失敗と通知」を、既存の節と同じ密度(箇条書き 5〜6 行)で要約する。
- 「ヘッダー」の`ファイル`メニューの項目に、`開く`の次に `PlantUML を取り込む` を足す。

- [ ] **Step 3: 開発者向けメモ(`docs/development.md`)を更新する**

- モジュール構成の表の `plantuml.py` の次の行に、`puml_import.py` を足す: `parse_plantuml`(`PlantUmlImport`)、`summary`、`read_plantuml`、`PLANTUML_OPEN_FILE_TYPES`。構成は `_Scanner`(行)→ `_Resolver`(日付)→ `_Builder`(`Project`)。純粋関数。結果は `dumps_project` → `parse_project` で検証する。
- 設計書の表に `PlantUML 取り込み | 2026-10-16-plantuml-import-design.md` を足す。
- 「既知の見送り事項」に次を足す: 進捗度の取り込み(`Task.progress` の新設を要する別機能)、`then`・`separator` などの構文、公式文法の全面的な網羅。

- [ ] **Step 4: 最終確認**

Run: `uv run pytest -n auto && uv run ty check src`
Expected: すべて PASS、ty はエラーなし

- [ ] **Step 5: 実機で確かめる**

Run: `uv run python -m projectapp.main`(起動方法は `docs/development.md` に従う)

手順: ネイティブウィンドウの`ファイル`メニュー → `PlantUML を取り込む` → `.puml` を選ぶ。確かめること: 新規プロジェクトとして開く、通知の件数、ガントチャートの日程、`名前をつけて保存`で保存できる、編集中は確認ダイアログが出る。確認用の `.puml` は、スクラッチパッドに作る(例: Task 3 の `SUPPORTED_SYNTAX`)。

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/development.md docs/superpowers/specs/2026-10-16-plantuml-import-design.md
git commit -m "$(cat <<'EOF'
docs: PlantUML 取り込みを仕様と開発者向けメモに反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```
