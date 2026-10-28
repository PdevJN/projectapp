# 設定値のエクスポート・インポート Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プロジェクトの設定値とメンバーの設定値を、専用の設定ファイルに書き出し、別のプロジェクトへ区分ごと・項目ごとに選んで取り込めるようにする。

**Architecture:** 純粋関数のモジュール `settings_io.py` が、書き出し(`build_settings`)・読み込み(`parse_settings`)・取り込み計画(`plan_import`)・適用(`apply_import`)を持つ。ファイルの各要素の変換と検証は、既存の `storage.dumps_project` / `storage.parse_project` に任せる(設定ファイルを「タスクのないプロジェクト」に組み直して読む)。取り込みのダイアログは `settings_dialog.py`。`MainView` は、メニューの項目 2 つと、取り込みの流れ(相対比率の上限・下限の見直し確認、参照方式のスナップショット、`after_edit` 1 回)をつなぐ。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -n auto -q`)、`uvx ty check src`

**Spec:** [`docs/superpowers/specs/2026-10-29-settings-export-import-design.md`](../specs/2026-10-29-settings-export-import-design.md)

## Global Constraints

- 応答・コメント・UI の文言は日本語。コメントは 3 行以内。すべての関数に型ヒント(`.claude/RULE.md`)。
- 設定ファイル: `{"kind": "projectapp-settings", "version": 1, "project_version": <書いたときの FORMAT_VERSION>, ...}`(UTF-8 の JSON)。拡張子 `.json`、既定のファイル名 `settings.json`。
- 含める: プロジェクト設定(`base_date`・`daily_hours`・`work_start`・`actual_mode`・`reference_mode`・`plantuml_overload_notice`・`ratio_limit_upper`・`ratio_limit_lower`)と `members`・`parameters`・`categories`・`url_templates`・`events`。含めない: タスク・セクション・実績・先行・プロジェクト参照。
- 突き合わせの鍵: メンバー・パラメータ・カテゴリ・URL テンプレートは名前(前後の空白を除く)。イベントは `開始日〜終了日 文字列`。イベントの重複は上書きできない(取り込まない)。
- 上書きは既存の `id` を保つ。追加は新しい `id` を振る(`models.new_id(project.used_ids())`)。
- 取り込みは未保存の編集で、元に戻す 1 ステップ(`after_edit` を 1 回)。書き出しはプロジェクトを変えず、変更扱いにもしない。
- ネイティブウィンドウのみ。Web モード(`exporter.available` が偽)ではメニューの項目を出さない。
- 相対比率の上限・下限が変わるときだけ、設定ダイアログと同じ「見直して適用 / 見直さずに適用 / キャンセル」を通す。稼働可能時間の変更に見直しの確認はない(換算率が変わらず、設定ダイアログの `apply_settings` にもない)。
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。push・マージは利用者の許可を得てから。ブランチは `feature/settings-io`(作成済み)。

## Review Focus

- `members` が文字列、メンバーの要素が数値など、形の壊れた設定ファイルで、例外が漏れず `ValueError`(通知)になる(Task 1)。
- 記録方式を `簡易` にする設定を、2 区間以上の実績のあるタスクがあるプロジェクトへ取り込んでも、区間のまま残る(Task 2)。
- 同じイベント(`開始日〜終了日 文字列`)が設定ファイルの中に 2 回あっても、1 件だけ足す(Task 2)。
- 上書きしたメンバー・カテゴリを担当・参照するタスクが、そのまま付いている(`id` を保つ)(Task 2・5)。
- 取り込みで相対比率の上限・下限が変わり、実績のあるタスクがあるとき、`キャンセル`でプロジェクト設定だけが取り消され、ほかの取り込みは残る(Task 5)。

---

### Task 1: 設定ファイルの書き出しと読み込み(`settings_io.py`)

**Files:**
- Create: `src/projectapp/settings_io.py`
- Test: `test/test_settings_io.py`

**Interfaces:**
- Consumes: `storage.dumps_project(project) -> str`、`storage.parse_project(text, name) -> Project`、`handoff.write_json(path, data) -> Path`、`models.FORMAT_VERSION`。
- Produces(後続のタスクが使う):
  - 定数 `SETTINGS_KIND`、`SETTINGS_VERSION`、`SETTINGS_FILE_TYPES: tuple[str, ...]`、`DEFAULT_FILENAME`、`IMPORT_NAME`、`PROJECT_KEYS`、`COLLECTION_KEYS`(`tuple[str, ...]`)、`SECTION_LABELS: dict[str, str]`(キー `project`・`members`・`parameters`・`categories`・`url_templates`・`events` の順)
  - `build_settings(project: Project) -> dict[str, Any]`
  - `write_settings(path: Path, data: dict[str, Any]) -> Path`
  - `@dataclass class ImportFile: project: Project; has_project_settings: bool`
  - `parse_settings(text: str) -> ImportFile`(正しくなければ `ValueError`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_settings_io.py`:

```python
import json
from datetime import date, time
from pathlib import Path

import pytest

from projectapp.models import (
    ActualMode,
    Category,
    Event,
    Level,
    Member,
    Parameter,
    Project,
    ReferenceMode,
    Section,
    Task,
    UrlTemplate,
    WorkDay,
)
from projectapp.settings_io import (
    DEFAULT_FILENAME,
    SETTINGS_FILE_TYPES,
    build_settings,
    parse_settings,
    write_settings,
)


def full_project() -> Project:
    return Project(
        "元",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        work_start=time(10, 0),
        actual_mode=ActualMode.INTERVALS,
        reference_mode=ReferenceMode.SNAPSHOT,
        plantuml_overload_notice=False,
        ratio_limit_upper=1.2,
        ratio_limit_lower=0.8,
        parameters=[Parameter("経験", [Level("初級", -0.2), Level("上級", 0.2)])],
        members=[Member("田中", 1.2, {"経験": "上級"}, work_days=[WorkDay(date(2026, 10, 12), None, None, "休暇")])],
        categories=[Category("開発", kind="業務", color="red", prj_code="PRJ-1")],
        url_templates=[UrlTemplate("チケット", "https://example.com/{ID}")],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "orange", closed=True)],
        sections=[Section("開発", [Task("実装")])],
        tasks=[Task("雑務")],
    )


def test_the_file_names_its_kind_and_leaves_out_the_tasks() -> None:
    data = build_settings(full_project())
    assert data["kind"] == "projectapp-settings" and data["version"] == 1
    assert "tasks" not in data and "sections" not in data
    assert DEFAULT_FILENAME == "settings.json" and SETTINGS_FILE_TYPES == ("JSON ファイル (*.json)",)


def test_the_settings_round_trip_into_a_project_without_tasks() -> None:
    project = full_project()
    loaded = parse_settings(json.dumps(build_settings(project)))
    got = loaded.project
    assert loaded.has_project_settings
    assert (got.base_date, got.daily_hours, got.work_start) == (project.base_date, 7.0, time(10, 0))
    assert (got.actual_mode, got.reference_mode, got.plantuml_overload_notice) == (
        ActualMode.INTERVALS,
        ReferenceMode.SNAPSHOT,
        False,
    )
    assert (got.ratio_limit_upper, got.ratio_limit_lower) == (1.2, 0.8)
    assert got.members == project.members and got.parameters == project.parameters
    assert got.categories == project.categories and got.url_templates == project.url_templates
    assert got.events == project.events
    assert got.members[0].id == project.members[0].id  # 取り込み側で振り直すので、ここでは保つ
    assert got.tasks == [] and got.sections == []


def test_missing_sections_read_as_empty() -> None:
    loaded = parse_settings(json.dumps({"kind": "projectapp-settings", "version": 1, "members": []}))
    assert not loaded.has_project_settings
    assert loaded.project.members == [] and loaded.project.events == []


def test_the_file_is_written_as_json(tmp_path: Path) -> None:
    path = write_settings(tmp_path / "out", build_settings(full_project()))
    assert path.name == "out.json"  # 拡張子がなければ付ける
    assert json.loads(path.read_text(encoding="utf-8"))["kind"] == "projectapp-settings"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]  # 一時ファイルを残さない


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "JSON"),
        ("{", "JSON"),
        ("[]", "設定ファイルではありません"),
        (json.dumps({"kind": "other", "version": 1}), "設定ファイルではありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 2}), "新しい形式"),
        (json.dumps({"kind": "projectapp-settings", "version": 0}), "version"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "project_version": 999}), "project_version"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "members": "abc"}), "リストではありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "members": [1]}), "形式が正しくありません"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "daily_hours": 0}), "稼働可能時間"),
        (json.dumps({"kind": "projectapp-settings", "version": 1, "base_date": "x"}), ""),
    ],
)
def test_a_broken_file_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_settings(text)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_settings_io.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.settings_io`)

