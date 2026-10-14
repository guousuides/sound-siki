// Copy the Python package next to the extension so the .vsix is self-contained.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const out = path.resolve(__dirname, "..", "python");
fs.rmSync(out, { recursive: true, force: true });
fs.cpSync(path.join(root, "demon"), path.join(out, "demon"), {
  recursive: true,
  filter: (src) => !src.includes("__pycache__") && !src.endsWith(".pyc"),
});
fs.copyFileSync(path.join(root, "requirements.txt"), path.join(out, "requirements.txt"));
console.log("bundled demon ->", out);
