# イベントの期間を休みにする Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** イベントごとのチェックボックス(`稼働日を休みにする`)で、チェックしたイベントの期間を全員の稼働日の休みとして扱う。

**Architecture:** `Event.closed`(version 15)を足し、純粋関数 `events.effective_holidays(project, base)` が祝日の辞書にイベントの休みを混ぜる。開いているプロジェクト(`MainView`・`GanttChart`)は祝日の元の辞書を `base_holidays` に持ち、`holidays` をイベント込みのプロパティにする(結果は `EffectiveHolidays` がキャッシュ)。他プロジェクトを読む経路(全プロジェクトの負荷・プロジェクト参照)は、各プロジェクト自身のイベントで混ぜる。メンバーの稼働日の上書きは、今の仕組み(`day_window`)のまま優先される。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest -n auto -q`)、`uvx ty check src`

**Spec:** [`docs/superpowers/specs/2026-10-28-event-closed-design.md`](../specs/2026-10-28-event-closed-design.md)

## Global Constraints

- 応答・コメント・UI の文言は日本語。コメントは 3 行以内。型ヒント必須(`.claude/RULE.md`)。
- ファイル形式: `FORMAT_VERSION` を 14 → 15。`events[].closed`(真偽値)。キーのない古いファイルは `false`。`null`・真偽値でない値は読込を拒否。version 14 以下の `closed` は無視する。
- 優先順: メンバーの稼働日の上書きが優先(`timeline.day_window` は変えない)。
- 見せ方: 休みの日の背景はイベントの色のまま(祝日の緑は付けない)。帯の文字の頭に `休 `、ホバーに `休み: 全員の稼働日`。
- 祝日と重なる日は祝日の名前を残す。同じ日に複数の休みのイベントが重なるときは、開始日の昇順で先のものの文字列。
- 年は `MIN_YEAR`〜`MAX_YEAR`(2000〜2100)の日だけ足す(イベントの検証は年の範囲を見ないので、関数側で切る)。
- コミットの末尾: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。push・マージは利用者の許可を得てから。

## Review Focus

- 祝日と休みのイベントが同じ日に重なるとき、背景は緑にならず(祝日の日は元から緑)、算出は休みになる(Task 3)。
- 年をまたぐ長いイベントや、`0001-01-01`〜`9999-12-31` のような極端な期間でも、`effective_holidays` が固まらず、キャッシュが効いて操作のたびに再計算しない(Task 1・3)。
- 他プロジェクトのイベントが、開いているプロジェクトに漏れない。開いているプロジェクトのイベントが、他プロジェクトの集計に混ざらない(Task 3)。
- 全員がイベントの休みの日に個別に稼働を上書きしているタスクで、完了予定がその時間帯で進む(Task 3)。
- 稼働日のダイアログのホバー(`祝日: …`)に、休みのイベントの名前が祝日として出ない(Task 3)。

---

## File Structure

- `src/projectapp/models.py` — `Event.closed`、`FORMAT_VERSION = 15`。
- `src/projectapp/events.py` — `effective_holidays`、`EffectiveHolidays`(キャッシュ)。
- `src/projectapp/storage.py` — `_events(value, version)`。
- `src/projectapp/merge.py` — `EVENT_LABELS` に `休み`、`_events` に `closed`、組み立て。
- `src/projectapp/forms.py` — `EventRow.closed`、`build_event_list`、`event_key`、設定ダイアログのチェックボックス。
- `src/projectapp/views.py` — `base_holidays` と `holidays` プロパティ、祝日更新、全プロジェクト集計・参照への配線。
- `src/projectapp/gantt.py` — `base_holidays` と `holidays` プロパティ、背景・稼働日のホバーは `base`、帯の `休 `。
- `src/projectapp/dashboard.py` — `summarize_cross_loads` がプロジェクトごとにイベント込みにする。
- `src/projectapp/reference.py` — 参照先をイベント込みで計算する。
- ドキュメント: `CLAUDE.md`、`docs/development.md`、`docs/requests.md`、`docs/superpowers/README.md`。

---

### Task 1: データ(`Event.closed`・version 15)と `effective_holidays`

**Files:**
- Modify: `src/projectapp/models.py`(`Event`、`FORMAT_VERSION`)
- Modify: `src/projectapp/events.py`(`effective_holidays`、`EffectiveHolidays`)
- Modify: `src/projectapp/storage.py`(`_events`、呼び出し)
- Modify: `src/projectapp/merge.py`
- Test: `test/test_events.py`、`test/test_storage.py`、`test/test_merge.py`、`test/test_reference_storage.py`、`test/test_summary.py`

**Interfaces:**
- Produces:
  - `Event(start, end, text, color="gray", id=..., closed=False)`(`closed` は `id` の後ろ。位置引数の既存の呼び出しを壊さない)。
  - `events.effective_holidays(project: Project, base: Mapping[date, str]) -> dict[date, str]`。
  - `events.EffectiveHolidays`: `get(project: Project, base: dict[date, str]) -> dict[date, str]`。`base` が同じオブジェクトで、休みのイベント(開始・終了・文字列)と `len(base)` が同じ間は、同じ辞書を返す。返した辞書は書き換えない。
  - `storage._events(value, version=FORMAT_VERSION)`。
  - マージの項目名 `休み`(選択のキー `("event", "<イベントid>", "休み")`)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_events.py` の import に `effective_holidays`、`EffectiveHolidays` を足し(既存の `from projectapp.events import (...)` に追記)、`from projectapp.models import Event` を `from projectapp.models import Event, Project` にして、末尾に追記する。

