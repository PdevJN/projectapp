# アサイン専用画面 段階 4d(試算の前後の比較)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アサイン専用画面のヘッダーに、画面を開いた時点(前)と今の試算(後)の、完了予定と不足(余裕)の変化を `前→後: 完了予定 10/13 → 10/08(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h` の 1 行で出す。変化がないときは出さない。

**Architecture:** 計算と文言は、4a・4b・4c の`shortage.py`に足す純粋関数(`compare_trial`・`compare_changed`・`compare_text`・`compare_hint`・`shortage_gap_text`)。完了予定は`timeline.effective_end`、不足は 4a の`task_shortage`を、前(元のタスク・元のプロジェクト)と後(試算のタスク・`trial_project`)で同じ`now`で求める。画面は、ヘッダーの必要な率の行の下に 1 行足し、`render_required_rate`と同じ流れで更新する。ファイル形式は変えない。

**Tech Stack:** Python 3.13・NiceGUI 4.0.0・pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-25-assign-screen-stage4d-design.md`(4a は`2026-11-22-assign-screen-stage4a-design.md`、4c は`2026-11-24-assign-screen-stage4c-design.md`)

## Global Constraints

- 言語は日本語(UI の文言・コメント・テスト名の説明)。Python 3.13 以上
- ファイル形式は変えない(`version`は 24 のまま)。表示は試算に含めず、`is_dirty`は変えない。元のタスク・元のプロジェクトは書き換えない
- 完了予定の差は日付の差(暦の日数)。時刻だけの違いは変化に数えない
- 変化がない・比べられないときは、行ごと隠す(`set_visibility(False)`)
- マーカーは`assign-`で始める(`assign-compare`)。メインのチャート・ダッシュボードの描画は変えない
- 用語: 予定超過・期限超過・**遅れ**(総称)・**警告**・**割り当て超過**。`遅延`は赤の意味では使わない
- 実装の完了時: smoke(`uv run pytest -m smoke`。失敗したときに限り全テスト`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(ty の 9 件は既存)
- ブランチは`feature/request-168-stage4d`。PR の base は`develop`。マージは利用者の指示を待つ(PR を作って止まる)
- コミットは、ファイルを名指しで`git add`する(`git add -A`は未追跡のサンプルまで拾うので使わない)。末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Plan rulings(設計書との差・補足)

- **前の値は、画面を開くときに 1 回ではなく、描画のたびに求める。** `AssignScreen.now`は、テストや日付をまたぐ操作で変わりうる。前だけを開いた時点の`now`で固定すると、前後で`now`がずれて、残りの工数が食い違う。元のタスク(`self.trial.original`)と元のプロジェクト(`self.project`)は変わらないので、描画のたびに求めても結果は同じで、計算は軽い。設計書の該当の 1 文は Task 3 で直す
- 不足の短い形は`shortage_gap_text`(`あと 7.5h 不足`・`余裕 25.0h`・`ちょうど`)。4a の`shortage_text`(`あと 7.5h 足りません(約 0.2 人)`)と別に持つ(並べやすいよう、人数を省く)
- 前後の比較は、完了予定と不足のどちらも「両方が求まっているとき」だけ出す。片方だけ求まるときは、その項目を出さない
- 画面のテストで基準日を入れるときは、元のプロジェクトのタスク・`trial.original`・`trial.task`の 3 か所に同じ値を入れる(前後で基準日がそろわないと、不足の比較が出ない)

## Review Focus

- 完了予定の日付が同じで時刻だけ違うとき、変化に数えない
- 手で決めた完了予定(`planned_end_manual`)は前後で同じ。不足だけが変わる
- 基準日がないとき、完了予定だけを出す。完了予定も求まらないときは行を出さない
- 画面を開いた直後・元に戻したあとは行が出ない
- 試算の元のタスクを書き換えない・`is_dirty`を変えない

---

### Task 1: `compare_trial`・文言(`shortage.py`)

**Files:**
- Modify: `src/projectapp/shortage.py`
- Test: `test/test_shortage.py`

