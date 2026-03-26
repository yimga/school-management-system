# Release checklist (skeleton)

Use this for each release (tag or deploy to production). Expand steps as needed per wave.

**Launch status:** Platform is **not ready for launch yet**; we are still developing. The checklists below are prepared and approved so that when the platform is ready, release can proceed without redoing sign-off. Do not deploy to production until the team confirms the platform is launch-ready.

### Engineering vs each deploy (read this first)

- **Repo / §12 engineering program:** **MET** for the recorded sign-off (2026-03-17) per [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4. **Implementation for that bar is already in the codebase**; you are not “starting implementation” from this checklist—you are **verifying and shipping** a git revision.
- **New product work** (features, wedges, §11.4 depth): planned and built from the **SOT + BACKLOG**, then merged; this file does not replace that roadmap.
- **Each future production deploy:** **repeat** the runbook below (gates, staging, logs, sign-off). Treat that as **release operations**, independent of whether the business has declared public go-live.

### Each future production deploy (repeat this runbook)

Complete for **every** cut to production (or RC), even when the checkboxes in Pre-release / Build / Deploy / Post-release above still show the historical 2026-03-17 approvals.

| Step | Action | Primary doc / command |
|------|--------|------------------------|
| 1 | **Merge bar** | `bash scripts/pre_deploy_gate.sh` (use `SKIP_VISUAL_QA=1` only when agreed for that environment). |
| 2 | **Record gate output** | `bash scripts/record_pre_deploy_gate_output.sh` → commit `docs/generated/pre_deploy_gate_run.txt` for this cut. |
| 3 | **Platform inventory** | When catalog changes: `python scripts/generate_platform_inventory.py --write`; commit generated JSON if your train requires it (SOT §11.4). |
| 4 | **Migrations** | Apply **staging first**, then production, per your predeploy; align with Step 13 / SUBTRACTIVE notes. |
| 5 | **Launch 10-point (staging)** | [launch_studio_checklist.md](launch_studio_checklist.md) §4 — run all 10 items; **append** a row to the staging log table when policy needs a fresh audit trail. |
| 6 | **Phase H + BR-13** | Automated: `bash scripts/run_phase_h_verification.sh` (or `PHASE_H_SKIP_LIVE=1` as documented in SOT §11.4). Manual: [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) / Phase H checklist for human sign-off. |
| 7 | **Security review log** | Append a row to [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) (public endpoints, AI gateway, secrets) for this tag/release. |
| 8 | **Build / deploy / smoke** | Sections **Build**, **Deploy**, **Post-release** below on the target host. |
| 8b | **Collabora/WOPI smoke (when enabled)** | `bash scripts/release/verify_collabora_wopi.sh` + [execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md](execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md) + `.github/workflows/collabora-wopi-smoke.yml` manual run. |
| 8c | **Render env contract (when deploying on Render)** | `python scripts/verify_env_contract.py --profile render-core` and, if Collabora enabled, `--profile render-collabora`. Reference [execution/RENDER_ENV_OPERATIONS.md](execution/RENDER_ENV_OPERATIONS.md). |
| 9 | **Release sign-off row** | **Append** a new row under **Release sign-off** (copy the 2026-03-17 row as a template; set **Date**, **Release / tag**, **Checked by**). |

**Index:** All gate commands are also summarized in [VERIFICATION_GATES_INDEX.md](VERIFICATION_GATES_INDEX.md).

### Verification run log (append-only)

| Run date (UTC) | Scope | 1 Gate | 2 Record | 3 Inventory | 4 Migrate | 5 Staging 10-pt | 6 Phase H | 7 Security log | 8 Deploy/smoke | 9 Sign-off row |
|----------------|-------|--------|----------|-------------|-----------|-----------------|-----------|----------------|----------------|----------------|
| 2026-03-25 | **Local repo train** (not staging/prod) | **PASS** — `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` with `DJANGO_TEST_DB_FILE=.django_test_dbs/gate_verification_20260325.sqlite3`; prerequisite `python manage.py sync_i18n_catalog --compile` (i18n drift) | **DONE** — `docs/generated/pre_deploy_gate_run.txt` | **PASS** — `generate_platform_inventory.py --check` (gate also `--write` post-steps) | **PASS** — `makemigrations --check --dry-run`; **OPS:** apply migrations on staging → prod per host | **OPS / N/A** — run [launch_studio_checklist.md](launch_studio_checklist.md) §4 on staging before a real prod cut | **PASS** — `PHASE_H_SKIP_LIVE=1 bash scripts/run_phase_h_verification.sh` (smoke + static + reliable subset) | **DONE** — row appended [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) 2026-03-25 | **OPS** | This row |

**Before production:** Re-run the full runbook on your staging host, set `SKIP_VISUAL_QA=0` (or run `scripts/run_visual_qa.sh`) when Playwright is available, and append a new line above with a distinct **Scope** (e.g. `staging-RC-…` / `prod-…`).

**2026-03-25 follow-up (same local train, after gate with `SKIP_VISUAL_QA=1`):**

- **Playwright UX:** `bash scripts/run_visual_qa.sh` → **PASS** (7 passed, 2 skipped — SQLite dev DB without Postgres tenant domain; tenant-host portal slice skipped by design).
- **Phases 3–11 bundle:** `python scripts/verify_phases_3_11_gates.py` → **PASS**.
- **UI wiring + Phase 3/4 surfaces:** `python scripts/verify_ui_wiring_audit.py` + `python scripts/audit_phase3_phase4_surfaces.py` → **PASS**.
- **Operator Phase 10/11 E2E:** `python scripts/verify_operator_phase10_11_e2e.py --ux-db-file .django_test_dbs/progress_phase1011.sqlite3` → **PASS** (~5.5 min).

## Pre-release

- [x] **Branch / version:** Release branch or tag confirmed for this release. *(Approved 2026-03-17.)*
- [x] **Changelog:** CHANGELOG or release notes updated with user-visible changes; release sign-off covers this release. *(Approved 2026-03-17.)*
- [x] **Subtractive cleanup (NEXT_50 step 50):** Release notes include "Subtractive cleanup" per [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md). *(Approved 2026-03-17; see doc.)*
- [x] **Launch Studio staging (NEXT_50 step 34):** Run the 10-point checklist in **staging** per [launch_studio_checklist.md](launch_studio_checklist.md) §4 (create school, select plan, recommend blueprint, import branding, choose starter stack, migration path, preview by role, launch checklist, health score, launch confidence). Mark rows DONE only when verified in staging. Optional: record the run in §4 Staging run log table (date, environment, sign-off, notes). *(Recorded 2026-03-17 in launch_studio_checklist.md §4 and Release sign-off below.)*
- [x] **Migrations (Step 13):** Migrations run in staging first when applicable; prod run per predeploy. *(Approved 2026-03-17.)*
- [x] **Baseline:** Wave 0 baseline/gates confirmed when applicable. *(Approved 2026-03-17.)*

## Build

- [x] **Migrate:** `python manage.py migrate` (or predeploy). *(Approved 2026-03-17.)*
- [x] **Static:** `python manage.py collectstatic --noinput` (or equivalent). *(Approved 2026-03-17.)*
- [x] **Tests / UX bar:** `bash scripts/full_ux_assurance.sh` (Playwright + gate) before major releases on Postgres; or `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` when no browser. See [VISUAL_AND_DASHBOARD_UX_BAR.md](VISUAL_AND_DASHBOARD_UX_BAR.md). *(Approved 2026-03-17; gate run recorded.)*
- [x] **Record gate output (RUNMYCAMPUS §12.1; required, nothing deferred):** Run `bash scripts/record_pre_deploy_gate_output.sh` (or `bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt`). Commit or attach `docs/generated/pre_deploy_gate_run.txt` for this release so gate results are recorded. *(Run 2026-03-16/17 with SKIP_VISUAL_QA=1; output in docs/generated/pre_deploy_gate_run.txt.)* **Refreshed 2026-03-25** — local verification train; see **Verification run log** above and `docs/generated/pre_deploy_gate_run.txt`.

## Deploy

- [x] **Env:** DATABASE_URL, SECRET_KEY, REDIS_URL, CELERY_BROKER_URL and optional EMAIL_* confirmed in target env. *(Approved 2026-03-17.)*
- [x] **Predeploy:** `./scripts/release/render_predeploy.sh` (or platform equivalent) runs and succeeds. *(Approved 2026-03-17.)*
- [x] **Health:** After deploy, GET `/health/` returns 200. *(Approved 2026-03-17.)*
- [x] **If changes don’t appear after deploy:** See [CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md](CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md); bootstrap_platform_catalog + cache clear when needed. *(Approved 2026-03-17.)*

## Security review (Step 49 / RUNMYCAMPUS §12.2)

Before release candidate, complete the following and record result in [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) (pass / fail / N/A and date).

- [x] **Public endpoints:** All public or exempt endpoints in [public_endpoint_audit.md](public_endpoint_audit.md); no new unlisted public endpoints; signature/replay where required (billing/finance webhooks done; others per audit). *Logged 2026-03-13: PASS — see [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md).*
- [x] **AI gateway:** No secrets in context; `get_ai_permission_for_user` enforced in gateway views; staff-only tasks gated (see [AI_GATEWAY_AND_CAPABILITY_FLAGS.md](AI_GATEWAY_AND_CAPABILITY_FLAGS.md), [AI_audit_trail_and_permissions.md](AI_audit_trail_and_permissions.md)). *Logged 2026-03-13: PASS.*
- [x] **Secrets:** `python scripts/lint_secret_exposure.py` pass; no API keys or tokens in client assets or tracked config. *Logged 2026-03-13: PASS.*

**Log:** Each release run must append a row to `docs/SECURITY_REVIEW_LOG.md` with date, release/tag, and the three results. Link from release notes.

## Post-release

- [x] **Smoke:** Login, backend dashboard, one critical flow; no 500s. *(Approved 2026-03-17; post-deploy verification.)*
- [x] **Monitoring:** Error rate and logs checked. *(Approved 2026-03-17.)*
- [x] **Rollback plan:** Documented in [execution/RELEASE_HARDENING_CHECKLIST.md](execution/RELEASE_HARDENING_CHECKLIST.md); revert + DB restore only if needed. *(Approved 2026-03-17.)*

---

## Release sign-off (required to declare plan "done")

Per [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4: the **repo engineering program** is **MET** when (1) §12 gates MET, (2) **release sign-off** recorded, (3) pre-release checklist complete. **Sign-off recorded 2026-03-17** — **future releases** must refresh this table + re-run Phase H / gate.

| Field | Value |
|-------|--------|
| **Date** | 2026-03-17 |
| **Release / tag** | (set at tag/deploy time) |
| **Checked by** | Release sign-off |
| **Launch 10-point run in staging** | Date 2026-03-17 Sign-off Release sign-off (see [launch_studio_checklist.md](launch_studio_checklist.md) §4) |
| **Phase H manual pass** | **MET** for 2026-03-17 sign-off (BR-13 + checklist); **each release:** repeat manual slice + automated `run_phase_h_verification.sh`. |
| **All optionals approved** | 2026-03-17: All optional checklist items and Launch Studio PARTIAL→DONE approved for this release. |
| **Product go-live** | **Business / GTM decision** — engineering gates per SOT are MET; use this checklist for each production cut. |

**First program sign-off (historical):** The 2026-03-17 row above satisfied SOT §11.4 for the **recorded engineering program** (§12 MET). **For each later production deploy:** repeat the **Each future production deploy** runbook; **append** a new sign-off row and fresh SECURITY_REVIEW_LOG / staging table rows as needed—do not delete the historical row.

**2026-03-25 — `local-verification-20260325`:** Repo-only verification train (pre_deploy_gate + Phase H slice + gate log + i18n catalog sync). **Does not** replace staging Launch 10-point or production deploy sign-off; see **Verification run log** table and [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md).
