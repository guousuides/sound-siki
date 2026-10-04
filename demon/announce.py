"""車内放送 - an announcer with no recordings and no text-to-speech.

The constraint is the whole point: this daemon carries zero bytes of audio and
opens no sockets, so the announcer cannot be a WAV and cannot be the operating
system's TTS.  What it can be is arithmetic.

Japanese is a mora-timed language built from a very small inventory, so a
station name is a rhythm of about seven moras a second over five vowels. Each
vowel is additive synthesis: harmonics of one pitch, scaled by three formant
resonances, band-limited to the 300-3400 Hz of a carriage PA. Consonants are
four gestures in front of the vowel - a burst, a hiss, a hum, a glide - which
is coarse but carries the syllable boundaries, and the boundaries are what make
it read as speech.

You will not make out a word of it, and that is deliberate: the *meaning* goes
to the terminal in Japanese, where reading it costs nothing. What comes out of
the speakers is the shape - the length of the name, the rise onto it, the fall
off the end - which is the part you actually recognise when you are half
listening on a train.

Everything above is precomputed. An announcement is assembled into a single
buffer of a few seconds and handed to the mixer as one voice, so the realtime
path never grows a per-syllable cost.
"""
from __future__ import annotations

import numpy as np

from .dsp import TWO_PI, band, noise_loop, normalize, peak

# vowels, in the order the tables below use
A, I, U, E, O = range(5)
VOWELS = "aiueo"

# consonant gestures in front of a vowel
C_NONE, C_STOP, C_FRIC, C_NASAL, C_GLIDE = range(5)

# Formants (F1, F2, F3) in Hz. A carriage announcer sits fairly high, so these
# are on the bright side of neutral.
FORMANTS = {
    A: (820, 1300, 2750),
    I: (330, 2300, 3000),
    U: (360, 1250, 2250),
    E: (520, 1900, 2600),
    O: (520, 920, 2550),
}

MORA = 0.132        # seconds between mora onsets (~7.6 mora/s)
GAP = 0.085         # っ
PAUSE = 0.26        # 、 and the end of a phrase
ONSET = {C_NONE: 0.0, C_STOP: 0.048, C_FRIC: 0.078, C_NASAL: 0.055, C_GLIDE: 0.026}

# kana -> (consonant gesture, vowel). Only what station names and the standard
# announcements actually need, which is nearly all of it anyway.
KANA = {}


def _row(chars, cls, vowels="aiueo"):
    for ch, v in zip(chars, vowels):
        KANA[ch] = (cls, VOWELS.index(v))


_row("あいうえお", C_NONE)
_row("かきくけこ", C_STOP)
_row("がぎぐげご", C_STOP)
_row("さすせそ", C_FRIC, "auoe"[0:0] or "aueo")   # し is palatal, set below
KANA["し"] = (C_FRIC, I)
_row("ざずぜぞ", C_FRIC, "aueo")
KANA["じ"] = (C_FRIC, I)
_row("たてと", C_STOP, "aeo")
KANA["ち"] = (C_FRIC, I)
KANA["つ"] = (C_FRIC, U)
_row("だでど", C_STOP, "aeo")
KANA["ぢ"], KANA["づ"] = (C_FRIC, I), (C_FRIC, U)
_row("なにぬねの", C_NASAL)
_row("はひふへほ", C_FRIC)
_row("ばびぶべぼ", C_STOP)
_row("ぱぴぷぺぽ", C_STOP)
_row("まみむめも", C_NASAL)
_row("やゆよ", C_GLIDE, "auo")
_row("らりるれろ", C_GLIDE)
KANA["わ"] = (C_GLIDE, A)
KANA["を"] = (C_NONE, O)
for small, big in zip("ぁぃぅぇぉ", "あいうえお"):
    KANA[small] = KANA[big]

SMALL_Y = {"ゃ": A, "ゅ": U, "ょ": O}


def pa_response(f):
    """The carriage speaker: a small cone behind a grille in the ceiling."""
    return band(f, 330, 3300, 0.65) * (1.0 + 0.55 * peak(f, 1500, 1.4, 1.0))


class Mora:
    """One beat of speech: a gesture, a vowel, and how long to hold it."""

    __slots__ = ("cls", "vowel", "hold", "kind")

    def __init__(self, cls, vowel, hold=1.0, kind="mora"):
        self.cls = cls
        self.vowel = vowel
        self.hold = hold
        self.kind = kind          # mora / nasal / gap / pause


