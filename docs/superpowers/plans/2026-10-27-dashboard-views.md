# ダッシュボードのカスタムビュー Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードの期間(`指定`なら日付も)・メンバー・`全プロジェクト`・カードの出し入れと順を、名前付きのビューとして `~/.projectapp/config.json` に保存し、切り替え・編集(ドラッグ)できるようにする。

**Architecture:** 純粋関数の新モジュール `dashboard_views.py`(`ViewSpec`・検証・カード操作・`config.json` との変換)を土台にする。条件(期間・メンバー・横断)の状態は今までどおり `MainView` が持ち、そこから「作業中のビュー」(`working_spec`)を組み立てて、保存済みのビューと比べて `●`(未保存)を決める(フラグを持たない)。`DashboardView` は、カードを「`CardId` → 描画メソッド」の表と `ViewState`(MainView が作る)の順で描き、ツールバー(ビューの選択と操作)と編集モード(ドラッグ・非表示)を足す。ブラウザ側のドラッグは、`gantt_drag.py` と同じ流儀の JS を新ファイル `dashboard_drag.py` に置き、`emitEvent` で Python に返す。

**Tech Stack:** Python 3.13、NiceGUI、pytest(`uv run pytest`)、`uvx ty check src`。

**Spec:** `docs/superpowers/specs/2026-10-27-dashboard-views-design.md`

## Global Constraints

- 保存先は `~/.projectapp/config.json`(全プロジェクト共通)。キーは `dashboard_views`(ビューのリスト。`標準`を含まない)と `dashboard_view_last`(最後に使ったビューの名前)。プロジェクトのファイル(`version`・3 者マージ・元に戻す履歴)には触れない。
- `指定`の期間は日付そのもの(`{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}`)で保存する。`指定`以外のビューは日付を持たない。年は 2000〜2100(`models.MIN_YEAR`・`MAX_YEAR`)、開始日は終了日以前、`dashboard.MAX_CUSTOM_DAYS`(400 日)以内。
- 名前は 30 文字まで・空不可・制御文字(`models.has_control_char`)不可・`標準`と同名不可・重複不可。ビューは `標準` を除いて 20 件まで。
- `全プロジェクト`のスイッチは保存するが、プロジェクトごとの除外は保存しない(ビューを適用すると除外は空に戻る)。
- 保存したメンバーが今の名簿にいないときは、画面上だけ `全員` に戻し、ビューは書き換えない(未保存の `●` にもしない)。
- ダッシュボードを開くたびに、`dashboard_view_last` のビュー(なければ `標準`)を適用する。作業中の変更は持ち越さない。別のビューへの切り替えは、作業中の変更を確認なしで捨てる。
- 言語は日本語。UI の文言・コメント・テスト名の流儀は周囲のコードに合わせる(コメントは少なめの日本語、型注釈あり)。
- テストは `uv run pytest`(並列は `-n auto`)。実際のホームの `~/.projectapp` を読み書きしない(`tmp_path` を使う)。型検査は `uvx ty check src`。
- 描画は NiceGUI の要素と CSS による自前描画。ドラッグのブラウザ側の JS は自動テストしない(定数の中身と、Python の受け口だけテストする)。

## Review Focus

- `config.json` に `dashboard_views` が文字列・数値・`null`・辞書で入っている、または `config.json` 自体が壊れた JSON: ビューは `標準` だけで起動し、例外で落ちない(Task 2)。
- ビューの JSON に未知のカード ID・重複したカード・`cards` が文字列・`period` が未知の値: 不正な件だけ捨てるか補正し、ほかのビューは生きる(Task 1)。
- 保存したメンバーが削除・改名されている / `全プロジェクト`で別プロジェクトのメンバーだったビュー: `全員`で開き、`●` が出ない(Task 4)。
- `指定` のビューの日付が 401 日・逆順・範囲外年: そのビューは残り、日付だけ捨てる(Task 1)。`指定` の欄がエラーのまま `保存` / `名前をつけて保存` を押しても、保存されない(Task 4)。
- `config.json` が書けない(ディスク満杯・権限): 通知を出し、画面上のビューは使い続ける。例外で落ちない(Task 4)。
- ドラッグの受け口に、未知のカード ID・自分自身の手前・`before` が隠れているカードの ID が来ても壊れない(Task 1・6)。

---

## File Structure

| ファイル | 役割 |
|---|---|
| `src/projectapp/dashboard_views.py`(新規) | 純粋関数。`CardId`・`ViewSpec`・`ViewState`、検証、カード操作、`config.json` との変換、ドラッグ引数の解析 |
| `src/projectapp/dashboard_drag.py`(新規) | カードのドラッグの JS・CSS の定数(`gantt_drag.py` と同じ流儀) |
| `src/projectapp/config.py` | `load/save_dashboard_views`・`load/save_dashboard_view_last` |
| `src/projectapp/dashboard_view.py` | カードを順序表で描く、ツールバー(ビューの選択・操作)、編集モード、`ViewActions` |
| `src/projectapp/views.py` | `MainView` の状態(ビューの一覧・今のビューの名前・カードの並び)と、操作のハンドラ、`open_dashboard` の適用 |
| `test/test_dashboard_views.py`(新規) | 純粋関数のテスト |
| `test/test_dashboard_drag.py`(新規) | JS 定数のテスト |
| `test/test_config.py` | 保存・読込のテストを追加 |
| `test/test_dashboard_view.py` | `DashboardView` 単体(順序・ツールバー・編集モード) |
| `test/test_views.py` | `MainView` の統合(切り替え・保存・削除・永続化) |
| `CLAUDE.md`・`docs/development.md`・`docs/requests.md`・`.claude/MEMORY.md` | 仕様・モジュール表・状態の更新(Task 7) |

設計書からの小さな変更(Task 7 で設計書にも反映する):
1. `名前をつけて保存` は常に出す(`標準` のままでも新しいビューを作れるように)。`保存`・`元に戻す` は `●` のときだけ出す。
2. `指定` のビューに日付がないとき(日付が不正で捨てられたとき)は、`指定` を選んだときと同じく、直前の期間から始める(欄は空にしない)。

---

### Task 1: 純粋関数 `dashboard_views.py`(ビューの型・検証・カード操作)

**Files:**
- Create: `src/projectapp/dashboard_views.py`
- Test: `test/test_dashboard_views.py`

**Interfaces:**
- Consumes: `dashboard.PeriodKind`・`dashboard.Period`・`dashboard.MAX_CUSTOM_DAYS`・`dashboard.custom_period_error`、`periodfield.validate_period`、`models.has_control_char`
- Produces(後続タスクが使う):
  - `STANDARD_NAME: str = "標準"`、`MAX_VIEWS = 20`、`MAX_VIEW_NAME = 30`
  - `class CardId(StrEnum)`: `TEAM="team"`・`PROGRESS="progress"`・`LOAD="load"`・`HEATMAP="heatmap"`・`HOURS="hours"`・`DUE="due"`
  - `DEFAULT_ORDER: tuple[CardId, ...]`
  - `@dataclass(frozen=True) class ViewSpec`: `name: str`・`period: PeriodKind`・`member: str | None`・`cross: bool`・`cards: tuple[CardId, ...]`・`custom: tuple[date, date] | None = None`
  - `@dataclass(frozen=True) class ViewState`: `names: tuple[str, ...]`・`current: str`・`dirty: bool`・`save_block: str | None`・`cards: tuple[CardId, ...]`・`hidden: tuple[CardId, ...]`
  - `standard_view() -> ViewSpec`
  - `validate_custom(start: date, end: date) -> str | None`
  - `normalize_cards(cards: object) -> tuple[CardId, ...]`
  - `validate_name(name: str, taken: Iterable[str]) -> str | None`(`name` は前後の空白を除いたもの)
  - `move_card(cards, card_id, before_id) -> tuple[CardId, ...]`、`hide_card(cards, card_id)`、`show_card(cards, card_id)`
  - `hidden_cards(cards, cross: bool) -> tuple[CardId, ...]`
  - `resolve_member(member: str | None, names: Iterable[str]) -> str | None`
  - `parse_card_move(args: object) -> tuple[CardId, CardId | None] | None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_views.py` を新規作成する:

