"""電車デーモン - the local line you ride when the bullet train is banned.

Coupling
--------
Typing speed is the throttle, but the train has mass: it takes ten seconds of
sustained typing to reach line speed, and it coasts for just as long after you
stop. You cannot flick it on, you have to keep feeding it.

  keys/sec      -> throttle, integrated through the train's inertia
  train speed   -> rail-joint tempo, rumble pitch, wind, VVVF motor whine
  Enter         -> a tunnel (the world closes in for a few seconds)
  Backspace     -> a set of points clatters under the floor
  long silence  -> brakes, air release, a sparrow on an empty platform

Rail joints are the signature. Japanese jointed track is laid in 25 m lengths;
each bogie has two axles about 2.4 m apart and the bogies sit about 14 m
apart, so one joint passing under one car is four strikes - gatan-goton - and
the gaps between them shrink as you speed up. All of that is arithmetic on the
current speed, which is why the acceleration reads as real.
"""
from __future__ import annotations

import numpy as np

from ..dsp import (Osc, StereoBed, Voices, add_panned, band, damped_sine,
                   ema_alpha, env_ad, noise_loop, normalize, peak, sweep, tilt)
from ..keywatch import BACKSPACE, ENTER
from .base import Demon, bar

RAIL_LENGTH = 25.0       # m, standard jointed rail
AXLE_SPACING = 2.4       # m, between the two axles of one bogie
BOGIE_SPACING = 14.0     # m, between the two bogies of one car
V_MIN, V_MAX = 4.0, 33.0  # m/s at throttle 0 and 1 (~15 to ~120 km/h)


