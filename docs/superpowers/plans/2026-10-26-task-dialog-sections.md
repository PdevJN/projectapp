# タスクのダイアログの節の折りたたみ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの追加・編集ダイアログを、折りたためる節(基本・担当とパラメータ・実績と進捗・関連)にし、切り替え `task-layout` を廃止する。

**Architecture:** 純粋関数を `task_sections.py` に置き(開閉の初期値・閉じた節の要約・エラーから節の対応)、`config.py` に `task_sections` の読み書きを足す。`task_dialog.py` は、欄を作る処理を変えず、`ui.expansion` の中へ作り直す(欄の生成順を節ごとにまとめ直す)。`refresh_visibility` からレイアウトの分岐をなくし、種別による出し分けと、節ごとの表示だけにする。

**Tech Stack:** Python 3.13、NiceGUI、pytest(NiceGUI の `user` フィクスチャ)、`ty`、`uv`

**Spec:** `docs/superpowers/specs/2026-10-26-task-dialog-sections-design.md`(要望 62)

## Global Constraints

- すべての関数に型ヒント(引数と戻り値)を付ける。`ty` で検証する(`uv run ty check`。指摘件数が変更の前後で増えないこと)。
- コメントは多くても 3 行以内。日本語。
- テストは `uv run pytest`。`pytest -n auto` で並列にできる。
- `task_layout` は、古い `config.json` に残っていても読み飛ばす(読込を壊さない)。新しくは書かない。
- 節のキーは `basic`・`assignees`・`actuals`・`related`。保存するのは折りたためる 3 つ(`assignees`・`actuals`・`related`)だけ。
- マーカーは `task-section-{key}`。`task-layout` は廃止。
- 節の見出しの要約は、`ui.expansion` の `caption` に出す(閉じているときだけ。開いているときと空の節は空文字)。設計書の `task-section-{key}-summary` マーカーは作らない(テストは `expansion.props["caption"]` を読む)。実装後に設計書を直す(Task 5)。
- NiceGUI のユーザー・シミュレーションの `should_see` / `should_not_see` は、閉じた `ui.expansion` の中身を「見えない」と判定しない。節の開閉は `expansion.value` で確かめ、種別による出し分けは `should_not_see`(`set_visibility(False)` が効く)で確かめる。
- 要望 62 の挙動(設計書より): 新規は基本だけ開く。編集は値のある節も開く。保存した開閉があれば「値があれば開く」より優先するが、編集で値のある節は保存した状態に関わらず開く。検証エラーが閉じた節の中なら、その節を開いてからエラーを出す。節を開閉しただけでは「変更」に数えない。

## Review Focus

- `config.json` の `task_sections` が、リストでない・未知のキーを含む・`basic` を含む → 既定(保存なし)として扱い、ダイアログが開く。
- 古い `config.json`(`task_layout` だけ)でも落ちない。
- 閉じた節の中の値(担当・パラメータ・実績・進捗・先行・リンク・色)が、保存で失われない。
- 週ごとのタスク(`weekly_crew`)の担当の節: 担当欄は出さず説明だけで、閉じた要約は全週の和集合の担当者になる。
- 種別の切り替えで、節が全部隠れても(チェックポイント・参照・まとめ)ダイアログが壊れず、通常へ戻すと節が戻る。開閉の状態は保たれる。
- 節の開閉の保存が失敗(`OSError`)しても、ダイアログは続けて使える(`views.py` で通知だけ)。

---

### Task 1: 節の純粋関数 `task_sections.py`

**Files:**
- Create: `src/projectapp/task_sections.py`
- Create: `test/test_task_sections.py`

**Interfaces:**
- Produces:
  - `FOLDABLE: tuple[str, ...]` = `("assignees", "actuals", "related")`
  - `TITLES: dict[str, str]`(キー → 見出し)。`basic` を含む。
  - `has_values(section: str, task: Task) -> bool`
  - `initial_open(task: Task | None, saved: list[str] | None) -> list[str]`(`FOLDABLE` の順)
  - `assignees_summary(crew: list[tuple[str, float]], parameters: int) -> str`(割り当て率は 0〜1)
  - `actuals_summary(count: int, interval_mode: bool, progress: int | None) -> str`
  - `related_summary(predecessors: int, links: int, priority: Priority, has_color: bool) -> str`
  - `section_of_error(message: str) -> str | None`

- [ ] **Step 1: 失敗するテストを書く** — `test/test_task_sections.py`

