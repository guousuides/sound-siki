"""蝉デーモン - the afternoon chorus outside the window in Kyoto.

Coupling
--------
The cicadas are an ecosystem and your concentration is the weather. Individual
insects fade in as `flow` rises, so the chorus thickens only after you have
been working steadily for a while - and thins out the moment you stop. It
rewards sustained attention rather than a burst of speed.

  flow          -> how many individuals are singing (1 distant one .. a wall)
  Backspace     -> the nearest few fall silent, startled, then creep back
  Enter         -> a wind chime on the veranda
  20 min of flow-> a higurashi joins, and the afternoon starts turning to dusk

Every voice is one precomputed phrase loop played at a slightly different rate
with a different pan and start offset, which is how a handful of buffers turns
into a chorus that never repeats audibly.
"""
from __future__ import annotations

import numpy as np

from ..dsp import (Loop, StereoBed, Voices, add_panned, band, clamp,
                   damped_sine, ema_alpha, env_ad, noise_loop, normalize,
                   peak, tilt)
from ..keywatch import BACKSPACE, ENTER
from .base import Demon, bar

N_VOICES = 10
HIGURASHI_AFTER = 20 * 60.0   # seconds of sustained flow before dusk sets in


class _Voice:
    __slots__ = ("loop", "rate", "pan", "level", "hush", "species", "far")

    def __init__(self, loop, rate, pan, species, far=0.0):
        self.loop = loop
        self.rate = rate
        self.pan = pan
        self.species = species
        self.far = far      # 0 = right outside the window, 1 = across the valley
        self.level = 0.0
        self.hush = 0.0


