# 実績の時刻を省略できるオプション Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 実績を入れるとき、時刻を省いて日付だけで済ませられるオプション(`省略できる`。既定)を足し、省いた時刻を始業・稼働時間から補う(要望 144)。

**Architecture:** 補う規則は、NiceGUI に依存しない純粋関数`fill_actual_times`(`forms.py`)にして、設定を束ねた`ActualTimePolicy`経由で 3 つの入力口(簡易の入力欄・区間の行・Shift クリックの小さなダイアログ)が使う。オプションはプロジェクト設定`actual_time_optional`(ファイル`version` 23)で、先例の`plantuml_overload_notice`と同じ経路(モデル・保存・マージ・設定の書き出しと取り込み・切り出し・設定ダイアログ)に通す。

**Tech Stack:** Python 3.13、NiceGUI 4、pytest(`nicegui.testing.User`)

**Spec:** `docs/superpowers/specs/2026-11-16-actual-time-optional-design.md`

## Global Constraints

- 言語は日本語(UI の文言・コメント・docstring)。Python 3.13 以上。依存は増やさない。
- 補う開始は`日付 work_start`、補う終了は`日付 work_start + daily_hours`(CSV の取り込みと同じ規則)。補った終了が開始より前なら、開始に揃える。両方を明示した前後逆は、今までどおり`build_actuals`がエラーにする。
- `必須`のときは、今の動作のまま(日付と時刻の両方が要る。片方だけは`日付と時刻を両方入れてください`)。
- 保存するのは、補ったあとの`datetime`。`Actual`の形・集計は変えない。
- ファイルの`version`を 22 → 23 に上げる。キーのない古いファイル(version 22 以前)は`True`(`省略できる`)で読む。真偽値でない値は拒否する。新しい`version`は、これまでどおり拒否する。
- 設定は、`plantuml_overload_notice`と同じ経路に通す: モデル・`storage.py`・`merge.py`・`settings_io.py`・`extract.py`・`open_settings_dialog`・`views.py`。
- `refreshable`の中でダイアログを作らない。開くたびに作るダイアログは`disposable(...)`で包む。
- 実装の完了時の確認の順: `uv run pytest -m smoke` → `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`(既存の 9 件以外が増えないこと)。smoke が失敗したときに限り`uv run pytest -n auto`。
- マージは利用者の指示を待つ(PR を作って止まる)。コミットの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける。

## Review Focus

- 日付だけの終了が、開始の明示した時刻より前になる(開始 18:00・終了は日付だけ・同じ日): 終了を開始に揃え、エラーにしない(Task 1)。
- `work_start + daily_hours`が翌日にかかる(始業 22:00・8 時間): 終了が翌日の日時になる。案内は`翌 06:00`の形(Task 1・3)。
- 時刻だけで日付がない: `省略できる`でも、エラー(`日付を入れてください`)(Task 1・3)。
- 開始の日付だけを入れて、終了は両方空: 開始だけを補い、終了は空のまま(実行中の区間)(Task 1)。
- 区間の行のエラーに、今までどおり`区間 N:`が付く(Task 3)。
- 日付の形式が不正(`2026-13-45`など): 補う前に落ちず、`build_actuals`の`実績の日時の形式が正しくありません`になる(Task 1)。
- キーのない古いファイル・`null`・文字列`"yes"`: 前者は`True`、後者 2 つは新しい形式では拒否(Task 2)。
- 状態の自動提案: 日付だけでも、`省略できる`のとき働く。`必須`では働かない(Task 3)。

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `src/projectapp/forms.py`(変更) | `fill_actual_times`・`ActualTimePolicy`・設定ダイアログの`実績の時刻`トグル |
| `src/projectapp/task_dialog.py`(変更) | `ActualFields`・`IntervalFields`・`open_quick_progress_dialog`・`open_task_dialog`に`policy`を通す。空の時刻欄の案内 |
| `src/projectapp/models.py`(変更) | `Project.actual_time_optional`・`FORMAT_VERSION` 23 |
| `src/projectapp/storage.py`・`merge.py`・`settings_io.py`・`extract.py`(変更) | 保存・マージ・設定の書き出しと取り込み・切り出し |
| `src/projectapp/views.py`(変更) | `actual_policy()`・`apply_actual_time_optional`・呼び出しに`policy`を渡す |
| `test/test_actual_time.py`(新規) | Task 1・2 のテスト |
| `test/test_task_dialog.py`(変更) | Task 3 のテスト、既存の「両方入れてください」の 3 件を`必須`の指定に |
| `test/test_forms.py`・`test/test_views.py`(変更) | Task 4 のテスト |
| `CLAUDE.md`・`docs/development.md`・`.claude/spec/gantt.md`・`docs/requests.md`(変更) | Task 5 |

---

### Task 1: 補う規則(`fill_actual_times`・`ActualTimePolicy`)

**Files:**
- Modify: `src/projectapp/forms.py`(`compose_actual`の近く、1333 行付近)
- Test: `test/test_actual_time.py`(新規)

