"""Numpy-only DSP primitives for the typing demon.

Design rule: everything expensive (spectral shaping, one-shot rendering) runs
once at startup and lands in a small numpy array.  The realtime callback only
mixes those precomputed buffers and does cheap per-block gain math, so the
whole daemon stays well under a millisecond of CPU per audio block and needs
no audio assets on disk.
"""
from __future__ import annotations

import numpy as np

TWO_PI = 2.0 * np.pi


# --------------------------------------------------------------------------
# scalar helpers
# --------------------------------------------------------------------------
def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, t):
    return a + (b - a) * t


def ema_alpha(dt, tau):
    """Per-block coefficient for an exponential move with time constant `tau`."""
    if tau <= 0.0:
        return 1.0
    return 1.0 - float(np.exp(-dt / tau))


# --------------------------------------------------------------------------
# spectrum shapes (magnitude as a function of frequency, for noise_loop)
# --------------------------------------------------------------------------
def band(f, lo, hi, edge=0.5):
    """Soft band-pass window in log-frequency; `edge` is the skirt in octaves."""
    lf = np.log2(np.maximum(f, 1e-3))
    up = 1.0 / (1.0 + np.exp(-(lf - np.log2(lo)) / edge))
    dn = 1.0 / (1.0 + np.exp((lf - np.log2(hi)) / edge))
    return up * dn


def tilt(f, ref=1000.0, slope=-1.0):
    """Magnitude proportional to (f/ref)**slope, safe at DC."""
    return (np.maximum(f, 1e-3) / ref) ** slope


def peak(f, f0, q=6.0, gain=1.0):
    """Resonant bump centred on f0 (analogue-ish bell)."""
    fs = np.maximum(f, 1e-3)
    return gain / (1.0 + (q * (fs / f0 - f0 / fs)) ** 2)


def noise_loop(seconds, sr, shape, rng):
    """Noise with an arbitrary magnitude spectrum, seamlessly loopable.

    Built in the frequency domain with random phase, so the result is periodic
    by construction - no crossfade seam, no click at the loop point.
    """
    n = int(round(seconds * sr))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    mag = np.asarray(shape(freqs), dtype=float)
    spec = mag * np.exp(1j * rng.uniform(0.0, TWO_PI, mag.shape))
    spec[0] = 0.0
    y = np.fft.irfft(spec, n)
    return normalize(y)


def normalize(x, peak_level=1.0):
    x = np.asarray(x, dtype=np.float32)
    m = float(np.max(np.abs(x)))
    return (x * (peak_level / m)).astype(np.float32) if m > 1e-12 else x


# --------------------------------------------------------------------------
# offline waveform builders (one-shots)
# --------------------------------------------------------------------------
def env_ad(n, sr, attack, decay):
    """Attack/decay envelope, normalised to a peak of 1."""
    t = np.arange(n, dtype=np.float64) / sr
    e = (1.0 - np.exp(-t / max(attack, 1e-5))) * np.exp(-t / max(decay, 1e-5))
    m = e.max()
    return (e / m if m > 0 else e).astype(np.float32)


def damped_sine(seconds, sr, f0, decay, phase=0.0):
    t = np.arange(int(round(seconds * sr)), dtype=np.float64) / sr
    return (np.sin(TWO_PI * f0 * t + phase) * np.exp(-t / decay)).astype(np.float32)


def sweep(seconds, sr, f_curve, harmonics=(1.0,)):
    """Tonal sweep; `f_curve(t)` returns instantaneous frequency in Hz."""
    n = int(round(seconds * sr))
    t = np.arange(n, dtype=np.float64) / sr
    ph = np.cumsum(f_curve(t)) * (TWO_PI / sr)
    y = np.zeros(n, dtype=np.float64)
    for k, amp in enumerate(harmonics, start=1):
        if amp:
            y += amp * np.sin(ph * k)
    return y.astype(np.float32)


# --------------------------------------------------------------------------
# realtime players
# --------------------------------------------------------------------------
_ARANGE = {}


def _arange(n):
    """Cached ramp; the block size never changes at runtime."""
    a = _ARANGE.get(n)
    if a is None:
        a = _ARANGE[n] = np.arange(n, dtype=np.float64)
    return a


