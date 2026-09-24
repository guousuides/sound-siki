"""持ち込みの環境音 - field recordings you bring, layered under the synthesis.

The daemon still ships zero bytes of audio. What this adds is a slot: drop a
WAV you have the right to use (CC0 is the easy answer) into ~/.demon/sounds/
and the train demon lays it under what it synthesises. Nothing is bundled, so
nothing is redistributed - the licence question stays between you and the
file, and the repository stays arithmetic.

    platform.wav   ホームの雑踏     - while standing at a station
    running.wav    走行中の車内     - under the rumble, rising with speed
    tunnel.wav     トンネルの中     - crossfaded in as the tunnel closes over

Any of them may be missing; a missing slot is simply silence. The files are
read once at start-up with the standard-library `wave` module, resampled,
level-matched and given a crossfaded loop point, so the realtime path sees
the same precomputed loops as everything else.
"""
from __future__ import annotations

import os
import wave

import numpy as np

from .dsp import StereoBed

SLOTS = ("platform", "running", "tunnel")
MAX_SECONDS = 120.0       # a longer file is trimmed; the loop point hides it
SEAM = 0.75               # s of crossfade folded into the loop point
TARGET_RMS = 0.12         # every file is brought to the same loudness


def default_dir():
    return os.path.join(os.path.expanduser("~"), ".demon", "sounds")


def _read(path, sr):
    """PCM WAV -> float32 (channels, n) at `sr`. None if it cannot be read."""
    try:
        with wave.open(path, "rb") as w:
            ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            frames = w.readframes(min(w.getnframes(), int(MAX_SECONDS * rate)))
    except (OSError, wave.Error, EOFError):
        return None

    if width == 1:
        x = (np.frombuffer(frames, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        x = np.frombuffer(frames, "<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(frames, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float32) / float(1 << 23)
    elif width == 4:
        x = np.frombuffer(frames, "<i4").astype(np.float32) / float(1 << 31)
    else:
        return None
    x = x.reshape(-1, ch).T[:2]
    if x.shape[1] < rate:                          # under a second is not a bed
        return None

    if rate != sr:                                 # linear is plenty for a bed
        n = int(round(x.shape[1] * sr / float(rate)))
        src = np.linspace(0.0, x.shape[1] - 1, n)
        x = np.stack([np.interp(src, np.arange(x.shape[1]), c) for c in x])
    return x.astype(np.float32)


def _loopable(x, sr):
    """Fold the tail into the head so the loop point has no click or gap."""
    k = min(int(SEAM * sr), x.shape[1] // 4)
    fade = np.linspace(0.0, 1.0, k, dtype=np.float32)
    head = x[:, :k] * fade + x[:, -k:] * (1.0 - fade)
    x = np.concatenate([head, x[:, k:-k]], axis=1)
    rms = float(np.sqrt(np.mean(x ** 2)))
    return x * (TARGET_RMS / rms) if rms > 1e-6 else None


def load(sr, directory=None):
    """{slot: StereoBed} for every slot that has a usable file."""
    directory = directory or default_dir()
    beds = {}
    for slot in SLOTS:
        x = _read(os.path.join(directory, slot + ".wav"), sr)
        if x is not None:
            x = _loopable(x, sr)
        if x is not None:
            beds[slot] = StereoBed(x[0] if x.shape[0] == 1 else x)
    return beds