```python
def closed(start: str, end: str, text: str = "夏季休業", **kw: object) -> Event:
    return Event(date.fromisoformat(start), date.fromisoformat(end), text, closed=True, **kw)  # type: ignore[arg-type]


def test_effective_holidays_without_closed_events_equals_the_base() -> None:
    base = {date(2026, 10, 12): "スポーツの日"}
    project = Project("p", events=[Event(date(2026, 10, 1), date(2026, 10, 3), "リリース")])
    assert effective_holidays(project, base) == base


def test_effective_holidays_adds_every_day_of_a_closed_event() -> None:
    project = Project("p", events=[closed("2026-10-26", "2026-10-28")])
    result = effective_holidays(project, {})
    assert result == {date(2026, 10, 26 + n): "夏季休業" for n in range(3)}


def test_effective_holidays_keeps_the_holiday_name_when_they_overlap() -> None:
    base = {date(2026, 10, 27): "祝日"}
    result = effective_holidays(Project("p", events=[closed("2026-10-26", "2026-10-28")]), base)
    assert result[date(2026, 10, 27)] == "祝日" and result[date(2026, 10, 26)] == "夏季休業"


def test_effective_holidays_uses_the_earlier_event_when_closed_events_overlap() -> None:
    events = [closed("2026-10-27", "2026-10-28", "後"), closed("2026-10-26", "2026-10-27", "先")]
    result = effective_holidays(Project("p", events=events), {})
    assert result[date(2026, 10, 27)] == "先" and result[date(2026, 10, 28)] == "後"


def test_effective_holidays_does_not_change_the_base() -> None:
    base: dict[date, str] = {}
    effective_holidays(Project("p", events=[closed("2026-10-26", "2026-10-26")]), base)
    assert base == {}


def test_effective_holidays_clamps_extreme_periods_to_the_supported_years() -> None:
    project = Project("p", events=[closed("0001-01-01", "9999-12-31")])
    result = effective_holidays(project, {})
    assert min(result) == date(2000, 1, 1) and max(result) == date(2100, 12, 31)


def test_effective_holidays_cache_follows_the_events_and_the_base() -> None:
    cache = EffectiveHolidays()
    base: dict[date, str] = {}
    project = Project("p", events=[closed("2026-10-26", "2026-10-26")])
    first = cache.get(project, base)
    assert cache.get(project, base) is first  # 同じ間は使い回す
    project.events[0].end = date(2026, 10, 27)
    assert date(2026, 10, 27) in cache.get(project, base)  # イベントの変更に追従する
    project.events[0].closed = False
    assert cache.get(project, base) == {}
    assert cache.get(project, {date(2026, 10, 12): "祝"}) == {date(2026, 10, 12): "祝"}  # 祝日の差し替えに追従する
```

`test/test_storage.py`: 既存の `test_events_roundtrip_and_are_ordered_as_saved`(1640 行付近)の最後の `assert` を次に置き換え、`FORMAT_VERSION == 14` / `== 14`(1311・1379・1903・1945・2110 行)をすべて 15 にし、`test/test_reference_storage.py:39`、`test/test_summary.py:72` も 15 にする。新しいテストを末尾へ足す。

```python
    assert raw["events"][0] == {
        "start": "2026-10-20", "end": "2026-10-24", "text": "リリース", "color": "red", "id": "e1", "closed": False
    }
```

```python
def test_event_closed_round_trips(tmp_path: Path) -> None:
    event = Event(date(2026, 10, 26), date(2026, 10, 28), "夏季休業", id="e1", closed=True)
    path = save_project(Project("p", events=[event]), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["events"][0]["closed"] is True
    assert load_project(path).events[0].closed is True


def test_events_without_a_closed_key_load_as_open() -> None:
    raw = json.loads(dumps_project(Project("p", events=[Event(date(2026, 10, 26), date(2026, 10, 28), "x", id="e1")])))
    del raw["events"][0]["closed"]
    assert parse_project(json.dumps(raw), "p").events[0].closed is False


def test_closed_in_a_version_14_file_is_ignored() -> None:
    event = Event(date(2026, 10, 26), date(2026, 10, 28), "x", id="e1", closed=True)
    raw = json.loads(dumps_project(Project("p", events=[event])))
    raw["version"] = 14
    assert parse_project(json.dumps(raw), "p").events[0].closed is False


@pytest.mark.parametrize("closed", [None, 1, "true", ["x"]])
def test_bad_event_closed_values_are_rejected(closed: object) -> None:
    raw = json.loads(dumps_project(Project("p", events=[Event(date(2026, 10, 26), date(2026, 10, 28), "x", id="e1")])))
    raw["events"][0]["closed"] = closed
    with pytest.raises(ValueError, match="休み"):
        parse_project(json.dumps(raw), "p")
```

