// Paperclip front proxy. Runs inside the official image, in front of Paperclip.
// - Proxies everything (HTTP + websockets) to Paperclip; with COMPUTER_GATEWAY set, /_computer/
//   goes to the agent computer's live screen (used by the paperclip-agent-computer template).
// - `--write-patch` writes the usage-check preload and the Claude Code / Codex launchers.
// - /connect only explains that Paperclip now does subscription sign-in itself.
import http from "node:http";
import net from "node:net";
import fs from "node:fs";

const LISTEN = Number(process.env.CONNECT_PORT || 3100);
const UPSTREAM = Number(process.env.PORT || 3101);
// Agent computer's live screen (host:port of its gateway), served on Paperclip's own address under
// /_computer/ so people's browsers need no second domain. Unset: everything goes to Paperclip.
const LIVE_SCREEN = (process.env.COMPUTER_GATEWAY || "").match(/^\[?([^\]]+?)\]?:(\d+)$/);
const upstreamFor = (url) => (LIVE_SCREEN && url.startsWith("/_computer/") ? { host: LIVE_SCREEN[1], port: Number(LIVE_SCREEN[2]) } : { host: "127.0.0.1", port: UPSTREAM });
const log = (...a) => console.log("[connect]", ...a);

// Preload for Paperclip's own process (written by `connect.mjs --write-patch <file>`, loaded with
// node --import). Paperclip verifies a Claude subscription by calling Anthropic's usage endpoint.
// For `claude setup-token` tokens that endpoint is no gate: they are inference-only, so it answers
// 403 (no profile scope), and it rate limits hard (429 seen after a handful of calls). Only 401
// means a bad token. For setup tokens only, any other failure becomes "no usage data" so Paperclip
// accepts the token; every other request and status passes through untouched.
const USAGE_PATCH = `const f = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const res = await f(input, init);
  try {
    const url = typeof input === "string" ? input : input.url || String(input);
    const auth = new Headers((init && init.headers) || (input && input.headers) || {}).get("authorization") || "";
    if (!res.ok && res.status !== 401 && url.startsWith("https://api.anthropic.com/api/oauth/usage") && auth.startsWith("Bearer sk-ant-oat"))
      return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  } catch {}
  return res;
};
`;
// Launchers for Paperclip's agents. Its bundled Claude Agent SDK and Codex binaries lag new
// models (Opus 5.5 needs Claude Code >=2.1.280; bundled 2.1.263) and its env allowlist drops
// CLAUDE_CODE_EXECUTABLE / CODEX_PATH, so the boot script symlinks the bundled binaries to these.
// Each prefers the copy kept updated on the volume, else the image's global CLI.
const launcher = (name) => `#!/bin/sh
[ -x /paperclip/.cli/bin/${name} ] && exec /paperclip/.cli/bin/${name} "$@"
exec /usr/local/bin/${name} "$@"
`;
if (process.argv[2] === "--write-patch") {
  fs.writeFileSync(process.argv[3], USAGE_PATCH);
  for (const name of ["claude", "codex"]) fs.writeFileSync(`/tmp/${name}-launcher`, launcher(name), { mode: 0o755 });
  process.exit(0);
}

// ---- /connect -------------------------------------------------------------------------
// Paperclip 2026.1023.0 runs `claude setup-token` and `codex login --device-auth` itself and
// shows the link and code in its own Connect a model step. The old token box and the second
// Codex sign-in here raced it (two different device codes), so /connect only points there now.
const NOTE = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect a model</title><body style="font:15px/1.5 ui-sans-serif,-apple-system,sans-serif;max-width:560px;margin:48px auto;padding:0 20px">
<h1 style="font-size:24px">Connect a model in Paperclip</h1>
<p>Paperclip now signs in to your Claude or ChatGPT subscription by itself. You do not need this page.</p>
<p>Open an agent's model settings (or the <b>Connect a model</b> onboarding step), click <b>Claude</b> or <b>OpenAI</b>, and follow the link and code that Paperclip shows.</p>
<p><a href="/">Back to Paperclip</a></p></body>`;
const send = (res, code, type, data) => { res.writeHead(code, { "content-type": type, "cache-control": "no-store" }); res.end(data); };

// ---- proxy -----------------------------------------------------------------------------
const server = http.createServer((req, res) => {
  if (req.url === "/connect" || req.url.startsWith("/connect/") || req.url.startsWith("/connect?")) {
    return send(res, 200, "text/html; charset=utf-8", NOTE);
  }
  const to = upstreamFor(req.url);
  const up = http.request({ ...to, method: req.method, path: req.url, headers: req.headers }, (r) => {
    res.writeHead(r.statusCode, r.rawHeaders);
    r.pipe(res);
  });
  up.on("error", () => { if (!res.headersSent) send(res, 502, "text/plain", "Paperclip is starting…"); else res.destroy(); });
  req.pipe(up);
});
server.on("upgrade", (req, socket, head) => {
  const to = upstreamFor(req.url);
  const up = net.connect(to.port, to.host, () => {
    let raw = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) raw += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    up.write(raw + "\r\n");
    if (head && head.length) up.write(head);
    up.pipe(socket).pipe(up);
  });
  up.on("error", () => socket.destroy());
  socket.on("error", () => up.destroy());
});
server.listen(LISTEN, "::", () => log(`listening on ${LISTEN}, proxying to ${UPSTREAM}`));
