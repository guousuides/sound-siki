"""CLI for the typing demon.

    python -m demon                            # 路線を選んで乗る
    python -m demon train cicada               # 電車 + 蝉
    python -m demon --line chuo --from 東京 --to 高尾    # 選択を飛ばす
    python -m demon --lines                    # 路線一覧
    python -m demon --list                     # デーモン一覧
    python -m demon train --demo               # 監視せず台本どおりに鳴らす
    python -m demon train --render out.wav --seconds 60
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import numpy as np

from . import __version__, journey, picker
from .demons import REGISTRY
from .engine import Engine
from .keywatch import KeyWatcher, ScriptedTypist
from .lines import LINES, ORDER
from .route import DONE

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
    p.add_argument("--lines", action="store_true", help="路線一覧")
    p.add_argument("--devices", action="store_true", help="音声出力デバイス一覧")
    p.add_argument("--device", default=None, help="出力デバイス番号または名前")
    p.add_argument("--volume", type=float, default=0.65, help="音量 0..1 (既定 0.65)")
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
    # 乗車 - giving all of these skips the picker, for scripts and for habit.
    p.add_argument("--line", default=None, help="路線 (%s)" % "/".join(ORDER))
    p.add_argument("--from", dest="origin", default=None, help="出発駅")
    p.add_argument("--to", dest="dest", default=None, help="目的駅")
    p.add_argument("--kind", default=None, help="種別 (既定: その路線の先頭)")
    p.add_argument("--reverse", action="store_true", help="逆向き（上り/外回り）")
    p.add_argument("--fresh", action="store_true", help="前回の続きを無視して乗り直す")
    p.add_argument("--sounds", metavar="DIR", default=None,
                   help="持ち込みの環境音WAVを置くフォルダ (既定: ~/.demon/sounds)")
    p.add_argument("--no-exit", dest="no_exit", action="store_true",
                   help="終点に着いても終了せず、ホームで鳴り続ける")
    return p


def list_demons():
    print(BANNER)
    print()
    for name, cls in REGISTRY.items():
        print("  %-8s %s" % (name, cls.title))
        print("           %s" % cls.blurb)
    print()
    print("  例: python -m demon train cicada")


def list_lines():
    print(BANNER)
    print()
    for key in ORDER:
        l = LINES[key]
        print("  %-11s %-10s %2d駅 %5.1fkm  %s／%s  最高%.0fkm/h  %s" % (
            key, l.name, len(l.stations), l.total_km,
            l.dir_names[0], l.dir_names[1], l.max_speed * 3.6, l.note))
        print("             種別: %s" % "／".join(k.name for k in l.kinds))
        print("             %s" % " ".join(s.name for s in l.stations))
    print()
    print("  例: python -m demon --line fukutoshin --from 小竹向原 --to 渋谷 --kind 急行")


def list_devices():
    import sounddevice as sd
    print("出力デバイス:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            api = sd.query_hostapis(d["hostapi"])["name"]
            print("  %3d  %-42s  %s" % (i, d["name"][:42], api))


def make_demons(names, sr, seed):
    """Construct, but do not prepare - the train needs its route first."""
    rng = np.random.default_rng(seed)
    demons = []
    for name in names:
        if name not in REGISTRY:
            raise SystemExit("知らないデーモンです: %s  (--list で一覧)" % name)
        demons.append(REGISTRY[name](sr, rng))
    return demons


def plan_from_args(args):
    """A fully specified journey, or None if the picker should run."""
    if not (args.line and args.origin and args.dest):
        return None
    if args.line not in LINES:
        raise SystemExit("知らない路線です: %s  (--lines で一覧)" % args.line)
    line = LINES[args.line]
    try:
        origin, dest = line.index(args.origin), line.index(args.dest)
    except KeyError as exc:
        raise SystemExit("%s に %s という駅はありません" % (line.name, exc.args[0]))
    kind = line.kinds[0]
    if args.kind:
        kind = next((k for k in line.kinds if k.name == args.kind), None)
        if kind is None:
            raise SystemExit("%s の種別は %s のいずれかです"
                             % (line.name, "／".join(k.name for k in line.kinds)))
    direction = -1 if args.reverse else 1
    if not line.is_loop and not args.reverse and dest < origin:
        direction = -1                       # 上りだと言わなくても分かる
    return line.plan(direction, origin, dest, kind)


def status_loop(engine, stop_event):
    """One live line, with the announcements scrolling past above it."""
    spinner = "|/-\\"
    i = 0
    width = 60

    def clear():
        sys.stdout.write("\r" + " " * width + "\r")

    while not stop_event.is_set():
        for d in engine.demons:
            while d.log:
                clear()
                sys.stdout.write(d.log.popleft() + "\n")
        r = engine.rhythm
        parts = ["%s %4.1f keys/s" % (spinner[i % 4], r.kps)]
        parts += [d.status() for d in engine.demons]
        line = "  ".join(p for p in parts if p)[:150]
        sys.stdout.write("\r" + line.ljust(width))
        width = max(len(line), 40)
        sys.stdout.flush()
        i += 1
        stop_event.wait(0.12)
    clear()
    for d in engine.demons:
        while d.log:
            sys.stdout.write(d.log.popleft() + "\n")
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
    if args.lines:
        list_lines()
        return 0
    if args.devices:
        list_devices()
        return 0

    names = args.demons or ["train"]
    demons = make_demons(names, args.rate, args.seed)
    train = next((d for d in demons if d.name == "train"), None)
    headless = bool(args.render or args.demo)
    sessions, start_x = 1, 0.0

    print(BANNER)
    print()
    if train is not None and not headless:
        # 乗車. Every run, unless the whole journey is on the command line.
        plan = plan_from_args(args)
        if plan is None:
            picked = picker.pick(resume_ok=not args.fresh)
            if picked is None:
                print("乗車をとりやめました。")
                return 0
            plan, start_x, elapsed, sessions = picked
            train.board(plan, start_x, elapsed)
        else:
            train.board(plan)
        print(picker.describe(plan, start_x))
        print()

    if train is not None:
        train.sounds_dir = args.sounds
    for d in demons:
        d.prepare()
    if train is not None and train.field:
        print("  持ち込みの環境音: %s" % "、".join(sorted(train.field)))

    if headless:
        source = ScriptedTypist(np.random.default_rng(args.seed))
        watcher = None
    else:
        watcher = KeyWatcher()
        source = watcher

    engine = Engine(demons, source, sr=args.rate, block=args.block,
                    volume=args.volume)

    if args.render:
        print("書き出し中: %s (%.0f 秒, %s)" % (args.render, args.seconds,
                                          "+".join(names)))
        audio = engine.render_wav(args.render, args.seconds,
                                  progress=lambda s: print("  %5.1f s" % s))
        rms = float(np.sqrt(np.mean(audio ** 2)))
        print("完了  peak=%.3f  rms=%.3f" % (float(np.max(np.abs(audio))), rms))
        return 0

    for d in demons:
        print("  %s を起こしました - %s" % (d.title, d.blurb))
    if watcher is not None:
        print("  打鍵は「速さ・間・訂正」だけを見ます。文字は一切記録しません。")
    else:
        print("  デモモード: キーボードは監視せず、台本どおりに打鍵を再現します。")
    if train is not None and not headless:
        print("  打鍵が主幹制御器です。手を止めると惰行し、やがて停まります。")
    print("  Ctrl+C で終了")
    print()

    if watcher is not None:
        watcher.start()

    stop_event = threading.Event()
    status = None
    arrived = False
    try:
        with engine.stream(device=parse_device(args.device)):
            if not args.quiet:
                status = threading.Thread(target=status_loop,
                                          args=(engine, stop_event), daemon=True)
                status.start()
            try:
                while True:
                    time.sleep(0.2)
                    if engine.error is not None:
                        raise engine.error
                    if train is not None and train.finished and not args.no_exit:
                        arrived = True
                        break
            except KeyboardInterrupt:
                pass
            engine.fade_out()              # ride the fade out rather than clicking
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

    # Park the train, or tear up the ticket. Position and time, nothing else.
    if train is not None and train.run is not None and not headless:
        if train.run.phase == DONE or arrived:
            journey.clear()
        else:
            journey.save(train.plan, train.run.x, train.run.elapsed, sessions)
            left = (train.plan.length - train.run.x) / 1000.0
            print("%s まで残り %.1f km。続きは次回。" % (train.plan.dest.name, left))

    print("デーモンは眠りました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
