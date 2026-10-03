# タスク編集ダイアログの見直し 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タスクの追加・編集ダイアログに、色のプレビュー、日付選択(時刻はチェックで追加)、開始・終了の横並び、閉じるときの確認、タスクの削除を加える。

**Architecture:** ダイアログの部品(`PriorityChips`、新規の `DateTimeFields`、`open_task_dialog`)を新モジュール `task_dialog.py` に切り出す。入力の検証(`build_task` ほか)と、日付・時刻の純粋関数(`default_times`、`compose_datetime`、`needs_time`)は `forms.py` に置く。ダイアログは日付と時刻から `YYYY-MM-DDTHH:MM` の文字列を組み立てて、既存の `build_task` に渡すので、検証と自動算出の終了の判定は変えない。削除は `views.MainView.delete_task` が行う。

**Tech Stack:** Python 3.13、NiceGUI(`ui.date`、`ui.time`、`ui.chip`、`ui.dialog`)、pytest(`nicegui.testing.User`)、`uvx ty`。

**Spec:** `docs/superpowers/specs/2026-10-03-task-edit-dialog-design.md`

## Global Constraints

- 画面の言語は日本語。コメントも日本語で、既存のコードの密度・書き方に合わせる。
- Python 3.13 以上。ライブラリは NiceGUI。
- データ形式は変えない(`Task.start` / `Task.end` は `datetime`、保存形式もそのまま)。
- 時刻を指定しないとき: 開始 = `Project.work_start`、終了 = 始業 + 標準稼働時間 `8:00` + 昼休憩 `1:00`(始業 09:00 なら 18:00)。標準稼働時間と昼休憩は固定の定数で、プロジェクトの設定ではない。
- 始業が15:00以降のときの本来の対応は保留事項(別ブランチ)。このブランチでは、補う終了を `23:59` で頭打ちにする暫定の1行だけを入れる。
- 日付の入力は、テキスト入力 + カレンダーアイコンで開く `ui.date` のダイアログ(ネイティブの `type=date` は使わない)。時刻も同じ方式。
- 閉じる確認は、変更があるときだけ。ボタンは「保存」「破棄して閉じる」「編集に戻る」。
- 削除は確認ダイアログつき。削除しても保存は自動で行わない(編集中の判定に入る)。
- 優先度に赤は使わない(予定超過の背景色と競合する)。
- 各タスクの完了ごとに `uv run pytest -q` と `uvx ty check src` を通してからコミットする。コミットメッセージは日本語で、末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付ける。
- プッシュ・マージは、ユーザーの許可を得てから行う。

## Review Focus

仕様が暗に求めるが、各タスクの主なテストでは押さえない入力・状況。該当するタスクに、それぞれテストを置いてある。

- 開始日より前の終了日を、日付だけで入れた(時刻なし)→ 「終了は開始以降の日時にしてください」で保存されない(Task 4)。
- 日付に存在しない値(`2026-13-45`)を入れた → 「日時の形式が正しくありません」で保存されない(Task 4)。
- 終了日を消して保存した → 終了は `None`(空)になる(Task 4)。
- 自動算出の終了(`15:30` など、補う終了と違う時刻)を持つタスクを、開いて何も変えずに保存した → 終了と `end_auto` が変わらない(Task 4)。
- 名前を消して「保存」で閉じる確認から保存した → エラーを出して、編集ダイアログが残り、入力が消えない(Task 5)。
- 複数のタスクがあるとき、選んだタスクだけが消える。セクション内とセクションなしの両方(Task 6)。

---

### Task 1: 色のプレビュー

**Files:**
- Modify: `src/projectapp/forms.py`(`open_task_dialog` の `ui.color_input`)
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: なし
- Produces: 色の入力に `task-color` のマーカーが付き、`preview=True` になる。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の `test_task_dialog_status_select_uses_full_width` の直前に追加する。

```python
async def test_task_dialog_color_shows_a_preview(user: User) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, lambda t: None))

    await user.open("/")
    user.find("open").click()
    color = user.find(marker="task-color").elements.pop()
    assert color.preview is True
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py -q -k color_shows_a_preview`
Expected: FAIL(`task-color` が見つからない)

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py` の `open_task_dialog` 内、次の1行を置き換える。

```python
        color = ui.color_input("色", value=initial.color)
```

を

```python
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "$(cat <<'EOF'
タスク編集の色の入力に、選んだ色のプレビューを表示する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: ダイアログを `task_dialog.py` に切り出す(動作は変えない)

**Files:**
- Create: `src/projectapp/task_dialog.py`
- Modify: `src/projectapp/forms.py`(`PRIORITY_COLORS`・`PriorityChips`・`open_task_dialog` を削除。`_format` を `format_datetime` に改名)
- Modify: `src/projectapp/views.py`(import)
- Modify: `test/test_forms.py`(import)
- Modify: `docs/development.md`(モジュール構成の表)

**Interfaces:**
- Consumes: `forms.build_task`、`forms.format_datetime`(この Task で公開名にする)
- Produces: `projectapp.task_dialog.open_task_dialog(task: Task | None, on_save: Callable[[Task], object]) -> None`(この Task では引数・戻り値を変えない)、`PriorityChips`、`PRIORITY_COLORS`

- [ ] **Step 1: `_format` を `format_datetime` に改名する**

```bash
sed -i '' 's/\b_format(/format_datetime(/g' src/projectapp/forms.py
grep -n "_format\|format_datetime" src/projectapp/forms.py
```
Expected: `def format_datetime(` と、`build_task` 内の呼び出し(3か所)、`open_task_dialog` 内(2か所)。`_format` は残らない。

