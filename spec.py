"""Single source of truth for the Paperclip template's services.
build_source.py writes it to the live source project; repair.py writes it into the template.
"""
import pathlib

# Official upstream image, digest of tag 2026.916.1 (== :latest on 2026-09-26).
IMAGE = "ghcr.io/paperclipai/paperclip:2026.916.1"
PG_IMAGE = "ghcr.io/railwayapp-templates/postgres-ssl:17"

PG_VARS = {
    "POSTGRES_DB": "railway",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": '${{ secret(32, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") }}',
    # Fresh Railway volumes carry lost+found; initdb refuses a non-empty dir.
    "PGDATA": "/var/lib/postgresql/data/pgdata",
    "PGHOST": "${{RAILWAY_PRIVATE_DOMAIN}}",
    "PGPORT": "5432",
    "PGUSER": "${{POSTGRES_USER}}",
    "PGPASSWORD": "${{POSTGRES_PASSWORD}}",
    "PGDATABASE": "${{POSTGRES_DB}}",
    "SSL_CERT_DAYS": "820",
    "DATABASE_URL": "postgresql://${{PGUSER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{PGDATABASE}}",
    "RAILWAY_DEPLOYMENT_DRAINING_SECONDS": "60",
}

PAPERCLIP_VARS = {
    # No HOST override: the server maps bind to lan (0.0.0.0) regardless (verified in the
    # boot banner with HOST=::), and the public edge + healthcheck reach it fine.
    # Paperclip listens on PORT=3101 (Railway healthchecks PORT, so /api/health hits Paperclip
    # directly). The /connect helper (connect.mjs) listens on 3100, the domain's target port,
    # and proxies everything except /connect to Paperclip, websockets included.
    "PORT": "3101",
    "CONNECT_PORT": "3100",
    "DATABASE_URL": "${{Postgres.DATABASE_URL}}",
    # private (image default) keeps the browser "Claim this instance" first-admin flow:
    # the first signed-in visitor claims admin. Chosen for UX over public's CLI invite;
    # the listing tells deployers to claim immediately after the deploy goes green.
    "PAPERCLIP_DEPLOYMENT_MODE": "authenticated",
    "PAPERCLIP_DEPLOYMENT_EXPOSURE": "private",
    # private mode turns Better Auth rate limiting off by default; this is a public URL.
    "PAPERCLIP_AUTH_RATE_LIMIT_ENABLED": "true",
    # private mode's hostname guard 403s any Host outside the allowlist, including Railway's
    # prober (Host: healthcheck.railway.app): first private deploy FAILED on 14x HTTP 403.
    # Additive to the PAPERCLIP_PUBLIC_URL host (server/src/config.ts:246).
    "PAPERCLIP_ALLOWED_HOSTNAMES": "healthcheck.railway.app",
    "PAPERCLIP_PUBLIC_URL": "https://${{RAILWAY_PUBLIC_DOMAIN}}",
    "PAPERCLIP_MIGRATION_AUTO_APPLY": "true",
    "BETTER_AUTH_SECRET": "${{secret(64)}}",
    "PAPERCLIP_TOOL_ACTION_SIGNING_SECRET": "${{secret(64)}}",
    # Falls back to BETTER_AUTH_SECRET, but unset makes the boot banner say
    # "Agent JWT missing (run npx paperclipai onboard)", which misleads deployers.
    "PAPERCLIP_AGENT_JWT_SECRET": "${{secret(64)}}",
}

PAPERCLIP_VARS["CONNECT_HELPER_JS"] = (pathlib.Path(__file__).parent / "connect.mjs").read_text()

# Railway discards the image ENTRYPOINT, so tini + docker-entrypoint.sh (volume chown, gosu to
# node) are called explicitly. The helper ships in a variable to keep the official image
# unmodified; it restarts in a loop if it ever dies, Paperclip stays the container's main process.
START_COMMAND = (
    '/usr/bin/tini -- docker-entrypoint.sh /bin/sh -c "'
    'printenv CONNECT_HELPER_JS > /tmp/connect.mjs && node /tmp/connect.mjs --write-patch /tmp/usage-patch.mjs /tmp/claude-launcher; '
    '(while true; do node /tmp/connect.mjs; sleep 2; done) & '
    # Newest Claude Code on the volume, installed in the background each boot: new models
    # need new CLIs (Opus 5.5 needs >=2.1.280; image shipped 2.1.278) and the image's CLI is
    # root-owned, so it cannot self-update. PATH prefers it once present, else the image's.
    '(npm i -g --prefix /paperclip/.cli @anthropic-ai/claude-code@latest > /tmp/cli-update.log 2>&1 '
    '&& echo [cli] claude updated: $(/paperclip/.cli/bin/claude --version) || echo [cli] claude update failed, see /tmp/cli-update.log) & '
    # Agents run Claude Code through Paperclip's bundled Agent SDK binary (2.1.263 in 2026.916.1),
    # whose env allowlist drops CLAUDE_CODE_EXECUTABLE, so point the bundled binary itself at the
    # launcher. /app is node-owned and container-local: redone on every boot.
    'for f in /app/node_modules/.pnpm/@anthropic-ai+claude-agent-sdk-linux-*/node_modules/@anthropic-ai/claude-agent-sdk-linux-*/claude; do ln -sf /tmp/claude-launcher $f; done; '
    'export PATH=/paperclip/.cli/bin:$PATH; '
    'exec node --import /tmp/usage-patch.mjs --import ./server/node_modules/tsx/dist/loader.mjs server/dist/index.js"'
)

PAPERCLIP_DEPLOY = {
    "startCommand": START_COMMAND,
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10,
}
