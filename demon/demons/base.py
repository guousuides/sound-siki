"""Common shape of a demon.

A demon owns a soundscape and a coupling: how the typing rhythm turns into
sound. It precomputes its material in `prepare()` and then only ever adds into
a shared stereo block in `render()`.
"""
from __future__ import annotations

import numpy as np


class Demon:
    name = "demon"
    title = "デーモン"
    blurb = ""

    def __init__(self, sr, rng):
        self.sr = sr
        self.rng = rng

    def prepare(self):
        """Synthesise every buffer this demon will ever need."""

    def render(self, out: np.ndarray, rhythm, events, dt: float):
        """Add out.shape[1] samples into the stereo block (float32, shape (2, n))."""
        raise NotImplementedError

    def status(self) -> str:
        """One short line for the terminal status display."""
        return ""


def bar(value, width=10, fill="#", empty="."):
    k = int(round(max(0.0, min(1.0, value)) * width))
    return fill * k + empty * (width - k)