**Interfaces:**
- Consumes: `compose_datetime`・`DEFAULT_WORK_START`・`DEFAULT_DAILY_HOURS`(`projectapp.models`)
- Produces:
  - `fill_actual_times(start_day: str, start_clock: str, end_day: str, end_clock: str, *, optional: bool, work_start: time, daily_hours: float) -> tuple[str, str]`: `build_actuals(start_text, end_text)`に渡す文字列の組。エラーは`ValueError`。
  - `@dataclass(frozen=True) class ActualTimePolicy`: `optional: bool = True`・`work_start: time = DEFAULT_WORK_START`・`daily_hours: float = DEFAULT_DAILY_HOURS`。メソッド`fill(start_day, start_clock, end_day, end_clock) -> tuple[str, str]`・`start_hint() -> str`・`end_hint() -> str`(`optional`が偽なら`""`)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_actual_time.py`:

```python
from datetime import time

import pytest

from projectapp.forms import ActualTimePolicy, build_actuals, fill_actual_times

START = time(9, 0)


def fill(sd="", sc="", ed="", ec="", *, optional=True, work_start=START, hours=6.5):
    return fill_actual_times(
        sd, sc, ed, ec, optional=optional, work_start=work_start, daily_hours=hours
    )


def test_both_empty_means_no_actual() -> None:
    assert fill() == ("", "")


def test_a_date_and_a_time_are_kept_as_typed() -> None:
    assert fill("2026-10-05", "09:15", "2026-10-05", "17:45") == (
        "2026-10-05T09:15",
        "2026-10-05T17:45",
    )


def test_a_date_only_start_gets_the_start_of_the_day() -> None:
    assert fill("2026-10-05") == ("2026-10-05T09:00", "")


def test_a_date_only_end_gets_the_start_of_the_day_plus_the_daily_hours() -> None:
    assert fill("2026-10-05", "", "2026-10-06") == (
        "2026-10-05T09:00",
        "2026-10-06T15:30",
    )


def test_the_date_is_normalized_like_the_typed_one() -> None:
    assert fill("2026-10-5", "", "2026-10-6")[0] == "2026-10-05T09:00"


def test_an_end_that_crosses_midnight_moves_to_the_next_day() -> None:
    assert fill("2026-10-05", "", "2026-10-05", work_start=time(22, 0), hours=8.0) == (
        "2026-10-05T22:00",
        "2026-10-06T06:00",
    )


def test_a_filled_end_before_an_explicit_start_is_raised_to_the_start() -> None:
    # 開始 18:00 を明示、終了は日付だけ(補うと 15:30)→ 開始に揃える
    assert fill("2026-10-05", "18:00", "2026-10-05") == (
        "2026-10-05T18:00",
        "2026-10-05T18:00",
    )


def test_an_explicit_end_before_the_start_is_left_for_build_actuals_to_refuse() -> None:
    start, end = fill("2026-10-05", "18:00", "2026-10-05", "17:00")
    assert (start, end) == ("2026-10-05T18:00", "2026-10-05T17:00")
    with pytest.raises(ValueError):
        build_actuals(start, end)


def test_a_time_without_a_date_is_an_error_even_when_optional() -> None:
    with pytest.raises(ValueError, match="日付を入れてください"):
        fill("", "09:00")
    with pytest.raises(ValueError, match="日付を入れてください"):
        fill("2026-10-05", "", "", "17:00")


def test_required_keeps_the_old_rule() -> None:
    assert fill("2026-10-05", "09:00", optional=False) == ("2026-10-05T09:00", "")
    for args in (("2026-10-05",), ("", "09:00"), ("2026-10-05", "09:00", "2026-10-06")):
        with pytest.raises(ValueError, match="日付と時刻を両方入れてください"):
            fill(*args, optional=False)


def test_a_bad_date_is_reported_by_build_actuals_not_by_the_filler() -> None:
    start, end = fill("2026-13-45")
    with pytest.raises(ValueError, match="形式"):
        build_actuals(start, end)


def test_a_bad_time_is_reported() -> None:
    with pytest.raises(ValueError, match="時刻の形式"):
        fill("2026-10-05", "9時")


def test_the_policy_delegates_and_makes_hints() -> None:
    policy = ActualTimePolicy(True, time(9, 0), 6.5)
    assert policy.fill("2026-10-05") == ("2026-10-05T09:00", "")
    assert policy.start_hint() == "省略: 始業 09:00"
    assert policy.end_hint() == "省略: 終業 15:30"


def test_the_end_hint_names_the_next_day_when_it_crosses_midnight() -> None:
    assert ActualTimePolicy(True, time(22, 0), 8.0).end_hint() == "省略: 終業 翌 06:00"


def test_a_required_policy_has_no_hints() -> None:
    policy = ActualTimePolicy(False)
    assert policy.start_hint() == "" and policy.end_hint() == ""
    with pytest.raises(ValueError):
        policy.fill("2026-10-05")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_actual_time.py -q`
Expected: FAIL(`ImportError: cannot import name 'ActualTimePolicy'`)

- [ ] **Step 3: 実装する**

`src/projectapp/forms.py`の先頭の import に、`from datetime import date, datetime, time`を`from datetime import date, datetime, time, timedelta`に直し(`timedelta`がなければ)、`from projectapp.models import`の並びに`DEFAULT_DAILY_HOURS`・`DEFAULT_WORK_START`がなければ足す(`grep -n "DEFAULT_" src/projectapp/forms.py`で確かめる)。`compose_actual`の次に足す:

```python
ACTUAL_BOTH_MESSAGE = "日付と時刻を両方入れてください"


