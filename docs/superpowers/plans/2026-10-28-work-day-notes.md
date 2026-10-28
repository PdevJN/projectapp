# 稼働日の上書きの拡張(メモと期間で追加)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メンバーの稼働日の上書きに、メモ(`WorkDay.note`)と「期間で追加」を足し、休暇を日ごとの行として手早く登録して、理由を残せるようにする(要望 44〜46)。

**Architecture:** 新しい休暇のデータは作らず、`WorkDay` に `note` を足す(`version` 14)。期間の展開は純粋関数 `workdays.expand_range` に置き、`forms.plan_work_day_range` が入力文字を解釈して呼ぶ。画面は稼働日ダイアログの行にメモ欄と「期間で追加」のサブダイアログを足す。ガントチャートのホバーは `calendar.work_day_note` が組み立てるので、そこにメモを添える。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -n auto -q`)、`uvx ty check src`。

**Spec:** [`docs/superpowers/specs/2026-10-28-work-day-notes-design.md`](../specs/2026-10-28-work-day-notes-design.md)

## Global Constraints

- メモ: 30 文字以内(`MAX_NOTE = 30`)。改行・制御文字・ゼロ幅文字(`models.has_control_char`。Unicode の `Cc`・`Cf`・`Zl`・`Zp`)は不可。前後の空白は取り除く。
- ファイル形式: `models.FORMAT_VERSION` を 14 にする。`members[].work_days[]` に `note`(文字列)を保存する。キーのない古いファイルと `null` は空として読む。`version` 13 以前のファイルにある `note` は無視する。文字列でない値・30 文字超・制御文字は読込を拒否する。
- 期間で追加: 1 回 366 日まで(`MAX_RANGE_DAYS = 366`)。年は `MIN_YEAR`〜`MAX_YEAR`(2000〜2100)。既存の日は上書きせず飛ばす。`土日祝を除く`は既定オン。
- 日付の入力は `10/26`・`1026`・`20261026` でも書ける(`dateinput.parse_date_input`)。時刻は `9`・`930`・`9:30`(`parse_time_input`)。
- 3 者マージ: キーはメンバーの `id` と日付。`window`(開始・終了の組)と `note` は別の項目として比べる。
- コメントは 3 行以内。すべての関数に型ヒント。テストは `test/` に置く。ドキュメントは日本語。
- 稼働率(%)・ガントチャートの不在の帯・ダッシュボードのカードへの反映は含めない。
- 実装中に `git push`・マージはしない(利用者の許可を得てから)。

## Review Focus

- `version` 13 のファイルに `note` キーが残っていても、読み込みで無視する(Task 1)。
- メモが 31 文字・改行入り・ゼロ幅文字入り・数値のとき、読込と入力の両方で拒否する(Task 1・4)。
- 期間がすべて土日祝か登録済みで、追加が 0 行になるとき、ダイアログを閉じずにエラーを出す(Task 4・5)。
- 期間が 366 日を超える・開始が終了より後・年が範囲外のとき、行を足さずにエラーを出す(Task 3・5)。
- 祝日データがない(空の辞書)ときは、土日だけを除く(Task 3)。
- メモだけ入れて日付が空の行は、無視せず日付のエラーにする(Task 4)。

---

## File Structure

| ファイル | 責務 |
| --- | --- |
| `src/projectapp/models.py` | `WorkDay.note`、`FORMAT_VERSION = 14` |
| `src/projectapp/workdays.py` | `MAX_NOTE`・`MAX_RANGE_DAYS`・`validate_note`・`expand_range`(NiceGUI に依存しない) |
| `src/projectapp/storage.py` | `note` の読み書き(古いファイルは空) |
| `src/projectapp/merge.py` | `note` を項目に足す |
| `src/projectapp/forms.py` | `WorkDayRow.note`、`plan_work_day_range`・`RangeAdd`・`work_day_range_summary`、行のメモ欄、`期間で追加`ダイアログ、`get_holidays` の配線 |
| `src/projectapp/views.py` | `get_holidays=lambda: self.holidays` を渡す |
| `src/projectapp/calendar.py` | ホバー文にメモを添える |
| `test/test_workdays.py`・`test_storage.py`・`test_merge.py`・`test_forms.py`・`test_calendar.py`・`test_gantt.py`・`test_views.py` | 各タスクのテスト |
| `CLAUDE.md`・`docs/development.md`・`docs/requests.md` | 仕様・形式・要望の状態 |

---

### Task 1: データ(`note`・検証・保存・読込・version 14)

**Files:**
- Modify: `src/projectapp/models.py`(`WorkDay`、`FORMAT_VERSION`)
- Modify: `src/projectapp/workdays.py`
- Modify: `src/projectapp/storage.py`(`_work_days`、`_members` の呼び出し)
- Test: `test/test_workdays.py`、`test/test_storage.py`、`test/test_reference_storage.py`、`test/test_summary.py`

**Interfaces:**
- Produces: `WorkDay(day, start=None, end=None, note="")`、`workdays.MAX_NOTE: int`、`workdays.validate_note(note: str) -> None`(不正は `ValueError`)、`workdays.validate_work_days` がメモも検証する、`storage._work_days(value, version=FORMAT_VERSION)`。

- [ ] **Step 1: 失敗するテストを書く(`test/test_workdays.py` の末尾に追記)**

```python
def test_work_day_note_defaults_to_empty() -> None:
    assert WorkDay(date(2026, 10, 12)).note == ""


def test_validate_accepts_a_note_up_to_the_limit() -> None:
    validate_work_days([WorkDay(date(2026, 10, 12), note="あ" * 30)])


@pytest.mark.parametrize("note", ["あ" * 31, "夏季\n休暇", "夏季​休暇"])
def test_validate_rejects_bad_notes(note: str) -> None:
    with pytest.raises(ValueError, match="メモ"):
        validate_work_days([WorkDay(date(2026, 10, 12), note=note)])
```

`test/test_storage.py` の既存テスト `test_member_work_days_round_trip_in_date_order`(1876 行付近)の期待値を、`note` を含む形に直し、新しいテストを足す。

```python
    assert saved == [
        {"day": "2026-10-17", "start": "13:00:00", "end": "16:00:00", "note": ""},
        {"day": "2026-10-18", "start": None, "end": None, "note": ""},
    ]
