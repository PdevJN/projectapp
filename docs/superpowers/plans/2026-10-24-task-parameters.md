# タスクのパラメータ(要望 51) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクに`パラメータ`(分類)を付けられるようにし、付けたタスクでは、付けたパラメータの判定値だけで担当メンバーの相対比率を決める。

**Architecture:** `Task.parameters: list[str]` を足し、`ratios.effective_ratio`/`ratio_detail` に`only`(数えるパラメータ名)を足す。`crew_of`/`assignees_rate`/`conversion_rate` がタスクのパラメータを渡すので、完了予定・担当者向けファイルの見積もり・見直しは同じ経路で変わる。ファイルは`version` 9。ダイアログに複数選択を足し、選択の変更で換算率を即時に作り直す。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)

**Spec:** `docs/superpowers/specs/2026-10-24-task-parameters-design.md`

## Global Constraints

- 付けたタスクの比率 = `基本比率 + 付けたパラメータの判定値の合計`(付けなかったパラメータは数えない)。付けないタスク(`parameters` が空)は今のまま(全パラメータの合計)。丸めは 10〜300%(`MIN_RATIO`・`MAX_RATIO`)。
- `FORMAT_VERSION` は 8 → 9。キーのない古いファイルは「付けない」として読む。型が不正なら読込を拒否する。まとめ・チェックポイントの`parameters`は読込で空にする。登録されていない名前は残し、計算では数えない。
- ダイアログの出し場所は`すべて`レイアウトだけ。ガントチャートの名前の欄のチップには出さない。パラメータが 0 件なら欄を出さない。
- 担当者向けファイル(`todos.json`)と PlantUML には独自のキーを足さない。
- 日本語のコメント・メッセージ。周囲のコードのコメントの量と書き方に合わせる。
- 各タスクの最後に、そのタスクが触るテストファイルを実行し、最後のタスクで`uv run pytest -q`(約 4 分。バックグラウンドで)を通す。

## Review Focus

- 付けたパラメータにメンバーが段階を選んでいない: 判定値 0%(基本比率だけ)。`test_ratios.py` に置く(Task 1)。
- プロジェクトに登録されていないパラメータ名が付いたタスク(古い・手編集のファイル): 数えず、読込も拒否しない。`test_ratios.py`(Task 1)と`test_storage.py`(Task 2)。
- 付けたパラメータを削除・改名したとき: 改名は追従、削除は外す。確認ダイアログに件数を出す(Task 4)。
- タスクのコピー・分解で`parameters`のリストを共有しない(片方の編集がもう片方に出ない)(Task 3)。
- パラメータを付け替えて保存したとき、実績・進捗度がある既存タスクで完了予定の見直しの確認を出す(Task 5)。

---

### Task 1: モデルと比率の計算

**Files:**
- Modify: `src/projectapp/models.py`(`Task`)
- Modify: `src/projectapp/ratios.py`(`ratio_detail`・`effective_ratio`)
- Modify: `src/projectapp/timeline.py:384-409,465`(`crew_of`・`assignees_rate`・`conversion_rate`・タスクの完了予定の算出)
- Test: `test/test_ratios.py`・`test/test_schedule.py`・`test/test_handoff.py`

**Interfaces:**
- Produces: `Task.parameters: list[str]`(既定は空)。`ratio_detail(member, parameters, only=None) -> RatioDetail`・`effective_ratio(member, parameters, only=None) -> float`(`only` が`None`か空なら全合計、そうでなければ名前の集合に含まれるパラメータだけ足す)。`crew_of(assignees, members, parameters=None, only=None)`・`assignees_rate(assignees, members, parameters=None, only=None)`。`conversion_rate(task, project)` は`task.parameters`を渡す。

- [ ] **Step 1: ratios の失敗するテストを書く**(`test/test_ratios.py` の末尾)

