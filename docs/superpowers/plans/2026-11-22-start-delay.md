# 着工遅れ・停止の表示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 予定どおりに着手できなかった作業(着工・未着手)と、一時停止から再開できていない作業(停止)を、ガントチャートの帯と名前の欄のチップで示し、表示・表し方・猶予日数・帯の色をプロジェクトの設定で変えられるようにする(段階 1。ダッシュボードの件数は段階 2 で別の計画にする)。

**Architecture:** 判定は NiceGUI から切り離した純粋関数の新モジュール`start_delay.py`(`timeline.is_workday`・`effective_start`を使う)。設定は`Project`に 4 項目(`StartDelaySettings`でまとめて扱う)を足し、ファイル形式を version 24 にする。描画は`gantt.py`の既存の棒・実績・チップの描画に、帯とチップを足す。設定ダイアログは既存の`相対比率の下限・上限`と同じ形(入力は`apply`で検証し、`commit`で変更だけを通知する)。

**Tech Stack:** Python 3.13、NiceGUI(自前描画)、pytest(`nicegui.testing.User`)、ruff、ty

**Spec:** `docs/superpowers/specs/2026-11-22-start-delay-design.md`(要望 161)

## Global Constraints

- 言語は日本語(文言・コメント・コミットメッセージ)。Python 3.13 以上
- 用語は`着工遅れ`。`遅れ`(予定超過・期限超過の総称)・`遅延`は使わない。既存の遅れの判定・赤い背景・警告は変えない
- ファイル形式の`version`は 23 → 24。キーのない古いファイルは既定値で読み、不正な値は拒否する。新しい`version`は既存どおり拒否される
- 設定の既定: `start_delay_enabled=True`・`start_delay_style="both"`・`start_delay_grace=0`・`start_delay_color="#7e57c2"`
- 猶予日数は整数 0〜30。表し方は`both`・`band`・`chip`。色は`#rrggbb`(保存時は小文字)
- 日数は稼働日で数える(`timeline.is_workday(day, holidays)`。`holidays`は`GanttChart.holidays`=祝日+休みのイベント。個人の休み・稼働日の上書きは見ない = 要望 162)。日付で比べ、時刻は見ない
- 判定の対象は通常タスク(`TaskKind.NORMAL`)だけ。判定の結果は保存しない
- プレビュー(`ViewOptions.read_only=True`)・PlantUML・CSV には出さない
- 帯は斜線(`repeating-linear-gradient`)を使わない。割り当て超過の縞(白と黒の 45 度の斜線)と区別するため
- 完了の確認は`.claude/RULE.md`の順: `uv run pytest -m smoke`(失敗したときに限り`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test` → `uvx ty check src`(ty の既存の指摘 9 件は変更前からある)
- マージは利用者の指示を待つ(PR を作って止まる)。コミットメッセージの末尾に`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`を付ける

## Review Focus

- 月曜に終えて火曜に再開(毎日の区切り)・金曜に終えて月曜に再開(週末)は停止にならない。ほぼ全タスクに帯が付く事故を防ぐ(Task 3 のテスト)
- 開始予定が土日のタスクを、次の月曜に着手しても着工遅れにならない(稼働日 0 日)(Task 3)
- 実績の区間が逆順・重なり(手で編集したファイル)でも、例外を出さず、停止にしない(Task 3)
- 実績のない`実行中`・`一時停止`・`終了`を、未着手の遅れとして数えない(Task 3)
- 先行で押し出されたタスクは、押し出された実効の開始から数える(Task 3)
- 古いファイル(`version` 23 以前でキーなし)を開いても、設定は既定値になり、保存し直すと 24 になる(Task 1)
- 設定ファイルの取り込みで、新しい 4 項目のキーがない古い設定ファイルは、今の値を上書きしない(Task 2)
- 設定が表示オフ・`chip`・`band`のとき、帯・チップが出るか出ないかの組み合わせ(Task 4)
- 猶予日数・色の入力が不正なとき、ダイアログが閉じず、エラーを出し、プロジェクトが変わらない(Task 5)

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/models.py`(変更) | `StartDelayStyle`・`StartDelaySettings`・`Project`の 4 項目・`FORMAT_VERSION = 24` |
| `src/projectapp/storage.py`(変更) | 4 項目の読み込み(検証)。書き出しは`asdict`で自動 |
| `src/projectapp/merge.py`・`settings_io.py`・`extract.py`(変更) | 3 者マージ・設定のエクスポート/インポート・切り出しに 4 項目を足す(`inherit.py`は`replace`なので変更なし) |
| `src/projectapp/start_delay.py`(新規) | 判定(`missed_workdays`・`start_delays`)と、チップの文言(`chip_texts`)。NiceGUI に依存しない |
| `src/projectapp/gantt.py`(変更) | 帯の描画(`start_delay_bands`)・チップの描画(`start_delay_chips`) |
| `src/projectapp/forms.py`・`views.py`(変更) | 設定ダイアログの`着工遅れ`の節・`build_start_delay`・`MainView.apply_start_delay` |
| `.claude/spec/*.md`・`docs/development.md`・`docs/requests.md`(変更) | 仕様・モジュール構成・要望の状態 |
| `test/test_start_delay_settings.py`・`test/test_start_delay.py`・`test/test_start_delay_view.py`(新規) | それぞれ設定・判定・描画と設定ダイアログ |

作業は`develop`から切った`feature/request-161-start-delay`で行う(設計書のコミットが入っている)。

---

### Task 1: 設定の持ち方(モデル・保存・version 24)

**Files:**
- Modify: `src/projectapp/models.py`(`FORMAT_VERSION`・`Project`)
- Modify: `src/projectapp/storage.py:843`付近(読み込みの検証)・`:1455`付近(`Project(...)`の組み立て)
- Create: `test/test_start_delay_settings.py`
- Modify: `FORMAT_VERSION == 23`を見ているテスト(`grep -rn "FORMAT_VERSION\|== 23" test`で洗う)

**Interfaces:**
- Produces: `models.StartDelayStyle`(`StrEnum`: `BOTH="both"`・`BAND="band"`・`CHIP="chip"`)、`models.StartDelaySettings`(frozen dataclass: `enabled: bool = True`・`style: StartDelayStyle = StartDelayStyle.BOTH`・`grace: int = 0`・`color: str = "#7e57c2"`)、定数`models.MAX_START_DELAY_GRACE = 30`・`models.DEFAULT_START_DELAY_COLOR = "#7e57c2"`、`Project.start_delay_enabled/style/grace/color`(4 項目)、`Project.start_delay`(読み取りの property。`StartDelaySettings`を返す)、`FORMAT_VERSION = 24`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_start_delay_settings.py`:

```python
"""着工遅れの設定(要望 161): 既定値・保存と読み込み・古いファイル・不正な値。"""

import json

import pytest

from projectapp.models import (
    DEFAULT_START_DELAY_COLOR,
    FORMAT_VERSION,
    MAX_START_DELAY_GRACE,
    Project,
    StartDelaySettings,
    StartDelayStyle,
)
from projectapp.storage import dumps_project, parse_project


def test_the_defaults_show_everything_with_no_grace() -> None:
    project = Project("p")
    assert project.start_delay == StartDelaySettings(
        enabled=True, style=StartDelayStyle.BOTH, grace=0, color="#7e57c2"
    )
    assert DEFAULT_START_DELAY_COLOR == "#7e57c2"
    assert MAX_START_DELAY_GRACE == 30


def test_the_format_version_is_24() -> None:
    assert FORMAT_VERSION == 24


def test_the_settings_round_trip() -> None:
    project = Project(
        "p",
        start_delay_enabled=False,
        start_delay_style=StartDelayStyle.CHIP,
        start_delay_grace=3,
        start_delay_color="#112233",
    )
    raw = json.loads(dumps_project(project))
    assert raw["version"] == 24
    assert raw["start_delay_enabled"] is False
    assert raw["start_delay_style"] == "chip"
    assert raw["start_delay_grace"] == 3
    assert raw["start_delay_color"] == "#112233"
    loaded = parse_project(dumps_project(project), "p")
    assert loaded.start_delay == project.start_delay


def test_an_old_file_without_the_keys_gets_the_defaults() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["version"] = 23
    for key in (
        "start_delay_enabled",
        "start_delay_style",
        "start_delay_grace",
        "start_delay_color",
    ):
        del raw[key]
    loaded = parse_project(json.dumps(raw), "p")
    assert loaded.start_delay == StartDelaySettings()
    assert json.loads(dumps_project(loaded))["version"] == 24


def test_the_color_is_stored_in_lower_case() -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw["start_delay_color"] = "#AABBCC"
    assert parse_project(json.dumps(raw), "p").start_delay_color == "#aabbcc"


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("start_delay_enabled", "yes"),
        ("start_delay_enabled", 1),
        ("start_delay_style", "stripe"),
        ("start_delay_style", None),
        ("start_delay_grace", -1),
        ("start_delay_grace", 31),
        ("start_delay_grace", 1.5),
        ("start_delay_grace", True),
        ("start_delay_color", "purple"),
        ("start_delay_color", "#12345"),
        ("start_delay_color", ""),
    ],
)
def test_a_bad_value_is_rejected(key: str, bad: object) -> None:
    raw = json.loads(dumps_project(Project("p")))
    raw[key] = bad
    with pytest.raises(ValueError, match="着工遅れ"):
        parse_project(json.dumps(raw), "p")
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_start_delay_settings.py -v`
Expected: FAIL(`ImportError: cannot import name 'DEFAULT_START_DELAY_COLOR'`)

- [ ] **Step 3: モデルを書く**

`src/projectapp/models.py`の`FORMAT_VERSION`の行を`24`にし、コメントの末尾の`23: 実績の時刻の省略 actual_time_optional`の後ろに`、24: 着工遅れの設定 start_delay_enabled・start_delay_style・start_delay_grace・start_delay_color`を足す。

`RatioLimits`(`:411`)の定義のすぐ後ろに足す:

```python
MAX_START_DELAY_GRACE = 30  # 着工遅れの猶予日数の上限
DEFAULT_START_DELAY_COLOR = "#7e57c2"  # 着工遅れの帯の既定の色(赤・黄・状態の色と区別できる紫)


class StartDelayStyle(StrEnum):
    BOTH = "both"  # 帯とチップ
    BAND = "band"  # 帯だけ
    CHIP = "chip"  # チップだけ


@dataclass(frozen=True)
class StartDelaySettings:
    """着工遅れ・停止の表示の設定(要望 161)。"""

    enabled: bool = True
    style: StartDelayStyle = StartDelayStyle.BOTH
    grace: int = 0  # 遅れの稼働日数がこの値を超えたときだけ、遅れとする
    color: str = DEFAULT_START_DELAY_COLOR  # 帯の色(#rrggbb)
```

`Project`の`actual_time_optional`の行(`:445`)の直後に足す:

```python
    start_delay_enabled: bool = True  # 着工遅れ・停止を出すか(要望 161)
    start_delay_style: StartDelayStyle = StartDelayStyle.BOTH  # 帯とチップ・帯だけ・チップだけ
    start_delay_grace: int = 0  # 猶予日数(0〜30)
    start_delay_color: str = DEFAULT_START_DELAY_COLOR  # 帯の色(#rrggbb)
```

`ratio_limits`の property(`:456`)の直後に足す:

```python
    @property
    def start_delay(self) -> StartDelaySettings:
        return StartDelaySettings(
            self.start_delay_enabled,
            self.start_delay_style,
            self.start_delay_grace,
            self.start_delay_color,
        )
```

- [ ] **Step 4: 読み込みを書く**

`src/projectapp/storage.py`の`_actual_time_optional`(`:843`)の直後に足す:

```python
def _start_delay_enabled(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"着工遅れの表示の設定が正しくありません: {value!r}")
    return value


def _start_delay_style(value: Any) -> StartDelayStyle:
    try:
        return StartDelayStyle(value)
    except ValueError:
        raise ValueError(f"着工遅れの表し方の設定が正しくありません: {value!r}") from None


def _start_delay_grace(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_START_DELAY_GRACE
    ):
        raise ValueError(
            f"着工遅れの猶予日数は 0〜{MAX_START_DELAY_GRACE} の整数にしてください: {value!r}"
        )
    return value


def _start_delay_color(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError(f"着工遅れの帯の色は #rrggbb の形にしてください: {value!r}")
    return value.lower()
```

ファイル先頭の import に`re`・`StartDelayStyle`・`MAX_START_DELAY_GRACE`が無ければ足す(`from projectapp.models import (...)`の並びに追加)。

`:1455`の`actual_time_optional=(...)`の直後に足す(`ratio_limit_upper=...`の前):

```python
        start_delay_enabled=(
            _start_delay_enabled(raw.get("start_delay_enabled", True))
            if ctx.version >= 24
            else True
        ),
        start_delay_style=(
            _start_delay_style(raw.get("start_delay_style", "both"))
            if ctx.version >= 24
            else StartDelayStyle.BOTH
        ),
        start_delay_grace=(
            _start_delay_grace(raw.get("start_delay_grace", 0))
            if ctx.version >= 24
            else 0
        ),
        start_delay_color=(
            _start_delay_color(raw.get("start_delay_color", DEFAULT_START_DELAY_COLOR))
            if ctx.version >= 24
            else DEFAULT_START_DELAY_COLOR
        ),
```

(`DEFAULT_START_DELAY_COLOR`も import する。)

- [ ] **Step 5: 通ることを確認し、古い期待値のテストを直す**

Run: `uv run pytest test/test_start_delay_settings.py -v`
Expected: PASS(全 17 件前後)

Run: `uv run pytest -n auto -q 2>&1 | tail -25`
Expected: `FORMAT_VERSION == 23`などを見ているテスト(`test_reference_storage.py:44`・`test_actual_time.py:130`・`test_storage.py:1582`・`:1667`・`:2373`・`:2431`・`:2628`・`:2713`・`test_summary.py:113`)が失敗する。1 件ずつ中身を読み、**今の形式を見ている期待値だけ**を`24`に直す(古い形式のファイルを作って読み込む`version = 23`の入力データは、そのまま)。`test_actual_time.py`の`test_the_option_defaults_to_optional_and_the_version_is_23`は、名前を`..._and_the_version_is_24`にして`== 24`にする。直したあと、もう一度全テストを走らせる。
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/models.py src/projectapp/storage.py test
git commit -m "feat: 着工遅れの設定(表示・表し方・猶予日数・帯の色)を足し、形式を version 24 にする(要望 161)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 設定の伝播(3 者マージ・設定ファイル・切り出し)

**Files:**
- Modify: `src/projectapp/merge.py:236-246`(`SETTING_LABELS`)・`:760-768`(`Project(...)`の組み立て)
- Modify: `src/projectapp/settings_io.py:30-40`(`PROJECT_KEYS`)・`:55-58`(`ImportFile`)・`:118-136`(取り込み)・`:180-196`(`_describe`)・`:284-296`(適用)
- Modify: `src/projectapp/extract.py:150`付近
- Test: `test/test_start_delay_settings.py`に足す。`test/test_merge.py`・`test/test_settings_io.py`・`test/test_extract.py`の既存の`actual_time_optional`のテストの隣に足してもよい(下は新しいファイルに足す形)

**Interfaces:**
- Consumes: Task 1 の`Project.start_delay_*`・`StartDelayStyle`
- Produces: `settings_io.ImportFile.start_delay_given: bool`、`settings_io.PROJECT_KEYS`に 4 キー、`merge.SETTING_LABELS`に 4 キー

- [ ] **Step 1: 失敗するテストを書く**

`test/test_start_delay_settings.py`の末尾に足す。先頭の import に次を足す:

```python
from projectapp.extract import extract
from projectapp.merge import SETTING_LABELS, merge_projects
from projectapp.settings_io import (
    PROJECT_KEYS,
    apply_import,
    build_settings,
    parse_settings,
    plan_import,
)
```

```python
KEYS = (
    "start_delay_enabled",
    "start_delay_style",
    "start_delay_grace",
    "start_delay_color",
)


def test_the_settings_file_carries_the_four_keys() -> None:
    assert all(key in PROJECT_KEYS for key in KEYS)
    source = Project("入", start_delay_grace=2, start_delay_style=StartDelayStyle.BAND)
    data = build_settings(source)
    assert data["start_delay_grace"] == 2
    assert data["start_delay_style"] == "band"


def test_the_import_applies_the_four_items() -> None:
    source = Project(
        "入",
        start_delay_enabled=False,
        start_delay_style=StartDelayStyle.CHIP,
        start_delay_grace=3,
        start_delay_color="#0a0b0c",
    )
    incoming = parse_settings(json.dumps(build_settings(source)))
    assert incoming.start_delay_given is True
    result = apply_import(Project("現"), incoming, {"project"}, set())
    assert result.project.start_delay == source.start_delay


def test_the_settings_labels_name_the_four_items() -> None:
    assert SETTING_LABELS["start_delay_enabled"] == "着工遅れの表示"
    assert SETTING_LABELS["start_delay_style"] == "着工遅れの表し方"
    assert SETTING_LABELS["start_delay_grace"] == "着工遅れの猶予日数"
    assert SETTING_LABELS["start_delay_color"] == "着工遅れの帯の色"


def test_the_merge_takes_a_one_sided_change() -> None:
    base = Project("p")
    ours = Project("p", start_delay_grace=2)
    merged = merge_projects(base, ours, Project("p")).project
    assert merged.start_delay_grace == 2
    theirs = Project("p", start_delay_enabled=False)
    both = merge_projects(base, ours, theirs).project
    assert (both.start_delay_grace, both.start_delay_enabled) == (2, False)


def test_extract_keeps_the_four_items() -> None:
    project = Project(
        "p",
        start_delay_enabled=False,
        start_delay_style=StartDelayStyle.CHIP,
        start_delay_grace=4,
        start_delay_color="#010203",
    )
    child = extract(project, [], "子").child
    assert child.start_delay == project.start_delay


def test_an_old_settings_file_without_the_keys_keeps_the_current_values() -> None:
    text = json.dumps(
        {k: v for k, v in build_settings(Project("入")).items() if k not in KEYS}
    )
    incoming = parse_settings(text)
    assert incoming.start_delay_given is False
    current = Project(
        "現", start_delay_grace=5, start_delay_color="#0a0b0c", start_delay_enabled=False
    )
    labels = {c.label for c in plan_import(current, incoming).project_changes}
    assert not labels & {
        "着工遅れの表示",
        "着工遅れの表し方",
        "着工遅れの猶予日数",
        "着工遅れの帯の色",
    }
    result = apply_import(current, incoming, {"project"}, set())
    assert result.project.start_delay == current.start_delay
```

`extract`の呼び方(`extract(project, [], "子").child`)は`test/test_extract.py:230-231`と同じ。引数の数が合わないときは、そこを開いて同じ形にする。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_start_delay_settings.py -v`
Expected: FAIL(`KeyError`・`AttributeError: ... start_delay_given`)

- [ ] **Step 3: 実装する**

`merge.py`の`SETTING_LABELS`(`:236`)の`"actual_time_optional"`の行の後ろに足す:

```python
    "start_delay_enabled": "着工遅れの表示",
    "start_delay_style": "着工遅れの表し方",
    "start_delay_grace": "着工遅れの猶予日数",
    "start_delay_color": "着工遅れの帯の色",
```

`merge.py:766`の`actual_time_optional=settings["actual_time_optional"],`の後ろに足す:

```python
        start_delay_enabled=settings["start_delay_enabled"],
        start_delay_style=settings["start_delay_style"],
        start_delay_grace=settings["start_delay_grace"],
        start_delay_color=settings["start_delay_color"],
```

`settings_io.py`:

```python
# PROJECT_KEYS(:30)の "actual_time_optional", の次の行に
    "start_delay_enabled",
    "start_delay_style",
    "start_delay_grace",
    "start_delay_color",

# ImportFile(:55)の actual_time_given の後ろに
    start_delay_given: bool = True  # 着工遅れの 4 項目のキーがそろっていたか(古い設定ファイルにはない)
```

`:118-125`の`return ImportFile(...)`の第 3 引数の後ろに足す:

```python
        all(key in raw for key in KEYS_START_DELAY),
```

(`PROJECT_KEYS`の定義の下に`KEYS_START_DELAY = ("start_delay_enabled", "start_delay_style", "start_delay_grace", "start_delay_color")`を足し、`PROJECT_KEYS`はそれを展開して使ってもよい。)

`_incoming_project`(`:129`)に足す:

```python
    if not incoming.start_delay_given:
        project.start_delay_enabled = current.start_delay_enabled
        project.start_delay_style = current.start_delay_style
        project.start_delay_grace = current.start_delay_grace
        project.start_delay_color = current.start_delay_color
```

`_describe`(`:190`の`"実績の時刻の省略"`の次の行)に足す:

```python
        "着工遅れの表示": "出す" if project.start_delay_enabled else "出さない",
        "着工遅れの表し方": {"both": "帯とチップ", "band": "帯だけ", "chip": "チップだけ"}[
            project.start_delay_style.value
        ],
        "着工遅れの猶予日数": f"{project.start_delay_grace}日",
        "着工遅れの帯の色": project.start_delay_color,
```

`:292`の`work.actual_time_optional = source.actual_time_optional`の次に足す:

```python
    work.start_delay_enabled = source.start_delay_enabled
    work.start_delay_style = source.start_delay_style
    work.start_delay_grace = source.start_delay_grace
    work.start_delay_color = source.start_delay_color
```

`extract.py:150`の`actual_time_optional=project.actual_time_optional,`の次に足す:

```python
        start_delay_enabled=project.start_delay_enabled,
        start_delay_style=project.start_delay_style,
        start_delay_grace=project.start_delay_grace,
        start_delay_color=project.start_delay_color,
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_start_delay_settings.py test/test_merge.py test/test_settings_io.py test/test_extract.py test/test_inherit.py -q`
Expected: PASS(既存の`_describe`の件数・順序を見るテストが落ちたら、新しい 4 行を足した期待値に直す)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/merge.py src/projectapp/settings_io.py src/projectapp/extract.py test
git commit -m "feat: 着工遅れの設定を、3 者マージ・設定ファイル・切り出しに足す(要望 161)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 判定(`start_delay.py`)

**Files:**
- Create: `src/projectapp/start_delay.py`
- Create: `test/test_start_delay.py`

**Interfaces:**
- Consumes: `timeline.is_workday(day, holidays)`・`timeline.effective_start(task, project, holidays, schedule)`・`timeline.Schedule`、`models.Status`・`TaskKind`・`Actual`
- Produces:
  - `DelayKind(StrEnum)`: `START="start"`・`UNSTARTED="unstarted"`・`STOP="stop"`
  - `StartDelay`(frozen dataclass): `kind: DelayKind`・`since: datetime`・`until: datetime`・`days: int`・`ongoing: bool = False`(`until`が今のとき True)
  - `missed_workdays(first: date, last: date, holidays: dict[date, str], *, include_first: bool, include_last: bool) -> int`
  - `start_delays(task: Task, project: Project, holidays: dict[date, str], schedule: Schedule, now: datetime) -> list[StartDelay]`(`project.start_delay_grace`を使う。`start_delay_enabled`は見ない。呼ぶ側が見る)
  - `chip_texts(delays: list[StartDelay]) -> list[tuple[DelayKind, str, str]]`(種類・チップの文言・ホバーの文言。停止は 1 つにまとめる)

テストの暦: 2026-10-05 は月曜(10/2 金・10/3 土・10/4 日・10/6 火・10/7 水・10/8 木・10/9 金)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_start_delay.py`:

```python
"""着工遅れ・停止の判定(要望 161)。2026-10-05 は月曜。"""

from datetime import date, datetime, timedelta

import pytest

from projectapp.models import (
    Actual,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.start_delay import (
    DelayKind,
    StartDelay,
    chip_texts,
    missed_workdays,
    start_delays,
)
from projectapp.timeline import Schedule

NO_HOLIDAYS: dict[date, str] = {}


def delays(
    task: Task,
    now: datetime,
    *,
    grace: int = 0,
    holidays: dict[date, str] | None = None,
    others: list[Task] | None = None,
) -> list[StartDelay]:
    project = Project(
        "p",
        start_delay_grace=grace,
        sections=[Section("s", [*(others or []), task])],
    )
    h = holidays or NO_HOLIDAYS
    return start_delays(task, project, h, Schedule(project, h), now)


def task(start: datetime, *actuals: Actual, status: Status = Status.NOT_STARTED) -> Task:
    return Task(
        "設計",
        planned_start=start,
        planned_end=start + timedelta(days=2),
        status=status,
        actuals=list(actuals),
    )


def day(n: int, hour: int = 9) -> datetime:
    """10/5(月)を n=0 とした日の hour 時。"""
    return datetime(2026, 10, 5, hour) + timedelta(days=n)


# --- missed_workdays ---


def test_missed_workdays_counts_only_workdays_in_the_range() -> None:
    fri, mon = date(2026, 10, 2), date(2026, 10, 5)
    assert missed_workdays(fri, mon, NO_HOLIDAYS, include_first=True, include_last=False) == 1
    assert missed_workdays(fri, mon, NO_HOLIDAYS, include_first=False, include_last=False) == 0
    assert missed_workdays(fri, mon, NO_HOLIDAYS, include_first=True, include_last=True) == 2


def test_missed_workdays_skips_holidays_and_is_zero_for_a_reversed_range() -> None:
    holidays = {date(2026, 10, 6): "休"}
    assert (
        missed_workdays(date(2026, 10, 5), date(2026, 10, 7), holidays, include_first=True, include_last=False)
        == 1
    )
    assert missed_workdays(date(2026, 10, 7), date(2026, 10, 5), NO_HOLIDAYS, include_first=True, include_last=True) == 0


# --- 着工 ---


def test_a_start_one_workday_late_is_a_start_delay() -> None:
    result = delays(task(day(0, 12), Actual(day(1), day(1, 12))), day(3))
    assert result == [StartDelay(DelayKind.START, day(0, 12), day(1), 1)]


def test_a_start_on_the_planned_day_is_not_a_delay_even_if_the_time_is_later() -> None:
    assert delays(task(day(0, 9), Actual(day(0, 15), day(0, 17))), day(3)) == []


def test_a_weekend_start_picked_up_on_monday_is_not_a_delay() -> None:
    saturday = datetime(2026, 10, 3, 9)
    assert delays(task(saturday, Actual(day(0), day(0, 12))), day(3)) == []


def test_friday_to_monday_counts_one_workday() -> None:
    friday = datetime(2026, 10, 2, 9)
    result = delays(task(friday, Actual(day(0), day(0, 12))), day(3))
    assert [(d.kind, d.days) for d in result] == [(DelayKind.START, 1)]


def test_a_holiday_is_not_counted() -> None:
    holidays = {date(2026, 10, 6): "休"}
    result = delays(task(day(0), Actual(day(2), day(2, 12))), day(4), holidays=holidays)
    assert [(d.kind, d.days) for d in result] == [(DelayKind.START, 1)]


def test_the_grace_must_be_exceeded() -> None:
    late_one = task(day(0), Actual(day(1), day(1, 12)))
    assert delays(late_one, day(3), grace=1) == []
    late_two = task(day(0), Actual(day(2), day(2, 12)))
    assert [d.days for d in delays(late_two, day(4), grace=1)] == [2]


def test_a_predecessor_pushes_the_start_so_the_count_begins_there() -> None:
    first = Task(
        "先行",
        planned_start=day(0),
        planned_end=day(2, 15),
        planned_end_manual=True,
    )
    second = task(day(0), Actual(day(3), day(3, 12)))
    second.predecessors = [first.id]
    result = delays(second, day(5), others=[first])
    # 先行の完了(10/7)から数えるので、10/5 からの 3 日ではなく 1 日
    assert [(d.kind, d.days) for d in result] == [(DelayKind.START, 1)]


# --- 未着手 ---


def test_an_unstarted_task_past_its_start_is_a_delay_that_runs_until_now() -> None:
    result = delays(task(day(0)), day(2, 10))
    assert result == [StartDelay(DelayKind.UNSTARTED, day(0), day(2, 10), 2, True)]


def test_today_is_not_counted_for_an_unstarted_task() -> None:
    assert delays(task(day(0)), day(0, 15)) == []
    assert [d.days for d in delays(task(day(0)), day(1, 9))] == [1]


@pytest.mark.parametrize("status", [Status.RUNNING, Status.PAUSED, Status.DONE])
def test_other_statuses_without_actuals_are_not_unstarted(status: Status) -> None:
    assert delays(task(day(0), status=status), day(4)) == []


# --- 停止 ---


def test_a_missed_workday_between_intervals_is_a_stop() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), Actual(day(2), day(2, 12))), day(3)
    )
    assert result == [StartDelay(DelayKind.STOP, day(0, 12), day(2), 1)]


def test_the_next_day_is_not_a_stop() -> None:
    result = delays(task(day(0), Actual(day(0), day(0, 12)), Actual(day(1), day(1, 12))), day(3))
    assert result == []


def test_a_weekend_between_intervals_is_not_a_stop() -> None:
    result = delays(task(day(0), Actual(day(-3), day(-3, 12)), Actual(day(0), day(0, 12))), day(3))
    assert [d.kind for d in result] == []


def test_a_paused_task_is_stopped_until_now() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), status=Status.PAUSED), day(3, 10)
    )
    assert result == [StartDelay(DelayKind.STOP, day(0, 12), day(3, 10), 2, True)]


def test_a_running_task_with_a_closed_interval_is_not_stopped() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), status=Status.RUNNING), day(3, 10)
    )
    assert result == []


def test_overlapping_or_reversed_intervals_do_not_raise_or_stop() -> None:
    reversed_ = task(day(0), Actual(day(2), day(2, 12)), Actual(day(0), day(0, 12)))
    assert [d.kind for d in delays(reversed_, day(3)) if d.kind is DelayKind.STOP] == []
    overlap = task(day(0), Actual(day(0), day(2)), Actual(day(1), day(1, 12)))
    assert [d.kind for d in delays(overlap, day(3)) if d.kind is DelayKind.STOP] == []


def test_a_start_delay_and_a_stop_can_both_be_reported() -> None:
    result = delays(
        task(day(0), Actual(day(1), day(1, 12)), Actual(day(3), day(3, 12))), day(5)
    )
    assert [d.kind for d in result] == [DelayKind.START, DelayKind.STOP]


# --- 対象外 ---


def test_a_checkpoint_has_no_delay() -> None:
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=day(0))
    assert delays(checkpoint, day(4)) == []


def test_a_task_without_a_start_has_no_delay() -> None:
    assert delays(Task("日付なし"), day(4)) == []


# --- チップの文言 ---


def test_the_chip_texts_name_each_kind() -> None:
    result = chip_texts(
        [
            StartDelay(DelayKind.START, day(0, 12), day(2), 2),
            StartDelay(DelayKind.STOP, day(3, 12), day(5), 1),
            StartDelay(DelayKind.STOP, day(6, 12), day(8, 10), 1, True),
        ]
    )
    assert [(kind, text) for kind, text, _ in result] == [
        (DelayKind.START, "着工 +2日"),
        (DelayKind.STOP, "停止 +2日"),
    ]
    assert "10/05" in result[0][2] and "10/07" in result[0][2]
    assert result[1][2].count("\n") == 1  # 停止は区間ごとに 1 行
    assert "(今)" in result[1][2]


def test_the_unstarted_chip() -> None:
    [(kind, text, tip)] = chip_texts(
        [StartDelay(DelayKind.UNSTARTED, day(0), day(2, 10), 2, True)]
    )
    assert (kind, text) == (DelayKind.UNSTARTED, "未着手 +2日")
    assert "10/05" in tip
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_start_delay.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'projectapp.start_delay'`)

- [ ] **Step 3: 実装する**

`src/projectapp/start_delay.py`:

```python
"""着工遅れ・停止の判定(要望 161)。NiceGUI に依存しない。

日付で比べ、時刻は見ない。日数はプロジェクト全体の稼働日(土日・祝日・休みのイベント)で数える。
個人の休み・稼働日の上書きは見ない(要望 162)。結果は保存せず、表示のたびに算出する。
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from projectapp.models import Project, Status, Task, TaskKind
from projectapp.timeline import Schedule, effective_start, is_workday


class DelayKind(StrEnum):
    START = "start"  # 着手済みで、開始が予定より遅れた
    UNSTARTED = "unstarted"  # 開始予定を過ぎても着手していない
    STOP = "stop"  # 実績の区間の間に、作業のなかった稼働日がある・一時停止のまま


@dataclass(frozen=True)
class StartDelay:
    kind: DelayKind
    since: datetime  # 帯の始まり
    until: datetime  # 帯の終わり
    days: int  # 稼働日数
    ongoing: bool = False  # until が今(まだ続いている)か


def missed_workdays(
    first: date,
    last: date,
    holidays: dict[date, str],
    *,
    include_first: bool,
    include_last: bool,
) -> int:
    """first から last までの稼働日の数。端の日を数えるかは引数で決める。last が first より前なら 0。"""
    if last < first:
        return 0
    total = 0
    current = first
    while current <= last:
        edge = (current == first and not include_first) or (
            current == last and not include_last
        )
        if not edge and is_workday(current, holidays):
            total += 1
        current += timedelta(days=1)
    return total


def start_delays(
    task: Task,
    project: Project,
    holidays: dict[date, str],
    schedule: Schedule,
    now: datetime,
) -> list[StartDelay]:
    """タスクの着工遅れ・停止。猶予日数(`project.start_delay_grace`)を超えたものだけ。
    先頭は着工か未着手(あれば 1 つ)、続けて停止(実績の区間の順)。対象外(通常タスク以外・開始が決まらない)は空。"""
    if task.kind is not TaskKind.NORMAL:
        return []
    planned = effective_start(task, project, holidays, schedule)
    if planned is None:
        return []
    grace = project.start_delay_grace
    found: list[StartDelay] = []
    actuals = task.actuals
    if actuals:
        began = actuals[0].start
        days = missed_workdays(
            planned.date(), began.date(), holidays, include_first=True, include_last=False
        )
        if days > grace:
            found.append(StartDelay(DelayKind.START, planned, began, days))
    elif task.status is Status.NOT_STARTED:
        days = missed_workdays(
            planned.date(), now.date(), holidays, include_first=True, include_last=False
        )
        if days > grace:
            found.append(StartDelay(DelayKind.UNSTARTED, planned, now, days, True))
    for before, after in zip(actuals, actuals[1:]):
        if before.end is None or after.start <= before.end:
            continue  # 進行中の区間の後ろ・重なり・逆順(手で編集したファイル)は、停止にしない
        days = missed_workdays(
            before.end.date(),
            after.start.date(),
            holidays,
            include_first=False,
            include_last=False,
        )
        if days > grace:
            found.append(StartDelay(DelayKind.STOP, before.end, after.start, days))
    if actuals and task.status is Status.PAUSED and actuals[-1].end is not None:
        ended = actuals[-1].end
        if now > ended:
            days = missed_workdays(
                ended.date(),
                now.date(),
                holidays,
                include_first=False,
                include_last=False,
            )
            if days > grace:
                found.append(StartDelay(DelayKind.STOP, ended, now, days, True))
    return found


def _moment(value: datetime) -> str:
    return value.strftime("%m/%d %H:%M")


def chip_texts(delays: list[StartDelay]) -> list[tuple[DelayKind, str, str]]:
    """名前の欄のチップ(種類・文言・ホバー)。停止は複数あっても 1 つにまとめ、日数は合計、ホバーは区間ごとに 1 行。"""
    chips: list[tuple[DelayKind, str, str]] = []
    stops = [d for d in delays if d.kind is DelayKind.STOP]
    for delay in delays:
        if delay.kind is DelayKind.START:
            chips.append(
                (
                    delay.kind,
                    f"着工 +{delay.days}日",
                    f"予定の開始 {delay.since.strftime('%m/%d')} → 着工 {_moment(delay.until)}",
                )
            )
        elif delay.kind is DelayKind.UNSTARTED:
            chips.append(
                (
                    delay.kind,
                    f"未着手 +{delay.days}日",
                    f"予定の開始 {delay.since.strftime('%m/%d')} を過ぎても着手していません",
                )
            )
    if stops:
        lines = [
            f"{_moment(s.since)} 〜 {'(今)' if s.ongoing else _moment(s.until)}({s.days}日)"
            for s in stops
        ]
        chips.append(
            (DelayKind.STOP, f"停止 +{sum(s.days for s in stops)}日", "\n".join(lines))
        )
    return chips
```

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_start_delay.py -v`
Expected: PASS。`test_a_predecessor_pushes_the_start_so_the_count_begins_there`が落ちるときは、先に`effective_start`が返す値を確かめる(`print(effective_start(second, project, {}, Schedule(project, {})))`)。先行の完了が 10/7 15:00 でなければ、テストの`day(2, 15)`・期待の日数を、実際の押し出し先の日付に合わせて直す(押し出された日から数えていることが本質)。

- [ ] **Step 5: 設計書の記述を合わせる**

`docs/superpowers/specs/2026-11-22-start-delay-design.md`の`## 判定(`timeline.py`の純粋関数)`の見出しを`## 判定(`start_delay.py`の純粋関数)`にし、本文の`timeline.py`への言及を`start_delay.py`に直す(`is_workday`・`effective_start`は`timeline.py`のものを使う、と 1 文足す)。

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/start_delay.py test/test_start_delay.py docs/superpowers/specs/2026-11-22-start-delay-design.md
git commit -m "feat: 着工遅れ・停止の判定とチップの文言を、純粋関数で足す(要望 161)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ガントチャートの帯とチップ

**Files:**
- Modify: `src/projectapp/gantt.py`(定数・`start_delay_bands`・`start_delay_chips`・呼び出し 2 か所。`actual_bars`の呼び出しは`:3155`、`task_chips`は`:3166`)
- Create: `test/test_start_delay_view.py`

**Interfaces:**
- Consumes: Task 1 の`Project.start_delay`・`StartDelayStyle`、Task 3 の`start_delays`・`chip_texts`・`DelayKind`
- Produces: 要素の印`start-delay-{key}-{ti}-{n}`(帯)・`task-start-delay-{key}-{ti}-{n}`(チップ)、`GanttChart.delays_of(task)`

テストの`mount`・`mount_with`・`actual_project`・`BASE`(= 2026-10-05 月曜)は`test/test_gantt.py`にある。新しいテストファイルでは、`test_gantt.py`の`mount`(`:219`)と同じ作りの小さな関数を、このファイルの中に定義する(他のテストファイルの関数に依存しない)。日次スケールで、1 日 40px、列の始まりが 10/5 0:00(`test_gantt.py:2306`の実績の隙間のテストと同じ前提)。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_start_delay_view.py`:

```python
"""着工遅れ・停止の描画(要望 161): ガントチャートの帯と名前の欄のチップ。"""

from datetime import date, datetime

import pytest
from nicegui import ui
from nicegui.testing import User

from projectapp.gantt import (
    ACTUAL_HEIGHT_PX,
    ACTUAL_TOP_PX,
    BAR_HEIGHT_PX,
    BAR_TOP_PX,
    GanttChart,
    ViewOptions,
)
from projectapp.models import (
    Actual,
    Project,
    Section,
    StartDelayStyle,
    Task,
)

BASE = date(2026, 10, 5)  # 月曜


def mount(project: Project, now: datetime = datetime(2026, 10, 9, 10)) -> list[GanttChart]:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        chart = GanttChart(project, {}, lambda *_: None, now=lambda: now)
        charts.append(chart)
        chart.build()

    return charts


def late_start_project(**settings: object) -> Project:
    """予定の開始 10/5 12:00、実績の開始 10/7 9:00(月・火の 2 稼働日の遅れ)。"""
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 9, 12),
        actuals=[Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12))],
    )
    return Project(
        "demo", base_date=BASE, sections=[Section("開発", [task])], **settings
    )


def stopped_project(**settings: object) -> Project:
    """実績が 10/5 9〜12 と 10/7 9〜12。火曜が抜けている(停止 1 日)。"""
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 12),
        actuals=[
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 7, 9), datetime(2026, 10, 7, 12)),
        ],
    )
    return Project(
        "demo", base_date=BASE, sections=[Section("開発", [task])], **settings
    )


async def test_a_start_delay_band_is_drawn_left_of_the_bar(user: User) -> None:
    mount(late_start_project())
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert band._style["left"] == "20.0px"  # 10/5 12:00 = 0.5 日
    assert band._style["width"] == "75.0px"  # 10/7 9:00 = 2.375 日。(2.375 - 0.5) * 40
    assert band._style["top"] == f"{BAR_TOP_PX}px"
    assert band._style["height"] == f"{BAR_HEIGHT_PX}px"
    assert "dashed" in band._style["border"]
    assert "#7e57c2" in band._style["border"]
    assert "repeating-linear-gradient" not in band._style["background"]


async def test_the_chip_names_the_delay(user: User) -> None:
    mount(late_start_project())
    await user.open("/")
    await user.should_see("着工 +2日")
    await user.should_see(marker="task-start-delay-0-0-0")


async def test_a_stop_band_sits_in_the_actual_lane(user: User) -> None:
    mount(stopped_project())
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert band._style["top"] == f"{ACTUAL_TOP_PX}px"
    assert band._style["height"] == f"{ACTUAL_HEIGHT_PX}px"
    await user.should_see("停止 +1日")
    await user.should_not_see("着工")


async def test_an_unstarted_task_gets_a_band_up_to_now(user: User) -> None:
    task = Task(
        "設計",
        planned_start=datetime(2026, 10, 5, 12),
        planned_end=datetime(2026, 10, 9, 12),
    )
    mount(Project("demo", base_date=BASE, sections=[Section("開発", [task])]))
    await user.open("/")
    await user.should_see("未着手 +4日")  # 10/5〜10/8 の 4 稼働日(今は 10/9)
    await user.should_see(marker="start-delay-0-0-0")


@pytest.mark.parametrize(
    ("style", "band", "chip"),
    [
        (StartDelayStyle.BOTH, True, True),
        (StartDelayStyle.BAND, True, False),
        (StartDelayStyle.CHIP, False, True),
    ],
)
async def test_the_style_chooses_the_band_and_the_chip(
    user: User, style: StartDelayStyle, band: bool, chip: bool
) -> None:
    mount(late_start_project(start_delay_style=style))
    await user.open("/")
    for marker, shown in (("start-delay-0-0-0", band), ("task-start-delay-0-0-0", chip)):
        if shown:
            await user.should_see(marker=marker)
        else:
            await user.should_not_see(marker=marker)


async def test_nothing_is_drawn_when_it_is_off(user: User) -> None:
    mount(late_start_project(start_delay_enabled=False))
    await user.open("/")
    await user.should_not_see(marker="start-delay-0-0-0")
    await user.should_not_see(marker="task-start-delay-0-0-0")


async def test_the_color_and_the_grace_are_used(user: User) -> None:
    mount(late_start_project(start_delay_color="#112233"))
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert "#112233" in band._style["border"]


async def test_the_grace_hides_a_short_delay(user: User) -> None:
    mount(late_start_project(start_delay_grace=2))
    await user.open("/")
    await user.should_not_see(marker="start-delay-0-0-0")


async def test_the_read_only_chart_does_not_draw_it(user: User) -> None:
    charts = mount(late_start_project())
    await user.open("/")
    charts[0].set_options(ViewOptions(read_only=True))
    await user.should_not_see(marker="start-delay-0-0-0")
    await user.should_not_see(marker="task-start-delay-0-0-0")


async def test_the_stripes_for_an_overload_are_not_replaced(user: User) -> None:
    """帯は斜線を使わないので、割り当て超過の縞と見分けられる。"""
    mount(late_start_project())
    await user.open("/")
    band = user.find(marker="start-delay-0-0-0").elements.pop()
    assert "gradient" not in band._style["background"]
```

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_start_delay_view.py -v`
Expected: FAIL(`start-delay-0-0-0`が見つからない)

- [ ] **Step 3: 描画を書く**

`gantt.py`の import に足す: `from projectapp.models import StartDelayStyle`(既存の models の import に追加)・`from projectapp.start_delay import DelayKind, StartDelay, chip_texts, start_delays`。

定数(`ACTUAL_TOP_PX`の近く、`:202`の後ろ)に足す:

```python
START_DELAY_FILL_PERCENT = 35  # 着工遅れの帯の塗りの濃さ(色の何%を、透明に混ぜるか)
START_DELAY_CHIP_STYLE = (
    "color: #fff; border-radius: 8px; padding: 0 6px; font-size: 11px;"
    " white-space: nowrap; flex: 0 0 auto"
)
```

`GanttChart`のメソッドを、`actual_bars`(`:3384`)の直前に足す:

```python
    def delays_of(self, task: Task) -> list[StartDelay]:
        """着工遅れ・停止(要望 161)。設定がオフ・プレビュー(読み取り専用)・対象外のタスクは空。"""
        if (
            not self.project.start_delay_enabled
            or self.options.read_only
            or task.kind is not TaskKind.NORMAL
        ):
            return []
        return start_delays(task, self.project, self.holidays, self.schedule, self.now())

    def start_delay_bands(
        self,
        key: int | str,
        ti: int,
        task: Task,
        columns: list[Column],
        width: int,
    ) -> None:
        """着工遅れ・停止の帯。色の半透明の塗りと点線の枠で、斜線は使わない(割り当て超過の縞と区別する)。
        着工・未着手は予定の棒の左の外側、停止は実績の行(棒の下半分)の隙間の上。"""
        if self.project.start_delay_style is StartDelayStyle.CHIP:
            return
        color = self.project.start_delay_color
        for n, delay in enumerate(self.delays_of(task)):
            if not self.bar_visible(delay.since, delay.until, columns):
                continue
            left, length = interval_span(delay.since, delay.until, columns)
            top, height = (
                (ACTUAL_TOP_PX, ACTUAL_HEIGHT_PX)
                if delay.kind is DelayKind.STOP
                else (BAR_TOP_PX, BAR_HEIGHT_PX)
            )
            ui.element("div").style(
                f"position: absolute; left: {from_name(left * width)};"
                f" width: {max(length * width, MIN_BAR_PX):.1f}px;"
                f" top: {top}px; height: {height}px;"
                f" background: color-mix(in srgb, {color} {START_DELAY_FILL_PERCENT}%, transparent);"
                f" border: 1.5px dashed {color}; box-sizing: border-box;"
                " border-radius: 3px; pointer-events: none; user-select: none"
            ).mark(f"start-delay-{key}-{ti}-{n}")

    def start_delay_chips(self, key: int | str, ti: int, task: Task) -> None:
        """名前の欄の着工遅れ・停止のチップ。名前の欄の枠の中で呼ぶ。"""
        if self.project.start_delay_style is StartDelayStyle.BAND:
            return
        for n, (_, text, tip) in enumerate(chip_texts(self.delays_of(task))):
            ui.label(text).style(
                f"{START_DELAY_CHIP_STYLE}; background: {self.project.start_delay_color}"
            ).tooltip(tip).mark(f"task-start-delay-{key}-{ti}-{n}")
```

呼び出しを足す:
- `:3155`の`self.actual_bars(path, ti, task, columns, width)`の次の行に`self.start_delay_bands(key, ti, task, columns, width)`(周りの変数名は、その行の前後を読んで合わせる。`key`が無ければ`section_key(path)`)
- `task_chips`の中、進捗の`ui.label(f"{percent}%")`のブロックの後ろ、`if task.urls and not self.options.read_only:`の前に`self.start_delay_chips(key, ti, task)`

- [ ] **Step 4: 通ることを確認する**

Run: `uv run pytest test/test_start_delay_view.py -v`
Expected: PASS。`test_the_read_only_chart_does_not_draw_it`で`set_options`後に再描画されない場合は、`test_gantt.py:1108`の`test_read_only_shows_every_row...`が`set_options`の後に要素を確かめている方法に合わせる。帯の`left`・`width`の数値が違うときは、`interval_span`の戻り値(列の幅の単位)を`test_gantt.py:2306`の実績の隙間のテストと照らして、期待値を直す(本質は、棒の左の外側に出ること・点線の枠・斜線がないこと)。

- [ ] **Step 5: 既存の描画を壊していないことを確認する**

Run: `uv run pytest test/test_gantt.py -n auto -q`
Expected: PASS(既存のチップ・実績の棒のテストが、新しいチップ・帯で落ちた場合は、そのテストのタスクが着工遅れ・停止に当たっている。テストのデータを直すのでなく、まず本当に遅れの条件に当たっているかを確かめ、当たっているなら、そのテストのプロジェクトに`start_delay_enabled=False`を足して、既存の確認の趣旨を守る)

- [ ] **Step 6: コミット**

```bash
git add src/projectapp/gantt.py test/test_start_delay_view.py
git commit -m "feat: ガントチャートに着工遅れ・停止の帯と名前の欄のチップを出す(要望 161)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 設定ダイアログと`MainView`

**Files:**
- Modify: `src/projectapp/forms.py`(`build_start_delay`・`open_settings_dialog`の引数・`着工遅れ`の節・`apply`・`commit`)
- Modify: `src/projectapp/views.py`(`apply_start_delay`・ダイアログの呼び出し`:1531`付近)
- Test: `test/test_start_delay_view.py`に足す。`test/test_forms.py`・`test/test_views.py`の`actual_time_optional`の隣に足してもよい

**Interfaces:**
- Consumes: Task 1 の`StartDelaySettings`・`StartDelayStyle`・`MAX_START_DELAY_GRACE`
- Produces: `forms.build_start_delay(enabled: bool, style: str, grace: object, color: str) -> StartDelaySettings`(不正は`ValueError`)、`open_settings_dialog(..., start_delay: StartDelaySettings = StartDelaySettings(), on_start_delay: Callable[[StartDelaySettings], object] | None = None)`、`MainView.apply_start_delay(settings: StartDelaySettings) -> None`、要素の印`settings-start-delay-enabled`・`settings-start-delay-style`・`settings-start-delay-grace`・`settings-start-delay-color`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_start_delay_view.py`の末尾に足す。先頭の import に`from datetime import time`・`from projectapp.forms import build_start_delay, open_settings_dialog`・`from projectapp.models import StartDelaySettings`を足す。

```python
def test_build_start_delay_reads_the_inputs() -> None:
    assert build_start_delay(True, "band", 3, "#ABCDEF") == StartDelaySettings(
        True, StartDelayStyle.BAND, 3, "#abcdef"
    )


@pytest.mark.parametrize(
    ("grace", "color", "message"),
    [
        (-1, "#7e57c2", "猶予日数"),
        (31, "#7e57c2", "猶予日数"),
        (1.5, "#7e57c2", "猶予日数"),
        (None, "#7e57c2", "猶予日数"),
        (0, "purple", "色"),
        (0, "", "色"),
    ],
)
def test_build_start_delay_rejects_bad_inputs(
    grace: object, color: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_start_delay(True, "both", grace, color)


async def test_the_settings_dialog_reports_a_changed_start_delay(user: User) -> None:
    applied: list[StartDelaySettings] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda *a: None,
                start_delay=StartDelaySettings(),
                on_start_delay=applied.append,
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-start-delay-style").elements.pop().set_value("chip")
    user.find(marker="settings-start-delay-grace").elements.pop().set_value(2)
    user.find(marker="settings-apply").click()
    assert applied == [StartDelaySettings(True, StartDelayStyle.CHIP, 2, "#7e57c2")]


async def test_an_unchanged_start_delay_is_not_reported(user: User) -> None:
    applied: list[StartDelaySettings] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda *a: None,
                start_delay=StartDelaySettings(grace=1),
                on_start_delay=applied.append,
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-apply").click()
    assert applied == []


async def test_a_bad_grace_keeps_the_dialog_open_and_reports_nothing(user: User) -> None:
    applied: list[StartDelaySettings] = []

    @ui.page("/")
    def index() -> None:
        ui.button(
            "open",
            on_click=lambda: open_settings_dialog(
                6.5,
                time(9, 0),
                lambda *a: None,
                start_delay=StartDelaySettings(),
                on_start_delay=applied.append,
            ),
        )

    await user.open("/")
    user.find("open").click()
    user.find(marker="settings-start-delay-grace").elements.pop().set_value(99)
    user.find(marker="settings-apply").click()
    assert applied == []
    await user.should_see("猶予日数")
```

`MainView.apply_start_delay`のテストは、`test/test_views.py:9636-9666`の`apply_actual_time_optional`のテストを写して足す(`view.apply_start_delay(StartDelaySettings(False))`で`view.project.start_delay_enabled is False`・同じ値では`after_edit`が呼ばれない・元に戻せる、の 3 点。そこで使っている fixture・`view`の作り方をそのまま使う)。

- [ ] **Step 2: 失敗を確認する**

Run: `uv run pytest test/test_start_delay_view.py -k "build_start_delay or settings_dialog or bad_grace" -v`
Expected: FAIL(`ImportError: cannot import name 'build_start_delay'`)

- [ ] **Step 3: `build_start_delay`を書く**

`forms.py`の`build_ratio_limits`(`:739`)の直前に足す(`models`から`MAX_START_DELAY_GRACE`・`StartDelaySettings`・`StartDelayStyle`を import する。`re`が無ければ import する):

```python
def build_start_delay(
    enabled: bool, style: str, grace: object, color: str
) -> StartDelaySettings:
    """着工遅れの入力を検証する。猶予日数は 0〜30 の整数、色は #rrggbb(小文字にそろえる)。"""
    if isinstance(grace, bool) or not isinstance(grace, (int, float)) or grace != int(grace):
        raise ValueError(f"着工遅れの猶予日数は 0〜{MAX_START_DELAY_GRACE} の整数にしてください")
    days = int(grace)
    if not 0 <= days <= MAX_START_DELAY_GRACE:
        raise ValueError(f"着工遅れの猶予日数は 0〜{MAX_START_DELAY_GRACE} の整数にしてください")
    text = color.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text) is None:
        raise ValueError("着工遅れの帯の色は #rrggbb の形で入力してください")
    return StartDelaySettings(enabled, StartDelayStyle(style), days, text.lower())
```

- [ ] **Step 4: ダイアログに節を足す**

`open_settings_dialog`の引数(`:1950`の`on_ratio_limits`の次)に足す:

```python
    start_delay: StartDelaySettings = StartDelaySettings(),
    on_start_delay: Callable[[StartDelaySettings], object] | None = None,
```

`相対比率の下限・上限`の節(`:2055-2093`)が終わった直後(`rows = [TemplateRow(...` の前)に足す:

```python
        delay_enabled = delay_style = delay_grace = delay_color = None
        if on_start_delay is not None:
            ui.label("着工遅れ").classes("text-caption text-grey")
            ui.label(
                "予定の開始より遅れて着手したタスク・開始予定を過ぎても未着手のタスク・再開できていない停止を、ガントチャートに帯とチップで出します"
            ).classes("text-caption text-grey")
            delay_enabled = ui.switch("着工遅れを表示する", value=start_delay.enabled).mark(
                "settings-start-delay-enabled"
            )
            delay_style = ui.toggle(
                {"both": "帯とチップ", "band": "帯だけ", "chip": "チップだけ"},
                value=start_delay.style.value,
            ).mark("settings-start-delay-style")
            with ui.row().classes("items-center"):
                delay_grace = (
                    ui.number(
                        "猶予日数(稼働日)",
                        value=start_delay.grace,
                        min=0,
                        max=MAX_START_DELAY_GRACE,
                        step=1,
                        precision=0,
                    )
                    .props("dense")
                    .classes("w-40")
                    .mark("settings-start-delay-grace")
                )
                delay_color = (
                    ui.color_input("帯の色(#RRGGBB)", value=start_delay.color)
                    .classes("w-48")
                    .mark("settings-start-delay-color")
                )
                delay_color.picker.q_color.props("no-header no-footer format-model=hex")
```

`apply`の`try`の中、`limits = (...)`の直後に足す(検証だけ。値は`commit`で読み直す):

```python
                if delay_enabled is not None:
                    build_start_delay(
                        bool(delay_enabled.value),
                        delay_style.value,
                        delay_grace.value,
                        delay_color.value or "",
                    )
```

`commit`の中、`on_ratio_limits(limits)`のブロックの後ろ、`edit is not None ...`の前に足す:

```python
            if delay_enabled is not None and on_start_delay is not None:
                chosen = build_start_delay(
                    bool(delay_enabled.value),
                    delay_style.value,
                    delay_grace.value,
                    delay_color.value or "",
                )
                if chosen != start_delay:
                    on_start_delay(chosen)
```

- [ ] **Step 5: `MainView`につなぐ**

`views.py`の`apply_actual_time_optional`(`:2599`)の直後に足す(`StartDelaySettings`を models から import):

```python
    def apply_start_delay(self, settings: StartDelaySettings) -> None:
        """着工遅れ・停止の表示の設定を変える(要望 161)。保存はしない。"""
        if settings == self.project.start_delay:
            return
        self.project.start_delay_enabled = settings.enabled
        self.project.start_delay_style = settings.style
        self.project.start_delay_grace = settings.grace
        self.project.start_delay_color = settings.color
        self.after_edit()
```

`:1535`の`on_ratio_limits=self.apply_ratio_limits,`の次に足す:

```python
            start_delay=self.project.start_delay,
            on_start_delay=self.apply_start_delay,
```

- [ ] **Step 6: 通ることを確認する**

Run: `uv run pytest test/test_start_delay_view.py test/test_forms.py test/test_views.py -n auto -q`
Expected: PASS。`set_value(2)`で`ui.number`の値が整数でなく`2.0`になる場合は、`build_start_delay`の`grace != int(grace)`の判定で通る(`2.0`は整数として読む)。`test_a_bad_grace...`で`set_value(99)`が、`ui.number`の`max`で丸められる場合は、`set_value(1.5)`に変えて、「整数にしてください」の文言を見る。

- [ ] **Step 7: コミット**

```bash
git add src/projectapp/forms.py src/projectapp/views.py test
git commit -m "feat: 設定ダイアログに着工遅れの設定(表示・表し方・猶予日数・帯の色)を足す(要望 161)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 仕様・文書・確認

**Files:**
- Modify: `.claude/spec/gantt.md`(用語・帯・チップ)・`.claude/spec/project-files.md`(設定の項目・version 24)・`.claude/spec/implementation.md`(version 24)・`CLAUDE.md`(`version`の数字 23 → 24。200 行以内を保つ)
- Modify: `docs/development.md`(モジュール構成に`start_delay.py`・テストに 3 ファイル)
- Modify: `docs/requests.md`(要望 161 の状態を`段階 1 実装済み(段階 2: ダッシュボードは未着手)`に)

- [ ] **Step 1: 仕様を書く**

`.claude/spec/gantt.md`の、実績の棒(`actual_bars`)の説明の近くに 1 項目を足す(既存の項目の書式・粒度に合わせる)。入れる内容: 用語`着工遅れ`(`着工`・`未着手`・`停止`)・判定(日付で比べ、稼働日で数える。個人の休み・稼働日の上書きは見ない = 要望 162。猶予日数を超えたとき)・帯(点線の枠・半透明の塗り・斜線なし・着工と未着手は棒の左の外側、停止は実績の行)・チップ(`着工 +n日`・`未着手 +n日`・`停止 +n日`・停止は合計)・設定(表示・表し方・猶予日数・帯の色。設定ダイアログの`着工遅れ`)・プレビューでは出さない・保存しない。`遅れ`(予定超過・期限超過の総称)に含めないことを明記する。

`.claude/spec/project-files.md`と`.claude/spec/implementation.md`の`version`の記述に、`24: 着工遅れの設定`を足す。`CLAUDE.md`の`先頭の`version`(現在 23)`を`24`にする。

- [ ] **Step 2: 検証コマンドを順に走らせる**

Run: `uv run pytest -m smoke -q`
Expected: PASS(落ちたときに限り`uv run pytest -n auto -q`)

Run: `uvx ruff check && uvx ruff format src test`
Expected: エラーなし(整形で変わったファイルは、そのコミットに含める)

Run: `uvx ty check src`
Expected: 既存の 9 件以外の指摘なし

- [ ] **Step 3: 実機で確認できるデータを用意する**

`docs/samples/`の置き場の慣習(`reference-projectapp-sample-data`のメモ)に従い、確認用のプロジェクトを`docs/samples/`か`~/.projectapp/`に置く(遅れが出る例: 予定が月曜で火・水に着手したタスク、開始予定を過ぎて未着手のタスク、月曜に終えて水曜に再開したタスク、一時停止のままのタスク、割り当て超過の縞と重なるタスク)。置いたファイルは、消してよい範囲(`docs/samples`の確認用)か、利用者に確かめてから消す。

- [ ] **Step 4: コミットして PR を作り、止まる**

```bash
git add -A
git commit -m "docs: 着工遅れ・停止の仕様と構成を書く(要望 161 の段階 1)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin feature/request-161-start-delay
gh pr create --base develop --title "feat: 着工遅れ・停止の表示(要望 161 段階 1)" --body "..."
```

PR の本文は、概要(判定・帯・チップ・設定)、確認したこと(smoke・ruff・ty)、実機で見てほしい点(割り当て超過の縞との見分け・日次/週次/月次/四半期での帯の幅・設定ダイアログの操作と元に戻す)、段階 2 が未着手であること、末尾に`🤖 Generated with [Claude Code](https://claude.com/claude-code)`を書く。**マージは利用者の指示を待つ**。最終レビューのモデルは sonnet を指定する。

---

## Self-Review(計画を書いたあとの確認)

- 仕様の対応: 判定(Task 3)・設定 4 項目と version 24(Task 1)・伝播(Task 2)・帯とチップ(Task 4)・設定ダイアログ(Task 5)・仕様と文書(Task 6)。ダッシュボード(段階 2)は含めない(設計書どおり、着手時に追記して別の計画にする)
- 型と名前: `StartDelaySettings`・`StartDelayStyle`・`StartDelay`・`DelayKind`・`start_delays`・`chip_texts`・`missed_workdays`・`delays_of`・`start_delay_bands`・`start_delay_chips`・`build_start_delay`・`apply_start_delay`は、定義(Task 1・3)と使う側(Task 4・5)で一致している
- 実装時に実物で確かめる箇所: Task 2 の取り込みテストの呼び出し名(`test_settings_io.py:485`を写す)、Task 3 の先行の押し出しの日付、Task 4 の帯の`left`・`width`の数値と読み取り専用への切り替え、Task 5 の`ui.number`の丸め。いずれも、確かめる手順を各タスクの中に書いた
