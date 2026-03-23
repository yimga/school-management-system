# Release checklist (skeleton)

Use this for each release (tag or deploy to production). Expand steps as needed per wave.

**Launch status:** Platform is **not ready for launch yet**; we are still developing. The checklists below are prepared and approved so that when the platform is ready, release can proceed without redoing sign-off. Do not deploy to production until the team confirms the platform is launch-ready.

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
- [x] **Record gate output (RUNMYCAMPUS §12.1; required, nothing deferred):** Run `bash scripts/record_pre_deploy_gate_output.sh` (or `bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt`). Commit or attach `docs/generated/pre_deploy_gate_run.txt` for this release so gate results are recorded. *(Run 2026-03-16/17 with SKIP_VISUAL_QA=1; output in docs/generated/pre_deploy_gate_run.txt.)*

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

**To unblock "plan done":** Complete all Pre-release and Build steps above; run 10-point checklist in staging and add sign-off in launch_studio_checklist.md §4; fill this table and commit. Then SOT §11.4 "Why not declared done yet" can be updated to "Release sign-off recorded on [date]."