```python
from projectapp.models import Assignee, Priority, Task, TaskUrl
from projectapp.task_sections import (
    actuals_summary,
    assignees_summary,
    has_values,
    initial_open,
    related_summary,
    section_of_error,
)
from projectapp.models import Actual
from datetime import datetime


def test_a_new_task_has_no_values_in_any_section() -> None:
    task = Task("a")
    assert not any(has_values(key, task) for key in ("assignees", "actuals", "related"))


def test_has_values_per_section() -> None:
    assert has_values("assignees", Task("a", assignees=[Assignee("田中", 1.0)]))
    assert has_values("assignees", Task("a", parameters=["P"]))
    assert has_values("actuals", Task("a", progress=0))
    assert has_values("actuals", Task("a", actuals=[Actual(datetime(2026, 10, 5, 9, 0), None)]))
    assert has_values("related", Task("a", predecessors=["p"]))
    assert has_values("related", Task("a", urls=[TaskUrl("仕様", None, {"URL": "https://example.com"})]))
    assert has_values("related", Task("a", priority=Priority.HIGH))
    assert has_values("related", Task("a", color="#123456"))
    assert not has_values("related", Task("a", priority=Priority.MEDIUM))


def test_initial_open_new_task_opens_nothing_without_a_saved_state() -> None:
    assert initial_open(None, None) == []


def test_initial_open_new_task_follows_the_saved_state() -> None:
    assert initial_open(None, ["related", "assignees"]) == ["assignees", "related"]


def test_initial_open_edit_opens_the_sections_with_values() -> None:
    task = Task("a", progress=40, priority=Priority.LOW)
    assert initial_open(task, None) == ["actuals", "related"]


def test_initial_open_edit_opens_valued_sections_even_if_the_saved_state_is_closed() -> None:
    task = Task("a", progress=40)
    assert initial_open(task, []) == ["actuals"]
    assert initial_open(task, ["assignees"]) == ["assignees", "actuals"]


def test_assignees_summary() -> None:
    assert assignees_summary([], 0) == ""
    assert assignees_summary([("田中", 1.0), ("鈴木", 0.5)], 0) == "田中 100%・鈴木 50%"
    assert assignees_summary([("田中", 1.0)], 2) == "田中 100%・パラメータ 2"
    assert assignees_summary([], 1) == "パラメータ 1"


def test_assignees_summary_caps_at_three_people() -> None:
    crew = [("A", 1.0), ("B", 1.0), ("C", 0.25), ("D", 1.0), ("E", 1.0)]
    assert assignees_summary(crew, 0) == "A 100%・B 100%・C 25%・ほか 2 人"


def test_actuals_summary() -> None:
    assert actuals_summary(0, True, None) == ""
    assert actuals_summary(2, True, 40) == "2区間・進捗 40%"
    assert actuals_summary(1, False, None) == "実績あり"
    assert actuals_summary(0, True, 0) == "進捗 0%"


def test_related_summary_omits_empty_items_and_the_default_priority() -> None:
    assert related_summary(0, 0, Priority.MEDIUM, False) == ""
    assert related_summary(2, 1, Priority.HIGH, False) == "先行 2・リンク 1・優先度 高"
    assert related_summary(0, 0, Priority.MEDIUM, True) == "色"


def test_section_of_error() -> None:
    assert section_of_error("区間 2: 前の区間と重なっています") == "actuals"
    assert section_of_error("区間は開始の早い順に入れてください") == "actuals"
    assert section_of_error("実績の終了は開始以降の日時にしてください") == "actuals"
    assert section_of_error("進捗度は0〜100の整数で入力してください") == "actuals"
    assert section_of_error("担当者が重複しています: 田中") == "assignees"
    assert section_of_error("先行タスクが正しくありません") == "related"
    assert section_of_error("色は#RRGGBBの形式で入力してください") == "related"
    assert section_of_error("URL を入力してください") == "related"
    assert section_of_error("工数は0以上の数値で入力してください") is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_sections.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.task_sections`)

- [ ] **Step 3: 実装する** — `src/projectapp/task_sections.py`

```python
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
    people = [f"{name} {allocation * 100:g}%" for name, allocation in crew[:MAX_SUMMARY_PEOPLE]]
    if len(crew) > MAX_SUMMARY_PEOPLE:
        people.append(f"ほか {len(crew) - MAX_SUMMARY_PEOPLE} 人")
    if parameters:
        people.append(f"パラメータ {parameters}")
    return "・".join(people)


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
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_task_sections.py -q`
Expected: PASS(全件)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/task_sections.py test/test_task_sections.py
git commit -m "feat: タスクのダイアログの節の決まりごと(開閉の初期値・要約・エラーの節)"
```

---

### Task 2: `config.py` の `task_sections`

**Files:**
- Modify: `src/projectapp/config.py:13`(`TASK_LAYOUTS` を置き換え)、`:76-82`(`load_task_layout`・`save_task_layout` を置き換え)
- Modify: `test/test_config.py:185-205`(`task_layout` のテストを置き換え)

**Interfaces:**
- Consumes: `task_sections.FOLDABLE`(Task 1)
- Produces:
  - `load_task_sections(base_dir: Path = BASE_DIR) -> list[str] | None`(保存なし・不正は `None`)
  - `save_task_sections(keys: list[str], base_dir: Path = BASE_DIR) -> None`

- [ ] **Step 1: 失敗するテストを書く** — `test/test_config.py` の 185〜205 行(`test_the_task_layout_*` の 3 件。パラメータ化の `@pytest.mark.parametrize` の行も含む)を次に置き換える

```python
def test_the_task_sections_default_to_none(tmp_path: Path) -> None:
    from projectapp.config import load_task_sections

    assert load_task_sections(tmp_path) is None


