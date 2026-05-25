#!/usr/bin/env node
/*
 * dashboard_post.cjs - Minimal stdio MCP client for posting one alert to a single
 * roosync dashboard, reusing the exact roo-state-manager `roosync_dashboard` tool
 * (so the server's structure/condensation logic stays authoritative).
 *
 * Why this exists: `claude -p` headless does NOT expose roo-state-manager's tools
 * (the server's heavy skeleton-load startup exceeds the print-session MCP init
 * window, so the tool never enters the function schema). A direct MCP client is
 * deterministic, token-free, and lets us control the readiness wait.
 *
 * Usage:
 *   node dashboard_post.cjs --workspace <a,b,...> --content-file <path> [--tags a,b]
 * Multiple workspaces are posted SEQUENTIALLY in one server session (they share
 * GDrive storage; concurrent .tmp->.md renames collide).
 * Exit: 0 only if every append succeeds, 1 if any failed.
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

function arg(name, def) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : def;
}

const workspaces = (arg("--workspace") || "").split(",").map(s => s.trim()).filter(Boolean);
const contentFile = arg("--content-file");
const tags = (arg("--tags", "SECURITY,WARN") || "").split(",").map(s => s.trim()).filter(Boolean);
const machineId = arg("--machine", "myia-ai-01");
const authorWs = arg("--author-workspace", "vllm");

if (!workspaces.length || !contentFile) {
  console.error("usage: node dashboard_post.cjs --workspace <a,b,...> --content-file <path> [--tags a,b]");
  process.exit(1);
}
const content = fs.readFileSync(contentFile, "utf8");

// roo-state-manager wrapper location (same as ~/.claude.json mcpServers entry).
const SERVER_DIR = "D:\\roo-extensions\\mcps\\internal\\servers\\roo-state-manager";
const SERVER_JS = path.join(SERVER_DIR, "mcp-wrapper.cjs");

const child = spawn("node", [SERVER_JS], {
  cwd: SERVER_DIR,
  stdio: ["pipe", "pipe", "inherit"], // server logs go to our stderr
  windowsHide: true,
});

let buf = "";
const pending = new Map(); // id -> {resolve, reject}
let nextId = 1;

function send(method, params, isNotification) {
  const msg = { jsonrpc: "2.0", method, params };
  if (!isNotification) msg.id = nextId++;
  child.stdin.write(JSON.stringify(msg) + "\n");
  return msg.id;
}
function request(method, params) {
  const id = send(method, params, false);
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

child.stdout.on("data", (d) => {
  buf += d.toString("utf8");
  let idx;
  while ((idx = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, idx).trim();
    buf = buf.slice(idx + 1);
    if (!line) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; } // skip non-protocol log lines
    if (o.id != null && pending.has(o.id)) {
      const p = pending.get(o.id); pending.delete(o.id);
      if (o.error) p.reject(new Error(JSON.stringify(o.error)));
      else p.resolve(o.result);
    }
  }
});
child.on("error", (e) => { console.error("spawn error:", e.message); process.exit(1); });

const HARD_TIMEOUT_MS = 240000;
const killer = setTimeout(() => { console.error("timeout"); try { child.kill(); } catch {} process.exit(1); }, HARD_TIMEOUT_MS);

(async () => {
  try {
    await request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "leaked-key-relay", version: "1.0" },
    });
    send("notifications/initialized", {}, true);

    let allOk = true;
    for (const ws of workspaces) {           // SEQUENTIAL: shared GDrive storage
      const res = await request("tools/call", {
        name: "roosync_dashboard",
        arguments: {
          action: "append",
          type: "workspace",
          workspace: ws,
          tags,
          author: { machineId, workspace: authorWs },
          content,
        },
      });
      const isErr = res && res.isError;
      const text = (res && res.content || []).map(c => c.text || "").join("\n");
      console.log(`[${ws}] ` + (isErr ? "TOOL_ERROR: " : "OK: ") + text.slice(0, 200).replace(/\s+/g, " "));
      if (isErr) allOk = false;
      await new Promise(r => setTimeout(r, 1500)); // let the .tmp->.md rename settle
    }
    clearTimeout(killer);
    try { child.kill(); } catch {}
    process.exit(allOk ? 0 : 1);
  } catch (e) {
    console.error("post failed:", e.message);
    clearTimeout(killer);
    try { child.kill(); } catch {}
    process.exit(1);
  }
})();