```python
def test_only_the_named_parameters_are_added() -> None:
    member = Member("a", 1.0, {"経験": "上級", "専門": "低"})
    assert effective_ratio(member, PARAMETERS, only=["経験"]) == pytest.approx(1.2)
    assert effective_ratio(member, PARAMETERS, only=["専門"]) == pytest.approx(0.9)
    detail = ratio_detail(member, PARAMETERS, only=["経験"])
    assert detail.adjustments == [("経験", "上級", 0.2)]
    assert detail.raw == pytest.approx(1.2)


def test_no_or_empty_only_means_every_parameter() -> None:
    member = Member("a", 1.0, {"経験": "上級", "専門": "低"})
    assert effective_ratio(member, PARAMETERS, only=None) == pytest.approx(1.1)
    assert effective_ratio(member, PARAMETERS, only=[]) == pytest.approx(1.1)


def test_a_named_parameter_without_a_chosen_level_adds_nothing() -> None:
    member = Member("a", 1.0, {"経験": "上級"})  # 専門は未選択
    assert effective_ratio(member, PARAMETERS, only=["専門"]) == pytest.approx(1.0)


def test_unregistered_names_are_ignored_and_the_result_is_still_clamped() -> None:
    member = Member("a", 2.9, {"経験": "上級"})
    assert effective_ratio(member, PARAMETERS, only=["ない"]) == pytest.approx(2.9)
    big = [Parameter("経験", [Level("上級", 0.5)])]
    assert effective_ratio(member, big, only=["経験"]) == pytest.approx(3.0)  # 3.4 を 300% に丸める
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_ratios.py -k "only or named or unregistered"`
Expected: FAIL(`unexpected keyword argument 'only'`)

- [ ] **Step 3: `ratios.py` を実装する**

`ratio_detail` を次のとおり直す(`effective_ratio` も`only`を通す)。

```python
def ratio_detail(member: Member, parameters: list[Parameter], only: Collection[str] | None = None) -> RatioDetail:
    """メンバーの相対比率の内訳。存在しないパラメータ・段階への選択は、判定値 0% として数えない。
    only があれば、その名前のパラメータだけ足す(None か空は全パラメータ。タスクに付けたパラメータの指定)。"""
    counted = set(only) if only else None
    adjustments: list[tuple[str, str, float]] = []
    for parameter in parameters:
        if counted is not None and parameter.name not in counted:
            continue
        chosen = member.levels.get(parameter.name)
        level = next((lv for lv in parameter.levels if lv.name == chosen), None) if chosen is not None else None
        if level is not None:
            adjustments.append((parameter.name, level.name, level.value))
    # 保存する値は小数点以下 4 桁までなので、足し算の誤差(0.3 - 0.2 = 0.0999…)で境界を外さないよう丸める
    raw = round(member.ratio + sum(value for _, _, value in adjustments), 4)
    ratio = min(max(raw, MIN_RATIO), MAX_RATIO) if isfinite(raw) else member.ratio
    return RatioDetail(member.ratio, adjustments, raw, ratio, ratio != raw)


def effective_ratio(member: Member, parameters: list[Parameter], only: Collection[str] | None = None) -> float:
    """計算に使う相対比率。"""
    return ratio_detail(member, parameters, only).ratio
```

ファイル先頭の import に `from collections.abc import Collection` を足す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q test/test_ratios.py`
Expected: PASS

- [ ] **Step 5: モデルと完了予定・見積もりの失敗するテストを書く**

```python
# test/test_schedule.py(MON・HOLIDAYS・effective_end は同ファイルの既存。Parameter・Level・Section は models から import に足す)
def test_a_task_with_parameters_uses_only_those_levels_for_its_end() -> None:
    parameters = [Parameter("Python", [Level("上級", 0.5)]), Parameter("Java", [Level("初級", -0.5)])]
    member = Member("田中", 1.0, {"Python": "上級", "Java": "初級"})  # 全合計は 100%
    plain = Task("a", planned_start=MON, effort_hours=13.0, assignees=[Assignee("田中", 1.0)])
    tagged = Task("b", planned_start=MON, effort_hours=13.0, assignees=[Assignee("田中", 1.0)], parameters=["Python"])
    proj = Project("p", members=[member], parameters=parameters, tasks=[plain, tagged], daily_hours=6.5)
    assert effective_end(plain, proj, HOLIDAYS) == datetime(2026, 10, 6, 15, 30)  # 100%: 13h = 2 日(6.5h × 2)
    assert effective_end(tagged, proj, HOLIDAYS) == datetime(2026, 10, 6, 11, 10)  # 150%: 8.667h = 6.5h + 2h10m
```

```python
# test/test_handoff.py(Assignee・Level・Member・Parameter・Project・Section・Task は models から import に足す。_estimate_hours は handoff の関数)
def test_the_estimate_uses_the_ratio_of_the_task_parameters() -> None:
    parameters = [Parameter("Python", [Level("上級", 0.5)])]
    member = Member("田中", 1.0, {"Python": "上級"})
    task = Task("a", effort_hours=6.0, assignees=[Assignee("田中", 1.0)], parameters=["Python"])
    project = Project("p", members=[member], parameters=parameters, sections=[Section("s", [task])])
    assert _estimate_hours(task, project, "田中") == 4.0  # 6h ÷ 150%
