# Release checklist (skeleton)

Use this for each release (tag or deploy to production). Expand steps as needed per wave.

## Pre-release

- [ ] Branch / version: confirm release branch or tag (e.g. `main` or `v1.2.0`).
- [ ] Changelog: update CHANGELOG or release notes with user-visible changes.
- [ ] **Subtractive cleanup (NEXT_50 step 50):** In release notes, include a "Subtractive cleanup" section listing removed paths, deprecated endpoints, and migrations that delete or replace legacy behavior. See [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md).
- [ ] **Launch Studio staging (NEXT_50 step 34):** Run the 10-point checklist in **staging** per [launch_studio_checklist.md](launch_studio_checklist.md) §4 (create school, select plan, recommend blueprint, import branding, choose starter stack, migration path, preview by role, launch checklist, health score, launch confidence). Mark rows DONE only when verified in staging. Optional: record the run in §4 Staging run log table (date, environment, sign-off, notes).
- [ ] **Migrations (Step 13):** If this release includes `0155_normalize_gilead_residue_runmycampus`, `0156_alter_educationsystemprofile_subject_seed_and_more`, or other subtractive migrations: run `python manage.py migrate` in **staging** first, verify app and health checks, then run in **prod**. Note in release notes per SUBTRACTIVE_CLEANUP_RELEASE_NOTES.
- [ ] Baseline: if Wave 0 applies, confirm [baseline_report.md](baseline_report.md) and gates are current.

## Build

- [ ] Migrate: `python manage.py migrate` (or let predeploy run it).
- [ ] Static: `python manage.py collectstatic --noinput` (or equivalent).
- [ ] Tests: run full test suite or at least `scripts/pre_deploy_gate.sh`. To run the gate without Browser visual QA (e.g. CI without Playwright/server), set `SKIP_VISUAL_QA=1`; run `bash scripts/run_visual_qa.sh` manually when server and Playwright are available.
- [ ] **Record gate output (RUNMYCAMPUS §12.1; required, nothing deferred):** Run `bash scripts/record_pre_deploy_gate_output.sh` (or `bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt`). Commit or attach `docs/generated/pre_deploy_gate_run.txt` for this release so gate results are recorded.

## Deploy

- [ ] Env: confirm DATABASE_URL, SECRET_KEY, REDIS_URL, CELERY_BROKER_URL and optional EMAIL_* in target env.
- [ ] Predeploy: `./scripts/release/render_predeploy.sh` (or platform equivalent) runs and succeeds.
- [ ] Health: after deploy, GET `/health/` returns 200.
- [ ] **If changes don’t appear after deploy (marketplace/catalog/Studio empty):** See [CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md](CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md) (use manager URL; run bootstrap_platform_catalog --all + cache clear in Shell). **RUN_BOOTSTRAP_PLATFORM_CATALOG=1** is in render.yaml so future deploys seed automatically.

## Security review (Step 49 / RUNMYCAMPUS §12.2)

Before release candidate, complete the following and record result in [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) (pass / fail / N/A and date).

- [x] **Public endpoints:** All public or exempt endpoints in [public_endpoint_audit.md](public_endpoint_audit.md); no new unlisted public endpoints; signature/replay where required (billing/finance webhooks done; others per audit). *Logged 2026-03-13: PASS — see [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md).*
- [x] **AI gateway:** No secrets in context; `get_ai_permission_for_user` enforced in gateway views; staff-only tasks gated (see [AI_GATEWAY_AND_CAPABILITY_FLAGS.md](AI_GATEWAY_AND_CAPABILITY_FLAGS.md), [AI_audit_trail_and_permissions.md](AI_audit_trail_and_permissions.md)). *Logged 2026-03-13: PASS.*
- [x] **Secrets:** `python scripts/lint_secret_exposure.py` pass; no API keys or tokens in client assets or tracked config. *Logged 2026-03-13: PASS.*

**Log:** Each release run must append a row to `docs/SECURITY_REVIEW_LOG.md` with date, release/tag, and the three results. Link from release notes.

## Post-release

- [ ] Smoke: open login, backend dashboard, one critical flow; confirm no 500s.
- [ ] Monitoring: check error rate and logs.
- [ ] Rollback plan: if critical failure, revert to previous deploy and restore DB backup only if needed (see [execution/RELEASE_HARDENING_CHECKLIST.md](execution/RELEASE_HARDENING_CHECKLIST.md)).

---

## Release sign-off (required to declare plan "done")

Per [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4: the plan is **done** when (1) §12 gates MET, (2) **release sign-off** recorded, (3) pre-release checklist complete. Do not claim 9.5/10 or "plan complete" until this sign-off is filled.

| Field | Value |
|-------|--------|
| **Date** | _______________ |
| **Release / tag** | _______________ |
| **Checked by** | _______________ |
| **Launch 10-point run in staging** | Date _______________ Sign-off _______________ (see [launch_studio_checklist.md](launch_studio_checklist.md) §4) |
| **Phase H manual pass** | Done / Deferred (if deferred: phase_h_audit + run_phase_h_verification automated slice in place; full manual when prioritized) |

**To unblock "plan done":** Complete all Pre-release and Build steps above; run 10-point checklist in staging and add sign-off in launch_studio_checklist.md §4; fill this table and commit. Then SOT §11.4 "Why not declared done yet" can be updated to "Release sign-off recorded on [date]."
