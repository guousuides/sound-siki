"""路線 - the three lines you can ride, and how a journey is laid out on one.

A line is a list of stations with their distance along the track, plus the few
things that decide how the line *sounds*: whether it is jointed or welded rail,
where it runs in tunnel, where it curves, and where the crossovers are. All of
it is arithmetic the train demon reads off the current position, so nothing in
the ride is decided by a die roll - the tunnel is there because the line goes
into a tunnel there.

Distances are 営業キロ, the published tariff distances, rounded to 100 m; the
route totals match the published figures (山手線 34.5 km, 中央線 東京〜高尾
53.1 km, 副都心線 20.2 km). Curves and crossovers are *indicative* rather than
surveyed - they are placed where that kind of line has them (a subway curves
constantly, a depot station has a crossover on its approach), so the ride has
the right texture in the right places rather than a surveyor's accuracy.

Readings are kana because the announcer speaks them: see announce.py, which
turns a kana string into moras and a mora into formants.
"""
from __future__ import annotations

KMH = 1.0 / 3.6            # km/h -> m/s


class Station:
    __slots__ = ("name", "kana", "km")

    def __init__(self, name, kana, km):
        self.name = name
        self.kana = kana
        self.km = float(km)


class Kind:
    """A service pattern: which stations this train actually stops at."""

    __slots__ = ("name", "kana", "stops")

    def __init__(self, name, kana, stops=None):
        self.name = name
        self.kana = kana
        self.stops = stops          # None = every station


class Line:
    def __init__(self, key, name, kana, stations, kinds, dir_names,
                 max_kmh, jointed, tunnels=(), curves=(), crossovers=(),
                 loop_close=None, note=""):
        self.key = key
        self.name = name
        self.kana = kana
        self.stations = [Station(*s) for s in stations]
        self.kinds = kinds
        self.dir_names = dir_names
        self.max_speed = max_kmh * KMH
        self.jointed = jointed
        self.tunnels = tunnels          # [(km, km)] along the canonical order
        self.curves = curves            # [km]
        self.crossovers = set(crossovers)   # station names with points on approach
        self.loop_close = loop_close    # km from the last station back to the first
        self.note = note

    @property
    def is_loop(self):
        return self.loop_close is not None

    @property
    def total_km(self):
        last = self.stations[-1].km
        return last + self.loop_close if self.is_loop else last

    def index(self, name):
        for i, s in enumerate(self.stations):
            if s.name == name:
                return i
        raise KeyError(name)

    # ------------------------------------------------------------------ plan
    def order(self, direction):
        """Station indices in travel order for this direction."""
        n = len(self.stations)
        return list(range(n)) if direction > 0 else list(range(n - 1, -1, -1))

    def gap_km(self, a, b):
        """Track distance between two adjacent stations, either way round."""
        if self.is_loop and {a, b} == {0, len(self.stations) - 1}:
            return self.loop_close
        return abs(self.stations[b].km - self.stations[a].km)

    def plan(self, direction, origin, dest, kind):
        """Lay the journey out as a straight line of metres from the origin.

        Everything downstream works in this one coordinate: the stations, the
        tunnel mouths, the curves and the rail joints all live on the same
        ruler, so 'where are we' is a single float.
        """
        seq = self.order(direction)
        start = seq.index(origin)
        stops = kind.stops

        walk, s_m, i = [], 0.0, start
        prev = seq[i]
        walk.append((prev, 0.0))
        while True:
            i += 1
            if i >= len(seq):
                if not self.is_loop:
                    raise ValueError("%s は %s の先には行きません"
                                     % (self.stations[dest].name,
                                        self.stations[seq[-1]].name))
                i = 0                           # only a loop line comes round
            cur = seq[i]
            s_m += self.gap_km(prev, cur) * 1000.0
            walk.append((cur, s_m))
            prev = cur
            if cur == dest:
                break
            if i == start:                      # a full lap, back where we began
                break

        entries = [RouteStop(self.stations[idx].name, self.stations[idx].kana, s,
                             stops is None or self.stations[idx].name in stops)
                   for idx, s in walk]
        entries[0].is_stop = True
        entries[-1].is_stop = True
        length = entries[-1].s

        # Fixed features are on the line's own ruler; fold them onto the
        # journey's, which may run backwards and may wrap past the origin.
        def fold(km):
            """A fixed point on the line -> every metre-mark it occupies here.

            A lap of a loop line passes the same tunnel mouth again, so this
            returns a list, not a value.
            """
            base = self.stations[origin].km
            total = self.total_km
            d = (km - base) * direction
            while d < -1e-9:
                d += total
            out = []
            while d * 1000.0 <= length + 1e-9:
                out.append(d * 1000.0)
                if not self.is_loop:
                    break
                d += total
            return out

        tunnels = []
        for a, b in self.tunnels:
            lo, hi = (a, b) if direction > 0 else (b, a)
            # A mouth can fall outside the journey while the bore still covers
            # it - riding 渋谷 -> 小竹向原 you start underground and never
            # surface - so clamp each span to the journey instead of dropping it.
            for s0 in fold(lo):
                s1 = s0 + abs(hi - lo) * 1000.0
                s0, s1 = max(s0, 0.0), min(s1, length)
                if s1 - s0 > 1.0:
                    tunnels.append((s0, s1))
        tunnels.sort()

        curves = sorted(s for km in self.curves for s in fold(km))
        points = sorted(e.s - 130.0 for e in entries
                        if e.name in self.crossovers and e.s > 200.0)

        return RoutePlan(self, kind, direction, entries, length,
                         tunnels, curves, points)