```

- [ ] **Step 6: 失敗を確かめる**

Run: `uv run pytest -q test/test_schedule.py test/test_handoff.py -k "parameters"`
Expected: FAIL(`Task.__init__() got an unexpected keyword argument 'parameters'`)

- [ ] **Step 7: `models.py` と`timeline.py` を実装する**

`models.py` の`Task`の`children`の次に足す。

```python
    parameters: list[str] = field(default_factory=list)  # 付けたパラメータの名前。空は付けない(相対比率は全パラメータの合計)
```

`timeline.py` を直す。

```python
def crew_of(
    assignees: list[Assignee],
    members: list[Member],
    parameters: list[Parameter] | None = None,
    only: Collection[str] | None = None,
) -> list[Worker]:
    """担当者を算出用の Worker にする。相対比率は、パラメータを反映した実効比率(only はタスクに付けたパラメータ)。メンバーにいない担当者は入れない。"""
    by_name = {m.name: m for m in members}
    chosen = parameters or []
    return [
        Worker(
            combine_rate(effective_ratio(by_name[a.name], chosen, only), a.allocation),
            work_day_map(by_name[a.name].work_days),
        )
        for a in assignees
        if a.name in by_name
    ]


def assignees_rate(
    assignees: list[Assignee],
    members: list[Member],
    parameters: list[Parameter] | None = None,
    only: Collection[str] | None = None,
) -> float:
    """担当者全員の換算率(相対比率 × 割り当て率)の合計。誰も数えられなければ 1.0(換算しない)。"""
    rates = [w.rate for w in crew_of(assignees, members, parameters, only)]
    return sum(rates) if rates else 1.0


def conversion_rate(task: Task, project: Project) -> float:
    return assignees_rate(task.assignees, project.members, project.parameters, task.parameters)
```

`computed_end(... crew=crew_of(...))`(465 行付近)も`crew_of(task.assignees, project.members, project.parameters, task.parameters)`にする。`from collections.abc import Collection` を import に足す。

- [ ] **Step 8: 通ることを確かめる**

Run: `uv run pytest -q test/test_ratios.py test/test_schedule.py test/test_handoff.py test/test_timeline.py test/test_reassign.py`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/projectapp/models.py src/projectapp/ratios.py src/projectapp/timeline.py test/test_ratios.py test/test_schedule.py test/test_handoff.py
git commit -m "feat: タスクのパラメータで相対比率を決める(モデルと計算)"
```

---

### Task 2: ファイル形式(version 9)と 3 者マージ

**Files:**
- Modify: `src/projectapp/models.py:11`(`FORMAT_VERSION`)
- Modify: `src/projectapp/storage.py`(`_task`・`_summary`・`_checkpoint`、新しい`_parameter_names`)
- Modify: `src/projectapp/merge.py:228-231`(`TASK_LABELS`)
- Test: `test/test_storage.py`・`test/test_merge.py`

**Interfaces:**
- Consumes: Task 1 の`Task.parameters`。
- Produces: 保存は`tasks[].parameters`(文字列の配列)。`_parameter_names(value: Any) -> list[str]`(キーなし・`None` は空、配列でない・文字列以外は`ValueError`、重複は最初の 1 件を残す)。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_storage.py`。既存の往復・`_rewrite` ヘルパーの使い方に合わせる)

```python
def test_task_parameters_round_trip_and_the_version_is_9(tmp_path: Path) -> None:
    task = Task("a", parameters=["Python", "Java"])
    project = Project("p", parameters=[Parameter("Python", []), Parameter("Java", [])], sections=[Section("s", [task])])
    path = save_project(project, tmp_path, overwrite=False)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == FORMAT_VERSION == 9
    assert raw["sections"][0]["tasks"][0]["parameters"] == ["Python", "Java"]
    assert load_project(path).sections[0].tasks[0].parameters == ["Python", "Java"]


def test_a_file_without_the_parameters_key_loads_as_none_attached(tmp_path: Path) -> None:
    path = save_project(Project("p", sections=[Section("s", [Task("a")])]), tmp_path, overwrite=False)
    _rewrite(path, lambda d: d["sections"][0]["tasks"][0].pop("parameters"))
    assert load_project(path).sections[0].tasks[0].parameters == []


def test_unregistered_and_duplicate_parameter_names_are_kept_once(tmp_path: Path) -> None:
    path = save_project(Project("p", sections=[Section("s", [Task("a")])]), tmp_path, overwrite=False)
    _rewrite(path, lambda d: d["sections"][0]["tasks"][0].update(parameters=["ない", "ない", "ある"]))
    assert load_project(path).sections[0].tasks[0].parameters == ["ない", "ある"]


