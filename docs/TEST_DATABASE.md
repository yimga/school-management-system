# Test database (SQLite) — hygiene

**Purpose:** Reliable `manage.py test` and `scripts/pre_deploy_gate.sh` on developer machines (especially Windows) where a shared corrupt or locked `.django_test_dbs/default.sqlite3` caused migration errors (`table already exists`, etc.).

## Paths

| File | When used |
|------|-----------|
| `.django_test_dbs/default.sqlite3` | Default when `DJANGO_TEST_DB_FILE` unset (local `python manage.py test`) |
| `.django_test_dbs/pre_deploy_gate.sqlite3` | **pre_deploy_gate.sh** and **`python scripts/verify_section7_gate.py`** (default when `DJANGO_TEST_DB_FILE` is unset) use this path so the gate and §7 catalog tests do not compete with IDE/test runners holding `default.sqlite3`. |
| §7 step 2 | **`verify_section7_gate.py`** runs marketplace minimums **without** `--keepdb` by default (rebuilds test DB — slower, avoids corrupt/half-migrated SQLite). For faster reruns when the DB is healthy: `VERIFY_SECTION7_KEEPDB=1`. To delete the gate file first (same as pre-deploy): `PRE_GATE_FRESH_TEST_DB=1`. |
| `.django_test_dbs/pre_deploy_gate_run.sqlite3` | **Optional** alternate path if `pre_deploy_gate.sqlite3` is **locked** (Windows) or **half-migrated** (`table already exists` during `migrate_gate_test_db`). Set `export DJANGO_TEST_DB_FILE=.django_test_dbs/pre_deploy_gate_run.sqlite3` then run `python scripts/migrate_gate_test_db.py` once before the gate. |
| `.django_test_dbs/wedge_super_premium_gates.sqlite3` | **§0.2.1.6** wedge gates: `bash scripts/run_wedge_super_premium_gates.sh` sets this path, runs `migrate_gate_test_db.py`, then `test_wedge_super_premium_phases` + `test_wedge_world_class_implemented` with `--keepdb` so Windows does not hit `[WinError 32]` on `.django_test_dbs/default.sqlite3`. |

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

## Settings

Configured in `config/settings.py`: `TEST.NAME` for SQLite aliases from `DJANGO_TEST_DB_FILE` or `.django_test_dbs/{alias}.sqlite3`.