`test/test_merge.py` の `test_event_changed_differently_is_a_conflict_with_a_readable_label` の後に追記する(`ev` ヘルパーは `closed` を取らないので、`replace` で作る。`from dataclasses import replace` を import に足す)。`closed` は 2 値なので、`closed` だけで両側が食い違うことはなく、衝突は起きない。片側だけの変更が残ることを確かめる。

```python
def test_event_closed_is_its_own_item() -> None:
    base = proj(events=[ev("e1")])
    ours = proj(events=[replace(ev("e1"), closed=True)])
    theirs = proj(events=[ev("e1", color="red")])
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == []
    (event,) = result.project.events
    assert (event.closed, event.color) == (True, "red")  # 休みは自分、色は相手


def test_event_closed_change_is_kept_whichever_side_made_it() -> None:
    base = proj(events=[ev("e1")])
    closed_side = proj(events=[replace(ev("e1"), closed=True)])
    unchanged = proj(events=[ev("e1")])
    assert merge_projects(base, closed_side, unchanged).project.events[0].closed is True
    assert merge_projects(base, unchanged, closed_side).project.events[0].closed is True
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_events.py test/test_storage.py test/test_merge.py -q 2>&1 | tail -8`
Expected: `Event` に `closed` がない(`TypeError`)・`effective_holidays` が import できない(`ImportError`)ことで FAIL。

- [ ] **Step 3: 実装する**

`src/projectapp/models.py`:
- `Event` の `id` の次の行に `closed: bool = False  # 期間の稼働日を全員の休みにする` を足す。
- `FORMAT_VERSION = 14` を `FORMAT_VERSION = 15` にし、コメント末尾の `14: 稼働日のメモ〔work_days[].note〕)` を `14: 稼働日のメモ〔work_days[].note〕。15: イベントの休み〔events[].closed〕)` にする。

`src/projectapp/events.py`(import に `from collections.abc import Mapping, Sequence`、`from datetime import date, timedelta`、`from projectapp.models import MAX_EVENT_TEXT_LENGTH, MAX_YEAR, MIN_YEAR, Event, Project, has_control_char` を足し、末尾に追記する):

```python
def effective_holidays(project: Project, base: Mapping[date, str]) -> dict[date, str]:
    """祝日 base に、休みにしたイベント(closed)の期間の全日を足した辞書。祝日と先のイベントの名前を残す。"""
    result = dict(base)
    first, last = date(MIN_YEAR, 1, 1), date(MAX_YEAR, 12, 31)  # 検証は年の範囲を見ないので、ここで切る
    for event in sort_events([e for e in project.events if e.closed]):
        day = max(event.start, first)
        while day <= min(event.end, last):
            result.setdefault(day, event.text)
            day += timedelta(days=1)
    return result


class EffectiveHolidays:
    """effective_holidays の結果を、祝日(同じオブジェクト)と休みのイベントが同じ間は使い回す。返した辞書は書き換えない。"""

    def __init__(self) -> None:
        self._base: dict[date, str] | None = None
        self._key: tuple | None = None
        self._value: dict[date, str] = {}

    def get(self, project: Project, base: dict[date, str]) -> dict[date, str]:
        key = (len(base), tuple((e.start, e.end, e.text) for e in project.events if e.closed))
        if base is not self._base or key != self._key:
            self._value, self._base, self._key = effective_holidays(project, base), base, key
        return self._value
```

`src/projectapp/storage.py`:
- `def _events(value: Any) -> list[Event]:` を `def _events(value: Any, version: int = FORMAT_VERSION) -> list[Event]:` にし、`events.append(...)` の直前に次を足し、`Event(...)` に `closed=closed` を渡す。

```python
        closed = raw.get("closed", False) if version >= 15 else False
        if not isinstance(closed, bool):
            raise ValueError(f"イベントの休みが真偽値ではありません: {closed!r}")
```

```python
        events.append(
            Event(dates[0], dates[1], text.strip(), normalized, _entity_id(raw.get("id"), "イベント"), closed=closed)
        )
```

- `events=_events(raw.get("events")) if ctx.version >= 4 else []` を `events=_events(raw.get("events"), ctx.version) if ctx.version >= 4 else []` にする。

