# メンバーごとの稼働日の上書き Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 稼働日の上書き(土日祝の稼働・平日の休み・時間枠)を、プロジェクト共通からメンバーごとに作り直す。

**Architecture:** 上書きを`Member.work_days`に持たせる。完了予定の算出は、担当者全員(`Worker`: 換算率 + そのメンバーの上書き)の枠を時刻順に重ね、その時刻に稼働中の人の換算率の合計で工数を消化する。担当者のいないタスクは通常カレンダー。既存のプロジェクト共通の実装(`feature/work-days`の 9 コミット)を、消費側から順に移して、最後に`Project.work_days`を削除する(各タスクのコミットで全体テストが通る)。

**Tech Stack:** Python 3.13、NiceGUI、pytest、ty。

**Spec:** `docs/superpowers/specs/2026-10-23-member-work-days-design.md`(置き換え対象: `2026-10-22-work-days-design.md`、`plans/2026-10-22-work-days.md`)

## Global Constraints

- 応答・コメント・文言は日本語。全関数に型ヒント、コメントは 3 行以内、PEP8(`.claude/RULE.md`)。
- テストは `test/`(`tests/` ではない)。全体は `uv run pytest -n auto -q`、型は `uv run ty check src/projectapp`(現在 `All checks passed!`)。コマンドは `&&` でつなぐ。
- ブランチは`feature/work-days`のまま。コミット末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。
- `FORMAT_VERSION` は 8 のまま(未リリース)。`members[].work_days`は version 8 以上で読み、7 以下は空。トップレベルの`work_days`は読まない・書かない。
- `WorkDay(day, start, end)`・`workdays.py`(`validate_work_days`・`sort_work_days`・`work_day_map`)・時刻の読込の検査(`HH:MM` か `HH:MM:00`)は、そのまま使う。
- 上書きがなければ、算出・集計の結果は今までと同じになる(既存のテストが通る)。
- 時刻の保存形式は`"13:00:00"`、休みは`start`・`end`とも`null`。

## Review Focus

- 担当者が複数で、片方だけが稼働する日(例: A が土曜、B は休み)の完了予定。稼働している人の分だけ消化される。
- 担当者の枠が時刻でずれる 2 人(9–12 と 10–15)の和集合。重なる時間は 2 人分、重ならない時間は 1 人分で消化する。
- 全員が休みの日が連続しても、必ず次の稼働日で終わる(無限ループにならない)。日付が範囲を超えるときは`None`。
- 担当者がメンバーにいない・担当者がいないタスクは、通常カレンダーで今までどおり算出する。
- メンバーを改名・削除しても、上書きが別のメンバーに付かない(`Member`に付いているので、削除すれば消える)。
- マージ: 休みと時間帯変更が衝突したとき、選んだ結果が不正な`WorkDay`にならない(開始と終了を 1 項目)。

---

### Task 1: メンバーの`work_days`を持ち、保存・読込・マージする

**Files:**
- Modify: `src/projectapp/models.py`(`WorkDay`を`Member`の前へ移し、`Member.work_days`を足す)
- Modify: `src/projectapp/storage.py`(`_dump`・`_members`)
- Modify: `src/projectapp/merge.py`(メンバーの`work_days`を日付単位でマージ)
- Test: `test/test_storage.py`、`test/test_merge.py`、`test/test_workdays.py`

**Interfaces:**
- Consumes: 既存の`WorkDay`・`_work_days(value)`(`storage.py`)・`validate_work_days`・`sort_work_days`。
- Produces: `Member.work_days: list[WorkDay]`(既定は空。日付昇順)。保存は`members[].work_days`。マージの`kind="work_day"`、キーは`"<メンバーid>:<YYYY-MM-DD>"`、項目名は`時間帯`。この時点では`Project.work_days`も残す(Task 6 で削除)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_storage.py` の末尾(`test_bad_work_days_are_rejected` の後)に足す。`test_bad_work_days_are_rejected` は、`raw["work_days"] = rows` を`raw["members"][0]["work_days"] = rows`に変え、`Project("p", members=[Member("甲", id="m1")])` を基にする形に書き換える(パラメータ一覧はそのまま)。

```python
def test_member_work_days_round_trip_in_date_order() -> None:
    member = Member(
        "甲",
        id="m1",
        work_days=[WorkDay(date(2026, 10, 18)), WorkDay(date(2026, 10, 17), time(13), time(16))],
    )
    text = dumps_project(Project("p", members=[member]))
    saved = json.loads(text)["members"][0]["work_days"]
    assert saved == [
        {"day": "2026-10-17", "start": "13:00:00", "end": "16:00:00"},
        {"day": "2026-10-18", "start": None, "end": None},
    ]
    loaded = parse_project(text, "p").members[0].work_days
    assert loaded == [WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 18))]


def test_members_without_work_days_load_as_empty() -> None:
    raw = json.loads(dumps_project(Project("p", members=[Member("甲", id="m1")])))
    raw["version"] = 7
    del raw["members"][0]["work_days"]
    assert parse_project(json.dumps(raw), "p").members[0].work_days == []
```

`test/test_merge.py` の末尾に足す(`wd`・`proj` ヘルパーは既存。`Member` は import 済み。`proj(members=[...])` で作る):

```python
def mem(*days: WorkDay) -> Member:
    return Member("甲", 1.0, id="m1", work_days=list(days))


def test_member_work_days_merge_by_member_and_date() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[mem(wd("2026-10-17"), wd("2026-10-18", 12))])
    theirs = proj(members=[mem(wd("2026-10-17", 17))])
    result = merge_projects(base, ours, theirs)
    assert result.conflicts == []
    assert [(w.day, w.end) for w in result.project.members[0].work_days] == [
        (date(2026, 10, 17), time(17)),
        (date(2026, 10, 18), time(12)),
    ]


def test_member_work_day_window_is_one_item() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[mem(WorkDay(date(2026, 10, 17)))])  # 休みにした
    theirs = proj(members=[mem(wd("2026-10-17", 18))])  # 終了を変えた
    result = merge_projects(base, ours, theirs, {("work_day", "m1:2026-10-17", "時間帯"): THEIRS})
    (conflict,) = result.conflicts
    assert (conflict.ours, conflict.theirs) == ("休み", "13:00〜18:00")
    assert result.project.members[0].work_days == [wd("2026-10-17", 18)]


