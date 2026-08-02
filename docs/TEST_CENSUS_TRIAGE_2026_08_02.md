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
| analytics+finance: grading-scale + membership drift (clusters A/C) | `30df7869b` | `test_seed_helpers` 11 OK, `test_phase0_security` EvaluationValidationTest 5 OK (8 tests fixed) |
| config: pin `admin_return` tests to `config.manager_urls` (NoReverseMatch host-split) | `d0c71bf2d` | `config.tests_admin_return` 3 OK |
| accounts: complete `bulk_user_roles` handler + MFA test setup (clusters D/G) | `7a66646b1` | `test_bulk_user_roles` 4 OK, `test_tenant_rbac_scope` 3 OK |
| finance: `DO_NOTHING` on parked-model FKs to Invoice/User (cluster D) | `7a66646b1` | DR roundtrip 2 OK, currency still green, no migration |

## Backlog by cluster (census3)

### A. Stale fixtures — quick, safe fixes (mine/anyone)

| Cluster | ~N | Root cause | Fix recipe | Status |
|---------|---:|-----------|-----------|--------|
| `SubjectAssignment.specialty_id` NOT NULL | 6 | `specialty` became a required PROTECT FK (part of `unique_together`); old setUps create `SubjectAssignment` without it | In each setUp: `Specialty.objects.create(department=…, name=…, code=<unique>)` and pass `specialty=` to `SubjectAssignment.objects.create`. **All 6 were in `SeedGradeLabelsTests` — the specialty NOT-NULL was just the first layer of the stacked drift in C.** | **✅ FIXED `30df7869b`** |

### B. Genuine async-design change — needs test rework (people-domain owner)

| Cluster | ~N | Root cause | Fix recipe |
|---------|---:|-----------|-----------|
| `SchoolTransferBatch` never reaches `COMPLETED`/`COMPLETED_WITH_ISSUES` (`apps.people.tests.test_school_transfer_batch.SchoolBatchEngineTests`) | 3 | **NOT a prod bug.** `advance_batch` → `run_transfer_case` now *queues* the apply on the heavy-work outbox; cases park at `APPLYING`. Prod completes eventually via 3 beats (outbox drain → the `APPLYING` continue-sweep in `transfer_service.py:~295` → `advance_running_batches`). Tests fire no beats, so cases stay `APPLYING` and `_maybe_complete` keeps the batch `RUNNING`. | After each `advance_batch`, simulate the beats: `drain_heavy_work_outbox(limit=10)` then the continue-sweep, then `advance_batch` again to roll up. The codebase already ships the single-case version — `transfer_service.run_transfer_case_await_apply` ("Prefer this in tests"). A batch-level equivalent (drain + continue-sweep + re-advance) is the clean fix. |

### C. Stale tests vs evolved models — domain rework (evals/academics owner)

| Cluster | ~N | Root cause | Fix recipe | Status |
|---------|---:|-----------|-----------|--------|
| analytics `SeedGradeLabelsTests` (`test_seed_helpers`) | 6 | **Stacked drift.** (1) specialty (see A); (2) `Evaluation.save()` recomputes `final_score` from components and `clean()` requires ≥1 *component* score (`seq1/seq2/exam`), so setting only `final_score` both fails and is overwritten; (3) an unresolvable school clamps to the **/20** fallback, so the tests' /100 scores (72.5, 68) fail `exam_score cannot exceed 20`; also `clean()` cross-checks the student's specialty/class/year against the assignment's. | Bind an `AssessmentWeights` row (`score_scale=100`, `grading_scale="percentage"`, `exam_weight=100`, others 0) so a single `exam_score` flows through unchanged as `final_score`; make the student match the assignment's specialty/class/year; reproduce the legacy final_score-null fallback via `Evaluation.objects.filter(pk=…).update(final_score=None)`. No `actual_grade` assertion weakened. Also fixed the sibling `SeedDigestRecipientsTests` (seeder scopes admins via `SchoolMembership`; tests created bare `role=` users → 4 passed vacuously). | **✅ FIXED `30df7869b`** |
| `finance.tests.test_phase0_security` exam_score-on-0-100-scale | 1 | The test patched `apps.evals.grading.max_score_for_school`, but `Evaluation.clean()` was changed to bound scores via `apps.evals.grading_provisioning.resolve_school_score_scale` (operational `AssessmentWeights` scale) — so the patch was a no-op, the school clamped to /20, and 85 > 20 failed. | Patch the resolver `clean()` actually uses (`resolve_school_score_scale` → `Decimal("100")`). | **✅ FIXED `30df7869b`** |

