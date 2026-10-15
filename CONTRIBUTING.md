# Contributing / コントリビュート

Issues and pull requests are welcome, in Japanese or English.
Issue・PR は日本語でも英語でも大歓迎です！お気軽にどうぞ。

## Setup / 開発環境のセットアップ

```sh
git clone https://github.com/guousuides/sound-siki
cd sound-siki
python -m venv .venv
# Windows:      .\.venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e .
sound-siki train --demo          # キー監視なしでデモ走行をテスト再生できます
```

VS Code extension / 拡張機能:
`vscode/` フォルダを VS Code で開いて `F5` キーを押すと拡張機能の開発ホストが起動します（リポジトリ直下の Python コードをそのまま使用します）。

## Ground rules / 開発にあたってのお願い

本プロジェクトの心地よさと安全性を守るため、以下の点にご留意いただけますと幸いです：

1. **No audio files（外部音源アセットの追加なし）**: すべての音は起動時に数式と乱数から合成します。
2. **No network（外部ネットワーク接続なし）**: 通信はローカル (`127.0.0.1`) の VOICEVOX エンジンのみに制限しています。
3. **Privacy first（打鍵情報の完全破棄）**: 打鍵コールバックから出力されるのは 4 つの汎用カテゴリ（文字 / スペース / 訂正 / 改行）のリズム情報のみです。入力文字やコード内容は保持せず、ディスクにも一切記録しません。
4. **Keep the audio callback cheap（オーディオスレッドの軽量化）**: 音声生成コールバック内で重い処理は行わず、`prepare()` や専用のバックグラウンドスレッドで処理します。

## Ideas / 歓迎するコントリビューション

- 新しい鉄道路線（`demon/lines.py` への追加）
- 新しい環境音サウンド（雨音、焚き火、静かな喫茶店など）
- macOS / Linux での動作確認・フィードバック
- ドキュメントの改善やバグ修正

PR を作成される前に、`sound-siki train --render out.wav --seconds 60` で正常に書き出しが行えるかご確認ください。皆さまからのコントリビューションを心よりお待ちしております！

