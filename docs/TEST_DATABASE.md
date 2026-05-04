# Test database (SQLite) — hygiene

**Purpose:** Reliable `manage.py test` and `scripts/pre_deploy_gate.sh` on developer machines (especially Windows) where a shared corrupt or locked `.django_test_dbs/default.sqlite3` caused migration errors (`table already exists`, etc.).

## Paths

| File | When used |
|------|-----------|
| `.django_test_dbs/default.sqlite3` | Default when `DJANGO_TEST_DB_FILE` unset (local `python manage.py test`) |
| `.django_test_dbs/pre_deploy_gate.sqlite3` | **pre_deploy_gate.sh** uses this path (and **`verify_section7_gate.py`** when `VERIFY_SECTION7_KEEPDB=1`). |
| §7 step 2 (no `--keepdb`) | **`verify_section7_gate.py`** sets **`DJANGO_TEST_DB_FILE`** to a **unique** `.django_test_dbs/section7_verify_<uuid>.sqlite3` per run (avoids **WinError 32** when Django replaces the test DB). `VERIFY_SECTION7_KEEPDB=1` → reuse `pre_deploy_gate.sqlite3`. `SECTION7_FIXED_TEST_DB=1` → `section7_verify.sqlite3`. `PRE_GATE_FRESH_TEST_DB=1` deletes the current `DJANGO_TEST_DB_FILE` before steps. Ephemeral files are removed by `python scripts/clean_django_test_dbs.py` (default removes all except `pre_deploy_gate.sqlite3`; `--all` removes everything). |
| `.django_test_dbs/pre_deploy_gate_run.sqlite3` | **Optional** alternate path if `pre_deploy_gate.sqlite3` is **locked** (Windows) or **half-migrated** (`table already exists` during `migrate_gate_test_db`). Set `export DJANGO_TEST_DB_FILE=.django_test_dbs/pre_deploy_gate_run.sqlite3` then run `python scripts/migrate_gate_test_db.py` once before the gate. |
| `.django_test_dbs/gate_verification_<label>.sqlite3` | **Optional** unique file per agent/CI run (e.g. `gate_verification_20260325.sqlite3`) when the default gate file stays locked despite `PRE_GATE_FRESH_TEST_DB=1`. Set `export DJANGO_TEST_DB_FILE=.django_test_dbs/gate_verification_<label>.sqlite3` for the full `pre_deploy_gate.sh` session. |
| `.django_test_dbs/wedge_super_premium_gates.sqlite3` | **§0.2.1.6** wedge gates: `bash scripts/run_wedge_super_premium_gates.sh` sets this path, runs `migrate_gate_test_db.py`, then `test_wedge_super_premium_phases` + `test_wedge_world_class_implemented` with `--keepdb` so Windows does not hit `[WinError 32]` on `.django_test_dbs/default.sqlite3`. |
| `.django_test_dbs/operator_phase1011_e2e.sqlite3` | **`python scripts/verify_operator_phase10_11_e2e.py`**: `migrate_gate_test_db.py` runs **first**; **`DJANGO_TEST_DB_FILE`** points here for **pytest** and UX so the bundle does not use shared `default.sqlite3` (reduces **database is locked** on Windows). **`verify_ux_completion.py`** uses **`DJANGO_UX_AUDIT_USE_GATE_DB=1`**. Override with **`--ux-db-file`**. |

**`verify_ux_completion.py` and the gate file:** With **`DJANGO_UX_AUDIT_USE_GATE_DB=1`**, SQLite’s default connection **`NAME`** is set to **`DJANGO_UX_AUDIT_DB_FILE`** or **`DJANGO_TEST_DB_FILE`** before `django.setup()`. **`pre_deploy_gate.sh`** exports this after **`migrate_gate_test_db.py`** so the UX audit uses **`pre_deploy_gate.sqlite3`**, not the dev working DB.

## §0.2.1.6 wedge super-premium gates (local)

1. **Scripts (no DB):** `python scripts/validate_wedge_world_class.py` and `python scripts/validate_wedge_super_premium_phases.py --phase all`.
2. **Tests:** `test_wedge_super_premium_phases` uses `SimpleTestCase` (no DB). `test_wedge_world_class_implemented` uses `TestCase` (needs migrations).
3. **Recommended one-shot:** `bash scripts/run_wedge_super_premium_gates.sh` (uses dedicated `DJANGO_TEST_DB_FILE` + `migrate_gate_test_db.py` + `--keepdb`).

## Fix corrupt or locked test DB

