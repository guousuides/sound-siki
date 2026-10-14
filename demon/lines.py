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
    __slots__ = ("name", "kana", "km", "en", "code", "transfers")

    def __init__(self, name, kana, km, en=None, code=None, transfers=None):
        self.name = name
        self.kana = kana
        self.km = float(km)
        self.en = en or name
        self.code = code
        self.transfers = tuple(transfers) if transfers else ()


class Kind:
    """A service pattern: which stations this train actually stops at."""

    __slots__ = ("name", "kana", "stops", "en")

    def __init__(self, name, kana, stops=None, en=None):
        self.name = name
        self.kana = kana
        self.stops = stops          # None = every station
        self.en = en or ("Local" if "各駅" in name else "Special Rapid" if "特別" in name else "Rapid" if "快速" in name else "Express" if "急行" in name else name)


class Line:
    def __init__(self, key, name, kana, stations, kinds, dir_names,
                 max_kmh, jointed, tunnels=(), curves=(), crossovers=(),
                 loop_close=None, note="", en=""):
        self.key = key
        self.name = name
        self.kana = kana
        self.en = en or name
        self.stations = [Station(*s) if isinstance(s, (tuple, list)) else s for s in stations]
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
                             stops is None or self.stations[idx].name in stops,
                             station=self.stations[idx])
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
    __slots__ = ("name", "kana", "s", "is_stop", "station")

    def __init__(self, name, kana, s, is_stop, station=None):
        self.name = name
        self.kana = kana
        self.s = s
        self.is_stop = is_stop
        self.station = station

    @property
    def en(self):
        return self.station.en if self.station else self.name

    @property
    def code(self):
        return self.station.code if self.station else None

    @property
    def transfers(self):
        return self.station.transfers if self.station else ()


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
# --------------------------------------------------------------------------
# 山手線 - above ground, jointed track, a station every 1.2 km, and it closes
# on itself, so "東京 to 東京" is a legitimate 59-minute lap.
# --------------------------------------------------------------------------
YAMANOTE = Line(
    key="yamanote", name="山手線", kana="やまのてせん", en="Yamanote Line",
    stations=[
        ("東京", "とうきょう", 0.0, "Tokyo", "JY-01", ["中央線", "京浜東北線", "東海道線", "新幹線"]),
        ("神田", "かんだ", 1.3, "Kanda", "JY-02", ["中央線", "銀座線"]),
        ("秋葉原", "あきはばら", 2.0, "Akihabara", "JY-03", ["総武線", "日比谷線", "つくばエクスプレス"]),
        ("御徒町", "おかちまち", 3.0, "Okachimachi", "JY-04", []),
        ("上野", "うえの", 3.6, "Ueno", "JY-05", ["常磐線", "宇都宮線", "銀座線", "日比谷線", "新幹線"]),
        ("鶯谷", "うぐいすだに", 4.7, "Uguisudani", "JY-06", []),
        ("日暮里", "にっぽり", 5.8, "Nippori", "JY-07", ["常磐線", "京成線"]),
        ("西日暮里", "にしにっぽり", 6.3, "Nishi-Nippori", "JY-08", ["千代田線"]),
        ("田端", "たばた", 7.1, "Tabata", "JY-09", ["京浜東北線"]),
        ("駒込", "こまごめ", 8.7, "Komagome", "JY-10", ["南北線"]),
        ("巣鴨", "すがも", 9.4, "Sugamo", "JY-11", ["三田線"]),
        ("大塚", "おおつか", 10.5, "Otsuka", "JY-12", ["都電荒川線"]),
        ("池袋", "いけぶくろ", 12.3, "Ikebukuro", "JY-13", ["丸ノ内線", "有楽町線", "副都心線", "東武東上線", "西武池袋線"]),
        ("目白", "めじろ", 13.5, "Mejiro", "JY-14", []),
        ("高田馬場", "たかだのばば", 14.4, "Takadanobaba", "JY-15", ["東西線", "西武新宿線"]),
        ("新大久保", "しんおおくぼ", 15.8, "Shin-Okubo", "JY-16", []),
        ("新宿", "しんじゅく", 17.1, "Shinjuku", "JY-17", ["中央線", "埼京線", "丸ノ内線", "小田急線", "京王線"]),
        ("代々木", "よよぎ", 17.8, "Yoyogi", "JY-18", ["総武線", "大江戸線"]),
        ("原宿", "はらじゅく", 19.3, "Harajuku", "JY-19", ["千代田線", "副都心線"]),
        ("渋谷", "しぶや", 20.5, "Shibuya", "JY-20", ["埼京線", "銀座線", "半蔵門線", "副都心線", "東急東横線", "井の頭線"]),
        ("恵比寿", "えびす", 22.1, "Ebisu", "JY-21", ["日比谷線", "埼京線"]),
        ("目黒", "めぐろ", 23.6, "Meguro", "JY-22", ["三田線", "南北線", "東急目黒線"]),
        ("五反田", "ごたんだ", 24.8, "Gotanda", "JY-23", ["浅草線", "東急池上線"]),
        ("大崎", "おおさき", 25.7, "Osaki", "JY-24", ["埼京線", "りんかい線"]),
        ("品川", "しながわ", 27.7, "Shinagawa", "JY-25", ["京浜東北線", "東海道線", "京急線", "新幹線"]),
        ("高輪ゲートウェイ", "たかなわげーとうえい", 28.6, "Takanawa Gateway", "JY-26", []),
        ("田町", "たまち", 29.9, "Tamachi", "JY-27", ["京浜東北線", "三田線"]),
        ("浜松町", "はままつちょう", 31.4, "Hamamatsucho", "JY-28", ["東京モノレール", "大江戸線"]),
        ("新橋", "しんばし", 32.6, "Shimbashi", "JY-29", ["銀座線", "浅草線", "ゆりかもめ"]),
        ("有楽町", "ゆうらくちょう", 33.7, "Yurakucho", "JY-30", ["有楽町線", "日比谷線"]),
    ],
    kinds=[Kind("各駅停車", "かくえきていしゃ", en="Local")],
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
    ("東京", "とうきょう", 0.0, "Tokyo", "JC-01", ["山手線", "京浜東北線", "東海道線", "新幹線"]),
    ("神田", "かんだ", 1.3, "Kanda", "JC-02", ["山手線", "銀座線"]),
    ("御茶ノ水", "おちゃのみず", 2.6, "Ochanomizu", "JC-03", ["総武線", "丸ノ内線"]),
    ("四ツ谷", "よつや", 6.6, "Yotsuya", "JC-04", ["総武線", "丸ノ内線", "南北線"]),
    ("新宿", "しんじゅく", 10.3, "Shinjuku", "JC-05", ["山手線", "埼京線", "丸ノ内線", "小田急線", "京王線"]),
    ("中野", "なかの", 14.7, "Nakano", "JC-06", ["東西線"]),
    ("高円寺", "こうえんじ", 16.1, "Koenji", "JC-07", []),
    ("阿佐ケ谷", "あさがや", 17.2, "Asagaya", "JC-08", []),
    ("荻窪", "おぎくぼ", 18.6, "Ogikubo", "JC-09", ["丸ノ内線"]),
    ("西荻窪", "にしおぎくぼ", 20.6, "Nishi-Ogikubo", "JC-10", []),
    ("吉祥寺", "きちじょうじ", 22.5, "Kichijoji", "JC-11", ["井の頭線"]),
    ("三鷹", "みたか", 24.1, "Mitaka", "JC-12", []),
    ("武蔵境", "むさしさかい", 25.7, "Musashi-Sakai", "JC-13", ["西武多摩川線"]),
    ("東小金井", "ひがしこがねい", 27.4, "Higashi-Koganei", "JC-14", []),
    ("武蔵小金井", "むさしこがねい", 29.1, "Musashi-Koganei", "JC-15", []),
    ("国分寺", "こくぶんじ", 31.6, "Kokubunji", "JC-16", ["西武国分寺線", "西武多摩湖線"]),
    ("西国分寺", "にしこくぶんじ", 33.3, "Nishi-Kokubunji", "JC-17", ["武蔵野線"]),
    ("国立", "くにたち", 35.0, "Kunitachi", "JC-18", []),
    ("立川", "たちかわ", 36.9, "Tachikawa", "JC-19", ["南武線", "青梅線", "多摩モノレール"]),
    ("日野", "ひの", 40.6, "Hino", "JC-20", []),
    ("豊田", "とよだ", 43.1, "Toyoda", "JC-21", []),
    ("八王子", "はちおうじ", 47.4, "Hachioji", "JC-22", ["横浜線", "八高線", "京王線"]),
    ("西八王子", "にしはちおうじ", 50.0, "Nishi-Hachioji", "JC-23", []),
    ("高尾", "たかお", 53.1, "Takao", "JC-24", ["中央本線", "京王高尾線"]),
]

