# Full-suite test census — triage & burndown map (2026-08-02)

Fresh whole-platform census after the Migration Cloud + harness work. This is a
**burndown map**: every failing cluster with its root cause, a concrete fix
recipe, and who owns it. CI runs no tests (Actions budget), so `manage.py test`
locally is the only gate — this doc is the shared worklist for getting there.

## How to reproduce the census

```
# 🚨 bare `manage.py test` (no labels) CRASHES in ~50s during discovery on
# emis/ (it has BOTH tests.py AND a tests/ package — a name collision).
# ALWAYS pass explicit labels:
DEBUG=0 SECRET_KEY="ci-django-tests-not-for-production-use-64chars___________________________" \
RMC_RELIABLE_TEST_RUNNER=1 DJANGO_TEST_DB_FILE="$PWD/.django_test_dbs/<lane>.sqlite3" \
../../.venv/Scripts/python.exe manage.py test apps config services payment.tests emis.tests \
  --settings=config.settings --keepdb --noinput -v1
```

Seed a clean lane from `.django_test_dbs/fast_reuse.sqlite3` (`--keepdb` then
applies any migration delta). Serial only — SQLite + `--parallel` worker-cloning
produces false `database is locked` failures.

## Headline

| Run | Tests | Non-passing | Pass rate |
|-----|------:|------------:|----------:|
| census2 (07-31, pre-fixes) | 15,988 | 232 | ~98.5% |
| census3 (08-01, shim live) | 16,209 | 245 (209 fail + 36 err) | ~98.5% |

The count is roughly flat, **not** because nothing improved but because the
dominant census2 signal (`'DatabaseWrapper' has no attribute 'tenant'`, 168 log
lines) was **caught-exception log noise, not failing tests** — it's now 0. The
real backlog is ~238 unique failing tests, and the population grew +221 from
active parallel-session commits between runs.

## Fixed already

| Fix | Commit | Result |
|-----|--------|--------|
| Harness: `schema_context` no-op under `USE_DJANGO_TENANTS=0` (`ReliableDiscoverRunner` installs a single-schema tenant shim) | `61a4a0c7c` | `connection.tenant` cluster → 0; +must-fire test |
| MC: `hasattr(connection,"set_schema")` guard on 4 `schema_context` call sites | `207b117d5` | verification/guardrails/companion_receiver/shadow |
| finance: receipt-upload fixtures use valid PNG magic bytes | `67397b627` | `test_receipt_upload_flow` 4 OK |

## Backlog by cluster (census3)

### A. Stale fixtures — quick, safe fixes (mine/anyone)

| Cluster | ~N | Root cause | Fix recipe |
|---------|---:|-----------|-----------|
| `SubjectAssignment.specialty_id` NOT NULL | 6 | `specialty` became a required PROTECT FK (part of `unique_together`); old setUps create `SubjectAssignment` without it | In each setUp: `Specialty.objects.create(school=…, department=…, name=…, code=<unique>)` and pass `specialty=` to `SubjectAssignment.objects.create`. **⚠️ `apps.analytics.tests.test_seed_helpers.SeedGradeLabelsTests` also has stacked drift — see C.** |

### B. Genuine async-design change — needs test rework (people-domain owner)

| Cluster | ~N | Root cause | Fix recipe |
|---------|---:|-----------|-----------|
| `SchoolTransferBatch` never reaches `COMPLETED`/`COMPLETED_WITH_ISSUES` (`apps.people.tests.test_school_transfer_batch.SchoolBatchEngineTests`) | 3 | **NOT a prod bug.** `advance_batch` → `run_transfer_case` now *queues* the apply on the heavy-work outbox; cases park at `APPLYING`. Prod completes eventually via 3 beats (outbox drain → the `APPLYING` continue-sweep in `transfer_service.py:~295` → `advance_running_batches`). Tests fire no beats, so cases stay `APPLYING` and `_maybe_complete` keeps the batch `RUNNING`. | After each `advance_batch`, simulate the beats: `drain_heavy_work_outbox(limit=10)` then the continue-sweep, then `advance_batch` again to roll up. The codebase already ships the single-case version — `transfer_service.run_transfer_case_await_apply` ("Prefer this in tests"). A batch-level equivalent (drain + continue-sweep + re-advance) is the clean fix. |

