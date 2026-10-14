# demon — an ambient sound daemon that feeds on your typing

**English** | [日本語](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

On the way back from Kyoto — a trip with a self-imposed "no bullet trains, no limited
expresses" rule — there was no Wi-Fi, so I was writing code without AI.
Music in my earphones was distracting. Silence made me restless.
I took the earphones out and let the sound of the train and the cicadas outside be the
soundtrack, and that was when I focused best.

You could just play an ambience video on YouTube. But that eats bandwidth, and more to
the point, there's no romance in it.
**So this doesn't play sound — it synthesises it on the spot, and it grows by feeding on
your keystrokes.** Hence "daemon".

It ships with zero bytes of audio. It never touches the internet.
Trains, cicadas, wind chimes and sparrows are all built from noise and arithmetic.

- Audio assets: **0 bytes** (synthesised with numpy at startup)
- Whole source: **~111 KB / 2,850 lines**
- CPU: **~5% of one core** with both demons at full tilt
- Dependencies: `numpy` / `sounddevice` / `pynput` only (no compiler needed)
- Two ways to use it: **a terminal command** or **a VS Code extension**

> The train lines, station names and announcements are Japanese (Tokyo railways).
> The terminal UI is in Japanese; station names can be typed or picked by number.

---

## Install

Requires Python 3.9+.

### As a command (Windows / macOS / Linux)

```sh
pip install git+https://github.com/guousuides/sound-siki
demon            # pick a line and ride
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

Platform notes:

- **macOS**: the command watches the whole keyboard, so the first time you must allow your
  terminal app under System Settings → Privacy & Security → **Accessibility** (and Input
  Monitoring). If you'd rather not, use the VS Code extension below — it needs no permission.
- **Linux**: `sounddevice` uses PortAudio, so you may need `sudo apt install libportaudio2`.
  Key watching assumes X11 (it does not work under Wayland).
- From a clone you can use the bundled launchers without activating the venv:
  `.\demon.ps1 train cicada` on Windows, `./demon.sh train cicada` on macOS / Linux.

### As a VS Code extension (Windows / macOS)

The extension lives in `vscode/`. No terminal needed: click **▶ demon** in the status bar.

```sh
cd vscode
npm run package                                   # builds typing-demon-0.1.0.vsix
code --install-extension typing-demon-0.1.0.vsix
```

- On first start it creates its own venv and installs `numpy` / `sounddevice` (Python 3.9+
  required). It looks for `py -3` on Windows and `python3` on macOS; otherwise set
  `demon.pythonPath`.
- Line, direction, service, origin and destination are chosen from Quick Picks, as is
  resuming your last ride.
- Keystrokes are taken from **edits in the editor** (`demon.keySource: editor`). No OS key
  hook, so no Accessibility permission on macOS. Set it to `global` to also pick up typing
  in the terminal.
- The 🔊 icon in the status bar opens a mixer: master, train, cicadas and announcements, each
  adjustable live.
- The status bar shows speed, next stop and distance left; announcement text goes to the
  **demon** output panel.
- Closing VS Code parks the train where it is.

See [vscode/README.md](vscode/README.md) for details.

## Usage

```sh
demon                       # pick a line and ride
demon train cicada          # train + cicadas
demon cicada --volume 0.85  # default is 0.65
demon --lines               # list lines
demon --list                # list demons
demon --devices             # list output devices
```

Without the `demon` command (e.g. a bare clone), `python -m demon ...` does the same.

Every time it starts, the train demon asks **where you're riding from and to**: line,
direction, service, origin, destination — each a number, and pressing Enter takes the
default.

```
  どの路線に乗りますか                 (Which line?)
    1  山手線        内回り／外回り    30駅  34.5km   地上・周回。ジョイントが主役。
    2  中央線快速      下り／上り        24駅  53.1km   地上・高速。駅間が長い。
    3  副都心線       渋谷方面／和光市方面  16駅  20.2km   地下・全駅ホームドア。
  > 3

  ── 副都心線 急行 ／ 小竹向原 → 渋谷 ／ 4駅 11.9km ／ 目安 15分 ──
```

**The "目安 15分" (about 15 min) is the point**: before you board, you've decided how long
today's stretch of work is. If the questions get tiresome, give everything up front:

```sh
demon train --line chuo --from 東京 --to 高尾 --kind 特別快速
demon train --fresh            # ignore the parked ride and start over
demon train --no-exit          # don't quit on arrival
```

Ctrl+C fades out and exits. **Arriving at your destination also ends it** — after the
terminal-station announcement it lingers on the platform for 30 seconds, prints a
summary of the run, and goes to sleep.

To hear it without touching the keyboard:

```sh
demon train --demo                                  # scripted virtual typing
demon train cicada --render out.wav --seconds 90    # render to WAV
```

These two don't ask for a line (they run the default Yamanote line).

---

## How typing couples to sound

The demons eat **rhythm, not characters**. They look at only four things: speed,
persistence, pauses and corrections.

| Feature | Meaning |
|---|---|
| `kps` | keystrokes per second (smoothed, 3 s time constant) |
| `intensity` | `kps` normalised to 0..1 and **dulled by a second stage (6–8 s)** — the drive |
| `flow` | a slow accumulator of **whether you're keeping it up**, not how fast (15–20 s) |
| `idle` | seconds since the last keystroke |

Typing is naturally gusty — a burst, a pause to think, another burst. Pipe that straight
into the sound and you can hear yourself panting, which is anything but calming. So the
smoothing has two stages. **A gust of typing doesn't become a gust of sound; it becomes a
slow tide.**

### The train demon

```
typing speed   → master controller (notch). But a train has mass
corrections    → shallower notch. Hesitant driving doesn't make good time
speed          → rail-joint spacing, rolling pitch, wind, VVVF whine
position       → tunnels, curves, points, platforms — and announcements
Enter          → horn (typhon), at most once every few minutes
long silence   → coasting, then braking. At a station, the doors won't close
```

The key is **mass**. Typing fast doesn't accelerate you instantly. Stop and it coasts;
leave it and the driver brakes to a halt. It's not a switch — it only runs if you keep
feeding it.

And now **it has somewhere to go**. It really advances by distance along the track, and
the next station always comes.

```
power   a = 0.83 · notch · taper(v) − resistance(v)    starting accel 3.0 km/h/s
coast   a = − resistance(v)
brake   a = − 1.00 · b                                  service max 3.6 km/h/s
        v += a·dt ,  x += v·dt
```

**The brake isn't yours.** Every block, the driver computes how much deceleration it
would take to stop exactly at the next station — `v² / 2d` — and applies the brake once
that reaches a suitable fraction of service braking. So however fast you type, the
station comes, and the train always stops there.
**The controller is yours; the timetable is not.** That asymmetry is the whole thing.

Typing faster gets you there sooner — but on a stopping service only the acceleration
out of each station is affected, so the difference is about 10%. That's physically
correct. What really matters is the other side: **stop typing and you stop moving**.

| How you type | Fukutoshin Express, Wakōshi → Shibuya (est. 23 min) |
|---|---|
| Typing continuously | **24 min** |
| 3 min on, 3 min off | 44 min |
| 2 min on, 5 min off | 72 min |
| 1 min in every 10 | **191 min** |

At a station it's blunter still: **if the typing stops, the doors don't close**.
Leave it long enough and this plays in the car:

> ♪ Ladies and gentlemen, we are currently holding at this station to attend to a
> passenger.

Slack off and the conductor calls you out.

### What used to be dice became terrain

The earlier version of this demon rolled **dice** for a tunnel when you pressed Enter and
for points when you pressed Backspace. Now that it has a position, everything sounds
because it's *there*.

- A tunnel is at the **metre mark** where that line enters a tunnel
- Points are on the **approach side** of stations with crossovers
- A curve squeals because you went through that curve
- A rail joint clicks because `floor(x / 25)` changed

The Fukutoshin line dives underground right after leaving Wakōshi. That one tunnel entry
happens not because you pressed Enter, but **because the tunnel is there**.

The joint sound is computed. Standard Japanese rail is 25 m long, bogie wheelbase about
2.4 m, bogie centres about 14 m apart. So one car crossing one joint gives four hits —
"ga-tan, go-ton" — spaced by exactly those distances divided by speed.

> The Fukutoshin line opened in 2008 with continuous welded rail, so **in reality it
> doesn't go ga-tan go-ton**. Here realism is bent on purpose and the joints play at 42%
> volume — purely because a train demon without ga-tan go-ton is too lonely.

### Announcements — speaking without recordings or TTS

The constraints are the design. No audio files, no sockets. So an announcement can't be a
WAV, and it can't be the OS's speech engine. **All that's left is arithmetic.**

Japanese is mora-timed and has only five vowels. So a station name is just
**a rhythm of five vowels at about seven beats a second**.

- Vowels are additive synthesis: a harmonic series at some pitch, shaped by three formant
  resonances
- Band-limited to an in-car speaker (330–3300 Hz) and put in a steel box with two short taps
- Consonants are just four gestures — plosive, fricative, nasal, glide — placed before the
  vowel. Crude, but **the syllable boundaries come through, and it's the boundaries that
  make speech feel readable**
- Contracted sounds, geminates, the moraic n and long vowels are handled by the parser, so
  writing the reading into the line data is enough to make it speak

You can't make out a word. **That's intended**: the meaning is printed in the terminal in
Japanese. What comes out of the speaker is only the shape — how many beats the station
name has, where it rises and falls — and on a train you're only half listening to, that
shape is what you actually take in.

```
四ツ谷  Yotsuya     → o-u-a        3 beats, short
西荻窪  Nishi-Ogikubo → i-i-o-i-u-o  6 beats, long
```

So **you can hear the station name change even without understanding it**.

The voice pitch is drawn from two options at the start of each session. Today's conductor
is decided.

### A real voice (VOICEVOX)

For days when shape alone isn't enough: **if a VOICEVOX engine is running locally, the
announcements use its voice**. With the default `auto` it looks for one, and silently
falls back to the formant synthesis above if it's not there.

1. Install and start [VOICEVOX](https://voicevox.hiroshiba.jp/) (the engine listens on
   `127.0.0.1:50021`). On Windows, `.\start-voicevox.ps1` starts just the engine in the
   background without opening the app
2. Ride as usual with `demon train`. If startup prints `車内放送: VOICEVOX:ずんだもん（ノーマル）`,
   it's a real voice

```sh
demon train --speaker 8                        # voice style ID (default 3 = Zundamon)
demon train --voicevox http://127.0.0.1:10101  # a compatible engine such as AivisSpeech
demon train --voice synth                      # formant synthesis only
demon train --announce-volume 0.5              # announcements only at half volume (0–2, default 1)
demon train cicada --cicada-volume 0.4         # quieter cicadas (likewise --train-volume)
```

- The engine is given **the sentence in kanji** (accents come out more natural that way),
  except station and service names, which are inserted in katakana from the line data —
  names like 「四ツ谷」 and 「雑司が谷」 are exactly what dictionaries get wrong
- The studio-quality voice is passed through **the same ceiling speaker and steel box** as
  the formants (330–3300 Hz, three short reflections) before it plays
- Every sentence spoken is kept as a WAV in `~/.demon/voice/`. Station announcements repeat,
  so after one lap **it speaks with a real voice even with the engine off**
- The only connection is to the engine on `127.0.0.1`. No proxy, no internet
- If synthesis fails, it gives up on the engine for the rest of the ride and uses formants.
  A broken announcement never stops the train

> The voice credit is shown at startup (e.g. `VOICEVOX:ずんだもん`). If you publish
> recordings, credit them according to each character's terms of use.

> There is deliberately no departure melody. Those are someone's copyrighted work, so only
> a characterless electric bell rings.

Each announcement is assembled into one buffer and handed to the mixer as a single voice. A
20-beat sentence costs the realtime side the same as one rail joint. The synthesis itself
runs off the audio thread (in a dedicated thread) — spending a few milliseconds inside a
46 ms block is a sure way to drop out on a slow machine.

---

### The cicada demon

```
flow                → how many are singing (one far away … a full chorus)
Backspace bursts    → the nearby ones startle, fall silent, creep back
Enter               → a wind chime on the veranda (rate-limited)
20 minutes of flow  → higurashi join in; the afternoon tilts toward evening
```

The cicadas respond not to speed but to **whether you're keeping it up**.
A fast burst doesn't add any. Keep going steadily and they slowly thicken.
The population doesn't step by whole insects — the one at the boundary fades in and out at
partial volume — so the thickness changes as **a gradient, not steps**. It tops out at
about eight.

Large brown cicadas are 3–8 kHz noise with 68 Hz AM; minmin-zemi are phrases that break
from "meeen" into a 9.5 Hz "min-min-min"; higurashi are 11 Hz pulses. Each individual gets
its own playback rate, position and phase, so with only three buffers the chorus never
audibly repeats.

### Built to happen only now and then

Coding involves a lot of Enter. Make Enter = horn and it'd be blaring like a level
crossing, so the horn has a 70–190 s cooldown. The wind chime, for the same reason,
35–110 s. A single Backspace doesn't startle the cicadas either (they need four presses'
worth of "pressure").

Tunnels and points have left this group. **They're decided by position now, not by
cooldown**, so nobody has to choose the spacing — the track already has.

The remaining constants sit at the top of each demon's `render()` and of `route.py`, so you
can tweak them to taste.

---

## Privacy

The command (and the extension's `global` mode) installs a global keyboard hook — that is,
technically the same entry point as a keylogger. So by design, **it throws everything away
at the door**:

The only thing that leaves `on_press` in `demon/keywatch.py` is an integer `0..3` (char /
space / correction / newline). No characters, key codes, window titles or timestamps are
kept. Nothing goes to the network (the only socket opened is to 127.0.0.1 when using
VOICEVOX). Modifiers like Shift and Ctrl are discarded before counting.

The VS Code extension's default (`editor` mode) installs no hook at all. Editor change
events are reduced inside the extension to a single letter `c/s/b/e` before they're handed
to Python, so what you write never leaves the process.

### The only thing written to disk

Now that there's a destination, it writes exactly one file, `~/.demon/journey.json`.
Eight fields in all — here's a real one:

```json
{ "version": 1, "line": "chuo", "kind": "特別快速", "direction": 1,
  "origin": "東京", "dest": "高尾",
  "x_m": 7535.8, "elapsed_s": 600.0, "sessions": 1 }
```

**Still not a single byte derived from your typing.** Not characters, not key codes, not a
keystroke count, not when you typed. What's there is **where the train is and how many
seconds it has run** — two numbers about a train — and the name of its route. Reading it
tells you nothing about you.

It exists because the Yamanote line is a loop and some lines can't be finished in one
sitting. A journey that doesn't end in one go needs somewhere to leave the train overnight.

`--fresh` ignores it, and the file is deleted when you reach the end.

Only when VOICEVOX is used, announcement WAVs accumulate in `~/.demon/voice/`. They contain
only **fixed sentences read aloud**, like "Next, Shibuya." — again unrelated to your typing.
Delete them and they're simply regenerated next time.

`--demo` installs no hook and writes no file, so you can just listen.

---

## How it works

It all rests on one idea: **do the expensive work once, at startup**.

1. `prepare()` synthesises noise in the frequency domain (`dsp.noise_loop`): an arbitrary
   magnitude spectrum times random phase, inverse-FFT'd, so the result **loops by
   construction** — no seam crossfades, no clicks. One-shots like rail joints, brakes,
   flange squeal and wind chimes are also built here, once.
2. The realtime callback just reads those prebuilt buffers at variable rates and mixes
   them. No IIR filters, no FFTs.

So each block (46 ms) is a few dozen numpy operations, with 5% CPU and a few MB of memory.

While mixing, buffers are channel-major `(2, n)` so each demon adds into contiguous
memory, transposed once just before going to the sound card. Rolling and wind noise aren't
panned mono; the same loop is read from two distant offsets so left and right are
decorrelated (panned mono collapses to the centre and gets tiring over long sessions).

```
demon/
  dsp.py        noise synthesis, loop playback, one-shot scheduler (numpy only)
  keywatch.py   keystrokes → features. Characters are dropped at the door
  engine.py     block loop, master, WAV export
  lines.py      stations, distances, tunnels, curves, points for 3 lines
  route.py      driving: notch, brakes, position. Knows nothing about sound
  announce.py   mora → formants. Announcement synthesis and scripts
  voice.py      VOICEVOX voice through the ceiling speaker (else formants)
  journey.py    the only place that touches disk (position and time only)
  picker.py     boarding: pick a line by typing numbers
  demons/
    base.py     the demon type
    train.py    the train demon
    cicada.py   the cicada demon
vscode/         the VS Code extension (spawns `python -m demon --ipc`)
```

`route.py` knowing nothing about sound is deliberate: the physics can be verified without
an audio device. In fact the Yamanote loop in 61 minutes and the Chūō Special Rapid
Tokyo–Takao in 54 were measured headless and tuned to match (both close to the real
timetable).

> Station distances are operating kilometres, and route totals match published figures
> (Yamanote 34.5 km, Chūō Tokyo–Takao 53.1 km, Fukutoshin 20.2 km). Curves and points are
> not surveyed; they're placed **where that kind of line tends to have them** — subways
> curve constantly, and stations with depots have crossovers on the approach. Which side
> the doors open on is not real data either.

## Adding a demon

Subclass `Demon`, write `prepare()` and `render()`, and register it in `REGISTRY` in
`demons/__init__.py`. `render(out, rhythm, events, dt)` **adds into** the `(2, n)` `out`
(never overwrites).

Rain (typing strength = rainfall), a campfire (`flow` is firewood), a café (customers are
`flow`) — all fit the same frame as-is.

## Credits

The idea started from [nathan-fiscaletti/keyboardsounds](https://github.com/nathan-fiscaletti/keyboardsounds).
That one plays the keystrokes themselves. This one feeds on keystrokes to move the world
that's playing.

---

## Contributing

Issues and PRs welcome — new lines and new demons (rain, campfire, café…) especially.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT License](LICENSE) © 2026 guousui

The code is MIT. Audio generated with VOICEVOX is not included in this repository and is
subject to the terms of each character and engine. Line data (station names, operating
kilometres) is based on public information; this project is not affiliated with any
railway operator.