1. Close other processes using the DB (Cursor test runner, another terminal running tests).
2. Run:
   ```bash
   python scripts/clean_django_test_dbs.py --all
   ```
   Or delete `.django_test_dbs/*.sqlite3` manually.
3. Re-run tests **without** `--keepdb` once, or set:
   ```bash
   PRE_GATE_FRESH_TEST_DB=1 bash scripts/pre_deploy_gate.sh
   ```
   to force the gate to recreate `pre_deploy_gate.sqlite3`. If `rm` cannot delete the file (Windows lock), `pre_deploy_gate.sh` falls back to `.django_test_dbs/pre_deploy_gate_run.sqlite3` automatically when `PRE_GATE_FRESH_TEST_DB=1`.
4. **`migrate_gate_test_db` duration:** A full migrate of the gate SQLite file can take **10–15+ minutes** on a large schema; ensure CI/agents do not time out mid-migrate (symptoms: exit `127` or partial migrate + `table already exists`).

## CI

Fresh checkouts have no stale DB; gate uses `pre_deploy_gate.sqlite3` inside the workspace.

## Local scripts that hit the default DB (not the test runner)

`python scripts/verify_phase_b_execution.py` (and similar verify scripts) use **`DATABASES["default"]`**, not Django’s ephemeral test database. If you see missing-table errors (for example `platform_runtime_phase_b_domain_snapshot`), run **`python manage.py migrate --noinput`** on that default DB, or point `DATABASE_URL` / settings at a DB that has current migrations. **CI** already runs `migrate_gate_test_db.py` before the gate verify steps.

## Settings

Configured in `config/settings.py`:

- `TEST.NAME` for SQLite aliases from `DJANGO_TEST_DB_FILE` or `.django_test_dbs/{alias}.sqlite3`.
- `OPTIONS.timeout` (busy timeout) on SQLite to reduce flaky `database is locked` on Windows; during `manage.py test` / unittest, timeout is raised to **at least 90s** on SQLite aliases.
- When `test` is in `sys.argv`, SQLite engines use **`CONN_MAX_AGE = 0`** so persistent connections do not worsen locks with `--keepdb` / `DJANGO_TEST_DB_FILE`.

`scripts/migrate_gate_test_db.py` runs migrations **outside** `manage.py test`; it lowers `django.db.backends` log levels to **WARNING** so DEBUG builds do not emit full SQL (huge I/O and log bloat during long migrates).

## Marketing public story tests (`TestCase`)

`apps.schools.tests.test_marketing_public_story_reset` hits the database. If `.env` sets **`DATABASE_URL`** to Postgres that is unreachable or slow, Django may appear **stuck on “Creating test database…”** while connecting or migrating Postgres.

**Fix:** force local SQLite for the test runner (see `config/settings.py`):

```bash
export RMC_TEST_LOCAL_SQLITE=1        # ignore DATABASE_URL during tests
export RMC_SQLITE_TEST_MEMORY=1       # SQLite engine for unittest
export RMC_SQLITE_TEST_USE_MEMORY_NAME=1   # optional; TEST NAME uses shared-memory SQLite (fewer Windows file locks)
```

**Scripts:**

| Script | Purpose |
|--------|---------|
| `bash scripts/smoke_marketing_public_story.sh` | Fast smoke: `validate_marketing_urls --smoke` + JSON tests + nav contract (mostly DB-free). Sets the exports above by default. |
| `bash scripts/smoke_marketing_public_story_full.sh` | Runs **`test_marketing_public_story_reset`** with the same exports. First run migrates the full schema (long); use `DJANGO_TEST_DB_FILE=.django_test_dbs/marketing_public_story.sqlite3` and **`--keepdb`** on later runs to reuse the migrated file. |

**Pre-migrate the marketing SQLite file (optional, avoids migrate time inside `manage.py test`):** `RMC_TEST_LOCAL_SQLITE` only applies when **`test` is in `sys.argv`**, so `migrate_gate_test_db.py` still sees Postgres if `.env` sets `DATABASE_URL`. For a one-off schema build, clear Postgres for that process only, then migrate:

```bash
env DATABASE_URL= DJANGO_TEST_DB_FILE=.django_test_dbs/marketing_public_story.sqlite3 python scripts/migrate_gate_test_db.py
```

Then run the story tests with **`RMC_TEST_LOCAL_SQLITE=1`**, **`RMC_SQLITE_TEST_MEMORY=1`**, **`DJANGO_TEST_DB_FILE`** pointing at the same file, **`unset RMC_SQLITE_TEST_USE_MEMORY_NAME`** (so Django uses the file-backed `TEST` DB), and **`--keepdb`**.