@pytest.mark.parametrize("bad", ["Python", [1], [None], {"a": 1}])
def test_a_malformed_parameters_value_is_rejected(tmp_path: Path, bad: object) -> None:
    path = save_project(Project("p", sections=[Section("s", [Task("a")])]), tmp_path, overwrite=False)
    _rewrite(path, lambda d: d["sections"][0]["tasks"][0].update(parameters=bad))
    with pytest.raises(ValueError):
        load_project(path)


def test_summaries_and_checkpoints_lose_their_parameters_on_load(tmp_path: Path) -> None:
    kid = Task("c", id="c")
    summary = Task("まとめ", kind=TaskKind.SUMMARY, children=["c"], parameters=["P"])
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17), parameters=["P"])
    project = Project("p", sections=[Section("s", [summary, kid, checkpoint])])
    loaded = load_project(save_project(project, tmp_path, overwrite=False))
    assert [t.parameters for t in loaded.sections[0].tasks] == [[], [], []]
```

`_rewrite`・`save_project`・`load_project` の実際の呼び方は既存のテスト(`test_storage.py:1144` 付近)に合わせる。

`test/test_merge.py` には、既存の「担当」の項目のテスト(`assignees` が片側だけ変わる・両側が違う値に変わる)をそのまま`parameters`に置き換えたものを 2 つ足す(片側だけ変更は採用、両側の衝突は項目名`パラメータ`で選択になる)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_storage.py test/test_merge.py -k "parameters"`
Expected: FAIL(`FORMAT_VERSION == 9` が偽、`parameters` が読まれない)

- [ ] **Step 3: 実装する**

`models.py:11` の`FORMAT_VERSION = 9` にし、コメントの末尾に`9: タスクのパラメータ`を足す。

`storage.py`:

```python
def _parameter_names(value: Any) -> list[str]:
    """タスクに付けたパラメータの名前。キーがない・null は空。配列でない・文字列以外は ValueError。重複は最初の 1 件を残す。
    登録されていない名前も残す(計算で数えないだけ)。"""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        raise ValueError("パラメータが文字列のリストではありません")
    return list(dict.fromkeys(value))
```

`_task` の`Task(...)`に`parameters=_parameter_names(raw.get("parameters")),`を足し、`_summary`と`_checkpoint`の`replace(...)`に`parameters=[],`を足す。

`merge.py` の`TASK_LABELS` に`"parameters": "パラメータ",`を足す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q test/test_storage.py test/test_merge.py test/test_models.py`
Expected: PASS(version を比べる既存のテストが落ちたら、8 を 9 に直す)

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/models.py src/projectapp/storage.py src/projectapp/merge.py test/test_storage.py test/test_merge.py
git commit -m "feat: タスクのパラメータを保存・読込・3者マージする(version 9)"
```

---

### Task 3: コピーと分解での引き継ぎ

**Files:**
- Modify: `src/projectapp/arrange.py:96-106`(`_plain_copy`)
- Modify: `src/projectapp/decompose.py:130-175`(子のタスク、元のタスクのまとめ化)
- Test: `test/test_arrange.py`・`test/test_summary.py`(`decompose` の純粋関数のテストがあるファイルに置く。`grep -ln "decompose(" test/*.py` で選び、見つからなければ新しい`test/test_decompose.py` を作る)

**Interfaces:**
- Consumes: Task 1 の`Task.parameters`。

- [ ] **Step 1: 失敗するテストを書く**

```python
# test/test_arrange.py(コピーの既存テストの書き方に合わせる)
def test_copying_a_task_keeps_its_parameters_as_an_independent_list() -> None:
    project = Project("p", sections=[Section("s", [Task("a", id="a", parameters=["P"])])])
    copy_task(project, ((0,), 0), ((0,), 1))  # arrange.copy_task(project, src, dst)
    original, copied = project.sections[0].tasks
    assert copied.parameters == ["P"]
    copied.parameters.append("Q")
    assert original.parameters == ["P"]
```

分解のテスト:

```python
def test_children_inherit_the_parameters_and_the_summary_has_none() -> None:
    task = Task("元", id="t", effort_hours=8.0, assignees=[Assignee("田中", 1.0)], parameters=["P"])
    project = Project("p", sections=[Section("s", [task])])
    decompose(project, (0,), 0, [Part("前", 4.0), Part("後", 4.0)])  # decompose(project, path, index, parts)
    summary, first, second = project.sections[0].tasks[:3]
    assert summary.parameters == []
    assert first.parameters == ["P"] and second.parameters == ["P"]
    first.parameters.append("Q")
    assert second.parameters == ["P"]
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_arrange.py test/test_summary.py -k "parameters"`
Expected: FAIL(コピーは`replace`が同じリストを共有する。分解の子は`parameters`が空)

