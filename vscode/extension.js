// demon for VS Code - feeds the editor's typing rhythm to the Python daemon.
//
// The daemon itself is unchanged: it runs as a child process with `--ipc`, and
// this side sends it one letter per edit (c/s/b/e). Only the category of the
// edit crosses the pipe - never the text - so the privacy rule from
// keywatch.py holds here too.
"use strict";

const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const path = require("path");

const IS_WIN = process.platform === "win32";
const TYPED_SCHEMES = new Set(["file", "untitled", "vscode-notebook-cell", "vscode-userdata", "vscode-remote"]);
const DEPS =["numpy>=1.24", "sounddevice>=0.4.6"];

let ctx;
let out;
let bar;
let keyBar;
let mixBar;
let proc = null;
let lastStatus = "";

function cfg() {
  return vscode.workspace.getConfiguration("demon");
}

// ------------------------------------------------------------------ python
function pythonRoot() {
  // Bundled copy in a packaged .vsix, the repo itself while developing.
  const bundled = path.join(ctx.extensionPath, "python");
  return fs.existsSync(path.join(bundled, "demon")) ? bundled : path.resolve(ctx.extensionPath, "..");
}

function venvDir() {
  return path.join(ctx.globalStorageUri.fsPath, "venv");
}

function venvPython() {
  return IS_WIN ? path.join(venvDir(), "Scripts", "python.exe") : path.join(venvDir(), "bin", "python");
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const p = cp.spawn(cmd, args, { windowsHide: true, ...opts });
    let stdout = "";
    let stderr = "";
    p.stdout.on("data", (d) => { stdout += d; if (opts.log) out.append(d.toString()); });
    p.stderr.on("data", (d) => { stderr += d; if (opts.log) out.append(d.toString()); });
    p.on("error", reject);
    p.on("close", (code) => (code === 0 ? resolve(stdout) : reject(new Error(stderr.trim() || `${cmd} exited ${code}`))));
  });
}

async function findBasePython() {
  const custom = cfg().get("pythonPath");
  const candidates = custom ? [[custom, []]]
    : IS_WIN ? [["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3", []], ["python", []]];
  for (const [cmd, pre] of candidates) {
    try {
      const v = await run(cmd, [...pre, "-c", "import sys;print(sys.version_info >= (3, 9))"]);
      if (v.trim() === "True") return [cmd, pre];
    } catch (_) { /* try the next one */ }
  }
  return null;
}

function wantedDeps() {
  return cfg().get("keySource") === "global" ? [...DEPS, "pynput>=1.7.6"] : DEPS;
}

async function ensurePython(force = false) {
  const stamp = path.join(venvDir(), "demon-deps.txt");
  const want = wantedDeps().join("\n");
  if (!force && fs.existsSync(venvPython()) && fs.existsSync(stamp) && fs.readFileSync(stamp, "utf8") === want) {
    return venvPython();
  }
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "demon: Python 環境を準備中" },
    async (progress) => {
      const base = await findBasePython();
      if (!base) {
        const pick = await vscode.window.showErrorMessage(
          "Python 3.9 以上が見つかりません。インストールするか、設定 demon.pythonPath を指定してください。",
          "設定を開く");
        if (pick) vscode.commands.executeCommand("workbench.action.openSettings", "demon.pythonPath");
        return null;
      }
      out.show(true);
      if (force || !fs.existsSync(venvPython())) {
        progress.report({ message: "venv を作成" });
        fs.rmSync(venvDir(), { recursive: true, force: true });
        fs.mkdirSync(ctx.globalStorageUri.fsPath, { recursive: true });
        await run(base[0], [...base[1], "-m", "venv", venvDir()], { log: true });
      }
      progress.report({ message: wantedDeps().join(", ") });
      await run(venvPython(), ["-m", "pip", "install", "--disable-pip-version-check", ...wantedDeps()], { log: true });
      fs.writeFileSync(stamp, want);
      return venvPython();
    });
}