**Interfaces:**
- Consumes: `task_shortage`・`Shortage`・`shortage_hint`・`Schedule`(`shortage.py`内)、`timeline.effective_end`
- Produces:
  - `@dataclass(frozen=True) TrialCompare(before_end: datetime | None, after_end: datetime | None, before: Shortage | None, after: Shortage | None)`
  - `shortage_gap_text(value: Shortage) -> str`(`あと 7.5h 不足`・`余裕 25.0h`・`ちょうど`)
  - `compare_trial(before_task: Task, before_project: Project, after_task: Task, after_project: Project, holidays: dict[date, str], now: datetime) -> TrialCompare`
  - `compare_text(value: TrialCompare) -> str`(変化がなければ空の文字列)
  - `compare_changed(value: TrialCompare) -> bool`
  - `compare_hint(value: TrialCompare) -> str`

- [ ] **Step 1: Write the failing tests**

`test/test_shortage.py`の import に`TrialCompare`・`compare_changed`・`compare_hint`・`compare_text`・`compare_trial`・`shortage_gap_text`を足し、末尾に追記する(`MON`・`FRI`・`project_of`・`task_of`は既存。`MON` = 2026-10-05 月 9:00、1 人 32.5h/週。田中 100%・40h の完了予定は 10/13 10:00、田中+鈴木 100% は 10/08 09:30、田中+鈴木 50% は 10/09 09:40)。

```python
def compared(before: Task, after: Task, now: datetime = MON) -> TrialCompare:
    return compare_trial(before, project_of(before), after, project_of(after), {}, now)


def test_the_gap_text_is_short_and_has_no_head_count() -> None:
    assert shortage_gap_text(Shortage(40.0, 32.5, 32.5, FRI, "締切")) == "あと 7.5h 不足"
    assert shortage_gap_text(Shortage(30.0, 32.5, 32.5, FRI, "締切")) == "余裕 2.5h"
    assert shortage_gap_text(Shortage(32.5, 32.5, 32.5, FRI, "締切")) == "ちょうど"


def test_adding_a_member_moves_the_end_earlier_and_turns_a_shortage_into_room() -> None:
    value = compared(
        task_of(), task_of(assignees=[Assignee("田中"), Assignee("鈴木")])
    )
    assert compare_changed(value)
    assert compare_text(value) == (
        "前→後: 完了予定 10/13 → 10/08(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h"
    )


def test_removing_a_member_moves_the_end_later() -> None:
    value = compared(
        task_of(assignees=[Assignee("田中"), Assignee("鈴木")]), task_of()
    )
    assert compare_text(value) == (
        "前→後: 完了予定 10/08 → 10/13(5 日遅れる)・余裕 25.0h → あと 7.5h 不足"
    )


def test_a_smaller_change_shows_the_days_and_the_new_room() -> None:
    value = compared(
        task_of(), task_of(assignees=[Assignee("田中"), Assignee("鈴木", 0.5)])
    )
    assert compare_text(value) == (
        "前→後: 完了予定 10/13 → 10/09(4 日早まる)・あと 7.5h 不足 → 余裕 8.8h"
    )


def test_identical_tasks_show_nothing() -> None:
    value = compared(task_of(), task_of())
    assert not compare_changed(value) and compare_text(value) == ""


def test_a_manual_end_stays_and_only_the_shortage_changes() -> None:
    manual = datetime(2026, 10, 12, 17)
    value = compared(
        task_of(planned_end=manual, planned_end_manual=True),
        task_of(
            planned_end=manual,
            planned_end_manual=True,
            assignees=[Assignee("田中"), Assignee("鈴木")],
        ),
    )
    assert compare_text(value) == "前→後: あと 7.5h 不足 → 余裕 25.0h"


def test_without_a_due_only_the_end_is_compared() -> None:
    value = compared(
        task_of(deadline=None),
        task_of(deadline=None, assignees=[Assignee("田中"), Assignee("鈴木")]),
    )
    assert value.before is None and value.after is None
    assert compare_text(value) == "前→後: 完了予定 10/13 → 10/08(5 日早まる)"


def test_the_same_date_with_a_different_time_is_not_a_change() -> None:
    # 田中 100% と 田中 100%・鈴木 1% は、どちらも 10/13 の日のうちに終わる(時刻は違う)
    before = task_of(deadline=None)
    after = task_of(deadline=None, assignees=[Assignee("田中"), Assignee("鈴木", 0.01)])
    value = compared(before, after)
    assert value.before_end is not None and value.after_end is not None
    assert value.before_end.date() == value.after_end.date()
    assert not compare_changed(value) and compare_text(value) == ""


def test_the_hint_gives_the_before_and_after_basis() -> None:
    value = compared(
        task_of(), task_of(assignees=[Assignee("田中"), Assignee("鈴木")])
    )
    hint = compare_hint(value)
    assert "前: 残り 40.0h / 稼働 32.5h" in hint
    assert "後: 残り 40.0h / 稼働 65.0h" in hint


def test_comparing_does_not_change_the_tasks() -> None:
    before = task_of()
    after = task_of(assignees=[Assignee("田中"), Assignee("鈴木")])
    compared(before, after)
    assert [a.name for a in before.assignees] == ["田中"]
    assert [a.name for a in after.assignees] == ["田中", "鈴木"]
```