- [ ] **Step 3: 実装する**

`arrange._plain_copy` の`replace(...)`に`parameters=list(original.parameters),`を足す。`decompose.py` の子の`Task(...)`に`parameters=list(task.parameters),`を足し、元のタスクを`replace(task, kind=SUMMARY, ...)`にするところに`parameters=[],`を足す。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -q test/test_arrange.py test/test_summary.py test/test_decompose_ui.py test/test_section_menu.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/arrange.py src/projectapp/decompose.py test/test_arrange.py test/test_summary.py
git commit -m "feat: タスクのコピーと分解でパラメータを引き継ぐ"
```

---

### Task 4: パラメータの改名・削除をタスクに伝える

**Files:**
- Modify: `src/projectapp/ratios.py`(`apply_parameter_edit`・新しい`task_deletion_impacts`・`impact_lines`)
- Modify: `src/projectapp/forms.py:1424,1525-1532,1818`(`impacts` の型と確認文)
- Modify: `src/projectapp/views.py:129,945`
- Test: `test/test_ratios.py`・`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の`Task.parameters`。
- Produces: `apply_parameter_edit(project, edit)` がタスクの`parameters`も写す(改名は追従、削除は外す)。`task_deletion_impacts(project, edit) -> list[tuple[str, int]]`(削除されるパラメータ名 → それを付けたタスクの件数。0 件は含めない)。`impact_lines(project, edit) -> list[str]`(確認ダイアログの行。メンバーの行は`「経験」の「上級」を選んでいるメンバーが2人います`、タスクの行は`「専門」を付けているタスクが3件あります`)。`parameters_panel`/`members_dialog` の`impacts` は`Callable[[ParameterEdit], list[str]]`(行のリスト)になる。

- [ ] **Step 1: 失敗するテストを書く**(`test/test_ratios.py`。`project_with`・`edit_of` は既存のヘルパー)

```python
def test_renaming_follows_in_tasks_and_deleting_removes_the_name() -> None:
    project = project_with(Member("a", 1.0), parameters=PARAMETERS)
    project.tasks.append(Task("t", parameters=["経験", "専門", "ない"]))
    new = [Parameter("スキル", [Level("初級", -0.2)])]
    edit = edit_of(new, {"経験": "スキル", "専門": None}, {"経験": {"初級": "初級"}})
    apply_parameter_edit(project, edit)
    assert project.tasks[0].parameters == ["スキル", "ない"]  # 改名は追従、削除は外す、登録外は触らない


def test_task_deletion_impacts_count_tasks_per_deleted_parameter() -> None:
    project = project_with(Member("a", 1.0), parameters=PARAMETERS)
    project.tasks += [Task("x", parameters=["専門"]), Task("y", parameters=["専門", "経験"]), Task("z", parameters=["経験"])]
    edit = edit_of([EXPERIENCE], {"経験": "経験", "専門": None}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    assert task_deletion_impacts(project, edit) == [("「専門」", 2)]


def test_impact_lines_list_members_then_tasks() -> None:
    project = project_with(Member("a", 1.0, {"専門": "高"}), parameters=PARAMETERS)
    project.tasks.append(Task("x", parameters=["専門"]))
    edit = edit_of([EXPERIENCE], {"経験": "経験", "専門": None}, {"経験": {"初級": "初級", "中級": "中級", "上級": "上級"}})
    assert impact_lines(project, edit) == [
        "「専門」を選んでいるメンバーが1人います",
        "「専門」を付けているタスクが1件あります",
    ]
```

`test/test_views.py` には、パラメータの適用ダイアログで削除を確認する既存のテスト(`parameter-apply` を押して`confirm`が出るもの。なければ`test_applying_parameters_rebuilds...` のすぐ後ろ)に倣って、タスクが付けているパラメータを削除すると確認の文にタスクの行が出て、確認後にタスクの`parameters`から外れるテストを足す。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_ratios.py -k "tasks or impact_lines"`
Expected: FAIL(`cannot import name 'task_deletion_impacts'`)

- [ ] **Step 3: `ratios.py` を実装する**

`apply_parameter_edit` を直す。

```python
def apply_parameter_edit(project: Project, edit: ParameterEdit) -> None:
    """定義を置き換え、全メンバーの選択とタスクに付けたパラメータを更新する。"""
    for member in project.members:
        member.levels = remap_levels(member.levels, edit)
    for task in project.all_tasks():
        # 登録外の名前(対応表にない)は触らない。改名は新しい名前に、削除は外す
        task.parameters = list(
            dict.fromkeys(
                edit.parameter_map.get(name, name) for name in task.parameters if edit.parameter_map.get(name, name) is not None
            )
        )
    project.parameters = edit.parameters