- [ ] **Step 3: 実装する**

`src/projectapp/settings_io.py`:

```python
"""プロジェクトの設定値・メンバーの設定値の書き出しと取り込み。NiceGUI には依存しない。"""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from projectapp.handoff import write_json
from projectapp.models import FORMAT_VERSION, Project
from projectapp.storage import dumps_project, parse_project

SETTINGS_KIND = "projectapp-settings"
SETTINGS_VERSION = 1
SETTINGS_FILE_TYPES = ("JSON ファイル (*.json)",)
DEFAULT_FILENAME = "settings.json"
IMPORT_NAME = "設定"  # 読み込みに使う仮のプロジェクト名
PROJECT_KEYS = (
    "base_date",
    "daily_hours",
    "work_start",
    "actual_mode",
    "reference_mode",
    "plantuml_overload_notice",
    "ratio_limit_upper",
    "ratio_limit_lower",
)
COLLECTION_KEYS = ("members", "parameters", "categories", "url_templates", "events")
SECTION_LABELS = {
    "project": "プロジェクト設定",
    "members": "メンバー",
    "parameters": "パラメータ",
    "categories": "カテゴリ",
    "url_templates": "URL テンプレート",
    "events": "イベント",
}


@dataclass
class ImportFile:
    project: Project  # 設定ファイルの中身を載せた、タスクのないプロジェクト
    has_project_settings: bool  # プロジェクト設定のキーが 1 つでもあったか


def build_settings(project: Project) -> dict[str, Any]:
    """設定ファイルの辞書。各要素の形は、プロジェクトファイルの保存と同じ。タスクとセクションは含めない。"""
    raw = json.loads(dumps_project(replace(project, tasks=[], sections=[])))
    data: dict[str, Any] = {"kind": SETTINGS_KIND, "version": SETTINGS_VERSION, "project_version": raw["version"]}
    data.update({key: raw[key] for key in (*PROJECT_KEYS, *COLLECTION_KEYS)})
    return data


def write_settings(path: Path, data: dict[str, Any]) -> Path:
    """設定ファイルを書く。拡張子がなければ .json を付ける。一時ファイル経由。"""
    return write_json(path, data)


def _version(value: Any, label: str, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
        raise ValueError(f"{label} が正しくありません: {value!r}")
    return value


def parse_settings(text: str) -> ImportFile:
    """設定ファイルを読んで検証する。正しくなければ ValueError(何も変えない)。"""
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"JSON として読めません: {exc}") from None
    if not isinstance(raw, dict) or raw.get("kind") != SETTINGS_KIND:
        raise ValueError("プロジェクトの設定ファイルではありません")
    version = raw.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version > SETTINGS_VERSION:
        raise ValueError(f"このアプリより新しい形式です(version {version})。アプリを更新してください")
    _version(version, "version", SETTINGS_VERSION)
    project_version = _version(raw.get("project_version", FORMAT_VERSION), "project_version", FORMAT_VERSION)
    for key in COLLECTION_KEYS:
        if key in raw and not isinstance(raw[key], list):
            raise ValueError(f"{key} がリストではありません")
    body = json.loads(dumps_project(Project(IMPORT_NAME)))  # キーのない区分は、空の既定で読む
    body["version"] = project_version
    body.update({key: raw[key] for key in (*PROJECT_KEYS, *COLLECTION_KEYS) if key in raw})
    try:
        project = parse_project(json.dumps(body), IMPORT_NAME)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("設定ファイルの形式が正しくありません") from exc
    return ImportFile(project, any(key in raw for key in PROJECT_KEYS))
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_settings_io.py -q`
Expected: PASS(すべて)。`match=""` の最後の 1 件は、`ValueError` であれば通る。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/settings_io.py test/test_settings_io.py
git commit -m "feat: 設定ファイルの書き出しと読み込みを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 取り込みの計画と適用(`settings_io.py`)

**Files:**
- Modify: `src/projectapp/settings_io.py`
- Test: `test/test_settings_io.py`

**Interfaces:**
- Consumes: Task 1 の `ImportFile`、`SECTION_LABELS`、`COLLECTION_KEYS`、`parse_settings`、`build_settings`。
- Produces:
  - `@dataclass(frozen=True) class SectionPlan: key: str; new: tuple[str, ...]; duplicates: tuple[str, ...]; overwritable: bool`
  - `@dataclass(frozen=True) class ProjectChange: label: str; now: str; incoming: str`
  - `@dataclass(frozen=True) class ImportPlan: sections: tuple[SectionPlan, ...]; project_changes: tuple[ProjectChange, ...]`
  - `plan_import(current: Project, incoming: ImportFile) -> ImportPlan`
  - `@dataclass class ImportResult: project: Project; counts: dict[str, int]; skipped: int; dropped_levels: int; notes: list[str]`
  - `apply_import(current: Project, incoming: ImportFile, sections: Collection[str], overwrite: Collection[tuple[str, str]]) -> ImportResult`(`current` は変えない。不正なら `ValueError`)。`overwrite` の要素は `(区分のキー, 項目の名前)`。
  - `summary(result: ImportResult) -> str`
  - `copy_into(target: Project, source: Project) -> None`(全フィールドを `target` へ移す。画面が持つ `Project` の参照を保つため)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_settings_io.py` の import に次を足し、末尾にテストを足す:

```python
from projectapp.models import Actual
from datetime import datetime
from projectapp.settings_io import (
    ImportFile,
    ImportPlan,
    ProjectChange,
    SectionPlan,
    apply_import,
    copy_into,
    plan_import,
    summary,
)


def incoming_of(project: Project) -> ImportFile:
    return parse_settings(json.dumps(build_settings(project)))


def test_the_plan_splits_new_items_from_duplicates() -> None:
    current = Project(
        "現", base_date=date(2026, 10, 5), members=[Member("田中")], parameters=[Parameter("経験", [Level("上級", 0.2)])]
    )
    source = Project(
        "入",
        base_date=date(2026, 10, 5),
        daily_hours=7.0,
        members=[Member("田中", 1.5), Member("鈴木")],
        parameters=[Parameter("経験", [Level("上級", 0.3)])],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")],
    )
    plan = plan_import(current, incoming_of(source))
    assert plan == ImportPlan(
        sections=(
            SectionPlan("members", ("鈴木",), ("田中",), True),
            SectionPlan("parameters", (), ("経験",), True),
            SectionPlan("events", ("2026-10-10〜2026-10-12 合宿",), (), False),
        ),
        project_changes=(ProjectChange("稼働可能時間", "6.5h", "7h"),),
    )


def test_a_file_with_nothing_new_makes_an_empty_plan() -> None:
    project = Project("同じ", base_date=date(2026, 10, 5))
    assert plan_import(project, incoming_of(project)) == ImportPlan((), ())


