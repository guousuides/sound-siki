"""電車デーモン - the local line you ride when the bullet train is banned.

You pick a line and a destination before you start work, and then you have to
drive there. Typing is the master controller; the train has mass and obeys it
slowly. Stop typing and it coasts, then the driver brings it to a stand; stop
typing on a platform and the doors will not close, and after a while they
announce to the carriage why the train is late. The only way to reach the
station you chose is to keep working.

  keys/sec      -> notch, integrated through the train's inertia (see route.py)
  corrections   -> the notch comes back off you; second thoughts do not make time
  train speed   -> rail-joint tempo, rumble pitch, wind, VVVF motor whine
  position      -> tunnels, curves, crossovers, platforms, the announcements
  Enter         -> the horn, rationed
  long silence  -> brakes, air release, a sparrow on an empty platform

What changed when the line became real: none of the scenery is a die roll any
more. The old demon rolled a tunnel when you pressed Enter and a set of points
when you pressed Backspace. Now the tunnel is at the metre the tunnel is at,
the crossover is on the approach to the station that has a crossover, and the
rail joints are struck because the wheels reached them - `floor(x / 25)`. The
arithmetic that always made the acceleration read as real now runs the whole
world.

Rail joints are still the signature. Japanese jointed track is laid in 25 m
lengths; each bogie has two axles about 2.4 m apart and the bogies sit about
14 m apart, so one joint passing under one car is four strikes - gatan-goton.
"""
from __future__ import annotations

import numpy as np

from ..announce import (Announcer, Speaker, approaching, arrival, departure,
                        held, next_stop, signal_hold, terminus)
from ..dsp import (Osc, StereoBed, Voices, add_panned, band, clamp,
                   damped_sine, ema_alpha, env_ad, noise_loop, normalize, peak,
                   sweep, tilt)
from ..keywatch import ENTER
from ..lines import LINES
from ..route import DONE, DWELL, RAIL, Run
from .base import Demon, bar

AXLE_SPACING = 2.4       # m, between the two axles of one bogie
BOGIE_SPACING = 14.0     # m, between the two bogies of one car

CODA = 30.0              # s of platform after the terminus, before it sleeps
HORN_COOLDOWN = (70.0, 190.0)


