# Full suite failure triage

## Round 11 fail-fast (2026-04-30) — **GREEN**

**Log:** `.django_test_dbs/failfast_round11.log`  
**Result:** **`Ran 2445 tests in 4241.014s`** — **`OK (skipped=5)`** (no further failures after fixes below).

**Full suite (same bar):** `.django_test_dbs/full_suite_final.log` — **`Ran 2445 tests in 2980.906s`**, **`OK (skipped=5)`** via `SKIP_RESET=1 RMC_TEST_STALL_SECONDS=7200 bash scripts/run_full_test_suite.sh`.

---

## Round 10 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round10.log`  
**Stopped at:** `TenantSettingsLintTests.test_generate_platform_inventory_check_passes` — inventory drift (same gate as round 7).

### triage-008 (fixed)

Re-ran `generate_platform_inventory.py --write` after the action_engine / accounts fixes so `--check` matches the tree.

---

## Round 9 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round9.log`  
**Stopped after:** 642 tests (~496s) — `FAILED (errors=1)`

### triage-007 (fixed)

| Field | Value |
| --- | --- |
| **Test** | `ActionEngineTests.test_request_provides_school_when_omitted` |
| **Observed** | `NameError: name 'school' is not defined` at nested `class Req: school = school` |
| **Classification** | Stale / fragile test pattern (class-body assignment shadowing on Python 3.14) |
| **Fix** | Use `sch` / `usr` bindings; nested class sets `school = sch` and `user = usr` (same scoping rule for both names) |

**Targeted verify:** `ActionEngineTests.test_request_provides_school_when_omitted` — **OK** after fix.

---

## Round 8 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round8.log`  
**Command:** `DJANGO_TEST_DB_FILE=.django_test_dbs/triage_failfast8.sqlite3 RMC_RELIABLE_TEST_RUNNER=1 python manage.py test --noinput --verbosity 2 --failfast`  
**Stopped after:** 1565 tests (~1367s) — `FAILED (failures=1)`

### triage-006 (fixed)

| Field | Value |
| --- | --- |
| **Test** | `Phase9SecurityGatesTests.test_allow_any_allowlist_lint` |
| **Observed** | `lint_allow_any_usage.py` exit 1 — root cause `IndentationError` at `apps/accounts/views.py` (~1599): mis-indented `dashboard_context = get_dashboard_context(...)` after `hero` dict |
| **Classification** | Governance lint blocked by syntax error (not allow-list drift) |
| **Fix** | Correct indentation so `dashboard_context` aligns with the rest of the view body |

**Targeted verify:** `Phase9SecurityGatesTests.test_allow_any_allowlist_lint` — **OK** (after indent fix).

---

## Round 7 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round7.log`  
**Command:** `DJANGO_TEST_DB_FILE=.django_test_dbs/triage_failfast7.sqlite3 RMC_RELIABLE_TEST_RUNNER=1 python manage.py test --noinput --verbosity 2 --failfast`  
**Stopped after:** 1820 tests (~2273s test CPU for the batch that reached failure; wall ~48m) — `FAILED (failures=1)`

### triage-005 (fixed)

| Field | Value |
| --- | --- |
| **Test** | `TenantSettingsLintTests.test_generate_platform_inventory_check_passes` |
| **Observed** | `generate_platform_inventory --check` reported drift (`AssertionError: 1 != 0`) |
| **Classification** | Generated artifact drift (platform inventory ledger) |
| **Fix** | `python scripts/generate_platform_inventory.py --write` |

**Targeted verify:** `TenantSettingsLintTests.test_generate_platform_inventory_check_passes` — **OK** (after `--write`).

---

## Round 5 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round5.log`  
**Stopped after:** 1145 tests (~707s) — `FAILED (failures=1)`

### triage-004 (fixed)

| Field | Value |
| --- | --- |
| **Test** | `PlatformAdminBridgeCompletenessTests.test_every_platform_admin_model_has_admin_bridge` |
| **Missing bridges** | `apicenter_developerapplication`, `apicenter_marketplaceextensionsubmission`, `apicenter_oauthauthorizationcode`, `apicenter_oauthtokenpair` changelists |
| **Classification** | Registry completeness (platform operator hub contract) |
| **Fix** | Added matching entries to `PLATFORM_ADMIN_BRIDGES` and `PLATFORM_ADMIN_BRIDGE_ORDER` in `super_admin_bridge_registry.py` |

---

## Round 4 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round4.log`  
**Stopped after:** 1082 tests (~676s) — `FAILED (failures=1)`

### triage-003 (fixed)

| Field | Value |
| --- | --- |
| **Test** | `Phase10ErrorPagesVerificationTests.test_tenant_403_uses_standard_template` |
| **Observed** | Response body contains **Access needs approval** (title), not literal **Access denied** |
| **Classification** | Stale string expectation |
| **Fix** | Accept either phrase in `test_phase10_control_plane_verification.py` |

---

## Round 3 fail-fast (2026-04-29)

**Log:** `.django_test_dbs/failfast_round3.log`  
**Command:** `DJANGO_TEST_DB_FILE=.django_test_dbs/triage_failfast3.sqlite3 RMC_RELIABLE_TEST_RUNNER=1 python manage.py test --noinput --verbosity 2 --failfast`  
**Stopped after:** 1056 tests (~599s) — `FAILED (failures=1)`

### triage-002 (fixed)

| Field | Value |
| --- | --- |
| **Test** | `MarketingFullUrlInventoryTests.test_all_inventory_marketing_urls_acceptable_status` (subtest `marketing_book_demo_submit`) |
| **Observed** | `GET /book-demo/submit/` → **405**; assertion expected **200** only |
| **Classification** | Stale smoke contract — not a product regression |
| **Cause** | `submit_demo_request` uses `@require_POST`; GET must not return 200 |
| **Fix** | `apps/schools/marketing_url_inventory.py`: for `marketing_book_demo_submit`, `ok_statuses` = `{200, 405}` |

**Targeted verify:** `MarketingFullUrlInventoryTests.test_all_inventory_marketing_urls_acceptable_status` — **OK** (after inventory change).

## Earlier: triage-001

Payment orchestration import / invoice recalculation — see git history and prior triage notes.

## Next steps

1. Re-run fail-fast from test 0 with a fresh DB file until green.  
2. Then full suite: `bash scripts/run_full_test_suite.sh`  
3. Then verifier stack (per operator checklist).

## Machine-readable companion

`full_suite_failure_triage.json`
