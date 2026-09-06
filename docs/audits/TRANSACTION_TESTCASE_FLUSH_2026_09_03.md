# TransactionTestCase flushes the whole database - audit 2026-09-03

**Status: SUPERSEDED 2026-09-06. Fixed systemically; read the note below before
acting on anything else in this file.**

The line this heading used to carry -- *CLOSED for 32 of 33 classes* -- was true when
it was written and was wrong by 2026-09-06. There were **fifteen** flushing classes
again, in twelve files, one of them a `LiveServerTestCase`
(`apps/compliance/tests/test_a11y_axe_smoke.py`) that a search for the obvious base
class does not find.

The remedy recorded below -- *order it last* -- was never enforceable. pytest runs in
COLLECTION order and does not reorder, so nothing made it happen; and because
`--keepdb` persists the truncation, the flush and the failure need not even be in the
same run, which is why bisecting the failing file never finds it.

Every flushing class now mixes in `apps/test_utils/seed_preserving.py::
RestoresSeedCatalogMixin`, which restores the post-migration snapshot in
`tearDownClass`. `scripts/scan_unrestored_flush_testcase.py` (zero baseline, no
allowlist) stops the sixteenth from arriving. Measured across all 13 converted files:
identical verdicts to the unfixed tree (1 failed / 107 passed / 6 skipped either way),
**+3.18s total**, and the seeded catalog survives (39 roles / 59 permissions) where it
was previously destroyed (1 / 0).

The per-class analysis below is still worth reading. Only its conclusion changed.

---

*(original 2026-09-03 status)* **CLOSED for 32 of 33 classes. One stays, with its
reason measured and recorded below.**

## What happens

Django's `TransactionTestCase` truncates **every table** at teardown (`_fixture_teardown`
calls `flush`) and does **not** roll it back. Against this repo's persisted keepdb SQLite
test database that damage is permanent: the migrations stay recorded as applied, so the
idempotent data-seed migrations never re-run, and every later test in that run *and every
later run reusing the file* sees an empty catalog.

`flush` re-emits `post_migrate`, which is why exactly one `AccessRole` survives -
`apps/accounts/superadmin_sync.on_post_migrate` recreates SUPERADMIN. Everything else
stays gone.

Granular RBAC resolves through `accounts_permission` / `accounts_accessrole`, so the
downstream symptom is unrelated suites returning **403** and looking like permission
regressions in code that is fine.

## Measured, not argued

A/B on `apps/apicenter/tests/test_api_center_open_and_usable.py`, same code, same
starting database, one arm each:

| table | `TestCase` | `TransactionTestCase` |
|---|---:|---:|
| `accounts_permission` | 46 | **0** |
| `accounts_accessrole` | 27 | **1** |
| `siteconfig_themepack` | 5 | **0** |

**Both arms reported `5 passed`.** The damage never appears in a test result. Do not look
for a red test - look at the row counts.

## Fixed

`ApiCenterOpenAndUsableTests` -> `TestCase` (commit `dedd0e6f7`). It needed no transaction
semantics; it arrived as a `TransactionTestCase` in the bulk "Ship v3.33 platform wave"
commit, so the choice was never reasoned.

## Reviewed: 33 classes, 32 converted, 1 stays

Every class was reviewed individually and verified by A/B against an identical
seeded database -- **each module run in isolation with its own fresh copy**,
because these are precisely the classes that flush, so a shared run would let
module 1 decide module 27's verdict.

| pass | modules | green | red |
|---|---:|---:|---:|
| before conversion | 28 | 20 | 8 |
| after conversion  | 28 | 20 | 8 |

The 8 reds are pre-existing and unrelated; they kept **identical pass/fail
counts**, not merely identical exit codes -- a new failure hiding inside an
already-red module would have changed the count.

### The one that stays: `MamaNoviFullBundleTests`

`apps/migration_cloud/tests/test_gilead_ingest_ui_slice_2026_09_02.py`.

It drives a real bundle apply, and `apps/migration_cloud/orchestrator.py` runs
its waves in a `ThreadPoolExecutor` (spawned ~line 576, collected ~588). Under
`TestCase` the outer test holds an open transaction on its connection while the
worker threads open their own, and `_create_audit_run` dies with:

```
sqlite3.OperationalError: database is locked
```

Measured: converted -> that failure; reverted -> 6 passed. **This module still
flushes the seeded catalog at teardown, so order it last.** The other two
classes in the same file convert cleanly and did.

### Two traps worth keeping

**The justifier heuristic cannot see the code under test.** This file has no
`threading` import -- the threads are in the orchestrator it calls. A file-level
grep will always miss that shape, which is why each class needed its own run
rather than a scan.

**Converting a class must always guarantee the new base is importable.** The
first cut only rewrote the import when `TransactionTestCase` had no remaining
use -- and a *docstring* mention counted as a use, so
`test_rollback_completeness_2026_08_15.py` got a converted class with no
`TestCase` import and failed collection with `NameError`. That looked exactly
like a genuine transaction-semantics requirement and was not one; with the
import fixed it passes 2/2. Removing the old name is the optional half.

## The systemic fix, and why it was NOT applied

`flush` re-emits `post_migrate`, and this repo already exploits that for exactly one row.
Moving the rest of the catalog seeding into an idempotent `post_migrate` receiver would
make every flush self-heal, which is what would let the one remaining class stop
matting -- it cannot be converted, so only a self-healing seed removes its blast
radius.

It is deliberately not attempted here. Re-seeding this catalog mid-investigation
previously turned 0 failures into **2** in the grade-approval cluster, because some tests
were passing only because permission was denied early - granting it changed their path.
The change also runs on every production `migrate`. That blast radius is an owner's
decision, not a drive-by fix.

## Reproducing the measurement

1. Build a test DB, then record `SELECT COUNT(*)` for `accounts_permission`,
   `accounts_accessrole`, `siteconfig_themepack`.
2. Copy the sqlite file aside - the run is destructive.
3. Run any module containing one of the classes above with `PYTEST_KEEPDB=1`.
4. Re-read the counts. Restore the copy.

Until this is closed, order any `TransactionTestCase` module **last** on the pytest
command line so everything before it runs against seeded data.
