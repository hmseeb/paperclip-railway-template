// Paperclip /connect helper. Runs inside the official image, in front of Paperclip.
//
// Paperclip's "Connect a model" subscription flow creates an empty login folder under
// <instance>/ai-local-logins/<id>/ and polls it, expecting someone to run a CLI login on
// the server. On Railway nobody has a terminal there, so this helper does it:
//   Claude: writes the admin's saved `claude setup-token` token as .credentials.json
//   Codex:  runs `codex login --device-auth` and shows the link + code on /connect
// Everything that is not /connect is proxied untouched (HTTP + websockets) to Paperclip.
import http from "node:http";
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const LISTEN = Number(process.env.CONNECT_PORT || 3100);
const UPSTREAM = Number(process.env.PORT || 3101);
const HOME = process.env.PAPERCLIP_HOME || "/paperclip";
const LOGINS = path.join(HOME, "instances", process.env.PAPERCLIP_INSTANCE_ID || "default", "ai-local-logins");
const TOKEN_FILE = path.join(HOME, "connect", "claude-token");
const CODEX_URL = "https://auth.openai.com/codex/device";
const CODEX_TTL_MS = 15 * 60 * 1000;
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
// Launcher for Paperclip's Claude agents (claude-agent-acp honours CLAUDE_CODE_EXECUTABLE). Its
// bundled Claude Code lags new models; prefer the copy the boot script keeps updated on the
// volume, else the image's global CLI (also newer than the bundled one).
const CLAUDE_LAUNCHER = `#!/bin/sh
[ -x /paperclip/.cli/bin/claude ] && exec /paperclip/.cli/bin/claude "$@"
exec /usr/local/bin/claude "$@"
`;
if (process.argv[2] === "--write-patch") {
  fs.writeFileSync(process.argv[3], USAGE_PATCH);
  if (process.argv[4]) fs.writeFileSync(process.argv[4], CLAUDE_LAUNCHER, { mode: 0o755 });
  process.exit(0);
}

// ---- login folder watcher -------------------------------------------------------------
const codex = new Map(); // dir id -> { code, status, startedAt, child }
let claudeFilled = null; // last time a Claude login folder was filled

const readToken = () => { try { return fs.readFileSync(TOKEN_FILE, "utf8").trim(); } catch { return ""; } };
const exists = (p) => fs.existsSync(p);

function startCodex(id) {
  const dir = path.join(LOGINS, id);
  const s = { code: null, status: "starting", startedAt: Date.now(), child: null };
  codex.set(id, s);
  // `script` gives codex a pseudo-terminal; it prints the device code only when it has one.
  const cmd = `codex -c 'cli_auth_credentials_store="file"' login --device-auth`;
  const child = spawn("script", ["-qfec", cmd, "/dev/null"], { env: { ...process.env, CODEX_HOME: dir } });
  s.child = child;
  let out = "";
  const onData = (buf) => {
    out = (out + buf.toString()).replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").slice(-4000);
    const m = out.match(/\b([A-Z0-9]{4}-[A-Z0-9]{5})\b/);
    if (m && !s.code) { s.code = m[1]; s.status = "waiting"; log(`Codex sign-in ${id}: code ${s.code}`); }
  };
  child.stdout.on("data", onData);
  child.stderr.on("data", onData);
  const timer = setTimeout(() => child.kill("SIGTERM"), CODEX_TTL_MS);
  child.on("exit", (code) => {
    clearTimeout(timer);
    s.status = code === 0 && exists(path.join(dir, "auth.json")) ? "connected" : (s.status === "cancelled" ? "cancelled" : "failed");
    log(`Codex sign-in ${id}: ${s.status}`);
  });
}