class TrainDemon(Demon):
    name = "train"
    title = "電車デーモン"
    blurb = "路線と行き先を選んで乗る各駅停車。打鍵が主幹制御器、着くまで降りられない。"

    def __init__(self, sr, rng):
        super().__init__(sr, rng)
        self.plan = None
        self.run = None
        self._start = (0.0, 0.0)
        self.keys = 0

        self.tunnel = 0.0
        self._station = 0.0
        self._cp = 0.0
        self._horn_wait = 45.0
        self._prev_x = 0.0
        self._coda = None
        self._speak_free = 0.0
        self._motor = Osc(60.0)
        self._brake_motor = Osc(900.0)

    def board(self, plan, x=0.0, elapsed=0.0):
        """Choose the journey. Must be called before prepare()."""
        self.plan = plan
        self._start = (float(x), float(elapsed))

    # ---------------------------------------------------------------- setup
    def prepare(self):
        sr, rng = self.sr, self.rng
        if self.plan is None:                    # --demo / --render / no picker
            line = LINES["yamanote"]
            self.plan = line.plan(1, line.index("東京"), line.index("東京"),
                                  line.kinds[0])

        self.rumble = StereoBed(noise_loop(
            8.0, sr, lambda f: band(f, 18, 210, 0.9) * tilt(f, 60, -0.7)
            * (1.0 + peak(f, 58, 3.0, 0.8)), rng))
        self.wind_open = StereoBed(noise_loop(
            6.0, sr, lambda f: band(f, 320, 6000, 0.8) * tilt(f, 1200, -0.8), rng))
        self.wind_tunnel = StereoBed(noise_loop(
            6.0, sr, lambda f: band(f, 80, 900, 0.7) * (1.0 + peak(f, 175, 2.0, 1.6)), rng))
        self.platform = StereoBed(noise_loop(
            8.0, sr, lambda f: band(f, 90, 1400, 1.0) * tilt(f, 300, -0.9), rng))
        # The compressor under the floor of a standing train. Nothing says
        # "stopped at a platform" like a motor cutting in while the doors are open.
        self.cp = StereoBed(noise_loop(
            4.0, sr, lambda f: band(f, 30, 700, 0.8) * tilt(f, 90, -0.8)
            * (1.0 + peak(f, 47, 9.0, 2.2) + peak(f, 94, 11.0, 1.1)
               + peak(f, 141, 13.0, 0.5)), rng))

        self.clacks = [self._make_clack(1.0 + 0.09 * (i - 3.5)) for i in range(8)]
        self.hiss = self._make_hiss()
        self.squeal = self._make_squeal()
        self.whoosh = self._make_whoosh()
        self.bird = self._make_bird()
        self.horn = self._make_horn()
        self.bell = self._make_bell()
        self.whistle = self._make_whistle()
        self.chime_open = self._make_chime((988.0, 740.0), 2)
        self.chime_close = self._make_chime((740.0, 988.0), 3, spacing=0.30)
        self.meet = self._make_meet()

        self.voices = Voices(limit=72)
        self.run = Run(self.plan, self.rng, *self._start)
        self._prev_x = self.run.x
        self.speaker = Speaker(Announcer(sr, rng).prepare()).start()
        # A welded-rail subway does not really do this; see README. It gets the
        # joints anyway, at less than half voice, because a train demon with no
        # gatan-goton in it is not a train demon.
        self._joint_gain = 1.0 if self.plan.line.jointed else 0.42
        return self

    # ------------------------------------------------------- one-shot sounds
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
        for k in range(3):
            chirp = sweep(0.075, sr,
                          lambda t: 3600 + 2600 * np.sin(np.pi * t / 0.075),
                          harmonics=(1.0, 0.2))
            chirp = chirp * env_ad(chirp.shape[0], sr, 0.004, 0.028)
            off = int((0.03 + k * 0.16) * sr)
            y[off:off + chirp.shape[0]] += chirp * (0.9 - 0.15 * k)
        return normalize(y)

    def _make_horn(self):
        """タイフォン - two pipes slightly out of tune, which is the whole sound."""
        sr, n = self.sr, int(round(0.85 * self.sr))
        t = np.arange(n, dtype=np.float64) / sr
        y = np.zeros(n)
        for f, a in ((392.0, 1.0), (589.0, 0.75), (784.0, 0.30), (1178.0, 0.16)):
            y += a * np.sin(2 * np.pi * f * t) + a * 0.8 * np.sin(2 * np.pi * f * 1.006 * t)
        air = noise_loop(0.85, sr, lambda f: band(f, 700, 5000, 0.7), self.rng) * 0.10
        env = np.minimum(t / 0.035, 1.0) * np.clip((0.85 - t) / 0.18, 0.0, 1.0)
        return normalize((y + air) * env)

    def _make_bell(self):
        """発車ベル - a clapper on a steel cup. Deliberately the plain electric
        bell and not a station melody: those are somebody's copyrighted tune."""
        sr, seconds = self.sr, 2.6
        n = int(round(seconds * sr))
        t = np.arange(n, dtype=np.float64) / sr
        y = np.zeros(n)
        for f, a, d in ((642.0, 1.0, 0.19), (1187.0, 0.62, 0.15),
                        (1733.0, 0.34, 0.11), (2490.0, 0.18, 0.08)):
            y += a * np.sin(2 * np.pi * f * t) * np.exp(-(t % 0.083) / d)
        clapper = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 12.0 * t))
        env = np.minimum(t / 0.01, 1.0) * np.clip((seconds - t) / 0.30, 0.0, 1.0)
        return normalize(y * clapper * env, 0.85)

    def _make_whistle(self):
        sr, seconds = self.sr, 0.75
        n = int(round(seconds * sr))
        y = noise_loop(seconds, sr,
                       lambda f: band(f, 1900, 4200, 0.35)
                       * (1.0 + peak(f, 2350, 40.0, 5.0) + peak(f, 2480, 40.0, 4.0)),
                       self.rng)
        t = np.arange(n) / sr
        env = np.minimum(t / 0.025, 1.0) * np.clip((seconds - t) / 0.09, 0.0, 1.0)
        return normalize(y[:n] * env, 0.8)

    def _make_chime(self, tones, repeats, spacing=0.42):
        """The two-tone door chime, repeated. Soft attack - it is a speaker, not a bell."""
        sr = self.sr
        unit = 0.36
        total = int(round((spacing * (repeats - 1) + unit + 0.25) * sr))
        y = np.zeros(total, dtype=np.float32)
        for r in range(repeats):
            for j, f in enumerate(tones):
                n = int(round(unit * sr))
                tone = (damped_sine(unit, sr, f, 0.16)
                        + 0.30 * damped_sine(unit, sr, f * 2.0, 0.07))
                tone = tone * env_ad(n, sr, 0.010, 0.13)
                off = int((r * spacing + j * 0.16) * sr)
                end = min(off + n, total)
                y[off:end] += tone[: end - off] * (0.95 - 0.10 * r)
        return normalize(y, 0.7)

    def _make_meet(self):
        """A train the other way, in a bore barely wider than it is.

        You hear the pressure before you hear the train: the air has nowhere to
        go, so it arrives as a thump, then the noise, then both leave at once.
        """
        sr, seconds = self.sr, 1.9
        n = int(round(seconds * sr))
        t = np.arange(n, dtype=np.float64) / sr
        body = noise_loop(seconds, sr,
                          lambda f: band(f, 45, 2400, 0.8) * tilt(f, 220, -0.7), self.rng)
        swell = np.exp(-((t - 0.92) / 0.34) ** 2)
        press = (damped_sine(seconds, sr, 31.0, 0.30)
                 + 0.7 * damped_sine(seconds, sr, 46.0, 0.20))
        return normalize(body[:n] * swell + 0.85 * press
                         * np.minimum(t / 0.02, 1.0), 0.95)

    # --------------------------------------------------------------- render
    def render(self, out, rhythm, events, dt):
        sr, n = self.sr, out.shape[1]
        run = self.run

        self.keys = rhythm.total
        self._horn_wait = max(0.0, self._horn_wait - dt)
        self._speak_free = max(0.0, self._speak_free - dt)

        x0 = run.x
        route_events = run.update(dt, rhythm)
        self._prev_x = x0
        v = run.v
        vmax = run.vmax
        sp = clamp(v / vmax)
        moving = v > 0.15

        for kind in events:                      # what you actually pressed
            if kind == ENTER and self._horn_wait <= 0.0 and moving:
                self._horn_wait = float(self.rng.uniform(*HORN_COOLDOWN))
                self.voices.trigger(self.horn, gain=0.16 * (0.45 + 0.55 * sp),
                                    pan=self.rng.uniform(-0.15, 0.15))

        for ev in route_events:
            self._handle(ev, sp)

        # --- an announcement that finished rendering is now ready to play ----
        buf = self.speaker.poll()
        if buf is not None:
            delay = max(0.0, self._speak_free) * sr
            self._speak_free = max(self._speak_free, 0.0) + buf.shape[0] / sr + 0.5
            for pan, off in ((-0.5, 0.0), (0.5, 0.006)):
                self.voices.trigger(buf, delay=delay + off * sr, gain=0.30, pan=pan)

        self._render_joints(x0, run.x, v, n, sr)

        # --- continuous beds --------------------------------------------------
        t_target = 1.0 if run.in_tunnel else 0.0
        self.tunnel += ema_alpha(dt, 0.9 if t_target > self.tunnel else 1.4) * (t_target - self.tunnel)
        st_target = 1.0 if run.phase in (DWELL, DONE) else 0.0
        self._station += ema_alpha(dt, 4.0) * (st_target - self._station)
        cp_target = 1.0 if run.dwell > 6.0 else 0.0
        self._cp += ema_alpha(dt, 3.5 if cp_target > self._cp else 1.2) * (cp_target - self._cp)

        tun = self.tunnel
        self.rumble.add(out, n, 0.88 + 0.30 * sp,
                        0.13 + 0.22 * sp ** 0.8 + 0.14 * tun * sp)

        wind_rate = 0.94 + 0.22 * sp
        wind_gain = 0.21 * sp ** 1.6
        if tun < 0.999:
            self.wind_open.add(out, n, wind_rate, wind_gain * (1.0 - tun))
        if tun > 0.001:
            self.wind_tunnel.add(out, n, wind_rate, wind_gain * tun * 1.5)

        # VVVF: current through the motors, so it sings while you are powering
        # and again, descending, while the brakes are regenerating.
        if moving and run.notch > 0.02:
            whine = self._motor.render(n, sr, 58.0 + 620.0 * sp,
                                       harmonics=(1.0, 0.45, 0.22, 0.10))
            add_panned(out, whine, 0.034 * run.notch * min(1.0, sp / 0.06))
        if moving and run.brake > 0.02:
            whine = self._brake_motor.render(n, sr, 120.0 + 520.0 * sp,
                                             harmonics=(1.0, 0.30, 0.12))
            add_panned(out, whine, 0.024 * run.brake * min(1.0, sp / 0.08))

        if self._station > 0.01:
            self.platform.add(out, n, 1.0, 0.050 * self._station)
        if self._cp > 0.01:
            self.cp.add(out, n, 1.0, 0.055 * self._cp)
        if (run.phase == DWELL and self._station > 0.4 and not run.in_tunnel
                and self.rng.random() < dt * 0.10):
            self.voices.trigger(self.bird, gain=0.11, pan=self.rng.uniform(-0.8, 0.8))

        self.voices.render(out)

        if self._coda is not None:
            self._coda -= dt
            if self._coda <= 0.0:
                self.finished = True

    # ---------------------------------------------------------- rail joints
    def _render_joints(self, x0, x1, v, n, sr):
        """Strike every 25 m mark the wheels crossed in this block.

        Sample-accurate, because the joint is at a place and the block is a
        span of places: where in the block it lands is just where in the span.
        """
        if v < 0.4 or x1 <= x0:
            return
        span = x1 - x0
        first = int(np.ceil(x0 / RAIL))
        last = int(np.floor(x1 / RAIL))
        if last < first:
            return
        d_axle, d_bogie = AXLE_SPACING / v * sr, BOGIE_SPACING / v * sr
        sp = clamp(v / self.run.vmax)
        loud = 0.20 * (0.55 + 0.45 * sp) * self._joint_gain
        for m in range(first, min(last, first + 3) + 1):
            base = (m * RAIL - x0) / span * n
            for off, g in ((0.0, 1.0), (d_axle, 0.72),
                           (d_bogie, 0.92), (d_bogie + d_axle, 0.64)):
                self.voices.trigger(
                    self.clacks[self.rng.integers(0, len(self.clacks))],
                    delay=max(0.0, base + off),
                    gain=loud * g * self.rng.uniform(0.85, 1.12),
                    pan=self.rng.uniform(-0.35, 0.35),
                    rate=0.95 + 0.13 * sp + self.rng.uniform(-0.04, 0.04))

    # ------------------------------------------------------- route reactions
    def _speak(self, made, room=0.35):
        text, kana = made
        self.say("♪ " + text)
        self.speaker.request(kana, room)

    def _handle(self, ev, sp):
        kind = ev[0]
        rng, V = self.rng, self.voices

        if kind == "arrive":
            stop = ev[1]
            V.trigger(self.squeal, gain=0.15, pan=-0.2, rate=0.8)
            V.trigger(self.hiss, delay=0.55 * self.sr, gain=0.21, pan=0.15)
            if not ev[2]:
                self._speak(arrival(stop), room=0.5)
        elif kind == "terminus":
            self._speak(terminus(ev[1]), room=0.5)
            self.say(self._summary())
            self._coda = CODA
        elif kind == "depart":
            nxt, final, first = ev[1], ev[2], ev[3]
            V.trigger(self.hiss, gain=0.16, pan=-0.1, rate=1.25)
            self._speak(departure(self.plan.kind, self.plan.dest, nxt, final)
                        if first else next_stop(nxt, final), room=0.45)
        elif kind == "approach":
            self._speak(approaching(ev[1], ev[2]), room=0.4)
        elif kind == "held":
            self._speak(held(), room=0.55)
        elif kind == "signal_hold":
            self._speak(signal_hold(), room=0.55)
        elif kind == "bell":
            V.trigger(self.bell, gain=0.13, pan=rng.uniform(-0.4, 0.4))
        elif kind == "whistle":
            V.trigger(self.whistle, gain=0.10, pan=rng.uniform(-0.6, -0.2))
        elif kind == "doors_close":
            # Two sets of doors on a platform-door line, a beat apart. That
            # offset is the signature of a modern subway platform.
            V.trigger(self.chime_close, gain=0.15, pan=-0.15)
            if self.plan.line.key == "fukutoshin":
                V.trigger(self.chime_close, delay=0.24 * self.sr,
                          gain=0.085, pan=0.45, rate=1.06)
            V.trigger(self.hiss, delay=1.25 * self.sr, gain=0.14, rate=1.5)
        elif kind == "points":
            v = max(ev[1], 1.0)
            for i in range(2):
                V.trigger(self.clacks[rng.integers(0, len(self.clacks))],
                          delay=(i * AXLE_SPACING / v) * self.sr,
                          gain=0.19 * (0.4 + 0.6 * sp),
                          pan=rng.uniform(-0.5, 0.5), rate=1.12)
        elif kind == "curve":
            V.trigger(self.squeal, gain=0.085 * sp, pan=rng.uniform(-0.7, 0.7))
        elif kind == "tunnel_enter":
            V.trigger(self.whoosh, gain=0.23 * (0.4 + sp))
        elif kind == "tunnel_exit":
            V.trigger(self.whoosh, gain=0.14 * (0.4 + sp), rate=1.3)
        elif kind == "meet":
            V.trigger(self.meet, gain=0.20 * (0.45 + 0.55 * sp), pan=-0.55)
            V.trigger(self.meet, delay=0.05 * self.sr,
                      gain=0.15 * (0.45 + 0.55 * sp), pan=0.7, rate=1.04)
        elif kind == "pass":
            # A platform going by at speed: it arrives on one side and leaves
            # on the other, which two voices and a few milliseconds will do.
            g = 0.17 * (0.35 + 0.65 * sp)
            V.trigger(self.whoosh, gain=g, pan=-0.85, rate=0.92 + 0.35 * sp)
            V.trigger(self.whoosh, delay=0.085 * self.sr, gain=g * 0.8,
                      pan=0.85, rate=1.10 + 0.35 * sp)

        if kind == "doors_open":
            V.trigger(self.chime_open, gain=0.15, pan=0.1)

    # --------------------------------------------------------------- status
    def _summary(self):
        run, plan = self.run, self.plan
        mins = run.elapsed / 60.0
        avg = (plan.length / 1000.0) / (run.elapsed / 3600.0) if run.elapsed > 1 else 0.0
        return ("── %s %s  %s → %s ／ 走行 %.1f km ／ 所要 %d時間%02d分 "
                "／ 表定 %.1f km/h ／ 打鍵 %s" % (
                    plan.line.name, plan.kind.name, plan.origin.name, plan.dest.name,
                    plan.length / 1000.0, int(mins // 60), int(mins % 60), avg,
                    "{:,}".format(self.keys)))

    def status(self):
        run, plan = self.run, self.plan
        if run is None:
            return ""
        if run.phase == DONE:
            return "電車 %s %s 到着" % (plan.line.name, plan.dest.name)
        done = clamp(run.x / max(plan.length, 1.0))
        tag = "[トンネル]" if run.in_tunnel else ""
        return "電車 %s %s %s %5.1f km/h %-4s 次:%s 残り%4.1fkm/%d駅 %s" % (
            bar(done), plan.line.name, plan.kind.name, run.kmh, run.notch_label(),
            run.next_stop.name, run.remaining_m / 1000.0, run.remaining_stops, tag)