class Loop:
    """Variable-rate looping playback of a precomputed buffer.

    The rate may be ramped across the block, which is what lets the train
    change speed without zipper noise. Two things keep it cheap enough to run
    fifteen of these per block: one wrapped sample is appended to the buffer so
    interpolation never needs a bounds check, and a block that does not cross
    the loop point never touches the modulo at all.
    """

    __slots__ = ("buf", "_ext", "pos", "_last_rate")

    def __init__(self, buf):
        self.buf = np.asarray(buf, dtype=np.float32)
        self._ext = np.concatenate([self.buf, self.buf[:1]])
        self.pos = 0.0
        self._last_rate = 1.0

    def render(self, n, rate):
        """Return `n` samples, ramping from the previous rate to `rate`."""
        length = self.buf.shape[0]
        if rate == self._last_rate:
            idx = _arange(n) * rate
            idx += self.pos
            nxt = self.pos + n * rate
        else:
            steps = np.linspace(self._last_rate, rate, n)
            idx = np.cumsum(steps)
            idx += self.pos - steps[0]
            nxt = idx[-1] + steps[-1]
            self._last_rate = rate
        if idx[-1] >= length:                      # at most one wrap per block
            idx[int(np.searchsorted(idx, length)):] -= length
        self.pos = nxt % length
        i0 = idx.astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        ext = self._ext
        base = ext[i0]
        return base + (ext[i0 + 1] - base) * frac


class StereoBed:
    """A looping bed whose two channels are genuinely decorrelated.

    Amplitude-panning one mono noise bed leaves both ears hearing the same
    signal, which collapses the space and gets fatiguing over a long session.
    Reading the same loop from two positions far apart costs one extra gather
    and puts you inside the sound rather than in front of it.
    """

    __slots__ = ("left", "right")

    def __init__(self, buf, spread=0.37):
        self.left = Loop(buf)
        self.right = Loop(buf)
        self.right.pos = (self.right.buf.shape[0] * spread) % self.right.buf.shape[0]

    def add(self, out, n, rate, gain):
        if gain <= 0.0:
            return
        out[0] += self.left.render(n, rate) * gain
        out[1] += self.right.render(n, rate) * gain


class Voices:
    """Sample-accurate one-shot mixer with equal-power pan and pitch shift.

    `delay` may exceed the block size, so a whole burst of future hits (the
    four axles crossing one rail joint) can be scheduled in a single go.
    """

    def __init__(self, limit=64):
        self._voices = []
        self.limit = limit

    def trigger(self, buf, delay=0.0, gain=1.0, pan=0.0, rate=1.0):
        if len(self._voices) >= self.limit:
            return
        a = (clamp(pan, -1.0, 1.0) + 1.0) * (np.pi * 0.25)
        self._voices.append(
            [np.asarray(buf, dtype=np.float32), float(delay), 0.0, float(rate),
             gain * float(np.cos(a)), gain * float(np.sin(a))]
        )

    def render(self, out):
        n = out.shape[1]
        keep = []
        for v in self._voices:
            buf, delay, pos, rate, gl, gr = v
            if delay >= n:
                v[1] = delay - n
                keep.append(v)
                continue
            start = int(delay)
            avail = n - start
            length = buf.shape[0]
            idx = pos + np.arange(avail) * rate
            cnt = int(np.count_nonzero(idx < length - 1))
            if cnt:
                idx = idx[:cnt]
                i0 = idx.astype(np.int64)
                frac = (idx - i0).astype(np.float32)
                seg = buf[i0] * (1.0 - frac) + buf[i0 + 1] * frac
                out[0, start:start + cnt] += seg * gl
                out[1, start:start + cnt] += seg * gr
            newpos = pos + avail * rate
            if newpos < length - 1:
                v[1] = 0.0
                v[2] = newpos
                keep.append(v)
        self._voices = keep

    def __len__(self):
        return len(self._voices)


class Osc:
    """Phase-continuous additive oscillator, frequency ramped per block."""

    __slots__ = ("phase", "_last_f")

    def __init__(self, f0=100.0):
        self.phase = 0.0
        self._last_f = f0

    def render(self, n, sr, freq, harmonics=(1.0,)):
        inc = np.linspace(self._last_f, freq, n) * (TWO_PI / sr)
        self._last_f = freq
        ph = self.phase + np.cumsum(inc)
        self.phase = float(ph[-1]) % TWO_PI
        y = np.zeros(n, dtype=np.float64)
        for k, amp in enumerate(harmonics, start=1):
            if amp:
                y += amp * np.sin(ph * k)
        return y.astype(np.float32)


def add_panned(out, mono, gain, pan=0.0):
    """Mix a mono block into a channel-major stereo buffer, shape (2, n)."""
    a = (clamp(pan, -1.0, 1.0) + 1.0) * (np.pi * 0.25)
    out[0] += mono * (gain * float(np.cos(a)))
    out[1] += mono * (gain * float(np.sin(a)))