def test_work_days_of_a_deleted_member_are_dropped() -> None:
    base = proj(members=[mem(wd("2026-10-17"))])
    ours = proj(members=[])
    theirs = proj(members=[mem(wd("2026-10-17"))])
    result = merge_projects(base, ours, theirs)
    assert result.project.members == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_storage.py test/test_merge.py -q -k "member_work_day or work_days_of_a_deleted or members_without_work_days" 2>&1 | tail -8`
Expected: FAIL(`Member` が`work_days`を取らない)

- [ ] **Step 3: 実装する**

`src/projectapp/models.py`: `class WorkDay`(`@dataclass`)のブロックを、`class Member` の直前へ移し、docstring の「(プロジェクト共通。」を「(メンバーごと。」に直す。`Member` の最後(`icon`の次)に足す:

```python
    work_days: list["WorkDay"] = field(default_factory=list)  # 稼働日の上書き(日付の昇順。このメンバーだけに効く)
```
(`WorkDay`を前に移したので引用符は不要。`list[WorkDay]`でよい。)

`src/projectapp/storage.py`:
- `_dump`: `data["work_days"] = ...` の行の下に、メンバーごとの並べ替えを足す。メンバーを補う`data["members"].append({...})`の辞書にも`"work_days": []`を足す。

```python
    for saved, member in zip(data["members"], project.members):
        saved["work_days"] = [asdict(row) for row in sort_work_days(member.work_days)]
```
- `_members`: `icon = ...` の次の行に `work_days = _work_days(raw.get("work_days")) if ctx.version >= 8 else []`、`member = Member(name, ratio, levels, icon=icon, work_days=work_days)` に直す。

`src/projectapp/merge.py`:
- `_work_days(project)`(プロジェクト共通)の下に足す:

```python
def _member_work_days(project: Project) -> dict[str, Record]:
    return {f"{m.id}:{w.day.isoformat()}": {"window": (w.start, w.end)} for m in project.members for w in m.work_days}
```
- `merge_projects` の `work_days = merger.collection(...)` の下に:

```python
    member_days = merger.collection(
        "work_day",
        WORK_DAY_LABELS,
        _member_work_days(base),
        _member_work_days(ours),
        _member_work_days(theirs),
        _show_window,
    )
```
 (プロジェクト共通の collection と kind は同じ`work_day`だが、キーが`"<id>:<日付>"`と`"<日付>"`で重ならないので、そのまま共存させる。Task 6 でプロジェクト共通の側を削除する。)
- `Project(...)` の組み立ての前に、メンバーへ戻す:

```python
    built_members = [
        Member(r["name"], r["ratio"], dict(r["levels"]), id=key, icon=r["icon"]) for key, r in members.items()
    ]
    by_id = {m.id: m for m in built_members}
    for key, r in member_days.items():
        member_id, day = key.split(":", 1)
        if member_id in by_id:  # 削除されたメンバーの上書きは捨てる
            by_id[member_id].work_days.append(WorkDay(date.fromisoformat(day), *r["window"]))
    for member in built_members:
        member.work_days = sort_work_days(member.work_days)
```
 `members=[Member(...) for ...]` を `members=built_members` に置き換える。`Conflict.kind` のコメントに`work_day`(メンバーごと)が既にあることを確かめる。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uv run ty check src/projectapp | tail -1`
Expected: すべて PASS(ここまでのプロジェクト共通の`work_days`は残っている)

- [ ] **Step 5: コミット**