def test_the_task_sections_round_trip_and_keep_other_keys(tmp_path: Path) -> None:
    from projectapp.config import load_task_sections, load_zoom, save_task_sections, save_zoom

    save_zoom(120, tmp_path)
    save_task_sections(["related", "assignees"], tmp_path)
    assert load_task_sections(tmp_path) == ["assignees", "related"]  # 節の順にそろえる
    assert load_zoom(tmp_path) == 120
    save_task_sections([], tmp_path)
    assert load_task_sections(tmp_path) == []  # 全部閉じた状態も保存できる


@pytest.mark.parametrize("value", ["assignees", 1, None, ["nope"], ["assignees", "basic"], [["assignees"]]])
def test_invalid_task_sections_fall_back_to_none(tmp_path: Path, value: object) -> None:
    from projectapp.config import load_task_sections

    (tmp_path / "config.json").write_text(json.dumps({"task_sections": value}), encoding="utf-8")
    assert load_task_sections(tmp_path) is None


def test_an_old_task_layout_is_ignored(tmp_path: Path) -> None:
    from projectapp.config import load_task_sections, save_task_sections

    (tmp_path / "config.json").write_text(json.dumps({"task_layout": "schedule"}), encoding="utf-8")
    assert load_task_sections(tmp_path) is None
    save_task_sections(["actuals"], tmp_path)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["task_layout"] == "schedule"  # 触らない
```

(削除する元の 3 件の直前にある `@pytest.mark.parametrize(...)` の行も、対応するテストと一緒に消す。`pytest` と `json` は同ファイルで import 済み。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: FAIL(`ImportError: cannot import name 'load_task_sections'`)

- [ ] **Step 3: 実装する** — `src/projectapp/config.py`

13 行目 `TASK_LAYOUTS = ...` を次に置き換える:

```python
TASK_SECTION_KEYS = ("assignees", "actuals", "related")  # タスクのダイアログの、折りたためる節(基本は常に開く)
```

76〜82 行を次に置き換える:

```python
def load_task_sections(base_dir: Path = BASE_DIR) -> list[str] | None:
    """開いている節のキー(節の順)。保存がない・不正(リストでない、未知のキーを含む)は None。"""
    value = read_config(base_dir).get("task_sections")
    if not isinstance(value, list) or any(key not in TASK_SECTION_KEYS for key in value):
        return None
    return [key for key in TASK_SECTION_KEYS if key in value]


def save_task_sections(keys: list[str], base_dir: Path = BASE_DIR) -> None:
    update_config({"task_sections": [key for key in TASK_SECTION_KEYS if key in keys]}, base_dir)
```

注: `["assignees", ["x"]]` のようにリストを含む値は `key not in TASK_SECTION_KEYS` が `True`(リストは比較できるが一致しない)になり `None`。`[["assignees"]]` も同様。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_config.py -q`
Expected: PASS(`test_views.py` などの `load_task_layout` 参照は Task 4 で直すので、ここでは `test_config.py` だけを走らせる)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/config.py test/test_config.py
git commit -m "feat: 設定にタスクのダイアログの節の開閉(task_sections)を持たせる"
```

---

### Task 3: ダイアログを節に作り直す

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`LAYOUT_LABELS` の削除〔177 行〕、import、`open_task_dialog` の引数と本体〔888〜1215 行〕、`save()` のエラー処理)
- Modify: `test/test_task_dialog.py`(`mount_dialog` の引数、レイアウトのテストの置き換え)

**Interfaces:**
- Consumes: `task_sections.FOLDABLE`・`TITLES`・`initial_open`・`assignees_summary`・`actuals_summary`・`related_summary`・`section_of_error`(Task 1)。`models.DEFAULT_COLOR`。
- Produces: `open_task_dialog(..., sections: list[str] | None = None, on_sections_change: Callable[[list[str]], object] | None = None, ...)`(`layout`・`on_layout_change` を置き換える。ほかの引数と順序はそのまま)。`ui.expansion` のマーカー `task-section-assignees`・`task-section-actuals`・`task-section-related`。

**構成の考え方:** カードの直下は 種別トグル・種別のヒント・`basic_box`(基本の欄を入れる列)・3 つの `ui.expansion`(すべて先に作る)・エラー文。欄の生成コードは `with basic_box:` か `with section_boxes[...]:` で包み、**生成する順序は節ごとにまとめる**(DOM の順序は、親の列の中での生成順で決まる)。欄を作るコード自体は変えない。

- [ ] **Step 1: テスト側の土台を直し、新しい挙動のテストを書く** — `test/test_task_dialog.py`

(a) `mount_dialog`(46〜47 行と 70〜71 行)の `layout`・`on_layout_change` を置き換える:

```python
    sections: list[str] | None = None,
    on_sections_change: Callable[[list[str]], object] | None = None,
