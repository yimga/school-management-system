# Deploy pipeline runbook

The Render pre-deploy script (`scripts/release/render_predeploy.sh`) is the SOT
for every step that runs before traffic is routed to a new release. This doc
explains what each step does, what can fail, and how to recover.

## Pipeline (in order)

| # | Step | Purpose | Failure mode | Recovery |
|---|------|---------|--------------|----------|
| 1 | Detect `TENANT_MODE` | Determine if `USE_DJANGO_TENANTS` is on | Settings load error | Fix settings; re-deploy |
| 2 | `migrate_schemas --shared` (tenants) or `migrate` (single) | Apply shared / default-DB migrations | Bad migration SQL; cross-app dep | Roll back to last good commit; re-apply migration |
| 3 | `ensure_tenant_schemas` | Provision missing tenant schemas | Postgres role lacks `CREATE SCHEMA` | Grant role; re-deploy |
| 4 | `migrate_schemas --tenant` | Apply tenant migrations to every schema | Tenant model conflict | Identify failing tenant via log; resolve schema manually |
| 5 | `migrate_schools_to_tenants` | Bridge legacy Schools → Client+Domain | Duplicate domain | Resolve domain dupe in Postgres; re-run |
| 6 | `migrate_schemas --tenant` (second pass) | Catch any tenants created in step 5 | Same as step 4 | Same as step 4 |
| 7 | `verify_all_migrations_applied` | **NEW** v3.15 — confirm every migration applied + no model drift | Warning by default; strict via `STRICT_MIGRATION_VERIFY=1` | See "Migration verification" below |
| 8 | `backfill_schooldomain` | Idempotent SchoolDomain backfill | Skipped via `RUN_BACKFILL_SCHOOLDOMAIN=0` | Operator override |
| 9 | `check_tenant_runtime` | Startup schema sanity check | Skipped via `RUN_STARTUP_SCHEMA_CHECK=0` | Operator override |
| 10 | `seed_admin_dashboard_palettes` | Always run; idempotent | RuntimeDefaults dispatch issue | Roll back |
| 11 | `import_ui_config fixtures/ui_config.json` (conditional) | Apply UI config from fixture | Bad JSON; missing fields | Validate fixture locally |
| 12 | `normalize_ui_config` | Post-import cleanup | — | — |
| 13 | `migrate_embeddings_to_pgvector` (Postgres only) | Move JSON embeddings → pgvector | Vector extension not installed | DB role needs CREATE on database |
| 14 | `verify_pgvector_index --strict` (Postgres only) | Confirm IVFFLAT index in use | Index missing | Run `rebuild_pgvector_index --vacuum` |
| 15 | `integration_preflight` | Check integration feature flags | Feature enabled but runtime missing | Disable flag or provision integration |
| 16 | `verify_residency_readiness --quiet` (opt-in via `RUN_VERIFY_RESIDENCY_READINESS=1`) | Confirm data-residency replicas | Region misalignment | Update tenant `data_region` or add replica |
| 17 | `seed_render_users` | Ensure super-admin + tenant_admin + demo users | None — fully idempotent | — |
| 18 | `bootstrap_at_risk_registry` | Register legacy at-risk artifact in registry | **v3.14: fully idempotent + graceful skip** | — |
| 19 | `seed_default_digest_recipients` (opt-in via `RUN_SEED_DIGEST_RECIPIENTS=1`) | Risk-digest recipient discovery | Skipped by default | Operator opts in once admin pool is provisioned |
| 20 | `seed_platform_complete --skip-tenants --continue-on-error` (default ON via `RUN_PLATFORM_SEED=1`) | Public-schema seed orchestration (~17 sub-steps) | Per-step failures logged + continued | See "Platform seed orchestration" below |
| 21 | `bootstrap_platform_catalog` (legacy path; opt-in via `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`) | Older bootstrap entry point | Superseded by step 20 | Leave at default 0; step 20 covers this |
| 22 | `collectstatic --noinput --clear` | Build static assets | Disk space | Free disk |
| 23 | `scripts/release/run_health_check.sh` (if present) | DB connection check before traffic | DB down | DB recovery |
| 24 | `verify_collabora_wopi_smoke.py` (opt-in via `RUN_COLLABORA_READINESS_CHECK=1`) | Confirm collabora WOPI works | Skipped by default | Operator opts in |

## Migration verification (step 7)

The `verify_all_migrations_applied` command walks every installed app's
migration graph against the database and reports:

- **Unapplied migrations on disk** — files exist but `django_migrations` table
  doesn't have them. Usually means the previous deploy was interrupted.
- **Model-vs-migrations drift** — model code has changes that no `.py`
  migration file captures. The Render-side warning "Your models in app(s):
  'automation' have changes that are not yet reflected in a migration" is
  exactly this. **Usually benign** — F2 callable-identity drift in `upload_to`
  / `default=` callables between Python environments. Run
  `python manage.py makemigrations` locally; if it emits no new file, it's
  cosmetic. If it does emit one, commit + redeploy.