def test_apply_adds_new_items_with_fresh_ids_and_keeps_the_current_ones() -> None:
    current = Project("現", members=[Member("田中", 1.0)], categories=[Category("開発")])
    source = Project(
        "入",
        members=[Member("田中", 1.5), Member("鈴木", 1.1)],
        categories=[Category("開発", color="red"), Category("保守")],
        events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")],
        url_templates=[UrlTemplate("チケット", "https://example.com/{ID}")],
    )
    result = apply_import(current, incoming_of(source), {"members", "categories", "events", "url_templates"}, set())
    members = result.project.members
    assert [(m.name, m.ratio) for m in members] == [("田中", 1.0), ("鈴木", 1.1)]  # 重複は既定でスキップ
    assert [c.name for c in result.project.categories] == ["開発", "保守"]
    assert result.project.categories[0].color == "blue"
    assert [e.text for e in result.project.events] == ["合宿"]
    assert [t.name for t in result.project.url_templates] == ["チケット"]
    all_ids = [x.id for x in (*members, *result.project.categories, *result.project.events)]
    assert len(set(all_ids)) == len(all_ids)
    assert result.counts == {"project": 0, "members": 1, "parameters": 0, "categories": 1, "url_templates": 1, "events": 1}
    assert result.skipped == 2  # 田中と開発
    assert current.members == [Member("田中", 1.0)]  # 元は変えない


def test_apply_overwrites_the_chosen_duplicates_and_keeps_their_ids() -> None:
    current = Project(
        "現",
        members=[Member("田中", 1.0)],
        categories=[Category("開発")],
        parameters=[Parameter("経験", [Level("上級", 0.2)])],
        url_templates=[UrlTemplate("チケット", "https://old/{ID}")],
    )
    member_id, category_id = current.members[0].id, current.categories[0].id
    source = Project(
        "入",
        members=[Member("田中", 1.5, work_days=[WorkDay(date(2026, 10, 12), None, None, "休")])],
        categories=[Category("開発", kind="業務", color="red", prj_code="P-1")],
        parameters=[Parameter("経験", [Level("上級", 0.3)])],
        url_templates=[UrlTemplate("チケット", "https://new/{ID}")],
    )
    overwrite = {("members", "田中"), ("categories", "開発"), ("parameters", "経験"), ("url_templates", "チケット")}
    result = apply_import(current, incoming_of(source), {"members", "categories", "parameters", "url_templates"}, overwrite)
    member, category = result.project.members[0], result.project.categories[0]
    assert (member.id, member.ratio, len(member.work_days)) == (member_id, 1.5, 1)
    assert (category.id, category.kind, category.color, category.prj_code) == (category_id, "業務", "red", "P-1")
    assert result.project.parameters[0].levels == [Level("上級", 0.3)]
    assert result.project.url_templates[0].pattern == "https://new/{ID}"
    assert result.skipped == 0


def test_unchecked_sections_are_left_alone() -> None:
    current = Project("現")
    source = Project("入", members=[Member("鈴木")], parameters=[Parameter("経験", [Level("上級", 0.2)])])
    result = apply_import(current, incoming_of(source), {"parameters"}, set())
    assert result.project.members == [] and [p.name for p in result.project.parameters] == ["経験"]
    assert result.skipped == 0


def test_a_duplicate_event_in_the_file_is_added_once() -> None:
    event = Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")
    source = Project("入", events=[event, Event(date(2026, 10, 10), date(2026, 10, 12), "合宿")])
    result = apply_import(Project("現"), incoming_of(source), {"events"}, set())  # 読込が重複を拒否するなら ImportFile(source, False) を直接作る
    assert len(result.project.events) == 1


def test_a_duplicate_event_is_never_overwritten_or_added() -> None:
    event = Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "red")
    current = Project("現", events=[event])
    source = Project("入", events=[Event(date(2026, 10, 10), date(2026, 10, 12), "合宿", "blue")])
    result = apply_import(current, incoming_of(source), {"events"}, {("events", "2026-10-10〜2026-10-12 合宿")})
    assert [e.color for e in result.project.events] == ["red"] and result.skipped == 1


def test_level_choices_that_no_longer_match_are_dropped_and_counted() -> None:
    current = Project("現", parameters=[Parameter("経験", [Level("上級", 0.2)])], members=[Member("田中", 1.0, {"経験": "上級"})])
    source = Project("入", parameters=[Parameter("経験", [Level("中級", 0.1)])])
    result = apply_import(current, incoming_of(source), {"parameters"}, {("parameters", "経験")})
    assert result.project.members[0].levels == {}
    assert result.dropped_levels == 1


def test_project_settings_are_applied_together() -> None:
    current = Project("現", base_date=date(2026, 10, 5))
    source = Project(
        "入",
        base_date=date(2026, 11, 1),
        daily_hours=7.0,
        work_start=time(10, 0),
        plantuml_overload_notice=False,
        ratio_limit_upper=1.2,
        ratio_limit_lower=0.8,
    )
    result = apply_import(current, incoming_of(source), {"project"}, set())
    got = result.project
    assert (got.base_date, got.daily_hours, got.work_start) == (date(2026, 11, 1), 7.0, time(10, 0))
    assert (got.plantuml_overload_notice, got.ratio_limits.upper, got.ratio_limits.lower) == (False, 1.2, 0.8)
    assert result.counts["project"] == 1


def test_the_simple_record_mode_is_refused_while_a_task_has_several_intervals() -> None:
    task = Task(
        "実装",
        actuals=[
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 10)),
            Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 10)),
        ],
    )
    current = Project("現", actual_mode=ActualMode.INTERVALS, tasks=[task])
    source = Project("入", actual_mode=ActualMode.SIMPLE, daily_hours=7.0)
    result = apply_import(current, incoming_of(source), {"project"}, set())
    assert result.project.actual_mode is ActualMode.INTERVALS and result.project.daily_hours == 7.0
    assert result.notes == ["記録方式は、2 区間以上のタスクがあるため変えませんでした"]


def test_an_invalid_result_raises_and_changes_nothing() -> None:
    current = Project("現", categories=[Category("開発")])
    incoming = incoming_of(Project("入", categories=[Category("保守")]))
    incoming.project.categories[0].color = "nope"  # 読み込み後に壊す(適用後の検証で拾う)
    with pytest.raises(ValueError):
        apply_import(current, incoming, {"categories"}, set())
    assert [c.name for c in current.categories] == ["開発"]


def test_copy_into_moves_every_field_and_keeps_the_target_object() -> None:
    target, source = Project("現"), Project("入", daily_hours=7.0, members=[Member("鈴木")])
    copy_into(target, source)
    assert target.name == "入" and target.daily_hours == 7.0 and [m.name for m in target.members] == ["鈴木"]


def test_the_summary_lists_the_counts_and_the_leftovers() -> None:
    current = Project("現", members=[Member("田中")])
    source = Project("入", members=[Member("田中"), Member("鈴木")], parameters=[Parameter("経験", [Level("上級", 0.2)])])
    result = apply_import(current, incoming_of(source), {"members", "parameters"}, set())
    assert summary(result) == "取り込みました(メンバー 1 件、パラメータ 1 件)。重複 1 件は取り込んでいません"
    empty = apply_import(current, incoming_of(Project("入")), {"members"}, set())
    assert summary(empty) == "取り込む項目はありませんでした"
```

(`from projectapp.models import Actual` と `datetime` の import は、ファイル先頭の import にまとめる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_settings_io.py -q`
Expected: FAIL(`ImportError: cannot import name 'apply_import'` など)

- [ ] **Step 3: 実装する**

`src/projectapp/settings_io.py` の import を次に置き換え、末尾に実装を足す:

```python
import json
from collections.abc import Collection
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from projectapp.handoff import write_json
from projectapp.models import (
    FORMAT_VERSION,
    ActualMode,
    Category,
    Event,
    Member,
    Parameter,
    Project,
    ReferenceMode,
    UrlTemplate,
    new_id,
)
from projectapp.storage import dumps_project, parse_project
```