```

```python
def test_work_day_note_round_trips_and_is_stripped() -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17), note="夏季休暇")])
    text = dumps_project(Project("p", members=[member]))
    raw = json.loads(text)
    assert raw["version"] == 14
    assert raw["members"][0]["work_days"][0]["note"] == "夏季休暇"
    assert parse_project(text, "p").members[0].work_days[0].note == "夏季休暇"
    raw["members"][0]["work_days"][0]["note"] = "  通院  "
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == "通院"


def test_work_days_without_a_note_key_load_with_an_empty_note() -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17))])
    raw = json.loads(dumps_project(Project("p", members=[member])))
    del raw["members"][0]["work_days"][0]["note"]
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == ""
    raw["members"][0]["work_days"][0]["note"] = None
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == ""


def test_a_note_in_a_version_13_file_is_ignored() -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17), note="夏季休暇")])
    raw = json.loads(dumps_project(Project("p", members=[member])))
    raw["version"] = 13
    assert parse_project(json.dumps(raw), "p").members[0].work_days[0].note == ""


@pytest.mark.parametrize("note", [3, ["x"], "あ" * 31, "a\nb"])
def test_bad_work_day_notes_are_rejected(note: object) -> None:
    member = Member("甲", id="m1", work_days=[WorkDay(date(2026, 10, 17))])
    raw = json.loads(dumps_project(Project("p", members=[member])))
    raw["members"][0]["work_days"][0]["note"] = note
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_workdays.py test/test_storage.py -q 2>&1 | tail -15`
Expected: `WorkDay` に `note` がない(`TypeError: ... unexpected keyword argument 'note'`)ことで複数件が FAIL。

- [ ] **Step 3: 実装する**

`src/projectapp/models.py`:
- `WorkDay` に、`end` の次の行へ `note: str = ""  # 休みや時間帯の理由(30 文字以内。例: 夏季休暇)` を足す。
- `FORMAT_VERSION = 13` を `FORMAT_VERSION = 14` にし、コメント末尾の `13: 相対比率の上限・下限〔ratio_limit_upper・ratio_limit_lower〕)` を `13: 相対比率の上限・下限〔ratio_limit_upper・ratio_limit_lower〕。14: 稼働日のメモ〔work_days[].note〕)` に直す。

`src/projectapp/workdays.py`(import を `from projectapp.models import MAX_YEAR, MIN_YEAR, WorkDay, has_control_char` にし、定数と関数を足す。`validate_work_days` のループ内、`seen.add(row.day)` の直後に `validate_note(row.note)` を足す):

```python
MAX_NOTE = 30  # メモの最大文字数
MAX_RANGE_DAYS = 366  # 期間で一括追加できる日数


def validate_note(note: str) -> None:
    """メモは 30 文字以内で、改行・制御文字・ゼロ幅文字を含まない。不正は ValueError。"""
    if len(note) > MAX_NOTE:
        raise ValueError(f"稼働日のメモは{MAX_NOTE}文字以内で入力してください")
    if has_control_char(note):
        raise ValueError("稼働日のメモに改行・制御文字は使えません")
```

`src/projectapp/storage.py`:
- `def _work_days(value: Any) -> list[WorkDay]:` を `def _work_days(value: Any, version: int = FORMAT_VERSION) -> list[WorkDay]:` にする。
- 末尾の `rows.append(WorkDay(day, times[0], times[1]))` を次に置き換える。

```python
        note = raw.get("note") if version >= 14 else None
        if note is None:
            note = ""
        elif not isinstance(note, str):
            raise ValueError(f"稼働日のメモが文字列ではありません: {note!r}")
        rows.append(WorkDay(day, times[0], times[1], note.strip()))
```
- `_members` の `_work_days(raw.get("work_days")) if ctx.version >= 8 else []` を `_work_days(raw.get("work_days"), ctx.version) if ctx.version >= 8 else []` にする。

- [ ] **Step 4: バージョンを固定した既存のテストを直す**

`test/test_reference_storage.py:39`、`test/test_summary.py:72`、`test/test_storage.py:1311` の `== 13` を `== 14` にする(`FORMAT_VERSION == 13` → `FORMAT_VERSION == 14`)。

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest test/test_workdays.py test/test_storage.py test/test_reference_storage.py test/test_summary.py -q 2>&1 | tail -5`
Expected: すべて PASS。

- [ ] **Step 6: 全体と型を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add src/projectapp/models.py src/projectapp/workdays.py src/projectapp/storage.py test/
git commit -m "feat: 稼働日の上書きにメモを足す(version 14)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 3 者マージで `note` を別の項目として比べる

**Files:**
- Modify: `src/projectapp/merge.py`(`WORK_DAY_LABELS`、`_show_window`、`_member_work_days`、メンバー組み立て)
- Test: `test/test_merge.py`

**Interfaces:**
- Consumes: Task 1 の `WorkDay.note`。
- Produces: マージの衝突ダイアログの項目名 `メモ`(`("work_day", "<メンバーid>:<日付>", "メモ")` が選択のキー)。

- [ ] **Step 1: 失敗するテストを書く(`test/test_merge.py` の `test_member_work_day_conflict_is_labelled_with_the_member_and_date` の後に追記)**

```python
def test_member_work_day_note_is_its_own_item() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[mem(WorkDay(date(2026, 10, 17), time(13), time(16), "通院"))])
    theirs = proj(members=[mem(wd("2026-10-17", 17))])
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == []
    (row,) = result.project.members[0].work_days
    assert (row.end, row.note) == (time(17), "通院")  # 時間帯は相手、メモは自分


def test_member_work_day_note_conflict_shows_the_notes() -> None:
    def noted(text: str) -> WorkDay:
        return WorkDay(date(2026, 10, 17), time(13), time(16), text)

    base = proj(members=[mem(noted("通院"))])
    ours = proj(members=[mem(noted("出張"))])
    theirs = proj(members=[mem(noted("休暇"))])
    result = merge_projects(base, ours, theirs, {("work_day", "m1:2026-10-17", "メモ"): THEIRS})
    (conflict,) = result.conflicts
    assert (conflict.ours, conflict.theirs) == ("出張", "休暇")
    assert result.project.members[0].work_days[0].note == "休暇"


