# RunMyCampus - agent execution contract

This repository is **not** a greenfield project. Use the **existing** enforcement layer as the primary control framework.

## Control framework (read before large edits)

| Artifact | Role |
| --- | --- |
| [docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) | Single execution source of truth; forward queue in section 11.4 |
| [docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) | Wave-by-wave implementation log |
| [docs/phase_checklists/](docs/phase_checklists/) | Phase checklists + gate crosswalk ([README](docs/phase_checklists/README.md)) |
| [docs/SITECONFIG_OWNERSHIP_MIGRATION.md](docs/SITECONFIG_OWNERSHIP_MIGRATION.md), [docs/site_settings_usage_inventory.md](docs/site_settings_usage_inventory.md) | SiteSettings / siteconfig ownership |
| `scripts/verify_*.py`, `scripts/lint_*.py` | Mechanical gates; `verify_phases_3_11_gates.py` bundles many |
| `scripts/generated/*.json`, `docs/generated/*` | Regenerated ledgers and inventories. Run writers when verifiers say stale |
| [`scripts/generate_system_closure_map.py`](scripts/generate_system_closure_map.py) | After section 11.4 **PARTIAL**/**NOT DONE**/**BLOCKED** edits: `python scripts/generate_system_closure_map.py --write` updates [`docs/generated/system_closure_map.json`](docs/generated/system_closure_map.json) |
| [`scripts/run_sqlite_memory_tests.py`](scripts/run_sqlite_memory_tests.py) | When `DATABASE_URL` is Postgres but no server is available, or Windows SQLite test DBs hang on teardown: `python scripts/run_sqlite_memory_tests.py <labels>` sets `RMC_SQLITE_TEST_MEMORY=1` and a unique `DJANGO_TEST_DB_FILE` per run. Optional: `RMC_SQLITE_TEST_USE_MEMORY_NAME=1` uses `:memory:` for the test DB name. |

## Autonomous slice loop (every deliverable)

1. **Inspect** - Scope files, routes, templates, and which verifier(s) apply.
2. **Map** - Phase checklist entry, SOT section 11.4 row if shipping a batch, generated artifacts touched.
3. **Implement** - Smallest diff; match existing patterns.
4. **Regenerate** - e.g. `scripts/build_phase8_security_ledger.py --write` when allowlists change; `generate_platform_inventory` when the gate requires it; `generate_system_closure_map.py --write` when section 11.4 partial-queue statuses change.
5. **Validate** - Narrow verifier first, then broader bundle (`verify_phases_3_11_gates.py` or release script per SOT).
6. **Remediate** - Fix failures; do not declare done from narrative alone.
7. **Record** - Autonomous log + checklist + section 11.4 when the slice closes.

## Slice selection (do not ask the user unless blocked)

Derive the next slice from, in order:

1. Failing or stale gates / generated artifacts / allowlist drift
2. SOT section 11.4 forward queue head and PATH action rows
3. Architecture gravity (singletons, shell fragmentation, public endpoints, raw SQL)
4. Operator UX / control plane / Studio OS / dashboards
5. Docs truth, legacy naming drift, contradictory claims

**Mechanical gate pass is not full product maturity.** After gates are green, continue with the next highest-value SOT or PATH slice until blocked or the queue has no next implementable row.

**Multi-batch rule (no early stop):** Stopping after a single shippable batch or clear handoff is **not allowed** when more **safely executable repo-contained** slices remain. After each green batch (code + verifiers + support docs as required), **automatically** select and execute the **next** highest-value slice from SOT **section 11.4** / **PATH** until a **true blocker** exists or the run has **exhausted** safely executable work.

**No pass-complete stop:** Do **not** end a run because a single autonomous pass is done, the next tranche would need a new section 11.4 row, the wave switched surface, or the next chunk is larger. If the next work is known and can be scoped, add the section 11.4 row (and PATH/autonomous support lines if required) yourself and continue in the same run.

## Cursor Cloud notes

### Project overview

RunMyCampus is a multi-tenant Django 5.x SaaS platform for schools with a Cameroon/Africa focus. It is a single Django project with apps under `apps/`, plus `emis/` and `payment/`.

### Tech stack

- **Python 3.12.3**, **Django 5.x**, SQLite for local development / PostgreSQL for production
- **Admin theme:** django-unfold
- **Key deps:** WeasyPrint, Celery, Redis, DRF, SimpleJWT

### Running the dev server

```bash
python3 manage.py runserver 0.0.0.0:8000
```

The app uses multi-tenant routing. Local URLs may use tenant paths or host-based routing depending on the environment:

- Login: `http://localhost:8000/t/demo-school/authentication/login/`
- Backend dashboard: `http://localhost:8000/t/demo-school/authentication/backend/`
- Django admin: `http://localhost:8000/admin/`

### Default local accounts

| Username | Password | Role |
| --- | --- | --- |
| admin | Sch00l_1234 | SUPERADMIN |
| teacher | Test1234 | TEACHER |
| parent | Test1234 | PARENT |

After a fresh migrate, run `python3 manage.py ensure_superuser --password Sch00l_1234 --no-input` if you need the known admin password.

### Database

Local development can use SQLite. If `.env.local` contains a Windows-style temp-path `DB_FILE` and you are on Linux/Cursor Cloud, override it with `DB_FILE=db_working.sqlite3`.

### Running tests and checks

```bash
python3 manage.py test apps.<app_name>.tests --verbosity=2 --no-input
python3 manage.py check
```

**Marketing public shell (runmycampus.com):** after editing files listed in `scripts/marketing_css_bundle_manifest.json`, rebuild bundles and verify:

```bash
npm run build:marketing-css
npm run verify:marketing
npm run audit:marketing
# Playwright theme matrix (Django on runmycampus.com:8000):
npm run test:e2e:marketing:theme
```

Use `python scripts/run_sqlite_memory_tests.py <labels>` when Postgres is configured but unavailable or when SQLite test DB teardown hangs on Windows.

**Abrupt-end / scroll-reveal sweep (Playwright):** `npm run sweep:abrupt-end:routes` regenerates `docs/generated/control_plane_sweep_routes.json` and `portal_tenant_sweep_routes.json`. With Django up on `VISUAL_QA_PORT` and `MAP manager.runmycampus.com 127.0.0.1`, run `npm run sweep:abrupt-end` (Git Bash) or `SWEEP_TIER=operator+admin node scripts/verify_platform_abrupt_end_sweep.mjs`. On Git Bash, `export MSYS_NO_PATHCONV=1` if you pass `SWEEP_PATHS` / `SWEEP_TENANT_PATHS` starting with `/`.

### Gotchas

- `collectstatic` can report duplicate static file warnings for admin JS files; django-unfold overrides make these non-blocking.
- WeasyPrint requires system libraries such as libpango, libcairo, and libgdk-pixbuf.
- Celery and Redis are optional for many local development paths, but production uses both.
- `python-json-logger` v4.x changed its API; related import warnings may be non-blocking.

## Parallelism

Partition by route family, app, or audit category. One coordinator reconciles and runs verifiers; avoid two agents editing the same hot files without ordering.

## Blockers only

Stop and ask only for missing secrets, irreversible external decisions, or ambiguity that cannot be resolved from the repo.