```python
Item = Member | Parameter | Category | UrlTemplate | Event


@dataclass(frozen=True)
class SectionPlan:
    key: str
    new: tuple[str, ...]  # 開いているプロジェクトにない項目(追加する)
    duplicates: tuple[str, ...]  # すでにある項目(上書きかスキップ)
    overwritable: bool  # False(イベント)は、重複を上書きできず、取り込まない


@dataclass(frozen=True)
class ProjectChange:
    label: str
    now: str
    incoming: str


@dataclass(frozen=True)
class ImportPlan:
    sections: tuple[SectionPlan, ...]
    project_changes: tuple[ProjectChange, ...]


@dataclass
class ImportResult:
    project: Project  # 取り込み後の新しいプロジェクト(元は変えない)
    counts: dict[str, int]  # 区分 → 追加か上書きした件数(プロジェクト設定は 0 か 1)
    skipped: int  # 重複のため取り込まなかった件数
    dropped_levels: int  # 合わなくなって外した、メンバーの段階の選択
    notes: list[str]


def item_key(item: Item) -> str:
    """突き合わせの鍵。イベントは期間と文字列、それ以外は名前。"""
    if isinstance(item, Event):
        return f"{item.start.isoformat()}〜{item.end.isoformat()} {item.text}"
    return item.name.strip()


def _describe(project: Project) -> dict[str, str]:
    def ratio(value: float | None) -> str:
        return "設定なし" if value is None else f"{value:.0%}"

    modes = {ActualMode.SIMPLE: "簡易", ActualMode.INTERVALS: "区間"}
    refs = {ReferenceMode.LIVE: "常に最新", ReferenceMode.SNAPSHOT: "スナップショット"}
    return {
        "基準日": project.base_date.isoformat(),
        "稼働可能時間": f"{project.daily_hours:g}h",
        "始業時刻": project.work_start.strftime("%H:%M"),
        "実績の記録方式": modes[project.actual_mode],
        "プロジェクト参照の方式": refs[project.reference_mode],
        "PlantUML の通知": "出す" if project.plantuml_overload_notice else "出さない",
        "相対比率の上限": ratio(project.ratio_limit_upper),
        "相対比率の下限": ratio(project.ratio_limit_lower),
    }


def project_changes(current: Project, incoming: Project) -> tuple[ProjectChange, ...]:
    now, then = _describe(current), _describe(incoming)
    return tuple(ProjectChange(label, now[label], then[label]) for label in now if now[label] != then[label])


def plan_import(current: Project, incoming: ImportFile) -> ImportPlan:
    """取り込む内容を、区分ごとの追加・重複と、プロジェクト設定の違いにまとめる。何も変えない。"""
    sections: list[SectionPlan] = []
    for key in COLLECTION_KEYS:
        mine = {item_key(item) for item in getattr(current, key)}
        new: list[str] = []
        duplicates: list[str] = []
        seen: set[str] = set()
        for item in getattr(incoming.project, key):
            name = item_key(item)
            if name in seen:
                continue
            seen.add(name)
            (duplicates if name in mine else new).append(name)
        if new or duplicates:
            sections.append(SectionPlan(key, tuple(new), tuple(duplicates), key != "events"))
    changes = project_changes(current, incoming.project) if incoming.has_project_settings else ()
    return ImportPlan(tuple(sections), changes)


def _overwrite(target: Item, item: Item) -> None:
    """重複の項目を、取り込む値で置き換える。名前と id は保つ。"""
    if isinstance(target, Member) and isinstance(item, Member):
        target.ratio, target.levels, target.icon, target.work_days = item.ratio, item.levels, item.icon, item.work_days
    elif isinstance(target, Parameter) and isinstance(item, Parameter):
        target.levels = item.levels
    elif isinstance(target, Category) and isinstance(item, Category):
        target.kind, target.expiry_date, target.color, target.prj_code = (
            item.kind,
            item.expiry_date,
            item.color,
            item.prj_code,
        )
    elif isinstance(target, UrlTemplate) and isinstance(item, UrlTemplate):
        target.pattern = item.pattern


def _merge(work: Project, source: Project, key: str, overwrite: Collection[tuple[str, str]], result: ImportResult) -> None:
    mine = {item_key(item): item for item in getattr(work, key)}
    seen: set[str] = set()
    for item in getattr(source, key):
        name = item_key(item)
        if name in seen:
            continue
        seen.add(name)
        target = mine.get(name)
        if target is None:
            if isinstance(item, Member | Category | Event):
                item.id = new_id(work.used_ids())
            getattr(work, key).append(item)
            result.counts[key] += 1
        elif key != "events" and (key, name) in overwrite:
            _overwrite(target, item)
            result.counts[key] += 1
        else:
            result.skipped += 1


def _apply_project_settings(work: Project, source: Project, result: ImportResult) -> None:
    work.base_date, work.daily_hours, work.work_start = source.base_date, source.daily_hours, source.work_start
    work.reference_mode = source.reference_mode
    work.plantuml_overload_notice = source.plantuml_overload_notice
    work.ratio_limit_upper, work.ratio_limit_lower = source.ratio_limit_upper, source.ratio_limit_lower
    if source.actual_mode is ActualMode.SIMPLE and any(len(task.actuals) > 1 for task in work.all_tasks()):
        result.notes.append("記録方式は、2 区間以上のタスクがあるため変えませんでした")
    else:
        work.actual_mode = source.actual_mode
    if work.reference_mode is ReferenceMode.LIVE:  # 常に最新は、スナップショットを持たない
        for task in work.all_tasks():
            task.ref_snapshot = None


def _drop_stale_levels(work: Project) -> int:
    levels = {parameter.name: {level.name for level in parameter.levels} for parameter in work.parameters}
    dropped = 0
    for member in work.members:
        kept = {name: level for name, level in member.levels.items() if level in levels.get(name, set())}
        dropped += len(member.levels) - len(kept)
        member.levels = kept
    return dropped


def apply_import(
    current: Project,
    incoming: ImportFile,
    sections: Collection[str],
    overwrite: Collection[tuple[str, str]],
) -> ImportResult:
    """選んだ区分を取り込んだ、新しいプロジェクトを返す。current は変えない。結果が読み込みの検証を通らなければ ValueError。"""
    work, source = deepcopy(current), deepcopy(incoming.project)
    result = ImportResult(work, dict.fromkeys(SECTION_LABELS, 0), 0, 0, [])
    for key in COLLECTION_KEYS:
        if key in sections:
            _merge(work, source, key, overwrite, result)
    if "project" in sections and incoming.has_project_settings:
        _apply_project_settings(work, source, result)
        result.counts["project"] = 1 if project_changes(current, work) else 0
    result.dropped_levels = _drop_stale_levels(work)
    parse_project(dumps_project(work), work.name)  # 保存・読込と同じ検証。通らなければ ValueError
    return result


def summary(result: ImportResult) -> str:
    done = [
        SECTION_LABELS[key] if key == "project" else f"{SECTION_LABELS[key]} {count} 件"
        for key, count in result.counts.items()
        if count
    ]
    head = f"取り込みました({'、'.join(done)})" if done else "取り込む項目はありませんでした"
    extras = [
        *([f"重複 {result.skipped} 件は取り込んでいません"] if result.skipped else []),
        *([f"合わない段階の選択 {result.dropped_levels} 件を外しました"] if result.dropped_levels else []),
        *result.notes,
    ]
    return head + (f"。{'、'.join(extras)}" if extras else "")


def copy_into(target: Project, source: Project) -> None:
    """source の全フィールドを target へ移す(画面が持つ Project の参照を保つ)。"""
    for field in fields(Project):
        setattr(target, field.name, getattr(source, field.name))
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_settings_io.py -q && uvx ty check src`
Expected: PASS、`ty` は通過。`isinstance(item, Member | Category | Event)` で `ty` が不満を出したら、タプル `(Member, Category, Event)` に直す。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/settings_io.py test/test_settings_io.py
git commit -m "feat: 設定の取り込みの計画と適用を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 取り込みのダイアログ(`settings_dialog.py`)