function pyEnv() {
  return { ...process.env, PYTHONPATH: pythonRoot(), PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" };
}

// ----------------------------------------------------------------- boarding
async function quick(items, placeHolder) {
  const pick = await vscode.window.showQuickPick(items, { placeHolder, ignoreFocusOut: true });
  return pick ? pick.value : undefined;
}

/** Same questions as picker.py, as QuickPicks. Returns CLI args or undefined. */
async function board(py) {
  const data = JSON.parse(await run(py, ["-m", "demon", "--lines-json"], { env: pyEnv() }));

  if (data.parked) {
    const p = data.parked;
    const go = await quick([
      { label: "続きから", description: `${p.line} ${p.kind}  ${p.origin} → ${p.dest}`,
        detail: `残り ${p.left_km} km ／ ここまで ${p.minutes} 分・${p.sessions} 回`, value: "resume" },
      { label: "新しい旅に出る", value: "new" },
    ], "前回の続きがあります");
    if (!go) return undefined;
    if (go === "resume") return ["--resume"];
  }

  const line = await quick(data.lines.map((l) => ({
    label: l.name, description: `${l.dirs.join("／")}  ${l.stations.length}駅 ${l.km}km`, detail: l.note, value: l,
  })), "どの路線に乗りますか");
  if (!line) return undefined;

  const n = line.stations.length;
  const ends = [line.stations[0], line.stations[n - 1]];
  const direction = await quick(line.dirs.map((d, i) => ({
    label: d, description: line.loop ? "" : i === 0 ? `${ends[0]} → ${ends[1]}` : `${ends[1]} → ${ends[0]}`,
    value: i === 0 ? 1 : -1,
  })), `${line.name} - 向きは`);
  if (!direction) return undefined;

  let kind = line.kinds[0];
  if (line.kinds.length > 1) {
    kind = await quick(line.kinds.map((k) => ({
      label: k.name, description: `${k.stops ? k.stops.length : n}駅に停車`, value: k,
    })), "種別は");
    if (!kind) return undefined;
  }

  const seq = [...Array(n).keys()];
  if (direction < 0) seq.reverse();
  const origin = await quick((line.loop ? seq : seq.slice(0, -1)).map((i) => ({ label: line.stations[i], value: String(i) })), "出発駅");
  if (origin === undefined) return undefined;

  const k = seq.indexOf(Number(origin));
  let after = line.loop ? [...seq.slice(k + 1), ...seq.slice(0, k)] : seq.slice(k + 1);
  const items = after.map((i) => ({ label: line.stations[i], value: String(i) }));
  if (line.loop) items.push({ label: `${line.stations[origin]}（一周）`, value: origin });
  items.reverse();                                  // 既定（いちばん遠く）を先頭に
  const dest = await quick(items, `目的駅  (${line.stations[origin]} 発)`);
  if (dest === undefined) return undefined;

  const args = ["--fresh", "--line", line.key, "--from", line.stations[origin], "--to", line.stations[dest], "--kind", kind.name];
  if (direction < 0) args.push("--reverse");
  return args;
}

// -------------------------------------------------------------- the daemon
function setBar(text, tooltip) {
  bar.text = text;
  bar.tooltip = tooltip || "";
}

async function start(opts = {}) {
  if (proc) {
    vscode.window.showInformationMessage("demon はもう走っています。");
    return;
  }
  let py;
  try {
    py = await ensurePython();
  } catch (e) {
    out.appendLine(String(e.message || e));
    vscode.window.showErrorMessage("demon: Python 環境の準備に失敗しました（出力パネル参照）");
    return;
  }
  if (!py) return;

  const c = cfg();
  const demons = c.get("demons");
  let args = ["-m", "demon", ...demons, "--ipc",
    "--volume", String(c.get("volume")), "--voice", c.get("voice"), "--speaker", String(c.get("speaker")),
    "--announce-volume", String(c.get("announceVolume")),
    "--train-volume", String(c.get("trainVolume")), "--cicada-volume", String(c.get("cicadaVolume"))];
  if (c.get("keySource") === "global") args.push("--global-keys");
  if (c.get("noExit")) args.push("--no-exit");
  if (demons.includes("train")) {
    let boarding;
    try {
      boarding = opts.resume ? ["--resume"] : await board(py);
    } catch (e) {
      out.appendLine(String(e.message || e));
      vscode.window.showErrorMessage("demon: 路線の読み込みに失敗しました（出力パネル参照）");
      return;
    }
    if (!boarding) return;
    args = args.concat(boarding);
  }

  out.appendLine("");
  const child = cp.spawn(py, args, { env: pyEnv(), windowsHide: true });
  proc = child;
  setBar("$(loading~spin) demon", "起動中…");

  let buf = "";
  child.stdout.on("data", (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).replace(/\r$/, "");
      buf = buf.slice(i + 1);
      if (line.startsWith("@status ")) {
        lastStatus = line.slice(8);
        setBar(`$(megaphone) ${shorten(lastStatus)}`, lastStatus + "\n\nクリックで降りる");
      } else {
        out.appendLine(line);
      }
    }
  });
  child.stderr.on("data", (d) => out.append(d.toString()));
  child.on("error", (e) => out.appendLine(String(e)));
  child.on("close", (code) => {
    if (proc === child) proc = null;
    setBar("$(play) demon", "クリックで乗車");
    bar.command = "demon.toggle";
    if (code !== 0 && code !== null) {
      vscode.window.showErrorMessage(`demon が終了しました (code ${code})。出力パネルを見てください。`, "出力を開く")
        .then((p) => p && out.show());
    }
  });
}

