# demon — typing-fed ambient sound for VS Code

**English** | [日本語](#日本語)

Your typing drives a train. Type, and it accelerates out of the station; stop, and it
coasts, brakes, and waits at the platform with the doors open. Cicadas thicken as you
keep a steady flow. Every sound — rail joints, VVVF whine, tunnels, announcements,
cicadas, wind chimes — is **synthesised on the spot from noise and arithmetic**.
Zero audio files, no network.

## Features

- Ride real Tokyo lines by distance: 山手線 (Yamanote), 中央線快速 (Chūō Rapid), 副都心線 (Fukutoshin)
- Pick line, direction, service, origin and destination from Quick Picks; see the estimated ride time
- Status bar shows speed, next stop and distance left; announcements go to the **demon** output panel
- Close VS Code and the train is parked — resume next time
- Optional real voice for announcements via a local [VOICEVOX](https://voicevox.hiroshiba.jp/) engine

## Requirements

- **Python 3.9+** on Windows or macOS (Linux likely works too).
  On first start the extension creates its own venv and installs `numpy` and `sounddevice`.
  If Python is not found automatically, set `demon.pythonPath`.

## Usage

Click **▶ demon** in the status bar (or run `demon: 乗車する (Start)` from the Command Palette).
Click it again to get off.

## Settings

| Setting | Default | |
|---|---|---|
| `demon.demons` | `["train"]` | Which demons to wake: `train`, `cicada` |
| `demon.volume` | `0.65` | 0..1 |
| `demon.trainVolume` / `demon.cicadaVolume` | `1` | Per-demon volume, 0..2. Applies live |
| `demon.announceVolume` | `1` | Announcement volume, 0..2. Applies live |

Click the 🔊 icon in the status bar to open the mixer (master / train / cicadas / announcements).
| `demon.keySource` | `editor` | `editor`: only edits in VS Code (no permissions). `global`: OS-wide key hook via pynput (macOS needs Accessibility permission) |
| `demon.voice` | `auto` | `auto` / `voicevox` / `synth` |
| `demon.speaker` | `3` | VOICEVOX style ID |
| `demon.noExit` | `false` | Keep running after arriving |
| `demon.pythonPath` | `""` | Python used to create the venv |

## Privacy

In `editor` mode no key hook is installed. Each edit is reduced inside the extension to
one of four letters (char / space / backspace / enter) before it reaches Python — the text
you write never leaves VS Code. The only file written is `~/.demon/journey.json`: where
the train is and how long it has run.

---

## 日本語

打鍵で電車が走る。打てば駅を出て加速し、手を止めれば惰行して、やがてホームでドアを開けたまま待つ。
淡々と打ち続ければ蝉が増える。ジョイント音も VVVF も車内放送も、全部**その場でノイズと四則演算から合成**。
音声ファイル 0 バイト、ネット接続なし。

- **必要なもの**: Python 3.9 以上（Windows / macOS）。初回に拡張専用の venv を作り `numpy` / `sounddevice` を入れる。
  見つからなければ設定 `demon.pythonPath`
- **使い方**: ステータスバーの **▶ demon** を押す → 路線・向き・種別・出発駅・目的駅を選ぶ。もう一度押すと降りる
- 打鍵は既定ではエディタの編集から取る（キーフックなし、macOS の許可も不要）。ターミナルの打鍵も拾うなら `demon.keySource: global`
- VS Code を閉じると位置を保存。次回「続きから」乗れる
- ローカルの VOICEVOX が動いていれば、車内放送が肉声になる

詳しい仕組みは [リポジトリの README](https://github.com/guousuides/sound-siki#readme) へ。

## License

MIT