class TrainDemon(Demon):
    name = "train"
    title = "電車デーモン"
    blurb = "打鍵が速いほど加速する各駅停車。Enterでトンネル、無音が続くと駅に停まる。"

    def __init__(self, sr, rng):
        super().__init__(sr, rng)
        self.speed = 0.0
        self.tunnel = 0.0
        self._tunnel_left = 0.0
        self._tunnel_wait = 45.0     # no tunnel in the first minute of the run
        self._points_wait = 0.0
        self._station = 0.0
        self._next_joint = 0.0
        self._stopped = True
        self._motor = Osc(60.0)

    # ---------------------------------------------------------------- setup
    def prepare(self):
        sr, rng = self.sr, self.rng

        # Beds: seamless loops, replayed at a speed-dependent rate.
        self.rumble = StereoBed(noise_loop(
            8.0, sr, lambda f: band(f, 18, 210, 0.9) * tilt(f, 60, -0.7)
            * (1.0 + peak(f, 58, 3.0, 0.8)), rng))
        self.wind_open = StereoBed(noise_loop(
            6.0, sr, lambda f: band(f, 320, 6000, 0.8) * tilt(f, 1200, -0.8), rng))
        self.wind_tunnel = StereoBed(noise_loop(
            6.0, sr, lambda f: band(f, 80, 900, 0.7) * (1.0 + peak(f, 175, 2.0, 1.6)), rng))
        self.platform = StereoBed(noise_loop(
            8.0, sr, lambda f: band(f, 90, 1400, 1.0) * tilt(f, 300, -0.9), rng))

        # Rail-joint strikes: eight variants so the pattern never sounds looped.
        self.clacks = [self._make_clack(1.0 + 0.09 * (i - 3.5)) for i in range(8)]

        self.hiss = self._make_hiss()
        self.squeal = self._make_squeal()
        self.whoosh = self._make_whoosh()
        self.bird = self._make_bird()

        self.voices = Voices(limit=48)

    def _make_clack(self, var):
        sr, rng = self.sr, self.rng
        n = int(round(0.17 * sr))
        noise = noise_loop(
            0.17, sr, lambda f: band(f, 240, 3800, 0.6)
            * (1.0 + peak(f, 880 * var, 5.0, 1.4) + peak(f, 1950 * var, 7.0, 0.7)), rng)
        body = (damped_sine(0.17, sr, 72 * var, 0.045)
                + 0.55 * damped_sine(0.17, sr, 108 * var, 0.028))
        y = noise * env_ad(n, sr, 0.0004, 0.020) + 0.7 * body * env_ad(n, sr, 0.001, 0.055)
        return normalize(y)

    def _make_hiss(self):
        sr, rng = self.sr, self.rng
        n = int(round(1.4 * sr))
        noise = noise_loop(1.4, sr, lambda f: band(f, 1400, 9000, 0.8) * tilt(f, 3000, -0.5), rng)
        t = np.arange(n) / sr
        env = np.clip(t / 0.05, 0.0, 1.0) * np.exp(-np.maximum(t - 0.25, 0.0) / 0.32)
        return normalize(noise * env)

    def _make_squeal(self):
        sr, rng = self.sr, self.rng
        n = int(round(1.8 * sr))
        tone = sweep(
            1.8, sr,
            lambda t: 1480.0 * (1 + 0.035 * np.sin(2 * np.pi * 5.5 * t)) * (1 + 0.09 * t / 1.8),
            harmonics=(1.0, 0.28, 0.12))
        grit = noise_loop(1.8, sr, lambda f: band(f, 1200, 4500, 0.5), rng) * 0.22
        return normalize((tone + grit) * env_ad(n, sr, 0.35, 0.55))

    def _make_whoosh(self):
        sr, rng = self.sr, self.rng
        n = int(round(0.9 * sr))
        air = noise_loop(0.9, sr, lambda f: band(f, 150, 5000, 0.7) * tilt(f, 800, -0.6), rng)
        boom = damped_sine(0.9, sr, 44.0, 0.22) + 0.6 * damped_sine(0.9, sr, 67.0, 0.16)
        return normalize(air * env_ad(n, sr, 0.012, 0.22) + 0.8 * boom)

    def _make_bird(self):
        sr = self.sr
        n = int(round(0.55 * sr))
        y = np.zeros(n, dtype=np.float32)
        for k in range(3):  # chun, chun, chun
            chirp = sweep(0.075, sr,
                          lambda t: 3600 + 2600 * np.sin(np.pi * t / 0.075),
                          harmonics=(1.0, 0.2))
            chirp = chirp * env_ad(chirp.shape[0], sr, 0.004, 0.028)
            off = int((0.03 + k * 0.16) * sr)
            y[off:off + chirp.shape[0]] += chirp * (0.9 - 0.15 * k)
        return normalize(y)

    # --------------------------------------------------------------- render
    def render(self, out, rhythm, events, dt):
        sr = self.sr
        n = out.shape[1]

        # --- throttle -> speed, through the train's mass -------------------
        throttle = 0.0 if rhythm.idle > 2.5 else rhythm.intensity
        if throttle > self.speed:
            tau = 7.0                       # notching up: heavy, takes ~10 s to wind out
        elif rhythm.idle > 8.0:
            tau = 3.5                       # you have clearly stopped - brakes on
        else:
            tau = 11.0                      # just thinking: coast
        self.speed += ema_alpha(dt, tau) * (throttle - self.speed)
        speed = self.speed
        moving = speed > 0.015

        if self._stopped and moving:
            self._stopped = False
        elif not self._stopped and not moving:  # pulling into the platform
            self._stopped = True
            self.voices.trigger(self.squeal, gain=0.22, pan=-0.2, rate=0.8)
            self.voices.trigger(self.hiss, delay=0.55 * sr, gain=0.30, pan=0.15)

        # --- discrete reactions to what you just typed ---------------------
        self._tunnel_wait = max(0.0, self._tunnel_wait - dt)
        self._points_wait = max(0.0, self._points_wait - dt)
        for kind in events:
            if kind == ENTER:
                # A newline opens a tunnel - but tunnels are rationed, or a
                # coding session would spend its whole life underground.
                if self._tunnel_wait <= 0.0 and speed > 0.35:
                    self._tunnel_wait = float(self.rng.uniform(70.0, 190.0))
                    self._tunnel_left = self.rng.uniform(3.5, 8.0)
                    self.voices.trigger(self.whoosh, gain=0.34 * (0.4 + speed))
            elif kind == BACKSPACE and moving and self._points_wait <= 0.0:
                # A correction throws a set of points under the floor. Rationed
                # too: one per typo would just be a snare drum.
                self._points_wait = float(self.rng.uniform(14.0, 40.0))
                v = V_MIN + (V_MAX - V_MIN) * speed
                for i in range(2):
                    self.voices.trigger(
                        self.clacks[self.rng.integers(0, len(self.clacks))],
                        delay=(i * AXLE_SPACING / v) * sr,
                        gain=0.30 * (0.4 + 0.6 * speed),
                        pan=self.rng.uniform(-0.5, 0.5), rate=1.12)

        prev_tunnel = self.tunnel
        self._tunnel_left = max(0.0, self._tunnel_left - dt)
        t_target = 1.0 if self._tunnel_left > 0.0 else 0.0
        self.tunnel += ema_alpha(dt, 0.35 if t_target > self.tunnel else 0.7) * (t_target - self.tunnel)
        if prev_tunnel > 0.5 >= self.tunnel:  # back into daylight
            self.voices.trigger(self.whoosh, gain=0.20 * (0.4 + speed), rate=1.3)

        st_target = 1.0 if (not moving and rhythm.idle > 6.0) else 0.0
        self._station += ema_alpha(dt, 3.0) * (st_target - self._station)

        # --- rail joints ---------------------------------------------------
        if moving:
            v = V_MIN + (V_MAX - V_MIN) * speed
            self._next_joint -= n
            while self._next_joint <= 0.0:
                base = self._next_joint + n
                d_axle, d_bogie = AXLE_SPACING / v * sr, BOGIE_SPACING / v * sr
                loud = 0.34 * (0.45 + 0.55 * speed)
                for off, g in ((0.0, 1.0), (d_axle, 0.72),
                               (d_bogie, 0.92), (d_bogie + d_axle, 0.64)):
                    self.voices.trigger(
                        self.clacks[self.rng.integers(0, len(self.clacks))],
                        delay=max(0.0, base + off),
                        gain=loud * g * self.rng.uniform(0.85, 1.12),
                        pan=self.rng.uniform(-0.35, 0.35),
                        rate=0.92 + 0.22 * speed + self.rng.uniform(-0.04, 0.04))
                self._next_joint += (RAIL_LENGTH / v) * sr
            if speed > 0.6 and self.rng.random() < dt * 0.05:  # a curve, now and then
                self.voices.trigger(self.squeal, gain=0.13 * speed,
                                    pan=self.rng.uniform(-0.7, 0.7))
        else:
            self._next_joint = 0.0
            if self._station > 0.4 and self.rng.random() < dt * 0.12:
                self.voices.trigger(self.bird, gain=0.13, pan=self.rng.uniform(-0.8, 0.8))

        # --- continuous beds ------------------------------------------------
        tun = self.tunnel
        self.rumble.add(out, n, 0.80 + 0.55 * speed,
                        0.10 + 0.46 * speed ** 0.8 + 0.30 * tun * speed)

        wind_rate = 0.90 + 0.42 * speed
        wind_gain = 0.42 * speed ** 1.6
        if tun < 0.999:
            self.wind_open.add(out, n, wind_rate, wind_gain * (1.0 - tun))
        if tun > 0.001:
            self.wind_tunnel.add(out, n, wind_rate, wind_gain * tun * 1.9)

        if moving:  # VVVF motor whine: loudest while accelerating, gone at cruise
            whine = self._motor.render(n, sr, 58.0 + 620.0 * speed,
                                       harmonics=(1.0, 0.45, 0.22, 0.10))
            amp = 0.055 * float(np.exp(-((speed - 0.24) / 0.30) ** 2)) * min(1.0, speed / 0.05)
            add_panned(out, whine, amp)

        if self._station > 0.01:
            self.platform.add(out, n, 1.0, 0.055 * self._station)

        self.voices.render(out)

    def status(self):
        kmh = (V_MIN + (V_MAX - V_MIN) * self.speed) * 3.6 if self.speed > 0.015 else 0.0
        tag = " [トンネル]" if self.tunnel > 0.5 else (" [停車中]" if self._station > 0.5 else "")
        return "電車 %s %5.1f km/h%s" % (bar(self.speed), kmh, tag)
