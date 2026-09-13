"""乗車 - choosing today's line before the daemon wakes.

Everything is a number you type, because asking for 「西荻窪」 at a prompt is
friction and friction is the enemy of actually starting work. Enter alone takes
the obvious option at every step.
"""
from __future__ import annotations

import unicodedata

from . import journey
from .lines import LINES, ORDER


def _ask(prompt, options, default=None):
    """options: list of (label, value). Returns a value, or None if abandoned."""
    while True:
        suffix = " [%d]" % default if default is not None else ""
        try:
            raw = input("  %s%s > " % (prompt, suffix)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw and default is not None:
            return options[default - 1][1]
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][1]
        # A station name typed in full should work too, for the stubborn.
        for label, value in options:
            if raw and raw in label:
                return value
        print("     1〜%d の番号で。" % len(options))


def _columns(options, width=3):
    rows = (len(options) + width - 1) // width
    for r in range(rows):
        cells = []
        for c in range(width):
            i = r + c * rows
            if i < len(options):
                cells.append("%3d %-10s" % (i + 1, options[i][0]))
        print("    " + "".join(cells))


def _travel_order(line, direction, origin=None):
    """(label, station index) in the order this train will meet them.

    Only a loop line comes round again, so only a loop line rotates: on a line
    with two ends, everything behind the origin is simply not on the journey.
    """
    seq = line.order(direction)
    if origin is not None:
        k = seq.index(origin)
        seq = seq[k:] + seq[:k] if line.is_loop else seq[k:]
    return [(line.stations[i].name, i) for i in seq]


def pick(resume_ok=True):
    """Interactive boarding. Returns (plan, start_x, elapsed, sessions) or None."""
    parked = journey.load() if resume_ok else None
    if parked is not None:
        p = parked["plan"]
        left = (p.length - parked["x"]) / 1000.0
        print("  前回の続きがあります")
        print("     %s %s  %s → %s ／ 残り %.1f km ／ ここまで %d 分・%d 回"
              % (p.line.name, p.kind.name, p.origin.name, p.dest.name, left,
                 int(parked["elapsed"] / 60), parked["sessions"]))
        print()
        go = _ask("続きから乗りますか", [("続きから", True), ("新しい旅に出る", False)],
                  default=1)
        if go is None:
            return None
        if go:
            return (parked["plan"], parked["x"], parked["elapsed"],
                    parked["sessions"] + 1)
        print()

    print("  どの路線に乗りますか")
    opts = []
    for i, key in enumerate(ORDER, start=1):
        l = LINES[key]
        print("    %d  %-10s %s／%s %6s %5.1fkm   %s"
              % (i, l.name, l.dir_names[0], l.dir_names[1],
                 "%d駅" % len(l.stations), l.total_km, l.note))
        opts.append((l.name, l))
    line = _ask("", opts, default=1)
    if line is None:
        return None
    print()

    print("  %s - 向きは" % line.name)
    ends = (line.stations[0].name, line.stations[-1].name)
    for i, d in enumerate(line.dir_names, start=1):
        via = "%s → %s" % (ends[0], ends[1]) if i == 1 else "%s → %s" % (ends[1], ends[0])
        print("    %d  %-10s %s" % (i, d, "" if line.is_loop else via))
    direction = _ask("", [(d, 1 if i == 0 else -1)
                          for i, d in enumerate(line.dir_names)], default=1)
    if direction is None:
        return None
    print()

    if len(line.kinds) > 1:
        print("  種別は")
        for i, k in enumerate(line.kinds, start=1):
            n = len(line.stations) if k.stops is None else len(k.stops)
            print("    %d  %-10s %d駅に停車" % (i, k.name, n))
        kind = _ask("", [(k.name, k) for k in line.kinds], default=1)
        if kind is None:
            return None
        print()
    else:
        kind = line.kinds[0]

    order = _travel_order(line, direction)
    print("  出発駅")
    _columns(order if line.is_loop else order[:-1])
    origin = _ask("", order if line.is_loop else order[:-1], default=1)
    if origin is None:
        return None
    print()

    after = _travel_order(line, direction, origin)[1:]
    if line.is_loop:
        after = after + [("%s（一周）" % line.stations[origin].name, origin)]
    print("  目的駅  (%s 発)" % line.stations[origin].name)
    _columns(after)
    dest = _ask("", after, default=len(after))
    if dest is None:
        return None
    print()

    plan = line.plan(direction, origin, dest, kind)
    return plan, 0.0, 0.0, 1


def width(s):
    """Display columns, counting kana and kanji as two. Terminals do."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def describe(plan, x=0.0):
    stops = len(plan.stops) - 1
    head = "── %s %s ／ %s → %s ／ %d駅 %.1fkm ／ 目安 %d分 " % (
        plan.line.name, plan.kind.name, plan.origin.name, plan.dest.name,
        stops, plan.length / 1000.0, round(plan.estimate_minutes()))
    if x > 1.0:
        head += "／ 残り %.1fkm " % ((plan.length - x) / 1000.0)
    return head + "─" * max(2, 78 - width(head))