def split_moras(kana):
    """Kana -> beats. Handles 拗音, 促音, 撥音, 長音 and punctuation."""
    out = []
    i = 0
    while i < len(kana):
        ch = kana[i]
        nxt = kana[i + 1] if i + 1 < len(kana) else ""
        if ch in "、。 　":
            out.append(Mora(C_NONE, A, 1.0, "pause"))
        elif ch == "っ":
            out.append(Mora(C_NONE, A, 1.0, "gap"))
        elif ch == "ん":
            out.append(Mora(C_NASAL, U, 1.0, "nasal"))
        elif ch == "ー":
            if out and out[-1].kind == "mora":
                out.append(Mora(C_NONE, out[-1].vowel, 1.0))
        elif ch in KANA:
            cls, vowel = KANA[ch]
            if nxt in SMALL_Y:                 # きゃ, しゅ, ちょ ...
                vowel = SMALL_Y[nxt]
                i += 1
            out.append(Mora(cls, vowel))
        i += 1
    return out


# --------------------------------------------------------------------------
# contours - what separates "a string of syllables" from "an announcement"
# --------------------------------------------------------------------------
def contour(style, k, n):
    """Pitch band (0 low, 1 mid, 2 high) for mora k of n in a phrase."""
    if n <= 1:
        return 1
    t = k / (n - 1)
    if style == "name":
        # 駅名は頭から二拍目で持ち上げて、あとは落とす
        return 2 if 0.08 < t < 0.55 else (1 if t < 0.85 else 0)
    if style == "end":
        return 1 if t < 0.35 else 0
    if style == "lead":                        # 「まもなく、」「つぎは、」
        return 1 if t < 0.6 else 2
    return 1 if t < 0.75 else 0                # plain declarative


