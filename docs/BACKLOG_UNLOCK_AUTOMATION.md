# Backlog unlock automation

**Authority:** Extends [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1.1 without duplicating strategy docs.

## Purpose

- **Registry:** `apps/platform_runtime/backlog_unlock_registry.json` lists backlog themes with **verifiable criteria**:
  - **`script_exit_zero`** — run `python scripts/<name>.py` with optional `args` (same pattern as `pre_deploy_gate.sh`).
  - **`pytest_exit_zero`** — run `python -m pytest` with `targets` (list of paths) and optional `args` (default `-q --no-header`).
  - Plus **external** and **program (SOT PARTIAL)** rows that cannot auto-complete in git.
- **Evaluation:** `python manage.py evaluate_backlog_unlocks` runs criteria against the repo, classifies each item as `ready`, `waiting`, `ready_attention`, or `blocked_external`, and optionally **updates Django cache** and **emits** `backlog_dependency_met` platform events when an item moves off `waiting`.
- **Profiles:** Each registry row may list `"profiles": ["smoke", "full"]`. Rows **without** `profiles` run under **`full` only** (default). **`smoke`** is a smaller set for quick operator refresh; **`full`** is the complete matrix (CI / pre-deploy when `RUN_BACKLOG_UNLOCK_EVAL=1`). Cache keys are **per profile**: evaluation snapshot `backlog_unlock:eval:<profile>:v1`, status map `backlog_unlock:states:<profile>:v1`, **aging** `backlog_unlock:aging:<profile>:v1` (first-seen timestamps for SLA). Human-readable descriptions live under `evaluation_profiles` in the JSON and in the super UI when a snapshot exists.
- **SLA (time in column):** Registry root object **`sla`** sets `default_max_days_in_waiting` and `default_max_days_in_ready_attention` (calendar days). Optional per-item **`max_days_in_waiting`** / **`max_days_in_ready_attention`** override defaults. Counts advance only when **`CACHES`** is **persistent** across evaluations (Redis in staging/prod, or repeated Refresh on the same instance). Ephemeral CI jobs reset aging each run unless you add external state. **`--fail-on-sla-breach`** exits non-zero when any in-scope item exceeds its limit — use on a host with persistent cache or in custom automation.
- **In-product:** **Super → Backlog unlock center** (`/super/backlog-unlock-center/`) shows the latest cached snapshot and recent `PlatformEventLog` rows so operators are not “in the dark” after CI or merges. Use **`?profile=smoke`** or **`?profile=full`** (or the form on that page) to switch which snapshot you view or refresh. **Refresh evaluation** runs `evaluate_backlog_unlocks` with **`--update-cache --emit-events`** for the selected profile (same transition logging as pre-deploy/Celery, scoped to that profile’s rows).

## Commands

```bash
# Summary only — full matrix (default; slow)
python manage.py evaluate_backlog_unlocks --timeout 420

# Fast smoke subset (core lints + pillar + inventory + selected gates; see registry)
python manage.py evaluate_backlog_unlocks --profile smoke --timeout 420

# Populate cache for the super UI + optional transition events
python manage.py evaluate_backlog_unlocks --profile full --update-cache --emit-events --timeout 420

# Machine-readable
python manage.py evaluate_backlog_unlocks --json --quiet

# Strict: fail the process if SLA exceeded (persistent cache required for meaningful ages)
python manage.py evaluate_backlog_unlocks --profile full --update-cache --emit-events --fail-on-sla-breach
```

## CI / pre-deploy

**GitHub Actions `smoke.yml`:** On **push to `main`** only, sets **`RUN_BACKLOG_UNLOCK_EVAL=1`** for the pre-deploy step and raises the step timeout so the backlog matrix runs after the rest of the gate passes. **Pull requests** skip the backlog eval block to limit wall time.

**Nightly:** `.github/workflows/backlog_unlock_nightly.yml` runs the **full** matrix (with gate SQLite migrated for pytest rows) and uploads **`backlog_eval_snapshot.json`** as an artifact for review.

At the end of `scripts/pre_deploy_gate.sh`, when `RUN_BACKLOG_UNLOCK_EVAL=1`:

- Runs `evaluate_backlog_unlocks --profile full --update-cache --emit-events --quiet` so production/staging (if the gate runs there) refreshes the **full** operator snapshot after a green gate.

Local default remains **off** unless you export the variable.

## Celery Beat (optional)

Set **`ENABLE_BACKLOG_UNLOCK_BEAT=1`** to register a **daily** task `platform_runtime.backlog_unlock_eval_and_cache` (see `config/settings.py` after `CELERY_BEAT_SCHEDULE`). Requires a running worker + beat; task is heavy. The task uses **`--update-cache --emit-events`**, keeping SLA aging and `backlog_dependency_met` aligned on long-lived deployments.

**Strict SLA on beat / pre-deploy (persistent cache only):** set **`BACKLOG_UNLOCK_FAIL_ON_SLA_BREACH=1`** so the Celery task (and, when combined with **`RUN_BACKLOG_UNLOCK_EVAL=1`**, `pre_deploy_gate.sh`) passes **`--fail-on-sla-breach`** to `evaluate_backlog_unlocks`. Use on staging/production where Redis (or equivalent) retains `backlog_unlock:aging:*` between runs — not on fresh CI workers unless you add separate state persistence.

## Extending the registry

1. Add or adjust rows in `backlog_unlock_registry.json` (keep `id` stable for transition detection). Add **`"profiles": ["smoke", "full"]`** only for criteria you want in the fast path; leave other rows **full-only** to avoid duplicating heavy Phase 6/7 bundles or `verify_phases_3_11` in smoke.
2. Prefer **script_exit_zero** for anything already invoked from `pre_deploy_gate.sh`; use **pytest_exit_zero** for focused test modules (bridge manifest, tenant lint bundle, runtime contract slice).
3. Set **`timeout_seconds`** per criterion for slow bundles (e.g. `verify_phases_3_11_gates.py` may need 900s).
4. **`verify_ux_completion.py`** uses Django and the **configured database** — treat like other production-touching audits: run in CI/staging or with the same DB discipline as `pre_deploy_gate.sh`, not ad hoc on production from the super “Refresh” button unless intentional.
5. Do **not** add overlapping markdown roadmaps; link existing docs in `doc_href` / `sot_refs`.
6. When a theme is **fully done** in code (no longer a meaningful gate), **delete** its registry row (or replace criteria with a no-op only if you must keep the id for history — prefer removal and stable docs). Shrinking the matrix is part of keeping the backlog honest.

## Related docs

- [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) — external-only open items
- [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) — narrative closure table
- [SITESETTINGS_GET_SOLO_ALLOWLIST.md](SITESETTINGS_GET_SOLO_ALLOWLIST.md) — SiteSettings choke point
