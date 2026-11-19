"""Single source of truth for the Paperclip template's services.
build_source.py writes it to the live source project; repair.py writes it into the template.
"""
import pathlib

# Official upstream image on :latest (hybrid policy): on 2026-11-20 :latest had the same digest
# as v2026.1117.0, the newest stable release; canary is a separate tag. Paperclip runs its own
# migrations on boot (PAPERCLIP_MIGRATION_AUTO_APPLY). test/spec_test.py checks the start command
# against the newest release's ENTRYPOINT/CMD; rerun it before republishing.
IMAGE = "ghcr.io/paperclipai/paperclip:latest"
# Git ref for the listing icon (a real tag, so the URL never moves).
ICON_REF = "v2026.1023.0"
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
    # directly). connect.mjs listens on 3100, the domain's target port, and proxies everything
    # to Paperclip, websockets included. Kept as a proxy (not dropped) so existing deploys and the
    # agent-computer template keep the same ports; /connect is only a pointer page since 1023.0.
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
    # Upstream bug paperclipai/paperclip#18557 (open on 2026-11-20): unset, the server checks
    # ACPX provider packages against /app/server, which the image's pnpm layout never passes,
    # so every new Runner agent stays "verifying" (acpx_runtime_unavailable). The image's own
    # provider pack passes; real runs use it too (verified with a haiku run on 2026.1117.0).
    "PAPERCLIP_ACPX_PROVIDER_PACKAGE_ROOT": "/opt/paperclip-runner/provider-pack",
}

PAPERCLIP_VARS["CONNECT_HELPER_JS"] = (pathlib.Path(__file__).parent / "connect.mjs").read_text()

# Railway discards the image ENTRYPOINT, so tini + docker-entrypoint.sh (volume chown, gosu to
# node) are called explicitly. The proxy ships in a variable to keep the official image
# unmodified; it restarts in a loop if it ever dies, Paperclip stays the container's main process.
START_COMMAND = (
    '/usr/bin/tini -s -- docker-entrypoint.sh /bin/sh -c "'
    'printenv CONNECT_HELPER_JS > /tmp/connect.mjs && node /tmp/connect.mjs --write-patch /tmp/usage-patch.mjs; '
    '(while true; do node /tmp/connect.mjs; sleep 2; done) & '
    # Newest Claude Code + Codex on the volume, installed in the background each boot: new models
    # need new CLIs (Opus 5.5 needs >=2.1.280; image shipped 2.1.278) and the image's CLI is
    # root-owned, so it cannot self-update. PATH prefers it once present, else the image's.
    '(npm i -g --prefix /paperclip/.cli @anthropic-ai/claude-code@latest @openai/codex@latest > /tmp/cli-update.log 2>&1 '
    '&& echo [cli] updated: $(/paperclip/.cli/bin/claude --version), $(/paperclip/.cli/bin/codex --version) || echo [cli] update failed, see /tmp/cli-update.log) & '
    # No symlinks over the bundled Agent SDK / codex binaries any more (done up to 2026.1023.0):
    # since 2026.1106.0 agents run on the Paperclip Runner, whose session.open verifies the
    # installed provider files and rejects a swapped binary (admission_installation). The
    # Runner's own SDK ships Claude Code 2.1.286 in 2026.1117.0, new enough for Opus 5.5.
    # The volume CLI above still serves the legacy CLI engine and the shell via PATH.
    'export PATH=/paperclip/.cli/bin:$PATH; '
    # Same entry as the image CMD (bundled runtime since 2026.1117.0), plus the usage preload.
    'exec node --import /tmp/usage-patch.mjs server/dist-runtime/index.mjs"'
)

PAPERCLIP_DEPLOY = {
    "startCommand": START_COMMAND,
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10,
}