CHUO = Line(
    key="chuo", name="中央線快速", kana="ちゅうおうせんかいそく", en="Chuo Line",
    stations=CHUO_STATIONS,
    kinds=[
        Kind("快速", "かいそく", en="Rapid"),
        Kind("特別快速", "とくべつかいそく", stops={
            "東京", "神田", "御茶ノ水", "四ツ谷", "新宿", "中野", "三鷹",
            "国分寺", "立川", "八王子", "西八王子", "高尾"}, en="Special Rapid"),
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
    key="fukutoshin", name="副都心線", kana="ふくとしんせん", en="Fukutoshin Line",
    stations=[
        ("和光市", "わこうし", 0.0, "Wakoshi", "F-01", ["東武東上線", "有楽町線"]),
        ("地下鉄成増", "ちかてつなります", 2.2, "Chikatetsu-narimasu", "F-02", ["有楽町線"]),
        ("地下鉄赤塚", "ちかてつあかつか", 3.6, "Chikatetsu-akatsuka", "F-03", ["有楽町線"]),
        ("平和台", "へいわだい", 5.4, "Heiwadai", "F-04", ["有楽町線"]),
        ("氷川台", "ひかわだい", 6.8, "Hikawadai", "F-05", ["有楽町線"]),
        ("小竹向原", "こたけむかいはら", 8.3, "Kotake-mukaihara", "F-06", ["有楽町線", "西武有楽町線"]),
        ("千川", "せんかわ", 9.3, "Senkawa", "F-07", ["有楽町線"]),
        ("要町", "かなめちょう", 10.3, "Kanamecho", "F-08", ["有楽町線"]),
        ("池袋", "いけぶくろ", 11.3, "Ikebukuro", "F-09", ["山手線", "丸ノ内線", "有楽町線", "東武東上線", "西武池袋線"]),
        ("雑司が谷", "ぞうしがや", 12.5, "Zoshigaya", "F-10", ["都電荒川線"]),
        ("西早稲田", "にしわせだ", 14.1, "Nishi-waseda", "F-11", []),
        ("東新宿", "ひがししんじゅく", 15.5, "Higashi-shinjuku", "F-12", ["大江戸線"]),
        ("新宿三丁目", "しんじゅくさんちょうめ", 16.6, "Shinjuku-sanchome", "F-13", ["丸ノ内線", "新宿線"]),
        ("北参道", "きたさんどう", 17.8, "Kita-sando", "F-14", []),
        ("明治神宮前", "めいじじんぐうまえ", 19.0, "Meiji-jingumae", "F-15", ["千代田線", "山手線"]),
        ("渋谷", "しぶや", 20.2, "Shibuya", "F-16", ["山手線", "銀座線", "半蔵門線", "東急東横線", "田園都市線", "井の頭線"]),
    ],
    kinds=[
        Kind("各駅停車", "かくえきていしゃ", en="Local"),
        Kind("急行", "きゅうこう", stops={
            "和光市", "小竹向原", "池袋", "新宿三丁目", "明治神宮前", "渋谷"}, en="Express"),
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
