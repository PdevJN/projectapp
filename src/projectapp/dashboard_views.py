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
    BACKLOG = "backlog"  # `未着手の工数と必要人数`
    DUE = "due"


DEFAULT_ORDER: tuple[CardId, ...] = (
    CardId.TEAM, CardId.PROGRESS, CardId.LOAD, CardId.HEATMAP, CardId.HOURS, CardId.BACKLOG, CardId.DUE,
)


@dataclass(frozen=True)
class ViewSpec:
    name: str
    period: PeriodKind
    member: str | None
    cross: bool
    cards: tuple[CardId, ...]  # 表示するカードを、並び順に
    custom: tuple[date, date] | None = None  # `period` が `指定` のときだけ。両端を含む
    team: str | None = None  # 絞り込み中のチーム名(メンバーとは同時に使わない。両方あればメンバー優先)


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


def resolve_team(team: str | None, names: Iterable[str]) -> str | None:
    """保存したチームが今の名簿になければ(メンバーのいるチームの名前になければ)、全員(None)。"""
    return team if team is not None and team in set(names) else None


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


def views_to_config(views: list[ViewSpec]) -> list[dict]:
    result = []
    for spec in views:
        entry: dict = {
            "name": spec.name,
            "period": spec.period.value,
            "member": spec.member,
            "team": spec.team,
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
    team = raw.get("team")
    cross = raw.get("cross")
    custom = custom_from_config(raw.get("custom")) if period is PeriodKind.CUSTOM else None
    return ViewSpec(
        name,
        period,
        member if isinstance(member, str) and member else None,
        cross if isinstance(cross, bool) else False,
        normalize_cards(raw.get("cards")),
        custom,
        team if isinstance(team, str) and team else None,
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