def _fill_one(day: str, clock: str, optional: bool) -> tuple[str, bool]:
    """1 つの時点の入力から、文字列を作る。戻りの bool は、時刻を補う必要があるか(日付だけ)。"""
    if not day and not clock:
        return "", False
    if clock and not day:
        raise ValueError("日付を入れてください" if optional else ACTUAL_BOTH_MESSAGE)
    if day and clock:
        return compose_datetime(day, clock), False
    if not optional:
        raise ValueError(ACTUAL_BOTH_MESSAGE)
    return day, True


def fill_actual_times(
    start_day: str,
    start_clock: str,
    end_day: str,
    end_clock: str,
    *,
    optional: bool,
    work_start: time,
    daily_hours: float,
) -> tuple[str, str]:
    """実績の開始・終了の入力から、`build_actuals`に渡す文字列の組を作る(純粋関数)。
    `optional`が真のとき、日付だけの開始は`日付 work_start`、終了は`日付 work_start + daily_hours`を補う
    (CSV の取り込みと同じ規則)。補った終了が開始より前なら、開始に揃える。両方を明示した前後逆は、ここでは直さない
    (`build_actuals`がエラーにする)。時刻だけで日付がないときはエラー。`optional`が偽なら、日付と時刻の両方が要る。"""
    start, start_fill = _fill_one(start_day.strip(), start_clock.strip(), optional)
    end, end_fill = _fill_one(end_day.strip(), end_clock.strip(), optional)
    if start_fill:
        start = _day_at(start, work_start, 0.0)
    if end_fill:
        end = _day_at(end, work_start, daily_hours)
        if start:
            try:
                if datetime.fromisoformat(end) < datetime.fromisoformat(start):
                    end = start  # 補った終了が、開始より前になったとき
            except ValueError:
                pass  # 開始の形式の誤りは、build_actuals が報告する
    return start, end


def _day_at(day: str, work_start: time, hours: float) -> str:
    """`日付`の`work_start`から`hours`時間あとの日時を、`YYYY-MM-DDTHH:MM`で返す。日付が読めなければ、そのまま返す
    (形式の誤りは、build_actuals が報告する)。"""
    try:
        base = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return day
    moment = datetime.combine(base.date(), work_start) + timedelta(hours=hours)
    return moment.strftime("%Y-%m-%dT%H:%M")


@dataclass(frozen=True)
class ActualTimePolicy:
    """実績の時刻の扱い(プロジェクトの設定を束ねたもの)。入力口の 3 か所が受け取る。"""

    optional: bool = True
    work_start: time = DEFAULT_WORK_START
    daily_hours: float = DEFAULT_DAILY_HOURS

    def fill(
        self, start_day: str, start_clock: str, end_day: str, end_clock: str
    ) -> tuple[str, str]:
        return fill_actual_times(
            start_day,
            start_clock,
            end_day,
            end_clock,
            optional=self.optional,
            work_start=self.work_start,
            daily_hours=self.daily_hours,
        )

    def start_hint(self) -> str:
        return f"省略: 始業 {self.work_start:%H:%M}" if self.optional else ""

    def end_hint(self) -> str:
        if not self.optional:
            return ""
        origin = datetime.combine(date(2000, 1, 1), self.work_start)
        end = origin + timedelta(hours=self.daily_hours)
        next_day = "翌 " if end.date() != origin.date() else ""
        return f"省略: 終業 {next_day}{end:%H:%M}"
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_actual_time.py -q`
Expected: PASS(`_fill_one`が日付を正規化しない点: `test_the_date_is_normalized_like_the_typed_one`が落ちたら、日付だけのときも`compose_datetime`と同じ正規化を`_fill_one`に足す。`datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d")`を、`try`で包んで使う)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py test/test_actual_time.py
git commit -m "feat: 実績の時刻を省いたときに、始業・終業を補う規則を作る(要望 144)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 設定とファイル形式(`actual_time_optional`・version 23)

**Files:**
- Modify: `src/projectapp/models.py`(`plantuml_overload_notice`の次〔442 行付近〕と`FORMAT_VERSION`〔13 行〕)
- Modify: `src/projectapp/storage.py`(`_plantuml_overload_notice`の次〔837 行付近〕と読み込み〔1444 行付近〕)
- Modify: `src/projectapp/merge.py`(`SETTING_LABELS`〔236 行〕と`Project(...)`の組み立て〔762 行付近〕)
- Modify: `src/projectapp/settings_io.py`(`PROJECT_KEYS`〔30 行〕・要約〔173 行付近〕・取り込み〔274 行付近〕)
- Modify: `src/projectapp/extract.py`(149 行付近)
- Test: `test/test_actual_time.py`(足す)、バージョン番号に依存する既存テスト

**Interfaces:**
- Consumes: なし
- Produces: `Project.actual_time_optional: bool = True`、`FORMAT_VERSION == 23`、`settings_io`の日本語キー`実績の時刻の省略`(`省略できる`・`必須`)

