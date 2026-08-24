"""The audio side of the daemon: pull keystroke features, let the demons add
into one stereo block, then limit and hand it to the sound card.

The same block loop drives both realtime playback and offline rendering, so
what you hear is exactly what `--render` writes to a WAV.
"""
from __future__ import annotations

import wave

import numpy as np

from .dsp import ema_alpha
from .keywatch import Rhythm


class Engine:
    def __init__(self, demons, source, sr=44100, block=2048, volume=0.7):
        self.demons = demons
        self.source = source
        self.sr = sr
        self.block = block
        self.volume = float(volume)
        self.rhythm = Rhythm()
        self.dt = block / float(sr)
        # Channel-major while mixing: every demon accumulates into contiguous
        # memory, and it is transposed once on the way to the sound card.
        self._buf = np.zeros((2, block), dtype=np.float32)
        self._gain = 0.0          # master fade, kept off zero-crossing clicks
        self._gain_target = 1.0
        self.peak = 0.0
        self.underruns = 0
        self.error = None

    # ------------------------------------------------------------------ core
    def render_block(self, n=None):
        n = n or self.block
        buf = self._buf if n == self.block else np.zeros((2, n), dtype=np.float32)
        buf[:] = 0.0

        dt = n / float(self.sr)
        events = self.source.poll(dt)
        self.rhythm.update(dt, events)
        for demon in self.demons:
            demon.render(buf, self.rhythm, events, dt)

        # Master fade ramped across the block, then a soft limiter. tanh keeps
        # a sudden pile-up of rail joints from clipping without a pumping
        # compressor, which would be audible in something this quiet.
        step = self._gain + ema_alpha(dt, 1.5) * (self._gain_target - self._gain)
        ramp = np.linspace(self._gain, step, n, dtype=np.float32)
        self._gain = float(step)
        buf *= ramp * self.volume
        np.tanh(buf * 1.6, out=buf)
        buf *= 0.625

        self.peak = max(self.peak * 0.98, float(np.max(np.abs(buf))))
        return buf.T

    def fade_out(self):
        self._gain_target = 0.0

    @property
    def faded_out(self):
        return self._gain < 0.01 and self._gain_target == 0.0

    # -------------------------------------------------------------- realtime
    def stream(self, device=None):
        import sounddevice as sd

        def callback(outdata, frames, time_info, status):
            if status:
                self.underruns += 1
            try:
                outdata[:] = self.render_block(frames)
            except Exception as exc:            # never let the audio thread die quietly
                self.error = exc
                outdata[:] = 0.0
                raise sd.CallbackAbort

        return sd.OutputStream(samplerate=self.sr, blocksize=self.block, device=device,
                               channels=2, dtype="float32", callback=callback,
                               latency="low")

    # --------------------------------------------------------------- offline
    def render_wav(self, path, seconds, progress=None):
        total = int(seconds * self.sr)
        chunks, done = [], 0
        while done < total:
            n = min(self.block, total - done)
            chunks.append(self.render_block(n).copy())
            done += n
            if progress and done % (self.sr * 5) < self.block:
                progress(done / self.sr)
        audio = np.concatenate(chunks, axis=0)
        pcm = np.clip(audio, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(pcm.tobytes())
        return audio
