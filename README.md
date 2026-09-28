# Paperclip on Railway

[Deploy on Railway](https://railway.com/deploy/paperclip-official-1) · Railway template for [Paperclip](https://github.com/paperclipai/paperclip): official image + Postgres 17, `authenticated/private` mode: first admin claims the instance from the browser.

| File | Purpose |
|---|---|
| `spec.py` | Services, variables, start command (single source of truth) |
| `build_source.py` | Creates the live source project (regeneration master) |
| `apply_live.py` | Re-applies `spec.py` to the live source service |
| `repair.py` | Restores literals stripped by `templateGenerate`, writes template into Auromations, asserts read-back |
| `deploy_as_stranger.py` | `templateDeployV2` into a fresh project |
| `test/journey.sh <url>` | Browser claim, second-claim refusal, company CRUD, second-user isolation |
| `TEMPLATE_OVERVIEW.md` | Marketplace listing copy |
| `template.json` | Build sheet with rationale |

Regenerate: `python3 apply_live.py`, `templateGenerate` into `generated.json`, `python3 repair.py <templateId>`.
