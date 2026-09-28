# Deploy and Host Paperclip on Railway

Paperclip is an open-source control plane for running a company staffed by AI agents. You define goals, an org chart and monthly budgets, then hire agents (Claude Code, Codex, OpenCode, Gemini, Kimi and more) that pick up tasks on a heartbeat, report to managers and ask you for approval when they need it.

## About Hosting Paperclip

This template runs the official `ghcr.io/paperclipai/paperclip` image (release 2026.916.1, no wrapper repo) next to a Railway Postgres 17 database. Both services keep their data on volumes: Postgres holds companies, agents, tasks and users; the `/paperclip` volume holds agent workspaces, uploaded files, the local secrets key and hourly database backups.

It boots in `authenticated` mode with `private` exposure, so every page needs a login, and the first admin is claimed straight from the browser. No CLI and no setup tokens.

## Common Use Cases

- Run a small team of coding agents against your repos with budgets and approvals
- Give a solo founder an always-on "company" of agents that works through a backlog
- Try Paperclip on a real URL before committing to your own server

## Dependencies for Paperclip Hosting

- A Railway account (Hobby is enough to start; agents that run CLIs like Claude Code want 2 GB+ of RAM)
- An API key or subscription login for at least one agent runtime (Anthropic, OpenAI, Google, and so on)

### Deployment Dependencies

- Paperclip: https://github.com/paperclipai/paperclip
- Docs: https://docs.paperclip.ing/
- Postgres image: `ghcr.io/railwayapp-templates/postgres-ssl:17`

### Implementation Details

**Claiming your instance (do this first)**

1. When the deploy goes green, open the Paperclip service's public URL.
2. Create an account and sign in.
3. On the setup screen choose **Claim this instance**. You are now the instance admin and can create your first company.

Claim it right away. Until someone claims it, the first signed-in user on the URL becomes the admin. Once it is claimed, later sign-ups are ordinary accounts with no access to your companies.

**Connecting agents (no terminal needed)**

Paperclip's subscription sign-in normally asks you to run a command on the server. This template adds a small page at `https://<your-app>/connect` (instance admin only) that does it for you:

- **Claude subscription:** run `claude setup-token` on your own computer, paste the `sk-ant-oat...` token on `/connect` and save. Then in Paperclip choose Claude, Subscription, and click Connect. The token is checked with Anthropic before it is saved and stays on your volume.
- **Codex (ChatGPT subscription):** in Paperclip choose Codex, Subscription. Within a few seconds `/connect` shows a link and a one-time code. Open the link, enter the code, approve, and Paperclip connects on its own.
- **API keys:** in Paperclip's Connect step, click **Use API key instead** under the provider tile and paste the key. No `/connect` needed.

The Claude Code, Codex, OpenCode, Gemini and Kimi CLIs are already installed in the image.

**Variables you might change**

| Variable | Default | Notes |
|---|---|---|
| `PAPERCLIP_PUBLIC_URL` | `https://<railway domain>` | Set it to your custom domain after adding one |
| `PAPERCLIP_AUTH_DISABLE_SIGN_UP` | unset | Set to `true` to close open sign-ups once your team has joined |
| `HEARTBEAT_SCHEDULER_ENABLED` | `true` | Set to `false` to pause every agent heartbeat at once |

Secrets (`BETTER_AUTH_SECRET`, `PAPERCLIP_AGENT_JWT_SECRET`, `PAPERCLIP_TOOL_ACTION_SIGNING_SECRET`, the Postgres password) are generated per deploy. Do not change `BETTER_AUTH_SECRET` after users exist; it signs every session.

**Upgrading**

Change the Paperclip service image tag to a newer release from https://github.com/paperclipai/paperclip/releases and redeploy. Database migrations apply automatically on boot (`PAPERCLIP_MIGRATION_AUTO_APPLY=true`).

**Troubleshooting**

- *"Someone else has already claimed this instance":* another account claimed it first. If that was not you, delete the project and deploy again, then claim immediately.
- *No claim option on the setup screen:* the instance is already claimed (`/api/health` shows `"bootstrapStatus":"ready"`). Sign in with the admin account.
- *Health shows a `database_backup_missing` warning right after deploy:* normal. The first automatic backup runs within the hour.
- *Agents fail to start:* the agent has no model connection. Connect one from the agent's settings, using `/connect` for subscriptions.
- *`/connect` shows no Codex code:* click the Codex tile in Paperclip first; the code appears once Paperclip starts the sign-in. If it says failed or expired, click the tile again.
- *`/connect` says Anthropic rejected the token:* create a fresh one with `claude setup-token` and paste it again.

## Why Deploy Paperclip on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying Paperclip on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
