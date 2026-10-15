# sound-siki — ambient soundscapes tuned to your typing rhythm

**English** | [日本語](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

On the way back from Kyoto — a trip with a self-imposed "no bullet trains, no limited expresses" rule — there was no Wi-Fi, so I was writing code offline without AI assistance.
Listening to music through earphones was distracting, yet complete silence made me restless.
When I took out my earphones and let the steady rhythm of the train and the cicadas outside become my background sound, that was when I focused best.

You could simply play an ambient video on YouTube. But that consumes network bandwidth, and more importantly, it lacks romance.
**Instead of playing static audio recordings, this synthesises soundscapes in real time — gently responding and growing with the natural cadence of your typing.**
That is why **sound-siki** was created.

![sound-siki Animated Demo](assets/demo.gif)

It ships with **zero bytes of recorded audio assets**. It never connects to the internet.
Using only noise generation and pure arithmetic, trains, cicadas, wind chimes, and announcements are all created right on your machine.

- **Audio assets**: **0 bytes** (synthesised entirely from mathematical formulas using numpy at startup)
- **Source size**: **~111 KB / 2,850 lines**
- **CPU usage**: **~5% of one core** with all soundscapes running together
- **Dependencies**: `numpy` / `sounddevice` / `pynput` only (no compiler required)
- **Two ways to enjoy**: **Terminal CLI command** or **VS Code extension**

> **Note on railway lines**: The train lines, station names, and announcements reflect real Tokyo railways. The terminal UI is in Japanese, and stations can be selected easily by number or name.

---

## Demos & Screenshots

### Terminal Interactive Run
Pick a line and destination. The train accelerates as you type, coasts when you pause to think, and smoothly brakes as it pulls into each station.

![Terminal Demo Screenshot](assets/demo_terminal.png)

### VS Code Extension
Board with a single click from the status bar. It monitors edits directly inside the editor without intrusive permissions, providing a calming companion to your coding.

![VS Code Extension Screenshot](assets/demo_vscode.png)

---

## Installation

Requires Python 3.9+.

### As a CLI command (Windows / macOS / Linux)

```sh
pip install git+https://github.com/guousuides/sound-siki
sound-siki            # Pick a line and start your journey (demon also works for compatibility)
```

For development:

```sh
git clone https://github.com/guousuides/sound-siki
cd sound-siki
python -m venv .venv
# Windows:      .\.venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e .
```

#### Platform notes

- **macOS**: The CLI command monitors global keyboard rhythm. The first time you run it, please allow your terminal under System Settings → Privacy & Security → **Accessibility** (and Input Monitoring). If you prefer not to grant OS permissions, please use the **VS Code extension** below, which requires zero special permissions.
- **Linux**: `sounddevice` uses PortAudio, so you may need `sudo apt install libportaudio2`. Global key watching supports X11.
- If running from a clone, you can use the bundled launcher scripts:
  - Windows: `.\demon.ps1 train cicada`
  - macOS / Linux: `./demon.sh train cicada`

---

### As a VS Code extension (Windows / macOS)

> [!NOTE]
> **Marketplace Availability**  
> This extension is currently **not published to the Visual Studio Marketplace**.  
> To use it, please build the `.vsix` package from this repository and install it manually.

The extension lives in `vscode/`. You can board right from your status bar by clicking **▶ sound-siki**:

```sh
cd vscode
npm run package                                   # builds typing-demon-0.1.0.vsix
code --install-extension typing-demon-0.1.0.vsix
```

- On first launch, the extension automatically sets up its own virtual environment with `numpy` and `sounddevice` (Python 3.9+).
- Choose line, direction, service, origin, and destination from Quick Picks, or resume where you left off.
- Keystrokes are read from **text edit events inside the editor** (`demon.keySource: editor`). No OS key hook is used, meaning no Accessibility permissions needed on macOS.
- Click the 🔊 icon in the status bar to adjust master, train, cicada, and announcement volumes live.
- The status bar displays real-time speed, next stop, and remaining distance; announcements stream to the "sound-siki" output channel.
- If a local VOICEVOX engine is present, it launches automatically in the background and shuts down when VS Code closes.
- Closing VS Code automatically parks your train so you can resume your commute next time.

For full settings and details, see [vscode/README.md](vscode/README.md).

---

## Usage

```sh
sound-siki                       # Pick a line and ride
sound-siki train cicada          # Train + Cicada chorus
sound-siki cicada --volume 0.85  # Specify volume (default 0.65)
sound-siki --lines               # List available railway lines
sound-siki --list                # List available soundscapes
sound-siki --devices             # List audio output devices
```

> **Note**: For backwards compatibility, the `demon` command or `python -m demon ...` can be used identically.

When running the train soundscape, it asks interactive questions: line, direction, service, origin, and destination. Pressing Enter accepts sensible defaults:

```text
  どの路線に乗りますか                 (Which line would you like to ride?)
    1  山手線        内回り／外回り    30駅  34.5km   Loop line. Joint clicks take center stage.
    2  中央線快速      下り／上り        24駅  53.1km   High-speed surface line with long stretches.
    3  副都心線       渋谷方面／和光市方面  16駅  20.2km   Underground metro with platform screen doors.
  > 3

  ── 副都心線 急行 ／ 小竹向原 → 渋谷 ／ 4駅 11.9km ／ 目安 15分 ──
```

The estimated journey time (**"目安 15分"**) helps you intuitively budget your work session.

To bypass prompts in scripts or habits, specify arguments upfront:

```sh
sound-siki train --line chuo --from 東京 --to 高尾 --kind 特別快速
sound-siki train --fresh            # Start fresh instead of resuming
sound-siki train --no-exit          # Stay on the platform after arriving
```

Press `Ctrl+C` to fade out cleanly and exit. **Reaching your final destination also completes the journey** — after the final announcement, the train rests at the platform for 30 seconds of quiet afterglow, prints a journey summary, and exits gracefully.

To test the audio without typing:

```sh
sound-siki train --demo                                  # Run with simulated typing script
sound-siki train cicada --render out.wav --seconds 90    # Render directly to a WAV file
```

---

## How typing connects to sound

sound-siki listens to **your rhythm, never the content of your keys**.
It observes only four core properties: speed, persistence, pauses, and corrections.

| Extracted feature | Purpose |
|---|---|
| `kps` | Keystrokes per second (smoothed with a 3 s time constant) |
| `intensity` | `kps` normalized to 0..1 and **softened by a second stage (6–8 s)** — driving power |
| `flow` | A steady accumulator measuring **how consistently you stay in flow** (15–20 s) |
| `idle` | Seconds elapsed since your last keystroke |

Typing is naturally gusty — bursts of rapid input, pauses to reflect, another burst.
Feeding raw typing directly into sound would reveal your own frantic breathing and cause unnecessary stress.
By chaining two smoothing stages, **a gust of typing doesn't become a gust of noise; it transforms into a gentle oceanic tide.**

---

### The physics of the train soundscape

```text
Typing speed   → Master controller (notch). But real trains have inertia and mass
Backspace      → Eases off the notch. Hesitant editing produces slower acceleration
Vehicle speed  → Rail-joint click tempo, motor hum, wind rush, VVVF inverter whine
Position       → Real-world tunnels, curves, crossover points, platforms, and announcements
Enter          → Typhon horn (rate-limited to once every few minutes)
Long pause     → Coasting, then gentle braking. At stations, doors remain open waiting for you
```

The essential element is **mass**. Rapid typing will not launch the train forward instantaneously. Stop typing, and the train coasts gracefully; leave it, and the virtual driver applies the brakes to stop safely.

Crucially, **the train is navigating real geographic distance**. The tracks have real length, and stations inevitably arrive.

```text
Power   a = 0.83 · notch · taper(v) − resistance(v)    Starting accel 3.0 km/h/s
Coast   a = − resistance(v)
Brake   a = − 1.00 · b                                  Service max 3.6 km/h/s
        v += a·dt ,  x += v·dt
```

**The brakes belong to the driver, not to you.**
Every audio block, the system computes the exact deceleration needed to stop cleanly at the next station (`v² / 2d`). Once that reaches service braking thresholds, the driver applies the brakes automatically.

**The accelerator is your typing; the schedule and brakes belong to the train.**
This calm asymmetry provides a gentle, encouraging companion to deep work.

| Typing pattern | Fukutoshin Express, Wakōshi → Shibuya (est. 23 min) |
|---|---|
| Typing continuously | **~24 min** |
| 3 min typing, 3 min resting | ~44 min |
| 2 min typing, 5 min resting | ~72 min |
| 1 min typing every 10 min | **~191 min** |

Once the train arrives at a station, **the doors will not close until you resume typing**.
If you pause for too long, a gentle passenger announcement plays:

> ♪ Ladies and gentlemen, we are currently holding at this station to attend to passenger needs.

---

### Pure mathematical sound synthesis

sound-siki operates under a strict principle: zero audio asset files and no outbound network calls.
Even the station announcements are synthesized on the fly using **additive formant synthesis**.

Japanese is a mora-timed language with only five vowels. Station names can be modeled as **a rhythmic sequence of five vowel frequencies at ~7 beats per second**:

- Vowels use additive harmonic series shaped by three formant resonance filters
- Filtered through the frequency curve of vintage train car ceiling speakers (330–3300 Hz) with short reflections
- Consonants provide four distinct acoustic gestures (plosive, fricative, nasal, glide) that create crisp syllable cadence

While speech isn't crystal-clear, **that is intentional**. The semantic text is shown in the terminal, while the sound gives you only the cadence and pitch contour — exactly what your subconscious registers while staying focused on writing code.

---

### Realistic voice announcements with VOICEVOX

If you prefer realistic Japanese train conductor voices, **sound-siki seamlessly connects to a local VOICEVOX engine**.
It automatically probes for an engine at `127.0.0.1:50021` and cleanly falls back to formant synthesis if none is active.

```sh
sound-siki train --speaker 8                        # Speaker style ID (default 3 = Zundamon)
sound-siki train --announce japanese                # Japanese-only announcements
sound-siki train --voicevox http://127.0.0.1:10101  # Custom compatible engine (e.g. AivisSpeech)
sound-siki train --voice synth                      # Force mathematical formant synthesis
sound-siki train --announce-volume 0.5              # Adjust announcement volume
sound-siki train cicada --cicada-volume 0.4         # Adjust cicada volume
```

- **Bilingual announcements**: Real Japanese railway phrasing followed by English announcements for departures, next stops, and transfers.
- **4-note car chime**: The iconic C5-E5-G5-C6 chime before announcements is also calculated entirely via sine formulas in numpy.

---

### The cicada soundscape

```text
Flow accumulator    → Chorus density (from a solitary distant song to an enveloping chorus)
Backspace bursts    → Nearby cicadas startle into silence, gradually returning
Enter               → Wind chime on the veranda
20 minutes of flow  → Higurashi (evening cicadas) join in as the atmosphere transitions to dusk
```

Cicadas do not respond to sudden typing spikes; they awaken with **steady, sustained concentration (`flow`)**.
Individual cicadas vary in playback rate, pan, and phase, creating an organic, non-fatiguing natural soundscape.

---

## Privacy & Security

The CLI version installs a standard keyboard hook to measure tempo.
Because of this, **strict privacy guarantees are built directly into the architecture**:

- Keystroke callbacks output only four generic numeric classifications: character, space, backspace, or enter.
- **No typed characters, key codes, window titles, or timestamps are ever recorded or stored.**
- Zero network communication occurs, other than local HTTP requests to a local VOICEVOX instance (`127.0.0.1`).
- Modifier keys (Shift, Ctrl, Cmd, Alt) are immediately discarded.

The only file written to disk is `~/.demon/journey.json`:

```json
{ "version": 1, "line": "chuo", "kind": "特別快速", "direction": 1,
  "origin": "東京", "dest": "高尾",
  "x_m": 7535.8, "elapsed_s": 600.0, "sessions": 1 }
```

This contains only the position of the train in metres and elapsed run time. It contains **zero keystroke or user information**.

In the VS Code extension's default `editor` mode, no OS-level hooks are used at all.

---

## Adding new soundscapes

You can easily create new ambient environments by subclassing `Demon` in `demon/demons/base.py` and implementing `prepare()` and `render()`:

- **Rain soundscape**: Typing intensity shapes the rainfall from drizzle to downpour
- **Campfire**: Sustained typing keeps the embers glowing and wood crackling
- **Coffee shop**: Steady flow brings gentle murmur and clinking cups to life

---

## Contributing

Pull requests and issues are warmly welcomed in English or Japanese!
Feel free to contribute new lines, new ambient soundscapes, or platform testing reports.
Please check [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

[MIT License](LICENSE) © 2026 guousui
