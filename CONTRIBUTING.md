# Contributing / コントリビュート

Issues and pull requests are welcome, in Japanese or English.
Issue・PR は日本語でも英語でも歓迎です。

## Setup / 開発環境

```sh
git clone https://github.com/guousuides/sound-siki
cd sound-siki
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate
pip install -e .
demon train --demo               # listen without a keyboard hook / キー監視なしで鳴らす
```

VS Code extension / 拡張機能: open `vscode/` in VS Code and press F5.
`vscode/` を VS Code で開いて F5 で拡張開発ホストが起動します（リポジトリ直下の `demon/` をそのまま使います）。

## Ground rules / 守ってほしいこと

1. **No audio files.** Every sound is synthesised at startup. / 音声ファイルを追加しない。音はすべて起動時に合成する。
2. **No network** except a VOICEVOX engine on `127.0.0.1`. / 通信は `127.0.0.1` の VOICEVOX だけ。
3. **Nothing derived from typing leaves the key callback** except a category (char / space / backspace / enter).
   Nothing about typing is ever written to disk. / 打鍵から外に出してよいのは 4 種類のカテゴリだけ。ディスクにも書かない。
4. **Keep the audio callback cheap** - heavy work goes in `prepare()` or a worker thread.
   / オーディオコールバックでは重い処理をしない。`prepare()` か別スレッドへ。

## Ideas / 歓迎するもの

- New lines in `demon/lines.py` / 新しい路線
- New demons (rain, campfire, café…) - see "デーモンを足す" in the README / 新しいデーモン（雨、焚き火、喫茶店…）
- Testing on macOS / Linux and reports / macOS・Linux での動作報告

Before a PR, please check `demon train --render out.wav --seconds 60` still renders.
PR の前に `--render` で書き出せることを確認してください。