function shorten(status) {
  // "1.2 keys/s  電車 ##.. 副都心線 急行  62.0 km/h 力行 次:池袋 残り3.1km/2駅"
  // 打鍵数は常に出す。ホームでは発車まで 20 秒以上かかるので、届いているかが見えないと壊れて見える
  const k = status.match(/^([\d.]+) keys\/s/);
  const keys = k ? `⌨${k[1]} ` : "";
  const m = status.match(/([\d.]+) km\/h\s+(\S+)\s+次:(\S+)\s+残り\s*([\d.]+km)/);
  if (m && m[2] === "停車") return `${keys}停車中（打ち続けると発車） 次:${m[3]}`;
  if (m) return `${keys}${Math.round(Number(m[1]))}km/h ${m[2]} 次:${m[3]} 残り${m[4]}`;
  if (/到着/.test(status)) return "到着";
  return status.replace(/\s+/g, " ").slice(0, 40);
}

function stop() {
  const child = proc;
  if (!child) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(() => { child.kill(); resolve(); }, 5000);
    child.on("close", () => { clearTimeout(timer); resolve(); });
    try { child.stdin.write("q\n"); } catch (_) { child.kill(); }
  });
}

// Reduce an edit to one letter. The text itself never leaves this function.
function onEdit(e) {
  if (!proc || cfg().get("keySource") !== "editor") return;
  // 出力パネルや git など、人が打っていない文書は数えない。undo/redo も打鍵ではない
  if (!TYPED_SCHEMES.has(e.document.uri.scheme) || e.reason !== undefined) return;
  const ch = e.contentChanges[0];                                            // マルチカーソルも 1 打鍵
  if (!ch) return;
  const code = ch.text === "" ? (ch.rangeLength > 0 ? "b" : null)
    : ch.text.includes("\n") ? "e"
    : ch.text === " " ? "s" : "c";
  if (code) proc.stdin.write(code + "\n");
}

// ---------------------------------------------------------------- key source
const KEY_SOURCES = {
  editor: { icon: "$(edit)", label: "エディタだけ", detail: "この IDE のエディタでの入力だけで走る。キーフックなし・権限不要" },
  global: { icon: "$(globe)", label: "PC 全体", detail: "ブラウザやチャットなど、どのアプリで打っても走る（macOS はアクセシビリティ許可が必要）" },
};

function showKeySource() {
  const k = KEY_SOURCES[cfg().get("keySource")] || KEY_SOURCES.editor;
  keyBar.text = k.icon;
  keyBar.tooltip = `demon の打鍵: ${k.label}
クリックで切り替え`;
}

async function pickKeySource() {
  const now = cfg().get("keySource");
  const pick = await quick(Object.entries(KEY_SOURCES).map(([value, k]) => ({
    label: `${k.icon} ${k.label}`, description: value === now ? "使用中" : "", detail: k.detail, value,
  })), "打鍵をどこから拾いますか");
  if (!pick || pick === now) return;
  await cfg().update("keySource", pick, vscode.ConfigurationTarget.Global);
  if (proc) {                       // 走行中なら、いまの位置で降りて同じ電車に乗り直す
    await stop();
    await start({ resume: true });
  }
}