Two modes:

| Mode | Env flag | Behavior |
|------|----------|----------|
| Warn (default) | `STRICT_MIGRATION_VERIFY=0` (or unset) | Prints the report; deploy continues |
| Strict | `STRICT_MIGRATION_VERIFY=1` | Exit 1 on any drift; deploy fails |

Tenant schemas: pass `--include-tenant` to walk every tenant connection.
Predeploy does this automatically when `USE_DJANGO_TENANTS=1`.

## Platform seed orchestration (step 20)

`seed_platform_complete --skip-tenants --continue-on-error` runs ~17 idempotent
seed commands in dependency order. Per-step failures are logged + skipped (the
remaining steps still run). The orchestrator itself exits 0 even if individual
steps failed.

Sub-steps (from `apps/siteconfig/management/commands/seed_platform_complete.py`):

1. `bootstrap_platform_catalog --all` — catalog + registries + portal + compliance + provider/region
2. `seed_marketplace_scopes` — OAuth scope definitions
3. `seed_first_party_apps` — PackageVersion records
4. `seed_phase9_first_party_packages` — Phase-9 package definitions
5. `seed_ultra_high_end_experience_packs` — Experience packs
6. `seed_process_definitions` — Orchestration workflows
7. `seed_business_glossary` — Glossary terms
8. `seed_entity_catalog` — Entity metadata catalog
9. `seed_office_documents` — Operator playbook + tenant handbook
10. `seed_report_platform_plan_skus` — Report platform plan SKUs
11. `seed_br10_plan_skus` — Brazil region plan SKUs
12. `seed_regions` — i18n grading-scale defaults per region
13. `seed_preview_fixtures` — Preview fixtures
14. `seed_cursor_twelve_phases` — Twelve-phase cursor seed
15. `sync_siteconfig_dynamicfields_to_metadata` — siteconfig → metadata sync
16. `seed_dynamic_field_recipes` — DynamicFieldDefinition recipes
17. Account/role bootstrap:
    - `ensure_superadmin`
    - `ensure_default_tenant_admin`
    - `backfill_user_roles`
18. `ensure_tenant_schemas` — Tenant infra (Postgres-only no-op on SQLite)
19. `verify_registry_coverage` + `verify_region_coverage` — health checks

To skip platform seeding entirely (e.g. while debugging a deploy):
```
RUN_PLATFORM_SEED=0
```

To run platform seeding manually outside a deploy:
```bash
python manage.py seed_platform_complete --skip-tenants --continue-on-error
```

## Common deploy failure modes

### "bootstrap_at_risk_registry: error: the following arguments are required: --operator-username"

**Fixed in v3.14.** The cmd no longer requires the flag — it falls back to first
active superuser, then to username `admin` (seeded by `seed_render_users`).

### "Your models in app(s): X have changes that are not yet reflected in a migration"

Informational. Run `python manage.py makemigrations X` locally:
- If it emits a new file → commit + redeploy.
- If it emits nothing ("No changes detected") → the warning is cosmetic F2
  callable-identity drift. Safe to ignore. To silence it, set
  `STRICT_MIGRATION_VERIFY=1` would BLOCK deploys; do not set in prod.

### "OperationalError: no such column: …"

A model field exists in code but not in the DB. Means a migration is unapplied:
1. Check `python manage.py verify_all_migrations_applied --json`
2. Apply: `python manage.py migrate` (or `migrate_schemas --tenant` for tenant)
3. If migration file is missing entirely: `makemigrations <app>` then commit + redeploy.

### Tenant schema missing

Symptom: `ProgrammingError: relation "<tenant_schema>.<table>" does not exist`.

Fix: Run `python manage.py ensure_tenant_schemas` then `migrate_schemas --tenant`.
Both are already in the predeploy at steps 3 and 4 / 6.

### Seed command fails

The orchestrator with `--continue-on-error` will log the failure and skip the
step. Individual seed cmds:
- Print failure to stdout with exception details.
- Are expected to be idempotent — re-running picks up where the partial state
  left off.

To debug a specific seed step:
```bash
python manage.py seed_<step_name> --verbosity=2
```

## Operator pre-flight commands

Before pushing a deploy, run these locally to surface issues:

```bash
# 1. Are there any uncommitted makemigrations?
python manage.py makemigrations --dry-run --check

# 2. Are any migrations missing from the local DB?
python manage.py verify_all_migrations_applied --strict

# 3. Are platform seeds idempotent on your local clone?
python manage.py seed_platform_complete --skip-tenants --continue-on-error

# 4. Does at-risk bootstrap work cleanly?
python manage.py bootstrap_at_risk_registry

# 5. Translation coverage healthy?
python manage.py i18n_review_status
```

If steps 1, 2, 4 are clean, the deploy will not fail on migration or seed
issues. Step 3 may take a few minutes — re-run any specific seed cmd that
shows errors with `--verbosity=2`.
