# Manual Seeding Runbook (post per-deploy-seeding-off)

As of 2026-06-01, heavy seeding no longer runs on every deploy. `render.yaml`
sets these to `"0"` on the web service:

| Flag | What it used to run every deploy |
|------|----------------------------------|
| `SEED_DEMO` | `seed_demo --reset` (heavy, resets demo data) |
| `RUN_BOOTSTRAP_PLATFORM_CATALOG` | `bootstrap_platform_catalog --all` |
| `APPLY_UI_FIXTURE_ON_DEPLOY` | `import_ui_config fixtures/ui_config.json` |
| `RUN_PLATFORM_SEED` | `seed_platform_complete --skip-tenants` |
| `RUN_PGVECTOR_MIGRATE` | `migrate_embeddings_to_pgvector` + index verify |

## Still automatic on every deploy (do nothing)
`render_predeploy.sh` always runs these — they're idempotent and required:
- `migrate_schemas --shared/--tenant` (+ tenant schema creation/healing)
- `seed_render_users` (ensures the `admin` superuser)
- `seed_admin_dashboard_palettes`, `normalize_ui_config`, `bootstrap_at_risk_registry`
- `collectstatic`
- `integration_preflight` (kept ON — cheap pre-traffic safety gate)

## Run a step manually (Render → service → **Shell** tab, or `render ssh`)
Use the venv interpreter. All commands are idempotent.

```bash
# After editing the platform catalog / marketplace / Studio content:
.venv/bin/python manage.py bootstrap_platform_catalog --all

# After editing fixtures/ui_config.json:
.venv/bin/python manage.py import_ui_config fixtures/ui_config.json
.venv/bin/python manage.py normalize_ui_config

# After changing platform public-schema seed data:
.venv/bin/python manage.py seed_platform_complete --skip-tenants --continue-on-error

# After changing the embedding pipeline (or first run on a new DB):
.venv/bin/python manage.py migrate_embeddings_to_pgvector --write-env-flag
.venv/bin/python manage.py verify_pgvector_index --strict
```

## Brand-new environment (first deploy only)
On a fresh DB, run the manual steps above **once** after the first deploy, OR
temporarily set the matching flag to `"1"` for the first deploy and set it back
to `"0"`. Demo data (`seed_demo`) should normally stay OFF in production.

## Why this changed
Per-deploy `--reset`/`--all` seeding inflated deploy time and memory and could
churn data on every release. See the SSE/worker-starvation incident
(2026-05-31) and `docs/CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md` for the original
reason these were ON (so content changes appeared automatically) — the
trade-off now is: lighter, faster, safer deploys in exchange for running the
relevant command yourself when you actually change that content.