```

新しい関数を足す。

```python
def task_deletion_impacts(project: Project, edit: ParameterEdit) -> list[tuple[str, int]]:
    """パラメータの削除で外れるタスクの数(パラメータの定義の順)。数が 0 のものは含めない。"""
    impacts: list[tuple[str, int]] = []
    for old_parameter, new_parameter in edit.parameter_map.items():
        if new_parameter is None:
            count = sum(1 for t in project.all_tasks() if old_parameter in t.parameters)
            if count:
                impacts.append((f"「{old_parameter}」", count))
    return impacts


def impact_lines(project: Project, edit: ParameterEdit) -> list[str]:
    """削除の確認ダイアログに出す行。メンバーの選択、続いてタスクに付けたもの。"""
    members = [f"{label}を選んでいるメンバーが{count}人います" for label, count in deletion_impacts(project, edit)]
    tasks = [f"{label}を付けているタスクが{count}件あります" for label, count in task_deletion_impacts(project, edit)]
    return members + tasks
```

- [ ] **Step 4: `forms.py` と`views.py` をつなぐ**

`forms.py:1424` と`1818` の`impacts: Callable[[ParameterEdit], list[tuple[str, int]]]` を`list[str]` に直し、`1525-1532` を次にする。

```python
        affected = impacts(edit)
        if affected:
            pending["edit"] = edit
            confirm_text.set_text(
                "\n".join(affected) + "\n削除すると、その選択は外れます(メンバーは判定値 0%、タスクはパラメータなし)"
            )
            confirm.open()
            return
```

`views.py:129` の import を`ParameterEdit, apply_parameter_edit, impact_lines`にし、`945` を`impacts=lambda edit: impact_lines(self.project, edit),`にする。`deletion_impacts` の既存のテストが期待する文言(「…を選んでいるメンバーが…人います」)は`impact_lines`に移ったので、`forms`/`views` のテストで旧い確認文を探しているものは新しい文に直す(`uv run pytest -q test/test_forms.py test/test_views.py -k parameter` で洗い出す)。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -q test/test_ratios.py test/test_forms.py test/test_views.py -k "parameter or ratio or impact"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/projectapp/ratios.py src/projectapp/forms.py src/projectapp/views.py test/test_ratios.py test/test_forms.py test/test_views.py
git commit -m "feat: パラメータの改名・削除をタスクに伝える"
```

---

### Task 5: 編集ダイアログ(選択・換算率の内訳・見直し)

**Files:**
- Modify: `src/projectapp/forms.py:261-330`(`build_task` に`parameters`)
- Modify: `src/projectapp/task_dialog.py:827-1175`(選択欄、比率の作り直し、内訳、見直しの文)
- Test: `test/test_forms.py`・`test/test_task_dialog.py`

**Interfaces:**
- Consumes: Task 1 の`effective_ratio(..., only)`・`Task.parameters`、Task 4 の改名の追従。
- Produces: `build_task(..., parameters: list[str] | None = None)`(`None` は既存の値を保つ。チェックポイントは空にする)。ダイアログの`ui.select`に`mark("task-parameters")`。

- [ ] **Step 1: `build_task` の失敗するテストを書く**(`test/test_forms.py`。既存の`build_task` の呼び方に合わせる)

```python
def test_build_task_takes_the_parameters_and_keeps_them_when_omitted() -> None:
    made = build_task(None, **VALID, parameters=["P", "P", "Q"])  # VALID は既存の最小の引数(なければ同ファイルの書き方に合わせる)
    assert made.parameters == ["P", "Q"]
    edited = build_task(made, **VALID)
    assert edited.parameters == ["P", "Q"]  # 引数がなければ引き継ぐ


def test_build_task_clears_the_parameters_of_a_checkpoint() -> None:
    made = build_task(None, **{**VALID, "kind": TaskKind.CHECKPOINT, "deadline": "2026-10-09 17:00"}, parameters=["P"])
    assert made.parameters == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest -q test/test_forms.py -k "build_task_takes or build_task_clears"`
Expected: FAIL(`unexpected keyword argument 'parameters'`)

- [ ] **Step 3: `build_task` を実装する**

引数に`parameters: list[str] | None = None,`を足す。まとめ(`replace(existing, ...)` の枝)は触らない。通常タスクの`Task` を作る箇所で`parameters=list(dict.fromkeys(base.parameters if parameters is None else parameters)),`を渡す。`_build_checkpoint` の戻りは`parameters=[]`(`Task(...)`を新しく作っているなら既定の空のままでよい。`replace(base, ...)` なら`parameters=[]`を足す)。