**Files:**
- Create: `src/projectapp/settings_dialog.py`
- Test: `test/test_settings_dialog.py`

**Interfaces:**
- Consumes: `settings_io.ImportPlan`・`SectionPlan`・`ProjectChange`・`SECTION_LABELS`、`forms.disposable`。
- Produces: `open_import_dialog(plan: ImportPlan, on_apply: Callable[[set[str], set[tuple[str, str]]], object]) -> None`。`on_apply(選んだ区分のキー, 上書きする(区分, 名前))` を、`取り込む` で 1 回呼んでダイアログを閉じる。マーカー: `import-section-<key>`(`project` を含む)、`import-overwrite-<key>-<index>`(重複の並び順)、`import-apply`、`import-cancel`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_settings_dialog.py`:

```python
from nicegui import ui
from nicegui.testing import User

from projectapp.settings_dialog import open_import_dialog
from projectapp.settings_io import ImportPlan, ProjectChange, SectionPlan

PLAN = ImportPlan(
    sections=(
        SectionPlan("members", ("鈴木",), ("田中", "佐藤"), True),
        SectionPlan("events", (), ("2026-10-10〜2026-10-12 合宿",), False),
    ),
    project_changes=(ProjectChange("稼働可能時間", "6.5h", "7h"),),
)


def mount(calls: list[tuple]) -> None:
    @ui.page("/")
    def index() -> None:
        open_import_dialog(PLAN, lambda sections, overwrite: calls.append((sections, overwrite)))


def element(user: User, marker: str) -> ui.element:
    return next(iter(user.find(marker=marker).elements))


async def test_the_dialog_lists_the_sections_and_the_project_changes(user: User) -> None:
    mount([])
    await user.open("/")
    await user.should_see("メンバー(追加 1 件・重複 2 件)")
    await user.should_see("稼働可能時間: 6.5h → 7h")
    await user.should_see("追加: 鈴木")
    await user.should_see("重複(取り込みません): 2026-10-10〜2026-10-12 合宿")
    assert element(user, "import-section-project").value
    assert element(user, "import-section-members").value
    assert not element(user, "import-overwrite-members-0").value  # 既定はスキップ


async def test_apply_passes_the_checked_sections_and_overwrites(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="import-section-events").click()  # events を外す
    user.find(marker="import-overwrite-members-1").click()  # 佐藤を上書き
    user.find(marker="import-apply").click()
    assert calls == [({"project", "members"}, {("members", "佐藤")})]


async def test_cancel_calls_nothing(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="import-cancel").click()
    assert calls == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_settings_dialog.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.settings_dialog`)

- [ ] **Step 3: 実装する**

`src/projectapp/settings_dialog.py`:

```python
"""設定の取り込みのダイアログ。区分ごとのチェックと、重複の項目ごとの上書きを選ばせる。"""

from collections.abc import Callable

from nicegui import ui

from projectapp.forms import disposable
from projectapp.settings_io import SECTION_LABELS, ImportPlan


def open_import_dialog(plan: ImportPlan, on_apply: Callable[[set[str], set[tuple[str, str]]], object]) -> None:
    sections: dict[str, ui.checkbox] = {}
    overwrites: dict[tuple[str, str], ui.checkbox] = {}
    with disposable(ui.dialog()) as dialog, ui.card().classes("w-[32rem]"):
        ui.label("設定を取り込む").classes("text-h6")
        with ui.column().classes("w-full gap-0"):
            if plan.project_changes:
                sections["project"] = ui.checkbox(SECTION_LABELS["project"], value=True).mark("import-section-project")
                for change in plan.project_changes:
                    ui.label(f"{change.label}: {change.now} → {change.incoming}").classes("text-caption q-ml-lg")
            for section in plan.sections:
                title = f"{SECTION_LABELS[section.key]}(追加 {len(section.new)} 件・重複 {len(section.duplicates)} 件)"
                sections[section.key] = ui.checkbox(title, value=True).mark(f"import-section-{section.key}")
                for name in section.new:
                    ui.label(f"追加: {name}").classes("text-caption q-ml-lg")
                for index, name in enumerate(section.duplicates):
                    if section.overwritable:
                        overwrites[(section.key, name)] = (
                            ui.checkbox(f"上書き: {name}").classes("q-ml-lg").mark(f"import-overwrite-{section.key}-{index}")
                        )
                    else:
                        ui.label(f"重複(取り込みません): {name}").classes("text-caption q-ml-lg")

        def apply() -> None:
            chosen = {key for key, box in sections.items() if box.value}
            picked = {pair for pair, box in overwrites.items() if box.value}
            dialog.close()
            on_apply(chosen, picked)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("import-cancel")
            ui.button("取り込む", on_click=apply).mark("import-apply")
    dialog.open()
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_settings_dialog.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/settings_dialog.py test/test_settings_dialog.py
git commit -m "feat: 設定の取り込みのダイアログを足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `エクスポート`メニューに`設定を書き出す`

**Files:**
- Modify: `src/projectapp/views.py`(import 追加、`export_tsv` の直後にメソッド、`エクスポート`メニュー)
- Test: `test/test_views.py`(メニューの既存テスト 2 件の期待値と、新しいテスト)

**Interfaces:**
- Consumes: `settings_io.build_settings`・`write_settings`・`SETTINGS_FILE_TYPES`・`DEFAULT_FILENAME`、`exporter.ask_path(filename, types)`、`HANDOFF_NOT_NATIVE_MESSAGE`。
- Produces: `MainView.export_settings()`(async)、メニューのマーカー `export-settings`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の既存のメニューのテストを直す:
- `test_the_menus_list_their_items_in_order` の `menu_icons(user, "menu-export-items")` を `["visibility", "ios_share", "download", "save_alt"]` に、`menu_items(user, "menu-export-items")` の末尾に `("設定を書き出す", "export-settings")` を足す。

import に `from projectapp.settings_io import DEFAULT_FILENAME as SETTINGS_DEFAULT_FILENAME, SETTINGS_FILE_TYPES` を足し、`test_export_tsv_needs_the_native_window` の直後に足す:

```python
async def test_export_settings_writes_the_file_without_touching_the_project(user: User, tmp_path: Path) -> None:
    target = tmp_path / "out" / "settings.json"
    target.parent.mkdir()
    exporter = FakeExporter(path=target)
    view = await open_for_import(user, tmp_path, exporter)
    view.project.members = [Member("田中", 1.2)]
    dirty = view.is_dirty()
    user.find(marker="export-settings").click()
    assert await wait_until(target.exists)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["kind"] == "projectapp-settings" and [m["name"] for m in data["members"]] == ["田中"]
    assert exporter.asked == [SETTINGS_DEFAULT_FILENAME] and exporter.asked_types == [SETTINGS_FILE_TYPES]
    assert view.is_dirty() == dirty and view.project.members == [Member("田中", 1.2)]
    await user.should_see("書き出しました")


async def test_cancelling_the_settings_save_dialog_writes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=None)
    await open_for_import(user, tmp_path, exporter)
    user.find(marker="export-settings").click()
    assert await wait_until(lambda: exporter.asked != [])
    assert not list(tmp_path.glob("settings*.json"))


async def test_the_settings_export_item_is_hidden_without_the_native_window(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(path=tmp_path / "x.json", available=False)
    await open_for_import(user, tmp_path, exporter)
    await user.should_see(marker="export-tsv")
    await user.should_not_see(marker="export-settings")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "export_settings or settings_export or settings_save or menus_list"`