class RouteStop:
    __slots__ = ("name", "kana", "s", "is_stop")

    def __init__(self, name, kana, s, is_stop):
        self.name = name
        self.kana = kana
        self.s = s
        self.is_stop = is_stop


class RoutePlan:
    """One journey, flattened onto a single ruler of metres."""

    def __init__(self, line, kind, direction, entries, length,
                 tunnels, curves, points):
        self.line = line
        self.kind = kind
        self.direction = direction
        self.entries = entries
        self.length = length
        self.tunnels = tunnels
        self.curves = curves
        self.points = points

    @property
    def stops(self):
        return [e for e in self.entries if e.is_stop]

    @property
    def origin(self):
        return self.entries[0]

    @property
    def dest(self):
        return self.entries[-1]

    @property
    def dir_name(self):
        return self.line.dir_names[0 if self.direction > 0 else 1]

    def estimate_minutes(self):
        """Door-to-door time, run section by section.

        It exists so you can pick a 25-minute ride when you have 25 minutes, so
        it has to be honest about the thing that actually dominates a stopping
        service: not the line speed but the accelerating, the braking and the
        standing. A short section never reaches line speed at all, which is why
        this integrates each gap rather than dividing the total by a number.
        """
        a, b = 0.268, 0.49                        # effective rates, incl. notch-up
        v_line = self.line.max_speed * 0.80      # what a stopping train really sees
        dwell = 24.0                             # doors open, bell, whistle, away
        stops = self.stops
        total = 0.0
        for u, w in zip(stops, stops[1:]):
            L = w.s - u.s
            if v_line * v_line * (1 / a + 1 / b) / 2.0 <= L:
                total += v_line / a + v_line / b + (
                    L - v_line * v_line * (1 / a + 1 / b) / 2.0) / v_line
            else:
                v = (2.0 * L * a * b / (a + b)) ** 0.5
                total += v / a + v / b
        return (total + dwell * max(len(stops) - 2, 0)) / 60.0


# --------------------------------------------------------------------------
# 山手線 - above ground, jointed track, a station every 1.2 km, and it closes
# on itself, so "東京 to 東京" is a legitimate 59-minute lap.
# --------------------------------------------------------------------------
YAMANOTE = Line(
    key="yamanote", name="山手線", kana="やまのてせん",
    stations=[
        ("東京", "とうきょう", 0.0),
        ("神田", "かんだ", 1.3),
        ("秋葉原", "あきはばら", 2.0),
        ("御徒町", "おかちまち", 3.0),
        ("上野", "うえの", 3.6),
        ("鶯谷", "うぐいすだに", 4.7),
        ("日暮里", "にっぽり", 5.8),
        ("西日暮里", "にしにっぽり", 6.3),
        ("田端", "たばた", 7.1),
        ("駒込", "こまごめ", 8.7),
        ("巣鴨", "すがも", 9.4),
        ("大塚", "おおつか", 10.5),
        ("池袋", "いけぶくろ", 12.3),
        ("目白", "めじろ", 13.5),
        ("高田馬場", "たかだのばば", 14.4),
        ("新大久保", "しんおおくぼ", 15.8),
        ("新宿", "しんじゅく", 17.1),
        ("代々木", "よよぎ", 17.8),
        ("原宿", "はらじゅく", 19.3),
        ("渋谷", "しぶや", 20.5),
        ("恵比寿", "えびす", 22.1),
        ("目黒", "めぐろ", 23.6),
        ("五反田", "ごたんだ", 24.8),
        ("大崎", "おおさき", 25.7),
        ("品川", "しながわ", 27.7),
        ("高輪ゲートウェイ", "たかなわげーとうえい", 28.6),
        ("田町", "たまち", 29.9),
        ("浜松町", "はままつちょう", 31.4),
        ("新橋", "しんばし", 32.6),
        ("有楽町", "ゆうらくちょう", 33.7),
    ],
    kinds=[Kind("各駅停車", "かくえきていしゃ")],
    dir_names=("内回り", "外回り"),
    max_kmh=90.0, jointed=True,
    tunnels=(),                                   # 全線地上
    curves=(19.9, 24.9, 25.9, 13.9),              # 原宿手前・五反田・大崎・目白
    crossovers=("東京", "池袋", "大崎", "品川", "田端"),
    loop_close=0.8,
    note="地上・周回。ジョイントが主役。",
)

