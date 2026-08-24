"""Turning keystrokes into something a demon can eat.

Privacy note, and it is a design constraint rather than a disclaimer: the
listener reduces every key to one of five coarse categories and throws the key
object away in the same expression.  No character, no keycode, no window
title, and no timestamp is stored, buffered to disk, or sent anywhere.  What
survives the callback is a category enum in an in-memory ring buffer that the
audio thread drains ~90 times a second.
"""
from __future__ import annotations

import threading
from collections import deque

from .dsp import clamp, ema_alpha

CHAR, SPACE, BACKSPACE, ENTER = range(4)

KIND_NAMES = {CHAR: "char", SPACE: "space", BACKSPACE: "backspace", ENTER: "enter"}


class Rhythm:
    """Rolling features of the typing stream - the demon's food.

    kps        keys per second, smoothed
    intensity  kps normalised to 0..1 (the instantaneous drive)
    flow       slow accumulator: how long you have been *sustaining* it
    error      fraction of keystrokes that are corrections
    idle       seconds since the last key
    sustain    seconds of continuous flow, for long-haul easter eggs
    """

    TARGET_KPS = 6.0

    def __init__(self):
        self.kps = 0.0
        self.back_kps = 0.0
        self.intensity = 0.0
        self.flow = 0.0
        self.error = 0.0
        self.idle = 999.0
        self.sustain = 0.0
        self.total = 0

    def update(self, dt, kinds):
        n = len(kinds)
        nb = sum(1 for k in kinds if k == BACKSPACE)

        self.kps += ema_alpha(dt, 1.2) * (n / dt - self.kps)
        self.back_kps += ema_alpha(dt, 6.0) * (nb / dt - self.back_kps)
        self.idle = 0.0 if n else self.idle + dt
        self.total += n

        self.intensity = clamp(self.kps / self.TARGET_KPS)
        target = 1.0 if self.intensity > 0.12 else 0.0
        self.flow += ema_alpha(dt, 9.0 if target > self.flow else 6.0) * (target - self.flow)
        self.error = clamp(self.back_kps / max(self.kps, 0.4))
        self.sustain = self.sustain + dt if self.flow > 0.5 else max(0.0, self.sustain - dt * 3.0)


class KeyWatcher:
    """Global key listener via pynput, categories only (see module docstring)."""

    def __init__(self):
        self._queue = deque(maxlen=1024)
        self._listener = None
        self._lock = threading.Lock()

    def start(self):
        from pynput import keyboard  # imported late so --render works headless

        key_cls = keyboard.Key
        ignored = {
            key_cls.shift, key_cls.shift_r, key_cls.shift_l,
            key_cls.ctrl, key_cls.ctrl_l, key_cls.ctrl_r,
            key_cls.alt, key_cls.alt_l, key_cls.alt_r, key_cls.alt_gr,
            key_cls.cmd, key_cls.cmd_r, key_cls.caps_lock,
        }
        corrections = {key_cls.backspace, key_cls.delete}
        newlines = {key_cls.enter}

        def on_press(key):
            # The only thing that leaves this function is an int in 0..3.
            if key in ignored:
                return
            if key in corrections:
                kind = BACKSPACE
            elif key in newlines:
                kind = ENTER
            elif key == key_cls.space:
                kind = SPACE
            else:
                kind = CHAR
            self._queue.append(kind)

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()
        return self

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def poll(self, dt):
        return self.drain()

    def drain(self):
        out = []
        try:
            while True:
                out.append(self._queue.popleft())
        except IndexError:
            pass
        return out


class ScriptedTypist:
    """Deterministic fake typist, for offline rendering and for `--demo`.

    Alternates between bursts of work and pauses so every state of the demon
    (spin-up, cruise, correction, newline, full stop) shows up in a short run.
    """

    def __init__(self, rng, script=None):
        self.rng = rng
        self.t = 0.0
        self._due = 0.0
        # (duration, keys-per-second) - a plausible half minute of coding
        self.script = script or [
            (3.0, 0.0), (9.0, 5.5), (2.0, 0.0), (7.0, 7.5),
            (4.0, 1.5), (10.0, 6.5), (12.0, 0.0), (8.0, 4.0),
        ]

    def _rate_at(self, t):
        span = sum(d for d, _ in self.script)
        t = t % span
        for dur, rate in self.script:
            if t < dur:
                return rate
            t -= dur
        return 0.0

    def poll(self, dt):
        return self.drain_for(dt)

    def drain_for(self, dt):
        rate = self._rate_at(self.t)
        self.t += dt
        out = []
        if rate <= 0.0:
            self._due = 0.0
            return out
        self._due += rate * dt
        while self._due >= 1.0:
            self._due -= 1.0
            r = self.rng.random()
            out.append(BACKSPACE if r < 0.07 else ENTER if r < 0.12 else SPACE if r < 0.28 else CHAR)
        return out