def test_a_work_day_added_with_a_note_keeps_the_note() -> None:
    base = proj(members=[mem()])
    ours = proj(members=[mem(WorkDay(date(2026, 10, 19), note="夏季休暇"))])
    theirs = proj(members=[mem()])
    result = merge_projects(base, ours, theirs)
    assert result.project.members[0].work_days == [WorkDay(date(2026, 10, 19), note="夏季休暇")]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_merge.py -q -k "note" 2>&1 | tail -10`
Expected: 3 件 FAIL(`note` を比べていないため、メモが失われるか衝突の形が違う)。

- [ ] **Step 3: 実装する**

`src/projectapp/merge.py`:

```python
WORK_DAY_LABELS = {"window": "時間帯", "note": "メモ"}
```

`_show_window` を次に置き換える(名前も `_show_work_day` にし、`merger.collection("work_day", ..., _show_window)` の引数を `_show_work_day` にする):

```python
def _show_work_day(name: str, value: Any) -> str:
    if name == "note":
        return value or "(なし)"
    start, end = value
    return "休み" if start is None else f"{start:%H:%M}〜{end:%H:%M}"
```

`_member_work_days` の値を次にする:

```python
    return {
        f"{m.id}:{w.day.isoformat()}": {"window": (w.start, w.end), "note": w.note}
        for m in project.members
        for w in m.work_days
    }
```

メンバーの組み立て(`by_id[member_id].work_days.append(...)`)を次にする:

```python
            start, end = r["window"]
            by_id[member_id].work_days.append(WorkDay(date.fromisoformat(day), start, end, r["note"]))
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_merge.py -q 2>&1 | tail -3`
Expected: PASS(既存の `test_member_work_day_window_is_one_item` なども通る)。

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/merge.py test/test_merge.py
git commit -m "feat: 稼働日のメモを3者マージの項目にする" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 期間の展開(`workdays.expand_range`)

**Files:**
- Modify: `src/projectapp/workdays.py`
- Test: `test/test_workdays.py`

**Interfaces:**
- Consumes: Task 1 の `validate_note`・`MAX_RANGE_DAYS`。
- Produces: `expand_range(start: date, end: date, window: tuple[time, time] | None, note: str, existing: Iterable[date], holidays: Mapping[date, str], skip_off: bool) -> tuple[list[WorkDay], int, int]`(戻り値は 足す行〔日付の昇順〕・登録済みで飛ばした日数・土日祝で飛ばした日数。`window` が None なら休み。不正は `ValueError`)。

- [ ] **Step 1: 失敗するテストを書く(`test/test_workdays.py` の末尾に追記)**

ファイル先頭の import を `from datetime import date, time, timedelta` と `from projectapp.workdays import expand_range, sort_work_days, validate_work_days, work_day_map` に直してから、次を追記する。

```python
MON, SUN = date(2026, 10, 26), date(2026, 11, 1)  # 月曜〜翌日曜


def test_expand_range_skips_weekends_by_default_choice() -> None:
    rows, registered, off = expand_range(MON, SUN, None, "夏季休暇", [], {}, True)
    assert [w.day for w in rows] == [date(2026, 10, 26 + n) for n in range(5)]
    assert all(w.start is None and w.end is None and w.note == "夏季休暇" for w in rows)
    assert (registered, off) == (0, 2)


def test_expand_range_can_include_weekends() -> None:
    rows, _, off = expand_range(MON, SUN, None, "", [], {}, False)
    assert len(rows) == 7 and off == 0


def test_expand_range_skips_holidays_when_given() -> None:
    rows, _, off = expand_range(MON, SUN, None, "", [], {date(2026, 10, 28): "祝"}, True)
    assert date(2026, 10, 28) not in [w.day for w in rows]
    assert off == 3  # 祝日 1 日と土日 2 日


def test_expand_range_without_holiday_data_skips_only_weekends() -> None:
    rows, _, off = expand_range(MON, SUN, None, "", [], {}, True)
    assert (len(rows), off) == (5, 2)


def test_expand_range_does_not_overwrite_registered_days() -> None:
    rows, registered, _ = expand_range(MON, SUN, None, "", [date(2026, 10, 27)], {}, True)
    assert date(2026, 10, 27) not in [w.day for w in rows]
    assert (len(rows), registered) == (4, 1)


def test_expand_range_with_a_window() -> None:
    rows, _, _ = expand_range(MON, MON, (time(9), time(12)), "通院", [], {}, True)
    assert rows == [WorkDay(MON, time(9), time(12), "通院")]


def test_expand_range_strips_the_note() -> None:
    (row,), _, _ = expand_range(MON, MON, None, "  通院  ", [], {}, True)
    assert row.note == "通院"


def test_expand_range_accepts_exactly_the_limit_and_rejects_one_more() -> None:
    start = date(2026, 1, 1)
    rows, _, _ = expand_range(start, start + timedelta(days=365), None, "", [], {}, False)
    assert len(rows) == 366
    with pytest.raises(ValueError, match="366"):
        expand_range(start, start + timedelta(days=366), None, "", [], {}, False)


