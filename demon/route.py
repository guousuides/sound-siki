"""運転 - the part that decides where the train is, with no idea what it sounds like.

This is the simulation the whole feature rests on. Typing is the master
controller; everything after that is a train obeying physics on a real line:

    notch   = how hard you are typing, minus how much you are deleting
    a       = A_POWER * notch * taper(v) - resistance(v)      力行
            = -resistance(v)                                   惰行
            = -A_BRAKE * b                                     制動
    v      += a dt ,  x += v dt

The brake is not yours. Each block the driver works out how hard he would have
to brake to stop at the next booked station - v^2 / 2d - and once that reaches
a useful fraction of a service application he puts it in and leaves it in. So
you can type as hard as you like and the station still arrives, and the train
still stops at it. That asymmetry is the point: the throttle is yours, the
timetable is not.

Nothing here is random except which way an oncoming train happens to be. The
tunnels, curves and crossovers are read off the route (see lines.py) at the
metre they occur, so the ride is the same ride every time you run it.
"""
from __future__ import annotations

DWELL, RUN, DONE = range(3)

A_POWER = 0.83          # m/s^2 at full notch   (起動加速度 3.0 km/h/s)
A_BRAKE = 1.00          # m/s^2 full service    (常用最大 3.6 km/h/s)
A_HOLD = 0.34           # m/s^2 when the driver simply stops, mid-section

BRAKE_ON = 0.45         # apply once the required rate reaches this much of full
STOP_MARGIN = 6.0       # m short of the board, where the cab actually stops

DWELL_MIN = 18.0        # s of doors-open before departure can begin
HELD_AFTER = 45.0       # s standing before the "we are being held" announcement
IDLE_NOTCH = 4.0        # s of no typing -> power off
IDLE_BRAKE = 12.0       # s of no typing -> the driver brings it to a stand

APPROACH_AT = 850.0     # m before a booked stop, where 「まもなく」 goes out
RAIL = 25.0             # m, standard jointed rail

# Doors open, bell, whistle, doors close, away - offsets in seconds from the
# moment the train is cleared to leave.
LEAVING = ((0.0, "bell"), (3.2, "whistle"), (4.3, "doors_close"), (6.0, "depart"))