Expected: FAIL(メニューに項目がない)

- [ ] **Step 3: 実装する**

`views.py` の import(`from projectapp.csv_import import ...` の近く)に追加:

```python
from projectapp.settings_io import DEFAULT_FILENAME as SETTINGS_DEFAULT_FILENAME
from projectapp.settings_io import SETTINGS_FILE_TYPES, build_settings, write_settings
```

`export_tsv` の直後にメソッドを足す:

```python
    async def export_settings(self) -> None:
        """設定値(プロジェクト設定・メンバー・パラメータなど)を書き出す。プロジェクトは変えない(保存も、変更扱いもしない)。"""
        if not self.exporter.available:
            ui.notify(HANDOFF_NOT_NATIVE_MESSAGE, type="warning")
            return
        path = await self.exporter.ask_path(SETTINGS_DEFAULT_FILENAME, SETTINGS_FILE_TYPES)
        if path is None:
            return
        try:
            written = write_settings(path, build_settings(self.project))
        except (OSError, ValueError) as exc:
            ui.notify(f"保存できませんでした: {exc}", type="negative")
            return
        ui.notify(f"書き出しました({written.name})")
```

`エクスポート`メニューの項目(`MenuItem("TSV として書き出す", ...)`)の後に、Web では出さない形で足す:

```python
                    *(
                        [MenuItem("設定を書き出す", "save_alt", self.export_settings, "export-settings")]
                        if self.exporter.available
                        else []
                    ),
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_views.py -q -k "export_settings or settings_export or settings_save or menus_list or header"`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: エクスポートメニューに設定を書き出す項目を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `ファイル`メニューに`設定を取り込む`

**Files:**
- Modify: `src/projectapp/views.py`
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 1〜3 の `parse_settings`・`plan_import`・`apply_import`・`summary`・`copy_into`・`ImportFile`・`ImportResult`・`open_import_dialog`、既存の `reassign.limit_reviews`・`take_snapshot`。
- Produces(`MainView`): `request_import_settings()`、`async import_settings()`、`apply_settings_import(incoming, sections, overwrite)`、`commit_settings_import(result, ends=None)`、`ask_limit_review(count, on_choice, cancel_message)`(`apply_ratio_limits` と共有)、`refresh_all_snapshots()`(`apply_reference_mode` と共有)。メニューのマーカー `file-import-settings`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の既存テストを直す:
- `test_the_menus_list_their_items_in_order`: `menu_items(user, "menu-file-items")` の `("CSV を取り込む", ...)` の次に `("設定を取り込む", "file-import-settings")`、`menu_icons(... "menu-file-items")` の `"table_view"` の次に `"settings_backup_restore"`。
- `test_the_file_menu_separates_open_save_and_update`: `kinds` を `["item", "item", "item", "item", "item", "sep", "item", "item", "sep", "item", "item"]` に。

import に追加: `from projectapp.settings_io import build_settings, parse_settings, write_settings`(Task 4 の import に合流)。`test_export_settings_...` 群の後に足す:

```python
def write_settings_file(tmp_path: Path, project: Project, name: str = "in.json") -> Path:
    folder = tmp_path / "other"
    folder.mkdir(exist_ok=True)
    return write_settings(folder / name, build_settings(project))


def incoming_file(project: Project):
    return parse_settings(json.dumps(build_settings(project)))


async def test_import_settings_adds_the_items_in_one_undoable_unsaved_edit(user: User, tmp_path: Path) -> None:
    source = Project("元", members=[Member("鈴木", 1.1)], parameters=[Parameter("経験", [Level("上級", 0.2)])])
    exporter = FakeExporter(open_path=write_settings_file(tmp_path, source))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-settings").click()
    await user.should_see(marker="import-apply")
    user.find(marker="import-apply").click()
    assert await wait_until(lambda: [m.name for m in view.project.members] == ["鈴木"])
    assert [p.name for p in view.project.parameters] == ["経験"] and view.is_dirty()
    assert view.project.name == "新規プロジェクト"  # 置き換えない
    assert exporter.asked_open == [SETTINGS_FILE_TYPES]
    await user.should_see("取り込みました(メンバー 1 件、パラメータ 1 件)")
    view.undo()
    assert view.project.members == [] and view.project.parameters == [] and not view.is_dirty()


async def test_import_settings_skips_a_duplicate_unless_it_is_overwritten(user: User, tmp_path: Path) -> None:
    source = Project("元", members=[Member("田中", 1.5)])
    exporter = FakeExporter(open_path=write_settings_file(tmp_path, source))
    view = await open_for_import(user, tmp_path, exporter)
    view.project.members = [Member("田中", 1.0)]
    member_id = view.project.members[0].id
    user.find(marker="file-import-settings").click()
    await user.should_see(marker="import-overwrite-members-0")
    user.find(marker="import-overwrite-members-0").click()
    user.find(marker="import-apply").click()
    assert await wait_until(lambda: view.project.members[0].ratio == 1.5)
    assert view.project.members[0].id == member_id and len(view.project.members) == 1


async def test_an_unchecked_section_is_not_imported(user: User, tmp_path: Path) -> None:
    source = Project("元", members=[Member("鈴木")], parameters=[Parameter("経験", [Level("上級", 0.2)])])
    exporter = FakeExporter(open_path=write_settings_file(tmp_path, source))
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-settings").click()
    await user.should_see(marker="import-section-members")
    user.find(marker="import-section-members").click()
    user.find(marker="import-apply").click()
    assert await wait_until(lambda: view.project.parameters != [])
    assert view.project.members == []


async def test_cancelling_the_file_dialog_or_the_import_dialog_changes_nothing(user: User, tmp_path: Path) -> None:
    exporter = FakeExporter(open_path=None)
    view = await open_for_import(user, tmp_path, exporter)
    user.find(marker="file-import-settings").click()
    assert await wait_until(lambda: exporter.asked_open != [])
    assert not view.is_dirty()
    exporter.open_path = write_settings_file(tmp_path, Project("元", members=[Member("鈴木")]))
    user.find(marker="file-import-settings").click()
    await user.should_see(marker="import-cancel")
    user.find(marker="import-cancel").click()
    assert view.project.members == [] and not view.is_dirty()


async def test_a_broken_settings_file_is_refused_with_a_notice(user: User, tmp_path: Path) -> None:
    folder = tmp_path / "other"
    folder.mkdir()
    broken = folder / "bad.json"
    broken.write_text('{"kind": "projectapp-settings", "version": 1, "members": "abc"}', encoding="utf-8")
    view = await open_for_import(user, tmp_path, FakeExporter(open_path=broken))
    user.find(marker="file-import-settings").click()
    await user.should_see("取り込めませんでした")
    assert view.project.members == [] and not view.is_dirty()


async def test_a_file_with_nothing_to_import_says_so(user: User, tmp_path: Path) -> None:
    view = await open_for_import(user, tmp_path, FakeExporter(open_path=write_settings_file(tmp_path, Project("元"))))
    user.find(marker="file-import-settings").click()
    await user.should_see("取り込める項目がありません")
    assert not view.is_dirty()


async def test_the_settings_import_item_is_hidden_without_the_native_window(user: User, tmp_path: Path) -> None:
    await open_for_import(user, tmp_path, FakeExporter(available=False))
    await user.should_see(marker="file-import-plantuml")
    await user.should_not_see(marker="file-import-settings")


async def test_import_with_changed_limits_asks_and_cancel_keeps_only_the_other_items(user: User, tmp_path: Path) -> None:
    view = await _open_existing(user, tmp_path, _progress_project())
    source = Project("元", ratio_limit_upper=1.0, members=[Member("鈴木")])
    view.apply_settings_import(incoming_file(source), {"project", "members"}, set())
    await user.should_see("見直して適用")
    assert view.project.ratio_limit_upper is None and len(view.project.members) == 1  # 確認の前は変わらない
    user.find(marker="limit-review-cancel").click()
    assert await wait_until(lambda: len(view.project.members) == 2)
    assert view.project.ratio_limit_upper is None  # プロジェクト設定だけ取り消す
    await user.should_see("プロジェクト設定は取り込みませんでした")


async def test_import_with_changed_limits_can_review_the_planned_end(user: User, tmp_path: Path) -> None:
    view = await _open_existing(user, tmp_path, _progress_project())
    view.apply_settings_import(incoming_file(Project("元", ratio_limit_upper=1.0)), {"project"}, set())
    user.find(marker="limit-review-apply").click()
    assert await wait_until(lambda: view.project.ratio_limit_upper == 1.0)
    assert view.project.all_tasks()[0].planned_end_manual is True
    view.undo()
    assert view.project.ratio_limit_upper is None and not view.project.all_tasks()[0].planned_end_manual


async def test_import_keeps_the_task_assignment_when_a_member_is_overwritten(user: User, tmp_path: Path) -> None:
    view = await _open_existing(user, tmp_path, _progress_project())
    source = Project("元", members=[Member("田中", 1.4)])
    view.apply_settings_import(incoming_file(source), {"members"}, {("members", "田中")})
    assert [a.name for a in view.project.all_tasks()[0].assignees] == ["田中"]
    assert view.project.members[0].ratio == 1.4


async def test_import_switching_to_snapshot_retakes_the_snapshots(user: User, tmp_path: Path, monkeypatch) -> None:
    view = await _open_existing(user, tmp_path, Project("既存"))
    calls: list[ReferenceMode] = []
    monkeypatch.setattr(view, "refresh_all_snapshots", lambda: calls.append(view.project.reference_mode))
    view.apply_settings_import(incoming_file(Project("元", reference_mode=ReferenceMode.SNAPSHOT)), {"project"}, set())
    assert calls == [ReferenceMode.SNAPSHOT] and view.project.reference_mode is ReferenceMode.SNAPSHOT
```

