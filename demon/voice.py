"""車内放送の肉声 - an announcer borrowed from a local VOICEVOX engine.

announce.py speaks in formants: the shape of a station name with none of its
words. This is the other option - a real singing-synth voice (VOICEVOX, or
anything that speaks its HTTP API, such as AivisSpeech) running on this
machine. The daemon still carries no audio and still never reaches the
internet: it talks to 127.0.0.1 only, and if nothing answers there it goes
back to the formants without a word.

What comes back from the engine is a clean studio voice, which is wrong for a
carriage. So it goes through the same small ceiling speaker and steel tube as
the formant voice - band-limited to the PA, two short reflections - before it
reaches the mixer as one buffer.

Rendered sentences are kept in ~/.demon/voice/. Station announcements repeat
on every ride, so after the first lap the engine does not even need to be
running. Nothing in that folder comes from your typing: it is the engine's
output for fixed sentences about stations.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
import wave

import numpy as np

from .announce import pa_response
from .dsp import normalize

DEFAULT_URL = "http://127.0.0.1:50021"     # VOICEVOX. AivisSpeech is :10101
DEFAULT_SPEAKER = 3                         # ずんだもん（ノーマル）

# An announcer reads at an even pace and does not perform.
QUERY = {"speedScale": 1.05, "intonationScale": 0.9,
         "prePhonemeLength": 0.05, "postPhonemeLength": 0.15}


def katakana(kana):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in kana)


def cache_dir():
    return os.path.join(os.path.expanduser("~"), ".demon", "voice")


class Voicevox:
    """A thin client for the VOICEVOX engine API. Standard library only."""

    def __init__(self, url=DEFAULT_URL, speaker=DEFAULT_SPEAKER, timeout=20.0):
        self.url = url.rstrip("/")
        self.speaker = int(speaker)
        self.timeout = timeout
        self.credit = None
        self.online = False
        # No proxies: the engine is on this machine, and nothing here should
        # ever be routed anywhere else.
        self._open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

    def _call(self, path, params=None, body=None, timeout=None):
        q = "?" + urllib.parse.urlencode(params) if params else ""
        get = path in ("/version", "/speakers")
        data = None if get else json.dumps(body).encode("utf-8") if body else b""
        req = urllib.request.Request(
            self.url + path + q, data=data, method="GET" if get else "POST",
            headers={"Content-Type": "application/json"})
        with self._open(req, timeout=timeout or self.timeout) as r:
            return r.read()

    def probe(self):
        """True if the engine answers. Fills in the credit line on the way."""
        try:
            self._call("/version", timeout=1.5)
        except Exception:
            return False
        name = "ID %d" % self.speaker
        try:
            for sp in json.loads(self._call("/speakers", timeout=3.0)):
                for st in sp.get("styles", []):
                    if st.get("id") == self.speaker:
                        name = "%s（%s）" % (sp.get("name"), st.get("name"))
        except Exception:
            pass
        self.credit = "VOICEVOX:%s" % name
        self.online = True
        return True

    def wav(self, text, sr):
        """text -> WAV bytes, synthesised straight at the mixer's rate."""
        query = json.loads(self._call(
            "/audio_query", {"text": text, "speaker": self.speaker}))
        query.update(QUERY)
        query["outputSamplingRate"] = int(sr)
        query["outputStereo"] = False
        return self._call("/synthesis", {"speaker": self.speaker}, body=query)


class VoicedAnnouncer:
    """Same render() as announce.Announcer, with a real voice in front of it.

    `readings` maps station and service names to kana. The engine gets the
    Japanese sentence with kanji intact - that is what gives it a natural
    accent - except for the names, which go in as katakana, because 四ツ谷 and
    雑司が谷 are exactly the words a dictionary gets wrong.
    """

    def __init__(self, engine, fallback, sr, readings=None):
        self.engine = engine
        self.fallback = fallback
        self.sr = sr
        self.alive = engine.online     # off: only what is already in the cache
        self._names = None
        self._readings = {}
        if readings:
            self._readings = {k: katakana(v) for k, v in readings.items()}
            alts = sorted(self._readings, key=len, reverse=True)
            self._names = re.compile("|".join(re.escape(a) for a in alts))

    def script(self, text):
        if self._names is None:
            return text
        return self._names.sub(lambda m: self._readings[m.group(0)], text)

    def _load(self, text):
        line = self.script(text)
        key = hashlib.sha1(("%d|%d|%s|%s" % (
            self.engine.speaker, self.sr, json.dumps(QUERY, sort_keys=True),
            line)).encode("utf-8")).hexdigest()[:20]
        path = os.path.join(cache_dir(), "%d-%s.wav" % (self.engine.speaker, key))
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            pass
        if not self.alive:
            raise ConnectionError("engine is away")
        try:
            data = self.engine.wav(line, self.sr)
        except Exception:
            self.alive = False       # stop waiting on it for the rest of the ride
            raise
        try:
            os.makedirs(cache_dir(), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
        except OSError:
            pass                     # a cache is not worth failing a sentence over
        return data

    def _decode(self, data):
        with wave.open(io.BytesIO(data)) as w:
            rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
        if width != 2:
            raise ValueError("unexpected sample width %d" % width)
        y = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        if ch > 1:
            y = y.reshape(-1, ch).mean(axis=1)
        if rate != self.sr:
            n = int(round(y.shape[0] * self.sr / rate))
            y = np.interp(np.arange(n) * (rate / self.sr), np.arange(y.shape[0]), y)
        return y

    def render(self, phrases, room=0.35, text=None):
        if text is None:
            return self.fallback.render(phrases, room)
        try:
            y = self._decode(self._load(text))
        except Exception:
            return self.fallback.render(phrases, room)

        sr = self.sr
        # Into the ceiling speaker. This runs on the speaker thread, once per
        # sentence, so a whole-buffer FFT is fine here.
        pad = int(0.45 * sr)
        n = y.shape[0] + pad
        spec = np.fft.rfft(y, n)
        spec *= pa_response(np.fft.rfftfreq(n, 1.0 / sr))
        out = np.fft.irfft(spec, n)
        if room > 0.0:
            dry = out.copy()
            for delay, g in ((0.019, 0.42), (0.037, 0.26), (0.061, 0.15)):
                d = int(delay * sr)
                out[d:] += dry[: n - d] * (g * room)
        return normalize(out, 0.92)