class Run:
    """One journey in progress."""

    def __init__(self, plan, rng, x=0.0, elapsed=0.0):
        self.plan = plan
        self.rng = rng
        self.x = float(x)
        self.v = 0.0
        self.notch = 0.0
        self.brake = 0.0
        self.elapsed = float(elapsed)
        self.keys = 0

        self.entries = plan.entries
        self.vmax = plan.line.max_speed

        self._i_entry = self._first_index_after(self.x)
        self._i_stop = self._next_stop_index(self._i_entry)
        self._i_tun = self._i_curve = self._i_pts = 0
        self.in_tunnel = False
        self._sync_features()

        self._said_approach = False
        self._held_said = False
        self._resumed = False
        self._stage = "run"
        self._dwell = 0.0
        self._sched = []
        self._sched_t = 0.0

        at_origin = self.x <= 1.0
        self.phase = DWELL if at_origin else RUN
        if at_origin:
            self._begin_dwell(first=True)
        else:
            # Picked up mid-section from a parked journey. You are standing
            # between stations, so do not open by telling the passengers off
            # for it - just say where we are once the brakes come off.
            self._held_said = True
            self._resumed = True

    # ------------------------------------------------------------- geometry
    def _first_index_after(self, x):
        for i, e in enumerate(self.entries):
            if e.s > x + 1.0:
                return i
        return len(self.entries) - 1

    def _next_stop_index(self, start):
        for i in range(start, len(self.entries)):
            if self.entries[i].is_stop:
                return i
        return len(self.entries) - 1

    def _sync_features(self):
        """Fast-forward the fixed-feature cursors to the current position."""
        p = self.plan
        while self._i_tun < len(p.tunnels) and p.tunnels[self._i_tun][1] <= self.x:
            self._i_tun += 1
        if self._i_tun < len(p.tunnels):
            s0, s1 = p.tunnels[self._i_tun]
            self.in_tunnel = s0 <= self.x < s1
        while self._i_curve < len(p.curves) and p.curves[self._i_curve] <= self.x:
            self._i_curve += 1
        while self._i_pts < len(p.points) and p.points[self._i_pts] <= self.x:
            self._i_pts += 1

    # ---------------------------------------------------------------- state
    @property
    def dwell(self):
        """Seconds standing at this platform; 0 while running."""
        return self._dwell if self.phase == DWELL else 0.0

    @property
    def next_stop(self):
        return self.entries[self._i_stop]

    @property
    def final(self):
        return self._i_stop >= len(self.entries) - 1

    @property
    def remaining_m(self):
        return max(0.0, self.entries[-1].s - self.x)

    @property
    def remaining_stops(self):
        return sum(1 for e in self.entries[self._i_stop:] if e.is_stop)

    @property
    def kmh(self):
        return self.v * 3.6

    def notch_label(self):
        if self.phase == DWELL:
            return "停車"
        if self.brake > 0.02:
            return "B%d" % max(1, min(7, int(round(self.brake * 7))))
        if self.notch > 0.02:
            return "P%d" % max(1, min(5, int(round(self.notch * 5))))
        return "惰行"

    # --------------------------------------------------------------- update
    def update(self, dt, rhythm):
        """Advance one audio block. Returns the events that happened in it.

        Events are (kind, *payload) tuples; the demon turns them into sound and
        the CLI turns some of them into a line of Japanese.
        """
        ev = []
        self.elapsed += dt
        if self.phase == DONE:
            return ev
        if self.phase == DWELL:
            self._tick_dwell(dt, rhythm, ev)
            return ev

        idle = rhythm.idle
        # --- the master controller ----------------------------------------
        # A floor under the notch, as before: any typing at all keeps the train
        # working, so the soundscape never swings between a crawl and line
        # speed with the density of your typing. Above the floor it is a real
        # throttle, and on a stopping service the difference compounds - you
        # pay it back at every single station you leave. Deleting takes it off
        # you again: a driver who keeps changing his mind does not make time.
        if idle > IDLE_NOTCH:
            target = 0.0
        else:
            target = (0.34 + 0.66 * rhythm.intensity) * (1.0 - 0.45 * rhythm.error)
        self.notch += min(1.0, dt / 2.0) * (target - self.notch)

        # --- the brake, which is the driver's, not yours -------------------
        d = self.next_stop.s - self.x - STOP_MARGIN
        need = self.v * self.v / (2.0 * max(d, 0.5)) if d > 0.0 else A_BRAKE
        if need >= BRAKE_ON * A_BRAKE:
            self.brake = min(1.0, need / A_BRAKE)
        elif idle > IDLE_BRAKE and self.v > 0.05:
            self.brake = A_HOLD / A_BRAKE          # you have clearly stopped
        else:
            self.brake = 0.0

        # --- integrate ------------------------------------------------------
        resist = 0.028 + 0.00055 * self.v * self.v
        if self.brake > 0.0:
            a = -A_BRAKE * self.brake - resist
        elif self.notch > 0.0:
            taper = min(1.0, 1.9 * (1.0 - self.v / self.vmax))
            a = A_POWER * self.notch * max(0.0, taper) - resist
        else:
            a = -resist
        x0 = self.x
        self.v = max(0.0, self.v + a * dt)
        self.x += self.v * dt

        if self._resumed and self.v > 1.0:
            self._resumed = False
            ev.append(("depart", self.next_stop, self.final, False))

        self._cross_features(x0, self.x, ev)

        # --- 「まもなく」 ----------------------------------------------------
        if not self._said_approach and d <= APPROACH_AT:
            self._said_approach = True
            ev.append(("approach", self.next_stop, self.final))

        # --- arrival ---------------------------------------------------------
        gap = self.next_stop.s - self.x
        if (gap <= STOP_MARGIN and self.v < 0.6) or (self.v <= 0.03 and gap <= 25.0):
            self.x = self.next_stop.s
            self.v = 0.0
            self.brake = self.notch = 0.0
            stop = self.next_stop
            if self.final:
                self.phase = DONE
                ev.append(("arrive", stop, True))
                ev.append(("terminus", stop))
            else:
                self.phase = DWELL
                ev.append(("arrive", stop, False))
                self._begin_dwell(at=self._i_stop)
        elif self.v <= 0.02 and idle > IDLE_BRAKE and not self._held_said:
            # Stopped between stations because you stopped. Signal check.
            self._held_said = True
            ev.append(("signal_hold",))
        return ev

    def _cross_features(self, x0, x1, ev):
        """Everything that is simply *there* at a metre mark on the line."""
        p = self.plan
        while (self._i_entry < len(self.entries)
               and self.entries[self._i_entry].s <= x1):
            e = self.entries[self._i_entry]
            if not e.is_stop:
                ev.append(("pass", e, self.v))
            self._i_entry += 1
        while self._i_pts < len(p.points) and p.points[self._i_pts] <= x1:
            ev.append(("points", self.v))
            self._i_pts += 1
        while self._i_curve < len(p.curves) and p.curves[self._i_curve] <= x1:
            ev.append(("curve", self.v))
            self._i_curve += 1
        while self._i_tun < len(p.tunnels):
            s0, s1 = p.tunnels[self._i_tun]
            if not self.in_tunnel and s0 <= x1:
                self.in_tunnel = True
                ev.append(("tunnel_enter", self.v))
            if self.in_tunnel and s1 <= x1:
                self.in_tunnel = False
                self._i_tun += 1
                ev.append(("tunnel_exit", self.v))
                continue
            break
        # The one thing on the line that genuinely is chance: whether anything
        # is coming the other way. In a bore it arrives as a pressure wave.
        if self.in_tunnel and self.v > 7.0:
            rate = 0.020 * (self.v / self.vmax)
            if self.rng.random() < (x1 - x0) / max(self.v, 1e-6) * rate:
                ev.append(("meet", self.v))

    # ---------------------------------------------------------------- dwell
    def _begin_dwell(self, first=False, at=None):
        self._dwell = 0.0
        self._stage = "open"
        self._sched = []
        self._sched_t = 0.0
        self._held_said = False
        self._said_approach = False
        if at is not None:
            # The arrival snapped the train onto the platform *after* the
            # feature cursors ran, so the station we are standing in is still
            # "ahead". Step over it, or we spend the day booking into it again.
            self._i_entry = at + 1
        self._i_stop = self._next_stop_index(self._i_entry)
        self._first = first

    def _tick_dwell(self, dt, rhythm, ev):
        self._dwell += dt
        if self._stage == "open":
            if self._dwell > DWELL_MIN and rhythm.idle < 2.5:
                self._stage = "leaving"
                self._sched = list(LEAVING)
                self._sched_t = 0.0
            elif self._dwell > HELD_AFTER and not self._held_said:
                # You stopped typing on the platform, so the doors stay open,
                # so the train is late, so they tell the passengers why.
                self._held_said = True
                ev.append(("held",))
            return

        self._sched_t += dt
        while self._sched and self._sched[0][0] <= self._sched_t:
            _, kind = self._sched.pop(0)
            if kind == "depart":
                self.phase = RUN
                ev.append(("depart", self.next_stop, self.final, self._first))
                self._first = False
            else:
                ev.append((kind,))