- [ ] **Step 4: ダイアログの失敗するテストを書く**(`test/test_task_dialog.py`。既存のテストの開き方〔`open_task_dialog` を呼ぶページの作り方〕に合わせる)

```python
async def test_the_parameter_select_shows_only_when_parameters_exist_and_saves_the_choice(user: User) -> None:
    saved: list[Task] = []
    open_dialog(None, saved.append, parameters=[Parameter("Python", []), Parameter("Java", [])])  # 既存のヘルパー名に合わせる
    await user.should_see(marker="task-parameters")
    user.find(marker="task-parameters").elements.pop().set_value(["Python"])
    user.find(marker="task-name").type("a")
    user.find(marker="save").click()  # 保存ボタンの mark は既存のテストに合わせる
    assert saved[0].parameters == ["Python"]


async def test_no_parameter_select_without_registered_parameters(user: User) -> None:
    open_dialog(None, lambda t: None, parameters=[])
    await user.should_not_see(marker="task-parameters")


async def test_the_conversion_follows_the_chosen_parameters(user: User) -> None:
    member = Member("田中", 1.0, {"Python": "上級", "Java": "初級"})
    parameters = [Parameter("Python", [Level("上級", 0.5)]), Parameter("Java", [Level("初級", -0.5)])]
    task = Task("a", effort_hours=13.0, assignees=[Assignee("田中", 1.0)])
    open_dialog(task, lambda t: None, members=[member], parameters=parameters)
    await user.should_see("換算率 100%")
    user.find(marker="task-parameters").elements.pop().set_value(["Python"])
    await user.should_see("換算率 150%")
    await user.should_see("Pythonを反映")
```

見直しの確認(既存の`reassign-apply` のテストに倣う): 実績のある既存タスクで、パラメータを付けて保存すると`reassign-text` が出る(`換算率が … に変わります`)ことを確かめるテストを足す。

- [ ] **Step 5: 失敗を確かめる**

Run: `uv run pytest -q test/test_task_dialog.py -k "parameter or conversion_follows"`
Expected: FAIL(`task-parameters` がない)

- [ ] **Step 6: ダイアログを実装する**

(a) 比率を作り直せるようにする。`member_list` の組み立てを、生のメンバーと、現在の選択からの比率の更新に分ける。

```python
    raw_members = list(members or [])
    chosen_parameters = list(initial.parameters)  # 付けたパラメータ(選択欄の値。空は全パラメータ)
    # 換算には、パラメータを反映した実効比率を使う(以降は、このコピーだけを見る)
    member_list = [
        Member(m.name, effective_ratio(m, parameters or [], chosen_parameters), work_days=list(m.work_days))
        for m in raw_members
    ]
    for assignee in initial.assignees:  # 一覧にいない担当者も、保存で失わない(相対比率は 100% とみなす)
        if all(m.name != assignee.name for m in member_list):
            member_list.append(Member(assignee.name, 1.0))
    initial_rate = assignees_rate(initial.assignees, member_list)

    def reapply_ratios() -> None:
        """付けたパラメータの選択が変わったとき、比率を作り直す(member_list は担当者の欄と共有なので、その場で書き換える)。"""
        by_name = {m.name: m for m in raw_members}
        for member in member_list:
            if member.name in by_name:
                member.ratio = effective_ratio(by_name[member.name], parameters or [], chosen_parameters)
```

(b) 選択欄を、`category` の次(`すべて`レイアウトのとき)に置き、登録パラメータがなければ作らない。

```python
        parameter_select = None
        if parameters:
            parameter_select = (
                ui.select(
                    [p.name for p in parameters],
                    label="パラメータ(付けると、そのパラメータの判定値だけで相対比率を決める)",
                    value=[name for name in initial.parameters if any(p.name == name for p in parameters)],
                    multiple=True,
                )
                .props("use-chips")
                .classes("w-full")
                .mark("task-parameters")
            )

            def on_parameters_change(event: ValueChangeEventArguments) -> None:
                chosen_parameters[:] = event.value or []
                reapply_ratios()
                refresh_conversion()

            parameter_select.on_value_change(on_parameters_change)
```

`refresh_conversion` は`assignee_fields` と`effort` の定義の後ろにあるので、`on_parameters_change` はそれらより後(`refresh_conversion()` を最初に呼ぶ行の直前)に登録する。選択欄そのものは`category` の直後で作り、`on_value_change` の登録だけを後ろに回す。

