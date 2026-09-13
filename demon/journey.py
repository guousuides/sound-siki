"""旅の続き - the only thing this daemon ever writes to disk.

The privacy rule has not moved: nothing derived from your typing leaves the
process. Not a character, not a keycode, not a count, not a window title, not
a timestamp of when you pressed anything. What is written here is where the
train is and how long it has been running - two numbers about a train - plus
enough to name the route it is on. You can read the file; there is nothing in
it about you.

That is the whole point of keeping it: 東海道本線 is 513 km, and 山手線 is a
lap. A line you cannot finish in one sitting needs somewhere to leave the
train overnight.
"""
from __future__ import annotations

import json
import os

from .lines import LINES

VERSION = 1


def path():
    home = os.path.expanduser("~")
    return os.path.join(home, ".demon", "journey.json")


def save(plan, x, elapsed, sessions=1):
    """Park the train. Never raises - a journey is not worth losing work over."""
    data = {
        "version": VERSION,
        "line": plan.line.key,
        "kind": plan.kind.name,
        "direction": plan.direction,
        "origin": plan.origin.name,
        "dest": plan.dest.name,
        "x_m": round(float(x), 1),
        "elapsed_s": round(float(elapsed), 1),
        "sessions": int(sessions),
    }
    try:
        p = path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError:
        pass
    return data


def load():
    """The parked train, or None. A file we cannot make sense of is not a file."""
    try:
        with open(path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("version") != VERSION:
        return None
    line = LINES.get(d.get("line"))
    if line is None:
        return None
    try:
        kind = next(k for k in line.kinds if k.name == d["kind"])
        plan = line.plan(int(d["direction"]), line.index(d["origin"]),
                         line.index(d["dest"]), kind)
    except (KeyError, StopIteration, ValueError):
        return None
    x = float(d.get("x_m", 0.0))
    if not 0.0 <= x < plan.length - 1.0:
        return None                      # already arrived, or off the end
    return {"plan": plan, "x": x, "elapsed": float(d.get("elapsed_s", 0.0)),
            "sessions": int(d.get("sessions", 1))}


def clear():
    try:
        os.remove(path())
    except OSError:
        pass