- [ ] **Step 1: 失敗するテストを書く**

`test/test_actual_time.py`に足す:

```python
import json

from projectapp.merge import SETTING_LABELS
from projectapp.models import FORMAT_VERSION, Project
from projectapp.storage import dumps_project, parse_project


def test_the_option_defaults_to_optional_and_the_version_is_23() -> None:
    assert Project("p").actual_time_optional is True
    assert FORMAT_VERSION == 23


def test_the_option_is_saved_and_read_back() -> None:
    for value in (True, False):
        project = Project("p", actual_time_optional=value)
        text = dumps_project(project)
        assert json.loads(text)["actual_time_optional"] is value
        assert parse_project(text, "p").actual_time_optional is value


def test_a_file_without_the_key_reads_as_optional() -> None:
    raw = json.loads(dumps_project(Project("p", actual_time_optional=False)))
    del raw["actual_time_optional"]
    raw["version"] = 22
    assert parse_project(json.dumps(raw), "p").actual_time_optional is True


@pytest.mark.parametrize("bad", [None, "yes", 1])
def test_a_non_boolean_value_is_refused(bad) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["actual_time_optional"] = bad
    with pytest.raises(ValueError, match="実績の時刻の省略"):
        parse_project(json.dumps(raw), "p")


def test_a_newer_version_is_still_refused() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = FORMAT_VERSION + 1
    with pytest.raises(ValueError):
        parse_project(json.dumps(raw), "p")


def test_the_option_is_one_of_the_three_way_merge_settings() -> None:
    assert SETTING_LABELS["actual_time_optional"] == "実績の時刻の省略"
```

(`parse_project`の第 2 引数と`dumps_project`は、`storage.py`にある。第 2 引数がプロジェクト名であることを、`def parse_project`で確かめる)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_actual_time.py -q`
Expected: FAIL(`TypeError: ... unexpected keyword argument 'actual_time_optional'`)

- [ ] **Step 3: 実装する**

`models.py`:
- `Project`の`plantuml_overload_notice`の定義の次に足す:

```python
    actual_time_optional: bool = (
        True  # 実績の時刻を省略できるか(省くと始業・終業を補う。False は日付と時刻の両方が要る)
    )
```

- `FORMAT_VERSION = 22`を`23`にし、同じ行のコメントの`22: 日ごとの担当 daily_crew`を`22: 日ごとの担当 daily_crew、23: 実績の時刻の省略 actual_time_optional`に直す。

`storage.py`: `_plantuml_overload_notice`の次に足す:

```python
def _actual_time_optional(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"実績の時刻の省略の設定が正しくありません: {value!r}")
    return value
```

読み込みの`plantuml_overload_notice=(...)`の次に足す:

```python
        actual_time_optional=(
            _actual_time_optional(raw.get("actual_time_optional", True))
            if ctx.version >= 23
            else True
        ),
```

`merge.py`: `SETTING_LABELS`の`"plantuml_overload_notice": ...`の次に`"actual_time_optional": "実績の時刻の省略",`を足し、`Project(...)`の組み立ての`plantuml_overload_notice=settings["plantuml_overload_notice"],`の次に`actual_time_optional=settings["actual_time_optional"],`を足す。

`settings_io.py`:
- `PROJECT_KEYS`の`"plantuml_overload_notice",`の次に`"actual_time_optional",`を足す。
- 要約の辞書(`"PlantUML の通知": ...`の次)に`"実績の時刻の省略": "省略できる" if project.actual_time_optional else "必須",`を足す。
- 取り込みの`work.plantuml_overload_notice = source.plantuml_overload_notice`の次に`work.actual_time_optional = source.actual_time_optional`を足す。

`extract.py`: `plantuml_overload_notice=project.plantuml_overload_notice,`の次に`actual_time_optional=project.actual_time_optional,`を足す。

- [ ] **Step 4: 通ることを確かめ、バージョン番号に依存する既存テストを直す**

Run: `uv run pytest test/test_actual_time.py -q` → PASS

Run: `uv run pytest test/test_storage.py test/test_merge.py test/test_settings_io.py test/test_extract.py test/test_models.py -q 2>&1 | tail -15`
Expected: 失敗があれば、理由がバージョン番号(22 → 23)か、設定の一覧に新しいキーが増えたことだけであることを確かめ、そのテストの期待値を直す(キーの一覧・設定の要約・`FORMAT_VERSION`の直書き)。ほかの理由で落ちるものは、実装を見直す。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp test
git commit -m "feat: 実績の時刻を省略できる設定を、プロジェクトに持たせる(version 23。要望 144)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 入力口(簡易・区間・小さなダイアログ)と views の接続

**Files:**
- Modify: `src/projectapp/task_dialog.py`(`moment_column`:290、`_parses`:557、`ActualFields`:567、`IntervalFields`:635、`open_quick_progress_dialog`:1104、`open_task_dialog`:1285、実績欄の生成:1690)
- Modify: `src/projectapp/views.py`(`add_task`・`add_top_task`・`edit_task`〔2750〜2790 行付近〕、`open_quick_progress_dialog`の呼び出し〔3127 行付近〕)
- Test: `test/test_task_dialog.py`

**Interfaces:**
- Consumes: `ActualTimePolicy`(Task 1)、`Project.actual_time_optional`(Task 2)
- Produces:
  - `moment_column(label, mark, picker, moment, time_hint: str = "")`(空の時刻欄の案内。`placeholder`)
  - `ActualFields(task, policy: ActualTimePolicy = ActualTimePolicy())`・`IntervalFields(task, policy: ActualTimePolicy = ActualTimePolicy())`
  - `open_quick_progress_dialog(task, intervals, on_save, policy: ActualTimePolicy = ActualTimePolicy())`
  - `open_task_dialog(..., actual_time_optional: bool = True)`(内部で、`work_start`・`daily_hours`と合わせて`ActualTimePolicy`にする)
  - `MainView.actual_policy() -> ActualTimePolicy`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_task_dialog.py`の`mount_dialog`の引数に、`teams: list[Team] | None = None,`の次として`actual_time_optional: bool = True,`を足し、`open_task_dialog(...)`の呼び出しに`actual_time_optional=actual_time_optional,`を足す。`mount_quick_dialog`は、`policy: ActualTimePolicy = ActualTimePolicy()`を足し、`open_quick_progress_dialog(task, intervals, saved.append, policy)`にする(`from projectapp.forms import ActualTimePolicy`を import に足す)。

