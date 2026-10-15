import os
from PIL import Image, ImageDraw, ImageFont

FONT_EN = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 14)
FONT_JP = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 13)
FONT_SYM = ImageFont.truetype("C:/Windows/Fonts/seguisym.ttf", 13)

FONT_TITLE_EN = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 12)
FONT_TITLE_JP = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 11)

FONT_UI_EN = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 12)
FONT_UI_JP = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 11)
FONT_UI_SYM = ImageFont.truetype("C:/Windows/Fonts/seguisym.ttf", 12)


def draw_smart_text(draw, x, y, text, color, font_en=FONT_EN, font_jp=FONT_JP, font_sym=FONT_SYM):
    """Draws mixed text (English, Japanese, and Unicode symbols/arrows) seamlessly."""
    cur_x = x
    for ch in text:
        code = ord(ch)
        if 0x2190 <= code <= 0x2bff or code in (0x25b6, 0x25cf, 0x2500, 0x2502):  # symbols, arrows, play
            f = font_sym
        elif code > 127:
            f = font_jp
        else:
            f = font_en
        draw.text((cur_x, y), ch, font=f, fill=color)
        cur_x += int(f.getlength(ch))
    return cur_x


def measure_smart_text(text, font_en=FONT_EN, font_jp=FONT_JP, font_sym=FONT_SYM):
    total = 0
    for ch in text:
        code = ord(ch)
        if 0x2190 <= code <= 0x2bff or code in (0x25b6, 0x25cf, 0x2500, 0x2502):
            f = font_sym
        elif code > 127:
            f = font_jp
        else:
            f = font_en
        total += int(f.getlength(ch))
    return total