```bash
git add src test && git commit -m "feat: メンバーが稼働日の上書きを持ち、保存・読込・マージする

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 完了予定の算出を、担当者の枠の重なりにする

**Files:**
- Modify: `src/projectapp/timeline.py`(`Worker`・`crew_of`・`calc_end`・`computed_end`・`_own_end`・`assignees_rate`)
- Modify: `src/projectapp/reassign.py`(`reviewed_end`)
- Modify: `src/projectapp/task_dialog.py`(`DateTimeFields`・`open_task_dialog`)
- Modify: `src/projectapp/views.py`(3 つの`open_task_dialog`呼び出しから`work_days=`を外す)
- Test: `test/test_timeline.py`(`calc_end`の`work_days`引数のテストを`crew`に書き換える)、`test/test_reassign.py`、`test/test_task_dialog*.py`(`grep -ln "DateTimeFields\|work_days" test/*.py`)

**Interfaces:**
- Consumes: Task 1 の`Member.work_days`、`day_window(day, daily_hours, work_start, holidays, work_days_map)`(1 人分のカレンダー。そのまま使う)、`effective_ratio`・`combine_rate`。
- Produces:
  - `Worker(rate: float = 1.0, days: Mapping[date, WorkDay] = {})`(frozen dataclass)。
  - `crew_of(assignees, members, parameters=None) -> list[Worker]`(メンバーにいない担当者は入れない)。
  - `calc_end(start, effort_hours, daily_hours, work_start, holidays, crew=None) -> datetime | None`。`effort_hours`は基準の人の時間(換算率で割らない)。`crew`が空・`None`なら`[Worker()]`。
  - `computed_end(start, effort_hours, daily_hours, work_start, holidays, deadline=None, rate=1.0, crew=None)`。`crew`があれば`rate`は使わない。
  - `reviewed_end(task, old_rate, new_rate, daily_hours, work_start, holidays, now, crew=None)`。
  - `DateTimeFields(task, work_start, daily_hours, holidays, crew=())`、`set_crew(crew)`(`set_rate`を置き換える)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_timeline.py`:`calc_end(..., work_days)` を呼ぶ既存のテスト(`grep -n "work_days\|WorkDay" test/test_timeline.py`)を、`crew=[Worker(1.0, work_day_map([...]))]` を渡す形に書き換える(期待値は変えない)。そのうえで次を足す(`Worker`・`crew_of` を import に足す。`H = {}` 相当の空の祝日辞書、2026-10-16 は金曜、10-17 は土曜):

```python
def test_two_workers_with_the_same_calendar_match_the_summed_rate() -> None:
    crew = [Worker(1.0), Worker(0.5)]
    one = calc_end(datetime(2026, 10, 12, 9), 9.0, 6.5, time(9), {}, [Worker(1.5)])
    assert calc_end(datetime(2026, 10, 12, 9), 9.0, 6.5, time(9), {}, crew) == one


def test_only_the_worker_who_works_on_the_override_day_burns_effort() -> None:
    a = Worker(1.0, work_day_map([WorkDay(date(2026, 10, 17), time(13), time(16))]))
    b = Worker(1.0)
    # 金曜 9:00 から 8h: 2 人で 4h → 13:00 に終わり、土曜は使わない
    assert calc_end(datetime(2026, 10, 16, 9), 8.0, 6.5, time(9), {}, [a, b]) == datetime(2026, 10, 16, 13)
    # 30h: 金曜 13h → 残り 17h。土曜は A だけが 13–16 の 3h → 残り 14h。月曜は 2 人で 13h → 残り 1h は 0.5h 後
    assert calc_end(datetime(2026, 10, 16, 9), 30.0, 6.5, time(9), {}, [a, b]) == datetime(2026, 10, 19, 9, 30)
    # A に土曜の上書きがなければ、残り 4h を火曜の 2h で終える
    assert calc_end(datetime(2026, 10, 16, 9), 30.0, 6.5, time(9), {}, [Worker(1.0), b]) == datetime(2026, 10, 20, 11)


def test_shifted_windows_are_stacked_by_time() -> None:
    a = Worker(1.0, work_day_map([WorkDay(date(2026, 10, 17), time(9), time(12))]))
    b = Worker(1.0, work_day_map([WorkDay(date(2026, 10, 17), time(10), time(15))]))
    # 土曜 9–10 は A だけ(1h)、10–12 は 2 人(4h)、12–15 は B だけ(3h)。累計 8h。
    end = calc_end(datetime(2026, 10, 17, 0), 7.0, 6.5, time(9), {}, [a, b])
    # 9–10 で 1h、10–12 で 4h → 5h。残り 2h は B だけの 12–14
    assert end == datetime(2026, 10, 17, 14)


def test_a_rest_day_for_every_worker_is_skipped() -> None:
    rest = work_day_map([WorkDay(date(2026, 10, 19))])
    end = calc_end(datetime(2026, 10, 19, 9), 1.0, 6.5, time(9), {}, [Worker(1.0, rest)])
    assert end == datetime(2026, 10, 20, 10)


def test_no_crew_uses_the_default_calendar() -> None:
    assert calc_end(datetime(2026, 10, 16, 15), 6.5, 6.5, time(9), {}) == datetime(2026, 10, 19, 15)
    assert calc_end(datetime(2026, 10, 16, 15), 6.5, 6.5, time(9), {}, []) == datetime(2026, 10, 19, 15)  # 金曜 0.5h + 月曜 6h


def test_crew_of_skips_unknown_assignees_and_carries_member_calendars() -> None:
    m = Member("甲", 1.0, id="m1", work_days=[WorkDay(date(2026, 10, 17), time(13), time(16))])
    crew = crew_of([Assignee("甲", 0.5), Assignee("乙", 1.0)], [m])
    assert [w.rate for w in crew] == [0.5]
    assert date(2026, 10, 17) in crew[0].days
```

`test/test_reassign.py`:`reviewed_end(..., work_days)` を呼ぶテストを`crew=`に直す。上書きなしの既存の期待値は変えない。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_timeline.py -q 2>&1 | tail -8`
Expected: FAIL(`Worker` がない)

- [ ] **Step 3: `timeline.py` を実装する**

`import` に `from dataclasses import dataclass, field`(なければ)・`Sequence` を足す。`MAX_WORKDAYS` の下か`_default_open`の前に`Worker`、`conversion_rate`の前に`crew_of`:

```python
@dataclass(frozen=True)
class Worker:
    """完了予定の算出に使う担当者 1 人。rate は換算率(相対比率 × 割り当て率)、days は日付 → 稼働日の上書き。"""

    rate: float = 1.0
    days: Mapping[date, WorkDay] = field(default_factory=dict)


def crew_of(assignees: list[Assignee], members: list[Member], parameters: list[Parameter] | None = None) -> list[Worker]:
    """担当者を算出用の Worker にする。メンバーにいない担当者は入れない。"""
    by_name = {m.name: m for m in members}
    chosen = parameters or []
    return [
        Worker(combine_rate(effective_ratio(by_name[a.name], chosen), a.allocation), work_day_map(by_name[a.name].work_days))
        for a in assignees
        if a.name in by_name
    ]
```

`assignees_rate` の中身を `rates = [w.rate for w in crew_of(assignees, members, parameters)]; return sum(rates) if rates else 1.0` に直す(挙動は同じ)。

`calc_end` / `_calc_end` を置き換える:

```python
def calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    crew: Sequence[Worker] | None = None,
) -> datetime | None:
    """基準の人の工数を、担当者全員の稼働の枠(その人の上書き、なければ始業から稼働可能時間)に割り当てた終了日時。

    枠が重なる時刻は、稼働中の担当者の換算率の合計で工数を消化する。crew が空なら換算率1の1人。
    工数が不正(NaN・inf・0以下・稼働日数の上限超え)、daily_hoursが0以下・24超、
    または日付が範囲を超えるときは、例外にせずNoneを返す。
    """
    workers = list(crew) if crew else [Worker()]
    total = sum(w.rate for w in workers)
    if not isfinite(effort_hours) or effort_hours <= 0 or not 0 < daily_hours <= 24:
        return None
    if not isfinite(total) or total <= 0 or effort_hours / total > daily_hours * MAX_WORKDAYS:
        return None
    try:
        return _calc_end(start, effort_hours, daily_hours, work_start, holidays, workers)
    except OverflowError:
        return None


def _calc_end(
    start: datetime,
    effort_hours: float,
    daily_hours: float,
    work_start: time,
    holidays: dict[date, str],
    workers: list[Worker],
) -> datetime:
    remaining = effort_hours
    day, cursor = start.date(), start
    while True:
        windows = [
            (w.rate, window)
            for w in workers
            if (window := day_window(day, daily_hours, work_start, holidays, w.days)) is not None
        ]
        points = sorted({max(p, cursor) for _, window in windows for p in window})
        for left, right in zip(points, points[1:]):
            speed = sum(rate for rate, (opens, closes) in windows if opens <= left and right <= closes)
            if speed <= 0:
                continue
            capacity = speed * (right - left).total_seconds() / 3600
            if remaining <= capacity:
                return left + timedelta(hours=remaining / speed)
            remaining -= capacity
        day += timedelta(days=1)
        cursor = datetime.combine(day, time.min)
```

`computed_end` の引数 `work_days` を `crew: Sequence[Worker] | None = None` に直し、本体を:

```python
    if start is not None and effort_hours > 0:
        workers = list(crew) if crew else [Worker(combine_rate(rate, 1.0))]
        end = calc_end(start, effort_hours, daily_hours, work_start, holidays, workers)
        if end is not None:
            return end
```
`_own_end` の末尾の呼び出しは、`conversion_rate(task, project)` と `work_day_map(project.work_days)` の 2 引数を、`crew=crew_of(task.assignees, project.members, project.parameters)` に置き換える(`rate`は既定の 1.0)。`timeline.py` から`work_day_map`の import が不要なら外すが、`crew_of`が使うので残す。

- [ ] **Step 4: `reassign.py`・`task_dialog.py`・`views.py` を直す**

`reassign.py`: `reviewed_end` の最後の引数を `crew: Sequence[Worker] | None = None` にし、`return calc_end(start, remaining, daily_hours, work_start, holidays, list(crew) if crew else [Worker(combine_rate(new_rate, 1.0))])`。`WorkDay`・`Mapping`の import を外し、`Worker`を足す。

`task_dialog.py`:
- `DateTimeFields.__init__` の `rate: float = 1.0, work_days: ... = None` を `crew: Sequence[Worker] = ()` に。`self._work_days` と `self._rate` を `self._crew = list(crew)` にする。`set_rate` を `set_crew(self, crew: Sequence[Worker]) -> None: self._crew = list(crew)` に置き換える(呼び出し元の再計算の呼び方は`set_rate`の時と同じに保つ)。`_computed_end` の最後の 2 引数 `self._rate, self._work_days` を `crew=self._crew` に。
- `open_task_dialog`: `work_days` 引数を削除。`initial_rate = assignees_rate(...)` はそのまま(確認ダイアログの比較に使う)。`DateTimeFields(initial, work_start, daily_hours, holidays or {}, crew_of(initial.assignees, member_list))`。担当者の選択が変わるところ(`rate = sum(combine_rate(m.ratio, f) for m, f in chosen) if chosen else 1.0` / `fields.set_rate(rate)`)は、`fields.set_crew([Worker(combine_rate(m.ratio, f), work_day_map(m.work_days)) for m, f in chosen])` に直す。保存時の `reviewed_end(..., now(), work_days)` は `crew_of(result.assignees, member_list)` を渡す。
- 不要になった`WorkDay`・`Mapping`・`date`の import があれば整理する。

`views.py`: `add_task`・`add_top_task`・`edit_task` の `work_days=work_day_map(self.project.work_days),` を削除する(`work_day_map` の import は Task 6 まで他で使われていれば残す)。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -4 && uv run ty check src/projectapp | tail -2`
Expected: すべて PASS。**既存の算出のテストが 1µs ずれて落ちたら**(浮動小数の丸め)、`remaining`を秒の整数マイクロ秒で持つ形(`timedelta`で引く)に直して、期待値は変えない。`ty` は`All checks passed!`。

- [ ] **Step 6: コミット**

```bash
git add src test && git commit -m "feat: 完了予定の算出が、担当者ごとの稼働日の上書きを重ねて使う

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ダッシュボードの負荷・予定工数を、人ごとの稼働日にする

**Files:**
- Modify: `src/projectapp/dashboard.py`(`summarize_loads`・`summarize_cross_loads`・`summarize_workload`)
- Test: `test/test_dashboard.py`

**Interfaces:**
- Consumes: `Member.work_days`、`_workdays(period, holidays, work_days_map)`、`day_hours`、`_day_peak`、`_stats_of`。
- Produces: 人ごとの稼働日で集計する`summarize_loads`・`summarize_cross_loads`・`summarize_workload`(シグネチャは変えない)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard.py` の末尾に足す。既存の`test_cross_load_ignores_a_project_on_days_it_does_not_work`(プロジェクト共通の`work_days`を使う)は、メンバーの`work_days`を使う形に書き換える(A の甲に土曜、B の甲には上書きなし)。`test_*work_day*`の他のダッシュボードのテストも同様に、`Project(work_days=...)`を`Member("…", work_days=[...])`に直す。

```python
def test_load_counts_only_the_members_own_workdays() -> None:
    sat = WorkDay(date(2026, 10, 17), time(9), time(12))
    task = Task("t", planned_start=datetime(2026, 10, 16, 9), planned_end=datetime(2026, 10, 19, 17), planned_end_manual=True)
    task.assignees = [Assignee("甲", 1.0), Assignee("乙", 1.0)]
    project = Project("p", members=[Member("甲", work_days=[sat]), Member("乙")], tasks=[task])
    period = Period(date(2026, 10, 12), date(2026, 10, 18))
    loads = summarize_loads(project, period, {})
    # 甲は土曜も稼働日(金・土の 2 日)、乙は金曜のみ(土日は休み)
    assert loads["甲"].peak == pytest.approx(1.0) and loads["乙"].peak == pytest.approx(1.0)
    cross = summarize_cross_loads([project], period, {})
    sat_row = next(d for d in cross["甲"].days if d.day == date(2026, 10, 17))
    assert sat_row.total == pytest.approx(1.0)
    sat_row_b = next(d for d in cross["乙"].days if d.day == date(2026, 10, 17))
    assert sat_row_b.total == 0.0  # 乙は土曜に稼働しない


def test_planned_hours_use_each_members_calendar() -> None:
    sat = WorkDay(date(2026, 10, 17), time(9), time(12))
    task = Task("t", planned_start=datetime(2026, 10, 17, 9), planned_end=datetime(2026, 10, 17, 17), planned_end_manual=True)
    task.assignees = [Assignee("甲", 1.0), Assignee("乙", 1.0)]
    project = Project("p", members=[Member("甲", work_days=[sat]), Member("乙")], tasks=[task])
    rows = {r.name: r.planned for r in summarize_workload(project, Period(date(2026, 10, 12), date(2026, 10, 18)), NOW, {})}
    assert rows["甲"] == pytest.approx(3.0)  # 土曜 9–12
    assert rows["乙"] == pytest.approx(0.0)


def test_unassigned_planned_hours_use_the_default_calendar() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 16, 9), planned_end=datetime(2026, 10, 17, 17), planned_end_manual=True)
    project = Project("p", tasks=[task])
    rows = {r.name: r.planned for r in summarize_workload(project, Period(date(2026, 10, 12), date(2026, 10, 18)), NOW, {})}
    assert rows[UNASSIGNED] == pytest.approx(project.daily_hours)  # 金曜だけ
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard.py -q 2>&1 | tail -8`
Expected: FAIL

- [ ] **Step 3: 実装する**

`summarize_loads`: `days` をメンバーごとにする。

```python
def summarize_loads(project, period, holidays, member=None):
    spans = _member_spans(project, holidays, member)
    return {
        entry.name: _load_stats(
            spans.get(entry.name, []), _workdays(period, holidays, work_day_map(entry.work_days))
        )
        for entry in project.members
        if member is None or entry.name == member
    }
```

`summarize_cross_loads`: 日の集合を、(プロジェクト, 名前)ごとに持つ。

```python
    open_days = {
        (id(p), m.name): set(_workdays(period, holidays, work_day_map(m.work_days))) for p in projects for m in p.members
    }
    days = sorted(set().union(*open_days.values())) if open_days else []
```
 名前ごとのループでは、`for project, spans in per_project:` の中の`open_days[id(project)]`を`open_days[(id(project), name)]`に直す(`name not in {...members}`の `continue` の後なので KeyError にならない)。`everything`の要素は`(project, items)`のまま、`overall`は`open_days[(id(p), name)]`で絞る。

`summarize_workload`: `work_days`・`days`の共通計算をやめ、キー(担当者名)ごとの日ごとの稼働時間を作る。

```python
    calendars = {m.name: work_day_map(m.work_days) for m in project.members}
    tables: dict[str, list[tuple[date, float]]] = {}

    def table(key: str) -> list[tuple[date, float]]:
        if key not in tables:  # 未割当は通常カレンダー
            cal = calendars.get(key)
            rows = ((day, day_hours(day, project.daily_hours, holidays, cal)) for day in period.days())
            tables[key] = [(day, h) for day, h in rows if h > 0]
        return tables[key]
```
 タスクのループでは、`hours` の一括計算をやめ、`for key, allocation, share in _shares(...)` の中で:

```python
            if start is not None and end is not None and end > start and isfinite(allocation):
                planned[key] += allocation * sum(h for day, h in table(key) if _covers(start, end, day))
```
 `is_workday`・`day_hours` の import を整理し、`_workdays`は引き続き使う。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uv run ty check src/projectapp | tail -1`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src test && git commit -m "feat: ダッシュボードの負荷と予定工数が、メンバーごとの稼働日を使う

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ガントチャートの表示を、担当者の上書きの印にする

**Files:**
- Modify: `src/projectapp/calendar.py`(`effective_kind`・`DayKind.REST`を削除、`member_notes`を足す)
- Modify: `src/projectapp/gantt.py`(`work_days`の属性・日付ヘッダーの`note`・縞の`effective_kind`を外し、行の印を足す)
- Test: `test/test_calendar.py`、`test/test_gantt.py`

**Interfaces:**
- Consumes: Task 1 の`Member.work_days`、既存の`work_day_note(day, holidays, work_days_map)`(`稼働 13:00〜16:00`/`休み`、祝日名つき)。
- Produces: `calendar.member_notes(task, project, holidays) -> dict[date, str]`(担当者が上書きした日 → `田中: 稼働 13:00〜16:00`。複数なら`/`で結ぶ)。日次の通常タスクの行に、マーカー`workmark-{key}-{ti}`の 1 要素。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_calendar.py`:`effective_kind`・`DayKind.REST` のテスト(`test_effective_kind_follows_overrides`)を削除する。`test_work_day_note` は残す。足す:

```python
def test_member_notes_list_each_assignees_override_by_day() -> None:
    sat = date(2026, 10, 17)
    a = Member("田中", work_days=[WorkDay(sat, time(13), time(16))])
    b = Member("鈴木", work_days=[WorkDay(sat), WorkDay(date(2026, 10, 12))])
    task = Task("t", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)])
    project = Project("p", members=[a, b], tasks=[task])
    notes = member_notes(task, project, {date(2026, 10, 12): "スポーツの日"})
    assert notes[sat] == "田中: 稼働 13:00〜16:00 / 鈴木: 休み"
    assert notes[date(2026, 10, 12)] == "鈴木: 休み(祝日: スポーツの日)"


def test_member_notes_ignore_non_members_and_unassigned_tasks() -> None:
    project = Project("p", members=[Member("田中", work_days=[WorkDay(date(2026, 10, 17))])])
    assert member_notes(Task("t"), project, {}) == {}
    assert member_notes(Task("t", assignees=[Assignee("他", 1.0)]), project, {}) == {}
```

`test/test_gantt.py`:日付ヘッダーの`note`・`box-shadow`・`REST` の背景に関するテスト(`grep -n "note\|REST\|work_day\|WorkDay" test/test_gantt.py`)を、次に置き換える(既存の日次チャートを作るヘルパーに合わせる):
- 担当者の上書きがある日次チャートで、`workmark-…` の要素があり、`title`に`田中: 稼働 13:00〜16:00`を含む。
- 週次・月次では`workmark-…`が出ない。担当者なし・上書きなしのタスクの行にも出ない。
- 日付ヘッダー(`label-row-cells`)に`title=`も橙の`box-shadow`も付かない(上書きがあっても)。
- 土曜の縞の色は上書きがあっても変わらない(`stripes` の中身が通常と同じ)。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_calendar.py test/test_gantt.py -q 2>&1 | tail -8`
Expected: FAIL

- [ ] **Step 3: 実装する**

`calendar.py`:`DayKind.REST`・`effective_kind` を削除する(`Mapping`・`WorkDay`の import は`work_day_note`が使う間は残す)。足す:

```python
def member_notes(task: Task, project: Project, holidays: dict[date, str]) -> dict[date, str]:
    """担当者が上書きした日 → 説明(`田中: 稼働 13:00〜16:00`)。複数なら ` / ` で結ぶ。担当者がメンバーでなければ数えない。"""
    by_name = {m.name: m for m in project.members}
    notes: dict[date, list[str]] = {}
    for assignee in task.assignees:
        member = by_name.get(assignee.name)
        if member is None:
            continue
        days = {row.day: row for row in member.work_days}
        for day in days:
            text = work_day_note(day, holidays, days)
            if text:
                notes.setdefault(day, []).append(f"{member.name}: {text}")
    return {day: " / ".join(lines) for day, lines in notes.items()}
```
(`Task`・`Project`を import に足す。循環 import になるなら関数内 import にせず、`TYPE_CHECKING` ブロックで型だけ import する。)

`gantt.py`:
- `KIND_COLORS` から`DayKind.REST`を外す。`GanttChart.__init__`と`set_project`の`self.work_days = work_day_map(...)`、`work_day_map`・`effective_kind`の import、`label_row`の`note=work_day_note(...)`を削除する。`stripes`は`KIND_COLORS.get(day_kind(column.start, self.holidays), "transparent")`。
- `header_cell_html(column, width, weekday, note=None)` の`note`引数・`title`・`mark`を削除し、元の形に戻す(`test_gantt.py` の`note`を使うテストは Step 1 で削除済み)。
- 行の印を足す。定数 `WORKMARK_HEIGHT_PX = 4`。メソッド:

```python
    def work_day_strip(self, key: int | str, ti: int, notes: dict[date, str], columns: list[Column], width: int) -> None:
        """日次の行の下端に、担当者が稼働日を上書きした日の印(橙)を出す。内容は日付と、メンバー名・時刻の文字列(エスケープする)。"""
        cells = "".join(
            f'<div title="{html.escape(notes[c.start], quote=True)}" style="width:{width}px;height:100%;'
            f'background:{DEADLINE_COLOR};pointer-events:auto"></div>'
            if c.start in notes
            else f'<div style="width:{width}px"></div>'
            for c in columns
        )
        ui.html(f'<div style="display:flex;height:100%">{cells}</div>', sanitize=False).style(
            f"position: absolute; left: var(--name-w); bottom: 0; height: {WORKMARK_HEIGHT_PX}px; pointer-events: none"
        ).mark(f"workmark-{key}-{ti}")
```
 `task_row` の通常タスクの経路(`start = self.schedule.start(task)` の直前)に:

```python
            if self.view_scale is Scale.DAY and (notes := member_notes(task, self.project, self.holidays)):
                self.work_day_strip(key, ti, notes, columns, width)
```
 (`pointer-events: none` の外枠の中の印だけ`auto`にする。`html.escape`・`DEADLINE_COLOR`・`member_notes` の import を足す。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uv run ty check src/projectapp | tail -1`
Expected: PASS(`project.work_days`を使うガントのテストが残っていれば書き換える)

- [ ] **Step 5: コミット**

```bash
git add src test && git commit -m "feat: ガントチャートの日次で、担当者ごとの稼働日の上書きを行の印で示す

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: メンバーのダイアログで稼働日を編集し、設定ダイアログの節を外す

**Files:**
- Modify: `src/projectapp/forms.py`(`MemberRow`・`build_members`・`members_panel`・`member_columns`・`member_table_min_rem`、設定ダイアログの稼働日の節を削除、`work_day_key`削除)
- Modify: `src/projectapp/views.py`(`apply_work_days`・`open_settings_dialog`への引数を削除)
- Test: `test/test_forms.py`、`test/test_views.py`

**Interfaces:**
- Consumes: 既存の`WorkDayRow(day, start, end, rest)`・`build_work_day_list(rows, today) -> list[WorkDay]`(`forms.py`)、Task 1 の`Member.work_days`。
- Produces: `MemberRow.work_days: list[WorkDayRow]`。`build_members(..., today: date | None = None)`が`Member.work_days`を作る(エラー文言の頭にメンバー名)。メンバーの表に列`稼働日`(ボタン`member-workday-open-{index}`。ラベルは`稼働日(n)`)。ダイアログ内のマーカー: `member-workday-{n}-day|start|end|rest|remove`、`member-workday-add`、`member-workday-close`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py`:設定ダイアログの稼働日の節のテスト(`mount_work_day_settings`、`settings-workday-*`、`test_apply_work_days...`)を削除する(`WorkDayRow`/`build_work_day_list` の単体テストは残す)。足す:

```python
def test_build_members_carries_work_day_rows_and_prefixes_errors_with_the_name() -> None:
    row = MemberRow("甲", "甲", 100.0, work_days=[WorkDayRow("10/17", "13", "16", False), WorkDayRow("10/18", "", "", True)])
    members, _ = build_members([row], ["甲"], lambda name: 0, today=date(2026, 10, 1))
    assert members[0].work_days == [WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 18))]
    bad = MemberRow("甲", "甲", 100.0, work_days=[WorkDayRow("10/17", "16", "13", False)])
    with pytest.raises(ValueError, match="甲"):
        build_members([bad], ["甲"], lambda name: 0, today=date(2026, 10, 1))
```
 メンバーの表のテスト(`member_columns`・`member_table_min_rem`)の期待列数・幅を、稼働日の列(`MEMBER_WORK_DAYS_COLUMN_REM = 7`)ぶん増やす。ダイアログ操作のテスト(既存のメンバーのダイアログの `User`/`mount` の書き方に合わせる。`grep -n "member-add\|member-apply" test/test_forms.py | head`):
 - `member-workday-open-0` を押す → `member-workday-add` で行を足し、`member-workday-0-day`=`10/17`・`-start`=`13`・`-end`=`16` を入れて`member-workday-close`で閉じる → `member-apply` で`on_apply`が呼ばれ、渡された`Member.work_days`が`[WorkDay(2026-10-17, 13:00, 16:00)]`。
 - 休みにチェックを入れる(`member-workday-0-rest`)と、開始・終了が無効になる。
 - 不正(開始 ≥ 終了)のまま適用すると`member-error`に文言(メンバー名つき)が出て、`on_apply`は呼ばれない。
 - 稼働日を編集すると、タブの`dirty()`が真になる。

`test/test_views.py`:`test_apply_work_days_marks_the_project_dirty_and_the_end_date_follows` を、`apply_members` で`Member.work_days`を設定したときに未保存扱いになり、そのメンバーが担当のタスクの完了予定が変わる、というテストに書き換える。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py test/test_views.py -q 2>&1 | tail -8`
Expected: FAIL

- [ ] **Step 3: 実装する**

`forms.py`:
- 設定ダイアログ(`open_settings_dialog`)から、`work_days`・`on_work_days` 引数、`card_width` の`and work_days is None`、`work_rows` とその節(`if work_days is not None:` のブロック全体)、`build_work_days`、`commit`/`pending`/`apply` の`wlist` の受け渡し、`work_day_key` を削除する。節の部品(refreshable の表・休みの切替・追加・削除)は、次の関数に移して再利用する。

```python
def work_day_editor(rows: list[WorkDayRow], marker: str) -> None:
    """稼働日の上書きの行(日付 / 開始 / 終了 / 休み / 削除)と追加ボタン。rows をその場で書き換える。"""

    @ui.refreshable
    def table() -> None:
        with ui.column().classes("w-full gap-1"):
            for n, wrow in enumerate(rows):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.input("日付", value=wrow.day, on_change=lambda e, r=wrow: setattr(r, "day", e.value or "")).classes(
                        "w-36"
                    ).mark(f"{marker}-{n}-day")
                    for label, name in (("開始", "start"), ("終了", "end")):
                        field = ui.input(
                            label, value=getattr(wrow, name), on_change=lambda e, r=wrow, k=name: setattr(r, k, e.value or "")
                        ).classes("w-24").mark(f"{marker}-{n}-{name}")
                        field.set_enabled(not wrow.rest)
                    ui.checkbox("休み", value=wrow.rest, on_change=lambda e, r=wrow: toggle(r, bool(e.value))).mark(
                        f"{marker}-{n}-rest"
                    )
                    ui.button(icon="delete", on_click=lambda _e, r=wrow: remove(r)).props("flat dense color=negative").mark(
                        f"{marker}-{n}-remove"
                    )

    def toggle(wrow: WorkDayRow, value: bool) -> None:
        wrow.rest = value
        table.refresh()

    def remove(wrow: WorkDayRow) -> None:
        rows.remove(wrow)
        table.refresh()

    def add() -> None:
        rows.append(WorkDayRow("", "", "", False))
        table.refresh()

    table()
    ui.button("稼働日を追加", icon="add", on_click=add).props("flat dense").mark(f"{marker}-add")
```
- `MemberRow` に `work_days: list[WorkDayRow] = field(default_factory=list)` を足す。`members_panel.to_rows` で、`WorkDayRow(w.day.isoformat(), w.start.strftime("%H:%M") if w.start else "", w.end.strftime("%H:%M") if w.end else "", w.start is None)` の一覧を渡す(`MemberRow(m.name, m.name, ..., m.id, m.icon, rows_of(m.work_days))`)。
- `build_members(rows, originals, assigned, parameters=None, taken=(), today: date | None = None)`: `Member(...)` を作る前に

```python
        try:
            work_days = build_work_day_list(row.work_days, today or date.today())
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from None
```
 `Member(name, round(ratio / 100, 4), levels, member_id, row.icon, work_days)`。
- 列: 定数 `MEMBER_WORK_DAYS_COLUMN_REM = 7` を`MEMBER_DELETE_COLUMN_REM`の近くに。`member_columns` は削除列の前に`f"{MEMBER_WORK_DAYS_COLUMN_REM}rem"`、`member_table_min_rem` は`+ MEMBER_WORK_DAYS_COLUMN_REM`と間隔の概算を`+1`。
- 表: ヘッダーに`ui.label("稼働日").classes(header).mark("member-header-workdays")`(削除列のヘッダー`ui.label("")`の前)。行に、削除ボタンの前で:

```python
                    ui.button(
                        f"稼働日({len(row.work_days)})" if row.work_days else "稼働日",
                        on_click=lambda r=row: open_work_days(r),
                    ).props("flat dense no-caps").mark(f"member-workday-open-{index}")
```
 `open_work_days(row)`:

```python
    def open_work_days(row: MemberRow) -> None:
        with ui.dialog() as sub, ui.card().classes("w-[40rem] max-w-full"):
            ui.label(f"{row.name or '(名前なし)'} の稼働日の上書き").classes("text-subtitle1")
            ui.label("日付ごとに、稼働の時間帯(開始〜終了)か休みを決めます。土日祝を稼働にしたり、平日を休みにできます").classes(
                "text-caption text-grey"
            )
            work_day_editor(row.work_days, "member-workday")
            ui.button("閉じる", on_click=sub.close).mark("member-workday-close")
        sub.on("hide", table.refresh)
        sub.open()
```
 `parameters_changed`・`apply` の流れは変えない(`rows != baseline`がネストしたリストも比べる)。`current = row.levels.get(...)` の既存の変数名との衝突に注意する(`open_work_days`は別スコープ)。

`views.py`:`apply_work_days` を削除し、`open_settings_dialog(...)` 呼び出しの`work_days=self.project.work_days, on_work_days=self.apply_work_days,` を削除する。`apply_members` の`members == self.project.members`の比較は、`Member.work_days`を含む dataclass の等価でそのまま働く。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uv run ty check src/projectapp | tail -1`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src test && git commit -m "feat: メンバーのダイアログで稼働日の上書きを編集できる

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: プロジェクト共通の`work_days`を削除する(PlantUML・マージ・保存・モデル)

**Files:**
- Modify: `src/projectapp/models.py`(`Project.work_days`を削除)
- Modify: `src/projectapp/storage.py`(トップレベルの`work_days`の書き出し・読込を削除)
- Modify: `src/projectapp/merge.py`(プロジェクト共通の`_work_days`・`project_work_day` collection を削除)
- Modify: `src/projectapp/plantuml.py`(休みの行を元に戻す)
- Modify: `src/projectapp/views.py`・`dashboard.py`・`gantt.py`(残った`project.work_days`の参照を削除)
- Test: `test/test_storage.py`、`test/test_merge.py`、`test/test_plantuml.py`、`test/test_workdays.py`

**Interfaces:**
- Consumes: Task 2〜5 で、`project.work_days`を使う箇所が残っていない状態。
- Produces: `Project.work_days`なし。`grep -rn "project.work_days\|Project(.*work_days" src test` が 0 件。

- [ ] **Step 1: 失敗するテストを書く(PlantUML)**

`test/test_plantuml.py`:`test_work_day_overrides_open_weekends_and_close_weekdays` を削除し、`rendered_svgs` のプロジェクトの`work_days=[...]`を `members=[Member("甲", work_days=[WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 14))])]` に直す。足す(`Member` を import):

```python
def test_member_work_days_do_not_change_the_closed_lines() -> None:
    project = Project("p", members=[Member("甲", work_days=[WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 14))])])
    out = lines(project, holidays={date(2026, 10, 13): "祝"})
    assert [line for line in out if "is closed" in line or "is open" in line] == ["2026-10-13 is closed"]
```
 `test_no_overrides_leave_the_closed_lines_unchanged` は残す。`test/test_storage.py`:トップレベル`work_days`のテスト(`test_work_days_round_trip_and_are_saved_in_date_order`、`test_files_without_work_days_load_as_empty`)を削除し、足す:

```python
def test_a_top_level_work_days_key_is_ignored() -> None:
    raw = json.loads(dumps_project(Project("p")))
    assert "work_days" not in raw
    raw["work_days"] = [{"day": "2026-10-17", "start": "13:00:00", "end": "16:00:00"}]
    assert not hasattr(parse_project(json.dumps(raw), "p"), "work_days")
```
 `test/test_merge.py`:プロジェクト共通の`work_days`のテスト(`test_work_days_merge_by_date`、`test_work_days_conflict_when_...`、`test_work_day_window_is_one_item_so_a_rest_choice_...`、`test_work_day_start_and_end_changed_on_different_sides_...`)を、Task 1 のメンバー版に置き換わっているか確かめて削除する。`test/test_workdays.py` の `assert Project("p").work_days == []` は`Member("m").work_days == []` に直す。

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_plantuml.py test/test_storage.py -q 2>&1 | tail -6`
Expected: FAIL(`Project.work_days` がまだある)

- [ ] **Step 3: 実装する**

- `models.py`:`Project.work_days` の行を削除。
- `storage.py`:`_dump` の`data["work_days"] = ...`の行を削除。`parse_project` の `work_days=_work_days(...) if ctx.version >= 8 else []` を削除(`_work_days`関数自体は`_members`が使うので残す)。`asdict(project)` が出す`work_days`キーは、`Project`に無くなるので出ない。
- `merge.py`:`_work_days(project)`・`work_days = merger.collection("work_day", ...)(プロジェクト共通の側)`・`Project(...)`の`work_days=sort_work_days(...)` を削除。`Conflict.kind` のコメントの`work_day`は残す。
- `plantuml.py`:Task 6 以前の休みの行へ戻す。

```python
    head += [
        f"{day.isoformat()} is closed"
        for day in sorted(holidays)
        if p_start <= day <= p_end and day.weekday() < 5
    ]
```
 (`work`・`closed`・`opened` の変数ブロックを置き換える。`date`の import が不要になれば整理する。)
- `grep -rn "project.work_days\|\.work_days" src/projectapp/views.py dashboard.py gantt.py timeline.py` で残りを確かめ、`work_day_map(self.project.work_days)` など、`Project`の参照を削除する(`views.py` の`work_day_map` import が不要なら外す)。

- [ ] **Step 4: 全体を確かめる**

Run: `grep -rn "project\.work_days\|Project(.*work_days" src test; uv run pytest -n auto -q 2>&1 | tail -3 && uv run ty check src/projectapp | tail -1`
Expected: grep は 0 件。テストはすべて PASS。`ty` は`All checks passed!`。

- [ ] **Step 5: コミット**

```bash
git add src test && git commit -m "refactor: プロジェクト共通の稼働日の上書きを削除する(メンバーごとに移行済み)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 仕様書・記録の更新と全体の確認

**Files:**
- Modify: `CLAUDE.md`、`docs/superpowers/specs/2026-10-22-work-days-design.md`(置き換えられた旨)、`docs/superpowers/specs/2026-10-23-member-work-days-design.md`(状態)、`docs/superpowers/README.md`、`docs/requests.md`、`docs/request-history.md`、`docs/development.md`、`.claude/MEMORY.md`

**Interfaces:** なし(文書のみ)。

- [ ] **Step 1: `CLAUDE.md` を直す**(置換前の語句が 1 回だけ出現することを確かめてから行う)

 - 設定ダイアログの箇条書きの`稼働日の上書き: 日付ごとに…`の文を、削除して、メンバーの箇条書きの末尾に次を足す: `メンバーには稼働日の上書きを持たせられる(\`メンバーとパラメータ\`のメンバーの表の\`稼働日\`ボタン)。日付ごとに、稼働の時間帯(開始〜終了。同じ日の 23:59 まで)か休みを 1 日ずつ登録でき、本来休みの日(土日祝)にその人だけ稼働したり、平日を休みにできる。上書きした日は、その人の枠を丸ごと置き換える(土日祝の判定より優先)。日付は昇順に並べ、重複は不可。`
 - 完了予定の算出(`工数（時間）は、基準の人が…`)の箇条書きの末尾に: `担当者が複数で稼働の枠が違う日は、全員の枠を時刻で重ね、その時刻に稼働している担当者の換算率の合計で工数を消化する(上書きがなければ、全員が同じ枠なので、工数 ÷ 換算率の合計と同じ)。担当者のいないタスクは、通常のカレンダー(月〜金・祝日を除く)で算出する。`
 - ガントチャートの土日祝の箇条書きの末尾の上書きの説明を、`日次では、担当者が稼働日を上書きした日を、そのタスクの行の下端に橙の印で示し、マウスオーバーに「田中: 稼働 13:00〜16:00」「鈴木: 休み」を出す(日付ヘッダーと土日祝の背景は変えない。週次・月次では出さない)。`に直す。
 - ダッシュボードの`人ごとの負荷`・`予定=…`の説明を、`その人の稼働日(上書きを反映)ごとに数える`/`予定=その人の稼働日ごとの稼働時間(上書きした日はその枠の長さ)×割り当て率の合計(担当なしは通常カレンダー)`に直す。全プロジェクトの負荷の列は、いずれかのメンバーが稼働する日の和集合で、そのメンバーが稼働しない日は 0 とする。
 - PlantUML の出力の箇条書き: 先に足した`(稼働日の上書きは、稼働にした土日を\`is open\`…)`の括弧を、`(メンバーごとの稼働日の上書きは出力しない)`に直す。
 - 「実装上の注意」の`version`(現在 8)の文に、`メンバーは稼働日の上書き(work_days)を持つ`を足す。`3 者マージ`の節の突き合わせの文に、`メンバーの稼働日の上書きは、メンバーの id と日付で突き合わせ、開始と終了を 1 項目として比べる`を足す。

- [ ] **Step 2: ほかの文書と記録を直す**

 - `2026-10-22-work-days-design.md` の先頭の状態を `置き換え済み(2026-10-23。[メンバーごとの設計](2026-10-23-member-work-days-design.md)へ)` に直す。`2026-10-23-member-work-days-design.md` の状態を `実装済み(2026-10-23。実機確認待ち)` に直す。
 - `docs/superpowers/README.md` の索引: 要望 30 の行の設計・計画に`2026-10-23-member-work-days`を足す(`稼働日の上書き(メンバーごと)`)。
 - `docs/requests.md`・`docs/request-history.md`: 要望 30 の記述を「メンバーごと」に直す。
 - `docs/development.md`: `Project.work_days`の記述(version 8 の項目)を`Member.work_days`・`timeline.Worker`・`crew_of`・`calc_end(crew)`に直し、`merge.py`の鍵の説明に`work_day`(メンバー id:日付)を足す。モジュール表の`timeline.py`の行に`Worker`・`crew_of`を足す。
 - `.claude/MEMORY.md`: 現在の状況・要望 30 の項目を「メンバーごとに作り直した」に直す。

- [ ] **Step 3: 全体を確かめる**

Run: `uv run pytest -n auto -q 2>&1 | tail -3 && uv run ty check src/projectapp | tail -1 && git status -sb | head -3`
Expected: すべて PASS、`All checks passed!`

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md docs .claude/MEMORY.md && git commit -m "docs: メンバーごとの稼働日の上書き(要望30)を仕様書と記録に反映する

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: 実機確認を頼む(ネイティブ)**

`git branch --show-current` が`feature/work-days`であることを確かめて、ユーザーに次の確認を頼む(`uv run projectapp`)。
1. `メンバーとパラメータ`のメンバーの表で、甲の`稼働日`から、土曜 13:00〜16:00 を足して適用 → 甲が担当のタスクだけ完了予定が変わる(乙のタスクは変わらない)。
2. 日次スケールで、甲が担当のタスクの行の下端の土曜に橙の印が付き、マウスオーバーに`甲: 稼働 13:00〜16:00`。日付ヘッダーと土日の背景は変わらない。週次・月次では出ない。
3. 甲と乙の共同タスクで、土曜に甲だけが働く分だけ消化される。
4. 休みにチェックで開始・終了が無効になる。重複・開始 ≥ 終了はエラー(メンバー名つき)。適用前に閉じると`●`が出る。
5. `Cmd+Z` で戻り、保存して開き直しても残る。メンバーを削除すると上書きも消える。
6. ダッシュボード:甲の負荷が土曜を稼働日に数える。予定工数が甲の土曜 3h ぶん増える。「全プロジェクト」の表に土曜の列が出て、乙は 0。
7. PlantUML に上書きは出ない(通常の休みのみ)。
8. ダークテーマで橙の印が見える。上書きのないプロジェクトの見た目・完了予定が変わらない。