既存の 3 件(`日付と時刻を両方入れてください`を確かめるもの。1134・1467・2641 行付近)は、`mount_dialog(...)`の呼び出しに`actual_time_optional=False`を足す。

次のテストを足す:

```python
async def test_a_date_without_a_time_gets_the_start_and_end_of_the_day(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)  # 始業 9:00・稼働 6.5 時間
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-actual-start-date").type("2026-10-05")
    user.find(marker="task-actual-end-date").type("2026-10-06")
    user.find(marker="task-save").click()
    assert saved[0].actuals == [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 6, 15, 30))
    ]


async def test_a_time_without_a_date_is_still_an_error_when_optional(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-actual-start-time").type("09:00")
    user.find(marker="task-save").click()
    assert saved == []
    await user.should_see("日付を入れてください")


async def test_the_empty_time_inputs_show_what_will_be_filled_in(user: User) -> None:
    mount_dialog(None, [], work_start=time(8, 30), daily_hours=8.0)
    await open_dialog(user)
    start = user.find(marker="task-actual-start-time").elements.pop()
    end = user.find(marker="task-actual-end-time").elements.pop()
    assert "省略: 始業 08:30" in str(start._props.get("placeholder"))
    assert "省略: 終業 16:30" in str(end._props.get("placeholder"))


async def test_required_shows_no_hint(user: User) -> None:
    mount_dialog(None, [], actual_time_optional=False)
    await open_dialog(user)
    start = user.find(marker="task-actual-start-time").elements.pop()
    assert not start._props.get("placeholder")


async def test_a_half_typed_interval_row_is_filled_and_names_its_number_on_error(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_dialog(None, saved, actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    user.find(marker="task-interval-0-start-date").type("2026-10-05")
    user.find(marker="task-interval-0-end-date").type("2026-10-05")
    user.find(marker="task-save").click()
    assert saved[0].actuals == [
        Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 15, 30))
    ]


async def test_an_interval_row_with_only_a_time_names_its_number(user: User) -> None:
    mount_dialog(None, [], actual_mode=INTERVALS)
    await open_dialog(user)
    user.find(marker="task-name").type("設計")
    user.find(marker="task-interval-add").click()
    user.find(marker="task-interval-0-start-time").type("09:00")
    user.find(marker="task-save").click()
    await user.should_see("区間 1: 日付を入れてください")


async def test_the_status_is_suggested_from_a_date_only_actual_when_optional(
    user: User,
) -> None:
    mount_dialog(None, [])
    await open_dialog(user)
    user.find(marker="task-actual-start-date").type("2026-10-05")
    await user.should_see("実績に合わせて状態を変えました")


async def test_the_quick_dialog_fills_a_date_only_actual(user: User) -> None:
    saved: list[Task] = []
    mount_quick_dialog(Task("作業"), saved)
    await open_dialog(user)
    with user.client:
        user.find(marker="task-actual-start-date").elements.pop().set_value("2026-10-05")
    user.find(marker="quick-save").click()
    assert saved[0].actuals == [Actual(datetime(2026, 10, 5, 9))]


async def test_the_quick_dialog_refuses_a_date_only_actual_when_required(
    user: User,
) -> None:
    saved: list[Task] = []
    mount_quick_dialog(Task("作業"), saved, policy=ActualTimePolicy(False))
    await open_dialog(user)
    with user.client:
        user.find(marker="task-actual-start-date").elements.pop().set_value("2026-10-05")
    user.find(marker="quick-save").click()
    assert saved == []
    assert "両方" in user.find(marker="quick-error").elements.pop().text
```