`src/projectapp/merge.py`:
- `EVENT_LABELS = {"start": "開始日", "end": "終了日", "text": "文字列", "color": "色"}` に `"closed": "休み"` を足す。
- `_events` の辞書に `"closed": e.closed` を足す(`{"start": e.start, "end": e.end, "text": e.text, "color": e.color, "closed": e.closed}`)。
- 組み立ての `Event(r["start"], r["end"], r["text"], r["color"], id=key)` に `closed=r["closed"]` を足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_events.py test/test_storage.py test/test_merge.py test/test_reference_storage.py test/test_summary.py -q 2>&1 | tail -5`
Expected: すべて PASS。

- [ ] **Step 5: 全体と型を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add src/projectapp/models.py src/projectapp/events.py src/projectapp/storage.py src/projectapp/merge.py test/
git commit -m "feat: イベントの休み(closed)と effective_holidays を足す(version 15)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 設定ダイアログのチェックボックス

**Files:**
- Modify: `src/projectapp/forms.py`(`EventRow`、`build_event_list`、`event_key`、設定ダイアログのイベント行)
- Test: `test/test_forms.py`

**Interfaces:**
- Consumes: Task 1 の `Event.closed`。
- Produces: `EventRow(original, start, end, text, color, closed=False)`。マーカー `settings-event-{n}-closed`(チェックボックス)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py` の `test_build_event_list_normalizes_dates_and_color_and_sorts` の後に追記し、`test_adding_an_event_applies_it` の後に画面のテストを足す。

```python
def test_event_row_is_open_by_default() -> None:
    assert EventRow(None, "10/20", "10/24", "x", "gray").closed is False


def test_build_event_list_carries_closed() -> None:
    rows = [EventRow(None, "10/26", "10/28", "夏季休業", "gray", True), EventRow(None, "10/1", "10/1", "x", "gray")]
    built = build_event_list(rows, set(), TODAY)
    assert [(e.text, e.closed) for e in built] == [("x", False), ("夏季休業", True)]
```

```python
async def test_closing_an_event_applies_it(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    mount_event_settings([], applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-add").click()
    await asyncio.sleep(0.2)
    user.find(marker="settings-event-0-start").type("2026-10-26")
    user.find(marker="settings-event-0-end").type("2026-10-28")
    user.find(marker="settings-event-0-text").type("夏季休業")
    user.find(marker="settings-event-0-closed").click()
    user.find(marker="settings-apply").click()
    assert applied == [1]
    ((event,),) = received
    assert event.closed is True


async def test_changing_only_closed_counts_as_an_event_change(user: User) -> None:
    applied: list[int] = []
    received: list[list[Event]] = []
    existing = [Event(date(2026, 10, 26), date(2026, 10, 28), "夏季休業", "gray", id="e1")]
    mount_event_settings(existing, applied, received)
    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-event-0-closed").click()
    user.find(marker="settings-apply").click()
    assert [e.closed for e in received[0]] == [True]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_forms.py -q -k "closed or closing" 2>&1 | tail -6`
Expected: `EventRow` に `closed` がない(`TypeError`)ことで FAIL。

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py`:
- `EventRow` の `color: str  # 色名` の次の行に `closed: bool = False  # 期間の稼働日を全員の休みにする` を足す。
- `build_event_list` の `built.append(Event(days[0], days[1], row.text.strip(), color, event_id))` を `built.append(Event(days[0], days[1], row.text.strip(), color, event_id, closed=row.closed))` にする。
- `event_key` の戻り値を `(e.id, e.start, e.end, e.text, e.color, e.closed)` にする。
- 設定ダイアログの `event_rows = [EventRow(e.id, e.start.isoformat(), e.end.isoformat(), e.text, e.color) for e in events or []]` に `e.closed` を足す。
- イベント行の 2 行目(`開始日` / `終了日` / 色)の末尾、色の `ui.input(...).mark(f"settings-event-{n}-color")` の後に、同じ `with ui.row()` の中で次を足す:

```python
                                ui.checkbox(
                                    "稼働日を休みにする",
                                    value=erow.closed,
                                    on_change=lambda e, r=erow: setattr(r, "closed", bool(e.value)),
                                ).mark(f"settings-event-{n}-closed")
```