```
```python
                sections=sections,
                on_sections_change=on_sections_change,
```

(b) 2255〜2349 行付近のレイアウトの定数とテスト(`HIDDEN_IN_SCHEDULE`・`SHOWN_IN_SCHEDULE`・`test_the_dialog_opens_in_the_layout_it_is_given` から `test_the_conversion_stays_visible_in_the_schedule_layout` まで)を、次に置き換える(`rich_task()` はそのまま残す)。

```python
RICH_MEMBERS = {"link_options": {"p1": "先行"}, "categories": [Category("開発", id="c1")], "members": [Member("田中", 1.0)]}


def section_of(user: User, key: str) -> ui.expansion:
    return user.find(marker=f"task-section-{key}").elements.pop()


async def test_a_new_task_opens_only_the_basic_fields(user: User) -> None:
    mount_dialog(None, [], **RICH_MEMBERS)
    await open_dialog(user)
    for key in ("assignees", "actuals", "related"):
        assert section_of(user, key).value is False
    for marker in ("task-name", "task-kind", "task-category", "task-start-date", "task-effort", "task-status"):
        await user.should_see(marker=marker)


async def test_an_edit_opens_the_sections_with_values(user: User) -> None:
    mount_dialog(Task("a", progress=40, assignees=[Assignee("田中", 0.5)]), [], **RICH_MEMBERS)
    await open_dialog(user)
    assert section_of(user, "assignees").value is True
    assert section_of(user, "actuals").value is True
    assert section_of(user, "related").value is False


async def test_a_saved_state_is_used_but_valued_sections_still_open(user: User) -> None:
    mount_dialog(Task("a", progress=40), [], sections=["related"], **RICH_MEMBERS)
    await open_dialog(user)
    assert section_of(user, "related").value is True  # 保存した開閉
    assert section_of(user, "actuals").value is True  # 値があるので開く
    assert section_of(user, "assignees").value is False


async def test_toggling_a_section_reports_the_open_sections(user: User) -> None:
    changed: list[list[str]] = []
    mount_dialog(None, [], on_sections_change=changed.append, **RICH_MEMBERS)
    await open_dialog(user)
    section_of(user, "related").set_value(True)
    section_of(user, "assignees").set_value(True)
    section_of(user, "related").set_value(False)
    assert changed == [["related"], ["assignees", "related"], ["assignees"]]


async def test_toggling_a_section_alone_is_not_a_change(user: User) -> None:
    mount_dialog(rich_task(), [], **RICH_MEMBERS)
    await open_dialog(user)
    section_of(user, "related").set_value(False)
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False
    assert confirm_dialog_of(user).value is False


async def test_closed_sections_keep_their_values_through_a_save(user: User) -> None:
    saved: list[Task] = []
    original = rich_task()
    mount_dialog(original, saved, sections=[], **RICH_MEMBERS)
    await open_dialog(user)
    for key in ("assignees", "actuals", "related"):
        section_of(user, key).set_value(False)
    user.find(marker="task-name").clear().type("改名")
    user.find(marker="task-save").click()
    result = saved[0]
    assert result.name == "改名"
    assert result.category_id == "c1"
    assert [(a.name, a.allocation) for a in result.assignees] == [("田中", 0.5)]
    assert result.predecessors == ["p1"]
    assert result.priority is Priority.HIGH
    assert result.color == "#123456"
    assert result.urls == original.urls


async def test_a_closed_section_shows_its_summary_in_the_header(user: User) -> None:
    task = Task(
        "a",
        assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)],
        progress=40,
        predecessors=["p1"],
        priority=Priority.HIGH,
    )
    mount_dialog(task, [], members=[Member("田中", 1.0), Member("鈴木", 1.0)], link_options={"p1": "先行"})
    await open_dialog(user)
    assert section_of(user, "assignees").props["caption"] == ""  # 開いている間は出さない
    for key in ("assignees", "actuals", "related"):
        section_of(user, key).set_value(False)
    assert section_of(user, "assignees").props["caption"] == "田中 100%・鈴木 50%"
    assert section_of(user, "actuals").props["caption"] == "進捗 40%"
    assert section_of(user, "related").props["caption"] == "先行 1・優先度 高"
    section_of(user, "actuals").set_value(True)
    assert section_of(user, "actuals").props["caption"] == ""


async def test_an_empty_closed_section_has_no_summary(user: User) -> None:
    mount_dialog(None, [], **RICH_MEMBERS)
    await open_dialog(user)
    for key in ("assignees", "actuals", "related"):
        assert section_of(user, key).props["caption"] == ""


async def test_the_summary_follows_edits_made_while_open(user: User) -> None:
    mount_dialog(None, [], sections=["actuals"], **RICH_MEMBERS)
    await open_dialog(user)
    task_progress_input(user).set_value(70)
    section_of(user, "actuals").set_value(False)
    assert section_of(user, "actuals").props["caption"] == "進捗 70%"


