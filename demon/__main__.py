"""CLI for the typing demon.

    python -m demon                     # 電車デーモン
    python -m demon train cicada        # both at once
    python -m demon cicada --volume 0.5
    python -m demon --list
    python -m demon --devices
    python -m demon train --demo        # no keyboard hook, scripted typist
    python -m demon train --render out.wav --seconds 60
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import numpy as np

from . import __version__
from .demons import REGISTRY
from .engine import Engine
from .keywatch import KeyWatcher, ScriptedTypist

BANNER = "demon %s - 打鍵を餌にする環境音デーモン" % __version__


def _utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def build_args():
    p = argparse.ArgumentParser(prog="demon", description=BANNER)
    p.add_argument("demons", nargs="*", default=None,
                   help="どのデーモンを起こすか (既定: train)")
    p.add_argument("--list", action="store_true", help="デーモン一覧")
    p.add_argument("--devices", action="store_true", help="音声出力デバイス一覧")
    p.add_argument("--device", default=None, help="出力デバイス番号または名前")
    p.add_argument("--volume", type=float, default=0.7, help="音量 0..1 (既定 0.7)")
    p.add_argument("--rate", type=int, default=44100, help="サンプリング周波数")
    p.add_argument("--block", type=int, default=2048,
                   help="ブロックサイズ (大きいほど軽い / 既定 2048 = 約46ms)")
    p.add_argument("--seed", type=int, default=None, help="音色生成のシード")
    p.add_argument("--demo", action="store_true",
                   help="キーボードを監視せず、台本どおりの仮想タイピングで鳴らす")
    p.add_argument("--render", metavar="WAV", default=None,
                   help="リアルタイム再生せずWAVに書き出す (--demo と同じ仮想入力)")
    p.add_argument("--seconds", type=float, default=60.0, help="--render の長さ")
    p.add_argument("--quiet", action="store_true", help="ステータス表示を出さない")
    return p


def list_demons():
    print(BANNER)
    print()
    for name, cls in REGISTRY.items():
        print("  %-8s %s" % (name, cls.title))
        print("           %s" % cls.blurb)
    print()
    print("  例: python -m demon train cicada")


def list_devices():
    import sounddevice as sd
    print("出力デバイス:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            api = sd.query_hostapis(d["hostapi"])["name"]
            print("  %3d  %-42s  %s" % (i, d["name"][:42], api))


def make_demons(names, sr, seed):
    rng = np.random.default_rng(seed)
    demons = []
    for name in names:
        if name not in REGISTRY:
            raise SystemExit("知らないデーモンです: %s  (--list で一覧)" % name)
        d = REGISTRY[name](sr, rng)
        d.prepare()
        demons.append(d)
    return demons


def status_loop(engine, stop_event):
    """Redraw a one-line status until asked to stop."""
    spinner = "|/-\\"
    i = 0
    width = 60
    while not stop_event.is_set():
        r = engine.rhythm
        parts = ["%s %4.1f keys/s" % (spinner[i % 4], r.kps)]
        parts += [d.status() for d in engine.demons]
        line = "  ".join(p for p in parts if p)[:120]
        # Padded rather than ANSI-erased, so this still looks right in the old
        # console host as well as in Windows Terminal.
        sys.stdout.write("\r" + line.ljust(width))
        width = max(len(line), 40)
        sys.stdout.flush()
        i += 1
        stop_event.wait(0.12)
    sys.stdout.write("\r" + " " * width + "\r")
    sys.stdout.flush()


def parse_device(spec):
    if spec is None:
        return None
    try:
        return int(spec)
    except ValueError:
        return spec


def main(argv=None):
    _utf8_stdout()
    args = build_args().parse_args(argv)

    if args.list:
        list_demons()
        return 0
    if args.devices:
        list_devices()
        return 0

    names = args.demons or ["train"]
    demons = make_demons(names, args.rate, args.seed)

    if args.render:
        source = ScriptedTypist(np.random.default_rng(args.seed))
        engine = Engine(demons, source, sr=args.rate, block=args.block, volume=args.volume)
        print(BANNER)
        print("書き出し中: %s (%.0f 秒, %s)" % (args.render, args.seconds, "+".join(names)))
        audio = engine.render_wav(args.render, args.seconds,
                                  progress=lambda s: print("  %5.1f s" % s))
        rms = float(np.sqrt(np.mean(audio ** 2)))
        print("完了  peak=%.3f  rms=%.3f" % (float(np.max(np.abs(audio))), rms))
        return 0

    if args.demo:
        source = ScriptedTypist(np.random.default_rng(args.seed))
        watcher = None
    else:
        watcher = KeyWatcher()
        source = watcher

    engine = Engine(demons, source, sr=args.rate, block=args.block, volume=args.volume)

    print(BANNER)
    for d in demons:
        print("  %s を起こしました - %s" % (d.title, d.blurb))
    if watcher is not None:
        print("  打鍵は「速さ・間・訂正」だけを見ます。文字は一切記録しません。")
    else:
        print("  デモモード: キーボードは監視せず、台本どおりに打鍵を再現します。")
    print("  Ctrl+C で終了")
    print()

    if watcher is not None:
        watcher.start()

    stop_event = threading.Event()
    status = None
    try:
        with engine.stream(device=parse_device(args.device)):
            if not args.quiet:
                status = threading.Thread(target=status_loop, args=(engine, stop_event),
                                          daemon=True)
                status.start()
            try:
                while True:
                    time.sleep(0.2)
                    if engine.error is not None:
                        raise engine.error
            except KeyboardInterrupt:
                engine.fade_out()          # ride the fade out rather than clicking
                deadline = time.time() + 2.0
                while not engine.faded_out and time.time() < deadline:
                    time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if status is not None:
            status.join(timeout=1.0)
        if watcher is not None:
            watcher.stop()

    print("デーモンは眠りました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