def make_terminal_frame(lines, status_line=None, width=920, height=600):
    img = Image.new("RGB", (width, height), color="#13141f")
    draw = ImageDraw.Draw(img)

    pad_x, pad_y = 16, 16
    win_w = width - pad_x * 2
    win_h = height - pad_y * 2
    corner_r = 10

    # Window body
    draw.rounded_rectangle(
        [pad_x, pad_y, pad_x + win_w, pad_y + win_h],
        radius=corner_r,
        fill="#1e1e2e",
        outline="#313244",
        width=1
    )

    # Title bar
    title_bar_h = 36
    draw.rounded_rectangle(
        [pad_x, pad_y, pad_x + win_w, pad_y + title_bar_h + 10],
        radius=corner_r,
        fill="#181825"
    )
    draw.rectangle(
        [pad_x, pad_y + 12, pad_x + win_w, pad_y + title_bar_h],
        fill="#181825"
    )
    draw.line(
        [(pad_x, pad_y + title_bar_h), (pad_x + win_w, pad_y + title_bar_h)],
        fill="#313244",
        width=1
    )

    # Window control buttons
    btn_y = pad_y + title_bar_h // 2
    buttons = [
        (pad_x + 18, "#f38ba8"),
        (pad_x + 36, "#f9e2af"),
        (pad_x + 54, "#a6e3a1"),
    ]
    for bx, color in buttons:
        draw.ellipse([bx - 6, btn_y - 6, bx + 6, btn_y + 6], fill=color)

    title_text = "sound-siki — bash — 80×24"
    tw = measure_smart_text(title_text, FONT_TITLE_EN, FONT_TITLE_JP, FONT_TITLE_EN)
    draw_smart_text(draw, pad_x + (win_w - tw) // 2, btn_y - 7, title_text, "#a6adc8", FONT_TITLE_EN, FONT_TITLE_JP)

    # Content
    content_x = pad_x + 22
    content_y = pad_y + title_bar_h + 14
    line_h = 22

    cur_y = content_y
    for line in lines:
        cur_x = content_x
        for text, color in line:
            cur_x = draw_smart_text(draw, cur_x, cur_y, text, color)
        cur_y += line_h

    # Status line
    if status_line:
        status_y = pad_y + win_h - 34
        draw.rounded_rectangle(
            [pad_x + 12, status_y - 4, pad_x + win_w - 12, status_y + 24],
            radius=4,
            fill="#262738",
            outline="#45475a",
            width=1
        )
        cur_x = content_x
        for text, color in status_line:
            cur_x = draw_smart_text(draw, cur_x, status_y, text, color)

    return img


def build_demos():
    C_PROMPT = "#89b4fa"
    C_CMD = "#a6e3a1"
    C_TEXT = "#cdd6f4"
    C_DIM = "#6c7086"
    C_ACCENT = "#f9e2af"
    C_ORANGE = "#fab387"
    C_PINK = "#f38ba8"
    C_CYAN = "#94e2d5"
    C_GREEN = "#a6e3a1"

    prompt = [("$ ", C_PROMPT)]
    cmd_text = "sound-siki train cicada"

    frames = []
    durations = []

    # 1. Typing command
    for i in range(0, len(cmd_text) + 1, 4):
        f_lines = [
            prompt + [(cmd_text[:i] + ("▋" if i < len(cmd_text) else ""), C_CMD)]
        ]
        frames.append(make_terminal_frame(f_lines))
        durations.append(100)

    frames.append(make_terminal_frame([prompt + [(cmd_text, C_CMD)]]))
    durations.append(400)

    # 2. Banner and interactive line picker
    banner_lines = [
        prompt + [(cmd_text, C_CMD)],
        [("sound-siki 0.1.0 - タイピングのリズムに寄り添う環境音ジェネレーター", C_ORANGE)],
        [],
        [("  どの路線に乗りますか", C_TEXT)],
        [("    1  山手線        内回り／外回り    30駅  34.5km   地上・周回。ジョイントが主役。", C_DIM)],
        [("    2  中央線快速      下り／上り        24駅  53.1km   地上・高速。駅間が長い。", C_DIM)],
        [("    3  副都心線       渋谷方面／和光市方面  16駅  20.2km   地下・全駅ホームドア。", C_ACCENT)],
    ]
    frames.append(make_terminal_frame(banner_lines + [[("    > ▋", C_TEXT)]]))
    durations.append(600)

    frames.append(make_terminal_frame(banner_lines + [[("    > 3", C_ACCENT)]]))
    durations.append(400)

    # 3. Setup selections
    config_lines = banner_lines + [
        [("    > 3", C_ACCENT)],
        [],
        [("  副都心線 - 向きは: 1 渋谷方面 (和光市 → 渋谷)", C_TEXT)],
        [("  種別は: 2 急行 (4駅停車)", C_TEXT)],
        [("  出発駅: 1 小竹向原  →  目的駅: 4 渋谷", C_TEXT)],
        [],
        [("── 副都心線 急行 ／ 小竹向原 → 渋谷 ／ 4駅 11.9km ／ 目安 15分 ──", C_CYAN)],
    ]
    frames.append(make_terminal_frame(config_lines))
    durations.append(800)

    # 4. Engine start logs
    start_lines = config_lines + [
        [],
        [("  車内放送: ", C_DIM), ("VOICEVOX:ずんだもん（ノーマル）", C_PINK)],
        [("  電車サウンドを開始しました - 路線と行き先を選んで乗る電車の旅。", C_CYAN)],
        [("  蝉サウンドを開始しました - 集中が続くほど心地よく広がる蝉時雨。", C_ACCENT)],
        [("  打鍵は「速さ・間・訂正」のリズムだけを受け取ります。文字や内容は一切記録しません。", C_DIM)],
        [("  タイピングのリズムが電車の動力になります。手を止めると惰行し、やがて停車します。", C_DIM)],
        [("  Ctrl+C で終了", C_DIM)],
    ]
    frames.append(make_terminal_frame(start_lines))
    durations.append(1000)

    # 5. Live train run
    run_base = [
        [("── 副都心線 急行 ／ 小竹向原 → 渋谷 ／ 4駅 11.9km ／ 目安 15分 ──", C_CYAN)],
        [("  車内放送: VOICEVOX:ずんだもん（ノーマル）", C_DIM)],
        [("  電車サウンド・蝉サウンド再生中", C_DIM)],
        [],
        [("♪ [車内チャイム (C5-E5-G5-C6)]", C_ORANGE)],
        [("「まもなく、小竹向原、小竹向原です。お出口は、左側です。」", C_PINK)],
    ]

    stages = [
        ("|", 3.2, "[##........]", 24, "池袋", 3.8, 2, 300),
        ("/", 4.5, "[####......]", 45, "池袋", 3.4, 3, 300),
        ("-", 6.2, "[######....]", 68, "池袋", 2.8, 4, 300),
        ("\\", 7.8, "[########..]", 82, "池袋", 2.1, 5, 350),
        ("|", 8.4, "[#########.]", 86, "池袋", 1.5, 6, 350),
        ("/", 8.0, "[#########.]", 88, "池袋", 1.0, 6, 400),
    ]

    for spin, kps, bar, kmh, nxt, dist, cic, dur in stages:
        st_line = [
            (f"{spin}  {kps:4.1f} keys/s  ", C_ACCENT),
            (f"電車: 巡航 {bar} {kmh:2d}km/h  ", C_CMD),
            (f"次: {nxt} (残り {dist:.1f}km)  ", C_TEXT),
            (f"蝉: {cic}匹", C_CYAN),
        ]
        frames.append(make_terminal_frame(run_base, st_line))
        durations.append(dur)

    # Approach Ikebukuro
    run_approach = run_base + [
        [],
        [("♪ [車内チャイム]", C_ORANGE)],
        [("「まもなく、池袋、池袋です。JR線、東武東上線、西武線はお乗り換えです。」", C_PINK)],
    ]

    decel_stages = [
        ("-", 5.0, "[######....]", 65, "池袋", 0.6, 5, 350),
        ("\\", 3.1, "[####......]", 42, "池袋", 0.3, 4, 350),
        ("|", 1.0, "[##........]", 18, "池袋", 0.1, 3, 350),
        ("-", 0.0, "[..........]",  0, "池袋", 0.0, 2, 1200),
    ]

    for spin, kps, bar, kmh, nxt, dist, cic, dur in decel_stages:
        status_desc = "停車中 (ドア開)" if kmh == 0 else "減速中"
        color = C_ORANGE if kmh == 0 else C_CMD
        st_line = [
            (f"{spin}  {kps:4.1f} keys/s  ", C_ACCENT),
            (f"電車: {status_desc} {bar} {kmh:2d}km/h  ", color),
            (f"池袋停車中 (乗り換え案内中)  " if kmh == 0 else f"次: {nxt} (残り {dist:.1f}km)  ", C_TEXT),
            (f"蝉: {cic}匹", C_CYAN),
        ]
        frames.append(make_terminal_frame(run_approach, st_line))
        durations.append(dur)

    # Depart Ikebukuro
    run_depart = run_approach + [
        [],
        [("「発車ベル♪ ドアが閉まります。次は、新宿三丁目、新宿三丁目です。」", C_PINK)],
    ]
    resume_stages = [
        ("/", 5.8, "[###.......]", 28, "新宿三丁目", 3.5, 3, 350),
        ("-", 7.5, "[######....]", 62, "新宿三丁目", 2.9, 4, 400),
        ("\\", 8.2, "[########..]", 84, "新宿三丁目", 2.2, 5, 800),
    ]
    for spin, kps, bar, kmh, nxt, dist, cic, dur in resume_stages:
        st_line = [
            (f"{spin}  {kps:4.1f} keys/s  ", C_ACCENT),
            (f"電車: 加速中 {bar} {kmh:2d}km/h  ", C_CMD),
            (f"次: {nxt} (残り {dist:.1f}km)  ", C_TEXT),
            (f"蝉: {cic}匹", C_CYAN),
        ]
        frames.append(make_terminal_frame(run_depart, st_line))
        durations.append(dur)

    # Save animated GIF
    out_gif = "assets/demo.gif"
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True
    )
    print("demo.gif created! Size:", os.path.getsize(out_gif))

    # Build rich showcase screenshot for demo_terminal.png
    showcase_lines = [
        prompt + [("sound-siki train cicada", C_CMD)],
        [("sound-siki 0.1.0 - タイピングのリズムに寄り添う環境音ジェネレーター", C_ORANGE)],
        [],
        [("── 副都心線 急行 ／ 小竹向原 → 渋谷 ／ 4駅 11.9km ／ 目安 15分 ──", C_CYAN)],
        [],
        [("  車内放送: ", C_DIM), ("VOICEVOX:ずんだもん（ノーマル）", C_PINK)],
        [("  電車サウンドを開始しました - 路線と行き先を選んで乗る電車の旅。", C_CYAN)],
        [("  蝉サウンドを開始しました - 集中が続くほど心地よく広がる蝉時雨。", C_ACCENT)],
        [("  打鍵は「速さ・間・訂正」のリズムだけを受け取ります。文字や内容は一切記録しません。", C_DIM)],
        [],
        [("♪ [車内チャイム (C5-E5-G5-C6)]", C_ORANGE)],
        [("「まもなく、小竹向原、小竹向原です。お出口は、左側です。」", C_PINK)],
        [],
        [("♪ [車内チャイム]", C_ORANGE)],
        [("「まもなく、池袋、池袋です。JR線、東武東上線、西武線はお乗り換えです。」", C_PINK)],
        [],
        [("「発車ベル♪ ドアが閉まります。次は、新宿三丁目、新宿三丁目です。」", C_PINK)],
    ]
    showcase_status = [
        ("\\  7.8 keys/s  ", C_ACCENT),
        ("電車: 巡航 [########..] 82km/h  ", C_GREEN),
        ("次: 新宿三丁目 (残り 2.9km)  ", C_TEXT),
        ("蝉: 5匹", C_CYAN),
    ]
    terminal_png = make_terminal_frame(showcase_lines, showcase_status)
    terminal_png.save("assets/demo_terminal.png")
    print("demo_terminal.png created!")


