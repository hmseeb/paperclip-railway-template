"""Single source of truth for the Paperclip template's services.
build_source.py writes it to the live source project; repair.py writes it into the template.
"""
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
    # Railway healthchecks the injected PORT (default 8080); pin the image's real port.
    "PORT": "3100",
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

PAPERCLIP_DEPLOY = {
    # None: image ENTRYPOINT (tini + docker-entrypoint.sh chowns the volume) + CMD.
    "startCommand": None,
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10,
}