// -------------------------------------------------------------------- mixer
// 走行中でも乗り直さずに効く: 標準入力に "v<チャンネル> <倍率>" を送るだけ
const CHANNELS = [
  { key: "volume", ch: "master", icon: "$(unmute)", label: "全体", max: 1 },
  { key: "trainVolume", ch: "train", icon: "$(rocket)", label: "電車の走行音", max: 2 },
  { key: "cicadaVolume", ch: "cicada", icon: "$(squirrel)", label: "蝉・風鈴", max: 2 },
  { key: "announceVolume", ch: "announce", icon: "$(megaphone)", label: "車内放送", max: 2 },
];

function pct(v) {
  return `${Math.round(v * 100)}%`;
}

function sendVolumes(keys) {
  if (!proc) return;
  for (const c of CHANNELS) {
    if (!keys || keys.includes(c.key)) proc.stdin.write(`v${c.ch} ${cfg().get(c.key)}\n`);
  }
}

function showMixer() {
  const c = cfg();
  mixBar.text = Number(c.get("volume")) === 0 ? "$(mute)" : "$(unmute)";
  mixBar.tooltip = "demon の音量（クリックで調整）\n" + CHANNELS.map((ch) => `${ch.label}: ${pct(c.get(ch.key))}`).join("\n");
}

/** チャンネルを選ぶ → 段階を選ぶ → またチャンネル一覧へ。Esc で閉じる */
async function openMixer() {
  for (;;) {
    const c = cfg();
    const ch = await quick(CHANNELS.map((x) => ({
      label: `${x.icon} ${x.label}`, description: pct(c.get(x.key)), value: x,
    })), "どの音量を変えますか（Esc で閉じる）");
    if (!ch) return;
    const now = Number(c.get(ch.key));
    const steps = ch.max === 1 ? [0, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 1] : [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2];
    const level = await quick(steps.map((v) => ({
      label: `${v === now ? "$(check) " : "      "}${pct(v)}`,
      description: v === 0 ? "消音" : "",
      value: String(v),
    })), `${ch.label} の音量（いま ${pct(now)}）`);
    if (level === undefined) continue;
    await c.update(ch.key, Number(level), vscode.ConfigurationTarget.Global);
  }
}

// ---------------------------------------------------------------- lifecycle
function activate(context) {
  ctx = context;
  out = vscode.window.createOutputChannel("demon");
  bar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  setBar("$(play) demon", "クリックで乗車");
  bar.command = "demon.toggle";
  bar.show();
  mixBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, -0.5);
  mixBar.command = "demon.mixer";
  showMixer();
  mixBar.show();
  keyBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, -1);
  keyBar.command = "demon.keySource";
  showKeySource();
  keyBar.show();

  context.subscriptions.push(
    out, bar, keyBar, mixBar,
    vscode.commands.registerCommand("demon.keySource", pickKeySource),
    vscode.commands.registerCommand("demon.mixer", openMixer),
    vscode.workspace.onDidChangeConfiguration((e) => {
      const changed = CHANNELS.filter((c) => e.affectsConfiguration(`demon.${c.key}`)).map((c) => c.key);
      if (changed.length) {
        sendVolumes(changed);
        showMixer();
      }
    }),
    vscode.workspace.onDidChangeConfiguration((e) => e.affectsConfiguration("demon.keySource") && showKeySource()),
    vscode.commands.registerCommand("demon.start", start),
    vscode.commands.registerCommand("demon.stop", stop),
    vscode.commands.registerCommand("demon.toggle", () => (proc ? stop() : start())),
    vscode.commands.registerCommand("demon.setup", async () => {
      await stop();
      try {
        if (await ensurePython(true)) vscode.window.showInformationMessage("demon: Python 環境を作り直しました。");
      } catch (e) {
        out.appendLine(String(e.message || e));
        vscode.window.showErrorMessage("demon: Python 環境の準備に失敗しました（出力パネル参照）");
      }
    }),
    vscode.workspace.onDidChangeTextDocument(onEdit),
  );
}

function deactivate() {
  return stop();   // 駅で停めて、続きを保存してから眠る
}

module.exports = { activate, deactivate };