async def test_an_error_in_a_closed_section_opens_it(user: User) -> None:
    mount_dialog(None, [], actual_mode=ActualMode.INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("a")
    section_of(user, "actuals").set_value(True)
    user.find(marker="task-interval-add").click()  # 日付だけの行を作って、エラーにする
    interval_start_day(user).set_value("2026-10-05")
    section_of(user, "actuals").set_value(False)
    user.find(marker="task-save").click()
    assert section_of(user, "actuals").value is True
    assert user.find(marker="form-error").elements.pop().text != ""


async def test_opening_a_section_for_an_error_is_not_saved(user: User) -> None:
    changed: list[list[str]] = []
    mount_dialog(None, [], actual_mode=ActualMode.INTERVALS, on_sections_change=changed.append)
    await open_dialog(user)
    user.find(marker="task-name").type("a")
    section_of(user, "actuals").set_value(True)
    user.find(marker="task-interval-add").click()
    interval_start_day(user).set_value("2026-10-05")
    section_of(user, "actuals").set_value(False)
    changed.clear()
    user.find(marker="task-save").click()
    assert changed == []


async def test_a_checkpoint_hides_the_normal_sections(user: User) -> None:
    mount_dialog(None, [], **RICH_MEMBERS)
    await open_dialog(user)
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.CHECKPOINT)
    for marker in ("task-start-date", "task-effort", "task-actual-start-date", "task-section-assignees", "task-section-actuals"):
        await user.should_not_see(marker=marker)
    await user.should_see(marker="task-deadline-date")
    await user.should_see(marker="task-section-related")
    user.find(marker="task-kind").elements.pop().set_value(TaskKind.NORMAL)
    for marker in ("task-effort", "task-section-assignees", "task-section-actuals"):
        await user.should_see(marker=marker)


async def test_the_conversion_is_shown_in_the_basic_fields(user: User) -> None:
    task = Task("a", effort_hours=13.0, assignees=[Assignee("田中", 0.5)])
    mount_dialog(task, [], members=[Member("田中", 0.5)])
    await open_dialog(user)
    section_of(user, "assignees").set_value(False)
    conversion = user.find(marker="task-conversion").elements.pop()
    assert "換算率" in conversion.text
```

注: `interval_start_day(user)`・`task_progress_input(user)` は、既存のテストが使うヘルパー名に合わせる。`interval_start_day` が無ければ、区間の開始日の入力を取る既存の書き方(`test_task_dialog.py` の区間のテスト。`grep -n "interval" test/test_task_dialog.py` で探す)に置き換える。区間追加ボタンのマーカーも既存の名前に合わせる。

(c) 1203〜1206 行の `test_the_task_progress_stays_in_the_schedule_layout` を削除する(レイアウトがなくなった)。

(d) 2610〜2613 行の `test_the_parameter_select_is_only_in_the_full_layout` を、次に置き換える:

```python
async def test_the_parameter_select_is_in_the_assignees_section(user: User) -> None:
    mount_dialog(None, [], parameters=PYTHON_JAVA, sections=["assignees"])
    await open_dialog(user)
    await user.should_see(marker="task-parameters")
    assert section_of(user, "assignees").value is True
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -x`
Expected: FAIL(`open_task_dialog() got an unexpected keyword argument 'sections'`)

- [ ] **Step 3: `task_dialog.py` の import と定数**

177 行 `LAYOUT_LABELS = ...` を削除する。import に追加する:

```python
from projectapp.models import DEFAULT_COLOR  # 既存の `from projectapp.models import ...` に足す
from projectapp.task_sections import (
    FOLDABLE,
    TITLES,
    actuals_summary,
    assignees_summary,
    initial_open,
    related_summary,
    section_of_error,
)
```

- [ ] **Step 4: `open_task_dialog` の引数を置き換える**(903〜904 行)

```python
    sections: list[str] | None = None,
    on_sections_change: Callable[[list[str]], object] | None = None,