- イベントの説明文(`開始日〜終了日に、文字列を…`)の後ろに、`「稼働日を休みにする」をチェックした期間は、全員の稼働日を休みとして扱います(メンバーが稼働日の上書きで稼働にした日を除く)` を 1 行の `ui.label(...).classes("text-caption text-grey")` として足す。

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_forms.py -q 2>&1 | tail -3`
Expected: PASS(既存のイベントのテストも通る)。

- [ ] **Step 5: 全体と型を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add src/projectapp/forms.py test/test_forms.py
git commit -m "feat: 設定ダイアログのイベントに「稼働日を休みにする」を足す" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 休みの反映(開いているプロジェクト・他プロジェクトの経路・ガントチャートの見せ方)

**Files:**
- Modify: `src/projectapp/gantt.py`(`base_holidays`・`holidays`、`set_holidays`、`stripes`、`member_notes`、`event_bar`)
- Modify: `src/projectapp/views.py`(`base_holidays`・`holidays`、祝日の更新、ガントチャートと集計・参照への配線)
- Modify: `src/projectapp/dashboard.py`(`summarize_cross_loads`)
- Modify: `src/projectapp/reference.py`(`ReferenceResolver.live`)
- Test: `test/test_timeline.py`、`test/test_dashboard.py`、`test/test_reference.py`、`test/test_gantt.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `effective_holidays`・`EffectiveHolidays`・`Event.closed`。
- Produces:
  - `GanttChart(project, holidays, ...)` の `holidays` 引数は、祝日の元の辞書(`base_holidays`)。`GanttChart.holidays` はイベント込みのプロパティ。`GanttChart.set_holidays(base)`。
  - `MainView.base_holidays: dict[date, str]`、`MainView.holidays`(イベント込みのプロパティ。代入すると `base_holidays` を置き換える)。
  - `dashboard.summarize_cross_loads(projects, period, holidays, member)` の `holidays` は、祝日の元の辞書(各プロジェクトのイベントを足す)。
  - `ReferenceResolver(project_dir, holidays)` の `holidays` は、祝日の元の辞書を返すコールバック。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py` の `test_effective_end_follows_the_project_settings_and_holidays` の後に追記する(`from projectapp.events import effective_holidays` を import に足し、`Event` を既存の `projectapp.models` の import に足す)。

```python
def test_effective_end_skips_the_days_of_a_closed_event() -> None:
    project = Project("p", daily_hours=8.0, events=[Event(date(2026, 10, 12), date(2026, 10, 13), "休業", closed=True)])
    holidays = effective_holidays(project, {})
    assert eff(project, holidays, effort_hours=15.0) == datetime(2026, 10, 14, 16)  # 金 8h + 水 7h(月・火は休業)


def test_a_members_override_beats_a_closed_event() -> None:
    work = [WorkDay(date(2026, 10, 12), time(9), time(17))]
    project = Project(
        "p",
        daily_hours=8.0,
        members=[Member("甲", work_days=work)],
        events=[Event(date(2026, 10, 12), date(2026, 10, 13), "休業", closed=True)],
    )
    holidays = effective_holidays(project, {})
    end = eff(project, holidays, effort_hours=15.0, assignees=[Assignee("甲", 1.0)])
    assert end == datetime(2026, 10, 12, 16)  # 金 8h + 月 7h。月曜は上書きで稼働(休業より優先)
```

`test/test_dashboard.py` に追記する(既存の `project_of`・`span_task`・`WEEK` を使う。`Event` を import に足す)。

```python
def test_cross_load_applies_each_projects_own_closed_events() -> None:
    plain = project_of(span_task("a", 5, 6, 0.6))
    closed_project = project_of(span_task("b", 5, 6, 0.6))
    closed_project.events = [Event(WEEK.start, WEEK.end, "休業", closed=True)]
    both = summarize_cross_loads([plain, closed_project], WEEK, {})["田中"]
    only_plain = summarize_cross_loads([plain], WEEK, {})["田中"]
    assert both.total == only_plain.total  # 休業のプロジェクトのタスクは数えない
    assert closed_project.events[0].closed and not plain.events  # 開いているほうのイベントは混ざらない
```

`test/test_reference.py` に追記する(`from projectapp.reference import compute_reference` と `Event` を import に足す。`save_project` は既存)。

```python
def test_reference_passes_the_event_closed_days_to_the_computation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project("基盤", events=[Event(date(2026, 10, 12), date(2026, 10, 12), "休業", closed=True)])
    save_project(project, tmp_path)
    seen: list[dict[date, str]] = []
    real = compute_reference

    def spy(p: Project, holidays: dict[date, str], now: datetime) -> ReferenceValue:
        seen.append(holidays)
        return real(p, holidays, now)

    monkeypatch.setattr("projectapp.reference.compute_reference", spy)
    ReferenceResolver(lambda: tmp_path, lambda: {date(2026, 10, 1): "祝"}).live("基盤", datetime(2026, 10, 14))
    assert seen == [{date(2026, 10, 1): "祝", date(2026, 10, 12): "休業"}]