Run: `uv run pytest test/test_shortage.py -q -k "gap_text or adding_a_member or removing_a_member or smaller_change or identical_tasks or manual_end_stays or without_a_due_only or same_date_with or hint_gives_the_before or comparing_does_not"`
Expected: FAIL(`ImportError: cannot import name 'TrialCompare'`)

注: `test_the_same_date_with_a_different_time_is_not_a_change`の鈴木 1% は、実計算で完了予定が 10/13 09:36(田中だけは 10/13 10:00)になり、日付は同じで時刻だけ違う(確認済み)。

- [ ] **Step 2: Write minimal implementation**

`src/projectapp/shortage.py`の import に、`from projectapp.timeline import (...)`へ`effective_end`を足す。ファイルの末尾に追記する。

```python
@dataclass(frozen=True)
class TrialCompare:
    before_end: datetime | None  # 前(画面を開いた時点)の完了予定
    after_end: datetime | None  # 後(今の試算)の完了予定
    before: Shortage | None  # 前の不足。基準日がないなど出せないときは None
    after: Shortage | None


def shortage_gap_text(value: Shortage) -> str:
    """比較用の短い形。`あと 7.5h 不足`・`余裕 25.0h`・`ちょうど`(人数は省く)。"""
    kind = value.kind
    if kind == "ちょうど":
        return "ちょうど"
    hours = abs(value.gap)
    return f"あと {hours:.1f}h 不足" if kind == "不足" else f"余裕 {hours:.1f}h"


def compare_trial(
    before_task: Task,
    before_project: Project,
    after_task: Task,
    after_project: Project,
    holidays: dict[date, str],
    now: datetime,
) -> TrialCompare:
    """試算の前後の、完了予定と不足(要望 168 段階 4d)。求まらない項目は None。元は変えない。"""

    def side(task: Task, project: Project) -> tuple[datetime | None, Shortage | None]:
        schedule = Schedule(project, holidays)
        end = effective_end(task, project, holidays, schedule)
        value = task_shortage(task, project, holidays, now, schedule)
        return end, None if isinstance(value, str) else value

    before_end, before = side(before_task, before_project)
    after_end, after = side(after_task, after_project)
    return TrialCompare(before_end, after_end, before, after)


def _compare_parts(value: TrialCompare) -> list[str]:
    parts: list[str] = []
    if value.before_end is not None and value.after_end is not None:
        days = (value.after_end.date() - value.before_end.date()).days
        if days != 0:
            word = "遅れる" if days > 0 else "早まる"
            parts.append(
                f"完了予定 {value.before_end:%m/%d} → {value.after_end:%m/%d}"
                f"({abs(days)} 日{word})"
            )
    if value.before is not None and value.after is not None:
        before, after = shortage_gap_text(value.before), shortage_gap_text(value.after)
        if before != after:
            parts.append(f"{before} → {after}")
    return parts


def compare_changed(value: TrialCompare) -> bool:
    """前後で、完了予定の日付か、不足の文言が変わったか。"""
    return bool(_compare_parts(value))


def compare_text(value: TrialCompare) -> str:
    """`前→後: 完了予定 10/13 → 10/08(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h`。変化がなければ空。"""
    parts = _compare_parts(value)
    return f"前→後: {'・'.join(parts)}" if parts else ""


def compare_hint(value: TrialCompare) -> str:
    """ホバーの文字。前後それぞれの`残り / 稼働(基準日)`。出せない側は書かない。"""
    parts = []
    if value.before is not None:
        parts.append(f"前: {shortage_hint(value.before)}")
    if value.after is not None:
        parts.append(f"後: {shortage_hint(value.after)}")
    return "。".join(parts)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest test/test_shortage.py -q`
Expected: すべて PASS(既存 56 件+追加 10 件)

- [ ] **Step 4: Commit**

```bash
uvx ruff format src test && uvx ruff check
git add src/projectapp/shortage.py test/test_shortage.py
git commit -m "feat: 試算の前後の完了予定と不足を比べる compare_trial を足す(要望 168 段階 4d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ヘッダーに前後の比較の行を出す(`assign_screen.py`)

**Files:**
- Modify: `src/projectapp/assign_screen.py`(import・`__init__`・ヘッダー・`render_required_rate`の次・`open`の`render_required_rate()`の次・`refresh`)
- Test: `test/test_assign_screen.py`

**Interfaces:**
- Consumes: Task 1 の`compare_trial`・`compare_changed`・`compare_text`・`compare_hint`
- Produces: `AssignScreen.compare_label: ui.label | None`・`AssignScreen.render_compare(project: Project | None = None) -> None`。マーカーは`assign-compare`

- [ ] **Step 1: Write the failing tests**

`test/test_assign_screen.py`の末尾に追記する(`open_team_screen`・`datetime`・`is_dirty`は既存。試算のタスクは、工数 40h・担当は田中 100%・11/16 月開始で、完了予定は 11/24。鈴木を週 0 に足すと 11/19)。

```python
def set_due(screen: AssignScreen, when: datetime | None) -> None:
    """前後で基準日をそろえる(元のプロジェクト・開いた時点・試算の 3 か所)。"""
    for task in (screen.project.tasks[0], screen.trial.original, screen.trial.task):
        task.deadline = when


async def test_the_compare_row_is_hidden_right_after_opening(user: User) -> None:
    screen, _ = await open_team_screen(user)
    set_due(screen, datetime(2026, 11, 20, 17))
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("あと 7.5h 足りません")  # 不足の行は出ている
    await user.should_not_see(marker="assign-compare")


async def test_the_compare_row_shows_the_end_and_the_shortage_after_adding_a_member(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    set_due(screen, datetime(2026, 11, 20, 17))
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    screen.drop_member("鈴木", 0, None)
    await user.should_see(
        "前→後: 完了予定 11/24 → 11/19(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h"
    )
    label = user.find(marker="assign-compare").elements.pop()
    assert "前: 残り 40.0h" in str(label.props.get("title", ""))


async def test_the_compare_row_hides_again_when_the_member_is_removed(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    set_due(screen, datetime(2026, 11, 20, 17))
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    screen.drop_member("鈴木", 0, None)
    await user.should_see(marker="assign-compare")
    screen.remove_member_at("鈴木", 0, None)
    await user.should_see("あと 7.5h 足りません")
    await user.should_not_see(marker="assign-compare")


async def test_without_a_due_the_compare_row_shows_only_the_end(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    screen.drop_member("鈴木", 0, None)
    await user.should_see("前→後: 完了予定 11/24 → 11/19(5 日早まる)")
    assert "不足" not in label_text(user, "assign-compare")


async def test_the_compare_row_does_not_change_the_dirty_flag(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.drop_member("鈴木", 0, None)
    await user.should_see(marker="assign-compare")
    dirty = is_dirty(screen.trial)
    screen.refresh()
    assert is_dirty(screen.trial) == dirty
    assert screen.trial.original.assignees[0].allocation == 1.0
```

Run: `uv run pytest test/test_assign_screen.py -q -k compare_row`
Expected: FAIL(`assign-compare`が見つからない)

- [ ] **Step 2: Write minimal implementation**

`assign_screen.py`の`from projectapp.shortage import (...)`に`compare_changed`・`compare_hint`・`compare_text`・`compare_trial`を足す(アルファベット順に合わせる)。`__init__`の`self.required_label`の次に`self.compare_label: ui.label | None = None`を足す。

ヘッダーの`required_label`を作る行の次(`self.required_label.set_visibility(False)`の次)に追加する。

```python
                    self.compare_label = (
                        ui.label("").classes("text-body2").mark("assign-compare")
                    )
                    self.compare_label.set_visibility(False)
```

`render_required_rate`の次に追加する。

```python
    def render_compare(self, project: Project | None = None) -> None:
        """画面を開いた時点(前)と今の試算(後)の、完了予定と不足の変化を出す。変化がないときは行ごと隠す。"""
        label = self.compare_label
        if label is None:
            return
        value = compare_trial(
            self.trial.original,
            self.project,
            self.trial.task,
            project or trial_project(self.project, self.trial),
            self.holidays,
            self.now(),
        )
        if not compare_changed(value):
            label.set_visibility(False)
            return
        label.set_text(compare_text(value))
        label.props(f'title="{compare_hint(value)}"')
        label.set_visibility(True)
```

呼び出しは、`open`の`self.render_required_rate()`の次と、`refresh`の`self.render_required_rate(trial)`の次に`render_compare`を足す(`refresh`は`self.render_compare(trial)`)。

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest test/test_assign_screen.py -q`
Expected: すべて PASS。`test_the_compare_row_hides_again_...`で、元に戻したあとに行が残るときは、`remove_member_at`の後の`weekly_crew`が元の担当と同じ稼働量か(田中だけの週が並ぶ)を確かめる

- [ ] **Step 4: smoke・lint・型**

Run: `uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: smoke 全 PASS・ruff 問題なし・ty は既存の 9 件のみ

- [ ] **Step 5: Commit**

```bash
git add src/projectapp/assign_screen.py test/test_assign_screen.py
git commit -m "feat: アサイン画面のヘッダーに試算の前後の比較の行を出す(要望 168 段階 4d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 文書の更新と PR

**Files:**
- Modify: `docs/superpowers/specs/2026-11-25-assign-screen-stage4d-design.md`・`docs/requests.md`・`docs/development.md`・`.claude/spec/dashboard.md`

- [ ] **Step 1: 設計書を実装に合わせる**

設計書の「画面」の最初の項目(`前の値は、画面を開くとき(open)に、元のタスクとプロジェクトで 1 回求めて持つ(self.before)`)を、`前の値は、描画のたびに、元のタスク(trial.original)と元のプロジェクト(self.project)で求める(now が変わっても前後でそろえるため。元は変わらないので結果は同じで、計算は軽い)`に直す。「確かめること」に、結果(完了予定の差は日付の差・手で決めた完了予定は前後で同じ・開いた直後は行が出ない。いずれもテストで確認)を 1 行で足す。

- [ ] **Step 2: 仕様・構成・要望の記録を更新する**

- `.claude/spec/dashboard.md`: `grep -n "段階 4c(必要な割り当て率)" .claude/spec/dashboard.md`で見つかる 4c の記述の次に、4d の説明を足す(試算に変更があるときだけ、必要な率の行の下に`前→後: 完了予定 10/13 → 10/08(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h`を出す。前は元のタスク、後は今の試算。日付の差は暦の日数。不足は基準日があるときだけ。変化がなければ行ごと隠す。ホバーに前後の`残り / 稼働`。試算には含めず保存しない。`shortage.py`の`compare_trial`)
- `docs/development.md`の`shortage.py`の行に、`TrialCompare`・`compare_trial`(試算の前後の比較。要望 168 段階 4d)を足す
- `docs/requests.md`: 要望 168 の状態の段階 4d を`実装済み(設計書: ...stage4d-design.md・計画: ...stage4d.md。実機確認待ち)`にする。段階 4(視点)がこれで一通りそろったことを 1 文で書く

- [ ] **Step 3: 全体の確認と PR**

Run: `uv run pytest -m smoke -q && uvx ruff check && uvx ruff format src test && uvx ty check src`
Expected: 通る

```bash
git add docs/superpowers/specs/2026-11-25-assign-screen-stage4d-design.md docs/requests.md docs/development.md .claude/spec/dashboard.md
git commit -m "docs: アサイン画面の試算の前後の比較(段階 4d)の仕様と構成を書く(要望 168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/request-168-stage4d
gh pr create --base develop --title "feat: アサイン画面の試算の前後の比較(要望 168 段階 4d)" --body "..."
```

PR の本文は、変更の要約・テスト結果・実機確認の手順(基準日のあるタスクで、メンバーを足して`前→後`の行が出る・元に戻すと消える・基準日がなければ完了予定だけが出る)を書き、末尾に`🤖 Generated with [Claude Code](https://claude.com/claude-code)`を付ける。PR を作って止まる。マージは利用者の指示を待つ。