function scan() {
  let ids = [];
  try { ids = fs.readdirSync(LOGINS); } catch { return; }
  for (const id of ids) {
    const dir = path.join(LOGINS, id);
    if (exists(path.join(dir, "config.toml"))) { // Paperclip writes this only for OpenAI/Codex
      if (!codex.has(id) && !exists(path.join(dir, "auth.json"))) startCodex(id);
    } else if (!exists(path.join(dir, ".credentials.json"))) {
      const token = readToken();
      if (!token) continue;
      fs.writeFileSync(path.join(dir, ".credentials.json"),
        JSON.stringify({ claudeAiOauth: { accessToken: token } }), { mode: 0o600 });
      claudeFilled = Date.now();
      log(`Claude sign-in ${id}: token provided`);
    }
  }
  for (const [id, s] of codex) { // Paperclip deletes the folder on connect or cancel
    if (!ids.includes(id)) {
      if (s.child && s.child.exitCode === null) { s.status = "cancelled"; s.child.kill("SIGTERM"); }
      if (Date.now() - s.startedAt > CODEX_TTL_MS) codex.delete(id);
    }
  }
}
setInterval(scan, 2000);

// ---- /connect page -------------------------------------------------------------------
async function admin(req) {
  const r = await fetch(`http://127.0.0.1:${UPSTREAM}/api/cli-auth/me`, {
    headers: { cookie: req.headers.cookie || "", host: req.headers.host || "localhost" },
  }).catch(() => null);
  if (!r || !r.ok) return null;
  const me = await r.json().catch(() => null);
  return me && me.userId ? me : null;
}

function state() {
  const active = [...codex.entries()].sort((a, b) => b[1].startedAt - a[1].startedAt)[0];
  return {
    claude: { tokenSaved: Boolean(readToken()), lastProvided: claudeFilled },
    codex: active ? { id: active[0], url: CODEX_URL, code: active[1].code, status: active[1].status,
                      expiresAt: active[1].startedAt + CODEX_TTL_MS } : null,
  };
}

const body = (req) => new Promise((ok) => { let b = ""; req.on("data", (c) => { b += c; if (b.length > 1e5) req.destroy(); }); req.on("end", () => ok(b)); });
const send = (res, code, type, data) => { res.writeHead(code, { "content-type": type, "cache-control": "no-store" }); res.end(data); };
const json = (res, code, data) => send(res, code, "application/json", JSON.stringify(data));

async function saveClaude(token) {
  token = token.trim();
  if (!token) { fs.rmSync(TOKEN_FILE, { force: true }); return { ok: true, removed: true }; }
  if (!/^sk-ant-oat\d*-/.test(token)) return { ok: false, error: "That does not look like a setup token. Run claude setup-token and paste the sk-ant-oat... value." };
  const r = await fetch("https://api.anthropic.com/api/oauth/usage", {
    headers: { authorization: `Bearer ${token}`, "anthropic-beta": "oauth-2025-04-20" },
    signal: AbortSignal.timeout(15000),
  }).catch(() => null);
  // Only 401 means a bad token; 403 (no profile scope) and 429/5xx are expected (see USAGE_PATCH).
  if (r && r.status === 401) return { ok: false, error: "Anthropic rejected the token. Run claude setup-token again and paste the new one." };
  fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true, mode: 0o700 });
  fs.writeFileSync(TOKEN_FILE, token, { mode: 0o600 });
  return { ok: true };
}