@pytest.mark.parametrize(
    ("start", "end", "window", "note", "message"),
    [
        (SUN, MON, None, "", "開始日"),  # 開始が終了より後
        (MON, SUN, (time(12), time(9)), "", "開始"),  # 時間帯が逆
        (MON, SUN, (time(9), time(9)), "", "開始"),
        (MON, SUN, None, "あ" * 31, "メモ"),
        (date(2100, 12, 30), date(2101, 1, 2), None, "", "2100"),  # 年の範囲外
    ],
)
def test_expand_range_rejects_bad_input(start: date, end: date, window, note: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        expand_range(start, end, window, note, [], {}, False)
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_workdays.py -q 2>&1 | tail -6`
Expected: `ImportError: cannot import name 'expand_range'`。

- [ ] **Step 3: 実装する(`src/projectapp/workdays.py` に追記。import に `Mapping` と `time, timedelta` を足す)**

```python
def expand_range(
    start: date,
    end: date,
    window: tuple[time, time] | None,
    note: str,
    existing: Iterable[date],
    holidays: Mapping[date, str],
    skip_off: bool,
) -> tuple[list[WorkDay], int, int]:
    """期間の各日を稼働日の上書きにする。window が None なら休み。
    戻り値は (足す行, 登録済みで飛ばした日数, 土日祝で飛ばした日数)。登録済みの日は上書きしない。"""
    if start > end:
        raise ValueError("期間は、開始日が終了日以前になるように入れてください")
    count = (end - start).days + 1
    if count > MAX_RANGE_DAYS:
        raise ValueError(f"一度に追加できるのは{MAX_RANGE_DAYS}日までです")
    if window is not None and window[0] >= window[1]:
        raise ValueError("稼働日の終了は開始より後にしてください")
    note = note.strip()
    validate_note(note)
    opens, closes = window if window is not None else (None, None)
    taken = set(existing)
    rows: list[WorkDay] = []
    registered = off = 0
    for offset in range(count):
        day = start + timedelta(days=offset)
        if not MIN_YEAR <= day.year <= MAX_YEAR:
            raise ValueError(f"稼働日の日付は {MIN_YEAR}〜{MAX_YEAR} 年にしてください: {day.isoformat()}")
        if skip_off and (day.weekday() >= 5 or day in holidays):
            off += 1
        elif day in taken:
            registered += 1
        else:
            rows.append(WorkDay(day, opens, closes, note))
    return rows, registered, off
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_workdays.py -q 2>&1 | tail -3`
Expected: PASS。

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/workdays.py test/test_workdays.py
git commit -m "feat: 稼働日の上書きを期間から展開する純粋関数を足す" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 入力行の `note` と、期間の解釈(`forms` の純粋な部分)

**Files:**
- Modify: `src/projectapp/forms.py`(`WorkDayRow`、`build_work_day_list`、`work_day_rows`、新しい `RangeAdd`・`plan_work_day_range`・`work_day_range_summary`、import)
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: Task 1 の `WorkDay.note`・`validate_work_days`、Task 3 の `expand_range`・`MAX_NOTE`。
- Produces:
  - `WorkDayRow(day, start, end, rest, note="")`。
  - `RangeAdd(rows: list[WorkDayRow], registered: int, off: int)`。
  - `plan_work_day_range(period_text: str, rest: bool, start_text: str, end_text: str, note: str, skip_off: bool, rows: list[WorkDayRow], holidays: Mapping[date, str], today: date) -> RangeAdd`(不正は `ValueError`)。
  - `work_day_range_summary(plan: RangeAdd) -> str`。

- [ ] **Step 1: 失敗するテストを書く(`test/test_forms.py`。既存の `from projectapp.forms import (...)` に `RangeAdd`・`plan_work_day_range`・`work_day_range_summary` を足す)**

```python
def test_work_day_row_has_an_empty_note_by_default() -> None:
    assert WorkDayRow("10/17", "", "", True).note == ""


def test_build_work_day_list_carries_the_note_and_strips_it() -> None:
    rows = [WorkDayRow("10/17", "13", "16", False, " 通院 "), WorkDayRow("10/18", "", "", True, "夏季休暇")]
    built = build_work_day_list(rows, WORK_TODAY)
    assert [w.note for w in built] == ["通院", "夏季休暇"]


def test_a_row_with_only_a_note_is_not_ignored() -> None:
    with pytest.raises(ValueError, match="日付"):
        build_work_day_list([WorkDayRow("", "", "", False, "メモだけ")], WORK_TODAY)


def test_build_work_day_list_rejects_a_long_note() -> None:
    with pytest.raises(ValueError, match="メモ"):
        build_work_day_list([WorkDayRow("10/17", "", "", True, "あ" * 31)], WORK_TODAY)


def test_plan_work_day_range_adds_rest_rows_and_skips_registered_days() -> None:
    existing = [WorkDayRow("10/27", "", "", True)]
    plan = plan_work_day_range("10/26 〜 10/30", True, "", "", "夏季休暇", True, existing, {}, WORK_TODAY)
    assert [r.day for r in plan.rows] == ["2026-10-26", "2026-10-28", "2026-10-29", "2026-10-30"]
    assert all(r.rest and r.note == "夏季休暇" and r.start == "" and r.end == "" for r in plan.rows)
    assert (plan.registered, plan.off) == (1, 0)


def test_plan_work_day_range_with_a_window_formats_the_times() -> None:
    plan = plan_work_day_range("2026-10-26 〜 2026-10-26", False, "9", "1230", "", True, [], {}, WORK_TODAY)
    assert [(r.start, r.end, r.rest) for r in plan.rows] == [("09:00", "12:30", False)]


@pytest.mark.parametrize(
    ("period", "rest", "start", "end", "message"),
    [
        ("", True, "", "", "期間"),  # 空
        ("abc", True, "", "", "期間"),
        ("10/30 〜 10/26", True, "", "", "開始日"),  # 逆
        ("10/26 〜 10/30", False, "", "", "時刻"),  # 時間帯なのに時刻が空
        ("10/26 〜 10/30", False, "12", "9", "開始"),  # 逆
    ],
)
def test_plan_work_day_range_rejects_bad_input(period: str, rest: bool, start: str, end: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        plan_work_day_range(period, rest, start, end, "", True, [], {}, WORK_TODAY)


def test_plan_work_day_range_with_nothing_to_add_returns_no_rows() -> None:
    plan = plan_work_day_range("10/31 〜 11/1", True, "", "", "", True, [], {}, WORK_TODAY)  # 土日だけ
    assert plan.rows == [] and plan.off == 2


def test_work_day_range_summary() -> None:
    row = WorkDayRow("2026-10-26", "", "", True)
    assert work_day_range_summary(RangeAdd([row] * 3, 1, 2)) == "3 日を追加しました(1 日は登録済みのため飛ばしました。土日祝 2 日を除きました)"
    assert work_day_range_summary(RangeAdd([row], 0, 0)) == "1 日を追加しました"
    assert work_day_range_summary(RangeAdd([], 2, 0)) == "追加する日がありません(2 日は登録済みのため飛ばしました)"
```

`WORK_TODAY` は `test_forms.py` の既存の定数(2026-10 の日付)を使う。値が 2026 年でないときは、`date(2026, 10, 7)` を持つ定数を使う。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py -q -k "work_day" 2>&1 | tail -8`
Expected: `ImportError`(新しい名前がない)または `TypeError`(`WorkDayRow` に `note` がない)。

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py`:

1. import を足す: `from projectapp.periodfield import normalize_period, split_period, validate_period` と `from projectapp.workdays import MAX_NOTE, expand_range`(既存の `from projectapp.workdays import ...` があれば名前を足す。循環 import になるときは、関数の中で読む)。`Mapping` が `collections.abc` から読まれていなければ足す。
2. `WorkDayRow` に `note: str = ""` を足す。
3. `build_work_day_list` を次に置き換える:

```python
def build_work_day_list(rows: list[WorkDayRow], today: date) -> list[WorkDay]:
    """入力の行を検証して、日付の昇順の一覧にする。完全に空の行は無視する(メモだけの行は日付のエラー)。休みの行は時刻を見ない。"""
    built: list[WorkDay] = []
    for row in rows:
        if not row.rest and not any(t.strip() for t in (row.day, row.start, row.end, row.note)):
            continue
        day = parse_date_input(row.day, today, roll_forward=False)
        if day is None:
            raise ValueError("稼働日の日付を入力してください(例: 2026-10-17、10/17)")
        note = row.note.strip()
        if row.rest:
            built.append(WorkDay(date.fromisoformat(day), note=note))
            continue
        start, end = parse_time_input(row.start), parse_time_input(row.end)
        if start is None or end is None:
            raise ValueError(
                f"稼働日 {day} の開始と終了を時刻で入力してください(例: 13:00、930)。休みなら「休み」にチェックしてください"
            )
        built.append(WorkDay(date.fromisoformat(day), time.fromisoformat(start), time.fromisoformat(end), note))
    validate_work_days(built)
    return sort_work_days(built)
```

4. `members_panel` の中の `work_day_rows` で、`WorkDayRow(` の引数の最後に `w.note,` を足す。
5. `build_work_day_list` の後ろに足す:

```python
@dataclass
class RangeAdd:
    rows: list[WorkDayRow]  # 足す行(日付の昇順)
    registered: int  # 登録済みで飛ばした日数
    off: int  # 土日祝で飛ばした日数


def plan_work_day_range(
    period_text: str,
    rest: bool,
    start_text: str,
    end_text: str,
    note: str,
    skip_off: bool,
    rows: list[WorkDayRow],
    holidays: Mapping[date, str],
    today: date,
) -> RangeAdd:
    """「期間で追加」の入力を解釈して、足す行を作る。不正は ValueError。"""
    fixed = normalize_period(period_text, today)
    if fixed is None:
        raise ValueError("期間を入れてください(例: 2026-10-26 〜 2026-10-30)")
    start, end = validate_period(*split_period(fixed))
    window: tuple[time, time] | None = None
    if not rest:
        opens, closes = parse_time_input(start_text), parse_time_input(end_text)
        if opens is None or closes is None:
            raise ValueError("開始と終了を時刻で入力してください(例: 13:00、930)。休みなら「休み」にしてください")
        window = (time.fromisoformat(opens), time.fromisoformat(closes))
    existing = {date.fromisoformat(d) for r in rows if (d := parse_date_input(r.day, today, roll_forward=False))}
    added, registered, off = expand_range(start, end, window, note, existing, holidays, skip_off)
    built = [
        WorkDayRow(
            w.day.isoformat(),
            w.start.strftime("%H:%M") if w.start else "",
            w.end.strftime("%H:%M") if w.end else "",
            window is None,
            w.note,
        )
        for w in added
    ]
    return RangeAdd(built, registered, off)


def work_day_range_summary(plan: RangeAdd) -> str:
    """追加のあとの通知(足した日数と、飛ばした日数)。足す日がないときは、その旨。"""
    head = f"{len(plan.rows)} 日を追加しました" if plan.rows else "追加する日がありません"
    skipped = []
    if plan.registered:
        skipped.append(f"{plan.registered} 日は登録済みのため飛ばしました")
    if plan.off:
        skipped.append(f"土日祝 {plan.off} 日を除きました")
    return head + (f"({'。'.join(skipped)})" if skipped else "")
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py -q 2>&1 | tail -3`
Expected: PASS(既存の `test_build_work_day_list_*` も通る)。

- [ ] **Step 5: 全体と型を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "feat: 稼働日の入力行にメモを足し、期間の解釈を純粋関数にする" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 画面(行のメモ欄・`期間で追加`・祝日の配線)

**Files:**
- Modify: `src/projectapp/forms.py`(`work_day_editor`、`members_panel`、`open_members_parameters_dialog`、`open_work_days` の幅)
- Modify: `src/projectapp/views.py`(`get_holidays` を渡す)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 4 の `plan_work_day_range`・`work_day_range_summary`・`WorkDayRow.note`、`periodfield.add_range_picker`。
- Produces: マーカー `member-workday-{n}-note`(行のメモ欄)、`member-workday-range-open`(`期間で追加`ボタン)、`member-workday-range-period`・`-kind`・`-start`・`-end`・`-skip`・`-note`・`-add`・`-error`(サブダイアログ)。`work_day_editor(rows, marker, get_holidays=dict)`。

- [ ] **Step 1: 失敗するテストを書く(`test/test_views.py` の末尾に追記。`date` は既存の import を使う)**

```python
async def open_work_day_dialog(user: User, tmp_path: Path) -> MainView:
    view = await open_members_view(user, tmp_path)
    view.project.members = [Member("甲", 1.0, {}, "m1")]
    view.mark_clean()
    await open_members_parameters(user)
    user.find(marker="member-workday-open-0").click()
    await user.should_see(marker="member-workday-add")
    return view


async def test_a_work_day_row_note_is_applied(user: User, tmp_path: Path) -> None:
    view = await open_work_day_dialog(user, tmp_path)
    user.find(marker="member-workday-add").click()
    await user.should_see(marker="member-workday-0-day")
    user.find(marker="member-workday-0-day").type("2026-10-17")
    user.find(marker="member-workday-0-rest").click()
    user.find(marker="member-workday-0-note").type("通院")
    user.find(marker="member-workday-close").click()
    await settle()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: view.project.members[0].work_days == [WorkDay(date(2026, 10, 17), note="通院")])


async def test_the_range_dialog_adds_one_row_per_workday(user: User, tmp_path: Path) -> None:
    view = await open_work_day_dialog(user, tmp_path)
    user.find(marker="member-workday-range-open").click()
    await user.should_see(marker="member-workday-range-period")
    user.find(marker="member-workday-range-period").type("2026-10-26 〜 2026-11-01")
    user.find(marker="member-workday-range-note").type("夏季休暇")
    user.find(marker="member-workday-range-add").click()
    await user.should_see(marker="member-workday-4-day")  # 月〜金の 5 行
    await user.should_not_see(marker="member-workday-5-day")  # 土日は除く
    user.find(marker="member-workday-close").click()
    await settle()
    user.find(marker="member-apply").click()
    expected = [WorkDay(date(2026, 10, 26 + n), note="夏季休暇") for n in range(5)]
    assert await wait_until(lambda: view.project.members[0].work_days == expected)


async def test_the_range_dialog_shows_an_error_and_stays_open(user: User, tmp_path: Path) -> None:
    await open_work_day_dialog(user, tmp_path)
    user.find(marker="member-workday-range-open").click()
    await user.should_see(marker="member-workday-range-add")
    user.find(marker="member-workday-range-add").click()  # 期間が空
    await settle()
    assert "期間" in user.find(marker="member-workday-range-error").elements.pop().text
    user.find(marker="member-workday-range-period").type("2026-10-31 〜 2026-11-01")  # 土日だけ
    user.find(marker="member-workday-range-add").click()
    await settle()
    assert "追加する日がありません" in user.find(marker="member-workday-range-error").elements.pop().text
    await user.should_see(marker="member-workday-range-add")  # 閉じていない
    await user.should_not_see(marker="member-workday-0-day")  # 行は増えていない


async def test_the_range_dialog_skips_days_that_already_have_a_row(user: User, tmp_path: Path) -> None:
    view = await open_work_day_dialog(user, tmp_path)
    user.find(marker="member-workday-add").click()
    await user.should_see(marker="member-workday-0-day")
    user.find(marker="member-workday-0-day").type("2026-10-27")
    user.find(marker="member-workday-0-start").type("13")
    user.find(marker="member-workday-0-end").type("16")
    user.find(marker="member-workday-range-open").click()
    await user.should_see(marker="member-workday-range-period")
    user.find(marker="member-workday-range-period").type("2026-10-26 〜 2026-10-28")
    user.find(marker="member-workday-range-add").click()
    await user.should_see(marker="member-workday-2-day")  # 既存 1 行 + 26・28 日
    user.find(marker="member-workday-close").click()
    await settle()
    user.find(marker="member-apply").click()
    assert await wait_until(lambda: len(view.project.members[0].work_days) == 3)
    kept = next(w for w in view.project.members[0].work_days if w.day == date(2026, 10, 27))
    assert (kept.start, kept.end) == (time(13), time(16))  # 既存の行は上書きしない
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_views.py -q -k "work_day or range_dialog" 2>&1 | tail -8`
Expected: 4 件 FAIL(マーカー `member-workday-range-open`・`member-workday-0-note` がない)。

- [ ] **Step 3: `work_day_editor` を置き換える(`src/projectapp/forms.py`)**

関数全体を次に置き換える(`add_range_picker` は `from projectapp.periodfield import add_range_picker` を、ほかの `periodfield` の import と一緒に足す):

```python
def work_day_editor(
    rows: list[WorkDayRow], marker: str, get_holidays: Callable[[], Mapping[date, str]] = dict
) -> None:
    """稼働日の上書きの行(日付 / 開始 / 終了 / 休み / メモ / 削除)と、追加・期間で追加のボタン。rows をその場で書き換える。"""

    from projectapp.task_dialog import add_picker, date_normalizer  # task_dialog が forms を使うので、呼ぶときに読む

    @ui.refreshable
    def table() -> None:
        with ui.column().classes("w-full gap-1"):
            for n, wrow in enumerate(rows):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    day_input = ui.input(
                        "日付", value=wrow.day, on_change=lambda e, r=wrow: setattr(r, "day", e.value or "")
                    ).classes("w-40").mark(f"{marker}-{n}-day")
                    add_picker(day_input, ui.date, "event", f"{marker}-{n}-day", "%Y-%m-%d", date_normalizer(False))
                    for label, name in (("開始", "start"), ("終了", "end")):
                        field_input = ui.input(
                            label,
                            value=getattr(wrow, name),
                            on_change=lambda e, r=wrow, k=name: setattr(r, k, e.value or ""),
                        ).classes("w-28").mark(f"{marker}-{n}-{name}")
                        add_picker(field_input, ui.time, "access_time", f"{marker}-{n}-{name}", "%H:%M", parse_time_input)
                        field_input.set_enabled(not wrow.rest)
                    ui.checkbox("休み", value=wrow.rest, on_change=lambda e, r=wrow: toggle(r, bool(e.value))).mark(
                        f"{marker}-{n}-rest"
                    )
                    note_input = ui.input(
                        "メモ", value=wrow.note, on_change=lambda e, r=wrow: setattr(r, "note", e.value or "")
                    ).classes("w-44").mark(f"{marker}-{n}-note")
                    limit_length(note_input, MAX_NOTE)
                    ui.button(icon="delete", on_click=lambda _e, r=wrow: remove(r)).props(
                        "flat dense color=negative"
                    ).mark(f"{marker}-{n}-remove")

    def toggle(wrow: WorkDayRow, value: bool) -> None:
        wrow.rest = value
        table.refresh()

    def remove(wrow: WorkDayRow) -> None:
        rows.remove(wrow)
        table.refresh()

    def add() -> None:
        rows.append(WorkDayRow("", "", "", False))
        table.refresh()

    def open_range() -> None:
        with ui.dialog() as sub, ui.card().classes("w-[34rem] max-w-full"):
            ui.label("期間で稼働日を追加").classes("text-subtitle1")
            ui.label("期間の各日を、1 日ずつの行として足します。登録済みの日は飛ばします").classes("text-caption text-grey")
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                period = ui.input("期間", placeholder="2026-10-26 〜 2026-10-30").classes("col").mark(
                    f"{marker}-range-period"
                )
                add_range_picker(period, f"{marker}-range")
            kind = ui.toggle({"rest": "休み", "window": "稼働の時間帯"}, value="rest").mark(f"{marker}-range-kind")
            with ui.row().classes("items-center gap-2"):
                start = ui.input("開始").classes("w-28").mark(f"{marker}-range-start")
                end = ui.input("終了").classes("w-28").mark(f"{marker}-range-end")
                for field_input in (start, end):
                    field_input.bind_enabled_from(kind, "value", lambda value: value == "window")
            skip = ui.checkbox("土日祝を除く", value=True).mark(f"{marker}-range-skip")
            note = ui.input("メモ(任意)").classes("w-full").mark(f"{marker}-range-note")
            limit_length(note, MAX_NOTE)
            error = ui.label("").classes("text-negative").mark(f"{marker}-range-error")

            def add_rows() -> None:
                try:
                    plan = plan_work_day_range(
                        period.value or "",
                        kind.value == "rest",
                        start.value or "",
                        end.value or "",
                        note.value or "",
                        bool(skip.value),
                        rows,
                        get_holidays(),
                        date.today(),
                    )
                except ValueError as exc:
                    error.set_text(str(exc))
                    return
                if not plan.rows:
                    error.set_text(work_day_range_summary(plan))
                    return
                rows.extend(plan.rows)
                rows.sort(key=lambda r: parse_date_input(r.day, date.today(), roll_forward=False) or "9999")
                ui.notify(work_day_range_summary(plan))
                sub.close()
                table.refresh()

            with ui.row().classes("gap-2"):
                ui.button("追加", on_click=add_rows).mark(f"{marker}-range-add")
                ui.button("キャンセル", on_click=sub.close).props("flat").mark(f"{marker}-range-cancel")
        sub.open()

    table()
    with ui.row().classes("gap-2"):
        ui.button("稼働日を追加", icon="add", on_click=add).props("flat dense").mark(f"{marker}-add")
        ui.button("期間で追加", icon="date_range", on_click=open_range).props("flat dense").mark(f"{marker}-range-open")
```

- [ ] **Step 4: `get_holidays` を配線する**

`src/projectapp/forms.py`:
- `members_panel(...)` の引数の最後(`get_limits` の次)に `get_holidays: Callable[[], dict[date, str]] = dict,` を足す。
- その中の `open_work_days` を次にする(幅を広げ、`get_holidays` を渡す):

```python
    def open_work_days(row: MemberRow) -> None:
        with ui.dialog() as sub, ui.card().classes("w-[58rem] max-w-full"):
            ui.label(f"{row.name or '(名前なし)'} の稼働日の上書き").classes("text-subtitle1")
            ui.label("日付ごとに、稼働の時間帯(開始〜終了)か休みを決めます。土日祝を稼働にしたり、平日を休みにできます").classes(
                "text-caption text-grey"
            )
            work_day_editor(row.work_days, "member-workday", get_holidays)
            ui.button("閉じる", on_click=sub.close).mark("member-workday-close")
        sub.on("hide", table.refresh)
        sub.open()
```
- `open_members_parameters_dialog(...)` の引数の最後(`get_limits` の次)に `get_holidays: Callable[[], dict[date, str]] = dict,` を足し、`members_panel(get_members, assigned, on_apply_members, get_parameters, get_taken, pick_icon, get_limits)` を `members_panel(get_members, assigned, on_apply_members, get_parameters, get_taken, pick_icon, get_limits, get_holidays)` にする。

`src/projectapp/views.py`: `open_members_parameters` の `open_members_parameters_dialog(...)` の呼び出しに `get_holidays=lambda: self.holidays,` を足す(`get_limits=...` の次の行)。

- [ ] **Step 5: 通ることを確認する**

Run: `uv run pytest test/test_views.py -q -k "work_day or range_dialog" 2>&1 | tail -5`
Expected: すべて PASS(既存の稼働日のテストも通る)。

- [ ] **Step 6: 全体と型を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_views.py
git commit -m "feat: 稼働日のダイアログにメモ欄と期間で追加を足す" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ガントチャートのホバーにメモを添える

**Files:**
- Modify: `src/projectapp/calendar.py`(`work_day_note`)
- Test: `test/test_calendar.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: Task 1 の `WorkDay.note`。
- Produces: ホバー文 `休み(夏季休暇)`・`稼働 13:00〜16:00(通院)`・`休み(夏季休暇。祝日: スポーツの日)`。メモがなければ今までの文。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_calendar.py`(`test_work_day_note` の後に追記):

```python
def test_work_day_note_with_a_memo() -> None:
    holidays = {date(2026, 10, 12): "スポーツの日"}
    days = {
        date(2026, 10, 16): WorkDay(date(2026, 10, 16), note="夏季休暇"),
        date(2026, 10, 17): WorkDay(date(2026, 10, 17), time(13), time(16), "通院"),
        date(2026, 10, 12): WorkDay(date(2026, 10, 12), note="夏季休暇"),
    }
    assert work_day_note(date(2026, 10, 16), holidays, days) == "休み(夏季休暇)"
    assert work_day_note(date(2026, 10, 17), holidays, days) == "稼働 13:00〜16:00(通院)"
    assert work_day_note(date(2026, 10, 12), holidays, days) == "休み(夏季休暇。祝日: スポーツの日)"


def test_member_notes_include_the_memo() -> None:
    sat = date(2026, 10, 17)
    member = Member("田中", work_days=[WorkDay(sat, note="夏季休暇")])
    task = Task("t", assignees=[Assignee("田中", 1.0)])
    notes = member_notes(task, Project("p", members=[member], tasks=[task]), {})
    assert notes[sat] == "田中: 休み(夏季休暇)"
```

`test/test_gantt.py`(`test_assignees_overrides_get_a_mark_on_the_task_row` の後に追記):

```python
async def test_the_work_day_mark_title_includes_the_memo(user: User) -> None:
    project = member_project()
    project.members[0].work_days = [WorkDay(date(2026, 10, 7), note="夏季休暇")]
    mount(project)
    await user.open("/")
    content = user.find(marker="workmark-0-0").elements.pop().content
    assert 'title="甲: 休み(夏季休暇)"' in content
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_calendar.py test/test_gantt.py -q -k "memo" 2>&1 | tail -8`
Expected: 3 件 FAIL(文にメモが入っていない)。

- [ ] **Step 3: 実装する(`src/projectapp/calendar.py` の `work_day_note`)**

関数の本文を次に置き換える:

```python
    if not work_days or day not in work_days:
        return None
    row = work_days[day]
    text = "休み" if row.start is None or row.end is None else f"稼働 {row.start:%H:%M}〜{row.end:%H:%M}"
    details = ([row.note] if row.note else []) + ([f"祝日: {holidays[day]}"] if day in holidays else [])
    return f"{text}({'。'.join(details)})" if details else text
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_calendar.py test/test_gantt.py -q 2>&1 | tail -3`
Expected: PASS(既存の `稼働 10:00〜12:00(祝日: スポーツの日)` も変わらない)。

- [ ] **Step 5: コミットする**

```bash
git add src/projectapp/calendar.py test/test_calendar.py test/test_gantt.py
git commit -m "feat: 稼働日の上書きのホバーにメモを添える" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: ドキュメントと全体確認

**Files:**
- Modify: `CLAUDE.md`、`docs/development.md`、`docs/requests.md`、`docs/superpowers/README.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

- 「`メンバー`には`稼働日の上書き`を持たせられる」の段落に、次を足す: 各日にメモ(30 文字以内。理由。例: 夏季休暇)を付けられる。稼働日のダイアログの`期間で追加`で、期間(範囲カレンダー可)の各日を 1 日ずつの行にまとめて足せる(休み / 稼働の時間帯。`土日祝を除く`は既定オン。登録済みの日は上書きせず飛ばす。1 回 366 日まで)。ホバー(ガントチャートの橙の印)にメモを添える(`休み(夏季休暇)`)。
- 「実装上の注意」のプロジェクトファイルの `version` の説明を、`現在 14`、`14 でメンバーの稼働日のメモ〔work_days[].note〕を足した` に直す。

- [ ] **Step 2: `docs/development.md` を更新する**

- 「形式のバージョンは先頭の `version`(… 現在 13)」を現在 14 にし、バージョンの履歴に `version 14(2026-10-28): members[].work_days[].note を保存する。キーのない古いファイルは空。version 13 以前のファイルにある note は無視する` を足す。
- `workdays.py` のモジュール一覧の説明に、`MAX_NOTE`・`MAX_RANGE_DAYS`・`validate_note`・`expand_range` を足す。

- [ ] **Step 3: `docs/requests.md` を更新する**

要望 41〜46 の節の見出しの `(2026-10-18 に受領。41〜43 は実装済み、44〜46 は未着手)` を `(2026-10-18 に受領。41〜43 は実装済み、44〜46 は稼働日の上書きの拡張で対応)` にし、節の末尾に次を足す:

```markdown
### 44〜46 の対応(2026-10-28)
> **状態**: 実装済み(ブランチ`feature/work-day-notes`。設計書`2026-10-28-work-day-notes-design.md`、計画`plans/2026-10-28-work-day-notes.md`)。`absences`(期間・稼働率・メモ)は作らず、すでにある稼働日の上書き(要望 30)に統合した。45(算出への反映)・46(ダッシュボードへの反映)は要望 30 で実装済み。足したのは、メモ(`WorkDay.note`。`version` 14)と、稼働日のダイアログの`期間で追加`(1 日ずつの行に展開)。稼働率(%)は持たず、半休・時短は時間帯で表す。不在の帯は作らない(橙の印のホバーにメモ)。ダッシュボードの`残りの工数と必要人数`への反映は要望 80 の 1。
```

- [ ] **Step 4: `docs/superpowers/README.md` の表に行を足す**

`| 2026-10-28 | 稼働日の上書きの拡張(メモ・期間で追加) | [設計](specs/2026-10-28-work-day-notes-design.md) | [計画](plans/2026-10-28-work-day-notes.md) | 44〜46 | (マージ後に記録) | — |`(既存の最終行の書式に合わせる)。

- [ ] **Step 5: 全体を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add CLAUDE.md docs/
git commit -m "docs: 稼働日の上書きの拡張(メモ・期間で追加)の仕様と記録を更新する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 実機確認の項目を利用者に渡す(実装者は確認結果を待つ。push・マージはしない)**

1. メンバーとパラメータ → メンバーの`稼働日`ボタン → 行にメモ欄がある。30 文字で止まる。
2. `期間で追加`: 期間(範囲カレンダーでも)・休み・メモを入れて追加 → 月〜金の行だけ増える。`土日祝を除く`を外すと土日も増える。
3. 登録済みの日がある期間で追加 → 既存の行は変わらず、通知に`登録済み`の件数が出る。
4. 土日だけの期間で追加 → ダイアログが閉じず、`追加する日がありません`が出る。
5. 稼働の時間帯(例: 9:00〜12:00)で追加 → 各行に開始・終了が入る。
6. 適用して保存 → 開き直してもメモが残る。ガントチャートの日次で、担当タスクの橙の印にホバーすると`田中: 休み(夏季休暇)`と出る。
7. 古いプロジェクトファイルを開いて保存し直しても、メモは空のまま、エラーが出ない。