class Announcer:
    """A precomputed voice. One per session - the conductor does not change."""

    def __init__(self, sr, rng, f0=None):
        self.sr = sr
        self.rng = rng
        # Today's conductor: a low voice or a high one, decided once.
        self.f0 = float(f0 if f0 is not None else rng.choice([116.0, 198.0]))
        self.bands = (0.90, 1.0, 1.13)
        self._vowels = {}
        self._onsets = {}
        self._nasal = None

    # ---------------------------------------------------------------- build
    def prepare(self):
        for band_i, mul in enumerate(self.bands):
            for v in range(5):
                self._vowels[(band_i, v)] = self._make_vowel(v, self.f0 * mul)
        self._onsets[C_STOP] = self._make_burst()
        self._onsets[C_FRIC] = self._make_hiss()
        self._onsets[C_GLIDE] = self._make_glide()
        self._nasal = self._make_nasal(self.f0)
        self._onsets[C_NASAL] = self._nasal[: int(0.055 * self.sr)].copy()
        return self

    def _pa(self, f):
        return pa_response(f)

    def _make_vowel(self, v, f0, seconds=0.175):
        """Additive synthesis: harmonics of f0 through three formants."""
        sr = self.sr
        n = int(round(seconds * sr))
        t = np.arange(n, dtype=np.float64) / sr
        f1, f2, f3 = FORMANTS[v]
        y = np.zeros(n, dtype=np.float64)
        k = 1
        while k * f0 < 4200.0:
            f = k * f0
            g = (peak(f, f1, 9.0, 1.0) + peak(f, f2, 8.0, 0.72)
                 + peak(f, f3, 7.0, 0.34)) * self._pa(f) / k ** 0.85
            if g > 1e-4:
                y += g * np.sin(TWO_PI * f * t + self.rng.uniform(0.0, TWO_PI))
            k += 1
        # A little breath so it is not a pure organ, and a vowel-shaped envelope:
        # quick on, held, then let go - the release is what makes moras legato.
        y += 0.035 * y.std() * self.rng.standard_normal(n)
        env = np.minimum(t / 0.018, 1.0) * np.minimum(
            1.0, np.clip((seconds - t) / 0.050, 0.0, 1.0))
        env *= 1.0 - 0.10 * np.sin(np.pi * t / seconds) ** 2     # slight sag
        return normalize(y * env, 0.85)

    def _make_burst(self):
        sr, n = self.sr, int(round(0.026 * self.sr))
        y = noise_loop(0.026, sr, lambda f: band(f, 900, 6500, 0.7) * self._pa(f), self.rng)
        t = np.arange(n) / sr
        return normalize(y[:n] * np.exp(-t / 0.006), 0.55)

    def _make_hiss(self):
        sr, n = self.sr, int(round(0.082 * self.sr))
        y = noise_loop(0.082, sr, lambda f: band(f, 2200, 7500, 0.6) * self._pa(f), self.rng)
        t = np.arange(n) / sr
        env = np.minimum(t / 0.012, 1.0) * np.clip((0.082 - t) / 0.022, 0.0, 1.0)
        return normalize(y[:n] * env, 0.42)

    def _make_glide(self):
        """ら行・や行: a brief formant smear, not a burst and not a hiss."""
        sr, n = self.sr, int(round(0.030 * self.sr))
        y = noise_loop(0.030, sr, lambda f: band(f, 400, 1800, 0.9) * self._pa(f), self.rng)
        t = np.arange(n) / sr
        return normalize(y[:n] * np.minimum(t / 0.006, 1.0)
                         * np.clip((0.030 - t) / 0.014, 0.0, 1.0), 0.45)

    def _make_nasal(self, f0, seconds=0.135):
        sr, n = self.sr, int(round(0.135 * self.sr))
        t = np.arange(n, dtype=np.float64) / sr
        y = np.zeros(n, dtype=np.float64)
        k = 1
        while k * f0 < 1600.0:
            f = k * f0
            g = (peak(f, 250, 6.0, 1.0) + peak(f, 1050, 9.0, 0.22)) * self._pa(f) / k
            y += g * np.sin(TWO_PI * f * t + self.rng.uniform(0.0, TWO_PI))
            k += 1
        env = np.minimum(t / 0.020, 1.0) * np.clip((seconds - t) / 0.045, 0.0, 1.0)
        return normalize(y * env, 0.6)

    # ---------------------------------------------------------------- speak
    def render(self, phrases, room=0.35, text=None):
        """(kana, style) pairs -> one mono buffer, PA reflections included.

        Assembling the whole announcement here rather than scheduling a voice
        per syllable keeps the mixer's voice count flat: a twenty-mora sentence
        costs the realtime path exactly one voice, same as a rail joint.

        `text` is the sentence as written. Formants cannot read, so it is
        ignored here; voice.VoicedAnnouncer is the one that uses it.
        """
        sr = self.sr
        plan, t = [], 0.0
        for kana, style in phrases:
            moras = [m for m in split_moras(kana)]
            speech = [m for m in moras if m.kind in ("mora", "nasal")]
            k = 0
            for m in moras:
                if m.kind == "pause":
                    t += PAUSE
                    continue
                if m.kind == "gap":
                    t += GAP
                    continue
                lvl = contour(style, k, len(speech))
                plan.append((t, m, lvl))
                t += MORA * (1.12 if m.kind == "nasal" else 1.0)
                k += 1
            t += PAUSE

        total = int((t + 0.45) * sr)
        out = np.zeros(total, dtype=np.float32)

        def stamp(buf, at, gain, rate=1.0):
            start = int(at * sr)
            if start < 0 or gain <= 0.0:
                return
            if rate != 1.0:
                idx = np.arange(0, buf.shape[0] - 1, rate)
                i0 = idx.astype(np.int64)
                frac = (idx - i0).astype(np.float32)
                buf = buf[i0] * (1.0 - frac) + buf[i0 + 1] * frac
            end = min(start + buf.shape[0], total)
            if end > start:
                out[start:end] += buf[: end - start] * gain

        for at, m, lvl in plan:
            jitter = float(self.rng.uniform(-0.008, 0.008))
            rate = float(self.rng.uniform(0.985, 1.015))
            if m.kind == "nasal":
                stamp(self._nasal, at + jitter, 0.9, rate)
                continue
            onset = ONSET[m.cls]
            if m.cls in self._onsets:
                stamp(self._onsets[m.cls], at + jitter, 1.0, rate)
            stamp(self._vowels[(lvl, m.vowel)], at + jitter + onset,
                  float(self.rng.uniform(0.88, 1.0)), rate)

        # The carriage is a steel tube with a hard floor. Two short taps are
        # enough to put the voice in it; a real reverb would be a filter in the
        # realtime path, which this design does not have and does not want.
        if room > 0.0:
            dry = out.copy()
            for delay, g in ((0.019, 0.42), (0.037, 0.26), (0.061, 0.15)):
                d = int(delay * sr)
                out[d:] += dry[: total - d] * (g * room)
        return normalize(out, 0.92)