注: `_progress_project()` の担当者は `田中`(基本比率 1.0、パラメータ 3 件の段階「高」+50% ずつ)。`test_import_with_changed_limits_*` は `limit_reviews` が 1 件を返す前提(既存の `apply_ratio_limits` のテストと同じ状況)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "import_settings or settings_import or settings_file or import_with_changed or import_keeps or import_switching or broken_settings or nothing_to_import or menus_list or file_menu_separates or cancelling_the_file"`
Expected: FAIL(項目・メソッドがない)

- [ ] **Step 3: 実装する**

(a) `views.py` の import に追加(Task 4 の行を拡張):

```python
from projectapp.settings_dialog import open_import_dialog
from projectapp.settings_io import ImportFile, ImportResult, apply_import, copy_into, parse_settings, plan_import
from projectapp.settings_io import summary as settings_import_summary
```

(`replace` は `dataclasses` から、`limit_reviews` は `projectapp.reassign` から、すでに import 済みなら足さない。なければ足す。)

(b) 見直し確認のダイアログを `apply_ratio_limits` から取り出す。`apply_ratio_limits` を次に置き換える:

```python
    def apply_ratio_limits(self, limits: RatioLimits) -> None:
        """相対比率の下限・上限を変える。実績か進捗のあるタスクの完了予定が変わるときは、見直しを選ばせる。"""
        if limits == self.project.ratio_limits:
            return
        reviews = limit_reviews(self.project, limits, self.holidays, datetime.now())

        def commit(review: bool) -> None:
            if review:
                for task, end in reviews:
                    task.planned_end, task.planned_end_manual = end, True
            self.project.ratio_limit_upper, self.project.ratio_limit_lower = limits.upper, limits.lower
            self.after_edit()

        if not reviews:
            commit(False)
            return
        self.ask_limit_review(
            len(reviews), lambda review: commit(review) if review is not None else None, "上限・下限は変更しませんでした"
        )

    def ask_limit_review(self, count: int, on_choice: Callable[[bool | None], None], cancel_message: str) -> None:
        """相対比率の上限・下限の変更で完了予定を見直すかを選ばせる。見直す=True・見直さない=False・キャンセル=None で on_choice を 1 回呼ぶ。"""
        with self.client, ui.dialog() as dialog, ui.card():  # 設定ダイアログの中で作ると、それが閉じるときに一緒に消える
            ui.label(
                f"上限・下限の変更で、実績か進捗のある {count} 件のタスクの換算率が変わります。\n"
                "残りの作業を新しい条件で見直して、完了予定を手で指定の値にしますか。"
            ).classes("whitespace-pre-line")

            decided = [False]

            def choose(review: bool) -> None:
                decided[0] = True
                dialog.close()
                on_choice(review)

            def cancel() -> None:
                """ほかの設定は適用済みなので、制限だけが未適用と知らせる(外側クリックと ESC も同じ)。"""
                if not decided[0]:
                    decided[0] = True
                    ui.notify(cancel_message)
                    on_choice(None)
                dialog.close()

            dialog.on("hide", cancel)

            with ui.row():
                ui.button("見直して適用", on_click=lambda: choose(True)).mark("limit-review-apply")
                ui.button("見直さずに適用", on_click=lambda: choose(False)).props("flat").mark("limit-review-skip")
                ui.button("キャンセル", on_click=cancel).props("flat").mark("limit-review-cancel")
        dialog.open()
```

(c) スナップショットの取り直しを取り出す。`apply_reference_mode` を次に置き換える:

```python
    def apply_reference_mode(self, mode: ReferenceMode) -> None:
        """参照の方式を変える。スナップショットへは全参照行のスナップショットをそのとき取り、常に最新へは捨てる。保存はしない。"""
        if mode is self.project.reference_mode:
            return
        self.project.reference_mode = mode
        self.refresh_all_snapshots()
        self.after_edit()

    def refresh_all_snapshots(self) -> None:
        """全参照行のスナップショットを方式に合わせて取り直す(スナップショットは取得、常に最新は捨てる)。"""
        now = datetime.now()
        snapshot = self.project.reference_mode is ReferenceMode.SNAPSHOT
        for task in self.project.all_tasks():
            if task.kind is TaskKind.REFERENCE:
                task.ref_snapshot = take_snapshot(self.reference_resolver, task.ref_project, now) if snapshot else None