```python
from datetime import date

from projectapp.dashboard import PeriodKind
from projectapp.dashboard_views import (
    DEFAULT_ORDER,
    MAX_VIEW_NAME,
    STANDARD_NAME,
    CardId,
    ViewSpec,
    hidden_cards,
    hide_card,
    move_card,
    normalize_cards,
    parse_card_move,
    resolve_member,
    show_card,
    standard_view,
    validate_custom,
    validate_name,
)


def test_the_default_order_matches_the_current_dashboard() -> None:
    assert DEFAULT_ORDER == (
        CardId.TEAM, CardId.PROGRESS, CardId.LOAD, CardId.HEATMAP, CardId.HOURS, CardId.DUE,
    )


def test_the_standard_view_is_todays_dashboard() -> None:
    assert standard_view() == ViewSpec(STANDARD_NAME, PeriodKind.WEEK, None, False, DEFAULT_ORDER, None)


def test_validate_custom_accepts_up_to_400_days_and_rejects_the_rest() -> None:
    assert validate_custom(date(2026, 10, 1), date(2026, 10, 31)) is None
    assert validate_custom(date(2026, 1, 1), date(2027, 2, 4)) is None  # ちょうど 400 日
    assert "長すぎ" in (validate_custom(date(2026, 1, 1), date(2027, 2, 5)) or "")
    assert validate_custom(date(2026, 10, 31), date(2026, 10, 1)) is not None  # 逆順
    assert validate_custom(date(1999, 12, 31), date(2000, 1, 2)) is not None  # 年の範囲外
    assert validate_custom(date(2100, 12, 30), date(2101, 1, 2)) is not None


def test_normalize_cards_drops_unknown_and_duplicate_ids_but_keeps_order() -> None:
    assert normalize_cards(["due", "x", "team", "due", 3, None]) == (CardId.DUE, CardId.TEAM)
    assert normalize_cards([]) == ()  # 全部隠したビュー
    assert normalize_cards("team") == DEFAULT_ORDER  # リストでなければ既定の順
    assert normalize_cards(None) == DEFAULT_ORDER


def test_validate_name_rejects_empty_long_control_standard_and_duplicates() -> None:
    assert validate_name("週次", ["月次"]) is None
    assert validate_name("a" * MAX_VIEW_NAME, []) is None
    assert validate_name("", []) is not None
    assert validate_name("a" * (MAX_VIEW_NAME + 1), []) is not None
    assert validate_name("a\nb", []) is not None
    assert validate_name(STANDARD_NAME, []) is not None
    assert validate_name("月次", ["月次"]) is not None


def test_move_card_inserts_before_the_target_or_at_the_end() -> None:
    order = (CardId.TEAM, CardId.PROGRESS, CardId.LOAD)
    assert move_card(order, CardId.LOAD, CardId.TEAM) == (CardId.LOAD, CardId.TEAM, CardId.PROGRESS)
    assert move_card(order, CardId.TEAM, None) == (CardId.PROGRESS, CardId.LOAD, CardId.TEAM)
    assert move_card(order, CardId.TEAM, CardId.TEAM) == order  # 自分の手前は動かさない
    assert move_card(order, CardId.TEAM, CardId.DUE) == (CardId.PROGRESS, CardId.LOAD, CardId.TEAM)  # 隠れた手前は末尾


def test_move_card_shows_a_hidden_card_at_the_position() -> None:
    order = (CardId.TEAM, CardId.LOAD)
    assert move_card(order, CardId.DUE, CardId.LOAD) == (CardId.TEAM, CardId.DUE, CardId.LOAD)


def test_hide_and_show_card() -> None:
    order = (CardId.TEAM, CardId.LOAD)
    assert hide_card(order, CardId.TEAM) == (CardId.LOAD,)
    assert hide_card(order, CardId.DUE) == order
    assert show_card(order, CardId.DUE) == (CardId.TEAM, CardId.LOAD, CardId.DUE)
    assert show_card(order, CardId.TEAM) == order


def test_hidden_cards_skips_the_heatmap_unless_cross_is_on() -> None:
    order = (CardId.TEAM,)
    assert CardId.HEATMAP not in hidden_cards(order, cross=False)
    assert CardId.HEATMAP in hidden_cards(order, cross=True)
    assert hidden_cards(order, cross=True)[0] is CardId.PROGRESS  # 既定の順


def test_resolve_member_falls_back_to_everyone() -> None:
    assert resolve_member("田中", ["田中", "佐藤"]) == "田中"
    assert resolve_member("鈴木", ["田中"]) is None
    assert resolve_member(None, ["田中"]) is None


def test_parse_card_move_accepts_only_known_ids() -> None:
    assert parse_card_move({"card": "load", "before": "team"}) == (CardId.LOAD, CardId.TEAM)
    assert parse_card_move({"card": "load", "before": None}) == (CardId.LOAD, None)
    assert parse_card_move({"card": "x", "before": None}) is None
    assert parse_card_move({"card": "load", "before": "x"}) is None
    assert parse_card_move({"card": "load"}) == (CardId.LOAD, None)
    assert parse_card_move("load") is None
    assert parse_card_move(None) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_views.py -q`
Expected: FAIL(`ModuleNotFoundError: projectapp.dashboard_views`)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_views.py` を新規作成する:

```python
"""ダッシュボードのビュー(名前を付けた、期間・メンバー・横断・カードの組み合わせ)。NiceGUI に依存しない純粋関数。"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from projectapp.dashboard import Period, PeriodKind, custom_period_error
from projectapp.models import has_control_char
from projectapp.periodfield import validate_period

STANDARD_NAME = "標準"  # 組み込みのビュー。消せない・改名できない・上書きできない
MAX_VIEWS = 20  # `標準` を除く
MAX_VIEW_NAME = 30


class CardId(StrEnum):
    TEAM = "team"
    PROGRESS = "progress"
    LOAD = "load"
    HEATMAP = "heatmap"  # `負荷の日ごとの推移`。`全プロジェクト`がオンのときだけ描く
    HOURS = "hours"
    DUE = "due"


DEFAULT_ORDER: tuple[CardId, ...] = (
    CardId.TEAM, CardId.PROGRESS, CardId.LOAD, CardId.HEATMAP, CardId.HOURS, CardId.DUE,
)


@dataclass(frozen=True)
class ViewSpec:
    name: str
    period: PeriodKind
    member: str | None
    cross: bool
    cards: tuple[CardId, ...]  # 表示するカードを、並び順に
    custom: tuple[date, date] | None = None  # `period` が `指定` のときだけ。両端を含む


@dataclass(frozen=True)
class ViewState:
    """DashboardView に渡す、ツールバーとカードの状態。"""

    names: tuple[str, ...]  # `標準` を先頭に
    current: str
    dirty: bool
    save_block: str | None  # `保存` できない理由(できるときは None)
    cards: tuple[CardId, ...]
    hidden: tuple[CardId, ...]


def standard_view() -> ViewSpec:
    return ViewSpec(STANDARD_NAME, PeriodKind.WEEK, None, False, DEFAULT_ORDER, None)


def validate_custom(start: date, end: date) -> str | None:
    """`指定` の期間の不正な理由。問題なければ None。"""
    try:
        validate_period(start.isoformat(), end.isoformat())
    except ValueError as exc:
        return str(exc)
    return custom_period_error(Period(start, end))


def normalize_cards(cards: object) -> tuple[CardId, ...]:
    """未知の ID と重複を捨てる(順は保つ)。リストでなければ既定の順。"""
    if not isinstance(cards, list | tuple):
        return DEFAULT_ORDER
    result: list[CardId] = []
    for item in cards:
        try:
            card_id = CardId(item)
        except ValueError:
            continue
        if card_id not in result:
            result.append(card_id)
    return tuple(result)


def validate_name(name: str, taken: Iterable[str]) -> str | None:
    """ビューの名前(前後の空白を除いたもの)の不正な理由。問題なければ None。"""
    if not name:
        return "名前を入力してください"
    if len(name) > MAX_VIEW_NAME:
        return f"名前は{MAX_VIEW_NAME}文字以内で入力してください"
    if has_control_char(name):
        return "名前に改行・制御文字は使えません"
    if name == STANDARD_NAME or name in set(taken):
        return "同じ名前のビューがあります"
    return None


def move_card(cards: tuple[CardId, ...], card_id: CardId, before_id: CardId | None) -> tuple[CardId, ...]:
    """card_id を before_id の手前へ(before_id が None か、並びにないときは末尾へ)。隠れているカードは、その位置へ出る。"""
    if card_id == before_id:
        return cards
    rest = [c for c in cards if c != card_id]
    if before_id is None or before_id not in rest:
        return (*rest, card_id)
    index = rest.index(before_id)
    return (*rest[:index], card_id, *rest[index:])


def hide_card(cards: tuple[CardId, ...], card_id: CardId) -> tuple[CardId, ...]:
    return tuple(c for c in cards if c != card_id)


def show_card(cards: tuple[CardId, ...], card_id: CardId) -> tuple[CardId, ...]:
    return cards if card_id in cards else (*cards, card_id)


def hidden_cards(cards: tuple[CardId, ...], cross: bool) -> tuple[CardId, ...]:
    """隠れているカード(既定の順)。`負荷の日ごとの推移` は、横断がオフのあいだは数えない。"""
    return tuple(c for c in DEFAULT_ORDER if c not in cards and (cross or c is not CardId.HEATMAP))


def resolve_member(member: str | None, names: Iterable[str]) -> str | None:
    """保存したメンバーが今の名簿にいなければ、全員(None)。"""
    return member if member is not None and member in set(names) else None


def parse_card_move(args: object) -> tuple[CardId, CardId | None] | None:
    """ブラウザから来たカードの移動 `{"card": id, "before": id | None}` を読む。不正な値は None。"""
    if not isinstance(args, dict):
        return None
    try:
        card_id = CardId(args.get("card"))
        raw_before = args.get("before")
        before = None if raw_before is None else CardId(raw_before)
    except ValueError:
        return None
    return card_id, before
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_views.py -q`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_views.py test/test_dashboard_views.py
git commit -m "feat: ダッシュボードのビューの型と、検証・カード操作の純粋関数を足す"
```

---

### Task 2: `config.json` との変換と保存・読込

**Files:**
- Modify: `src/projectapp/dashboard_views.py`(末尾に変換を追加)
- Modify: `src/projectapp/config.py`
- Test: `test/test_dashboard_views.py`、`test/test_config.py`

**Interfaces:**
- Consumes: Task 1 の `ViewSpec`・`normalize_cards`・`validate_custom`・`validate_name`・`MAX_VIEWS`・`DEFAULT_ORDER`
- Produces:
  - `views_to_config(views: list[ViewSpec]) -> list[dict]`
  - `views_from_config(raw: object) -> list[ViewSpec]`
  - `config.load_dashboard_views(base_dir=BASE_DIR) -> list[ViewSpec]`、`config.save_dashboard_views(views, base_dir=BASE_DIR) -> None`
  - `config.load_dashboard_view_last(base_dir=BASE_DIR) -> str | None`、`config.save_dashboard_view_last(name, base_dir=BASE_DIR) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_views.py` に追加する(import に `MAX_VIEWS`・`views_from_config`・`views_to_config` を足す):

```python
def view(name: str = "月次", **changes: object) -> ViewSpec:
    base = ViewSpec(name, PeriodKind.MONTH, "田中", True, (CardId.LOAD, CardId.DUE), None)
    return replace(base, **changes)


def test_views_round_trip_including_a_custom_period() -> None:
    views = [view(), view("十月", period=PeriodKind.CUSTOM, custom=(date(2026, 10, 1), date(2026, 10, 31)), member=None)]
    assert views_from_config(views_to_config(views)) == views
    assert views_to_config(views)[1]["custom"] == {"start": "2026-10-01", "end": "2026-10-31"}
    assert "custom" not in views_to_config(views)[0]


def test_views_from_config_drops_only_the_bad_entries() -> None:
    good = views_to_config([view("月次")])[0]
    raw = [
        good,
        "x",
        {**good, "name": ""},
        {**good, "name": STANDARD_NAME},
        {**good, "name": "週", "period": "未知"},
        {**good, "name": "月次"},  # 重複は最初の 1 件だけ
        {**good, "name": "カード", "cards": ["due", "zzz", "due"]},
        {**good, "name": "文字列", "cards": "due"},
        {**good, "name": "メンバー", "member": 3, "cross": "yes"},
    ]
    views = views_from_config(raw)
    assert [v.name for v in views] == ["月次", "カード", "文字列", "メンバー"]
    assert views[1].cards == (CardId.DUE,)
    assert views[2].cards == DEFAULT_ORDER
    assert (views[3].member, views[3].cross) == (None, False)


def test_views_from_config_ignores_bad_dates_but_keeps_the_view() -> None:
    good = views_to_config([view("十月", period=PeriodKind.CUSTOM, custom=(date(2026, 10, 1), date(2026, 10, 31)))])[0]
    for custom in (
        {"start": "2026-10-31", "end": "2026-10-01"},  # 逆順
        {"start": "2026-01-01", "end": "2027-02-05"},  # 401 日
        {"start": "1999-01-01", "end": "1999-01-02"},  # 範囲外の年
        {"start": "x", "end": "y"},
        {"start": "2026-10-01"},
        "2026-10-01",
        None,
    ):
        (loaded,) = views_from_config([{**good, "custom": custom}])
        assert loaded.name == "十月" and loaded.period is PeriodKind.CUSTOM and loaded.custom is None
    month = views_to_config([view("月次")])[0]
    (loaded,) = views_from_config([{**month, "custom": {"start": "2026-10-01", "end": "2026-10-31"}}])
    assert loaded.custom is None  # `指定` 以外のビューは日付を持たない


def test_views_from_config_caps_the_count_and_rejects_non_lists() -> None:
    raw = [{**views_to_config([view("a")])[0], "name": f"v{i}"} for i in range(MAX_VIEWS + 5)]
    assert len(views_from_config(raw)) == MAX_VIEWS
    for bad in (None, "x", 3, {"a": 1}):
        assert views_from_config(bad) == []
```

(ファイル先頭の import に `from dataclasses import replace` を足す。)

`test/test_config.py` に追加する(import に `load_dashboard_view_last`・`load_dashboard_views`・`save_dashboard_view_last`・`save_dashboard_views` と、`from datetime import date`・`from projectapp.dashboard import PeriodKind`・`from projectapp.dashboard_views import CardId, ViewSpec` を足す):

```python
def test_dashboard_views_round_trip_and_keep_other_keys(tmp_path: Path) -> None:
    save_theme("dark", tmp_path)
    views = [ViewSpec("月次", PeriodKind.MONTH, "田中", True, (CardId.LOAD,), None)]
    save_dashboard_views(views, tmp_path)
    save_dashboard_view_last("月次", tmp_path)
    assert load_dashboard_views(tmp_path) == views
    assert load_dashboard_view_last(tmp_path) == "月次"
    assert load_theme(tmp_path) == "dark"


def test_dashboard_views_default_to_empty_when_missing_or_unreadable(tmp_path: Path) -> None:
    assert load_dashboard_views(tmp_path) == []
    assert load_dashboard_view_last(tmp_path) is None
    (tmp_path / "config.json").write_text("{broken", encoding="utf-8")
    assert load_dashboard_views(tmp_path) == []
    assert load_dashboard_view_last(tmp_path) is None
    (tmp_path / "config.json").write_text(json.dumps({"dashboard_views": 3, "dashboard_view_last": 4}), encoding="utf-8")
    assert load_dashboard_views(tmp_path) == []
    assert load_dashboard_view_last(tmp_path) is None
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_views.py test/test_config.py -q`
Expected: FAIL(`views_from_config` などが未定義)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_views.py` の import に `from datetime import date` はあるので、`import` 行に次を足し、末尾に変換を追加する:

```python
def views_to_config(views: list[ViewSpec]) -> list[dict]:
    result = []
    for spec in views:
        entry: dict = {
            "name": spec.name,
            "period": spec.period.value,
            "member": spec.member,
            "cross": spec.cross,
            "cards": [c.value for c in spec.cards],
        }
        if spec.custom is not None:
            entry["custom"] = {"start": spec.custom[0].isoformat(), "end": spec.custom[1].isoformat()}
        result.append(entry)
    return result


def custom_from_config(raw: object) -> tuple[date, date] | None:
    """`custom` の値(`{"start", "end"}`)を読む。読めない・不正な期間は None。"""
    if not isinstance(raw, dict):
        return None
    try:
        start = date.fromisoformat(raw["start"])
        end = date.fromisoformat(raw["end"])
    except (KeyError, TypeError, ValueError):
        return None
    return None if validate_custom(start, end) else (start, end)


def view_from_config(raw: object) -> ViewSpec | None:
    """1 件のビューを読む。名前か期間が不正なら None(その件だけ捨てる)。それ以外の不正な値は補う。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    name = raw["name"].strip()
    if validate_name(name, ()):
        return None
    try:
        period = PeriodKind(raw.get("period"))
    except ValueError:
        return None
    member = raw.get("member")
    cross = raw.get("cross")
    custom = custom_from_config(raw.get("custom")) if period is PeriodKind.CUSTOM else None
    return ViewSpec(
        name,
        period,
        member if isinstance(member, str) and member else None,
        cross if isinstance(cross, bool) else False,
        normalize_cards(raw.get("cards")),
        custom,
    )


