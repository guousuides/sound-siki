# sound-siki — typing-fed ambient sound for VS Code

**English** | [日本語](#日本語)

Your typing drives a train. Type, and it accelerates out of the station; pause, and it
coasts, brakes, and waits peacefully at the platform with doors open. Cicadas gently thicken as you
keep a steady flow. Every sound — rail joints, motor hum, tunnels, announcements,
cicadas, and wind chimes — is **synthesised in real time from noise and arithmetic**.
Zero audio files, no network required.

> [!NOTE]
> **Marketplace Availability Notice**  
> This extension is currently **not published to the Visual Studio Marketplace**.  
> To use it, please build or obtain the `.vsix` package from this repository and install it manually via `code --install-extension <package>.vsix`.

## Features

- Ride real Tokyo lines calculated by distance: 山手線 (Yamanote), 中央線快速 (Chūō Rapid), 副都心線 (Fukutoshin)
- Pick line, direction, service, origin and destination from Quick Picks, with estimated ride time shown
- Status bar displays current speed, next stop, and remaining distance; announcements stream to the **sound-siki** output panel
- Close VS Code and the train is parked safely — resume seamlessly next time
- Optional warm voice for announcements via a local [VOICEVOX](https://voicevox.hiroshiba.jp/) engine

## Requirements

- **Python 3.9+** on Windows or macOS (Linux supported).
  On first run, the extension creates its dedicated venv and installs `numpy` and `sounddevice`.
  If Python is not found automatically, please set `demon.pythonPath`.

## Usage

Click **▶ sound-siki** in the status bar (or run `sound-siki: 乗車する (Start)` from the Command Palette).
Click it again whenever you wish to get off.

## Settings

| Setting | Default | Description |
|---|---|---|
| `demon.demons` | `["train"]` | Active soundscapes: `train`, `cicada` |
| `demon.volume` | `0.65` | Master volume (0..1) |
| `demon.trainVolume` / `demon.cicadaVolume` | `1` | Individual sound volume (0..2, applies live) |
| `demon.announceVolume` | `1` | Train announcement volume (0..2, applies live) |

Click the 🔊 icon in the status bar to open the mixer anytime.

| Setting | Default | Description |
|---|---|---|
| `demon.keySource` | `editor` | `editor`: only edits in VS Code (no OS permissions needed). `global`: OS-wide key hook via pynput |
| `demon.voice` | `auto` | `auto` / `voicevox` / `synth` |
| `demon.autoStartVoicevox` | `true` | Automatically start a locally installed VOICEVOX engine when boarding |
| `demon.voicevoxEnginePath` | `""` | Path to `vv-engine/run.exe` (`run` on macOS) if not found automatically |
| `demon.speaker` | `3` | VOICEVOX style ID |
| `demon.noExit` | `false` | Keep running even after arriving at the destination |
| `demon.pythonPath` | `""` | Python executable used to create the environment |

## Privacy

In `editor` mode, no OS key hook is used. Each edit is reduced inside the extension to
one of four generic categories (char / space / backspace / enter) before reaching Python — your typed code
never leaves VS Code. The only file written is `~/.demon/journey.json`: saving only where
the train is and how long it has travelled.

---

## 日本語

> [!NOTE]
> **Marketplace 未公開について**  
> 本拡張機能は現在、**Visual Studio Marketplace には公開していません**。  
> ご利用の際は、本リポジトリから `.vsix` ファイルをパッケージング（`npm run package`）またはダウンロードし、手動でインストールしてください。

あなたのタイピングに合わせて、心地よい電車の走行音が響きます。キーを叩けば駅を出発して加速し、手を止めると惰行して、駅のホームでドアを開けて静かに待ってくれます。
淡々と集中を続ければ、木々から蝉の声が重なります。レールの継ぎ目音（ジョイント音）も、VVVFインバータの唸りも、車内アナウンスも、すべて**その場で計算式からリアルタイム合成**しています。
音声ファイルは0バイト、外部ネットワーク通信も一切ありません。

- **必要な環境**: Python 3.9 以上（Windows / macOS / Linux）。初回起動時に拡張専用の仮想環境を自動作成し、`numpy` と `sounddevice` をセットアップします。もし見つからない場合は、設定 `demon.pythonPath` で Python のパスを指定してください。
- **使い方**: ステータスバーの **▶ sound-siki** をクリックするだけで乗車できます。路線・向き・種別・出発駅・目的駅をクイックピックから選ぶと旅が始まります。もう一度クリックするといつでも下車できます。
- **プライバシー**: キー入力は既定でエディタ内の文字編集イベントから取得します（OSのキーフックは使用しないため、macOSのアクセシビリティ許可も不要です）。作業中のソースコードの内容が外部に漏れることは一切ありません。
- **旅の続きから乗車**: VS Code を閉じると、電車の現在地が自動保存されます。次回開いたときに「前回の続きから」乗車できます。
- **リアルな肉声放送**: ローカルで VOICEVOX を起動しておくと、車内アナウンスが温かみのある肉声（ずんだもん等）になります。

詳しい仕組みやターミナル版の使い方は、[リポジトリの README](https://github.com/guousuides/sound-siki#readme) をご覧ください。

## License

MIT