- [ ] **Step 2: `task_dialog.py` を作る**

`src/projectapp/task_dialog.py`:

```python
"""タスクの追加・編集ダイアログ。入力の検証は forms.py の build_task に任せる。"""

from collections.abc import Callable

from nicegui import ui

from projectapp.forms import build_task, format_datetime
from projectapp.models import Priority, Status, Task

# 赤は「予定超過」の背景色と意味が競合するため、優先度には使わない
PRIORITY_COLORS = {Priority.HIGH: "orange", Priority.MEDIUM: "amber", Priority.LOW: "blue"}


class PriorityChips:
    """優先度を色付きチップで選ぶ。選択は常に1つで、選択中は塗りつぶし、未選択は枠線のみ。"""

    def __init__(self, value: Priority) -> None:
        self.value = value
        ui.label("優先度").classes("text-caption text-grey")
        self._chips: dict[Priority, ui.chip] = {}
        with ui.row().classes("gap-2"):
            for priority in Priority:
                self._chips[priority] = ui.chip(
                    priority.value,
                    color=PRIORITY_COLORS[priority],
                    on_click=lambda _, p=priority: self.select(p),
                ).mark(f"priority-{priority.name}")
        self._refresh()

    def select(self, priority: Priority) -> None:
        self.value = priority
        self._refresh()

    def _refresh(self) -> None:
        for priority, chip in self._chips.items():
            selected = priority == self.value
            chip.props(remove="outline" if selected else "", add="" if selected else "outline")
            filled_text = "black" if priority == Priority.MEDIUM else "white"  # 黄は白だと読みにくい
            chip.props["text-color"] = filled_text if selected else PRIORITY_COLORS[priority]
            chip.update()


def open_task_dialog(task: Task | None, on_save: Callable[[Task], object]) -> None:
    initial = task or Task("")
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        name = ui.input("名前", value=initial.name).mark("task-name")
        start = ui.input("開始日時", value=format_datetime(initial.start)).props(
            "type=datetime-local"
        ).mark("task-start")
        end = ui.input("終了日時", value=format_datetime(initial.end)).props(
            "type=datetime-local"
        ).mark("task-end")
        effort = ui.number("工数(時間)", value=initial.effort_hours, min=0)
        priority = PriorityChips(initial.priority)
        status = (
            ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
            .classes("w-full")
            .mark("task-status")
        )
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )
        assignee = ui.input("担当者", value=initial.assignee or "")
        error = ui.label("").classes("text-negative").mark("form-error")

        def save() -> None:
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    start=start.value or "",
                    end=end.value or "",
                    effort_hours=effort.value,
                    priority=priority.value,
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).mark("task-save")
    dialog.open()
```

- [ ] **Step 3: `forms.py` から移した部分を削除する**

`src/projectapp/forms.py` から、次を丸ごと削除する: `# 赤は「予定超過」...` のコメント行から、`PRIORITY_COLORS`、`class PriorityChips`、`def open_task_dialog` の終わり(`dialog.open()`)まで。`forms.py` の docstring を `"""タスク・セクションの追加・編集の入力検証と、ファイル・名前・設定のダイアログ。"""` に直す。

- [ ] **Step 4: import を直す**

`src/projectapp/views.py`: `from projectapp.forms import (...)` の一覧から `open_task_dialog,` を消し、その import 文の直後に次を足す。

```python
from projectapp.task_dialog import open_task_dialog
```

`test/test_forms.py`: `from projectapp.forms import (...)` の一覧から `open_task_dialog,` を消し、直後に次を足す。

```python
from projectapp.task_dialog import open_task_dialog
```

- [ ] **Step 5: `docs/development.md` の表を直す**

`forms.py` の行を `| `forms.py` | タスク・セクションの入力検証、プロジェクト名の入力・ファイル一覧・未保存の確認ダイアログ、稼働時間の設定ダイアログと入力検証 |` に置き換え、その下に次の行を足す。

```
| `task_dialog.py` | タスクの追加・編集ダイアログ(優先度チップ、日付・時刻の入力、閉じる確認、削除) |
```

- [ ] **Step 6: 動作が変わらないことを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全件 PASS(件数は Task 1 の後と同じ)、`All checks passed!`

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/task_dialog.py src/projectapp/forms.py src/projectapp/views.py test/test_forms.py docs/development.md
git commit -m "$(cat <<'EOF'
タスクの編集ダイアログを task_dialog.py に切り出す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 日付・時刻の純粋関数

**Files:**
- Modify: `src/projectapp/forms.py`
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: なし
- Produces(Task 4 が使う):
  - `STANDARD_WORK_HOURS = 8`、`LUNCH_HOURS = 1`
  - `default_times(work_start: time) -> tuple[time, time]` — (補う開始, 補う終了)。終了は始業 + 9h を、`23:59` で頭打ちにする。
  - `compose_datetime(day: str, clock: str) -> str` — 日付が空なら `""`。日付があるとき、時刻が `HH:MM` でなければ `ValueError("時刻の形式が正しくありません")`。それ以外は `"{day}T{clock}"`(前後の空白は除く)。
  - `needs_time(start: datetime | None, end: datetime | None, work_start: time) -> bool` — 開始が始業と違うか、終了が補う終了と違えば `True`(分単位で比べる)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の import に `compose_datetime`、`default_times`、`needs_time` を足し、ファイルの末尾に追加する。