def views_from_config(raw: object) -> list[ViewSpec]:
    """`config.json` の `dashboard_views` を読む。不正な件だけ捨て、同名は最初の 1 件を残し、20 件までにする。"""
    if not isinstance(raw, list):
        return []
    views: list[ViewSpec] = []
    for item in raw:
        spec = view_from_config(item)
        if spec is None or spec.name in {v.name for v in views}:
            continue
        views.append(spec)
        if len(views) >= MAX_VIEWS:
            break
    return views
```

`src/projectapp/config.py` に追加する(import に `from projectapp.dashboard_views import ViewSpec, views_from_config, views_to_config` を足し、`load_name_width` の近くに置く):

```python
def load_dashboard_views(base_dir: Path = BASE_DIR) -> list[ViewSpec]:
    """保存したダッシュボードのビュー(`標準` を含まない)。読めないときは空。"""
    try:
        raw = read_config(base_dir).get("dashboard_views")
    except (OSError, ValueError):
        return []
    return views_from_config(raw)


def save_dashboard_views(views: list[ViewSpec], base_dir: Path = BASE_DIR) -> None:
    update_config({"dashboard_views": views_to_config(views)}, base_dir)


def load_dashboard_view_last(base_dir: Path = BASE_DIR) -> str | None:
    """最後に使ったダッシュボードのビューの名前。読めないときは None。"""
    try:
        name = read_config(base_dir).get("dashboard_view_last")
    except (OSError, ValueError):
        return None
    return name if isinstance(name, str) and name else None


def save_dashboard_view_last(name: str, base_dir: Path = BASE_DIR) -> None:
    update_config({"dashboard_view_last": name}, base_dir)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_views.py test/test_config.py -q`
Expected: PASS(循環 import でエラーになったら、`config.py` の import を関数内に移す)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_views.py src/projectapp/config.py test/test_dashboard_views.py test/test_config.py
git commit -m "feat: ダッシュボードのビューを config.json に保存・読込できるようにする"
```

---

### Task 3: `DashboardView` がカードを順序表で描く

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`show`・`cards`・`__init__`)
- Test: `test/test_dashboard_view.py`

**Interfaces:**
- Consumes: Task 1 の `CardId`・`DEFAULT_ORDER`・`ViewState`
- Produces: `DashboardView.show(data, kind, icons=None, custom_text=None, custom_error="", view_state: ViewState | None = None)`(`view_state` が None のあいだは既定の順で全カード = 今の動き)。`DashboardView.card_order: tuple[CardId, ...]`、`DashboardView.state: ViewState | None`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` に追加する(import に `from projectapp.dashboard_views import CardId, ViewState` を足す):

```python
def state(cards: tuple[CardId, ...]) -> ViewState:
    return ViewState(("標準",), "標準", False, None, cards, ())


async def test_cards_follow_the_view_order_and_skip_hidden_ones(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=state((CardId.DUE, CardId.HOURS)))
    await user.should_see(marker="dashboard-due-0")
    await user.should_see(marker="dashboard-hours-total")
    await user.should_not_see(marker="dashboard-progress-percent")
    await user.should_not_see(marker="dashboard-team")
    assert views[0].card_order == (CardId.DUE, CardId.HOURS)  # 描く順は card_order のとおり

async def test_without_a_view_state_all_cards_show_in_the_default_order(user: User) -> None:
    views, _, _ = mount()
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK)
    await user.should_see(marker="dashboard-progress-percent")
    assert views[0].card_order == DEFAULT_ORDER
```

(import に `DEFAULT_ORDER` も足す。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_view.py -q -k "view_order or without_a_view_state"`
Expected: FAIL(`show()` が `view_state` を受け取らない)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_view.py`:

import に `from projectapp.dashboard_views import DEFAULT_ORDER, CardId, ViewState` を足す。

`__init__` の末尾(`self.syncing = False` の次)に:

```python
        self.state: ViewState | None = None  # ビューの選択・カードの並び。None のあいだは既定の順で全部出す
        self.card_order: tuple[CardId, ...] = DEFAULT_ORDER