(`time`・`INTERVALS`・`open_dialog`・`mount_dialog`は同じファイルにある。`time`が import されていなければ足す)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_task_dialog.py -q -k "date_without_a_time or time_without_a_date or empty_time_inputs or required_shows or half_typed or only_a_time or date_only or quick" 2>&1 | tail -12`
Expected: FAIL(`mount_dialog`に新しい引数を足したため、`TypeError: ... actual_time_optional`ではなく、`open_task_dialog`が受け付けない旨の`TypeError`)

- [ ] **Step 3: `task_dialog.py`を実装する**

1. import に`ActualTimePolicy`を足す(`from projectapp.forms import (...)`の並び。`compose_actual`の import は、使わなくなるので外す)。
2. `moment_column`に引数`time_hint: str = ""`を足し、時刻の入力の生成の直後に足す:

```python
        if time_hint:
            clock.props(f'placeholder="{time_hint}"')
```

3. `_parses`の次に足す:

```python
def _moment_ready(day: str | None, clock: str | None, optional: bool) -> bool:
    """日付と時刻が、状態の提案に使える形か。`optional`のとき、時刻が空でも、日付が完成していれば使える。"""
    if optional and not (clock or "").strip():
        try:
            datetime.strptime((day or "").strip(), "%Y-%m-%d")
        except ValueError:
            return False
        return True
    return _parses(day, clock)
```

4. `ActualFields`: `__init__(self, task: Task, policy: ActualTimePolicy = ActualTimePolicy())`にして`self.policy = policy`を保存する(`read_only`で`return`する分岐より前に)。`_column`を次にする:

```python
    def _column(
        self, label: str, key: str, moment: datetime | None
    ) -> tuple[ui.input, ui.input]:
        hint = self.policy.end_hint() if key == "end" else self.policy.start_hint()
        return moment_column(label, f"task-actual-{key}", f"actual-{key}", moment, hint)
```

   `start_text`・`end_text`を、次の`texts`に寄せる:

```python
    def texts(self) -> tuple[str, str]:
        """`build_actuals`に渡す開始・終了の文字列(補った時刻を含む)。入力に誤りがあれば ValueError。"""
        if self.read_only:
            return "", ""
        return self.policy.fill(
            self.start_day.value or "",
            self.start_time.value or "",
            self.end_day.value or "",
            self.end_time.value or "",
        )

    def start_text(self) -> str:
        return self.texts()[0]

    def end_text(self) -> str:
        return self.texts()[1]
```

   `filled`の`_parses(...)`2 つを、`_moment_ready(self.start_day.value, self.start_time.value, self.policy.optional)`と`_moment_ready(self.end_day.value, self.end_time.value, self.policy.optional)`にする。クラスの docstring の`(補う時刻はない)`を`(時刻の省略は policy による)`に直す。

5. `IntervalFields`: `__init__(self, task: Task, policy: ActualTimePolicy = ActualTimePolicy())`にして、`self.policy = policy`を、`self._rows`の定義の前に保存する。`_add_row`の 2 つの`moment_column(...)`に、末尾の引数として`self.policy.start_hint()`・`self.policy.end_hint()`を足す。`rows()`の`try`の中を、次にする:

```python
                start, end = self.policy.fill(
                    row.start_day.value or "",
                    row.start_time.value or "",
                    row.end_day.value or "",
                    row.end_time.value or "",
                )
```

   `filled`の`_parses(...)`2 つも、`_moment_ready(..., self.policy.optional)`にする。

6. `open_quick_progress_dialog(task, intervals, on_save, policy: ActualTimePolicy = ActualTimePolicy())`にして、`ActualFields(task)`を`ActualFields(task, policy)`にする。保存の`apply_quick_progress(task, progress.value, fields.start_text(), fields.end_text(), intervals=intervals)`を、`start, end = fields.texts()`を先に呼んでから渡す形にする(`ValueError`は既存の`except`で`error`に出る。`texts()`も`try`の中で呼ぶ)。

7. `open_task_dialog`: 引数`actual_time_optional: bool = True,`を`actual_mode`の次に足し、実績欄の生成の手前(1690 行付近)で`policy = ActualTimePolicy(actual_time_optional, work_start, daily_hours)`を作り、`IntervalFields(initial, policy) if intervals else ActualFields(initial, policy)`にする。

- [ ] **Step 4: `views.py`を接続する**

`MainView`の`add_task`の近くにメソッドを足す(import に`from projectapp.forms import ActualTimePolicy`を足す):

```python
    def actual_policy(self) -> ActualTimePolicy:
        """実績の時刻の扱い(プロジェクトの設定)。"""
        return ActualTimePolicy(
            self.project.actual_time_optional,
            self.project.work_start,
            self.project.daily_hours,
        )
```

`add_task`・`add_top_task`・`edit_task`の`open_task_dialog(...)`の`actual_mode=self.project.actual_mode,`の次に`actual_time_optional=self.project.actual_time_optional,`を足す。`open_quick_progress_dialog(task, self.project.actual_mode is ActualMode.INTERVALS, apply)`を、末尾に`self.actual_policy()`を足した呼び出しにする。

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest test/test_task_dialog.py test/test_actual_time.py -q 2>&1 | tail -6`
Expected: PASS