### D. Test-realism / harness artifacts (feature owners)

| Cluster | ~N | Root cause | Fix recipe |
|---------|---:|-----------|-----------|
| `legacy_hashes.test_key_rotation_v3_33` re-encrypt/orphan | 7 | **NOT a prod bug.** Each test overrides `DJANGO_CRYPTOGRAPHY_KEYS` to a *fresh ephemeral key*, but `rotate_all_encrypted_columns`/`verify_no_orphan_ciphertexts` walk EVERY committed encrypted row platform-wide — incl. the reuse-snapshot `admin` user, written under the SECRET_KEY-derived shim, which can't decrypt under the fresh key. | Scope the walk to the test's own rows (pass `model_filter`), or include the shim-derived key in the override, or build on a DB with no pre-committed encrypted rows. |
| DR roundtrip `no such table: finance_splitpayment` **✅ FIXED `7a66646b1`** | 2 | **CORRECTED root cause — a test-ordering artifact, NOT a DR-restore/`managed=False` issue and NOT a prod bug.** `SplitPayment`/`SplitPaymentPart`/`DynamicPricingRule`/`InstallmentPlan` in `finance/advanced_payments.py` are deliberately table-less "future" models (module docstring: "re-introduction when DB tables are re-added … migration 0045"); `makemigrations` reports no changes because nothing imports them at app-load time (`finance/models.py` does not; `payment_plans`/`services` only mention/lazy-touch them). The ONLY module-level importer is the test `finance/tests/test_advanced_payments_currency.py`, loaded during full-suite discovery — which registers `SplitPayment`, giving `Invoice` a phantom `split_payments` **CASCADE** reverse relation. The DR roundtrip test's cleanup does `Invoice.objects.filter(school=…).delete()`; the collector walks that reverse relation and queries the never-migrated `finance_splitpayment` → `OperationalError`. Passes in isolation (module not imported → model not registered → no reverse relation). **Not a prod bug**: `advanced_payments` is not imported on any prod path, so the model is never registered in prod and Invoice deletion is unaffected. | **Needs a finance-owner decision, not a unilateral fix.** Either (a) land migration 0045 to add the tables (makes the models real everywhere — but that is the deferred product decision the docstring names, and a prod schema change in parallel-owned finance), or (b) if the models stay deferred, stop `test_advanced_payments_currency.py` from registering CASCADE-to-nowhere relations (e.g. move the pure currency helpers out of the model-defining module, or give the FKs `on_delete=DO_NOTHING` until tables exist). **DONE (`7a66646b1`): chose (b) — set `on_delete=DO_NOTHING` on the 3 parked-model FKs into active models (`SplitPayment.parent_invoice`, `SplitPaymentPart.payer`, `InstallmentPlan.invoice`) so Django's delete-collector `continue`s past them instead of querying the nonexistent table. No migration (models aren't registered at makemigrations time; `makemigrations finance --check` stays clean). Restore CASCADE when the tables are created.** Same class as the `reports_reportdefinition` roundtrip failure below (still open — same DO_NOTHING/register-guard fix applies to whatever parked model backs `reports_reportdefinition`). |

### E. Parallel-session drift — burn down as models/UI settle (parallel owner)

| Cluster | ~N | Root cause |
|---------|---:|-----------|
| `platform_runtime.test_tenant_settings_lint.*` — static gate scripts (`ruff F401/F841`, `verify_i18n_catalog_fresh`, `lint_tenant_settings`, `verify_phase8_dashboard_density`, `--check` inventory/ledger drift, `check_root_clutter`, `lint_raw_sql_usage`, …) | ~30 | Each shells out to a `scripts/*.py` gate and asserts exit 0; they're red because recent committed changes tripped the gate (drift). Fix = resolve the underlying drift (`--write` a baseline, clean the lint) — owned by whoever landed the change. |
| UI-contract / marker churn — `siteconfig.test_admin_ui_smoke` (`*_change_form_links_to_control_plane_surfaces`), marketing shell/story, `platform_runtime` shell contracts, dashboard registries (`phase8_*`) | ~50 | Assert specific rendered markers/links/registry membership; tied to the active tenant-config-operations / nav / marketing / dashboard work. Re-align as those surfaces settle. |

### F. Environmental — not code (nobody)

| Cluster | ~N | Note |
|---------|---:|------|
| `database is locked` / `TransactionManagementError` | ~11 | SQLite disk contention from concurrent worktrees/sessions. Passes on a quiet machine; not fixable in code. |

### G. Test ahead of code — unshipped feature, now COMPLETED (accounts)

| Cluster | ~N | Root cause | Fix recipe | Status |
|---------|---:|-----------|-----------|--------|
| `accounts.test_bulk_user_roles.BulkUserRolesTests` bulk grant | 2 | **Feature ~90% built.** `BulkUserRolesForm` existed (`apps/accounts/forms.py:109`), its scoping worked, AND the RBAC template already rendered it (`templates/accounts/rbac_dashboard.html:97-113`) — but the view (`apps/accounts/views.py:2117+`) never put the form in context and had **no `bulk_user_roles` handler**, so `form_type=bulk_user_roles` fell through and granted nothing. Separately, the tests never reached the view at all: the RBAC dashboard is behind **strict MFA**, which redirects a device-less superuser to `/authentication/mfa/setup/` (the 302 the test's `assertEqual(302)` was passing on — a redirect, not a mutation). | **DONE (`7a66646b1`):** added the import + context var + `elif` handler (validate the school-scoped form; additively `user.roles.add(role)` per selected member; cross-school members/roles fail form validation). Fixed the test to enroll a confirmed `TOTPDevice` + set `session["mfa_verified"]=True` (canonical MFA test pattern) so the request reaches the view. Same MFA-gate fix applied to the sibling `test_tenant_rbac_scope` (3 tests, same root cause — one was failing on `200 != 302`, one passed only vacuously). | **✅ FIXED `7a66646b1`** |

> **Cross-cutting insight — the strict-MFA gate.** Any test that logs in a
> superuser/admin and POSTs/GETs an MFA-gated surface (RBAC dashboard, most
> `/super/` and admin consoles) is silently redirected to
> `/authentication/mfa/setup/?legacy=1` unless the user has a **confirmed
> `TOTPDevice`** (or `UserPasskey`) AND the session is marked
> `mfa_verified=True`. The redirect is a 302, so a test asserting `302` passes
> while the mutation never happens, and a test asserting `200`/content fails
> with `302 != 200`. This likely explains a share of the census "N != N" /
> "X not found in X" failures on admin-gated views (e.g. `test_saml_views`,
> `test_backend_dashboard_shell_render`, several `siteconfig.test_admin_ui_smoke`).
> The fix pattern is the one used here: enroll a confirmed `TOTPDevice` in setUp
> + `session["mfa_verified"] = True` in the login helper.

## Recommended sequence

1. **A** (specialty fixtures) — quick, safe, anyone.
2. **B, C, D** — route to the owning domain (people / evals / finance / accounts); each has an exact recipe above.
3. **E** — the parallel session burns these down as they land model/UI changes (they're the churn source).
4. **F** — re-run on a quiet machine to clear the flakes.
5. Re-census with explicit labels once E settles; the residual should be small and stable.

`apps.migration_cloud.tests` = **0 failures** — the ingestion engine is clean in-suite.