```

`show` のシグネチャに `view_state: ViewState | None = None` を足し、`self.data = data` の次に:

```python
        self.state = view_state
        self.card_order = view_state.cards if view_state is not None else DEFAULT_ORDER
```

`cards()` を次に置き換える:

```python
    @ui.refreshable_method
    def cards(self) -> None:
        data = self.data
        if data is None:
            return
        builders = {
            CardId.TEAM: self.team_card,
            CardId.PROGRESS: self.progress_card,
            CardId.LOAD: self.load_card,
            CardId.HEATMAP: self.heatmap_card,
            CardId.HOURS: self.hours_card,
            CardId.DUE: self.due_card,
        }
        with ui.element("div").style(GRID_STYLE):
            for card_id in self.card_order:
                builders[card_id](data)
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_view.py -q`
Expected: PASS(既存テストも全部通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_view.py test/test_dashboard_view.py
git commit -m "feat: ダッシュボードのカードを、ビューの順序表で描く"
```

---

### Task 4: `MainView` のビューの状態と操作(切り替え・保存・改名・削除・永続化)

**Files:**
- Modify: `src/projectapp/views.py`(import・`__init__`・`open_dashboard`・`refresh_dashboard`・`change_dashboard_period`・新メソッド)
- Test: `test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の型と関数、Task 2 の `load/save_*`、Task 3 の `show(..., view_state=)`、既存の `forms.open_name_dialog`・`forms.open_confirm_dialog`
- Produces(Task 5・6 が使う): `MainView` の
  - 状態: `dashboard_views: list[ViewSpec]`、`dashboard_view_name: str`、`dashboard_cards: tuple[CardId, ...]`、`dashboard_names: list[str]`
  - `working_spec(name) -> ViewSpec`、`dashboard_dirty() -> bool`、`dashboard_view_state() -> ViewState`
  - ハンドラ: `select_dashboard_view(name)`、`save_dashboard_view()`、`save_dashboard_view_as()`、`revert_dashboard_view()`、`rename_dashboard_view()`、`delete_dashboard_view()`、`move_dashboard_card(card_id, before_id)`、`hide_dashboard_card(card_id)`、`show_dashboard_card(card_id)`

- [ ] **Step 1: 失敗するテストを書く**

`test/test_views.py` の `open_dashboard_view` の近くに追加する(import に `load_dashboard_view_last`・`load_dashboard_views`・`save_dashboard_view_last`・`save_dashboard_views`、`from projectapp.dashboard_views import STANDARD_NAME, CardId, ViewSpec` を足す):

```python
async def open_dashboard(user: User, view: MainView) -> None:
    user.find(marker="open-dashboard").click()
    await user.should_see(marker="dashboard-load-田中")