```

(d) `pick_csv` の近く(`export_settings` の前)に取り込みの流れを足す:

```python
    def request_import_settings(self) -> None:
        """設定の取り込みを始める(ネイティブのみ)。プロジェクトは置き換えず、今のプロジェクトへ足すので、編集中でも確認しない。"""
        if not self.exporter.available:
            ui.notify(IMPORT_NOT_NATIVE_MESSAGE, type="warning")
            return
        with self.client:  # `pick_csv` と同じ理由で、タイマーは画面の直下に置く
            ui.timer(0, self.import_settings, once=True)

    async def import_settings(self) -> None:
        """選んだ設定ファイルを読み、取り込みのダイアログを開く。失敗したら、通知だけして何も変えない。"""
        path = await self.exporter.ask_open_path(SETTINGS_FILE_TYPES)
        if path is None:
            return
        try:
            incoming = parse_settings(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # UnicodeDecodeError は ValueError
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        plan = plan_import(self.project, incoming)
        if not plan.sections and not plan.project_changes:
            ui.notify("取り込める項目がありません")
            return
        with self.client:
            open_import_dialog(plan, lambda sections, overwrite: self.apply_settings_import(incoming, sections, overwrite))

    def apply_settings_import(self, incoming: ImportFile, sections: set[str], overwrite: set[tuple[str, str]]) -> None:
        """選んだ内容を取り込む。相対比率の上限・下限が変わり、見直しが要るタスクがあるときは、先に選ばせる。"""
        try:
            result = apply_import(self.project, incoming, sections, overwrite)
        except ValueError as exc:
            ui.notify(f"取り込めませんでした: {exc}", type="negative")
            return
        old, new = self.project.ratio_limits, result.project.ratio_limits
        reviews: list[tuple[Task, datetime]] = []
        if new != old:
            before = replace(result.project, ratio_limit_upper=old.upper, ratio_limit_lower=old.lower)
            reviews = limit_reviews(before, new, self.holidays, datetime.now())
        if not reviews:
            self.commit_settings_import(result)
            return
        ends = {task.id: end for task, end in reviews}

        def choose(review: bool | None) -> None:
            if review is None:  # キャンセルは、プロジェクト設定の反映だけを取り消す
                self.apply_settings_import(incoming, sections - {"project"}, overwrite)
            else:
                self.commit_settings_import(result, ends if review else None)

        self.ask_limit_review(len(reviews), choose, "プロジェクト設定は取り込みませんでした")

    def commit_settings_import(self, result: ImportResult, ends: dict[str, datetime] | None = None) -> None:
        """取り込み後のプロジェクトを今のプロジェクトへ移し、1 回の編集として確定する。"""
        for task in result.project.all_tasks():
            if ends and task.id in ends:
                task.planned_end, task.planned_end_manual = ends[task.id], True
        mode_changed = result.project.reference_mode is not self.project.reference_mode
        copy_into(self.project, result.project)
        if mode_changed:
            self.refresh_all_snapshots()
        self.after_edit()
        ui.notify(settings_import_summary(result))
```

(`Task` が `views.py` で未 import なら `from projectapp.models import ... Task` に足す。)

注意: `ask_limit_review` は、キャンセルで `cancel_message` を通知したあと `on_choice(None)` を呼ぶ。`apply_ratio_limits` 側は従来どおり `上限・下限は変更しませんでした`、取り込み側は `プロジェクト設定は取り込みませんでした`。

(e) `ファイル`メニューの `CSV を取り込む` の項目の後に、Web では出さない形で足す:

```python
                    *(
                        [MenuItem("設定を取り込む", "settings_backup_restore", self.request_import_settings, "file-import-settings")]
                        if self.exporter.available
                        else []
                    ),
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_views.py test/test_settings_io.py test/test_settings_dialog.py -q -n auto && uvx ty check src`
Expected: PASS(既存の `apply_ratio_limits` / `apply_reference_mode` のテストも通ること)。`ty` は通過。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: ファイルメニューに設定を取り込む項目を足す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 仕様・開発メモ・記録の更新と全体確認

**Files:**
- Modify: `CLAUDE.md`(プロジェクトの `projectapp/CLAUDE.md`)、`docs/development.md`、`docs/superpowers/specs/2026-10-29-settings-export-import-design.md`、`docs/superpowers/README.md`、`docs/requests.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

- 「ヘッダー」の `ファイル`メニューの一覧で、`CSV を取り込む` の次に `設定を取り込む` を、`エクスポート`メニューの一覧で、`TSV として書き出す` の次に `設定を書き出す` を足す。
- 「CSV の取り込みと TSV の書き出し」の節の後に、次の節を足す:

```markdown
## 設定値のエクスポート・インポート

- `エクスポート`メニューの`設定を書き出す`で、プロジェクト設定(基準日・稼働可能時間・始業時刻・実績の記録方式・参照の方式・PlantUML の通知・相対比率の上限と下限)と、メンバー(稼働日の上書き・アイコン・段階の選択を含む)・パラメータ・カテゴリ・URL テンプレート・イベントを、`settings.json`(`kind: "projectapp-settings"`・`version: 1`・`project_version`)に書き出す(ネイティブウィンドウのみ。Web モードでは項目を出さない)。タスク・セクション・実績は含めない。プロジェクトは変えず、変更扱いにもしない
- `ファイル`メニューの`設定を取り込む`で、設定ファイルを選び、取り込みのダイアログで、区分(プロジェクト設定・メンバー・パラメータ・カテゴリ・URL テンプレート・イベント)ごとにチェックし、重複(同じ名前。イベントは期間と文字列)の項目ごとに`上書き`を選ぶ(既定はスキップ。イベントの重複は取り込まない)。新しい項目は追加し、新しい`id`を振る。上書きは既存の`id`を保つ。編集中でも確認なしで今のプロジェクトへ足す
- 取り込み後、合わなくなったメンバーの段階の選択は外して件数を通知する。2 区間以上のタスクがあるあいだは、記録方式を簡易にしない(通知する)。参照の方式をスナップショットにしたときは、全参照行のスナップショットを取る。相対比率の上限・下限が変わって、見直しが要るタスクがあるときは、設定ダイアログと同じ`見直して適用`・`見直さずに適用`・`キャンセル`を出す(キャンセルはプロジェクト設定の取り込みだけを取り消す)。結果は保存・読込と同じ検証を通し、通らなければ取り込まない
- 取り込みは未保存の編集で、元に戻す 1 ステップ。設定ファイルは 3 者マージの対象外
```

- [ ] **Step 2: `docs/development.md` のモジュール表に 2 行足す**

`csv_export.py` の行の後に:

```markdown
| `settings_io.py` | 設定値のエクスポート・インポート(要望 78)。`build_settings`・`write_settings`・`parse_settings`(`ImportFile`。設定ファイルを「タスクのないプロジェクト」に組み直して `storage.parse_project` で検証する)、`plan_import`(`ImportPlan`: 区分ごとの追加・重複とプロジェクト設定の違い)、`apply_import`(`ImportResult`。選んだ区分と上書きを、コピーに適用して検証する。元は変えない)、`summary`、`copy_into`(`MainView` の `Project` の参照を保つ)。鍵は名前(イベントは期間と文字列)。NiceGUI に依存しない |
| `settings_dialog.py` | 取り込みのダイアログ(`open_import_dialog`)。区分のチェック `import-section-<key>`、重複の上書き `import-overwrite-<key>-<index>`、`import-apply`・`import-cancel`。`MainView.apply_settings_import` が `apply_import` と、上限・下限の見直し確認(`ask_limit_review`。`apply_ratio_limits` と共有)、スナップショットの取り直し(`refresh_all_snapshots`。`apply_reference_mode` と共有)につなぐ |
```

- [ ] **Step 3: 設計書・一覧・要望の記録を更新する**

- 設計書の `決めたこと`の下の「整合」で、`相対比率の上限・下限、稼働可能時間が変わるときは` を `相対比率の上限・下限が変わるときは` に直し、`稼働可能時間の変更に見直しの確認はない(換算率が変わらず、設定ダイアログにもない)` を足す。設計書の状態を `設計書承認済み(2026-10-29)。実装計画 [plans/2026-10-29-settings-export-import.md](../plans/2026-10-29-settings-export-import.md)— 要望 78 — feature/settings-io。` にする。
- `docs/superpowers/README.md` の要望 78 の行の計画の列を `[計画](plans/2026-10-29-settings-export-import.md)` に、状態を `実装中(feature/settings-io)` にする。
- `docs/requests.md` の要望 78 の状態を `実装中(2026-10-29。設計書・実装計画あり。feature/settings-io)` にする。

- [ ] **Step 4: 全体確認**

Run: `uv run pytest -n auto -q && uvx ty check src`
Expected: すべて PASS、`ty` 通過。

- [ ] **Step 5: 実機確認の案内(利用者に依頼)**

`uv run projectapp` で、(1) `エクスポート` → `設定を書き出す` でファイルができる、(2) 別のプロジェクトで `ファイル` → `設定を取り込む` → ダイアログの区分・上書きの選択 → 取り込み、(3) `Cmd+Z` で戻る、を確認してもらう。

- [ ] **Step 6: コミット**

```bash
git add CLAUDE.md docs
git commit -m "docs: 設定値のエクスポート・インポートの仕様と記録を更新する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