```python
def test_default_times_adds_the_standard_day_and_lunch() -> None:
    assert default_times(time(9, 0)) == (time(9, 0), time(18, 0))
    assert default_times(time(8, 30)) == (time(8, 30), time(17, 30))


def test_default_times_caps_the_end_at_2359() -> None:
    # 暫定: 始業が15:00以降だと始業+9hが24時以上になり、表せない(保留事項)
    assert default_times(time(14, 59)) == (time(14, 59), time(23, 59))
    assert default_times(time(15, 0)) == (time(15, 0), time(23, 59))
    assert default_times(time(17, 0)) == (time(17, 0), time(23, 59))


def test_compose_datetime_joins_day_and_clock() -> None:
    assert compose_datetime("2026-10-05", "09:00") == "2026-10-05T09:00"
    assert compose_datetime(" 2026-10-05 ", " 09:00 ") == "2026-10-05T09:00"


def test_compose_datetime_ignores_the_clock_when_the_day_is_empty() -> None:
    assert compose_datetime("", "09:00") == ""
    assert compose_datetime("  ", "") == ""
    assert compose_datetime("", "xx") == ""


@pytest.mark.parametrize("clock", ["", "25:00", "9am", "09:60", "09"])
def test_compose_datetime_rejects_a_bad_clock_when_the_day_is_given(clock: str) -> None:
    with pytest.raises(ValueError, match="時刻の形式"):
        compose_datetime("2026-10-05", clock)


def test_needs_time_is_false_for_default_or_empty_times() -> None:
    nine = time(9, 0)
    assert needs_time(None, None, nine) is False
    assert needs_time(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 7, 18, 0), nine) is False
    assert needs_time(datetime(2026, 10, 5, 9, 0), None, nine) is False
    assert needs_time(None, datetime(2026, 10, 7, 18, 0), nine) is False


def test_needs_time_is_true_when_either_time_differs() -> None:
    nine = time(9, 0)
    assert needs_time(datetime(2026, 10, 5, 9, 30), None, nine) is True
    assert needs_time(None, datetime(2026, 10, 7, 15, 30), nine) is True


def test_needs_time_compares_in_minutes() -> None:
    # 秒を持つ終了(自動算出)でも、同じ分なら補う時刻と同じとみなす
    assert needs_time(None, datetime(2026, 10, 7, 18, 0, 30), time(9, 0)) is False


def test_needs_time_follows_the_work_start() -> None:
    assert needs_time(datetime(2026, 10, 5, 8, 30), datetime(2026, 10, 7, 17, 30), time(8, 30)) is False
    assert needs_time(datetime(2026, 10, 5, 8, 30), datetime(2026, 10, 7, 17, 30), time(9, 0)) is True
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py -q`
Expected: FAIL(`ImportError: cannot import name 'compose_datetime'`)

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py` の `DATETIME_FORMAT = ...` の行の直後に定数を足す。

```python
STANDARD_WORK_HOURS = 8  # 時刻を指定しないときに補う終了の、標準稼働時間(固定)
LUNCH_HOURS = 1  # 同じく、昼休憩(固定。稼働設定の対象外)
```

`format_datetime` の定義の直後(`def open_...` の前の、純粋関数が並ぶ位置)に追加する。

```python
def default_times(work_start: time) -> tuple[time, time]:
    """時刻を指定しないときに補う開始・終了の時刻。終了は始業 + 標準稼働時間 + 昼休憩。"""
    start = work_start.replace(second=0, microsecond=0)
    minutes = start.hour * 60 + start.minute + (STANDARD_WORK_HOURS + LUNCH_HOURS) * 60
    minutes = min(minutes, 24 * 60 - 1)  # 暫定: 24時以降は表せないので23:59で頭打ち(保留事項)
    return start, time(minutes // 60, minutes % 60)


def compose_datetime(day: str, clock: str) -> str:
    """日付と時刻の入力から、build_taskに渡す文字列を作る。日付が空なら空(時刻は無視する)。"""
    day, clock = day.strip(), clock.strip()
    if not day:
        return ""
    try:
        datetime.strptime(clock, "%H:%M")
    except ValueError:
        raise ValueError("時刻の形式が正しくありません") from None
    return f"{day}T{clock}"


def needs_time(start: datetime | None, end: datetime | None, work_start: time) -> bool:
    """開始・終了が、補う時刻と違うか。違えば、ダイアログは時刻の入力を開いた状態で出す。"""
    default_start, default_end = default_times(work_start)

    def minute(moment: datetime) -> time:
        return moment.time().replace(second=0, microsecond=0)

    return (start is not None and minute(start) != default_start) or (
        end is not None and minute(end) != default_end
    )
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "$(cat <<'EOF'
日付・時刻の入力に使う純粋関数(補う時刻の算出と文字列の組み立て)を追加

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 日付・時刻の入力と、開始・終了の横並び

**Files:**
- Modify: `src/projectapp/task_dialog.py`
- Modify: `src/projectapp/views.py`(`work_start` を渡す)
- Modify: `test/test_forms.py`(古いマーカーを使うテストの書き換え)
- Modify: `test/test_views.py`(同上)
- Create: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: `forms.default_times`、`forms.compose_datetime`、`forms.needs_time`、`forms.format_datetime`(Task 3 まで)
- Produces:
  - `open_task_dialog(task: Task | None, on_save: Callable[[Task], object], work_start: time = DEFAULT_WORK_START) -> None`(`DEFAULT_WORK_START` は `projectapp.models`)
  - `DateTimeFields(start: datetime | None, end: datetime | None, work_start: time)` — 属性 `start_day`、`start_time`、`end_day`、`end_time`(`ui.input`)、`use_time`(`ui.checkbox`)。メソッド `start_text() -> str`、`end_text() -> str`(`compose_datetime` の結果。`ValueError` を出しうる)、`state() -> tuple[str, str, str, str]`(日付・時刻の生の入力。Task 5 の変更判定に使う)
  - マーカー: `task-start-date`、`task-start-time`、`task-end-date`、`task-end-time`、`task-use-time`、日付選択のアイコン `open-start-date-picker`・`open-end-date-picker`、時刻選択のアイコン `open-start-time-picker`・`open-end-time-picker`、選択部品 `start-date-picker` ほか(`{start|end}-{date|time}-picker`)、OK ボタン `{start|end}-{date|time}-picker-ok`

- [ ] **Step 1: 古いマーカーを使う既存テストを書き換える**

`test/test_forms.py` の `test_task_dialog_saves_a_valid_task` を次に置き換える。

```python
async def test_task_dialog_saves_a_valid_task(user: User) -> None:
    saved: list[Task] = []

    @ui.page("/")
    def index() -> None:
        ui.button("open", on_click=lambda: open_task_dialog(None, saved.append))

    await user.open("/")
    user.find("open").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert [t.name for t in saved] == ["設計"]
    assert saved[0].start == datetime(2026, 10, 5, 9, 0)
    assert saved[0].end == datetime(2026, 10, 7, 18, 0)
```

`test_task_dialog_prefills_when_editing` の最後の行を置き換える。

```python
    assert user.find(marker="task-start-date").elements.pop().value == "2026-10-05"
```

`test/test_views.py` の `test_add_section_then_task_shows_a_bar` の2行を置き換える。

```python
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
```

- [ ] **Step 2: 新しいテストを書く**

`test/test_task_dialog.py`(新規):

```python
from datetime import datetime, time

from nicegui import ui
from nicegui.testing import User

from projectapp.models import Task
from projectapp.task_dialog import open_task_dialog


def mount_dialog(
    task: Task | None, saved: list[Task], work_start: time = time(9, 0)
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_task_dialog(task, saved.append, work_start=work_start),
        )


async def open_dialog(user: User) -> None:
    await user.open("/")
    user.find("open").click()


async def test_dates_only_fill_the_default_times(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 9, 0)
    assert saved[0].end == datetime(2026, 10, 7, 18, 0)


async def test_default_times_follow_the_work_start(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, work_start=time(8, 30))
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 8, 30)
    assert saved[0].end == datetime(2026, 10, 7, 17, 30)


async def test_time_inputs_are_hidden_until_the_checkbox_is_checked(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")
    await user.should_not_see(marker="task-end-time")
    user.find(marker="task-use-time").click()
    await user.should_see(marker="task-start-time")
    await user.should_see(marker="task-end-time")


async def test_checked_times_are_used(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-end-time").clear().type("16:45")
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 10, 15)
    assert saved[0].end == datetime(2026, 10, 7, 16, 45)


async def test_unchecking_resets_the_times_to_the_defaults(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-end-date").type("2026-10-07")
    user.find(marker="task-use-time").click()
    user.find(marker="task-start-time").clear().type("10:15")
    user.find(marker="task-use-time").click()  # 外す
    user.find(marker="task-save").click()
    assert saved[0].start == datetime(2026, 10, 5, 9, 0)


async def test_a_task_with_non_default_times_opens_with_the_times_shown(user: User) -> None:
    task = Task("既存", start=datetime(2026, 10, 5, 10, 15), end=datetime(2026, 10, 7, 16, 45))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_see(marker="task-start-time")
    assert user.find(marker="task-start-time").elements.pop().value == "10:15"
    assert user.find(marker="task-end-time").elements.pop().value == "16:45"


async def test_a_task_with_default_times_opens_with_the_times_hidden(user: User) -> None:
    task = Task("既存", start=datetime(2026, 10, 5, 9, 0), end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, [])
    await open_dialog(user)
    await user.should_not_see(marker="task-start-time")


async def test_an_automatic_end_is_kept_when_nothing_is_edited(user: User) -> None:
    # 工数から算出された終了(15:30)は補う終了(18:00)と違うので、時刻を出した状態で開く
    saved: list[Task] = []
    task = Task(
        "旧",
        start=datetime(2026, 10, 5, 9, 0),
        end=datetime(2026, 10, 5, 15, 30),
        effort_hours=6.5,
        end_auto=True,
    )
    mount_dialog(task, saved)
    await open_dialog(user)
    await user.should_see(marker="task-end-time")
    user.find(marker="task-save").click()
    assert saved[0].end == datetime(2026, 10, 5, 15, 30)
    assert saved[0].end_auto is True


async def test_checked_but_empty_time_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-05")
    user.find(marker="task-use-time").click()
    user.find(marker="task-start-time").clear()
    user.find(marker="task-save").click()
    await user.should_see("時刻の形式が正しくありません")
    assert saved == []


async def test_an_end_date_before_the_start_date_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-10-07")
    user.find(marker="task-end-date").type("2026-10-05")
    user.find(marker="task-save").click()
    await user.should_see("終了は開始以降の日時にしてください")
    assert saved == []


async def test_an_impossible_date_is_rejected(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-start-date").type("2026-13-45")
    user.find(marker="task-save").click()
    await user.should_see("日時の形式が正しくありません")
    assert saved == []


async def test_clearing_the_end_date_saves_an_empty_end(user: User) -> None:
    saved: list[Task] = []
    task = Task("既存", start=datetime(2026, 10, 5, 9, 0), end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, saved)
    await open_dialog(user)
    user.find(marker="task-end-date").clear()
    user.find(marker="task-save").click()
    assert saved[0].end is None


async def test_start_and_end_are_side_by_side(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    start_column = user.find(marker="task-start-date").elements.pop().parent_slot.parent
    end_column = user.find(marker="task-end-date").elements.pop().parent_slot.parent
    assert start_column is not end_column
    assert start_column.parent_slot.parent is end_column.parent_slot.parent
    assert isinstance(start_column.parent_slot.parent, ui.row)


async def test_date_picker_and_field_stay_in_sync(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="open-start-date-picker").click()
    picker = user.find(marker="start-date-picker").elements.pop()
    field = user.find(marker="task-start-date").elements.pop()
    with user.client:
        picker.set_value("2026-10-09")
    assert field.value == "2026-10-09"
    user.find(marker="task-start-date").clear().type("2026-10-12")
    assert picker.value == "2026-10-12"


async def test_time_picker_and_field_stay_in_sync(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-use-time").click()
    user.find(marker="open-end-time-picker").click()
    picker = user.find(marker="end-time-picker").elements.pop()
    field = user.find(marker="task-end-time").elements.pop()
    assert picker.value == "18:00"
    with user.client:
        picker.set_value("15:30")
    assert field.value == "15:30"
```

- [ ] **Step 3: 失敗を確認する**

Run: `uv run pytest test/test_task_dialog.py test/test_forms.py test/test_views.py -q`
Expected: FAIL(`task-start-date` などが見つからない)

- [ ] **Step 4: `task_dialog.py` を実装する**

import を直す。

```python
from collections.abc import Callable
from datetime import datetime, time

from nicegui import ui

from projectapp.forms import (
    build_task,
    compose_datetime,
    default_times,
    needs_time,
)
from projectapp.models import DEFAULT_WORK_START, Priority, Status, Task
```

(`format_datetime` の import は、このファイルで使わなくなるので外す。)

`PriorityChips` の直後に追加する。

```python
def add_picker(field: ui.input, picker_factory: Callable[[], ui.element], icon: str, key: str) -> None:
    """入力欄の右端のアイコンで、選択部品のダイアログを開く。小さな画面でも切れない。"""
    with ui.dialog() as picker, ui.card():
        picker_factory().bind_value(field).mark(f"{key}-picker")
        ui.button("OK", on_click=picker.close).mark(f"{key}-picker-ok")
    with field.add_slot("append"):
        ui.icon(icon).classes("cursor-pointer").on("click", picker.open).mark(
            f"open-{key}-picker"
        )


class DateTimeFields:
    """開始・終了を、日付の入力(横並び)と、チェックで出す時刻の入力で受け取る。"""

    def __init__(self, start: datetime | None, end: datetime | None, work_start: time) -> None:
        default_start, default_end = default_times(work_start)
        self._defaults = {"start": default_start, "end": default_end}
        with ui.row().classes("w-full no-wrap gap-4"):
            self.start_day, self.start_time = self._column("開始", "start", start, default_start)
            self.end_day, self.end_time = self._column("終了", "end", end, default_end)
        self.use_time = ui.checkbox(
            "時刻も指定する",
            value=needs_time(start, end, work_start),
            on_change=lambda e: self._show_times(e.value),
        ).mark("task-use-time")
        self._show_times(self.use_time.value, reset=False)

    @staticmethod
    def _column(
        label: str, key: str, moment: datetime | None, default: time
    ) -> tuple[ui.input, ui.input]:
        with ui.column().classes("flex-1 gap-0"):
            ui.label(label).classes("text-caption text-grey")
            day = ui.input("日付", value=moment.strftime("%Y-%m-%d") if moment else "")
            day.classes("w-full").mark(f"task-{key}-date")
            add_picker(day, ui.date, "event", f"{key}-date")
            clock = ui.input("時刻", value=(moment.time() if moment else default).strftime("%H:%M"))
            clock.classes("w-full").mark(f"task-{key}-time")
            add_picker(clock, ui.time, "access_time", f"{key}-time")
        return day, clock

    def _show_times(self, show: bool, *, reset: bool = True) -> None:
        for key, clock in (("start", self.start_time), ("end", self.end_time)):
            clock.set_visibility(show)
            if not show and reset:
                clock.set_value(self._defaults[key].strftime("%H:%M"))

    def start_text(self) -> str:
        return compose_datetime(self.start_day.value or "", self.start_time.value or "")

    def end_text(self) -> str:
        return compose_datetime(self.end_day.value or "", self.end_time.value or "")

    def state(self) -> tuple[str, str, str, str]:
        """入力の生の値。開いた時点との比較(変更の判定)に使う。"""
        return (
            self.start_day.value or "",
            self.start_time.value or "",
            self.end_day.value or "",
            self.end_time.value or "",
        )
```

`open_task_dialog` を直す。シグネチャ:

```python
def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
) -> None:
```

カードの幅を `ui.card().classes("w-[36rem] max-w-full")` にする。`start = ...`・`end = ...` の2つの `ui.input(...)`(6行)を次の1行に置き換える。

```python
        fields = DateTimeFields(initial.start, initial.end, work_start)
```

`save()` の `build_task(...)` 呼び出しは、`start=...`・`end=...` を次に直し、`compose` の `ValueError` も同じ `try` で受ける(すでに `try: ... except ValueError` の中なので、呼び出しの引数を変えるだけでよい)。

```python
                    start=fields.start_text(),
                    end=fields.end_text(),
```

- [ ] **Step 5: `views.py` から `work_start` を渡す**

`add_task`、`add_top_task`、`edit_task` の `open_task_dialog(...)` に、キーワード引数 `work_start=self.project.work_start` を足す。例:

```python
    def add_task(self, section_index: int) -> None:
        open_task_dialog(
            None,
            lambda task: self.save_task(section_index, None, task),
            work_start=self.project.work_start,
        )
```

`add_top_task`、`edit_task` も同じ形にする。

- [ ] **Step 6: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`

失敗が `user.find(...).clear()` 周りなら、`.clear()` の後に `.type(...)` を続けているか、`ui.input` に `on_change` が必要か(`ui.date` との双方向の同期)を `test_settings_dialog_time_picker_and_field_stay_in_sync`(`test/test_forms.py`)と見比べて直す。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/task_dialog.py src/projectapp/views.py test/test_forms.py test/test_views.py test/test_task_dialog.py
git commit -m "$(cat <<'EOF'
タスク編集の開始・終了を、日付の選択と時刻のチェック(横並び)にする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 閉じるときの確認

**Files:**
- Modify: `src/projectapp/task_dialog.py`
- Test: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: `DateTimeFields.state()`、`DateTimeFields.start_text()` / `end_text()`(Task 4)
- Produces:
  - `open_task_dialog(...) -> ui.dialog`(これまでの `None` から、ダイアログを返す)
  - ダイアログは `persistent`。`escape-key`(NiceGUI 内部の登録名は `escapeKey`)と「キャンセル」(マーカー `task-cancel`)が、変更があれば確認を出し、なければそのまま閉じる。
  - 確認ダイアログのボタンのマーカー: `close-save`、`close-discard`、`close-back`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` に追加する。

```python
from nicegui import ui


def dialog_of(user: User) -> ui.dialog:
    """画面にある、タスク編集ダイアログ(`persistent` の、最初に作られたダイアログ)。"""
    return next(
        e for e in user.client.elements.values() if isinstance(e, ui.dialog) and e.props.get("persistent")
    )


async def test_the_dialog_is_persistent_and_listens_for_escape(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    dialog = dialog_of(user)
    assert dialog.props.get("persistent") is True
    assert "escapeKey" in {listener.type for listener in dialog._event_listeners.values()}


async def test_cancel_without_changes_closes_without_asking(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False
    await user.should_not_see(marker="close-save")


async def test_cancel_with_changes_asks_first(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")
    assert dialog_of(user).value is True
    assert saved == []


async def test_close_confirm_save_saves_and_closes(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    user.find(marker="close-save").click()
    assert [t.name for t in saved] == ["設計"]
    assert dialog_of(user).value is False


async def test_close_confirm_discard_closes_without_saving(user: User) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    user.find(marker="close-discard").click()
    assert saved == []
    assert dialog_of(user).value is False


async def test_close_confirm_back_keeps_the_dialog_and_the_input(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-cancel").click()
    user.find(marker="close-back").click()
    assert dialog_of(user).value is True
    assert user.find(marker="task-name").elements.pop().value == "設計"


async def test_close_confirm_save_with_an_invalid_input_shows_the_error_and_stays(
    user: User,
) -> None:
    # 名前を空にしたまま「保存」を選ぶ: エラーを出して、編集ダイアログに入力を残す
    saved: list[Task] = []
    mount_dialog(Task("既存", effort_hours=2.0), saved)
    await open_dialog(user)
    user.find(marker="task-name").clear()
    user.find(marker="task-cancel").click()
    user.find(marker="close-save").click()
    await user.should_see("名前を入力してください")
    assert dialog_of(user).value is True
    assert saved == []


async def test_changing_only_the_checkbox_is_not_a_change(user: User) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-use-time").click()
    user.find(marker="task-cancel").click()
    assert dialog_of(user).value is False


async def test_changing_a_date_counts_as_a_change(user: User) -> None:
    task = Task("既存", start=datetime(2026, 10, 5, 9, 0), end=datetime(2026, 10, 7, 18, 0))
    mount_dialog(task, [])
    await open_dialog(user)
    user.find(marker="task-end-date").clear().type("2026-10-08")
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")


async def test_priority_and_status_changes_count_as_changes(user: User) -> None:
    mount_dialog(Task("既存"), [])
    await open_dialog(user)
    user.find(marker="priority-HIGH").click()
    user.find(marker="task-cancel").click()
    await user.should_see(marker="close-save")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_task_dialog.py -q`
Expected: FAIL(`persistent` でない、`task-cancel` がない)

- [ ] **Step 3: 実装する**

`src/projectapp/task_dialog.py` の `open_task_dialog` を、次の形に直す(`...` は Task 4 までと同じ入力部品の並び)。

```python
def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
) -> ui.dialog:
    initial = task or Task("")
    with ui.dialog().props("persistent") as dialog, ui.card().classes("w-[36rem] max-w-full"):
        ui.label("タスクの編集" if task else "タスクの追加").classes("text-h6")
        name = ui.input("名前", value=initial.name).mark("task-name")
        fields = DateTimeFields(initial.start, initial.end, work_start)
        effort = ui.number("工数(時間)", value=initial.effort_hours, min=0)
        priority = PriorityChips(initial.priority)
        status = (
            ui.select({s: s.value for s in Status}, label="状態", value=initial.status)
            .classes("w-full")
            .mark("task-status")
        )
        color = ui.color_input("色", value=initial.color, preview=True).classes("w-full").mark(
            "task-color"
        )
        assignee = ui.input("担当者", value=initial.assignee or "")
        error = ui.label("").classes("text-negative").mark("form-error")

        def current() -> tuple[object, ...]:
            """入力の現在値。開いた時点と比べて、変更があるかを判定する。"""
            return (
                name.value,
                *fields.state(),
                effort.value,
                priority.value,
                status.value,
                color.value,
                assignee.value,
            )

        opened = current()

        def save() -> None:
            try:
                result = build_task(
                    task,
                    name=name.value or "",
                    start=fields.start_text(),
                    end=fields.end_text(),
                    effort_hours=effort.value,
                    priority=priority.value,
                    status=Status(status.value),
                    color=color.value or initial.color,
                    assignee=assignee.value or "",
                )
            except ValueError as exc:
                error.set_text(str(exc))
                return
            on_save(result)
            dialog.close()

        with ui.dialog() as confirm, ui.card():
            ui.label("編集内容を確定しますか?")
            with ui.row():
                ui.button("保存", on_click=lambda: (confirm.close(), save())).mark("close-save")
                ui.button(
                    "破棄して閉じる", on_click=lambda: (confirm.close(), dialog.close())
                ).props("flat").mark("close-discard")
                ui.button("編集に戻る", on_click=confirm.close).props("flat").mark("close-back")

        def request_close() -> None:
            if current() == opened:
                dialog.close()
            else:
                confirm.open()

        dialog.on("escape-key", request_close)  # persistent なので、ESCでは自動で閉じない
        with ui.row():
            ui.button("キャンセル", on_click=request_close).props("flat").mark("task-cancel")
            ui.button("保存", on_click=save).mark("task-save")
    dialog.open()
    return dialog
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`

`lambda: (confirm.close(), save())` が `ty` で警告される場合は、`def confirm_save() -> None:` / `def discard() -> None:` の関数に分けて、`on_click=confirm_save` のように渡す。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/task_dialog.py test/test_task_dialog.py
git commit -m "$(cat <<'EOF'
タスク編集を閉じるとき、変更があれば確定するか確認する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: タスクの削除

**Files:**
- Modify: `src/projectapp/task_dialog.py`
- Modify: `src/projectapp/views.py`
- Test: `test/test_task_dialog.py`、`test/test_views.py`

**Interfaces:**
- Consumes: `open_task_dialog(...) -> ui.dialog`(Task 5)
- Produces:
  - `open_task_dialog(task, on_save, work_start=DEFAULT_WORK_START, on_delete: Callable[[], object] | None = None) -> ui.dialog`。`task` と `on_delete` がどちらもあるときだけ、削除ボタン(マーカー `task-delete`)が出る。確認ダイアログのボタンのマーカーは `delete-confirm`・`delete-cancel`。
  - `MainView.delete_task(section_index: int | None, task_index: int) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py` の `mount_dialog` を、削除の呼び出しを記録できるように直す。

```python
def mount_dialog(
    task: Task | None,
    saved: list[Task],
    work_start: time = time(9, 0),
    deleted: list[str] | None = None,
) -> None:
    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_task_dialog(
                task,
                saved.append,
                work_start=work_start,
                on_delete=None if deleted is None else lambda: deleted.append("deleted"),
            ),
        )
```

追加するテスト:

```python
async def test_a_new_task_has_no_delete_button(user: User) -> None:
    mount_dialog(None, [], deleted=[])
    await open_dialog(user)
    await user.should_not_see(marker="task-delete")


async def test_an_existing_task_without_a_delete_callback_has_no_delete_button(user: User) -> None:
    mount_dialog(Task("既存"), [])
    await open_dialog(user)
    await user.should_not_see(marker="task-delete")


async def test_delete_asks_for_confirmation_and_cancel_keeps_the_task(user: User) -> None:
    deleted: list[str] = []
    mount_dialog(Task("既存"), [], deleted=deleted)
    await open_dialog(user)
    user.find(marker="task-delete").click()
    await user.should_see("「既存」を削除しますか?")
    user.find(marker="delete-cancel").click()
    assert deleted == []
    assert dialog_of(user).value is True


async def test_delete_confirm_calls_the_callback_and_closes_the_dialog(user: User) -> None:
    deleted: list[str] = []
    mount_dialog(Task("既存"), [], deleted=deleted)
    await open_dialog(user)
    user.find(marker="task-delete").click()
    user.find(marker="delete-confirm").click()
    assert deleted == ["deleted"]
    assert dialog_of(user).value is False


async def test_delete_does_not_ask_about_unsaved_changes(user: User) -> None:
    deleted: list[str] = []
    mount_dialog(Task("既存"), [], deleted=deleted)
    await open_dialog(user)
    user.find(marker="task-name").type("変更")
    user.find(marker="task-delete").click()
    user.find(marker="delete-confirm").click()
    assert deleted == ["deleted"]
    await user.should_not_see(marker="close-save")
```

`test/test_views.py` に追加する(`make_view`・`wait_until`・`choose_in_combo` は既存)。

```python
async def test_delete_task_removes_only_that_task_and_makes_the_view_dirty(
    user: User, tmp_path: Path
) -> None:
    save_cache({}, tmp_path)
    save_project(
        Project(
            "既存",
            tasks=[Task("a"), Task("b")],
            sections=[Section("開発", [Task("x"), Task("y")])],
        ),
        tmp_path,
    )
    views: list[MainView] = []
    mount_capturing(tmp_path, views)
    await user.open("/")
    view = views[0]
    await choose_in_combo(user, "既存")
    assert await wait_until(lambda: view.path is not None)
    assert not view.is_dirty()
    view.delete_task(None, 0)
    assert [t.name for t in view.project.tasks] == ["b"]
    assert [t.name for t in view.project.sections[0].tasks] == ["x", "y"]
    view.delete_task(0, 1)
    assert [t.name for t in view.project.sections[0].tasks] == ["x"]
    assert [t.name for t in view.project.tasks] == ["b"]
    assert view.is_dirty()


async def test_delete_from_the_edit_dialog_removes_the_bar(user: User, tmp_path: Path) -> None:
    save_cache({}, tmp_path)
    mount(tmp_path, make_transport(200, []))
    await user.open("/")
    user.find(marker="add-task-top").click()
    user.find(marker="task-name").type("設計")
    user.find(marker="task-save").click()
    await user.should_see(marker="task-top-0")
    user.find(marker="task-top-0").click()
    user.find(marker="task-delete").click()
    user.find(marker="delete-confirm").click()
    await user.should_not_see(marker="task-top-0")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_task_dialog.py test/test_views.py -q`
Expected: FAIL(`on_delete` を受け取らない、`delete_task` がない)

- [ ] **Step 3: `task_dialog.py` を実装する**

シグネチャに `on_delete` を足す。

```python
def open_task_dialog(
    task: Task | None,
    on_save: Callable[[Task], object],
    work_start: time = DEFAULT_WORK_START,
    on_delete: Callable[[], object] | None = None,
) -> ui.dialog:
```

「編集に戻る」の確認ダイアログの定義の直後(`def request_close` の前)に、削除の確認を足す。

```python
        delete_confirm: ui.dialog | None = None
        if task is not None and on_delete is not None:
            handler = on_delete

            def delete() -> None:
                delete_confirm.close()
                dialog.close()
                handler()

            with ui.dialog() as delete_confirm, ui.card():
                ui.label(f"「{task.name}」を削除しますか?")
                with ui.row():
                    ui.button("キャンセル", on_click=delete_confirm.close).props("flat").mark(
                        "delete-cancel"
                    )
                    ui.button("削除", on_click=delete).props("color=negative").mark(
                        "delete-confirm"
                    )
```

最下行のボタンの並びを、削除を左端に置く形にする。

```python
        with ui.row().classes("w-full items-center"):
            if delete_confirm is not None:
                ui.button("削除", on_click=delete_confirm.open).props(
                    "flat color=negative"
                ).mark("task-delete")
            ui.space()
            ui.button("キャンセル", on_click=request_close).props("flat").mark("task-cancel")
            ui.button("保存", on_click=save).mark("task-save")
```

`ty` が `delete_confirm` の `None` の可能性を指摘する場合は、`delete()` 内を `assert delete_confirm is not None` で受けるか、`confirm_delete = ui.dialog()` を先に作る形にして `None` をなくす。

- [ ] **Step 4: `views.py` を実装する**

`edit_task` に `on_delete` を渡す。

```python
    def edit_task(self, section_index: int | None, task_index: int) -> None:
        task = self.tasks_in(section_index)[task_index]
        open_task_dialog(
            task,
            lambda t: self.save_task(section_index, task_index, t),
            work_start=self.project.work_start,
            on_delete=lambda: self.delete_task(section_index, task_index),
        )

    def delete_task(self, section_index: int | None, task_index: int) -> None:
        """タスクを取り除いて再描画する。保存は自動では行わない(編集中の判定に入る)。"""
        del self.tasks_in(section_index)[task_index]
        self.gantt.set_project(self.project)
```

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest -q && uvx ty check src`
Expected: 全件 PASS、`All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/task_dialog.py src/projectapp/views.py test/test_task_dialog.py test/test_views.py
git commit -m "$(cat <<'EOF'
タスク編集ダイアログからタスクを削除できるようにする(確認つき)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: ドキュメントの更新と、全体の確認

**Files:**
- Modify: `docs/development.md`(必要なら追記)
- Modify: `.claude/MEMORY.md`(作業記録)
- Modify: `README.md`(キー操作の表は、キー操作が増えていないので触らない)

**Interfaces:**
- Consumes: Task 1〜6
- Produces: 最新の作業記録

- [ ] **Step 1: 全体のテストと型チェック**

Run: `uv run pytest --cov=projectapp -q && uvx ty check src`
Expected: 全件 PASS(件数を控える)、`All checks passed!`

- [ ] **Step 2: 実機で確認する(自動テストでは見えない項目)**

`uv run projectapp` で起動して、次を確かめる。確認の結果は、ユーザーに伝える(自分で「できた」と判断しない)。
- 開始・終了が横並びで、ダイアログの幅が足りている。
- 日付のカレンダーアイコン、時刻の時計アイコンのダイアログが、小さなウィンドウでも切れない。
- 色のプレビュー(選択ボタンが選んだ色になる)。
- 優先度チップの色(ライト・ダークの両テーマ)。
- `ESC` で、変更があれば確認が出て、なければ閉じる。背景のクリックでは閉じない。
- 削除 → 確認 → バーが消える。保存していないので、プロジェクトは「編集中」(別プロジェクトを開こうとすると確認が出る)。

`ESC` が確認に入らない場合は、設計書の「編集を閉じるときの確認」に従い、「キャンセル」ボタンだけを確認の対象にして、設計書を直す。

- [ ] **Step 3: `.claude/MEMORY.md` を更新する**

「現在の状況」「ブランチ」「実装済みの機能」「保留中の課題」「次にやること」を、いまの状態に合わせる。特に次を書く。
- `feature/task-edit-dialog` の内容と、`develop` へのマージ前であること(マージは許可を得てから)。
- 保留事項: 始業が15:00以降のときの補う終了(暫定の `23:59` の頭打ち)、稼働設定のオプション「始業時刻を制限する」(設計書の「保留事項」に制限事項7点)、昼休憩を設定にするか。
- 実機で確認した項目と、確認できていない項目。

- [ ] **Step 4: コミット**

```bash
git add .claude/MEMORY.md docs/development.md
git commit -m "$(cat <<'EOF'
作業記録: タスク編集ダイアログの見直しを反映

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: 完了の報告**

テスト件数、`ty` の結果、実機で確認した項目と未確認の項目を伝え、`develop` へのマージの許可をユーザーに求める(許可を得るまでマージ・プッシュはしない)。