async def test_opening_the_dashboard_applies_the_standard_view(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    assert view.dashboard_view_name == STANDARD_NAME
    assert view.dashboard_kind is PeriodKind.WEEK and view.dashboard_cards == DEFAULT_ORDER
    assert view.dashboard_dirty() is False


async def test_changing_a_condition_marks_the_view_dirty_and_changing_it_back_clears_it(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.change_dashboard_period(PeriodKind.MONTH)
    assert view.dashboard_dirty() is True
    view.change_dashboard_period(PeriodKind.WEEK)
    assert view.dashboard_dirty() is False
    view.hide_dashboard_card(CardId.DUE)
    assert view.dashboard_dirty() is True


async def test_save_as_creates_a_view_persists_it_and_remembers_it_as_the_last(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.change_dashboard_period(PeriodKind.MONTH)
    view.hide_dashboard_card(CardId.DUE)
    view.save_dashboard_view_as()
    user.find(marker="project-name").type("月次")
    user.find(marker="name-save").click()
    assert view.dashboard_view_name == "月次" and view.dashboard_dirty() is False
    (saved,) = load_dashboard_views(tmp_path)
    assert (saved.name, saved.period, CardId.DUE in saved.cards) == ("月次", PeriodKind.MONTH, False)
    assert load_dashboard_view_last(tmp_path) == "月次"


async def test_save_as_rejects_a_duplicate_and_the_standard_name(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("月次", PeriodKind.MONTH, None, False, DEFAULT_ORDER)], tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.save_dashboard_view_as()
    for name in ("月次", STANDARD_NAME, ""):
        user.find(marker="project-name").type(name)
        user.find(marker="name-save").click()
        await user.should_see(marker="name-error")
    assert [v.name for v in load_dashboard_views(tmp_path)] == ["月次"]


async def test_selecting_a_view_applies_it_and_discards_unsaved_changes(user: User, tmp_path: Path) -> None:
    save_dashboard_views(
        [ViewSpec("田中だけ", PeriodKind.ALL, "田中", False, (CardId.LOAD,))], tmp_path
    )
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.hide_dashboard_card(CardId.TEAM)  # 作業中の変更
    view.select_dashboard_view("田中だけ")
    assert (view.dashboard_kind, view.dashboard_member, view.dashboard_cards) == (PeriodKind.ALL, "田中", (CardId.LOAD,))
    assert view.dashboard_dirty() is False
    assert load_dashboard_view_last(tmp_path) == "田中だけ"
    view.select_dashboard_view(STANDARD_NAME)
    assert view.dashboard_cards == DEFAULT_ORDER and view.dashboard_member is None


async def test_the_last_used_view_opens_next_time(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("田中だけ", PeriodKind.ALL, "田中", False, DEFAULT_ORDER)], tmp_path)
    save_dashboard_view_last("田中だけ", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    assert view.dashboard_view_name == "田中だけ" and view.dashboard_kind is PeriodKind.ALL


async def test_an_unknown_last_view_falls_back_to_standard(user: User, tmp_path: Path) -> None:
    save_dashboard_view_last("消えた", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    assert view.dashboard_view_name == STANDARD_NAME


async def test_a_saved_member_who_is_gone_shows_everyone_without_a_dirty_mark(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("鈴木だけ", PeriodKind.WEEK, "鈴木", False, DEFAULT_ORDER)], tmp_path)
    save_dashboard_view_last("鈴木だけ", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    assert view.dashboard_member is None
    assert view.dashboard_dirty() is False
    assert load_dashboard_views(tmp_path)[0].member == "鈴木"  # ビューは書き換えない


async def test_a_custom_view_opens_with_its_dates(user: User, tmp_path: Path) -> None:
    custom = (date(2026, 9, 1), date(2026, 9, 30))
    save_dashboard_views([ViewSpec("九月", PeriodKind.CUSTOM, None, False, DEFAULT_ORDER, custom)], tmp_path)
    save_dashboard_view_last("九月", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    assert view.dashboard_custom == Period(*custom)
    assert view.dashboard_dirty() is False
    assert view.working_spec("九月").custom == custom


async def test_a_custom_view_without_dates_starts_from_the_previous_period(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("日付なし", PeriodKind.CUSTOM, None, False, DEFAULT_ORDER, None)], tmp_path)
    save_dashboard_view_last("日付なし", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    assert view.dashboard_kind is PeriodKind.CUSTOM and view.dashboard_custom is not None


async def test_saving_is_blocked_while_the_custom_field_has_an_error(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.change_dashboard_period(PeriodKind.CUSTOM)
    view.change_dashboard_custom("x")
    assert view.dashboard_view_state().save_block is not None
    view.save_dashboard_view_as()
    await user.should_see("期間")  # 理由の通知。ダイアログは開かない
    await user.should_not_see(marker="project-name")
    assert load_dashboard_views(tmp_path) == []


async def test_save_overwrites_a_custom_view_but_not_the_standard_one(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("月次", PeriodKind.MONTH, None, False, DEFAULT_ORDER)], tmp_path)
    save_dashboard_view_last("月次", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.hide_dashboard_card(CardId.DUE)
    view.save_dashboard_view()
    assert CardId.DUE not in load_dashboard_views(tmp_path)[0].cards
    view.select_dashboard_view(STANDARD_NAME)
    view.hide_dashboard_card(CardId.DUE)
    assert view.dashboard_view_state().save_block is not None
    view.save_dashboard_view()
    assert [v.name for v in load_dashboard_views(tmp_path)] == ["月次"]


async def test_revert_restores_the_saved_view(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.change_dashboard_period(PeriodKind.MONTH)
    view.hide_dashboard_card(CardId.TEAM)
    view.revert_dashboard_view()
    assert view.dashboard_kind is PeriodKind.WEEK and view.dashboard_cards == DEFAULT_ORDER


async def test_rename_and_delete(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("月次", PeriodKind.MONTH, None, False, DEFAULT_ORDER)], tmp_path)
    save_dashboard_view_last("月次", tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.rename_dashboard_view()
    user.find(marker="project-name").clear().type("毎月")
    user.find(marker="name-save").click()
    assert view.dashboard_view_name == "毎月"
    assert [v.name for v in load_dashboard_views(tmp_path)] == ["毎月"]
    assert load_dashboard_view_last(tmp_path) == "毎月"
    view.delete_dashboard_view()
    await user.should_see("「毎月」を削除しますか?")
    user.find(marker="confirm-ok").click()
    assert view.dashboard_view_name == STANDARD_NAME
    assert load_dashboard_views(tmp_path) == []
    assert load_dashboard_view_last(tmp_path) == STANDARD_NAME


async def test_the_standard_view_cannot_be_renamed_or_deleted(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.rename_dashboard_view()
    view.delete_dashboard_view()
    await user.should_not_see(marker="project-name")
    await user.should_not_see(marker="confirm-ok")


async def test_the_view_limit_is_enforced(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec(f"v{i}", PeriodKind.WEEK, None, False, DEFAULT_ORDER) for i in range(20)], tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.save_dashboard_view_as()
    user.find(marker="project-name").type("21 件目")
    user.find(marker="name-save").click()
    await user.should_see(marker="name-error")
    assert len(load_dashboard_views(tmp_path)) == 20


async def test_a_failed_write_notifies_and_keeps_the_view_in_memory(user: User, tmp_path: Path, monkeypatch) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("projectapp.views.save_dashboard_views", boom)
    view.change_dashboard_period(PeriodKind.MONTH)
    view.save_dashboard_view_as()
    user.find(marker="project-name").type("月次")
    user.find(marker="name-save").click()
    await user.should_see("保存できませんでした")
    assert view.dashboard_view_name == "月次" and [v.name for v in view.dashboard_views] == ["月次"]


async def test_card_moves_change_the_order_and_ignore_nonsense(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.move_dashboard_card(CardId.DUE, CardId.TEAM)
    assert view.dashboard_cards[0] is CardId.DUE
    view.hide_dashboard_card(CardId.DUE)
    assert CardId.DUE not in view.dashboard_cards
    view.show_dashboard_card(CardId.DUE)
    assert view.dashboard_cards[-1] is CardId.DUE
```

(`DEFAULT_ORDER`・`Period` を import に足す。`user.find(...).clear()` が使えなければ、既存の改名テスト〔`rename_task` のテスト〕と同じ書き方に合わせる。)

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_views.py -q -k "dashboard or custom_view or saved_member or last_used or view_limit or card_moves"`
Expected: FAIL(`AttributeError: 'MainView' object has no attribute 'dashboard_cards'` など)

- [ ] **Step 3: 実装する**

`src/projectapp/views.py`:

(a) import を足す(既存の `from projectapp.config import (...)` に `load_dashboard_view_last`・`load_dashboard_views`・`save_dashboard_view_last`・`save_dashboard_views` を、`from projectapp.dashboard_view import DashboardView` の次に下を):

```python
from projectapp.dashboard_views import (
    DEFAULT_ORDER,
    MAX_VIEWS,
    STANDARD_NAME,
    CardId,
    ViewSpec,
    ViewState,
    hidden_cards,
    hide_card,
    move_card,
    resolve_member,
    show_card,
    standard_view,
    validate_name,
)
```

(b) `__init__` の `self.dashboard_excluded` の次に:

```python
        self.dashboard_views = load_dashboard_views(base_dir)  # 保存したビュー(`標準` を含まない)。全プロジェクト共通
        self.dashboard_view_name = load_dashboard_view_last(base_dir) or STANDARD_NAME  # 最後に使ったビュー
        self.dashboard_cards: tuple[CardId, ...] = DEFAULT_ORDER  # 表示するカードの並び。保存するのはビューにしたときだけ
        self.dashboard_names: list[str] = []  # 今の名簿(refresh のたびに更新)。保存したメンバーが残っているかの判定に使う
```

(c) `open_dashboard` の本体を置き換える:

```python
        self.dashboard_kind = PeriodKind.WEEK
        self.dashboard_custom = None
        self.dashboard_custom_error = ""
        self.set_header_visible(False)
        self.gantt.set_visible(False)
        self.apply_dashboard_view(self.saved_dashboard_view(self.dashboard_view_name))
        self.refresh_dashboard()
```

(d) `refresh_dashboard` の `if self.dashboard_member not in names:` の直前に `self.dashboard_names = names` を足し、最後の `self.dashboard_view.show(...)` に `view_state=self.dashboard_view_state()` を足す。

(e) `change_dashboard_period` の `if kind is PeriodKind.CUSTOM:` ブロックを、共通の補助に切り出す:

```python
    def starting_custom_period(self) -> Period:
        """`指定` を始めるときの期間 = 直前に見ていた期間。全期間が長いときは、終わりの側の上限の長さに切る。"""
        previous = period_for(
            self.dashboard_kind or PeriodKind.WEEK, self.now().date(), self.project, self.holidays, self.dashboard_custom
        )
        if custom_period_error(previous):
            previous = Period(previous.end - timedelta(days=MAX_CUSTOM_DAYS - 1), previous.end)
        return previous
```

`change_dashboard_period` 側は `if kind is PeriodKind.CUSTOM: self.dashboard_custom = self.starting_custom_period()` にする。

(f) ビューの状態と操作を `close_dashboard` の前に追加する:

```python
    def saved_dashboard_view(self, name: str) -> ViewSpec:
        """保存済みのビュー。名前がなければ `標準`。"""
        return next((v for v in self.dashboard_views if v.name == name), standard_view())

    def working_spec(self, name: str) -> ViewSpec:
        """今の画面の条件とカードの並びを、ビューの形にしたもの。"""
        custom = None
        if self.dashboard_kind is PeriodKind.CUSTOM and self.dashboard_custom is not None and not self.dashboard_custom_error:
            custom = (self.dashboard_custom.start, self.dashboard_custom.end)
        return ViewSpec(
            name,
            self.dashboard_kind or PeriodKind.WEEK,
            self.dashboard_member,
            self.dashboard_cross,
            self.dashboard_cards,
            custom,
        )

    def dashboard_dirty(self) -> bool:
        """保存したビューと違うか。保存したメンバーがいないときは、全員に戻した状態を同じとみなす。"""
        saved = self.saved_dashboard_view(self.dashboard_view_name)
        saved = replace(saved, member=resolve_member(saved.member, self.dashboard_names))
        return self.working_spec(saved.name) != saved

    def custom_save_block(self) -> str | None:
        if self.dashboard_kind is PeriodKind.CUSTOM and (self.dashboard_custom_error or self.dashboard_custom is None):
            return "期間の欄を直してください"
        return None

    def dashboard_save_block(self) -> str | None:
        """`保存` できない理由。`標準` は上書きできない。"""
        if self.dashboard_view_name == STANDARD_NAME:
            return "「標準」は上書きできません。名前をつけて保存してください"
        return self.custom_save_block()

    def dashboard_view_state(self) -> ViewState:
        return ViewState(
            (STANDARD_NAME, *(v.name for v in self.dashboard_views)),
            self.dashboard_view_name,
            self.dashboard_dirty(),
            self.dashboard_save_block(),
            self.dashboard_cards,
            hidden_cards(self.dashboard_cards, self.dashboard_cross),
        )

    def apply_dashboard_view(self, spec: ViewSpec) -> None:
        """ビューの条件とカードの並びを、画面の状態に取り込む(集計し直さない)。除外したプロジェクトは空に戻る。"""
        self.dashboard_view_name = spec.name
        self.dashboard_kind = spec.period
        if spec.period is PeriodKind.CUSTOM:
            self.dashboard_custom = Period(*spec.custom) if spec.custom is not None else self.starting_custom_period()
        self.dashboard_custom_error = ""
        self.dashboard_member = spec.member
        self.dashboard_cross = spec.cross
        self.dashboard_excluded = set()
        self.dashboard_cards = spec.cards

    def persist_dashboard(self, *, views: bool = False, last: bool = False) -> None:
        """設定に書く。書けなくても、画面上のビューは使い続ける(通知だけ出す)。"""
        try:
            if views:
                save_dashboard_views(self.dashboard_views, self.base_dir)
            if last:
                save_dashboard_view_last(self.dashboard_view_name, self.base_dir)
        except OSError:
            ui.notify("ダッシュボードのビューを保存できませんでした(この画面では使い続けられます)")

    def select_dashboard_view(self, name: str) -> None:
        if self.dashboard_kind is None or (name != STANDARD_NAME and all(v.name != name for v in self.dashboard_views)):
            return
        self.apply_dashboard_view(self.saved_dashboard_view(name))
        self.persist_dashboard(last=True)
        self.refresh_dashboard()

    def save_dashboard_view(self) -> None:
        if self.dashboard_kind is None:
            return
        if reason := self.dashboard_save_block():
            ui.notify(reason)
            return
        name = self.dashboard_view_name
        self.dashboard_views = [self.working_spec(name) if v.name == name else v for v in self.dashboard_views]
        self.persist_dashboard(views=True)
        self.refresh_dashboard()
        ui.notify(f"ビュー「{name}」を保存しました")

    def save_dashboard_view_as(self) -> None:
        if self.dashboard_kind is None:
            return
        if reason := self.custom_save_block():
            ui.notify(reason)
            return

        def validate(clean: str) -> str | None:
            if len(self.dashboard_views) >= MAX_VIEWS:
                return f"ビューは{MAX_VIEWS}件までです"
            return validate_name(clean, (v.name for v in self.dashboard_views))

        def apply(name: str) -> None:
            self.dashboard_views = [*self.dashboard_views, self.working_spec(name)]
            self.dashboard_view_name = name
            self.persist_dashboard(views=True, last=True)
            self.refresh_dashboard()

        open_name_dialog(apply, validate, title="ビューの保存", label="ビュー名")

    def revert_dashboard_view(self) -> None:
        if self.dashboard_kind is None:
            return
        self.apply_dashboard_view(self.saved_dashboard_view(self.dashboard_view_name))
        self.refresh_dashboard()

    def rename_dashboard_view(self) -> None:
        old = self.dashboard_view_name
        if self.dashboard_kind is None or old == STANDARD_NAME:
            return

        def apply(name: str) -> None:
            self.dashboard_views = [replace(v, name=name) if v.name == old else v for v in self.dashboard_views]
            self.dashboard_view_name = name
            self.persist_dashboard(views=True, last=True)
            self.refresh_dashboard()

        others = [v.name for v in self.dashboard_views if v.name != old]
        open_name_dialog(
            apply, lambda clean: validate_name(clean, others), title="ビュー名の変更", initial=old, label="ビュー名"
        )

    def delete_dashboard_view(self) -> None:
        name = self.dashboard_view_name
        if self.dashboard_kind is None or name == STANDARD_NAME:
            return

        def apply() -> None:
            self.dashboard_views = [v for v in self.dashboard_views if v.name != name]
            self.apply_dashboard_view(standard_view())
            self.persist_dashboard(views=True, last=True)
            self.refresh_dashboard()

        open_confirm_dialog(f"ビュー「{name}」を削除しますか?", apply)

    def move_dashboard_card(self, card_id: CardId, before_id: CardId | None) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cards = move_card(self.dashboard_cards, card_id, before_id)
        self.refresh_dashboard()

    def hide_dashboard_card(self, card_id: CardId) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cards = hide_card(self.dashboard_cards, card_id)
        self.refresh_dashboard()

    def show_dashboard_card(self, card_id: CardId) -> None:
        if self.dashboard_kind is None:
            return
        self.dashboard_cards = show_card(self.dashboard_cards, card_id)
        self.refresh_dashboard()
```

(`open_name_dialog`・`open_confirm_dialog` は `views.py` で既に import 済みか確認し、なければ `from projectapp.forms import ...` に足す。`replace` は既に import 済み〔`refresh_dashboard` が使っている〕。)

注意: `refresh_dashboard` は `dashboard_names` を更新する。`open_dashboard` の `apply_dashboard_view` 直後の `dashboard_dirty()` は、`refresh_dashboard` の中(`show` に渡す前)で呼ばれるので、名簿は更新済み。

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_views.py -q -k "dashboard or custom_view or saved_member or last_used or view_limit or card_moves"` を実行し、続けて `uv run pytest test/test_views.py test/test_dashboard_view.py -q -n auto`
Expected: PASS(既存のダッシュボードのテストも通る)

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/views.py test/test_views.py
git commit -m "feat: ダッシュボードのビューの切り替え・保存・改名・削除を MainView に足す"
```

---

### Task 5: ツールバー(ビューの選択・`●`・操作)

**Files:**
- Modify: `src/projectapp/dashboard_view.py`(`ViewActions`・`build`・`show`)
- Modify: `src/projectapp/views.py`(`DashboardView(...)` の生成に `actions=` を渡す)
- Test: `test/test_dashboard_view.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 3 の `show(view_state=)`、Task 4 の `MainView` ハンドラ
- Produces: `@dataclass class ViewActions`(`select: Callable[[str], object]`・`save`・`save_as`・`revert`・`rename`・`delete`: `Callable[[], object]`・`move_card: Callable[[CardId, CardId | None], object]`・`hide_card: Callable[[CardId], object]`・`show_card: Callable[[CardId], object]`)。`DashboardView(..., actions: ViewActions | None = None)`。マーカー: `dashboard-view`(プルダウン)・`dashboard-view-dirty`(`●`)・`dashboard-view-save`・`dashboard-view-save-as`・`dashboard-view-revert`・`dashboard-view-menu`・`dashboard-view-rename`・`dashboard-view-delete`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_view.py` に追加する(import に `ViewActions` を足す)。`mount` に `actions` を渡せるよう、引数 `actions: ViewActions | None = None` を足して `DashboardView(..., actions=actions)` に渡す:

```python
def full_state(
    current: str = "標準", dirty: bool = False, save_block: str | None = None, names: tuple[str, ...] = ("標準", "月次")
) -> ViewState:
    return ViewState(names, current, dirty, save_block, DEFAULT_ORDER, ())


def recording_actions(log: list) -> ViewActions:
    return ViewActions(
        select=lambda name: log.append(("select", name)),
        save=lambda: log.append("save"),
        save_as=lambda: log.append("save_as"),
        revert=lambda: log.append("revert"),
        rename=lambda: log.append("rename"),
        delete=lambda: log.append("delete"),
        move_card=lambda card_id, before: log.append(("move", card_id, before)),
        hide_card=lambda card_id: log.append(("hide", card_id)),
        show_card=lambda card_id: log.append(("show", card_id)),
    )


async def test_the_toolbar_shows_the_dirty_mark_and_save_buttons_only_when_dirty(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(dirty=False))
    await user.should_see(marker="dashboard-view")
    await user.should_see(marker="dashboard-view-save-as")  # 名前をつけて保存は常に出す
    await user.should_not_see(marker="dashboard-view-dirty")
    await user.should_not_see(marker="dashboard-view-save")
    await user.should_not_see(marker="dashboard-view-revert")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True))
    await user.should_see(marker="dashboard-view-dirty")
    await user.should_see(marker="dashboard-view-save")
    await user.should_see(marker="dashboard-view-revert")


async def test_save_is_disabled_with_a_reason_when_blocked(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(dirty=True, save_block="「標準」は上書きできません"))
    await user.should_see(marker="dashboard-view-save")
    save = user.find(marker="dashboard-view-save").elements.pop()
    assert save.enabled is False


async def test_toolbar_buttons_call_the_actions(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次", dirty=True))
    await user.should_see(marker="dashboard-view-save")
    user.find(marker="dashboard-view-save").click()
    user.find(marker="dashboard-view-save-as").click()
    user.find(marker="dashboard-view-revert").click()
    assert log == ["save", "save_as", "revert"]


async def test_selecting_in_the_dropdown_calls_select_but_syncing_does_not(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state())
    await user.should_see(marker="dashboard-view")
    assert log == []  # show でプルダウンの値を合わせても、選択の通知は出ない
    views[0].view_select.set_value("月次")
    assert log == [("select", "月次")]


async def test_rename_and_delete_are_disabled_for_the_standard_view(user: User) -> None:
    views, _, _ = mount(actions=recording_actions([]))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="標準"))
    assert views[0].rename_item.enabled is False and views[0].delete_item.enabled is False
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state(current="月次"))
    assert views[0].rename_item.enabled is True and views[0].delete_item.enabled is True
```

`test/test_views.py` に結合テストを足す:

```python
async def test_the_toolbar_select_switches_the_view(user: User, tmp_path: Path) -> None:
    save_dashboard_views([ViewSpec("田中だけ", PeriodKind.ALL, "田中", False, (CardId.LOAD,))], tmp_path)
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    view.dashboard_view.view_select.set_value("田中だけ")
    assert view.dashboard_view_name == "田中だけ"
    await user.should_not_see(marker="dashboard-progress-percent")  # カードの並びも切り替わる
    await user.should_see(marker="dashboard-load-田中")


async def test_a_condition_change_shows_the_dirty_mark(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    await user.should_not_see(marker="dashboard-view-dirty")
    view.change_dashboard_period(PeriodKind.MONTH)
    await user.should_see(marker="dashboard-view-dirty")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_view.py test/test_views.py -q -k "toolbar or dirty or rename_and_delete_are or save_is_disabled or syncing"`
Expected: FAIL(`ViewActions` が未定義)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_view.py`:

import に `from dataclasses import dataclass` を足す。クラス定義の前に:

```python
@dataclass
class ViewActions:
    """ビューの操作。MainView が渡す。"""

    select: Callable[[str], object]
    save: Callable[[], object]
    save_as: Callable[[], object]
    revert: Callable[[], object]
    rename: Callable[[], object]
    delete: Callable[[], object]
    move_card: Callable[[CardId, CardId | None], object]
    hide_card: Callable[[CardId], object]
    show_card: Callable[[CardId], object]
```

`__init__` に引数 `actions: ViewActions | None = None` を足し(`on_custom_change` の次)、本体に:

```python
        self.actions = actions
        self.view_select: ui.select | None = None
        self.dirty_mark: ui.label | None = None
        self.save_button: ui.button | None = None
        self.revert_button: ui.button | None = None
        self.rename_item: ui.menu_item | None = None
        self.delete_item: ui.menu_item | None = None
```

`build()` の `ui.label("ダッシュボード")...` の直後(トグルの前)に挿入する:

```python
                with ui.row().classes("items-center gap-1 no-wrap"):
                    self.view_select = (
                        ui.select({STANDARD_NAME: STANDARD_NAME}, value=STANDARD_NAME, on_change=self.on_view)
                        .props("dense outlined options-dense")
                        .style("min-width: 8rem")
                        .mark("dashboard-view")
                    )
                    self.dirty_mark = (
                        ui.label("●").classes("text-warning").tooltip("保存していない変更があります").mark("dashboard-view-dirty")
                    )
                    self.save_button = (
                        ui.button("保存", on_click=lambda: self.act("save")).props("flat dense").mark("dashboard-view-save")
                    )
                    ui.button("名前をつけて保存", on_click=lambda: self.act("save_as")).props("flat dense").mark(
                        "dashboard-view-save-as"
                    )
                    self.revert_button = (
                        ui.button("元に戻す", on_click=lambda: self.act("revert")).props("flat dense").mark("dashboard-view-revert")
                    )
                    with ui.button(icon="more_vert").props("flat dense round").mark("dashboard-view-menu"):
                        with ui.menu():
                            self.rename_item = ui.menu_item("名前の変更", on_click=lambda: self.act("rename")).mark(
                                "dashboard-view-rename"
                            )
                            self.delete_item = ui.menu_item("削除", on_click=lambda: self.act("delete")).mark(
                                "dashboard-view-delete"
                            )
```

(import に `from projectapp.dashboard_views import STANDARD_NAME` を足す。)

メソッドを足す:

```python
    def act(self, name: str, *args: object) -> None:
        """MainView の操作を呼ぶ。actions がないとき(単体のテスト)は何もしない。"""
        if self.actions is not None:
            getattr(self.actions, name)(*args)

    def on_view(self, event: ValueChangeEventArguments) -> None:
        if not self.syncing and event.value:
            self.act("select", event.value)

    def sync_toolbar(self) -> None:
        """ビューの選択・`●`・ボタンの有効/無効を、状態に合わせる(通知は出さない)。"""
        state = self.state
        if state is None or self.view_select is None:
            return
        self.syncing = True
        try:
            self.view_select.set_options({name: name for name in state.names}, value=state.current)
        finally:
            self.syncing = False
        if self.dirty_mark is not None:
            self.dirty_mark.set_visibility(state.dirty)
        if self.save_button is not None:
            self.save_button.set_visibility(state.dirty)
            self.save_button.set_enabled(state.save_block is None)
            if state.save_block is not None:
                self.save_button.tooltip(state.save_block)
        if self.revert_button is not None:
            self.revert_button.set_visibility(state.dirty)
        standard = state.current == STANDARD_NAME
        for item in (self.rename_item, self.delete_item):
            if item is not None:
                item.set_enabled(not standard)
```

`show()` の `self.card_order = ...` の次に `self.sync_toolbar()` を呼ぶ。`build()` の最後の `box.set_visibility(False)` の前に、初期状態として `self.dirty_mark.set_visibility(False); self.save_button.set_visibility(False); self.revert_button.set_visibility(False)` を足す。

`src/projectapp/views.py`: `DashboardView(...)` の生成(`self.change_dashboard_custom,` の次)に、`actions=ViewActions(...)` を足す(import に `ViewActions` を足す):

```python
            actions=ViewActions(
                select=self.select_dashboard_view,
                save=self.save_dashboard_view,
                save_as=self.save_dashboard_view_as,
                revert=self.revert_dashboard_view,
                rename=self.rename_dashboard_view,
                delete=self.delete_dashboard_view,
                move_card=self.move_dashboard_card,
                hide_card=self.hide_dashboard_card,
                show_card=self.show_dashboard_card,
            ),
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_view.py test/test_views.py -q -n auto`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_view.py src/projectapp/views.py test/test_dashboard_view.py test/test_views.py
git commit -m "feat: ダッシュボードのツールバーに、ビューの選択と保存の操作を足す"
```

---

### Task 6: 編集モード(ドラッグ・非表示・復帰)

**Files:**
- Create: `src/projectapp/dashboard_drag.py`
- Modify: `src/projectapp/dashboard_view.py`(編集モード・取っ手・隠したカードの一覧・イベントの受け口)
- Test: `test/test_dashboard_drag.py`、`test/test_dashboard_view.py`、`test/test_views.py`

**Interfaces:**
- Consumes: Task 1 の `parse_card_move`・`CardId`・`ViewState.hidden`、Task 5 の `ViewActions.move_card/hide_card/show_card`
- Produces: `dashboard_drag.DASHBOARD_DRAG_JS`・`DASHBOARD_DRAG_CSS`・`CARD_TITLES`(`CardId → 表示名`は `dashboard_view.py` に置く)。`DashboardView.edit_mode: bool`、`DashboardView.handle_move(args: object)`、`DashboardView.set_edit_mode(on: bool)`。マーカー: `dashboard-edit-toggle`・`dashboard-hide-{card_id}`・`dashboard-hidden-{card_id}`(`+` ボタン)・`dashboard-drop-end`。

- [ ] **Step 1: 失敗するテストを書く**

`test/test_dashboard_drag.py` を新規作成する:

```python
from projectapp.dashboard_drag import DASHBOARD_DRAG_CSS, DASHBOARD_DRAG_JS


def test_the_js_emits_the_move_event_and_uses_its_own_drag_type() -> None:
    assert 'emitEvent("dashboard_move_card"' in DASHBOARD_DRAG_JS
    assert "application/x-dashboard-card" in DASHBOARD_DRAG_JS  # ガントチャートの drag と見分ける
    assert "data-dash-handle" in DASHBOARD_DRAG_JS and "data-dash-card" in DASHBOARD_DRAG_JS
    assert "__dashboardDragInstalled" in DASHBOARD_DRAG_JS  # 二重に入れない


def test_the_css_marks_the_drop_position() -> None:
    assert ".dash-drop-before" in DASHBOARD_DRAG_CSS
```

`test/test_dashboard_view.py` に追加する:

```python
async def test_edit_mode_shows_handles_and_hide_buttons_and_the_hidden_list(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    hidden_state = ViewState(("標準",), "標準", False, None, (CardId.TEAM, CardId.DUE), (CardId.PROGRESS,))
    views[0].show(sample(), PeriodKind.WEEK, view_state=hidden_state)
    await user.should_see(marker="dashboard-edit-toggle")
    await user.should_not_see(marker="dashboard-hide-team")  # ふだんは出さない
    user.find(marker="dashboard-edit-toggle").click()
    await user.should_see(marker="dashboard-hide-team")
    await user.should_see(marker="dashboard-hide-due")
    await user.should_see(marker="dashboard-hidden-progress")
    await user.should_see(marker="dashboard-drop-end")
    user.find(marker="dashboard-hide-due").click()
    user.find(marker="dashboard-hidden-progress").click()
    assert log == [("hide", CardId.DUE), ("show", CardId.PROGRESS)]
    user.find(marker="dashboard-edit-toggle").click()
    await user.should_not_see(marker="dashboard-hide-team")


async def test_a_move_event_calls_move_card_and_ignores_bad_arguments(user: User) -> None:
    log: list = []
    views, _, _ = mount(actions=recording_actions(log))
    await user.open("/")
    views[0].show(sample(), PeriodKind.WEEK, view_state=full_state())
    views[0].handle_move({"card": "due", "before": "team"})
    views[0].handle_move({"card": "due", "before": None})
    views[0].handle_move({"card": "nope", "before": None})
    views[0].handle_move("due")
    assert log == [("move", CardId.DUE, CardId.TEAM), ("move", CardId.DUE, None)]
```

ブラウザ側は、取っ手(`data-dash-handle`)が編集モードのときだけ存在するので、Python の受け口は編集モードを見ない。

`test/test_views.py` に追加する:

```python
async def test_editing_cards_in_the_dashboard_changes_order_and_shows_the_dirty_mark(user: User, tmp_path: Path) -> None:
    view = await open_dashboard_view(user, tmp_path)
    await open_dashboard(user, view)
    user.find(marker="dashboard-edit-toggle").click()
    user.find(marker="dashboard-hide-due").click()
    await user.should_see(marker="dashboard-view-dirty")
    await user.should_see(marker="dashboard-hidden-due")
    user.find(marker="dashboard-hidden-due").click()
    assert view.dashboard_cards[-1] is CardId.DUE
    view.dashboard_view.handle_move({"card": "due", "before": "team"})
    assert view.dashboard_cards[0] is CardId.DUE
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest test/test_dashboard_drag.py test/test_dashboard_view.py test/test_views.py -q -k "edit_mode or move_event or editing_cards or dashboard_drag or js_emits or css_marks"`
Expected: FAIL(`dashboard_drag` が未定義)

- [ ] **Step 3: 実装する**

`src/projectapp/dashboard_drag.py` を新規作成する:

```python
"""ダッシュボードのカードのドラッグ用の JS と CSS(定数のみ)。

取っ手(`data-dash-handle`)を HTML5 の drag で掴み、カード(`data-dash-card`)か末尾の落とし場所(`data-dash-end`)に落とす。
結果だけを emitEvent で Python に返す。カードは再描画で作り直されるので、document に委譲する。
ガントチャートの drag とは、dataTransfer の種類で見分ける。
"""

DASHBOARD_DRAG_CSS = """
.dash-drop-before { box-shadow: inset 4px 0 0 0 #1976d2; }
[data-dash-handle] { cursor: grab; }
"""

DASHBOARD_DRAG_JS = """
(() => {
  if (window.__dashboardDragInstalled) return;
  window.__dashboardDragInstalled = true;
  const TYPE = "application/x-dashboard-card";
  let source = null;
  const isOurs = (event) => Array.from((event.dataTransfer || {}).types || []).includes(TYPE);
  const clearMarks = () => {
    document.querySelectorAll(".dash-drop-before").forEach((el) => el.classList.remove("dash-drop-before"));
  };
  const dropTarget = (event) =>
    event.target.closest ? event.target.closest("[data-dash-card], [data-dash-end]") : null;

  document.addEventListener("dragstart", (event) => {
    const handle = event.target.closest ? event.target.closest("[data-dash-handle]") : null;
    if (!handle) return;
    source = handle.dataset.dashHandle;
    event.dataTransfer.setData(TYPE, source);
    event.dataTransfer.effectAllowed = "move";
  });

  document.addEventListener("dragover", (event) => {
    if (!isOurs(event)) return;
    clearMarks();
    const el = dropTarget(event);
    if (!el) return;
    event.preventDefault();
    el.classList.add("dash-drop-before");
  });

  document.addEventListener("drop", (event) => {
    if (!isOurs(event) || source === null) return;
    const el = dropTarget(event);
    clearMarks();
    if (!el) { source = null; return; }
    event.preventDefault();
    const message = { card: source, before: el.dataset.dashCard || null };
    source = null;
    emitEvent("dashboard_move_card", message);
  });

  document.addEventListener("dragend", () => { clearMarks(); source = null; });
})();
"""
```

`src/projectapp/dashboard_view.py`:

import に `from projectapp.dashboard_drag import DASHBOARD_DRAG_CSS, DASHBOARD_DRAG_JS` と、`from projectapp.dashboard_views import ... parse_card_move` を足す。定数を足す:

```python
CARD_TITLES = {
    CardId.TEAM: "チーム全体の進捗",
    CardId.PROGRESS: "進捗と遅れ",
    CardId.LOAD: "人ごとの負荷",
    CardId.HEATMAP: "負荷の日ごとの推移",
    CardId.HOURS: "工数の予定と実績",
    CardId.DUE: "期限とマイルストーン",
}
```

`__init__` に `self.edit_mode = False` を足す。`build()` の先頭の `ui.add_css(HEATMAP_CSS)` の次に:

```python
        ui.add_css(DASHBOARD_DRAG_CSS)
        ui.add_head_html(f"<script>{DASHBOARD_DRAG_JS}</script>")
        ui.on("dashboard_move_card", lambda e: self.handle_move(e.args))
```

ツールバーの `ui.button("戻る", ...)` の前に、編集ボタンを足す:

```python
                self.edit_button = (
                    ui.button("カードを編集", icon="edit", on_click=lambda: self.set_edit_mode(not self.edit_mode))
                    .props("flat dense")
                    .mark("dashboard-edit-toggle")
                )
```

(`__init__` に `self.edit_button: ui.button | None = None` を足す。)

メソッドを足す:

```python
    def set_edit_mode(self, on: bool) -> None:
        self.edit_mode = on
        if self.edit_button is not None:
            self.edit_button.set_text("完了" if on else "カードを編集")
            self.edit_button.props(f"icon={'check' if on else 'edit'}")
        self.cards.refresh()

    def handle_move(self, args: object) -> None:
        """ブラウザからのカードの移動(取っ手を掴んで落とした)を受ける。不正な値は無視する。"""
        parsed = parse_card_move(args)
        if parsed is not None:
            self.act("move_card", *parsed)

    def decorate(self, element: ui.element, card_id: CardId) -> None:
        """編集モードのカードに、取っ手(掴む)と非表示ボタンの帯を、先頭に足す。"""
        element.props(f"data-dash-card={card_id.value}")
        with element:
            with ui.row().classes("w-full items-center justify-between no-wrap") as bar:
                ui.icon("drag_indicator").props(f"data-dash-handle={card_id.value} draggable=true").classes("text-grey")
                ui.button(icon="close", on_click=lambda c=card_id: self.act("hide_card", c)).props(
                    "flat dense round size=sm"
                ).tooltip("このカードを隠す").mark(f"dashboard-hide-{card_id.value}")
        bar.move(element, target_index=0)
```

`cards()` を編集モード対応にする:

```python
        with ui.element("div").style(GRID_STYLE) as grid:
            for card_id in self.card_order:
                before = len(grid.default_slot.children)
                builders[card_id](data)
                created = grid.default_slot.children[before:]
                if self.edit_mode and created:  # 何も描かないカード(空の横断など)は、取っ手を付けない
                    self.decorate(created[0], card_id)
            if self.edit_mode:
                ui.element("div").props("data-dash-end").style("min-height: 3rem; border: 2px dashed rgba(128,128,128,0.5)").mark(
                    "dashboard-drop-end"
                )
        if self.edit_mode and self.state is not None and self.state.hidden:
            with ui.row().classes("w-full items-center gap-2"):
                ui.label("隠したカード").classes("text-caption text-grey")
                for card_id in self.state.hidden:
                    ui.button(
                        CARD_TITLES[card_id], icon="add", on_click=lambda c=card_id: self.act("show_card", c)
                    ).props("flat dense").mark(f"dashboard-hidden-{card_id.value}")
```

(`created[0]` が `ui.card` でない場合〔builder が `box = card(...)` を返す前に別要素を作る等〕に備え、実装時に `builders` の各カードが `card()` を先頭に作ることを確認する。`dashboard-drop-end` の `.props("data-dash-end")` が空の属性値で通らない場合は `data-dash-end=1` にし、JS の `[data-dash-end]` はそのまま使える。)

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest test/test_dashboard_drag.py test/test_dashboard_view.py test/test_views.py -q -n auto`
Expected: PASS。続けて `uvx ty check src` と全体 `uv run pytest -n auto -q`。

- [ ] **Step 5: コミット**

```bash
git add src/projectapp/dashboard_drag.py src/projectapp/dashboard_view.py test/test_dashboard_drag.py test/test_dashboard_view.py test/test_views.py
git commit -m "feat: ダッシュボードのカードを、編集モードでドラッグ・非表示・復帰できるようにする"
```

---

### Task 7: 仕様・開発者向け文書・状態の更新と実機確認

**Files:**
- Modify: `CLAUDE.md`(`ダッシュボード`の節、`データの保存先`の節)
- Modify: `docs/development.md`(モジュール表に `dashboard_views.py`・`dashboard_drag.py`)
- Modify: `docs/superpowers/specs/2026-10-27-dashboard-views-design.md`(冒頭の小さな変更 2 点)
- Modify: `docs/requests.md`・`.claude/MEMORY.md`・`docs/request-history.md`(要望 40 の状態)

**Interfaces:**
- Consumes: Task 1〜6 の実装
- Produces: なし

- [ ] **Step 1: 仕様書(`CLAUDE.md`)を更新する**

`ダッシュボード`の節の末尾の `集計は、表示のたびに…` の前に、次を足す:

```
- 期間・メンバー・`全プロジェクト`・カードの出し入れと順を、名前を付けた「ビュー」として保存して切り替えられる(ツールバーの、`ダッシュボード`の見出しの右のプルダウン)。`標準`は組み込み(今週・全員・オフ・全カード・既定の順)で、改名・削除・上書きはできない。`指定`のビューは日付(`2026-10-01 〜 2026-10-31`)も保存する(相対的な指定は未対応)。プロジェクトごとの除外は保存しない。名前は 30 文字まで(タスク名と同じ文字の制限)、ビューは `標準` を除いて 20 件まで。保存先は`~/.projectapp/config.json`の`dashboard_views`と、最後に使った名前の`dashboard_view_last`(全プロジェクト共通・プロジェクトのファイルには触れない)。ダッシュボードを開くと最後に使ったビューを出し、作業中の変更は持ち越さない
- 条件の変更・カードの移動・非表示は、保存するまで作業中の状態で、プルダウンの横に`●`と`保存`・`元に戻す`を出す(`名前をつけて保存`は常に出す)。`保存`は`標準`では押せず、`指定`の欄にエラーがあるときは押せない。別のビューへの切り替えは作業中の変更を確認なしで捨てる。改名・削除はプルダウン横のメニュー(`標準`では押せない。削除は確認を出す)。保存したメンバーが今の名簿にいないときは、画面だけ`全員`に戻す(ビューは書き換えず、`●`も出さない)。設定を書けないときは通知し、画面上のビューは使い続ける
- `カードを編集`で編集モードに入り(`完了`で抜ける)、カードの取っ手を掴んで別のカードの上(または末尾の落とし場所)へ落とすと並べ替わり、×で隠し、`隠したカード`の`+`で末尾に戻す。`負荷の日ごとの推移`は`全プロジェクト`がオンのときだけ出る
```

`データの保存先`の節の `テーマと名前の欄の幅と画面の倍率は…` の行に、`ダッシュボードのビュー(`dashboard_views`・`dashboard_view_last`)` を足す。

- [ ] **Step 2: 開発者向け文書を更新する**

`docs/development.md` のモジュール表に、`dashboard_views.py`(`ViewSpec`・`ViewState`・`CardId`・検証・カード操作・`views_from_config`/`views_to_config`・`parse_card_move`。純粋関数)と `dashboard_drag.py`(カードのドラッグの JS・CSS の定数。`gantt_drag.py` と dataTransfer の種類で見分ける)の行を、周囲の書式に合わせて足す。`dashboard_view.py` の行に `ViewActions`・`ViewState` で MainView と繋ぐことを書く。

- [ ] **Step 3: 設計書を実装に合わせる**

`docs/superpowers/specs/2026-10-27-dashboard-views-design.md` の、`操作` の節の `名前をつけて保存` の行に「常に出す(`標準` のままでも新しいビューを作れるように)。`保存`・`元に戻す` は `●` のときだけ」を足し、`エラー処理` の節の `指定` のビューに日付がないときの文を「`指定` を選んだときと同じく、直前の期間から始める(欄は空にしない)」に直す。

- [ ] **Step 4: 全体の確認**

Run: `uv run pytest -n auto -q` と `uvx ty check src`
Expected: すべて通過(件数を記録する)

- [ ] **Step 5: 実機(ネイティブ)で確かめる**

Run: `uv run projectapp`。次を目で確かめ、結果を記録する:
1. ダッシュボードを開く → ツールバーに、ビューのプルダウン・`名前をつけて保存`・`カードを編集` が出る。
2. `今月` に変える → `●` と `保存`・`元に戻す` が出る。`名前をつけて保存` で「月次」を作る → `●` が消え、アプリを閉じて開き直しても、ダッシュボードが「月次」で開く。
3. `カードを編集` → カードの取っ手を掴んで別のカードの上に落とす(ネイティブの WebKit で drag が動くか)。末尾の落とし場所への drop。×で隠す、`隠したカード` の `+` で戻す。
4. `指定` で日付を入れて保存 → 別のビューへ切り替えて戻る → 日付が戻る。
5. `全プロジェクト` をオン → `負荷の日ごとの推移` がカードに出て、編集モードでも動く。
6. ガントチャートに戻る → ダッシュボードのドラッグが、ガントチャートの行・セクションのドラッグに干渉しない。

- [ ] **Step 6: 状態を更新してコミットする**

`docs/requests.md` の要望 40 の状態を「実装済み(PR 番号は、マージ後に記録)」にし、`.claude/MEMORY.md` の「現在の状況」と「今後の要望」の 40 を更新し、`docs/request-history.md` に対応を足す(周囲の書式に合わせる)。

```bash
git add CLAUDE.md docs .claude/MEMORY.md
git commit -m "docs: ダッシュボードのビューの仕様と開発者向けの記録を更新する"
```

---

## Self-Review(計画を書いたあとの確認)

- **設計書との対応**: ビューの型・検証・上限(Task 1)、`config.json` の 2 つのキーと壊れた値の扱い(Task 2)、カードの順序表(Task 3)、作業中の状態・`●`・保存・名前をつけて保存・元に戻す・改名・削除・開いたときのビュー・メンバーの解決・永続化の失敗(Task 4)、ツールバー(Task 5)、編集モードとドラッグ(Task 6)、仕様書と実機確認(Task 7)。`指定` の日付の保存・読込・保存の拒否は Task 1・2・4。
- **設計書からの変更**: `名前をつけて保存` を常に出す、`指定` の日付なしは直前の期間から始める。前者は Task 5、後者は Task 4(`apply_dashboard_view`)で実装し、Task 7 で設計書に反映する。
- **型の一貫性**: `ViewState.save_block`・`ViewActions.*`・`MainView` のハンドラ名(`select_dashboard_view` など)は Task 4・5・6 で同じ名前を使っている。`handle_move` は `DashboardView` の受け口で、`MainView.move_dashboard_card` に繋がる。
- **既知の確認点**: Task 4 の `.clear().type()` は、既存テストの書き方に合わせて直す。Task 6 の `created[0]` が各カードの最上位要素である前提は、実装時に 6 つの描画メソッドを読んで確かめる。