(c) 内訳に付けたパラメータを出す。`refresh_conversion` の`detail` を次にする。

```python
            detail = " + ".join(f"{m.name} {m.ratio * 100:g}%×{f * 100:g}%" for m, f in chosen)
            tagged = f"・{'・'.join(chosen_parameters)}を反映" if chosen_parameters else ""
```

ラベルは`f"換算率 {rate * 100:g}%({detail}{tagged})→ ..."`にする。付けたタスクでは例えば`換算率 150%(田中 150%×100%・Pythonを反映)→ 13h は約 1.3日分`と出る(各メンバーの比率は、付けたパラメータを反映した値)。

(d) 表示の切り替え。`refresh_visibility` の`full` のときだけ出す。`for widget in (category, predecessors, priority_box, url_box, color):` に`parameter_select` を足し(`None` でないとき)、まとめの枝では隠す(`for widget in (...)` の隠す側に足す)。チェックポイントのときは隠す(`normal` と`full` の両方のとき出す: `parameter_select.set_visibility(full and normal)`)。

(e) 保存。`build_task(...)` に`parameters=chosen_parameters if parameter_select is not None else None,` を渡す(パラメータが 0 件で欄がないときは、既存の値を保つ)。`new_rate = assignees_rate(result.assignees, member_list)` はそのままでよい(`member_list` の比率は選択に追従済み)。見直しの文を直す。

```python
            review_text.set_text(
                f"担当またはパラメータの変更で、換算率が {initial_rate:.2f} → {new_rate:.2f} に変わります。\n"
                f"残りの作業を新しい条件で見直すと、完了予定は {new_end:%Y-%m-%d %H:%M} です。"
            )
```

既存のテストで`担当の付け替えで`を探しているものは、新しい文に直す。

- [ ] **Step 7: 通ることを確かめる**

Run: `uv run pytest -q test/test_forms.py test/test_task_dialog.py test/test_reassign.py`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/projectapp/forms.py src/projectapp/task_dialog.py test/test_forms.py test/test_task_dialog.py
git commit -m "feat: タスクの編集ダイアログでパラメータを付けられるようにする"
```

---

### Task 6: ドキュメントと全体の確認

**Files:**
- Modify: `CLAUDE.md`(仕様)
- Modify: `docs/development.md`(ファイル形式の注意)
- Modify: `docs/requests.md`(要望 51 の状態)
- Modify: `docs/superpowers/specs/2026-10-24-task-parameters-design.md`(状態、`only` が空のときの扱い)
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: 仕様を`CLAUDE.md`に反映する**

- `パラメータ`の項目(「メンバー〜パラメータは、プロジェクト共通で…」)の次に、タスクのパラメータの項目を足す: 「タスクには、登録したパラメータを複数付けられる(編集ダイアログの`すべて`レイアウトの`パラメータ`欄。登録がなければ欄を出さない)。付けたタスクでは、担当メンバーの相対比率が`基本比率 + 付けたパラメータの判定値の合計`(付けなかったパラメータは数えない。10〜300% に丸める。段階を選んでいなければ判定値 0%)になり、完了予定・ダイアログの換算率・担当者向けファイルの見積もり・担当付け替え時の見直しがその値を使う。付けないタスクは今までどおり全パラメータの合計。ガントチャートのチップには出さない」。
- 「担当の付け替えと完了予定の見直し」の項に、パラメータの付け替えで換算率が変わるときも同じ確認を出すことを足す。
- パラメータの削除の項に、削除はタスクに付けたものも外す(確認に件数を出す)、改名はタスクに追従することを足す。
- 「実装上の注意」の`version`を`現在 9。9 でタスクの`parameters`を足した`にする。タスクのコピー・分解で引き継ぐことを、分解の項に足す。

- [ ] **Step 2: 他のドキュメントを直す**

`docs/development.md` のファイル形式の注意に`tasks[].parameters`(version 9)を足す。`docs/requests.md` の要望 51 を「実装済み(PR は`feature/task-parameters`。実機確認待ち)」にする。設計書の状態も同じにし、「`only` が`None` か空のときは全合計」を、計算の節に書き足す。`.claude/MEMORY.md` の「現在の状況」に要望 51 の実装を、未着手の一覧から 51 を外して書く(`feature/work-days` のリモートは削除済みなので、その記述も直す)。

- [ ] **Step 3: 全体のテストを通す**

Run: `uv run pytest -q -p no:cacheprovider`(約 4 分。バックグラウンドで実行し、合否は出力の最終行と終了コードで確かめる)
Expected: すべて PASS

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "docs: 要望 51(タスクのパラメータ)の仕様と記録を更新する"
```