# --------------------------------------------------------------------------
# what the announcer actually says - text for the terminal, kana for the voice
# --------------------------------------------------------------------------
def _side(name):
    """Which side the doors open. Not survey data; stable per station name."""
    return "右" if sum(ord(c) for c in name) % 2 else "左"


def departure(kind, dest, nxt, final=False):
    text = "この電車は、%s、%sゆきです。次は、%s。" % (kind.name, dest.name, nxt.name)
    kana = [("このでんしゃは、", "plain"), (kind.kana + "、", "plain"),
            (dest.kana + "ゆきです。", "plain"),
            ("つぎは、", "lead"), (nxt.kana + "。", "name")]
    if final:
        text = "この電車は、%s、%sゆきです。次は、終点、%s。" % (
            kind.name, dest.name, nxt.name)
        kana = kana[:3] + [("つぎは、しゅうてん、", "lead"), (nxt.kana + "。", "name")]
    return text, kana


def next_stop(nxt, final=False):
    if final:
        return ("次は、終点、%s。" % nxt.name,
                [("つぎは、しゅうてん、", "lead"), (nxt.kana + "。", "name")])
    return ("次は、%s。" % nxt.name,
            [("つぎは、", "lead"), (nxt.kana + "。", "name")])


def approaching(stop, final=False):
    head = "まもなく、終点、%s" % stop.name if final else "まもなく、%s" % stop.name
    text = "%s、%sです。お出口は%s側です。" % (head, stop.name, _side(stop.name))
    lead = "まもなく、しゅうてん、" if final else "まもなく、"
    return text, [(lead, "lead"), (stop.kana + "、", "name"),
                  (stop.kana + "です。", "plain"),
                  ("おでぐちは%sがわです。" % ("みぎ" if _side(stop.name) == "右" else "ひだり"),
                   "end")]


def arrival(stop):
    return ("%s、%sです。" % (stop.name, stop.name),
            [(stop.kana + "、", "name"), (stop.kana + "です。", "end")])


def terminus(stop):
    return ("終点、%s。ご乗車ありがとうございました。" % stop.name,
            [("しゅうてん、", "lead"), (stop.kana + "。", "name"),
             ("ごじょうしゃありがとうございました。", "end")])


def held():
    return ("お客様にお知らせいたします。ただいま、お客様対応のため、"
            "当駅にてしばらく停車しております。",
            [("おきゃくさまにおしらせいたします。", "plain"),
             ("ただいま、おきゃくさまたいおうのため、", "plain"),
             ("とうえきにてしばらくていしゃしております。", "end")])


class Speaker:
    """Renders announcements off the audio thread.

    Assembling a sentence costs a few milliseconds - nothing, unless you spend
    it inside a 46 ms audio callback, where it is a third of the budget and an
    underrun waiting for a slow machine. So the callback posts a request and
    picks the finished buffer up a block or two later, which for a station
    announcement is inaudible.
    """

    def __init__(self, announcer):
        import threading
        from collections import deque

        self.announcer = announcer
        self._in = deque()
        self._out = deque()
        self._wake = threading.Event()
        self._alive = True
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._alive = False
        self._wake.set()

    def request(self, phrases, room=0.35, text=None):
        self._in.append((phrases, room, text))
        self._wake.set()

    def poll(self):
        return self._out.popleft() if self._out else None

    def _loop(self):
        while self._alive:
            self._wake.wait(0.5)
            self._wake.clear()
            while self._in and self._alive:
                phrases, room, text = self._in.popleft()
                try:
                    self._out.append(self.announcer.render(phrases, room, text))
                except Exception:
                    pass          # a missed announcement must never stop the ride


def signal_hold():
    return ("お待たせしております。ただいま、前方の信号が赤のため、停車しております。",
            [("おまたせしております。", "plain"),
             ("ただいま、ぜんぽうのしんごうがあかのため、", "plain"),
             ("ていしゃしております。", "end")])