```

`test/test_gantt.py` の `test_the_work_day_mark_title_includes_the_memo` の後に追記する(`mount_chart(project)` は `(charts, _)` を返す既存のヘルパー)。

```python
async def test_closed_event_days_are_not_painted_as_holidays(user: User) -> None:
    project = Project("p", base_date=BASE, events=[Event(date(2026, 10, 7), date(2026, 10, 7), "休業", closed=True)])
    mount(project, {date(2026, 10, 8): "祝"})
    await user.open("/")
    html = user.find(marker="stripes").elements.pop().content
    assert html.count(KIND_COLORS[DayKind.HOLIDAY]) == 1  # 10/8 の祝日だけ。休業の 10/7 は緑にしない


async def test_the_chart_computes_with_closed_event_days_but_keeps_the_base(user: User) -> None:
    project = Project("p", base_date=BASE, events=[Event(date(2026, 10, 7), date(2026, 10, 7), "休業", closed=True)])
    charts, _ = mount_chart(project)
    await user.open("/")
    assert charts[0].holidays == {date(2026, 10, 7): "休業"}
    assert charts[0].base_holidays == {}
    project.events[0].closed = False
    assert charts[0].holidays == {}  # 休みを外すと戻る


async def test_closed_event_bar_has_a_mark_and_a_tooltip(user: User) -> None:
    event = Event(date(2026, 10, 8), date(2026, 10, 9), "夏季休業", "gray", id="e1", closed=True)
    mount_with(event_project(event), ViewOptions(period=EVENT_PERIOD))
    await user.open("/")
    bar = user.find(marker="event-bar-e1").elements.pop()
    assert bar._props.get("title") == "夏季休業(休み: 全員の稼働日)"
    await user.should_see("休 夏季休業")


async def test_work_day_mark_does_not_call_a_closed_event_a_holiday(user: User) -> None:
    project = member_project()
    project.events = [Event(date(2026, 10, 7), date(2026, 10, 7), "夏季休業", closed=True)]
    mount(project)
    await user.open("/")
    content = user.find(marker="workmark-0-0").elements.pop().content
    assert "祝日" not in content and "夏季休業" not in content
```

`test/test_views.py` の末尾に追記する(ヘルパー `open_members_view` は既存)。

```python
async def test_the_view_holidays_include_closed_events_but_the_base_does_not(user: User, tmp_path: Path) -> None:
    view = await open_members_view(user, tmp_path)
    view.base_holidays = {date(2026, 10, 12): "スポーツの日"}
    view.project.events = [Event(date(2026, 10, 26), date(2026, 10, 27), "夏季休業", closed=True)]
    assert view.holidays == {
        date(2026, 10, 12): "スポーツの日",
        date(2026, 10, 26): "夏季休業",
        date(2026, 10, 27): "夏季休業",
    }
    assert view.base_holidays == {date(2026, 10, 12): "スポーツの日"}
    view.project.events[0].closed = False
    assert view.holidays == {date(2026, 10, 12): "スポーツの日"}  # 休みを外すと戻る
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_timeline.py test/test_dashboard.py test/test_reference.py test/test_gantt.py test/test_views.py -q -k "closed" 2>&1 | tail -10`
Expected: `base_holidays` がない・`summarize_cross_loads` が各プロジェクトのイベントを見ない・`compute_reference` の引数にイベントの日が入らない・帯に `休 ` がない、で複数 FAIL。timeline の 2 件は、実装なしで PASS する(算出は辞書を受けるだけ。回帰の確認なので、RED でなくてよい)。

- [ ] **Step 3: 実装する**

`src/projectapp/gantt.py`:
- import に `from projectapp.events import EffectiveHolidays`(既存の `projectapp.events` の import があれば名前を足す)を足す。
- `__init__` の `self.holidays = holidays` を次にする(`self.project = project` の後なので、プロパティが使える):

```python
        self.base_holidays = holidays  # 祝日だけ。背景と稼働日のホバーは、これを使う
        self._effective = EffectiveHolidays()
```

- クラスにプロパティを足す(`set_holidays` の直前):

```python
    @property
    def holidays(self) -> dict[date, str]:
        """祝日に、休みにしたイベントの期間を足した辞書。計算はこれを使う。"""
        return self._effective.get(self.project, self.base_holidays)
```

- `set_holidays` を次にする:

```python
    def set_holidays(self, holidays: dict[date, str]) -> None:
        self.base_holidays = holidays
        self.render.refresh()