# --------------------------------------------------------------------------
# 中央線快速 - the long-haul one. Stations thin out west of 三鷹 and the train
# gets to actually run, which is what the wind and the motor are for.
# --------------------------------------------------------------------------
CHUO_STATIONS = [
    ("東京", "とうきょう", 0.0),
    ("神田", "かんだ", 1.3),
    ("御茶ノ水", "おちゃのみず", 2.6),
    ("四ツ谷", "よつや", 6.6),
    ("新宿", "しんじゅく", 10.3),
    ("中野", "なかの", 14.7),
    ("高円寺", "こうえんじ", 16.1),
    ("阿佐ケ谷", "あさがや", 17.2),
    ("荻窪", "おぎくぼ", 18.6),
    ("西荻窪", "にしおぎくぼ", 20.6),
    ("吉祥寺", "きちじょうじ", 22.5),
    ("三鷹", "みたか", 24.1),
    ("武蔵境", "むさしさかい", 25.7),
    ("東小金井", "ひがしこがねい", 27.4),
    ("武蔵小金井", "むさしこがねい", 29.1),
    ("国分寺", "こくぶんじ", 31.6),
    ("西国分寺", "にしこくぶんじ", 33.3),
    ("国立", "くにたち", 35.0),
    ("立川", "たちかわ", 36.9),
    ("日野", "ひの", 40.6),
    ("豊田", "とよだ", 43.1),
    ("八王子", "はちおうじ", 47.4),
    ("西八王子", "にしはちおうじ", 50.0),
    ("高尾", "たかお", 53.1),
]

CHUO = Line(
    key="chuo", name="中央線快速", kana="ちゅうおうせんかいそく",
    stations=CHUO_STATIONS,
    kinds=[
        Kind("快速", "かいそく"),
        Kind("特別快速", "とくべつかいそく", stops={
            "東京", "神田", "御茶ノ水", "四ツ谷", "新宿", "中野", "三鷹",
            "国分寺", "立川", "八王子", "西八王子", "高尾"}),
    ],
    dir_names=("下り", "上り"),
    max_kmh=100.0, jointed=True,
    tunnels=((3.3, 3.7), (4.9, 5.3)),             # 御茶ノ水〜四ツ谷の掘割と短いトンネル
    curves=(2.4, 5.8, 14.5, 36.5, 52.0),
    crossovers=("東京", "中野", "三鷹", "武蔵小金井", "立川", "豊田",
                "八王子", "高尾"),
    note="地上・高速。駅間が長く、走行音を長く浴びられる。",
)

# --------------------------------------------------------------------------
# 副都心線 - opened 2008, so the track is welded and the line is underground
# from just past 和光市 all the way to 渋谷. One tunnel mouth, then the world
# stays closed: the reverberant bed is not an event here, it is the weather.
# --------------------------------------------------------------------------
FUKUTOSHIN = Line(
    key="fukutoshin", name="副都心線", kana="ふくとしんせん",
    stations=[
        ("和光市", "わこうし", 0.0),
        ("地下鉄成増", "ちかてつなります", 2.2),
        ("地下鉄赤塚", "ちかてつあかつか", 3.6),
        ("平和台", "へいわだい", 5.4),
        ("氷川台", "ひかわだい", 6.8),
        ("小竹向原", "こたけむかいはら", 8.3),
        ("千川", "せんかわ", 9.3),
        ("要町", "かなめちょう", 10.3),
        ("池袋", "いけぶくろ", 11.3),
        ("雑司が谷", "ぞうしがや", 12.5),
        ("西早稲田", "にしわせだ", 14.1),
        ("東新宿", "ひがししんじゅく", 15.5),
        ("新宿三丁目", "しんじゅくさんちょうめ", 16.6),
        ("北参道", "きたさんどう", 17.8),
        ("明治神宮前", "めいじじんぐうまえ", 19.0),
        ("渋谷", "しぶや", 20.2),
    ],
    kinds=[
        Kind("各駅停車", "かくえきていしゃ"),
        Kind("急行", "きゅうこう", stops={
            "和光市", "小竹向原", "池袋", "新宿三丁目", "明治神宮前", "渋谷"}),
    ],
    dir_names=("渋谷方面", "和光市方面"),
    max_kmh=90.0, jointed=False,
    tunnels=((1.5, 20.2),),                       # 和光市を出てすぐ地下へ
    curves=(4.6, 7.9, 8.6, 10.9, 12.1, 13.4, 15.0, 16.2, 17.4, 18.6, 19.6),
    crossovers=("和光市", "小竹向原", "池袋", "新宿三丁目", "渋谷"),
    note="地下・全駅ホームドア。トンネルが例外ではなく常態。",
)

LINES = {l.key: l for l in (YAMANOTE, CHUO, FUKUTOSHIN)}
ORDER = ["yamanote", "chuo", "fukutoshin"]
