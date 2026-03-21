# Test database (SQLite) — hygiene

**Purpose:** Reliable `manage.py test` and `scripts/pre_deploy_gate.sh` on developer machines (especially Windows) where a shared corrupt or locked `.django_test_dbs/default.sqlite3` caused migration errors (`table already exists`, etc.).

## Paths

| File | When used |
|------|-----------|
| `.django_test_dbs/default.sqlite3` | Default when `DJANGO_TEST_DB_FILE` unset (local `python manage.py test`) |
| `.django_test_dbs/pre_deploy_gate.sqlite3` | **pre_deploy_gate.sh** and **`python scripts/verify_section7_gate.py`** (default when `DJANGO_TEST_DB_FILE` is unset) use this path so the gate and §7 catalog tests do not compete with IDE/test runners holding `default.sqlite3`. |
| `.django_test_dbs/pre_deploy_gate_run.sqlite3` | **Optional** alternate path if `pre_deploy_gate.sqlite3` is **locked** (Windows) or **half-migrated** (`table already exists` during `migrate_gate_test_db`). Set `export DJANGO_TEST_DB_FILE=.django_test_dbs/pre_deploy_gate_run.sqlite3` then run `python scripts/migrate_gate_test_db.py` once before the gate. |

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
   to force the gate to recreate `pre_deploy_gate.sqlite3`.

## CI

Fresh checkouts have no stale DB; gate uses `pre_deploy_gate.sqlite3` inside the workspace.

## Settings

Configured in `config/settings.py`: `TEST.NAME` for SQLite aliases from `DJANGO_TEST_DB_FILE` or `.django_test_dbs/{alias}.sqlite3`.
