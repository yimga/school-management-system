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
- [ ] Tests: run full test suite or at least `scripts/pre_deploy_gate.sh`.
- [ ] **Record gate output (RUNMYCAMPUS §12.1; required, nothing deferred):** Run `bash scripts/record_pre_deploy_gate_output.sh` (or `bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt`). Commit or attach `docs/generated/pre_deploy_gate_run.txt` for this release so gate results are recorded.

## Deploy

- [ ] Env: confirm DATABASE_URL, SECRET_KEY, REDIS_URL, CELERY_BROKER_URL and optional EMAIL_* in target env.
- [ ] Predeploy: `./scripts/release/render_predeploy.sh` (or platform equivalent) runs and succeeds.
- [ ] Health: after deploy, GET `/health/` returns 200.
- [ ] **If changes don’t appear after deploy (marketplace/catalog/Studio empty):** Run the commands in [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md) **§0** (bootstrap_platform_catalog --all, cache clear). Optional: set **RUN_BOOTSTRAP_PLATFORM_CATALOG=1** in Render env so future deploys seed automatically.

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

**Date:** _______________  
**Release / tag:** _______________  
**Checked by:** _______________