```

- `self.schedule = Schedule(project, holidays)`(`__init__`)を `self.schedule = Schedule(project, self.holidays)` にする。
- `stripes` の `day_kind(column.start, self.holidays)` を `day_kind(column.start, self.base_holidays)` にする。
- `member_notes(task, self.project, self.holidays)`(1729 行付近)を `member_notes(task, self.project, self.base_holidays)` にする。
- `event_bar` を次に置き換える:

```python
    def event_bar(self, event: Event, left: int, bar_width: int) -> None:
        bar = ui.element("div").style(
            f"position: absolute; left: {left}px; width: {bar_width}px; top: 0;"
            f" height: {EVENT_ROW_HEIGHT_PX}px; overflow: clip; --ev: {color_hex(event.color)}"
        )
        # 属性の値として渡る(HTML にはならない)。全文はマウスオーバーで出す。休みのイベントは、その旨を添える
        bar._props["title"] = f"{event.text}(休み: 全員の稼働日)" if event.closed else event.text
        with bar.mark(f"event-bar-{event.id}"):
            ui.element("div").classes("event-fill")
            # 帯が画面より広くても、名前の列の右端に文字が残るよう、帯の中で固定する(年・月の帯と同じ)
            ui.label(f"休 {event.text}" if event.closed else event.text).style(
                "position: sticky; left: var(--name-w); display: inline-block; padding: 0 4px;"
                " font-size: 10px; line-height: 16px; white-space: nowrap"
            )
```

`src/projectapp/views.py`:
- import に `from projectapp.events import EffectiveHolidays`(`effective_holidays` は使わない)を足す。
- `self.holidays: dict[date, str] = cached or {}` を次にする(`__init__`。`self.project` が先に設定済みであること):

```python
        self.base_holidays: dict[date, str] = cached or {}  # 祝日だけ。計算には、休みのイベントを足した holidays を使う
        self._effective_holidays = EffectiveHolidays()
```

- `self.reference_resolver = ReferenceResolver(lambda: self.project_dir, lambda: self.holidays)` の `lambda: self.holidays` を `lambda: self.base_holidays` にする(参照先は、そのプロジェクト自身のイベントを足す)。
- `GanttChart(self.project, self.holidays, ...)` の第 2 引数を `self.base_holidays` にする。
- クラスにプロパティを足す(`__init__` の外):

```python
    @property
    def holidays(self) -> dict[date, str]:
        """祝日に、休みにしたイベントの期間を足した辞書。日程の計算・集計はこれを使う。"""
        return self._effective_holidays.get(self.project, self.base_holidays)

    @holidays.setter
    def holidays(self, value: dict[date, str]) -> None:
        self.base_holidays = value
```

- `refresh_holidays` の `self.holidays = await download_holidays(...)` はセッターを通るのでそのままでよいが、読みやすさのため `self.base_holidays = await download_holidays(...)` にし、`self.gantt.set_holidays(self.holidays)` を `self.gantt.set_holidays(self.base_holidays)` にする。
- `summarize_cross_loads(chosen, period, self.holidays, self.dashboard_member)` の `self.holidays` を `self.base_holidays` にする。

`src/projectapp/dashboard.py`(import に `from projectapp.events import effective_holidays`):
- `summarize_cross_loads` の冒頭と本体を、プロジェクトごとの休み込みの辞書を使うようにする:

```python
    closed_aware = {id(p): effective_holidays(p, holidays) for p in projects}  # 各プロジェクトの休みのイベントを足す
    open_days = {
        (id(p), m.name): set(_workdays(period, closed_aware[id(p)], work_day_map(m.work_days))) for p in projects for m in p.members
    }
    days = sorted(set().union(*open_days.values())) if open_days else []
    per_project = [(project, _member_spans(project, closed_aware[id(project)], member)) for project in projects]