Run: `uv run pytest test/test_views.py test/test_gantt.py -q -x 2>&1 | tail -4`
Expected: PASS(`actual_policy`と引数の追加だけなので、既存の呼び出しは変わらない。落ちたら、モックの`open_task_dialog`の引数が合っているか確かめる)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/task_dialog.py src/projectapp/views.py test/test_task_dialog.py
git commit -m "feat: 実績の入力口で、時刻を省いて日付だけで確定できるようにする(要望 144)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 設定ダイアログのトグル

**Files:**
- Modify: `src/projectapp/forms.py`(`open_settings_dialog`:1749〔引数〕、トグルの生成:1833 付近、`commit`:2236 付近)
- Modify: `src/projectapp/views.py`(`open_settings`:1389 付近、`apply_plantuml_notice`:2432 付近)
- Test: `test/test_forms.py`・`test/test_views.py`

**Interfaces:**
- Consumes: `Project.actual_time_optional`(Task 2)
- Produces: `open_settings_dialog(..., actual_time_optional: bool = True, on_actual_time_optional: Callable[[bool], object] | None = None)`、マーカー`settings-actual-time-optional`、`MainView.apply_actual_time_optional(enabled: bool)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_forms.py`の、`test_the_settings_dialog_does_not_report_an_unchanged_plantuml_notice`(2780 行付近)の次に足す(`open_settings_dialog`・`time`・`ui`・`User`は同じファイルで import 済み):

```python
async def test_the_settings_dialog_reports_a_changed_actual_time_option(
    user: User,
) -> None:
    applied: list[bool] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda *a: None,
                actual_time_optional=True,
                on_actual_time_optional=applied.append,
            ),
        )

    await user.open("/")
    user.find("open").click()
    toggle = user.find(marker="settings-actual-time-optional").elements.pop()
    assert toggle.value == "optional"
    toggle.set_value("required")
    user.find(marker="settings-apply").click()
    assert applied == [False]


async def test_the_settings_dialog_does_not_report_an_unchanged_actual_time_option(
    user: User,
) -> None:
    applied: list[bool] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda *a: None,
                actual_time_optional=False,
                on_actual_time_optional=applied.append,
            ),
        )

    await user.open("/")
    user.find("open").click()
    toggle = user.find(marker="settings-actual-time-optional").elements.pop()
    assert toggle.value == "required"
    user.find(marker="settings-apply").click()
    assert applied == []
```

`test/test_views.py`の末尾に足す:

```python
async def test_the_settings_apply_changes_the_actual_time_option(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    assert view.project.actual_time_optional is True
    view.apply_actual_time_optional(False)
    assert view.project.actual_time_optional is False
    assert view.is_dirty()
    view.apply_actual_time_optional(False)  # 同じ値では、何も変えない


async def test_the_task_dialog_gets_the_projects_actual_time_policy(
    user: User, tmp_path: Path
) -> None:
    view = await open_members_view(user, tmp_path)
    view.project.actual_time_optional = False
    view.project.daily_hours = 7.0
    policy = view.actual_policy()
    assert (policy.optional, policy.daily_hours) == (False, 7.0)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -k "actual_time" 2>&1 | tail -6`
Expected: FAIL(`TypeError`または`AttributeError: apply_actual_time_optional`)

- [ ] **Step 3: 実装する**

`forms.py`の`open_settings_dialog`:
- 引数に、`on_plantuml_notice`の次として`actual_time_optional: bool = True,`・`on_actual_time_optional: Callable[[bool], object] | None = None,`を足す。
- `実績の記録方式`のトグルと、区間から簡易へ戻せない注記(`mode.on_value_change(keep_intervals)`まで)の直後に足す:

```python
        time_option = None
        if on_actual_time_optional is not None:
            ui.label("実績の時刻").classes("text-caption text-grey")
            time_option = ui.toggle(
                {"optional": "省略できる", "required": "必須"},
                value="optional" if actual_time_optional else "required",
            ).mark("settings-actual-time-optional")
            ui.label(
                "省略できるとき、日付だけの実績には、始業・終業(稼働可能時間)の時刻を補います"
            ).classes("text-caption text-grey")
```

- `commit`の`on_plantuml_notice(...)`の`if`の次に足す:

```python
            if (
                time_option is not None
                and on_actual_time_optional is not None
                and (time_option.value == "optional") is not actual_time_optional
            ):
                on_actual_time_optional(time_option.value == "optional")
```

`views.py`の`open_settings`の`on_plantuml_notice=self.apply_plantuml_notice,`の次に足す:

```python
            actual_time_optional=self.project.actual_time_optional,
            on_actual_time_optional=self.apply_actual_time_optional,
```

`apply_plantuml_notice`の次にメソッドを足す:

```python
    def apply_actual_time_optional(self, enabled: bool) -> None:
        """実績の時刻を省略できるかを変える。保存済みの実績は変えない。保存はしない。"""
        if enabled is self.project.actual_time_optional:
            return
        self.project.actual_time_optional = enabled
        self.after_edit()
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_forms.py test/test_views.py -q -k "settings or actual_time" 2>&1 | tail -4`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test/test_forms.py test/test_views.py
git commit -m "feat: 設定ダイアログに、実績の時刻を省略できるかの切り替えを足す(要望 144)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 設定の書き出し・取り込み・切り出しの確認、文書、最終確認