def build_vscode_demo():
    width, height = 1000, 620
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)

    # Activity Bar (Left, 48px wide)
    act_w = 48
    draw.rectangle([0, 0, act_w, height], fill="#181825")
    # Clean VS Code-like box/list icons
    for i in range(5):
        iy = 16 + i * 44
        if i == 0:
            draw.rectangle([0, iy, 2, iy + 24], fill="#cdd6f4")
            draw.rectangle([16, iy + 4, 32, iy + 20], outline="#cdd6f4", width=1)
            draw.line([(20, iy + 8), (28, iy + 8)], fill="#cdd6f4", width=1)
            draw.line([(20, iy + 12), (28, iy + 12)], fill="#cdd6f4", width=1)
            draw.line([(20, iy + 16), (25, iy + 16)], fill="#cdd6f4", width=1)
        else:
            draw.rectangle([16, iy + 4, 32, iy + 20], outline="#45475a", width=1)

    # Sidebar (Explorer, 190px wide)
    side_w = 190
    draw.rectangle([act_w, 0, act_w + side_w, height - 24], fill="#1e1e2e")
    draw.line([(act_w + side_w, 0), (act_w + side_w, height - 24)], fill="#313244", width=1)

    draw_smart_text(draw, act_w + 16, 14, "EXPLORER: SOUND-SIKI", "#a6adc8", FONT_UI_EN, FONT_UI_JP)
    files = [
        ("v sound-siki", "#cdd6f4"),
        ("  > demon", "#a6adc8"),
        ("  > vscode", "#a6adc8"),
        ("    main.py", "#89b4fa"),
        ("    lines.py", "#a6adc8"),
        ("    route.py", "#a6adc8"),
        ("    README.md", "#fab387"),
        ("    pyproject.toml", "#a6adc8"),
    ]
    for i, (fn, col) in enumerate(files):
        draw_smart_text(draw, act_w + 14, 42 + i * 22, fn, col, FONT_UI_EN, FONT_UI_JP, FONT_UI_SYM)

    # Editor Area
    edit_x = act_w + side_w

    # Tab bar
    draw.rectangle([edit_x, 0, width, 34], fill="#181825")
    draw.rectangle([edit_x, 0, edit_x + 130, 34], fill="#1e1e2e")
    draw.line([(edit_x, 0), (edit_x + 130, 0)], fill="#89b4fa", width=2)
    draw_smart_text(draw, edit_x + 16, 10, "main.py", "#cdd6f4", FONT_UI_EN, FONT_UI_JP)
    draw_smart_text(draw, edit_x + 108, 10, "x", "#6c7086", FONT_UI_EN, FONT_UI_JP)

    # Python code
    code_lines = [
        [("import", "#cba6f7"), (" numpy ", "#cdd6f4"), ("as", "#cba6f7"), (" np", "#cdd6f4")],
        [("from", "#cba6f7"), (" .engine ", "#cdd6f4"), ("import", "#cba6f7"), (" Engine", "#89b4fa")],
        [],
        [("# タイピングのリズムを受け取って、電車の走行音をリアルタイム合成", "#6c7086")],
        [("def", "#cba6f7"), (" run_journey", "#89b4fa"), ("(line_name: ", "#cdd6f4"), ("str", "#f9e2af"), (", destination: ", "#cdd6f4"), ("str", "#f9e2af"), ("):", "#cdd6f4")],
        [("    print", "#89dceb"), ("(f", "#a6e3a1"), ("\"乗車中: {line_name} -> {destination}\"", "#a6e3a1"), (")", "#cdd6f4")],
        [("    engine = Engine(sounds=[", "#cdd6f4"), ("\"train\"", "#a6e3a1"), (", ", "#cdd6f4"), ("\"cicada\"", "#a6e3a1"), ("])", "#cdd6f4")],
        [("    engine.start()", "#cdd6f4")],
        [],
        [("    ", "#cdd6f4"), ("# キーボードの入力速度とテンポから電車の加減速を自然に制御", "#6c7086")],
        [("    ", "#cdd6f4"), ("while", "#cba6f7"), (" engine.is_running():", "#cdd6f4")],
        [("        speed = engine.current_speed()", "#cdd6f4")],
        [("        next_station = engine.next_stop()", "#cdd6f4")],
        [("        time.sleep(", "#cdd6f4"), ("0.1", "#fab387"), (")", "#cdd6f4")],
    ]

    code_y = 48
    line_h = 22
    for i, line in enumerate(code_lines):
        draw_smart_text(draw, edit_x + 12, code_y, f"{i+1:2d}", "#45475a")
        cx = edit_x + 44
        for token, col in line:
            cx = draw_smart_text(draw, cx, code_y, token, col)
        code_y += line_h

    # Output panel at bottom of editor
    panel_y = height - 24 - 170
    draw.rectangle([edit_x, panel_y, width, height - 24], fill="#181825")
    draw.line([(edit_x, panel_y), (width, panel_y)], fill="#313244", width=1)

    draw_smart_text(draw, edit_x + 16, panel_y + 10, "PROBLEMS", "#6c7086", FONT_UI_EN, FONT_UI_JP)
    draw_smart_text(draw, edit_x + 90, panel_y + 10, "OUTPUT: sound-siki", "#89b4fa", FONT_UI_EN, FONT_UI_JP)
    draw.line([(edit_x + 90, panel_y + 26), (edit_x + 225, panel_y + 26)], fill="#89b4fa", width=2)
    draw_smart_text(draw, edit_x + 245, panel_y + 10, "TERMINAL", "#6c7086", FONT_UI_EN, FONT_UI_JP)

    panel_lines = [
        (" [sound-siki] 車内放送: VOICEVOX:ずんだもん（ノーマル）", "#a6adc8"),
        (" [sound-siki] ♪ [車内チャイム (C5-E5-G5-C6)]", "#fab387"),
        (" [sound-siki] 「まもなく、池袋、池袋です。お出口は右側です。」", "#f38ba8"),
        (" [sound-siki]   JR線、東武東上線、西武池袋線はお乗り換えです。", "#f38ba8"),
        (" [sound-siki]   池袋停車中（ドア開）。タイピングを再開すると発車します。", "#a6e3a1"),
    ]
    for i, (txt, col) in enumerate(panel_lines):
        draw_smart_text(draw, edit_x + 14, panel_y + 36 + i * 22, txt, col)

    # Status Bar (Bottom 24px)
    sb_y = height - 24
    draw.rectangle([0, sb_y, width, height], fill="#11111b")
    draw.line([(0, sb_y), (width, sb_y)], fill="#313244", width=1)

    sb_left = [
        (" main ", "#89b4fa"),
        (" | > sound-siki: 池袋 82km/h (次: 1.2km) ", "#a6e3a1"),
        (" | Vol 65% ", "#f9e2af"),
        (" | editor ", "#cdd6f4"),
        (" | ずんだもん ", "#f38ba8"),
    ]
    cur_x = 10
    for txt, col in sb_left:
        cur_x = draw_smart_text(draw, cur_x, sb_y + 4, txt, col, FONT_UI_EN, FONT_UI_JP, FONT_UI_SYM)

    sb_right = "Ln 12, Col 24  Spaces: 4  UTF-8  Python 3.11  "
    rw = measure_smart_text(sb_right, FONT_UI_EN, FONT_UI_JP, FONT_UI_SYM)
    draw_smart_text(draw, width - rw - 10, sb_y + 4, sb_right, "#6c7086", FONT_UI_EN, FONT_UI_JP, FONT_UI_SYM)

    img.save("assets/demo_vscode.png")
    print("demo_vscode.png created!")


if __name__ == "__main__":
    build_demos()
    build_vscode_demo()