```

(関数の後半にある既存の `own = [i for i, day in enumerate(days) ...]` とは別の名前にするため、`closed_aware` とする。後半は変えない。)

`src/projectapp/reference.py`(import に `from projectapp.events import effective_holidays`):
- `value, problem = compute_reference(load_project(path), self.holidays(), now), ""` を次にする:

```python
            project = load_project(path)
            value, problem = compute_reference(project, effective_holidays(project, self.holidays()), now), ""
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_timeline.py test/test_dashboard.py test/test_reference.py test/test_gantt.py test/test_views.py -q 2>&1 | tail -5`
Expected: すべて PASS。`events` と `timeline` の循環 import が起きたら、`events.py` の `from projectapp.timeline import Column` は型だけなので `TYPE_CHECKING` の中へ移す(`Column` を実行時に使っていなければ)。

- [ ] **Step 5: 全体と型を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add src/projectapp/ test/
git commit -m "feat: 休みにしたイベントの期間を、日程の計算・集計・参照に反映する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ドキュメントと全体確認

**Files:**
- Modify: `CLAUDE.md`、`docs/development.md`、`docs/requests.md`、`docs/superpowers/README.md`

- [ ] **Step 1: `CLAUDE.md` を更新する**

- 「ガントチャートに、`イベント`(プロジェクト共通)を登録できる。」の段落の末尾に、次を足す: イベントごとにチェックボックス`稼働日を休みにする`(既定オフ)があり、チェックした期間は、全員の稼働日を休みとして扱う(完了予定の算出・割り当て超過・ダッシュボード・担当者向けファイル・PlantUML は、祝日と同じ休み)。メンバーの稼働日の上書きが優先(上書きで稼働にした日は、その人だけ稼働する)。背景はイベントの色のまま(祝日の緑は付けない)で、帯の文字の頭に`休 `、ホバーに`休み: 全員の稼働日`。他のプロジェクトを重ねる集計・プロジェクト参照は、それぞれのプロジェクト自身のイベントで休みにする。
- 「実装上の注意」の `version` の説明を、`現在 15`、`15 でイベントの`closed`を足した` に直す。

- [ ] **Step 2: `docs/development.md` を更新する**

- 「形式のバージョンは…現在 14」を現在 15 にする。
- 「稼働日のメモ(version 14、…)」の項の前に、次の項を足す: イベントの休み(version 15、2026-10-28)は `Event.closed`。保存は `events[].closed`。キーのない古いファイルは `false`、`null`・真偽値でない値は読込を拒否、version 14 以下の `closed` は無視する(`storage._events(value, version)`)。休みの算出は `events.effective_holidays(project, base)`(祝日に、休みのイベントの全日を足す。祝日・先のイベントの名前を残す。年は 2000〜2100 に切る)。開いているプロジェクト(`MainView`・`GanttChart`)は、祝日の元の辞書を `base_holidays` に持ち、`holidays` を `EffectiveHolidays` のキャッシュ付きプロパティにする(計算は `holidays`、背景と稼働日のホバーの `祝日:` は `base_holidays`)。他プロジェクトを読む経路(`dashboard.summarize_cross_loads`・`reference.ReferenceResolver`)は `base` を受け取り、各プロジェクト自身のイベントで `effective_holidays` を通す(渡し忘れると他プロジェクトの休みが抜ける)。マージはイベントの `closed` を別の項目(`休み`)で比べる。

- [ ] **Step 3: `docs/requests.md` を更新する**

要望 82 の `> **状態**: 未着手(設計はまだない)。` を `> **状態**: 実装済み(ブランチ`feature/event-closed`。設計書`2026-10-28-event-closed-design.md`、計画`plans/2026-10-28-event-closed.md`)。決定: メンバーの上書きが優先・祝日と同じ休みに混ぜる(`effective_holidays`)・背景はイベントの色のまま(帯に`休 `)。` にする。「決めたい点(未決)」の節の見出しを `### 決めた点` にし、箇条書きを次の 4 行に置き換える: 反映先は、完了予定・割り当て超過・ダッシュボード・担当者向けファイル・PlantUML(祝日と同じ)。メンバーの上書きが優先。ファイル形式は`version` 15(`events[].closed`)・マージは項目`休み`。日次の見せ方は、背景はイベントの色のまま(帯に`休 `・ホバーに`休み: 全員の稼働日`)。

- [ ] **Step 4: `docs/superpowers/README.md` の表に行を足す**

`| 2026-10-28 | イベントの期間を休みにする | [設計](specs/2026-10-28-event-closed-design.md) | [計画](plans/2026-10-28-event-closed.md) | 要望 82 | (マージ後に記録) | — |`(既存の最終行の書式に合わせる)。設計書の状態行も `> **状態**: 設計書承認済み(2026-10-28)。実装計画 [`plans/2026-10-28-event-closed.md`](../plans/2026-10-28-event-closed.md) — 要望 82 — `feature/event-closed`。` にする。

- [ ] **Step 5: 全体を確認してコミットする**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uvx ty check src 2>&1 | tail -2`
Expected: 全件 PASS、`All checks passed!`

```bash
git add CLAUDE.md docs/
git commit -m "docs: イベントの休みの仕様と記録を更新する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 実機確認の項目を利用者に渡す(実装者は確認結果を待つ。push・マージはしない)**

1. 設定ダイアログの`イベント`で、各行に`稼働日を休みにする`のチェックボックスがある。チェックして適用 → 開き直しても残る。
2. 休みにしたイベントの帯は、文字が`休 …`で始まり、ホバーに`…(休み: 全員の稼働日)`と出る。期間のセルの色は、イベントの色のまま(緑にならない)。
3. 工数のあるタスクの期間が、休みのイベントの日を飛ばして伸びる(チェックを外すと戻る)。元に戻す(`Cmd+Z`)でも追従する。
4. メンバーが稼働日の上書きで、休みのイベントの日に稼働を登録していると、その人の分は、その日も進む。
5. ダッシュボードの`人ごとの負荷`・`工数の予定と実績`・`残りの工数と必要人数`で、休みの日が稼働日に数えられない。
6. 全プロジェクトのスイッチをオンにすると、別のプロジェクトのイベントの休みが、そのプロジェクトのタスクにだけ効く。
7. 稼働日のダイアログ・ガントチャートの橙の印のホバーに、`祝日: 夏季休業` のような表示が出ない。
8. 古いプロジェクトファイル(version 14 以下)を開いて保存し直しても、エラーが出ず、イベントは休みなしのまま。
