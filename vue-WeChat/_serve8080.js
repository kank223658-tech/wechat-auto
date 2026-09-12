// 8080 dev server 保活包装：子进程 stdio 直接写文件，不依赖任何父 shell 的管道。
// 用法: node _serve8080.js
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const here = __dirname;
const nodeExe = process.execPath;
const cli = path.join(here, "node_modules", "@vue", "cli-service", "bin", "vue-cli-service.js");
const out = fs.openSync(path.join(here, "_dev8080.log"), "a");
const err = fs.openSync(path.join(here, "_dev8080.err.log"), "a");

fs.appendFileSync(path.join(here, "_dev8080.log"), "\n=== wrapper start " + new Date().toISOString() + " ===\n");

const child = spawn(nodeExe, [cli, "serve", "--port", "8080"], {
  cwd: here,
  env: Object.assign({}, process.env, { NODE_OPTIONS: "--openssl-legacy-provider" }),
  stdio: ["ignore", out, err],
});

child.on("exit", (code, sig) => {
  fs.appendFileSync(path.join(here, "_dev8080.log"),
    "=== wrapper child exited code=" + code + " sig=" + sig + " " + new Date().toISOString() + " ===\n");
});
child.on("error", (e) => {
  fs.appendFileSync(path.join(here, "_dev8080.err.log"), "wrapper spawn error: " + e + "\n");
});
process.on("exit", () => {
  try { child.kill(); } catch (e) {}
});
