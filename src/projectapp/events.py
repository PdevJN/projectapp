"""イベントカレンダーの規則(検証・段の割り当て・列との重なり・セルの色)。NiceGUI に依存しない。"""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from projectapp.models import MAX_EVENT_TEXT_LENGTH, MAX_YEAR, MIN_YEAR, Event, Project, has_control_char
from projectapp.timeline import Column

# CSS の名前付き色(CSS Color Module Level 4)。キーは小文字、値は #rrggbb。transparent は含めない
CSS_COLORS: dict[str, str] = {
    "aliceblue": "#f0f8ff", "antiquewhite": "#faebd7", "aqua": "#00ffff", "aquamarine": "#7fffd4",
    "azure": "#f0ffff", "beige": "#f5f5dc", "bisque": "#ffe4c4", "black": "#000000",
    "blanchedalmond": "#ffebcd", "blue": "#0000ff", "blueviolet": "#8a2be2", "brown": "#a52a2a",
    "burlywood": "#deb887", "cadetblue": "#5f9ea0", "chartreuse": "#7fff00", "chocolate": "#d2691e",
    "coral": "#ff7f50", "cornflowerblue": "#6495ed", "cornsilk": "#fff8dc", "crimson": "#dc143c",
    "cyan": "#00ffff", "darkblue": "#00008b", "darkcyan": "#008b8b", "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9", "darkgreen": "#006400", "darkgrey": "#a9a9a9", "darkkhaki": "#bdb76b",
    "darkmagenta": "#8b008b", "darkolivegreen": "#556b2f", "darkorange": "#ff8c00", "darkorchid": "#9932cc",
    "darkred": "#8b0000", "darksalmon": "#e9967a", "darkseagreen": "#8fbc8f", "darkslateblue": "#483d8b",
    "darkslategray": "#2f4f4f", "darkslategrey": "#2f4f4f", "darkturquoise": "#00ced1", "darkviolet": "#9400d3",
    "deeppink": "#ff1493", "deepskyblue": "#00bfff", "dimgray": "#696969", "dimgrey": "#696969",
    "dodgerblue": "#1e90ff", "firebrick": "#b22222", "floralwhite": "#fffaf0", "forestgreen": "#228b22",
    "fuchsia": "#ff00ff", "gainsboro": "#dcdcdc", "ghostwhite": "#f8f8ff", "gold": "#ffd700",
    "goldenrod": "#daa520", "gray": "#808080", "green": "#008000", "greenyellow": "#adff2f",
    "grey": "#808080", "honeydew": "#f0fff0", "hotpink": "#ff69b4", "indianred": "#cd5c5c",
    "indigo": "#4b0082", "ivory": "#fffff0", "khaki": "#f0e68c", "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5", "lawngreen": "#7cfc00", "lemonchiffon": "#fffacd", "lightblue": "#add8e6",
    "lightcoral": "#f08080", "lightcyan": "#e0ffff", "lightgoldenrodyellow": "#fafad2", "lightgray": "#d3d3d3",
    "lightgreen": "#90ee90", "lightgrey": "#d3d3d3", "lightpink": "#ffb6c1", "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa", "lightskyblue": "#87cefa", "lightslategray": "#778899", "lightslategrey": "#778899",
    "lightsteelblue": "#b0c4de", "lightyellow": "#ffffe0", "lime": "#00ff00", "limegreen": "#32cd32",
    "linen": "#faf0e6", "magenta": "#ff00ff", "maroon": "#800000", "mediumaquamarine": "#66cdaa",
    "mediumblue": "#0000cd", "mediumorchid": "#ba55d3", "mediumpurple": "#9370db", "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee", "mediumspringgreen": "#00fa9a", "mediumturquoise": "#48d1cc", "mediumvioletred": "#c71585",
    "midnightblue": "#191970", "mintcream": "#f5fffa", "mistyrose": "#ffe4e1", "moccasin": "#ffe4b5",
    "navajowhite": "#ffdead", "navy": "#000080", "oldlace": "#fdf5e6", "olive": "#808000",
    "olivedrab": "#6b8e23", "orange": "#ffa500", "orangered": "#ff4500", "orchid": "#da70d6",
    "palegoldenrod": "#eee8aa", "palegreen": "#98fb98", "paleturquoise": "#afeeee", "palevioletred": "#db7093",
    "papayawhip": "#ffefd5", "peachpuff": "#ffdab9", "peru": "#cd853f", "pink": "#ffc0cb",
    "plum": "#dda0dd", "powderblue": "#b0e0e6", "purple": "#800080", "rebeccapurple": "#663399",
    "red": "#ff0000", "rosybrown": "#bc8f8f", "royalblue": "#4169e1", "saddlebrown": "#8b4513",
    "salmon": "#fa8072", "sandybrown": "#f4a460", "seagreen": "#2e8b57", "seashell": "#fff5ee",
    "sienna": "#a0522d", "silver": "#c0c0c0", "skyblue": "#87ceeb", "slateblue": "#6a5acd",
    "slategray": "#708090", "slategrey": "#708090", "snow": "#fffafa", "springgreen": "#00ff7f",
    "steelblue": "#4682b4", "tan": "#d2b48c", "teal": "#008080", "thistle": "#d8bfd8",
    "tomato": "#ff6347", "turquoise": "#40e0d0", "violet": "#ee82ee", "wheat": "#f5deb3",
    "white": "#ffffff", "whitesmoke": "#f5f5f5", "yellow": "#ffff00", "yellowgreen": "#9acd32",
}