async function handleConnect(req, res) {
  if (req.url.split("?")[0] === "/connect/inline.js") return send(res, 200, "text/javascript", INLINE); // no secrets; its API calls are gated
  const me = await admin(req);
  if (!me) { res.writeHead(302, { location: "/auth?next=/connect" }); return res.end(); }
  if (!me.isInstanceAdmin) return send(res, 403, "text/plain", "Only the Paperclip instance admin can connect models.");
  const url = req.url.split("?")[0];
  if (req.method === "GET" && url === "/connect") return send(res, 200, "text/html; charset=utf-8", PAGE);
  if (req.method === "GET" && url === "/connect/state") return json(res, 200, state());
  if (req.method === "POST") {
    const origin = req.headers.origin || "";
    if (!origin || new URL(origin).host !== req.headers.host) return json(res, 403, { ok: false, error: "Bad origin" });
    if (url === "/connect/claude") {
      const { token = "" } = JSON.parse((await body(req)) || "{}");
      return json(res, 200, await saveClaude(String(token)));
    }
  }
  send(res, 404, "text/plain", "Not found");
}

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect a model · Paperclip</title><style>
body{font:15px/1.5 ui-sans-serif,-apple-system,sans-serif;background:#141413;color:#fff;max-width:620px;margin:48px auto;padding:0 20px}
h1{font-size:26px;margin:0 0 4px}p.sub{color:#9a958a;margin:0 0 28px}section{border:1px solid #2f2c28;border-radius:14px;padding:20px;margin:0 0 18px;background:#1f1d1a}
h2{font-size:17px;margin:0 0 10px}ol{padding-left:20px;margin:8px 0}code,.code{font-family:ui-monospace,Menlo,monospace}
.code{font-size:30px;letter-spacing:3px;margin:10px 0;display:block}input{width:100%;box-sizing:border-box;background:#141413;color:#fff;border:1px solid #3a3836;border-radius:8px;padding:10px;font:14px ui-monospace,monospace}
button{margin-top:10px;background:#fff;color:#141413;border:0;border-radius:999px;padding:8px 18px;font-weight:600;cursor:pointer}
.muted{color:#9a958a}.ok{color:#22c55e}.err{color:#f87171}a{color:#93c5fd}</style></head><body>
<h1>Connect a model</h1><p class="sub">For Paperclip's subscription sign-in on Railway. Keep this tab open next to Paperclip's <b>Connect a model</b> step.</p>
<section><h2>Claude subscription</h2>
<ol><li>On your own computer run <code>claude setup-token</code> and copy the <code>sk-ant-oat…</code> token.</li>
<li>Paste it here and save. It is kept on your Paperclip volume only.</li>
<li>In Paperclip, choose <b>Claude · Subscription</b> and click <b>Connect</b>.</li></ol>
<input id="tok" type="password" placeholder="sk-ant-oat01-..." autocomplete="off"><button id="save">Save token</button>
<p id="cst" class="muted"></p></section>
<section><h2>Codex (ChatGPT subscription)</h2>
<p class="muted" id="xhint">In Paperclip, choose <b>Codex · Subscription</b>. A one-time code appears here within a few seconds.</p>
<div id="xbox" hidden><ol><li>Open <a id="xurl" target="_blank" rel="noopener"></a> and sign in to ChatGPT.</li><li>Enter this code:</li></ol>
<span class="code" id="xcode"></span><p id="xst" class="muted"></p></div></section>
<script>
const $=id=>document.getElementById(id);
async function refresh(){const s=await (await fetch('/connect/state')).json();
$('cst').className=s.claude.tokenSaved?'ok':'muted';
$('cst').textContent=s.claude.tokenSaved?'Token saved.'+(s.claude.lastProvided?' Last handed to Paperclip '+new Date(s.claude.lastProvided).toLocaleTimeString()+'.':' Click Connect in Paperclip.'):'No token saved yet.';
const x=s.codex;$('xbox').hidden=!x||!x.code;
if(x){$('xurl').href=$('xurl').textContent=x.url;$('xcode').textContent=x.code||'';
const left=Math.max(0,Math.round((x.expiresAt-Date.now())/1000));
const msg={starting:'Starting sign-in…',waiting:'Waiting for you to approve ('+Math.floor(left/60)+':'+String(left%60).padStart(2,'0')+' left).',connected:'Signed in. Paperclip picks it up automatically.',failed:'Sign-in failed or expired. Click the Codex tile in Paperclip again to retry.',cancelled:'Cancelled in Paperclip.'}[x.status];
$('xst').textContent=msg;$('xst').className=x.status==='connected'?'ok':x.status==='failed'?'err':'muted';$('xhint').hidden=!!x.code;}}
$('save').onclick=async()=>{$('cst').textContent='Checking token with Anthropic…';
const r=await (await fetch('/connect/claude',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({token:$('tok').value})})).json();
if(!r.ok){$('cst').className='err';$('cst').textContent=r.error;return}$('tok').value='';refresh()};
refresh();setInterval(refresh,2000);
</script></body></html>`;

// Injected into Paperclip's own pages: on the "Connect a model" step it replaces the
// "run this in a terminal" block with the token box (Claude) or the live device code (Codex).
// Anchored on the sign-in command's login folder path; if Paperclip's markup changes, it
// simply finds nothing and /connect keeps working. Uses CSS order, never moves React nodes.
const INLINE = `(() => {
const BOX = "margin:0 0 4px;padding:18px;border:1px solid rgba(127,127,127,.3);border-radius:12px;color:var(--foreground,inherit);font-size:14px;line-height:1.5;text-align:center";
const BTN = "display:block;width:100%;margin-top:14px;padding:12px 16px;border-radius:999px;border:0;background:var(--foreground,#fff);color:var(--background,#141413);font-weight:600;font-size:15px;cursor:pointer;text-decoration:none";
const MUTED = "opacity:.65;margin-top:10px";
let state = null, busy = false;
async function poll(){ try { const r = await fetch("/connect/state",{cache:"no-store"}); state = r.ok ? await r.json() : null; } catch { state = null; } render(); }
function render(){
  for (const code of document.querySelectorAll("pre code")) {
    const cmd = code.textContent || ""; const m = cmd.match(/ai-local-logins.([0-9a-f-]{36})/); if (!m) continue;
    const kind = cmd.includes("CODEX_HOME") ? "codex" : cmd.includes("CLAUDE_CONFIG_DIR") ? "claude" : null; if (!kind || !state) continue;
    const box = code.closest("div.rounded-md"), wrap = box && box.parentElement; if (!wrap) continue;
    wrap.style.display = "flex"; wrap.style.flexDirection = "column";
    box.style.display = "none";
    for (const el of wrap.querySelectorAll(":scope > p")) if (/Run this in a terminal|on the machine running Paperclip|Connect uses your local|Run the sign-in command/.test(el.textContent)) el.style.display = "none";
    let panel = wrap.querySelector(":scope > .pc-connect");
    if (!panel) { panel = document.createElement("div"); panel.className = "pc-connect"; panel.style.cssText = BOX; panel.style.order = "-1"; wrap.appendChild(panel); }
    const html = kind === "claude" ? claude() : codex(m[1]);
    if (panel.dataset.html !== html) { panel.dataset.html = html; panel.innerHTML = html; wire(panel); }
  }
}
function claude(){
  if (state.claude.tokenSaved) return "<div style='font-weight:600;font-size:15px'>Claude subscription token saved</div><div style='" + MUTED + "'>Click Connect to use it. <a href='/connect' target='_blank' style='text-decoration:underline'>Change token</a></div>";
  return "<div style='font-weight:600;font-size:15px'>Sign in with your Claude subscription</div>" +
    "<div style='" + MUTED + ";margin-top:4px'>Run <code>claude setup-token</code> on your computer and paste the token below.</div>" +
    "<input class='pc-tok' type='password' placeholder='sk-ant-oat01-...' autocomplete='off' style='display:block;width:100%;box-sizing:border-box;margin-top:14px;padding:11px 12px;border-radius:10px;border:1px solid rgba(127,127,127,.35);background:transparent;color:inherit;font-family:ui-monospace,monospace;text-align:center'>" +
    "<button class='pc-save' type='button' style='" + BTN + "'>Save token</button><div class='pc-msg' style='margin-top:8px;color:#f87171'></div>";
}
function codex(id){
  const x = state.codex && state.codex.id === id ? state.codex : null;
  if (!x || !x.code) return "<div style='" + MUTED + ";margin:0'>Preparing your ChatGPT sign-in code...</div>";
  if (x.status === "connected") return "<div style='font-weight:600;font-size:15px'>Signed in to ChatGPT</div><div style='" + MUTED + "'>Click Connect to finish.</div>";
  if (x.status === "failed") return "<div style='font-weight:600;font-size:15px'>This code expired</div><div style='" + MUTED + "'>Click Start sign-in again below for a new one.</div>";
  return "<div style='font-weight:600;font-size:15px'>Sign in with ChatGPT</div><div style='" + MUTED + ";margin-top:4px'>Enter this code on the ChatGPT sign-in page</div>" +
    "<div class='pc-code' title='Click to copy' style='font:700 38px/1.1 ui-monospace,Menlo,monospace;letter-spacing:5px;margin:16px 0 4px;cursor:pointer;user-select:all'>" + x.code + "</div>" +
    "<a class='pc-open' href='" + x.url + "' target='_blank' rel='noopener' data-code='" + x.code + "' style='" + BTN + "'>Copy code & open ChatGPT</a>" +
    "<div style='" + MUTED + "'>Waiting for approval, then click Connect</div>";
}
function copy(t){ try { navigator.clipboard.writeText(t); } catch {} }
function wire(panel){
  const open = panel.querySelector(".pc-open"); if (open) open.onclick = () => copy(open.dataset.code);
  const code = panel.querySelector(".pc-code"); if (code) code.onclick = () => { copy(code.textContent); code.style.opacity = ".5"; setTimeout(() => code.style.opacity = "1", 300); };
  const b = panel.querySelector(".pc-save"); if (!b) return;
  b.onclick = async () => { if (busy) return; busy = true; const msg = panel.querySelector(".pc-msg"); msg.style.color = "inherit"; msg.textContent = "Checking token with Anthropic...";
    try { const r = await (await fetch("/connect/claude",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({token:panel.querySelector(".pc-tok").value})})).json();
      if (!r.ok) { msg.style.color = "#f87171"; msg.textContent = r.error; } else { await poll(); } } finally { busy = false; } };
}
new MutationObserver(() => { if (!busy) render(); }).observe(document.documentElement, { childList: true, subtree: true });
poll(); setInterval(poll, 2000);
})();`;

// ---- proxy -----------------------------------------------------------------------------
const server = http.createServer((req, res) => {
  if (req.url === "/connect" || req.url.startsWith("/connect/") || req.url.startsWith("/connect?")) {
    return handleConnect(req, res).catch((e) => { log(e); send(res, 500, "text/plain", "connect helper error"); });
  }
  const page = req.method === "GET" && (req.headers.accept || "").includes("text/html");
  const headers = { ...req.headers };
  if (page) delete headers["accept-encoding"]; // uncompressed HTML so the script tag can be added
  const up = http.request({ host: "127.0.0.1", port: UPSTREAM, method: req.method, path: req.url, headers }, (r) => {
    if (!page || !(r.headers["content-type"] || "").startsWith("text/html")) {
      res.writeHead(r.statusCode, r.rawHeaders);
      return r.pipe(res);
    }
    const chunks = [];
    r.on("data", (c) => chunks.push(c));
    r.on("end", () => {
      const html = Buffer.concat(chunks).toString("utf8").replace("</body>", '<script src="/connect/inline.js" defer></script></body>');
      const h = { ...r.headers, "content-length": Buffer.byteLength(html) };
      delete h["transfer-encoding"];
      res.writeHead(r.statusCode, h);
      res.end(html);
    });
  });
  up.on("error", () => { if (!res.headersSent) send(res, 502, "text/plain", "Paperclip is starting…"); else res.destroy(); });
  req.pipe(up);
});
server.on("upgrade", (req, socket, head) => {
  const up = net.connect(UPSTREAM, "127.0.0.1", () => {
    let raw = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) raw += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    up.write(raw + "\r\n");
    if (head && head.length) up.write(head);
    up.pipe(socket).pipe(up);
  });
  up.on("error", () => socket.destroy());
  socket.on("error", () => up.destroy());
});
server.listen(LISTEN, "::", () => log(`listening on ${LISTEN}, proxying to ${UPSTREAM}, watching ${LOGINS}`));