class CicadaDemon(Demon):
    name = "cicada"
    title = "蝉デーモン"
    blurb = "集中が続くほど個体数が増える蝉時雨。Backspaceで蝉が驚いて鳴き止む。"

    def __init__(self, sr, rng):
        super().__init__(sr, rng)
        self._dusk = 0.0
        self._disturb = 0.0   # backspace pressure, decays away between bursts
        self._cooldown = 0.0
        self._chime_wait = 20.0

    # ---------------------------------------------------------------- setup
    def prepare(self):
        sr, rng = self.sr, self.rng

        abura = self._make_abura()
        minmin = self._make_minmin()
        higurashi = self._make_higurashi()

        self.chorus = StereoBed(self._make_chorus())
        self.heat = StereoBed(noise_loop(
            8.0, sr, lambda f: band(f, 30, 380, 1.0) * tilt(f, 120, -0.8), rng))

        self.voices_pool = []
        for i in range(N_VOICES):
            near = i / max(1, N_VOICES - 1)          # 0 = close by, 1 = far off
            species, src = ("abura", abura) if i % 5 != 2 else ("minmin", minmin)
            voice = _Voice(Loop(src), rate=float(rng.uniform(0.93, 1.08)),
                           pan=float(rng.uniform(-0.85, 0.85)), species=species, far=near)
            voice.loop.pos = float(rng.uniform(0, src.shape[0]))
            self.voices_pool.append(voice)

        self.higurashi = _Voice(Loop(higurashi), 1.0, 0.55, "higurashi")
        self.higurashi.loop.pos = float(rng.uniform(0, higurashi.shape[0]))

        self.furin = self._make_furin()
        self.oneshots = Voices(limit=8)

    def _make_abura(self):
        """アブラゼミ: a continuous fry, amplitude-modulated around 68 Hz."""
        sr, rng = self.sr, self.rng
        n = int(round(4.0 * sr))
        t = np.arange(n) / sr
        carrier = noise_loop(
            4.0, sr, lambda f: band(f, 2600, 8200, 0.55)
            * (1.0 + peak(f, 4300, 3.0, 1.2) + peak(f, 6400, 4.0, 0.5)), rng)
        am = 0.5 + 0.5 * np.sin(2 * np.pi * 68.0 * t)     # 272 whole cycles in 4 s
        am = am ** 1.7
        wobble = 0.8 + 0.2 * np.sin(2 * np.pi * 0.75 * t)  # 3 whole cycles in 4 s
        return normalize(carrier * am * wobble)

    def _make_minmin(self):
        """ミンミンゼミ: a long 'miii' opening into a run of 'min-min-min'."""
        sr, rng = self.sr, self.rng
        n = int(round(4.0 * sr))
        t = np.arange(n) / sr
        noise = noise_loop(
            4.0, sr, lambda f: band(f, 2000, 5400, 0.5)
            * (1.0 + peak(f, 2850, 6.0, 1.3) + peak(f, 3650, 6.0, 0.8)), rng)
        tonal = (np.sin(2 * np.pi * 2860 * t) * 0.22 + np.sin(2 * np.pi * 3620 * t) * 0.12)
        carrier = noise + tonal.astype(np.float32)

        phrase = np.clip(t / 0.75, 0.0, 1.0) * np.clip((3.45 - t) / 0.45, 0.0, 1.0)
        phrase = np.where(t > 3.45, 0.0, phrase)
        depth = np.clip((t - 0.85) / 0.35, 0.0, 1.0) * 0.85   # 'min-min' only later on
        am = 1.0 - depth * (0.5 + 0.5 * np.cos(2 * np.pi * 9.5 * t)) ** 1.4
        return normalize(carrier * phrase * am)

    def _make_higurashi(self):
        """ヒグラシ: the descending 'kana-kana-kana' that means the day is ending."""
        sr, rng = self.sr, self.rng
        n = int(round(4.0 * sr))
        t = np.arange(n) / sr
        carrier = noise_loop(
            4.0, sr, lambda f: band(f, 1800, 4200, 0.45)
            * (1.0 + peak(f, 2350, 9.0, 1.6) + peak(f, 4700, 9.0, 0.5)), rng)
        tonal = np.sin(2 * np.pi * 2340 * t * (1.0 - 0.03 * t / 4.0)) * 0.45
        pulse = (0.5 + 0.5 * np.cos(2 * np.pi * 11.0 * t)) ** 2.2
        phrase = np.clip(t / 0.9, 0.0, 1.0) * np.clip((3.7 - t) / 0.8, 0.0, 1.0)
        phrase = np.where(t > 3.7, 0.0, phrase)
        return normalize((carrier + tonal.astype(np.float32)) * pulse * phrase)

    def _make_chorus(self):
        """The far-off wall of cicadas that is always there on a hot day."""
        sr, rng = self.sr, self.rng
        n = int(round(8.0 * sr))
        t = np.arange(n) / sr
        bed = noise_loop(
            8.0, sr, lambda f: band(f, 2800, 6800, 0.7) * (1.0 + peak(f, 4400, 2.0, 0.6)), rng)
        wobble = 0.72 + 0.28 * np.sin(2 * np.pi * 0.375 * t)  # 3 whole cycles in 8 s
        return normalize(bed * wobble)

    def _make_furin(self):
        """風鈴: a glass wind chime, three inharmonic partials with a slow beat."""
        sr, rng = self.sr, self.rng
        n = int(round(2.4 * sr))
        y = (damped_sine(2.4, sr, 2093.0, 1.9)
             + 0.85 * damped_sine(2.4, sr, 2098.5, 1.7)      # beating against the first
             + 0.45 * damped_sine(2.4, sr, 3151.0, 1.1)
             + 0.22 * damped_sine(2.4, sr, 4404.0, 0.55))
        strike = noise_loop(2.4, sr, lambda f: band(f, 2000, 9000, 0.6), rng)
        return normalize(y + 0.25 * strike * env_ad(n, sr, 0.0006, 0.010))

    # --------------------------------------------------------------- render
    def render(self, out, rhythm, events, dt):
        n = out.shape[1]
        rng = self.rng

        # A single typo is not an event; a burst of corrections is. Pressure
        # builds across backspaces and leaks away, so only a real correction
        # storm - or a sharp one after a quiet stretch - startles them.
        self._disturb = max(0.0, self._disturb - dt * 0.6)
        self._cooldown = max(0.0, self._cooldown - dt)
        self._chime_wait = max(0.0, self._chime_wait - dt)

        for kind in events:
            if kind == BACKSPACE:
                self._disturb += 1.0
                if self._disturb >= 4.0 and self._cooldown <= 0.0:
                    self._disturb = 0.0
                    self._cooldown = float(rng.uniform(10.0, 20.0))
                    # Something moved. The nearest ones stop first.
                    singing = sorted((v for v in self.voices_pool if v.level > 0.25),
                                     key=lambda v: -v.level)[:2]
                    for v in singing:
                        v.hush = max(v.hush, float(rng.uniform(2.5, 5.0)))
            elif kind == ENTER:
                # Enter is common while coding, so the chime is rationed: it
                # should feel like a breeze arriving, not a notification.
                if self._chime_wait <= 0.0:
                    self._chime_wait = float(rng.uniform(35.0, 110.0))
                    self.oneshots.trigger(self.furin, gain=float(rng.uniform(0.24, 0.40)),
                                          pan=float(rng.uniform(-0.6, 0.6)),
                                          rate=float(rng.uniform(0.96, 1.05)))

        # How many individuals the weather supports right now. Fractional on
        # purpose: the voice on the boundary rides in and out at partial level,
        # so the chorus thickens as a gradient instead of in steps.
        want = 1.0 + (N_VOICES - 3) * rhythm.flow ** 0.85

        for i, v in enumerate(self.voices_pool):
            if v.hush > 0.0:
                v.hush = max(0.0, v.hush - dt)
                target = 0.0
                tau = 0.4                        # a startled cicada cuts out fast
            else:
                target = clamp(want - i)
                tau = 7.0 if target > v.level else 5.5
            v.level += ema_alpha(dt, tau) * (target - v.level)
            if v.level > 0.004:
                near = 1.0 - 0.75 * v.far
                add_panned(out, v.loop.render(n, v.rate), 0.26 * near * v.level, v.pan)

        # After a long stretch of unbroken flow the afternoon turns to dusk.
        dusk_target = 1.0 if rhythm.sustain > HIGURASHI_AFTER else 0.0
        self._dusk += ema_alpha(dt, 25.0) * (dusk_target - self._dusk)
        if self._dusk > 0.004:
            h = self.higurashi
            add_panned(out, h.loop.render(n, h.rate), 0.24 * self._dusk, h.pan)

        self.chorus.add(out, n, 1.0, 0.11 + 0.10 * rhythm.flow)
        self.heat.add(out, n, 1.0, 0.085)
        self.oneshots.render(out)

    def status(self):
        singing = sum(1 for v in self.voices_pool if v.level > 0.2)
        hushed = sum(1 for v in self.voices_pool if v.hush > 0.0)
        tag = " [ヒグラシ]" if self._dusk > 0.3 else (" [静止]" if hushed else "")
        return "蝉 %s %2d匹%s" % (bar(singing / N_VOICES), singing, tag)