def normalize_color(name: str) -> str | None:
    """色名を小文字にして返す。前後の空白は除く。CSS の色名でなければ None。"""
    key = name.strip().lower()
    return key if key in CSS_COLORS else None


def color_hex(name: str) -> str:
    """色名の #rrggbb。検証済みの色名だけを渡す。"""
    return CSS_COLORS[name]


def validate_events(events: Sequence[Event]) -> None:
    """イベントの一覧を検証する。不正は ValueError(理由つき)。"""
    ids: set[str] = set()
    for e in events:
        if not e.id or e.id in ids:
            raise ValueError(f"イベントの id が正しくありません: {e.id!r}")
        ids.add(e.id)
        if e.start > e.end:
            raise ValueError("イベントの終了日は開始日以降にしてください")
        if not e.text.strip():
            raise ValueError("イベントの文字列を入力してください")
        if len(e.text) > MAX_EVENT_TEXT_LENGTH:
            raise ValueError(f"イベントの文字列は{MAX_EVENT_TEXT_LENGTH}文字以内で入力してください")
        if has_control_char(e.text):
            raise ValueError("イベントの文字列に改行・制御文字は使えません")
        if e.color not in CSS_COLORS:
            raise ValueError(f"イベントの色が正しくありません: {e.color!r}(red・orange・gray などの色名)")


def sort_events(events: Sequence[Event]) -> list[Event]:
    """開始日、終了日の昇順。同じものは元の並びを保つ(安定)。"""
    return sorted(events, key=lambda e: (e.start, e.end))


def assign_lanes(events: Sequence[Event], columns: Sequence[Column] | None = None) -> list[int]:
    """イベントごとの段(0 から)。開始の早い順に、空いた最小の段へ詰める。入力と同じ順で返す。

    `columns` がなければ日付で比べる(前の終了日の翌日に始まるなら同じ段)。あれば、描く列の範囲で比べる
    (週次・月次で、日付は重ならなくても同じ列に入るイベントは、別の段にする)。列の外のイベントは段を取らない(0)。
    """
    keys: dict[int, tuple[int, int]] = {}  # 日付の序数、または列の添字
    for i, e in enumerate(events):
        if columns is None:
            keys[i] = (e.start.toordinal(), e.end.toordinal())
        elif (span := column_span(e, columns)) is not None:
            keys[i] = (span[0], span[0] + span[1] - 1)
    order = sorted(keys, key=lambda i: (keys[i], i))
    lane_ends: list[int] = []  # 各段の最後のイベントの終わり
    lanes = [0] * len(events)
    for i in order:
        start, end = keys[i]
        for lane, last in enumerate(lane_ends):
            if last < start:
                lane_ends[lane] = end
                lanes[i] = lane
                break
        else:
            lanes[i] = len(lane_ends)
            lane_ends.append(end)
    return lanes


def count_lanes(lanes: Sequence[int]) -> int:
    return max(lanes, default=-1) + 1


def column_span(event: Event, columns: Sequence[Column]) -> tuple[int, int] | None:
    """期間に 1 日でも重なる列の、先頭の添字と列数。重ならなければ None。列は [start, end)。"""
    touched = [i for i, c in enumerate(columns) if c.start <= event.end and c.end > event.start]
    if not touched:
        return None
    return touched[0], len(touched)


def cell_colors(events: Sequence[Event], columns: Sequence[Column]) -> list[str | None]:
    """列ごとの色名。重なる列は、リストの後ろのイベントの色になる。"""
    colors: list[str | None] = [None] * len(columns)
    for e in events:
        span = column_span(e, columns)
        if span is not None:
            first, count = span
            for i in range(first, first + count):
                colors[i] = e.color
    return colors


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