```

- [ ] **Step 5: ダイアログ本体の組み替え**(929〜1215 行)

組み替え後の並びは次のとおり。**各欄の生成コードは、行番号の範囲をそのまま移す**(中身は変えない)。`...` は「元のコードをそのまま」の意味で、省略ではなく移動の指示。

```python
    with disposable(ui.dialog().props("persistent")) as dialog, ui.card().classes("w-[44rem] max-w-full"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")   # 930 行
        # (931〜933 行の layout_toggle は削除)
        offered = [...]            # 934〜940 行そのまま
        kind = ui.toggle(...)      # 941〜944 行そのまま
        kind_hint = (...)          # 945〜949 行そのまま
        basic_box = ui.column().classes("w-full")
        section_boxes: dict[str, ui.expansion] = {}
        for key in FOLDABLE:
            section_boxes[key] = (
                ui.expansion(TITLES[key], value=key in opened_sections)
                .props("dense")
                .classes("w-full border rounded")
                .mark(f"task-section-{key}")
            )
```

`opened_sections = initial_open(task, sections)` は、`open_task_dialog` の本体の先頭付近(`reapply_ratios` の定義の後、`with disposable` の前)に置く。

続いて、欄を節ごとに作る。**生成の順序**は次のとおり(右は元の行):

1. `with basic_box:`
   - `name` と `replace_control_chars`(950〜966)
   - `ref_project`(967〜973)
   - `category` とそのスロット(974〜988)
   - `fields`・`effort`(1002〜1011)
   - `weekly = bool(initial.weekly_crew)`(1012)
   - `conversion` ラベル(1019)と `refresh_conversion`・`on_effort_change`・`effort.on_value_change`(1021〜1054)。**`refresh_conversion()` の呼び出し(1064)はまだ置かない**(担当の欄がまだ無い)
   - `status`・`hint`・`suggest`・`on_status_change` とそのバインド(1106〜1120)
2. `with section_boxes["assignees"]:`
   - `parameter_select`(989〜1001)
   - `assignee_fields`(1013)・`weekly_note`(1014〜1018)
   - ここで `if parameter_select is not None:` のブロック(1056〜1063)と `refresh_conversion()`(1064)を置く(`assignee_fields` が定義された後)
3. `with section_boxes["actuals"]:`
   - `actual_box`・`intervals`・`actual_fields`(1100〜1104)
   - `progress_field`(1105)
   - その直後(同じ `with` の外でよい)に `on_actual_change` とそのバインド、`has_normal_data`(1122〜1147)
4. `with section_boxes["related"]:`
   - `options`・`kept`・`predecessors`・`push`・`refresh_push`・`merged_predecessors`(1065〜1096)
   - `priority_box`(1098〜1099)
   - `url_box`(1170〜1172。`templates` の定義は 1170 行なので `with` の前に出す)
   - `color`(1173〜1175)
5. `apply_kind`(1149〜1169)は、`status`・`kind_hint`・`refresh_push` が定義された後であれば、元の位置のままでよい(`apply_kind()` の初回呼び出しは、`url_box` などの生成後 = 手順 4 の後)。

`refresh_push` の最後の行を、レイアウトに依存しない形にする(1088 行):

```python
            push.set_visibility(bool(text))
```

- [ ] **Step 6: `refresh_visibility` を置き換える**(1177〜1214 行を、次に置き換える)

```python
        def refresh_visibility(_event: object = None) -> None:
            """欄と節の出し入れを 1 か所で決める(値は消さない)。種別によって出す欄が変わり、欄が 1 つも無い節は隠す。"""
            if is_summary:  # まとめは、名前・カテゴリ・優先度・リンクだけ
                for widget in (
                    fields.first_row, fields.second_row, conversion, status, hint, kind, kind_hint,
                    predecessors, push, color, section_boxes["assignees"], section_boxes["actuals"],
                ):
                    widget.set_visibility(False)
                for widget in (category, priority_box, url_box, section_boxes["related"]):
                    widget.set_visibility(True)
                return
            reference = kind.value == TaskKind.REFERENCE
            normal = kind.value not in (TaskKind.CHECKPOINT, TaskKind.REFERENCE)
            ref_project.set_visibility(reference)
            for widget in (fields.first_row, effort, conversion, actual_box, progress_field.container):
                widget.set_visibility(normal)
            assignee_fields.container.set_visibility(normal and not weekly)
            weekly_note.set_visibility(normal and weekly)
            if parameter_select is not None:
                parameter_select.set_visibility(normal)
            for widget in (category, status, priority_box, url_box):  # プロジェクト参照は、状態・カテゴリ・優先度・リンクを持たない
                widget.set_visibility(not reference)
            for widget in (predecessors, color):
                widget.set_visibility(True)
            section_boxes["assignees"].set_visibility(normal)
            section_boxes["actuals"].set_visibility(normal)
            section_boxes["related"].set_visibility(True)
            refresh_push()

        kind.on_value_change(refresh_visibility)
        refresh_visibility()
```

注: 旧コードの `layout_toggle` を含む 1184 行・1211〜1213 行の記述は、すべてなくなる。まとめの `hint` は旧コードでも隠れていた(`status` と同じ)。

- [ ] **Step 7: 要約と開閉の保存を足す**(`refresh_visibility()` の直後、`error = ui.label(...)` の前)

```python
        quiet = {"on": False}  # エラーで開いたときは、開閉の保存を呼ばない

        def crew_summary() -> list[tuple[str, float]]:
            if weekly:
                return [(a.name, a.allocation) for a in initial.assignees]
            return [(m.name, share) for m, share in assignee_fields.chosen()]

        def caption_of(key: str) -> str:
            try:
                if key == "assignees":
                    return assignees_summary(crew_summary(), len(chosen_parameters))
                if key == "actuals":
                    count = len(actual_fields.rows()) if isinstance(actual_fields, IntervalFields) else int(bool(actual_fields.start_text()))
                    value = progress_field.value
                    return actuals_summary(count, intervals, None if value is None else int(value))
                return related_summary(
                    len(predecessors.value or []),
                    len(url_fields.rows()),
                    Priority(priority.value),
                    (color.value or initial.color) != DEFAULT_COLOR,
                )
            except ValueError:  # 入力の途中(書式の誤り)は、要約を出さない
                return ""

        def refresh_captions(_event: object = None) -> None:
            for key, box in section_boxes.items():
                box.props["caption"] = "" if box.value else caption_of(key)
                box.update()

        def on_section_toggle(_event: object) -> None:
            refresh_captions()
            if on_sections_change is not None and not quiet["on"]:
                on_sections_change([key for key in FOLDABLE if section_boxes[key].value])

        def open_section(key: str) -> None:
            quiet["on"] = True
            try:
                section_boxes[key].set_value(True)
            finally:
                quiet["on"] = False

        for box in section_boxes.values():
            box.on_value_change(on_section_toggle)
        refresh_captions()
```

`url_fields.rows()` が書式の誤りで `ValueError` を投げる場合は上の `except` で空の要約になる。`Priority` を import に足す(未 import のとき)。

- [ ] **Step 8: `save()` のエラー処理を直す**

```python
            except ValueError as exc:
                error.set_text(str(exc))
                if (key := section_of_error(str(exc))) is not None:
                    open_section(key)
                return
```

- [ ] **Step 9: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py test/test_task_sections.py -q -n auto`
Expected: PASS。`user.find(marker="task-layout")` を使う既存テストが残っていれば、削除済みの 4 件以外に無いか `grep -n "task-layout\|layout=" test/test_task_dialog.py` で確かめ、残りは節の開閉に置き換える。

- [ ] **Step 10: 型を確かめる**

Run: `uv run ty check src/projectapp/task_dialog.py src/projectapp/task_sections.py src/projectapp/config.py 2>&1 | tail -5`
Expected: 変更の前後で指摘件数が増えない(`git stash` で戻して件数を比べてよい)。

- [ ] **Step 11: コミット**

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "feat: タスクのダイアログを折りたためる節にする(task-layout を廃止)"
```

---

### Task 4: `views.py` の配線と、残りのテスト

**Files:**
- Modify: `src/projectapp/views.py:29,36`(import)、`:228`、`:640-646`、`:1269-1270`
- Modify: `test/test_views.py:4093-` (`task_layout` のテスト 2 件)

**Interfaces:**
- Consumes: `config.load_task_sections`・`save_task_sections`(Task 2)、`open_task_dialog(sections=, on_sections_change=)`(Task 3)
- Produces: `MainView.task_sections: list[str] | None`、`MainView.set_task_sections(keys: list[str]) -> None`

- [ ] **Step 1: 失敗するテストを書く** — `test/test_views.py` の 4093 行以降の 2 件(`test_the_task_layout_is_loaded_and_saved`・`test_the_task_dialogs_get_the_saved_layout`)を置き換える。後者の本体は現状を読んで(`sed -n 4100,4125p test/test_views.py`)、`task_layout`→`task_sections`、`"schedule"`→`["related"]` に読み替える。前者は次のとおり:

```python
async def test_the_task_sections_are_loaded_and_saved(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"task_sections": ["related"]}', encoding="utf-8")
    view = await open_members_view(user, tmp_path)
    assert view.task_sections == ["related"]
    view.set_task_sections(["assignees", "actuals"])
    assert view.task_sections == ["assignees", "actuals"]
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["task_sections"]
    assert saved == ["assignees", "actuals"]


async def test_the_old_task_layout_does_not_break_the_view(user: User, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"task_layout": "schedule"}', encoding="utf-8")
    view = await open_members_view(user, tmp_path)
    assert view.task_sections is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "task_sections or task_layout or saved_layout"`
Expected: FAIL(`task_sections` が無い)

- [ ] **Step 3: 実装する** — `src/projectapp/views.py`

- 29 行 `load_task_layout,` → `load_task_sections,`、36 行 `save_task_layout,` → `save_task_sections,`(アルファベット順の位置に直す)
- 228 行: `self.task_sections = load_task_sections(base_dir)  # タスクのダイアログで開いている節。全プロジェクト共通`
- 640〜646 行を置き換える:

```python
    def set_task_sections(self, keys: list[str]) -> None:
        """タスクのダイアログの節の開閉を覚える。保存できなくても、画面には反映する(通知だけ出す)。"""
        self.task_sections = keys
        try:
            save_task_sections(keys, self.base_dir)
        except OSError:
            ui.notify("節の開閉を保存できませんでした", type="warning")
```

- 1269〜1270 行: `"sections": self.task_sections,` と `"on_sections_change": self.set_task_sections,`

- [ ] **Step 4: 通ることを確かめる(全体)**

Run: `grep -rn "task_layout\|task-layout\|layout_toggle\|LAYOUT_LABELS\|on_layout_change" src test | grep -v "\.pyc"` → 残りが無いこと(`test_config.py` の「古い task_layout」のテストは意図的に残る)。
Run: `uv run pytest -n auto -q 2>&1 | tail -5`
Expected: 全件 PASS。`uv run ty check` の件数が変更前(`git stash` で比べる)と同数以下。

- [ ] **Step 5: 実機確認(ネイティブ)**

Run: `uv run projectapp`(ネイティブ)。次を目で確かめ、ユーザーに結果を報告する。
1. 新規(`+`)は、基本だけ開き、3 つの節が閉じている。
2. 節を開いて閉じると、見出しの右(下)に要約が出る。開くと消える。
3. 閉じて再び新規を開くと、前に開いた節が開いている(`~/.projectapp/config.json` の `task_sections`)。
4. 実績の区間を 1 行だけ日付にして保存 → 実績・進捗の節が開いてエラーが出る。
5. チェックポイントに切り替えると、担当・実績の節が消える。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: 節の開閉を config.json の task_sections に保存し、ダイアログへ渡す"
```

---

### Task 5: 仕様と記録を直す

**Files:**
- Modify: `CLAUDE.md`(プロジェクトの、タスクのダイアログの記述〔`task_layout`・`予定・実績`/`すべて`〕)
- Modify: `docs/superpowers/specs/2026-10-26-task-dialog-sections-design.md`(状態と、要約の出し方)
- Modify: `docs/requests.md`(要望 62 の状態)
- Modify: `docs/superpowers/README.md`(索引があれば状態)
- Modify: `docs/development.md`(`task_layout` の記述があれば)
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: `task_layout` の記述を探す**

Run: `grep -n "task_layout\|予定・実績\|task-layout" CLAUDE.md docs/*.md docs/superpowers/README.md .claude/MEMORY.md README.md`

- [ ] **Step 2: `CLAUDE.md` の直し**

「タスクの追加・編集ダイアログは、タイトルの下の切り替えで、レイアウトを…」の項目を、次に置き換える(`task_layout`・`config.json` の説明も含めて):

```
- タスクの追加・編集ダイアログは、欄を折りたためる節に分ける: `基本`(種別・名前・参照先・カテゴリ・開始予定・完了予定・締切・工数・状態。常に開く)・`担当・パラメータ`・`実績・進捗`・`関連`(先行・優先度・リンク・色)。新規は基本だけ開き、編集は値のある節も開く。節を開閉した状態は`~/.projectapp/config.json`の`task_sections`(開いている節のキーのリスト。全プロジェクト共通)に保存し、次回も使う(保存した状態があればそれを使うが、編集で値のある節は必ず開く)。閉じた節の見出しには、中身の要約(`田中 100%・鈴木 50%`・`2区間・進捗 40%`・`先行 2・リンク 1・優先度 高`)を出す。閉じた節の値は保持し、保存でも失わない。検証エラーが閉じた節の中の項目にあるときは、その節を開いてからエラーを出す。種別で出す欄が変わり、欄が 1 つも出ない節は隠す。古い`task_layout`は読み飛ばす
```

- [ ] **Step 3: 設計書・要望・MEMORY を直す**

- 設計書の状態を「実装済み(PR #?)」にし、「要約は `task-section-{key}-summary` マーカーではなく、`ui.expansion` の `caption` に出す(テストは `props["caption"]`)」と書き直す。
- `docs/requests.md` の要望 62 の状態を「完了(実機確認済み。日付)。[設計書]・[計画](superpowers/plans/2026-10-26-task-dialog-sections.md)」にする。
- `docs/superpowers/README.md` に索引があれば、状態を更新し、計画へのリンクを足す。
- `.claude/MEMORY.md` の「現在の状況」の先頭に、要望 62 の実装済みの項目を足し、「最終更新」を直す(PR の番号が決まってから)。

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "docs: 要望 62 の完了を記録し、仕様(CLAUDE.md)を節の折りたたみに直す"
```

---

## Self-Review

- 設計書の各項目 → 節と項目: Task 3 Step 5(生成順)。要約: Task 1 + Task 3 Step 7。種別との関係: Task 3 Step 6。開閉と保存: Task 1(`initial_open`)・Task 2・Task 3 Step 7・Task 4。検証エラーと節: Task 1(`section_of_error`)・Task 3 Step 8。テスト: 各タスク。見送り(並べ替えなど)は作らない。
- 型の一貫性: `initial_open(task, saved)`・`FOLDABLE`・`TITLES`・`load_task_sections`/`save_task_sections`・`open_task_dialog(sections, on_sections_change)`・`MainView.task_sections`/`set_task_sections` は、全タスクで同じ名前。
- 設計書との差: 要約のマーカーをやめ `caption` にした(Global Constraints と Task 5 で直す)。