### C. Stale tests vs evolved models — domain rework (evals/academics owner)

| Cluster | ~N | Root cause | Fix recipe |
|---------|---:|-----------|-----------|
| analytics `SeedGradeLabelsTests` (`test_seed_helpers`) | 6 | **Stacked drift.** (1) specialty (see A); (2) `Evaluation.save()` now enforces "at least one score" over component fields (`seq1/seq2/exam`), so setting only `final_score` fails; (3) school resolves to a **/20** scale, so the tests' /100 scores (72.5, 68) fail `exam_score cannot exceed 20`. | Rework to set component scores within the school's actual scale (or configure a `percentage`/100 grading scale for the test school via the evals grading-config), and create the no-score fixture via `.update(...)` to bypass `save()` validation. Do **not** weaken the `actual_grade` assertions. Needs evals-domain knowledge of the weighted `final_score` computation. |
| `finance.tests.test_phase0_security` exam_score-on-0-100-scale | 1 | Same /20-vs-/100 scale drift | Align test to the school's grading scale. |

### D. Test-realism / harness artifacts (feature owners)

| Cluster | ~N | Root cause | Fix recipe |
|---------|---:|-----------|-----------|
| `legacy_hashes.test_key_rotation_v3_33` re-encrypt/orphan | 7 | **NOT a prod bug.** Each test overrides `DJANGO_CRYPTOGRAPHY_KEYS` to a *fresh ephemeral key*, but `rotate_all_encrypted_columns`/`verify_no_orphan_ciphertexts` walk EVERY committed encrypted row platform-wide — incl. the reuse-snapshot `admin` user, written under the SECRET_KEY-derived shim, which can't decrypt under the fresh key. | Scope the walk to the test's own rows (pass `model_filter`), or include the shim-derived key in the override, or build on a DB with no pre-committed encrypted rows. |
| DR restore `no such table: finance_splitpayment` | 2 | `SplitPayment`/`SplitPaymentPart`/`DynamicPricingRule`/`InstallmentPlan` in `finance/advanced_payments.py` — `makemigrations` reports no changes, so they're likely `managed=False` (no table created). DR restore iterates all tables and hits the missing one. | Confirm `managed=False`; have the DR snapshot/restore skip unmanaged tables, or provide the table in the test target schema. |

### E. Parallel-session drift — burn down as models/UI settle (parallel owner)

| Cluster | ~N | Root cause |
|---------|---:|-----------|
| `platform_runtime.test_tenant_settings_lint.*` — static gate scripts (`ruff F401/F841`, `verify_i18n_catalog_fresh`, `lint_tenant_settings`, `verify_phase8_dashboard_density`, `--check` inventory/ledger drift, `check_root_clutter`, `lint_raw_sql_usage`, …) | ~30 | Each shells out to a `scripts/*.py` gate and asserts exit 0; they're red because recent committed changes tripped the gate (drift). Fix = resolve the underlying drift (`--write` a baseline, clean the lint) — owned by whoever landed the change. |
| UI-contract / marker churn — `siteconfig.test_admin_ui_smoke` (`*_change_form_links_to_control_plane_surfaces`), marketing shell/story, `platform_runtime` shell contracts, dashboard registries (`phase8_*`) | ~50 | Assert specific rendered markers/links/registry membership; tied to the active tenant-config-operations / nav / marketing / dashboard work. Re-align as those surfaces settle. |

### F. Environmental — not code (nobody)

| Cluster | ~N | Note |
|---------|---:|------|
| `database is locked` / `TransactionManagementError` | ~11 | SQLite disk contention from concurrent worktrees/sessions. Passes on a quiet machine; not fixable in code. |

## Recommended sequence

1. **A** (specialty fixtures) — quick, safe, anyone.
2. **B, C, D** — route to the owning domain (people / evals / finance / accounts); each has an exact recipe above.
3. **E** — the parallel session burns these down as they land model/UI changes (they're the churn source).
4. **F** — re-run on a quiet machine to clear the flakes.
5. Re-census with explicit labels once E settles; the residual should be small and stable.

`apps.migration_cloud.tests` = **0 failures** — the ingestion engine is clean in-suite.