**Files:**
- Modify: `.claude/spec/gantt.md`(実績の記録方式の項:49 行付近、設定ダイアログの項:54 行付近、切り出しで引き継ぐ設定:20 行付近)
- Modify: `CLAUDE.md`(`version`(現在 22))・`docs/development.md`(形式のバージョン:140 行付近)
- Modify: `docs/requests.md`(要望 144 の状態)
- Test: `test/test_settings_io.py`・`test/test_extract.py`

- [ ] **Step 1: 設定の書き出し・取り込み・切り出しのテストを足す**

`test/test_settings_io.py`の末尾に足す(`from projectapp.settings_io import _describe`を、同じファイルの import の並びに足す。`build_settings`・`apply_import`・`incoming_of`・`Project`は同じファイルにある):

```python
def test_the_actual_time_option_goes_through_the_settings_file_and_the_import() -> None:
    source = Project("入", actual_time_optional=False)
    assert build_settings(source)["actual_time_optional"] is False
    result = apply_import(Project("現"), incoming_of(source), {"project"}, set())
    assert result.project.actual_time_optional is False


def test_the_settings_summary_names_the_actual_time_option() -> None:
    assert _describe(Project("p"))["実績の時刻の省略"] == "省略できる"
    assert _describe(Project("p", actual_time_optional=False))["実績の時刻の省略"] == "必須"
```

`test/test_extract.py`の`test_settings_and_events_are_carried_but_not_teams`の次に足す:

```python
def test_the_actual_time_option_is_carried_to_the_child() -> None:
    project = make()
    project.actual_time_optional = False
    assert extract(project, ["a"], "子").child.actual_time_optional is False
```

Run: `uv run pytest test/test_settings_io.py test/test_extract.py -q` → PASS(Task 2 で実装済みなので、足したテストは通る。落ちたら、Task 2 の該当箇所を直す)

- [ ] **Step 2: 文書を直す**

- `.claude/spec/gantt.md`: 49 行目の`実績の記録方式`の項の次に、新しい項を足す:

```markdown
- 実績の時刻(要望 144): 設定ダイアログの`実績の時刻`で、プロジェクトごとに`省略できる`(既定)・`必須`を選ぶ。`省略できる`のとき、実績の開始・終了は、日付だけを入れて確定できる(簡易の入力欄・区間の行・棒の Shift クリックの小さなダイアログのすべて)。日付だけの開始は、その日の始業時刻、終了は、その日の始業時刻に稼働可能時間を足した時刻(日をまたぐときは翌日)を補い、補った終了が開始より前なら開始に揃える(CSV の取り込みと同じ規則)。保存するのは補ったあとの日時で、開き直すと補った時刻が入っている。時刻だけで日付がないときはエラー。空の時刻欄には、`省略: 始業 09:00`・`省略: 終業 15:30`(日をまたぐときは`翌 06:00`)の案内を出し、状態の自動提案も日付だけで働く。`必須`のときは、日付と時刻の両方が要る(案内は出さない)。ファイルは`actual_time_optional`(version 23。キーのない古いファイルは`省略できる`)。設定の書き出し・取り込み・3 者マージ・子プロジェクトへの切り出しに含める
```

  54 行目の設定ダイアログの項の`(と`基準日`、`プロジェクト参照の方式`、`PlantUML の通知`、`相対比率の下限・上限`)`に`実績の時刻`を足し、20 行目の切り出しで引き継ぐ設定の`実績の記録方式`の次に`実績の時刻の省略`を足す。
- `CLAUDE.md`: `version`(現在 22)を`(現在 23)`に直す。`docs/development.md`: `現在 22`を`現在 23`に直す。
- `docs/requests.md`: 要望 144 の`### 状態`を`実装済み(`feature/actual-time-optional`)。実機確認とマージの指示待ち。設計は`docs/superpowers/specs/2026-11-16-actual-time-optional-design.md`。`に、`### 決めたい点`の見出しを`### 決めた点(設計書で決定済み。2026-11-16)`に直し、中身を設計書の決定事項(時刻を補って保存・オプション`省略できる`が既定・設定ダイアログの置き場所・version 23・補う終了は始業+稼働可能時間)に書き換える。

- [ ] **Step 3: 最終の確認**

Run:
```bash
uv run pytest -m smoke
uvx ruff check
uvx ruff format src test
uvx ty check src
uv run pytest test/test_task_dialog.py test/test_forms.py test/test_views.py test/test_actual_time.py test/test_storage.py test/test_merge.py test/test_settings_io.py test/test_extract.py -q
```
Expected: smoke が PASS。ruff が通る。ty は、既存の 9 件以外が増えない。最後のテストの一式が PASS。smoke が失敗したときに限り`uv run pytest -n auto`で全テストを確かめる。

- [ ] **Step 4: コミットして PR を作る(マージは指示を待つ)**

```bash
git add -A src test docs .claude CLAUDE.md
git commit -m "docs: 実績の時刻の省略の仕様・要望の状態・version を更新する(要望 144)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/actual-time-optional
gh pr create --base develop --title "feat: 実績の時刻を省略できるオプションを足す(要望 144)" --body "設計書: docs/superpowers/specs/2026-11-16-actual-time-optional-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR を作ったら止まり、実機の確認とマージの指示を待つ。
